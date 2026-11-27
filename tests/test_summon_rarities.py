import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WAIFU = ROOT / "waifu" / "aoiwaifu"


def assigned_literal(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} assignment not found in {path}")


class SummonRarityAlignmentTests(unittest.TestCase):
    def test_canonical_rarities_match_spawn_weights_and_shop_prices(self):
        rarity_map = assigned_literal(WAIFU / "unit" / "aoi_rarity.py", "rarity_map")
        spawn_weights = assigned_literal(
            WAIFU / "unit" / "aoi_send_img.py", "RARITY_WEIGHTS"
        )
        shop_prices = assigned_literal(WAIFU / "modules" / "shop.py", "RARITY_PRICE")

        self.assertEqual(len(rarity_map), 18)
        self.assertEqual(rarity_map[15], "🔞 Ecchi")
        canonical_names = list(rarity_map.values())
        self.assertEqual(list(spawn_weights), canonical_names)
        self.assertEqual(set(shop_prices), set(canonical_names))

    def test_special_rarity_rank_uses_summon_amv_not_removed_diwali(self):
        rank_source = (WAIFU / "modules" / "rank.py").read_text(encoding="utf-8")
        self.assertIn("('amv', 'AMV', 'STAR')", rank_source)
        self.assertIn("'🎥 AMV Edition'", rank_source)
        self.assertNotIn("Diwali", rank_source)


if __name__ == "__main__":
    unittest.main()
