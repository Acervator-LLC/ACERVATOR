# Peer Reviewer A — full transcript

Spawned via `Agent(subagent_type="general-purpose")`. Instructed to
review the two fixtures using judgment only (no tool invocation).

## Response

FILE: known_good.py
  - LINE 29: `main()` function lacks a docstring while every other function has one (minor inconsistency).  [SEVERITY: low]
  - LINE 30-31: Uses `print()` for output instead of a logger, acceptable for a small script but not for library code.  [SEVERITY: low]

FILE: known_bad.py
  - LINE 17: `import subprocess` is unused.  [SEVERITY: medium]
  - LINE 20: Hardcoded credential `DB_PASSWORD = "hunter2"` — secret in source.  [SEVERITY: high]
  - LINE 23: `broken_types(x, y)` missing parameter and return type annotations.  [SEVERITY: medium]
  - LINE 23: `broken_types` lacks a docstring.  [SEVERITY: low]
  - LINE 24: Local variable `unused_local = 42` is assigned but never used (dead code).  [SEVERITY: low]
  - LINE 28: `check_positive` lacks a docstring.  [SEVERITY: low]
  - LINE 29: `assert n > 0` used for validation — asserts are stripped under `python -O`, making this an unreliable check (security/correctness).  [SEVERITY: high]
  - LINE 33: `entry()` lacks a docstring.  [SEVERITY: low]
  - LINE 20: Module-level constant `DB_PASSWORD` naming suggests real credential; should be loaded from env/secret store.  [SEVERITY: high]
  - Missing `from __future__ import annotations` (present in the good file, omitted here); minor style inconsistency across the fixture pair.  [SEVERITY: low]

```json
{
  "known_good.py": {
    "total_issues": 2,
    "issues": [
      {"line": 29, "severity": "low", "description": "main() lacks a docstring while sibling functions have one"},
      {"line": 30, "severity": "low", "description": "Uses print() rather than logging"}
    ]
  },
  "known_bad.py": {
    "total_issues": 10,
    "issues": [
      {"line": 17, "severity": "medium", "description": "Unused import: subprocess"},
      {"line": 20, "severity": "high", "description": "Hardcoded password/secret in source"},
      {"line": 20, "severity": "high", "description": "Credential should come from env/secret store, not module constant"},
      {"line": 23, "severity": "medium", "description": "broken_types missing type hints on params and return"},
      {"line": 23, "severity": "low", "description": "broken_types missing docstring"},
      {"line": 24, "severity": "low", "description": "unused_local assigned but never referenced"},
      {"line": 28, "severity": "low", "description": "check_positive missing docstring"},
      {"line": 29, "severity": "high", "description": "assert used for runtime validation; stripped under python -O"},
      {"line": 33, "severity": "low", "description": "entry() missing docstring"},
      {"line": 1, "severity": "low", "description": "Missing 'from __future__ import annotations' present in paired fixture"}
    ]
  }
}
```

Usage: 37,912 subagent tokens; 2 tool uses; 18,133 ms.
