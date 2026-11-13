# CODE.VARIABLE@1

Reference. CODE.VARIABLE@1 reads the names, assignments and function arguments
in one Python file against 54 ruff rules. The Coding Archetype owns it. It is
one sigil of [the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the 54 rules on the card. Five of them are preview rules, so ruff runs
with preview rules on. The file goes to ruff on standard input, from the folder
of the file. For a function or class, only the findings inside its lines count.

For each rule that fires, ruff's own rule page gives the rule's name, its fix
class, and its published faulty and corrected forms. The card records ruff
0.16.0, and the command prints the ruff version it ran.

`dev_harness/sigils/code_variable.py, in _ruff_findings`:

```python
def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    rows = check(source, folder, RULES, preview=bool(PREVIEW))
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

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms.
FINDINGS reads HOLD only when the file sits in application source and PLE0118,
PLE0237 or PLE0605 fires. These are the pylint error rules for a name used
before its global statement, an assignment to an attribute that the class slots
do not list, and an export list that is not a list or a tuple. Every other
finding reads FIX, and the merge proceeds.

F821 and F823 are the pyflakes rules for an undefined name and an undefined
local. The card lists both in its undefined_names setting, as rules that would
hold a merge. Both are left off the card, so neither can fire.

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
| ASYNC230 | blocking-open-call-in-async-function | Checks that async functions do not open files with blocking methods like `open`. | none | no |
| ASYNC250 | blocking-input-in-async-function | Checks that async functions do not contain blocking usage of input from user. | none | no |
| BLE001 | blind-except | Checks for `except` clauses that catch all exceptions.  This includes `except BaseException` and `except Exception`. | none | no |
| B003 | assignment-to-os-environ | Checks for assignments to `os.environ`. | none | no |
| B007 | unused-loop-control-variable | Checks for unused variables in loops (e.g., `for` and `while` statements). | sometimes | no |
| B020 | loop-variable-overrides-iterator | Checks for loop control variables that override the loop iterable. | none | no |
| B023 | function-uses-loop-variable | Checks for function definitions that use a loop variable. | none | no |
| B031 | reuse-of-groupby-generator | Checks for multiple usage of the generator returned from `itertools.groupby()`. | none | no |
| A001 | builtin-variable-shadowing | Checks for variable (and function) assignments that use the same names as builtins. | none | no |
| A002 | builtin-argument-shadowing | Checks for function arguments that use the same names as builtins. | none | no |
| LOG002 | invalid-get-logger-argument | Checks for any usage of `__cached__` and `__file__` as an argument to `logging.getLogger()`. | sometimes | no |
| PIE794 | duplicate-class-field-definition | Checks for duplicate field definitions in classes. | always | no |
| PIE796 | non-unique-enums | Checks for enums that contain duplicate values. | none | no |
| RET504 | unnecessary-assign | Checks for variable assignments that immediately precede a `return` of the assigned variable. | always | no |
| SIM113 | enumerate-for-loop | Checks for `for` loops with explicit loop-index variables that can be replaced with `enumerate()`. | none | no |
| SIM115 | open-file-with-context-handler | Checks for cases where files are opened (e.g., using the builtin `open()` function) without using a context manager. | none | no |
| N806 | non-lowercase-variable-in-function | Checks for the use of non-lowercase variable names in functions. | none | no |
| N815 | mixed-case-variable-in-class-scope | Checks for class variable names that follow the `mixedCase` convention. | none | no |
| N816 | mixed-case-variable-in-global-scope | Checks for global variable names that follow the `mixedCase` convention. | none | no |
| PERF403 | manual-dict-comprehension | Checks for `for` loops that can be replaced by a dictionary comprehension. | sometimes | no |
| E731 | lambda-assignment | Checks for lambda expressions which are assigned to a variable. | sometimes | no |
| E741 | ambiguous-variable-name | Checks for the use of the characters 'l', 'O', or 'I' as variable names. | none | no |
| F405 | undefined-local-with-import-star-usage | Checks for names that might be undefined, but may also be defined in a wildcard import. | none | no |
| F602 | multi-value-repeated-key-variable | Checks for dictionary keys that are repeated with different values. | sometimes | no |
| F841 | unused-variable | Checks for the presence of unused variables in function scopes. | sometimes | no |
| F901 | raise-not-implemented | Checks for `raise` statements that raise `NotImplemented`. | sometimes | no |
| PLC0105 | type-name-incorrect-variance | Checks for type names that do not match the variance of their associated type parameter. | none | no |
| PLC0131 | type-bivariance | Checks for `TypeVar` and `ParamSpec` definitions in which the type is both covariant and contravariant. | none | no |
| PLC0205 | single-string-slots | Checks for single strings assigned to `__slots__`. | none | no |
| PLC2401 | non-ascii-name | Checks for the use of non-ASCII characters in variable names. | none | no |
| PLE0118 | load-before-global-declaration | Checks for uses of names that are declared as `global` prior to the relevant `global` declaration. | none | no |
| PLE0237 | non-slot-assignment | Checks for assignments to attributes that are not defined in `__slots__`. | none | no |
| PLE0605 | invalid-all-format | Checks for invalid assignments to `__all__`. | none | no |
| PLR1704 | redefined-argument-from-local | Checks for variables defined in `for`, `try`, `with` statements that redefine function parameters. | none | no |
| PLR6104 | non-augmented-assignment | Checks for assignments that can be replaced with augmented assignment statements. | always | yes |
| PLW0127 | self-assigning-variable | Checks for self-assignment of variables. | none | no |
| PLW0128 | redeclared-assigned-name | Checks for declared assignments to the same variable multiple times in the same assignment. | none | no |
| PLW0131 | named-expr-without-context | Checks for uses of named expressions (e.g., `a := 42`) that can be replaced by regular assignment statements (e.g., `a = 42`). | none | no |
| PLW0602 | global-variable-not-assigned | Checks for `global` variables that are not assigned a value in the current scope. | none | no |
| PLW0603 | global-statement | Checks for the use of `global` statements to update identifiers. | none | no |
| PLW0642 | self-or-cls-assignment | Checks for assignment of `self` and `cls` in instance and class methods respectively. | none | no |
| UP001 | useless-metaclass-type | Checks for the use of `__metaclass__ = type` in class definitions. | always | no |
| UP006 | non-pep585-annotation | Checks for the use of generics that can be replaced with standard library variants based on [PEP 585]. | sometimes | no |
| UP013 | convert-typed-dict-functional-to-class | Checks for `TypedDict` declarations that use functional syntax. | sometimes | no |
| UP014 | convert-named-tuple-functional-to-class | Checks for `NamedTuple` declarations that use functional syntax. | sometimes | no |
| UP019 | typing-text-str-alias | Checks for uses of `typing.Text` and `typing_extensions.Text`. | sometimes | no |
| FURB148 | unnecessary-enumerate | Checks for uses of `enumerate` that discard either the index or the value when iterating over a sequence. | sometimes | yes |
| FURB187 | list-reverse-copy | Checks for list reversals that can be performed in-place in lieu of creating a new list. | always | no |
| FURB189 | subclass-builtin | Checks for subclasses of `dict`, `list` or `str`. | always | yes |
| RUF007 | zip-instead-of-pairwise | Checks for use of `zip()` to iterate over successive pairs of elements. | sometimes | no |
| RUF052 | used-dummy-variable | Checks for "dummy variables" (variables that are named as if to indicate they are unused) that are in fact used. | sometimes | yes |
| RUF059 | unused-unpacked-variable | Checks for the presence of unused variables in unpacked assignments. | sometimes | no |
| RUF070 | unnecessary-assign-before-yield | Checks for variable assignments that immediately precede a `yield` (or `yield from`) of the assigned variable, where the variable is not referenced anywhere else. | always | yes |
| TRY401 | verbose-log-message | Checks for excessive logging of exception objects. | none | no |

## Rules left off

The card leaves 35 of the 89 variable rules off. A reason that starts with
faulty or corrected names the sample. A tool and its finding mean the write
gate refused that sample, because the coding archetype grades the finding high.
Reads names what ruff reads on that published form. Refused at tier 2 means the
published faulty form holds no binding that tier 2 accepts, so the sigil cannot
read it. The reason column is the card's own text.

Fourteen reasons name vulture. In thirteen of them, the published form leaves a
function argument unused, and the coding archetype grades an unused argument
high.

| Rule | ruff name | Reason on the card |
| ---- | --------- | ------------------ |
| ANN001 | missing-type-function-argument | faulty: vulture unused variable 'x' |
| ANN401 | any-type | faulty: vulture unused variable 'x' |
| S509 | snmp-weak-cryptography | faulty: refused at tier 2, the published form holds no binding |
| B025 | duplicate-try-block-exception | faulty: refused at tier 2, the published form holds no binding |
| B032 | unintentional-type-annotation | faulty: mypy valid-type and pyright reportInvalidTypeForm |
| ARG001 | unused-function-argument | faulty: vulture unused variable 'baz' |
| ARG002 | unused-method-argument | faulty: vulture unused variable 'arg2' |
| ARG003 | unused-class-method-argument | faulty: vulture unused variable 'cls' and 'arg2' |
| ARG004 | unused-static-method-argument | faulty: vulture unused variable 'arg2' |
| ARG005 | unused-lambda-argument | faulty: vulture unused variable 'y' |
| PTH123 | builtin-open | faulty: refused at tier 2, the published form holds no binding |
| N803 | invalid-argument-name | faulty: vulture unused variable 'A' and 'myArg' |
| N804 | invalid-first-argument-name-for-class-method | faulty: vulture unused variable 'data' |
| N805 | invalid-first-argument-name-for-method | faulty: vulture unused variable 'cls' and 'data' |
| F402 | import-shadowed-by-loop-var | corrected: vulture unused import 'path' |
| F633 | invalid-print-syntax | faulty: refused at tier 2, the published form holds no binding |
| F821 | undefined-name | faulty: refused at tier 2, the published form holds no binding |
| F823 | undefined-local | faulty: pyright reportUnboundVariable, 'x' is unbound |
| PLE0115 | nonlocal-and-global | faulty: pyright, 'counter' declared global and nonlocal |
| PLE0117 | nonlocal-without-binding | faulty: pyright reportUndefinedVariable and no binding for nonlocal 'bar' |
| PLE0241 | duplicate-bases | faulty: refused at tier 2, the published form holds no binding |
| PLE0604 | invalid-all-object | faulty: mypy list-item, list items 1 and 2 |
| PLE1141 | dict-iter-missing-items | faulty: mypy str-unpack, unpacking a string |
| PLR1722 | sys-exit-alias | faulty: refused at tier 2, the published form holds no binding |
| PLW0211 | bad-staticmethod-argument | corrected: vulture unused variable 'sheep' |
| PLW0245 | super-without-brackets | faulty: pyright reportIncompatibleMethodOverride, method 'speak' |
| PLW1514 | unspecified-encoding | faulty: refused at tier 2, the published form holds no binding |
| UP004 | useless-object-inheritance | faulty: refused at tier 2, the published form holds no binding |
| UP024 | os-error-alias | faulty: refused at tier 2, the published form holds no binding |
| UP037 | quoted-annotation | corrected: reads UP037 |
| RUF013 | implicit-optional | faulty: vulture unused variable 'arg' |
| RUF018 | assignment-in-assert | corrected: reads RUF018 |
| RUF020 | never-union | faulty: refused at tier 2, the published form holds no binding |
| RUF036 | none-not-at-end-of-union | faulty: vulture unused variable 'arg' |
| TRY201 | verbose-raise | faulty: refused at tier 2, the published form holds no binding |
