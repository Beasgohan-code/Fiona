"""Character auctions backed by MongoDB.

Auction escrow is held by the auction document: every accepted bid is debited
from the bidder before the auction CAS wins, the previous highest bidder is
refunded immediately after the CAS, and non-winning bids are always returned.
Auctions close through an idempotent settlement path so retries cannot merge a
payout or duplicate an escrowed character copy.
"""

import asyncio
import html
import logging
import time
import uuid

from pyrogram import enums, filters
from pyrogram.types import InlineKeyboardMarkup

from aoiwaifu import app, db, user_collection
from aoiwaifu.admin.blocklist import is_user_blocklisted
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import (
    edit_panel,
    premium_button,
    premium_text,
    reply_notice,
    reply_panel,
    reply_photo_panel,
    rich_card,
    rich_quote,
    send_panel,
)

LOGGER = logging.getLogger(__name__)

auctions_collection = db["character_auctions"]
pending_refunds_collection = db["auction_refund_queue"]

_AUCTION_DURATION_DEFAULT = 30
_AUCTION_DURATION_MIN = 5
_AUCTION_DURATION_MAX = 180
_MIN_STARTING_BID = 100
_MIN_BID_INCREMENT = 100
_ANTI_SNIPE_WINDOW = 60
_ANTI_SNIPE_EXTENSION = 60
_QUICK_BIDS = (500, 1000, 5000, 10000)
_ACTIVE_LIST_LIMIT = 8
_REAPER_INTERVAL = 30
_STALE_CLAIM_SECONDS = 300

_indexes_ready = False
_reaper_task = None


def _now() -> float:
    return time.time()


def _format_coins(amount) -> str:
    try:
        value = max(0, int(amount or 0))
    except (TypeError, ValueError):
        value = 0
    return f"{value:,}"


def _parse_integer(value, *, default=None, minimum=None, maximum=None):
    raw = str(value if value is not None else "").strip().replace(",", "").replace("_", "")
    if not raw:
        return default
    try:
        number = int(raw)
    except ValueError:
        return default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _time_left(seconds) -> str:
    remaining = max(0, int(seconds))
    hours, rem = divmod(remaining, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def _character_id_text(value) -> str:
    value = str(value or "").strip()
    return str(int(value)) if value.isdigit() else value


def _character_id_candidates(value) -> list:
    raw = str(value or "").strip()
    candidates = [raw]
    if raw.isdigit():
        candidates.extend((raw.zfill(2), int(raw)))
    return list(dict.fromkeys(candidates))


def _character_name(character: dict) -> str:
    return html.escape(str((character or {}).get("name") or "Unknown character"))


def _character_rarity(character: dict) -> str:
    return html.escape(str((character or {}).get("rarity") or "Unknown rarity"))


def _auction_code(auction_id: str) -> str:
    return html.escape(str(auction_id or "unknown")[:12])


def _remove_character_copy(characters: list, character_id):
    query_ids = set(_character_id_candidates(character_id)) | {_character_id_text(character_id), str(character_id)}
    for index, character in enumerate(characters):
        if not isinstance(character, dict):
            continue
        character_ids = set(_character_id_candidates(character.get("id"))) | {_character_id_text(character.get("id")), str(character.get("id"))}
        if query_ids & character_ids:
            removed = characters[index]
            return list(characters[:index]) + list(characters[index + 1:]), removed
    return None


def _minimum_absolute_bid(auction: dict) -> int:
    current_bid = int(auction.get("current_bid") or auction.get("start_price") or 0)
    if auction.get("highest_bidder_id") is None:
        return int(auction.get("start_price") or _MIN_STARTING_BID)
    return current_bid + _MIN_BID_INCREMENT


def _target_bid(auction: dict, increment: int | None = None, absolute: int | None = None) -> int:
    current_bid = int(auction.get("current_bid") or auction.get("start_price") or 0)
    if increment is not None:
        return current_bid + int(increment)
    return int(absolute or 0)


def _bid_keyboard(auction_id: str):
    code = str(auction_id)[:48]
    buttons = [
        premium_button(f"+{_format_coins(amount)}", emoji="COIN", style="PRIMARY", callback_data=f"auction_bid_{code}_{amount}")
        for amount in _QUICK_BIDS
    ]
    return InlineKeyboardMarkup([
        [buttons[0], buttons[1]],
        [buttons[2], buttons[3]],
        [
            premium_button("Custom bid", emoji="EDIT_PENCIL", callback_data=f"auction_custom_{code}"),
            premium_button("Refresh", emoji="REFRESH", callback_data=f"auction_refresh_{code}"),
        ],
    ])


def _list_keyboard(auctions: list):
    rows = []
    for auction in auctions:
        code = str(auction.get("auction_id"))[:12]
        label = str((auction.get("character") or {}).get("name") or f"#{code}")[:22]
        rows.append([
            premium_button(f"View #{code} · {label}", emoji="INFO", callback_data=f"auction_view_{code}"),
        ])
    return InlineKeyboardMarkup(rows) if rows else None


def _auction_body(auction: dict, *, include_footer: bool = True) -> str:
    character = auction.get("character") or {}
    name = _character_name(character)
    anime = html.escape(str(character.get("anime") or "Unknown series"))
    rarity = _character_rarity(character)
    seller_id = html.escape(str(auction.get("seller_id") or ""))
    high_bidder = auction.get("highest_bidder_id")
    current_bid = _format_coins(auction.get("current_bid") or auction.get("start_price"))
    remaining = _time_left(float(auction.get("ends_at") or 0) - _now())
    code = _auction_code(auction.get("auction_id"))
    if high_bidder:
        leader_name = html.escape(str(auction.get("highest_bidder_name") or "Collector"))
        leader = f"👑 Leading: <b>{leader_name}</b>"
    else:
        leader = "👑 Leading: <i>No bids yet</i>"
    lines = [
        f"🎴 <b>{name}</b>\n⛩️ <i>{anime}</i>\n⭐ Rarity: <b>{rarity}</b>\n",
        f"🏷 Starting bid: <code>{_format_coins(auction.get('start_price'))}</code> 🪙",
        f"🔨 Current bid: <code>{current_bid}</code> 🪙",
        f"👤 Seller: <a href='tg://user?id={seller_id}'>Seller</a>",
        f"🔖 Auction ID: <code>#{code}</code>",
        f"⏳ Time left: <b>{remaining}</b>",
        leader,
    ]
    if include_footer:
        lines.append("\nTap a quick bid below, or use <code>/bid " + code + " &lt;amount&gt;</code>.")
    return "\n".join(lines)


async def _ensure_auction_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await auctions_collection.create_index("auction_id", unique=True)
        await auctions_collection.create_index([("status", 1), ("ends_at", 1)])
        await auctions_collection.create_index([("seller_id", 1), ("status", 1)])
        await auctions_collection.create_index("bidder_ids")
        await pending_refunds_collection.create_index("refund_id", unique=True)
        await pending_refunds_collection.create_index([("status", 1), ("created_at", 1)])
        _indexes_ready = True
    except Exception as exc:
        LOGGER.warning("Auction index setup skipped: %s", exc)


async def _credit_balance(user_id, amount: int, *, marker_field: str | None = None, marker: dict | None = None) -> bool:
    """Credit coins; optionally use a marker to make retries idempotent."""
    amount = int(amount or 0)
    if amount <= 0:
        return True
    if marker_field and marker:
        marker_id = marker.get("refund_id") or marker.get("payout_id") or marker.get("auction_id")
        if not marker_id:
            return False
        if await user_collection.count_documents({"id": user_id, f"{marker_field}.marker_id": marker_id}, limit=1):
            return True
        update = {
            "$inc": {"balance": amount},
            "$push": {marker_field: {**marker, "marker_id": marker_id, "amount": amount}},
            "$setOnInsert": {"id": user_id, "characters": []},
        }
        result = await user_collection.update_one(
            {"id": user_id, f"{marker_field}.marker_id": {"$ne": marker_id}},
            update,
            upsert=True,
        )
        if result.modified_count or result.upserted_id is not None:
            return True
        return bool(await user_collection.count_documents({"id": user_id, f"{marker_field}.marker_id": marker_id}, limit=1))
    result = await user_collection.update_one({"id": user_id}, {"$inc": {"balance": amount}})
    return bool(result.modified_count)


async def _refund_bid(user_id, amount: int, refund_id: str) -> bool:
    return await _credit_balance(
        user_id,
        int(amount or 0),
        marker_field="auction_refund_ids",
        marker={"refund_id": refund_id, "source": "auction_bid", "created_at": _now()},
    )


async def _pay_seller(seller_id, amount: int, auction_id: str) -> bool:
    return await _credit_balance(
        seller_id,
        int(amount or 0),
        marker_field="auction_payouts",
        marker={"payout_id": f"payout:{auction_id}", "source": "auction_sale", "auction_id": auction_id, "created_at": _now()},
    )


async def _enqueue_refund(user_id, amount: int, refund_id: str) -> None:
    try:
        await pending_refunds_collection.update_one(
            {"refund_id": refund_id},
            {
                "$setOnInsert": {
                    "refund_id": refund_id,
                    "user_id": user_id,
                    "amount": int(amount or 0),
                    "created_at": _now(),
                    "status": "pending",
                    "attempts": 0,
                }
            },
            upsert=True,
        )
    except Exception as exc:
        LOGGER.error("Could not queue auction refund %s: %s", refund_id, exc)


async def _process_pending_refunds(limit: int = 25) -> int:
    processed = 0
    cursor = pending_refunds_collection.find({"status": "pending"}).sort("created_at", 1).limit(limit)
    async for item in cursor:
        refund_id = str(item.get("refund_id") or "")
        if not refund_id:
            continue
        try:
            if await _refund_bid(item.get("user_id"), int(item.get("amount") or 0), refund_id):
                await pending_refunds_collection.update_one(
                    {"_id": item["_id"]},
                    {"$set": {"status": "done", "processed_at": _now()}},
                )
            else:
                await pending_refunds_collection.update_one(
                    {"_id": item["_id"]},
                    {"$inc": {"attempts": 1}, "$set": {"last_attempt_at": _now()}},
                )
            processed += 1
        except Exception as exc:
            await pending_refunds_collection.update_one(
                {"_id": item["_id"]},
                {"$inc": {"attempts": 1}, "$set": {"last_error": type(exc).__name__, "last_attempt_at": _now()}},
            )
    return processed


async def _deliver_escrow_copy(target_user_id, character: dict, instance_id: str) -> bool:
    if not isinstance(character, dict) or not instance_id:
        return False
    copy = dict(character)
    copy["auction_instance_id"] = instance_id
    marker_query = {"id": target_user_id, "characters.auction_instance_id": instance_id}
    if await user_collection.count_documents(marker_query, limit=1):
        return True
    result = await user_collection.update_one(
        {"id": target_user_id, "characters.auction_instance_id": {"$ne": instance_id}},
        {
            "$push": {"characters": copy},
            "$setOnInsert": {"id": target_user_id, "balance": 0},
        },
        upsert=True,
    )
    if result.modified_count or result.upserted_id is not None:
        return True
    return bool(await user_collection.count_documents(marker_query, limit=1))


async def _load_live_auction(auction_id: str):
    return await auctions_collection.find_one({"auction_id": auction_id})


async def _claim_ended_auction(auction: dict) -> bool:
    now = _now()
    if auction.get("status") == "active":
        result = await auctions_collection.update_one(
            {"auction_id": auction.get("auction_id"), "status": "active", "ends_at": auction.get("ends_at")},
            {"$set": {"status": "settling", "claimed_at": now}},
        )
        return bool(result.modified_count)
    return auction.get("status") == "settling"


async def _settle_auction(auction: dict, reason: str = "ended") -> bool:
    if not await _claim_ended_auction(auction):
        return False
    auction_id = str(auction.get("auction_id"))
    character = auction.get("character") or {}
    instance_id = str(character.get("auction_instance_id") or auction_id)
    high_bidder = auction.get("highest_bidder_id")
    final_price = int(auction.get("current_bid") or auction.get("start_price") or 0)
    now = _now()

    if high_bidder:
        delivered = await _deliver_escrow_copy(high_bidder, character, instance_id)
        if not delivered:
            LOGGER.error("Auction %s could not deliver escrowed character", auction_id)
            return False
        paid = await _pay_seller(auction.get("seller_id"), final_price, auction_id)
        if not paid:
            LOGGER.error("Auction %s could not pay seller", auction_id)
            return False
        closed_reason = "sold"
    else:
        delivered = await _deliver_escrow_copy(auction.get("seller_id"), character, instance_id)
        if not delivered:
            LOGGER.error("Auction %s could not return escrowed character", auction_id)
            return False
        closed_reason = reason if reason in {"cancelled", "no_bids"} else "no_bids"

    result = await auctions_collection.update_one(
        {"auction_id": auction_id, "status": "settling"},
        {
            "$set": {
                "status": "closed",
                "closed_at": now,
                "closed_reason": closed_reason,
                "winner_id": high_bidder,
                "final_price": final_price if high_bidder else 0,
            },
            "$unset": {"claimed_at": ""},
        },
    )
    if not result.modified_count:
        return False
    await _announce_settlement(auction, closed_reason, final_price if high_bidder else 0)
    return True


async def _announce_settlement(auction: dict, reason: str, final_price: int) -> None:
    auction_id = str(auction.get("auction_id"))
    character = auction.get("character") or {}
    name = _character_name(character)
    code = _auction_code(auction_id)
    chat_id = auction.get("chat_id")
    if reason == "sold":
        winner_id = auction.get("highest_bidder_id")
        body = (
            f"🏆 <b>Auction #{code} sold!</b>\n\n"
            f"🎴 <b>{name}</b>\n"
            f"💰 Final bid: <code>{_format_coins(final_price)}</code> 🪙\n"
            f"📦 Character moved to the winner's collection.\n"
            f"👤 Seller paid automatically."
        )
        try:
            await send_panel(app, int(chat_id), premium_text(rich_card("Auction sold", rich_quote(tr(body, "en")), "🏆")), parse_mode=enums.ParseMode.HTML)
        except Exception as exc:
            LOGGER.warning("Auction %s room announcement failed: %s", auction_id, exc)
        try:
            await send_panel(app, int(winner_id), premium_text(rich_card("Auction won", rich_quote(tr(body, "en")), "🏆")), parse_mode=enums.ParseMode.HTML)
        except Exception as exc:
            LOGGER.warning("Auction %s winner PM failed: %s", auction_id, exc)
        return

    label = "cancelled" if reason == "cancelled" else "ended with no bids"
    body = (
        f"📭 <b>Auction #{code} {label}.</b>\n\n"
        f"🎴 <b>{name}</b> returned to the seller."
    )
    try:
        await send_panel(app, int(chat_id), premium_text(rich_card("Auction closed", rich_quote(tr(body, "en")), "📭")), parse_mode=enums.ParseMode.HTML)
    except Exception as exc:
        LOGGER.warning("Auction %s no-bid announcement failed: %s", auction_id, exc)


async def _settle_ended_auctions(limit: int = 20) -> int:
    await _ensure_auction_indexes()
    now = _now()
    settled = 0
    active = auctions_collection.find({"status": "active", "ends_at": {"$lte": now}}).sort("ends_at", 1).limit(limit)
    async for auction in active:
        try:
            if await _settle_auction(auction, "ended"):
                settled += 1
        except Exception as exc:
            LOGGER.error("Auction %s settlement failed: %s", auction.get("auction_id"), exc)
    stale = auctions_collection.find({"status": "settling", "claimed_at": {"$lte": now - _STALE_CLAIM_SECONDS}}).limit(limit)
    async for auction in stale:
        try:
            if await _settle_auction(auction, "ended"):
                settled += 1
        except Exception as exc:
            LOGGER.error("Stale auction %s retry failed: %s", auction.get("auction_id"), exc)
    return settled


async def _process_auction_retries() -> None:
    await _process_pending_refunds()
    await _settle_ended_auctions()


async def _reaper_loop() -> None:
    while True:
        try:
            await _process_auction_retries()
        except Exception as exc:
            LOGGER.warning("Auction reaper tick failed: %s", type(exc).__name__)
        await asyncio.sleep(_REAPER_INTERVAL)


async def _ensure_reaper() -> None:
    global _reaper_task
    await _ensure_auction_indexes()
    if _reaper_task is not None and not _reaper_task.done():
        return
    try:
        _reaper_task = asyncio.create_task(_reaper_loop(), name="fiona-auction-reaper")
    except RuntimeError:
        pass


async def _place_bid(target, user, auction_id: str, *, increment: int | None = None, absolute: int | None = None) -> bool:
    await _ensure_reaper()
    lang = await get_effective_lang(target)
    user_id = user.id
    if await is_user_blocklisted(user_id):
        await _notice(target, tr("🚫 Your account cannot place auction bids.", lang))
        return False
    auction = await _load_live_auction(auction_id)
    if not auction:
        await _notice(target, tr("❌ Auction not found.", lang))
        return False
    if auction.get("status") == "active" and float(auction.get("ends_at") or 0) <= _now():
        await _settle_auction(auction, "ended")
        auction = await _load_live_auction(auction_id)
        if not auction or auction.get("status") != "active" or float(auction.get("ends_at") or 0) <= _now():
            await _notice(target, tr("⏰ That auction has ended.", lang))
            return False
    if auction.get("status") != "active":
        await _notice(target, tr("⏰ That auction is already closed.", lang))
        return False
    if int(auction.get("seller_id")) == int(user_id):
        await _notice(target, tr("🚫 You cannot bid on your own auction.", lang))
        return False

    now = _now()
    current_bid = int(auction.get("current_bid") or auction.get("start_price") or 0)
    previous_bidder = auction.get("highest_bidder_id")
    bid_target = _target_bid(auction, increment=increment, absolute=absolute)
    minimum = _minimum_absolute_bid(auction)
    if bid_target < minimum:
        await _notice(target, tr(f"❌ Your bid must be at least <code>{_format_coins(minimum)}</code> coins.", lang), parse_mode=enums.ParseMode.HTML)
        return False
    prior_escrow = current_bid if previous_bidder == user_id else 0
    debit_amount = bid_target - prior_escrow
    if debit_amount <= 0:
        await _notice(target, tr("❌ That bid is not higher than your current escrowed bid.", lang))
        return False

    balance_doc = await user_collection.find_one({"id": user_id}, {"balance": 1}) or {}
    available = int(balance_doc.get("balance", 0) or 0) + prior_escrow
    if available < bid_target:
        await _notice(target, tr(f"❌ You need <code>{_format_coins(bid_target)}</code> coins for that bid; you have <code>{_format_coins(available)}</code>.", lang), parse_mode=enums.ParseMode.HTML)
        return False

    debit = await user_collection.update_one(
        {"id": user_id, "balance": {"$gte": debit_amount}},
        {"$inc": {"balance": -debit_amount}},
    )
    if not debit.modified_count:
        await _notice(target, tr("❌ Not enough coins for that bid.", lang))
        return False

    new_end = float(auction.get("ends_at") or now)
    if new_end - now < _ANTI_SNIPE_WINDOW:
        new_end = now + _ANTI_SNIPE_EXTENSION
    version = int(auction.get("version") or 0)
    anti_snipe = new_end > float(auction.get("ends_at") or 0)
    update_result = await auctions_collection.update_one(
        {
            "auction_id": auction_id,
            "status": "active",
            "current_bid": current_bid,
            "highest_bidder_id": previous_bidder,
            "ends_at": auction.get("ends_at"),
        },
        {
            "$set": {
                "current_bid": bid_target,
                "highest_bidder_id": user_id,
                "highest_bidder_name": getattr(user, "first_name", None) or getattr(user, "username", None) or "Collector",
                "ends_at": new_end,
                "last_bid_at": now,
            },
            "$inc": {"bid_count": 1, "version": 1},
            "$addToSet": {"bidder_ids": user_id},
        },
    )
    if not update_result.modified_count:
        await _credit_balance(user_id, debit_amount)
        await _notice(target, tr("⚠️ This auction changed while your bid was processing. Your escrow was returned safely; please try again.", lang))
        return False

    if previous_bidder and previous_bidder != user_id:
        refund_id = f"refund:{auction_id}:{version + 1}:{previous_bidder}"
        try:
            refunded = await _refund_bid(previous_bidder, current_bid, refund_id)
        except Exception as exc:
            refunded = False
            LOGGER.error("Auction %s previous-bidder refund failed: %s", auction_id, exc)
        if not refunded:
            await _enqueue_refund(previous_bidder, current_bid, refund_id)
        try:
            character = auction.get("character") or {}
            await send_panel(
                app,
                int(previous_bidder),
                premium_text(rich_card(
                    "You were outbid",
                    rich_quote(tr(f"🎴 <b>{_character_name(character)}</b>\n🔨 New high bid: <code>{_format_coins(bid_target)}</code> 🪙", "en")),
                    "⚡",
                )),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as exc:
            LOGGER.warning("Outbid PM for auction %s failed: %s", auction_id, exc)

    updated = {
        **auction,
        "current_bid": bid_target,
        "highest_bidder_id": user_id,
        "highest_bidder_name": getattr(user, "first_name", None) or getattr(user, "username", None) or "Collector",
        "ends_at": new_end,
    }
    keyboard = _bid_keyboard(auction_id)
    caption = premium_text(rich_card("Live auction", rich_quote(tr(_auction_body(updated), lang)), "🔨"))
    return bool(await _show_bid_result(target, caption, keyboard, bid_target, anti_snipe, lang))


def _plain_text(value) -> str:
    text = html.unescape(str(value or ""))
    import re
    return re.sub(r"<[^>]+>", "", text)


async def _notice(target, text, **kwargs):
    if hasattr(target, "answer") and hasattr(target, "message"):
        try:
            await target.answer(_plain_text(text), show_alert=True)
            return None
        except Exception:
            pass
    try:
        return await reply_notice(target, text, **kwargs)
    except Exception:
        return None


async def _show_bid_result(target, caption: str, keyboard, bid_target: int, anti_snipe: bool, lang: str) -> bool:
    text = caption
    if anti_snipe:
        text += "\n\n⚡ <i>Anti-snipe: the auction was extended by 60 seconds.</i>"
    if hasattr(target, "message") and getattr(target, "message", None) is not None:
        edited = await edit_panel(target.message, text, reply_markup=keyboard)
        try:
            await target.answer(tr(f"Bid placed: {_format_coins(bid_target)} coins", lang))
        except Exception:
            pass
        return edited
    sent = await reply_panel(target, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    return sent is not None


async def _send_auction_detail(message, auction: dict, lang: str) -> None:
    character = auction.get("character") or {}
    caption = premium_text(rich_card(
        "Live auction",
        rich_quote(tr(_auction_body(auction), lang)),
        "🔨",
    ))
    keyboard = _bid_keyboard(str(auction.get("auction_id")))
    image_url = (character.get("img_url") or character.get("image") or character.get("url") or "").strip()
    if image_url:
        await reply_photo_panel(message, photo=image_url, caption=caption, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await reply_panel(message, caption, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)


async def _rollback_listing(auction: dict) -> bool:
    auction_id = str(auction.get("auction_id"))
    character = auction.get("character") or {}
    instance_id = str(character.get("auction_instance_id") or auction_id)
    try:
        result = await auctions_collection.update_one(
            {"auction_id": auction_id, "status": "active"},
            {"$set": {"status": "settling", "claimed_at": _now()}},
        )
    except Exception:
        return False
    if not result.modified_count:
        return False
    delivered = await _deliver_escrow_copy(auction.get("seller_id"), character, instance_id)
    if not delivered:
        return False
    await auctions_collection.update_one(
        {"auction_id": auction_id, "status": "settling"},
        {"$set": {"status": "closed", "closed_at": _now(), "closed_reason": "listing_failed", "winner_id": None, "final_price": 0}, "$unset": {"claimed_at": ""}},
    )
    return True


def _try_start_reaper_on_import() -> None:
    global _reaper_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _reaper_task is None or _reaper_task.done():
        _reaper_task = loop.create_task(_reaper_loop(), name="fiona-auction-reaper")


_try_start_reaper_on_import()


@app.on_message(filters.command("auction"))
async def create_auction(client, message):
    if not message.from_user:
        return
    await _ensure_reaper()
    await _settle_ended_auctions()
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    if await is_user_blocklisted(user_id):
        return await reply_notice(message, tr("🚫 Your account cannot list auctions.", lang))

    args = message.command or []
    if len(args) not in (3, 4):
        return await reply_notice(message, tr("Usage: /auction <character_id> <start_price> [duration_minutes]", lang))
    char_id = str(args[1]).strip().lstrip("#")
    if not char_id:
        return await reply_notice(message, tr("❌ Please provide a character ID.", lang))
    start_price = _parse_integer(args[2], minimum=_MIN_STARTING_BID)
    if start_price is None:
        return await reply_notice(message, tr(f"❌ Start price must be at least <code>{_MIN_STARTING_BID}</code> coins.", lang), parse_mode=enums.ParseMode.HTML)
    duration = _parse_integer(args[3] if len(args) > 3 else _AUCTION_DURATION_DEFAULT, default=_AUCTION_DURATION_DEFAULT, minimum=_AUCTION_DURATION_MIN, maximum=_AUCTION_DURATION_MAX)
    if duration is None:
        duration = _AUCTION_DURATION_DEFAULT

    user = await user_collection.find_one({"id": user_id})
    if not user:
        return await reply_notice(message, tr("⚠️ Your collection was not found. Use /waifu first.", lang))
    characters = user.get("characters") or []
    if not isinstance(characters, list):
        return await reply_notice(message, tr("⚠️ Your collection data is invalid. Please contact support.", lang))
    removal = _remove_character_copy(characters, char_id)
    if removal is None:
        return await reply_notice(message, tr("❌ You do not own that character.", lang))
    after, removed = removal
    if not isinstance(removed, dict):
        return await reply_notice(message, tr("⚠️ That character entry is invalid. Please contact support.", lang))

    auction_id = uuid.uuid4().hex[:12]
    escrow_character = dict(removed)
    escrow_character["auction_instance_id"] = auction_id
    update = await user_collection.update_one(
        {"_id": user["_id"], "characters": characters},
        {"$set": {"characters": after}},
    )
    if not update.modified_count:
        return await reply_notice(message, tr("⚠️ Your collection changed while the auction was being created. Please try again.", lang))

    now = _now()
    auction = {
        "auction_id": auction_id,
        "seller_id": user_id,
        "seller_name": message.from_user.first_name or "Collector",
        "character": escrow_character,
        "character_id": _character_id_text(removed.get("id")),
        "start_price": int(start_price),
        "current_bid": int(start_price),
        "highest_bidder_id": None,
        "highest_bidder_name": None,
        "bidder_ids": [],
        "bid_count": 0,
        "version": 0,
        "status": "active",
        "created_at": now,
        "ends_at": now + int(duration) * 60,
        "chat_id": getattr(getattr(message, "chat", None), "id", None),
        "message_id": None,
    }
    try:
        await auctions_collection.insert_one(auction)
    except Exception as exc:
        LOGGER.error("Auction insert failed for seller %s: %s", user_id, exc)
        await _deliver_escrow_copy(user_id, escrow_character, auction_id)
        return await reply_notice(message, tr("⚠️ The auction could not be created. Your character was returned safely.", lang))

    caption = premium_text(rich_card("Auction listed", rich_quote(tr(_auction_body(auction), lang)), "🏺"))
    keyboard = _bid_keyboard(auction_id)
    image_url = (escrow_character.get("img_url") or escrow_character.get("image") or escrow_character.get("url") or "").strip()
    try:
        if image_url:
            sent = await reply_photo_panel(message, photo=image_url, caption=caption, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else:
            sent = await reply_panel(message, caption, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        sent_id = getattr(sent, "id", None)
        if sent_id:
            await auctions_collection.update_one({"auction_id": auction_id}, {"$set": {"message_id": int(sent_id)}})
    except Exception as exc:
        LOGGER.error("Auction %s message failed; rolling back: %s", auction_id, exc)
        await _rollback_listing(auction)
        return await reply_notice(message, tr("⚠️ Telegram could not post the auction. Your character was returned safely.", lang))


@app.on_message(filters.command("bid"))
async def bid_command(client, message):
    if not message.from_user:
        return
    args = message.command or []
    lang = await get_effective_lang(message)
    if len(args) != 3:
        return await reply_notice(message, tr("Usage: /bid <auction_id> <amount>", lang))
    auction_id = str(args[1]).strip().lstrip("#").lower()
    amount = _parse_integer(args[2], minimum=1)
    if amount is None:
        return await reply_notice(message, tr("❌ Amount must be a positive number.", lang))
    await _place_bid(message, message.from_user, auction_id, absolute=amount)


@app.on_message(filters.command(["auctionlist", "auction_list", "auctions"]))
async def auction_list(client, message):
    if not message.from_user:
        return
    await _ensure_reaper()
    await _settle_ended_auctions()
    lang = await get_effective_lang(message)
    now = _now()
    auctions = await auctions_collection.find({"status": "active", "ends_at": {"$gt": now}}).sort("ends_at", 1).limit(_ACTIVE_LIST_LIMIT).to_list(length=_ACTIVE_LIST_LIMIT)
    if not auctions:
        return await reply_notice(message, tr("📭 No live auctions right now. List one with /auction <character_id> <start_price> [minutes].", lang))
    lines = []
    for auction in auctions:
        character = auction.get("character") or {}
        code = _auction_code(auction.get("auction_id"))
        mark = "👑" if auction.get("highest_bidder_id") == message.from_user.id else "🔨"
        lines.append(
            f"{mark} <code>#{code}</code> · <b>{_character_name(character)}</b>\n"
            f"   Bid <code>{_format_coins(auction.get('current_bid'))}</code> 🪙 · ⏳ {_time_left(float(auction.get('ends_at') or 0) - now)}"
        )
    body = "\n\n".join(lines) + "\n\nTap a button to open an auction, or bid with <code>/bid &lt;auction_id&gt; &lt;amount&gt;</code>."
    await reply_panel(
        message,
        premium_text(rich_card("Live auctions", rich_quote(tr(body, lang)), "🏺")),
        reply_markup=_list_keyboard(auctions),
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command("mybids"))
async def my_bids(client, message):
    if not message.from_user:
        return
    await _ensure_reaper()
    await _settle_ended_auctions()
    lang = await get_effective_lang(message)
    now = _now()
    auctions = await auctions_collection.find(
        {"status": "active", "ends_at": {"$gt": now}, "bidder_ids": message.from_user.id}
    ).sort("ends_at", 1).limit(_ACTIVE_LIST_LIMIT).to_list(length=_ACTIVE_LIST_LIMIT)
    if not auctions:
        return await reply_notice(message, tr("📭 You have not bid on any live auctions.", lang))
    lines = []
    for auction in auctions:
        character = auction.get("character") or {}
        code = _auction_code(auction.get("auction_id"))
        winning = auction.get("highest_bidder_id") == message.from_user.id
        marker = "👑" if winning else "👀"
        lines.append(
            f"{marker} <code>#{code}</code> · <b>{_character_name(character)}</b>\n"
            f"   Current <code>{_format_coins(auction.get('current_bid'))}</code> 🪙 · ⏳ {_time_left(float(auction.get('ends_at') or 0) - now)}"
        )
    body = "\n\n".join(lines) + "\n\n👑 = leading · 👀 = outbid"
    await reply_panel(
        message,
        premium_text(rich_card("Your bids", rich_quote(tr(body, lang)), "🧾")),
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command(["cancelauction", "cancel_auction", "auctioncancel"]))
async def cancel_auction(client, message):
    if not message.from_user:
        return
    await _ensure_reaper()
    lang = await get_effective_lang(message)
    args = message.command or []
    if len(args) != 2:
        return await reply_notice(message, tr("Usage: /cancelauction <auction_id>", lang))
    auction_id = str(args[1]).strip().lstrip("#").lower()
    auction = await _load_live_auction(auction_id)
    if not auction or auction.get("status") == "closed":
        return await reply_notice(message, tr("❌ Auction not found or already closed.", lang))
    if int(auction.get("seller_id")) != int(message.from_user.id):
        return await reply_notice(message, tr("🚫 Only the seller can cancel this auction.", lang))
    if int(auction.get("bid_count") or 0) > 0 or auction.get("highest_bidder_id"):
        return await reply_notice(message, tr("❌ You cannot cancel an auction after a bid has been placed.", lang))
    if auction.get("status") != "active":
        return await reply_notice(message, tr("⏰ That auction is already being settled.", lang))
    settled = await _settle_auction(auction, "cancelled")
    if not settled:
        return await reply_notice(message, tr("⚠️ That auction changed while it was closing. Please try again.", lang))
    await reply_notice(message, tr(f"✅ Auction #{_auction_code(auction_id)} cancelled. Your character was returned.", lang))


@app.on_callback_query(filters.create(lambda _, __, query: query.data.startswith(("auction_bid_", "auction_custom_", "auction_refresh_", "auction_view_"))))
async def auction_callbacks(client, callback_query):
    if not callback_query.from_user:
        return
    data = callback_query.data or ""
    lang = await get_effective_lang(callback_query)
    await _ensure_reaper()
    try:
        if data.startswith("auction_bid_"):
            parts = data.split("_")
            if len(parts) < 4:
                return await callback_query.answer(tr("Invalid bid.", lang), show_alert=True)
            amount = _parse_integer(parts[-1], minimum=1)
            auction_id = "_".join(parts[2:-1]).lower()
            if amount is None:
                return await callback_query.answer(tr("Invalid bid amount.", lang), show_alert=True)
            await _settle_ended_auctions()
            await _place_bid(callback_query, callback_query.from_user, auction_id, increment=amount)
            return
        if data.startswith("auction_custom_"):
            auction_id = data.split("_", 2)[-1].lower()[:12]
            return await callback_query.answer(tr(f"Use /bid {auction_id} <amount> for a custom bid.", lang), show_alert=True)
        if data.startswith("auction_view_") or data.startswith("auction_refresh_"):
            auction_id = data.split("_", 2)[-1].lower()[:12]
            await _settle_ended_auctions()
            auction = await _load_live_auction(auction_id)
            if not auction or auction.get("status") != "active":
                return await callback_query.answer(tr("⏰ This auction is not live.", lang), show_alert=True)
            if data.startswith("auction_refresh_"):
                await edit_panel(
                    callback_query.message,
                    premium_text(rich_card("Live auction", rich_quote(tr(_auction_body(auction), lang)), "🔨")),
                    reply_markup=_bid_keyboard(auction_id),
                )
                return await callback_query.answer(tr("Refreshed", lang))
            await _send_auction_detail(callback_query.message, auction, lang)
            return await callback_query.answer(tr("Auction opened below.", lang))
    except Exception as exc:
        LOGGER.error("Auction callback %s failed: %s", data, exc)
        try:
            await callback_query.answer(tr("⚠️ Auction action failed. Please try again.", lang), show_alert=True)
        except Exception:
            pass
