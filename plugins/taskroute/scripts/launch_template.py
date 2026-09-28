"""One reserved structured CLI trial; never retry or resume automatically."""

import hashlib
import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

from runtime import Journal, clean_environment

ROOT = Path(__file__).resolve().parent
M = json.loads((ROOT / "manifest.json").read_text())

session = str(uuid.uuid4())
binary = M["claude_binary"]
args = [
    binary,
    "-p",
    "--verbose",
    "--output-format",
    "stream-json",
    "--model",
    M["model"],
    "--effort",
    M["effort"],
    "--session-id",
    session,
    "--restricted",
    "--setting-sources",
    "",
    "--tools",
    "Read,Write,Edit,Bash,Agent",
    "--allowedTools",
    "Read,Write,Edit,Bash,Agent",
    "--permission-mode",
    "dontAsk",
    "--permission-prompts",
    "none",
    "--no-chrome",
    "--disable-slash-commands",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--settings",
    str(ROOT / "settings.json"),
    "--agents",
    str(ROOT / "agents.json"),
    "--max-turns",
    str(M["max_parent_turns"]),
    "--forward-subagent-text",
    "--prompt-suggestions",
    "false",
]
for name, digest in M["canonical_source_hashes"].items():
    if not (hashlib.sha256((Path(M["project_root"]) / name).read_bytes()).hexdigest() == digest):
        raise ValueError("SOURCE_INTEGRITY_CHECK_FAILED")
if not (json.loads((ROOT / "preflight.json").read_text())["status"] == "PASS"):
    raise ValueError("SOURCE_INTEGRITY_CHECK_FAILED")
Journal(ROOT).reserve(
    "live-launch",
    session_id=session,
    argv=args,
    time=time.time(),
    prompt_sha256=hashlib.sha256((ROOT / "prompt.txt").read_bytes()).hexdigest(),
)
start = time.monotonic()
status = "ENDED"
with (ROOT / "stdout.jsonl").open("wb") as out, (ROOT / "stderr.log").open("wb") as err:
    p = subprocess.Popen(
        args,
        cwd=M["workspace"],
        env=clean_environment(),
        stdin=subprocess.PIPE,
        stdout=out,
        stderr=err,
        start_new_session=True,
    )
    (ROOT / "process.json").write_text(json.dumps({"pid": p.pid, "session_id": session}))
    try:
        p.communicate((ROOT / "prompt.txt").read_bytes(), timeout=M["wall_seconds"])
    except subprocess.TimeoutExpired:
        status = "TIMEOUT_UNKNOWN"
        os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
result = {
    "status": status,
    "exit_code": p.returncode,
    "wall_seconds": round(time.monotonic() - start, 3),
    "session_id": session,
    "live_launches": 1,
    "resends": 0,
}
(ROOT / "terminal.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
