# CODE.COLLECTION@1

Reference. CODE.COLLECTION@1 reads the tuples, lists, sets and dictionaries in
one Python file against 34 ruff rules. The Coding Archetype owns it. It is one
sigil of [the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the 34 rules on the card. Three of them are preview rules, so ruff runs
with preview rules on. The file goes to ruff on standard input, from the folder
of the file. For a function or class, only the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_collection.py, in _ruff_findings`:

```python
def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    rows = check(source, folder, RULES, preview=bool(PREVIEW))
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
| S607 | start-process-with-partial-path | Checks for the starting of a process with a partial executable path. | none | no |
| B006 | mutable-argument-default | Checks for uses of mutable objects as function argument defaults. | sometimes | no |
| B013 | redundant-tuple-in-exception-handler | Checks for single-element tuples in exception handlers (e.g., `except (ValueError,):`). | always | no |
| B033 | duplicate-value | Checks for set literals that contain duplicate items. | sometimes | no |
| B039 | mutable-contextvar-default | Checks for uses of mutable objects as `ContextVar` defaults. | none | no |
| COM812 | missing-trailing-comma | Checks for the absence of trailing commas. | always | no |
| COM818 | trailing-comma-on-bare-tuple | Checks for the presence of trailing commas on bare (i.e., unparenthesized) tuples. | none | no |
| COM819 | prohibited-trailing-comma | Checks for the presence of prohibited trailing commas. | always | no |
| C400 | unnecessary-generator-list | Checks for unnecessary generators that can be rewritten as list comprehensions (or with `list()` directly). | always | no |
| C401 | unnecessary-generator-set | Checks for unnecessary generators that can be rewritten as set comprehensions (or with `set()` directly). | always | no |
| C402 | unnecessary-generator-dict | Checks for unnecessary generators that can be rewritten as dict comprehensions. | always | no |
| C403 | unnecessary-list-comprehension-set | Checks for unnecessary list comprehensions. | always | no |
| C404 | unnecessary-list-comprehension-dict | Checks for unnecessary list comprehensions. | always | no |
| C405 | unnecessary-literal-set | Checks for `set()` calls that take unnecessary list or tuple literals as arguments. | always | no |
| C406 | unnecessary-literal-dict | Checks for unnecessary list or tuple literals. | always | no |
| C408 | unnecessary-collection-call | Checks for unnecessary `dict()`, `list()` or `tuple()` calls that can be rewritten as empty literals. | always | no |
| C409 | unnecessary-literal-within-tuple-call | Checks for `tuple` calls that take unnecessary list or tuple literals as arguments. | sometimes | no |
| C410 | unnecessary-literal-within-list-call | Checks for `list()` calls that take unnecessary list or tuple literals as arguments. | always | no |
| C411 | unnecessary-list-call | Checks for unnecessary `list()` calls around list comprehensions. | sometimes | no |
| C414 | unnecessary-double-cast-or-process | Checks for unnecessary `list()`, `reversed()`, `set()`, `sorted()`, and `tuple()` call within `list()`, `set()`, `sorted()`, and `tuple()` calls. | always | no |
| C418 | unnecessary-literal-within-dict-call | Checks for `dict()` calls that take unnecessary dict literals or dict comprehensions as arguments. | sometimes | no |
| G101 | logging-extra-attr-clash | Checks for `extra` keywords in logging statements that clash with `LogRecord` attributes. | none | no |
| PIE800 | unnecessary-spread | Checks for unnecessary dictionary unpacking operators (`**`). | sometimes | no |
| PERF101 | unnecessary-list-cast | Checks for explicit casts to `list` on for-loop iterables. | always | no |
| F601 | multi-value-repeated-key-literal | Checks for dictionary literals that associate multiple values with the same key. | sometimes | no |
| F822 | undefined-export | Checks for undefined names in `__all__`. | none | no |
| PLC0208 | iteration-over-set | Checks for iteration over a `set` literal in which each element is a literal. | always | no |
| PLR6201 | literal-membership | Checks for membership tests on `list` and `tuple` literals. | always | yes |
| PLW0244 | redefined-slots-in-subclass | Checks for a re-defined slot in a subclass. | none | yes |
| RUF022 | unsorted-dunder-all | Checks for `__all__` definitions that are not ordered according to an "isort-style" sort. | sometimes | no |
| RUF023 | unsorted-dunder-slots | Checks for `__slots__` definitions that are not ordered according to a [natural sort](https://en.wikipedia.org/wiki/Natural_sort_order). | sometimes | no |
| RUF031 | incorrectly-parenthesized-tuple-in-subscript | Checks for consistent style regarding whether nonempty tuples in subscripts are parenthesized. | always | yes |
| RUF048 | map-int-version-parsing | Checks for calls of the form `map(int, __version__.split("."))`. | none | no |
| RUF068 | duplicate-entry-in-dunder-all | Detects duplicate elements in `__all__` definitions. | sometimes | no |

## Rules left off

The card leaves 5 of the 39 collection rules off. For each one, the write gate
refused that rule's faulty or corrected sample, because the coding archetype
grades the named finding high. The reason column is the card's own text.

| Rule | ruff name | Reason on the card |
| ---- | --------- | ------------------ |
| S104 | hardcoded-bind-all-interfaces | faulty: ruff S104 possible binding to all interfaces |
| S609 | unix-command-wildcard-injection | faulty: bandit B602 and B609, ruff S602 and S609, semgrep subprocess-shell-true |
| F634 | if-tuple | faulty: vulture redundant if-condition |
| RUF008 | mutable-dataclass-default | corrected: mypy no-redef and pyright reportRedeclaration, class 'A' |
| RUF012 | mutable-class-default | corrected: mypy no-redef and pyright reportRedeclaration, class 'A' |
