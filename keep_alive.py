"""Small health/keep-alive HTTP server for Render and other web hosts.

This exposes liveness only; it does not run a second bot client or promise to
prevent a hosting provider from sleeping a free instance.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

log = logging.getLogger("fiona.keepalive")
_started_at = time.monotonic()
_last_heartbeat = _started_at
_ready = False
_state_lock = threading.Lock()


class _HealthServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def beat() -> None:
    """Record that the bot's asyncio event loop is still responsive."""
    global _last_heartbeat
    with _state_lock:
        _last_heartbeat = time.monotonic()


def set_ready(ready: bool = True) -> None:
    """Mark the bot healthy after startup, or unhealthy during shutdown."""
    global _ready
    with _state_lock:
        _ready = bool(ready)
        if ready:
            global _last_heartbeat
            _last_heartbeat = time.monotonic()


def _health() -> tuple[int, dict[str, Any]]:
    with _state_lock:
        ready = _ready
        heartbeat_age = max(0, int(time.monotonic() - _last_heartbeat))
    ok = ready and heartbeat_age < 120
    return (200 if ok else 503), {
        "ok": ok,
        "status": "ok" if ok else ("stale" if ready else "starting"),
        "uptime_seconds": int(time.monotonic() - _started_at),
        "heartbeat_age_seconds": heartbeat_age,
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "FionaHealth/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path not in ("/", "/health", "/ping"):
            self.send_error(404)
            return
        status, payload = _health()
        body = (
            b"Fiona is running\\n"
            if self.path == "/"
            else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        content_type = "text/plain; charset=utf-8" if self.path == "/" else "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        log.debug("health HTTP %s - %s", self.address_string(), format % args)


def start_server(host: str | None = None, port: int | None = None) -> _HealthServer:
    """Bind the health server (Render supplies PORT; local default is 10000)."""
    global _ready
    host = host or os.getenv("KEEP_ALIVE_HOST", "0.0.0.0")
    port = int(port if port is not None else os.getenv("PORT", "10000"))
    with _state_lock:
        _ready = False
    server = _HealthServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, name="fiona-health", daemon=True)
    thread.start()
    log.info("Fiona health endpoint listening on %s:%s", host, server.server_address[1])
    return server


def stop_server(server: _HealthServer | None) -> None:
    """Stop a server previously returned by :func:`start_server`."""
    if server is None:
        return
    set_ready(False)
    server.shutdown()
    server.server_close()


__all__ = ["beat", "set_ready", "start_server", "stop_server"]
