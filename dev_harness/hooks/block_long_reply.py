"""Refuses a reply that is longer than the operator's per-file report format.

`last_reply` reads the assistant's final text from the transcript, and `words`
counts it. While `item_lock.json` names an open item, a reply over `CAP` words
that carries no six-step block is refused with exit 2.
"""

import json
import pathlib
import re
import sys

from transcript_tail import last_reply, rows_from_end

LOCK = pathlib.Path.home() / ".claude" / "item_lock.json"
CAP = 40
STEPS = re.compile(
    r"converted\s*[·|]\s*tested|^\s*none\s*$", re.IGNORECASE | re.MULTILINE
)
BANNED = re.compile(
    r"^\s{0,3}(#{1,6}\s|\|\s*\w[^|\n]*\|)", re.MULTILINE
)


def locked():
    """True when the operator has locked work to one item."""
    try:
        body = json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(body.get("item"), int)


ASKED = re.compile(
    r"progress report|status report|give me (a|my|the)|report right|where are we"
    r"|how many|what is left|what's left|explain|why ",
    re.IGNORECASE,
)


def user_asked(path):
    """True when the operator's last message requests a report."""
    for row in rows_from_end(path):
        if row.get("type") != "user":
            continue
        content = (row.get("message") or {}).get("content")
        text = content if isinstance(content, str) else json.dumps(content)
        return ASKED.search(text) is not None
    return False


def main():
    """Reads the stop payload and refuses an over-long reply."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("stop_hook_active") or not locked():
        return 0
    path = payload.get("transcript_path", "")
    if user_asked(path):
        return 0
    text = last_reply(path)
    if not text:
        return 0
    if STEPS.search(text):
        return 0
    count = len(text.split())
    if count <= CAP and not BANNED.search(text):
        return 0
    sys.stderr.write(
        "Reply refused: %d words, and the operator's format is one block per"
        " file, under %d.\n"
        "Send exactly this, one block per file finished:\n"
        "  <path>\n"
        "  converted | tested | verified | tables updated | manual updated"
        " | merged\n"
        "If no file finished, send: none\n"
        "No headings, no tables, no counts, no SHAs, no explanation.\n"
        % (count, CAP)
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
