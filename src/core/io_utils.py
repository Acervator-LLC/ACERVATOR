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

:func:`append_json_lines` and :func:`read_json_lines` are the append-log pair a
caller uses instead when rewriting the whole file costs too much. An append is
not atomic, so the reader stops at the first line it cannot read whole and
reports the byte offset where the lines it kept end. :func:`read_json_line_before`
reads back one line from a given offset, so a caller holding a saved offset can
check what stands there without reading the file up to it.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

__all__ = [
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
    "append_json_lines",
    "read_json_lines",
    "read_json_line_before",
]

#: How far back :func:`read_json_line_before` looks for the start of one line.
MAX_JSON_LINE_BYTES = 1 << 20


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


def append_json_lines(
    path: os.PathLike | str,
    payloads: Iterable[Any],
    *,
    default: Optional[Callable[[Any], Any]] = None,
) -> int:
    """Append every payload in ``payloads`` to ``path`` as one JSON line each.

    Each line is compact and key-sorted, so the same payload always produces the
    same bytes. Every payload is serialized before the file is opened, so one
    ``json.dumps`` rejects leaves the file untouched. The lines reach disk in one
    write followed by one fsync, so an interrupted call can only cut the tail of
    that write and :func:`read_json_lines` then stops there. The file is opened in
    binary mode, so a newline stays one byte on every platform. Returns the number
    of bytes appended, which is 0 for an empty ``payloads``.
    """
    body = b"".join(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
            default=default,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
        for payload in payloads
    )
    if not body:
        return 0
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "ab") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return len(body)


def read_json_lines(
    path: os.PathLike | str,
    *,
    start: int = 0,
    accept: Optional[Callable[[Any], bool]] = None,
) -> tuple[list[Any], int]:
    """Read ``path`` as JSON lines from byte ``start``, and say where they end.

    A line counts only when it is newline-terminated, ``json.loads`` reads it and
    ``accept`` returns True; reading stops at the first line failing any of those,
    and the returned offset is where a caller truncates.
    """
    try:
        with open(Path(path), "rb") as handle:
            handle.seek(start)
            raw = handle.read()
    except FileNotFoundError:
        return [], start
    payloads: list[Any] = []
    end = start
    for line in raw.split(b"\n")[:-1]:
        try:
            payload = json.loads(line)
        except ValueError:
            break
        if accept is not None and not accept(payload):
            break
        payloads.append(payload)
        end += len(line) + 1
    return payloads, end


def read_json_line_before(path: os.PathLike | str, end: int) -> Optional[Any]:
    """Return the payload of the JSON line that ends at byte ``end`` of ``path``.

    Looks back at most ``MAX_JSON_LINE_BYTES`` for where that line starts, and
    returns ``None`` when ``end`` is not one past a newline, when no line start
    stands inside that window, or when the line does not parse.
    """
    start = max(0, end - MAX_JSON_LINE_BYTES)
    try:
        with open(Path(path), "rb") as handle:
            handle.seek(start)
            window = handle.read(end - start)
    except (OSError, ValueError):
        return None
    if not window.endswith(b"\n"):
        return None
    cut = window.rfind(b"\n", 0, len(window) - 1)
    if cut < 0 and start > 0:
        return None
    try:
        return json.loads(window[cut + 1 : -1])
    except ValueError:
        return None
