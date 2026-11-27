import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import keep_alive


class KeepAliveTests(unittest.TestCase):
    def test_health_endpoint_tracks_readiness(self):
        server = keep_alive.start_server(host="127.0.0.1", port=0)
        url = f"http://127.0.0.1:{server.server_address[1]}/health"
        try:
            with self.assertRaises(HTTPError) as response:
                urlopen(url, timeout=2)
            self.assertEqual(response.exception.code, 503)

            keep_alive.beat()
            keep_alive.set_ready(True)
            with urlopen(url, timeout=2) as response:
                self.assertEqual(response.status, 200)
                payload = json.load(response)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "ok")

            keep_alive.set_ready(False)
            with self.assertRaises(HTTPError) as response:
                urlopen(url, timeout=2)
            self.assertEqual(response.exception.code, 503)
        finally:
            keep_alive.stop_server(server)

    def test_live_endpoint_is_separate_from_readiness_and_head_is_supported(self):
        server = keep_alive.start_server(host="127.0.0.1", port=0)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base_url}/live", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(json.load(response)["ok"])

            with self.assertRaises(HTTPError) as response:
                urlopen(f"{base_url}/ready", timeout=2)
            self.assertEqual(response.exception.code, 503)

            request = Request(f"{base_url}/health", method="HEAD")
            with self.assertRaises(HTTPError) as response:
                urlopen(request, timeout=2)
            self.assertEqual(response.exception.code, 503)
            self.assertGreater(int(response.exception.headers["Content-Length"]), 0)
            self.assertEqual(response.exception.read(), b"")

            with urlopen(base_url, timeout=2) as response:
                self.assertEqual(response.read(), b"Fiona is running\n")
        finally:
            keep_alive.stop_server(server)

    def test_merged_bot_uses_music_health_module(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        implementation = root / "music/AoiMusic/core/keep_alive.py"
        merged = (root / "merged.py").read_text(encoding="utf-8")
        self.assertTrue(implementation.is_file())
        self.assertIn("AoiMusic.core.keep_alive", merged)
        self.assertNotIn("from keep_alive import", merged)

    def test_render_blueprint_uses_health_route_and_cookie_secret_path(self):
        from pathlib import Path

        blueprint = Path(__file__).resolve().parents[1] / "render.yaml"
        content = blueprint.read_text(encoding="utf-8")
        self.assertIn("healthCheckPath: /health", content)
        self.assertIn("/etc/secrets/youtube-cookies.txt", content)
        self.assertIn("plan: starter", content)


if __name__ == "__main__":
    unittest.main()
