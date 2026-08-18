# Multi-Base Coordination + Cross-Pair Intelligence — Design Plan

Author: session assistant. Date: 2026-07-28. Version at scan: v3.23.45.

Operator directive 2026-07-28:

> "we need every scrumming bot to be aware of all exchange rates
> available for its target asset (…) At no point have I been able to
> have two bots running the same target asset. We need this resolved
> (…) Either we resolve the common asset and coordination issue or
> we make the individual bots smarter so that they can trade against
> any available pair while primarily preserving the USD value level
> (…) additional rows added below the Target USD field that states
> the value in BTC and ETH if the pair is available and additionally
> the Target Delta for the BTC and ETH exchange rates should be
> stated as a %."

Screenshot at time of directive: bot `bc469d79`, pair `ETH/BTC`,
Target `$200.0000` white, Ammo `$200.0000` red, 18 trades.

## 1  Diagnostic — what the red `$200` in the screenshot means

The second money column is the **Ammo delta**, computed at
[main_window.py:1442](src/gui/main_window.py:1442) as
`position_val - target_val` and coloured red when the delta is
below `-max(target × 0.001, $0.01)`.

The specific branch that renders `$200 red` when the target is `$200`
is [main_window.py:1423-1432](src/gui/main_window.py:1423): reached
when **both** `position_val <= 0` AND `holdings <= 0`. In that branch
`delta = 0 - target_val = -$200` and Ammo prints the magnitude.

`position_val` is `holdings × current_price × quote_to_usd`
([main_window.py:1409](src/gui/main_window.py:1409)). Zero means one
or more of those three components is zero.

Combined signal: **18 trades executed → 0 holdings on an ETH/BTC bot
with a $200 USD target**. Two possible root causes:

  1. Bot legitimately sold its ETH accumulation back to zero and is
     waiting to buy again. Plausible for a scrumming pass after a
     price spike; would flip to Ammo-neutral once it buys back in.
  2. Over-reservation on ETH bricked the bot's sells (see §2.1)
     OR wrong `current_price` interpretation on BTC-quoted pairs
     caused reservation qty to be wildly wrong (see §2.2), and one of
     those cascaded into a state where the tick loop reports zero.

The screenshot alone can't discriminate, but §2 identifies two
concrete correctness bugs that fit the "two bots on same asset can
never coexist" symptom.

## 2  Diagnostic — why coordination is still broken

The `CapitalReservationRegistry` **is** in place, **is** asset-keyed
(so ETH/USDC and ETH/BTC bots both reserve against `"ETH"`), and the
sell-side gate in
[scrumming_bot.py:9150-9184](src/trading/scrumming_bot.py:9150) does
query `effective_available()` correctly. Yet the operator reports
"at no point have I been able to have two bots running the same
target asset." Two bugs explain that.

### 2.1  Over-commit is silently allowed

`_ensure_capital_reservation` at
[scrumming_bot.py:738](src/trading/scrumming_bot.py:738) calls
`reserve()` and `update()` **without** passing `total_holdings`. The
registry's over-commit check at
[capital_reservation.py:309](src/trading/capital_reservation.py:309)
only fires when `total_holdings is not None`. Consequence: two bots
on ETH each successfully reserve `target/price × 1.10` ETH; nothing
rejects the second reservation even though combined reservations now
exceed actual exchange holdings.

Cascading failure mode: `effective_available()` for either bot
returns `holdings − other_bot_reservations`, which now underflows.
Bot A's sells get refused with a "capital reservation" message. Bot A
looks broken to the operator.

### 2.2  Reservation qty formula assumes USD price on non-USD pairs

`_compute_reservation_qty` at
[scrumming_bot.py:716](src/trading/scrumming_bot.py:716) computes
`target_balance / current_price × 1.10`. `target_balance` is in USD.
`current_price` on an ETH/BTC bot is **ETH-priced-in-BTC** (e.g.
`0.06` BTC per ETH), not USD-per-ETH.

Consequence: `200 / 0.06 = 3,333` ETH reserved on an ETH/BTC $200
bot, versus the correct `200 / 3000 = 0.067` ETH. The bot claims
50,000× more ETH than it owns, and any other ETH bot instantly
hits over-commit refusals when it tries to sell.

Fix requires the CRR call to divide by USD-per-target-asset, not by
`current_price`. `quote_to_usd` is already exported from status
([main_window.py:1408](src/gui/main_window.py:1408)) and
`CurrencyRateMonitor` at
[currency_rate_monitor.py:1](src/exchange/currency_rate_monitor.py:1)
already provides BTC/USD + ETH/USD. So the USD-per-target-asset
number is derivable today — the CRR call just needs to consume it.

### 2.3  Neither bug has a test

`tests/test_scrumming_capital_reservation.py` covers the happy path
and the over-holding refusal, but does not assert:
  - `reserve()` was called with a `total_holdings` argument, and
  - the qty passed corresponds to USD-target ÷ USD-per-asset.

Adding those two assertions would have caught both bugs the day the
CRR wiring landed.

## 3  Approach options

### Approach A — Registry-first coordination (evolves what exists)

Fix the two bugs in §2. Every bot still declares one pair. The CRR
becomes a correct arbiter for target-asset ownership across bots.
Add "who else is on this asset" telemetry so the operator can see
the contention state in the GUI.

Pros:
  - Minimal architectural change; no new abstraction.
  - Directly addresses the correctness failure the operator sees.
  - Zero risk of behavioural surprise on existing bots — the code
    path is already there, we're closing gaps in it.

Cons:
  - Doesn't give the operator the "smart bot" behaviour they hinted
    at (cross-pair opportunistic execution). Each bot still trades
    only its declared pair.

### Approach B — Multi-pair opportunistic execution

Rewire scrumming so each bot declares a **target asset** and a
**USD target** but not a fixed pair. On each tick the bot scans all
pairs on the exchange trading the target asset, ranks them, and
routes the tick's action (buy / sell / hold) through whichever pair
has the best price divergence right now.

Pros:
  - Gives the intelligence the operator described. Automatically
    exploits cross-pair moves.
  - Removes the "one pair per bot" limitation entirely.

Cons:
  - Fundamental redesign. Entry cost basis, cost-basis accounting,
    fee-tier optimisation, order-book depth per pair all become
    non-trivial. Bot must maintain multiple base-currency claims in
    parallel (BTC and USDC and ETH pools).
  - Interacts poorly with the operator's directive that scrumming
    bots "should not have any multibase code or references" — B
    reintroduces the same kind of complexity, just spread across a
    routing layer instead of an internal ledger.
  - Behavioural changes to shipping bots are large; a bot that has
    been running on ETH/USDC for months will suddenly execute on
    ETH/BTC without operator opt-in.

### Approach C — Hybrid (RECOMMENDED)

Do Approach A now for correctness. Add a **read-only** cross-pair
awareness layer that shows the operator the divergence in the GUI
per the explicit request. Leave the option to make it executable
later.

Concretely:

  1. **Correctness cascade (v3.23.46)** — fix §2.1 (pass
     `total_holdings`) and §2.2 (USD-denominated reservation qty).
     Add regression tests for both. Ship.

  2. **Awareness cascade (v3.23.47)** — new `MarketPairsScout`
     module. Polls `get_all_tickers()` on a 60-90 s cadence, groups
     tickers by base asset, exposes:
       `pairs_for(asset) -> list[PairSnapshot]` where each snapshot
       carries `symbol`, `quote_currency`, `last_price`, `pct_24h`,
       and `usd_per_asset` (via the CurrencyRateMonitor for BTC/ETH
       conversion). Reuses the CCXT `get_all_tickers` path
       ([ccxt_connector.py:838](src/exchange/ccxt_connector.py:838))
       — one bulk call per exchange, cheap.

  3. **GUI cascade (v3.23.48)** — operator's explicit request:
     under the Target USD row in Bot Details Status tab, add two
     rows:
       `Target BTC: 0.00325 BTC   (Δ24h vs USD: −1.4 %)`
       `Target ETH: 0.06452 ETH   (Δ24h vs USD: +2.1 %)`
     Where "Δ24h vs USD" is the target asset's 24h % move in that
     denomination minus its 24h % move in USD. A positive Δ means
     the base currency (BTC or ETH) weakened vs USD — a BTC-quoted
     buy today is cheaper in USD terms than yesterday.
     Only show rows for pairs the exchange actually lists.

  4. **Optional smart-execution cascade (v3.23.49+, pending
     operator sign-off)** — extend `ScrummingBot` to consult the
     scout on each tick and, when Δ24h vs USD exceeds a threshold
     (operator-configurable, default 3 %), route the tick's trade
     through the divergent pair instead of the declared pair. This
     is the "make the bot smarter" ask. Requires the scout to be
     stable and the operator to have seen a session of read-only
     divergence data before committing.

Approach C is the recommendation. It closes the correctness gap
immediately, gives the operator the visibility they asked for
without waiting, and preserves the option to go smart-bot in a
subsequent cascade once we have data on how often meaningful
divergence actually appears.

## 4  UI design — target rows

Per operator directive: "additional rows added below the Target USD
field that states the value in BTC and ETH if the pair is available
and additionally the Target Delta for the BTC and ETH exchange rates
should be stated as a %."

The Target USD field lives in the Bot Details **Status** tab. Not to
be confused with the two-column table Ammo/Target that lives in the
main Bots list; the operator's directive references the Details
panel where per-bot summary lines are laid out vertically.

Proposed rendering:

```
Target USD:  $200.0000
Target BTC:  0.00325 BTC   (Δ24h vs USD: −1.4 %)
Target ETH:  0.06452 ETH   (Δ24h vs USD: +2.1 %)
```

Row layout rules:
  - Show the BTC row iff the bot's target asset trades a
    `<target>/BTC` pair on the bot's exchange.
  - Show the ETH row iff a `<target>/ETH` pair exists.
  - If the bot's target asset is BTC itself, omit the BTC row (self-
    reference is meaningless). Same for ETH.
  - Value = `target_usd / (BTC/USD from CurrencyRateMonitor)`
    (or ETH/USD), formatted 4-6 decimals depending on magnitude.
  - Δ24h vs USD = `pct_24h(<target>/BTC) - pct_24h(<target>/USD)`
    computed from the scout snapshot. Formatted `+X.X %` /
    `−X.X %`. Colour: green positive, red negative, grey ≤ 0.1 %.
  - If the scout hasn't populated yet (fresh process), show
    `pending…` rather than `$0` or `0 %`.

The Δ interpretation is the operationally meaningful one: it tells
the operator whether trading through the BTC-quoted pair is cheaper
or more expensive right now than trading through the USD-quoted
pair — the exact insight the smart-execution cascade would consume.

## 5  Correctness fixes in detail (v3.23.46 scope)

### 5.1  Pass `total_holdings` on reserve() and update()

At [scrumming_bot.py:769](src/trading/scrumming_bot.py:769) and
[scrumming_bot.py:791](src/trading/scrumming_bot.py:791), add
`total_holdings=<the exchange balance of the target asset>` to
both calls. Source of truth: the bot already knows this via
`self._current_holdings` (post v3.23.43) which sums `_main_lots`,
but that's the bot's own claim — the registry needs the **exchange
balance** so it can enforce the invariant across all bots.

Two options for the exchange balance:
  a. Poll `exchange.get_balance(asset)` synchronously in the ensure
     path. Adds a per-tick API call which is expensive.
  b. Read from the cached balance snapshot the tick loop already
     maintains ([scrumming_bot.py:_current_holdings]) — but scale
     it up by *N* if we want the invariant to be "reservations
     across all bots ≤ actual exchange balance."

Recommendation: option (b), and add a bot-container-level periodic
task that pushes exchange balance into a `TotalHoldings` service
that CRR consults. Every 30 s is plenty — reservation qty drift
tolerance is already 1 % (see
[scrumming_bot.py:790](src/trading/scrumming_bot.py:790)).

### 5.2  USD-denominated reservation qty

Change `_compute_reservation_qty` at
[scrumming_bot.py:716](src/trading/scrumming_bot.py:716) to divide
by USD-per-asset, not by the pair's `current_price`. Source of
USD-per-asset:

  - For USD/USDC quoted pairs: `current_price` itself (unchanged).
  - For BTC quoted pairs: `current_price × btc_usd` (btc_usd from
    CurrencyRateMonitor).
  - For ETH quoted pairs: `current_price × eth_usd`.
  - Generic path: `current_price × quote_to_usd`, and export
    `quote_to_usd` from the bot's status (it already is, per
    [main_window.py:1408](src/gui/main_window.py:1408)).

Pin test: two ETH bots on different quote currencies, both with
`target_balance = $200` at an ETH price of $3000, should each
reserve ~0.067 ETH — not 3,333 ETH.

### 5.3  Regression tests

Two new tests in `tests/test_scrumming_capital_reservation.py`:
  - `test_reserve_passes_total_holdings_argument` — asserts CRR
    `reserve()` was called with a non-None `total_holdings`.
  - `test_reservation_qty_is_usd_denominated_on_btc_quoted_pair`
    — creates an ETH/BTC bot with $200 target and BTC price
    context, asserts qty ≈ 0.067 ETH (not 3,333).

## 6  Cascade sequence

| # | Version   | Deliverable | Effort |
|---|-----------|-------------|--------|
| 1 | v3.23.46  | §5 correctness fixes + tests | ~2 h |
| 2 | v3.23.47  | `MarketPairsScout` module + wire into `ScrummingBot` as read-only field + tests | ~3 h |
| 3 | v3.23.48  | GUI Target-BTC / Target-ETH rows + Δ24h vs USD | ~2 h |
| 4 | v3.23.49  | *(optional)* smart-bot pair-routing under operator threshold | ~6-8 h + sim validation |

Cascades 1-3 are additive and low-risk. Cascade 4 is a redesign and
should not proceed without a sim-first validation and explicit
operator sign-off.

## 7  What this plan does NOT do

  - It does not reintroduce multi-base attribution inside
    ScrummingBot. All of that machinery was correctly ripped in
    v3.23.43; the reintroduction would violate the operator's
    2026-07-25 directive.
  - It does not touch ExtractorBot's existing capital-reservation
    dance. ExtractorBot already passes `total_holdings` correctly
    (verified during recon; see extractor_bot.py's own
    `_ensure_capital_reservation` implementation for the reference
    pattern).
  - It does not attempt to solve cross-exchange coordination.
    Reservations remain per-exchange; a bot on Coinbase and a bot
    on Kraken don't contend even if they both target ETH. That
    scope belongs to a future cascade.

## 8  Adversarial verification (what would falsify §2's diagnosis)

  - **Falsifier for §2.1**: if I add a `reserve()` mock that
    inspects `total_holdings` and it's not None on trunk, the
    diagnosis is wrong. Verified today at scrumming_bot.py:769:
    the argument is not passed. Diagnosis stands.
  - **Falsifier for §2.2**: if `current_price` for an ETH/BTC bot
    already carries USD scaling somewhere upstream, the divide-by-
    pair-price is fine. Verified: `current_price` is written by
    `set_current_price` at scrumming_bot.py from the tick's
    exchange ticker, which is the raw pair price (BTC-denominated
    for BTC-quoted pairs). Diagnosis stands.
  - **Falsifier for the screenshot interpretation**: if the bot
    genuinely just sold to zero and is waiting to buy back, the
    Ammo=$200-red state is correct behaviour and only a UI
    freshness question. That's possible but doesn't explain the
    operator's "at no point" report — pattern is systematic, not
    incidental.

## 8.5  Prior-art research findings (added 2026-07-28 post-research)

Full report at
[docs/audits/2026-07-28_prior_art_multibase_coordination_research.md](docs/audits/2026-07-28_prior_art_multibase_coordination_research.md).
Bottom line: **Approach C is confirmed by external prior art.** Six
concrete findings the design must fold in:

### 8.5.1  Hummingbot is *behind* us on this problem

Hummingbot's XEMM validates inventory reactively (cancel on
insufficient balance), not proactively via reservation. Their
`balance limit` CLI is a static per-exchange ceiling, not a runtime
lock. No documented cross-controller reservation ledger exists in
Hummingbot V2. The `CapitalReservationRegistry` pattern is ahead of
the largest open-source trading framework — the correctness fix in
§5 is well-motivated, not backward.

### 8.5.2  The pattern has a name: **soft-lease**

Asset-keyed shared pool + named owners with reservation IDs +
monotonic-clock heartbeats + forced release on missed heartbeat +
atomic reserve/release under a single lock. This is the classic
distributed-lease pattern (Chubby / Zookeeper / etcd) applied to
in-process trading state. Documenting it by that name in
`capital_reservation.py` helps future contributors reason about it.

### 8.5.3  Explicit invariant to test in v3.23.46

The report calls out the exact invariant the correctness fixes must
enforce:

    sum(reservations_for_asset_A) + free_A <= exchange_balance_A

at every reserve/release/update step. This becomes the third
regression test (in addition to the two already listed in §5.3):
`test_invariant_sum_reservations_never_exceeds_holdings`.

### 8.5.4  DEX pathfinders are a bad analogy — reinforces "no B now"

1inch Pathfinder / Paraswap / Uniswap Auto Router solve one-shot
swap problems with no persistent inventory constraint. Borrowing
their routing model for a scrumming bot with a USD-target
invariant would be a category error. The correct analogues for
Approach B, if we ever go there, are the Barzykin/Bergault/Guéant
FX-dealer papers (arXiv 2207.04100, 2112.02269) — where the bot
already holds inventory and the decision is which pair *reduces
inventory imbalance most efficiently*, weighted by execution cost.
Different math, different data requirements.

### 8.5.5  Scout implementation refinements (v3.23.47 scope)

  - Cadence: start at **10 seconds** (report's suggested default),
    not 60-90 s as I initially wrote. `fetch_tickers` is a single
    bulk call per exchange, cheap.
  - Pair enumeration: `exchange.markets` post-`load_markets()` —
    `MarketPairsScout.pairs_for("ETH")` returns `[("ETH", "USDC"),
    ("ETH", "USD"), ("ETH", "BTC"), ...]` via iteration.
  - Coinbase caveat (ccxt issue #26170): `fetch_tickers` and
    `fetch_ticker` return different payload shapes on
    `coinbaseexchange`. The scout should always use `fetch_tickers`
    for consistency; do not mix.
  - Instrument the scout to record spread + 24h volume + last-price
    per pair so the data collected during v3.23.47's read-only
    period becomes the calibration input if we later promote to
    Approach B.

### 8.5.6  Falsifiers for later Approach B promotion

Concrete thresholds from the report (fold into §7 of the eventual
v3.23.49 sign-off gate):

  - Divergence > 2× execution cost, occurring on > 20 % of
    decision windows, for ≥ 2 consecutive weeks. Anything less and
    the routing complexity does not pay.
  - Operator regularly wants > 3 bots on the same base asset for
    legitimate reasons (N² contention makes registry costly).
  - Coinbase adds an account-level asset-lock API making the
    in-process registry redundant.

Any one of these triggers a real Approach B design conversation.
Absent them, C is the terminal state.

## 9  Ask

Two decisions from the operator before I start coding:

  1. Accept Approach C (recommendation) as the plan?
     Approach A alone is a fallback if the scout is considered
     out-of-scope; Approach B alone is not recommended.
  2. Accept the cascade order 1 → 2 → 3, deferring cascade 4
     pending operator sign-off after seeing the read-only
     divergence data?

If yes to both, I'll ship v3.23.46 first (correctness only, ~2 h,
no behavioural surprise) and pause for confirmation before starting
v3.23.47.
