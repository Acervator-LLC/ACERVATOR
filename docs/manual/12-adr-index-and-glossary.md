# Decision Records and Glossary

Reference. Where this repository records a decision, and the words the manual
uses, each anchored to the module that implements it.

## Where a decision is recorded

Four places hold the decisions this repository has made. Each answers a
different question.

- `docs/engineering-notes/` — 21 notes, ten with an evidence directory beside
  them holding the rows and the script that produced them. One note per
  question, each naming the standard it measures against and the control beside
  every measurement.
- `.claude/rules/` — three binding standards, on code comments, on documentation
  and on tests. `CLAUDE.md` at the root holds the repository rules above them:
  one role per folder, and no machine-specific path anywhere committed.
- Executable guards in the test suite. One holds a reason for every tracked file
  at the repository root, and a reason has to name a mechanism. A second holds
  the retirement of the older protocol, and it records driving itself both ways:
  reverting the five files it guards failed four of its checks, and restoring
  them passed all seven. A decision written as a guard fails when someone
  reverses it, which a decision written as prose does not.
- `CHANGELOG.md` and the commit history. See
  [09-updates-and-versioning.md](09-updates-and-versioning.md) for what the
  changelog holds today.

The two guards:

```
tests/test_repo_root_inventory.py         a reason per tracked root file
tests/test_no_dead_sadp_references.py     the older protocol's retirement
```

`docs/engineering-notes/ci_failure_ledger.md` is the narrowest of these: one row
per continuous-integration failure, its class, the change that closed it, and
the run that shows it closed. A row leaves the file after three consecutive
green runs hold its tests, and the file states its own ceiling — past 20 rows,
the work is producing failures faster than it closes them.

## Glossary

Every term below names something in the code, and carries the module or symbol
that implements it. The technical-analysis vocabulary is in
[07-indicators.md](07-indicators.md) with the twelve published formulae, and is
not repeated here.

### The accumulation cycle

- **Target** — the dollar value a bot aims to hold in an asset. The scrum sells
  above it and the fold buys back beneath it.
- **Scrum** — a sell of the excess above the target. `ScrummingBot` in
  `src/trading/scrumming_bot.py` decides and places it.
- **Fold** — the buy back on the dip that follows a scrum, carried by
  `apply_profit_fold` in `src/trading/profit_fold.py`.
- **Interval** — the smallest price move between two fires, in percent.
  `scrumming_interval_pct` in `src/trading/container/config.py`, default 1.0.
- **Scrum/Fold cycle** — the pair, run against volatility rather than against a
  price forecast. A completed cycle ends holding more of the asset than it
  started with.
- **Price floor** — every unit bought back after a fold costs at or under the
  lot's original price. `_fold_eligible_tranches` in
  `src/trading/scrumming/tick_phases.py` enforces it.
- **Fold tranche** — one queued slice of scrummed dollars waiting for its buy
  back. `src/trading/scrumming/fold_tranches.py` holds the book.
- **Merge** — `_top_up_remnant_fold_tranches` folds a new sell's dollars into
  part-spent tranches, and `_bound_new_fold_tranches` collapses one sell's fresh
  slice into a single record when the fill arrived as many lots. Both reduce the
  record count without losing a dollar.
- **Despawn** — `_despawn_aged_tranches` removes a tranche older than the bot's
  threshold. It removes the record; it does not delist it, and the count lands
  in the discarded lifetime counter rather than the closed one.
- **Clear** — `clear_fold_tranches` discards every queued tranche and trades
  nothing.

Merge, despawn and clear are the only three functions that collapse or remove a
tranche. [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md) describes each in full.

### Bots and what they hold

- **Scrumming Bot** — the accumulation bot, `ScrummingBot` in
  `src/trading/scrumming_bot.py`. One per traded symbol.
- **Extractor Bot** — `ExtractorBot` in `src/trading/extractor_bot.py`, a chunked
  state machine rather than a scrum/fold engine.
- **Smart Wire** — a capital reinforcement link between two bots, in
  `src/trading/smart_wire.py`.
- **Phantom balance** — a bot's view of holdings it may not sell yet, in
  `src/trading/phantom_balance.py`.
- **Capital claim** — one bot's hold on a quantity of an asset.
  `effective_available` in `src/trading/capital_reservation.py` answers holdings
  minus every other bot's claim on the same asset, never the caller's own.
- **Fleet** — the bots a run holds, with their wires, ledgers and tranches. All
  of it loads from `bot_state.json` through `StateManager`, which is the only
  source.

The classes behind the wire, the phantom balance and the fleet load:

```python
class SmartWireManager: ...     # src/trading/smart_wire.py
class BotLedger: ...
class WireTransaction: ...

class PhantomBalanceManager: ...    # src/trading/phantom_balance.py
class PhantomBalanceBot: ...

class StateManager: ...     # src/core/state_manager.py
```

### Deciding a trade

- **Voter** — one indicator's contribution to a direction and a confidence.
  `VotingEngine` in `src/trading/ta_engine.py` runs the twelve.
- **Gate chain** — the ordered checks a candidate trade passes before it fires,
  in `src/trading/gate_chain.py`. The sell chain and the buy chain differ, and
  [07-indicators.md](07-indicators.md) lists both.
- **Heikin-Ashi candle** — a smoothed price bar. `detect_landing_strip_v2` in
  `src/trading/indicators/landing_strip.py` reads them.
- **Landing Strip** — a tightening detector, `detect_landing_strip_v2` in
  `src/trading/indicators/landing_strip.py`.
- **Band travel** — the mean-reversion read, `MRInspector` in
  `src/trading/mr_inspector.py`.
- **Trade grade** — a letter per completed trade, from four scored axes in
  `src/trading/trade_grader.py`. The market regime is recorded beside them and
  never scored. See [10-live-trade-history.md](10-live-trade-history.md).

The gate chain's two classes and the grader's five entry points:

```python
class GateChain: ...    # src/trading/gate_chain.py
class GateContext: ...

def grade_trade(record, ctx) -> TradeGrade: ...     # src/trading/trade_grader.py
def _score_execution(...): ...
def _score_timing(...): ...
def _score_strategic(...): ...
def _score_outcome(...): ...
```

### Getting a strategy to real money

- **Promotion pipeline** — Market Inspector, then Simulator, then Paper Trader,
  then Live. Each step is a gate rather than a mode, and
  [08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) holds the
  entry and exit criteria for each.
- **Gate-latch criterion** — the Simulator's own criterion. It passes when the
  gates latch identically on the same candles as live, not when profit or trade
  count matches. See [08-tabs/simulator.md](08-tabs/simulator.md).
- **Stone Tablet** — a stored candle history a Simulator run replays.
  `src/simulator/fleet/fleet_replay_controller.py` drives the replay and
  `src/simulator/fleet/sim_exchange.py` serves the candles.
- **Paper Trader** — the step between Simulator and Live, defined by running the
  same logic against a real-time feed and a fake budget. In development. The
  surface that mentions it defaults to `paper_trader_available: bool = False` in
  `src/gui/main_tabs/stock_main_window_surface.py`. See
  [08-tabs/paper-trader.md](08-tabs/paper-trader.md).
- **Proof of Accumulation** — the competition package, `src/competition/`. It
  holds the bot identity, the Merkle log, the challenge protocol, the token
  ledger and the local chain. Its two screens are shelved by the operator's own
  direction. See
  [08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md).

### The development harness

- **Archetype** — a domain quality gate under `dev_harness/harness/`, reporting a
  `passed` boolean.
- **Handoff** — `ACERVATOR_HOP8.md`, measured for drift by `tools/hop_check.py`.
- **Rule id** — an RN name in `RULE_META`, in `src/core/rule_registry.py`. The
  registry has no production importer and the ids bind nothing.

[11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md)
describes all three.

### The title page

- **Solve et coagula** — dissolve and reform, the sense the epigraph
  *Turbator aequilibrii dissolvendus reformandusque* carries on
  [01-title.md](01-title.md). One function letters SOLVE · ET · COAGULA around
  the outer arc of the harvest trophy, and that is the one place the phrase
  appears in the code.

```python
def harvest_svg(d: TrophyData) -> str: ...      # src/competition/trophy_generator.py
```

## The operator's own words

These name a posture rather than a component. They appear in the manual because
the operator uses them, and no module implements any of them.

- **Accumulation trading** — the product category he places Acervator in:
  harvesting volatility to end holding more of the asset, rather than predicting
  a direction.
- **Conceptual hopscotch** — his name for a session hopping across a context
  boundary, which the handoff file exists to carry.
- **Ekthelius the Accumulator** — his handle.

