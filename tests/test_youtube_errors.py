import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STREAM_FILE = ROOT / "music/AoiMusic/utils/stream/stream.py"


def load_error_hint():
    tree = ast.parse(STREAM_FILE.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_youtube_download_error_hint"
    )
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(STREAM_FILE), "exec"), namespace)
    return namespace["_youtube_download_error_hint"]


HINT = load_error_hint()


class YouTubeDownloadErrorTests(unittest.TestCase):
    def test_sign_in_error_points_to_render_cookie_secret(self):
        hint = HINT(Exception("Sign in to confirm you're not a bot"))
        self.assertIn("Render cookies Secret File", hint)

    def test_unavailable_video_is_not_misdiagnosed_as_cookie_problem(self):
        hint = HINT(Exception("Video unavailable"))
        self.assertIn("unavailable to Fiona", hint)
        self.assertNotIn("cookie", hint.lower())

    def test_missing_format_suggests_track_availability_not_cookie_refresh(self):
        hint = HINT(Exception("Requested format is not available"))
        self.assertIn("no compatible format", hint)
        self.assertNotIn("cookie", hint.lower())

    def test_unknown_errors_point_to_render_logs(self):
        hint = HINT(Exception("All extractor clients failed"))
        self.assertIn("Render logs", hint)


if __name__ == "__main__":
    unittest.main()
