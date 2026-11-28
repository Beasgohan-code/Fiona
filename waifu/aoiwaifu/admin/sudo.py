from aoiwaifu.unit.rich_ui import (
    reply_notice,
    premium_button,
)
# ==============================================================================
# How to Use:
#   - Purpose: Manages sudo users and granular power flags, including automatic
#     VIP session revocation (Auto-Logout) whenever VIP power is turned off.
#   - Components: add_sudo, remove_sudo, edit_sudo, toggle_power, sudo_list.
#   - Roots / Routes:
#       * Commands: /saddsudo, /sremovesudo, /seditsudo, /sudolist
#       * Callbacks: toggle_<uid>_<power>, close_keyboard
#       * DB Collection: db.sudo_users
#   - Usage: Loaded automatically by aoiwaifu/__main__.py.
# ==============================================================================

from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, CallbackQuery
from pymongo import MongoClient
from aoiwaifu import OWNER_ID, SUDO
from aoiwaifu import app, db, require_power
from functools import wraps
import html
from aoiwaifu.unit.aoi_parse_fix import SudoUsersHybrid

sudo_users = SudoUsersHybrid(db['sudo_users'], SUDO, OWNER_ID)
ALL_POWERS = ['add_character', 'delete_character', 'update_character', 'approve_request', 'approve_inventory_request', 'VIP']


def _powers_keyboard(user_id: int, powers: dict):
    """Premium toggle keyboard for sudo power flags."""
    buttons = []
    for power in ALL_POWERS:
        enabled = bool(powers.get(power, False))
        toggle = premium_button(
            'Enabled' if enabled else 'Disabled',
            emoji='CHECK_CIRCLE' if enabled else 'CROSS_BADGE',
            style='SUCCESS' if enabled else 'DANGER',
            callback_data=f'toggle_{user_id}_{power}',
        )
        buttons.append([premium_button(power, emoji='KEY_ACCESS', callback_data='noop'), toggle])
    buttons.append([premium_button('Close', emoji='CLOSE', style='DANGER', callback_data='close_keyboard')])
    return InlineKeyboardMarkup(buttons)


@app.on_message(filters.command('saddsudo') & filters.reply)
@require_power('VIP')
async def add_sudo(client, message):
    lang = await get_effective_lang(message)
    replied_user_id = message.reply_to_message.from_user.id
    existing_user = await sudo_users.find_one({'_id': replied_user_id})
    if existing_user:
        await reply_notice(message, tr(f'User <code>{replied_user_id}</code> is already a sudo.', lang))
        return
    await sudo_users.update_one({'_id': replied_user_id}, {'$set': {'powers': {'add_character': True}}}, upsert=True)
    await reply_notice(message, tr(f"User <code>{replied_user_id}</code> has been added as a sudo with 'add_character' power.", lang))


@app.on_message(filters.command('sremovesudo'))
@require_power('VIP')
async def remove_sudo(client, message):
    lang = await get_effective_lang(message)
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif len(message.command) > 1 and message.command[1].isdigit():
        user_id = int(message.command[1])
    else:
        await reply_notice(message, tr('❌ Please reply to a user or provide a valid user ID.', lang))
        return
    existing_user = await sudo_users.find_one({'_id': user_id})
    if not existing_user:
        await reply_notice(message, tr(f'⚠️ User <code>{user_id}</code> is not a sudo.', lang))
        return
    await sudo_users.delete_one({'_id': user_id})
    await reply_notice(message, tr(f"✅ User <a href='tg://user?id={user_id}'>{user_id}</a> has been removed from sudo.", lang))


@app.on_message(filters.command('seditsudo') & filters.reply)
@require_power('VIP')
async def edit_sudo(client, message):
    lang = await get_effective_lang(message)
    replied_user_id = message.reply_to_message.from_user.id
    user_data = await sudo_users.find_one({'_id': replied_user_id})
    if not user_data:
        await reply_notice(message, tr('This user is not a sudo.', lang))
        return
    powers = user_data.get('powers', {})
    keyboard = _powers_keyboard(replied_user_id, powers)
    await reply_notice(message, tr(f'Edit powers for <code>{replied_user_id}</code>:', lang), reply_markup=keyboard)


@app.on_callback_query(filters.regex('^toggle_(\\d+)_(\\w+)$'))
@require_power('VIP')
async def toggle_power(client, callback_query):
    lang = await get_effective_lang(callback_query)
    user_id = int(callback_query.matches[0].group(1))
    power = callback_query.matches[0].group(2)
    user_data = await sudo_users.find_one({'_id': user_id})
    if not user_data:
        await callback_query.answer(tr('User not found.', lang), show_alert=True)
        return
    current_status = user_data.get('powers', {}).get(power, False)
    new_status = not current_status
    await sudo_users.update_one({'_id': user_id}, {'$set': {f'powers.{power}': new_status}})

    # If VIP power was turned OFF, immediately auto-logout any active VIP Admin Panel session!

    await callback_query.answer(tr(f"Power '{power}' updated to {('Yes' if new_status else 'No')}.", lang), show_alert=True)
    user_data = await sudo_users.find_one({'_id': user_id})
    powers = user_data.get('powers', {})
    keyboard = _powers_keyboard(user_id, powers)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)


@app.on_callback_query(filters.regex('^close_keyboard$'))
@require_power('VIP')
async def close_keyboard(client, callback_query):
    lang = await get_effective_lang(callback_query)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.answer(tr('Keyboard closed.', lang), show_alert=True)


def require_power(required_power):

    def decorator(func):

        @wraps(func)
        async def wrapper(client, message, *args, **kwargs):
            lang = await get_effective_lang(message)
            if isinstance(message, CallbackQuery):
                user_id = message.from_user.id
                if user_id == OWNER_ID:
                    return await func(client, message, *args, **kwargs)
                user_data = await sudo_users.find_one({'_id': user_id})
                if not user_data or not user_data.get('powers', {}).get(required_power, False):
                    await message.answer(tr(f'You do not have the {required_power} power required to use this button.', lang), show_alert=True)
                    return
                return await func(client, message, *args, **kwargs)
            user_id = message.from_user.id
            if user_id == OWNER_ID:
                return await func(client, message, *args, **kwargs)
            user_data = await sudo_users.find_one({'_id': user_id})
            if not user_data or not user_data.get('powers', {}).get(required_power, False):
                await reply_notice(message, tr(f'You do not have the <code>{required_power}</code> power required to use this command.', lang))
                return
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator


@app.on_message(filters.command('waifusudolist'))
async def sudo_list(client, message):
    lang = await get_effective_lang(message)
    if message.from_user.id != OWNER_ID:
        await reply_notice(message, tr('You do not have permission to use this command.', lang))
        return
    users = await sudo_users.find().to_list(length=None)
    if not users:
        await reply_notice(message, tr('There are no sudo users.', lang))
        return
    sudo_list_text = '🛠 <b>Sudo Users List:</b>\n\n'
    for user in users:
        user_id = user.get('_id')
        try:
            user_info = await client.get_users(user_id)
            name = html.escape(str(user_info.first_name or 'Unknown'))
            uname = getattr(user_info, 'username', None)
        except Exception:
            name = 'Unknown'
            uname = None
        if uname:
            sudo_list_text += f'➤ <a href="https://t.me/{html.escape(str(uname), quote=True)}">{name}</a> (<code>{user_id}</code>)\n'
        else:
            sudo_list_text += f'➤ {name} (<code>{user_id}</code>)\n'
    await reply_notice(message, tr(sudo_list_text, lang))
