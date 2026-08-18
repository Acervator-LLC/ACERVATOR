# Methodological List for Fixing Everything

**Date:** 2026-08-05 · **Baseline:** v3.24.32, 1105 tests green · **Scope:** 242 open findings across 66 cascades

This is the execution method first, the order second, the cascades third. The method is what makes the order safe; read it before reading the sequence.

---

## 1. Method

Standing rules. Every cascade below is executed under all of them.

| # | Rule | Why |
|---|---|---|
| M1 | **Cold read before design (R68 DPA).** Re-verify every cited `file:line` from current source before writing a fix. Cluster rationales are prior analysis, not evidence. | Verified this session: `feature_telemetry.py` *does* define `TELEMETRY_ROOT_ENV` and `_telemetry_root()` (:88-113). The real defect is that `TELEMETRY_PATH` binds at import, so C14 must resolve the root at **call** time — a setter would have been the wrong fix. |
| M2 | **One risk tier per cascade.** Never mix live-behaviour with record-only or gui-truth in one ship. Anything tiered `live-behaviour` or `live-money` rides alone. | A mixed cascade's decision diff is unreadable; you cannot attribute a flip to a cause. |
| M3 | **The exit gate is a measurement.** A number, a byte-comparison, a diff, or a named test transitioning red→green. "Looks right in the GUI" is never an exit gate. | Eight prior cascades shipped on inspection; four of them are findings in this document. |
| M4 | **Failing-first is mandatory** wherever the 1105-test suite would stay green with a wrong fix. Write or restore the pin, observe it **RED on the unmodified baseline snapshot**, record the failure text, then edit. | A pin never observed failing has not been verified. `grep -rl bot_visualizer tests/` returns zero — eight cascades touch that file. |
| M5 | **Verify by forcing the failure, not by observing success.** Uninstall the analyzer, make the random source raise, make `mkdtemp` fail, corrupt the tablet — then assert the system *reports* it. | All four static analyzers are installed on this machine, so NF-160's "missing" branch is unreachable locally and a naive test proves nothing. |
| M6 | **No banner bump or CHANGELOG entry** without `tools/harness/check_release_readiness.py` printing `[OK] Release-ready (vX.Y.Z, N tests)` with `N > 0` and **zero checks skipped**. Until cascade 1 lands, treat every green as vacuous. | `main()` :150-195 accepts `--no-pytest --no-archetypes --no-claims`; with all three set `failures` is empty and it prints `[OK] … 0 tests` and writes a green sidecar. |
| M7 | **Never modify a test to make it pass.** When a green pin encodes the defect (`test_wire_canvas_ignores_unknown_bot` vs SWARM-A3; `test_swarm_row_parity`'s `_SWARM_ACCENTS` assertion vs C07), record in writing that the pin encodes the defect, replace it with one encoding the requirement, and get operator acknowledgement *first*. | The rule is absolute; the escape hatch is replacement-with-consent, not relaxation. |
| M8 | **The live tree is read-only from every non-live path.** `~/.acervator/{bot_state,coinbase_credentials,reservation_state,feature_telemetry}.json`, `~/.acervator_logs/*`, and the Stone Tablet archive. Sim, tests and tooling **fail closed** (raise) rather than fall back to a live singleton. | Two isolation breaches have already shipped under a green guard that watched the wrong directory. |
| M9 | **No sim↔live bridges.** Fork class bodies into `sadp/RAIntSimBat/sim_*.py`. Never construct `BotManager`, `ExchangeInterface`, the `EventBus` singleton, `PhantomBalance`, or the `CapitalReservationRegistry` singleton from a sim path. Never add a sim identifier to a live table (no `fleet_sim` key in `src/exchange/timeframes.py`). | `BotManager.__init__` subscribes three handlers to the global bus at :1461/:1465/:1466 *before* any caller can rebind `._bus`, and `event_bus.py` has no `unsubscribe` method. |
| M10 | **Fail closed on isolation.** Any sim path that cannot obtain its private bus, private registry or private telemetry sink **aborts the run with an operator-visible reason.** Silent fallback to a process-wide singleton is the failure mode that has shipped twice. | `fleet_replay_controller.py:110-125` returns `None` on any exception; `scrumming_bot.py:1029-1032` then resolves the live autosaving registry. |
| M11 | **Back up before the first destructive run.** Any cascade arming a new writer or deleter of persisted state (C01 merge, C13 prune, C30 prune, C38 sweep) first adds backup-before-overwrite, then runs one full operator session in dry-run/log-only mode, then arms. | `capital_reservation.py:217-238` does `tmp.replace()` with **no** backup, unlike `StateManager`. The 6.5 MB `pre_purge` and 6.0 MB quarantine residue on disk is evidence a mass loss already happened here. |
| M12 | **Structural verification over wall-clock for perf work.** Runtime allocation counters and AST/source assertions that the hot path allocates and imports nothing and that timers stop on `hideEvent`. Any wall-clock claim needs one manual operator measurement at real window size. | An AST check on `paintEvent` alone is defeated by moving allocation into a helper; and CPython does not return freed arenas to the OS, so RSS can stay flat after a correct fix. |
| M13 | **GUI pins must fail, not skip.** Assert `_HAS_QT is True` at test module scope, `resize()+show()+processEvents()` before probing geometry, and keep a collected-GUI-test-count floor the gate refuses to drop below. | `bot_visualizer.py:35-54` hides every class behind `if _HAS_QT:`, so the house-style skip swallows a real absence and the suite still exits 0. |
| M14 | **Live gate decisions change alone and with evidence.** Every live-behaviour cascade ships a per-symbol before/after SCRUM/FOLD decision table from the decision-diff harness, plus a staged rollout — one bot, one session — before fleet-wide arming. | Without a decision table the only available evidence is "the suite is green", and the suite does not construct a live bot. |
| M15 | **Persisted-state semantics are decided explicitly, never inherited from a generic helper.** No dict-deep-merge, no `getattr` default, no "preserve if truthy". Write the rule down, then write the test that encodes it. | A key-level merge on `bot_state.json` re-preserves stale `_main_lots` for a bot that just folded to empty, and the next SCRUM sizes against inventory that does not exist. |
| M16 | **Record truth ships with the fix.** When a cascade proves a CHANGELOG or docstring claim false (RECORD-1, RECORD-4, RECORD-8), the correction lands in the *same* commit as the real fix. | A corrected record that ships later is a record that does not ship. |
| M17 | **Snapshot, not `git revert`.** This tree is **not** under version control — `git rev-parse --is-inside-work-tree` → `fatal: not a git repository`, and there is no `.git` at the root or its parent. Every rollback below names a dated full-tree snapshot under `_archive/pre_<cascade_id>_<date>/`, and every "observe RED on unmodified HEAD" means "observe RED against the baseline snapshot". | Cascade 0 exists solely to make M4, M14 and every `rollback` field executable. |

---

## 2. Ordering doctrine

The sequence is built on six ordering principles, applied in this precedence:

1. **Doctrine 0 — make the instruments trustworthy first.** Nothing can be verified while the release gate can print `[OK]` with every check skipped, the live-tree guard watches a directory the breaches do not touch, and the decision-diff harness the live gates all cite does not exist. Cascades 0–3 build the instruments and produce zero product change.
2. **Doctrine 1 — stop the ongoing destroyers of unrecoverable state.** `save_state` deleting a bot's lots within 60 s, and a sim run that can write the live capital registry or the live telemetry tree.
3. **Doctrine 2 — stop the things that silently overwrite operator intent.** Wire creation rewriting `profit_folding_active`; Settings Save resetting twelve unread keys.
4. **Doctrine 3 — put confirmation in front of destructive gestures** before making those gestures reachable. C06b precedes C04 precisely because the broken mouse-opaque overlay is currently the only thing shielding the default List view from two silent wire-removal branches.
5. **Doctrine 4 — display truth**, ordered so that producers land before consumers (C54 before C03) and so file-level rewrites of `bot_visualizer.py` happen in one descending pass rather than eight interleaved ones.
6. **Doctrine 5/6 — reachability, then features, then perf.** Perf last, and structurally verified, because a perf change that alters a value is a live-behaviour change wearing a disguise.

Four corrections to the naive ordering, each forced by evidence:

- **CV2 moves from 42nd to 3rd.** Its own step reads "record the pre-change baselines NOW, before any live gate lands", which is unsatisfiable from position 42 — four live-behaviour cascades land before it, and C39f changes `profit_folding_active`, which gates target growth at `scrumming_bot.py:1356`. Its stated dependency on C18/C19/C20 is a convenience, not a dependency: the harness replays live gate chains over Stone Tablet windows and calls `compute_all` directly.
- **C14 and C15 swap.** C15's exit gate requires a normal replay to completion, and a replay's `finally` block (`fleet_replay_controller.py:932-955`) is exactly what writes the two live-tree files C14 exists to stop. C14 needs nothing from C15.
- **C11's boot smoke test moves to CV1**; only the wire-or-delete decisions stay at position 20. That test is the only boot-level regression detector this repo would have (`grep -rn 'MainWindow(' tests/*.py` → zero), and thirteen GUI cascades edit window construction ahead of it.
- **C56's SMS disposition hoists into C12.** C12 otherwise writes an exhaustive, by-construction round-trip pin over a delivery path that reports success and sends nothing, and would have to be rewritten 53 cascades later.

---

## 3. The sequence

### 0 — C00 · Baseline snapshot protocol *(v3.24.33, record-only)*

| | |
|---|---|
| **Goal** | Every `rollback`, every "RED on unmodified HEAD", and CV2's tree-pair diff become executable operations. |
| **Why here** | Not optional infrastructure — `git rev-parse --is-inside-work-tree` returns `fatal: not a git repository`; `ls -d .git ../.git` both fail. Only `_archive/` exists as a snapshot mechanism. Without this, 66 `rollback` fields and CV2's core mechanism name operations that do not exist. |
| **Findings** | — (enabling cascade) |
| **Files** | `tools/harness/snapshot.py` (new), `docs/audits/2026-08-05_snapshot_protocol.md` |
| **Risk tier** | record-only |

**Steps**

1. Operator decision first: `git init` + baseline commit, **or** the snapshot protocol. If git, every `rollback` below reads normally and this cascade is ~10 minutes. If not:
2. Write `tools/harness/snapshot.py`: copies the working tree (excluding `_archive/`, `_logs/`, `__pycache__`) to `_archive/pre_<cascade_id>_<YYYYMMDD>/`, records a manifest of `(relpath, sha256, size)`, and refuses to overwrite an existing snapshot directory.
3. Add `snapshot.py --verify <dir>` reporting which files differ from the current tree — this is the "observe RED on unmodified HEAD" mechanism: restore the snapshot, run the pin, record the failure, restore the working tree.
4. Take `_archive/pre_C43_20260805/` as the first baseline.
5. Rewrite CV2's harness signature as `decision_diff(baseline_tree: Path, candidate_tree: Path, windows)` rather than a git-ref pair.

**Entry gate** — none. **Exit gate (measurement):** `snapshot.py --verify` on an unmodified tree reports zero differing files; after touching one byte in one file it names exactly that path; a restore round-trip reproduces the manifest hashes byte-for-byte.
**New tests** — `tests/test_snapshot_roundtrip.py`. **Rollback** — delete the tool; no product code touched.
**Operator decision** — `git init` or snapshot protocol.

---

### 1 — C43 · Release-gate integrity *(v3.24.34, record-only)*

| | |
|---|---|
| **Goal** | The gate can no longer print `[OK] Release-ready` or write a green sidecar when any check was skipped or any analyzer was absent, and `main.py`'s version literals agree with `src/__init__.py`. |
| **Why here** | Doctrine 0. Every cascade below is blessed by this tool. Cold read confirms `main()` :150-195 accepts all three skip flags; with all three set `failures` is empty, so `_write_sidecar(version, 0)` runs and the banner prints "0 tests". The hook only checks sidecar freshness. |
| **Findings** | NF-159, NF-160, NF-133, NF-65, NF-29, NF-154 |
| **Files** | `tools/harness/check_release_readiness.py`, `coding_archetype.py`, `gui_archetype.py`, `docs_archetype.py`, `claim_ledger.py`, `tools/build_release_zip.py`, `main.py`, `.claude/hooks/verify_release_gate.py` |
| **Risk tier** | record-only |

**Steps**

1. Restore `_archive/tests_pre_2026_07_25/test_check_release_readiness.py` and `test_release_gate_hook.py` into `tests/`, run them, and **classify every failure** as (i) import/path drift or (ii) a genuine gate defect. *Correction:* the archived module does `from tools.check_release_readiness import _changelog_block_has_version, _changelog_block_test_count, _first_changelog_block, _read_init_version, _read_main_version, main` — the tool now lives at `tools/harness/` and defines none of those five helpers, so a verbatim restore yields a collection-time `ImportError`, i.e. the wrong red. `test_release_gate_hook.py` pins `.sadp/.last_release_check.json` while the live hook reads `.release_ready.json`.
2. Rewrite the restored tests against `tools.harness.check_release_readiness` and `.release_ready.json`, keeping only assertions that encode the vacuous-green defect. Add the five CHANGELOG/version helpers if the changelog-block assertions are to be retained.
3. Add a `checks_run` record (`{pytest, archetypes, claims}` each `true|skipped`) to `_write_sidecar`; `main()` refuses to write a sidecar and returns non-zero when any entry is `skipped` or `test_count <= 0`.
4. `verify_release_gate.py` DENIES on `tests<=0`, on any `skipped` entry, and on a **missing** `checks_run` field (old sidecars are not trusted).
5. Replace `coding_archetype.py`'s thirteen unconditional `return findings, "ok"` with status `missing` when the analyzer is not importable/executable — `_run_ruff:418-420` returns `"ok"` on empty stdout, which is exactly the `ModuleNotFoundError` case; `_run_archetype_selfcheck` appends `missing` statuses to `errors`.
6. NF-133: there are **three** hardcoded version literals in `main.py`, not two — the boot log at :540, `setApplicationVersion` at :555, and `current_version = "3.24.32"` at :612 (the one the archived `_read_main_version` pinned, and the one `main.py:10-11`'s own header says must match). Source all three from `src.__init__.__version__`. Fix NF-154 in the adjacent boot guard (`logger` is unbound at :124 while the guard's three handlers call `logger.debug`).
7. Correct the claim-ledger (NF-65) and the `build_release_zip` session-27 record (NF-29).

**Entry gate** — `_archive/pre_C43_*` snapshot taken; suite count recorded (1105); both archived gate tests restored, run, and their failures classified in writing.

**Exit gate (measurement):**
(a) running with all three skip flags exits non-zero, prints no `[OK]` line and writes **no** sidecar;
(b) on a run with one test deliberately broken, the tool writes no `checks_run` record and a subsequent hook invocation **DENIES** — *correction: the plan's original clause here ("exits 1 and removes the sidecar") already holds on the baseline at :165-191 and is non-discriminating;*
(c) with `subprocess.run` monkeypatched to simulate ruff absent, `coding_archetype` returns `missing` and the self-check fails;
(d) the rewritten gate tests are green and each red observed during step 1 was classified;
(e) a source-level test parses all three `main.py` version literals and asserts each equals `src.__init__.__version__` — *correction: the plan's original `python main.py --version` clause names a flag that does not exist; `main.py` has no argparse and only sniffs `sys.argv` for `--child`/`--no-watchdog`/`--watchdog`, so that invocation boots the GUI.*

**New tests** — restored `tests/test_check_release_readiness.py`, `tests/test_release_gate_hook.py`, new `_run_ruff` missing-analyzer pin, new three-literal version consistency pin.
**Rollback** — restore `_archive/pre_C43_*`; the old sidecar format is still accepted by the pre-change hook.

---

### 2 — CV1 · Verification substrate *(v3.24.35, record-only)*

| | |
|---|---|
| **Goal** | No test run can mutate any path under `~/.acervator`, `~/.acervator_logs` or the Stone Tablet archive without failing the suite; GUI pins fail rather than skip; boot-level regressions are detectable; the archived pins each downstream cascade must restore are written down. |
| **Why here** | Doctrine 0 continued. `tests/conftest.py:107-122` guards **only** `~/.acervator_logs/sim/runs` by directory-name diff — the two files C14 is about are outside it, so the original breach happened with the guard green. Without this, C14/C15/C26/C38's proofs are unfalsifiable. |
| **Findings** | — (detection substrate only; *correction: SN-6, RECORD-4 and TABLET-9 are **detected** here but **remediated** by C14 and C37, and are claimed there. CV1 builds detectors; a detector is not a remediation, and claiming them here would close three critical ids one cascade early.*) |
| **Files** | `tests/conftest.py`, `src/trading/stone_tablets/registry.py`, `docs/audits/2026-08-05_archived_pin_inventory.md`, `tests/test_main_window_boot_smoke.py` |
| **Risk tier** | record-only |

**Steps**

1. Make live-root resolution **injectable**: replace the module constant `_LIVE_ROOTS` with a monkeypatchable `_live_roots()`. *Correction: the plan's original exit gate — "a test writing one byte to `~/.acervator/feature_telemetry.json` FAILS the suite" — cannot be executed under this project's discipline, because running the gate requires writing the operator's read-only live tree. The guard must be provable against fake roots.*
2. Extend `_assert_no_live_tree_writes` to snapshot `(path, mtime_ns, size)` for every file under **both** live roots at session start and assert none changed at session end, naming the changed path.
3. Add the Stone Tablet archive root to the guarded set; make `StoneTabletsRegistry.__init__` raise when the default root is used under the pytest marker (`registry.py:164-166` currently creates the root on construction).
4. Add a guard failing any test that resolves `capital_reservation.get_registry()` or `core.event_bus.get_event_bus()` from a sim/test path without explicit opt-in.
5. Add a collected-test-count floor and a **collected-GUI-test-count floor** (M13).
6. Write `tests/test_main_window_boot_smoke.py` — offscreen `MainWindow` construction, zero swallowed exceptions, named subsystems non-None. *Moved here from C11: no test in the 73-file suite constructs `MainWindow` (`test_canonical_tab_order.py:47-51` explicitly extracts `_reorder_main_tabs` as a plain callable to avoid construction cost), and thirteen GUI cascades edit that path before position 20.* Observe it RED on the baseline — `main_window.py:3816` calls `self._simulator.set_bot_viz(...)`, defined nowhere, into a bare except.
7. Publish the archived-pin inventory naming, per cascade, the file to restore first. *Correction to two filenames:* the archive contains `test_wire_canvas_overlay_v3_23_19.py` and `test_quick_routing_matrix_multi_select_v3_23_13.py`, not `test_wire_canvas_overlay.py` / `test_quick_routing_matrix.py`. The other nine (`test_swarm_row_parity`, `test_mem245_state_persistence`, `test_swarm_state_persistence`, `test_capital_reservation_coverage`, `test_version_sweep_coverage`, `test_rule_registry_coverage`, `test_adx_trend_suppression_gate`, `test_p2_9_adx_wiring`) verify exact.

**Entry gate** — C43 green. A scratch script confirms the *current* guard passes while touching a file under a fake `~/.acervator`, proving the blind spot.

**Exit gate (measurement):** with `_live_roots()` monkeypatched to a `tmp_path` pair, a test writing one byte under either fake root FAILS the guard **naming that path**, and the real `~/.acervator` and `~/.acervator_logs` are untouched for the whole suite (asserted by the same snapshot); a test constructing `StoneTabletsRegistry()` with no root FAILS under the marker; the boot smoke test is green and its handler counter is 0; the gate's reported suite count equals the count recorded at the end of C43 **plus exactly** the guard tests added here (state both numbers) — *correction: a fixed literal 1105 is wrong at every cascade after the first, since C43 restores two modules and adds two pins.*

**New tests** — `tests/test_conftest_live_tree_guard.py`, `tests/test_conftest_archive_guard.py`, `tests/test_main_window_boot_smoke.py`.
**Rollback** — restore snapshot; guards are additive with no production change.

---

### 3 — CV2 · Live decision-diff harness + TA golden baseline *(v3.24.36, record-only)*

| | |
|---|---|
| **Goal** | A runnable tool that replays fixture windows through baseline and candidate trees and emits a per-symbol SCRUM/FOLD decision table, plus a `compute_all` golden baseline captured **before** any gate input moves. |
| **Why here** | *Correction: moved from order 42 to order 3.* Eight cascades (C31, C32, C39a-d, C13, C60) name this table as their exit-gate evidence and CV2 is their entry gate; four live-behaviour cascades otherwise land before it (C39f, C05, C17, C38), and C39f changes `profit_folding_active`, a live gate input (`scrumming_bot.py:1356`), so a baseline taken at position 42 is already post-contamination. `ls tools/harness/` confirms neither `decision_diff.py` nor `ta_golden_baseline.py` exists. |
| **Findings** | — (tool; SN-40/SN-41 are remediated by C47, which consumes this baseline) |
| **Files** | `tools/harness/decision_diff.py`, `tools/harness/ta_golden_baseline.py` |
| **Risk tier** | record-only |

**Steps**

1. `decision_diff.py`: given a **baseline tree path and a candidate tree path** (per C00 — not a git ref pair) and a set of Stone Tablet windows, run each live bot's gate chain over both and emit a per-symbol table of SCRUM/FOLD decisions with the differing inputs named.
2. `ta_golden_baseline.py`: capture `compute_all`'s full output bit-for-bit over real tablet windows. `tests/test_ta_suffix_bit_identity.py` covers only `_sma`/`_stdev`/`_sma_tail`/`_stdev_tail`, not the eleven-indicator block.
3. Record the pre-change baselines **now**.
4. Self-test: inject a known threshold change and assert the table reports exactly the expected flips and nothing else.

**Entry gate** — C00 and CV1 green. *Correction: the plan's original entry gate required C18/C19/C20; dropped. The harness replays live gate chains over tablet windows and calls `compute_all` directly — it needs no `FleetSimExchange`, no sim capital registry, and no `_build_sim`.*

**Exit gate (measurement):** with an injected one-line threshold change the harness reports exactly the expected set of decision flips and zero others; with no change it reports a byte-identical table across two runs; the `compute_all` golden baseline is recorded and re-running against the baseline snapshot reproduces it byte-for-byte.

**New tests** — `tests/test_decision_diff_harness.py`, `tests/test_ta_golden_baseline.py`.
**Rollback** — delete the tools; no production code touched.
**Operator decision** — which fixture windows constitute the standard diff set. They become the evidence base for every live gate below.

---

### 4 — C01 · State persistence: merge-not-replace, explicit delete, honest restore *(v3.24.37, live-money)*

| | |
|---|---|
| **Goal** | A bot that fails to restore, or is refused by the capital registry, keeps its persisted config/stats/`scrumming_state` on disk; a deleted bot is removed from disk explicitly; `register()`'s refusal is surfaced instead of logged as "Restored". |
| **Why here** | Doctrine 1 — the only ongoing destroyer of unrecoverable persisted state. `state_manager.py:83-98` builds `"bots": {}` and fills it solely from the passed list, so restore's four silent `continue` paths delete a bot's lots/tranches at the next 60 s save, and `bot_state.backup.json` is single-generation and overwritten by that same save. |
| **Findings** | SWARM-4.1, SWARM-4.2, NF-135, NF-156 |
| **Files** | `src/core/state_manager.py`, `src/trading/bot_container.py`, `main.py` |
| **Risk tier** | live-money |

**Steps**

1. **First edit:** `save_state` merges whole **entries** only — for every `bot_id` in the live registry the live dict REPLACES the disk dict wholesale (no key-level union, no deep-merge helper); merge re-adds only entries whose `bot_id` is absent from the live registry. Same rule for `smart_wires`/`ledgers` passed as `None` (the docstring at :70-79 already promises a preservation the code does not do).
2. *Correction — SWARM-4.2 is not resolved by that rule and directly contradicts exit gate (d).* A bot whose `import_scrumming_state` **raises** is logged at WARNING (`bot_container.py:2787-2794`) and falls through to `self.register(bot)` at :2803, so it **is** in the live registry with default/empty state, and the wholesale replacement overwrites its good persisted lots. Set a per-bot flag (`bot._state_import_failed = True`) on any import failure and have `save_state` treat that bot as **absent** from the live registry for merge purposes (disk entry preserved verbatim), or refuse to serialise its `scrumming_state` until a successful import.
3. Drop `scrumming_state.smart_wire_routes` from any merge-preserved entry so the GUI-only key cannot become immortal and replay deleted wires at boot via `_hydrate_smart_wire_routes_from_disk`.
4. Add explicit removal: `BotManager.unregister` writes the deletion through `StateManager` (or a tombstone the merge honours) so the operator's "this cannot be undone" delete actually is.
5. Gate merge-preserved entries out of `main.py`'s `_autostart_bot_count` on the first boot after the change, so a resurrected entry cannot be auto-started into live trading.
6. NF-156: propagate `register()`'s `(False, reason)` out of `restore_bots_from_state`, do not append the bid to `restored`, log at ERROR; the merge keeps the disk entry intact.
7. On the first run after the change, write a **dated** copy of `bot_state.json` alongside the single-generation backup (M11).

**Entry gate** — cascades 0–3 green. `tests/test_state_manager_merge.py` plus the restored `test_mem245_state_persistence.py` / `test_swarm_state_persistence.py` observed RED against the baseline snapshot. A dated offline copy of `~/.acervator/bot_state.json` taken by the operator.

**Exit gate (measurement)** — against a seeded temp `bot_state.json`, never `~/.acervator`:
(a) 35-bot file + `save_state([1 bot])` leaves 35 entries;
(b) live bot with `_main_lots == []` plus a disk entry holding 3 lots yields **0** lots on disk;
(c) delete → save → load leaves the `bot_id` **ABSENT**;
(d1) a bot **skipped during restore** survives a full boot+save cycle byte-identical;
(d2) a bot **registered but import-failed** survives byte-identical — *the SWARM-4.2 case, an independent pin*;
(e) create wire → delete wire → simulate hydrate emits **ZERO** `wire.created`;
(f) `smart_wires=None` preserves the array byte-for-byte.

**New tests** — `tests/test_state_manager_merge.py`, `tests/test_bot_delete_removes_from_disk.py`, `tests/test_restore_refusal_preserves_state.py`, `tests/test_import_failed_bot_preserved.py`.
**Rollback** — restore `_archive/pre_C01_*`; the on-disk format is unchanged (merge is writer-side policy). The dated pre-merge copy is the data rollback.
**Operator decision** — delete semantics: hard key removal vs tombstone-with-retention.

---

### 5 — C14 · Sim telemetry stops writing the live tree *(v3.24.38, sim-only)*

| | |
|---|---|
| **Goal** | A Fleet Replay writes telemetry and its validation report into the run's own directory; the two live files are untouched by any sim run; sim counters stop being recorded under `live.` keys. |
| **Why here** | *Correction: swapped with C15 (was order 5, now order 4 in the sim pair).* C15's exit gate requires a normal replay to completion, and the replay's `finally` block at `fleet_replay_controller.py:932-955` is precisely what writes `~/.acervator/feature_telemetry.json` and `~/.acervator_logs/feature_validation.md`. C14 needs nothing from C15 — with `mkdtemp` working normally the sim registry is already `autosave=False` on a temp path. Cold-read correction: `TELEMETRY_ROOT_ENV` and `_telemetry_root()` **do** exist (`feature_telemetry.py:88-113`); the defect is that `TELEMETRY_PATH` binds at import (:113) and `__init__` freezes `self._path` (:197), so a later env override is a no-op. |
| **Findings** | SN-6, RECORD-4, SN-56 |
| **Files** | `src/core/feature_telemetry.py`, `fleet/fleet_replay_controller.py`, `nuclear_fleet_controller.py`, `topology_stress.py`, `nuclear_verification.py`, `fleet_replay_panel.py`, `simulator_tab.py`, `src/trading/scrumming_bot.py`, `tests/conftest.py`, `CHANGELOG.md` |
| **Risk tier** | sim-only |

**Steps**

1. Do **not** fix by mutating process environment: `write_markdown_report` resolves at call time while the `.json` path is frozen at import, so an env redirect would send LIVE reports into the sim's temp dir while leaving the json in `~/.acervator`.
2. Have the controller **construct** its own run-scoped `FeatureTelemetry` by default (sink derived from the run directory it already owns), with a fallback to `get_telemetry()` that **raises**. *Correction to the plan's injection-only design: `nuclear_fleet_controller.py:425-432` and `topology_stress.py:310` each construct `FleetReplayController` with a fixed six-kwarg list carrying no telemetry sink, so an omission-defaults-to-singleton design silently re-opens this the moment C24 arms Nuclear v2 — once per soak cycle.* Add both construction sites to this cascade's files.
3. Write the precedence rule down and pin it: **explicit `path=` > `ACERVATOR_TELEMETRY_ROOT` > `Path.home()`**. *Correction: without this, step 2 (injected sim path) and step 4 (call-time root resolution) cancel each other — a `save()` that re-resolves the root at call time discards the injected sim path, and the plan's original gate clause passes for exactly that broken implementation.*
4. Resolve the telemetry root at **call** time in `save()`/`write_markdown_report()` for default-constructed instances, so the frozen-at-import failure class cannot recur.
5. SN-56: derive the scope prefix from `self._sim_mode` at `scrumming_bot.py:4574` and every sibling record site (`'sim.'` vs `'live.'`), never a hardcoded literal.
6. Correct the v3.24.32 CHANGELOG entry recording RECORD-4 as shipped (M16).

**Entry gate** — CV1's file-granularity live-tree guard active and observed RED on a baseline replay.

**Exit gate (measurement):** one full replay start→finish leaves `mtime_ns` and size of both live files byte-identical; the run directory contains both artefacts; a forced sim gate-emit failure changes **no** `live.` key; a test that imports the module, THEN sets the override, THEN calls `save()` lands the file in `tmp_path`; and the three-case precedence pin passes (explicit+env → explicit wins; no-path+env → env; neither → home).

**New tests** — `tests/test_feature_telemetry_call_time_root.py`, `tests/test_feature_telemetry_path_precedence.py`, `tests/test_sim_telemetry_isolation.py`, `tests/test_telemetry_scope_prefix.py`.
**Rollback** — restore snapshot; the live singleton path is unchanged. The CHANGELOG correction stays — record truth is not rolled back.

---

### 6 — C15 · Sim capital registry: fail closed and own its temp dir *(v3.24.39, live-money)*

| | |
|---|---|
| **Goal** | A sim fleet that cannot obtain a private, non-persisting `CapitalReservationRegistry` aborts the run and can never fall back to the process-wide autosaving registry that writes `~/.acervator/reservation_state.json`. |
| **Why here** | Doctrine 1/2 (M10), and a hard predecessor of every replay-verified cluster (C16, C18, C19, C20, C23, C26, C61) and of C13. `scrumming_bot.py:1029-1032` `_crr()` returns the process-wide `get_registry()` when the injected registry is `None`, and `fleet_replay_controller.py:110-125` returns `None` on any exception. |
| **Findings** | SWARM-4.24, SN-52 |
| **Files** | `fleet/fleet_replay_controller.py`, `src/gui/simulator_tab/nuclear_controller.py`, `src/trading/scrumming_bot.py` |
| **Risk tier** | live-money |

**Steps**

1. Rewrite `_make_sim_capital_registry` to hold a `TemporaryDirectory` on the controller (cleaned in the run's `finally`) and to **RAISE** with an operator-visible reason instead of `except Exception: return None`.
2. *Correction: `nuclear_controller.py:37` imports `_make_sim_capital_registry` and calls it at :355 — a second production caller the plan's file list omits. Changing the helper to raise introduces an unguarded exception at the Nuclear start path unless that site is handled, which would abort Nuclear Mode with a bare traceback — the opposite of the goal.* Handle both call sites.
3. Make `_instantiate_bot` refuse to construct a sim bot when no registry was injected.
4. Structural backstop: `ScrummingBot._crr()` returns `None` (not `get_registry()`) when `self._sim_mode` is True.
5. Assert at replay start that every constructed sim bot's registry is not the module singleton.

**Entry gate** — C14 green; CV1's `get_registry` guard active and observed RED against a forced-`mkdtemp`-failure replay on the baseline.

**Exit gate (measurement):** with `tempfile.mkdtemp` monkeypatched to raise, **both** the Fleet replay **and** Nuclear Mode start ABORT with a named operator-visible reason (not a bare traceback), zero sim bots are constructed, and `mtime`+size of `~/.acervator/reservation_state.json` are unchanged; on a normal replay the temp dir exists during and is gone after, and no sim `bot_id` appears in the live file.

**New tests** — `tests/test_sim_capital_registry_fail_closed.py`, `tests/test_nuclear_capital_registry_fail_closed.py`, extend `tests/test_sim_reservation_isolation.py`.
**Rollback** — restore snapshot; the `_crr` sim_mode backstop reverts independently and has no live effect.

---

### 7 — C39f · LIVE GATE: wire creation must not rewrite `profit_folding_active` *(v3.24.40, live-behaviour)*

| | |
|---|---|
| **Goal** | Rehydrating or adopting a Smart Wire never flips `bot.config.profit_folding_active`; only an explicit operator action changes it. |
| **Why here** | Doctrine 2, and it must precede C02 and C06c, both of which multiply the paths emitting `wire.created`. `main_window.py:5589` sets the flag unconditionally; `bot_container.py:2404` and `bot_visualizer.py:2669` both re-emit at boot; `get_full_state` persists `asdict(config)` at the next 60 s save, so the operator's OFF is permanently overwritten. The flag gates target growth (:1356) and DIST tranche rebuild (:8688). |
| **Findings** | SWARM-4.3 |
| **Files** | `src/gui/main_window.py`, `src/trading/bot_container.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Tag `wire.created` with `origin` (`operator` \| `rehydrate` \| `adopt`) at all three emitters.
2. `_on_wire_created` mutates config **only** for `origin == 'operator'`; rehydrate and adopt never write config.
3. Route enabling profit folding through the existing explicit Live Settings action.
4. Produce the before/after config diff across all 35 persisted bots over one boot cycle.

**Entry gate** — cascades 0–6 green. A recorded snapshot of `profit_folding_active` for all 35 bots from a **read-only copy** of `bot_state.json`.

**Exit gate (measurement):** *correction — the measurement must run against a temp config dir, not a real boot. Booting the app starts the 60 s autosave (`main.py:983-989`) which rewrites `~/.acervator/bot_state.json` through the very `save_state` path C01 just changed, so measuring would mutate the artefact being measured and persist a wrong fix before the diff is read.* Seed a `StateManager(config_dir=<tmp>)` from a read-only copy of the operator's file, boot against it with all 35 bots and their wires, and assert post-boot `profit_folding_active` is IDENTICAL to the pre-boot snapshot for every bot (currently the wired sources flip True); assert `~/.acervator/bot_state.json` `mtime_ns` and size are unchanged for the whole measurement run; plus a SCRUM/FOLD decision diff (CV2) on the affected bots showing no other decision changed. Only then does a real staged boot happen — and that boot is the rollout, not the gate.

**New tests** — `tests/test_wire_created_does_not_mutate_config.py`.
**Rollback** — restore snapshot; values already flipped by prior boots are restored by the operator from the recorded snapshot, which this cascade produces as an artefact.
**Operator decision** — for bots already silently flipped True by previous boots: restore each to the intended value, or leave as-is? A live compounding decision, per bot.

---

### 8 — C12 · Settings round-trip: read back everything you write *(v3.24.41, gui-truth)*

| | |
|---|---|
| **Goal** | Opening Settings and pressing Save cannot change any value the operator did not touch, and no widget silently discards its value. |
| **Why here** | Doctrine 2. `settings_dialog._save` (:1023-1123) writes twelve keys `_load_current` (:979-1021) never reads, so every Save resets them to widget defaults; the TA/Phantom/SMS tab widgets are in neither function; zero test references to `settings_dialog` exist today. |
| **Findings** | NF-6, NF-78, SWARM-T7-12 |
| **Files** | `src/gui/settings_dialog.py`, `src/gui/bot_visualizer.py`, `src/core/settings.py` |
| **Risk tier** | gui-truth |

**Steps**

1. **Operator decision first (hoisted from C56):** is the SMS channel intended functionality or abandoned? NF-39 shows `notifications.py:330` reports SMS as delivered while sending nothing (wrong arg order, config never reaches the engine). If abandoned, remove the tab rather than wiring it — otherwise the exhaustive pin written below locks in keys that must be unwound 53 cascades later, and the platform persists phone numbers and carrier selections for a dead delivery path.
2. Write the **key-enumerating** round-trip pin (parse `_save`'s written keys or drive the dialog offscreen) so the fix cannot miss a key the way a hand-written list can.
3. *Correction: that pin is structurally blind to NF-78 and would ship it green.* NF-78 is that the TA-weight sliders (`self._ta_weight_sliders` :444/:458), phantom-timeframe checkboxes (`self._phantom_tf_checks` :471/:476) and the ten SMS widgets (:751-811) appear in **neither** function — a widget `_save` never writes contributes no key, so a save-side enumeration passes trivially. Add a **widget-enumerating** pin: `findChildren` over `QCheckBox/QLineEdit/QComboBox/QSlider`, set a non-default on each, save, reconstruct the dialog, assert every widget's value survived and that the widget count equals the round-tripped count.
4. Make `_load_current` read every key `_save` writes; add the surviving TA/Phantom/SMS widgets to both.
5. Persist `_view_mode` and `_wire_opacity_pct` (`bot_visualizer.py:1067-1068`) through the same settings namespace as the already-persisted privacy dot, with a loader.

**Entry gate** — C43 green; the SMS disposition recorded; both pins observed RED on the baseline, the key pin naming the twelve unread keys and the widget pin naming the three unwired tabs.

**Exit gate (measurement):** for every key `_save` writes, set a non-default value, then save→load→save; the second serialised write equals the first byte-for-byte. Separately, three-way set equality: {value-bearing input widgets} == {keys `_save` writes} == {keys `_load_current` reads}, zero unmatched in any direction. Separately: view mode and wire opacity survive a tab restart.

**New tests** — `tests/test_settings_dialog_roundtrip.py`, `tests/test_settings_dialog_widget_coverage.py`.
**Rollback** — restore snapshot; added keys are ignored by older code.
**Operator decision** — SMS channel: wire or delete.

---

### 9 — C02 · Smart Wire persistence: decide ONE durable channel *(v3.24.42, live-money)*

| | |
|---|---|
| **Goal** | Smart Wire routes have exactly one persistence channel and the GUI no longer performs full-file read-modify-write on `bot_state.json`. |
| **Why here** | Hard after C01 (the 60 s rebuild erases any channel established first) and after C39f (a new rehydration path must not rewrite config). NF-45 says delete `_apply_routes_to_state` while SWARM-A7 says call it from the drag path — only a single-channel decision resolves that, which is why `bot_visualizer.py:2534-2675` is one edit pass. |
| **Findings** | SWARM-4.19, SWARM-4.20, SWARM-4.21, SWARM-4.22, SWARM-A7, NF-45 |
| **Files** | `src/gui/bot_visualizer.py`, `src/trading/smart_wire.py`, `src/core/state_manager.py` |
| **Risk tier** | live-money |

**Steps**

1. Decide the channel: `SmartWireManager.export_wires` → `state_manager.smart_wires` is the single durable record; `scrumming_state.smart_wire_routes` is retired.
2. Delete `_save_bot_state_dict` / `_load_bot_state_dict` / `_apply_routes_to_state` / `_clear_all_routes_in_state`; route every GUI mutation through the manager and `save_all_state` (single writer — this closes the read-modify-write race that silently reverts a just-filled trade's lot update).
3. Migrate existing `scrumming_state.smart_wire_routes` into the manager once, then delete the key from disk (C01's merge already refuses to preserve it).
4. Replace `_hydrate_smart_wire_routes_from_disk` with a manager-sourced hydrate emitting `origin='rehydrate'` (C39f contract).
5. No `except Exception: pass` may remain on a persistence path.

**Entry gate** — C01 and C39f green. A GUI pin (fail-not-skip, `_HAS_QT` asserted, sized+shown) creating/removing a route and asserting the persisted record, observed RED on the baseline.

**Exit gate (measurement):** (a) create route, force a concurrent `save_all_state`, assert BOTH the route and a freshly-appended lot survive on disk; (b) remove route, restart-simulate, ZERO `wire.created` emitted for it; (c) grep proves no `smart_wire_routes` key and no full-file writer remain.

**New tests** — `tests/test_smart_wire_durable_channel.py`.
**Rollback** — restore snapshot; the migration is one-way, so C01's dated pre-merge copy of `bot_state.json` is the data rollback.
**Operator decision** — confirm the durable channel before editing; it decides whether `_apply_routes_to_state` is deleted (NF-45) or retained (SWARM-A7).

---

### 10 — C06b · Destructive wire-drag confirmation + removal audit trail *(v3.24.43, live-money)*

| | |
|---|---|
| **Goal** | No left-press-and-drag removes a Smart Wire without explicit confirmation, and every removal is recoverable from an audit record. |
| **Why here** | HARD before C04, and counter-intuitively so: the broken mouse-opaque overlay is currently the only thing shielding the default List view from these two silent branches. `_finish_wire_drag:2740-2759` removes a wire on drag-between-a-connected-pair and on drag-to-empty-space; `remove_wire` → `unregister_wire` stops real fold-profit routing and `save_all_state` persists the loss within 60 s. |
| **Findings** | SWARM-A1 |
| **Files** | `src/gui/bot_visualizer.py`, `src/trading/bot_container.py` |
| **Risk tier** | live-money |

**Steps**

1. Add a modal confirmation naming source, target and pct to **both** destructive branches.
2. Have `unregister_wire` append the removed `(source_id, target_id, pct, ts)` to a dated wire-audit file **before** the removal takes effect, so a mis-click is recoverable whatever the confirmation design.
3. Require a modifier or explicit handle so an accidental press cannot even reach the confirmation.

**Entry gate** — C02 green (the durable channel exists, so "removed" has one meaning). A GUI pin driving a synthetic drag observed RED on the baseline.

**Exit gate (measurement):** synthetic drag-to-empty-space with one outgoing wire leaves the wire count UNCHANGED and raises a confirmation; confirming removes the wire AND writes an audit line containing the exact pct.

**New tests** — `tests/test_wire_drag_confirmation.py`.
**Rollback** — restore snapshot; the audit file is additive and harmless if left.
**Operator decision** — confirmation style: modal per removal, or undo-toast with a 5 s window.

---

### 11 — C06c · Topology Adopt safety: asset binding, overwrite disclosure, rollback *(v3.24.44, live-money)*

| | |
|---|---|
| **Goal** | Adopting a topology is one disclosed transaction: no unvalidated asset→bot binding, no silent overwrite of a hand-tuned wire pct, no orphan bots on cancel. |
| **Why here** | Doctrine 3, after C39f (adopt emits `wire.created`) and C02 (the wire record has one home). `main_window.py:5223-5279` is one loop; `smart_wire.py:285`'s setdefault-then-assign overwrites an existing pct with no read-back and returns `applied: True` either way. |
| **Findings** | SWARM-4.25, SWARM-4.26, SWARM-4.27 |
| **Files** | `src/gui/main_window.py`, `src/trading/smart_wire.py`, `src/gui/market_inspector_topologies.py` |
| **Risk tier** | live-money |

**Steps**

1. Validate the symbol before `asset_to_bot[asset] = sorted(new_ids)[0]` at :5258; refuse the adopt with a named reason on mismatch.
2. Make `register_wire` return the prior pct (`replaced_pct`) instead of silently overwriting.
3. Collect every create and every overwrite into ONE pre-commit confirmation listing `A->B: 20% -> 50%` before anything is applied.
4. Snapshot `export_wires()` to a dated file before the transaction; on cancel or any step failure, roll back created bots and restore the snapshot (no orphan bots from a cancelled six-wizard sequence).

**Entry gate** — C39f and C02 green. A pin adopting a topology that overlaps an existing hand-tuned wire, observed RED on the baseline.

**Exit gate (measurement):** adopting a topology containing an existing A→B at a different pct produces confirmation text containing the exact old and new pct; declining leaves wire count, pcts AND bot count identical; cancelling mid-wizard leaves zero new bots.

**New tests** — `tests/test_topology_adopt_transaction.py`.
**Rollback** — restore snapshot; the dated `export_wires` snapshot is the data rollback for an already-applied adopt.
**Operator decision** — may an adopt ever overwrite an existing pct at all, or must it always skip existing pairs and report them?

---

### 12 — C04 · Wire-canvas geometry + visibility (restore the default List view) *(v3.24.45, gui-truth)*

| | |
|---|---|
| **Goal** | The wire canvas is shown only over the visible grid; the default List view receives mouse and wheel events again; and in Grid mode it is correctly positioned and mouse-transparent. |
| **Why here** | Doctrine 5 (reachability), hard after C06b. Confirmed: `__init__` builds `_wire_canvas` at :1496 with `WA_TransparentForMouseEvents=False`, hides it at :1499, then `_on_tab_changed(currentIndex())` at :1512 unconditionally shows/raises/repositions it over the HIDDEN `_grid_widget`. |
| **Findings** | SWARM-1.1-OVERLAY, NF-3, SWARM-A6 |
| **Files** | `src/gui/bot_visualizer.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Make show/raise of `_wire_canvas` conditional on `_grid_widget` being visible; keep it hidden at the default list index.
2. Reconcile `_reposition_wire_canvas` (:2187-2210) with `resizeEvent` (:2212-2216) so geometry follows the grid widget rather than a stale rect.
3. Set `WA_TransparentForMouseEvents` True except while a drag is active.

**Entry gate** — C06b green. `tests/test_bot_visualizer_overlay.py` written and RED on the baseline, using `resize(1280,900)+show()+processEvents()` before probing — an unsized offscreen widget reports a `sizeHint` rect and would pass trivially on broken code.

**Exit gate (measurement):** with `currentIndex()==0` and `_grid_widget` hidden, `_wire_canvas.isVisible()` is False AND `self.childAt(x,y)` at three concrete coordinates inside the list rows returns the row widget, not the canvas. *Correction — two positive-control clauses are required, because every clause above is satisfied by a fix that simply deletes the `show()` call and thereby permanently removes the Grid view's wire drawing:* (a) after switching to the Grid page, `_wire_canvas.isVisible()` is True and its geometry equals `_grid_widget`'s mapped rect (exact `QRect` equality); (b) in Grid mode with no drag active, `_wire_canvas.testAttribute(Qt.WA_TransparentForMouseEvents)` is True **and** a synthesised `QMouseEvent` at the Exchange-combo coordinate is delivered to the combo (assert via an event-filter capture) — `childAt()` does not consult that attribute, so it cannot measure step 3 at all. Plus one manual operator confirmation at real window size that the seven interactions named in the `:2187-2199` docstring work.

**New tests** — `tests/test_bot_visualizer_overlay.py` (asserts `_HAS_QT is True` at module scope).
**Rollback** — restore snapshot; the overlay returns, which also re-hides the C06b-guarded drag, so no new exposure.

---

### 13 — C05 · Quick Routing: mass-operation confirmation, named rejections, scroll stability *(v3.24.46, live-behaviour)*

| | |
|---|---|
| **Goal** | Connect/Disconnect disclose how many wires they will create or destroy and why any pair was rejected; the scope list keeps scroll position and selection. |
| **Why here** | Doctrine 3, hard after C04 (the clicks and wheel events these tests drive were being swallowed) and after C02 (which decides whether these handlers still call `_apply_routes_to_state`). |
| **Findings** | SWARM-A2, SWARM-4.9, SWARM-4.8 |
| **Files** | `src/gui/bot_visualizer.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Add an N × M count label and a confirmation to `_on_connect_clicked` (:959-988) and `_on_disconnect_clicked` (:994-1015).
2. Replace the six bare returns and two `except Exception: pass` with named rejection messages surfaced in the panel.
3. Fix `rebuild_scope`'s clear+refill (:867-900) to preserve scroll offset and checked sets.

**Entry gate** — C04 and C02 green. The restored `test_quick_routing_matrix_multi_select_v3_23_13.py` plus a multi-select connect pin, observed RED on the baseline.

**Exit gate (measurement):** 4 sources × 3 targets ⇒ the confirmation states 12; declining leaves the wire count unchanged; a rejected pair produces a non-empty named reason; after `rebuild_scope` the scrollbar value and checked set are identical to before.

**New tests** — `tests/test_quick_routing_mass_ops.py` (restore + extend the archived pin).
**Rollback** — restore snapshot (150-line region).

---

### 14 — C51 · Indicator Voting Panel: stop fabricating TA *(v3.24.47, gui-truth)*

| | |
|---|---|
| **Goal** | The panel never renders synthetic/random indicator values under a real bot's symbol, through any of its three entry paths, and a fabrication attempt is loud rather than swallowed. |
| **Why here** | Doctrine 4 — the highest-deception live surface outside the Swarm. `indicator_panel.py:383` schedules a 3 s demo that generates TA from random noise; the panel is constructed at `main_window.py:3451` and fed real data at :4980. No dependencies. |
| **Findings** | NF-4 |
| **Files** | `src/gui/indicator_panel.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Gate all three entry paths together: `_auto_init_demo`, `_on_bot_selected`, `force_refresh`.
2. Narrow or remove the blanket `except Exception` at `indicator_panel.py:876-879`. *Correction: it currently wraps the entire `_generate_demo_ta` body including `rng = random.Random(seed)` and the candle loop, so a monkeypatched-to-raise random source is swallowed and the method returns normally — the plan's original entry gate ("observed RED on HEAD") and exit gate ("all three paths render successfully") are **both already satisfied by the unmodified baseline**, so neither measures anything.*
3. Render an explicit "no data" state instead of fabricated values when a real bot is selected.
4. Keep the demo generator reachable only from an explicitly labelled demo mode.

**Entry gate** — C43 green. A pin asserting `panel._data` is empty and `_table_a.rowCount() == 0` after each of the three entry paths for a real bot, observed RED on the baseline.

**Exit gate (measurement):** with `random.Random` monkeypatched to raise, all three entry paths leave `panel._data` empty and render the explicit no-data string, and the raised exception is **not** swallowed. *Correction to the timer clause: `_anim_timer` (:188-190) is the 60 fps confidence-bar animation, not the demo — the demo is scheduled by `QTimer.singleShot(3000, self._auto_init_demo)` at :383 with no retained handle, so asserting on `_anim_timer.isActive()` measures the wrong timer and stopping it breaks the bar graph.* Instead: with `QTimer.singleShot` monkeypatched to a capture list, assert **no demo callback is queued** when a real bot is present.

**New tests** — `tests/test_indicator_panel_no_fabrication.py`, `tests/test_indicator_panel_demo_timer_not_scheduled.py`.
**Rollback** — restore snapshot; the thirteen existing layout pins are untouched either way.

---

### 15 — C10 · Main-window dashboard display truth *(v3.24.48, gui-truth)*

| | |
|---|---|
| **Goal** | The 2 s dashboard tick shows the real Ammo value with an explicit staleness marker, clears the Swarm when the last bot is deleted, and stops decorating retired widgets. |
| **Why here** | Doctrine 4, and NF-5 is the worst of the set: the Ammo column takes `max(stale, fresh)` at :1511, INVERTING the Scrum/Fold signal on the Manual Fire surface the operator acts from. |
| **Findings** | NF-5, SWARM-A8, NF-107, NF-110, NF-147, NF-47 |
| **Files** | `src/gui/main_window.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Replace `max(stale, fresh)` at :1511 with a **freshness-selected** value plus a staleness indicator. *Correction: a literal "use the fresh value" replacement renders $0.00 on a live position whenever the ticker has not populated — `fresh_pv = holdings*cur_price*qrate if (holdings>0 and cur_price>0) else 0.0`, and the empty-position guard at :1519 requires `holdings <= 0` so it does not catch that case. On the Manual Fire surface that inverts the signal in the opposite direction from NF-5.*
2. Move the `_bot_widgets` writer out from behind `if all_statuses:` at :4818 so an empty fleet clears the Swarm.
3. Repoint the pulse off the retired `_stat_pnl` (NF-107); fix the abbrev tooltip case-mismatch against the uppercased KPI labels (NF-110); restore the discarded Detail tooltip and privacy column comments (NF-147); pass a severity, not a CSS colour, at the NF-47 site.

**Entry gate** — C43 green. A pin computing the Ammo cell from a fixture where `stale > fresh`, observed RED on the baseline.

**Exit gate (measurement):** fixture `stale=100, fresh=40` renders **40** (currently 100); fixture `holdings=5, cur_price=0.0, stats_pv=100` renders **100 with an explicit staleness marker** — not $0.00 and not a bare 100; the marker string is present for the stale case and **absent** for the fresh case (both directions asserted); deleting the last bot leaves `len(_bot_widgets)==0` after one tick; every abbrev tooltip key resolves against the rendered label set (zero unmatched).

**New tests** — `tests/test_dashboard_ammo_freshness.py`, `tests/test_dashboard_ammo_staleness_marker.py`, `tests/test_swarm_clears_on_last_delete.py`.
**Rollback** — restore snapshot (refresh-path commit).

---

### 16 — C54 · BotContainer status/stats dict contract *(v3.24.49, gui-truth)*

| | |
|---|---|
| **Goal** | `get_status()` emits every key its consumers read — `ytd_scrummed_usd`, `ytd_folded_usd`, `portfolio_value`, `passive_value` — with **that bot's own** values, and `BotState.ERROR` is actually written. |
| **Why here** | Hard before C03: the Inflow/Outflow columns read `ytd_folded_usd`/`ytd_scrummed_usd` and the producer does not emit them, so C03's "assert the Outflow cell != $0.00" cannot pass without this. |
| **Findings** | NF-83, NF-84, NF-122 |
| **Files** | `src/trading/bot_container.py`, `src/trading/scrumming_bot.py` |
| **Risk tier** | gui-truth |

**Steps**

1. *Correction — the plan's original step is a category error that C03 would then bless.* `get_status()` at :1242 is a method on **`BotContainer`** (a single bot, class at :836) while the cited aggregation at :2978-2980 sits inside **`BotManager.get_aggregate_stats`** (class at :1412, method at :2931) — a fleet-wide method a `BotContainer` cannot call, and whose body reads `bot.stats.ytd_scrummed_usd`, i.e. exactly the "per-bot stats object" the original step forbids. Sourcing a per-bot key from the fleet aggregate makes every row show the fleet total and inflates the AI Live Monitor's portfolio by 35× at :1719-1726. Emit each bot's **own** `ytd_scrummed_usd`/`ytd_folded_usd`/`portfolio_value`/`passive_value` from `self.stats` (fields already declared at :790-791); `BotManager.get_aggregate_stats` keeps the summation.
2. *Correction — NF-84's `accumulated_fold`/`accumulated_distribute` cannot be fixed by adding `get_status()` keys.* Both are declared at :762-763 with **zero writers anywhere in `src/`**, and their only consumer reads them off `bot.stats` directly (`fleet_replay_panel.py:1061`), not off `get_status()`. Adding them as status keys yields a permanent 0.0 that never reaches the consumer, and the plan's original gate passes trivially by seeding the fixture. Write them at the FOLD/DIST execution sites in `scrumming_bot` — or, if they are dead, move NF-84 to C56 as a delete-and-remove-the-consumer disposition.
3. Write `BotState.ERROR` where consumers expect it.
4. Add a behavioural contract test — the existing pins (`test_status_tab_sources.py:108`, `test_ytd_per_trade_increment.py:56`) assert source **text** and would stay green against a wrong object.

**Entry gate** — C43 green. The behavioural contract test observed RED on the baseline.

**Exit gate (measurement):** seed **two** `BotContainer`s with **different** `BotStats` values; `get_status()` on each returns that bot's own value and the two differ; the manager's aggregate equals their sum. Drive a fold through a bot and assert `bot.stats.accumulated_fold` increased by the folded amount, and that `fleet_replay_panel`'s Mature cell renders that value. Existing regex pins remain green but are recorded as drift detectors only.

**New tests** — `tests/test_bot_status_contract.py` (value-level, two-bot), `tests/test_accumulated_fold_written.py`.
**Rollback** — restore snapshot; added dict keys are ignored by non-readers.

---

### 17 — C07 · Delete the Sim/Paper theatre; restore the parity lock *(v3.24.50, gui-truth)*

| | |
|---|---|
| **Goal** | The Bot Swarm has one row factory; the fake sim/paper builders and the dead live-row API are gone, the surviving factory is pinned, and the register/update/stop API C24 depends on is intact. |
| **Why here** | Doctrine 4/6, before C03 (same file) and before C24 (which makes the summary functions operator-visible for the first time). No test in the 73-file suite mentions "paper" or imports `bot_visualizer`, so this deletion currently has zero regression surface. |
| **Findings** | SWARM-4.16, 4.17, 4.18, T7-1, T7-2, T7-3, T7-11, T7-13, T7-4, T7-7, T7-14, SWARM-A4, NF-2, NF-46, NF-105, RECORD-2, RECORD-3 |
| **Files** | `src/gui/bot_visualizer.py`, `tests/test_swarm_row_parity.py` |
| **Risk tier** | gui-truth |

**Steps**

1. FIRST add a headless construction test building `BotVisualizationTab` offscreen, asserting `register_live_run` inserts a widget and `_create_swarm_row('live',...)` returns the full handle key set. It must pass BEFORE and AFTER — it is the only thing distinguishing "removed the theatre" from "removed the stage".
2. *Correction — scope the deletion explicitly.* The `+ Add / Run All / Stop All` headers (:1313-1327) are built in the **same construction block** as `_sim_swarm_layout` (:1349-1352), which is the insertion point `register_sim_run` uses at :1991-1992 and which C24 depends on to show one Swarm row per Nuclear worker. Deleting the section wholesale reproduces RECORD-3 exactly — an `insertWidget` into a layout assigned nowhere, swallowed by the caller's bare except. **Delete** `_create_sim_bot_row` (:1519-1639), `_create_paper_bot_row` (:1641-1732), their headers, and the `_sim_bots`/`_paper_bots` manual lists. **Preserve** `_sim_swarm_layout`, `_paper_swarm_layout`, `_live_sim_rows` and the `register_/update_/stop_sim_run` API.
3. Extend the step-1 test to assert `register_sim_run('x','label',cfg)` inserts a widget into `_sim_swarm_layout` and returns the full handle key set — the same bar already set for `register_live_run`.
4. Restore the archived `test_swarm_row_parity.py`, RUN IT, and enumerate which assertions fail and why. Its `_SWARM_ACCENTS` regex assertion (keys == {live,sim,paper}) will fail because of the intended deletion plus SWARM-A4, **not** because of RECORD-3 — record this so the wrong red is not read as the expected red.
5. Resolve the dead live-row API: `register_live_run` dereferences `self._live_rows_layout`, assigned nowhere (RECORD-3's "safe no-op" comment is false) — assign it or remove the API, then assert at Qt runtime that it inserts a widget.
6. Fix `_update_sim_summary`/`_update_paper_summary` (:2167-2185): the aggregate-trades literal, the missing `_pnl` stash in `stop_sim_run`, and the paper summary ignoring `_live_paper_rows`.
7. Rewrite `_SWARM_ACCENTS` for the surviving factory and update the restored test's accents assertion to the post-deletion contract (M7 — replacement with consent, recorded).

**Entry gate** — C54 green. Headless construction test passing on the baseline; restored parity test run on the baseline with failures enumerated and classified. **C24's operator decision hoisted here** (below).

**Exit gate (measurement):** the headless construction test passes identically pre- and post-deletion, including the `register_sim_run` clause; the restored parity test is green with its accents assertion rewritten to the documented key set; grep proves zero references to `_create_sim_bot_row`/`_create_paper_bot_row`/`_live_rows_layout`; the summary functions return the seeded aggregate, not a literal.

**New tests** — `tests/test_swarm_row_construction.py` (must pass before AND after), `tests/test_swarm_row_parity.py` restored and rewritten.
**Rollback** — restore snapshot; the restored test file stays as the lock.
**Operator decision** — confirm the Sim/Paper **rows** are theatre to delete. *Correction: C24's decision ("does Nuclear v2 replace the tape-scout path?") is hoisted into this entry gate, because it decides whether the preserved `_sim_swarm_layout` will ever have a producer — C07 must not be asked to delete a surface 17 cascades before the cascade that gives it one is approved.*

---

### 18 — C03 · Bot Swarm list view: real columns, masking, exchange filter *(v3.24.51, gui-truth)*

| | |
|---|---|
| **Goal** | Each row shows its bot's real exchange, masked symbol and non-zero Inflow/Outflow from the status dict; the exchange filter actually filters; and the locust hover tooltip stops leaking in the clear. |
| **Why here** | Hard after C54 (the keys must exist), after C04 (the filter interaction was swallowed) and after C07 (same file). All fixes read the same `_bot_data` dict in one ~170-line span. |
| **Findings** | SWARM-4.4, 4.5, 4.6, 4.7, 4.15, SWARM-A9, SWARM-4.11, SWARM-A5 |
| **Files** | `src/gui/bot_visualizer.py`, `src/gui/bot_swarm_list.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Rewrite `_bot_exchange_id` (:2364-2385) to read `status['exchange']`; remove the dead `get_bot_container` import and the `StateManager` fallback, and the duplicate fallback in `QuickRoutingMatrix._symbol_for`.
2. Rewrite `_refresh_bot_list_rows` (:2490-2530) to render `ytd_scrummed_usd`/`ytd_folded_usd` from the C54 keys and to mask `_data.get('symbol')` at :2512.
3. *Correction — SWARM-4.7 has a second half the plan resolves nowhere.* `BotNodeWidget.paintEvent` masks the painted labels at :685 and :704 but interpolates the **raw** symbol and raw `bot_id` into the tooltip at :712-720, and `bot_swarm_list.py` has zero `mask_or` references. Route the tooltip through `_mask_or` with the same `bot_swarm.identifiers` field id. Sequenced before C08 so C08's hoist moves already-masked text.
4. Make `_on_exchange_filter_changed`/`_refresh_visible_bots` (:2440-2460) filter on the real exchange id.
5. Stop the `set_bots` item churn in `bot_swarm_list`; apply the theme in the same paint loop (SWARM-A5).

**Entry gate** — C54, C04, C07 green. Restored bot-swarm list pins observed RED on the baseline.

**Exit gate (measurement):** with a seeded fleet whose aggregates are non-zero, the rendered Outflow cell TEXT is non-zero for every folding bot, **and at least two rows render DIFFERENT Outflow values** for a fleet seeded with different per-bot `ytd_folded_usd` (the clause that fails if C54 regressed to a fleet aggregate); selecting an exchange changes the row count to the expected number; the rendered symbol equals `mask_or(symbol)`; with privacy mode ON, `BotNodeWidget.toolTip()` contains neither the raw symbol nor the raw `bot_id` prefix; `set_bots` called twice with identical input creates zero new `QListWidgetItem`s.

**New tests** — `tests/test_bot_swarm_list_rows.py`.
**Rollback** — restore snapshot (loop rewrite).

---

### 19 — C09 · Lane canvas: exhaustion visibility + endpoint resolution *(v3.24.52, gui-truth)*

| | |
|---|---|
| **Goal** | A wire that cannot be assigned a lane is reported rather than silently dropped, and endpoint resolution stops linear-scanning rows per paint. |
| **Why here** | Doctrine 4, same file as C03 and immediately after it. Collision to manage: `tests/test_bot_swarm_list.py:247` `test_wire_canvas_ignores_unknown_bot` asserts the silent skip is CORRECT — that pin encodes the defect. |
| **Findings** | SWARM-A3, SWARM-4.14 |
| **Files** | `src/gui/bot_swarm_list.py`, `tests/test_bot_swarm_list.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Record in writing, before editing, that `test_wire_canvas_ignores_unknown_bot` encodes the defect; replace it with a pin asserting the skip is REPORTED while still not being assigned a lane. Do **not** relax the assertion in place (M7).
2. Leave `test_returns_none_when_all_lanes_full` (:67) untouched — allocator exhaustion is a separate legitimate pin that must stay green.
3. Make `if lane is None: continue` at :284-286 increment a visible skipped counter and surface it.
4. Replace `row_of_bot`'s linear scan at :287-288 with a dict built once per paint.

**Entry gate** — C03 green. The replacement pin written and RED on the baseline; **operator acknowledgement recorded** that the old pin is being replaced, not relaxed.

**Exit gate (measurement):** a wire to an unlisted bot leaves `_lane_assignments` without an entry AND increments the reported skip counter by exactly 1; a paint over N rows performs O(1) endpoint lookups (assert `row_of_bot` is not called in the loop).

**New tests** — `tests/test_bot_swarm_list.py::test_wire_canvas_reports_unknown_bot` (replaces the old pin).
**Rollback** — restore snapshot (source and test replacement together).
**Operator decision** — approve replacing a currently-green pin whose name asserts the present behaviour is correct.

---

### 20 — C11 · Main-window dead startup branches: implement or delete *(v3.24.53, record-only)*

| | |
|---|---|
| **Goal** | Boot no longer raises `AttributeError` into a bare except, and no `hasattr` guard protects a structurally impossible branch. |
| **Why here** | Doctrine 4/5, cheap, and it precedes C49, which makes the same wire-or-delete decision systematically. *Correction: the boot smoke test that was this cascade's deliverable moved to CV1 (order 2) — it is the only boot-level regression detector this repo has (`grep -rn 'MainWindow(' tests/*.py` returns zero), and thirteen GUI cascades edit window construction between there and here. Only the two dispositions remain at this position.* |
| **Findings** | NF-162, NF-109 |
| **Files** | `src/gui/main_window.py`, `src/gui/simulator_tab/simulator_tab.py` |
| **Risk tier** | record-only |

**Steps**

1. Decide per branch: implement `set_bot_viz` on `SimulatorTab` (zero definitions repo-wide today, called at :3816), or delete the call.
2. Delete the unreachable `_paper_trader` branch at :3819 (`_paper_trader` is hard-assigned `None` at :3779; Paper is gated behind Sim+Nuclear and no Paper source file exists, so deletion is the honest option).
3. Convert the surrounding bare `except Exception: pass` into a logged, named handler so the next silent boot failure is visible.

**Entry gate** — CV1's boot smoke test green and its swallowed-exception counter recorded.

**Exit gate (measurement):** offscreen main-window construction raises zero exceptions into the boot guard (handler counter == 0) and grep shows zero references to `set_bot_viz` and to the dead `_paper_trader` branch.

**New tests** — extends `tests/test_main_window_boot_smoke.py`.
**Rollback** — restore snapshot; deletions are recorded in the commit for C49 to reconsider.
**Operator decision** — implement `SimulatorTab.set_bot_viz` or delete the call?

---

### 21 — C52 · History tab trade grader time inversion *(v3.24.54, gui-truth)*

| | |
|---|---|
| **Goal** | Letter grades are computed with the time axis in the correct direction. |
| **Why here** | Doctrine 4, fully headless, cheap, self-contained. `history_tab.py:699-702` treats page rows as oldest-first when they are newest-first, so every grade and grade tooltip is computed reversed. |
| **Findings** | NF-16 |
| **Files** | `src/gui/history_tab.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Flip `ref_price_at_decision` and `future_prices` together in the same loop — flipping one half leaves grades wrong and unflagged.
2. Note in the CHANGELOG that previously displayed or screenshotted grades are non-comparable after this change.

**Entry gate** — C43 green. A pure-function pin with a hand-built newest-first page and a known-correct letter grade, observed RED on the baseline.

**Exit gate (measurement):** for the hand-built fixture the computed grade equals the hand-derived correct letter **and differed before** the fix; the fifteen existing tooltip pins remain green.

**New tests** — `tests/test_history_grade_ordering.py`.
**Rollback** — restore snapshot (two-line region).

---

### 22 — C53 · Extractor: live position display + config mutation window *(DEFERRED TO SERIES TAIL, gui-truth)*

> **DEFERRED 2026-08-07 by operator directive.** Skipped in place; the
> sequence continues at #23.
>
> > "Extractor Bot has never met functional release criteria. Common
> >  asset sharing between bots and attempts to engineer bot
> >  inoperability protocols and rules have thus far failed. Can add
> >  this to the end of our current cascade series along with the
> >  re-implementation of the Paper Trader Tab."
>
> The Extractor's blockers are architectural — asset contention between
> bots, and no working stand-down protocol — not the two display and
> hygiene defects below. Correct display of a subsystem that cannot be
> released has no consumer, so this rides at the tail with the Paper
> Trader work rather than ahead of 43 items that ship into live use.
>
> Nothing here is withdrawn; NF-85 and NF-58 are still real. Note that
> `extractor_bot.py` has **zero test coverage** (verified 2026-08-07),
> so the two pins named below remain the first tests for a 1702-line
> file, and no existing pin encodes the defect — M7 consent is not
> required when it is eventually run.
>
> **Tail additions queued alongside it:** re-implementation of the Paper
> Trader Tab. Paper is currently absent from crypto entirely —
> `main_window` hard-assigns `_paper_trader`, `_paper_trader_stack`,
> `_paper_trader_crypto` and `_paper_trader_equity` to `None` (C11
> deleted the unreachable branch that referenced them), no crypto Paper
> source file exists, and Paper sits behind Sim + Nuclear in the
> promotion pipeline.

| | |
|---|---|
| **Goal** | Current (USD) reflects the live ticker rather than the position's own entry price, and manual fire stops mutating shared config across an await. |
| **Why here** | Doctrine 4. Neither change alters order sizing (that is C40c). `positions_for_gui` currently sets `current_price` to the average buy price, so a drawdown position shows a positive delta beside a red DRAWDOWN cell. |
| **Findings** | NF-85, NF-58 |
| **Files** | `src/trading/extractor_bot.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Cache the ticker already fetched in `tick()` step 1 and use it for `current_price`; extend `export_state`/`import_state` so the cache survives restart without falsifying the display.
2. Replace `manual_fire_position`'s config mutation with an explicit `exit_pct` parameter, removing the try/finally restore dance and the cross-await shared-state window.

**Entry gate** — C43 green. A pin asserting a drawdown position renders a NEGATIVE delta, observed RED on the baseline.

**Exit gate (measurement):** fixture with `avg_buy=100` and `ticker=80` renders Current (USD) from 80 and a negative delta; a concurrent tick during `manual_fire_position` observes `config.exit_pct` unchanged throughout (asserted on a recorded sequence, not a sleep).

**New tests** — `tests/test_extractor_positions_for_gui.py`, `tests/test_extractor_manual_fire_no_config_mutation.py`.
**Rollback** — restore snapshot; `export_state` gains a field older code ignores.

---

### 23 — C35 · Topology proposal ranking + dismissal persistence *(v3.24.56, gui-truth)*

| | |
|---|---|
| **Goal** | `sector_cluster` proposals rank on more than cluster size, and a 24 h dismissal actually lasts 24 h. |
| **Why here** | Doctrine 4, self-contained. `topology_proposals.py:479` scores on cluster size so nine sectors tie at the 100.0 ceiling and iteration order picks the leader; `market_inspector_topologies.py:308`'s dismiss cache is memory-only while the prompt promises 24 h. |
| **Findings** | SWARM-4.28, SWARM-4.29 |
| **Files** | `src/trading/topology_proposals.py`, `src/gui/market_inspector_topologies.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Add a tie-breaking signal so the 100.0 ceiling is not reachable by size alone; make ranking deterministic under shuffled input.
2. Persist the dismissal cache with its timestamp through the settings namespace and honour it on restart.

**Entry gate** — C43 green. A pin feeding shuffled sector input and asserting a stable leader, observed RED on the baseline.

**Exit gate (measurement):** over 20 shuffles of the same input the ranked leader is identical every time and fewer than 2 proposals share the top score; dismiss a card, restart the tab, it is still suppressed and returns only after the persisted timestamp + 24 h.

**New tests** — `tests/test_topology_proposal_ranking_stability.py`, `tests/test_topology_dismiss_persistence.py`.
**Rollback** — restore snapshot; the persisted key is ignored by older code.
**Operator decision** — the secondary ranking signal (liquidity, correlation, existing bot coverage).

---

### 24 — C26 · Fleet Replay panel: control state + operator visibility *(v3.24.57, gui-truth)*

| | |
|---|---|
| **Goal** | Start/Stop/Reset form a correct state machine, every failure path says why, a long run cannot be reset out from under the operator without confirmation, and Start does not freeze the Qt thread. |
| **Why here** | Doctrine 4/5, hard after C14 — until C14 lands, every Start/Stop/Reset cycle this cascade's test module drives writes the operator's live telemetry files, turning a run-frequency breach into a test-frequency breach. |
| **Findings** | SN-31, SN-12, SN-13, SN-14, SN-35, SN-34, SN-29 |
| **Files** | `fleet/fleet_replay_panel.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Route all nine failure sites through `_status_error` (SN-31), including a try/except around `_do_fetch` (SN-12).
2. `_on_reset_clicked` (:455-468): stop both timers, null `_controller`, clear `_gate_cells`, and confirm when a run is in flight (SN-13 + SN-35).
3. `_on_start_clicked` (:664+): re-entrancy guard, plus a status line on the bare return at :665-666.
4. SN-34: *correction — memoisation alone does not fix this and the plan's exit gate does not measure it.* Collapsing three trade-log walks into one leaves the surviving walk running synchronously on the Qt main thread inside `_on_start_clicked`, and `_live_trade_timestamps` (:567-599) returns early only `if out:` — falling back to a full `live_trades()` read whenever `_ytd_trades` is empty, which SN-29 says is the normal condition. Move the walk off the Qt thread (worker + signal, matching C38's pattern), **or** keep memoisation and adopt C38's explicit stall measurement.
5. Report when the parity check is skipped because `_ytd_trades` is empty (SN-29).

**Entry gate** — C14 green AND CV1's file-granularity guard active. The offscreen GUI test module written and RED on the baseline. Pre-change maximum main-thread block during `_on_start_clicked` **measured and recorded**.

**Exit gate (measurement):** after Reset both timers are stopped, `_controller` is None and `_gate_cells` is empty; double-clicking Start constructs exactly one controller; every failure path leaves a non-empty status string (assert none is `''`); an empty `_ytd_trades` produces a named "parity skipped" status; the maximum contiguous main-thread block during `_on_start_clicked` is under a stated bound and strictly below the recorded pre-change figure; the full Start/Stop/Reset cycle leaves both live roots byte-identical.

**New tests** — `tests/test_fleet_replay_panel_state_machine.py`.
**Rollback** — restore snapshot (panel commit).

---

### 25 — C28 · Chart Expand re-entrancy *(v3.24.58, gui-truth)*

| | |
|---|---|
| **Goal** | A second Expand cannot orphan the chart into a hidden `QDialog`, and the dialog is destroyed on close. |
| **Why here** | Doctrine 4, five lines, and landing it before C29 keeps the marker cluster's visual verification from being confounded by an orphaned chart. |
| **Findings** | SN-10, SN-36 |
| **Files** | `fleet/sim_visuals.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Add a re-entry guard to `_show_expanded` (:43-102) so dialog #1 cannot be captured as `prior_parent`.
2. Set `WA_DeleteOnClose`; restore `minimumHeight` only when this call changed it.

**Entry gate** — C43 green. A pin calling `_show_expanded` twice and asserting the chart's parent, observed RED on the baseline.

**Exit gate (measurement):** two successive Expand calls leave `chart.parent()` equal to the original parent after close, and the dialog object is destroyed (weakref dead).

**New tests** — `tests/test_sim_visuals_expand_reentrancy.py`.
**Rollback** — restore snapshot (five lines).

---

### 26 — C29 · Sim chart markers: anchoring, axis, lifecycle *(v3.24.59, gui-truth)*

| | |
|---|---|
| **Goal** | A trade marker sits on the candle the trade occurred on, before and after decimation, and marker state is cleared and bounded. |
| **Why here** | Doctrine 4, after C28. The marker loop at `fleet_replay_panel.py:1238` runs BEFORE the append at :1268, so `mark_trade` pins the previous drain's point; the halving decimation then warps the axis, making the offset variable and invisible by eye. |
| **Findings** | SN-15, SN-16, SN-30, SN-37, NF-51 |
| **Files** | `fleet/sim_visuals.py`, `fleet/fleet_replay_panel.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Reorder the drain so `append_tick` precedes `mark_trade`, and anchor markers by **timestamp** rather than index so decimation cannot move them.
2. Make `clear_data` also clear `_markers`, and give `clear_markers` a real call site (SN-30).
3. Bound `_markers` with a `deque(maxlen=)` (SN-37).
4. Fix `clear_gates` so the LS LED is cleared too (NF-51).

**Entry gate** — C28 green. A numeric pin using a synthetic series with a uniquely identifiable spike candle, observed RED on the baseline.

**Exit gate (measurement):** the stored marker index equals the spike index at a series length BELOW the decimation threshold and at one ABOVE it (two runs, both exact); `clear_data` leaves `len(_markers)==0`; after 10× the cap `len(_markers)==cap`; `clear_gates` leaves the LS LED off.

**New tests** — `tests/test_sim_chart_marker_anchoring.py`.
**Rollback** — restore snapshot (both files).

---

### 27 — C17 · Inject the bus and the singletons instead of resolving them *(v3.24.60, live-behaviour)*

| | |
|---|---|
| **Goal** | No object constructed on a sim path subscribes to or emits on the process-wide EventBus, and subscriptions can be retracted. |
| **Why here** | Keystone of the sim band: hard predecessor of C22, C23, C46, and **C20 (promoted to hard per hazard)**. `BotManager.__init__` resolves `get_event_bus()` and subscribes three handlers at :1461/:1465/:1466 BEFORE `nuclear_controller.py:262` can rebind `._bus`. Cold read confirms `event_bus.py` has an unsubscribe **closure** at :120 but no unsubscribe **method**, and every caller discards the closure. |
| **Findings** | SWARM-4.23, SN-42, SN-39, SN-44, NF-9 |
| **Files** | `src/trading/bot_container.py`, `phantom_balance.py`, `src/core/event_bus.py`, `logging_engine.py`, `src/exchange/idempotency.py`, `nuclear_controller.py`, `scrumming_bot.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Add `EventBus.unsubscribe` (NF-9) — the capability all of these need — plus a subscriber-count accessor for the exit gate.
2. Add a `bus` parameter to `BotManager.__init__` **used before** the three subscribe calls; same for `PhantomBalanceBot` (:150) and `TimeframeCoordinator` (:313). *Scope correction: `SmartWireManager` takes no bus and emits nothing, so SN-28's stated fix is misdiagnosed — the nuclear leak is `BotManager` at `nuclear_controller.py:261`.*
3. Reach the constructions **inside** `ScrummingBot`: :414 does `self._coordinator = coordinator or TimeframeCoordinator()` AFTER the private-bus swap at :372 and does not pass it — thread `self._bus` into the coordinator and each phantom.
4. Make the sim private-bus swap **FAIL CLOSED**: if the private `EventBus` cannot be constructed, raise out of `__init__` so the sim bot is never built (it currently logs a warning and keeps the global bus). This is the precondition C22 depends on.
5. Same injection for `get_idempotency_layer()` (SN-44).
6. Add explicit detach in `nuclear_controller` teardown (:416) and in the fleet controller's `finally`.

**Entry gate** — C14 and C15 green. `tests/test_nuclear_scout_isolation.py:97` (which already encodes this trap for one constructor) generalized to all four and observed RED for three of them.

**Exit gate (measurement):** for `BotManager`, `PhantomBalanceBot`, `TimeframeCoordinator` and the idempotency layer, `obj._bus is not get_event_bus()`; `get_event_bus()` subscriber count is IDENTICAL before and after a full sim Start/Stop cycle (currently it grows by 3 per replay and never shrinks); a forced private-bus construction failure ABORTS the sim run.

**New tests** — `tests/test_bus_injection_isolation.py`, `tests/test_event_bus_unsubscribe.py`, `tests/test_sim_bus_fail_closed.py`.
**Rollback** — restore snapshot; the `bus` parameter defaults to `get_event_bus()`, so live construction sites are unchanged either way.

---

### 28 — C22 · Restore the sim trade-notification trace *(v3.24.61, sim-only)*

| | |
|---|---|
| **Goal** | A sim run records SENT/PLACED/FILLED/CANCELLED, including the CANCELLED reason string — the only place a sim run records WHY a trade did not fire. |
| **Why here** | Hard after C17 and only once the fail-closed bus lands: `scrumming_bot.py:1966`'s `if self._sim_mode: return` is currently the belt stopping sim notifications from reaching live subscribers, and the private-bus swap at :371-378 is fail-open today. |
| **Findings** | SN-54 |
| **Files** | `src/trading/scrumming_bot.py` |
| **Risk tier** | sim-only |

**Steps**

1. Confirm C17's fail-closed assertion is in force for every sim construction path (fleet, nuclear, tests).
2. Remove the `sim_mode` early return at :1966.
3. Assert at sim instantiation that `bot._bus is not get_event_bus()` for every constructed bot.

**Entry gate** — C17 green with its subscriber-count measurement recorded.

**Exit gate (measurement):** a 200-candle sim run produces a non-empty SENT/PLACED/FILLED/CANCELLED trace in the run directory with at least one CANCELLED reason string, AND `get_event_bus()` receives ZERO events during that run (instrumented counter, not absence of sound).

**New tests** — `tests/test_sim_trade_trace.py`.
**Rollback** — restore the one-line guard.

---

### 29 — C16 · SIM GATE: make capital reservations actually succeed in sim *(v3.24.62, sim-only)*

| | |
|---|---|
| **Goal** | Sim reservations succeed on the first ensure so the "SELL REFUSED (capital reservation)" branch becomes reachable — without inflating sim inventory above live. |
| **Why here** | Hard after C15, whose absence would make this cascade's assertion measure — and its run mutate — the live reservation file. It changes which sim SELLs fire, so it rides alone with a decision diff. |
| **Findings** | SN-5 |
| **Files** | `fleet/fleet_replay_controller.py`, `src/trading/scrumming_bot.py` |
| **Risk tier** | sim-only |

**Steps**

1. Take the pass-`total_holdings=None`-on-first-ensure option, which the docstring at `scrumming_bot.py:996-999` already blesses. Do **NOT** seed sim holdings at the reservation ceiling: the 1.10 in `_compute_reservation_qty` (:986) is a live over-commit headroom constant, and seeding there gives every sim bot 110% of a live bot's base units, making sim out-scrum live and be misread as the fix working.
2. Keep sim holdings seeded at exactly `target/open_px` so sim and live start from identical inventory.
3. Produce a before/after sim SELL decision diff per symbol.

**Entry gate** — C15 green; the reservation-count assertion confirmed to run against the injected private registry only.

**Exit gate (measurement):** *correction — the plan's original clause (`len(registry._reservations) == number of instantiated bots`) is wrong for the data model and fails a correct fix.* `_reservations` is keyed by a fresh `uuid4().hex` **token** (`capital_reservation.py:323-335`), lookups filter by `bot_id` (:445), and a bot with `target_balance == 0` or no first candle yields `qty == 0.0` (`scrumming_bot.py:982-987`) which `reserve()` rejects at :300-302. Assert instead: for **every bot with `_compute_reservation_qty() > 0`**, exactly **one** reservation token exists with `r.bot_id == bot.bot_id`, and the set of reserving bot_ids equals the set of eligible bot_ids; no bot holds more than one token after N ticks (the idempotent-update contract); the over-commit raise fires 0 times per tick (was every bot every tick); sim seeded holdings are UNCHANGED from the pre-fix seed (assert equality); plus a before/after table of sim SELL decisions per symbol.

**New tests** — `tests/test_sim_reservation_succeeds.py`.
**Rollback** — restore snapshot; sim-only, no persisted live state touched.

---

### 30 — C18 · SIM GATE: TA and phantom input fidelity *(v3.24.63, sim-only)*

| | |
|---|---|
| **Goal** | Sim phantoms read their own timeframe's series, honour the persisted per-bot `phantoms_enabled`, and resolve timeframe availability against the real venue. |
| **Why here** | Hard after C14 and after C15/C16. The three defects interact — SN-57 alone moots most of SN-1's blast radius — so one combined decision diff is the only readable verification. |
| **Findings** | SN-1, SN-57, SN-58 |
| **Files** | `fleet/sim_exchange.py`, `fleet/fleet_replay_controller.py`, `fleet/bot_state_loader.py` |
| **Risk tier** | sim-only |

**Steps**

1. Remove `del timeframe` from `FleetSimExchange.get_ohlcv` (:267-291) and serve the requested timeframe, so the six phantoms stop reading the identical 5 m series into `get_higher_tf_bias` (which blocks SCRUM at `scrumming_bot.py:6786`).
2. SN-57: make phantom enablement an explicit per-run panel toggle **defaulting to the persisted per-bot value** (all 35 bots record `phantoms_enabled=False`). Do not hard-disable — C17 and C46 change phantom code and would otherwise be "verified" by a replay in which `_tick` never ran.
3. SN-58: do **NOT** add a `fleet_sim` key to `src/exchange/timeframes.py` — that is a sim identifier in a live table, and it would silently apply Coinbase's set to a future Kraken fleet (M9). Carry the real venue on the sim bot and resolve availability from it.
4. **HAZARD GATE:** restoring the real `exchange_id` makes the sim's `MarketDataPool` key (`{exchange_id}|{symbol}|{timeframe}`) identical to live's — namespace the sim key or inject a per-run `MarketDataPool`, and forbid `get_data_pool()` from any simulator path.

**Entry gate** — C14, C15, C16 green. A probe confirming no key in `get_data_pool()._candles` is touched during a replay.

**Exit gate (measurement):** (a) the six phantoms return six DIFFERENT series (pairwise inequality of last-candle timestamps); (b) with phantoms defaulted from persisted state, zero phantoms are constructed for the 35 recorded bots, and six with the toggle forced on; (c) no 4h phantom exists for a Coinbase-sourced bot; (d) zero `MarketDataPool` keys mutate during a replay; (e) a combined before/after sim SCRUM/FOLD decision table per symbol.

**New tests** — `tests/test_sim_exchange_timeframe_fidelity.py`, `tests/test_sim_phantom_enable_defaults.py`, `tests/test_sim_pool_key_isolation.py`, plus **direct unit pins on `PhantomBalanceBot._tick` and `TimeframeCoordinator`** so C17/C46 are not verified only by a phantom-less replay.
**Rollback** — restore snapshot; a partial revert re-creates the SN-1/SN-57 interaction.
**Operator decision** — default phantom state for parity runs: match live (off, faithful) or force on (covers the phantom subsystem). Recommend default-off with an explicit toggle.

---

### 31 — C19 · SIM GATE: order-execution realism (both sim venues) *(v3.24.64, sim-only)*

| | |
|---|---|
| **Goal** | Sim orders check balance before settling, can rest unfilled, lock capital while resting, and honour real per-symbol limits — identically in `FleetSimExchange` and `NuclearSimExchange`. |
| **Why here** | After C16 (with reservations failing every tick the SELL path never reaches the order layer in a representative state). SN-18 and SN-19 must land together or fixing the resting-order test alone creates a double-pledged-capital bug. |

> **SN-18 CLOSED 2026-08-07 AS NOT-A-DEFECT.** Do not re-open without
> reading this first.
>
> The finding says the `crosses` test is "unconditionally true for every
> order the bot places". That is TRUE, and it is INTENDED.
> `execution_discipline.fill_price` applies one-directional adverse
> slippage (`abs(random.gauss(...))`), and the bot places its LIMIT at
> that slipped price — so a sell lands below the bid and a buy above the
> ask, marketable by construction.
>
> `scrumming_bot.py:10929` documents why: *"For LIMIT orders the
> exec_price below already includes a -0.1% drift for **fast fill**"*.
> The bot deliberately places a marketable limit to guarantee execution,
> and `verify_hit` is the cap that CANCELS when that drift exceeds
> per-asset-class tolerance. Limits crossing is the designed outcome.
>
> **Removing the `abs()` would make live orders less likely to fill** —
> a strategy change degrading execution on a live fleet, dressed as a
> bug fix.
>
> What is genuinely true is narrower and is NOT a correctness defect:
> Fleet's resting-order model is never exercised by the fleet, because
> the fleet never places a non-marketable limit. A coverage gap in the
> harness. The resting code works and is pinned directly by
> `tests/test_fleet_sim_infrastructure.py`.
>
> Shipped alongside this closure (v3.24.69): `fill_price` described
> itself as a *"zero-mean half-normal"* draw, which is a contradiction —
> `abs()` of a zero-mean normal is a half-normal with mean
> `spread × √(2/π)`, strictly positive. The wording invited the
> conclusion that slippage averages out over many fills. It does not:
> over N fills the expected cost is `N × price × spread × √(2/π)`.
> Corrected, and pinned behaviourally by
> `tests/test_slippage_is_adverse.py`.
>
> **SN-19 stands and is unaffected** — `Balance.used` is still hardcoded,
> and resting orders still pledge nothing.
| **Findings** | SN-17, SN-18, SN-19, SN-20, SN-21, NF-7 |
| **Files** | `fleet/sim_exchange.py`, `nuclear_sim_exchange.py`, `stone_tablets/addressing.py` |
| **Risk tier** | sim-only |

**Steps**

1. Add a balance check before `_settle_fill` (:294-371).
2. Fix the `crosses` test at :362-364 (unconditionally true for every order the bot places) AND `Balance.used` (hardcoded 0.0 at :296) in the **same edit** — resting orders must lock what they pledge.
3. Replace fabricated uniform limits (SN-20) with real per-symbol limits, and make `IOC_LIMIT` supported rather than raising (SN-21) — Stack Mode (C40a) depends on `IOC_LIMIT` being simulable.
4. Stamp fill addresses with tablet indices, not window indices (NF-7).
5. **HAZARD:** apply the identical contract to `NuclearSimExchange` (`used=0.0` at :211/:218-219, its own `place_order` at :223) or extract a shared stateless fill/settlement helper both fork bodies call — otherwise the two harnesses disagree and neither is authoritative.

**Entry gate** — C16 green. A pin parameterised over BOTH sim exchanges written and RED on the baseline.

**Exit gate (measurement, parameterised over both venues, identical results required):** an order exceeding balance is REFUSED; a limit order away from the market REMAINS OPEN after N ticks; while resting, `Balance.used` equals the pledged amount; an `IOC_LIMIT` order does not raise; a fill's stamped address resolves to the same candle in the tablet as in the window.

**New tests** — `tests/test_sim_order_realism.py`.
**Rollback** — restore snapshot (both venue files together).

---

### 32 — C20 · `_build_sim` must construct what live has — without importing live stateful classes *(v3.24.65, sim-only)*

> **AMENDED 2026-08-07 after a six-cluster cold read.** Ten defects found in
> the text below; the original is preserved at the end of this block. Full
> evidence: [`2026-08-07_C20_cold_read.md`](2026-08-07_C20_cold_read.md).
>
> **The headline: steps 2+3 as originally written would have shipped a lie** —
> a harness importing 40 wires, logging "40 wires active", and routing **$0.00**,
> with exit gate (c) going GREEN on it. Sim bots carry fresh `uuid.uuid4()[:8]`
> ids (`bot_container.py:881`) while wires are keyed by the persisted live id
> (`smart_wire.py:344-346`). Disjoint key spaces. The join key already exists —
> `bot_state_loader.py:86` stamps `_src_bot_id` — and is read by **nothing**.

| | |
|---|---|
| **Goal** | The primary parity harness routes the persisted Smart Wires — actually routes them, not merely reports them — and computes anchor indices in the master clock's index space. |
| **Why here** | After C17 and C18 (attribution: two large uncorrelated causes in one diff is unreadable). *Corrected: the original "Why here" justified this on an unretractable global-bus leak from constructing a `BotManager`. Both halves were stale. The three subscribes are `bot_container.py:1626/:1631/:1633`, not `:1461/:1465/:1466` (which is inside `BotContainer`), and C17 already made them retractable — `:1563 self._bus_unsubs`, `:1636 def detach_bus()`, bus injectable at `:1542/:1580`. A third wrong set (`:1598/:1602/:1603`) circulates in the repo's own comments. "Do not construct a `BotManager`" still holds, but for the mundane reason that a replay has no use for one.* |
| **Findings** | SN-8 (closed, not-a-defect), SN-55 (re-scoped), NF-18 |
| **Files** | `fleet/fleet_replay_controller.py`, `fleet/fleet_replay_panel.py`, `trading/smart_wire.py`, `nuclear_fleet_controller.py` |
| **Risk tier** | sim-only |

**Steps**

1. ~~Construct `VolumeGuard` and `MarketDataPool` on the controller.~~ **STRUCK — dead work in both halves (SN-8 closed).**
   - *VolumeGuard:* `volume_guard.py:190` — the `enabled` property's whole body is `return False` (MEM-259), and the setter at `:192-196` is documented as not affecting it. The sole read is `bot_container.py:1048` `if self._volume_guard and self._volume_guard.enabled:`. Live (guard, `.enabled` False) and sim (guard `None`) take the **identical** else-branch. This fix reaches no read path. Ship a regression pin instead — see tests.
   - *MarketDataPool:* the plan inverted. Sim's `_data_pool = None` (`bot_container.py:893`) is the **safety property**, documented as a HAZARD at `fleet_replay_controller.py:282-287` (not `:282-290`). The pool has no job in a replay, and `refresh_all_tickers`'s only callers (`bot_container.py:1833`, `:1868`) are `BotManager` methods this step forbids constructing. The plain import form also trips the shipped pin at `tests/test_sim_ta_input_fidelity.py:91-93`, so the step is satisfiable only by evading a test.
2. **Remap the bot id FIRST, before any manager exists.** In `_build_sim`, immediately after `_instantiate_bot` returns, `bot.bot_id = str(cfg["_src_bot_id"])`, failing **loudly** if the key is absent. Mirrors live's own `bot_container.py:3160-3161` `# Preserve original bot ID` / `bot.bot_id = bid`, which is precisely why live's `import_wires` works. *Ordering hazard: this must land before anything else keys off `bot_id` — per-bot parity diffs, run-log attribution, capital-reservation comparison all currently see uuid4s.*
3. Construct a `SmartWireManager(bus=<a private EventBus owned by the controller>)` **after** the bot loop so both endpoints resolve. *Corrected: the original said "the class has no bus and no singleton". No singleton is right; **no bus is wrong** — `smart_wire.py:214-217` takes `bus=None`, `:231` stores it, and `:507-511` / `:695-698` fall through to `get_event_bus()` and emit `bot.log`. `smart_wire.py:220-226` quotes the original sentence and answers "That correction is itself wrong" — shipped in C17. No single sim bus exists to borrow; each sim bot builds its own `EventBus()` at `scrumming_bot.py:394`.*
4. `import_wires` + `attach_bot`, and **compute** the ACTIVE count — both endpoints must be in the sim fleet, which `available_symbols` (`:578`) filters. `import_wires` (`smart_wire.py:456-478`) does no existence check and returns `n` for every well-formed row, so reporting its return value is the green-log-zero-effect failure this cascade exists to catch. Do **NOT** call `import_ledgers`: live's persisted `wired_in == wired_out == $1,047.4917` (48 rows, 13 orphaned) would satisfy the exit gate without a single sim wire firing.
5. **NF-18:** compute anchor indices in the master-clock index space. `fleet_replay_controller.py:1154` computes `(ts*1000 - base) // 300_000`, a slot on a gapless ruler; `:932-933` compares it against `candle_i`, the MasterClock cursor — a position in `sorted(union)`. Nothing converts between them. *Two amendments the original omitted:* **(a)** the **bound** is in the wrong space too — `fleet_replay_panel.py:1027-1029` passes `progress.total_candles or max(len(r) for r in candles.values())`, and `progress.total_candles` is assigned only at `controller:417-418`, **after** `_build_sim()` at `:411` and after the panel built anchors at `panel:1090`, so the fallback fires on every run. **(b)** severity, MEASURED on all 35 live tablets 2026-08-07: union 61,201 candles (2026-01-01 → 2026-08-01), **79 missing slots across exactly 3 gaps** — +1 after 02-19, **+77 after 05-08 01:15** (~6.4 h outage), +1 that evening. **No trade is dropped**: drift 79 < warmup 100, so the true candle stays inside `range(idx-100, idx+1)`. The loss is warm-up DEPTH — **21 real warm-up candles instead of 100** for every trade after 2026-05-08, on a harness whose purpose is that simulated indicators match live. **Margin: 21 candles.** The bound half is minor: longest single series 61,200 vs union 61,201, off by **one**.
6. Fix `nuclear_fleet_controller.py:551` `mgr = SmartWireManager()` — bus-less, so its wire logs land on the operator's **live** bus while the sim bots around it are fail-closed onto private ones (`scrumming_bot.py:393-394`). The original cited this line as the **precedent to copy**; it is the leak. Fix here or hand it to C23 step 7 **in writing**.

**Entry gate** — C17, C18, C19 green.

**Exit gate (measurement).** *All five original criteria were rewritten; two were unsatisfiable and two would have passed on the unfixed baseline.*
(a) A **spy** subscribed to the live `get_event_bus()` for `bot.log` receives ZERO events during a replay, with a premise control proving the spy fires for a deliberately bus-less manager. *The original's subscriber-count criterion is vacuous here: a `SmartWireManager` emits but never subscribes, so the exact risk step 3 introduces leaves the count untouched. Use `subscription_fingerprint()` over a bare count — a total cannot distinguish "+3 leaked" from "+1 leak, +2 legitimate".*
(b) `set(mgr._bot_refs) == {b.bot_id for b in ctl._bots}`. *After step 2 those ids ARE the live ids — that is the point — so this compares against the sim fleet, not against "not a live id". The original's second half is unsatisfiable: `get_bot_manager()` **does not exist** anywhere in `src/` or `main.py`.*
(c) ACTIVE wires == endpoint-resolved count (**computed**, never the import count), and `wired_in` accrued **from zero** during the replay. *40 is the right import count — verified: 40 rows, 23 distinct sources, 4 targets, 0 dangling endpoints, all 35 bots `mode=='scrumming'`.*
(d) Anchors resolve to union positions on a union with a **planted gap**. *The original's hand-checked candle would pass unfixed — the operator's normal window is gapless, so grid == union for every trade.* Plus: `n_candles` equals the union size, not `max(len(series))`.
(e) `ScrummingBot.apply_wire_income` is never called on an object outside `ctl._bots`, covering all THREE `_bot_refs` dereferences — `smart_wire.py:529` (source), `:580` (fold target), and the scrum-time reach at `scrumming_bot.py:1800/:1835/:1840`. *The original's "live `bot_state.json` byte-identical" is unsatisfiable in-app: `main.py:1103-1109` `save_timer.start(60000)` rewrites it every 60 s regardless of the sim.*

**New tests** — `tests/test_build_sim_wires_route.py` (the test that distinguishes *wired* from *reported wired*), `tests/test_build_sim_wires_loaded.py`, `tests/test_build_sim_no_live_manager.py`, `tests/test_fleet_replay_anchors.py`, `tests/test_volume_guard_is_a_noop.py` (a **regression pin**, green on baseline, labelled as such — it goes red the moment anyone edits `volume_guard.py:190`, the single condition that would make the guard asymmetry real).

**Deferred out of this cascade** — harden `tests/test_sim_ta_input_fidelity.py`: its Call check at `:87-89` matches only bare-name `get_data_pool()`, so the attribute form passes green; there is no `ast.Import` branch; and a bare `bot._data_pool = pool` assignment is invisible to both tests. The pin does not enforce its own docstring.

**Corrected narrative** — the original said wired bots "route 10% of every scrum". Per-**wire** pcts are `{10.0: 38, 50.0: 2}`, but `scrumming_bot.py:1791` sums a source's wires: per-source totals are 17 bots at **20.0%**, 4 at 10.0%, 2 at 50.0%. The modal wired bot diverts a **fifth** of every scrum in live and zero in sim — roughly double the stated divergence.

**Rollback** — restore snapshot; the harness returns to its wire-less state.

---

### 33 — C23 · Harden Nuclear v2 before it is reachable *(v3.24.66, sim-only)*

> **RE-SCOPED 2026-08-07 by operator directive. Read this before starting.**
> Full design record: `2026-08-05_sim_nuclear_2point0_and_optimization_audit.md`
> sections **1.0** and **1.0b** (added the same day).
>
> **1. Nuclear is an abuse instrument, NOT a validator, and it is gated BEHIND
> parity.** Operator: *"Nuclear mode trades are not for validation against YTD
> data. They are meant to exercise the system brutally **after** it has been
> proven accurate by the YTD data and Stone Tablet simulated trade alignment
> that demonstrates identical (but not forced or form fitted!) trade logic
> behavior."*
> **No exit criterion in this cascade may be written in terms of trade match,
> P&L, or trade count against live.** Nuclear injects market noise on purpose,
> so its tape deliberately is not history — trade-alignment comparison there is
> meaningless by construction. The criteria are coverage and survival.
>
> **2. Design before hardening.** Operator: *"Nuclear Mode has several missing
> features and is still designed around single tape runs… No need to fix the
> wrong design so fix them first."* The seven steps below harden a controller
> that cannot yet do the thing it exists for. D18 in the audit already says the
> same: fix these defects *as part of* the rewiring, not after.
>
> **3. What is missing, verified from source 2026-08-07:**
> - The panel drives **v1** (`nuclear_controller.py`, single tape A/B). **v2**
>   (`NuclearFleetController`) has zero production callers — that is W3.
> - `set_topologies` and `set_swarm_hooks` on v2 have **zero callers anywhere,
>   including tests**. Both seams dead on arrival.
> - **v2 never re-rolls market noise** — loads tablets once at
>   `nuclear_fleet_controller.py:283`, hands the same dict to every cycle at
>   `:427`. Its oscillator is `SystemLoadOscillator` (CPU load), not market
>   structure. The noise machinery exists only in
>   `NuclearCandleSource.reroll_noise`, used solely by v1. **This gap was in
>   neither design doc.** It is a missing feature, not a defect.
> - **W1 is CLOSED** — Fleet Replay now loads the Smart Wire topology, shipped
>   as C20 / v3.24.72 on 2026-08-07.
>
> **4. Already-known-wrong citations in the text below** (from the C20 cold
> read): step 7's `nuclear_controller.py:261` — the construction is at `:268`
> and already injects a bus; `sim_run_log.py` lives at `src/trading/`, not
> `simulator_tab/`; and step 7's "keep the local SmartWireManager at :551" is
> **already fixed** — v3.24.72 injects a private `EventBus` there, because that
> line was the live-bus leak, not the precedent to copy.
>
> ---
>
> **COLD READ 2026-08-07 — nine defects. Raw evidence:**
> `raw/2026-08-07_C23_cold_read_raw.json`.
>
> **(a) THE RISK-TIER NOTE IS WRONG, and it is the most consequential error.**
> The Rollback line says *"the class remains unreachable either way until
> C24."* But the Files row lists `fleet/fleet_replay_controller.py`, which
> steps 3 and 4 both edit and which **is constructed in production today** —
> `fleet_replay_panel.py:968`, started at `:1123`. A `start()` regression can
> escape now. Rewrite as: *"`nuclear_fleet_controller.py` and
> `nuclear_controller.py` are unreachable until C24; `fleet_replay_controller.py`
> is NOT, so steps 3 and 4 require Fleet Replay regression coverage in the same
> cascade."*
>
> **(b) ANCHOR DRIFT IS SYSTEMATIC AND DIAGNOSABLE.** Every anchor into
> `nuclear_fleet_controller.py` **below `:551` is off by exactly +21**, because
> C20 (commit `39dc102`) inserted 22 lines and deleted 1 there. Every anchor
> **above** `:551` is still correct. Verified individually: 598→619 (the zip),
> 649→670, 682→703, 695→716, 551→572.
> **Do NOT run a blanket "fix the line numbers" pass** — it would break the four
> that are right. Shift below-`:551` anchors by +21, then RE-READ each.
> *Going forward: cite `file:symbol` with a line hint, not a bare absolute
> line, and add a re-anchor pass to every cascade's entry gate.*
>
> **(c) Step 4 is already SHIPPED — v3.24.74.** Severity was understated by an
> order of magnitude: not "spins forever" but a **non-yielding hot spin that
> starves the shared Qt/asyncio loop**. Measured 477,043 iterations/sec with a
> competing coroutine advancing **zero**; `main.py:1085-1092` pumps one loop
> from the GUI thread, so it freezes the GUI *and* live trading. See the
> v3.24.74 CHANGELOG entry for the asymmetry between the two refusal paths.
>
> **(d) Step 7 is 100% dead — DELETE IT.** All three targets shipped: bus
> injection and detach by C17 (`nuclear_controller.py:267-268`, `_teardown_quiet`),
> and the `SmartWireManager` bus by C20/v3.24.72. C23 becomes a **6-step
> cascade covering 8 findings**; drop SN-28 and update the index row.
>
> **(e) Step 6's verb is wrong and its anchor points at correct code.**
> Nothing zeroes `total_exceptions` — `:494` uses `+=` throughout. The real
> mechanism is `:373 if cyc.ok:` gating **all four** aggregates 117 lines away,
> so a failing cycle discards `cycles_completed`, `total_candles`,
> `total_trades` *and* `total_exceptions`. An implementer editing `:494`
> produces a diff that changes nothing — *"and then the gate gets tuned until it
> passes."* The one real defect **at** `:494` is the one step 6 omits:
> `:496 cyc.error = ...` is a plain assignment, so six worker failures report as
> one.
>
> **(f) Step 2 has three traps, two of which turn its own exit gate GREEN.**
> Two of the three `record_gate` sites run *after* `finish_run()` sets
> `_open = False`, so they are dead regardless of the kwarg. And `record_gate`
> projects a **fixed key set** with no passthrough (contrast `record_trade`,
> which takes `extra`), so renaming `payload=`→`gate_state=` yields N
> syntactically valid, semantically **empty** rows — row count goes 0→N and the
> gate passes on a fix that stores nothing.
>
> **(g) Step 5's severity is inverted.** Every operator-facing verdict is a
> membership or `>0` threshold and is **immune** to multiplication. And the
> unbounded axis is **cycles**, not workers (capped at 6) — a 40-cycle
> single-worker soak accumulates 40 fleets' worth with no workers involved.
> Split membership state (shared, cumulative) from quantity state.
>
> **(h) Step 1 fixes a function nothing calls.** `_bot_for_asset` is reachable
> only through `self._topologies`, whose sole writer `set_topologies` has zero
> callers repo-wide — and **C24 adds none**. "Why here"'s claim that wiring
> the panel first ships *"topology wires bound to the wrong bots"* is therefore
> **FALSE**;
> strike that clause. Its exit criterion calls the private method directly and
> so passes GREEN on dead code. Either give C24 a `set_topologies` caller, or
> label step 1 dead-code hardening in writing.
>
> **(i) MISSED FINDING, in the function step 1 edits.** `_wire_topology`
> silently replaces the fleet's **persisted** Smart Wire topology on every
> nuclear cycle — *after* the child has already logged its active-wire count.
> `FleetReplayController._build_smart_wires` runs first (via `_build_sim()`
> inside `start()`) and installs the operator's real 40 wires; nuclear then
> overwrites `bot._smart_wire_mgr` with a ring. **This is a consequence of
> C20/v3.24.72** — before it, no sim path built a manager at all, which is why
> `_wire_topology`'s docstring still claims *"Smart Wire was never instantiated
> anywhere in the simulator."* If the ring override is intended, say so in code
> and supersede the child's log line, so the record does not claim a topology
> that was immediately replaced.
>
> Also: `self._sim_bus` on `NuclearFleetController` is **write-only** — no
> reader, never declared in `__init__`. Tidy-up, not a concurrency defect.
>
> **Entry-gate note:** "observed RED on the baseline" was **not achievable** for
> step 4 with the installed tooling — `pytest-timeout` is not installed and a
> baseline test does not fail, it *hangs the suite at 100% CPU*. v3.24.74
> solved this by bounding every await individually and adding a negative
> control that the probe can still detect an unbounded spin. Reuse that shape.
> Note also that `tests/test_nuclear_fleet_controller.py` has 13 tests and
> **zero** coverage of `_run_cycle`, `_one`, `_wire_topology`, `_teardown`,
> `_record_cycle`, `_verifier` or `_emit_obs`.

| | |
|---|---|
| **Goal** | Every latent defect in `nuclear_fleet_controller.py` is fixed while the class still has zero production constructions. |
| **Why here** | Hard before C24 — wiring the panel first ships, in one step, a worker loop that spins forever when a fleet fails to start, three swallowed `record_gate` TypeErrors, and topology wires bound to the wrong bots. Scope correction carried from C17: the nuclear global-bus leak is `BotManager` at `nuclear_controller.py:261`, not `SmartWireManager`. |
| **Findings** | SN-22, SN-23, SN-24, SN-25, SN-26, SN-27, SN-28, T7-9, T7-10 |
| **Files** | `nuclear_fleet_controller.py`, `fleet/fleet_replay_controller.py`, `sim_run_log.py`, `nuclear_controller.py` |
| **Risk tier** | sim-only |

**Steps**

1. Fix the zip misalignment in `_bot_for_asset` (:598).
2. Fix the three `record_gate(payload=...)` TypeErrors swallowed to debug (:649/:682/:695) — a soak currently records no cycle data.
3. Evaluate stop/COOLING **inside** cycles, not only between them (:362), and ask child controllers to stop (T7-10).
4. Fix the never-terminating `while not ctl.progress.finished` (:462) together with `fleet_replay_controller.start`'s early return before the progress reassignment — SN-25 and T7-9 are the same defect.
5. Give the verifier/observer **per-worker** instances so quantities stop being multiplied by worker count (:337/:343).
6. Fix the exception-aggregation loop that zeroes `total_exceptions` on failing cycles (:494).
7. Re-scope SN-28 to the `BotManager` construction at `nuclear_controller.py:261` (bus injection from C17 plus explicit detach at :416); keep the local `SmartWireManager` at :551 attaching only sim bots.

**Entry gate** — C17, C19, C20 green. `tests/test_nuclear_fleet_controller.py` extended with the seven scenarios and observed RED on the baseline.

**Exit gate (measurement):** a fleet whose `start()` refuses terminates the worker loop within one cycle (bounded wall time, not a timeout kill); a soak's run directory contains one gate record per cycle (count == cycle count, currently 0); `_bot_for_asset` returns the correct bot for a shuffled asset list; `total_exceptions` on a failing cycle is non-zero; a full nuclear cycle leaves `get_event_bus()` subscriber count unchanged.

**New tests** — extend `tests/test_nuclear_fleet_controller.py`.
**Rollback** — restore snapshot; the class remains unreachable either way until C24.

---

### 34 — C24 · Wire Nuclear v2 to the panel and correct the record *(v3.24.67, sim-only)*

| | |
|---|---|
| **Goal** | The Simulator Swarm is actually driven by `NuclearFleetController`, and the CHANGELOG claims describing it become true. |
| **Why here** | Doctrine 6, hard after C23, and after C07 (whose summary fixes and preserved `_sim_swarm_layout` this makes visible for the first time) and C19 (so the two sim venues agree). |
| **Findings** | SN-2, SN-9, T7-5, T7-6, T7-8, RECORD-1, RECORD-8 |
| **Files** | `nuclear_mode_panel.py`, `nuclear_fleet_controller.py`, `bot_visualizer.py`, `fleet/sim_visuals.py`, `CHANGELOG.md` |
| **Risk tier** | sim-only |

**Steps**

1. Repoint `nuclear_mode_panel.py:35/:383` from the old `NuclearController` to `NuclearFleetController`.
2. Fix `set_swarm_hooks` (T7-5: 2 args into a 3-positional consumer) and T7-6 (`trades_fired` fed into the pnl slot — an R91 MAM violation).
3. Give T7-8's unbounded `_live_sim_rows` a real stop/remove call site.
4. Register the symbol so SN-9's chart/readout receives data.
5. Make RECORD-1 and RECORD-8 true, or correct them (M16).

**Entry gate** — C23 green with its measurements recorded; C07 green so the summaries are correct before they become visible.

**Exit gate (measurement):** starting Nuclear mode constructs a `NuclearFleetController` (assert the type); the Swarm shows N rows for N workers and returns to 0 after stop across 5 start/stop cycles (no unbounded `_live_sim_rows` growth); the pnl readout displays a currency value NOT equal to `trades_fired`; the chart receives a registered symbol; **a full Nuclear start/stop cycle leaves `~/.acervator/feature_telemetry.json` and `~/.acervator_logs/feature_validation.md` byte-identical** — *correction: C24 otherwise silently re-opens C14, because `nuclear_fleet_controller.py:425-432` constructs `FleetReplayController` with a fixed six-kwarg list carrying no telemetry sink, once per cycle in a soak, and C24's original gate had no live-tree clause*; CHANGELOG claims re-verified against behaviour.

**New tests** — `tests/test_nuclear_panel_wiring.py`.
**Rollback** — restore snapshot (panel import/construction); C23's hardening is independent and stays.
**Operator decision** — confirm Nuclear v2 replaces the old tape-scout path. *Hoisted to C07's entry gate; recorded again here because it also decides whether cascade 35 runs at all.*

---

### 35 — C25 · Old tape-scout fidelity *(CONDITIONAL — run only if C24 slips)* *(v3.24.68, sim-only)*

| | |
|---|---|
| **Goal** | If the old `NuclearController` remains reachable, its scouts stop buying in from flat against a zero-fee venue. |
| **Why here** | Explicitly conditional. If C24 lands, this path is retired and a gated sim-fidelity diff on soon-orphaned code is waste; if C24 slips, these three defects are live in the reachable scout path. |
| **Findings** | SN-3, SN-53, NF-115 |
| **Files** | `nuclear_controller.py`, `nuclear_sim_exchange.py` |
| **Risk tier** | sim-only |

**Steps**

1. **SKIP ENTIRELY** if C24 is green and the old controller has zero constructions (verify by grep).
2. Otherwise replace the $200 quote-only / 0.0 base seed at :78 with a seed matching the bot's persisted holdings.
3. Replace `fee_pct=0.0` at :272 with the real per-symbol rate the fleet path now charges.
4. Add the missing `params` kwarg to `NuclearSimExchange.get_my_trades` (NF-115).

**Entry gate** — C24 NOT green, **or** the old controller still has a production construction, confirmed by grep before starting.

**Exit gate (measurement):** a scout run's opening base holding equals the persisted holding (was 0.0); realised fees over the run are non-zero and equal the per-symbol rate × notional; `get_my_trades` accepts `params` without TypeError. **If skipped:** recorded grep output showing zero constructions of `NuclearController`.

**New tests** — `tests/test_nuclear_scout_seed_and_fees.py` (only if this cascade runs).
**Rollback** — restore snapshot; sim-only.
**Operator decision** — run or skip, decided by C24's outcome.

---

### 36 — C30 · Sim run-log directory retention *(v3.24.69, perf)*

| | |
|---|---|
| **Goal** | Run directories are pruned in step with the 500-entry index, by a prune structurally incapable of leaving the sim subtree. |
| **Why here** | Perf with a correctness edge (unbounded disk), and it introduces the module's FIRST delete operation — which is why it lands after the isolation guards and with a hard structural constraint. `sim_run_log.py:366` truncates the index while no `rmtree`/`unlink` exists anywhere in the module, and the parent `~/.acervator_logs` holds `gate.log` and its rotated `.1-.5` files. |
| **Findings** | SN-46 |
| **Files** | `src/trading/sim_run_log.py` |
| **Risk tier** | perf |

**Steps**

1. *Correction — the plan's name-based guard (`root.name == 'sim'`) makes its own acceptance measurement unrunnable and contradicts its third gate clause.* `tests/conftest.py:90-103` sets `ACERVATOR_SIM_LOG_ROOT` to `tempfile.mkdtemp(prefix="acervator-test-sim-")` session-wide and `_default_sim_log_root()` returns that override verbatim, so under test the root is **never** named `sim` — the guard would refuse to prune in every test while the gate demands a 600→500 prune on a temp root. Use a **structural** guard that survives redirection instead: prune only paths matching `root / "runs" / <generated-run-id-pattern>`; refuse when `root` is, or is an ancestor of, either live root as resolved by CV1's injectable `_live_roots()`; never `iterdir` the root itself.
2. Delete only run directories; never touch anything at root level except `index.json`.
3. Prune in the same transaction as `_append_index`'s truncation so index and directories cannot diverge.

**Entry gate** — CV1's guard active. A pin seeding a fake `~/.acervator_logs` containing `gate.log`, `gate.log.1-.5` and `trade.log`, written as the acceptance case.

**Exit gate (measurement):** after pruning a temp root holding 600 runs, exactly 500 run directories remain and index length is 500; in the seeded fake-live-tree case `gate.log`, `gate.log.1-.5` and `trade.log` all survive byte-identical; a root that **is** (monkeypatched) `~/.acervator_logs` raises rather than deleting.

**New tests** — `tests/test_sim_run_log_prune.py`.
**Rollback** — restore snapshot; deletion is the only new capability, so rollback removes all risk.
**Operator decision** — retention count for directories (500 is the current implicit index policy; directories may warrant fewer given size).

---

### 37 — C61 · Simulator per-bot configurability + details view *(v3.24.70, sim-only)*

| | |
|---|---|
| **Goal** | Every sim cluster's before/after diff becomes inspectable per bot, with a logged override layer for run provenance. |
| **Why here** | Doctrine 6 (feature, not fix), after C26 (its Start/Reset state machine must be correct before new controls hang off it) and after the sim gates whose diffs it makes readable. |
| **Findings** | SN-4 |
| **Files** | `fleet/fleet_replay_panel.py`, `fleet/fleet_replay_controller.py` |
| **Risk tier** | sim-only |

**Steps**

1. Add a `{field: value}` override dict applied to the passthrough in `_instantiate_bot`, logged to the Activity Log and to the run directory for provenance.
2. Add a row-selectable read-only details panel bound to the sim bot's existing `_tranche_snapshot`/`_compounding_snapshot`/`_last_gate_state` helpers.
3. Refuse overrides for fields that would break parity silently, and record the refusal.

**Entry gate** — C26 green; C16/C18/C19/C20 green so the details panel shows correct state.

**Exit gate (measurement):** an override of a single field appears verbatim in the run directory's provenance record and the constructed bot's config differs from the persisted config in exactly one field (full config diff cardinality == 1); selecting a row renders that `bot_id`'s tranche/compounding/gate snapshot and nothing is writable.

**New tests** — `tests/test_sim_override_provenance.py`.
**Rollback** — restore snapshot; additive UI only.
**Operator decision** — which fields may be overridden in a parity run at all.

---

### 38 — C37 · Stone Tablet test pins (before anything is armed) *(v3.24.71, record-only)*

| | |
|---|---|
| **Goal** | `auto_updater` and the fetcher's since-units-and-slot contract are pinned, and `ccxt_connector`'s current two-branch call shape is captured as the baseline C31 needs. |
| **Why here** | Hard before C38 (`auto_updater` has zero tests and is about to become the only writer to a 406-tablet, 7.2 M-candle archive) and **promoted to hard before C31** (TABLET-10 is the only baseline capture of the current positional call shape). |
| **Findings** | TABLET-9, TABLET-10 |
| **Files** | `tests/test_stone_tablets_auto_updater.py`, `tests/test_stone_tablets_fetcher.py` |
| **Risk tier** | record-only |

**Steps**

1. Write `tests/test_stone_tablets_auto_updater.py` against an explicit tmp root — CV1's guard now refuses the default root under the test marker.
2. Pin `CoinbaseAdapter.fetch_chunk`'s `since` **units** and **argument slot** — the exact contract whose breakage the `auto_updater` docstring blames for the archive never updating.
3. Pin `ccxt_connector`'s two-branch split EXACTLY AS IT IS TODAY (`limit` occupying the `since` positional when `since` is None), labelled as a **baseline capture**, so C31's change appears as a deliberate reviewed test update rather than an invisible edit.

**Entry gate** — CV1 green (archive-root guard active).

**Exit gate (measurement):** pytest collects the new module; every pin passes on the unmodified baseline; the real archive's file count and mtime set are unchanged after the run (guard-verified).

**New tests** — `tests/test_stone_tablets_auto_updater.py` (new), `tests/test_stone_tablets_fetcher.py` (fetch_chunk units/slot pin, ccxt two-branch baseline pin).
**Rollback** — delete the test files; no source change.

---

### 39 — C36a · Stone Tablet sweep correctness *(v3.24.72, record-only)*

| | |
|---|---|
| **Goal** | `sweep_once` resolves the correct quote and exchange per asset, validates returned rows, and reports failures instead of "update complete". |
| **Why here** | Hard before C38. Critical hazard: `registry.py:473` keys tablets as `(asset, exchange_id, timeframe, year)` with **no quote**, ingest dedupes only by timestamp, and `auto_updater.py:213` constructs `GapFiller(reg, adapter)` taking the `quote='USD'` default — so a USDC-built archive swept against USD splices two different price series into one tablet, and NF-91 means the checksum is written but never verified. |
| **Findings** | TABLET-2, TABLET-6, TABLET-7, TABLET-8, NF-26 |
| **Files** | `stone_tablets/auto_updater.py`, `fetcher.py`, `registry.py` |
| **Risk tier** | record-only |

**Steps**

1. Resolve the quote per asset from the coverage row rather than the `GapFiller` default; add the quote to the tablet key or to a per-tablet provenance field that `ingest_candles` **ASSERTS** against before appending.
2. Pass `cov.exchange_id` into `CoinbaseAdapter` (:212) so non-Coinbase rows cannot fork history under a Coinbase key.
3. Reject rows whose `ts` falls outside the requested `[cursor..chunk_end]` window.
4. Surface `FillReport.chunks_error` (:232-236) so a 100%-failed sweep reports failure, not "update complete".
5. Fix the stop/start restart hole (TABLET-8) and the USD/USDC quote-key defect in `build_universe` (NF-26).

**Entry gate** — C37 green. A full offline copy of the Stone Tablet archive taken by the operator (M11).

**Exit gate (measurement):** a sweep in which every chunk fails returns a report whose failed count equals the chunk count and whose status is NOT "complete"; a fixture asset with USDC provenance, swept with a USD-serving adapter, is REFUSED with a named reason and its tablet is byte-identical afterwards; an out-of-window row is rejected; `stop()` then `start()` resumes without duplicate work.

**New tests** — extend `tests/test_stone_tablets_auto_updater.py`.
**Rollback** — restore snapshot; the sweep is still unwired (C38 has not landed), so no archive has been touched.
**Operator decision** — for assets whose archive quote cannot be determined from the coverage row: refuse the sweep, or ask per asset. Refusal is the safe default.

---

### 40 — C36b · Stone Tablet registry safety + blocking cost *(v3.24.73, perf)*

| | |
|---|---|
| **Goal** | Ingest computes each tablet's SHA-256 once, verifies it on load, stops orphaning transiently-unreadable tablets, and stops re-requesting legitimately-absent candles. |
| **Why here** | Hard before C38: the measured 0.312 s/chunk × ~1,600 chunks is ~140 s of aggregate blocking through the Qt thread that also pumps every live bot tick — and combined with C13 a long stall can push a bot past the 120 s heartbeat TTL. |
| **Findings** | TABLET-5, NF-91, NF-27, NF-28 |
| **Files** | `stone_tablets/registry.py`, `storage.py` |
| **Risk tier** | perf |

**Steps**

1. Compute the SHA-256 once and share it between `entry_from_tablet` (:499) and `write_tablet` (:502).
2. Verify the stored checksum on load (NF-91) — the only detector for C36a's splice hazard.
3. Replace `self._entries.pop(key, None)` at :254 with a quarantine-and-report path so a transiently-unreadable tablet is not orphaned forever.
4. Make `missing_ranges` remember legitimately-absent candles (NF-28).
5. Batch writes outside the lock so a chunk's persist does not hold `_lock` across `write_tablet` plus `_persist_manifest`.

**Entry gate** — C36a green; a measured baseline of per-chunk ingest time on this machine recorded (expected ~0.312 s).

**Exit gate (measurement):** per-chunk ingest time is at most half the **recorded** baseline (asserted against that number, not a guess); a corrupted tablet is DETECTED on load and reported (currently silent); a transiently-unreadable tablet reappears in `_entries` after the transient clears; a second consecutive sweep issues zero requests for known-absent ranges.

**New tests** — `tests/test_stone_tablets_registry_checksum.py`, `tests/test_stone_tablets_ingest_cost.py`, `tests/test_stone_tablets_transient_unreadable.py`.
**Rollback** — restore snapshot; checksum verification is the only newly-refusing behaviour.

---

### 41 — C38 · Wire the Stone Tablet auto-updater in *(v3.24.74, live-behaviour)*

| | |
|---|---|
| **Goal** | The 406 stale tablets actually update, off the GUI thread, and the two error messages that point at each other are corrected. |
| **Why here** | Doctrine 6, hard after C36a, C36b and C37. **HAZARD: must NOT ship in the same release as C13** — a sweep stall can starve heartbeats past the 120 s TTL and cause the new prune to delete a live bot's reservation. |
| **Findings** | TABLET-1, TABLET-4, NF-8 |
| **Files** | `main.py`, `stone_tablets/__init__.py`, `auto_updater.py`, `fetcher.py`, `fleet/fleet_replay_panel.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Export the updater from `__init__`, construct it after `asyncio.set_event_loop`, and register `stop()` in shutdown.
2. Run the sweep OFF the GUI loop (worker thread with its own event loop); add a max-stall assertion to the sweep test.
3. First armed run is **DRY-RUN**: log what would be fetched and written, write nothing (M11).
4. Correct `fetcher.py:681-685` (points at a "Fetch missing coverage" button grep proves does not exist) and `fleet_replay_panel.py:797-800` (points back at a CLI subcommand that always exits 1).
5. Confirm the release does not also contain C13.

**Entry gate** — C36a, C36b, C37 green; the operator's offline archive copy confirmed; C13 confirmed NOT in this release; checksum-verify-on-load active.

**Exit gate (measurement):** (a) dry-run reports the expected chunk count for 406 tablets with archive file mtimes unchanged; (b) an armed run **on a COPY** updates coverage and every tablet passes checksum verification afterwards; (c) maximum contiguous GUI-thread stall during a full sweep is under 100 ms, measured and asserted; (d) neither corrected message names a nonexistent affordance (grep).

**New tests** — `tests/test_auto_updater_wiring.py`.
**Rollback** — restore snapshot (boot wiring); the updater becomes unreachable. Data rollback is the operator's offline copy.
**Operator decision** — sweep cadence, and whether the first armed sweep runs against the live archive or a copy that is then swapped in. **Recommend copy-then-swap.**

---

### 42 — C27 · Fleet Replay report + docstring truth *(v3.24.75, record-only)*

| | |
|---|---|
| **Goal** | Coverage is divided by the correct denominator and no banner, tooltip or docstring promises a mechanism that does not exist. |
| **Why here** | Record-only, after C38 because fresher tablets change the per-symbol coverage numbers this report prints. |
| **Findings** | SN-11, NF-19, SN-33, SN-32, SN-51, NF-79 |
| **Files** | `fleet/fleet_replay_panel.py`, `fleet/fleet_replay_controller.py` |
| **Risk tier** | record-only |

**Steps**

1. Compute `_expected_per_sym` from the FINALISED `_since_ms` (:727-733), not from `YTD_START_MS` at :700-701.
2. Replace the hardcoded `(122 days × 288)` at :770 with the live-computed day count it currently contradicts.
3. Correct the header banner (:193) and the two tooltips still promising synthetic sine-wave candles and a 1d/200-candle fetch.
4. Correct the three docstrings asserting a nonexistent thread boundary and the citation to `main.py:955`, which points at a log string.
5. Remove the two dead window-bound params whose comments assert an unimplemented mechanism (NF-79).

**Entry gate** — C38 green with refreshed coverage.

**Exit gate (measurement):** for a run with a known `_since_ms`, printed coverage% equals hand-computed candles/expected to 2 dp, and the printed day count equals the other rendered day count in the same block (they currently disagree); grep finds zero occurrences of "sine", "200 candles" and the `main.py:955` citation.

**New tests** — `tests/test_fleet_report_coverage_math.py`.
**Rollback** — restore snapshot; display and docs only.

---

> **Live-gate band begins here (cascades 43–55).** Every cascade below is tiered `live-behaviour` or `live-money`, rides alone (M2), and ships a per-symbol before/after SCRUM/FOLD decision table from CV2's harness plus a staged one-bot one-session rollout (M14). None of them may be scheduled before CV2 is green.

### 43 — C31 · LIVE GATE: OHLCV limit/since slot correction *(v3.25.0, live-behaviour)*

| | |
|---|---|
| **Goal** | The requested candle count is actually transmitted as a limit, at a window the operator has chosen — not silently cut to whatever the old default was. |
| **Why here** | Hard after C43 (a live order-path change must not ship on a vacuous green), after C37 (baseline pin) and CV2 (the diff harness). Cold read confirms `ccxt_connector.py:909-915` passes `limit` into ccxt's `since` positional when `since` is None, so the count has NEVER been applied on the live path. Heikin-Ashi is a forward recurrence seeded at index 0 and EMA is SMA-seeded, so this moves live decisions across all 35 bots at once. |
| **Findings** | DOCKET-OHLCV-1, NF-66 |
| **Files** | `src/exchange/ccxt_connector.py`, `scrumming_bot.py`, `phantom_balance.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. **DECIDE the window with the operator before editing.** Do not accept the venue default by accident-correction.
2. **HAZARD:** make the window decision at the **CALLER** (the `limit` default in `_get_ohlcv` at `scrumming_bot.py:5668`/`:5852` and `phantom_balance.py:238`), not only at the connector — otherwise live pool-routed TA sees the decided count while `FleetSimExchange.get_ohlcv` still returns exactly `limit` rows, and sim/live diverge on candle count alone.
3. Move the value into ccxt's `limit` slot and update C37's baseline pin as a deliberate, reviewed test change (M7).
4. Add a sim-side parity pin: `len(sim get_ohlcv(sym, tf, limit=N)) == len(pool-routed live result)` for the same N.
5. Stage the rollout: one bot, one session, before fleet-wide arming.

**Entry gate** — C43, C37, CV2 green; the operator's window decision recorded in writing; pre-change decision table and TA golden baseline captured.

**Exit gate (measurement):** (a) the connector transmits `limit=<decided>` (asserted on the recorded ccxt call args); (b) a per-symbol before/after SCRUM/FOLD decision table over the standard fixture set with every flip attributed to a named indicator delta; (c) sim and live return the same row count for the same requested N; (d) one staged live bot runs one session with its decisions logged and reviewed before the remaining 34 are armed.

**New tests** — `tests/test_ccxt_ohlcv_limit_slot.py`, `tests/test_sim_live_candle_count_parity.py`.
**Rollback** — restore snapshot (single call-site change); C37's baseline pin reverts with it. Request-shaped only, so no persisted state migrates.
**Operator decision** — **THE window: 100, 300, or another value.** This sets how much history Heikin-Ashi and the SMA-seeded EMA see on every live gate decision, and 300 may be the better number than the count currently requested.

---

### 44 — C32 · LIVE GATE: route the direct OHLCV callers through the pool *(v3.25.1, live-behaviour)*

| | |
|---|---|
| **Goal** | Phantom higher-TF bias and the detonation harvest check read pooled candles at the decided window, and stop constructing a throwaway default-weight `VotingEngine`. |
| **Why here** | Hard after C31 — the pool re-truncates to the requested limit and would mask C31's window change at exactly the two most valuable diff surfaces; the docket's own plan says window first, routing second. |
| **Findings** | DOCKET-OHLCV-7, DOCKET-OHLCV-8, **SN-50** *(correction: the plan cited "NF-50", an id that does not exist anywhere in the 242-item inventory or the repo; the substance — `scrumming_bot.py:9473` non-pooled fetch and `:9486` throwaway `VotingEngine()` — is SN-50. Left uncorrected, the coverage ledger would show SN-50 unremediated and NF-50 remediated.)* |
| **Files** | `phantom_balance.py`, `scrumming_bot.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Route `phantom_balance.py:238` (feeding `compute_all` and `get_higher_tf_bias`, which gates directional intent) through `MarketDataPool`.
2. Route `scrumming_bot.py:9473` (detonation harvest check) through the pool.
3. Replace the throwaway `VotingEngine()` with DEFAULT weights at :9486 with `self._voting_engine`.
4. Keep sim pool keys namespaced (C18's constraint) so this routing cannot make sim and live share cache entries.

**Entry gate** — C31 green and its staged rollout complete. Pre-change decision table captured for the two affected surfaces.

**Exit gate (measurement):** raw connector call count from these two sites drops to zero (instrumented connector); a before/after decision table for the higher-TF bias and harvest decisions on every live symbol, with each change attributable to the routing rather than a weight change (assert the weights used are `self._voting_engine`'s, not DEFAULT).

**New tests** — `tests/test_ohlcv_callers_pool_routed.py`.
**Rollback** — restore snapshot (two call sites).

---

### 45 — C33 · OHLCV record + contract truth *(v3.25.2, record-only)*

| | |
|---|---|
| **Goal** | The api_logger, the docstrings and the `ExchangeInterface` ABC describe what the code now does, and the sim exchanges refuse a `since` they cannot honour. |
| **Why here** | Record-only companion to C31, written after it so the honest params dict and the `BB_LOOKBACK` docstring state the window actually settled. |
| **Findings** | DOCKET-OHLCV-2, -3, -4, -5, -9, TABLET-3 |
| **Files** | `ccxt_connector.py`, `src/exchange/base.py`, `gate_healer.py`, `fleet/sim_exchange.py`, `nuclear_sim_exchange.py`, `docs/audits/2026-08-05_docket_ohlcv_limit_since_defect.md` |
| **Risk tier** | record-only |

**Steps**

1. Fix the api_logger params dict at `ccxt_connector.py:924` to name the slot the value is actually transmitted in.
2. Correct the stale `ta_engine.py:2522` citation (the real site is `compute_heikin_ashi` at 2608-2626).
3. Correct `gate_healer`'s `BB_LOOKBACK` docstring to state that the guarantee holds only via `MarketDataPool`'s re-truncation.
4. Add `since` to the `ExchangeInterface` ABC (`base.py:191-195`). **HAZARD:** the sim implementations are cursor-based (`CandleSeries.get_history` slices by cursor, not timestamp) — they must **RAISE `NotImplementedError`** on a non-None `since`, never accept-and-discard with `del since`, or a gap-filler would silently write wrong-range rows into the archive.
5. Correct the docket's own affected-caller table (DOCKET-5), which mis-scopes the whole remediation.

**Entry gate** — C31 and C32 green with the decided window recorded.

**Exit gate (measurement):** a test parameterised over BOTH sim exchanges asserts `get_ohlcv(..., since=<ts>)` RAISES; the api_logger record for a live fetch names the same slot the ccxt call used (assert equality of the two recorded dicts); grep finds zero occurrences of the corrected citations.

**New tests** — `tests/test_sim_exchange_since_refused.py`, `tests/test_api_logger_slot_truth.py`.
**Rollback** — restore snapshot; the ABC addition is backward compatible for callers passing no `since`.

---

### 46 — C34 · Market Inspector: real status, real window, non-blank pane *(v3.25.3, gui-truth)*

| | |
|---|---|
| **Goal** | The tab reports what the fetcher actually emitted, keeps scroll and selection across the 2 s tick, requests a window the venue can serve, and never shows a blank 800 px half-tab. |
| **Why here** | Hard after C31 — whether the 365-daily-bar request needs a limit correction or genuine since-based pagination is decided by C31's window decision and the venue's real per-request ceiling. |
| **Findings** | SWARM-4.30, NF-137, SWARM-4.31, DOCKET-OHLCV-6 |
| **Files** | `src/gui/market_inspector.py`, `market_inspector_fetcher.py` |
| **Risk tier** | gui-truth |

**Steps**

1. Stop `_render_signals` rewriting the status label as its first statement at :349 on every 2 s tick; preserve fetch progress, scroll offset and selection.
2. Add an `exchange` branch to `_status_line` — the only source the fetcher emits — so a successful scan stops reporting "No data yet".
3. Render a named error state instead of a blank 800 px pane when the topologies pane fails to construct.
4. Apply C31's window decision: correct the limit, or implement since-based pagination if the venue caps below 365.

**Entry gate** — C31 green with the venue's real per-request ceiling measured.

**Exit gate (measurement):** after a successful scan the status line contains the exchange name, not "No data yet"; across 5 refresh ticks the scrollbar value and selected row are unchanged; a forced topologies construction failure renders a non-empty error widget (rendered text length > 0); the fetcher receives the number of daily bars it requested (`len(result) == requested`, currently short).

**New tests** — `tests/test_market_inspector_status_and_scroll.py`, extend `tests/test_market_inspector.py`.
**Rollback** — restore snapshot (both files).
**Operator decision** — if the venue caps below 365 daily bars: paginate (slower, complete) or accept the cap (faster, shorter history)?

---

### 47 — C39d · LIVE GATE: ADX scale correction + its gate threshold *(v3.25.4, live-behaviour)*

| | |
|---|---|
| **Goal** | ADX runs on the textbook 0-100 scale and `ADXTrendSuppressionGate`'s threshold is reset in the SAME ship, so "ranging" and "developing" become reachable and ADX stops being a permanently-maxed voter. |
| **Why here** | Alone, after CV2, because it is the largest single live consensus change with no automated proof today: `grep -rin adx tests/*.py` returns one hit (a string in an indicator-name list), both ADX pins are archived, and `grep -rl gate_chain tests/` returns zero. |
| **Findings** | NF-72 |
| **Files** | `src/trading/ta_engine.py`, `gate_chain.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Restore both archived ADX pins and write the two new ones; confirm all RED on the baseline.
2. Capture the CV2 `compute_all` golden baseline BEFORE editing — this is also C47's baseline, so it must not be deferred.
3. Fix the SUM-form smoother at `ta_engine.py:342` so ADX no longer runs ~14× textbook.
4. Reset `ADXTrendSuppressionGate`'s 500.0 threshold (`gate_chain.py:551`) to the textbook-scale equivalent **in the same commit** — shipping the smoother alone inverts the gate and blocks live SCRUM on every trending candle across 35 bots.
5. Re-record the golden baseline and produce a diff.

**Entry gate** — CV2 green with the pre-change golden baseline and decision table recorded; both archived ADX pins restored and RED; operator briefed that this changes consensus on every bot.

**Exit gate (measurement):** (a) ADX lands in 0-100 over real tablet windows and each of ranging/developing/strong/parabolic is reachable on some window; (b) the gate's pass/block decision asserted at `adx = 15/25/40/60` matches the intended table; (c) *correction — scope this clause to per-indicator Signals, not the summary.* For every indicator **other than adx**, its `Signal` (direction, confidence, weight, details) is byte-identical to the recorded baseline; the summary's `consensus_*` / `net_score` / `*_count` fields are **permitted to move** and each delta is attributed to the adx signal alone — the plan's original "ONLY adx fields changed" clause would fail the *correct* fix, because ADX's own direction/confidence are derived from the adx value (`ta_engine.py:349-372`) and feed `bullish_count`/`net_score`/`consensus_confidence` at :2549-2555. Add an explicit clause that `_wilder_smooth` itself was NOT modified (source-hash assertion), since the correct fix is only at the `s_dx` call site and touching the shared helper would silently move Vortex and Slingshot; (d) a printed per-symbol before/after SCRUM/FOLD decision table; (e) a staged one-bot, one-session live run reviewed before fleet arming.

**New tests** — `tests/test_adx_scale_golden.py`, restored `tests/test_adx_trend_suppression_gate.py`, restored `tests/test_p2_9_adx_wiring.py`.
**Rollback** — restore snapshot (both files together). **NEVER revert one** — the smoother and the threshold are a single semantic unit.
**Operator decision** — the post-correction ADX threshold. ~30 is the textbook default, but how aggressively trend should suppress SCRUM is a trading decision, not a math one.

---

### 48 — C47 · TA duplicate computation + per-tick memoisation *(v3.25.5, perf)*

| | |
|---|---|
| **Goal** | `compute_all` stops recomputing the same series five times and memoises per tick, proved bit-identical against the golden baseline. |
| **Why here** | After C39d, using the baseline CV2 captured and C39d re-recorded. Perf that is also a correctness risk, so the exit gate is byte-equality, not speed. |
| **Findings** | SN-40, SN-41 |
| **Files** | `src/trading/ta_engine.py`, `scrumming_bot.py` |
| **Risk tier** | perf |

**Steps**

1. Remove the five verified duplications inside the one `compute_all` block: period-20 stdev 3-4×, Heikin-Ashi 2×, True Range 3×, Wilder RSI 2×, plus the two oversized allocations.
2. Memoise the block. *Correction — the plan's key `(len, last_ts)` is incomplete in two ways that would silently serve wrong results.* `compute_all(self, candles, timeframe="1h")` threads `timeframe` into every `Signal.timeframe` and into indicator behaviour, and `ta_engine.py:2587-2588` loops `per_tf[tf] = engine.compute_all(candles, tf)` over multiple timeframes — two calls with the same length and last timestamp but different timeframes would collide. Separately, `VotingEngine.__init__` stores **per-instance** `self.weights` (:2430-2442), so a module-level memo would serve a DEFAULT-weight result (the throwaway engine at `scrumming_bot.py:9488`) to a call on the operator's tuned engine at :5908. Key on **(engine-instance scope, timeframe, len(candles), last_ts)**, stored as an instance attribute, never module-level.
3. Not a behaviour change: `MarketDataPool` already freezes the candles for the TTL window, and the memo correctly no-ops in sim where the master clock advances every tick.
4. Prove bit-identity against the post-C39d golden baseline over real tablet windows.

**Entry gate** — C39d green with its re-recorded baseline.

**Exit gate (measurement):** `compute_all` output is BYTE-IDENTICAL to the recorded baseline across the full fixture window set; the memo returns the cached object on a repeated key and a fresh object when `last_ts` advances (object identity); **the same candle list at two different timeframes returns two DIFFERENT summaries, and two engines with different weights over identical candles return different summaries, neither served from the other's cache**; per-call series computation counts drop to 1 each (instrumented counters, not wall clock).

**New tests** — `tests/test_ta_compute_all_golden.py`, `tests/test_ta_memoisation.py`, `tests/test_ta_memo_key_completeness.py`.
**Rollback** — restore snapshot; byte-identity means rollback is a pure perf regression with no decision change.

---

### 49 — C39a · LIVE GATE: Smart Ceiling quote-vs-USD *(v3.25.6, live-behaviour)*

| | |
|---|---|
| **Goal** | The FOLD-side maturity stop engages on crypto-quoted pairs, matching the three sibling sites that already compare correctly. |
| **Why here** | Alone. `scrumming_bot.py:7475` compares a quote-denominated position against a USD ceiling, so "FOLD HOLD (Smart Ceiling)" never arms on those bots — fixing it **stops their compounding**, a live behaviour change requiring its own diff. |
| **Findings** | NF-21 |
| **Files** | `src/trading/scrumming_bot.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Apply `_quote_to_usd` at :7475 exactly as the three sibling sites do.
2. Produce a byte-identical proof on USD-quoted fixtures, where `quote_to_usd` is 1.0 and nothing may change.
3. Produce the before/after FOLD decision table for the crypto-quoted bots.

**Entry gate** — CV2 green; pre-change decision table captured for every crypto-quoted bot.

**Exit gate (measurement):** (a) on USD-quoted fixtures every FOLD decision is byte-identical to before; (b) on crypto-quoted fixtures a before/after table shows exactly which bots newly enter "FOLD HOLD (Smart Ceiling)" and at what position value; (c) a staged one-bot live session reviewed before arming the rest.

**New tests** — `tests/test_smart_ceiling_quote_conversion.py`.
**Rollback** — restore snapshot (single expression).
**Operator decision** — arming the Smart Ceiling on crypto-quoted bots stops their compounding at maturity. Confirm that is intended, per affected pair.

---

### 50 — C39b · LIVE GATE: autonomous SCRUM sell sizing on crypto-quoted pairs *(v3.25.7, live-behaviour)*

| | |
|---|---|
| **Goal** | Autonomous SCRUM sizes correctly on crypto-quoted pairs, matching the three sibling sites that already divide correctly. |
| **Why here** | Alone, and after C39a because both touch the same quote-conversion surface and their diffs must be individually attributable. `scrumming_bot.py:7044` divides a USD delta by `ticker.last` alone, so every autonomous SCRUM on those pairs is oversized and refused by the CRR gate — those bots currently never fire autonomously, and fixing it **starts real sells**. |
| **Findings** | NF-70 |
| **Files** | `src/trading/scrumming_bot.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Apply `_quote_to_usd` at :7044 as the three sibling sites do.
2. Produce a byte-identical proof on USD-quoted fixtures.
3. Produce a before/after table of autonomous SCRUM order SIZES and CRR outcomes per affected bot.
4. Stage: enable on one low-value crypto-quoted pair for one session first.

**Entry gate** — C39a green and its staged session reviewed; pre-change order-size table captured.

**Exit gate (measurement):** (a) USD-quoted fixtures produce byte-identical order sizes; (b) per crypto-quoted bot, a before/after order-size table plus the CRR accept/refuse outcome — the count of CRR refusals attributable to oversizing must drop to zero; (c) one staged live session with real fills reviewed.

**New tests** — `tests/test_autonomous_scrum_sizing_quote.py`.
**Rollback** — restore snapshot; sizing returns to oversized-and-refused, a safe if inert state.
**Operator decision** — these bots have never fired autonomously. Confirm the operator wants them trading autonomously now, pair by pair.

---

### 51 — C39c · LIVE GATE: initial-entry lot bookkeeping units *(v3.25.8, live-behaviour)*

| | |
|---|---|
| **Goal** | The lot appended on initial entry is denominated correctly, so `_main_lots` — persisted and rebuilding `_current_holdings` at boot — stops corrupting Target Delta, Smart Ceiling and cartridge thresholds. |
| **Why here** | Alone. `scrumming_bot.py:5790` appends a lot derived from a USD cost divided by a quote fill price, and the corruption survives restart via the init handshake. The finding's FOLD half was **refuted by its own verifier** and must NOT be "fixed". |
| **Findings** | NF-24 |
| **Files** | `src/trading/scrumming_bot.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Pin `_execute_buy`'s undocumented `cost` unit FIRST — the root cause is that the unit is stated nowhere; the fix must make it explicit and asserted (M15).
2. Correct the lot construction at :5790 for the pinned unit.
3. Do **NOT** touch the FOLD half of NF-24; record in the commit that its verifier refuted it.
4. Audit existing persisted `_main_lots` for already-corrupted entries and **report** them to the operator; do not silently rewrite them.

**Entry gate** — CV2 green; the `cost` unit pin written and RED on the baseline; a read-only report of current `_main_lots` per crypto-quoted bot captured.

**Exit gate (measurement):** for a hand-built initial entry with known cost and quote fill price, the appended lot's base quantity equals the hand-computed value and differed before; on USD-quoted fixtures every lot is byte-identical; a before/after table of Target Delta and Smart Ceiling inputs per affected bot; FOLD-path decisions byte-identical, proving the refuted half was not touched.

**New tests** — `tests/test_execute_buy_cost_units.py`, `tests/test_initial_entry_lot_units.py`.
**Rollback** — restore snapshot (single expression). Persisted corrupted lots are NOT auto-rewritten, so there is no data migration to undo.
**Operator decision** — what to do about already-corrupted persisted lots on live bots: leave them (decisions stay wrong until the position closes) or reconstruct from exchange fill history. Reconstruction touches live state and needs explicit approval.

---

### 52 — C60 · LIVE GATE: initial-entry sibling-claim semantics + DIST balance clamp *(v3.25.9, live-behaviour)*

| | |
|---|---|
| **Goal** | The initial-entry branch stops raising `AttributeError` into the container's cooldown loop, and the DIST balance clamp actually applies — with the claim semantics decided explicitly rather than restored by reflex. |
| **Why here** | Alone, and treated as live-behaviour rather than a "swallowed-exception repair". Confirmed: `_sum_sibling_base_currency_claims` is called at `scrumming_bot.py:5611` and defined NOWHERE in `src` (only in an archived test), so no bot in that branch ever buys. Either fix outcome is mass-scale: delegating to `BotManager`'s summation makes `_quote_free` deeply negative across 35 USD-sharing bots so **nothing** enters; returning 0.0 fires **up to 35 simultaneous live BUYs** on the first tick after the upgrade. |
| **Findings** | NF-68, NF-158 |
| **Files** | `src/trading/scrumming_bot.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Decide the claim semantics explicitly with the operator; **write the rule down before writing code** (M15).
2. **DRY RUN FIRST:** log the computed `_sibling_claims` and `_quote_free` per bot for one full session with the initial-entry fire still DISABLED, and show the operator the table (M11).
3. Only then arm, staged one bot at a time.
4. Fix NF-158 in the same file: `scrumming_bot.py:8636` compares a float to a `Balance` object, so the DIST clamp raises TypeError into a bare except and never applies — extract the numeric field and assert the clamp fires.

**Entry gate** — CV2 green; the dry-run table for all 35 bots reviewed and signed off by the operator; C39c green so claims are computed against correct holdings.

**Exit gate (measurement):** (a) the dry-run table shows `_sibling_claims` and `_quote_free` for all 35 bots with zero `AttributeError`s raised into the cooldown loop (currently every eligible bot raises); (b) with the decided semantics, the number of bots that would fire an initial entry on the first armed tick equals the operator-approved number, staged; (c) a DIST clamp fixture asserts the clamped amount is applied (currently the TypeError is swallowed).

**New tests** — `tests/test_sibling_base_claims_semantics.py`, `tests/test_dist_balance_clamp_applies.py`.
**Rollback** — restore snapshot; the branch returns to raising, which is inert — no bot buys — a safe rollback state.
**Operator decision** — **THE claim semantics:** sum every sibling's `target_balance` (nothing ever enters with 35 USD bots), sum only ACTIVE claims, or 0.0 (up to 35 simultaneous live buys). A capital-allocation policy decision only the operator can make.

---

### 53 — C40a · LIVE GATE: revive Stack Mode (four coupled defects, one commit) *(v3.25.10, live-behaviour)*

| | |
|---|---|
| **Goal** | Stack Mode places exactly one tranche ladder per SCRUM decision, at operator-set Split Distance, above the venue minimum, and falls through to a single sell when placement fails. |
| **Why here** | After C19 (`IOC_LIMIT` must be simulable before Stack is armed live) and after the quote/units gates. `scrumming_bot.py:9743` reads `self.exchange_interface`, which appears exactly once in the whole tree — so Stack is fully dead while advertised in the wizard, Live Settings and a Stack Tranches tab. |
| **Findings** | NF-69, NF-23, NF-25, SN-48 |
| **Files** | `src/trading/scrumming_bot.py`, `stack_math.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. **ONE COMMIT for all four.** Fixing NF-69 alone arms a runaway: on success `_open_stack_from_scrum` returns `len(tranches)` (:9826) while the caller at :9981-9990 reads `if _n > 0: return None` — `None` is the sell path's FAILURE value, so hysteresis is never armed and the same SCRUM re-fires a full ladder every tick.
2. Repoint the dead attribute AND return the count of **SUCCESSFULLY PLACED** tranches, not built ones, so the documented fall-through to the single sell at :9986-9988 actually works.
3. Source `min_order_size` from the connector's real per-symbol market limits — not a `getattr` default of 0.0, which would build sub-minimum tranches, fail every placement, still return `_n>0`, and silently stop the bot selling forever.
4. Fix SN-48: `split_distance_pct` is a typo for `split_distance` (the `BotConfig` field), so operator Split Distance is ignored and the first live ladder would use 1.0% spacing.
5. Ship to a single low-value pair first.

**Entry gate** — C19 green (Stack is simulable), C39a/b/c green (sizing and units correct), CV2 pre-change table captured. All four sub-fixes staged in one branch.

**Exit gate (measurement):** (a) across three consecutive ticks after one SCRUM decision exactly ONE ladder is placed (currently three); (b) every tranche is at or above the venue's real per-symbol minimum (asserted against fetched market limits); (c) tranche spacing equals `config.split_distance`, not 1.0; (d) with all placements forced to fail, the single-sell fall-through EXECUTES; (e) one low-value pair traded live for one session and reviewed.

**New tests** — `tests/test_stack_open_one_ladder_per_scrum.py`, `test_stack_min_order_size.py`, `test_stack_split_distance_honoured.py`, `test_stack_placement_failure_falls_through.py`.
**Rollback** — restore snapshot, **whole commit, never partially**. Rollback returns Stack to fully dead, which is the safe state.
**Operator decision** — whether to revive Stack Mode at all, and on which pair to stage it. It has been dead long enough that the advertised behaviour has never actually run live.

---

### 54 — C40c · LIVE: inverted Extractor artillery sizing *(v3.25.11, live-money)*

| | |
|---|---|
| **Goal** | An INVERTED Extractor's order size stops being inflated by 1/price. |
| **Why here** | Alone, live-money order-size change. `extractor_bot.py:1377` (mirror at :1016) divides an already-base-denominated ammo amount by the pair price, while the ledger multiplies the error back out so the GUI reads correct — which is why it has gone unnoticed. |
| **Findings** | NF-67 |
| **Files** | `src/trading/extractor_bot.py` |
| **Risk tier** | live-money |

**Steps**

1. Remove the division at :1377 and its mirror at :1016.
2. Correct the ledger's compensating multiplication **in the same commit**, or the GUI starts reading wrong once the order is right.
3. Produce a before/after order-size diff on an inverted fixture and a byte-identical proof on a non-inverted one.

**Entry gate** — C53 green (display truth) so the GUI reading can be trusted as evidence. Pre-change order sizes recorded for every inverted Extractor.

**Exit gate (measurement):** on an inverted fixture the placed order size equals the hand-computed base amount and differed by exactly 1/price before; on a non-inverted fixture every order size is byte-identical; the ledger's reported amount equals the placed amount (they currently differ by the compensating factor).

**New tests** — `tests/test_extractor_inverted_sizing.py`.
**Rollback** — restore snapshot (sizing and ledger compensation together).
**Operator decision** — confirm which live Extractors are configured INVERTED before arming; their order sizes change immediately.

---

### 55 — C13 · LIVE GATE: capital-reservation reclamation *(v3.25.12, live-money)*

| | |
|---|---|
| **Goal** | Orphaned reservations are reclaimed without ever freeing capital a live or paused bot legitimately pledged. |
| **Why here** | Hard after C15 (a sim fallback writing the live registry makes this sweep structurally blind — those rows heartbeat every sim tick and are never expired) and deliberately LAST among live gates. `prune_expired` (`capital_reservation.py:567`) has zero callers; `_load` rehydrates with no staleness filter; the purge residue on disk (6.5 MB `pre_purge`, 6.0 MB quarantine vs an 11 KB current file) is evidence this has fired destructively before. **Must not ship in the same release as C38.** |
| **Findings** | SN-7 |
| **Files** | `src/trading/capital_reservation.py`, `main.py` |
| **Risk tier** | live-money |

**Steps**

1. Add backup-before-overwrite to `_save` (:217-238 currently does `tmp.replace` with NO backup, unlike `StateManager`) and have `prune_expired` write its pruned list to a dated audit file BEFORE mutating. Both are additive and land ahead of the reclamation logic (M11).
2. **HAZARD:** never prune a reservation whose `bot_id` is still registered in `BotManager`, regardless of heartbeat — `heartbeat()` is called only from the tick path, so a legitimately PAUSED bot never heartbeats and would be pruned within 180 s, freeing a sibling to sell against its holdings. Alternatively have PAUSED/IDLE bots heartbeat from the container's 2 s tick.
3. Report any reservation whose `bot_id` is absent from `BotManager._bots` as an ORPHAN regardless of heartbeat freshness — that is the exact signature of a sim-injected row.
4. Ship in **DRY-RUN** mode (log what WOULD be pruned, prune nothing) for one full operator session, then arm.
5. Confirm the release does not also contain C38.

**Entry gate** — C15 green; C38 confirmed NOT in this release; `test_capital_reservation_coverage.py` restored from `_archive` and RED for the new cases; the comment at `capital_reservation.py:92` ("the first `prune_expired()` call after startup would nuke everything") treated as a **required test case**.

**Exit gate (measurement):** *correction — the plan's clause (a) passes vacuously on the baseline and never exercises the path that destroys data.* `prune_expired` computes `within_grace = (now - self._boot_time) < self._restart_grace` and enforces staleness **only** when not within grace, so a fresh-registry fixture seeded at t-1s/t-1h/t-30d runs entirely inside the 60 s window and nothing is pruned — true for the wrong reason. Worse, `_load` rehydrates `_reservations` but **never `_heartbeats`** (:239-252), so post-grace `last_hb = self._heartbeats.get(r.bot_id, r.reserved_at)` falls back to `reserved_at` and **every disk-rehydrated reservation older than the 120 s TTL is pruned 60 seconds after boot** — the mechanism behind the residue this cascade cites. Rewrite as: seed a **temp `reservation_state.json`** with rows at t-1s/t-1h/t-30d, construct a registry (forcing `_load`), then call `prune_expired(now = boot_time + RESTART_GRACE_SECONDS + 1)`; assert exactly the expected set survives AND that `_heartbeats` was rehydrated so a live-but-quiet bot's row is not among the pruned. Then: (b) a PAUSED registered bot's reservation SURVIVES a prune; (c) `effective_available` per live symbol is UNCHANGED for every non-expired entry (per-symbol before/after table); (d) one full session of dry-run output reviewed with zero unexpected candidates; (e) `_save` writes a backup before overwriting.

**New tests** — restored `tests/test_capital_reservation_coverage.py`, plus `tests/test_capital_reservation_heartbeat_rehydrate.py` (without which clause (b) is also unreachable, since a paused bot's heartbeat is likewise absent after `_load`).
**Rollback** — restore snapshot (`main.py` caller) so the sweep is unreachable again. The dated audit file and the new backup are the data rollback for anything already pruned.
**Operator decision** — the TTL and the paused-bot policy: prune paused bots' reservations after some longer window, or never while the bot is registered? This decides whether a sibling can sell into a paused bot's holdings.

---

### 56 — C46 · Phantom polling cost + timeframe availability *(v3.25.13, perf)*

| | |
|---|---|
| **Goal** | Phantoms stop making ~12,600 raw OHLCV calls/hour of which ~94.6% are redundant, and the forked stale blocklist stops silently dropping the 30 m phantom on Coinbase. |
| **Why here** | After C17 (same constructor and `_tick`, so separate cascades churn the same two methods twice) and after C31/C32 (pool routing and window settled). Perf that is also correctness: the CPM this burns is the same gauge whose 450 threshold gates phantom sets, which is why it precedes C45. |
| **Findings** | SN-38, NF-89 |
| **Files** | `phantom_balance.py`, `scrumming_bot.py`, `src/exchange/timeframes.py` |
| **Risk tier** | perf |

**Steps**

1. Replace the unconditional 60 s clamp at `phantom_balance.py:206` with a per-timeframe sleep.
2. Route :238 through `MarketDataPool` (the same fix v3.23.74 claims for the parent path), respecting C18's sim key namespacing.
3. Delete the forked, stale `_EXCHANGE_UNSUPPORTED_TFS` blocklist at `scrumming_bot.py:2285` and resolve from `src/exchange/timeframes.py` so the 30 m phantom is no longer silently dropped on Coinbase.
4. Prove TA output unchanged — this must be behaviour-preserving.

**Entry gate** — C17, C31, C32 green. Direct unit pins on `PhantomBalanceBot._tick` exist (C18 required them precisely so this cascade is not verified by a phantom-less replay).

**Exit gate (measurement):** instrumented raw OHLCV call count over one simulated hour at 35 bots drops from the measured baseline (~12,600) by at least 90%; every phantom's `compute_all` output is byte-identical to pre-change; the 30 m phantom EXISTS for a Coinbase bot (currently absent).

**New tests** — `tests/test_phantom_polling_cost.py`, `tests/test_phantom_timeframe_resolution.py`.
**Rollback** — restore snapshot (both files; the blocklist deletion reverts with them).

---

### 57 — C45 · Exchange layer: load accounting, retry classification, breaker coverage *(v3.25.14, live-behaviour)*

| | |
|---|---|
| **Goal** | The API-load gauge can read above 500 CPM and counts every connector method; permanent 4xx stop being retried; read paths are breaker-protected; market limits are cached with a TTL. |
| **Why here** | After C46, which removes ~94.6% of the phantom calls — the dominant contributor to the CPM this gauge measures. Calibrating first would mean tuning against a load profile about to change by an order of magnitude. |
| **Findings** | NF-13, NF-41, NF-74, NF-157, NF-103, NF-14 |
| **Files** | `api_load_monitor.py`, `ccxt_connector.py`, `circuit_breaker.py`, `bot_container.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Replace the 500-entry ring that structurally caps the gauge at 500 CPM; add recording to the six connector methods that never record.
2. Fix `_with_retry`'s substring match that treats `BadRequest` as retryable because "request" matches — tripling cost on permanent 4xx.
3. Give `call_with_breaker` real call sites ordered **OUTSIDE** `_with_retry` — inside, NF-41's retries fire first and the breaker never sees the burst. This ordering is one edit with the retry fix.
4. Add a TTL to the negative market-limits cache (NF-157) and consume the fetched-but-unread market metadata (NF-103) in the pre-flight path.
5. Fix the `_scan_symbols` thread race (NF-14).

**Entry gate** — C46 green with the post-change CPM baseline measured.

**Exit gate (measurement):** a synthetic 900 CPM load reads as ~900, not 500; a `BadRequest` is attempted exactly ONCE (call count); with the breaker open a read path returns the breaker's refusal without reaching the connector; a negative market-limits entry expires after the TTL and is re-fetched; concurrent `_scan_symbols` from two threads produces a consistent result set across 100 iterations.

**New tests** — extend `tests/test_api_load_monitor.py`; `tests/test_retry_classification.py`, `tests/test_breaker_ordering.py`.
**Rollback** — restore snapshot; breaker wiring is the only new refusal path.
**Operator decision** — the CPM threshold that gates phantom sets, now that the real load profile has changed (450 was calibrated against the pre-C46 burn).

---

### 58 — C49 · Unwired subsystems: wire or delete, one decision each *(v3.25.15, live-behaviour)*

| | |
|---|---|
| **Goal** | Every subsystem constructed under `main.py`'s "# Shared subsystems" comment is either genuinely wired or removed, and no GUI renders statistics from a permanently empty store. |
| **Why here** | Doctrine 6, deliberately after C01 (a CapitalRegistry wiring arms NF-156's silent data loss — `set_capital_registry` has zero callers today, which is the only reason it is latent), after C17/C22 (a global-bus consumer that can PAUSE_ALL must not be reachable from a leaked sim event), and after C11. |
| **Findings** | NF-94, NF-82, NF-88, NF-87, NF-76, SN-49, SWARM-4.32 |
| **Files** | `main.py`, `main_window.py`, `analytics_engine.py`, `risk_manager.py`, `reconciliation.py`, `bot_container.py` |
| **Risk tier** | live-behaviour |

**Steps**

1. Decide each of the seven explicitly: `shared_risk`/`shared_analytics` (NF-94); `AnalyticsEngine`'s trade store vs the Analytics tab's win rate and Sharpe from an always-empty list (NF-82); `RiskManager`'s PAUSE_BOT set-insert and PAUSE_ALL literal `pass` (NF-88); `ReconciliationEngine`'s caller-less `reconcile()` and its orphan detector hardcoded to flag every live order (NF-87); `CapitalRegistryPanel` (NF-76); `ChartsTab.log_trade`'s missing writer (SN-49); `profit.cross_bot`'s zero emitters and the persisted-never-read Route combo (SWARM-4.32).
2. **HAZARD:** if `RiskManager` is wired, make it and `AnalyticsEngine` IGNORE events whose `bot_id` is not in `BotManager._bots`, so a leaked sim event can never trigger a live PAUSE_ALL.
3. **HAZARD:** if `CapitalRegistry` is wired, re-verify C01's refusal handling first.
4. Where the decision is delete, remove the GUI surface in the same commit so nothing renders from an empty store.

**Entry gate** — C01, C11, C17, C22 green. CV1's boot smoke test extended to assert each named subsystem is non-None (or absent by decision), RED where relevant.

**Exit gate (measurement):** for each of the seven, either (wired) a fixture event reaches the subsystem and produces a non-default observable result, or (deleted) grep shows zero references and the boot smoke test passes; an event with an unknown `bot_id` triggers ZERO risk actions; the Analytics tab either shows values derived from a seeded store or does not render those fields.

**New tests** — `tests/test_shared_subsystems_wiring.py`, `tests/test_risk_ignores_unknown_bot.py`.
**Rollback** — restore snapshot per subsystem — each decision is an independent commit within the cascade.
**Operator decision** — seven wire-or-delete calls. **PAUSE_ALL in particular:** implementing it gives the platform power to halt all live trading autonomously — a policy decision, not a code cleanup.

---

### 59 — C42 · Gate forensics: healer provenance + live fixture completeness *(v3.25.16, record-only)*

| | |
|---|---|
| **Goal** | `gate_healer`'s reconstruction window excludes look-ahead and re-aggregates to the requested timeframe BEFORE it is ever wired, and live ticks stop writing null gate fixtures. |
| **Why here** | Record-only but ordered before any healer wiring: the window currently includes the trade's own fully-closed candle, so every "RECOVERABLE" field carries look-ahead, and the module has zero production callers — the first wiring would ship contaminated rows into the parity record. |
| **Findings** | RECORD-5, RECORD-6, RECORD-7, NF-22 |
| **Files** | `src/trading/gate_healer.py`, `scrumming_bot.py` |
| **Risk tier** | record-only |

**Steps**

1. Exclude the trade's own candle from the reconstruction window (RECORD-5).
2. Actually **re-aggregate** the native 5 m rows to the labelled timeframe instead of merely labelling them (RECORD-7).
3. Leave the module unwired until both land; record explicitly that the PROVENANCE CONTRACT is declared and unconsumed (RECORD-6).
4. NF-22: every `tick()` early return currently skips the gate-fixture write, so out-of-band fires log null fixtures — writing them reduces what the healer must reconstruct at all.

**Entry gate** — CV2 green (the fixture windows are the same evidence base). A pin feeding a trade whose own candle would change the outcome, RED on the baseline.

**Exit gate (measurement):** for a fixture where the trade's own candle would flip the reconstructed decision, the healer's output is UNCHANGED by that candle; a 1 h reconstruction from 5 m rows equals the hand-aggregated 1 h series byte-for-byte; the fraction of live gate fixtures written with null fields drops to zero over one session, measured against the current rate.

**New tests** — `tests/test_gate_healer_no_lookahead.py`, `test_gate_healer_reaggregation.py`, `test_gate_fixture_written_on_early_return.py`.
**Rollback** — restore snapshot; the healer stays unwired either way.

---

### 60 — C48 · Live-process retention: bound the unbounded buffers *(v3.25.17, perf)*

| | |
|---|---|
| **Goal** | No live buffer grows without bound and no bounded ring is implemented as an O(N) re-slice inside a contended lock. |
| **Why here** | Perf after the correctness work. One review lens, one memory probe: `_memorised_trades` retains a full `VotingSummary` per fill while its only consumer has zero callers; `_transactions` is write-only; five "bounded" rings re-slice on every append inside the lock every emitter contends on. |
| **Findings** | SN-43, SN-45, SN-47 |
| **Files** | `scrumming_bot.py`, `smart_wire.py`, `event_bus.py`, `analytics_engine.py`, `reconciliation.py`, `risk_manager.py`, `volume_guard.py` |
| **Risk tier** | perf |

**Steps**

1. Delete or bound `_memorised_trades` — `memorize_to_grid` has zero callers.
2. Delete or bound `SmartWireManager._transactions` — its only reader is a stats property nothing consumes.
3. Convert the five list-re-slice rings to `deque(maxlen=)` so append is O(1) and the lock is held for less time.

**Entry gate** — C45 green. A memory probe recording RSS growth per 1,000 simulated fills on the baseline.

**Exit gate (measurement):** *correction — the plan's primary clause ("RSS growth drops to under 10% of baseline") contradicts M12 and can fail a correct fix.* CPython's allocator does not reliably return freed arenas to the OS, so converting to `deque(maxlen=)` and deleting `_memorised_trades` can leave RSS essentially flat while being entirely correct — and a GC-timing artefact can make it pass while a ring is still unbounded. The gate is **structural**: after 10× the cap in appends, `len(ring) == maxlen` for each of the five converted rings; `type(ring) is collections.deque` and `ring.maxlen is not None` (both asserted, so a list re-slice cannot masquerade); append time is flat across 10× the cap rather than growing; `_memorised_trades` and `SmartWireManager._transactions` are either absent or bounded, asserted by attribute inspection. The RSS figure is demoted to a **manual operator measurement** (*unmeasured as an automated gate*).

**New tests** — `tests/test_live_buffer_bounds.py`.
**Rollback** — restore snapshot; `deque` and `list` share the append/iterate interface used at every call site.
**Operator decision** — whether `memorize_to_grid` is a feature to finish or dead code to delete — it is the only consumer of the retained `VotingSummary` data.

---

### 61 — C08 · Bot Swarm paint/tick cost *(v3.25.18, perf)*

| | |
|---|---|
| **Goal** | The 33 ms repaint path allocates and imports nothing per frame, the grid is not torn down every tick, timers stop when the tab is hidden, and `logger` is defined. |
| **Why here** | Perf last, but with a correctness component: NF-15 means `logger` is undefined at `bot_visualizer.py:3045` (no `import logging` anywhere in the 3,257-line module), so the `update_bots` exception handler itself raises. |
| **Findings** | SWARM-4.10, SWARM-4.12, SWARM-4.13, NF-15 |
| **Files** | `src/gui/bot_visualizer.py` |
| **Risk tier** | perf |

**Steps**

1. Add the module-header `import logging` and `logger` (NF-15) in the same handler SWARM-4.10 rewrites.
2. Stop the unconditional `QGridLayout` teardown at :3049-3063; update in place.
3. Hoist `BotNodeWidget.paintEvent`'s per-frame imports, tooltip construction and pen allocation out of the paint path (:384-723). The tooltip text is already masked by C03, so this hoist moves masked text.
4. Add `showEvent`/`hideEvent` around `_anim_timer.start(33)` at :1517 and guard the lane `raise_` at :2697.

**Entry gate** — C03, C07, C09 green (the file's structural work is done). Structural pins written and RED on the baseline.

**Exit gate (measurement):** *correction — an AST-only gate is defeated by the most natural refactor.* Asserting `paintEvent`'s syntactic body contains no imports and constructs no `QPen`/`QColor` passes unchanged if that work moves into a helper called from `paintEvent`, and says nothing about the tooltip construction named in step 3. Use **runtime allocation counters**: monkeypatch `QPen`/`QColor`/`setToolTip` with counting wrappers, drive 30 `repaint()`s, and assert construction count is 0 (or a fixed constant independent of frame count) and `setToolTip` call count is 0; assert the `sys.modules` snapshot is identical before and after 30 paints so a helper-hidden import is still caught. Keep the AST import check as a secondary. Plus: `_anim_timer.isActive()` is False after `hideEvent` and True after `showEvent`; `update_bots` called twice with identical input creates zero new layout items; the exception handler logs successfully (previously `NameError`). Plus one **manual** operator frame-rate measurement on the real 35-bot grid at real window size (*wall-clock claims are unmeasured until that manual pass*).

**New tests** — `tests/test_bot_visualizer_paint_cost.py`.
**Rollback** — restore snapshot; all four are local.

---

### 62 — C44 · Static-analysis and sweep tooling: stop reporting false results *(v3.25.19, record-only)*

| | |
|---|---|
| **Goal** | `version_sweep` and `rule_registry` stop emitting permanent false findings and stop mutating the repo as a side effect of running. |
| **Why here** | After C43, which consumes these results — fixing the sweep while the gate can still pass vacuously means neither run proves anything about the other. NF-40's `sadp/` recreation makes the cluster's own acceptance non-idempotent, so it is fixed first. |
| **Findings** | NF-11, NF-12, NF-73, NF-10, NF-134, NF-40, NF-30, NF-31, NF-32, NF-33, NF-34 |
| **Files** | `version_sweep.py`, `rule_registry.py`, `gui_archetype.py`, `rules/hallucination.py`, `rules/scaffolding.py`, `tools/orphan_widget_scan.py` |
| **Risk tier** | record-only |

**Steps**

1. **FIRST** fix NF-40 (stop recreating the deleted `sadp/` tree on every run) — otherwise run 1 creates the dead imports run 2 reports and neither run is reproducible.
2. Remove the R25 gate's dependence on the deleted `simulator.py` (NF-11) and the four permanent false DEPENDENCY findings against a nonexistent `requirements.txt` (NF-12).
3. Make the two silently no-op checks report "not run" instead of printing a pass tick (NF-73).
4. Point `rule_registry` at a directory that exists (NF-10) and extend `RULE_META` past R35 so the R1–R70 rules this codebase cites stop being rejected (NF-134) — that rejection is what turns 215 in-tree annotations into spurious MEDIUMs.
5. Fix the four tautological/inert/async-blind harness rules (NF-30/31/32/33) and the `tools/` shim that crashes on import (NF-34).
6. Restore `test_version_sweep_coverage.py` and `test_rule_registry_coverage.py` from `_archive` as the pins.

**Entry gate** — C43 green. Both archived coverage modules restored and RED on the baseline.

**Exit gate (measurement):** run the sweep twice against a **FROZEN fixture tree copied to `tmp_path`** — both runs produce identical output and the tree is byte-identical afterwards (no `sadp/` recreated); the false DEPENDENCY finding count is 0; a rule annotation citing R70 is ACCEPTED (currently rejected); the two previously-no-op checks report "not run" rather than a pass tick.

**New tests** — restored `tests/test_version_sweep_coverage.py`, `tests/test_rule_registry_coverage.py`.
**Rollback** — restore snapshot; dev tooling only.

---

### 63 — C55 · Declared-but-unhonoured knobs and docstrings *(v3.25.20, record-only)*

| | |
|---|---|
| **Goal** | Every constant, flag and contract that is declared is either honoured by code or removed. |
| **Why here** | Record-only, no behaviour change today, batched because verifying six near-identical one-line reconciliations individually would mean six near-identical runs. |
| **Findings** | NF-64, NF-126, NF-125, NF-61, NF-44, NF-143 |
| **Files** | `volume_guard.py`, `scrumming_bot.py`, `gate_chain.py`, `idempotency.py`, `privacy_mask_registry.py` |
| **Risk tier** | record-only |

**Steps**

1. `VolumeGuard`: MEM-259's disable is enforced at one call site while `execute()` still reads `config.enabled` (NF-64) — make one authority.
2. `YTD_TRADE_MAX_PAGES` is declared 40 while the loop hardcodes 12 (NF-126) — honour the constant or delete it.
3. `import_scrumming_state`'s drift check is structurally unreachable after MEM-254 while its docstring promises the warning (NF-125).
4. `GateContext.delta_pct` is fed a raw USD amount no gate reads (NF-61) — name it correctly or remove it.
5. `idempotency.invalidate()` is dead while the module docstring promises a 4xx invalidation path (NF-44).
6. `privacy_mask_registry`'s class docstring contradicts `mask_or`'s own allowlist contract (NF-143).

**Entry gate** — C43 green.

**Exit gate (measurement):** for each of the six, either a test asserts the declared value **is** the value used (e.g. setting `YTD_TRADE_MAX_PAGES=3` limits the loop to 3 pages), or grep shows the declaration removed. Six assertions, six greps, zero remaining divergences.

**New tests** — `tests/test_declared_knobs_honoured.py`.
**Rollback** — restore snapshot; no behaviour change means rollback is free.
**Operator decision** — whether `VolumeGuard`'s authority is the call site or `config.enabled` — MEM-259 says disabled, and the two must agree.

---

### 64 — C41 · Load-bearing comment corrections on live code *(v3.25.21, record-only)*

| | |
|---|---|
| **Goal** | No comment on a live decision path tells the next implementer that live code is dead, or that a backstop exists when it does not. |
| **Why here** | Record-only but grouped apart from cosmetic doc rot because these are the comments that would cause a **live mistake** — including on the very threshold C39d just changed. |
| **Findings** | NF-141, NF-90, NF-104, NF-132, NF-136 |
| **Files** | `gate_chain.py`, `smart_orders.py`, `scrumming_bot.py`, `data_pool.py`, `bot_live_settings.py`, `bot_wizard.py`, `main_window.py` |
| **Risk tier** | record-only |

**Steps**

1. `gate_chain.py:30` says "this module is dead code" while `scrumming_bot.py:346/:6871` builds and evaluates the chain as the live SCRUM trigger — correct it and cross-reference C39d's threshold so a maintainer editing it knows it is live.
2. Correct `smart_orders`' "execution-level backstop" claim in all four places (three in `scrumming_bot`) — the engine has zero callers, which is what makes the registry pre-check's fall-through look safe (NF-90).
3. Correct `data_pool`'s header, which teaches a push architecture that was replaced (NF-104).
4. Correct the Aggressive Trading label, which promises IOC takers on every order when only Stack tranches consult the flag (NF-132).
5. Fix Help→About: it reports v1.7 and advertises deleted Grid Mode (NF-136).

**Entry gate** — C39d green so the `gate_chain` correction can cite the real, current threshold.

**Exit gate (measurement):** grep finds zero occurrences of "dead code" in `gate_chain.py`, of the backstop claim at the four sites, and of "Grid Mode" in the About dialog; Help→About renders the string from `src/__init__.__version__` (assert equality, which C43's consistency check also enforces).

**New tests** — `tests/test_about_dialog_version.py`.
**Rollback** — restore snapshot; comments only.

---

### 65 — C56 · Dead-weight sweep: delete or declare *(v3.25.22, record-only)*

| | |
|---|---|
| **Goal** | The 95 verified-open anchors and their named companions are each dispositioned, with nothing silently removed from a live path and nothing left broken behind a "keep" verdict. |
| **Why here** | Last by doctrine, and `single_edit_pass` is **false** — a disposition pass, not one edit. **HAZARD:** eight of the twelve modules have zero test coverage and `main_window`/`bot_visualizer` import optional subsystems inside bare `except Exception:` blocks, so deleting one produces no failure, no import error and no log line — just a platform that silently stopped notifying. |
| **Findings** | NF-155, NF-101, NF-49, NF-55, NF-56, NF-57, NF-60, NF-63, NF-164, NF-98, NF-99, NF-39 |
| **Files** | `usb_auth.py`, `shared_testnet.py`, `market_hours.py`, `capital_arbiter_bridge.py`, `capital_registry.py`, `poa_tournament.py`, `triangular_swarm.py`, `live_monitor.py`, `notifications.py`, `sound_engine.py`, `docs/audits/2026-08-04_needed_fixes_list.md` |
| **Risk tier** | record-only |

**Steps**

1. BEFORE any deletion: extend CV1's boot smoke test to assert a **NAMED** list of subsystems is non-None, converting each swallowed import into an assertion; add an import-graph check that no surviving module names a deleted one.
2. Give the sweep an explicit per-item acceptance line — a sweep with no criterion cannot be gated.
3. *Correction — split the finding set into two bands with different gates, because seven of the twelve ids are real functional defects that a "keep" verdict would leave unfixed while the cascade reports green.*
   - **Delete-or-keep band** (disposition gate suffices): `usb_auth` (NF-101), `shared_testnet` (NF-49's threading-invariant text), `triangular_swarm`, `capital_arbiter_bridge` (NF-56), the NF-155 anchors.
   - **Fix-required band** (a per-item **behavioural** gate fires whenever the disposition is "keep"): NF-164 (`TradeJournal.verify` at `live_monitor.py:61-67` counts lines and unconditionally returns True, while carrying a `fail-loudly(R28)` annotation — it is the tamper-evidence for the live trade journal); NF-55 (`market_hours.py:195-207` hardcodes `et_offset = -5` with the comment "Approximate", so Eastern Time is an hour wrong every EDT month); NF-49 (worker mutates `LocalTestnet` off the GUI thread); NF-56 (absolute USD passed where a [0,1] fraction is expected); NF-57 (`drift_usd` identically equals `free_usd`); NF-60 (`hash()` breaks replay determinism); NF-63 (`KeyError 'arm_scores'`).
4. Ship the three real fixes in the same sweep: the discarded notification level (NF-98), the sound engine's silence on macOS/Linux (NF-99), and the unreachable SMS channel (NF-39) — *the last of which is decided in C12's entry gate, not here.*
5. Split NF-155's 95 anchors into the dead-code sweep and the stale-doc sweep it was already triaged into, and record each disposition.

**Entry gate** — C11 and C49 green (their decisions bound what is genuinely unreachable); the extended boot smoke test with the named subsystem list passing on the baseline; C12's SMS disposition already recorded.

**Exit gate (measurement):** the boot smoke test passes after every deletion with its named list intact; the import-graph check reports zero references to deleted modules; **each of the 95 anchors has a recorded disposition (count == 95, zero undispositioned)**; for every fix-required item dispositioned "keep", its behavioural pin passes — e.g. `verify()` returns False on a tampered journal line; `_to_eastern` returns the correct hour on an EDT date **and** an EST date; NF-98's notification level appears in the delivered notification (asserted on a captured notification object); NF-99's sound engine reaches a non-silent platform branch. For any fix-required item dispositioned "delete", the gate is the grep + boot-smoke assertion instead.

**New tests** — `tests/test_boot_subsystems_present.py`, `test_import_graph_no_deleted_modules.py`, `test_notification_level_delivered.py`, `test_sound_engine_platform_branch.py`, plus one behavioural pin per "keep" in the fix-required band.
**Rollback** — per-item restore from snapshot; each disposition is its own commit precisely because this cascade is not a single edit pass.
**Operator decision** — twelve delete-or-keep calls. Notably the USB auth path (NF-101); the SMS channel (NF-39) is already decided at C12.

---

### 66 — C57 · INVESTIGATION: capital-reservation over-commit storm on the live fleet *(investigation-only, no fix in scope)*

> **QUEUED 2026-08-07 by operator directive**, from a live console
> screenshot at 19:25:19–19:25:20. *"Add an investigation to the end of
> the cascade series for these warning messages in the console."*
>
> **This is an INVESTIGATION cascade. It produces a report, not a fix.**
> Scope the remediation afterwards, as its own live-behaviour cascade
> under M2 — this touches live capital accounting on 35 real bots.

| | |
|---|---|
| **Goal** | Explain, from evidence, why `capital_reservation.reserve()` raises over-commit on at least 10 live bots within a two-second window, and whether any live behaviour is degraded by it. |
| **Why here** | Operator placement. **Flagged for possible promotion — see the hazard note below.** |
| **Findings** | New — C57-1 (accumulation signature), C57-2 (~10% sizing signature), C57-3 (duplicate emission) |
| **Files** | `trading/capital_reservation.py`, `trading/scrumming_bot.py`, `trading/wallet_reservations.py`, `core/logging_engine.py` |
| **Risk tier** | investigation-only (record-only until scoped) |

**Verified anchors** (read 2026-08-07, not from the screenshot):

- The raise: `capital_reservation.py:311-320` — `reserve:` computes
  `existing = sum(r.qty for r in self._reservations.values() if r.asset == asset)`
  and raises when `existing + qty > total_holdings + 1e-12`.
- The catch: `scrumming_bot.py:1228-1235` — a bare
  `except Exception` that logs the warning, then sets
  `self._crr_token = None` and `self._crr_last_reserved_qty = 0.0`.
- A second over-commit site exists at `capital_reservation.py:404`
  (`update:`), which the screenshot does **not** show firing.

**The evidence, as arithmetic.** Two populations, and they are not the
same defect:

*C57-1 — existing reservations ALONE already exceed holdings.* In every
non-zero case on screen, the ledger holds more than the wallet does,
before the new request is even considered:

| bot | asset | existing | holdings | existing ÷ holdings |
|---|---|---|---|---|
| f9cfb7ba | CAP | 3096.547142 | 1502 | **2.06×** |
| e6df7221 | HYPE | 2.067724682 | 0.925 | **2.24×** |
| ff6a37a3 | ADA | 169.7530864 | 122.3570869 | **1.39×** |
| 9f737e8f | NEAR | 32.95386459 | 31.332 | **1.05×** |

*C57-2 — zero existing reservations, request alone ~10% over.* Nothing
is reserved at all, so this cannot be a stale-reservation problem, and
the ratio is suspiciously tight across six unrelated assets:

| bot | asset | requested | holdings | ratio |
|---|---|---|---|---|
| 650df31a | PUMP | 24666.20294 | 22358 | 1.1032 |
| 7a4e0e88 | HBAR | 812.9134854 | 737.8 | 1.1018 |
| 7a0334bb | PENGU | 18193.80093 | 16668 | 1.0915 |
| c8e5c5db | CHIP | 11170.07564 | 10210 | 1.0940 |
| d9681a57 | ONDO | 238.9268268 | 214.66 | 1.1131 |
| 934f242d | LTC | 0.6029379522 | 0.53232758 | 1.1326 |

Range 1.09–1.13. A consistent ~10% overshoot across six assets with
different prices and decimals is a *sizing* signature, not a leak.

*C57-3 — every warning appears TWICE*, same bot, same asset, same
second, consecutive lines. Either the emit path runs twice or two
handlers render to the same console pane.

**The message itself is wrong for half its audience.** It advises
*"Release stale reservations or reduce request"* — but the C57-2
population has **zero** reservations to release.

**Leads to test — HYPOTHESES, not findings.** Nobody has investigated
this; the next session starts cold and must falsify each:

1. *Orphan-on-exception loop.* The handler at `scrumming_bot.py:1233`
   discards `_crr_token` on **any** exception, while
   `_release_capital_reservation` needs that token to release. A bot
   that fails once forgets the handle to its own live reservation and
   requests a new one next tick — permanently, since every later
   reserve then trips the check the orphan created. Would explain
   C57-1's 2× ratios. **Falsifier:** the registry's heartbeat-staleness
   prune should reclaim orphans; check whether `heartbeat()` is
   reachable when `reserve()` raises — it is called after the reserve
   in the same `try`, so it may never run. If the prune does fire, this
   hypothesis is dead.
2. *Target-vs-actual sizing.* C57-2's ~10% suggests the request is
   computed from a target or a stale holdings snapshot while the check
   uses a fresh one. **Falsifier:** if the overshoot tracked price
   movement it would vary far more than 1.09–1.13 across six assets.
3. *Duplicate emission.* Compare against the v3.24.x logging work —
   `logging_engine.py` already had one records-dropping defect.

**Do NOT assume this is harmless.** The handler says "continuing tick",
and `wallet_reservations.py` is documented as *advisory*, which suggests
no order is blocked. **That is exactly the kind of claim this
investigation exists to verify, not to inherit.** Trace whether a failed
ensure gates a SELL, and whether cross-bot contention on a shared asset
silently changes sizing.

**Steps**

1. Cold-read the three anchors above; confirm the two populations are
   distinct and re-derive both tables from the live logs, not the
   screenshot.
2. Instrument, do not guess: capture `_reservations` for one affected
   bot across consecutive ticks and show whether entries accumulate.
3. Establish a **positive control** before reporting any zero — an
   instrument that cannot observe a released reservation cannot prove
   one leaked.
4. Determine the blast radius: does a raised ensure change any order
   the bot would otherwise have placed? Answer at the consumer.
5. Write the report. Scope remediation as a separate live-behaviour
   cascade; do not fix inside this one.

**Exit gate (measurement):** a written report that (a) reproduces both
tables from log evidence, (b) names the mechanism for each population
or states plainly that it could not be determined, (c) answers the
blast-radius question with a consumer-side measurement, and (d) either
explains the duplicate emission or records it as still open.

**HAZARD — placement.** Queued at the tail as directed. Recording the
one fact that might change that call: this is **live, now, on real
capital**, and the C57-1 population shows a ledger holding 2× what the
wallet contains. If leads (1) proves out, an affected bot is stuck
permanently — every subsequent reserve fails against an orphan it can no
longer release — and nothing in the log distinguishes "stuck" from
"noisy". Thirty-five bots are trading against this. **Operator decision:
leave at tail, or promote ahead of the sim band.**

---

### 67 — C58 · Caller contracts: the direct-call analogue of `emit_contracts` *(tooling, record-only)*

> **QUEUED 2026-08-08 by operator directive.** *"'Zero production
> callers' is probably the closest and best approach to what we want for
> this particular problem. If working on module X, needs production
> callers A, B, C from source. Can use this as a starting point for
> cataloging all our modules['] emitters and their expected behavior in
> the context of the full platform and trading strategy."*

| | |
|---|---|
| **Goal** | Every module declares who is expected to call it, and a static check reports the gap. Extends `emit_contracts.py` from bus coupling to direct-call coupling. |
| **Why here** | Tail by directive. It is tooling, not a defect fix, and its value is cumulative across the remaining cascades rather than blocking any one of them. |
| **Files** | `src/core/emit_contracts.py` (pattern to follow), new `tools/harness/` check |
| **Risk tier** | record-only — analysis, no runtime behaviour |

**Why this is the right mechanism, and what it cannot do.**
`emit_contracts.py` already solves this shape for **bus emissions**, and
names the class precisely: *"Never emitted — a topic that is declared
but never fires. This is the zero-call class that hid
`SimStatStrip.set()`, `compare_trades()`, `SystemLoadOscillator` and
`register_sim_run()`, each of which passed its tests without ever
running."* The gap is that nothing does the same for **direct calls**.

A call-graph fact is mechanically decidable — no judgement, nothing to
hallucinate: *does symbol S have a caller outside `tests/`?* That is
what makes it worth building. **It cannot decide whether the code was
right**, and the cascade must not claim otherwise.

**Evidence it would have paid for itself.** Five separate defects in
this series share the identical signature:

| Symbol | Consequence |
|---|---|
| `set_topologies` | zero callers, so `_topology_pairs` always took its fabricated fallback — the whole reason the invented circular topology survived (fixed v3.24.76) |
| `set_swarm_hooks` | zero callers, so the Simulator Swarm was never driven from Nuclear |
| `clear_markers()` | zero callers (W5) — the API that would have made two other findings fixable |
| `register_sim_run()` | zero callers; `nuclear_verification.py` documented its own inertness |
| C23 step 1's exit criterion | called a private method **directly**, so it passes GREEN on dead code |

The last row is the sharpest: a test that calls a symbol with no
production caller is measuring nothing, and no existing gate says so.

**Steps**

1. Build the call-graph check: AST over `src/`, resolving calls by name
   and attribute, with `tests/` excluded from the caller set. Report
   every public symbol whose only callers are tests, and every symbol
   with no caller at all.
2. Add the **declaration** half — the operator's "needs production
   callers A, B, C". A module states its expected callers; the check
   reports declared-but-absent and present-but-undeclared. Mirror
   `emit_contracts.py`'s three failure classes: *never called*,
   *called from an unexpected site*, *called with a shape the callee
   does not accept*.
3. Flag the test-only-caller case explicitly, so an exit criterion that
   exercises dead code cannot read as coverage.
4. Seed the catalogue: walk every module, record its emitters and its
   expected callers **in the context of the platform and the trading
   strategy** — what the thing is for, not just what calls it. This is
   the durable deliverable; the checker is the enforcement.
5. Observation only, per `emit_contracts.py`'s own design note: a
   contract violation must never raise into a live path.

**Exit gate (measurement):** the checker runs over `src/` and its output
reproduces the five known cases in the table above (a **positive
control** — a checker that cannot rediscover them is not measuring
anything); at least one module carries a declared caller contract
end-to-end; and the catalogue covers every module in `src/` with an
explicit "expected callers + purpose" entry, with unknowns recorded as
unknown rather than omitted.

**Deliberately NOT in scope — a general "happy-path avoidance"
detector.** Considered and rejected. The invented circular topology was
syntactically clean, commented, tested, and passed every gate; what made
it wrong was a design fact living outside the code (bot_state is the
only legitimate fleet source). No static analyzer can know that, and a
check claiming to catch it would fire mostly false positives and train
its reader to dismiss it — worse than not having it. Operator's own
framing: *"or just result in another harness-based hallucination that is
pretending to do something useful."* Keep the checks to what is
decidable.

---

### 68 — C59 · DESIGN: the optional data-fetching API has no way in *(design, then implementation)*

> **QUEUED 2026-08-08 by operator directive.** *"We have the main
> exchange trading API and then an optional data fetching API. There is
> currently no entry field or means of adding a data fetching API so
> this also another design piece that needs to be appended to the
> cascade series."*

| | |
|---|---|
| **Goal** | A data-fetching API can be entered, stored, and used for market data, separately from the exchange trading API — and its absence falls back cleanly to today's behaviour. |
| **Why here** | Tail by directive. Design first; implementation follows the design, not this entry. |
| **Files** | `gui/settings_dialog.py`, `gui/init_wizard.py`, `exchange/ccxt_connector.py`, `exchange/data_pool.py`, `exchange/api_load_monitor.py` |
| **Risk tier** | live-behaviour — it touches credential storage and the connector that places real orders. Rides alone. |

**Verified state, 2026-08-08 (not assumed):**

- **No data-fetch API concept exists in code.** Repo grep for
  `data_api`, `data_fetch`, `DATA_API`, `market_data_api`,
  `secondary_api` across `src/` returns **nothing**.
- **Market data is fetched through the TRADING connector.** Every
  OHLCV path resolves to `ccxt_connector.fetch_ohlcv`
  (`:886`, `:915`, `:918`, `:924`), and `data_pool.py:161`'s
  `get_or_fetch_ohlcv` sits on top of it.
- **The trading API's rate budget is already the binding constraint,
  and OHLCV is the heaviest consumer.** `api_load_monitor.py:33-44`:
  `DEFAULT_CEILING_CPM = 600.0`, `DEFAULT_SAFETY_PCT = 0.75` ("refuse
  new phantoms above this"), and in its own words *"The heaviest
  single-tick call is the OHLCV fetch."*
- **Entry exists only for exchanges.** `settings_dialog.py:80` adds an
  "Exchanges" tab; there is no second credential surface.

**What this means, stated plainly.** Stone Tablet appends, YTD history
fetches and phantom warm-up all spend the *trading* connector's rate
budget. That budget is what throttles live order placement. A separate
data API is not a convenience — it decouples "read the market" from
"trade the market", so a heavy history pull cannot compete with a fill.

**Design questions to answer BEFORE any implementation:**

1. **Scope of the split.** Which calls are data (OHLCV, tickers,
   markets, history) and which are trading (orders, balances,
   positions)? Enumerate against `ExchangeInterface`, not from memory.
2. **Fallback semantics.** "Optional" means absent → use the trading
   connector, exactly as today. That fallback must be explicit and
   logged, never silent, or a mis-entered data API degrades invisibly
   into extra load on the trading budget.
3. **Credential storage.** Where, and under what protection? The
   trading credentials live at `~/.acervator/coinbase_credentials.json`
   and are never to be read, echoed or committed. A second credential
   set inherits every one of those constraints.
4. **Per-connector rate accounting.** `api_load_monitor` currently
   reasons about one budget. Two connectors means two budgets, and the
   phantom-admission check must know which one it is spending.
5. **Provider shape.** Same CCXT interface against a different venue, or
   a genuinely different provider? This decides whether the split is a
   second connector instance or a new adapter.
6. **Simulator/Paper interaction.** Per the fleet-source rule, sim reads
   Stone Tablets and never calls an API mid-run. Confirm the data API
   changes only the *append* and *YTD fetch* paths, and nothing a
   replay touches.

**Deliverable of the design phase:** a written design in
`docs/audits/`, answering all six, before a line is implemented.

**Exit gate (implementation, once designed):** a data API can be entered
and persisted; data calls route to it while order calls do not; absence
falls back to the trading connector **with a log line**; `api_load_monitor`
reports the two budgets separately; and a pin proves no order path can
reach the data connector.

---

### 69 — C60 · DESIGN: Market Inspector's tiered topology push *(design, then implementation)*

> **QUEUED 2026-08-08 by operator directive.** *"It should have separate
> routes i.e. Push to Sim (Tier 1a and Tier 1b (Verified Back Test w/
> Robust Hypothetical Profit and Performance Metrics — Call the TA Quant
> Archetype if needed…)), Push to Paper (Tier 2), and Push to Live
> (Tier 3)."*
>
> And on the destination: *"Topologies naturally have to map to the Bot
> Swarm Tab (Sim, Live, or Paper) and then be controlled / monitored by
> the corresponding mode (Simulator controls Sim Bot Swarm, Paper Trader
> controls the Paper Swarm, and Live, of course, controls the Live
> Swarm)."*

**VOCABULARY — fixed by operator directive 2026-08-08.** *"Strategies =
Topologies for Market Inspector … we should avoid term conflation."* In
Market Inspector, a proposal **is** a topology. Do not write "strategy"
for it anywhere in this cascade.

| | |
|---|---|
| **Goal** | A topology proposal is pushed along an explicit promotion ladder, each tier landing in its own swarm and owned by that swarm's mode. |
| **Why here** | Tail by directive. This is the promotion pipeline made concrete at the push surface — design first. |
| **Files** | `gui/market_inspector_topologies.py`, `gui/market_inspector.py`, `gui/bot_visualizer.py`, `gui/main_window.py`, `simulator_tab/`, Paper Trader (does not exist) |
| **Risk tier** | Tier 3 touches live capital and **rides alone**. Tiers 1a/1b are sim-only. |

**The ladder, and each tier's destination:**

| Tier | Route | Swarm | Controlled by |
|---|---|---|---|
| 1a | Push to Sim | Sim Swarm | Simulator |
| 1b | Verified Back Test — robust hypothetical profit + performance metrics | Sim Swarm | Simulator |
| 2 | Push to Paper | Paper Swarm | Paper Trader |
| 3 | Push to Live | Live Swarm | Live / Trading |

**Verified state, 2026-08-08 (read, not assumed):**

- **The three swarms already exist.** `bot_visualizer.py` carries
  `_sim_swarm_layout` (:1514), `_paper_swarm_layout` (:1610), plus the
  live rows, with `register_sim_run` / `update_sim_run` / `stop_sim_run`
  and a `register_paper_run` sibling. The destination structure the
  operator describes is built; what is missing is the routing INTO it.
- **Tier 1a exists as of v3.24.79** — but only as a *pull*, not a push:
  Nuclear resolves `current_topology_proposals()` at Start. No
  operator-facing "Push to Sim" control exists.
- **Tier 1b has real foundations, and zero callers.**
  `src/trading/topology_stress.py` already replays a proposal across
  noise realisations through the real `FleetReplayController` and reports
  `median_base_gained`, `dispersion`, `sign_flipped` and a `verdict` of
  ROBUST / FRAGILE / NOISY / NEGATIVE. Its stated finding is *"dispersion,
  not the mean"* — a topology whose accumulation changes **sign** between
  noise draws was fitted to one price sequence. **Nothing calls it**
  (AST-checked). That is the C58 zero-caller class again, and it is most
  of Tier 1b already written.
- **Tier 2 is blocked.** No Paper Trader source file exists anywhere in
  `src/`. Paper remains gated behind Sim + Nuclear per the promotion
  pipeline.
- **Tier 3 exists TODAY WITH NO GATE IN FRONT OF IT.**
  `MainWindow._adopt_topology_proposal` opens the Bot Wizard and creates
  **real bots and real wires on the live fleet**. Nothing requires a
  proposal to have passed Sim or Paper first. Under the operator's ladder
  that is Tier 3 reachable without Tiers 1–2 — **the single most
  consequential finding here.**

**Q1 IS ANSWERED — operator, 2026-08-08:** *"The ladder was intended
mostly as a loose abstraction but could be deployed as an administrative
tool when the platform is eventually able to run in Full Auto Mode."*

**ADVISORY NOW, ENFORCEABLE LATER. Build the RECORD, not the gate.**

This is the shape-determining decision, so state the consequences
plainly:

- **Do NOT block Push to Live on a Tier 1b verdict.** A hard gate built
  today buys nothing and costs the operator a fight every time they want
  to adopt a topology they already trust. Surface the tier state; let
  the operator decide.
- **DO build the promotion record properly**, because that is precisely
  what an administrative control reads when Full Auto arrives. A ladder
  with no persisted record is decoration, and retrofitting the record
  later means retrofitting the history too — the runs that would have
  justified a promotion are gone.
- The enforcement switch is then a *policy* question at the Full Auto
  boundary, not a rebuild. Design the record so that flipping advisory →
  mandatory needs no new data, only a new check.
- Full Auto is the stated backbone of the promotion pipeline
  (Market Inspector → Simulator → Paper → Live). This ladder is that
  pipeline's operator-facing surface, so the record's vocabulary should
  match the pipeline's.

**Remaining design questions:**

1. ~~Mandatory or advisory?~~ **Answered above: advisory, with the record
   built to support later enforcement.**
2. **Where does tier state live, and at what grain?** Per topology id, or
   per (topology, tier, run)? An administrative tool will want *which
   run* justified a promotion, not merely that one did. It must survive
   restart.
3. **What does Tier 1b RECORD?** `topology_stress` already emits
   `verdict` (ROBUST / FRAGILE / NOISY / NEGATIVE), `median_base_gained`,
   `dispersion` and `sign_flipped`. Record the verdict **and** the inputs
   that produced it (trial count, candle window, seed), or the record
   cannot be re-derived and is worth little as an audit trail. Note the
   platform metric is **base accumulated**, not P&L — see the module's
   own reasoning, and do not let "profit metrics" reintroduce a P&L
   framing the platform does not use.
4. **What does "Push" mean per tier?** Registering swarm rows, or
   instantiating bots? Tier 1a/1b instantiate sim bots from `bot_state`
   plus the proposal's wires. Tier 3 creates real bots. Those are
   different verbs and must not share one button.
5. **The TA Quant Archetype.** The operator names it for Tier 1b metrics.
   Confirm what exists under the skills-based harness before assuming a
   capability.
6. **Sequencing with C59.** Tier 1b backtests want history; a heavy pull
   on the trading connector competes with live fills.

**Deliverable of the design phase:** a written design in `docs/audits/`
answering all six, before a line is implemented.

**Exit gate (implementation, once designed):** each tier is a distinct
operator action with a distinct destination swarm; a topology's promotion
state is **persisted, re-derivable and visible**; Tier 1b produces a
recorded verdict from `topology_stress` (giving that module its first
production caller); Push to Live remains **reachable without a verdict**
and says what is missing rather than refusing; and a pin proves **no sim
or paper route can reach `_adopt_topology_proposal`** — the same
separation defended in v3.24.79, extended to every tier below Live.

*That last pin is the one that stays mandatory. Advisory applies to the
promotion ladder, never to the sim/live boundary: a simulator route that
can create live bots is a defect at any tier.*

---

## 4. Coverage table

242 findings in, 242 findings scheduled, **zero unscheduled**. Grouped by cascade for compression; the family totals at the foot are the reconciliation.

| # | Cascade | n | Finding ids |
|---|---|---|---|
| 0 | C00 | 0 | *(enabling — snapshot protocol)* |
| 1 | C43 | 6 | NF-159, NF-160, NF-133, NF-65, NF-29, NF-154 |
| 2 | CV1 | 0 | *(detection substrate — see note A)* |
| 3 | CV2 | 0 | *(harness — see note B)* |
| 4 | C01 | 4 | SWARM-4.1, SWARM-4.2, NF-135, NF-156 |
| 5 | C14 | 3 | SN-6, RECORD-4, SN-56 |
| 6 | C15 | 2 | SWARM-4.24, SN-52 |
| 7 | C39f | 1 | SWARM-4.3 |
| 8 | C12 | 3 | NF-6, NF-78, SWARM-T7-12 |
| 9 | C02 | 6 | SWARM-4.19, SWARM-4.20, SWARM-4.21, SWARM-4.22, SWARM-A7, NF-45 |
| 10 | C06b | 1 | SWARM-A1 |
| 11 | C06c | 3 | SWARM-4.25, SWARM-4.26, SWARM-4.27 |
| 12 | C04 | 3 | SWARM-1.1-OVERLAY, NF-3, SWARM-A6 |
| 13 | C05 | 3 | SWARM-A2, SWARM-4.9, SWARM-4.8 |
| 14 | C51 | 1 | NF-4 |
| 15 | C10 | 6 | NF-5, SWARM-A8, NF-107, NF-110, NF-147, NF-47 |
| 16 | C54 | 3 | NF-83, NF-84 *(see note C)*, NF-122 |
| 17 | C07 | 17 | SWARM-4.16, 4.17, 4.18, T7-1, T7-2, T7-3, T7-4, T7-7, T7-11, T7-13, T7-14, SWARM-A4, NF-2, NF-46, NF-105, RECORD-2, RECORD-3 |
| 18 | C03 | 8 | SWARM-4.4, 4.5, 4.6, 4.7, 4.11, 4.15, SWARM-A5, SWARM-A9 |
| 19 | C09 | 2 | SWARM-A3, SWARM-4.14 |
| 20 | C11 | 2 | NF-162, NF-109 |
| 21 | C52 | 1 | NF-16 |
| 22 | C53 | 2 | NF-85, NF-58 |
| 23 | C35 | 2 | SWARM-4.28, SWARM-4.29 |
| 24 | C26 | 7 | SN-31, SN-12, SN-13, SN-14, SN-35, SN-34, SN-29 |
| 25 | C28 | 2 | SN-10, SN-36 |
| 26 | C29 | 5 | SN-15, SN-16, SN-30, SN-37, NF-51 |
| 27 | C17 | 5 | SWARM-4.23, SN-42, SN-39, SN-44, NF-9 |
| 28 | C22 | 1 | SN-54 |
| 29 | C16 | 1 | SN-5 |
| 30 | C18 | 3 | SN-1, SN-57, SN-58 |
| 31 | C19 | 6 | SN-17, SN-18, SN-19, SN-20, SN-21, NF-7 |
| 32 | C20 | 3 | SN-8, SN-55, NF-18 |
| 33 | C23 | 9 | SN-22, SN-23, SN-24, SN-25, SN-26, SN-27, SN-28, T7-9, T7-10 |
| 34 | C24 | 7 | SN-2, SN-9, T7-5, T7-6, T7-8, RECORD-1, RECORD-8 |
| 35 | C25 | 3 | SN-3, SN-53, NF-115 *(conditional — see note D)* |
| 36 | C30 | 1 | SN-46 |
| 37 | C61 | 1 | SN-4 |
| 38 | C37 | 2 | TABLET-9, TABLET-10 |
| 39 | C36a | 5 | TABLET-2, TABLET-6, TABLET-7, TABLET-8, NF-26 |
| 40 | C36b | 4 | TABLET-5, NF-91, NF-27, NF-28 |
| 41 | C38 | 3 | TABLET-1, TABLET-4, NF-8 |
| 42 | C27 | 6 | SN-11, NF-19, SN-33, SN-32, SN-51, NF-79 |
| 43 | C31 | 2 | DOCKET-OHLCV-1, NF-66 |
| 44 | C32 | 3 | DOCKET-OHLCV-7, DOCKET-OHLCV-8, **SN-50** *(was mis-cited as "NF-50")* |
| 45 | C33 | 6 | DOCKET-OHLCV-2, -3, -4, -5, -9, TABLET-3 |
| 46 | C34 | 4 | SWARM-4.30, NF-137, SWARM-4.31, DOCKET-OHLCV-6 |
| 47 | C39d | 1 | NF-72 |
| 48 | C47 | 2 | SN-40, SN-41 |
| 49 | C39a | 1 | NF-21 |
| 50 | C39b | 1 | NF-70 |
| 51 | C39c | 1 | NF-24 *(FOLD half refuted — see note E)* |
| 52 | C60 | 2 | NF-68, NF-158 |
| 53 | C40a | 4 | NF-69, NF-23, NF-25, SN-48 |
| 54 | C40c | 1 | NF-67 |
| 55 | C13 | 1 | SN-7 |
| 56 | C46 | 2 | SN-38, NF-89 |
| 57 | C45 | 6 | NF-13, NF-41, NF-74, NF-157, NF-103, NF-14 |
| 58 | C49 | 7 | NF-94, NF-82, NF-88, NF-87, NF-76, SN-49, SWARM-4.32 |
| 59 | C42 | 4 | RECORD-5, RECORD-6, RECORD-7, NF-22 |
| 60 | C48 | 3 | SN-43, SN-45, SN-47 |
| 61 | C08 | 4 | SWARM-4.10, SWARM-4.12, SWARM-4.13, NF-15 |
| 62 | C44 | 11 | NF-11, NF-12, NF-73, NF-10, NF-134, NF-40, NF-30, NF-31, NF-32, NF-33, NF-34 |
| 63 | C55 | 6 | NF-64, NF-126, NF-125, NF-61, NF-44, NF-143 |
| 64 | C41 | 5 | NF-141, NF-90, NF-104, NF-132, NF-136 |
| 65 | C56 | 12 | NF-155, NF-101, NF-49, NF-55, NF-56, NF-57, NF-60, NF-63, NF-164, NF-98, NF-99, NF-39 |
| 66 | C57 | 3 | C57-1, C57-2, C57-3 *(new 2026-08-07, investigation-only)* |
| 67 | C58 | 5 | `set_topologies`, `set_swarm_hooks`, `clear_markers`, `register_sim_run`, C23-step-1 exit criterion *(new 2026-08-08, tooling)* |
| 68 | C59 | 1 | optional data-fetching API has no entry field or routing *(new 2026-08-08, design-then-implement, live-behaviour)* |
| 69 | C60 | 4 | tiered topology push (1a Sim / 1b Verified Back Test / 2 Paper / 3 Live); Tier 3 currently reachable with no gate *(new 2026-08-08, design-then-implement)* |

**Reconciliation by family**

| Family | Range | Count | Scheduled | Unscheduled |
|---|---|---|---|---|
| SWARM-4.x | 4.1–4.32 | 32 | 32 | 0 |
| SWARM-T7-x | T7-1–T7-14 | 14 | 14 | 0 |
| SWARM-Ax | A1–A9 | 9 | 9 | 0 |
| SWARM-1.1-OVERLAY | — | 1 | 1 | 0 |
| NF-x | NF-2…NF-164 (non-contiguous) | 101 | 101 | 0 |
| SN-x | SN-1–SN-58 | 58 | 58 | 0 |
| DOCKET-OHLCV-x | 1–9 | 9 | 9 | 0 |
| TABLET-x | 1–10 | 10 | 10 | 0 |
| RECORD-x | 1–8 | 8 | 8 | 0 |
| **Total** | | **242** | **242** | **0** |

**Notes on partial or conditional coverage** — none of these is an unscheduled finding; each is a scoping fact the executing engineer must carry.

- **A · CV1 claims nothing.** The original plan assigned SN-6, RECORD-4 and TABLET-9 to CV1. CV1's five steps build **detectors** — a live-tree guard, an archive-root guard, a singleton-resolution guard, test-count floors, a pin inventory — and touch neither `feature_telemetry.py` (SN-6/RECORD-4's root cause) nor `test_stone_tablets_auto_updater.py` (TABLET-9's deliverable). A detector that makes a defect visible is not the defect being remediated. All three are claimed by the cascades that actually fix them: SN-6 and RECORD-4 by **C14**, TABLET-9 by **C37**.
- **B · CV2 claims nothing.** The original plan assigned SN-40/SN-41 to both CV2 and C47. CV2 builds the golden-baseline tool; **C47** performs the de-duplication and memoisation. Single claim, at C47.
- **C · NF-84 may relocate.** `accumulated_fold`/`accumulated_distribute` are declared (`bot_container.py:762-763`) with zero writers anywhere in `src/`, and their only reader is `fleet_replay_panel.py:1061` reading `bot.stats` directly. C54 either writes them at the FOLD/DIST execution sites **or** — if the operator judges them dead — hands NF-84 to C56's delete-and-remove-the-consumer band. Whichever, it is dispositioned, not dropped.
- **D · C25 is conditional.** SN-3, SN-53 and NF-115 are scheduled but execute **only** if C24 slips or the old `NuclearController` still has a production construction. If C25 is skipped, its closure evidence is the recorded grep showing zero constructions — the ids close as *retired with the path*, not as fixed.
- **E · NF-24 is half-refuted.** Its FOLD half was refuted by its own verifier (`buy_cost` there is already QUOTE, so `buy_cost / buy_fill` is correct). C51 fixes only the INITIAL ENTRY half at `scrumming_bot.py:5790` and records the refutation in the commit. Fixing the FOLD half would be a regression.
- **F · NF-155 is a container, not an item.** It carries 95 verified-open low-severity anchors. C56 splits them into a dead-code sweep and a stale-doc sweep and requires a recorded disposition for each (count == 95, zero undispositioned) — the anchors are dispositioned individually even though they enter as one id.
- **G · NF-39's decision moves earlier than its fix.** The SMS disposition is taken at **C12**'s entry gate (position 8) so C12's exhaustive widget-coverage pin does not lock in keys for a dead delivery path; the code change itself lands with C56 (position 65).

---

## 5. Operator decisions required

Thirty-one judgement calls, each blocking a named cascade's entry gate. Recommendations are mine; the trading and capital-allocation ones are yours alone.

### Blocking before any work starts

| # | Cascade | Decision | Options | Recommendation |
|---|---|---|---|---|
| D1 | **C00** | Version control | `git init` + baseline commit · dated snapshot protocol under `_archive/` | **`git init`.** It makes 66 rollback fields, every failing-first step, and CV2's tree-pair diff work natively and costs ten minutes. The snapshot protocol is a full substitute but pays a copy cost on every cascade. |
| D2 | **CV2** | Which fixture windows constitute the standard diff set | Operator-chosen | Pick windows spanning at least one strong trend, one range, and one gap/late-listing case per venue. These become the evidence base for **every** live gate below, so choosing them badly is choosing to prove less. |

### Capital-allocation and trading policy — only you can make these

| # | Cascade | Decision | Options | Recommendation |
|---|---|---|---|---|
| D3 | **C60** | **The sibling-claim semantics** | Sum every sibling's `target_balance` (with 35 USD bots, *nothing ever enters*) · sum only ACTIVE claims · return 0.0 (*up to 35 simultaneous live BUYs on the first armed tick*) | Sum ACTIVE claims only, then dry-run for one full session and read the per-bot `_quote_free` table before arming a single bot. The other two options are both mass-scale, in opposite directions. |
| D4 | **C31** | **THE OHLCV window: 100, 300, or other** | Operator-chosen | Do not accept the venue default by accident-correction. 300 is plausibly the better number — Heikin-Ashi is a forward recurrence seeded at index 0 and EMA is SMA-seeded, so more history is more stable — but decide it deliberately, then propagate to the callers, `gate_healer.BB_LOOKBACK`, both sim exchanges and `data_pool`'s `max(limit, 100)` floor. |
| D5 | **C39d** | The post-correction ADX threshold | ~30 (textbook) · other | ~30, then read the decision table before arming. How aggressively trend should suppress SCRUM is a trading decision, not a math one. |
| D6 | **C39a** | Arm the Smart Ceiling on crypto-quoted bots | Arm · leave inert, per pair | Arming **stops those bots compounding** at maturity. Confirm per affected pair against the before/after FOLD table. |
| D7 | **C39b** | Let crypto-quoted bots fire autonomously | Arm · leave inert, per pair | These bots have **never** fired autonomously. Stage one low-value pair for one session first. |
| D8 | **C39c** | Already-corrupted persisted `_main_lots` | Leave (decisions stay wrong until the position closes) · reconstruct from exchange fill history | Leave, and act on the read-only report. Reconstruction touches live state and needs explicit separate approval. |
| D9 | **C40a** | Revive Stack Mode at all, and on which pair | Revive on one low-value pair · leave dead | Revive only if you want it; it has been dead long enough that the advertised behaviour has never run live. Rolling back returns it to dead, which is the safe state. |
| D10 | **C40c** | Which live Extractors are INVERTED | Confirm the list before arming | Their order sizes change immediately on ship. Confirm from config, not memory. |
| D11 | **C13** | Reservation TTL and paused-bot policy | Prune paused bots after a longer window · never prune while the bot is registered | **Never while registered.** `heartbeat()` fires only from the tick path, so a paused bot never heartbeats and would be pruned within 180 s — freeing a sibling to sell into its holdings. |
| D12 | **C49** | Seven wire-or-delete calls, **PAUSE_ALL** in particular | Wire · delete, per subsystem | Wiring PAUSE_ALL gives the platform power to halt all live trading autonomously. That is a policy decision. If wired, it must ignore events whose `bot_id` is absent from `BotManager._bots`. |
| D13 | **C01** | Delete semantics | Hard key removal · tombstone-with-retention | Hard removal. A tombstone keeps recovery possible but makes the dialog's "this cannot be undone" literally false. |

### Data and archive

| # | Cascade | Decision | Options | Recommendation |
|---|---|---|---|---|
| D14 | **C38** | Sweep cadence, and first armed sweep target | Live archive · **copy-then-swap** | **Copy-then-swap.** The tablet key omits the quote and ingest dedupes on timestamp alone, so a wrong-quote sweep splices two price series with no detector until C36b's checksum verification is proven. |
| D15 | **C36a** | Assets whose archive quote cannot be determined | Refuse the sweep · ask per asset | Refuse. It is the safe default and leaves the asset stale rather than corrupt. |
| D16 | **C30** | Run-directory retention count | 500 (current implicit index policy) · fewer | Fewer than 500 for directories — the index entry is bytes, a run directory is not. |
| D17 | **C34** | If the venue caps below 365 daily bars | Paginate (slower, complete) · accept the cap (faster, shorter history) | Measure the real ceiling first; paginate only if the Inspector's year-scale metrics matter to you. Either way, stop implying 365 when serving fewer. |

### Scope and disposition

| # | Cascade | Decision | Options | Recommendation |
|---|---|---|---|---|
| D18 | **C07** | Sim/Paper rows are theatre to delete · a surface to implement | Delete rows, preserve API · implement | Delete the rows, **preserve** `_sim_swarm_layout` and the register/update/stop API. |
| D19 | **C07 / C24** | Does Nuclear v2 replace the old tape-scout path? | Yes · no | *Hoisted into C07's entry gate.* It decides whether the preserved layout gets a producer, and whether C25 runs at all. Answer before C07, not at position 34. |
| D20 | **C25** | Run or skip | Decided by C24's outcome | Skip if C24 is green and grep shows zero `NuclearController` constructions. |
| D21 | **C02** | The durable Smart Wire channel | Manager + `state_manager.smart_wires` · retain `_apply_routes_to_state` | Manager. It decides whether NF-45 (delete) or SWARM-A7 (retain) is correct — they cannot both be. |
| D22 | **C06b** | Wire-removal confirmation style | Modal per removal · undo-toast with a 5 s window | Modal. Safer; undo is faster only for bulk retopology, which is rare. |
| D23 | **C06c** | May an adopt overwrite an existing pct at all? | Never (skip and report) · overwrite with disclosure | Never overwrite. Report the skipped pairs — a hand-tuned pct is an operator decision the adopt did not make. |
| D24 | **C09** | Approve replacing a currently-green pin | Approve · decline | Approve, with the written record. `test_wire_canvas_ignores_unknown_bot` asserts the defect is correct behaviour; replacing it is the only path that does not violate M7. |
| D25 | **C11** | `SimulatorTab.set_bot_viz` | Implement · delete the call | Delete unless the Simulator is meant to drive the Bot Swarm visual. |
| D26 | **C12** | SMS channel | Wire · delete the tab | *Hoisted from C56.* Delete unless intended — the platform currently persists phone numbers and carrier selections for a path that reports success and sends nothing. |
| D27 | **C18** | Default phantom state for parity runs | Match live (off, faithful) · force on (covers the subsystem) | **Default-off with an explicit toggle.** All 35 bots record `phantoms_enabled=False`; a parity run that forces phantoms on is not a parity run. |
| D28 | **C35** | Secondary topology ranking signal | Liquidity · correlation · existing bot coverage | Liquidity as the tie-break, since `ranked` is already sorted by `baseVolume`. It decides which topology you are shown first. |
| D29 | **C45** | The CPM threshold gating phantom sets | Keep 450 · recalibrate | Recalibrate after C46 — 450 was calibrated against a burn that is about to fall by an order of magnitude. |
| D30 | **C48** | `memorize_to_grid` | Finish the feature · delete | Delete. It is the only consumer of the retained `VotingSummary` graph and has zero callers. |
| D31 | **C55 / C56** | `VolumeGuard` authority; twelve delete-or-keep calls | Call site · `config.enabled`; per module | MEM-259 says disabled — make `config.enabled` the single authority so the two cannot disagree. For C56, note that seven of the twelve are functional defects, not dead weight: a "keep" verdict there obliges the behavioural pin, not just a disposition line. |

---

## 6. What this plan does not cover

Honest residual surface. None of the following is scheduled above, and none should be assumed handled.

1. **The 1105-test baseline is itself unverified.** Every green recorded before cascade 1 was produced by a gate that can print `[OK]` with zero checks run. The count is a number, not evidence. Treat the pre-C43 suite as *unmeasured*.
2. **No wall-clock performance claim in this document is measured.** C08's frame rate, C48's RSS, C46's call-count reduction and C36b's per-chunk timing all carry structural gates plus, where stated, one manual operator measurement. The perf *improvements* are therefore *unmeasured* until those manual passes happen; only the structural properties are gated.
3. **Live-fill verification is out of scope.** Every live gate ships a decision **table** and a staged one-bot session. Nothing here proves an order filled at the expected price on a real venue — that is an operator observation, not a test.
4. **The archive's existing integrity is unknown.** NF-91 means the MANIFEST checksum has been written but never verified since the archive was built. C36b adds verify-on-load, which will tell you whether the 406 existing tablets are clean — but if a splice already happened (NF-26's USD/USDC merge, or the pre-fetcher one-off script whose `source` string appears nowhere in the repo), this plan detects it and does not repair it. Repair would be its own cascade against a fresh fetch.
5. **`bot_state.json`'s current contents are not audited.** C39f snapshots `profit_folding_active` and C39c reports corrupted `_main_lots`, both read-only. Whether other persisted fields have already drifted from operator intent is not examined.
6. **Multi-venue is scaffolded, not tested.** All 35 bots are `coinbase`. TABLET-7 (per-exchange adapter selection), SN-58 (timeframe availability) and NF-26 (quote in the tablet key) are fixed structurally, but nothing here exercises a second venue end to end. The first Kraken bot will find defects this plan cannot predict.
7. **Paper trading remains unbuilt.** C07 deletes the Paper theatre and C11 deletes the dead `_paper_trader` branch. Paper stays gated behind Sim + Nuclear with no source file, per the promotion pipeline. Nothing here advances it.
8. **The old `NuclearController` path is retired by assumption.** If C24 lands, C25 is skipped and the tape-scout code becomes unreachable but is **not deleted**. Deciding its fate is a follow-on disposition.
9. **Cross-cascade interaction beyond the stated edges is not proven.** The ordering encodes the interactions found by cold read and adversarial review. Sixty-six cascades against a 3,257-line GUI module and a ~10,000-line trading module will surface interactions no static pass found; the failing-first discipline (M4) is what catches them, and it only works if it is actually performed.
10. **Nothing here addresses strategy.** Every finding is a correctness, isolation, record-truth or performance defect. Whether the accumulation strategy is *right* — thresholds, wire percentages, target balances, topology choice — is untouched. Fixing the platform makes the strategy measurable; it does not make it good.

