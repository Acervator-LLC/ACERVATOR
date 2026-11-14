# CODE.OPTIMIZE@1

Reference. CODE.OPTIMIZE@1 reads one Python file against the 85 ruff rules it
can run, from seven ruff rule families that name a faster or simpler form of the
same code. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.OPTIMIZE@1 reads each statement for a published rewrite that makes the code
faster, simpler, or current with Python's own forms and annotations. It draws on
four disciplines: conventions, maintainability, performance efficiency and
typing.

Its scope is each rule in the seven families that ruff lists and has not
removed, 149 rules. The card holds each scope rule that one of its disciplines
houses, so it can run 85 rules. A rule housed only under reliability or security
names a fault, not an optimization, and leaves this card.
[The tool scope](../16-sigil-project.md#the-tool-scope) states how a rule is
held.

`dev_harness/sigils/code_optimize.py, in HELD`:

```python
DISCIPLINES = ("conventions", "maintainability", "performance-efficiency", "typing")
SCOPE = tuple(
    sorted(
        code
        for code, listed in listing().items()
        if code.startswith(FAMILIES) and not listed.removed
    )
)
HELD = hold(TOOL, SCOPE, DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs ruff with the selected rules of the 85 the card can
run. The file goes to ruff on standard input, from the folder of the file.
For a function or class, only the findings inside its lines count.

Three of the 85 are preview rules: FURB101, FURB103 and FURB140. They run in a
second ruff call with preview rules on, when the selection keeps one. The ruff settings the tree keeps beside
the file set the Python version, the preview setting of the other 82 rules and
the complexity limit. The card records ruff 0.16.0, and the command prints the
ruff version it ran.

`dev_harness/sigils/code_optimize.py, in FAMILIES` and `in _ruff_findings`:

```python
FAMILIES = ("PERF", "SIM", "C4", "UP", "FURB", "PLR17", "C901")


def _ruff_findings(source: bytes, folder: Path, rules: tuple[str, ...]) -> list[Finding]:
    """Return each `Finding` of `rules` for `source` on stdin, run from `folder`, by line; none when `rules` is empty."""
    stable = tuple(code for code in rules if code in STABLE)
    preview = tuple(code for code in rules if code in PREVIEW)
    rows = check(source, folder, stable, preview=False) if stable else []
    if preview:
        rows += check(source, folder, preview, preview=True)
    return [
        Finding(row.code, row.name, row.line, fix_class(row.code))
        for row in sorted(rows, key=lambda row: row.line)
    ]
```

## The selection

For each input, CODE.OPTIMIZE@1 runs only those of its 85 rules that the run
rule selects for the input's facts. The selected rules that are not preview
rules go to one ruff call, and the selected preview rules to a second. A call
with no selected rule does not run.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_optimize.py, in _functions_verdict`:

```python
    version, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_optimize.py, in findings`, the rules ruff gets:

```python
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 503 | 85 | 4 | 71 | 81 | 2,827 | 2,827 |
| def or class | 13,885 | 85 | 7 | 61 | 81 | 3,884 | 3,884 |

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| OPTIMIZABLE | OPTIMIZE | OPTIMIZE |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. OPTIMIZABLE carries, for each finding,
the rule id, the rule name, the line and the fix class ruff states: always,
sometimes or none. OPTIMIZE never holds a merge. The fix class names what
follows: an automatic fix is applied and the file read again, and a rule with no
automatic fix becomes a unit of work.

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

The seven rule families set the card's scope. One row per family. The linter
name comes from `python -m ruff linter`. The first two counts come from the
rule set ruff resolves for the seven families with preview rules off and on,
read with `python -m ruff check --show-settings` for ruff 0.16.0. The last count
is the rules in the family that the card can run. Each finding carries its own
rule's fix class.

| Family | ruff linter | Rules, preview off | Rules, preview on | Rules it can run |
| ------ | ----------- | ------------------ | ----------------- | ---------------- |
| PERF | Perflint | 6 | 6 | 6 |
| SIM | flake8-simplify | 30 | 30 | 21 |
| C4 | flake8-comprehensions | 19 | 19 | 6 |
| UP | pyupgrade | 45 | 46 | 29 |
| FURB | refurb | 22 | 36 | 17 |
| PLR17 | Pylint, refactor rules PLR1700 to PLR1799 | 9 | 11 | 5 |
| C901 | mccabe | 1 | 1 | 1 |

The seven families hold 132 rules with preview rules off and 149 with them on.
C901 is one rule, complex-structure, which ruff states has no automatic fix.

## Rules

Each line comes from `python -m ruff rule --all` for ruff 0.16.0. The fix
column is the fix class ruff states. The last column names each discipline that
houses the rule, from the rules.json files under `dev_harness/disciplines/`.

`dev_harness/sigils/code_optimize.py, in SETTINGS`: the card prints them as
rules, and the three preview rules again as preview_rules.

| Rule | ruff name | What it catches | Fix | Preview | Housed by |
| ---- | --------- | --------------- | --- | ------- | --------- |
| C400 | unnecessary-generator-list | Checks for unnecessary generators that can be rewritten as list comprehensions (or with `list()` directly). | always | no | conventions |
| C413 | unnecessary-call-around-sorted | Checks for unnecessary `list()` or `reversed()` calls around `sorted()` calls. | always | no | performance efficiency |
| C414 | unnecessary-double-cast-or-process | Checks for unnecessary `list()`, `reversed()`, `set()`, `sorted()`, and `tuple()` call within `list()`, `set()`, `sorted()`, and `tuple()` calls. | always | no | conventions |
| C417 | unnecessary-map | Checks for unnecessary `map()` calls with lambda functions. | sometimes | no | conventions |
| C419 | unnecessary-comprehension-in-call | Checks for unnecessary list or set comprehensions passed to builtin functions that take an iterable. | sometimes | no | performance efficiency |
| C420 | unnecessary-dict-comprehension-for-iterable | Checks for unnecessary dict comprehension when creating a dictionary from an iterable. | sometimes | no | performance efficiency |
| C901 | complex-structure | Checks for functions with a high `McCabe` complexity. | none | no | maintainability |
| FURB101 | read-whole-file | Checks for uses of `open` and `read` that can be replaced by `pathlib` methods, like `Path.read_text` and `Path.read_bytes`. | sometimes | yes | conventions |
| FURB103 | write-whole-file | Checks for uses of `open` and `write` that can be replaced by `pathlib` methods, like `Path.write_text` and `Path.write_bytes`. | sometimes | yes | conventions |
| FURB116 | f-string-number-format | Checks for uses of `bin(...)[2:]` (or `hex`, or `oct`) to convert an integer into a string. | sometimes | no | conventions |
| FURB129 | readlines-in-for | Checks for uses of `readlines()` when iterating over a file line-by-line. | always | no | performance efficiency |
| FURB136 | if-expr-min-max | Checks for `if` expressions that can be replaced with `min()` or `max()` calls. | sometimes | no | conventions |
| FURB140 | reimplemented-starmap | Checks for generator expressions, list and set comprehensions that can be replaced with `itertools.starmap`. | sometimes | yes | conventions |
| FURB157 | verbose-decimal-constructor | Checks for unnecessary string literal or float casts in `Decimal` constructors. | always | no | conventions |
| FURB161 | bit-count | Checks for uses of `bin(...).count("1")` to perform a population count. | always | no | performance efficiency |
| FURB167 | regex-flag-alias | Checks for the use of shorthand aliases for regular expression flags (e.g., `re.I` instead of `re.IGNORECASE`). | always | no | conventions |
| FURB168 | isinstance-type-none | Checks for uses of `isinstance` that check if an object is of type `None`. | always | no | performance efficiency |
| FURB169 | type-none-comparison | Checks for uses of `type` that compare the type of an object to the type of `None`. | always | no | performance efficiency |
| FURB171 | single-item-membership-test | Checks for membership tests against single-item containers. | always | no | performance efficiency |
| FURB177 | implicit-cwd | Checks for current-directory lookups using `Path().resolve()`. | sometimes | no | conventions |
| FURB181 | hashlib-digest-hex | Checks for the use of `.digest().hex()` on a hashlib hash, like `sha512`. | sometimes | no | conventions |
| FURB187 | list-reverse-copy | Checks for list reversals that can be performed in-place in lieu of creating a new list. | always | no | performance efficiency |
| FURB188 | slice-to-remove-prefix-or-suffix | Checks for code that could be written more idiomatically using [`str.removeprefix()`](https://docs.python.org/3/library/stdtypes.html#str.removeprefix) or [`str.removesuffix()`](https://docs.python.org/3/library/stdtypes.html#str.removesuffix). | always | no | performance efficiency |
| FURB192 | sorted-min-max | Checks for uses of `sorted()` to retrieve the minimum or maximum value in a sequence. | sometimes | no | performance efficiency |
| PERF101 | unnecessary-list-cast | Checks for explicit casts to `list` on for-loop iterables. | always | no | performance efficiency |
| PERF102 | incorrect-dict-iterator | Checks for uses of `dict.items()` that discard either the key or the value when iterating over the dictionary. | always | no | performance efficiency |
| PERF203 | try-except-in-loop | Checks for uses of except handling via `try`-`except` within `for` and `while` loops. | none | no | performance efficiency |
| PERF401 | manual-list-comprehension | Checks for `for` loops that can be replaced by a list comprehension. | sometimes | no | performance efficiency |
| PERF402 | manual-list-copy | Checks for `for` loops that append every item of an iterable to a list, which can be replaced with a call to `list`. | none | no | performance efficiency |
| PERF403 | manual-dict-comprehension | Checks for `for` loops that can be replaced by a dictionary comprehension. | sometimes | no | performance efficiency |
| PLR1714 | repeated-equality-comparison | Checks for repeated equality comparisons that can be rewritten as a membership test. | always | no | performance efficiency |
| PLR1716 | boolean-chained-comparison | Check for chained boolean operations that can be simplified. | always | no | conventions |
| PLR1730 | if-stmt-min-max | Checks for `if` statements that can be replaced with `min()` or `max()` calls. | sometimes | no | conventions |
| PLR1733 | unnecessary-dict-index-lookup | Checks for key-based dict accesses during `.items()` iterations. | always | no | conventions |
| PLR1736 | unnecessary-list-index-lookup | Checks for index-based list accesses during `enumerate` iterations. | always | no | conventions |
| SIM102 | collapsible-if | Checks for nested `if` statements that can be collapsed into a single `if` statement. | sometimes | no | conventions |
| SIM107 | return-in-try-except-finally | Checks for `return` statements in `try`-`except` and `finally` blocks. | none | no | conventions |
| SIM110 | reimplemented-builtin | Checks for `for` loops that can be replaced with a builtin function, like `any` or `all`. | sometimes | no | conventions |
| SIM113 | enumerate-for-loop | Checks for `for` loops with explicit loop-index variables that can be replaced with `enumerate()`. | none | no | conventions |
| SIM115 | open-file-with-context-handler | Checks for cases where files are opened (e.g., using the builtin `open()` function) without using a context manager. | none | no | performance efficiency, reliability, security |
| SIM116 | if-else-block-instead-of-dict-lookup | Checks for three or more consecutive if-statements with direct returns | none | no | conventions |
| SIM117 | multiple-with-statements | Checks for the unnecessary nesting of multiple consecutive context managers. | sometimes | no | conventions |
| SIM118 | in-dict-keys | Checks for key-existence checks against `dict.keys()` calls. | always | no | performance efficiency |
| SIM201 | negate-equal-op | Checks for negated `==` operators. | always | no | conventions |
| SIM202 | negate-not-equal-op | Checks for negated `!=` operators. | always | no | conventions |
| SIM208 | double-negation | Checks for double negations (i.e., multiple `not` operators). | always | no | conventions |
| SIM210 | if-expr-with-true-false | Checks for `if` expressions that can be replaced with `bool()` calls. | sometimes | no | conventions |
| SIM211 | if-expr-with-false-true | Checks for `if` expressions that can be replaced by negating a given condition. | always | no | conventions |
| SIM212 | if-expr-with-twisted-arms | Checks for `if` expressions that check against a negated condition. | always | no | conventions |
| SIM220 | expr-and-not-expr | Checks for `and` expressions that include both an expression and its negation. | always | no | maintainability, security |
| SIM221 | expr-or-not-expr | Checks for `or` expressions that include both an expression and its negation. | always | no | maintainability, security |
| SIM222 | expr-or-true | Checks for `or` expressions that contain truthy values. | always | no | maintainability, security |
| SIM223 | expr-and-false | Checks for `and` expressions that contain falsey values. | always | no | maintainability, security |
| SIM300 | yoda-conditions | Checks for conditions that position a constant on the left-hand side of the comparison operator, rather than the right-hand side. | sometimes | no | conventions |
| SIM905 | split-static-string | Checks for static `str.split` calls that can be replaced with list literals. | sometimes | no | conventions |
| SIM911 | zip-dict-keys-and-values | Checks for use of `zip()` to iterate over keys and values of a dictionary at once. | always | no | conventions |
| UP003 | type-of-primitive | Checks for uses of `type` that take a primitive as an argument. | sometimes | no | conventions |
| UP006 | non-pep585-annotation | Checks for the use of generics that can be replaced with standard library variants based on [PEP 585]. | sometimes | no | typing |
| UP007 | non-pep604-annotation-union | Check for type annotations that can be rewritten based on [PEP 604] syntax. | sometimes | no | typing |
| UP008 | super-call-with-parameters | Checks for `super` calls that pass redundant arguments. | sometimes | no | maintainability |
| UP009 | utf8-encoding-declaration | Checks for unnecessary UTF-8 encoding declarations. | always | no | conventions |
| UP013 | convert-typed-dict-functional-to-class | Checks for `TypedDict` declarations that use functional syntax. | sometimes | no | conventions |
| UP014 | convert-named-tuple-functional-to-class | Checks for `NamedTuple` declarations that use functional syntax. | sometimes | no | conventions |
| UP017 | datetime-timezone-utc | Checks for uses of `datetime.timezone.utc`. | sometimes | no | conventions |
| UP018 | native-literals | Checks for unnecessary calls to `str`, `bytes`, `int`, `float`, `bool`, and `complex`. | always | no | conventions |
| UP019 | typing-text-str-alias | Checks for uses of `typing.Text` and `typing_extensions.Text`. | sometimes | no | typing |
| UP021 | replace-universal-newlines | Checks for uses of `subprocess.run` that set the `universal_newlines` keyword argument. | always | no | conventions |
| UP022 | replace-stdout-stderr | Checks for uses of `subprocess.run` that send `stdout` and `stderr` to a pipe. | sometimes | no | conventions |
| UP023 | deprecated-c-element-tree | Checks for uses of the `xml.etree.cElementTree` module. | always | no | conventions |
| UP024 | os-error-alias | Checks for uses of exceptions that alias `OSError`. | always | no | conventions |
| UP028 | yield-in-for-loop | Checks for `for` loops that can be replaced with `yield from` expressions. | sometimes | no | conventions |
| UP030 | format-literals | Checks for unnecessary positional indices in format strings. | sometimes | no | conventions |
| UP031 | printf-string-formatting | Checks for `printf`-style string formatting, and offers to replace it with `str.format` calls. | sometimes | no | conventions, reliability |
| UP032 | f-string | Checks for `str.format` calls that can be replaced with f-strings. | sometimes | no | conventions |
| UP033 | lru-cache-with-maxsize-none | Checks for uses of `functools.lru_cache` that set `maxsize=None`. | always | no | conventions |
| UP034 | extraneous-parentheses | Checks for extraneous parentheses. | always | no | conventions |
| UP035 | deprecated-import | Checks for uses of deprecated imports based on the minimum supported Python version. | sometimes | no | typing |
| UP040 | non-pep695-type-alias | Checks for use of `TypeAlias` annotations and `TypeAliasType` assignments for declaring type aliases. | always | no | typing |
| UP041 | timeout-error-alias | Checks for uses of exceptions that alias `TimeoutError`. | always | no | conventions |
| UP043 | unnecessary-default-type-args | Checks for unnecessary default type arguments for `Generator` and `AsyncGenerator` on Python 3.13+. | always | no | typing |
| UP044 | non-pep646-unpack | Checks for uses of `Unpack[]` on Python 3.11 and above, and suggests using `*` instead. | always | no | typing |
| UP045 | non-pep604-annotation-optional | Check for `typing.Optional` annotations that can be rewritten based on [PEP 604] syntax. | sometimes | no | typing |
| UP046 | non-pep695-generic-class | Checks for use of standalone type variables and parameter specifications in generic classes. | sometimes | no | typing |
| UP047 | non-pep695-generic-function | Checks for use of standalone type variables and parameter specifications in generic functions. | always | no | typing |
| UP049 | private-type-parameter | Checks for use of [PEP 695] type parameters with leading underscores in generic classes and functions. | sometimes | no | conventions |

## Rules left off

The card does not run the 64 scope rules below, though its rule families named
each of them before it took its rules from its disciplines. 47 sit in
unplaced.json, 3 are housed only by a discipline the card does not name, and 14
are preview rules the house holds no row for. The card's left setting names
every one with its full text.

`dev_harness/sigils/construct_rules.py, in why_left`, the reason each rule left:

```python
def why_left(tool: str, rule: str, named: Sequence[str]) -> str | None:
    """Return why no `named` discipline houses `tool` rule `rule`, or None when one does."""
    housed_by = _housed().get((tool, rule), ())
    if set(housed_by) & set(named):
        return None
    if housed_by:
        return NOT_NAMED.format(housing=", ".join(housed_by))
    return _unplaced().get((tool, rule), UNHOUSED)
```

| Rule | Reason |
| ---- | ------ |
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
| C415 | No discipline houses it. |
| C416 | No discipline houses it. |
| C418 | No discipline houses it. |
| FURB105 | No discipline houses it. |
| FURB110 | No discipline houses it. |
| FURB113 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB118 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB122 | No discipline houses it. |
| FURB131 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB132 | No discipline houses it. |
| FURB142 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB145 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB148 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB152 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB154 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB156 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB162 | No discipline houses it. |
| FURB163 | No discipline houses it. |
| FURB164 | No discipline houses it. |
| FURB166 | No discipline houses it. |
| FURB180 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| FURB189 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| PLR1702 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| PLR1704 | No discipline houses it. |
| PLR1708 | Housed by reliability, which the card does not name. |
| PLR1711 | No discipline houses it. |
| PLR1712 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
| PLR1722 | Housed by reliability, which the card does not name. |
| SIM101 | No discipline houses it. |
| SIM103 | No discipline houses it. |
| SIM105 | No discipline houses it. |
| SIM108 | No discipline houses it. |
| SIM109 | No discipline houses it. |
| SIM112 | No discipline houses it. |
| SIM114 | No discipline houses it. |
| SIM401 | No discipline houses it. |
| SIM910 | No discipline houses it. |
| UP001 | No discipline houses it. |
| UP004 | No discipline houses it. |
| UP005 | Housed by security, which the card does not name. |
| UP010 | No discipline houses it. |
| UP011 | No discipline houses it. |
| UP012 | No discipline houses it. |
| UP015 | No discipline houses it. |
| UP020 | No discipline houses it. |
| UP025 | No discipline houses it. |
| UP026 | No discipline houses it. |
| UP029 | No discipline houses it. |
| UP036 | No discipline houses it. |
| UP037 | No discipline houses it. |
| UP039 | No discipline houses it. |
| UP042 | No discipline houses it. |
| UP050 | No discipline houses it. |
| UP051 | No discipline houses it, and neither the archetype nor a sigil runs this preview rule, so the house holds no row for it. |
