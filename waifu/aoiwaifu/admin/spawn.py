"""Owner-only manual character spawn, compatible with Summon's /spawn."""

from pyrogram import enums, filters

from aoiwaifu import OWNER_ID, app
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.aoi_send_img import spawn_character
from aoiwaifu.unit.rich_ui import premium_text, rich_showcase_panel, reply_notice, reply_panel


@app.on_message(filters.command(["spawn"]) & filters.group)
async def manual_spawn(client, message):
    lang = await get_effective_lang(message)
    if not message.from_user or message.from_user.id != OWNER_ID:
        await reply_notice(message, tr("This manual spawn command is restricted to the bot owner.", lang))
        return

    try:
        result = await spawn_character(client, message.chat.id, manual=True)
    except Exception:
        await reply_panel(
            message,
            premium_text(rich_showcase_panel(
                "Manual spawn failed",
                "<blockquote>Check the catalog connection and bot permissions, then try again.</blockquote>",
                "⚠️",
            )),
            parse_mode=enums.ParseMode.HTML,
        )
        return

    messages = {
        "active": "There is already an uncaught character in this group.",
        "blocked": "Character drops are disabled for this group.",
        "empty": "There are no characters available to spawn.",
        "failed": "The character could not be sent. Check the bot's permissions and character image URL.",
    }
    if result == "spawned":
        await reply_panel(
            message,
            premium_text(rich_showcase_panel(
                "Manual spawn launched",
                "<blockquote>A new character round has been posted. Be quick and catch it!</blockquote>",
                "🎯",
            )),
            parse_mode=enums.ParseMode.HTML,
        )
    elif result in messages:
        await reply_panel(
            message,
            premium_text(rich_showcase_panel(
                "Manual spawn unavailable",
                f"<blockquote>{tr(messages[result], lang)}</blockquote>",
                "⚠️",
            )),
            parse_mode=enums.ParseMode.HTML,
        )
