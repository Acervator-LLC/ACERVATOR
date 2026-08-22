# Coding-Quality Calibration

Domain: Python source code quality.

## What a coding-quality peer reviewer looks for

- **Correctness signals** the tools miss: latent type-confusion in dynamically-typed code, off-by-one, unhandled edge cases, silent exception swallows.
- **Security patterns**: hardcoded credentials, unsafe subprocess/eval, deserialization of untrusted input, weak crypto (MD5/SHA1), SSL verify=False, YAML unsafe loaders.
- **Dead / suspicious code**: unused imports, unused local variables, dead functions, unreachable branches, `TODO`/`FIXME`/`XXX`/`HACK` markers, `pass` bodies.
- **Type-hint discipline**: missing type hints on public functions, `Any` overuse, missing return types, mismatched hints vs behavior.
- **Naming**: misleading function/variable names ("`broken_types` doing addition"), single-letter public parameters, cryptic abbreviations.
- **Docstrings**: missing on public functions/classes, missing on `__init__` when it does non-trivial setup.
- **Style consistency across files**: mixed use of `from __future__ import annotations`, mixed exception message casing.

## Severity conventions (peer reviewer)

- **high**: security issue (hardcoded credential, unsafe subprocess), correctness bug (asserts stripped under `-O`, silent exception swallow, latent TypeError).
- **medium**: dead code, missing type hints on public API, unused imports, magic numbers.
- **low**: docstring gaps, naming preferences, style consistency.

## What the mechanical tools already cover (do not duplicate)

- **ruff `--select=ALL`**: pycodestyle (E/W), pyflakes (F), bandit-mirror (S), bugbear (B), naming (N), docstrings (D), isort (I), pyupgrade (UP), simplify (SIM), pylint (PL), pytest (PT).
- **mypy `--disallow-untyped-defs`**: type-hint gaps on public functions.
- **pyright**: independent type check.
- **bandit** with severity overrides on B101, B105-107, B303, B324, B501-502, B506, B602, B605, B609.
- **vulture `--min-confidence 60`**: dead code including function locals.
- **semgrep p/python + p/security-audit**: pattern-based security and bug rules.

Peer review adds VALUE where semantic understanding matters — bugs that require reading the code's intent, not just its syntax.

## Output shape peer reviewer must return

Markdown findings block, then a single JSON block:

```json
{
  "<filename>": {
    "total_issues": N,
    "issues": [
      {"line": N, "severity": "low|medium|high", "description": "..."}
    ]
  }
}
```

Keep the whole response under 500 words. Do not run tools; the mechanical archetype is the tool layer.
