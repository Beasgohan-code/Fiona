import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ECONOMY = ROOT / "waifu/aoiwaifu/admin/economy.py"


class AdminMoneyCompatibilityTests(unittest.TestCase):
    def test_summon_owner_money_aliases_are_registered_and_owner_gated(self):
        source = ECONOMY.read_text(encoding="utf-8")
        menu = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        self.assertIn('filters.command(["givemoney"])', source)
        self.assertIn('filters.command(["rmmoney"])', source)
        self.assertIn("message.from_user.id != OWNER_ID", source)
        self.assertIn("('givemoney',", menu)
        self.assertIn("('rmmoney',", menu)

    def test_removal_is_bounded_by_available_balance(self):
        source = ECONOMY.read_text(encoding="utf-8")
        self.assertIn("adjusted = min(requested_amount, current_balance)", source)
        self.assertIn('{"id": target_id, "balance": {"$gte": adjusted}}', source)
        self.assertIn('{"$inc": {"balance": -adjusted}}', source)


if __name__ == "__main__":
    unittest.main()
