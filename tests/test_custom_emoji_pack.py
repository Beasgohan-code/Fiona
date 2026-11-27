import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "music/AoiMusic/utils/custom_emoji_pack.py"
REGISTRY_PATH = ROOT / "music/AoiMusic/utils/premium_emoji.py"
RICH_MSG_PATH = ROOT / "music/AoiMusic/utils/rich_msg.py"


class CustomEmojiPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = runpy.run_path(str(PACK_PATH))
        cls.ids = cls.pack["CUSTOM_EMOJI_IDS"]
        cls.entries = cls.pack["CUSTOM_EMOJI_ENTRIES"]

    def test_all_custom_ids_are_numeric_and_fallbacks_are_unicode(self):
        self.assertGreaterEqual(len(self.entries), 100)
        self.assertTrue(all(value.isdigit() for _, value in self.entries))
        self.assertTrue(all(key and key == self.pack["normalize_emoji"](key) for key, _ in self.entries))

    def test_supplied_fallback_mappings(self):
        expected = {
            "✅": "5084979757905347540",
            "💜": "5084974483685507801",
            "👻": "5082478549340783285",
            "⚡": "5085022089103016925",
            "🎵": "5172447776205702031",
            "🔍": "5258274739041883702",
            "📂": "5341492148468465410",
        }
        for fallback, emoji_id in expected.items():
            with self.subTest(fallback=fallback):
                self.assertEqual(self.ids[fallback], emoji_id)

    def test_registry_and_rich_ui_resolve_supplemental_ids(self):
        registry = REGISTRY_PATH.read_text(encoding="utf-8")
        rich_msg = RICH_MSG_PATH.read_text(encoding="utf-8")
        self.assertIn("for _index, (_glyph, _custom_id) in enumerate(CUSTOM_EMOJI_ENTRIES,", registry)
        self.assertIn("PREMIUM_EMOJIS[_custom_key] = (_custom_id, _glyph)", registry)
        self.assertIn("custom_id = CUSTOM_EMOJI_IDS.get(key)", rich_msg)

    def test_distinct_same_fallback_ids_are_kept(self):
        # Two heart variants in the supplied data have separate IDs and remain
        # independently addressable, even though they render similarly.
        self.assertEqual(self.ids["♥"], "5100657930429006538")
        self.assertEqual(self.ids["❤"], "5118454879039259395")


if __name__ == "__main__":
    unittest.main()
