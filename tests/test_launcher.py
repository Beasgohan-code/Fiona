import tempfile
import unittest
from pathlib import Path

from launcher import _read_env_file, environment_errors, normalize_environment


class LauncherEnvironmentTests(unittest.TestCase):
    def test_env_file_parser_handles_comments_quotes_and_equals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# comment\nBOT_MODE=music\nTOKEN='a=b'\nEMPTY=\n", encoding="utf-8")
            self.assertEqual(_read_env_file(path), {"BOT_MODE": "music", "TOKEN": "a=b", "EMPTY": ""})

    def test_shared_names_are_normalized_for_one_bot(self):
        common = {
            "API_ID": "12345",
            "API_HASH": "hash",
            "BOT_TOKEN": "token",
            "MONGO_DB_URI": "mongodb://localhost/db",
            "OWNER_ID": "123456",
            "STRING_SESSIONS": "session",
        }
        for mode in ("merged",):
            env = normalize_environment(mode, common)
            self.assertEqual(env["TOKEN"], "token")
            self.assertEqual(env["BOT_TOKEN"], "token")
            self.assertEqual(env["MONGO_URL"], "mongodb://localhost/db")
            self.assertEqual(env["MONGO_DB_URI"], "mongodb://localhost/db")
            self.assertEqual(environment_errors(mode, env), [])

    def test_legacy_alias_beats_unedited_template_placeholder(self):
        env = normalize_environment(
            "merged",
            {
                "API_ID": "12345",
                "API_HASH": "hash",
                "BOT_TOKEN": "your_bot_token_here",
                "TOKEN": "real-token",
                "MONGO_DB_URI": "mongodb+srv://username:password@cluster.mongodb.net/db",
                "MONGO_URL": "mongodb://localhost/db",
                "OWNER_ID": "123456",
            },
        )
        self.assertEqual(env["BOT_TOKEN"], "real-token")
        self.assertEqual(env["MONGO_DB_URI"], "mongodb://localhost/db")

    def test_legacy_names_are_accepted(self):
        env = normalize_environment(
            "merged",
            {
                "API_ID": "12345",
                "API_HASH": "hash",
                "TOKEN": "legacy-token",
                "MONGO_URL": "mongodb://localhost/db",
                "OWNER_ID": "123456",
                "STRING_SESSION2": "legacy-session",
            },
        )
        self.assertEqual(env["BOT_TOKEN"], "legacy-token")
        self.assertEqual(env["MONGO_DB_URI"], "mongodb://localhost/db")
        self.assertEqual(environment_errors("merged", env), [])

    def test_merged_requires_assistant_session(self):
        env = normalize_environment(
            "merged",
            {
                "API_ID": "12345",
                "API_HASH": "hash",
                "BOT_TOKEN": "token",
                "MONGO_DB_URI": "mongodb://localhost/db",
                "OWNER_ID": "123456",
            },
        )
        self.assertIn("STRING_SESSIONS is required for voice-chat playback in the merged bot", environment_errors("merged", env))

    def test_legacy_numbered_assistant_session_is_accepted(self):
        env = normalize_environment(
            "merged",
            {
                "API_ID": "12345",
                "API_HASH": "hash",
                "BOT_TOKEN": "token",
                "MONGO_DB_URI": "mongodb://localhost/db",
                "OWNER_ID": "123456",
                "STRING_SESSION2": "legacy-session",
            },
        )
        self.assertEqual(environment_errors("merged", env), [])

    def test_invalid_api_id_is_reported(self):
        env = normalize_environment(
            "merged",
            {"API_ID": "not-a-number", "API_HASH": "hash", "TOKEN": "token", "MONGO_URL": "db", "OWNER_ID": "123456"},
        )
        self.assertIn("API_ID must be a positive integer", environment_errors("merged", env))


if __name__ == "__main__":
    unittest.main()
