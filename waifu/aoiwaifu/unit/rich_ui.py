"""Shared rich-message and premium-button helpers for Fiona's collection UI."""

from __future__ import annotations

from pyrogram.enums import ParseMode

from AoiMusic.utils.premium_emoji import pbtn
from AoiMusic.utils.rich_msg import edit_rich, premiumize_html


def premium_text(text: str) -> str:
    """Decorate supported emoji in rich HTML while preserving standard fallbacks."""
    try:
        return premiumize_html(str(text or ""))
    except Exception:
        return str(text or "")


def premium_button(text: str, emoji: str, **kwargs):
    """Build a native premium-icon button with graceful plain-button fallback."""
    return pbtn(text=text, emoji=emoji, **kwargs)


def rich_card(title: str, body: str, emoji: str = "✨") -> str:
    """Wrap a short HTML body in Fiona's consistent Telegram card treatment."""
    title = str(title or "Fiona")
    body = str(body or "")
    return f"<b>{emoji} {title}</b>\n<blockquote>{body}</blockquote>"


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
