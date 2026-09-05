# Conceptual Hopscotch

Reference. Three subjects that a reader meets in the older manual and cannot
find in the code: the handoff file that carries a session across a context
boundary, the rule registry no running module reads, and the development
protocol, which exists in two versions — one with no source in this repository,
one running today.

## The handoff file

`ACERVATOR_HOP8.md` at the repository root is the current handoff and the only
one this manual describes. The earlier `ACERVATOR_HOP*.md` files at the root
hold archives of sessions that closed, and nothing in them binds.

`tests/test_repo_root_inventory.py` records why the handoff sits at the root
rather than in a directory: `tools/hop_check.py` globs `ACERVATOR_HOP*.md`
there, and a fresh clone has to find its orientation without being told where to
look. Each root file in that inventory carries a reason naming a mechanism, and
a new root file without one fails the check.

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
- Cited paths that no longer exist. `TRACKED` matches a backticked path under
  `src`, `tests`, `tools`, `docs`, `desktop`, `dev_harness`, `harness_fixtures`
  or `.github`.
- Cited commits that no longer resolve, matched as a backticked hex string of
  seven characters or more and checked with `git cat-file -t`.

Any one of the three returns exit 1. Run against the tree, the report reads 107
commits since the handoff was written, three paths declared absent on purpose,
no missing path and no unresolved commit, and it exits 1 on the commit count
alone.

`declared_absent` reads the paths under the `## CITED AS ABSENT` heading and
drops them from the missing-path count. A path under that heading is skipped even
when it sits on disk, which makes the heading a record of a deliberate citation
rather than a check on one.

### The sort key picks the wrong file at ten

`newest_hop` sorts the glob by `Path.stem` as a string and takes the last entry.
Every handoff suffix holds one digit today, and the answer is correct. Driven
with a two-digit name added, `ACERVATOR_HOP10` sorts ahead of `ACERVATOR_HOP2`,
the last entry stays `ACERVATOR_HOP8.md`, and the drift report then describes a
superseded file. Driven again with only the two newest names present, the answer
is the same. The check needs a numeric key before a tenth handoff exists.

## The rules registry

`RULE_META` in `src/core/rule_registry.py` declares 35 rule ids, R1 through R35,
across ten lettered groups. `RuleRegistry` holds one `RuleEntry` per id in one of
the four `VALID_STATES` — LOCKED, UNLOCKED, SUSPENDED and DEPRECATED — and
`parse_rule_command` turns a `RULE` line into a call on it. `CORE_RULES` derives
the five ids marked CORE: R1, R5, R10, R11 and R12.

`suspend` refuses a CORE id. Driven both ways against a registry file in a
temporary directory, `suspend("R1")` returns a refusal and leaves R1 LOCKED,
while `suspend("R2")` moves R2 to SUSPENDED. The refusal is a real one rather
than a declared one.

Nothing in the product reads any of it. `REGISTRY_PATH` resolves to
`RULE_REGISTRY.json` inside a top-level `sadp` directory, and no commit in this
repository has ever added a path under that directory. An import scan over 957
Python files — parsing each file and reading its import nodes, rather than
matching text — finds one importer, `tests/test_rule_registry_validation.py`,
which is also the only caller of any symbol in the module. The same scan against
`src/core/log_paths.py` returns three importers, so the instrument does find an
importer where one exists.

The module's own docstring says as much. The ids name nothing the running
program consults, and they carry no authority.

## Version one of the protocol

The manual this one replaces documents a development protocol across 51 pages,
under 26 file names and 77 numbered rules. None of it has a source in this
repository. `git log --all --diff-filter=ADR --name-only` limited to paths under
`sadp/` returns nothing, while the same query naming `src/core/log_paths.py`
returns the commit that added it. The two file names the version sweep still
reads, `RAIntSimBat.py` and `RULE_REGISTRY.json`, return nothing on the same
query, and so does `src/gui/simulator.py`, the other half of one of those
comparisons — the live file is `src/gui/simulator_tab/simulator_tab.py`.

The id overlap with the live registry is a coincidence. The 42 ids from R36
upward have no entry in `RULE_META` at all, and of the 35 that do collide, not
one describes the same rule: the older manual's first rule is a lock-state
default where the registry's is a target increment after a fold, and its third is
an append-only log where the registry's is a targeting-mode reset. The two are
unrelated id spaces that share a shape. Version one was never built and its
R-numbers were never live. `docs/audits/manual-original-parts-audit.md` carries
the full count.

What did ship was a set of references to it. `tests/test_no_dead_sadp_references.py`
holds the line: `pyproject.toml`, `README.md` and `CONTRIBUTING.md` may not name
the protocol or its battery, no module under `src/` or `tools/` may
import it, and `datas_candidates` in `tools/spec_common.py` may not ship a path
naming it. The test module records both directions of its own control: reverting
the five files to their earlier state failed four of its checks, and restoring
them passed all seven. Fifty-one annotation comments naming those ids survive in
`src/` across 21 files, and they bind nothing.

## Version two of the protocol

Version two is the system running now. It has three layers, and only the first
is in this repository.

### The harness, in the repository

`dev_harness/harness/` holds twelve modules and the shared report contract. Each
runs as `python -m dev_harness.harness.<name> <path>` and reports a `passed`
boolean, exiting non-zero when `passed` is false. `passed` in
`dev_harness/harness/report.py` needs five conditions and the first four concern
the run rather than the findings: an unhandled file type, an unscanned target, an
analyzer that did not report `ok`, and a recorded error each hold it false. A
`refuse_silent_failure` call around every subprocess raises on a tool that wrote
to standard error and exited non-zero with empty output, which is how an
installed-but-unconfigured linter used to report a clean run.

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

The gate and the ledger:

- `check_release_readiness.py` — the release gate. It runs the suite under
  `tests/`, runs each archetype against its `known_good` fixture, and reads the
  claim ledger. It declines to declare a release ready when a step was skipped or
  when a green pytest run collected nothing. No copy lives under `tools/`; the
  older `tools/check_release_readiness.py` and the whole `tools/harness/`
  directory are gone from the working tree.
- `claim_ledger.py` — one JSONL row per claim, each carrying a status of `open`,
  `verified` or `refuted`, which leaves a claim without a measurement visible.

Four analysis tools, each answering one question about live behaviour:

- `decision_diff.py` — the live decision diff.
- `manual_fire_frame_check.py` — the Manual Fire target-frame split against live
  state.
- `reconcile_position_values.py` — displayed position values against their own
  inputs.
- `ytd_compounding_replay.py` — a venue year-to-date export walked per asset for
  fold-back opportunities.

Four rule modules under `dev_harness/harness/rules/` run inside the archetypes
rather than alone: `hallucination.py` for a dead path, a dead subsystem name, an
import of a module that is not there, a citation past the end of the file it
names, and a dotted name split across string literals; `numeric_guard.py`,
`scaffolding.py` and `slop.py` for the other three families.

`harness_fixtures/` holds the calibration bodies — a `known_good` and a
`known_bad` per archetype. The pair is the control on the gate: the good fixture
exits 0 and the bad one exits 1, and a run of the archetypes that skips the pair
proves nothing about the archetypes.

### The skills, outside the repository

Nineteen skills sit under `~/.claude/skills/`, one directory each with a
`SKILL.md`. They are machine-local and none is committed, so a reader cannot
locate them in this repository. They carry the standing rules that version one
put in a numbered registry.

- Authority and process — `harness-law` (who may write code and which archetype
  clears which domain), `found-it-own-it` (a defect found is a defect fixed in
  the same unit), `branch-discipline` (work on a branch, never the tree the
  operator trades from), `unit-decomposition` (size a task into one-pass units),
  `close-package` (build the session close archive).
- Measurement — `ocir` (observe, calibrate, iterate, repeat, before trusting any
  zero or pass), `two-sided-control` (drive a check to failure before trusting a
  pass), `job-watch` (tell a slow background job from a stuck one),
  `log-pruning` (bound a log that grows without limit).
- Writing — `descriptive-comments-only`, `simple-technical-english`,
  `variable-naming-precision`, `hyper-refocus` (filter a report against the item
  and the directives), `prompt-distillation` (decompose a dense request before
  starting), `anti-claudism` (eight recurring failure behaviours).
- Domain — `acervator` (project posture and operator identity), `ta-canon`
  (an indicator against its published formula), `archetype-peer-review` (build or
  extend an archetype), `hop-protocol` (the handoff file described above).

### The hooks, outside the repository

Seven hooks sit under `~/.claude/hooks/`, also machine-local and also not
committed. They are the blocking layer, and five of them deny a call outright
rather than warn about it.

- `archetype_gate.py` — in its pre mode, denies a write whose pending content
  would introduce a high or critical finding the file does not already carry; in
  its post mode, runs the archetype on what was written and reports the verdict.
  It blocks a rise, never a level.
- `block_heavy_run.py` — denies a test run above the memory ceiling, a run while
  another is resident, and `-n auto` outright.
- `block_heredoc.py` — denies a shell command carrying a heredoc.
- `block_unanchored_docstring.py` — denies a Python docstring that argues rather
  than describes: a justification clause, or a sentence naming no identifier from
  its own file.
- `verify_release_gate.py` — denies a write to `src/__init__.py` or `main.py`
  when `.release_ready.json` is absent or older than an hour, and allows every
  other path through.

Two add context rather than deny: `prompt_router.py` names the archetype a task
will need, and `session_stop_backstop.py` writes a forensic record of whatever
is uncommitted at a session boundary.

### Where each layer resolves

The harness is in the tree, so every claim above about it resolves to a path a
reader can open. The skills and the hooks run, and they are not in the tree —
a reader who searches this repository for them finds nothing, and that is the
correct result rather than a missing file. The contrast with version one is the
point: version one's subject has no source anywhere, in this repository or on
disk.

## Declared means wired

Source: LEGACY, the fourteen-part manual, Part 7b "Rules Registry", page 11.

The legacy registry catalogues 77 numbered rules. The registry that exists in
this repository defines 35, the numbers above 35 have no entry at all, and of
the identifiers that do collide, not one describes the same rule. The two are
unrelated namespaces that happen to share a number space, and the legacy one is
the one with no code. Its numbers are not live and must not be cited as though
they were.

One entry survives that comparison, because it is a standing engineering rule
rather than a numbered claim, and because this repository can show it working.

**A declared interface that nothing invokes is a defect, not a placeholder.**

The measured case is the gate pair in
[07-indicators.md](07-indicators.md#gate-call-site-activation). Two gate classes
existed, sat in the chain, and returned pass on every tick, because the context
field each one reads defaults to `0.0` and no call site filled it. The gate was
declared. The gate was not wired. Nothing failed, nothing warned, and the only
visible symptom was a live trading result that did not move.

The same shape appeared a second time in the bot configuration. One dataclass
served two bot modes, so a field meaningful to one mode could be passed into the
other, sit on the object, and mean nothing. The field existed. The behaviour did
not. The repair was structural rather than local: a factory that owns
construction, a field manifest per mode, refusal of a mode-foreign field at
build time, and a test that bans direct construction outside the factory.
`make_bot_config` at `src/trading/container/config.py:578` is that factory, and
`_BOT_CONFIG_SCRUMMING_ONLY_FIELDS` and `_BOT_CONFIG_EXTRACTOR_ONLY_FIELDS` are
those manifests.

The rule generalises to a check anyone can run. Enumerate every declared thing
of a kind — every gate class, every construction site, every voter — and assert
that each one is reached. `tests/test_gate_coverage.py` does exactly that. A
rule written as prose cannot fail. A rule written as an enumeration fails the
moment somebody adds the eighteenth gate and forgets the chain.

Two further declarations in this repository are in the unwired state right now,
and neither is hidden: `apply_profit_fold` in `src/trading/profit_fold.py`
records in its own docstring that no module imports it, and
`src/trading/poa_tournament.py` has no caller anywhere, including in the tests.
Naming them is the rule working.

## Related parts

- [09-updates-and-versioning.md](09-updates-and-versioning.md) — the release gate
  in full, and where the version number comes from.
- [12-adr-index-and-glossary.md](12-adr-index-and-glossary.md) — where decisions
  are recorded, and the vocabulary this manual uses.
