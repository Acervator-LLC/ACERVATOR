# Bitstamp — the sectors it serves, and the three a United States account trades

Read 2026-10-11 from bitstamp's own credential-free endpoints and its own
published pages. No credential was used, no order was placed, and no order was
previewed. `ccxt` 4.5.85, synchronous path, which is the path the product uses.

## The instrument, before any reading

`www.bitstamp.net` serves every non-API path behind an Imperva shell. The body
is 205 bytes carrying one Incapsula script and nothing else, and the host
answers **200 for a path that cannot exist**:

```
/terms-of-use/                     200   205 B   Incapsula shell
/legal/terms-of-use/inc/           200   212 B   Incapsula shell
/this-path-does-not-exist-9f3a/    200     -     the control
```

So no status code from that host is a reading. Two hosts answer real bodies, and
every quotation in this report comes from one of them:

```
www.bitstamp.net/api/v2/...   JSON, 200, real rows
blog.bitstamp.net/post/...    215 KB HTML
```

A `Mozilla/5.0` user agent with no platform string drew a 2265-byte shell from
one control page where a full Chrome agent drew 388 KB. Every fetch below uses
the full agent, and every body length is reported so a short body is visible as
a short body.

### The US-refusal search is two-sided

One instrument over four pages: a refusal phrase and a United States mention
must both appear inside 420 characters of one another.

| page | text | refusal passages |
| ---- | ---- | ---------------- |
| kucoin terms-of-use (refusal exists) | 84,754 | **4** |
| coinbase user agreement (no account refusal) | 363,667 | 6, none an account refusal |
| bitstamp perpetual-futures post | 8,208 | **1** |
| bitstamp terms-of-use post | 5,276 | **1** |

The positive side fires and quotes kucoin's clause whole: "the User (whether as
an individual or legal entity) is not a resident of or registered in, any of the
Restricted Locations. For the purpose of this Agreement, 'Restricted Locations'
shall include the United States". Coinbase's six passages read on inspection as
an advice disclaimer, a securities-arm clause and a content-copying
prohibition — the instrument fires on that page and finds no account refusal,
which is the negative reading.

A first pass matched per sentence and reported **zero** on kucoin, whose clause
spans two sentences. That zero was the instrument, not the venue, and it was
corrected before any reading was reported.

## Sector truth comes from the venue, and bitstamp publishes it twice

### `/api/v2/markets/` — 271 rows, 22 fields

```
asset_class    none 251   CRYPTO 13   COMMODITIES 4   ETF 2   FX 1
market_type    SPOT 251   PERPETUAL 20
payoff_type    none 251   Linear 20
contract_size  none 251   1.00000000 20
max_leverage   none 251   10.00 15   5.00 5
trading        Enabled 270   Disabled 1
```

Every one of the 20 perpetual rows, with the venue's own fields:

| market | `asset_class` | `underlying_asset` | `isin` |
| ------ | ------------- | ------------------ | ------ |
| `BRENT/USD-PERP` | COMMODITIES | Kaiko Brentoil Reference Rate | EZDYY9LD5K66 |
| `GOLD/USD-PERP` | COMMODITIES | Kaiko GOLD Benchmark Reference Rate | EZ2PKGJGBCW1 |
| `SILVER/USD-PERP` | COMMODITIES | Kaiko SILVER Benchmark Reference Rate | EZ8BQYJ29D49 |
| `WTI/USD-PERP` | COMMODITIES | Kaiko WTI Crude Oil Reference Rate | EZ6FWK6Z7Y08 |
| `EWY/USD-PERP` | ETF | Kaiko EWY Reference Rate | EZS52SFDSJY1 |
| `QQQ/USD-PERP` | ETF | Kaiko QQQ Benchmark Reference Rate | EZC4J383W3P1 |
| `EUR/USD-PERP` | FX | Kaiko Euro-US Dollar Rate | EZ24WJB12291 |
| `PAXG/USD-PERP` | CRYPTO | Kaiko PAXG Benchmark Reference Rate | EZXWD80F8CM9 |
| the other 12 | CRYPTO | one Kaiko rate each | one ISIN each |

### The venue's own words name the same four families

> "Available markets include: FX: EUR/USD. Equity indices: QQQ, EWY.
> Commodities: Gold, Silver, WTI, Brent. Crypto: BTC, ETH, SOL, XRP, DOGE, ADA,
> LINK, AVAX, SUI, HYPE, TAO, PAXG and ASTER"

`ETF` therefore names an **index**, not a company. And PAXG's perpetual sits in
the venue's own crypto list beside BTC, which is the same answer its
`asset_class` field gives.

### `/api/v2/currencies/` — 170 rows

```
type    crypto 166    fiat 4
fiat    EUR "Euro"   GBP "British Pound"   SGD "Singapore dollar"   USD "U.S. dollar"
```

This field names the **leg**, not the family. A record on it would read every
bitcoin pair quoted in euro as a currency pair, so the `name` field is what the
citation tables use instead.

## What a record costs — the reason bitstamp has none

A `VENUE_ASSET_SECTOR_RECORDS` row on `publicGetMarkets` names a sector for **7
of the venue's 123 base codes**. A record makes `published` non-None, which
switches off the `PRECIOUS_METAL_CODES` and `FIAT_CURRENCY_CODES` reading for
the whole venue, and bitstamp publishes no category on a single spot row.

Driven over all 271 markets through
`src/exchange/ccxt_connector.py, in market_asset_class`:

| gained — 6 markets | lost — 4 real markets |
| ------------------ | --------------------- |
| `BRENT/USD:USD` futures_perps to commodities | `GBP/USD` forex to **crypto** |
| `GOLD/USD:USD` futures_perps to commodities | `SGD/USD` forex to **crypto** |
| `SILVER/USD:USD` futures_perps to commodities | `PAXG/USD` commodities to **crypto** |
| `WTI/USD:USD` futures_perps to commodities | `PAXG/EUR` commodities to **crypto** |
| `EWY/USD:USD` futures_perps to indices | |
| `QQQ/USD:USD` futures_perps to indices | |

Eleven token pairs also fall from forex to crypto under a record, some rightly
and some not, which the market-grain citation separates by hand instead.

**Verdict: no record.** `CITED_VENUE_BASE_SECTORS` and
`CITED_VENUE_MARKET_SECTORS` take the six gains and cost nothing.

## The ticker collision, settled from bitstamp's own currency list

Every base code bitstamp's markets name, with the venue's own `name` and `type`:

```
MNT    "Mantle"                      crypto    <- NOT the Mongolian tugrik
XSGD   "StraitsX Singapore Dollar"   crypto
EURC   "EURC"                        crypto
EURCV  "EUR CoinVertible"            crypto
USDC   "USDC"                        crypto
USDT   "Tether"                      crypto
RLUSD  "Ripple USD"                  crypto
USDG   "Global Dollar"               crypto
PYUSD  "PayPal USD"                  crypto
PAXG   "PAX Gold"                    crypto
EUR    "Euro"                        fiat
GBP    "British Pound"               fiat
SGD    "Singapore dollar"            fiat
USD    "U.S. dollar"                 fiat
NOK, AMD, XAUT, USD1   absent from the list entirely
```

`MNT` is the fourth venue where this platform's forex reading had to be undone
by the venue's own label. Bitstamp's two MNT markets hold Mantle, not the
tugrik.

### What moved

| market | was | is | ground |
| ------ | --- | -- | ------ |
| `MNT/USD`, `MNT/EUR` | forex | crypto | `/currencies/` names MNT "Mantle" |
| `EURC/EUR` | forex | crypto | a euro token against the euro |
| `USDC/USD`, `USDT/USD` | forex | crypto | a dollar token against the dollar |
| `USDC/USDT` | forex | crypto | two dollar tokens, no currency |
| `EURCV/USDC`, `EURCV/USDT` | crypto | forex | "EUR CoinVertible" against a dollar token |
| `PAXG/USD:USD` | commodities | crypto | the venue files it under `CRYPTO` |
| BRENT, GOLD, SILVER, WTI perps | futures_perps | commodities | the venue's `COMMODITIES` |
| QQQ, EWY perps | futures_perps | indices | the venue's `ETF`, its words "Equity indices" |

Five markets take the market grain and not a base row, because their base codes
each sit on both sides of the line: `USDC` also bases `USDC/EUR`, `USDT` also
bases `USDT/EUR`, `EURC` also bases `EURC/USDC`, and `PAXG` also bases two spot
markets that redeem for gold.

### The recording, before and after

```
                 before   after    the arithmetic
crypto              235     240    +6 wrong forex +1 PAXG perp -2 EURCV
forex                15      11    -6 wrong readings +2 missed
commodities           3       6    -1 PAXG perp +4 venue words
futures_perps        18      12    -4 commodities -2 indices
indices               0       2    +2 venue words
                    ---     ---
                    271     271
```

## US eligibility — bitstamp is in neither set

### Spot: a United States account is served

> "Virtual currency services to US residents are provided by Bitstamp USA, Inc.,
> which is licensed to engage in virtual currency business activity by the New
> York State Department of Financial Services."

The venue's own market list confirms it per entity. `/api/v2/markets/` accepts
an `entity` parameter, and the parameter is two-sided:

```
entity=US_INC               200   251 rows   SPOT 251   PERPETUAL 0
entity=UK_LTD               200   251 rows   SPOT 251   PERPETUAL 0
entity=UK                   200   251 rows   SPOT 251   PERPETUAL 0
entity=EUROPE_SA            200   217 rows   SPOT 217   PERPETUAL 0
entity=SINGAPORE            400   "Value SINGAPORE cannot be deserialized to
                                   BitstampEntityEnum"
entity=NOT_AN_ENTITY_9F3A   400   same refusal
```

Twenty other names were probed and refused. Three plausible parameter names —
`broker=`, `broker_entity=` and `legal_entity=` — each answered the full 271
rows for every value including the invented one, so `entity` is the only live
filter and the others carry no information.

`EUROPE_SA` withholds 34 markets that `US_INC` serves, among them `PAXG/USD`,
`PAXG/EUR`, `XSGD/USD`, `RLUSD/USD` and `USDT/USD`. A United States account
reaches more of bitstamp's spot catalogue than a European one.

### Perpetuals: a United States account is refused

> "Derivatives trading is not available to customers in the US, Canada, Japan
> and some other countries."

> "Investment services with regards to trading in derivatives are provided by
> Bitstamp Financial Services Ltd., Dalmatinova ulica 2, 1000 Ljubljana,
> Slovenia (Reg. No: 9776745000) (BFS). BFS is authorized and supervised by the
> Slovenian Securities Market Agency (ATVP) as a MiFiD investment firm"

> "This addition provides eligible EU traders with a regulated environment to
> trade on crypto asset price movements"

> "Multi-Asset Perpetual Futures are offered through a MiFID II-authorised
> Multilateral Trading Facility (MTF)"

Both sentences appear on each of bitstamp's own two perpetual-futures posts.

**So bitstamp sits in neither `US_IP_BLOCKED_EXCHANGES` nor
`US_ACCOUNT_RESTRICTED_EXCHANGES`** — the shape gemini holds — because the
refusal falls on a product and not on the account. This is the first venue in
this issue where those two differ.

### U.S. states — not established, which is not absent

No page read names a state excluded from trading. What the pages do name:

> "Not available to residents of Alabama, Hawaii, Idaho, Louisiana, New Jersey,
> New York and Nevada."

That sentence is on bitstamp's own Earn pages and governs Earn, a staking
product this platform does not use. Its own New York post reads "Quick buy &
sell option has landed in New York!", so New York is served for trading. A
state excluded from spot **trading** is **not established**.

Detours searched and the reading that shut each: the terms-of-use pages for both
entities (Incapsula shell, 212 B); `assets.bitstamp.net` (403); a PDF path
(Incapsula shell); the Nuxt `_payload.json` route the blog host serves
(Incapsula shell on `www`); the API documentation (names no geography); the
`entity` filter (narrows the market list, names no state).

## The cash market buy — two routes, and the library sends the unit one

Bitstamp's own order pages give each route its own unit:

| route | the venue's own words |
| ----- | --------------------- |
| Market Buy Order | "Amount in base currency (Example: For BTC/USD pair, amount is quoted in BTC)" |
| Instant Buy Order | "Amount in counter currency (Example: For BTC/USD pair, amount is quoted in USD)" |

The market route's own subtypes are "MARKET" "STOP_LOSS" "TAKE_PROFIT"
"TRAILING_STOP_LOSS" "TRAILING_TAKE_PROFIT".

`ccxt.bitstamp.create_order` branches on the type:

```
type == 'market'    privatePostBuyMarketPair    amount = amount_to_precision(...)
type == 'instant'   privatePostBuyInstantPair   the cash route
otherwise           privatePostBuyPair          limit, price_to_precision
```

`CCXTConnector.place_order` composes no order of the `instant` type, so the cash
route is unreachable from this program and the size stays a unit count.

```
market_buy_names_cash("BTC/USD", "bitstamp")   False
market_buy_names_cash("PAXG/USD", "bitstamp")  False
market_buy_names_cash("EUR/USD", "bitstamp")   False
market_buy_names_cash("BTC/USD", "coinbase")   True     <- the control
```

**Bitstamp is not a member of `CITED_CASH_MARKET_BUY`.** It is the first venue
to publish the cash amount on a route of its own rather than a field of its own.

### `code_leg`

Bitstamp publishes `base_currency` on all 271 market rows and `currency` on all
170 currency rows, each a bare code with no separator. Its `market_symbol`
concatenates the legs — `eurusd`, `btcusd-perp` — so no leg reading reaches a
base code on this venue, and **no `code_leg` is named**.

## The eight connections

| # | connection | reading | control |
| - | ---------- | ------- | ------- |
| 1 | registered | `bitstamp` in `SUPPORTED_EXCHANGES`: True | an invented id: False |
| 2 | offered under every sector it serves | crypto, commodities, forex, indices, futures_perps | an invented id is offered under none |
| 3 | credential form | `exchange_status_rows` draws its venues from `venues_for_class`, so the Add form's set equals row 2's by construction | a sector with no venue draws `class_state`'s note |
| 4 | a Start press builds its connector | `MainWindow._connect_exchange_for_bot` reads `broker_connector_class` first and takes the crypto path for a `SUPPORTED_EXCHANGES` id | a broker id takes `_connect_broker_for_bot` |
| 5 | market rules record on connect | `record_venue` writes `CLASS_FIELD` per symbol; 271 markets carry a sector | an empty market list writes nothing |
| 6 | the order shape | `declared_order_types` reads "market and limit" off the venue's own capability map, where `createMarketOrder` is True | gemini reads limit-only off the same reader |
| 7 | a built variant selects | `variant_holds_market` True for 271 of 271; `venue_variant` "no order-formatting difference" for all | — |
| 8 | gate decisions log under it | `gate_log_path` composes `trade/gate/bitstamp/<sector>/gate.log` for each of the five | an unoffered sector composes a path as well, so the path is not the gate |

`order_types_for(None, sector, "bitstamp")` answered **None for all six
sectors** before this unit — the same gap gemini's unit found. It now answers
"market and limit" for the five sectors bitstamp records a market in, and None
for stocks, which is right.

## Verdicts

| sector | verdict | cost or ground |
| ------ | ------- | -------------- |
| crypto | **yes** | 240 markets, 222 fractional and 18 whole |
| commodities | **yes** | 6 markets. `US_INC` serves both PAXG spot markets; `EUROPE_SA` does not |
| forex | **yes** | 11 markets, every one holding two currencies by the venue's own labels |
| indices | **yes, and not for a US account** | 2 markets. Offered, read, charted and sized. "Derivatives trading is not available to customers in the US" |
| futures_perps | **yes, and not for a US account** | 12 markets. Same refusal, same entity: Bitstamp Financial Services Ltd |
| stocks | **proven no** | the door does not exist |

### The stocks block, proven three ways

1. **The venue's own published answer.** Its launch page lists the equity
   products as "Equity indices: QQQ, EWY" and no company. Its `asset_class`
   vocabulary publishes no stock word on any of its 271 rows.
2. **The detours searched.** `/api/v2/markets/` with every accepted `entity`
   value (251, 251, 251, 217 rows, zero naming a company);
   `/api/v2/trading-pairs-info/` (251 rows, 9 fields, no company);
   `/api/v2/currencies/` (170 rows, `type` crypto or fiat only, no equity);
   three derivatives-contract paths (404 each); the API documentation's
   Derivatives tag (12 endpoints, no equity order route).
3. **The control.** The same search over the same rows finds `COMMODITIES` on 4
   and `ETF` on 2, so it could have found a stock word had one existed.

## The arithmetic, per sector

```
sector          offered  venue lists  actionable  offered - actionable
crypto              yes          240         240                    0
commodities         yes            6           6                    0
forex               yes           11          11                    0
indices             yes            2           2                    0
futures_perps       yes           12          12                    0
stocks               no            0           0                    0
```

Before this unit, indices and futures_perps were offered under nothing while the
venue listed 22 markets between them.

## The regression drive

The sector and market-filter paths are shared, so nine venues were driven before
and after: coinbase, kraken, gateio, bitget, okx, okxus, bitfinex, gemini and
kucoin.

```
coinbase 1156 {crypto 904, forex 20, commodities 25, futures_perps 168, stocks 33, indices 6}
kraken   1460 {crypto 1416, forex 38, commodities 6}
gateio   6679 {crypto 2188, commodities 8, forex 21, futures_perps 1044, options 3418}
bitget   4265 {crypto 3375, forex 16, commodities 8, futures_perps 866}
okx      4571 {crypto 1133, forex 27, commodities 14, futures_perps 751, options 2646}
okxus    1152 {crypto 1125, forex 23, commodities 4}
bitfinex  288 {crypto 189, forex 4, commodities 9, futures_perps 76, indices 10}
gemini    345 {crypto 324, forex 2, commodities 6, futures_perps 13}
kucoin   1659 {crypto 956, forex 14, commodities 8, futures_perps 681}
```

**Not one count moved.** The citation tables key on the venue id, so a
bitstamp-only key cannot reach another venue, and the drive confirms it. A
tampered copy of the same reading is the control: the comparison reports it as a
difference.

## The Market Inspector universe

Bitstamp's own currency list names eight codes `STABLECOIN_DENYLIST` did not
hold, each one a currency or the token of one, and each basing a market the scan
would otherwise pick as a crypto to scrum: `SGD` "Singapore dollar" (type
`fiat`), `XSGD` "StraitsX Singapore Dollar", `EURCV` "EUR CoinVertible", `RLUSD`
"Ripple USD", `USDG` "Global Dollar", `VEUR` "VNX Euro", `VCHF` "VNX Swiss
Franc" and `UST` "TerraUSD".

Measured over the dollar-quoted spot markets of ten venues:

```
venue       universe before   after   removed
bitstamp                120     112         8
kraken                  756     750         6
gemini                  229     226         3
gateio                 2118    2116         2
bitget                 3345    3343         2
okx                     713     711         2
okxus                   705     703         2
coinbase                831     830         1
kucoin                  862     861         1
bitfinex                142     142         0
```

Every removed market is a currency or currency-token base. `GYEN` and `ZUSD`
stay out of the list, because bitstamp names each only by its own ticker and no
reading grounds what either stands for.

## Timeframes

`src/exchange/timeframes.py` needed no change to its row. Read from ccxt 4.5.85
`exchange.timeframes` after a public `load_markets()`, bitstamp publishes twelve
granularities and `ALL_TIMEFRAMES` draws eleven of them, which is exactly the
row. The one it leaves is `3m`, and `_AVAILABILITY["bitstamp"]` equals the
intersection of `ALL_TIMEFRAMES` and the published set exactly. Only the row's
comment changed, because the row carried no reading at all.

## The manual edit is add-only

Measured by sentence census against `git show origin/current:` the same path,
decoded as UTF-8:

```
ADD-ONLY CHECK       base 2383 sentences, new 2445, missing 0
TAMPER CONTROL       base 2383 sentences, new 2445, missing 1   <- fires
APPEND CONTROL       base 2383 sentences, new 2446, missing 0
```

The tamper control rewords a word **inside** an existing sentence, so it can
fail. The append control shows that adding text after a full stop alone would
not have exercised the check, which is why it is not the control.

## What the reading cannot show

No reading used a credential, so nothing here proves bitstamp accepts a live
order from this program. The order bodies are what the library composes, not
what the venue acknowledged. The `instant` route was read from its own
documentation and from the library's branch, never called. The perpetual
markets' refusal of a United States account was read from bitstamp's own pages
and not tested, which would require an account the operator does not hold.
