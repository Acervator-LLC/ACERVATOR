# CODE.TYPE@1

Reference. CODE.TYPE@1 reads one Python file with two type checkers, mypy and
pyright. It also runs one rule of its own, which reads a builtin's value that no
code uses. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.TYPE@1 reads each value against the type its annotation, assignment or
call gives it, for a type fault that fails at run time, breaks the typing
standard, or leaves implicit what Python's conventions ask to state, or for a
builtin's value that no code reads. It draws on the Python discipline, under
three characteristics: conventions, reliability and typing.

Its scope is each code on mypy's own error code list, 78 codes, each of the 42
pyright rules that the house holds, and the one rule it runs itself. The card
holds each scope rule that the Python discipline houses under one of its
characteristics, so it can run 63
rules: 33 mypy codes, 29 pyright rules and its own rule.
[The tool scope](../16-sigil-project.md#the-tool-scope) states how a rule is
held.

`dev_harness/sigils/code_type.py, in MYPY` and `in PYRIGHT`:

```python
DISCIPLINES = ("python",)
CHARACTERISTICS = ("conventions", "reliability", "typing")
MYPY = hold("mypy", sorted(mypy.errorcodes.error_codes), DISCIPLINES, CHARACTERISTICS)
PYRIGHT = hold("pyright", house_rules("pyright"), DISCIPLINES, CHARACTERISTICS)
```

The card holds its own rule the same way. A discipline must house it, or it
leaves the card with its reason.

`dev_harness/sigils/code_type.py, in OWN` and `in CAN_RUN`:

```python
OWN = hold(OWN_TOOL, (UNUSED_RESULT,), DISCIPLINES, CHARACTERISTICS)
CAN_RUN = tuple(
    f"{held.tool} {rule}" for held in (MYPY, PYRIGHT, OWN) for rule in held.rules
)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs each type checker whose rules the selection keeps from the root of
the target tree, with the settings each tool finds there. Only mypy errors,
pyright errors and warnings, and the findings of its own rule count, and only
those in the input file. For a function or class, only the findings inside its
lines count.

An error counts only under a rule the card holds and the selection keeps. An error under any other
code, or with no code, moves no verdict.

A plugin or interpreter that the tree's own mypy or pyright settings name runs
as code. Each tool finds imports from the root of the target tree and from the
installed packages, never from the tree's own list of files to check.

`dev_harness/sigils/code_type.py, in _mypy_findings`:

```python
def _mypy_findings(
    path: str, root: Path, file: Path, disabled: tuple[str, ...]
) -> list[Finding]:
    """Return each mypy error in `file`, run on `path` from `root` with no cache and no `disabled` code run."""
    argv = [sys.executable, "-P", "-m", "mypy", "--output", "json", "--cache-dir", os.devnull]
    try:
        proc = subprocess.run(
            [*argv, *_code_flags(disabled), path],
            cwd=root,
            capture_output=True,
            timeout=MYPY_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolFault(f"mypy: {exc}") from exc
    if proc.returncode not in MYPY_FINISHED:
        said = tool_text(proc.stderr or proc.stdout)
        raise ToolFault(f"mypy exited {proc.returncode}: {said}")
    try:
        lines = tool_text(proc.stdout).splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        return [
            Finding("mypy", row["code"] or NO_CODE, row["line"])
            for row in rows
            if row["severity"] == "error" and _same_file(root / row["file"], file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"mypy printed an unreadable row: {exc}") from exc
```

`dev_harness/sigils/code_type.py, in findings`, the errors that count:

```python
    kept = [
        finding
        for finding in errors
        if f"{finding.tool} {finding.code}" in to_run
        and (not is_narrowed or first <= finding.line <= last)
    ]
```

## The levels that count

Pyright gives each finding a level: error, warning or information. CODE.TYPE@1
reports a pyright finding at error or at warning. It does not report a finding
at information.

`dev_harness/sigils/code_type.py, in PYRIGHT_SEVERITIES`:

```python
PYRIGHT_SEVERITIES = ("error", "warning")
```

`dev_harness/sigils/code_type.py, in _pyright_findings`, the rows that count:

```python
            for diagnostic in report["generalDiagnostics"]
            if diagnostic["severity"] in PYRIGHT_SEVERITIES
            and _same_file(Path(diagnostic["file"]), file)
```

The house reads the standard column of pyright's Diagnostic Settings Defaults
table. That column turns 34 of the 42 house rules on at error and 8 at warning.
The card holds five of the eight, and pyright gives each of them at warning:

```text
reportInvalidStringEscapeSequence
reportInvalidTypeVarUse
reportSelfClsParameterName
reportUnsupportedDunderAll
reportWildcardImportFromLibrary
```

Mypy gives each row as an error or a note. A note is not a rule finding, so
CODE.TYPE@1 reports only mypy errors. The `_mypy_findings` block above keeps
only the rows whose severity is "error".

## The rule it runs itself

CODE.TYPE@1 runs one rule that this project writes: unused-builtin-result. The
rule reads a statement whose whole value is a call to a builtin, where no code
reads that value. No tool that the Coding Archetype runs reports this shape.
Ruff B018 leaves calls out, by its own rule page. Pyright's
reportUnusedCallResult reads every call that returns a value, and pyright sets
it to none in its basic, standard and strict modes.

The Python discipline houses the rule under reliability, on CWE-252. The rule's row in
`dev_harness/disciplines/python/rules.json` quotes MITRE's description:

```text
CWE-252  The product does not check the return value from a method or function.
```

The rule parses the input's file with Python's ast module. It reports the line
of each expression statement whose value is a call to a name on the list below.
The module must not bind that name, and the statement must not sit in a try body
or a with suite.

`dev_harness/sigils/code_type.py, in _unused_builtin_results`:

```python
def _unused_builtin_results(source: bytes) -> tuple[int, ...]:
    """Return the line of each statement throwing away a `VALUE_ONLY_BUILTINS` call's value, outside a try body or with suite."""
    tree = ast.parse(source)
    bound = _bound_names(tree)
    if bound is None:
        return ()
    names = VALUE_ONLY_BUILTINS - bound
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    return tuple(
        sorted(
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in names
            and not _in_handled_body(node, parents)
        )
    )
```

The Python 3.14 ast documentation names the node the rule reads:

```text
class ast.Expr(value)
When an expression, such as a function call, appears as a statement by itself
with its return value not used or stored, it is wrapped in this container.
```

### The builtins it reads

The Python 3.14 page "Built-in Functions" lists 71 names. The rule reads 34 of
them. Each one returns a value and has no other effect. Some of them call a
special method of their argument. For each such method, the data model in the
Python language reference says that it gives the value the builtin returns. So
a statement that calls one of the 34 alone has no effect except its value, or
the exception the call raises.

`dev_harness/sigils/code_type.py, in VALUE_ONLY_BUILTINS` holds the list.

| Builtin | The page says | Special method it can call |
| ------- | ------------- | -------------------------- |
| abs | "Return the absolute value of a number." | `__abs__` |
| aiter | "Return an asynchronous iterator for an asynchronous iterable." | `__aiter__` |
| ascii | "As repr(), return a string containing a printable representation of an object" | `__repr__` |
| bin | "Convert an integer number to a binary string prefixed with “0b”." | `__index__` |
| bool | "Return a Boolean value, i.e. one of True or False." | `__bool__`, `__len__` |
| callable | "Return True if the object argument appears callable, False if not." | none |
| chr | "Return the string representing a character with the specified Unicode code point." | `__index__` |
| complex | "Convert a single string or number to a complex number, or create a complex number from real and imaginary parts." | `__complex__`, `__float__`, `__index__` |
| divmod | "Take two (non-complex) numbers as arguments and return a pair of numbers consisting of their quotient and remainder when using integer division." | `__divmod__` |
| enumerate | "Return an enumerate object." | `__iter__` |
| filter | "Note that filter(function, iterable) is equivalent to the generator expression (item for item in iterable if function(item))" | `__iter__` |
| float | "Return a floating-point number constructed from a number or a string." | `__float__`, `__index__` |
| format | "Convert a value to a “formatted” representation, as controlled by format_spec." | `__format__` |
| globals | "Return the dictionary implementing the current module namespace." | none |
| hash | "Return the hash value of the object (if it has one)." | `__hash__` |
| hex | "Convert an integer number to a lowercase hexadecimal string prefixed with “0x”." | `__index__` |
| int | "Return an integer object constructed from a number or a string, or return 0 if no arguments are given." | `__int__`, `__index__` |
| isinstance | "Return True if the object argument is an instance of the classinfo argument, or of a (direct, indirect, or virtual) subclass thereof." | `__instancecheck__` |
| issubclass | "Return True if class is a subclass (direct, indirect, or virtual) of classinfo." | `__subclasscheck__` |
| iter | "Return an iterator object." With a sentinel: "The iterator created in this case will call callable with no arguments for each call to its __next__() method" | `__iter__` |
| len | "Return the length (the number of items) of an object." | `__len__` |
| map | "Return an iterator that applies function to every item of iterable, yielding the results." | `__iter__` |
| object | "When the constructor is called, it returns a new featureless object." | none |
| oct | "Convert an integer number to an octal string prefixed with “0o”." | `__index__` |
| ord | "Return the ordinal value of a character." | none |
| pow | "Return base to the power exp; if mod is present, return base to the power exp, modulo mod" | `__pow__` |
| range | "Rather than being a function, range is actually an immutable sequence type" | `__index__` |
| repr | "Return a string containing a printable representation of an object." | `__repr__` |
| reversed | "Return a reverse iterator." | `__reversed__`, `__len__` |
| round | "Return number rounded to ndigits precision after the decimal point." | `__round__` |
| slice | "Return a slice object representing the set of indices specified by range(start, stop, step)." | none |
| str | "Return a str version of object." | `__str__` |
| super | "Return a proxy object that delegates method calls to a parent or sibling class of type." | none |
| zip | "zip() is lazy: The elements won’t be processed until the iterable is iterated on" | `__iter__` |

Each special method in that table, with the words of the data model:

| Special method | The data model says |
| -------------- | ------------------- |
| `__abs__` | "Called to implement the unary arithmetic operations (-, +, abs() and ~)." |
| `__aiter__` | "Must return an asynchronous iterator object." |
| `__bool__` | "Called to implement truth value testing and the built-in operation bool(); should return False or True." |
| `__complex__`, `__int__`, `__float__` | "Called to implement the built-in functions complex(), int() and float(). Should return a value of the appropriate type." |
| `__divmod__`, `__pow__` | "These methods are called to implement the binary arithmetic operations" |
| `__format__` | "Called by the format() built-in function ... to produce a “formatted” string representation of an object." |
| `__hash__` | "The __hash__() method should return an integer." |
| `__index__` | "Called to implement operator.index(), and whenever Python needs to losslessly convert the numeric object to an integer object (such as in slicing, or in the built-in bin(), hex() and oct() functions)." |
| `__instancecheck__` | "Return true if instance should be considered a (direct or indirect) instance of class." |
| `__iter__` | "This method should return a new iterator object that can iterate over all the objects in the container." |
| `__len__` | "Called to implement the built-in function len(). Should return the length of the object, an integer >= 0." |
| `__repr__` | "Called by the repr() built-in function to compute the “official” string representation of an object." |
| `__reversed__` | "It should return a new iterator object that iterates over all the objects in the container in reverse order." |
| `__round__` | "Called to implement the built-in function round() and math functions trunc(), floor() and ceil()." |
| `__str__` | "Called by str(object) ... to compute the “informal” or nicely printable string representation of an object." |
| `__subclasscheck__` | "Return true if subclass should be considered a (direct or indirect) subclass of class." |

Map, filter, zip, enumerate and iter with a sentinel call no function and read
no item when they are called. They read items only when their iterator is
read, and a statement that throws the iterator away never reads it.

### The builtins it leaves out

The other 37 names can run code with an effect, or have an effect of their own.
The rule does not read them.

`dev_harness/sigils/code_type.py, in LEFT_OUT_BUILTINS` holds each one under its
reason.

| Builtin | Reason | The documentation says |
| ------- | ------ | ---------------------- |
| `__import__` | its page names an effect of its own | "This function is invoked by the import statement." |
| breakpoint | its page names an effect of its own | "This function drops you into the debugger at the call site." |
| delattr | its page names an effect of its own | "The function deletes the named attribute, provided the object allows it." |
| eval | its page names an effect of its own | "This function executes arbitrary code." |
| exec | its page names an effect of its own | "This function executes arbitrary code." |
| help | its page names an effect of its own | "Invoke the built-in help system." |
| input | its page names an effect of its own | "The function then reads a line from input" |
| open | its page names an effect of its own | "Open file and return a corresponding file object." |
| print | its page names an effect of its own | "Print objects to the text stream file, separated by sep and followed by end." |
| setattr | its page names an effect of its own | "The function assigns the value to the attribute, provided the object allows it." |
| anext | it advances an iterator | "When awaited, return the next item from the given asynchronous iterator" |
| next | it advances an iterator | "Retrieve the next item from the iterator by calling its __next__() method." |
| all | it iterates its argument, and iterating an iterator uses it up | "Return True if all elements of the iterable are true" |
| any | it iterates its argument, and iterating an iterator uses it up | "Return True if any element of the iterable is true." |
| bytearray | it iterates its argument, and iterating an iterator uses it up | "If it is an iterable, it must be an iterable of integers in the range 0 <= x < 256" |
| bytes | it iterates its argument, and iterating an iterator uses it up | "class bytes(source=b'')", with the same source rules as bytearray |
| dict | it iterates its argument, and iterating an iterator uses it up | "class dict(iterable, /, **kwargs)" |
| frozenset | it iterates its argument, and iterating an iterator uses it up | "Return a new frozenset object, optionally with elements taken from iterable." |
| list | it iterates its argument, and iterating an iterator uses it up | "class list(iterable=(), /)" |
| max | it iterates its argument, and iterating an iterator uses it up | "Return the largest item in an iterable or the largest of two or more arguments." |
| min | it iterates its argument, and iterating an iterator uses it up | "Return the smallest item in an iterable or the smallest of two or more arguments." |
| set | it iterates its argument, and iterating an iterator uses it up | "Return a new set object, optionally with elements taken from iterable." |
| sorted | it iterates its argument, and iterating an iterator uses it up | "Return a new sorted list from the items in iterable." |
| sum | it iterates its argument, and iterating an iterator uses it up | "Sums start and the items of an iterable from left to right and returns the total." |
| tuple | it iterates its argument, and iterating an iterator uses it up | "class tuple(iterable=(), /)" |
| classmethod | it reads an attribute, which runs a property's getter | "Class methods now inherit the method attributes (__module__, __name__, __qualname__, __doc__ and __annotations__)" |
| dir | it reads an attribute, which runs a property's getter | "the function tries its best to gather information from the object’s __dict__ attribute" |
| getattr | it reads an attribute, which runs a property's getter | "For example, getattr(x, 'foobar') is equivalent to x.foobar." |
| hasattr | it reads an attribute, which runs a property's getter | "This is implemented by calling getattr(object, name)" |
| property | it reads an attribute, which runs a property's getter | "Otherwise, the property will copy fget’s docstring (if it exists)." |
| staticmethod | it reads an attribute, which runs a property's getter | "Static methods now inherit the method attributes (__module__, __name__, __qualname__, __doc__ and __annotations__)" |
| vars | it reads an attribute, which runs a property's getter | "Return the __dict__ attribute for a module, class, instance, or any other object with a __dict__ attribute." |
| compile | it raises an auditing event, which runs each audit hook | "Raises an auditing event compile with arguments source and filename." |
| id | it raises an auditing event, which runs each audit hook | "Raises an auditing event builtins.id with argument id." |
| locals | before Python 3.13 it refreshes the mapping an earlier call returned | Python 3.12: "Update and return a dictionary representing the current local symbol table." |
| memoryview | its buffer is released through `__release_buffer__` when the view is freed | data model: "The method must release any resources associated with the buffer." |
| type | its three-argument form makes a class, which runs `__init_subclass__` | "Keyword arguments provided to the three argument form are passed to the appropriate metaclass machinery (usually __init_subclass__())" |

Four more texts ground the reasons:

```text
glossary, iterator   When no more data are available a StopIteration exception
                     is raised instead. At this point, the iterator object is
                     exhausted and any further calls to its __next__() method
                     just raise StopIteration again.
property             If c is an instance of C, c.x will invoke the getter
sys.addaudithook     When an auditing event is raised through the sys.audit()
                     function, each hook will be called in the order it was added
__init_subclass__    This method is called whenever the containing class is
                     subclassed.
```

Ruff's own page for B018 says the same of an attribute read: "if a seemingly
useless expression (like an attribute access) is needed to trigger a side
effect, consider assigning it to an anonymous variable". The project supports
Python 3.11 and later, so the 3.12 text of locals binds.

### A try body or a with suite

A call in a try body is kept for its exception, so it is not a finding. The
language reference, 8.5 "The with statement", gives a with statement as a try
statement whose try body holds the suite. So a call in a with suite is in a try
body too.

```text
with EXPRESSION as TARGET:
    SUITE

is semantically equivalent to:

manager = (EXPRESSION)
enter = manager.__enter__
exit = manager.__exit__
value = enter()
hit_except = False

try:
    TARGET = value
    SUITE
except:
    hit_except = True
    if not exit(*sys.exc_info()):
        raise
finally:
    if not hit_except:
        exit(None, None, None)
```

The rule climbs from the statement to each node that holds it. It stops at a
def, an async def or a lambda, because their body runs when they are called,
not inside the try. An else clause, an except clause and a finally clause are
not the try body.

`dev_harness/sigils/code_type.py, in _in_handled_body`:

```python
def _in_handled_body(node: ast.stmt, parents: dict[ast.AST, ast.AST]) -> bool:
    """Report whether `node` sits in a `HANDLED_BODIES` body before any `DEFERRED_BODIES` parent."""
    child: ast.AST = node
    parent = parents.get(child)
    while parent is not None and not isinstance(parent, DEFERRED_BODIES):
        if isinstance(parent, HANDLED_BODIES) and any(child is s for s in parent.body):
            return True
        child, parent = parent, parents.get(parent)
    return False
```

`dev_harness/sigils/code_type.py, in HANDLED_BODIES` and `in DEFERRED_BODIES`:

```python
HANDLED_BODIES = (ast.Try, ast.TryStar, ast.With, ast.AsyncWith)
DEFERRED_BODIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
```

### A name the module binds

A module can bind a builtin's name to something else, such as a def named len,
an import named float or a parameter named str. Then a call of that name is not
a call of the builtin. The rule leaves out each name the module binds anywhere.
A star import can bind any name, so the rule reads nothing in a module that
holds one.

`dev_harness/sigils/code_type.py, in _bound_names`:

```python
def _bound_names(tree: ast.Module) -> frozenset[str] | None:
    """Return each name `tree` binds, or None when a star import can bind any name."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.alias):
            if node.name == "*":
                return None
            names.add(node.asname or node.name.partition(".")[0])
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(name := getattr(node, "name", None), str):
            names.add(name)
        elif isinstance(rest := getattr(node, "rest", None), str):
            names.add(rest)
    return frozenset(names)
```

## The selection

For each input, CODE.TYPE@1 keeps only those of its 63 rules that the run rule
selects for the input's facts. Mypy runs when the selection keeps a mypy code,
and pyright when it keeps a pyright rule. Its own rule runs when the selection
keeps it, which needs an expression statement in the input. Each checker reads the whole program
from the root of the tree, so a rule that reads the project fits a file or a
function too. The sigil counts only the findings under the selected rules.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

Mypy is told which codes not to run. Each mypy code of the card that the
selection leaves out goes to mypy as a disabled error code, so mypy does not
report it. A selected sub code of a left-out code, such as method-assign under
assignment, is named as enabled, so it still runs. Every pyright rule fits every
source file, so pyright runs all 29 on each input of `src/`.

`dev_harness/sigils/code_type.py, in _functions_verdict`:

```python
    versions, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_type.py, in findings`, when mypy runs:

```python
    mypy_run = [rule for rule in MYPY.rules if f"{MYPY.tool} {rule}" in to_run]
    if mypy_run:
        disabled = tuple(rule for rule in MYPY.rules if rule not in mypy_run)
        ran.append(f"mypy {mypy.version.__version__}")
        errors += _mypy_findings(path, root, file, disabled)
```

`dev_harness/sigils/code_type.py, in findings`, when its own rule runs:

```python
    if f"{OWN.tool} {UNUSED_RESULT}" in to_run:
        ran.append(f"{OWN.tool} on Python {platform.python_version()}")
        errors += [
            Finding(OWN.tool, UNUSED_RESULT, line)
            for line in _unused_builtin_results(source)
        ]
```

`dev_harness/sigils/code_type.py, in _code_flags`:

```python
    kept = [
        code
        for code, item in mypy.errorcodes.error_codes.items()
        if item.sub_code_of is not None
        and item.sub_code_of.code in disabled
        and code not in disabled
    ]
    return [
        *(flag for code in disabled for flag in ("--disable-error-code", code)),
        *(flag for code in kept for flag in ("--enable-error-code", code)),
    ]
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 503 | 63 | 32 | 62 | 63 | 6,024 | 6,024 |
| def or class | 13,885 | 63 | 41 | 59 | 63 | 11,513 | 11,513 |

Its own rule adds no finding in `src/`: each of the 14,388 inputs gives the
same count of findings as it did before the rule existed. Four statements there
throw away a builtin's value, and the rule leaves each one out:

```text
src/gui/main_tabs/exchange_tab_surface.py, in check_refuses
    a float call in a try body
src/gui/simulator/sim_react_trading_tab.py, in SimTradingTabReact._way_in
    a getattr call in a try body; getattr is left out
src/gui/simulator/sim_trading_tab.py, in SimTradingTab._way_in
    a getattr call in a try body; getattr is left out
src/trading/scrumming/tick_phases.py, in TickPhaseMixin._tick_execute_fold
    a sum call; sum is left out, as it iterates its argument
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| SOUND | PASS | PASS |
| UNSOUND | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

SOUND means mypy reports no error, pyright no error or warning, and no statement
throws away a listed builtin's value, under a rule the card holds. UNSOUND carries, for each finding, the tool, its error code and
the line. UNSOUND reads
HOLD when the file the input line names sits in application source. Anywhere
else it reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_type/`. The sample tree holds the published
examples of six mypy error codes: arg-type, return-value, attr-defined,
union-attr, call-arg and index. It also holds the shape its own rule reads: a
float call whose value no code reads. Its known-good twin binds that value, and
holds the same kind of call in a try body and in a with suite.

```
python -m dev_harness.sigils.code_type <file>
python -m dev_harness.sigils.code_type --root <folder> <file>
python -m dev_harness.sigils.code_type --gate <file>
python -m dev_harness.sigils.code_type --card
```

## Tools and rules

The card names two tools and one rule of its own. Each mypy error, each pyright
error or warning, and each finding of its own rule, in the input file under a
rule the card holds, is an output. One row
per tool, from the card's
settings and tier 3. The command prints the versions it ran.

| Tool | Version on the card | How the card runs it | What counts |
| ---- | ------------------- | -------------------- | ----------- |
| mypy | 2.1.0 | `python -P -m mypy` from the root of the target tree, with `--output json`, the null device as its cache folder, and `--disable-error-code` for each mypy code the selection leaves out | each error in the input file under one of the 33 mypy codes the card can run that the selection keeps |
| pyright | 1.1.411 | `pyright.run` from the root of the target tree, with `--outputjson` | each error or warning in the input file under one of the 29 pyright rules the card can run that the selection keeps |
| code_type | none: the Python that runs the sigil, whose version the command prints | Python's ast module parses the input file | each statement in the input file that throws away a listed builtin's value, when the selection keeps unused-builtin-result |

## Rules

The card can run the 63 rules below. The last column names each characteristic
under which the Python discipline houses the rule, from `dev_harness/disciplines/python/rules.json`.

`dev_harness/sigils/code_type.py, in SETTINGS`: the card prints them as
mypy_rules, pyright_rules and own_rules.

| Rule | Tool | Characteristics |
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
| unused-builtin-result | code_type | reliability |

## Rules left off

The card does not run the 58 scope rules below, though it read every error
under them before it took its rules from its disciplines. An error under one of
them moves no verdict. Each reason comes from the Python discipline and
unplaced.json, and the card's left setting names every one with its full text.

`dev_harness/sigils/construct_rules.py, in why_left`, the reason each rule left:

```python
def why_left(
    tool: str, rule: str, named: Sequence[str], characteristics: Sequence[str]
) -> str | None:
    """Return why no `named` discipline houses `tool` rule `rule` under one of `characteristics`, or None when one does."""
    places = _housed().get((tool, rule), ())
    if any(name in named and found in characteristics for name, found in places):
        return None
    if places:
        return NOT_NAMED.format(housing=_housing_text(places))
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
| truthy-function | mypy | Housed by python under maintainability, security, which the card does not name. |
| truthy-iterable | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| type-abstract | mypy | No discipline houses it. |
| type-arg | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unimported-reveal | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unreachable | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| untyped-decorator | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unused-awaitable | mypy | No discipline houses it. The archetype's mypy flags leave this optional check off, so the house holds no row for it. |
| unused-ignore | mypy | No discipline houses it. |
| valid-type | mypy | No discipline houses it. |
| reportAssertAlwaysTrue | pyright | Housed by python under maintainability, security, which the card does not name. |
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
| reportUnusedExcept | pyright | Housed by python under maintainability, which the card does not name. |
| reportUnusedExpression | pyright | No discipline houses it. |
