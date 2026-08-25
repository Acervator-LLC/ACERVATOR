#!/usr/bin/env python3
"""UserPromptSubmit hook — route prompts to archetypes + surface relevant skills.

Purpose
═══════
Whenever the operator submits a prompt, this hook:

1. Reads the prompt from stdin JSON.
2. Emits the authorship law on EVERY turn that carries a prompt.
3. Detects the task domain (coding / gui / docs / other) via keyword
   matching against a curated vocabulary per domain.
4. Emits routing context that:
   - Names the archetype the operator will expect Claude to run before
     reporting the task done.
   - Names the skills Claude should consult.
   - Reminds Claude to log verifiable assertions via the claim ledger
     and to run the pre-cascade check before any banner bump.

WHY THE LAW IS UNCONDITIONAL
════════════════════════════
Quiet-when-neutral used to cover the law too. Measured 2026-08-10:
"proceed", "fix that", "go ahead", "do it" and "continue" all produced
empty output, and those are the turns where a rule stated long ago has
already stopped binding. The law now rides every turn. It is short by
design: a wall of text every turn trains the reader to skip it, which
recreates the failure it is meant to stop. The long form returns on a
fixed turn interval; every other turn gets one line.

Domain routing stays quiet-when-neutral. Only the law is unconditional.

TURN COUNT IS NOT CONTEXT TELEMETRY
═══════════════════════════════════
The interval is driven by a per-session turn count and nothing else.
This hook must never compute or print a token count, a context-fill
percentage, a budget warning or a handoff suggestion. That is a
permanent operator ban, not a preference.

HOOK CONTRACT (Claude Code UserPromptSubmit)
════════════════════════════════════════════
- stdin: JSON {"user_prompt": "..."} (Claude Code may include other fields).
- stdout: text injected as pre-prompt context for the model.
- exit 0: inject stdout into agent context.
- exit non-zero: hook error (skipped, no injection).

Design constraints
═══════════════════
- One small state file, named by `_TURN_STATE`, holding the per-session
  turn count. Nothing else is written.
- Fast. Regex-based classification; targets <50 ms.
- A named skill that does not resolve on disk is announced, not
  swallowed. A silent miss is how a law goes unwired.
- Never emit a "ctx" footer. Operator directive.

Falsification
═════════════
This hook is wrong if:
  (a) A task about coding/gui/docs produces no routing output (recall gap).
  (b) A prompt of any kind produces no harness-law line.
  (c) The named archetype path does not exist on disk.
  (d) A named skill file does not exist on disk and the miss is silent.
  (e) Any output mentions tokens, context fill, a budget or a handoff.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path

with contextlib.suppress(AttributeError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


REPO = Path(__file__).resolve().parent.parent.parent


# The skill that states who may author code. It was never named by any
# hook or by settings.json, so the one mechanism that fires every turn
# never surfaced it. Every domain now carries it.
_LAW_SKILL = "harness-law"

# ---------------------------------------------------------------------------
# Domain keyword taxonomies
#
# Each entry: (domain, compiled_regex, archetype_module_path, skill_slugs)
# The regex is matched with re.IGNORECASE against the user's prompt.
# If multiple domains match, all are surfaced (a "refactor the GUI docs"
# task legitimately spans coding + gui + docs).
# ---------------------------------------------------------------------------

_DOMAIN_RULES: list[tuple[str, re.Pattern[str], str, tuple[str, ...]]] = [
    (
        "coding",
        re.compile(
            r"\b("
            r"refactor|implement|write .* function|"
            r"fix .* bug|patch|hotfix|"
            r"unit ?test|pytest|type[- ]?hint|"
            r"python|\.py\b|"
            r"mypy|ruff|bandit|pyright|vulture|semgrep|"
            r"class |def |from __future__"
            r")\b",
            re.IGNORECASE,
        ),
        "tools.harness.coding_archetype",
        (_LAW_SKILL, "archetype-peer-review"),
    ),
    (
        "gui",
        re.compile(
            r"\b("
            r"gui|widget|window|dialog|tab|panel|button|"
            r"pyside|qt|qwidget|qdialog|qpushbutton|qlineedit|"
            r"accessib(le|ility)|screen ?reader|"
            r"layout|qvbox|qhbox|qgrid|"
            r"signal|slot|connect\("
            r")\b",
            re.IGNORECASE,
        ),
        "tools.harness.gui_archetype",
        (_LAW_SKILL, "archetype-peer-review"),
    ),
    (
        "docs",
        re.compile(
            r"\b("
            r"docs?|documentation|readme|changelog|manual|"
            r"report|audit|writeup|write[- ]?up|"
            r"markdown|\.md\b|"
            r"prose|proselint|vale|diataxis|"
            r"how[- ]?to|tutorial|reference doc"
            r")\b",
            re.IGNORECASE,
        ),
        "tools.harness.docs_archetype",
        (_LAW_SKILL, "archetype-peer-review"),
    ),
]


# Prompts that name any of these are cascade-adjacent and warrant an
# explicit claim-ledger reminder — regardless of domain.
_CASCADE_KEYWORDS = re.compile(
    r"\b("
    r"ship|release|bump|cascade|"
    r"version|banner|changelog|"
    r"cut a build|deploy|publish"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Emit helpers — quiet when nothing to say
# ---------------------------------------------------------------------------


def _archetype_module_exists(module_path: str) -> bool:
    """Check that a `tools.harness.<name>_archetype` file exists on disk."""
    rel = Path(*module_path.split(".")).with_suffix(".py")
    return (REPO / rel).is_file()


def _skill_exists(slug: str) -> bool:
    """Check that a `.claude/skills/<slug>/SKILL.md` exists."""
    return (REPO / ".claude" / "skills" / slug / "SKILL.md").is_file()


def _build_domain_section(
    domain: str,
    archetype_module: str,
    skill_slugs: tuple[str, ...],
) -> str:
    """Name the archetype and the skills for one matched domain."""
    lines = [f"[routing] task appears to involve **{domain}**."]
    if _archetype_module_exists(archetype_module):
        lines.append(f"  - After the work, run: `python -m {archetype_module} <path>`")
        lines.append(
            "    A `passed=False` archetype report blocks self-reporting done."
        )
    for slug in skill_slugs:
        if _skill_exists(slug):
            lines.append(f"  - Consult skill: `{slug}`")
        else:
            # A wrong slug used to fail silently, which is how the
            # authorship rule stayed unwired. Say it out loud.
            lines.append(
                f"  - [router defect] skill `{slug}` has no "
                f".claude/skills/{slug}/SKILL.md on disk."
            )
    return "\n".join(lines)


def _build_cascade_reminder() -> str:
    """Pre-banner checks. Both commands are module invocations."""
    return (
        "[cascade] this prompt mentions release / version / cascade. "
        "Before bumping any banner:\n"
        "  1. `python -m tools.harness.check_release_readiness` must print "
        "[OK] first.\n"
        "  2. `python -m tools.harness.claim_ledger check` must exit 0 "
        "(no open claims)."
    )


# ---------------------------------------------------------------------------
# The authorship law - emitted every turn
# ---------------------------------------------------------------------------

# State file holding one integer per session: how many prompts that
# session has submitted. Nothing else lives here.
_TURN_STATE = REPO / "_logs" / "prompt_router_turns.json"

# The long form returns on this interval. Every other turn gets one line.
_LAW_FULL_EVERY = 10

# Cap on remembered sessions, so the state file cannot grow without end.
_TURN_STATE_MAX_SESSIONS = 20


def _bump_turn(session: str) -> int:
    """Increment and return this session's prompt count.

    A turn count, and only a turn count. The operator permanently banned
    token counts, context-fill percentages, budget warnings and handoff
    suggestions on 2026-05-31. Nothing here computes any of them.
    """
    data: dict = {}
    try:
        raw = json.loads(_TURN_STATE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw
    except (OSError, json.JSONDecodeError):
        data = {}
    try:
        count = int(data.get(session, 0)) + 1
    except (TypeError, ValueError):
        count = 1
    data[session] = count
    if len(data) > _TURN_STATE_MAX_SESSIONS:
        data = dict(list(data.items())[-_TURN_STATE_MAX_SESSIONS:])
    try:
        _TURN_STATE.parent.mkdir(exist_ok=True)
        _TURN_STATE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # the law still ships; only the interval degrades
    return count


def _build_law(turn: int) -> str:
    """Render the authorship rule. Long form on the interval, else one line."""
    if turn == 1 or turn % _LAW_FULL_EVERY == 0:
        return "\n".join(
            [
                f"[harness-law] turn {turn}",
                "  The archetype authors code. You referee its findings.",
                (
                    "  Run `python -m tools.harness.coding_archetype <path>` on "
                    "every file you touch."
                ),
                "  Report `passed`, never a delta. No archetype run = INVALID.",
                f"  Skill: `{_LAW_SKILL}`",
            ]
        )
    return (
        f"[harness-law] turn {turn} - archetype authors, you referee; report "
        f"`passed`, not a delta; no run = INVALID. Skill: `{_LAW_SKILL}`"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _extract_prompt(stdin_text: str) -> str:
    """Extract the user prompt from the hook input, best effort.

    Claude Code sends a JSON blob; we tolerate either a `user_prompt`
    or a `prompt` key, and fall back to raw stdin if parsing fails.
    """
    try:
        data = json.loads(stdin_text)
    except (json.JSONDecodeError, ValueError):
        return stdin_text
    # Measured 2026-08-10: stdin of `null` or `[1,2,3]` raised
    # AttributeError here and exited 1, which drops the injection
    # silently. Treat any non-object as raw text.
    if not isinstance(data, dict):
        return stdin_text
    for key in ("user_prompt", "prompt", "message", "content"):
        v = data.get(key)
        if isinstance(v, str):
            return v
    return stdin_text


def _session_id(stdin_text: str) -> str:
    """Session key for the turn count. Falls back to a single bucket."""
    try:
        data = json.loads(stdin_text)
    except (json.JSONDecodeError, ValueError):
        return "default"
    if not isinstance(data, dict):
        return "default"
    sid = data.get("session_id") or data.get("sessionId")
    return sid if isinstance(sid, str) and sid.strip() else "default"


def main() -> int:
    """Emit the law every turn, plus routing when a domain matches."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0  # hook must never crash Claude Code
    prompt = _extract_prompt(raw)
    if not prompt.strip():
        return 0  # no prompt is not a turn

    # The law rides every turn. Domain routing stays quiet when neutral.
    print(_build_law(_bump_turn(_session_id(raw))))

    sections: list[str] = []
    for domain, pattern, archetype_module, skill_slugs in _DOMAIN_RULES:
        if pattern.search(prompt):
            sections.append(
                _build_domain_section(domain, archetype_module, skill_slugs)
            )
    if _CASCADE_KEYWORDS.search(prompt):
        sections.append(_build_cascade_reminder())
    if not sections:
        return 0

    header = "=" * 72
    print()
    print(header)
    print("prompt_router - routing context (auto-injected)")
    print(header)
    print()
    for s in sections:
        print(s)
        print()
    print(header)
    return 0


if __name__ == "__main__":
    sys.exit(main())
