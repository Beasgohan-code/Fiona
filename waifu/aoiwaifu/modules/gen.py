"""User character redeem command (/redeem)."""

from aoiwaifu.unit.rich_ui import (
    reply_panel,
    premium_text,
    rich_card,
    rich_table,
    reply_notice,
)
import html
from pymongo import ReturnDocument
from pyrogram import enums, filters

from aoiwaifu import ZYRO as app, collection, db, user_collection
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr


redeem_collection = db["redeem_codes"]
redeem_locks = set()


@app.on_message(filters.command("redeem"))
async def redeem_character(client, message):
    lang = await get_effective_lang(message)
    args = message.command
    if len(args) < 2:
        await reply_notice(message,
            tr("Usage: <code>/redeem &lt;code&gt;</code>", lang),
            parse_mode=enums.ParseMode.HTML,
        )
        return

    redeem_code = args[1].strip()
    user_id = message.from_user.id
    if user_id in redeem_locks:
        await reply_notice(message,
            tr("⏳ Your redeem request is already processing. Please wait!", lang),
            parse_mode=enums.ParseMode.HTML,
        )
        return

    redeem_locks.add(user_id)
    try:
        redeem_data = await redeem_collection.find_one({"code": redeem_code})
        if not redeem_data:
            await reply_notice(message,
                tr("❌ Invalid or expired redeem code.", lang),
                parse_mode=enums.ParseMode.HTML,
            )
            return
        if user_id in redeem_data.get("redeemed_by", []):
            await reply_notice(message,
                tr("❌ You have already redeemed this code.", lang),
                parse_mode=enums.ParseMode.HTML,
            )
            return
        if len(redeem_data.get("redeemed_by", [])) >= redeem_data.get("redeem_limit", 0):
            await reply_notice(message,
                tr("❌ This redeem code has reached its limit.", lang),
                parse_mode=enums.ParseMode.HTML,
            )
            return

        character = await collection.find_one({"id": redeem_data["character_id"]})
        if not character:
            await reply_notice(message, tr("❌ Character not found.", lang), parse_mode=enums.ParseMode.HTML)
            return

        claimed = await redeem_collection.find_one_and_update(
            {
                "code": redeem_code,
                "redeemed_by": {"$ne": user_id},
                "$expr": {"$lt": [{"$size": "$redeemed_by"}, "$redeem_limit"]},
            },
            {"$push": {"redeemed_by": user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            await reply_notice(message,
                tr("❌ Code limit reached or already claimed!", lang),
                parse_mode=enums.ParseMode.HTML,
            )
            return

        await user_collection.update_one(
            {"id": user_id}, {"$push": {"characters": character}}, upsert=True
        )
        char_info = rich_card(
            'Code redeemed',
            rich_table(
                ('DETAIL', 'CHARACTER'),
                [
                    ('Name', f"<b>{html.escape(str(character.get('name', 'Unknown')))}</b>"),
                    ('Anime', html.escape(str(character.get('anime', 'Unknown')))),
                    ('Rarity', html.escape(str(character.get('rarity', 'Unknown')))),
                    ('ID', f"<code>{html.escape(str(character.get('id', '?')))}</code>"),
                ],
            ) + "\nThis character has been added to your collection.",
            '🎟️',
        )
        await reply_panel(message,premium_text(tr(char_info, lang)), parse_mode=enums.ParseMode.HTML)
    finally:
        redeem_locks.discard(user_id)
