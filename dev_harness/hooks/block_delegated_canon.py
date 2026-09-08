"""Refuses a Workflow script that spawns an agent to run the canon.

`AGENT_CALL` matches the dispatch a workflow script uses and `argument_text`
reads that call's arguments. `CANON_COMMAND` matches a canon tool named as a
program, `CANON_NAME` needs an unnegated `RUN_VERB` beside it, and `speakable`
drops fenced blocks and quoted lines first.
"""

import json
import re
import sys

GATED_TOOLS = {"Workflow"}

FENCE = re.compile(r"```.*?```", re.DOTALL)
QUOTED = re.compile(r"^\s*>.*$", re.MULTILINE)

AGENT_CALL = re.compile(
    r"\b(?:agent|subagent|spawn_?agent|launch_?agent|dispatch_?agent|task)\s*\(",
    re.IGNORECASE,
)

_TOOLS = (
    "pdb|debugpy|black|flake8|ruff|mypy|pyright|bandit|vulture|semgrep"
    "|vale|proselint"
)

_RUN = r"(?:run|runs|running|re-?run|re-?runs|invoke|execute|drive)"

_ARTICLE = r"(?:the\s+|an?\s+|each\s+|every\s+|both\s+|its\s+|their\s+)*"

# A canon tool named as a program to run. A match needs no other word.
CANON_COMMAND = re.compile(
    r"harness\.\w*archetype"
    r"|\bcheck_release_readiness\b"
    r"|\btools[./]local_ci\b"
    r"|-m\s+(?:[\w.]+\.)?(?:" + _TOOLS + r")\b"
    r"|\b" + _RUN + r"\s+" + _ARTICLE + r"(?:" + _TOOLS + r"|debugger"
    r"|archetypes?|release\s+gate)\b",
    re.IGNORECASE,
)

# A canon tool named by word. A match fires only beside an unnegated RUN_VERB.
CANON_NAME = re.compile(
    r"\b(?:coding|ta|gui|docs|truth|watchdog)[ _-]archetypes?\b",
    re.IGNORECASE,
)

RUN_VERB = re.compile(r"\b" + _RUN + r"\b", re.IGNORECASE)

# A refusal standing in front of a run verb, which then instructs nothing.
NEGATED = re.compile(
    r"\b(?:do\s+not|does\s+not|don'?t|never|no\s+need\s+to|without|avoid)\s+"
    r"(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)

# The window a negation must sit in to disarm the run verb after it.
NEGATION_LOOKBACK = 25

_OPENERS = "'\"`"

# A template slot splicing a value into a name.
PLACEHOLDER = re.compile(r"\$\{[^{}]*\}|\{[A-Za-z0-9_]*\}")

# A concatenation seam: two quoted runs joined by a value.
SEAM = re.compile(r"[\"'`]\s*\+\s*[^+\"'`]*\+\s*[\"'`]")

MESSAGE = (
    "Refused: this Workflow spawns an agent to run the canon.\n"
    "  dispatch: %s\n"
    "  canon run in its arguments: %s\n"
    "The operator, 2026-09-08: update the archetypes to block this type of"
    " incorrect deployment. Two orchestrations were killed the same day, one"
    " spawning four agents each to run an archetype, one spawning five each to"
    " run the debugger.\n"
    "Run the tool here and read its exit code. An agent's report of passed is a"
    " claim, not a verdict; the exit code is the verdict and nobody read it.\n"
    "Spawning an operative to AUTHOR a change stays allowed. Give it the work,"
    " not the canon run.\n"
)


def speakable(text):
    """Returns the instruction text of `text`, fenced and quoted parts dropped."""
    return QUOTED.sub(" ", FENCE.sub(" ", text))


def readings(text):
    """Returns `text` raw, then with `PLACEHOLDER` slots and `SEAM` joins closed."""
    return (text, SEAM.sub("", PLACEHOLDER.sub("", text)))


def collect_strings(value, out):
    """Appends every string reachable inside `value` to the list `out`."""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            collect_strings(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            collect_strings(item, out)


def script_of(payload):
    """Returns every string a Workflow tool call carries, joined by newline."""
    out = []
    collect_strings(payload.get("tool_input") or {}, out)
    return "\n".join(out)


def argument_text(script, open_index):
    """Returns the text between the paren at `open_index` and its match.

    Quoted runs are skipped whole, so a paren inside a string does not close it.
    """
    depth = 0
    index = open_index
    end = len(script)
    while index < end:
        char = script[index]
        if char in _OPENERS:
            index += 1
            while index < end and script[index] != char:
                index += 2 if script[index] == "\\" else 1
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return script[open_index + 1 : index]
        index += 1
    return script[open_index + 1 :]


def instructs_a_run(text):
    """True when `text` carries a `RUN_VERB` that no `NEGATED` phrase disarms."""
    for match in RUN_VERB.finditer(text):
        before = text[max(0, match.start() - NEGATION_LOOKBACK) : match.start()]
        if not NEGATED.search(before):
            return True
    return False


def canon_hit(text):
    """Returns the canon `text` names, empty when it names none.

    A `CANON_NAME` counts only when `instructs_a_run` also holds for `text`.
    """
    for reading in readings(text):
        command = CANON_COMMAND.search(reading)
        if command:
            return command.group(0)
        named = CANON_NAME.search(reading)
        if named and instructs_a_run(reading):
            return named.group(0)
    return ""


def delegated_runs(script):
    """Returns (dispatch, canon run) for each agent call naming a canon run."""
    found = []
    for match in AGENT_CALL.finditer(script):
        hit = canon_hit(speakable(argument_text(script, match.end() - 1)))
        if hit:
            found.append((match.group(0).strip(), hit.strip()))
    return found


def main():
    """Reads the tool payload on stdin and refuses a delegated canon run."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in GATED_TOOLS:
        return 0
    script = script_of(payload)
    if not script.strip():
        return 0
    found = delegated_runs(script)
    if not found:
        return 0
    dispatch = ", ".join(sorted({name for name, _ in found}))
    runs = ", ".join(sorted({run for _, run in found}))
    sys.stderr.write(MESSAGE % (dispatch, runs))
    return 2


if __name__ == "__main__":
    sys.exit(main())
