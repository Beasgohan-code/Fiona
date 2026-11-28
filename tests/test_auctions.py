from __future__ import annotations

import ast
import py_compile
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUCTION = ROOT / "waifu" / "aoiwaifu" / "modules" / "auction.py"
WAIFU_HELP = ROOT / "music" / "AoiMusic" / "plugins" / "waifu_help.py"


def source() -> str:
    return AUCTION.read_text(encoding="utf-8")


import unittest


class AuctionModuleTests(unittest.TestCase):
    def test_auction_module_compiles(self):
        with tempfile.NamedTemporaryFile(suffix=".pyc") as compiled:
            py_compile.compile(str(AUCTION), cfile=compiled.name, doraise=True)

    def test_auction_uses_mongo_and_no_sqlite(self):
        text = source()
        self.assertIn('db["character_auctions"]', text)
        self.assertIn("pending_refunds_collection", text)
        self.assertNotIn("sqlite3", text.lower())
        self.assertNotIn("summon.db", text.lower())
        self.assertNotIn("CREATE TABLE", text)

    def test_listing_escrow_removes_a_copy_with_compare_and_set(self):
        text = source()
        self.assertIn('{"_id": user["_id"], "characters": characters}', text)
        self.assertIn('{"$set": {"characters": after}}', text)
        self.assertIn("auction_instance_id", text)
        self.assertIn("_deliver_escrow_copy", text)

    def test_bids_are_debited_before_cas_and_refunded_on_loss(self):
        text = source()
        self.assertIn('{"id": user_id, "balance": {"$gte": debit_amount}}', text)
        self.assertIn('{"$inc": {"balance": -debit_amount}}', text)
        self.assertIn('"current_bid": current_bid', text)
        self.assertIn('"highest_bidder_id": previous_bidder', text)
        self.assertIn('f"refund:{auction_id}:{version + 1}:{previous_bidder}"', text)
        self.assertIn("marker_field=\"auction_refund_ids\"", text)
        self.assertIn("_enqueue_refund", text)

    def test_auction_settlement_is_idempotent(self):
        text = source()
        self.assertIn('"status": "settling"', text)
        self.assertIn('{"auction_id": auction_id, "status": "settling"}', text)
        self.assertIn('"characters.auction_instance_id": {"$ne": instance_id}', text)
        self.assertIn('marker_field="auction_payouts"', text)
        self.assertIn('"auction_refund_ids"', text)
        self.assertIn("pending_refunds_collection.find", text)

    def test_auction_commands_are_registered(self):
        text = source()
        for command in ("auction", "bid", "auctionlist", "mybids", "cancelauction"):
            self.assertRegex(text, rf'filters\.command\([^\n]*["\']{re.escape(command)}["\']', command)
        self.assertIn('"auction_bid_"', text)
        self.assertIn('"auction_custom_"', text)
        self.assertIn('"auction_refresh_"', text)
        self.assertIn('"auction_view_"', text)

    def test_auction_buttons_use_registered_premium_icons(self):
        registry = (ROOT / "music" / "AoiMusic" / "utils" / "premium_emoji.py").read_text(encoding="utf-8")
        tree = ast.parse(source())
        keys = re.findall(r'"([A-Z_]+)":\s*\(', registry)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "emoji" and isinstance(keyword.value, ast.Constant):
                    self.assertIn(keyword.value.value, keys, f"{keyword.value.value} is not a registered premium emoji key")

    def test_unified_menu_and_help_mention_auction_bundle(self):
        commands = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        help_text = WAIFU_HELP.read_text(encoding="utf-8")
        compatibility = (ROOT / "SUMMON_BOT_COMPATIBILITY.md").read_text(encoding="utf-8")
        for command in ("auction", "bid", "auctionlist", "mybids", "cancelauction"):
            self.assertIn(f'("{command}",', commands)
            self.assertIn(f"/{command}", help_text)
        self.assertIn("character_auctions", compatibility)
        self.assertIn("idempotently", compatibility.lower())


if __name__ == "__main__":
    unittest.main()
