# C01 — A save never removes a bot record

Date: 2026-08-05 · Build v3.24.34 (1240 green) · Status: design, not yet built
Supersedes: the prior C01 merge design (registries, record classes, QUARANTINED state,
carry-forward semantics, forensic sidecars, eight open decisions) — withdrawn.

---

## 1. What the defect actually is

The operator's framing is the correct one: **a transient in-memory condition must not
modify long-term storage.** `bot_state.json` is not a dump of RAM, but the platform
treats it as one — `save_state()` builds `state = {... "bots": {}}`
(`src/core/state_manager.py:88`) and fills it only from the list it is handed
(`:95-98`), which is `[bot.get_full_state() for bot in self._bots.values()]`
(`src/trading/bot_container.py:2357`). So every 60 s (`main.py:1063-1068`) and at
shutdown (`main.py:1223`) the file is rebuilt from whatever is in memory right now.
The concrete case: `register()` can refuse a bot on capital over-allocation (MEM-417) —
a **transient** condition that depends on the order bots restore in and on how much USD
is free at that instant. A bot refused for that reason is absent from `_bots`, and 60
seconds later its record — per-lot cost basis included, which is *not* recoverable from
exchange fill history — is gone from disk. The bug is not "save_state does not merge";
it is that a save is allowed to delete.

## 2. The rule

**A save never removes a bot record from `bot_state.json`.** A record is removed only
when the operator explicitly deletes that bot, and that removal is written at the moment
of deletion — not inferred from a bot's absence from memory.

## 3. Why the previous design was wrong

It treated "the record is missing from memory" as a diagnosis to be classified rather
than a question that should never have been asked at save time. Once you accept that a
save may delete, you need to know *why* a bot is missing, so you need observation
registries to record it, record classes (HEALTHY / ABSENT / DEGRADED / SAVE-DEGRADED) to
grade it, a QUARANTINED bot state to park it, carry-forward semantics to decide what
survives, forensic sidecars to explain what happened, and eight operator decisions to
resolve the ambiguities. **All of that exists to answer a question the rule deletes.** If
a save never removes anything, the reason a bot is absent stops being load-bearing for
correctness. None of those constructs are in this design.

## 4. Adversarial breaks

Three lenses ran. Two returned `rule_holds_with_caveats`, one returned `rule_is_broken`.
They converged on the *same single break*, from three independent directions.

### B1 — CRITICAL. The save IS the delete mechanism today. Abolishing it disarms delete.

Deletion is not implemented anywhere. `unregister()` (`bot_container.py:2112-2152`)
releases capital, pops `_bots` at `:2138`, detaches wires — and never touches
`StateManager` (its only uses are at `:2355`, `:2406`, `:2465`, all save/load).
`StateManager` has no per-bot delete at all, and `clear_state()` (`:375`) has zero
production callers. The record disappears from disk purely because the next save rebuilds
`"bots"` from scratch. Under the rule it survives, and at next launch
`restore_bots_from_state` rebuilds the bot with its lots and its capital reservation.
"This cannot be undone" becomes "hidden until reboot."

**Mitigation (this is the whole fix):** add `StateManager.delete_bot(bot_id)` — read the
file, `state["bots"].pop(bot_id, None)`, drop matching `smart_wire_ledgers` rows and any
`smart_wires` naming that id, write through the existing atomic tmp+replace path. Call it
from `unregister()`, guarded `if self._state_manager is not None`. One method, one call
site. Blast radius verified: `BotManager.unregister` has exactly **one** production caller
(`src/gui/main_window.py:6273`, behind the confirmation at `:6265`) and two test call
sites (`tests/test_c01_restore_ledger.py`). *(The `.PRIVACY_ARC_BACKUP_2026-06-14` hit is
a dead file, and `bot_container.py:1135` is `_data_pool.unregister`, a different object.)*

### B2 — HIGH. The existing PR-0 comment gives false assurance on exactly this point.

`unregister()` already pops `_restore_ledger` and `_boot_state_records` (`:2126-2127`) and
its shipped comment says this exists so carry-forward "would [not] resurrect its record on
the next save." That guard only works if carry-forward is driven by those in-memory dicts.
This design implements carry-forward as a **disk read-merge**, which consults the file, not
the ledger — so the pop is inert and a reviewer who stops at that comment ships a
permanently broken delete on the happy path.

**Mitigation:** same `delete_bot(bot_id)` — it removes by id from the file, so it is
correct under either shape. Then **rewrite the comment at `bot_container.py:2119-2127`** to
stop claiming the ledger pop protects delete. This edit is not optional; it is the one that
prevents the next reader from re-introducing the bug.

### B3 — HIGH. `detach_bot` already runs a never-remove list, and it has already rotted.

`SmartWireManager.detach_bot` (`src/trading/smart_wire.py:253-264`) pops `_bot_refs` and
`_wires` but **not** `_ledgers`. `export_ledgers` (`:329`) exports every ledger regardless,
and `import_ledgers` (`:377-381`) recreates any missing at boot — so a ledger row can never
leave. Measured on the live file: 48 `smart_wire_ledgers` rows, **13 for bot ids absent
from `bots`** (27%), real assets, two with non-zero `wired_out`, zero overlap with known
sim ids. Unnoticed for 84 days because a row is ~219 bytes. A bot record is 10.3 KB median
/ 87.5 KB max and resurrects into a trading bot — 47x to 400x the unit cost. This is the
same failure shape the rule would reproduce if the delete path misses a structure keyed by
bot id.

**Mitigation:** `self._ledgers.pop(bot_id, None)` in `detach_bot`. Before shipping, check
whether any *surviving* ledger's `provenance` dict references a dead id — if so keep the
row and mark it; do not silently drop accounting history. Cleaning the 13 existing orphans
is out of scope for this cascade (they are on the operator's live file; see §9).

### B4 — MEDIUM. A second writer bypasses the rule and can empty the file.

`src/gui/bot_visualizer.py:2549-2564` `_save_bot_state_dict` writes `bot_state.json`
**directly** — not through `StateManager`, so no backup, no `detect_prune`, no merge, and
`except Exception: pass`. Its input comes from `_load_bot_state_dict` (`:2542-2547`), which
returns `{}` whenever `load_state()` fails — and `load_state` returns `{}` on any
non-JSONDecodeError (`state_manager.py:358-360`, e.g. file locked). Then
`_apply_routes_to_state` does `state.setdefault("bots", {})` and the atomic replace writes
a file containing only the stub it just made. All 35 records gone in one write.

**This exists today and is not created by the rule** — but it is why the rule must be
worded at the *file* level, not as a property of `save_state`.

**Mitigation (cheap form):** in `_apply_routes_to_state`, return early when
`_load_bot_state_dict()` yields a dict with no `"bots"` key. An empty load is never a
legitimate basis for a write. The full fix (route the visualizer through `StateManager`) is
correct but is a separate cascade — see §9.

### B5 — LOW. Zombie stub ids. **Accepted with a one-line fix.**

`_ensure_routes` (`bot_visualizer.py:2577-2584`) does `bots.setdefault(bid, {})`, creating a
config-less record. Under merge-forever it is carried, skipped at restore ("no exchange_id"),
and carried again — self-sustaining junk that pollutes the skip-log signal. Measured: **has
not fired** — 0 config-less records, 40/40 wires resolve, 0 dangling routes.
**Mitigation:** `if bid not in bots: continue` in the add loop, matching what the remove
loop already does at `:2600-2601`. Ships because it is one line, not because it is urgent.

### B6 — LOW. A carried bot's wires are not carried. **Accepted.**

`save_state` replaces `smart_wires` / `smart_wire_ledgers` wholesale from memory
(`state_manager.py:90-92`). A preserved-but-unrestored bot is never attached to
`SmartWireManager`, so its wire rows vanish on the first save even though its `bots` record
survives. 40 wires = 2,600 bytes and are redrawable in the GUI; per-lot cost basis is not.
**Accepted** — the rule text must simply say what it protects: *the `bots` map. Wires are
rebuilt from memory.*

### B7 — LOW. Unbounded growth. **Not a break; no action.**

Measured, not argued. Retention is idempotent — restore reassigns the persisted id verbatim
(`bot_container.py:2850`), so a bot skipped 1,000 times still occupies one record; the file
is bounded by lifetime bots created, never by boots. 72% of bot bytes are `fold_tranches`
and `main_lots`, both of which are *consumed* on sell (`scrumming_bot.py:7224`, `:2094`,
`:8162-8164`) and track open inventory, not uptime. Live file: 870,552 bytes / 35 bots.
`json.dumps` of a 3x file = 15.8 ms against a 60 s timer. With B1 wired, retained ids are
restore-skips only — zero across 3,012 log files. **Growth = 0 KB/yr. Do not add pruning,
TTLs, or size caps.**

### B8 — LOW. An unrestored bot cannot be deleted from the GUI. **Accepted.**

`list_bots()` returns only `_bots.values()` (`:2335-2337`), so a skipped bot has no card and
no menu; `_on_bot_command` also gates on `get_bot(bot_id)` (`main_window.py:6113-6116`). The
class the rule protects is the class the operator cannot delete. **Accepted, and it is
already closed at code level by B1's fix:** `delete_bot(bot_id)` is keyed by id, not memory
presence, and `unregister` already tolerates an absent bot (`self._bots.pop(bot_id, None)`).
Do **not** build a "records on disk not in memory" panel for a failure that has fired zero
times. Revisit only if a restore skip is ever actually observed.

### B9 — LOW. Orphaned wire routes hydrated from disk. **Accepted.**

`_hydrate_smart_wire_routes_from_disk` (`bot_visualizer.py:2636-2674`) emits `wire.created`
per disk route without checking either endpoint is registered, unlike the live path
(`bot_container.py:2453`). Cosmetic only — the row table iterates `_bot_widgets`, so an
unregistered source contributes no row and no % Out; no money moves on this path. Reachable
today with an orphaned `dest_bot_id`, so the rule does not introduce it. **Accepted, do not
ship on this cascade.**

**No lens returned a break requiring a new class, a new bot state, or a decision matrix.**

## 5. The exact edits

Five, plus one comment rewrite. Nothing else.

| # | File | Edit |
|---|---|---|
| E1 | `src/core/state_manager.py` `save_state()`, after the fill loop at `:95-98` | Read the current file; for every `bot_id` present on disk but not in `state["bots"]`, copy the on-disk record forward verbatim. Wrapped so any read failure logs and proceeds with today's behavior — the merge must never be able to abort a save. |
| E2 | `src/core/state_manager.py`, new method | `delete_bot(bot_id)`: load, `state["bots"].pop(bot_id, None)`, drop `smart_wire_ledgers` rows for that id and `smart_wires` naming it source or target, write via the existing atomic tmp+replace (`:105-146`). Idempotent; no-op if the file is absent or unparseable. |
| E3 | `src/trading/bot_container.py` `unregister()`, after `:2138` | `if self._state_manager is not None: self._state_manager.delete_bot(bot_id)` — same guard style as `:2355`. Wrapped in try/except-log: a failed disk delete must not abort the in-memory teardown. |
| E4 | `src/trading/bot_container.py:2119-2127` | Rewrite the comment. It currently claims the `_restore_ledger` pop is what protects delete. It is not; E2/E3 are. Keep the pops for their diagnostic value, say so. |
| E5 | `src/trading/smart_wire.py` `detach_bot()` `:253` | `self._ledgers.pop(bot_id, None)`. |
| E6 | `src/gui/bot_visualizer.py` `_apply_routes_to_state` `:2574` and add loop `:2586` | Return early if the loaded dict has no `"bots"` key (B4); `if bid not in bots: continue` in the add loop (B5). |

`bot_count` at `state_manager.py:87` becomes `len(state["bots"])` after the merge rather
than `len(bots)`, so the field keeps meaning "records in this file."

Optional, one line, not required: call `save_all_state()` right after
`main_window.py:6273`. E3 already writes the deletion at delete time, so this only refreshes
the rest of the file; skip it.

## 6. What already-shipped PR-0 machinery becomes unnecessary

Honest accounting: PR-0 was built to serve the withdrawn design. Under the rule, most of it
is no longer load-bearing for **correctness**. Nothing below is being removed in this
cascade — removal is its own risk — but the record should be straight.

**No longer needed for correctness, keep for diagnosis:**
- `_restore_ledger`, `_boot_state_records`, `_restore_completed`
  (`bot_container.py:1434-1436`) — the merge reads the file, not these. They remain the
  only structured answer to "which bots were skipped and why," which is worth keeping
  precisely because the answer has always been "none." **Keep. Do not let them influence a
  save.**
- `detect_prune()` (`state_manager.py:167`) — was the alarm for the behavior the rule
  removes. Under the rule it should report ~nothing; a non-empty report now means an
  explicit delete or a bug. **Keep as a regression tripwire; it is log-only and cannot
  raise.**
- The DRY-RUN block at `bot_container.py:2382-2402` — obsolete the moment E1 lands.
  **Remove in the same edit** (it computes what to carry forward and then does not carry it;
  leaving both is two answers to one question).
- `_state_import_failed` flags (`:2877`, `:2893`, `:2918`) — these mark the *other* two
  failures (`import_state` / `import_scrumming_state` fall through to `register()` holding
  DEFAULT state). The rule does **not** fix those: the bot is in `_bots`, so a save
  overwrites its good record with defaults. **Keep the flags; out of scope here. See §9.**

**Genuinely load-bearing regardless of design, keep:**
`preflight_snapshot` (`:257`, wired at `main.py:701`), the corrupt-primary backup guard
(`:120-127`), `diff_primary_vs_backup` (`:208`), `probe` (`:403`), `_read_bot_ids` (`:152`),
and the six restore-exit log lines.

Assessment: PR-0 over-built. Roughly the ledger/records/dry-run third of it exists only
because the old design needed to classify absences. It is cheap, log-only, and already
tested, so it stays — but it should not be cited as part of the fix.

## 7. Test plan — `tmp_path` only, RED first

Every test constructs `StateManager(config_dir=tmp_path)`. Nothing touches `~/.acervator`
or `~/.acervator_logs`; `tests/conftest.py` fails the suite if anything does. Each test must
be **observed failing before the corresponding edit**, and the observed failure recorded.

| T | Asserts | Must go RED before |
|---|---|---|
| T1 | Save with bot A only, after a file containing A and B → B's record survives byte-identical, including `main_lots`. | E1 |
| T2 | The MEM-417 case end to end: file has A+B; B is refused by `register()`; a save runs; B is still on disk with its per-lot cost basis. | E1 |
| T3 | `delete_bot("B")` removes B's `bots` entry **and** its `smart_wire_ledgers` row **and** wires naming it either side; A untouched. | E2 |
| T4 | `unregister("B")` with a `StateManager` wired → B is off disk immediately, before any save. | E3 |
| T5 | Delete then save then reload → B does **not** come back. This is the B1/B2 regression test and is the single most important one. | E1+E3 together |
| T6 | Unparseable primary → `save_state` still writes, logs, and does not lose the in-memory bots (merge failure is non-fatal). | E1 |
| T7 | `detach_bot` drops the ledger. | E5 |
| T8 | `_apply_routes_to_state` with a `{}` load performs **no write** (file mtime and bytes unchanged). | E6 |

T5 and T2 are the two that would catch a regression years from now; write them first.

## 8. Exit gates — each a measurement

1. All 8 tests observed RED, with the failure text captured, before their edit lands.
2. `python -m pytest` → **1240 + 8 = 1248 passed, 0 failed.** No test modified; `git diff --stat tests/` shows additions only.
3. `grep -rn "\.unregister(" src/ main.py tools/` still returns exactly one `BotManager` production caller.
4. On an **island copy** of the live file: load → save with an empty bot list → **35 bots still present**, and a byte-diff of the `bots` map is empty. (Island copy only. The live file is read-only.)
5. Same island copy: `delete_bot` on one id → **34 bots**, exactly one id gone, that id absent from `smart_wire_ledgers` and `smart_wires`, all other bytes unchanged.
6. `detect_prune` emits nothing across a full island save cycle.
7. Island GUI launch: 35 bots restore, no new WARN/ERROR in `~/.acervator_logs` relative to a pre-change baseline run.
8. `tools/check_release_readiness.py` → `[OK] Release-ready (vX.Y.Z, 1248 tests)` **before** any banner or CHANGELOG bump.

## 9. The one operator decision that remains

**The 13 orphaned `smart_wire_ledgers` rows already on the live file (27% of 48).** E5 stops
new ones; it does not clean existing ones. Two of the 13 carry non-zero `wired_out`
(132.86 and 9.81), so they are accounting history for bots that no longer exist.

> **Question:** delete the 13 orphan ledger rows, or keep them and mark them
> `orphaned: true`?

Recommendation: **keep and mark.** They are 2.8 KB total, they are the only surviving record
that those transfers happened, and deleting accounting history to save 2.8 KB is the same
instinct that caused this bug. Either way it is a separate, operator-run cleanup on the live
file — not part of this cascade.

*Deferred, not decisions:* the two `import_state` / `import_scrumming_state` failures that
leave a registered bot holding DEFAULT state (the rule does not cover them — a save still
overwrites a good record with defaults), and routing `bot_visualizer` writes through
`StateManager`. Both are separate cascades; neither blocks this one.
