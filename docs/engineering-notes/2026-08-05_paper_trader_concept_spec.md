<!-- Acervator — captured 2026-08-05, operator directive -->

# Paper Trader — Concept Specification

**Reference.** Operator-stated concept, captured verbatim in intent on
2026-08-05. **Not a build plan.** Paper development is explicitly gated:

> "We will develop Paper after Sim + Nuclear are verified fully working."

This document exists so the concept is not re-derived or half-remembered
when that gate opens. Where the platform already has a piece, it is named;
where it does not, that is stated rather than implied.

---

## 1. The seven requirements

| # | Requirement | Status today |
|---|---|---|
| 1 | Identical to the Trading tab in every way, bar a slightly different colour scheme for distinguishability | **Not built.** No source file exists |
| 2 | Trades **in real time** against real market data; executes and records everything on paper, never real money | **Not built** |
| 3 | Compounds and tests Smart Wire topologies using Bot Swarm (Paper) | **Not built.** Smart Wire exists; Paper layer is inert |
| 4 | Must interoperate with Market Inspector and Bot Swarm (Paper) | **Not built** |
| 5 | Market Inspector must push proposed topologies **and opposing trades** to Live, Sim **and** Paper | **Partial** — see §3 |
| 6 | Records all activity and results to a Paper Trading log | **Not built.** Pattern exists (`SimRunLog`) |
| 7 | All emitters tracked, to isolate issues. **Standard going forward** | **Partial** — see §4 |

---

## 2. What survives to start from

There is **no deprecated Paper Trader source file**. Verified 2026-08-05:
the working tree, all 159 release archives on the operator's desktop, and
a tree-wide grep for `class PaperTrader` — zero hits.

The genuine starting points:

| Asset | Location | Note |
|---|---|---|
| Design doc | `_archive/docs_audits_pre_2026_07_24/2026-05-19_simulator_paper_trader_design.md` | 35 KB, operator-approved 2026-05-19. Phases E–G cover Paper. Records the decision "Simulator first (A–D), then Paper Trader (E–G)" — which matches the current gating |
| Row API | `bot_visualizer.py:2030-2088` | `register_paper_run` / `update_paper_run` / `stop_paper_run` exist with **zero callers** |
| Sentinels | `main_window.py:3779-3782` | `_paper_trader`, `_paper_trader_stack`, `_paper_trader_crypto`, `_paper_trader_equity` — all `None` |
| Broken import | `stock_main_window.py:363` | `from .paper_trader_tab import PaperTraderTab` — module does not exist. **Live defect independent of Paper work**: any path reaching it raises `ImportError` |

Requirement 1 ("identical to the Trading tab") makes the 2026-05-19
decision *"Same as Trading tab — one paper tab per real exchange the
operator has configured. Visual chrome 1:1 with Trading"* still current,
and it pre-dates this spec by two months. The two agree.

---

## 2a. Real time is the defining distinction

Operator correction, 2026-08-05: **"Trades in real time."**

This is what separates Paper from the Simulator, and it is not a detail:

| | clock | data | fills | money |
|---|---|---|---|---|
| **Simulator** | replayed master clock, as fast as CPU allows | Stone Tablet history | modelled against historical candles | none |
| **Paper** | **wall clock** | **live market feed** | modelled against live prices | none |
| **Live** | wall clock | live market feed | real exchange orders | real |

Consequences that follow from real-time and would be missed if Paper
were built as "Simulator with a different label":

- **No candle to sweep.** The Simulator fills a LIMIT order when a
  historical candle's range crosses the price. Paper has no future
  candle — it must decide fills from a live tick or book snapshot.
- **Rate limits are real.** A replay reads tablets from disk; Paper
  competes with Live for the same exchange API budget. The header
  already shows `API coinbase: n/600 CPM`, and Paper doubles the
  pressure on it.
- **It cannot be run faster than wall clock.** Load oscillation, soak
  cycles and the anchored fast-path are all Simulator concepts and do
  not transfer.
- **Latency and staleness become observable**, which is precisely the
  class of defect Paper is meant to catch before Live.

---

## 3. The promotion pipeline (requirement 5)

The operator's stated workflow:

> "Simulator pushes to Paper which pushes to Live. This flow will also
> form the backbone of the platform intelligent, self-calibration
> feedback loop that will allow the platform to run in Full Auto."

    Market Inspector
         │  proposes topologies + opposing trades
         ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │Simulator│ ───► │  Paper  │ ───► │  Live   │
    └─────────┘      └─────────┘      └─────────┘
     backtest         real data,       real money
                      paper fills

Each stage is a promotion gate: a topology earns its way forward by
surviving the previous one. That ordering is what makes the eventual
Full Auto loop safe — Full Auto is explicitly deferred until "everything
[is] working and optimized."

**Today Market Inspector can push to none of the three as a verified
path.** `topology_proposals.py` generates proposals and
`market_inspector_topologies.py` previews them, but the adopt handoff to
`SmartWireManager.set_wire` and its reachability are what the running
Bot Swarm audit is measuring. Treat the arrow into Simulator as the
first one to make real, since Simulator is the only stage that currently
runs topologies at all (`topology_stress.py`, v3.24.26).

**Note on scope:** requirement 5 says topologies **and opposing trades**.
Opposing-trade distance is a live gate term
(`scrumming_bot.py:10019-10023`), not part of the topology proposal
schema in `topology_proposals.py`. Pushing it is a schema extension, not
just a new destination.

---

## 3a. Simulator → Paper continuation (operator, 2026-08-05)

> "Allow Simulator back tests to continue running as Paper Trader
> instances. The end state of the Simulator fleet (earnings included)
> would transpose to the Paper Trader and then begin running in real
> time."

This makes requirement 5's first arrow concrete. "Simulator pushes to
Paper" stops being a config handoff and becomes a **continuation**: the
fleet that survived the backtest keeps trading, with its evolved state
intact, against live ticks.

It also fits how the platform already works. `target_balance` grows
organically through the Tranche-Surplus mechanism (`scrumming_bot.py`
v3.16.50), so a fleet's *earnings* are literally encoded in its evolved
config plus its tranche book. Transposing that state IS transposing the
earnings.

### What must transpose

| State | Why it matters |
|---|---|
| base holdings per bot | the accumulated position — the whole point |
| quote balance | spendable, per quote currency |
| `_fold_tranches` (incl. `wire_credits` + `wire_credits_rolled`) | the compounding book and its provenance |
| `target_balance` / `_anchor_target_balance` | where surplus growth is recorded — the earnings |
| `stats` (realised, scrummed, folded, tranches lifetime) | reporting continuity across the boundary |
| Smart Wire topology + ledgers | the thing under test |

### Three hazards, two of them silent

**1. `_last_trade_price` carried across a price gap → spurious immediate fire.**
Gates are threshold comparisons against `_last_trade_price` and the
opposing-trade hysteresis reference. The sim's final candle close and
the live ticker at handoff are different numbers. Carry the sim value
and the first live tick can look like a large instantaneous move,
firing SCRUM or FOLD on an artefact of the handoff rather than on the
market. Decide explicitly: **re-anchor to the live ticker at
transposition**, or carry and accept the fire. Re-anchoring is almost
certainly right, and it must be a deliberate line of code with a
comment, not an omission.

**2. The time gap between sim end and Paper start — measured at ~4 DAYS.**
An earlier draft of this section guessed the gap was "small today".
Measured 2026-08-05 across all 406 tablets:

    freshest  97.6 h old
    median    97.6 h old
    stalest  102.1 h old

So a continuation started right now would hand Paper a fleet whose last
known price is **four days stale**, across the entire archive. During
that gap the position was unmanaged and prices moved; the transposed
holdings are valued at a four-day-old close.

This is not a reason to reject the feature — it is a reason the handoff
must **re-fetch live prices and revalue before the first tick**, and
must refuse or loudly warn past a staleness threshold. It also means a
continuation is only as good as the archive: a Stone Tablet backfill
should be part of the continuation flow, not an assumption about it.

Surface the gap in the Paper log at start ("continued from sim run
&lt;id&gt;, N hours stale") rather than letting it be invisible.

**3. Do NOT reuse this mechanism for Paper → Live.**
This is the important one. Sim → Paper transposes notional state into
notional state, which is sound. Paper → Live must NOT transpose
holdings: **live positions are exchange-authoritative**. A paper bot
believing it holds 0.5 BTC does not make 0.5 BTC exist in the account,
and writing that belief into a live bot would produce exactly the
phantom-holdings class that MEM-257 fail-closed verification exists to
prevent. What may promote from Paper to Live is the *topology and
config* — never the position book.

### The serialization already mostly exists

A continuation needs a state snapshot, and the platform already has the
shape of one. `BotContainer.get_full_state` (`bot_container.py:1345`)
calls `export_scrumming_state` and produces exactly the dict that
`bot_state.json` stores — holdings, `_fold_tranches`, `target_balance`,
`_anchor_target_balance`, stats. `restore_bots_from_state`
(`bot_container.py:2418`) is the matching reader.

So the transposition format is **the bot_state schema**, and both
directions are already written and exercised in production. A
continuation is closer to "serialize the sim fleet through the existing
path, hand the dict to Paper" than to new persistence work.

Two gaps to note: `ScrummingBot` itself exposes no `get_state` /
`restore_state` (the serialization lives on the container), and
`current_holdings` is **not** among the persisted fields — verified
earlier: 0 of 35 live bots carry it. Holdings would have to be added to
the transposed payload explicitly, since for live bots they come from
the exchange rather than from state.

### Open questions this adds

6. Does a continuation start a fresh Paper log, or append to the sim
   run's record? Provenance argues for a new log that names the parent
   run id.
7. What happens to a bot whose symbol has no live feed at handoff —
   refuse the whole continuation, or continue the rest and report?
   Refusing wholesale is safer; partial continuation silently changes
   the topology under test.
8. Is a continuation resumable a second time (Paper → paused → Paper),
   and if so does it re-anchor again?

---

## 4. Emitter tracking as a standing standard (requirement 7)

> "Must have all emitters tracked to help isolate issues. This will be
> standard going forward."

This is the broadest requirement in the list — it applies to the whole
platform, not to Paper.

**Already built:** `src/core/emit_contracts.py` (v3.24.30) declares the
expected payload shape per bus topic and validates what actually
appears. It catches three silent failure classes: never-emitted,
missing/renamed field, bad value.

It exists because of a real incident: a consumer read `data["action"]`
while the bus writes `data["type"]`, and **665 trades flowed past a
verifier that recorded zero** with no exception raised. A key-name
mismatch is invisible to both sides — the producer emits fine, the
consumer reads fine and gets `None`.

On its first run against Nuclear Mode it found a live data-integrity
defect: `scrumming_bot.py:8568` emitted `size` (USD) and no `amount`, so
`LogManager` wrote **every hedge rebalance to the live trade.log with
`amount=0.0`**.

**What "standard going forward" requires beyond today:**

1. Contracts declared for every topic, not the four currently covered
   (`trade.filled`, `bot.gate_decision`, `pnl.event`, `ta.voting`).
   Observed but undeclared so far: `bot.log`,
   `bot.voting_panel_snapshot`.
2. The observer attached on the **live** path, not only in Nuclear.
   It is observation-only and never raises into the producer.
3. A declared-but-never-emitted topic treated as a finding, since that
   is the class that hid `SimStatStrip.set()`, `compare_trades()`,
   `SystemLoadOscillator` and `register_sim_run()` — each of which
   passed its tests without ever running.
4. Paper's own emitters declared at build time rather than retrofitted.

---

## 5. Open questions for when the gate opens

Recorded now so they are not rediscovered mid-build:

1. **Paper fill model.** Requirement 2 says real market data with paper
   execution. Does a paper order fill at the touch, cross the spread, or
   model queue position? The Simulator's `FleetSimExchange` fills a LIMIT
   order when the candle sweeps its price — realistic for backtest,
   optimistic for a live-data paper tab.
2. **Paper fees.** The Simulator charged zero until v3.24.32. Paper
   should charge from `BotConfig.trading_fee_pct` from day one.
3. **One paper tab per exchange** (per the 2026-05-19 decision) or one
   tab with an exchange selector? The Trading tab's structure decides
   this if requirement 1 is taken literally.
4. **Paper state isolation.** Paper must not reach `~/.acervator`
   bot_state, the capital-reservation singleton, or the live event bus.
   The injection pattern from v3.24.31 (private registry, private bus,
   `sim_mode`) is the precedent to reuse.
5. **Promotion mechanics.** What does "Simulator pushes to Paper"
   concretely move — a topology proposal, a tuned config, or both? And
   what records that a promotion happened?

---

## 6. Falsification

This document is wrong if: a Paper Trader source file is found (searched
159 archives and the tree, none exists); or the 2026-05-19 design doc
contradicts requirement 1 (checked — it agrees); or `emit_contracts.py`
turns out to be reachable from the live path already (it is not — its
only consumer is `nuclear_fleet_controller.py`).
