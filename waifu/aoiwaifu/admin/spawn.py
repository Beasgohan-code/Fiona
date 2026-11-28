"""Owner-only manual character spawn, compatible with Summon's /spawn."""

from aoiwaifu.unit.rich_ui import (
    reply_notice,
)
from pyrogram import filters

from aoiwaifu import OWNER_ID, app
from aoiwaifu.unit.aoi_send_img import spawn_character
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr


@app.on_message(filters.command(["spawn"]) & filters.group)
async def manual_spawn(client, message):
    lang = await get_effective_lang(message)
    if not message.from_user or message.from_user.id != OWNER_ID:
        await reply_notice(message, tr("This manual spawn command is restricted to the bot owner.", lang))
        return

    try:
        result = await spawn_character(client, message.chat.id, manual=True)
    except Exception:
        await reply_notice(message, tr("Manual spawn failed. Check the database and bot permissions.", lang))
        return
    messages = {
        "active": "There is already an uncaught character in this group.",
        "blocked": "Character drops are disabled for this group.",
        "empty": "There are no characters available to spawn.",
        "failed": "The character could not be sent. Check the bot's permissions and character image URL.",
    }
    if result in messages:
        await reply_notice(message, tr(messages[result], lang))
