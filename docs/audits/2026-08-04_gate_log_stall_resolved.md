# gate.log "stall" — resolved, not open

Reference. 2026-08-04, measured against the live logs at
`~/.acervator_logs/trade/`.

**The gate.log writer is healthy. This was carried as an open live-side
P0 and should not have been.**

## What the logs actually say

| file | size | last entry |
|---|---:|---|
| `gate.log` | 719,501 B | `2026-08-05T02:00:50.176649Z` |
| `trade.log` | 192,116 B | `2026-08-05T02:00:50.175700Z` |

**1 ms apart — the same event.** Both written at the same wall time. The
writer is not stalled and has not been for weeks.

## The thing that looked like a stall

Emission rate collapsed by ~3,400x:

| source | rate |
|---|---:|
| rotated `gate.log.1`-`.5` | 82,283 entries/day |
| active `gate.log` | ~24 entries/day |

That is real, and it is **by design**. Two separate changes explain the
whole picture, and both are already in the tree.

### Cause 1 — Windows rotation hazard (fixed v3.23.5)

`Path.rename()` raises `WinError 183` on Windows when the destination
exists; POSIX overwrites silently, Windows refuses. The rotate-then-
append flow could not get past the `.4 -> .5` shift, so the writer
stalled outright. 350,470 warnings between 2026-06-10T22:29 and
2026-06-13T13:12.

Fixed by switching to `Path.replace()`, the documented cross-platform
overwrite primitive. See `src/core/logging_engine.py:150-159`.

### Cause 2 — emission moved to fire time (v3.23.11)

`_emit_gate_decision_at_fire` (`scrumming_bot.py:4469`) replaced the
in-tick emit. The old placement was position-buggy: only the organic
SCRUM path could reach it, so CARTRIDGE_FOLD, CARTRIDGE_SCRUM, FOLD,
HEDGE, DIST, ENTRY, AUTO_DETONATION and manual fires all bypassed it —
a measured **11.1% coverage at v3.23.10**.

It is now called after every `trade.filled` emit (10 sites). That is why
the gate:trade ratio is exactly 1.0 from 2026-07-25 onward, and why the
rate is no longer per-tick.

## Every gap is accounted for

Classifying all 612 live trades: **100% of the 211 `LOG_GAP` trades fall
inside the two windows above.**

| window | log_gap | explanation |
|---|---:|---|
| 2026-06-09 → 06-13 | 77 | rotation stall (cause 1) |
| 2026-06-14 → 06-25 | 134 | post-rotation-fix, pre-fire-emit (cause 2) |
| 2026-06-26 → 07-24 | 0 | **zero trades too** — app not running |
| **2026-07-25 → 08-05** | **0** | **100% coverage, every day** |

Eleven consecutive days of complete gate coverage, after both fixes
landed. There is nothing left to fix.

## Why this was worth checking rather than accepting

The stale memory entry asserted a specific, plausible mechanism —
"handler-specific silent failure in `_on_gate_decision_bus`" — and
recommended grepping `system.log` for it. That diagnosis was reasonable
when written on 2026-06-13, and it was superseded twice within days by
fixes that the memory never learned about.

A memory entry is a point-in-time observation. This one was 52 days old
and described a system state that two shipped cascades had already
changed.

## Falsification

This resolution is wrong if any trade dated after 2026-07-25 classifies
as `LOG_GAP`. That is a one-line check against
`gate_coverage.classify_trades` and should be re-run if gate coverage
ever looks sparse again.

## Correction issued

`~/.claude/.../memory/project_live_gate_log_stalled.md` and the
`MEMORY.md` index line were rewritten to record the resolution, so the
next session does not spend time re-diagnosing a fixed defect.
