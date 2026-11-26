"""Start and interactive help menu commands (/start)."""

import asyncio
import html
import random
import time
from pyrogram import enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup

from aoiwaifu import (
    GLOG,
    OWNER_USERNAME,
    START_MEDIA,
    SUPPORT_CHAT,
    UPDATE_CHAT,
    app,
    user_collection,
)
from aoiwaifu.unit.aoi_help import HELP_DATA
from aoiwaifu.unit.rich_ui import edit_panel, premium_button, premium_text
from aoiwaifu.unit.aoi_lang import (
    DEFAULT_LANG,
    build_language_keyboard,
    get_chat_lang,
    get_effective_lang,
    get_lang_label,
    get_user_lang,
    has_user_set_lang,
    t,
    tr,
)

START_TIME = time.time()


def get_uptime():
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def build_dm_first_start_lang_prompt() -> tuple[str, InlineKeyboardMarkup]:
    caption = (
        f"╭━〔 🌐 𝐅𝐈𝐎𝐍𝐀 • 𝐋𝐀𝐍𝐆𝐔𝐀𝐆𝐄 〕━╮\n\n"
        f"<blockquote>{t('lang_select_dm_title', 'en')}\n"
        f"{t('lang_select_dm_body', 'en')}\n\n"
        f"🇺🇸 <b>English</b> • 🇷🇺 <b>Русский</b> • 🇪🇸 <b>Español</b> • 🇧🇷 <b>Português</b>\n"
        f"🇮🇩 <b>Indonesia</b> • 🇮🇳 <b>हिन्दी</b> • 🇲🇲 <b>မြန်မာစာ</b> • 🇸🇦 <b>العربية</b>\n"
        f"🇹🇷 <b>Türkçe</b> • 🇻🇳 <b>Tiếng Việt</b></blockquote>\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━╯"
    )
    markup = build_language_keyboard(
        callback_prefix="set_dm_lang", current_lang=None, back_callback=None, extra_suffix=":start"
    )
    return (caption, markup)


async def generate_start_message(client, message, lang: str = None):
    if not lang:
        uid = (
            message.from_user.id
            if message and getattr(message, "from_user", None)
            else message.chat.id if message and getattr(message, "chat", None) else 0
        )
        lang = await get_user_lang(uid)
    bot_user = await client.get_me()
    bot_name = getattr(bot_user, "first_name", None) or "Fiona"
    bot_username = getattr(bot_user, "username", None) or ""
    msg_ts = (
        message.date.timestamp()
        if message and getattr(message, "date", None) and hasattr(message.date, "timestamp")
        else time.time()
    )
    ping = max(0.01, round(time.time() - msg_ts, 2))
    uptime = get_uptime()
    caption = t(
        "start_private_caption",
        lang,
        bot_name=html.escape(str(bot_name)),
        bot_username=html.escape(str(bot_username)),
        ping=ping,
        uptime=uptime,
    )
    buttons = []
    if bot_username:
        buttons.append(
            [
                premium_button(
                    t("btn_add_to_group", lang), emoji="BOT", style="PRIMARY",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ]
        )
    links = []
    if SUPPORT_CHAT:
        links.append(premium_button(t("btn_support", lang), emoji="CHAT_BUBBLE", style="SUCCESS", url=SUPPORT_CHAT))
    if UPDATE_CHAT:
        links.append(premium_button(t("btn_updates", lang), emoji="MEGAPHONE", style="SUCCESS", url=UPDATE_CHAT))
    if links:
        buttons.append(links)
    buttons.append(
        [
            premium_button(t("btn_help_commands", lang), emoji="HELP_SUPPORT", style="PRIMARY", callback_data="open_help"),
            premium_button(f"{t('btn_language', lang)} ({get_lang_label(lang)})", emoji="GLOBE_LANG", callback_data="open_dm_lang"),
        ]
    )
    if OWNER_USERNAME:
        buttons.append(
            [premium_button(t("btn_owner", lang), emoji="CROWN_OWNER", url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}")]
        )
    return (caption, buttons)


async def generate_group_start_message(client, message=None, lang: str = None):
    if not lang:
        cid = message.chat.id if message and getattr(message, "chat", None) else 0
        lang = await get_chat_lang(cid)
    bot_user = await client.get_me()
    bot_username = getattr(bot_user, "username", None) or ""
    group_title = (
        html.escape(str(message.chat.title))
        if message and getattr(message, "chat", None) and getattr(message.chat, "title", None)
        else "your group"
    )
    caption = t("start_group_caption", lang, group_title=group_title)
    buttons = []
    if bot_username:
        buttons.append(
            [
                premium_button(
                    t("btn_add_to_group", lang), emoji="BOT", style="PRIMARY",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ]
        )
    if SUPPORT_CHAT:
        buttons.append([premium_button(t("btn_support", lang), emoji="CHAT_BUBBLE", style="SUCCESS", url=SUPPORT_CHAT)])
    buttons.append(
        [
            premium_button(
                f"{t('btn_group_settings', lang)} ({get_lang_label(lang)})",
                emoji="SETTINGS", callback_data="open_group_settings",
            )
        ]
    )
    return (caption, buttons)


async def send_media_message(message, media, caption, buttons):
    reply_markup = buttons if isinstance(buttons, InlineKeyboardMarkup) else InlineKeyboardMarkup(buttons)
    caption = premium_text(caption)
    if media.lower().endswith((".png", ".jpg", ".jpeg")):
        await message.reply_photo(
            photo=media, caption=caption, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML
        )
    elif media.lower().endswith(".gif"):
        await message.reply_animation(
            animation=media, caption=caption, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML
        )
    else:
        await message.reply_video(
            video=media, caption=caption, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML
        )


@app.on_message(filters.command("waifu") & filters.private)
async def start_private_command(client, message):
    user = message.from_user
    lang_already_set = True
    if user:
        existing_user = await user_collection.find_one({"id": user.id})
        is_new_start = not existing_user or not existing_user.get("has_started_bot")
        lang_already_set = bool(existing_user and existing_user.get("lang_set") and existing_user.get("lang"))
        await user_collection.update_one(
            {"id": user.id},
            {
                "$set": {
                    "first_name": getattr(user, "first_name", "") or "",
                    "username": getattr(user, "username", "") or "",
                    "last_name": getattr(user, "last_name", "") or "",
                    "has_started_bot": True,
                },
                "$setOnInsert": {"start_time": time.time(), "balance": 0, "tokens": 0, "characters": []},
            },
            upsert=True,
        )
        if len(message.command) > 1:
            try:
                from aoiwaifu.modules.referral import process_referral

                await process_referral(client, user, message.command[1], is_new_start=is_new_start)
            except Exception:
                pass

    media = random.choice(START_MEDIA)
    if GLOG and user:
        try:
            await app.send_message(
                chat_id=GLOG,
                text=(
                    f"🌸 {getattr(user, 'mention', user.first_name)} started the bot.\n\n"
                    f"<b>User ID:</b> <code>{user.id}</code>\n"
                    f"<b>Username:</b> @{user.username}"
                ),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass

    if user and (not lang_already_set) and (not await has_user_set_lang(user.id)):
        prompt_caption, prompt_markup = build_dm_first_start_lang_prompt()
        await send_media_message(message, media, prompt_caption, prompt_markup)
        return

    user_lang = await get_user_lang(user.id if user else 0)
    caption, buttons = await generate_start_message(client, message, lang=user_lang)
    await send_media_message(message, media, caption, buttons)


@app.on_message(filters.command("waifu") & filters.group)
async def start_group_command(client, message):
    user = message.from_user
    if user:
        await user_collection.update_one(
            {"id": user.id},
            {
                "$set": {
                    "first_name": getattr(user, "first_name", "") or "",
                    "username": getattr(user, "username", "") or "",
                    "last_name": getattr(user, "last_name", "") or "",
                },
                "$setOnInsert": {"start_time": time.time(), "balance": 0, "tokens": 0, "characters": []},
            },
            upsert=True,
        )
    grp_lang = await get_chat_lang(message.chat.id)
    caption, buttons = await generate_group_start_message(client, message, lang=grp_lang)
    media = random.choice(START_MEDIA)
    await send_media_message(message, media, caption, buttons)


HELP_MODULE_EMOJIS = {
    "guess": "GAMEPAD",
    "harem": "USERS_GROUP",
    "profile": "USER",
    "balance": "WALLET",
    "trade": "GIFT",
    "search": "SEARCH",
    "lang": "GLOBE_LANG",
    "admin": "SHIELD_ADMIN",
}


def find_help_modules(lang: str = DEFAULT_LANG):
    buttons = []
    for module_name, module_data in HELP_DATA.items():
        button_name = tr(module_data.get("HELP_NAME", "Unknown"), lang)
        buttons.append(
            premium_button(
                button_name,
                emoji=HELP_MODULE_EMOJIS.get(module_name, "INFO"),
                style="PRIMARY",
                callback_data=f"help_{module_name}",
            )
        )
    return [buttons[i : i + 3] for i in range(0, len(buttons), 3)]


@app.on_callback_query(filters.regex("^open_help$"))
async def show_help_menu(client, query: CallbackQuery):
    await asyncio.sleep(0.05)
    lang = await get_effective_lang(query)
    buttons = find_help_modules(lang)
    buttons.append([premium_button(t("btn_back", lang), emoji="BACK_ARROW", callback_data="back_to_home")])
    text = premium_text(tr(t("help_menu_caption", lang), lang))
    await edit_panel(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


@app.on_callback_query(filters.regex("^help_(.+)"))
async def show_help(client, query: CallbackQuery):
    await asyncio.sleep(0.05)
    lang = await get_effective_lang(query)
    module_name = query.data.split("_", 1)[1]
    try:
        module_data = HELP_DATA.get(module_name, {})
        help_text = module_data.get(f"HELP_{lang.upper()}") or module_data.get("HELP", t("help_not_found", lang))
        buttons = [[premium_button(t("btn_back", lang), emoji="BACK_ARROW", callback_data="open_help")]]
        full_text = t("help_module_header", lang, module_name=module_name.upper(), help_text=help_text)
        await edit_panel(
            query.message,
            tr(full_text, lang),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        await query.answer()
    except Exception:
        await query.answer(t("help_load_error", lang))


@app.on_callback_query(filters.regex("^back_to_home$"))
async def back_to_home(client, query: CallbackQuery):
    await asyncio.sleep(0.05)
    lang = await get_effective_lang(query, user_id=query.from_user.id if query.from_user else None)
    caption, buttons = await generate_start_message(client, query.message, lang=lang)
    await edit_panel(query.message, tr(caption, lang), reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()
