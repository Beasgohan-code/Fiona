#!/usr/bin/env python3
"""Run the music and character-collection plugins on one Telegram bot client."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
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
    )
    from unified_commands import ADMIN_COMMANDS, GROUP_COMMANDS, PRIVATE_COMMANDS

    def convert(rows):
        return [BotCommand(command, description) for command, description in rows]

    await app.set_bot_commands(convert(PRIVATE_COMMANDS), scope=BotCommandScopeAllPrivateChats())
    await app.set_bot_commands(convert(GROUP_COMMANDS), scope=BotCommandScopeAllGroupChats())
    await app.set_bot_commands(convert(ADMIN_COMMANDS), scope=BotCommandScopeAllChatAdministrators())


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
    from pyrogram import idle

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
    try:
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
        try:
            await _set_unified_menu(app)
        except Exception as exc:
            LOGGER("Fiona").warning("Could not update Telegram command menus (%s).", type(exc).__name__)

        LOGGER("Fiona").info("Fiona is online: music, group tools, and character collection share one bot.")
        await idle()
    finally:
        if trim_task:
            trim_task.cancel()
        if AoiCall.calls:
            await asyncio.gather(*(call.stop() for call in AoiCall.calls), return_exceptions=True)
        if userbot_started:
            await userbot.stop()
        if client_started:
            await app.stop()
        if ptb.running:
            await ptb.stop()
        await ptb.shutdown()
        for client_name in ("ddw", "backup_ddw"):
            client = getattr(aoiwaifu, client_name, None)
            if client is not None:
                client.close()
        try:
            from AoiMusic.core import mongo as music_mongo

            for client_name in ("_mongo_async_", "_mongo_sync_"):
                client = getattr(music_mongo, client_name, None)
                if client is not None:
                    client.close()
        except Exception:
            LOGGER("Fiona").debug("Music database cleanup skipped.", exc_info=True)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Fiona could not start: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
