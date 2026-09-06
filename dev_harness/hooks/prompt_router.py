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
import os
from pathlib import Path

with contextlib.suppress(AttributeError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _find_repo() -> Path:
    """Locate the repository root.

    These hooks moved to user level on 2026-08-25 at the CTO's request, so
    ``__file__`` no longer sits inside the repository and the previous
    ``Path(__file__).parent.parent.parent`` resolved to the home directory.

    Order: the project directory Claude Code exports, then a walk up from
    the working directory looking for the harness itself. ``dev_harness``
    is the marker because it is what these hooks actually invoke.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (Path(env) / "dev_harness").is_dir():
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for cand in (here, *here.parents):
        if (cand / "dev_harness").is_dir():
            return cand
    return here


REPO = _find_repo()


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
        "dev_harness.harness.coding_archetype",
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
        "dev_harness.harness.gui_archetype",
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
        "dev_harness.harness.docs_archetype",
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
    """Check that a `dev_harness.harness.<name>_archetype` file exists on disk."""
    rel = Path(*module_path.split(".")).with_suffix(".py")
    return (REPO / rel).is_file()


def _skill_exists(slug: str) -> bool:
    """Check that a `SKILL.md` exists for ``slug``.

    These hooks moved to user level on 2026-08-25 at the CTO's request,
    so the skills left the repository with them. Look in BOTH places:
    the user-level directory the skills now live in, and the repository
    for any project that still carries its own. Checking only the
    repository made every skill report a router defect, which is the
    same silent-miswiring this defect line exists to announce.
    """
    rel = Path(".claude") / "skills" / slug / "SKILL.md"
    home = Path.home() / rel
    if home.is_file():
        return True
    return (REPO / rel).is_file()


def _build_domain_section(
    domain: str, archetype_module: str, skill_slugs: tuple[str, ...],
) -> str:
    """Name the archetype and the skills for one matched domain."""
    lines = [f"[routing] task appears to involve **{domain}**."]
    if _archetype_module_exists(archetype_module):
        lines.append(
            f"  - After the work, run: `python -m {archetype_module} <path>`")
        lines.append(
            "    A `passed=False` archetype report blocks self-reporting done.")
    for slug in skill_slugs:
        if _skill_exists(slug):
            lines.append(f"  - Consult skill: `{slug}`")
        else:
            # A wrong slug used to fail silently, which is how the
            # authorship rule stayed unwired. Say it out loud.
            lines.append(
                f"  - [router defect] skill `{slug}` has no "
                f".claude/skills/{slug}/SKILL.md on disk.")
    return "\n".join(lines)


def _build_cascade_reminder() -> str:
    """Pre-banner checks. Both commands are module invocations."""
    return (
        "[cascade] this prompt mentions release / version / cascade. "
        "Before bumping any banner:\n"
        "  1. `python -m dev_harness.harness.check_release_readiness` must print "
        "[OK] first.\n"
        "  2. `python -m dev_harness.harness.claim_ledger check` must exit 0 "
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
        return "\n".join([
            f"[harness-law] turn {turn}",
            "  The archetype authors code. You referee its findings.",
            ("  Run `python -m dev_harness.harness.coding_archetype <path>` on "
             "every file you touch."),
            "  Report `passed`, never a delta. No archetype run = INVALID.",
            f"  Skill: `{_LAW_SKILL}`",
        ])
    return (
        f"[harness-law] turn {turn} - archetype authors, you referee; report "
        f"`passed`, not a delta; no run = INVALID. Skill: `{_LAW_SKILL}`"
    )


# ---------------------------------------------------------------------------
# OCIR catalogue routing
# ---------------------------------------------------------------------------

_CATALOGUE_RULES = (
    (
        "Counting and searching",
        re.compile(
            r"\b(count|counted|counting|how many|number of|search|grep|scan|"
            r"sweep|list of|files? (?:that|which)|remaining|total)\b", re.I),
        "C15, C25, C26, C30, C33, C45, C56, C82, C83, C87, C89",
    ),
    (
        "A check that cannot fail",
        re.compile(
            r"\b(control|green|passed|no findings|nothing found|zero|clean|"
            r"vacuous|prove|proof|verif\w+|gate)\b", re.I),
        "C1-C6, C17, C18, C22, C23, C29, C38, C47, C51, C52, C57, C84, C85",
    ),
    (
        "The machine you are on",
        re.compile(
            r"\b(host|machine|pixel|render|font|platform|windows|linux|"
            r"parallel|worker|timing|ram|memory|cpu)\b", re.I),
        "C11, C27, C35, C37, C50, C65, C66, C69, C71, C84",
    ),
    (
        "Absence read as a value",
        re.compile(
            r"\b(missing|absent|empty|skipped|did not run|never ran|silent|"
            r"quiet|none|null)\b", re.I),
        "C13, C30, C40, C41, C57, C59",
    ),
    (
        "A number from recall instead of measurement",
        re.compile(
            r"\b(assume|assumed|recall|remember|should be|probably|"
            r"typical|usually|known to)\b", re.I),
        "C48, C67, C86, C88",
    ),
    (
        "The referee's own conduct",
        re.compile(
            r"\b(brief|dispatch|report(?:ing|ed)? to|my own|invented|"
            r"rule I|directive)\b", re.I),
        "C25, C82, C83, C86, C88, C89",
    ),
)


#: Bans the environment's own guidance contradicts. Each row names the
#: guidance that recommends the banned form.
_ENVIRONMENT_CONFLICTS = (
    (
        "heredocs, and `python -`",
        "auto-mode's Bash guidance recommends heredocs for file changes",
        "Write the file with the Write tool, then run `python <path>`. "
        "For a commit message, `git commit -F <path>`.",
    ),
    (
        "`pytest -n auto`",
        "the CI workflow itself runs `-n auto`",
        "Use `-n 4` at most: this machine runs the live trading app.",
    ),
)


def _build_environment_conflicts() -> str:
    """Name each ban the environment's own guidance contradicts."""
    lines = [
        "[ocir] **the environment recommends things this project bans.** "
        "The project wins, every turn, with no exception:",
    ]
    for banned, guidance, instead in _ENVIRONMENT_CONFLICTS:
        lines.append(f"  - {banned} — BANNED, though {guidance}.")
        lines.append(f"    {instead}")
    return "\n".join(lines)


def _build_catalogue_section(title: str, rows: str) -> str:
    """Name one OCIR section and its rows, without quoting them."""
    return "\n".join([
        f"[ocir] this turn touches **{title}**.",
        f"  - Rows to read before trusting a result: {rows}",
        "  - Reach them through the index in `.claude/skills/ocir/SKILL.md`.",
    ])


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

    # Rides every turn: the guidance it contradicts also rides every turn.
    sections: list[str] = [_build_environment_conflicts()]
    for domain, pattern, archetype_module, skill_slugs in _DOMAIN_RULES:
        if pattern.search(prompt):
            sections.append(
                _build_domain_section(domain, archetype_module, skill_slugs))
    if _CASCADE_KEYWORDS.search(prompt):
        sections.append(_build_cascade_reminder())
    for title, pattern, rows in _CATALOGUE_RULES:
        if pattern.search(prompt):
            sections.append(_build_catalogue_section(title, rows))
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
