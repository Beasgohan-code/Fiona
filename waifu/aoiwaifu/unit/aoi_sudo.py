import os

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, CallbackQuery
from aoiwaifu import *
from functools import wraps
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr

# Optional second account that bypasses every require_power() check, like
# OWNER_ID. Historically a hardcoded placeholder; set EXTRA_ADMIN_ID in the
# environment to enable it (0/empty disables it).
x = int(os.getenv("EXTRA_ADMIN_ID", "0") or 0)
from aoiwaifu.unit.aoi_parse_fix import SudoUsersHybrid
sudo_users = SudoUsersHybrid(db['sudo_users'], SUDO, OWNER_ID)

# Predefined powers
ALL_POWERS = [
    "add_character",  # Adds a new character
    "delete_character",  # Deletes a character
    "update_character",  # Updates an existing character
    "approve_request",  # Approves a request
    "approve_inventory_request",  # Approves an inventory request
    "VIP"
]

def require_power(required_power):
    def decorator(func):
        @wraps(func)
        async def wrapper(client, message, *args, **kwargs):
            lang = await get_effective_lang(message)
            # Check if the message is a callback query or a regular message
            if isinstance(message, CallbackQuery):
                user_id = message.from_user.id
                if user_id == OWNER_ID or user_id == x:
                    return await func(client, message, *args, **kwargs)

                user_data = await sudo_users.find_one({"_id": user_id})
                if not user_data or not user_data.get("powers", {}).get(required_power, False):
                    await message.answer(
                        tr(f"You do not have the {required_power} power required to use this button.", lang),
                        show_alert=True,
                    )
                    return
                return await func(client, message, *args, **kwargs)

            # Regular message handling
            user_id = message.from_user.id
            if user_id == OWNER_ID or user_id == x:
                return await func(client, message, *args, **kwargs)

            user_data = await sudo_users.find_one({"_id": user_id})
            if not user_data or not user_data.get("powers", {}).get(required_power, False):
                await message.reply_text(
                    tr(f"You do not have the <code>{required_power}</code> power required to use this command.", lang)
                )
                return
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator
