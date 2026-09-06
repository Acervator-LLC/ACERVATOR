"""Refuses a search for a fact the conversion table already states.

`DISCOVERY` matches a command that lists or searches the converted screens, and
`READING` matches opening one file the table names. `main` returns 2 when
`DISCOVERY` fires without `READING`.
"""

import json
import re
import sys

GATED_TOOLS = {"Bash", "PowerShell", "Grep", "Glob"}

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


def main():
    """Reads the tool payload on stdin and refuses a table lookup by search."""
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
