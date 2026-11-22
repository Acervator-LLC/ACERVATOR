# The Sigil Project

Reference. A sigil is a complex function set for one domain, such as Python. It
holds that domain's canonized rules, workflows and restricted outputs as code
built into it, so no skill has to be loaded for each prompt. While a prompt is
processed, the sigil constrains input inference: it refuses an incompatible
input, applies the canonized rules and workflows to a compatible one, and
produces one or more valid outputs. Like a protein or a hormone, a sigil fits
only certain places and performs only its own function there.

Sigils sit under archetypes, the occupation-specific agents, and an archetype's
vernacular is the set of marks that call its sigils. An archetype's mind is
built from its sigils, one per language, in one repeating structure. The aim is
consistent, valid, professional results from prompts that word one objective
differently, with less drift and hallucination. It is not compression, and a
speed gain is secondary.

The project's name is Sigil-based Vernacular Condensate. The work is research,
and nothing here changes the trading platform.

## The spine

Six things define every sigil.

*Proposed, not present:*

```
the sigil       one per domain, with its edition: PYTHON@1
its socket      the inputs it accepts, read in tiers: data type, then fit with the
                archetype's work, then the processing functions it requires
its canon       the domain's canonized rules, workflows and allowed outputs, as code inside it
its output      one or more outputs that meet the canon, or a refusal that names the tier or rule
its archetype   the occupation it serves; the archetype's mind is the set of its sigils
its mark        the short name in the archetype's vernacular that calls it
```

## What a hosted model allows

A sigil here can constrain what reaches the model, the shape of its call, and
what is accepted from it. It cannot constrain the inference between those
points. Whether that reach is enough for varied prompts to give one valid
result is the question the trial answers.

```
the model's inference     not reachable: in the documentation read, the Claude API
                          constrains token sampling only through a JSON Schema
the socket                reachable: a sigil called as a tool with a strict schema
the input rail            reachable: the prompt hook reads each prompt before the model
                          and can block it or add text beside it
the output rail           reachable: the tool hook can deny a write before it lands
the canon                 reachable: named analyzers run on each output, and a failed
                          rule sends the work back
```

## Measures

The project reads its results on four measures.

*Proposed, not present:*

```
consistency   one objective in many published wordings: how far each arm's outputs differ
validity      the task's hidden tests, such as EvalPlus's, which the sigil never runs;
              and each canon rule as a program check
placement     each sigil's socket table: a known-good and a known-bad input per row
refusal       each refused input names the tier that refused it
```

## Build order

The rows run from the Python canon up to the archetype's mind. Nothing is built
under this design, so every row reads unbuilt.

### Layer 0: the Python canon

| # | Concept | Subsystem | Status |
| --- | ------- | --------- | ------ |
| 1 | every rule the Python canon holds, in one list, each rule with its published source | none | unbuilt |
| 2 | the canonized workflow for a Python change, from request to accepted code, each step with its published source | none | unbuilt |

### Layer 1: the Python Sigil

| # | Concept | Subsystem | Status |
| --- | ------- | --------- | ------ |
| 3 | the socket: the three tiers, and a refusal that names the tier | none | unbuilt |
| 4 | the function set: rows 1 and 2 as code inside the sigil, giving one or more valid outputs | none | unbuilt |

### Layer 2: the prompt path

| # | Concept | Subsystem | Status |
| --- | ------- | --------- | ------ |
| 5 | the input rail: the sigil reads each Python prompt before the model | none | unbuilt |
| 6 | the output rail: each Python write meets the sigil's canon before it lands | none | unbuilt |

### Layer 3: the trial

| # | Concept | Subsystem | Status |
| --- | ------- | --------- | ------ |
| 7 | published tasks in published wordings, run by a plain archetype and by one holding the Python Sigil, paired; power sets the count, and the scoring is fixed and hashed, before the first run | none | unbuilt |

### Layer 4: the archetype's mind, built only after row 7 reads a gain

| # | Concept | Subsystem | Status |
| --- | ------- | --------- | ------ |
| 8 | the Coding Archetype built from its sigils, one per language, in one repeating structure | none | unbuilt |
| 9 | the vernacular: the marks the archetype reads, each calling one sigil | none | unbuilt |

## In the repository, outside this design

The write hook runs nine coding sigils, each for one kind of check, on each
Python write. They come from an earlier design. This design holds one Python
Sigil in their place, and the nine stay until rows 1 to 6 replace them.

After each write of a Python file, the hook prints the archetype verdict first.
Then it adds the sigil feedback, marked `[sigil-feedback]`. A sigil with
findings gets a block that names each rule and its lines. The other sigils
share one line for each state: clean, does not cover this file, or not read.
The nine are the names in `dev_harness/hooks/archetype_gate.py, in CODING_SIGILS`:
CODE.LOOP, CODE.IMPORT, CODE.FLOW, CODE.VARIABLE, CODE.COLLECTION,
CODE.OPTIMIZE, CODE.TYPE, CODE.REACH and CODE.SECURE.

The feedback is on by default, and
`dev_harness/hooks/archetype_gate.py, in _sigil_feedback_off` turns it off in
two cases. The first is the environment variable ACERVATOR_SIGIL_FEEDBACK
reading off, and the hook ignores the case of that value and the spaces around
it. The second is a file named SIGIL_FEEDBACK_OFF in the written file's folder,
or in a folder above it up to the repository root.

```python
def _sigil_feedback_off(path: Path) -> bool:
    """Report off when `SIGIL_SWITCH` reads `SIGIL_OFF` or `_sigil_marked` holds."""
    if os.environ.get(SIGIL_SWITCH, "").strip().lower() == SIGIL_OFF:
        return True
    return _sigil_marked(path)
```

Their lines after a write are advice.
`dev_harness/hooks/archetype_gate.py, in _run_post` builds the archetype
verdict before any sigil runs, and it adds the sigil lines after the verdict
only while the feedback is on. The archetype verdict reads the same with the
feedback on or off.

```python
    deadline = time.monotonic() + POST_BUDGET_S
    parts = []
    for module in modules:
        _debug_log(f"post: running {module} on {path.name}")
        parts.append(
            _summarize(_run_archetype(module, path, deadline=deadline),
                       module, path))
    if path.suffix == SIGIL_SUFFIX and not _sigil_feedback_off(path):
        _debug_log(f"post: running the coding sigils on {path.name}")
        parts.append(_sigil_part(path, deadline))
```

### The construct scope

Five of the nine read one construct each: CODE.LOOP, CODE.IMPORT,
CODE.COLLECTION, CODE.FLOW and CODE.VARIABLE. None holds a list of ruff rules
of its own. Each takes the ruff rules that the construct scope places on its
construct and that the Python discipline houses under one of its
characteristics. A rule sits on a construct where its own published faulty
example raises its finding on that construct.
`dev_harness/sigils/construct_scope.py, in owners` climbs from the finding's
node to the first node that a construct sigil reads. One command writes the
scope beside the sigils, and each sigil reads it when it loads:

```
python -m dev_harness.sigils.construct_scope
```

### The tool scope

The other four hold the rules of named tools: CODE.OPTIMIZE holds ruff's,
CODE.TYPE holds mypy's and pyright's, CODE.SECURE holds bandit's and semgrep's,
and CODE.REACH holds vulture's. A tool sigil holds each rule in its tool's
scope that the Python discipline houses under one of the characteristics its
card names.

`dev_harness/sigils/construct_rules.py, in hold`:

```python
def hold(
    tool: str, rules: Iterable[str], named: Sequence[str], characteristics: Sequence[str]
) -> Held:
    """Return the `Held` scope `rules` of `tool` that the `named` disciplines house under `characteristics`."""
    _check_named(named, characteristics)
    held: list[str] = []
    left: dict[str, str] = {}
    for rule in rules:
        why = why_left(tool, rule, named, characteristics)
        if why is None:
            held.append(rule)
        else:
            left[rule] = why
    return Held(tool, tuple(named), tuple(characteristics), tuple(held), left)
```

### A marker that refuses a write

A file named SIGIL_FEEDBACK_REFUSE lets the nine refuse a write before it
lands. When it sits in the folder of a Python file, or in a folder above it up
to the repository root, the hook stages the pending content beside the file
and the sigils read that copy. The hook refuses the write when a sigil flags a
fault, FIX or HOLD, on a line that the write adds or changes. The archetype
check runs first, and no sigil runs while the feedback is off.

`dev_harness/hooks/archetype_gate.py, in _sigil_refusal`:

```python
def _sigil_refusal(path: Path, content: str, deadline: float) -> str:
    """Return `_REFUSAL` text when a sigil flags a `_changed_lines` line, else empty."""
    if path.suffix != SIGIL_SUFFIX or not _sigil_marked(path, SIGIL_REFUSE_MARKER):
        return ""
    if _sigil_feedback_off(path):
        return ""
```

### The sigil pages

Each page states what one sigil reads, its outputs and flags, its command and
its rules. The nine that the write hook runs:

- [CODE.LOOP@1](16-sigil-project/code-loop.md)
- [CODE.IMPORT@1](16-sigil-project/code-import.md)
- [CODE.FLOW@1](16-sigil-project/code-flow.md)
- [CODE.VARIABLE@1](16-sigil-project/code-variable.md)
- [CODE.COLLECTION@1](16-sigil-project/code-collection.md)
- [CODE.OPTIMIZE@1](16-sigil-project/code-optimize.md)
- [CODE.TYPE@1](16-sigil-project/code-type.md)
- [CODE.REACH@1](16-sigil-project/code-reach.md)
- [CODE.SECURE@1](16-sigil-project/code-secure.md)

Three more sigils of the earlier design sit beside them, and the write hook
runs none of them:

- [CODE.DEBUG.PYTHON@1](16-sigil-project/code-debug-python.md)
- [CITE.SYMBOL@3](16-sigil-project/cite-symbol.md)
- [TA.AUDIT@1](16-sigil-project/ta-audit.md)

Three pages cover the coding sigils as a set:

- [Rule run partitioning](16-sigil-project/rule-partition.md)
- [The OCIR cases](16-sigil-project/ocir-cases.md)
- [Which OCIR rows are cases](16-sigil-project/ocir-qualify.md)
