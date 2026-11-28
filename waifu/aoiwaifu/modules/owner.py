"""Interactive owner-only Richgram overview of Fiona's admin tools."""

import html

from pyrogram import Client, enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from aoiwaifu import OWNER_ID, OWNER_USERNAME, app
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import (
    edit_panel,
    premium_button,
    premium_text,
    rich_card,
    reply_panel,
)


_PAGES = {
    "characters": (
        "Character administration",
        "<code>/add &lt;name&gt; &lt;anime&gt; &lt;rarity&gt; &lt;image_url&gt;</code> · Add a catalog entry\n"
        "<code>/gupload</code> · Upload through ImgBB or Catbox\n"
        "<code>/update &lt;id&gt; &lt;field&gt; &lt;value&gt;</code> · Update name, anime, rarity, or image\n"
        "<code>/deletechar &lt;id&gt;</code> · Delete a catalog entry and collection copies\n"
        "Reply to a user with <code>/give &lt;character_id&gt;</code> to grant a catalog character.",
        "🪄",
    ),
    "economy": (
        "Economy administration",
        "<code>/givemoney &lt;user_id&gt; &lt;amount&gt;</code> · Add collector coins\n"
        "<code>/rmmoney &lt;user_id&gt; &lt;amount&gt;</code> · Remove available coins\n"
        "<code>/add c|b &lt;amount&gt; [user_id]</code> · Adjust coins or tokens\n"
        "<code>/kill</code> · Existing reply-based user data controls\n"
        "All money commands validate balances; deductions cannot make coins negative.",
        "💰",
    ),
    "spawning": (
        "Spawn & claim controls",
        "In a group: <code>/spawn</code> manually starts a round; <code>/checkspawn</code> shows progress; <code>/changetime &lt;count&gt;</code> changes the threshold.\n"
        "<code>/chance &lt;rarity_id&gt; &lt;weight&gt;</code> / <code>/chancelist</code> configure automatic spawn odds.\n"
        "<code>/setclaim &lt;rarity_id&gt; &lt;weight&gt;</code> / <code>/claimweights</code> configure daily-claim odds.\n"
        "Weights are relative; 0 disables a rarity for that draw. These settings are owner-only.",
        "🎲",
    ),
    "safety": (
        "Collection safety",
        "<code>/removeall &lt;user_id&gt;</code> opens an owner-bound confirmation before clearing character copies only.\n"
        "Coins, tokens, profile fields, and daily history are preserved. Confirmations expire after five minutes.\n"
        "<code>/transfer</code> and <code>/backtransfer</code> are separate legacy transfer tools; review the target IDs before confirming.",
        "🛡️",
    ),
}


def _home_markup():
    return InlineKeyboardMarkup([
        [
            premium_button("Characters", emoji="IMAGE_PHOTO", callback_data="ownerpanel:characters"),
            premium_button("Economy", emoji="WALLET", callback_data="ownerpanel:economy"),
        ],
        [
            premium_button("Spawning & claims", emoji="DICE_LUCK", callback_data="ownerpanel:spawning"),
            premium_button("Safety", emoji="SHIELD_ADMIN", callback_data="ownerpanel:safety"),
        ],
    ])


def _page_markup():
    return InlineKeyboardMarkup([[
        premium_button("← Owner tools", emoji="BACK_ARROW", callback_data="ownerpanel:home"),
    ]])


def _home_text(owner_name):
    return rich_card(
        "Fiona owner tools",
        f"Welcome, <b>{owner_name}</b>. Choose a section for command syntax and safety notes.\n\n"
        "Restricted commands continue to enforce their own owner or Sudo checks. Use <code>/help</code> for the public command guide.",
        "👑",
    )


@app.on_message(filters.command(["owner", "panel"]) & filters.private)
async def owner_overview(client: Client, message: Message):
    """Show a private interactive command index to the configured owner."""
    if not message.from_user or not OWNER_ID or message.from_user.id != OWNER_ID:
        return

    lang = await get_effective_lang(message)
    owner_name = html.escape(OWNER_USERNAME or message.from_user.first_name or "Owner")
    await reply_panel(
        message,
        premium_text(tr(_home_text(owner_name), lang)),
        reply_markup=_home_markup(),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


@app.on_callback_query(filters.regex(r"^ownerpanel:(home|characters|economy|spawning|safety)$"))
async def owner_panel_page(client: Client, callback_query: CallbackQuery):
    """Navigate owner-panel sections without exposing admin notes to other users."""
    if not callback_query.from_user or not OWNER_ID or callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("This owner panel is private.", show_alert=True)
        return

    page = callback_query.matches[0].group(1)
    await callback_query.answer()
    if page == "home":
        text = _home_text(html.escape(OWNER_USERNAME or callback_query.from_user.first_name or "Owner"))
        markup = _home_markup()
    else:
        title, body, emoji = _PAGES[page]
        text = rich_card(title, body, emoji)
        markup = _page_markup()

    await edit_panel(
        callback_query.message,
        premium_text(text),
        reply_markup=markup,
    )
