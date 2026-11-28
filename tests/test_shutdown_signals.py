"""Verify the merged runtime records host shutdown signals for diagnostics."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShutdownSignalTests(unittest.TestCase):
    def test_sigterm_is_reported_and_handled_gracefully(self):
        script = r'''
import asyncio
import logging
import os
import signal
from merged import _wait_for_shutdown_signal

async def main():
    waiter = asyncio.create_task(_wait_for_shutdown_signal(logging.getLogger("signal-test")))
    await asyncio.sleep(0.05)
    os.kill(os.getpid(), signal.SIGTERM)
    print(await asyncio.wait_for(waiter, timeout=2))

asyncio.run(main())
'''
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SIGTERM", result.stdout)


if __name__ == "__main__":
    unittest.main()
