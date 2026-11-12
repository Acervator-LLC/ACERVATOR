"""Exits 2 on a gated tool while `STATE_PATH` lists a skill unloaded since the last `SessionStart`.

`SessionStart` writes every `SKILL_DIR` name holding `SKILL.md`, and `PostToolUse` on `Skill` strikes the loaded name.
"""

import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path.home() / ".claude" / "skills"
STATE_PATH = Path.home() / ".claude" / "hooks" / "_state" / "skills_unloaded.json"
REFUSED = 2


def read_state() -> dict:
    """Returns `STATE_PATH` as a mapping of session id to unloaded names."""
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def write_state(state: dict) -> None:
    """Replaces `STATE_PATH` with `state` in one step."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, STATE_PATH)


def all_skills() -> list[str]:
    """Returns every folder name under `SKILL_DIR` that holds `SKILL.md`."""
    return sorted(p.parent.name for p in SKILL_DIR.glob("*/SKILL.md"))


def on_session_start(session: str, source: str) -> int:
    """Marks `all_skills` unloaded for `session` and prints them as context."""
    names = all_skills()
    state = read_state()
    state[session] = names
    write_state(state)
    print(f"Context boundary ({source}). Load all {len(names)} skills with the Skill tool before other work: {', '.join(names)}")
    return 0


def on_skill_loaded(session: str, tool_input: dict) -> int:
    """Strikes the skill in `tool_input` from the unloaded names of `session`."""
    state = read_state()
    held = state.get(session)
    if isinstance(held, list):
        name = str(tool_input.get("skill", "")).rsplit(":", 1)[-1]
        state[session] = [n for n in held if n != name]
        write_state(state)
    return 0


def on_tool(session: str) -> int:
    """Exits 2 while `session` has unloaded names in `STATE_PATH`."""
    held = read_state().get(session)
    if isinstance(held, list) and held:
        print(
            f"Refused: {len(held)} skills are not loaded since the last context boundary. "
            f"Load each with the Skill tool first: {', '.join(held)}",
            file=sys.stderr,
        )
        return REFUSED
    return 0


def main() -> int:
    """Routes the hook record on stdin by its `hook_event_name`."""
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    session = str(payload.get("session_id", ""))
    event = payload.get("hook_event_name")
    if event == "SessionStart":
        return on_session_start(session, str(payload.get("source", "")))
    if event == "PostToolUse":
        return on_skill_loaded(session, payload.get("tool_input") or {})
    return on_tool(session)


if __name__ == "__main__":
    sys.exit(main())
