# Decision Records and Glossary

Reference. Where this repository records a decision, and the words the manual
uses, each anchored to the module that implements it.

## The decision-record index

The manual this one replaces carries a decision-record index across three lists.
No file whose name holds "adr", in any case, appears in any commit. The set of
paths any commit across every ref has added holds 1,599 distinct names, and none
matches. Run over that same set, the control returns `src/core/log_paths.py` and
three paths naming the older development protocol, so the query does find a name
when one is present.

No decision-record index exists here, and none has ever existed. Nothing carries
forward from that part of the older manual.

## Where a decision is recorded instead

Five places hold the decisions this repository has made. None of them is an
index, and each answers a different question.

- `docs/engineering-notes/` — 21 notes, ten with an evidence directory beside
  them holding the rows and the script that produced them. One note per
  question, each naming the standard it measures against and the control beside
  every measurement.
- `docs/audits/manual-original-parts-audit.md` — the claim audit of the older
  manual, part by part, with a migration list and a corrections table.
- `.claude/rules/` — three binding standards, on code comments, on documentation
  and on tests. `CLAUDE.md` at the root holds the repository rules above them:
  one role per folder, and no machine-specific path anywhere committed.
- Executable guards under `tests/`. `test_repo_root_inventory.py` holds a reason
  for every tracked file at the repository root, and a reason has to name a
  mechanism. `test_no_dead_sadp_references.py` holds the retirement of the older
  protocol, and records driving itself both ways: reverting the five files it
  guards failed four of its checks and restoring them passed all seven. A
  decision written as a guard fails when someone reverses it, which a decision
  written as prose does not.
- `CHANGELOG.md` and the commit history. See
  [09-updates-and-versioning.md](09-updates-and-versioning.md) for what the
  changelog holds today.

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
- **Scrum/Fold cycle** — the pair, run against volatility rather than against a
  price forecast. A completed cycle ends holding more of the asset than it
  started with.
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
- **Smart Wire** — a capital reinforcement link between two bots.
  `SmartWireManager`, `BotLedger` and `WireTransaction` in
  `src/trading/smart_wire.py`.
- **Phantom balance** — a bot's view of holdings it may not sell yet.
  `PhantomBalanceManager` and `PhantomBalanceBot` in
  `src/trading/phantom_balance.py`.
- **Capital claim** — one bot's hold on a quantity of an asset.
  `effective_available` in `src/trading/capital_reservation.py` answers holdings
  minus every other bot's claim on the same asset, never the caller's own.
- **Fleet** — the bots a run holds, with their wires, ledgers and tranches. All
  of it loads from `bot_state.json` through `StateManager` in
  `src/core/state_manager.py`, which is the only source.

### Deciding a trade

- **Voter** — one indicator's contribution to a direction and a confidence.
  `VotingEngine` in `src/trading/ta_engine.py` runs the twelve.
- **Gate chain** — the ordered checks a candidate trade passes before it fires.
  `GateChain` and `GateContext` in `src/trading/gate_chain.py`. The sell chain
  and the buy chain differ, and [07-indicators.md](07-indicators.md) lists both.
- **Landing Strip** — a tightening detector, `detect_landing_strip_v2` in
  `src/trading/indicators/landing_strip.py`.
- **Band travel** — the mean-reversion read, `MRInspector` in
  `src/trading/mr_inspector.py`.
- **Trade grade** — a letter per completed trade. `grade_trade` in
  `src/trading/trade_grader.py` returns a `TradeGrade` from four scored axes,
  `_score_execution`, `_score_timing`, `_score_strategic` and `_score_outcome`.
  The market regime is recorded beside them and never scored. See
  [10-live-trade-history.md](10-live-trade-history.md).

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
  same logic against a real-time feed and a fake budget. **It is not built.** No
  file named `paper*` exists under `src/`, no commit ever added one, and the
  surface that mentions it defaults to `paper_trader_available: bool = False` in
  `src/gui/main_tabs/stock_main_window_surface.py`, beside a stored import error
  for a module nobody wrote. See
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
- **Rule id** — an `RN` name in `RULE_META` in `src/core/rule_registry.py`. The
  registry has no production importer and the ids bind nothing.

[11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md)
describes all three.

### The title page

- **Solve et coagula** — dissolve and reform, the sense the epigraph
  *Turbator aequilibrii dissolvendus reformandusque* carries on
  [01-title.md](01-title.md). `harvest_svg` in
  `src/competition/trophy_generator.py` letters `SOLVE · ET · COAGULA` around the
  outer arc of the harvest trophy, which is the one place the phrase appears in
  the code.

## The operator's own words

These name a posture rather than a component. They appear in the manual because
the operator uses them, and no module implements any of them.

- **Accumulation trading** — the product category he places Acervator in:
  harvesting volatility to end holding more of the asset, rather than predicting
  a direction.
- **Conceptual hopscotch** — his name for a session hopping across a context
  boundary, which the handoff file exists to carry.
- **Ekthelius the Accumulator** — his handle.

## Trading-engine vocabulary from the legacy manual

Source: LEGACY, the fourteen-part manual, Part 7c "ADR Index and Glossary", page
8. The claim audit calls the trading-engine vocabulary accurate, and it carries
here with each entry re-anchored. The technical-analysis vocabulary from page 10
of the same part is in [07-indicators.md](07-indicators.md), which is where this
file already says such words belong.

- **Advantage** — the final portfolio value minus what passive holding would
  have produced on the same capital. A run wins when this is above zero.
- **Band travel** — price displacement measured as a fraction of the current
  Bollinger Band width, so the threshold follows volatility.
  `band_travel_pct` in `src/trading/container/config.py:100`, default 70.
- **Explode** — the liquidation trigger of the bear-regime accumulator, at a
  recovery to 98 percent of entry. No source in this repository; see
  [15-patent-portfolio.md](15-patent-portfolio.md).
- **Fold** — a profit-realisation event. The target grows by the realised
  amount.
- **Heikin-Ashi candle** — a smoothed price bar. The landing strip reads them,
  in `src/trading/indicators/landing_strip.py`.
- **Interval** — the profit-take threshold for one trade, in percent.
  `scrumming_interval_pct`, default 1.0.
- **Landing strip** — several consecutive same-colour Heikin-Ashi candles with a
  narrow body range against a band boundary. `detect_landing_strip_v2`.
- **Phantom** — a read-only copy of the position at a longer timeframe, read by
  the bias gates. `src/trading/phantom_balance.py`.
- **Price floor** — the invariant that every unit bought back after a fold costs
  at or under the lot's original price. The test is in
  `src/trading/scrumming/tick_phases.py`.
- **Regime** — the market classification a timeframe's indicators produce.
- **Scrum** — a trade inside the zone. In the main bot, a profit-take followed
  by a target increase.
- **Target** — the running dollar goal. It grows on a fold and never shrinks.
- **Tier** — a signal's importance, from structural down to contextual. A
  structural signal can open a trade; a contextual one can only move confidence.
- **Tranche** — one buy kept as its own cost-basis lot, so the fold can decide
  lot by lot. `self._fold_tranches` in `src/trading/scrumming/tick_phases.py`.

The legacy glossary also defines the simulation battery at one size, and the
same legacy manual gives it two other sizes on other pages. No battery engine
has any source in this repository, so no size is the right one to carry. The
entry is dropped and the reason is here.

## Three things deliberately not built

Source: LEGACY, the fourteen-part manual, Part 6 "Department Leads Review",
pages 10 to 17. These are product decisions rather than deferred work, each with
a stated reason, and the claim audit verified each subject absent from the code.
They belong in this file because a decision not to build is still a decision,
and nothing else in this repository records them.

### No classical trend following

Moving-average crossovers, Donchian channels and channel breakouts are absent,
and stay absent. Adding them would put a second trading system inside one
engine, on a different thesis from accumulation. The trend-signal class that
belongs in an accumulation bot is already covered by the MACD voter and its
divergence reading, in `src/trading/ta_engine.py`. A dedicated trend follower
would be a separate product.

### No hard stops

A stop-loss contradicts the price floor. The floor asserts that every unit held
was bought at or under the lot's original price, and a stop would liquidate
exactly the units that structural defence exists to carry through a temporary
drawdown. What the platform has instead is bounded per-event damage:
`CircuitBreakerGate` and the soft and hard trip percentages, and
`SmartCeilingGate` with the position ceiling. Those bound one event. They do not
promise that a long decline costs nothing.

### No tape reading and no order-book depth

Level-two order-book data varies widely in quality between venues and would need
its own data pipeline. At the size this platform trades, the extra signal does
not pay for the infrastructure. The bot reads the line of least resistance from
candle patterns and band positions instead, which the legacy section calls a
derivative signal and admits as such. The decision is scale-based, and the note
that comes with it is the honest part: revisit when the size grows enough for
microstructure to matter.

