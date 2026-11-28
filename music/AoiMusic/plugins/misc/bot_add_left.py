"""Single group-membership handler for Music logging and assistant lifecycle."""
from html import escape

from pyrogram import filters
from pyrogram.types import Message

from config import LOG, LOGGER_ID
from AoiMusic import LOGGER, app
from AoiMusic.utils.database import delete_served_chat, get_assistant, is_on_off


def _group_event_text(message: Message, *, added: bool, actor: str, members: int | None = None) -> str:
    chat = message.chat
    title = escape(chat.title or "Untitled group")
    username = getattr(chat, "username", None)
    public_name = f"@{escape(username)}" if username else "Private group"
    link = f'\n<b>Link:</b> <a href="https://t.me/{escape(username, quote=True)}">Open group</a>' if username else ""
    member_line = f"\n<b>Members:</b> {members}" if members is not None else ""
    heading = "➕ Fiona added to a group" if added else "➖ Fiona left a group"
    return (
        f"<b>{heading}</b>\n\n"
        f"<b>Group:</b> {title}\n"
        f"<b>Username:</b> {public_name}\n"
        f"<b>Chat ID:</b> <code>{int(chat.id)}</code>{member_line}{link}\n"
        f"{actor}"
    )


async def _event_destinations():
    """Always include Waifu GLOG; include Music LOGGER_ID when its log switch is on."""
    from aoiwaifu import GLOG

    destinations = [GLOG]
    try:
        if LOGGER_ID and await is_on_off(LOG):
            destinations.append(LOGGER_ID)
    except Exception as exc:
        LOGGER("Fiona.GroupEvents").warning(
            "Could not read Music log setting (%s); still sending to GLOG.",
            type(exc).__name__,
        )
    return destinations


@app.on_message(filters.new_chat_members)
async def on_bot_added(_, message: Message):
    bot_id = app.id
    if not bot_id:
        bot_id = (await app.get_me()).id
    if not any(getattr(member, "id", None) == bot_id for member in (message.new_chat_members or [])):
        return

    from aoiwaifu.modules.joinlog import mark_group_active
    from aoiwaifu.unit.event_logger import actor_details, send_event_logs

    await mark_group_active(message.chat)
    adder = actor_details(message.from_user, fallback="Telegram or a group admin", label="Added by")
    try:
        member_count = await app.get_chat_members_count(message.chat.id)
    except Exception:
        member_count = None
    try:
        await send_event_logs(
            app,
            await _event_destinations(),
            _group_event_text(message, added=True, actor=adder, members=member_count),
            logger_name="Fiona.GroupEvents",
        )
    except Exception as exc:
        LOGGER("Fiona.GroupEvents").warning(
            "Could not prepare group-added log (%s).", type(exc).__name__
        )

    username = getattr(message.chat, "username", None)
    if username:
        try:
            userbot = await get_assistant(message.chat.id)
            await userbot.join_chat(username)
        except Exception as exc:
            LOGGER("Fiona.GroupEvents").warning(
                "Assistant could not join group %s (%s).", message.chat.id, type(exc).__name__
            )


@app.on_message(filters.left_chat_member)
async def on_bot_kicked(_, message: Message):
    member = message.left_chat_member
    if not member:
        return
    bot_id = app.id
    if not bot_id:
        bot_id = (await app.get_me()).id
    if getattr(member, "id", None) != bot_id:
        return

    from aoiwaifu.modules.joinlog import mark_group_inactive
    from aoiwaifu.unit.event_logger import actor_details, send_event_logs

    await mark_group_inactive(message.chat.id)
    remover = actor_details(message.from_user, fallback="Telegram or a group admin", label="Removed by")
    try:
        await send_event_logs(
            app,
            await _event_destinations(),
            _group_event_text(message, added=False, actor=remover),
            logger_name="Fiona.GroupEvents",
        )
    except Exception as exc:
        LOGGER("Fiona.GroupEvents").warning(
            "Could not prepare group-left log (%s).", type(exc).__name__
        )

    try:
        await delete_served_chat(message.chat.id)
    except Exception as exc:
        LOGGER("Fiona.GroupEvents").warning(
            "Could not delete served-chat record %s (%s).", message.chat.id, type(exc).__name__
        )
    try:
        userbot = await get_assistant(message.chat.id)
        await userbot.leave_chat(message.chat.id)
    except Exception as exc:
        LOGGER("Fiona.GroupEvents").warning(
            "Assistant could not leave group %s (%s).", message.chat.id, type(exc).__name__
        )
