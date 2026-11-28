"""Summon-compatible controls for Fiona's weighted daily character claims."""

import html
import math

from pyrogram import filters

from aoiwaifu import OWNER_ID, app, rarity_map
from aoiwaifu.modules.hclaim import (
    MAX_CLAIM_WEIGHT,
    claim_rarity_weights,
    load_claim_rarity_weights,
    set_claim_rarity_weight,
)
from aoiwaifu.unit.rich_ui import rich_card, rich_table, reply_notice, reply_panel


@app.on_message(filters.command(["setclaim"]))
async def set_claim_weight_command(client, message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        await reply_notice(message, "This claim-weight command is restricted to the bot owner.")
        return
    if len(message.command) != 3:
        await reply_notice(message, "Usage: <code>/setclaim &lt;rarity_id&gt; &lt;weight&gt;</code>\nUse <code>/claimweights</code> to inspect all rarity weights.")
        return
    try:
        rarity_id = int(message.command[1])
        weight = float(message.command[2])
    except (TypeError, ValueError):
        await reply_notice(message, "Rarity ID must be a whole number and weight must be numeric.")
        return
    if rarity_id not in rarity_map:
        await reply_notice(message, f"Unknown rarity ID. Choose from 1 to {len(rarity_map)}.")
        return
    if not 0 <= weight <= MAX_CLAIM_WEIGHT:
        await reply_notice(message, f"Claim weight must be between 0 and {MAX_CLAIM_WEIGHT:,}. Set it to 0 to disable that rarity.")
        return

    await load_claim_rarity_weights()
    await set_claim_rarity_weight(rarity_id, weight, message.from_user.id)
    status = "disabled" if weight == 0 else f"set to <code>{weight:g}</code> relative weight"
    await reply_panel(
        message,
        rich_card("Claim weight updated", f"{rarity_map[rarity_id]} is {status} for daily claims.", "🎁"),
    )


@app.on_message(filters.command(["claimweights"]))
async def list_claim_weights(client, message):
    if not message.from_user or message.from_user.id != OWNER_ID:
        await reply_notice(message, "This claim-weight command is restricted to the bot owner.")
        return

    await load_claim_rarity_weights()
    entries = []
    for rarity_id, rarity in rarity_map.items():
        try:
            weight = float(claim_rarity_weights.get(rarity_id, 0))
        except (TypeError, ValueError, OverflowError):
            weight = 0.0
        if not math.isfinite(weight) or weight < 0:
            weight = 0.0
        entries.append((rarity_id, rarity, weight))

    total_weight = sum(weight for _rarity_id, _rarity, weight in entries)
    rows = []
    for rarity_id, rarity, weight in entries:
        weight_label = f"<code>{weight:g}</code>" if weight > 0 else "OFF"
        odds_label = f"{(weight / total_weight * 100):.2f}%" if weight > 0 and total_weight else "—"
        rows.append((f"<code>{rarity_id}</code> · {html.escape(str(rarity))}", weight_label, odds_label))
    await reply_panel(
        message,
        rich_card(
            "Daily claim weights",
            "Configured odds assume every enabled rarity is available. For each claim, Fiona excludes "
            "rarities without eligible characters before drawing; weight 0 disables a rarity.\n\n"
            + rich_table(("RARITY", "WEIGHT", "ODDS"), rows),
            "🎁",
        ),
    )
