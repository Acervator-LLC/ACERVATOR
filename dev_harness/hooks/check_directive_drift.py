"""Refuses a dispatch brief that contradicts a pinned operator directive.

`LEGACY`, `DELETE_TEXT`, `DROP_FIGURES` and `PARALLEL_PYTEST` each match a brief
that must not be sent. `NO_DELETE_CLAUSE` and `SERIAL_CLAUSE` name wording a
brief must carry. `deny` exits 2, the only signal that blocks a tool call.
"""

import json
import re
import sys

MANUAL_PDF = "Acervator Product Manual 2026~2027.pdf"

LEGACY = re.compile(r"hot mess manual version", re.IGNORECASE)
ORIGINAL_CLAIM = re.compile(
    r"\bthe original(?:\s+manual|\s+version|\s+file)?\b", re.IGNORECASE
)
DELETE_TEXT = re.compile(
    r"\b(?:delete|remove|drop|cut|trim|shorten|reword|rewrite)\b[^.\n]{0,60}"
    r"\b(?:his|the operator'?s?)\s+(?:text|prose|sentence|wording|words)",
    re.IGNORECASE,
)
DROP_FIGURES = re.compile(
    r"\b(?:drop|omit|exclude|skip)\b[^.\n]{0,40}\b(?:figure|image|chart)s?\b",
    re.IGNORECASE,
)
PARALLEL_PYTEST = re.compile(r"pytest[^\n]{0,80}-n\s+(?:auto|[5-9]|\d\d)")

MANUAL_WORK = re.compile(r"docs/manual|FIGURES\.md", re.IGNORECASE)
CODE_WORK = re.compile(r"#319|coding_archetype|sweep|comments? audit", re.IGNORECASE)

NO_DELETE_CLAUSE = re.compile(
    r"(?:\bno\b|\bnever\b|\bnot\b|immutable|untouched)"
    r"[^.]{0,90}?"
    r"(?:sentence|text|prose|wording|words|paragraph)"
    r"[^.]{0,90}?"
    r"(?:deleted|delete|reworded|reword|removed|changed|altered)"
    r"|(?:sentence|text|prose|wording|words|paragraph)"
    r"[^.]{0,90}?"
    r"(?:\bnot\b|\bnever\b|\bno\b)"
    r"[^.]{0,90}?"
    r"(?:deleted|reworded|removed|changed|altered)",
    re.IGNORECASE | re.DOTALL,
)
SERIAL_CLAUSE = re.compile(r"serial", re.IGNORECASE)
ANCHOR_CLAUSE = re.compile(
    r"anchor|base reality|names the (?:module|symbol)", re.IGNORECASE
)
WRITES_PROSE = re.compile(
    r"\b(?:write|describe|document|caption)\b[^.\n]{0,50}"
    r"\b(?:part|section|figure|manual|chronicle|glossary)",
    re.IGNORECASE,
)


def deny(reason: str, fix: str) -> None:
    """Prints the refusal to stderr and exits 2 to block the call."""
    sys.stderr.write("Dispatch refused: %s\n%s\n" % (reason, fix))
    sys.exit(2)


def main() -> int:
    """Reads the hook payload and checks an Agent prompt against the pins."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Agent":
        return 0
    prompt = str(payload.get("tool_input", {}).get("prompt", ""))
    if not prompt:
        return 0

    if LEGACY.search(prompt) and ORIGINAL_CLAIM.search(prompt):
        deny(
            "the brief calls the legacy fourteen-part set 'the original'",
            "The original is %s. The legacy set is superseded." % MANUAL_PDF,
        )
    if DELETE_TEXT.search(prompt):
        deny(
            "the brief permits deleting or rewording the operator's text",
            "ADD and MODIFY only. Prove it with a token multiset and a control.",
        )
    if DROP_FIGURES.search(prompt):
        deny(
            "the brief permits dropping figures",
            "Every figure is carried and described. Absence is anchored, not omitted.",
        )
    if PARALLEL_PYTEST.search(prompt):
        deny(
            "the brief allows a parallel pytest run while the platform is live",
            "Run serially, no -n.",
        )
    if MANUAL_WORK.search(prompt) and not NO_DELETE_CLAUSE.search(prompt):
        deny(
            "a manual brief is missing the no-deletion clause",
            "State: no existing sentence may be deleted or reworded, with a proof.",
        )
    if WRITES_PROSE.search(prompt) and not ANCHOR_CLAUSE.search(prompt):
        deny(
            "a brief that writes manual prose is missing the anchoring clause",
            "State: Simple Technical English, current code is base reality, and"
            " every description names the module and symbol behind it.",
        )
    if CODE_WORK.search(prompt) and not SERIAL_CLAUSE.search(prompt):
        deny(
            "a code brief is missing the serial-pytest clause",
            "State that pytest runs serially while the platform is live.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
