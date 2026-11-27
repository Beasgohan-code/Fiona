"""Owner-only overview of Fiona's available collection administration tools."""

import html

from pyrogram import Client, enums, filters
from pyrogram.types import Message

from aoiwaifu import OWNER_ID, OWNER_USERNAME, app
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, rich_card


@app.on_message(filters.command(["owner", "panel"]) & filters.private)
async def owner_overview(client: Client, message: Message):
    """Show a safe command overview to the configured bot owner only."""
    if not message.from_user or not OWNER_ID or message.from_user.id != OWNER_ID:
        # Match the source bot's owner-only behavior without leaking operations
        # or deployment metadata in public chats.
        return

    lang = await get_effective_lang(message)
    owner_name = html.escape(OWNER_USERNAME or message.from_user.first_name or "Owner")
    body = (
        f"Welcome, <b>{owner_name}</b>. Here is your private command index.\n\n"
        "<b>Collector administration</b>\n"
        "<code>/cgen</code> · Generate a character\n"
        "<code>/gupdate</code>, <code>/gdelete</code> · Update or delete a character\n"
        "<code>/transfer</code> · Transfer characters\n"
        "<code>/add</code>, <code>/kill</code> · Adjust collection balances\n"
        "<code>/waifubcast</code> · Broadcast to collectors\n"
        "<code>/list</code>, <code>/groups</code> · Export users or groups\n"
        "<code>/blocklist</code>, <code>/removeblocklist</code> · Manage blocked users\n"
        "<code>/backup</code>, <code>/backupstatus</code>, <code>/listbackups</code> · Backups\n\n"
        "Use <code>/help</code> for the full public command guide. Restricted commands still enforce their own owner or Sudo checks."
    )
    text = rich_card("Fiona owner tools", body, "👑")
    await message.reply_text(
        premium_text(tr(text, lang)),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )
