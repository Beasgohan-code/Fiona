import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPAWN_FILE = ROOT / "waifu/aoiwaifu/unit/aoi_send_img.py"


def load_rarity_picker():
    tree = ast.parse(SPAWN_FILE.read_text(encoding="utf-8"))
    weights = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RARITY_WEIGHTS" for target in node.targets)
    )
    active_picker = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "active_spawn_rarities"
    )
    picker = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "pick_weighted_rarity"
    )
    max_weight = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "MAX_SPAWN_WEIGHT" for target in node.targets)
    )

    class DeterministicRandom:
        @staticmethod
        def uniform(low, high):
            return low

    import math
    namespace = {"system_random": DeterministicRandom(), "math": math}
    exec(compile(ast.Module(body=[weights, max_weight, active_picker, picker], type_ignores=[]), str(SPAWN_FILE), "exec"), namespace)
    return namespace["pick_weighted_rarity"], namespace["RARITY_WEIGHTS"]


class SpawnCompatibilityTests(unittest.TestCase):
    def test_auto_spawn_picker_respects_enabled_rarities_and_empty_pool(self):
        picker, weights = load_rarity_picker()
        weights["Disabled test rarity"] = (1000, False)
        self.assertEqual(
            picker(["Disabled test rarity", "⚪ Common", "🔵 Rare"]),
            "⚪ Common",
        )
        self.assertEqual(picker(["Disabled test rarity"]), "")
        self.assertEqual(picker([]), "")

    def test_auto_spawn_picker_ignores_invalid_weights_and_respects_global_disable(self):
        picker, weights = load_rarity_picker()
        import math
        from_source = (ROOT / "waifu/aoiwaifu/unit/aoi_send_img.py").read_text(encoding="utf-8")
        self.assertIn("if not active_rarities:", from_source)
        self.assertIn("return None", from_source[from_source.index("if not active_rarities:"):])
        weights["nan"] = (math.nan, True)
        weights["infinity"] = (math.inf, True)
        weights["too large"] = (1_000_001, True)
        self.assertEqual(picker(["nan", "infinity", "too large"]), "")

    def test_threshold_spawn_is_implemented_and_manual_spawn_is_owner_only(self):
        source = SPAWN_FILE.read_text(encoding="utf-8")
        manual = (ROOT / "waifu/aoiwaifu/admin/spawn.py").read_text(encoding="utf-8")
        ctime = (ROOT / "waifu/aoiwaifu/admin/ctime.py").read_text(encoding="utf-8")
        self.assertIn("await spawn_character(context.bot, chat.id)", source)
        self.assertIn("@app.on_message(filters.command([\"spawn\"]) & filters.group)", manual)
        self.assertIn("message.from_user.id != OWNER_ID", manual)
        self.assertIn('filters.command(["ctime", "changetime"])', ctime)

    def test_rarity_weight_controls_are_owner_only_and_persistent(self):
        chance = (ROOT / "waifu/aoiwaifu/admin/chance.py").read_text(encoding="utf-8")
        source = SPAWN_FILE.read_text(encoding="utf-8")
        self.assertIn('filters.command(["chance"])', chance)
        self.assertIn('filters.command(["chancelist"])', chance)
        self.assertIn("message.from_user.id == OWNER_ID", chance)
        self.assertIn("set_spawn_weight(rarity_id, rarity, weight, message.from_user.id)", chance)
        self.assertIn("MAX_SPAWN_WEIGHT = 1_000_000", source)
        self.assertIn("MAX_SPAWN_WEIGHT", chance)
        self.assertIn('("RARITY", "WEIGHT", "ODDS")', chance)
        self.assertIn("weight / total_weight * 100", chance)
        self.assertIn('db["spawn_rarity_chances"]', source)
        self.assertIn("/chancelist", (ROOT / "SUMMON_BOT_COMPATIBILITY.md").read_text(encoding="utf-8"))

    def test_spawn_state_supports_existing_guess_and_timeout_flow(self):
        source = SPAWN_FILE.read_text(encoding="utf-8")
        self.assertIn('"name": str(character.get("name") or "Unknown")', source)
        self.assertIn('"ranaway": False', source)
        self.assertIn('name=f"expire_session_{chat_id}"', source)
        self.assertIn("first_correct_guesses.pop(chat_id, None)", source)

    def test_spawn_lifecycle_uses_richgram_panels_and_blockquotes(self):
        source = SPAWN_FILE.read_text(encoding="utf-8")
        status = (ROOT / "waifu/aoiwaifu/modules/checkspawn.py").read_text(encoding="utf-8")
        guess = (ROOT / "waifu/aoiwaifu/modules/guess.py").read_text(encoding="utf-8")
        manual = (ROOT / "waifu/aoiwaifu/admin/spawn.py").read_text(encoding="utf-8")
        self.assertIn("send_media_panel", source)
        self.assertIn("send_panel", source)
        self.assertIn("premium_text(rich_showcase_panel(", source)
        self.assertIn("<blockquote>", source)
        self.assertIn("<blockquote>", status)
        self.assertIn("<blockquote>", guess)
        self.assertIn("reply_panel(", manual)
        self.assertIn("<blockquote>", manual)
        rich_ui = (ROOT / "waifu/aoiwaifu/unit/rich_ui.py").read_text(encoding="utf-8")
        self.assertIn("def rich_showcase_panel(", rich_ui)
        self.assertIn('heading = f"<h4>{emoji}', rich_ui)


if __name__ == "__main__":
    unittest.main()
