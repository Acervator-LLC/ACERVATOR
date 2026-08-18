# Peer Reviewer B — full transcript

Spawned via `Agent(subagent_type="general-purpose")`. Instructed to
review the two fixtures using judgment only (no tool invocation).
Independent instance, no shared context with Reviewer A.

## Response

FILE: known_good.py
  - LINE 29: `main()` has no docstring while other functions do — minor inconsistency in a file that otherwise documents every function [SEVERITY: low]
  - LINE 30-31: `print` calls in `main()` have no explanatory context; acceptable for a demo entrypoint but arguably should be behind a logger for reusability [SEVERITY: low]
  - LINE 26: `ValueError` message is lowercase; PEP 8 / common style prefers sentence-case exception messages [SEVERITY: low]

FILE: known_bad.py
  - LINE 17: `import subprocess` is unused — dead import [SEVERITY: medium]
  - LINE 20: `DB_PASSWORD = "hunter2"` — hardcoded credential in source; secret should come from env/secret store [SEVERITY: high]
  - LINE 23: `def broken_types(x, y):` — parameters and return value have no type hints (PEP 484 gap) [SEVERITY: medium]
  - LINE 23: `broken_types` has no docstring [SEVERITY: low]
  - LINE 24: `unused_local = 42` — assigned but never read; dead local variable [SEVERITY: low]
  - LINE 25: `return x + y` — because `x` and `y` are untyped, this silently accepts strings, lists, etc.; latent type-confusion bug [SEVERITY: medium]
  - LINE 28: `check_positive` has no docstring [SEVERITY: low]
  - LINE 29: `assert n > 0` used as a runtime precondition — asserts are stripped under `python -O`, so the check disappears in optimized runs; use explicit `if ... raise ValueError` [SEVERITY: high]
  - LINE 29: on failure, the assert raises a bare `AssertionError` with no message — poor diagnostics [SEVERITY: low]
  - LINE 33: `entry()` has no docstring [SEVERITY: low]
  - MODULE: no `from __future__ import annotations` (present in `known_good.py`) — inconsistency across the fixture pair, and defers to runtime annotation evaluation [SEVERITY: low]
  - MODULE: `DB_PASSWORD` is module-level and would be imported into any consumer's namespace — widens the credential blast radius beyond the file [SEVERITY: medium]

```json
{
  "known_good.py": {
    "total_issues": 3,
    "issues": [
      {"line": 29, "severity": "low", "description": "main() lacks a docstring while sibling functions have one"},
      {"line": 30, "severity": "low", "description": "print used directly in main; a logger would be more reusable"},
      {"line": 26, "severity": "low", "description": "ValueError message is lowercase; prefer sentence-case exception text"}
    ]
  },
  "known_bad.py": {
    "total_issues": 11,
    "issues": [
      {"line": 17, "severity": "medium", "description": "Unused import: subprocess"},
      {"line": 20, "severity": "high", "description": "Hardcoded password 'hunter2' in source"},
      {"line": 23, "severity": "medium", "description": "broken_types missing PEP 484 type hints on params and return"},
      {"line": 23, "severity": "low", "description": "broken_types has no docstring"},
      {"line": 24, "severity": "low", "description": "unused_local assigned but never used"},
      {"line": 25, "severity": "medium", "description": "Untyped x + y silently accepts non-numeric types; latent bug"},
      {"line": 28, "severity": "low", "description": "check_positive has no docstring"},
      {"line": 29, "severity": "high", "description": "assert used for runtime precondition; stripped under python -O"},
      {"line": 29, "severity": "low", "description": "AssertionError raised with no message; poor diagnostics"},
      {"line": 33, "severity": "low", "description": "entry() has no docstring"},
      {"line": 0, "severity": "medium", "description": "Module-level DB_PASSWORD constant leaks the credential to any importer"}
    ]
  }
}
```

Usage: 37,890 subagent tokens; 2 tool uses; 26,950 ms.
