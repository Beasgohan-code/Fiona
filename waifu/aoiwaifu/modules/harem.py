from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t
from aoiwaifu.unit.rich_ui import edit_panel, premium_button, premium_text, rich_card, rich_heading, reply_notice
from aoiwaifu import *
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import ChatAdminRequired, UserNotParticipant
from collections import Counter
from itertools import groupby
import math
from html import escape
from pyrogram import enums

async def check_support_channel(client: Client, user_id: int) -> bool:
    if user_id == x:
        return True
    try:
        await client.get_chat_member(SUPPORT_CHANNEL, user_id)
        return True
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        print(f'Bot needs admin privileges in {SUPPORT_CHANNEL} to check membership.')
        return False
    except Exception as e:
        print(f'Error checking support channel membership: {e}')
        return False

async def fetch_user_characters(user_id):
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return (None, 'You have not guessed any characters yet. Use /waifu and try again.')
    raw_characters = user.get('characters') or []
    if not isinstance(raw_characters, list):
        return (None, '⚠️ Your character collection data is invalid. Please contact support.')
    characters = [c for c in raw_characters if isinstance(c, dict) and c.get('id') is not None]
    if not characters:
        return (None, 'No valid characters found in your collection.')
    return (characters, None)

@app.on_message(filters.command(['pincharacter', 'hpin']))
async def pin_character_handler(client: Client, message: Message):
    lang = await get_effective_lang(message)
    if not message.from_user:
        return
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await reply_notice(message, tr('Usage: /pincharacter <character_id>\nExample: /pincharacter 205', lang))
    user_id = message.from_user.id
    character_id = str(message.command[1])
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return await reply_notice(message, tr('Your collection is empty.', lang))
    owned = any((isinstance(char, dict) and str(char.get('id')) == character_id for char in user.get('characters') or []))
    if not owned:
        return await reply_notice(message, tr("You don't own this character.", lang))
    pinned = [str(cid) for cid in user.get('pinned_characters') or []]
    if character_id in pinned:
        return await reply_notice(message, tr(f'Character #{character_id} is already pinned.', lang))
    if len(pinned) >= 10:
        return await reply_notice(message, tr('You can pin a maximum of 10 characters. Use /unpincharacter <id> first.', lang))
    pinned.append(character_id)
    await user_collection.update_one({'id': user_id}, {'$set': {'pinned_characters': pinned}})
    try:
        from aoiwaifu.modules.inlinequery import user_collection_cache
        user_collection_cache.pop(str(user_id), None)
    except Exception:
        pass
    await reply_notice(message, tr(f'📌 Character #{character_id} pinned. It will appear at the top of your inline collection.', lang))

@app.on_message(filters.command(['unpincharacter', 'hunpin']))
async def unpin_character_handler(client: Client, message: Message):
    lang = await get_effective_lang(message)
    if not message.from_user:
        return
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await reply_notice(message, tr('Usage: /unpincharacter <character_id>\nExample: /unpincharacter 205', lang))
    user_id = message.from_user.id
    character_id = str(message.command[1])
    user = await user_collection.find_one({'id': user_id})
    pinned = [str(cid) for cid in user.get('pinned_characters') or []] if user else []
    if character_id not in pinned:
        return await reply_notice(message, tr(f'Character #{character_id} is not pinned.', lang))
    pinned.remove(character_id)
    await user_collection.update_one({'id': user_id}, {'$set': {'pinned_characters': pinned}})
    try:
        from aoiwaifu.modules.inlinequery import user_collection_cache
        user_collection_cache.pop(str(user_id), None)
    except Exception:
        pass
    await reply_notice(message, tr(f'📌 Character #{character_id} unpinned.', lang))

@app.on_message(filters.command(['pinnedcharacters', 'pinlist']))
async def pinlist_handler(client: Client, message: Message):
    lang = await get_effective_lang(message)
    if not message.from_user:
        return
    user = await user_collection.find_one({'id': message.from_user.id})
    pinned = [str(cid) for cid in user.get('pinned_characters') or []] if user else []
    if not pinned:
        return await reply_notice(message, tr("You haven't pinned any characters yet. Use /pincharacter <character_id>.", lang))
    owned_by_id = {}
    for char in user.get('characters') or []:
        if isinstance(char, dict) and char.get('id') is not None:
            owned_by_id.setdefault(str(char['id']), char)
    lines = ['📌 <b>Your Pinned Characters</b>']
    for index, character_id in enumerate(pinned, 1):
        char = owned_by_id.get(character_id)
        if char:
            lines.append(f"{index}. <b>{escape(str(char.get('name', 'Unknown Character')))}</b> — {escape(str(char.get('rarity', 'Unknown')))} <code>#{escape(character_id)}</code>")
        else:
            lines.append(f'{index}. <code>#{escape(character_id)}</code>')
    lines.append(f'\n{len(pinned)}/10 pinned')
    await reply_notice(message, tr('\n'.join(lines), lang), parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(['harem', 'collection', 'claimlist']))
async def harem_handler(client: Client, message: Message):
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    page = 0
    user = await user_collection.find_one({'id': user_id})
    filter_rarity = user.get('filter_rarity', None) if user else None
    await display_harem(client, message, user_id, page, filter_rarity, is_initial=True)

async def display_harem(client, message, user_id, page, filter_rarity, is_initial=False, callback_query=None, force_refresh_photo=False):
    # Initialize language before any operation that can fail, so error handlers can use it too.
    lang = await get_effective_lang(callback_query or message, user_id=user_id)
    try:
        user_db = await user_collection.find_one({'id': user_id})
        fallback_name = message.from_user.first_name if is_initial and getattr(message, 'from_user', None) and message.from_user.first_name else 'Collector'
        user_first_name = (user_db.get('first_name') if user_db else None) or fallback_name
        characters, error = await fetch_user_characters(user_id)
        if error:
            error_text = premium_text(tr(error, lang))
            if is_initial:
                return await message.reply_text(error_text, parse_mode=enums.ParseMode.HTML)
            await edit_panel(callback_query.message, error_text)
            return
        characters = sorted(characters, key=lambda x: (str(x.get('anime', '')), str(x.get('id', ''))))
        all_characters = characters
        if filter_rarity:
            filtered_characters = [c for c in characters if c.get('rarity') == filter_rarity]
            if not filtered_characters:
                keyboard = [[premium_button(tr('Remove filter', lang), emoji='CLOSE', style='DANGER', callback_data=f'remove_filter:{user_id}')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                empty_filter_text = rich_card(
                    'Collection filter',
                    f"No characters found with rarity: <b>{escape(str(filter_rarity))}</b>. Clear this filter to browse your full collection.",
                    '🔎',
                )
                if is_initial:
                    return await message.reply_text(
                        premium_text(tr(empty_filter_text, lang)),
                        reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML,
                    )
                await edit_panel(callback_query.message, tr(empty_filter_text, lang), reply_markup)
                return
            characters = filtered_characters
        total_characters = len(characters)
        amv_characters = len([c for c in characters if 'vid_url' in c])
        character_counts = Counter(str(character.get('id', '')) for character in characters)
        unique_characters = list({str(character.get('id')): character for character in characters}.values())
        items_per_page = 10
        total_pages = max(1, math.ceil(len(unique_characters) / items_per_page))
        if page < 0 or page >= total_pages:
            page = 0
        lang = await get_effective_lang(callback_query or message, user_id=user_id)
        harem_message = (
            f"📄 <b>Page:</b> {page + 1}/{total_pages}  •  "
            f"✨ <b>Unique:</b> {len(unique_characters):,}  •  🎴 <b>Cards:</b> {total_characters:,}"
        )
        if filter_rarity:
            harem_message += f"\n{t('harem_filtered_by', lang, rarity=escape(str(filter_rarity)))}"
        current_characters = unique_characters[page * items_per_page:(page + 1) * items_per_page]
        current_grouped_characters = {k: list(v) for k, v in groupby(current_characters, key=lambda x: x.get('anime', 'Unknown Anime'))}
        for anime, chars in current_grouped_characters.items():
            total_anime_chars = await collection.count_documents({'anime': anime})
            owned_in_anime = len({
                str(character.get('id'))
                for character in all_characters
                if character.get('anime', 'Unknown Anime') == anime
            })
            harem_message += (
                f"\n\n{rich_heading(escape(str(anime)), '⛩️')} "
                f"<i>{owned_in_anime}/{total_anime_chars} collected</i>\n"
            )
            for character in chars:
                character_id = str(character.get('id', '?'))
                count = character_counts.get(character_id, 1)
                rarity_emoji = rarity_map2.get(character.get('rarity'), '❔')
                harem_message += (
                    f"◈ <code>{escape(character_id)}</code> {rarity_emoji} "
                    f"<b>{escape(str(character.get('name', 'Unknown Character')))}</b> "
                    f"×{count}\n"
                )
        harem_message = rich_card(f'Collection · {escape(user_first_name)}', harem_message, '🎴')
        keyboard = [
            [
                premium_button(
                    f'Harem ({total_characters})',
                    emoji='USERS_GROUP',
                    switch_inline_query_current_chat=f'collection.{user_id}',
                ),
                premium_button(
                    f'AMV ({amv_characters})',
                    emoji='VIDEO_STREAM',
                    switch_inline_query_current_chat=f'collection.{user_id}.AMV',
                ),
            ],
            [
                premium_button(
                    tr('Refresh', lang),
                    emoji='REFRESH',
                    callback_data=f"harem_refresh:{page}:{user_id}:{filter_rarity or 'None'}",
                ),
            ],
        ]
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    premium_button(
                        tr('Previous', lang),
                        emoji='LEFT_CHEVRON',
                        callback_data=f"harem:{page - 1}:{user_id}:{filter_rarity or 'None'}",
                    )
                )
            if page < total_pages - 1:
                nav_buttons.append(
                    premium_button(
                        tr('Next', lang),
                        emoji='RIGHT_CHEVRON',
                        callback_data=f"harem:{page + 1}:{user_id}:{filter_rarity or 'None'}",
                    )
                )
            keyboard.append(nav_buttons)
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Pick favorite character photo, else first available character photo, else PHOTO_URL[0]
        harem_photo = None
        fav_ids = (user_db.get('favorites') or []) if user_db else []
        if fav_ids:
            fav_char = next((c for c in characters if str(c.get('id')) == str(fav_ids[0]) and c.get('img_url')), None)
            if fav_char:
                harem_photo = fav_char['img_url']
        if not harem_photo:
            harem_photo = next((c.get('img_url') for c in current_characters if c.get('img_url')), None) or PHOTO_URL[0]

        localized_caption = tr(harem_message, lang)
        if is_initial:
            try:
                return await message.reply_photo(
                    photo=harem_photo,
                    caption=premium_text(localized_caption),
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                return await message.reply_text(
                    premium_text(localized_caption),
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
        await edit_panel(callback_query.message, localized_caption, reply_markup)
    except Exception as e:
        print(f'Error in display_harem: {e}')
        error_msg = premium_text(tr('⚠️ Could not load this collection page. Please try again.', lang))
        if is_initial:
            await message.reply_text(error_msg, parse_mode=enums.ParseMode.HTML)
        elif callback_query:
            await edit_panel(callback_query.message, error_msg)

@app.on_callback_query(filters.regex('^remove_filter'))
async def remove_filter_callback(client: Client, callback_query: CallbackQuery):
    lang = await get_effective_lang(callback_query)
    try:
        _, user_id = callback_query.data.split(':')
        user_id = int(user_id)
        if callback_query.from_user.id != user_id:
            await callback_query.answer(tr("It's not your Harem!", lang), show_alert=True)
            return
        await user_collection.update_one({'id': user_id}, {'$set': {'filter_rarity': None}}, upsert=True)
        await callback_query.answer(tr('Filter removed. Showing all rarities.', lang))
        await display_harem(
            client,
            callback_query.message,
            user_id,
            page=0,
            filter_rarity=None,
            is_initial=False,
            callback_query=callback_query,
        )
    except Exception as e:
        print(f'Error in remove_filter callback: {e}')

@app.on_callback_query(filters.regex('^harem:'))
async def harem_callback(client: Client, callback_query: CallbackQuery):
    lang = await get_effective_lang(callback_query)
    try:
        data = callback_query.data
        _, page, user_id, filter_rarity = data.split(':')
        page = int(page)
        user_id = int(user_id)
        filter_rarity = None if filter_rarity == 'None' else filter_rarity
        if callback_query.from_user.id != user_id:
            await callback_query.answer(tr("It's not your Harem!", lang), show_alert=True)
            return
        await callback_query.answer()
        await display_harem(client, callback_query.message, user_id, page, filter_rarity, is_initial=False, callback_query=callback_query, force_refresh_photo=False)
    except Exception as e:
        print(f'Error in harem callback: {e}')

@app.on_callback_query(filters.regex('^harem_refresh:'))
async def harem_refresh_callback(client: Client, callback_query: CallbackQuery):
    lang = await get_effective_lang(callback_query)
    try:
        data = callback_query.data
        _, page, user_id, filter_rarity = data.split(':')
        page = int(page)
        user_id = int(user_id)
        filter_rarity = None if filter_rarity == 'None' else filter_rarity
        if callback_query.from_user.id != user_id:
            await callback_query.answer(tr("It's not your Harem!", lang), show_alert=True)
            return
        await callback_query.answer(tr('Refreshing your collection...', lang))
        await display_harem(client, callback_query.message, user_id, page, filter_rarity, is_initial=False, callback_query=callback_query, force_refresh_photo=True)
    except Exception as e:
        print(f'Error in harem_refresh callback: {e}')

@app.on_message(filters.command('hmode'))
async def hmode_handler(client: Client, message: Message):
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    keyboard = []
    row = []
    for i, (rarity, emoji) in enumerate(rarity_map2.items(), 1):
        row.append(InlineKeyboardButton(emoji, callback_data=f'set_rarity:{user_id}:{rarity}'))
        if i % 4 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        premium_button(
            tr('All rarities', lang),
            emoji='GRID',
            callback_data=f'set_rarity:{user_id}:None',
        )
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    prompt = rich_card(
        'Collection filter',
        "Choose a rarity to focus your collection.\nYour choice is saved for the next /harem view.",
        '💎',
    )
    await message.reply_text(
        premium_text(tr(prompt, lang)),
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
    )

@app.on_callback_query(filters.regex('^set_rarity'))
async def set_rarity_callback(client: Client, callback_query: CallbackQuery):
    lang = await get_effective_lang(callback_query)
    try:
        _, user_id, filter_rarity = callback_query.data.split(':')
        user_id = int(user_id)
        filter_rarity = None if filter_rarity == 'None' else filter_rarity
        if callback_query.from_user.id != user_id:
            await callback_query.answer(tr("It's not your Harem!", lang), show_alert=True)
            return
        await user_collection.update_one({'id': user_id}, {'$set': {'filter_rarity': filter_rarity}}, upsert=True)
        selected = filter_rarity or 'All'
        await callback_query.answer(tr(f"Showing {selected} rarities", lang))
        await display_harem(
            client,
            callback_query.message,
            user_id,
            page=0,
            filter_rarity=filter_rarity,
            is_initial=False,
            callback_query=callback_query,
        )
    except Exception as e:
        print(f'Error in set_rarity callback: {e}')
