import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPAWN_FILE = ROOT / "waifu/aoiwaifu/unit/aoi_send_img.py"
GUESS_FILE = ROOT / "waifu/aoiwaifu/modules/guess.py"


class SpawnCardTests(unittest.TestCase):
    def setUp(self):
        self.spawn_source = SPAWN_FILE.read_text(encoding="utf-8")
        self.guess_source = GUESS_FILE.read_text(encoding="utf-8")

    def test_spawn_caption_never_renders_empty_rarity(self):
        # Catalog rows with a missing/blank rarity must fall back to "Unknown"
        # and log, instead of shipping an empty "Rarity ·" line.
        self.assertIn('raw_rarity = str(character.get("rarity") or "").strip()', self.spawn_source)
        self.assertIn('"rarity": raw_rarity or "Unknown"', self.spawn_source)
        self.assertIn("no rarity in the catalog", self.spawn_source)

    def test_spawn_card_attaches_hint_button_on_every_send_path(self):
        self.assertIn('callback_data=f"spawn_hint:{chat_id}"', self.spawn_source)
        media = self.spawn_source.index("await send_media_panel")
        panel = self.spawn_source.index("await send_panel(bot, chat_id=chat_id, text=caption")
        fallback = self.spawn_source.index("bot.send_message")
        self.assertIn("reply_markup=hint_markup", self.spawn_source[media:media + 400])
        self.assertIn("reply_markup=hint_markup", self.spawn_source[panel:panel + 200])
        self.assertIn("reply_markup=hint_markup", self.spawn_source[fallback:fallback + 200])

    def test_hint_callback_is_registered_and_never_leaks_the_name(self):
        self.assertRegex(self.guess_source, r'on_callback_query\(filters\.regex\(r"\^spawn_hint:\(-\?\\d\+\)\$"\)\)')
        hint_handler = self.guess_source[self.guess_source.index("async def spawn_hint"):]
        self.assertIn("show_alert=True", hint_handler)
        # The full character name must never be sent in the hint answer.
        answer_calls = re.findall(r"callback_query\.answer\(([^)]*)\)", hint_handler)
        self.assertTrue(answer_calls)
        for call in answer_calls:
            self.assertNotIn('state.get("name")', call)
            self.assertNotIn("name,", call)
        # Stale spawns (replaced or expired) are rejected via message id match.
        self.assertIn('.get("message_id")', hint_handler)

    def test_catch_caption_mentions_hunt_alias(self):
        self.assertIn("/hunt &lt;name&gt;", self.spawn_source)


if __name__ == "__main__":
    unittest.main()
