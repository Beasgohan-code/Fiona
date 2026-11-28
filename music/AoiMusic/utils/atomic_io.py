"""Crash-safe local file helpers.

Fiona persists a little state on disk (command/audio/video settings, the bot
session string, cached media). A torn ``open(path, "w")`` + ``json.dump`` can
leave a truncated file behind; for modules that read these files at import
time that used to mean the bot could not start until someone deleted the file
by hand. These helpers write to a temporary sibling and ``os.replace`` into
place, so a reader always sees either the old file or the new one, never a
partial write.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".part"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        return target
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(
    path: str | Path, payload: Any, *, indent: int | None = None
) -> Path:
    return atomic_write_text(path, json.dumps(payload, indent=indent))


def load_json(path: str | Path, default: Any, *, logger: Any = None) -> Any:
    """Load ``path`` as JSON, returning ``default`` if it is missing or corrupt.

    Used at import time, so a damaged file must never propagate an exception —
    the caller gets the default and a log line instead of a dead bot.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except Exception:
        if logger is not None:
            logger.warning("Could not parse %s; falling back to default", path, exc_info=True)
        return default
