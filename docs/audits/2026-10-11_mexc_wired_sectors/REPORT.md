# MEXC — the six sectors it serves, and the two its own order route holds

Read 2026-10-11 from mexc's own credential-free endpoints and its own documented
API reference. No credential was used, no order was placed, and no order was
previewed. `ccxt` 4.5.85, synchronous path, which is the path the product uses.

## The instrument, before any reading

Four hosts answer. Each one carries its own control, a path that cannot exist.

```
api.mexc.com/api/v3/ping                           200   2 B
api.mexc.com/api/v3/exchangeInfo                   200   1,555,334 B   1890 rows
  .../api/v3/this-path-cannot-exist-9f3a           404   30 B      the control
api.mexc.com/api/v1/contract/detail                200   2,305,198 B   1197 rows
  .../api/v1/contract/this-cannot-exist-9f3a       404   50 B      the control
contract.mexc.com/api/v1/contract/detail           200   2,308,075 B
  .../api/v1/contract/this-cannot-exist-9f3a       403   433 B     the control
mexcdevelop.github.io/apidocs/spot_v3_en/          200   445,494 B
mexcdevelop.github.io/apidocs/contract_v1_en/      200   316,221 B
  .../apidocs/spot_v3_en/this-cannot-exist-9f3a    404   9,379 B   the control
blog.mexc.com/                                     200   38,102 B  6,126 chars
  blog.mexc.com/this-cannot-exist-9f3a/            404   19,801 B  1,925 chars
```

`ccxt.mexc` composes its contract calls against `api.mexc.com/api/v1/contract`,
so that host is the one every reading below uses; `contract.mexc.com` serves the
same list and is not read from.

### The Help Center cannot be read, and that is the instrument

| page | markup | text | "United States" |
| ---- | ------ | ---- | --------------- |
| `www.mexc.com/support/articles/360039544031` | 93,327 B | 104 chars | 0 |
| `www.mexc.com/support/articles/9999999999999` | 93,329 B | 104 chars | 0 |
| `www.mexc.co/support/articles/360039544031` | 444,836 B | 102 chars | 0 |
| `www.coinbase.com/legal/user_agreement/united_states` | 281,147 B | **363,926 chars** | **37** |
| `blog.mexc.com/` | 38,102 B | 6,126 chars | 0 |
| `blog.mexc.com/this-cannot-exist-9f3a/` | 19,801 B | 1,925 chars | 0 |

An invented article id answers two bytes away from a real one, on the same host,
with the same 104 characters of text. The zero on that host is the page shape,
not the venue. The positive control is Coinbase's own United States user
agreement, which the same reader pulls 363,926 characters off; the negative one
is `blog.mexc.com`, which serves a real body of 6,126 characters against a
1,925-character 404 and carries no refusal clause.

`www.mexc.com` refuses curl's default header set with 403 on every path. The
readings above use a browser header set: a Chrome user agent, `Accept`,
`Accept-Language`, four `sec-ch-ua` and `Sec-Fetch` headers and
`Upgrade-Insecure-Requests`.

### What that settles, and what it does not

mexc is **not IP-blocked**: every public endpoint above answered from a United
States address. So mexc stays out of `US_IP_BLOCKED_EXCHANGES`.

Whether mexc's terms refuse a United States account is **not established**, not
"no". The clause would live in the Help Center, and the Help Center serves no
text to any reader available here. `US_ACCOUNT_RESTRICTED_EXCHANGES` is unchanged
and does not hold mexc, which is the same answer the manual page has carried
since 2026-08-28; what is new is the reason, which is now measured.

## Sector truth comes from the venue

### `/api/v3/exchangeInfo` — 1890 rows, 29 fields

```
status                 "1" 1889      "2" 1
permissions            ("SPOT",) 1890
orderTypes             ("LIMIT","MARKET","LIMIT_MAKER") 1855
                       ("LIMIT","LIMIT_MAKER") 35
isSpotTradingAllowed   true 1810     false 80
quoteAsset             USDT 1489  USDC 226  USD1 114  BTC 21  EUR 16
                       ETH 8  BRL 6  USDE 6  USDF 4
baseAsset              1890 rows
fullName               1890 rows      the venue's own name per asset
conceptPlates          1890 rows      42 distinct words
```

### `/api/v1/contract/detail` — 1197 rows, 70 fields

```
futureType        1 on all 1197
state             0 on all 1197
apiAllowed        true 1168     false 29
quoteCoin         USDT 1088  USDC 64  USD1 35  USD 10
settleCoin        USDT 1088  USDC 64  USD1 35, and 13 inverse coins at 1 each
contractSize      13 distinct values, 0.00001 to 1,000,000
automaticDelivery 0 on 1183     1 on 14
baseCoin          1197 rows
baseCoinName      1197 rows      the venue's own name per contract
conceptPlate      1028 rows      55 distinct words
```

mexc's own contract reference documents `conceptPlate` on the instrument record
and prints two of its words in the response example:

> "conceptPlate" : [ "mc-trade-zone-grey" , "mc-trade-zone-pow" ]

It publishes no list of the whole vocabulary, so every word below was read off a
live row. The spot reference lists `exchangeInfo`'s fields and does not list
`conceptPlates` among them; the field is served on all 1890 rows.

### The spot vocabulary, the venue's own spelling

```
Innovation 1384   Main 273   0 Fees 235   Assessment 233   MEME 215
LAYER 1 / LAYER 2 179   Tokenized Stocks 165   AI 129   Web3.0 111
DeFi 100   GameFi 80   RWA 76   Robinhood Ecosystem 62   Privacy 57
DePIN 54   Stock Meme Tokens 51   POW 38   Launchpad 38   WLFI 33
ZK 31   BTC Ecosystem 29   AI Agent 28   NFT 28   Stablecoins 21
Metaverse 21   BONKGUY 21   Perp Dex 18   CEX TOKEN 18   Storage 16
Fan Token 15   TON Ecosystem 15   Precious Metals 10   Defense & Energy 10
InfoFi 9   Prediction Market 7   Arc 6   DeSci 5   SocialFi 3
Chinese 3   Pre-IPO 2   Metals 1   Crude Oil 1
```

### The contract vocabulary

```
0fees 616   tradfi 500   Stock 469   mainly 219   layer2 111   MEME 76
web3 73   stockindex 66   DeFi 61   ETF 61   ai 47   pow 30
innovation 30   aiapplicationlayer 28   GameFi 27   semiconductors 27
AICompute 25   nft 21   aisemiconductors 20   Commodities 19   metaverse 19
contract-new 19   RWA 18   metalsfutures 17   privity 16   PerpDex 16
metals 13   TON 13   aistorage 12   aerospace 12   finance 12
aicomputing 11   storagechips 10   japanstock 10   TechGiants 9   cpo 8
aerospacedefense 8   aipowerenergy 8   Forex 8   InfoFi 6   CEX 6
CryptoConcepts 6   preipo 6   robinhood 5   stockmeme 4   Chinese 4
OIL 4   x402 4   healthcare 4   launchpad 3   AIAGENT 3   DePIN 3
SocialFi 1   arc 1   Prediction 1
```

Each word above is prefixed `mc-trade-zone-` on the wire.

### Which words name a family, and which do not

Of the 97 words across both vocabularies, exactly **one** resolves through
`src/trading/ata_spm.py, in asset_class_named` with no `words` row: the spot word
`Metals`, through `RETIRED_CLASSES`, onto commodities. Driven over all 97, every
other word answers `NO_ASSET_CLASS`. `Metals` is named in the record anyway, so
no word of either vocabulary resolves by accident.

The words the records name:

| the word | onto | the venue's own evidence |
| -------- | ---- | ------------------------ |
| `Tokenized Stocks` | stocks | 165 markets, "Apple xStock", "Tesla (Ondo)", "Alibaba (Ondo)" |
| `Pre-IPO` | stocks | "SPACEX(PRE)", "Paimon Polymarket S" |
| `Precious Metals` | commodities | "PAX Gold", "Tether Gold", "iShares Silver Trust", "Uranium.io" |
| `Metals` | commodities | "SILVER", one market |
| `Crude Oil` | commodities | "United States Oil", one market |
| `mc-trade-zone-Stock` | stocks | 469 markets, "MRNA", "MU", "TOYOTA" |
| `mc-trade-zone-stockindex` | indices | "SP500", "NAS100", "QQQ", "SPY", "US30", "JP225" |
| `mc-trade-zone-ETF` | indices | "TQQQ", "SQQQ", "SOXL", "XLE", "ARKK", "GLD" |
| `mc-trade-zone-Commodities` | commodities | "GOLD(XAU)", "SILVER(XAG)", "GAS(NG)", "COPPER(XCU)" |
| `mc-trade-zone-metals` | metals | the same gold, silver, platinum and palladium rows |
| `mc-trade-zone-metalsfutures` | commodities | plus "ALUMINIUM(XAL)", "NICKEL(XNI)", "ZINC(XZN)", "LEAD(XPB)" |
| `mc-trade-zone-OIL` | commodities | "OIL(WTI)", "OIL(BRENT)" |
| `mc-trade-zone-Forex` | forex | BRL, EUR, JPY, GBP, CAD, TRY, AUD, CHF |
| `mc-trade-zone-preipo` | stocks | "OPENAI", "ANTHROPIC", "POLYMARKET", "OURA", "MOONSHOT", "YMTC" |
| `mc-trade-zone-japanstock` | stocks | "TOYOTA", "SONY", "SOFTBANK", "MURATA", "ADVANTEST" |

The words the records name as **no family**, each because the venue's own market
names refute the reading a human would take:

| the word | markets | what they are |
| -------- | ------- | ------------- |
| `Stock Meme Tokens` | 51 | "Boner Coin", "Send Nudes", "Stonks", "RuneScape Gold" |
| `mc-trade-zone-stockmeme` | 4 | SI, MUSEBOOK, GM, GP — the same codes on the contract host |
| `mc-trade-zone-robinhood` | 5 | PONS, MEMEROBINHOOD, BONER, MOO, DELTA |
| `Robinhood Ecosystem` | 62 | "Robin the Frog", "Cash Cat", "Hoodrat" |
| `mc-trade-zone-Chinese` | 4 | Chinese-language meme tokens |
| `Prediction Market` | 7 | protocol tokens: Azuro, Drift, Opinion |
| `mc-trade-zone-Prediction` | 1 | DRIFT, the same protocol token |
| `Defense & Energy` | 10 | all ten also carry `Tokenized Stocks`, which precedes it |
| `mc-trade-zone-tradfi` | 500 | spans stocks, commodities, forex and indices |

## Three records, because the venue writes the general word first

`mc-trade-zone-Stock` precedes `mc-trade-zone-stockindex` and
`mc-trade-zone-ETF` in the same row's own list, on every one of the 66 rows that
carries either:

```
55 rows   (Stock, ETF, stockindex)
11 rows   (Stock, stockindex)
 5 rows   (Stock, ETF)
 1 row    (metals, Commodities, ETF)        GLD, which reads commodities
```

`src/exchange/ccxt_connector.py, in _read_asset_sector_rows` takes the first word
that resolves, so one record would call all 66 index funds equities and never
reach the venue's own index word. Driven under a single record keyed on
`conceptPlate`, 65 of the 66 answered stocks.

mexc therefore holds three records, read in order:

```
1  spotPublicGetExchangeInfo    rows_key symbols    sector_key conceptPlates
2  contractPublicGetDetail      rows_key data       sector_key conceptPlate
       the specific families; mc-trade-zone-Stock onto NO_PUBLISHED_FAMILY
3  contractPublicGetDetail      rows_key data       sector_key conceptPlate
       mc-trade-zone-Stock onto stocks, and nothing else
```

`_read_asset_sector_rows` leaves a code already holding a non-empty sector
untouched, so the 66 index codes keep indices and the other 392 stock-zone codes
take stocks. The spot list names its rows under `symbols`; every earlier venue
named them under `data`, so `AssetSectorRecord` gained a `rows_key`.
`_asset_sector_rows` reads that key in place of the module constant and keeps the
constant as its default, so every earlier venue's reading is unchanged — driven
over coinbase, kraken, gateio, bitget, okx, okxus, bitfinex, gemini, kucoin,
bitstamp and cryptocom, twice.

The record names a sector for **650 of mexc's 2013 base codes**: stocks 553,
indices 65, commodities 24, forex 8.

## What the record gains, and what it costs

Driven over all 3087 markets `ccxt.mexc.load_markets` serves, through
`src/exchange/ccxt_connector.py, in market_asset_class`, with no credential and
no order placed.

```
                 before   after    move
crypto             1869    1705    -164
stocks                0     562    +562
futures_perps      1175     697    -478
indices               0      71     +71
commodities           9      36     +27
forex                34      16     -18
                   ----    ----
                   3087    3087
```

679 markets move, under these transitions:

```
futures_perps -> stocks        398
crypto        -> stocks        164
futures_perps -> indices        71
futures_perps -> commodities    14
crypto        -> commodities     13
crypto        -> indices          1
forex         -> crypto          13
forex         -> futures_perps    5
```

661 of the 679 reach a sector no reading gave them. The 18 that leave forex are
corrections, and the venue's own name field and its own price feed settle each:

| base code | the venue's own name or zone | `GET /api/v3/ticker/price` | the currency's own rate |
| --------- | --------------------------- | -------------------------- | ----------------------- |
| `MNT` | "Mantle" | 0.5613 | a tugrik near 0.00028 |
| `SCR` | "Scroll" | 0.02577 | a rupee near 0.068 |
| `TOP` | "TOP Network" | 0.0000695 | a pa'anga near 0.42 |
| `RON` | "RONIN", in `GameFi` | — | a leu near 0.23 |
| `BOB` | in `BTC Ecosystem` | 0.004636 | a boliviano near 0.145 |
| `COP` | in `DeFi` | 0.0003055 | — |
| `USD` | "USD", a dollar token | 1.001 | the dollar itself |
| `USD1` | "USD1", in `Stablecoins` | 0.99993 | the dollar itself |
| `USDS` | "Sky Dollar" | 1.0007 | the dollar itself |
| `USDC` | "USDCoin" | — | the dollar itself |
| `ALL` | priced off `BINANCE_FUTURE` alone | — | a lek near 0.012 |

`USD/USDT`, `USD/USDC`, `USD1/USDT`, `USD1/USDC`, `USDC/USDT` and `USDS/USDT`
each quote a dollar token against a dollar token, so none holds a second
currency — the reading bitfinex's, gemini's and bitstamp's rows already take for
the same codes.

Three codes the record wrongly drops are the real cost, and three
`CITED_VENUE_BASE_SECTORS` rows take them back:

| base code | markets | the venue's own evidence |
| --------- | ------- | ------------------------ |
| `PLN` | `PLN/USDT`, `PLN/USDC` | `fullName` "Polish Zloty"; `PLNUSDT` 0.2546 |
| `ARS` | `ARS/USDT` | `ARSUSDT` 0.0006163, the Argentine peso; `Stablecoins` zone |
| `MXN` | `MXN/USDT` | `MXNUSDT` 0.0564, the Mexican peso; `Stablecoins` zone |

Each bases one or two markets and every one is quoted in a dollar token, so the
base grain carries them.

Two `CITED_VENUE_MARKET_SECTORS` rows take two more. `USDC` bases four spot
markets — `USDC/USDF`, `USDC/USDT`, `USDC/EUR`, `USDC/BRL` — and one perpetual,
and only two hold a national currency:

```
USDCEUR  0.893   the inverse of the venue's own EURUSDT 1.1207
USDCBRL  5.025   the inverse of the venue's own BRLUSDT 0.1992
```

A third market row is the one base code mexc's two hosts give to two different
assets. Spot `EWT` is "Energy Web", a crypto token; contract `EWT_USDT` is the
iShares MSCI Taiwan fund and carries `mc-trade-zone-stockindex`. Driven over all
3087 markets it is the only such code: every other base code either host names a
sector for sits on one host alone or names the same asset on both, and **zero**
contract markets take their sector from the spot record.

With those six rows the record costs nothing. Final recording, read back through
`src/exchange/market_rules_store.py, in recorded_classes`:

```
crypto 1705   futures_perps 697   stocks 562   indices 71
commodities 36   forex 16          total 3087
```

### The four collision codes

| code | spot markets | contract markets | what settles it |
| ---- | ------------ | ---------------- | --------------- |
| `NOK` | 0 | 0 | no mexc market names it |
| `AMD` | 0 | 0 | no mexc market names it |
| `SGD` | 0 | 0 | no mexc market names it |
| `MNT` | 2 | 1 | `fullName` "Mantle"; `MNTUSDT` 0.5613 |

Three of the four base nothing on this venue, and the fourth is settled by the
venue's own name field, so no table row is needed for any of them.

## The six points, per sector

| sector | market list | order route | order shape | position and fill | candles | variant |
| ------ | ----------- | ----------- | ----------- | ----------------- | ------- | ------- |
| crypto | 1705 spot | `POST /api/v3/order` | `symbol`, `side`, `type`, `quantity` or `quoteOrderQty` | `fetch_balance`, `fetch_my_trades` | eight granularities | Crypto Scrumming |
| stocks | 164 spot, 398 contract | the spot route; the contract route is under maintenance | the same two bodies | `fetch_balance` on spot, `fetch_positions` on contract | the same eight | Stock Scrumming |
| commodities | 13 spot, 23 contract | the same | the same | the same | the same eight | Commodity Scrumming |
| forex | 8 spot, 8 contract | the same | the same | the same | the same eight | Forex Scrumming |
| indices | 71 contract | the contract route alone, under maintenance | `symbol`, `vol`, `type`, `openType`, `side` | `fetch_positions` | the same eight | Index Scrumming |
| futures_perps | 697 contract | the contract route alone, under maintenance | the same | the same | the same eight | Futures Scrumming |

## The order shape

### Spot — `POST /api/v3/order`

The venue's own New Order page:

> base on different type, some params are mandatory:
> LIMIT — quantity, price
> MARKET — quantity or quoteOrderQty

Composed with no credential reaching the venue, by replacing `ccxt`'s own
`fetch` before any key was set:

```
BTC/EUR buy  market  price None    symbol=BTCEUR&side=BUY&type=MARKET&quantity=0.001
BTC/EUR buy  market  price 50000   symbol=BTCEUR&side=BUY&type=MARKET&quoteOrderQty=50&price=50000
BTC/EUR sell market  price None    symbol=BTCEUR&side=SELL&type=MARKET&quantity=0.001
BTC/EUR sell market  price 50000   symbol=BTCEUR&side=SELL&type=MARKET&quoteOrderQty=50&price=50000
BTC/EUR buy  limit   price 50000   symbol=BTCEUR&side=BUY&type=LIMIT&quantity=0.001&price=50000
BTC/EUR sell limit   price 50000   symbol=BTCEUR&side=SELL&type=LIMIT&quantity=0.001&price=50000
```

`ccxt.mexc.create_spot_order_request` writes `quantity` on a market order priced
None and `quoteOrderQty` of `amount` times `price` on a market order carrying a
price. `src/exchange/ccxt_connector.py, in place_order` fetches a ticker and
supplies that price on a MARKET BUY and on nothing else, so the buy carries the
cash and the sell carries the count. mexc joins `CITED_CASH_MARKET_BUY` as its
fifth member, and it is the first venue there whose unit is set by the price this
program supplies rather than by the venue's own default.

`has['createMarketBuyOrderWithCost']`, `has['createMarketOrderWithCost']` and
`has['createMarketSellOrderWithCost']` all read True on mexc's capability map,
and no caller in this tree reaches the separate methods they name.

### Contract — `POST /api/v1/private/order/create`

```
BTC/USDT:USDT buy  market  {"symbol":"BTC_USDT","vol":1.0,"type":6,"openType":2,"side":1}
BTC/USDT:USDT sell market  {"symbol":"BTC_USDT","vol":1.0,"type":6,"openType":2,"side":3}
BTC/USDT:USDT buy  limit   {"symbol":"BTC_USDT","vol":1.0,"type":1,"openType":2,"price":50000.0,"side":1}
BTC/USDT:USDT sell limit   {"symbol":"BTC_USDT","vol":1.0,"type":1,"openType":2,"price":50000.0,"side":3}
```

`vol` is a contract count on both sides and no cash field appears, and
`src/trading/scrumming/sizing.py, in market_buy_names_cash` already answers False
for a symbol carrying `SETTLE_LEG`, so no contract order is sized as cash. A
0.001 order on the same symbol raised `InvalidOrder: amount of BTC/USDT:USDT must
be greater than minimum amount precision of 1`, which is the whole-contract step
the venue publishes as `volUnit` 1.

### The contract order route is under maintenance, in the venue's own words

mexc's own contract reference marks six of its own order endpoints:

```
Order (Under maintenance)
Bulk order (Under maintenance)
Cancel the order (Under maintenance)
Cancel the order according to the external order ID (Under maintenance)
Cancel all orders under a contract (Under maintenance)
Trigger order (Under maintenance)
```

The documented path is `POST api/v1/private/order/submit`, with the body the
reference describes:

> USDT perpetual contract trading offers limit and market orders. You can place
> an order only you have enough money in your account. Once you place an order,
> your account funds will be frozen.

The path `ccxt` composes is `POST /api/v1/private/order/create`, which that
reference does not document at all. The contract list itself carries
`apiAllowed`, true on 1168 of its 1197 markets and false on 29, so the venue
publishes a per-market API flag beside the host-wide notice.

Every read endpoint the reference lists is unmarked. The detours searched, and
what shut each:

```
another endpoint      order/create, the path ccxt sends — undocumented, so
                      nothing published says whether it answers
another API version   the contract reference publishes v1 alone
another doc host      mexcdevelop.github.io is the host ccxt's own method map
                      links to; the Help Center serves no text
the page's script     the reference is served markup, read as 95,318 characters
another product       the SPOT host, which carries no maintenance notice and
                      lists tokenised equities, gold and silver tokens and three
                      national currencies — this is the detour that answers
a tree capability     apiAllowed per market, read above
another account type  the reference names "Required permissions: Trading
                      permission" and no account tier
```

So indices and futures_perps read **yes-if**, not "no": the door exists and the
venue says it is under maintenance, which is a venue-side state. The other four
sectors each hold spot markets on a route carrying no notice.

## The eight connections, each driven with its own control

Driven with `USERPROFILE` and `HOME` redirected to a temporary directory; the
operator's own runtime tree was neither read nor written.

```
1  SUPPORTED_EXCHANGES holds mexc            True
   control, an invented id                   False
2  venues_for_class answers mexc             all six sectors
   control, an invented venue                False in all six
3  the Add form names the venue              "Mexc (mexc)" on all six sectors
   control, a row index past the last        "Press a venue above to choose it."
4  CCXTConnector("mexc")                     builds, exchange_id mexc
   control, an invented id                   ValueError
5  record_venue wrote                        3087 rows
   recorded_classes read back                3087 rows, all six sectors
   control, an unrecorded venue              0 rows
6  declared_order_types                      "market and limit"
   order_types_for on all six sectors        "market and limit"
   control, an invented venue                None
   market_buy_names_cash BTC/USDT            True
   market_buy_names_cash BTC/USDT:USDT       False
   control, an invented venue                False
7  variant_holds_market                      True on all 3087 markets
   control, an invented sector               False
8  gate_log_path("mexc", sector)             trade/gate/mexc/<sector>/gate.log
                                             on all six, inside the redirected
                                             home
```

Connection 2's control cannot be an invented **sector**:
`src/gui/main_tabs/asset_class_surface.py, in normalise` answers the first
declared class for a name it does not hold, so an invented sector reads as
crypto. The control is an invented venue id, which answers False in all six.

### Connection 5 needed a repair

`ccxt.mexc.fetch_currencies` calls `spotPrivateGetCapitalConfigGetall`, a signed
endpoint, and carries ccxt's own comment:

> this endpoint requires authentication while fetchCurrencies is a public API
> method by design, therefore we check the keys here and fallback to generating
> the currencies from the markets

`load_markets` calls it whenever a credential is present. Driven against a
credential mexc refuses that endpoint for, `load_markets` raised
`BadRequest: mexc {"code":10072,"msg":"Api key info invalid"}` and recorded no
market at all. `mexc` now sits in `DISABLE_FETCH_CURRENCIES` beside `coinbase`,
which `sync_connect` applies before `load_markets`, so a key without the wallet
scope still loads 3087 markets. With no credential the endpoint is skipped and
the same 3087 load, which is every reading in this document.

## Order types

`src/trading/scrumming/sizing.py, in order_types_for` answered None for all six
sectors on mexc before this unit — the gap gemini, kucoin, bitstamp and
cryptocom each found in turn. `CITED_VENUE_ORDER_TYPES` gains a row in all six.

`declared_order_types` reads "market and limit" off mexc's own capability map,
where `createMarketOrder` is True, and both order routes compose the pair: the
spot list publishes `orderTypes` per market, reading
`["LIMIT","MARKET","LIMIT_MAKER"]` on 1855 of 1890 rows and
`["LIMIT","LIMIT_MAKER"]` on the other 35, and the contract body carries a
numbered `type`, 6 for a market order and 1 for a limit order.

The recorded value is what `order_types_for` reads first, and the cited row
answers only where a record carries none, so the 35 limit-only spot markets keep
their own declaration.

## Candles

`src/exchange/timeframes.py` needed no change, and gained a comment naming what
was read. `ccxt` 4.5.85 keys mexc's granularities by market kind:

```
spot   1m 5m 15m 30m 1h 4h 1d 1w 1M            nine
swap   1m 5m 15m 30m 1h 4h 8h 1d 1w 1M         ten
```

`ALL_TIMEFRAMES` draws eight of the nine both maps share, which is exactly the
existing row: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w. The one both publish and
`ALL_TIMEFRAMES` leaves is 1M; 2h, 6h and 12h are the three `ALL_TIMEFRAMES`
holds that mexc publishes on neither map. One row therefore serves a spot pair
and a perpetual alike.

## Variants

`src/trading/scrumming/sizing.py, in SECTOR_VARIANTS` names a variant for all
six sectors and `VARIANTS_BUILT` is built from its values, so every sector mexc
records a market in already carries a built variant. Driven over all 3087
markets, `variant_holds_market` reads True on every one:

```
Crypto Scrumming 1705   Futures Scrumming 697   Stock Scrumming 562
Index Scrumming 71      Commodity Scrumming 36  Forex Scrumming 16
```

Ten of the 3087 still refuse an order, and the variant is not what refuses them.
`ccxt.mexc` sets `options['fetchMarkets']['types']` to spot and linear swap, and
ten inverse perpetuals load anyway:

```
BTC/USD:BTC    ETH/USD:ETH     XRP/USD:XRP     SOL/USD:SOL    DOGE/USD:DOGE
SUI/USD:SUI    ADA/USD:ADA     LINK/USD:LINK   AVAX/USD:AVAX  LTC/USD:LTC
```

Each is margined in the coin it tracks, so `permits_size_shapes` reads True and
`permitted_size_shapes` answers a cash amount on the buy and on the sell alike.
`size_shape_refusal` answers for all ten:

> the venue permits a cash amount alone on a buy of this product, and every built
> variant sizes a unit count rather than a cash amount in the quote currency

That is this issue's row 6, unbuilt, and mexc is the second venue after binance
to select it. Driven over all 3087 markets: `permits_size_shapes` True on 10,
`size_shape_refusal` non-empty on the same 10 and empty on the other 3077. All
ten sit in futures_perps, so that sector sizes 687 of its 697 markets.

`market_unit_rule` over the same 3087:

```
commodities    fractional 13     whole 23
crypto         fractional 1655   whole 49
forex          fractional 8      whole 8
futures_perps  fractional 0      whole 697
indices        fractional 1      whole 71
stocks         fractional 0      whole 562
```

Every contract steps in whole contracts, which `volUnit` 1 publishes, so
`VARIANT_WHOLE_UNIT`'s arithmetic governs 1420 of mexc's markets.

## The arithmetic

```
sector          offered  Add form  mexc markets  offered - form
crypto               22        22          1705               0
stocks               21        21           562               0
commodities          20        20            36               0
forex                12        12            16               0
indices              19        19            71               0
futures_perps        17        17           697               0
```

Both sets are narrowed from one superset,
`src/gui/main_tabs/asset_class_surface.py, in known_venues`, through
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows`, so
offered minus connectable is zero on every sector by construction, and the
subtraction above is the proof rather than the design.

## The other eleven venues did not move

coinbase, kraken, gateio, bitget, okx, okxus, bitfinex, gemini, kucoin, bitstamp
and cryptocom were driven through their own `market_asset_class`, before and
after, twice each and minutes apart in the same session.

```
coinbase   commodities 25  crypto 904   forex 20  futures_perps 168  indices 6   stocks 33
kraken     commodities 6   crypto 1416  forex 38
gateio     commodities 20  crypto 2033  forex 6   futures_perps 619  indices 18  options 3418  stocks 565
bitget     commodities 12  crypto 578   futures_perps 534  stocks 3141
okx        commodities 21  crypto 1021  futures_perps 483  options 2780  stocks 400
okxus      commodities 4   crypto 1013  stocks 135
bitfinex   commodities 9   crypto 189   forex 4   futures_perps 76   indices 10
gemini     commodities 6   crypto 324   forex 2   futures_perps 13
kucoin     commodities 12  crypto 958   forex 2   futures_perps 527  stocks 160
bitstamp   commodities 6   crypto 240   forex 11  futures_perps 12   indices 2
cryptocom  commodities 16  crypto 561   forex 2   futures_perps 247  indices 28  stocks 134
```

Zero venues differ between the before and after readings, in either pair, and
zero differ between the two before readings or between the two after readings,
so no venue's own field moved under the drive. The control is a copy of one
after reading with one count raised by one, and the comparison reports it as a
difference:

```
bitget: commodities 12 -> 13      reported
```

The first census attempt read ten of the eleven: `getattr(ccxt, "gateio")`
raised `AttributeError`, because the library names that class `gate`.
`src/exchange/ccxt_connector.py, in resolve_ccxt_class` is what the product uses
and what the census uses now, and gateio reads 6679 markets.

## The manual page is add-only

Every sentence of the published page survives verbatim in the working page.
Measured against `git show origin/current:docs/manual/15-venue-compatibility.md`,
decoded as UTF-8:

```
committed sentences                                  1740
committed sentences missing from the working page        0
distinct sentences added                                28
```

The control is two-sided. One phrase reworded inside one committed sentence makes
that sentence missing, and the committed page compared against itself reports
zero missing. The two table rows mexc's own pages contradict are kept verbatim in
`OVERTAKEN, quoted whole:` blocks with a `True today:` line beneath each.

## The verdict, three words only

```
crypto           yes
stocks           yes
commodities      yes
forex            yes
indices          yes-if
futures_perps    yes-if
```

Each yes-if names the same first cost: mexc's own contract reference marks its
own order endpoints "Under maintenance", and every market in those two sectors is
a contract. Both sectors record and chart, and an order into either reaches a
path the venue publishes as held. futures_perps names a second cost of its own:
10 of its 697 markets are the inverse perpetuals above, whose only permitted
shape is a cash amount, which row 6 has not built, so those ten refuse before the
route is even reached. The other 687 size, and so do all 71 index markets. What
the operator must do is nothing; what must change is the venue lifting its own
notice, and row 6 landing. Neither sector is a "no", because the door exists and
is named.

## What the mexc reading cannot show

No credential was used for any reading in this document, so nothing here proves
mexc accepts a live order from this program; the order bodies above are what the
library composes, not what mexc acknowledged. One call did reach a private
endpoint: the first order composition set a placeholder key before
`load_markets`, and `fetch_currencies` sent a signed request that mexc refused
with code 10072. That refusal is the only authenticated call in this unit, it
placed nothing and previewed nothing, and it is what found the
`DISABLE_FETCH_CURRENCIES` repair; every later composition replaced `ccxt`'s own
`fetch` before any key was set.

mexc's own Help Center cannot be read as text on either of its hosts, so no
clause about a United States account was read and none was ruled out. The
`www.mexc.com` support path answers 200 for an article id that cannot exist, two
bytes from a real one, so no status code from that host was read as a reading.
Every quotation above comes from `api.mexc.com` or from
`mexcdevelop.github.io/apidocs/`, and each answers 403 or 404 for a path that
cannot exist.
