"""User collector profile and statistics (/profile, /stats)."""

import html
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

import aiohttp
from pyrogram import Client, enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message

from aoiwaifu import STATS_IMG, app, collection, rarity_map, rarity_map2, user_collection
from aoiwaifu.admin.blocklist import get_blocklisted_id_variants, is_user_blocklisted
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.profile_card import build_profile_card
from aoiwaifu.unit.rich_ui import edit_panel, premium_button, premium_text, rich_card, rich_heading, rich_table


MAX_FEATURED_IMAGE_BYTES = 5 * 1024 * 1024


async def _fetch_featured_image(url: str | None) -> bytes | None:
    """Fetch a bounded HTTPS image for the profile artwork; fail closed on bad media."""
    if not url or not isinstance(url, str):
        return None
    try:
        url = url.strip()
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        timeout = aiohttp.ClientTimeout(total=5, connect=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    return None
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if not content_type.startswith("image/"):
                    return None
                length = response.content_length
                if length is not None and length > MAX_FEATURED_IMAGE_BYTES:
                    return None
                image_data = await response.content.read(MAX_FEATURED_IMAGE_BYTES + 1)
                if len(image_data) > MAX_FEATURED_IMAGE_BYTES:
                    return None
                return image_data
    except Exception:
        return None


async def _resolve_profile_portrait(client: Client, user_id: int, favorite_url: str | None):
    """Prefer favorite artwork, then the target user's Telegram profile photo."""
    favorite_image = await _fetch_featured_image(favorite_url)
    if favorite_image:
        return favorite_image, "favorite"

    try:
        telegram_user = await client.get_users(user_id)
        photo = getattr(telegram_user, "photo", None)
        file_id = getattr(photo, "big_file_id", None) or getattr(photo, "small_file_id", None)
        if not file_id:
            return None, None
        downloaded = await client.download_media(file_id, in_memory=True)
        if hasattr(downloaded, "getvalue"):
            image_data = downloaded.getvalue()
        elif isinstance(downloaded, bytes):
            image_data = downloaded
        else:
            image_data = None
        if image_data and len(image_data) <= MAX_FEATURED_IMAGE_BYTES:
            return image_data, "profile"
    except Exception:
        pass
    return None, None


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


async def get_user_stats(user_id: int, username: str = "", first_name: str = "Collector"):
    """Fetch complete Waifu Collector profile data for a user."""
    user_doc = await user_collection.find_one({"id": user_id}) or {}
    username = username or str(user_doc.get("username") or "")
    balance = int(user_doc.get("balance") or 0)
    tokens = int(user_doc.get("tokens") or 0)
    raw_first_name = str(user_doc.get("first_name") or first_name or "Collector")
    escaped_first_name = html.escape(raw_first_name)

    raw_characters = user_doc.get("characters") or []
    characters = [c for c in raw_characters if isinstance(c, dict) and c.get("id") is not None]
    total_characters = await collection.count_documents({})
    character_count = len(characters)
    unique_character_count = len({str(c.get("id")) for c in characters})
    progress_percentage = min(
        100.0, (unique_character_count / total_characters * 100.0) if total_characters > 0 else 0.0
    )

    progress_bar_length = 10
    filled_slots = min(progress_bar_length, int(progress_percentage / 100.0 * progress_bar_length))
    progress_bar = "█" * filled_slots + "□" * (progress_bar_length - filled_slots)

    last_daily = _date_value(user_doc.get("last_daily"))
    stored_streak = max(0, int(user_doc.get("daily_streak", 0) or 0))
    daily_streak = stored_streak if last_daily in {date.today(), date.today() - timedelta(days=1)} else 0
    best_daily_streak = max(daily_streak, int(user_doc.get("longest_daily_streak", 0) or 0))

    blocked_ids = await get_blocklisted_id_variants()
    user_is_blocklisted = await is_user_blocklisted(user_id)
    cursor = user_collection.find({"id": {"$nin": blocked_ids}}, {"_id": 0, "id": 1, "characters": 1})
    all_users = await cursor.to_list(length=None)
    all_users.sort(
        key=lambda x: len(x.get("characters") or []) if isinstance(x.get("characters"), list) else 0,
        reverse=True,
    )
    total_users = len(all_users)
    rank = (
        None
        if user_is_blocklisted
        else next((i + 1 for i, u in enumerate(all_users) if str(u.get("id")) == str(user_id)), None)
    )

    rarity_counts = {rarity: 0 for rarity in rarity_map.values()}
    legacy_rarity_count = 0
    for char in characters:
        rarity = char.get("rarity")
        if rarity in rarity_counts:
            rarity_counts[rarity] += 1
        else:
            legacy_rarity_count += 1
    if legacy_rarity_count:
        rarity_counts["Legacy / unconfigured"] = legacy_rarity_count

    # Feature the explicitly selected /fav character; keep a separate safe photo fallback.
    featured_character = None
    featured_photo_url = None
    favorites = user_doc.get("favorites") or []
    if favorites:
        favorite_id = str(favorites[0])
        favorite = next(
            (c for c in characters if str(c.get("id")) == favorite_id),
            None,
        )
        if favorite:
            featured_character = {
                "id": str(favorite.get("id", "")),
                "name": str(favorite.get("name") or "Unknown"),
                "anime": str(favorite.get("anime") or "Your collection"),
                "rarity": str(favorite.get("rarity") or ""),
            }
            featured_photo_url = favorite.get("img_url") or favorite.get("image") or favorite.get("url")
    first_img = next(
        (
            c.get("img_url") or c.get("image") or c.get("url")
            for c in characters
            if c.get("img_url") or c.get("image") or c.get("url")
        ),
        None,
    )
    fav_photo = featured_photo_url or first_img or STATS_IMG[0]

    return (
        {
            "user_id": user_id,
            "first_name": escaped_first_name,
            "balance": balance,
            "tokens": tokens,
            "character_count": character_count,
            "unique_character_count": unique_character_count,
            "total_characters": total_characters,
            "progress_percentage": progress_percentage,
            "progress_bar": progress_bar,
            "daily_streak": daily_streak,
            "best_daily_streak": best_daily_streak,
            "rank": rank,
            "total_users": total_users,
            "rarity_counts": rarity_counts,
            "photo_url": fav_photo,
            "username": username or "",
            "featured_character": featured_character,
            "featured_photo_url": featured_photo_url,
        },
        None,
    )


def _build_profile_view(stats: dict, lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    """Single source of truth for /profile and profile_refresh caption & keyboard."""
    global_rank = f"#{stats['rank']} / {stats['total_users']}" if stats.get("rank") else "Unranked"
    caption = rich_card(
        "Collector profile",
        "\n".join((
            f"👤 <b>Name:</b> {stats['first_name']}",
            f"🆔 <b>User ID:</b> <code>{stats['user_id']}</code>",
            f"🏆 <b>Global rank:</b> <code>{global_rank}</code>",
            "",
            f"💰 <b>Coins:</b> <code>{stats['balance']:,}</code>",
            f"🪙 <b>Tokens:</b> <code>{stats['tokens']:,}</code>",
            "",
            f"🎴 <b>Total waifus:</b> <code>{stats['character_count']:,}</code>",
            f"✨ <b>Unique:</b> <code>{stats['unique_character_count']:,} / {stats['total_characters']:,}</code>",
            f"📊 <b>Progress:</b> <code>{stats['progress_bar']}</code> ({stats['progress_percentage']:.1f}%)",
            f"🔥 <b>Daily streak:</b> <code>{stats.get('daily_streak', 0)} days</code> · Best <code>{stats.get('best_daily_streak', 0)}</code>",
        )),
        "🌸",
    )

    non_zero_rarities = [(rarity, count) for rarity, count in stats["rarity_counts"].items() if count > 0]
    if non_zero_rarities:
        caption += f"\n\n{rich_heading('RARITY BREAKDOWN', '💎')}\n"
        caption += rich_table(
            ('RARITY', 'CHARACTERS'),
            [
                (f"{rarity_map2.get(rarity, '🗂️')} {html.escape(str(rarity))}", f"<b>{count:,}</b>")
                for rarity, count in non_zero_rarities
            ],
        )


    uid = stats["user_id"]
    keyboard = InlineKeyboardMarkup(
        [
            [
                premium_button(
                    f"Harem ({stats['character_count']})",
                    emoji="USERS_GROUP",
                    switch_inline_query_current_chat=f"collection.{uid}",
                ),
                premium_button(
                    tr("Refresh", lang),
                    emoji="REFRESH",
                    callback_data=f"profile_refresh:{uid}",
                ),
            ]
        ]
    )
    return premium_text(tr(caption, lang)), keyboard


async def _resolve_target_user(client: Client, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        return (u.id, u.username or "", u.first_name or "Collector")
    if len(message.command) > 1:
        arg = message.command[1].strip()
        if arg.lstrip("-").isdigit():
            uid = int(arg)
            db_user = await user_collection.find_one({"id": uid})
            if db_user:
                return (uid, db_user.get("username") or "", db_user.get("first_name") or "Collector")
            try:
                tg_u = await client.get_users(uid)
                return (tg_u.id, tg_u.username or "", tg_u.first_name or "Collector")
            except Exception:
                return (uid, "", f"User {uid}")
        else:
            clean_uname = arg.lstrip("@")
            db_user = await user_collection.find_one(
                {"username": {"$regex": f"^{clean_uname}$", "$options": "i"}}
            )
            if db_user and db_user.get("id"):
                return (
                    int(db_user["id"]),
                    db_user.get("username") or clean_uname,
                    db_user.get("first_name") or clean_uname,
                )
            try:
                tg_u = await client.get_users(arg)
                return (tg_u.id, tg_u.username or "", tg_u.first_name or "Collector")
            except Exception:
                pass
    u = message.from_user
    return (u.id, u.username or "", u.first_name or "Collector")


@app.on_message(filters.command(["profile", "me", "hstats"]))
async def profile_and_stats_handler(client: Client, message: Message):
    lang = await get_effective_lang(message)
    target_user_id, target_username, target_first_name = await _resolve_target_user(client, message)
    stats, error = await get_user_stats(
        target_user_id, username=target_username, first_name=target_first_name
    )
    if error or not stats:
        await message.reply_text(
            premium_text(tr(error or "Unable to load profile.", lang)),
            parse_mode=enums.ParseMode.HTML,
        )
        return

    caption, keyboard = _build_profile_view(stats, lang=lang)
    try:
        featured_image, portrait_kind = await _resolve_profile_portrait(
            client, target_user_id, stats.get("featured_photo_url")
        )
        stats["portrait_kind"] = portrait_kind
        card = build_profile_card(stats, featured_image=featured_image)
        await message.reply_photo(
            photo=card,
            caption=caption,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        try:
            await message.reply_photo(
                photo=stats["photo_url"] or STATS_IMG[0],
                caption=caption,
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            await message.reply_text(
                caption,
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True,
            )


@app.on_callback_query(filters.regex(r"^profile_refresh:(\d+)$"))
async def profile_refresh_callback(client: Client, callback_query: CallbackQuery):
    lang = await get_effective_lang(callback_query)
    try:
        target_user_id = int(callback_query.matches[0].group(1))
        await callback_query.answer(tr("🔄 Refreshing profile...", lang))
        stats, error = await get_user_stats(target_user_id)
        if error or not stats:
            return
        caption, keyboard = _build_profile_view(stats, lang=lang)
        featured_image, portrait_kind = await _resolve_profile_portrait(
            client, target_user_id, stats.get("featured_photo_url")
        )
        stats["portrait_kind"] = portrait_kind
        card = build_profile_card(stats, featured_image=featured_image)
        try:
            await callback_query.message.edit_media(
                media=InputMediaPhoto(
                    media=card,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception:
            await edit_panel(callback_query.message, caption, keyboard)
    except Exception:
        pass
