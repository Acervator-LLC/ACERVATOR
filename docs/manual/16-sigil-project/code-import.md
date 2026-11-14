# CODE.IMPORT@1

Reference. CODE.IMPORT@1 reads the import statements in one Python file
against the 25 ruff rules it can run. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.IMPORT@1 reads each import statement for an import that fails, slows the
start, hides the name it binds, or departs from Python's ordering, naming and
typing practice. It draws on four disciplines: conventions, performance
efficiency, reliability and typing.

The card holds no rule list of its own. It takes each ruff rule that the
construct scope places on the import construct and that one of its disciplines
houses. [The construct scope](../16-sigil-project.md#the-construct-scope)
states how a rule is placed.

`dev_harness/sigils/code_import.py, in TAKEN`:

```python
DISCIPLINES = ("conventions", "performance-efficiency", "reliability", "typing")
TAKEN = take("import", DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the selected rules of the 25 the card can run. No rule on the list is a preview rule, so ruff
runs with preview rules off. The file goes to ruff on standard input, from the
folder of the file. For a function or class, only the findings inside its lines
count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_import.py, in _ruff_findings`:

```python
def _ruff_findings(
    source: bytes, folder: Path, rules: tuple[str, ...]
) -> list[tuple[str, int]]:
    """Return each code and line of `rules` for `source` on stdin, run from `folder`; none when `rules` is empty."""
    if not rules:
        return []
    rows = check(source, folder, rules, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]
```

Tier 2 accepts an input only when Python's ast module finds an import or
from-import statement in the input's lines. An input that holds none is refused
at tier 2.

`dev_harness/sigils/code_import.py, in IMPORT_NODES`:

```python
IMPORT_NODES = (ast.Import, ast.ImportFrom)
NO_IMPORT = "no import or from-import statement"
```

## The selection

For each input, CODE.IMPORT@1 runs only those of its 25 rules that the run rule
selects for the input's facts. Each of the 25 needs an import statement in the
input, and tier 2 already refuses an input that holds none, so every input it
accepts selects all 25.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_import.py, in _functions_verdict`:

```python
    version, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_import.py, in findings`, the rules ruff gets:

```python
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 490 | 25 | 25 | 25 | 25 | 4,199 | 4,199 |
| def or class | 1,016 | 25 | 25 | 25 | 25 | 3,041 | 3,041 |

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | FIX |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms. A
finding holds a merge only when it is a pylint error-class rule or the pyflakes
undefined-name rules F821, F822 and F823. No rule on the list is any of these, so
the holding list on the card is empty and every finding reads FIX.

`dev_harness/sigils/construct_rules.py, in take`:

```python
    holding = tuple(
        code for code in rules if code.startswith(ERROR_CLASS) or code in UNDEFINED_NAMES
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
| E401 | multiple-imports-on-one-line | Check for multiple imports on one line. | always | no |
| E402 | module-import-not-at-top-of-file | Checks for imports that are not at the top of the file. | sometimes | no |
| F401 | unused-import | Checks for unused imports. | sometimes | no |
| F403 | undefined-local-with-import-star | Checks for the use of wildcard imports. | none | no |
| F404 | late-future-import | Checks for `__future__` imports that are not located at the beginning of a file. | none | no |
| F406 | undefined-local-with-nested-import-star-usage | Check for the use of wildcard imports outside of the module namespace. | none | no |
| I001 | unsorted-imports | De-duplicates, groups, and sorts imports based on the provided `isort` settings. | sometimes | no |
| ICN001 | unconventional-import-alias | Checks for imports that are typically imported using a common convention, like `import pandas as pd`, and enforces that convention. | sometimes | no |
| N811 | constant-imported-as-non-constant | Checks for constant imports that are aliased to non-constant-style names. | none | no |
| N812 | lowercase-imported-as-non-lowercase | Checks for lowercase imports that are aliased to non-lowercase names. | none | no |
| N813 | camelcase-imported-as-lowercase | Checks for `CamelCase` imports that are aliased to lowercase names. | none | no |
| N814 | camelcase-imported-as-constant | Checks for `CamelCase` imports that are aliased to constant-style names. | none | no |
| N817 | camelcase-imported-as-acronym | Checks for `CamelCase` imports that are aliased as acronyms. | none | no |
| PLC0415 | import-outside-top-level | Checks for `import` statements outside of a module's top-level scope, such as within a function or class definition. | none | no |
| PLC2403 | non-ascii-import-name | Checks for the use of non-ASCII characters in import statements. | none | no |
| PLR0402 | manual-from-import | Checks for submodule imports that are aliased to the submodule name. | sometimes | no |
| PYI057 | byte-string-usage | Checks for uses of `typing.ByteString` or `collections.abc.ByteString`. | none | no |
| TC001 | typing-only-first-party-import | Checks for first-party imports that are only used for type annotations, but aren't defined in a type-checking block. | sometimes | no |
| TC002 | typing-only-third-party-import | Checks for third-party imports that are only used for type annotations, but aren't defined in a type-checking block. | sometimes | no |
| TC003 | typing-only-standard-library-import | Checks for standard library imports that are only used for type annotations, but aren't defined in a type-checking block. | sometimes | no |
| TC004 | runtime-import-in-type-checking-block | Checks for imports that are required at runtime but are only defined in type-checking blocks. | sometimes | no |
| TID252 | relative-imports | Checks for relative imports. | sometimes | no |
| UP023 | deprecated-c-element-tree | Checks for uses of the `xml.etree.cElementTree` module. | always | no |
| UP035 | deprecated-import | Checks for uses of deprecated imports based on the minimum supported Python version. | sometimes | no |

## Rules left off

The card does not run the rules below, though its own rule list once named
them. Each reason comes from the construct scope and the six disciplines. The
card's left setting names every rule on the import construct that no discipline
houses, with its unplaced.json text.

| Rule | Reason |
| ---- | ------ |
| UP010 | No discipline houses it. |
| UP029 | No discipline houses it. |
