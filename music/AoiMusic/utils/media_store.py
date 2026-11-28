"""Telegram-only persistent audio cache backed by a private Store channel.

The Store channel is both the file vault and the search index: uploads carry a
``#FionaMediaCache`` marker plus the YouTube video id, and later playback
searches that channel before falling back to the normal download providers.
MongoDB is deliberately not used for this cache.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from typing import AsyncIterator, Any

import config
from AoiMusic import app


_MARKER = "#FionaMediaCache"
_VIDEO_ID_RE = re.compile(r"[^A-Za-z0-9_-]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SUPPORTED_AUDIO_EXTS = {
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".webm"
}
_store_tasks: set[asyncio.Task] = set()
_store_locks: dict[str, asyncio.Lock] = {}


def _store_id() -> int:
    try:
        return int(getattr(config, "STORE_ID", 0) or 0)
    except (TypeError, ValueError):
        return 0


def store_enabled() -> bool:
    return _store_id() != 0


def _max_file_bytes() -> int:
    try:
        limit_mb = int(getattr(config, "STORE_MAX_MB", 45) or 45)
    except (TypeError, ValueError):
        limit_mb = 45
    return max(1, limit_mb) * 1024 * 1024


def _video_id(value: Any) -> str:
    return _VIDEO_ID_RE.sub("", str(value or ""))[:64]


def _clean_text(value: Any, limit: int = 140) -> str:
    return _CONTROL_RE.sub(" ", str(value or "")).strip()[:limit]


def _extension(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    return ext if ext in _SUPPORTED_AUDIO_EXTS else ".mp3"


def _caption(video_id: str, title: str = "") -> str:
    safe_title = _clean_text(title, 120)
    lines = [_MARKER, f"video_id={video_id}"]
    if safe_title:
        lines.append(f"title={safe_title}")
    return "\n".join(lines)


def _message_caption(message: Any) -> str:
    return str(getattr(message, "caption", None) or getattr(message, "text", None) or "")


def _message_has_video(message: Any, video_id: str) -> bool:
    caption = _message_caption(message)
    return (
        _MARKER in caption
        and f"video_id={video_id}" in caption
        and message_file_id(message) is not None
    )


def message_file_id(message: Any) -> tuple[str, str] | None:
    """Return (file_id, file_name) for audio-like messages stored by Fiona."""
    audio = getattr(message, "audio", None)
    if audio and getattr(audio, "file_id", None):
        file_name = _clean_text(getattr(audio, "file_name", "") or f"{_video_id(getattr(audio, 'file_unique_id', 'audio'))}.mp3", 120)
        return str(audio.file_id), file_name
    document = getattr(message, "document", None)
    if document and getattr(document, "file_id", None):
        mime = str(getattr(document, "mime_type", "") or "").lower()
        file_name = _clean_text(getattr(document, "file_name", "") or "cached-audio.mp3", 120)
        ext = Path(file_name).suffix.lower()
        if mime.startswith("audio/") or ext in _SUPPORTED_AUDIO_EXTS:
            return str(document.file_id), file_name
    return None


def _assistant_client():
    """Return the first assistant user session, if one is configured.

    Kurigram/Pyrogram exposes channel search as a user-client operation. If the
    bot client cannot search the Store channel, an assistant already configured
    by the bot owner can be used instead. Add that assistant account to the
    private Store channel for this fallback to work.
    """
    try:
        from AoiMusic import userbot
        clients = getattr(userbot, "clients", None) or []
        return clients[0] if clients else None
    except Exception:
        return None


async def _iter_search_results(result: Any) -> AsyncIterator[Any]:
    if result is None:
        return
    if inspect.isawaitable(result):
        result = await result
    if hasattr(result, "__aiter__"):
        async for item in result:
            yield item
        return
    for item in result or []:
        yield item


async def _search_cached_message(video_id: Any):
    """Return ``(client, file_id, file_name)`` for a Store match.

    The bot client is tried first because it is the account that uploaded the
    file. When channel search is unavailable to bots in the installed Telegram
    client, the configured assistant user account is used instead. The returned
    client must be used for the matching ``file_id``.
    """
    if not store_enabled():
        return None
    safe_video_id = _video_id(video_id)
    if not safe_video_id:
        return None
    assistant = _assistant_client()
    clients = [app]
    if assistant is not None and assistant is not app:
        clients.append(assistant)
    for client in clients:
        try:
            search_result = client.search_messages(_store_id(), safe_video_id, limit=20)
            async for message in _iter_search_results(search_result):
                if _message_has_video(message, safe_video_id):
                    cached = message_file_id(message)
                    if cached:
                        return client, cached[0], cached[1]
            # A matching message was selected, or this client completed an empty
            # search; try the configured assistant as well if it is available.
            continue
        except Exception:
            continue
    return None


async def find_cached_audio(video_id: Any):
    """Find a cached audio message by exact YouTube video id.

    Returns ``(file_id, file_name)`` on a strong match, otherwise ``None``.
    Telegram search is best-effort; invalid or deleted messages simply fall
    back to the normal provider flow.
    """
    cached = await _search_cached_message(video_id)
    if cached is None:
        return None
    _client, file_id, file_name = cached
    return file_id, file_name


async def download_cached_audio(video_id: Any, downloads_dir: str | Path = "downloads") -> str | None:
    """Download a cached audio file from STORE_ID if available."""
    cached = await _search_cached_message(video_id)
    if not cached:
        return None
    client, file_id, file_name = cached
    safe_video_id = _video_id(video_id)
    ext = _extension(file_name)
    target = Path(downloads_dir) / f"store_{safe_video_id}{ext}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            return str(target)
        downloaded = await client.download_media(file_id, file_name=str(target))
        path = Path(downloaded or target)
        if path.exists() and path.stat().st_size > 0:
            return str(path)
    except Exception:
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
    return None


async def store_audio(video_id: Any, file_path: str | Path, title: Any = "") -> bool:
    """Upload one downloaded audio file to STORE_ID, then make it searchable."""
    if not store_enabled():
        return False
    safe_video_id = _video_id(video_id)
    path = Path(file_path)
    if not safe_video_id or not path.is_file():
        return False
    if path.stat().st_size <= 0 or path.stat().st_size > _max_file_bytes():
        return False
    lock = _store_locks.setdefault(safe_video_id, asyncio.Lock())
    async with lock:
        if await _search_cached_message(safe_video_id):
            return True
        try:
            await app.send_audio(
                _store_id(),
                str(path),
                caption=_caption(safe_video_id, title),
            )
            return True
        except Exception:
            return False


def schedule_store_audio(video_id: Any, file_path: str | Path, title: Any = "") -> asyncio.Task | None:
    """Upload without delaying playback or failing the play handler."""
    if not store_enabled():
        return None
    task = asyncio.create_task(store_audio(video_id, file_path, title))
    _store_tasks.add(task)

    def _done(done: asyncio.Task) -> None:
        _store_tasks.discard(done)
        try:
            done.result()
        except Exception:
            pass

    task.add_done_callback(_done)
    return task


__all__ = [
    "store_enabled",
    "find_cached_audio",
    "download_cached_audio",
    "store_audio",
    "schedule_store_audio",
    "message_file_id",
]
