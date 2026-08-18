# Bot Interoperability + USD-Denominated Trading — Audit + Design

Date: 2026-07-27. Version at audit: v3.23.40.

Deliverable this pass:
- LTM refresh + audit of the current interop code (capital reservation,
  sibling attribution, multi-bot-on-same-base scenarios).
- Root-cause diagnosis of the “two BTC bots fight and eat each other”
  behaviour.
- Design proposal covering: USD-denominated Target Balance + base-
  currency settlement (BTC/ETH quote pairs), Sat↔USD + Wei↔USD rate
  monitor with Indicator Voting Panel display, multi-bot capital
  isolation on shared base wallets, BTC:alt → BTC:USD profit routing.
- Concrete first ship: currency rate monitor + IVP header display.

---

## Part 1 — LTM findings

- `reference_runtime_layout.md:17` — `reservation_state.json` (~5.6 MB)
  exists at `~/.acervator/`, persists live `CapitalRegistry + Arbiter`
  state. Operator ruling 2026-06-13: “wallet doesn't matter in sim” —
  sim ignores reservations; live consults them.
- `feedback_no_bridges_sim_live.md:19` — sim path has
  `sim_capital_reservation.py` forked to prevent bridge back to live
  registry.
- `MEMORY.md:13` — reservation_state.json is a first-class runtime
  artifact under `~/.acervator/`.

No memory entry mentions the “two BTC bots fight” symptom directly.

---

## Part 2 — Interop audit

### 2.1  The registry exists and is well-designed

`src/trading/capital_reservation.py:149` `CapitalReservationRegistry`
— 649 lines. Provides `reserve(bot_id, asset, qty, reason)`,
`release(token)`, `update(token, new_qty)`, `effective_available(bot_id,
asset, total_holdings)`, `heartbeat(bot_id)`, `prune_expired()`,
`force_release()`. State persists to `~/.acervator/reservation_state.json`.
Heartbeat TTL 120 s; restart grace 60 s.

Invariant (line 51-61):

> Total reservations on an asset MUST NOT exceed the bot's own declared
> holdings. Registry view is authoritative for all bots inside the
> platform; exchange balance is the ultimate truth.

Design intent (operator quote at line 4-15) covers *exactly* the
symptom operator now reports:

> "a graceful solution for preventing overlapping Scrumming Bots
> attempting to sell excess Base Currencies… So if I have a $100 ETH
> Extractor running then this field will tell the Scrumming Bot to
> start ignoring $100 of the ETH budget."

### 2.2  BUT — ScrummingBot only READS, never RESERVES

Repo grep across `src/trading/scrumming_bot.py` shows:

| Call | Location | Behaviour |
|---|---|---|
| `_crr_reg.effective_available(...)` | line 9446 | READ — subtracts others' reservations from available |
| (no `reserve(...)` call anywhere) | — | ScrummingBot never registers its own claim |

Compare to `src/trading/extractor_bot.py`:

| Call | Location | Behaviour |
|---|---|---|
| `_crr_reg.reserve(...)` | line 323 | RESERVES its chunk at init |
| `_crr_reg.update(token, new_qty)` | line 447 | RESIZES its claim on target change |
| `_crr_reg.release(token)` | line 497 | RELEASES on destroy |
| `_crr_reg.heartbeat(bot_id)` | line 1461 | Pulses per tick |

**Consequence**: ScrummingBots correctly avoid Extractor-reserved
capital, but two ScrummingBots on the same base see each other as
unclaimed capital. **F62** — root cause of the "two BTC bots fight
each other" symptom.

### 2.3  Sibling attribution layer is init-time only

`scrumming_bot.py:4130-4160` (chunk-claim during first tick) does look
at `_bot_manager.sum_sibling_tracked_units(bot_id, target_asset)` and
refuses to claim more than the free portion of the exchange pool. This
handles first-launch correctly.

But once the bot is running, it does not re-check per tick. Assumptions
that the initial claim persists implicitly through `_main_lots`
accounting break when: (1) the sibling bot is created LATER, (2) either
bot restarts (state re-hydrates without cross-bot arbitration), (3)
the operator holds base outside any bot (the “$500 BTC personal +
$200 bot” scenario the operator described). All three trigger the
symptom.

### 2.4  BTC/ETH quote pairs — current handling

`bot_container.py` BotConfig has `symbol: str` (e.g., `"XRP/USD"`,
`"XRP/BTC"`) but no explicit “quote asset” field. Downstream code
splits `symbol` on `"/"` and treats index 1 as the quote for size
math. Target Balance is a float with no unit annotation. **The
codebase assumes quote == USD.** For BTC-quoted pairs (e.g. `XRP/BTC`),
the bot silently interprets `target_balance = 50` as *50 BTC of XRP*,
not *$50 USD of XRP* — off by five orders of magnitude at current
prices.

**F63** — Target Balance has no unit annotation; USD assumption
hardcoded in size math.

Verified no `usd_denominated_target` or equivalent flag on `BotConfig`
(grep for `denom`, `usd`, `quote_asset`, `base_currency` in
bot_container.py returns nothing that switches interpretation).

### 2.5  Profit routing — current options

`bot_container.py:105` `profit_route: str` values:
`fold_to_target | spendable | split | cross_bot`. The `cross_bot`
path can route to any target bot ID (raw string). Operator directive
2026-07-27:

> "I want the option to route BTC / ETH alt pairing profits to their
> respective USD bot stack tranches for optimal USD value capture."

Interpretation: an alt-pair bot (e.g. `XRP/BTC`) folding to a
`BTC/USD` bot's Stack Tranches. `cross_bot` already exists but:
- Does not automatically identify the “respective USD bot” — needs
  operator to type the bot id.
- Does not route into Stack Tranches specifically — routes into the
  target bot's target_balance via wire manager.

**F64** — cross_bot exists; auto-routing to a symmetric BTC/USD or
ETH/USD bot's stack tranche pool needs a new profit_route value
(e.g. `parent_base_usd_stack`) or an auto-resolver.

---

## Part 3 — Design proposal

### 3.1  Fix F62 — ScrummingBot self-reserves

Every ScrummingBot's `__init__` calls `registry.reserve(bot_id,
target_asset, initial_claim_qty, reason)` after the sibling-attribution
init math computes its claim. Reservation is `update()`-ed whenever
`_target_balance` changes (operator top-up, compound growth, live
edit). Released on `close()`. Heartbeat wired to the tick loop.

Effect: two BTC ScrummingBots each register their claim; each sees
the other's claim excluded from `effective_available()`. They coexist
without eating each other. Same fix generalises to ETH, USDC, or any
shared base.

Additional field: `target_balance_reserve_units` on BotConfig — the
asset-unit equivalent of `target_balance` at the last known price.
Computed on each `_target_balance` change and rounded up
conservatively (10 % safety margin). This is what gets pushed to the
registry.

**Ships in cascade after operator approves; touches ScrummingBot
lifecycle so wants a green pin-test battery first.**

### 3.2  USD-denominated Target Balance + base-currency settlement (F63)

New BotConfig fields:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `target_balance_denom` | str | `"quote"` | `"usd"` \| `"quote"`. When `"usd"`, `target_balance` is interpreted as USD regardless of the pair's quote. |
| `settlement_currency` | str \| None | None | Explicit override of the quote currency for trade execution. When None, derived from `symbol.split('/')[1]`. |

Bot init at symbol `"XRP/BTC"` with `target_balance=50`,
`target_balance_denom="usd"`, `settlement_currency=None`:

- Bot computes: *"I want to hold $50 USD of XRP, buying and selling
  in BTC."*
- Every tick: fetch XRP/USD spot (via existing rate monitor, § 3.3),
  compute `xrp_units_target = target_balance_usd / xrp_usd`. This
  is the bot's *effective target in the target asset*.
- Delta calculation: `current_xrp_units * xrp_usd - target_balance_usd`.
  A `-$5` delta triggers a buy of `5 / xrp_usd` XRP, quoted in BTC
  as `5 / btc_usd`.
- Order placement: same `_execute_buy` path but uses the *base-quoted*
  side of the pair (XRP/BTC) rather than a USD-quoted synthetic.

Rate feed dependency: **needs XRP/USD price and XRP/BTC price on
each decision tick.** Coinbase (and most exchanges) list both. When
one is missing, fall back to `xrp_usd = xrp_btc × btc_usd` (both
of which we have from the currency-rate monitor + the pair's own
ticker).

**Impact surface**: `_delta()`, `_execute_buy()`, `_execute_sell()`,
`get_status()` (P&L reporting), and the Bot Details Status tab
(display USD not quote units). Non-trivial but bounded — the math
lives in one place.

### 3.3  Sat/Wei/BTC/ETH rate monitor (ships this cascade)

- **New: `src/exchange/currency_rate_monitor.py`** —
  `CurrencyRateMonitor` singleton polls any connected exchange for
  `BTC/USD` and `ETH/USD` tickers on a 60 s cadence. Computes derived
  rates:

    sat_per_dollar        = 100_000_000 / (BTC/USD)
    sat_per_cent          = 1_000_000 / (BTC/USD)   [= 1e8 × 0.01]
    wei_per_dollar        = 1e18 / (ETH/USD)
    wei_per_cent          = 1e16 / (ETH/USD)

  Emits `CurrencyRates` dataclass on every refresh; exposes
  `snapshot()` for pull-based consumers.

- **IVP header row** — insert a compact `QLabel` (Consolas 10 pt) into
  `_setup_ui` between the TF Lock row and the QTableWidget. Text:

      BTC ${btc_usd:,.2f}   1$ = {sat_1:,} sat / 1¢ = {sat_c:,} sat  │  ETH ${eth_usd:,.2f}   1$ = {wei_1:,} wei / 1¢ = {wei_c:,} wei

  New method `IndicatorVotingPanel.update_currency_rates(rates)`.
  Cached; refreshed by main_window on the dashboard tick.

- **Additional bot-context injection**: when the bot selector picks a
  bot whose base currency is BTC or ETH, add a third column showing
  “1 {base} = ${base_usd:,.2f} = {base_units_target:,.8f} {target_asset}”.

**No BotConfig / runtime-math changes.** Pure display + monitor.

### 3.4  Multi-bot base-wallet isolation (F62 + operator hold-personal scenario)

Two layers:

1. **Registry self-reservation** (§ 3.1) — solves the two-bots-on-same-
   base fight.
2. **Operator hold-out reservation** — new BotConfig field:
   `personal_hold_qty: float = 0.0`. Sums into a synthetic “operator”
   reservation on the registry keyed as `bot_id="__operator_hold__"`,
   never expires, never heartbeats. Each bot's registry consult excludes
   this from available. Operator scenario “$500 BTC personal + $200 bot”
   is expressed as `personal_hold_qty = 500 / btc_usd` on the bot at
   creation time.

Alternative interface: single global “held out” setting on the main
window under a **Wallet Holdings** panel — the operator declares
“reserve 0.008 BTC for personal use” once and every bot on BTC sees
it excluded. Simpler UX, one setting instead of per-bot.

### 3.5  BTC:alt → BTC:USD profit routing (F64)

New `profit_route` value: `"base_usd_stack"`. When selected:

1. Resolve at commit time: find the bot with symbol
   `{settlement_currency}/USD` (e.g. `BTC/USD` for a `XRP/BTC` bot).
2. On profit realization, funnel the profit into the resolved bot's
   `_stack_tranches` ledger as an additional pending credit tagged
   with the source bot id + “alt pair inflow” reason.
3. The BTC/USD bot processes the credit as if it were realized profit
   on its own trades — it feeds the next SCRUM's Stack tranches at
   the operator's configured spacing.
4. If the resolver finds no matching BTC/USD bot, refuse at commit
   with a wizard warning (or fall back to plain `cross_bot` with
   operator-typed target).

---

## Part 4 — Findings summary

| # | Severity | Finding |
|---|----------|---------|
| **F62** | **Broken** | ScrummingBot doesn't reserve its own capital in the registry → two BTC bots collide. Fix: § 3.1. |
| **F63** | Design gap | Target Balance has no unit annotation; USD assumption hardcoded → BTC/ETH quote pairs mis-sized by 5+ orders of magnitude. Fix: § 3.2. |
| F64 | Design gap | cross_bot routing works but doesn't auto-target the symmetric BTC/USD stack tranche pool. Fix: § 3.5. |
| F65 | Design gap | No place for operator to “hold out” personal balance from a bot's registry view. Fix: § 3.4. |
| F66 | UX | Sat/Wei/BTC/ETH context absent from the panel. Fix: § 3.3 (ships this cascade). |

---

## Part 5 — Ships this cascade

- Currency rate monitor + IVP header display (§ 3.3). No trading-math
  changes, low risk, immediate operator value.

## Part 6 — Operator decisions requested before implementation

Deep architectural changes need alignment before implementation.
Numbered for a quick answer per line:

1. **F62 fix** — should ScrummingBot self-reserve default to *on* for
   new bots and *migrated on next launch* for existing bots?
2. **F63 fix** — operator visibility: expose `target_balance_denom` as
   a wizard combo (`USD | quote currency`) or as an implicit flag
   inferred from pair (USD when quote is USD, else prompt)?
3. **F63 fix** — for USD-denom on non-USD pairs, source XRP/USD
   directly from a ticker call, or derive via
   `xrp_usd = xrp_btc × btc_usd`? (Latter avoids a second API call
   per tick.)
4. **F64 fix** — new `base_usd_stack` route or overload `cross_bot`
   with a resolver flag?
5. **F65 fix** — per-bot `personal_hold_qty` field, or a single
   global Wallet Holdings panel?
