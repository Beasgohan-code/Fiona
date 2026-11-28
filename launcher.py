#!/usr/bin/env python3
"""Load Fiona's shared settings and launch the single combined bot."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parent
MODES = {
    "merged": (ROOT / "music", [str(ROOT / "merged.py")]),
}


def _read_env_file(path: Path) -> dict[str, str]:
    """Read the simple KEY=VALUE form used by the checked-in env template."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '\"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def _is_configured(value: str | None) -> bool:
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    return bool(cleaned) and not lowered.startswith("your_") and "username:password@cluster" not in lowered


def normalize_environment(mode: str, source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Map the shared environment names expected by both feature packages."""
    if source is None:
        env = _read_env_file(ROOT / ".env")
        env.update(os.environ)
    else:
        env = dict(source)
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")

    # Accept either naming convention in the shared .env file.
    token = next((env.get(key, "").strip() for key in ("BOT_TOKEN", "TOKEN") if _is_configured(env.get(key))), "")
    database = next((env.get(key, "").strip() for key in ("MONGO_DB_URI", "MONGO_URL") if _is_configured(env.get(key))), "")
    env["BOT_TOKEN"] = token
    env["TOKEN"] = token
    env["MONGO_DB_URI"] = database
    env["MONGO_URL"] = database

    return env


def environment_errors(mode: str, env: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    for key in ("API_ID", "API_HASH"):
        if not _is_configured(env.get(key)):
            errors.append(f"{key} is required")
    api_id = (env.get("API_ID") or "").strip()
    if _is_configured(api_id) and (not api_id.isdigit() or int(api_id) <= 0):
        errors.append("API_ID must be a positive integer")
    if not _is_configured(env.get("BOT_TOKEN")):
        errors.append("BOT_TOKEN (or TOKEN) is required")
    if not _is_configured(env.get("MONGO_DB_URI")):
        errors.append("MONGO_DB_URI (or MONGO_URL) is required")
    owner_id = (env.get("OWNER_ID") or "").strip()
    if not owner_id or owner_id == "0":
        errors.append("OWNER_ID is required")
    elif not owner_id.isdigit() or int(owner_id) <= 0:
        errors.append("OWNER_ID must be a positive numeric Telegram user ID")
    session_names = ("STRING_SESSIONS", "STRING_SESSION", "STRING_SESSION1", "STRING_SESSION2", "STRING_SESSION3", "STRING_SESSION4", "STRING_SESSION5")
    has_session = any(_is_configured(env.get(name)) for name in session_names)
    if not has_session:
        errors.append("STRING_SESSIONS is required for voice-chat playback in the merged bot")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the unified Fiona bot (music, moderation, and character collection)."
    )
    parser.parse_args(argv)
    mode = "merged"

    env = normalize_environment(mode)
    errors = environment_errors(mode, env)
    if errors:
        print("Configuration error:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("Copy .env.example to .env and fill in the values for the unified bot.", file=sys.stderr)
        return 2

    component_dir, module_args = MODES[mode]
    if mode == "merged":
        music_path = str(ROOT / "music")
        waifu_path = str(ROOT / "waifu")
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (music_path, waifu_path, existing_path)))
        # The merged runner installs one curated command menu after both plugin
        # registries are loaded, so suppress the upstream music-only menu.
        env["SET_CMDS"] = "False"
    # Use the unified dependency environment when it has been prepared.
    venv_root = ROOT / ".venv-merged"
    venv_python = venv_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(venv_python) if venv_python.is_file() else sys.executable
    print(f"Starting {mode} mode from {component_dir.relative_to(ROOT)} …", flush=True)
    command = [python, *module_args]
    try:
        # Replace the launcher process so Docker/systemd signals reach the bot
        # directly and shutdown is graceful—there is no second bot process.
        os.chdir(component_dir)
        os.execvpe(python, command, env)
    except OSError as exc:
        print(f"Could not start Fiona: {exc}", file=sys.stderr)
        return 127
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
