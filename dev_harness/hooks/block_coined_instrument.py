"""Refuses work that creates an instrument this project did not import.

`COINED` names the words used for something written here and dressed as
standard, and `OFFICIAL` names the tools that are actually imported. `main`
returns 2 when `COINED` appears as a thing being made.
"""

import json
import re
import sys

GATED_TOOLS = {"Agent", "SendMessage", "Write", "NotebookEdit"}

COINED = re.compile(
    r"\b(?:probes?|pins?|pinning|collectors?|checkers?|verifiers?"
    r"|instruments?|canar(?:y|ies)|sentinels?|harness rigs?|rigs?"
    r"|shims?|drivers?|scaffolds?|scaffolding|frameworks?"
    r"|parity harness|test harness|custom checks?|bespoke checks?)\b",
    re.IGNORECASE,
)

MAKING = re.compile(
    r"\b(?:build|create|write|add|author|implement|design|make|produce"
    r"|introduce|stand up|set up|assemble|outline|sketch)\b",
    re.IGNORECASE,
)

OFFICIAL = re.compile(
    r"\bdebugpy\b|\bpdb\b|\bruff\b|\bmypy\b|\bpyright\b|\bbandit\b"
    r"|\bvulture\b|\bsemgrep\b|\bblack\b|\bflake8\b|\bvale\b|\bproselint\b",
    re.IGNORECASE,
)


def text_of(payload):
    """Returns the text a tool call carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    keys = ("prompt", "message", "description", "content", "file_path")
    parts = [data.get(key) or "" for key in keys]
    return "\n".join(part for part in parts if isinstance(part, str))


def coined_makings(text):
    """Returns the coined words that appear within reach of a making verb."""
    found = []
    for match in COINED.finditer(text):
        window = text[max(0, match.start() - 120):match.end() + 120]
        if MAKING.search(window):
            found.append(match.group(0).lower())
    return found


def main():
    """Reads the tool payload on stdin and refuses a coined instrument."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    text = text_of(payload)
    if not text.strip():
        return 0
    found = coined_makings(text)
    if not found:
        return 0
    sys.stderr.write(
        "Refused: this makes an instrument that was not imported.\n"
        "  words: %s\n"
        "The operator, 2026-09-06: no probes, no pins, no custom checks, and no"
        " renaming them to get past this.\n"
        "Run a tool that someone else maintains, by its official name:"
        " debugpy, pdb, ruff, mypy, pyright, bandit, vulture, semgrep, black,"
        " flake8, vale, proselint.\n"
        "If none of them can answer the question, say so and stop — that is a"
        " proposed rule for him, not a thing to build.\n"
        % ", ".join(sorted(set(found)))
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
