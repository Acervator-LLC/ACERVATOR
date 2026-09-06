"""Refuses a command that runs the source-shape parity tests.

`CUSTOM` matches a path this repository's own rule forbids, and `WHOLE_SUITE`
matches a run wide enough to include them. `main` returns 2 for either, so the
debugger and the archetypes are used instead.
"""

import json
import re
import sys

GATED_TOOLS = {"Bash", "PowerShell"}

PYTEST = re.compile(r"\bpytest\b", re.IGNORECASE)
CUSTOM = re.compile(r"surface_parity", re.IGNORECASE)
WHOLE_SUITE = re.compile(
    r"pytest\s+(?:-[^\s]+\s+)*tests[\\/]?\s*$"
    r"|pytest\s+(?:-[^\s]+\s+)*$"
    r"|check_release_readiness|tools\.gate\b|tools/gate\.py",
    re.IGNORECASE,
)


def command_of(payload):
    """Returns the command text a tool call carries."""
    data = payload.get("tool_input") or {}
    value = data.get("command")
    return value if isinstance(value, str) else ""


def refusal(command):
    """Names why `CUSTOM` or `WHOLE_SUITE` matched, or returns empty text."""
    if not PYTEST.search(command) and not WHOLE_SUITE.search(command):
        return ""
    if CUSTOM.search(command):
        return "it names a source-shape parity test"
    if WHOLE_SUITE.search(command):
        return "it runs the whole suite, which contains them"
    return ""


def main():
    """Reads the tool payload on stdin and refuses a custom-test run."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    command = command_of(payload)
    if not command.strip():
        return 0
    reason = refusal(command)
    if not reason:
        return 0
    sys.stderr.write(
        "Refused: %s.\n"
        "The operator, 2026-09-06: you will not create, deploy, or use any"
        " custom tests; you will use the debugger to identify and isolate"
        " coding issues.\n"
        "This repository's own rule agrees — a test that reads or"
        " pattern-matches the source of the code under test is the defect.\n"
        "Instead: run the thing under `python -X dev -X faulthandler`, read the"
        " traceback, use pdb or debugpy post-mortem, and run the archetype that"
        " owns the file.\n"
        "A named behavioural test file is still allowed; name it.\n" % reason
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
