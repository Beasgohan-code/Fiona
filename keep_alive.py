"""Backward-compatible import shim for Fiona's Music health module.

The implementation lives in ``AoiMusic.core.keep_alive`` so the combined bot
keeps its operational health code with the Music runtime, while this top-level
name remains available to deployments and older imports.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "music" / "AoiMusic" / "core" / "keep_alive.py"
_SPEC = importlib.util.spec_from_file_location("_fiona_music_keep_alive", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load Fiona health module from {_MODULE_PATH}")
_IMPLEMENTATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_IMPLEMENTATION)

beat = _IMPLEMENTATION.beat
set_ready = _IMPLEMENTATION.set_ready
start_server = _IMPLEMENTATION.start_server
stop_server = _IMPLEMENTATION.stop_server

__all__ = ["beat", "set_ready", "start_server", "stop_server"]
