"""Refuses the creation of a new test file.

`is_new_test` decides whether the tool call writes a path under a test tree that
does not exist yet. `main` returns 2 for such a call, so the canon is run rather
than extended.
"""

import json
import pathlib
import re
import sys

TEST_PATH = re.compile(r"(^|[\\/])tests?[\\/]", re.IGNORECASE)
HARNESS = re.compile(r"harness_fixtures[\\/]", re.IGNORECASE)
WRITERS = {"Write", "NotebookEdit"}


def is_new_test(payload):
    """True when the call creates a file that does not exist under a test tree."""
    if payload.get("tool_name") not in WRITERS:
        return False
    data = payload.get("tool_input") or {}
    raw = data.get("file_path") or data.get("notebook_path") or ""
    if not isinstance(raw, str) or not raw:
        return False
    if not TEST_PATH.search(raw) or HARNESS.search(raw):
        return False
    return not pathlib.Path(raw).exists()


def main():
    """Reads the tool payload on stdin and refuses a new test file."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not is_new_test(payload):
        return 0
    sys.stderr.write(
        "Refused: this creates a new test file.\n"
        "Tests are canon. You run one, you do not write one.\n"
        "Measured 2026-09-05 to 09-06: 321 commits, 202 of them touching"
        " tests/, 29 new test files, 284 test files modified, 23,151 test"
        " lines added against 14,872 product lines. Fourteen commits touched"
        " desktop/.\n"
        "Run the canonical check that already covers this behaviour, through"
        " the archetype that owns it. If no canon test covers it, report that"
        " as a proposed rule to the operator and stop.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
