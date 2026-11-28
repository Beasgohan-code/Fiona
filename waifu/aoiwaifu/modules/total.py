from aoiwaifu.unit.rich_ui import (
    reply_panel,
    premium_text,
    rich_card,
    rich_table,
)
from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from aoiwaifu import app, collection

from cachetools import TTLCache

# Character IDs are unique by construction; count via distinct('id') instead of
# streaming every document. Cached briefly — the catalog barely changes.
_unique_total_cache: TTLCache = TTLCache(maxsize=1, ttl=300)


async def _unique_character_total() -> int:
    cached = _unique_total_cache.get("total")
    if cached is None:
        ids = await collection.distinct("id")
        cached = len(ids)
        _unique_total_cache["total"] = cached
    return cached


@app.on_message(filters.command('total'))
async def total_characters(client: Client, message: Message):
    lang = await get_effective_lang(message)
    try:
        unique_characters = await _unique_character_total()
        card = rich_card(
            'Fiona character catalog',
            rich_table(('STATISTIC', 'COUNT'), [('Unique characters', f'<b>{unique_characters:,}</b>')]),
            '📚',
        )
        await reply_panel(message,premium_text(tr(card, lang)), parse_mode=ParseMode.HTML)
    except Exception:
        card = rich_card('Catalog unavailable', 'Could not load the character total. Please try again.', '⚠️')
        await reply_panel(message,premium_text(tr(card, lang)), parse_mode=ParseMode.HTML)
