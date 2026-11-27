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
from pyrogram import Client, filters, types as t_types
from pyrogram.types import InlineKeyboardMarkup
from aoiwaifu.unit.rich_ui import premium_button, premium_text, rich_card, rich_table, reply_notice
from datetime import datetime, timedelta
from aoiwaifu import ZYRO as bot
from aoiwaifu import user_collection, collection, user_guess_progress, SUPPORT_CHAT_ID as chat, SUPPORT_CHAT

claim_lock = {}


async def format_time_delta(delta):
    seconds = delta.total_seconds()
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{int(hours)}h {int(minutes)}m {int(seconds)}s' if hours or minutes or seconds else '0s'


async def get_unique_characters(user_id, target_rarities=None):
    if target_rarities is None:
        from aoiwaifu import rarity_map
        target_rarities = [rarity_map[index] for index in (1, 2, 3) if index in rarity_map]
    try:
        user_data = await user_collection.find_one({'id': user_id}, {'characters.id': 1})
        claimed_ids = [char['id'] for char in user_data.get('characters', []) if isinstance(char, dict) and 'id' in char] if user_data else []
        pipeline = [
            {'$match': {'rarity': {'$in': target_rarities}, 'id': {'$nin': claimed_ids}}},
            {'$sample': {'size': 1}},
        ]
        cursor = collection.aggregate(pipeline)
        characters = await cursor.to_list(length=None)
        if not characters:
            # Fallback if user already claimed all unique cards in those rarities
            pipeline_any = [
                {'$match': {'rarity': {'$in': target_rarities}}},
                {'$sample': {'size': 1}},
            ]
            cursor_any = collection.aggregate(pipeline_any)
            characters = await cursor_any.to_list(length=None)
        return characters if characters else []
    except Exception as e:
        print(f'Error retrieving unique characters: {e}')
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
        return await message.reply_text(
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
            return await message.reply_text(
                premium_text(rich_card('Claim already collected', f"Your next daily claim unlocks in <code>{html.escape(formatted_time)}</code>.", '⏳')),
                parse_mode='html',
            )
        unique_characters = await get_unique_characters(user_id)
        if not unique_characters:
            return await message.reply_text(
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
                    await message.reply_photo(
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
        await message.reply_text(
            premium_text(rich_card('Claim unavailable', 'Something went wrong while processing this claim. Please retry shortly.', '⚠️')),
            parse_mode='html',
        )
    finally:
        claim_lock.pop(user_id, None)
