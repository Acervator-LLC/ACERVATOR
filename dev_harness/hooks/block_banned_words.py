"""Refuses the vocabulary the operator banned, in a reply or in a brief.

`block_coined_instrument` refuses only such a thing being MADE, so the words
still reached him inside ordinary prose. `BANNED` refuses them outright in what
he reads and in what a unit is told, after `speakable` drops fenced blocks,
quoted lines and the allowed dependency wording.
"""

import json
import pathlib
import re
import sys

GATED_TOOLS = {"Agent", "SendMessage"}

FENCE = re.compile(r"```.*?```", re.DOTALL)
QUOTED = re.compile(r"^\s*>.*$", re.MULTILINE)
ALLOWED = re.compile(
    r"\bpin(?:s|ned|ning)?\s+(?:an?\s+|the\s+|every\s+)?(?:exact\s+)?"
    r"(?:dependenc|version|commit|sha|requirement)\w*"
    r"|\bpin(?:s|ned|ning)?\s+(?:to|at)\s+(?:an?\s+|the\s+)?(?:exact\s+)?\w+",
    re.IGNORECASE,
)

BANNED = re.compile(
    r"\b(?:probes?|probed|probing"
    r"|pins?|pinned|pinning"
    r"|collectors?|checkers?|verifiers?"
    r"|canar(?:y|ies)|sentinels?"
    r"|rigs?|scaffolds?|scaffolding)\b",
    re.IGNORECASE,
)


def speakable(text):
    """Returns the prose that carries the words, quotes and code removed."""
    stripped = FENCE.sub(" ", text)
    stripped = QUOTED.sub(" ", stripped)
    return ALLOWED.sub(" ", stripped)


def text_of(payload):
    """Returns the prose a gated tool call carries."""
    data = payload.get("tool_input") or {}
    keys = ("prompt", "message", "description", "summary")
    parts = [data.get(key) or "" for key in keys]
    return "\n".join(part for part in parts if isinstance(part, str))


def last_reply(path):
    """Returns the assistant's final text block from the transcript."""
    try:
        lines = pathlib.Path(path).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
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


def refuse(word):
    """Returns the blocking exit code, having named the refused word."""
    sys.stderr.write(
        "Refused: \"%s\" is vocabulary the operator has banned.\n"
        "2026-09-07, verbatim: \"You are not even allowed to speak these"
        " terms. Forget them.\"\n"
        "Verification here is the debugger and the archetypes, nothing"
        " else:\n"
        "  reproduce -> diagnose -> fix -> verify -> document\n"
        "  debugpy, pdb, and a debug report under tests/debug_reports/\n"
        "Say what you ran and what it returned. A reading taken with the"
        " debugger needs no name of its own.\n"
        % word
    )
    return 2


def main():
    """Refuses the banned words in a gated brief or in the final reply."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    name = payload.get("tool_name")
    if name in GATED_TOOLS:
        found = BANNED.search(speakable(text_of(payload)))
        return refuse(found.group(0)) if found else 0
    if name is not None or payload.get("stop_hook_active"):
        return 0
    text = last_reply(payload.get("transcript_path", ""))
    if not text:
        return 0
    found = BANNED.search(speakable(text))
    return refuse(found.group(0)) if found else 0


if __name__ == "__main__":
    sys.exit(main())
