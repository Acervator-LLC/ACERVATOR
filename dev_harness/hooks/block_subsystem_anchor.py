"""Refuses a general-scope brief whose subject is one subsystem.

`GENERAL` marks a brief that claims to cover the whole repository, and
`SUBSYSTEM` counts the product-specific words in it. `main` returns 2 when a
general brief leans on a subsystem past `CAP`.
"""

import json
import re
import sys

GATED_TOOLS = {"Agent", "SendMessage"}
CAP = 6

GENERAL = re.compile(
    r"\bproject[- ]wide\b|\bevery file in\b|\bevery code edit\b"
    r"|\bwhole (project|repo\w*)\b|\bacross the (whole )?repo\w*\b"
    r"|\ball code\b|\bgoing forward\b",
    re.IGNORECASE,
)

SUBSYSTEM = re.compile(
    r"\belectron\b|\breact\b|\bqt\b|\bpyside6\b|\bsimulator\b|\bconversion\b"
    r"|\bgui\b|\brenderer\b|\bpanel\b|\btab\b|\bscreen\b|\bwidget\b"
    r"|\bwebengine\w*\b|\bdevtools\b|\bshell\b",
    re.IGNORECASE,
)


def brief_of(payload):
    """Returns the text a dispatch carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def anchored(text):
    """Returns the subsystem words in a general brief that leans on one."""
    if not GENERAL.search(text):
        return []
    return SUBSYSTEM.findall(text)


def main():
    """Reads the tool payload on stdin and refuses a subsystem-anchored brief."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    text = brief_of(payload)
    if not text.strip():
        return 0
    hits = anchored(text)
    if len(hits) <= CAP:
        return 0
    seen = sorted({word.lower() for word in hits})
    sys.stderr.write(
        "Dispatch refused: this brief claims general scope and then leans on"
        " one subsystem %d times.\n"
        "  words: %s\n"
        "The operator has corrected this three times. A capability that applies"
        " to every file is described in terms that fit every file — an"
        " interpreter, a subprocess, a runtime, a module. Name a subsystem only"
        " as one example among others, or not at all.\n"
        "If a name would read oddly for a maths module or a connector, it is"
        " the wrong name.\n" % (len(hits), ", ".join(seen))
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
