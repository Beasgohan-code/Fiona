"""Closed-auction history and live escrow stats for collectors."""

import html

from pyrogram import enums, filters

from aoiwaifu import app
from aoiwaifu.admin.blocklist import is_user_blocklisted
from aoiwaifu.modules import auction as auction_module
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, reply_notice, reply_panel, rich_card, rich_quote

_HISTORY_LIMIT = 8


def _coins(amount) -> str:
    return f"{max(0, int(amount or 0)):,}"


def _code(auction_id) -> str:
    return html.escape(str(auction_id or "unknown")[:12])


def _name(auction: dict) -> str:
    return html.escape(str((auction.get("character") or {}).get("name") or "Unknown character"))


def _line_for_history(auction: dict, user_id: int) -> str:
    code = _code(auction.get("auction_id"))
    name = _name(auction)
    reason = str(auction.get("closed_reason") or "closed")
    price = int(auction.get("final_price") or auction.get("current_bid") or 0)
    if auction.get("winner_id") == user_id:
        role = f"Won for <code>{_coins(price)}</code> coins"
    elif reason == "sold" and auction.get("seller_id") == user_id:
        role = f"Sold for <code>{_coins(price)}</code> coins"
    elif reason == "cancelled":
        role = "Cancelled"
    else:
        role = "No bids · returned"
    return f"🔨 <code>#{code}</code> · <b>{name}</b><br>   {role}"


@app.on_message(filters.command(["auctionhistory", "auctionlog"]))
async def auction_history(client, message):
    if not message.from_user:
        return
    await auction_module._ensure_reaper()
    await auction_module._settle_ended_auctions()
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    if await is_user_blocklisted(user_id):
        return await reply_notice(message, tr("🚫 Your account cannot view auction history.", lang))

    rows = await auction_module.auctions_collection.find(
        {"status": "closed", "$or": [{"seller_id": user_id}, {"winner_id": user_id}, {"bidder_ids": user_id}]}
    ).sort("closed_at", -1).limit(_HISTORY_LIMIT).to_list(length=_HISTORY_LIMIT)
    if not rows:
        return await reply_notice(message, tr("📭 You do not have any closed auctions yet.", lang))

    body = "<br><br>".join(_line_for_history(row, user_id) for row in rows)
    await reply_panel(
        message,
        premium_text(rich_card("Auction history", rich_quote(tr(body, lang)), "🧾")),
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command(["auctionstats", "auctionsummary"]))
async def auction_stats(client, message):
    if not message.from_user:
        return
    await auction_module._ensure_reaper()
    await auction_module._settle_ended_auctions()
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    if await is_user_blocklisted(user_id):
        return await reply_notice(message, tr("🚫 Your account cannot view auction stats.", lang))

    now = auction_module._now()
    closed = await auction_module.auctions_collection.find(
        {"status": "closed", "$or": [{"seller_id": user_id}, {"winner_id": user_id}, {"bidder_ids": user_id}]}
    ).to_list(length=500)
    active_participations = await auction_module.auctions_collection.count_documents(
        {"status": "active", "ends_at": {"$gt": now}, "bidder_ids": user_id}
    )
    leading_docs = await auction_module.auctions_collection.find(
        {"status": "active", "ends_at": {"$gt": now}, "highest_bidder_id": user_id}
    ).to_list(length=100)

    wins = sales = cancelled = returned = 0
    spent = earned = 0
    for auction in closed:
        reason = str(auction.get("closed_reason") or "")
        price = int(auction.get("final_price") or auction.get("current_bid") or 0)
        if auction.get("winner_id") == user_id:
            wins += 1
            spent += price
        if auction.get("seller_id") == user_id and reason == "sold":
            sales += 1
            earned += price
        elif auction.get("seller_id") == user_id and reason == "cancelled":
            cancelled += 1
        elif auction.get("seller_id") == user_id:
            returned += 1

    live_escrow = sum(int(auction.get("current_bid") or 0) for auction in leading_docs)
    net = earned - spent
    sign = "+" if net >= 0 else "-"
    body = (
        f"🔴 Leading now: <b>{len(leading_docs):,}</b> auction(s) · live escrow: <code>{_coins(live_escrow)}</code> coins\n"
        f"🟡 Bidding now: <b>{active_participations:,}</b> auction(s)\n"
        f"🏆 Won: <b>{wins:,}</b> · spent <code>{_coins(spent)}</code> coins\n"
        f"🪙 Sold: <b>{sales:,}</b> · earned <code>{_coins(earned)}</code> coins\n"
        f"📭 No-bid returns: <b>{returned:,}</b> · cancelled: <b>{cancelled:,}</b>\n"
        f"⚖️ Net auction profit: <b>{sign}{_coins(abs(net))}</b> coins"
    )
    await reply_panel(
        message,
        premium_text(rich_card("Auction stats", rich_quote(tr(body, lang)), "📊")),
        parse_mode=enums.ParseMode.HTML,
    )
