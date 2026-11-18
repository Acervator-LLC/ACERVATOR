# CODE.LOOP@1

Reference. CODE.LOOP@1 reads the loops in one Python file against the 29 ruff
rules it can run. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.LOOP@1 reads each loop and comprehension for the faults that give a wrong
result, waste work, or write by hand what Python's own forms already state. It
draws on the Python discipline, under three characteristics: conventions,
performance efficiency and reliability.

The card holds no rule list of its own. It takes each ruff rule that the
construct scope places on the loop construct and that the Python discipline
houses under one of its characteristics. [The construct scope](../16-sigil-project.md#the-construct-scope)
states how a rule is placed.

`dev_harness/sigils/code_loop.py, in TAKEN`:

```python
DISCIPLINES = ("python",)
CHARACTERISTICS = ("conventions", "performance-efficiency", "reliability")
TAKEN = take("loop", DISCIPLINES, CHARACTERISTICS)
```

## How its loop rules were found

Two readings looked for every loop rule the Python discipline houses, without
starting from the construct scope. The first reads each rule's published pair
and asks whether the corrected form changes a for, async for or while
statement, or a list, set or dictionary builder or generator expression, of the
faulty form. The second reads each rule's published text for a loop.

| Reading | Rules it names, of 491 housed ruff rules |
| ------- | ---------------------------------------- |
| the published pair changes a loop | 34 |
| the published text names a loop | 43 |
| both | 27 |

The construct scope already placed 16 of the 27 on the loop construct. It
places the other 11 there through a list in the scope command, each with the
first loop node its corrected form changes.

One reading alone names 23 rules. B031 and PTH206 of them sit on the loop
construct through the climb. The other 21 were read against their pairs and
stay off the card. A rule joins only when its corrected form changes the loop
itself, and its faulty form holds no fault outside the loop. Each of the 21
fails one test: its corrected form leaves the loop as it is, its faulty form
holds the fault outside a loop too, its faulty form holds no loop, or ruff
publishes no pair for it.

`dev_harness/sigils/construct_scope.py, in LOOP_PAIRS`:

```python
LOOP_PAIRS = (
    "B023",
    "C400",
    "PERF101",
    "PERF203",
    "PERF401",
    "PERF403",
    "PLC0208",
    "RET507",
    "RET508",
    "SIM110",
    "SIM113",
)
```

| Rule | Where the climb places it | The loop node its corrected form changes |
| ---- | ------------------------- | ---------------------------------------- |
| B023 | none | the list builder at line 1 |
| C400 | collection | the generator expression at line 1 |
| PERF101 | collection | the for at line 2 |
| PERF203 | none | the for at line 5 |
| PERF401 | flow | the for at line 3 |
| PERF403 | variable | the for at line 3 |
| PLC0208 | collection | the for at line 1 |
| RET507 | flow | the for at line 2 |
| RET508 | flow | the for at line 2 |
| SIM110 | none | the for at line 2 |
| SIM113 | variable | the for at line 3 |

PERF203 fires only when ruff's target is below Python 3.11. This tree's
`pyproject.toml` requires Python 3.14, so its faulty form reads CLEAN here. The
test pair reads it again under a ruff.toml that sets target-version py310, and
there it reads FINDINGS.

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the selected rules of the 29 the card can run and with preview rules on. The file goes to ruff
on standard input, from the folder of the file. For a function or class, only
the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

When ruff is missing or its installed version is not 0.16.0,
`dev_harness/sigils/core.py, in version_fault` refuses the input at tier 3
before ruff runs.

`dev_harness/sigils/code_loop.py, in _ruff_findings`:

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

Tier 2 accepts an input only when Python's ast module finds a for, async for,
while, list, set or dictionary builder, or generator expression in the input's
lines. An input that holds none is refused at tier 2.

`dev_harness/sigils/code_loop.py, in LOOP_NODES`:

```python
LOOP_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
```

## The selection

For each input, CODE.LOOP@1 runs only those of its 29 rules that the run rule
selects for the input's facts. A rule whose subject the input lacks does not
run, and an input that selects no rule runs no ruff.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_loop.py, in _functions_verdict`:

```python
    version, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_loop.py, in findings`, the rules ruff gets:

```python
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 418 | 29 | 17 | 24 | 28 | 113 | 113 |
| def or class | 3,775 | 29 | 7 | 21 | 28 | 159 | 159 |

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms.
FINDINGS reads HOLD only when the file sits in application source and PLE4703
fires. PLE4703 is the one pylint error-class rule on the list. Every other
finding reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_loop/`.

```
python -m dev_harness.sigils.code_loop <file>
python -m dev_harness.sigils.code_loop --root <folder> <file>
python -m dev_harness.sigils.code_loop --gate <file>
python -m dev_harness.sigils.code_loop --card
```

## Rules

Each line comes from `python -m ruff rule <code>` for ruff 0.16.0. The fix
column is the fix class ruff states. A preview rule fires only with preview
rules on.

| Rule | ruff name | What it catches | Fix | Preview |
| ---- | --------- | --------------- | --- | ------- |
| ASYNC110 | async-busy-wait | Checks for the use of an async sleep function in a `while` loop. | none | no |
| B007 | unused-loop-control-variable | Checks for unused variables in loops (e.g., `for` and `while` statements). | sometimes | no |
| B023 | function-uses-loop-variable | Checks for function definitions that use a loop variable. | none | no |
| B031 | reuse-of-groupby-generator | Checks for multiple usage of the generator returned from `itertools.groupby()`. | none | no |
| C400 | unnecessary-generator-list | Checks for unnecessary generators that can be rewritten as list comprehensions (or with `list()` directly). | always | no |
| C419 | unnecessary-comprehension-in-call | Checks for unnecessary list or set comprehensions passed to builtin functions that take an iterable. | sometimes | no |
| C420 | unnecessary-dict-comprehension-for-iterable | Checks for unnecessary dict comprehension when creating a dictionary from an iterable. | sometimes | no |
| F402 | import-shadowed-by-loop-var | Checks for import bindings that are shadowed by loop variables. | none | no |
| FURB129 | readlines-in-for | Checks for uses of `readlines()` when iterating over a file line-by-line. | always | no |
| FURB140 | reimplemented-starmap | Checks for generator expressions, list and set comprehensions that can be replaced with `itertools.starmap`. | sometimes | yes |
| PERF101 | unnecessary-list-cast | Checks for explicit casts to `list` on for-loop iterables. | always | no |
| PERF102 | incorrect-dict-iterator | Checks for uses of `dict.items()` that discard either the key or the value when iterating over the dictionary. | always | no |
| PERF203 | try-except-in-loop | Checks for uses of except handling via `try`-`except` within `for` and `while` loops. | none | no |
| PERF401 | manual-list-comprehension | Checks for `for` loops that can be replaced by a list comprehension. | sometimes | no |
| PERF402 | manual-list-copy | Checks for `for` loops that append every item of an iterable to a list, which can be replaced with a call to `list`. | none | no |
| PERF403 | manual-dict-comprehension | Checks for `for` loops that can be replaced by a dictionary comprehension. | sometimes | no |
| PLC0206 | dict-index-missing-items | Checks for dictionary iterations that extract the dictionary value via explicit indexing, instead of using `.items()`. | none | no |
| PLC0208 | iteration-over-set | Checks for iteration over a `set` literal in which each element is a literal. | always | no |
| PLE4703 | modified-iterating-set | Checks for loops in which a `set` is modified during iteration. | always | yes |
| PLR1733 | unnecessary-dict-index-lookup | Checks for key-based dict accesses during `.items()` iterations. | always | no |
| PLR1736 | unnecessary-list-index-lookup | Checks for index-based list accesses during `enumerate` iterations. | always | no |
| PTH206 | os-sep-split | Checks for uses of `.split(os.sep)` | none | no |
| RET507 | superfluous-else-continue | Checks for `else` statements with a `continue` statement in the preceding `if` block. | sometimes | no |
| RET508 | superfluous-else-break | Checks for `else` statements with a `break` statement in the preceding `if` block. | sometimes | no |
| RUF006 | asyncio-dangling-task | Checks for `asyncio.create_task` and `asyncio.ensure_future` calls that do not store a reference to the returned result. | none | no |
| SIM110 | reimplemented-builtin | Checks for `for` loops that can be replaced with a builtin function, like `any` or `all`. | sometimes | no |
| SIM113 | enumerate-for-loop | Checks for `for` loops with explicit loop-index variables that can be replaced with `enumerate()`. | none | no |
| SIM911 | zip-dict-keys-and-values | Checks for use of `zip()` to iterate over keys and values of a dictionary at once. | always | no |
| UP028 | yield-in-for-loop | Checks for `for` loops that can be replaced with `yield from` expressions. | sometimes | no |

## Rules left off

The card does not run the rules below, though its own rule list once named
them. Each reason comes from the construct scope and the Python discipline. The
card's left setting names every rule on the loop construct that no discipline
houses, with its unplaced.json text.

| Rule | Reason |
| ---- | ------ |
| B035 | No discipline houses it. |
| C416 | No discipline houses it. |
| PLW0120 | No discipline houses it. |
| FURB122 | No discipline houses it. |
| FURB142 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
