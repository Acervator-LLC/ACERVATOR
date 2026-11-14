# CODE.COLLECTION@1

Reference. CODE.COLLECTION@1 reads the tuples, lists, sets and dictionaries in
one Python file against the 23 ruff rules it can run. The Coding Archetype owns it. It is one
sigil of [the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.COLLECTION@1 reads each tuple, list, set and dictionary, written out, built
or called, for contents that are wrong, wasteful, unsafe, unclear, untyped or
against convention. It draws on six disciplines: conventions, maintainability,
performance efficiency, reliability, security and typing.

The card holds no rule list of its own. It takes each ruff rule that the
construct scope places on the collection construct and that one of its disciplines
houses. [The construct scope](../16-sigil-project.md#the-construct-scope)
states how a rule is placed.

`dev_harness/sigils/code_collection.py, in TAKEN`:

```python
DISCIPLINES = (
    "conventions",
    "maintainability",
    "performance-efficiency",
    "reliability",
    "security",
    "typing",
)
TAKEN = take("collection", DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the selected rules of the 23 the card can run. Two of them are preview rules, so ruff runs
with preview rules on. The file goes to ruff on standard input, from the folder
of the file. For a function or class, only the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_collection.py, in _ruff_findings`:

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

Tier 2 accepts an input only when Python's ast module finds a collection in the
input's lines: a tuple or list written out and read as a value, a set or
dictionary written out, a list, set or dictionary comprehension, or a call to
tuple, list, set or dict by that name. An input that holds none is refused at
tier 2.

`dev_harness/sigils/code_collection.py, in _is_collection`:

```python
def _is_collection(node: ast.expr) -> bool:
    """Report whether `node` writes out, builds or calls a tuple, list, set or dict."""
    if isinstance(node, DISPLAY_NODES):
        return isinstance(node.ctx, ast.Load)
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Name) and node.func.id in BUILDERS
    return isinstance(node, COLLECTION_NODES)
```

## The selection

For each input, CODE.COLLECTION@1 runs only those of its 23 rules that the run
rule selects for the input's facts. A rule whose subject the input lacks does
not run, and an input that selects no rule runs no ruff.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_collection.py, in _functions_verdict`:

```python
    version, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_collection.py, in findings`, the rules ruff gets:

```python
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 470 | 23 | 14 | 18 | 21 | 288 | 288 |
| def or class | 6,720 | 23 | 3 | 17 | 21 | 364 | 364 |

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms.
FINDINGS reads HOLD only when the file sits in application source and F822
fires. F822 is the pyflakes rule for an undefined name in a module's export
list. Every other finding reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_collection/`.

```
python -m dev_harness.sigils.code_collection <file>
python -m dev_harness.sigils.code_collection --root <folder> <file>
python -m dev_harness.sigils.code_collection --gate <file>
python -m dev_harness.sigils.code_collection --card
```

## Rules

Each line comes from `python -m ruff rule <code>` for ruff 0.16.0. The fix
column is the fix class ruff states. A preview rule fires only with preview
rules on.

| Rule | ruff name | What it catches | Fix | Preview |
| ---- | --------- | --------------- | --- | ------- |
| B006 | mutable-argument-default | Checks for uses of mutable objects as function argument defaults. | sometimes | no |
| C400 | unnecessary-generator-list | Checks for unnecessary generators that can be rewritten as list comprehensions (or with `list()` directly). | always | no |
| C414 | unnecessary-double-cast-or-process | Checks for unnecessary `list()`, `reversed()`, `set()`, `sorted()`, and `tuple()` call within `list()`, `set()`, `sorted()`, and `tuple()` calls. | always | no |
| C419 | unnecessary-comprehension-in-call | Checks for unnecessary list or set comprehensions passed to builtin functions that take an iterable. | sometimes | no |
| C420 | unnecessary-dict-comprehension-for-iterable | Checks for unnecessary dict comprehension when creating a dictionary from an iterable. | sometimes | no |
| F634 | if-tuple | Checks for `if` statements that use non-empty tuples as test conditions. | none | no |
| F822 | undefined-export | Checks for undefined names in `__all__`. | none | no |
| G101 | logging-extra-attr-clash | Checks for `extra` keywords in logging statements that clash with `LogRecord` attributes. | none | no |
| NPY201 | numpy2-deprecation | Checks for uses of NumPy functions and constants that were removed from the main namespace in NumPy 2.0. | sometimes | no |
| PERF101 | unnecessary-list-cast | Checks for explicit casts to `list` on for-loop iterables. | always | no |
| PIE800 | unnecessary-spread | Checks for unnecessary dictionary unpacking operators (`**`). | sometimes | no |
| PLC0208 | iteration-over-set | Checks for iteration over a `set` literal in which each element is a literal. | always | no |
| PLR6201 | literal-membership | Checks for membership tests on `list` and `tuple` literals. | always | yes |
| PLW0244 | redefined-slots-in-subclass | Checks for a re-defined slot in a subclass. | none | yes |
| PT007 | pytest-parametrize-values-wrong-type | Checks for the type of parameter values passed to `pytest.mark.parametrize`. | always | no |
| PYI061 | redundant-none-literal | Checks for redundant `Literal[None]` annotations. | sometimes | no |
| RUF008 | mutable-dataclass-default | Checks for mutable default values in dataclass attributes. | none | no |
| RUF012 | mutable-class-default | Checks for mutable default values in class attributes. | none | no |
| RUF022 | unsorted-dunder-all | Checks for `__all__` definitions that are not ordered according to an "isort-style" sort. | sometimes | no |
| RUF023 | unsorted-dunder-slots | Checks for `__slots__` definitions that are not ordered according to a [natural sort](https://en.wikipedia.org/wiki/Natural_sort_order). | sometimes | no |
| S104 | hardcoded-bind-all-interfaces | Checks for hardcoded bindings to all network interfaces (`0.0.0.0`). | none | no |
| S607 | start-process-with-partial-path | Checks for the starting of a process with a partial executable path. | none | no |
| S609 | unix-command-wildcard-injection | Checks for possible wildcard injections in calls to `subprocess.Popen()`. | none | no |

## Rules left off

The card does not run the rules below, though its own rule list once named
them. Each reason comes from the construct scope and the six disciplines. The
card's left setting names every rule on the collection construct that no discipline
houses, with its unplaced.json text.

| Rule | Reason |
| ---- | ------ |
| B013 | No discipline houses it. |
| B033 | No discipline houses it. |
| B039 | No discipline houses it. |
| COM812 | It reads text the AST does not hold, so it sits on no construct. |
| COM818 | It reads text the AST does not hold, so it sits on no construct. |
| COM819 | It reads text the AST does not hold, so it sits on no construct. |
| C401 | No discipline houses it. |
| C402 | No discipline houses it. |
| C403 | No discipline houses it. |
| C404 | No discipline houses it. |
| C405 | No discipline houses it. |
| C406 | No discipline houses it. |
| C408 | No discipline houses it. |
| C409 | No discipline houses it. |
| C410 | No discipline houses it. |
| C411 | No discipline houses it. |
| C418 | No discipline houses it. |
| F601 | No discipline houses it. |
| RUF031 | It reads text the AST does not hold, so it sits on no construct. |
| RUF048 | No discipline houses it. |
| RUF068 | No discipline houses it. |
