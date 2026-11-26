import ast
import os
import shutil
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_FILE = ROOT / "music/AoiMusic/platforms/Youtube.py"


def load_stager(cache_dir):
    tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
    stager = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_stage_cookie_file"
    )
    fake_tempfile = SimpleNamespace(gettempdir=lambda: str(cache_dir))
    namespace = {
        "os": os,
        "shutil": shutil,
        "tempfile": fake_tempfile,
        "threading": threading,
        "_COOKIE_COPY_LOCK": threading.Lock(),
        "_COOKIE_COPY_SIGNATURE": None,
        "_COOKIE_COPY_SOURCE": None,
        "_log": lambda *args, **kwargs: None,
    }
    exec(compile(ast.Module(body=[stager], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)
    return namespace["_stage_cookie_file"]


class YouTubeCookieStagingTests(unittest.TestCase):
    def test_secret_source_is_copied_to_private_writable_runtime_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "secret-cookies.txt"
            secret.write_text("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tSID\tsecret\n")
            secret.chmod(0o444)
            stage = load_stager(root / "runtime")

            staged_path = Path(stage(str(secret)))
            self.assertNotEqual(staged_path, secret)
            self.assertEqual(staged_path.read_text(), secret.read_text())
            self.assertEqual(stat.S_IMODE(staged_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o444)

    def test_staged_copy_refreshes_when_render_secret_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "secret-cookies.txt"
            secret.write_text("# Netscape HTTP Cookie File\n# version one\n")
            stage = load_stager(root / "runtime")
            staged_path = Path(stage(str(secret)))
            secret.write_text("# Netscape HTTP Cookie File\n# version two and newer\n")
            os.utime(secret, None)

            self.assertIn("version two", Path(stage(str(secret))).read_text())
            self.assertEqual(staged_path, Path(stage(str(secret))))


if __name__ == "__main__":
    unittest.main()
