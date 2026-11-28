"""Owner-only, confirmation-gated Summon-compatible /removeall."""

import html
import time
import uuid

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup

from aoiwaifu import OWNER_ID, app, user_collection
from aoiwaifu.unit.rich_ui import edit_panel, premium_button, rich_card, reply_notice, reply_panel

_PENDING = {}
_PENDING_TTL = 5 * 60


def _prune_pending():
    now = time.monotonic()
    for token, data in list(_PENDING.items()):
        if now - data["created"] > _PENDING_TTL:
            _PENDING.pop(token, None)


@app.on_message(filters.command(["removeall"]))
async def request_remove_all(client, message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        await reply_notice(message, "This harem reset is restricted to the bot owner.")
        return
    if len(message.command or []) != 2 or not message.command[1].isdigit():
        await reply_panel(
            message,
            rich_card("Collection reset", "Usage: <code>/removeall &lt;user_id&gt;</code>", "🧹"),
        )
        return

    target_id = int(message.command[1])
    if target_id <= 0:
        await reply_notice(message, "Please provide a valid positive user ID.")
        return
    user = await user_collection.find_one(
        {"id": target_id},
        {"characters": 1, "first_name": 1, "username": 1},
    )
    if not user:
        await reply_notice(message, "No Fiona collector profile was found for that user ID.")
        return

    _prune_pending()
    token = uuid.uuid4().hex[:12]
    _PENDING[token] = {
        "created": time.monotonic(),
        "owner_id": message.from_user.id,
        "target_id": target_id,
        "chat_id": message.chat.id,
    }
    name = html.escape(str(user.get("first_name") or (f"@{user['username']}" if user.get("username") else "Unknown")))
    character_count = len(user.get("characters", []) or [])
    keyboard = InlineKeyboardMarkup([
        [
            premium_button("Confirm reset", emoji="CHECK_CIRCLE", style="DANGER", callback_data=f"removeall:confirm:{token}"),
            premium_button("Cancel", emoji="CLOSE", style="PRIMARY", callback_data=f"removeall:cancel:{token}"),
        ]
    ])
    await reply_panel(
        message,
        rich_card(
            "Confirm collection reset",
            f"<b>Collector:</b> {name} (<code>{target_id}</code>)\n"
            f"<b>Copies to remove:</b> <code>{character_count}</code>\n\n"
            "This only clears their character collection; coins, tokens, profile, and daily history stay intact."
            " This confirmation expires in five minutes.",
            "⚠️",
        ),
        reply_markup=keyboard,
    )


@app.on_callback_query(filters.regex(r"^removeall:(confirm|cancel):([a-f0-9]{12})$"))
async def resolve_remove_all(client, callback_query):
    action, token = callback_query.matches[0].group(1, 2)
    pending = _PENDING.get(token)
    if not pending or time.monotonic() - pending["created"] > _PENDING_TTL:
        _PENDING.pop(token, None)
        await callback_query.answer("This confirmation expired. Run /removeall again.", show_alert=True)
        return
    if callback_query.from_user.id != pending["owner_id"]:
        await callback_query.answer("Only the bot owner who opened this confirmation can use it.", show_alert=True)
        return
    if callback_query.message.chat.id != pending["chat_id"]:
        await callback_query.answer("This confirmation belongs to another chat.", show_alert=True)
        return

    _PENDING.pop(token, None)
    await callback_query.answer()
    if action == "cancel":
        await edit_panel(
            callback_query.message,
            rich_card("Collection reset cancelled", "No collector data was changed.", "✅"),
            reply_markup=None,
        )
        return

    target_id = pending["target_id"]
    user = await user_collection.find_one({"id": target_id}, {"characters": 1})
    if not user:
        await edit_panel(
            callback_query.message,
            rich_card("Collector not found", "No collection was changed.", "⚠️"),
            reply_markup=None,
        )
        return
    removed = len(user.get("characters", []) or [])
    await user_collection.update_one({"id": target_id}, {"$set": {"characters": []}})
    await edit_panel(
        callback_query.message,
        rich_card(
            "Collection cleared",
            f"Removed <code>{removed}</code> character copies from collector <code>{target_id}</code>.\n"
            "Their coins, tokens, profile, and daily history were preserved.",
            "🗑️",
        ),
        reply_markup=None,
    )
