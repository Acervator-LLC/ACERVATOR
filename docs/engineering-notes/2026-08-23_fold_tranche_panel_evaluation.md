# Fold-Tranche panel — measured inventory of every control

Reference. This document records what each control on the Fold-Tranche Cycle
Health panel shows, where its number comes from, and whether it is correct. It
is an evaluation. **It repairs nothing.** Each defect below becomes its own unit
later.

Measured 2026-08-23 against `current` at commit `8159b98`, version `v3.26.0`.
The subject is `src/gui/bot_live_settings.py:1736` — `_create_fold_tranches_tab`
— and the bot methods it calls in `src/trading/scrumming_bot.py`.

## Method, and what each number is

Three sources, and every figure below names its own:

1. **Code read.** File and line, from the clone at `8159b98`.
2. **State read.** `~/.acervator/bot_state.json`, opened read-only, saved
   2026-08-23 17:32:18. 38 bots, all in `scrumming` mode. The file was never
   written.
3. **Offscreen drive.** The shipped `_create_fold_tranches_tab` built under
   `QT_QPA_PLATFORM=offscreen` against a **fixture copy** of live tranche data,
   with the clock frozen to the state file stamp. Both Clear buttons were driven
   against a **stub bot**, never against the running application.

The operator’s Acervator kept running throughout. Nothing started it, stopped
it, or attached to it. No live Clear button was pressed.

The probe script is not in this repository. It does not ship.

## Fleet numbers, 2026-08-23 17:32

| Measure | Value |
|---|---|
| Open fold tranches | 1,701 across 38 bots |
| Open stack tranches | 0 on every bot |
| Parked USD in the fold queue | $758.32 |
| Tranches under $1.00 | 1,481 of 1,701 (87.1%) |
| Smallest tranche | $0.00000022 (XLM/USDC) |
| Tranches with `created_ts` | 1,701 of 1,701 (100%) |
| `tranche_despawn_days` | 0 (Off) on all 38 bots |
| Price-eligible tranches right now | 11 of 1,701 |

`fold_queue_usd` agreed with the summed tranche `usd` on all 38 bots. That
aggregate is correct.

---

## The findings, ranked by what they cost the operator

### F1 — Min rebuy and Status omit the trading fee. The panel shows a gate that does not exist

**Cost: the operator plans against the wrong price.**

The panel computes its rebuy threshold from the scrumming interval alone:

    bot_live_settings.py:1987   _otd_pct = float(getattr(
                                    self._bot.config,
                                    'scrumming_interval_pct', 0) or 0)
    bot_live_settings.py:2146   min_rebuy_v = ref_v * (1.0 - _otd_pct / 100.0)
    bot_live_settings.py:2168   otd_thresh  = ref_v * (1.0 - _otd_pct / 100.0)

The executor uses a different number. The Minimum Opposing Trade Distance is
`interval + fee`, clamped, and it has one definition in `src/trading/otd_math.py`:

    otd_math.py                 total = float(interval_pct) + float(fee_pct)
    scrumming_bot.py:9554       _otd_factor = fold_rebuy_factor_from_pct(...)
    scrumming_bot.py:9577       ticker.last <= float(_t.get("ref", 0)) * _otd_factor
    scrumming_bot.py:9857       ticker.last <= float(t.get("ref", 0)) * _otd_factor

The fee is not optional. `tests/test_fold_otd_includes_fee.py` records the
2026-08-12 operator ruling that put it there.

Live configuration, from the state file:

| Interval | Fee | Bots | Panel factor | Executor factor | Panel price is too high by |
|---|---|---|---|---|---|
| 5.0% | 1.6% | 24 | 0.9500 | 0.9340 | 1.71% |
| 5.0% | 0.6% | 12 | 0.9500 | 0.9440 | 0.64% |
| 1.0% | 0.6% | 2 | 0.9900 | 0.9840 | 0.61% |

**This is not theoretical.** Both formulas were applied to the 1,701 live
tranches at their stored current price:

    panel says Price-OK : 17
    executor accepts    : 11
    FALSE GREEN         :  6      all on ALLO/USDC

Six tranches show a green **Price-OK** right now for a buy the executor refuses.
The Min rebuy column prints a price 1.71% above the real one on 24 of 38 bots.

This is the same defect class as the Target Delta bug. A label reads one field
and names another.

### F2 — Cycle close ratio is not verifiable

**Cost: the panel’s only health verdict is built on two counters that do not
reconcile.**

    bot_live_settings.py:1886   sf.addRow("Cycle close ratio (closed/opened):", ratio_lbl)

The ratio is `_tranches_closed_lifetime / _tranches_created_lifetime`. It drives
a colour. Red under 50%, amber under 80%, green above.

Two separate problems.

**Discards stay in the denominator.** A discarded tranche did not fold, and the
code counts it apart (`scrumming_bot.py:13249`). But `created` still includes it,
so clearing tranches depresses the ratio permanently. BTC/USD folded 118 of the
118 tranches it ever closed and discarded the other 42. The panel reports 73.75%.

**The counters do not reconcile with the standing list on 13 of 38 bots.** The
stated invariant is `created − closed − discarded == standing`. Measured:

| Symbol | created | closed | discarded | expected | actual open | drift |
|---|---|---|---|---|---|---|
| CHIP/USD | 4924 | 4603 | 90 | 231 | 210 | −21 |
| BILL/USD | 3276 | 3038 | 0 | 238 | 230 | −8 |
| ORCA/USD | 685 | 535 | 107 | 43 | 19 | −24 |
| KAT/USD | 1038 | 943 | 0 | 95 | 82 | −13 |
| ZEC/USD | 555 | 445 | 0 | 110 | 121 | +11 |
| BIO/USD | 305 | 161 | 132 | 12 | 19 | +7 |
| SPK/USD | 761 | 618 | 0 | 143 | 141 | −2 |
| VVV/USD | 473 | 367 | 0 | 106 | 104 | −2 |
| LINK/USD | 90 | 49 | 0 | 41 | 43 | +2 |
| XRP/USD | 55 | 36 | 0 | 19 | 22 | +3 |
| SOL/USD | 69 | 39 | 0 | 30 | 31 | +1 |
| SUI/USD | 162 | 125 | 0 | 37 | 36 | −1 |
| ONDO/USD | 233 | 187 | 0 | 46 | 45 | −1 |

The drift runs in both directions. One contributor is confirmed.
`_top_up_remnant_fold_tranches` (`scrumming_bot.py:11089`) merges a new tranche
into a part-spent one and then decrements `_tranches_created_lifetime`
(`scrumming_bot.py:11222`). That produces the positive drift. **The cause of the
negative drift is not established.** `tranches_malformed_dropped` is 0 on every
bot, so it is not that.

Until the counters reconcile, the ratio and its colour are decoration.

### F3 — Both Clear buttons write memory only. State is not saved

**Cost: clear, then close inside 60 seconds, and every tranche returns.**

    scrumming_bot.py:13273      self._fold_tranches = []
    scrumming_bot.py:13350      self._pending_wire_credits = 0.0

Neither method saves. **`clear_pending_wire_credits` has the same shape as
`clear_fold_tranches`.** Both rely on the rolling save:

    main.py:1343                save_timer.start(60000)

The precedent for the other behaviour is already in the tree. The Reset-all-errors
handler calls `save_all_state()` inside the click, and its comment names the exact
risk (`main_window.py:8259`).

The panel documents its reason for not saving at `bot_live_settings.py:2328`. A
fleet serialise on the GUI thread is the freeze class. That reason was written for
an Arbiter **toggle**. A toggle lost to a crash is set again in one click. A clear
lost to a crash restores records the operator deliberately destroyed.

### F4 — The panel never refreshes after any action

**Cost: the operator cannot tell a working button from a dead one.**

Driven offscreen against the fixture, with the confirmation accepted:

    BEFORE: table rows 58   bot tranches 58   "Open tranches: 58"
    AFTER : table rows 58   bot tranches  0   "Open tranches: 58"
            clear button text still "Clear 58 Fold Tranche(s)", enabled True
            58 Fire buttons still present

The dialog builds its tabs once in `__init__`. No refresh path exists. The code
admits it at `bot_live_settings.py:1496`, and the Manual Fire handler says the
same at `bot_live_settings.py:2650` (“Tab will refresh on next dialog open”).

The stale Fire buttons are safe. Each captured its tranche by identity, so a click
after a clear resolves nothing and shows a refusal (`bot_live_settings.py:2450`).
No wrong trade is possible. The panel misleads. It is not dangerous.

### F5 — The Source column names the wrong action

**Cost: 219 live tranches carry a label that describes an operation that cannot
have created them.**

    bot_live_settings.py:2204   src_str = ("manual fire" if t.get("operator_initiated")
                                           else "auto scrum")

`operator_initiated` is written at exactly one site, the manual **rebalance**
(`scrumming_bot.py:12393`), and its value comes from the intent map at
`scrumming_bot.py:12153`:

    "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True)
    "wire_stack":    ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False)
    "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False)

The flag means **manual scrum** — an operator-initiated SELL that created the
tranche. Manual Fire is the opposite operation. It is a BUY, and it **removes** a
tranche (`scrumming_bot.py:3548`). A tranche created by a manual fire cannot
exist.

219 of 1,701 live tranches show “manual fire”. All 219 came from a manual scrum.

The false branch is also lossy. Three provenances collapse into two labels, and a
wire-stack scrum and a cartridge scrum both print “auto scrum”.

### F6 — The success message reads as an error

**Cost: reassurance stands where a result belongs, after a button that appears to
have done nothing.**

Captured from the offscreen drive:

    [INFO] Clear fold tranches
    Discarded 58 tranche(s) holding $19.2735.

    No order was placed. This panel still shows the pre-clear figures —
    reopen it to see the new state.

Both buttons work. The trade log proves it on BTC bot `7c39c7a2`, and the state
file agrees. That bot now carries `tranches_discarded_lifetime = 42` and
`wire_credits_discarded_lifetime = 343.68244206`, which match the two log lines of
22:05 exactly.

The message is true. It reads as a failure because “No order was placed” arrives
where the operator expects a result, beside a table that did not change.

### F7 — The panel’s stated documentation does not exist

**Cost: eight of eleven columns have no explanation anywhere.**

The prose explainer was removed on operator directive 2026-07-26. The comment that
replaced it says (`bot_live_settings.py:1994`):

> Column headers + per-column tooltips are the authoritative per-tranche
> documentation.

Measured on the built table. **No header carries a tooltip.** Not one of the
eleven. Three cell tooltips exist — Min rebuy, Status and Arbiter. The columns
`#`, `Age`, `Units`, `USD parked`, `Sell ref $`, `Original cost $`, `Source` and
`Fire` carry none. No summary row carries one either.

The authority the comment names is empty.

### F8 — The table shows eight rows of up to 230

**Cost: the operator cannot reach the tranche the summary names.**

    bot_live_settings.py:2014   table.setMaximumHeight(280)
    bot_live_settings.py:2043   setDefaultSectionSize(TRANCHE_ROW_HEIGHT_PX)  # 30

Measured on BILL/USD. 230 rows, a 280 px cap, 30 px rows and a 16 px header. About
**8 rows are visible.** `setSortingEnabled` appears 0 times in the file, so the
table cannot be sorted. No filter and no search exist.

Row order is insertion order, and that is load-bearing. The Fire button resolves
its target by `tranches.index(tranche)` against `_fold_tranches`
(`bot_live_settings.py:2447`), so any re-order must keep the mapping.

On TAO the summary reports an oldest tranche of 30.4 days. The first three rows
show 2.7 d, 2.7 d and 3.6 d. The row the headline names sits somewhere inside 58,
and the operator must scroll to find it.

### F9 — The Fire dialog can name a different number from the row

**Cost: a confirmation for a market buy names a tranche the operator did not
click.**

The row number is written at build time (`bot_live_settings.py:2069`,
`str(row + 1)`). The confirmation resolves the index again at click time
(`bot_live_settings.py:2447`) and prints that (`bot_live_settings.py:2559`,
`Fire tranche #{idx + 1}?`).

Because the panel never refreshes (F4), a fold that lands between opening the
dialog and clicking Fire shifts every later index. The operator clicks row 7 and
the confirmation says tranche 6. The buy itself is correct, because identity
capture makes sure of that. The number in the confirmation is not the number on
screen.

### F10 — Sub-$1 tranches cannot fire alone, and nothing says so

**Cost: a green Price-OK on a tranche the bot will skip.**

87.1% of live tranches hold under $1.00. Coinbase enforces a minimum cost near
$1.00, and the bot has a pre-decision guard for it (`scrumming_bot.py:8961`),
added after ORCA retried a $0.33 scrum 5,558 times.

A fold cycle **packs** several tranches into one buy (`_plan_fold_consumption`,
`scrumming_bot.py:10925`), so a small tranche can discharge inside a batch. It
cannot discharge alone. When one sub-$1 tranche is the only price-eligible record,
the buy falls below minimum cost and the bot skips it.

The Status column reports the price gate only. It says nothing about minimum cost
and nothing about the per-cycle cap.

Size is not what blocks the queue today. Price is. Only 11 of 1,701 tranches are
price-eligible right now.

### F11 — Units marked exceed units held on two bots

**Cost: the fold queue claims more asset than the bot owns.**

Tranche `units` summed against holdings implied by `position_value / current_price`:

| Symbol | Units in tranches | Units held | Ratio |
|---|---|---|---|
| PUMP/USD | 19,870.72 | 9,987.78 | 1.99x |
| CAP/USD | 1,075.61 | 800.42 | 1.34x |
| ZEC/USD | 0.1598 | 0.1762 | 0.91x |

Every other bot sits at or below 0.61x.

The panel prints per-row Units and no total. It offers no comparison against the
position, so this condition stays invisible on the panel that owns the ledger.

**Not attributed here.** The tranche list is display-only in this document. The
cause of the excess sits outside the panel.

### F12 — Three real quantities are missing from the panel

- `tranches_malformed_dropped` — persisted, never shown. 0 fleet-wide today.
- `wire_credits_discarded_lifetime` — persisted, never shown. Non-zero on three
  bots now: BTC/USD $343.68, ETH/USD $213.90, ORCA/USD $1.20. The tranche discard
  row exists (`bot_live_settings.py:1895`). The wire-credit one does not. The two
  Clear buttons are not symmetric in what they report.
- `fold_cycle_cap_consumed` — persisted, never shown, and it decides how much of
  the queue one cycle may take.

---

## The Age column — answered

**The age is stored, not derived.** Every fold tranche carries `created_ts`, a
wall-clock epoch second written at creation.

Three creation sites, all writing the field:

    scrumming_bot.py:9110    "created_ts": time.time(),   auto scrum
    scrumming_bot.py:10726   "created_ts": time.time(),   distribute leg
    scrumming_bot.py:12397   "created_ts": time.time(),   manual rebalance

The panel reads it at `bot_live_settings.py:2079` and formats it with
`_format_age` (`bot_live_settings.py:2691`), which prints seconds, minutes, hours,
then days to one decimal.

**All 1,701 live tranches carry a valid `created_ts`.** Zero are missing it. The
“pre-v3.16.39, no timestamp” fallback at `bot_live_settings.py:1841` is
unreachable on this fleet.

Live age spread:

| Band | Tranches | Share |
|---|---|---|
| under 1 day | 331 | 19.5% |
| 1 to 7 days | 1,042 | 61.3% |
| 7 to 30 days | 248 | 14.6% |
| 30 days and over | 80 | 4.7% |

Oldest: 79.7 days.

**The despawn timer reads the same field.** `_tranche_age_seconds`
(`scrumming_bot.py:13379`) takes the field name as an argument, and the sweep
passes `created_ts` for fold tranches and `opened_ts` for stack tranches
(`scrumming_bot.py:13540`). The sweep runs from the tick at
`scrumming_bot.py:6788`.

**Switching the timer on would therefore delist by measured age, correctly.** It would
not delist nothing, and it would not delist everything. At a 30-day threshold it
would delist 80 tranches today. The control sits on the Settings tab
(`bot_live_settings.py:4076`), not on this panel, and it is Off on all 38 bots.

The earlier read that found no creation timestamp was wrong. The field is there,
and it is populated everywhere.

---

## Every control, one row each

Verified against TAO/USD (`f7295d86`), the bot in the operator’s screenshot. The
state-file column holds the value computed from `bot_state.json`. The panel column
holds the value the shipped builder produced offscreen.

### Summary section — Fold-Tranche Cycle Health

| Control | Shows | Source field | State file | Panel | Correct? |
|---|---|---|---|---|---|
| Open tranches | 58 | `len(_fold_tranches)` | 58 | `58` | Yes |
| Parked USD (in fold queue) | $19.2735 | sum of `t["usd"]` | 19.273467704 | `$19.2735` | Yes. Matches `fold_queue_usd` on all 38 bots. Includes accreted wire credits, by design (`scrumming_bot.py:2461`) |
| Oldest tranche age | 30.4 d | `max(now − created_ts)` | 30.380 d | `30.4d` | Yes |
| Lifetime tranches opened | 224 | `_tranches_created_lifetime` | 224 | `224` | The number matches the field. The field itself drifts — F2 |
| Lifetime tranches closed | 166 | `_tranches_closed_lifetime` | 166 | `166` | Same. F2 |
| Cycle close ratio | 74.11% | `closed / created` | 166/224 | `74.11%  (166/224)` | The arithmetic is correct. The meaning is wrong — F2 |
| Lifetime tranches discarded | hidden | `_tranches_discarded_lifetime` | 0 | not shown | Correct. The row appears only when the value is not zero (`:1893`) |
| — | — | `wire_credits_discarded_lifetime` | — | no row exists | Missing — F12 |
| — | — | `tranches_malformed_dropped` | — | no row exists | Missing — F12 |
| — | — | `fold_cycle_cap_consumed` | — | no row exists | Missing — F12 |

None of these ten rows carries a tooltip.

### Buttons

| Button | Label | What it really does | Result visible? |
|---|---|---|---|
| Clear N Fold Tranche(s) | `Clear 58 Fold Tranche(s)` | Calls `clear_fold_tranches` (`scrumming_bot.py:13221`). Empties `_fold_tranches`, zeroes `_fold_queue_usd`, adds to `_tranches_discarded_lifetime`, emits `bot.log`. Places no order. Touches no holding, no cost basis and no target balance. Does not save state — F3 | **No.** The table, the counters and the button label all keep the pre-clear values — F4. The message reads as an error — F6 |
| Clear $X Wire Credits | `Clear $343.68 Wire Credits` | Calls `clear_pending_wire_credits` (`scrumming_bot.py:13310`). Zeroes `_pending_wire_credits` and `_pending_wire_ledger`, adds to `_wire_credits_discarded_lifetime`, emits `bot.log`. Releases an earmark. Moves no money. Does not save state — F3 | **No.** The same staleness. The lifetime it writes has no row on the panel — F12 |
| Fire (one per row) | `Fire` | Resolves the tranche by identity, refuses unreadable stored values before it offers a confirmation (`bot_live_settings.py:2513`), then schedules `manual_fire_tranche(idx)` on the async loop. A market buy. Bypasses TA, OTD and Target Delta. Smart Ceiling still applies | **Partly.** A polling QTimer shows the fill dialog (`bot_live_settings.py:2622`). The table never updates. The confirmation can name a different number from the row — F9 |

Both confirmation dialogs are honest and complete. The fold-tranche one names the
parked wire credit and the absorb-window trap. The wire one names the earmark
distinction. Neither confirmation is a defect.

The disabled states are correct. With zero tranches the Clear button reads
`Clear Fold Tranches` and is disabled. With zero parked credit the wire button
reads `Clear Wire Credits` and is disabled.

### Open Tranches table — eleven columns

Row 1 of TAO, as the shipped builder rendered it.

| # | Column | Rendered | Source field | Correct? |
|---|---|---|---|---|
| 0 | `#` | `1` | `row + 1` at build time | An index into `_fold_tranches`, load-bearing for Fire. Goes stale after any change — F4, F9 |
| 1 | `Age` | `2.7d` | `now − created_ts` | **Yes.** A stored field, populated on all 1,701 |
| 2 | `Units` | `0.001145` | `t["units"]` | The value is correct. No total row and no comparison with holdings — F11 |
| 3 | `USD parked` | `$0.2415` | `t["usd"]` | Yes. Includes accreted wire credits |
| 4 | `Sell ref $` | `$221.95000000` | `t["ref"]` | Yes. The price the scrum sold at |
| 5 | `Original cost $` | `$299.48000000` | `t["initial_buy_price"]` | Yes. Informational provenance (MEM-171). It does not gate the fold |
| 6 | `Min rebuy $` | `≤$210.85250000` | `ref × (1 − interval/100)` | **No. It omits the fee. The real threshold is $207.30 — F1** |
| 7 | `Status` | `Need price ≤ OTD (+13.62%)` | the same fee-less threshold against `current_price` | **No. The same defect — F1.** It is also silent on minimum cost and on the cycle cap — F10 |
| 8 | `Source` | `auto scrum` | `t["operator_initiated"]` | **No. “manual fire” names the wrong operation — F5** |
| 9 | `Fire` | button | — | It works. See the Buttons table |
| 10 | `Arbiter` | `—` | constant | Correct. A fold tranche has no arbiter, and the tooltip says so |

Value admission is sound. Every money cell and the timestamp pass through
`as_finite_float`, so a stored `True`, `nan`, `inf`, `None` or an out-of-range int
renders an em dash instead of a number or a traceback. That work is pinned by
`tests/test_bot_live_settings_fold_row_admission.py`, and it holds.

Extractor rows append after the fold rows and never interleave, which keeps the
Fire index mapping true (`bot_live_settings.py:2005`). **Not exercised on live.**
All 38 bots run in scrumming mode and no Extractor exists, so `ext_rows` is empty
everywhere.

---

## What the panel is missing — items 21, 22 and 24

Searched `src/`, `tools/` and `docs/` for `merge_down`, `merge_up`, `Merge Down`,
`Merge Up`, `min_tranche_size`, `minimum_tranche`, `max_tranches`,
`max_fold_tranches` and `maximum_tranche`. **Zero hits.**

| Proposed feature | Present? | The nearest thing that exists |
|---|---|---|
| Merge Downward | **No** | none |
| Merge Upward | **Partly, and not as a control.** `_top_up_remnant_fold_tranches` (`scrumming_bot.py:11089`) folds a new tranche into a part-spent one. It is automatic. It needs an identical `initial_buy_price` and a `ref` inside the current BB range, and it has no operator surface. 1 tranche in 1,701 carries `fold_partial_spent`, so it almost never runs |
| Minimum Tranche Size | **No** | none. 1,481 of 1,701 tranches sit under $1.00, and 103 sit under $0.01 |
| Maximum Number of Tranches | **No** | none. The largest queue is BILL/USD at 230 |

The panel has no create-side control at all. It can clear everything, or fire one
row.

---

## What I could not verify

- **The negative counter drift (F2).** The positive drift has a confirmed cause.
  The bots that show fewer standing tranches than the counters predict do not.
  Every removal site increments a counter, and `tranches_malformed_dropped` is 0
  fleet-wide. The cause sits elsewhere and needs its own unit.
- **Extractor Tranche rows.** No Extractor exists on this fleet. That path was read
  from code only and never rendered with data.
- **The live Clear buttons.** Driven against a fixture and a stub bot only.
  Pressing a real one would be a trading action.
- **The exact Coinbase minimum cost per market.** The bot fetches it from
  `_get_market_limits` at run time. $1.00 is the figure the code comments name
  (`scrumming_bot.py:908`), and F10 uses it as an approximation.
- **The despawn timer running.** It is Off on all 38 bots and has never swept. The
  claim that it would delist 80 tranches at a 30-day threshold is arithmetic over
  the state file, not an observed sweep.
- **The stack side.** 0 stack tranches exist, so the mirror panel was not
  evaluated.

## Falsification

This evaluation is wrong if:

(a) `_create_fold_tranches_tab` reads a field this document does not name;
(b) the executor fold predicate stops being `ticker.last <= ref * _otd_factor`
with `_otd_factor` from `otd_math`, which would void F1;
(c) `created_ts` is absent from any tranche created after 2026-08-23, which would
void the Age answer;
(d) `clear_fold_tranches` or `clear_pending_wire_credits` gains a save call, which
would void F3;
(e) the state file read here was not the file the running application wrote at
17:32:18 on 2026-08-23;
(f) the offscreen stub diverges from the live bot in any attribute the tab reads.
The stub supplies `_fold_tranches`, the three lifetime counters,
`_pending_wire_credits`, `_pending_wire_ledger`, `config` and `get_status`, and the
tab reads nothing else.
