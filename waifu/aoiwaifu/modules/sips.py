"""Search the character catalog with a compact, paginated rich card."""

import html
import re

from aoiwaifu import app, collection, rarity_map2 as rarity_map
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import edit_panel, premium_button, premium_text, rich_card
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup


async def handle_search(client, message, query=None, page=1, is_callback=False):
    lang = await get_effective_lang(message)
    try:
        if not query:
            args = message.command
            if len(args) < 2:
                await message.reply_text(tr("Please provide a character name. Usage: /sips {character name}", lang))
                return
            query = " ".join(args[1:]).strip()
        page = max(1, int(page))
        per_page = 10
        skip = (page - 1) * per_page
        safe_query = re.escape(query)
        search = {"name": {"$regex": safe_query, "$options": "i"}}
        total_characters = await collection.count_documents(search)
        if total_characters == 0:
            text = premium_text(rich_card("Character search", f"No matches for <b>{html.escape(query)}</b>. Try another name.", "🔎"))
            if is_callback:
                await edit_panel(message, text, reply_markup=None)
            else:
                await message.reply_text(text, parse_mode=ParseMode.HTML)
            return

        characters = await collection.find(search).skip(skip).limit(per_page).to_list(length=per_page)
        lines = [f"<b>{total_characters:,} matches</b> · page {page}\n"]
        for index, character in enumerate(characters, start=1 + skip):
            rarity = html.escape(str(character.get("rarity", "Unknown")))
            rarity_emoji = rarity_map.get(character.get("rarity"), "❓")
            name = html.escape(str(character.get("name", "Unknown")))
            anime = html.escape(str(character.get("anime", "Unknown")))
            character_id = html.escape(str(character.get("id", "?")))
            lines.append(
                f"{index}. {rarity_emoji} <b>{name}</b> · <i>{anime}</i>\n"
                f"   {rarity} · ID <code>{character_id}</code>"
            )
        response = premium_text(rich_card("Character search", "\n".join(lines), "🔎"))
        buttons = []
        if page > 1:
            buttons.append(premium_button("Previous", emoji="LEFT_CHEVRON", callback_data=f"sips:{query}:{page - 1}"))
        if skip + per_page < total_characters:
            buttons.append(premium_button("Next", emoji="RIGHT_CHEVRON", callback_data=f"sips:{query}:{page + 1}"))
        rows = [buttons] if buttons else []
        rows.append([premium_button("View inline", emoji="SEARCH", switch_inline_query_current_chat=f"see.{query}.{page}")])
        reply_markup = InlineKeyboardMarkup(rows)
        if is_callback:
            await edit_panel(message, response, reply_markup)
        else:
            await message.reply_text(response, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as exc:
        error_message = premium_text(rich_card("Search unavailable", "Could not load these results. Please try again.", "⚠️"))
        if is_callback:
            await edit_panel(message, error_message)
        else:
            await message.reply_text(error_message, parse_mode=ParseMode.HTML)


@app.on_message(filters.command("sips"))
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
