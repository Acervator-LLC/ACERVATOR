# Stone Tablets — in-tree rebuild design

Reference specification (Diataxis: reference). Version at write:
v3.23.96. Consumer: v3.23.97+ implementation cascades.

## 1  What operator asked for (2026-08-01)

Verbatim:

> Stone Tablets concept imported (LTM query to find current versions
> and code) which are the actual historical candles for every active
> target asset found within the YTD data. The YTD data does not run,
> it is the control set against which the simulation run is
> verified.
>
> Furthermore, we need a means of keeping the platform aware of the
> state of the Stone Tablets. This feature keeps drifting. They are
> a critical resource they should be getting re-downloaded
> repeatedly. We established them once, track them, and append on
> new trade events. They are to be made a core part of the program.
>
> Lastly, we need the Stone Tablet builds to be updated automatically
> at any point where historical data for a simulated target asset is
> missing via a Simulator call. This will augment future simulation
> capability of the individual user platform and help build a local
> database.

Core semantics distilled:

1. **Stone Tablets = persistent historical OHLCV per asset.** Not
   trades. Trades are the CONTROL SET; tablets are the price stream.
2. **Established once, appended incrementally.** No blanket
   re-downloads. On new trade events, append the range that just
   became historical.
3. **Platform-aware state.** GUI + programmatic accessors know what
   coverage exists, when it was last refreshed, where gaps live.
4. **Auto-heal on missing-coverage.** When Sim asks for candles for
   an asset that isn't covered, the Sim triggers a fetch that fills
   the gap AND promotes it to a Stone Tablet.
5. **Core part of the program.** Not a tools/ script the operator
   remembers to run — a runtime subsystem the app initialises on boot.

## 2  Prior art (LTM query result)

Archived design at
`_archive/docs_audits_pre_2026_07_24/2026-06-07_tape_archive_extractor_sim_ytd_replay_design.md`
documents the previous v3.22.55 implementation:

| Component (archived) | Fate |
|---|---|
| `tools/fetch_coingecko_history.py` (chunked fetcher) | retired with `sadp/` purge |
| `tools/promote_to_stone_tablets.py` (scratch → canonical) | retired |
| `sadp/RAIntSimBat/data/cache/` (scratch) | retired |
| `sadp/historical_data/` (canonical) | retired |
| `qa_baselines/schemas/stone_tablets_manifest.schema.json` | still present in `_archive/qa_baselines/schemas/` |
| First canonical tablet `BTC_2026.json` (298 candles) | retired |

Design lessons carried forward:

- **Chunked-fetch with sleep** — CoinGecko free tier ≈ 10 req/min;
  25 assets × 3 years × 15 s sleep ≈ 19 min. Same rate-limit
  discipline applies to Coinbase (which is what the operator's
  bots actually run on today).
- **SHA256 + provenance in manifest** — every tablet is checksummed
  and carries `fetched_at` + `source` fields so tampering / drift
  is detectable.
- **Never overwrite existing tablets** — append-only. Preserves
  historical integrity per the operator's "no one is going back
  into the past and fiddling with it."

## 3  In-tree architecture

Rebuilding fresh under `src/trading/stone_tablets/` (in-tree,
matches the "core part of the program" directive — not tools/ or
docs/).

### 3.1  Storage layout

Runtime data lives under the user's Acervator data dir (matches
`bot_state.json` convention). Never checked in.

```
~/.acervator/stone_tablets/
├── MANIFEST.json                    # index of every tablet + checksum
├── BTC_1d_2026.json                 # canonical tablet per (asset, tf, year)
├── ETH_1d_2026.json
├── SOL_1d_2026.json
├── CHIP_1d_2026.json
├── ...
└── _scratch/                        # pre-verified fetches; deleted on promote
```

Per-tablet JSON schema:

```json
{
  "schema_version": 2,
  "asset": "BTC",
  "timeframe": "1d",
  "year": 2026,
  "source": "coinbase",
  "fetched_at": "2026-08-01T00:00:00Z",
  "candle_count": 214,
  "first_ts_ms": 1735689600000,
  "last_ts_ms": 1754179200000,
  "candles": [
    [1735689600000, 42150.0, 42800.0, 41900.0, 42500.0, 12345.6],
    …
  ],
  "checksum_sha256": "3b5f…"
}
```

Manifest schema:

```json
{
  "schema_version": 2,
  "generated_at": "2026-08-01T00:00:00Z",
  "tablets": [
    {
      "asset": "BTC", "timeframe": "1d", "year": 2026,
      "file": "BTC_1d_2026.json",
      "checksum_sha256": "3b5f…",
      "candle_count": 214,
      "first_ts_ms": 1735689600000,
      "last_ts_ms": 1754179200000,
      "fetched_at": "2026-08-01T00:00:00Z",
      "source": "coinbase"
    },
    …
  ]
}
```

### 3.2  Runtime module `src/trading/stone_tablets/`

```
src/trading/stone_tablets/
├── __init__.py                # public API
├── registry.py                # StoneTabletsRegistry (singleton)
├── storage.py                 # read/write per-tablet files + manifest
├── fetcher.py                 # async fetch_range() via connector
└── coverage.py                # missing-ranges + freshness helpers
```

Public API surface (imported via `from src.trading.stone_tablets
import get_registry`):

```python
class StoneTabletsRegistry:
    def has_coverage(asset, since_ms, until_ms, timeframe="1d") -> bool
    def missing_ranges(asset, since_ms, until_ms, timeframe="1d") -> list[tuple[int, int]]
    def get_candles(asset, since_ms, until_ms, timeframe="1d") -> list[list[float]]
    def ingest_candles(asset, timeframe, rows: list[list[float]], source: str) -> int
    def coverage_summary() -> dict  # for GUI status display
    def stale_assets(now_ms=None, threshold_days=2) -> list[str]

def get_registry() -> StoneTabletsRegistry
```

### 3.3  Fetcher `src/trading/stone_tablets/fetcher.py`

```python
async def fetch_range(
    connector,               # any exchange with get_ohlcv
    exchange_id: str,        # "coinbase" for provenance
    asset: str,              # e.g., "BTC"
    since_ms: int,
    until_ms: int,
    timeframe: str = "1d",
) -> int:                    # returns candles appended
    """Fetch the requested range in chunks respecting rate limits,
    ingest into registry, promote to Stone Tablet, update MANIFEST."""
```

### 3.4  Sim integration point

The Simulator's Fleet Replay panel now asks the registry BEFORE
running:

```python
async def _ensure_replay_coverage(configs, connector):
    reg = get_registry()
    missing = []
    for cfg in configs:
        asset = cfg["symbol"].split("/")[0]
        if not reg.has_coverage(asset, YTD_START_MS, now_ms):
            missing.append(asset)
    if missing:
        # Auto-heal — operator directive: "updated automatically at
        # any point where historical data for a simulated target
        # asset is missing via a Simulator call"
        for asset in missing:
            await fetch_range(
                connector, "coinbase", asset,
                YTD_START_MS, now_ms, "1d")
```

The replay controller then reads candles from `reg.get_candles(...)`.
It does NOT call `ScrummingBot.tick()` — that path drags in balance
fetches, capital reservation, live monitor, and 30+ other subsystems
that have no place in a sim (operator's 2026-08-01 point). The
replay controller runs an ISOLATED trade-logic evaluator (v3.24.x
work — separate cascade).

### 3.5  On-boot registration

`main.py` boot sequence adds:

```python
from src.trading.stone_tablets import get_registry
_reg = get_registry()                              # loads MANIFEST
logger.info("Stone Tablets: %d tablets, %d assets covered",
            len(_reg._tablets), len(_reg._assets))
```

No fetching on boot — just load the index. Fetches are on-demand
(sim call) or event-driven (post-trade append, v3.24.x).

## 4  Cascade sequence

Splitting the delivery so each cascade ships green + operator can
verify each layer before the next.

- **v3.23.97 — Registry + storage** (pure runtime, no fetch)
  - `src/trading/stone_tablets/{__init__,registry,storage,coverage}.py`
  - Manifest read/write, per-tablet read/write, checksum validate
  - `has_coverage`, `missing_ranges`, `get_candles`, `ingest_candles`,
    `coverage_summary`, `stale_assets`
  - Pin tests: manifest roundtrip, gap detection, checksum drift
  - On-boot log line via main.py
  - No fetching. Population via manual `ingest_candles()` (tests).

- **v3.23.98 — Fetcher + GUI status pill**
  - `src/trading/stone_tablets/fetcher.py`
  - Chunked async fetch via connector.get_ohlcv (coinbase)
  - Rate-limit sleep (configurable, default 1 s per call)
  - Auto-promote to Stone Tablet (creates or extends existing)
  - Simulator Fleet Replay panel: coverage-status line + "Fetch
    missing" button
  - Pin tests: fake connector + verified promote flow

- **v3.23.99 — Sim replay uses Stone Tablets**
  - Fleet Replay controller reads from registry instead of
    synthetic candles or `_real_candles`
  - `_ensure_replay_coverage` called on Start Replay
  - Removes the ScrummingBot.tick() code path from sim entirely
  - Replaced with a MINIMAL trade-logic evaluator (separate design
    pass — v3.24.x)

- **v3.24.0 — Event-driven append**
  - Subscribe to `trade.filled` on the bus
  - On live trade, registry appends the candle for that asset's
    latest 1d bucket (extends the current-year tablet)
  - No manual re-download needed for ongoing coverage

## 5  Operator answers (2026-08-01) — sign-off CLOSED

1. **Path**: `~/.acervator/stone_tablets/` — confirmed.
2. **Timeframe**: **5m primary** — must match the current bot TF
   resolution. Operator flag: multi-TF is a real concern — either
   store multiple TF tapes OR develop an accurate 5m → higher-TF
   conversion. **Decision**: store 5m natively as the single source
   of truth; derive 15m / 1h / 4h / 1d on demand via deterministic
   OHLCV rollup (see § 3.6). One store, one truth.
3. **Fetch source**: Both — Coinbase primary, CoinGecko fallback.
   Fallback semantics = when the Coinbase fetch fails (asset not
   listed, delisted, rate-limited hard, etc.), try CoinGecko for
   whatever it can deliver. CoinGecko free tier caps 5m to the
   last ~1 day, so it's a reliability fallback for recent data
   only — not a deep-history filler.

### Scale implications of 5m

- ~105,120 candles per asset per year (288/day × 365)
- Coinbase's `fetch_ohlcv` per-call limit is typically 300 candles
  → ~350 chunks per asset per year
- At 1 s sleep between chunks: ~350 s ≈ 6 min per asset per year
- Full 35-asset YTD (April 1 → now, ~4 months) ≈
  35 × 4 × 30 × 288 = 1,209,600 candles across
  35 × 4 × 30 = 4,200 chunks × 1 s = 70 min wall-clock
- File size per (asset, year) at 5m ≈ 5-10 MB uncompressed JSON.
  For 35 assets × 1 year ≈ 175-350 MB total on disk.
  Compression (gzip) would drop to ~30-60 MB but complicates
  incremental append. Deferring compression to v3.24.x.

### 3.6  Multi-TF rollup (added per operator's flag)

Registry stores 5m natively. `get_candles(asset, since, until,
timeframe="1h")` internally reads the 5m stream and rolls up:

```
1h candle = {
  ts_ms:  first 5m ts in the hour bucket
  open:   first 5m open
  high:   max of 12 × 5m highs
  low:    min of 12 × 5m lows
  close:  last 5m close
  volume: sum of 12 × 5m volumes
}
```

Rollup is pure — same inputs always produce same outputs. No
hidden precision loss. Supported target TFs: 5m (native), 15m
(3×), 30m (6×), 1h (12×), 2h (24×), 4h (48×), 6h (72×), 12h
(144×), 1d (288×). Timeframes that don't divide evenly (e.g., 7m)
are rejected with a ValueError.

## 6  Sign-off gate

## 6  Falsification

This design is wrong if:

- (a) The operator's Coinbase account cannot fetch OHLCV via
  `connector.get_ohlcv` for historical ranges (would force us onto
  a separate historical data source such as CoinGecko + require the
  free-tier chunking discipline from the archived design).
- (b) `~/.acervator/stone_tablets/` collides with an existing
  operator directory (checked at v3.23.97 boot).
- (c) The manifest's `checksum_sha256` field drifts from any
  tablet's actual content — indicates external tampering or a
  bug in `_write_tablet`.
- (d) A Simulator call for a missing-coverage asset does NOT
  trigger an auto-fetch — indicates the sim integration point is
  wired wrong.
