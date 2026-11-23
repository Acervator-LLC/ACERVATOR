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

The project, Sigil-based Vernacular Condensate, closed on 2026-11-23. The
operator, 2026-11-23:

> "Okay, that is fine.  We are done with 1633.  It is not showing enough promise to continue."
>
> "Science must be allowed to win even if you do not like the results."

The last measurement is comment 7094741655 on #1633, and the closure is
comment 7110762631. Nothing under this design was built. The concept, the
spine, the build order and the sigil pages below stay as the record.

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

The write hook runs none of the nine coding sigils, before a write or after
it. They come from an earlier design. The operator, 2026-11-23:

> "Coding Sigils should not be active at all since they were supposed to be part of a separate archetype version that was being tested and not yet deployed."

The nine stay under `dev_harness/sigils/` as the record of that version:
CODE.LOOP, CODE.IMPORT, CODE.FLOW, CODE.VARIABLE, CODE.COLLECTION,
CODE.OPTIMIZE, CODE.TYPE, CODE.REACH and CODE.SECURE.

After each write of a Python file,
`dev_harness/hooks/archetype_gate.py, in _run_post` prints the archetype
verdict and no sigil line.

```python
    deadline = time.monotonic() + POST_BUDGET_S
    parts = []
    for module in modules:
        _debug_log(f"post: running {module} on {path.name}")
        parts.append(
            _summarize(_run_archetype(module, path, deadline=deadline),
                       module, path))
    if not parts:
        return 0
```

Before a write, `dev_harness/hooks/archetype_gate.py, in _run_pre` refuses the
write only when the archetype finds a new high or critical fault in it. The
hook reads no sigil marker file.

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

### The sigil pages

Each page states what one sigil reads, its outputs and flags, its command and
its rules. The nine coding sigils, none of which the write hook runs:

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
