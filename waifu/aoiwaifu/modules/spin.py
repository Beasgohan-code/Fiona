"""Daily coin spin adapted to Fiona's Mongo-backed economy."""
from __future__ import annotations


from aoiwaifu.unit.rich_ui import (
    reply_panel,
    premium_text,
    rich_card,
    rich_quote,
    reply_notice,
)
import html
import random
from datetime import datetime, timedelta, timezone

from pyrogram import Client, enums, filters
from pyrogram.types import Message
from pymongo import ReturnDocument

from aoiwaifu import app, user_collection
from aoiwaifu.admin.blocklist import is_user_blocklisted
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr, tr_panel

SPIN_COOLDOWN = timedelta(hours=24)
SPIN_REWARDS = (50, 100, 250, 500, 1_000, 2_500)
SPIN_WEIGHTS = (35, 30, 18, 10, 5, 2)


def _as_utc(value) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@app.on_message(filters.command("spin"))
async def daily_spin(client: Client, message: Message):
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    user_id = int(message.from_user.id)
    if await is_user_blocklisted(user_id):
        return await reply_notice(message, tr("🚫 Your account is not eligible for economy rewards.", lang))

    # Ensure there is a document before doing the compare-and-set below.
    await user_collection.update_one(
        {"id": user_id}, {"$setOnInsert": {"id": user_id, "balance": 0}}, upsert=True
    )
    user = await user_collection.find_one({"id": user_id}, {"last_spin": 1, "balance": 1}) or {}
    now = datetime.now(timezone.utc)
    previous = user.get("last_spin")
    previous_utc = _as_utc(previous)
    if previous_utc and now < previous_utc + SPIN_COOLDOWN:
        remaining = previous_utc + SPIN_COOLDOWN - now
        hours, remainder = divmod(max(0, int(remaining.total_seconds())), 3600)
        minutes = remainder // 60
        card = rich_card(
            "Daily spin used",
            rich_quote(f"🕓 Your next spin is ready in <b>{hours}h {minutes}m</b>."),
            "⏳",
        )
        return await reply_panel(message,premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)

    reward = random.choices(SPIN_REWARDS, weights=SPIN_WEIGHTS, k=1)[0]
    claim_filter = {"id": user_id}
    claim_filter["last_spin"] = previous if "last_spin" in user else {"$exists": False}
    updated = await user_collection.find_one_and_update(
        claim_filter,
        {"$set": {"last_spin": now}, "$inc": {"balance": reward}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        card = rich_card(
            "Spin already claimed",
            rich_quote("A spin was recorded for your account. Check again tomorrow."),
            "⏳",
        )
        return await reply_panel(message,premium_text(tr(card, lang)), parse_mode=enums.ParseMode.HTML)

    first_name = html.escape(message.from_user.first_name or "Collector")
    new_balance = int(updated.get("balance", 0) or 0)
    body = "\n\n".join(
        (
            rich_quote(f"🎉 <b>{first_name}</b>, the wheel chose you!"),
            rich_quote(
                f"🏆 Payout: <b>+{reward:,} coins</b>\n"
                f"💰 Wallet balance: <code>{new_balance:,}</code>"
            ),
            "<i>Your next spin unlocks in 24 hours. Good luck next time!</i>",
        )
    )
    await reply_panel(message,
        premium_text(tr_panel(rich_card("Daily spin", body, "🎰"), lang)),
        parse_mode=enums.ParseMode.HTML,
    )
