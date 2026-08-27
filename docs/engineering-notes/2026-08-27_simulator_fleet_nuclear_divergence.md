# Simulator: fleet vs nuclear divergence

Measurement brief for issue #75 [DUP-05]. No production code changed.

Tree: branch `audit-75-simulator-divergence`, base `cc35f83`.

## 0. Headline

Issue #75 asks for `SimExchangeBase` and `ReplayControllerBase` to collapse
"near-duplicate" fleet and nuclear simulators.

Measured result: the duplication is not there.

| claim in #75 | measured |
|---|---|
| two near-duplicate exchanges | 34 distinct members, 7 identical, 11 shared statements |
| two near-duplicate replay controllers | 4 members in both, 0 identical, 0 shared statements |
| two near-duplicate panels | 4 members in both, 1 identical, 3 shared statements |
| all files under `src/gui/simulator_tab/` | 5 of 7 are under `src/simulator/` |

Both `ExchangeInterface` implementations are unreachable from the GUI.
No site in `src/`, `tools/` or the repo root constructs
`FleetSimExchange`. One site constructs `NuclearSimExchange`, inside a
controller that is itself unreachable.

`NuclearFleetController` does not duplicate `FleetReplayController`. It
constructs one (`nuclear_fleet_controller.py:639`) and drives it. The
relationship is composition.

Recommendation: delete, do not abstract. See section 6.

## 1. Reachability

### Method

Two independent instruments, both run through `python -m pytest`.

**M1 — module import graph.** AST over every `.py` in `src/`, `tools/` and
the repo root. Every `import` and `from` node, module-level and
function-local, relative resolved. BFS from `main`.

Controls:

| control | expected | observed |
|---|---|---|
| positive: `src.gui.main_window` | reachable | reachable |
| negative: `tools.gate` | not reachable | not reachable |
| mutation: add edge `main -> <subject>`, per subject | reachable | reachable, 9 of 9 |

The mutation control is the load-bearing one. It proves the BFS can see
each named subject when an edge exists, so a `false` verdict is the
graph's answer, not the instrument's blindness.

**M2 — GUI click.** Construct `NuclearModePanel` under `QApplication`,
rebind `NuclearFleetController` in the panel module to a spy, click
`_start_btn`. Positive: the click constructs the spy. Negative: the panel
module has no `NuclearController` attribute at all.

**M3 — construction sites.** AST over `src/`, `tools/`, repo root for
`ast.Call` nodes whose callee name matches each class. Positive control:
`CCXTConnector` returns 8 sites.

### Verdict

| subject | verdict | entry point |
|---|---|---|
| `FleetReplayController` | reachable from GUI | `main.py` -> `main_window.py:5929` -> `simulator_tab.py:221` -> `fleet_replay_panel.py:348` `_start_btn.clicked` -> `_on_start_clicked` -> `fleet_replay_panel.py:608` |
| `NuclearFleetController` | reachable from GUI | `main.py` -> `main_window.py:5929` -> `simulator_tab.py:283` -> `nuclear_mode_panel.py:287` `_start_btn.clicked` -> `_on_start_clicked` -> `nuclear_mode_panel.py:465` |
| `NuclearController` | **unreachable** | zero importers in `src/`, `tools/`, repo root; zero construction sites |
| `FleetSimExchange` | **unreachable as a class** | module reachable (`fleet_replay_controller.py:58` imports `make_symbol_series_map`); class constructed nowhere outside `tests/` |
| `NuclearSimExchange` | **unreachable** | one construction site, `nuclear_controller.py:278`, inside an unreachable module |

Construction sites, M3, verbatim:

```
"FleetSimExchange":       []
"NuclearController":      []
"NuclearSimExchange":     ["src/simulator/nuclear_controller.py:278"]
"NuclearFleetController": ["src/gui/simulator_tab/nuclear_mode_panel.py:465"]
"FleetReplayController":  ["src/simulator/nuclear_fleet_controller.py:639",
                           "src/trading/topology_stress.py:316",
                           "src/gui/simulator_tab/fleet/fleet_replay_panel.py:608",
                           "src/gui/simulator_tab/fleet/fleet_replay_panel.py:1570"]
```

Test-only reach:

| subject | runtime importers in `tests/` |
|---|---|
| `NuclearController` | `test_nuclear_panel_drives_v2.py:140`, `test_nuclear_scout_isolation.py:59`, `test_nuclear_scout_isolation.py:118` |
| `NuclearSimExchange` | `test_nuclear_limit_fill_price.py:55`, `test_sim_balance_precondition.py:61`, `test_sim_ioc_limit.py:64`, `test_sim_market_limits_agree.py:62` |
| `FleetSimExchange` | 12 sites across 10 files |

### The two-nuclear-controllers question

The brief states `nuclear_mode_panel.py` imports both controllers. It does
not. The panel's complete import list contains one simulator import:

```
src/gui/simulator_tab/nuclear_mode_panel.py:56
    from src.simulator.nuclear_fleet_controller import (
        DEFAULT_CYCLE_CANDLES,
        NuclearFleetController,
    )
```

`NuclearController` has no importer anywhere in `src/`. The panel repointed
at v2 and dropped the v1 import with it.

`NuclearController` and `NuclearFleetController` are **two generations of
one feature**, not two features:

- both are the orchestrator behind the one GUI page, `simulator_tab.py:320`
  stack index 1, selected by mode key `nuclear` at `simulator_tab.py:825`
- `nuclear_mode_panel.py:6` records the replacement explicitly
- `_STATUS_FIELDS` at `nuclear_mode_panel.py:64-91` carries v1's two
  surviving keys, `running` and `uptime_seconds`

They share no implementation. 5 members appear in both classes; 0 are
identical; the highest similarity is 0.745 on `is_running`, a one-line
attribute read.

The mechanisms are different:

| | `NuclearController` (v1) | `NuclearFleetController` (v2) |
|---|---|---|
| unit of work | one scout `ScrummingBot` | whole `bot_state` fleet |
| data | synthetic `TAPEA/USD` tapes | the fleet's own Stone Tablets |
| venue | `NuclearSimExchange` | delegates to `FleetReplayController` |
| loop | one pass, world-clock coroutine | cycles, `max_cycles` or unlimited |
| variation | none | per-cycle market noise + load oscillation |
| `start` | synchronous, `start(loop) -> bool` | coroutine, `async start() -> bool` |

Consequence for #75: the "duplication" between the nuclear and fleet
simulators is dead code on one side. A shared base class would abstract
over a class no user can run.

### Other reachability results

| module | reachable from `main` | note |
|---|---|---|
| `src.simulator.nuclear_candle_source` | yes | via `nuclear_fleet_controller.py:553` `noised_series` |
| `src.simulator.fleet` | yes | via `nuclear_mode_panel.py:398` |
| `src.gui.simulator_tab.nuclear_mode_panel` | yes | `simulator_tab.py:53` |
| `src.gui.simulator_tab.fleet.fleet_replay_panel` | yes | `simulator_tab.py:61` |
| `src.trading.topology_stress` | **no** | zero importers in `src/`; test-only |

## 2. The two `ExchangeInterface` implementations

`ExchangeInterface` is `src/exchange/base.py:159`. Contract: 16
`@abstractmethod` members plus `get_my_trades`, which is concrete and
raises `NotImplementedError` by default.

### Contract coverage

Both cover all 17. Neither is partial.

| member | abstract | `FleetSimExchange` | `NuclearSimExchange` |
|---|---|---|---|
| `exchange_id` | yes | yes | yes |
| `display_name` | yes | yes | yes |
| `connect` | yes | yes | yes |
| `disconnect` | yes | yes | yes |
| `is_connected` | yes | yes | yes |
| `get_ticker` | yes | yes | yes |
| `get_orderbook` | yes | yes | yes |
| `get_ohlcv` | yes | yes | yes |
| `get_balances` | yes | yes | yes |
| `get_balance` | yes | yes | yes |
| `place_order` | yes | yes | yes |
| `cancel_order` | yes | yes | yes |
| `get_order` | yes | yes | yes |
| `get_open_orders` | yes | yes | yes |
| `get_my_trades` | no | yes | yes |
| `get_markets` | yes | yes | yes |
| `get_asset_logo_url` | yes | yes | yes |

### Method-by-method

Normalisation for the "identical" column: `ast.unparse` round-trip, which
removes all comments and normalises quoting, spacing and line breaks; the
leading docstring is then stripped. Identifiers and string literals are
**not** renamed. Statement counts are post-normalisation.

The 7 rows marked identical were re-checked against raw source text with
only blank lines and whole-line comments removed. All 7 are byte-equal
under that second pass as well.

| method | where | Fleet stmts | Nuclear stmts | diff lines | ratio | verdict |
|---|---|---|---|---|---|---|
| `connect` | both | 2 | 2 | 0 | 1.000 | identical |
| `disconnect` | both | 1 | 1 | 0 | 1.000 | identical |
| `exchange_id` | both | 1 | 1 | 0 | 1.000 | identical |
| `get_asset_logo_url` | both | 2 | 2 | 0 | 1.000 | identical |
| `get_balance` | both | 3 | 3 | 0 | 1.000 | identical |
| `get_balances` | both | 1 | 1 | 0 | 1.000 | identical |
| `is_connected` | both | 1 | 1 | 0 | 1.000 | identical |
| `get_order` | both | 5 | 5 | 2 | 0.975 | same behaviour; class name in the error string |
| `_adjust_balance` | both | 1 | 1 | 2 | 0.955 | same behaviour; Fleet coerces via `float()` on read |
| `get_my_trades` | both | 7 | 6 | 3 | 0.954 | same behaviour; Fleet takes an extra `params` argument |
| `display_name` | both | 1 | 1 | 2 | 0.789 | different constant: `"Fleet Sim"` / `"Nuclear Sim"` |
| `cancel_order` | both | 8 | 5 | 5 | 0.731 | **behaviour**: Fleet sets `CANCELLED` and de-indexes; Nuclear returns the order unchanged |
| `get_markets` | both | 7 | 7 | 12 | 0.368 | **behaviour**: Fleet enumerates `self._series` symbols; Nuclear enumerates tape ids and memoises `AssetInfo` |
| `get_ticker` | both | 9 | 7 | 14 | 0.318 | **behaviour**: different lookup (`series` vs `tape`); Fleet raises `ValueError` on unknown symbol, Nuclear resolves through `_resolve_tape` |
| `get_orderbook` | both | 11 | 9 | 14 | 0.250 | **behaviour**: same synthetic-book shape; Fleet floors the step at `1e-9`, Nuclear does not |
| `get_ohlcv` | both | 15 | 4 | 19 | 0.185 | **behaviour**: Fleet honours `timeframe` with a per-`(symbol, tf)` fallback warning and ignores `limit` (fixed `LIVE_EFFECTIVE_PAGE_SIZE`); Nuclear `del timeframe` and honours `limit` |
| `place_order` | both | 46 | 44 | 78 | 0.160 | **behaviour**: see below |
| `get_open_orders` | both | 1 | 2 | 3 | 0.132 | **behaviour**: Fleet filters `self._orders` by `OPEN`; Nuclear returns `[]` unconditionally |
| `__init__` | both | 23 | 11 | 24 | 0.058 | **behaviour**: different constructor contracts entirely |
| `_candle_address_for` | Fleet only | | | | | |
| `_cursor_index` | Fleet only | | | | | |
| `_mark_open` | Fleet only | | | | | |
| `_settle_fill` | Fleet only | | | | | |
| `_sweep_open_limit_orders` | Fleet only | | | | | |
| `_unmark_open` | Fleet only | | | | | |
| `fee_for` | Fleet only | | | | | |
| `has_data` | Fleet only | | | | | |
| `master_clock` | Fleet only | | | | | |
| `on_trade` | Fleet only | | | | | |
| `step` | Fleet only | | | | | |
| `step_symbol` | Fleet only | | | | | |
| `total_clock_ticks` | Fleet only | | | | | |
| `_resolve_tape` | Nuclear only | | | | | |
| `snapshot` | Nuclear only | | | | | |

Totals: 34 distinct members. 19 in both, 13 Fleet only, 2 Nuclear only.
Of the 19 in both: 7 identical, 3 at ratio >= 0.90, 2 differ by a
constant, 7 differ in behaviour.

Shared statements across the identical set: **11**.

### `place_order` — the largest method, and the least shared

Both are ~45 statements. Ratio 0.160.

| | `FleetSimExchange` | `NuclearSimExchange` |
|---|---|---|
| limit that does not cross | rests OPEN, indexed in `_open_by_symbol`, filled later by `_sweep_open_limit_orders` on the next `step()` | returns immediately, status `OPEN` (or `CANCELLED` for `IOC_LIMIT`), never revisited |
| fill settlement | delegated to `_settle_fill` | inline |
| fee rate | per symbol via `fee_for` | one exchange-wide `_fee_pct` |
| id prefix | `fleet_` | `nuclear_` |
| unsupported order type | raises | falls through the limit test |

`sim_exchange.py:300-302` states the fork is deliberate: "Fleet's
resting/sweep model is deliberately NOT copied here — the two venues stay
forks; only the fill PRICE contract crosses."

### `__init__` — the constructors are not compatible

| | `FleetSimExchange` | `NuclearSimExchange` |
|---|---|---|
| data | `series_map: dict[str, CandleSeries]` | `candle_source: NuclearCandleSource` |
| symbols | real `BASE/QUOTE` | synthesised `TAPEx/<QUOTE>` |
| balances | `starting_balances` dict, both sides of every pair seeded | `{quote_currency: quote_seed}` plus one zero per tape |
| fees | `fee_pct` plus `fee_pct_by_symbol` | `fee_pct` only |
| clock | `MasterClock.from_series(...)` | none; the candle source owns the cursor |
| open-order index | `_open_by_symbol` | none |
| opening snapshot | `_opening_balances` | none |

A `SimExchangeBase` would have to hold both a series map and a candle
source, both a per-symbol fee table and a scalar, both a master clock and
nothing. That is a base class each subclass fights.

## 3. The three controllers

`request_stop` is present on all three under two names. `_run` exists on
two. `start` exists on all three with two different signatures.

### Lifecycle surface

| member | `FleetReplayController` | `NuclearFleetController` | `NuclearController` |
|---|---|---|---|
| `__init__` | yes | yes | yes |
| `prepare` | no | yes | no |
| `start` | `async -> bool` | `async -> bool` | `sync(loop) -> bool` |
| `_run` | `async`, 186 stmts | `async`, 27 stmts | no |
| `_run_cycle` | no | yes | no |
| `is_running` | no | yes | yes |
| `stop` | no | yes (alias) | yes |
| `request_stop` | yes | yes | no |
| `snapshot` | no | yes | yes |
| `progress` / `state` | `ReplayProgress` | `NuclearState` | scalar attributes |
| `stopped_event` | yes | yes | no |

### Pairwise divergence

Same normalisation as section 2.

| pair | members in both | identical | shared stmts | highest ratio |
|---|---|---|---|---|
| `FleetReplayController` vs `NuclearFleetController` | 4 of 35 | 0 | 0 | 0.350 (`request_stop`) |
| `NuclearFleetController` vs `NuclearController` | 5 of 28 | 0 | 0 | 0.745 (`is_running`) |
| `FleetReplayController` vs `NuclearController` | 2 of 30 | 0 | 0 | 0.075 (`start`) |

`FleetReplayController` vs `NuclearFleetController`, method by method:

| method | Fleet stmts | NuclearFleet stmts | ratio |
|---|---|---|---|
| `__init__` | 31 | 26 | 0.144 |
| `start` | 37 | 27 | 0.075 |
| `_run` | 186 | 27 | 0.024 |
| `request_stop` | 2 | 6 | 0.350 |

15 members are `FleetReplayController` only. 16 are `NuclearFleetController`
only.

`_run` is where the issue expects the duplication. It runs 186 statements
against 27 at a similarity of 0.024, because the two loops iterate
different things:

- `FleetReplayController._run` (`fleet_replay_controller.py:1791`) is the
  candle tick loop: master clock, per-bot ticks, TA observation, trade
  recording, yield budget.
- `NuclearFleetController._run` (`nuclear_fleet_controller.py:495`) is a
  cycle loop. Its body is `cyc = await self._run_cycle(idx)` plus counter
  accumulation.

### The relationship is composition, not duplication

`nuclear_fleet_controller.py:569` imports `FleetReplayController`;
`nuclear_fleet_controller.py:639` constructs one per cycle inside `_one()`;
`nuclear_fleet_controller.py:685` awaits `ctl.start()`.

`NuclearFleetController` supplies, per cycle:

| input | source |
|---|---|
| `configs` | `bot_state` via `fleet.bot_state_loader` |
| `candles_by_symbol` | `_noised_candles_for_cycle`, a perturbed copy of the tablets |
| `tick_delay_s` | `SystemLoadOscillator.effective_tick_interval(0.8)` |
| `max_candles` | `_cycle_candles` |
| `smart_wires` | `bot_state` |
| load feed | `ctl.set_load_feed(self._osc.tick_workload)` |

`NuclearFleetController` equals `FleetReplayController` plus
looping, market noise, load oscillation, swarm rows and topology
injection. A common base would merge a supervisor with the thing it
supervises.

## 4. Genuinely shared vs only looks shared

### Genuinely shared

| artefact | consumers | note |
|---|---|---|
| `FleetReplayController` | `nuclear_fleet_controller.py:639`, `topology_stress.py:316`, `fleet_replay_panel.py:608`, `fleet_replay_panel.py:1570` | already the shared replay engine; needs no base class |
| `nuclear_candle_source.noised_series` | `nuclear_fleet_controller.py:553`, `topology_stress.py:216` | already a free function; the correct shape |
| `_make_sim_capital_registry` | `fleet_replay_controller.py:149`, imported by `nuclear_controller.py:41` | free function; the only code v1 shares with the fleet tree |
| `src/exchange/base.py` dataclasses | both exchanges | the contract already exists |
| 7 exchange methods, 11 statements | both exchanges | `connect`, `disconnect`, `exchange_id`, `get_asset_logo_url`, `get_balance`, `get_balances`, `is_connected` |
| `set_visual_widgets`, 3 statements | both panels | the only identical panel method |

### Only looks shared

| appearance | measurement |
|---|---|
| "two exchanges to unify" | 11 shared statements out of 145 + 113 in the members they have in common |
| "two replay controllers to unify" | 0 shared statements |
| "two panels to unify" | 3 shared statements out of 294 + 195 |
| "one nuclear feature duplicated" | one generation is unreachable |
| the shared vocabulary — `snapshot`, `is_running`, `stop`, `start`, `_run` | same names, different contracts; `start` alone has two signatures |

The honest description: these are **different things that resemble each
other in naming**. The exchange pair shares 11 statements — smaller than the
7-statement result that issue #79 correctly answered with a 20-line base.
Here even 11 statements are moot, because neither class is reachable.

## 5. Blast radius outside `src/simulator/`

### Production

Exactly one file. `src/trading/topology_stress.py`:

| site | edge |
|---|---|
| `topology_stress.py:216` | `from src.simulator.nuclear_candle_source import noised_series` (function-local) |
| `topology_stress.py:218` | `noised_series(rows, seed)` |
| `topology_stress.py:294` | `from src.simulator.fleet.fleet_replay_controller import FleetReplayController` (function-local) |
| `topology_stress.py:316` | `FleetReplayController(configs=, candles_by_symbol=, tick_delay_s=, max_candles=)` |
| `topology_stress.py:324` | `await ctl.start()` |
| `topology_stress.py:325` | `await ctl.stopped_event.wait()` |
| `topology_stress.py:329-331` | `ctl.progress.candles_played / trades_fired / exceptions` |
| `topology_stress.py:352` | `ctl.tape` |
| `topology_stress.py:364` | `ctl.progress.per_symbol_trade_count` |

Any refactor must preserve: the four constructor keywords, `.start()`,
`.stopped_event`, `.progress`, `.tape`, and the four `ReplayProgress`
fields above.

`topology_stress` is itself unreachable from `main`; it has no importer in
`src/`.

Both imports are deliberately function-local. Hoisting either to module
scope creates the cycle `src.trading.topology_stress ->
src.simulator.fleet.fleet_replay_controller -> src.trading.bot_container`.

### The five consumers named in the brief

The measurement refutes all five. Every hit is a comment or a docstring;
none is an import.

| file | verdict | hits |
|---|---|---|
| `src/trading/sim_run_log.py` | comment only | `:15`, `:445` |
| `src/trading/stone_tablets/parity_harness.py` | comment only | `:6`, `:35`, `:80`, `:83`, `:174`, `:181` |
| `src/trading/ta_engine.py` | comment only | `:46`, `:263` |
| `src/exchange/ccxt_connector.py` | comment only | `:82`, `:1062`, `:1635` |
| `src/exchange/tablet_backend.py` | comment only | `:12`, `:148`, `:151`, `:174`, `:290` |
| `src/trading/bot_container.py` | comment only | `:2165`, inside the `BotManager.__init__` docstring |

The brief's claim that `bot_container.py` "already imports
`nuclear_controller`" is false. `bot_container.py` contains no reference to
`simulator` or `nuclear` outside that one docstring line.

### Direction of dependency

The edge runs simulator -> trading, not the reverse. 28 import statements
from `src/simulator/` into `src/trading`, `src/exchange` and `src/core`,
against 2 statements in the other direction, both in `topology_stress.py`.

Five of the six files the brief named as consumers are in fact
**dependencies** of the simulator:

| module | imported by |
|---|---|
| `src/exchange/ccxt_connector.py` | `fleet_replay_controller.py:56` |
| `src/exchange/tablet_backend.py` | `fleet_replay_controller.py:57` |
| `src/trading/sim_run_log.py` | `fleet_replay_controller.py:680`, `nuclear_fleet_controller.py:1078` |
| `src/trading/ta_engine.py` | `fleet_replay_controller.py:1572`, `:2289` |
| `src/trading/bot_container.py` | `fleet_replay_controller.py:289`, `:326`, `:329`; `nuclear_controller.py:35` |

### Tests

`tests/` is where the real blast radius is.

| module | test files | runtime import sites |
|---|---|---|
| `fleet_replay_controller.py` | 22 | 49 |
| `sim_exchange.py` | 10 | 12 |
| `nuclear_fleet_controller.py` | 8 | 11 |
| `nuclear_sim_exchange.py` | 4 | 5 |
| `nuclear_controller.py` | 2 | 3 |
| `bot_state_loader.py` | 12 | 19 |
| `nuclear_candle_source.py` | 5 | 6 |
| `candle_series.py` | 4 | 6 |
| `simulator_bot_state.py` | 3 | 6 |
| `master_clock.py` | 1 | 1 |

Four tests reach past `__all__` into private names:
`_YIELD_BUDGET_S`, `_make_sim_capital_registry`, `_instantiate_bot`,
`_tape_id_to_base`. Sixteen assert against source TEXT read from a path
string, so a file move breaks them without any import changing:
`test_bus_injection_isolation.py:134`, `test_nuclear_stop_is_responsive.py:117`,
`test_build_sim_smart_wires.py:355`, `test_sim_market_limits_agree.py:160`,
`test_exchange_dataclass_parity.py:48`, `test_signal_timing.py:88`,
`test_ta_raw_prefix_consumer.py:42`, `test_state_parity_on_import.py:200`,
`test_sim_causality_no_future_prices.py:141`,
`test_nuclear_capital_registry_fail_closed.py:36`,
`test_relocated_modules_keep_their_repo_root.py:128`,
`test_nuclear_drives_the_sim_swarm.py:87`, `:117`,
`test_nuclear_receives_topology_injections.py:228`,
`test_nuclear_uses_the_real_fleet_topology.py:85`,
`test_atomic_write_site_equivalence.py:398`.

`tools/`, `dev_harness/` and the repo-root `*.py` files contain zero
consumers. No `importlib` or `__import__` reaches the simulator anywhere.

## 6. Recommendation

**Do not build `SimExchangeBase`. Do not build `ReplayControllerBase`.**

Neither base has enough to hold, and one side of each pair is dead. The
work #75 wants is deletion, and the two halves carry different risk.

Sequence matters: unit 1 removes the sole consumer of unit 2's subject, and
unit 3 depends on nothing.

### Unit 1 — delete `NuclearController`

Owns: `src/simulator/nuclear_controller.py` (462 lines).

Also touches: `tests/test_nuclear_scout_isolation.py`,
`tests/test_nuclear_panel_drives_v2.py:140-142`,
`tests/test_bus_injection_isolation.py:128-160`,
`tests/test_nuclear_stop_is_responsive.py:117`,
`tests/test_nuclear_capital_registry_fail_closed.py`,
`tests/test_event_bus_unsubscribe.py:178`,
`tests/test_sim_capital_registry_fail_closed.py:24`.

Those tests pin invariants against v1's source text — bus-unsubscribe
discipline, capital-registry fail-closed, scout isolation. The invariants
are real and outlive the file. Restate each against
`NuclearFleetController` or `FleetReplayController`, whichever actually
holds the behaviour; do not delete the assertion with the subject.

Proof of no behaviour change: the M1 graph reports `NuclearController` with
zero importers in `src/`, `tools/` and the repo root before the change; the
GUI click probe (M2) constructs `NuclearFleetController` and never
`NuclearController`. Re-run both after. Release gate green.

### Unit 2 — delete `NuclearSimExchange`

Owns: `src/simulator/nuclear_sim_exchange.py` (544 lines).

Blocked on unit 1: `nuclear_controller.py:44` is its only production
importer.

Also touches: `tests/test_nuclear_limit_fill_price.py`,
`tests/test_sim_balance_precondition.py`, `tests/test_sim_ioc_limit.py`,
`tests/test_sim_market_limits_agree.py`.

Three of those four are **cross-venue agreement** tests — they assert
`FleetSimExchange` and `NuclearSimExchange` behave the same on limits,
IOC and the balance precondition. Deleting one side deletes the
comparison. The live venue is `TabletBackend` behind `CCXTConnector`;
re-point each of those three at `TabletBackend`, so they assert the
agreement against the venue that actually runs. Do not delete them.

Proof: M3 reports zero construction sites for `NuclearSimExchange` after
unit 1. Release gate green.

### Unit 3 — decide `FleetSimExchange`

Owns: `src/simulator/fleet/sim_exchange.py` (851 lines).

Independent of units 1-2.

The class has zero construction sites in `src/`, `tools/` and the repo
root. `TabletBackend` replaced it (`tablet_backend.py:148`). But
`make_symbol_series_map` in the same file IS live —
`fleet_replay_controller.py:58`, called at `:887` — and
`test_sim_live_ohlcv_parity.py` pins `LIVE_EFFECTIVE_PAGE_SIZE` at `:67`
equal to `ccxt_connector.EFFECTIVE_OHLCV_PAGE_SIZE`.
That test is the anti-drift bridge the
"no bridges" rule requires, and it must survive.

Split the file: move `make_symbol_series_map` and
`LIVE_EFFECTIVE_PAGE_SIZE` beside `candle_series.py`, then delete the
class and its 10 test files.

**Do this unit last, and only with the operator's sign-off on losing the
tests.** 12 of the class's test sites assert venue behaviour — causality,
open-index, IOC, market limits, state parity — that `TabletBackend` should
also honour. Deleting one without a `TabletBackend` counterpart loses
coverage; it does not remove duplication. If that migration is not funded,
leave the class in place and mark it retained-for-tests; 851 dead lines
cost less than a venue with no behavioural tests.

### Unit 4 — fix the Nuclear visual feed

Owns: `src/gui/simulator_tab/nuclear_mode_panel.py` and
`src/simulator/nuclear_fleet_controller.py:1167-1186`.

Defect D1 below. Independent of units 1-3. Smallest unit, highest
operator-visible value: it restores the price chart and voting readout
during a soak.

Proof: the probe in section 7 is already two-sided. Assert
`_feed_visuals` feeds the chart when given a real
`NuclearFleetController.snapshot()`, and re-run the v1-shaped positive
control unchanged.

### Leave these apart

| candidate | reason |
|---|---|
| `SimExchangeBase` | 11 shared statements; incompatible constructors; both subclasses unreachable |
| `ReplayControllerBase` | 0 shared statements across all three pairs |
| `NuclearFleetController` into `FleetReplayController` | composition, not duplication — one constructs the other per cycle |
| the two panels | 3 shared statements out of 489 |
| `NuclearSimExchange.place_order` into `FleetSimExchange.place_order` | `sim_exchange.py:300-302` forks the resting model deliberately; ratio 0.160 |

## 7. Defects found

Not fixed. All are pre-existing.

### D1 — Nuclear Mode's visual feed reads keys the controller never emits

`src/gui/simulator_tab/nuclear_mode_panel.py:693`

`_feed_visuals` reads `snap["symbol"]` and returns at once on an empty
value. `NuclearFleetController.snapshot()`
(`src/simulator/nuclear_fleet_controller.py:1167-1186`) emits 16 keys, and
`symbol`, `last_price`, `last_volume` and `voting_summary` are none of
them. The nearest key is `symbols`, an integer count.

Consequence: the price chart, the voting readout and the stat strip receive
nothing for the whole soak. This is the same failure the method's own
docstring (`:683-692`) says v3.24.28 repaired; the v3.24.78 repoint from v1
to v2 reintroduced it, because v1's snapshot carried all four keys
(`nuclear_controller.py:249-252`).

Measured, two-sided: the same reader, the same panel, only the payload
differs.

```
missing_from_v2:            ["symbol","last_price","last_volume","voting_summary"]
chart_calls_with_v2_snapshot: []                              <- real payload
chart_calls_with_v1_shape:    [["TAPEA/USD", 101.5, 3.0]]     <- positive control
```

### D2 — `NuclearSimExchange.cancel_order` does not cancel

`src/simulator/nuclear_sim_exchange.py:444-452`

Returns the stored `Order` with its status untouched. An order left `OPEN`
by `place_order` is still `OPEN` after `cancel_order` returns it.
`FleetSimExchange.cancel_order` (`sim_exchange.py:764-774`) sets
`OrderStatus.CANCELLED` and de-indexes.

### D3 — `NuclearSimExchange` can hold an order its own query surface denies

`src/simulator/nuclear_sim_exchange.py:462-464`

`get_open_orders` returns `[]` unconditionally, while `place_order` at
`:333-356` stores a non-crossing `LIMIT` with `status=OrderStatus.OPEN`
in `self._orders`. The order exists, is reachable through `get_order`, and
is invisible to `get_open_orders`. No live venue behaves this way.

### D4 — `NuclearSimExchange.get_ohlcv` discards `timeframe` silently

`src/simulator/nuclear_sim_exchange.py:227`

`del timeframe` on the first statement. Every timeframe request gets the
native tape, with no warning. `FleetSimExchange.get_ohlcv`
(`sim_exchange.py:344-427`) also falls back, but warns once per
`(symbol, timeframe)`.

### D5 — comment cites a method that does not exist

`src/simulator/nuclear_fleet_controller.py:593`

"see `_load_workers()`". `_load_workers` occurs nowhere in the repository
except that comment. Hallucination-rule class H003.

### D6 — two adjacent comments give opposite mechanisms

`src/simulator/nuclear_fleet_controller.py:583-593` states that load
becomes parallelism. `:594-628` states the opposite: "ONE FLEET. LOAD IS
INTENSITY, NOT COPIES." The code at `:634` is `cyc.workers = 1`. The first
block is stale and contradicts the shipped behaviour.

### D7 — `NuclearCycle.workers` is a constant reported as a measurement

`src/simulator/nuclear_fleet_controller.py:116` declares it, `:634` assigns
the literal `1`, and `:141` reports it in `to_dict()`, hence into the
run log. A field that can only be 1 is not an observation.

### D8 — stale `noqa` whose justification names an absent symbol

`src/simulator/nuclear_controller.py:39`

```
)  # noqa: F401  (BotConfig retained for type hints; ...)
```

`BotConfig` is not in the import at `:35-38`, which brings in `BotManager`,
`BotMode` and `make_bot_config`. `coding_archetype` flags the directive as
unused (ruff, medium, line 39). A suppression whose stated reason cites a
symbol that is not there hides whatever the directive was covering.

### D9 — the panel discards `start()`'s refusal

`src/gui/simulator_tab/nuclear_mode_panel.py:527`

`asyncio.run_coroutine_threadsafe(self._controller.start(), loop)` — the
call drops the returned `Future`, so `start()` returning `False`
(`nuclear_fleet_controller.py:417`, already running; `:420`, `prepare()`
refused) leaves the buttons latched into the running state at `:534-540`
over a soak that is not running. The panel's own `prepare()` gate at
`:486` narrows it, which catches the common case first.

### D10 — v1 vocabulary on a v2 panel

`src/gui/simulator_tab/nuclear_mode_panel.py:278` — the Start button reads
`"Start Scout"`. v2 has no scout; it loops the whole fleet. `:171`
labels the section "Tape selector" and `:172` names the widget
`_tape_card`, both v1 terms for what `:187-192` documents as a fleet
readout that is not a selector.

### D11 — stale module documentation

| site | claim | measured |
|---|---|---|
| `src/gui/main_window.py:5921` | "Nuclear Mode is placeholder until Phase B lands `NuclearSimExchange`" | `NuclearSimExchange` shipped and is now unreachable |
| `src/gui/simulator_tab/__init__.py:24` | "No `NuclearSimExchange` yet" | same |
| `src/gui/simulator_tab/__init__.py:19` | Nuclear Mode runs against a `NuclearSimExchange` | it runs against `FleetReplayController` -> `TabletBackend` |
| `src/gui/simulator_tab/simulator_tab.py:88` | "`basic_modes`: `BasicModesPanel` — page 0 of the stack" | `basic_modes_panel.py` does not exist; `:348` sets `self.basic_modes = None` |
| `src/simulator/fleet/sim_exchange.py:4` | "the retired `NuclearSimExchange`" | true of `NuclearSimExchange`, and now equally true of `FleetSimExchange` itself |

### D12 — `_noised_candles_for_cycle` returns the last symbol's amplitude

`src/simulator/nuclear_fleet_controller.py:558-566`

The loop rebinds `pct` on every iteration and returns the last one.
Benign as written: the code hands every symbol the same `seed`, so
`noised_series` returns one amplitude for the whole map. The defect is
latent. If `noised_series` ever draws per series, the returned
`noise_pct` describes one symbol and the run log records it as the
cycle's.

## 8. Not determined

| question | status |
|---|---|
| whether the 12 `FleetSimExchange` test behaviours are already covered against `TabletBackend` | **unknown**. Not measured. Unit 3 must answer it before deleting anything. |
| whether `NuclearFleetController` completes a cycle end to end today | **unknown**. Not executed. The Simulator has initialised no bot since v3.24.84, so nothing here asserts the soak runs. |
| whether `topology_stress` has a non-test entry point planned | **unknown**. Unreachable from `main` today. |
| whether `nuclear_controller.py:34` importing `EventBus` violates the no-bridges rule | **unknown as a ruling**. Observed: `nuclear_controller.py:34,35,40` import `EventBus`, `BotManager` and `ScrummingBot`; `fleet_replay_controller.py:289,290` import `bot_container` and `ScrummingBot`. `tests/` holds no mechanised allowlist test, so nothing in the tree adjudicates it. Unit 1 removes one of the two sites regardless. |
| whether any caller needs `get_my_trades`'s extra `params` argument on `FleetSimExchange` | **unknown**. No caller measured; the argument widens the base signature. |

## 9. Method appendix

| instrument | file | control |
|---|---|---|
| M1 module graph | AST BFS from `main` over `src/`, `tools/`, repo root | positive `src.gui.main_window`; negative `tools.gate`; mutation per subject, 9 of 9 |
| M2 GUI click | `QApplication` + spy on `nuclear_mode_panel.NuclearFleetController` + `_start_btn.click()` | positive: spy constructed; negative: no `NuclearController` attribute on the module |
| M3 construction sites | AST `ast.Call` callee-name scan | positive: `CCXTConnector`, 8 sites |
| M4 divergence | `ast.unparse` round-trip, docstring stripped, no renaming; `difflib.SequenceMatcher` ratio + unified diff | "identical" re-verified on raw text with blank lines and whole-line comments removed |
| M5 visual feed | real panel, real controller snapshot, spy chart | positive: v1-shaped payload feeds the chart; negative: real v2 snapshot does not |

All probes ran through `python -m pytest`, exit code 0. They are not
committed.
