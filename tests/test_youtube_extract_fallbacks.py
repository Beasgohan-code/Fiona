import ast
import asyncio
import copy
import os
import time as time_module
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_FILE = ROOT / "music/AoiMusic/platforms/Youtube.py"
STREAM_FILE = ROOT / "music/AoiMusic/utils/stream/stream.py"


def load_extract_helper(fake_ytdl, runtimes=None, clock=None):
    tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "extract_info_with_fallback"
    )
    bounded_options = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_bounded_youtube_probe_options"
    )
    namespace = {
        "copy": copy,
        "get_available_runtimes": lambda: list(runtimes or []),
        "_get_youtube_dl": lambda: fake_ytdl,
        "_log": lambda *args, **kwargs: None,
        "_YT_EXTRACT_TOTAL_BUDGET": 60,
        "time": clock or time_module,
    }
    exec(compile(ast.Module(body=[bounded_options, helper], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)
    return namespace["extract_info_with_fallback"]


class YouTubeExtractFallbackTests(unittest.TestCase):
    def _load_track_method(self, videos_search):
        tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
        youtube_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTube"
        )
        method = next(
            node for node in youtube_class.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "track"
        )
        method.decorator_list = []
        namespace = {
            "asyncio": asyncio,
            "time": time_module,
            "VideosSearch": videos_search,
            "_query_variants": lambda query: [query, "trimmed query"],
            "_YT_SEARCH_TIMEOUT": 8,
            "_YT_SEARCH_TOTAL_BUDGET": 30,
            "_log": lambda *args, **kwargs: None,
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)
        return namespace["track"]

    def test_youtube_search_hits_direct_query_before_optional_media_api(self):
        calls = []

        class Search:
            async def next(self):
                return {"result": [{
                    "title": "Direct match", "duration": "03:20", "id": "abc123",
                    "link": "https://youtu.be/abc123",
                    "thumbnails": [{"url": "https://img.example/abc.jpg?size=1"}],
                    "channel": {"name": "Artist"},
                }]}

        def videos_search(query, **kwargs):
            calls.append(query)
            return Search()

        class Resolver:
            async def _api_search(self, query, started):
                raise AssertionError("media API must not delay a direct YouTube hit")

        result = asyncio.run(self._load_track_method(videos_search)(Resolver(), "direct query"))
        self.assertEqual(calls, ["direct query"])
        self.assertEqual(result[0]["vidid"], "abc123")

    def test_media_api_remains_fallback_after_direct_youtube_miss(self):
        calls = []

        class Search:
            async def next(self):
                return {"result": []}

        def videos_search(query, **kwargs):
            calls.append(query)
            return Search()

        expected = ({"title": "API result", "vidid": "api123"}, "api123")

        class Resolver:
            async def _api_search(self, query, started):
                self.api_query = query
                return expected

        resolver = Resolver()
        result = asyncio.run(self._load_track_method(videos_search)(resolver, "direct query"))
        self.assertEqual(result, expected)
        self.assertEqual(resolver.api_query, "direct query")
        self.assertEqual(calls, ["direct query"])

    def test_group_play_search_cards_embed_the_resolved_track_thumbnail(self):
        inline_path = ROOT / "music/AoiMusic/utils/inline/play.py"
        tree = ast.parse(inline_path.read_text(encoding="utf-8"))
        card = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "play_card_html"
        )
        namespace = {
            "rich_img": lambda url: f'<img src="{url}"/>' if url else "",
            "rich_heading": lambda text, **kwargs: f"<heading>{text}</heading>",
            "rich_md": lambda text: text,
            "pemoji": lambda emoji: emoji,
        }
        exec(compile(ast.Module(body=[card], type_ignores=[]), str(inline_path), "exec"), namespace)
        html = namespace["play_card_html"](
            {}, "Track title", "<buttons/>", thumbnail="https://img.example/current-track.jpg"
        )
        self.assertIn('<img src="https://img.example/current-track.jpg"/>', html)
        self.assertIn("Track title", html)
        self.assertTrue(html.endswith("<buttons/>"))

        handler_tree = ast.parse((ROOT / "music/AoiMusic/plugins/play/play.py").read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(handler_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "play_card_html"
        ]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(any(keyword.arg == "thumbnail" for keyword in call.keywords) for call in calls))

    def test_media_api_remains_fallback_after_direct_youtube_search_error(self):
        calls = []

        class Search:
            async def next(self):
                raise RuntimeError("temporary YouTube search failure")

        def videos_search(query, **kwargs):
            calls.append(query)
            return Search()

        expected = ({"title": "API result", "vidid": "api456"}, "api456")

        class Resolver:
            async def _api_search(self, query, started):
                return expected

        result = asyncio.run(self._load_track_method(videos_search)(Resolver(), "direct query"))
        self.assertEqual(result, expected)
        self.assertEqual(calls, ["direct query"])

    def test_search_trim_ladder_is_bounded_to_four_queries(self):
        tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_query_variants"
        )
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)
        query = "one two three four five six seven eight nine ten eleven"
        variants = namespace["_query_variants"](query)
        self.assertEqual(variants[0], query)
        self.assertLessEqual(len(variants), 4)
        self.assertTrue(all(isinstance(variant, str) and variant for variant in variants))

    def test_shizumusic_api_environment_names_are_accepted_without_hardcoding_keys(self):
        config_path = ROOT / "music/config/config.py"
        tree = ast.parse(config_path.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_first_nonempty_env"
        )
        env = {"API_BASE": "https://api.example.test", "API_KEY": "rotated-test-key"}
        namespace = {"getenv": lambda name, default="": env.get(name, default)}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(config_path), "exec"), namespace)
        first_env = namespace["_first_nonempty_env"]

        self.assertEqual(first_env("SHIZUMUSIC_API_URL", "API_URL", "API_BASE"), "https://api.example.test")
        self.assertEqual(first_env("SHIZUMUSIC_API_KEY", "API_KEY", "YT_API_KEY"), "rotated-test-key")
        self.assertEqual(first_env("MEDIA_API_URL", "MEDIA_API_BASE", default="fallback"), "fallback")
        env["SHIZUMUSIC_API_KEY"] = "preferred-key"
        self.assertEqual(first_env("SHIZUMUSIC_API_KEY", "API_KEY"), "preferred-key")
        self.assertNotIn("rotated-test-key", config_path.read_text(encoding="utf-8"))
        self.assertIn('f"{api_base}/download"', (ROOT / "music/AoiMusic/platforms/Youtube.py").read_text(encoding="utf-8"))
        self.assertIn('"api_key": api_key', (ROOT / "music/AoiMusic/platforms/Youtube.py").read_text(encoding="utf-8"))

    def test_slow_media_operation_updates_status_instead_of_staying_on_searching(self):
        tree = ast.parse(STREAM_FILE.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_await_with_progress"
        )
        statuses = []

        async def update_status(mystic, text):
            statuses.append(text)

        namespace = {"asyncio": asyncio, "_time": __import__("time"), "_update_play_status": update_status}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(STREAM_FILE), "exec"), namespace)

        async def slow_operation():
            await asyncio.sleep(0.04)
            return "ready"

        result = asyncio.run(namespace["_await_with_progress"](slow_operation(), object(), "Resolving source", interval=0.005))
        self.assertEqual(result, "ready")
        self.assertTrue(statuses)
        self.assertIn("Resolving source", statuses[0])
        self.assertIn("s)", statuses[0])

    def test_shizumusic_api_download_streams_from_get_download_contract(self):
        tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
        youtube_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "YouTube")
        method = next(
            node for node in youtube_class.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_shizumusic_api_download"
        )
        requests = []
        logs = []

        class FakeContent:
            async def iter_chunked(self, size):
                yield b"M" * 12000

        class FakeResponse:
            status = 200
            content_type = "audio/mpeg"
            content = FakeContent()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class FakeSession:
            def get(self, url, **kwargs):
                requests.append((url, kwargs))
                return FakeResponse()

        class FakeDownloader:
            _download_locks = {}

            async def _get_http_session(self):
                return FakeSession()

        namespace = {
            "aiohttp": types.SimpleNamespace(ClientTimeout=lambda **kwargs: kwargs),
            "asyncio": asyncio,
            "config": types.SimpleNamespace(
                SHIZUMUSIC_API_URL="https://shizu.example.test/",
                SHIZUMUSIC_API_KEY="private-key",
            ),
            "os": os,
            "_log": lambda *args, **kwargs: logs.append(args),
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)

        import tempfile
        previous_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                path = asyncio.run(namespace["_shizumusic_api_download"](FakeDownloader(), "vid123", "audio"))
                self.assertEqual(path, os.path.join("downloads", "shizumusic", "vid123.mp3"))
                self.assertEqual(os.path.getsize(path), 12000)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(requests[0][0], "https://shizu.example.test/download")
        self.assertEqual(
            requests[0][1]["params"],
            {"url": "vid123", "type": "audio", "api_key": "private-key"},
        )
        self.assertNotIn("private-key", repr(logs))

    def test_shizumusic_configured_playback_uses_its_local_download_first(self):
        tree = ast.parse(STREAM_FILE.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "play_youtube_source"
        )
        attempted = []

        class FakeYoutube:
            async def _api_download(self, vidid, media_type):
                attempted.append(("download", vidid, media_type))
                return "downloads/shizumusic/vid123.mp3"

            def invalidate_media_url(self, *args):
                attempted.append(("invalidate", args))

            async def stream_url(self, *args, **kwargs):
                attempted.append(("yt-dlp-stream", args, kwargs))
                return 0, None

        class FakeLogger:
            def warning(self, *args, **kwargs):
                pass

        async def fake_play(path):
            attempted.append(("play", path))

        async def update_status(mystic, text):
            pass

        async def passthrough(awaitable, mystic, label):
            return await awaitable

        config = types.SimpleNamespace(
            MEDIA_API_URL="", MEDIA_API_KEY="",
            SHIZUMUSIC_API_URL="https://shizu.example.test",
            SHIZUMUSIC_API_KEY="private-key",
        )
        namespace = {
            "config": config,
            "Platform": types.SimpleNamespace(youtube=FakeYoutube()),
            "MEDIA_ERRORS": (RuntimeError,),
            "aiohttp": types.SimpleNamespace(ClientError=RuntimeError),
            "slog": FakeLogger(),
            "_update_play_status": update_status,
            "_await_with_progress": passthrough,
            "_api_stream_url": lambda *args: None,
            "_youtube_download_error_hint": str,
            "AssistantErr": RuntimeError,
            "os": os,
            "_STREAM_LOG": "Stream",
        }
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(STREAM_FILE), "exec"), namespace)
        result = asyncio.run(namespace["play_youtube_source"]("vid123", False, object(), fake_play))

        self.assertEqual(result, "downloads/shizumusic/vid123.mp3")
        self.assertIn(("download", "vid123", "audio"), attempted)
        self.assertIn(("play", "downloads/shizumusic/vid123.mp3"), attempted)
        self.assertFalse(any(item[0] == "yt-dlp-stream" for item in attempted))

    def test_audio_playback_uses_media_api_permalink_before_ytdlp(self):
        tree = ast.parse(STREAM_FILE.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "play_youtube_source"
        )
        attempted = []
        statuses = []

        class FakeYoutube:
            async def _api_download(self, vidid, media_type):
                attempted.append(("download", vidid, media_type))
                return None

            async def stream_url(self, *args, **kwargs):
                attempted.append(("yt-dlp", args, kwargs))
                return 0, None

            def invalidate_media_url(self, *args):
                attempted.append(("invalidate", args))

        class FakeLogger:
            def warning(self, *args, **kwargs):
                pass

            def info(self, *args, **kwargs):
                pass

        async def api_stream(vidid, video):
            attempted.append(("api-stream", vidid, video))
            return "https://cdn.example.test/audio.mp3"

        async def fake_play(url):
            attempted.append(("play", url))

        class FakeMystic:
            async def edit_text(self, text):
                statuses.append(text)
                return True

        async def update_status(mystic, text):
            if mystic:
                await mystic.edit_text(text)

        namespace = {
            "config": types.SimpleNamespace(
                MEDIA_API_URL="https://media.example.test",
                MEDIA_API_KEY="configured",
                SHIZUMUSIC_API_URL="",
                SHIZUMUSIC_API_KEY="",
            ),
            "Platform": types.SimpleNamespace(youtube=FakeYoutube()),
            "MEDIA_ERRORS": (RuntimeError,),
            "aiohttp": types.SimpleNamespace(ClientError=RuntimeError),
            "slog": FakeLogger(),
            "_update_play_status": update_status,
            "_await_with_progress": lambda awaitable, mystic, label: awaitable,
            "_api_stream_url": api_stream,
            "_youtube_download_error_hint": str,
            "AssistantErr": RuntimeError,
            "os": os,
            "_STREAM_LOG": "Stream",
        }
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(STREAM_FILE), "exec"), namespace)
        result = asyncio.run(namespace["play_youtube_source"]("vid123", False, FakeMystic(), fake_play))

        self.assertEqual(result, "https://cdn.example.test/audio.mp3")
        self.assertTrue(any("best source for your track" in status for status in statuses))
        self.assertTrue(any("direct stream" in status for status in statuses))
        self.assertIn(("api-stream", "vid123", False), attempted)
        self.assertIn(("play", "https://cdn.example.test/audio.mp3"), attempted)
        self.assertFalse(any(item[0] == "yt-dlp" for item in attempted))

    def test_media_api_accepts_stream_url_and_legacy_url_fields(self):
        tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_media_api_stream_url"
        )
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)
        get_stream_url = namespace["_media_api_stream_url"]

        self.assertEqual(get_stream_url({"ok": True, "stream_url": "https://cdn.test/a"}), "https://cdn.test/a")
        self.assertEqual(get_stream_url({"ok": True, "url": "https://cdn.test/b"}), "https://cdn.test/b")
        with self.assertRaisesRegex(RuntimeError, "quota exhausted"):
            get_stream_url({"ok": False, "error": "quota exhausted"})
        with self.assertRaisesRegex(RuntimeError, "did not include"):
            get_stream_url({"ok": True})

    def test_youtube_extractor_pin_includes_current_client_policy_fixes(self):
        source = YOUTUBE_FILE.read_text(encoding="utf-8")
        requirements = (ROOT / "requirements/merged.txt").read_text(encoding="utf-8")
        self.assertIn("yt-dlp==2026.11.23", requirements)
        self.assertIn("nodejs-wheel==22.20.0", requirements)
        self.assertIn('_YT_CLIENTS = ["tv", "mweb", "web", "ios_producer", "tv_samsung"]', source)
        self.assertIn('("tv_samsung", "ios_producer", "android", "ios", "tv", "web_embedded")', source)
        audio_clients = source.split('ydl_optssx["extractor_args"]["youtube"]["player_client"] = [', 1)[1].split("]", 1)[0]
        self.assertLess(audio_clients.index('"ios_producer"'), audio_clients.index('"web_embedded"'))

    def test_download_methods_reuse_extraction_options(self):
        tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
        youtube_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTube"
        )
        download_method = next(
            node
            for node in youtube_class.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "download"
        )
        nested_downloads = [
            node
            for node in ast.walk(download_method)
            if isinstance(node, ast.FunctionDef)
            and node.name in {"audio_dl", "video_dl", "song_video_dl", "song_audio_dl"}
        ]
        self.assertEqual(len(nested_downloads), 4)
        for method in nested_downloads:
            source = ast.get_source_segment(YOUTUBE_FILE.read_text(encoding="utf-8"), method)
            self.assertIn("return_options=True", source, method.name)
            self.assertIn("_get_youtube_dl()(download_opts)", source, method.name)

    def test_runtime_fallback_uses_ytdlp_option_shape_without_duplicate_probe(self):
        seen_runtimes = []

        class RuntimeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, link, download=False):
                runtime = self.options.get("js_runtimes")
                seen_runtimes.append(runtime)
                if runtime == {"bun": {}}:
                    return {"id": "runtime123", "ext": "m4a"}
                raise Exception("runtime did not solve the YouTube challenge")

        helper = load_extract_helper(RuntimeYoutubeDL, runtimes=["node", "bun"])
        info, chosen = helper(
            "https://youtube.com/watch?v=runtime123",
            {
                "format": "bestaudio/best",
                "js_runtimes": {"node": {}},
                "extractor_args": {"youtube": {"player_client": ["tv_samsung"]}},
            },
            return_options=True,
        )

        self.assertEqual(info["id"], "runtime123")
        self.assertEqual(chosen["js_runtimes"], {"bun": {}})
        self.assertEqual(seen_runtimes, [{"node": {}}, {"bun": {}}])

    def test_client_fallback_returns_the_effective_options_for_download(self):
        seen_clients = []
        seen_options = []

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options
                seen_options.append(copy.deepcopy(options))

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, link, download=False):
                self.assert_download_false(download)
                clients = self.options["extractor_args"]["youtube"]["player_client"]
                seen_clients.append(tuple(clients))
                if clients == ["tv_samsung"]:
                    return {"id": "test123", "ext": "m4a"}
                raise Exception("Requested format is not available")

            @staticmethod
            def assert_download_false(download):
                if download is not False:
                    raise AssertionError("fallback probing must not download yet")

        helper = load_extract_helper(FakeYoutubeDL)
        original = {
            "format": "bestaudio/best/18/worst",
            "extractor_args": {"youtube": {"player_client": ["web_embedded", "tv"]}},
        }
        info, chosen = helper("https://youtube.com/watch?v=test123", original, return_options=True)

        self.assertEqual(info["id"], "test123")
        self.assertEqual(chosen["extractor_args"]["youtube"]["player_client"], ["tv_samsung"])
        self.assertEqual(chosen["extractor_retries"], 1)
        self.assertEqual(chosen["socket_timeout"], 12)
        self.assertIn(("tv_samsung",), seen_clients)
        self.assertEqual(original["extractor_args"]["youtube"]["player_client"], ["web_embedded", "tv"])

    def test_raw_format_probe_recovers_exact_audio_format_after_selector_failures(self):
        seen_clients = []

        class RawFormatsYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, link, download=False, process=True):
                if process:
                    raise Exception("Requested format is not available")
                clients = self.options["extractor_args"]["youtube"]["player_client"]
                seen_clients.extend(clients)
                return {
                    "id": "test123",
                    "formats": [
                        {"format_id": "140", "ext": "m4a", "acodec": "mp4a.40.2", "vcodec": "none", "abr": 128}
                    ],
                }

        helper = load_extract_helper(RawFormatsYoutubeDL)
        info, chosen = helper(
            "https://youtube.com/watch?v=test123",
            {"format": "bestaudio/best", "extractor_args": {"youtube": {"player_client": ["web", "tv"]}}},
            return_options=True,
        )

        self.assertEqual(info["ext"], "m4a")
        self.assertEqual(chosen["format"], "140")
        self.assertIn("web", seen_clients)
        self.assertEqual(chosen["extractor_args"]["youtube"]["player_client"], ["web"])

    def test_raw_video_probe_builds_a_downloadable_video_audio_pair(self):
        class RawVideoYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, link, download=False, process=True):
                if process:
                    raise Exception("Requested format is not available")
                return {
                    "id": "video123",
                    "formats": [
                        {"format_id": "v720", "ext": "webm", "acodec": "none", "vcodec": "vp9", "height": 720},
                        {"format_id": "a128", "ext": "m4a", "acodec": "aac", "vcodec": "none", "abr": 128},
                    ],
                }

        helper = load_extract_helper(RawVideoYoutubeDL)
        info, chosen = helper(
            "https://youtube.com/watch?v=video123",
            {
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "extractor_args": {"youtube": {"player_client": ["web_embedded"]}},
            },
            return_options=True,
        )

        self.assertEqual(chosen["format"], "v720+a128")
        self.assertEqual(info["ext"], "mp4")

    def test_fallback_ladder_stops_at_total_budget_instead_of_waiting_over_two_minutes(self):
        class FakeClock:
            now = 0

            def monotonic(self):
                return self.now

        clock = FakeClock()
        seen_options = []

        class SlowFailYoutubeDL:
            def __init__(self, options):
                self.options = options
                seen_options.append(copy.deepcopy(options))

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, link, download=False, process=True):
                clock.now += 20
                raise Exception("Requested format is not available")

        helper = load_extract_helper(SlowFailYoutubeDL, clock=clock)
        with self.assertRaisesRegex(Exception, "overall extraction budget"):
            helper("https://youtube.com/watch?v=slow123", {"format": "bestaudio/best"})

        self.assertEqual(len(seen_options), 3)
        self.assertEqual(seen_options[0]["extractor_retries"], 2)
        self.assertEqual(seen_options[1]["extractor_retries"], 1)
        self.assertEqual(seen_options[0]["socket_timeout"], 12)

    def test_fallback_failure_reports_each_last_client_attempt(self):
        class AlwaysFailYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self, link, download=False):
                raise Exception("Requested format is not available")

        helper = load_extract_helper(AlwaysFailYoutubeDL)
        with self.assertRaisesRegex(Exception, "client-tv: Requested format is not available"):
            helper("https://youtube.com/watch?v=test123", {"extractor_args": {"youtube": {}}})


if __name__ == "__main__":
    unittest.main()
