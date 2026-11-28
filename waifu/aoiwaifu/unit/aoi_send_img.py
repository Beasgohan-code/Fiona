# ==============================================================================
# How to Use:
#   - Purpose: Manages weighted character spawning in groups with dynamic
#     MongoDB rarity settings and duplicate-avoidance windows.
#   - Components: RARITY_WEIGHTS, pick_weighted_rarity, spawn_character, send_image.
#   - Spawn state is shared with modules/guess.py via last_characters.
# ==============================================================================

from aoiwaifu import *
import asyncio
import html
import logging
import random
import time
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import CallbackContext

from aoiwaifu.unit.rich_ui import premium_text, rich_card, send_media_panel, send_panel

logger = logging.getLogger(__name__)
system_random = random.SystemRandom()
SPAWN_TIMEOUT_SECONDS = 120

# Relative weights mirror Summon-bot's default distribution. The second value
# lets the owner disable a rarity from automatic drops without hiding it from
# the catalog, collection, or manual /spawn.
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

# Track recent character IDs to avoid repeats within a chat and across groups.
recent_global_spawns = deque(maxlen=25)
recent_chat_spawns = defaultdict(lambda: deque(maxlen=15))


def pick_weighted_rarity(rarities_list: list[str]) -> str:
    """Pick an enabled rarity by relative weight, or an empty string if none."""
    active = []
    for rarity in rarities_list:
        weight, enabled = RARITY_WEIGHTS.get(rarity, (1.0, True))
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            continue
        if enabled and weight > 0:
            active.append((rarity, weight))
    if not active:
        return ""

    roll = system_random.uniform(0, sum(weight for _, weight in active))
    cumulative = 0.0
    for rarity, weight in active:
        cumulative += weight
        if roll <= cumulative:
            return rarity
    return active[-1][0]


async def _sample_character(query: dict, recent_ids: list):
    """Sample one catalog entry, preferring characters not recently spawned."""
    base_query = dict(query)
    if recent_ids:
        with_history = {**base_query, "_id": {"$nin": recent_ids}}
        matches = await collection.aggregate([
            {"$match": with_history},
            {"$sample": {"size": 1}},
        ]).to_list(length=1)
        if matches:
            return matches[0]
    matches = await collection.aggregate([
        {"$match": base_query},
        {"$sample": {"size": 1}},
    ]).to_list(length=1)
    return matches[0] if matches else None


_spawn_weights_loaded = False


async def load_spawn_weight_overrides() -> None:
    """Load owner-configured rarity weights once, preserving catalog defaults."""
    global _spawn_weights_loaded
    if _spawn_weights_loaded:
        return
    try:
        cursor = db["spawn_rarity_chances"].find({})
        overrides = await cursor.to_list(length=None)
        for item in overrides:
            rarity = item.get("rarity")
            if not rarity:
                continue
            try:
                weight = max(0.0, float(item.get("weight", 0)))
            except (TypeError, ValueError):
                continue
            enabled = bool(item.get("enabled", weight > 0)) and weight > 0
            RARITY_WEIGHTS[rarity] = (weight, enabled)
        _spawn_weights_loaded = True
    except Exception:
        logger.exception("Could not load custom rarity spawn weights; using built-in defaults")
        _spawn_weights_loaded = True


async def set_spawn_weight(rarity_id: int, rarity: str, weight: int, updated_by: int) -> None:
    """Persist and immediately apply an owner-configured auto-spawn weight."""
    global _spawn_weights_loaded
    enabled = weight > 0
    await db["spawn_rarity_chances"].update_one(
        {"rarity_id": int(rarity_id)},
        {"$set": {
            "rarity_id": int(rarity_id),
            "rarity": rarity,
            "weight": int(weight),
            "enabled": enabled,
            "updated_by": int(updated_by),
            "updated_at": time.time(),
        }},
        upsert=True,
    )
    RARITY_WEIGHTS[rarity] = (float(weight), enabled)
    _spawn_weights_loaded = True


async def _choose_character(chat_id: int, manual: bool = False):
    """Choose a random manual-spawn character or a weighted auto-spawn one."""
    recent_ids = list(recent_global_spawns) + list(recent_chat_spawns[chat_id])
    if manual:
        return await _sample_character({}, recent_ids)

    await load_spawn_weight_overrides()
    rarities = await collection.distinct("rarity")
    active_rarities = [
        rarity for rarity in rarities
        if RARITY_WEIGHTS.get(rarity, (1.0, True))[1]
        and float(RARITY_WEIGHTS.get(rarity, (1.0, True))[0]) > 0
    ]
    rarity = pick_weighted_rarity(active_rarities)
    if rarity:
        character = await _sample_character({"rarity": rarity}, recent_ids)
        if character:
            return character

    # A rarity may be configured but have no usable records. Fall back safely
    # to any available catalog character rather than silently losing the drop.
    return await _sample_character({}, recent_ids)


async def _expire_spawn(bot, chat_id: int, spawn_token: str) -> None:
    """Mark an unclaimed character as escaped after the catch window closes."""
    await asyncio.sleep(SPAWN_TIMEOUT_SECONDS)
    current = last_characters.get(chat_id)
    if (
        not current
        or current.get("spawn_token") != spawn_token
        or current.get("ranaway")
        or chat_id in first_correct_guesses
    ):
        return

    current["ranaway"] = True
    try:
        await send_panel(
            bot,
            chat_id=chat_id,
            text=rich_card(
                "Character escaped",
                "<blockquote>The catch window closed before anyone caught this character.</blockquote>\n"
                "Keep chatting to trigger the next round.",
                "⏰",
            ),
        )
    except Exception as exc:
        logger.warning("Could not post character escape notice in %s: %s", chat_id, exc)


async def spawn_character(bot, chat_id: int, *, manual: bool = False) -> str:
    """Create and post a character round, returning a small status for callers."""
    if await db["blocked_character_drop_groups"].find_one({"_id": chat_id}):
        return "blocked"

    active = last_characters.get(chat_id)
    if active and not active.get("ranaway") and chat_id not in first_correct_guesses:
        return "active"

    character = await _choose_character(chat_id, manual=manual)
    if not character:
        logger.warning("No character records are available for a spawn in %s", chat_id)
        return "empty"

    char_id = character.get("id", character.get("_id"))
    spawn_token = f"{chat_id}:{char_id}:{time.time_ns()}"
    last_characters[chat_id] = {
        "id": character.get("id"),
        "name": str(character.get("name") or "Unknown"),
        "anime": str(character.get("anime") or "Unknown"),
        "rarity": str(character.get("rarity") or "Unknown"),
        "img_url": character.get("img_url") or character.get("image") or character.get("url"),
        "timestamp": time.time(),
        "message_id": None,
        "ranaway": False,
        "spawn_token": spawn_token,
    }
    first_correct_guesses.pop(chat_id, None)

    spawned = last_characters[chat_id]
    caption = premium_text(rich_card(
        "A character appeared!",
        "<blockquote>"
        f"🎌 <b>Anime:</b> {html.escape(spawned['anime'])}\n"
        f"💎 <b>Rarity:</b> {html.escape(spawned['rarity'])}"
        "</blockquote>\n"
        "Be the first to catch it with <code>/guess &lt;name&gt;</code> or <code>/summon &lt;name&gt;</code>.",
        "🌠",
    ))
    photo = spawned.get("img_url")
    sent = None
    try:
        if photo:
            sent = await send_media_panel(
                bot,
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode="html",
            )
        else:
            sent = await send_panel(bot, chat_id=chat_id, text=caption, parse_mode="html")
    except Exception as exc:
        logger.warning("Character media send failed in %s; trying text fallback: %s", chat_id, exc)
        try:
            sent = await bot.send_message(chat_id=chat_id, text=caption, parse_mode="html")
        except Exception:
            logger.exception("Could not post character spawn in %s", chat_id)
            if last_characters.get(chat_id, {}).get("spawn_token") == spawn_token:
                last_characters.pop(chat_id, None)
            return "failed"

    spawned["message_id"] = getattr(sent, "message_id", None) or getattr(sent, "id", None)
    recent_global_spawns.append(character.get("_id", char_id))
    recent_chat_spawns[chat_id].append(character.get("_id", char_id))
    asyncio.create_task(
        _expire_spawn(bot, chat_id, spawn_token),
        name=f"expire_session_{chat_id}",
    )
    return "spawned"


async def send_image(update: Update, context: CallbackContext) -> None:
    """Automatic message-threshold spawn entry point used by massage.py."""
    chat = update.effective_chat
    if not chat:
        return
    try:
        result = await spawn_character(context.bot, chat.id)
    except Exception:
        logger.exception("Automatic character spawn failed in %s", chat.id)
        return
    if result not in ("spawned", "active", "blocked"):
        logger.warning("Automatic spawn in %s ended with status %s", chat.id, result)
