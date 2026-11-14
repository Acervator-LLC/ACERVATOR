# CODE.TYPE@1

Reference. CODE.TYPE@1 reads one Python file with two type checkers, mypy and
pyright. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.TYPE@1 reads each value against the type its annotation, assignment or
call gives it, for a type fault that fails at run time, breaks the typing
standard, or leaves implicit what Python's conventions ask to state. It draws on
three disciplines: conventions, reliability and typing.

Its scope is each code on mypy's own error code list, 78 codes, and each of the
42 pyright rules that the house holds. The card holds each scope rule that one
of its disciplines houses, so it can run 62 rules: 33 mypy codes and 29 pyright
rules. [The tool scope](../16-sigil-project.md#the-tool-scope) states how a rule
is held.

`dev_harness/sigils/code_type.py, in MYPY` and `in PYRIGHT`:

```python
DISCIPLINES = ("conventions", "reliability", "typing")
MYPY = hold("mypy", sorted(mypy.errorcodes.error_codes), DISCIPLINES)
PYRIGHT = hold("pyright", house_rules("pyright"), DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs both type checkers from the root of
the target tree, with the settings each tool finds there. Only errors count,
and only those in the input file. For a function or class, only the errors
inside its lines count.

An error counts only under a rule the card holds. An error under any other
code, or with no code, moves no verdict.

A plugin or interpreter that the tree's own mypy or pyright settings name runs
as code. Each tool finds imports from the root of the target tree and from the
installed packages, never from the tree's own list of files to check.

`dev_harness/sigils/code_type.py, in _mypy_findings`:

```python
def _mypy_findings(path: str, root: Path, file: Path) -> list[Finding]:
    """Return each mypy error in `file`, run on `path` from `root` with no cache."""
    with contextlib.chdir(root):
        stdout, stderr, status = mypy.api.run(
            ["--output", "json", "--cache-dir", os.devnull, path]
        )
    if status not in MYPY_FINISHED:
        raise ToolFault(f"mypy exited {status}: {tool_text(stderr or stdout)}")
    try:
        rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        return [
            Finding("mypy", row["code"] or NO_CODE, row["line"])
            for row in rows
            if row["severity"] == "error" and _same_file(root / row["file"], file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"mypy printed an unreadable row: {exc}") from exc
```

`dev_harness/sigils/code_type.py, in _functions_verdict`, the errors that count:

```python
    findings = [
        finding
        for finding in [*_mypy_findings(path, root, file), *pyright_found]
        if finding.code in HELD[finding.tool]
        and (not is_narrowed or first <= finding.line <= last)
    ]
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| SOUND | PASS | PASS |
| UNSOUND | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

SOUND means neither tool reports an error under a rule the card holds. UNSOUND
carries, for each error, the tool, its error code and the line. UNSOUND reads
HOLD when the file the input line names sits in application source. Anywhere
else it reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_type/`. The sample tree holds the published
examples of six mypy error codes: arg-type, return-value, attr-defined,
union-attr, call-arg and index.

```
python -m dev_harness.sigils.code_type <file>
python -m dev_harness.sigils.code_type --root <folder> <file>
python -m dev_harness.sigils.code_type --gate <file>
python -m dev_harness.sigils.code_type --card
```

## Tools and rules

The card names two tools, and each error either tool reports in the input file
under a rule the card holds is an output. One row per tool, from the card's
settings and tier 3. The command prints the versions it ran.

| Tool | Version on the card | How the card runs it | What counts |
| ---- | ------------------- | -------------------- | ----------- |
| mypy | 2.1.0 | `mypy.api.run` from the root of the target tree, with `--output json` and the null device as its cache folder | each error in the input file under one of the 33 mypy codes the card can run |
| pyright | 1.1.411 | `pyright.run` from the root of the target tree, with `--outputjson` | each error in the input file under one of the 29 pyright rules the card can run |

## Rules

The card can run the 62 rules below. The last column names each discipline
that houses the rule, from the rules.json files under `dev_harness/disciplines/`.

`dev_harness/sigils/code_type.py, in SETTINGS`: the card prints them as
mypy_rules and pyright_rules.

| Rule | Tool | Housed by |
| ---- | ---- | --------- |
| abstract | mypy | typing |
| arg-type | mypy | typing |
| assert-type | mypy | typing |
| assignment | mypy | typing |
| attr-defined | mypy | typing |
| call-arg | mypy | typing |
| call-overload | mypy | typing |
| dict-item | mypy | typing |
| has-type | mypy | conventions |
| import-untyped | mypy | typing |
| index | mypy | reliability |
| list-item | mypy | typing |
| literal-required | mypy | typing |
| metaclass | mypy | reliability |
| method-assign | mypy | conventions |
| name-defined | mypy | reliability, security |
| narrowed-type-not-subtype | mypy | typing |
| no-any-return | mypy | typing |
| no-overload-impl | mypy | typing |
| no-untyped-def | mypy | typing |
| operator | mypy | reliability |
| return | mypy | conventions |
| return-value | mypy | typing |
| str-bytes-safe | mypy | conventions |
| type-var | mypy | typing |
| typeddict-item | mypy | typing |
| typeddict-readonly-mutated | mypy | typing |
| typeddict-unknown-key | mypy | typing |
| union-attr | mypy | typing |
| unused-coroutine | mypy | reliability, security |
| used-before-def | mypy | reliability, security |
| valid-newtype | mypy | typing |
| var-annotated | mypy | conventions |
| reportAbstractUsage | pyright | typing |
| reportArgumentType | pyright | typing |
| reportAssertTypeFailure | pyright | typing |
| reportAssignmentType | pyright | typing |
| reportAttributeAccessIssue | pyright | typing |
| reportCallIssue | pyright | typing |
| reportInconsistentOverload | pyright | typing |
| reportIndexIssue | pyright | reliability |
| reportInvalidStringEscapeSequence | pyright | reliability |
| reportInvalidTypeVarUse | pyright | typing |
| reportNoOverloadImplementation | pyright | typing |
| reportOperatorIssue | pyright | reliability |
| reportOptionalCall | pyright | reliability |
| reportOptionalContextManager | pyright | reliability |
| reportOptionalIterable | pyright | reliability |
| reportOptionalMemberAccess | pyright | reliability |
| reportOptionalOperand | pyright | reliability |
| reportOptionalSubscript | pyright | reliability |
| reportPossiblyUnboundVariable | pyright | reliability, security |
| reportPrivateImportUsage | pyright | typing |
| reportReturnType | pyright | typing |
| reportSelfClsParameterName | pyright | conventions |
| reportTypedDictNotRequiredAccess | pyright | reliability |
| reportUnboundVariable | pyright | reliability, security |
| reportUndefinedVariable | pyright | reliability, security |
| reportUnhashable | pyright | reliability |
| reportUnsupportedDunderAll | pyright | reliability |
| reportUnusedCoroutine | pyright | reliability, security |
| reportWildcardImportFromLibrary | pyright | conventions |

## Rules left off

The card does not run the 58 scope rules below, though it read every error
under them before it took its rules from its disciplines. An error under one of
them moves no verdict. Each reason comes from the six disciplines and
unplaced.json, and the card's left setting names every one with its full text.

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

| Rule | Tool | Reason |
| ---- | ---- | ------ |
| annotation-unchecked | mypy | No discipline houses it. |
| await-not-async | mypy | No discipline houses it. |
| comparison-overlap | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| deprecated | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| empty-body | mypy | No discipline houses it. |
| exhaustive-match | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| exit-return | mypy | No discipline houses it. |
| explicit-any | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| explicit-override | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| func-returns-value | mypy | No discipline houses it. |
| ignore-without-code | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| import | mypy | No discipline houses it. |
| import-not-found | mypy | No discipline houses it. |
| maybe-unrecognized-str-typeform | mypy | No discipline houses it. |
| misc | mypy | No discipline houses it. |
| mutable-override | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| name-match | mypy | No discipline houses it. |
| no-any-unimported | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| no-redef | mypy | No discipline houses it. |
| no-untyped-call | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| nonetype-type | mypy | No discipline houses it. |
| overload-cannot-match | mypy | No discipline houses it. |
| overload-overlap | mypy | No discipline houses it. |
| override | mypy | No discipline houses it. |
| possibly-undefined | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| prop-decorator | mypy | No discipline houses it. |
| redundant-cast | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| redundant-expr | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| redundant-self | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| safe-super | mypy | No discipline houses it. |
| str-format | mypy | No discipline houses it. |
| str-unpack | mypy | No discipline houses it. |
| syntax | mypy | No discipline houses it. |
| top-level-await | mypy | No discipline houses it. |
| truthy-bool | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| truthy-function | mypy | Housed by maintainability, security, which the card does not name. |
| truthy-iterable | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| type-abstract | mypy | No discipline houses it. |
| type-arg | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unimported-reveal | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unreachable | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| untyped-decorator | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unused-awaitable | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unused-ignore | mypy | No discipline houses it. |
| valid-type | mypy | No discipline houses it. |
| reportAssertAlwaysTrue | pyright | Housed by maintainability, security, which the card does not name. |
| reportFunctionMemberAccess | pyright | No discipline houses it. |
| reportGeneralTypeIssues | pyright | No discipline houses it. |
| reportIncompatibleMethodOverride | pyright | No discipline houses it. |
| reportIncompatibleVariableOverride | pyright | No discipline houses it. |
| reportInvalidTypeArguments | pyright | No discipline houses it. |
| reportInvalidTypeForm | pyright | No discipline houses it. |
| reportMissingImports | pyright | No discipline houses it. |
| reportMissingModuleSource | pyright | No discipline houses it. |
| reportOverlappingOverload | pyright | No discipline houses it. |
| reportRedeclaration | pyright | No discipline houses it. |
| reportUnusedExcept | pyright | Housed by maintainability, which the card does not name. |
| reportUnusedExpression | pyright | No discipline houses it. |
