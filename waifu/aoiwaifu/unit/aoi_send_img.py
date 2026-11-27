# ==============================================================================
# How to Use:
#   - Purpose: Manages weighted character spawning in groups with dynamic
#     MongoDB rarity toggles, weights, rarity spawn spacing, and temp spawn logs.
#   - Components: RARITY_WEIGHTS, pick_weighted_rarity, send_image, delete_message.
#   - Roots / Routes:
#       * Triggered by: massage.py message_counter when count >= ctime
#       * DB Collections: db.anime_characters_lol, db.blocked_character_drop_groups,
#         db.bot_dynamic_settings
#   - Usage: Imported by aoiwaifu/__init__.py and massage.py.
# ==============================================================================

from aoiwaifu import *
import random
import time
import asyncio
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import CallbackContext

log = "-1002155818429"
blocked_groups_collection = db["blocked_character_drop_groups"]

system_random = random.SystemRandom()

# Track recently spawned character IDs to prevent repeats across & within groups
recent_global_spawns = deque(maxlen=25)
recent_chat_spawns = defaultdict(lambda: deque(maxlen=15))


async def delete_message(chat_id, message_id, context):
    await asyncio.sleep(300)  # 5 minutes (300 seconds)
    try:
        await context.bot.delete_message(chat_id, message_id)
    except Exception as e:
        print(f"Error deleting message: {e}")


# Relative spawn weights mirror Summon-bot's default chance distribution.
# Fiona normalizes these against the rarities available in the catalog.
RARITY_WEIGHTS = {
    "⚪ Common": (4500.0, True),
    "🔵 Rare": (2500.0, True),
    "💮 Special Edition": (1200.0, True),
    "⭐ Legendary": (600.0, True),
    "🛸 Mythic Edition": (300.0, True),
    "💝 Valentine Edition": (50.0, True),
    "🏖️ Summer Edition": (50.0, True),
    "🌧️ Rainy Edition": (50.0, True),
    "🎃 Halloween Edition": (50.0, True),
    "🎄 Christmas Edition": (50.0, True),
    "❄️ Winter Edition": (50.0, True),
    "🎇 New Year Edition": (50.0, True),
    "🎍 Festival Edition": (40.0, True),
    "🎥 AMV Edition": (100.0, True),
    "🔞 Ecchi": (100.0, True),
    "🌌 Celestial Edition": (40.0, True),
    "💎 Luxury Edition": (30.0, True),
    "🔮 Limited Edition": (20.0, True),
}


def pick_weighted_rarity(rarities_list: list[str]) -> str:
    """Strictly selects a rarity based on exact cumulative percentage weights."""
    weights = [max(0.01, float(RARITY_WEIGHTS.get(r, (1.0, True))[0])) for r in rarities_list]
    total_weight = sum(weights)
    if total_weight <= 0:
        return rarities_list[0]
    roll = system_random.uniform(0, total_weight)
    cumulative = 0.0
    for rarity, weight in zip(rarities_list, weights):
        cumulative += weight
        if roll <= cumulative:
            return rarity
    return rarities_list[0]


async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    chat_title = getattr(update.effective_chat, "title", None) or f"Group {chat_id}"

    # Ensure dynamic MongoDB settings are loaded
