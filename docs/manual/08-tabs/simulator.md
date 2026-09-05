# Simulator Tab

Reference. The second step of [the promotion pipeline](promotion-pipeline.md):
the live fleet, replayed against stored history.

## What builds it

The window constructs the tab, inserts it beside Trading, and hands it four
getters. Every one is a lambda rather than a bound instance, resolved when the
operator presses Start, because the tabs are built in an order none of them
should depend on.

`src/gui/main_tabs/simulator_tab.py` — `SimulatorTabMixin._build_simulator_tab`

```python
self._simulator = SimulatorTab()
# _reorder_main_tabs runs after every builder, so index 1 is not the final slot.
self._main_tabs.insertTab(1, self._simulator, "Simulator")
if hasattr(self._simulator, "set_connectors_getter"):
    self._simulator.set_connectors_getter(
        lambda: getattr(self, "_exchange_connectors", {})
    )
if hasattr(self._simulator, "set_bot_manager"):
    self._simulator.set_bot_manager(self._bot_manager)
```

The tab is isolated: the window's header strip hides while it is active, and
the tab draws its own strip with the same ten fields against sim balances. A
mode switcher stacks two panels, Fleet Replay and Nuclear Mode.

## Fleet Replay

`FleetReplayPanel` in `src/gui/simulator_tab/fleet/fleet_replay_panel.py` is
the panel. Four steps run it.

**Load.** The panel builds one real bot per saved config. It uses the class
body unchanged, which is the parity guarantee: the sim runs live's code against
a fake exchange rather than a second implementation. The bots exist and hold
their imported state, and the tape only advances when the operator presses
Start Replay.

`src/gui/simulator_tab/fleet/fleet_replay_panel.py` — `_spawn_sim_fleet`

```python
def _spawn_sim_fleet(self) -> int:
    """Construct a real sim bot for every loaded config.

    Returns the number spawned. Reads the Stone Tablet registry
    through the same call Start Replay uses, rather than adding a
    second candle path.

    The controller is built but NOT started: the bots exist, hold
    their imported state and can be inspected, and the tape only
    advances when the operator presses Start Replay.
    """
```

**Configs.** The loader reads the operator's state file read-only and carries
each bot's saved scrumming state and stats alongside its config. The fleet is
never fabricated; it is whatever that file holds.

`src/simulator/fleet/bot_state_loader.py` — `load_bot_configs_from_state`

```python
def load_bot_configs_from_state(
    path: Optional[Path] = None,
    mode_filter: Optional[str] = "scrumming",
) -> list[dict[str, Any]]:
```

`load_smart_wires_from_state` does the same for the topology, and
`summarize_loaded_configs` reports what loaded.

**Fetch.** Fetch YTD pulls the year's live trades so the run has something to
be compared against, and `_compute_soft_start` picks the start point from the
timestamps it found.

**Run.** `FleetReplayController` in
`src/simulator/fleet/fleet_replay_controller.py` drives it.

| Piece | What it does |
| ----- | ------------ |
| `_build_sim` | Assembles the bots |
| `sim_bot_id`, `live_bot_id` | Keep the two id spaces apart |
| `_on_sim_trade` | Records each fill |

One assertion runs once, at the point where the bot set is final and before any
of them can trade.

`src/simulator/fleet/fleet_replay_controller.py` — `_assert_capital_isolation`

```python
def _assert_capital_isolation(self) -> None:
    """Every constructed sim bot must be off the live registry.

    The guards upstream -- the factory raising, `_instantiate_bot`
    refusing, `_crr()` returning None in sim mode -- each protect
    one path. This checks the outcome they exist to produce, once,
    at the point where the bot set is final and before any of them
    can trade. Aborts the run rather than let a replay write sim
    reservations into the operator's live capital state.
    """
```

`ReplayProgress` carries candles played, trades fired and tick failures back to
`_refresh_progress`.

Three more pieces hold the run together. One symbol's rows sit behind a cursor
that never reads past itself.

`src/simulator/fleet/candle_series.py` — `CandleSeries`

```python
class CandleSeries:
    """One symbol's OHLCV history with a replay cursor.

    ``cursor`` starts at 0 and moves through ``step`` or ``step_to_ts``.
    ``rows`` carry unix-millisecond timestamps and are sorted on construction.
    """
```

`FleetSimExchange` in `src/simulator/fleet/sim_exchange.py` is the order and
balance ledger. Above both sits one clock over the union of every series, which
is what makes a timestamp comparison against live meaningful.

`src/simulator/fleet/master_clock.py` — `MasterClock`

```python
class MasterClock:
    """Union-timestamp clock across N CandleSeries.

    Construction:
        clock = MasterClock.from_series(series_iterable)
    Advance:
        while clock.step():
            ts = clock.current_ts_ms()
            for series in series_iterable:
                series.step_to_ts(ts)
    """
```

`SimRunLog` in `src/trading/sim_run_log.py` persists a completed run under the
log root in the live schema.

## The candles

Stone Tablets are the history, and they are read-only throughout. Three
functions in `src/trading/stone_tablets/storage.py` move them between disk and
memory, and a backend module serves them in a ccxt shape.

| Function | What it does |
| -------- | ------------ |
| `read_tablet` | Loads one tablet from disk |
| `write_tablet` | Writes one back |
| `read_manifest` | Carries the index of what exists |

One timeframe is stored and every other rolls up from it.

`src/exchange/tablet_backend.py` — `NATIVE_TIMEFRAME`

```python
NATIVE_TIMEFRAME = "5m"  # what the Stone Tablets store
```

## The validation criterion

The Simulator is validated when the gates latch identically on the same data.
Not profit and loss, and not the trade count.

The sim's gate cell draws each bot's scrum and fold arm state as a
double-stacked grid of lights, ten then nine.

`src/gui/simulator_tab/fleet/sim_visuals.py` — `GateLightsCell`

```python
class GateLightsCell(QWidget):
    """One linear labelled row of trading gates.

    ``_draw_bank`` paints the ten ``_GATE_ORDER_SCRUM`` lights then the
    nine ``_GATE_ORDER_FOLD`` lights, each below its own label.
    ``gate_light_color`` picks every colour, and ``update_gates`` sets the
    arm and blocker state ``paintEvent`` reads.
    """
```

Both that cell and the History table's gate cell read one vocabulary,
`src/trading/gate_vocabulary.py`, so the two surfaces cannot drift apart on
what a gate is called or what blocked it.

The fire-time snapshot is a declared contract, and a declared contract is what
makes a missing field visible instead of silently absent.

`src/core/emit_contracts.py` — the gate-decision contract

```python
EmitContract(
    topic="bot.gate_decision",
    required=("symbol",),
    optional=(
        "scrum_armed",
        "fold_armed",
        "scrum_blockers",
        "fold_blockers",
        "scrum_fixture",
        "fold_fixture",
    ),
    description="Gate evaluation snapshot at fire time.",
),
```

`compare_trades` in `src/trading/stone_tablets/parity_harness.py` prints a
reproduction report into the Performance log, rendered by a sibling function in
the same module. Read that as a report, not as the criterion.

The panel puts the honest label on screen. A run with no live trades loaded is
synthetic and comparable to nothing, and the panel says so rather than looking
like a parity run.

`src/gui/simulator_tab/fleet/fleet_replay_panel.py` — `_note_parity_state`

```python
def _note_parity_state(self) -> None:
    """Say so when the run cannot be compared to live.

    ``_ytd_trades`` being empty is the NORMAL condition, and the panel
    said nothing about it, so a synthetic run looked exactly like a
    parity run on screen.
    """
```

`SimValidationGuard` in `src/trading/sim_validation_guard.py` names the five
conditions under which a run cannot be trusted.

`src/trading/sim_validation_guard.py` — `ValidationIssueType`

```python
class ValidationIssueType:
    NO_TABLET = "no_tablet"
    PRE_LISTING = "pre_listing"
    UNRESOLVABLE_TS = "unresolvable_timestamp"
    SCHEMA_DRIFT = "schema_drift"
    ADDRESS_MISMATCH = "address_mismatch"
```

The last two halt immediately whatever their count, because tolerating them
would mean computing on data whose meaning has shifted. The guard is defined
and covered by tests; no module under `src/` calls it.

## Nuclear Mode

`NuclearModePanel` in `src/gui/simulator_tab/nuclear_mode_panel.py` drives the
controller. The controller loops the same state-file fleet over the tablet
window until stopped, recording each cycle so a late failure traces back to the
cycle that produced it.

`src/simulator/nuclear_fleet_controller.py` — `NuclearFleetController`

```python
class NuclearFleetController:
    """Loops the bot_state fleet over Stone Tablet history until stopped.

    GUI-agnostic: all operator-visible output goes through the callbacks,
    so this is testable without Qt.
    """
```

The market structure varies per loop, and nothing on disk is touched.

`src/simulator/nuclear_candle_source.py` — `noised_series`

```python
def noised_series(
    rows: list,
    seed: int,
) -> tuple[list, float]:
    """Return ``(noised_rows, noise_pct)`` for one pass over *rows*.

    A ``_Tape`` seeded from *seed* perturbs a copy through ``_at``; *rows* is
    left as it was and nothing here touches disk.
    """
```

A second oscillator supplies the load pulse, and it is capped while its cooling
regime holds, because the pulse shares a machine with the live trading engine.

`src/core/system_load_oscillator.py` — `SystemLoadOscillator`

```python
class SystemLoadOscillator:
    """Dual-oscillator for Nuclear Mode tick rate + per-tick workload.
```

`set_swarm_hooks` connects the controller to three methods on the Bot Swarm
tab, which is how a nuclear run appears in the Simulator Swarm sub-tab.

| Hook | Fires when |
| ---- | ---------- |
| `register_sim_run` | A run starts |
| `update_sim_run` | A cycle reports |
| `stop_sim_run` | The run ends |

`set_topologies` replays a Market Inspector proposal shape across the sim bots.

Nuclear is not a validator. It runs after trade-logic alignment is earned, its
noised tape is deliberately not history, and its criteria are coverage and
survival. Nothing in it compares output to live.

`NuclearController` in `src/simulator/nuclear_controller.py` is the earlier
single-tape prototype: one scout bot walking one tape. Nothing under the source
tree constructs it. It stays because both controllers share the noise source.

## Bridge

Five methods serve this screen, and the renderer modules carry the matching
names.

| Bridge method | Serves |
| ------------- | ------ |
| `simulator_tab.state` | The tab, its mode switcher and its table |
| `fleet_replay_panel.state` | Fleet Replay |
| `nuclear_mode_panel.state` | Nuclear Mode |
| `sim_stat_strip.state` | The tab's own ten-field strip |
| `sim_visuals.state` | The gate lights and the sim charts |

Back to [the subsystem index](README.md).
