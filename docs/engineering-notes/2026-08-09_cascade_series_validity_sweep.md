# Cascade series — retroactive validity sweep

## 1. Verdict up front

**33 work units shipped. 25 were swept. 5 HOLD. 16 are PARTIAL. 4 are BROKEN. 8 shipped units were never swept at all.**

**The lead finding is C16.** C16 diagnosed a real live-money defect and shipped a sim-only workaround, leaving the live defect firing on the operator's 37-bot fleet.

- The arithmetic: `_compute_reservation_qty` claims `base_units * 1.10`. A bot at target holds ~100% of target, so the claim is ~110% of its own inventory. The registry refuses it on every tick.
- C16's fix (`src/trading/scrumming_bot.py:1214-1215`) suppresses the holdings assertion **for sim bots only**.
- The live failure then fired one day after C16 shipped. The evidence is in the tree: `src/trading/scrumming_bot.py:1168-1174` names XRP, LINK, ORCA, ALLO, BONK, CHIP, GROVE, ONDO, WLFI, KAT, SUI, RAVE, PENGU, TAO, BILL, HYPE, BIO, ADA, XLM, NEAR, AGLD, CAP, VVV, LTC and BTC from the operator's live log, 2026-08-08.
- Every one of those failures was invisible. `_ensure_capital_reservation` is called from `tick()` inside `try/except Exception: logger.debug(...)` at `src/trading/scrumming_bot.py:5101-5107`. C16 did not touch that swallow.

**The live fix is not in version control.** The cap at `src/trading/scrumming_bot.py:1185-1186` (`if _total_holdings is not None and _qty > _total_holdings > 0: _qty = float(_total_holdings)`) exists only in the working tree. `git log -S "CAP THE CLAIM AT WHAT IS ACTUALLY HELD"` returns nothing. `git diff HEAD --stat -- src/trading/scrumming_bot.py` reports +376/-9. The fix that protects real money carries no commit, no CHANGELOG entry, no test and no gate run. One `git checkout` removes it.

Second live-money defect, still open in committed code: **C01 leaves the extractor half of its own fix undone.** `src/trading/bot_container.py:3236-3244` logs "Do not let that record be replaced" and then falls through to `register()`. The scrumming twin at `:3320` ends in `continue`. An extractor bot with a failed state import is therefore registered with default state, and the next 60-second save overwrites its persisted positions.

**What the drift actually was.** It was not bad code. It was bad instruments. 16 of the 75 recorded defects across the 14 fully swept cascades are tests that cannot fail, present in 11 of those 14 cascades. That is the single largest mode and it is the mechanism by which every other mode survived review.

---

## 2. Roster reconciliation

The series is **70 numbered sequence positions (0-69)** in `docs/engineering-notes/2026-08-05_remediation_methodology.md:55-2487`. That is 68 C-entries plus 2 non-C instrument cascades (CV1, CV2). The 68 entries carry only **67 distinct C-ids**, because C60 is assigned twice.

The doc header "66 cascades" is stale. It counts positions 0-65 as of 2026-08-05, before C57, C58, C59 and C60-DESIGN were appended on 08-07 and 08-08.

**What ran.** The series executed positions 0 through 33 contiguously, then stopped. That is 34 positions — the operator's remembered "~34". Within them: 32 shipped, C07 (pos 17) was skipped, C53 (pos 22) was formally deferred.

**Resolution of 31-in-git versus ~34-recalled.** Three effects produce the gap.

1. **Suffixed ids dropped by extraction.** C06b, C06c, C39f and C39g have their own C-tagged commits (`c9eb757`, `51266b1`, `c8520ce`, `d3e4444`) and CHANGELOG sections. A `\bC[0-9]{2}\b` regex does not match them.
2. **Completed with no C-tagged commit.** Two cases. C11 landed inside `953c253`, whose subject is about Manual Fire; the attribution survives at `src/gui/main_window.py:4064` and is pinned over the AST at `tests/test_suite_integrity.py:139-197`. C23 step 3 landed in `a41c9c6`, and its only C-attribution is a code comment at `src/gui/simulator_tab/nuclear_fleet_controller.py:822`.
3. **Five of the 31 are not fixes.** C57, C58, C59 and C60 appear as `queue C57` … `queue C60` — docket additions with no work. C53 appears only as a deferral.

**Net.** 30 roster C-ids shipped + off-roster C39g = 31 C-ids in git. + CV1 + CV2 = **33 shipped work units**. + C53's deferral = 34 dispositioned items.

**Anomalies that must be fixed before any re-validation pass.**

- **C60 is used twice.** Position 52 (`methodology:1687`) is a P0 live-money `AttributeError` on every zero-position bot's tick. Position 69 (`methodology:2354`) is a Market Inspector design item. Commit `617f9d0` refers to the design one. Anyone re-validating C60 from git validates the wrong cascade.
- **C39g is in git and in no series document.** It shipped in v3.24.35 with its own CHANGELOG section at `CHANGELOG.md:2777`.
- **C21, C50, C06a, C39e and C40b do not exist anywhere.** The numbering has genuine holes.
- **Planned version numbers do not locate a cascade.** v3.24.37 through v3.24.49 have no CHANGELOG entry. Six cascades share [3.24.50].

**Where it stopped.** The last numbered cascade is position 33 (C23), 2026-08-07. From 2026-08-08 every commit leaves the sequence. `648ca54` delivers position 34's (C24's) stated goal under the label "W3" with no C-attribution. The series did not stop at a boundary. It dissolved into an adjacent arc while its next position was executed under a different name.

**No halt note exists.** A search of commit subjects, bodies and every `.md` under `docs/` for "hallucinat", "drift", "halt", "series stopped" and "assumed invalid" returns nothing recording an operator decision to stop.

---

## 3. Results table

Provenance codes: **[F]** full verdict record with harness run and issue list. **[A]** verdict recovered from the adversarial pass only; no full issue list was delivered to this synthesis. **[N]** no verdict record of any kind.

| # | Id | Subject | Verdict | Harness | Tests | Pos. control |
|---|---|---|---|---|---|---|
| 0 | C00 **[F]** | Baseline snapshot protocol | HOLDS | Release gate GREEN; per-file N/A at 1369-file scope | none | NO |
| 1 | C43 **[A]** | Release-gate integrity | PARTIAL | `docs_archetype` on its own record: passed=False, 1 high (`vale write-good.So`) | gate refusal reproduced (exit 1, no sidecar) | YES |
| 2 | CV1 **[N]** | Verification substrate | UNVERIFIABLE | not run | unknown | unknown |
| 3 | CV2 **[N]** | Decision-diff harness + TA golden | UNVERIFIABLE | not run | unknown | unknown |
| 4 | C01 **[F]** | State persistence: merge, delete, restore | PARTIAL | `coding` state_manager 0 high; bot_container 22 high (all NOISE) | 4 files, **72** tests | YES |
| 5 | C14 **[F]** | Sim telemetry stops writing the live tree | PARTIAL | `coding` rc 0, 0 high | 6 pins | narrow only |
| 6 | C15 **[F]** | Sim capital registry fails closed | PARTIAL | `coding` 12 high, all vulture varargs NOISE | 52 tests, 5 files | YES (strongest) |
| 7 | C39f **[N]** | Wire creation vs profit_folding_active | UNVERIFIABLE | not run | unknown | unknown |
| — | C39g **[N]** | bot.log diagnostics reach disk (off-roster) | UNVERIFIABLE | not run | unknown | unknown |
| 8 | C12 **[F]** | Settings round-trip | PARTIAL | `coding` settings.py 1 high (NOISE); `gui` dialog 1 high (NOISE) | **15** tests | write-side only |
| 9 | C02 **[F]** | Smart Wire: one durable channel | PARTIAL | `gui` 5 high, all S311 NOISE | 6 pins | YES, but blind |
| 10 | C06b **[N]** | Wire-drag confirmation + audit trail | UNVERIFIABLE | not run | unknown | unknown |
| 11 | C06c **[N]** | Topology Adopt safety | UNVERIFIABLE | not run | unknown | unknown |
| 12 | C04 **[F]** | Wire-canvas geometry | PARTIAL | `gui` 5 high NOISE; 0 high in range | 7 pins | YES |
| 13 | C05 **[F]** | Quick Routing mass ops | PARTIAL | `gui` 0 findings in :995-1190 | 2 files, 20 pins | step 3 only |
| 14 | C51 **[A]** | Indicator panel: stop fabricating TA | HOLDS | `gui` indicator_panel 0 high / 100 total | present | YES |
| 15 | C10 **[F]** | Dashboard display truth (NF-5) | PARTIAL | `gui` main_window 9 high, none in range | 4 files, 65 tests | YES (best in series) |
| 16 | C54 **[A]** | BotContainer status/stats contract | PARTIAL | not delivered | present | unknown |
| 17 | C07 | Delete Sim/Paper theatre | **SKIPPED** | — | — | — |
| 18 | C03 **[F]** | Bot Swarm list view | PARTIAL | `gui` 0 high in range | 14 pins | YES |
| 19 | C09 **[F]** | Lane canvas visibility + O(1) endpoints | HOLDS | `gui` passed=True, 0 high | 20 tests | YES, 1 blind |
| 20 | C11 **[N]** | Dead startup branches | UNVERIFIABLE | not run | `test_suite_integrity.py:139-197` | unknown |
| 21 | C52 **[A]** | History grader time inversion | PARTIAL | not delivered | 2 dead pins confirmed | NO |
| 22 | C53 | Extractor live display | **DEFERRED** | — | — | — |
| 23 | C35 **[A]** | Topology ranking + dismissal persistence | **BROKEN** | `coding` topology_proposals 0 high / 49 | present | confirmed by execution |
| 24 | C26 **[A]** | Fleet Replay control state | HOLDS | not delivered | present | YES |
| 25 | C28 **[A]** | Chart Expand re-entrancy | HOLDS | not delivered | present | YES |
| 26 | C29 **[A]** | Sim chart markers | **BROKEN** | `gui` sim_visuals 0 high / 32 | present | reproduced exactly |
| 27 | C17 **[F]** | Inject the bus and the singletons | PARTIAL | `coding` on 6 files; no high attributable | 3 files, 119 tests | YES, 1 dead class |
| 28 | C22 **[A]** | Restore sim trade-notification trace | PARTIAL | `coding` scrumming_bot 90 high, 1 in range | present | unknown |
| 29 | C16 **[F]** | Sim reservations succeed | PARTIAL | `coding` 90 high, 0 in blast radius | 26 pins | 1 real |
| 30 | C18 **[F]** | Sim TA + phantom input fidelity | **BROKEN** | `coding` 2 high (NOISE); vulture flags the dead method | 2 files | split: 2 groups NO |
| 31 | C19 **[F, truncated]** | Order-execution realism, both venues | PARTIAL | not delivered in full | present | unknown |
| 32 | C20 **[N]** | `_build_sim` constructs what live has | UNVERIFIABLE | not run | unknown | unknown |
| 33 | C23 **[A]** | Harden Nuclear v2 | **BROKEN** | `gui` nuclear_fleet_controller 0 high / 27 | present | critical confirmed |

---

## 4. Cascades that do not hold

### 4.1 BROKEN

Ranked by production impact.

#### C35 — topology dismissal never persists (live settings path)

**Claimed:** proposal ranking plus dismissal persistence.
**True:** the dismissal key is not an `AppSettings` field. The adversarial pass executed the real `SettingsManager` against a temporary config dir and got `SET RAISED: KeyError 'Unknown setting: topology_dismissed_proposals'`, then `GET after set: {}`. `src/gui/market_inspector_topologies.py:497` `_persist_dismissed` catches `Exception` and logs a warning at `:505-508`, so the failure is silent. Every dismissal returns on the next launch.
**Overturned:** the verdict cited `:45` for `DISMISS_SETTINGS_KEY` and `:479-488` for `_persist_dismissed`. The real anchors are `:48` and `:497` / `:505-508`. The substance is confirmed; the anchors drifted.
**To make it real:** add the field to `src/core/settings.py` beside the other dict-valued fields, then a test that calls the real `SettingsManager.set` and re-reads it.

#### C23 — Nuclear gate recording raises on every call

**Claimed:** Nuclear v2 hardened before it becomes reachable.
**True:** verified in current code. `src/gui/simulator_tab/nuclear_fleet_controller.py:1084-1086` calls `self._log.record_gate(bot_id="nuclear", symbol="", payload={...})`. The signature at `src/trading/sim_run_log.py:220-224` is `(bot_id, symbol, gate_state, sim_ts_ms=None, candle_address="")`. There is no `payload` parameter and `gate_state` is required. Every call raises `TypeError` into `logger.debug` at `:1087-1088`. The same defect repeats at `:1117` and `:1130`. Nuclear records no gate decisions at all.
Two further C23 defects survive, both verified today. `nuclear_fleet_controller.py:504` keeps `self.state.total_exceptions += cyc.exceptions` inside `if cyc.ok:`, so a failing cycle discards its own exception count — the exact behaviour C23 step 6 exists to fix. `:830` uses plain assignment `cyc.error = f"{type(r).__name__}: {r}"` inside the results loop, so six worker failures report as one.
Steps 1, 2, 5 and 6 never shipped. Step 7 was struck as dead.
**Premise inversion:** C23's plan treats v2 as unreachable. `src/gui/simulator_tab/nuclear_mode_panel.py:4, :435, :449` show v2 drives Nuclear Mode today.
**To make it real:** correct the three call sites to the real signature, add a positive-control test that asserts a gate row lands in the run log, move the exception accumulation out of the `ok` branch, and accumulate errors into a list.

#### C18 — sim TA fidelity: three of four claims are not wired

**Claimed:** per-timeframe OHLCV, real venue id, replay-clock phantom cadence, honoured phantom setting.
**True:**
- **SN-1 not fixed.** `src/gui/simulator_tab/fleet/sim_exchange.py:101` initialises `self._tf_series = {}`. A repo-wide grep returns only `:101` (init), `:341` (a comment claiming it "is populated per (symbol, timeframe) when the run is built") and `:347` (the read). Nothing writes it. Every `get_ohlcv` misses and falls through to the single native per-symbol series at `:349`. Six phantoms still read one series.
- **Cadence not fixed.** `PhantomBalanceBot.__init__` takes `sim_mode` at `src/trading/phantom_balance.py:141`. The only production construction, `:650-664`, does not pass it. `_sim_mode` is therefore always False, the sim branch at `:257-259` never runs, and the wall-clock `asyncio.sleep` at `:261` is what executes. `tick_for_cursor` (`:199`) has zero production callers and vulture flags it unused.
- **Toggle does not exist.** The `force` parameter at `src/gui/simulator_tab/fleet/fleet_replay_controller.py:189` is never passed True. With every persisted bot at `phantoms_enabled=False`, phantoms are off for the whole replay fleet with no way to turn them on. `docs/engineering-notes/2026-08-05_remediation_methodology.md:906` explicitly forbids that state.
- SN-58 (real venue id) holds at `fleet_replay_controller.py:337-338`.
- The record `docs/engineering-notes/2026-08-07_C18_pin_replacement_record.md:57` asserts "with the per-run toggle forced on, phantoms **are** constructed". No such toggle was ever built.
**To make it real:** populate `_tf_series` at run build; pass `sim_mode=True` at `phantom_balance.py:650-664`; give `force` a caller or delete it. Test the methodology's own gate: the six phantoms return six different series.

#### C29 — sim chart markers freeze the price series

**Claimed:** marker anchoring, axis and lifecycle corrected.
**True:** the decimation at `src/gui/simulator_tab/fleet/sim_visuals.py:838-848` freezes the series. Reproduced exactly by the adversarial pass against the real `SimPriceVwapChart`: at 1 marker per 7 candles the series pins at 501 entries with newest ordinal 1996, unchanged at ticks 1999, 2050, 3000, 4000, 5999 and 9999. At 1 per 10 it freezes at ordinal 2871 through tick 20,000. Mechanism: the newest candle sits at an odd index whenever the retained length is even, is unmarked, and is the entry `_keep` drops; `mark_trade` then re-pins the frozen ordinal. `clear_data` at `:850-859` resets `_series`, `_ordinals` and `_markers` but not `_candles` (`:646`) or `_ytd_from` (`:655`).
**Overturned:** the verdict's per-tick cost of "24x, ~0.10 ms/tick" did not reproduce. Measured 0.880 s versus 0.055 s — 16x, ~0.073 ms/tick. Direction and magnitude hold; the multiplier was inflated.

### 4.2 PARTIAL — the ones with production impact

#### C16 — see section 1. Live defect left open; live fix uncommitted.

Additional defects: `tests/test_sim_reservation_isolation.py:181-203` walks `If` nodes whose test contains `_sim_mode` and asserts none is a bare return — if C16's branch were deleted there would be zero such nodes and the test would pass vacuously. `tests/test_sim_reservation_isolation.py:130-178`, presented as the behavioural pin, never constructs a `ScrummingBot` and never calls `_ensure_capital_reservation`; it would pass with C16 fully reverted. The comment block at `scrumming_bot.py:1191-1213` still asserts a failure that the preceding uncommitted block prevents.

#### C01 — extractor state overwrite (see section 1)

Verified today at `src/trading/bot_container.py:3236-3244` against the twin at `:3320`. Three further defects:
- The boot report at `:3360-3367` logs at ERROR that records "will be DELETED by the next save (PR-0 is log-only)". The carry-forward at `src/core/state_manager.py:122-137` preserves them. The message is the opposite of the behaviour and it points the operator at recovery that is not needed.
- `bot._state_import_failed` is write-only. Set at `:3220`, `:3236`, `:3261`; read nowhere in `src/`, `main.py` or `tools/`.
- Three live comments cite PR-1, a mechanism commit `4e9c113` removed: `bot_container.py:2846-2852`, `:3354-3358`, `tests/test_c01_restore_ledger.py:202`.
- `clear_state()` at `src/core/state_manager.py:507-529` unlinks primary and backup and has zero callers.
**Overturned:** the verdict said 78 tests. The four named files yield **72** (16+15+25+16). The extra 6 belong to `tests/test_c02_smart_wire_persistence.py`.

#### C12 — settings: the cascade fixed a defect it found and not the one it was named for

`docs/engineering-notes/2026-08-05_remediation_methodology.md:294` gives the goal: "Opening Settings and pressing Save cannot change any value the operator did not touch." `src/gui/settings_dialog.py:979-1021` `_load_current` still reads 9 keys while `_save` writes 16. Four font keys now persist and reach no consumer — `src/gui/theme_engine.py:80,82` carries its own literals and `src/gui/main_window.py:4167` hardcodes `QFont("Consolas", 9)`. 1 of the 5 keys landed.
NF-78 is untouched: `_ta_weight_sliders` (`:444`), `_phantom_tf_checks` (`:471`) and the ten SMS widgets (`:751-811`) appear in neither `_save` nor `_load_current`. Three tabs still discard everything the operator types.
Neither the commit body nor `CHANGELOG.md:2694-2702` discloses that steps 3, 4 and 5 were skipped. **This is the pattern the operator's standing rule targets: the harness cannot catch it, because the code that is present is correct.**
**Overturned:** the verdict said 25 tests. `--collect-only` reports **15** (8 functions, parametrized).

#### C14 — the override nothing sets

`src/core/feature_telemetry.py:113-131` resolves the root at call time. But `grep "os.environ\["` over `src/` and `main.py` returns zero hits, and every app consumer goes through the `get_telemetry()` singleton at `:654-660`, whose `_path` binds once. The sim replay writes through it at `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1883-1891`, into `~/.acervator/feature_telemetry.json`. All 6 pins construct `FeatureTelemetry` by hand. `feature_telemetry.py:90-91` states the override is "set by the simulator and by tests"; the simulator half is false.

#### C54 — the correction does not reach the aggregate

`src/trading/bot_container.py:2085` still sums the raw status-dict `portfolio_value` sourced from the uncorrected `:1483`. The claim that the last stale consumer was closed is false.

#### C05 — three pins that cannot fail

`src/gui/bot_visualizer.py:998` `_reject` and `:1013` `_confirm_mass` exist and reach the app path. The pins do not measure them. `tests/test_c05_quick_routing_mass_ops.py:69-78` asserts only that a `_confirm_mass` call appears at a lower line number than the mutation; it never asserts the answer gates it. `:101-140` asserts a `_reject` call node exists; nothing asserts operator-visible output. `:142-154`, docstring "Positive control for the scanner above", never calls the `_scan` closure it names — `_scan` is defined at `:116` inside another test and is unreachable. The plan's entry-gate file `tests/test_quick_routing_matrix_multi_select_v3_23_13.py` does not exist and was never added.
Committed encoding corruption: four U+FFFD characters at `src/gui/bot_visualizer.py:894, :898, :932, :936`.

#### C02 — the record contradicts itself one file over

The code fix holds at `src/gui/bot_visualizer.py:2811` and `:2816-2822`. But `:752-755` still presents `smart_wire_routes` as the persistence mechanism — the exact comment C02's commit says it exists to correct. Worse, `git log -L 1091,1094` attributes `:1091-1093` ("`_apply_routes_to_state` reloads a fresh dict from disk and its save is the ONLY durable effect") to `5d9979c`, cascade C05, committed 50 minutes after C02 measured that same save as non-durable. Two cascades, one file, one day, opposite records.
The read side is still swallowed at `:1461-1463` (`try: _hydrate_smart_wire_routes_from_disk() except Exception: pass`).
**Overturned:** the verdict cited `src/gui/bot_visualizer.py:2788` as saying "emits 31 keys". That citation is **fabricated** — `:2788` reads "``export_scrumming_state`` does not emit that key — so the". Only `tests/test_c02_smart_wire_persistence.py:11` carries the stale count. The measurement half is correct: `export_scrumming_state` (`src/trading/scrumming_bot.py:3723-3885`) emits **38** constant keys.

#### C03, C04, C10, C15, C17, C22, C43, C52 — summarised

- **C03.** SWARM-4.4 and 4.7 hold. SWARM-4.11's mask is computed only inside `update_bots`, so the privacy toggle at `src/gui/bot_visualizer.py:2449-2484` does not refresh the list. Plan step 5 never shipped: `set_bots` constructs 420 `QTableWidgetItem`s on identical input, twice, measured. Four of eight findings have no disposition anywhere.
- **C04.** Fixes 1 and 3 hold and are pinned. Fix 2 is untested — restoring the pre-C04 `resizeEvent` body leaves the file green, because fix 3 repairs the geometry before the assertion reads it. Plan step 3 never shipped: `src/gui/bot_visualizer.py:1662` still sets `WA_TransparentForMouseEvents` False unconditionally.
- **C10.** Both substantive findings shipped and the tests are the strongest in the series. Step 3's four cosmetic findings were deferred to `docs/engineering-notes/2026-08-06_docket_c10_step3_cosmetics.md` — disclosed correctly.
- **C15.** Steps 1, 4 and 5 hold and reach the app path. Step 2's guard lives in `src/gui/simulator_tab/nuclear_controller.py`, which no `src/` module imports since the v3.24.78 repoint. C15 **blinded** two pre-existing tests: `tests/test_fleet_replay_controller.py:57-63` and `:66-78` now return at the new guard before the check they exist to make.
- **C17.** `EventBus.unsubscribe` reaches production at `src/core/logging_engine.py:607-631`. `BotManager(bus=...)` and `detach_bus()` have one production call site each, both inside the orphaned v1 controller. `tests/test_bus_injection_isolation.py:128-154` pins a file the app no longer loads.
- **C22.** Three of the verdict's own citations were **overturned** — see section 8. The conclusion survives for a reason the verdict never states: `NuclearController` v1 has no production caller at all.
- **C43.** The hardening holds: `tools/harness/check_release_readiness.py:185-278` refuses a sidecar when any entry is "skipped", reproduced at exit code 1 with no sidecar written. One sub-claim in commit `d263660` is false — `.vale/styles/write-good/So.yml:3` and `ThereIs.yml:4` carry `level: error`, `tools/harness/docs_archetype.py:435` maps error to high, and `docs_archetype` on C43's own record file returns `passed=False` with one high.
- **C52.** Two pins are dead. The fixture supplies only two newer same-symbol rows, so `[-10:]` and `[:10]` return the same list. `grade_trade` returns D for both `ref=103.0` and `ref=500.0`, because `src/core/trade_grader.py:132` clamps the execution score to [0,1].

---

## 5. Failure-mode census

**Census A — the 14 cascades with a complete delivered issue list (C00-C18, excluding the truncated C19). 75 defects.**

| Mode | Count | Cascades |
|---|---|---|
| **4. TEST WITH NO POSITIVE CONTROL** | **16** | C00, C01, C02 ×2, C04 ×2, C05 ×3, C09, C12, C15, C16 ×2, C17, C18 |
| 3. HALLUCINATED CITATION | 9 | C01, C02, C03, C05, C10, C14, C17, C18 ×2 |
| 1. DEAD ON ARRIVAL | 5 | C01, C09, C14, C16, C18 |
| 2. FIX DOES NOT REACH THE READ PATH | 5 | C01, C03, C12, C14, C18 |
| 5. UNREACHABLE CODE | 4 | C01, C15, C17, C18 |
| 7. SILENT SWALLOW | 4 | C02, C09, C16, C17 |
| 6. GUARD THAT CANNOT FIRE | 3 | C12, C15, C18 |
| Other (outside the 7) | 29 | all |

**Census B — additions from the 10 cascades covered by the adversarial pass only.**

Dead on arrival +1 (C51's `sim_mode` flag, omitted by all three production constructions). Fix does not reach the read path +2 (C35, C54). Hallucinated citation +2 (C51 cites `tests/test_privacy_mask_v3_23_7.py` and `tests/test_indicator_panel_coverage.py`, both absent). Test with no positive control +2 (C52). Unreachable code +1 (C53: `src/trading/extractor_bot.py:234` `set_initial_chunk_rate` has zero call sites). Silent swallow +1 (C23's `record_gate` `TypeError` into `logger.debug`).

**Combined: TNPC 18, HC 11, FDNRRP 7, DOA 6, UC 5, SS 5, GCF 3.**

**What the drift looked like.** Mode 4 dominates and it dominates by a factor of nearly two over the next mode. It is also the enabler. Every mode-1, mode-2 and mode-5 defect in this series shipped past a green pin, because the pin either called the helper by hand (C14, C16, C18), read the source text instead of the behaviour (C02, C05, C12), or asserted an absence with no proof the measured event occurred (C09). Mode 3 is second and is almost entirely **anchor drift** — comments citing versions that were never cut (`v3.24.38`, `v3.24.41`) and line numbers moved by later cascades. The C23 cold read already named this as systematic: every anchor below `nuclear_fleet_controller.py:551` is off by exactly +21 because C20's own commit inserted 22 lines and deleted 1.

**The code was mostly right. The instruments were mostly blind.** That is the shape of the drift.

---

## 6. Test-coverage verdict

Of the 14 fully swept cascades, **13 shipped a test**. C00 shipped none — its invariants (`_archive/` tracked, sidecar ignored, credential patterns held) exist only in a commit message and a `.gitignore` comment.

Of those 13, **8 carry a genuine positive control** that would fail if the fix were removed: C01, C03, C04, C09, C10, C15, C16, C17. **5 do not, or carry one that does not cover the claim:** C02 (blind to f-strings), C05 (only the step-3 file), C12 (write side only), C14 (narrow mechanism only, never the purpose), C18 (two of four groups have none).

The two strongest instruments in the whole series are `tests/test_c10_dashboard_ammo_truth.py` and `tests/test_sim_capital_registry_fail_closed.py`. Both label their controls explicitly and state what would pass vacuously without them. `tests/test_c05_scope_list_stability.py:85-92` is the best single control: it asserts `scrollbar.maximum() > 0` before every scroll assertion.

**Tests that cannot fail, named:**

1. `tests/test_c05_quick_routing_mass_ops.py:142-154` — declared positive control; never calls the `_scan` closure it names.
2. `tests/test_c05_quick_routing_mass_ops.py:69-78` — line-order only; passes if the confirmation's answer is ignored.
3. `tests/test_c05_quick_routing_mass_ops.py:101-140` — call-node existence only; passes if `_reject` returns `None`.
4. `tests/test_c04_wire_canvas_geometry.py:119-131` — passes against the pre-fix `resizeEvent`.
5. `tests/test_bot_swarm_list.py:351-378` — passes when `paintEvent` returns immediately.
6. `tests/test_sim_reservation_isolation.py:181-203` — vacuous if C16's branch is deleted.
7. `tests/test_sim_reservation_isolation.py:130-178` — passes with C16 fully reverted.
8. `tests/test_sim_ta_input_fidelity.py:257-267` — AST name-load; cannot see the empty `_tf_series`.
9. `tests/test_sim_ta_input_fidelity.py:274-290` — `"sim" in seg.lower()`, satisfied by the commit's own comment.
10. `tests/test_sim_ta_input_fidelity.py:292-296` — bare `hasattr`.
11. `tests/test_c02_smart_wire_persistence.py:79-86` — collapses every f-string to one token, so `f".tmp"` passes.
12. `tests/test_c12_settings_roundtrip.py:164-174` — substring greps that pass against a comment.
13. `tests/test_bus_injection_isolation.py:128-154` — AST over a file the app no longer loads.
14. `tests/test_fleet_replay_controller.py:57-63` and `:66-78` — blinded by C15's own guard.
15. C52's two pins — identical slices, and a letter grade clamped at `src/core/trade_grader.py:132`.

**Rule for the re-work: no pin lands without a stated positive control and a stated negative control, and the record must name what the pin would report if the fix were reverted.**

---

## 7. Re-work list

Ordered by production impact.

**1. C16 / C57 — land the live over-commit cap under version control.**
Files: `src/trading/scrumming_bot.py:1159-1186` (commit it), `:1191-1213` (the C16 comment now contradicts the code above it), `:1214-1215` (decide whether the sim-only branch survives gate-latch parity — the cap requires `_total_holdings > 0`, so a sim bot at exactly zero can still claim units it does not hold).
Test: a live-mode `ScrummingBot` at target holdings completes `_ensure_capital_reservation` with no refusal. **Positive control:** the same bot claiming above holdings is still refused — `tests/test_sim_reservation_succeeds.py:57-64` already proves the registry raise fires; reuse it.
Emitter: replace the debug swallow at `src/trading/scrumming_bot.py:5101-5107` with a WARNING carrying `bot_id`, `qty` and `total_holdings`. Register it in `emit_contracts.py`.
Exit: one full live session with zero "requested … > total holdings" rows in `~/.acervator_logs/gate.log`, and a green `check_release_readiness` on a clean tree.

**2. C01 — close the extractor half.**
Files: `src/trading/bot_container.py:3244` (add `continue`), `:3208-3212` (the comment claims both branches fall through), `:3360-3367` (the boot report states the opposite of the behaviour), `src/core/state_manager.py:507-529` (delete `clear_state` or give it a guard).
Test: a paired fixture that fails the import for one extractor and one scrumming bot and asserts `registered is False` for both. **Positive control:** a healthy extractor still registers.
Exit: after a failed import plus one save cycle, the on-disk `extractor_state` still holds the pre-boot positions.

**3. C18 — wire what the record says shipped.**
Files: `src/gui/simulator_tab/fleet/sim_exchange.py:101/:341/:347` (populate `_tf_series` at run build), `src/trading/phantom_balance.py:650-664` (pass `sim_mode=True`), `src/gui/simulator_tab/fleet/fleet_replay_controller.py:189` (give `force` a caller or delete it).
Test: the methodology's own gate at `docs/engineering-notes/2026-08-05_remediation_methodology.md` — the six phantoms return six **different** series. **Positive control:** assert the six are non-empty first, then assert at least two differ on a known-divergent bar.
Emitter: a per-replay count of phantom ticks driven by the replay clock. Zero ticks must fail the run, not pass it silently.
Exit: a replay in which `tick_for_cursor` has a non-zero call count and vulture no longer flags it.

**4. C23 — Nuclear gate recording and cycle accounting.**
Files: `src/gui/simulator_tab/nuclear_fleet_controller.py:1084-1086, :1117, :1130` (match `src/trading/sim_run_log.py:220-224`), `:501-509` (move the exception accumulation out of the `ok` branch), `:830` (accumulate errors into a list).
Test: run one cycle and assert a `gate.decision` row lands in the run log. **Positive control:** assert the row count is zero before the cycle.
Exit: a failing cycle reports its own exception count and every worker failure appears in `cyc.error`.

**5. C35 — make dismissal persist.**
Files: `src/core/settings.py` (add `topology_dismissed_proposals` as an `AppSettings` field), `src/gui/market_inspector_topologies.py:497-508` (the warning-only swallow hides the failure).
Test: call the real `SettingsManager.set` then `get` and assert the value round-trips. **Positive control:** an unregistered key still raises `KeyError`.
Exit: a dismissed proposal is absent after relaunch.

**6. C12 — read back what you write, and stop discarding three tabs.**
Files: `src/gui/settings_dialog.py:979-1021` (`_load_current` reads 9 of 16), `:444`, `:471`, `:751-811` (TA weights, phantom timeframes, SMS — in neither `_save` nor `_load_current`), plus the operator decision on the SMS channel (wire or delete; `:88` still adds the tab).
Test: the plan's three-way set equality — `{value-bearing input widgets} == {keys _save writes} == {keys _load_current reads}`, zero unmatched in any direction. **Positive control:** the extractor must find ≥14 widgets and ≥14 keys before any equality is asserted (the existing control at `:108-114` is the right shape).
Exit: opening Settings and pressing Save changes no value the operator did not touch.

**7. C29 — marker decimation.**
Files: `src/gui/simulator_tab/fleet/sim_visuals.py:838-848` (`_keep` drops the newest unmarked candle), `:850-859` (`clear_data` misses `_candles` at `:646` and `_ytd_from` at `:655`), `:931-937` (focused-view index mismatch between decimated `_series` and un-decimated `_candles`).
Test: 20,000 ticks at 1 marker per 7 candles; assert the newest ordinal advances monotonically. **Positive control:** assert it advances with markers disabled.

**8. C14 — telemetry isolation must reach the singleton.**
Files: `src/core/feature_telemetry.py:654-660` (the singleton binds `_path` once), `:90-91` (the comment claims the simulator sets the override; it does not), `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1883-1891`.
Test: run a replay and assert `~/.acervator/feature_telemetry.json` mtime and size are unchanged. **Positive control:** the sim's own telemetry file exists and is non-empty. `tests/test_nuclear_capital_registry_fail_closed.py:44-56` already uses this fingerprint pattern — copy it.

**9. C15 / C17 — resolve the v1 orphan.**
`src/gui/simulator_tab/nuclear_controller.py` has no importer in `src/`. Delete it, or repoint `tests/test_nuclear_capital_registry_fail_closed.py` and `tests/test_bus_injection_isolation.py:128-154` at `nuclear_fleet_controller.py`. Restore the two tests C15 blinded at `tests/test_fleet_replay_controller.py:57-63` and `:66-78` by passing a registry so the mode check is reached.

**10. C05 — replace the three blind pins** with widget-driving tests, or state in the record that the confirmation gate is unmeasured. Also strip the four U+FFFD characters at `src/gui/bot_visualizer.py:894, :898, :932, :936`.

**11. C60 — fix the id collision** in `docs/engineering-notes/2026-08-05_remediation_methodology.md:1687` and `:2354` before any further re-validation. Anyone validating C60 from git validates the design item, not the P0.

---

## 8. What this sweep did not cover

**Eight shipped work units were never swept.** No verdict record of any kind exists for **CV1, CV2, C06b, C06c, C11, C20, C39f, C39g**. C20 matters most: it touched `nuclear_fleet_controller.py` and its commit `39dc102` is the cause of the +21 anchor drift the C23 cold read recorded. C11 matters second: it is the clearest instance of work landing with no C-tagged commit. C39g appears in git and in no series document at all.

**Ten cascades were swept at reduced depth.** C22, C23, C26, C28, C29, C35, C43, C51, C52 and C54 are reported from the adversarial pass's notes. I did not receive their full verdict records. Their issue lists are therefore incomplete in section 4 and their contribution to the census sits in a separate table in section 5. Their verdict labels are sound — every one was attacked directly — but their defect inventories are not exhaustive.

**C19's record arrived truncated mid-sentence.** Its evidence for SN-17, SN-21 and SN-20 was delivered and shows the fixes present at `src/gui/simulator_tab/fleet/sim_exchange.py:601-611`, `:483-518` and `:793`. Its issue list was not delivered. C19 is recorded PARTIAL on the delivered half only.

**The release gate was not re-run for this synthesis, and every gate result quoted in the verdicts was produced against a dirty tree.** The verdicts cite `[OK] Release-ready (v3.25.1, 2482 tests)`. `src/__init__.py:16` does read 3.25.1, but the tree carries 33 modified tracked files, including `src/trading/scrumming_bot.py` at +376/-9 and five test files. That gate result describes the working tree, not the commits under audit. **No cascade in this series has been gated against its own committed state.**

**Four mutant probes were not reproduced.** The C01, C02, C04 and C05 verdicts report measured pass counts against rebuilt mutants ("12 passed"). The adversarial pass read every assertion each probe targets and confirmed each is structurally blind as described, but did not rebuild the mutants. The conclusions stand on inspection; the specific counts are unreproduced.

**Verdicts overturned by the adversarial pass, corrected above and not silently kept:**

1. **C02, issue 8 — fabricated citation.** `src/gui/bot_visualizer.py:2788` does not say "emits 31 keys". Only `tests/test_c02_smart_wire_persistence.py:11` does. The measurement (38 keys) is correct.
2. **C01 — wrong test count.** 78 → **72**. The extra 6 belong to C02's file.
3. **C12 — wrong test count.** 25 → **15**.
4. **C22, issue 3 — withdrawn.** The citation at `src/trading/scrumming_bot.py:2276` pointing to `:1138` is accurate. `:1138-1144` states the principle being cited. This is not a hallucinated citation.
5. **C22, evidence — withdrawn.** `src/gui/simulator_tab/nuclear_controller.py:383` assigns `scout._bus = self._sim_bus`, so the scout does hold the subscribed bus. The verdict's conclusion survives only because v1 has no production caller.
6. **C22, issue 4 — fabricated comparator.** `grep -n "Release-ready" CHANGELOG.md` returns exactly `:81`, `:1109`, `:2833`. None sits in the C20 or C23 entries. The contrast that gave the finding its force does not exist.
7. **C26, evidence — incomplete enumeration.** `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1632` is a fourth `_status_lbl` write after `:1202`. HOLDS survives because `:1632` is also an abort path. Separately, the docstring at `:823` calling `_status_error` "the single funnel for every operator-visible failure" is false — four abort paths bypass it and never log at WARNING.
8. **C35, anchors — drifted.** `DISMISS_SETTINGS_KEY` is at `:48`, not `:45`. `_persist_dismissed` is at `:497` with its swallow at `:505-508`, not `:479-488`. Substance confirmed by execution.
9. **C29, issue 6 — overstated.** 24x / 0.10 ms per tick → measured **16x / 0.073 ms**.

**Taken on trust.** The roster reconciliation in section 2 is reported as delivered; I re-derived the C23 and C16 anchors it cites but did not re-walk all 70 methodology positions. The claim that no halt note exists rests on the reconciliation pass's search terms, not on a fresh search.

**Not touched, by instruction.** `~/.acervator` and `~/.acervator_logs` were not read. The live blast radius of the C01 extractor defect is therefore stated as "every extractor bot whose state import fails", not as a bot count.