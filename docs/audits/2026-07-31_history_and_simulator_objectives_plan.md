# History Tab + Simulator objectives — cascade plan

Reference specification (Diataxis: reference). Cascade planning for
the ten-item operator directive received 2026-07-31 covering the
History tab (5 items) and Simulator tab (5 items). Version at write:
v3.23.70. Author: Claude Opus 4.7. Reviewer: operator (Ekthelius).

## 1  Prior-context reconciliation

Two prior facts from long-term memory must be reconciled with today's
directive before any code lands.

### 1.1  Sim-boundary rule — architecturally SUPERSEDED

Memory `feedback-no-bridges-sim-live` (2026-06-13) codified: sim
does not import from `src.trading.*`; sim files live in
`sadp/RAIntSimBat/`; sanctioned reader at
`sadp/_tools/live_log_reader.py`.

**Current reality (verified 2026-07-31)**:
- `sadp/` directory no longer exists (removed in the archive cascade
  from tasks 33–36 above).
- `sadp/_tools/live_log_reader.py` no longer exists. Replaced by
  `src/trading/live_log_reader.py` (equivalent function, in-tree).
- `tools/check_sim_live_boundary.py` no longer exists.
- Current sim engine at `src/gui/simulator_tab/` **directly imports**
  `ScrummingBot`, `BotContainer`, `BotConfig`, `BotMode`,
  `EventBus` (see `nuclear_controller.py:34-36`).

The old boundary rule assumed a wrapper anti-pattern that broke
parity. The current architecture goes the opposite direction: sim
runs the same class code as live, but against a `NuclearSimExchange`
instead of a real exchange. That IS the parity guarantee — same code
path, different exchange fake.

**Applied consequence**: this plan does not fork any bot code. The
sim engine that already exists is the substrate. If it is broken
today, we fix the exchange fake + orchestration, not the bot classes.

### 1.2  gate.log stall from 2026-06-11 — RE-VERIFY

Memory `project-live-gate-log-stalled` says gate.log writer stopped
2026-06-11T05:29Z; the sim-side workaround was to glob rotated
files. Memory is 47 days old. Before proceeding with History Tab
items #2 and #5 (which read from gate.log), I will:

1. Check `~/.acervator_logs/trade/gate.log` mtime.
2. If still stale, the writer stall is a live-side P0 that must
   land before History Tab items #2/#3 mean anything.
3. If not stale, memory can be updated and the item proceeds.

Cannot verify from the codebase alone — needs the operator's live
machine state, or I can add a diagnostic that logs the last-seen
gate.log entry timestamp on app start (v3.23.71 lightweight probe).

## 2  Item-by-item mapping

### History Tab

| # | Item | Risk | Prior context | Depends on |
|---|------|------|---------------|------------|
| H1 | Default start date = 4/1/2026 | LOW  | `history_tab.py:310` sets `From:` to `now - 30d`. One-line change. | none |
| H2 | Gate column → Gates plural + per-gate mouseover explaining state at trade time | MEDIUM | Gate state is captured in `gate.log` v3.23.0 schema (`data.scrum_armed / fold_armed / scrum_blockers / fold_blockers / scrum_fixture / fold_fixture / indicators / state`). The reader `live_gate_decisions()` already yields all of this. History Tab renders only a compressed `S`/`F` marker string. | 1.2 gate.log liveness |
| H3 | Grade + Gates + Voting column mouseovers; Voting expanded to show individual indicator states; upgrade capture if not present | HIGH | Voting is captured in `voting.log` per-fired-trade with a full `VotingSummary` snapshot including `signals: list[Signal]` — each Signal carries `direction`, `confidence`, `timeframe`, indicator name. **Per-indicator state IS captured** — the Voting column just doesn't surface it. Grade tooltip has zero capture cost (already computed on-demand). | none |
| H4 | History Refresh front-loads Simulator with YTD data | HIGH | Requires the Simulator to accept a fixture feed. Sim engine has `NuclearCandleSource` (tape-based) — needs new "live-trade replay" surface. | S1, S2 |
| H5 | Fewer trades in History than boot-up YTD pull | HIGH | Suspects: (a) `_apply_filters` silently dropping rows; (b) exchange trade-fetch pagination cap (RAVE bug pattern we already fixed); (c) `_all_trades` de-dup collision. Needs targeted diagnostic. | needs cold read |

### Simulator Tab

| # | Item | Risk | Prior context | Depends on |
|---|------|------|---------------|------------|
| S1 | Load isolated sim of all live bots via YTD + bot_state | XHIGH | Requires: (a) new "fleet replay" mode alongside Basic/Nuclear; (b) `bot_state.json` reader-and-instantiator; (c) YTD-tick source (comes from H4). "Sim engine broken" operator statement — need to identify what specifically is broken first. | S6 diagnosis |
| S2 | Run front-loaded YTD + simulated bots against it | XHIGH | Presupposes S1 exists + the exchange fake can drive real ScrummingBot.tick() through historical ticks. Nuclear Mode already does this for a single bot on synthetic tapes; S2 extends to multi-bot on real YTD. | S1 |
| S3 | Verify trading-gate logic + behavior identical | HIGH | With the SUPERSEDED sim-boundary (see 1.1), gate logic is literally the same class code — parity is a property of the exchange fake, not the bot. Test: feed the same tick sequence to sim and diff `gate.log` outputs. | S1, S2 |
| S4 | Finalize sim-to-real baseline for developing Acervator strategies + testing features pre-implementation | HIGH | Follows S3. Once parity is proven, the sim is the strategy-dev harness. This is a discipline change, not a code delivery — codified in a doc + a test template. | S3 |
| S5 | Nuclear Mode = brutally tests ALL platform features for stability and reliability. **It does NOT backtest anything.** | XHIGH | Two sub-goals: (a) speed cycling of current features (already the design intent — see `nuclear_mode_panel.py` header comment); (b) backtest topology proposals from v3.23.67 — a topology can spawn its bots + wires into the sim and run the fixture against them. | S1, S2, plus v3.23.67 topology_proposals |

> **S5 CORRECTED 2026-08-08 by operator directive.** The original line read
> "brutal speed-cycling test bed + backtests Market Inspector topology
> proposals". Operator: *"Nuclear brutally tests all platform features for
> stability and reliability. It does not back test anything since this is done
> with the standard Simulator mode. I said this."*
>
> This changes what S5's evidence must be. NOT outcome signals — accumulation,
> dispersion, robustness verdicts; those are Simulator-side (S1-S4) and are what
> `src/trading/topology_stress.py` computes, which is why nothing in Nuclear
> calls it. S5's evidence is COVERAGE AND SURVIVAL: which features were
> exercised, exception counts, throughput under rising load, data integrity,
> and resource growth across loops.
>
> Consistent with the operator's other statements: Nuclear "attempts to abuse
> all aspects of the application", and its trades "are not for validation
> against YTD data… they are meant to exercise the system brutally AFTER it has
> been proven accurate". Nuclear is downstream of parity and never measures it.
>
> **S6 note:** the blocking question below ("sim engine completely broken") is
> STALE as of 2026-08-08. The sim demonstrably runs — 81 run directories,
> 10,046 trade records, 10,046 gate records on disk. S6 should be re-scoped
> from "what is broken" to ongoing engine-health signals.

### Sim engine health (implicit item S6)

Before S1-S5 can proceed, I need the operator's diagnostic on "sim
engine completely broken" — one of:

- Does the Simulator tab fail to open?
- Does Nuclear Mode Start button raise?
- Do sim bots create but never trade?
- Does the exchange fake violate an invariant?

Any one of those has a different root cause. Without it, S1-S5
cannot be sequenced.

## 3  Proposed cascade sequence

Grouped for independence + reversibility. Each cascade ships a green
zip.

- **v3.23.71 — History Tab low-risk polish + gate.log liveness probe**
  - H1: default From = 2026-04-01
  - H3 (partial): Grade + Gates + Voting cell tooltips (no capture
    upgrade — surface what is already in `voting.log`)
  - New diagnostic: on app start, log `gate.log` last-entry timestamp
    to `system.log` so we can verify §1.2 without pestering the
    operator. Also log `voting.log` liveness.
  - Pin tests: tooltip content presence for the three columns.

- **v3.23.72 — History Tab #5 diagnosis + fix**
  - Cold-read `history_tab._fetch_and_render`, `_apply_filters`,
    the boot-YTD pull path in `main.py` / `bot_manager`, and the
    trade-fetch pagination.
  - Emit a comparison log line at each dedupe/filter checkpoint so
    the reduction is quantifiable at run time.
  - Ship fix + pin tests once root cause is confirmed.

- **v3.23.73 — History Tab #2 full + #3 full (blocked on gate.log liveness)**
  - Split `Gate` column into a `Gates` group: for each rule in the
    v3.23.0 schema, one narrow cell showing state (✓ armed / ✗
    blocked with reason on hover). If gate.log is stale, this
    cascade waits.
  - Voting column: expand into per-indicator badges with tooltip
    showing indicator name + confidence + timeframe.
  - Capture upgrade only if the join reveals a missing indicator
    field the panel expects.

- **v3.23.74 — Sim engine diagnosis + repair (S6)**
  - Instrument sim tab boot to log every stage.
  - Ship fix for whatever the "completely broken" symptom is once
    the operator's diagnostic pin arrives.
  - Green suite required before any of S1-S5 lands.

- **v3.23.75 — Sim S1 + H4 first half**
  - New "Fleet Replay" mode alongside Basic + Nuclear.
  - `bot_state.json` reader → instantiate each live bot as a sim
    ScrummingBot instance against a shared `NuclearSimExchange`
    (or a new `YtdReplaySimExchange`).
  - History Tab Refresh emits a "YTD trades ready" event carrying
    the trade list; sim listens.

- **v3.23.76 — Sim S2 + S3**
  - Fleet Replay Start button plays the YTD trade sequence through
    the sim exchange, driving each sim bot's tick().
  - Parity harness: after sim runs, compare sim's `gate.log` output
    to live's `gate.log` for the same time window. Diff report in
    the Simulator's Performance Log.
  - Pin tests: identical trade set → identical gate decisions.

- **v3.23.77 — Sim S4 discipline doc + S5**
  - Doc: `docs/audits/2026-08-XX_sim_first_strategy_dev_discipline.md`
    codifies the "sim before live" workflow now that parity is
    proven.
  - Nuclear Mode: extend `NuclearController` to accept a
    `TopologyProposal` object as fixture source instead of a tape;
    the controller spins up the proposal's bots + wires and runs
    the fixture.

## 4  Open questions

1. **H1 date grounding**: is `4/1/2026` the fixed launch date for
   all bots, or a placeholder that should update when a later
   launch happens? Suggest: keep as fixed literal until operator
   changes it (settings.toml override).
2. **H2/H3 gate.log liveness**: proceed with the v3.23.71 diagnostic
   probe first, then decide whether H2/H3 need a live-side gate.log
   fix before proceeding.
3. **H5 diagnostic**: is the discrepancy operator has observed
   (fewer trades in History than YTD pull) reproducible on demand,
   or intermittent? Reproducibility affects whether a diagnostic
   log or a full cold-read audit is the faster path.
4. **S6 sim symptom**: what is the concrete failure? App tab crash?
   Start button no-op? Bots create but silent? Please pin one.
5. **S1 scope**: does "all live bots" include Extractors, or just
   ScrummingBots? Extractor sim is a separate class; if included
   scope roughly doubles.
6. **S5 topology backtest cadence**: how many minutes of YTD data
   fed at nuclear speed per proposal? Suggest 30 days at
   compressed 100x (~7.2 h wall-clock).

## 5  Sign-off gate

Cascades v3.23.71-77 proceed when:

1. Operator answers the six open questions in § 4.
2. Operator confirms the cascade order in § 3 (any reorder or
   drop-item is fine — this plan is a proposal).
3. Each cascade passes `gui_archetype` +
   `check_release_readiness.py` before its version bumps.

Fastest path to visible progress: **v3.23.71 lands today** without
any sign-off gate (all three sub-items — H1 date, H3 tooltips,
gate.log probe — are non-invasive polish + observability). The rest
wait on § 4 answers.

## 6  Reference: log schemas involved

For quick reference during implementation.

- **`~/.acervator_logs/trade/gate.log`** (NDJSON, one entry per gate
  evaluation):
  ```
  { "timestamp": ISO8601, "category": "gate.decision",
    "bot_id": str, "data": {
      "symbol": str, "scrum_armed": bool, "fold_armed": bool,
      "scrum_blockers": [str, ...], "fold_blockers": [str, ...],
      "scrum_fixture": {...}, "fold_fixture": {...},
      "indicators": {...}, "state": str,
      "evaluated_at_tick": int
  }}
  ```
- **`~/.acervator_logs/trade/voting.log`** (NDJSON, one entry per
  fired trade):
  ```
  { "timestamp": ISO8601, "category": "voting.panel.snapshot",
    "bot_id": str, "data": {
      "panel": {  // full VotingSummary asdict()
        "bullish_count": int, "bearish_count": int,
        "net_score": float, "consensus_confidence": float,
        "signals": [ { "direction": int, "confidence": float,
                       "timeframe": str, "weight": float,
                       "indicator": str }, ... ],
        "timeframe": str
  }}}
  ```
- **`~/.acervator_logs/trade/trade.log`** (NDJSON, one entry per
  outcome):
  ```
  { "timestamp": ISO8601, "category": "trade.executed",
    "bot_id": str, "data": {
      "action": str, "symbol": str, "side": str,
      "amount": float, "price": float, "status": str,
      "usd": float, "operator_initiated": bool
  }}
  ```

Consumer: `src.trading.live_log_reader.live_gate_decisions()`,
`.live_voting_panel_snapshots()`, `.live_trades()`. All three iterate
the active `<name>.log` and rotated `<name>.log.1..5`.
