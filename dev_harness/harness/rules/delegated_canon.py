"""delegated_canon.py — a canon run handed to a spawned agent.

`SPAWN_TOKENS` holds the callee words that dispatch an agent, and `CANON_RUN`
matches a canon tool named as a program to run. `scan` reports DC001 for such a
dispatch and DC002 for a `PROCESS_SPAWNERS` call whose argv carries both.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FALSIFICATION = (
    "This rule module is wrong if: (a) it fires on a file that calls a canon "
    "tool directly, including tools/local_ci.py, an archetype module, and "
    "dev_harness/touchset.py, which submits run_archetype to a thread pool; "
    "(b) it fires on a file that only imports or names an archetype; (c) it "
    "stays quiet on a call whose callee carries an agent token and whose "
    "arguments carry a canon command string; (d) callee_tokens splits MAGENTA "
    "or User-Agent into a token equal to agent. Known gap: CANON_RUN reads "
    "string literals, so a prompt assembled in a variable and passed by name "
    "is not visible here."
)


@dataclass
class Finding:
    """One delegated-canon result, shaped like every other rule module's."""

    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


#: Callee words naming an agent dispatch, matched per identifier token.
SPAWN_TOKENS = frozenset({"agent", "agents", "subagent", "subagents", "task", "tasks"})

#: Dotted callee tails that start a process. `Popen` is also accepted bare.
PROCESS_SPAWNERS = frozenset(
    {
        "run",
        "popen",
        "call",
        "check_call",
        "check_output",
        "system",
        "create_subprocess_exec",
        "create_subprocess_shell",
    }
)

#: Modules whose call in PROCESS_SPAWNERS starts a process.
SPAWNER_ROOTS = frozenset({"subprocess", "os", "asyncio"})

_TOOLS = (
    "pdb",
    "debugpy",
    "black",
    "flake8",
    "ruff",
    "mypy",
    "pyright",
    "bandit",
    "vulture",
    "semgrep",
    "vale",
    "proselint",
)

_TOOL_ALT = "|".join(_TOOLS)

#: A canon tool named as a program to run, never as a bare word.
CANON_RUN = re.compile(
    r"dev_harness\.harness\.\w*archetype"
    r"|\bcheck_release_readiness\b"
    r"|\btools[./]local_ci\b"
    r"|-m\s+(?:[\w.]+\.)?(?:" + _TOOL_ALT + r")\b"
    r"|\b(?:coding|ta|gui|docs|truth|watchdog)[ _-]archetypes?\b"
    r"|\b(?:run|runs|running|invoke|execute|drive)\s+"
    r"(?:the\s+|an?\s+|each\s+|every\s+|its\s+|their\s+)*"
    r"(?:" + _TOOL_ALT + r"|debugger|archetypes?|canon|release gate)\b",
    re.IGNORECASE,
)

_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def callee_tokens(name: str) -> set[str]:
    """Return the lower-case identifier words of `name`.

    `MAGENTA` yields `{'magenta'}` and `spawnAgent` yields `{'spawn', 'agent'}`.
    """
    words: set[str] = set()
    for part in name.replace("-", "_").split("_"):
        words.update(w.lower() for w in _CAMEL.findall(part))
    return words


def dotted_name(node: ast.AST) -> str:
    """Return the dotted source name of a call target, empty when it has none."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def call_strings(call: ast.Call) -> list[str]:
    """Return every string literal inside `call`, f-string parts concatenated."""
    out: list[str] = []
    for node in ast.walk(call):
        if isinstance(node, ast.JoinedStr):
            joined = "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if joined:
                out.append(joined)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def canon_hits(texts: list[str]) -> list[str]:
    """Return the `CANON_RUN` match of each text of `texts` naming a canon run."""
    return [m.group(0) for text in texts for m in [CANON_RUN.search(text)] if m]


def is_agent_dispatch(name: str) -> bool:
    """True when the dotted callee `name` carries a `SPAWN_TOKENS` word."""
    return bool(callee_tokens(name.rsplit(".", 1)[-1]) & SPAWN_TOKENS)


def is_process_spawn(name: str) -> bool:
    """True when the dotted callee `name` starts a separate process."""
    parts = name.split(".")
    tail = parts[-1].lower()
    if tail == "popen":
        return True
    rooted = len(parts) > 1 and parts[0] in SPAWNER_ROOTS
    if tail.startswith("spawn"):
        return rooted
    return tail in PROCESS_SPAWNERS and rooted


def names_an_agent(texts: list[str]) -> bool:
    """True when a word of `texts` carries a `SPAWN_TOKENS` token."""
    return any(
        callee_tokens(word) & SPAWN_TOKENS
        for text in texts
        for word in _WORD.findall(text)
    )


def _finding(target: Path, node: ast.Call, rule_id: str, message: str) -> Finding:
    """Return one `Finding` for `node` at `target`, severity high."""
    return Finding(
        tool="delegated_canon",
        severity="high",
        file=str(target),
        line=node.lineno,
        rule_id=rule_id,
        message=message,
    )


def scan(target: Path, source: str) -> list[Any]:
    """Return every DC001 and DC002 finding for `source`, empty on a non-`.py`."""
    if target.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError:
        return []
    findings: list[Any] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if not name:
            continue
        texts = call_strings(node)
        hits = canon_hits(texts)
        if not hits:
            continue
        quoted = ", ".join(sorted({hit.strip() for hit in hits}))
        if is_agent_dispatch(name):
            findings.append(
                _finding(
                    target,
                    node,
                    "DC001",
                    f"{name}(...) dispatches an agent and its arguments name a "
                    f"canon run ({quoted}). Call the tool in this file and read "
                    f"the exit code it returns. A spawned agent reporting on a "
                    f"run nobody read is not a result.",
                )
            )
        elif is_process_spawn(name) and names_an_agent(texts):
            findings.append(
                _finding(
                    target,
                    node,
                    "DC002",
                    f"{name}(...) starts an agent process and its argv names a "
                    f"canon run ({quoted}). Call the tool directly, as "
                    f"tools/local_ci.py calls black and flake8, and read the "
                    f"exit code the call returns.",
                )
            )
    return findings


__all__ = ["FALSIFICATION", "Finding", "scan"]
