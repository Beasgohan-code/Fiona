"""Public leaderboard and community score commands (/TopGroups, /ctop, /st)."""

from aoiwaifu.unit.rich_ui import (
    reply_panel,
    reply_photo_panel,
    premium_text,
    rich_card,
    rich_table,
)
import html
from pyrogram import Client, enums, filters
from pyrogram.types import Message

from aoiwaifu import (
    PHOTO_URL,
    app,
    group_user_totals_collection,
    top_global_groups_collection,
    user_collection,
)
from aoiwaifu.admin.blocklist import get_blocklisted_id_variants
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr, tr_panel


def _photo_url():
    return PHOTO_URL[0] if PHOTO_URL else None


def _medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"<code>{rank:02}</code>")


def _rank_rows(items, value_key, *, name_key="group_name", name_limit=20):
    rows = []
    for rank, item in enumerate(items, start=1):
        raw_name = str(item.get(name_key) or "Unknown")
        if len(raw_name) > name_limit:
            raw_name = raw_name[: name_limit - 1] + "…"
        name = html.escape(raw_name)
        value = int(item.get(value_key) or 0)
        rows.append((_medal(rank), f"<b>{name}</b>", f"<b>{value:,}</b>"))
    return rows


def _rank_caption(title, eyebrow, rows, empty_message, footer):
    if not rows:
        return rich_card(title, f"<i>{empty_message}</i>", "🏆")
    body = "\n\n".join((
        f"<i>{html.escape(eyebrow)}</i>",
        rich_table(("RANK", "NAME", "SCORE"), rows),
        f"<i>{html.escape(footer)}</i>",
    ))
    return rich_card(title, body, "🏆")


async def _reply_rank_card(message, lang, caption):
    text = premium_text(tr(caption, lang))
    photo = _photo_url()
    if photo:
        try:
            return await reply_photo_panel(message, photo=photo, caption=text, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
    return await reply_panel(message, text, parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command("TopGroups"))
async def global_leaderboard(client: Client, message: Message):
    try:
        lang = await get_effective_lang(message)
        cursor = top_global_groups_collection.aggregate(
            [
                {"$project": {"group_name": 1, "count": 1}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ]
        )
        leaderboard_data = await cursor.to_list(length=10)
        rows = _rank_rows(leaderboard_data, "count", name_key="group_name")
        leaderboard_message = _rank_caption(
            "TOP 10 GROUPS",
            "Communities that guessed the most characters",
            rows,
            "No group rankings yet. Be the first community on the board!",
            "Keep playing together — every correct guess lifts the group.",
        )
        await _reply_rank_card(message, lang, leaderboard_message)
    except Exception:
        lang = await get_effective_lang(message)
        await reply_panel(message, premium_text(rich_card("Leaderboard unavailable", "Could not load the group rankings right now. Please try again.", "⚠️")), parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command("ctop"))
async def ctop(client: Client, message: Message):
    try:
        lang = await get_effective_lang(message)
        chat_id = message.chat.id
        blocked_ids = await get_blocklisted_id_variants()
        blocked_docs = await user_collection.find({"id": {"$in": blocked_ids}}, {"username": 1}).to_list(length=None)
        blocked_names = {str(u.get("username") or "").lstrip("@").lower() for u in blocked_docs}

        cursor = group_user_totals_collection.aggregate(
            [
                {"$match": {"group_id": chat_id, "username": {"$nin": list(blocked_names)}}},
                {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
                {"$sort": {"character_count": -1}},
                {"$limit": 10},
            ]
        )
        leaderboard_data = await cursor.to_list(length=10)
        rows = []
        for rank, user in enumerate(leaderboard_data, start=1):
            username = str(user.get("username") or "").lstrip("@")
            raw_name = str(user.get("first_name") or "Unknown")
            if len(raw_name) > 18:
                raw_name = raw_name[:17] + "…"
            first_name = html.escape(raw_name)
            if username and username != "Unknown":
                profile = f'<a href="https://t.me/{html.escape(username, quote=True)}"><b>{first_name}</b></a>'
            else:
                profile = f"<b>{first_name}</b>"
            rows.append((_medal(rank), profile, f"<b>{int(user.get('character_count') or 0):,}</b>"))
        leaderboard_message = _rank_caption(
            "GROUP CHALLENGERS",
            "Most characters guessed in this group",
            rows,
            "No guesses in this group yet. Be the first!",
            "Every guess sharpens your eye — climb this group's board.",
        )
        await _reply_rank_card(message, lang, leaderboard_message)
    except Exception:
        lang = await get_effective_lang(message)
        await reply_panel(message, premium_text(rich_card("Leaderboard unavailable", "Could not load this group's rankings right now. Please try again.", "⚠️")), parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command(["st", "server"]))
async def stats(client: Client, message: Message):
    lang = await get_effective_lang(message)
    user_count = await user_collection.count_documents({})
    group_ids = await group_user_totals_collection.distinct("group_id")
    group_count = len(group_ids or [])
    body = rich_table(
        ("METRIC", "TOTAL"),
        (
            ("👥 Collectors", f"<b>{user_count:,}</b>"),
            ("🌐 Active groups", f"<b>{group_count:,}</b>"),
        ),
    )
    await reply_panel(
        message,
        premium_text(tr_panel(rich_card("Fiona community", body, "📊"), lang)),
        parse_mode=enums.ParseMode.HTML,
    )
