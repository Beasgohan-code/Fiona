"""Waifu group registry helpers called by Music's unified membership handler."""
from datetime import datetime, timezone

from aoiwaifu import db, LOGGER

game_active_groups_col = db["game_active_groups"]


async def mark_group_active(chat) -> bool:
    """Record that Fiona is active in this group."""
    chat_id = int(chat.id)
    try:
        await game_active_groups_col.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "chat_title": chat.title or f"Chat {chat_id}",
                    "chat_username": getattr(chat, "username", None),
                    "active": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        LOGGER("Waifu.JoinLog").warning(
            "Could not mark group %s active (%s).", chat_id, type(exc).__name__
        )
        return False


async def mark_group_inactive(chat_id: int) -> bool:
    """Record that Fiona has left or been removed from this group."""
    chat_id = int(chat_id)
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
        return True
    except Exception as exc:
        LOGGER("Waifu.JoinLog").warning(
            "Could not mark group %s inactive (%s).", chat_id, type(exc).__name__
        )
        return False


__all__ = ["mark_group_active", "mark_group_inactive"]
