from aoiwaifu.unit.rich_ui import (
    reply_photo_panel,
    reply_panel,
    premium_button,
    premium_text,
    rich_card,
    rich_table,
    reply_notice,
)
# ==============================================================================
# How to Use:
#   - Purpose: Daily character claim handler (/claim, /hclaim) using dynamic
#     MongoDB-configured claimable rarities.
#   - Components: format_time_delta, get_unique_characters, mclaim.
#   - Roots / Routes:
#       * Commands: /claim, /hclaim
#       * DB Collections: db.user_collection_lmaoooo, db.anime_characters_lol,
#         db.bot_dynamic_settings
#   - Usage: Loaded automatically by aoiwaifu/__main__.py.
# ==============================================================================

from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
import asyncio
import html
import random
from pyrogram import Client, filters, types as t_types
from pyrogram.types import InlineKeyboardMarkup
from datetime import datetime, timedelta
from aoiwaifu import ZYRO as bot
from aoiwaifu import user_collection, collection, user_guess_progress, SUPPORT_CHAT_ID as chat, SUPPORT_CHAT, db, rarity_map

claim_lock = {}


async def format_time_delta(delta):
    seconds = delta.total_seconds()
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{int(hours)}h {int(minutes)}m {int(seconds)}s' if hours or minutes or seconds else '0s'


DEFAULT_CLAIM_WEIGHTS = {
    1: 400.0, 2: 0.0, 3: 1200.0, 4: 600.0, 5: 300.0, 6: 50.0,
    7: 50.0, 8: 50.0, 9: 50.0, 10: 0.0, 11: 2.0, 12: 50.0,
    13: 40.0, 14: 0.0, 15: 100.0, 16: 40.0, 17: 0.0, 18: 20.0,
}
claim_rarity_weights = dict(DEFAULT_CLAIM_WEIGHTS)
_claim_weights_loaded = False


def pick_claim_rarity(available_ids, weights, rng=None):
    """Weighted-pick a claim rarity from the available, enabled IDs."""
    choices = sorted(
        (int(rarity_id), max(0.0, float(weights.get(int(rarity_id), 0))))
        for rarity_id in available_ids
        if max(0.0, float(weights.get(int(rarity_id), 0))) > 0
    )
    if not choices:
        return None
    rng = rng or random.SystemRandom()
    return rng.choices([item[0] for item in choices], weights=[item[1] for item in choices], k=1)[0]


async def load_claim_rarity_weights():
    """Apply persisted owner overrides on top of Summon-compatible defaults."""
    global _claim_weights_loaded
    if _claim_weights_loaded:
        return
    try:
        documents = await db["claim_rarity_chances"].find({}).to_list(length=None)
        for document in documents:
            rarity_id = int(document.get("rarity_id", 0))
            if rarity_id not in rarity_map:
                continue
            weight = max(0.0, float(document.get("weight", 0)))
            claim_rarity_weights[rarity_id] = weight
    except Exception as exc:
        print(f"Could not load claim rarity weights; using defaults: {exc}")
    _claim_weights_loaded = True


async def set_claim_rarity_weight(rarity_id: int, weight: float, updated_by: int):
    """Persist one claim rarity weight and apply it without restarting Fiona."""
    global _claim_weights_loaded
    rarity_id = int(rarity_id)
    weight = float(weight)
    await db["claim_rarity_chances"].update_one(
        {"rarity_id": rarity_id},
        {"$set": {
            "rarity_id": rarity_id,
            "rarity": rarity_map[rarity_id],
            "weight": weight,
            "enabled": weight > 0,
            "updated_by": int(updated_by),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    claim_rarity_weights[rarity_id] = weight
    _claim_weights_loaded = True


async def get_unique_characters(user_id, target_rarities=None):
    """Choose an unowned claimable character using the configured rarity weights."""
    try:
        await load_claim_rarity_weights()
        user_data = await user_collection.find_one({"id": user_id}, {"characters.id": 1}) or {}
        claimed_ids = [
            char["id"] for char in user_data.get("characters", [])
            if isinstance(char, dict) and "id" in char
        ]

        allowed_ids = [
            rarity_id for rarity_id, rarity in rarity_map.items()
            if target_rarities is None or rarity in target_rarities
        ]
        enabled_ids = [
            rarity_id for rarity_id in allowed_ids
            if claim_rarity_weights.get(rarity_id, 0) > 0
        ]
        enabled_rarities = [rarity_map[rarity_id] for rarity_id in enabled_ids]
        if not enabled_rarities:
            return []

        available_unclaimed = await collection.distinct(
            "rarity",
            {"rarity": {"$in": enabled_rarities}, "id": {"$nin": claimed_ids}},
        )
        available_ids = [
            rarity_id for rarity_id in enabled_ids
            if rarity_map[rarity_id] in available_unclaimed
        ]
        unique_only = bool(available_ids)
        if not unique_only:
            available_any = await collection.distinct(
                "rarity", {"rarity": {"$in": enabled_rarities}}
            )
            available_ids = [
                rarity_id for rarity_id in enabled_ids
                if rarity_map[rarity_id] in available_any
            ]
        rarity_id = pick_claim_rarity(available_ids, claim_rarity_weights)
        if rarity_id is None:
            return []

        match = {"rarity": rarity_map[rarity_id]}
        if unique_only:
            match["id"] = {"$nin": claimed_ids}
        return await collection.aggregate([
            {"$match": match},
            {"$sample": {"size": 1}},
        ]).to_list(length=1)
    except Exception as exc:
        print(f"Error retrieving claim character: {exc}")
        return []


@bot.on_message(filters.command(['hclaim', 'claim']))
async def mclaim(_, message: t_types.Message):
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    mention = message.from_user.mention
    target_chat = str(chat or '').strip()
    if target_chat and str(message.chat.id) != target_chat:
        reply_markup = None
        if SUPPORT_CHAT:
            reply_markup = InlineKeyboardMarkup([[
                premium_button('Join support group', emoji='CHAT_BUBBLE', style='PRIMARY', url=SUPPORT_CHAT)
            ]])
        return await reply_panel(message,
            premium_text(rich_card('Daily claim', 'Claims are available in the configured support group.', '🔔')),
            reply_markup=reply_markup,
            parse_mode='html',
        )
    if user_id in claim_lock:
        await reply_notice(message, tr('Your claim request is already being processed. Please wait.', lang))
        return
    claim_lock[user_id] = True
    try:
        user_data = await user_collection.find_one({'id': user_id})
        if not user_data:
            user_data = {'id': user_id, 'username': message.from_user.username, 'first_name': message.from_user.first_name, 'characters': [], 'last_daily_reward': None}
            await user_collection.insert_one(user_data)
        last_claimed_date = user_data.get('last_daily_reward')
        if last_claimed_date and hasattr(last_claimed_date, 'date') and last_claimed_date.date() == datetime.utcnow().date():
            remaining_time = timedelta(days=1) - (datetime.utcnow() - last_claimed_date)
            formatted_time = await format_time_delta(remaining_time)
            return await reply_panel(message,
                premium_text(rich_card('Claim already collected', f"Your next daily claim unlocks in <code>{html.escape(formatted_time)}</code>.", '⏳')),
                parse_mode='html',
            )
        unique_characters = await get_unique_characters(user_id)
        if not unique_characters:
            return await reply_panel(message,
                premium_text(rich_card('No claim available', 'There are no eligible characters right now. Please try again later.', '🚫')),
                parse_mode='html',
            )
        await user_collection.update_one({'id': user_id}, {'$push': {'characters': {'$each': unique_characters}}, '$set': {'last_daily_reward': datetime.utcnow()}})
        for character in unique_characters:
            details = rich_table(
                ('DETAIL', 'CHARACTER'),
                [
                    ('Name', f"<b>{html.escape(str(character.get('name', 'Unknown')))}</b>"),
                    ('Rarity', html.escape(str(character.get('rarity', 'Unknown')))),
                    ('Anime', html.escape(str(character.get('anime', 'Unknown')))),
                    ('ID', f"<code>{html.escape(str(character.get('id', '?')))}</code>"),
                ],
            )
            caption = premium_text(rich_card(
                'Daily character claimed',
                f"Congratulations, {mention}!\n{details}\nCome back tomorrow for another claim.",
                '🎁',
            ))
            if character.get('img_url'):
                try:
                    await reply_photo_panel(message,
                        photo=character['img_url'],
                        caption=tr(caption, lang),
                        parse_mode='html',
                    )
                    continue
                except Exception:
                    pass
            await reply_notice(message, tr(caption, lang), parse_mode='html')
    except Exception as e:
        print(f'Error in mclaim command: {e}')
        await reply_panel(message,
            premium_text(rich_card('Claim unavailable', 'Something went wrong while processing this claim. Please retry shortly.', '⚠️')),
            parse_mode='html',
        )
    finally:
        claim_lock.pop(user_id, None)
