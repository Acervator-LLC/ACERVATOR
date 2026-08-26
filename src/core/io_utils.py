"""
io_utils.py — durable filesystem helpers
=========================================
Shared low-level I/O primitives used across the platform. The one export
here is :func:`atomic_write_json`, the single implementation of the
tmp-file-then-rename idiom that every persistence path (bot state, capital
reservations, telemetry, TA snapshots, stone tablets, simulator state) now
routes through.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional


def atomic_write_json(
    path: os.PathLike | str,
    payload: Any,
    *,
    indent: Optional[int] = 2,
    default: Optional[Callable[[Any], Any]] = None,
    sort_keys: bool = False,
    separators: Optional[tuple[str, str]] = None,
) -> Path:
    """Serialize ``payload`` to JSON and write it to ``path`` atomically.

    The payload is written to a unique temporary file in the destination's
    own directory, flushed and fsync'd, then moved onto ``path`` with
    :func:`os.replace`. A concurrent reader therefore never observes a
    half-written file, and — because the staging file is unique per call —
    two independent writers targeting the same path can never rename one
    another's partial write over the live file. If serialization or the
    write fails, the temporary file is removed and the original ``path`` is
    left untouched.

    The JSON formatting keywords (``indent``, ``default``, ``sort_keys``,
    ``separators``) mirror :func:`json.dumps` so each call site can preserve
    its exact on-disk format. Returns the destination path.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        indent=indent,
        default=default,
        sort_keys=sort_keys,
        separators=separators,
    )
    fd, tmp = tempfile.mkstemp(
        dir=str(dest.parent), prefix=f".{dest.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return dest
