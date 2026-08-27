# Emitter Network Inventory

Reference. Item 10, first unit. This document counts the emitter network.
It does not add a pin, wire a tab, or design a network.

Date: 2026-08-13. Tree: `acervator_session25_CLOSE_hop5_v3_15_27`,
branch `cascade/c43-release-gate-integrity`.

The authoritative number is **40 pin call sites, all wired, in 9 files of
163 scanned**.

---

## 1. The instrument and its controls

### 1.1 What counts as a pin

The instrument is `tools/harness/watchdog_archetype.py`
(class `WatchdogArchetype`, version 2.0, rule W001). Its own docstring
states the predicate:

> A call counts as a pin when it is a plain call, not a call on an object,
> and its name is `emit`, ends in `_emit`, or is a name this file bound to
> `signal_contract.emit` by import or by plain assignment. Bindings are
> read from the WHOLE file, because this codebase aliases `emit` INSIDE
> the function that uses it.

In code, the predicate is `_PinScan.visit_Call`
(`watchdog_archetype.py:238-263`). It admits two forms:

| form | example | verdict |
|---|---|---|
| bare name bound to `signal_contract.emit` | `_s2("sim.trades_fired", ...)` | pin, wired |
| bare name matching `emit` / `*_emit` / a repointed `emit` import, not bound to the wire | `_zz("x", ...)` | pin, NOT wired (W001) |
| `signal_contract.emit(...)` or an aliased module attribute | `sc.emit("x", ...)` | pin, wired |
| any other `obj.emit(...)` | `self._bus.emit(...)`, `btn.clicked.emit()` | NOT a pin |

The last row is deliberate. Three mechanisms share the attribute `.emit`
in this tree, and only one is a pin. Section 6 shows what happens when a
counter ignores that.

### 1.2 The reporting surface

The archetype reports through two surfaces, and both were read directly:

- the `falsification` string:
  `Pins seen: N wired, M not wired, over F file(s) scanned`
- the process exit code, because `python -m tools.harness.watchdog_archetype`
  runs `sys.exit(main())`

No intermediate was read.

### 1.3 Baseline

    python -m tools.harness.watchdog_archetype src

    passed  : true
    exit    : 0
    findings: 0
    errors  : 0
    Pins seen: 40 wired, 0 not wired, over 163 file(s) scanned

163 is the gated count. `src/` holds 164 `.py` files; `signal_contract.py`
is exempt because it IS the wire.

### 1.4 The four controls

Each control ran against a full scratchpad copy of `src/`. Each was read
at the CLI surface. All trees parsed cleanly, so no count moved because a
file stopped parsing.

| # | control | expected | measured | exit | verdict |
|---|---|---|---|---|---|
| A | plant one pin in `gui/main_window.py`, which had none | 41 wired | 41 wired, 0 not wired | 0 | PASS |
| B | remove one pin from `trading/smart_wire.py`, which had two | 39 wired | 39 wired, 0 not wired | 0 | PASS |
| C | short nickname `from src.core.signal_contract import emit as _zz` | 41 wired | 41 wired, 0 not wired | 0 | PASS |
| D | short nickname from an impostor module | 40 wired, 1 not wired | 40 wired, 1 not wired | 1 | PASS |

Control D produced one W001 finding naming `_zz`, and no finding naming a
Qt signal or an EventBus call.

**Control B failed on its first run, and the failure was in the control,
not the instrument.** The removal wrote a `pass` at the wrong indentation.
`smart_wire.py` stopped parsing, both its pins disappeared, and the count
fell by two. A two-pin drop reads exactly like a one-pin removal plus an
unrelated loss. The control now asserts that the mutated file still parses
and still holds exactly one pin before it reads the count.

### 1.5 The short-nickname case

The class still exists. It is the dominant form in this codebase.

| alias shape | distinct aliases | call sites |
|---|---|---|
| matches `emit` or `*_emit` | 13 | 23 |
| short nickname, no name-shape signal | 9 | **17** |
| total | 22 | 40 |

The nine short nicknames are `_cr_ok`, `_dz`, `_fs`, `_pe`, `_s2`, `_tk`,
`_tk2`, `_w`, `_wb`. They carry 17 of the 40 call sites — the same 17 an
earlier session recorded as invisible to the archetype's first version.

The current version sees all of them. `collect_bindings` walks the whole
tree, so a function-local `from src.core.signal_contract import emit as _s2`
binds `_s2` to the wire. Control C confirms the mechanism at the surface.
Control D confirms the instrument still discriminates a nickname bound to
something else, so it is not simply accepting every short name.

---

## 2. Per-file inventory

9 files carry pins. 154 of the 163 gated files carry none.

| file | pins | wired | subsystem prefixes |
|---|---|---|---|
| `src/gui/simulator_tab/fleet/fleet_replay_controller.py` | 11 | 11 | `fleet`, `sim`, `ta` |
| `src/gui/simulator_tab/fleet/fleet_replay_panel.py` | 9 | 9 | `sim`, `ytd` |
| `src/trading/scrumming_bot.py` | 8 | 8 | `bot`, `extractor`, `tick` |
| `src/gui/simulator_tab/fleet/bot_state_loader.py` | 4 | 4 | `fleet` |
| `src/gui/simulator_tab/simulator_tab.py` | 2 | 2 | `sim` |
| `src/trading/smart_wire.py` | 2 | 2 | `topology` |
| `src/trading/ta_engine.py` | 2 | 2 | `ta` |
| `src/exchange/ccxt_connector.py` | 1 | 1 | `history` |
| `src/gui/indicator_panel.py` | 1 | 1 | `gui` |
| **total** | **40** | **40** | |

### By subsystem

| subsystem | pins |
|---|---|
| `sim` | 14 |
| `fleet` | 7 |
| `bot` | 3 |
| `tick` | 3 |
| `ta` | 3 |
| `ytd` | 3 |
| `extractor` | 2 |
| `topology` | 2 |
| `gui` | 1 |
| `history` | 1 |
| built at run time | 1 |

The one run-time name is `ta_engine.py:2656`, `f"ta.raw.{_sig.indicator}"`.
No reader of the source can decide its bucket.

---

## 3. Pins per tab

The tabs come from `addTab` and `insertTab` in `src/gui/main_window.py`.
`insertTab` matters: the Simulator is added with
`self._main_tabs.insertTab(1, self._simulator, "Simulator")` at line 4020,
so an `addTab`-only enumeration misses the one tab that carries the network.

The order below is `CANONICAL_TAB_ORDER` (`main_window.py:4583-4586`).

Attribution rule: a tab owns the module or package that builds its widget
tree. Three tabs are built inline inside `main_window.py`, so they have no
module of their own. Import reachability is reported separately, because
the closure of `main_window.py` is the whole GUI and would credit one pin
to every tab.

| # | tab | built from | own pins | reachable pins | subsystems |
|---|---|---|---|---|---|
| 1 | Trading | `gui/main_window.py` (inline; `ExchangeTab` at line 2404) | **0** | 0 | none |
| 2 | Market Inspector | `gui/market_inspector.py` | **0** | 0 | none |
| 3 | Bot Swarm | `gui/bot_visualizer.py` | **0** | 0 | none |
| 4 | Asset Charts | `gui/main_window.py` (inline; `TradeChartsTab` at line 1149) | **0** | 0 | none |
| 5 | History | `gui/history_tab.py` | **0** | 0 | none |
| 6 | Simulator | `gui/simulator_tab/` (18 files) | **26** | 27 | `sim`, `fleet`, `ta`, `ytd` |
| 7 | Console | `gui/main_window.py` (inline, line 4573) | **0** | 0 | none |

The Simulator's reachable count adds one: `gui/indicator_panel.py`, whose
single `gui.voting_panel.fit` pin is shared with the Trading surface.

### The remaining 13 pins

13 pins sit in the shared engine, below every tab. They fire whichever tab
is open.

| file | pins | layer |
|---|---|---|
| `src/trading/scrumming_bot.py` | 8 | bot engine |
| `src/trading/smart_wire.py` | 2 | topology |
| `src/trading/ta_engine.py` | 2 | TA |
| `src/exchange/ccxt_connector.py` | 1 | exchange |

26 (Simulator) + 1 (shared widget) + 13 (engine) = 40.

### Nested tab widgets

These carry no pins either.

| host | nested tabs | pins |
|---|---|---|
| `gui/bot_visualizer.py` | Bot Swarm, Simulator Swarm, Paper Swarm | 0 |
| `gui/settings_dialog.py` | 11 tabs (User, Exchanges, Trading, Profit Folding, TA Indicators, Phantom Bots, Theme, Logging, Sound, SMS, AI Monitor) | 0 |
| `gui/bot_live_settings.py` | 8 tabs (Status, Settings, Fold Tranches, Stack Tranches, Bot Swarm, Market Inspector, Phantom Bots, Positions Held) | 0 |
| `gui/stock_main_window.py` | Trading, Webhooks, Paper Trader, Console | 0 |

This matches the operator's statement of 2026-08-11. The Simulator is the
reference implementation, not a defect.

---

## 4. What the pins report

39 distinct names over 40 call sites. One name repeats:
`bot.capital_reservation` fires from `scrumming_bot.py:1319` (the refusal
path) and `:1341` (the granted path).

| what it observes | pins | examples |
|---|---|---|
| value or count | 11 | `sim.trades_fired`, `ta.coverage_per_bot`, `ytd.per_symbol_counts` |
| state change | 10 | `fleet.bots_loaded`, `sim.fleet_spawned`, `topology.bot_attached` |
| decision or invariant | 8 | `fleet.state_parity`, `extractor.arrival_atomic`, `bot.adoption_capped` |
| render outcome | 5 | `sim.bot_table.rendered`, `sim.price_chart.fed`, `gui.voting_panel.fit` |
| throttle or tick state | 5 | `tick.throttled`, `tick.worked`, `sim.bot_ticks_did_work` |
| other | 1 | `fleet.bot_ids_mirror_live` |

### Does any pin carry a duration?

**No. Zero of the 40 pins carry a duration.**

No pin payload holds a key naming elapsed time: no `duration`, `elapsed`,
`_ms`, `latency`, `took`, `runtime`, `perf_counter`, `monotonic`,
`started_at`, or `finished_at`.

**One pin carries a timestamp pair, and it does not measure work.**
`sim.window_played` (`fleet_replay_controller.py:1796`) reports
`{"first_ts": _first, "last_ts": _last, "symbols": ...}`. Those are the
first and last stamps of the market tape that was replayed. They measure
the span of the simulated DATA, not the wall-clock time the replay took.
Subtracting them gives the length of the tape, not the cost of playing it.

Every record does carry a `ts` wall-clock field and a monotonic `seq`
(`signal_contract.py:189-240`), stamped by the sink. A duration between two
records could therefore be derived after the fact. No pin declares one.

The five pins grouped as "throttle or tick state" name timing but report
counts and booleans, not time. `tick.throttled` reports `actual=True` with
a counter and a skip interval. `sim.bot_ticks_did_work` reports how many
ticks did work, not how long they took.

This is the gap between the network as built and the stated purpose. The
network can currently answer "did it run, and was the value right". It
cannot answer "how long did it take".

#### Control on this answer

A zero is a claim about the detector. The detector was checked both ways:

| control | result |
|---|---|
| fires on a planted `{"duration_ms": t1 - t0}` | PASS |
| silent on a clean pin | PASS |
| fires on a planted `{"first_ts": a, "last_ts": b}` | PASS |
| silent on `{"candle_ts": _last_ts}` | PASS |
| silent on a lone `{"since_ts": ...}` | PASS |

The fourth control exists because the first version of the detector failed
it. A substring scan over the call source matched the variable name
`_last_ts` and reported `ta.raw.*` as pair-carrying. The detector now reads
the payload KEYS from the AST, because what a pin reports is its keys, not
the local variable names behind them.

A second defect in the same script was caught the same way. The span lookup
was keyed by line number alone and overwritten, so for
`_emit("fleet.bots_loaded", actual=len(out), ...)` the stored span became
`len(_eligible)`. Four pin names read as unnamed and four payloads were
never examined. The lookup is now keyed by line AND callee, and it raises
if the span for a pin the Watchdog found is missing.

---

## 5. The collector

### Where it is installed

`install_process_sink()` is called from `main.py:610-611`, inside `main()`,
before the Qt application is created. It is NOT limited to a Fleet Replay.

    from src.core.signal_contract import install_process_sink
    _sig_sink = install_process_sink()

The comment at `main.py:599-608` records why. Before v3.24.88 the only
caller of `set_sink` was the Fleet Replay controller, so outside the
Simulator every `emit()` returned immediately.

A Fleet Replay still installs its own sink for the run
(`fleet_replay_controller.py:524-533`). It saves the previous sink in
`self._prior_sink` and RESTORES it at teardown (`:1806-1813`) rather than
clearing to `None`, so live collection resumes when the replay ends.

Installation is best-effort. A sink that cannot open its file returns
`None` and the application starts normally.

### What it does with a record

`emit()` (`signal_contract.py:532-574`) looks up the installed sink. With
no sink it is a lookup and a return. With one:

1. derives `ok` by equality when `expected` is given and no verdict is passed
2. applies the rate limit when `every > 0`, folding suppressed observations
   into the next record's `count`; a FAILING check is never suppressed
3. captures `site` (`file:line`) and `module` from the calling frame
4. freezes `actual`, `expected` and `context` into immutable forms
5. appends a frozen `Signal` to an in-memory buffer and returns

No I/O happens on the emit path. Disk writes are amortised over
`flush_every` (500 for the process sink). `flush()` appends JSONL and never
rewrites. `MAX_ROWS` is 2,000,000 per sink, and reaching it is recorded
rather than silent.

The Console reads the sink by polling `since(seq)` on a timer
(`main_window.py:4688-4695`), not by being pushed to.

### The known limit

The message file has a fixed name. It is only ever appended to. Nothing
trims it, rotates it, or caps it by size.

    path : ~/.acervator_logs/signals/session.jsonl
    size : 1,402,465,219 bytes (1.306 GiB)
    first record: 2026-08-09T18:24:26Z

`install_process_sink` builds the name as `base / "session.jsonl"`
(`signal_contract.py:613`). Every process writes to that one file. The
`MAX_ROWS` cap is per SINK, held in memory as `_seq`, so it resets to zero
on every launch and never limits the file. The file has reached 1.3 GiB in
four days.

---

## 6. Reconciling the three counts

| source | number | verdict |
|---|---|---|
| Watchdog archetype, 2026-08-13 | **40 call sites, 39 distinct names** | correct |
| earlier session | 38 pins across 40 call sites | call sites correct, name count off by one |
| regex A, 2026-08-11 | 0 | wrong; matched a form that does not occur |
| regex B, 2026-08-11 | 309 | wrong; counted a different mechanism |

### 38 against 40

The call-site number was right. 40 then, 40 now.

The name count is 39 distinct names today, not 38. One name is emitted from
two sites (`bot.capital_reservation`), which accounts for 40 sites against
39 names. The recorded 38 is one short. The likely cause is the one name
built at run time, `f"ta.raw.{_sig.indicator}"`, which is not a literal and
is easy to drop from a distinct-name tally. This document reports both
numbers so the distinction cannot collapse again.

### 0

Measured over the same 163 files:

| pattern | matches |
|---|---|
| `signal_contract\.emit\s*\(` | **0** |

That is the result. The qualified call `signal_contract.emit(...)` appears
NOWHERE in `src/`. Every one of the 40 sites imports `emit` under an alias
inside the function that uses it, then calls the bare alias. A counter that
looks for the qualified form finds nothing and reports an empty network.

A bare `emit\s*\(` fares little better: 14 matches, against 40 real sites.
It misses every short nickname.

### 309

309 belongs to the `.emit(` family. Measured today over the same files:

| pattern | matches |
|---|---|
| `\.emit\s*\(`, text | 374 |
| `\.emit\s*\(`, excluding comment lines | 372 |
| attribute `.emit` calls, by AST | 367 |
| `(?:bus\|_bus)\.emit\s*\(` | 293 |
| `self\._bus\.emit\s*\(` | 275 |

The receivers are not pins:

| receiver | calls |
|---|---|
| `_bus` (EventBus) | 275 |
| `status_changed` (Qt signal) | 20 |
| `_sig_console` | 9 |
| `_vis_bus` | 7 |
| `bus` | 6 |
| others | 50 |

No variant reproduces 309 exactly, and this is stated rather than guessed.
The nearest measured values bracket it at 293 and 367, and the tree has
changed since 2026-08-11. What is certain is the mechanism: 309 is about
eight times the pin count, and it is dominated by EventBus traffic and Qt
signal emissions. The EventBus carries payloads between parts of the
program. A Qt signal drives the widget tree. Neither reaches the handler.
Counting them as pins reports button labels as pin names.

The archetype excludes them by design, and states the cost: a pin that
emits into a `SignalSink` it built for itself, rather than the installed
process sink, is not seen. No such case was found in this tree.

### Why both regexes were wrong

Both asked the wrong question. A pin is not a spelling. A pin is a call
that reaches the installed handler. That is a binding question, and it is
answerable only by resolving names, which is why the instrument parses the
tree instead of matching text. Regex A demanded a spelling nobody uses.
Regex B accepted a spelling three mechanisms share.

---

## 7. Tabs ranked by how little they are instrumented

| rank | tab | own pins | files with pins |
|---|---|---|---|
| 1 (tied) | Trading | 0 | none |
| 1 (tied) | Market Inspector | 0 | none |
| 1 (tied) | Bot Swarm | 0 | none |
| 1 (tied) | Asset Charts | 0 | none |
| 1 (tied) | History | 0 | none |
| 1 (tied) | Console | 0 | none |
| 7 | Simulator | 26 | 4 of 18 |

Six of the seven tabs carry zero pins. All nested tab groups carry zero:
11 Settings tabs, 8 Bot Live Settings tabs, 3 Bot Swarm sub-tabs, and the
4 tabs of the equities window.

Of the 56 Python files under `src/gui/`, 6 carry a pin. Of the 163 gated
files under `src/`, 9 carry a pin and 154 carry none.

---

## Falsification

This inventory is wrong if any of the following holds.

- `python -m tools.harness.watchdog_archetype src` reports a wired count
  other than 40 on this tree, with no source change between the runs.
- Any of the four controls in section 1.4 stops discriminating.
- A pin exists that emits into a self-built `SignalSink` rather than the
  installed process sink. The archetype states this blind spot; no instance
  was found, and the search was the archetype's own scan, so an instance
  would be invisible to it as well.
- A tab is reached by a route other than `addTab` or `insertTab` in
  `src/gui/main_window.py`.
- A pin payload carries elapsed time under a key the section 4 detector
  does not list.

## Artifacts

Analysis scripts and raw output are under the session scratchpad:
`enumerate_pins.py`, `controls.py`, `tabmap.py`, `reconcile.py`, with
`inventory.json`, `tabmap.json`, `reconcile.json` and the per-control CLI
reports `cli_BASE.json`, `cli_A.json`, `cli_B.json`, `cli_C.json`,
`cli_D.json`.
