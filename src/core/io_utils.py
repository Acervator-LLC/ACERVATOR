"""io_utils.py — the one durable file write the persisted-state paths share.

Nine call sites carried their own temp-file-then-rename idiom with five
different temp-naming conventions, and not one of them fsynced. A rename
is atomic with respect to the directory entry only; without an fsync of
the temp file first, a power loss can promote a file whose contents are
still in the page cache. ``bot_state.json`` is one of the files that
protects.

Temp names come from ``tempfile.mkstemp``, which creates with O_EXCL, so
two writers of one destination cannot collide on a staging path. The old
convention-based names could: ``StateManager`` and ``bot_visualizer``
both staged ``bot_state.json`` through ``bot_state.tmp``.

Bytes are written unbuffered through the file descriptor, so the result
is identical on every platform. Text-mode writing translates ``\n`` to
``os.linesep``, which produced CRLF JSON on Windows and LF elsewhere from
the same source.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

__all__ = ["atomic_write_bytes", "atomic_write_text", "atomic_write_json"]


def _fsync_directory(directory: Path) -> None:
    """Flush the directory entry so the rename survives a power loss.

    POSIX only. Windows refuses ``os.open`` on a directory; the failure
    is suppressed because the rename itself is already durable there.
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
    path: Path,
    data: bytes,
    *,
    before_replace: Optional[Callable[[], None]] = None,
) -> None:
    """Replace ``path`` with ``data``, or leave it exactly as it was.

    Stages through an O_EXCL temp file in the destination directory,
    fsyncs it, then renames. Any failure removes the temp file and
    re-raises; the destination is never partially written.

    ``before_replace`` runs after the temp file is durable and before the
    rename — the one moment at which both the old and the new contents
    exist on disk.
    """
    directory = Path(path).parent
    fd, tmp_name = tempfile.mkstemp(
        dir=str(directory), prefix=f".{Path(path).name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_directory(directory)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    before_replace: Optional[Callable[[], None]] = None,
) -> None:
    """Encode ``text`` and write it through :func:`atomic_write_bytes`.

    No newline translation: ``\n`` reaches the file as ``\n`` on every
    platform.
    """
    atomic_write_bytes(Path(path), text.encode(encoding), before_replace=before_replace)


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: Optional[int] = None,
    sort_keys: bool = False,
    default: Optional[Callable[[Any], Any]] = None,
    separators: Optional[tuple[str, str]] = None,
    ensure_ascii: bool = True,
    encoding: str = "utf-8",
    before_replace: Optional[Callable[[], None]] = None,
) -> None:
    """Serialise ``payload`` and write it through :func:`atomic_write_bytes`.

    The keyword arguments are ``json.dumps``' own and carry its defaults,
    so a caller states only what it needs. Serialisation happens before
    the temp file is created: a payload ``json.dumps`` rejects leaves no
    temp file behind.
    """
    text = json.dumps(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        default=default,
        separators=separators,
        ensure_ascii=ensure_ascii,
    )
    atomic_write_text(
        Path(path), text, encoding=encoding, before_replace=before_replace
    )
