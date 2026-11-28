"""Sell duplicate collection characters safely for a small coin refund."""

import html

from pyrogram import enums, filters

from aoiwaifu import app, user_collection
from aoiwaifu.admin.blocklist import is_user_blocklisted
from aoiwaifu.modules.shop import RARITY_PRICE
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, reply_notice, reply_panel, rich_card, rich_quote

_SELL_RATIO = 0.10
_UNKNOWN_SHOP_PRICE = 1000


def _sale_price(character: dict) -> int:
    """Return a conservative 10% rarity-based resale value in coins."""
    rarity = str(character.get("rarity") or "")
    shop_price = max(1, int(RARITY_PRICE.get(rarity, _UNKNOWN_SHOP_PRICE)))
    return max(1, int(shop_price * _SELL_RATIO))


def _partition_duplicates(characters: list) -> tuple[list, list]:
    """Keep the first copy of every character and return all later copies."""
    kept = []
    duplicates = []
    seen = set()
    for character in characters:
        if not isinstance(character, dict) or character.get("id") is None:
            kept.append(character)
            continue
        character_id = str(character["id"])
        if character_id in seen:
            duplicates.append(character)
        else:
            seen.add(character_id)
            kept.append(character)
    return kept, duplicates


def _remove_one_duplicate(characters: list, character_id: str):
    """Remove one extra copy, never the collector's last copy of a character."""
    matching = [
        index
        for index, character in enumerate(characters)
        if isinstance(character, dict) and str(character.get("id")) == str(character_id)
    ]
    if len(matching) < 2:
        return None
    sell_index = matching[-1]
    remaining = list(characters)
    sold = remaining.pop(sell_index)
    return remaining, sold


def _valid_collection(user: dict):
    characters = user.get("characters") or []
    if not isinstance(characters, list):
        return None
    return characters


async def _finish_sale(message, user: dict, before: list, after: list, sold: list[dict], lang: str):
    """Apply collection removal and coin credit together with optimistic CAS."""
    amount = sum(_sale_price(character) for character in sold)
    if not sold or amount <= 0:
        return False
    result = await user_collection.update_one(
        {"_id": user["_id"], "characters": before},
        {"$set": {"characters": after}, "$inc": {"balance": amount}},
    )
    if not result.modified_count:
        await reply_notice(
            message,
            tr("Your collection changed while this sale was processing. Please check it and try again.", lang),
        )
        return False
    updated = await user_collection.find_one({"_id": user["_id"]}, {"balance": 1}) or {}
    balance = int(updated.get("balance", 0) or 0)
    summary = (
        f"🃏 Copies sold: <b>{len(sold)}</b>\n"
        f"🪙 Coins earned: <b>+{amount:,}</b>\n"
        f"👛 New balance: <b>{balance:,}</b>\n\n"
        "One copy of every sold character remains in your collection."
    )
    await reply_panel(
        message,
        premium_text(rich_card("Duplicate sale complete", rich_quote(tr(summary, lang)), "🪙")),
        parse_mode=enums.ParseMode.HTML,
    )
    return True


@app.on_message(filters.command("sell"))
async def sell_duplicate(client, message):
    """Sell one extra copy: /sell <character_id>. Unique copies are protected."""
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    if await is_user_blocklisted(message.from_user.id):
        return await reply_notice(message, tr("🚫 Your account cannot use collection sales.", lang))
    args = message.command or []
    if len(args) != 2 or not args[1].isdigit():
        return await reply_notice(
            message,
            tr("Usage: /sell <character_id>\nOnly duplicate copies can be sold; your last copy is always protected.", lang),
        )

    user = await user_collection.find_one({"id": message.from_user.id})
    if not user:
        return await reply_notice(message, tr("Your collection is empty. Catch characters before selling duplicates.", lang))
    characters = _valid_collection(user)
    if characters is None:
        return await reply_notice(message, tr("⚠️ Your collection data is invalid. Please contact support.", lang))
    sale = _remove_one_duplicate(characters, args[1])
    if sale is None:
        return await reply_notice(
            message,
            tr("You need at least two copies of a character to sell one. Your last copy cannot be sold.", lang),
        )

    remaining, character = sale
    amount = _sale_price(character)
    name = html.escape(str(character.get("name") or "Unknown character"))
    rarity = html.escape(str(character.get("rarity") or "Unknown rarity"))
    result = await user_collection.update_one(
        {"_id": user["_id"], "characters": characters},
        {"$set": {"characters": remaining}, "$inc": {"balance": amount}},
    )
    if not result.modified_count:
        return await reply_notice(
            message,
            tr("Your collection changed while this sale was processing. Please check it and try again.", lang),
        )
    updated = await user_collection.find_one({"_id": user["_id"]}, {"balance": 1}) or {}
    balance = int(updated.get("balance", 0) or 0)
    body = (
        f"<b>{name}</b> · {rarity}\n"
        f"🪙 Sale value: <b>+{amount:,} coins</b>\n"
        f"👛 New balance: <b>{balance:,}</b>\n\n"
        "One copy remains safely in your collection."
    )
    await reply_panel(
        message,
        premium_text(rich_card("Duplicate sold", rich_quote(tr(body, lang)), "💰")),
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command("sellall"))
async def sell_all_duplicates(client, message):
    """Preview duplicates, then sell them with /sellall confirm."""
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    if await is_user_blocklisted(message.from_user.id):
        return await reply_notice(message, tr("🚫 Your account cannot use collection sales.", lang))
    args = message.command or []
    confirm = len(args) == 2 and args[1].casefold() == "confirm"
    if len(args) > 2 or (len(args) == 2 and not confirm):
        return await reply_notice(message, tr("Usage: /sellall, then /sellall confirm to complete the sale.", lang))

    user = await user_collection.find_one({"id": message.from_user.id})
    if not user:
        return await reply_notice(message, tr("Your collection is empty. Catch characters before selling duplicates.", lang))
    characters = _valid_collection(user)
    if characters is None:
        return await reply_notice(message, tr("⚠️ Your collection data is invalid. Please contact support.", lang))
    remaining, duplicates = _partition_duplicates(characters)
    if not duplicates:
        return await reply_notice(message, tr("No duplicate characters to sell. Your collection is unchanged.", lang))
    amount = sum(_sale_price(character) for character in duplicates)

    if not confirm:
        preview = (
            f"🃏 Duplicate copies: <b>{len(duplicates)}</b>\n"
            f"🪙 Estimated coins: <b>+{amount:,}</b>\n\n"
            "Your last copy of every character is protected. Review the total, then send <code>/sellall confirm</code> to continue."
        )
        return await reply_panel(
            message,
            premium_text(rich_card("Review duplicate sale", rich_quote(tr(preview, lang)), "🛡️")),
            parse_mode=enums.ParseMode.HTML,
        )

    await _finish_sale(message, user, characters, remaining, duplicates, lang)
