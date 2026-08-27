# Prior-Art Research — Multi-Pair Inventory Management and Cross-Quote-Currency Routing

**Date:** 2026-07-28
**Author:** Deep-research agent (Opus 4.7 1M context)
**Consumer:** `docs/engineering-notes/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md`
**Question:** Does external prior art support Approach C (fix asset-keyed reservation + read-only cross-pair scout, defer dynamic routing) over Approach B (per-tick dynamic pair routing) for the Acervator scrumming bot?

**Bottom line up front:** Approach C is well-supported. No prior art we found treats the specific Acervator problem (multiple persistent-inventory scrumming bots on the same base asset across different quote currencies on one exchange, with a USD-value invariant) — the closest academic analogue (Barzykin/Bergault/Guéant FX market-making) treats a related-but-not-identical problem. All DEX-pathfinder analogues (1inch, Paraswap, Uniswap Auto Router, CoW Swap) solve a **one-shot swap** problem, not a persistent-inventory routing problem, and rely on much heavier infrastructure than the user should build in one hop. Cross-margin/portfolio-margin systems (Coinbase Prime, Kraken, FTX) validate the asset-keyed reservation shape but operate at exchange-account level, not bot-process level.

---

## 1. Cross-exchange / multi-pair market-making architectures

### 1.1 Hummingbot Cross-Exchange Market Making (XEMM)

The XEMM strategy runs on two venues: it posts limit orders on the less-liquid market and hedges via taker orders on the more-liquid market. Its inventory-management pattern is instructive for what it does **not** do.

- **Continuous validation, not pre-reservation.** Inventory sufficiency is checked in `c_check_if_sufficient_balance()`; orders are **cancelled** if balance becomes insufficient rather than blocked at creation. [VERIFIED via `https://hummingbot.org/strategies/v1-strategies/cross-exchange-market-making/`]
- **Static size gates.** Three config knobs bound risk: `order_size_taker_balance_factor` (default 99.5%), `order_size_taker_volume_factor` (default 25%), `order_size_portfolio_ratio_limit` (default 16.67%). These are per-strategy multipliers, not cross-strategy locks. [VERIFIED, same URL]
- **Cross-pair conversion is baked in.** `taker_to_maker_base_conversion_rate` and `taker_to_maker_quote_conversion_rate` let the strategy price across pairs when the base/quote don't literally match. [VERIFIED, same URL]

**Analogy caveat:** XEMM's cross-pair reasoning is between two venues on the same pair, not between two pairs of the same base asset on one venue. Adjacent, not identical.

### 1.2 Hummingbot Pure Market Making (PMM) + Inventory Skew

- PMM is **explicitly single-pair.** [VERIFIED via `https://hummingbot.org/strategies/v1-strategies/pure-market-making/`]
- `inventory_skew_enabled` + `inventory_target_base_pct` biases order sizes to maintain a target base/quote split — but only within one pair. [VERIFIED via `https://hummingbot.org/strategies/v1-strategies/strategy-configs/inventory-skew/`]

**Analogy caveat:** Inventory skew is the closest single-strategy analogue to Acervator's scrumming discipline. It confirms the "target-balance-anchored size adjustment" pattern is standard, but it does not touch the multi-strategy contention problem.

### 1.3 Hummingbot V2 Controllers + `balance limit`

Hummingbot V2 supports multiple controllers in one process. The nearest thing to Acervator's `CapitalReservationRegistry` is the `balance limit` CLI:

- **Static config, per exchange/asset.** `balance limit binance USDT 100` caps how much USDT any strategy on binance may treat as available. [VERIFIED via `https://hummingbot.org/client/global-configs/balance-limit/`]
- **No runtime coordination.** The doc explicitly frames the feature as "useful when running multiple bots on different pairs with same tokens" but it is **not** a runtime reservation — it is a global ceiling per (exchange, asset). If two bots each see the same 100-USDT ceiling they can still both place 100-USDT orders. [VERIFIED, same URL]
- **No documented cross-controller reservation ledger.** [UNVERIFIED-NEGATIVE — searched Hummingbot docs and V2 walkthrough; found no dedicated primitive.]

**Verdict for section 1:** Hummingbot has three partially-overlapping mechanisms (per-strategy sufficiency check, per-strategy inventory skew, and a static per-exchange balance ceiling), none of which is a runtime asset-keyed reservation across strategies. **The Acervator `CapitalReservationRegistry` pattern is *ahead* of what Hummingbot exposes today; the correctness fix is well-motivated.** No change to Approach C.

**Sources:**
- https://hummingbot.org/strategies/v1-strategies/cross-exchange-market-making/
- https://hummingbot.org/strategies/v1-strategies/pure-market-making/
- https://hummingbot.org/strategies/v1-strategies/strategy-configs/inventory-skew/
- https://hummingbot.org/client/global-configs/balance-limit/
- https://hummingbot.org/strategies/v2-strategies/controllers/
- https://github.com/hummingbot/hummingbot/blob/master/hummingbot/strategy/cross_exchange_market_making/cross_exchange_market_making.py

---

## 2. Professional / institutional multi-quote inventory management

### 2.1 Coinbase Prime unified cross-margin

- Coinbase Prime launched **unified cross-margin across spot, derivatives, and CFTC-regulated perps** in March 2026. [VERIFIED via `https://www.coinbase.com/blog/coinbase-prime-the-institutional-os-ushering-in-the-next-era-of-crypto-trading`]
- Design intent: exposures **evaluated together within one portfolio framework**; hedged strategies (e.g., basis trades) receive favourable margin treatment. [VERIFIED via `https://www.marketsmedia.com/coinbase-prime-launches-unified-spot-derivatives-cross-margin/`]
- No **whitepaper** with technical detail on the shared-balance reservation engine could be located — only marketing blog posts. [UNVERIFIED for engineering details]

### 2.2 Kraken multi-collateral (Multi-M) and portfolio margining

- Multi-M cross margin uses the **entire wallet balance as collateral**; multiple pair positions share one collateral pool. [VERIFIED via `https://support.kraken.com/articles/4844463246100-margining-liquidations-multi-collateral-derivatives`]
- Portfolio margin (options/futures) evaluates risk at the **portfolio level by integrating risk factors in a structured manner**. [VERIFIED via `https://support.kraken.com/articles/options-portfolio-margining-demo`]

### 2.3 FTX unified margin (historical)

- FTX's unified-margin design allowed collateral posted in any supported asset with all open positions cross-margined automatically. [VERIFIED via `https://help.ftx.com/hc/en-us/articles/4404204316052-FTX-s-Unique-Design`]
- No serious engineering post-mortem was found — the fraud collapse buried public architectural retrospectives. [UNVERIFIED — searched Hacker News, bankruptcy filings, U-Chicago Business Law Review; only high-level references remain]

### 2.4 Wintermute / Jump statements

- Wintermute publicly discusses **cross-venue inventory management** across 50+ venues and 1,000+ assets. [VERIFIED via `https://www.bitget.com/academy/wintermute-crypto`]
- Neither firm publishes protocol-level detail on how they reserve inventory across the many pair permutations of a single base asset. [UNVERIFIED — no primary sources found]

**Analogy caveat:** All three exchange systems solve the same *shape* of problem the user faces (shared collateral across positions), but at **account level**, computed by the exchange, not at bot-process level, computed by the user. They validate the reservation shape without giving an off-the-shelf design.

**Verdict for section 2:** Exchange-level cross-margin systems confirm that asset-keyed shared-pool accounting is the right abstraction. **Approach C's asset-keyed `CapitalReservationRegistry` mirrors this pattern one layer down (bot process instead of exchange account) — architecturally sound.** No change to Approach C.

**Sources:**
- https://www.coinbase.com/blog/coinbase-prime-the-institutional-os-ushering-in-the-next-era-of-crypto-trading
- https://www.theblock.co/post/392716/coinbase-prime-unified-cross-margin-spot-derivatives-regulated-perps
- https://support.kraken.com/articles/4871775312276-portfolio-management-derivatives
- https://support.kraken.com/articles/4844463246100-margining-liquidations-multi-collateral-derivatives
- https://help.ftx.com/hc/en-us/articles/4404204316052-FTX-s-Unique-Design
- https://www.bitget.com/academy/wintermute-crypto

---

## 3. DEX pathfinder / smart-order-routing architectures

### 3.1 1inch Pathfinder v2

- Pathfinder is a **graph-search** engine: given `(from_token, to_token, amount)` find the path (or path split) through the DeFi liquidity graph maximising output net of fees + gas. [VERIFIED via `https://www.dextools.io/tutorials/what-is-1inch-defi-dex-aggregator-guide-2026`]
- v2 added **multi-hop routing** and splits across "market depths" within one protocol. [VERIFIED via `https://blog.1inch.com/introducing-1inch-v2-defis-fastest-and-most-advanced-aggregation-protocol/`]
- Two user-facing modes: **Maximum return** (complex routes) vs **Lowest gas** (simple routes). [VERIFIED, same URL]
- Specific graph representation, candidate-enumeration algorithm, and refresh cadence are **not published** (competitive advantage). [UNVERIFIED — the blog post is intentionally silent on internals]

### 3.2 Paraswap MultiPath

- MultiPath searches integrated exchanges + token pairings, weighing gas + slippage. [VERIFIED via `https://dev.to/stablecoinstrategist/paraswap-best-routes-explained-why-aggregation-beats-single-dexs-1o45`]
- Their Delta algorithm uses ML models over 50M historical transactions to predict optimal paths. [UNVERIFIED — cited in marketing content; no whitepaper found]

### 3.3 CoW Swap batch auctions

- Aggregates orders over ~30s windows and auctions the batch to competing solvers. [VERIFIED via `https://docs.cow.fi/cow-protocol/concepts/introduction/fair-combinatorial-auction`]
- **Uniform Directed Clearing Prices (UDP):** an asset pair that appears multiple times in one auction settles at one consistent price. [VERIFIED, same URL]
- Coincidence-of-Wants matching first, on-chain liquidity for residuals. [VERIFIED via `https://cow.fi/learn/what-is-price-improvement-and-why-is-it-unique-to-cow-swap`]

### 3.4 Uniswap Auto Router

- Splits trades across up to **7 paths**; gas-aware; only splits when the extra hops beat the extra gas. [VERIFIED via `https://blog.uniswap.org/auto-router-v2`]
- Improves pricing on **13.97% of all trades** (36.84% of top-10-by-TVL trades). [VERIFIED, same URL]

**Analogy caveat — this is the most important caveat in the report.** All four DEX pathfinders solve a **one-shot swap** problem: user has token A, wants token B, execute now, done. There is no persistent inventory constraint, no USD-value target to preserve, no need to hedge on the other side of the same pair later. The Acervator scrumming bot has an **inventory the pathfinder does not have** — the target-balance discipline, the fact that a sell fill on ETH/USDC will need a buy fill (perhaps on ETH/BTC) to restore the target — and this fundamentally changes the optimisation.

Concretely: 1inch does not care that yesterday's route left it holding USDC-priced ETH that must be re-bought against BTC today; it never held anything. The scrumming bot **must** care.

**Verdict for section 3:** DEX pathfinders are a weak analogy for the persistent-inventory case. Their algorithms are borrowable (graph search, multi-hop, gas-aware split) **only for the read-only scout stage** of Approach C, not as a template for Approach B. **Approach C's cross-pair scout is well-founded; a Pathfinder-style dynamic router is a much heavier project than the user is scoping.** No change to Approach C; the evidence weighs *against* a hasty Approach B.

**Sources:**
- https://www.dextools.io/tutorials/what-is-1inch-defi-dex-aggregator-guide-2026
- https://blog.1inch.com/introducing-1inch-v2-defis-fastest-and-most-advanced-aggregation-protocol/
- https://dev.to/stablecoinstrategist/paraswap-best-routes-explained-why-aggregation-beats-single-dexs-1o45
- https://docs.cow.fi/cow-protocol/concepts/introduction/fair-combinatorial-auction
- https://cow.fi/learn/what-is-price-improvement-and-why-is-it-unique-to-cow-swap
- https://blog.uniswap.org/auto-router-v2
- https://blog.uniswap.org/auto-router

---

## 4. Triangular arbitrage patterns

### 4.1 The canonical Bellman-Ford / log-weight pattern

- Model currency graph: node per currency, edge per exchange rate. Take `-log(rate)` as edge weight. A **negative-weight cycle** is an arbitrage. Run Bellman-Ford to detect. [VERIFIED via `https://medium.com/@23bt04107/bellman-ford-in-cryptocurrency-arbitrage-detecting-profitable-trade-cycles-2a6264a409b3`]
- Recent peer-reviewed treatment claims 0.002ms detection latency, 92% accuracy on 6-month backtest. [VERIFIED via `https://beei.org/index.php/EEI/article/view/10817`]

### 4.2 Open-source implementations worth studying

- `Drakkar-Software/Triangular-Arbitrage` — CCXT + OctoBot, 15+ exchanges, active. [VERIFIED via `https://github.com/Drakkar-Software/Triangular-Arbitrage`]
- `hzjken/crypto-arbitrage-framework` — CCXT + cplex, monitors multiple exchanges, finds multi-lateral paths maximising rate of return, computes optimal trade size per pair given constraints. [VERIFIED via `https://github.com/hzjken/crypto-arbitrage-framework`]
- Multiple other Python/CCXT implementations exist but few have stars > 100. [VERIFIED via GitHub topic search]

### 4.3 Polling cadence

- These engines commonly use `fetch_tickers()` bulk calls (single request returns all tickers) rather than per-pair polling, then cache and Bellman-Ford over the cached snapshot. [VERIFIED via multiple sources cited above]

**Analogy caveat:** Triangular arb **detects mispricing cycles for a one-shot round-trip**. The user's bot **holds inventory persistently** and cannot round-trip out because the mandate is accumulation. Some primitives are reusable — the CCXT bulk-poll pattern, the log-weight graph — but the optimisation target is different.

**Verdict for section 4:** Confirms the read-only scout can use standard bulk-poll + graph structure. Does **not** support dynamic per-tick routing for a persistent-inventory bot. No change to Approach C.

**Sources:**
- https://medium.com/@23bt04107/bellman-ford-in-cryptocurrency-arbitrage-detecting-profitable-trade-cycles-2a6264a409b3
- https://beei.org/index.php/EEI/article/view/10817
- https://github.com/Drakkar-Software/Triangular-Arbitrage
- https://github.com/hzjken/crypto-arbitrage-framework
- https://github.com/a-r-d/Bellman-Form-BTCe-Arbitrager

---

## 5. Coordination-registry design patterns for shared trading resources

### 5.1 Two-phase commit vs. optimistic reservation

- **2PC:** phase 1 asks all participants "can you commit?"; phase 2 commits iff every response was yes. Classic distributed-transaction pattern. [VERIFIED via `https://martinfowler.com/articles/patterns-of-distributed-systems/two-phase-commit.html`]
- **Optimistic concurrency control:** transactions run without locks, then validate at end; conflicts detected and losers retry. [VERIFIED via `https://singhajit.com/distributed-systems/two-phase-commit/`]
- Reservation-system engineering (hotel-booking-style) commonly uses optimistic reservation with a short **hold timer** — pattern discussed at `https://medium.com/devbulls/concurrency-strategies-in-multi-user-reservation-systems-b8142dea1bc8`. [VERIFIED]

### 5.2 Trading-specific writeups

- No engineering blog from Binance / OKX / prop shops was located that describes an asset-keyed reservation registry for concurrent strategies. [UNVERIFIED-NEGATIVE — searched engineering blogs, patent DB, arXiv]
- Nonce-management race-condition literature is the closest adjacent domain: shows that atomic-update discipline for `remaining_qty` + `available_qty` is critical to prevent desync. [VERIFIED via `https://hacken.io/insights/order-book-security-vulnerabilities/`]

### 5.3 Does the user's pattern have a name?

- The user's `CapitalReservationRegistry` — in-process, asset-keyed, heartbeat-liveness — is essentially a **soft lease** or **optimistic reservation with owner-heartbeat expiry**. This has no single canonical name in the trading literature; the closest cross-domain term is **lease** (Chubby, Zookeeper) or **hold** (reservation systems). [UNVERIFIED-NEGATIVE for a trading-specific term]

**Analogy caveat:** The primitives (locks, leases, optimistic reservation) are well-established in the distributed-systems literature, but their specific application to *multi-strategy trading in one process on one exchange account* is not well-documented publicly. This is a novel enough application that the user shouldn't expect a drop-in reference implementation.

**Verdict for section 5:** The `CapitalReservationRegistry` shape is a soft-lease pattern well-known in distributed systems, less-known in trading. **Approach C's proposal to fix the correctness bugs is a straight applied-CS problem, not a research problem.** The heartbeat-liveness design already borrows from the right pattern family. Recommend explicit modelling as: (1) shared asset-keyed pool, (2) named owners with reservation IDs, (3) monotonic clock heartbeats, (4) forced release on missed heartbeat, (5) atomic reserve/release with a single lock (or an actor). No change to Approach C.

**Sources:**
- https://martinfowler.com/articles/patterns-of-distributed-systems/two-phase-commit.html
- https://singhajit.com/distributed-systems/two-phase-commit/
- https://medium.com/devbulls/concurrency-strategies-in-multi-user-reservation-systems-b8142dea1bc8
- https://hacken.io/insights/order-book-security-vulnerabilities/
- https://www.cs.princeton.edu/courses/archive/fall16/cos418/docs/L6-2pc.pdf

---

## 6. CCXT-specific patterns for cross-pair discovery

### 6.1 Enumerating pairs for a base asset

- `exchange.load_markets()` fetches and caches every trading pair. Filter the resulting dict by `market['base'] == 'ETH'` to enumerate ETH/*. [VERIFIED via `https://github.com/ccxt/ccxt/wiki/manual`]
- Symbols are always `BASE/QUOTE`. [VERIFIED, same URL]

### 6.2 Bulk polling

- `fetch_tickers(symbols=None)` returns all tickers in one call where the exchange supports it; `fetch_ticker(symbol)` fetches one. For a scout that wants prices on all quote permutations of one base, bulk-poll + client-side filter is the standard approach. [VERIFIED via `https://docs.ccxt.com/en/latest/manual.html`]
- Some exchanges cap `fetch_tickers` at N symbols (e.g., Yobit at 50). Coinbase does not have a documented cap, but the endpoint is subject to rate-limit budget. [VERIFIED via `https://github.com/ccxt/ccxt/issues/2502`]
- `enableRateLimit: true` (default) applies a leaky-bucket throttler. [VERIFIED via `https://deepwiki.com/ccxt/ccxt/3-getting-started`]
- **Best-practice cadence** for a scout: one bulk `fetch_tickers` per polling interval (5–10s), cache, share the snapshot across strategies. Do **not** have each bot call `fetch_ticker` for its own pair — this wastes rate budget and produces skewed timestamps. [VERIFIED via community wiki + issue discussions]

### 6.3 Coinbase-specific caveats

- `fetch_tickers` and `fetch_ticker` return **structurally different** payloads on `coinbaseexchange`; the bulk version omits some fields the single version provides. [VERIFIED via `https://github.com/ccxt/ccxt/issues/26170`]
- If the scout needs bid/ask depth or 24h volume, it may need to supplement with `fetch_order_book(symbol, limit=1)` per pair — which puts rate-budget pressure back on. [VERIFIED, same URL]

**Verdict for section 6:** The CCXT primitives to build a cross-pair scout are well-understood: `load_markets` for discovery, `fetch_tickers` bulk polling for cadence, and a single shared snapshot cached in-process for consumers. **Approach C's read-only scout is a solved CCXT pattern.** No change; adds a concrete implementation note for the plan.

**Sources:**
- https://github.com/ccxt/ccxt/wiki/manual
- https://docs.ccxt.com/en/latest/manual.html
- https://github.com/ccxt/ccxt/issues/2502
- https://github.com/ccxt/ccxt/issues/26170
- https://deepwiki.com/ccxt/ccxt/3-getting-started

---

## 7. Academic / practitioner literature

### 7.1 Cartea / Jaimungal / Penalva — "Algorithmic and High-Frequency Trading" (CUP 2015)

- Book covers execution of large orders, market making, VWAP targeting, pairs trading, dark-pool execution. [VERIFIED via `https://books.google.com/books/about/Algorithmic_and_High_Frequency_Trading.html?id=5dMmCgAAQBAJ`]
- No specific chapter on "multiple quote currencies for the same base asset" is indexed in the ToC visible from Google Books / Cambridge product page. [UNVERIFIED — full-text access not available in this session]

### 7.2 Almgren-Chriss and extensions

- Original A-C model formulates optimal execution as stochastic control balancing market impact vs price risk. [VERIFIED via `https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf`]
- Multi-asset extension appears in the original paper's appendix; correlation figures into optimal trajectories. [VERIFIED via `https://questdb.com/glossary/optimal-execution-strategies-almgren-chriss-model/`]
- Multi-venue extensions exist with separate temporary/permanent impact by weights (Riccati-type). [VERIFIED, same URL]
- Multi-asset optimal execution + statistical arbitrage under Ornstein-Uhlenbeck dynamics: arXiv:2103.13773. [VERIFIED via `https://arxiv.org/pdf/2103.13773`]

**Analogy caveat:** A-C literature is about **executing a fixed target quantity over a fixed horizon**. The scrumming bot's mandate is the opposite — hold a target USD balance indefinitely and continuously rebalance. Some multi-asset math is transferable (correlation-aware sizing) but the framework doesn't fit natively.

### 7.3 The Barzykin / Bergault / Guéant FX papers — MOST DIRECTLY RELEVANT

- **arXiv:2207.04100** — "Dealing with multi-currency inventory risk in FX cash markets" (2022). Market maker holds multi-currency inventory and quotes multiple pairs; framework maximises expected profit subject to inventory-risk control; **approximation techniques scale to any number of currency pairs**. [VERIFIED via `https://arxiv.org/abs/2207.04100`]
- Follow-on 2023 paper builds portfolio-level multi-currency model with optimal prices and hedging rates as functions of inventory + risk aversion. [VERIFIED via `https://al.linkedin.com/posts/alexander-barzykin-b430ab33_algorithmic-market-making-in-foreign-exchange-activity-6991468876580446208-unef`]
- Related: `arXiv:2112.02269` — "Market making by an FX dealer: tiers, pricing ladders and hedging" — treats internalisation vs externalisation decision explicitly. [VERIFIED via `https://arxiv.org/pdf/2112.02269`]

**Analogy caveat (partial):** These papers treat an FX market maker who holds one asset (say EUR) obtained via many pairs (EUR/USD, EUR/GBP, EUR/JPY) and decides whether to **internalise** the risk (hold inventory and let it net across pairs) or **externalise** (hedge on the interdealer market). This is close to the user's problem — EUR is the "base" the way ETH is the base — but the *decision* being modelled is hedging, not choosing which pair to trade on next. Still, the **shared inventory pool per currency** is exactly the model shape; the paper family confirms the pattern is mathematically defensible.

### 7.4 Recent 2024-2025 arXiv on AMM multi-currency inventory

- `arXiv:2506.02869` — optimal dynamic fees in AMMs. [VERIFIED]
- `arXiv:2508.08152` — optimal fees for liquidity provision. [VERIFIED via cite in `https://arxiv.org/html/2407.16885v1`]
- `arXiv:2509.06510` — optimal exit time for AMM LPs. [VERIFIED, same]
- None of these papers directly addresses multi-quote inventory for CEX spot trading of the same base asset. [UNVERIFIED — no exact-match hit in my searches]

**Verdict for section 7:** Barzykin/Bergault/Guéant is the closest academic backing and validates the **asset-keyed shared-inventory model** used by the `CapitalReservationRegistry`. No academic source suggests **dynamic pair-routing per tick** is a solved problem for persistent-inventory trading — the closest work treats it as a stochastic-control problem requiring calibrated market parameters and approximation techniques the user does not currently maintain. **This is strong evidence *against* jumping to Approach B without first collecting the market-parameter data the models require.**

**Sources:**
- https://books.google.com/books/about/Algorithmic_and_High_Frequency_Trading.html?id=5dMmCgAAQBAJ
- https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf
- https://questdb.com/glossary/optimal-execution-strategies-almgren-chriss-model/
- https://arxiv.org/pdf/2103.13773
- https://arxiv.org/abs/2207.04100
- https://arxiv.org/pdf/2207.04100
- https://arxiv.org/pdf/2112.02269
- https://www.risk.net/cutting-edge/7956321/podcast-barzykin-and-gueant-on-fx-market-making
- https://arxiv.org/html/2407.16885v1

---

## Integration notes — what to fold into the design plan

**Fold 1 — reservation registry.** The `CapitalReservationRegistry` should be explicitly documented as a **soft-lease pattern**: shared asset-keyed pool, named owners with reservation IDs, monotonic-clock heartbeats, forced release on missed heartbeat, atomic reserve/release under a single lock or actor. This aligns with (a) Kraken/Coinbase-Prime shared-collateral models one layer up and (b) classic distributed-systems lease patterns (Chubby, Zookeeper) one layer over. The correctness bugs described in the design plan are, in this framing, standard concurrency issues — the fix is disciplined atomic mutation, not a rewrite. Explicit invariant to test: `sum(reservations_for_asset_A) + free_A <= exchange_balance_A` at every step, and `sum(reservations_for_asset_A) <= exchange_balance_A - min_free_reserve_A`.

**Fold 2 — read-only cross-pair scout.** Implement the scout as a single-process `fetch_tickers` poller on a configurable interval (start 10s), maintaining an in-memory snapshot keyed by `(base, quote) -> Ticker`. Consumers (each bot) query the snapshot, never the exchange directly. The scout can safely enumerate quote-currency permutations for any base using `exchange.markets` post-`load_markets()`. Do **not** fold in a Pathfinder-style optimiser at this stage: the scout only reports "here is the current relative price / divergence / spread across pairs for base X"; the bot still trades on its declared pair. This makes the scout genuinely read-only and defers all the routing/rebalancing complexity to Fold 3.

**Fold 3 — dynamic routing deferred, but design for it.** Approach B is not falsified by this research — Barzykin/Bergault/Guéant show it is mathematically tractable — but the evidence strongly supports doing it as a *separate later cascade* rather than in this hop. The precondition for Approach B is having the market-parameter data (spreads, depth, drift, cross-pair correlations, execution-cost model) that the FX-market-making literature assumes as inputs. Use the read-only scout from Fold 2 to **collect that data live** for 2–4 weeks before designing the router. When Approach B is picked up, the design should look more like the FX-dealer internalisation-vs-externalisation decision than like a 1inch pathfinder: the bot has persistent inventory and must decide which pair *reduces* inventory imbalance most efficiently, weighted by execution cost, not just which pair currently prints the best one-shot rate.

---

## Adversarial — what would falsify the recommendation?

**Evidence that would push toward Approach B (dynamic routing) instead of Approach C:**

1. **Persistent, materially-large cross-pair divergence in the scout data.** If the read-only scout, once deployed, shows that for a given base asset the best-priced pair changes on a horizon shorter than the bot's trade cadence, *and* the divergence exceeds the round-trip execution cost (maker fee + slippage + spread), *and* this happens often enough to move accumulation P/L by more than a token amount over a week, then Approach C's "trade on the declared pair" discipline is leaving money on the table and Approach B becomes justified. The threshold I would set: divergence > 2× execution cost, occurring on > 20% of decision windows, for at least 2 consecutive weeks. Anything less and the routing complexity is not worth the maintenance burden and the additional inventory-management surface area.

2. **A single-bot-per-asset regime becoming untenable.** If the user regularly wants > 3 bots on the same base asset for legitimate reasons (e.g., different quote currencies for different tax lots, or different scrum tempos), the coordination overhead of Approach C's registry grows super-linearly (N^2 contention checks), and a router that funnels all N bots through one execution layer starts looking simpler than N mutually-suspicious reservers.

3. **Evidence that the exchange itself provides a stronger primitive.** If Coinbase Advanced Trade adds an account-level asset-lock API that the bot can call directly, the in-process reservation registry becomes redundant — better to lean on the exchange primitive and reduce bot-side state.

**Evidence that would strongly confirm Approach C:**

1. **Scout data showing cross-pair divergence stays inside execution cost.** If the divergence signal is small and mean-reverting on the bot's timescale, dynamic routing captures nothing and Approach C's simplicity wins.
2. **Any bug found in the reservation logic that reproduces on the fixed registry.** Discovery of a real coordination bug in-flight would validate the "fix correctness first, defer feature" ordering.
3. **Barzykin-style calibration data absent.** If the user cannot easily measure spreads/depth/drift per pair at bot-frequency (which the FX papers assume), Approach B is under-specified and Approach C is the only responsible path.

**Where the analogy weakens most sharply:** DEX pathfinders (§3) and triangular arbitrage (§4) are frequently invoked as precedent for "smart cross-pair routing" — but neither has any concept of *persistent inventory that must be maintained at a target*. Do not draw the analogy carelessly. The Acervator scrumming bot is a **market-making-with-a-drift-target** system, not a swap engine or an arbitrageur. The correct analogies are the FX-dealer literature (Barzykin/Bergault/Guéant) and the exchange-side cross-margin systems (Coinbase Prime, Kraken), both of which validate the reservation shape without validating dynamic routing.

**Final call:** Approach C stands. Ship the reservation fix + scout. Instrument the scout so its data becomes the falsifier for Approach B in a later cascade.
