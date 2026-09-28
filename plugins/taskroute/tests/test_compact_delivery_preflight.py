"""Reject preparation failures before any provider process is started."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compact_delivery_packet as packet


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name).resolve()
        work = self.run / 'workspace'
        work.mkdir()
        body = 'def example():\n    pass\n'
        (work / 'example.py').write_text(body)
        manifest = dict(workspace=str(work), python=sys.executable,
                        source_hashes={'example.py': hashlib.sha256(body.encode()).hexdigest()},
                        canonical_source_hashes={})
        for name, value in [('manifest.json', manifest), ('originals.json', {'example.py': body}),
                            ('settings.json', {}), ('agents.json', {}),
                            ('preflight.json', {'status': 'PASS'})]:
            (self.run / name).write_text(json.dumps(value))
        for name in ['launch.py', 'prompt.txt', 'test.sb']:
            (self.run / name).write_text('fixture')

    def test_missing_scratch_is_created_without_reserving_launch(self):
        self.assertEqual(packet.preflight(self.run)['status'], 'PASS')
        self.assertTrue((self.run / 'scratch').is_dir())
        self.assertEqual(list((self.run / 'scratch').iterdir()), [])
        self.assertFalse((self.run / 'live-launch.reserved.json').exists())
        self.assertEqual(packet.preflight(self.run)['status'], 'PASS')

    def test_changed_input_blocks_before_process(self):
        (self.run / 'workspace/example.py').write_text('changed')
        with patch.object(sys, 'argv', ['packet', str(self.run), '--launch']), \
             patch.object(packet.subprocess, 'run') as launch, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(packet.main(), 2)
        launch.assert_not_called()
        self.assertIn('INITIAL_INPUT_CHANGED', (self.run / 'packet-error.json').read_text())

    def test_missing_file_blocks(self):
        (self.run / 'settings.json').unlink()
        with self.assertRaisesRegex(ValueError, 'MISSING_LAUNCH_FILE'):
            packet.preflight(self.run)

    def test_existing_attempt_cannot_be_replayed(self):
        (self.run / 'live-launch.reserved.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ALREADY_RESERVED'):
            packet.preflight(self.run)

    def test_scratch_file_and_used_directory_block(self):
        scratch = self.run / 'scratch'
        scratch.write_text('not a directory')
        with self.assertRaises(FileExistsError):
            packet.preflight(self.run)
        scratch.unlink()
        scratch.mkdir()
        (scratch / 'old-check').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'SCRATCH_NOT_EMPTY'):
            packet.preflight(self.run)
        self.assertEqual((scratch / 'old-check').read_text(), 'preserve')

    def test_preflight_only_never_launches(self):
        with patch.object(sys, 'argv', ['packet', str(self.run), '--preflight']), \
             patch.object(packet.subprocess, 'run') as launch, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(packet.main(), 0)
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
