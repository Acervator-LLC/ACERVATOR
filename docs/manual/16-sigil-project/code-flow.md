# CODE.FLOW@1

Reference. CODE.FLOW@1 reads the if, try, with, return, raise, assert, pass and
del statements in one Python file against 39 ruff rules. The Coding Archetype
owns it. It is one sigil of [the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the 39 rules on the card. Seven of them are preview rules, so ruff runs
with preview rules on. The file goes to ruff on standard input, from the folder
of the file. For a function or class, only the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_flow.py, in _ruff_findings`:

```python
def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    rows = check(source, folder, RULES, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]
```

Tier 2 accepts an input only when Python's ast module finds a flow statement in
the input's lines: an if, try, try star, with, async with, return, raise,
assert, pass or del statement. An input that holds none is refused at tier 2.

`dev_harness/sigils/code_flow.py, in _content_fault`:

```python
def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_FLOW`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_flow = any(
        isinstance(node, FLOW_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_flow else NO_FLOW
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms.
FINDINGS reads HOLD only when the file sits in application source and PLE0101,
PLE1205 or PLE1206 fires. These are the pylint error rules for a value returned
from an init method, and for too many or too few logging arguments. Every other
finding reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_flow/`.

```
python -m dev_harness.sigils.code_flow <file>
python -m dev_harness.sigils.code_flow --root <folder> <file>
python -m dev_harness.sigils.code_flow --gate <file>
python -m dev_harness.sigils.code_flow --card
```

## Rules

Each line comes from `python -m ruff rule <code>` for ruff 0.16.0. The fix
column is the fix class ruff states. A preview rule fires only with preview
rules on.

| Rule | ruff name | What it catches | Fix | Preview |
| ---- | --------- | --------------- | --- | ------- |
| ASYNC100 | cancel-scope-no-checkpoint | Checks for timeout context managers which do not contain a checkpoint. | none | no |
| B029 | except-with-empty-tuple | Checks for exception handlers that catch an empty tuple. | none | no |
| B901 | return-in-generator | Checks for `return {value}` statements in functions that also contain `yield` or `yield from` statements. | none | yes |
| G201 | logging-exc-info | Checks for uses of `logging.error` that pass `exc_info=True`. | none | no |
| G202 | logging-redundant-exc-info | Checks for redundant `exc_info` keyword arguments in logging statements. | none | no |
| RET501 | unnecessary-return-none | Checks for the presence of a `return None` statement when `None` is the only possible return value. | always | no |
| RET502 | implicit-return-value | Checks for the presence of a `return` statement with no explicit value, for functions that return non-`None` values elsewhere. | always | no |
| RET505 | superfluous-else-return | Checks for `else` statements with a `return` statement in the preceding `if` block. | sometimes | no |
| RET506 | superfluous-else-raise | Checks for `else` statements with a `raise` statement in the preceding `if` block. | sometimes | no |
| RET507 | superfluous-else-continue | Checks for `else` statements with a `continue` statement in the preceding `if` block. | sometimes | no |
| RET508 | superfluous-else-break | Checks for `else` statements with a `break` statement in the preceding `if` block. | sometimes | no |
| SIM102 | collapsible-if | Checks for nested `if` statements that can be collapsed into a single `if` statement. | sometimes | no |
| SIM105 | suppressible-exception | Checks for `try`-`except`-`pass` blocks that can be replaced with the `contextlib.suppress` context manager. | sometimes | no |
| SIM114 | if-with-same-arms | Checks for `if` branches with identical arm bodies. | sometimes | no |
| SIM116 | if-else-block-instead-of-dict-lookup | Checks for three or more consecutive if-statements with direct returns | none | no |
| SIM117 | multiple-with-statements | Checks for the unnecessary nesting of multiple consecutive context managers. | sometimes | no |
| TC005 | empty-type-checking-block | Checks for an empty type-checking block. | always | no |
| PERF401 | manual-list-comprehension | Checks for `for` loops that can be replaced by a list comprehension. | sometimes | no |
| E701 | multiple-statements-on-one-line-colon | Checks for compound statements (multiple statements on the same line). | none | no |
| E722 | bare-except | Checks for bare `except` catches in `try`-`except` statements. | none | no |
| PLE0101 | return-in-init | Checks for `__init__` methods that return values. | none | no |
| PLE1205 | logging-too-many-args | Checks for too many positional arguments for a `logging` format string. | none | no |
| PLE1206 | logging-too-few-args | Checks for too few positional arguments for a `logging` format string. | none | no |
| PLR1708 | stop-iteration-return | Checks for explicit `raise StopIteration` in generator functions. | none | no |
| PLR1711 | useless-return | Checks for functions that end with an unnecessary `return` or `return None`, and contain no other `return` statements. | always | no |
| PLR1730 | if-stmt-min-max | Checks for `if` statements that can be replaced with `min()` or `max()` calls. | sometimes | no |
| PLR5501 | collapsible-else-if | Checks for `else` blocks that consist of a single `if` statement. | sometimes | no |
| FURB101 | read-whole-file | Checks for uses of `open` and `read` that can be replaced by `pathlib` methods, like `Path.read_text` and `Path.read_bytes`. | sometimes | yes |
| FURB103 | write-whole-file | Checks for uses of `open` and `write` that can be replaced by `pathlib` methods, like `Path.write_text` and `Path.write_bytes`. | sometimes | yes |
| FURB131 | delete-full-slice | Checks for `del` statements that delete the entire slice of a list or dictionary. | sometimes | yes |
| FURB132 | check-and-remove-from-set | Checks for uses of `set.remove` that can be replaced with `set.discard`. | always | no |
| RUF047 | needless-else | Checks for `else` clauses that only contains `pass` and `...` statements. | always | yes |
| RUF050 | unnecessary-if | Checks for `if` statements (without `elif` or `else` branches) where the body contains only `pass` or `...` | always | yes |
| RUF072 | useless-finally | Checks for `finally` clauses that only contain `pass` or `...` statements | sometimes | yes |
| TRY004 | type-check-without-type-error | Checks for type checks that do not raise `TypeError`. | none | no |
| TRY203 | useless-try-except | Checks for immediate uses of `raise` within exception handlers. | none | no |
| TRY300 | try-consider-else | Checks for `return` statements in `try` blocks. | none | no |
| TRY301 | raise-within-try | Checks for `raise` statements within `try` blocks. The only `raise`s caught are those that throw exceptions caught by the `try` statement itself. | none | no |
| TRY400 | error-instead-of-exception | Checks for uses of `logging.error` instead of `logging.exception` when logging an exception. | sometimes | no |

## Rules left off

The card leaves 17 of the 56 flow rules off. A reason that starts with faulty
or corrected names the sample. A tool and its finding mean the write gate
refused that sample, because the coding archetype grades the finding high.
Reads names what ruff reads on that published form. The reason column is the
card's own text.

| Rule | ruff name | Reason on the card |
| ---- | --------- | ------------------ |
| S101 | assert | faulty: bandit B101 and ruff S101 use of assert |
| S110 | try-except-pass | faulty: ruff S110 try-except-pass |
| S112 | try-except-continue | faulty: ruff S112 try-except-continue |
| B012 | jump-statement-in-finally | faulty: pyright, a return cannot exit a finally block |
| B904 | raise-without-from-inside-except | faulty: vulture unreachable else block |
| PIE790 | unnecessary-placeholder | corrected: reads PIE790 |
| SIM103 | needless-bool | corrected: reads SIM103 |
| SIM107 | return-in-try-except-finally | faulty: pyright, a return cannot exit a finally block |
| SIM108 | if-else-block-instead-of-if-exp | corrected: reads SIM108 |
| SIM401 | if-else-block-instead-of-dict-get | corrected: reads SIM401 |
| PERF203 | try-except-in-loop | faulty: reads no PERF203, which ruff reads only below Python 3.11 |
| F631 | assert-tuple | faulty: bandit B101 and ruff S101 use of assert |
| F707 | default-except-not-last | faulty: pyright, a named except clause after a catch-all except clause |
| PLE0704 | misplaced-bare-raise | faulty: mypy return and pyright reportReturnType, missing return |
| PLR1712 | swap-with-temporary-variable | faulty: bandit B101 and ruff S101 use of assert |
| PLW0717 | too-many-statements-in-try-clause | faulty: ruff S311 pseudo-random generator |
| RUF051 | if-key-in-dict-del | faulty and corrected: mypy var-annotated, dictionary |
