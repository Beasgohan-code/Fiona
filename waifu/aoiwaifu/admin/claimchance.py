"""Summon-compatible controls for Fiona's weighted daily character claims."""

from pyrogram import filters

from aoiwaifu import OWNER_ID, app, rarity_map
from aoiwaifu.modules.hclaim import (
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
    if not 0 <= weight <= 1_000_000:
        await reply_notice(message, "Claim weight must be between 0 and 1,000,000. Set it to 0 to disable that rarity.")
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
    rows = []
    for rarity_id, rarity in rarity_map.items():
        weight = float(claim_rarity_weights.get(rarity_id, 0))
        status = f"<code>{weight:g}</code>" if weight > 0 else "OFF"
        rows.append((f"<code>{rarity_id}</code> · {rarity}", status))
    await reply_panel(
        message,
        rich_card(
            "Daily claim weights",
            "Weights are relative, not percentages. A weight of 0 removes that rarity from daily claim selection.\n\n"
            + rich_table(("RARITY", "WEIGHT"), rows),
            "🎁",
        ),
    )
