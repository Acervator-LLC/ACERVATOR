# `src/exchange/ccxt_connector.py` and `src/exchange/crypto_assets.py`

Two defects kept `src/competition/market_rotation.py` from reaching its floor of
twelve eligible markets. `Ticker.volume_24h` held 0.0 for every Coinbase market,
and eight of the venue's twenty biggest bases had no CoinGecko id.

## The error

`CCXTConnector.get_ticker` read `quoteVolume` from Coinbase's single-market
ticker call, which serves no volume field of any kind.

```
--- fetch_ticker BTC/USD, singular ---
  last = 78046.78
  baseVolume = None
  quoteVolume = None
  info keys: ['ask', 'bid', 'exchange', 'price', 'product_id', 'side', 'size', 'time', 'trade_id']
--- CCXTConnector.get_ticker BTC/USD ---
  Ticker.volume_24h = 0.0
--- fetch_tickers BTC/USD row, plural ---
  baseVolume = 5239.84270947
  quoteVolume = 408952851.18
--- plural rows carrying a non-zero quoteVolume: 923 of 931
```

`MarketRotation.eligible_pool` refused eight of the top twenty before asking
their age.

```
RESULT BEFORE eligible      : 5
RESULT BEFORE refusals      : {'no_coingecko_id': 8, 'no_genesis_date': 7}
RESULT BEFORE open_window  : REFUSED pool_below_floor: coinbase holds 5 eligible
                             markets, under the floor of 12, so it draws nothing
```

## Reproduction

The before-state is a second git worktree at `f7f07157`, not a hand reversal.
`git show f7f07157:<path>` and the worktree file agree byte for byte on all three
changed files: 52558, 26498 and 17900 bytes, zero CRLF.

```
PYTHONWARNINGS=error python -X dev -X faulthandler U24_pool_run.py <tree> <label> <cache>
```

The driver connects `CCXTConnector("coinbase")` with empty credentials, folds one
`get_all_tickers` answer into a `MarketPairsScout`, and runs
`MarketRotation.eligible_pool` then `open_window`. `ProjectAgeLookup` takes a
scratch cache path, so no file under `~/.acervator` is written. Detail calls pace
at `AGE_LOOKUP_INTERVAL_S`, thirteen seconds.

## The cause

`src/exchange/ccxt_connector.py` mapped `raw.get("quoteVolume", 0)` from
`fetch_ticker`. Coinbase's single-market endpoint is a trade snapshot: price,
bid, ask, size and trade id. No 24h aggregate reaches it. The plural
`fetch_tickers` call carries `quoteVolume` on 923 of 931 rows, and
`src/exchange/data_pool.py` was already reading it there, so one field held a
real figure on the batch path and 0.0 on the single-market path.

`src/exchange/crypto_assets.py` registered forty assets. `ProjectAgeLookup`
reads `ASSETS[base].coingecko_id`, and ZEC, HYPE, VVV, USELESS, PUMP, TAO, AERO
and LIGHTER were absent, so `verdict_for` answered `no_coingecko_id` with no call
made.

## The correction

`CCXTConnector` keeps a per-symbol quote volume, filled by the
`get_all_tickers` call the platform already runs on a timer, and
`_quote_volume_for` reads the served figure first and the recorded one second.
The shared helper `row_quote_volume_24h` does the reading, so the single-market
path, the batch path in `data_pool` and the scout all compute the figure the same
way. No request was added to the venue.

Eight assets joined the catalogue. Each id came from CoinGecko's own record of
which of its coins trades that market on Coinbase Exchange, read through
`/coins/<id>/tickers?exchange_ids=gdax`. Ticker matching against the published
coin list was measured and rejected: of the twelve ids the catalogue already held
correctly, only SUI and XLM resolve to a single coin, and twelve separate coins
carry the ticker BTC. CoinGecko also carries Lighter under the ticker LIT, so no
ticker match finds it.

## The rerun

```
RESULT AFTER Ticker.volume_24h BTC/USD = 412916265.31
RESULT AFTER eligible      : 6
RESULT AFTER markets       : ['BTC/USD', 'ETH/USD', 'ZEC/USD', 'LINK/USD', 'DOGE/USDC', 'LTC/USD']
RESULT AFTER refusals      : {'no_genesis_date': 14}
RESULT AFTER draw_size     : 0
RESULT AFTER open_window  : REFUSED pool_below_floor: coinbase holds 6 eligible
                            markets, under the floor of 12, so it draws nothing
```

The platform's API log reports the volume it now reads.

```
[COINBASE] FETCH_TICKER | Get current price for BTC/USD | last=78,010.87
bid=78,010.87 ask=78,010.88 vol24h=411256638 | 102ms
```

Both runs paced at thirteen seconds and CoinGecko refused no call: twelve detail
requests before, fifteen after, zero HTTP 429.

The construction path `src/gui/main_window.py:277` uses reaches both repairs.
`SharedTestnetBridge.install_market_rotation` built the rotation and its lookup,
and the lookup's answer for the three newly named bases flipped.

```
BEFORE  ZEC/USD HYPE/USD LIGHTER/USD  has_cached_answer=True   no id, no call owed
AFTER   ZEC/USD HYPE/USD LIGHTER/USD  has_cached_answer=False  an id, a call owed
BEFORE  Ticker.volume_24h BTC/USD = 0.0
AFTER   Ticker.volume_24h BTC/USD = 412792386.26
```

## What the repair does not fix

The pool is six and the floor is twelve, so Coinbase still draws nothing. Seven
of the eight newly named projects publish no founding date and moved from
`no_coingecko_id` to `no_genesis_date`. Fourteen of the twenty now refuse for
that one reason.

`src/trading/volume_guard.py:302` copies the figure into the cap on order size.
`VolumeGuard.enabled` returns False on every call, and
`src/trading/bot_container.py:247` takes the direct exchange path while it is
False, so `_get_market_profile` never runs. That guard is a separate item.

`src/trading/extractor_bot.py:567` ranks a watch list on the figure. All 38 bots
in `bot_state.json` carry mode `scrumming`, so no `ExtractorBot` exists in the
fleet today and the ranking reaches nothing.
