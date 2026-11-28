"""Collector-side collection value summary based on Fiona rarity prices."""

import html
from collections import Counter

from pyrogram import enums, filters

from aoiwaifu import app, user_collection
from aoiwaifu.admin.blocklist import is_user_blocklisted
from aoiwaifu.modules.shop import RARITY_PRICE
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, reply_notice, reply_panel, rich_card, rich_quote

_FALLBACK_RARITY_PRICE = 1000


def _coins(amount) -> str:
    return f"{max(0, int(amount or 0)):,}"


def _character_id(character: dict) -> str:
    value = str(character.get("id") or "unknown").strip()
    return str(int(value)) if value.isdigit() else value


def _rarity_price(rarity: str) -> int:
    return int(RARITY_PRICE.get(str(rarity or ""), _FALLBACK_RARITY_PRICE))


@app.on_message(filters.command(["collectionvalue", "colvalue", "haremvalue"]))
async def collection_value(client, message):
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    if await is_user_blocklisted(message.from_user.id):
        return await reply_notice(message, tr("🚫 Your account cannot view collection value.", lang))

    user = await user_collection.find_one({"id": message.from_user.id})
    if not user:
        return await reply_notice(message, tr("Use /waifu first to create your collector profile.", lang))
    characters = user.get("characters") or []
    if not isinstance(characters, list):
        return await reply_notice(message, tr("⚠️ Your collection data is invalid. Please contact support.", lang))
    if not characters:
        return await reply_notice(message, tr("Your collection is empty. Catch characters before checking its value.", lang))

    rarity_counts = Counter()
    id_counts = Counter()
    total_value = 0
    priced = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        rarity = str(character.get("rarity") or "Unknown")
        rarity_counts[rarity] += 1
        id_counts[_character_id(character)] += 1
        price = _rarity_price(rarity)
        total_value += price
        priced.append((price, character))

    if not priced:
        return await reply_notice(message, tr("⚠️ Your collection contains no valid character entries. Please contact support.", lang))

    unique_count = len(id_counts)
    duplicate_copies = sum(count - 1 for count in id_counts.values() if count > 1)
    highest_price, highest_character = max(priced, key=lambda item: item[0], default=(0, {}))
    highest_name = html.escape(str(highest_character.get("name") or "Unknown"))
    highest_rarity = html.escape(str(highest_character.get("rarity") or "Unknown"))
    top_rarity, top_rarity_count = rarity_counts.most_common(1)[0]
    top_rarity = html.escape(str(top_rarity))

    body = (
        f"🃏 Copies: <b>{len(characters):,}</b> · unique: <b>{unique_count:,}</b> · duplicates: <b>{duplicate_copies:,}</b>\n"
        f"🪙 Estimated collection value: <b>{_coins(total_value)}</b>\n"
        f"⭐ Most common rarity: <b>{top_rarity}</b> × <b>{top_rarity_count:,}</b>\n"
        f"💎 Highest-value card: <b>{highest_name}</b> · {highest_rarity} · <code>{_coins(highest_price)}</code>\n\n"
        "Value uses Fiona's rarity prices; it is an estimate, not a sale guarantee."
    )
    await reply_panel(
        message,
        premium_text(rich_card("Collection value", rich_quote(tr(body, lang)), "🧾")),
        parse_mode=enums.ParseMode.HTML,
    )
