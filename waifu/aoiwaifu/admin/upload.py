"""Admin character upload commands with a per-upload ImgBB/Catbox choice."""

from aoiwaifu.unit.rich_ui import (
    send_media_panel,
    edit_notice,
    premium_text,
    reply_notice,
    rich_showcase_panel,
    premium_button,
)
import asyncio
import html
import os
import requests
import time
import uuid
from urllib.parse import urlparse
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup

from aoiwaifu import (
    CHARA_CHANNEL_ID,
    IMGBB_API_KEYS,
    ZYRO,
    collection,
    rarity_map,
    require_power,
)
from aoiwaifu.unit.aoi_lang import get_effective_lang, tr

IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"


def character_channel_target_error(target) -> str | None:
    """Reject phone numbers and positive user IDs before beginning an upload."""
    if isinstance(target, int) and target >= 0:
        return (
            "CHARA_CHANNEL_ID/GLOG must be a channel or group destination, not a phone/user ID. "
            "Use the numeric chat ID (usually starts with -100) or a public @channel username."
        )
    if isinstance(target, str) and target.startswith("+") and target[1:].isdigit():
        return (
            "CHARA_CHANNEL_ID/GLOG is set to a phone number. Bots cannot resolve phone numbers; "
            "use the channel's numeric chat ID (usually starts with -100) or public @channel username."
        )
    return ""


def format_character_upload_error(error: Exception) -> str:
    """Give actionable setup guidance for bot-incompatible phone chat targets."""
    detail = str(error)
    if "contacts.ResolvePhone" in detail or "BOT_METHOD_INVALID" in detail:
        return (
            "Telegram is treating the configured character destination as a phone number, "
            "which bots cannot resolve. Set CHARA_CHANNEL_ID (or GLOG) to the channel's "
            "numeric chat ID, usually beginning with -100, or its public @channel username; "
            "do not use a phone number. Ensure Fiona can post in that channel."
        )
    return detail

def _uploaded_character_panel(character_id, name, anime, rarity, uploader_id, uploader_name):
    """Format the shared channel announcement for every accepted photo upload."""
    body = "<blockquote>\n" + "\n".join((
        f"🆔 <b>ID:</b> <code>{html.escape(str(character_id))}</code>",
        f"🎌 <b>Anime:</b> {html.escape(str(anime))}",
        f"👤 <b>Name:</b> {html.escape(str(name))}",
        f"✨ <b>Rarity:</b> {html.escape(str(rarity))}",
        "📂 <b>Type:</b> PHOTO",
        f"👑 <b>Uploaded By:</b> <a href=\"tg://user?id={int(uploader_id)}\">{html.escape(str(uploader_name or 'Admin'))}</a>",
    )) + "\n</blockquote>"
    return premium_text(rich_showcase_panel("NEW CHARACTER UPLOADED", body, "📝"))


WRONG_FORMAT_TEXT = (
    "Wrong ❌ format... eg. /gupload reply to photo muzan-kibutsuji Demon-slayer 3\n\n"
    "Format: /gupload <character-name> <anime-name> <rarity-number>\n\n"
    "Rarity numbers:\n"
    + "\n".join(f"{number}. {name}" for number, name in rarity_map.items())
)


async def find():
    cursor = collection.find().sort("id", 1)
    ids = []
    async for doc in cursor:
        if "id" in doc:
            try:
                ids.append(int(doc["id"]))
            except (TypeError, ValueError):
                continue
    ids.sort()
    for i in range(1, len(ids) + 2):
        if i not in ids:
            return str(i).zfill(2)
    return str(len(ids) + 1).zfill(2)


async def find_available_id():
    return await find()


def upload_to_imgbb(file_path: str) -> str:
    """Upload a local image file to ImgBB using configured API key(s)."""
    if not file_path or not os.path.isfile(file_path):
        raise Exception(f"Invalid file path: {file_path}")

    api_keys = list(IMGBB_API_KEYS) or [
        key.strip()
        for key in os.getenv("IMGBB_API_KEYS", os.getenv("IMGBB_API_KEY", "")).split(",")
        if key.strip()
    ]
    if not api_keys:
        raise Exception(
            "ImgBB API key is not configured. Set IMGBB_API_KEYS or IMGBB_API_KEY in your environment."
        )

    errors = []
    for index, api_key in enumerate(api_keys, start=1):
        try:
            with open(file_path, "rb") as image_file:
                response = requests.post(
                    IMGBB_UPLOAD_URL,
                    data={"key": api_key},
                    files={"image": image_file},
                    timeout=60,
                )
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("data", {}).get("url"):
                    return data["data"]["url"]
                err_msg = data.get("error", {}).get("message", "Unexpected ImgBB response")
                errors.append(f"key #{index}: {err_msg}")
            else:
                errors.append(f"key #{index}: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as exc:
            errors.append(f"key #{index}: {str(exc)[:200]}")

    raise Exception("ImgBB upload failed: " + " | ".join(errors))


CHARACTER_IMAGE_HOSTS = {"files.catbox.moe", "i.ibb.co", "endtrz.vercel.app"}


def require_character_image_url(image_url: str) -> str:
    """Accept only direct HTTPS image URLs from the supported Catbox/ImgBB hosts."""
    value = str(image_url or "").strip()
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in CHARACTER_IMAGE_HOSTS
        or not parsed.path.strip("/")
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use a direct HTTPS image URL from files.catbox.moe, i.ibb.co, or endtrz.vercel.app.")
    return value


def upload_to_catbox(file_path: str) -> str:
    """Upload one image to Catbox and validate its returned public URL."""
    if not file_path or not os.path.isfile(file_path):
        raise Exception(f"Invalid file path: {file_path}")
    if os.path.getsize(file_path) > 200 * 1024 * 1024:
        raise Exception("Catbox supports image uploads up to 200 MB.")

    with open(file_path, "rb") as image_file:
        response = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (os.path.basename(file_path), image_file)},
            timeout=90,
        )
    if response.status_code != 200:
        raise Exception(f"Catbox upload failed: HTTP {response.status_code}")

    image_url = (response.text or "").strip()
    parsed = urlparse(image_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "files.catbox.moe"
        or not parsed.path.strip("/")
    ):
        raise Exception("Catbox returned an invalid image URL.")
    return image_url


_upload_lock = None
_pending_uploads = {}
_PENDING_UPLOAD_TTL = 10 * 60


def _get_upload_lock() -> asyncio.Lock:
    global _upload_lock
    if _upload_lock is None:
        _upload_lock = asyncio.Lock()
    return _upload_lock


@ZYRO.on_message(filters.command(["add"]))
@require_power("add_character")
async def add_character_command(client, message):
    """Summon-compatible direct URL form: /add name anime rarity-id image-url."""
    lang = await get_effective_lang(message)
    args = (message.text or "").split()
    if len(args) != 5:
        await reply_notice(
            message,
            "Usage: <code>/add &lt;name&gt; &lt;anime&gt; &lt;rarity-id&gt; &lt;Catbox-or-ImgBB-HTTPS-URL&gt;</code>",
        )
        return
    if not CHARA_CHANNEL_ID:
        await reply_notice(message, "Set <code>CHARA_CHANNEL_ID</code> (or <code>GLOG</code>) before adding characters.")
        return
    target_error = character_channel_target_error(CHARA_CHANNEL_ID)
    if target_error:
        await reply_notice(message, html.escape(target_error))
        return

    name = args[1].replace("-", " ").title()
    anime = args[2].replace("-", " ").title()
    try:
        rarity_number = int(args[3])
        rarity = rarity_map[rarity_number]
        image_url = require_character_image_url(args[4])
    except (ValueError, KeyError) as exc:
        await reply_notice(message, f"Invalid rarity or image URL: {html.escape(str(exc))}")
        return

    lock = _get_upload_lock()
    if lock.locked():
        await reply_notice(message, tr("Another upload is in progress. Please wait until it is completed.", lang))
        return
    async with lock:
        available_id = await find_available_id()
        character = {
            "name": name,
            "anime": anime,
            "rarity": rarity,
            "id": available_id,
            "img_url": image_url,
        }
        try:
            await send_media_panel(client,
                chat_id=CHARA_CHANNEL_ID,
                photo=image_url,
                caption=_uploaded_character_panel(
                    available_id,
                    name,
                    anime,
                    rarity,
                    message.from_user.id,
                    message.from_user.first_name,
                ),
                parse_mode="html",
            )
            await collection.insert_one(character)
            await reply_notice(message, tr(f"Character {name} added as ID {available_id}.", lang))
        except Exception as exc:
            await reply_notice(message, f"Character add failed: {html.escape(format_character_upload_error(exc))}")


@ZYRO.on_message(filters.command(["find"]))
@require_power("add_character")
async def find_next_id_cmd(client, message):
    lang = await get_effective_lang(message)
    available_id = await find()
    await reply_notice(message, tr(f"Next available character ID: `{available_id}`", lang))


def _prune_pending_uploads() -> None:
    now = time.monotonic()
    for token, pending in list(_pending_uploads.items()):
        if now - pending["created"] > _PENDING_UPLOAD_TTL:
            _pending_uploads.pop(token, None)


def _provider_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            premium_button("ImgBB", emoji="IMAGE_PHOTO", style="PRIMARY", callback_data=f"gupload:{token}:imgbb"),
            premium_button("Catbox", emoji="UPLOAD", style="PRIMARY", callback_data=f"gupload:{token}:catbox"),
        ],
        [premium_button("Cancel", emoji="CLOSE", style="DANGER", callback_data=f"gupload:{token}:cancel")],
    ])


async def _finish_upload(client, status_message, pending, provider: str, lang: str) -> None:
    path = None
    provider_name = "ImgBB" if provider == "imgbb" else "Catbox"
    try:
        await edit_notice(
            status_message,
            f"Downloading image, then uploading to {provider_name}…",
            emoji="⏳",
            title="Character upload",
            reply_markup=None,
        )
        path = await pending["source_message"].download()
        if not path:
            raise RuntimeError("Telegram did not return a local image file.")

        upload_func = upload_to_imgbb if provider == "imgbb" else upload_to_catbox
        file_url = await asyncio.to_thread(upload_func, path)
        available_id = await find_available_id()
        character = {
            "name": pending["name"],
            "anime": pending["anime"],
            "rarity": pending["rarity"],
            "id": available_id,
            "img_url": file_url,
        }
        await send_media_panel(client,
            chat_id=CHARA_CHANNEL_ID,
            photo=file_url,
            caption=_uploaded_character_panel(
                available_id,
                pending["name"],
                pending["anime"],
                pending["rarity"],
                pending["user_id"],
                pending["user_name"],
            ),
            parse_mode="html",
        )
        await collection.insert_one(character)
        await edit_notice(
            status_message,
            f"<b>Name:</b> {html.escape(pending['name'])}\n"
            f"<b>Anime:</b> {html.escape(pending['anime'])}\n"
            f"<b>Character ID:</b> <code>{available_id}</code>\n"
            f"<b>Rarity:</b> {html.escape(str(pending['rarity']))}\n"
            f"<b>Image host:</b> {provider_name}\n"
            f"<b>Sent to:</b> <code>{html.escape(str(CHARA_CHANNEL_ID))}</code>",
            emoji="✅",
            title="Character added",
        )
    except Exception as exc:
        try:
            await edit_notice(
                status_message,
                f"Upload failed.\n{html.escape(format_character_upload_error(exc))}",
                emoji="❌",
                title="Character upload",
            )
        except Exception:
            pass
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


@ZYRO.on_message(filters.command(["gupload", "u", "upload"]))
@require_power("add_character")
async def ul_main(client, message):
    lang = await get_effective_lang(message)
    reply = message.reply_to_message
    if not reply or not (reply.photo or reply.document):
        await reply_notice(message, tr("Please reply to a photo or image document.", lang))
        return

    if reply.document:
        mime = getattr(reply.document, "mime_type", "") or ""
        if not mime.startswith("image/"):
            await reply_notice(message, tr("Only image files are supported for character uploads.", lang))
            return

    args = (message.text or "").split()
    if len(args) != 4:
        await reply_notice(message, tr(WRONG_FORMAT_TEXT, lang))
        return

    character_name = args[1].replace("-", " ").title()
    anime = args[2].replace("-", " ").title()
    try:
        rarity_number = int(args[3])
    except ValueError:
        await reply_notice(message, tr(WRONG_FORMAT_TEXT, lang))
        return

    if rarity_number not in rarity_map:
        await reply_notice(
            message,
            tr(f"Invalid rarity value. Choose a number from 1 to {len(rarity_map)}.", lang),
        )
        return
    if not CHARA_CHANNEL_ID:
        await reply_notice(
            message,
            "Set <code>CHARA_CHANNEL_ID</code> (or <code>GLOG</code>) before uploading characters.",
            emoji="⚠️",
            title="Character channel is not configured",
        )
        return
    target_error = character_channel_target_error(CHARA_CHANNEL_ID)
    if target_error:
        await reply_notice(message, html.escape(target_error), emoji="⚠️", title="Character channel configuration")
        return

    _prune_pending_uploads()
    token = uuid.uuid4().hex[:10]
    _pending_uploads[token] = {
        "created": time.monotonic(),
        "user_id": message.from_user.id,
        "user_name": message.from_user.first_name or "Admin",
        "source_message": reply,
        "name": character_name,
        "anime": anime,
        "rarity": rarity_map[rarity_number],
    }
    prompt = await reply_notice(
        message,
        tr("Select upload server:", lang),
        title="Character image host",
        reply_markup=_provider_keyboard(token),
    )
    if not prompt:
        _pending_uploads.pop(token, None)


@ZYRO.on_callback_query(filters.regex(r"^gupload:([a-f0-9]{10}):(imgbb|catbox|cancel)$"))
@require_power("add_character")
async def choose_upload_provider(client, callback_query):
    lang = await get_effective_lang(callback_query)
    token, provider = callback_query.matches[0].group(1, 2)
    pending = _pending_uploads.get(token)
    if not pending or time.monotonic() - pending["created"] > _PENDING_UPLOAD_TTL:
        _pending_uploads.pop(token, None)
        await callback_query.answer("This upload choice expired. Run /gupload again.", show_alert=True)
        return
    if callback_query.from_user.id != pending["user_id"]:
        await callback_query.answer("Only the admin who started this upload can choose its host.", show_alert=True)
        return

    if provider == "cancel":
        _pending_uploads.pop(token, None)
        await callback_query.answer("Upload cancelled.")
        await edit_notice(callback_query.message, "The character upload was cancelled.", emoji="ℹ️")
        return

    lock = _get_upload_lock()
    if lock.locked():
        await callback_query.answer(
            tr("Another upload is in progress. Please wait until it is completed.", lang),
            show_alert=True,
        )
        return

    async with lock:
        pending = _pending_uploads.pop(token, None)
        if not pending:
            await callback_query.answer("This upload choice was already used or expired.", show_alert=True)
            return
        await callback_query.answer()
        await _finish_upload(client, callback_query.message, pending, provider, lang)
