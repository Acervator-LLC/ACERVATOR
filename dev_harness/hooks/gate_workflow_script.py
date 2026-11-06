"""Runs `BRIEF_HOOKS` over a Workflow script as an Agent brief, and passes a refusal through.

`script_text` reads the inline `script` or the file `scriptPath` names, and `main` exits 2 when no script text can be read.
"""

import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
BRIEF_HOOKS = (
    "check_directive_drift.py",
    "block_uncanonized_workflow.py",
    "block_unreachable_done.py",
    "block_off_item.py",
    "block_narrowed_bar.py",
    "block_subsystem_anchor.py",
    "block_coined_instrument.py",
    "block_alt_grounding.py",
    "block_detour.py",
    "block_missing_skills.py",
    "block_stand_in_without_source.py",
    "block_conversion_table_grounding.py",
)
REFUSED = 2
HOOK_FAULTS = (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError)


def script_text(tool_input: dict) -> str:
    """Returns the Workflow script text from `tool_input`, or the empty string."""
    inline = tool_input.get("script")
    if isinstance(inline, str) and inline.strip():
        return inline
    named = tool_input.get("scriptPath")
    if isinstance(named, str) and Path(named).is_file():
        return Path(named).read_text(encoding="utf-8", errors="replace")
    return ""


def run_hook(name: str, record: str) -> tuple[int, str]:
    """Returns the exit code and stderr of hook `name` given `record` on stdin."""
    stderr = io.StringIO()
    stdin = sys.stdin
    sys.stdin = io.TextIOWrapper(io.BytesIO(record.encode("utf-8")), encoding="utf-8")
    code = 0
    try:
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(HOOK_DIR / name), run_name="__main__")
    except SystemExit as stop:
        if stop.code is not None:
            code = stop.code if isinstance(stop.code, int) else 1
    except HOOK_FAULTS as fault:
        return REFUSED, f"{name} did not finish: {fault}"
    finally:
        sys.stdin = stdin
    return code, stderr.getvalue()


def main() -> int:
    """Exits 2 with the first refusal any of `BRIEF_HOOKS` gives the script."""
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    tool_input = payload.get("tool_input") or {}
    text = script_text(tool_input)
    if not text:
        print("Workflow refused: gate_workflow_script read no script text to grade.", file=sys.stderr)
        return REFUSED
    brief = dict(payload, tool_name="Agent", tool_input={"prompt": text, "description": "workflow script"})
    record = json.dumps(brief)
    for name in BRIEF_HOOKS:
        code, stderr = run_hook(name, record)
        if code != 0:
            print(f"Workflow refused by {name}: {stderr.strip()[:900]}", file=sys.stderr)
            return REFUSED
    return 0


if __name__ == "__main__":
    sys.exit(main())
