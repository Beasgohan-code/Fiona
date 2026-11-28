import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "music/config/config.py"
PROMPT_IMAGE = ROOT / "music/assets/fiona_play_prompt.jpg"
GLOBAL_STATS_IMAGE = ROOT / "music/assets/fiona_global_stats.jpg"
BOT_STATS_IMAGE = ROOT / "music/assets/fiona_bot_stats.jpg"
SOURCE_IMAGES = {
    "fiona_source_audio.jpg": ("TELEGRAM_AUDIO_URL", "SOUNDCLOUD_IMG_URL"),
    "fiona_source_video.jpg": ("TELEGRAM_VIDEO_URL", "YOUTUBE_IMG_URL"),
    "fiona_source_stream.jpg": ("STREAM_IMG_URL",),
    "fiona_source_spotify.jpg": ("SPOTIFY_ARTIST_IMG_URL", "SPOTIFY_ALBUM_IMG_URL", "SPOTIFY_PLAYLIST_IMG_URL"),
}
SONGS = ROOT / "music/AoiMusic/plugins/tools/songs.py"


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

    def test_service_source_banners_use_local_fiona_assets(self):
        source = CONFIG.read_text(encoding="utf-8")
        for filename, settings in SOURCE_IMAGES.items():
            image = ROOT / "music/assets" / filename
            self.assertTrue(image.is_file())
            self.assertGreater(image.stat().st_size, 10_000)
            self.assertIn(f'"assets" / "{filename}"', source)
            for setting in settings:
                marker = f'{setting} = getenv("{setting}", "").strip() or'
                self.assertIn(marker, source)
        self.assertNotIn("te.legra.ph/file/", source)

    def test_song_fallback_thumbnail_uses_local_fiona_asset(self):
        source = SONGS.read_text(encoding="utf-8")
        self.assertIn('"assets" / "fiona_source_audio.jpg"', source)
        self.assertNotIn("i.ibb.co/7zYzRJw", source)


if __name__ == "__main__":
    unittest.main()
