import logging

logger = logging.getLogger(__name__)
"""Owner and Sudo broadcast to registered users and groups."""

from aoiwaifu.unit.rich_ui import (
    reply_panel,
    premium_text,
    rich_card,
)
import asyncio

from pyrogram import enums, filters
from pyrogram.errors import FloodWait, PeerIdInvalid

from aoiwaifu import OWNER_ID, SUDO, app, top_global_groups_collection, user_collection
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr, tr_panel


@app.on_message(filters.command(["waifubcast", "waifubroadcast"]) & filters.user(SUDO + [OWNER_ID]))
async def broadcast(_, message):
    lang = await get_effective_lang(message)
    replied_message = message.reply_to_message
    if not replied_message:
        await reply_panel(message,
            premium_text(tr_panel(rich_card("Broadcast", "❌ Reply to a message to broadcast it.", "📢"), lang)),
            parse_mode=enums.ParseMode.HTML,
        )
        return

    progress_message = await reply_panel(message,
        premium_text(
            tr_panel(
                rich_card(
                    "Broadcast",
                    "Starting. Your replied message will be sent to registered users and groups.",
                    "📢",
                ),
                lang,
            )
        ),
        parse_mode=enums.ParseMode.HTML,
    )
    fail_count = 0
    message_count = 0
    user_success = 0
    group_success = 0

    async def forward_message(target_id) -> bool:
        nonlocal fail_count, message_count
        try:
            await replied_message.forward(target_id)
            message_count += 1
            if message_count % 7 == 0:
                await asyncio.sleep(2)
            return True
        except PeerIdInvalid:
            fail_count += 1
            return False
        except FloodWait as error:
            await asyncio.sleep(error.value)
            return await forward_message(target_id)
        except Exception as error:
            logger.warning(f"Error forwarding to {target_id}: {error}")
            fail_count += 1
            return False

    async def update_progress():
        body = "\n".join(
            (
                f"✅ <b>Users sent:</b> {user_success}",
                f"✅ <b>Groups sent:</b> {group_success}",
                f"❌ <b>Failed attempts:</b> {fail_count}",
            )
        )
        try:
            await progress_message.edit_text(
                premium_text(tr_panel(rich_card("Broadcast in progress", body, "📢"), lang)),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass

    async for user in user_collection.find({}):
        user_id = user.get("id")
        if user_id and await forward_message(user_id):
            user_success += 1
        if (user_success + fail_count) and (user_success + fail_count) % 100 == 0:
            await update_progress()

    unique_group_ids = set()
    async for group in top_global_groups_collection.find({}):
        group_id = group.get("chat_id")
        if group_id and group_id not in unique_group_ids:
            unique_group_ids.add(group_id)
            if await forward_message(group_id):
                group_success += 1
            if (user_success + group_success + fail_count) % 100 == 0:
                await update_progress()

    body = "\n".join(
        (
            f"👤 <b>Users sent:</b> {user_success}",
            f"👥 <b>Groups sent:</b> {group_success}",
            f"❌ <b>Failed attempts:</b> {fail_count}",
        )
    )
    await progress_message.edit_text(
        premium_text(tr_panel(rich_card("Broadcast complete", body, "✅"), lang)),
        parse_mode=enums.ParseMode.HTML,
    )
