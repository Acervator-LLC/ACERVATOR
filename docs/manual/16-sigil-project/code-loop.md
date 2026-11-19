# CODE.LOOP@1

Reference. CODE.LOOP@1 reads the loops in one Python file against the 33 rules
it can run: 29 ruff rules and 4 rules of its own. The Coding Archetype owns it.
It is one sigil of [the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.LOOP@1 reads each loop and comprehension for the faults that give a wrong
result, waste work, or write by hand what Python's own forms already state. It
draws on the Python discipline, under three characteristics: conventions,
performance efficiency and reliability.

The card holds no list of ruff rules. It takes each ruff rule that the
construct scope places on the loop construct and that the Python discipline
houses under one of its characteristics. [The construct scope](../16-sigil-project.md#the-construct-scope)
states how a rule is placed. The card's four rules of its own are under
[Rules of its own](#rules-of-its-own).

`dev_harness/sigils/code_loop.py, in TAKEN`:

```python
DISCIPLINES = ("python",)
CHARACTERISTICS = ("conventions", "performance-efficiency", "reliability")
TAKEN = take("loop", DISCIPLINES, CHARACTERISTICS)
```

## How its loop rules were found

Two readings looked for every loop rule the Python discipline houses, without
starting from the construct scope. The first reads each rule's published pair
and asks whether the corrected form changes a for, async for or while
statement, or a list, set or dictionary builder or generator expression, of the
faulty form. The second reads each rule's published text for a loop.

| Reading | Rules it names, of 491 housed ruff rules |
| ------- | ---------------------------------------- |
| the published pair changes a loop | 34 |
| the published text names a loop | 43 |
| both | 27 |

The construct scope already placed 16 of the 27 on the loop construct. It
places the other 11 there through a list in the scope command, each with the
first loop node its corrected form changes.

One reading alone names 23 rules. B031 and PTH206 of them sit on the loop
construct through the climb. The other 21 were read against their pairs and
stay off the card. A rule joins only when its corrected form changes the loop
itself, and its faulty form holds no fault outside the loop. Each of the 21
fails one test: its corrected form leaves the loop as it is, its faulty form
holds the fault outside a loop too, its faulty form holds no loop, or ruff
publishes no pair for it.

`dev_harness/sigils/construct_scope.py, in LOOP_PAIRS`:

```python
LOOP_PAIRS = (
    "B023",
    "C400",
    "PERF101",
    "PERF203",
    "PERF401",
    "PERF403",
    "PLC0208",
    "RET507",
    "RET508",
    "SIM110",
    "SIM113",
)
```

| Rule | Where the climb places it | The loop node its corrected form changes |
| ---- | ------------------------- | ---------------------------------------- |
| B023 | none | the list builder at line 1 |
| C400 | collection | the generator expression at line 1 |
| PERF101 | collection | the for at line 2 |
| PERF203 | none | the for at line 5 |
| PERF401 | flow | the for at line 3 |
| PERF403 | variable | the for at line 3 |
| PLC0208 | collection | the for at line 1 |
| RET507 | flow | the for at line 2 |
| RET508 | flow | the for at line 2 |
| SIM110 | none | the for at line 2 |
| SIM113 | variable | the for at line 3 |

PERF203 fires only when ruff's target is below Python 3.11. This tree's
`pyproject.toml` requires Python 3.14, so its faulty form reads CLEAN here. The
test pair reads it again under a ruff.toml that sets target-version py310, and
there it reads FINDINGS.

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module. Tier 3 runs ruff
with the selected ruff rules of the 29 the card can run and with preview rules on. The file goes to ruff
on standard input, from the folder of the file. Python's ast module then reads
the same file for each selected rule of the card's own. For a function or
class, only the findings inside its lines count.

For each ruff rule that fires, ruff's own rule page gives the rule's name, its
fix class, and its published faulty and corrected forms. For a rule of the
card's own, the card gives them, with the rule's source quoted beside its link.
The card records ruff 0.16.0, and the command prints the ruff version it ran.

When ruff is missing or its installed version is not 0.16.0,
`dev_harness/sigils/core.py, in version_fault` refuses the input at tier 3
before ruff runs.

`dev_harness/sigils/code_loop.py, in _ruff_findings`:

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

## The selection

For each input, CODE.LOOP@1 runs only those of its 33 rules that the run rule
selects for the input's facts. A rule whose subject the input lacks does not
run, and an input that selects no ruff rule runs no ruff. The keys file holds
no keys for the card's 4 rules of its own, so the run rule keeps them for every
input.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_loop.py, in _functions_verdict`:

```python
    version, found = findings(text, root, selection(text, root, CAN_RUN))
```

The rules ruff gets, and the rules of the card's own that run:

`dev_harness/sigils/code_loop.py, in findings`:

```python
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
    own = tuple(code for code in OWN.rules if f"{OWN.tool} {code}" in to_run)
```

[The sigil proof](rule-partition.md#the-sigil-proof) runs CODE.LOOP@1 on every
tracked Python file of `src/` and every def and class in them, once with the
selection and once with every rule it can run, and fails when the two lists of
findings differ.

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| FINDINGS | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means no rule on the list fires. FINDINGS carries, for each finding, the
rule id, the rule name, the line, the fix class, and both published forms. For
a rule of the card's own, it also carries each source quoted with its link.
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
| B007 | unused-loop-control-variable | Checks for unused variables in loops (e.g., `for` and `while` statements). | sometimes | no |
| B023 | function-uses-loop-variable | Checks for function definitions that use a loop variable. | none | no |
| B031 | reuse-of-groupby-generator | Checks for multiple usage of the generator returned from `itertools.groupby()`. | none | no |
| C400 | unnecessary-generator-list | Checks for unnecessary generators that can be rewritten as list comprehensions (or with `list()` directly). | always | no |
| C419 | unnecessary-comprehension-in-call | Checks for unnecessary list or set comprehensions passed to builtin functions that take an iterable. | sometimes | no |
| C420 | unnecessary-dict-comprehension-for-iterable | Checks for unnecessary dict comprehension when creating a dictionary from an iterable. | sometimes | no |
| F402 | import-shadowed-by-loop-var | Checks for import bindings that are shadowed by loop variables. | none | no |
| FURB129 | readlines-in-for | Checks for uses of `readlines()` when iterating over a file line-by-line. | always | no |
| FURB140 | reimplemented-starmap | Checks for generator expressions, list and set comprehensions that can be replaced with `itertools.starmap`. | sometimes | yes |
| PERF101 | unnecessary-list-cast | Checks for explicit casts to `list` on for-loop iterables. | always | no |
| PERF102 | incorrect-dict-iterator | Checks for uses of `dict.items()` that discard either the key or the value when iterating over the dictionary. | always | no |
| PERF203 | try-except-in-loop | Checks for uses of except handling via `try`-`except` within `for` and `while` loops. | none | no |
| PERF401 | manual-list-comprehension | Checks for `for` loops that can be replaced by a list comprehension. | sometimes | no |
| PERF402 | manual-list-copy | Checks for `for` loops that append every item of an iterable to a list, which can be replaced with a call to `list`. | none | no |
| PERF403 | manual-dict-comprehension | Checks for `for` loops that can be replaced by a dictionary comprehension. | sometimes | no |
| PLC0206 | dict-index-missing-items | Checks for dictionary iterations that extract the dictionary value via explicit indexing, instead of using `.items()`. | none | no |
| PLC0208 | iteration-over-set | Checks for iteration over a `set` literal in which each element is a literal. | always | no |
| PLE4703 | modified-iterating-set | Checks for loops in which a `set` is modified during iteration. | always | yes |
| PLR1733 | unnecessary-dict-index-lookup | Checks for key-based dict accesses during `.items()` iterations. | always | no |
| PLR1736 | unnecessary-list-index-lookup | Checks for index-based list accesses during `enumerate` iterations. | always | no |
| PTH206 | os-sep-split | Checks for uses of `.split(os.sep)` | none | no |
| RET507 | superfluous-else-continue | Checks for `else` statements with a `continue` statement in the preceding `if` block. | sometimes | no |
| RET508 | superfluous-else-break | Checks for `else` statements with a `break` statement in the preceding `if` block. | sometimes | no |
| RUF006 | asyncio-dangling-task | Checks for `asyncio.create_task` and `asyncio.ensure_future` calls that do not store a reference to the returned result. | none | no |
| SIM110 | reimplemented-builtin | Checks for `for` loops that can be replaced with a builtin function, like `any` or `all`. | sometimes | no |
| SIM113 | enumerate-for-loop | Checks for `for` loops with explicit loop-index variables that can be replaced with `enumerate()`. | none | no |
| SIM911 | zip-dict-keys-and-values | Checks for use of `zip()` to iterate over keys and values of a dictionary at once. | always | no |
| UP028 | yield-in-for-loop | Checks for `for` loops that can be replaced with `yield from` expressions. | sometimes | no |

## Rules of its own

CODE.LOOP@1 runs four rules that this project writes, under the tool name
code_loop. Each reads a slow loop form that none of the 968 rules ruff 0.16.0
lists reads. Of those 968, only FURB129 names `readlines()`, and it reads the
fault on the built-in open, io.open, a pathlib class call, and a name annotated
typing.TextIO. LOOP004
reads the same fault on a file that any other method named open returned. Each
rule rests on a section of the Python 3.14 documentation that states the form's
cost and names the faster form.

| Rule | Name | What it catches | Faster form | Fix |
| ---- | ---- | --------------- | ----------- | --- |
| LOOP001 | list-pop-front-in-loop | `pop(0)` on a list inside a loop, or `name = name[1:]` | `popleft()` on a `collections.deque` | none |
| LOOP002 | list-insert-front-in-loop | `insert(0, item)` on a list inside a loop, or `name = [item] + name` | `appendleft(item)` on a `collections.deque` | none |
| LOOP003 | str-concat-in-loop | a str built by `+=` inside a loop, or by `name = name + text` | `write()` to an `io.StringIO`, or a list joined by `str.join()` | none |
| LOOP004 | open-method-readlines-in-for | `readlines()` iterated by a for loop or a builder, on a file a method `open` returned | the file object itself, iterated | none |

The sources, as the documentation states them:

```text
LOOP001, LOOP002  The Python Tutorial, 5.1.2. Using Lists as Queues
                  https://docs.python.org/3.14/tutorial/datastructures.html#using-lists-as-queues
                  While appends and pops from the end of list are fast, doing
                  inserts or pops from the beginning of a list is slow (because
                  all of the other elements have to be shifted by one). See Time
                  complexity of operations on built-in types for more
                  information. To implement a queue, use collections.deque which
                  was designed to have fast appends and pops from both ends.

LOOP003           Python built-ins reference, Common Sequence Operations, note 6
                  https://docs.python.org/3.14/builtins/stdtypes.html#typesseq-repeated-concatenation
                  Concatenating immutable sequences always results in a new
                  object. This means that building up a sequence by repeated
                  concatenation will have a quadratic runtime cost in the total
                  sequence length. To get a linear runtime cost, you must switch
                  to one of the alternatives below: if concatenating str
                  objects, you can build a list and use str.join() at the end or
                  else write to an io.StringIO instance and retrieve its value
                  when complete

LOOP004           The Python Tutorial, 7.2.1. Methods of File Objects
                  https://docs.python.org/3.14/tutorial/inputoutput.html#methods-of-file-objects
                  For reading lines from a file, you can loop over the file
                  object. This is memory efficient, fast, and leads to simple
                  code:
```

LOOP004 also quotes the faulty and corrected forms that ruff publishes for
FURB129, readlines-in-for, at
[docs.astral.sh/ruff/rules/readlines-in-for](https://docs.astral.sh/ruff/rules/readlines-in-for/):

```text
Example:
with open("file.txt") as fp:
    for line in fp.readlines():
        ...

Use instead:
with open("file.txt") as fp:
    for line in fp:
        ...
```

LOOP001, LOOP002 and LOOP003 fire only inside a part of a loop that runs on
each pass: a for or async for body, a while test or body, or a builder's
element, conditions and later sources. A call in a for header or a for else
clause does not fire, and neither does one in a function defined inside the
loop.

`dev_harness/sigils/code_loop.py, in _repeated`:

```python
def _repeated(loop: LoopNode) -> list[ast.AST]:
    """Return the parts of `loop` that run on each pass: body, while test, or builder element and conditions."""
    if isinstance(loop, ast.For | ast.AsyncFor):
        return list(loop.body)
    if isinstance(loop, ast.While):
        return [loop.test, *loop.body]
    parts: list[ast.AST] = (
        [loop.key, loop.value] if isinstance(loop, ast.DictComp) else [loop.elt]
    )
    for index, generator in enumerate(loop.generators):
        parts.extend(generator.ifs)
        if index:
            parts.append(generator.iter)
    return parts
```

A name counts as a list or a str only when every binding in its nearest scope
builds one: a display, a comprehension, an f-string, a list or str call, or a
list or str annotation. An attribute of a method's first parameter counts the
same way, from every binding the class's methods give it. A pop on a
dictionary, on a name also bound to a deque, or on an attribute of any other
name does not fire.

`dev_harness/sigils/code_loop.py, in _key`:

```python
def _key(expr: ast.expr | None) -> str | None:
    """Return the name `expr` reads, or `owner.attr` for an attribute of a name, else None."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        return f"{expr.value.id}.{expr.attr}"
    return None
```

The loop must also carry the name or attribute from one pass to the next: no
part that runs on each pass gives it a plain assignment. An assignment from its
own value, a slice of it or a sum that holds it, carries it. A list or str
assigned afresh on each pass does not fire.

`dev_harness/sigils/code_loop.py, in _carried`:

```python
def _carried(expr: ast.expr, chain: Chain, rebound: frozenset[str]) -> str:
    """Return `_kind` of `expr` when its `_key` is not in `rebound`, else `OTHER`."""
    if _key(expr) in rebound:
        return OTHER
    return _kind(expr, chain)
```

`dev_harness/sigils/code_loop.py, in _front_call`:

```python
def _front_call(
    node: Node, chain: Chain, rebound: frozenset[str], method: str, count: int
) -> bool:
    """Report whether `node` calls `method` with `count` arguments, the first 0, on a carried `LIST` key."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and len(node.args) == count
        and not node.keywords
        and _int_value(node.args[0]) == 0
        and _carried(node.func.value, chain, rebound) == LIST
    )
```

LOOP004 reads the loop's iterable instead: the iterable of a for or async for
loop, and of each generator of a builder. A call anywhere inside the iterable,
such as inside an enumerate call, does not fire.

`dev_harness/sigils/code_loop.py, in _iterated`:

```python
def _iterated(loop: LoopNode) -> list[ast.AST]:
    """Return the iterable of a for `loop`, or of each generator of a builder `loop`."""
    if isinstance(loop, ast.For | ast.AsyncFor):
        return [loop.iter]
    if isinstance(loop, ast.While):
        return []
    return [generator.iter for generator in loop.generators]
```

The iterable must call readlines with no argument, on a call to a method named
open or on a name. A name counts only when every binding in its nearest scope
gives it such a call: as a with item's name, or by a plain assignment. A name
bound again to anything else does not fire. A size hint, a list kept in a name,
and an object no method open returned do not fire.

`dev_harness/sigils/code_loop.py, in _file_targets`:

```python
def _file_targets(node: ast.AST) -> list[tuple[ast.Name, ast.expr]]:
    """Return each name `node` binds by a with item's `as`, or by assigning a `_calls_open` call, with its value."""
    if isinstance(node, ast.With | ast.AsyncWith):
        pairs = [(item.optional_vars, item.context_expr) for item in node.items]
    elif isinstance(node, ast.Assign) and _calls_open(node.value):
        pairs = [(target, node.value) for target in node.targets]
    else:
        return []
    targets = []
    for target, value in pairs:
        if isinstance(target, ast.Name):
            targets.append((target, value))
    return targets
```

`dev_harness/sigils/code_loop.py, in _reads_all_lines`:

```python
def _reads_all_lines(node: Node, chain: Chain, _rebound: frozenset[str]) -> bool:
    """Report whether `node` calls `readlines()` with no argument on an `_opens` call or an `OPENED` name."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "readlines"
        and not node.args
        and not node.keywords
    ):
        return False
    file = node.func.value
    return _opens(file, chain) or (
        isinstance(file, ast.Name) and _kind(file, chain) == OPENED
    )
```

A method open that FURB129 already reads does not count, so no line carries
both rules. That is a call to a pathlib class, or the io or os module, each
named through an import in the nearest scope that binds the name.

`dev_harness/sigils/code_loop.py, in _opens`:

```python
def _opens(expr: ast.expr | None, chain: Chain) -> bool:
    """Report whether `expr` calls a method `open` on no `FURB129_PATH_CLASSES` call and no `FURB129_OPEN_MODULES` module."""
    if not (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "open"
    ):
        return False
    owner = expr.func.value
    if isinstance(owner, ast.Call):
        return _qualified(owner.func, chain) not in FURB129_PATH_CLASSES
    return _qualified(owner, chain) not in FURB129_OPEN_MODULES
```

The Python discipline houses the four under performance efficiency, each on
the section above. LOOP003 also rests on this CWE, which the performance
efficiency list holds:

```text
CWE-1046  The product creates an immutable text string using string concatenation operations.
```

The card runs only those rules of its own that the house holds.

`dev_harness/sigils/code_loop.py, in OWN`:

```python
OWN = hold(OWN_TOOL, tuple(OWN_RULES), DISCIPLINES, CHARACTERISTICS)
```

Each of the four carries fix class none. The follow-on runner passes none of
them to ruff. It prints the rule's corrected form, and the named file keeps
every byte. LOOP004's corrected form iterates the file object.

These forms have no rule:

```text
x in a list inside a loop       the time complexity page gives x in l as O(n) and x in s as
                                O(1), and no section names the set as the faster form
name = name + [item]            a list grown at its end: the same page gives l1 + l2 a cost,
                                and no section names a faster form
other + name, del name[0],      the front of a list changed through a second name, a del or a
name[:0] = [item]               slice assignment: the rules read pop, insert, a slice from 1
                                and a list display before the name
bytes or tuple built by +=      the rules read a str alone
a list on a class by its name   only an attribute of a method's first parameter has a kind
an unannotated parameter        no binding gives it a kind
file: TextIO = path.open()      an annotated name takes its annotation's kind; FURB129 reads
                                this form when the annotation is typing.TextIO
enumerate(file.readlines())     LOOP004 reads the loop's iterable itself, as FURB129 does
a file name bound another way   every binding of the name must give it a call to a method open
in the same scope
```

The test lists hold each rule's published faulty form, its corrected form, the
same call outside any loop, and the same call on a name each pass assigns
afresh. `harness_fixtures/sigil_code_loop/failure_modes.txt` adds each rule's
form in a for loop, a while loop, a nested loop, a rebinding and an attribute,
and the sites found in `src/`, each with a corrected twin and a twin outside any
loop. Each faulty input reads its own rule, and no twin does.

For LOOP004 the list holds the three forms FURB129 misses and the form two
experiment tasks first held. It also holds a method open on an attribute and on
a call result. Each has a corrected twin, a kept list, a size hint and an object
no method open returned. A file bound by plain assignment has a corrected twin,
a twin that binds the name again before the loop, and its built-in open twin.
Beside them sit the six other forms FURB129 reads and the one readlines site in
`src/`:

`src/core/usb_auth.py, in _list_usb_linux`

8 of 8 faulty inputs read LOOP004, 0 of 37 twins do, and no line carries both
FURB129 and LOOP004.

Every input of `harness_fixtures/sigil_code_loop/known_good.txt` reads CLEAN,
so the list exits 0, and `known_bad.txt` exits 1. A corrected form that reads
another rule, or holds no loop once fixed, stays in the sample tree. The head
of known_good.txt names each such file with its reason.

## Rules left off

The card does not run the rules below, though its own rule list once named
them. Each reason comes from the construct scope and the Python discipline. The
card's left setting names every rule on the loop construct that no discipline
houses, with its unplaced.json text.

| Rule | Reason |
| ---- | ------ |
| B035 | No discipline houses it. |
| C416 | No discipline houses it. |
| PLW0120 | No discipline houses it. |
| FURB122 | No discipline houses it. |
| FURB142 | No discipline houses it, and no sigil runs this preview rule now, so it left the house too. |
