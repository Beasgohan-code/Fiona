from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
from aoiwaifu import app, collection as character_collection, user_collection
from aoiwaifu.admin.blocklist import get_blocklisted_id_variants
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, CallbackQuery
from aoiwaifu.unit.rich_ui import edit_panel, premium_button, premium_text, rich_card
from html import escape

@app.on_message(filters.command('check'))
async def check_character(client, message):
    lang = await get_effective_lang(message)
    args = message.command
    if len(args) < 2:
        await message.reply_text(tr('Please provide a Character ID: `/check <character_id>`', lang))
        return
    character_id = args[1]
    character = await character_collection.find_one({'id': character_id})
    if not character:
        await message.reply_text(tr('Character not found.', lang))
        return
    keyboard = InlineKeyboardMarkup([[
        premium_button('Find collectors', emoji='USERS_GROUP', callback_data=f'whohaveit_{character_id}')
    ]])
    text = rich_card(
        'Character details',
        f"🆔 <b>ID:</b> <code>{escape(str(character_id))}</code>\n"
        f"📛 <b>Name:</b> {escape(str(character.get('name', 'Unknown')))}\n"
        f"📺 <b>Anime:</b> {escape(str(character.get('anime', 'Unknown')))}\n"
        f"💎 <b>Rarity:</b> {escape(str(character.get('rarity', 'Unknown')))}",
        '🌟',
    )
    caption = premium_text(tr(text, lang))
    if character.get('vid_url'):
        await message.reply_video(character['vid_url'], caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)
    elif character.get('img_url'):
        await message.reply_photo(character['img_url'], caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.reply_text(caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)

@app.on_callback_query(filters.regex('^whohaveit_'))
async def who_have_it(client, callback_query):
    lang = await get_effective_lang(callback_query)
    character_id = callback_query.data.split('_')[1]
    blocked_ids = await get_blocklisted_id_variants()
    users = await user_collection.find({'characters.id': character_id, 'id': {'$nin': blocked_ids}}).to_list(length=10)
    if not users:
        await callback_query.answer(tr('No one owns this character yet!', lang), show_alert=True)
        return
    owner_lines = []
    for i, user in enumerate(users, 1):
        user_name = escape(str(user.get('first_name', 'Collector')))
        count = sum(
            1 for char in user.get('characters', [])
            if isinstance(char, dict) and str(char.get('id')) == str(character_id)
        )
        owner_lines.append(f"{i}. <a href='tg://user?id={user['id']}'>{user_name}</a> · x{count}")
    owner_text = rich_card('Character owners', "\n".join(owner_lines), '🏆')
    await edit_panel(callback_query.message, tr(owner_text, lang), reply_markup=None)
    await callback_query.answer()
