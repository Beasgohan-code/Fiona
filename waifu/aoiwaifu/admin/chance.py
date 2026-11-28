"""Owner-only Summon-compatible controls for automatic rarity spawn weights."""

import html
import math

from pyrogram import filters

from aoiwaifu import OWNER_ID, app, rarity_map
from aoiwaifu.unit.aoi_send_img import (
    MAX_SPAWN_WEIGHT,
    RARITY_WEIGHTS,
    load_spawn_weight_overrides,
    set_spawn_weight,
)
from aoiwaifu.unit.rich_ui import rich_card, rich_table, reply_notice, reply_panel


def _owner_only(message) -> bool:
    return bool(message.from_user and message.from_user.id == OWNER_ID)


@app.on_message(filters.command(["chance"]))
async def set_spawn_chance(client, message):
    if not _owner_only(message):
        await reply_notice(message, "This spawn-weight command is restricted to the bot owner.")
        return
    if len(message.command) != 3:
        await reply_notice(message, "Usage: <code>/chance &lt;rarity_id&gt; &lt;weight&gt;</code>\nUse <code>/chancelist</code> to see IDs and weights.")
        return
    try:
        rarity_id = int(message.command[1])
        weight = int(message.command[2])
    except (TypeError, ValueError):
        await reply_notice(message, "Both the rarity ID and weight must be whole numbers.")
        return
    if rarity_id not in rarity_map:
        await reply_notice(message, f"Unknown rarity ID. Choose from 1 to {len(rarity_map)}.")
        return
    if not 0 <= weight <= MAX_SPAWN_WEIGHT:
        await reply_notice(message, f"Weight must be between 0 and {MAX_SPAWN_WEIGHT:,}. Use 0 to disable this rarity in automatic drops.")
        return

    await load_spawn_weight_overrides()
    rarity = rarity_map[rarity_id]
    await set_spawn_weight(rarity_id, rarity, weight, message.from_user.id)
    state = "disabled for automatic drops" if weight == 0 else f"set to <code>{weight}</code> relative weight"
    await reply_panel(
        message,
        rich_card("Spawn weight updated", f"{html.escape(str(rarity))} is {state}.\nManual <code>/spawn</code> can still select any catalog rarity.", "🎯"),
    )


@app.on_message(filters.command(["chancelist"]))
async def list_spawn_chances(client, message):
    if not _owner_only(message):
        await reply_notice(message, "This spawn-weight command is restricted to the bot owner.")
        return

    await load_spawn_weight_overrides()
    entries = []
    for rarity_id, rarity in rarity_map.items():
        weight, enabled = RARITY_WEIGHTS.get(rarity, (1.0, True))
        try:
            numeric_weight = float(weight)
        except (TypeError, ValueError, OverflowError):
            numeric_weight = 0.0
        if not math.isfinite(numeric_weight) or numeric_weight < 0:
            numeric_weight = 0.0
        active = bool(enabled) and numeric_weight > 0
        entries.append((rarity_id, rarity, numeric_weight, active))

    total_weight = sum(weight for _rarity_id, _rarity, weight, active in entries if active)
    rows = []
    for rarity_id, rarity, weight, active in entries:
        weight_label = f"<code>{weight:g}</code>" if active else "OFF"
        odds_label = f"{(weight / total_weight * 100):.2f}%" if active and total_weight else "—"
        rows.append((f"<code>{rarity_id}</code> · {html.escape(str(rarity))}", weight_label, odds_label))

    await reply_panel(
        message,
        rich_card(
            "Automatic spawn weights",
            "Relative weights determine the approximate odds shown; odds change when any weight changes. "
            f"Use <code>/chance &lt;rarity_id&gt; &lt;weight&gt;</code> (0–{MAX_SPAWN_WEIGHT:,}); set 0 to disable an automatic drop.\n\n"
            + rich_table(("RARITY", "WEIGHT", "ODDS"), rows),
            "🎲",
        ),
    )
