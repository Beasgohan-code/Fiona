import json
import logging
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ATOMIC_IO = ROOT / "music" / "AoiMusic" / "utils" / "atomic_io.py"

import importlib.util

_spec = importlib.util.spec_from_file_location("fiona_atomic_io_test", ATOMIC_IO)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)

atomic_write_bytes = _module.atomic_write_bytes
atomic_write_json = _module.atomic_write_json
atomic_write_text = _module.atomic_write_text
load_json = _module.load_json


class AtomicIoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_write_text_round_trip_creates_parents(self):
        target = self.dir / "nested" / "state.txt"
        atomic_write_text(target, "hello fiona")
        self.assertEqual(target.read_text(), "hello fiona")
        # No temp artifacts should remain behind
        leftovers = [p.name for p in self.dir.rglob("*.part")]
        self.assertEqual(leftovers, [])

    def test_atomic_write_bytes_replaces_existing_file(self):
        target = self.dir / "audio.json"
        target.write_bytes(b'{"old": true}')
        atomic_write_bytes(target, b'{"new": true}')
        self.assertEqual(target.read_bytes(), b'{"new": true}')

    def test_failed_json_write_preserves_existing_file_and_leaves_no_temp(self):
        target = self.dir / "command.json"
        target.write_text('[1, 2, 3]', encoding="utf-8")
        with self.assertRaises(TypeError):
            atomic_write_json(target, {"unserializable": object()})
        self.assertEqual(target.read_text(encoding="utf-8"), "[1, 2, 3]")
        leftovers = [p.name for p in self.dir.rglob("*.part")]
        self.assertEqual(leftovers, [])

    def test_atomic_write_json_indent_round_trip(self):
        target = self.dir / "video.json"
        atomic_write_json(target, {"chat": "HIGH"}, indent=4)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"chat": "HIGH"})

    def test_load_json_missing_file_returns_default(self):
        self.assertEqual(load_json(self.dir / "nope.json", []), [])

    def test_load_json_corrupt_file_returns_default_and_logs(self):
        target = self.dir / "broken.json"
        target.write_text("{not json", encoding="utf-8")
        logger = logging.getLogger("atomic_io-test")
        with self.assertLogs(logger, level="WARNING"):
            self.assertEqual(load_json(target, {"safe": True}, logger=logger), {"safe": True})

    def test_load_json_valid_file(self):
        target = self.dir / "ok.json"
        target.write_text('[1, 2, 3]', encoding="utf-8")
        self.assertEqual(load_json(target, []), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
