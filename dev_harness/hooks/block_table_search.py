"""Refuses a search for a fact the conversion table already states, on issue #128's units only.

`CONVERSION_ITEM` matches a `unit/128-` or `fix-128-` branch or a `u128` or `wt-128`
worktree path in the branch under the payload's `cwd` or in the command text; `DISCOVERY` matches a command that
lists or searches the converted screens, and `READING` matches opening one file the
table names. `main` returns 2 when `CONVERSION_ITEM` and `DISCOVERY` fire without
`READING`.
"""

import json
import re
import sys
from pathlib import Path

GATED_TOOLS = {"Bash", "PowerShell", "Grep", "Glob"}

CONVERSION_ITEM = re.compile(
    r"\b(?:unit|fix)[\\/-]128-|[\\/](?:u128|wt-128)(?:[\\/_-]|\b)", re.IGNORECASE
)

CONVERTED = re.compile(
    r"src[\\/]gui[\\/]web\b|module_manifest|desktop[\\/]renderer\b"
    r"|registerPanel|acervatorPanelHost|_surface\.py",
    re.IGNORECASE,
)

DISCOVERY = re.compile(
    r"\b(?:ls|dir|find|grep|rg|select-string|get-childitem)\b|\*\.js|\*\.py",
    re.IGNORECASE,
)

READING = re.compile(r"\b(?:cat|head|sed -n|type)\b", re.IGNORECASE)


def text_of(payload):
    """Returns the command or pattern a tool call carries."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("command", "pattern", "path", "glob")]
    return " ".join(part for part in parts if isinstance(part, str))


def branch_of(payload):
    """Returns the branch the `HEAD` file names for the git tree holding the payload's
    `cwd`, or an empty string when `cwd` sits in no tree or on a detached `HEAD`."""
    cwd = payload.get("cwd") or ""
    if not cwd:
        return ""
    start = Path(cwd)
    for folder in [start] + list(start.parents):
        marker = folder / ".git"
        if marker.is_dir():
            head = marker / "HEAD"
        elif marker.is_file():
            pointer = marker.read_text(encoding="utf-8", errors="replace").strip()
            if not pointer.startswith("gitdir:"):
                return ""
            head = Path(pointer[len("gitdir:"):].strip()) / "HEAD"
        else:
            continue
        try:
            text = head.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""
        prefix = "ref: refs/heads/"
        return text[len(prefix):] if text.startswith(prefix) else ""
    return ""


def on_conversion_item(payload, text):
    """Returns True when `CONVERSION_ITEM` matches the branch under `cwd` or the text."""
    return bool(CONVERSION_ITEM.search(branch_of(payload)) or CONVERSION_ITEM.search(text))


def main():
    """Reads the tool payload on stdin and refuses a table lookup by search on issue #128."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    name = payload.get("tool_name")
    if name not in GATED_TOOLS:
        return 0
    text = text_of(payload)
    if not text.strip():
        return 0
    if not CONVERTED.search(text):
        return 0
    if not on_conversion_item(payload, text):
        return 0
    if name in {"Grep", "Glob"} or (DISCOVERY.search(text)
                                    and not READING.search(text)):
        sys.stderr.write(
            "Refused: this searches for a fact the conversion table states.\n"
            "Issue #128 and docs/manual/08-tabs.md carry the same 76-row table."
            " Per row it gives the Qt file, the React module, the bridge"
            " method, the manifest entry, whether it registers, whether it"
            " ships, whether it renders, and its scope.\n"
            "Read the row. A search produces a second answer, and when they"
            " disagree nothing says which is right.\n"
            "If the table is wrong, that is a finding — name the cell and what"
            " you observed through the debugger.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
