import json
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

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

    def test_render_blueprint_uses_health_route_and_cookie_secret_path(self):
        from pathlib import Path

        blueprint = Path(__file__).resolve().parents[1] / "render.yaml"
        content = blueprint.read_text(encoding="utf-8")
        self.assertIn("healthCheckPath: /health", content)
        self.assertIn("/etc/secrets/youtube-cookies.txt", content)
        self.assertIn("plan: starter", content)


if __name__ == "__main__":
    unittest.main()
