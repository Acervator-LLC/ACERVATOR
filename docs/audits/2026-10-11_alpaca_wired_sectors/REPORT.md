# Alpaca — every sector it serves, and the three it does not

Read 2026-10-11. No credential was sent. No order was placed, previewed, priced,
amended or cancelled. Every drive ran with `HOME` and `USERPROFILE` redirected to
a scratch tree, so no operator file was read or written.

Alpaca is the first broker this issue wires. `ccxt.alpaca.fetch_markets` calls
`traderPrivateGetV2Assets`, a private route, so the library cannot list this
venue and `src/stocks/alpaca_connector.py, in AlpacaConnector` is the path.

- [The reading routes, and the control on each](#the-reading-routes-and-the-control-on-each)
- [The eight connections](#the-eight-connections)
- [The six points, per sector](#the-six-points-per-sector)
- [The sector record: what it gained and cost](#the-sector-record-what-it-gained-and-cost)
- [The order shape and the cash amount](#the-order-shape-and-the-cash-amount)
- [The time in force Alpaca refuses](#the-time-in-force-alpaca-refuses)
- [The broker fill ledger](#the-broker-fill-ledger)
- [US-person eligibility](#us-person-eligibility)
- [The blocks, proven and unproven](#the-blocks-proven-and-unproven)
- [The arithmetic](#the-arithmetic)
- [Calibration and regression](#calibration-and-regression)
- [What this reading cannot show](#what-this-reading-cannot-show)

## The reading routes, and the control on each

| route | a real page | an invented path |
| ----- | ----------- | ---------------- |
| `docs.alpaca.markets/us/reference/...` and `/docs/...` | 200, 487,170 to 824,486 bytes | **404**, 340,348 bytes |
| the same page with `.md` appended | 200, 1,049 to 65,454 bytes over 18 pages | **404**, 290 bytes |
| `alpaca.markets/support/<slug>` | 200, 311,376 to 323,593 bytes | **404** |
| `alpaca.markets/<path>` | 200 | **200**, 81,029 bytes, title "Alpaca - 404 not found" |
| `api.alpaca.markets/v2/assets` | — | **401**, `{"message": "unauthorized."}` |
| `data.alpaca.markets/v1beta3/crypto/us/...` | 200 with a price | 200 with `{"bars":{}}` |

The fourth row is why nothing in this report is quoted from the marketing root on
status alone: that host answers 200 for a path that cannot exist. Every quotation
below comes from the documented API host, from a support article whose own slug
answers 200 under the support namespace, or from a PDF on
`files.alpaca.markets`.

The sixth row is the second trap. `AAPLx/USD` and the invented `ZZZZ/USD` both
answer `{"bars":{}}` at 11 bytes, while `PAXG/USD` answers 121 bytes carrying a
close of 4185.0. An empty bar map is not a reading; a priced one is.

`docs.alpaca.markets` publishes an index for a reader, which is how the whole
OpenAPI spec was read without a credential. Its own page says so: "For AI
agents: visit https://docs.alpaca.markets/us/llms.txt for an index of all pages
formatted in Markdown and endpoints in OpenAPI. Append .md to any documentation
page URL to get its markdown version."

```
pages the whole-site index names          696
projects it covers                          4   us, in-giftcity, eu, reference
pages the US project names                383
reference endpoints the US project names  259
```

## The eight connections

| # | the connection | answered |
| - | -------------- | -------- |
| 1 | a connector exists and is registered | yes. `src/stocks/alpaca_connector.py, in BROKER_CONNECTORS` holds `alpaca` against `AlpacaConnector`; `broker_connector_class("alpaca")` answers the class and an invented venue id answers None. `'alpaca' in SUPPORTED_EXCHANGES` is False, which is right: a broker is not a library venue |
| 2 | the venue is offered under every sector it serves | yes, four. `src/gui/main_tabs/asset_class_surface.py, in venues_for_class` answers alpaca under crypto, stocks, commodities and indices, and not under forex or futures_perps. The venue's own data agrees, which is the first time in six venues the offered set was already right |
| 3 | the operator can enter its credentials | yes, in all four. `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` iterates `venues_for_class` itself, so the Add form cannot differ. Driven over all six sectors: the difference is 0 in each |
| 4 | a Start press builds its connector | yes. `src/gui/main_window.py, in _connect_exchange_for_bot` reads `broker_serves_sector` first, so alpaca takes `_connect_broker_for_bot`, which builds `AlpacaConnector` and wraps it in `src/stocks/broker_exchange.py, in BrokerExchange` |
| 5 | its market rules record on connect | yes, and **now with a sector**. `src/stocks/broker_base.py, in record_markets` called `record_venue` with no `classes`, so every broker row recorded under no sector. It now passes `asset_sectors`, and 74 of 74 published records carry one |
| 6 | its orders carry the shape the venue publishes | yes, after one repair. `qty` is the size field this tree composes and that is the right one; the time in force on a crypto market order was not, and three of Alpaca's own pages say so |
| 7 | a built variant selects for it | yes in all four. Crypto, Stock and Commodity Scrumming over a fractional rule, Index Scrumming over a whole one, and `VARIANT_WHOLE_UNIT` already holds a share the record marks `fractionable` False |
| 8 | its gate decisions log under it | yes. `src/core/log_paths.py, in gate_log_path` composes `trade/gate/alpaca/<sector>/gate.log` for each of the six sectors, driven with the home redirected; the coinbase path composes beside it unchanged |

## The six points, per sector

### crypto — 73 markets

| point | the answer |
| ----- | ---------- |
| market list | `GET /v2/assets?asset_class=crypto`, which answers 401 with no key. The venue publishes the same list as a table in its own support article "What cryptocurrencies does Alpaca currently support?", dated March 2026: 73 pairs over 36 bases against USD, USDC, USDT and BTC |
| order route | `POST /v2/orders` on `api.alpaca.markets` |
| order shape | `symbol`, `qty` or `notional`, `side`, `type`, `time_in_force`. Types market, limit and stop_limit. Times in force gtc and ioc |
| position and fill read | `GET /v2/positions` and `GET /v2/positions/{symbol}` for the holding; `GET /v2/account/activities/FILL` for the fills |
| candles | `GET /v1beta3/crypto/us/bars`, credential-free, which is how `PAXG/USD` was priced for this report |
| bot variant | Crypto Scrumming, fractional, continuous session |

### stocks — the venue's own equity universe

| point | the answer |
| ----- | ---------- |
| market list | `GET /v2/assets`, which defaults to `asset_class=us_equity` and answers 401 with no key. The count is the venue's own and this report does not invent it. Its own fractional page states "You can now buy as little as $1 worth of shares for over 2,000 US equities" |
| order route | the same `POST /v2/orders` |
| order shape | the same fields. Types market, limit, stop, stop_limit and trailing_stop. Times in force day, gtc, opg, cls, ioc and fok |
| position and fill read | the same two routes |
| candles | `GET /v2/stocks/{symbol}/bars`, which needs a key |
| bot variant | Stock Scrumming, fractional, US equity session. `VARIANT_WHOLE_UNIT` takes over on a share whose record reads `fractionable` False |

### commodities — 1 market

| point | the answer |
| ----- | ---------- |
| market list | the crypto list above. `PAXG/USD`, Pax Gold, is row 44 of the venue's own table and it priced at 4185.0 on the venue's own credential-free bar route at 07:58 UTC. None of Alpaca's ten class words names a commodity, so a fund share holding oil or metal publishes `us_equity` and records under stocks |
| order route | the same `POST /v2/orders` |
| order shape | the crypto shape, because the market is on the crypto route |
| position and fill read | the same two routes |
| candles | the credential-free crypto bar route |
| bot variant | Commodity Scrumming, fractional, continuous session |

### indices — 0 recorded, 4 underliers published

| point | the answer |
| ----- | ---------- |
| market list | `GET /v2/options/contracts`, which `AlpacaConnector.list_assets` does not read. Its own Index Options page, updated 2026-09-10, publishes seven roots over four underliers: SPX, SPXW, XSP, VIX, VIXW, DJX and DJXW, traded "by the index underlier (`SPX`, `XSP`, `VIX`, `DJX`)" |
| order route | the same `POST /v2/orders`. Quoted whole: "Index options use the same contracts, orders, positions, and activities surfaces you already use for equity options" |
| order shape | types Market, Limit and Stop; times in force Day and GTC. Quoted whole: "Not supported: IOC/FOK, trailing stop, notional, fractional contracts, extended hours, calendar/diagonal spreads" |
| position and fill read | the same two routes, plus the exercise and do-not-exercise routes |
| candles | `GET /v1beta1/options/bars`, which needs a key |
| bot variant | Index Scrumming, whole units, US equity session. **This is the block**: the contract list route is not the one the connector reads, so no index symbol records |

### forex — 0 markets

| point | the answer |
| ----- | ---------- |
| market list | none. No currency word among the ten `AssetClass` values |
| order route | **none** |
| order shape | not applicable |
| position and fill read | not applicable |
| candles | `GET /v1beta1/forex/rates/latest` and the historical twin, both Market Data readings under a tag whose own words are "Endpoints for forex currency rates" |
| bot variant | none selects, because no market records |

### futures_perps — 0 markets

| point | the answer |
| ----- | ---------- |
| market list | `crypto_perp` is one of the ten class words and no route lists one |
| order route | **not established** |
| order shape | not established |
| position and fill read | not established |
| candles | not established |
| bot variant | none selects |

## The sector record: what it gained and cost

Alpaca's own `AssetClass` enum, quoted whole from the spec its `/v2/assets`
reference page carries:

```
"enum":["us_equity","us_option","crypto","crypto_perp","treasury",
        "corporate","global_equity","us_index","us_equity_chain","ipo"]
```

Its own `Exchange` enum, quoted whole:

```
"Represents the current exchanges Alpaca supports. List is currently:
 - AMEX - ARCA - BATS - NYSE - NASDAQ - NYSEARCA - OTC - CRYPTO"
```

`src/stocks/alpaca_connector.py, in asset_sector` reads the market grain first,
the base grain second and the class word third, the precedence
`src/exchange/ccxt_connector.py, in market_asset_class` already takes. Driven
over all ten words and two controls:

```
us_equity        -> stocks          treasury         -> None
us_option        -> None            corporate        -> None
crypto           -> crypto          global_equity    -> stocks
crypto_perp      -> futures_perps   us_index         -> indices
us_equity_chain  -> None            ipo              -> stocks
<invented word>  -> None            <not a record>   -> None
```

Six of ten map. Over the 73 coin pairs the venue's own table marks:

```
before  0 of 74 records carry a sector
after  74 of 74 records carry a sector
        crypto 72, commodities 1, stocks 1
cost    0 markets leave a sector
gain    1 market in a sector that held none
```

The one move is `PAXG/USD`, and `src/trading/scrumming/sizing.py, in
CITED_VENUE_BASE_SECTORS` carries it as `("alpaca", "PAXG"): commodities`,
beside the cryptocom row for the same token. The base code is the right grain
because PAXG bases exactly one alpaca market; no row is needed in
`CITED_VENUE_MARKET_SECTORS`, and it gains **0**.

Two-sided control on the recording: a broker whose `asset_sector` names nothing
writes its row and records **0** of 1 carrying a class, so the field is this
reader's answer and not a default the store supplies.

**The ticker collision.** `NOK` is Nokia and the Norwegian krone, `AMD` is
Advanced Micro Devices and the Armenian dram, `COP` is ConocoPhillips and the
Colombian peso, and `SGD` is the Singapore dollar. On a broker the equity
reading wins, and Alpaca's own data gives it: each of the four is a listed US
equity whose class word is `us_equity` and whose exchange word is NYSE or
NASDAQ. None of the four bases one of the 73 crypto pairs, so no base-keyed row
is needed. `STABLECOIN_DENYLIST` in
`src/exchange/market_inspector_fetcher.py` holds 30 codes and is read by
`_pick_universe` and by `_quote_volumes` over a venue's own **tickers**; a
broker publishes none through that path, so not one of the 30 touches an alpaca
symbol. The currency reading cannot win here because it is never consulted.

## The order shape and the cash amount

Quoted whole from Alpaca's own order spec:

> `notional` — "dollar amount to trade. Cannot work with `qty`. Can only work
> for market order types and day for time in force."
>
> `qty` — "number of shares to trade. Can be fractionable for only market and
> day order types."

And from its own fractional page: "You can pass either a fractional amount
(qty), or a notional value (notional) in any POST/v2/orders request. Note that
entering a value for either parameters, will automatically nullify the other. If
both qty and notional are entered the request will be rejected with an error
status 400."

**This tree composes `qty`.** `src/stocks/alpaca_connector.py, in
AlpacaConnector.place_order` writes `{"qty": str(quantity)}` and no `notional`
field exists anywhere in `src/`. So the size is a unit count on both sides,
every built variant already sizes one, and alpaca needs **no** row in
`src/trading/scrumming/sizing.py, in CITED_CASH_MARKET_BUY`, which holds five
venues and still does. Driven: `market_buy_names_cash` answers False for `AAPL`
and for `BTC/USD` on alpaca, which is correct.

The properties this venue carries are `MECHANIC_PERMITTED_SHAPE` and
`MECHANIC_NONE`. `MECHANIC_LIMIT_ONLY` is wrong for it: market orders are
published in every sector it serves. `MECHANIC_EXPIRY` applies to no alpaca
market today, because `/v2/assets` publishes no date field — its `Assets` schema
names ten required fields and not one is a date — and the option contracts that
do expire are listed by a route the connector does not read.

**The whole-share minimum.** The record itself names it: `fractionable` False,
which `size_increment` reads as `WHOLE_SHARE_INCREMENT` of 1.0, which
`recorded_unit_rule` reads as `WHOLE_UNITS`, which `variant_holds_market` holds
as `VARIANT_WHOLE_UNIT` and `position_minimum_refusal` guards at two units.
Driven on the venue's own two published records:

```
fractionable False                   -> whole
BTC/USD min_trade_increment 0.0001   -> fractional
```

The cash floor is the venue's own, quoted whole from its support article dated
April 2026: "No, to ensure an equitable trading experience for traders across
the platform, we enforce a minimum 1 USD notional amount for Buy entry orders."

## The time in force Alpaca refuses

`src/stocks/broker_exchange.py, in BROKER_ORDER_TYPES` maps a market order onto
`TimeInForce.DAY`. Alpaca does not accept `day` on a crypto market, and three of
its own pages say so:

> its order spec — "The Time-In-Force values supported by Alpaca vary based on
> the order's security type. ... Crypto trading: gtc, ioc."
>
> its Crypto Spot Trading page — "Market, Limit and Stop Limit orders are
> supported while the supported `time_in_force` values are `gtc`, and `ioc`."
>
> its support article dated October 2025 — "Crypto trading is facilitated by the
> Alpaca Crypto Exchange. Market, Limit, and Stop Limit orders are supported
> while the supported time_in_force values are gtc and ioc."

So a market order into any of the 73 crypto markets carried a value the venue
publishes as unsupported. The limit rows were already right: a plain limit maps
onto `gtc` and `IOC_LIMIT` onto `ioc`, and crypto takes both.

`src/stocks/alpaca_connector.py, in published_time_in_force` answers the value
the venue takes. Driven on both symbol shapes with no request sent:

```
BTC/USD  day -> gtc     AAPL  day -> day
BTC/USD  gtc -> gtc     AAPL  gtc -> gtc
BTC/USD  ioc -> ioc     AAPL  ioc -> ioc
```

An equity order is untouched, which is the control: the substitution fires only
where the venue publishes a refusal. `crypto_symbol` is the test, and it reads
True for `BTC/USD` and False for `AAPL`, off the venue's own symbology:
"symbology for trading pairs has changed from our previous format, where
`BTC/USD` was previously referred to as `BTCUSD`."

## The broker fill ledger

OVERTAKEN, quoted whole from the manual page:

> **No fill ledger.** Neither broker publishes a filled-trade history.

True today: that is Robinhood's absence and not Alpaca's.

`GET /v2/account/activities/{activity_type}` is the route, and `FILL` is the
first of the 42 words its own `ActivityType` enum holds. The route's own query
parameters, from its own reference: `order_id`, `date`, `until` ("Get activities
created before this date"), `after` ("Get activities created after this date"),
`direction` (asc or desc, default desc), `page_size` (default 100, maximum 100,
minimum 1) and `page_token` ("Provide the ID of the last activity from the last
page").

The `TradingActivities` record against `src/exchange/base.py, in Trade`:

| `Trade` field | Alpaca's own field and words |
| ------------- | ---------------------------- |
| `id` | `id`, "An id for the activity. Always in \"::\" format" |
| `symbol` | `symbol`, "The symbol of the security being traded" |
| `side` | `side`, "buy or sell" |
| `amount` | `qty`, "The number of shares involved in the trade execution" |
| `price` | `price`, "The per-share price that the trade was executed at" |
| `timestamp` | `transaction_time`, "The time at which the execution occurred" |
| `fee` | **no field on a fill** |

Built: `src/stocks/broker_base.py, in BrokerBase.list_fills` is the route every
broker answers and `PUBLISHES_FILL_HISTORY` decides whether it is read;
`src/stocks/alpaca_connector.py, in AlpacaConnector.list_fills` composes the
query; `src/stocks/broker_exchange.py, in broker_trade` reads one record into a
`Trade`; and `src/stocks/broker_exchange.py, in BrokerExchange.get_my_trades`
now takes the `params` dict `src/exchange/fill_history.py, in FillHistory._page`
already passes.

Driven on the record Alpaca's own reference publishes as its example, with no
request sent:

```
id 20220202135509981::2d7be4ff-d1f3-43e9-856a-0f5cf5c5088e
symbol AAPL  side buy  amount 2.0  price 174.78  fee 0.0
timestamp 1643828109.981482
```

That moment is 2022-02-02T18:55:09.98Z, the record's own `transaction_time`.

The composed paths, with no request sent:

```
GET /v2/account/activities/FILL?page_size=100&after=2020-09-13T12:26:40Z&until=2023-11-14T22:13:20Z
GET /v2/account/activities/FILL?page_size=100
fill_page_size   500 -> 100    0 -> 1    None -> 100
activity_moment  1.6e12 -> '2020-09-13T12:26:40Z'    None -> ''
```

Five two-sided controls:

| control | reading |
| ------- | ------- |
| a blank record | amount 0.0, price 0.0, timestamp 0.0 |
| a record whose side reads `sell` | side sell |
| a broker publishing one fill | 1 trade, price 174.78 |
| the same call narrowed to another market | 0 trades |
| a broker declaring `PUBLISHES_FILL_HISTORY` False | raises "Nosector publishes no filled-trade history" |

So three of the four blank figures now have a reading — realised profit, cost
basis and the unrealised figure — and the fee total does not. That is Alpaca's
own absence, in its own words: the fee is posted as its own activity, `FEE` "Fee
denominated in USD" and `CFEE` "Crypto fee", and "Fees are currently calculated
and posted end of day. If you query on same day of trade you might not get
results." No fee reaches a fill, so `Trade.fee` is 0.0 however the ledger is
paged.

## US-person eligibility

Alpaca is the first venue in this issue whose own pages **require** a US person
rather than refusing one. Its own support article "Who can apply for an Alpaca
brokerage account?", quoted whole:

> "For U.S. Residents — If you are a U.S. resident, you will need to meet the
> following requirements to open an Alpaca account: Be at least 18 years old,
> Have a valid Social Security Number (not a Taxpayer Identification Number),
> Have a legal U.S. residential address within the 50 states or Puerto Rico: Be
> a U.S. citizen, U.S. permanent resident, or hold a valid U.S. visa. Acceptable
> visa types are E-1, E-2, E-3, F-1, H1-B, TN-1, J-1, L-1, B-1, B-2, O-1."

Three readings, and no state is excluded in any of them:

```
its Domestic (USA) Accounts page        54 state codes, 0 refusals
                                        50 states, DC, and AA, AE, AP
its Account Application, Margin Agreement and Customer Agreement
  version V26.2026.07, 33 pages, 103,748 characters
  "United States"   6 hits, each defining a US person or waiving a foreign venue
  a refusal of a US person              0
```

The agreement names its own jurisdiction instead: "the word 'federal' means the
United States of America", "governed by the laws of the State of New York", and
disputes "settled by arbitration in accordance with the rules of FINRA Dispute
Resolution, Inc."

Positive control on the same reading: the same PDF reader over the same agreement
finds "New York" twice and "resident" three times, so a clause of this shape is
findable where it exists. Negative control: the same page reader over Coinbase's
own United States user agreement pulls 363,665 characters with 37 mentions of
"United States" and no refusal.

`alpaca` is in neither `US_IP_BLOCKED_EXCHANGES` nor
`US_ACCOUNT_RESTRICTED_EXCHANGES`, and both already read False for it, so
nothing changed there.

**One condition is unread, and it is named.** Alpaca's own Crypto Spot Trading
page states "As of November 18, 2022, cryptocurrency trading is open to select
international jurisdictions and some U.S. jurisdictions" and links to a region
list at `alpaca.markets/support/what-regions-support-cryptocurrency-trading`,
which answers 404 — the venue's own link is broken. None of the 24 support
categories publishes that list. The state condition on the crypto sector is
**not established**, not absent.

## The blocks, proven and unproven

### forex — a proven no

The door does not exist, and three readings say so:

```
currency words among the ten AssetClass values            0
reference endpoints naming forex, of 259                  2, both rate readings
documentation pages naming forex, of 696                  2, the same two
```

The detours searched, and the reading that shut each one:

| detour | reading |
| ------ | ------- |
| another endpoint | the 259-endpoint census finds no currency order route |
| another API version | `v1beta1/forex/rates/latest` is Market Data, and the same prefix answers 401 for an invented family, so its status names no path |
| another documentation host | the whole-site index covers us, in-giftcity, eu and reference, 696 pages, and forex still reads 2 |
| a page's script rather than its markup | the OpenAPI spec is read out of the script block, which is where the enum was found |
| another product reaching the same market | Local Currency Trading, quoted whole: "Local Currency Trading allows customers to trade US equities in over 15+ local currencies, with FX conversion done on-the-fly" — an equity order, not a currency market. A currency fund share publishes `us_equity` |
| a capability already in this tree | `CITED_VENUE_BASE_SECTORS` could name a currency fund share, but `/v2/assets` answers 401 so no such symbol can be confirmed listed |
| a different account type | LCT is that account type and it trades equities |

**Control proving the census could have found a door that exists:** the same
reading over the same index finds **8** order routes, among them "Create an
Order" at `POST /v2/orders` and the crypto order route the Crypto Spot Trading
page names.

### futures_perps — not established

`crypto_perp` is one of the ten class words. Against it:

```
documentation pages naming a perpetual, of 696            0
reference endpoints naming a perpetual, of 259            0
credential-free routes pricing one                        0
```

Two readings looked like evidence and were the reading method instead.
`data.alpaca.markets/v1beta1/crypto-perps/us/latest/bars` answers 401 at 172
bytes, and `v1beta1/invented-family-no-such-thing/us/latest/bars` answers the
same 401 at the same 172 bytes, so that status is the host's auth gate and names
no path. And the crypto bar route's own symbol pattern `^[A-Z]+x?/[A-Z]+$`
admits a lowercase `x`, the tokenised-equity convention, but `AAPLx/USD` and the
invented `ZZZZ/USD` both answer `{"bars":{}}` at 11 bytes while `PAXG/USD`
answers 121 bytes with a price.

An enum value with no product page, no endpoint and no priced market is not a
listed market, and it is not a refusal either. The sector is **not established**.
It is not added to `EXTRA_VENUE_CLASSES`.

### indices — a yes-if, with its cost named

An index reaches an order as an index option. The contract list is
`GET /v2/options/contracts` and `AlpacaConnector.list_assets` reads
`GET /v2/assets`, so no index symbol records today. What must be built is that
second list reaching the connector. What the operator must do is the venue's own
sentence: "Contact your Customer Success Manager for pricing and the steps to
enable index options. Enablement is at the correspondent and the end account.
Options trading must already be approved on the account."

The index-fund share is reachable now and records under stocks, which is where
Alpaca's own class word puts it — the reading bitget, OKX and KuCoin each took on
their own index-fund tokens.

## The arithmetic

```
sector          offered  Add form  alpaca markets  offered - form
crypto               22        22              73               0
stocks               21        21   the venue's own             0
commodities          20        20               1               0
forex                12        12               0               0
indices              19        19               0               0
futures_perps        17        17               0               0
```

The Add form cannot differ from the offered set:
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` iterates
`venues_for_class` itself. Driven over all six sectors, the difference is 0 in
each.

The cited rows, before and after:

```
sector         unit before  unit after   session before  session after  types before  types after
crypto         None         fractional   None            continuous     None          market and limit
stocks         fractional   fractional   us_equity       us_equity      None          market and limit
commodities    None         fractional   None            continuous     None          market and limit
indices        None         whole        None            us_equity      None          market and limit
forex          None         None         None            None           None          None
futures_perps  None         None         None            None           None          None
```

`broker_serves_sector`, before and after:

```
before  crypto True  stocks True  commodities True  forex True   indices True  futures_perps True
after   crypto True  stocks True  commodities True  forex False  indices True  futures_perps False
```

## Calibration and regression

Every archetype was calibrated before it was trusted, and each exit code was read
directly rather than through a command substitution:

```
coding_archetype  known_good exit 0   known_bad exit 1
docs_archetype    known_good exit 0   known_bad exit 1
gui_archetype     known_good exit 0   known_bad exit 1
ta_archetype      known_good exit 0   known_bad exit 1
```

Then each archetype ran on each changed file, serial, one file at a time. Fifteen
runs over the five Python files, every one exit 0.

The lint lanes, run with the gate's own argument lists because the RAM hook
refuses the whole gate while the operator's build is running:

```
black --check --diff src tests tools *.py    exit 0, 523 files unchanged
flake8 src tests tools *.py                  exit 0, 0 findings
```

Two-sided control on the flake8 lane, because the project's config hands E501 to
black: one undefined name added to a changed file reads
`F821 undefined name 'undefined_name_control'` and **exit 1**; removing it reads
0 findings and **exit 0**.

**The manual page is add-only.** A sentence census against
`git show origin/current:docs/manual/15-venue-compatibility.md`, decoded as
UTF-8:

```
the real edit      before 2623 sentences  after 2748  gained 125  LOST 0
tampered control   before 2623 sentences  after 2624  gained 1    LOST 1
```

The control reworded one word inside an existing sentence and added a new one,
and the census reported the loss, so the zero above is a reading and not a blind
spot. One existing passage is contradicted by Alpaca's own pages, and it is kept
verbatim in a blockquote under `OVERTAKEN, quoted whole:` with a `True today:`
line beneath it.

**The eleven recorded venues were driven before and after.** coinbase, kraken,
gateio, bitget, okx, okxus, bitfinex, gemini, kucoin, bitstamp and cryptocom,
over all six sectors — 66 venue-and-sector cells, 110 base-code readings, the
offered set, the Add form's set, `CITED_CASH_MARKET_BUY` and `VARIANTS_BUILT`.
Two runs each, minutes apart, from a second worktree checked out at
`origin/current`:

```
run 1   before 14,441 bytes   after 14,441 bytes   differing lines 0
run 2   before 14,441 bytes   after 14,441 bytes   differing lines 0
```

Tampered control: one extra `CITED_VENUE_ORDER_TYPES` row for an existing venue,
`(forex, coinbase)`, changes one reading from `null` to `"limit only"` and the
comparison reports it. Restoring the file reads 0 differing lines again. So the
zeros above are a reading.

## What this reading cannot show

No credential was used, so nothing here proves Alpaca accepts a live order from
this program; the order bodies are what this tree composes, not what Alpaca
acknowledged.

The equity market list was never read. `/v2/assets` answers 401 without a key
and no public route enumerates Alpaca's equities, so the stocks sector's count is
the venue's own and is left unnamed rather than invented. The 73 coin pairs come
from the venue's own support table dated March 2026, not from its order API, so
a pair listed since then is not here.

The state condition on crypto trading is unread, because the venue's own link to
its region list answers 404.

`MarketRules.contract_size` stays unrecorded for every alpaca market, because the
asset record publishes none, and issue row 10 is unchanged.
`CITED_VENUE_SETTLEMENT` gains no alpaca row: "settle" names no retail
trade-settlement rule in the 383 pages of the venue's own US documentation, and
the five hits in that index are JIT settlement, a correspondent-level process.
That is not established, so no row was cited.
