import os

from pyrogram.types import CallbackQuery

from aoiwaifu import *
from functools import wraps
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.aoi_parse_fix import SudoUsersHybrid

# Optional second account that bypasses every require_power() check, like
# OWNER_ID. Historically a hardcoded placeholder; set EXTRA_ADMIN_ID in the
# environment to enable it (0/empty disables it). `x` is kept as a
# backwards-compatible alias — older code imports it by that name.
EXTRA_ADMIN_ID = int(os.getenv("EXTRA_ADMIN_ID", "0") or 0)
x = EXTRA_ADMIN_ID

sudo_users = SudoUsersHybrid(db['sudo_users'], SUDO, OWNER_ID)

# Predefined powers
ALL_POWERS = [
    "add_character",  # Adds a new character
    "delete_character",  # Deletes a character
    "update_character",  # Updates an existing character
    "approve_request",  # Approves a request (e.g. user-submitted characters)
    "approve_inventory_request",  # Approves an inventory request (reserved)
    "VIP",  # Other staff commands (sudo management, backups, economy, ...)
]


def require_power(required_power):
    """Require one sudo power (or ANY of several) for a handler to run.

    `required_power` may be a single power name or an iterable of power
    names — pass a collection to accept holders of any of them, e.g.
    ``require_power(("add_character", "approve_request"))``.
    ``OWNER_ID`` and the optional ``EXTRA_ADMIN_ID`` bypass every check.
    """

    powers = (
        tuple(required_power)
        if isinstance(required_power, (set, list, tuple))
        else (required_power,)
    )
    power_label = " or ".join(powers)

    def decorator(func):
        @wraps(func)
        async def wrapper(client, message, *args, **kwargs):
            # Check if the message is a callback query or a regular message
            is_callback = isinstance(message, CallbackQuery)
            user_id = message.from_user.id
            if user_id == OWNER_ID or user_id == x:
                return await func(client, message, *args, **kwargs)

            user_data = await sudo_users.find_one({"_id": user_id})
            granted = (user_data or {}).get("powers", {})
            if granted and any(granted.get(power, False) for power in powers):
                return await func(client, message, *args, **kwargs)

            lang = await get_effective_lang(message)
            if is_callback:
                await message.answer(
                    tr(f"You do not have the {power_label} power required to use this button.", lang),
                    show_alert=True,
                )
            else:
                await message.reply_text(
                    tr(f"You do not have the <code>{power_label}</code> power required to use this command.", lang)
                )
            return None

        return wrapper

    return decorator

__all__ = ["ALL_POWERS", "require_power", "sudo_users", "EXTRA_ADMIN_ID", "x"]
