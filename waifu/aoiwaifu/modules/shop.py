from aoiwaifu.unit.rich_ui import (
    reply_photo_panel,
    premium_button,
    premium_text,
    rich_card,
)
from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t
import html
import random
from pyrogram.types import InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from bson import ObjectId
from pyrogram import filters
from pyrogram.enums import ParseMode
from aoiwaifu import *
from pymongo import ReturnDocument
from aoiwaifu.unit.aoi_rarity import RARITY_NAMES
user_shop_state = {}
shop_claim_locks = set()
SHOP_IMAGE_URL = WAIFU_SHOP_IMAGE
# Summon-bot's configured purchase prices, keyed by Fiona's canonical rarity names.
RARITY_PRICE = {
    "⚪ Common": 15000,
    "🔵 Rare": 25000,
    "💮 Special Edition": 50000,
    "⭐ Legendary": 90000,
    "🛸 Mythic Edition": 150000,
    "💝 Valentine Edition": 250000,
    "🏖️ Summer Edition": 250000,
    "🌧️ Rainy Edition": 250000,
    "🎃 Halloween Edition": 350000,
    "🎄 Christmas Edition": 350000,
    "❄️ Winter Edition": 400000,
    "🎇 New Year Edition": 450000,
    "🎍 Festival Edition": 550000,
    "🎥 AMV Edition": 100000,
    "🔞 Ecchi": 650000,
    "🌌 Celestial Edition": 1000000,
    "💎 Luxury Edition": 1500000,
    "🔮 Limited Edition": 2000000,
}
SHOP_RARITIES = [(rarity, rarity.split(maxsplit=1)[0]) for rarity in RARITY_NAMES]

def build_shop_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        premium_button(rarity.split(maxsplit=1)[1], emoji='STAR', callback_data=f'xeno_{i}')
        for i, (rarity, _) in enumerate(SHOP_RARITIES)
    ]
    keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(keyboard)

def safe_split(data, sep='_', expected=2):
    parts = data.split(sep)
    if len(parts) < expected:
        parts += [None] * (expected - len(parts))
    return parts[:expected]

def is_video(url):
    return any((url.lower().endswith(ext) for ext in ['.mp4', '.mov', '.webm']))

async def _edit_shop_message_media(msg, media_url: str, caption: str, reply_markup: InlineKeyboardMarkup):
    """
    Edit the existing shop message in place instead of deleting and sending a new message.
    """
    try:
        caption = premium_text(caption)
        if is_video(media_url):
            media_obj = InputMediaVideo(media=media_url, caption=caption, parse_mode=ParseMode.HTML)
        else:
            media_obj = InputMediaPhoto(media=media_url, caption=caption, parse_mode=ParseMode.HTML)
        await msg.edit_media(media=media_obj, reply_markup=reply_markup)
    except Exception:
        try:
            await msg.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:
            pass

@app.on_message(filters.command(['shop', 'hshop', 'hshopmenu']))
async def shop_menu(client, message):
    lang = await get_effective_lang(message)
    await reply_photo_panel(message,
        photo=SHOP_IMAGE_URL,
        caption=premium_text(rich_card('Fiona character shop', t('shop_main_caption', lang), '🌸')),
        reply_markup=build_shop_keyboard(),
        parse_mode=ParseMode.HTML,
    )

@app.on_callback_query(filters.regex('^xeno_\\d+$'))
async def show_rarity_list(client, callback_query):
    lang = await get_effective_lang(callback_query)
    _, index_str = safe_split(callback_query.data, '_', 2)
    idx = int(index_str)
    if idx < 0 or idx >= len(SHOP_RARITIES):
        return await callback_query.answer(tr('Invalid rarity selection!', lang), show_alert=True)
    rarity, _ = SHOP_RARITIES[idx]
    user_id = callback_query.from_user.id
    characters = await collection.find({'rarity': rarity}).to_list(length=200)
    if not characters:
        return await callback_query.answer(tr('No characters found for this rarity!', lang), show_alert=True)
    random.shuffle(characters)
    user_shop_state[user_id] = {'rarity': rarity, 'index': 0, 'characters': characters[:5]}
    await show_character(client, callback_query.message, user_id)
    await callback_query.answer()

async def show_character(client, msg, user_id):
    lang = await get_effective_lang(msg)
    data = user_shop_state[user_id]
    char = data['characters'][data['index']]
    price = RARITY_PRICE.get(char['rarity'], 1000)
    user = await user_collection.find_one({'id': user_id}, {'balance': 1, 'characters': 1}) or {}
    balance = int(user.get('balance', 0) or 0)
    owned = sum(
        1 for item in (user.get('characters') or [])
        if isinstance(item, dict) and str(item.get('id')) == str(char.get('id'))
    )
    caption = rich_card(
        "Fiona character bazaar",
        "\n".join((
            f"💎 <b>{html.escape(str(char.get('name', 'Unknown')))}</b>",
            f"🏯 <b>Anime:</b> {html.escape(str(char.get('anime', 'Unknown')))}",
            f"⭐ <b>Rarity:</b> {html.escape(str(char.get('rarity', 'Unknown')))}",
            f"🆔 <b>ID:</b> <code>{html.escape(str(char.get('id', '?')))}</code>",
            f"💰 <b>Price:</b> {price:,} coins",
            f"👛 <b>Your wallet:</b> {balance:,} coins",
            f"📦 <b>Already owned:</b> {owned}",
            "<i>Review the details, then buy or keep browsing.</i>",
        )),
        "🛍️",
    )
    keyboard = [
        [
            premium_button('Previous', emoji='LEFT_CHEVRON', callback_data='prev_char'),
            premium_button('Buy', emoji='CART', style='SUCCESS', callback_data=f"claim_{data['index']}"),
            premium_button('Next', emoji='RIGHT_CHEVRON', callback_data='next_char'),
        ],
        [
            premium_button('Refresh · 5k', emoji='REFRESH', callback_data='refresh_chars'),
            premium_button('Shop home', emoji='HOME', callback_data='shop_back'),
        ],
    ]
    image_url = char.get('img_url') or char.get('image') or char.get('url')
    if not image_url:
        try:
            return await msg.edit_caption(caption=tr(f'{caption}\n\n❌ <i>No valid media URL for this character.</i>', lang), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        except Exception:
            return
    await _edit_shop_message_media(msg=msg, media_url=image_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex('^shop_back$'))
async def shop_back_callback(client, callback_query):
    lang = await get_effective_lang(callback_query)
    await _edit_shop_message_media(msg=callback_query.message, media_url=SHOP_IMAGE_URL, caption=premium_text(rich_card('Fiona character shop', t('shop_main_caption', lang), '🌸')), reply_markup=build_shop_keyboard())
    await callback_query.answer()

@app.on_callback_query(filters.regex('^refresh_chars$'))
async def refresh_shop_chars(client, callback_query):
    lang = await get_effective_lang(callback_query)
    user_id = callback_query.from_user.id
    state = user_shop_state.get(user_id)
    if not state:
        return await callback_query.answer(tr('Start from /shop again!', lang), show_alert=True)
    refresh_cost = 5000
    updated_user = await user_collection.find_one_and_update({'id': user_id, 'balance': {'$gte': refresh_cost}}, {'$inc': {'balance': -refresh_cost}}, return_document=ReturnDocument.AFTER)
    if not updated_user:
        return await callback_query.answer(tr('❌ Need 5,000 coins to refresh!', lang), show_alert=True)
    characters = await collection.find({'rarity': state['rarity']}).to_list(length=200)
    if not characters:
        return await callback_query.answer(tr('No characters found!', lang), show_alert=True)
    random.shuffle(characters)
    state['index'] = 0
    state['characters'] = characters[:5]
    await show_character(client, callback_query.message, user_id)
    await callback_query.answer(tr('🔄 Shop refreshed!', lang))

@app.on_callback_query(filters.regex('^next_char$'))
async def next_character(client, callback_query):
    lang = await get_effective_lang(callback_query)
    user_id = callback_query.from_user.id
    state = user_shop_state.get(user_id)
    if not state:
        return await callback_query.answer(tr('Start from /shop again!', lang), True)
    if state['index'] >= len(state['characters']) - 1:
        return await callback_query.answer(tr('No more heroes!', lang), True)
    state['index'] += 1
    await show_character(client, callback_query.message, user_id)
    await callback_query.answer()

@app.on_callback_query(filters.regex('^prev_char$'))
async def prev_character(client, callback_query):
    lang = await get_effective_lang(callback_query)
    user_id = callback_query.from_user.id
    state = user_shop_state.get(user_id)
    if not state:
        return await callback_query.answer(tr('Start from /shop again!', lang), True)
    if state['index'] <= 0:
        return await callback_query.answer(tr('Already at first hero!', lang), True)
    state['index'] -= 1
    await show_character(client, callback_query.message, user_id)
    await callback_query.answer()

@app.on_callback_query(filters.regex('^claim_\\d+$'))
async def claim_character(client, callback_query):
    lang = await get_effective_lang(callback_query)
    user_id = callback_query.from_user.id
    if user_id in shop_claim_locks:
        return await callback_query.answer(tr('⏳ Purchase in progress, please wait!', lang), show_alert=True)
    shop_claim_locks.add(user_id)
    try:
        _, index_str = safe_split(callback_query.data, '_', 2)
        state = user_shop_state.get(user_id)
        if not state or not state.get('characters'):
            return await callback_query.answer(tr('Open /shop again!', lang), show_alert=True)
        idx = int(index_str)
        if idx < 0 or idx >= len(state['characters']):
            return await callback_query.answer(tr('Invalid character selection!', lang), show_alert=True)
        char = state['characters'][idx]
        price = RARITY_PRICE.get(char.get('rarity'), 1000)
        updated_user = await user_collection.find_one_and_update({'id': user_id, 'balance': {'$gte': price}}, {'$inc': {'balance': -price}, '$push': {'characters': {'_id': ObjectId(), 'img_url': char.get('img_url'), 'name': char.get('name'), 'anime': char.get('anime'), 'rarity': char.get('rarity'), 'id': char.get('id')}}}, return_document=ReturnDocument.AFTER)
        if not updated_user:
            return await callback_query.answer(tr('❌ Not enough coins or not registered!', lang), show_alert=True)
        await callback_query.answer(tr(f"🎉 You claimed {char.get('name')} for {price:,} coins!", lang), show_alert=True)
        await show_character(client, callback_query.message, user_id)
    finally:
        shop_claim_locks.discard(user_id)
