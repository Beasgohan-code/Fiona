"""Show catalog size by rarity in a compact Richgram-style card."""

import html

from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, rich_card, rich_table
from aoiwaifu import app, collection
from pyrogram import filters, enums


@app.on_message(filters.command("rarity"))
async def rarity_count(client, message):
    lang = await get_effective_lang(message)
    try:
        rarities = await collection.distinct("rarity")
        if not rarities:
            return await message.reply_text(
                premium_text(rich_card("Rarity catalog", "No rarities are available yet.", "⚠️")),
                parse_mode=enums.ParseMode.HTML,
            )

        rows = []
        total_count = 0
        for rarity in sorted(rarities, key=lambda value: str(value).casefold()):
            count = await collection.count_documents({"rarity": rarity})
            total_count += count
            rows.append((html.escape(str(rarity)), f"<b>{count:,}</b>"))
        rows.append(("<b>Total characters</b>", f"<b>{total_count:,}</b>"))
        card = rich_card("Character catalog by rarity", rich_table(("RARITY", "COUNT"), rows), "💎")
        await message.reply_text(premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)
    except Exception:
        card = rich_card("Catalog unavailable", "Could not load rarity totals. Please try again.", "⚠️")
        await message.reply_text(premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)
