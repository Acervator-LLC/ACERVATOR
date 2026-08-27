# Emitter duration classification — all 40, for item 10.3 phase 2

Measured 2026-08-19 in the GitHub repo at `current`, against `v3.25.8`.
Read-only: no branch was cut for the measurement, nothing was edited, no
emitter changed.

The work order (`docs/ITEM_10_EMITTER_NETWORK.md`, UNIT 1) requires this before
any duration is added: *"Classify all 40 first: which wrap an interval that can
be measured honestly, and which are instantaneous observations where a duration
would be fabricated. A fabricated duration is worse than a missing one, because
item 17 computes health from it."*

This is that classification.

---

## FIRST: 10.3 IS HALF SHIPPED, AND THE SHIPPED HALF IS NOT WHAT PHASE 2 ADDS

**`Signal.dt` already exists, works, and is pinned.** It records seconds since
the previous emission of the same `(name, site)` identity, from
`time.monotonic()`. Driven 2026-08-19:

    nth=1  dt=None        first emission, correctly None and not 0.0
    nth=2  dt=0.0005375   0.5 ms injected
    nth=3  dt=0.0020274   2.0 ms injected

That is the control UNIT 1 demands — two known intervals producing two
DIFFERENT tracking values — and it passes. `tests/test_signal_timing.py` is
1,028 lines and roughly 34 tests covering identity separation, first-emission
versus never-measured, staleness, hang detection, round-trip persistence,
console rendering and performance ceilings, with its own two-sided controls.

**`dt` IS CADENCE. IT IS NOT DURATION.** The register already draws the line:

> `timer`. No pin carries a duration. … Adding duration is a later unit, which
> will claim this term.

| | measures | state |
|---|---|---|
| `dt` | the gap BETWEEN emissions | shipped, pinned, controlled |
| duration | how long the observed operation TOOK | not started — this unit |

For item 17's health definition, cadence already answers **on time** and
**hangs** (staleness). What is missing is **slow downs**. Phase 2 is therefore real,
and narrower than "0 of 40 carry a duration" suggests.

**Anyone reading "0 of 40 carry a duration" and concluding the record has no
time field will waste an hour.** It has one. It measures something else.

---

## THE INSTRUMENT, AND ITS CONTROL

The 40 were enumerated with the Watchdog's own definition, the `(list, error)`
pair unpacked, and a zero control:

    TOTAL: 40      ZERO CONTROL (src/core/fmt.py): 0

Enclosing functions were resolved by walking the AST for the innermost
`FunctionDef` spanning each emitter's line, not by regex.

**A CLOCK HAZARD WAS PRE-MORTEMED AND REFUTED.** The concern was that
`time.monotonic()` on Windows is quantised at the ~15.6 ms scheduler tick, which
would make UNIT 1's control unfalsifiable or, worse, passable with quantised
junk. Measured on this machine: resolution **1e-07**, smallest observable delta
**100 ns**, and 0.5 ms versus 2.0 ms cleanly separated on both `monotonic` and
`perf_counter`. Python 3.14 backs `monotonic()` with `QueryPerformanceCounter`.
The work order's instruction stands unmodified. A pre-mortem that finds nothing
is the positive control's twin.

---

## FINDING 1 — DURATION CANNOT MEAN "TIME THE ENCLOSING FUNCTION"

**32 of 40 emitters share their enclosing function with at least one other.**
Only 8 sit alone.

    8 emitters in fleet_replay_controller.py:_run()
    4 emitters in scrumming_bot.py:tick()
    3 each in load_bot_configs_from_state(), _build_sim(),
             _spawn_sim_fleet(), _do_fetch()
    2 each in _drain_visual_snapshot(), _ensure_capital_reservation(),
             apply_extractor_tranche_return(), compute_all()

If each carried its enclosing function's elapsed time, those 32 would report
**identical numbers**. That is a fabricated distinction, and item 17 would
compute health from it.

**THE RULE THAT FOLLOWS: at most ONE emitter per operation owns that
operation's duration.** Every other emitter in the same function is `None`, or
gets its own explicitly instrumented sub-interval.

## FINDING 2 — `tick.08.002.event.worked` IS AN ENTRY MARKER

It fires at line 6239 of a `tick()` spanning 6154-10657 — 85 lines into 4,503.
Its own comment states the purpose: *"Emitted so silence is never ambiguous."*
It records that the tick DECIDED TO WORK, not that work finished.

A duration there would measure nothing. **And the tick has no completion emitter
at all**, so per-tick latency — exactly what items 11 and 17 want — is not
reachable from the current network. Named here, not fixed here: adding one is a
new emitter, which is 10.5+ work, not 10.3.

---

## GROUP A — DURATION WOULD BE FABRICATED. `None` IS THE DELIVERABLE. (23)

`None` is already distinguishable from a real zero in the record by design, so
no code change is needed for any of these.

| emitter | why instantaneous |
|---|---|
| `fleet.03.002.invariant.bot_ids_mirror_live` | comparison of two sorted lists |
| `fleet.03.003.invariant.sections_imported` | set comparison |
| `fleet.03.005.invariant.state_parity` | comparison |
| `sim.06.003.counter.ticks_before_tape` | reads a counter |
| `sim.06.004.counter.trades_fired` | reads a counter |
| `sim.06.005.invariant.exceptions` | reads a counter, compares to 0 |
| `sim.06.008.invariant.state_persisted` | comparison |
| `sim.06.009.invariant.spawn_drift` | comparison |
| `sim.06.013.state_transition.mode_selected` | a UI mode switch |
| `sim.06.014.event.log.line` | one line delivered |
| `bot.01.001.postcondition.capital_reservation` | guard evaluation |
| `bot.01.002.postcondition.capital_reservation` | guard evaluation |
| `bot.01.003.postcondition.adoption_capped` | arithmetic |
| `tick.08.003.event.exit_dust_band` | a branch was taken |
| `extractor.02.002.invariant.arrival_atomic` | comparison against 0.0 |
| `topology.09.001.state_transition.bot_attached` | a dict insert, span 15 |
| `ta.07.001.postcondition.coverage_per_bot` | counts |
| `ta.07.002.invariant.invariants` | violation count |
| `ta.07.004.postcondition.raw.{indicator}` | reporting loop AFTER the compute |
| `ytd.10.003.gauge.per_symbol_counts` | a mapping of counts |

Three need their reason stated explicitly, because each is a trap:

- **`tick.08.001.event.throttled`** — the tick was SKIPPED. No work occurred. A
  duration here would not merely be fabricated, it would be **actively false**,
  and it would land in the health computation as a fast tick.
- **`tick.08.002.event.worked`** — an entry marker. See FINDING 2.
- **`sim.06.006.event.window_played`** — **already carries a timestamp pair, and
  it measures the LENGTH OF THE TAPE REPLAYED, not the cost of replaying it.**
  This is the single most likely record for a reader to mistake for a duration.
  The inventory recorded this in 10.0 and it remains true.

## GROUP B — HONEST DURATION, READY TO OWN IT TODAY (6)

Each is the completion point of a bounded operation, and each is the sole owner
of that operation. No start markers, no sub-intervals, no double-count risk.

| emitter | operation | why it is clean |
|---|---|---|
| `history.05.001.postcondition.scan_complete` | `_scan_trade_history()` | sole emitter in the function, network I/O |
| `fleet.03.004.postcondition.wires_loaded` | `load_smart_wires_from_state()` | sole emitter, file load, span 34 |
| `topology.09.002.postcondition.wires_received` | `import_wires()` | sole emitter, span 222 |
| `ta.07.003.postcondition.computed` | `compute_all()` | owns the compute; `ta.07.004` fires later in a reporting loop |
| `fleet.03.001.postcondition.bots_loaded` | `load_bot_configs_from_state()` | first emitter, owns the load |
| `sim.06.007.postcondition.fleet_spawned` | `_spawn_sim_fleet()` | owns the spawn |

**`ta.07.003.computed` is the highest-value single row in this table.** It is TA
compute latency, on the path items 11 and 17 both care about.

## GROUP C — POSSIBLE, BUT THE SITE NEEDS WORK FIRST (11)

Each needs its own instrumentation decision, so each is its own later unit.

**Emit-only helpers — the operation happened elsewhere (2).** Timing these means
instrumenting the render, not the emitter.
`gui.04.001.postcondition.voting_panel.fit` (`emit_fit()`, span 20),
`sim.06.010.postcondition.bot_table.rendered` (`emit_bot_table()`, span 18).

**Phases inside large functions — need an explicit start marker (6).**
`fleet.03.006.postcondition.state_imported` and
`fleet.03.007.postcondition.positions_seeded_from_lots` (`_build_sim()`, span
377); `sim.06.001.postcondition.candles_stepped` and
`sim.06.002.postcondition.bot_ticks_did_work` (`_run()`, span 655, teardown
block); `extractor.02.001.postcondition.tranche_contained`
(`apply_extractor_tranche_return()`, span 670).

**Siblings that would double-count (3).**
`sim.06.011.price_chart.fed` and `sim.06.012.gate_status.rendered` share one
`_drain_visual_snapshot()`; `ytd.10.001.gauge.trades_fetched` and
`ytd.10.002.postcondition.fleet_symbol_coverage` share one `_do_fetch()`. One of
each pair may own the operation; the other must not repeat it.

    23 + 6 + 11 = 40

---

## WHAT THIS MAKES UNIT 1

**Group B, the six.** A vertical unit with one control: a duration that TRACKS —
absent before, present after, and two different known intervals producing two
different recorded values within a stated tolerance. Present-but-constant passes
an existence check and fails this one.

Group A needs no code. Group C is one later unit per site.

## FALSIFICATION

This classification is wrong if any of the following holds.

- The emitter count is not 40, or the zero control on `src/core/fmt.py` returns
  non-zero — then the instrument is lying and every row here is void.
- Any Group B emitter is not in fact the sole owner of its operation, or another
  emitter in the same function would also claim that interval.
- Any Group A emitter turns out to wrap a measurable interval — in which case a
  `None` there is a missing measurement, not an honest one.
- `Signal.dt` is shown to measure operation duration rather than inter-arrival
  cadence, which would make phase 2 redundant rather than narrower.
- `time.monotonic()` on the target machine is measured coarser than the
  intervals being recorded, which would make the tracking control unfalsifiable.

Re-derive the counts with the Step 0 script in the work order. Re-derive the
sharing counts by walking the AST for the innermost enclosing `FunctionDef`; a
regex over `def ` will not give the same answer on nested functions.
