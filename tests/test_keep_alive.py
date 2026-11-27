import json
import os
import threading
import time
import unittest
from unittest.mock import patch
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

            keep_alive.beat({"telegram_bot": False, "assistant_session": True})
            keep_alive.set_ready(True)
            with self.assertRaises(HTTPError) as response:
                urlopen(url, timeout=2)
            self.assertEqual(response.exception.code, 503)
            degraded = json.load(response.exception)
            self.assertEqual(degraded["status"], "degraded")
            self.assertEqual(degraded["unhealthy_components"], ["telegram_bot"])

            keep_alive.beat({"telegram_bot": True, "assistant_session": True})
            with urlopen(url, timeout=2) as response:
                self.assertEqual(response.status, 200)
                payload = json.load(response)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["bot"], "Fiona")
            self.assertIn("heartbeat_timeout_seconds", payload)
            self.assertIn("checked_at", payload)
            self.assertEqual(payload["components"], {"telegram_bot": True, "assistant_session": True})

            # Readiness fails on a truly stale heartbeat, while liveness remains 200.
            implementation = keep_alive._IMPLEMENTATION
            with implementation._state_lock:
                implementation._last_heartbeat = time.monotonic() - implementation._heartbeat_timeout() - 1
            with self.assertRaises(HTTPError) as response:
                urlopen(url, timeout=2)
            self.assertEqual(response.exception.code, 503)
            self.assertEqual(json.load(response.exception)["status"], "stale")
            with urlopen(f"http://127.0.0.1:{server.server_address[1]}/live", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(json.load(response)["heartbeat_age_seconds"], 0)

            keep_alive.beat({"telegram_bot": True, "assistant_session": True})
            keep_alive.set_ready(False)
            with self.assertRaises(HTTPError) as response:
                urlopen(url, timeout=2)
            self.assertEqual(response.exception.code, 503)
        finally:
            keep_alive.stop_server(server)
            keep_alive.stop_server(server)

    def test_live_endpoint_is_separate_from_readiness_and_head_is_supported(self):
        server = keep_alive.start_server(host="127.0.0.1", port=0)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base_url}/live", timeout=2) as response:
                self.assertEqual(response.status, 200)
                live = json.load(response)
                self.assertTrue(live["ok"])
                self.assertEqual(live["status"], "live")
                self.assertIn("uptime_seconds", live)

            # Liveness remains 200 during startup; readiness reports 503.
            with urlopen(f"{base_url}/ping", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["status"], "live")

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

    def test_render_self_ping_target_uses_external_url_and_liveness_route(self):
        implementation = keep_alive._IMPLEMENTATION
        with patch.dict(
            os.environ,
            {
                "KEEP_ALIVE_SELF_PING": "true",
                "KEEP_ALIVE_PING_URL": "",
                "RENDER_EXTERNAL_URL": "https://fiona.example.test/",
            },
        ):
            self.assertEqual(
                implementation._self_ping_target(10000),
                ("https://fiona.example.test/live", "public"),
            )

    def test_optional_public_self_ping_records_success_and_stops_cleanly(self):
        with patch.dict(
            os.environ,
            {
                "KEEP_ALIVE_SELF_PING": "true",
                "KEEP_ALIVE_PING_URL": "",
                "RENDER_EXTERNAL_URL": "",
                "KEEP_ALIVE_PING_TIMEOUT": "2",
            },
        ):
            server = keep_alive.start_server(host="127.0.0.1", port=0)
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                deadline = time.monotonic() + 2
                payload = {}
                while time.monotonic() < deadline:
                    with urlopen(f"{base_url}/live", timeout=1) as response:
                        payload = json.load(response)
                    if payload["keepalive"]["last_success_at"]:
                        break
                    time.sleep(0.02)
                self.assertTrue(payload["keepalive"]["enabled"])
                self.assertEqual(payload["keepalive"]["mode"], "local")
                self.assertTrue(payload["keepalive"]["running"])
                self.assertIsNotNone(payload["keepalive"]["last_success_at"])
                self.assertEqual(payload["keepalive"]["consecutive_failures"], 0)
            finally:
                keep_alive.stop_server(server)
            self.assertFalse(server._fiona_self_ping_thread.is_alive())

    def test_watchdog_logs_stale_and_component_failure_recovery_once(self):
        implementation = keep_alive._IMPLEMENTATION
        stop_event = threading.Event()
        keep_alive.beat({"telegram_bot": False})
        keep_alive.set_ready(True)
        with implementation._state_lock:
            implementation._last_heartbeat = time.monotonic() - implementation._heartbeat_timeout() - 1

        with patch.object(implementation, "_watchdog_interval", return_value=0.01):
            with self.assertLogs("fiona.keepalive", level="INFO") as captured:
                watchdog = threading.Thread(
                    target=implementation._watchdog_loop,
                    args=(stop_event,),
                    daemon=True,
                )
                watchdog.start()
                time.sleep(0.04)
                keep_alive.beat({"telegram_bot": True})
                time.sleep(0.04)
                stop_event.set()
                watchdog.join(timeout=1)

        self.assertFalse(watchdog.is_alive())
        output = "\n".join(captured.output)
        self.assertIn("heartbeat is stale", output)
        self.assertIn("heartbeat recovered", output)
        self.assertIn("component is unhealthy: telegram_bot", output)
        self.assertIn("component recovered: telegram_bot", output)
        keep_alive.set_ready(False)
        keep_alive.beat()

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
        self.assertIn("KEEP_ALIVE_SELF_PING", content)
        self.assertIn('value: "300"', content)


if __name__ == "__main__":
    unittest.main()
