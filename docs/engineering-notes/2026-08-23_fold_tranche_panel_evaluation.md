# Fold-Tranche panel — measured inventory of every control

Reference. This document records what each control on the Fold-Tranche Cycle
Health panel shows, where its number comes from, and whether it is correct. It
is an evaluation of the panel as it stands. Every defect below is still in the
code.

Measured 2026-08-23 against `current` at commit `8159b98`, version `v3.26.0`.
The subject was `_create_fold_tranches_tab` and the bot methods it calls in
`src/trading/scrumming_bot.py`. The 2026-08-27 mixin split moved
`_create_fold_tranches_tab` to `src/gui/live_settings/fold_tranches_tab.py:860`
and moved most of the bot methods below into `src/trading/scrumming/`; every
citation in this document has been re-anchored to that layout.

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

**Status: FIXED (issue #97, v3.26.0). Re-verified 2026-09-03 by cold read.**
The panel now asks `otd_math` for the same factor the executor uses, instead
of computing its own fee-less one. This section is kept as the record of the
defect, not as an open item.

**Cost: the operator plans against the wrong price.**

The panel computed its rebuy threshold from the scrumming interval alone
(pre-fix, no longer in the tree):

    _otd_pct = float(getattr(
        self._bot.config, 'scrumming_interval_pct', 0) or 0)
    min_rebuy_v = ref_v * (1.0 - _otd_pct / 100.0)
    otd_thresh  = ref_v * (1.0 - _otd_pct / 100.0)

Neither expression is in the panel any more. It now reads the same factor as
the executor:

    fold_tranches_tab.py:1406   _otd_pct = minimum_opposing_trade_distance_pct_from_config(...)
    fold_tranches_tab.py:1409   _otd_factor = fold_rebuy_factor_from_pct(_otd_pct)
    fold_tranches_tab.py:1641   min_rebuy_v = ref_v * _otd_factor
    fold_tranches_tab.py:1674   otd_thresh = ref_v * _otd_factor

The Minimum Opposing Trade Distance is `interval + fee`, clamped, and it has
one definition in `src/trading/otd_math.py`:

    otd_math.py:110              total = float(interval_pct) + float(fee_pct)
    otd_math.py:114              def fold_rebuy_factor_from_pct(otd_pct: float) -> float:
    scrumming_bot.py:3912        _otd_factor = fold_rebuy_factor_from_pct(_otd_pct_for_gate)
    scrumming/fold_tranches.py:53   def _fold_eligible_tranches(self, ticker_last, otd_factor) -> list:

`_fold_eligible_tranches` is now the single definition of the per-tranche gate
(`ticker_last <= ref * otd_factor`); the FOLD_DIAG counter and the fold-back
executor both call it, which is what the two separate comprehensions below
used to risk diverging on.

The fee is not optional. `tests/test_fold_otd_includes_fee.py` and
`tests/test_fold_panel_asks_the_executor.py` record the 2026-08-12 operator
ruling that put it there and the 2026-08-23 fix that connected the panel
to it.

Live configuration at measurement time:

| Interval | Fee | Bots | Panel factor | Executor factor | Panel price was too high by |
|---|---|---|---|---|---|
| 5.0% | 1.6% | 24 | 0.9500 | 0.9340 | 1.71% |
| 5.0% | 0.6% | 12 | 0.9500 | 0.9440 | 0.64% |
| 1.0% | 0.6% | 2 | 0.9900 | 0.9840 | 0.61% |

**This was not theoretical.** Both formulas were applied to the 1,701 live
tranches at their stored current price:

    panel said Price-OK : 17
    executor accepted   : 11
    FALSE GREEN         :  6      all on ALLO/USDC

Six tranches showed a green **Price-OK** for a buy the executor refused. The
Min rebuy column printed a price 1.71% above the real one on 24 of 38 bots.
The panel and the executor now read the same factor, so a false green of
this kind is no longer possible.

This was the same defect class as the Target Delta bug. A label read one
field and named another.

### F2 — Cycle close ratio is not verifiable

**Status: FIXED (issue #98 defect 4, v3.26.0). Re-verified 2026-09-03 by cold
read.** The ratio and its colour now come from one pure composer,
`compose_cycle_close_ratio` (`src/gui/live_settings/fold_tokens.py:619`), and
the denominator excludes discards. This section is kept as the record of the
defect, not as an open item.

**Cost: the panel's only health verdict was built on two counters that did not
reconcile.**

    sf.addRow("Cycle close ratio (closed/opened):", ratio_lbl)   # pre-fix, no longer in the tree

That row is gone. The current call is:

    fold_tranches_tab.py:1018   discarded_lifetime = int(getattr(
                                     self._bot, "_tranches_discarded_lifetime", 0) or 0)
    fold_tranches_tab.py:1021   ratio_str, ratio_colour = compose_cycle_close_ratio(
                                     created_lifetime, closed_lifetime, discarded_lifetime)
    fold_tranches_tab.py:1114   "Cycle close ratio (folded / opened minus discarded):"

The ratio used to be `_tranches_closed_lifetime / _tranches_created_lifetime`,
with a second, separate arithmetic deciding the colour over the same
`created` denominator. It drove a colour: red under 50%, amber under 80%,
green above.

Two separate problems, both repaired.

**Discards stayed in the denominator.** A discarded tranche did not fold, and
the code counted it apart. But `created` still included it, so clearing
tranches depressed the ratio permanently. BTC/USD folded 118 of the 118
tranches it ever closed and discarded the other 42. The panel reported
73.75%. The ratio is now `closed / (created − discarded)`; the same bot now
reads 100.00% (118/118), and the label states the arithmetic instead of
naming a formula the colour did not share.

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

The drift ran in both directions. The positive-drift contributor named here
still stands: `_top_up_remnant_fold_tranches`
(`src/trading/scrumming/fold_tranches.py:304`) merges a new tranche into a
part-spent one and then decrements `_tranches_created_lifetime`
(`src/trading/scrumming/fold_tranches.py:375`).

**The negative-drift cause, then unestablished, is now found and repaired.**
`_drop_malformed_fold_tranches`
(`src/trading/scrumming/fold_tranches.py:177`) removed a malformed tranche
(`ref` not above zero) and bumped only `_tranches_malformed_dropped`, which is
not a term of `created − closed − discarded == standing`. A removal that
moves no term of that identity leaves standing one lower than the counters
predict, per record, forever — the negative-drift write site this section
could not find. It now also bumps `_tranches_discarded_lifetime`
(`src/trading/scrumming/fold_tranches.py:237`), and
`_tranches_malformed_dropped` is a sub-count of the discard total rather than
a fourth term.

Until this fix, the ratio and its colour were decoration.

### F3 — Both Clear buttons write memory only. State is not saved

**Status: FIXED (issue #98 items 1–3, v3.26.0). Re-verified 2026-09-03 by cold
read.** Both clears now save before they refresh. This section is kept as the
record of the defect, not as an open item.

**Cost: clear, then close inside 60 seconds, and every tranche returns.**

    self._fold_tranches = []          # pre-fix line numbers, no longer in the tree
    self._pending_wire_credits = 0.0

The same assignments now live at:

    src/trading/scrumming/fold_tranches.py:644     self._fold_tranches = []
    src/trading/scrumming/wire_routing.py:678       self._pending_wire_credits = 0.0

Neither method saves by itself; the save moved to the caller. Both clear
handlers now call `_settle_after_clear`
(`src/gui/live_settings/fold_tranches_tab.py:785`), which saves first, then
refreshes:

    fold_tranches_tab.py:802    saved, why = self._save_fleet_state_now(what)
    fold_tranches_tab.py:803    refresh = self._refresh_fold_tranches_tab()

Before the fix, both methods relied on the rolling save alone:

    save_timer.start(60000)     # pre-fix line number, no longer in the tree

That call now lives at `main.py:960`.

The precedent for the fix is the Reset-all-errors handler, which calls
`save_all_state()` inside the click at `src/gui/main_window.py:2086`.

The panel documents its reason for NOT forcing a save on the Arbiter
**toggle** at `src/gui/live_settings/fold_tranches_tab.py:1908` — a fleet
serialise on the GUI thread is the freeze class the toggle avoids. A toggle
lost to a crash is set again in one click. A clear lost to a crash restored
records the operator deliberately destroyed, which is why the clear buttons,
unlike the toggle, now force the save.

### F4 — The panel never refreshes after any action

**Status: FIXED (issue #98 defect 1, v3.26.0). Re-verified 2026-09-03 by cold
read.** `_install_fold_tranches_tab` records the built page and
`_refresh_fold_tranches_tab` rebuilds it in place, found by widget identity
and reinserted at the same index. Both clears call it, and so does a filled
Manual Fire. This section is kept as the record of the defect, not as an
open item.

**Cost: the operator could not tell a working button from a dead one.**

Driven offscreen against the fixture, with the confirmation accepted:

    BEFORE: table rows 58   bot tranches 58   "Open tranches: 58"
    AFTER : table rows 58   bot tranches  0   "Open tranches: 58"
            clear button text still "Clear 58 Fold Tranche(s)", enabled True
            58 Fire buttons still present

The dialog built its tabs once in `__init__` and had no refresh path. The
build and refresh methods now live at
`src/gui/live_settings/fold_tranches_tab.py:623`
(`_install_fold_tranches_tab`) and `:637` (`_refresh_fold_tranches_tab`), and
both clear handlers and the Manual Fire handler call the latter through
`_settle_after_clear` (`:785`).

The stale Fire buttons were already safe. Each captured its tranche by
identity, so a click after a clear resolved nothing and showed a refusal —
the refusal message now lives at
`src/gui/live_settings/fold_tranches_tab.py:2086`. No wrong trade was
possible even before the fix.

### F5 — The Source column names the wrong action

**Status: FIXED (issue #98 defect 5, v3.26.0). Re-verified 2026-09-03 by cold
read.** The column now distinguishes three provenances instead of two. This
section is kept as the record of the defect, not as an open item.

**Cost: 219 live tranches carried a label that described an operation that
could not have created them.**

    src_str = ("manual fire" if t.get("operator_initiated")   # pre-fix, no longer in the tree
               else "auto scrum")

That two-way test is gone. The column now calls
`_fold_tranche_source_label` (`src/gui/live_settings/fold_tokens.py:667`):

    if tranche.get("operator_initiated"):
        return FOLD_SOURCE_MANUAL_SCRUM
    if "operator_initiated" in tranche:
        return FOLD_SOURCE_AUTO_REBALANCE
    return FOLD_SOURCE_AUTO_SCRUM

`operator_initiated` is written at the manual **rebalance** append
(`src/trading/scrumming/execution.py:671`, key set at `:677`), and its value
comes from the intent map at `src/trading/scrumming/execution.py:448`:

    "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True)
    "wire_stack":    ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False)
    "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False)

The flag means **manual scrum** — an operator-initiated SELL that created the
tranche. Manual Fire is the opposite operation. It is a BUY, and it
**removes** a tranche (`src/trading/scrumming_bot.py:1608`). A tranche
created by a manual fire cannot exist.

219 of 1,701 live tranches showed “manual fire”. All 219 came from a manual
scrum, and now read “manual scrum”.

The false branch was also lossy: a wire-stack scrum and a cartridge scrum
both printed “auto scrum”. The key's presence, not just its truthiness, now
distinguishes an autonomous rebalance (`FOLD_SOURCE_AUTO_REBALANCE`, key
present and false — Wire Stack or Max Cartridge) from the ordinary scrum
cycle or a DIST re-fold (`FOLD_SOURCE_AUTO_SCRUM`, key absent). Wire Stack
and Max Cartridge are still not told apart on the record.

### F6 — The success message reads as an error

**Status: FIXED (issue #98 defect 2, v3.26.0). Re-verified 2026-09-03 by cold
read.** The message now leads with what happened, at
`src/gui/live_settings/fold_tranches_tab.py:206`. This section is kept as the
record of the defect, not as an open item.

**Cost: reassurance stood where a result belonged, after a button that
appeared to have done nothing.**

Captured from the offscreen drive:

    [INFO] Clear fold tranches
    Discarded 58 tranche(s) holding $19.2735.

    No order was placed. This panel still shows the pre-clear figures —
    reopen it to see the new state.

Both buttons worked. The trade log proved it on BTC bot `7c39c7a2`, and the
state file agreed. That bot carried `tranches_discarded_lifetime = 42` and
`wire_credits_discarded_lifetime = 343.68244206`, which matched the two log
lines of 22:05 exactly.

The message was true. It read as a failure because “No order was placed”
arrived where the operator expected a result, beside a table that had not
changed. The order is now: what happened, what the bot holds, what the panel
shows, whether it reached disk, and the reassurance last.

### F7 — The panel’s stated documentation does not exist

**Status: FIXED (issue #98 defect 6, v3.26.0). Re-verified 2026-09-03 by cold
read.** All eleven column headers now carry a tooltip
(`FOLD_COLUMN_TOOLTIPS`, `src/gui/live_settings/fold_tokens.py:472`), and
nine of twelve summary rows carry one on both the label and the value. This
section is kept as the record of the defect, not as an open item.

**Cost: eight of eleven columns had no explanation anywhere.**

The prose explainer was removed on operator directive 2026-07-26. The
comment that replaced it named “column headers + per-column tooltips” as the
authoritative per-tranche documentation.

Measured on the built table at the time. **No header carried a tooltip.**
Not one of the eleven. Three cell tooltips existed — Min rebuy, Status and
Arbiter. The columns `#`, `Age`, `Units`, `USD parked`, `Sell ref $`,
`Original cost $`, `Source` and `Fire` carried none. No summary row carried
one either.

The authority the comment named was empty. The record of that measurement
now lives in the comment at `src/gui/live_settings/fold_tokens.py:455`,
beside the fix.

### F8 — The table shows eight rows of up to 230

**Status: FIXED (issue #98 defect 7, v3.26.0). Re-verified 2026-09-03 by cold
read.** The fixed 280px cap is gone; the table now sizes to
`TRANCHE_TABLE_VISIBLE_ROWS = 18`
(`src/gui/live_settings/fold_tokens.py:254`) and a filter box hides rows
without moving any. This section is kept as the record of the defect, not as
an open item.

**Cost: the operator could not reach the tranche the summary named.**

    table.setMaximumHeight(280)                          # pre-fix, no longer in the tree
    setDefaultSectionSize(TRANCHE_ROW_HEIGHT_PX)  # 30

The fixed cap is replaced with a row-count-driven height:

    fold_tranches_tab.py:1483   table.setFixedHeight(fold_table_max_height_px(
                                     len(tranches) + len(ext_rows), ...))
    fold_tranches_tab.py:1516   table.verticalHeader().setDefaultSectionSize(TRANCHE_ROW_HEIGHT_PX)

Measured on BILL/USD at the time: 230 rows, a 280 px cap, 30 px rows and a 16
px header — about 8 rows visible. `setSortingEnabled` is still unused, and
the reason is load-bearing: it moves items and leaves `setCellWidget`
widgets behind, which would slide a row's text out from under its own Fire
button. A filter box (`self._fold_filter_edit`,
`src/gui/live_settings/fold_tranches_tab.py:901`) now hides rows without
reordering them.

Row order is still insertion order, and that is still load-bearing. The Fire
button resolves its target by `tranches.index(tranche)` against
`_fold_tranches` (`src/gui/live_settings/fold_tranches_tab.py:2072`), so the
filter hides rows rather than removing or reordering them.

On TAO the summary reported an oldest tranche of 30.4 days, with the first
three rows showing 2.7 d, 2.7 d and 3.6 d. At 18 visible rows against 58
open, the operator now reaches most queues without scrolling; a queue larger
than 18 still needs the filter or a scroll.

### F9 — The Fire dialog can name a different number from the row

**Status: FIXED (issue #98 defect 8, v3.26.0). Re-verified 2026-09-03 by cold
read.** The row's `#` is now captured in its own closure at build time, and
the confirmation names both numbers when they disagree. This section is kept
as the record of the defect, not as an open item.

**Cost: a confirmation for a market buy could name a tranche the operator did
not click.**

The row number was written at build time (`str(row + 1)`, pre-fix). The
confirmation resolved the index again at click time and printed that
(`Fire tranche #{idx + 1}?`, pre-fix) — neither line is in the tree any more.

The row number is now written at
`src/gui/live_settings/fold_tranches_tab.py:1549`
(`str(queue_index + 1)`), captured for the click at `:2096`:

    _row_no = idx + 1 if clicked_number is None else int(clicked_number)
    _moved = _row_no != idx + 1

and the confirmation at `:2227` (`Fire tranche #{_row_no}?`) names the
captured row number; when `_moved` is true, the dialog states that a fold
landed in between and names both numbers (`:2218`).

Before the fix, because the panel never refreshed (F4), a fold landing
between opening the dialog and clicking Fire shifted every later index. The
operator clicked row 7 and the confirmation said tranche 6. The buy itself
was correct even then, because identity capture made sure of that; the fix
makes the confirmation correct too.

### F10 — Sub-$1 tranches cannot fire alone, and nothing says so

**Status: OPEN. Re-verified 2026-09-03 by cold read.** Issue #98's other nine
defects were repaired in the same unit; this one was not addressed, and the
Status column tooltip still names only the price gate and TA
(`src/gui/live_settings/fold_tranches_tab.py:1684`).

**Cost: a green Price-OK on a tranche the bot will skip.**

87.1% of live tranches held under $1.00 at measurement time. Coinbase
enforces a minimum cost near $1.00, and the bot has a pre-decision guard for
it on the fold side, now at `src/trading/scrumming/tick_phases.py:1643`
(`_min_cost_fc`).

A fold cycle **packs** several tranches into one buy
(`_plan_fold_consumption`, `src/trading/scrumming/fold_tranches.py:131`), so
a small tranche can discharge inside a batch. It cannot discharge alone.
When one sub-$1 tranche is the only price-eligible record, the buy falls
below minimum cost and the bot skips it.

The Status column still reports the price gate only. It says nothing about
minimum cost and nothing about the per-cycle cap.

Size was not what blocked the queue at measurement time. Price was — only 11
of 1,701 tranches were price-eligible.

### F11 — Units marked exceed units held on two bots

**Status: Visibility FIXED (issue #98 defect 9, v3.26.0). Re-verified
2026-09-03 by cold read. The excess itself is not attributed, then or now.**
A summary row now states the total and its ratio and turns red above 1.00x
(`compose_units_marked_row`, `src/gui/live_settings/fold_tokens.py:572`),
called from `src/gui/live_settings/fold_tranches_tab.py:1058`. It attributes
nothing. This section is kept as the record of the defect, not as an open
item.

**Cost: the fold queue claimed more asset than the bot owned, and the panel
did not say so.**

Tranche `units` summed against holdings implied by `position_value /
current_price`, measured at the time:

| Symbol | Units in tranches | Units held | Ratio |
|---|---|---|---|
| PUMP/USD | 19,870.72 | 9,987.78 | 1.99x |
| CAP/USD | 1,075.61 | 800.42 | 1.34x |
| ZEC/USD | 0.1598 | 0.1762 | 0.91x |

Every other bot sat at or below 0.61x.

The panel printed per-row Units and no total. It offered no comparison
against the position, so this condition stayed invisible on the panel that
owns the ledger. The new row, “Units marked (queue vs held):”
(`src/gui/live_settings/fold_tranches_tab.py:1069`), makes it visible.

**Still not attributed.** The tranche list is display-only in this document,
and the fix does not attribute the excess either. The cause sits outside the
panel.

### F12 — Three real quantities are missing from the panel

**Status: FIXED (issue #98 defect 10, v3.26.0). Re-verified 2026-09-03 by
cold read.** All three now have a row. This section is kept as the record of
the defect, not as an open item.

- `_tranches_malformed_dropped` — was persisted, never shown. 0 fleet-wide at
  measurement time. Now always shown (`src/gui/live_settings/fold_tranches_tab.py:1180`,
  row at `:1190`), because a zero is a positive statement.
- `_wire_credits_discarded_lifetime` — was persisted, never shown. Non-zero on
  three bots at measurement time: BTC/USD $343.68, ETH/USD $213.90, ORCA/USD
  $1.20. The tranche discard row existed then and still does, now at
  `src/gui/live_settings/fold_tranches_tab.py:1133`; the wire-credit one did
  not. Now shown once non-zero, mirroring that row's own convention
  (`src/gui/live_settings/fold_tranches_tab.py:1169`).
- `_fold_cycle_cap_consumed` — was persisted, never shown, and it decides how
  much of the queue one cycle may take. Now shown beside the budget it is
  spent from (`src/gui/live_settings/fold_tranches_tab.py:1216`, row at
  `:1225`), reading the same two fields the Settings tab already prints
  rather than a second arithmetic of its own.

---

## The Age column — answered

**The age is stored, not derived.** Every fold tranche carries `created_ts`, a
wall-clock epoch second written at creation.

Three creation sites, all writing the field:

    scrumming/tick_phases.py:1248   "created_ts": time.time(),   auto scrum
    scrumming/tick_phases.py:2030   "created_ts": time.time(),   distribute leg
    scrumming/execution.py:678      "created_ts": time.time(),   manual rebalance

The panel reads it at `src/gui/live_settings/fold_tranches_tab.py:1559` and
formats it with `_format_age` (`src/gui/bot_live_settings.py:962`), which
prints seconds, minutes, hours, then days to one decimal.

**All 1,701 live tranches carried a valid `created_ts`** at measurement time.
Zero were missing it. The “pre-v3.16.39, no timestamp” fallback still exists,
at `src/gui/live_settings/fold_tranches_tab.py:1010`, and was unreachable on
that fleet.

Live age spread:

| Band | Tranches | Share |
|---|---|---|
| under 1 day | 331 | 19.5% |
| 1 to 7 days | 1,042 | 61.3% |
| 7 to 30 days | 248 | 14.6% |
| 30 days and over | 80 | 4.7% |

Oldest: 79.7 days.

**The despawn timer reads the same field.** `_tranche_age_seconds`
(`src/trading/scrumming/fold_tranches.py:811`) takes the field name as an
argument, and the sweep (`_despawn_aged_tranches`,
`src/trading/scrumming/fold_tranches.py:850`) passes `created_ts` for fold
tranches (`:943`) and `opened_ts` for stack tranches (`:957`). The sweep runs
from the tick at `src/trading/scrumming_bot.py:2645`.

**Switching the timer on would therefore delist by measured age, correctly.**
It would not delist nothing, and it would not delist everything. At a 30-day
threshold it would have delisted 80 tranches at measurement time. The
control sits on the Settings tab
(`src/gui/live_settings/settings_tab.py:870`), not on this panel, and it was
Off on all 38 bots.

The earlier read that found no creation timestamp was wrong. The field is there,
and it is populated everywhere.

---

## Every control, one row each

Verified against TAO/USD (`f7295d86`), the bot in the operator's screenshot,
at measurement time. The state-file column holds the value computed from
`bot_state.json`. The panel column holds the value the shipped builder
produced offscreen. Every citation below has been re-anchored to the current
tree; the “Correct?” column is left as measured, with a status note where a
finding above has since been fixed.

### Summary section — Fold-Tranche Cycle Health

| Control | Shows | Source field | State file | Panel | Correct? |
|---|---|---|---|---|---|
| Open tranches | 58 | `len(_fold_tranches)` | 58 | `58` | Yes |
| Parked USD (in fold queue) | $19.2735 | sum of `t["usd"]` | 19.273467704 | `$19.2735` | Yes. Matched `fold_queue_usd` on all 38 bots. Includes accreted wire credits, by design (`src/trading/scrumming/wire_routing.py:501`) |
| Oldest tranche age | 30.4 d | `max(now − created_ts)` | 30.380 d | `30.4d` | Yes |
| Lifetime tranches opened | 224 | `_tranches_created_lifetime` | 224 | `224` | The number matched the field. The field itself drifted — F2, now FIXED |
| Lifetime tranches closed | 166 | `_tranches_closed_lifetime` | 166 | `166` | Same. F2, now FIXED |
| Cycle close ratio | 74.11% | `closed / created` | 166/224 | `74.11%  (166/224)` | The arithmetic was correct. The meaning was wrong — F2, now FIXED (`closed / (created − discarded)`) |
| Lifetime tranches discarded | hidden | `_tranches_discarded_lifetime` | 0 | not shown | Correct. The row appears only when the value is not zero (`src/gui/live_settings/fold_tranches_tab.py:1133`) |
| — | — | `wire_credits_discarded_lifetime` | — | no row exists | Missing — F12, now FIXED |
| — | — | `tranches_malformed_dropped` | — | no row exists | Missing — F12, now FIXED |
| — | — | `fold_cycle_cap_consumed` | — | no row exists | Missing — F12, now FIXED |

None of these ten rows carried a tooltip at measurement time; nine of twelve
now do (F7).

### Buttons

| Button | Label | What it really does | Result visible? |
|---|---|---|---|
| Clear N Fold Tranche(s) | `Clear 58 Fold Tranche(s)` | Calls `clear_fold_tranches` (`src/trading/scrumming/fold_tranches.py:614`). Empties `_fold_tranches`, zeroes `_fold_queue_usd`, adds to `_tranches_discarded_lifetime`, emits `bot.log`. Places no order. Touches no holding, no cost basis and no target balance. Did not save state — F3, now FIXED | **F4 FIXED.** The table, the counters and the button label now rebuild after a clear. The message no longer reads as an error — F6, now FIXED |
| Clear $X Wire Credits | `Clear $343.68 Wire Credits` | Calls `clear_pending_wire_credits` (`src/trading/scrumming/wire_routing.py:653`). Zeroes `_pending_wire_credits` and `_pending_wire_ledger`, adds to `_wire_credits_discarded_lifetime`, emits `bot.log`. Releases an earmark. Moves no money. Did not save state — F3, now FIXED | **F4 FIXED.** The lifetime it writes now has a row on the panel — F12, now FIXED |
| Fire (one per row) | `Fire` | Resolves the tranche by identity, refuses unreadable stored values before it offers a confirmation (`src/gui/live_settings/fold_tranches_tab.py:2168`), then schedules `manual_fire_tranche(idx)` on the async loop. A market buy. Bypasses TA, OTD and Target Delta. Smart Ceiling still applies | **F4 FIXED.** A polling QTimer shows the fill dialog (`src/gui/live_settings/fold_tranches_tab.py:2301`), and the table now updates. The confirmation naming a different number from the row is FIXED — F9 |

Both confirmation dialogs were honest and complete. The fold-tranche one
names the parked wire credit and the absorb-window trap. The wire one names
the earmark distinction. Neither confirmation was a defect.

The disabled states were correct. With zero tranches the Clear button reads
`Clear Fold Tranches` and is disabled. With zero parked credit the wire
button reads `Clear Wire Credits` and is disabled.

### Open Tranches table — eleven columns

Row 1 of TAO, as the shipped builder rendered it at measurement time.

| # | Column | Rendered | Source field | Correct? |
|---|---|---|---|---|
| 0 | `#` | `1` | `row + 1` at build time | An index into `_fold_tranches`, load-bearing for Fire. Went stale after any change — F4, F9, now FIXED (`src/gui/live_settings/fold_tranches_tab.py:1549`) |
| 1 | `Age` | `2.7d` | `now − created_ts` | **Yes.** A stored field, populated on all 1,701 |
| 2 | `Units` | `0.001145` | `t["units"]` | The value was correct. No total row and no comparison with holdings — F11, visibility now FIXED |
| 3 | `USD parked` | `$0.2415` | `t["usd"]` | Yes. Includes accreted wire credits |
| 4 | `Sell ref $` | `$221.95000000` | `t["ref"]` | Yes. The price the scrum sold at |
| 5 | `Original cost $` | `$299.48000000` | `t["initial_buy_price"]` | Yes. Informational provenance (MEM-171). It does not gate the fold |
| 6 | `Min rebuy $` | `≤$210.85250000` | `ref × (1 − interval/100)` | **It omitted the fee. The real threshold was $207.30 — F1, now FIXED** |
| 7 | `Status` | `Need price ≤ OTD (+13.62%)` | the same fee-less threshold against `current_price` | **Same defect — F1, now FIXED.** Still silent on minimum cost and on the cycle cap — F10, OPEN |
| 8 | `Source` | `auto scrum` | `t["operator_initiated"]` | **“manual fire” named the wrong operation — F5, now FIXED** |
| 9 | `Fire` | button | — | It works. See the Buttons table |
| 10 | `Arbiter` | `—` | constant | Correct. A fold tranche has no arbiter, and the tooltip says so |

Value admission was sound. Every money cell and the timestamp pass through
`as_finite_float`, so a stored `True`, `nan`, `inf`, `None` or an
out-of-range int renders an em dash instead of a number or a traceback. That
work is pinned by `tests/test_bot_live_settings_fold_row_admission.py`, and
it holds.

Extractor rows append after the fold rows and never interleave, which keeps
the Fire index mapping true (`src/gui/live_settings/fold_tranches_tab.py:1458`,
comment above it at `:1451`). **Not exercised on live.** All 38 bots run in
scrumming mode and no Extractor exists, so `ext_rows` is empty everywhere.

---

## What the panel is missing — items 21, 22 and 24

Searched `src/`, `tools/` and `docs/` for `merge_down`, `merge_up`, `Merge Down`,
`Merge Up`, `min_tranche_size`, `minimum_tranche`, `max_tranches`,
`max_fold_tranches` and `maximum_tranche`. **Zero hits.**

| Proposed feature | Present? | The nearest thing that exists |
|---|---|---|
| Merge Downward | **No** | none |
| Merge Upward | **Partly, and not as a control.** `_top_up_remnant_fold_tranches` (`src/trading/scrumming/fold_tranches.py:304`) folds a new tranche into a part-spent one. It is automatic. It needs an identical `initial_buy_price` and a `ref` inside the current BB range, and it has no operator surface. 1 tranche in 1,701 carried `fold_partial_spent` at measurement time, so it almost never runs |
| Minimum Tranche Size | **No** | none. 1,481 of 1,701 tranches held under $1.00, and 103 held under $0.01 |
| Maximum Number of Tranches | **No** | none. The largest queue was BILL/USD at 230 |

The search still returns zero hits on the current tree. The panel still has
no create-side control at all. It can clear everything, or fire one row.

---

## What I could not verify

- **The negative counter drift (F2), then unverified, is now found and
  repaired.** `_drop_malformed_fold_tranches`
  (`src/trading/scrumming/fold_tranches.py:177`) was the missing negative-drift
  write site: it bumped `_tranches_malformed_dropped` only, not a term of the
  `created − closed − discarded == standing` identity. It now also bumps
  `_tranches_discarded_lifetime`.
- **Extractor Tranche rows.** No Extractor exists on this fleet. That path was read
  from code only and never rendered with data.
- **The live Clear buttons.** Driven against a fixture and a stub bot only.
  Pressing a real one would be a trading action.
- **The exact Coinbase minimum cost per market.** The bot fetches it from
  `_get_market_limits` (`src/trading/bot_container.py:110`) at run time. The
  narrative comment that named $1.00 as the approximate Coinbase min_cost is
  no longer in the tree; the guard it described is now the fold-side
  min-cost pre-check at `src/trading/scrumming/tick_phases.py:1643`, and F10
  still uses $1.00 as an approximation.
- **The despawn timer running.** It was Off on all 38 bots and had never swept
  at measurement time. The claim that it would delist 80 tranches at a 30-day
  threshold was arithmetic over the state file, not an observed sweep.
- **The stack side.** 0 stack tranches existed at measurement time, so the
  mirror panel was not evaluated.

## Falsification

This evaluation is wrong if:

(a) `_create_fold_tranches_tab` reads a field this document does not name;
(b) the executor fold predicate stops being `ticker.last <= ref * otd_factor`
in `_fold_eligible_tranches`, with `otd_factor` from `otd_math`, which would
reopen F1;
(c) `created_ts` is absent from any tranche created after 2026-08-23, which would
void the Age answer;
(d) the F3 fix regresses — `clear_fold_tranches` or `clear_pending_wire_credits`
stops reaching `_settle_after_clear` before the panel is closed;
(e) the state file read here was not the file the running application wrote at
17:32:18 on 2026-08-23;
(f) the offscreen stub diverges from the live bot in any attribute the tab reads.
The stub supplies `_fold_tranches`, the three lifetime counters,
`_pending_wire_credits`, `_pending_wire_ledger`, `config` and `get_status`, and the
tab reads nothing else.
