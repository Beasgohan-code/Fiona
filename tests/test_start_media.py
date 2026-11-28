import ast
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
START_FILE = ROOT / "waifu/aoiwaifu/modules/start.py"
MUSIC_START_FILE = ROOT / "music/AoiMusic/plugins/bot/start.py"
EN_STRINGS = ROOT / "music/strings/langs/en.yml"


def load_media_kind():
    tree = ast.parse(START_FILE.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_start_media_kind"
    )
    namespace = {"Path": Path, "urlparse": urlparse}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(START_FILE), "exec"), namespace)
    return namespace["_start_media_kind"]


class StartMediaTests(unittest.TestCase):
    def test_media_type_uses_url_path_not_query_string(self):
        media_kind = load_media_kind()
        self.assertEqual(media_kind("https://cdn.example/start.png?token=123"), "photo")
        self.assertEqual(media_kind("https://cdn.example/start.gif?expires=1"), "animation")
        self.assertEqual(media_kind("https://cdn.example/start.mp4?download=1"), "video")

    def test_start_add_button_is_renamed_and_character_link_is_removed(self):
        strings = EN_STRINGS.read_text(encoding="utf-8")
        start_source = MUSIC_START_FILE.read_text(encoding="utf-8")
        self.assertIn('S_B_5 : "➕ Add me"', strings)
        self.assertNotIn("Summon Me", strings)
        self.assertNotIn("Open character collection", start_source)
        self.assertNotIn("?start=waifu", start_source)

    def test_failed_remote_media_send_has_local_and_text_fallbacks(self):
        tree = ast.parse(START_FILE.read_text(encoding="utf-8"))
        sender = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_media_message"
        )
        calls = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(sender)
            if isinstance(node, ast.Call)
        }
        self.assertIn("_download_start_media", calls)
        self.assertIn("reply_panel", calls)


if __name__ == "__main__":
    unittest.main()
