# Peer Reviewer A v2 — full transcript

Independent Claude subagent, spawned in parallel with Reviewer B v2.
Same prompt scaffold as v1. Judgment-only review of the same two
fixtures (unchanged). Purpose: verify that adding new mechanical
tools to the archetype does not degrade the multi-agent aspect of
the harness.

## Response

FILE: known_good.py
  - LINE 29: `main()` prints without a docstring; minor style gap for consistency with other functions.  [SEVERITY: low]
  - LINE 30-31: Uses bare `print` for I/O in a module also exposing a library API; mixing entrypoint and library concerns.  [SEVERITY: low]
  - LINE 26: `ValueError` message is lowercase; conventional Python style prefers sentence-case.  [SEVERITY: low]

FILE: known_bad.py
  - LINE 17: `import subprocess` is unused.  [SEVERITY: medium]
  - LINE 17: Importing `subprocess` at module scope, even unused, invites future misuse; remove.  [SEVERITY: low]
  - LINE 20: Hardcoded credential `DB_PASSWORD = "hunter2"` — secret in source, Bandit B105.  [SEVERITY: high]
  - LINE 20: Module-level mutable-looking secret has no access controls; should come from env/secret store.  [SEVERITY: high]
  - LINE 23: `broken_types(x, y)` missing parameter and return type hints (PEP 484).  [SEVERITY: medium]
  - LINE 23: Function name `broken_types` is misleading (does addition); poor naming.  [SEVERITY: low]
  - LINE 23: Missing docstring on public function.  [SEVERITY: low]
  - LINE 24: `unused_local = 42` assigned but never used (dead code).  [SEVERITY: medium]
  - LINE 25: `return x + y` has no defined behavior contract for non-numeric inputs; latent TypeError risk given missing hints.  [SEVERITY: medium]
  - LINE 28: `check_positive` missing docstring.  [SEVERITY: low]
  - LINE 29: `assert n > 0` used for input validation — stripped under `python -O`; Bandit B101. Should raise `ValueError`.  [SEVERITY: high]
  - LINE 33: `entry()` missing docstring.  [SEVERITY: low]
  - LINE 34: Passes literal `2` into `broken_types` — fine, but demonstrates that no negative/zero path exercises `check_positive`'s assertion; weak self-test.  [SEVERITY: low]
  - GLOBAL: No `from __future__ import annotations` despite mixed-hint style; inconsistent with sibling file.  [SEVERITY: low]
  - GLOBAL: Module lacks `__all__`; minor.  [SEVERITY: low]

```json
{
  "known_good.py": {"total_issues": 3, "issues": [
    {"line": 29, "severity": "low", "description": "main() missing docstring"},
    {"line": 30, "severity": "low", "description": "library module mixes print entrypoint with API"},
    {"line": 26, "severity": "low", "description": "ValueError message not sentence-cased"}
  ]},
  "known_bad.py": {"total_issues": 14, "issues": [
    {"line": 17, "severity": "medium", "description": "unused import subprocess"},
    {"line": 17, "severity": "low", "description": "subprocess import invites misuse"},
    {"line": 20, "severity": "high", "description": "hardcoded password DB_PASSWORD (Bandit B105)"},
    {"line": 20, "severity": "high", "description": "secret in source, no env/secret-store indirection"},
    {"line": 23, "severity": "medium", "description": "broken_types missing type hints (PEP 484)"},
    {"line": 23, "severity": "low", "description": "misleading function name broken_types"},
    {"line": 23, "severity": "low", "description": "missing docstring"},
    {"line": 24, "severity": "medium", "description": "unused local variable unused_local"},
    {"line": 25, "severity": "medium", "description": "latent TypeError from untyped x+y"},
    {"line": 28, "severity": "low", "description": "check_positive missing docstring"},
    {"line": 29, "severity": "high", "description": "assert for input validation, stripped under -O (Bandit B101)"},
    {"line": 33, "severity": "low", "description": "entry missing docstring"},
    {"line": 34, "severity": "low", "description": "test path never triggers assertion branch"},
    {"line": 0, "severity": "low", "description": "no from __future__ import annotations; inconsistent with sibling"}
  ]}
}
```

Usage: 37,957 subagent tokens; 2 tool uses; 28,580 ms.
