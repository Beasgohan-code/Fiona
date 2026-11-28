from __future__ import annotations

import py_compile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUP_INFO = ROOT / "music" / "AoiMusic" / "plugins" / "manage" / "group_info.py"
COLLECTION_VALUE = ROOT / "waifu" / "aoiwaifu" / "modules" / "collection_value.py"
AUCTION_HISTORY = ROOT / "waifu" / "aoiwaifu" / "modules" / "auction_history.py"
HELP = ROOT / "music" / "AoiMusic" / "plugins" / "bot" / "help.py"
INLINE_QUERY = ROOT / "music" / "AoiMusic" / "utils" / "inlinequery.py"


class FionaFeatureBundleTests(unittest.TestCase):
    def test_new_modules_compile(self):
        with tempfile.NamedTemporaryFile(suffix=".pyc") as compiled:
            for path in (GROUP_INFO, COLLECTION_VALUE, AUCTION_HISTORY):
                py_compile.compile(str(path), cfile=compiled.name, doraise=True)

    def test_group_info_uses_group_context_and_rich_management_style(self):
        source = GROUP_INFO.read_text(encoding="utf-8")
        self.assertIn('filters.command(["ginfo", "groupinfo", "chatinfo"])', source)
        self.assertIn("filters.group", source)
        self.assertIn("get_chat_members_count", source)
        self.assertIn("ChatMembersFilter.ADMINISTRATORS", source)
        self.assertIn("get_chat_settings", source)
        self.assertIn("get_flood_config", source)
        self.assertIn("mgmt_reply", source)
        self.assertNotIn("check_admin_and_bot", source, "/ginfo should be read-only for group members")

    def test_collection_value_uses_Fiona_rarity_prices(self):
        source = COLLECTION_VALUE.read_text(encoding="utf-8")
        self.assertIn("from aoiwaifu.modules.shop import RARITY_PRICE", source)
        self.assertIn('filters.command(["collectionvalue", "colvalue", "haremvalue"])', source)
        self.assertIn("Counter", source)
        self.assertIn("rich_ui", source)
        self.assertIn("Estimated collection value", source)

    def test_auction_history_settles_before_reading_and_reports_both_sides(self):
        source = AUCTION_HISTORY.read_text(encoding="utf-8")
        self.assertIn("auction_module._ensure_reaper()", source)
        self.assertIn("auction_module._settle_ended_auctions()", source)
        self.assertIn('filters.command(["auctionhistory", "auctionlog"])', source)
        self.assertIn('filters.command(["auctionstats", "auctionsummary"])', source)
        self.assertIn('"bidder_ids": user_id', source)
        self.assertIn('"closed_reason"', source)
        self.assertIn('"highest_bidder_id": user_id', source)

    def test_help_back_button_returns_to_help_not_settings(self):
        source = HELP.read_text(encoding="utf-8")
        self.assertIn('callback_data=f"help_prev(0,{int(close)})"', source)
        self.assertNotIn('callback_data="close" if close else "settingsback_helper"', source)

    def test_inline_query_has_no_hotlinked_thumbnails(self):
        self.assertNotIn("te.legra.ph", INLINE_QUERY.read_text(encoding="utf-8"))
        self.assertNotIn("thumb_url=", INLINE_QUERY.read_text(encoding="utf-8"))

    def test_new_commands_are_advertised_in_menus_help_and_docs(self):
        commands = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        private_menu = commands.split("GROUP_COMMANDS", 1)[0]
        group_menu = commands.split("GROUP_COMMANDS", 1)[1].split("ADMIN_COMMANDS", 1)[0]
        help_text = (ROOT / "music" / "AoiMusic" / "plugins" / "waifu_help.py").read_text(encoding="utf-8")
        group_help = (ROOT / "music" / "AoiMusic" / "plugins" / "manage" / "group_utils.py").read_text(encoding="utf-8")
        compatibility = (ROOT / "SUMMON_BOT_COMPATIBILITY.md").read_text(encoding="utf-8")

        for command in ("auctionhistory", "auctionstats", "collectionvalue"):
            self.assertIn(f'("{command}",', private_menu)
            self.assertIn(f'("{command}",', group_menu)
            self.assertIn(f"/{command}", help_text)
            self.assertIn(f"/{command}", compatibility)
        self.assertIn('("ginfo",', group_menu)
        self.assertNotIn('("ginfo",', private_menu)
        self.assertIn("/ginfo", group_help)


if __name__ == "__main__":
    unittest.main()
