"""Refuses a brief that grounds work in anything but the issues and the manual.

`ALT_SOURCE` matches an authority outside the repository, and `SANCTIONED`
matches the three the operator allows. `main` returns 2 when `ALT_SOURCE`
appears.
"""

import json
import re
import sys

GATED_TOOLS = {"Agent", "SendMessage"}

ALT_SOURCE = re.compile(
    r"UNIT_RULES|DIRECTIVES\.md"
    r"|AppData[\\/]Local[\\/]Temp"
    r"|[\\/]Temp[\\/]claude[\\/][^\s`]*\.md"
    r"|scratchpad[\\/][^\s`]*\.md",
    re.IGNORECASE,
)

SANCTIONED = (
    "gh issue view",
    "docs/manual",
    "Skill:",
)


def text_of(payload):
    """Returns the text a dispatch carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def main():
    """Reads the tool payload on stdin and refuses an alternate authority."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    text = text_of(payload)
    if not text.strip():
        return 0
    hits = ALT_SOURCE.findall(text)
    if not hits:
        return 0
    sys.stderr.write(
        "Dispatch refused: it grounds the work in a source outside the"
        " repository.\n"
        "  found: %s\n"
        "The operator, 2026-09-06: skills get loaded, the harness enforces, and"
        " work grounds to the issues and the Product Manual only.\n"
        "Every durable rule belongs in a skill under dev_harness/skills/, which"
        " the unit loads by name. Every fact about the work belongs in the"
        " issue or the manual.\n"
        "Cite: %s\n" % (", ".join(sorted(set(hits))), ", ".join(SANCTIONED))
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
