"""Refuses a new tool file and a brief that inserts a reading step.

`TOOL_PATH` matches a new file under a tooling directory, and `READING_STEP`
matches an instruction to read something that is not the issue, the manual or a
skill. `main` returns 2 for either. `COMMISSIONED` names the repository paths an
item asks for and `new_tool` allows them.
"""

import json
import pathlib
import re
import sys

WRITERS = {"Write", "NotebookEdit"}
BRIEFS = {"Agent", "SendMessage"}

TOOL_PATH = re.compile(r"(^|[\\/])(?:tools|scripts|bin|utils)[\\/][^\\/]+\.py$",
                       re.IGNORECASE)

ROOT_MARKER = "pyproject.toml"

COMMISSIONED = frozenset({"tools/capture_screen_figure.py"})

READING_STEP = re.compile(
    r"\b(?:read|consult|review|refer to|open)\b[^.\n]{0,60}"
    r"(?:C:[\\/]|[\\/]Temp[\\/]|scratchpad[\\/]|\.txt\b|notes?\.md\b"
    r"|standard\.md\b|rules\.md\b|brief\.md\b)",
    re.IGNORECASE,
)


def text_of(payload):
    """Returns the text a tool call carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message", "description")]
    return "\n".join(part for part in parts if isinstance(part, str))


def repo_relative(raw):
    """Returns `raw` relative to the nearest folder holding `ROOT_MARKER`."""
    path = pathlib.Path(raw).resolve()
    for parent in path.parents:
        if (parent / ROOT_MARKER).is_file():
            return path.relative_to(parent).as_posix()
    return ""


def new_tool(payload):
    """True when the call creates a file under a tooling directory that
    `COMMISSIONED` does not name."""
    data = payload.get("tool_input") or {}
    raw = data.get("file_path") or data.get("notebook_path") or ""
    if not isinstance(raw, str) or not TOOL_PATH.search(raw):
        return False
    if repo_relative(raw) in COMMISSIONED:
        return False
    return not pathlib.Path(raw).exists()


def main():
    """Reads the tool payload on stdin and refuses a detour."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    name = payload.get("tool_name")
    if name in WRITERS and new_tool(payload):
        sys.stderr.write(
            "Refused: this creates a new tool.\n"
            "The operator, 2026-09-06: actions originate off the issue; no"
            " tools, no detours, no workarounds.\n"
            "Run a program someone else maintains, by its official name. If"
            " none can do it, say what is missing and stop.\n"
        )
        return 2
    if name in BRIEFS:
        hits = READING_STEP.findall(text_of(payload))
        if hits:
            sys.stderr.write(
                "Dispatch refused: it inserts a reading step before the work.\n"
                "A unit reads the issue, the manual page it names, and its"
                " skills. Nothing else.\n"
                "Cite `gh issue view <n>`, a `docs/manual/` page, or"
                " `Skill: <name>`.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
