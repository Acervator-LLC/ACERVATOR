# Market Inspector — Audit & Design Proposal

Date: 2026-07-27. Version at audit: v3.23.36.
Scope: two surfaces the operator identified as needing conceptual and
functional alignment — the Bot Details `Mr. Inspector` tab
(`bot_live_settings.py:1821`) and the top-level `Market Map` tab
(`market_map.py`), plus the `MRInspector` runtime class
(`mr_inspector.py`) and the `market_map_fetcher.py` hybrid data path.

Operator directive (2026-07-27):

> This tab is almost certainly not wired at all or correctly. Currently
> displays “not connected to the selected bot” but there is no method
> for connecting it nor did I ever propose this as a part of how it is
> supposed to function.
>
> Change tab name to **Market Inspector**.
>
> The intended design function of this inspector was to identify
> **opposing pairs** and **high-timeframe (daily, weekly, monthly
> candles) entry opportunities on non-active markets**.
>
> This tab is also supposed to correspond to the Market Map tab of the
> application. This tab should also be renamed to **Market Inspector**
> so that we have alignment.

Deliverable this pass: audit + design proposal. **No code changes**;
operator alignment required on the redesign before implementation.

---

## Part 1 — Memory (LTM) findings

Two memory files referenced these surfaces:

- `reference_runtime_layout.md:21` — notes `market_map_cache.json` as a
  research cache under `~/.acervator/`. Confirms the hybrid fetcher
  writes a durable CoinGecko snapshot cache.
- `user_operator.md:7` — operator vocabulary includes “MR Inspector”
  and “Boost Fold” as production-lexicon terms.

No memory hits for design intent of `opposing pairs` on HTF or
`non-active markets`. The intended design as stated in this session’s
directive is therefore treated as fresh authoritative spec.

---

## Part 2 — Audit of the four artefacts

### 2.1  Bot Details “Mr. Inspector” tab (`bot_live_settings.py:1821-2082`)

Renders a five-section view (Config + Lifetime → This Bot’s Asset State
→ 3-Layer Gate Status → All Tracked Assets) driven entirely by
`getattr(self._bot, "_mr_inspector", None)`.

**Finding F40 — the tab is a phantom for crypto bots.** The empty state
at line 1838 fires whenever `_mr_inspector is None`, and:

- `ScrummingBot._mr_inspector = None` at `scrumming_bot.py:605`.
- A setter `set_mr_inspector()` exists at `scrumming_bot.py:703`.
- **Nothing in the crypto code path calls that setter.** A codebase
  grep for `set_mr_inspector` shows zero hits across `src/`. Only
  `stock_accumulation_bot.py:135` instantiates an MRInspector, and
  that is a different bot class on a different code path (stocks, not
  crypto).

Consequence: every operator opening the tab on a crypto bot sees the
“not attached” message. The tab’s populated branches (lines 1853-2081)
are unreachable in production. Operator’s report is correct.

**Finding F41 — the tab’s conceptual framing is per-bot, not
per-market.** Even if wired, the tab is designed to answer “what is the
MR-signal state for THIS bot’s asset?” — useful for a running bot, not
for the operator’s stated purpose of surfacing HTF entry opportunities
on markets that are NOT yet being traded.

### 2.2  Top-level “Market Map” tab (`market_map.py`)

Renders `MarketMapCanvas` (geometric 2-D projection of coins by 24 h
change) plus `RecommendationsPanel` (a short list of counter-pairs).
Data via three fallbacks: live CCXT tickers → CoinGecko HTTP → cache
→ synthetic universe (per `market_map_fetcher.py`).

Counter-pair detection lives at `market_map.py:621-650`:

```python
up_coins   = [c for c in coins if c.change_24h > 2.0]
down_coins = [c for c in coins if c.change_24h < -2.0]
…
if spread > 5:
    pairs.append(CounterPair(upside=u, downside=d,
                             correlation=-spread / 100, …))
```

**Finding F42 — “correlation” label is misleading.** The value stored
in `CounterPair.correlation` is `-(u.change_24h − d.change_24h) / 100`.
That is a *momentum spread proxy*, not a Pearson correlation over
price history. A pair with 24 h changes `+10 %` and `−8 %` gets
`correlation = -0.18`; the same pair might be perfectly *positively*
correlated over 30 days and merely diverging this particular day. The
label overpromises the analysis.

**Finding F43 — timeframe collapse.** All pair detection runs on 24 h
change only. The operator’s stated intent (daily/weekly/monthly
timeframes) is not represented. There is no HTF gate — no z-score, no
BB position, no HTF Landing Strip tightening — despite the runtime
having all three primitives available in `ta_engine` and `mr_inspector`.

**Finding F44 — target-asset flag is used only for colour, not
filtering.** `CoinNode.is_target` is set at lines 445-447 whenever a
coin is on the active-bot list, and is used at render time to draw a
teal ring. The recommendations panel does NOT filter to non-active
markets — it can (and does) recommend pairs where one leg is already
being traded. Operator’s stated intent (“non-active markets”) is not
enforced.

**Finding F45 — the Market Map does not talk to `MRInspector` at all.**
There is no import of `mr_inspector` in `market_map.py` and no
callback from the fetcher into any MR scanner. The class docstring at
`mr_inspector.py:9` (“MR Inspector is a background scanner on the
Market Map”) is aspirational, not descriptive.

### 2.3  `MRInspector` runtime (`mr_inspector.py`)

A 230-line dataclass + class implementing a 3-layer gate:

- Layer 1 — z-score (`>±1.8σ`) plus BB position at extreme (`>0.80` /
  `<0.20`) over the LAST 20 candles.
- Layer 2 — HTF Landing Strip tightening on the same candle stream
  (via `detect_landing_strip_v2`).
- Layer 3 — cooldown-gated emission of a `BOOST_SELL` / `BOOST_BUY`
  signal with a recommended-percent hint.

**Finding F46 — the 3-layer gate is well-designed BUT scoped for LTF
holdings adjustment, not HTF market discovery.** The `.scan(asset,
candles)` API takes a single asset’s candles at whatever timeframe the
caller supplies. If a caller fed it 1 D candles, the math would still
work — but the class is invoked per-asset per-bot per-tick in the
stocks path, using the bot’s trading TF (typically 1 h / 4 h).
Nothing feeds it a fleet-wide HTF stream.

**Finding F47 — the class is single-timeframe.** No mechanism combines
signals across daily / weekly / monthly candles for the same asset.
Operator intent explicitly calls out ALL THREE HTFs.

**Finding F48 — signal semantics don’t match the intended use case.**
`BOOST_SELL` and `BOOST_BUY` are position-adjustment signals for a bot
that already holds the asset. Operator wants *entry-opportunity*
signals for markets the operator does NOT already trade — a distinct
semantic (`ENTRY_LONG` / `ENTRY_SHORT` / `WATCHLIST` etc.).

### 2.4  `market_map_fetcher.py`

Three-tier fetch (CoinGecko → cache → synthetic). Solid runtime.
Provides only `current_price`, `change_24h`, `change_7d`,
`market_cap_rank`. **No candles.** So even if we retrofit HTF analytics,
the fetcher itself cannot supply the data — we would need a second
data path (exchange OHLCV fetch or CoinGecko’s `/coins/{id}/ohlc`
endpoint) to feed daily / weekly / monthly bars to the MR analyzer.

---

## Part 3 — Diagnosis summary

| # | Symptom | Root cause | Severity |
|---|---------|------------|----------|
| F40 | Bot Details tab always shows “not attached” | No caller wires `_mr_inspector` on crypto bots | Broken |
| F41 | Wrong conceptual scope (per-bot instead of per-market) | Legacy design lift from stocks path | Design gap |
| F42 | “Correlation” label overpromises | Field name doesn’t match computed value | Misleading |
| F43 | Only 24 h momentum; no HTF gate | Tab predates the HTF-inspector concept | Design gap |
| F44 | Recommendations don’t exclude active markets | Filter never wired | Design gap |
| F45 | Market Map ≠ MRInspector | The two subsystems were never connected | Design gap |
| F46 | 3-layer gate scoped for LTF holdings | Class API designed for the stocks per-tick use case | Design gap |
| F47 | Single timeframe only | No aggregator across daily / weekly / monthly | Design gap |
| F48 | Signals are `BOOST_*`, not `ENTRY_*` | Original spec targeted an in-flight bot | Semantic gap |

Bottom line: the two surfaces don’t talk to each other, don’t focus on
non-active markets, and don’t look at HTF candles. Together they do
not deliver the operator’s stated intent. Fixing this requires a
redesign, not a bug fix.

---

## Part 4 — Design proposal

### 4.1  Nomenclature

Both surfaces become **Market Inspector**:

- Top-level `Market Map` tab → **Market Inspector** (main app tab).
- Bot Details `Mr. Inspector` tab → **Market Inspector** (per-bot view).

Both consume the same analytics; the difference is scope:
- Top-level: fleet-wide, filters DEFAULT to non-active markets.
- Per-bot: focuses on the current bot’s asset and neighbouring
  candidates.

### 4.2  Core concept — the HTF Market Inspector

A single background analyzer scans a universe of candidate markets on
daily / weekly / monthly candles, scores each on entry-opportunity
signals, and identifies opposing pairs. Two surfaces render the same
underlying analysis at different scopes.

Universe definition:
- CoinGecko top-N by market cap (already fetched, N configurable —
  default 50 per current fetcher cap).
- Excluding stablecoins (heuristic: name in a small denylist or
  `abs(change_24h) < 0.5%` sustained).
- Optionally filtering out markets the exchange doesn’t support
  (defer — CoinGecko’s universe is broader than any one exchange).

Per-market scoring on three timeframes (D / W / M):

- **Layer A — HTF position extremity.** Compute rolling BB (20-period
  Bollinger) on the market’s daily candles, weekly candles, monthly
  candles. Emit `bb_pos_d`, `bb_pos_w`, `bb_pos_m` — same math the
  existing `MRInspector.scan` already knows.
- **Layer B — HTF Landing Strip tightening.** Reuse
  `detect_landing_strip_v2` on each HTF candle stream. Consolidation
  near an extreme signals coiling energy.
- **Layer C — Directional bias reconciliation.** If all three HTFs
  agree on a direction (e.g., D and W and M all near lower band with
  tightening), score = HIGH. Two-of-three = MEDIUM. Divergence = LOW.

Signal semantics:
- `ENTRY_LONG_HIGH` — HTFs converge at a lower extreme with
  tightening. Prime accumulation candidate.
- `ENTRY_SHORT_HIGH` — HTFs converge at an upper extreme with
  tightening. Prime distribution candidate.
- `ENTRY_LONG_MEDIUM` / `ENTRY_SHORT_MEDIUM` — partial agreement.
- `WATCHLIST` — early tightening detected but not yet at extreme.

### 4.3  Opposing pair identification (redesigned)

Two candidates form an **opposing pair** when:

1. One shows `ENTRY_LONG_*` and the other `ENTRY_SHORT_*`, AND
2. Their 30-day return correlation (real Pearson, not the current
   momentum-spread proxy) is between `−1.0` and `−0.3` — i.e., they
   actually move opposite over the medium term, AND
3. Both are in the non-active universe (unless the operator toggles
   “include active”).

The result is a small ranked list — an operator scanning it should be
able to open one new bot on each side of a pair and structurally
harvest the divergence.

### 4.4  Non-active market filter

The active-market set is derived from the current bot roster: for each
running bot, `config.target_asset` (or the base leg of
`config.symbol`) is added to `_active_markets`. The Market Inspector
excludes any market in that set from the default candidate list, with
a toggle to include-all when the operator wants a broader view.

The per-bot Market Inspector tab flips the default — it INCLUDES the
current bot’s asset (highlighted) so the operator can see how the
bot’s market compares to the HTF landscape.

### 4.5  Data path

The current fetcher provides only ticker-level fields. HTF analytics
need candles. Two options:

- **Option A — CoinGecko OHLC endpoint.** `/coins/{id}/ohlc` returns
  daily candles for the top N days (up to 90 with `days=90` free-tier).
  Fetch weekly / monthly by resampling. Downside: another rate-limited
  endpoint; adds ~N HTTP calls per refresh cycle.
- **Option B — Exchange OHLCV via CCXT.** For markets the connected
  exchange supports, use `exchange.fetch_ohlcv(symbol, "1d", limit=90)`.
  Rate-limited to whatever CCXT’s per-exchange semaphore allows. Fills
  in for the exchange-supported subset only.
- **Option C — hybrid.** Prefer CCXT for symbols the exchange lists;
  fall back to CoinGecko OHLC for the rest.

Recommendation: start with **Option A** (uniform data source, works
offline via the same cache pattern the fetcher already implements),
add Option C later if operator wants exchange-supported markets to
show fresher intraday state.

### 4.6  Runtime location

The analyzer is a new class `MarketInspector` in
`src/trading/market_inspector.py`. It reuses `TA` primitives from
`ta_engine` (BB math, Landing Strip detection, Heikin-Ashi) and mirrors
the class shape of `MRInspector` for familiarity, but:

- API is `scan_universe(candles_by_tf: dict[str, dict[str, list[Candle]]])`
  where the outer key is the timeframe (`1d` / `1w` / `1M`) and the
  inner key is the market symbol. Emits `MarketInspectorReport`.
- `MRInspector` is retained on the stocks path unchanged (it works
  there — different problem).

Data fetcher: a new `market_inspector_fetcher.py` extends the hybrid
pattern from `market_map_fetcher.py` to include OHLC bars.

### 4.7  GUI surfaces

**Top-level Market Inspector tab** (replaces Market Map):

- Left panel: geometric visualization retained (operators liked it),
  colour-coded by top-tier signal (`ENTRY_LONG_HIGH` = strong green
  glow; `ENTRY_SHORT_HIGH` = strong red glow; `WATCHLIST` = amber
  ring). Active markets get the existing teal ring.
- Right panel: “HTF Signals” — sorted list of markets with signal
  strength, HTF-agreement badge (D/W/M), and top opposing pair.
- Filter row: [ ] Show active markets / [ ] Include stablecoins /
  timeframe checkbox array (D/W/M).
- Refresh cadence: 15 min default (much slower than current 60 s —
  HTF data doesn’t change fast).

**Per-bot Market Inspector tab** (replaces `Mr. Inspector`):

- Focus card: this bot’s asset with its D/W/M signal breakdown, HTF
  BB positions and tightening state.
- Neighbouring candidates: top-5 markets scoring higher than this
  bot’s asset, and top-3 opposing pairs featuring this bot’s asset.
- Removes the “not attached” empty state entirely — the tab now works
  regardless of whether the bot has an MRInspector attached.

### 4.8  Deliverables inventory

Phase A — foundation:
- `src/trading/market_inspector.py` (new class, ~250 lines).
- `src/gui/market_inspector_fetcher.py` (new fetcher, ~300 lines,
  patterned on `market_map_fetcher.py` plus OHLC).
- Cache file `~/.acervator/market_inspector_cache.json`.

Phase B — GUI:
- `src/gui/market_inspector.py` (new tab widget, ~400 lines,
  patterned on `market_map.py` plus HTF panels).
- `bot_live_settings.py` — replace `_create_mr_inspector_tab` with
  `_create_market_inspector_tab`; feed it the shared analyzer.
- `main_window.py:3427-3430` — rename top-level tab; swap widget.

Phase C — retirement:
- Retire the old `_mr_inspector` attribute + setter path on
  `ScrummingBot` (stocks path keeps `MRInspector` unchanged).
- Retire the old `market_map.py` counter-pair function (replaced by
  the correlation-aware one in `MarketInspector`).
- Add pin tests: fixture with known D/W/M candles → deterministic
  signal output.
- Bot Details tab audit doc updated to reference the new tab name.

Estimated total diff: ~1000 lines new + ~250 lines edits + ~100 lines
retired. Roughly the size of the Bot Details / Wizard parity work
already delivered this session.

### 4.9  What this design will NOT do

- Not a signal execution engine. It emits watchlist-quality signals.
  The operator still chooses when to spin up a bot; no automation.
- Not a replacement for the per-bot inspector concept in stocks path
  (that class stays where it is — it serves a different need).
- Not a fundamentals dashboard. No token-supply metrics, no dev
  activity, no on-chain analytics. This is pure price-action HTF
  analytics.

---

## Part 5 — Decisions requested before implementation

1. **Universe size / source** — CoinGecko top-50 default, or a
   different size / exchange-linked filter?
2. **Data path** — Option A (CoinGecko OHLC), Option C (hybrid CCXT
   + CoinGecko), or start with A and iterate?
3. **Opposing-pair correlation window** — 30-day proposed; longer
   window (90-day) would smooth noise but delay responsiveness.
4. **Refresh cadence** — 15 min proposed; slower or faster?
5. **Rename affects operator-facing text in memory, chronicle, and
   plan documents** — should I also do a sweep to rename “Mr.
   Inspector” references in in-repo docs, or leave those for the
   session ledger?
6. **Should the per-bot Market Inspector tab keep any of the current
   3-layer gate visualization** (as a “this bot’s asset’s current
   LTF state” curiosity) or drop it entirely for the HTF-only view?
7. **BotConfig persistence** — should the operator’s Market Inspector
   filter preferences (D/W/M toggles, show-active) persist on
   `BotConfig` per bot, or globally in a `~/.acervator/preferences.json`?

Once these are answered, the implementation splits cleanly into three
cascades matching the Phase A / B / C breakdown above.
