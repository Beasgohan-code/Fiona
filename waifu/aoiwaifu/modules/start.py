"""Start and interactive help menu commands (/start)."""

from aoiwaifu.unit.rich_ui import (
    reply_photo_panel,
    reply_video_panel,
    reply_panel,
    edit_panel,
    premium_button,
    premium_text,
    rich_card,
)
import asyncio
import html
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from pyrogram import enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup

from aoiwaifu import (
    OWNER_USERNAME,
    START_MEDIA,
    SUPPORT_CHAT,
    UPDATE_CHAT,
    app,
    user_collection,
)
from aoiwaifu.unit.aoi_help import HELP_DATA
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
_start_media_cycle: list[str] = []


def pick_start_media() -> str:
    """Return images in a shuffled cycle so adjacent starts avoid repeats."""
    global _start_media_cycle
    choices = [str(item).strip() for item in START_MEDIA if str(item).strip()]
    if not choices:
        return ""
    if not _start_media_cycle:
        _start_media_cycle = choices.copy()
        random.shuffle(_start_media_cycle)
    return _start_media_cycle.pop()


def get_uptime():
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def build_dm_first_start_lang_prompt() -> tuple[str, InlineKeyboardMarkup]:
    caption = rich_card(
        t('lang_select_dm_title', 'en'),
        "\n".join((
            t('lang_select_dm_body', 'en'),
            "",
            "🇺🇸 <b>English</b> • 🇷🇺 <b>Русский</b> • 🇪🇸 <b>Español</b> • 🇧🇷 <b>Português</b>",
            "🇮🇩 <b>Indonesia</b> • 🇮🇳 <b>हिन्दी</b> • 🇲🇲 <b>မြန်မာစာ</b> • 🇸🇦 <b>العربية</b>",
            "🇹🇷 <b>Türkçe</b> • 🇻🇳 <b>Tiếng Việt</b>",
        )),
        "🌐",
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
                t("btn_help_commands", lang),
                emoji="HELP_SUPPORT",
                callback_data="grouphelp:open",
            ),
            premium_button(
                f"{t('btn_group_settings', lang)} ({get_lang_label(lang)})",
                emoji="SETTINGS",
                callback_data="open_group_settings",
            ),
        ]
    )
    return (caption, buttons)


def _start_media_kind(media: str) -> str:
    suffix = Path(urlparse(str(media)).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "photo"
    if suffix == ".gif":
        return "animation"
    return "video"


async def _reply_with_media(message, media, kind, caption, reply_markup):
    common = {
        "caption": caption,
        "reply_markup": reply_markup,
        "parse_mode": enums.ParseMode.HTML,
    }
    if kind == "photo":
        await reply_photo_panel(message,photo=media, **common)
    elif kind == "animation":
        await message.reply_animation(animation=media, **common)
    else:
        await reply_video_panel(message,video=media, **common)


async def _download_start_media(url: str) -> tuple[str, str]:
    """Fetch a remote start asset locally when Telegram cannot curl its URL."""
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("start media is not an HTTP(S) URL")

    timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            suffix = Path(urlparse(str(response.url)).path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4"}:
                suffix = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                    "image/gif": ".gif",
                    "video/mp4": ".mp4",
                }.get(content_type, "")
            if not suffix:
                raise ValueError(f"unsupported start-media content type: {content_type or 'unknown'}")

            kind = "animation" if suffix == ".gif" else "video" if suffix == ".mp4" else "photo"
            fd, path = tempfile.mkstemp(prefix="fiona-start-", suffix=suffix)
            total = 0
            try:
                with os.fdopen(fd, "wb") as output:
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        total += len(chunk)
                        if total > 50 * 1024 * 1024:
                            raise ValueError("start-media file exceeds 50 MiB")
                        output.write(chunk)
                if total == 0:
                    raise ValueError("start-media file is empty")
                return path, kind
            except Exception:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise


async def send_media_message(message, media, caption, buttons):
    reply_markup = buttons if isinstance(buttons, InlineKeyboardMarkup) else InlineKeyboardMarkup(buttons)
    caption = premium_text(caption)
    kind = _start_media_kind(media)
    is_remote = urlparse(str(media)).scheme in {"http", "https"}

    try:
        await _reply_with_media(message, media, kind, caption, reply_markup)
        return
    except Exception as telegram_error:
        logging.getLogger(__name__).warning(
            "Telegram could not send start media (%s); attempting a local upload.",
            type(telegram_error).__name__,
        )

    if is_remote:
        local_path = None
        try:
            local_path, local_kind = await _download_start_media(str(media))
            await _reply_with_media(message, local_path, local_kind, caption, reply_markup)
            return
        except Exception as download_error:
            logging.getLogger(__name__).warning(
                "Local start-media fallback failed (%s); sending the start caption without media.",
                type(download_error).__name__,
            )
        finally:
            if local_path:
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

    await reply_panel(message,
        text=caption,
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
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

    media = pick_start_media()
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
    media = pick_start_media()
    await send_media_message(message, media, caption, buttons)


HELP_MODULE_EMOJIS = {
    "guess": "GAMEPAD",
    "harem": "USERS_GROUP",
    "profile": "USER",
    "balance": "WALLET",
    "trade": "GIFT",
    "auction": "GIFT",
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
                callback_data=f"waifuhelp:{module_name}",
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


@app.on_callback_query(filters.regex(r"^waifuhelp:([a-z0-9_]+)$"))
async def show_help(client, query: CallbackQuery):
    await asyncio.sleep(0.05)
    lang = await get_effective_lang(query)
    module_name = query.data.split(":", 1)[1]
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
