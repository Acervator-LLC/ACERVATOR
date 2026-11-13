# CODE.OPTIMIZE@1

Reference. CODE.OPTIMIZE@1 reads one Python file against seven ruff rule
families that name a faster or simpler form of the same code. The Coding
Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs ruff with the seven rule families on
the card. The file goes to ruff on standard input, from the folder of the file.
For a function or class, only the findings inside its lines count.

The ruff settings the tree keeps beside the file set the Python version, the
preview rules and the complexity limit. The card records ruff 0.16.0, and the
command prints the ruff version it ran.

`dev_harness/sigils/code_optimize.py, in FAMILIES` and `in _ruff_findings`:

```python
FAMILIES = ("PERF", "SIM", "C4", "UP", "FURB", "PLR17", "C901")


def _ruff_findings(source: bytes, folder: Path) -> list[Finding]:
    """Return each `FAMILIES` `Finding` for `source` on stdin, run from `folder`."""
    return [
        Finding(row.code, row.name, row.line, fix_class(row.code))
        for row in check(source, folder, FAMILIES, preview=False)
    ]
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| OPTIMIZABLE | OPTIMIZE | OPTIMIZE |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule in the seven families fires. OPTIMIZABLE carries, for each
finding, the rule id, the rule name, the line and the fix class ruff states:
always, sometimes or none. OPTIMIZE never holds a merge. The fix class names
what follows: an automatic fix is applied and the file read again, and a rule
with no automatic fix becomes a unit of work.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_optimize/`.

```
python -m dev_harness.sigils.code_optimize <file>
python -m dev_harness.sigils.code_optimize --root <folder> <file>
python -m dev_harness.sigils.code_optimize --gate <file>
python -m dev_harness.sigils.code_optimize --card
```

## Rule families

The card lists rule families, not single rules. One row per family. The
linter name comes from `python -m ruff linter`. The two counts come from the
rule set ruff resolves for the seven families with preview rules off and on,
read with `python -m ruff check --show-settings` for ruff 0.16.0. Each finding
carries its own rule's fix class.

| Family | ruff linter | Rules, preview off | Rules, preview on |
| ------ | ----------- | ------------------ | ----------------- |
| PERF | Perflint | 6 | 6 |
| SIM | flake8-simplify | 30 | 30 |
| C4 | flake8-comprehensions | 19 | 19 |
| UP | pyupgrade | 45 | 46 |
| FURB | refurb | 22 | 36 |
| PLR17 | Pylint, refactor rules PLR1700 to PLR1799 | 9 | 11 |
| C901 | mccabe | 1 | 1 |

The seven families hold 132 rules with preview rules off and 149 with them on.
C901 is one rule, complex-structure, which ruff states has no automatic fix.

## Families left off

The card holds no list of rules left off, so no family and no rule in one is
left off.
