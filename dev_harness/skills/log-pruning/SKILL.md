---
name: log-pruning
description: Bound a log that grows without limit, and retire artefacts that never expire, without deleting evidence or touching a file the running application holds open. Use when a log directory grows unbounded, before adding any new writer, and before scaling an instrumentation network.
---

# Log Pruning

## The measured state, 2026-08-13

```
TOTAL                        12.58 GB across 3,986 files
console/system.log            9.09 GB   ONE file, NO rotation
signals/session.jsonl         2.02 GB   ONE file, NO rotation
trade/ gate + diagnostics     0.56 GB   ROTATES, capped ~52 MB x 10
sim/runs/                     0.63 GB   per-run artefacts, never expire
free on C:                     389 GB of 931 GB
```

**Two files hold 88% of the total.** Disk was never at risk. The cost is
elsewhere: a 9 GB file cannot be opened, searched or shipped, so the evidence
it holds is effectively unreachable.

## THE RULE THAT DOES MOST OF THE WORK

**Rotation already exists in this repository and it works.** Name it exactly,
because the codebase has THREE writers and only one is bounded:

| writer | mechanism | measured |
|---|---|---|
| `gate.log`, `trade.log`, `pnl/<day>.log` | `NDJSONWriter`, `src/core/logging_engine.py:99` — `_max_bytes`, `_backup_count`, `Path.replace()` | BOUNDED, holding at ~52 MB x 5 |
| `console/system.log` | plain `logging.FileHandler`, same file, line 370 | **9.09 GB** |
| `signals/session.jsonl` | `src/core/signal_contract.py:612` | **2.02 GB** |

Two writers never received a bound, and that is the entire defect. One file,
two mechanisms, and the unbounded one sits 60 lines from the bounded one.

**`NDJSONWriter` IS NOT A DROP-IN FOR A LOGGING HANDLER.** It writes NDJSON
records. `system.log` is a `logging` stream, so its bound is the standard
library's `RotatingFileHandler`. Copy the PARAMETERS that are proven here
(~52 MB, 5 backups), not the class.

**THE ROTATION BUG THIS REPO ALREADY PAID FOR — do not reintroduce it.**
`logging_engine.py:150-159` records it: `Path.rename()` raises WinError 183 on
Windows when the destination exists, where POSIX silently overwrites.
Measured consequence: **350,470 `gate.log.4 -> gate.log.5` warnings** over
three days, and the writer stalled completely because rotate-then-append
could not get past the `.4 -> .5` shift. `Path.replace()` is the documented
cross-platform overwrite primitive and is what the fix uses. Any new rotation
on this platform must use `replace`, never `rename`.

**FINDING THE PRECEDENT IS ITSELF A TRAP.** Measured 2026-08-14: a grep for
`RotatingFileHandler|maxBytes|backupCount|rotate` reported NOTHING in `src/`
and I read that as "no rotation exists". Two errors at once — the code uses
`_max_bytes` and `_backup_count`, so the camelCase patterns missed it, and the
one pattern that DID match was cut off by `head -12` because `.claude/`
sorts before `src/`. **A truncated search is not an absent result.** Count the
matches before trusting a zero, and search snake_case and camelCase both.

## NEVER PRUNE A FILE THE RUNNING APPLICATION HOLDS OPEN

Windows is not Linux. A live handle makes delete and rename fail, and
truncating a file underneath an open append handle corrupts the writer's
offset rather than freeing space.

The operator trades real money on 37 bots through this process. A pruning
step that disturbs its logging can take the process with it.

- **Never** delete, rename, move or truncate a log while the app runs.
- Rotation belongs INSIDE the writer, which owns the handle and can close,
  rename and reopen in the right order.
- An external cleanup tool may only touch files the app has already closed —
  a rotated `.1`-`.5`, a completed run directory, a previous session.
- If a size must be reported live, `stat` it. Reading metadata is safe;
  writing is not.

## THREE DIFFERENT PROBLEMS. Do not solve them with one hammer.

| shape | example here | the fix |
|---|---|---|
| **Unbounded stream** — one file, appended for ever | `console/system.log`, `signals/session.jsonl` | size-based rotation with a retained count, inside the writer |
| **Per-run artefact** — a new directory each run, none expire | `sim/runs/*` | a retention policy: keep the newest N runs, or anything newer than D days |
| **Evidence** — written to be read later | audit reports, post-mortems, ledgers | NOT logs. Never subject to either rule above |

Applying rotation to evidence destroys the record. Applying retention to a
live stream leaves the current file unbounded. The shapes are different.

## INSTRUMENTATION SCALES ITS OWN LOG. Size it before you scale it.

`signals/session.jsonl` is the emitter network's own file. **2.02 GB from 40
pins.** The stated target is a thousand.

Multiplying pin count multiplies write volume. A network built to find
problems becomes the problem, and it does so silently because nobody watches
the monitor's own footprint.

**Before adding an observation point, state its write cost per hour.** Before
scaling a network, multiply. An instrumentation plan with no volume figure is
not finished. See `two-sided-control` rule 4 — a measurement with no defined
interpretation is not evidence, and a measurement nobody can afford to store
is not a measurement.

## WHAT MUST NEVER BE PRUNED

- Anything an audit or report CITES. A finding whose evidence was deleted is
  no longer verifiable, and re-deriving it costs more than the disk did.
- Post-mortems and crash artefacts. They exist because the event is rare.
- The ledger that records what was promoted to live.
- Anything under `~/.acervator/` — that is state, not logs. `bot_state.json`
  is the stone tablet and is READ-ONLY to every tool.

## BEFORE DELETING ANYTHING

1. **Measure first.** Total, per directory, top files by size. Name what is
   actually large rather than guessing.
2. **Confirm the writer is closed.** A rotated or dated file, not the current
   one.
3. **Say what will go and how much it frees**, then do it. Deletion is
   irreversible and the operator's data is not mine to discard.
4. **Prefer bounding the writer over deleting the output.** Deleting today
   fixes nothing tomorrow.

## FALSIFICATION

This skill is wrong if:

- rotation inside the writer loses lines under real concurrent load, which
  would make the existing `trade/` policy unsafe to copy
- the 52 MB / 5-rotation shape proves wrong for a stream with a different
  write rate, meaning the parameters need deriving per writer rather than
  copying
- a retention policy on `sim/runs/` deletes a run a later audit needed, which
  would put run artefacts in the evidence row rather than the artefact row
- bounding `signals/session.jsonl` loses emitter records that the System
  Status tab or the Watchdog later needs, which would mean the network needs
  a durable store rather than a log
- disk pressure turns out to matter more than reachability, which would
  reverse the ordering of the whole skill

Related: `branch-discipline`, `two-sided-control`, `harness-law`.
