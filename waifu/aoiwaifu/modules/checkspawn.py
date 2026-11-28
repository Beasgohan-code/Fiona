"""Summon-compatible /checkspawn status for Fiona's group message threshold."""

from aoiwaifu.unit.rich_ui import (
    reply_panel,
    premium_text,
    rich_showcase_panel,
)
from html import escape

from pyrogram import enums, filters

from aoiwaifu import (
    app,
    db,
    first_correct_guesses,
    group_ctimes,
    group_user_totals_collection,
    last_characters,
    normal_message_counts,
)
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr

_DEFAULT_SPAWN_LIMIT = 80


def _spawn_progress(current_count, spawn_limit):
    """Clamp cached counter values and return (count, limit, remaining, percent)."""
    try:
        limit = max(1, int(spawn_limit))
    except (TypeError, ValueError):
        limit = _DEFAULT_SPAWN_LIMIT
    try:
        count = max(0, int(current_count or 0))
    except (TypeError, ValueError):
        count = 0
    count = min(count, limit)
    remaining = max(0, limit - count)
    percent = min(100, int(count * 100 / limit))
    return count, limit, remaining, percent


@app.on_message(filters.command(["checkspawn"]) & filters.group)
async def check_spawn_status(client, message):
    """Show the chat's configured message threshold and live counter state."""
    chat_id = message.chat.id
    chat_key = str(chat_id)
    lang = await get_effective_lang(message)

    spawn_limit = group_ctimes.get(chat_key)
    if spawn_limit is None:
        settings = await group_user_totals_collection.find_one(
            {"group_id": chat_key},
            {"_id": 0, "ctime": 1},
        )
        spawn_limit = (settings or {}).get("ctime", _DEFAULT_SPAWN_LIMIT)
    current_count, spawn_limit, remaining, percent = _spawn_progress(
        normal_message_counts.get(chat_key, 0), spawn_limit
    )

    blocked = await db["blocked_character_drop_groups"].find_one({"_id": chat_id})
    current_character = last_characters.get(chat_id)
    if not current_character:
        round_state = "No active character round"
    elif chat_id in first_correct_guesses:
        round_state = "Current character already caught"
    elif current_character.get("ranaway"):
        round_state = "Current character round expired"
    else:
        round_state = "A character round is active"

    availability = "Catching is disabled for this group" if blocked else "Catching is enabled"
    progress = "▰" * min(10, percent // 10) + "▱" * (10 - min(10, percent // 10))
    body = (
        "<blockquote>"
        f"<b>Group:</b> {escape(message.chat.title or str(chat_id))}\n"
        f"<b>Status:</b> {escape(availability)}\n"
        f"<b>Messages counted:</b> <code>{current_count}/{spawn_limit}</code>\n"
        f"<b>Until next configured trigger:</b> <code>{remaining}</code> messages\n"
        f"<b>Progress:</b> {progress} <code>{percent}%</code>\n"
        f"<b>Catch round:</b> {escape(round_state)}"
        "</blockquote>\n"
        "<i>The message counter is held in memory and resets after a trigger or bot restart.</i>"
    )
    await reply_panel(message,
        premium_text(tr(rich_showcase_panel("Group spawn status", body, "📊"), lang)),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )
