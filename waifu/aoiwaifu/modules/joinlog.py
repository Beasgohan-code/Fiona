"""Keep Waifu's active-group registry in sync with bot membership events."""
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import Message

from aoiwaifu import app, db, LOGGER
from aoiwaifu.unit.event_logger import send_event_log

game_active_groups_col = db["game_active_groups"]


async def send_log_message(chat_id: int | str | None, message: str) -> bool:
    """Backward-compatible best-effort logger for Waifu modules."""
    return await send_event_log(app, chat_id, message, logger_name="Waifu.JoinLog")


@app.on_message(filters.new_chat_members)
async def on_new_chat_members(client: Client, message: Message):
    """Mark a group active when Fiona itself is added; ignore regular joins."""
    bot_user = await client.get_me()
    if not any(
        getattr(user, "id", None) == bot_user.id
        for user in (message.new_chat_members or [])
    ):
        return

    chat_id = int(message.chat.id)
    try:
        await game_active_groups_col.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "chat_title": message.chat.title or f"Chat {chat_id}",
                    "chat_username": getattr(message.chat, "username", None),
                    "active": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        LOGGER("Waifu.JoinLog").warning(
            "Could not mark group %s active (%s).", chat_id, type(exc).__name__
        )


@app.on_message(filters.left_chat_member)
async def on_left_chat_member(client: Client, message: Message):
    """Mark a group inactive when Fiona itself is removed or leaves."""
    left_member = message.left_chat_member
    if not left_member:
        return
    bot_user = await client.get_me()
    if getattr(left_member, "id", None) != bot_user.id:
        return

    chat_id = int(message.chat.id)
    try:
        await game_active_groups_col.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "active": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
    except Exception as exc:
        LOGGER("Waifu.JoinLog").warning(
            "Could not mark group %s inactive (%s).", chat_id, type(exc).__name__
        )
