import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALL = ROOT / "music/AoiMusic/core/call.py"


class AssistantPeerRecoveryTests(unittest.TestCase):
    def test_peer_id_invalid_membership_probe_does_not_abort_playback_join(self):
        source = CALL.read_text(encoding="utf-8")
        self.assertIn("except PeerIdInvalid:", source)
        self.assertIn("continuing with invite flow", source)

    def test_peer_id_invalid_invite_join_retries_with_fresh_non_primary_link(self):
        source = CALL.read_text(encoding="utf-8")
        self.assertIn("except PeerIdInvalid as e:", source)
        self.assertIn("app.create_chat_invite_link(", source)
        self.assertIn('name="Music assistant join"', source)
        self.assertIn("await userbot.join_chat(fresh_link)", source)
        self.assertIn("await app.approve_chat_join_request(chat_id, userbot.id)", source)
        self.assertIn("Telegram could not resolve the assistant peer", source)


if __name__ == "__main__":
    unittest.main()
