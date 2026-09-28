"""Task-scoped before-tool gate; does not infer semantic intent or resume effects."""
import fcntl
import json
from pathlib import Path
import sys
import time

ROOT = Path(sys.argv[1]).resolve()
M = json.loads((ROOT / 'manifest.json').read_text())
WORK = Path(M['workspace'])


def decide(event):
    if event.get('hook_event_name') != 'PreToolUse':
        return False, 'Unexpected hook event'
    tool, args = event.get('tool_name'), event.get('tool_input')
    if not isinstance(args, dict):
        return False, 'Missing structured tool arguments'
    child = bool(event.get('agent_id'))
    if tool in ('Read', 'Edit', 'Write'):
        value = args.get('file_path')
        if not isinstance(value, str):
            return False, 'Missing path'
        path = Path(value)
        if not path.is_absolute():
            path = WORK / path
        resolved = path.resolve()
        if not resolved.is_relative_to(WORK) or any(p.is_symlink() for p in [path, *path.parents]):
            return False, 'Path outside owned copy or symlink'
        relative = str(resolved.relative_to(WORK))
        if tool == 'Read':
            return (resolved.is_file() and relative in {*M['source_hashes'], M['test_target'], 'TASK.md', 'checks.json'}), 'Read declared evidence only'
        if child:
            return False, 'Reviewer is read-only'
        return relative in (M['target'], M['test_target']), 'Only candidate source and tests may change'
    if tool == 'Bash':
        return (not child and args.get('command') == M['verify_command'] and
                not args.get('run_in_background')), 'Only the exact sandboxed verifier is executable'
    if tool in ('Task', 'Agent'):
        return (not child and args.get('subagent_type') == 'reviewer' and
                isinstance(args.get('prompt'), str) and not args.get('run_in_background') and
                not args.get('resume') and args.get('model') in (None, 'inherit', M['model']) and
                set(args) <= {'subagent_type', 'prompt', 'description', 'model', 'run_in_background'}), 'One foreground read-only reviewer only'
    return False, 'Undeclared tool'


def main():
    try:
        event = json.loads(sys.stdin.read(1000000))
        allowed, reason = decide(event)
        if '--check-only' not in sys.argv:
            with (ROOT / 'gate-events.jsonl').open('a+') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                stream.seek(0)
                previous = [json.loads(line) for line in stream]
                if event.get('tool_name') in ('Task', 'Agent') and any(row['allowed'] and row['tool'] in ('Task', 'Agent') for row in previous):
                    allowed, reason = False, 'Reviewer launch ceiling reached'
                row = dict(time=time.time(), session_id=event.get('session_id'),
                           tool=event.get('tool_name'), tool_use_id=event.get('tool_use_id'),
                           agent_id=event.get('agent_id'), agent_type=event.get('agent_type'),
                           input=event.get('tool_input'), allowed=bool(allowed), reason=reason)
                stream.write(json.dumps(row) + '\n');stream.flush()
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
              'permissionDecision': 'allow' if allowed else 'deny',
              'permissionDecisionReason': reason}}))
    except Exception:
        print('Task gate failed closed', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
