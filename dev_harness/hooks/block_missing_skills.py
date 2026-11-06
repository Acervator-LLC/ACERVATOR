"""Refuses a unit brief that omits a skill the work requires.

`ALWAYS` names the skills every brief carries, and `WHEN` pairs a subject with
the extra skills it demands. `main` returns 2 naming each one a brief left out.
"""

import json
import os
import re
import sys
from pathlib import Path

GATED_TOOLS = {"Agent"}

COMMISSIONING = re.compile(
    r"##\s*YOUR UNIT\b|##\s*UNIT \d|\bwhat this unit delivers\b"
    r"|\byour boundary\b|\bthe deliverable is\b|\bYou are a unit\b",
    re.IGNORECASE,
)

ALWAYS = (
    "truth-check",
    "no-detours",
    "ground-to-issue-and-manual",
    "simple-technical-english",
    "reachability-first",
    "found-it-own-it",
    "hyper-refocus",
    "anti-claudism",
    "widest-true-reading",
    "descriptive-comments-only",
)

WHEN = (
    (
        re.compile(
            r"\.py\b|\.js\b|\bconvert\b|\bfix\b|\bdebug|\brefactor\b"
            r"|\btraceback\b|\bcrash\b",
            re.IGNORECASE,
        ),
        ("debugging", "variable-naming-precision"),
    ),
    (
        re.compile(r"docs/manual|\bmanual\b|\.md\b|\bissue body\b", re.IGNORECASE),
        ("docs-narrative",),
    ),
    (
        re.compile(r"\bindicator\b|\barithmetic\b|\bformula", re.IGNORECASE),
        ("ta-canon",),
    ),
    (
        re.compile(r"\bHOP\b|\bhandoff\b|ACERVATOR_HOP", re.IGNORECASE),
        ("hop-protocol",),
    ),
)


def text_of(payload):
    """Returns the text a dispatch carries."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def missing(text):
    """Returns every required skill the text does not cite."""
    cited = set(re.findall(r"Skill:\s*([\w-]+)", text))
    subject_text = re.sub(r"Skill:\s*[\w-]+", " ", text)
    need = set(ALWAYS)
    for subject, extra in WHEN:
        if subject.search(subject_text):
            need.update(extra)
    return sorted(need - cited)


def skill_roots(payload):
    """Returns the two folders a skill can live in: the user's and the repo's."""
    cwd = payload.get("cwd") or os.getcwd()
    return (
        Path.home() / ".claude" / "skills",
        Path(cwd) / "dev_harness" / "skills",
    )


def nonexistent(text, roots):
    """Returns every cited skill that has a SKILL.md in neither root."""
    cited = sorted(set(re.findall(r"Skill:\s*([\w-]+)", text)))
    return [
        name for name in cited
        if not any((root / name / "SKILL.md").is_file() for root in roots)
    ]


def main():
    """Reads the tool payload on stdin and refuses an under-skilled brief."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    text = text_of(payload)
    if not COMMISSIONING.search(text):
        return 0
    roots = skill_roots(payload)
    invented = nonexistent(text, roots)
    if invented:
        sys.stderr.write(
            "Dispatch refused: the brief cites skills that do not exist.\n"
            + "".join("  Skill: %s\n" % name for name in invented)
            + "Looked for <name>/SKILL.md under:\n"
            + "".join("  %s\n" % root for root in roots)
            + "A unit told to load a skill that is not there loads nothing and"
            " follows a rule nobody wrote. Name only skills on disk.\n"
        )
        return 2
    absent = missing(text)
    if not absent:
        return 0
    sys.stderr.write(
        "Dispatch refused: the brief omits skills this work requires.\n"
        + "".join("  Skill: %s\n" % name for name in absent)
        + "Measured 2026-09-06: of 29 skills, 6 are dangerous and 4 are stale,"
        " so ALWAYS and WHEN name only the 15 that hold.\n"
        "Add the lines to the brief's skill block. A skill that is not named is"
        " not loaded, and a rule that is not loaded is not followed.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
