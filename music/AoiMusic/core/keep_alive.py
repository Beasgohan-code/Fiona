"""Threaded HTTP liveness/readiness endpoints for the unified Fiona process.

The health server runs alongside the Telegram clients in the same process. It
is intended for Render/container health checks, not as a way to defeat a host's
sleep policy.
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
_DEFAULT_HEARTBEAT_TIMEOUT = 120


def _heartbeat_timeout() -> int:
    try:
        value = int(os.getenv("KEEP_ALIVE_MAX_AGE", str(_DEFAULT_HEARTBEAT_TIMEOUT)))
    except (TypeError, ValueError):
        return _DEFAULT_HEARTBEAT_TIMEOUT
    return value if value > 0 else _DEFAULT_HEARTBEAT_TIMEOUT


class _HealthServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def beat() -> None:
    """Record that Fiona's asyncio event loop is still responsive."""
    global _last_heartbeat
    with _state_lock:
        _last_heartbeat = time.monotonic()


def set_ready(ready: bool = True) -> None:
    """Mark the bot ready after startup, or not-ready during shutdown."""
    global _ready, _last_heartbeat
    with _state_lock:
        _ready = bool(ready)
        if ready:
            _last_heartbeat = time.monotonic()


def _health_snapshot() -> tuple[int, dict[str, Any]]:
    with _state_lock:
        ready = _ready
        heartbeat_age = max(0, int(time.monotonic() - _last_heartbeat))
    fresh = heartbeat_age < _heartbeat_timeout()
    ok = ready and fresh
    return (200 if ok else 503), {
        "ok": ok,
        "status": "ok" if ok else ("stale" if ready else "starting"),
        "uptime_seconds": max(0, int(time.monotonic() - _started_at)),
        "heartbeat_age_seconds": heartbeat_age,
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "FionaHealth/1.1"

    def _respond(self, include_body: bool = True) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/health", "/ready", "/live", "/ping"):
            self.send_error(404)
            return

        if path == "/live":
            status = 200
            payload = {"ok": True, "status": "live"}
        elif path == "/":
            status = 200
            payload = None
        else:
            status, payload = _health_snapshot()

        if path == "/":
            body = b"Fiona is running\n"
            content_type = "text/plain; charset=utf-8"
        else:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            content_type = "application/json; charset=utf-8"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if include_body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                log.debug("health client disconnected before response completed")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._respond()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._respond(include_body=False)

    def log_message(self, format: str, *args: Any) -> None:
        log.debug("health HTTP %s - %s", self.address_string(), format % args)


def start_server(host: str | None = None, port: int | None = None) -> _HealthServer:
    """Bind the health server (Render supplies ``PORT``; local default is 10000)."""
    global _ready
    host = host or os.getenv("KEEP_ALIVE_HOST", "0.0.0.0")
    configured_port = os.getenv("KEEP_ALIVE_PORT") or os.getenv("PORT", "10000")
    try:
        port = int(port if port is not None else configured_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("KEEP_ALIVE_PORT/PORT must be an integer") from exc
    if not 0 <= port <= 65535:
        raise ValueError("health server port must be between 0 and 65535")

    with _state_lock:
        _ready = False
    server = _HealthServer((host, port), _Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="fiona-health",
        daemon=True,
    )
    server._fiona_thread = thread
    thread.start()
    log.info("Fiona health endpoints listening on %s:%s", host, server.server_address[1])
    return server


def stop_server(server: _HealthServer | None) -> None:
    """Stop a server returned by :func:`start_server`, safely on repeated calls."""
    if server is None:
        return
    set_ready(False)
    thread = getattr(server, "_fiona_thread", None)
    if thread is not None and thread.is_alive():
        server.shutdown()
        thread.join(timeout=5)
    server.server_close()


__all__ = ["beat", "set_ready", "start_server", "stop_server"]
