"""User character submission workflow with per-request ImgBB/Catbox selection."""

from aoiwaifu.unit.rich_ui import (
    send_media_panel,
    edit_panel,
    notice_card,
    premium_button,
    premium_text,
    reply_notice,
    rich_card,
)
import asyncio
import html
import os
import time
import uuid
from bson.objectid import ObjectId
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup

from aoiwaifu import CHARA_CHANNEL_ID, app as ZYRO, collection, db, rarity_map, require_power
from aoiwaifu.admin.upload import (
    character_channel_target_error,
    find_available_id,
    format_character_upload_error,
    upload_to_catbox,
    upload_to_imgbb,
)
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr
WRONG_FORMAT_TEXT = (
    "Wrong ❌ format...\n"
    "eg. /addchar muzan-kibutsuji Demon-slayer\n\n"
    "Format: /addchar <character-name> <anime-name>"
)
upload_collection = db.uploads
_pending_addchar_uploads = {}
_addchar_upload_lock = None
_PENDING_ADDCHAR_TTL = 10 * 60


def _get_addchar_upload_lock():
    global _addchar_upload_lock
    if _addchar_upload_lock is None:
        _addchar_upload_lock = asyncio.Lock()
    return _addchar_upload_lock


def _prune_addchar_uploads():
    now = time.monotonic()
    for token, pending in list(_pending_addchar_uploads.items()):
        if now - pending["created"] > _PENDING_ADDCHAR_TTL:
            _pending_addchar_uploads.pop(token, None)


def _addchar_host_keyboard(token):
    return InlineKeyboardMarkup([
        [
            premium_button("ImgBB", emoji="IMAGE_PHOTO", style="PRIMARY", callback_data=f"addcharhost:{token}:imgbb"),
            premium_button("Catbox", emoji="UPLOAD", style="PRIMARY", callback_data=f"addcharhost:{token}:catbox"),
        ],
        [premium_button("Cancel", emoji="CLOSE", style="DANGER", callback_data=f"addcharhost:{token}:cancel")],
    ])


@ZYRO.on_message(filters.command(["addchar"]))
async def request_upload(client, message):
    lang = await get_effective_lang(message)
    reply = message.reply_to_message
    if not reply or not (reply.photo or reply.document):
        return await reply_notice(message, tr("Please reply to a photo or image document.", lang))

    if reply.document:
        mime = getattr(reply.document, "mime_type", "") or ""
        if not mime.startswith("image/"):
            return await reply_notice(message, tr("Only image files are supported.", lang))

    args = (message.text or "").split()
    if len(args) != 3:
        return await reply_notice(message, tr(WRONG_FORMAT_TEXT, lang))
    if not CHARA_CHANNEL_ID:
        return await reply_notice(
            message,
            "Character submissions are unavailable until <code>CHARA_CHANNEL_ID</code> or <code>GLOG</code> is configured.",
        )
    target_error = character_channel_target_error(CHARA_CHANNEL_ID)
    if target_error:
        return await reply_notice(message, html.escape(target_error))

    _prune_addchar_uploads()
    token = uuid.uuid4().hex[:10]
    _pending_addchar_uploads[token] = {
        "created": time.monotonic(),
        "user_id": message.from_user.id,
        "user_name": message.from_user.first_name or "Collector",
        "source_message": reply,
        "name": args[1].replace("-", " ").title(),
        "anime": args[2].replace("-", " ").title(),
    }
    prompt = await reply_notice(
        message,
        tr("Select upload server:", lang),
        title="Choose an image host",
        reply_markup=_addchar_host_keyboard(token),
    )
    if not prompt:
        _pending_addchar_uploads.pop(token, None)


@ZYRO.on_callback_query(filters.regex(r"^addcharhost:([a-f0-9]{10}):(imgbb|catbox|cancel)$"))
async def choose_addchar_host(client, callback_query):
    lang = await get_effective_lang(callback_query)
    token, provider = callback_query.matches[0].group(1, 2)
    pending = _pending_addchar_uploads.get(token)
    if not pending or time.monotonic() - pending["created"] > _PENDING_ADDCHAR_TTL:
        _pending_addchar_uploads.pop(token, None)
        await callback_query.answer("This upload choice expired. Run /addchar again.", show_alert=True)
        return
    if callback_query.from_user.id != pending["user_id"]:
        await callback_query.answer("Only the person who started this submission can choose its host.", show_alert=True)
        return

    if provider == "cancel":
        _pending_addchar_uploads.pop(token, None)
        await callback_query.answer("Submission cancelled.")
        await edit_panel(
            callback_query.message,
            notice_card(tr("The character submission was cancelled.", lang)),
            reply_markup=None,
        )
        return

    lock = _get_addchar_upload_lock()
    if lock.locked():
        await callback_query.answer(
            tr("Another upload is in progress. Please wait until it is completed.", lang),
            show_alert=True,
        )
        return

    async with lock:
        pending = _pending_addchar_uploads.pop(token, None)
        if not pending:
            await callback_query.answer("This upload choice was already used or expired.", show_alert=True)
            return
        await callback_query.answer()
        path = None
        inserted_id = None
        try:
            await edit_panel(
                callback_query.message,
                notice_card(tr("Downloading image and submitting for review…", lang)),
                reply_markup=None,
            )
            path = await pending["source_message"].download()
            if not path:
                raise RuntimeError("Telegram did not return a local image file.")
            upload_func = upload_to_imgbb if provider == "imgbb" else upload_to_catbox
            img_url = await asyncio.to_thread(upload_func, path)
            upload_data = {
                "name": pending["name"],
                "anime": pending["anime"],
                "img_url": img_url,
                "image_host": "ImgBB" if provider == "imgbb" else "Catbox",
                "requested_by": {
                    "id": pending["user_id"],
                    "name": pending["user_name"],
                },
            }
            result = await upload_collection.insert_one(upload_data)
            inserted_id = result.inserted_id

            rarity_buttons = []
            rarity_items = list(rarity_map.items())
            for i in range(0, len(rarity_items), 4):
                row = [
                    premium_button(value, emoji="STAR", callback_data=f"rarity_{inserted_id}_{key}")
                    for key, value in rarity_items[i : i + 4]
                ]
                rarity_buttons.append(row)
            rarity_buttons.append(
                [premium_button("Cancel request", emoji="CLOSE", style="DANGER", callback_data=f"cancel_{inserted_id}")]
            )
            try:
                await send_media_panel(client,
                    chat_id=CHARA_CHANNEL_ID,
                    photo=img_url,
                    caption=premium_text(tr(
                        rich_card(
                            "Character submission pending",
                            f"<b>Name:</b> {html.escape(pending['name'])}\n"
                            f"<b>Anime:</b> {html.escape(pending['anime'])}\n"
                            f"<b>Image host:</b> {'ImgBB' if provider == 'imgbb' else 'Catbox'}\n"
                            f"<b>Requested by:</b> <a href='tg://user?id={pending['user_id']}'>"
                            f"{html.escape(pending['user_name'])}</a>\n\n"
                            "Choose a rarity to approve or cancel this request.",
                            "📥",
                        ),
                        lang,
                    )),
                    parse_mode="html",
                    reply_markup=InlineKeyboardMarkup(rarity_buttons),
                )
            except Exception:
                await upload_collection.delete_one({"_id": inserted_id})
                inserted_id = None
                raise

            await edit_panel(
                callback_query.message,
                notice_card(tr("✅ Your request has been submitted successfully!", lang)),
                reply_markup=None,
            )
        except Exception as exc:
            await edit_panel(
                callback_query.message,
                notice_card(tr(f"❌ Request upload failed.\nError: {format_character_upload_error(exc)}", lang)),
                reply_markup=None,
            )
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


@ZYRO.on_callback_query(filters.regex(r"^rarity_([0-9a-fA-F]+)_(\d+)$"))
@require_power(("add_character", "approve_request"))
async def approve_upload(client, callback_query):
    lang = await get_effective_lang(callback_query)
    upload_id = callback_query.matches[0].group(1)
    rarity_key = int(callback_query.matches[0].group(2))
    upload_data = await upload_collection.find_one({"_id": ObjectId(upload_id)})
    if not upload_data:
        return await callback_query.answer(tr("Request already processed or not found.", lang), show_alert=True)

    rarity_text = rarity_map.get(rarity_key, rarity_map[1])
    available_id = await find_available_id()
    character = {
        "name": upload_data["name"],
        "anime": upload_data["anime"],
        "rarity": rarity_text,
        "id": available_id,
        "img_url": upload_data["img_url"],
    }
    await collection.insert_one(character)
    await upload_collection.delete_one({"_id": ObjectId(upload_id)})
    await edit_panel(
        callback_query.message,
        tr(
            rich_card(
                "Character approved",
                f"<b>{html.escape(character['name'])}</b> · {html.escape(character['anime'])}\n"
                f"{html.escape(rarity_text)} · ID <code>{html.escape(str(available_id))}</code>\n"
                f"Approved by {html.escape(callback_query.from_user.first_name or 'Admin')}.",
                "✅",
            ),
            lang,
        ),
        reply_markup=None,
    )
    await callback_query.answer(tr("✅ Character approved and added!", lang))


@ZYRO.on_callback_query(filters.regex(r"^cancel_([0-9a-fA-F]+)$"))
@require_power(("add_character", "approve_request"))
async def cancel_upload(client, callback_query):
    lang = await get_effective_lang(callback_query)
    upload_id = callback_query.matches[0].group(1)
    await upload_collection.delete_one({"_id": ObjectId(upload_id)})
    await edit_panel(
        callback_query.message,
        tr(
            rich_card(
                "Submission cancelled",
                f"No character was added. Cancelled by {html.escape(callback_query.from_user.first_name or 'Admin')}.",
                "❌",
            ),
            lang,
        ),
        reply_markup=None,
    )
    await callback_query.answer(tr("❌ Request cancelled.", lang))
