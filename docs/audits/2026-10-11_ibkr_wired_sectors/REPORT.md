# Interactive Brokers — the eight connections and the six sectors

Read 2026-10-11 from Interactive Brokers' own hosts. No credential sent. No
order placed, previewed, priced, amended or cancelled. No client or developer
account registered. Home redirected on every drive of this tree.

The venue id is `ibkr`. `src/stocks/ibkr_connector.py, in VENUE_ID` holds it and
`src/stocks/alpaca_connector.py, in BROKER_CONNECTORS` keys it.

## Contents

- [Part one — the readings taken before the build](#part-one--the-readings-taken-before-the-build)
- [Part two — what the build settled](#part-two--what-the-build-settled)
- [The detours searched](#the-detours-searched)
- [Defects found and fixed](#defects-found-and-fixed)

---

## Part one — the readings taken before the build

The third broker, and the one that offers more sectors than any other venue in
the tree. Read 2026-10-11 off Interactive Brokers' own hosts, its own OpenAPI
document, its own documentation markdown and its own FAQ service. No credential
sent. No order placed, previewed, priced, amended or cancelled. No client or
developer account registered. Home redirected on every drive.

**Schwab's order body was unreadable and ibkr's is published in full.** Where the
schwab unit could read a route and no field, this unit read a 939,918-byte
OpenAPI document on a credential-free route, version 2.41.0, naming 179 paths and
every field the order route takes. So `IbkrConnector.place_order` composes a body
and does not refuse.

#### Every host, and the control on each

| host | a real path | an invented path | does status name a path |
| --- | --- | --- | --- |
| `www.interactivebrokers.com` (product pages) | 200, 217,058–303,618 bytes | **404**, 17,287 bytes | yes |
| `www.interactivebrokers.com/campus/` | 200, 483,154 bytes | **404**, 860,258 bytes | yes |
| `www.interactivebrokers.com/docs/…/llms.txt` | 200, 10,850–13,263 bytes | — | yes |
| `www.interactivebrokers.com/docs/….md` | 200, 674 bytes | 200, **258 bytes, "Page Not Found"** | by **size**, not status |
| `api.ibkr.com/gw/api/v3/api-docs` | **200, 939,918 bytes** | — | the document itself |
| `api.ibkr.com/v1/api/` | 401, 49 bytes | 401, **49 bytes** | **no** |
| `www.interactivebrokers.com/tws.proxy/faq/content` | **405** on GET, answers on POST | **404**, 114 bytes | yes |
| `www.interactivebrokers.com/faq?id=` | 200, 5,809 bytes | 200, **5,809 bytes** | **no** |
| `www.ibkr.com` | **redirects to `www.interactivebrokers.com`**, 240,678 bytes | — | — |
| an invented host | — | **000, no DNS** | — |

Two rows carry no path information and both have a replacement. `api.ibkr.com/v1/api`
answers the same 401 at the same 49 bytes for a real route and an invented one, so
no route census is possible there — the OpenAPI document names the routes instead.
`/faq?id=` is one JavaScript shell for every id, byte-identical for a real id and
an invented one — its own bundle names the content route, `POST /tws.proxy/faq/content`,
and that route answers without a credential.

#### The one list every answer comes from

```
api.ibkr.com/gw/api/v3/api-docs     openapi 3.0.0, "IB REST API", version 2.41.0
                                    179 paths, 939,918 bytes, no credential
```

`ccxt` 4.5.85 carries no ibkr exchange: `'ibkr' in ccxt.exchanges` and
`'interactivebrokers' in ccxt.exchanges` both answer False, and the three names
holding "ib" are `coinbaseinternational`, `deribit` and `hibachi`. So this venue
needs a hand-written connector, as alpaca and schwab did.

#### The order route, and the order body, both published

**One order route serves every sector**:
`POST /v1/api/iserver/account/{accountId}/orders`, `operationId` `submitNewOrder`,
taking a JSON body whose `orders` array holds `singleOrderSubmissionRequest`
objects. Five fields are required and the document names them:

```
required   conid  orderType  quantity  side  tif
side       enum   BUY, SELL
tif        enum   DAY, IOC, GTC, OPG, PAX
quantity   number, "Quantity of the order ticket in units of the reading"
cashQty    number, "Quantity of currency used with cash quantity orders"
outsideRTH boolean, "Instructs IB to permit the order to execute outside of
                     regular trading hours"
secType    string, "IB asset class identifier"
cOID       string, the client order id, unique for 24 hours, 64 characters
```

**A field no venue in this issue has had before.** `manualIndicator`, quoted whole:
"For all orders for US Futures products, clients must submit this flag to indicate
whether the order was originated manually (by a natural person) or automatically
(by an automated trading system transmitting orders without human intervention).
Submit a True value to indicate a manually originated order, and submit a False
value to indicate an automated order. **Orders for USFUT products that do not
include this field will be rejected.**" This platform is an automated trading
system, so every US futures order carries `manualIndicator` False or the venue
refuses it. That is three of the six sectors.

#### The security type is the sector, and the venue publishes the vocabulary

`assetClass` sits on every contract record `/v1/api/trsrv/secdef`,
`/v1/api/portfolio/{accountId}/position/{conid}` and `/v1/api/iserver/account/trades`
serve. The order-status schema closes the vocabulary at nine words — `STK`, `OPT`,
`FUT`, `FOP`, `CASH`, `CRYPTO`, `BOND`, `WAR`, `FUND` — and the contract pages add
`CMDTY` and `IND`. Each of ibkr's own contract-definition pages names the word for
its product:

| ibkr's own page | its own sentence | sector |
| --- | --- | --- |
| Stocks | `secType` `STK` | stocks |
| Cryptocurrency | "Specify `CRYPTO`" on `PAXOS` or `ZEROHASH` | crypto |
| Commodities | "Specify CMDTY", `symbol = "XAUUSD"` on SMART | commodities |
| FX Pairs | "Specify CASH", `IDEALPRO` for "true forex trading" | forex |
| Index | "Specify IND" | indices |
| Futures | `FUT`, with eleven product families named | futures_perps |

#### crypto — 20 tokens, and the only market-buy rule in this issue that bans a unit count

- **who** — `src/stocks/ibkr_connector.py, in IbkrConnector.place_order` composes the body; `src/stocks/broker_exchange.py, in BrokerExchange.place_order` shapes it; `src/trading/bot_container.py, in guarded_place_order` sizes and submits
- **what** — 20 tokens, read whole from the venue's own FAQ table: AAVE, ADA, APT, AVAX, BCH, BTC, CC, DOGE, ETH, LDO, LTC, LINK, MON, NEAR, PAXG, SOL, SUI, UNI, XPL, XRP. Paxos carries 8 of them and zerohash all 20. "Currency: Only USD is available at this time"
- **where** — `POST /v1/api/iserver/account/{accountId}/orders`, the one order route
- **when** — `src/stocks/ibkr_connector.py, in IbkrConnector.list_assets` on every connect; `src/stocks/broker_base.py, in BrokerBase.record_markets` writes the rules and the sector
- **why** — `src/trading/scrumming/sizing.py, in order_types_for` answers None for this sector and for all six, so no cited row governs any ibkr order
- **how** — `src/trading/scrumming/sizing.py, in sector_variant` answers Crypto Scrumming. The minimum order size is **.00000001**, the venue's own figure, so `recorded_unit_rule` reads `FRACTIONAL_UNITS`

**ibkr's own Cryptocurrency Trading page publishes a rule no other venue in this
issue publishes.** Quoted whole: "Please be aware that no other order types are
available for Crypto orders." And per side:

```
BUY    LMT Order Using "quantity" or "totalQuantity" values.
       MKT Orders using "cashQty" value.
SELL   LMT Order Using "quantity" or "totalQuantity values.
       MKT orders using "quantity" or "totalQuantity" values.
TIF    LMT Orders support "DAY", "GTC", "IOC"
       MKT Orders only support "IOC".
```

A crypto market **buy** on ibkr takes a cash amount and nothing else. This
platform sizes a unit count, so the only crypto buy it can compose is a limit
order. `ORDER_TYPES_LIMIT_ONLY` is the true reading for this sector, and
`market_replaces_market_order` already converts a market order to a limit at the
record's own tick. A market **sell** does take a unit count, and a limit sell at
the tick is accepted on the venue's own sentence, so the narrower row costs the
sell nothing and the buy would otherwise be refused at the venue.

**`PAXG` needs a base-keyed row.** It is on ibkr's own crypto list and it redeems
for gold, which `PRECIOUS_METAL_CODES` and the alpaca and cryptocom rows already
answer commodities for. `CITED_VENUE_BASE_SECTORS` gains one ibkr row.

#### stocks — fractional on four named platforms, and whole units through the API

- **who** — the same three symbols
- **what** — "over 10,000 US-listed stocks and ETFs" in ibkr's own overnight session, across "170+ markets worldwide". The market list is `GET /v1/api/trsrv/all-conids?exchange=&assetClass=STK` per exchange and `GET /v1/api/trsrv/stocks?symbols=` per symbol
- **where** — the same one order route
- **when** — the same two moments
- **why** — `src/trading/scrumming/sizing.py, in CITED_UNIT_RULES` holds no ibkr row in any sector, and `CITED_VENUE_SESSIONS` holds none either, so this sector has no cited rule at all
- **how** — `src/trading/scrumming/sizing.py, in session_unit_rule` and `in session_order_types`, because this is a US equity session

**The reading that inverts both brokers before it.** Alpaca is fractional and
schwab is fractional, and ibkr's **API** is not. Quoted whole from ibkr's own
Notes & Limitations page for its order types: "Interacive Brokers APIs do not
support fractional or cash quantity trading with exception to Cryptocurrencies and
Forex trading." Its own minimum-order FAQ agrees: "Nearly every product offered by
IBKR has NO minimum order size. You can place trades with an order size as low as
**1 share, 1 contract, 1 unit of currency**."

**A contradiction inside ibkr's own pages, named.** Its Fractional Trading page
offers fractional shares — "Invest as little as USD 1" — and its Get Started
section lists the platforms that reach them: Trader Workstation, IBKR Mobile on
four devices, and Client Portal. **The API is not one of the six.** The OpenAPI
`quantity` field is `type: number`, which permits a decimal, so the schema allows
what the page refuses. The reading that satisfies both is that fractional shares
are a platform feature and not an API feature, which is what the page naming the
API says. `CITED_UNIT_RULES[(stocks, ibkr)]` is `WHOLE_UNITS`, and this is a
belief that would have cost a refused order if it had been carried the other way.

**The session rule the schwab unit found, found again, in ibkr's own words.** On
its own Trading Outside Regular Trading Hours page, Interactive Brokers answers a
client on 9 July 2025: "**It is not possible to submit market orders outside of
RTH, including a stop loss.**" And on 18 February 2025: "Only Day Limit orders are
allowed in the US overnight trading session." And on 4 February 2025, on whether a
product trades outside RTH: "It depends on the product you are trading. **Futures
are available outside RTH. US stocks are not.**" So `CITED_VENUE_SESSIONS` gains a
`SESSION_US_EQUITY` row for stocks alone, `session_order_types` narrows a 18:00 ET
order to a limit, and the five other sectors take no session row.

**A settlement figure, the first any venue has published in this issue besides
coinbase's zero.** Quoted whole from the same page: "all US equities settle on a
T+1 basis since May 2024". `CITED_VENUE_SETTLEMENT` gains `(stocks, ibkr) = 1.0`.

#### commodities — one spot product, and the only sector whose own page refuses four states

- **who** — the same three symbols
- **what** — **US Spot Gold, symbol `USGOLD`**, security type `CMDTY`, "quoted in US dollars per troy ounce", with "Efficient Pricing in Quantities as Small as 1 Ounce", beside COMEX metal futures under ibkr's own Metals and Agriculture and Energy and Softs futures families. "Spot Platinum (XPTUSD) is currently not available at IBKR", and London gold and silver derivatives are on the UK website, not this one
- **where** — the same one order route
- **when** — the same two moments
- **why** — `src/exchange/base.py, in MarketRules` carries `contract_size`, and ibkr publishes a `multiplier` on every contract record, so this venue fills that field for every futures market
- **how** — Whole Unit Scrumming. `src/trading/scrumming/sizing.py, in contracts_for_units` reads the contract size and `position_minimum_refusal` guards the two-unit floor

**A market-order rule the venue publishes by omission, and the control that reads
it.** ibkr's own Market Order page lists its products: "BOND, CFD, EFP, CASH, FUND,
FUT, FOP, OPT, STK, WAR". Its own Limit Order page lists: "BOND, CASH, CFD,
**CMDTY**, FUT, FOP, OPT, STK, WAR". `CMDTY` is on the limit list and **not** on
the market list, so a spot-gold market order is a type the venue does not name.
The control is the pair of lists themselves: the same reading reads `CASH`,
`FUT`, `STK` on both, so a security type missing from one list is a difference the
reading can see. `ORDER_TYPES_LIMIT_ONLY` is the true reading for a `CMDTY` market
and the per-market `MarketRules.order_types` field carries it, so the futures half
of this sector keeps its market order.

#### forex — 100+ pairs on 28 currencies, and the row-11 answer in the venue's own words

- **who** — the same three symbols
- **what** — "IBKR Offers 100+ Currency Pairs On **28 Currencies**", named whole on its own Spot Currencies page: USD, AED, AUD, BRL, CAD, CHF, CNH, CZK, DKK, EUR, GBP, HKD, HUF, ILS, JPY, KRW, MXN, MYR, NOK, NZD, PLN, RON, SAR, SEK, SGD, TRY, TWD, ZAR. The list route is `GET /v1/api/iserver/currency/pairs?currency=USD`, whose own example answers `USD.SGD`, `USD.RON` and `USD.CZK`
- **where** — the same one order route, with `isCcyConv` False so the position is a position and not a conversion
- **when** — the same two moments
- **why** — `src/gui/main_tabs/asset_class_surface.py, in venues_for_class` already offers ibkr under forex, and `src/trading/scrumming/sizing.py, in unit_rule` answers **None** for it
- **how** — Forex Scrumming, fractional, because ibkr's own API page excepts Forex from the no-fractional rule

**Issue row 11 is settled, and its reason is overtaken.** The row reads "only
Interactive Brokers documents a currency security type, and it sizes by the second
currency's notional, which is row 6's `VARIANT_CASH_AMOUNT` and not a lot." The
first clause is right and the second is the option, not the default. ibkr's own
minimum-order FAQ, quoted whole: "Forex order quantity is by default defined in
terms of units of the first currency of the pair. **The concept of Forex lots does
not apply at IBKR.**" Its own FX Pairs page says the same twice: "Symbol: Specify
the target currency. **For orders, this will dictate the quantity value.**" and
"Currency: Specify the base currency forex pair. This will dictate size **with cash
quantity trades**." So `quantity` is a unit count of the first currency and
`cashQty` is the alternative. The row's conclusion — no third member of
`UNIT_RULES` — holds, and its stated reason needs replacing.

**A minimum that is a price, not a refusal.** Quoted whole: "a minimum size of USD
25,000, or equivalent, is imposed on all IdealPro orders. Orders below this size
are considered odd lots and their limit prices are not disclosed through
IdealPro… **Odd lot marketable limit orders will still be accepted**, but they are
not guaranteed execution at the inter-bank spreads." So the 25,000 is a spread
penalty and not a floor, and `MarketRules.min_amount` carries no ibkr forex row.

**A second settlement figure.** Quoted whole: "Fast settlement, typically in T+2
(trade date plus two days)". `CITED_VENUE_SETTLEMENT` gains `(forex, ibkr) = 2.0`.

#### indices — the sector whose own security type takes no order

- **who** — the same three symbols
- **what** — ibkr's own futures page names two index families itself, **Equity Indices** and **Volatility Indices**, beside its E-mini and Micro E-mini family. The index itself is `secType` `IND`, and `IND` is **not** in the nine-word order-status vocabulary and **not** on either the market-order or the limit-order product list. `GET /v1/api/iserver/secdef/search` takes `secType` `STK`, `IND`, `BOND` as an **underlying** type, which is what an index is on this venue
- **where** — the same one order route, reached by the index **future** and not by the index
- **when** — the same two moments
- **why** — the sector is offered and `unit_rule("indices", "ibkr")` answers **None**
- **how** — Index Scrumming, whole contracts, with `expiry_close_decision` governing the date

**The detour searched and shut.** A CFD on an index would reach the sector without
an expiry. ibkr's own `products-cfds.php` answers **200 with the title "Home |
Interactive Brokers LLC"** and the word "CFD" appears **0** times in its body. The
control is the other six product pages fetched the same way, each of which answers
its own title: "Currency Trading", "US Spot Gold", "Futures Trading", "Stock
Trading", "Fractional Trading", "Trade Crypto for Less". So the US entity publishes
no CFD product page while publishing six others, and the index route for this
platform is the dated contract.

#### futures_perps — eleven families, and 0 perpetuals

- **who** — the same three symbols
- **what** — ibkr names its own futures families: **Agriculture, Cryptocurrency, Currencies, Energy, Equity Indices, E-mini and Micro E-mini Futures, Fixed Income, Interest Rates, Metals, Softs, Volatility Indices**, on "30+ market centers". The list route is `GET /v1/api/trsrv/futures?symbols=ES,MES`, which answers an `expirationDate` and an `ltd` per contract. **No perpetual.** The word "perpetual" names **0** of the 13 ibkr pages read; the controls on the same 13 pages are "futures" 265, "currency" 137, "gold" 72 and "index" 24
- **where** — the same one order route, with `manualIndicator` False on every US futures order
- **when** — the same two moments
- **why** — `src/trading/scrumming/sizing.py, in VARIANT_ROLLING_POSITION` is built and `expiry_close_decision` is the action, reading `MarketRules.expiry_ms` which this connector fills from the venue's own `expirationDate`
- **how** — Rolling Position Scrumming, which `VARIANTS_BUILT` holds

The family-to-sector map is schwab's shape on ibkr's own words: Agriculture,
Energy, Metals and Softs reach commodities; Equity Indices and Volatility Indices
reach indices; Cryptocurrency reaches crypto; Currencies reaches forex; Fixed
Income and Interest Rates reach no sector this platform draws; and E-mini and Micro
E-mini is a size family whose rows repeat a row in another family, exactly as
schwab's 24 Micros rows did.

#### The four blank figures — all four published, which is the first time

`BrokerExchange.get_my_trades` raised for every broker. Alpaca settled three of
four and named the fee total as its own absence. ibkr publishes all four.

| the figure | ibkr's own field | the route |
| --- | --- | --- |
| realised profit | `realizedPnl` | `GET /v1/api/portfolio/{accountId}/position/{conid}`, and `rpnl` on `POST /v1/api/pa/transactions` |
| cost basis | `avgCost`, `avgPrice` | the same position route |
| the unrealised figure | `unrealizedPnl`, and `upl` | the same route, and `GET /v1/api/iserver/account/pnl/partitioned` |
| the fee total | **`commission`** | `GET /v1/api/iserver/account/trades`, one of its 28 fields |

**A defect this unit owns.** `src/stocks/broker_exchange.py, in broker_trade` sets
`fee=0.0` and `fee_currency=""` on every record, and its docstring states the
reason: "A broker publishes its size, price and moment as decimal strings and
names no fee on a fill." That is Robinhood's and Alpaca's absence written as a
law. It is false of ibkr, whose own execution record names
`commission`: "Commissions incurred by the execution." The fix lands at that one
site, so every broker naming a fee carries it and every broker naming none keeps
the zero.

#### The paged ledger — no page, and a 7-day window instead

Alpaca capped a page at 100 and the code asked 500. Schwab's cap was
unestablished and the schwab unit wrote no walk. ibkr's own spec settles it:
`GET /v1/api/iserver/account/trades`, `operationId` `getTradeHistory`, summary
"Trade History", description "**Retrieve a list of trades, up to a maximum of 7
days prior.**" It takes **one** query parameter:

```
days   integer, "The number of prior days prior to include in response, up to a
       maximum of 7. If omitted, only the current day's executions will be
       returned."
```

The response is a bare array of execution objects. **There is no page token, no
page size, no cursor and no offset** — in the whole 179-path document the route
declares one parameter. So there is nothing to walk, and the honest build asks
`days=7` and logs that the ledger it read is a seven-day window and not the whole
history. `POST /v1/api/pa/transactions` reaches further back — its `days` field
defaults to 90 — and takes "Only supports one contract id at a time", so it is a
per-market route and not a fill ledger.

#### US-person eligibility — the widest of the three brokers, and one sector that refuses four states

**The account itself refuses no US person and requires none.** Quoted whole from
ibkr's own FAQ: "IBKR accepts applications from citizens or residents of **most
countries except those of countries prohibited by the U.S. Office of Foreign
Assets Control (OFAC)**." Alpaca **requires** a US address in the 50 states or
Puerto Rico; schwab serves US residents only; ibkr requires neither.

**Crypto names 103 eligible countries and excludes no state.** Read whole from
`POST /tws.proxy/faq/content` with `question_id` 182858938, "Is there eligibility
criteria linked to residency to trade cryptocurrency?" The list opens with
"United States" and holds five US territories — **Puerto Rico, Guam, American
Samoa, Northern Mariana Islands and United States Virgin Islands** — every one of
which schwab's crypto agreement refuses. Eight disqualifiers follow, quoted whole:
"addresses in unsupported countries", "account located in an unsupported IBKR
entity (IB-AU, IB-CAN, IB-IN, IB-JP, and IB-SG)", "tax residences in unsupported
countries", "identity numbers, registration numbers, or identity documents from
unsupported countries", "any connection to China", "ORG owners in unsupported
countries", "US TINs starting with 9", "non conforming US Grantor Trusts". And
separately: "Trading of cryptocurrency is not offered in IRA accounts or tax
wrapper accounts such as ISA or SIPP in the UK."

**Commodities is the one sector that names states**, and it names four. Quoted
whole from the Disclosures block of its own US Spot Gold page: "**US Gold is only
available to legal residents of the United States. US Gold is not available to
legal residents of Arizona, Montana, New Hampshire, and Rhode Island.**" Its own
FAQ repeats it word for word.

**One more per-product rule.** Quoted whole from its own products page: "US Mutual
Funds are only available to customers who are U.S. legal residents and have a U.S.
address." `FUND` records under stocks.

**Stocks, forex, indices and futures_perps name no state and no residency refusal.**

**The census, with its two-sided control.** Ten state names were counted across all
13 ibkr pages fetched, over the whole page and not a window, because the schwab
unit's refusal sat 302 lines below its sector word and cryptocom's sat in a table
240 rows from its header.

```
page                     state-name hits                               invented
ib_metals.txt            Arizona 1, Montana 1, New Hampshire 1,              0
                         Rhode Island 1, New York 1
ib_stocks.txt            New York 1                                          0
ibkr_crypto.txt          New York 3                                          0
ibkr_products.txt        New York 2                                          0
the other 9 pages        none                                                0
```

Positive control: the same reading found all four refused states on the one
page that carries a refusal. Negative control: an invented state name reads **0**
on all 13 pages. Every "New York" hit outside the metals page was read in context
and **none is a refusal** — they are "New York Stock Exchange", "New York
Department of Financial Services", "New York BitLicense" and "New York State
Department of Financial Services", a regulator or an exchange and never a
residency clause.

#### The ticker collision, and the symbology that settles it

| code | the equity reading | the currency reading | which wins on ibkr, and why |
| --- | --- | --- | --- |
| `NOK` | Nokia, a listed ADR | Norwegian krone, **1 of ibkr's own 28 currency legs** | **both, and the symbol says which.** A bare code is an equity; a pair is two codes joined by a dot, as in `USD.NOK` |
| `SGD` | none | Singapore dollar, a leg on its own 28-code list, and the first leg of its own `USD.SGD` example | the currency |
| `AMD` | Advanced Micro Devices | Armenian dram | the equity. `AMD` names **0** of the 28 legs |
| `COP` | ConocoPhillips | Colombian peso | the equity. `COP` names **0** of the 28 legs |

ibkr writes a currency market as **two codes joined by a dot** — its own
`/iserver/currency/pairs` example answers `USD.SGD`, `USD.RON`, `USD.CZK` — and an
equity as a bare ticker. A contract carries a `FUT` class word and an expiry. So
the venue's own symbology separates all four codes with no cited row, which is the
reading schwab's leading slash and slashed pair already took.
`STABLECOIN_DENYLIST` in `src/exchange/market_inspector_fetcher.py` is read by
`in _pick_universe` and `in _quote_volumes` over a venue's own **tickers**, and a
broker publishes none through that path, so none of its 30 codes touches an ibkr
symbol.

#### Row 16 — two ids, one firm, and what the firm's own hosts say

`EQUITY_VENUES` holds `ibkr` and `interactivebrokers`, and row 16 exists to close
that. Four readings, all from the firm's own hosts:

```
www.ibkr.com                  200, redirects to www.interactivebrokers.com,
                              240,678 bytes, byte-for-byte the same page
api.ibkr.com                  200, the firm's own API host
api.ibkr.com/gw/api/v3/api-docs   200, "IB REST API", the order spec itself
an invented host              000, no DNS record
```

**The firm's own short domain redirects onto its own long one**, so both names are
the same firm and neither names a second venue. The id the rest of the tree reads
is `ibkr`:

```
                                  ibkr   interactivebrokers
files in src/ naming it              2                    1
sectors venues_for_class offers      6                    1
EXTRA_VENUE_CLASSES rows             1                    0
EQUITY_VENUES member               yes                  yes
```

`interactivebrokers` reaches `EQUITY_VENUES` and nothing else, and it is read on
exactly one line of `src/`. `ibkr` is the firm's own API host name, carries the
`EXTRA_VENUE_CLASSES` row for five sectors, and is offered under all six.
**`VENUE_ID` is `ibkr`, and every row this unit writes is keyed `ibkr`.**

**Neither id is removed in this unit.** Removing an id reshapes the Exchanges tab
and belongs to row 16's own unit, exactly as the schwab unit left `tdameritrade`
standing after proving it names no venue that exists. What this unit records is the
reading beside both ids, so the row that removes one has the measurement it needs.

#### Where the answer is nothing, and the count that shows it

- **a cash market buy this program can compose** — `CITED_CASH_MARKET_BUY` gains **0** ibkr rows. That set is keyed by **venue** and ibkr's cash-amount rule is per **security type**: its own API page excepts "Cryptocurrencies and Forex" alone, so a venue-keyed row would claim a cash market buy of its equities, which the same page refuses. The row is not written because the table's grain is wrong for this venue, and the crypto rule is carried by `ORDER_TYPES_LIMIT_ONLY` instead, at the market grain the recording already has.
- **a market-keyed sector row** — `CITED_VENUE_MARKET_SECTORS` gains **0** ibkr rows. The venue's own `assetClass` word answers every market, and its own symbology separates every colliding code, so no market needs the finer grain.
- **options** — `src/trading/ata_spm.py` draws six sectors and options is not one, so `OPT` and `FOP` map to no sector. ibkr's order-status vocabulary holds both and this connector records neither.
- **bonds** — `BOND` is in the vocabulary and bonds is **0** of this platform's six sectors. Its own futures page names Fixed Income and Interest Rates as two of eleven families, and both record under no sector.
- **warrants, combos and event contracts** — `WAR`, `BAG` and the event-contract rows map to no sector this platform draws. The trade record's `side` enum carries `"N"` for "Shares netted from trading Event Contracts" and `"X"` for an expiration, and neither is a buy or a sell.
- **a paper route** — ibkr's own Notes & Limitations page states "Paper Trading Accounts are based on a simulated environment, and as a result, order execution behavior is not indicative of real world trading conditions." A paper account exists, and the account record's own `type` field reads `DEMO` in the venue's own example, so `HAS_PAPER_ROUTE` is True and `broker_paper_route` opens the paper session.
- **an index that takes an order** — `IND` is in **0** of the three product lists that name an order type and in **0** of the nine words the order-status vocabulary holds. Not an absence of the sector: the index future carries it.

#### The arithmetic, offered minus actionable

Driven with the home redirected and no venue contacted.

```
sector          offered  Add form  ibkr offered  order_types_for  unit_rule  offered - form
crypto               22        22           yes             None       None              0
stocks               21        21           yes             None       None              0
commodities          20        20           yes             None       None              0
forex                13        13           yes             None       None              0
indices              19        19           yes             None       None              0
futures_perps        17        17           yes             None       None              0
```

The Add form cannot differ from the offered set:
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` iterates
`venues_for_class` itself, and the difference is **0** in all six sectors. What is
missing is not the offer. `broker_serves_sector("ibkr", "stocks")` answers
**False** because `BROKER_CONNECTORS` holds `alpaca`, `robinhood` and `schwab` and
no ibkr row, so a Start press on any of the six sectors takes the crypto path and
finds no connector. **Six sectors offered, zero reachable.**

#### The verdict

```
crypto           yes-if
stocks           yes
commodities      yes-if
forex            yes
indices          yes
futures_perps    yes
```

Four plain yeses, which no venue in this issue has had. The order route, the order
body, the market list, the fill ledger, the position read, the price history and
the candles are all published on credential-free routes, and this unit builds
against them.

Two sectors carry a cost of their own, and both are the venue's own rule and not a
missing door:

- **crypto** needs the Cryptocurrencies trading permission, which its own page says is requested in Client Portal and "final approval will be determined by Cryptocurrency Service Providers", and a market buy can never carry a unit count.
- **commodities** needs the Metals trading permission with the "United States" box checked, and it refuses residents of Arizona, Montana, New Hampshire and Rhode Island.

**What the operator must do, once:** open or name an IBKR account, request the
Cryptocurrencies and Metals trading permissions in Client Portal, and store the
Web API credential. The order spec needs nothing from him, because ibkr publishes
it.

#### What this unit builds

1. `src/stocks/ibkr_connector.py` — `IbkrConnector` with `VENUE_ID`, `SECTORS_SERVED` naming all six, `ASSET_CLASS_SECTORS` off the venue's own nine-word vocabulary plus `CMDTY` and `IND`, `FUTURES_FAMILY_SECTORS` off its own eleven families, `CURRENCY_LEGS` holding its own 28 codes, `asset_sector`, `market_rules`, `published_time_in_force`, `list_assets`, `list_fills` and a `place_order` that **composes a real body** on the one published route.
2. Registration in `BROKER_CONNECTORS`, so `broker_connector_class` answers it and a Start press builds it through `BrokerExchange`.
3. `CITED_VENUE_ORDER_TYPES` rows in all six sectors, crypto reading `ORDER_TYPES_LIMIT_ONLY` on the venue's own market-buy rule.
4. `CITED_UNIT_RULES` rows in all six sectors: fractional on crypto and forex, the two its own API page excepts, and whole on the other four.
5. `CITED_VENUE_SESSIONS` with a `SESSION_US_EQUITY` row for stocks alone, and five sectors deliberately absent.
6. `CITED_VENUE_SETTLEMENT` rows for stocks at 1.0 day and forex at 2.0 days, the first settlement figures any venue has published here besides coinbase's zero.
7. `CITED_VENUE_BASE_SECTORS` one row, `("ibkr", "PAXG")` to commodities.
8. **The `broker_trade` fee defect**, fixed at its one site so a broker publishing a fee carries it.
9. The `manualIndicator` field on every futures order, because the venue's own spec says an order without it is rejected.

Full readings, with every control and every URL, will land in
`docs/audits/2026-10-11_ibkr_wired_sectors/REPORT.md`.

---
## Part two — what the build settled

`ibkr` is the first broker whose order body this program composes. Schwab serves
its order spec only to a signed-in developer, so
`src/stocks/schwab_connector.py, in SchwabConnector.place_order` raises. Interactive
Brokers serves a complete OpenAPI document on a credential-free route, so
`src/stocks/ibkr_connector.py, in IbkrConnector.place_order` sends a real body.

Every figure below was read on 2026-10-11 from the firm's own hosts, with no
credential sent, no order placed or previewed, and no account registered.

#### The one document every answer comes from

| the reading | the answer |
| --- | --- |
| `api.ibkr.com/gw/api/v3/api-docs` | 200, 939,918 bytes, no credential |
| its own title and version | "IB REST API", openapi 3.0.0, version 2.41.0 |
| paths it names | 179 |
| order routes among them | **1** |
| `api.ibkr.com/v1/api/<a real route>` | 401, 49 bytes |
| control, `api.ibkr.com/v1/api/<an invented route>` | 401, **49 bytes** |
| `www.interactivebrokers.com/<a real product page>` | 200, 217,058–303,618 bytes |
| control, `www.interactivebrokers.com/<an invented page>` | **404**, 17,287 bytes |
| control, an invented host | 000, no DNS record |

The API host's status names no path: a real route and an invented one answer the
same 401 at the same byte count. The document names the routes instead, and the
product host's status does discriminate.

#### The one order route, and the fields its own schema marks required

`POST /v1/api/iserver/account/{accountId}/orders`, `operationId`
`submitNewOrder`, with a JSON array of order tickets under `orders`.

| field | its own description | what this program sends |
| --- | --- | --- |
| `conid` | "IB contract ID of the reading" | the record's own contract id |
| `orderType` | "IB order type identifier" | `MKT`, `LMT`, `STP` or `STP LMT` |
| `side` | enum `BUY`, `SELL` | the bot's own side |
| `tif` | enum `DAY`, `IOC`, `GTC`, `OPG`, `PAX` | what `published_time_in_force` names |
| `quantity` | "Quantity of the order ticket in units of the reading" | the unit count `sized_order` floored |

Four more fields the same schema publishes reach the body where the market calls
for them: `secType`, `price`, `auxPrice` and `manualIndicator`.
`src/stocks/ibkr_connector.py, in order_body` composes all nine and raises
`ValueError` for a side or an order type the document does not name.

#### The field that would have cost every futures order

Quoted whole from `manualIndicator`'s own description in that document:

> "For all orders for US Futures products, clients must submit this flag to
> indicate whether the order was originated manually (by a natural person) or
> automatically (by an automated trading system transmitting orders without human
> intervention). Submit a True value to indicate a manually originated order, and
> submit a False value to indicate an automated order. Orders for USFUT products
> that do not include this field will be rejected."

This platform transmits with no human intervention, so
`src/stocks/ibkr_connector.py, in MANUAL_ORDER` is False and
`MANUAL_INDICATOR_SECTORS` names the three sectors whose markets are contracts.
An order into commodities, indices or futures_perps carries the flag.

#### Fractional shares, and the page that refuses them

| ibkr's own page | its own sentence |
| --- | --- |
| Fractional Trading | "Invest as little as USD 1" |
| the same page's Get Started list | Trader Workstation, IBKR Mobile on four devices, Client Portal |
| order-type Notes & Limitations | "Interacive Brokers APIs do not support fractional or cash quantity trading with exception to Cryptocurrencies and Forex trading." |
| the minimum-order FAQ | "You can place trades with an order size as low as 1 share, 1 contract, 1 unit of currency." |

Six platforms reach a fraction of a share and the API is not one of them. The
order schema's own `quantity` is `type: number`, which permits a decimal, so the
schema allows what the page refuses. The reading that satisfies both is that the
fraction is a platform feature, so `CITED_UNIT_RULES[("stocks", "ibkr")]` is
`WHOLE_UNITS`. This inverts alpaca and schwab, which are both fractional.

#### The unit rule per sector

| Sector | rule | the venue's own figure |
| --- | --- | --- |
| crypto | fractional | "The minimum order size is .00000001." |
| stocks | whole | "an order size as low as 1 share" |
| commodities | whole | "Efficient Pricing in Quantities as Small as 1 Ounce" |
| forex | fractional | "units of the first currency of the pair", no step named |
| indices | whole | one contract, each carrying its own multiplier |
| futures_perps | whole | one contract, each carrying its own multiplier |

`src/stocks/ibkr_connector.py, in size_increment` writes the same step per
market off the record's own security type, so `PAXG` records under commodities
and still steps at the crypto route's own fraction.

#### The crypto market buy that cannot carry a unit count

Quoted whole from ibkr's own Cryptocurrency Trading page:

> "Please be aware that no other order types are available for Crypto orders."

| side | order types | time in force |
| --- | --- | --- |
| BUY | "LMT Order Using 'quantity' or 'totalQuantity' values." and "MKT Orders using 'cashQty' value." | LMT takes "DAY", "GTC", "IOC"; "MKT Orders only support 'IOC'." |
| SELL | "LMT Order Using 'quantity' or 'totalQuantity values." and "MKT orders using 'quantity' or 'totalQuantity' values." | the same two rules |

A crypto market buy names a cash amount and nothing else, and this platform
sizes a unit count, so `CITED_VENUE_ORDER_TYPES[("crypto", "ibkr")]` is
`ORDER_TYPES_LIMIT_ONLY` and
`src/trading/scrumming/sizing.py, in market_replaces_market_order` raises every
crypto market order onto the record's own tick.
`src/stocks/ibkr_connector.py, in published_time_in_force` names `IOC` on a
crypto market order, which is the only value the page allows there.

#### A defect this reading found in a shared function

`market_replaces_market_order` read the market's own declaration through
`venue_variant`, which answers one mechanic per market and tests four things
ahead of `MECHANIC_LIMIT_ONLY`. Spot gold found it: `CMDTY` is on ibkr's own
Limit Order product list and on no market one, so its record declares
`ORDER_TYPES_LIMIT_ONLY`, and at $4,100 an ounce
`MECHANIC_SMALLEST_ORDER_OVER_EXCESS` won first and a market order would have
gone to a venue that publishes none for it. The record's own declaration is now
read at that site directly.

Driven over 432 record shapes — four declarations, three sessions, two expiries,
two shape sets, three prices and three moments: **88 answers moved and every one
of them is a record declaring "limit only"** that one of three earlier mechanics
had claimed. Every mover went False to True, so no market lost a limit order it
already had. Controls: a record declaring "market and limit" never moves, a
record declaring nothing never moves, and a record carrying a corrupt
declaration never moves.

#### The order types per sector

| Sector | the row | the venue's own source |
| --- | --- | --- |
| crypto | limit only | its Cryptocurrency Trading page's own per-side rule |
| stocks | market and limit | `STK` is on both its Market Order and Limit Order product lists |
| commodities | market and limit | `FUT` is on both lists; the `CMDTY` record itself declares limit only |
| forex | market and limit | `CASH` is on both lists |
| indices | market and limit | `FUT` is on both lists |
| futures_perps | market and limit | `FUT` is on both lists |

Its Market Order page lists "BOND, CFD, EFP, CASH, FUND, FUT, FOP, OPT, STK,
WAR" and its Limit Order page lists "BOND, CASH, CFD, CMDTY, FUT, FOP, OPT, STK,
WAR". `CMDTY` is on the second and not the first, which is the whole difference.

#### The session, in the venue's own words

Interactive Brokers answers its own clients on its own Trading Outside Regular
Trading Hours page:

> "It is not possible to submit market orders outside of RTH, including a stop
> loss."

> "Only Day Limit orders are allowed in the US overnight trading session."

> "It depends on the product you are trading. Futures are available outside RTH.
> US stocks are not."

So `CITED_VENUE_SESSIONS` holds one ibkr row, `(stocks, ibkr)` as
`SESSION_US_EQUITY`, and the five other sectors hold none.
`src/stocks/ibkr_connector.py, in asset_session` writes the same word per market
off the record's own `isUS` field, so a market listed outside the US publishes no
session. Driven on one US equity at two hours of Thursday 2026-10-08: at 10:40 ET
the session reads regular, the unit rule is unchanged and the market order
stands; at 18:00 ET the session reads after hours, the unit rule is whole and the
market order becomes a limit at the record's own tick.

#### The settlement delay, the first above zero

| Sector | days | the venue's own sentence |
| --- | --- | --- |
| stocks | 1 | "all US equities settle on a T+1 basis since May 2024" |
| forex | 2 | "Fast settlement, typically in T+2 (trade date plus two days)" |

`CITED_VENUE_SETTLEMENT` held one row before this, coinbase crypto at zero. Its
other four ibkr sectors hold no row, because no ibkr page read names a day count
for a futures contract, a spot-gold trade or a crypto trade.

#### The four figures a broker could not answer

`src/stocks/broker_exchange.py, in BrokerExchange.get_my_trades` raised for every
broker, and alpaca settled three of four with the fee named as its own absence.
Interactive Brokers publishes all four.

| the figure | its own field | the route |
| --- | --- | --- |
| realised profit | `realizedPnl` | `GET /v1/api/portfolio/{accountId}/position/{conid}` |
| cost basis | `avgCost` and `avgPrice` | the same route |
| the unrealised figure | `unrealizedPnl`, and `upl` | the same route, and `GET /v1/api/iserver/account/pnl/partitioned` |
| the fee total | **`commission`** | `GET /v1/api/iserver/account/trades` |

`broker_trade` set `fee=0.0` on every record and its own docstring gave the
reason: a broker "names no fee on a fill". That is false of this venue, whose
execution record carries "Commissions incurred by the execution" among its 28
fields. `src/stocks/broker_exchange.py, in FILL_FEE_FIELD` is now read, and
`src/stocks/ibkr_connector.py, in fill_record` maps `commission` onto it. Driven
on the venue's own example execution: the fee reads 1.01 in USD, and a record
naming no fee still reads 0.0 with an empty currency.

#### The fill ledger — a window, not a walk

Alpaca caps a page at 100 and a short page read as the end. Schwab's cap was
never established. Interactive Brokers publishes neither a page nor a cap.

| the reading | the answer |
| --- | --- |
| route | `GET /v1/api/iserver/account/trades` |
| parameters it declares | **1**, `days` |
| its own ceiling | "up to a maximum of 7" |
| a page token, page size, cursor or offset | **0** of the 179 paths' parameters for this route |
| the response | a bare array of execution objects |

There is nothing to walk. `src/stocks/ibkr_connector.py, in list_fills` asks for
the days a caller's floor needs, capped at seven, and logs
`FILL_WINDOW_NOTE` so no reader takes a short answer for the whole history.
`POST /v1/api/pa/transactions` reaches further back, defaulting to 90 days, and
its own `conids` field "Only supports one contract id at a time", so it is a
per-market route and not a ledger.

#### Eligibility — the widest account of the three brokers, and four states on one sector

| the rule | the venue's own sentence |
| --- | --- |
| the account | "IBKR accepts applications from citizens or residents of most countries except those of countries prohibited by the U.S. Office of Foreign Assets Control (OFAC)." |
| crypto | 103 eligible countries, opening with "United States" and holding Puerto Rico, Guam, American Samoa, Northern Mariana Islands and United States Virgin Islands |
| commodities | "US Gold is only available to legal residents of the United States. US Gold is not available to legal residents of Arizona, Montana, New Hampshire, and Rhode Island." |
| fund shares | "US Mutual Funds are only available to customers who are U.S. legal residents and have a U.S. address." |
| stocks, forex, indices, futures_perps | no state and no residency refusal on any page read |

Alpaca **requires** a US address in the 50 states or Puerto Rico. Schwab serves
US residents only and refuses New York, Louisiana, Ohio, Arizona and every US
territory across two sectors. Interactive Brokers requires no US residency for
the account, serves five US territories its crypto FAQ names, and refuses four
states on one sector alone.

Eight further crypto disqualifiers are its own words: an address in an
unsupported country, an account in IB-AU, IB-CAN, IB-IN, IB-JP or IB-SG, a tax
residence in an unsupported country, an identity document from one, "any
connection to China", an organisation owner in one, "US TINs starting with 9",
and a non-conforming US grantor trust. Crypto is also not offered in an IRA or a
UK ISA or SIPP.

The census, over all 13 ibkr pages read, counting ten state names across the
whole page rather than a window:

| page | state names | control, an invented state |
| --- | --- | --- |
| the US Spot Gold page | Arizona 1, Montana 1, New Hampshire 1, Rhode Island 1, New York 1 | 0 |
| the stocks page | New York 1 | 0 |
| the crypto page | New York 3 | 0 |
| the products page | New York 2 | 0 |
| the other 9 pages | none | 0 |

Positive control: the one page carrying a refusal gives all four of its states to
the same reading. Every "New York" hit outside that page was read in its own
sentence and **none is a refusal** — each names the New York Stock Exchange or
the New York State Department of Financial Services.

#### The ticker collision, and the dot that settles it

| code | the equity reading | the currency reading | which wins, and why |
| --- | --- | --- | --- |
| `NOK` | Nokia, a listed ADR | the Norwegian krone, 1 of ibkr's own 28 currency legs | **both, and the symbol says which.** A bare code is the equity; a pair is two codes joined by a dot |
| `SGD` | none | the Singapore dollar, the first leg of its own `USD.SGD` example | the currency |
| `AMD` | Advanced Micro Devices | the Armenian dram | the equity. `AMD` names 0 of the 28 legs |
| `COP` | ConocoPhillips | the Colombian peso | the equity. `COP` names 0 of the 28 legs |

`src/stocks/ibkr_connector.py, in currency_pair_symbol` takes the venue's own
symbology: a dot with a member of `CURRENCY_LEGS` on each side. Driven on seven
codes: `NOK`, `SGD`, `AMD`, `COP` and `AMD.USD` each answer False and `USD.NOK`
and `NOK.SEK` each answer True, so a bare `NOK` record reads stocks and a
`USD.NOK` record reads forex. One base-keyed row is needed and it is not a
collision: `("ibkr", "PAXG")` records commodities, because the token is on ibkr's
own 20-token crypto table and redeems for gold.

#### Indices reach an order as the contract, never as a CFD

| the reading | the answer |
| --- | --- |
| `IND` on its Market Order product list | absent |
| `IND` on its Limit Order product list | absent |
| `IND` in the nine-word order-status vocabulary | absent |
| `products-cfds.php` | 200, titled "Home \| Interactive Brokers LLC" |
| "CFD" in that page's body | **0** |
| control, its six other product pages | each answers its own title |

The US entity publishes no CFD product page while publishing six others, so the
index route is the index future. Its own futures page names the two index
families itself, Equity Indices and Volatility Indices.

#### The futures families, and the sector each one reaches

ibkr's own futures page names eleven families. `src/stocks/ibkr_connector.py, in
FUTURES_FAMILY_SECTORS` maps eight of them.

| family | sector |
| --- | --- |
| Agriculture, Energy, Metals, Softs | commodities |
| Equity Indices, Volatility Indices | indices |
| Cryptocurrency | crypto |
| Currencies | forex |
| Fixed Income, Interest Rates | no sector this platform draws |
| E-mini and Micro E-mini Futures | a size family whose products repeat a product in another family |

**No perpetual.** The word names **0** of the 13 ibkr pages read, where
"futures" names 265, "currency" 137, "gold" 72 and "index" 24. So futures_perps
is dated contracts alone, which is what schwab reads too.

#### Row 11 — the currency lot, settled by the venue the row names

Issue row 11 reads that only Interactive Brokers documents a currency security
type and "it sizes by the second currency's notional". The first half is right
and the second is the option, not the default. Quoted whole from its own
minimum-order FAQ:

> "Forex order quantity is by default defined in terms of units of the first
> currency of the pair. The concept of Forex lots does not apply at IBKR."

Its own FX Pairs page says the same twice: "Symbol: Specify the target currency.
For orders, this will dictate the quantity value." and "Currency: Specify the base
currency forex pair. This will dictate size with cash quantity trades." So
`quantity` is a unit count of the first currency and `cashQty` is the
alternative. The row's conclusion holds — `UNIT_RULES` needs no third member —
and the reason it gives needs replacing.

The 25,000 figure is a spread penalty and not a floor: "a minimum size of USD
25,000, or equivalent, is imposed on all IdealPro orders. Orders below this size
are considered odd lots… Odd lot marketable limit orders will still be accepted."
So `MarketRules.min_amount` carries no ibkr forex row.

#### Row 16 — two ids, one firm

| the reading | the answer |
| --- | --- |
| `www.ibkr.com` | 200, redirects to `www.interactivebrokers.com` |
| bytes each host serves | 240,678, the same page |
| `api.ibkr.com` | 200, the firm's own API host |
| control, an invented host | 000, no DNS record |
| files in `src/` naming `ibkr` | 2 |
| files in `src/` naming `interactivebrokers` | 1, on one line |
| sectors `venues_for_class` offers `ibkr` | 6 |
| sectors it offers `interactivebrokers` | 1 |

The firm's own short domain redirects onto its own long one, so neither name
reaches a second venue. `ibkr` is the id this unit builds on: it is the API
host's own name, it holds the `EXTRA_VENUE_CLASSES` row for five sectors, and it
keys every sizing row and every gate log. **Neither id is removed here.**
Removing an id reshapes the Exchanges tab, which is its own row, and the reading
now sits beside both in `src/gui/main_tabs/asset_class_surface.py`.

#### The eight connections, driven

Driven with the home redirected and no venue contacted.

| # | the connection | the answer |
| --- | --- | --- |
| 1 | the id in the broker registry | `BROKER_CONNECTORS` holds `alpaca`, `ibkr`, `robinhood`, `schwab`; an invented id answers None |
| 2 | the venue offered under each sector | all six, and `broker_serves_sector` True on all six; an invented sector answers False |
| 3 | a credential form on the Exchanges tab | the form's set equals the offered set in all six sectors, difference 0 |
| 4 | a Start press builds a bot | `BrokerExchange(IbkrConnector())` answers `exchange_id` `ibkr` and a paper route |
| 5 | market rules recorded on connect | 9 records in, 9 rows written, 8 sectors read back, the ninth a `BOND` naming none |
| 6 | the order shape | 8 bodies composed; two controls raise `ValueError` |
| 7 | a built variant selects | all 8 sector-bearing markets hold a built variant |
| 8 | gate decisions log under the venue | `trade/gate/ibkr/<sector>/gate.log` for all six |

The order bodies, read off the composition with nothing sent:

```
BTC   market buy   {"conid":479624278,"orderType":"MKT","side":"BUY","tif":"IOC","quantity":2.0,"secType":"CRYPTO"}
BTC   limit buy    {"conid":479624278,"orderType":"LMT","side":"BUY","tif":"DAY","quantity":2.0,"secType":"CRYPTO","price":100000.0}
AAPL  market buy   {"conid":265598,"orderType":"MKT","side":"BUY","tif":"DAY","quantity":2.0,"secType":"STK"}
USGOLD limit buy   {"conid":69067924,"orderType":"LMT","side":"BUY","tif":"DAY","quantity":2.0,"secType":"CMDTY","price":4100.0,"manualIndicator":false}
USD.SGD market buy {"conid":37928772,"orderType":"MKT","side":"BUY","tif":"DAY","quantity":2.0,"secType":"CASH"}
ES    market buy   {"conid":495512563,"orderType":"MKT","side":"BUY","tif":"DAY","quantity":2.0,"secType":"FUT","manualIndicator":false}
```

The variant each market selects, driven at $100 a unit:

| market | sector | variant | mechanic |
| --- | --- | --- | --- |
| BTC | crypto | Crypto Scrumming | the venue declares no market order |
| PAXG | commodities | Commodity Scrumming | the venue declares no market order |
| AAPL | stocks | Whole Unit Scrumming | the venue's smallest order costs more than the excess |
| USGOLD | commodities | Whole Unit Scrumming | the venue's smallest order costs more than the excess |
| USD.SGD | forex | Forex Scrumming | no order-formatting difference |
| ES | indices | Index Scrumming | the venue expires this market on a date |
| GC | commodities | Commodity Scrumming | the venue expires this market on a date |

#### The arithmetic, offered minus actionable — after the build

```
sector          offered  Add form  order_types  unit rule   difference
crypto               22        22  limit only   fractional           0
stocks               21        21  market+limit whole                0
commodities          20        20  market+limit whole                0
forex                13        13  market+limit whole*               0
indices              19        19  market+limit whole                0
futures_perps        17        17  market+limit whole                0
```

`order_types_for` answered None for all six ibkr sectors before this entry and
answers a cited row for all six now. `unit_rule` answered None for all six and
answers a rule for all six. The forex row reads fractional, and the asterisk
marks the one sector whose step the venue publishes nowhere, so the record
carries no step and the cited row governs.

#### What the Interactive Brokers reading cannot show

No credential was used and no account was registered, so nothing above proves
this venue accepts an order from this program. The order **body** is published
and was read; the **market list** was not, because every `/v1/api/` route answers
401 without a token. So the product counts above come from ibkr's own retail
pages and its own FAQ service, not from its API, and
`IbkrConnector.list_assets` reads `GET /trsrv/secdef` for the contract ids the
operator's own bots name rather than guessing a universe. Two sectors need a
trading permission the operator requests once in Client Portal: Cryptocurrencies,
whose "final approval will be determined by Cryptocurrency Service Providers",
and Metals with the "United States" box checked. The positive control for every
census above is that the same reading finds the doors that do exist: 179 paths,
one order route, nine required and optional order fields, 20 crypto tokens, 28
currency legs and eleven futures families, where an invented word finds 0.

---

## The detours searched

Six, each one shut or opened by a reading.

1. **Another endpoint.** The OpenAPI document names 179 paths and exactly one order route. `/iserver/account/{accountId}/orders/whatif` previews an order and was never called.
2. **Another API version.** `/v1/api/` is the only trading prefix in the document; `/gw/api/v1/`, `/gw/api/v2/` and `/oauth2/api/v1/token` are account-management and token paths, and none of them places an order.
3. **Another documentation host.** `ibkrcampus.com` answers a Cloudflare refusal, "DNS points to prohibited IP", and `www.interactivebrokers.com/docs/` serves the same pages, with a `/llms.txt` index and a `.md` form of every page.
4. **A page's script rather than its markup.** The FAQ's own `index.js` names `getBase()` as `document.location.origin + "/tws.proxy"` and the content route as `faq/content`, which is how every eligibility clause here was read.
5. **Another product reaching the same market.** A CFD would reach indices with no expiry, and the US entity publishes no CFD product page.
6. **A capability already in this tree.** `ccxt` 4.5.85 holds no ibkr exchange: `'ibkr' in ccxt.exchanges` and `'interactivebrokers' in ccxt.exchanges` both answer False, and the three names holding "ib" are `coinbaseinternational`, `deribit` and `hibachi`.

**Control proving the search could have found a door that exists:** the same
reading found the order route itself, its own 29-field schema, the trade route,
the position route, the PnL route, the market-data snapshot and history routes,
the secdef route, the per-exchange conid route, the futures route and the
currency pairs route — eleven doors on a host whose status names none of them.

---

## Defects found and fixed

1. **`broker_trade` threw every broker fee away.** `src/stocks/broker_exchange.py, in broker_trade` set `fee=0.0` and `fee_currency=""` on every record, and its docstring gave the reason as a law: a broker "names no fee on a fill". The venue's own execution record carries `commission`, "Commissions incurred by the execution". The fee is now read off the record through `FILL_FEE_FIELD`, and a broker naming none still answers 0.0. Driven on the venue's own example execution: the fee reads 1.01 in USD, and the same record with the two fields removed reads 0.0 and "".
2. **`market_replaces_market_order` lost the market's own declaration.** It read that declaration only through `venue_variant`, which answers one mechanic per market and tests four things ahead of `MECHANIC_LIMIT_ONLY`. Spot gold found it: `CMDTY` declares `ORDER_TYPES_LIMIT_ONLY` and at $4,100 an ounce `MECHANIC_SMALLEST_ORDER_OVER_EXCESS` won first, so a market order would have reached a venue publishing none for it. The record's own declaration is read at that site now. Driven over 432 record shapes — four declarations, three sessions, two expiries, two shape sets, three prices, three moments: **88 answers moved, every mover a record declaring "limit only" that one of three earlier mechanics had claimed, and every mover False to True**, so no market lost a limit order it already had. Controls: a record declaring "market and limit" never moves, a record declaring nothing never moves, and a record carrying a corrupt declaration never moves.
3. **A fill's moment was dropped.** `broker_trade` reads its moment through `bar_epoch_ms`, which takes an ISO 8601 string alone, and the venue publishes `trade_time_r` in epoch milliseconds. The first drive read a timestamp of 0.0, which `FillHistory` orders oldest first. `src/stocks/ibkr_connector.py, in fill_moment` converts it, and the same drive reads 1702317649.0 now.
4. **A sector was the wrong grain for a size step.** `size_increment` keyed the step off the sector, and `PAXG` records under commodities while its order takes the crypto route. It keys off the venue's own security type now, so `PAXG` steps at 1e-08 and still records under commodities.

Two measuring failures of this unit's own, recorded so the next unit does not
repeat them.

- The first Add-form census read `row[0]` of `exchange_status_rows`, which is the drawn text, and reported the whole offered set as missing from the form. The venue id is `row[1]`. The reading was wrong and the code was right.
- The first add-only control reworded a sentence by replacing `" the "`, and the sentence it picked carried no `" the "` with a space on both sides, so the tamper changed nothing and the control proved nothing. The control changes the fourth word now, and refuses to run at all if the tamper left the sentence unchanged.
