import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RichgramCharacterBrowseTests(unittest.TestCase):
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
        self.assertIn("</blockquote>", harem)
        self.assertIn("FIONA CHARACTER BAZAAR", shop)
        self.assertIn("BAZAAR CHARACTER", shop)
        self.assertIn("<blockquote>", shop)
        self.assertIn("purchase_hint", shop)
        self.assertIn("reply_photo_panel(", shop)


if __name__ == "__main__":
    unittest.main()
