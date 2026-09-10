# The rotating reward set — what each run printed, and the defects found

Reference. Subjects: `src/competition/market_rotation.py`,
`src/competition/project_age.py`, `src/competition/__init__.py`,
`src/exchange/market_pairs_scout.py`, `src/exchange/market_inspector_fetcher.py`,
`src/gui/shared_testnet.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Every run below used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.
No test was written. `main.py` was never launched: `main.py:812` builds an
instance guard whose `take_ownership` writes into the runtime folder, and the
operator is trading on this machine, so `SharedTestnetBridge.install_on` was
driven directly with every runtime path redirected into a scratch folder.

## The error

Two program faults, both found by running the real code against real venue data.

### The ranking mixed two units, and the wrong one chose the markets

`src/exchange/market_pairs_scout.py` read `baseVolume` into
`PairSnapshot.volume_24h`, which line 69 declares as a base-unit figure. A
base-unit figure counts coins, so it cannot order two markets. The rule that
reads it is "top 20 by volume".

`src/exchange/market_inspector_fetcher.py` held the same fault with a docstring
that contradicted the code.

```
src/exchange/market_inspector_fetcher.py  _pick_universe, before
    """Rank tickers by 24 h quote volume ..."""
    vol = float(tk.get("quoteVolume") or tk.get("baseVolume", 0) or 0)
```

The docstring promises quote volume. The expression silently returns base units
whenever a venue omits `quoteVolume`, and the sort then compares coins against
dollars.

### Every market ranked first by coins is a sub-cent token

One live Coinbase snapshot, 931 pairs, 403 assets after one book per asset. The
same list sorted each way shares one market out of twenty.

```
top 20 by quote_volume_24h
  BTC/USD ETH/USD ZEC/USD XRP/USD SOL/USD HYPE/USD VVV/USD NEAR/USD LINK/USD
  DOGE/USD USELESS/USD UNI/USD PUMP/USD SUI/USD ADA/USD TAO/USD XLM/USD
  AERO/USD LIGHTER/USD LTC/USD

top 20 by volume_24h, the base-unit field
  NEX/USD MOG/USD PEPE/USD BONK/USD SHIB/USD FLOKI/USD TOSHI/USD VTHO/USD
  PUMP/USD NOICE/USD SPELL/USD BNKR/USD DRB/USD B3/USD AMP/USD DOGINME/USD
  NOM/USD BLAST/USD PENGU/USD OXT/USD

same order: False
markets only the base ranking admits: 19 of 20
```

`PUMP/USD` is the sharpest single row: 3,818,829,171 coins traded, the largest
base volume on the venue, against 15,355,512.10 dollars, which is rank 13.
`BTC/USD` trades 5,224.63 coins and 409,375,465.28 dollars.

## Reproduction

```
cd <repo>
PYTHONPATH=<repo> PYTHONWARNINGS=error python -X dev -X faulthandler \
  <scratch>/U9_rules.py <scratch>
```

The driver connects the platform's own `CCXTConnector` to Coinbase with no
credentials, fills a real `MarketPairsScout` from `get_all_tickers`, and then
calls `MarketRotation` methods. Every figure below is the venue's.

## The cause

### Does the venue supply a quote volume — measured, not assumed

Yes, on the plural call, and no on the singular one. Both were asked.

```
connector.get_all_tickers()["BTC/USD"]
  quoteVolume 409059593.11      baseVolume 5232.1333725      last 78182.18

connector._ex.fetch_ticker("BTC/USD")
  quoteVolume None              baseVolume None              last 78172.92
  info {'trade_id': ..., 'price': '78172.92', 'size': '0.00000007',
        'side': 'BUY', 'exchange': 'coinbase'}
```

ccxt maps Coinbase's single-ticker call onto the last-trade endpoint, whose body
carries no 24-hour volume at all. The plural call carries it for every row: the
repaired function logs at debug whenever it has to derive the figure, and over all
931 ingested rows it logged **0** lines.

### Every consumer of a field named `volume_24h`

Three different records carry that name and they do not mean the same thing.

| Record | Filled from | Read by |
| ------ | ----------- | ------- |
| `PairSnapshot.volume_24h` | `baseVolume` | `src/gui/main_window.py:1877`, which passes it on as `baseVolume` |
| `Ticker.volume_24h` | `quoteVolume` | `src/trading/volume_guard.py:302` as `volume_24h_quote`; `src/trading/extractor_bot.py:567` to rank a watch list; `src/exchange/data_pool.py:315` |
| `TickerEntry.volume_24h` | `quoteVolume` at `data_pool.py:369`, or `Ticker.volume_24h` at `data_pool.py:315` | `data_pool.py:241`, `281`, `307`, `674` |
| `ArbitrageQuote.volume_24h` | its caller's argument | `src/trading/arbitrage.py:131` |
| `market_data` dict key | CoinGecko `/coins/markets` | `market_data.py:169` |

`PairSnapshot.volume_24h` keeps its meaning and its only reader keeps its figure.
The ranking reads the new `PairSnapshot.quote_volume_24h` instead.

### A second fault, named and not repaired

`Ticker.volume_24h` is 0.0 for every Coinbase market, because `get_ticker` reads
`quoteVolume` out of a body that has none.

```
Ticker(symbol='BTC/USD', bid=78179.57, ask=78179.58, last=78179.58,
       volume_24h=0.0, timestamp=1789021369.854)
```

`volume_guard.py:302` copies that into `MarketProfile.volume_24h_quote`, which
sizes live orders through `max_single_order_volume_pct`, and `data_pool.py:369`
writes the correct figure into the same cache entry from the plural call. Which
figure a bot sees depends on which path refreshed the entry last.

Repairing it changes what a number the operator's order sizing reads means, on 37
live bots mid-session. That is his decision, it is recorded here with its
measurement, and this unit did not touch it.

## The correction

One shared function, read by both rankings.

```python
def row_quote_volume_24h(row: object) -> float:
    """Return one raw ticker ``row``'s 24h volume in quote units.

    Reads ``quoteVolume`` where the venue serves it, and otherwise multiplies
    ``baseVolume`` by ``last``, so a ranking across markets never mixes a
    base-unit figure with a quote-unit one. Returns 0.0 for a row carrying
    neither.
    """
```

`PairSnapshot` gains `quote_volume_24h`, filled from that function, and
`volume_24h` is unchanged. `_pick_universe` calls the same function, so its
docstring and its code now agree.

Two further faults were found while driving the rule and repaired in this unit.

`ranked_usd_markets` first returned one row per market, so `BTC/USD` and
`BTC/USDC` both appeared and a top twenty held ten assets. It now keeps the
larger book per base.

`EURC` is a euro stablecoin and was absent from `STABLECOIN_DENYLIST`, which
already holds `EUR`. It ranked 21st on Coinbase and is now dropped by name.

## The rerun

Each of the four rules, driven on the venue's own state, with its refusal.

### The eligible pool — all three conditions, never any one

```
  1 BTC/USD        eligible
  2 ETH/USD        eligible
  3 ZEC/USD        no_coingecko_id
  4 XRP/USD        no_genesis_date
  5 SOL/USD        no_genesis_date
  6 HYPE/USD       no_coingecko_id
  7 VVV/USD        no_coingecko_id
  8 NEAR/USD       no_genesis_date
  9 LINK/USD       eligible
 10 DOGE/USD       eligible
 11 USELESS/USDC   no_coingecko_id
 12 UNI/USD        no_genesis_date
 13 PUMP/USD       no_coingecko_id
 14 SUI/USD        no_genesis_date
 15 ADA/USD        no_genesis_date
 16 TAO/USD        no_coingecko_id
 17 XLM/USD        no_genesis_date
 18 AERO/USD       no_coingecko_id
 19 LIGHTER/USD    no_coingecko_id
 20 LTC/USD        eligible

pool_size 5    draw_size 0
refusal_counts {'no_coingecko_id': 8, 'no_genesis_date': 7}
eligible ['BTC/USD', 'ETH/USD', 'LINK/USD', 'DOGE/USD', 'LTC/USD']
```

`no_genesis_date` refuses **7 of the real 20**, and `no_coingecko_id` a further
eight. Five markets pass all three conditions on the largest venue the platform
supports.

The volume condition refuses on its own, on the real rank 21.

```
{"symbol": "ARB/USD", "volume_rank": 21, "in_top_volume": false,
 "quote_volume_24h": 7326044.09, "is_eligible": false,
 "reason": "outside_top_volume"}
```

`age_reason` is empty on that row, which is the point: the age rule was never
asked, because the volume condition had already refused.

### The draw — a quarter, rounded up, never fewer than one

```
pool   1  quarter_rounded_up 1  draw_size 0
pool   5  quarter_rounded_up 2  draw_size 0
pool   7  quarter_rounded_up 2  draw_size 0
pool  10  quarter_rounded_up 3  draw_size 0
pool  11  quarter_rounded_up 3  draw_size 0
pool  12  quarter_rounded_up 3  draw_size 3
pool  13  quarter_rounded_up 4  draw_size 4
pool  16  quarter_rounded_up 4  draw_size 4
pool  20  quarter_rounded_up 5  draw_size 5

share ceiling on a 1000 pool  50
earners to exhaust one pool   20
```

Every row matches the table the issue records. The draw refuses to exceed a
quarter: a pool of 20 draws 5 and never 6, so one in four is the ceiling on any
market's chance.

### The floor of twelve — observed twice

The live pool is already below it, so the refusal needed no contrivance.

```
open_window refused: pool_below_floor: coinbase holds 5 eligible markets,
under the floor of 12, so it draws nothing
```

Driven to the boundary value through real filed exclusions:

```
season 2 pool_size 11  draw_size 0
open_window refused: pool_below_floor: coinbase holds 11 eligible markets,
under the floor of 12, so it draws nothing
season 1 pool_size 20  draw_size 5
```

Eleven refuses, twelve draws three, twenty draws five.

### The season boundary — an event, not a date

`currentSeason` is an integer in `contracts/CompetitionRegistry.sol:69` that
`advanceSeason` increments. No date, duration or calendar field exists in the
schedule module, so the boundary is expressed as the season number a pool is
computed for, and an exclusion records the first season it binds in.

```
filed in season 1, binds from season 2   BTC/USD
in effect in season 1                    ()
in effect in season 2                    ('BTC/USD',)
season 1 BTC/USD                         eligible
season 2 BTC/USD                         excluded_by_exchange
season 1 pool_size 5                     season 2 pool_size 4
```

The same market, the same venue data, one season apart. That is the refusal.

### The concealment

The chain carries the commitment and the count. It carries no market name.

```
chain tx args: {"exchange": "coinbase", "season": 1,
                "commitment": "2c69e1e853579c19...", "marketCount": 5}
chain event  : RotationCommitted, the same four fields
```

Each leaf is `sha256(salt + symbol)` and the salt is withheld until the close, so
the twenty candidate symbols cannot be hashed and matched against the root.
Asking for a membership proof while the window is open is refused.

```
REFUSAL - membership_proof while open: coinbase has an open window;
a membership proof would reveal the set it conceals
REFUSAL - a pool member not drawn: BTC/USD not_drawn
REFUSAL - a second window: a rotation window is already open on coinbase
```

At the close both publish together and the proof verifies against the root that
was already on the chain.

```
reveal {"commitment": "2c69e1e853579c19...", "salt": "3840a25be57405a0...",
        "markets": ["ADA/USD","HYPE/USD","LIGHTER/USD","UNI/USD","VVV/USD"]}
proof verified True   root 2c69e1e853579c19
REFUSAL - reward_reason after the close: no_open_window
```

What it does not conceal, and what the chain cannot hold:

```
the drawing node        holds the salt and the set in its own record file
    <rotation_path> while open: {"drawn": {"coinbase": [...5 symbols...]},
                                 "salts": {"coinbase": "3840a25be57405a0..."}}
an unbiased draw        the node chooses the set, then commits; the commitment
                        stops it changing the set, not choosing it
a verifiable draw       no other node can repeat the draw, because no shared
                        random value exists that several nodes produce together
encryption to a key     no field anywhere holds an exchange public key, and
                        BotIdentity is Ed25519, which signs and does not encrypt
```

A commitment is therefore what ships in place of encryption. On the property the
directive names it is the stronger of the two: encryption to an exchange lets
that exchange read its own rotation before the window, and a salted commitment
lets nobody read it.

## Construction and reach

`src/gui/main_window.py:277` calls `SharedTestnetBridge.install_on` inside
`_setup_ui`, before any tab is built. That method now builds the rotation
alongside the chain, the ledger and the certification socket, so the rotation
lives where every other PoA object the running program holds lives, and reads the
same chain.

```
before: 'src.competition.market_rotation' in sys.modules   False
from src.competition.local_testnet import LocalTestnet
after : 'src.competition.market_rotation' in sys.modules   True
```

`install_on` driven directly, every runtime path redirected:

```
live     MarketRotation  U9_rotation_live.json     chain LocalTestnet 2941857046176
testnet  MarketRotation  U9_rotation_testnet.json  chain LocalTestnet 2941857049696
same class True
bridge property: market_rotation is the attached object  True
summary  top_n_by_volume 20  min_eligible_pool 12  draw_denominator 4
         share_ceiling_pct 5  min_earners_per_market 20
```

**Nothing in the running program calls `eligible_pool` or `open_window` yet.** The
object is constructed on every launch and waits. The caller belongs with the
market allotment, which sizes a pool per market and is not built: the share
ceiling has its arithmetic here and no pool to apply it to. The age walk also
blocks for thirteen seconds per uncached market, so its caller must not be a GUI
timer.

## Demo mode

The two rows above are the proof. One class, one `open_window` path, two
`LocalTestnet` instances, two record files, no flag anywhere. The rotation takes
its chain at construction, which is the pattern the certification socket already
uses, and the tab payload's `chain` field names which one a surface reads.

## The pacing

Unit 8 measured CoinGecko refusing 34 of 40 detail calls at 2 seconds apart.
`AGE_LOOKUP_INTERVAL_S` is 13.0 seconds, which is inside the published 5 to 15
calls a minute band for the keyless endpoint. The pace is paid only when a call
actually leaves, which `ProjectAgeLookup.has_cached_answer` reports.

```
cold cache   20 markets   8 of 20 need no call (no coingecko_id)
             12 calls     12 answered, 0 refused
             walk 145.5 s
warm cache    5 dates served from the file, 7 nulls re-asked
              7 calls      7 answered, 0 refused
              walk  79.5 s
second and third walks in the same process   0 calls
```

Zero HTTP 429 at 13 seconds, against 34 of 40 refused at 2 seconds. A null answer
is not written to the file by design, so a fresh process re-asks those seven.

## The archetype fixtures, one good and one bad

```
coding_archetype  known_good.py exit 0          known_bad.py exit 1
ta_archetype      known_good_ta001.py exit 0    known_bad_ta001.py exit 1
docs_archetype    known_good.md exit 0          known_bad.md exit 1
```

## Verdicts

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
```
