import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "music/config/config.py"
PROMPT_IMAGE = ROOT / "music/assets/fiona_play_prompt.jpg"
GLOBAL_STATS_IMAGE = ROOT / "music/assets/fiona_global_stats.jpg"
BOT_STATS_IMAGE = ROOT / "music/assets/fiona_bot_stats.jpg"


class PlayPromptImageTests(unittest.TestCase):
    def test_bare_play_prompt_uses_local_fiona_asset(self):
        self.assertTrue(PROMPT_IMAGE.is_file())
        self.assertGreater(PROMPT_IMAGE.stat().st_size, 10_000)
        source = CONFIG.read_text(encoding="utf-8")
        self.assertIn("_FIONA_PLAY_PROMPT_IMAGE", source)
        self.assertIn('"assets" / "fiona_play_prompt.jpg"', source)
        self.assertIn('PLAYLIST_IMG_URL = getenv("PLAYLIST_IMG_URL", "").strip() or _FIONA_PLAY_PROMPT_IMAGE', source)
        self.assertNotIn("file-00000000fc9c8208a9c65e000748c4d3", source.split("PLAYLIST_IMG_URL", 1)[1].split("\n", 1)[0])

    def test_stats_banners_use_local_fiona_assets(self):
        for image in (GLOBAL_STATS_IMAGE, BOT_STATS_IMAGE):
            self.assertTrue(image.is_file())
            self.assertGreater(image.stat().st_size, 10_000)
        source = CONFIG.read_text(encoding="utf-8")
        self.assertIn('"assets" / "fiona_global_stats.jpg"', source)
        self.assertIn('"assets" / "fiona_bot_stats.jpg"', source)
        self.assertIn('GLOBAL_IMG_URL = getenv("GLOBAL_IMG_URL", "").strip() or _FIONA_GLOBAL_STATS_IMAGE', source)
        self.assertIn('STATS_IMG_URL = getenv("STATS_IMG_URL", "").strip() or _FIONA_BOT_STATS_IMAGE', source)
        self.assertNotIn("file-00000000fc9c8208a9c65e000748c4d3", source)


if __name__ == "__main__":
    unittest.main()
