from aoiwaifu.unit.aoi_lang import get_user_lang, get_chat_lang, get_effective_lang, set_user_lang, set_chat_lang, has_user_set_lang, t, tr
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from aoiwaifu.unit.aoi_inline import get_all_characters
from aoiwaifu.unit.rich_ui import premium_text, rich_card, rich_table
from aoiwaifu import app

@app.on_message(filters.command('total'))
async def total_characters(client: Client, message: Message):
    lang = await get_effective_lang(message)
    try:
        all_characters = await get_all_characters()
        unique_characters = len({char['id']: char for char in all_characters if 'id' in char})
        card = rich_card(
            'Fiona character catalog',
            rich_table(('STATISTIC', 'COUNT'), [('Unique characters', f'<b>{unique_characters:,}</b>')]),
            '📚',
        )
        await message.reply_text(premium_text(tr(card, lang)), parse_mode=ParseMode.HTML)
    except Exception:
        card = rich_card('Catalog unavailable', 'Could not load the character total. Please try again.', '⚠️')
        await message.reply_text(premium_text(tr(card, lang)), parse_mode=ParseMode.HTML)
