import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RichgramCharacterBrowseTests(unittest.TestCase):
    def test_check_id_lookup_supports_legacy_numeric_and_zero_padded_ids(self):
        tree = ast.parse((ROOT / "waifu/aoiwaifu/modules/check.py").read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_character_id_candidates"
        )
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "check.py", "exec"), namespace)
        candidates = namespace["_character_id_candidates"]
        self.assertEqual(candidates("1"), ["1", "01", 1])
        self.assertEqual(candidates("01"), ["01", 1])
        self.assertEqual(candidates("abc"), ["abc"])

    def test_character_dossier_and_owner_list_are_structured_richgram_panels(self):
        source = (ROOT / "waifu/aoiwaifu/modules/check.py").read_text(encoding="utf-8")
        self.assertIn("rich_showcase_panel(", source)
        self.assertIn("CHARACTER DOSSIER", source)
        self.assertIn("COLLECTOR OWNERS", source)
        self.assertIn("<blockquote>", source)
        self.assertIn("<p><i>Tap the button below", source)
        self.assertIn("reply_photo_panel(", source)
        self.assertIn("reply_video_panel(", source)

    def test_collection_and_shop_views_have_rich_headings_and_quoted_details(self):
        harem = (ROOT / "waifu/aoiwaifu/modules/harem.py").read_text(encoding="utf-8")
        shop = (ROOT / "waifu/aoiwaifu/modules/shop.py").read_text(encoding="utf-8")
        self.assertIn("rich_showcase_panel(", harem)
        self.assertIn("rich_showcase_panel(f'{user_first_name} · COLLECTION'", harem)
        self.assertNotIn("escape(user_first_name)", harem)
        self.assertIn("</blockquote>", harem)
        self.assertIn("FIONA CHARACTER BAZAAR", shop)
        self.assertIn("BAZAAR CHARACTER", shop)
        self.assertIn("<blockquote>", shop)
        self.assertIn("purchase_hint", shop)
        self.assertIn("reply_photo_panel(", shop)


if __name__ == "__main__":
    unittest.main()
