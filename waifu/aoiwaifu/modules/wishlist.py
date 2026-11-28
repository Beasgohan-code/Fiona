"""Collector wishlists for characters they want to catch next."""

import html

from pyrogram import enums, filters

from aoiwaifu import app, collection, user_collection
from aoiwaifu.admin.blocklist import is_user_blocklisted
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
from aoiwaifu.unit.rich_ui import premium_text, reply_notice, reply_panel, rich_card, rich_quote

_MAX_WISHLIST = 20


def _canonical_id(value) -> str:
    """Normalize numeric catalog IDs so legacy padding cannot create duplicates."""
    value = str(value or "").strip()
    return str(int(value)) if value.isdigit() else value


def _id_candidates(value):
    value = str(value or "").strip()
    candidates = [value]
    if value.isdigit():
        candidates.extend((value.zfill(2), int(value)))
    return list(dict.fromkeys(candidates))


def _normalise_wishlist(raw) -> list[str] | None:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    result = []
    seen = set()
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip().isdigit():
            return None
        character_id = _canonical_id(value)
        if character_id not in seen:
            result.append(character_id)
            seen.add(character_id)
    return result


def _wishlist_update_filter(user: dict) -> dict:
    """Compare-and-set prevents parallel add/remove actions from overwriting."""
    conditions = [{"wishlist": {"$exists": False}}]
    if "wishlist" in user:
        conditions.append({"wishlist": user.get("wishlist")})
    return {"_id": user["_id"], "$or": conditions}


async def _save_wishlist(user: dict, after: list[str]) -> bool:
    result = await user_collection.update_one(
        _wishlist_update_filter(user),
        {"$set": {"wishlist": after}},
    )
    return bool(result.modified_count)


async def _render_wishlist(message, user: dict, wishes: list[str], lang: str):
    if not wishes:
        body = "Your wishlist is empty. Use <code>/wishlist &lt;character_id&gt;</code> to add a character."
        return await reply_panel(
            message,
            premium_text(rich_card("Your wishlist", rich_quote(tr(body, lang)), "💖")),
            parse_mode=enums.ParseMode.HTML,
        )

    candidate_ids = list(dict.fromkeys(candidate for wish in wishes for candidate in _id_candidates(wish)))
    catalog = await collection.find({"id": {"$in": candidate_ids}}).to_list(length=_MAX_WISHLIST * 3)
    by_id = {}
    for character in catalog:
        for candidate in _id_candidates(character.get("id")):
            by_id[_canonical_id(candidate)] = character

    lines = []
    for index, character_id in enumerate(wishes, 1):
        character = by_id.get(character_id)
        if character:
            name = html.escape(str(character.get("name") or "Unknown character"))
            anime = html.escape(str(character.get("anime") or "Unknown series"))
            lines.append(f"{index}. <b>{name}</b> · {anime} · <code>#{html.escape(character_id)}</code>")
        else:
            lines.append(f"{index}. <i>Character no longer in catalog</i> · <code>#{html.escape(character_id)}</code>")
    lines.append(f"\n{len(wishes)}/{_MAX_WISHLIST} saved · use <code>/unwish &lt;character_id&gt;</code> to remove one")
    body = "\n".join(lines)
    return await reply_panel(
        message,
        premium_text(rich_card("Characters to catch", rich_quote(tr(body, lang)), "💖")),
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command(["wishlist", "wish"]))
async def wishlist(client, message):
    """Show saved characters, or add one with /wishlist <character_id>."""
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    if await is_user_blocklisted(user_id):
        return await reply_notice(message, tr("🚫 Your account cannot manage a wishlist.", lang))

    user = await user_collection.find_one({"id": user_id})
    if not user:
        return await reply_notice(message, tr("Use /waifu first to create your collector profile.", lang))
    wishes = _normalise_wishlist(user.get("wishlist"))
    if wishes is None:
        return await reply_notice(message, tr("⚠️ Your wishlist data is invalid. Please contact support.", lang))

    args = message.command or []
    if len(args) == 1:
        return await _render_wishlist(message, user, wishes, lang)
    if len(args) != 2 or not args[1].isdigit():
        return await reply_notice(message, tr("Usage: /wishlist [character_id] — view your list or add a character.", lang))

    requested_id = args[1]
    character = await collection.find_one({"id": {"$in": _id_candidates(requested_id)}})
    if not character:
        return await reply_notice(message, tr("Character not found. Check its ID with /check <character_id>.", lang))
    character_id = _canonical_id(character.get("id", requested_id))
    if character_id in wishes:
        return await reply_notice(message, tr("That character is already on your wishlist.", lang))
    if len(wishes) >= _MAX_WISHLIST:
        return await reply_notice(message, tr(f"Your wishlist is full ({_MAX_WISHLIST} characters). Remove one with /unwish <character_id> first.", lang))

    # Preserve any legacy formatting while replacing the field with canonical IDs.
    updated = list(wishes) + [character_id]
    if not await _save_wishlist(user, updated):
        return await reply_notice(message, tr("Your wishlist changed at the same time. Please try again.", lang))
    name = html.escape(str(character.get("name") or "Unknown character"))
    body = f"💖 <b>{name}</b> is on your wishlist. You can save up to {_MAX_WISHLIST} characters."
    await reply_panel(
        message,
        premium_text(rich_card("Added to wishlist", rich_quote(tr(body, lang)), "💖")),
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.command("unwish"))
async def remove_wishlist_item(client, message):
    """Remove a saved character with /unwish <character_id>."""
    if not message.from_user:
        return
    lang = await get_effective_lang(message)
    user_id = message.from_user.id
    if await is_user_blocklisted(user_id):
        return await reply_notice(message, tr("🚫 Your account cannot manage a wishlist.", lang))
    args = message.command or []
    if len(args) != 2 or not args[1].isdigit():
        return await reply_notice(message, tr("Usage: /unwish <character_id>", lang))

    user = await user_collection.find_one({"id": user_id})
    if not user:
        return await reply_notice(message, tr("Use /waifu first to create your collector profile.", lang))
    wishes = _normalise_wishlist(user.get("wishlist"))
    if wishes is None:
        return await reply_notice(message, tr("⚠️ Your wishlist data is invalid. Please contact support.", lang))
    character_id = _canonical_id(args[1])
    if character_id not in wishes:
        return await reply_notice(message, tr("That character is not on your wishlist.", lang))

    updated = [wish for wish in wishes if wish != character_id]
    if not await _save_wishlist(user, updated):
        return await reply_notice(message, tr("Your wishlist changed at the same time. Please try again.", lang))
    await reply_notice(message, tr(f"Removed character #{character_id} from your wishlist.", lang))
