# § 1 Trading Parameters — Stack Mode redesign (Phase 2 design proposal)

Operator directive 2026-07-25:

> "For Bulk Trading, I should have called this Stack Mode. The Stacks
> would essentially be Tranches that Sell instead of Buy where a given
> Fold is Split upwards across a price range. Given this, we will want
> to create a Stack Tranches tab to display this positions and their
> activity. Stack Tranches must match Fold Tranches in styling. A new
> Split Distance setting will be required to complete this redesign.
> Also of note, is that the first order listed in the Split Stack will
> always be at the Minimum Opposing Trade Distance. Invisible Mode just
> means the Tranches / Stack is track[ed] internally / off-books until
> price levels are met or exceeded. If the Stacks are Visible then the
> Tranches can be listed normally under the appropriate conditions in
> accordance with the Split Distance. Aggressive Trading mode forces
> all trades to execute as Taker Orders."

**Nothing below is implemented.** This is a proposal to align on
scope before touching engine code. Approve / adjust / reject in a
reply, and I execute in tranches.

**FALSIFICATION**: the design below is wrong if I've misread the
operator's spec, if the “Minimum Opposing Trade Distance” I identify
is not the field the operator means, or if any file I list as
affected is actually consumed on a path I missed.

---

## Reflected understanding (in my own words — correct anything wrong)

1. **What a Stack is**: the mirror-image of a Fold. Fold tranches BUY across a downward price range; Stack tranches SELL across an upward price range. Each Stack tranche represents a portion of an eventual SCRUM (sell) that would otherwise fire as a single order.

2. **How a Stack is created**: when a bot decides to SCRUM at price `P`, instead of firing one sell for the full size, it splits that sell across N tranches placed at:
   - Tranche 1: `P × (1 + min_opposing/100)` — where `min_opposing` is the existing `scrumming_interval_pct` opposing-hysteresis distance. This is the same price a normal SCRUM would have fired at.
   - Tranche 2: `Tranche 1 × (1 + split_distance/100)`
   - Tranche 3: `Tranche 2 × (1 + split_distance/100)`
   - …up to N tranches (see Open Question #1 on where N comes from).

3. **Visible vs Invisible Stack**:
   - **Visible** (`visibility="orderbook"`): Stack tranches are RESTING LIMIT SELL orders on the exchange order book at the computed price levels. The exchange fills them naturally as price rises.
   - **Invisible** (`visibility="internal"`): Stack tranches are tracked in the bot's internal ledger only. When price crosses a tranche's level, the bot fires a MARKET SELL for that tranche's size. No orders sit on the book.

4. **Aggressive Trading redefinition**: when ON, ALL trades (Fold + Scrum + Stack tranches + manual fire) execute as **taker orders** — i.e., market orders or IOC/aggressive limits designed to cross the spread and pay the taker fee for immediate fill. When OFF, the bot may use passive maker orders when appropriate.

5. **Stack Tranches GUI tab**: mirror of Fold Tranches tab. Same visual grouping (Cycle Health summary + per-tranche detail rows). Read from a new `_stack_tranches: list[dict]` runtime state on ScrummingBot.

---

## Files affected (by change)

### BotConfig schema — `src/trading/bot_container.py`

| Change | Effect |
|---|---|
| Rename `bulk_trading` → `stack_mode` (bool) | breaks any consumer that still references old name (audit showed 1: the Settings widget init) |
| Add `split_distance: float = 1.0` (%) | new field, spacing between successive Stack tranches |
| Add `stack_tranche_count: int = ?` (int) | see Open Question #1 |
| Remove `bulk_partial_on_return` OR redefine as `stack_partial_on_return` for the analogous partial-fill-when-price-retreats case | see Open Question #4 |

Also update `_BOT_CONFIG_SCRUMMING_ONLY_FIELDS` allowlist.

### Runtime state — `src/trading/scrumming_bot.py`

| Change | Effect |
|---|---|
| Add `self._stack_tranches: list[dict] = []` at `__init__` (mirror of `_fold_tranches`) | new ledger |
| Add `self._stack_created: int = 0` (counter) | mirror of fold counters |
| New method `_split_scrum_into_stack(scrum_price, scrum_size)` | returns list of tranche dicts `{units, price, side="sell", state="pending"}` |
| Modify SCRUM firing path (currently a single `_execute_sell`) to branch on `self.config.stack_mode`. When true, populate `_stack_tranches` instead of firing immediately (Invisible) OR place limit orders (Visible) then track their fill state | main behavior change |
| Add per-tick check: iterate `_stack_tranches`, fire market sell for any whose price threshold is crossed (Invisible mode) or reconcile with exchange fills (Visible mode) | new tick-time loop |
| Aggressive Trading enforcement: in every `_execute_buy` / `_execute_sell` path, when `self._aggressive`, force `order_type="market"` (or IOC limit crossing spread) | modification to existing execute paths |
| Invisible Mode semantic change: `self._invisible` still gates market-vs-limit for the FIRST order, but Stack tranches now respect the same flag (Visible = limits on book; Invisible = internal ledger + market fires on threshold cross) | consistency |

### GUI — `src/gui/bot_live_settings.py`

| Change | Effect |
|---|---|
| Widget label: “Bulk Trading” → “Stack Mode” | operator-visible |
| New QDoubleSpinBox: `Split Distance:` (%, likely 0.1-20 range mirroring `scrumming_interval_pct`) | operator-visible |
| Possibly a new QSpinBox: `Stack Tranche Count:` if operator wants to control N (Open Question #1) | operator-visible |
| New `_create_stack_tranches_tab()` method — clone of `_create_fold_tab()`, reads from `self._bot._stack_tranches` | operator-visible |
| Register the new tab in the tabs.addTab block at line ~154 | operator-visible |

### GUI — `src/gui/main_window.py`

| Change | Effect |
|---|---|
| Rename kwarg `bulk_trading` → `stack_mode` in the make_bot_config restore path | prevents TypeError |
| Add `split_distance` kwarg | new |
| Add `stack_tranche_count` kwarg if applicable | new |

### Pin tests — `tests/`

| Change | Effect |
|---|---|
| `test_stack_mode_pins.py` — assert BotConfig has `stack_mode` + `split_distance` + `stack_tranche_count`; old `bulk_trading` / `bulk_partial_on_return` fields are gone; Stack Tranches tab exists; Aggressive path forces market order type | prevents drift |

---

## Open questions (need operator judgment)

1. **How is N (tranche count) chosen?** Three possibilities:
   - **(a) Operator sets it** as `stack_tranche_count: int` in Settings (e.g., 3, 5, 10). Simplest.
   - **(b) Derived from the SCRUM size** — e.g., 1 tranche per `investment_amount / target_balance` unit. Adaptive.
   - **© Fixed constant** (e.g., always 3). No config surface.

   My recommendation: **(a)** — explicit control, simplest reasoning, easy to demo the mechanism.

2. **Split Distance unit**: **percent** (like `scrumming_interval_pct`) or **absolute price** (like `max_entry_price`)? Percent scales naturally across price ranges; absolute is more intuitive for a specific pair. My recommendation: **percent**.

3. **Split Distance range**: what's a sensible min/max? `scrumming_interval_pct` is 0.1-20. I'd propose the same: 0.1-20%.

4. **`bulk_partial_on_return` fate**: does the Stack Mode redesign have an analogous “partial-fill-if-price-retreats” concept? For Fold it's “if price rises above a passed BUY tranche, exclude it from the fold”. For Stack (sells), the analog would be “if price falls below a passed SELL tranche before it fires, exclude it from the stack.” I lean **YES this concept survives** — but the operator should confirm. If yes: rename field to `stack_partial_on_return`. If no: retire the field.

5. **Aggressive Trading — Taker enforcement mechanism**: on Coinbase Advanced Trade the taker vs maker distinction is (a) market orders are always taker, (b) limit orders that cross the spread at placement are taker, © limit orders that rest on the book are maker. Simplest implementation: when `self._aggressive` is ON, force `order_type="market"` for every non-manual order. Does this match the operator's intent, or should there be nuance (e.g., use IOC limits for slippage protection)?

6. **Stack Tranches tab scope**: mirror of Fold Tranches includes both (a) Cycle Health summary at top and (b) per-tranche detail cards. Should the Stack Tranches tab also include © unrealized P/L per tranche (mark-to-market against current price) and (d) “would fire in ±X%” distance projections? The operator said “match Fold Tranches in styling” — I read that as scoped to the same shape, not adding new columns. Confirm?

7. **Backwards compatibility for existing bot_state.json**: bots already saved with `bulk_trading: false` will restore against the new `stack_mode` field name. I'd add a kwarg-adapter that maps `bulk_trading` → `stack_mode` in the restore path so existing bot_state files don't fail on load. Confirm this compatibility is wanted, or hard-cut the old name?

8. **The `TradingParamsPage` in `bot_wizard.py`** may still expose a widget that says “Bulk Trading” or references the old name. If so, wizard needs a matching update. I'll enumerate before making the rename.

---

## Proposed execution sequence (once Phase 2 is approved)

**Sub-phase 2A — schema + rename**
- Rename `bulk_trading` → `stack_mode` in BotConfig, kwarg allowlist, restore paths
- Add `split_distance` + `stack_tranche_count` fields with sane defaults
- Adapter for old `bulk_trading` kwarg in restore path (Open Q #7)
- Update Settings widget label + add Split Distance widget + optional Tranche Count widget
- Pin tests for the rename + new fields
- Cascade v3.23.25 → v3.23.26 (schema change only, no runtime behavior yet)

**Sub-phase 2B — engine: Stack Tranche machinery**
- Add `self._stack_tranches` ledger + `_stack_created` counter
- Implement `_split_scrum_into_stack(price, size)`
- Modify SCRUM firing path to branch on `stack_mode`
- Add tick-time Stack reconciliation (Invisible: fire-on-threshold; Visible: reconcile with exchange fills)
- Pin tests for the stack-splitting logic (pure function: given P, size, distance, N → returns tranche list)
- Cascade v3.23.26 → v3.23.27

**Sub-phase 2C — Invisible Mode semantic tightening**
- Verify `self._invisible` gates Stack tranche placement correctly (limits vs internal)
- Update tooltips + docstrings to reflect the redefined semantic
- Pin tests for both mode paths
- Cascade v3.23.27 → v3.23.28

**Sub-phase 2D — Aggressive Trading taker enforcement**
- Modify `_execute_buy` / `_execute_sell` / Stack fires to force market when `_aggressive`
- Pin test: with `_aggressive=True`, any executed order sent to `guarded_place_order` has `order_type="market"`
- Cascade v3.23.28 → v3.23.29

**Sub-phase 2E — Stack Tranches GUI tab**
- Add `_create_stack_tranches_tab()` mirroring Fold Tranches
- Register in tabs
- R90 VCB visual-confirm render
- Pin tests + cascade v3.23.29 → v3.23.30

---

## Ready for your call

Answer the 8 open questions in-line or point-form, and I execute Sub-phase 2A. Or say “adjust the design as follows: …” and I revise the report before touching anything.
