# CODE.VARIABLE@1

Reference. CODE.VARIABLE@1 reads the names, assignments and function arguments
in one Python file against the 38 ruff rules it can run. The Coding Archetype owns it. It is
one sigil of [the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.VARIABLE@1 reads each binding, from an assignment to a function argument,
for a name that is wrong, unsafe, wasteful, untyped, or against Python's naming
conventions. It draws on five disciplines: conventions, performance efficiency,
reliability, security and typing.

The card holds no rule list of its own. It takes each ruff rule that the
construct scope places on the variable construct and that one of its disciplines
houses. [The construct scope](../16-sigil-project.md#the-construct-scope)
states how a rule is placed.

`dev_harness/sigils/code_variable.py, in TAKEN`:

```python
DISCIPLINES = (
    "conventions",
    "performance-efficiency",
    "reliability",
    "security",
    "typing",
)
TAKEN = take("variable", DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the selected rules of the 38 the card can run. No rule on the list is a preview rule, so
ruff runs with preview rules off. The file goes to ruff on standard input, from the folder
of the file. For a function or class, only the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_variable.py, in _ruff_findings`:

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

Tier 2 accepts an input only when Python's ast module finds a binding in the
input's lines: an assignment, an annotated or augmented assignment, a named
expression, a function argument, or a global or nonlocal statement. An input
that holds none is refused at tier 2.

`dev_harness/sigils/code_variable.py, in _content_fault`:

```python
def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_BINDING`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_binding = any(
        isinstance(node, BINDING_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_binding else NO_BINDING
```

## The selection

For each input, CODE.VARIABLE@1 runs only those of its 38 rules that the run
rule selects for the input's facts. A rule whose subject the input lacks does
not run, and an input that selects no rule runs no ruff.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_variable.py, in _functions_verdict`:

```python
    version, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_variable.py, in findings`, the rules ruff gets:

```python
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 491 | 38 | 16 | 33 | 35 | 5,792 | 5,792 |
| def or class | 13,313 | 38 | 12 | 32 | 35 | 8,625 | 8,625 |

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms.
FINDINGS reads HOLD only when the file sits in application source and PLE0117,
PLE0237, PLE0604, PLE0605 or F823 fires. The four pylint error rules are for a
nonlocal name with no binding, an assignment to an attribute that the class
slots do not list, an export list holding something other than a string, and
an export list that is not a list or a tuple. Every other
finding reads FIX, and the merge proceeds.

F821, F822 and F823 are the pyflakes rules for an undefined name, an undefined
export and an undefined local. The card lists all three in its undefined_names
setting, as rules that hold a merge. F823 is on the card, so it can fire.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_variable/`.

```
python -m dev_harness.sigils.code_variable <file>
python -m dev_harness.sigils.code_variable --root <folder> <file>
python -m dev_harness.sigils.code_variable --gate <file>
python -m dev_harness.sigils.code_variable --card
```

## Rules

Each line comes from `python -m ruff rule <code>` for ruff 0.16.0. The fix
column is the fix class ruff states. A preview rule fires only with preview
rules on.

| Rule | ruff name | What it catches | Fix | Preview |
| ---- | --------- | --------------- | --- | ------- |
| A001 | builtin-variable-shadowing | Checks for variable (and function) assignments that use the same names as builtins. | none | no |
| A002 | builtin-argument-shadowing | Checks for function arguments that use the same names as builtins. | none | no |
| ANN001 | missing-type-function-argument | Checks that function arguments have type annotations. | none | no |
| ANN401 | any-type | Checks that function arguments are annotated with a more specific type than `Any`. | none | no |
| ASYNC109 | async-function-with-timeout | Checks for `async` function definitions with `timeout` parameters. | none | no |
| DJ006 | django-exclude-with-model-form | Checks for the use of `exclude` in Django `ModelForm` classes. | none | no |
| DJ007 | django-all-with-model-form | Checks for the use of `fields = "__all__"` in Django `ModelForm` classes. | none | no |
| DJ012 | django-unordered-body-content-in-model | Checks for the order of Model's inner classes, methods, and fields as per the [Django Style Guide]. | none | no |
| E731 | lambda-assignment | Checks for lambda expressions which are assigned to a variable. | sometimes | no |
| E741 | ambiguous-variable-name | Checks for the use of the characters 'l', 'O', or 'I' as variable names. | none | no |
| F823 | undefined-local | Checks for undefined local variables. | none | no |
| FURB187 | list-reverse-copy | Checks for list reversals that can be performed in-place in lieu of creating a new list. | always | no |
| N803 | invalid-argument-name | Checks for argument names that do not follow the `snake_case` convention. | none | no |
| N804 | invalid-first-argument-name-for-class-method | Checks for class methods that use a name other than `cls` for their first argument. | sometimes | no |
| N805 | invalid-first-argument-name-for-method | Checks for instance methods that use a name other than `self` for their first argument. | sometimes | no |
| N806 | non-lowercase-variable-in-function | Checks for the use of non-lowercase variable names in functions. | none | no |
| N815 | mixed-case-variable-in-class-scope | Checks for class variable names that follow the `mixedCase` convention. | none | no |
| N816 | mixed-case-variable-in-global-scope | Checks for global variable names that follow the `mixedCase` convention. | none | no |
| PERF403 | manual-dict-comprehension | Checks for `for` loops that can be replaced by a dictionary comprehension. | sometimes | no |
| PLC2401 | non-ascii-name | Checks for the use of non-ASCII characters in variable names. | none | no |
| PLE0117 | nonlocal-without-binding | Checks for `nonlocal` names without bindings. | none | no |
| PLE0237 | non-slot-assignment | Checks for assignments to attributes that are not defined in `__slots__`. | none | no |
| PLE0604 | invalid-all-object | Checks for the inclusion of invalid objects in `__all__`. | none | no |
| PLE0605 | invalid-all-format | Checks for invalid assignments to `__all__`. | none | no |
| PLW0642 | self-or-cls-assignment | Checks for assignment of `self` and `cls` in instance and class methods respectively. | none | no |
| PT019 | pytest-fixture-param-without-value | Checks for `pytest` test functions that should be decorated with `@pytest.mark.usefixtures`. | none | no |
| PYI032 | any-eq-ne-annotation | Checks for `__eq__` and `__ne__` implementations that use `typing.Any` as the type annotation for their second parameter. | always | no |
| PYI041 | redundant-numeric-union | Checks for parameter annotations that contain redundant unions between builtin numeric types (e.g., `int \| float`). | sometimes | no |
| PYI063 | pep484-style-positional-only-parameter | Checks for the presence of [PEP 484]-style positional-only parameters. | none | no |
| PYI064 | redundant-final-literal | Checks for redundant `Final[Literal[...]]` annotations. | sometimes | no |
| RUF013 | implicit-optional | Checks for the use of implicit `Optional` in type annotations when the default parameter value is `None`. | sometimes | no |
| RUF036 | none-not-at-end-of-union | Checks for type annotations where `None` is not at the end of a union. | sometimes | no |
| RUF059 | unused-unpacked-variable | Checks for the presence of unused variables in unpacked assignments. | sometimes | no |
| SIM113 | enumerate-for-loop | Checks for `for` loops with explicit loop-index variables that can be replaced with `enumerate()`. | none | no |
| UP013 | convert-typed-dict-functional-to-class | Checks for `TypedDict` declarations that use functional syntax. | sometimes | no |
| UP014 | convert-named-tuple-functional-to-class | Checks for `NamedTuple` declarations that use functional syntax. | sometimes | no |
| UP040 | non-pep695-type-alias | Checks for use of `TypeAlias` annotations and `TypeAliasType` assignments for declaring type aliases. | always | no |
| UP044 | non-pep646-unpack | Checks for uses of `Unpack[]` on Python 3.11 and above, and suggests using `*` instead. | always | no |

## Rules left off

The card does not run the rules below, though its own rule list once named
them. Each reason comes from the construct scope and the six disciplines. The
card's left setting names every rule on the variable construct that no discipline
houses, with its unplaced.json text.

| Rule | Reason |
| ---- | ------ |
| ASYNC230 | Its finding sits on a part of the withitem that no construct owns. |
| ASYNC250 | Its finding sits on a part of the Assign that no construct owns. |
| BLE001 | Its finding sits on a part of the ExceptHandler that no construct owns. |
| B003 | No discipline houses it. |
| B007 | Its finding sits on the loop construct, so CODE.LOOP runs it. |
| B020 | Its finding sits on the loop construct, and no discipline houses it. |
| B023 | The climb from its finding reaches the Lambda before any construct. |
| B031 | Its finding sits on the loop construct, so CODE.LOOP runs it. |
| LOG002 | Its finding sits on a part of the Assign that no construct owns. |
| PIE794 | No discipline houses it. |
| PIE796 | No discipline houses it. |
| RET504 | Its finding sits on a part of the Return that no construct owns. |
| SIM115 | Its finding sits on a part of the Assign that no construct owns. |
| F405 | Its finding sits on a part of the Return that no construct owns. |
| F602 | Its finding sits on the collection construct, and no discipline houses it. |
| F841 | No discipline houses it. |
| F901 | Its finding sits on a part of the Raise that no construct owns. |
| PLC0105 | Its finding sits on a part of the Assign that no construct owns. |
| PLC0131 | Its finding sits on a part of the Assign that no construct owns. |
| PLC0205 | No discipline houses it. |
| PLE0118 | The climb from its finding reaches the FunctionDef before any construct. |
| PLR1704 | Its finding sits on the loop construct, and no discipline houses it. |
| PLR6104 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
| PLW0127 | No discipline houses it. |
| PLW0128 | No discipline houses it. |
| PLW0131 | No discipline houses it. |
| PLW0602 | No discipline houses it. |
| PLW0603 | No discipline houses it. |
| UP001 | No discipline houses it. |
| UP006 | Its finding sits on a part of the AnnAssign that no construct owns. |
| UP019 | Its finding sits on a part of the AnnAssign that no construct owns. |
| FURB148 | Its finding sits on the loop construct, and no discipline houses it. |
| FURB189 | The climb from its finding reaches the ClassDef before any construct. |
| RUF007 | The climb from its finding reaches the Module before any construct. |
| RUF052 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
| RUF070 | The climb from its finding reaches the FunctionDef before any construct. |
| TRY401 | Its finding sits on the flow construct, and no discipline houses it. |
