# Simulator Tab + Nuclear — implemented emitter census

**2026-08-08.** Every emitter that exists today in `src/gui/simulator_tab/**`.
Call sites enumerated by **AST** (not text search — comments mentioning a symbol
do not count as uses). Frequencies and examples taken from the **81 real run
directories** under `~/.acervator_logs/sim/runs/`, read-only.

Scope is the Simulator Tab and Nuclear only, per operator directive.

---

## 1. Summary

**54 emitter call sites** across the tab, in four kinds:

| Kind | Call sites | Reaches disk? | Machine-readable? |
|---|---:|---|---|
| `callback._activity` | 35 | no — GUI pane + logger | **no** (free prose) |
| `callback._perf` | 8 | no — GUI pane + logger | **no** (free prose) |
| `SimRunLog.record_gate` | 3 | **yes** — `gates.log` | yes (JSONL) |
| `bus.emit` | 3 | no — in-process only | partial |
| `SimRunLog.start_run` | 2 | **yes** — `meta.json` | yes |
| `SimRunLog.finish_run` | 2 | **yes** — `meta.json` | yes |
| `SimRunLog.record_trade` | 1 | **yes** — `trades.log` | yes (JSONL) |

**43 of 54 sites (80%) are free-text callbacks** that reach a GUI pane and a
logger and are never persisted in machine-readable form. They cannot be
queried, counted, or verified after a run.

---

## 2. Persisted emitters — the only ones an audit can read

### 2.1 `trade.executed`

| | |
|---|---|
| **Emitter** | `SimRunLog.record_trade` |
| **Location** | `fleet/fleet_replay_controller.py:1050` (sole call site) |
| **Producer chain** | `FleetSimExchange._settle_fill` → `on_trade` → `_on_sim_trade` |
| **Sink** | `~/.acervator_logs/sim/runs/<run_id>/trades.log` (JSONL, append-only) |
| **Frequency** | one per settled fill. **10,046 records across 81 runs.** |
| **Buffering** | flushed every 200 rows, plus on `finish_run` |

```json
{
 "timestamp": "2026-04-01T01:00:00+00:00",
 "category": "trade.executed",
 "origin": "sim",
 "run_id": "20260803T154437_d74f3b",
 "bot_id": "",
 "candle_address": "",
 "data": {
  "action": "", "symbol": "CHIP/USD", "side": "BUY",
  "amount": 4165.972337943676, "price": 0.06001,
  "status": "filled", "usd": 250.00000000000003,
  "operator_initiated": false
 }
}
```

**Field integrity, measured across all 81 runs:**

| Field | Populated | Note |
|---|---|---|
| `timestamp` | 100% | master-clock time, not wall clock — correct |
| `symbol` / `side` / `amount` / `price` | 100% | real per-symbol values |
| `bot_id` | **0%** on historic runs | fixed 2026-08-08 (`09fa4a8`), **unproven on a fresh run** |
| `candle_address` | 0% historic, varies on recent | populated on 2026-08-08 runs |
| `data.action` | **0%** | the `action`-vs-`type` mismatch `emit_contracts.py` was written to catch; fixed same commit, unproven |

### 2.2 `gate.decision`

| | |
|---|---|
| **Emitter** | `SimRunLog.record_gate` |
| **Location** | `nuclear_fleet_controller.py:1027`, `:1060`, `:1073` |
| **Producer** | subscribes to exactly one topic, `bot.gate_decision`, on each bot's PRIVATE bus |
| **Sink** | `~/.acervator_logs/sim/runs/<run_id>/gates.log` (JSONL, append-only) |
| **Frequency** | one per gate evaluation. **10,046 records across 81 runs.** |

```json
{
 "timestamp": "2026-08-03T15:45:04.966712+00:00",
 "category": "gate.decision",
 "origin": "sim",
 "run_id": "20260803T154437_d74f3b",
 "bot_id": "cd437493",
 "candle_address": "",
 "data": {
  "symbol": "CHIP/USD",
  "scrum_armed": false, "fold_armed": false,
  "scrum_blockers": ["pre-tick"], "fold_blockers": ["pre-tick"],
  "scrum_fixture": null, "fold_fixture": null
 }
}
```

**Field integrity:**

| Field | Populated | Note |
|---|---|---|
| `bot_id` | **100%** (10,046/10,046) | and on 2026-08-08 runs the 35 distinct ids all exist in `bot_state`; pre-08-08 runs are uuid4 with **0% match** |
| `timestamp` | 100% | **WALL CLOCK, not master clock** — inconsistent with `trade.executed` |
| `scrum_blockers` | 100% | carries computed values, e.g. `bb_pos=0.44`, `dir=BEARISH` |
| `candle_address` | **0%** | no gate decision can be located to a candle |

**Note the asymmetry:** trades carry a candle address but no bot; gates carry a
bot but no candle address. Neither log joins to the other, so
"which bot decided what at which candle" is unanswerable from the artifacts.

### 2.3 `meta.json`

| | |
|---|---|
| **Emitters** | `SimRunLog.start_run` (`fleet_replay_controller.py:490`, `nuclear_fleet_controller.py:1008`), `finish_run` (`:1311`, `:1041`) |
| **Frequency** | one per run. 81 files. |
| **Keys** | `schema_version`, `run_id`, `origin`, `started_at`, `config{bots, symbols, total_candles, max_candles, anchored, full_evaluation, anchor_candles}` |

**`config` is a declaration of intent, not a record of work.**
`full_evaluation: true` states what the run was configured to do. It is not
evidence any of it happened, and treating it as such is how the per-candle-TA
claim survived.

---

## 3. Non-persisted emitters

### 3.1 `_activity` — 35 sites

Free prose to the GUI Activity pane and a logger. Examples in-tree:

```
"cycle wiring: injected 5 of 5 Market Inspector proposal wire(s) across
 35 bot(s), on top of the fleet's own bot_state topology."
"Wallet seed: $3,300.00 across 2 quote currencies (USD $2,850.00,
 USDC $450.00); spendable starts equal to locked."
```

Human-readable, machine-opaque. Not counted, not queried, not verified.
**This is where most of what the simulator "knows" goes to die.**

### 3.2 `_perf` — 8 sites

Same shape, to the Performance pane:

```
"Nuclear cycle 1: 3,000 candles · 627 trades · 0 exceptions ·
 32.0 c/s · load 1.11x (1 fleet)"
```

Contains real numbers in a string. Extracting them requires parsing prose.

### 3.3 `bus.emit` — 3 sites

All in `fleet_replay_panel.py` (`:433`, `:1132`, `:1549`), all dynamic topics.
In-process only, never persisted.

---

## 4. What has NO emitter at all

These are the gaps that make a directive **unverifiable** rather than merely
unmet. A claim about any of them cannot be checked against any artifact.

| Missing signal | Consequence |
|---|---|
| **TA computed** | Nothing counts TA invocations. `ReplayProgress` has 15 fields, none TA; `meta.json` has 14 keys, none TA. `bots_ticked` counts tick ENTRIES, so the ~91% that return early at `scrumming_bot.py:5046` are indistinguishable from the ~5% that compute. **This is why "per-candle TA ran" could not be falsified.** |
| **Per-indicator invocation** | No record of which of the 12 indicators ran |
| **TA input window** | Not recorded, so no value can be independently recomputed |
| **Tablet reads** | No per-symbol read counter |
| **Tablet integrity** | No before/after hash |
| **Loop count** | Cycles are counted; passes over a tablet are not |
| **Fold / tranche EXECUTION** | Only arming is visible (42 `fold_armed=True` observed) |
| **Wire income credited** | No record that value moved along a wire |
| **Data loss under load** | No emitted-vs-recorded reconciliation |

`ta.voting` (`scrumming_bot.py:6503`) does emit per-tick — onto the bot's
**private** bus, with no persisting subscriber. The richest payload,
`bot.voting_panel_snapshot` (`:4821`, the full per-indicator `VotingSummary`),
fires only at trade-fire and has **zero sim subscribers**.

---

## 5. Against the standardized format

Operator's requirement: every emitter produces "name, location, expected
result, actual result".

| | `trade.executed` | `gate.decision` | `_activity` / `_perf` |
|---|---|---|---|
| name | ✅ `category` | ✅ `category` | ❌ |
| location | ❌ | ❌ | ❌ |
| expected | ❌ | ❌ | ❌ |
| actual | ✅ `data` | ✅ `data` | prose only |

**No existing emitter carries a declared expectation, and none carries its
location.** The two persisted streams have half the required shape; the other
43 sites have none of it.

`src/core/signal_contract.py` (new, 26 pins passing) provides the full record.
Nothing in the tab emits through it yet.

---

## 6. How each emitter was implemented, against the design proposals

Operator's request: explain each on the basis of the Simulator and Nuclear Mode
design proposals, per the workflow.

**The short answer, and it explains the entire census: none of them were built
against those directives.** Every persisted emitter was built to solve a
*contamination and disappearance* problem. The provenance is stated in-tree.

### The stated basis, quoted from source

`sim_run_log.py` header:

> Operator directive 2026-08-02, after v3.24.12 isolated the sim's event bus:
> *"Yes, let's implement the persistent log before I build and test."*
>
> v3.24.12 gave sim bots a private EventBus so their fills stop landing in the
> live `trade.log` (136 rows of measured contamination). That fixed the
> pollution but **left the sim with no durable record at all** — its trades
> lived only in `FleetSimExchange._trades` for the lifetime of the process, so
> a replay's output vanished the moment the run ended.

`fleet_replay_controller.py:1050`, at the `record_trade` site:

> v3.24.13 — persist the fill. Before this, sim trades lived only in
> `FleetSimExchange._trades` and vanished when the process ended, so a replay
> could not be compared against anything afterwards.

### What that means

The question these emitters were built to answer is **"did the sim leave a
trace?"** — not **"did the sim do what it was designed to do?"**

That is why the coverage has the shape it has. The emitters are **output-shaped**:
they record that a trade happened and that a gate decided, because the
motivating defect was that outputs vanished. They are not **process-shaped**:
nothing records that TA ran, that a tablet was read, that a loop completed, or
that a wire moved value — because nobody was asking those questions when the
emitters were written.

The five directives were stated on 2026-08-07/08. The emitters date from
v3.24.12–13 (2026-08-02). **They predate the design they are now being asked to
evidence.** That is not an excuse for the gap; it is the mechanism of it.

### Directive-by-directive

| Directive | Which emitter serves it | Verdict |
|---|---|---|
| **1. Loads bot_state fleet as sim bots** | `meta.json.config.bots` (a count), `gate.decision.bot_id` | **Partial.** The count proves bots were constructed. `bot_id` proves *which* — but only since 2026-08-08; every earlier run carries uuid4s with 0% match to `bot_state`. Nothing records which *fields* imported, so the 0-of-36 `stats` and 0-of-38 `scrumming_state` drop is invisible in the artifacts. |
| **2. Per-candle TA every tick** | **none** | **No emitter exists.** Not partial — absent. The claim was unfalsifiable from artifacts, which is why it survived. |
| **3. Simulates trades on the existing toggling trade logic** | `trade.executed` | **Served for the trade half.** 10,046 records with real prices and sides. The *toggle* half is not emitted: which gate toggles were active is not recorded, only the blockers that fired. |
| **4. Receives, deploys, trades with swarm topologies** | `_activity` prose only | **Not served.** "injected 5 of 5 … wire(s)" is a sentence in a GUI pane. Nothing records whether a wire *routed value* — the "40 wires, $0.00" failure mode is invisible by construction. |
| **5. Logs all behavior and signal flows** | 2 persisted streams; 43 prose sites | **Partially served, and misleadingly so.** Two streams are genuinely machine-readable. But 80% of the tab's emissions are free text, so "all behavior" is not logged in any form an analysis can consume. |

### The structural conclusion

Three of the five directives have **no emitter capable of evidencing them**, and
a fourth is evidenced only in prose. Under the operator's own standard —
*"data and its verified behaviors must be your guiding principal"* — those
directives cannot currently be judged correct or incorrect. They can only be
asserted, which is what went wrong.

The emitters are not defective at what they were built for. They were built for
a different question, and were then treated as if they answered this one.
