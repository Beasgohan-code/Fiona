import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ECONOMY = ROOT / "waifu/aoiwaifu/admin/economy.py"
REMOVEALL = ROOT / "waifu/aoiwaifu/admin/removeall.py"


class OwnerCharacterAdminTests(unittest.TestCase):
    def test_give_requires_owner_reply_and_catalog_character(self):
        source = ECONOMY.read_text(encoding="utf-8")
        self.assertIn('filters.command(["give"])', source)
        self.assertNotIn('filters.command(["give"]) & filters.group', source)
        self.assertIn("message.from_user.id != OWNER_ID", source)
        self.assertIn("message.reply_to_message.from_user", source)
        self.assertIn('collection.find_one(', source)
        self.assertIn('"$push": {"characters": new_copy}', source)
        self.assertIn('await reply_video_panel(message, character["vid_url"]', source)
        self.assertIn('await reply_photo_panel(message, character["img_url"]', source)

    def test_removeall_is_owner_bound_confirmed_and_preserves_profile(self):
        source = REMOVEALL.read_text(encoding="utf-8")
        self.assertIn('filters.command(["removeall"])', source)
        self.assertIn('filters.regex(r"^removeall:(confirm|cancel):', source)
        self.assertIn('callback_query.from_user.id != pending["owner_id"]', source)
        self.assertIn('callback_query.message.chat.id != pending["chat_id"]', source)
        self.assertIn('{"$set": {"characters": []}}', source)
        self.assertIn("coins, tokens, profile", (ROOT / "waifu/aoiwaifu/admin/removeall.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
