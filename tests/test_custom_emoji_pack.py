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
        self.assertEqual(len(self.entries), 507)
        self.assertTrue(all(value.isdigit() for _, value in self.entries))
        self.assertTrue(all(key and key == self.pack["normalize_emoji"](key) for key, _ in self.entries))

    def test_supplied_fallback_mappings(self):
        expected = {
            "⭐": "6212881347141181453",
            "✅": "6212749607609310928",
            "💜": "5084974483685507801",
            "👻": "6215238098775711325",
            "⚡": "5042334757040423886",
            "🎵": "5463107823946717464",
            "🔍": "5039649904264217620",
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
        # Multiple star IDs remain available as entries; direct rendering uses
        # the first ID in the newest supplied pack as the deterministic default.
        star_ids = [emoji_id for glyph, emoji_id in self.entries if glyph == "⭐"]
        self.assertGreaterEqual(len(star_ids), 5)
        self.assertEqual(star_ids[0], "5116163917713769254")
        self.assertEqual(self.ids["⭐"], "6212881347141181453")
        # The same heart fallback from multiple packs keeps every ID.
        heart_ids = {emoji_id for glyph, emoji_id in self.entries if glyph == "❤"}
        self.assertIn("5118454879039259395", heart_ids)
        self.assertIn("5040072842578756396", heart_ids)


if __name__ == "__main__":
    unittest.main()
