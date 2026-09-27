"""Refuses a script that posts input at a screen point.

`SCREEN_INPUT` matches the calls that aim at coordinates or at the window under a
point; `SCRIPTS` names the file types checked. `deny` exits 2 and blocks the write.
"""

import json
import re
import sys

WRITERS = {"Write", "Edit", "NotebookEdit"}
SCRIPTS = (".py", ".ps1", ".js", ".ahk", ".bat", ".cmd")

SCREEN_INPUT = re.compile(
    r"(?:\b(?:SetCursorPos|mouse_event|SendInput|WindowFromPoint"
    r"|WindowFromPhysicalPoint|pyautogui|pynput|keyboard\.(?:press|send|write)"
    r"|ClickAtPoint|click_at|SetCursorPosition)\b"
    r"|\[System\.Windows\.Forms\.Cursor\]::Position)"
)


def text_of(payload):
    """Returns the text a write carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    for key in ("content", "new_string", "new_source"):
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""


def path_of(payload):
    """Returns the file path a write targets."""
    data = payload.get("tool_input") or {}
    raw = data.get("file_path") or data.get("notebook_path") or ""
    return raw if isinstance(raw, str) else ""


def deny(reason: str, fix: str) -> None:
    """Prints the refusal to stderr and exits 2 to block the call."""
    sys.stderr.write("Write refused: %s\n%s\n" % (reason, fix))
    sys.exit(2)


def main() -> int:
    """Reads the hook payload and refuses screen-point input in a script."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("tool_name") not in WRITERS:
        return 0
    path = path_of(payload)
    if not path.lower().endswith(SCRIPTS):
        return 0
    if path.replace("\\", "/").endswith("/block_screen_point_input.py"):
        return 0
    hit = SCREEN_INPUT.search(text_of(payload))
    if hit:
        deny(
            "the script posts input at a screen point (%s)" % hit.group(0),
            "This machine runs the operator's live trading window. Three drivers this"
            " session clicked into a window that was not theirs; the last reached his"
            " live window. Drive only an accessibility element or a widget whose"
            " process id is your own, and capture by window handle, never by screen"
            " region.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
