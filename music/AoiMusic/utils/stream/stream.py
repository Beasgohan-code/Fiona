

#

import asyncio
import aiohttp
import logging
import os
import time as _time
from functools import partial
from urllib.parse import urlencode
from weakref import WeakValueDictionary
from random import randint
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from AoiMusic import Platform, app, userbot
from AoiMusic.core.call import AoiCall, MEDIA_ERRORS
from AoiMusic.misc import db
from AoiMusic.utils.database import (
    add_active_video_chat,
    get_vc_lyrics,
    is_video_allowed,
    get_instant_play,
)
from AoiMusic.utils.exceptions import AssistantErr
from AoiMusic.utils.formatters import time_to_seconds
from AoiMusic.utils.inline.playlist import close_markup
from AoiMusic.utils.media_store import download_cached_audio, schedule_store_audio
from AoiMusic.utils.pastebin import AoiBin
from AoiMusic.utils.rich_msg import edit_any
from AoiMusic.utils.rich_panels import (
    notice_card,
    refresh_panel,
    replace_panel,
    spawn_now_playing,
)
from AoiMusic.utils.stream import lyrics as lyrics_display
from AoiMusic.utils.stream.queue import put_queue, put_queue_index
from AoiMusic.utils.thumbnails import gen_qthumb, gen_thumb
slog = logging.getLogger("AoiMusic.utils.stream.stream")


_VIDEO_HEIGHTS = (144, 240, 360, 480, 720, 1080, 1440, 2160)


def _video_height() -> int:
    limit = getattr(config, "VIDEO_STREAM_LIMIT", 720) or 720
    allowed = [h for h in _VIDEO_HEIGHTS if h <= limit]
    return allowed[-1] if allowed else 360


_prefetch_tasks = {}
_stream_locks = WeakValueDictionary()


async def _start_lyrics(chat_id, title, duration, playback_started=None):
    """Show synced lyrics for the track that just started, posted by the assistant.

    Every path in stream() that joins the call calls this. Three of them did not,
    in three separate commits, each reported as "lyrics stopped working" — because
    a path that forgets to call this is indistinguishable, from the outside and
    from the log, from a lyrics endpoint that has broken.
    """
    try:
        if not await get_vc_lyrics(chat_id):
            return
    except Exception as e:
        slog.warning(
            "[%s] lyrics setting unreadable for %s: %s: %s",
            _STREAM_LOG, chat_id, type(e).__name__, e,
        )
        return
    seconds = None
    try:
        seconds = time_to_seconds(duration)
    except Exception:
        seconds = None
    try:
        assistant = userbot.clients[0]
    except Exception:
        assistant = None
    if assistant is None:
        return
    use_title = getattr(config, "VC_LYRICS_TITLE", "True") in (True, "True", "true")
    post_message = getattr(config, "VC_LYRICS_MESSAGE", "False") in (True, "True", "true")

    async def _show():
        try:
            await lyrics_display.start(
                assistant, chat_id, title, seconds,
                post_message=post_message, use_title=use_title,
                playback_started=playback_started,
            )
        except Exception as e:
            slog.warning(
                "[%s] lyrics failed for %s: %s: %s",
                _STREAM_LOG, title[:40], type(e).__name__, e,
            )

    asyncio.create_task(_show())


def _prefetch_next(chat_id):
    """Warm the permalink for the next queued track while this one plays.

    Resolving takes ~4s; doing it now means the switch costs nothing.
    """
    queued = db.get(chat_id) or []
    if len(queued) < 2:
        return
    nxt = queued[1]
    vidid = nxt.get("vidid")
    if not vidid or vidid == "telegram":
        return
    video = nxt.get("streamtype") == "video"
    if _prefetch_tasks.get(chat_id) and not _prefetch_tasks[chat_id].done():
        return

    async def _warm():
        try:
            if not video:
                cached = await download_cached_audio(vidid)
                if cached:
                    slog.info("[%s] prefetched Store cache for next track %s", _STREAM_LOG, vidid)
                    return
            if (
                (getattr(config, "MEDIA_API_URL", "") or "").strip()
                and (getattr(config, "MEDIA_API_KEY", "") or "").strip()
            ) or (
                (getattr(config, "SHIZUMUSIC_API_URL", "") or "").strip()
                and (getattr(config, "SHIZUMUSIC_API_KEY", "") or "").strip()
            ):
                mtype = "video" if video else "audio"
                path = await Platform.youtube._api_download(vidid, media_type=mtype)
                if path:
                    slog.info("[%s] prefetched local %s for next track %s", _STREAM_LOG, mtype, vidid)
                    return
            if await _api_stream_url(vidid, bool(video)):
                slog.info("[%s] prefetched permalink for next track %s", _STREAM_LOG, vidid)
        except Exception:
            pass

    _prefetch_tasks[chat_id] = asyncio.create_task(_warm())


async def _update_play_status(mystic, text):
    """Best-effort progress update; status failures must not stop playback."""
    if mystic is None:
        return
    try:
        updated = await mystic.edit_text(text)
        if updated is False:
            slog.debug("[%s] could not update playback status", _STREAM_LOG)
    except Exception as exc:
        slog.debug("[%s] playback status edit failed: %s", _STREAM_LOG, exc)


async def _await_with_progress(awaitable, mystic, label, interval=20):
    """Await a slow media operation while keeping its status card informative."""
    task = asyncio.ensure_future(awaitable)
    started = _time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                return task.result()
            elapsed = max(1, int(_time.monotonic() - started))
            await _update_play_status(mystic, f"⏳ {label}… ({elapsed}s)")
    except BaseException:
        if not task.done():
            task.cancel()
        raise


async def _api_stream_url(vidid, video):
    """Fetch a direct MP3/MP4 stream URL from the Aoi Hosting Music API."""
    if not (getattr(config, "MEDIA_API_KEY", "") or "").strip():
        return None
    try:
        return await Platform.youtube.get_media_url(
            vidid, media_type="video" if video else "audio"
        )
    except Exception as exc:
        slog.warning("Aoi Music API failed for %s: %s", vidid, exc)
        return None

def _youtube_download_error_hint(exc: Exception) -> str:
    """Turn yt-dlp's wrapped exception into a safe, useful user-facing hint."""
    details = []
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        details.append(str(current).lower())
        current = current.__cause__ or current.__context__
    detail = " ".join(details)

    sign_in_errors = (
        "sign in to confirm",
        "confirm you're not a bot",
        "cookies are no longer valid",
        "login required",
    )
    if any(term in detail for term in sign_in_errors):
        return (
            "YouTube requires a valid login session for this track. If it is available to your account, "
            "refresh the Render cookies Secret File and redeploy."
        )
    unavailable_errors = (
        "private video",
        "video unavailable",
        "has been removed",
        "not available in your country",
    )
    if any(term in detail for term in unavailable_errors):
        return "This video is unavailable to Fiona (private, removed, or region restricted). Try another track."
    if "requested format is not available" in detail or "no video formats found" in detail:
        return (
            "YouTube returned no compatible format for this track, even after alternate client retries. "
            "It may be restricted or temporarily unavailable; try another track."
        )
    if any(term in detail for term in ("http error 403", "http error 429", "forbidden")):
        return (
            "YouTube refused the download request. Check the Render logs; a fresh "
            "cookie file or a different track may help."
        )
    if "timeout" in detail or "timed out" in detail:
        return "YouTube timed out while downloading this track. Please retry in a little while."
    return "Could not download this track. Check the Render logs near this time for the yt-dlp error details."


async def play_youtube_source(vidid, video, mystic, play, instant=True, title=""):
    """Fastest & most reliable playback path: local 1-hop API download for BOTH
    audio (MP3) and video (MP4), avoiding remote FFmpeg probe/Range failures
    during /vplay, /skip, and Autoplay."""
    has_aoi_api = bool(
        (getattr(config, "MEDIA_API_URL", "") or "").strip()
        and (getattr(config, "MEDIA_API_KEY", "") or "").strip()
    )
    has_shizumusic_api = bool(
        (getattr(config, "SHIZUMUSIC_API_URL", "") or "").strip()
        and (getattr(config, "SHIZUMUSIC_API_KEY", "") or "").strip()
    )
    has_api = has_aoi_api or has_shizumusic_api
    mtype = "video" if video else "audio"
    # Persistent Store cache first: if this exact track was uploaded earlier, fetch
    # it from the private channel and play without another YouTube request.
    if not video:
        cached_path = await download_cached_audio(vidid)
        if cached_path:
            await _update_play_status(mystic, "⚡ Loading this track from Fiona’s Store…")
            try:
                await play(cached_path)
                return cached_path
            except (*MEDIA_ERRORS, aiohttp.ClientError, OSError) as exc:
                slog.warning(
                    "Store cache playback failed for %s (%s: %s) -> continuing with providers",
                    vidid, type(exc).__name__, exc,
                )
                try:
                    if os.path.exists(cached_path) and os.path.basename(cached_path).startswith("store_"):
                        os.remove(cached_path)
                except OSError:
                    pass
    # Primary fast-path: download MP3/MP4 locally from Music API (0ms if cached/prefetched),
    # then play directly from local disk so FFmpeg never fails on remote MP4 probing or /skip!
    if has_api:
        await _update_play_status(mystic, "⚡ Finding the best source for your track…")
        api_path = await _await_with_progress(
            Platform.youtube._api_download(vidid, media_type=mtype),
            mystic,
            "Getting your track ready",
        )
        if api_path:
            try:
                await play(api_path)
                if not video:
                    schedule_store_audio(vidid, api_path, title=title)
                return api_path
            except (*MEDIA_ERRORS, aiohttp.ClientError, OSError) as exc:
                slog.warning(
                    "Local API %s playback failed for %s (%s: %s) -> cleaning file & retrying fallback",
                    mtype,
                    vidid,
                    type(exc).__name__,
                    exc,
                )
                Platform.youtube.invalidate_media_url(vidid, mtype)
                try:
                    if os.path.exists(api_path):
                        os.remove(api_path)
                except OSError:
                    pass

    if instant:
        permalink = None
        if has_aoi_api:
            await _update_play_status(mystic, "🎧 Trying a direct stream for quicker playback…")
            permalink = await _await_with_progress(
                _api_stream_url(vidid, video),
                mystic,
                "Finding a direct stream",
            )
            if permalink:
                try:
                    await play(permalink)
                    return permalink
                except (*MEDIA_ERRORS, aiohttp.ClientError, OSError) as exc:
                    slog.warning(
                        "Media API %s stream fallback failed for %s (%s: %s) -> evicting cache",
                        mtype,
                        vidid,
                        type(exc).__name__,
                        exc,
                    )
                    Platform.youtube.invalidate_media_url(vidid, mtype)
        if not permalink:
            try:
                ok, direct = await Platform.youtube.stream_url(
                    vidid, videoid=True, video=video, use_api=False
                )
            except Exception as exc:
                slog.warning("Direct URL lookup failed for %s (%s)", vidid, type(exc).__name__)
            else:
                if ok and direct:
                    try:
                        await play(direct)
                        return direct
                    except MEDIA_ERRORS as exc:
                        slog.warning("Direct playback failed for %s (%s)", vidid, type(exc).__name__)
    await _update_play_status(
        mystic,
        "🎵 That source isn’t available yet. Switching to a reliable download…"
        if has_api else "🎵 Preparing your track for playback…",
    )
    try:
        path, _ = await _await_with_progress(
            Platform.youtube.download(vidid, mystic, videoid=True, video=video),
            mystic,
            "Preparing your track for playback",
        )
    except Exception as exc:
        slog.exception("[%s] YouTube download failed for vidid=%s", _STREAM_LOG, vidid)
        error_hint = _youtube_download_error_hint(exc)
        if has_api:
            error_hint += " The configured download API was also attempted; check the preceding ShizuMusic/Aoi API warnings for its failure reason."
        else:
            error_hint += " No media download API is configured; set SHIZUMUSIC_API_URL/SHIZUMUSIC_API_KEY or MEDIA_API_URL/MEDIA_API_KEY privately in the deployment environment."
        raise AssistantErr(error_hint) from exc
    try:
        await play(path)
    except MEDIA_ERRORS as exc:
        raise AssistantErr(f"Could not play the downloaded media ({type(exc).__name__}).") from exc
    if not video:
        schedule_store_audio(vidid, path, title=title)
    return path


_STREAM_LOG = "Stream"
_MEDIA_API_URL = config.MEDIA_API_URL


def _play_source_tag(stream_link) -> str | None:
    """Which pipe actually fuels this track — the card prints it "via".

    An Aoi media permalink (…/stream/<id>) or a local ShizuMusic download is
    labeled by its provider; anything else (googlevideo URL or a downloaded
    file) came through the bot's own yt-dlp. Telegram/soundcloud/saavn entries carry no tag here:
    the panel falls back to a file-prefix label for those.
    """
    if stream_link is None:
        return None
    s = str(stream_link)
    if s.startswith("downloads/store_"):
        return "Fiona Store"
    if s.startswith("downloads/shizumusic/"):
        return "ShizuMusic API"
    if (
        (_MEDIA_API_URL and s.startswith(str(_MEDIA_API_URL).rstrip("/")))
        or ((getattr(config, "MEDIA_API_KEY", "") or "").strip() and s.startswith("downloads/"))
    ):
        return "AoiMusic Api"
    return "YouTube"


async def stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
):
    lock = _stream_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        try:
            return await _stream(_, mystic, user_id, result, chat_id, user_name,
                                 original_chat_id, video, streamtype, spotify, forceplay)
        except MEDIA_ERRORS as exc:
            raise AssistantErr(f"Playback failed ({type(exc).__name__}).") from exc


async def _stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
):
    st0 = _time.monotonic()
    slog.info(
        "[%s] stream() entry streamtype=%s chat=%s video=%s forceplay=%s result=%s",
        _STREAM_LOG, streamtype, chat_id, video, forceplay,
        str(result)[:80] if result else "None",
    )
    if not result:
        # A playlist that yields zero entries (Radio/Mix links cannot be
        # fetched) used to leave both the status card and the user hanging.
        if streamtype == "playlist":
            raise AssistantErr(_["playlist_26"])
        return
    if video:
        if not await is_video_allowed(chat_id):
            raise AssistantErr(_["play_7"])
    if forceplay:
        await AoiCall.force_stop_stream(chat_id)
    if streamtype == "playlist":
        # Respect the caller's video flag (/vplay playlist plays & queues as video, /play as audio).
        msg = f"{_['playlist_16']}\n\n"
        count = 0
        started_track = False
        # Resolving one track to its video id takes the better part of a
        # second, and a playlist has hundreds of them: done one after another a
        # fifty-track list spends most of a minute in silence before the first
        # note. They are looked up together instead, a handful at a time so the
        # search backend is not hammered, and the results keep their order.
        entries = list(result)[: config.PLAYLIST_FETCH_LIMIT * 2]
        semaphore = asyncio.Semaphore(8)

        async def _resolve(search):
            async with semaphore:
                try:
                    return await Platform.youtube.details(
                        search, False if spotify else True
                    )
                except Exception:
                    return None

        slog.info("[%s] playlist: resolving %d entries", _STREAM_LOG, len(entries))
        _resolved = await asyncio.gather(*[_resolve(item) for item in entries])
        slog.info(
            "[%s] playlist: resolved %d/%d in %.1fs",
            _STREAM_LOG, len([r for r in _resolved if r]), len(entries),
            _time.monotonic() - st0,
        )
        for details in _resolved:
            if details is None:
                continue
            try:
                (
                    title,
                    duration_min,
                    duration_sec,
                    thumbnail,
                    vidid,
                ) = details
            except Exception:
                continue
            if str(duration_min) == "None":
                continue
            if duration_sec > config.DURATION_LIMIT:
                continue
            if await AoiCall.is_live_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                )
                _prefetch_next(chat_id)
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}- {title[:70]}\n"
                msg += f"{_['playlist_17']} {position}\n\n"
            else:
                if not forceplay:
                    db[chat_id] = []
                status = True if video else None
                instant = await get_instant_play(chat_id)
                stream_link = await play_youtube_source(
                    vidid, status, mystic,
                    partial(AoiCall.join_call, chat_id, original_chat_id, video=status, image=thumbnail),
                    instant=instant,
                    title=title,
                )
                # The playlist path joins the call but never told the lyrics
                # display anything, so a track started from a playlist produced no
                # lyrics at all — the same silence a broken endpoint produces, with
                # nothing in the log to tell the two apart.
                asyncio.create_task(
                    _start_lyrics(chat_id, title, duration_min)
                )
                slog.info("[%s] join_call done for vidid=%s", _STREAM_LOG, vidid)
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                    forceplay=forceplay,
                )
                try:
                    db[chat_id][0]["source"] = _play_source_tag(stream_link)
                except Exception:
                    pass
                started_track = True
                img = await gen_thumb(vidid)
                mid_np = await spawn_now_playing(
                    _, chat_id, vidid, title, duration_min, user_name,
                    thumb=img,
                )
        if count == 0:
            if started_track:
                return
            # Radio/Mix playlists resolve to nothing — a silent return used to
            # leave the user staring at a dead status card with no feedback, so
            # surface the failure so the play handler shows an error card.
            raise AssistantErr(_["playlist_26"])
        else:
            link = await AoiBin(msg)
            lines = msg.count("\n")
            if lines >= 17:
                car = os.linesep.join(msg.split(os.linesep)[:17])
            else:
                car = msg
            mid_np = await notice_card(
                _, original_chat_id, "ᴘʟᴀʏʟɪꜱᴛ ꜱᴜᴍᴍᴀʀʏ",
                _["playlist_18"].format(link, position),
            )
            return

    elif streamtype == "youtube":
        link = result["link"]
        vidid = result["vidid"]
        try:
            from AoiMusic.utils.autoplay import record_played_track
            record_played_track(chat_id, vidid, result.get("title"))
        except Exception:
            pass
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        thumbnail = result["thumb"]
        status = True if video else None
        if await AoiCall.is_live_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            mid_np = await notice_card(
                _, original_chat_id, "Qᴜᴇᴜᴇ",
                _["queue_4"].format(position, title[:27], duration_min, user_name),
                thumb=thumbnail or await gen_qthumb(vidid),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            _jt = _time.monotonic()
            stream_link = await play_youtube_source(
                vidid, status, mystic,
                partial(AoiCall.join_call, chat_id, original_chat_id, video=status, image=thumbnail),
                instant=await get_instant_play(chat_id),
                title=result.get("title", ""),
            )
            asyncio.create_task(
                _start_lyrics(chat_id, title, duration_min,
                              playback_started=_time.monotonic())
            )
            _prefetch_next(chat_id)
            slog.info(
                "[%s] join_call took %.1fs (link_ready_age=%.1fs)",
                _STREAM_LOG, _time.monotonic() - _jt, _time.monotonic() - st0,
            )
            await put_queue(
                chat_id,
                original_chat_id,
                f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            try:
                db[chat_id][0]["source"] = _play_source_tag(stream_link)
            except Exception:
                pass
            mid_np = await spawn_now_playing(
                _, chat_id, vidid, title, duration_min, user_name,
                thumb=thumbnail or await gen_thumb(vidid),
            )
        slog.info("[%s] youtube branch completed in %.1fs for vidid=%s", _STREAM_LOG, _time.monotonic() - st0, vidid)

    elif "saavn" in streamtype:
        if streamtype == "saavn_track":
            if result["duration_sec"] == 0:
                return
            file_path = result["filepath"]
            title = result["title"]
            duration_min = result["duration_min"]
            link = result["url"]
            thumb = result["thumb"]
            if await AoiCall.is_live_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path,
                    title,
                    duration_min,
                    user_name,
                    streamtype,
                    user_id,
                    "audio",
                    url=link,
                )
                position = len(db.get(chat_id)) - 1
                mid_np = await notice_card(
                    _, original_chat_id, "Qᴜᴇᴜᴇ",
                    _["queue_4"].format(position, title[:30], duration_min, user_name),
                    thumb=thumb,
                )
            else:
                if not forceplay:
                    db[chat_id] = []
                await AoiCall.join_call(chat_id, original_chat_id, file_path, video=None)
                asyncio.create_task(
                    _start_lyrics(chat_id, title, duration_min)
                )
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path,
                    title,
                    duration_min,
                    user_name,
                    streamtype,
                    user_id,
                    "audio",
                    forceplay=forceplay,
                    url=link,
                )
                mid_np = await spawn_now_playing(
                    _, chat_id, None, title, duration_min, user_name,
                    thumb=thumb,
                )

        elif streamtype == "saavn_playlist":
            msg = f"{_['playlist_16']}\n\n"
            count = 0
            for search in result:
                if search["duration_sec"] == 0:
                    continue
                title = search["title"]
                duration_min = search["duration_min"]
                duration_sec = search["duration_sec"]
                link = search["url"]
                thumb = search["thumb"]
                file_path, details = await Platform.saavn.download(link)
                if await AoiCall.is_live_chat(chat_id):
                    await put_queue(
                        chat_id,
                        original_chat_id,
                        file_path,
                        title,
                        duration_min,
                        user_name,
                        streamtype,
                        user_id,
                        "audio",
                        url=link,
                    )
                    position = len(db.get(chat_id)) - 1
                    count += 1
                    msg += f"{count}- {title[:70]}\n"
                    msg += f"{_['playlist_17']} {position}\n\n"

                else:

                    if not forceplay:
                        db[chat_id] = []
                    await AoiCall.join_call(
                        chat_id, original_chat_id, file_path, video=None
                    )
                    asyncio.create_task(
                        _start_lyrics(chat_id, title, duration_min)
                    )
                    await put_queue(
                        chat_id,
                        original_chat_id,
                        file_path,
                        title,
                        duration_min,
                        user_name,
                        streamtype,
                        user_id,
                        "audio",
                        forceplay=forceplay,
                        url=link,
                    )
                    mid_np = await spawn_now_playing(
                        _, chat_id, None, title, duration_min, user_name,
                        thumb=thumb,
                    )
            if count == 0:
                return
            else:
                link = await AoiBin(msg)
                lines = msg.count("\n")
                if lines >= 17:
                    car = os.linesep.join(msg.split(os.linesep)[:17])
                else:
                    car = msg
                mid_np = await notice_card(
                    _, original_chat_id, "ᴘʟᴀʏʟɪꜱᴛ ꜱᴜᴍᴍᴀʀʏ",
                    _["playlist_18"].format(link, position),
                )
                return

    elif streamtype == "soundcloud":
        file_path = result["filepath"]
        title = result["title"]
        duration_min = result["duration_min"]
        if await AoiCall.is_live_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
            )
            position = len(db.get(chat_id)) - 1
            await notice_card(
                _,
                original_chat_id,
                "Qᴜᴇᴜᴇ",
                _["queue_4"].format(position, title[:30], duration_min, user_name),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await AoiCall.join_call(chat_id, original_chat_id, file_path, video=None)
            asyncio.create_task(_start_lyrics(chat_id, title, duration_min))
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
                forceplay=forceplay,
            )
            mid_np = await spawn_now_playing(
                _, chat_id, None, title, duration_min, user_name,
                thumb=config.SOUNCLOUD_IMG_URL,
            )
    elif streamtype == "telegram":
        file_path = result["path"]
        link = result["link"]
        title = (result["title"]).title()
        duration_min = result["dur"]
        status = True if video else None
        if await AoiCall.is_live_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            await notice_card(
                _,
                original_chat_id,
                "Qᴜᴇᴜᴇ",
                _["queue_4"].format(position, title[:30], duration_min, user_name),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await AoiCall.join_call(chat_id, original_chat_id, file_path, video=status)
            asyncio.create_task(_start_lyrics(chat_id, title, duration_min))
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            if video:
                await add_active_video_chat(chat_id)
            mid_np = await spawn_now_playing(
                _, chat_id, None, title, duration_min, user_name,
                thumb=config.TELEGRAM_VIDEO_URL if video else config.TELEGRAM_AUDIO_URL,
            )
    elif streamtype == "live":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        thumbnail = result["thumb"]
        duration_min = "00:00"
        status = True if video else None
        if await AoiCall.is_live_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            await notice_card(
                _,
                original_chat_id,
                "Qᴜᴇᴜᴇ",
                _["queue_4"].format(position, title[:30], duration_min, user_name),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            slog.info("[%s] live branch: calling video() for link=%s", _STREAM_LOG, link[:80])
            n, file_path = await Platform.youtube.video(link)
            slog.info("[%s] video() returned n=%s", _STREAM_LOG, n)
            if n == 0:
                raise AssistantErr(_["str_3"])
            await AoiCall.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=thumbnail if thumbnail else None,
            )
            asyncio.create_task(_start_lyrics(chat_id, title, duration_min))
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            img = await gen_thumb(vidid)
            mid_np = await spawn_now_playing(
                _, chat_id, vidid, title, duration_min, user_name,
                thumb=img,
            )
    elif streamtype == "index":
        link = result
        title = "Index or M3u8 Link"
        duration_min = "URL stream"
        if await AoiCall.is_live_chat(chat_id):
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            await edit_any(
                mystic,
                _["queue_4"].format(position, title[:30], duration_min, user_name),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await AoiCall.join_call(
                chat_id,
                original_chat_id,
                link,
                video=True if video else None,
            )
            asyncio.create_task(_start_lyrics(chat_id, title, duration_min))
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            mid_np = await spawn_now_playing(
                _, chat_id, None, title, duration_min, user_name,
                thumb=config.STREAM_IMG_URL,
            )
            await mystic.delete()
