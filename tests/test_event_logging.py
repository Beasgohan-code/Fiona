import ast
import asyncio
import html
import logging
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOGGER_FILE = ROOT / "waifu/aoiwaifu/unit/event_logger.py"
TREE = ast.parse(EVENT_LOGGER_FILE.read_text(encoding="utf-8"))
NAMESPACE = {"html": html, "logging": logging, "Any": Any}
exec(compile(TREE, str(EVENT_LOGGER_FILE), "exec"), NAMESPACE)


class EventLoggerTests(unittest.TestCase):
    def test_actor_identity_is_html_escaped_and_includes_user_id(self):
        class User:
            id = 73
            first_name = "<Fiona>"
            last_name = "& Bot"
            username = "name_test"

        rendered = NAMESPACE["actor_details"](User())
        self.assertIn("&lt;Fiona&gt; &amp; Bot", rendered)
        self.assertIn("@name_test", rendered)
        self.assertIn("<code>73</code>", rendered)
        self.assertNotIn("<Fiona>", rendered)

    def test_log_sender_normalizes_numeric_chat_ids_and_survives_api_errors(self):
        class Client:
            def __init__(self, fail=False):
                self.fail = fail
                self.sent = []

            async def send_message(self, **kwargs):
                if self.fail:
                    raise RuntimeError("no access")
                self.sent.append(kwargs)

        async def run_checks():
            client = Client()
            self.assertTrue(
                await NAMESPACE["send_event_log"](client, "-100123", "<b>event</b>")
            )
            self.assertEqual(client.sent[0]["chat_id"], -100123)
            self.assertTrue(client.sent[0]["disable_web_page_preview"])
            await NAMESPACE["send_event_logs"](
                client, ["-100123", -100123, "@logchat", "@logchat"], "event"
            )
            self.assertEqual(len(client.sent), 3)
            self.assertEqual(client.sent[1]["chat_id"], -100123)
            self.assertEqual(client.sent[2]["chat_id"], "@logchat")

            failing = Client(fail=True)
            self.assertFalse(
                await NAMESPACE["send_event_log"](failing, "@logchat", "event")
            )
            self.assertFalse(await NAMESPACE["send_event_log"](client, "", "event"))

        asyncio.run(run_checks())

    def test_lifecycle_and_first_user_start_events_are_wired(self):
        merged = (ROOT / "merged.py").read_text(encoding="utf-8")
        music_start = (ROOT / "music/AoiMusic/plugins/bot/start.py").read_text(encoding="utf-8")
        self.assertIn("Fiona started", merged)
        self.assertIn("Fiona stopping", merged)
        self.assertIn("is_first_start = await add_served_user", music_start)
        self.assertIn("New user started Fiona", music_start)

    def test_group_join_and_leave_events_are_logged_once_to_both_configured_loggers(self):
        music_handler = (ROOT / "music/AoiMusic/plugins/misc/bot_add_left.py").read_text(encoding="utf-8")
        waifu_handler = (ROOT / "waifu/aoiwaifu/modules/joinlog.py").read_text(encoding="utf-8")
        self.assertIn("Fiona added to a group", music_handler)
        self.assertIn("Fiona left a group", music_handler)
        merged = (ROOT / "merged.py").read_text(encoding="utf-8")
        self.assertIn("[aoiwaifu.GLOG, config.LOGGER_ID]", merged)
        self.assertIn("GLOG", music_handler)
        self.assertIn("LOGGER_ID", music_handler)
        self.assertIn('"active": False', waifu_handler)
        self.assertNotIn("send_log_message(GLOG", waifu_handler)


if __name__ == "__main__":
    unittest.main()
