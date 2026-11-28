import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCLAIM = ROOT / "waifu/aoiwaifu/modules/hclaim.py"


def load_claim_picker():
    tree = ast.parse(HCLAIM.read_text(encoding="utf-8"))
    defaults = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "DEFAULT_CLAIM_WEIGHTS" for target in node.targets)
    )
    picker = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "pick_claim_rarity"
    )
    namespace = {}
    exec(compile(ast.Module(body=[defaults, picker], type_ignores=[]), str(HCLAIM), "exec"), namespace)
    return namespace["DEFAULT_CLAIM_WEIGHTS"], namespace["pick_claim_rarity"]


class ClaimWeightCompatibilityTests(unittest.TestCase):
    def test_claim_picker_uses_only_available_enabled_rarities_and_their_weights(self):
        defaults, pick = load_claim_picker()

        class Recorder:
            def choices(self, population, weights, k):
                self.call = (population, weights, k)
                return [population[-1]]

        rng = Recorder()
        selected = pick([1, 2, 4], defaults, rng)
        self.assertEqual(selected, 4)
        self.assertEqual(rng.call, ([1, 4], [400.0, 600.0], 1))
        self.assertIsNone(pick([2, 10], defaults, rng))

    def test_claim_admin_controls_persist_and_drive_claim_selection(self):
        admin = (ROOT / "waifu/aoiwaifu/admin/claimchance.py").read_text(encoding="utf-8")
        hclaim = HCLAIM.read_text(encoding="utf-8")
        menu = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        self.assertIn('filters.command(["setclaim"])', admin)
        self.assertIn('filters.command(["claimweights"])', admin)
        self.assertIn("set_claim_rarity_weight(rarity_id, weight, message.from_user.id)", admin)
        self.assertIn('db["claim_rarity_chances"]', hclaim)
        self.assertIn("pick_claim_rarity(available_ids, claim_rarity_weights)", hclaim)
        self.assertIn("('setclaim',", menu)
        self.assertIn("('claimweights',", menu)


if __name__ == "__main__":
    unittest.main()
