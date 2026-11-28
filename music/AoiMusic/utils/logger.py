import html

#
# Logger play-log — classic tree card, sent as photo (thumbnail) + caption.

from pyrogram.enums import ParseMode

from config import LOG, LOGGER_ID
from AoiMusic import app
from AoiMusic.utils.database import is_on_off


def _or_dash(value):
    value = str(value or "").strip()
    return value if value else "—"


async def play_logs(message, streamtype, thumbnail=None):
    if not await is_on_off(LOG):
        return
    if message.chat.id == LOGGER_ID:
        return

    user = message.from_user
    try:
        query = message.text.split(None, 1)[1]
    except Exception:
        query = message.text or "N/A"
    query = _or_dash(query)[:120]

    if message.chat.username:
        username = f"@{message.chat.username}"
        chat_link = f"https://t.me/{message.chat.username}"
        chat_name = (
            f'<a href="{chat_link}">'
            f"{html.escape(str(message.chat.title or 'Unknown'))}</a>"
        )
    else:
        username = "—"
        chat_name = html.escape(str(message.chat.title or "Private Group"))

    bot_name = html.escape(str(getattr(app, "name", None) or "AoiMusic"))

    text = (
        f"🎵 <b>{bot_name} play log</b>\n\n"
        "🏰 <b>Chat info</b>\n"
        f"• Chat: {chat_name}\n"
        f"• Chat ID: <code>{_or_dash(message.chat.id)}</code>\n"
        f"• Username: {html.escape(str(username))}\n\n"
        "👤 <b>Requested by</b>\n"
        f"• Name: {user.mention}\n"
        f"• User ID: <code>{_or_dash(user.id)}</code>\n"
        f"• Username: {html.escape('@' + str(user.username)) if user.username else '—'}\n\n"
        "🎶 <b>Track details</b>\n"
        f"• Query: {html.escape(str(query))}\n"
        f"• Stream: {html.escape(str(streamtype))}\n\n"
        "⚡ Mode: Direct stream · Premium UI"
    )

    if thumbnail and str(thumbnail).startswith(("http://", "https://")):
        try:
            await app.send_photo(
                LOGGER_ID,
                photo=str(thumbnail),
                caption=text,
                parse_mode=ParseMode.HTML,
            )
            return
        except Exception:
            pass
    try:
        await app.send_message(LOGGER_ID, text, parse_mode=ParseMode.HTML)
    except Exception:
        pass
