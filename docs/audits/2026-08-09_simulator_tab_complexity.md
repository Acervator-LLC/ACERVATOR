# Simulator Tab — time and space complexity

Date: 2026-08-09
Scope: `src/gui/simulator_tab/` — 18 files
Method: AST candidate scan, then measurement on the real Load → Start path

This is the pass the archetype triage listed as "Not started".

## Headline

The per-candle path is flat. Measured over 1,500 candles with 37 bots:
**0.0745 s/candle**, which is 13.4 candles/s. Extrapolated to a full
35,282-candle run: **43.8 minutes**.

The emitter sink holds **14 rows** for the whole run and its cap is
2,000,000. Nothing on the replay path grows without a bound.

## The instrument had to be calibrated twice

Both corrections are recorded because each first result was wrong in a way
that read as a finding.

**First error — I measured my own harness.** The probe pumped asyncio in a
loop with `time.sleep(0.02)`, capping it near 50 pumps/s. It reported
**1.0692 s/candle**, extrapolating to 10.5 hours. That number describes the
sleep, not the replay. Removing the sleep gave 0.0810 s/candle.

The check that caught it: `fleet_replay_panel.py` already documents a
measured "~12.5 candles/s" and "~47 minutes". The corrected harness reads
12.35 c/s and 47.6 min. Two independent figures agreeing is what makes the
number usable; the first result disagreed with the code by 13x and I nearly
reported it.

**Second error — the probe wrote to the live tree.** The first run changed
`~/.acervator/feature_telemetry.json`. `feature_telemetry.telemetry_path()`
resolves at call time and honours `ACERVATOR_TELEMETRY_ROOT`; the probe
never set it. Fixed by setting it before any `src` import. That was my
defect, not the product's — the override exists and works.

**A census cannot attribute writes while the app runs.** `bot_state.json`
and `bot_state.backup.json` appear as "changed" on any run longer than 60
seconds. Measured with nothing of mine running: 4 distinct states in 160
seconds, at deltas of 60.0 s, 60.1 s and 59.9 s. That is
`main.py:1126-1128`, `save_timer.start(60000)`. Runs under 60 s report 0
changed; that is timing, not proof of isolation.

## Time — measured

Per-block cost over 1,500 candles, 150 candles per block:

| candles | s/candle |
|---|---|
| 1–150 | 0.1129 |
| 151–300 | 0.0670 |
| 301–450 | 0.0688 |
| 451–600 | 0.0642 |
| 601–750 | 0.0678 |
| 751–900 | 0.0699 |
| 901–1050 | 0.0733 |
| 1051–1200 | 0.0722 |
| 1201–1350 | 0.0759 |
| 1351–1500 | 0.0732 |

Block 1 is warmup. First-to-last ratio is 0.65x, so the cost does not grow
with run length at this scale.

**One thing 1,500 candles cannot settle.** Ignoring warmup, blocks 4 → 9
drift from 0.0642 to 0.0759, about +14%. That is either slow accumulation
or noise, and this run cannot separate them. Do not claim the path is O(1)
without a longer run; claim it is flat within the noise of 1,500 candles.

Other measured quantities from the same run:

- bot ticks entered: 50,961 (1,500 candles x ~34 bots)
- bot ticks that did work: 10,546 (20.7%) — the rest throttle
- trades fired: 77
- exceptions: 0

## Space — measured

| quantity | value |
|---|---|
| emitter rows, 1,500 candles | 14 |
| emitter rows, 600 candles | 14 |
| emitter rows, 250 candles | 15 |
| `MAX_ROWS` | 2,000,000 |
| dropped | 0 |
| capped | False |

The sink is bounded at `signal_contract.py:80` with a `dropped` counter and
a `capped` flag, so an overrun would announce itself rather than truncate
silently. Nothing approaches it.

**Row count does not vary with candle count.** 250, 600 and 1,500 candles
all yield 14–15 rows. Those are the run-end S2 emitters in the `finally`
block. The per-candle `ta.raw.*` records that
`fleet_replay_controller.py:1723` describes as "~1200 green rows per
indicator" are not landing in this sink. Named here, not chased: it is an
emitter-coverage question, not a complexity one.

## Candidate scan

77 candidates across 18 files. Counts are candidates, not defects.

| class | count | what it looks for |
|---|---|---|
| S1 | 34 | append inside a loop with no visible bound |
| T3 | 18 | `sorted`/`min`/`max` over a collection inside a loop |
| T1 | 13 | nested loop over a non-constant iterable |
| T2 | 8 | linear scan inside a loop |
| T4 | 4 | comprehension inside a loop |

Nothing nests deeper than 2. The candidates that would matter are the ones
on the per-candle path, and the two that looked worst are not on it:

- `fleet_replay_controller.py:1714` — `sorted(self._ta_eligible.items())`
  is inside the `finally` block, so it runs once at shutdown, not per
  candle.
- `fleet_replay_controller.py:1739` — the sink pass is the same block, and
  its own comment says it "costs one pass at shutdown and keeps the hot
  path free of tallying state". Measurement agrees.

The genuine per-candle loop is `fleet_replay_controller.py:1487`,
`for _bi, bot in enumerate(self._bots)` — 37 iterations per candle. That is
the work itself.

## What this pass did not do

- Memory footprint in bytes. Row count is bounded and small, so the sink is
  not a risk; per-bot state was not profiled.
- A full 35,282-candle run. Every total here is extrapolated from 1,500,
  and the extrapolation assumes the flat rate holds. See the drift note.
- `sim_visuals.py` paint cost. `paintEvent` carries depth-2 loops
  (lines 1021, 1029, 1053) but repaint is throttled to roughly 200 updates
  per run by `_visual_refresh_every`, so it is not on the per-candle path.
