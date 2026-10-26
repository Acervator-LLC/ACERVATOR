# Conceptual Hopscotch

Reference. Three subjects a reader meets around this repository and cannot find
in the running code: the handoff file that carries a session across a context
boundary, the rule registry no running module reads, and the development
protocol, which exists in two versions — one with no source in this repository,
one running today.

## The handoff file

`ACERVATOR_HOP8.md` at the repository root is the current handoff and the only
one this manual describes. The earlier `ACERVATOR_HOP*.md` files at the root
hold archives of sessions that closed, and nothing in them binds.

### The root-file inventory sentences, overtaken

OVERTAKEN, quoted whole:

> "A root-file inventory test records why the handoff sits at the root rather
> than in a directory: the drift check looks for it there, and a fresh clone has
> to find its orientation without being told where to look. Each root file in
> that inventory carries a reason naming a mechanism, and a new root file without
> one fails the check."

```python
def test_the_inventory_names_every_tracked_root_file() -> None: ...  # test_repo_root_inventory
def test_the_inventory_names_no_file_that_has_left() -> None: ...
def test_every_inventory_entry_carries_a_reason() -> None: ...
```

True today: no inventory and no check. The file named above is not in the tree,
and the repository tracks one Python module under `tests/`, its own conftest.
Nothing now records a reason for any root file, and a new root file is refused
by nothing.

The reason the handoff sits at the root still holds: the measuring tool
`tools/hop_check.py` looks for it there, so a fresh clone finds its orientation
without being told where to look.

The handoff holds current state and an index, never a history. Its own three
standing instructions are to rewrite a section that has drifted rather than
append to it, to move anything measurable into a tool rather than prose, and to
keep every claim checkable in one command.

## What the drift check measures

`python -m tools.hop_check` reads the newest handoff and reports three
quantities.

- Commits landed since the handoff was last written, from `git rev-list --count`
  against the commit that last touched it. `STALE_AFTER` is 15; at or past that
  count the report calls the file drifted.
- Cited paths that no longer exist, matched as a backticked path under one of
  eight tracked directories.
- Cited commits that no longer resolve, matched as a backticked hex string of
  seven characters or more and checked with `git cat-file -t`.

```python
TRACKED = r"`((?:src|tests|tools|docs|desktop|dev_harness|harness_fixtures|\.github)/[\w./-]+)`"
```

Any one of the three returns exit 1. Run against the tree, the report reads 107
commits since the handoff was written, three paths declared absent on purpose,
no missing path and no unresolved commit, and it exits 1 on the commit count
alone.

`declared_absent` reads the paths under the `## CITED AS ABSENT` heading and
drops them from the missing-path count. A path under that heading is skipped even
when it sits on disk, which makes the heading a record of a deliberate citation
rather than a check on one.

### The sort key picks the wrong file at ten

The picker sorts the file names as strings and takes the last one. Every handoff
suffix holds one digit today, so the answer is correct. Driven with a two-digit
name added, `ACERVATOR_HOP10` sorts ahead of the single digits, the last entry
stays `ACERVATOR_HOP8.md`, and the drift report then describes a superseded file.
Driven again with only the two newest names present, the answer is the same. The
check needs a numeric key before a tenth handoff exists.

```python
def newest_hop() -> pathlib.Path | None:        # tools/hop_check.py
    """Returns the highest-numbered ACERVATOR_HOP*.md at the repository root."""
    found = sorted(ROOT.glob("ACERVATOR_HOP*.md"), key=lambda p: p.stem)
    return found[-1] if found else None
```

## The rules registry

The registry module declares 35 rule ids, R1 through R35, across ten lettered
groups. It holds one entry per id in one of four states — LOCKED, UNLOCKED,
SUSPENDED and DEPRECATED — and a parser turns a `RULE` line into a call on the
registry. Five ids are marked CORE: R1, R5, R10, R11 and R12.

```python
RULE_META = {...}       # unreached/core/rule_registry.py, 35 ids, R1 through R35
CORE_RULES = {r for r, m in RULE_META.items() if m["protection"] == "CORE"}
VALID_STATES = {"LOCKED", "UNLOCKED", "SUSPENDED", "DEPRECATED"}

class RuleEntry: ...
class RuleRegistry: ...
def parse_rule_command(...): ...
```

### The module moved, and the path citations are overtaken

OVERTAKEN. Every `unreached/core/rule_registry.py` and `unreached/core/version_sweep.py`
citation on this page stays whole, in prose and in the code blocks both.

The registry module is now `unreached/core/rule_registry.py` and the version
sweep is now `unreached/core/version_sweep.py`. Both were moved out of `src/`
because nothing in the tree reaches either one. An import scan over all 616
tracked Python files, reading import nodes rather than matching text, finds no
importer of either, and fifteen importers of `src/core/log_paths.py` in the same
pass, which is the control saying the count reports an importer where one
exists. `unreached/README.md` records what each file was for.

One shell step used to run the registry module. `deploy/kiosk/install.sh`
captured its output into a file on the kiosk. The step never produced anything:
the module saves to `sadp/`, so it raised `FileNotFoundError` before printing a
line, and `2>/dev/null || true` discarded the error and the exit code. It wrote
a 0-byte file on every install. Nothing read that file. The step is gone.

The suspend call refuses a CORE id. Driven both ways against a registry file in a
temporary directory, R1 draws a refusal and stays LOCKED while R2 moves to
SUSPENDED. The refusal is a real one rather than a declared one.

```python
def suspend(self, rule: str, reason: str, expires: str = "") -> str: ...     # unreached/core/rule_registry.py
```

Nothing in the product reads any of it. The registry path resolves into a
top-level directory that no commit in this repository has ever added.

### The importer sentences, overtaken

True today: the module has no importer at all. The one importer it once had is
not in the tree, so no file imports the registry and no file calls any symbol in
it. One module names it in printed text rather than in an import:
`unreached/core/version_sweep.py`, in `check_rule_registry`, prints a command a reader
is told to run.

```python
REGISTRY_PATH = ROOT / "sadp" / "RULE_REGISTRY.json"        # unreached/core/rule_registry.py
# sadp/ is not in the tree, so REGISTRY_PATH resolves to nothing
```

The module's own docstring says as much. The ids name nothing the running
program consults, and they carry no authority.

### What the version sweep's registry checks answer

`unreached/core/version_sweep.py` registers seventeen checks and prints one line for
each. Five of them read a path that has never been in this repository, and three
of those five read `sadp/RULE_REGISTRY.json`.

| check | path it reads | what it prints |
|---|---|---|
| `check_r6_two_paths` | `simulator.py under src/gui` | NOT INSPECTED, naming the absent file |
| `check_snapshot_consistency` | `simulator.py under src/gui` | NOT INSPECTED, naming the absent file |
| `check_rule_registry` | `sadp/RULE_REGISTRY.json` | one informational finding |
| `check_sadp_annotations` | `sadp/RULE_REGISTRY.json` | five high findings |
| `check_sadp_dependency_graph` | `sadp/RULE_REGISTRY.json` | NOT INSPECTED, naming the absent file |

Three of them report their own blindness through `_no_subject`, which `run`
turns into NOT INSPECTED in place of the pass mark. `check_snapshot_consistency`
calls it with the absent path, so a run of the sweep now prints three
NOT INSPECTED lines and no pass mark for a check that opened no file.

`check_sadp_annotations` reads an absent registry as an empty mapping and does
not return early. No `# sadp:` annotation remains in the tree, so it raises
nothing against an annotation, and five high findings against its own mandatory
list. One entry on that list names `simulator.py`.

Nothing in the tree runs any of it. An import scan over the 498 Python files
under `src/` and `main.py`, parsing each file and reading its import nodes,
finds no importer of the module, and finds fourteen importers of
`src/core/log_paths.py` in the same pass. No workflow, script or build step
names it. A reader reaches the per-check column only by typing the module name.

### The annotation check's sentences, overtaken

The sentence above that names this check's reading stays whole:

> `check_sadp_annotations` reads an absent registry as an empty mapping and does
> not return early.

True today: the check returns early. It names the file it could not read and
reports NOT INSPECTED, which is what the two siblings in the same class already
did. The row for it in the table above, and the count of NOT INSPECTED lines in
the paragraph before that table, are overtaken by the same change.

`unreached/core/version_sweep.py, in check_sadp_annotations`

```python
        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        rel = self._rel(registry_path)
        if not registry_path.exists():
            self._no_subject(f"{rel} absent")
            return
        try:
            registry = _json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._no_subject(f"{rel} unreadable: {type(exc).__name__}")
            return
```

A sweep over a tree holding no scratch checkout reads one line differently and
every other line the same.

```
                          before     after
SADP annotations (R38)    5 findings NOT INSPECTED
NOT INSPECTED lines                3         4
HIGH                              13         8
MEDIUM                            83        83
LOW                              488       488
INFO                               2         2
files scanned                    624       624
lines scanned                361,698   361,698
```

The five findings that stopped being printed are the whole of the difference.
Each one demanded an annotation of the retired protocol on a file that is not in
this repository, and nothing else was added, removed or changed. The retirement
is recorded under version one of the protocol, below.

Driven against a tree built for the reading, with the registry file on disk and
with it removed, the printed line separates where it did not before.

```
registry present, before    6 findings
registry present, after     6 findings
registry absent, before     6 findings
registry absent, after      NOT INSPECTED, naming the absent file
```

The present arm reads the same either way, so the change took nothing away from
a check that had something to read. Two neighbouring checks were read the same
way in all four arms: the registry check printed one finding throughout, and the
dependency check printed NOT INSPECTED with the file absent and one finding with
it present.

## Version one of the protocol

Version one was never built here. It named a directory, and the history holds no
commit that ever added that directory or anything inside it, the battery file
and the registry file included. The version sweep still reads three of those
paths: the battery file, the registry file, and a simulator module that is not
there either. Run the same query against a file that is real and it answers with
the commit that added it, which is the control saying the query works.

`git log --all --diff-filter=ADR --name-only`, one path per run

```
the query finds no commit that added the first two rows
sadp/, and RAIntSimBat.py and RULE_REGISTRY.json inside it   nothing
simulator.py under src/gui                                  nothing
src/core/log_paths.py                       the commit that added it
```

Version one's R-numbers were never live and must not be cited as though they
were.

### What SADP was, and what happened to it

The directory version one named belongs to SADP. The name is written out in
full on the manual's own legal page.

> Produced using the SADP (Structured Assistant Development Protocol) discipline
> framework designed by Ekthelius and deployed within Claude Code as a
> Skills-based and python-driven harness.

Seven lines on this page name that directory, and not one of them says what it
is. It held version one's rule registry, its rule specifications, its episodic
memory and its edit log.

No commit in this repository ever added it. The query in the table above returns
nothing for it. All that ever existed here was a set of references pointing at
it, and one commit removed them.

```
76879e44, 2026-08-22, issue #68, "strip the dead SADP references"

    pyproject.toml    the coverage source, the omit list, the vulture paths
    README.md         four sections, the launcher line, the battery instructions
    CONTRIBUTING.md   the pull-request step that ran a file that is not there
```

The repository front page records the retirement in one sentence.

> An earlier governance harness, SADP, was retired.

What replaced it is version two, below: the harness in this repository, the
skills, and the hooks. Nothing in the tree reads a version-one R-number.

One live path reads like the retired one and is not it. The session-stop hook
writes a record of whatever is uncommitted at a session boundary into a
directory named `.sadp` at the repository root, and the ignore list calls that
directory regenerable.

```
dev_harness/hooks/session_stop_backstop.py, in main    writes the record
.gitignore                                            names .sadp regenerable
```

The two names share four letters. The retired directory is in no commit and
never was. The one the hook writes is created at every session boundary.

### The Simulator-module sentences, overtaken

True today: the live file behind the second row is
`src/gui/main_tabs/simulator_tab.py`, and it is in the tree. The Simulator
surface beside it is `src/gui/main_tabs/simulator_tab_surface.py`, and the
panels the tab draws sit under `src/gui/simulator/`.

### The seven retirement checks, overtaken

True today: no check holds the line. The repository tracks one Python module
under `tests/`, its own conftest, and no retirement check is among them.
The retirement itself still holds, and one rule reports on it rather than
refusing it: the hallucination rule's H002 names the retired subsystem and
reports at low severity, so a page naming it still answers `passed` true.

## Version two of the protocol

Version two is the system running now. It has three layers, and only the first
is in this repository.

### The harness, in the repository

The harness directory holds twelve modules and the shared report contract. Each
runs from the command line against one path and reports a `passed` boolean,
exiting non-zero when it is false. That boolean needs five conditions, and the
first four concern the run rather than the findings: an unhandled file type, an
unscanned target, an analyzer that did not report ok, and a recorded error each
hold it false. A guard around every subprocess raises on a tool that wrote to
standard error and exited non-zero with empty output, which is how an
installed-but-unconfigured linter used to report a clean run.

```
python -m dev_harness.harness.<name> <path>

passed                  dev_harness/harness/report.py
refuse_silent_failure   dev_harness/harness/report.py
```

Five archetypes, one per domain:

- `coding_archetype.py` — Python source through ruff, mypy, pyright, bandit,
  vulture and semgrep, each normalised into one `Finding` schema.
- `docs_archetype.py` — Markdown through proselint and vale, plus a structural
  check for one H1, no repeated heading text, and a mode signal in the opening
  500 characters.
- `gui_archetype.py` — PySide6 widget source through a static AST pass, ruff and
  bandit. It rejects a colour read back from `styleSheet()`.
- `ta_archetype.py` — indicator source against its published formula, under rule
  ids TA000 through TA011.
- `watchdog_archetype.py` — the out-of-process crash watchdog, checking that
  every test pin reaches the one handler.

**Overtaken.** *"`coding_archetype.py` — Python source through ruff, mypy,
pyright, bandit, vulture and semgrep, each normalised into one `Finding`
schema."*

The bullet above keeps its wording. The coding archetype reads four languages,
not one. Python takes the six analyzers the bullet names. JavaScript takes
eslint. A shell script takes shellcheck. A YAML settings file takes yamllint.
For a file of any other type the archetype answers `unhandled`, which is
neither a pass nor a failure.

```
.py .pyi .pyw .spec    ruff, mypy, pyright, bandit, vulture, semgrep
.js .mjs .cjs .jsx     eslint
.sh .bash .zsh         shellcheck
.yml .yaml             yamllint
anything else          unhandled - no analyzer ran
```

The archetype marks an absent analyzer missing, and a report carrying a missing
analyzer never counts as a pass.

### What the dead-code floor admits

The dead-code analyzer scores a candidate from 0 to 100 and prints only the rows
at or above a floor. An uncalled function, method, class or property scores 60.
A hand-typed run reads its floor from the vulture block in `pyproject.toml`; the
coding archetype passes its own floor on the command line, which overrides that
block.

```
floor 60, the whole declared path set     1148 rows, exit 3
floor 70, the same paths                     0 rows, exit 0
floor 100, the same paths                    0 rows, exit 0
```

The floor is 60. At 70 the analyzer had nothing to say about any file, because
every one of the 1,148 rows scores exactly 60 and no row in the declared paths
scores higher. A silence from it was available to read as a clean result.

The archetype's verdict does not move with this block. It reads one file at a
time, and a 60% row is scored low, which never blocks a pass.

```
coding archetype on one module, floor 60 in the block    5 rows, all low, passed
coding archetype on the same module, floor 100           5 rows, all low, passed
```

A single-file reading cannot see a caller in another file, so a row it prints is
a question rather than an answer. The whole-path run is the reading that settles
it: of those 5 rows, 1 survives the whole-path run and 4 have a caller elsewhere.

The declared path set is `src` and the watchdog entry file. A callable reached
only from `main.py` therefore reads as uncalled, because the caller sits outside
the set.

The gate and the ledger:

- `check_release_readiness.py` — the release gate. It runs the suite, runs each
  archetype against its good fixture, and reads the claim ledger. It declines to
  declare a release ready when a step was skipped or when a green pytest run
  collected nothing. The older copy under `tools/`, and the whole harness
  directory beside it, are gone from the working tree.
- `claim_ledger.py` — one JSONL row per claim, each row carrying a status. A
  claim with no measurement behind it stays visible.

A claim holds one of three statuses.

| Status | What it records |
| ---------- | ------------------------------------------------------------- |
| `open` | Asserted, no measurement yet. A new claim starts here, and the pre-cascade check returns exit code 1 while one remains |
| `verified` | Evidence attached, as a note and a file list. Only an open claim moves here |
| `refuted` | Evidence disproved the claim. Only an open claim moves here |

Four analysis tools, each answering one question about live behaviour:

- `decision_diff.py` — the live decision diff.
- `manual_fire_frame_check.py` — the Manual Fire target-frame split against live
  state.
- `reconcile_position_values.py` — displayed position values against their own
  inputs.
- `ytd_compounding_replay.py` — a venue year-to-date export walked per asset for
  fold-back opportunities.

Four rule modules run inside the archetypes rather than alone. The first catches
a dead path, a dead subsystem name, an import of a module that is not there, a
citation past the end of the file it names, and a dotted name split across string
literals. The other three carry the numeric, scaffolding and slop families.

```
dev_harness/harness/rules/
    hallucination.py        dead path, dead subsystem, absent import, bad citation, split name
    numeric_guard.py
    scaffolding.py
    slop.py
```

The first module also reads a module name a page writes bare, with no folder in
front of it and no file extension after it. A page names the module a block came
from, and that name is reported when no file of that name is on disk. The check
reads one shape and leaves the name alone wherever else it appears.

```
dev_harness/harness/rules/hallucination.py, in _find_absent_module_headers

read      a code span opening a line, then a dash, then a description
present   a .py or .js file of that name, or a package of that name
silent    a name inside a sentence, inside a fenced block, or mid-sentence
```

The fixtures directory holds the calibration bodies — a good body and a bad body
per archetype. The pair is the control on the gate, and a run of the archetypes
that skips the pair proves nothing about the archetypes.

```
harness_fixtures/<archetype>/known_good.<ext>       exits 0
harness_fixtures/<archetype>/known_bad.<ext>        exits 1
```

### The harness holds six archetypes and eight rule modules

Three counts above are overtaken. Each sentence is quoted whole below, and the
true sentence follows it.

> The harness directory holds twelve modules and the shared report contract.

Overtaken. Its top level holds sixteen Python modules, the shared report
contract among them, and a calibration folder beside them.

> Five archetypes, one per domain:

Overtaken. There are six. The sixth is the truth archetype, and its domain is a
report or a claim: it resolves the checkable claims in a text against the tree.

> Four rule modules run inside the archetypes rather than alone.

Overtaken. Eight run there, beside the package file. The four the sentence names
are all still present and still carry what it says they carry.

```
dev_harness/harness/
    coding_archetype.py      Python, JavaScript, shell and settings source
    docs_archetype.py        markdown
    gui_archetype.py         PySide6 widget source
    ta_archetype.py          indicator source
    truth_archetype.py       a report or a claim
    watchdog_archetype.py    the out-of-process crash watchdog

dev_harness/harness/rules/
    cell_text_fit.py         a cell's drawn text against its column's room
    delegated_canon.py       a canon run handed to a spawned agent
    hallucination.py         dead path, dead subsystem, absent import, bad citation
    numeric_guard.py         an open numeric type guard
    restore_set.py           a restore that stores a choice it never tests
    scaffolding.py           a placeholder or a stub shipped as finished work
    slop.py                  duplicate handling, oversized functions and files
    story.py                 the Storyteller subtype of the documentation archetype
```

### The skills, outside the repository

Twenty skills sit under `~/.claude/skills/`, one directory each with a
`SKILL.md`. They are machine-local and none is committed, so a reader cannot
locate them in this repository. They carry the standing rules that version one
put in a numbered registry.

Five carry authority and process.

| Skill | What it governs |
| --------------------- | ----------------------------------------------- |
| `harness-law` | Who may write code, and which archetype clears which domain |
| `found-it-own-it` | A defect found is a defect fixed in the same unit |
| `branch-discipline` | Work on a branch, never the tree the operator trades from |
| `unit-decomposition` | Sizing a task into units one pass can finish |
| `close-package` | Building the session close archive |

Four carry measurement.

| Skill | What it governs |
| --------------------- | ----------------------------------------------- |
| `ocir` | Observe, calibrate, iterate, repeat, before trusting any zero or pass |
| `two-sided-control` | Driving a check to failure before trusting a pass |
| `job-watch` | Telling a slow background job from a stuck one |
| `log-pruning` | Bounding a log that grows without limit |

Seven carry writing.

| Skill | What it governs |
| --------------------------- | ----------------------------------------- |
| `descriptive-comments-only` | A comment states a technical fact or it does not exist |
| `simple-technical-english` | Plain words and short sentences in everything the operator reads |
| `variable-naming-precision` | Short, functional and exact names |
| `docs-narrative` | Narrative shape, citation density, and where the code sits |
| `hyper-refocus` | Filtering a report against the item and the directives |
| `prompt-distillation` | Decomposing a dense request before the work starts |
| `anti-claudism` | The eight recurring failure behaviours |

Four carry the domain.

| Skill | What it governs |
| ----------------------- | --------------------------------------------- |
| `acervator` | Project posture and operator identity |
| `ta-canon` | An indicator against its published formula |
| `archetype-peer-review` | Building or extending an archetype |
| `hop-protocol` | The handoff file described above |

### The skills are in the tree now

Two sentences above are overtaken. Each is quoted whole below, and the true
sentence follows it.

> Twenty skills sit under `~/.claude/skills/`, one directory each with a
> `SKILL.md`.

Overtaken. Thirty-three skills sit there, one directory each with a `SKILL.md`,
and the four tables above name twenty of them.

> They are machine-local and none is committed, so a reader cannot locate them
> in this repository.

Overtaken. All thirty-three are tracked under `dev_harness/skills/`, one
directory per skill, so a reader of this repository finds every one of them. The
copy outside the repository is the one the Skill tool loads, and the two hold the
same text.

The tracked copies end each line with one byte and the loaded copies end it with
two, so a comparison of the pair strips carriage returns before it reads the
text. Comparing the raw bytes instead names six of the thirty-three as different
when no rule in them differs.

### The hooks, outside the repository

Eight hooks sit under `~/.claude/hooks/`, also machine-local and also not
committed. They are the blocking layer, and six of them deny a call outright
rather than warn about it.
- `archetype_gate.py` — in its pre mode, denies a write whose pending content
  would introduce a high or critical finding the file does not already carry; in
  its post mode, runs the archetype on what was written and reports the verdict.
  It blocks a rise, never a level. It routes a shell script and a workflow file
  to the coding archetype, and for a type with no analyzer it reports that the
  file was not examined rather than saying nothing.
- `block_heavy_run.py` — denies a test run above the memory ceiling, a run while
  another is resident, and `-n auto` outright.
- `block_heredoc.py` — denies a shell command carrying a heredoc.
- `block_unanchored_docstring.py` — denies a Python docstring that argues rather
  than describes: a justification clause, or a sentence naming no identifier from
  its own file.
- `check_directive_drift.py` — denies a dispatch brief that contradicts a pinned
  directive.
- `verify_release_gate.py` — denies a write to either file that carries the
  version when the release-ready record is absent or older than an hour, and
  allows every other path through.

The two files that hook protects, and the record it reads:

```
src/__init__.py         __version__ = resolve_version()
main.py                 current_version = _acervator_version
.release_ready.json     written by the release gate, good for one hour
```

Two add context rather than deny, and both are machine-local, not in the tree:
`prompt_router.py` names the archetype a task will need, and
`session_stop_backstop.py` writes a forensic record of whatever is uncommitted
at a session boundary.

The count reads the directory, not a list. Eight names end in `.py` and each of
those runs. Six saved copies and one cache directory sit beside them, and the
listing marks every entry the count leaves out.

```
~/.claude/hooks/, not committed and not in the tree
    archetype_gate.py                            counted, denies
    block_heavy_run.py                           counted, denies
    block_heredoc.py                             counted, denies
    block_unanchored_docstring.py                counted, denies
    check_directive_drift.py                     counted, denies
    verify_release_gate.py                       counted, denies
    prompt_router.py                             counted, adds context
    session_stop_backstop.py                     counted, adds context
    archetype_gate.py.before_pointer_repair      not counted, a saved copy
    prompt_router.py.before_catalogue_routing    not counted, a saved copy
    prompt_router.py.before_env_conflict         not counted, a saved copy
    prompt_router.py.before_pointer_repair       not counted, a saved copy
    prompt_router.py.before_skill_pointer_fix    not counted, a saved copy
    verify_release_gate.py.before_pointer_repair not counted, a saved copy
    __pycache__/                                 not counted, a directory
```

### The hooks are in the tree now

Three sentences above are overtaken. Each is quoted whole below, and the true
sentence follows it.

> Eight hooks sit under `~/.claude/hooks/`, also machine-local and also not
> committed.

Overtaken. Twenty-eight hook files are tracked in `dev_harness/hooks/`, and the
same twenty-eight run from the machine profile.

> The count reads the directory, not a list. Eight names end in `.py` and each of
> those runs.

Overtaken. Twenty-eight names end in the Python extension. Twenty-two of them run
at an event, and six sit in the directory with no event calling them.

> The skills and the hooks run, and they are not in the tree — a reader who
> searches this repository for them finds nothing, and that is the correct result
> rather than a missing file.

Overtaken. A reader who searches this repository for a hook finds its source, and
`dev_harness/hooks/REGISTRATIONS.md` records the event each one runs at. The
skills are tracked the same way, under `dev_harness/skills/`, one directory per
skill.

### What each hook refuses or reports

Three more sentences above are overtaken, and the listing under them names eight
of twenty-eight. Each sentence is quoted whole below, and the true sentence
follows it.

> They are the blocking layer, and six of them deny a call outright rather than
> warn about it.

Overtaken. Twenty-six of the twenty-eight refuse a call. Twenty-four refuse by
exiting with code 2, and two refuse by printing a deny decision.

> Six saved copies and one cache directory sit beside them, and the listing marks
> every entry the count leaves out.

Overtaken. The tracked directory holds twenty-nine files and no saved copy. The
twenty-ninth is the registration record, which is markdown, so the hook count
counts the twenty-eight Python files. The machine profile still carries six
saved copies and a cache directory beside its own set.

> Two add context rather than deny, and both are machine-local, not in the tree:

Overtaken. Those two still only report. Both are in the tree with the rest, and
every other file in the directory refuses something.

The hook count, read against the registration record:

```
29  tracked files in the hooks directory
28  of them end in the Python extension
 1  REGISTRATIONS.md, the record of the event each hook runs at
22  named in the hooks block of the machine settings file, so an event calls them
 6  on disk, in no block, called by no event
```

The twenty-two an event calls, and what each one refuses or reports:

```
archetype_gate.py              --pre refuses a write that adds a high or critical finding
                               --post reports the archetype's verdict as context
verify_release_gate.py         refuses a write to either version file when the
                               release-ready record is absent or over an hour old
block_unanchored_docstring.py  refuses a docstring that argues instead of describing
block_heredoc.py               refuses a shell command carrying a heredoc
block_heavy_run.py             refuses a test run over the memory ceiling, a run while
                               another is resident, and an unbounded worker count
block_custom_test_run.py       refuses a run of the source-shape parity tests, and a
                               run wide enough to include them
block_table_search.py          refuses a search for a fact the conversion table states
block_new_test.py              refuses the creation of a new test file
check_directive_drift.py       refuses a brief that contradicts a pinned directive
block_off_item.py              refuses a dispatch that does not name the locked item
block_missing_skills.py        refuses a brief that omits a skill the work requires
block_uncanonized_workflow.py  refuses a commissioning brief that skips a workflow step
block_unreachable_done.py      refuses a brief whose proof cannot observe what it builds
block_narrowed_bar.py          refuses a brief whose acceptance bar drops a term the
                               directive carries
block_subsystem_anchor.py      refuses a general-scope brief whose subject is one
                               subsystem
block_alt_grounding.py         refuses a brief grounded in anything but the issues, the
                               manual and the skills
block_detour.py                refuses a new tool file, and a brief that inserts a
                               reading step
block_coined_instrument.py     refuses making an instrument this project never imported
block_unanchored_claim.py      refuses a reply that predicts a result it has not measured
block_long_reply.py            refuses a reply longer than the report format, while an
                               item is locked
prompt_router.py               reports the archetype a prompt's task needs, and the
                               skills to load; refuses nothing
session_stop_backstop.py       reports what is uncommitted at a session boundary;
                               refuses nothing
```

The six no event calls, and what each one would refuse:

```
block_banned_words.py                 the vocabulary the operator banned, in a reply
                                      and in a brief
block_deflection.py                   a reply handing a technical decision back to him
block_delegated_canon.py              a workflow script spawning an agent to run a
                                      canon command
block_conversion_table_grounding.py   a brief grounding a unit to the closed conversion
                                      table
block_stand_in_without_source.py      a brief whose stand-in names nothing the real
                                      source serves, and a proof ending at an empty state
block_screen_point_input.py           a script posting input at a screen point, or
                                      reading the window under one
```

Each of the six needs an entry in the settings file before it fires, and the
registration record carries the entry each one wants.

### Where each layer resolves

The harness is in the tree, so every claim above about it resolves to a path a
reader can open. The skills and the hooks run, and they are not in the tree —
a reader who searches this repository for them finds nothing, and that is the
correct result rather than a missing file. The contrast with version one is the
point: version one's subject has no source anywhere, in this repository or on
disk.

### A credential written into a page

This repository is public. The documentation archetype reports a credential
written into a markdown page, at the severity that makes the page fail, under
rule id DOC014.

```
dev_harness/harness/docs_archetype.py, in _run_credentials

reads     every markdown page whole, fenced blocks included
reports   one high finding per credential, naming its shape and its line
silent    a placeholder, a field name, a credentials file path, a short value
```

Six shapes are read, and each one is the shape a credential takes in this
application's own files.

```
a labelled secret         src/exchange/api_logger.py, _SENSITIVE_LABEL
a bearer token            src/stocks/robinhood_broker.py, BEARER_PREFIX
a private key block       src/core/encryption.py, EC_PEM_HEADER
a Coinbase key name       src/exchange/ccxt_connector.py, in sync_connect
a hex private key         contracts/deploy.py
a password in a URL       src/exchange/api_logger.py, in _redact
```

The finding names the shape and the line and never the secret, because a
finding is pasted into a report and a report is read in public. The repair is
to delete the credential from the page and rotate it at the venue.

Before this rule the archetype raised a prose finding to high when its check
name began with a security family. The installed prose linter registers 122
checks across 23 families and none of them is a security family, so that branch
had no subject and a page carrying a credential exited zero.

```
harness_fixtures/docs_archetype/credential_bad.md     exits 1
harness_fixtures/docs_archetype/credential_good.md    exits 0
```

The good body carries the near-miss shapes the rule must not report, so the
pair reads both sides of the rule rather than one.

## Related parts

- [09-updates-and-versioning.md](09-updates-and-versioning.md) — the release gate
  in full, and where the version number comes from.
- [12-adr-index-and-glossary.md](12-adr-index-and-glossary.md) — where decisions
  are recorded, and the vocabulary this manual uses.
