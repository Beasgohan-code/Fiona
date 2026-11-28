from aoiwaifu.unit.rich_ui import (
    reply_photo_panel,
    reply_video_panel,
    reply_panel,
    edit_panel,
    premium_button,
    premium_text,
    rich_showcase_panel,
    reply_notice,
)
from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
from aoiwaifu import app, collection as character_collection, user_collection
from aoiwaifu.admin.blocklist import get_blocklisted_id_variants
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, CallbackQuery
from html import escape


def _character_id_candidates(raw_id):
    """Match current string IDs plus legacy zero-padded/numeric catalog IDs."""
    value = str(raw_id or "").strip()
    candidates = [value]
    if value.isdigit():
        candidates.extend((value.zfill(2), int(value)))
    return list(dict.fromkeys(candidates))


@app.on_message(filters.command('check'))
async def check_character(client, message):
    lang = await get_effective_lang(message)
    args = message.command
    if len(args) < 2:
        await reply_notice(message, tr('Please provide a Character ID: `/check <character_id>`', lang))
        return
    character_id = args[1]
    id_candidates = _character_id_candidates(character_id)
    character = await character_collection.find_one({'id': {'$in': id_candidates}})
    if not character:
        await reply_notice(message, tr('Character not found.', lang))
        return
    stored_character_id = character.get('id', character_id)
    keyboard = InlineKeyboardMarkup([[
        premium_button(
            'Find collectors',
            emoji='USERS_GROUP',
            callback_data=f'whohaveit_{stored_character_id}',
        )
    ]])
    text = rich_showcase_panel(
        'CHARACTER DOSSIER',
        "<blockquote>"
        f"🆔 <b>ID</b> · <code>{escape(str(stored_character_id))}</code>\n"
        f"👤 <b>Name</b> · {escape(str(character.get('name', 'Unknown')))}\n"
        f"🎌 <b>Anime</b> · {escape(str(character.get('anime', 'Unknown')))}\n"
        f"✨ <b>Rarity</b> · {escape(str(character.get('rarity', 'Unknown')))}"
        "</blockquote>"
        "<p><i>Tap the button below to find collectors who own this character.</i></p>",
        '🪪',
    )
    caption = premium_text(tr(text, lang))
    if character.get('vid_url'):
        await reply_video_panel(message,character['vid_url'], caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)
    elif character.get('img_url'):
        await reply_photo_panel(message,character['img_url'], caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)
    else:
        await reply_panel(message,caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)

@app.on_callback_query(filters.regex('^whohaveit_'))
async def who_have_it(client, callback_query):
    lang = await get_effective_lang(callback_query)
    character_id = callback_query.data[len('whohaveit_'):]
    id_candidates = _character_id_candidates(character_id)
    blocked_ids = await get_blocklisted_id_variants()
    users = await user_collection.find(
        {'characters.id': {'$in': id_candidates}, 'id': {'$nin': blocked_ids}}
    ).to_list(length=10)
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
    owner_text = rich_showcase_panel(
        'COLLECTOR OWNERS',
        "<blockquote>" + "\n".join(owner_lines) + "</blockquote>"
        "<p><i>Showing up to 10 collectors for this character.</i></p>",
        '🏆',
    )
    await edit_panel(callback_query.message, tr(owner_text, lang), reply_markup=None)
    await callback_query.answer()
