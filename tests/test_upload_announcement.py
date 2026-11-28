import ast
import html
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD = ROOT / "waifu/aoiwaifu/admin/upload.py"


def load_panel_builder():
    tree = ast.parse(UPLOAD.read_text(encoding="utf-8"))
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_uploaded_character_panel"
    )
    namespace = {
        "html": html,
        "rich_showcase_panel": lambda title, body, emoji: f"<{emoji}>{title}</{emoji}>\\n{body}",
        "premium_text": lambda text: text,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(UPLOAD), "exec"), namespace)
    return namespace["_uploaded_character_panel"]


class UploadAnnouncementTests(unittest.TestCase):
    def test_announcement_has_requested_labels_order_and_photo_type(self):
        panel = load_panel_builder()("16", "Ganyu", "Genshin Impact", "💮 Special Edition", 42, "Uploader")
        expected = [
            "NEW CHARACTER UPLOADED",
            "🆔 <b>ID:</b> <code>16</code>",
            "🎌 <b>Anime:</b> Genshin Impact",
            "👤 <b>Name:</b> Ganyu",
            "✨ <b>Rarity:</b> 💮 Special Edition",
            "📂 <b>Type:</b> PHOTO",
            '👑 <b>Uploaded By:</b> <a href="tg://user?id=42">Uploader</a>',
        ]
        positions = [panel.index(text) for text in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("<blockquote>", panel)

    def test_announcement_escapes_user_content_and_both_upload_paths_use_it(self):
        panel = load_panel_builder()("01", "<Bulma>", "Dragon & Ball", "🔞 Ecchi", 7, "A < B")
        self.assertIn("&lt;Bulma&gt;", panel)
        self.assertIn("Dragon &amp; Ball", panel)
        self.assertIn("A &lt; B", panel)
        source = UPLOAD.read_text(encoding="utf-8")
        self.assertEqual(source.count("caption=_uploaded_character_panel("), 2)


if __name__ == "__main__":
    unittest.main()
