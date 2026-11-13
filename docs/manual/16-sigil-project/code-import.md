# CODE.IMPORT@1

Reference. CODE.IMPORT@1 reads the import statements in one Python file
against 8 ruff rules. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the 8 rules on the card. No rule on the list is a preview rule, so ruff
runs with preview rules off. The file goes to ruff on standard input, from the
folder of the file. For a function or class, only the findings inside its lines
count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_import.py, in _ruff_findings`:

```python
def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    return [(row.code, row.line) for row in check(source, folder, RULES, preview=False)]
```

Tier 2 accepts an input only when Python's ast module finds an import or
from-import statement in the input's lines. An input that holds none is refused
at tier 2.

`dev_harness/sigils/code_import.py, in IMPORT_NODES`:

```python
IMPORT_NODES = (ast.Import, ast.ImportFrom)
NO_IMPORT = "no import or from-import statement"
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | FIX |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms. A
finding holds a merge only when it is a pylint error-class rule or the pyflakes
undefined-name rule F821. No rule on the list is either, so the holding list on
the card is empty and every finding reads FIX.

`dev_harness/sigils/code_import.py, in HOLDING`:

```python
HOLDING = tuple(
    code for code in RULES if code.startswith(ERROR_CLASS) or code == UNDEFINED_NAME
)
```

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_import/`.

```
python -m dev_harness.sigils.code_import <file>
python -m dev_harness.sigils.code_import --root <folder> <file>
python -m dev_harness.sigils.code_import --gate <file>
python -m dev_harness.sigils.code_import --card
```

## Rules

Each line comes from `python -m ruff rule <code>` for ruff 0.16.0. The fix
column is the fix class ruff states.

| Rule | ruff name | What it catches | Fix | Preview |
| ---- | --------- | --------------- | --- | ------- |
| A004 | builtin-import-shadowing | Checks for imports that use the same names as builtins. | none | no |
| TC001 | typing-only-first-party-import | Checks for first-party imports that are only used for type annotations, but aren't defined in a type-checking block. | sometimes | no |
| TC003 | typing-only-standard-library-import | Checks for standard library imports that are only used for type annotations, but aren't defined in a type-checking block. | sometimes | no |
| TC004 | runtime-import-in-type-checking-block | Checks for imports that are required at runtime but are only defined in type-checking blocks. | sometimes | no |
| F403 | undefined-local-with-import-star | Checks for the use of wildcard imports. | none | no |
| PLC0415 | import-outside-top-level | Checks for `import` statements outside of a module's top-level scope, such as within a function or class definition. | none | no |
| UP010 | unnecessary-future-import | Checks for unnecessary `__future__` imports. | always | no |
| UP029 | unnecessary-builtin-import | Checks for imports of Python 3 builtins from Python 2 compatibility shims such as `python-future` and `six`. | always | no |

## Rules left off

The card leaves 20 of the 28 import rules off. For each one, the write gate
refused that rule's faulty or corrected sample, because the coding archetype
grades the named finding high. The reason column is the card's own text.

| Rule | ruff name | Reason on the card |
| ---- | --------- | ------------------ |
| ICN001 | unconventional-import-alias | faulty: vulture unused import 'pandas'; mypy import-untyped pandas |
| TID252 | relative-imports | faulty: vulture unused import 'foo' |
| TC002 | typing-only-third-party-import | faulty: mypy import-untyped pandas |
| N811 | constant-imported-as-non-constant | faulty: vulture unused import 'ConstantValue' |
| N812 | lowercase-imported-as-non-lowercase | faulty: vulture unused import 'MyClassName' |
| N813 | camelcase-imported-as-lowercase | faulty: vulture unused import 'myclassname' |
| N814 | camelcase-imported-as-constant | faulty: vulture unused import 'MY_CLASS_NAME' |
| N817 | camelcase-imported-as-acronym | faulty: vulture unused import 'MCN' |
| E401 | multiple-imports-on-one-line | faulty: vulture unused import 'os' |
| E402 | module-import-not-at-top-of-file | faulty: vulture unused import 'os' and 'x' |
| F401 | unused-import | faulty: vulture unused import 'np' |
| F404 | late-future-import | faulty: vulture unused import 'Path' |
| F406 | undefined-local-with-nested-import-star-usage | faulty: pyright, wildcard import not allowed within a class or function |
| F811 | redefined-while-unused | faulty: vulture unused import 'foo' and 'bar' |
| PLC0414 | useless-import-alias | corrected: vulture unused import 'np' |
| PLC2403 | non-ascii-import-name | faulty: vulture unused import 'bár' |
| PLR0402 | manual-from-import | faulty: vulture unused import 'futures' |
| UP023 | deprecated-c-element-tree | faulty: vulture unused import 'ET'; semgrep use-defused-xml |
| UP026 | deprecated-mock-import | faulty: vulture unused import 'mock' |
| UP035 | deprecated-import | faulty: vulture unused import 'Sequence' |
