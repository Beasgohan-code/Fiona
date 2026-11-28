"""Read-only group overview for Fiona administrators and members."""

from __future__ import annotations

from pyrogram import filters
from pyrogram.enums import ChatMembersFilter
from pyrogram.types import Message

from config import BANNED_USERS
from AoiMusic import app
from AoiMusic.utils.manage_db import (
    get_all_filters,
    get_approved_users,
    get_blacklists,
    get_blstickers,
    get_chat_settings,
    get_flood_config,
    get_locks,
    get_rules,
    get_welcome,
    list_notes,
)
from AoiMusic.utils.manage_helpers import esc, mgmt_reply
from AoiMusic.utils.premium_emoji import pe


def _type_label(chat) -> str:
    raw = str(getattr(chat, "type", "group"))
    label = raw.rsplit(".", 1)[-1].replace("_", " ").lower()
    return label or "group"


async def _count_admins(client, chat_id) -> tuple[int, int]:
    admins = 0
    owners = 0
    async for member in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
        user = getattr(member, "user", None)
        if not user or user.is_bot or user.is_deleted:
            continue
        if str(getattr(member, "status", "")).upper().endswith("OWNER"):
            owners += 1
        else:
            admins += 1
    return owners, admins


async def _count_bots(client, chat_id) -> int:
    total = 0
    async for _member in client.get_chat_members(chat_id, filter=ChatMembersFilter.BOTS):
        total += 1
    return total


async def _member_count(client, chat_id) -> int | None:
    try:
        return int(await client.get_chat_members_count(chat_id))
    except Exception:
        return None


def _flag(value) -> str:
    return "on" if bool(value) else "off"


def _priv_bool(privileges, name: str) -> bool | None:
    if privileges is None:
        return None
    value = getattr(privileges, name, None)
    if value is None:
        return None
    return bool(value)


async def _bot_permission_line(client, chat_id) -> str:
    try:
        me = await client.get_me()
        member = await client.get_chat_member(chat_id, me.id)
    except Exception:
        return "Unknown"
    privileges = getattr(member, "privileges", None)
    checks = {
        "delete": _priv_bool(privileges, "can_delete_messages"),
        "restrict": _priv_bool(privileges, "can_restrict_members"),
        "pin": _priv_bool(privileges, "can_pin_messages"),
        "invite": _priv_bool(privileges, "can_invite_users"),
        "change info": _priv_bool(privileges, "can_change_info"),
        "promote": _priv_bool(privileges, "can_promote_members"),
    }
    parts = []
    for label, value in checks.items():
        if value is None:
            parts.append(f"{label}: unknown")
        else:
            parts.append(f"{label}: {'yes' if value else 'no'}")
    return ", ".join(parts)


@app.on_message(filters.command(["ginfo", "groupinfo", "chatinfo"]) & filters.group & ~BANNED_USERS)
async def group_info_cmd(client, message: Message):
    chat = message.chat
    title = esc(chat.title or "This group")
    chat_id = chat.id

    member_count = await _member_count(client, chat_id)
    owners, admins = await _count_admins(client, chat_id)
    bot_count = await _count_bots(client, chat_id)

    settings = await get_chat_settings(chat_id)
    welcome = await get_welcome(chat_id)
    locks = await get_locks(chat_id)
    flood = await get_flood_config(chat_id)
    blacklist = await get_blacklists(chat_id)
    blstickers = await get_blstickers(chat_id)
    approved = await get_approved_users(chat_id)
    notes = await list_notes(chat_id)
    filters_list = await get_all_filters(chat_id)
    rules = await get_rules(chat_id)

    active_locks = sum(1 for enabled in locks.values() if enabled)
    words = blacklist.get("words") or []
    sticker_sets = blstickers.get("sets") or []
    flood_limit = int(flood.get("limit") or 0)
    flood_label = f"{flood_limit}/min · {flood.get('mode', 'mute')}" if flood_limit > 0 else "disabled"

    lines = [
        f"{pe('INFO')} <b>ɢʀᴏᴜᴘ ᴏᴠᴇʀᴠɪᴇᴡ</b>",
        "",
        f"<b>ᴄʜᴀᴛ:</b> {title}",
        f"<b>ɪᴅ:</b> <code>{chat_id}</code> · <b>ᴛʏᴘᴇ:</b> <code>{esc(_type_label(chat))}</code>",
        f"<b>ᴍᴇᴍʙᴇʀs:</b> <code>{member_count if member_count is not None else 'unknown'}</code> · <b>ᴏᴡɴᴇʀ(s):</b> <code>{owners}</code> · <b>ᴀᴅᴍɪɴs:</b> <code>{admins}</code> · <b>ʙᴏᴛs:</b> <code>{bot_count}</code>",
        "",
        "<b>sᴇᴄᴜʀɪᴛʏ &amp; ᴍᴏᴅᴇʀᴀᴛɪᴏɴ</b>",
        f"Reports: <code>{_flag(settings.get('reports', True))}</code> · lockdown: <code>{_flag(settings.get('lockdown', False))}</code> · flood: <code>{esc(flood_label)}</code>",
        f"Locks enabled: <code>{active_locks}</code> · approved exempt: <code>{len(approved)}</code>",
        f"Blacklist: <code>{len(words)}</code> words / <code>{blacklist.get('mode', 'delete')}</code> · sticker sets: <code>{len(sticker_sets)}</code> / <code>{blstickers.get('mode', 'delete')}</code>",
        "",
        "<b>ɢʀᴏᴜᴘ sᴇᴛᴜᴘ</b>",
        f"Welcome: <code>{_flag(welcome.get('welcome_on'))}</code> · goodbye: <code>{_flag(welcome.get('goodbye_on'))}</code> · welcome mute: <code>{_flag(welcome.get('welcome_mute'))}</code>",
        f"Join-request panel: <code>{_flag(settings.get('joinrequest'))}</code> · clean welcome: <code>{_flag(welcome.get('clean_welcome'))}</code> · clean service: <code>{_flag(welcome.get('clean_service'))}</code>",
        f"Rules: <code>{'set' if rules else 'not set'}</code> · notes: <code>{len(notes)}</code> · filters: <code>{len(filters_list)}</code>",
        "",
        f"<b>ʙᴏᴛ ᴘᴇʀᴍs:</b> <code>{esc(await _bot_permission_line(client, chat_id))}</code>",
        "",
        "<i>Tip: use /grouphelp for moderation commands, or /export to back up these settings.</i>",
    ]
    await mgmt_reply(message, f"<blockquote>{chr(10).join(lines)}</blockquote>")
