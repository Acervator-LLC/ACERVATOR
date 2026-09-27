"""Refuses a dispatch whose brief skips a canonized workflow step.

`W5H` names the six questions, `OCIR` names the reading that must be shown to
fail, `GATE` names the command a merge is gated on, and `CONVERSION` names the
five counts a screen conversion reports. `missing` collects every rule a
commissioning brief breaks, and `main` returns 2 when it finds one.
"""

import json
import re
import sys

GATED_TOOLS = {"Agent"}

#: A brief that commissions work. Anything else is a question and passes.
COMMISSIONING = re.compile(
    r"##\s*What this unit delivers\b|\bwhat this unit delivers\b"
    r"|\byou (?:will )?build\b|\bthe deliverable is\b|##\s*YOUR UNIT\b",
    re.IGNORECASE,
)

W5H = (
    re.compile(r"\bwho\b", re.IGNORECASE),
    re.compile(r"\bwhat\b", re.IGNORECASE),
    re.compile(r"\bwhere\b", re.IGNORECASE),
    re.compile(r"\bwhen\b", re.IGNORECASE),
    re.compile(r"\bwhy\b", re.IGNORECASE),
    re.compile(r"\bhow\b", re.IGNORECASE),
)

#: A reading nobody has watched fail is not a reading.
OCIR = re.compile(
    r"\bcan fail\b|\bcould fail\b|\bblinded?\b|\bknown_bad\b|\bplanted\b"
    r"|\bpositive control\b|\bcalibrat\w+\b|\bfalsif\w+\b",
    re.IGNORECASE,
)

#: The merge gate, by its command.
GATE = re.compile(r"tools\.local_ci|tools/local_ci", re.IGNORECASE)

#: A brief that writes a host for the second build variant.
CONVERSION_SUBJECT = re.compile(
    r"\bhost\b.{0,120}\bvariant\b|\bvariant\b.{0,120}\bhost\b"
    r"|\bconvert\w*\b.{0,120}\bscreen\b|\bregister\(",
    re.IGNORECASE | re.DOTALL,
)
CONVERSION_STEPS = re.compile(r"Skill:\s*screen-conversion", re.IGNORECASE)

#: Every brief names the skills it loads, bare, so the loader can read them.
SKILL_LINE = re.compile(r"Skill:\s*[\w-]+")


def brief_of(payload):
    """Returns the text a dispatch carries."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def missing(text):
    """Returns a reason for every canonized step the brief omits."""
    if not COMMISSIONING.search(text):
        return []
    found = []
    absent = [n for n, rule in zip("who what where when why how".split(), W5H)
              if not rule.search(text)]
    if absent:
        found.append("the six questions, missing: " + ", ".join(absent))
    if not OCIR.search(text):
        found.append(
            "no reading shown to fail: name the blinded run, the planted "
            "control or the calibration"
        )
    if not GATE.search(text):
        found.append("the merge gate is not named: python -m tools.local_ci --all")
    if not SKILL_LINE.search(text):
        found.append("no skill block: write `Skill: name` bare, one per line")
    if CONVERSION_SUBJECT.search(text) and not CONVERSION_STEPS.search(text):
        found.append("a conversion brief that does not load Skill: screen-conversion")
    return found


def main():
    """Reads the tool payload on stdin and refuses an uncanonized brief."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    text = brief_of(payload)
    if not text.strip():
        return 0
    reasons = missing(text)
    if not reasons:
        return 0
    sys.stderr.write(
        "Dispatch refused: the brief skips a canonized workflow step.\n"
        + "".join("  - %s\n" % reason for reason in reasons)
        + "Measured 2026-09-13: four screens shipped drawing nothing because a "
        "brief asked for the parts a picture shows. W5H names what to answer, "
        "OCIR names what proves the answer, the gate names what a merge waits "
        "on.\nAdd the step. A workflow that is not written into the brief is "
        "not followed.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
