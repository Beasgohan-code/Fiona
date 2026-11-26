from pyrogram import filters
from pyrogram.types import Message

import config
from AoiMusic import app
from AoiMusic.utils.rich_msg import (
    pemoji,
    rich_esc,
    rich_heading,
    rich_url_button,
    rich_button_row,
    send_rich,
)


def privacy_html():
    parts = [
        rich_heading(f'{pemoji("🔒")} ᴘʀɪᴠᴀᴄʏ ᴢᴏɴᴇ', level=4),
        f"<p>{pemoji('🔒')} <b>{rich_esc(app.mention)}</b> ᴘʀɪᴠᴀᴄʏ ꜱᴇᴛᴜᴘ</p>",
    ]
    if config.PRIVACY_LINK:
        parts.append(f"<p>{pemoji('🔗')} <a href='{config.PRIVACY_LINK}'>ᴘʀɪᴠᴀᴄʏ ᴘᴏʟɪᴄʏ</a></p>")
    if config.SUPPORT_GROUP:
        parts.append(f"<p>{pemoji('💬')} <a href='{config.SUPPORT_GROUP}'>ꜱᴜᴘᴘᴏʀᴛ</a></p>")
    return "".join(parts)


@app.on_message(filters.command("privacy"))
async def privacy(client, message: Message):
    rows = []
    if config.PRIVACY_LINK:
        rows.append(rich_url_button("🔒 ᴠɪᴇᴡ ᴘᴏʟɪᴄʏ", config.PRIVACY_LINK))
    markup = rich_button_row(*rows) if rows else ""
    await send_rich(message.chat.id, privacy_html() + markup)
