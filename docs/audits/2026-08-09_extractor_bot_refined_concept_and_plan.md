# Extractor Bot — refined concept and development plan

**Scope.** This report covers `src/trading/extractor_bot.py` (1702 lines) and the capital-coordination modules it depends on. All repo paths are relative to
`acervator_session25_CLOSE_hop5_v3_15_27/`.

Design-document keys, all under `_archive/docs_audits_pre_2026_07_24/`:

| Key | File |
|---|---|
| DESIGN | `2026-05-20_extractor_bot_design.md` |
| FINAL | `2026-05-20_extractor_bot_final_design_consideration.md` |
| INVERTED | `2026-06-05_inverted_extractor_design_space.md` |
| BLEED | `2026-06-05_extractor_vs_scrumming_and_bleed_offset.md` |
| USDBASE | `2026-06-05_extractor_usd_vs_base_audit.md` |
| FIRING | `2026-06-05_extractor_firing_and_profit_flow_audit.md` |

---

## 1. What the Extractor is

The operator holds a pool of a base asset. Example: 5 ETH. The operator wants 6 ETH. The operator does not want to trade ETH itself.

The bot owns a slice of that pool. The slice is called the **chunk**. The bot fires small temporary rounds of base units — **artillery** — into volatile alt pairs quoted in that base. It buys an alt on a dip. It sells the alt on a rally. It returns the base units to the pool, plus a gain (DESIGN:34-41).

**Anchor.** ScrummingBot anchors to a target USD balance of an alt. The Extractor anchors to a pool of a base asset (DESIGN:36).

**Metric.** Base unit count. Not USD.

**The central rule — the double-layer valuation split.** Risk is judged in USD. Success is judged in base units (DESIGN:333-355). Drawdown detection multiplies alt units by price-in-base by the USD rate, then compares against `artillery_size_usd_at_entry`, which is snapshotted at firing and never updated (DESIGN:355). Exit profitability is computed only in base units (DESIGN:359-373). The worked case: RAVE/ETH falls 10% while ETH/USD rises 5%. That is not a real drawdown. Do not average down.

**Intended state machine.** Per pair, not per bot.

- `PENDING` — no alt held. Watch for a bearish signal. It is never stored on a Position (`extractor_bot.py:78`, comment "transitional — never persisted on a Position"). It means "pair absent from `_positions`".
- `IN_FLIGHT` — alt held.
- `DRAWDOWN` — sub-state of IN_FLIGHT. USD notional below the entry floor. Averaging-down starts.
- `BULLISH_EXIT` — sub-state of IN_FLIGHT. The bullish gate fired and the sell is queued.

Intended transitions (DESIGN:76-81): PENDING→IN_FLIGHT on a bearish signal with pool capacity; IN_FLIGHT→DRAWDOWN on the USD floor breach; DRAWDOWN→IN_FLIGHT on recovery or correction; IN_FLIGHT→BULLISH_EXIT on the bullish gate; BULLISH_EXIT→PENDING (tier locks) **or** BULLISH_EXIT→IN_FLIGHT (tier rolls).

Note on the source: the diagram at DESIGN:54-58 draws **five** boxes, including `AT_OR_ABOVE ENTRY`. The definitions list at DESIGN:70-74 names four. The fifth box is unaccounted for in the definitions.

**Intended accounting model.** Three base-unit numbers (DESIGN:174-187, `extractor_bot.py:159-186`):

- `_chunk_size_base` — the operator's allocation. Never auto-resized.
- `_chunk_free_base` — available for new artillery.
- `_chunk_extracted_total` — cumulative base added since start.

The chunk is the accounting unit. The bot never reads `exchange.get_balance(base)` to size a decision (DESIGN:27, DESIGN:177-181).

**Stated invariant I1**, verbatim from DESIGN:197-200:
`chunk_free + sum(cost_basis for open positions) == chunk_size + chunk_extracted_total`, annotated "Violation = test failure".

**Concurrency control.** One number. `_has_chunk_capacity` computes `reserve = chunk_size_base * (pool_reserve_pct/100)` and returns `(chunk_free_base - artillery_base) >= reserve` (`extractor_bot.py:531-534`). The reserve is measured against chunk **size**, not chunk **free**, by design, "so corrections that have drained the chunk can't be papered over" (`extractor_bot.py:520-523`).

---

## 2. Ground truth — design vs implementation

| # | Intended | Implemented | Divergence |
|---|---|---|---|
| 1 | Chunk USD converted to base units at bot creation via a live rate (DESIGN:96-103) | `set_initial_chunk_rate` (`extractor_bot.py:234`) is the only method that sets the rate at construction. It has **zero callers** in `src/`, `main.py`, `tests/`, `tools/`. The only non-definition hit is a tooltip string at `bot_wizard.py:1307`. | **Total.** On a bot with no saved state, `_chunk_to_base_rate` keeps its default `1.0` (`extractor_bot.py:160`), so `_usd_to_base` (`:695-699`) is the identity. `_chunk_size_base` equals the raw USD number. A restored bot is different: `import_state` is a second writer at `:1655-1656`, so it inherits whatever rate the state file carries. |
| 2 | Artillery sized in USD, converted to base at firing (DESIGN:96-103) | `artillery_base = self._usd_to_base(artillery_usd)` at `:1343`, with the identity rate above. Default `extractor_artillery_size_usd = 5.0` (`bot_container.py:426`). | **Money-moving.** On a fresh ETH-pool bot a "$5" round is ordered as **5 ETH**. The error factor equals the USD price of one base unit. On a USD or USDC base the factor is exactly 1 and sizing is correct by accident. `guarded_place_order` (`bot_container.py:996-1144`) checks `min_amount` and `min_cost` only; it has no maximum-size check. |
| 3 | The bot files a `CapitalReservationRegistry` claim on its chunk plus hedge (`extractor_bot.py:318-333`) | The `reserve()` call sits inside `set_initial_chunk_rate`. Unreachable per row 1. | **Total.** `_crr_token` stays `None` (`:228`). The tick heartbeat is guarded at `:1457` and never pulses. The `stop()` release is guarded at `:493` and never runs. No sibling bot ever sees this Extractor's claim. |
| 4 | USD-anchored re-sizing with spike protection (USDBASE:7) | `update_base_usd_rate` (`:794-868`) is fully written, with a 10% divergence threshold and a median-of-3 fallback. **Zero callers.** Its own docstring at `:800-803` asserts the tick loop calls it each tick. `tick()` (`:1438-1533`) contains no such call. | **Total.** `_rate_spike_events` and `_rate_refuse_events` (`:177-178`) are always 0. |
| 5 | Compounding tier ROLL vs LOCK (DESIGN:416-432) | Both branches run the identical statement `self._chunk_free_base += base_received`, at `:1267` and `:1275`. Only `log_kind` differs. The in-code comment at `:1263-1266` concedes it. The tier bump at `:1270-1271` requires `pos.alt_units > 1e-12`, which is false on the default `extractor_exit_pct = 100.0` (`bot_container.py:439`). | **Total.** The tier never advances. The operator log emits `ROLL_TO_NEXT_TIER` for behaviour identical to `LOCK_TO_POOL`. `bot_live_settings.py:3301-3307` correctly labels the field "currently informational". |
| 6 | Four states; PENDING implicit | Three states are ever written to a Position: `IN_FLIGHT` at `:1413`, `DRAWDOWN` at `:929-930`, `BULLISH_EXIT` at `:947`. | Matches, with one gap: on a partial exit the position survives (`:1306` false) but nothing writes the state back to IN_FLIGHT. `:931` only tests for DRAWDOWN. The GUI then shows the position permanently as `bullish_exit` (`:1568`). |
| 7 | DRAWDOWN→BULLISH_EXIT is reachable | `_evaluate_open_position` returns at `:939` right after `_maybe_fire_correction`, before the exit check at `:944`. | **Real.** While `_is_in_drawdown()` is true, the exit signal is never read. The only exits are price recovery or Manual Fire (`:1075`). |
| 8 | Entries evaluated in volume-rank order (DESIGN:329) | MODE B ranks by `volume_24h` and slices top-N (`:658-671`). MODE A, active whenever `config.extractor_alt_targets` is non-empty, iterates the operator's selection at `:620` with **no volume sort**. Both modes append open-position pairs at the tail (`:678-680`). | **Partial.** The tie-break rule holds only in MODE B. The "one entry per tick" rule holds in both (unconditional `break` at `:1533`). |
| 9 | Operator sets scan breadth | `top_n = max(5, min(10, top_n))` at `:670-671`. Default 8 (`bot_container.py:430`), no declared range. | Silent override. 20 becomes 10; 2 becomes 5. Not logged. |
| 10 | Full exit destroys the position; partial exit keeps it | `:1306` reads `if pos.alt_units < 1e-12 or self.config.extractor_exit_pct >= 100.0`. On default config the second clause is always true. `:1252` subtracts only `filled_units`. | **Real.** A partial market fill leaves alt units on the exchange with no position record. `manual_fire_position` forces `extractor_exit_pct = 100.0` at `:1165`, so the operator's own close path hits this every time. |
| 11 | Cost basis reduced in proportion to what was sold | `cost_basis_proportional` comes from `config.extractor_exit_pct` (`:1246-1248`), the **intended** fraction. `base_received` comes from `filled_units` (`:1245`), the **actual** fill. | On a partial fill the two disagree. `gain_base` (`:1249`) is understated and `pos.cost_basis_base` (`:1253`) is over-deducted. The corrupted basis then feeds `_exit_is_profitable_in_base` (`:914-917`) and the correction headroom (`:972-975`). |
| 12 | Ledger reflects realised economics | The exit gate applies the fee at `:912-913` and compares at `:917`, so any exit that clears the gate has after-fee proceeds above the proportional basis. The ledger then credits **gross** `base_received` at `:1267`/`:1275`, and `gain_base` at `:1249` carries no fee term. The entry debit at `:1405-1408` is also gross. | Both sides of the ledger are gross of fee. The gate itself is sound. A real shortfall needs slippage between the ticker price the gate used and `fill_price` at `:1245` — the fee alone cannot produce one. |
| 13 | Hedge reserve protects `chunk_free` from corrections (DESIGN:132-136) | `_hedge_free_base` is subtracted at `:1054` and credited nowhere. Exits return 100% of proceeds to `_chunk_free_base`. | One-way drain. Currently masked, because the field is `0.0` on a fresh bot per row 1. |
| 14 | Restore is lossless | `import_state` wraps each `ExtractorPosition` build in `try/except: continue` at `:1668-1694`, while `_chunk_free_base` is restored verbatim at `:1659-1660`. `bot_container.py:3223-3225` calls it on every restore. | **Capital leak.** A malformed record is dropped silently. The alt units stay in the wallet. The `if pair in self._positions: continue` guard at `:1495` no longer matches, so the bot double-buys the pair. `bot_container.py:3238-3240` has a loud handler that this inner loop bypasses. |
| 15 | MEM-257 fail-closed buy check protects the artillery path | `verify_buy_safe_or_refuse` refuses only when the exchange reports zero **and** `expected_units > 0` (`buy_safety.py:149`). `extractor_bot.py:1364` passes `expected_units=0.0` hardcoded. | The refuse branch is unreachable from that call site. Only a fetch exception (`buy_safety.py:158`) can refuse. `buy_safety.py:91-93` also names `Balance.absent` in its own docstring and never reads it; the body reads `total` and `free` only (`:138-139`). |
| 16 | `verified_units` reconciles bot state against the exchange | Both call sites unpack it and never read it (`extractor_bot.py:1000`, `:1362`). The correction path keeps using `pos.alt_units` (`:1053`). | The bot pays for the round-trip and discards the answer. `ruff` cannot see this; `F841` does not flag tuple-unpacked names. |
| 17 | Confidence gates the TA consensus | `TASignalProvider.__init__` accepts `confidence_threshold` (`ta_signal_provider.py:185`) and passes it to `VotingEngine` (`:194`), which stores it (`ta_engine.py:2520`). Nothing reads it. `consensus_direction` (`ta_engine.py:107-117`) tests `net_score > 0.1` / `< -0.1` only. | The knob is dead end-to-end. `extractor_bot.py:756-758` fires artillery on a net_score of 0.11. The docstring at `ta_engine.py:2506-2508` advertises a threshold that does not exist. |
| 18 | Signal failures are visible | Four `except Exception: return None` blocks in `ta_signal_provider.evaluate()` (`:233-237`, `:241-245`, `:256-260`, `:266-270`), each logging at DEBUG. `main.py:256-257` sets the root level to INFO. | The messages are suppressed in the shipped configuration. The consumer bare-`continue`s at `extractor_bot.py:1473-1475` and `:1497-1499`. TA can go dark permanently with zero evidence. |
| 19 | Ship gate: five named tests, then five more, with a written commitment not to ship without a chunk-invariant test (DESIGN:508-512, FINAL:143-147, FINAL:196) | `tests/` contains no import of `ExtractorBot`. The single grep hit, `tests/test_manual_fire_settled_fill.py:22`, is a line inside a docstring. `tests/test_extractor_bot.py` does not exist. The only `assert` in `extractor_bot.py` is the BotMode check at `:142`. | **The gate was bypassed.** I1 has no assertion and no test. |
| 20 | Docstring references resolve | `extractor_bot.py:28`, `:29`, `:130` and `:1284` cite four live paths. All four are absent from the live tree. `:130` asserts a drift-detector test at `tests/test_extractor_bot.py` "pins this invariant by name-checking the module source". | The docstring asserts live enforcement that is not running. |
| 21 | Inverted mode mirrors the machine cleanly (INVERTED:69-77) | Flag at `:708-716`; entry side SELL at `:778`; exit side BUY at `:784`; standing-units import at `:259-279`. Sizing at `:1377` divides `artillery_base` by price and passes the result as the order amount. Exit at `:1245` credits `filled_units * fill_price` to `_chunk_free_base`. | Dimensionally inconsistent in both directions. Confidence: **likely**, not verified by execution. Neither path has a mode branch. |
| 22 | The chunk never queries the exchange (DESIGN:27) | True. The file holds no reconciliation against exchange balances. | Matches the design. It is also why rows 10 and 14 lose capital undetected. |

**Design-internal contradictions**, carried forward because they still block a rewrite:

- C1: DESIGN:24 replaces the fixed pair list with dynamic top-N. DESIGN:455 still specifies `extractor_target_pairs` as a wizard multi-select. Both are shipped — that is row 8.
- C2: DESIGN:27 states "NO Circuit Breakers". DESIGN:211 lists `_cb_*` among the gate functions to extract.
- C3: DESIGN:396-404 reads `pos.artillery_size` and computes in base units. No such field exists (DESIGN:152-172). DESIGN:346-355 mandates USD for the same decision.
- C4: DESIGN:96-103 freezes the rate at creation "so ETH-USD price moves don't silently shrink/grow the bot's chunk". USDBASE:7 quotes the operator asking for full USD anchoring. The two are mutually exclusive. **Unresolved design conflict, not a defect.** USDBASE's own worked example does not apply to this tree: its premise at USDBASE:25 — that `set_initial_chunk_rate` is "called by BotManager during construction" — is false.

**Self-refuting item in the design.** DESIGN:424-430 gives cycles $5→$5.50→$6.10→$6.70 and compares $6.70 against "$5.50 + $5.50 + $5.50 = $16.50 if non-compounded", concluding compounding trades larger-but-rarer for smaller-and-frequent. The $16.50 counts the $5.00 principal three times. Extraction only: compounded $1.70, non-compounded $1.50. Compounding is slightly **better**. The conclusion contradicts its own arithmetic.

---

## 3. Harness verdict

**What a green archetype means.** It means "nothing I already thought of is broken". It does not mean "correct". Two results in this run prove it:

- `capital_registry.py` returned **passed=True**, 64 findings, 0 high. That module is never constructed anywhere in the live tree. Every line of it is unreachable.
- `buy_safety.py` returned **passed=True**, 17 findings, 0 high. Its refuse branch cannot fire from the Extractor's main buy path.

A clean archetype on dead code reads exactly like a clean archetype on correct code.

**Counts.**

| Target | Archetype | passed | Findings | high / med / low | By tool |
|---|---|---|---|---|---|
| `extractor_bot.py` | coding | **False** | 156 | 13 / 47 / 96 | ruff 115, vulture 25, mypy 6, bandit 6, hallucination 4 |
| `extractor_bot.py` | ta | **False** | 5 | 1 / 0 / 4 | ta-quant 1, ruff 4 |
| `capital_reservation.py` | coding | **False** | 109 | 1 / 21 / 84 (+3 info) | ruff 84, vulture 15, mypy 8, semgrep 1, scaffolding 1 |
| `capital_registry.py` | coding | **True** | 64 | 0 / 5 / 59 | ruff 47, vulture 13, mypy 2, hallucination 2 |
| `opportunity_arbiter.py` | coding | **False** | 36 | 1 / 7 / 28 | ruff 23, vulture 11, mypy 1, hallucination 1 |
| `ta_signal_provider.py` | coding | **False** | 31 | 2 / 7 / 22 | ruff 19, vulture 12 |
| `buy_safety.py` | coding | **True** | 17 | 0 / 5 / 12 | ruff 12, vulture 2, hallucination 3 |

All nine sub-tools reported availability `ok` on every coding run. `errors[]` was empty on all runs. `gui_archetype` does not apply: none of these files imports PySide6/PyQt or defines a QWidget.

**Instrument calibration.** `ta_archetype` returned zero findings on the three capital modules. That zero is real, not a dead instrument: the same command on `src/trading/ta_engine.py` returns 151 findings and `passed=False`.

**REAL findings, ranked by production impact.**

1. **`set_initial_chunk_rate` and `update_base_usd_rate` have zero callers.** Reported only as vulture **LOW** entries at `:234` and `:794`, sitting next to `unused class 'ExtractorBot'` at `:118` — a single-file false positive that trains the reader to discount the whole group. This is the top defect in the file and the harness ranked it last.
2. **S112 at `:1693`** — malformed saved position dropped on restore. Double-buy plus permanent orphan alt. The only S112 site that loses base units.
3. **S112 at `:1479`** — ticker failure silently suspends management of an open position: no drawdown check, no correction, no exit, no log. The asymmetry is the finding: the entry-side equivalent 30 lines below was hardened at `:1508-1519` with a comment explaining that a silent skip is indistinguishable from no signal. The exit side, where money is already deployed, was left bare.
4. **S112 at `:666`** — a full ticker outage empties the watch list with no signal. Unbounded sequential ticker calls, one per candidate market, on the asyncio-on-GUI-thread path. Bias, and jank.
5. **Hallucination H001 ×4** at `:28`, `:29`, `:130`, `:1284`. The serious one is `:130`, which claims a live drift-detector test that does not exist.
6. **Five genuinely dead imports** at `:56`, `:59`, `:62`, `:63`, `:64`. `OrderSide` at `:63` is dead only because `:777` and `:783` re-import it locally, which ruff separately flags F811.
7. **`enable_phantoms` at `:140`** — accepted and discarded. Both call sites pass it explicitly (`main_window.py:7545`, `bot_container.py:3126`). An API lie, not a defect.

**NOISE.**

- **S112 at `:615` and `:652`** — bounded. A malformed market entry is dropped from one refresh. `:615`'s outcome is already reported at `:626-629`, though as "delisted or wrong base", which misattributes a data-shape failure.
- **S101 / B101 at `:142`** — the assert restates a condition both construction sites already dispatch on (`main_window.py:7542`, `bot_container.py:3124`).
- **vulture `:69` — FALSE POSITIVE. Do not act on it.** `ExchangeInterface` sits under `if TYPE_CHECKING:` and resolves the string annotation at `:139`. ruff's F401 pass flags `:56`, `:59`, `:62`, `:63`, `:64` and deliberately omits `:69`.
- **ta-quant TA004 at `:844`** — both operands are percentages. `divergence_pct` at `:843` is a ratio × 100.0; `_rate_spike_threshold_pct` is the literal `10.0` at `:175`. The rule cannot classify a literal-assigned constant and defaults it to absolute (`tools/harness/ta_archetype.py:247-263`, `:334-353`).
- **vulture "high" on an unused `field` import** in `opportunity_arbiter.py:36` and `capital_reservation.py:72`. Both are correct and inert. These are the **only two high findings across all three capital modules**.
- **semgrep at `capital_reservation.py:339`** — flags a log format string holding a bot_id, a quantity and a UUID prefix as a possible hardcoded secret.

**Meta finding.** For this file the archetype's severity ranking is inverted. All 13 highs are lint-class. None of them moves wrong money. The two defects that do move wrong money appear as LOW entries in a list that also contains five false "unused method" reports (`set_bot_manager`, `export_state`, `import_state`, `tick`, `manual_fire_position` — all reached by duck-typed dispatch at `bot_container.py:2428`, `:1551`, `:3223`, `bot_live_settings.py:972`). Reading the tool output alone would rank this file clean-but-linty. Only a repo-wide grep found the real defects.

**One count in the session brief is wrong and I correct it here.** `ruff --select S112,F401,F841,S101,ARG002` returns exactly 14 findings: F401 at 56, 59, 62, 63, 64; ARG002 at 140 and 1337; S101 at 142; F841 at 1157; S112 at 615, 652, 666, 1479, 1693. That is **five** dead imports, not six, and `:69` is not among them.

---

## 4. The two architectural blockers

Operator statement, 2026-08-07: *"Extractor Bot has never met functional release criteria. Common asset sharing between bots and attempts to engineer bot inoperability protocols and rules have thus far failed."*

The finding of this report: **neither protocol failed. Neither ran.**

### 4a. Common asset sharing between bots

**The named risk** (DESIGN:558). A ScrummingBot reads `exchange.get_balance("ETH").free`, sees TOTAL ETH, mistakes a sibling Extractor's chunk for excess, and scrums it away. DESIGN:560 classes this as the same bug family as MEM-203 / MEM-256.

**The specified answer** (DESIGN:564-599). Claim **subtraction**, not stand-down. A `BotManager` helper sums other bots' claims on the same base. Every balance read becomes `free_for_me = raw_exchange_free - sibling_claims`. Two explicit rules: paused bots still own their chunk ("claims are allocation, not active deployment", DESIGN:~570); and when `free_for_me` is negative the ScrummingBot logs a warning and refuses to fire FOLD-side trades, and **does not** try to sell to recover, "the excess belongs to a sibling" (DESIGN:595).

**What exists.** Three separate systems. Trace each.

**System 1 — `BotManager.sum_sibling_base_currency_claims`.** Defined at `bot_container.py:2608-2625+`. Its docstring is exactly the design: a ScrummingBot's claim is its `target_balance` converted through `_quote_to_usd`; an ExtractorBot's claim is its `_chunk_size_base`.

The full code path:

```
scrumming_bot.py:6252  _sibling_claims = self._sum_sibling_base_currency_claims()
```

`def _sum_sibling_base_currency_claims` **does not exist**. An AST walk of `scrumming_bot.py` returns zero methods containing "sibling". No `__getattr__` exists on `ScrummingBot` or `BotContainer`. `BotManager.sum_sibling_base_currency_claims` has zero callers repo-wide — the underscore-prefixed name at `:6252` is not that method.

Line 6252 sits inside `tick` (`scrumming_bot.py:5094-9479`) with **zero enclosing `Try` nodes**. It sits on the INITIAL ENTRY path, immediately after the quote-balance fetch at `:6237-6245`, reached whenever a ScrummingBot needs an initial acquisition. The `AttributeError` propagates to the fault boundary at `bot_container.py:1224`, which sets `BotState.ERROR` at `:1261` and enters COOLDOWN after `MAX_CONSECUTIVE_ERRORS` at `:1277-1286`.

The one line that implements §13a is therefore a hard crash on the path it guards. This is the whole of the asset-sharing protocol. It is one call site, on one branch, in one bot class, and it raises.

**System 2 — `CapitalReservationRegistry`** (`capital_reservation.py:149`). Asset-quantity claims. This one is real and is live for ScrummingBot: `_ensure_capital_reservation` (`scrumming_bot.py:1107`) reserves at `:1226`, updates at `:1252`, heartbeats at `:1256`, called once per tick from `:5103`; released at `:1338` from `:12186`. The sell-side decision gate reads `effective_available` at `:11265` and refuses at `:11290`.

The Extractor's participation is written at `extractor_bot.py:318-333` — and it sits inside `set_initial_chunk_rate`, which has no caller. `_crr_token` is always `None`, so:

- the heartbeat at `:1457` is skipped;
- the release at `:493` is skipped;
- no sibling ever sees the Extractor's claim.

**System 3 — `CapitalRegistry`** (`capital_registry.py:111`), the USD broker whose stated purpose is to enforce `sum(reservations) <= wallet_total` across bots. `CapitalRegistry(` appears zero times in `src/`, `main.py`, `tests/`, `tools/`. Its only wiring hook, `BotManager.set_capital_registry` (`bot_container.py:2146`), has zero callers. `bot_container.py:1628` leaves `_capital_registry = None` forever, so `:2185`, `:2237`, `:2274`, `:2350` and `:2498` all short-circuit. The comment at `bot_container.py:1621` says "Wired by main.py via set_capital_registry()". It is not.

**The declared second enforcement layer does not exist.** `capital_reservation.py:30-35` declares defence in depth: decision-level via `effective_available`, execution-level via "order placement (`smart_orders.py`) pre-flights against the registry before submitting to exchange. Catches races between decision and execution." `smart_orders.py` has **zero importers**. Every reference to it in the live tree is a comment (`extractor_bot.py:312`, `:488`; `scrumming_bot.py:11222`, `:11235`, `:11291`). The execution-level layer is prose.

**Root cause of the unwired init.** Both construction sites build the Extractor with a placeholder exchange: `main_window.py:7542-7546` and `bot_container.py:3122-3128` pass `_PlaceholderExchange` / `_PlaceholderExchangeForRestore`. At construction there is no live price, so there is nothing to hand `set_initial_chunk_rate`. The natural later hook is the connector swap — but `bot_container.py:2126-2129` and `:2451-2454` are both guarded by `if not getattr(bot, "exchange", None)`, and `_PlaceholderExchange` (`main_window.py:2754-2758`) is a plain truthy object, so neither guard fires. Only `main_window.py:6697` assigns unconditionally. The other lifecycle hook, `bootstrap_exchange_state`, is dispatched at `bot_container.py:2457` behind `hasattr` — and `ExtractorBot` does not define it. `ScrummingBot` does, at `:4511`.

**The Extractor has no post-connector initialisation hook at all.** That is the mechanical reason the sharing code was written and never reached.

**Two further leaks in the one live system.**

- `prune_expired` (`capital_reservation.py:567`), the documented crash-recovery collector, has zero callers. Five production comment blocks state the opposite as fact: `extractor_bot.py:303-306`, `:486-489`, `:507-512`, `scrumming_bot.py:1340-1341`, `:1358`, plus the module docstring at `capital_reservation.py:40-42`. `reserve()` persists on every mutation (`:338`→`:217`); `heartbeat()` deliberately does not (`:561-565`). A killed process therefore leaves reservations on disk with stale heartbeats; they reload at `:239-253`; nothing removes them. `scrumming_bot.py:1084-1086` records 16,523 orphan reservations as the HISTORICAL cost of a sim bot receiving the live singleton registry. That path is CLOSED: `scrumming_bot.py:1092-1098` now returns `None` in sim mode and refuses to resolve the process-wide registry. Orphans can no longer be mass-produced. A hard process kill can still strand one, and nothing reclaims it.
- An orphan is not inert. `reserve()`'s over-commit guard (`:310-321`) sums **every** reservation on the asset, orphans included, and raises. The v3.24.93 comment at `scrumming_bot.py:1274-1277` records the resulting incident on live money: existing reservations 30.02068843 LINK plus requested 9.984649731, where nothing held 30 LINK under a live token. That incident is FIXED. `scrumming_bot.py:1282-1293` releases the stale token BEFORE the retry, so a retry no longer collides with the bot's own ghost. Both numbers in this bullet are historical records, not current state. And `force_release` / `force_release_all` (`:419`, `:438`) have zero callers, so the recovery path the refusal message points at (`scrumming_bot.py:11277-11278`, "check Settings → Capital Reservations or force_release if a reservation is stale") does not exist. The only capital table in the GUI (`main_window.py:862`) reads the always-`None` other registry.

**Summary of 4a.** Three coordination systems. One is a crash on a single line. One is written but unreachable for the Extractor. One is never constructed. The declared execution-level backstop has no importer. The reclamation path has no caller.

### 4b. Bot stand-down — the specific missing mechanism

The codebase holds no stand-down mechanism. Name the gap precisely.

**What exists is a read, not a hold.** `effective_available(asset, bot_id, total_holdings)` (`capital_reservation.py:464`) returns a **float**. The caller reads it at `scrumming_bot.py:11265`, refuses at `:11270` — and then `:11306` awaits `get_open_orders(...)` before the order is placed. Every `await` is a yield point. Nothing holds a claim across that window. The answer is advisory. Additionally, `_ensure_capital_reservation` awaits `_get_cached_exchange_balance` at `:1157` (60-second TTL, `:1032-1056`) before calling `reserve()` at `:1226`, so the `total_holdings` ceiling can be up to 60 seconds stale.

**Contention resolution is first-come-wins.** `reserve()` (`:307-338`) holds a `threading.Lock` and contains no `await`, so the over-commit sum and the insert are atomic against other coroutines; the process is not single-threaded (`live_bot_window.py:265`, `ccxt_connector.py:492`, `:731` all start threads), but the lock covers that too. The loser gets a `ValueError` from `:315`, which `scrumming_bot.py:1257` swallows. The registry offers no queue, no fairness ordering, no priority, and no preemption. The only ranking code in the repo, `opportunity_arbiter.rank_candidates` (`:259`), has zero callers and is not wired to the registry.

**The four missing primitives, named.**

1. **A lease with an expiry.** Capital is claimed indefinitely. Nothing bounds how long a slice stays deployed. `extractor_bot.py` has no timer, no max-hold, and no stop-loss transition. A sibling waiting on that asset waits forever.
2. **A yield request.** No code path lets bot A ask bot B to release a claim. `release(token, bot_id)` (`:345`) refuses a foreign caller (`:359`). The only override, `force_release`, has no caller and no GUI surface.
3. **A ranking between claims.** Two bots that both want ETH are indistinguishable to the registry. The registry holds no priority field, no bot-kind precedence, no per-bot cap on shared capital.
4. **A hold that survives the decision-to-execution window.** The check and the act are separated by awaits, and nothing is locked between them.

**Consequence for the Extractor specifically.** Even if 4a were fully wired, the Extractor still could not stand down, because a stand-down needs something to stand down *from* — a claim that another bot can observe, contest and reclaim. The Extractor files no claim. Its participation in the only working system is one unreachable call.

**Design note.** The design never specified stand-down. DESIGN:564-599 specifies claim **subtraction** plus refuse-to-fire. That is a weaker and simpler contract, and it is the right one to build first. Stand-down as commonly imagined — a negotiation protocol between bots — is not in the design and, per §5.3 below, is not how production systems solve this either.

---

## 5. Comparative implementations

Every system below was fetched from source. URLs are the ones actually retrieved. Sources that returned HTTP 403 or failed to parse carry no claims here: Gate, Gainium, BitMEX, Deribit, the IWU paper, and arXiv 1508.05241. I make no claim about the BitMEX or Deribit inverse-contract formulas.

**The dominant result across the sample.** No system found lets two independent strategy processes dynamically share one balance pool. Every system picks one of two designs: **static partition** (each strategy gets a fixed slice and never sees the rest) or **single-owner ledger** (one component owns all balance state and every order passes through it). The sample offers no third option. That bears directly on the operator statement: two writers on one balance is the defect, and no lock inside `extractor_bot.py` can fix it.

### 5.1 Per-cycle collateral lock — Hummingbot `BudgetChecker`

State is one dict: `_locked_collateral: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))`, keyed by token. `adjust_candidate(order_candidate, all_or_none)` calls `populate_collateral_entries()`, which fills `order_collateral`, `percent_fee_collateral`, `fixed_fee_collaterals` and `potential_returns` on the candidate; `collateral_dict` sums the legs per token. `_get_available_balances()` returns `balance_fn(token) - self._locked_collateral[token]`. `OrderCandidate.adjust_from_balances()` computes `scaler = available_balances[token] / amount` and calls `_scale_order(scaler)`, which multiplies **every** leg so the legs stay consistent. With `all_or_none=True` the order is zeroed rather than shrunk. `adjust_candidate_and_lock_available_collateral()` then runs `_lock_available_collateral()`, which does `self._locked_collateral[token] += amount` per token, so the next candidate sees less.

Two design points matter more than the code. The lock is **per cycle, not per session** — the docstring states the collateral stays unavailable "until the `reset_locked_collateral` method is called". And there is exactly **one arbiter**: the checker lives at the connector layer, below every strategy, so all strategies on that connector pass through the same object.

Failure mode, stated plainly: the lock is incremental. A missed reset starves the bot. An early reset double-spends. The lock never crosses process or connector boundaries. `potential_returns` is informational — a sell that will fund a buy does not release collateral until it fills.

Source: https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/connector/budget_checker.py

**Applicability to Acervator.** This is the missing primitive for 4a, and it is a closer fit than `CapitalRegistry` because it operates per proposal cycle against a live balance rather than granting an amount once. Acervator's `request_reservation` is **not** a one-shot grant — its docstring at `capital_registry.py:210-211` treats a repeat request as an UPDATE, and `grow_reservation` (`:287`) and `update_reservation` (`:354`) exist — but it is still admission control, not per-order arbitration. Adopt the `all_or_none=True` semantics for artillery rounds: a partially funded slice is worse than no slice, because the pool then carries an odd-lot obligation to unwind.

### 5.2 Derived lock, not incremental — NautilusTrader `AccountsManager`

Nautilus rebuilds the locked map from the open-order list on every update rather than incrementing a counter. It clears the lock when that list is empty (`if not orders_open: account.clear_balance_locked(instrument.id)`) and clears again when the rebuilt total is empty. The method is private: `_update_balance_locked`.

Source: github.com/nautechsystems/nautilus_trader — `nautilus_trader/accounting/manager.pyx` (master).

**Applicability to Acervator.** This is the decisive design choice, and it points away from Hummingbot's shape. A derived lock cannot drift. An incremental lock always can — and Acervator has already paid for that: 16,523 orphan reservations (`scrumming_bot.py:1084-1086`) are exactly what an incremental ledger with a missing decrement produces. Build the Extractor's claim as a **derived** value recomputed from open positions each tick, not as a counter that `reserve()` increments and `release()` must remember to decrement. That change alone removes the need for `prune_expired`, `force_release`, and the boot-time staleness filter that `capital_reservation.py:44-49` promises and `__init__` (`:211`) does not perform.

### 5.3 Hard one-sided suppression — Guéant, Lehalle, Fernandez-Tapia

The paper adds a hard inventory bound Q to Avellaneda-Stoikov and states the rule verbatim: a market maker with inventory Q "will never set a bid quote", and one with inventory −Q "will never set an ask quote". This is structural, not a resize. The HJB system is indexed by q ∈ {−Q…Q}; the row for q = Q contains only the ask term. The bid side does not exist at the bound: `v̇_Q(t) = αQ²v_Q(t) − ηv_{Q−1}(t)`, a single neighbour term. Theorem 1 gives `δ_b*(t,q) = (1/k)·ln(v_q(t)/v_{q+1}(t)) + (1/γ)·ln(1+γ/k)` for q ≠ Q, from a **linear** ODE system — no PDE solver. Propositions 1 and 2 state `α = (k/2)·γ·σ²` and `η = A·(1+γ/k)^−(1+k/γ)`.

Source: https://arxiv.org/pdf/1105.3115

**Applicability to Acervator.** This is the only true stand-down mechanism in the literature I read, and it needs **no inter-bot negotiation and no message passing**. Each agent's own bound removes its own side. That is what the operator's failed "bot inoperability protocols" were reaching for, and it is cheaper than what was attempted. Define a hard bound on pool units deployed. At the bound, do not construct the buy leg at all — do not emit a resized one. At zero deployed, do not construct the sell leg.

### 5.4 Soft size skew that reaches exactly zero — Hummingbot inventory skew

`calculate_bid_ask_ratios_from_base_asset_ratio(base_asset_amount, quote_asset_amount, price, target_base_asset_ratio, base_asset_range)`. In the body: `base_asset_range_value = min(base_asset_range * price, total_portfolio_value * 0.5)` — the range is capped at half the portfolio. `np.interp` maps the position into `[0,0.5]` below target and `[0.5,1]` above. Then `bid_adjustment = interp(...)` and `ask_adjustment = 2.0 - bid_adjustment`.

Three properties. At target both multipliers are 1.0. At the top of the range `bid_adjustment` is exactly **0.0** — buying stops by arithmetic, with no flag and no branch. The pair always sums to 2.0, so total quoted size is conserved while only the direction moves. Guard: if the portfolio value or range is ≤ 0 it returns `(0.0, 0.0)` and quotes nothing.

The band is expressed in multiples of the bot's own order size, not as a fixed percentage: `c_apply_inventory_skew` passes `total_order_size * inventory_range_multiplier` as `base_asset_range`. Documented example: portfolio 10 BTC, order size 1 BTC, target 50%; multiplier 1.0 gives a 40–60% band, 2.0 gives 30–70%. Defaults: `inventory_skew_enabled` False, `inventory_target_base_pct` 50, `inventory_range_multiplier` 1.

Sources: https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/strategy/pure_market_making/inventory_skew_calculator.pyx and https://hummingbot.org/strategies/v1-strategies/strategy-configs/inventory-skew/

Related, from the underlying theory: Avellaneda-Stoikov equation (8) is `r(s,q,t) = s − qγσ²(T−t)`, arrival intensity is `λ(δ) = A·exp(−kδ)` (eq. 12), terminal condition `u(s,x,q,T) = −exp(−γ(x+qs))`. Their 1000-run simulation (s=100, T=1, σ=2, γ=0.1, k=1.5, A=140) gives inventory strategy profit 65.0 with **std** 6.6 and final q 0.08 with std 2.9, against symmetric profit 68.4 with std 12.7 and final q 0.26 with std 8.4. Read against itself: skewing costs 4.97% of mean profit and buys a 1.92× cut in profit **standard deviation** (3.7× in variance) and a 2.9× cut in final-inventory dispersion. It is a variance trade, not a profit trade. Note the limit: price skew only biases arrival rates. It cannot refuse a fill. Source: https://www.math.nyu.edu/~avellane/HighFrequencyTrading.pdf

**Applicability to Acervator.** `_has_chunk_capacity` (`extractor_bot.py:531-534`) is a single boolean cliff against a fixed reserve percentage. It has no graded region. Port the ratio function with pool semantics: deployed-into-alts against target deployment, band width in multiples of `artillery_size`. Multiply every slice size by the deploy ratio. Use it as the **soft layer under** the hard bound of §5.3, not instead of it.

### 5.5 Static partition — Freqtrade `available_capital`

`stake_currency` is "Required. Crypto-currency used for trading" and must be the quote side of every pair. `stake_amount` is "Amount of crypto-currency your bot will use for each trade". Fiat is quarantined into a display-only field: `fiat_display_currency`, "Fiat currency used to show your profits". Backtest reporting follows the same split — "Absolute profit: Profit made in stake currency". For contention: `available_capital` is "Available starting capital for the bot. Useful when running multiple bots on the same exchange account", and it **replaces** `tradable_balance_ratio`, which the docs caution against when operating multiple bots.

Honest limit, verified: the advanced-setup page covers only separate databases, Telegram bots and ports for multiple instances. It does not mention `available_capital` and does not document safe sharing of one exchange account. Freqtrade documents the knob, not the discipline.

Sources: https://www.freqtrade.io/en/stable/configuration/ , https://www.freqtrade.io/en/stable/backtesting/ , https://www.freqtrade.io/en/stable/advanced-setup/

**Applicability to Acervator.** This is the cheap answer and it deserves serious consideration as the shipped one. The Extractor's chunk is already a static partition — `_chunk_size_base` is operator-allocated and never auto-resized (DESIGN:180-181). What is missing is not a smarter allocator; it is (a) making the partition **visible** to siblings, and (b) forbidding any bot from sizing against raw exchange free. Freqtrade's fiat quarantine also maps directly onto Acervator's double-layer valuation rule: USD is a display and risk lens only.

### 5.6 Capital as a lease with a forced expiry — Hummingbot V2 and Aave V3

Hummingbot `PositionExecutorConfig` requires a scalar `amount` and carries a `TripleBarrierConfig` with `stop_loss`, `time_limit`, `take_profit` and `trailing_stop`. `open_order_type` defaults to LIMIT; `take_profit_order_type`, `stop_loss_order_type` and `time_limit_order_type` all default to **MARKET**. `ExecutorOrchestrator` keeps `active_executors`, `positions_held` and `cached_performance` keyed by controller id; `stop_executor()` calls `executor.early_stop()`; shutdown runs `force_stop_with_position_hold()`, converting remaining exposure into tracked `PositionHold` objects so nothing goes untracked. HYPOTHESIS (verified as such): the orchestrator layer performs no capital admission control, leaving contention entirely to the connector `BudgetChecker`.

Source: https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/strategy_v2/executors/position_executor/data_types.py

Aave V3 flash loans enforce the same idea by settlement. The pool transfers funds and calls `executeOperation()`. Before it returns, the receiver must approve the pool for amount + premium; the pool **pulls** the funds. If the approval or balance is absent, the transaction reverts. `FLASHLOAN_PREMIUM_TOTAL` is initialised at 0.05%.

Source: https://aave.com/docs/aave-v3/guides/flash-loans

**Applicability to Acervator.** This converts pool contention from a **lock** problem into a **lease** problem, which is the single highest-value structural change available. A sibling's wait becomes bounded instead of open-ended. It also fixes divergence #7 in §2 — a position stuck in DRAWDOWN currently has no exit at all. Give every artillery round a `time_limit` whose exit order type is MARKET, plus an `early_stop()` and a force-stop path that converts residual exposure into a tracked obligation, so shutdown never leaves untracked units in an alt. From Aave, take the obligation ledger: record `required_return = slice_out_base × (1 + premium)` at pull time, and treat a round that closes below it as an **open obligation**, not a profit event.

### 5.7 Base-denominated accounting and a share price — EIP-4626, Lido, Yearn

EIP-4626 abstract, verbatim: "The following standard allows for the implementation of a standard API for tokenized Vaults representing shares of a single underlying EIP-20 token." Asset = "The underlying token managed by the Vault." `totalAssets` = "Total amount of the underlying asset that is 'managed' by Vault. SHOULD include any compounding that occurs from yield." Deposits and withdrawals move both assets and shares, so the ratio is invariant to flows — the metric cannot be flattered by adding capital. The Security Considerations mandate a rounding direction: round **down** when issuing shares or transferring assets to users, round **up** when calculating what users owe.
Source: https://eips.ethereum.org/EIPS/eip-4626

Lido publishes the growth rate from a share-rate delta: `preShareRate = preTotalEther * 1e27 / preTotalShares`, `postShareRate = postTotalEther * 1e27 / postTotalShares`, `userAPR = secondsInYear * ((postShareRate - preShareRate) / preShareRate) / timeElapsed`. The share rate changes only on a rebase event, which makes the metric event-anchored rather than tick-noisy. Fee: "the fee collected by Lido protocol is 10% of staking rewards".
Sources: https://docs.lido.fi/integrations/api/ , https://docs.lido.fi/guides/lido-tokens-integration-guide

Yearn states the user-facing form: yVault tokens are "like a deposit receipt"; "If your yVault generates profit, the share price of your yVault tokens will increase"; "This happens because there are more underlying tokens in the yVault to redeem upon withdrawal."
Source: https://raw.githubusercontent.com/yearn/yearn-docs/master/yearn-finance/yvaults/vault-tokens.md

Hummingbot's `InventoryCostPriceDelegate` is the trading-bot equivalent of a cost-basis floor. `get_price()` returns `record.quote_volume / record.base_volume`, a persisted VWAP. On a **sell** it does not use the sale price: it removes `quote_volume = -(record.quote_volume/record.base_volume) * base_volume` at the **original** ratio. The in-source comment states the intent — profits are deliberately not allowed to change the inventory price. It hard-fails on an unbacked sell with `RuntimeError("Sold asset without having inventory price set. This should not happen.")`.
Source: https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/strategy/pure_market_making/inventory_cost_price_delegate.py

Academic status: Borri, Liu, Tsyvinski and Wu note in the Data section, verbatim, "We note that alternative numeraire or crypto-to-crypto return measures may reveal additional dimensions that are not captured by USD-based trades", continuing "…which is a potentially important direction for future research." That is the only occurrence of the word *numeraire* in the paper.
Source: https://arxiv.org/html/2510.14435v4

**Applicability to Acervator.** Replace `_chunk_extracted_total` as the headline number with `base_per_share = total_pool_value_in_base / shares_outstanding`, minting shares on operator deposit and burning on withdrawal. Deposits and withdrawals then cannot move the metric — which is the exact failure mode of a raw cumulative counter. Compute the growth rate from a share-rate delta on **cycle-close events only**, not per tick. Apply the EIP-4626 rounding rule literally. From Hummingbot, port the cost-basis floor: it turns "the pool must come back whole plus a gain" from an intent into a computed floor price that the sell gate can compare against, and it is a stronger form of `_exit_is_profitable_in_base`.

**One correction to a claim I will not repeat.** It is *not* generally true that "beat buy-and-hold in USD" and "grew base unit count" are the same test. The identity holds only when the strategy holds 100% base at both endpoints and takes no deposits or withdrawals. The Extractor holds open alt positions by design — `pool_color()` returns "yellow" or "red" precisely when `_positions` is non-empty (`extractor_bot.py:538-551`). That is the exact case where the two tests diverge, because the USD test marks the whole mixed basket while the unit-count test counts only base units. The Extractor therefore needs a **stated marking convention** for open positions, not an assumed equivalence.

### 5.8 The null model the Extractor must beat — Uniswap v2

The Extractor's cycle — buy the alt on a dip, sell on a rally, return more base — is the discrete form of a constant-product rebalance. Uniswap documents the closed form: `eth_liquidity_pool = sqrt(constant_product / eth_price)` and `token_liquidity_pool = sqrt(constant_product * eth_price)`. Read with ETH as numeraire on an ALT/ETH pair, the ETH count grows as sqrt(alt price in ETH): it rises on an alt rally and falls on an alt dump.

The worked example is the point. An LP supplies 1 ETH + 100 DAI into a 100 ETH / 10,000 DAI pool at 1 ETH = 100 DAI. Price moves to 120. The LP claims "0.9129 ETH and 109.54 DAI", worth 219.09 DAI against 220 DAI held — a 0.91 DAI shortfall. Aigner and Dhaliwal formalise this for the semi-infinite domain.

Sources: http://developers.uniswap.org/llms.mdx/docs/protocols/v2/concepts/understanding-returns and https://arxiv.org/abs/2106.14404

Balancer generalises it so only a chosen weight of the pool is exposed to the volatile leg: `aO = bO * (1 - (bI/(bI+aI))^(wI/wO))`. A low weight on the alt leg caps exposure and flattens the base-count drawdown while keeping the same sell-rally / buy-dip sign, with the weight as a single auditable knob.
Source: https://raw.githubusercontent.com/balancer/balancer-v2-monorepo/master/pkg/pool-weighted/contracts/WeightedMath.sol

**Applicability to Acervator — and a warning.** HYPOTHESIS, and it must be tested before the redesign is committed: a slice-based Extractor that crosses the spread as a taker approximates the same rebalancing rule, inherits the same sign, and has a **negative** expected base-unit edge after fees in a random walk. The AMM result is a theorem for the continuous constant-product rule only; it does not automatically transfer to arbitrary discrete trigger rules. Build the curve as the Simulator's **positive control**: replay a tablet through both the Extractor and `base_count = sqrt(k · alt_price_in_base)` on identical candles. If the Extractor cannot beat the curve after fees, its trigger logic adds nothing over a passive rebalance. Report drawdown against **holding base**, not against zero.

This also reframes the one empirical result in the design set. BLEED:16-24 reports an Inverted Extractor at 1%/1% thresholds recovering +19.21% (AVAX 2022) and +19.02% (SOL 2022) versus passive hold, with near-zero offset on smooth BTC/ETH bleeds; 5%/3% fires almost nothing and 0.5%/0.5% loses to the 0.6% per-fill fee (BLEED:87-94). The doc states its own limit at BLEED:72 — the measurements came from "SwingHarvester v0 … a minimal reference, NOT the production extractor_bot.py". Those are **not** production-Extractor numbers. The same doc retracts the Scrumming "$214M total advantage" as "a scaling-behavior metric on synthetic stress-test tape, not realistic dollar P&L" against realistic per-cell Extractor numbers of $1–$20 (BLEED:37-44).

---

## 6. Refined concept

### 6.1 What changes and what does not

**Keep.** The anchor model (pool of base, metric is base units). The four-state per-pair machine. The double-layer valuation split — risk in USD, success in base. The chunk as the accounting unit. One position per pair. No cross-base mixing. Positions temporary by design, so no Circuit Breakers (DESIGN:27).

**Drop.**

- **The compounding tier.** It has never executed (§2 row 5). Its justifying example is arithmetically self-refuting (§2). Remove the config field, the branch, and the two log kinds. Do not implement ROLL. If compounding is wanted later, it returns as a separate, tested feature with its own worked example.
- **The frozen-rate design.** C4 is unresolvable as written. Resolve it by the third option: neither freeze nor per-tick refresh, but **explicit re-anchor on a named event** (see I2).
- **MODE A / MODE B duality.** Contradiction C1 shipped as two code paths with different ordering semantics. Pick one. Recommendation: MODE B only, operator selection becomes a *filter* applied to the volume ranking rather than a replacement for it.

**Add.** A lease. A derived claim. A cost-basis floor. An observability surface.

### 6.2 The invariants, with enforcement and observation

Acervator's standard: every claim needs an emitter that can falsify it at runtime. **Today the Extractor emits exactly one topic — `bot.log` — at all fourteen emit sites (`extractor_bot.py:1006, 1026, 1064, 1126, 1137, 1147, 1171, 1226, 1328, 1368, 1387, 1427, 1487, 1526`).** It never emits `trade.filled`, never emits `bot.gate_decision`, never emits `pnl.event`. `ScrummingBot` emits `trade.filled` 24 times. `guarded_place_order` (`bot_container.py:996-1144`) emits nothing. The Extractor makes no historian call and no gate-log call. It is invisible to every structured consumer in the system, and `emit_contracts.py:110-137` declares contracts for four topics, none of them the Extractor's.

Every invariant below therefore ships with a **new** declared contract in `src/core/emit_contracts.py`, not a log line.

| ID | Invariant | ENFORCED by | OBSERVED by (emitter) |
|---|---|---|---|
| **I1** | `chunk_free + Σ cost_basis(open) == chunk_size + chunk_extracted_total`, to 1e-9 base units | A `_check_chunk_invariant()` call at the end of every mutating path: `_fire_artillery`, `_maybe_fire_correction`, `_execute_bullish_exit`, `import_state`. On violation it raises. | New topic `extractor.ledger`, required `("chunk_free","chunk_size","cost_basis_sum","extracted_total","residual")`. Emitted every tick. A non-zero `residual` is the falsifier. |
| **I2** | The USD↔base rate is never the unset default when an order is sized | `_usd_to_base` raises `ExtractorNotAnchored` when `_rate_anchored_at is None`. The `1.0` default (`:160`) is replaced by `None`. `_fire_artillery` and `_maybe_fire_correction` refuse before placing. | New topic `extractor.anchor`, required `("rate","source","anchored_at")` where `source ∈ {"connector_attach","state_restore","rate_refresh"}`. Never emitted ⇒ the bot never anchored. This is the single emitter that would have caught the top defect in §2. |
| **I3** | Every order amount is a base-asset quantity derived from an anchored rate | One helper, `_size_artillery_base()`, is the only producer of an order amount. It returns a `(units, rate_used, rate_age_s)` triple. Direct arithmetic at the call site is removed. | `extractor.order_sized`, required `("pair","side","units","rate_used","rate_age_s","usd_equivalent")`. A `usd_equivalent` two orders of magnitude off the configured artillery size falsifies I2 and I3 together. |
| **I4** | The bot's claim on the base asset is **derived**, never incremented | `claimed_base()` returns `chunk_size_base` recomputed from config plus open positions each call. `reserve()` is replaced by an idempotent `set_claim(bot_id, asset, qty)` that overwrites. No decrement exists to forget. | `extractor.claim`, required `("asset","claimed_base","deployed_base","free_base","token")`. Emitted per tick. Cross-check against `CapitalReservationRegistry` state; a divergence falsifies the derivation. |
| **I5** | No bot sizes against raw exchange free on a shared base | A single module-level function `free_for_bot(bot_id, exchange_id, currency)` is the only reader of `get_balance(currency).free` in the trading layer. Both `ScrummingBot` and `ExtractorBot` call it. The direct read at `scrumming_bot.py:6248` is replaced. `free_for_bot` returns `raw - Σ sibling claims`, and **refuses to fire** on a negative result — it never sells to recover (DESIGN:595). | `capital.free_for_bot`, required `("bot_id","currency","raw_free","sibling_claims","free_for_me","refused")`. A `refused=True` run is the over-allocation signal, throttled, not silent. |
| **I6** | A slice returns to the pool within a bounded time | Every `ExtractorPosition` carries `lease_expires_at`. `_evaluate_open_position` checks it **before** the drawdown branch, so a DRAWDOWN position can still exit (fixes §2 row 7). Expiry fires a MARKET close regardless of signal. | `extractor.lease`, required `("pair","opened_at","expires_at","action")` with `action ∈ {"opened","renewed","expired_closed"}`. A pair with no `expired_closed` and no exit for longer than the lease falsifies I6. |
| **I7** | A round closes at or above its base-unit obligation, or it is recorded as an open obligation | At firing, record `required_return_base = cost_basis_base × (1 + fee_pct/100)`. `_exit_is_profitable_in_base` compares against that, not against bare cost basis. A lease-expiry close below it writes an `obligation` record instead of a gain. | `extractor.round_closed`, required `("pair","cost_basis_base","required_return_base","base_received","gain_base","obligation_base","reason")`. `Σ obligation_base > 0` with `chunk_extracted_total > 0` is the falsifier for "the pool grew". |
| **I8** | Position records and exchange holdings do not diverge | Exit destroys the position **only** when `alt_units < 1e-12` — the `or extractor_exit_pct >= 100.0` clause at `:1306` is deleted. `import_state` failure raises into `bot_container.py:3238-3240` instead of `continue` at `:1693`. Cost-basis proportion is computed from `filled_units / alt_units_before`, not from config (fixes §2 row 11). | `extractor.reconcile`, required `("pair","units_recorded","units_verified","delta")`, emitted from the `verified_units` that both `buy_safety` call sites currently discard. A non-zero `delta` is the orphan detector. |
| **I9** | A signal failure is loud | The four `logger.debug` calls in `ta_signal_provider.evaluate()` become `logger.warning`. The consumer's bare `continue`s at `extractor_bot.py:1473-1475` and `:1497-1499` gain a counter. The S112 sites at `:666` and `:1479` gain a per-pair failure counter that escalates after N. | `extractor.signal_gap`, required `("pair","stage","consecutive")`. `consecutive` rising monotonically is the dark-TA detector. Silence from this emitter with zero trades is the current unfalsifiable state. |
| **I10** | Deposits and withdrawals cannot flatter the growth metric | The headline number becomes `base_per_share = pool_value_base / shares_outstanding`. Operator deposit mints shares; withdrawal burns them. Rounding follows EIP-4626: down when issuing shares or paying out, up when computing what the pool is owed. | `extractor.share_rate`, required `("pre_rate","post_rate","elapsed_s","apr")`, emitted **only on round close**, computed by the Lido formula. A rate that moves on a deposit falsifies I10. |

### 6.3 Deployment control — replacing the boolean cliff

Three layers, in the order they run, replacing `_has_chunk_capacity`:

1. **Hard bound (§5.3).** `deployed_base >= deployment_bound_base` ⇒ the entry leg is not constructed. Not resized. Not emitted. This is the stand-down primitive: it needs no negotiation, and it is per-bot.
2. **Soft skew (§5.4).** Inside the band, multiply the slice size by `deploy_ratio`, computed from the gap between deployed and target with a band width in multiples of `artillery_size`. At the top of the band the ratio is exactly 0.0. Ship it disabled by default, as Hummingbot does.
3. **All-or-none funding (§5.1).** If the skewed slice cannot be funded in full from `free_for_bot`, fire nothing. A partial slice is worse than no slice.

The existing reserve-against-`chunk_size` rule (`:520-523`) survives as the floor under layer 1. Its rationale is sound and should be quoted in the new docstring.

### 6.4 Position on the Inverted variant

Defer it. The mode is dimensionally inconsistent in both sizing and proceeds (§2 row 21), the confidence there is **likely** rather than verified, and the one empirical result that motivates it came from `SwingHarvester v0`, not this code (BLEED:72). Reactivate only after Stage 5 below, and gate it behind its own dimensional-analysis test.

---

## 7. Development plan

Legend: **[BLOCKED]** = depends on the architectural work in Stage 3. **[PARALLEL]** = can run alongside it.

Every stage's test carries a **positive control** — a paired case that fails if the check goes blind. A check with no positive control is a claim about the instrument, not the world.

---

### Stage 0 — The test file that does not exist [PARALLEL]

**Ships.** `tests/test_extractor_bot.py`. It has never existed in the live tree; the module docstring at `extractor_bot.py:129-131` asserts that it does and that it enforces an invariant.

**Files touched.** New: `tests/test_extractor_bot.py`. Modified: `extractor_bot.py:28-29, 129-131, 1284` (repoint the four dead doc paths at `_archive/…` and delete the false sentence about the test).

**Test + positive control.**
- Assert I1 on a hand-built bot after: construction, one artillery fire, one correction, one full exit, one partial exit, and an export/import round-trip.
- **Positive control:** a paired case that mutates `_chunk_free_base` by +1e-6 outside a money path and asserts the invariant check **raises**. If that case passes, the invariant check is blind and the whole file is worthless.
- Second control: assert `test_extractor_bot.py` exists from within itself, so the docstring claim at `:130` becomes self-verifying.

**Emitter.** `extractor.ledger` (I1), asserted in-test on a stub bus.

**Exit criterion.** `python -m tools.harness.check_release_readiness` runs on an island copy with the new file present, and the invariant test fails on the paired mutation case and passes on the clean case.

---

### Stage 1 — Make the file honest [PARALLEL]

**Ships.** The lint-class REAL findings from §3, and nothing else.

**Files touched.** `extractor_bot.py` only: delete the five dead imports (`:56, :59, :62, :63, :64`) and the two local re-imports (`:777, :783`); remove `enable_phantoms` (`:140`) and update both call sites (`main_window.py:7545`, `bot_container.py:3126`); convert the assert at `:142` to `raise ValueError`; remove `cost_basis_before` (`:1157`) and the unused `snapshot` parameter (`:1337`); add a `# noqa` for vulture on `:69` — **do not delete that import**.

**Test + positive control.** Re-run `coding_archetype`. Compare against the **baseline of 156 findings / 13 high**, not against zero.
- **Positive control:** re-run the archetype on the unmodified island copy in the same session and confirm it still returns 156. If both runs return the same number, the tool did not see the edit and the comparison is void.

**Emitter.** None. This stage moves no money.

**Exit criterion.** `coding_archetype` high count drops from 13 to 3 (the three REAL S112 sites, which Stage 2 handles). `ruff --select S112,F401,F841,S101,ARG002` drops from 14 findings to 5.

---

### Stage 2 — Close the silent swallows [PARALLEL]

**Ships.** The three REAL S112 fixes, ranked by the capital they can lose.

**Files touched.** `extractor_bot.py:1668-1694` (import_state: log at error and **raise**, so `bot_container.py:3238-3240` handles it); `:1476-1480` (open-position ticker: log at warning, count consecutive failures per pair, escalate after N); `:658-672` (watch-list scan: count per-symbol failures, log once per refresh with the count); `:607-616` and `:644-656` (log at debug — cosmetic, but they currently misattribute a parse failure to a delisting at `:626-629`).

**Test + positive control.**
- Feed `import_state` a position dict missing `pair`. Assert it raises and that `bot_container`'s handler fires.
- **Positive control:** feed it a well-formed dict and assert it does **not** raise and the position lands in `_positions`. Without this pair, a fix that raises on everything passes the first case.
- Stub an exchange whose `get_ticker` raises for one pair only. Assert the warning fires and the counter increments; assert the *other* pair still evaluates.

**Emitter.** `extractor.signal_gap` (I9). Its `consecutive` field is the falsifier.

**Exit criterion.** Zero S112 findings on `extractor_bot.py`. The import-failure test fails when the `raise` is reverted to `continue`.

---

### Stage 3 — The architectural work: anchor, claim, and one arbiter

This is the blocker. Nothing downstream of it is meaningful.

**3a. Give the Extractor a lifecycle hook.**

**Ships.** `ExtractorBot.bootstrap_exchange_state()`, matching the `ScrummingBot` contract at `scrumming_bot.py:4511`. It fetches the live base/USD rate, calls the anchoring path, files the derived claim, and emits `extractor.anchor`.

**Files touched.** `extractor_bot.py` (new method; `_chunk_to_base_rate` default at `:160` becomes `None`; `_usd_to_base` at `:695-699` raises when unanchored). `bot_container.py:2457` already dispatches on `hasattr(bot, "bootstrap_exchange_state")` — adding the method is sufficient there. Also fix `bot_container.py:2126-2129` and `:2451-2454`, whose `if not getattr(bot, "exchange", None)` guards never fire because `_PlaceholderExchange` (`main_window.py:2754-2758`) is truthy: test for the placeholder class, not for falsiness.

**Test + positive control.**
- Construct an Extractor through `bot_container`'s restore path with a stub connector. Assert `extractor.anchor` fires exactly once, with `source="connector_attach"`, and that `_fire_artillery` refuses before it.
- **Positive control:** construct one and **skip** the bootstrap. Assert `_fire_artillery` raises `ExtractorNotAnchored` and places no order. Without this case, a bootstrap that silently no-ops still passes.
- Sizing case: with base=ETH, rate anchored at a stub 3000, assert a $5 artillery round produces ~0.001667 ETH. Paired case: with base=USDC, rate 1.0, assert it produces 5.0 units. The pair is what distinguishes a real conversion from an identity.

**Emitter.** `extractor.anchor` (I2), `extractor.order_sized` (I3).

**Exit criterion.** No order can be sized without an `extractor.anchor` emission preceding it in the same session, proven by a bus-replay assertion.

**3b. Fix the sibling-claim crash and collapse the two half-arbiters.**

**Ships.** `free_for_bot(bot_id, exchange_id, currency)` as the single reader of shared base free, per I5. Both bot classes call it.

**Files touched.** `scrumming_bot.py:6252` (replace the call to the non-existent `self._sum_sibling_base_currency_claims`); `bot_container.py:2608` (`sum_sibling_base_currency_claims` becomes the implementation behind `free_for_bot`); `extractor_bot.py:517-534` (the docstring at `:525-530` — "Sibling claims are NOT subtracted from chunk_size_base here … Operator over-allocation surfaces at the ScrummingBot side, not here" — is the asymmetry, in writing; delete it and route through the shared helper).

**Test + positive control.**
- Two-bot fixture: one ScrummingBot and one ExtractorBot on the same ETH base. Assert the ScrummingBot's `free_for_me` equals raw free minus the Extractor's `_chunk_size_base`.
- **Positive control:** a single-bot fixture where `free_for_me == raw_free`. If both fixtures return the same number, the subtraction is not running.
- Regression control: assert that reaching the initial-entry path does **not** raise `AttributeError`. Today it always does.
- Negative-balance case: assert the bot refuses to fire FOLD-side and does **not** attempt a recovery sell (DESIGN:595).

**Emitter.** `capital.free_for_bot` (I5).

**Exit criterion.** The AttributeError regression test passes. A ScrummingBot on the initial-entry path with a sibling Extractor completes its tick without entering `BotState.ERROR`.

**3c. Make the claim derived, not incremental.**

**Ships.** `set_claim()` replacing `reserve()` for the Extractor path. Idempotent overwrite. No decrement to forget.

**Files touched.** `capital_reservation.py` (add the idempotent setter alongside the existing API; do not remove `reserve()` while ScrummingBot uses it). `extractor_bot.py:318-333` (move the claim out of `set_initial_chunk_rate` and into the per-tick derivation).

**Test + positive control.**
- Call `set_claim` 100 times with the same quantity. Assert the registry holds exactly one entry and the over-commit sum does not grow.
- **Positive control:** call it 100 times with **increasing** quantities and assert the stored value tracks the last call. Without this, a setter that ignores its argument passes the first case.
- Orphan case: kill and restore a bot. Assert the derived claim after restore equals the derived claim before, with no residue. Today the equivalent path produced 16,523 orphans (`scrumming_bot.py:1084-1086`).

**Emitter.** `extractor.claim` (I4), cross-checked against registry state.

**Exit criterion.** A kill-restore cycle leaves the reservation count unchanged. `prune_expired` becomes unnecessary for the Extractor path — flag it, do not delete it, because ScrummingBot still needs it and it still has no caller.

---

### Stage 4 — Capital as a lease [BLOCKED by 3]

**Ships.** `lease_expires_at` on every position. A MARKET close on expiry. The DRAWDOWN exit path unblocked.

**Files touched.** `extractor_bot.py:937-949` (check the lease **before** the drawdown branch, so the early `return` at `:939` no longer traps the position); `:1413` (set the lease at fire time); new expiry handler.

**Test + positive control.**
- Drive a position into DRAWDOWN, hold it there past the lease, assert a MARKET close fires and `extractor.lease` emits `action="expired_closed"`.
- **Positive control:** the same fixture with the lease not yet expired. Assert no close fires. A handler that closes everything passes the first case alone.
- Assert a DRAWDOWN position with a **bullish** signal and an unexpired lease still does not exit — that is current, intended behaviour per the design, and the test pins whether the operator wants it changed (see §8).

**Emitter.** `extractor.lease` (I6).

**Exit criterion.** No position can remain open longer than `lease_seconds + one tick`, proven by a 10,000-tick simulator replay with no exit signals.

---

### Stage 5 — The obligation ledger and the exit-accounting fixes [BLOCKED by 3]

**Ships.** I7 and I8. The cost-basis proportion fix, the `:1306` clause deletion, the `verified_units` reconciliation, and the required-return floor.

**Files touched.** `extractor_bot.py:1245-1253` (proportion from `filled_units / alt_units_before`); `:1306` (delete `or self.config.extractor_exit_pct >= 100.0`); `:1163-1180` (`manual_fire_position` mutates shared config across an `await` — pass an explicit exit fraction instead of writing `self.config`); `:1000` and `:1362` (consume `verified_units`); `:896-917` (compare against `required_return_base`); `buy_safety.py:138-157` (read `Balance.absent`, which its own docstring at `:91-93` names and the body ignores; treat absent as a refusal); `extractor_bot.py:1364` (pass the recorded `alt_units`, not hardcoded `0.0`, so the MEM-257 refuse branch becomes reachable).

**Test + positive control.**
- Partial-fill fixture: sell 100% intent, 60% filled. Assert the position survives, `cost_basis_base` drops by 60%, and `gain_base` reflects the actual fill.
- **Positive control:** full-fill fixture. Assert the position is destroyed and `cost_basis_base` reaches zero. Without the pair, a fix that never destroys positions passes.
- `buy_safety`: table-driven over all five documented branches plus `absent=True`. **Positive control** on each refusal: a paired non-refusal case with the same shape but one field changed.
- `manual_fire_position`: two concurrent coroutines on one bot, one manual-firing a 100% close while the other evaluates a configured 40% exit. Assert the second still exits 40%.

**Emitter.** `extractor.round_closed` (I7), `extractor.reconcile` (I8).

**Exit criterion.** `Σ obligation_base` is reported alongside `chunk_extracted_total` in `get_status()` (`:1601-1602`), and a simulator run that closes rounds below their required return reports a non-zero obligation rather than a gain.

---

### Stage 6 — Deployment control [BLOCKED by 3, PARALLEL with 4 and 5]

**Ships.** The three-layer replacement for `_has_chunk_capacity` (§6.3).

**Files touched.** `extractor_bot.py:517-534`; new config fields in `bot_container.py` near `:426-453`; `bot_live_settings.py` and `bot_wizard.py` for the new knobs. Also fix the silent clamp at `:670-671`: validate `extractor_scan_top_n` in `BotConfig.validate()` and refuse an out-of-range value, or log the clamp once.

**Test + positive control.**
- At the hard bound, assert **no order object is constructed** — not that a zero-size order is rejected downstream. Instrument the order factory.
- **Positive control:** one unit below the bound, assert an order **is** constructed. A gate that never constructs anything passes the first case.
- Skew table: assert the deploy ratio is 1.0 at target, exactly 0.0 at the top of the band, and that deploy + recall == 2.0 across the band.
- Assert the skew is inert at its default-off setting, with a paired case proving it becomes active when enabled.

**Emitter.** `extractor.claim` (I4), whose `deployed_base` field is the bound's observable.

**Exit criterion.** A simulator replay never exceeds the bound, and the emitter proves the bound was actually approached — a run that never nears it does not test the bound.

---

### Stage 7 — Observability [PARALLEL from Stage 3 onward, but must complete before any release claim]

**Ships.** The declared contracts for all nine new topics in `src/core/emit_contracts.py:110-137`, plus a `trade.filled` emission from the Extractor's fill paths so its trades are visible to the historian and to every existing consumer.

**Files touched.** `src/core/emit_contracts.py` (nine new `EmitContract` entries); `extractor_bot.py` at the three money paths (`:1405-1425`, `:1054-1063`, `:1245-1280`).

**Test + positive control.**
- Run a simulator tablet. Assert every declared topic has `topics_seen > 0` and zero violations.
- **Positive control:** assert the observer reports a violation when a payload key is deliberately renamed. This is the exact failure `emit_contracts.py:20-27` was written for — `data["action"]` versus `data["type"]` — where the producer emits successfully, the consumer reads successfully and gets `None`, and coverage reads 0/17 while 665 trades flow past.
- Second control: a topic declared but deliberately never fired must be reported by the zero-call class.

**Emitter.** All nine. This stage's deliverable *is* the emitters.

**Exit criterion.** `EmitObserver` reports zero violations and `topics_seen == topics_declared` across a full Nuclear tablet. Any claim in §6.2 that has no firing emitter is struck from the invariant list rather than shipped unproven.

---

### Stage 8 — Calibration against the null model [BLOCKED by 4, 5, 6, 7]

**Ships.** The AMM positive control from §5.8 as a Simulator comparator.

**Files touched.** Simulator tooling only. No production file.

**Test + positive control.**
- Replay identical candles through the Extractor and through `base_count = sqrt(k · alt_price_in_base)`. Report both base-unit trajectories against **holding base**, not against zero.
- **Positive control:** replay a synthetic monotone-up tape where the closed form has a known answer, and assert the comparator reproduces it. A comparator that cannot reproduce a known answer cannot judge the Extractor.

**Emitter.** `extractor.share_rate` (I10), computed by the Lido formula on round-close events only.

**Exit criterion.** The Extractor's after-fee base-unit trajectory beats the constant-product curve on at least one operator-selected tablet. **If it does not, the trigger logic adds nothing over a passive rebalance and the release decision changes.** This is the stage that can invalidate the concept, so it is last and it is not optional.

---

### Dependency summary

```
Stage 0 ─┐
Stage 1 ─┼─ PARALLEL, no blockers
Stage 2 ─┘
              Stage 3 (3a → 3b → 3c)  ← THE BLOCKER
                 │
        ┌────────┼────────┐
     Stage 4  Stage 5  Stage 6      ← all BLOCKED by 3
        └────────┼────────┘
              Stage 7  (starts with 3, completes last)
                 │
              Stage 8              ← BLOCKED by 4,5,6,7
```

Stages 0, 1 and 2 can start today and touch nothing the architectural work will rewrite. Stage 3 is a single arc and must not be split across sessions, because 3b changes a live ScrummingBot path.

---

## 8. What this report does not settle

**Operator decisions required.**

1. **C4 — the rate anchor.** DESIGN:96-103 freezes the rate at creation so ETH-USD moves do not silently resize the chunk. USDBASE:7 quotes the operator asking for USD-anchored firing. These are mutually exclusive. §6.2 I2 proposes a third option — anchor on named events with a declared `source` — but the operator must choose which semantic is correct. **Note that USDBASE's worked example does not apply to this tree**; its premise, that `set_initial_chunk_rate` is called during construction, is false.

2. **C1 — MODE A or MODE B.** Both shipped. They have different ordering semantics and only MODE B honours the volume tie-break rule at DESIGN:329. Stage 6 recommends MODE B with operator selection as a filter. That is a design change, not a fix.

3. **Should a DRAWDOWN position be allowed to exit on a bullish signal?** Today it cannot (`extractor_bot.py:937-949`). Stage 4 adds a lease-expiry exit but deliberately preserves the signal block, because averaging-down into a recovery is the stated strategy. Changing it changes the strategy.

4. **Compounding: delete or implement?** §6.1 recommends deleting it. It has never run, and its justifying example is self-refuting. If the operator wants it, it needs a fresh worked example and its own arc.

5. **Inverted Extractor: defer or fix now?** §6.4 recommends deferring. The dimensional inconsistency is rated **likely**, not verified. Confirming it requires either execution or a line-by-line dimensional trace that this report did not perform.

6. **Is the Extractor a lease-holder or a partition-owner?** §5.5 (Freqtrade) and §5.6 (Hummingbot V2 / Aave) are different architectures. The plan above adopts leases. A static partition is cheaper and would ship sooner. This is the largest single architectural fork remaining.

**Open technical questions.**

7. **Does the discrete Extractor inherit the AMM's negative expected edge?** HYPOTHESIS, stated in §5.8, and the reason Stage 8 exists. Untested. The AMM result is a theorem for the continuous constant-product rule only.

8. **The unbounded ticker loop at `:658-672`** issues one sequential call per candidate market on the asyncio-on-GUI-thread path. Stage 2 makes its failures visible. It does not make the loop bounded. That belongs to the asyncio-thread arc, not here.

9. **`prune_expired`, `force_release` and `force_release_all` still have no callers** after Stage 3c, because 3c only removes the Extractor's dependency on them. ScrummingBot's incremental reservations still need a reaper, and wiring one naively will delete live claims: `heartbeat()` deliberately skips persistence (`capital_reservation.py:561-565`), so after a restart a live bot carries a stale timestamp and `prune_expired` (`:594-602`) would drop it. That is a separate arc.

10. **`CapitalRegistry` (`capital_registry.py`), `opportunity_arbiter.py`, `capital_arbiter_bridge.py` and `smart_orders.py` remain unwired.** This report does not propose wiring them. Three of their internal defects are latent and would become live the moment they are constructed: `request_reservation` **fails open** on any wallet-provider error (`:246-251`, `:517-535`); `drift_pct` (`:466-477`) is the free-capital ratio, not a drift measure, so it alerts whenever capital is unreserved; and `capital_arbiter_bridge.py:156-160` passes a dollar amount into `pool_capacity`, defined on `[0.0, 1.0]` at `opportunity_arbiter.py:275`, which silently disables the cap. Either wire them with those fixed, or mark each module unwired at the top so no future reader assumes the invariant is enforced.

11. **Three doc-rot clusters remain**, beyond the four the archetype flagged in `extractor_bot.py`: `buy_safety.py:61-63` (three archived paths; `docs/operator_logs/` does not exist), `capital_registry.py:6` (archived audit) and `capital_registry.py:22-27`, which states the module "MUST be mirrored in `sadp/RAIntSimBat/RAIntSimBat.py`" and that an R6 cascade gate enforces it. No `sadp/` directory exists. A reader treats a dead mandate as live.

12. **Angle 3 of the supplied research was truncated mid-entry.** Its QuantConnect LEAN, Backtrader and CCXT citations lost their source URLs and could not be verified. I have used only its Nautilus and Hummingbot entries, both independently confirmed. The LEAN and Backtrader mechanisms are **UNVERIFIED** and are not cited in §5.