# C01 — `save_state` Merge Design & Implementation Plan

**Date:** 2026-08-05
**Build at time of writing:** v3.24.34, 1185 tests green
**Cascade:** C01 — persisted bot records destroyed by a save that follows a skipped restore
**Method rules binding this cascade:** M3 (exit gate is a measurement), M4 (failing-first), M11 (back up before the first destructive run), M15 (persisted-state semantics decided explicitly)
**Target file this plan protects:** `~/.acervator/bot_state.json` — the operator's LIVE trading state. READ-ONLY to every process this plan describes except the armed writer in Phase 2.

> **Status of this document.** This is the design + execution plan. It is not the code. Nothing in Phase 2 may be written until the Phase 0 and Phase 1 exit gates in §8 have been measured green and the operator has answered §9.

---

## Table of contents

1. [The defect](#1-the-defect)
2. [The merge rule](#2-the-merge-rule)
3. [Rejected alternatives](#3-rejected-alternatives)
4. [Adversarial breaks — disposition](#4-adversarial-breaks--disposition)
5. [The exact edits](#5-the-exact-edits)
6. [Test plan](#6-test-plan)
7. [M11 protocol — backup, dry-run, arm](#7-m11-protocol--backup-dry-run-arm)
8. [Exit gates](#8-exit-gates)
9. [Operator decisions required](#9-operator-decisions-required)

---

## 1. The defect

### 1.1 Statement

`StateManager.save_state()` is a **whole-file replacement**, not an update. It constructs `state["bots"] = {}` and fills it *only* from the list of records it was handed. It never reads the file it is about to overwrite. Any bot absent from the caller's list is **deleted from disk**.

`BotManager.save_all_state()` hands it `[bot.get_full_state() for bot in self._bots.values()]` — i.e. only bots currently **registered**. A bot skipped during restore is absent from `self._bots`, therefore absent from the list, therefore absent from the newly written file.

`save_all_state` runs on a 60-second `QTimer`. One tick after a skipped restore, that bot's record is gone.

### 1.2 Verified file:line evidence

| Claim | File:line | Verified text |
|---|---|---|
| `bots` dict built empty | `src/core/state_manager.py:88` | `"bots": {},` |
| Filled only from the passed list | `src/core/state_manager.py:95-98` | `for bot_data in bots: bid = bot_data.get("bot_id", ""); if bid: state["bots"][bid] = bot_data` |
| No read of the current file anywhere on the save path | `src/core/state_manager.py:60-128` | the only `open(self._path)` calls in the class are `load_state` (:138) and `has_saved_state` (:197) |
| Sixth, **write-side** silent drop | `src/core/state_manager.py:96-97` | `if bid:` — a record with no `bot_id` is dropped with no log |
| Backup is unconditional on content | `src/core/state_manager.py:106-108` | `if self._path.exists(): self._backup_path.write_bytes(self._path.read_bytes())` |
| Backup copy is non-atomic | `src/core/state_manager.py:108` | `write_bytes` truncates then writes — no tmp+rename |
| Only prune signal is a post-loss INFO line | `src/core/state_manager.py:124` | `logger.info("Bot state saved: %d bots", len(bots))` |
| Backup unreachable for this defect | `src/core/state_manager.py:144-146` | `_try_backup` is called **only** from the `json.JSONDecodeError` branch of `load_state`; a pruned file is valid JSON |
| Backup unreachable at boot even for corruption | `main.py:720` + `state_manager.py:196-201` | `load_state` is gated behind `has_saved_state()`, which is `try: ... except Exception: return False` |
| Docstring version disagrees with the writer | `state_manager.py:37` vs `:84` | `"1.9.4"` documented, `"1.9.5"` written |
| Caller passes registered bots only | `src/trading/bot_container.py:2334` | `states = [bot.get_full_state() for bot in self._bots.values()]` |
| 60s timer | `main.py:1029-1035` | **(brief said `main.py:985` — that is stale by ~45 lines)** |
| Shutdown save | `main.py:1190` | `bot_manager.save_all_state()` immediately after `result = app.exec()` |
| Third save trigger | `src/gui/main_window.py:5525` | Reset-all-errors button, wrapped in `except/pass` |
| Second, un-backed-up writer | `src/gui/bot_visualizer.py:2549-2564` | writes `~/.acervator/bot_state.json` directly; no backup, no `bot_count`, `except Exception: pass` |
| Both writers collide on one tmp path | `state_manager.py:101` + `bot_visualizer.py:2558` | both resolve to `~/.acervator/bot_state.tmp` |

### 1.3 The eight restore exits (brief said four; there are eight)

| # | File:line | Condition | Log | `continue`? | In `self._bots` after? |
|---|---|---|---|---|---|
| 1 | `bot_container.py:2435-2436` | `not cfg.get("exchange_id")` | **NONE — completely silent** | yes | no |
| 2 | `bot_container.py:2452-2459` | unrecognized `mode` string | ERROR | yes | no |
| 3 | `bot_container.py:2629-2640` | `make_bot_config` raised `ValueError`/`TypeError` | ERROR | yes | no |
| 4 | `bot_container.py:2719-2731` | no construction branch for the `BotMode` (defensive `else`) | ERROR | yes | no |
| 5 | `bot_container.py:2732-2738` | blanket `except Exception` around construction | ERROR | yes | no |
| 6 | `bot_container.py:2768-2771` | Extractor `import_state` raised | **WARNING** | **no** | **yes — degraded** |
| 7 | `bot_container.py:2787-2790` | `import_scrumming_state` raised | **WARNING** | **no** | **yes — degraded** |
| 8 | `bot_container.py:2007` via `:2802` | `register()` returns `(False, reason)` on CapitalRegistry refusal; return value **discarded**, then `restored.append(bid)` runs at `:2803` anyway | `bot.register_refused` event only | n/a | **no — but reported as restored** |

Exit 8 is the one that defeats a naive `bot_count != len(restored)` detector. `restored` is a list of *intentions*; `self._bots` is the *fact*. Exit 8 is currently dormant — `set_capital_registry` (`bot_container.py:1782`) has zero callers, so `self._capital_registry` is `None` — and the comment at `:1430` says it is intended to be armed by MEM-417 Phase B.

Exits 6 and 7 are **strictly worse** than exits 1–5 and are logged at a **lower** severity. The bot registers carrying a *partially* imported state (`import_scrumming_state` at `scrumming_bot.py:3484` mutates field-by-field with no transaction), its `get_full_state()` emits a plausible-looking record built from that indeterminate object, and the next save overwrites the good persisted lots with it.

### 1.4 Measured recovery window

Boot with skipped bot **B**. Disk = `S_pre` (has B).

- **Save 1:** `backup ← S_pre` (has B); `primary ← S_1` (no B).
- **Save 2:** `backup ← S_1` (no B); `primary ← S_2` (no B).

**B is now absent from both files.** Two saves. On the 60s timer that is 120 seconds. It is *less* if the operator quits — `main.py:1190` is save 1 and the next boot's first tick is save 2. No code path performs recovery in that window: `_try_backup` is unreachable because a pruned file parses cleanly.

### 1.5 Irreplaceable-data inventory

Measured read-only from `~/.acervator/bot_state.json` (no write performed): **870,506 bytes, 35 bots, 1,949 `main_lots`, 829 `fold_tranches`,** `version "1.9.5"`. Average blast radius of one pruned record: **~56 lots, ~24 tranches.**

| Rank | Data | Where | Why unrecoverable |
|---|---|---|---|
| **IRREPLACEABLE** | `scrumming_state.main_lots[].initial_buy_price` | `scrumming_bot.py:3443` | This *is* the MEM-171 no-rebuy-higher floor. The exchange gives fills, not the highest-price-first split (`scrumming_bot.py:7199`) that produced today's lot list. |
| **IRREPLACEABLE** | `main_lots[].operator_initiated` / `.auto_detonated_reset` | append sites `:2080`, `:9295`, `:9330`, `:9347`, `:9667` | Operator provenance. Open schema — 8 append sites, 4 distinct key sets. Rebuilding lots from `units`+`initial_buy_price` deletes it. |
| **IRREPLACEABLE** | `scrumming_state.fold_tranches[].ref` / `.initial_buy_price` / `.created_ts` | `scrumming_bot.py:3444`, constructed `:7210`, `:8698`, `:9085` | MEM-245 queued folds. `ref` is the scrum fill the fold-back is measured against; `initial_buy_price` is the MEM-171 floor inherited from the consumed lot. Neither exists on Coinbase. |
| **IRREPLACEABLE** | `fold_tranches[].wire_credits` / `.wire_credits_rolled` | grafted post-construction at `scrumming_bot.py:1904`, helper at `:105-122` | Cross-bot dollar provenance. The code itself: *"this is money provenance, not telemetry."* Present in **no** append site — the live key union is already wider than every constructor. |
| **IRREPLACEABLE** | `anchor_target_balance`, `target_balance` | `scrumming_bot.py:3388-3389`, restore semantics `:3507-3513` | `anchor` is the MEM-244 frozen operator set-point and the detonation-harvest denominator (`anchor × position_ceiling_multiple`, `:3522-3528`). Persistence **is** the organic-growth mechanism. |
| **IRREPLACEABLE (safety)** | `cb_hard_tripped` + 5 sibling `cb_*` keys | `scrumming_bot.py:3420-3434` | Code comment: a tripped breaker *"cannot silently reopen because the process restarted."* Dropping the record is functionally identical to clearing the breaker — the bot comes back untripped and trades. |
| **IRREPLACEABLE (accounting)** | `standing_surplus_usd`, `fold_cycle_cap_consumed`, `pending_wire_credits`, `pending_stack_buy_usd` | `scrumming_bot.py:3394-3419` | Undischarged USD obligations, not counters. Losing `pending_wire_credits` deletes money another bot already routed over. Losing `fold_cycle_cap_consumed` lets the bot spend its per-cycle cap twice — a real over-trade. |
| **IRREPLACEABLE** | `extractor_state.positions[].cost_basis_base`, `.compounding_tier` | `extractor_bot.py:1608`, gated at `bot_container.py:1397-1400` | The Extractor's MEM-171 equivalent. **Zero production coverage** — no extractor record exists in the live file today. |
| **HAND-RECOVERABLE** | `config` (70 `BotConfig` fields) | `bot_container.py:1352` | No exchange source, but operator can re-enter. Note `position_ceiling_enabled`/`_multiple` are read *during restore* to clamp the restored target — a lost config silently moves the harvest threshold of a bot whose `scrumming_state` survived. |
| **PARTLY RECOVERABLE** | `stats` (34 fields) | `bot_container.py:749` | 8 fields refresh from the exchange on start. Only `total_scrummed_usd`, `total_folded_usd`, `total_errors`, `extended_positions_created`, `accumulated_fold`, `accumulated_distribute` are unrecoverable. |
| **DERIVABLE** | `saved_at`, `state_when_saved`, `bot_id`, `phantoms_enabled`, `fold_queue_usd` | `bot_container.py:1350-1374`; `fold_queue_usd` recomputed at `scrumming_bot.py:3741` | The only keys a merge may regenerate. |
| **DEAD** | `phantom_config` | guard at `bot_container.py:1364` | Nothing in `src/` ever assigns `self._phantom_config`. Present in 0 of 35 live records. Documented as real at `state_manager.py:45` — **that docstring line is a trap and must be deleted.** |
| **DELIBERATELY ABSENT** | `current_holdings` | removed by MEM-254, `scrumming_bot.py:3372`, `:3408` | Persisting it created the saved-state-vs-exchange disagreement surface BONK phantom buys exploited. **Any key-union merge resurrects it.** |

---

## 2. The merge rule

> **M15 compliance statement.** This rule is written down explicitly and inherits from nothing. There is no generic helper, no `dict.update`, no deep-merge, no `getattr` default, no "preserve if truthy". Two implementers following §2.1–§2.9 must produce byte-identical output for every input. Where a behaviour is not specified here, that is a defect in this document, not an implementer's judgement call.

### 2.1 The unit of merge

**The unit of merge is the WHOLE per-bot record. There is no sub-key merge anywhere, ever.**

For each `bot_id` that will appear in the written file, exactly **one** source wins wholesale — either the in-memory record from `BotContainer.get_full_state()`, or a carried record copied verbatim — and the losing source is discarded **entirely, including its empty lists, its zeros, and its `False` values.**

### 2.2 Which source wins is never inferred from absence

It is decided by **three explicit registries that only code which OBSERVED an event may write to**:

| Registry | Owner | Populated by |
|---|---|---|
| `BotManager._bots` | `bot_container.py:2017` | a bot that registered successfully |
| `BotManager._restore_ledger` | **NEW** — `dict[bot_id] -> {reason, phase, ts}` | every one of the **eight** exits in §1.3 |
| `BotManager._save_degraded` | **NEW** — `dict[bot_id] -> {reason, ts}` | save-time export failures (`get_full_state` `except` at `bot_container.py:1383`) and Class-A key-loss detection (§2.6) |

The carry *payload* comes from a fourth structure, `BotManager._boot_state_records` — a deep copy of `state["bots"]` taken at the top of `restore_bots_from_state`, i.e. the records exactly as they were on disk at boot. **The carry payload is never re-read from the file at save time.** This is the single most important structural decision in this design; it removes the save-path read entirely and with it four separate adversarial breaks (§4 breaks 4, 14, 15, 17).

### 2.3 The four classes

| Class | Condition | Written record | In-memory disposition |
|---|---|---|---|
| **A — HEALTHY** | in `_bots`, not in `_restore_ledger`, not in `_save_degraded` | **memory record only.** Disk/boot record discarded entirely. An empty `main_lots`, a `0.0` `standing_surplus_usd` and a `False` `cb_hard_tripped` from a healthy bot are REAL values and **must overwrite**. | normal |
| **B — ABSENT** | in `_restore_ledger`, not in `_bots` (exits 1–5, 8) | **boot record carried verbatim** — no key inspection, no validation, no re-derivation, no mode lookup, **zero key edits**. | no object exists |
| **C — DEGRADED** | in `_bots` AND in `_restore_ledger` (exits 6, 7) | **boot record carried verbatim, exactly as Class B.** | **QUARANTINED** — see §2.4 |
| **D — SAVE-DEGRADED** | in `_bots`, not in `_restore_ledger`, in `_save_degraded` | **last successfully persisted record carried verbatim** (`_last_written_records[bid]`, seeded from `_boot_state_records[bid]`). | left running; ERROR logged; surfaced in the panel |

**A `bot_id` present on disk but in NEITHER `_bots` NOR `_restore_ledger` is DROPPED.** That is the one and only delete path, and it is how deliberate deletion keeps working: `main_window.py:6273` → `BotManager.unregister()` pops it from `_bots` (`bot_container.py:2115`) and **must also pop it from `_restore_ledger` and `_boot_state_records`**, so the very next save omits it.

**Why Class C carries disk rather than memory:** `import_scrumming_state` (`scrumming_bot.py:3484`) mutates in place field-by-field with no transaction. A raise leaves the object **partially** imported and **indeterminate** — not "defaults". A record produced from it is plausible and wrong, which is worse than one that is obviously absent.

**Why Class D exists:** `get_full_state` at `bot_container.py:1380-1386` wraps the scrumming export in `try/except` and, on failure, emits the record with **no `scrumming_state` key at all** at WARNING severity while the bot keeps running. `export_scrumming_state` does ~10 unguarded coercions (`float(self._target_balance)`, `[dict(lot) for lot in self._main_lots]`, …) — the shipped handler exists because the authors consider this reachable. Class A's justification is written in terms of empty-vs-populated *values*; a record missing `scrumming_state` entirely is an **absence of a key**, not a value, and must never be allowed to overwrite. Class D is that guard.

### 2.4 Quarantine (Class C) — enforced in memory, at four boundaries

The quarantine is **not** implemented via `bot._was_running`. That field is written at `bot_container.py:2799` and read at exactly one place — the log string at `:2806`. `eligible_filter` (`:2814`, `:2854`) is never passed by any production caller; `main_window.py:6304` calls `start_all()` bare, and `main.py:1056-1060` builds its own `eligible` list that never consults `_was_running`. **Gating on `_was_running` would be a quarantine that does not quarantine.**

Instead:

1. **State boundary.** New enum member `BotState.QUARANTINED = "quarantined"`. A Class C bot is set to it instead of `IDLE`. This one predicate excludes it from *every* existing auto-start path simultaneously, because all four filter on `state.value in ("idle","stopped")` / `state in (BotState.IDLE, BotState.STOPPED)`: `main.py:755` (`_autostart_bot_count`), `main.py:1056-1060` (`_trigger_auto_restart`), `bot_container.py:2852` (`start_all`), `main_window.py:6293` (start-all scan).
2. **Start boundary.** `BotContainer.start()` (`bot_container.py:1094`) refuses when `getattr(self, "_quarantined", False)` is true, logs ERROR, emits `bot.start_refused`. This is the single async start for every bot type, so it also covers `main_window.py:6206`'s direct `bot.start()` which bypasses `BotManager` entirely.
3. **Money boundary.** `SmartWireManager.suspend_bot(bot_id)` pops the bot from `_bot_refs` while leaving `_wires` and `_ledgers` intact. `route_fold_profit` / `_route_scrum_proceeds_via_wires` then take the existing "target unreachable — Wire is orphaned" path (`smart_wire.py:538-548`) and the money **stays with the source and is persisted correctly.** Without this, `apply_wire_income` (`scrumming_bot.py:1719`) has no running/paused/quarantine gate and would credit dollars into an object whose record is frozen on disk — annihilating them.
4. **Mutator boundary.** `reset_circuit_breaker`, `self_destruct`, and the live-settings apply path refuse on `_quarantined` and surface *"this bot is quarantined; adopt the in-memory state or restart the platform"* instead of a button that silently does nothing durable.

### 2.5 The carried-record affordance (mandatory — the rule is incomplete without it)

A Class B bot has no in-memory object, so the GUI delete command at `main_window.py:6273` cannot reach it. Without an explicit affordance, carried records become **immortal**.

- New top-level `carried_forward` map drives a **"Not loaded"** panel.
- Per-row action `forget_unrestored(bot_id)` pops the ledger entry so the next save omits the record.
- Per-row action `adopt_memory(bot_id)` (Class C/D only) discards the carried record and promotes the in-memory one.

**`forget_unrestored` is the single most destructive click in the platform** and must carry the strongest confirmation in it — see §4 break 9 and §5 E22.

### 2.6 Class-A key-loss guard (M15, written down)

Before accepting a memory record for `bot_id` B, compare its **top-level key set** against `_last_written_records[B]`'s top-level key set (seeded from `_boot_state_records[B]`).

- **If the memory record is missing any top-level key the last persisted record had → B is reclassified Class D for this save.** Carry the last persisted record. Log ERROR. Record in `_save_degraded`.
- **This guard can never fire spuriously.** The only conditional top-level keys are `phantom_config` (dead — never present), `phantoms_enabled` (`hasattr` on a constructor-set attribute, always true for both bot types), `scrumming_state` (`hasattr` + `try` — the failure this guard exists for), and `extractor_state` (gated on `config.mode`, which does not change at runtime). **There is no legitimate way for a top-level key to disappear.** Written down here so a future implementer does not "relax" it.
- **One level deeper**, on `scrumming_state`'s key set: `export_scrumming_state` emits a fixed 31-key literal, so no sub-key can vanish from memory once E16 lands (`smart_wire_routes` round-trips). If a sub-key loss is nonetheless detected: write `bot_state.dropped.<ts>.json` containing the disk record, log ERROR, and **accept the memory record**. Rationale, explicit: sub-keys can only ever be added by foreign writers, and freezing a bot's real trading state on disk to preserve a foreign key is the wrong trade. Top-level loss freezes; sub-key loss does not.

### 2.7 Mechanism — `save_state` signature

```python
def save_state(self,
               bots: list[dict],
               smart_wires: Optional[list[dict]] = None,
               smart_wire_ledgers: Optional[list[dict]] = None,
               carry_forward_records: Optional[dict[str, dict]] = None,
               carried_forward_meta: Optional[dict[str, dict]] = None,
               restore_completed: bool = True) -> bool:
```

- `carry_forward_records` is **the records themselves**, by value, passed in from RAM — never a `bool merge` flag, never a set of ids that `save_state` resolves by reading the file, and never derived inside `save_state` by diffing disk against the incoming list. A diff inside `save_state` cannot distinguish a skipped bot from an operator-deleted one; that ambiguity *is* the cascade.
- Passing records rather than ids means **`save_state` performs no read on the save path at all**, so there is no read that can fail, and therefore no abort-on-read-failure, and therefore no fleet-wide persistence freeze.
- Returns `True` on a completed write, `False` on refusal. `save_all_state` logs and surfaces a GUI banner on `False`.

### 2.8 Write-side ordering contract (binding)

`save_state` executes in exactly this order. **Every refusal check runs before any filesystem write**, so a refusal leaves *both* `bot_state.json` and `bot_state.backup.json` byte-identical and mtime-identical.

1. **Refusal check — save before restore.** If `restore_completed is False` and `self.probe() != Probe.NO_FILE`, refuse. Return `False`. (`probe()` is three-valued; `UNKNOWN`/`UNREADABLE` counts as PRESENT — refuse. See §4 break 7 and 16.)
2. Build `out = {}` from the passed `bots` list, **keyed on the registry key**, not on `record["bot_id"]`.
3. **Per-record identity quarantine (NOT an abort).** A memory-sourced record whose `bot_id` is missing or disagrees with its registry key is moved to `carried_forward[bid] = {reason: "malformed_identity", ...}`, written to `bot_state.malformed.<ts>.json`, omitted from `bots`, logged ERROR — **and the rest of the file is written.** Carried records are **exempt** from this check by definition (they are copied without key inspection).
4. Insert `carry_forward_records` verbatim into the same `out` map, only for ids not already present. No side-tree, no `orphans` key — `tests/test_fleet_sim_infrastructure.py:216` and `tests/test_stone_tablets_fetcher.py:171` read `bots` as a flat `bot_id → {config: …}` map and would not warn if the shape changed.
5. `bot_count = len(out)` — **after** carry-forward.
6. `carried_forward = carried_forward_meta`.
7. **Drop sidecar.** Compute `dropped = set(on_disk_ids) - set(out)`. If non-empty, write `bot_state.dropped.<ts>.json` containing the full dropped records **before** anything else touches the primary or the backup. (`on_disk_ids` for this comparison comes from `_last_written_ids`, held in RAM — still no save-path read.)
8. **Backup guard.** Write `bot_state.backup.json` **only if** `set(out) ⊇ on_disk_ids`. When a record is being dropped, the backup is *not* rolled, so the pre-drop copy survives. Backup copy is itself atomic (tmp + rename), unlike today's truncating `write_bytes`.
9. Dump to a **process-unique** tmp path `bot_state.<pid>.tmp`, then `replace()` onto the primary.
10. Update `_last_written_records` / `_last_written_ids`.
11. `logger.info("Bot state saved: %d bots (%d live, %d carried, %d dropped)", …)`.

### 2.9 Per-key table

| Key | Rule | Why |
|---|---|---|
| `bots.<bot_id>` (whole record) | Single-source, whole-object. Class A → memory only. Class B/C/D → carried verbatim, zero key edits, zero validation. **Never a blend.** | The record is the only unit whose internal consistency is guaranteed by the code that produced it. `get_full_state()` (`bot_container.py:1345-1400`) emits config, stats and scrumming_state as one coherent snapshot. Blending a config from one snapshot with a scrumming_state from another silently changes behaviour. |
| `.bot_id` | Identity, never merged. Output dict keyed on the **registry key**. Memory record with missing/mismatched `bot_id` → quarantine that record to sidecar, write the rest. Carried records exempt. | `state_manager.py:96-97` today does `if bid:` and silently drops — a sixth silent-drop, on the write side, indistinguishable from the C01 loss it must prevent. But aborting the whole save on it is a *strict regression*: today the other 34 bots still persist. |
| `.config` (70 fields) | Whole-object from the winning source. Never sub-key merged, never partially refreshed. | `position_ceiling_enabled` + `position_ceiling_multiple` are read during restore (`scrumming_bot.py:3522-3528`) to clamp the restored `target_balance` to `anchor × multiple`. A config from one source beside a `scrumming_state` from another silently moves the Smart Ceiling / detonation-harvest threshold with no log line. |
| `.stats` (34 fields) | Whole-object from the winning source. Carrying a stale stats block is **explicitly accepted as safe**. Never cherry-pick the exchange-refreshable subset. | Restore applies stats through a permissive `hasattr` loop (`bot_container.py:2744-2747`), so obsolete keys are dropped harmlessly on the way back in, and `realized_pnl_exchange`/`avg_entry_exchange`/`fees_paid_exchange` refresh from the exchange on start. Only 6 fields are unrecoverable and they travel with the record. |
| `.state_when_saved` | Regenerated from the live bot for Class A. **Carried VERBATIM for B/C/D** — do not rewrite to `"idle"` to make the record look safe. | The persisted value is evidence of the last healthy save; next boot must re-evaluate the import on its own (a transient failure is fixed by a restart, and rewriting the field would permanently disarm a legitimate auto-restart). Safety is enforced in memory by `BotState.QUARANTINED`, not on disk. |
| `.saved_at` | Regenerated at write for Class A. **Frozen at its carried value** for B/C/D. Carry age tracked separately in `carried_forward.first_carried_at`. | If `saved_at` were refreshed on carry, a record stuck in carry for weeks would look freshly written and every staleness heuristic would read a lie. |
| `.phantoms_enabled` | Whole-record source. No special handling. | Present on all 35 live records. Carving it out would create a second merge granularity for no benefit. |
| `.phantom_config` | Never synthesized, never expected. Carried verbatim if a record happens to contain it. **Delete its line from the docstring at `state_manager.py:45`.** | The `hasattr` guard at `bot_container.py:1364` is always `False` — nothing in `src/` assigns `self._phantom_config`, and the key appears nowhere in the live file. A merge author budgeting for it from the docstring writes a branch that can never execute. |
| `.scrumming_state` (31-key dict) | Whole-object, atomic, from the winning source. **NEVER sub-key merged.** Never reconstructed from a declared field list. | This is the M15 hazard in its exact form: any per-key rule re-preserves a stale sub-key against a bot that legitimately changed it. It is also the only container of MEM-171 and MEM-245 data — 1,949 lots and 829 tranches across 35 bots. |
| `.scrumming_state.main_lots` | Travels with its parent record only. Whole-list copy of opaque dicts. **An EMPTY list from a Class A bot is a real value and must overwrite the disk's populated list.** | Fold-to-empty is normal. Re-preserving 56 lots for a bot that just folded to zero makes the next SCRUM size against inventory that does not exist and computes MEM-171 floors from ghost lots. Conversely, 8 append sites with 4 key sets mean rebuilding from `units`+`initial_buy_price` silently deletes operator provenance. |
| `.scrumming_state.fold_tranches` | Travels with its parent record only. Whole-list copy; **no key whitelist, no schema validation on carry.** | `wire_credits` / `wire_credits_rolled` are grafted onto an existing tranche long after construction (`scrumming_bot.py:105-122`, `:1904`) and appear in NO append site. The live key union is already wider than every constructor. Any validation keyed to a construction site deletes cross-bot dollar provenance. |
| `.scrumming_state.fold_queue_usd` | Must travel with the same source as `fold_tranches`. Never carried or regenerated independently. | It is a derived summary — `sum(t["usd"])` over `_fold_tranches` (`scrumming_bot.py:3741`). Split from its list it desynchronizes from the thing it summarizes, invisibly, because both values are plausible floats. |
| `.scrumming_state.anchor_target_balance`, `.target_balance` | Whole-record source. Never mixed with a config from the other source. | `anchor` is the MEM-244 frozen operator set-point and the detonation-harvest denominator. `target_balance` **above** anchor is the correct persisted state (`scrumming_bot.py:3507-3513` — the organic-growth mechanism). Lose the record and the bot re-anchors at a wizard default, silently moving the harvest threshold. |
| `.scrumming_state.cb_hard_tripped` (+ `cb_hard_tripped_at`, `cb_hard_trip_pct`, `cb_soft_active_side`, `cb_soft_cooldown_remaining`, `cb_soft_trip_pct`) | Whole-record source. **No automatic path may ever drop a record containing a `True` `cb_hard_tripped`** — only the explicit operator forget/adopt actions may, and `forget` refuses outright on such a record unless the operator types the bot id. Equally, a `False` from a Class A bot **must** overwrite a `True` on disk. | `scrumming_bot.py:3420`: a tripped breaker must not silently reopen because the process restarted. Dropping the record is functionally identical to clearing the breaker. The symmetric error is preserve-if-truthy, which would make an operator-cleared breaker re-trip forever. |
| `.scrumming_state.standing_surplus_usd`, `.fold_cycle_cap_consumed`, `.pending_wire_credits`, `.pending_stack_buy_usd` | Whole-record source. **`0.0` from a Class A bot is a real discharge and MUST overwrite a non-zero disk value.** | Undischarged USD obligations, not counters. Re-preserving a spent `standing_surplus_usd` double-grows `target_balance`; re-preserving a consumed `fold_cycle_cap_consumed` lets the bot spend its per-cycle cap twice — a real over-trade. |
| `.scrumming_state._format_version` | **Never rewritten on carry.** The forward-version gate lives at **import** time, not carry time: `import_scrumming_state` refuses (→ Class C) when the on-disk version exceeds the running version. A lower version is imported normally — that is what the per-key `.get()` defaults exist for. Carry-side check retained as a second line. | Currently `7` (`scrumming_bot.py:3481`) and **write-only** — nothing reads it. A forward-version record means the file was written by a newer build and this process cannot reason about it. Putting the gate only on the carry path checks it in the one place it cannot help (§4 break 20). |
| `.scrumming_state.smart_wire_routes` | **Must round-trip through `export_scrumming_state`/`import_scrumming_state` (edit E16).** Until it does, Class A silently deletes it. | Written into `scrumming_state` by `bot_visualizer.py:2580/2608/2632` and read back by `_hydrate_smart_wire_routes_from_disk` (`:2636-2659`), but absent from the 31-key export. Measured: 0 of 35 live records carry it; `smart_wires` holds 40 entries. Without E16, a Class A bot loses its routes on the next tick while a Class B bot keeps them forever — survival inverted. |
| `.scrumming_state.current_holdings` | **Never written into a memory-sourced record** (already true — MEM-254 removed it). **Never stripped from a carried record either** — carry stays byte-identical, zero exceptions. | MEM-254 deleted it because persisting it created the saved-state-vs-exchange disagreement surface BONK phantom buys exploited. A key-union merge resurrects it from any pre-MEM-254 record — the strongest single argument against deep-merge. Stripping on carry would sound safer but opens the door to "just one more" key edit; a stale key is inert on the way back in because `import_scrumming_state` reads only named keys via `.get()`. |
| `.extractor_state` | Whole-object from the winning source. For a carried record, **do NOT consult the bot's mode** — there is no live object — and do not re-derive the mode gate. Copy the record whole regardless of contents. | Mode-gated at write (`bot_container.py:1397-1400`) and mirrored at read (`:2754-2756`). A merge keyed on the live bot's mode has no mode to consult for an absent bot. `positions[].cost_basis_base` and `compounding_tier` are the Extractor's MEM-171 equivalent. **Zero production coverage today** — this path must not depend on inference. |
| `bots` (top-level container) | Shape frozen: JSON object keyed by `bot_id` whose values contain a `config` sub-object. Carried records go in the **same** map — no `orphans`/`quarantine` sub-tree. | `tests/test_fleet_sim_infrastructure.py:216` and `tests/test_stone_tablets_fetcher.py:171` read this shape from fixtures they write themselves — they will **not** warn if the real writer changes shape. A side-tree would also make a carried bot invisible to every existing consumer including the sim fleet loader. |
| `bot_count` | `len(state["bots"])` **after** carry-forward, not `len(bots)`. | `state_manager.py:87` writes `len(bots)` today. With carry armed that under-counts by exactly the carried count, and the file would disagree with itself — the first thing an operator checks during an incident. |
| `carried_forward` (**NEW** top-level) | Written each save from the in-memory ledger: `{bot_id: {reason, phase, first_carried_at, source_saved_at, carry_count, symbol, exchange_id, lots, tranches, anchor_target_balance, standing_surplus_usd, cb_hard_tripped}}`. **READ-ONLY on load** — forensic, drives the panel, and readable by `tools/`. **NEVER the authority for what to carry.** The ledger is rebuilt from scratch each boot from observed restore events. | If the file told the next boot what to carry, a single bad write would make a bot immortal and the skipped-vs-deleted ambiguity would return in persisted form. The denormalized summary fields exist so the "Not loaded" panel and the forget-confirmation can name what is being destroyed without parsing the record. |
| `version` | Bump to `"1.10.0"` when the writer is armed. Fix the docstring at `state_manager.py:37` (`1.9.4` → `1.9.5` in Phase 0, → `1.10.0` at arm). Readers must tolerate unknown top-level keys — they already do. | M15 requires the semantics be written down; the field that would carry them is currently written, never read, and already documented wrong. `carried_forward` is the first on-disk contract change with anything to hang a migration on. |
| `saved_at` / `saved_at_human` | Always regenerated at write from wall clock. Never carried. | They describe the **write**, not any bot. Freezing them breaks the only human-readable staleness signal `load_state` logs. |
| `smart_wires` / `smart_wire_ledgers` | Unchanged: whole-list replacement from `SmartWireManager`, existing preserve-if-`None` contract. **No carry-forward needed, and it is PROHIBITED to add an "endpoint must be registered" filter to `export_wires()`/`export_ledgers()`.** | `import_wires` (`smart_wire.py:414-437`) does not filter unknown endpoints and `import_ledgers` creates missing entries, so wires belonging to a carried bot survive the round trip today. `detach_bot` (`:253`) — called only from `unregister()` — must remain the ONLY wire pruner, keeping wire deletion aligned with the same explicit-delete rule as records. A registration filter would reproduce C01 one layer up, silently deleting the swarm topology of every carried bot. **`suspend_bot` (§2.4) is deliberately distinct from `detach_bot`: it pops `_bot_refs` only, never `_wires`.** |

---

## 3. Rejected alternatives

### 3.1 Recursive deep-merge / key-union (memory wins on conflict)

**Rejected because** it cannot represent deletion of anything. Every empty list, zero and `False` produced by a legitimate state change is re-filled from the stale record, and obsolete keys are resurrected.

**Concrete failure (A):** A bot folds its last lot. `_main_lots` becomes `[]`; export writes `main_lots: []`. The merge re-preserves the disk's 56 lots. The next SCRUM sizes a fold against inventory that does not exist and computes MEM-171 no-rebuy-higher floors from ghost `initial_buy_price` values.

**Concrete failure (B), independent:** Any pre-MEM-254 record still on disk carries `current_holdings`. A key-union resurrects it into the merged record, re-opening the exact saved-state-vs-exchange disagreement surface BONK phantom buys exploited and that Session 26 deliberately closed by deleting the field (`scrumming_bot.py:3372`, `:3408`).

### 3.2 Preserve-if-truthy / "only overwrite when the in-memory value is non-empty"

**Rejected because** it conflates "absent" with "legitimately zero", and silently reverses two operator actions.

**Concrete failure (A):** `standing_surplus_usd` drains to `0.0` after being spent into target growth. `0.0` is falsy, so the old dollar value is re-preserved and the bot grows its target a second time off money already spent.

**Concrete failure (B), worse:** The operator clears a circuit breaker, so `cb_hard_tripped` becomes `False`. `False` is falsy, so the disk's `True` is re-preserved and the breaker **re-trips on every restart forever** — the operator cannot clear it by any means short of hand-editing JSON.

### 3.3 Infer preservation from absence: "any `bot_id` on disk but not in `self._bots` is preserved"

**Rejected because** absence is the exact ambiguity this cascade exists to remove. This rule cannot tell a skipped restore from a deliberate delete, and it resolves the ambiguity in the direction that breaks the operator's explicit action.

**Concrete failure (A):** `main_window.py:6262-6276` — the operator confirms a `QMessageBox` reading *"Delete bot X? This cannot be undone"*. `unregister()` pops it from `self._bots` (`bot_container.py:2115`). The next 60-second save re-preserves the record from disk, and the next boot restores the deleted bot with all its lots. **The delete undoes itself.**

**Concrete failure (B):** A save fired while the registry is only partially built — reachable today from the Reset-all-errors button at `main_window.py:5525`, wrapped in `except/pass` — preserves full stale records for bots that are mid-load, producing a file that mixes live and stale records with no marker distinguishing them.

### 3.4 Tombstone-only: record deletions explicitly, preserve every other absent bot forever

**Rejected because** it is the mirror image of the chosen rule with an *unbounded* rather than bounded failure surface, and it makes the safety property depend on a write succeeding at exactly the wrong moment.

**Concrete failure:** The operator deletes a bot; the app is killed (or the save fails, or the disk is full) before the tombstone reaches disk. The bot resurrects on next boot with its full lot list and can be started. And the tombstone list must be retained **forever** to prevent resurrection, so the file accretes ids indefinitely with no principled expiry.

The chosen positive-carry set is bounded by what *this boot's* restore actually observed. Its worst-case failure is that a record is dropped that would have been carried — visible immediately in the `carried_forward` panel, the drop sidecar, and the prune WARNING — rather than a silent resurrection weeks later.

### 3.5 Key-level merge restricted to a whitelist of "irreplaceable" keys

**Rejected because** whitelists go stale against an open schema, and every key added by a future version is silently outside the protection until someone remembers to extend the list.

**Concrete failure:** `fold_tranches` entries carry `wire_credits` and `wire_credits_rolled`, grafted on post-construction at `scrumming_bot.py:1904` and appearing in **no** append site. The live tranche key union (`created_ts`, `initial_buy_price`, `operator_initiated`, `ref`, `units`, `usd`, `wire_credits`, `wire_credits_rolled`) is already wider than every constructor. A whitelist derived from the construction sites at `:7210`/`:8698`/`:9085` deletes cross-bot dollar provenance the code itself labels *"money provenance, not telemetry."* Same failure on lots: `operator_initiated` and `auto_detonated_reset` are absent from the two-field "canonical" shape.

### 3.6 Rely on `bot_state.backup.json` and change nothing on the write side

**Rejected because** the backup is not reachable in this scenario, is not reachable at boot even in the scenario it *was* designed for, and leaning on it makes the recovery claim an opinion — which M3 forbids.

**Concrete failure:** `_try_backup` (`state_manager.py:151`) is called from exactly one place: the `json.JSONDecodeError` branch of `load_state` (`:144-146`). A pruned file is perfectly valid JSON, so `load_state` returns it and the backup is never consulted. Measured window: save 1 copies the good file to backup and writes the pruned primary; save 2 copies the pruned primary over the backup. Two saves and the record is gone from both files. Separately, `main.py:720` gates `load_state` behind `has_saved_state()`, which swallows every exception and returns `False`, so on a genuinely corrupt primary the app starts with zero bots and never reaches the backup at all.

### 3.7 Freeze persistence entirely whenever any bot was skipped

**Rejected because** it trades a bounded loss for an unbounded one and stops the platform recording work it is still doing.

**Concrete failure:** One bot whose persisted config lost its `exchange_id` (the silent skip at `bot_container.py:2436`) freezes saves for all 35 bots. Every scrum, fold, tranche creation and breaker trip on the other 34 goes unpersisted for the entire session; a crash or power loss then discards the whole session's lots and tranches — orders of magnitude more MEM-171 data than the single record being protected.

**Note:** the earlier draft of this rule reintroduced this alternative through the "abort the save if the carry read fails" door. §2.2's RAM-held carry payload removes the read entirely, so there is nothing left to abort on. See §4 breaks 4, 14.

### 3.8 Materialise skipped bots as read-only pseudo-bot objects inside `self._bots`

**Rejected because** `self._bots` is iterated by dozens of consumers that assume a live, startable bot. Injecting inert objects turns a persistence fix into a platform-wide behavioural change.

**Concrete failure:** `for bot in self._bots.values()` drives capital-reservation totals, `list_bots()`/`list_bots_by_exchange()` (`bot_container.py:2312-2322`), the start_all eligibility scan (`main_window.py:6293-6294`), and `SmartWireManager` attach. A pseudo-bot in IDLE appears in the GUI as a startable bot; the operator clicks Start All and the platform attempts to start an object that was never constructed because its config raised in `make_bot_config`. Keeping carried records in a ledger *outside* the registry leaves all those call sites untouched.

### 3.9 Fix only the import-failure fall-throughs (add `continue` at `:2790`) and leave `save_state` alone

**Rejected because** it converts the worst class into the second-worst class rather than fixing either, and leaves five skip paths still destroying records.

**Concrete failure:** Adding `continue` at `:2790` makes the bot **ABSENT** instead of degraded — which is precisely the condition that causes `save_all_state` to erase its record 60 seconds later. The archived tests prove this is a trap already fallen into once: `_archive/tests_pre_2026_07_25/test_bot_restoration_dispatch.py:320` asserts `restored_ids == []` and `"grid-1" not in mgr._bots` as the **SUCCESS** condition — it pins the skip as correct while the record is being deleted, and would stay green through the entire data loss.

### 3.10 Resolve carry ids by reading the file inside `save_state`

**Rejected because** the read is on the critical path of every 60-second tick and its failure mode is a fleet-wide persistence freeze on an ambient Windows IO condition (AV scanner, backup agent, ACL change) that the operator cannot see.

**Concrete failure:** see §4 breaks 4 and 14 — the abort-on-read-failure design loses an entire session of new lots and tranches across 34 healthy bots in order to protect one record. Replaced by §2.2: the carry payload is deep-copied from `state["bots"]` at boot, held in RAM, and passed by value into `save_state`.

---

## 4. Adversarial breaks — disposition

Every break from the adversarial pass is listed. Each is **MITIGATED** (with the specific edit that closes it) or **ACCEPTED** (with the reason).

| # | Lens / severity | Break, one line | Disposition |
|---|---|---|---|
| **1** | DATA LOSS / high | **`register()` refusal is invisible.** `register` returns `(granted, reason)` and `return False, reason` at `:2007` never reaches `self._bots[...] = bot` at `:2017`; `restore_bots_from_state:2802` discards the return and runs `restored.append(bid)` at `:2803` anyway. The bot hits none of the seven ledger exits, so it is in *neither* registry — which the rule defines as DROP. The fix deliberately deletes it, and the `bot_count != len(restored)` detector reads EQUAL. Dormant today (`_capital_registry is None`), armed by MEM-417 Phase B. | **MITIGATED — E6.** Capture the return: `_ok, _why = self.register(bot)`. On refusal, write ledger entry `reason="register_refused", phase="register"` (**exit 8**) and do **not** append to `restored`. **E9** changes the detector to compare `len(saved["bots"])` against `len(self._bots)` — the fact, not the intention. **E21** asserts every id in the outgoing `states` list is a key of `self._bots`. |
| **2** | DATA LOSS / high | **`get_full_state` swallows export failure and emits a record with NO `scrumming_state` key**, at WARNING, while the bot keeps running. The bot is Class A by the two-registry rule, so its truncated record overwrites 56 lots and 24 tranches. Both registries observe only *restore*-time events; there is no save-time observation point. | **MITIGATED — §2.3 Class D + §2.6 + E7 + E21.** Third registry `_save_degraded`, written by the `except` branch at `bot_container.py:1383` (also raised **WARNING → ERROR**). Structural guard: a memory record missing any top-level key the last persisted record had is reclassified Class D and the last persisted record is carried instead. |
| **3** | DATA LOSS / high | **Quarantined Class C bot still receives wire income.** It is registered, so `SmartWireManager._bot_refs` contains it; `apply_wire_income` (`scrumming_bot.py:1719`) has no state gate; `_scrum_routed_total += _routed` at `:1646` runs unconditionally. Dollars leave the source's persisted fold queue and are annihilated at the quarantined bot whose record is frozen on disk. Net-new loss introduced by quarantine. | **MITIGATED — E17 + E18.** Quarantine at the money boundary: `SmartWireManager.suspend_bot(bot_id)` pops `_bot_refs` (leaving `_wires`/`_ledgers` intact) so the existing "target unreachable — Wire is orphaned" path at `smart_wire.py:538-548` fires and the money stays with the source. **E18** independently fixes `scrumming_bot.py:1646` so `_scrum_routed_total += _routed` only executes when `_apply_result.get("applied")` is truthy — today a rejected apply still debits the source. Both pinned by tests. |
| **4** | DATA LOSS / high | **Abort-on-read-failure freezes the whole fleet.** With `carry_forward_ids` non-empty all session, a persistent Windows read failure (AV handle, backup agent, ACL) aborts every 60s tick and the shutdown save. To protect one record the design discards a whole session of lots/tranches across 34 bots — reintroducing rejected alternative §3.7 through the abort door. | **MITIGATED — §2.2 + §2.7, structurally eliminated.** The carry payload is deep-copied at boot from the `state` dict already loaded at `main.py:721` and passed **by value** into `save_state`. `save_state` performs **no read on the save path**. There is no read to fail, therefore no abort, therefore no freeze. This also removes the need for the N-consecutive-aborts / rescue-sidecar machinery the break proposed. |
| **5** | DATA LOSS / high | **Abort-on-malformed-identity is a permanent, self-perpetuating, all-bot persistence freeze.** A carried record with no `bot_id` (creatable by `bot_visualizer._ensure_routes` doing `bots.setdefault(bid, {})`) is never inspected or edited by the carry, so the abort fires on every tick forever. Strict regression: today `if bid:` drops it and the other 34 still persist. | **MITIGATED — §2.8 step 3.** Never abort the whole save on a per-record defect. Quarantine the record: move it to `carried_forward[bid] = {reason: "malformed_identity"}`, write `bot_state.malformed.<ts>.json`, omit from `bots`, log ERROR, **write the rest.** Abort is reserved for whole-file conditions (only §2.8 step 1 remains). Carried records are exempt from the identity check by definition. **E13** additionally stops `bot_visualizer` from creating such stubs. |
| **6** | DATA LOSS / high | **Phase 0's own first boot destroys pre-existing recoverable damage.** Phase 0 changes no write behaviour by design, so the ordinary 60s save at t+60s copies the already-pruned primary over the backup that still holds the pre-fix record. | **MITIGATED — E1 + E2 + E5.** Phase 0's **first** action, before `restore_bots_from_state` and before the `QTimer` at `main.py:1033` starts, is `state_mgr.preflight_snapshot()` — a dated off-ring copy of **both** files to `bot_state.preflight.<ts>.json` / `bot_state.backup.preflight.<ts>.json`. Pure-read on the live tree; satisfies M11 literally. **E5** adds a boot-time diff of primary vs backup reporting any `bot_id` in the backup but absent from the primary — the only detector that can surface pre-existing C01 damage. |
| **7** | DATA LOSS / medium | **Corrupt primary defeats the save-before-restore guard.** `has_saved_state()` swallows the `JSONDecodeError` and returns `False`, so restore is skipped, `_restore_completed` is never set, but the guard's companion predicate ("a state file with bots exists") also reads `False` → guard passes → the app writes `bots: {}` and two saves later both files hold zero bots. | **MITIGATED — E3 + §2.8 step 1.** Three-valued `StateManager.probe() -> NO_FILE | HAS_BOTS | EMPTY | UNREADABLE`, implemented on the **file** (`exists() and stat().st_size > 0`) before parsing. `UNREADABLE` counts as PRESENT → refuse the write. `main.py:720` branches on `UNREADABLE` into `_try_backup()` before any save timer starts. `has_saved_state()` is reimplemented as a thin wrapper over `probe()` so the bare `except: return False` disappears. |
| **8** | DATA LOSS / medium | **`smart_wire_routes` survival is inverted.** The GUI writes it into `scrumming_state`; `export_scrumming_state` does not emit it. Class A deletes the operator's routes on the next tick; Class B keeps them forever. Proof that "Class A memory wins wholesale" is unsafe against keys memory does not know exist. | **MITIGATED — E16 + E13 + §2.6.** `smart_wire_routes` is added to `export_scrumming_state`/`import_scrumming_state` so it round-trips through memory (option **a** from the break). `_save_bot_state_dict` is deleted and the routing matrix routed through `StateManager`. §2.6's key-set guard is the backstop that catches the *next* such key the day it appears rather than after it is lost. |
| **9** | DATA LOSS / high (dupe of OPERATIONAL #6) | **`forget_unrestored` is a one-click, no-undo delete of MEM-171 cost basis** with no specified confirmation, on a panel whose rows carry no information about what is inside them, and where Privacy Mode (`bot_visualizer.py:878-886`) can render two rows visually identical. Recovery window ~60s, and no code performs the recovery. | **MITIGATED — E22 + §2.8 step 7/8.** (1) Panel rows render, from the carried record itself, `symbol / exchange / len(main_lots) / len(fold_tranches) / anchor_target_balance / standing_surplus_usd / cb_hard_tripped`. Identifiers are **never masked** in this panel or its dialogs. (2) Confirm modal restates those numbers verbatim. (3) `forget` writes `bot_state.forgotten.<bot_id>.<ts>.json` **synchronously, before** popping the ledger. (4) `forget` **refuses outright** on a record with `cb_hard_tripped: true` unless the operator types the bot's short hash. (5) `forget` forces an immediate `save_all_state()` rather than waiting for the tick. (6) The drop sidecar (§2.8 step 7) and the backup guard (step 8) give a second, off-ring copy regardless. |
| **10** | STALE RESURRECTION / **critical** | **Class C quarantine is unenforceable via `_was_running`.** `main_window.py:6304` calls `start_all()` bare; `bot_container.py:2853` selects purely on `BotState`; `main_window.py:6206` calls `bot.start()` directly, bypassing `BotManager`; `bot_live_settings.py:2656` self-destruct market-sells without the bot ever running. The bot then trades all session while the carry copies its pre-trade record, and next boot restores ghost lots. The drift check at `scrumming_bot.py:3745` is **dead** (MEM-254 leaves `_current_holdings` at 0.0 during import), so there is no log line at all. | **MITIGATED — E17, using option (b) with a state change.** `BotState.QUARANTINED` (a value that is in **neither** `("idle","stopped")`) excludes the bot from all four auto-start filters by the one predicate they already share. Plus a `_quarantined` flag checked **inside `BotContainer.start()`** (`:1094` — the single async start for every bot type, so `main_window.py:6206` is covered), inside `self_destruct`, inside manual fire, and inside the live-settings apply path. `start_all` at `:2853` additionally excludes `getattr(b, "_quarantined", False)` **regardless of any caller-supplied `eligible_filter`**. Failing-first test T-14 drives `mgr.start_all()` with **no** filter against a quarantined bot. |
| **11** | STALE RESURRECTION / **critical** | **Quarantined bot is a live wire endpoint.** `_route_scrum_proceeds_via_wires` finds it in `_bot_refs` (unlike a Class B bot, which is `None` and skipped at `:1638`), `apply_wire_income` mutates its tranches/target/anchor, `:1646` debits the source unconditionally. Repeats on every scrum of every wired bot all session — unbounded, not one-shot. | **MITIGATED — E17 + E18.** Same as break 3: `suspend_bot` pops `_bot_refs` only. `smart_wires`/`smart_wire_ledgers` are untouched so topology still round-trips (the §2.9 prohibition on registration filters is preserved). `:1646` is gated on `applied`. |
| **12** | STALE RESURRECTION / high | **Operator cannot clear a hard breaker on a quarantined bot.** `bot_live_settings.py:2600-2606` → `reset_circuit_breaker("all")` mutates the live object with no state check; the quarantine excludes the bot from the states list so `False` never reaches disk; the carry re-writes `cb_hard_tripped: true` every 60s; next boot re-trips at `scrumming_bot.py:3653`. Reproduces the very failure §3.2 rejects. | **MITIGATED — E17 mutator boundary + E22 adopt.** `reset_circuit_breaker` refuses on `_quarantined` and the panel surfaces *"this bot is quarantined; adopt the in-memory state or restart the platform"* instead of a button that silently does nothing durable. The escape is `adopt_memory(bot_id)`, which discards the carried record, clears the quarantine, and lets the next save write the real value. **Subject to operator decision D2** (§9). |
| **13** | STALE RESURRECTION / high | **Carried record defeats `tools/purge_orphan_reservations.py`.** Its `_load_live_bot_ids` (`:60-66`) builds the live set from `bot_state.json["bots"].keys()`, and a carried record is in that dict. A phantom `0.118 ETH` reservation permanently suppresses a sibling bot's SCRUMs (`capital_reservation.py:481-484` → `scrumming_bot.py:10105` SELL REFUSED), and the only automated reclaim path reports zero orphans. `prune_expired` (`capital_reservation.py:567`) has **zero production callers**. | **MITIGATED — E19 + E6.** `purge_orphan_reservations.py` builds its live set as `bots` **MINUS** `carried_forward` — which is exactly why `carried_forward` must be readable by tooling despite being non-authoritative. Same fix for `tools/quarantine_sim_contamination.py:_is_contaminated`. **E6** additionally calls `self._capital_registry.release_reservation(bot_id=bid)` for every Class B ledger entry at the end of `restore_bots_from_state` (a Class B bot has no object, so it can hold no reservation), and wires `prune_expired` to run once after restore completes. |
| **14** | STALE RESURRECTION / medium | **An aborted save also drops fold-to-empty, breaker clears and deletions** — not just "stats deltas" as the earlier cost model claimed. Trigger includes the `bot_state.tmp` collision between `state_manager.py:101` and `bot_visualizer.py:2558` producing a `PermissionError` inside the rename window. | **MITIGATED — §2.2 (no save-path read at all) + E13 (second writer deleted) + E14 (process-unique tmp `bot_state.<pid>.tmp`).** All three independently remove the trigger. |
| **15** | STALE RESURRECTION / medium | **"Forget" is a RAM-only decision that a second writer can undo.** `_apply_routes_to_state` re-reads a file that still contains the forgotten bot, mutates, and `_save_bot_state_dict` writes the whole dict back with no backup and `except: pass` — resurrecting it. `_ensure_routes` also injects `smart_wire_routes` into a carried record, falsifying "byte-identical carry". | **MITIGATED — E13 + E22.** `_save_bot_state_dict` is **deleted**; the routing matrix routes through `StateManager`. `_load_bot_state_dict` excludes ids listed in `carried_forward` so dead bots are never offered as wire endpoints. `_apply_routes_to_state` / `_clear_all_routes_in_state` are restricted to ids in `BotManager._bots`, so no GUI path can touch a carried record. `forget_unrestored` forces an immediate save and logs the dropped record's lot/tranche counts. |
| **16** | OPERATIONAL / **critical** | **`_was_running` is a dead field; `main.py:1056-1060` never consults it.** `_trigger_auto_restart` fires at ~9.25s post-splash, ~50s before the first save, and starts the Class C bot with a real exchange. Anchor and target restored, `_main_lots` empty → the first SCRUM has no MEM-171 price floor at all. | **MITIGATED — E17.** Identical to break 10: gate on `BotState.QUARANTINED`, not on `_was_running`. Failing-first test **T-15** drives `main.py`'s exact `eligible` list comprehension (`[b for b in mgr._bots.values() if b.state.value in ("idle","stopped")]`) against a Class C bot and asserts it is empty. |
| **17** | OPERATIONAL / **critical** | **Operator hand-edits the live file (as `bot_container.py:2636-2638` instructs) → unparseable → abort-on-read freezes the fleet silently for six hours** → power loss discards everything. Only signal is a `logger.error` line nobody watches. | **MITIGATED — §2.2 (no save-path read) + E9/E20 GUI banner + E23 remediation-text change.** With the carry payload in RAM the hand-edit cannot stall the writer at all. Additionally: any refusal (§2.8 step 1) raises a **persistent GUI banner**, not only a log line. And the remediation text at `bot_container.py:2636-2638` is rewritten to point at the "Not loaded" panel's repair action instead of telling the operator to hand-edit a live file. |
| **18** | OPERATIONAL / **critical** | **`_load_bot_state_dict` silently returns `_try_backup()` contents on a corrupt primary, and `_save_bot_state_dict` then writes that rollback back over the primary** — repairing-by-reverting an entire save cycle, with the carried record reported as a healthy carry and no rollback marker anywhere. | **MITIGATED — E13 + E24.** `_save_bot_state_dict` is deleted (the break's own first recommendation). `StateManager.load_state()` gains a provenance flag; a new `load_state_strict()` **never** falls back to the backup and is the only loader permitted to any caller whose next act is a write. The routing matrix uses `load_state_strict()`. |
| **19** | OPERATIONAL / high | **Transient unreadable file at boot** → `has_saved_state()` returns `False` → restore skipped → operator recreates a bot by hand → the save-before-restore guard blocks writes for the whole session (or, if fail-open, one record replaces 35). The rule never specified the guard's behaviour when its predicate cannot be evaluated. | **MITIGATED — E3 + §2.8 step 1 + E20 banner.** Three-valued `probe()`; `UNREADABLE`/`UNKNOWN` is treated as PRESENT (refuse). Refusal is made **visible**: a persistent GUI banner reading *"State persistence is OFF — restore did not complete"*, so an operator never spends a session writing to nothing. `main.py:720` branches on `UNREADABLE` into `_try_backup()` and offers backup recovery (**operator decision D5**, §9). |
| **20** | OPERATIONAL / medium | **The `_format_version` guard is placed where it cannot fire.** `import_scrumming_state` never checks it, so a newer build's records all restore as Class A, zero are carried, the carry-side guard never fires, and 35 records are silently round-trip **downgraded** to version 7. | **MITIGATED — E11 (phase 0, log-only) + E25 (phase 2, enforcing).** The gate moves to the top of `import_scrumming_state`: refuse the import (→ Class C) when the on-disk `_format_version` **exceeds** the running version. The carry-side check is kept as a second line. Phase 0 ships the log-only WARNING form, which changes no write behaviour and is the cheapest M11 instrument available. |
| **21** | OPERATIONAL / high | **The one-cycle backup grace window is spent by the fix itself.** After the first carry save, primary and backup agree about the carried record; `bot_state.backup.json` stops meaning "may still contain something the current write dropped" and becomes a second copy of the same carry set. The one-deep ring becomes redundant rather than protective. | **MITIGATED — §2.8 steps 7-8.** The backup is made to do work the primary cannot: it is rolled **only when `set(out) ⊇ on_disk_ids`**, so a save that drops anything leaves the pre-drop backup intact. And any drop writes a dated off-ring `bot_state.dropped.<ts>.json` containing the full dropped records **before** the rename. This is M11's "backup before the first destructive run" applied to the one destructive act the fix still permits, and it answers the open question about a first-carry sidecar: **the sidecar belongs at the DROP, not at the first carry.** |
| **22** | OPERATIONAL / medium | **Abort ordering: the backup write at `:108` sits upstream of any natural abort point**, so every aborted save copies the primary over the backup and the ring is dead for the whole incident. | **MITIGATED — §2.8, binding order.** Contract stated as *"neither `bot_state.json` nor `bot_state.backup.json` is modified"* and enforced structurally: **all refusal checks run before the tmp dump at step 9.** Test **T-19** aborts a save and asserts both files' bytes **and** mtimes are unchanged. **E14** additionally makes the backup copy atomic (tmp+rename) so a crash mid-copy cannot leave a truncated backup that `_try_backup` rejects at `:161`. |
| **23** | OPERATIONAL / medium | **Disconnect All edits carried records in place**, falsifying the byte-identical guarantee: `_clear_all_routes_in_state:2620` iterates **every** record in the file including carried ones and sets `scr["smart_wire_routes"] = []`, then writes 870 KB with no backup and `except: pass`. | **MITIGATED — E13.** Routing matrix routed through `StateManager`; `_clear_all_routes_in_state` and `_apply_routes_to_state` restricted to ids in `BotManager._bots`. The write-side identity check is **scoped explicitly to memory-sourced records only** (§2.8 step 3), so a malformed record on disk can never freeze the fleet. |
| **24** | OPERATIONAL / medium | **No single-instance guard.** Two processes each with a 60s timer and its own ledger make every bot's lots oscillate between live values and a boot-time snapshot on a 60s beat. Also exposes an unspecified case: a carry id absent from the file. | **MITIGATED — E15 + §4a below.** Exclusive OS handle on `~/.acervator/bot_state.lock` acquired at `StateManager` construction; a second instance is refused with a dialog rather than becoming a silent second writer. **Missing-carry-id case specified explicitly:** with §2.2's RAM payload the id can only be missing if `unregister`/`forget` popped it, in which case it is popped from `_boot_state_records` in the same operation; any residual mismatch logs **WARNING**, drops the id from the ledger, **does NOT refuse**, and surfaces in the panel as *"carry source vanished"* so it is never confused with a successful carry. |

### 4a. Explicitly ACCEPTED risks

| Accepted risk | Reason |
|---|---|
| **A carried record's `stats` block goes stale for as long as it is carried.** | Restore applies stats through a permissive `hasattr` loop, and 8 of 34 fields refresh from the exchange on start. The 6 unrecoverable fields travel with the record, so carrying is strictly better than dropping. Cherry-picking would create a second merge granularity — the exact thing §2.1 forbids. |
| **A carried record can contain `current_holdings` (pre-MEM-254) or any other obsolete key, carried verbatim forever.** | `import_scrumming_state` reads only named keys via `.get()`, so a stale key is **inert** on the way back in. Stripping it would sound safer but opens the door to "just one more" key edit and destroys the absoluteness of the rule. |
| **`main_lots` sub-key loss (§2.6, one level deep) accepts the memory record after writing a drop sidecar, rather than freezing.** | Sub-keys can only ever be added by foreign writers. Freezing a bot's real trading state on disk to preserve a foreign key is the wrong trade, and after E16 the only known such key round-trips. Written down under M15 so a future implementer does not silently invert it. |
| **A record carried across many sessions is never automatically expired.** | Any automatic expiry is a silent delete. Immortal carry is an operator-visible cost (the panel + `carry_count`); silent deletion is not. **Escalation policy is operator decision D3** (§9). |
| **`bot_state.dropped.*`, `.malformed.*`, `.forgotten.*`, `.preflight.*` sidecars accumulate on disk with no automatic cleanup.** | The live file is 870 KB. Automatic cleanup of forensic copies of destroyed cost basis is precisely the class of silent delete this cascade exists to stop. Retention is **operator decision D6** (§9). |
| **`extractor_state` carry has zero production coverage.** | No extractor record exists in the live file. Mitigated by the rule's refusal to consult mode on carry (§2.9) and by synthetic test T-08, but the risk of an unknown extractor-specific interaction is accepted rather than eliminated. |
| **Adding `BotState.QUARANTINED` is a new enum value visible to GUI code.** | Verified: no exhaustive `match`/dict-over-all-`BotState` consumer exists in `src/`. All consumers test membership in explicit tuples. A new value is inert to every one of them. Regression pinned by test T-16. |

---

## 5. The exact edits

Three PRs. **PR-0 and PR-1 change no write semantics of `bot_state.json` bot records.** Only PR-2 arms the writer.

### PR-0 — Phase 0 instrumentation (log-only; ships first; runs one full operator session)

| ID | File | Function / anchor | Change |
|---|---|---|---|
| **E1** | `src/core/state_manager.py` | **new** `preflight_snapshot() -> tuple[Path|None, Path|None]` | Copy `bot_state.json` → `bot_state.preflight.<ISO-ts>.json` and `bot_state.backup.json` → `bot_state.backup.preflight.<ISO-ts>.json`. Read-only on existing files; creates new ones. Log INFO with both paths and byte counts. Never raises — returns `(None, None)` and logs ERROR on failure. |
| **E2** | `main.py` | after `state_mgr = StateManager(...)` at `:680`, **before** `has_saved_state()` at `:720` and before `save_timer.start(60000)` at `:1035` | Call `state_mgr.preflight_snapshot()`; log the returned paths into the status log. **This is the M11 "back up before the first destructive run" obligation and must be the first thing that touches the file.** |
| **E3** | `src/core/state_manager.py` | **new** `Probe` enum + `probe() -> Probe`; rewrite `has_saved_state()` (`:192-201`) | `probe()` returns `NO_FILE` (not `exists()` or `st_size == 0`), `UNREADABLE` (`OSError`/`PermissionError`/`JSONDecodeError`), `EMPTY` (parses, `len(bots) == 0`), `HAS_BOTS`. `has_saved_state()` becomes `return self.probe() is Probe.HAS_BOTS`. The bare `except Exception: return False` is deleted. Also: docstring `:37` `"1.9.4"` → `"1.9.5"`; **delete the `phantom_config` line at `:45`.** |
| **E4** | `src/core/state_manager.py` | `save_state`, before the tmp dump at `:103` | **Log-only prune detector.** Read the current file's `bots` keys (best-effort; any failure logs DEBUG and is ignored — Phase 0 must not change behaviour). If `on_disk_ids - incoming_ids` is non-empty, `logger.warning("C01 PRUNE DETECTED: %d record(s) would be deleted by this save: %s", n, sorted(ids))`. **No behaviour change — the save proceeds exactly as today.** |
| **E5** | `src/core/state_manager.py` | **new** `diff_primary_vs_backup() -> list[str]`; called from `main.py` right after E2 | Return `bot_id`s present in `bot_state.backup.json` but absent from `bot_state.json`. Log WARNING per id with its `len(main_lots)`/`len(fold_tranches)`. **The only detector that can surface pre-existing C01 damage.** |
| **E6** | `src/trading/bot_container.py` | `BotManager.__init__`; `restore_bots_from_state` (`:2418-2808`); `unregister` (`:2098`) | Add `self._restore_ledger: dict[str, dict] = {}`, `self._boot_state_records: dict[str, dict] = {}`, `self._save_degraded: dict[str, dict] = {}`, `self._restore_completed: bool = False`. At the top of `restore_bots_from_state`, `self._boot_state_records = copy.deepcopy(bots_data)` and `self._restore_ledger.clear()`. Add a ledger write at **all eight** exits (§1.3) — including the **silent** one at `:2436`, which also gains an ERROR log naming the missing `exchange_id`. At `:2802`, capture `_ok, _why = self.register(bot)`; on refusal write ledger entry and **do not** `restored.append(bid)`. At the end, set `self._restore_completed = True`, log the full ledger, release capital reservations for every Class B id, and call `prune_expired()` once. In `unregister`, pop `bot_id` from `_restore_ledger`, `_boot_state_records` and `_save_degraded`. |
| **E7** | `src/trading/bot_container.py` | `get_full_state` `except` at `:1383-1386`; same pattern for extractor at `:1401` | `logger.warning` → `logger.error` (a bot whose state cannot be exported is not a warning-level condition), and set `self._state_export_failed = True` (cleared to `False` on a successful export). |
| **E8** | `src/trading/bot_container.py` | `:2757-2771` (extractor) and `:2775-2790` (scrumming) | Set `bot._state_import_failed = False` before the `try`; set `bot._state_import_failed = True` in **both** `except` branches. **Symmetric — do not fix only the scrumming half.** Raise both logs WARNING → ERROR and change the misleading `"(bot will start fresh)"` text to `"(persisted record will be carried; bot QUARANTINED this session)"` in PR-1, `"(persisted record NOT overwritten this session)"` in PR-0. |
| **E9** | `main.py` | `:720-729` | After `restore_bots_from_state`, compare `len(saved.get("bots", {}))` against **`len(bot_manager._bots)`** — the fact, not `len(restored)`, which exit 8 inflates. On mismatch, log WARNING with the ledger contents and push a line to `crypto_window._status_log`. Also fix the `if restored:` guard at `:726` so a restore that recovers **zero** bots still says so on screen. |
| **E10** | `src/trading/bot_container.py` | `save_all_state` (`:2325-2355`) | **Dry-run reporting only.** Compute what Phase 2 *would* carry and *would* drop, and log it at INFO with a stable, greppable prefix `C01-DRYRUN`. **`save_state` is still called with today's exact arguments.** |
| **E11** | `src/trading/scrumming_bot.py` | top of `import_scrumming_state` (`:3484`) | Log-only forward-version WARNING: if `data.get("_format_version", 0) > RUNNING_FORMAT_VERSION`, `logger.warning("bot %s persisted _format_version=%s exceeds running %s — this build cannot reason about that record", ...)`. **Import proceeds unchanged in Phase 0.** |

### PR-1 — pre-arm hardening (M11 prerequisite; no carry yet)

| ID | File | Function / anchor | Change |
|---|---|---|---|
| **E13** | `src/gui/bot_visualizer.py` | `_save_bot_state_dict` (`:2549-2564`), `_load_bot_state_dict` (`:2543-2547`), `_apply_routes_to_state` (`:2566-2610`), `_clear_all_routes_in_state` (`:2612-2634`) | **Delete `_save_bot_state_dict` entirely.** Route the routing-matrix save through a new `StateManager.save_raw_state(state)` (backup + atomic write + unique tmp + `bot_count` maintenance + `version` preservation, and it **raises** rather than `except: pass`). `_load_bot_state_dict` uses `load_state_strict()` (E24) and **excludes ids in `carried_forward`**. Both mutators restrict their id loop to `set(bots) & set(BotManager._bots)`, so no GUI path can create a stub (`setdefault(bid, {})`) or edit a carried record. |
| **E14** | `src/core/state_manager.py` | `:101`, `:106-108` | tmp path → `self._dir / f"bot_state.{os.getpid()}.tmp"` (removes the collision with `bot_visualizer.py:2558`, which E13 deletes anyway — belt and braces). Backup copy becomes atomic: write to `bot_state.backup.<pid>.tmp`, then `replace()` onto `bot_state.backup.json`. |
| **E15** | `src/core/state_manager.py` | `__init__` (`:54-58`) | Acquire an exclusive OS handle on `~/.acervator/bot_state.lock` (Windows: `msvcrt.locking` / `O_EXCL` sentinel with pid + heartbeat; POSIX: `fcntl.flock`). On failure, raise `StateLockedError`. `main.py` catches it and shows a modal *"Another Acervator instance owns the state file"* and exits. **Tests must pass `config_dir=tmp_path`, which gives each test its own lock.** |
| **E16** | `src/trading/scrumming_bot.py` | `export_scrumming_state` (`:3387-3482`), `import_scrumming_state` (`:3484+`) | Add `"smart_wire_routes": list(getattr(self, "_smart_wire_routes", []) or [])` to the export (making it a **32-key** dict, `_format_version` → `8`) and the matching `.get()` on import. Closes the inverted-survival asymmetry (break 8). |
| **E17** | `src/trading/bot_container.py`, `src/trading/smart_wire.py`, `src/gui/bot_live_settings.py` | `BotState` (`:45-52`); `BotContainer.start` (`:1094`); `start_all` (`:2852-2856`); `SmartWireManager` | **Quarantine machinery.** Add `BotState.QUARANTINED = "quarantined"`. Add `BotContainer._quarantined = False` and a refusal at the very top of `start()` (before the `RUNNING/STARTING` check) that logs ERROR and emits `bot.start_refused`. In `start_all`, add `and not getattr(b, "_quarantined", False)` to the `eligible` comprehension **outside** the caller-supplied `eligible_filter`. Add `SmartWireManager.suspend_bot(bot_id)` popping `_bot_refs` only (never `_wires`, never `_ledgers`) and `resume_bot(bot_id)`. Gate `reset_circuit_breaker`, `self_destruct`, manual fire and the live-settings apply path on `_quarantined`. |
| **E18** | `src/trading/scrumming_bot.py` | `:1646` | `_scrum_routed_total += _routed` executes **only** when `_apply_result.get("applied")` is truthy. Today a rejected `apply_wire_income` still debits the source. Independent of C01; pinned by its own test. |
| **E19** | `tools/purge_orphan_reservations.py` (`:57-66`), `tools/quarantine_sim_contamination.py` (`:61`) | `_load_live_bot_ids`, `_is_contaminated` | Live set = `set(state["bots"]) - set(state.get("carried_forward", {}))`. Both tools already support `--dry-run`; no other change. |
| **E23** | `src/trading/bot_container.py` | `:2630-2639` | Rewrite the remediation text: stop telling the operator to hand-edit a live file; point at the **"Not loaded"** panel's repair/forget actions. |
| **E24** | `src/core/state_manager.py` | `load_state` (`:130-149`); **new** `load_state_strict()` | `load_state` returns provenance (`_source: "primary" | "backup"`). `load_state_strict()` never falls back to the backup and raises on corruption. **Any caller whose next act is a write must use `load_state_strict()`.** |
| **E25** | `src/trading/scrumming_bot.py` | `import_scrumming_state` | Promote E11's log-only forward-version WARNING to a **refusal** (`raise ValueError`), which routes the bot to exit 7 → Class C → carried + quarantined. |

### PR-2 — arm the writer

| ID | File | Function / anchor | Change |
|---|---|---|---|
| **E20** | `src/core/state_manager.py` | `save_state` (`:60-128`) | New signature (§2.7). Implement §2.8 **in the stated order**. `version` → `"1.10.0"`; docstring updated to match and to document the merge rule by reference to this file. `bot_count = len(out)`. Emit `carried_forward`. Per-record identity quarantine → `bot_state.malformed.<ts>.json`. Drop sidecar → `bot_state.dropped.<ts>.json`. Backup rolled only on superset. Returns `bool`. |
| **E21** | `src/trading/bot_container.py` | `save_all_state` (`:2325-2355`) | Classify every id into A/B/C/D per §2.3. Assert every id in `states` is a key of `self._bots`. Apply the §2.6 key-set guard against `_last_written_records`. Build `carry_forward_records` from `_boot_state_records` (deep copy) and `carried_forward_meta` from `_restore_ledger` + `_save_degraded` (with the denormalized summary fields). Pass `restore_completed=self._restore_completed`. On a `False` return, log ERROR and raise the GUI banner. |
| **E22** | `src/gui/main_window.py` (+ new `src/gui/not_loaded_panel.py`) | new panel | **"Not loaded"** panel driven by `carried_forward`. Rows render `symbol / exchange / lots / tranches / anchor / standing_surplus / cb_hard_tripped`, **never masked by Privacy Mode.** Actions: `forget_unrestored(bot_id)` (typed-hash confirm, sidecar-first, refuses on `cb_hard_tripped: true` without a typed hash, forces an immediate save) and `adopt_memory(bot_id)` for Class C/D (confirm names exactly what is lost: *"N lots, M tranches, $X standing surplus"*). Plus the persistent **"State persistence is OFF"** banner for §2.8 step 1 refusals. |

---

## 6. Test plan

**Hard constraint, non-negotiable:** every test constructs `StateManager(config_dir=tmp_path)`. `tests/conftest.py:234` treats *modification* of a pre-existing file as a **print, not a failure**, when a live Acervator process is running — and the measured normal case is that the operator's app **is** running. A test that constructed a bare `StateManager()` would rewrite `~/.acervator/bot_state.json` and the suite would stay **green** while destroying live trading state. There is no second line of defence here.

Corollary: no test may import a path that constructs `StateManager()` bare — `bot_visualizer.py:915`, `:2380`, `:2545`. E13 removes `:2545`; the other two must be given an injectable `state_manager` before any test reaches them.

All fixtures are **synthetic state dicts** built in-test. New file: `tests/test_c01_state_merge.py`. Support fakes (`FakeBot` with `get_full_state`, `FakeManager` with `_bots`/`_restore_ledger`) live in the same file — no import of live GUI modules.

### 6.1 Tests that MUST be observed RED first (M4)

The suite is green today **with the defect present**, and there is **zero** existing behavioural coverage of `state_manager.py` (measured: `grep` over `tests/` for `core.state_manager`, `save_state`, `get_full_state`, `restore_bots_from_state`, `import_scrumming_state` returns **zero** hits). A wrong fix would keep the suite green. Every test below is written and **run against the un-fixed tree first**; the plan is blocked until each is observed failing for the stated reason.

| ID | Test | Must go RED because (pre-fix behaviour) | Turns GREEN at |
|---|---|---|---|
| **T-01** | `test_save_state_does_not_delete_absent_bot` — save `{A,B}`, then save `[A]` with `carry_forward_records={"B": rec_B}`; assert `loaded["bots"]["B"] == rec_B` byte-for-byte. | `save_state` takes no such parameter → `TypeError`; without it, `B` is deleted. | PR-2 / E20 |
| **T-02** | `test_carried_record_is_byte_identical` — assert `json.dumps(loaded["bots"]["B"], sort_keys=True) == json.dumps(rec_B, sort_keys=True)`, including a nonsense key `"__operator_note__"` and a pre-MEM-254 `current_holdings`. | no carry exists. | E20 |
| **T-03** | `test_class_A_empty_main_lots_overwrites_populated_disk` — disk has 56 lots; memory record for the same id has `main_lots: []`; assert the written record has `[]`. | passes today by accident; **must stay green** — this is the anti-deep-merge pin. | already green; **regression pin** |
| **T-04** | `test_class_A_false_cb_hard_tripped_overwrites_true` — same shape for `cb_hard_tripped`. | as T-03 — anti-preserve-if-truthy pin. | already green; **regression pin** |
| **T-05** | `test_unregistered_bot_is_dropped_not_carried` — id in neither registry → absent from the written file. Encodes the delete path. | passes today; **must stay green** after E20. | regression pin |
| **T-06** | `test_restore_ledger_records_all_eight_exits` — eight synthetic state dicts, one per exit of §1.3; assert `mgr._restore_ledger` has the id with the right `reason`. | `_restore_ledger` does not exist → `AttributeError`. | PR-0 / E6 |
| **T-07** | `test_silent_skip_2436_is_no_longer_silent` — record with no `exchange_id`; assert an ERROR is logged **and** a ledger entry exists. | no log at any level. | E6 |
| **T-08** | `test_extractor_import_failure_sets_state_import_failed` — symmetric to the scrumming case. | `_state_import_failed` does not exist. | E8 |
| **T-09** | `test_scrumming_import_failure_sets_flag_and_quarantines` — `import_scrumming_state` raises; assert `bot._state_import_failed is True`, `bot._quarantined is True`, `bot.state is BotState.QUARANTINED`, and the bot **is** in `_bots`. | flag and enum member do not exist. | E8, E17 |
| **T-10** | `test_register_refusal_is_ledgered_and_not_counted_as_restored` — fake registry refusing; assert `bid not in restored`, `bid in _restore_ledger`, `bid not in _bots`. | `restored.append(bid)` runs unconditionally at `:2803` → `bid in restored`. | E6 |
| **T-11** | `test_get_full_state_missing_scrumming_state_is_class_D` — bot whose `export_scrumming_state` raises; assert `save_all_state` carries the last persisted record, not the truncated one, and `_save_degraded` names it. | `_save_degraded` does not exist; today the truncated record is written. | E7, E21 |
| **T-12** | `test_top_level_key_loss_never_overwrites` — memory record missing `scrumming_state`; assert the last persisted record is written and an ERROR is logged. | no guard exists. | §2.6 / E21 |
| **T-13** | `test_smart_wire_routes_round_trip` — set routes, export, import, assert equal; then assert a Class A save does **not** delete them. | `smart_wire_routes` absent from the 31-key export → lost. | E16 |
| **T-14** | `test_start_all_with_no_filter_excludes_quarantined` — call `await mgr.start_all()` with **no** `eligible_filter` against a quarantined bot; assert it is not started. | `BotState.QUARANTINED` and `_quarantined` do not exist; today the bot is eligible. | E17 |
| **T-15** | `test_main_autorestart_comprehension_excludes_quarantined` — reproduce `main.py:1056-1060`'s literal comprehension `[b for b in mgr._bots.values() if b.state.value in ("idle","stopped")]`; assert empty. | quarantined bot is `IDLE` today → non-empty. | E17 |
| **T-16** | `test_bot_container_start_refuses_when_quarantined` — `await bot.start()` directly (the `main_window.py:6206` path); assert state unchanged and `bot.start_refused` emitted. | no gate in `start()`. | E17 |
| **T-17** | `test_quarantined_bot_is_suspended_from_wire_refs` — assert `bot_id not in mgr._smart_wire_mgr._bot_refs` **and** `mgr._smart_wire_mgr.export_wires()` still contains its wires. | `suspend_bot` does not exist; the bot stays reachable and its wires would be at risk from a naive detach. | E17 |
| **T-18** | `test_rejected_wire_income_does_not_debit_source` — `apply_wire_income` returns `{"applied": False}`; assert `_scrum_routed_total` unchanged. | `:1646` increments unconditionally. | E18 |
| **T-19** | `test_refused_save_touches_neither_file` — trigger the save-before-restore refusal; assert primary **and** backup bytes and mtimes are unchanged. | no refusal path; backup at `:108` runs upstream of everything. | E20, §2.8 |
| **T-20** | `test_backup_not_rolled_when_a_record_is_dropped` — save `{A,B}`, then save `[A]` with no carry; assert `backup` still contains `B`. | backup roll is unconditional at `:106-108`. | E20 |
| **T-21** | `test_dropped_record_written_to_sidecar` — same setup; assert `bot_state.dropped.*.json` exists in `tmp_path` and contains B's full record. | no sidecar. | E20 |
| **T-22** | `test_malformed_identity_quarantines_one_record_and_writes_the_rest` — 3 records, one with `bot_id: ""`; assert the other 2 **are** written, the bad one lands in `bot_state.malformed.*.json` and in `carried_forward`. | today it is silently dropped at `:96-97`; a naive abort-based fix would write nothing (strict regression). | E20 |
| **T-23** | `test_bot_count_equals_written_bots_after_carry` — assert `loaded["bot_count"] == len(loaded["bots"])`. | `:87` writes `len(bots)` → under-counts by the carried count. | E20 |
| **T-24** | `test_probe_distinguishes_unreadable_from_absent` — write garbage bytes; assert `probe() is Probe.UNREADABLE` and `has_saved_state() is False` but the guard treats it as PRESENT. | `has_saved_state()` swallows and returns `False` with no way to tell why. | E3 |
| **T-25** | `test_save_refused_before_restore_completes` — `_restore_completed = False`, file with bots on disk; assert `save_state` returns `False` and writes nothing. | no such guard; today the Reset-all-errors button can wipe the file. | E20, E21 |
| **T-26** | `test_forward_format_version_refuses_import` — `_format_version` = running+1; assert `import_scrumming_state` raises and the bot lands Class C. | no version gate anywhere. | E25 |
| **T-27** | `test_forget_writes_sidecar_before_popping_ledger` — assert `bot_state.forgotten.<id>.*.json` exists **and** its content matches, before `_restore_ledger` loses the key. | `forget_unrestored` does not exist. | E22 |
| **T-28** | `test_forget_refuses_on_tripped_breaker_without_typed_hash` | as T-27. | E22 |
| **T-29** | `test_unregister_pops_all_three_registries` — delete a carried bot; assert next save omits it. **The delete-still-works pin.** | `_restore_ledger` does not exist. | E6 |
| **T-30** | `test_preflight_snapshot_copies_both_files_and_mutates_neither` — assert both sidecars exist and both sources' bytes/mtimes unchanged. | `preflight_snapshot` does not exist. | E1 |
| **T-31** | `test_purge_orphan_reservations_excludes_carried_forward` — synthetic state with a carried id; assert the tool classifies it as **not** live. | tool reads `bots.keys()` → carried id looks live. | E19 |
| **T-32** | `test_routing_matrix_cannot_touch_carried_or_unknown_ids` — `_apply_routes_to_state` with a carried id; assert no record is created or mutated. | `bots.setdefault(bid, {})` creates a stub today. | E13 |
| **T-33** | `test_no_test_constructs_bare_state_manager` — fitness test: grep `tests/` for `StateManager(` not followed by `config_dir`. | new pin; RED only if someone writes an unsafe test. | ships with PR-0 |

### 6.2 Regression pins that must stay green

- `tests/test_fleet_sim_infrastructure.py:216` and `tests/test_stone_tablets_fetcher.py:171` — the `bots` shape contract. **These will not warn you**; they write their own fixtures. T-34: re-run the real writer's output through `load_bot_configs_from_state` and `TargetAssetDiscovery`.
- `tests/test_singleton_isolation.py:60` — C01 must not introduce `StateManager` into any `src/gui/simulator_tab/` module.
- `tests/test_stack_mode_schema.py:150-160` — the four `'"stack_mode": cfg.get('`-style substrings in `bot_container.py` must survive E6's edits to the same region.
- `tests/test_suite_integrity.py:45` — `MIN_TEST_FILES = 70`, `MIN_TEST_FUNCTIONS = 1100`. Floors are minimums; adding files is free.

### 6.3 Tests explicitly NOT written

- Nothing exercises `~/.acervator`. There is no "integration test against the live file" in this plan, at any phase.
- The archived `test_bot_restoration_dispatch.py:320` / `:344` are **not** resurrected. They assert `restored_ids == []` and `"grid-1" not in mgr._bots` as the *success* condition — they pin the skip as correct while the record is being deleted. T-06 supersedes them by asserting the ledger entry **and** the record's survival.

---

## 7. M11 protocol — backup, dry-run, arm

### Phase 0 — instrument, one full operator session, zero write-behaviour change

**Ship:** PR-0 (E1–E11) plus the tests in §6.1 that turn green at PR-0.

**What the operator runs:**

1. Close Acervator completely. Confirm no `acervator` process remains (Task Manager, or `Get-Process *acervator*`).
2. Launch the Phase-0 build normally. **Do nothing else for the first 90 seconds.**
3. Immediately confirm in `~/.acervator/` that these two files now exist:
   ```
   bot_state.preflight.<timestamp>.json
   bot_state.backup.preflight.<timestamp>.json
   ```
   **Copy both to a location outside `~/.acervator` before continuing.** If they do not exist, stop — the build is not safe to run, close it and report.
4. Use the platform normally for one full session: start bots, let scrums and folds happen, use the routing matrix, quit cleanly.
5. At the end of the session, collect from `~/.acervator_logs/`:
   ```
   grep -E "C01-DRYRUN|C01 PRUNE DETECTED|restore ledger|preflight|_format_version exceeds" system.log
   ```

**What the output means:**

| Observation | Meaning | Action |
|---|---|---|
| `preflight snapshot written: <2 paths, N bytes>` at the very top of the log | M11 satisfied. | proceed |
| `diff_primary_vs_backup: 0 id(s) in backup absent from primary` | No pre-existing C01 damage. | proceed |
| `diff_primary_vs_backup: N id(s) ...` | **Pre-existing loss found.** The preflight backup copy holds records the primary does not. | **STOP.** Recover those records by hand from the preflight copy before arming anything. |
| `restore ledger: {} (0 entries)` for every launch of the session | No bot was skipped this session. | proceed — but see the caveat below |
| `restore ledger: {<id>: {reason: ...}}` | A bot **was** skipped. The dry-run lines will name it. | proceed; this is the case the fix exists for |
| `C01-DRYRUN would_carry=[] would_drop=[]` on every tick | Nothing would change if the writer were armed. | **This is the "safe to arm" signal.** |
| `C01-DRYRUN would_carry=[X] would_drop=[]` and `X` is the same id all session | The fix would carry exactly one skipped record and drop nothing. | **Safe to arm.** |
| `C01-DRYRUN would_drop=[Y]` where `Y` was **not** deleted by the operator this session | **The classification is wrong.** | **STOP.** Do not arm. Report the id and the ledger. |
| `C01 PRUNE DETECTED: N record(s) would be deleted by this save` | The unfixed writer is actively pruning, right now. | Expected if the ledger is non-empty; **alarming if the ledger is empty** — report. |
| `persisted _format_version=N exceeds running M` | The file was written by a newer build. | **STOP.** Do not arm on a forward-version file. |
| Any `save_all_state` refusal or GUI banner | Not possible in Phase 0 (no refusal paths ship until PR-2). If seen, report. | STOP |

**Caveat, stated plainly:** an empty ledger for a whole session does **not** prove the fix is unnecessary — it proves nothing was skipped *that session*. The dry-run's job is to prove the **classification** is correct when it does fire, not to prove the defect is rare.

**Phase 0 exit requires:** at least one launch in which the ledger was **deliberately** made non-empty by the operator on a **copy** of the state file in a scratch directory (see §8 G-06), so `would_carry` is observed non-empty at least once.

### Phase 1 — pre-arm hardening

**Ship:** PR-1 (E13–E19, E23–E25). Still no carry. The two prerequisites M11 names explicitly:

- The **second, un-backed-up writer** at `bot_visualizer.py:2549` is deleted and routed through `StateManager` (E13). Without this, the routing-matrix save re-prunes or rolls back everything the carry protects.
- **Backup-before-overwrite discipline** now covers every writer of the file (E13, E14).

Run one operator session on PR-1 with the same dry-run collection as Phase 0. The added observation is that the routing matrix still works: connect a wire, disconnect all, restart, confirm the canvas repaints.

### Phase 2 — arm

**Ship:** PR-2 (E20–E22), **only** after §8's gates are green and §9's decisions are answered.

**What the operator runs on the first armed launch:**

1. Close Acervator. Confirm no process remains.
2. Manually copy `~/.acervator/bot_state.json` and `bot_state.backup.json` to an external location. (The build does this itself via E1, but this one is by hand.)
3. Launch. Wait 90 seconds. Confirm in the log:
   ```
   Bot state saved: 35 bots (35 live, 0 carried, 0 dropped)
   ```
4. Confirm `~/.acervator/bot_state.json` has `"version": "1.10.0"`, `"bot_count": 35`, and `"carried_forward": {}`.
5. **First-armed-session save cadence is operator decision D7** (§9). Default recommendation: arm the timer normally — the design has no read on the save path and no abort-on-IO, so the "suspend the timer while the ledger is non-empty" caution is no longer buying anything, and suspending it would cost the session's lots on a crash.

---

## 8. Exit gates

Each gate is a **measurement**, not an opinion (M3). None may be satisfied by inspection or by argument.

| ID | Gate | Measurement | Pass condition |
|---|---|---|---|
| **G-01** | Every failing-first test was observed RED | Run each §6.1 test against the pre-fix tree; capture output. | Every test marked "must go RED" is observed failing, **for the stated reason** (not a collection error, not an import error). Paste the failure lines into the cascade log. |
| **G-02** | Suite green | `python -m pytest -q` | `0 failed`, and the count is **≥ 1185 + (number of new tests)**. |
| **G-03** | Release readiness | `python tools/check_release_readiness.py` | Output contains `[OK] Release-ready (vX.Y.Z, N tests)`. **No version bump, no CHANGELOG entry, no banner change before this line is seen.** |
| **G-04** | No test touched the live tree | `tests/conftest.py` live-tree guard output + manual `Get-Item ~/.acervator/bot_state.json \| Select LastWriteTime` before and after the suite | mtime **unchanged**. The conftest print is not sufficient evidence — the guard downgrades modification to a print when a live process is running. |
| **G-05** | No bare `StateManager()` in tests | T-33 | green |
| **G-06** | Classification verified on a real state file, off the live tree | Copy `~/.acervator/bot_state.json` to a scratch dir. Delete `exchange_id` from exactly one record. Run a harness that constructs `StateManager(config_dir=<scratch>)` + a `BotManager`, restores, and calls the armed `save_all_state`. | The scratch file after the save contains **all 35** records; the mutated one is **byte-identical** to its pre-run bytes; `carried_forward` has exactly that one id; `bot_count == 35`. |
| **G-07** | Two-save annihilation is closed | Same harness, run the save **three** times. | The carried record survives all three saves in **both** primary and backup. |
| **G-08** | Deliberate delete still works | Same harness: restore cleanly, `unregister("<id>")`, save twice. | The id is absent from the file after save 1 and stays absent. `bot_state.dropped.*.json` contains its full record. `backup` still holds it after save 1 (superset guard) and after save 2 (still not a superset). |
| **G-09** | Quarantine holds against the real auto-start comprehension | T-14, T-15, T-16, T-17 | all green |
| **G-10** | Refusal touches nothing | T-19 | both files' bytes **and** mtimes unchanged |
| **G-11** | Phase-0 dry-run session complete | §7 Phase 0 log collection | `would_drop` empty on every tick except operator-initiated deletes; `would_carry` observed non-empty at least once (via G-06's mutated copy if the live session produced no skips); no `_format_version exceeds` line |
| **G-12** | Second writer eliminated | `grep -rn "_save_bot_state_dict" src/` | **zero hits** |
| **G-13** | tmp-path collision eliminated | `grep -rn 'with_suffix(".tmp")' src/` | **zero hits**; the only tmp construction is the pid-qualified one in `state_manager.py` |
| **G-14** | Consumer contract intact | T-34 + `tests/test_fleet_sim_infrastructure.py` + `tests/test_stone_tablets_fetcher.py` | green, and T-34 proves the **real writer's** output loads |
| **G-15** | Sim isolation intact | `tests/test_singleton_isolation.py` | green |
| **G-16** | No emitter added without a contract entry | `python tools/emit_contracts.py --check` (per the tracked-emitter standard) | green — `bot.start_refused` and any new events are registered |
| **G-17** | Operator decisions recorded | §9 table | every row has a written answer, in the operator's own words, in the cascade log |

---

## 9. Operator decisions required

**No code from PR-2 may be written until every row below has an answer.** Each row states the question, the trade, and my recommendation. The recommendation is not the decision.

### D1 — **Delete semantics: hard removal vs tombstone** (the load-bearing one)

**Question.** When a `bot_id` exists on disk but in neither `_bots` nor `_restore_ledger`, should it be **hard-removed** from the file (positive-carry design, §2.3), or should removal require an explicit **tombstone** written to the file, with every other absent bot preserved forever?

**The trade.**

| | Hard removal (positive carry) — recommended | Tombstone |
|---|---|---|
| What can go wrong | A record is **dropped that should have been carried** — because the boot that observed the skip is not the boot that saves. | A record is **resurrected that should have been deleted** — because the tombstone write did not land. |
| Bounded by | What *this boot's* restore actually observed. Finite, enumerable, logged. | Nothing. The tombstone list must be retained **forever** with no principled expiry, and the file accretes ids indefinitely. |
| Failure visibility | Immediate: `carried_forward` panel, drop sidecar, prune WARNING, backup superset guard. | Delayed and silent: the operator deletes a bot, the app is killed before the tombstone flushes, and the bot reappears weeks later with its full lot list and can be started. |
| Operator's explicit action | Honoured. `unregister()` pops all three registries; the next save omits the record. | Honoured only if a write succeeds at exactly the right moment. |
| Recovery from the failure | `bot_state.dropped.<ts>.json` holds the full record, off the one-deep ring. | Delete the bot again — but it has now been running with resurrected lots. |

**Recommendation: hard removal.** The worst case is a record dropped that would have been carried, which is *visible* and *recoverable from a sidecar*. The tombstone's worst case is a silent resurrection of a bot the operator deliberately deleted, running against ghost inventory, with no marker anywhere.

**Answer required:** ☐ hard removal  ☐ tombstone  ☐ other (specify)

### D2 — Class C release policy

May a quarantined bot be **adopted into service within the same session** via an explicit *"use memory, discard the persisted record"* confirmation naming exactly what is lost (N lots, M tranches, $X standing surplus)? Or must the operator restart the platform so the import is retried cleanly?

**Recommendation: adopt-with-confirm.** The confirm is the only path by which a genuinely corrupt persisted record ever gets cleared, and D2 is the escape hatch for break 12 (the un-clearable circuit breaker). But it is the operator's call, because it is also the only in-session path that destroys MEM-171 data.

**Answer required:** ☐ adopt-with-confirm  ☐ restart-only

### D3 — Carry expiry / escalation

Should a record carried for N consecutive saves (or N days) escalate — banner, modal, refusal to launch — or stay carried indefinitely with only the "Not loaded" panel?

**Recommendation: no automatic expiry, ever** (any automatic expiry is a silent delete). Escalate **visibility** only: after 3 consecutive sessions carrying the same id, promote the panel to a launch-time modal. I will not choose an expiry; the alternative (immortal carry) is also an operator-visible cost.

**Answer required:** ☐ visibility escalation only  ☐ visibility escalation + threshold N = ____  ☐ no escalation

### D4 — Second writer disposition

Delete `bot_visualizer._save_bot_state_dict` (`:2549`) and route the routing-matrix save through `StateManager` — **or** keep it and duplicate the backup + carry discipline in it?

**Recommendation: delete and route (E13).** It also fixes the shared `bot_state.tmp` collision and the `except/pass` silence. But it **changes GUI routing-matrix save behaviour** — a failed write will now be reported instead of swallowed — and that needs sign-off.

**Answer required:** ☐ delete and route  ☐ keep and duplicate

### D5 — Corrupt-primary launch policy

Today a corrupt `bot_state.json` launches the platform with **zero bots** and an untouched, perfectly good backup beside it, because `has_saved_state()` swallows the exception. Should launch instead **HALT** with a loud prompt offering backup recovery?

**Recommendation: HALT with a prompt.** This is a second, independent defect in the same safety net, and it is what defeats the save-before-restore guard (break 7). It changes launch behaviour, so it needs an explicit decision rather than being folded into C01.

**Answer required:** ☐ HALT + recovery prompt  ☐ launch empty (status quo) + banner  ☐ other

### D6 — Sidecar retention

`bot_state.preflight.*`, `.dropped.*`, `.malformed.*`, `.forgotten.*` accumulate in `~/.acervator/` with no automatic cleanup. Keep forever (recommended — they are forensic copies of destroyed cost basis, and automatic cleanup is exactly the silent delete this cascade exists to stop), or cap at N per kind?

**Answer required:** ☐ keep forever  ☐ cap at N = ____ per kind  ☐ move to a subdirectory `~/.acervator/forensics/`

### D7 — First armed session save cadence

During the first session after the writer is armed: suspend the 60-second timer and the shutdown save while the ledger is non-empty (maximum caution, at the cost of losing that session's stats/lots on a crash), or arm normally?

**Recommendation: arm normally.** The RAM-held carry payload (§2.2) removes the read from the save path, so the abort-storm risk that motivated the caution no longer exists; suspending the timer would reintroduce rejected alternative §3.7 on purpose.

**Answer required:** ☐ arm normally  ☐ suspend while ledger non-empty

### D8 — Carried-bot repair affordance

Should the "Not loaded" panel also offer **"repair and load"** — edit the persisted config in place (e.g. supply the missing `exchange_id` for the `:2436` skip) and retry the restore — or is forget-only sufficient for now?

**Recommendation: forget-only in PR-2; repair in a follow-on cascade.** Repair is the thing `bot_container.py:2633-2638` already tells the operator to do by hand, and E23 rewrites that text to point at the panel — so shipping the panel without repair leaves the text pointing at an action that does not exist yet. Either ship repair, or leave the remediation text pointing at the log until it does.

**Answer required:** ☐ forget-only (and keep the old remediation text)  ☐ ship repair in PR-2  ☐ forget-only + reword E23 to say "repair coming"

---

## Appendix A — line-number corrections against the cascade brief

| Brief said | Verified | Note |
|---|---|---|
| 60s timer at `main.py:985` | `main.py:1029-1035` | ~45 lines stale |
| "one save trigger" | **three**: `main.py:1031` (timer), `main.py:1190` (shutdown), `main_window.py:5525` (Reset-all-errors, `except/pass`) | shutdown-save is the nastier one — an operator who sees the ERROR and closes the app to protect their state triggers the destructive write on the way out |
| "Four skip paths" | **five `continue`s**: `:2436`, `:2459`, `:2640`, `:2731`, `:2738` | `:2719-2731` (the defensive `else`) was not enumerated; it is unreachable today but goes live the day a new `BotMode` is added — i.e. exactly when a new bot type's state is at risk |
| ":2731 no construction branch" | correct, and it is `continue` at `:2731` | |
| "two non-skipping import failures" | correct: `:2768-2771` (extractor) and `:2787-2790` (scrumming) | the brief named only the scrumming one in its prose |
| seven ledger exits | **eight** — `register()` refusal at `:2007` via `:2802` is the eighth | see §4 break 1 |
| `save_state` version `1.9.5` | correct at `:84`; docstring at `:37` says `1.9.4` | |

## Appendix B — files touched, by PR

```
PR-0  main.py
      src/core/state_manager.py
      src/trading/bot_container.py
      src/trading/scrumming_bot.py
      tests/test_c01_state_merge.py                 (new)

PR-1  src/core/state_manager.py
      src/gui/bot_visualizer.py
      src/gui/bot_live_settings.py
      src/trading/bot_container.py
      src/trading/scrumming_bot.py
      src/trading/smart_wire.py
      tools/purge_orphan_reservations.py
      tools/quarantine_sim_contamination.py
      tests/test_c01_state_merge.py
      tests/test_c01_quarantine.py                  (new)

PR-2  src/core/state_manager.py
      src/trading/bot_container.py
      src/gui/main_window.py
      src/gui/not_loaded_panel.py                   (new)
      tests/test_c01_state_merge.py
      tests/test_c01_not_loaded_panel.py            (new)
```

**Files this plan NEVER writes:** `~/.acervator/*` (except by the armed production writer in Phase 2), `~/.acervator_logs/*`, anything under the Stone Tablet archive, and any existing test file (M: never modify tests to make them pass).
