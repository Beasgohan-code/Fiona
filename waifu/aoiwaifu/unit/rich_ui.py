"""Shared Richgram message and premium-button helpers for Fiona's bot UI."""

from __future__ import annotations

from pyrogram.enums import ParseMode

from AoiMusic.utils.premium_emoji import pbtn
from AoiMusic.utils.rich_msg import edit_rich, premiumize_html, rich_esc


def premium_text(text: str) -> str:
    """Decorate supported emoji in rich HTML while preserving standard fallbacks."""
    try:
        return premiumize_html(str(text or ""))
    except Exception:
        return str(text or "")


def premium_button(text: str, emoji: str, **kwargs):
    """Build a native premium-icon button with graceful plain-button fallback."""
    return pbtn(text=text, emoji=emoji, **kwargs)


def rich_heading(title: str, emoji: str = "✨") -> str:
    """Render a strong, parse-mode-safe heading for Richgram-style panels."""
    return f"<b>{emoji} {title}</b>"


def rich_table(headers, rows) -> str:
    """Render a compact, Telegram-safe table with clear row and column breaks.

    Telegram's Bot API doesn't accept HTML <table> tags, so rows use compact
    bullet separators and plain line breaks instead of drawing borders.
    Cell values may contain trusted HTML such as <code> or <b> tags.
    """
    header = "  •  ".join(str(cell) for cell in headers)
    lines = [f"<b>{header}</b>"]
    for row in rows:
        lines.append("  •  ".join(str(cell) for cell in row))
    return "\n".join(lines)


def rich_card(title: str, body: str, emoji: str = "✨") -> str:
    """Render an open, borderless Fiona panel with a clear title and body."""
    title = str(title or "Fiona")
    body = str(body or "").strip()
    return "\n\n".join((rich_heading(title, emoji), body)) if body else rich_heading(title, emoji)


def notice_card(
    text: str,
    emoji: str | None = None,
    title: str = "Fiona",
) -> str:
    """Turn plain user-facing text into a safe, borderless Richgram notice."""
    raw = str(text or "").strip()
    if emoji is None:
        emoji = next(
            (
                mark
                for mark in (
                    "🚫", "❌", "⚠️", "⏰", "⏳", "🔄", "✅", "🎉", "📌", "🌸"
                )
                if raw.startswith(mark)
            ),
            "ℹ️",
        )
    body = raw[len(emoji):].lstrip() if raw.startswith(emoji) else raw
    return premium_text(rich_card(rich_esc(title), rich_esc(body), emoji))


async def reply_notice(
    message,
    text=None,
    *,
    emoji: str | None = None,
    title: str = "Fiona",
    **kwargs,
):
    """Reply with a Richgram notice, falling back to the original plain text."""
    raw = str(text or "")
    original_kwargs = dict(kwargs)
    rich_kwargs = dict(kwargs)
    rich_kwargs.setdefault("disable_web_page_preview", True)
    rich_kwargs["parse_mode"] = kwargs.get("parse_mode") or ParseMode.HTML
    try:
        return await message.reply_text(
            notice_card(raw, emoji=emoji, title=title),
            **rich_kwargs,
        )
    except (TypeError, ValueError):
        original_kwargs.pop("parse_mode", None)
        return await message.reply_text(raw, **original_kwargs)
    except Exception as exc:
        reason = str(exc).lower()
        parse_errors = (
            "parse entities",
            "can't parse",
            "unsupported start tag",
            "can't find end tag",
        )
        if not any(token in reason for token in parse_errors):
            raise
        original_kwargs.pop("parse_mode", None)
        return await message.reply_text(raw, **original_kwargs)


async def edit_notice(
    message,
    text,
    *,
    emoji: str | None = None,
    title: str = "Fiona",
    reply_markup=None,
) -> bool:
    """Edit an existing message into the same safe Richgram notice style."""
    return await edit_panel(
        message,
        notice_card(text, emoji=emoji, title=title),
        reply_markup=reply_markup,
    )


async def edit_panel(message, text: str, reply_markup=None) -> bool:
    """Edit a Fiona panel through the shared rich renderer, then fall back safely."""
    html = premium_text(text)
    try:
        if await edit_rich(
            message.chat.id,
            message.id,
            html,
            reply_markup=reply_markup,
        ):
            return True
    except Exception:
        pass

    try:
        await message.edit_caption(
            caption=html,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
        return True
    except Exception:
        try:
            await message.edit_text(
                text=html,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return True
        except Exception:
            return False
