import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
MEDIA_STORE = ROOT / "music" / "AoiMusic" / "utils" / "media_store.py"


class FakeMedia:
    def __init__(self, file_id, file_name="cached.mp3"):
        self.file_id = file_id
        self.file_name = file_name


class FakeMessage:
    def __init__(self, caption, file_id="file-id-1", file_name="cached.mp3"):
        self.caption = caption
        self.audio = FakeMedia(file_id, file_name)


class FakeApp:
    def __init__(self, search_messages=None):
        self.search_messages = search_messages or (lambda *args, **kwargs: [])
        self.sent_audio = []
        self.download_paths = []

    async def send_audio(self, chat_id, file_path, caption=""):
        self.sent_audio.append((chat_id, file_path, caption))
        return True

    async def download_media(self, file_id, file_name=None):
        path = Path(file_name)
        path.write_bytes(b"cached-audio")
        self.download_paths.append((file_id, str(path)))
        return str(path)


def _load_media_store(app):
    config = types.SimpleNamespace(STORE_ID=-1001234567890, STORE_MAX_MB=1)
    aoi_music = types.ModuleType("AoiMusic")
    aoi_music.app = app
    config_module = types.ModuleType("config")
    config_module.STORE_ID = config.STORE_ID
    config_module.STORE_MAX_MB = config.STORE_MAX_MB
    previous = {name: sys.modules.get(name) for name in ("config", "AoiMusic")}
    sys.modules["config"] = config_module
    sys.modules["AoiMusic"] = aoi_music
    try:
        spec = importlib.util.spec_from_file_location("fiona_media_store_test", MEDIA_STORE)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        module.config = config_module
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class MediaStoreCacheTests(unittest.TestCase):
    def test_store_helpers_sanitize_and_use_exact_marker(self):
        app = FakeApp()
        module = _load_media_store(app)
        self.assertEqual(module._video_id("abc def:/../xyz"), "abcdefxyz")
        caption = module._caption("abc123", "Song\nName")
        self.assertIn("#FionaMediaCache", caption)
        self.assertIn("video_id=abc123", caption)
        self.assertIn("title=Song Name", caption)
        self.assertNotIn("\x00", caption)

    def test_search_requires_store_marker_and_video_id(self):
        matching = FakeMessage("#FionaMediaCache\nvideo_id=abc123\ntitle=A song", "file-123", "a.mp3")
        wrong = FakeMessage("#FionaMediaCache\nvideo_id=other\ntitle=Wrong", "file-999", "wrong.mp3")
        app = FakeApp(lambda *args, **kwargs: [wrong, matching])
        module = _load_media_store(app)
        result = asyncio.run(module.find_cached_audio("abc123"))
        self.assertEqual(result, ("file-123", "a.mp3"))

    def test_download_writes_cached_audio(self):
        message = FakeMessage("#FionaMediaCache\nvideo_id=abc123", "file-123", "a.m4a")
        app = FakeApp(lambda *args, **kwargs: [message])
        module = _load_media_store(app)
        with TemporaryDirectory() as tmp:
            result = asyncio.run(module.download_cached_audio("abc123", tmp))
            self.assertTrue(Path(result).is_file())
            self.assertEqual(Path(result).read_bytes(), b"cached-audio")
            self.assertEqual(app.download_paths[0][0], "file-123")

    def test_store_audio_sends_searchable_caption_and_respects_size_cap(self):
        message = FakeMessage("#FionaMediaCache\nvideo_id=abc123", "file-123", "a.mp3")
        app = FakeApp(lambda *args, **kwargs: [])
        module = _load_media_store(app)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.mp3"
            path.write_bytes(b"audio-data")
            self.assertTrue(asyncio.run(module.store_audio("abc123", path, "Track title")))
            self.assertEqual(app.sent_audio[0][0], -1001234567890)
            self.assertIn("video_id=abc123", app.sent_audio[0][2])
            path.write_bytes(b"x" * (1024 * 1024 + 1))
            self.assertFalse(asyncio.run(module.store_audio("abc123", path, "Too big")))

    def test_store_audio_does_not_duplicate_existing_cache(self):
        message = FakeMessage("#FionaMediaCache\nvideo_id=abc123", "file-123", "a.mp3")
        app = FakeApp(lambda *args, **kwargs: [message])
        module = _load_media_store(app)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.mp3"
            path.write_bytes(b"audio-data")
            self.assertTrue(asyncio.run(module.store_audio("abc123", path, "Track")))
            self.assertEqual(app.sent_audio, [])

    def test_assistant_search_is_used_when_bot_search_fails(self):
        class FailingSearchApp(FakeApp):
            def __init__(self):
                self.sent_audio = []
                self.download_paths = []

            def search_messages(self, *args, **kwargs):
                raise RuntimeError("bot search unsupported")

        class FakeAssistant:
            def __init__(self):
                self.downloaded = []

            def search_messages(self, *args, **kwargs):
                return [FakeMessage("#FionaMediaCache\nvideo_id=abc123", "assistant-file", "a.mp3")]

            async def download_media(self, file_id, file_name=None):
                self.downloaded.append((file_id, file_name))
                path = Path(file_name)
                path.write_bytes(b"assistant-audio")
                return str(path)

        assistant = FakeAssistant()
        app = FailingSearchApp()
        module = _load_media_store(app)
        module._assistant_client = lambda: assistant
        with TemporaryDirectory() as tmp:
            result = asyncio.run(module.download_cached_audio("abc123", tmp))
            self.assertTrue(Path(result).is_file())
            self.assertEqual(Path(result).read_bytes(), b"assistant-audio")
            self.assertEqual(assistant.downloaded[0][0], "assistant-file")

    def test_assistant_cache_prevents_duplicate_upload(self):
        class FailingSearchApp(FakeApp):
            def __init__(self):
                self.sent_audio = []
                self.download_paths = []

            def search_messages(self, *args, **kwargs):
                raise RuntimeError("bot search unsupported")

        class FakeAssistant:
            def search_messages(self, *args, **kwargs):
                return [FakeMessage("#FionaMediaCache\nvideo_id=abc123", "assistant-file", "a.mp3")]

        app = FailingSearchApp()
        module = _load_media_store(app)
        module._assistant_client = lambda: FakeAssistant()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.mp3"
            path.write_bytes(b"audio-data")
            self.assertTrue(asyncio.run(module.store_audio("abc123", path, "Track")))
            self.assertEqual(app.sent_audio, [])

    def test_store_implementation_is_mongo_free(self):
        source = MEDIA_STORE.read_text(encoding="utf-8")
        self.assertIn("send_audio", source)
        self.assertIn("search_messages", source)
        self.assertIn("download_media", source)
        lowered = source.lower()
        self.assertNotIn("motor.", lowered)
        self.assertNotIn("pymongo", lowered)
        self.assertNotIn("mongodb.uri", lowered)
        self.assertNotIn("collection", lowered)

    def test_stream_checks_store_before_providers_and_schedules_upload(self):
        source = (ROOT / "music" / "AoiMusic" / "utils" / "stream" / "stream.py").read_text(encoding="utf-8")
        self.assertIn("download_cached_audio(vidid)", source)
        self.assertIn("schedule_store_audio(vidid, api_path", source)
        self.assertIn("schedule_store_audio(vidid, path", source)
        self.assertIn("if not video:", source)


if __name__ == "__main__":
    unittest.main()
