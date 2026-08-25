# Item 10.4 PROVE - the Simulator emitter network, measured at run time

Date: 2026-08-22. Branch `item-10.4-prove-the-emitters-fire`, cut from
`db9e3c6b36fb`.

Queue item 10.4. The operator's acceptance test, 2026-08-16:

> "The Sim 40 Emitters (not pins!) must be verified fully built in
> accordance with my design spec."

And, 2026-08-13:

> "We must have a functional baseline at the Simulator for the Emitter
> Network before we wired it elsewhere. Otherwise we may be pollenating
> the platform with flaws we will have to chase down later."

The queue also records that 10.4 must be a REAL Simulator run, not a
source scan. This document reports one.

## The result, in one paragraph

74 register rows. One Simulator run reached 36 of them and emitted
3,799,113 records. All 36 carry the name, the signal type and the call
site the register declares, and a duration consistent with the 10.3
disposition in their row. Nothing fired that the register does not
list. 38 pins stayed silent; 37 of those have no verdict, because a
Simulator run cannot reach them or this run's market data did not take
their branch. One is a defect: `swarm.11.002.postcondition.
paper_run_registered` has no reference of any kind anywhere in the
tree, so it cannot fire in any run.

## What ran

One Simulator run, driven through the operator's own path.

| step | what the run did |
|---|---|
| build | `SimulatorTab()`, real widgets, `set_async_loop`, swarm getter and BotManager injected as `main_window.py:5330` injects them |
| show | the tab shown and resized twice, so `showEvent` and `resizeEvent` reach the mounted panels |
| Load live fleet | `FleetReplayPanel._on_load_clicked()`. 38 bot configs and 33 Smart Wires from the operator's real `bot_state.json`. 38 sim bots spawned from the real Stone Tablets |
| Fetch YTD | `_on_fetch_ytd_clicked()` |
| Start Replay | `_on_start_clicked()`. 15,211 of 15,212 candles played, 414 sim trades, 234,139 bot ticks, 0 exceptions, 2,143 seconds |
| Nuclear Mode | `nuclear_mode_panel._on_start_clicked()`. One cycle, then stop |

The fleet is the operator's own: 38 bots, all `mode=scrumming`, read
from `~/.acervator/bot_state.json`. This unit fabricated no topology.

Nuclear Mode is in the run for one reason. `swarm.11.001` has exactly
one caller, `nuclear_mode_panel.py:636`, on the Nuclear start path. A
run that stopped at Fleet Replay would have reported that pin silent
for the wrong reason.

## The instruments, and the control on each

A zero is a claim about the instrument, not about the world. Three
instruments produced the numbers below. Each carries a control, and two
of the controls caught a defect in the instrument they guard.

### 1. The record observer

`SignalSink` is the platform's own collector. The run installs three:
one before the run, one that `FleetReplayController.start()` installs
for the replay, one for the Nuclear cycle. The observer holds all
three and folds every record into a per-(sink, name, site) tally. This
unit edited no source file to make that work.

**Positive control.** This unit planted a pin inside the replay loop at
`fleet_replay_controller.py:1425`, named
`provecontrol.99.001.event.planted`, carrying `duration=0.5`. The
observer recorded it, with its site (`fleet_replay_controller.py:1429`),
its `ok`, its `actual`, its `expected` and its duration. The
outside-the-register detector reported it as one name with no row. The
plant was then removed and the file verified byte-identical:
`2213f740c4c41148a1b29855357c79630bd03eff98d1268d5a6fad86091aafc8`
before and after.

The plant also shifted every later line in that file by three. The site
check reported all eight later pins in that file at exactly +3 lines.
The site dimension discriminates at one-line resolution.

**Completeness control, and the defect it caught.**
`SignalSink.records()` is a WINDOW. It keeps the last 350,000 records
and evicts the rest. A first attempt harvested only at the end, and the
sink reported **3,441,494 records evicted**. That harvest would have
lost every early record, and every pin that fires once at run start
would have read as silent. That is an instrument defect, not a finding. The
observer now drains on the spin loop through `SignalSink.since(seq)`.
The control is the sink's own lifetime counter, `health()['emitted']`.

| sink | emitted | tallied by the observer | equal |
|---|---|---|---|
| pre-run | 217 | 217 | yes |
| replay | 3,791,494 | 3,791,494 | yes |
| nuclear | 7,402 | 7,402 | yes |

`dropped` is 0 on all three. `duration_rejected` is 0 on all three: no
call site passed a duration the sink refused.

### 2. The line-execution instrument

`coverage.py` recorded which lines the run executed. This is what turns
"did not fire" into a measurement and splits it by cause.

**Positive control, and the defect it caught.** Every file a pin FIRED
from must appear in the coverage data. On the first attempt two pins
fired - `gui.04.001` and `swarm.11.001` - out of files the coverage data
called unmeasured. The cause sits in the repo's own `pyproject.toml`:

```
[tool.coverage.run]
omit = [ ..., "src/gui/*" ]
```

Coverage applies that silently, so the whole GUI tree reads as never
executed. This unit ran the Simulator again with `config_file=False`.
The control now reads: 36 fired pins checked, 0 in files the coverage data does not
measure. PASS.

A second correction. The first classifier asked whether any line between
the `def` and the end of the function ran. A `def` executes when Python
imports its module, so every never-called function scored as entered.
The classifier now reads the function BODY, taken from the syntax tree.

### 3. The caller instrument

An AST walk over 164 files under `src/` counts, for each pin's enclosing
function, the direct calls, the attribute references, the bare name
loads and the string literals of its name.

**Positive control, and the defect it caught.** The first version
counted calls and attributes only. It reported
`HistoryTab._kick_async_fetch._check` and
`MainWindow._setup_ui._on_activity_pause_toggled` as having no reference
at all. A bare name connects both:
`poll_timer.timeout.connect(_check)` at `history_tab.py:526`. The
instrument now reads bare `Name` loads too. The instrument now finds 16 functions reached
only indirectly, through `connect()` or `getattr`, and exactly one with
no reference of any kind. A zero from it means something because its
non-zeros do.

**A limit, stated rather than hidden.** This instrument matches on the
function's leaf name, not on its resolved class. `ExchangeTab.
update_bots` and `BotStatusTable.update_bots` share a leaf, so the
reference counts for `15-002` and `15-003` include calls that reach the
other class. The counts are an upper bound. They do not enter any
verdict: the fault kinds come from coverage of the exact file and line.

## The static half, re-derived as a control

The referee reported the static result. A separate reader re-derived it
here from the register text, and the two agree.

| check | this reading |
|---|---|
| register rows | 74 |
| naming-convention violations | 0 |
| ID subsystem number disagrees with the row's subsystem | 0 |
| ID emitter number disagrees with the name | 0 |
| signal type in the name disagrees with the column | 0 |
| previous name is not `subsystem.slug` | 0 |
| source does not resolve to `file.py:line` | 0 |
| duplicate ID, duplicate name or duplicate site | 0 |
| planned-names table disagrees with the register | 0 of 74 |

Counts by signal type: `postcondition` 48, `invariant` 15, `event` 5,
`counter` 2, `gauge` 2, `state_transition` 2. By duration disposition:
`measured` 21, `forbidden` 26, `none` 16, `deferred` 11. Both match the
register's own tables and the referee's report.

All 74 call sites were then resolved from the syntax tree at the exact
line each row declares. All 74 pass a name literal equal to the row's
current name, except `07-004`, whose leaf the engine builds while it
runs - which is what its `{}` records. Exactly 21 call sites pass `duration=`, and
they are the same 21 the register declares `measured`.

This unit checked `07-004` further. Its prefix constant is
`TA_RAW_PREFIX = "ta.07.004.postcondition.raw."` at `ta_engine.py:3043`.
`VotingEngine._create_indicators` wires 12 indicators. The run recorded
all 12 leaves and no thirteenth.

This unit ran `python -m tools.emitter_registry_check` before and after.
Both times: exit 0, `pins in src 74`, `registry rows 74`,
`instrument controls OK`, no `E` line, no `W1` line.

## The three-way partition of the 74

A pin this run cannot reach is not a pass and is not a failure. It has
**no verdict**, and this report says so rather than folding it into
either column.

| group | pins | what decides membership |
|---|---|---|
| exercised, verdict given | 36 | the pin fired; the analyser held its record against the register |
| reachable by the Simulator, NOT exercised by this run's data | 4 | the call site is on the Simulator's own execution path; this run's inputs did not take the branch. NO VERDICT |
| outside the Simulator's surface | 33 | the call site belongs to a surface the Simulator does not own. NO VERDICT |
| cannot fire anywhere | 1 | no reference of any kind in the tree. This is the one failure |

The register's own rule governs the third group:

> "A 'cannot fire here' verdict is only admissible when it names the
> exact guard, by file and line, that blocks the pin, and that citation
> is re-resolved on every run."

This run resolved every citation below from the tree.

### Reachable by the Simulator, not exercised - 4 pins, no verdict

| ID | name | why this run did not take it |
|---|---|---|
| `01-001` | `bot.01.001.postcondition.capital_reservation` | the REFUSAL path of `ScrummingBot._ensure_capital_reservation`. The run entered that function and took the GRANT path 37 times. Nothing refused a reservation |
| `01-003` | `bot.01.003.postcondition.adoption_capped` | a branch inside `ScrummingBot.tick`, which the run entered 234,139 times. No adoption hit the cap |
| `02-001` | `extractor.02.001.postcondition.tranche_contained` | `ScrummingBot.apply_extractor_tranche_return` has ONE caller, `src/trading/extractor_bot.py:1558`. The loaded fleet holds 38 bots and all 38 are `mode=scrumming`. No ExtractorBot exists to call it |
| `02-002` | `extractor.02.002.invariant.arrival_atomic` | the same function, the same reason |

`01-001` and `01-003` sit inside functions the run drove hard. Different
market data reaches them. `02-001` and `02-002` need a fleet that holds
an Extractor bot, and the operator's fleet does not.

### Outside the Simulator's surface - 33 pins, no verdict

| owner | pins | guard, resolved on this run |
|---|---|---|
| History tab | `05-002` to `05-007` | `src/gui/history_tab.py` was never imported. The Simulator does not construct `HistoryTab` |
| exchange trade-history scan | `05-001` | `CCXTConnector._scan_trade_history`, `src/exchange/ccxt_connector.py:778`. The run DID import the module; the function body never ran. Its callers sit on the History tab's fetch path |
| Trading tab | `12-001` to `12-006` | the run imported `src/gui/main_window.py` and constructed no `MainWindow`, so no `_setup_ui` body ran |
| Asset Charts tab | `13-001` to `13-005` | `MainWindow` builds `TradeChartsTab`. No instance existed |
| Console tab | `14-001` to `14-005` | `MainWindow._emit_console_health` and `MainWindow._toggle_console_pause`. No instance existed |
| Exchange tab | `15-001` to `15-005` | `MainWindow` builds `ExchangeTab`. No instance existed |
| API Tester tab | `16-001` to `16-005` | `MainWindow` builds `APITesterTab`. No instance existed |

A Simulator run cannot exercise the API Tester tab. This report gives
those five pins no verdict. They are not a failure and not a pass.
The run never read the credentials that tab holds.

### Cannot fire anywhere - 1 pin, and the whole finding

**`swarm.11.002.postcondition.paper_run_registered`,
`src/gui/bot_visualizer.py:2315`.**

Its enclosing function is `BotVisualizationTab.register_paper_run`. The
AST walk over 164 files under `src/` finds:

| reference kind | count |
|---|---|
| direct calls | 0 |
| attribute references | 0 |
| bare name loads | 0 |
| string literals of the name | 0 |

Zero of every kind. Its sibling `register_sim_run` scores 0 direct calls
but one string literal, at `nuclear_mode_panel.py:636`, inside
`getattr(swarm, "register_sim_run", None)`. That sibling fired in this
run. The two methods are next to each other in one class, and only one
of them carries a caller.

Coverage agrees with the walk. `register_sim_run` ran; the body of
`register_paper_run` never did, in a run that constructed
`BotVisualizationTab` and drove the Nuclear path that reaches its
sibling.

The repo already knew. `docs/audits/2026-08-05_paper_trader_concept_
spec.md` line 41 records `register_paper_run` with "zero callers".
Nothing has changed since, and 10.2 gave the pin a name and a register
row anyway.

This is a FINDING, not a repair. This unit does not fix it. A pin that
can never produce a verdict is decoration that reads as evidence, and
that is the exact defect the register exists to prevent.

## Per-pin results

A script renders the tables below from the run data. Nothing here
repeats a number by hand.

### A. Counts

| group | pins |
|---|---|
| register rows | 74 |
| fired in this run | 36 |
| fired and in spec | 36 |
| fired and OUT of spec | 0 |
| silent | 38 |
| records observed | 3799113 |
| names fired with no register row | 0 |

### B. Fired, in spec

| ID | name | signal type | duration term | records | duration on records | ok values |
|---|---|---|---|---|---|---|
| `01-002` | `bot.01.002.postcondition.capital_reservation` | `postcondition` | `none` | 37 | 0 | True=37 |
| `03-001` | `fleet.03.001.postcondition.bots_loaded` | `postcondition` | `measured` | 3 | 3 | True=3 |
| `03-002` | `fleet.03.002.invariant.bot_ids_mirror_live` | `invariant` | `forbidden` | 3 | 0 | True=3 |
| `03-003` | `fleet.03.003.invariant.sections_imported` | `invariant` | `forbidden` | 3 | 0 | True=3 |
| `03-004` | `fleet.03.004.postcondition.wires_loaded` | `postcondition` | `measured` | 3 | 3 | True=3 |
| `03-005` | `fleet.03.005.invariant.state_parity` | `invariant` | `forbidden` | 114 | 0 | True=114 |
| `03-006` | `fleet.03.006.postcondition.state_imported` | `postcondition` | `deferred` | 3 | 0 | True=3 |
| `03-007` | `fleet.03.007.postcondition.positions_seeded_from_lots` | `postcondition` | `deferred` | 3 | 0 | True=3 |
| `04-001` | `gui.04.001.postcondition.voting_panel.fit` | `postcondition` | `deferred` | 7 | 0 | True=7 |
| `06-001` | `sim.06.001.postcondition.candles_stepped` | `postcondition` | `deferred` | 2 | 0 | False=1, True=1 |
| `06-002` | `sim.06.002.postcondition.bot_ticks_did_work` | `postcondition` | `deferred` | 2 | 0 | True=2 |
| `06-003` | `sim.06.003.counter.ticks_before_tape` | `counter` | `forbidden` | 2 | 0 | None=2 |
| `06-004` | `sim.06.004.counter.trades_fired` | `counter` | `forbidden` | 2 | 0 | None=2 |
| `06-005` | `sim.06.005.invariant.exceptions` | `invariant` | `forbidden` | 2 | 0 | True=2 |
| `06-006` | `sim.06.006.event.window_played` | `event` | `forbidden` | 2 | 0 | None=2 |
| `06-007` | `sim.06.007.postcondition.fleet_spawned` | `postcondition` | `measured` | 1 | 1 | True=1 |
| `06-008` | `sim.06.008.invariant.state_persisted` | `invariant` | `forbidden` | 1 | 0 | True=1 |
| `06-009` | `sim.06.009.invariant.spawn_drift` | `invariant` | `forbidden` | 1 | 0 | True=1 |
| `06-010` | `sim.06.010.postcondition.bot_table.rendered` | `postcondition` | `deferred` | 2 | 0 | True=2 |
| `06-011` | `sim.06.011.postcondition.price_chart.fed` | `postcondition` | `deferred` | 430 | 0 | True=430 |
| `06-012` | `sim.06.012.postcondition.gate_status.rendered` | `postcondition` | `deferred` | 430 | 0 | True=430 |
| `06-013` | `sim.06.013.state_transition.mode_selected` | `state_transition` | `forbidden` | 1 | 0 | True=1 |
| `06-014` | `sim.06.014.event.log.line` | `event` | `forbidden` | 120 | 0 | None=120 |
| `07-001` | `ta.07.001.postcondition.coverage_per_bot` | `postcondition` | `none` | 71 | 0 | True=71 |
| `07-002` | `ta.07.002.invariant.invariants` | `invariant` | `forbidden` | 2 | 0 | True=2 |
| `07-003` | `ta.07.003.postcondition.computed` | `postcondition` | `measured` | 273967 | 273967 | True=273967 |
| `07-004` | `ta.07.004.postcondition.raw.{}` | `postcondition` | `none` | 3287604 | 0 | None=3866, True=3283738 |
| `08-001` | `tick.08.001.event.throttled` | `event` | `forbidden` | 181259 | 0 | None=181259 |
| `08-002` | `tick.08.002.event.worked` | `event` | `forbidden` | 53994 | 0 | None=53994 |
| `08-003` | `tick.08.003.event.exit_dust_band` | `event` | `forbidden` | 921 | 0 | None=921 |
| `09-001` | `topology.09.001.state_transition.bot_attached` | `state_transition` | `forbidden` | 114 | 0 | None=114 |
| `09-002` | `topology.09.002.postcondition.wires_received` | `postcondition` | `measured` | 3 | 3 | True=3 |
| `10-001` | `ytd.10.001.gauge.trades_fetched` | `gauge` | `forbidden` | 1 | 0 | None=1 |
| `10-002` | `ytd.10.002.postcondition.fleet_symbol_coverage` | `postcondition` | `measured` | 1 | 1 | False=1 |
| `10-003` | `ytd.10.003.gauge.per_symbol_counts` | `gauge` | `forbidden` | 1 | 0 | None=1 |
| `11-001` | `swarm.11.001.postcondition.sim_run_registered` | `postcondition` | `measured` | 1 | 1 | True=1 |

### C. Fired, OUT of spec

None. Every pin that fired carried the name, the signal type and the site the register declares, and a duration consistent with its 10.3 disposition.

### D. Silent, by fault kind

| fault kind | pins |
|---|---|
| `branch-not-taken` | 2 |
| `enclosing-function-never-entered` | 30 |
| `module-not-executed` | 6 |

**`branch-not-taken`** — 2 pins

| ID | name | source | enclosing function | callers of that function |
|---|---|---|---|---|
| `01-001` | `bot.01.001.postcondition.capital_reservation` | `src/trading/scrumming_bot.py:1354` | `ScrummingBot._ensure_capital_reservation` | 1 direct |
| `01-003` | `bot.01.003.postcondition.adoption_capped` | `src/trading/scrumming_bot.py:6601` | `ScrummingBot.tick` | 2 direct |

**`enclosing-function-never-entered`** — 30 pins

| ID | name | source | enclosing function | callers of that function |
|---|---|---|---|---|
| `02-001` | `extractor.02.001.postcondition.tranche_contained` | `src/trading/scrumming_bot.py:3268` | `ScrummingBot.apply_extractor_tranche_return` | 1 direct |
| `02-002` | `extractor.02.002.invariant.arrival_atomic` | `src/trading/scrumming_bot.py:3283` | `ScrummingBot.apply_extractor_tranche_return` | 1 direct |
| `05-001` | `history.05.001.postcondition.scan_complete` | `src/exchange/ccxt_connector.py:778` | `CCXTConnector._scan_trade_history` | 2 direct |
| `11-002` | `swarm.11.002.postcondition.paper_run_registered` | `src/gui/bot_visualizer.py:2315` | `BotVisualizationTab.register_paper_run` | NONE OF ANY KIND |
| `12-001` | `trading.12.001.postcondition.tab_assembled` | `src/gui/main_window.py:4926` | `MainWindow._setup_ui` | 12 direct |
| `12-002` | `trading.12.002.postcondition.exchange_tab_routed` | `src/gui/main_window.py:7365` | `MainWindow.add_exchange_tab` | 1 direct |
| `12-003` | `trading.12.003.postcondition.exchange_tabs_synced` | `src/gui/main_window.py:9413` | `MainWindow._sync_exchange_tabs` | 1 direct |
| `12-004` | `trading.12.004.postcondition.active_layer_alias` | `src/gui/main_window.py:9292` | `MainWindow._toggle_trading_mode` | 0 direct, 1 indirect |
| `12-005` | `trading.12.005.postcondition.activity_log_paused` | `src/gui/main_window.py:5069` | `MainWindow._setup_ui._on_activity_pause_toggled` | 0 direct, 1 indirect |
| `12-006` | `trading.12.006.postcondition.notification_relayed` | `src/gui/main_window.py:5002` | `MainWindow._setup_ui._NotifyStub.notify` | 15 direct |
| `13-001` | `charts.13.001.invariant.panels_mounted` | `src/gui/main_window.py:1417` | `TradeChartsTab.update_charts` | 1 direct |
| `13-002` | `charts.13.002.postcondition.panel_symbols_current` | `src/gui/main_window.py:1426` | `TradeChartsTab.update_charts` | 1 direct |
| `13-003` | `charts.13.003.postcondition.timeframe_rearmed` | `src/gui/main_window.py:1462` | `TradeChartsTab._on_tf_changed` | 1 direct |
| `13-004` | `charts.13.004.postcondition.panel_refreshed` | `src/gui/main_window.py:1586` | `TradeChartsTab.fetch_chart_data` | 1 direct |
| `13-005` | `charts.13.005.invariant.panels_fresh` | `src/gui/main_window.py:1621` | `TradeChartsTab.fetch_chart_data` | 1 direct |
| `14-001` | `console.14.001.invariant.records_rendered` | `src/gui/main_window.py:6381` | `MainWindow._emit_console_health` | 0 direct, 1 indirect |
| `14-002` | `console.14.002.invariant.view_holds_rendered` | `src/gui/main_window.py:6392` | `MainWindow._emit_console_health` | 0 direct, 1 indirect |
| `14-003` | `console.14.003.invariant.drain_alive` | `src/gui/main_window.py:6403` | `MainWindow._emit_console_health` | 0 direct, 1 indirect |
| `14-004` | `console.14.004.postcondition.pause_quiets_both_panes` | `src/gui/main_window.py:6229` | `MainWindow._toggle_console_pause` | 0 direct, 1 indirect |
| `14-005` | `console.14.005.postcondition.pause_buffer_delivered` | `src/gui/main_window.py:6258` | `MainWindow._toggle_console_pause` | 0 direct, 1 indirect |
| `15-001` | `exchange.15.001.postcondition.command_routed_to_chosen_table` | `src/gui/main_window.py:3162` | `ExchangeTab._cmd` | 1 direct |
| `15-002` | `exchange.15.002.invariant.every_bot_reaches_a_table` | `src/gui/main_window.py:3320` | `ExchangeTab.update_bots` | 7 direct |
| `15-003` | `exchange.15.003.invariant.selection_survives_refresh` | `src/gui/main_window.py:3333` | `ExchangeTab.update_bots` | 7 direct |
| `15-004` | `exchange.15.004.postcondition.privacy_applied_to_every_field` | `src/gui/main_window.py:3398` | `ExchangeTab._on_global_privacy_clicked` | 0 direct, 1 indirect |
| `15-005` | `exchange.15.005.postcondition.privacy_button_matches_registry` | `src/gui/main_window.py:3448` | `ExchangeTab._on_global_privacy_clicked` | 0 direct, 1 indirect |
| `16-001` | `apitest.16.001.postcondition.label_matches_session` | `src/gui/main_window.py:3796` | `APITesterTab._do_connect` | 0 direct, 1 indirect |
| `16-002` | `apitest.16.002.postcondition.session_released` | `src/gui/main_window.py:3909` | `APITesterTab._do_disconnect` | 0 direct, 1 indirect |
| `16-003` | `apitest.16.003.postcondition.reported_ok_ran_a_test` | `src/gui/main_window.py:4021` | `APITesterTab._run_test` | 1 direct |
| `16-004` | `apitest.16.004.postcondition.green_probe_read_a_body` | `src/gui/main_window.py:4272` | `APITesterTab._raw_http_probe` | 0 direct, 1 indirect |
| `16-005` | `apitest.16.005.postcondition.indicator_is_mappable` | `src/gui/main_window.py:4368` | `APITesterTab._check_exchange_status` | 0 direct, 1 indirect |

**`module-not-executed`** — 6 pins

| ID | name | source | enclosing function | callers of that function |
|---|---|---|---|---|
| `05-002` | `history.05.002.postcondition.trades_stored` | `src/gui/history_tab.py:488` | `HistoryTab._kick_async_fetch._check` | 0 direct, 1 indirect |
| `05-003` | `history.05.003.postcondition.filter_options_built` | `src/gui/history_tab.py:608` | `HistoryTab._populate_filter_options` | 1 direct |
| `05-004` | `history.05.004.postcondition.filters_applied` | `src/gui/history_tab.py:714` | `HistoryTab._apply_filters` | 2 direct |
| `05-005` | `history.05.005.postcondition.page_rendered` | `src/gui/history_tab.py:916` | `HistoryTab._render_page` | 3 direct |
| `05-006` | `history.05.006.postcondition.joiner_indexes_built` | `src/gui/history_tab.py:1180` | `HistoryTab._build_joiner_indexes_for_page` | 1 direct |
| `05-007` | `history.05.007.postcondition.csv_exported` | `src/gui/history_tab.py:1307` | `HistoryTab._export_csv` | 0 direct, 1 indirect |

### E. Duration disposition, held against the records

| disposition | pins in register | of those, fired | records carrying a duration | verdict |
|---|---|---|---|---|
| `measured` | 21 | 7 | 273979 of 273979 | every record of every fired `measured` pin carries a duration |
| `forbidden` | 26 | 18 | 0 of 236543 | no record carries a duration |
| `none` | 16 | 3 | 0 of 3287712 | no record carries a duration |
| `deferred` | 11 | 8 | 0 of 879 | no record carries a duration |


## The live tree was not touched

The operator's Acervator was trading throughout. Two `Acervator.exe`
processes were live. The run never started, stopped or attached to
them.

**Structural containment.** The run set `HOME`, `USERPROFILE`,
`HOMEDRIVE` and `HOMEPATH` to a sandbox, and `ACERVATOR_SIM_STATE_ROOT`,
`ACERVATOR_SIM_LOG_ROOT` and `ACERVATOR_TELEMETRY_ROOT` to throwaway
directories. The driver refuses to start if `HOME` is not the sandbox
and refuses if any of the three roots is unset. The sandbox holds
copies of `bot_state.json`, `settings.json`, `settings.toml`,
`reservation_state.json`, `ta_snapshots`, all 407 Stone Tablet files,
and the gate and trade logs. It does NOT hold
`coinbase_credentials.json`, which was never read, echoed or copied.

**Measured containment.** This unit hashed every file under
`~/.acervator/` before and after, 478 files, excluding the credentials. The files that
changed are `bot_state.json`, `bot_state.backup.json`,
`recovery/last_snapshot.json` and one `ta_snapshots` entry. Those are
the live application's own writes, and the proof is that
`recovery/last_snapshot.json` changed again inside a 45-second window
during which no run of this unit started or stopped.

The decisive evidence is the other direction. The files a Simulator run
writes all held their hash:

| file | state |
|---|---|
| `~/.acervator/simulator_bot_state.json` | mtime 09:59:49, before this unit began. Unchanged |
| `~/.acervator/feature_telemetry.json` | mtime 2026-08-15. Unchanged |
| `~/.acervator/sim_logs/` | no new file. Newest is from April |
| `~/.acervator_logs/sim/` | no run directory. The run's `signals.jsonl` and SimRunLog went to the throwaway root |

## Evidence on disk

`docs/audits/2026-08-22_item_10_4_evidence/` holds the raw output.

| file | what it holds |
|---|---|
| `mainrun.json` | the run's phases, its per-(sink, name, site) record tally, three examples per name, and each sink's `health()` |
| `verdicts.json` | one verdict per pin, the fault kind for every silent pin, the coverage control result and the drain control result |
| `callsites.json` | all 74 call sites read off the syntax tree: the emit line, the name literal, the kwargs, the enclosing function and its body span |
| `callers.json` | per pin, the direct calls, attribute references, bare name loads and string literals of its enclosing function's name, each with a file and a line |

The driver scripts stay outside the tree. They are measuring
instruments for one unit, not platform code, and a permanent harness is
its own unit with its own two-sided control. This document states each
instrument, its control and the defect that control caught, which is
what a later run needs to rebuild them.

## Adjacent defects, named and not fixed

- `pyproject.toml` sets `omit = ["src/gui/*"]` for coverage, so every coverage number this repo has ever produced says nothing about the GUI tree.
- `BotVisualizationTab.update_paper_run` and `stop_paper_run` have the same zero references as `register_paper_run`; nothing calls the paper-swarm row API at all.
- `tools/harness/coding_archetype` parses a Markdown file as Python, so no `.md` file in `docs/audits/` can pass it; `docs_archetype` is the matching one.
- `emit` accepts a `duration` on a non-`postcondition` pin at run time; rule E8 refuses it statically only. The planted control pin carried `duration=0.5` on an `event` and the sink stored it.
- Three fired `measured` pins produced one record each in this run, so this run alone cannot show their duration varying: `06-007`, `10-002`, `11-001`.
