---
name: job-watch
description: Detect a background job that has hung, stalled or begun spiralling, and tell the difference between slow and stuck. Use whenever background workflows are running, before reporting progress, and before deciding to stop one.
---

# Job Watch

## Why this exists

Background workflows run for hours and notify only on completion. A job that
hangs, or that loops without advancing, produces **no signal at all** — the
absence looks identical to patient work.

Operator, 2026-08-15: **"Make sure we are keeping a watch for any further hangs
or hallucinatory spirals."**

## THE MEASURED BASELINE. Thresholds come from data, not from taste.

Seventeen jobs completed on 2026-08-15:

| | |
|---|---|
| shortest end to end | 56 min (blocked before promoting) |
| longest end to end | 188 min (3 phases) |
| a 3-phase job, per agent | ~63 min mean |
| slowest agent inside a completed job | ~90 min |
| every live job's write cadence | continuous — seconds to a few minutes |

**The dominant cost is real pytest.** The whole suite runs 560-844 seconds and
a promoting unit runs it many times, so hours of wall clock is normal and is
not evidence of a fault.

## THREE SIGNALS, AND ONLY ONE OF THEM IS ELAPSED TIME

| signal | threshold | what it means |
|---|---|---|
| **STALE** | no write in **15 min** | Genuinely suspect. Live jobs write constantly. |
| **SLOW AGENT** | one agent past **120 min** with no phase closed | ~2x the measured per-agent mean. |
| **RUNAWAY** | job past **240 min** with phases outstanding | Beyond any completed job. |

**ELAPSED TIME ALONE IS NOT A SIGNAL.** Read it with **phases completed** and
**last write** together. A job at 300 minutes with two phases closed and a fresh
write is slow. The same job with zero phases closed is outside the distribution.

## THE HARD ONE: A SPIRAL LOOKS LIKE HEALTH

An agent re-running the same command writes constantly and never advances.
Freshness alone cannot separate work from thrash.

**THE DISCRIMINATOR IS PHASE ADVANCE OVER TIME, not activity.** Sample twice,
twenty minutes apart. Writing but not advancing, twice running, is the shape.
When suspicious, read the agent's transcript and look for the same command with
the same arguments repeating.

## BEFORE CALLING ANYTHING A FAULT, EXPLAIN THE SLOWNESS

Today's outlier ran 319 minutes with zero phases closed — and the cause was
arithmetic, not a fault. That unit carried **seven two-sided controls**, and the
standing no-subset rule means each revert runs the whole suite: seven reverts at
~12 minutes is ~84 minutes of pytest before its baseline and post-change runs
count at all. It was also rebasing seven prior repairs and fixing three more
defects.

**A slow job with a measurable reason is not a hang.** Name the reason or say
you could not find one; never characterise it as "seems stuck".

## WHAT NOT TO DO

- **DO NOT STOP A JOB MID-PROMOTE.** A half-applied change is worse than none,
  and a change spanning `src/` and a doc lands in two steps. Check whether the
  promote phase has started before stopping anything.
- **DO NOT KILL A SLOW JOB TO SAVE TIME.** The work is resumable, but a stopped
  job discards the phase in flight. Resume replays completed agents from cache;
  the running one restarts from zero.
- **DO NOT ASSUME A JOB SURVIVES A RESTART.** A Claude Code restart kills every
  in-flight background job silently. Recovery is
  `Workflow({scriptPath, resumeFromRunId})` — completed agents replay from cache.
  The tell is every MCP server disconnecting and reconnecting in the same window.

## HOW TO RUN IT

The watcher reads each run's `journal.jsonl` for completed agents and the
transcript directory's file times for liveness. One `result` line per completed
agent. Keep the job table current as jobs are dispatched and land.

```bash
python <scratchpad>/WATCH_jobs.py
```

**Run it before reporting progress**, and whenever the operator asks how long
something will take. Phase completion is a MEASUREMENT; time-to-finish is an
extrapolation and must be labelled as one.

## A SEPARATE SIGNAL: THE GATE THAT GOES RED FOR SOMEONE ELSE

With several jobs promoting into one tree, a gate can fail on a file a
**different** job rewrote mid-run. Measured twice on 2026-08-15.

**Prove attribution before reporting a red**: read the failing test's inputs,
check the mtime and hash of every file it touches against the other jobs, then
re-run. Report both runs.

Related: an exit code of 1 with an **empty** output file is a concurrency
artefact, not a verdict — the gate always prints `[FAIL]` and its failure list
first. And `.release_ready.json` is shared and last-writer-wins, so **your own
banner is the evidence**, never the sidecar another job may have overwritten.

## EXIT CODES THAT ARE NOT VERDICTS

Three shapes measured on 2026-08-15, each of which reads as a failure and is not one.

| what you see | what it actually is |
|---|---|
| **exit 143** | SIGTERM. The Bash tool kills a foreground command at its ceiling — the whole suite runs 560-844 s and the gate runs longer. **Re-run detached, with the exit code captured to a FILE.** |
| **exit 1 with an EMPTY output file** | A concurrency artefact. The gate always prints `[FAIL]` and its failure list before returning 1, so a silent non-zero cannot be a judgement. Re-run. |
| **exit 139** | SIGSEGV. Prints no failure summary at all, so a reader looking only at the tail sees nothing and may call it a pass. |

**NEVER READ AN EXIT CODE THROUGH A PIPE.** `cmd | tail` returns TAIL's status, not the
command's. Redirect to a file and read `$?` on its own line.

**AND A COUNT FROM ONE INVOCATION IS NOT A COUNT FROM ANOTHER.** The gate's own pytest
collects a different set from a bare `pytest tests -q` — 6605 against 6234 on the same tree.
Report both rather than reconciling them into whichever is more flattering.

## FALSIFICATION

This skill is wrong if:

- A job flagged STALE turns out to be doing legitimate long work that writes
  nothing — which would mean the write-cadence assumption is wrong for some job
  shape, and liveness needs a different probe.
- A genuine spiral advances phases while looping, defeating the discriminator.
- The thresholds fire so often that they get ignored. They are calibrated to one
  day's distribution; if the workload changes, re-measure rather than widening
  them by feel.
- Stopping and resuming a slow job proves cheaper than letting it finish, which
  would invert the do-not-kill rule.

Related: `harness-law`, `two-sided-control`, `development-island`.
