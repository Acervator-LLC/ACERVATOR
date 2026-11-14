"""`rows_from_end` reads a session transcript backwards in `BLOCK_BYTES` blocks,
and `last_reply` stops at the newest reply.
"""

import json
import os
import pathlib
from collections.abc import Iterator
from typing import IO, Any

BLOCK_BYTES = 65536


def lines_from_end(handle: IO[bytes]) -> Iterator[bytes]:
    """Yield each newline-separated line of `handle`, last line first, reading
    `BLOCK_BYTES` at a time."""
    end = handle.seek(0, os.SEEK_END)
    pieces: list[bytes] = []
    while end > 0:
        start = max(0, end - BLOCK_BYTES)
        handle.seek(start)
        block = handle.read(end - start)
        end = start
        stop = len(block)
        cut = block.rfind(b"\n", 0, stop)
        while cut != -1:
            pieces.append(block[cut + 1 : stop])
            yield b"".join(reversed(pieces))
            pieces = []
            stop = cut
            cut = block.rfind(b"\n", 0, stop)
        pieces.append(block[:stop])
    yield b"".join(reversed(pieces))


def rows_from_end(path: str) -> Iterator[Any]:
    """Yield each line of the transcript at `path` that `json.loads` parses,
    last first; an unreadable `path` yields nothing."""
    try:
        with pathlib.Path(path).open("rb") as handle:
            for line in lines_from_end(handle):
                try:
                    row = json.loads(line.decode("utf-8", errors="replace"))
                except ValueError:
                    continue
                yield row
    except OSError:
        return


def last_reply(path: str) -> str:
    """Return the text blocks of the newest `assistant` row in `path` that
    holds text, or empty text."""
    for row in rows_from_end(path):
        if row.get("type") != "assistant":
            continue
        content = (row.get("message") or {}).get("content") or []
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(part for part in parts if part).strip()
        if text:
            return text
    return ""
