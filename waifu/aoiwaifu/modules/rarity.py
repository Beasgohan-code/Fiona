"""Show catalog counts for Fiona's active canonical rarity options."""

from aoiwaifu.unit.rich_ui import (
    reply_panel,
    premium_text,
    rich_card,
    rich_table,
    rich_progress_bar,
)
import html

from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu import app, collection, rarity_map
from pyrogram import filters, enums


@app.on_message(filters.command(["rarity", "rarities"]))
async def rarity_count(client, message):
    lang = await get_effective_lang(message)
    try:
        # Aggregate once, then render the active rarities in their configured order.
        count_rows = await collection.aggregate([
            {"$group": {"_id": "$rarity", "count": {"$sum": 1}}}
        ]).to_list(length=None)
        counts = {row.get("_id"): int(row.get("count", 0) or 0) for row in count_rows}
        configured = list(rarity_map.values())
        rows = []
        total_count = sum(counts.values())

        for rarity in configured:
            count = counts.pop(rarity, 0)
            progress = rich_progress_bar(count, total_count, 8)
            rows.append((html.escape(rarity), f"<b>{count:,}</b><br><code>{progress}</code>"))

        # Keep older catalog data visible as a count, without exposing obsolete
        # rarity names as choices or deleting character records.
        legacy_count = sum(counts.values())
        if legacy_count:
            rows.append(("Legacy / unconfigured", f"<b>{legacy_count:,}</b>"))
        rows.append(("<b>Total characters</b>", f"<b>{total_count:,}</b>"))

        card = rich_card(
            "Character catalog by rarity",
            rich_table(("RARITY", "COUNT"), rows),
            "💎",
        )
        await reply_panel(message,premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)
    except Exception:
        card = rich_card("Catalog unavailable", "Could not load rarity totals. Please try again.", "⚠️")
        await reply_panel(message,premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)
