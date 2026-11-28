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
        # Stale spawns (replaced or expired) are rejected via message id match,
        # implemented in the shared resolver used by both the pyrogram and the PTB twin.
        self.assertIn("spawn_hint_answer(chat_id, message_id", hint_handler)
        resolver = self.spawn_source[self.spawn_source.index("def spawn_hint_answer"):]
        self.assertIn('.get("message_id")', resolver)
        self.assertIn('state.get("ranaway")', resolver)

    def test_catch_caption_mentions_hunt_alias(self):
        self.assertIn("/hunt &lt;name&gt;", self.spawn_source)


class SpawnHintTests(unittest.TestCase):
    def setUp(self):
        self.spawn_source = SPAWN_FILE.read_text(encoding="utf-8")

    def _build_spawn_hint(self, name):
        import ast

        tree = ast.parse(self.spawn_source)
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "build_spawn_hint"
        )
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(SPAWN_FILE), "exec"), namespace)
        return namespace["build_spawn_hint"](name)

    def test_hint_masks_single_word_name(self):
        self.assertEqual(self._build_spawn_hint("Goku"), "💡 HINT: G__u")

    def test_hint_keeps_word_boundaries_for_multi_word_names(self):
        self.assertEqual(self._build_spawn_hint("Monkey D Luffy"), "💡 HINT: M____y D L___y")

    def test_hint_hides_two_letter_words_partially(self):
        self.assertEqual(self._build_spawn_hint("Go"), "💡 HINT: G_")

    def test_hint_never_echoes_full_name(self):
        masked = self._build_spawn_hint("Kirigakure Shito")
        self.assertNotIn("Kirigakure", masked)
        self.assertNotIn("Shito", masked)
        self.assertIn("K________e", masked)
        self.assertIn("S___o", masked)

    def test_hint_unknown_or_missing_name_has_no_clue(self):
        self.assertIsNone(self._build_spawn_hint(""))
        self.assertIsNone(self._build_spawn_hint("unknown"))


if __name__ == "__main__":
    unittest.main()
