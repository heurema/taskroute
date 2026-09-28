"""Offline qualification of test receipts and native reviewer tool aliases."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(TOOLS))
import verify_structured_flow as verifier


class ResultTests(unittest.TestCase):
    def test_structured_result_is_independent_of_long_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'result.json'
            path.write_text(json.dumps(dict(tests=3, failures=0, errors=0, skips=0)))
            result = verifier.read_stats(path, dict(returncode=0, stop_reason=None, feedback='x'*12000))
            self.assertEqual(result['tests'], 3)

    def test_invalid_or_absent_results_never_pass(self):
        samples = [None, '{', '[]', '{}', json.dumps(dict(tests=True, failures=0, errors=0, skips=0)),
                   json.dumps(dict(tests=0, failures=0, errors=0, skips=0)),
                   json.dumps(dict(tests=2, failures=0, errors=0, skips=2))]
        with tempfile.TemporaryDirectory() as temp:
            for i, sample in enumerate(samples):
                with self.subTest(sample=sample):
                    path = Path(temp) / str(i)
                    if sample is not None:
                        path.write_text(sample)
                    with self.assertRaises(ValueError):
                        verifier.read_stats(path, dict(returncode=0, stop_reason=None))

    def test_process_failure_overrides_success_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'result.json'
            path.write_text(json.dumps(dict(tests=1, failures=0, errors=0, skips=0)))
            for code, reason in [(1, None), (-9, None), (0, 'CHECK_TIMEOUT'), (0, 'CHECK_OUTPUT_CAP')]:
                with self.subTest(code=code, reason=reason), self.assertRaises(ValueError):
                    verifier.read_stats(path, dict(returncode=code, stop_reason=reason))

    @unittest.skipUnless(Path('/usr/bin/sandbox-exec').exists(), 'macOS sandbox required')
    def test_real_long_output_original_failure_candidate_success_and_ceiling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); work = root/'workspace'; work.mkdir()
            original = 'def normalize_session(receipts) -> list:\n    return [x["value"] for x in receipts]\n'
            candidate = 'def normalize_session(receipts) -> list:\n    if any(not isinstance(x, dict) for x in receipts):\n        raise ValueError("INVALID_NATIVE_IDENTITY")\n    return [x["value"] for x in receipts]\n'
            source = 'src/sample.py'; test = 'tests/test_claude_accounting_shape.py'
            originals = {source: original}
            manifest = dict(workspace=str(work), target=source, test_target=test, max_checks=1,
                            python=str(Path(sys.executable).resolve()))
            (root/'manifest.json').write_text(json.dumps(manifest)); (root/'originals.json').write_text(json.dumps(originals))
            (work/'src').mkdir(); (work/'tests').mkdir(); (work/source).write_text(candidate)
            (work/test).write_text('import unittest\nfrom sample import normalize_session\nprint("x"*20000)\nclass Checks(unittest.TestCase):\n    def test_invalid(self):\n        with self.assertRaisesRegex(ValueError, "^INVALID_NATIVE_IDENTITY$"):\n            normalize_session([None])\n    def test_valid(self):\n        self.assertEqual(normalize_session([{"value": 2}]), [2])\n')
            (root/'test.sb').write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(root/'scratch'))+') (literal "/dev/null"))\n')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(verifier.verify(root), 0)
            receipt = json.loads((work/'checks.json').read_text())
            self.assertEqual(receipt['status'], 'PASS')
            self.assertEqual(receipt['checks']['original']['stats']['errors'], 1)
            self.assertEqual(receipt['checks']['candidate']['stats']['tests'], 2)
            self.assertEqual(len((root/'check-1-original.log').read_text()), 12000)
            with self.assertRaisesRegex(ValueError, 'CHECK_CEILING'):
                verifier.verify(root)


class ReviewerGateTests(unittest.TestCase):
    def test_native_and_documented_alias_share_one_launch_limit(self):
        for first, second in [('Task', 'Agent'), ('Agent', 'Task')]:
            with self.subTest(first=first), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                (root/'manifest.json').write_text(json.dumps(dict(workspace=str(root), model='fake')))
                def invoke(tool, **extra):
                    event = dict(hook_event_name='PreToolUse', tool_name=tool,
                                 tool_input=dict(subagent_type='reviewer', prompt='Review', **extra))
                    result = subprocess.run([sys.executable, '-B', str(TOOLS/'guard_structured_flow.py'), str(root)],
                                            input=json.dumps(event), capture_output=True, text=True, check=True)
                    return json.loads(result.stdout)['hookSpecificOutput']['permissionDecision']
                self.assertEqual(invoke(first, run_in_background=True), 'deny')
                self.assertEqual(invoke(first), 'allow')
                self.assertEqual(invoke(second), 'deny')

    def test_nested_reviewer_and_writes_are_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root/'manifest.json').write_text(json.dumps(dict(workspace=str(root), model='fake', target='candidate.py', test_target='test.py')))
            for tool, args in [('Task', dict(subagent_type='reviewer', prompt='Review')),
                               ('Write', dict(file_path=str(root/'candidate.py'), content='x'))]:
                event = dict(hook_event_name='PreToolUse', agent_id='review-child', tool_name=tool, tool_input=args)
                result = subprocess.run([sys.executable, '-B', str(TOOLS/'guard_structured_flow.py'), str(root)],
                                        input=json.dumps(event), capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')


if __name__ == '__main__':
    unittest.main()
