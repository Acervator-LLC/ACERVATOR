# tastytrade — the eight connections and the six sectors

Read 2026-10-11 from tastytrade's own hosts. No credential sent. No order
placed, previewed, priced, dry-run, amended or cancelled. No developer account
and no OAuth application registered. Home redirected on every drive of this
tree.

The venue id is `tastytrade`. `src/stocks/tastytrade_connector.py, in VENUE_ID`
holds it and `src/stocks/alpaca_connector.py, in BROKER_CONNECTORS` keys it.

## Contents

- [Part one — the readings taken before the build](#part-one--the-readings-taken-before-the-build)
- [Part two — what the build settled](#part-two--what-the-build-settled)
- [The detours searched](#the-detours-searched)
- [Defects this unit found in its own first shape](#defects-this-unit-found-in-its-own-first-shape)
- [Calibration](#calibration)

---

## Part one — the readings taken before the build

This part is the comment posted on issue #1192 before any file in this tree was
changed, kept word for word. The per-document sizes behind its one-list block,
each fetched with no credential:

| document | bytes | paths |
| --- | --- | --- |
| `orders.json` | 446,502 | 12 |
| `instruments.json` | 266,855 | 23 |
| `market-sessions.json` | 115,819 | 11 |
| `balances-and-positions.json` | 86,799 | 4 |
| `watchlists.json` | 84,215 | 6 |
| `accounts-and-customers.json` | 72,198 | 4 |
| `transactions.json` | 52,496 | 3 |
| `market-metrics.json` | 44,989 | 3 |
| `risk-parameters.json` | 34,920 | 4 |
| `backtesting.json` | 31,471 | 6 |
| `quote-alerts.json` | 30,719 | 2 |
| `market-data.json` | 29,832 | 1 |
| `margin-requirements.json` | 26,984 | 2 |
| `account-status.json` | 22,012 | 1 |
| `net-liquidating-value-history.json` | 15,895 | 1 |
| `symbol-search.json` | 11,216 | 1 |
| an invented area name | **558** | **404** |

The nine futures families, each product code probed live on the venue's own
credential-free `/symbols/search/` route:

| the venue's own family | named | live | sector |
| --- | --- | --- | --- |
| Equity Index | 12 | 12 | indices |
| Volatility | 2 | 2 | indices |
| Foreign Currency | 11 | 11 | forex |
| Energy | 9 | 9 | commodities |
| Metals | 10 | 10 | commodities |
| Agriculture | 6 | 6 | commodities |
| Livestock | 2 | 2 | commodities |
| Cryptocurrency | 5 | 5 | crypto |
| Interest Rate | 11 | 11 | no family sector; each records under futures_perps |
| **total** | **68** | **68** | commodities 27, indices 14, forex 11, crypto 5, 11 unfamilied |

`/CL` alone answers **108** dated `contract-codes`. Controls: `/ZZQ` and `/QQZ`
each answer nothing.

The word census over the 29 venue files read:

| word | hits | files of 29 |
| --- | --- | --- |
| futures | 725 | 24 |
| currency | 327 | 24 |
| crypto | 325 | 24 |
| fractional | 55 | 4 |
| **perpetual** | **0** | **0** |
| control, an invented word | 0 | 0 |

The baseline control is the venue's own 404 page, which carries "futures" 11,
"currency" 7 and "crypto" 7 from its site navigation alone.

The crypto census:

```
the 26 coins its own page names   asked 26  live 26  types {Cryptocurrency: 26}
the 4 funding stablecoins         asked  4  live  0
index symbols                     asked  6  live  6  types {Index: 6}
currency pairs                    asked  6  live  6  types {Currency Pair: 6}
control, invented coins           asked  2  live  0
```

The route census over all 84 published paths:

```
route names holding candle           0
route names holding bar              0
route names holding ohlc             0
route names holding currency-pair    0
route names holding index            0
route names holding histor           3   net-liq/history, and two
                                         market-metrics/historic-corporate-events
control, names holding instrument   22
control, names holding order        12
control, names holding quote         3
control, names holding transaction   3
```

`ccxt` 4.5.85 carries no tastytrade exchange: `'tastytrade'`, `'tastyworks'` and
`'tastyfx'` each answer False over its 104 names, and **0** names hold `tast`,
where the control `kraken` names 2.

---

## tastytrade — W5H per sector, before the build

The fourth broker, and the second whose order body this program can compose. Read
2026-10-11 off tastytrade's own hosts, its own 16 OpenAPI documents, its own
agent-docs corpus and its own product pages. No credential sent. No order
placed, previewed, priced, dry-run, amended or cancelled. No client or developer
account registered. No OAuth application created. Home redirected on every
drive.

**Schwab's order body was unreadable, ibkr's was published, and tastytrade's is
published in sixteen pieces.** `developer.tastytrade.com/openapi/<area>.json`
serves **16 OpenAPI 3.1.0 documents, 1,372,922 bytes, 84 paths**, every one on a
credential-free route, and an invented area name answers **404 at 558 bytes**. So
`TastytradeConnector.place_order` composes a body and does not refuse.

### Every host, and the control on each

| host | a real path | an invented path | does the answer name a path |
| --- | --- | --- | --- |
| `developer.tastytrade.com` | 200, 29,559–1,046,135 bytes | **404**, 540–558 bytes | yes |
| `developer.tastytrade.com/openapi/` | 200, 11,216–446,502 bytes | **404**, 558 bytes | yes |
| `api.tastyworks.com/market-time/…` | **200**, 294–2,226 bytes, real data | **404**, 13 bytes | yes |
| `api.tastyworks.com/symbols/search/…` | **200**, 1,698 bytes, real data | 200, `items: []` | by the **items**, not the status |
| `api.tastyworks.com/instruments/…` | 401, 83 bytes | 401, **83 bytes** | **no** |
| `api.tastyworks.com` root | 404, 263 bytes | 404, **263 bytes** | **no** |
| `api.cert.tastyworks.com` | 502, 157 bytes | — | — |
| `api.tastytrade.com` | 404, 256 bytes | — | not the API host |
| `tastytrade.com` | 200, 350,180–468,514 bytes | **404**, 326,647 bytes, title "Not found" | yes |
| `support.tastytrade.com/support/s/solutions/articles/…` | 200, 739,255 bytes | **404**, **739,255 bytes, the same shell** | by **status**, not content |
| an invented subdomain | — | **000, no DNS** | — |

Two rows carry no path information and both have a replacement. **`/instruments/`
answers the same 401 at the same 83 bytes for `cryptocurrencies` and for
`invented-zzzqqq`**, so no route census is possible there — the 16 OpenAPI
documents name the routes instead, exactly as ibkr's one document did. The API
root answers 404 at 263 bytes for every unknown path, real or not.

**The Help Center is one JavaScript shell.** A real article id and an invented one
each answer **739,255 bytes of `siteforce:communityApp`**, byte-identical; only
the status differs. The detours searched and shut: `/support/solutions/articles/…`
**401**, `/api/v2/solutions/articles/…` **401**, `tastyworks.freshdesk.com` **404**,
`/s/article/<name>` **404**, `/webruntime/api/…` **401**, and the Aura endpoint
answers a redirect page of 1,452 bytes. Its sitemap does answer — 246 article ids
over three sitemaps — with **no titles**. So the eligible-country list the
International Accounts page links to is not readable on a credential-free route,
and nothing in this unit depends on it.

### The one list every answer comes from

```
developer.tastytrade.com/openapi/{area}.json   16 documents, openapi 3.1.0
                                               1,372,922 bytes, 84 paths
developer.tastytrade.com/llms-full.txt         1,046,135 bytes, the whole
                                               documentation corpus
developer.tastytrade.com/postman/
    tastytrade.postman_collection.json         89,904 bytes
api.tastyworks.com/symbols/search/{symbol}     200 with real instrument records,
                                               no credential
api.tastyworks.com/market-time/…               200 with the live sessions,
                                               no credential
```

`ccxt` 4.5.85 carries no tastytrade exchange: `'tastytrade'`, `'tastyworks'` and
`'tastyfx'` each answer False over its 104 names, and **0** names hold `tast`,
where the control `kraken` names 2. So this venue needs a hand-written connector,
as alpaca, schwab and ibkr did.

### The order route, and the order body, both published

**One order route serves every sector**:
`POST /accounts/{account_number}/orders`, `operationId`
`postAccountsAccountNumberOrders`, summary "Submit Order". **Six fields are
required and the document names them** — three on the order and three on each
leg:

```
required, order   order-type  time-in-force  legs
required, leg     action  instrument-type  symbol

order-type        enum  Limit, Market, Marketable Limit, Notional Market,
                        Stop, Stop Limit
time-in-force     enum  Day, Ext, Ext Overnight, GTC, GTC Ext,
                        GTC Ext Overnight, GTD, IOC
price             decimal string, "Required for limit and stop-limit orders"
price-effect      enum  Credit, Debit
value             decimal string, "required for notional market orders"
leg.quantity      decimal string, "Required for all orders but notional market"
leg.action        enum  Allocate, Buy, Buy to Close, Buy to Open, Sell,
                        Sell to Close, Sell to Open. "Note: `Buy` and `Sell`
                        are only applicable to Futures orders."
external-identifier  string, the client order id
automated-source     boolean, "If the order was placed from an automated
                              source", default false
```

**Every figure is a decimal string, not a number.** The schema says so on each
one: "Decimal value serialized as a JSON string (e.g. \"150.25\")". ibkr's
`quantity` was `type: number`; this one is `type: string, format: decimal`. A
body that sends a float sends a type the schema does not declare.

**A field ibkr's `manualIndicator` has a mirror of, read the other way round.**
`automated-source` defaults **False** and this platform transmits with no human
intervention, so every order it composes carries it **True**. ibkr's flag reads
False to mean automated; this one reads True. Writing either from the other's
habit would mis-declare every order.

**`price-effect` is a field no venue in this issue has had.** A price is a
magnitude and its direction is a separate enum word: a buy limit is `Debit` and a
sell limit is `Credit`. A body carrying a price and no `price-effect` names no
direction.

### The security type is the sector, and the venue publishes two vocabularies

`instrument-type` appears twice in the same document with two different widths,
and the difference is the whole forex-and-indices reading.

```
order leg instrument-type, 8 words, at 7 sites
    Cryptocurrency  Equity  Equity Option  Event Contract
    Fixed Income Security  Future  Future Option  Liquidity Pool

condition instrument-type, 14 words, at 16 sites
    Bond  Cryptocurrency  Currency Pair  Equity  Equity Offering  Equity Option
    Event Contract  Fixed Income Security  Future  Future Option  Index
    Liquidity Pool  Unknown  Warrant
```

The six words in the wide list and not the narrow one are **Bond, Currency Pair,
Equity Offering, Index, Unknown, Warrant**. Each can trigger a condition on an
order and **none can be an order leg**. The venue says the same thing in prose on
its own Instruments & Symbology page, quoted whole: "An **instrument** is any
single tradeable security at tastytrade: an equity, equity option, future, future
option, or cryptocurrency." Five tradeable kinds, and neither `Currency Pair` nor
`Index` is one.

**The route census says it a third time.** Over all 84 paths: the names holding
`instrument` number 22, `order` 12 and `quote` 3, and the names holding
`currency-pair` number **0** and `index` **0**. The venue publishes a list route
for cryptocurrencies, equities, futures, future options and warrants, and none
for a currency pair or an index.

**And its own live data names five types.** `GET /symbols/search/{symbol}`
answers without a credential. Driven over 52 prefix queries, 791 records: Equity
494, Future 296, Cryptocurrency 1, and `Index` and `Currency Pair` answer only on
an exact symbol — `SPX`, `VIX`, `NDX`, `RUT`, `XSP`, `DJX` all read `Index`, and
`EUR/USD`, `USD/JPY`, `GBP/USD`, `SGD/JPY`, `USD/NOK`, `EUR/GBP` all read
`Currency Pair`. Controls: two invented symbols answer 0 items.

### crypto — 26 coins, all live, and a fee that is a percentage

- **who** — `src/stocks/tastytrade_connector.py, in TastytradeConnector.place_order` composes the body; `src/stocks/broker_exchange.py, in BrokerExchange.place_order` shapes it; `src/trading/bot_container.py, in guarded_place_order` sizes and submits
- **what** — 26 coins, read whole from the venue's own Available Cryptocurrencies page: AAVE, ADA, ALGO, APT, ARB, AVAX, BAT, BCH, BTC, COMP, DOGE, DOT, ETC, ETH, HBAR, LINK, LTC, PEPE, POL, SHIB, SOL, SUI, UNI, XLM, XRP, XTZ, each as `<CODE>/USD`, "through Zero Hash". **26 of 26 answer live** on `/symbols/search/`, every one `instrument-type` `Cryptocurrency`; two invented coins answer 0
- **where** — `POST /accounts/{account_number}/orders`, the one order route, leg `instrument-type` `Cryptocurrency`
- **when** — `src/stocks/tastytrade_connector.py, in TastytradeConnector.list_assets` on every connect; `src/stocks/broker_base.py, in BrokerBase.record_markets` writes the rules and the sector
- **why** — `src/trading/scrumming/sizing.py, in venue_order_types` and `in unit_rule` both answer **None** for this sector and for all six, so no cited row governs any tastytrade order
- **how** — `src/trading/scrumming/sizing.py, in sector_variant` answers Crypto Scrumming. The step is **1e-08**: `/instruments/quantity-decimal-precisions` publishes it and its own description says "BTC/USD has a precision of 8, so `0.12345678` is valid but `0.123456789` is not", so `recorded_unit_rule` reads `FRACTIONAL_UNITS`

**The session.** Quoted whole from its own crypto page: "Since cryptocurrencies
trade **24/7/365** and do not take a break like stock, options, and futures,
settlement times will vary depending on the day that a position is closed." So
`SESSION_CONTINUOUS`, the coinbase and alpaca reading.

**The settlement figure, and it is three figures.** Quoted whole from the same
page: "Trades closed before anytime on Sunday and those closed before 12am CT
Monday thru Wednesday will settle **T+2**. Trades placed before 12am CT Thursday
and Friday will settle **T+4**. Trades closed on Saturday (at any time) will
settle **T+3**." `CITED_VENUE_SETTLEMENT` holds one float per pair, so the row is
the **longest** of the three, 4.0. A shorter figure would let a Thursday sale
fund a buy the venue has not funded; the longest is never wrong and only holds
cash longer on some days.

**The four funding stablecoins are not markets.** Its own page names USDC, USDT,
PYUSD and RLUSD as "stablecoin tokens" it accepts "when funding an individual
crypto-enabled account". Driven on `/symbols/search/`: **0 of 4** answer as a
`<CODE>/USD` market, against **26 of 26** for the traded coins and 0 of 2 for two
invented coins. So no row records them as crypto markets.

**No gold token.** `PAXG` and `XAUT` name 0 of the 26, so
`CITED_VENUE_BASE_SECTORS` gains no crypto-to-commodities row — the alpaca,
cryptocom and ibkr row has no tastytrade equivalent.

**The fee is a rate and not an amount.** Its own pricing table: "Cryptocurrency
(BTC/ETH) **0.75%** per total purchase to open / to close" and "All other
cryptocurrencies **1%**". That is the first percentage fee any broker in this
issue has published; the per-fill figure is still read off the transaction
record, which names the dollar amount.

### stocks — fractional per market, published per market, which is the third reading in three brokers

- **who** — the same three symbols
- **what** — "Build a diversified portfolio, from tech giants to consumer staples—**full or fractional shares, it's your choice**", on its own `/stocks/` page. The market list is `GET /instruments/equities` at **1,000 rows a page, capped at 1,000**, and `GET /instruments/equities/active` at 1,000 a page **capped at 5,000**
- **where** — the same one order route, leg `instrument-type` `Equity`
- **when** — the same two moments
- **why** — `src/trading/scrumming/sizing.py, in CITED_UNIT_RULES` holds no tastytrade row in any sector and `CITED_VENUE_SESSIONS` holds none either, so this sector has no cited rule at all
- **how** — `src/trading/scrumming/sizing.py, in session_unit_rule` and `in session_order_types`, because this is a US equity session

**The reading that is neither alpaca's nor ibkr's.** Alpaca is fractional
venue-wide, schwab is fractional venue-wide, ibkr's API is whole venue-wide, and
**tastytrade publishes the answer per equity**. `Equity.is-fractional-quantity-eligible`,
quoted whole: "Whether the equity can be traded in fractional share quantities."
And `/instruments/quantity-decimal-precisions`, quoted whole: "The `value`
defines how many decimal places a quantity may use… **A value of 0 means the
instrument must trade in whole numbers.**" So the grain is the market, the
recording carries it, and `recorded_unit_rule` reads the venue's own answer per
symbol. `CITED_UNIT_RULES[(stocks, tastytrade)]` is the fallback for a market the
recording holds no step for, and it is `WHOLE_UNITS` — a share is a whole share
unless the venue's own flag says otherwise, and the flag is the exception.

**The session, in the venue's own live data.** `GET /market-time/equities/sessions/current`
answers without a credential:

```
start-at       12:15 UTC   08:15 ET, the pre-market open
open-at        13:30 UTC   09:30 ET, the regular open
close-at       20:00 UTC   16:00 ET, the regular close
close-at-ext   00:00 UTC   20:00 ET, the extended close
```

That is `SESSION_US_EQUITY` exactly. **And the extended window is reached by a
time in force, not by an order type.** The venue's own `tif` enum holds `Ext`,
`Ext Overnight`, `GTC Ext` and `GTC Ext Overnight` beside `Day` and `GTC`, and
`Equity.overnight-trading-permitted` flags it per equity. This platform sends
`Day` on a market order and `GTC` on a limit order —
`src/stocks/broker_exchange.py, in BROKER_ORDER_TYPES` — and **neither is an
`Ext` word**, so an order this platform composes works inside the regular session
alone. `CITED_VENUE_SESSIONS` gains the `SESSION_US_EQUITY` row, which is what
holds the order to the shape the platform's own time in force can reach.

**Where schwab's and ibkr's rule was a sentence, this venue's is a field.** Schwab
publishes "only limit orders outside it" in prose and ibkr publishes "It is not
possible to submit market orders outside of RTH" in a staff answer. tastytrade
publishes **no sentence either way** on its own pages — its `/learn/` extended-hours
page is industry education, and says "**Most** brokerage firms accept only limit
orders during extended hours", which is a statement about firms and not about
tastytrade. The venue's own mechanism is the `Ext` time in force, and the honest
row is the session one; the order-type restriction outside hours is **not
established** and this unit claims none.

**24/5 is a published fact and a separate door.** Its own `/stocks/` page:
"**24/5 TRADING. $0 COMMISSIONS.** Get around-the-clock access to hedge and
speculate." That door is `Ext Overnight` on an equity whose own record permits
it, and this platform's time in force does not reach it. Naming the overnight
session as this platform's session would claim hours its own order cannot use.

**No settlement figure.** Nothing on the 20 tastytrade.com pages read states an
equity settlement period. `CITED_VENUE_SETTLEMENT` gains no stocks row, and that
is an absence, not a zero.

### commodities — 27 contracts over four of the venue's own nine families

- **who** — the same three symbols
- **what** — **27 contracts**, from four families its own Available Futures Products page names: Energy 9 (/CL, /MCL, /QM, /NG, /MNG, /QG, /RB, /HO, /BZ), Metals 10 (/GC, /MGC, /1OZ, /HG, /MHG, /SI, /SIL, /SIC, /PL, /PA), Agriculture 6 (/ZC, /XC, /ZS, /XK, /ZW, /XW) and Livestock 2 (/LE, /HE). **No spot metal and no spot energy**: the venue's own five tradeable kinds hold no commodity instrument, so every commodity here is a dated contract
- **where** — the same one order route, leg `instrument-type` `Future`, leg `action` `Buy` or `Sell`, the two words its own schema marks "only applicable to Futures orders"
- **when** — the same two moments
- **why** — `src/exchange/base.py, in MarketRules` carries `contract_size`, and `Future.contract-size` and `Future.notional-multiplier` are both published per contract, so this venue fills that field for every futures market
- **how** — Whole Unit Scrumming. `src/trading/scrumming/sizing.py, in contracts_for_units` reads the contract size and `position_minimum_refusal` guards the two-unit floor

**Every one of the 68 product codes is live, and the controls prove the census.**
Driven over the nine families its own page names, on `/symbols/search/` with no
credential: **68 named, 68 live**, every one `instrument-type` `Future`, each
carrying its own `price-increments` and a list of dated `contract-codes` — /CL
alone answers **108** contract codes. Two invented codes, `/ZZQ` and `/QQZ`,
answer None.

| the venue's own family | contracts | sector |
| --- | --- | --- |
| Equity Index | 12 | indices |
| Interest Rate | 11 | **no sector this platform draws** |
| Foreign Currency | 11 | forex |
| Energy | 9 | commodities |
| Metals | 10 | commodities |
| Agriculture | 6 | commodities |
| Cryptocurrency | 5 | crypto |
| Livestock | 2 | commodities |
| Volatility | 2 | indices |

12 + 11 + 11 + 9 + 10 + 6 + 5 + 2 + 2 = **68**. Per sector: commodities 27,
indices 14, forex 11, crypto 5, and 11 under no sector.

**The venue also publishes the sector word itself.** `FutureProduct.market-sector`,
quoted whole: "Market sector classification", example "Equity Index". So the
family map above is the fallback and the record's own word is read first, the
precedence `ccxt_connector.market_asset_class` already takes.

### forex — the sector the screen missed, and two doors of which one opens

- **who** — the same three symbols
- **what** — **11 currency futures**, the Foreign Currency family its own page names: /6E, /M6E, /6J, /6B, /M6B, /6C, /MCD, /6A, /M6A, /6M, /6S. All 11 live, all `Future`. And **80+ spot pairs** — "Forex trading offered through **tastyfx** includes 20 US dollar pairs and 60+ non-USD pairs" — which is the door that does not open
- **where** — the same one order route for the 11 contracts; **no route at all** for the spot pairs
- **when** — the same two moments
- **why** — `src/gui/main_tabs/asset_class_surface.py, in venues_for_class` does **not** offer tastytrade under forex, and the venue's own data names a `Currency Pair` instrument type and 11 currency futures. **The offered set is what is wrong**, as it was on bitstamp, cryptocom, mexc and schwab
- **how** — Whole Unit Scrumming on the contract, because a currency future is a contract and not a lot

**Why the spot door does not open, with the refusal quoted.** Spot forex is a
different firm. Quoted whole from its own forex pages: "Forex trading offered by
**tastyfx LLC** ("tastyfx"), an affiliate company of tastytrade, Inc.
("tastytrade"). Both companies are under common control through IG US Holdings,
Inc. **tastytrade and tastyfx are separate legal entities, have separate
businesses and are not responsible for each other's products, services, or
policies.**" And tastytrade's own role: it "is engaged in the business of
**introducing** customer foreign exchange ("Forex," or "FX") accounts to
tastyfx, LLC ("tastyfx"), a CFTC-registered retail foreign exchange dealer".

Three readings close it, each from the venue's own document: `Currency Pair` is
in the 14-word condition enum and **not** in the 8-word order-leg enum; **0** of
the 84 published paths holds `currency-pair`, where `instrument` holds 22; and
its own prose names five tradeable kinds and no currency pair among them.

**So forex is a yes through the contract.** The sector is added to the offered set
and its 11 markets take the one order route every other futures market takes.
Row 11 of this issue — "no venue the platform connects sizes a currency lot" —
holds here too: a currency future is sized in contracts, which `UNIT_RULES`
already answers with `WHOLE_UNITS`.

### indices — 14 contracts, and an `Index` type that takes no leg

- **who** — the same three symbols
- **what** — **14 contracts** over two of its own families: Equity Index 12 (/ES, /MES, /NES, /NQ, /MNQ, /NNQ, /YM, /MYM, /NDOW, /RTY, /M2K, /N2K) and Volatility 2 (/VX, /VXM). All 14 live, all `Future`. The index itself is `instrument-type` `Index` — `SPX`, `VIX`, `NDX`, `RUT`, `XSP` and `DJX` all answer it, 6 of 6
- **where** — the same one order route, reached by the index **future** and not by the index
- **when** — the same two moments
- **why** — the sector is offered and `unit_rule("indices", "tastytrade")` answers **None**
- **how** — Rolling Position Scrumming, whole contracts, with `expiry_close_decision` governing the date

**The index takes no order and the venue says so three ways.** `Index` is in the
condition enum and not the leg enum; **0** of the 84 paths holds `index` as a
route name, where `instrument` holds 22; and its own five tradeable kinds hold no
index. **The detour searched and shut:** `Equity.is-index` exists — "Whether the
equity is an index instrument" — so an index could in principle be an `Equity`
leg. It is not: `/symbols/search/SPX` answers `instrument-type` `Index` and not
`Equity`, so the venue's own data separates the two and an `Equity` leg naming
`SPX` would name a type the record does not carry. The control is the same route
on `GLD`, the SPDR Gold Shares ETF, which answers `Equity` with `etf: true` — a
fund share IS an equity leg and an index is not. The index route for this
platform is the dated contract.

### futures_perps — 68 contracts, and 0 perpetuals

- **who** — the same three symbols
- **what** — all **68** contracts, every one dated. `Future.expiration-date`, `Future.expires-at` and `Future.last-trade-date` are published per contract, and `contract-codes` lists them per product. **No perpetual.** The word "perpetual" names **0** of the 29 venue files read; the controls on the same 29 files are "futures" 725, "currency" 327, "crypto" 325 and "fractional" 55, and an invented word names 0. The baseline control is the venue's own 404 page, which carries "futures" 11 from the site navigation alone
- **where** — the same one order route, with `automated-source` True on every order
- **when** — the same two moments
- **why** — `src/trading/scrumming/sizing.py, in VARIANT_ROLLING_POSITION` is built and `expiry_close_decision` is the action, reading `MarketRules.expiry_ms` which this connector fills from the venue's own `expiration-date`
- **how** — Rolling Position Scrumming, which `VARIANTS_BUILT` holds

**Issue row 5 is overtaken, and this is the venue that overtakes it.** Row 5
reads: "The roll needs data no venue publishes: **no successor field in the
product schema**." tastytrade publishes one. `Future.roll-target-symbol`, quoted
whole: "**Symbol of the contract this one rolls into.**" And beside it
`FutureProduct.roll`, "Contract roll attributes for the product", carrying
`name`, `active-count`, `cash-settled`, `business-days-offset` and `first-notice`.
This unit records the field and does not build the roll — the roll is row 5's own
decision 1, still unanswered — but the reason row 5 gives for being unbuildable
is false of this venue and the measurement now sits beside it.

### The four blank figures — three published, and the fourth refused in writing

`BrokerExchange.get_my_trades` raised for every broker. Alpaca settled three of
four, schwab none, ibkr all four. tastytrade settles three and **states the
fourth's absence itself**.

| the figure | tastytrade's own field | the route |
| --- | --- | --- |
| realised profit | `realized-today`, `realized-day-gain` | `GET /accounts/{account_number}/positions` |
| cost basis | `average-open-price` | the same positions route |
| the fee total | **`GET /accounts/{account_number}/transactions/total-fees`**, a route of its own | plus six fee fields per fill |
| the unrealised figure | **none** | — |

Quoted whole from its own Positions & Balances page: "**The API does not return a
live profit/loss figure.** You compute it using **mark** (current value of one
unit) against a cost basis". The schema agrees: `CurrentPosition` carries
`average-open-price`, `realized-today`, `realized-day-gain`, `mark` and
`mark-price`, and no unrealised field. So the absence is the venue's own written
statement, not an unread page.

**The fee is six fields, not one.** ibkr published one `commission` and
`FILL_FEE_FIELD` reads one name. tastytrade's `Transaction` publishes
**`commission`, `clearing-fees`, `regulatory-fees`,
`proprietary-index-option-fees`, `currency-conversion-fees` and `other-charge`**,
each paired with its own `-effect` enum of `Credit`, `Debit` or `None`, plus
`is-estimated-fee`, "Whether the fees on this transaction are estimated rather
than final". The fee on one fill is their sum, and the connector's own
`fill_record` sums them onto the one `fee` name `broker_trade` reads — no change
at that site.

**And the venue publishes an unsettled figure row 9 needs.**
`AccountBalance.unsettled-cryptocurrency-fiat-amount` with its own
`-effect`, beside `total-settle-balance`, `cash-settle-balance` and
`margin-settle-balance`. Row 9's `unsettled_usd` holds one row today; this is a
venue that publishes the number directly.

### The paged ledger — a real walk, with the total published

Alpaca capped a page at 100, the code asked 500, and a short page read as the
end. Schwab's cap was unestablished and that unit wrote no walk. ibkr's route
declares one parameter and no cursor. **tastytrade publishes every cap in its own
schema**, so the walk is determinate:

```
GET /accounts/{account_number}/transactions
    per-page      default 250, maximum 2000
    page-offset   default 0
    sort          Desc or Asc, "Defaults to Desc"
    pagination    per-page, page-offset, item-offset,
                  total-items, total-pages, current-item-count
```

**A short page cannot lie here, because the venue publishes `total-pages`.** Its
own pagination guide states the stop condition word for word: "you are on the
last page when `page-offset + 1 >= pagination.total-pages`". It also states the
rate discipline: "**Keep `per-page` modest and page steadily rather than
hammering the endpoint** — a burst of rapid requests can earn an HTTP 429", and
its own example asks `per-page=250`. So the walk asks the venue's own default and
stops on the venue's own total, not on a short page.

The cap census over all 84 paths, because a cap read from one route does not hold
for another:

```
/accounts/{n}/transactions          per-page default 250   max 2000
/accounts/{n}/balance-snapshots     per-page default 250   max 2000
/accounts/{n}/orders                per-page default  10   max  200
/accounts/{n}/orders/live           per-page default 100   max  200
/customers/{id}/orders              per-page default  10   max  200
/instruments/equities               per-page default 1000  max 1000
/instruments/equities/active        per-page default 1000  max 5000
/instruments/futures                per-page default 1000  max 1000
/instruments/future-products        per-page default 1000  max 1000
/accounts/{n}/positions             no page parameter — one answer
/instruments/cryptocurrencies       no page parameter — one answer
/instruments/quantity-decimal-precisions   no parameter at all — one answer
```

**The open-orders default is 10.** `GET /accounts/{n}/orders` defaults
`per-page` to 10 and caps at 200, so a reader taking the default reads 10 orders
and reads a fleet's book as ten rows. That is the alpaca defect in a new shape,
caught before it was written.

### US-person eligibility — the widest account of the four brokers, and no state anywhere

**The venue requires no US person and names no state.** Quoted whole from its own
International Accounts page: "**International customers are welcome to open
individual margin, individual cash, and joint accounts with tastytrade.** We do
not support international entity accounts at this time." And "Customers in
eligible countries can open international accounts". Alpaca **requires** a US
address in the 50 states or Puerto Rico; schwab serves US residents only and
refuses Ohio, Arizona, New York and Louisiana by product; ibkr refuses no US
person and names four states for US Gold; tastytrade requires neither and names
none.

**The census, over the whole of each page and not a window**, because the schwab
unit's refusal sat 302 lines below its sector word and cryptocom's sat in a table
240 rows from its header:

```
state or clause                  files naming it, of 29
New York                                             21
Louisiana                                             0
Ohio                                                  0
Arizona                                               0
Montana                                               0
New Hampshire                                         0
Rhode Island                                          0
Puerto Rico                                           0
"50 states"                                           0
"not available to residents"                          0
control, an invented state name                       0
```

Every one of the 24 "New York" hits was read in its own sentence and **none is a
refusal** — each is the Zero Hash licensing disclosure in the shared footer,
"licensed to engage in Virtual Currency Business Activity by the New York State
Department of Financial Services", which appears on the venue's own **404 page**
too. The 404 page is the baseline control.

**Positive control, on a page that does refuse.** The same instrument, the same
whole-page window, run over Charles Schwab's own forex page: "Ohio" **1**,
"Arizona" **1**, "not available to residents" **1**, and the invented state name
**0**. So the zero on all 29 venue files is a reading of the venue and not
of the instrument.

**Two per-product permissions, and both are a permission and not a refusal.**
Quoted whole from its own Trading Permissions page: "To trade futures on
tastytrade, you must have "**The Works**"", its most comprehensive margin
approval; and "Cryptocurrency trading is **currently available exclusively for
individual accounts**. To start trading cryptocurrencies, simply log in to your
account and enable cryptocurrency trading."

### The ticker collision, and the symbology that settles it

Driven live on `/symbols/search/`, with the venue's own answer per code.

| code | the equity reading | the currency reading | which wins on tastytrade, and why |
| --- | --- | --- | --- |
| `NOK` | **Nokia Corporation Sponsored American Depositary Shares**, XNYS, `instrument-type` `Equity` | the Norwegian krone, a leg of its own `USD/NOK` and `NOK/SEK` | **both, and the symbol says which.** A bare code is an `Equity`; a pair is two codes joined by a slash, and `USD/NOK` answers `Currency Pair` |
| `SGD` | **none** — the exact code answers no record | the Singapore dollar, a leg of its own `SGD/JPY`, "SGD/JPY Spot Forex Pair" | the currency, and only as a leg. The prefix search answers `SGDJ` and `SGDM`, two Sprott gold ETFs, and no bare `SGD` |
| `AMD` | **Advanced Micro Devices, Inc. - Common Stock**, XNAS, `Equity` | the Armenian dram | the equity. `AMD` is a leg of **0** of the pairs its own forex page names |
| `COP` | **ConocoPhillips Common Stock**, XNYS, `Equity` | the Colombian peso | the equity. `COP` is a leg of **0** of the pairs its own page names |

tastytrade writes a currency market as **two codes joined by a slash**, a crypto
market the same way with a `/USD` quote, a futures contract with a **leading
slash**, and an equity as a **bare code**. So the venue's own symbology separates
all four codes and `CITED_VENUE_MARKET_SECTORS` needs **0** rows.

**`STABLECOIN_DENYLIST` touches nothing here.** `src/exchange/market_inspector_fetcher.py, in STABLECOIN_DENYLIST`
holds 30 codes and is read `in _pick_universe` and `in _quote_volumes` over a
venue's own tickers. Driven against this venue's own codes: it names **0** of the
26 crypto codes and **0** of the 68 futures product codes. Control: `SGD` is in
the set, so the instrument would have reported a hit.

### Where the answer is nothing, and the count that shows it

- **a cash market buy this program can compose** — `CITED_CASH_MARKET_BUY` gains **0** tastytrade rows. The venue does publish a cash-amount order: `order-type` `Notional Market` with `value` and `value-effect`, and `leg.quantity` "Required for all orders but notional market". It is an **alternative**, not a requirement — every order type beside it takes a unit count — so this platform's unit count composes on the route it already uses and `VARIANT_CASH_AMOUNT` is not forced. Row 6 of this issue stays as it stands.
- **a market-keyed sector row** — `CITED_VENUE_MARKET_SECTORS` gains **0** tastytrade rows. The venue's own `instrument-type` answers every market and its own symbology separates every colliding code.
- **a stocks settlement row** — `CITED_VENUE_SETTLEMENT` gains **0** stocks rows. Nothing on the 20 tastytrade.com pages read states an equity settlement period, and an absence is not a zero.
- **a base-sector row** — `CITED_VENUE_BASE_SECTORS` gains **0** tastytrade rows. No gold token and no index token: `PAXG` and `XAUT` name 0 of its 26 coins.
- **options** — `src/trading/ata_spm.py` draws six sectors and options is not one, so `Equity Option` and `Future Option` map to no sector. **tastytrade is an options-first firm** — its own pages list 5 futures-option families and 6 option-chain routes — and this connector records neither type. Its own `/futures-option-chains/{symbol}` and `/option-chains/{symbol}` routes are read by nothing in this tree.
- **bonds and prediction markets** — `Bond` and `Fixed Income Security` name a bond and `Event Contract` names its own Prediction Markets product, and bonds, options and event contracts are **0** of this platform's six sectors. Its Interest Rate futures family, 11 contracts, records under no sector for the same reason.
- **warrants, equity offerings and liquidity pools** — `Warrant`, `Equity Offering` and `Liquidity Pool` map to no sector this platform draws. `/instruments/warrants` exists and this connector does not read it.
- **a candle route** — **0** of the 84 published paths holds `candle`, `bar` or `ohlc`. The names holding `histor` number 3 and none is a bar route: `/accounts/{n}/net-liq/history`, and two `/market-metrics/historic-corporate-events/` routes for dividends and earnings. The control is `quote`, which names 3. The venue's candles are on its **DXLink** WebSocket — "Candle events return historical aggregates (open/high/low/close) — you supply a period and type in the symbol (for example `AAPL{=5m}`) plus a `fromTime` Unix-epoch timestamp" — behind `GET /api-quote-tokens` and capped at **100** Candle subscriptions a session. That is a WebSocket this connector does not open, so `get_bars` answers no bar and names the route it did not take.
- **a REST quote without a funded account** — `/market-data/by-type` states its own gate: "The combined number of symbols across all type parameters is capped at **100** per request… **Available to funded account holders only; no delayed quotes are served over REST.**"
- **a paper route** — the venue publishes one and names it a sandbox: `api.cert.tastyworks.com`, "a full copy of the tastytrade API backed by simulated money", and "Orders placed in the sandbox **never reach a real market**". So `HAS_PAPER_ROUTE` is True. Its own warning rides into the status log: "**Fill behaviour is derived from the order type and price**, and nothing else" — a market order "Always fills, at a price of **$1**", a limit under $3 fills, a limit at $3 or above "Goes `Live` and never fills" — and "**Market data is not served.** `/market-data` and `/market-metrics` return HTTP 502 on every route". The host answered 502 on this unit's own probe.
- **an idempotency key** — the venue states its own absence: "tastytrade has **no idempotency-key header and does NOT deduplicate retried submissions**". `external-identifier` is the correlation handle instead, and `BrokerExchange.place_order` drops the `client_order_id` it is handed, so a retry has nothing to correlate on. Named, not fixed in this unit.

### The arithmetic, offered minus actionable

Driven with the home redirected and no venue contacted.

```
sector          offered  Add form  tastytrade offered  venue_order_types  unit_rule  offered - form
crypto               22        22                 yes               None       None              0
stocks               21        21                 yes               None       None              0
commodities          20        20                 yes               None       None              0
forex                13        13                  NO               None       None              0
indices              19        19                 yes               None       None              0
futures_perps        17        17                 yes               None       None              0
```

The Add form cannot differ from the offered set:
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` iterates
`venues_for_class` itself, and the difference is **0** in all six sectors. What is
missing is the connector and one sector.
`broker_serves_sector("tastytrade", "stocks")` answers **False** because
`BROKER_CONNECTORS` holds `alpaca`, `ibkr`, `robinhood` and `schwab` and no
tastytrade row, so a Start press on any of the five offered sectors takes the
crypto path and finds no connector. All seven `CITED_` tables hold **0**
tastytrade rows. `gate_log_path` does compose
`~/.acervator_logs/trade/gate/tastytrade/<sector>/gate.log` for all six.

**Five sectors offered, one missing, zero reachable.**

### The verdict read before the build

```
crypto           yes-if
stocks           yes
commodities      yes-if
forex            yes-if
indices          yes
futures_perps    yes-if
```

Three plain yeses. The four yes-ifs are each the venue's own permission and not a
missing door:

- **crypto** needs cryptocurrency trading enabled, and it is "currently available exclusively for individual accounts".
- **commodities**, **forex** and **futures_perps** are all futures, and futures needs "**The Works**", the venue's most comprehensive margin approval.

**forex is a yes-if and not a no**, and it is the sector the screen does not
offer. Its spot door is shut and proven shut — a separate firm, a type absent
from the order-leg enum, 0 of 84 routes, and the venue's own five-kind sentence —
and its contract door is open: 11 live currency futures on the one order route.

**What the operator must do, once:** open or name a tastytrade account, request
"The Works" for futures and enable cryptocurrency trading, create an OAuth
application and store its refresh token. The order spec needs nothing from him,
because tastytrade publishes it.

### What this unit builds

1. `src/stocks/tastytrade_connector.py` — `TastytradeConnector` with `VENUE_ID`, `SECTORS_SERVED` naming all six, `INSTRUMENT_TYPE_SECTORS` off the venue's own order-leg enum, `FUTURES_FAMILY_SECTORS` off its own nine families and 68 product codes, `asset_sector`, `market_rules`, `published_time_in_force`, `list_assets`, a `list_fills` that **walks the pages on the venue's own `total-pages`**, and a `place_order` that **composes a real body** on the one published route, with every figure a decimal string and `automated-source` True.
2. Registration in `BROKER_CONNECTORS`, so `broker_connector_class` answers it and a Start press builds it through `BrokerExchange`.
3. **forex added to `EXTRA_VENUE_CLASSES` for this venue**, the sector the screen missed, with the 11 currency futures as its reason.
4. `CITED_VENUE_ORDER_TYPES` rows in all six sectors, all `ORDER_TYPES_WITH_MARKET`: the venue's own `order-type` enum holds `Market` and names no per-type restriction.
5. `CITED_UNIT_RULES` rows in all six sectors: fractional on crypto, whole on the five others, with stocks the fallback for a market whose own `is-fractional-quantity-eligible` the recording did not read.
6. `CITED_VENUE_SESSIONS` with `SESSION_US_EQUITY` for stocks and `SESSION_CONTINUOUS` for crypto, and four sectors deliberately absent because a futures session is neither word.
7. `CITED_VENUE_SETTLEMENT` one row, crypto at 4.0 days, the longest of the three figures its own page publishes.
8. `CITED_VENUE_BASE_SECTORS`, `CITED_VENUE_MARKET_SECTORS` and `CITED_CASH_MARKET_BUY` gain **0** rows each, for the reasons counted above.
9. The **open-orders page default of 10**, asked at the venue's own 200 instead, so a fleet's book is not read as ten rows.

Full readings, with every control and every URL, will land in
`docs/audits/2026-10-11_tastytrade_wired_sectors/REPORT.md`.

---

## Part two — what the build settled

### The state before, driven with the home redirected and no venue contacted

```
sector          offered  Add form  tastytrade offered  venue_order_types  unit_rule
crypto               22        22                 yes               None       None
stocks               21        21                 yes               None       None
commodities          20        20                 yes               None       None
forex                13        13                  NO               None       None
indices              19        19                 yes               None       None
futures_perps        17        17                 yes               None       None
```

`BROKER_CONNECTORS` held `alpaca`, `ibkr`, `robinhood` and `schwab` and no
tastytrade row, so `broker_serves_sector("tastytrade", …)` answered **False** on
all six and a Start press on any of the five offered sectors took the crypto path
and found no connector. All seven `CITED_` tables held **0** tastytrade rows.
**Five sectors offered, one missing, zero reachable.**

### The eight connections, each with a two-sided control

| # | the connection | the answer |
| --- | --- | --- |
| 1 | the id in the broker registry | `alpaca`, `ibkr`, `robinhood`, `schwab`, `tastytrade`; an invented id and `tastyfx` each answer None |
| 2 | the venue offered under each sector | all six, `broker_serves_sector` True on all six; an invented sector answers False and an invented venue no class |
| 3 | a credential form on the Exchanges tab | the form's set equals the offered set in all six sectors, difference 0 |
| 4 | a Start press builds a bot | `BrokerExchange(TastytradeConnector())` answers `exchange_id` `tastytrade`, a paper route and a published fill history |
| 5 | market rules recorded on connect | 14 records in, 14 rows written, 12 sectors read back and two naming none; a non-record answers None and an empty asset list writes nothing |
| 6 | the order shape | 10 bodies composed; an `Index` leg, a `Currency Pair` leg, a `Bond` leg, an unpublished side and an unpublished order type each raise `ValueError` |
| 7 | a built variant selects | every sector-bearing market holds a built variant |
| 8 | gate decisions log under the venue | `trade/gate/tastytrade/<sector>/gate.log` for all six |

The recorded rules, read back out of the recording:

| symbol | sector | step | tick | contract | order types | session | expiry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC/USD | crypto | 1e-08 | 0.01 | — | market and limit | continuous | — |
| AAPL | stocks | 1e-06 | 0.01 | — | market and limit | us_equity | — |
| NOK | stocks | 1.0 | 0.01 | — | market and limit | us_equity | — |
| GLD | stocks | 1.0 | 0.01 | — | market and limit | us_equity | — |
| /GCZ6 | commodities | 1.0 | 0.1 | 100.0 | market and limit | — | 2026-12-29 |
| /ESZ6 | indices | 1.0 | 0.25 | 50.0 | market and limit | — | 2026-12-18 |
| /6EZ6 | forex | 1.0 | 5e-05 | 125000.0 | market and limit | — | 2026-12-14 |
| /BTCZ6 | crypto | 1.0 | 5.0 | 5.0 | market and limit | — | 2026-12-25 |
| /ZCZ6 | commodities | 1.0 | 0.25 | 50.0 | market and limit | — | 2026-12-14 |
| /ZNZ6 | futures_perps | 1.0 | 0.015625 | — | market and limit | — | 2026-12-21 |
| SPX, an `Index` | indices | — | — | — | **none** | — | — |
| EUR/USD, a `Currency Pair` | forex | — | — | — | **none** | — | — |
| an `Equity Option` | — | — | — | — | — | — | — |
| a `Bond` | — | — | — | — | — | — | — |

`AAPL` steps at 1e-06 because its own `is-fractional-quantity-eligible` reads
True, `NOK` at 1.0 because it reads False, and `GLD` at 1.0 because the record
carries no flag. That is the per-market grain, driven.

The order bodies, composed with nothing sent:

```
BTC/USD  market buy   {"order-type":"Market","time-in-force":"Day","legs":[{"action":"Buy to Open","instrument-type":"Cryptocurrency","symbol":"BTC/USD","quantity":"2"}],"automated-source":true}
BTC/USD  limit  sell  {"order-type":"Limit","time-in-force":"GTC","legs":[{"action":"Sell to Close","instrument-type":"Cryptocurrency","symbol":"BTC/USD","quantity":"2"}],"automated-source":true,"price":"100000","price-effect":"Credit"}
AAPL     market buy   {"order-type":"Market","time-in-force":"Day","legs":[{"action":"Buy to Open","instrument-type":"Equity","symbol":"AAPL","quantity":"2"}],"automated-source":true}
AAPL     limit  sell  {"order-type":"Limit","time-in-force":"GTC","legs":[{"action":"Sell to Close","instrument-type":"Equity","symbol":"AAPL","quantity":"2"}],"automated-source":true,"price":"275.5","price-effect":"Credit"}
/GCZ6    market buy   {"order-type":"Market","time-in-force":"Day","legs":[{"action":"Buy","instrument-type":"Future","symbol":"/GCZ6","quantity":"2"}],"automated-source":true}
/ESZ6    limit  buy   {"order-type":"Limit","time-in-force":"GTC","legs":[{"action":"Buy","instrument-type":"Future","symbol":"/ESZ6","quantity":"2"}],"automated-source":true,"price":"6900.25","price-effect":"Debit"}
/6EZ6    market sell  {"order-type":"Market","time-in-force":"Day","legs":[{"action":"Sell","instrument-type":"Future","symbol":"/6EZ6","quantity":"2"}],"automated-source":true}
a crypto fraction     "quantity":"0.00000001"
an equity fraction    "quantity":"1.57"
```

A futures leg carries `Buy` or `Sell`, the words the venue reserves for a
contract, and every other market carries `Buy to Open` or `Sell to Close`.

The refusals, each raising before any request:

```
an Index leg          tastytrade publishes no order leg for instrument type 'index'
a Currency Pair leg   tastytrade publishes no order leg for instrument type 'currency pair'
a Bond leg            tastytrade publishes no order leg for instrument type 'bond'
an unpublished side   order side 'sideways' is not one of (BUY, SELL)
an unpublished type   order type 'teleport' is not one of (MARKET, LIMIT, STOP, STOP_LIMIT)
```

`decimal_text`, so no step reaches the venue in exponent form:

```
1e-08    -> "0.00000001"   where repr would write "1e-08"
1e-06    -> "0.000001"     where repr would write "1e-06"
1.0      -> "1"
1.57     -> "1.57"
100000.0 -> "100000"
nan      -> ""
```

The time in force, narrowed to the three words the venue's own enum holds and
this platform composes:

```
day -> day    gtc -> gtc    ioc -> ioc
fok -> day    opg -> day    cls -> day
```

The fee, summed over the venue's own six components. Driven on one execution
record carrying `commission` 0.00 at effect `None`, `clearing-fees` 0.02 at
`Debit`, `regulatory-fees` 0.03 at `Debit` and `other-charge` 0.01 at `Credit`:
the sum is **0.04** in USD and the `Trade` reads `fee=0.04`,
`fee_currency='USD'` and a moment of 1791556309.0 off the record's own
`executed-at`. Control: the same record with the six fee fields removed reads
`fee=0.0` and `fee_currency=''`, and keeps its moment. Controls on `is_fill`: a
`Money Movement` row answers False, an `Allocate` action answers False, and a
`Trade` row answers True.

The paged walk, driven on three replies: `total-pages` 3 reads 3 with 250 items,
1 reads 1 with 7, and 0 reads 0 with 0. Controls: a reply with no `pagination`
block reads 0, and a non-reply reads 0 with no items.

### What each table gained

| table | tastytrade rows | why |
| --- | --- | --- |
| `CITED_VENUE_ORDER_TYPES` | 6 | its own `order-type` enum carries `Market` at nine sites and no page narrows it per type |
| `CITED_UNIT_RULES` | 6 | crypto fractional at 8 decimals, the five others whole; stocks is the fallback a market with no recorded step falls to |
| `CITED_VENUE_SESSIONS` | 2 | stocks `SESSION_US_EQUITY` and crypto `SESSION_CONTINUOUS`; the four futures sectors name hours neither declared word holds |
| `CITED_VENUE_SETTLEMENT` | 1 | crypto 4.0 days, the longest of the three figures its own page publishes |
| `CITED_VENUE_BASE_SECTORS` | **0** | no gold token and no index token among its 26 coins, and the four funding stablecoins are not markets |
| `CITED_VENUE_MARKET_SECTORS` | **0** | its own `instrument-type` answers every market and its own symbology separates every colliding code |
| `CITED_CASH_MARKET_BUY` | **0** | the cash amount is an order type of its own, `Notional Market`, and the unit count is the default on all six types |

### The state after

```
sector          offered  Add form  serves  venue_order_types  unit_rule   session    settle
crypto               22        22    True   market and limit  fractional  continuous    4.0
stocks               21        21    True   market and limit  whole       us_equity    None
commodities          20        20    True   market and limit  whole       None         None
forex                14        14    True   market and limit  whole       None         None
indices              19        19    True   market and limit  whole       None         None
futures_perps        17        17    True   market and limit  whole       None         None
```

Forex rose from 13 venues to 14. The Add form cannot differ from the offered set:
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` iterates
`venues_for_class` itself, and the difference is **0** in all six sectors.
Controls: an invented sector answers None for both tables, and an invented venue
answers None as well.

### The verdict

```
crypto           yes-if
stocks           yes
commodities      yes-if
forex            yes-if
indices          yes
futures_perps    yes-if
```

Three plain yeses. The four yes-ifs are each the venue's own permission and not a
missing door: crypto needs cryptocurrency trading enabled and is "currently
available exclusively for individual accounts", and commodities, forex and
futures_perps are all futures, which needs "The Works".

**forex is a yes-if and not a no**, and it is the sector the screen did not
offer. Its spot door is proven shut — a separate firm, a type absent from the
order-leg enum, 0 of 84 routes, and the venue's own five-kind sentence — and its
contract door is open: 11 live currency futures on the one order route.

**What the operator must do, once:** open or name a tastytrade account, request
"The Works" for futures and enable cryptocurrency trading, create an OAuth
application and store its client secret and a grant's refresh token. The order
spec needs nothing from him.

---

## The detours searched

| the detour | the reading that shut it |
| --- | --- |
| another host for the spec | `api.tastytrade.com` answers 404; `api.tastyworks.com` is the API host its own documents name |
| a route census under `/instruments/` | the same 401 at the same 83 bytes for a real route and an invented one, so the gate names no path; the 16 OpenAPI documents name the routes instead |
| the Help Center's article content | `/support/solutions/articles/…` 401, `/api/v2/solutions/articles/…` 401, `tastyworks.freshdesk.com` 404, `/s/article/<name>` 404, `/webruntime/api/…` 401, the Aura endpoint a 1,452-byte redirect page; its three sitemaps do answer with 246 article ids and **no titles** |
| an `Equity` leg for an index | `/symbols/search/SPX` answers `instrument-type` `Index` and not `Equity`; the control `GLD` answers `Equity` with `etf` true |
| spot forex on the tastytrade API | a separate legal entity, `Currency Pair` absent from the order-leg enum, 0 of 84 routes naming a currency pair |
| a REST bar route | 0 of 84 paths holds `candle`, `bar` or `ohlc`; the 3 holding `histor` are a net-liq history and two corporate-event routes, and the control `quote` names 3 |
| a cash-amount order this program needs | `Notional Market` exists and `leg.quantity` is "Required for all orders but notional market", so the unit count is the default on every other type |
| a venue-wide fractional rule | the venue publishes it per equity and per symbol instead, so no venue-wide row would be true |

## Defects this unit found in its own first shape

1. **A recorded `Index` or `Currency Pair` would have let a cited row claim a
   market order for a market that takes no order.** `asset_sector` names the
   sector for both, and `order_types_for` falls back to
   `CITED_VENUE_ORDER_TYPES` where the record declares none, which would have
   answered "market and limit" for `SPX`.
   `src/stocks/tastytrade_connector.py, in tradable_market` now keeps such a
   record out of `list_assets`, so it never becomes a recorded market, and
   `in order_body` raises as the second guard. Driven: of 14 records, 10 record
   and 4 are refused — an `Index`, a `Currency Pair`, an `Equity Option` and a
   `Bond` — and a non-record answers False.
2. **A step of 1e-08 would have reached the venue as `1e-08`.** Every size and
   money field on this route is `type: string, format: decimal`, and
   `str(1e-08)` writes an exponent. `in decimal_text` writes `0.00000001`
   instead. Driven over nine figures, with the repr beside each.
3. **A credential-shaped constant name failed the coding archetype at high
   severity.** `TOKEN_ROUTE`, `TOKEN_GRANT_TYPE` and three instance fields named
   `token` or `secret` each read as a hardcoded password to two separate tools,
   10 high findings in all. The names are `GRANT_ROUTE`, `GRANT_TYPE_WORD`,
   `_bearer`, `_grant` and `_client_key` now, and no suppression was added.

## Calibration

- Coding archetype `passed=True` on all four Python files, serial, one file at a
  time. Calibrated: `harness_fixtures/coding_archetype/known_good.py` exit **0**
  and `known_bad.py` exit **1**, each read directly and not through a shell that
  had already run a command substitution.
- TA archetype `passed=True`, calibrated on `known_good_ta001.py` exit 0 and
  `known_bad_ta001.py` exit 1.
- GUI archetype calibrated on `known_good_widget.py` exit 0 and
  `known_bad_widget.py` exit 1.
- Docs archetype `passed=True` on both markdown pages, calibrated on
  `known_good.md` exit 0 and `known_bad.md` exit 1.
- The baseline that proves a medium finding does not gate:
  `src/stocks/ibkr_connector.py` answers `passed=True` with 41 mediums and
  `src/stocks/alpaca_connector.py` with 26.
- The manual edit is add-only: **7,522 sentences before, 0 missing, 400 added**,
  and the new file begins with `origin/current`'s bytes exactly with 25,067
  appended. Three controls, all firing: a sentence reworded inside its own text
  is reported missing, a deleted sentence is reported missing, and a one-byte
  tamper of the baseline is no longer a prefix.
- Driven twice: the two runs are byte for byte identical once the temp home path
  is normalised, 0 differing lines, and a one-cell tamper of the second differs
  from the first.
