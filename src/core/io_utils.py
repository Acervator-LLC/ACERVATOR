"""
io_utils.py — durable filesystem helpers
=========================================
Shared low-level I/O primitives used across the platform. Every persistence
path (bot state, capital reservations, telemetry, TA snapshots, stone
tablets, simulator state) routes its writes through these three functions
instead of carrying its own tmp-file-then-rename idiom.

:func:`atomic_write_bytes` is the primitive; :func:`atomic_write_text` and
:func:`atomic_write_json` encode onto it. Staging names come from
``tempfile.mkstemp``, which creates with O_EXCL, so two writers of one
destination cannot collide on a staging path.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = ["atomic_write_bytes", "atomic_write_text", "atomic_write_json"]


def _fsync_directory(directory: Path) -> None:
    """Flush the directory entry so the rename survives a power loss.

    POSIX only. Windows refuses ``os.open`` on a directory; the failure is
    suppressed because the rename itself is already durable there.
    """
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(
    path: os.PathLike | str,
    data: bytes,
    *,
    before_replace: Optional[Callable[[], None]] = None,
) -> Path:
    """Replace ``path`` with ``data``, or leave it exactly as it was.

    Stages through an O_EXCL temp file in the destination's own directory,
    fsyncs it, then moves it onto ``path`` with :func:`os.replace`. A
    concurrent reader therefore never observes a half-written file. Any
    failure removes the temp file and re-raises; the destination is never
    partially written.

    ``before_replace`` runs after the temp file is durable and before the
    rename — the one moment at which both the old and the new contents exist
    on disk. Returns the destination path.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(dest.parent), prefix=f".{dest.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(tmp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_directory(dest.parent)
    return dest


def atomic_write_text(
    path: os.PathLike | str,
    text: str,
    *,
    encoding: str = "utf-8",
    before_replace: Optional[Callable[[], None]] = None,
) -> Path:
    """Encode ``text`` and write it through :func:`atomic_write_bytes`.

    Bytes reach the file unbuffered through the descriptor, so there is no
    newline translation: a newline stays one byte on every platform. Returns
    the destination path.
    """
    return atomic_write_bytes(
        path, text.encode(encoding), before_replace=before_replace
    )


def atomic_write_json(
    path: os.PathLike | str,
    payload: Any,
    *,
    indent: Optional[int] = 2,
    default: Optional[Callable[[Any], Any]] = None,
    sort_keys: bool = False,
    separators: Optional[tuple[str, str]] = None,
    ensure_ascii: bool = True,
    encoding: str = "utf-8",
    before_replace: Optional[Callable[[], None]] = None,
) -> Path:
    """Serialize ``payload`` to JSON and write it through
    :func:`atomic_write_text`.

    The JSON formatting keywords (``indent``, ``default``, ``sort_keys``,
    ``separators``, ``ensure_ascii``) mirror :func:`json.dumps` so each call
    site can preserve its exact on-disk format. ``indent`` defaults to 2
    rather than to ``json.dumps``' ``None``; a site wanting compact output
    states ``indent=None``. Serialization happens before
    the temp file is created: a payload ``json.dumps`` rejects leaves no temp
    file behind and the original ``path`` untouched. Returns the destination
    path.
    """
    text = json.dumps(
        payload,
        indent=indent,
        default=default,
        sort_keys=sort_keys,
        separators=separators,
        ensure_ascii=ensure_ascii,
    )
    return atomic_write_text(
        path, text, encoding=encoding, before_replace=before_replace
    )
