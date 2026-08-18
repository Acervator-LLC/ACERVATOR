# Fold-tranche lifecycle — end-to-end audit and repair plan

**Produced** 2026-08-06 · 16 agents · 89 findings · 39 confirmed growth-blockers
**Method** seven lifecycle segments mapped from source, each adversarially
re-verified, then traced end to end against the live fleet state and the
diagnostics log. No project code was executed and no project classes were
constructed; state and logs were opened read-only.

**Companions**
- `2026-08-06_measurement_tranche_compounding_fleet.md` — $26.20 growth from 10,197 fills
- `2026-08-06_analysis_why_folds_do_not_fire.md` — the gate-stack measurement

---

# PART 1 — END-TO-END TRACE

Verification complete. Every load-bearing line re-read from source; live figures re-derived read-only from `bot_state.json` (35 bots, saved 2026-08-06 18:03:42) and `~/.acervator_logs/trade/diagnostics.log`.

---

# END-TO-END TRACE: SCRUM → target balance does not move

**Verification basis.** All line numbers below are from the working-tree file `C:\Users\brown\OneDrive\Desktop\ACERTAVOR PRODUCT DOCUMENTATION\acervator_session25_CLOSE_hop5_v3_15_27\src\trading\scrumming_bot.py` (11,085 lines, 602,017 bytes, mtime 2026-08-06 17:27), which I re-read directly. I executed no project code and constructed no project classes; the two scripts I ran open `bot_state.json` with mode `"r"` and never write.

**Caveat that constrains every runtime claim below — this is new and the segment map did not have it.** The running process is executing **older code than the source file on disk**. All 7,957 `HOLD FOLD` lines in the live window carry the pre-v3.24.43 wording (`"TA=BEARISH — waiting for BEARISH"`), including lines written at `2026-08-07T01:06:46Z` — after the source file's mtime of `2026-08-07T00:27Z`. Zero lines carry the post-fix wording emitted by :8520-8522. So the log corroborates the *shape* of the failure and the *state file* it produced, but it cannot validate specific current-source line numbers. Static claims are anchored to source; runtime claims are labelled.

---

## The chain

### Step 1 — SCRUM sell fires
`:7161` `sell_fill = await self._execute_sell(...)`; on success `:7182 scrum_usd = scrum_asset * sell_fill`.
**FINE.** Units leave, cash arrives.

### Step 2 — Growth-cap counter is reset
`:7190-7192` `if self._fold_cycle_cap_consumed > 1e-9: ... self._fold_cycle_cap_consumed = 0.0`.
**FINE.** A fresh cycle budget is granted.

### Step 3 — Smart Wire exports principal off the top
`:7211-7219` `_scrum_routed_total = self._route_scrum_proceeds_via_wires(...)` then `scrum_usd = scrum_usd - _scrum_routed_total`.
**LOSSY, and it is principal, not profit.** The tranche built next carries the *full* units sold but only the *reduced* cash. Live fingerprint confirms this exactly: `usd / (units × ref)` is a per-bot constant of **0.800 on 16 bots** (two 10% outbound wires), **0.900 on 4** (one wire), **1.000 on 6** (none). The source bot can only ever rebuy ~80% of the units it sold. Chain continues.

### Step 4 — Tranches spawn, one per lot, sized with no reference to the cap
`:7234-7248`: `for _lot in list(self._main_lots):` / `_t_usd = (_take / scrum_asset) * scrum_usd` / `"usd": _t_usd, "units": _take, "ref": sell_fill` / `self._fold_tranches.append(_new_tr)`.
**BROKEN — THIS IS THE FIRST LINK THAT BREAKS.** Tranche size is set purely by lot size and sell price. Nothing here consults `_cycle_cap_usd`. But the only autonomous consumer (Step 9) admits a tranche only if its *whole* `usd` fits inside the per-cycle growth budget. Producer and consumer disagree on the contract, so tranches are routinely **born un-foldable**. Live: **129 of 948 open tranches carry `usd` greater than their own bot's entire cycle cap, holding $343.48 of $480.36 total queued tranche capital — 71.5%.** On three bots the *smallest* tranche exceeds the full cap, so their autonomous fold queue is frozen solid regardless of price: AGLD/USD ($1.2681 vs $0.50 cap), ADA/USDC ($1.2502 vs $0.25), AERO/USDC ($1.4223 vs $0.25).

### Step 5 — Pending wire credits absorb (narrow window)
`:7264-7267` gated on `_tranche_count_before == 0`; body at `:2246-2252` dumps the **entire** parked pool into **one** tranche's `usd` with no split and no cap reference.
**BROKEN.** The park condition (`:1916` "no tranches at wire arrival") and the absorb condition ("no tranches at the next scrum") are different instants. Live: ETH/USD and ORCA/USD have tranches, so their window is permanently shut ($215.10 behind it). BTC/USD ($342.26, 0 tranches) and XLM/USDC ($9.45, 0 tranches) still have it open — and firing it would mint a single ~$342 tranche against a $2.50 cap, 137× over, instantly un-foldable by Step 9. The one repair path is a trap.

### Step 6 — Wire income arrives at a bot that has tranches
`:1916-1926` `share = u / len(self._fold_tranches)` / `t["usd"] = float(t.get("usd", 0) or 0) + share`. `units` and `ref` are never touched.
**BROKEN.** Inflating `usd` alone pushes tranches across the Step 9 cap. Live proof, ETH/USD (cap $2.00): its ten largest tranches carry `usd` of $10.54 … $7.54 against `units × ref` of only $5.91 … $0.24 — inflation ratios **1.78× to 32.76×**, with a per-bot maximum of **226.6×**. All 27 tranches carry `wire_credits`; all 27 exceed the cap; $140.80 stranded. Every bot with no inbound wires shows a razor-flat ratio (0.800/0.900/1.000), which isolates wire credit as the sole cause of the dispersion.

### Step 7 — Dip arrives; outer TA gate
`:6398` `is_bearish = (eff_direction in (BEARISH, NEUTRAL) and eff_confidence >= _TA_CONFIDENCE_FLOOR)`, floor = 0.25 at `:96`.
**Working as designed, but dominant in practice.** Runtime, 93-min window: 7,957 `HOLD FOLD` lines, of which **4,537 report `TA=BEARISH` while still refusing** — direction was bearish and the 0.25 confidence floor blocked it. The fold block is usually never entered.

### Step 8 — Price eligibility filter
`:7943-7947` `_otd_factor = 1.0 - (_otd_pct_for_gate / 100.0)` / `_eligible = [t for t in self._fold_tranches if ticker.last <= float(t.get("ref", 0)) * _otd_factor]`.
**FINE as code.** Runtime: of 57 `FOLD_DIAG_GATE_PASSED` events in the window, the best any bot managed was **"1 of 38 tranches strict-eligible"** (ONDO/USD); the other bot logged **"0 of 17"**.

### Step 9 — Per-cycle cap filter: capital measured against a growth budget
`:7979-7980` `_cycle_cap_usd = (self._anchor_target_balance * _max_growth_pct / 100.0)`; `:7990-7992` `_cap_remaining_for_queue = max(0.0, _cycle_cap_usd - self._fold_cycle_cap_consumed)`; `:7999-8003` `_t_usd = float(_t.get('usd', 0) or 0)` / `if _running_usd + _t_usd <= _cap_remaining_for_queue:` / `_elig_capped.append(_t)`; `:8030` `_eligible = _elig_capped`.
**BROKEN — semantic unit mismatch.** The minuend is a *growth* budget; the quantity tested against it is *deployed capital*; and the subtrahend `_fold_cycle_cap_consumed` accrues in *growth* dollars (`:1430`). Consequences: (a) a tranche larger than the full cap is skipped on every cycle forever — `:8004-8007` explicitly refuses partial splits; (b) deployable capital per cycle is ~1% of anchor, and since surplus is only the OTD fraction of that (~5%), realised growth per cycle is ~0.05% of anchor against a configured 1% cap — a **~20:1 gap**; (c) when the cap is exhausted, `_cap_remaining_for_queue` is 0, `_eligible` empties, and the autonomous fold cannot fire at all.

### Step 10 — Exchange minimum trade size, applied to the already-capped subtotal
`:8057` `_fusd = sum(t["usd"] for t in _eligible)`; `:8062` `buy_cost = _fusd * _taper`; `:8085-8090` → `_fold_skipped_below_min = True`; `:8131-8132` `buy_fill = None`; `:8154` → `:8166 return`.
**BROKEN, and it composes lethally with Step 9.** Step 9 caps the admitted set at `_cap_remaining_for_queue`; Step 10 then requires that same sum to be at least `min_cost`. Where `cycle_cap < min_cost` **no admissible set exists at any price**. Confirmed for ONDO/USD from two independent live sources: cap = $75.00 × 1% = **$0.75** (state file) versus **`min_cost $1.00`** quoted verbatim in the live log. Runtime: `FOLD HELD (below min trade size): 1 eligible tranche(s) totaling $0.6932 ... below ONDO/USD min_cost $1.00` — while ONDO's full queue is $10.58 across 38 tranches, ten times min_cost. **20 of 35 bots have a cycle cap below $1.00.**

Also at this step: the early `return` at `:8166` exits the whole `tick()` (next `def` is `:8787`), skipping the DIST block and `self._last_price = ticker.last` at `:8780`. The codebase already fixed this hazard for the sibling DIST path — `:8709-8716` "Use if/else so post-block updates (self._last_price = ticker.last) stay reachable" — and left it unfixed here.

### Step 11 — The buy executes
`:8134` `buy_fill = await self._execute_buy(buy_cost, ticker.last, summary, trace_context={"path": "fold_rebuy", ...})`.
**FINE.** This is "the tranche fills." The operator sees it.

### Step 12 — Tranches are dequeued BEFORE growth is attempted
`:8188-8194` appends rebought units to `_main_lots`; `:8203` `self._fold_tranches = [t for t in self._fold_tranches if t not in _eligible]`; `:8210` `self._tranches_closed_lifetime += _removed`.
**BROKEN — ordering defect.** Every irreversible mutation completes here. The growth call is 92 lines later. If growth returns 0.0, the tranche is already gone, real money has already bought real units, and there is no retry path.

### Step 13 — Surplus computed
`:8170-8181` `buy_asset = buy_cost / buy_fill` / `asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)` / `extra_asset = buy_asset - asset_at_scrum` / `accum_profit = extra_asset * buy_fill`.
**FINE in the cash frame** (gross of fees; no fee term appears anywhere in the fold block, and 24 of 35 bots run `trading_fee_pct` 1.6).

### Step 14 — Growth applied, bounded by the same conflated counter
`:8295-8296` `_growth_applied = self._apply_fold_target_growth(accum_profit, source="auto")` → `:1407-1411` `_cycle_cap_growth = self._anchor_target_balance * (_cap_pct / 100.0)` / `_cap_remaining = max(0.0, _cycle_cap_growth - self._fold_cycle_cap_consumed)` → `:1428-1430` `_growth_applied = min(_new_surplus_usd, _cap_remaining)` / `self._target_balance = float(self._target_balance) + _growth_applied` / `self._fold_cycle_cap_consumed += _growth_applied`.
**THIS LINK WORKS.** `:1429` genuinely raises the internal target. Live: 26 of 35 bots have `target_balance > anchor_target_balance`.

### Step 15 — Anything above the cap is confiscated
`:1413` `self._standing_surplus_usd += _new_surplus_usd` (cap-exhausted branch) and `:1435` `self._standing_surplus_usd += _leftover`.
**BROKEN — one-way sink.** Exhaustive grep across all of `src/`: initialisation at `:498`, two `+=` at `:1413`/`:1435`, log/telemetry reads at `:1418`/`:1424`/`:1450`/`:8279`, persistence at `:3415`/`:3568-3574`, and a comment at `bot_container.py:826`. **There is no `-=`, no lowering assignment, and the symbol appears in neither operand of `:1428`.** Meanwhile the class docstring at `:488-494` specifies the drain explicitly — `this_cycle_growth = min(this_cycle_surplus + standing_surplus, per_cycle_growth_budget)` — and `bot_container.py:825-830` plus `:3410-3413` repeat the claim. Three comment sites describe a drain that was never written.

### Step 16 — The cap latches for the rest of the dip
`:1432` `self._target_grow_last_side = "lower"`. Resets exist only at `:7192` (SCRUM fires — needs price back at target) and `:6068-6071` (requires `bb_pos >= 0.75`, the **upper** band). A dip is neither. The counter is persisted (`:3422`) and restored (`:3577-3583`), so restarting does not clear it.
**BROKEN.** Live: CAP/USD sits at `fold_cycle_cap_consumed = 0.5000` = exactly 100% of its $0.50 cap, with `standing_surplus_usd = $0.4703`, `target_grow_last_side = "lower"`, and 12 tranches still open. It is latched right now.

### Step 17 — The budget itself never compounds
Both cap sites use `_anchor_target_balance` (`:1407`, `:7979`). Grep shows the anchor is written only at `:1289`, `:1296` (operator edit), `:1874` (Wire Stack), `:3522` (restore) — **never by fold growth**.
**BROKEN.** Maximum growth per cycle is a constant dollar figure for the life of the bot. Even with everything else fixed, the target would rise linearly, never geometrically.

### Step 18 — The operator looks at the screen
`:1429` writes `self._target_balance`. It does **not** write `self.config.target_balance` — grep shows only two writers of that field, `:1301` (operator input) and `:1877` (Wire Stack), with `:1297-1299` stating the intent outright: *"config.target_balance always reflects the operator's INPUT value (anchor)."*
**BROKEN — and this is what the operator is actually reporting.** I grepped every `_target_balance` reference in `src/gui/` and found **zero live-dashboard readers of the grown value**: `bot_live_settings.py:2198 self._target_bal.setValue(cfg.target_balance)` shows the anchor; `main_window.py:1187-1188` reads `getattr(bot, "_anchor_target_balance", getattr(bot, "_target_balance", 0))` — anchor wins on all 35 bots; `nuclear_controller.py:199` is the simulator, not live. **Correction to the segment map:** its "growth" segment claimed the grown target surfaces at `bot_live_settings.py:3232` — I read that site, and it is the **phantom-bot table** (`for row, ph in enumerate(phantoms): st = ph.get_status()`), not the compounding snapshot. The grown value reaches only `_compounding_snapshot()` at `:4650-4671`, which feeds `gate.log` (`:4582`) — a log file, not a GUI surface. Live: `config.target_balance == anchor_target_balance` on **all 35 bots, zero exceptions.**

---

## Branch: the operator's actual dip workflow

Steps 8-17 describe the autonomous path. When the operator catches a dagger by hand, control goes elsewhere entirely:

**`manual_fire_tranche` (`:2031-2177`) — buys at `:2084`, appends units to `_main_lots` at `:2100-2104`, removes the tranche at `:2114`, bumps `_tranches_closed_lifetime` at `:2130-2131`, returns at `:2172`.** I read the method in full. It **never computes a surplus quantity at all** — there is no `accum_profit`, no `extra_asset`, no growth call. Repo-wide grep confirms `_apply_fold_target_growth` has exactly one definition (`:1344`) and exactly two call sites: `:8295` (autonomous) and `:9430` (whole-bot MANUAL_FOLD / CARTRIDGE_FOLD / WIRE_STACK_FOLD). The per-tranche variant was left out of that rollout.

**BROKEN, totally and silently.** No `[COMPOUND SKIPPED]` line appears, because that diagnostic lives inside the helper that is never entered. This matters because ETH/USD's tranches are **27 of 27 `operator_initiated`**, and ORCA/USD's are 56 of 107.

---

## The first link that breaks

**Step 4, `:7240-7248` — spawn sizes a tranche with no reference to the per-cycle cap, while the only autonomous consumer at `:8001` requires the whole tranche to fit inside that cap.** This is the earliest point where the operator's money leaves the intended path: it is where a tranche is created that the system can never fold. 129 of 948 live tranches ($343.48, 71.5% of all queued tranche capital) are in that state.

Two qualifications, stated plainly:

- **On the operator's actual dip workflow the break is earlier in experience and more total in kind.** Per-tranche Manual Fire (`:2031-2177`) has no growth code whatsoever, so on that path the fill→growth link does not exist to be broken.
- **The reason the operator sees a *frozen number* rather than a *small number* is Step 18**, which is independent of all the arithmetic above. Even on CAP/USD, whose internal target has grown $5.41 (10.8% above anchor), every live GUI surface renders $50.00.

**Classification summary.** Fine: 1, 2, 7, 8, 11, 13, 14. Lossy (chain continues, value stranded): 3, 5, 6, 15. Broken (chain stops): 4, 9, 10, 12, 16, 17, 18, and the Manual Fire branch.

---

## Direct answers

### 1. When multiple tranches fill during a dip, what SHOULD happen vs what ACTUALLY happens

**Should** (per `:488-494`): each fill's surplus is added to any standing surplus, the sum is drained into `_target_balance` at up to `anchor × max_target_growth_pct/100` per cycle, and the remainder carries forward to drain on subsequent cycles — `this_cycle_growth = min(this_cycle_surplus + standing_surplus, per_cycle_growth_budget)`.

**Actually**, depending on how the tranche filled:

- *Filled by per-tranche Manual Fire* (`:2084`-`:2177`): target growth is exactly **$0.00**. No surplus is computed; `_apply_fold_target_growth` is never called. Silent — not even a `[COMPOUND SKIPPED]` line.
- *Filled autonomously*: `:8203` dequeues the tranches first, then `:8295` calls the helper, and `:1429` does raise `_target_balance` — but by `min(surplus, cap_remaining)` where the deployable capital was already clamped to ~1% of anchor at `:8001`, so realised growth is ~0.05% of anchor per cycle against a configured 1%.
- *Either way*, `:1428` ignores `_standing_surplus_usd` entirely — the documented `+ standing_surplus` term is absent from the code — so any prior overflow never drains (`:1413`, `:1435`, no decrement anywhere).
- *And in every case*, `config.target_balance` is untouched, so the displayed number cannot move (`:1297-1299`, `bot_live_settings.py:2198`).

**Quantified fleetwide, from live state:** total accrued growth across all 35 bots is **$26.1996** against **10,197 lifetime closed tranches** — $0.0026 per closed tranche. The sum of a *single* cycle's authorised budget across those same 35 bots is **$33.00**. The entire lifetime compounding of the whole fleet is **0.79× what one cycle is authorised to produce.**

### 2. Is there any code path by which a tranche fill raises the target balance?

**Yes — exactly one, and it does fire.** `:8295-8296` → `:1429` `self._target_balance = float(self._target_balance) + _growth_applied`. Live proof: 26 of 35 bots carry a `target_balance` strictly above their anchor, at non-round fractional values (CAP/USD 55.4148 vs 50.00; BILL/USD 253.0969 vs 250.00; GROVE/USD 102.6133 vs 100.00; BTC/USD 250.0919 vs 250.00) that only `:1429` can produce — the operator-edit path writes `nt` or `nt + accrued` (`:1290`/`:1295`) and detonation writes the anchor exactly (`:9721`). The grown value is functionally live, not cosmetic: `:3226` and `:990` read it for trading decisions.

**So the honest answer is not "it never fires" — it is "it fires, feebly, and invisibly."** Why it does not *appear* to fire:

1. **It is invisible.** No live GUI surface reads `_target_balance` (Step 18). This alone fully explains the operator's literal words.
2. **It is throttled ~20:1** by the capital-vs-growth cap conflation (Step 9).
3. **It is bypassed entirely** on the per-tranche Manual Fire path the operator uses most during dips.
4. **It is often unreachable** because the fold never executes: 57 gate-passes and zero fills in a 93-minute live window; the cap/min_cost deadlock is arithmetically permanent on ONDO ($0.75 cap vs $1.00 min_cost) and 20 of 35 bots have a cap below $1.00.

### 3. Is the max-target-growth cap reachable?

**Yes. It is reachable, it has been reached, and the cutoff gate has fired.** This refutes the segment map's headline claim that the gate is arithmetically unreachable.

Live: **CAP/USD f9cfb7ba** carries `fold_cycle_cap_consumed = 0.5000` against `anchor_target_balance = 50.0` and `max_target_growth_pct = 1.0` — a $0.50 cap consumed **to the cent** — alongside `standing_surplus_usd = $0.4703`. That pairing can only be produced by the `min()` clamp at `:1428` plus the `:1411-1427` held branch or the `:1433-1435` leftover accrual.

But reachability is rare and its consequence is destructive:
- **1 of 35** bots has fully consumed its cap; 2 more are partial (BTC/USD $0.0919, SUI/USD $0.3389); **32 of 35 sit at $0.0000.**
- What the gate catches is **confiscated**, not deferred (Step 15).
- CAP/USD is now **latched**: `_cap_remaining_for_queue` at `:7990-7992` evaluates to $0.00, so `:8001` admits nothing, `_eligible` is empty, and its autonomous fold cannot fire *at all* until a SCRUM or a `bb_pos >= 0.75` touch. Restart does not clear it (`:3577-3583`).
- Runtime confirms the rarity: **zero** `TARGET-GROW HELD` and **zero** `TARGET GROWN` lines in the 93-minute window.

### 4. Operator money currently stranded

From `~/.acervator/bot_state.json`, read-only, 35 bots, saved 2026-08-06 18:03:42.

**Parked cash buckets — $567.90 total**

| Bot | Pending wire credits | Standing surplus | Open tranches | Absorb window |
|---|---:|---:|---:|---|
| BTC/USD `7c39c7a2` | $342.2567 | — | 0 | **OPEN** (will mint a 137× over-cap tranche) |
| ETH/USD `7c4c4ff3` | $213.9008 | — | 27 | **CLOSED permanently** |
| XLM/USDC `5d335c96` | $9.4482 | — | 0 | **OPEN** (19× over-cap) |
| ORCA/USD `695f39e1` | $1.1988 | — | 107 | **CLOSED permanently** |
| BIO/USD `7c30a150` | — | $0.6289 | 126 | n/a |
| CAP/USD `f9cfb7ba` | — | $0.4703 | 12 | n/a |
| **TOTAL** | **$566.8045** | **$1.0992** | | |

Of the pending total, **$215.0996** (ETH + ORCA) sits behind a permanently closed absorb window — the only call site is `:7264-7267`, gated on `_tranche_count_before == 0`, and both bots have tranches. The remaining $351.70 is behind an open window whose absorb (`:2246-2252`) would dump the whole pool into a single tranche and re-strand it under Step 9.

**Structurally un-foldable tranche capital — $343.48**

129 of 948 open tranches carry `usd` exceeding their own bot's full cycle cap, holding **$343.48 of $480.36** total queued tranche capital (71.5%). Worst: ORCA/USD 32/107 ($73.50, cap $0.50); BIO/USD 16/126 ($27.92, cap $1.00); ALLO/USDC 5/9 ($20.05); PUMP/USD 7/9 ($17.95); ETH/USD 22/27 ($140.80, cap $2.00); CAP/USD 10/12 ($14.42); XRP/USD 6/10 ($8.02); ADA/USDC 5/5 ($7.12); RAVE/USD 5/10 ($6.67); AGLD/USD 3/3 ($5.13). Three bots (AGLD, ADA, AERO) have *every* tranche over cap.

**Also lost, not a cash bucket:** `pending_wire_ledger` is not persisted anywhere — I enumerated the union of all `scrumming_state` keys across all 35 records and it is absent. The $566.80 of parked money has **no surviving provenance**; `_add_wire_credits` guards with `if entries:`, so a post-restart absorb creates no `wire_credits` key at all.

**Do not double-count:** $567.90 is cash sitting in buckets with no outlet. $343.48 is capital inside tranches that cannot be folded. They are disjoint. Combined exposure: **$911.38**.

---

## What I could NOT establish

1. **The running build does not match the source on disk.** Every `HOLD FOLD` line in the live window uses pre-v3.24.43 wording, including after the file's mtime. I could not determine how far the running build lags, so **no runtime observation here validates a current-source line number**. This is the most important limitation on everything above and it was not in the segment map.
2. **Exchange `min_cost` per pair.** Only ONDO/USD ($1.00) is established, quoted from the live log. The rest come from `_get_market_limits` at runtime. I confirmed 20 of 35 bots have a cap below $1.00 and that the deadlock mechanism is real for at least one — I could not compute how many are actually deadlocked.
3. **Attribution of CAP/USD's exact-cap consumption** to the autonomous path (`:8295`) versus the uncapped whole-bot manual path (`:9430`). Zero `TARGET GROWN` lines survive in the retained window; rotated `gate.log.1-.5` are from June and I did not search them.
4. **Whether per-tranche Manual Fire is the dominant discharge path.** `MANUAL TRANCHE FIRE COMPLETE` appears **0 times** in the retained window. The inference rests on `operator_initiated: True` on 27/27 ETH and 56/107 ORCA tranches plus the operator's own account — not on observed fire events.
5. **Whether the 9 bots at `target == anchor` exactly** (ZEC, HYPE, RAVE, NEAR, XLM, ADA, LTC, LSETH, WLFI) got there via the Manual-Fire zero-growth defect or via the `set_target_balance_live` collapse branch at `:1291-1296`. Both are reachable; nothing in the state file distinguishes them. Note LTC/LSETH/WLFI have 0 created and 0 closed — they have simply never traded.
6. **Whether BIO/USD's target of exactly $102.0000** against a $100 anchor is two clean cap-limited cycles or a separate writer I have not found. Two `min(surplus, cap)` draws landing on a round number to the cent is possible but not obviously the product of that formula.
7. **Fee impact on booked surplus.** `accum_profit` (`:8181`) has no fee term, and 24 of 35 bots run `trading_fee_pct` 1.6 (11 at 0.6) against a 5.0% gross OTD spread. Every `TARGET GROWN` figure therefore overstates real compounding, but I did not verify whether fees are deducted upstream inside `_execute_buy`.
8. **Latent-but-not-firing paths I confirmed as code and confirmed as inert:** Stack Mode severing SCRUM from tranche spawn (`:10041-10054`), the uncapped Wire-Stack target bump (`:1871-1879`), and the fold-rate taper booking zero growth while dequeuing everything (`:8062` vs `:8171`, `:8203`). Live state shows `stack_mode: false` and `position_ceiling_enabled: false` on all 35 bots, and `quote_to_usd = 1.0` everywhere, so none of these is today's cause. They arm the instant those toggles flip.

---

# PART 2 — REPAIR PLAN

## What the chain is supposed to do

The operator's own model, expanded into the chain the code is meant to implement:

1. **SCRUM.** Price reaches target; the bot sells units. `_execute_sell` returns a fill; `scrum_usd = scrum_asset * sell_fill` (`scrumming_bot.py:7182`).
2. **Fold tranches spawn.** The retained proceeds become one or more standing tranches, each carrying `usd` (cash held to rebuy with), `units` (what was sold), `ref` (the sell price) and `initial_buy_price` (MEM-171 provenance). `:7241-7248`.
3. **Smart Wire routes and splits.** Income arriving from other bots is split across the standing tranches, or parked in a bucket to wait for the next tranche to be spawned. `apply_wire_income` `:1916-1953`.
4. **Tranches fill.** Price falls below `ref` by at least the OTD spread; the bot rebuys with the tranche's `usd`, acquiring more units than it sold. `:8134`, `:8170-8181`.
5. **Target balance grows.** The extra units are the surplus; it is added to the target balance so the bot's next cycle trades against a larger base. `:1429`.
6. **Growth is capped per buy cycle.** `max_target_growth_pct` limits how much of that surplus may be applied this cycle. `:1406-1411`.
7. **Surplus beyond the cap is handled by a cutoff gate.** It accrues to a standing pool and drains into the target on subsequent cycles at the same per-cycle rate. Specified verbatim at `:488-494`:
   ```
   this_cycle_growth = min(this_cycle_surplus + standing_surplus,
                           per_cycle_growth_budget)
   standing_surplus = (this_cycle_surplus + standing_surplus)
                      - this_cycle_growth
   ```

---

## Where it actually breaks

Ordered first-break-first along the chain. Every line below was re-read from the working-tree file (`src/trading/scrumming_bot.py`, 11,085 lines, mtime 2026-08-06 17:27).

### Break 1 — Spawn sizes a tranche with no reference to the budget that will later admit it — CONFIRMED

`scrumming_bot.py:7240`
```python
_t_usd = (_take / scrum_asset) * scrum_usd
```

Tranche size is set purely by lot size and sell price. Nothing at any of the three spawn sites (`:7241-7248`, `:8761-8767`, `:9147-9155`) consults `_cycle_cap_usd`. The only autonomous consumer requires the *whole* tranche to fit inside the per-cycle budget. Producer and consumer disagree on the contract, so tranches are routinely **born un-foldable**.

**Operator-visible:** 129 of 948 open tranches carry `usd` larger than their own bot's entire cycle cap, holding **$343.48 of $480.36** queued tranche capital — 71.5%. On AGLD/USD, ADA/USDC and AERO/USDC every single tranche is over cap, so those queues are frozen at any price. These tranches count in every `len(self._fold_tranches)` log and in the Fold Tranches tab, and are silently dropped on every cycle in which they become price-eligible.

### Break 2 — Wire income inflates `usd` without touching `units`, pushing credited tranches over the cap — CONFIRMED

`scrumming_bot.py:1920`
```python
t["usd"] = float(t.get("usd", 0) or 0) + share
```

`units` and `ref` are never assigned in that block. `usd` is the exact field the cap filter tests at `:8001`.

**Operator-visible:** the routing mechanism designed to feed standing tranches is what disqualifies them. ETH/USD `7c4c4ff3` (cap $2.00): all 27 tranches carry `wire_credits`, all 27 exceed the cap, $140.80 stranded; its ten largest carry `usd` of $10.54…$7.54 against `units × ref` of $5.91…$0.24. Every bot with no inbound wires shows a razor-flat `usd/(units × ref)` constant (0.800 / 0.900 / 1.000, tracking outbound wire count), which isolates wire credit as the sole cause of ETH's dispersion.

### Break 3 — The park/absorb window is a different condition than the park condition, and the absorb dumps the whole pool into one tranche — CONFIRMED

Park at `:1942` when the bot has no tranches. Absorb has exactly one call site, `:7264-7267`:
```python
if (_first_new_tranche is not None
        and _tranche_count_before == 0
        and self._pending_wire_credits > 0):
    self._absorb_pending_wire_credits_into(_first_new_tranche)
```
and the body at `:2249` is
```python
new_tranche["usd"] = float(new_tranche.get("usd", 0) or 0) + pending
```

No split, no cap reference. The docstring at `:2238` names `_execute_sell` as the caller; grep shows the sole call site is the SCRUM block in the tick loop.

**Operator-visible:** $566.80 parked fleet-wide. $215.10 of it (ETH $213.90 with 27 tranches, ORCA $1.20 with 107) sits behind a permanently closed window. The other $351.70 (BTC $342.26, XLM $9.45) sits behind an *open* window that, when it fires, mints a single ~$342 tranche against a $2.50 cap — 137× over — instantly un-foldable by Break 5. The one repair path for parked money is a trap. `_pending_wire_ledger` is never persisted, so the provenance is already gone.

### Break 4 — Per-tranche Manual Fire fills a tranche and applies zero target growth — CONFIRMED

`manual_fire_tranche` (`:2031-2177`) buys at `:2084`, returns units at `:2100-2104`, removes the tranche at `:2114`, bumps `_tranches_closed_lifetime` at `:2130-2131`, returns at `:2172`. It **never computes a surplus quantity at all** — no `accum_profit`, no `extra_asset`, no growth call. Grep confirms `_apply_fold_target_growth` has one definition (`:1344`) and exactly two call sites: `:8295` (autonomous) and `:9430` (whole-bot MANUAL_FOLD / CARTRIDGE_FOLD / WIRE_STACK_FOLD). The per-tranche variant was left out of the 2026-07-26 Option-B rollout.

**Operator-visible:** the dip workflow — hand-firing individual tranches from the tranche list — closes tranches, grows the position, and moves the target by exactly $0.00. Silent: `[COMPOUND SKIPPED]` lives inside the helper that is never entered. ETH/USD's tranches are 27 of 27 `operator_initiated`; ORCA's are 56 of 107.

### Break 5 — The cap filter measures deployed CAPITAL against a GROWTH budget — CONFIRMED

`scrumming_bot.py:7979-7992` then `:7999-8003`
```python
_cycle_cap_usd = (self._anchor_target_balance
                   * _max_growth_pct / 100.0)
...
_cap_remaining_for_queue = max(
    0.0,
    _cycle_cap_usd - self._fold_cycle_cap_consumed)
...
for _t in _elig_sorted:
    _t_usd = float(_t.get('usd', 0) or 0)
    if _running_usd + _t_usd <= _cap_remaining_for_queue:
```
and the subtrahend accrues in growth dollars at `:1430`
```python
self._fold_cycle_cap_consumed += _growth_applied
```

Three consequences. (a) A tranche larger than the full cap is skipped forever — `:8004-8007` explicitly refuses partial splits. (b) Deployable capital per cycle is ~1% of anchor and surplus is only the OTD fraction of that (~5%), so realised growth is ~0.05% of anchor against a configured 1% — a **~20:1 gap**. (c) When consumed reaches the cap, `_cap_remaining_for_queue` is 0, `_eligible` empties at `:8030`, and the autonomous fold cannot fire at all.

**Operator-visible:** CAP/USD `f9cfb7ba` sits at `fold_cycle_cap_consumed = 0.5000` against a $0.50 cap — admission-frozen right now, and the counter is persisted at `:3422` / restored at `:3577-3583`, so restarting does not clear it.

### Break 6 — The cap and the exchange minimum compose into an arithmetic deadlock — CONFIRMED (mechanism), HYPOTHESIS (fleet count)

Break 5 caps the admitted set at `_cap_remaining_for_queue`; `:8085-8090` then requires that same sum to reach `min_cost`:
```python
_below_min_cost_fc = (
    _min_cost_fc > 0
    and _fold_notional_usd < _min_cost_fc)
```
Where `cycle_cap < min_cost`, **no admissible set exists at any price, for any queue depth.**

CONFIRMED for ONDO/USD `d9681a57` from two independent sources: cap = $75.00 × 1% = **$0.75** (state file) versus **`min_cost $1.00`** quoted verbatim in the live log, against a full queue of $10.58 across 38 tranches. **21 of 35 bots have a cycle cap below $1.00.** HYPOTHESIS for the other 20 — `min_cost` comes from `_get_market_limits` at runtime and is not in source.

Also here: the operator-facing text at `:8103-8105` says *"tranches stay queued until more accumulate or price moves enough"* — a remedy that cannot work, because more accumulation cannot raise the admitted subtotal above the cap. And the bare `return` at `:8166` exits the whole `tick()` (next `def` is `:8787`), skipping the DIST block and `self._last_price = ticker.last` at `:8780`. The codebase already fixed exactly this hazard on the sibling DIST path — `:8715-8716` *"Use if/else so post-block updates (self._last_price = ticker.last) stay reachable"* — and left it unfixed here.

### Break 7 — Tranches are dequeued before growth is attempted — CONFIRMED

`:8188-8194` appends rebought units to `_main_lots`; `:8203` `self._fold_tranches = [t for t in self._fold_tranches if t not in _eligible]`; `:8210` bumps the closed counter. The growth call is 92 lines later at `:8295`. If the helper returns 0.0 (cap latched), the tranche is already gone and real money has already bought real units. There is no retry path.

### Break 8 — `_standing_surplus_usd` is a one-way sink — CONFIRMED

Exhaustive grep of `src/`: init `:498`, two increments `:1413` and `:1435`, log/telemetry reads `:1418` `:1424` `:1450` `:8279`, persistence `:3415` / `:3568-3574`, one comment in `bot_container.py:826`. **No decrement anywhere**, and the symbol appears in neither operand of the drain:
```python
_growth_applied = min(_new_surplus_usd, _cap_remaining)   # :1428
```
The documented `+ standing_surplus` term (`:488-494`) is absent. Three comment sites assert the drain exists — `:488-494`, `:3410-3413`, `bot_container.py:825-830` — which is precisely why this survived seven documented remediation attempts (`:8250-8259`).

### Break 9 — The cap latches for the duration of a dip — CONFIRMED

`:1432` sets `_target_grow_last_side = "lower"`. Resets exist only at `:7190-7192` (a SCRUM fires — needs price back at target) and `:6068-6071` (needs `bb_pos >= 0.75`, the **upper** band). A dip is neither. Persisted and restored, so a reboot does not clear it.

### Break 10 — The growth budget itself never compounds — CONFIRMED

Both cap sites use `_anchor_target_balance` (`:1407`, `:7979`), and grep shows the anchor is written only at `:1289` / `:1296` (operator edit), `:1874` (Wire Stack) and `:3522` (restore) — never by fold growth. Maximum growth per cycle is a **constant dollar figure for the life of the bot.** Even with everything else fixed, target rises linearly, never geometrically.

### Break 11 — No live GUI surface renders the grown target — CONFIRMED

`:1429` writes `self._target_balance`. It does not write `self.config.target_balance` — grep shows only two writers of that field, `:1301` and `:1877`, with `:1298-1300` stating the intent outright: *"config.target_balance always reflects the operator's INPUT value (anchor)."*

`bot_container.py:1299` exports `"target_balance": self.config.target_balance` — the anchor. `bot_live_settings.py:2198` `self._target_bal.setValue(cfg.target_balance)` — the anchor. `main_window.py:1187-1188` reads `_anchor_target_balance` first. The grown value reaches only `_compounding_snapshot()` (`:4650-4681`), which feeds `gate.log` — a log file, not a GUI surface.

Live: `config.target_balance == anchor_target_balance` on **all 35 bots, zero exceptions.** Even on CAP/USD, whose internal target has grown $5.41 (10.8% above anchor), every panel reads $50.00. **This is why the reported symptom is a frozen number rather than a small one.**

### Break 12 — The FOLD success log blames a gate that no longer executes — CONFIRMED

`scrumming_bot.py:8376-8377`, emitted on every successful fold:
```python
f"Rebought {len(_eligible)}/{len(self._fold_tranches) + len(_eligible)} tranches "
f"(others gated by MEM-171 initial_buy_price floor)"
```
`initial_buy_price` is not consulted by the eligibility filter — `:7944-7947` tests `ticker.last <= ref * _otd_factor` only, and the code's own comment at `:7926-7933` records that the IBP gate is retained but no longer consulted. The two real exclusion causes are the OTD price gate and the cycle-cap filter. **Every fold event in the log attributes non-folding tranches to a profit floor that has been dead code since v3.16.41.** This is the single most likely reason the failure survived seven remediation attempts.

### Latent — armed but not firing today

All measured inert on the live fleet (`stack_mode` False, `position_ceiling_enabled` False, `quote_to_usd` 1.0 on all 35):

- **Stack Mode severs SCRUM from tranche spawn.** `:10041-10054` returns `None` from `_execute_sell`; `:7170` reads that as failure and skips the entire `:7180-7330` success block containing the only autonomous `_fold_tranches.append`. Units sell, no tranche is created, `_main_lots` is never consumed, and the operator sees `SCRUM ABORTED: sell failed` on every successful stack open.
- **Wire Stack is the only uncapped growth path**, and it is the only one that moves the dashboard number (`:1873-1877`). It also raises the anchor, which is the denominator of every future cycle cap.
- **Fold rate taper books zero growth while dequeuing everything.** `:8062` tapers `buy_cost`; `:8171` computes `asset_at_scrum` from the full untapered `t["usd"]`; `:8203` removes every eligible tranche regardless. At taper 0.1, 90% of a tranche's capital is dequeued without being spent.

---

## Stranded money

From `~/.acervator/bot_state.json`, read-only, 35 bots, saved **2026-08-06 18:11:42**.

### Parked cash with no outlet — $567.90

| Bot | Pending wire credits | Standing surplus | Open tranches | Cycle cap | Absorb window |
|---|---:|---:|---:|---:|---|
| BTC/USD `7c39c7a2` | $342.2567 | — | 0 | $2.50 | **OPEN** — will mint a 137× over-cap tranche |
| ETH/USD `7c4c4ff3` | $213.9008 | — | 27 | $2.00 | **CLOSED permanently** |
| XLM/USDC `5d335c96` | $9.4482 | — | 0 | $0.50 | **OPEN** — 19× over-cap |
| ORCA/USD `695f39e1` | $1.1988 | — | 107 | $0.50 | **CLOSED permanently** |
| BIO/USD `7c30a150` | — | $0.6289 | 126 | $1.00 | n/a |
| CAP/USD `f9cfb7ba` | — | $0.4703 | 12 | $0.50 | n/a — cap 100% consumed |
| **TOTAL** | **$566.8045** | **$1.0992** | | | |

### Tranche capital that cannot be folded — $343.48

129 of 948 open tranches carry `usd` exceeding their own bot's full cycle cap, holding **$343.4795 of $480.3648** queued (71.5%).

| Bot | Over-cap / total | Over-cap $ | Cap | Queue $ |
|---|---:|---:|---:|---:|
| ETH/USD `7c4c4ff3` | 22 / 27 | $140.7981 | $2.00 | $145.2118 |
| ORCA/USD `695f39e1` | 32 / 107 | $73.5006 | $0.50 | $85.2136 |
| BIO/USD `7c30a150` | 16 / 126 | $27.9174 | $1.00 | $68.4165 |
| ALLO/USDC `45e9e720` | 5 / 9 | $20.0457 | $1.25 | $21.9276 |
| PUMP/USD `650df31a` | 7 / 9 | $17.9482 | $0.50 | $18.3550 |
| CAP/USD `f9cfb7ba` | 10 / 12 | $14.4152 | $0.50 | $14.5504 |
| XRP/USD `a873b457` | 6 / 10 | $8.0202 | $0.75 | $8.9018 |
| ADA/USDC `ff6a37a3` | **5 / 5** | $7.1202 | $0.25 | $7.1202 |
| RAVE/USD `a0a82b8c` | 5 / 10 | $6.6682 | $0.50 | $7.6257 |
| AGLD/USD `a632ff52` | **3 / 3** | $5.1281 | $0.50 | $5.1281 |
| RE/USD `04e1cafc` | 4 / 5 | $4.8930 | $0.50 | $5.3882 |
| HYPE/USDC `e6df7221` | 4 / 10 | $3.9732 | $0.50 | $4.8388 |
| LINK/USD `4a53be56` | 4 / 22 | $3.9013 | $0.75 | $8.5537 |
| ZEC/USD `b2ef9a74` | 2 / 42 | $3.4401 | $1.50 | $14.1595 |
| HBAR/USDC `7a4e0e88` | 1 / 2 | $2.5199 | $0.50 | $2.5273 |
| ONDO/USD `d9681a57` | 2 / 38 | $1.7677 | $0.75 | $10.5842 |
| AERO/USDC `cc18670d` | **1 / 1** | $1.4223 | $0.25 | $1.4223 |
| 18 others | 0 | $0 | | $50.9926 |

These two buckets are **disjoint**. Combined exposure: **$911.38**.

### Context for scale

Total accrued growth across the whole fleet is **$26.1996** against **10,197 lifetime closed tranches** — $0.0026 per closed tranche. The sum of a **single** cycle's authorised growth budget across those same 35 bots is **$33.00**. The entire lifetime compounding of the fleet is 0.79× what one cycle is authorised to produce.

---

## The repair, in order

**Working discipline for every step below:** edit and test on an isolated hard copy, never in the working tree. The tree at `acervator_session25_CLOSE_hop5_v3_15_27/src/` *is* live — it is what the next launch runs. Promote files only after the whole phase verifies. No `src/__init__.py.__version__`, `main.py:current_version` or CHANGELOG bump until `python tools/harness/check_release_readiness.py` returns `[OK] Release-ready`.

**Two blocking preconditions before any promotion.**

### Step 0 — Determine which build is actually running. No code change.

The running process is executing **older code than the source file on disk.** All 7,957 `HOLD FOLD` lines in the live log window carry pre-v3.24.43 wording (`"TA=BEARISH — waiting for BEARISH"`), including lines written after the source file's mtime. Zero lines carry the post-fix wording emitted by `:8520-8522`.

**Why first:** you cannot reason about the effect of a change on a process whose code you have not identified. Every runtime observation in this plan corroborates the *shape* of the failure and the *state file it produced*, but none of it validates a current-source line number.

**Blast radius:** none.

**Test:** restart the fleet from the on-disk source with `profit_folding_active` untouched, then grep `~/.acervator_logs/trade/diagnostics.log` for the post-v3.24.43 `HOLD FOLD` wording. **Positive control:** grep for the pre-fix wording in the same window and confirm it stops appearing. If both appear after restart, two processes are running.

---

## Phase 1 — Truth. Zero effect on any trading decision.

Nothing in this phase writes trading state, changes an order size, or changes when an order fires. It exists so that Phase 2 and Phase 3 are observable.

### Step 1 — Correct every comment and log string that misdirects diagnosis.

**Exact change.**
- `:8376-8377` — replace `(others gated by MEM-171 initial_buy_price floor)` with the real causes: OTD price gate and cycle-cap filter, with the counts from each.
- `:7478-7481` — header claims two eligibility gates; the code implements one. Delete the MEM-171 clause; the corrective note already sits at `:7926-7933`.
- `:8176-8180` and `:8246-8248` — both assert a strict-below-ref filter (`ticker.last < t["ref"]`) that does not exist. Replace with the actual predicate.
- `:7763-7764` — `NO_STRICT_ELIGIBLE` prints `_min_ref` as the activation price; the executor requires `ref × (1 − otd/100)`. Multiply by `_otd_factor`.
- `:2238` — docstring names `_execute_sell` as caller; the single call site is `:7267`.
- `:10038` — comment claims a non-None sentinel; the code returns `None`.
- `:10494` — comment claims manual fire bypasses `_execute_buy` via `guarded_place_order`; `manual_fire_tranche` calls `_execute_buy` at `:2084`.
- Leave `:488-494`, `:3410-3413` and `bot_container.py:825-830` alone — Step 7 makes them true.

**Why here:** these strings are the reason seven prior attempts failed. Every subsequent step is diagnosed by reading the log; fix the log first.

**Blast radius:** zero. Comment and f-string text only. No control flow touched.

**Test:** `tests/test_fold_diag_strings.py` — source-shape pins in the existing idiom of `tests/test_fold_target_growth_helper.py:29-59`: assert `"MEM-171 initial_buy_price floor"` is absent from the `FOLD: Bought` emit block and the new text is present. **Positive control:** run the same assertions against a saved copy of the pre-fix file and confirm they fail.

### Step 2 — Make the FOLD_DIAG counters use the executor's predicate.

**Exact change.** `:7686-7691` uses `ticker.last < ref AND ticker.last <= initial_buy_price`; the executor at `:7944-7947` uses `ticker.last <= ref × _otd_factor` with no IBP term. Compute `_eligible` once with the executor's predicate and have `FOLD_DIAG_BLOCKED` (`:7707`), `FOLD_DIAG_SNAPSHOT` (`:7732-7733`) and `FOLD_DIAG_NO_STRICT_ELIGIBLE` (`:7747`) read it. `FOLD_DIAG_GATE_PASSED` (`:7954`) already does.

**Prerequisite inside the step:** verify by grep that `_per_tranche_eligible` and `_patent_only_eligible` are not read by any control flow. If either is, stop and treat as a separate finding.

**Why here:** these counters are the instrument you will use to verify Phase 3. An instrument that measures a different predicate than the executor cannot confirm or refute a Phase 3 change.

**Blast radius:** zero, conditional on the grep above.

**Test:** stub with three tranches straddling `ref` and `ref × 0.95`; assert `FOLD_DIAG_SNAPSHOT`'s count equals `len(_eligible)`. **Positive control:** the same test on current code returns a different count for the tranche between `ref × 0.95` and `ref`.

### Step 3 — Surface the numbers the operator needs.

**Exact change.**
- `bot_container.py:1278-1300` already exports `anchor_target_balance` at `:1287` alongside `target_balance` at `:1299`. Add `"live_target_balance": float(self._target_balance)` and `"standing_surplus_usd"`, `"fold_cycle_cap_consumed"`, `"cycle_growth_budget_usd"`, and a computed `"tranches_over_cycle_cap"` / `"tranches_over_cycle_cap_usd"`. `_compounding_snapshot()` (`:4650-4681`) already assembles most of this for `gate.log`; reuse it.
- `bot_live_settings.py` — add read-only rows next to the Target Balance spinbox: `Live target: $X (anchor $Y, accrued +$Z)`, `Standing surplus: $S`, `Cycle cap: $C consumed $K`, `Over-cap tranches: N ($M)`.
- Fix `bot_container.py:829-830`, which claims `standing_surplus_usd` is *"Surfaced for visibility (Status tab + diagnostics)"* — grep of `src/gui/` for `standing_surplus` returns zero matches.

**Hazard that must be honoured — this is a live-money trap.** Do **not** repoint the `_target_bal` spinbox at `:2198` to the grown value. The change-detector at `bot_live_settings.py:499-505` diffs against `cfg.target_balance`; if the spinbox holds a different number, every panel open registers as an edit and can fire `set_target_balance_live`, which at `:1291-1296` collapses the anchor and wipes accrued growth. The spinbox is the operator's *input* field and must keep showing the anchor. The grown value goes in a new read-only row.

**Why here:** Steps 7, 8 and 9 move the target balance. Without this, the operator has no way to see whether they worked, and the plan repeats the failure mode it is fixing.

**Blast radius:** zero — read-only additions to a status dict and read-only GUI rows.

**Test:** two assertions. (a) `_target_bal.value() == cfg.target_balance` after panel construction on a stub with `target != anchor` — pins that the spinbox was not repointed. (b) the new live-target row renders `_target_balance`. **Positive control:** on a stub with `_target_balance = 55.41`, `config.target_balance = 50.00`, assert the row shows `55.41` — this fails against current code because no such row exists.

### Step 4 — Persist the diagnostic fields that are destroyed on every restart.

**Exact change.** Add to `export_scrumming_state` (`:3407-3502`) and `import_scrumming_state` (`:3504-3790`), all with `data.get(..., default)` restores:
- `_pending_wire_ledger` (`:783`, appended `:1943`) — **the provenance for $566.80 currently dies on restart**, and because `_add_wire_credits` guards with `if entries:`, a post-restart absorb creates no `wire_credits` key at all.
- `_fold_accumulator` (`:471`, incremented `:1436`) — lifetime compound counter, resets to zero every launch.
- `_tranches_malformed_dropped` (`:568`, incremented `:7882`) — the single most diagnostic number for "tranches fill but nothing happens", destroyed every launch.
- `_stack_tranches` / `_stack_created` (`:544-545`) — latent today (`stack_mode` False on all 35), but `_pending_stack_buy_usd` *is* exported at `:3436-3439` with a comment explaining why a restart must not lose the queued acquisition; the same reasoning applies to the tranches that acquisition produces.

**Why here:** `_pending_wire_ledger` is a hard prerequisite for Step 14 — without it the wire release has no audit trail. The rest must land before Phase 3 so you can attribute Phase 3's effects.

**Blast radius:** adds keys to `bot_state.json`. Verify that `import_scrumming_state` ignores unknown keys so an older build can still read the newer file, and that every new restore is defaulted so a newer build reads an older file.

**Test:** round-trip — populate all five fields on a stub, export, import into a fresh stub, assert equality; then import a state dict with all five keys *absent* and assert defaults. **Positive control:** write the round-trip assertion first and confirm it fails against the current export.

### Step 5 — Stop the restore path from destroying a bot's fold queue.

**Exact change.** `bot_container.py:2993-3022` — on an `import_scrumming_state` exception the code sets `_state_import_failed = True`, calls `_ledger_skip`, logs an ERROR naming the hazard, and then **does not `continue`**: control reaches `register(bot)` at `:3022` with default state. The function's own header at `:2942-2948` states it: *"the next 60s save writes those defaults over the good persisted record. That is strictly worse than a skip."* Grep confirms `_state_import_failed`, `_boot_state_records` (`:2587`) and `_restore_completed` (`:3042`) all have write sites and **zero reads**.

Minimum fix: either `continue` past registration on import failure, or have `save_all_state` (`:2457`) consult `_state_import_failed` and carry that bot's on-disk record forward. The carry-forward at `state_manager.py:123-126` keys on *absence* from `state["bots"]`, so a bad-import bot is present and invisible to it.

**Why here:** it protects the queue everything else operates on. CHIP/USD carries 199 tranches; one malformed field costs the whole queue plus per-lot cost basis, 60 seconds after launch.

**Blast radius:** a bot that fails import will no longer appear in the fleet. That is a visible behaviour change — it must ship with a loud operator-facing banner naming the bot and the exception, otherwise a missing bot reads as a deletion. Note also that `import_scrumming_state` is **not transactional** (it applies fields sequentially from `:3522`), so a partially-applied record is what you are protecting, not a cleanly zeroed one.

**Test:** write a temp state file with one bot's `scrumming_state` malformed, run restore, run one save cycle, assert the good record is byte-identical on disk. **Positive control:** the same test on current code shows the record zeroed.

---

## Phase 2 — Accounting. Moves the target balance; bounded by the existing cap.

Every step here changes the number the bot trades against, which changes target delta, which changes buy sizing. The magnitudes are measured and small, and each remains bounded by the per-cycle cap that is already in force. Nothing here changes tranche admission or order timing.

### Step 6 — Bump the closed-lifetime counter and clear the standing pool on detonation.

**Exact change.** `:9722 self._fold_tranches.clear()` has no counter bump. The two other bulk clears do (`:2784-2790`, `:2892-2897`), and `__init__` asserts the invariant at `:552-553`. Add `self._tranches_closed_lifetime += len(self._fold_tranches)` before the clear. Also zero `_standing_surplus_usd` in the reset block (`:9716-9737`) — after Step 7 that pool drains into the target, and detonation explicitly resets the target to anchor, so carrying it forward would inject pre-detonation surplus into a post-detonation target.

Do **not** clear `_fold_cycle_cap_consumed` here — that unlatches folds and belongs in Phase 3 (Step 13).

**Why here:** it is display-and-pool hygiene, and it must precede Step 7 so the drain never starts from a stale detonation-era pool.

**Blast radius:** the counter is display-only. The pool clear is bounded by whatever `_standing_surplus_usd` holds on a detonating bot — currently $0 on both bots that hold any. **Verify `detonation_enabled` per bot before promoting**; I did not measure it.

**Test:** stub with 5 tranches, `_standing_surplus_usd = 3.0`, closed counter 10 → detonate → assert closed = 15 and pool = 0. **Positive control:** current code gives closed = 10 and pool = 3.0.

### Step 7 — Implement the standing-surplus drain the code already specifies.

**Exact change.** `:1428`
```python
_growth_applied = min(_new_surplus_usd, _cap_remaining)
```
becomes the formula at `:488-494`:
```python
_available = _new_surplus_usd + self._standing_surplus_usd
_growth_applied = min(_available, _cap_remaining)
self._standing_surplus_usd = _available - _growth_applied
```
with `:1433-1435`'s separate `_leftover` accrual removed (now subsumed), and the cap-exhausted branch at `:1411-1427` left intact — it still parks, it just now has an outlet.

**Why here:** it must follow Step 3 (otherwise invisible) and Step 6 (otherwise it drains a stale pool). It must precede Step 11, because Step 11 changes the denominator this drain is measured against, and you want one variable moving at a time.

**Blast radius:** raises `_target_balance`, therefore raises target delta, therefore increases buy sizing. **Measured magnitude: $1.0992 fleet-wide** — BIO/USD $0.6289, CAP/USD $0.4703 — released at no more than `anchor × max_target_growth_pct/100` per cycle. It also resolves Break 7: after this step, a fold that lands while the cap is latched no longer *loses* its surplus, so the dequeue-before-growth ordering stops being a data-loss path and becomes hygiene only.

**Test:** helper-level, on the existing `tests/test_fold_target_growth_helper.py` stub. `_standing_surplus_usd = 5.0`, `_cap_remaining = 2.0`, `accum_profit = 0.5` → assert `_growth_applied == 2.0` and `_standing_surplus_usd == 3.5`. **Positive control:** the same inputs against current code give `_growth_applied == 0.5` and the pool unchanged at 5.0. Add a second case pinning that a *zero-surplus* fold still drains the pool.

### Step 8 — Give per-tranche Manual Fire a surplus and a growth call.

**Exact change.** In `manual_fire_tranche`, after `:2099 rebought_units = cost / float(fill_price)`, compute the surplus in the **cash frame**, identical to the autonomous path:
```python
_ref = float(tranche.get("ref", 0.0) or 0.0)
accum_profit = cost * (1.0 - float(fill_price) / _ref) if _ref > 0 else 0.0
_growth_applied = self._apply_fold_target_growth(
    accum_profit, source="MANUAL_TRANCHE_FOLD")
```
This is algebraically the autonomous formula for a single tranche: `extra_asset = cost × (1/fill − 1/ref)`, `accum_profit = extra_asset × fill = cost × (1 − fill/ref)`. Carry `_growth_applied` into the `pnl.event` at `:2145` and the `trade.filled` at `:2159`, both of which currently carry no profit field.

**Why here:** it must follow Step 7 so its surplus lands in a helper with a working drain, and follow Step 3 so it is visible. It must precede Step 9 so the two manual paths are unified against a known-good reference.

**Blast radius:** this is the step that will actually start moving the number, because per-tranche Manual Fire is the operator's dominant dip path (ETH 27/27 `operator_initiated`, ORCA 56/107). It is bounded per cycle by `_cap_remaining` at `:1408-1411` — at most `anchor × 1%` per cycle per bot, $33.00 fleet-wide per cycle. It does not change what is bought or when; it changes what is booked after the buy.

**Test:** stub tranche `ref=1.00, usd=10.00`, fired at `fill_price=0.95`, `anchor=200`, cap 1% → surplus = $0.50, assert `_target_balance` rose $0.50. **Positive control:** current code gives $0.00 rise.

### Step 9 — Unify the whole-bot manual fold onto the cash frame.

**Exact change.** `:9347-9350` accumulates in the **unit** frame:
```python
if _t_ref > fill_price:
    _manual_fold_accum_profit += (
        take * (_t_ref - fill_price))
```
`take` is units. Because wire credit and wire routing move `usd` only, this formula is blind to every wired dollar. Replace with the per-slice cash frame — for the slice fraction `take / t["units"]` of the tranche, `usd_share × (1 − fill_price/ref)`.

**Why here:** after Steps 7 and 8 all three fold paths land in the same helper; this makes them agree on the *input* to that helper. Doing it earlier would mean changing the formula while the drain semantics are still in flux.

**Blast radius:** raises booked growth on the whole-bot manual path, materially on wire-credited bots. An ETH tranche carrying $7.95 `usd` against $0.73 `units × ref` currently books ~11× less growth through Manual Fire than the autonomous formula would. Still bounded by the per-cycle cap.

**Test:** stub tranche `usd=8.0, units=1.0, ref=1.0` (wire-inflated), whole-bot fold at `fill_price=0.95` → cash frame gives $0.40, unit frame gives $0.05. Assert $0.40. **Positive control:** current code gives $0.05.

### Step 10 — Fix the `set_target_balance_live` frame mismatch.

**Exact change.** `:1286`
```python
if nt > old_t and accrued > 1e-9:
```
compares the operator's new value against the **grown** target. The operator sees the **anchor** (`config.target_balance`, `:1301`), and the GUI's change-detector diffs against the anchor (`bot_live_settings.py:499-505`). Change the guard to `nt > old_a`. Top-up then correctly sets `anchor := nt`, `target := nt + accrued`.

**Why here:** it must follow Step 3, which is what makes the anchor/target distinction visible. Shipping it earlier means the operator still cannot tell which number they moved.

**Blast radius:** changes buy sizing on **operator edits only**, never autonomously. Currently, a raise landing between anchor and grown target *lowers* the runtime target and wipes accrued growth; after the fix it raises it. Bounded by total accrued growth — $26.1996 fleet-wide, max $5.41 on any single bot (CAP/USD).

**Test:** extend `tests/test_set_target_balance_live_growth_preserve.py` with the `anchor < new < target` case: anchor 200, target 205, set 203 → assert anchor 203, target 208. **Positive control:** current code gives anchor 203, target 203.

---

## Phase 3 — Buy sizing and timing. LAST.

Everything below directly determines how much money a fold order spends and whether it fires at all. Nothing here should be promoted until Phase 1 and Phase 2 have run in production long enough to confirm the instruments work.

### Step 11 — Separate the capital budget from the growth budget.

**Exact change.** Introduce a second counter that tracks deployed capital, and stop spending the growth budget on it.

- Add `self._fold_cycle_capital_deployed: float = 0.0`, exported and restored beside `_fold_cycle_cap_consumed` (`:3422`, `:3577-3583`), reset at the same two sites (`:7190-7192`, `:6068-6071`).
- `:7990-7992` becomes `_cap_remaining_for_queue = max(0.0, _capital_cap_usd - self._fold_cycle_capital_deployed)`.
- After the packing loop, `self._fold_cycle_capital_deployed += _running_usd`.
- `_fold_cycle_cap_consumed` keeps doing exactly what `:815-822` and `:1408-1411` say: bounding **growth**.

`_capital_cap_usd` is a **new configured quantity and an operator decision** — see section 5.

**Why last-but-one:** it is the largest single change to order size in the plan, and every accounting fix must be in place and verified first so that when the orders get bigger you can see exactly what they produce.

**Blast radius: the largest of any step.** At a capital cap of `anchor × growth_pct / (interval_pct/100)` — the capital needed to produce exactly one cap's worth of growth, 20% of anchor at the fleet's uniform 1% / 5.0% settings — a $250-anchor bot's fold order goes from $2.50 to $50.00. Across the fleet this makes up to **$480.36** of currently-queued tranche capital deployable, of which **$343.48** is currently frozen. This is real money buying real coins on a live exchange.

**Test:** extract the packing loop (`:7999-8007`) into a pure function `pack_eligible(tranches, capital_remaining) -> list`, then unit-test it against fixture tranche sets copied from the live state file. Assert that ORCA's 32 over-cap tranches are admitted at a 20%-of-anchor capital cap and refused at the 1% cap. **Positive control:** run the same fixtures through the current expression and assert the admitted set is empty for those 32.

### Step 12 — Let the exchange minimum override the capital cap, and stop returning out of the tick.

**Exact change.** Two parts.

(a) `:8085-8090` tests the **already-capped** subtotal against `min_cost`. When the capped subtotal is below `min_cost` but the *full* eligible subtotal is not, admit tranches up to `min_cost` — that is, treat `min_cost` as a floor on the admitted set that overrides the capital cap for that one order. Also fix the unit bug at the same site: `_fold_notional_usd` is converted to USD (`:8080`) but compared against `_min_cost_fc`, which `_get_market_limits` returns in quote currency. Immaterial today (`quote_to_usd = 1.0` on all 35 bots, measured) but wrong.

(b) Replace the bare `return` at `:8166` with an `if/else` so `self._last_price = ticker.last` at `:8780` and the DIST block stay reachable — mirroring the fix the codebase already applied to the DIST path at `:8715-8716`.

**Why here:** (a) is meaningless before Step 11 — until the capital budget exists as a separate quantity there is nothing for `min_cost` to override. (b) is independent but touches the same block, so it ships together.

**Blast radius:** (a) makes autonomous folds fire on the **21 bots whose cycle cap is below $1.00** and which today cannot fold at all. Confirmed deadlocked: ONDO/USD ($0.75 cap vs $1.00 `min_cost`, $10.58 queue). (b) unblocks DIST sells and band-travel baseline updates that are currently deferred indefinitely on those same bots — this is a **sell**-timing change as well as a buy-timing one.

**Test:** stub `_get_market_limits` returning `min_cost = 1.00`, capital cap $0.75, queue $10.58 across 38 tranches → assert an order of at least $1.00 is issued. Separately, assert `_last_price` is updated on a below-min-cost tick. **Positive control:** current code issues no order and leaves `_last_price` stale; assert both first.

### Step 13 — Unlatch the cycle cap.

**Exact change.** `:6049-6072` requires `bb_pos >= 0.75`; `:7190-7192` requires a SCRUM. Add a third reset. **Which reset is an operator decision** — see section 5. Also clear `_fold_cycle_cap_consumed` in the detonation reset block (`:9716-9737`), the half deliberately deferred from Step 6.

**Why here:** after Step 11 this counter no longer gates *admission*, only *growth*, so unlatching it is a much smaller change than it is today. Doing it before Step 11 would unlatch admission too, which is a far larger blast radius for the same edit.

**Blast radius:** after Step 11, this affects only how much growth is booked per cycle — not order size. CAP/USD is the live case: `fold_cycle_cap_consumed = 0.5000` against a $0.50 cap, `target_grow_last_side = "lower"`, latched across restarts.

**Test:** stub with cap fully consumed, drive the chosen reset condition, assert the counter clears and the next fold books growth. **Positive control:** without the reset condition, assert growth stays $0.00.

### Step 14 — Repair the wire park/absorb path and release the parked money.

**Exact change.** Four parts, all in one step because releasing the money without fixing where it lands re-strands it.

- `:7264-7267` — drop the `_tranche_count_before == 0` condition. Absorb whenever `_pending_wire_credits > 0` and at least one tranche exists after the spawn. The park condition at `:1941` is "no tranches at wire arrival"; the absorb condition must match, not be narrower.
- `:2246-2252` — distribute the pool across the current tranche list the way `apply_wire_income` does at `:1916-1926`, instead of dumping it into `new_tranche`.
- Add the absorb call to the two spawn sites that lack it: DIST (`:8751-8775`) and Manual-Fire/Wire-Stack/Cartridge SCRUM (`:9139-9164`). Grep confirms neither references `_pending_wire_credits`.
- Fix the `_add_wire_credits` provenance gap: with `_pending_wire_ledger` persisted (Step 4), the `if entries:` guard no longer silently produces a tranche with no `wire_credits` key.

**Why absolutely last:** an inflated `usd` is exactly what makes a tranche permanently un-foldable under the current cap filter. Releasing $566.80 into tranche `usd` before Step 11 converts stranded-in-bucket dollars into stranded-in-tranche dollars with no outlet but Manual Fire or detonation. This step **depends on Step 11**, and its provenance depends on Step 4.

**Blast radius:** the largest single injection of fold-buy capital in the plan — **$566.80**. $351.70 of that (BTC $342.26, XLM $9.45) sits behind a window that is currently *open* and will fire on the next SCRUM regardless, so that portion is a change in *shape* (distributed vs one lump) rather than in whether it moves. $215.10 (ETH, ORCA) is currently frozen and will start moving for the first time.

**Test:** state-fixture test — load BTC/USD's persisted posture (0 tranches, $342.26 pending, cap $2.50), spawn 4 tranches, assert the pool is split across all 4 and that each resulting tranche is admissible under the Step 11 capital cap. **Positive control:** the same fixture against current code produces one ~$342 tranche and an empty admitted set.

---

## What must NOT be changed yet

Each item below is a decision, not a defect. Making the call wrong costs real money, and none of them can be inferred from the code.

### D1 — What should the fold capital cap actually be? (blocks Step 11)

The v3.16.40 comment at `:7961-7967` quotes the directive that created this filter: *"if I have enough lingering Folds that will immediately exceed my 10% growth rate, the amount needs to be soft-capped until the next lower BB touch is confirmed."* That is ambiguous between capping capital and capping growth, and the code does both against one number.

- **(a) Uncapped.** Restore pre-v3.16.40 behaviour: all price-eligible tranches fold. Maximum accumulation, no throttle on a deep dip. On today's fleet a single fold could deploy $145.21 on ETH.
- **(b) Its own percentage of anchor.** A new `max_fold_capital_pct` setting, independent of `max_target_growth_pct`. Explicit, but adds a dial.
- **(c) Derived: `anchor × growth_pct / (scrumming_interval_pct/100)`.** The capital needed to produce exactly one cap's worth of growth — 20% of anchor at the fleet's uniform 1% / 5.0%. Self-consistent, no new dial, and makes the growth cap the thing that actually binds. This is the option the arithmetic points to.

### D2 — May a tranche be partially split? (blocks Step 11's effect on the 129 over-cap tranches)

`:8004-8007` refuses partial splits, citing MEM-171 provenance corruption. That reasoning is arguable: `initial_buy_price` is a scalar that would be *copied* to both halves, not divided, and `usd`/`units` split proportionally. Without a split, any tranche larger than the chosen capital cap stays frozen no matter what Step 11 sets the cap to. With a split, ETH's $10.54 tranche becomes foldable in pieces.

**Options:** (a) keep the refusal and accept that some tranches only ever move via Manual Fire; (b) allow proportional split with `initial_buy_price` copied and `ref` preserved; (c) allow split only for tranches carrying `wire_credits`, since those are the ones inflated by a mechanism the tranche did not originate.

### D3 — Should the anchor compound? (blocks Step 10's long-run behaviour and any geometric growth)

Both cap sites use `_anchor_target_balance` (`:1407`, `:7979`), which fold growth never raises. The frozen anchor is deliberate — `:1285-1296` documents it against `docs/audits/2026-07-25_ytd_compounding_replay/REPORT.md`, and it is also the reference for the top-up/withdrawal semantic. But it means the growth budget is a constant dollar figure for the life of the bot: **linear, never geometric.**

**Options:** (a) leave frozen — accepts linear growth and keeps the top-up semantic clean; (b) derive the cycle cap from `_target_balance` instead — geometric, and the top-up semantic still works because the anchor stays the operator's input; (c) raise the anchor by applied growth — geometric, but destroys the accrued-growth-preservation logic at `:1285-1296`.

### D4 — Which reset should unlatch the cycle cap? (blocks Step 13)

**Options:** (a) reset on any **lower** BB touch, which is what the operator's own 2026-05-08 directive literally asks for (*"until the next lower BB touch is confirmed"*) and which the current upper-band condition at `:6051` inverts; (b) a time-based reset per TA bar; (c) leave as-is — after Step 7 the held surplus is no longer lost, it drains next cycle, which is exactly the behaviour specified at `:488-494`. Option (c) is genuinely defensible and is the smallest change.

### D5 — Should Smart Wire export principal on the scrum route?

`:7211-7219` routes a percentage of **gross sale proceeds** out and rewrites `scrum_usd`; the tranche is then built with full `units` but reduced cash. The measured consequence is the `usd/(units × ref)` constant: 0.800 on 16 bots. **The source bot can only ever rebuy ~80% of the units it sold.** On an accumulation platform that is a permanent per-cycle unit leak.

Separately, `:1638-1640` passes gross proceeds to `compute_safe_outflow_pct` as `scrum_profit_usd`, and `smart_wire.py:108-109` treats that argument as profit — so the SWOS ceiling is sized against the wrong quantity.

**This changes how much money leaves on every scrum and is not a fold-subsystem defect.** Options: (a) route from realised profit rather than gross proceeds; (b) keep routing gross but size the tranche from pre-routing proceeds so units and cash stay coherent; (c) leave as designed and accept the unit leak as the cost of cross-bot compounding.

### D6 — Should wire credit be tracked separately from organic tranche capital?

`:1920` adds to `usd` alone. Once Step 11 lands, this may be harmless — the cap becomes proportional and inflated tranches become admissible. But the `usd ≈ units × ref` relationship stays broken, and it is the diagnostic fingerprint that made Break 2 findable.

**Options:** (a) no change — Step 11 absorbs it; (b) add a distinct `wire_usd` field so the two capital sources can be budgeted separately; (c) synthesise `units` at the credit-time price, which restores the invariant but fabricates a unit count the bot never bought.

### D7 — Do not enable Stack Mode or Smart Ceiling until their paths are fixed.

Both are False on all 35 bots, and all three latent defects arm the instant they flip:

- **Stack Mode:** `:10041-10054` returns `None` from `_execute_sell`, `:7170` reads it as failure, and the entire spawn block `:7180-7330` is skipped. Units sell, no tranche is created, `_main_lots` is never consumed, and every successful stack open logs `SCRUM ABORTED: sell failed`. Additionally `:1871-1879` is the only uncapped target-growth path in the system and it raises the anchor too — enabling Stack Mode would make the dashboard Target start moving via the one path with no cap, which would badly mislead diagnosis of everything else in this plan.
- **Smart Ceiling:** `:8062` tapers `buy_cost` while `:8171` computes `asset_at_scrum` from the full untapered `t["usd"]`, and `:8203` dequeues every eligible tranche regardless. At taper 0.1, 90% of a tranche's capital is dequeued without being spent and growth books zero.

### D8 — Extractor sizing reads the anchor.

`bot_container.py:2036` `usd_amount = float(getattr(bot.config, "target_balance", 0) or 0)` sizes an extraction from the frozen anchor, not the grown target. Out of scope for this plan, but it is a live sizing path that changes meaning once compounding works. Flagging, not fixing.

---

## Reset question

**The short answer: repairing the code fixes most of the stranded state on its own. Two categories need a decision, and one is unrecoverable.**

### Released by code repair alone — no state edit needed

| What | Amount | Released by |
|---|---:|---|
| `_standing_surplus_usd` | $1.0992 | Step 7. The drain reads the persisted value and pays it out at the per-cycle rate. Persistence is correct; only the drain was missing. |
| `_pending_wire_credits` | $566.8045 | Step 14. The absorb condition is widened to match the park condition, so ETH's and ORCA's permanently-closed windows reopen. No state edit. |
| Over-cap tranche capital | $343.4795 | Step 11, **conditionally** — only for tranches smaller than whatever capital cap D1 selects. At 20% of anchor, all 129 become admissible. At a lower cap, the residue needs D2 (partial split) or manual discharge. |

**Risk of this path:** low, and it is the only path that does not fabricate history. The values on disk are honest records of what the code did; the repair changes what the code does with them next. The one thing to watch is that Step 14 releases $566.80 into buy capital in a single event on four bots — stage it by promoting Step 14 to one bot first (XLM/USDC, $9.45, window already open) before ETH and BTC.

### Needs a decision, not necessarily an edit

**`_fold_cycle_cap_consumed`.** CAP/USD carries 0.5000 — 100% of its cap — plus BTC/USD 0.0919 and SUI/USD 0.3389. These are restored at `:3577-3583`, so **repairing the code does not clear them.** Today CAP/USD is admission-frozen: `_cap_remaining_for_queue` evaluates to $0.00, so `:8001` admits nothing.

After Step 11 this counter stops gating admission and only bounds growth, so the harm shrinks to "CAP/USD's target will not rise until its next SCRUM or upper-band touch" — which is correct behaviour. **Recommendation: no state edit.** Ship Step 11 and let the counter clear naturally.

If you want it cleared sooner, the alternative is a one-shot migration zeroing the field on all 35 bots at next launch. **Risk:** it grants every bot a fresh growth budget simultaneously, so the first post-launch fold on each bot books up to the full cap at once — $33.00 fleet-wide of target increase in a single tick, which then raises target delta on 35 bots simultaneously and triggers buying. That is a synchronised fleet-wide buy event. Do not do this.

### Unrecoverable — do not attempt to correct

- **Growth never booked by per-tranche Manual Fire.** Nine bots sit at `target == anchor` exactly (ZEC, HYPE, RAVE, NEAR, XLM, ADA, LTC, LSETH, WLFI); three of those (LTC, LSETH, WLFI) have simply never traded (created = 0, closed = 0). The other six accumulated closures with zero growth. There is no per-event history in `bot_state.json` to replay from, and `MANUAL TRANCHE FIRE COMPLETE` appears zero times in the retained log window. **Writing a corrected target would be fabrication.** Leave them; Step 8 starts the clock from now.
- **Wire provenance for the $566.80 already parked.** `_pending_wire_ledger` was never persisted, so the source-bot attribution for anything that survived a restart is gone. Step 4 stops the bleeding forward; it cannot reconstruct the past.
- **`_tranches_closed_lifetime` on any bot that has detonated.** Understated by the size of the queue at detonation time, unrecoverable. Step 6 fixes it forward.

### Explicitly do NOT reset

- **The 26 grown targets, totalling $26.1996.** These are correct values produced by a working path (`:1429`). They are the only evidence the growth mechanism functions at all. Resetting them to anchor would destroy the baseline against which every step in this plan is measured.
- **Lot fragmentation.** CHIP/USD holds 199 tranches spanning 4 distinct `ref` values against 64 lots. Fragmented, not corrupt — a consequence of one-tranche-per-lot spawn (`:7234-7249`) with no consolidation anywhere in the 94 `_main_lots` references. A consolidation pass would mutate live cost-basis records, which is the one thing MEM-171 exists to protect. Leave it.

---

## What this plan does NOT establish

1. **The running build does not match the source on disk.** This is the single largest limitation and it governs everything. All 7,957 `HOLD FOLD` lines in the live window carry pre-v3.24.43 wording, including lines written after the source file's mtime. **No runtime observation in this plan validates a current-source line number.** Static claims are anchored to quoted source; runtime claims corroborate the shape of the failure and the state file it produced, and nothing more. Step 0 exists because of this.

2. **No runtime behaviour was observed.** Per standing directive I executed no project code and constructed no project classes. Every claim about what a path *does* at runtime is an inference from quoted lines plus read-only inspection of `~/.acervator/bot_state.json`. The two scripts I ran open that file in mode `"r"` and write nothing.

3. **Exchange `min_cost` per pair is known for exactly one symbol.** ONDO/USD ($1.00), quoted from the live log. The rest come from `_get_market_limits` at runtime. I confirmed **21 of 35** bots have a cycle cap below $1.00 and that the deadlock mechanism is real for at least one — I could not compute how many are actually deadlocked. (Note: 21, not the 20 reported upstream; VVV/USD at $0.75 was missed.)

4. **The tranches I identify as over-cap are not proven to be price-eligible right now.** Eligibility requires `ticker.last <= ref × (1 − interval/100)` and needs a live ticker. `bot_state.json` carries `last_trade_price` but not a market price. What is established is that these tranches *would* be excluded whenever they become price-eligible — not that they are being excluded on every tick today.

5. **Attribution of CAP/USD's exact-cap consumption is unresolved.** It could have come from the autonomous path (`:8295`) or the uncapped whole-bot manual path (`:9430`). Zero `TARGET GROWN` lines survive in the retained window; rotated `gate.log.1-.5` are from June and were not searched.

6. **Per-tranche Manual Fire is not proven to be the dominant discharge path.** `MANUAL TRANCHE FIRE COMPLETE` appears **0 times** in the retained log window. The inference rests on `operator_initiated: True` on 27/27 ETH tranches and 56/107 ORCA tranches, plus the operator's own account.

7. **BIO/USD's target of exactly $102.0000 against a $100 anchor is unexplained.** Two `min(surplus, cap)` draws landing on a round number to the cent is possible but not obviously the product of that formula. I did not reconstruct its growth history and cannot rule out a writer I have not found.

8. **Fee impact on booked surplus is not quantified.** `accum_profit` (`:8181`) has no fee term, and 24 of 35 bots run `trading_fee_pct` 1.6 (11 at 0.6) against a 5.0% gross OTD spread. Every `TARGET GROWN` figure therefore likely overstates real compounding — but I did not verify whether fees are deducted upstream inside `_execute_buy`, so the magnitude is unestablished.

9. **`detonation_enabled` was not measured per bot.** Step 6's blast radius assumes it is off or rare; verify before promoting.

10. **A unit divergence on the fold path is flagged but unmeasured.** `_execute_buy` credits `_current_holdings` at the *intended* price (`:10825`, `:10917`) while the fold path appends to `_main_lots` at the *actual* fill (`:8170`, `:8191-8194`). `accum_profit` derives from the lots number. Whether a later `_reconcile_holdings` pass absorbs the drift was not traced, and zero folds executed in the observable window, so there is no measurement.

11. **Sim parity is unverified.** `src/trading/profit_fold.py:2-6` declares itself the *"single source of truth for target-balance growth"* shared by all three engines; grep shows `apply_profit_fold` has **zero callers** outside its own `__main__` self-test, and `bot_container.py:122` claims it is wired up. Its formula also disagrees with the live one in two ways — it caps against the grown target rather than the anchor, and routes spillover to `realised_pnl` rather than a standing pool. **The Simulator's growth semantics cannot be assumed to match live**, so no step in this plan can be validated in the Sim without first establishing which formula the Sim actually runs.

12. **The `_funits` variable at `:8058` is assigned and never read** (grep: exactly one occurrence in all of `src/`). I report it as dead, not as intent — it may be a stub for planned unit-frame accounting that Step 9 should reuse rather than delete.
