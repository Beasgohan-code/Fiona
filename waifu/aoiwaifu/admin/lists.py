"""Admin user/group export commands (/list, /groups)."""

import os
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message

from aoiwaifu import app, sudo_users as SUDO_USERS, top_global_groups_collection, user_collection
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import reply_notice


async def _send_export_document(message, lines, lang, empty_message, prefix):
    """Send a non-empty temporary text export and always remove the temp file."""
    if not lines:
        await reply_notice(message, tr(empty_message, lang))
        return False

    file_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            prefix=prefix,
            delete=False,
        ) as document:
            file_path = document.name
            document.write("\n".join(lines))
        if os.path.getsize(file_path) == 0:
            await reply_notice(message, tr(empty_message, lang))
            return False
        await message.reply_document(document=file_path)
        return True
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@app.on_message(filters.command("list"))
async def send_users_document(client: Client, message: Message):
    lang = await get_effective_lang(message)
    if str(message.from_user.id) not in SUDO_USERS:
        await reply_notice(message, tr("Only for Sudo users.", lang))
        return

    lines = []
    async for doc in user_collection.find({}, {"first_name": 1, "id": 1}):
        lines.append(f"{doc.get('first_name', 'Unknown')} ({doc.get('id', '?')})")

    await _send_export_document(
        message,
        lines,
        lang,
        "There are no user records to export yet.",
        "fiona-users-",
    )


@app.on_message(filters.command("groups"))
async def send_groups_document(client: Client, message: Message):
    lang = await get_effective_lang(message)
    if str(message.from_user.id) not in SUDO_USERS:
        await reply_notice(message, tr("Only for Sudo users.", lang))
        return

    lines = []
    async for doc in top_global_groups_collection.find({}, {"group_name": 1, "chat_id": 1}):
        lines.append(f"{doc.get('group_name', 'Unknown')} ({doc.get('chat_id', '?')})")

    await _send_export_document(
        message,
        lines,
        lang,
        "There are no group records to export yet.",
        "fiona-groups-",
    )
