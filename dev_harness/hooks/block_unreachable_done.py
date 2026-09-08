"""Refuses a build brief whose proof of completion cannot observe the deliverable.

`BUILDS` matches a brief that constructs or converts a surface. `OBSERVABLE`
names the clauses that prove the thing is reached at runtime, and `PARITY_ONLY`
matches a proof that only compares two descriptions. `deny` exits 2 and blocks.
"""

import json
import re
import sys

BUILDS = re.compile(
    r"\b(convert|conversion|port|migrate|mount|render|wire up|wire the|build the"
    r"|implement|replace the (?:qt|widget)|new (?:tab|panel|screen|surface))\b",
    re.IGNORECASE,
)

OBSERVABLE = re.compile(
    r"\b(?:reachab|constructed|is mounted|mounts|actually (?:render|run|draw|load)"
    r"|on screen|the running (?:program|app|application|build)"
    r"|drives the real|driven for real|import closure"
    r"|a user can see|observable outcome|renders? in|displayed)\b",
    re.IGNORECASE,
)

PARITY_ONLY = re.compile(
    r"\b(?:parity test|surface parity|compares? the two|view model matches"
    r"|the two sides agree)\b",
    re.IGNORECASE,
)

EXEMPT = re.compile(
    r"\b(?:audit|measure|survey|inventory|report only|do not change|documentation"
    r" unit|no code change|comment sweep|rank|triage)\b",
    re.IGNORECASE,
)


def deny(reason: str, fix: str) -> None:
    """Prints the refusal to stderr and exits 2 to block the call."""
    sys.stderr.write("Dispatch refused: %s\n%s\n" % (reason, fix))
    sys.exit(2)


def main() -> int:
    """Reads the hook payload and checks an Agent prompt for a reachability proof."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("tool_name") != "Agent":
        return 0
    prompt = str(payload.get("tool_input", {}).get("prompt", ""))
    if not prompt or EXEMPT.search(prompt):
        return 0

    if BUILDS.search(prompt) and not OBSERVABLE.search(prompt):
        deny(
            "a build brief with no proof the deliverable is reached at runtime",
            "State how the unit proves the thing is CONSTRUCTED and REACHED by the"
            " running program, not merely that its tests pass. Measured 2026-09-05:"
            " 70 React modules and 72 passing parity tests shipped while 3 files"
            " rendered anything. A parity test asks whether two descriptions agree;"
            " it never asks whether the screen is on screen.",
        )

    if PARITY_ONLY.search(prompt) and not OBSERVABLE.search(prompt):
        deny(
            "the brief's proof is a comparison, not an observation",
            "A parity or view-model comparison passes with zero of the thing"
            " displayed. Require a runtime check: the object is constructed, the"
            " module is mounted, or the panel appears in the import closure of the"
            " running program.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
