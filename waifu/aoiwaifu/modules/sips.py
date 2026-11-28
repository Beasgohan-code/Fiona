"""Search the character catalog with a polished, paginated rich card."""

from aoiwaifu.unit.rich_ui import (
    reply_panel,
    reply_photo_panel,
    edit_panel,
    premium_button,
    premium_text,
    rich_card,
    rich_progress_bar,
    reply_notice,
)
import html
import re

from aoiwaifu import app, collection, rarity_map2 as rarity_map
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup


def _pagination_pages(total: int, per_page: int) -> int:
    if total <= 0:
        return 1
    return max(1, (total + per_page - 1) // per_page)


def _http_image_url(character: dict) -> str | None:
    for key in ("img_url", "image_url", "image", "url"):
        value = str((character or {}).get(key) or "").strip()
        if value.startswith("https://") or value.startswith("http://"):
            return value
    return None


def _first_image(characters: list[dict]) -> str | None:
    for character in characters:
        if isinstance(character, dict):
            image = _http_image_url(character)
            if image:
                return image
    return None


def _search_caption(query: str, total: int, page: int, pages: int, characters: list[dict], skip: int):
    lines = [
        f"🔎 <b>{total:,}</b> matches for <b>{html.escape(query)}</b>",
        f"Page <code>{page}/{pages}</code> · <code>{rich_progress_bar(page, pages, 10)}</code>",
        "",
    ]
    for index, character in enumerate(characters, start=1 + skip):
        rarity = html.escape(str(character.get("rarity", "Unknown")))
        rarity_emoji = html.escape(str(rarity_map.get(character.get("rarity"), "❓")))
        name = html.escape(str(character.get("name", "Unknown")))
        anime = html.escape(str(character.get("anime", "Unknown")))
        character_id = html.escape(str(character.get("id", "?")))
        image_hint = "🖼" if _http_image_url(character) else ""
        lines.append(
            f"<b><code>{index:02}</code></b> {rarity_emoji} <b>{name}</b> {image_hint}<br>"
            f"<i>{rarity}</i> · <i>{anime}</i> · ID <code>{character_id}</code>"
        )
    return rich_card("Character search", "<blockquote>" + "<br><br>".join(lines) + "</blockquote>", "🔎")


async def handle_search(client, message, query=None, page=1, is_callback=False):
    lang = await get_effective_lang(message)
    try:
        if not query:
            args = message.command
            if len(args) < 2:
                await reply_notice(message, tr("Please provide a character name. Usage: /sips {character name}", lang))
                return
            query = " ".join(args[1:]).strip()
        page = max(1, int(page))
        per_page = 10
        skip = (page - 1) * per_page
        safe_query = re.escape(query)
        search = {"name": {"$regex": safe_query, "$options": "i"}}
        total_characters = await collection.count_documents(search)
        if total_characters == 0:
            text = premium_text(rich_card("Character search", f"No matches for <b>{html.escape(query)}</b>.<br>Try a different name, spelling, or series.", "🔎"))
            if is_callback:
                await edit_panel(message, text, reply_markup=None)
            else:
                await reply_panel(message, text, parse_mode=ParseMode.HTML)
            return

        pages = _pagination_pages(total_characters, per_page)
        page = min(page, pages)
        skip = (page - 1) * per_page
        characters = await collection.find(search).skip(skip).limit(per_page).to_list(length=per_page)
        response = premium_text(tr(_search_caption(query, total_characters, page, pages, characters, skip), lang))

        nav = []
        if page > 1:
            nav.append(premium_button("Previous", emoji="LEFT_CHEVRON", callback_data=f"sips:{query}:{page - 1}"))
        nav.append(premium_button(f"{page}/{pages}", emoji="GRID", callback_data=f"sips:{query}:{page}"))
        if skip + per_page < total_characters:
            nav.append(premium_button("Next", emoji="RIGHT_CHEVRON", callback_data=f"sips:{query}:{page + 1}"))
        rows = [nav]
        rows.append([premium_button("View inline", emoji="SEARCH", switch_inline_query_current_chat=f"see.{query}.{page}")])
        reply_markup = InlineKeyboardMarkup(rows)

        if is_callback:
            await edit_panel(message, response, reply_markup)
            return

        image_url = _first_image(characters)
        if image_url:
            try:
                await reply_photo_panel(message, photo=image_url, caption=response, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass
        await reply_panel(message, response, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception:
        error_message = premium_text(rich_card("Search unavailable", "Could not load these results. Please try again.", "⚠️"))
        if is_callback:
            await edit_panel(message, error_message)
        else:
            await reply_panel(message, error_message, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["sips", "search"]))
async def search_characters(client, message):
    await handle_search(client, message)


@app.on_callback_query(filters.regex(r"^sips:(.+):(\d+)$"))
async def handle_pagination(client, callback_query):
    try:
        data = callback_query.data.split(":")
        query = ":".join(data[1:-1])
        page = int(data[-1])
        await handle_search(client, callback_query.message, query=query, page=page, is_callback=True)
    finally:
        await callback_query.answer()
