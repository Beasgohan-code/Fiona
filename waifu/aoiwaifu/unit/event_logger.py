"""Shared Telegram event-log helpers for Fiona's Music and Waifu features."""
from __future__ import annotations

import html
import logging
from typing import Any


def actor_details(user: Any, fallback: str = "Unknown", label: str = "Actor") -> str:
    """Return a compact, HTML-safe actor identity for event-log messages."""
    if user is None:
        return f"<b>{html.escape(label)}:</b> {html.escape(fallback)}"

    name = html.escape(
        " ".join(
            part
            for part in (
                getattr(user, "first_name", ""),
                getattr(user, "last_name", ""),
            )
            if part
        )
        or fallback
    )
    username = getattr(user, "username", None)
    if username:
        safe_username = html.escape(str(username), quote=True)
        name = f'<a href="https://t.me/{safe_username}">{name}</a> (@{safe_username})'
    user_id = getattr(user, "id", None)
    identity = f"<b>{html.escape(label)}:</b> {name}"
    if user_id is not None:
        identity += f"\n<b>User ID:</b> <code>{int(user_id)}</code>"
    return identity


def _normalized_target(destination: int | str | None) -> int | str | None:
    target = str(destination or "").strip()
    if not target:
        return None
    numeric = target[1:] if target.startswith("-") else target
    if numeric.isdigit():
        value = int(target)
        return value if value else None
    return target


async def send_event_log(
    client: Any,
    destination: int | str | None,
    text: str,
    *,
    logger_name: str = "Fiona.EventLog",
) -> bool:
    """Best-effort send to the configured log chat; event logging never breaks handlers."""
    target = _normalized_target(destination)
    if target is None:
        return False

    try:
        await client.send_message(
            chat_id=target,
            text=text,
            disable_web_page_preview=True,
        )
        return True
    except Exception as exc:
        logging.getLogger(logger_name).warning(
            "Could not send event log to %r (%s); check the log chat configuration and bot permissions.",
            target,
            type(exc).__name__,
        )
        return False


async def send_event_logs(
    client: Any,
    destinations: list[int | str | None] | tuple[int | str | None, ...],
    text: str,
    *,
    logger_name: str = "Fiona.EventLog",
) -> int:
    """Send once to each configured unique destination and return success count."""
    unique: list[int | str] = []
    seen: set[int | str] = set()
    for destination in destinations:
        target = _normalized_target(destination)
        if target is not None and target not in seen:
            seen.add(target)
            unique.append(target)
    results = [
        await send_event_log(client, target, text, logger_name=logger_name)
        for target in unique
    ]
    return sum(results)


__all__ = ["actor_details", "send_event_log", "send_event_logs"]
