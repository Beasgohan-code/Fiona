import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIFU = ROOT / "waifu/aoiwaifu"
SELL = WAIFU / "modules/sell.py"


def _load_helpers():
    sell_tree = ast.parse(SELL.read_text(encoding="utf-8"))
    helper_names = {"_sale_price", "_partition_duplicates", "_remove_one_duplicate"}
    helpers = [
        node for node in sell_tree.body
        if isinstance(node, ast.FunctionDef) and node.name in helper_names
    ]
    shop_tree = ast.parse((WAIFU / "modules/shop.py").read_text(encoding="utf-8"))
    prices = next(
        ast.literal_eval(node.value)
        for node in shop_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RARITY_PRICE" for target in node.targets)
    )
    namespace = {
        "RARITY_PRICE": prices,
        "_SELL_RATIO": 0.10,
        "_UNKNOWN_SHOP_PRICE": 1000,
    }
    exec(compile(ast.Module(body=helpers, type_ignores=[]), str(SELL), "exec"), namespace)
    return namespace


class SellDuplicateCharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_helpers()

    def test_bulk_partition_keeps_one_of_each_and_preserves_invalid_entries(self):
        characters = [
            {"id": 4, "name": "First", "rarity": "⚪ Common"},
            {"id": 9, "name": "Unique", "rarity": "🔵 Rare"},
            {"id": "4", "name": "Duplicate", "rarity": "⚪ Common"},
            None,
            {"name": "Legacy without id"},
            {"id": 9, "name": "Second duplicate", "rarity": "🔵 Rare"},
        ]
        kept, duplicates = self.helpers["_partition_duplicates"](characters)
        self.assertEqual([item.get("name") if isinstance(item, dict) else item for item in kept], [
            "First", "Unique", None, "Legacy without id"
        ])
        self.assertEqual([item["name"] for item in duplicates], ["Duplicate", "Second duplicate"])

    def test_single_sale_removes_only_an_extra_copy(self):
        characters = [{"id": 12}, {"id": 12, "copy": 2}, {"id": 13}]
        result = self.helpers["_remove_one_duplicate"](characters, "12")
        self.assertIsNotNone(result)
        remaining, sold = result
        self.assertEqual(sum(str(char.get("id")) == "12" for char in remaining), 1)
        self.assertEqual(sold, {"id": 12, "copy": 2})
        self.assertIsNone(self.helpers["_remove_one_duplicate"](remaining, "13"))

    def test_sale_price_is_a_small_rarity_based_refund(self):
        sale_price = self.helpers["_sale_price"]
        self.assertEqual(sale_price({"rarity": "⚪ Common"}), 1500)
        self.assertEqual(sale_price({"rarity": "unknown"}), 100)
        self.assertGreater(sale_price({"rarity": "🔮 Limited Edition"}), sale_price({"rarity": "⚪ Common"}))

    def test_sellall_requires_explicit_confirmation_and_updates_coins_atomically(self):
        source = SELL.read_text(encoding="utf-8")
        self.assertIn('filters.command("sell")', source)
        self.assertIn('filters.command("sellall")', source)
        self.assertIn('args[1].casefold() == "confirm"', source)
        self.assertIn('{"_id": user["_id"], "characters": before}', source)
        self.assertIn('{"$set": {"characters": after}, "$inc": {"balance": amount}}', source)
        self.assertIn('/sellall confirm', source)
        help_source = (WAIFU / "unit/aoi_help.py").read_text(encoding="utf-8")
        self.assertIn("/sell <character_id>", help_source)
        self.assertIn("/sellall confirm", help_source)
        command_menu = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        self.assertIn('(\"sell\", \"Sell one duplicate character for coins\")', command_menu)
        self.assertIn('(\"sellall\", \"Preview and sell duplicate characters\")', command_menu)


if __name__ == "__main__":
    unittest.main()
