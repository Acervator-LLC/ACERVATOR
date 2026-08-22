# touchset — refuse a unit's bad file before the first edit

`dev_harness/touchset.py` measures the files a unit is about to touch. It
refuses a touch set that cannot succeed. It then re-measures the same
files on the island and refuses a change that made them worse.

It only measures and refuses. It fixes nothing. It edits no file it
inspects. It writes one file, the pin.

It is not a replacement for the archetypes. Every `passed` it prints is
the archetype's own `passed`, read through that archetype's published
`to_dict()`. It never reports a verdict an archetype did not produce.

---

## The two commands

### Baseline — run this BEFORE the first edit

```
python -m dev_harness.touchset baseline <path> [<path>...] [--pin FILE] [--root DIR]
```

For each path it measures:

- every archetype the gate routes to that path, plus the watchdog
  archetype for Python;
- the file's line-ending kind;
- the file's count of forbidden directives, per spelling;
- the file's SHA-256, size and byte counts.

It writes a JSON pin. It exits non-zero, and writes no pin, if any path
is unusable or any file is already red.

### Check — run this BEFORE promotion

```
python -m dev_harness.touchset check --pin FILE --against DIR
```

It re-measures every pinned path inside the island. It compares each one
to the PIN, never to zero. It then sweeps the island for files the pin
never saw and measures those as the unit's own new work.

---

## Options

| Option | Effect |
|---|---|
| `--root DIR` | The tree the baseline paths are relative to. Default: the repo. |
| `--pin FILE` | Where the pin is written or read. Default: `tools/.touchset_pin.json`. |
| `--only MOD...` | Narrow the archetype set. Records `complete: false`. |
| `--jobs N` | Archetypes run per file at once. Default 4. |
| `--timeout N` | Seconds one archetype may take on one file. Default 1800. |
| `--baseline-root DIR` | The tree the pin came from, when the pin's own record has moved. |
| `--new-file-limit N` | How many never-pinned files `check` will measure. Default 25. |
| `--accept-reduced` | Accept a `--only` pin as a pass. Records that the result is partial. |

The default run is COMPLETE. A default that skips is the failure this
tool exists to remove.

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Everything was measured. Nothing fired. |
| 1 | A gate fired. Something is wrong with the work. |
| 2 | The run could not be made. Something is wrong with the command or the pin. |

---

## Every refusal, and what to do about it

### Exit 2 — the run could not be made

| Line | What it means | What to do |
|---|---|---|
| `MISSING <path>` | No such file. | Fix the path. A path that does not exist is refused BEFORE any archetype runs, because all five archetypes return exit 0 and `passed: true` on a path that is not there. |
| `NOT-A-FILE <path>` | The path is a directory. | Name the file, not the folder. |
| `OUTSIDE-ROOT <path>` | The path resolves outside `--root`. | Use a path inside the tree being measured. An absolute path outside the root used to be pinned as typed, and `check` then re-measured the ORIGINAL file instead of the island copy. |
| `CASE-MISMATCH <path>` | The spelling differs from the disk. | Use the on-disk spelling. Windows ignores case; a case-sensitive host does not, and the Mac Mini is one. |
| `no routing rule at ...` | `.claude/hooks/archetype_gate.py` cannot be loaded. | Restore the hook. This tool reuses the gate's routing and never substitutes a private copy. |
| `... is not readable JSON` | The pin is corrupt. | Re-run `baseline`. |
| `... is pin_version N` | The pin predates this tool. | Re-run `baseline`. |
| `... fails its own integrity digest` | The pin changed after it was written. | Re-run `baseline`. Do not hand-edit a pin. |
| `... pins ZERO files` | The pin is empty. | Re-run `baseline`. An empty pin compares nothing and would report OK. |
| `... is self-inconsistent` | The pin claims `complete` beside a narrowing `only`. | Re-run `baseline`. A pin that claims both suppresses its own warning. |
| `the pin's baseline root ... is not available` | The sweep cannot tell a new file from an old one. | Pass `--baseline-root`, or re-run `baseline`. This refuses rather than skipping the sweep, because skipping it is how the MODE 2 suppression got through. |

### Exit 1 — a gate fired

| Line | What it means | What to do |
|---|---|---|
| `<file>: <archetype> passed=False` | The archetype's own verdict is red. | At baseline: DROP the file from the touch set, or fix the red first as its own unit. At check: fix what the unit broke. |
| `<file>: <archetype> COULD NOT RUN` | The archetype raised, exited, or returned a report this tool cannot read. | Fix the archetype invocation. A verdict the harness did not produce is not a pass. |
| `NOTHING MEASURED` | Archetypes route to the file and none of them ran. | Widen `--only`. A filter that grades nothing is not a pass. |
| `SUPPRESSION ADDED` | A forbidden directive count rose against the pin, in a CODE file. | Remove the directive and fix the finding. A pre-existing count is not this unit's to clear; an increase always is. |
| `SUPPRESSION IN A NEW FILE` | A CODE file the pin never saw carries a directive. | Remove it. A new file starts at zero. |
| `LINE ENDING FLIPPED` | The file's line-ending kind changed. | Rewrite the file in its original kind. Read AND write with `newline=""`. |
| `NEW FILE LINE ENDING` | A new file defies its directory's measured majority. | Match the directory. The repo has no repo-wide ending. |
| `TOOL STOPPED RUNNING` | An archetype ran fewer lint tools than at baseline. | Reinstall the tool. An archetype reports `passed=True` when its tools are absent, so that verdict is a scan that did not happen. |
| `PATH VANISHED` | A pinned file is not on the island. | Restore it, or re-baseline the real touch set. |
| `PATH REPLACED` | A pinned file is now a directory. | Restore the file. |
| `TOO MANY NEW FILES` | The island holds more unpinned files than the limit. | Narrow the island, or raise `--new-file-limit` deliberately. |
| `this pin is REDUCED` | The pin was made with `--only`. | Re-run `baseline` without `--only`, or pass `--accept-reduced` to record that a partial result was accepted. |
| `... exceeded Ns` | One archetype passed its wall-clock ceiling. | Re-run, or raise `--timeout`. An archetype runs in a thread and a thread cannot be killed, so the process exits rather than hanging with no verdict. |

---

## The four measured incidents

All four were measured on 2026-08-13. Each cost a full review round.

**MODE 1 — a red file in the touch set.** `src/gui/bot_wizard.py` entered
a touch set already carrying 4 coding highs on the unmodified live tree.
Three were unfixable inside the unit's authority. The whole unit blocked
on a file it did not need. Nothing asked before the first edit.
`baseline` asks, and refuses, in about 10 seconds.

**MODE 2 — a suppression added and unreported.** A `# noqa: BLE001`
landed in a NEW test file. It survived the build's own gate, because an
archetype keys `passed` on high and critical findings, and an unused
`noqa` lands at medium. Measured separately: a single `# noqa: F401`
REMOVES a 90%-confidence vulture HIGH from the report entirely. So
`passed` cannot see its own blinding, and counting directives is the
only way to catch this. Because the incident happened in a file that did
not exist at baseline, `check` also sweeps for files the pin never saw.

**MODE 3 — an archetype exits 0 on a path that does not exist.** Measured
on all five archetypes: coding, ta, watchdog, gui and docs each return
exit 0 AND `passed: true` for a target that is absent from the tree. The
reason is recorded only in `errors[]`, which the exit code discards. A
verification that scanned nothing reports success. It bit the referee: a
positive control run on a mistyped fixture path returned 0 and briefly
read as a defect that did not exist. The archetypes may not be edited,
so this tool refuses a path that does not exist before it reads any
verdict.

**MODE 4 — a line-ending kind flip.** Twice in one session an editor
rewrote a CRLF file as LF. One was a 2,099-line test file. Unnoticed,
that is a 27,348-line diff hiding the real change. Measured:
`src/**/*.py` is LF 95 / CRLF 68, `tests/*.py` is LF 149 / CRLF 51. The
repo has no repo-wide ending, so the rule is per-file preservation.

---

## What it costs

Measured on a realistic two-file touch set — `scrumming_bot.py` at
14,154 lines plus `bot_live_settings.py` at 4,494:

- `baseline` 66 seconds.
- `check` 76 seconds, including the new-file sweep.
- The `bot_wizard` refusal costs 77 seconds and saves a review round.

About 93% of that time is inside `coding_archetype`, which runs six
tools in series. This tool may not change that. Cost scales roughly
linearly with touch-set size.

Run `baseline` once when the unit opens. Run `check` once before
promotion. Both modes are pre-edit or pre-promotion conditions, so that
is enough. Running `check` on every island iteration is what gets it
skipped.

---

## WHAT IT CANNOT CATCH

Read this as carefully as the rest. A gate oversold is worse than a gate
absent.

**1. Whether the change is complete.** A unit that converts 7 of 10
sites and leaves 3 lands green on every check here. The 3 untouched
sites were green before and are green after. Nothing in the pin encodes
intended scope. This is a semantic argument, not a measurement.

**2. Whether a docstring tells the truth.** A docstring can assert an
invariant the code does not implement, and every gate stays green. No
archetype in the routed set checks prose against behaviour, and this
tool only aggregates archetype verdicts. This is the highest-value class
still costing review rounds, and no counting instrument addresses it.

**3. Whether the touch set is the RIGHT set.** This tool validates only
the paths it is given, plus new files. A file that SHOULD have been in
the unit and was omitted is invisible. It performs no coupling analysis.
It will pass a unit that freshens a cache and never touches the field
the consumer reads.

**4. Whether any edit is correct.** Out of scope, by design.

**5. A suppression spelled outside the counted set.** The set is: noqa,
nosec, type: ignore, pyright: ignore, ruff: noqa, pylint: disable,
flake8: noqa, nosemgrep, mypy: disable-error-code, mypy: ignore-errors,
pylint: skip-file. Anything else is not counted. Vale's own
`vale off` marker is not in the set.

**5b. A suppression in a file that is not code.** Directive counts are
measured and recorded for every file, but only CODE files can be
refused for them. No checker in the harness reads Markdown, so a
directive quoted in prose silences nothing. This tool refused its own
documentation until that was corrected.

**6. A pin taken AFTER the edits.** The pin records a SHA-256 per file
and the git HEAD it was taken at, but nothing proves the baseline ran
before the first edit. Run `baseline` first. The tool cannot make you.

**7. A determined forgery of the pin.** The pin's digest catches
truncation, corruption and casual hand-editing. It is not a signature.
Anyone who can edit the pin can recompute the digest.

**8. A repointed symlink.** Symlinks could not be created on this host,
so no symlink branch is claimed or controlled. A pinned path that is a
symlink is measured at whatever it points to at the time. Re-test this
on a host where symlinks can be made.

**9. A new file outside the routed suffixes.** The sweep looks at `.py`,
`.pyw`, `.pyi`, `.md` and `.markdown`. A new `.json` or `.txt` is not
measured.

**10. The gap this tool inherits on purpose.** It reuses the gate's
routing rather than inventing its own. The gate's `_QT_BASES` set omits
`QWizard` and `QWizardPage`, so `src/gui/bot_wizard.py` never reaches
`gui_archetype` and the 2 gui highs the MODE 1 incident recorded do not
appear here. A private mapping would have hidden that gap. Fixing the
gate fixes this tool for free.

**11. Whether an archetype's findings are correct.** That is the
archetype's domain. This tool never overrides a verdict and never
produces one.

**12. A refusal nobody thought to build.** The sabotage suite disables
refusals that exist. It cannot surface a refusal that was never written.
The MODE 2 new-file miss was exactly that: every control passed, because
every control tested a pinned file, and no control asked what happens to
a file that was never pinned.
