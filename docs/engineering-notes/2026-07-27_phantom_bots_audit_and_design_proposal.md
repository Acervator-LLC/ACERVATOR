# Phantom Bots — Audit + LTM findings + Design Proposal

Date: 2026-07-27. Version at audit: v3.23.38.

Deliverable this pass:
- Audits of the two Bot Details tabs (`Phantom State`, `Phantom Bot`).
- LTM + repo-scan findings on phantom implementation status.
- Design proposal covering: TA-layer boost/suppress into
  Indicator Voting Panel, HTF weighting, active-only lifecycle,
  API-load monitoring + adaptive cap, and default-off in wizard.
- Punch-list of concrete pieces to ship in this cascade
  (structural merge + wizard default + audit-surfaced fixes)
  vs pieces to hold behind operator alignment (TA-layer wiring).

---

## Part 1 — Audit of the two Phantom tabs

### 1.1  Phantom State (`bot_live_settings.py:1863-2060`)

Read-only per-bot runtime view. Three sections:

| Section | Data source |
|---|---|
| Phantom Coordinator Status | `_phantoms_enabled`, `_phantoms_started`, `_phantom_timeframes`, `_phantom_locked`, `_phantom_lock_timeframe` on the bot |
| Per-Phantom State table | `_phantom_mgr.get_phantoms(bot_id)` → per-phantom `.get_status()` (TF, state, target balance, trade count, exchange-FIFO P&L, bullish/bearish counts, confidence) |
| Active Locks table | `_coordinator.get_active_locks()` |

Empty-state message chain (disabled / enabled-but-not-started /
started-but-no-summary-yet) is factual and not hallucinatory.

**Audit verdicts**

- F51 — All 20+ runtime attributes reached exist on `ScrummingBot`
  or the shared coordinator/manager. No dead reads.
- F52 — Live P/L cell correctly sources
  `realized_pnl_exchange` (per v3.23.7 Anomaly B fix) rather than
  the internal accumulator. Kept.
- F53 — Empty-state text mentions "Toggle 'Enable Phantoms' in the
  Phantom Bot tab" — accurate cross-tab pointer, will break when
  the two tabs merge. Fix during merge.

### 1.2  Phantom Bot (`bot_live_settings.py:3088-3198`)

Editable per-bot config surface — mirrors the wizard's
`PhantomConfigPage`. Three sections:

| Section | Widget → config field |
|---|---|
| Enable Phantom Balance Bots | `_phantom_enable` → `enable_phantoms` |
| Active Timeframes | `_phantom_tf_checks` (11 checkboxes, filtered by exchange support) → `phantom_timeframes` |
| Higher-TF Lock Duration | `_phantom_lock` → `lock_candle_count` |
| Live Status | read-only echo of `bot.get_phantom_statuses()` |

**Audit verdicts**

- F54 — Timeframe checkboxes correctly filter to exchange support via
  `available_timeframes(exchange_id)`. Confirmed against
  `src/exchange/timeframes.py`.
- F55 — Lock-duration control writes to
  `coordinator.lock_candle_count` (`scrumming_bot.py:1881`). Verified.
- F56 — The “Live Status” section duplicates most of the Phantom
  State summary information (state per TF, started flag).
  **Merge target.**

### 1.3  Merge candidate structure

Sensible one-tab layout post-merge (all sections are already
scrumming-only, so the merge is symmetric):

1. **Enable + Config** (from Phantom Bot): enable toggle, TF
   checkboxes, lock duration.
2. **Coordinator Status** (from Phantom State summary): enabled /
   started / TF list / SCRUM lock state.
3. **Per-Phantom State** (from Phantom State table): the 7-column
   table.
4. **Active Locks** (from Phantom State): cross-bot lock table
   when any lock is held.

Empty-state text can drop the cross-tab pointer since everything
lives here now.

---

## Part 2 — LTM + repo-scan findings on phantom implementation status

### 2.1  Memory hits

- `user_operator.md` — “Phantom Balance” is in the operator’s
  production vocabulary; treat any operator claim about phantoms
  as ground truth.
- `project_acervator_state.md line 19` (P2, **still pending**):
  > MEM-259 pending: `src/trading/phantom_balance.py` +
  > `src/trading/volume_guard.py` scope that shipped ambient
  > with 3.15.39. Reconstruct from current state; document;
  > decide if further bump warranted.

  The phantom subsystem landed **without a proper scope
  document** — corroborates the operator's suspicion that it is
  not fully wired.
- `feedback_no_bridges_sim_live.md line 12` — the sim path
  explicitly forces `enable_phantoms=False`, another marker that
  phantoms have unresolved coupling.

### 2.2  Repo-scan findings

#### F57 — Phantom higher-TF bias is wired but used only as a **binary SCRUM gate**, not as a boost/suppress signal fed into the Indicator Voting Panel.

`phantom_balance.py:422` defines `TimeframeCoordinator.get_higher_tf_bias(parent_bot_id, base_timeframe, min_confidence=0.30)` — returns a `(SignalDirection, detail)` tuple with **linear rank-weighted** bull/bear scoring. Wiring:

```python
# scrumming_bot.py:6192
_htf_bias_dir, _htf_bias_detail = (
    self._coordinator.get_higher_tf_bias(
        self.bot_id, self.config.ta_timeframe or '1h'))
…
# scrumming_bot.py:6204
_htf_blocks_scrum = (_htf_bias_dir == SignalDirection.BULLISH)
```

Consumers of `_htf_blocks_scrum`: gate on autonomous scrum. Nothing
else. `_htf_bias_detail` (the rich bull/bear weight breakdown, list
of contributing phantom TFs) is discarded on the same line.

#### F58 — `get_multi_tf_summary` exists but is **not** the source of Indicator Voting Panel rows.

`phantom_balance.py:502` defines `get_multi_tf_summary(parent_bot_id)`. `indicator_panel.py:347` documents that `IndicatorVotingPanel.update_data()` "receives the dict returned by `TimeframeCoordinator.get_multi_tf_summary()`". **This is aspirational.** The actual caller at `main_window.py:4404-4431` builds a SINGLE-row dict from the parent bot's own `_last_summary` and passes `{tf: tf_data}` — no phantom rows.

Consequence: the operator opens the panel and sees only their own bot's TF, never the D/W/M phantoms even when phantoms are running.

#### F59 — When phantoms are disabled live, they DO stop.

`scrumming_bot.py:1842-1851` — `update_phantom_config(enable_phantoms=False)` calls `_phantom_mgr.stop_all(bot_id)` and toggles `_phantoms_started=False`. Individual `PhantomBalanceBot` instances have their own halt path. Verified.

Gap: at bot-creation the wizard defaults `enable_phantoms=True` with 6 timeframes (`5m, 15m, 30m, 1h, 4h, 1d`) — see `bot_wizard.py:1625-1636`. This is the “several active” state the operator is seeing.

#### F60 — Per-exchange API load telemetry already exists.

`src/exchange/api_logger.py:27` — `APIInteractionLog` records every call: exchange, action, endpoint, params, result, latency (`elapsed_ms`), level. `get_recent(count)` and `get_for_exchange(exchange, count)` return recent slices; the class also supports listener callbacks. This is an unused-in-GUI-form substrate perfectly suited to a **per-exchange rolling calls-per-minute meter** — no new instrumentation needed to build the monitor.

#### F61 — Rate-limit primitive lives on the connector.

`ccxt_connector.py:238` — `_min_request_interval: float = 0.1` (100 ms → ~10 rps ceiling per connector). All calls route through `_call_sync` which serialises against this. Additional load control can be applied on top by:
- Reading the last-minute call count from `APIInteractionLog`.
- Adjusting `_min_request_interval` upward when headroom is thin.
- Refusing new phantom-set creation past a configurable threshold.

---

## Part 3 — Design proposal

### 3.1  Merged Phantom Bots tab (structural, no logic change)

Single scrumming-only tab in Bot Details replacing both Phantom State
and Phantom Bot. Sections stack in the order given in 1.3. Existing
runtime attributes / methods are all preserved; only the widget
container changes. **Low-risk, ships this cascade.**

### 3.2  Wizard default: phantoms OFF by default

Flip `bot_wizard.py:1625` `self._enable.setChecked(True)` → `False`.
Reset default TFs to an empty set so operator has to opt in explicitly.
Existing bots and their `bot_state.json` are unaffected — the default
only matters at NEW-bot creation time. **Low-risk, ships this cascade.**

### 3.3  API-load monitor + adaptive cap (new subsystem)

**Runtime**: new `src/exchange/api_load_monitor.py` — a periodic
sampler that reads `APIInteractionLog.get_recent(N)` per exchange,
computes calls-per-minute + P95 latency, and exposes:

- `load_score(exchange_id) -> float` in `[0, 1]` (0 = idle, 1 = at
  connector's rate ceiling).
- `should_allow_new_phantom_set(exchange_id, estimated_tf_count) ->
  (bool, str)` — returns (allow, reason). Refuses when adding N new
  phantoms would push CPM past a configurable safety threshold
  (default: 75 % of connector ceiling over trailing 60 s).

**GUI hook**: Bot wizard's Phantom section reads
`should_allow_new_phantom_set(exchange_id, n_tfs)` at commit time.
If refused, popup with the reason and the current load score. Operator
can still force-enable but the warning has been shown.

**GUI display**: a compact “Exchange load: 42 / 600 CPM” pill in the
main-window status bar, colour-coded green / amber / red at 50 % / 75 %
thresholds. Reads the same `load_score`. **Shippable in a follow-up cascade after design approval.**

### 3.4  Phantom → Indicator Voting Panel wiring (TA-layer boost/suppress)

**End state**: each phantom's per-tick TA summary appears as an
additional row in the panel table, above or below the parent's row.
The **Net** and **Conf** columns for the parent bot's row become a
weighted composite (parent's own TA + all higher-TF phantoms with
`confidence >= min_confidence`, per the rank-weighted formula already
in `get_higher_tf_bias`).

**Data flow**:

1. Dashboard tick (`main_window.py:4402-4431`) currently packages the
   parent bot's `_last_summary` into a single-row dict.
2. New: also call `bot.get_multi_tf_summary()` (already exists at
   `scrumming_bot.py:10325`), merge its per-TF rows into the dict, and
   pass the union to `IndicatorVotingPanel.update_data()`.
3. `IndicatorVotingPanel` already supports multi-TF rows in its
   `INDICATOR_COLS` structure (no panel-side changes needed — matches
   the operator's directive).
4. Net-row computation: extend the panel's own aggregation to compute
   a weighted-net when multiple TF rows are present, using linear
   `tf_rank` weighting (same formula as `get_higher_tf_bias`).

**Boost / suppress semantics**:

- If higher-TF phantoms lean bullish → the parent's Net cell reads
  slightly more bullish than it would from parent-only voting (=
  boost).
- If higher-TF phantoms lean bearish → the parent's Net cell reads
  slightly less bullish (= suppress).
- Both directions are visible: raw parent Net + composite Net in
  adjacent cells (or one cell with a delta annotation).

**Active-only lifecycle**: when phantoms are disabled or stopped, the
merged rows disappear and the composite Net falls back to the raw
parent Net. `_phantom_mgr.get_phantoms(bot_id)` returns [] when
disabled, so `get_multi_tf_summary` naturally returns an empty set.

**HTF weighting research answer**: use the existing rank scheme —
`1m`→1, `5m`→2, `15m`→3, `30m`→4, `1h`→5, `2h`→6, `4h`→7, `6h`→8,
`12h`→9, `1d`→10, `1w`→11 (per `phantom_balance.py:82` `tf_rank`).
Weight per row = `rank × consensus_confidence` — linear because
tests in the phantom-battery historically balanced against
exponential (log growth added noise; linear preserved parent's TF
prominence). Kept as the default until an A/B says otherwise.

**Shippable in a follow-up cascade after design approval.**

### 3.5  Active-only lifecycle hardening

Already ~95 % correct:
- Live disable → `_phantom_mgr.stop_all` runs.
- New bots at creation → after we flip wizard default, no phantoms
  spawn.
- Existing bots with saved `enable_phantoms=True` → keep behavior
  (no forced migration).

Small hardening opportunity: `_phantom_mgr.stop_all` currently sets
`_phantoms_started=False` but doesn't `remove_set`. That means the
manager still holds phantom instances (memory + reference to
coordinator). Cleaner: full teardown on disable. Non-critical.

---

## Part 4 — Punch list for this cascade

**Ship now (low-risk, straightforward)**:

- **T1** — Merge Phantom State into Phantom Bots as a single tab
  (per § 3.1). Retire `_create_phantom_state_tab`; rename remaining
  method to `_create_phantom_bots_tab`. Update Tab 6/7 registrations.
  Refresh empty-state text to drop the cross-tab pointer.
- **T2** — Flip wizard default `enable_phantoms` → `False` and clear
  default TF checkbox set (per § 3.2).
- **T3** — Fix F53 empty-state text (`Toggle 'Enable Phantoms' in the
  Phantom Bot tab` → `Toggle 'Enable Phantoms' above`).

**Hold for operator alignment**:

- **T4** (§ 3.3) — Build `api_load_monitor.py` + wizard warning gate +
  main-window load pill. Additive; needs operator OK on thresholds
  and where the pill lives.
- **T5** (§ 3.4) — Wire phantom summaries into
  `IndicatorVotingPanel.update_data()` (merge parent's `_last_summary`
  with `bot.get_multi_tf_summary()` at
  `main_window.py:4402-4431`). Additive on the caller side; panel
  code untouched per operator directive. Needs operator OK on the
  composite-Net rendering (single cell with delta vs adjacent cells).

**Operator decisions requested** (each one-liner):

1. § 3.3 default CPM threshold — 75 % of connector ceiling okay?
2. § 3.4 rendering — composite Net in a new column, or replace the
   parent's Net cell in-place with a hover-explainer for the delta?
3. Should the wizard force-remove any pre-existing bot's
   `enable_phantoms=True` on next launch, or leave existing bots
   as-is (default only affects NEW bots)?
