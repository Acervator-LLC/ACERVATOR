# Gemini Wired Across The Sectors It Serves

Every number here came from gemini's own credential-free public endpoints and
its own published pages, read on 2026-10-10 with the home directory redirected
to a temporary tree. No credential was used against the venue. No order was
placed or previewed. The order bodies were read with the transport replaced, so
no request left the machine.

The venue id is `gemini`. `src/gui/main_tabs/asset_class_surface.py, in
venues_for_class` offers it under four sectors: crypto, commodities, forex and
futures and perpetuals.

## The verdict, one row per sector

| Sector | Verdict | The cost | Markets |
| --- | --- | --- | --- |
| crypto | **yes** | nothing | 322 |
| commodities | **yes** | nothing | 8 |
| forex | **yes** | nothing | 4 |
| futures and perpetuals | **yes** | nothing | 13 |
| stocks | **no** | the venue sells stocks and publishes no order interface: "Stocks are currently available in the Gemini UI. API trading and developer documentation are coming soon." | 0 |
| indices | **no** | the venue publishes no index family, and a prediction contract pays $1.00 or $0.00 on an event | 0 |

Stocks and indices are not offered on the screen today, so neither is a sector
this unit had to open. Both counts are now grounded in the venue's own pages
rather than in an absence of evidence.

## The instrument came first

`ccxt.async_support` resolves a hostname through `aiodns`, which cannot reach a
DNS server in this shell. Eight venues read `ExchangeNotAvailable` while `curl`
answered HTTP 200 for the same URL.

```
aiodns.error.DNSError: (11, 'Could not contact DNS servers')
  aiohttp/resolver.py, in AsyncResolver.resolve
```

The zero was the instrument, not the venue. With aiohttp's threaded resolver
installed before any session opened, all eight answered. Every count below was
taken after that, and the synchronous path the product itself uses,
`CCXTConnector.sync_connect` over `requests`, was never affected.

## The eight connections

| # | The connection | Before | After |
| --- | --- | --- | --- |
| 1 | a connector exists and is registered | answered, `SUPPORTED_EXCHANGES` and `PREFLIGHT_URLS` | unchanged |
| 2 | offered under every sector it serves | four sectors | four sectors, each now grounded |
| 3 | the operator can enter its credentials | answered, key and secret, no passphrase | unchanged, and the key must be an account key |
| 4 | a Start press builds its connector | answered, the ccxt path | unchanged |
| 5 | its market rules record on connect | **0 rows of 345** | 347 rows of 347 |
| 6 | its orders carry the shape the venue publishes | unreached | `amount` a base unit count, `type` `exchange limit` |
| 7 | a built variant selects for it | unreached | four variants, all built, 0 refused |
| 8 | its gate decisions log under it | unreached, 0 files | four distinct paths, one line each |

Rows 6, 7 and 8 read unreached for one reason, and it was row 5.

## Row five, the comparison that skipped every market

`src/exchange/ccxt_connector.py, in get_markets` skipped a market whose own
record answered anything falsy under `active`. The default `True` in that read
fires only when the key is absent. ccxt sets the key for gemini and sets it to
`None`, and `not None` is True.

```
ccxt market['active'], per venue, 2026-10-10
coinbase   1156 markets   present True, value True 1148; value False 8
kraken     1460 markets   present True, value True 1365; value False 95
gateio     6679 markets   present True, value True 6677; value False 2
bitget     4265 markets   present True, value True 4258; value False 7
okx        4569 markets   present True, value True 4561; value False 8
okxus      1152 markets   present True, value True 1152
bitfinex    288 markets   present True, value True 288
gemini      345 markets   present True, value None 345
```

`src/exchange/ccxt_connector.py, in is_listed_market` is the one reader now. It
refuses a market only where the venue's own field reads `False`.

```
the predicate, one record of each shape
  no key               True
  active True          True
  active None          True
  active False         False
  active 0             True
  active empty string  True
  record None          True
```

Six readers shared the old comparison and all six read the predicate now.

```
src/exchange/ccxt_connector.py, in get_markets
src/exchange/ccxt_connector.py, in asset_info
src/exchange/ccxt_connector.py, in _sector_products
src/exchange/market_inspector_fetcher.py, in trading_products
src/gui/bot_wizard.py, in _fetch_markets                 (both market scans)
src/gui/preflight_check.py, in check
src/gui/main_tabs/preflight_check_surface.py, in run
```

The two pre-flight readers also told a published `False` from a published
nothing for the first time. `active_reported` read the key's presence, which is
True for gemini, so a gemini market would have been reported "Market active: No"
on the screen. It now reads the field's value, so the same market reports "not
reported".

`src/gui/main_tabs/preflight_check_surface.py, at MARKET_ACTIVE_DEFAULT` was the
default `is_listed_market` now carries, and it was removed as the thing replaced.

## The filter is venue-generic, so every recorded venue was driven

`CCXTConnector.sync_connect("", "")`, then `get_markets()`, then
`recorded_classes()`, before and after, home redirected.

```
            markets  recorded   sector counts
            before/after        before against after
coinbase    2148 / 2148         identical: commodities 25, crypto 896, forex 20,
                                futures_perps 168, indices 6, stocks 1033
kraken      1365 / 1365         identical: commodities 6, crypto 1321, forex 38
gateio      6677 / 6677         identical: commodities 20, crypto 2031, forex 6,
                                futures_perps 619, indices 18, options 3418,
                                stocks 565
bitget      4258 / 4258         identical: commodities 12, crypto 571,
                                futures_perps 534, stocks 3141
okx         4561 / 4561         identical: commodities 21, crypto 1013,
                                futures_perps 483, options 2644, stocks 400
okxus       1152 / 1152         identical: commodities 4, crypto 1013, stocks 135
bitfinex     288 / 288          identical: commodities 9, crypto 189, forex 4,
                                futures_perps 76, indices 10
gemini         0 / 347          from none to commodities 8, crypto 322, forex 4,
                                futures_perps 13
```

Kraken is the control that matters: its 1460 markets hold 95 whose own record
reads `False`, and the predicate still refuses all 95. Coinbase holds 8 and
still refuses all 8. Not one row moved anywhere but gemini.

The Market Inspector moved with it.

```
                     bases before   trading before   bases after   trading after
gemini                        158                0            82             82
kraken                        677              633           677            633
coinbase                      411              407           411            407
```

All 158 gemini bases read not trading before, because
`src/exchange/market_inspector_fetcher.py, in _product_trades` received the
`None` and answered `bool(None)`. 77 of those 158 were codes gemini publishes on
no row, which the next section explains, and `2ZRL` is gone from the answer
while `2Z` is in it.

## The cause one level deeper, and the two readings it cost

ccxt's `gemini.parse_market` never asks gemini for its own symbol details.
`options['fetchMarketsFromAPI']['fetchDetailsForAllSymbols']` is False by
default, so the parser takes the market id string from `GET /v1/symbols` and a
library-held trading-pair table. That branch never sets a status, which is where
`active` comes from, and it splits the id against a hardcoded quote list.

Gemini publishes `RLUSD` as the quote currency on 77 of the 348 rows its own
`GET /v1/symbols/details/all` serves, and ccxt's list omits it.

```
ccxt's own quoteCurrencies
  USDT GUSD USD DAI EUR GBP SGD BTC ETH LTC BCH SOL USDC

the venue's own quote currencies, off its own 348 rows
  BTC ETH EUR FIL GBP GUSD RLUSD SGD SOL USD USDC USDT
```

`2ZRLUSD` ends in `USD`, so the parser read the base as `2ZRL`. The market id
stayed `2zrlusd`, so an order still routed, and the legs on the screen were a
code the venue publishes nowhere. Two commodity rows were lost with it:
`PAXGRLUSD` read base `PAXGRL`, which no metal table answers. ccxt's own
`brokenPairs` list also dropped `eurusd` and `eurusdc`, and gemini serves both
today.

```
GET /v1/symbols/details/eurusd
  {"symbol":"EURUSD","quote_currency":"USD","tick_size":0.000001,
   "quote_increment":0.00001,"min_order_size":"0.1","status":"open",
   "product_type":"spot","contract_type":"vanilla","base_currency":"EUR"}
```

This issue's own row 11 cites "Gemini's euro-dollar market steps at a tenth",
and `min_order_size` is 0.1.

`src/exchange/ccxt_connector.py, at GEMINI_QUOTE_CURRENCIES` is ccxt's own list
with `RLUSD` ahead of `USD`, so the longer quote matches first.
`src/exchange/ccxt_connector.py, at GEMINI_BROKEN_PAIRS` is ccxt's own list
without those two euro pairs. The entries kept are the ones a renamed currency
code would duplicate a symbol for: `MATIC` resolves to `POL` and `EFIL` to
`FIL`, so `maticusd` would collide with `polusd`. `maticusd` is also gone from
the venue, which answered `"reason":"InvalidSymbol"` for it.

Both reach the venue through
`src/exchange/ccxt_connector.py, at EXCHANGE_OPTIONS`, keyed by venue id, so no
other venue can read them.

```
                markets  commodities  crypto  forex  futures_perps  duplicate ids
ccxt's own list      345            6     320      6             13            none
the venue's own      347            8     318      8             13            none

gained 79 symbols, lost 77, net 2 markets
  79 gained: 77 moving onto the RLUSD quote, plus EUR/USD and EUR/USDC
  77 lost:   every fabricated base, 2ZRL/USD through ZECRL/USD
  0 symbols kept their name while their legs moved
  0 market ids changed
```

## Row three, the credential, and one detail the manual table lacked

Gemini takes a key and a secret and no passphrase. The key must be an account
key: a master key is refused inside the library before any request leaves.

```
ccxt.gemini({"apiKey": "k", "secret": "..."}).create_order(...)
  AuthenticationError: gemini sign() requires an account-key,
  master-keys are not-supported
```

## Row six, the order shape

Gemini publishes **no market order at all**. Its own Create New Order page at
`https://docs.gemini.com/trading/rest-api/orders/create-new-order`:

> "What about market orders? The API doesn't directly support market orders
> because they provide you with no price protection."

> "Instead, use the 'immediate-or-cancel' order execution option, coupled with
> an aggressive limit price (i.e. very high for a buy order or very low for a
> sell order), to achieve the same result."

The program already composes exactly that. `OrderType.IOC_LIMIT` is sent as a
limit order with `timeInForce` IOC in
`src/exchange/ccxt_connector.py, in place_order`, and ccxt turns that into the
venue's own option array.

```
one endpoint for every sector: POST https://api.gemini.com/v1/order/new

BTC/USD        buy  limit  {"symbol":"btcusd","amount":"0.001","price":"50000","side":"buy","type":"exchange limit"}
BTC/USD        sell limit  {"symbol":"btcusd","amount":"0.001","price":"200000","side":"sell","type":"exchange limit"}
BTC/USD        buy  IOC    {"symbol":"btcusd","amount":"0.001","price":"999999","side":"buy","type":"exchange limit","options":["immediate-or-cancel"]}
PAXG/USD       buy  limit  {"symbol":"paxgusd","amount":"0.0001","price":"9000","side":"buy","type":"exchange limit"}
AUD/USD        buy  limit  {"symbol":"audusd","amount":"1","price":"1","side":"buy","type":"exchange limit"}
BTC/USDC:USDC  buy  limit  {"symbol":"btcusdcperp","amount":"0.0001","price":"200000","side":"buy","type":"exchange limit"}
BTC/USDC:USDC  sell limit  {"symbol":"btcusdcperp","amount":"0.0001","price":"10000","side":"sell","type":"exchange limit"}
BTC/USD        buy  market REFUSED  ExchangeError: gemini createOrder() allows limit orders only
```

`amount` carries a unit count in the base currency on both sides and in every
sector, the spot pair and the perpetual alike. `type` is always
`exchange limit`. `client_order_id` is the field ccxt sends, on every order.

`src/exchange/ccxt_connector.py, in declared_order_types` reads **limit only**
off the venue's own capability map, where `createMarketOrder` is False and
`createLimitOrder` is True.

### The cash market buy, reading 3

`src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` keeps its four
members and gemini is not one. The ground here is stronger than for any venue
before it: the page publishes no quote-currency size field because it publishes
no market order.

```
gemini    market buy   refused by the library and by the venue's own page
gemini    limit buy    amount  0.001     the base currency
gemini    limit sell   amount  0.001     the base currency
bitget    market buy   size    50        the cash
createMarketBuyOrderWithCost   None on gemini's own capability map
```

### The bot's shape fits this venue

`src/trading/bot_container.py, in guarded_place_order` reads
`src/trading/scrumming/sizing.py, in market_replaces_market_order` on every
order and replaces a market order with a limit order priced on the market's own
tick.

```
the mechanic venue_variant answers, over 347 gemini markets
at the venue's own last price   the venue declares no market order        347
at $100 a unit                  the venue declares no market order        249
                                smallest order costs more than the excess  98

market_replaces_market_order, at the venue's own last price
  gemini     347 markets   True 347
  coinbase  2148 markets   False 2148
```

The second row is the control. A price the market does not have moves 98 markets
onto an earlier mechanic, which is why the reading is taken at the venue's own
price from `GET /v1/pricefeed`, where 346 of 347 markets are priced.

### The order-type table carries every sector the venue serves

`src/trading/scrumming/sizing.py, at CITED_VENUE_ORDER_TYPES` held one gemini
row, keyed to crypto. Gemini has one order endpoint and one capability map, so
the declaration belongs to the venue and not to one of its sectors. Three rows
were owed, and the gap showed where no record had been read yet.

```
order_types_for with no record read
sector           gemini before   gemini after   coinbase
crypto           limit only      limit only     market and limit
commodities      None            limit only     None
forex            None            limit only     None
futures_perps    None            limit only     None
stocks           None            None           None
indices          None            None           None
```

## US-person eligibility, reading 1

**Gemini is the first venue in this run whose own terms serve a United States
resident, and it excludes no state.** Its own User Agreement landing page at
`https://www.gemini.com/legal/user-agreement`:

> "Your use of the Gemini platform is governed by the user agreement that
> corresponds to your state of residence: Residents of ID, LA, NY, OH, TX are
> subject to the terms of the Gemini Trust Company, LLC User Agreement.
> Residents of AL, AK, AZ, AR, CA, CO, CT, DE, FL, GA, HI, IL, IN, IA, KS, KY,
> ME, MD, MA, MI, MN, MS, MO, MT, NE, NV, NH, NJ, NM, NC, ND, OK, OR, PA, PR,
> RI, SC, SD, TN, UT, VT, VA, WA, DC, WV, WI, WY are subject to the Gemini
> Moonbase, LLC User Agreement."

Five states in the first group and forty-five in the second: all fifty, plus the
District of Columbia and Puerto Rico. No state is excluded.

Both agreements were read whole, 185,392 and 206,930 characters. Neither refuses
a United States person. The only refusal names sanctioned countries:

> "you may not buy Digital Assets on the Gemini Platform or use any of our
> services that we provide if: (i) you are in, under the control of, or a
> national or resident of any country or region subject to sanctions or
> embargoes issued by OFAC, the U.S. Department of State, the United Nations,
> the UK's HM Treasury's financial sanctions regime, or any other applicable
> government authority"

`src/exchange/ccxt_connector.py, at US_ACCOUNT_RESTRICTED_EXCHANGES` does not
gain the id and `at US_IP_BLOCKED_EXCHANGES` does not either. Gemini stays in
neither set.

**Control.** The same word search over the same two documents found that refusal
clause, found "Prohibited" 0 times, and found "Any U.S. Person" in bitfinex's
own Prohibited Person List. The search could have found a refusal had one been
written.

## Sector truth comes from the venue, reading 2

**Gemini publishes no asset category, so no `AssetSectorRecord` was added.**
`src/exchange/ccxt_connector.py, at VENUE_ASSET_SECTOR_RECORDS` keeps its four
rows.

Its one bulk product endpoint, `GET /v1/symbols/details/all`, serves 348 rows
and eleven keys, every key on every row.

```
base_currency            348 of 348
contract_price_currency  348 of 348
contract_type            348 of 348
min_order_size           348 of 348
product_type             348 of 348
quote_currency           348 of 348
quote_increment          348 of 348
status                   348 of 348
symbol                   348 of 348
tick_size                348 of 348
wrap_enabled             348 of 348
```

Two of the eleven look like a category and neither is one.

```
product_type   spot 335, swap 13
contract_type  vanilla 335, linear 13
status         open 343, closed 3, limit_only 2
wrap_enabled   False 346, True 2
```

Both name the product form that
`src/exchange/ccxt_connector.py, in is_contract_market` already reads off the
ccxt record. There is no `category`, no `instCategory` and no `symbolType`.

A record would also cost the venue both of its non-crypto sectors.
`src/exchange/ccxt_connector.py, in market_asset_class` reads
`PRECIOUS_METAL_CODES` and `FIAT_CURRENCY_CODES` only while the published sector
is None, so handing it any mapping switches that reading off. That is the same
arithmetic the bitfinex report records.

**Control for the absence.**

```
GET /v1/instruments          404 EndpointNotFound
GET /v1/assets               404 EndpointNotFound
GET /v1/currencies           404 EndpointNotFound
GET /v1/categories           404 EndpointNotFound
GET /v1/products             404 EndpointNotFound
GET /v1/symbols/categories   404 EndpointNotFound
GET /v1/symbols/details      404 EndpointNotFound
GET /v1/symbols/details/all  200, 348 rows
GET /v1/symbols              200, 348 ids
GET /v1/pricefeed            200, prices
GET /v1/network/btc          200, {"token":"BTC","network":["bitcoin"]}
```

The probe could find a page that exists.

## `code_leg`, reading 4

`src/exchange/ccxt_connector.py, at AssetSectorRecord` carries `code_leg`
because OKX publishes no base code on a contract type. Gemini publishes
`base_currency`, `quote_currency` and `contract_price_currency` as their own
fields on 348 of 348 rows, the 13 perpetuals included.

```
GET /v1/symbols/details/btcgusdperp
  {"symbol":"BTCGUSDPERP","quote_currency":"GUSD","tick_size":0.0001,
   "quote_increment":0.5,"min_order_size":"0.0001","status":"open",
   "product_type":"swap","contract_type":"linear",
   "contract_price_currency":"GUSD","base_currency":"BTC"}
```

There is no code to split, and gemini takes no `AssetSectorRecord` at all, so
the field has nothing to read. **Not needed, and the same reading holds.**

## The ticker collision, and the venue's own refutation

Eight pairs read forex off gemini's own base and quote codes. Four are not
currency markets. `GET /v1/pricefeed` is gemini's own credential-free feed and
it settles each one.

| market | base | quote | the venue's own price | what it is | sector recorded |
| --- | --- | --- | --- | --- | --- |
| AUDUSD | AUD | USD | 0.70147668 | the Australian dollar | forex |
| AUDUSDC | AUD | USDC | not in the feed | the Australian dollar | forex |
| EURUSD | EUR | USD | 1.15087 | the euro | forex |
| EURUSDC | EUR | USDC | not in the feed | the euro | forex |
| USD1USD | USD1 | USD | 0.99935 | a dollar token at par | crypto |
| USDCUSD | USDC | USD | 0.99983 | a dollar token at par | crypto |
| USDTUSD | USDT | USD | 0.999 | a dollar token at par | crypto |
| USDTUSDC | USDT | USDC | not in the feed | a dollar token at par | crypto |

`USD1`, `USDC` and `USDT` all redeem onto `USD` in
`src/exchange/ccxt_connector.py, at TOKEN_UNDERLYING_CODES`, and all three are
quoted against the dollar, so no pair holds two currencies.
`src/trading/scrumming/sizing.py, at CITED_VENUE_BASE_SECTORS` gains three
gemini rows, beside the three bitfinex rows that undo the same collision.

`AUD` and `EUR` need no row: the venue prices both at the cross rate, which is
what `FIAT_CURRENCY_CODES` already answers. Pax Gold and Tether Gold need none
either, because `TOKEN_UNDERLYING_CODES` redeems both onto `XAU`, and the same
feed prices them at 4201.22 and 4175.2197 a unit.

**Control, through the production reader.**

```
market_asset_class(record, None, "gemini")   against   market_asset_class(record, None, "")
  USDT/USD   crypto        forex
  USDC/USD   crypto        forex
  USD1/USD   crypto        forex
  AUD/USD    forex         forex
  EUR/USD    forex         forex
  PAXG/USD   commodities   commodities

venue_base_sector
  ("gemini", "USDT")    crypto
  ("gemini", "USDC")    crypto
  ("gemini", "USD1")    crypto
  ("gemini", "AUD")     None
  ("gemini", "BTC")     None
  ("bitfinex", "USD1")  None
  ("", "USDT")          None
```

## The two sectors with no market, and the venue's own reason

Gemini's own developer navigation names four product families, Spot crypto,
Perpetuals, Stocks and Prediction Markets, and no index family.

### stocks

0 of the venue's own 348 published rows names a company share. Gemini sells
stocks and publishes no order interface for them. Its own Stocks page at
`https://docs.gemini.com/products/stocks`:

> "Stocks on Gemini — Trade stocks in the Gemini UI today. API trading and
> developer documentation are coming soon."

> "API availability: Stocks are currently available in the Gemini UI. API
> trading and developer documentation are coming soon."

Its own legal index carries a "Gemini Galactic Markets User Agreement", a
"Market Data Agreement" and a "Form CRS" under a "Gemini Stocks" group, so the
product is real and the door this program walks through is not built. The
detours searched, and the reading that shut each one:

```
/products/stocks.md                  the page itself, "coming soon"
/rest-api/rest-api.md                four trading groups, no stocks group
/trading/rest-api/orders.md          ten order endpoints, none naming an equity
/v1/symbols/details/all              348 rows, 0 naming a company share
the venue's own navigation           API Reference lists Orders, Market Data,
                                     Derivatives, Fund Management, Margin,
                                     Clearing, Instant Orders, Staking and
                                     Prediction markets, and no stocks
```

**Control:** the same navigation read names Prediction Markets, which does have
a published REST order interface, so the search could have found a published
order path.

### indices

0 of 348 rows names an index, and no index family is published. Prediction
Markets carries a taxonomy with Crypto, Sports, Commodities and Weather, and a
prediction contract pays $1.00 or $0.00 on an event:

> "A contract is one tradable proposition expressed in YES space. Each contract
> supports YES and NO outcomes. The winning outcome pays $1.00 and the losing
> outcome pays $0.00."

That is not a market in any sector `ASSET_CLASSES` draws. Prediction Markets is
a product shape this platform does not model, and this unit builds nothing for
it.

## Row seven, the variants

`src/trading/scrumming/sizing.py, in sector_variant` names a built variant for
every one of the 347 recorded markets, and `variant_built` refuses none.

```
Crypto Scrumming      322
Commodity Scrumming     8
Forex Scrumming         4
Futures Scrumming      13
unbuilt                 0
```

`src/trading/scrumming/sizing.py, in recorded_unit_rule` reads 345 of the 347 as
fractional and 2 as whole: `XRP/GUSD:GUSD` and `XRP/USDC:USDC`, whose published
amount step is 1.0. Gemini's precision mode is tick size, so the step the venue
publishes under `tick_size` reaches the rule directly.

`src/trading/scrumming/sizing.py, in order_types_for` reads **limit only** on
all 347.

## Row eight, the gate log

Four real decisions written through `LogManager.log_gate_decision`, home
redirected.

```
trade/gate/gemini/crypto/gate.log          1 line   BTC/USD
trade/gate/gemini/commodities/gate.log     1 line   PAXG/USD
trade/gate/gemini/forex/gate.log           1 line   EUR/USD
trade/gate/gemini/futures_perps/gate.log   1 line   BTC/USDC:USDC
```

`gate_writer_keys` opened four distinct pairs, every row names its own sector in
its own `asset_class` field, and `src/core/log_paths.py, in gate_log_files`
lists all four, so a reader follows the writer.

## What each sector records

| Sector | Markets | What they are |
| --- | --- | --- |
| crypto | 322 | spot pairs against USD, GUSD, RLUSD, USDC, USDT, EUR, GBP, SGD, BTC, ETH and SOL |
| commodities | 8 | Pax Gold on four quotes and Tether Gold on four quotes |
| forex | 4 | the Australian dollar and the euro, each against the dollar and against USDC |
| futures and perpetuals | 13 | linear perpetuals on AVAX, BTC, ETH, HYPE, SOL, TRUMP and XRP |

The read paths each sector needs are declared on the venue's own capability map.

```
fetchBalance        True
fetchMyTrades       True
fetchOpenOrders     True
fetchOHLCV          True
fetchTickers        True
fetchTicker         True
fetchOrder          True
cancelOrder         True
fetchCurrencies     True
createLimitOrder    True
createMarketOrder   False
fetchPositions      False
fetchClosedOrders   False
```

Two read False and both belong to one sector. A perpetual position is read
through the balance and the trade list, not through a position list, and a
closed order is read through `fetchOrder` by id.

## The timeframe row

`src/exchange/timeframes.py` offers gemini seven timeframes and the row is
exact: the recorded set equals ccxt's published set, nothing either way.

```
recorded   1m 5m 15m 30m 1h 6h 1d
published  1m 5m 15m 30m 1h 6h 1d
```

## Step five, the arithmetic

| Sector | Venues offered, before | After | Markets gemini can act on, before | After |
| --- | --- | --- | --- | --- |
| crypto | 22 | 22 | 0 | 322 |
| stocks | 21 | 21 | 0 | 0 |
| commodities | 18 | 18 | 0 | 8 |
| forex | 9 | 9 | 0 | 4 |
| indices | 15 | 15 | 0 | 0 |
| futures and perpetuals | 16 | 16 | 0 | 13 |

Every before-count of markets is zero for the one comparison this report opens
on. No offered count moved, because
`src/gui/main_tabs/asset_class_surface.py, at EXTRA_VENUE_CLASSES` already held
gemini's four sectors.

`src/gui/main_tabs/asset_class_surface.py, in known_venues` holds 26 ids and
`src/gui/main_tabs/init_wizard_surface.py, in exchange_ids` holds the same 26,
so the Exchanges tab and the first-run wizard offer the same set. The Add form's
set equals the screen's set in all six sectors, because both narrow that one
list. The subtraction is zero in every sector.

## Add-only on the manual page

```
committed sentences                                5098
working sentences                                  5464
committed sentences absent from the working page      0
control, the committed page against itself            0
control, one committed sentence reworded              1
control, two committed sentences reworded             2
```

Decoded as UTF-8 on both sides. Two sentences the venue's own pages contradict
are kept verbatim in a blockquote under `OVERTAKEN, quoted whole:` with a
`True today:` line beneath each: the venue-and-classes table row, and the
limit-only variant paragraph that counts two cited pairs.

## What this could not establish

No reading used a credential, so nothing here proves gemini accepts a live order
from this program. The order bodies are what the library composes, not what the
venue acknowledged.

Gemini's 85 markets quoted in its own GUSD and 77 quoted in RLUSD read crypto.
Whether a national currency against a dollar stablecoin is a forex market is
this issue's second open decision and belongs to the operator. `AUD/GUSD`,
`AUD/RLUSD`, `EUR/GUSD` and `EUR/RLUSD` are the markets that answer would move.

ccxt's own gemini parser still reads a library-held pair table rather than the
venue's own symbol details, because the branch that reads those details sets a
settle currency from `contract_price_currency`, which gemini publishes on all
348 rows, and would therefore read every spot pair as a swap. A published amount
step or minimum the library has not refreshed is a reading this program cannot
correct from here. The venue's own `status` field, which holds `closed` on 3 rows
and `limit_only` on 2, never reaches the ccxt record for the same reason.
