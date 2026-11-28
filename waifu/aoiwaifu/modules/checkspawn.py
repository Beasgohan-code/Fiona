"""Summon-compatible interactive /checkspawn status dashboard."""

from html import escape

from pyrogram import enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup

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
from aoiwaifu.unit.rich_ui import (
    edit_panel,
    premium_button,
    premium_text,
    reply_panel,
    rich_showcase_panel,
)

_DEFAULT_SPAWN_LIMIT = 80


def _spawn_progress(current_count, spawn_limit):
    """Clamp cached counter values and return (count, limit, remaining, percent)."""
    try:
        limit = max(1, int(spawn_limit))
    except (TypeError, ValueError, OverflowError):
        limit = _DEFAULT_SPAWN_LIMIT
    try:
        count = max(0, int(current_count or 0))
    except (TypeError, ValueError, OverflowError):
        count = 0
    count = min(count, limit)
    remaining = max(0, limit - count)
    percent = min(100, int(count * 100 / limit))
    return count, limit, remaining, percent


def _refresh_keyboard(chat_id):
    return InlineKeyboardMarkup([[
        premium_button(
            "Refresh live progress",
            emoji="REFRESH",
            callback_data=f"checkspawn:refresh:{chat_id}",
        )
    ]])


async def _build_spawn_status(chat_id, chat_title, lang):
    """Build one current Richgram status view for a group spawn round."""
    chat_key = str(chat_id)
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
    filled = min(10, percent // 10)
    progress = "▰" * filled + "▱" * (10 - filled)
    body = (
        "<blockquote>"
        f"<b>Group</b> · {escape(chat_title or str(chat_id))}\n"
        f"<b>Status</b> · {escape(availability)}\n"
        f"<b>Messages counted</b> · <code>{current_count}/{spawn_limit}</code>\n"
        f"<b>Until next trigger</b> · <code>{remaining}</code> messages\n"
        f"<b>Progress</b> · {progress} <code>{percent}%</code>\n"
        f"<b>Catch round</b> · {escape(round_state)}"
        "</blockquote>"
        "<p><i>Tap refresh to read the latest in-memory counter. It resets after a spawn trigger or bot restart.</i></p>"
    )
    return premium_text(tr(rich_showcase_panel("GROUP SPAWN STATUS", body, "📊"), lang))


@app.on_message(filters.command(["checkspawn"]) & filters.group)
async def check_spawn_status(client, message):
    """Show and refresh the chat's configured threshold and live counter state."""
    lang = await get_effective_lang(message)
    panel = await _build_spawn_status(message.chat.id, message.chat.title, lang)
    await reply_panel(
        message,
        panel,
        reply_markup=_refresh_keyboard(message.chat.id),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


@app.on_callback_query(filters.regex(r"^checkspawn:refresh:(-?\d+)$"))
async def refresh_spawn_status(client, callback_query: CallbackQuery):
    """Update the current group's status card in place after callback checks."""
    try:
        target_chat_id = int(callback_query.matches[0].group(1))
    except (IndexError, TypeError, ValueError):
        await callback_query.answer("This status panel is invalid. Run /checkspawn again.", show_alert=True)
        return

    if not callback_query.message or callback_query.message.chat.id != target_chat_id:
        await callback_query.answer("This status panel belongs to another group.", show_alert=True)
        return

    await callback_query.answer()
    lang = await get_effective_lang(callback_query)
    panel = await _build_spawn_status(
        target_chat_id,
        callback_query.message.chat.title,
        lang,
    )
    await edit_panel(
        callback_query.message,
        panel,
        _refresh_keyboard(target_chat_id),
    )
