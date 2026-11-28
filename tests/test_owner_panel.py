import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / "waifu/aoiwaifu/modules/owner.py"


class OwnerPanelTests(unittest.TestCase):
    def test_panel_is_private_owner_gated_and_uses_shared_richgram_ui(self):
        source = OWNER.read_text(encoding="utf-8")
        self.assertIn('filters.command(["owner", "panel"]) & filters.private', source)
        self.assertIn("message.from_user.id != OWNER_ID", source)
        self.assertIn("callback_query.from_user.id != OWNER_ID", source)
        self.assertIn("premium_button(", source)
        self.assertIn("reply_panel(", source)
        self.assertIn("edit_panel(", source)

    def test_panel_covers_common_owner_workflows(self):
        source = OWNER.read_text(encoding="utf-8")
        for page in ("characters", "economy", "spawning", "safety"):
            self.assertIn(f'"{page}": (', source)
            self.assertIn(f'callback_data="ownerpanel:{page}"', source)
        for command in ("/give", "/givemoney", "/chance", "/setclaim", "/removeall"):
            self.assertIn(command, source)


if __name__ == "__main__":
    unittest.main()
