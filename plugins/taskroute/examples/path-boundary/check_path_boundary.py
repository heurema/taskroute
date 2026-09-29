"""Check both sides of a root-alias boundary using filesystem identity as oracle.

Run in a disposable directory: python check_path_boundary.py /path/to/directorydiff
The fixture has one link per path and stable trees; races and arbitrary link chains
are outside this finite domain. No candidate normalization logic is reused.
"""

import itertools
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def check(binary):
    base = Path(tempfile.mkdtemp(prefix="paired-boundary-", dir=Path.cwd()))
    counts = {"allow": 0, "reject": 0}
    failures = []
    initial = {}
    for layout in ("flat", "nested"):
        area = base / layout
        parent = area / ("data" if layout == "flat" else "deep/data")
        target = parent / "target"
        peer = parent / "peer"
        for directory in (target, target / "sub", target / "sub/leaf", peer):
            directory.mkdir(parents=True, exist_ok=True)
            file = directory / "sample.txt"
            file.write_text(str(file.relative_to(base)))
            initial[file] = file.read_bytes()
        anchor = area / "aliases"
        anchor.mkdir()
        alias = anchor / "link"
        alias.symlink_to(target if layout == "flat" else os.path.relpath(target, anchor))
        empty = area / "empty"
        empty.mkdir()
        roots = (target, target / "sub", target / "sub/leaf", peer)
        suffixes = {""}
        for length in (1, 2, 3):
            suffixes.update(
                "/" + "/".join(parts)
                for parts in itertools.product(
                    (".", "..", "sub", "leaf", "target", "peer"), repeat=length
                )
            )
        seen = set()
        for suffix in sorted(suffixes):
            for trailing in ("", "/", "/."):
                raw = str(alias) + suffix + trailing
                if raw in seen:
                    continue
                seen.add(raw)
                try:
                    resolved = next((p for p in roots if os.path.samefile(raw, p)), None)
                except OSError:
                    continue  # Invalid raw roots are covered by the separate property.
                if resolved is None:
                    continue  # Never enumerate outside the known, link-free trees.
                reject = os.path.samefile(resolved, target)
                for side in (0, 1):
                    counts["reject" if reject else "allow"] += 1
                    args = [raw, str(empty)] if side == 0 else [str(empty), raw]
                    result = subprocess.run(
                        [str(binary), *args], capture_output=True, text=True, timeout=2
                    )
                    if reject:
                        passed = (
                            result.returncode == 2 and not result.stdout and bool(result.stderr)
                        )
                    else:
                        expected = sorted(
                            (
                                {
                                    "path": p.relative_to(resolved).as_posix(),
                                    "kind": "deleted" if side == 0 else "added",
                                }
                                for p in resolved.rglob("*")
                                if p.is_file()
                            ),
                            key=lambda x: x["path"],
                        )
                        try:
                            actual = json.loads(result.stdout)
                        except ValueError:
                            actual = None
                        passed = result.returncode == 0 and not result.stderr and actual == expected
                    if not passed:
                        failures.append(
                            {
                                "layout": layout,
                                "suffix": suffix + trailing,
                                "side": side,
                                "expected": "reject" if reject else "allow",
                                "exit": result.returncode,
                                "stdout": result.stdout[:100],
                            }
                        )
    unchanged = all(p.read_bytes() == body for p, body in initial.items())
    report = {
        "cases": counts,
        "violations": len(failures),
        "examples": failures[:8],
        "input_files_unchanged": unchanged,
        "oracle": "OS identity against known distinct fixture directories; exact file report",
    }
    print(json.dumps(report))
    return bool(failures) or not unchanged or not all(counts.values())


if __name__ == "__main__":
    sys.exit(check(Path(sys.argv[1]).resolve()))
