"""Collector milestones derived from Fiona's existing Mongo user documents."""

import html

from pyrogram import Client, enums, filters
from pyrogram.types import Message

from aoiwaifu import app, user_collection
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, rich_card, rich_table


@app.on_message(filters.command(["achievements", "ach", "badges"]))
async def achievements(client: Client, message: Message):
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    user = await user_collection.find_one({"id": message.from_user.id}) or {}
    characters = [
        item for item in (user.get("characters") or [])
        if isinstance(item, dict) and item.get("id") is not None
    ]
    unique_count = len({str(item["id"]) for item in characters})
    rarities = {str(item.get("rarity")) for item in characters if item.get("rarity")}
    balance = int(user.get("balance") or 0)
    referrals = int(user.get("referrals_count") or 0)

    milestones = (
        ("First catch", len(characters), 1, "🎴"),
        ("Collector", unique_count, 10, "🌱"),
        ("Dedicated collector", unique_count, 50, "🌟"),
        ("Rarity explorer", len(rarities), 5, "💎"),
        ("Coin keeper", balance, 10_000, "💰"),
        ("Friend inviter", referrals, 1, "🤝"),
        ("Community builder", referrals, 10, "👑"),
    )
    rows = [
        (
            f"{icon} {html.escape(name)}",
            f"{'✅' if progress >= goal else '🔒'} <code>{progress:,}/{goal:,}</code>",
        )
        for name, progress, goal, icon in milestones
    ]
    unlocked = sum(progress >= goal for _, progress, goal, _ in milestones)
    card = rich_card(
        "Collector achievements",
        f"<b>{unlocked}/{len(milestones)}</b> milestones reached\n\n"
        + rich_table(("MILESTONE", "PROGRESS"), rows),
        "🏅",
    )
    await message.reply_text(premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)
