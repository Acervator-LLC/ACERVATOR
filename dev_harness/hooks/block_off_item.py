"""Refuses any dispatch that does not name the locked item.

`load_lock` reads the item the operator has locked work to. `cites_item` decides
whether a brief names it, reading the text `brief_of` pulls from the payload.
`main` returns 2 for a brief that does not, so the dispatch never happens.
"""

import json
import pathlib
import re
import sys

LOCK = pathlib.Path.home() / ".claude" / "item_lock.json"
GATED_TOOLS = {"Agent", "SendMessage"}


def load_lock():
    """Returns the locked item number, or None when no lock is set."""
    try:
        body = json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    item = body.get("item")
    return item if isinstance(item, int) else None


def cites_item(text, item):
    """True when the text names the item as an issue number."""
    pattern = r"(?:#|issue\s+|item\s+)0*%d\b" % item
    return re.search(pattern, text, re.IGNORECASE) is not None


def brief_of(payload):
    """Returns the text a dispatch carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def main():
    """Reads the tool payload on stdin and refuses an off-item dispatch."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    item = load_lock()
    if item is None:
        return 0
    brief = brief_of(payload)
    if not brief.strip():
        return 0
    if cites_item(brief, item):
        return 0
    sys.stderr.write(
        "Dispatch refused: work is locked to issue #%d and this brief does not"
        " name it.\n"
        "The operator locked the queue. A brief that does not carry #%d is not"
        " the assigned work, however true it is.\n"
        "Name the item and the file it changes, or do not dispatch.\n"
        "The lock lives at %s.\n" % (item, item, LOCK)
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
