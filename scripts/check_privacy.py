#!/usr/bin/env python3
"""Scan staged Git objects or history; never echo detected personal data or secrets."""

import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

RULES = {
    "user-home-path": re.compile(
        rb"(?:/Users/|/home/)[A-Za-z0-9_.-]+(?:/|\\\\)|[A-Za-z]:[\\\\/]+Users[\\\\/]+[A-Za-z0-9_.-]+",
        re.I,
    ),
    "email": re.compile(
        rb"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+", re.I
    ),
    "phone-like": re.compile(rb"(?<![A-Za-z0-9])\+[1-9](?:[ ()-]?\d){8,14}(?!\d)"),
    "private-key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
}
RESERVED_DOMAINS = (b"example.com", b"example.org", b"example.net", b"example.invalid")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def findings(data: bytes, terms: list[bytes]) -> list[tuple[str, int]]:
    found = []
    for rule, pattern in RULES.items():
        for match in pattern.finditer(data):
            if (
                rule == "email"
                and match.group().rsplit(b"@", 1)[1].lower() in RESERVED_DOMAINS
            ):
                continue
            found.append((rule, data[: match.start()].count(b"\n") + 1))
    for term in terms:
        offset = data.lower().find(term.lower())
        if offset >= 0:
            found.append(("private-blocklist", data[:offset].count(b"\n") + 1))
    return sorted(set(found))


def objects(history: bool) -> dict[str, str]:
    if history:
        entries = git("rev-list", "--objects", "--all").splitlines()
        names = {}
        for row in entries:
            parts = row.split(b" ", 1)
            oid = parts[0].decode()
            name = (
                parts[1].decode("utf-8", errors="replace")
                if len(parts) == 2
                else "history-object"
            )
            names[oid] = names.get(oid, "") + "\n" + name
        return names
    entries = {}
    for row in git("ls-files", "--stage", "-z").split(b"\0"):
        if not row:
            continue
        header, name = row.split(b"\t", 1)
        mode, oid, stage = header.split()
        if stage != b"0" or mode == b"160000":
            raise ValueError("UNMERGED_OR_SUBMODULE_INDEX")
        # Scan file names too; never materialize arbitrary Git paths.
        key = oid.decode()
        entries[key] = (
            entries.get(key, "") + "\n" + name.decode("utf-8", errors="replace")
        )
    return entries


def contents(oids: list[str]):
    response = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=("\n".join(oids) + "\n").encode(),
        capture_output=True,
        check=True,
    )
    stream = io.BytesIO(response.stdout)
    for _ in oids:
        header = stream.readline().split()
        if len(header) != 3:
            raise ValueError("UNREADABLE_GIT_OBJECT")
        oid, kind, size = header
        data = stream.read(int(size))
        if stream.read(1) != b"\n":
            raise ValueError("INVALID_GIT_OBJECT_STREAM")
        if kind == b"blob":
            yield oid.decode(), data


def scan(history: bool) -> int:
    binary = shutil.which("gitleaks")
    if binary is None:
        raise ValueError("GITLEAKS_REQUIRED")
    private_file = Path(
        os.fsdecode(git("rev-parse", "--git-path", "privacy-terms.json").strip())
    )
    terms = []
    if private_file.exists():
        values = json.loads(private_file.read_text())
        if not isinstance(values, list) or any(
            not isinstance(v, str) or len(v) < 3 for v in values
        ):
            raise ValueError("INVALID_PRIVATE_BLOCKLIST")
        terms = [v.encode() for v in values]
    entries = objects(history)
    issues = []
    with tempfile.TemporaryDirectory(prefix="taskroute-privacy-") as temp:
        root = Path(temp)
        snapshot = root / "objects"
        snapshot.mkdir()
        for oid, data in contents(list(entries)):
            (snapshot / (oid + ".txt")).write_bytes(data)
            for rule, line in findings(data, terms) + findings(
                entries[oid].encode(), terms
            ):
                issues.append(f"{oid[:12]}:{line}: {rule}")
        config = root / "rules.toml"
        config.write_text("[extend]\nuseDefault = true\n")
        report = root / "report.json"
        environment = {
            k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_")
        }
        result = subprocess.run(
            [
                binary,
                "dir",
                str(snapshot),
                "--config",
                str(config),
                "--gitleaks-ignore-path",
                str(root / "no-ignores"),
                "--ignore-gitleaks-allow",
                "--max-archive-depth",
                "2",
                "--redact",
                "--no-banner",
                "--no-color",
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ],
            env=environment,
            capture_output=True,
        )
        if result.returncode not in (0, 1):
            raise ValueError("GITLEAKS_SCAN_FAILED")
        if result.returncode == 1:
            if not report.exists():
                raise ValueError("GITLEAKS_REPORT_MISSING")
            for item in json.loads(report.read_text()):
                issues.append(
                    f"{Path(item['File']).stem[:12]}:{item['StartLine']}: secret/{item['RuleID']}"
                )
            if not issues:
                raise ValueError("GITLEAKS_FAILURE_WITHOUT_FINDINGS")
    if issues:
        print("Privacy check BLOCKED (values redacted):")
        print("\n".join(sorted(set(issues))))
        return 1
    print(
        f"Privacy check PASS: {'history' if history else 'complete staged snapshot'}; {len(entries)} Git objects."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    try:
        return scan(args.history)
    except (OSError, ValueError, subprocess.SubprocessError):
        print(
            "Privacy check BLOCKED: scanner/tool/config error; no content printed.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
