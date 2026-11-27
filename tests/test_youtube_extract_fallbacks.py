import ast
import copy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_FILE = ROOT / "music/AoiMusic/platforms/Youtube.py"


def load_extract_helper(fake_ytdl):
    tree = ast.parse(YOUTUBE_FILE.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "extract_info_with_fallback"
    )
    namespace = {
        "copy": copy,
        "get_available_runtimes": lambda: [],
        "_get_youtube_dl": lambda: fake_ytdl,
        "_log": lambda *args, **kwargs: None,
    }
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(YOUTUBE_FILE), "exec"), namespace)
    return namespace["extract_info_with_fallback"]


class YouTubeExtractFallbackTests(unittest.TestCase):
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

    def test_client_fallback_returns_the_effective_options_for_download(self):
        seen_clients = []

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

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
