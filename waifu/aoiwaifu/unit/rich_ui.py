"""Shared Richgram message and premium-button helpers for Fiona's bot UI."""

from __future__ import annotations

from types import SimpleNamespace

from pyrogram.enums import ParseMode

from AoiMusic.utils.rich_msg import send_rich

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
    """Render a parse-mode-safe heading with safely escaped title text."""
    return f"<b>{emoji} {rich_esc(title)}</b>"


def rich_quote(text: str) -> str:
    """Render a safe Telegram blockquote, preserving allowed rich inline tags."""
    return f"<blockquote>{rich_esc(text)}</blockquote>"


def rich_progress_bar(current, maximum, width: int = 12) -> str:
    """Render a compact Unicode progress bar for rich cards."""
    width = max(4, int(width or 12))
    try:
        maximum = int(maximum)
        current = max(0, int(current))
    except (TypeError, ValueError):
        current, maximum = 0, 0
    if maximum <= 0:
        filled = width
    else:
        filled = min(width, max(0, round(current / maximum * width)))
    return "▰" * filled + "▱" * (width - filled)


def user_mention(user, fallback: str = "User") -> str:
    """Return an HTML-safe tg:// mention link for rich cards and panels."""
    name = rich_esc(getattr(user, "first_name", None) or fallback)
    user_id = getattr(user, "id", None)
    if user_id is None:
        return name
    return f'<a href="tg://user?id={int(user_id)}">{name}</a>'


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
    """Render a compact borderless Fiona panel using Richgram-compatible tags."""
    body = str(body or "").strip()
    heading = rich_heading(str(title or "Fiona"), emoji)
    return "\n\n".join((heading, body)) if body else heading


def rich_showcase_panel(title: str, body: str, emoji: str = "✨") -> str:
    """Build an emphasized Richgram panel with a structural heading.

    ``body`` is trusted Richgram HTML assembled by the caller. The title is
    escaped so user-provided names cannot inject markup.
    """
    body = str(body or "").strip()
    heading = f"<h4>{emoji} {rich_esc(str(title or 'Fiona'))}</h4>"
    return "\n".join((heading, body)) if body else heading


def richgram_notice_card(
    text: str,
    emoji: str | None = None,
    title: str = "Fiona",
) -> str:
    """Compose an enhanced Richgram heading and callout for Bot API 10.3 clients."""
    raw = str(text or "").strip()
    if emoji is None:
        emoji = next(
            (mark for mark in ("🚫", "❌", "⚠️", "⏰", "⏳", "🔄", "✅", "🎉", "📌", "🌸") if raw.startswith(mark)),
            "ℹ️",
        )
    body = raw[len(emoji):].lstrip() if raw.startswith(emoji) else raw
    return premium_text(
        f"<h4>{emoji} {rich_esc(title)}</h4><blockquote>{rich_esc(body)}</blockquote>"
    )


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


class _RichMessageRef:
    """Minimal editable reference when Richgram sends but message fetch fails."""

    def __init__(self, chat_id: int, message_id: int):
        self.chat = SimpleNamespace(id=chat_id)
        self.chat_id = chat_id
        self.id = message_id

    async def edit_text(self, text, reply_markup=None, **kwargs):
        return await edit_rich(self.chat_id, self.id, str(text), reply_markup=reply_markup)

    async def edit_caption(self, caption, reply_markup=None, **kwargs):
        return await edit_rich(self.chat_id, self.id, str(caption), reply_markup=reply_markup)

    async def edit_reply_markup(self, reply_markup=None, **kwargs):
        from AoiMusic import app as music_app

        try:
            await music_app.edit_message_reply_markup(
                self.chat_id, self.id, reply_markup=reply_markup
            )
            return True
        except Exception:
            return False


async def _send_rich_reply(message, content: str, reply_markup=None):
    """Send through the shared Richgram client and return an editable message ref."""
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    reply_to = getattr(message, "id", None) or getattr(message, "message_id", None)
    if not chat_id:
        return None
    try:
        message_id = await send_rich(
            chat_id,
            content,
            reply_markup=reply_markup,
            reply_to=reply_to,
        )
        if not message_id:
            return None
        try:
            client = getattr(message, "_client", None)
            if client is None:
                from AoiMusic import app as client
            fetched = await client.get_messages(chat_id, int(message_id))
            if fetched:
                return fetched
        except Exception:
            pass
        return _RichMessageRef(chat_id, int(message_id))
    except Exception:
        return None


async def send_panel(client, *args, **kwargs):
    """Send an outbound text panel through Richgram, with Bot API fallback."""
    if args:
        chat_id = args[0]
        content = args[1] if len(args) > 1 else kwargs.pop("text", "")
    else:
        chat_id = kwargs.pop("chat_id")
        content = kwargs.pop("text", kwargs.pop("content", ""))
    reply_markup = kwargs.pop("reply_markup", None)
    rich_message = None
    try:
        message_id = await send_rich(
            chat_id,
            premium_text(str(content or "")),
            reply_markup=reply_markup,
        )
        if message_id:
            try:
                rich_client = client if hasattr(client, "get_messages") else None
                if rich_client is None:
                    from AoiMusic import app as rich_client
                fetched = await rich_client.get_messages(chat_id, int(message_id))
                if fetched:
                    return fetched
            except Exception:
                pass
            rich_message = _RichMessageRef(chat_id, int(message_id))
    except Exception:
        pass
    if rich_message:
        return rich_message
    kwargs["reply_markup"] = reply_markup
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    kwargs.setdefault("disable_web_page_preview", True)
    return await client.send_message(chat_id=chat_id, text=content, **kwargs)


async def send_media_panel(client, *args, **kwargs):
    """Send an image-backed Richgram card, retaining media API fallback."""
    chat_id = kwargs.pop("chat_id", args[0] if args else None)
    media = kwargs.pop("photo", args[1] if len(args) > 1 else None)
    caption = kwargs.pop("caption", "")
    reply_markup = kwargs.pop("reply_markup", None)
    kwargs.pop("parse_mode", None)
    if media:
        try:
            import html

            body = f'<img src="{html.escape(str(media), quote=True)}"/>' + premium_text(caption)
            message_id = await send_rich(chat_id, body, reply_markup=reply_markup)
            if message_id:
                return _RichMessageRef(chat_id, int(message_id))
        except Exception:
            pass
    kwargs["reply_markup"] = reply_markup
    kwargs.setdefault("caption", caption)
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    return await client.send_photo(chat_id=chat_id, photo=media, **kwargs)


async def reply_panel(message, content: str | None = None, reply_markup=None, **kwargs):
    """Send a complete Fiona panel through Richgram, with safe Bot API fallback."""
    if content is None:
        content = kwargs.pop("text", "")
    rich_message = await _send_rich_reply(
        message,
        premium_text(str(content or "")),
        reply_markup=reply_markup,
    )
    if rich_message:
        return rich_message
    fallback_kwargs = dict(kwargs)
    fallback_kwargs["reply_markup"] = reply_markup
    fallback_kwargs.setdefault("parse_mode", ParseMode.HTML)
    fallback_kwargs.setdefault("disable_web_page_preview", True)
    try:
        return await message.reply_text(content, **fallback_kwargs)
    except Exception as exc:
        reason = str(exc).lower()
        if not any(token in reason for token in ("parse entities", "can't parse", "unsupported start tag", "can't find end tag")):
            raise
        fallback_kwargs.pop("parse_mode", None)
        return await message.reply_text(content, **fallback_kwargs)


async def reply_media_panel(
    message,
    media_url: str | None = None,
    caption: str = "",
    *,
    reply_markup=None,
    media_type: str = "photo",
    **kwargs,
):
    """Send an image-backed Richgram card; use Telegram media methods as fallback."""
    media_key = "video" if media_type == "video" else "photo"
    media_url = media_url or kwargs.pop(media_key, None)
    caption = kwargs.pop("caption", caption)
    kwargs.pop("parse_mode", None)
    if media_type == "photo" and media_url:
        import html

        media_tag = f'<img src="{html.escape(str(media_url), quote=True)}"/>'
        rich_message = await _send_rich_reply(
            message,
            media_tag + premium_text(caption),
            reply_markup=reply_markup,
        )
        if rich_message:
            return rich_message
    method = getattr(message, "reply_video" if media_type == "video" else "reply_photo")
    media_arg = {"video" if media_type == "video" else "photo": media_url}
    fallback_kwargs = dict(kwargs)
    fallback_kwargs.update(
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
    return await method(**media_arg, **fallback_kwargs)


async def reply_photo_panel(message, *args, **kwargs):
    """Richgram-enabled ``reply_photo`` drop-in for Fiona message handlers."""
    media_url = args[0] if args else kwargs.pop("photo", None)
    caption = kwargs.pop("caption", "")
    reply_markup = kwargs.pop("reply_markup", None)
    return await reply_media_panel(
        message,
        media_url,
        caption,
        reply_markup=reply_markup,
        media_type="photo",
        **kwargs,
    )


async def reply_video_panel(message, *args, **kwargs):
    """Keep video media native while routing its caption through Richgram."""
    media_url = args[0] if args else kwargs.pop("video", None)
    caption = kwargs.pop("caption", "")
    reply_markup = kwargs.pop("reply_markup", None)
    return await reply_media_panel(
        message,
        media_url,
        caption,
        reply_markup=reply_markup,
        media_type="video",
        **kwargs,
    )


async def reply_notice(
    message,
    text=None,
    *,
    emoji: str | None = None,
    title: str = "Fiona",
    **kwargs,
):
    """Reply with a native Richgram card; retain an editable safe fallback."""
    raw = str(text or "")
    markup = kwargs.get("reply_markup")
    rich_message = await _send_rich_reply(
        message,
        richgram_notice_card(raw, emoji=emoji, title=title),
        reply_markup=markup,
    )
    if rich_message:
        return rich_message

    rich_kwargs = dict(kwargs)
    rich_kwargs.setdefault("disable_web_page_preview", True)
    rich_kwargs["parse_mode"] = kwargs.get("parse_mode") or ParseMode.HTML
    return await message.reply_text(
        notice_card(raw, emoji=emoji, title=title),
        **rich_kwargs,
    )


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
