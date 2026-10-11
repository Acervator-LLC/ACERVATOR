# Fidelity — the eight connections and the six sectors

Read 2026-10-11 from Fidelity's own hosts with no credential sent, no developer
account registered, and no order previewed, placed, amended or cancelled.

Fidelity is the eighth and last broker in the exchange-by-exchange rhythm of
issue #1192, and the only one of the eight with **no order route of any kind**.
That is this unit's finding. The four sectors it does sell are fully measured
anyway, so the verdict names what is missing and not what is unknown.

## 1. The corpus, pinned before any count

| host | pages | bytes | characters of text |
| --- | --- | --- | --- |
| `www.fidelity.com` | 50 | 13,787,217 | 850,745 |
| `institutional.fidelity.com` | 1 | 153,771 | 16,621 |
| `clearingcustody.fidelity.com` | 1 | 98,688 | 10,104 |
| `capitalmarkets.fidelity.com` | 1 | 65,554 | 10,745 |
| **fidelity.com total** | **53** | **14,105,230** | **888,215** |
| `www.fidelitydigitalassets.com` | 2 | 140,093 | 10,560 |
| `developer.fil.com`, a different firm | 4 | 299,743 | 6,348 |

Two URL lists were pinned as well: `www.fidelity.com/sitemap1.xml` plus
`sitemap2.xml`, 612,098 bytes giving **3,203** unique URLs, and
`institutional.fidelity.com/app/contentSitemap.xml`, 1,759,336 bytes giving
**9,670** unique URLs.

Eleven further URLs were attempted and are recorded as absences, not as pages:
three PDF paths answering 403 at 263 bytes, two institutional paths answering 404
at their hosts' own invented-path byte counts, and six `www.fidelity.com` leaves
answering 400 at 31,888 bytes.

Two control fetches sit outside the corpus and are never counted with it:
`akoya.com` and `www.schwab.com/forex`.

## 2. Host calibration, three-way and two-sided

| probe | answer |
| --- | --- |
| a real page on `www.fidelity.com` | 200 at 218,000–582,000 bytes, with its own `<title>` |
| an invented top-level path | **403 at 243–263 bytes** |
| an invented leaf under a real directory | **400 at 31,888 bytes** |
| `/api` | 404 at 85 bytes |
| `capitalmarkets.fidelity.com`, any path | **404 at 25,655 bytes**, real-sounding and invented alike |
| `institutional.fidelity.com`, any absent path | 404 at 20,665 bytes, both |
| `developer.fil.com` | 404 at 55,108 invented, 200 at 57,967 and 58,761 real |
| `www.fidelitydigitalassets.com` | 404 at 55,230 invented, 200 at 56,601 and 83,492 real |

The middle answer is the trap this unit was warned about. `/trading/api`,
`/trading/futures`, `/trading/extended-hours-trading`, `/go/developer`,
`/about-fidelity/technology` and `/trading/trader-plus` each answer 400 at
**31,888 bytes, byte-identical to `/trading/ZZZ-NO-SUCH-LEAF-CONTROL`**. A 400
there names nothing on its own, and every absence below is grounded on a census
or a quoted sentence rather than on a status code.

**The user agent is a second trap, and it explains the manual sentence this unit
overtook.** The same home page, three probes in one minute:

| user agent | answer |
| --- | --- |
| a full browser string | **200 at 473,350 bytes** |
| none at all | **200 at 473,350 bytes** |
| the short string `Mozilla/5.0` | **403 at 370 bytes** |

So `www.fidelity.com` refuses a truncated user agent and nothing else. A reader
probing with one sees 403 on every path and concludes the host refused every
request, which is exactly what this page said before today. Every fetch in the
pinned corpus above carried a full browser string, and the three-way reading was
repeated at the end of the unit with the same byte counts.

## 3. There is no order route, and here is the proof

### 3.1 No API host exists

| host | DNS |
| --- | --- |
| `api.fidelity.com` | no record |
| `developer.fidelity.com` | no record |
| `developers.fidelity.com` | no record |
| `apis.fidelity.com` | no record |
| `www.fidelity.com` | resolves, Akamai |
| `institutional.fidelity.com` | resolves, Akamai |

### 3.2 The census over the 53 pages, matching on word boundaries

| word | count | word | count |
|---|---|---|---|
| `API` | **0** | `swagger` | **0** |
| `APIs` | **0** | `OpenAPI` | **0** |
| `OAuth` | **0** | `webhook` | **0** |
| `SDK` | **0** | `FIX` | **0** |
| `endpoint` | **0** | `programmatic` | **0** |
| `automated trading` | **0** | `application programming` | **0** |
| `algorithmic trading` | **0** | `REST` | 1, and it is "the rest" |

Positive controls on the same corpus: `Fidelity` **3,381**, `trading` **1,159**,
`ETFs` **321**, `stocks` **278**, `fractional` **118**, `limit order` **33**,
`market order` 10, `extended hours` 14, `precious metals` 52, `cryptocurrency`
44, `whole ounces` 2. An invented word names **0**.

Reword control, inside sentences and compared in binary: three `fractional`
reworded in place take the count from **118 to 115** and the invented word from
**0 to 3**, and the tampered body differs from the original.

Substring counting was rejected after it inflated two figures on this very
corpus: a case-insensitive substring count answered `API` 1 and `REST` 30, and
the hits were "capitalization" and "nearest" / "interest". Every count in this
report is word-boundary.

### 3.3 The two-sided control, on the same firm's own name

The identical instrument over Fidelity International's `developer.fil.com`, 4
pages and 6,348 characters, answers `API` **28**, `APIs` **12**, `OAuth` **1**.
The counter finds the word where it exists.

That portal then shuts itself. Quoted whole from its own API Catalog page:

> "No API documentation is currently available."

The page carries a Swagger UI module (`fidelity_swagger_ui`), which is the
control proving it would have rendered a spec had one been published. Its footer
reads "© FIL Limited 2026" — a different firm from the US broker this venue id
names.

### 3.4 The census over Fidelity's own URL lists

| list | `api` | `developer` | `oauth` | `integration-xchange` | `forex` | `futures` |
| --- | --- | --- | --- | --- | --- | --- |
| retail, 3,203 URLs | 16, all "capital" | 0 | 0 | 0 | 0 | 1 |
| institutional, 9,670 URLs | 4, three "capital" and one literature code | 0 | 0 | 0 | 0 | 1 |

Positive controls on the retail list: `trading` 631, `crypto` 146, `etf` 144,
`options` 129. An invented word names 0.

The one retail `futures` URL is a learning article,
`/learning-center/trading-investing/trading/using-futures-as-indicator`. The one
institutional `futures` URL is a managed-futures strategy paper.

### 3.5 What Fidelity offers in place of a route

Quoted whole from the one page in the whole corpus carrying the word
"developer":

> "Custody & Trading with Fidelity Digital Assets® Institutional clients can log
> in below to access the Fidelity Digital Assets® Custody and Trading Platform."
> "Trade with Fidelity Crypto® U.S. individual investors can log in and trade
> through their Fidelity Crypto® accounts."

Two doors, and both are a log-in. The "developer resources" on that page are a
token contract: "Name of Token: Fidelity Digital Dollar / Token Symbol: FIDD /
Available chain(s): Ethereum / Smart Contract Standard: ERC-20 / FIDD Mainnet
Address: 0x7C135549504245B5eAe64fc0E99Fa5ebabb8e35D", plus a GitHub repository
and an OpenZeppelin audit. `API` names **0** of that host's 10,560 characters.

### 3.6 The detours searched, and the reading that shut each one

| detour | the reading |
| --- | --- |
| a developer or API host | four candidate hostnames, **no DNS record** on any |
| an API documentation page on the retail site | `/trading/api`, `/go/developer` and `/about-fidelity/technology` each answer 400 at 31,888 bytes, byte-identical to an invented leaf |
| a machine-readable spec | `/swagger.json`, `/openapi.json` and `/.well-known/openapi.json` answer 403 at 243–263; `/api/v1/orders` answers 404 at 85 |
| Fidelity International's developer portal | a different firm, and its own catalogue reads "No API documentation is currently available." |
| Fidelity Access | data sharing only, in its own words: "Fidelity Access provides a convenient and more secure way to share your Fidelity account **data** with third-party websites and applications" |
| Akoya, the aggregation network behind it | the same data path; no order word on the page |
| Fidelity Institutional / Integration Xchange | **0** of its own 9,670 sitemap URLs name it, and the one path probed answers 404 at the same 20,665 bytes an invented path gives. Advisor-facing, behind a log-in |
| Fidelity Capital Markets | institutional, in its own words, and every path on that host answers 404 at the same 25,655 bytes |
| Fidelity Digital Assets | institutional custody behind a log-in; `API` names 0 of its 10,560 characters |
| the authenticated web application | `digital.fidelity.com` and `oltx.fidelity.com` both land on a sign-in wall |
| a capability already in this tree | ccxt 4.5.85 carries no `fidelity`, and `[e for e in ccxt.exchanges if 'fid' in e]` answers `[]` |
| a different account type | the metals desk, the crypto account and the margin upgrade are each named and none opens a route |
| an unofficial client | a third-party project drives the Fidelity Trader+ desktop application by replaying its network traffic. **Refused.** It is not a venue API |

### 3.7 The negative control, on hosts that do publish an order route

The same credential-free probe, same minute:

| host | answer |
| --- | --- |
| `apisb.etrade.com/docs/api/order/api-order-v1.html` | 200 at **686,928 bytes** |
| `docs.alpaca.markets/reference/postorder` | 200 at **824,486 bytes** |
| `developer.schwab.com/products/trader-api--individual` | 200 at **55,033 bytes** |
| `developer.webull.com/api-doc/trade_place_order` | 200 at **24,771 bytes** |

Fidelity has no such host to probe. A route that exists answers; Fidelity's
candidate hosts do not resolve.

## 4. The firms behind the products

| product | legal entity, in its own words | publishes a program route |
| --- | --- | --- |
| equities, ETFs, mutual funds, options | Fidelity Brokerage Services LLC ("FBS"), custody by National Financial Services LLC | no |
| spot crypto and FIDD | "Fidelity Digital Asset Services, LLC, which is chartered as a limited purpose trust company by the New York State Department of Financial Services to engage in virtual currency business (NMLS ID 1773897)" | no |
| physical metals | "Orders to buy and sell precious metals by customers of Fidelity Brokerage Services, LLC (FBS) are handled by National Financial Services LLC (NFS)… NFS processes precious metal orders through FideliTrade which is not affiliated with either FBS or NFS." | no |
| institutional equities, options, fixed income, FOREX | "Fidelity Capital Markets is a division of National Financial Services LLC, Member NYSE, SIPC" | no, and not for a retail account |
| UK and EU APIs | FIL Limited, `developer.fil.com` | "No API documentation is currently available." |

## 5. The product set, from four of Fidelity's own enumerations

| enumeration | what it names |
| --- | --- |
| Investment Accounts & Products page | "Mutual funds, Stocks, ETFs, Fixed income bonds & CDs, Options, Crypto, Alternative investments, Margin trading, Precious metals, International", plus IPOs and Fully Paid Lending |
| site navigation, on all 50 pages read | "Stocks, ETFs, Crypto \| Mutual Funds \| Fixed Income, Bonds & CDs \| Options \| IPOs \| Annuities" |
| Trading section's Investment Choices sub-navigation | five links: stock trading, options trading, gold-silver-platinum, international investments, investment research |
| commissions table | five product rows: Stocks, Options, ETFs, Bonds and CDs, Mutual Funds |

**Not one of the four names a futures market or a currency market.**

## 6. The six points, per sector

### 6.1 stocks

| point | the answer |
| --- | --- |
| market list | behind the log-in; the venue gives a count, "more than 7,000 US Stocks and ETFs", and names no list |
| order route | **none published** |
| order shape | a share quantity to three decimals, or a dollar amount to two; market, limit, stop loss, stop limit, trailing stop loss, trailing stop limit, plus conditional, contingent, OCO and OTOCO; day, or GTC with a "default order expiration date of 180 calendar days" |
| position and fill read | behind the log-in |
| candles | behind the log-in; `get_bars` answers `[]` |
| bot variant | "Stock Scrumming", and `VARIANT_WHOLE_UNIT` ahead of it outside regular hours |

### 6.2 crypto

| point | the answer |
| --- | --- |
| market list | five assets named on its own pages: BTC, ETH, LTC, SOL, FIDD; plus FBTC, FETH, FSOL as fund shares on the equity route |
| order route | **none published**; the ticket is inside the log-in |
| order shape | market or limit, day only, by coin amount or dollar amount, $1 minimum, published per-asset maximums, 95% cash cap |
| position and fill read | behind the log-in |
| candles | behind the log-in |
| bot variant | "Crypto Scrumming" |

### 6.3 commodities

| point | the answer |
| --- | --- |
| market list | gold, silver, platinum and palladium as coins and bullion bars, 16 products named by fine content; plus commodity ETPs on the equity route |
| order route | **a telephone**: "Call us at 800-544-6666 to buy precious metals or to learn more." |
| order shape | "Order quantity Whole ounces, or whole numbers of coins", minimum $2,500, order hours 8:00 a.m.–3:00 p.m. ET |
| position and fill read | behind the log-in |
| candles | none; the venue offers a metals-market news page and no price route |
| bot variant | `VARIANT_WHOLE_UNIT` |

### 6.4 indices

Same six points as stocks, because the market is the same object: an index ETF.
The index itself takes no order, and the index option is a product this platform
draws no sector for. Fidelity's own ETF page offers "actively managed and index
ETFs"; its zero-fee index funds are named by symbol — FNILX, FZROX, FZILX,
FZIPX, FXAIX — and a mutual fund is excluded from the equity shape by the
venue's own words.

### 6.5 forex

| point | the answer |
| --- | --- |
| market list | **none**. `forex` 3 and all three on `capitalmarkets.fidelity.com`; `FX` 0; `currency pair` 0; `spot forex` 0 |
| order route | none |
| order shape | n/a |
| position and fill read | n/a |
| candles | n/a |
| bot variant | n/a |

### 6.6 futures_perps

| point | the answer |
| --- | --- |
| market list | **none**. `futures` 26, every one prose; `perpetual` 0 |
| order route | none |
| order shape | n/a |
| position and fill read | n/a |
| candles | n/a |
| bot variant | n/a |

## 7. The ten readings, settled

### 7.1 The order body decides whether a connector may connect

It does not exist, so `src/stocks/fidelity_connector.py, in FidelityConnector.connect`
answers False with `ORDER_ROUTE_UNPUBLISHED` and `place_order` raises it. That is
Schwab's shape one step further: Schwab has an API host that answers 401 and will
not publish its fields; Fidelity has no host.

### 7.2 The fractional rule — the seventh different answer

| broker | the rule |
| --- | --- |
| Alpaca | fractional venue-wide |
| Schwab | fractional venue-wide, four decimal places |
| Interactive Brokers | the API is whole venue-wide |
| tastytrade | published per equity |
| Webull | capped at one share on both entry shapes |
| E\*TRADE | a fractional buy, and a fractional sale refused |
| **Fidelity** | **both sides at .001, regular session only** |

Quoted whole: "Fractional share quantities can be entered out to 3 decimal places
(.001) as long as the value of the order is at least $1.00. Executions will be
rounded down to the nearest .001 shares." On the sale: "any future sell orders
will need to include the whole and fractional share amounts that you want to
trade." On the hour: "Both dollar-based and fractional share orders are only
eligible for execution during normal market hours."

`CITED_UNIT_RULES` takes `FRACTIONAL_UNITS` for stocks, crypto and indices and
`WHOLE_UNITS` for commodities.

### 7.3 The fee per fill

| sector | the venue's own figure |
| --- | --- |
| stocks, indices | "$0 commissions for online US stock, ETF, and option trades", plus on every sale "an additional assessment fee that ranges from $0.01 to $0.03 per $1,000 of principal" |
| crypto | "1% of the market value of executed orders", buy and sell |
| commodities | 2.90% / 2.50% / 1.98% / 0.99% buying and 2.00% / 1.00% / 0.75% selling |

A professional tier is published too: "$0.001 per share rounded up to the nearest
$0.01 on a per order basis".

The crypto fee is a field now and was a spread before: "Transaction records for
trades executed before December 4, 2025, won't show a separate fee because the 1%
fee was previously included in the price as a spread."

### 7.4 The session rule — Fidelity moves both the type and the size

The first venue in the eight to do both, and both halves are its own words.

The type: "Fidelity will accept limit orders in the extended-hours trading
sessions; all other order types are ineligible for trading during extended-hours.
Good 'til canceled (GTC) orders are not available for extended-hours trading
sessions."

The size: "Both dollar-based and fractional share orders are only eligible for
execution during normal market hours."

`CITED_VENUE_SESSIONS` takes `SESSION_US_EQUITY` for stocks and indices, and that
one word drives both `session_unit_rule` and `session_order_types`.

Fidelity's own windows are narrower than the shared ones — "Orders for the
premarket session can be placed from 7:00 a.m. to 9:28 a.m. ET. Orders in the
after-hours session can be placed from 4:00 p.m. to 8:00 p.m. ET" — so
`src/stocks/fidelity_connector.py, in equity_session` reads its own boundaries.
Driven at six hours on one weekday:

| moment, Eastern | window | market order | fraction |
| --- | --- | --- | --- |
| 05:30 | closed | no | no |
| 07:30 | premarket | no | no |
| 09:29 | closed | no | no |
| 10:40 | regular | **yes** | **yes** |
| 18:00 | after hours | no | no |
| 22:30 | closed | no | no |

Control: a Saturday at 10:40 reads closed, and a moment that is not a number
reads closed. Second control: a continuous session never moves either reading at
18:00.

**No round-lot rule.** `odd lot` names **0** of the 888,215 characters where
`round lot` names 4, all four about how a multi-lot limit order fills.

**Two further order desks publish their own hours, and neither is a session
word.** `PRODUCT_WINDOWS` holds both and `src/stocks/fidelity_connector.py, in
order_refusal` reads them, so an order outside a desk's own published window is
refused by name rather than sized.

| desk | the published window | driven |
| --- | --- | --- |
| the crypto ticket | 1:00–24:00 Eastern | 00:30 refused, 01:30 taken, 23:30 taken |
| the metals desk | 8:00–15:00 Eastern | 07:30 refused, 09:00 taken, 14:59 taken, 15:30 refused |

Control: an equity record carries no window refusal at any of those four hours,
and a record given no moment carries none either.

### 7.5 The paged ledger

Fidelity publishes no ledger route, no page size and no continuation token.
`PUBLISHES_FILL_HISTORY` reads False and **no walk is written at all**, the
reading the Schwab unit established. A walk with no published cap reads a short
page as the end of the history, which cost Alpaca 150 fills and tastytrade 261
rows.

### 7.6 The four figures

All four are **not established**, never reported as absent. Realised profit, the
fee total, the cost basis and the unrealised figure each sit behind the log-in,
and no published record schema exists to read them from. Fidelity is the second
unestablished after Schwab, and for a different reason: Schwab has a route it
will not document, Fidelity has no route.

### 7.7 US-person eligibility

The footer of **50 of the 53 pages** reads "This is for persons in the US only."
No state is refused for any product.

The crypto page is a per-state table and the table was read, not a window: **50
of 50 states** carry their own paragraph, and every one reads that "Fidelity
Digital Assets® provides custody and trading of cryptocurrencies in Fidelity
Crypto® accounts". New York is **not** refused, unlike Schwab and Crypto.com.
Hawaii, Ohio, Arizona, Louisiana and Nevada are not refused. Control: an invented
state name answers False, so a missing paragraph would have been seen.

The only exceptions, quoted whole:

> "Fidelity Crypto® for IRAs currently isn't available in California or Oregon,
> and customers in Oregon can't buy, sell, or deposit solana (SOL). Fidelity
> Crypto® and Fidelity Crypto® for IRAs currently aren't available in Guam,
> Puerto Rico, U.S. Virgin Islands, or outside the U.S."

California and Oregon close the **IRA** and not the account, and Oregon drops one
of the five coins. Reading an IRA clause as an account refusal would have shut a
sector, which is the mistake the E\*TRADE unit caught on a mortgage clause.

Positive control on a page that does refuse a state: the same instrument finds
"Forex accounts are not available to residents of Ohio or Arizona" on Schwab's
own forex page, 200 at 451,404 bytes, where the same phrase names **0** of
Fidelity's 53 pages.

One eligibility rule is a dollar and not a place: the metals desk needs $2,500.

### 7.8 The ticker collision

Every Fidelity symbol outside the crypto ticket is a security, so `NOK` is Nokia,
`AMD` is Advanced Micro Devices and `COP` is ConocoPhillips. No currency leg
exists in any route because no route exists: `currency pair` names **0** of
888,215 characters.

The five crypto symbols are BTC, ETH, LTC, SOL and FIDD, and FIDD is the one
needing a reading: "a stablecoin pegged 1:1 to the US dollar and issued by
Fidelity Digital Assets as an ERC-20 token on the Ethereum network".
`CITED_VENUE_BASE_SECTORS` takes it as crypto, beside gemini's `USD1` and
bitfinex's `USDC`. No fidelity symbol needs `STABLECOIN_DENYLIST` in
`src/exchange/market_inspector_fetcher.py`, which denies a quote leg and not a
base.

### 7.9 Each product placed once

Six words in Fidelity's own enumeration name no sector this platform draws:
Options, Mutual funds, Fixed income bonds & CDs, Annuities, IPOs and Alternative
investments. `src/stocks/fidelity_connector.py, in order_refusal` refuses a
record naming any of the six by name, each one driven.

This unit does not over-refuse. A commodity ETP and an index ETF are equity
shares and belong in commodities and indices, the E\*TRADE reading. The physical
metals belong in commodities even though they are not securities, because the
sector is the product and not the wrapper. A mutual fund is excluded by the
venue's own words — "Fund shares are priced daily after the close of the market"
and "We do not accept limit orders for mutual funds" — and its ticket takes a
cash amount, which is `VARIANT_CASH_AMOUNT`.

### 7.10 The seven `CITED_` tables

| table | fidelity rows | the reason where it takes none |
| --- | --- | --- |
| `CITED_UNIT_RULES` | 4: crypto, stocks and indices fractional, commodities whole | forex and futures_perps have no product |
| `CITED_VENUE_ORDER_TYPES` | 4, all `ORDER_TYPES_WITH_MARKET` | the same two |
| `CITED_VENUE_SESSIONS` | 2: stocks and indices `SESSION_US_EQUITY` | crypto is 23 hours from 1 a.m. ET and the metals desk is 8:00–15:00 ET; neither is a word `SESSIONS_DECLARED` holds, and citing either would claim hours the venue does not publish |
| `CITED_VENUE_SETTLEMENT` | 2: stocks and indices at 1.0 | neither Fidelity Digital Assets nor the metals desk publishes a day count |
| `CITED_VENUE_BASE_SECTORS` | 1: `FIDD` → crypto | every other base is unambiguous |
| `CITED_VENUE_MARKET_SECTORS` | **0** | `PRODUCT_SECTORS` answers every record off its own `product` word, and no two fidelity products share a symbol across sectors |
| `CITED_CASH_MARKET_BUY` | **0** | the dollar amount is a second entry shape the operator chooses, not what a market buy becomes; the connector names the share or coin quantity on every order |

## 8. The eight connections, before and after

```
                                        before                      after
1  connector exists + registered        ABSENT                      FidelityConnector; 8 ids
2  offered under every sector served    1 of 4                      4 of 4
3  credential form                      built                       built, now under all four
4  Start press builds a connector       ABSENT, silent               the class, and a named refusal
5  market rules record on connect       ABSENT                      12 records, all 12 with a sector
6  orders carry the venue's shape       ABSENT                      the published absence, raised
7  a built variant selects              built                       built, and the rows now select
8  gate decisions log under it          built                       built, unchanged
```

Row 5 is the one row built in the data and unreachable on the screen, and the
reason is named: `MainWindow._connect_broker_for_bot` returns before
`_read_broker_markets` when the session does not open, and Fidelity's session can
never open. The 12 records are driven directly instead.

`src/stocks/broker_base.py` and `src/stocks/broker_exchange.py` take **no
change**, as with Webull and E\*TRADE. `BrokerBase.SECTORS_SERVED` is left empty
on purpose: a narrowed set would route a bot on a sector outside it down the
crypto path, and ccxt 4.5.85 carries no `fidelity`, so the bot would fail with no
sentence. `asset_class_surface.EXTRA_VENUE_CLASSES` is what narrows the screen.

## 9. The verdict, three words each

```
stocks           yes-if
crypto           yes-if
commodities      yes-if
indices          yes-if
forex            no
futures_perps    no
```

**Four yes-if and two no, and not one yes** — the only venue in the eight with
none.

**The cost of each yes-if:** an order route Fidelity publishes nowhere. Each is a
yes-if and not a no because the door exists: the operator can trade all four
sectors at Fidelity today, by hand, inside its own applications. What the operator
can do is open the three accounts; what only Fidelity can do is publish the route.

**Why each no is a no.** The venue lists no product in either sector, measured
over four of its own enumerations and two of its own URL lists, with positive
controls on the same corpora. The only `FOREX` word on any Fidelity host is an
institutional division's product list, with no spec, no onboarding and a host
that answers 404 at one byte count for every path. The only currency surface a
retail customer reaches is a SWIFT wire, in-kind, over 15 currencies, arranged by
telephone — a transfer and not a trade.

**The fullest tier.** On this venue the fullest tier is still a log-in: a
brokerage account with fractional trading enrolled, a Fidelity Crypto account,
and the metals desk, each opened once. None of the three opens a program route.

## 10. The arithmetic

Offered **1**, served **4**, difference **3** — crypto, commodities and indices.
Fidelity was the narrowest row in the tree and this unit widens it by three. The
screen over-offers nothing.

After this unit: offered **4**;
`alpaca_connector.broker_serves_sector("fidelity", …)` True on all six, so every
sector takes the broker route and reads the named refusal; of the four offered,
**0** reach an order route and **4** are refused with the venue's own absence as
the reason. Before this unit `broker_serves_sector` answered False on all six,
because `BROKER_CONNECTORS` held no `fidelity` row.

## 11. Calibration and controls

- **The drive:** **166 assertions, 166 passed, 0 failed**, home redirected, no
  venue contacted, no order placed. Run four times over the build; the three
  runs at 149 assertions were byte-identical to each other, and the fourth
  carries the 17 the window reading added.
- **The hosts, read twice, 20 minutes apart:** every byte count identical. The
  home page 200 at 473,350; the fractional page 200 at 283,440; an invented
  top-level path 403 at 263; an invented leaf 400 at 31,888; `/trading/api` and
  `/trading/futures` 400 at 31,888; `capitalmarkets.fidelity.com` 404 at 25,655
  for both a real-sounding and an invented path; `developer.fil.com/apis` 200 at
  58,762; and the E\*TRADE order reference 200 at 686,928 as the live control.
  The four API hostnames answered **no DNS record** on both readings and the
  four live hosts resolved through Akamai on both. **Nothing moved.**
- **The runtime tree was never written.** The redirected homes this unit drove
  under hold **0 files**. Control, so the zero is not the instrument's: against a
  reference file from the start of this unit, `~/.acervator_logs` shows 6 files
  newer and `~/.acervator` shows 4, and all 10 are the operator's live build
  writing `bot_state.json` and its own logs, while the scratchpad shows 198. An
  earlier form of this check used `find -newermt` with a wall-clock string and
  answered 0 on a directory written to seconds before, so that reading was
  discarded and the reference-file form replaces it.
- **Every recorded venue, before and after:** 26 venue ids × 6 sectors × 9
  readings = **1,404 cells**. **27 moved and all 27 are fidelity.** Control: a
  tampered copy of the sizing module, one unit-rule row flipped, moves exactly
  **1** cell, and the comparison names it.
- **The manual page is add-only:** 6,929 base sentences counted against
  `origin/current`, decoded as UTF-8, **0 absent**, **563 lines added and 0
  deleted**. Two-sided control: one word reworded *inside* an existing sentence
  breaks exactly **1** and the census names it, and the base compared against
  itself reports **0**.
- **The archetypes:** calibrated on their own `known_good` and `known_bad` bodies
  with exit codes read directly, not through a shell that had already run a
  command substitution — coding 0/1, docs 0/1, GUI 0/1, TA 0/1. Then run serial,
  one file at a time, on every file touched. All pass.
- **The census instrument:** word-boundary matching, after a substring count
  inflated two figures on this very corpus.
- **The corpus is pinned and printed** before any count, so no file this unit
  wrote is counted in it.
- **Controls that could not fire,** reported as unreachable rather than as
  passing: Fidelity publishes no signed-request digest of its own, so no
  signature verification is possible here; and no credential-free market route
  exists, so no live market record could be read back.

## 12. Defects this unit found in its own work before opening

1. **A drive assertion that read the wrong path.** The first drive asserted
   `market_unit_rule(None, "stocks", "fidelity", …)` and expected whole units
   outside regular hours. It answered fractional, because `market_unit_rule`
   reads `recorded.session` and the caller resolves that session:
   `BotContainer._get_market_rules` calls `session_for` and writes the answer onto
   the record. The assertion now builds the record the way that method builds it
   and drives the real resolution, which is what the order site reads.
2. **A duplicate heading on the manual page.** `### The ticker collision` already
   existed in another venue's section, and the docs archetype reported it at high
   severity as DOC005. The new heading is now `### The ticker collision on
   Fidelity`, and no existing sentence moved.
3. **Four published figures recorded with nothing reading them.**
   `PRODUCTS_WITHOUT_SECTOR`, `EQUITY_QUANTITY_DECIMALS`,
   `CRYPTO_ORDER_HOUR_OPEN` and `METAL_ORDER_HOUR_OPEN` and their closes were
   written as documentation and read by nothing, which is the dangling-constant
   shape the operator has corrected before. `order_refusal` now reads
   `PRODUCTS_WITHOUT_SECTOR` and separates a product Fidelity sells from a word
   its pages never name; `EQUITY_AMOUNT_INCREMENT` is derived from
   `EQUITY_QUANTITY_DECIMALS` so the venue's "3 decimal places" is stated once;
   and the four hour constants are read through `PRODUCT_WINDOWS` by
   `order_window`, which `order_refusal` consults. Seventeen drive assertions and
   four controls cover the new reading, taking the drive from 149 to 166.
4. **A crypto fund share would have been refused on the coin ticket's hours.**
   `order_window` first keyed on the product word alone, so FBTC, FETH and FSOL —
   crypto-sector markets that trade as equity shares — carried the Fidelity
   Crypto ticket's 1:00–24:00 Eastern window. An FBTC order at 00:30 Eastern
   would have been refused on hours that belong to another desk. It now reads
   `crypto_symbol` first, so only a coin takes the ticket's window and a fund
   share takes the equity session. Driven both ways at 00:30 Eastern: the fund
   share passes and the coin is refused.
5. **An overtaken sentence this unit corrected too widely.** The manual's "its
   host refused every request, the control included" was replaced with "the host
   refuses nothing", which is wrong: `www.fidelity.com` answers 403 at 370 bytes
   to the short user-agent string `Mozilla/5.0`, and 200 at 473,350 both to a
   full browser string and to no user agent at all. The correction now names the
   mechanism and the three byte counts, which is also the likely cause of the
   2026-09-24 reading. Found on a third re-reading of this unit's own host
   calibration, after the gate had gone green and with auto-merge disarmed first.
6. **Three published figures still have no reader, and that is named rather than
   hidden.** `CRYPTO_FILL_FEE` at 1%, `CRYPTO_CASH_SHARE_MAX` at 95% and
   `PRODUCT_HOSTS` are the venue's own mechanics recorded at the symbol a future
   order or fill route would read. No such route exists, so nothing reads them
   today. They are kept because issue #1192's reading 3 asks what each venue
   publishes per fill, and deleting the answer would lose it.

## 13. What remains, named plainly

Nothing in this tree. The absent piece belongs to Fidelity: a published order
route. Until it exists, a Fidelity bot builds its connector, reads a named
refusal on its Start press, and nothing is sent.

Two readings are adjacent and belong to other rows rather than to this venue:
`src/paper/paper_run.py` and `src/simulator/back_test.py` call
`market_unit_rule` with the rules from their own source and do not resolve the
session through `session_for` first, so the cited session row reaches Live alone —
the same shape the expiry close already has on row 5. Fidelity bots cannot start
at all, so neither surface is reachable for this venue.
