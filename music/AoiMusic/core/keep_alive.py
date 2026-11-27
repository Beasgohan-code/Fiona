"""Threaded HTTP liveness/readiness endpoints for the unified Fiona process.

The health server runs alongside the Telegram clients in the same process.
It exposes separate liveness/readiness checks and can optionally self-ping its
public liveness URL when the deployment provides one. Self-pinging is best-effort
and never substitutes for an always-on hosting plan.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

log = logging.getLogger("fiona.keepalive")
_started_at = time.monotonic()
_last_heartbeat = _started_at
_ready = False
_components: dict[str, bool] = {}
_state_lock = threading.Lock()
_self_ping_thread: threading.Thread | None = None
_self_ping_stop: threading.Event | None = None
_self_ping_state: dict[str, Any] = {
    "enabled": False,
    "mode": None,
    "running": False,
    "last_success_at": None,
    "consecutive_failures": 0,
    "last_error": None,
}
_DEFAULT_HEARTBEAT_TIMEOUT = 120
_DEFAULT_SELF_PING_INTERVAL = 300
_DEFAULT_SELF_PING_TIMEOUT = 10


def _heartbeat_timeout() -> int:
    try:
        value = int(os.getenv("KEEP_ALIVE_MAX_AGE", str(_DEFAULT_HEARTBEAT_TIMEOUT)))
    except (TypeError, ValueError):
        return _DEFAULT_HEARTBEAT_TIMEOUT
    return value if value > 0 else _DEFAULT_HEARTBEAT_TIMEOUT


def _watchdog_interval() -> int:
    try:
        value = int(os.getenv("KEEP_ALIVE_WATCHDOG_INTERVAL", "30"))
    except (TypeError, ValueError):
        return 30
    return max(1, value)


def _self_ping_interval() -> int:
    try:
        value = int(os.getenv("KEEP_ALIVE_SELF_PING_INTERVAL", str(_DEFAULT_SELF_PING_INTERVAL)))
    except (TypeError, ValueError):
        return _DEFAULT_SELF_PING_INTERVAL
    return max(30, value)


def _self_ping_timeout() -> int:
    try:
        value = int(os.getenv("KEEP_ALIVE_PING_TIMEOUT", str(_DEFAULT_SELF_PING_TIMEOUT)))
    except (TypeError, ValueError):
        return _DEFAULT_SELF_PING_TIMEOUT
    return max(1, value)


def _self_ping_enabled() -> bool:
    configured = os.getenv("KEEP_ALIVE_SELF_PING")
    if configured is None:
        # Render sets this URL for web services. A custom ping target is also
        # an explicit opt-in; other hosts remain disabled by default.
        return bool(
            (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
            or (os.getenv("KEEP_ALIVE_PING_URL") or "").strip()
        )
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def _self_ping_target(port: int) -> tuple[str, str]:
    public_base = (os.getenv("KEEP_ALIVE_PING_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    mode = "public" if public_base else "local"
    base = public_base or f"http://127.0.0.1:{port}"
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("self-ping URL must be an absolute HTTP(S) URL")
    path = parsed.path.rstrip("/")
    if not path.endswith(("/live", "/ping")):
        path = f"{path}/live" if path else "/live"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")), mode


def _self_ping_snapshot() -> dict[str, Any]:
    with _state_lock:
        snapshot = dict(_self_ping_state)
        thread = _self_ping_thread
    snapshot["running"] = bool(thread and thread.is_alive())
    return snapshot


def _self_ping_loop(stop_event: threading.Event, target: str, timeout: int) -> None:
    """Periodically request this service's public liveness URL, if enabled."""
    request = Request(target, headers={"User-Agent": "Fiona-KeepAlive/1.0"})
    while not stop_event.is_set():
        try:
            with urlopen(request, timeout=timeout) as response:
                if not 200 <= response.status < 400:
                    raise RuntimeError(f"HTTP_{response.status}")
            with _state_lock:
                _self_ping_state.update(
                    last_success_at=datetime.now(timezone.utc).isoformat(),
                    consecutive_failures=0,
                    last_error=None,
                )
        except Exception as exc:
            with _state_lock:
                _self_ping_state["consecutive_failures"] += 1
                _self_ping_state["last_error"] = type(exc).__name__
            log.warning("Fiona self-ping failed (%s)", type(exc).__name__)
        stop_event.wait(_self_ping_interval())


class _HealthServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def beat(components: dict[str, bool] | None = None) -> None:
    """Record event-loop responsiveness and the latest critical client states."""
    global _last_heartbeat, _components
    with _state_lock:
        _last_heartbeat = time.monotonic()
        if components is not None:
            # Copy and normalize values so callers cannot mutate shared state.
            _components = {str(name): bool(healthy) for name, healthy in components.items()}


def set_ready(ready: bool = True) -> None:
    """Mark the bot ready after startup, or not-ready during shutdown."""
    global _ready, _last_heartbeat
    with _state_lock:
        _ready = bool(ready)
        if ready:
            _last_heartbeat = time.monotonic()


def _health_snapshot() -> tuple[int, dict[str, Any]]:
    now = time.monotonic()
    with _state_lock:
        ready = _ready
        heartbeat_age = max(0.0, now - _last_heartbeat)
        components = dict(_components)
    timeout = _heartbeat_timeout()
    fresh = heartbeat_age < timeout
    unhealthy = sorted(name for name, healthy in components.items() if not healthy)
    ok = ready and fresh and not unhealthy
    if not ready:
        status = "starting"
    elif not fresh:
        status = "stale"
    elif unhealthy:
        status = "degraded"
    else:
        status = "ok"
    return (200 if ok else 503), {
        "ok": ok,
        "bot": "Fiona",
        "ready": ready,
        "status": status,
        "uptime_seconds": max(0, int(now - _started_at)),
        "heartbeat_age_seconds": round(heartbeat_age, 3),
        "heartbeat_timeout_seconds": timeout,
        "components": components,
        "unhealthy_components": unhealthy,
        "keepalive": _self_ping_snapshot(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _liveness_snapshot() -> dict[str, Any]:
    now = time.monotonic()
    with _state_lock:
        heartbeat_age = max(0.0, now - _last_heartbeat)
        components = dict(_components)
    return {
        "ok": True,
        "bot": "Fiona",
        "status": "live",
        "uptime_seconds": max(0, int(now - _started_at)),
        "heartbeat_age_seconds": round(heartbeat_age, 3),
        "components": components,
        "keepalive": _self_ping_snapshot(),
    }


def _watchdog_loop(stop_event: threading.Event) -> None:
    """Log stale heartbeats and critical-client transitions once per incident."""
    stale = False
    unhealthy_components: set[str] = set()
    while not stop_event.wait(_watchdog_interval()):
        _, snapshot = _health_snapshot()
        is_stale = snapshot["status"] == "stale"
        if is_stale and not stale:
            log.warning(
                "Fiona heartbeat is stale (%.3fs old; threshold %ss)",
                snapshot["heartbeat_age_seconds"],
                snapshot["heartbeat_timeout_seconds"],
            )
        elif stale and not is_stale and snapshot["ready"]:
            log.info("Fiona heartbeat recovered (age %.3fs)", snapshot["heartbeat_age_seconds"])
        stale = is_stale

        current_unhealthy = set(snapshot["unhealthy_components"])
        for name in sorted(current_unhealthy - unhealthy_components):
            log.warning("Fiona critical component is unhealthy: %s", name)
        for name in sorted(unhealthy_components - current_unhealthy):
            log.info("Fiona critical component recovered: %s", name)
        unhealthy_components = current_unhealthy


class _Handler(BaseHTTPRequestHandler):
    server_version = "FionaHealth/1.1"

    def _respond(self, include_body: bool = True) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/health", "/ready", "/live", "/ping"):
            self.send_error(404)
            return

        if path in ("/live", "/ping"):
            status = 200
            payload = _liveness_snapshot()
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
    global _ready, _last_heartbeat, _components, _self_ping_thread, _self_ping_stop, _self_ping_state
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
        _last_heartbeat = time.monotonic()
        _components = {}
        _self_ping_thread = None
        _self_ping_stop = None
        _self_ping_state = {
            "enabled": False,
            "mode": None,
            "running": False,
            "last_success_at": None,
            "consecutive_failures": 0,
            "last_error": None,
        }
    server = _HealthServer((host, port), _Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="fiona-health",
        daemon=True,
    )
    server._fiona_thread = thread
    thread.start()
    watchdog_stop = threading.Event()
    watchdog_thread = threading.Thread(
        target=_watchdog_loop,
        args=(watchdog_stop,),
        name="fiona-health-watchdog",
        daemon=True,
    )
    server._fiona_watchdog_stop = watchdog_stop
    server._fiona_watchdog_thread = watchdog_thread
    watchdog_thread.start()

    ping_stop = None
    ping_thread = None
    if _self_ping_enabled():
        try:
            target, ping_mode = _self_ping_target(server.server_address[1])
        except ValueError as exc:
            log.warning("Fiona self-ping disabled: %s", exc)
        else:
            ping_stop = threading.Event()
            ping_thread = threading.Thread(
                target=_self_ping_loop,
                args=(ping_stop, target, _self_ping_timeout()),
                name="fiona-public-self-ping",
                daemon=True,
            )
            with _state_lock:
                _self_ping_thread = ping_thread
                _self_ping_stop = ping_stop
                _self_ping_state["enabled"] = True
                _self_ping_state["mode"] = ping_mode
            ping_thread.start()
            log.info(
                "Fiona public self-ping enabled (interval %ss)", _self_ping_interval()
            )
    server._fiona_self_ping_stop = ping_stop
    server._fiona_self_ping_thread = ping_thread
    log.info("Fiona health endpoints listening on %s:%s", host, server.server_address[1])
    return server


def stop_server(server: _HealthServer | None) -> None:
    """Stop a server returned by :func:`start_server`, safely on repeated calls."""
    if server is None:
        return
    set_ready(False)
    ping_stop = getattr(server, "_fiona_self_ping_stop", None)
    if ping_stop is not None:
        ping_stop.set()
    ping_thread = getattr(server, "_fiona_self_ping_thread", None)
    if ping_thread is not None and ping_thread.is_alive():
        ping_thread.join(timeout=_self_ping_timeout() + 2)
        if ping_thread.is_alive():
            log.warning("Fiona self-ping thread did not stop before timeout")
    watchdog_stop = getattr(server, "_fiona_watchdog_stop", None)
    if watchdog_stop is not None:
        watchdog_stop.set()
    watchdog_thread = getattr(server, "_fiona_watchdog_thread", None)
    if watchdog_thread is not None and watchdog_thread.is_alive():
        watchdog_thread.join(timeout=2)
    thread = getattr(server, "_fiona_thread", None)
    if thread is not None and thread.is_alive():
        server.shutdown()
        thread.join(timeout=5)
    server.server_close()


__all__ = ["beat", "set_ready", "start_server", "stop_server"]
