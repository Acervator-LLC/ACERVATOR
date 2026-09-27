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

A root-file inventory test records why the handoff sits at the root rather than
in a directory: the drift check looks for it there, and a fresh clone has to find
its orientation without being told where to look. Each root file in that
inventory carries a reason naming a mechanism, and a new root file without one
fails the check.

```python
def test_the_inventory_names_every_tracked_root_file() -> None: ...  # tests/test_repo_root_inventory.py
def test_the_inventory_names_no_file_that_has_left() -> None: ...
def test_every_inventory_entry_carries_a_reason() -> None: ...
```

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
RULE_META = {...}       # src/core/rule_registry.py, 35 ids, R1 through R35
CORE_RULES = {r for r, m in RULE_META.items() if m["protection"] == "CORE"}
VALID_STATES = {"LOCKED", "UNLOCKED", "SUSPENDED", "DEPRECATED"}

class RuleEntry: ...
class RuleRegistry: ...
def parse_rule_command(...): ...
```

The suspend call refuses a CORE id. Driven both ways against a registry file in a
temporary directory, R1 draws a refusal and stays LOCKED while R2 moves to
SUSPENDED. The refusal is a real one rather than a declared one.

```python
def suspend(self, rule: str, reason: str, expires: str = "") -> str: ...     # src/core/rule_registry.py
```

Nothing in the product reads any of it. The registry path resolves into a
top-level directory that no commit in this repository has ever added. An import
scan over 957 Python files — parsing each file and reading its import nodes,
rather than matching text — finds one importer,
`tests/test_rule_registry_validation.py`, which is also the only caller of any
symbol in the module. The same scan against `src/core/log_paths.py` returns three
importers, so the instrument does find an importer where one exists.

```python
REGISTRY_PATH = ROOT / "sadp" / "RULE_REGISTRY.json"        # src/core/rule_registry.py
# sadp/ is not in the tree, so REGISTRY_PATH resolves to nothing
```

The module's own docstring says as much. The ids name nothing the running
program consults, and they carry no authority.

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
src/gui/simulator.py                                         nothing
src/core/log_paths.py                       the commit that added it
```

The live file behind the second row is `src/gui/simulator_tab/simulator_tab.py`.
Version one's R-numbers were never live and must not be cited as though they
were.
The Simulator rebuild removed this file; it is not in the tree.

What did ship was a set of references to it, and one test module holds the line
against their return. Two front-door documents and the build config may not name
the protocol or its battery, no shipped module may import it, and no build may
carry a path naming it. Fifty-one annotation comments naming those ids survive
in the source across 21 files, and they bind nothing.

`tests/test_no_dead_sadp_references.py` — the seven checks

```python
def test_sadp_directory_is_absent() -> None:
def test_build_config_names_no_dead_subsystem(name: str) -> None:
def test_front_door_docs_name_no_dead_subsystem(name: str) -> None:
def test_readme_says_the_harness_was_retired() -> None:
def test_no_shipped_python_imports_the_dead_package() -> None:
def test_no_build_datas_pair_ships_a_dead_subsystem() -> None:
def test_every_shipped_tool_imports() -> None:
```

The module records both directions of its own control: reverting the five files
to their earlier state failed four of the seven, and restoring them passed all
seven.

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

The fixtures directory holds the calibration bodies — a good body and a bad body
per archetype. The pair is the control on the gate, and a run of the archetypes
that skips the pair proves nothing about the archetypes.

```
harness_fixtures/<archetype>/known_good.<ext>       exits 0
harness_fixtures/<archetype>/known_bad.<ext>        exits 1
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

### Where each layer resolves

The harness is in the tree, so every claim above about it resolves to a path a
reader can open. The skills and the hooks run, and they are not in the tree —
a reader who searches this repository for them finds nothing, and that is the
correct result rather than a missing file. The contrast with version one is the
point: version one's subject has no source anywhere, in this repository or on
disk.

## Related parts

- [09-updates-and-versioning.md](09-updates-and-versioning.md) — the release gate
  in full, and where the version number comes from.
- [12-adr-index-and-glossary.md](12-adr-index-and-glossary.md) — where decisions
  are recorded, and the vocabulary this manual uses.
