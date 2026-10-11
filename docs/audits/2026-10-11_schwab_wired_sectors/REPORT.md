# Schwab — the eight connections and the six sectors

Read 2026-10-11 from Schwab's own hosts. No credential was sent, no developer
account was registered, and no order was placed, previewed, priced, amended or
cancelled. Every reading below carries the control that decides whether it says
anything.

## 1. Which Schwab host answers, and which answer carries no information

A plain request is refused on every Schwab host. With a browser user agent the
retail pages and the filed documents answer. The control on each host is an
invented path beside a real one.

| host | a real path | an invented path | does the status name a path |
| --- | --- | --- | --- |
| `www.schwab.com` | 200, 339,131 to 675,191 bytes | 404, 360,187 bytes | yes |
| `api.schwabapi.com/trader/v1/` | 401, 161 bytes | 404, 172 bytes | yes |
| `api.schwabapi.com/marketdata/v1/` | 401, 22 bytes | 404, 22 bytes | yes |
| `disclosures.schwab.com` | 200, 244,557 to 637,505 bytes | 403, 111 bytes | yes |
| `contentdelivery.schwab.com/api/content/rtcontent/asset` | 200, 150,309 bytes | 404, 0 bytes | yes |
| `developer.schwab.com` | 200, 55,033 bytes | 200, 55,033 bytes | **no** |
| `jfk2-api-gateway.schwab.com/.../AnonymousUser/api/v1/` | 401, 83 bytes | 401, 83 bytes | **no** |

The two bottom rows are the whole difficulty of this venue. `developer.schwab.com`
serves one Angular shell for every path: `cmp` reads
`/products/trader-api--individual` and `/products/invented-api-no-such-thing-zzz`
as the same file. The content behind that shell loads from the gateway in the
last row, whose route names sit in the portal's own bundle —
`production-api-products`, `categorized-api-products`, `api-product-categories`,
`apis` — and every one answers 401 at 83 bytes, as does an invented route on the
same prefix.

**Schwab publishes its order spec on no credential-free route.** Without signing
in, the portal still publishes a sitemap of 33 pages naming **6** API products:

```
account-and-client-data   data-aggregation   trader-api--commercial
advisor-services          tax-data           trader-api--individual
```

There is no futures product, no forex product and no crypto product among the
six. The earlier reading that `/products/market-data-production` answers 200 is
the shell and not a product page: that slug is absent from the sitemap and
answers the same 55,033 bytes as an invented one.

## 2. The route census

Eighteen paths under `/trader/v1/` and ten under `/marketdata/v1/`, each
discriminated by status.

| exists, 401 | does not exist, 404 |
| --- | --- |
| `/trader/v1/accounts` | `/trader/v1/accounts/{n}/previewOrder` |
| `/trader/v1/accounts/accountNumbers` | `/trader/v1/accounts/{n}/positions` |
| `/trader/v1/accounts/{n}/orders` | `/trader/v1/accounts/{n}/balances` |
| `/trader/v1/orders` | `/trader/v1/accounts/{n}/activities` |
| `/trader/v1/accounts/{n}/orders/{id}` | `/trader/v1/accounts/{n}/watchlists` |
| `/trader/v1/accounts/{n}/transactions` | `/trader/v1/instruments` |
| `/trader/v1/accounts/{n}/transactions/{id}` | `/trader/v1/markets` |
| `/trader/v1/userPreference` | `/trader/v1/quotes` |
| `/marketdata/v1/quotes` | `/trader/v1/futures/orders` |
| `/marketdata/v1/{symbol}/quotes` | `/trader/v1/forex/orders` |
| `/marketdata/v1/chains` | `/futures/v1/orders` |
| `/marketdata/v1/expirationchain` | `/forex/v1/orders` |
| `/marketdata/v1/pricehistory` | `/crypto/v1/orders` |
| `/marketdata/v1/movers/{id}` | `/invented/v1/no-such-family` |
| `/marketdata/v1/markets` | `/trader/v1/invented-no-such-route` |
| `/marketdata/v1/markets/{id}` | `/marketdata/v1/invented-no-such-route` |
| `/marketdata/v1/instruments` | `/marketdata/v1/forex/pricehistory` |
| `/marketdata/v1/instruments/{cusip}` | `/marketdata/v1/futures/chains` |
| `/v1/oauth/authorize` | `/v1/oauth/token`, `/v1/oauth/invented-no-such-route` |

**One order route serves the whole venue**,
`POST /trader/v1/accounts/{accountNumber}/orders`.

### The reading that was the measurement and not the venue

`/marketdata/v1/futures/quotes` and `/marketdata/v1/forex/quotes` each answer
**401**, which reads like two gated data families and would have placed a futures
and a forex data route in the table above. Driven again on an invented word,
`/marketdata/v1/ZZZINVENTEDSYM/quotes` answers the **same 401 at the same 22
bytes**: that path is the single-symbol quote route and its symbol matches any
word. Neither answer names a family. The two paths that would name one,
`/marketdata/v1/forex/pricehistory` and `/marketdata/v1/futures/chains`, each
answer 404.

`POST` was never sent to the order route. A body sent to an order endpoint is an
order submission whatever its content, so the route's shape was settled by `GET`
status alone.

## 3. The products, from Schwab's own two tables

`www.schwab.com/futures/futures-markets` names ten families itself and gives
every product a **Symbol**, a **Multiplier**, a **Minimum Tick Size**, a
**Settlement** word and its **Trading Days/Hours**. The parse reads 163 rows over
**139 unique symbols**.

| family | rows | sector |
| --- | --- | --- |
| Single Stock | 55 | stocks |
| Agriculture | 22 | commodities |
| Stock Indices | 14 | indices |
| Metals | 11 | commodities |
| Energy | 9 | commodities |
| Crypto | 8 | crypto |
| Currency | 8 | forex |
| Interest Rates | 7 | no sector this platform draws |
| Softs | 5 | commodities |
| Micros | 24 | each row repeats another family's row |

Every one of the 24 Micros rows carries a symbol that also sits in another
family, and no symbol sits under Micros alone. Per sector: stocks 55,
commodities 47, indices 14, crypto 8, forex 8, Interest Rates 7, and
55 + 47 + 14 + 8 + 8 + 7 = 139.

The table declares "showing /26 rows" for Micros and renders 24, so two rows sit
behind its "View More" control and outside the served markup. That is named, not
counted.

`www.schwab.com/forex/what-is-forex` carries a table headed "Currency pairs
available at Schwab" listing **70 pairs** over **19** currency legs, against the
page's own headline "Access to over 65 currency pairs". The table declares 12
rows and renders 11.

### Contract sizes, which issue row 10 asks for

| symbol | name | multiplier | tick | settlement |
| --- | --- | --- | --- | --- |
| `/ES` | E-mini S&P 500 | $50 | 0.25 = $12.50 | Cash |
| `/MES` | Micro E-mini S&P 500 | $5 | 0.25 = $1.25 | Cash |
| `/BTC` | CME Bitcoin | $5 | 5.00 = $25.00 | Cash |
| `/MBT` | CME Micro Bitcoin | $0.10 | 5.00 = $0.50 | Cash |
| `/MGC` | Micro Gold | $10 | 0.10 = $1.00 | **Physical** |
| `/M6E` | Micro EUR/USD | $12,500 | 0.0001 = $1.25 | **Physical** |

`asset_rules` in `src/stocks/schwab_connector.py` reads the Multiplier into
`MarketRules.contract_size` and the Minimum Tick Size into `price_increment`, and
`rule_number` drops the dollar sign and the thousands separator. Driven:
`$12,500` reads 12500.0, an empty string reads None, and -1 reads None.

### A contradiction inside Schwab's own pages

Its futures FAQ reads "Charles Schwab Futures and Forex LLC doesn't allow clients
to take physical delivery of a futures contract; contracts are cash-settled." Its
product table marks **Physical** on `/MGC`, `/SIL` and all 8 Currency contracts.
Both are Schwab's own words. The reading that satisfies both is that the contract
settles physically and the firm closes the position first, which is what
`expiry_close_decision` already does.

## 4. The order shape

### The size unit

Schwab names two size units on its equity order: "Place trades in dollar or share
amounts". Its fractional-shares page sets the floor, "Own fractional shares of
most U.S.-listed stocks and ETFs for as little as $1", and its brokerage account
agreement sets the grain, "Schwab calculates the quantity, unit price, and market
price out to four decimal places if necessary". **This program composes the share
count.**

Its spot crypto buy is a cash amount, quoted whole from section 5.3 of the
Cryptocurrency Account Agreement: "When a Trade Order is entered, the notional
U.S. dollar value of the purchase or the quantity of Cryptocurrencies for the
sale, plus applicable fees, will be deducted from your Account's available
balance." That account has no order route — the phrase "application programming"
appears **0** times in its 118,303 characters, and `/crypto/v1/orders` answers
404 — so Schwab stays out of `CITED_CASH_MARKET_BUY` and
`market_buy_names_cash("AAPL", "schwab")` answers False.

Its 70 spot currency pairs trade in lots its own page sizes: "Standard lots
represent 100,000 units and mini lots represent 10,000 units", with "1,000-unit
increments, also known as 'micro lots'". Each is a whole number of units, so
`WHOLE_UNITS` holds a currency lot. **Issue row 11 needs no third member of
`UNIT_RULES`**, and Schwab is the second firm after Interactive Brokers to
document a currency market at all.

### The order types, which Schwab states per session

Quoted whole from `www.schwab.com/stocks/extended-hours-trading`:

> regular session — "Many order types and conditions are accepted, including:
> market, limit, stop-limit, all-or-none, etc."
>
> extended session — "Only limit orders are accepted."

Quoted whole from section 5.7 of the Cryptocurrency Account Agreement: "If you
place a market order, you agree to pay or receive the prevailing market price at
execution" and "If you submit a limit order, you agree to pre-fund the amount of
such limit order".

Commodities, forex, indices and futures hold no order-type row. Of the 1637 pages
Schwab's own sitemap lists, 88 name futures and 59 name forex, and the phrase
"market order" appears on none of the futures and forex pages read. That is
reported as not established, never as a refusal.

## 5. The defect this unit found and fixed

`order_types_for` reads the venue's own record first and the cited table second,
and neither carries a moment. The record `BotContainer._get_market_rules` caches
carries one answer for the whole day. So a market order into a US equity market at
18:00 ET was still composed as a market order, which Schwab's own page says it
does not accept.

`session_order_types(session, moment_s)` in `src/trading/scrumming/sizing.py` is
the sibling of `session_unit_rule`, and `market_replaces_market_order` reads it at
the order site. Driven with no venue contacted, at 10:40 ET and 18:00 ET on Monday
2026-10-12:

```
record                moment             session_order_types   replaces a market order
us_equity, market     regular 10:40 ET   None                  False
us_equity, market     after 18:00 ET     limit only            True
us_equity, market     no moment          None                  False
continuous, market    regular 10:40 ET   None                  False
continuous, market    after 18:00 ET     None                  False
continuous, market    no moment          None                  False
```

**One cell of six moved.** The two-sided control is the existing path, which must
answer the same as before:

```
REFERENCE_SCRUM_EXCESS_USD = 17.5
venue_variant(limit_only)  = the venue declares no market order
venue_variant(with_market) = no order-formatting difference

limit-only record   no moment          replaces=True
limit-only record   regular 10:40 ET   replaces=True
limit-only record   after 18:00 ET     replaces=True
market record       no moment          replaces=False
market record       regular 10:40 ET   replaces=False
market record       after 18:00 ET     replaces=True
```

A first attempt at that control read False for the limit-only record and looked
like a defect in the new code. It was the control: its record carried `min_amount`
1.0 at a price of 100, a smallest order of $100 against a reference excess of
$17.50, so `venue_variant` answered `MECHANIC_SMALLEST_ORDER_OVER_EXCESS` ahead
of `MECHANIC_LIMIT_ONLY`. The record was corrected, not the code.

`market_replaces_market_order` has one caller,
`BotContainer.guarded_place_order`, so this reaches Live and not the Paper Trader
or the Simulator, the same boundary `expiry_close_decision` already has.

## 6. The eight connections

| # | the connection | before | after |
| - | --- | --- | --- |
| 1 | a connector exists and is registered | `BROKER_CONNECTORS` held 2 ids | holds 3; `broker_connector_class("schwab")` answers `SchwabConnector` and an invented id answers None |
| 2 | offered under every sector it serves | offered under **5**, served none declared | offered under **6**, served **6**, served minus offered **0** |
| 3 | the operator can enter its credentials | the Add form matched the screen | unchanged; the difference is 0 in all six sectors |
| 4 | a Start press builds its connector | no class to build | `broker_connector_class` answers one, and `_connect_broker_for_bot` reads it |
| 5 | its market rules record on connect | no connector, no sector | 15 of 15 driven records answer, 14 carrying a sector and 1 carrying none |
| 6 | its orders carry the shape the venue publishes | `order_types_for` answered None in all 6 sectors | 2 of 6, and the other 4 are named as not established |
| 7 | a built variant selects for it | 6 of 6 built, 0 cited rules | 6 of 6 built, **6 of 6 cited unit rules** |
| 8 | its gate decisions log under it | composes per sector | unchanged, driven over all six |

### The sector each record reads, driven on one record per family

```
/ES      family=Stock Indices    sector=indices       contract_size=50.0     tick=0.25
/SAAPL   family=Single Stock     sector=stocks        contract_size=100.0    tick=0.01
/BTC     family=Crypto           sector=crypto        contract_size=5.0      tick=5.0
/MGC     family=Metals           sector=commodities   contract_size=10.0     tick=0.1
/MCL     family=Energy           sector=commodities   contract_size=100.0    tick=0.01
/MZC     family=Agriculture      sector=commodities   contract_size=5.0      tick=0.5
/KC      family=Softs            sector=commodities   contract_size=375.0    tick=0.05
/M6E     family=Currency         sector=forex         contract_size=12500.0  tick=0.0001
/ZB      family=Interest Rates   sector=None          contract_size=1000.0   tick=0.03125
EUR/USD  family=                 sector=forex
USD/NOK  family=                 sector=forex
NOK      family=                 sector=stocks
AMD      family=                 sector=stocks
COP      family=                 sector=stocks
AAPL     family=                 sector=stocks
```

Per sector: stocks 5, commodities 4, forex 3, indices 1, crypto 1, none 1.
Controls: a value that is not a record answers None with `read` False;
`futures_symbol("/ES")` True and `futures_symbol("NOK")` False;
`currency_pair_symbol("USD/NOK")` True, `currency_pair_symbol("NOK")` False and
`currency_pair_symbol("PAXG/USD")` False, because `PAXG` is in no currency leg.

### The cited tables, after

```
sector         order_types        unit_rule    session     cash_buy
commodities    None               whole        None        False
crypto         market and limit   whole        None        False
forex          None               whole        None        False
futures_perps  None               whole        None        False
indices        None               whole        None        False
stocks         market and limit   fractional   us_equity   False
```

Control: an invented venue answers None for both `order_types_for` and
`unit_rule`.

### The gate log, driven over all six sectors

```
gate/schwab/commodities/gate.log     gate/schwab/forex/gate.log
gate/schwab/crypto/gate.log          gate/schwab/futures_perps/gate.log
gate/schwab/indices/gate.log         gate/schwab/stocks/gate.log
control, an invented sector          gate/schwab/zzzinvented/gate.log
```

The home was redirected to a scratch tree on every drive, and nothing was written
into the operator's runtime tree.

## 7. The ticker collision

| code | the equity | the currency | which wins, and how the venue says so |
| --- | --- | --- | --- |
| `NOK` | Nokia, a listed ADR | the Norwegian krone, a base on `NOK/SEK` and `NOK/JPY` and a quote leg on 7 more pairs | both, and the symbol says which |
| `AMD` | Advanced Micro Devices, `/SAMD0` under Single Stock | the Armenian dram | the equity; `AMD` names 0 of the 70 pairs |
| `COP` | ConocoPhillips, `/SCOP0` under Single Stock | the Colombian peso | the equity; `COP` names 0 of the 70 pairs |
| `SGD` | none | the Singapore dollar, a leg on 4 pairs | the currency; `SGD` bases 0 Schwab equities |

`NOK` is the first code in this issue genuinely both on one venue. Schwab's own
symbology settles it with no cited row: `currency_pair_symbol` reads a currency
market only where a member of `CURRENCY_LEGS` sits on both sides of the
separator, and `futures_symbol` reads a contract only where the leading slash
sits, so a bare code can only be the equity. `CITED_VENUE_BASE_SECTORS` and
`CITED_VENUE_MARKET_SECTORS` each gain **0** Schwab rows. `STABLECOIN_DENYLIST`
in `src/exchange/market_inspector_fetcher.py` is read over a venue's own tickers,
and a broker publishes none through that path, so none of its codes touches a
Schwab symbol.

## 8. US-person eligibility

Three firms, three rules, two naming a state.

The site, on every page: "This site is designed for U.S. residents. Non-U.S.
residents are subject to country-specific restrictions."

`www.schwab.com/forex/what-is-forex`: "Forex accounts are not available to
residents of Ohio or Arizona."

The Cryptocurrency Account Agreement, 20 pages and 118,303 characters, section
1.9, quoted whole:

> "Available Only to U.S. Residents — Accounts are available exclusively to
> residents of all 50 United States except New York and Louisiana. New York and
> Louisiana State residents (as defined under applicable state law) are not
> currently eligible to open an Account. Customers residing in U.S. territories
> or foreign countries are also not eligible to open an Account."

Section 10.1 repeats it as a warranty the holder gives: "You are a U.S. resident
who is eighteen years of age or older and not a resident of New York or
Louisiana, as defined y relevant state law, or any U.S. territory."

The Futures Client Agreement names no state and no residency refusal.

**This inverts the Alpaca reading twice.** Alpaca requires a US address "within
the 50 states or Puerto Rico" and excludes no state. Schwab requires a US
resident, refuses four states across two sectors, and refuses every U.S.
territory.

### How the refusals were found, and the controls

Both sit far from the sector word. The forex refusal is in a disclosure block 302
lines below the heading that names forex; the crypto refusal is inside a numbered
section of a PDF. The reading used a window of 320 characters either side of each
match and read the pages' tables, not their lines.

Positive control on the same reader: the Forex Client Agreement, 6 pages and
38,574 characters, reads "forex" **135** times and "Agreement" **55** times.
Negative control: an invented word reads **0** in both documents. The five words
the forex agreement does not carry — Ohio, Arizona, lot, minimum, API — each read
0 on a reader proven to find what is there.

## 9. The fill ledger, and the four figures

`/trader/v1/accounts/{n}/transactions` exists and
`/trader/v1/accounts/{n}/activities` does not, so the transaction list is the only
fill ledger Schwab publishes. Its record's fields are published nowhere a
credential-free reader reaches. `SchwabConnector.PUBLISHES_FILL_HISTORY` is
therefore False, `BrokerExchange.get_my_trades` raises its own sentence, and none
of the four figures — realised profit, cost basis, the unrealised figure, the fee
total — is read for Schwab today. The paging cap and the continuation shape are
**not established** for the same reason, so no walk was written that could report
itself complete.

## 10. TD Ameritrade

| the reading | the answer |
| --- | --- |
| DNS for `developer.tdameritrade.com` | no record at all |
| `www.tdameritrade.com` | Schwab's own authorization wall |
| "tdameritrade" in Schwab's own sitemap | 0 of 1637 pages |
| "ameritrade" in Schwab's own sitemap | 0 of 1637 pages |
| control, an invented word | 0 of 1637 |
| control, "futures" | 88 of 1637 |

`tdameritrade` names no venue that exists. The id is **not removed** in this
unit: removing an id reshapes the Exchanges tab, which is issue row 15's work.
The reading sits beside the id in `src/gui/main_tabs/asset_class_surface.py`.
`ibkr` beside `interactivebrokers` is the same shape and belongs to row 16.

## 11. The arithmetic, offered minus actionable

```
sector          offered  Add form  schwab markets  offered - form
crypto               22        22               8               0
stocks               21        21     55 + the universe         0
commodities          20        20              47               0
forex                13        13              78               0
indices              19        19              14               0
futures_perps        17        17             139               0
```

The forex row read **12** before this unit and reads 13 after, and schwab is the
venue it gained. The Add form cannot differ from the offered set:
`exchange_status_rows` in `src/gui/main_tabs/settings_dialog_surface.py` iterates
`venues_for_class` itself, and the difference is 0 in all six sectors. The stocks
count is the venue's own and not this unit's: `/trader/v1/accounts` answers 401
with no token and no public route enumerates Schwab's equities.

## 12. The verdict

```
crypto           yes-if
stocks           yes-if
commodities      yes-if
forex            yes-if
indices          yes-if
futures_perps    yes-if
```

Six yes-ifs and **one cost shared by all six**. Every sector has a door: a
product list with symbols, a named firm, a filed agreement and, for five of the
six, the one order route the venue publishes. What no sector has is the order
body.

**What the operator must do, once:** register for the Trader API Individual
product on `developer.schwab.com` and read the order spec it serves. That one act
settles all six sectors.

No sector is a "no". For a "no" the door must not exist, and Schwab's own tables
list 139 contracts and 70 currency pairs. Two sectors carry a second cost: crypto
spot needs the Schwab Crypto account at Charles Schwab Premier Bank, which its own
FAQ says is not open yet and which refuses New York, Louisiana and every U.S.
territory; and forex spot needs an order interface Schwab publishes nowhere, and
refuses Ohio and Arizona.

### The detours searched, and the reading that shut each one

| detour | the reading |
| --- | --- |
| another endpoint | 18 trader paths and 10 market-data paths censused; one order route |
| another API version | `/v1/oauth/authorize` answers 401 and `/v1/oauth/invented-no-such-route` answers 404, so the prefix discriminates and no second trader version exists |
| another documentation host | 1637 retail pages name an API on 0; the 2 apparent hits are the letters inside "capital" |
| a page's script rather than its markup | the portal's bundle names its content routes and every one answers 401 at the same 83 bytes as an invented one |
| another product reaching the same market | 6 API products, none for futures, forex or crypto |
| a capability already in this tree | `ccxt` 4.5.85 carries no schwab exchange |
| a different account type | three firms were read and each one's agreement was read; none publishes an order interface the first does not |

**Control proving the census could have found a door that exists:** the same
reading finds the 8 trader routes and 10 market-data routes above, among them the
order route itself, and finds 88 futures pages and 59 forex pages where an
invented word finds 0.

## 13. Regression over every recorded venue

26 venues and 6 sectors, 156 cells, plus 44 cited base and market rows, driven
before and after with the home redirected.

| reading | lines differing |
| --- | --- |
| before, run twice from two worktrees | **0** |
| after, against before | **12**, all 12 being schwab's own 6 cells |
| every venue other than schwab | **0** |
| tampered copy, one cell changed | **2**, and the diff names the cell |

The first tampered control reported 402 differing lines for one changed cell,
because the rewrite normalised the file's line endings. The tamper was redone in
binary, one occurrence replaced and every other byte left alone, and the diff
reported 2 lines.

## 14. The manual page

```
sentences before   9,726
sentences after   10,198
gained               472
LOST                   0
control, one existing row reworded   gained 473, LOST 1, and the lost row named
```

The page is add-only, measured against
`git show origin/current:docs/manual/15-venue-compatibility.md` decoded as UTF-8.
Three of its sentences are contradicted by Schwab's own pages, and each is kept
verbatim in a blockquote under `OVERTAKEN, quoted whole:` with a `True today:`
line beneath it.

## 15. What this reading cannot show

No credential was used and no developer account was registered, so nothing above
proves Schwab accepts an order from this program. **The order body's fields were
never read**, which is why `SchwabConnector.place_order` raises instead of
composing one and why `connect` answers False with its own refusal rather than
opening a session on a shape it cannot build. No market list was read:
`/trader/v1/accounts` and every `/marketdata/v1/` route answer 401 without a
token, so the 139 contracts and the 70 pairs come from Schwab's own retail tables
and not from its API, and `list_assets` answers an empty list, which
`record_markets` keeps as the rows already recorded.
