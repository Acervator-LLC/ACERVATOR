"""Refuses a brief that grounds a unit to the closed conversion table.

`TABLE` matches the table's names in an Agent or SendMessage payload; `main` returns 2
on a match and 0 otherwise.
"""

import json
import re
import sys

GATED_TOOLS = {"Agent", "SendMessage"}

TABLE = re.compile(
    r"conversion[ _-]table|conversion rows|the conversion table's|conversion_scope"
    r"|conversion_state|parity_pins",
    re.IGNORECASE,
)


def text_of(payload):
    """Returns the prompt or message a tool call carries."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message")]
    return " ".join(part for part in parts if isinstance(part, str))


def main():
    """Reads the tool payload on stdin and refuses a brief that names `TABLE`."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    hit = TABLE.search(text_of(payload))
    if not hit:
        return 0
    sys.stderr.write(
        "Refused: the brief grounds to the conversion table (%r).\n"
        "Issue #128 is closed; its table is not a grounding point for any live"
        " issue. Ground to the unit's own issue and the manual page it names"
        " (operator, 2026-09-20).\n" % hit.group(0)
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
