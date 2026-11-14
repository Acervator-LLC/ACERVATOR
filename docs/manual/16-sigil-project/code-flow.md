# CODE.FLOW@1

Reference. CODE.FLOW@1 reads the if, try, with, return, raise, assert, pass and
del statements in one Python file against the 33 ruff rules it can run. The Coding Archetype
owns it. It is one sigil of [the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.FLOW@1 reads each if, try, with, return, raise, assert, pass and del
statement for a control path that fails, hides an error, opens a hole, wastes
work, or reads harder than Python's own form. It draws on five disciplines:
conventions, maintainability, performance efficiency, reliability and security.

The card holds no rule list of its own. It takes each ruff rule that the
construct scope places on the flow construct and that one of its disciplines
houses. [The construct scope](../16-sigil-project.md#the-construct-scope)
states how a rule is placed.

`dev_harness/sigils/code_flow.py, in TAKEN`:

```python
DISCIPLINES = (
    "conventions",
    "maintainability",
    "performance-efficiency",
    "reliability",
    "security",
)
TAKEN = take("flow", DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the 33 rules the card can run. Three of them are preview rules, so ruff runs
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
FINDINGS reads HOLD only when the file sits in application source and PLE0101
or PLE0704 fires. These are the pylint error rules for a value returned from
an init method, and for a bare raise outside an except clause. Every other
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
| B012 | jump-statement-in-finally | Checks for `break`, `continue`, and `return` statements in `finally` blocks. | none | no |
| B029 | except-with-empty-tuple | Checks for exception handlers that catch an empty tuple. | none | no |
| B901 | return-in-generator | Checks for `return {value}` statements in functions that also contain `yield` or `yield from` statements. | none | yes |
| B904 | raise-without-from-inside-except | Checks for `raise` statements in exception handlers that lack a `from` clause. | none | no |
| E722 | bare-except | Checks for bare `except` catches in `try`-`except` statements. | none | no |
| F631 | assert-tuple | Checks for `assert` statements that use non-empty tuples as test conditions. | none | no |
| F707 | default-except-not-last | Checks for `except` blocks that handle all exceptions, but are not the last `except` block in a `try` statement. | none | no |
| FURB101 | read-whole-file | Checks for uses of `open` and `read` that can be replaced by `pathlib` methods, like `Path.read_text` and `Path.read_bytes`. | sometimes | yes |
| FURB103 | write-whole-file | Checks for uses of `open` and `write` that can be replaced by `pathlib` methods, like `Path.write_text` and `Path.write_bytes`. | sometimes | yes |
| FURB188 | slice-to-remove-prefix-or-suffix | Checks for code that could be written more idiomatically using [`str.removeprefix()`](https://docs.python.org/3/library/stdtypes.html#str.removeprefix) or [`str.removesuffix()`](https://docs.python.org/3/library/stdtypes.html#str.removesuffix). | always | no |
| G201 | logging-exc-info | Checks for uses of `logging.error` that pass `exc_info=True`. | none | no |
| PERF401 | manual-list-comprehension | Checks for `for` loops that can be replaced by a list comprehension. | sometimes | no |
| PLE0101 | return-in-init | Checks for `__init__` methods that return values. | none | no |
| PLE0704 | misplaced-bare-raise | Checks for bare `raise` statements outside of exception handlers. | none | no |
| PLR1708 | stop-iteration-return | Checks for explicit `raise StopIteration` in generator functions. | none | no |
| PLR1722 | sys-exit-alias | Checks for uses of the `exit()` and `quit()`. | sometimes | no |
| PLR1730 | if-stmt-min-max | Checks for `if` statements that can be replaced with `min()` or `max()` calls. | sometimes | no |
| PT012 | pytest-raises-with-multiple-statements | Checks for `pytest.raises` context managers with multiple statements. | none | no |
| PT017 | pytest-assert-in-except | Checks for `assert` statements in `except` clauses. | none | no |
| RET502 | implicit-return-value | Checks for the presence of a `return` statement with no explicit value, for functions that return non-`None` values elsewhere. | always | no |
| RET505 | superfluous-else-return | Checks for `else` statements with a `return` statement in the preceding `if` block. | sometimes | no |
| RET506 | superfluous-else-raise | Checks for `else` statements with a `raise` statement in the preceding `if` block. | sometimes | no |
| RET507 | superfluous-else-continue | Checks for `else` statements with a `continue` statement in the preceding `if` block. | sometimes | no |
| RET508 | superfluous-else-break | Checks for `else` statements with a `break` statement in the preceding `if` block. | sometimes | no |
| S101 | assert | Checks for uses of the `assert` keyword. | none | no |
| S110 | try-except-pass | Checks for uses of the `try`-`except`-`pass` pattern. | none | no |
| S112 | try-except-continue | Checks for uses of the `try`-`except`-`continue` pattern. | none | no |
| SIM102 | collapsible-if | Checks for nested `if` statements that can be collapsed into a single `if` statement. | sometimes | no |
| SIM107 | return-in-try-except-finally | Checks for `return` statements in `try`-`except` and `finally` blocks. | none | no |
| SIM116 | if-else-block-instead-of-dict-lookup | Checks for three or more consecutive if-statements with direct returns | none | no |
| SIM117 | multiple-with-statements | Checks for the unnecessary nesting of multiple consecutive context managers. | sometimes | no |
| TRY004 | type-check-without-type-error | Checks for type checks that do not raise `TypeError`. | none | no |
| TRY300 | try-consider-else | Checks for `return` statements in `try` blocks. | none | no |

## Rules left off

The card does not run the rules below, though its own rule list once named
them. Each reason comes from the construct scope and the six disciplines. The
card's left setting names every rule on the flow construct that no discipline
houses, with its unplaced.json text.

| Rule | Reason |
| ---- | ------ |
| ASYNC100 | No discipline houses it. |
| G202 | No discipline houses it. |
| RET501 | No discipline houses it. |
| SIM105 | No discipline houses it. |
| SIM114 | No discipline houses it. |
| TC005 | No discipline houses it. |
| E701 | It reads text the AST does not hold, so it sits on no construct. |
| PLE1205 | No discipline houses it. |
| PLE1206 | No discipline houses it. |
| PLR1711 | No discipline houses it. |
| PLR5501 | It reads text the AST does not hold, so it sits on no construct. |
| FURB131 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
| FURB132 | No discipline houses it. |
| RUF047 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
| RUF050 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
| RUF072 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
| TRY203 | No discipline houses it. |
| TRY301 | No discipline houses it. |
| TRY400 | No discipline houses it. |
