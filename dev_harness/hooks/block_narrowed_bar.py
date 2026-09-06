"""Refuses a brief whose acceptance bar drops a term the directive carries.

`PAIRS` names a subject and the term its proof must reach. `missing` collects
every pair a brief raises without meeting, and `main` returns 2 when it finds
one.
"""

import json
import re
import sys

GATED_TOOLS = {"Agent", "SendMessage"}

PAIRS = (
    (
        re.compile(r"\bconvert\w*\b.{0,80}\breact\b", re.IGNORECASE | re.DOTALL),
        re.compile(r"\belectron\b|\bshell\b", re.IGNORECASE),
        "a React conversion brief that never names Electron or the shell",
    ),
    (
        re.compile(r"\bdebugg?\w*\b|\berror stream\b", re.IGNORECASE),
        re.compile(
            r"\bproject[- ]wide\b|\bevery file\b|\bwhole (project|repo\w*)\b"
            r"|\btrading\b|\bexchange\b",
            re.IGNORECASE,
        ),
        "a debugging brief scoped to one area instead of the project",
    ),
    (
        re.compile(r"\brenders?\b|\brendering\b", re.IGNORECASE),
        re.compile(
            r"\bmatch\w*\s+qt\b|\bqt\s+variant\b|ACERVATOR_VARIANT=qt"
            r"|\bboth variants\b",
            re.IGNORECASE,
        ),
        "a rendering brief with no comparison against the Qt screen",
    ),
)


def brief_of(payload):
    """Returns the text a dispatch carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def missing(text):
    """Returns a reason for every pair whose subject appears unmet in the text."""
    found = []
    for subject, required, reason in PAIRS:
        if subject.search(text) and not required.search(text):
            found.append(reason)
    return found


def main():
    """Reads the tool payload on stdin and refuses a narrowed brief."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    text = brief_of(payload)
    if not text.strip():
        return 0
    found = missing(text)
    if not found:
        return 0
    sys.stderr.write(
        "Dispatch refused: the acceptance bar is narrower than the directive.\n"
        + "".join("  - %s\n" % reason for reason in found)
        + "Measured: 46 rows were marked converted while 16 reached the shell,"
        " because the brief accepted a proof the directive did not.\n"
        "Widen the criterion to what he actually asked for, or say in one line"
        " why the wider one is too large and let him decide.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
