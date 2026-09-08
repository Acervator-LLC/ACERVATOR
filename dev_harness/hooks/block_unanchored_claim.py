"""Refuses a reply that predicts a result it has not measured.

`PREDICTIVE` matches a claim about work that has not reported yet, and
`ANCHORED` matches the evidence a measured claim carries. `main` returns 2 when
`PREDICTIVE` fires and `ANCHORED` stays below `CAP`.
"""

import json
import pathlib
import re
import sys

CAP = 12

PREDICTIVE = re.compile(
    r"\bwill (?:show|give|be|prove|tell|make|let|confirm|reveal)\b"
    r"|\bshould (?:go up|improve|be faster|drop|rise|reduce|speed)\b"
    r"|\bthat gives you\b|\bthis gives you\b"
    r"|\bonce (?:it|they) lands?\b.{0,40}\byou(?:'ll| will)\b"
    r"|\bexpect(?:ed)? to (?:be|see|show|improve)\b"
    r"|\bis going to (?:show|be|give|prove)\b",
    re.IGNORECASE,
)

ANCHORED = re.compile(
    r"\bmeasured\b|\bexit=?\s*\d|\bpassed=(?:True|False)\b"
    r"|`[^`]*\.(?:py|js|md|json)`|\b[0-9a-f]{7,40}\b|\b\d+ of \d+\b",
    re.IGNORECASE,
)


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
    """Reads the stop payload and refuses an unanchored predictive claim."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    text = last_reply(payload.get("transcript_path", ""))
    if not text:
        return 0
    hits = PREDICTIVE.findall(text)
    if not hits:
        return 0
    if len(ANCHORED.findall(text)) >= CAP:
        return 0
    sys.stderr.write(
        "Reply refused: it predicts a result it has not measured.\n"
        "  phrases: %s\n"
        "A running unit has not reported. What it produces is unknown, and"
        " saying it reads as fact.\n"
        "Report what was measured — a command, a count, an exit code, a file —"
        " or say what was dispatched and stop there.\n" % ", ".join(sorted(set(hits)))
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
