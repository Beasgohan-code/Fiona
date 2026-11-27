#!/usr/bin/env python3
"""Run the music and character-collection plugins on one Telegram bot client."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# The merged runtime owns command registration and module loading. Disable the
# music-only menu and remote plugin auto-install path before importing config.
os.environ["SET_CMDS"] = "False"
os.environ["EXTRA_PLUGINS"] = "False"
MUSIC_ROOT = ROOT / "music"
WAIFU_ROOT = ROOT / "waifu"
for package_path in (str(MUSIC_ROOT), str(WAIFU_ROOT)):
    if package_path not in sys.path:
        sys.path.insert(0, package_path)

# These upstream admin modules execute arbitrary code. The merged deployment
# deliberately omits them; owner-only operational controls remain available.
DISABLED_MUSIC_MODULES = {"AoiMusic.plugins.sudo.dev"}
DISABLED_WAIFU_MODULES = {"aoiwaifu.modules.ping", "aoiwaifu.admin.eval"}


def _attach_waifu_to_music_client(music_app, waifu) -> None:
    """Point all Waifu decorators/helpers at the single shared bot client."""
    for name in ("AOI", "ZYRO", "app", "bot"):
        setattr(waifu, name, music_app)


def _install_waifu_modules(waifu) -> int:
    from aoiwaifu.modules import ALL_MODULES as waifu_modules
    from aoiwaifu.admin import ALL_ADMIN_MODULES

    loaded = 0
    for name in waifu_modules:
        module = f"aoiwaifu.modules.{name}"
        if module in DISABLED_WAIFU_MODULES:
            continue
        importlib.import_module(module)
        loaded += 1

    for name in ALL_ADMIN_MODULES:
        module = f"aoiwaifu.admin.{name}"
        if module in DISABLED_WAIFU_MODULES:
            continue
        importlib.import_module(module)
        loaded += 1
    return loaded


def _install_music_modules(module_names: list[str], helpable: dict) -> int:
    loaded = 0
    for module_name in module_names:
        if module_name in DISABLED_MUSIC_MODULES:
            continue
        module = importlib.import_module(module_name)
        if getattr(module, "__MODULE__", None) and getattr(module, "__HELP__", None):
            helpable[module.__MODULE__.lower()] = module
        loaded += 1
    return loaded


async def _start_ptb(application) -> None:
    await application.initialize()
    if application.post_init:
        await application.post_init(application)
    await application.start()


async def _set_unified_menu(app) -> None:
    from pyrogram.types import (
        BotCommand,
        BotCommandScopeAllChatAdministrators,
        BotCommandScopeAllGroupChats,
        BotCommandScopeAllPrivateChats,
        BotCommandScopeChat,
    )
    from unified_commands import ADMIN_COMMANDS, GROUP_COMMANDS, PRIVATE_COMMANDS
    from aoiwaifu import OWNER_ID

    def convert(rows):
        return [BotCommand(command, description) for command, description in rows]

    await app.set_bot_commands(convert(PRIVATE_COMMANDS), scope=BotCommandScopeAllPrivateChats())
    await app.set_bot_commands(convert(GROUP_COMMANDS), scope=BotCommandScopeAllGroupChats())
    await app.set_bot_commands(convert(ADMIN_COMMANDS), scope=BotCommandScopeAllChatAdministrators())
    if OWNER_ID:
        owner_commands = (*PRIVATE_COMMANDS, ("owner", "Open owner tools"))
        await app.set_bot_commands(
            convert(owner_commands), scope=BotCommandScopeChat(chat_id=OWNER_ID)
        )


async def _health_heartbeat(bot_client, assistant_client) -> None:
    """Publish event-loop heartbeats together with Telegram connection health."""
    from AoiMusic.core.keep_alive import beat

    while True:
        beat(
            {
                "telegram_bot": bool(getattr(bot_client, "is_connected", False)),
                "assistant_session": bool(getattr(assistant_client, "is_connected", False)),
            }
        )
        await asyncio.sleep(30)


async def _wait_for_shutdown_signal(logger) -> str:
    """Wait for a host shutdown signal and log which signal initiated teardown."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    received: list[str] = []
    loop_signals = []
    fallback_signals = []

    def request_shutdown(signum: int) -> None:
        if received:
            return
        name = signal.Signals(signum).name
        received.append(name)
        logger.info("Received %s; beginning graceful shutdown.", name)
        shutdown_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_shutdown, signum)
            loop_signals.append(signum)
        except (NotImplementedError, RuntimeError):
            previous = signal.getsignal(signum)

            def fallback_handler(received_signal, _frame):
                loop.call_soon_threadsafe(request_shutdown, received_signal)

            signal.signal(signum, fallback_handler)
            fallback_signals.append((signum, previous))

    if not loop_signals and not fallback_signals:
        raise RuntimeError("Could not register a graceful-shutdown signal handler")

    try:
        await shutdown_event.wait()
        return received[0]
    finally:
        for signum in loop_signals:
            loop.remove_signal_handler(signum)
        for signum, previous in fallback_signals:
            signal.signal(signum, previous)


async def run() -> None:
    # Import the music package first: it owns the one Telegram bot client and
    # voice-call stack. The Waifu package is attached to that client before its
    # command modules are imported, so no second bot-token polling client runs.
    import AoiMusic
    import aoiwaifu
    import config

    from AoiMusic import LOGGER, app, userbot
    from AoiMusic.core.call import AoiCall
    from AoiMusic.plugins import ALL_MODULES as MUSIC_MODULES
    from AoiMusic.utils.database import get_banned_users, get_gbanned
    from AoiMusic.utils.premium import install_text_entities_patch, validate_db
    from AoiMusic.utils.premium_emoji import patch_pyrogram_premium_emoji
    from AoiMusic.core.keep_alive import beat, set_ready, start_server, stop_server
    from aoiwaifu.unit.event_logger import send_event_logs

    if not config.STRING_SESSIONS:
        raise RuntimeError("Music voice playback requires at least one STRING_SESSIONS assistant session.")

    _attach_waifu_to_music_client(app, aoiwaifu)
    install_text_entities_patch()
    patch_pyrogram_premium_emoji()

    # Register all collection/group features on the shared client before start.
    waifu_loaded = _install_waifu_modules(aoiwaifu)

    ptb = aoiwaifu.application
    await _start_ptb(ptb)
    client_started = False
    userbot_started = False
    trim_task = None
    health_server = None
    heartbeat_task = None
    runtime_started_at = time.monotonic()
    service_ready = False
    shutdown_trigger = None

    async def shutdown_step(name, operation, timeout: float = 20) -> None:
        """Keep one cleanup failure from skipping the remaining shutdown steps."""
        try:
            result = operation()
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=timeout)
        except Exception as exc:
            LOGGER("Fiona").warning(
                "Shutdown step '%s' failed (%s).", name, type(exc).__name__
            )

    try:
        health_server = start_server()
        await app.start()
        client_started = True

        try:
            for user_id in await asyncio.wait_for(get_gbanned(), timeout=15):
                config.BANNED_USERS.add(user_id)
            for user_id in await asyncio.wait_for(get_banned_users(), timeout=15):
                config.BANNED_USERS.add(user_id)
        except Exception as exc:
            LOGGER("Fiona").warning("Could not preload bans (%s).", type(exc).__name__)

        try:
            await asyncio.wait_for(validate_db(app), timeout=20)
        except Exception as exc:
            LOGGER("Fiona").warning("Premium emoji validation skipped (%s).", type(exc).__name__)

        music_loaded = _install_music_modules(MUSIC_MODULES, AoiMusic.HELPABLE)
        LOGGER("Fiona").info(
            "Loaded %d music plugins and %d collection/group plugins on one bot client.",
            music_loaded,
            waifu_loaded,
        )

        # Help gets one combined catalogue entry rather than a second /help handler.
        waifu_help = importlib.import_module("AoiMusic.plugins.waifu_help")
        AoiMusic.HELPABLE[waifu_help.__MODULE__.lower()] = waifu_help

        await userbot.start()
        userbot_started = True
        await AoiCall.start()
        beat(
            {
                "telegram_bot": bool(getattr(app, "is_connected", False)),
                "assistant_session": bool(getattr(userbot, "is_connected", False)),
            }
        )
        heartbeat_task = asyncio.create_task(
            _health_heartbeat(app, userbot), name="fiona-health-heartbeat"
        )
        try:
            await _set_unified_menu(app)
        except Exception as exc:
            LOGGER("Fiona").warning("Could not update Telegram command menus (%s).", type(exc).__name__)

        set_ready(True)
        service_ready = True
        LOGGER("Fiona").info("Fiona is online: music, group tools, and character collection share one bot.")
        await send_event_logs(
            app,
            [aoiwaifu.GLOG, config.LOGGER_ID],
            "<b>🟢 Fiona started</b>\n"
            "Music, group management, and Waifu features are online.\n"
            f"<b>Time (UTC):</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
            logger_name="Fiona.Lifecycle",
        )
        shutdown_trigger = await _wait_for_shutdown_signal(LOGGER("Fiona"))
    finally:
        set_ready(False)
        if service_ready:
            uptime = max(0, int(time.monotonic() - runtime_started_at))
            hours, remainder = divmod(uptime, 3600)
            minutes, seconds = divmod(remainder, 60)
            await shutdown_step(
                "lifecycle notification",
                lambda: send_event_logs(
                    app,
                    [aoiwaifu.GLOG, config.LOGGER_ID],
                    "<b>🔴 Fiona stopping</b>\n"
                    f"<b>Uptime:</b> {hours}h {minutes}m {seconds}s\n"
                    f"<b>Shutdown trigger:</b> {shutdown_trigger or 'runtime exit'}\n"
                    f"<b>Time (UTC):</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
                    logger_name="Fiona.Lifecycle",
                ),
                timeout=10,
            )
        if heartbeat_task:
            heartbeat_task.cancel()
            await shutdown_step(
                "health heartbeat",
                lambda: asyncio.gather(heartbeat_task, return_exceptions=True),
                timeout=3,
            )
        await shutdown_step(
            "health HTTP server",
            lambda: asyncio.to_thread(stop_server, health_server),
            timeout=20,
        )
        if trim_task:
            trim_task.cancel()
            await shutdown_step(
                "temporary-file cleanup task",
                lambda: asyncio.gather(trim_task, return_exceptions=True),
                timeout=3,
            )
        await shutdown_step("voice calls", AoiCall.stop, timeout=25)
        if userbot_started:
            await shutdown_step("assistant sessions", userbot.stop, timeout=20)
        if client_started:
            await shutdown_step("Telegram bot client", app.stop, timeout=20)
        if ptb.running:
            await shutdown_step("collection bot application", ptb.stop, timeout=15)
        await shutdown_step("collection bot shutdown", ptb.shutdown, timeout=15)

        for client_name in ("ddw", "backup_ddw"):
            client = getattr(aoiwaifu, client_name, None)
            if client is not None:
                await shutdown_step(
                    f"collection database client {client_name}", client.close, timeout=5
                )
        try:
            from AoiMusic.core import mongo as music_mongo

            for client_name in ("_mongo_async_", "_mongo_sync_"):
                client = getattr(music_mongo, client_name, None)
                if client is not None:
                    await shutdown_step(
                        f"music database client {client_name}", client.close, timeout=5
                    )
        except Exception as exc:
            LOGGER("Fiona").debug(
                "Music database cleanup unavailable (%s).", type(exc).__name__
            )


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Fiona exited with an unhandled error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
