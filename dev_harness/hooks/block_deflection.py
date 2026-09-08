"""Refuses a reply that hands a technical decision back to the operator.

`decidable` strips fenced blocks and quoted lines so the operator's own words
are never matched, then searches what remains for the phrases that pass a
decision upward. A match is refused with exit 2 naming the three questions that
may reach him.
"""

import json
import pathlib
import re
import sys

FENCE = re.compile(r"```.*?```", re.DOTALL)
QUOTED = re.compile(r"^\s*>.*$", re.MULTILINE)

DEFLECTION = re.compile(
    r"\b(?:"
    r"your call"
    r"|up to you"
    r"|(?:both|that|this|these|they)\s+(?:are|is)\s+yours"
    r"|which (?:one )?do you want"
    r"|let me know (?:if|which|whether|what|how)"
    r"|do you want me to"
    r"|would you like me to"
    r"|should I (?:fix|change|raise|lower|add|remove|repair|use|build|run)"
    r"|shall I "
    r"|confirm before I"
    r"|await(?:ing)? your"
    r"|pending your"
    r"|need(?:s)? (?:you|your) (?:to decide|decision|ruling)"
    r"|leav(?:e|ing) (?:it|this|that|them) to you"
    r"|defer(?:ring)? to you"
    r"|(?:tell|say) me which"
    r")\b",
    re.IGNORECASE,
)


def decidable(text):
    """Returns the reply with fenced blocks and quoted lines removed."""
    stripped = FENCE.sub(" ", text)
    return QUOTED.sub(" ", stripped)


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


def main():
    """Reads the stop payload and refuses a reply that defers a decision."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    text = last_reply(payload.get("transcript_path", ""))
    if not text:
        return 0
    found = DEFLECTION.search(decidable(text))
    if found is None:
        return 0
    sys.stderr.write(
        "Reply refused: \"%s\" hands a decision to the operator.\n"
        "He decides product and spec. Every other decision is yours, and the"
        " ground to decide it exists:\n"
        "  the issue body, the Product Manual page it names, or the published"
        " standard the subject already has\n"
        "Go read one of those three, decide, and report the decision with the"
        " ground it stands on.\n"
        "Only three things reach him: does it work, does it match spec, is it"
        " worth doing.\n"
        % found.group(0)
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
