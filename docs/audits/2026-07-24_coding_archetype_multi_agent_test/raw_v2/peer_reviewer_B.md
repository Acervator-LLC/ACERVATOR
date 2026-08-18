# Peer Reviewer B v2 — full transcript

Independent Claude subagent, spawned in parallel with Reviewer A v2.
Same prompt scaffold as v1. Judgment-only. Independent — no shared
context with Reviewer A.

## Response

FILE: known_good.py
  - LINE 29: `main()` lacks a docstring while sibling functions have them; minor consistency gap [SEVERITY: low]
  - LINE 30-31: `print()` side effects in `main` without any guard/logging abstraction; acceptable for a demo entry point but noteworthy [SEVERITY: low]

FILE: known_bad.py
  - LINE 17: `import subprocess` is unused — dead import, and importing `subprocess` unnecessarily widens the attack surface [SEVERITY: high]
  - LINE 20: `DB_PASSWORD = "hunter2"` hardcoded credential at module scope; Bandit B105 [SEVERITY: high]
  - LINE 23: `broken_types(x, y)` missing parameter and return type annotations (PEP 484 gap) [SEVERITY: high]
  - LINE 23: `broken_types` also lacks a docstring [SEVERITY: low]
  - LINE 23: function name `broken_types` is misleading — describes the defect, not the behavior; naming smell [SEVERITY: low]
  - LINE 24: `unused_local = 42` assigned but never referenced (dead local) [SEVERITY: medium]
  - LINE 25: `return x + y` on an un-annotated function creates a latent runtime bug — `x`/`y` could be any type, so `+` may raise `TypeError` at runtime (e.g., `broken_types("a", 1)`) [SEVERITY: medium]
  - LINE 28: `check_positive` docstring missing [SEVERITY: low]
  - LINE 29: bare `assert n > 0` used as a validation gate — stripped under `python -O`, and Bandit B101 flags assert-for-security; should be `if not n > 0: raise ValueError(...)` [SEVERITY: high]
  - LINE 33: `entry()` lacks a docstring [SEVERITY: low]
  - LINE 34: calls `broken_types(1, 2)` — masks the latent type bug because both args happen to be `int`; still a code-quality concern that untyped surface is exercised only with a safe path [SEVERITY: low]
  - MODULE: no `from __future__ import annotations` (contrast with `known_good.py`); minor consistency gap [SEVERITY: low]
  - MODULE: `DB_PASSWORD` is module-level mutable global constant with no `Final` annotation; PEP 484 gap [SEVERITY: low]

```json
{
  "known_good.py": {"total_issues": 2, "issues": [
    {"line": 29, "severity": "low", "description": "main() missing docstring; inconsistent with siblings"},
    {"line": 30, "severity": "low", "description": "print() side effects in entry point without logging abstraction"}
  ]},
  "known_bad.py": {"total_issues": 12, "issues": [
    {"line": 17, "severity": "high", "description": "unused import subprocess (dead code + attack surface)"},
    {"line": 20, "severity": "high", "description": "hardcoded password DB_PASSWORD='hunter2' (Bandit B105)"},
    {"line": 23, "severity": "high", "description": "broken_types missing type hints on params and return (PEP 484)"},
    {"line": 23, "severity": "low", "description": "broken_types missing docstring"},
    {"line": 23, "severity": "low", "description": "misleading function name 'broken_types'"},
    {"line": 24, "severity": "medium", "description": "unused local variable 'unused_local'"},
    {"line": 25, "severity": "medium", "description": "untyped x+y latent TypeError at runtime"},
    {"line": 28, "severity": "low", "description": "check_positive missing docstring"},
    {"line": 29, "severity": "high", "description": "assert used for validation; stripped under -O (Bandit B101)"},
    {"line": 33, "severity": "low", "description": "entry() missing docstring"},
    {"line": 34, "severity": "low", "description": "broken_types called only with ints, masking latent type bug"},
    {"line": 0, "severity": "low", "description": "module lacks 'from __future__ import annotations' and Final on DB_PASSWORD"}
  ]}
}
```

Usage: 38,089 subagent tokens; 2 tool uses; 26,446 ms.
