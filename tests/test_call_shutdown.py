"""Regression coverage for graceful PyTgCalls shutdown in the merged launcher."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CallShutdownTests(unittest.TestCase):
    def test_launcher_uses_the_call_manager_shutdown_not_pytgcalls_stop(self):
        merged = (ROOT / "merged.py").read_text(encoding="utf-8")
        call_module = (ROOT / "music/AoiMusic/core/call.py").read_text(encoding="utf-8")

        self.assertIn("await shutdown_step(\"voice calls\", AoiCall.stop, timeout=25)", merged)
        self.assertIn("await shutdown_step(\"assistant sessions\", userbot.stop, timeout=20)", merged)
        self.assertIn("Fiona exited with an unhandled error:", merged)
        self.assertNotIn("Fiona could not start:", merged)
        self.assertNotIn("call.stop() for call in AoiCall.calls", merged)
        self.assertIn("async def stop(self):", call_module)
        self.assertIn("self.stop_stream(chat_id)", call_module)
        self.assertIn("client._binding.calls()", call_module)
        self.assertIn("PyTgCalls 3.x has no process-wide", call_module)


if __name__ == "__main__":
    unittest.main()
