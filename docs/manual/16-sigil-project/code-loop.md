# CODE.LOOP@1

Reference. CODE.LOOP@1 reads the loops in one Python file against 19 ruff
rules. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the 19 rules on the card and with preview rules on. The file goes to ruff
on standard input, from the folder of the file. For a function or class, only
the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_loop.py, in _ruff_findings`:

```python
def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    return [(row.code, row.line) for row in check(source, folder, RULES, preview=True)]
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
| B035 | static-key-dict-comprehension | Checks for dictionary comprehensions that use a static key, like a string literal or a variable defined outside the comprehension. | none | no |
| C416 | unnecessary-comprehension | Checks for unnecessary dict, list, and set comprehension. | always | no |
| C419 | unnecessary-comprehension-in-call | Checks for unnecessary list or set comprehensions passed to builtin functions that take an iterable. | sometimes | no |
| C420 | unnecessary-dict-comprehension-for-iterable | Checks for unnecessary dict comprehension when creating a dictionary from an iterable. | sometimes | no |
| SIM911 | zip-dict-keys-and-values | Checks for use of `zip()` to iterate over keys and values of a dictionary at once. | always | no |
| PERF102 | incorrect-dict-iterator | Checks for uses of `dict.items()` that discard either the key or the value when iterating over the dictionary. | always | no |
| PERF402 | manual-list-copy | Checks for `for` loops that append every item of an iterable to a list, which can be replaced with a call to `list`. | none | no |
| PLC0206 | dict-index-missing-items | Checks for dictionary iterations that extract the dictionary value via explicit indexing, instead of using `.items()`. | none | no |
| PLE4703 | modified-iterating-set | Checks for loops in which a `set` is modified during iteration. | always | yes |
| PLR1733 | unnecessary-dict-index-lookup | Checks for key-based dict accesses during `.items()` iterations. | always | no |
| PLR1736 | unnecessary-list-index-lookup | Checks for index-based list accesses during `enumerate` iterations. | always | no |
| PLW0120 | useless-else-on-loop | Checks for `else` clauses on loops without a `break` statement. | sometimes | no |
| UP028 | yield-in-for-loop | Checks for `for` loops that can be replaced with `yield from` expressions. | sometimes | no |
| FURB122 | for-loop-writes | Checks for the use of `IOBase.write` in a for loop. | always | no |
| FURB129 | readlines-in-for | Checks for uses of `readlines()` when iterating over a file line-by-line. | always | no |
| FURB140 | reimplemented-starmap | Checks for generator expressions, list and set comprehensions that can be replaced with `itertools.starmap`. | sometimes | yes |
| FURB142 | for-loop-set-mutations | Checks for code that updates a set with the contents of an iterable by using a `for` loop to call `.add()` or `.discard()` on each element separately. | always | yes |
| RUF006 | asyncio-dangling-task | Checks for `asyncio.create_task` and `asyncio.ensure_future` calls that do not store a reference to the returned result. | none | no |

## Rules left off

The card holds no list of rules left off, so every rule this sigil reads is in
the table above.
