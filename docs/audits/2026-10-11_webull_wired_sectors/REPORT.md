# Webull — the eight connections and the six sectors

Read 2026-10-11 from Webull's own hosts. No credential sent. No order placed,
previewed, priced, dry-run, amended or cancelled. No developer account and no
API application registered. Home redirected on every drive of this tree.

The venue id is `webull`. `src/stocks/webull_connector.py, in VENUE_ID` holds it
and `src/stocks/alpaca_connector.py, in BROKER_CONNECTORS` keys it.

## Contents

- [The corpus, pinned](#the-corpus-pinned)
- [The instrument, calibrated before any reading](#the-instrument-calibrated-before-any-reading)
- [The nine readings, settled](#the-nine-readings-settled)
- [The eight connections, driven](#the-eight-connections-driven)
- [The six sectors](#the-six-sectors)
- [The detours searched](#the-detours-searched)
- [Defects this unit found in its own first shape](#defects-this-unit-found-in-its-own-first-shape)
- [The arithmetic](#the-arithmetic)

---

## The corpus, pinned

Thirty-five pages of Webull's own documentation, each fetched with no
credential, printed before any count was taken. The 26 under `/apis/docs/` are
the corpus every count below is taken over.

| page | bytes |
| --- | --- |
| `apis/llms.txt` | 38,071 |
| `reference/common-order-place.md` | 57,236 |
| `reference/common-order-preview.md` | 52,150 |
| `reference/order-history.md` | 42,806 |
| `reference/order-open.md` | 40,547 |
| `reference/order-detail.md` | 39,133 |
| `reference/trade-cash-activity-by-type.md` | 24,725 |
| `reference/futures-instrument-list.md` | 20,751 |
| `reference/account-balance.md` | 19,901 |
| `reference/snapshot.md` | 19,542 |
| `reference/instrument-list.md` | 18,790 |
| `authentication/signature.md` | 16,657 |
| `reference/historical-bars.md` | 16,528 |
| `trade-api/stock.md` | 16,312 |
| `reference/account-position.md` | 16,129 |
| `reference/crypto-bars.md` | 15,713 |
| `reference/crypto-instrument-list.md` | 15,116 |
| `reference/crypto-snapshot.md` | 14,860 |
| `rate-limits.md` | 14,660 |
| `reference/futures-historical-bars.md` | 14,096 |
| `reference/common-order-cancel.md` | 11,679 |
| `reference/futures-products.md` | 11,535 |
| `reference/account-list.md` | 11,196 |
| `reference/futures-products-class.md` | 10,267 |
| `trade-api/overview.md` | 5,057 |
| `trade-api/faq.md` | 4,245 |
| `trade-api/futures.md` | 4,046 |
| `trade-api/account.md` | 3,842 |
| `authentication/token.md` | 3,560 |
| `authentication/overview.md` | 3,374 |
| `trade-api/crypto.md` | 3,305 |
| `faq.md` | 3,210 |
| `market-data-api/data-api.md` | 2,928 |
| `market-data-api/overview.md` | 2,640 |
| `about-open-api.md` | 2,055 |

Plus Webull's own public product pages, each fetched with a browser user agent
and read as text with the tags stripped: `trading-investing/futures` 14,448
characters of text, `trading-investing/index-options` 13,620,
`trading-investing/stocks` 13,181, `trading-investing/crypto` 13,053,
`trading-investing/overnight-trading` 11,946,
`trading-investing/prediction-markets` 11,645,
`help/faq/11094-Getting-Started-with-Crypto-Trading` 10,714 and `pricing`
10,612.

## The instrument, calibrated before any reading

Three calibrations, each one a control that fired.

**One.** An invented path under `/apis/docs/reference/` answers **404 with 9
bytes**; `common-order-place.md` answers **200 with 57,236**. The documentation
host answers honestly on that prefix.

**Two, and it caught a whole prefix.** Every path under
`developer.webull.com/api-doc/` answers **200 with exactly 24,771 bytes**,
invented or not, because that prefix serves a single-page shell. The `/apis/`
prefix is the one that answers per page. A status code could not tell the two
apart; a byte count could.

**Three, and it caught three pages.** `www.webull.com/help/faq/1031-…`,
`.../892-…` and `.../887` are **byte-identical** to
`www.webull.com/help/faq/99999-No-Such-Page-Xyz`, all 341,288 bytes. No verdict
was read off those three. Their subject — whether crypto is open in New York —
was settled instead on `help/faq/11094-Getting-Started-with-Crypto-Trading`,
which answers 360,446 bytes and carries its text in the served markup. A web
search had returned two pages with opposite answers on that question; the
venue's own rendered page settled it.

**Archetype calibration.** Each archetype's own `known_good` and `known_bad`
bodies, with the exit code read directly:

```
coding archetype   known_good  exit 0     known_bad  exit 1
docs archetype     known_good  exit 0     known_bad  exit 1
```

## The nine readings, settled

### 1. The order body decides whether a connector may connect

Webull is the Interactive Brokers and tastytrade shape, not the Schwab shape.
Its OpenAPI body is served to anyone: `POST /trading/orders/place`,
`operationId` "Common Order Place", 57,236 bytes, nine required fields in one
order item. So this connector composes a real body and guesses no field name.

### 2. The fractional rule, inverted a fifth time and in a new shape

Quoted whole from Webull's own Stock Trading page:

> "Only `MARKET` orders are supported for fractional trading. The quantity must
> be between 0 (exclusive) and 1 (inclusive), and the order value must be at
> least $5."

And from its own `total_cash_amount` field: "Amount must be less than the price
of 1 share." And from the same page's parameter table: "`AMOUNT` (by cash
amount, for buying less than 1 share)."

So the fraction exists only **below** one share, on both of the two entry
shapes. An order of 1.57 shares cannot be sent as 1.57. Its own instrument
profile does carry `fractionable` per equity, which is the eligibility for the
sub-one-share entry this engine's scrum arithmetic never produces. The honest
unit rule is `WHOLE_UNITS`, and carrying Alpaca's, Schwab's, Interactive
Brokers' or tastytrade's belief would have cost a refused order on every scrum.

Crypto is fractional to eight decimal places: "Crypto trading supports
quantities with up to 8 decimal places", with "Smallest tradable amount
0.00000001". Futures are whole: "For futures, only quantity orders are
supported."

### 3. The fee

Published, and read. `GET /trading/orders/get` carries
`commission.actual_commission` and every `fees[].actual_value`.
`GET /trading/orders/historical-orders/list` carries neither, so `list_fills`
reads the detail per fill, bounded at **50** reads because that route's own rate
limit is 2 requests in 2 seconds, and logs how many fills carry no fee rather
than writing a zero.

The venue's own fee schedule publishes the components: "Webull does not charge
commissions for trading stocks, ETFs and options listed on U.S. exchanges", "SEC
Fee $0.0000206 \* Total Trade Volume Sells Only", "Consolidated Audit Trail Fee
$0.000003 \* Total Trade Volume Buys & Sells", "Equity algo order types $0.0050
per share", and "Webull does charge a $0.50 per contract fee for certain index
option trades".

### 4. The order-type rule that changes with the session

Here the session changes the **size**, not the type. Quoted whole from Webull's
own Overnight Trading page:

> "You can now trade Select Stocks (whole shares only) and ETFs anytime with
> Overnight Trading."

`support_trading_session` is required on every equity order and its enum holds
three words: "NIGHT: Only supports night trading. ALL: Include extended trading
hours. CORE: Only support regular trading hours." The instrument profile carries
`overnight_trading_supported` per symbol, so the night session reaches only the
stocks it marks. `session_unit_rule` already answers whole shares outside
regular hours for a US equity session, so the rule lands where the Schwab unit
built the seam.

### 5. The paged ledger

This shape cannot report itself complete.

```
page size parameter        none published on any orders route
continuation               pagination_key, a cursor
end condition              "If absent, indicates this is the last page."
earliest start_time        2018-05-21
```

There is no cap to mis-state and no short page to misread. The route states why
a page length is never the end test: "If orders are group orders, they will be
returned together, and the number of orders returned on one page may exceed the
page_size." `list_fills` walks until the key is absent, bounded at
`ORDER_PAGES_MAX` of 100 pages, and logs the page count.

Driven: a reply with a key answers `'K2'`, a reply with three rows and no key
answers `''`, a reply with one row and a key answers `'K2'`, and a reply that is
a bare list answers `''`.

### 6. The four blank figures

| figure | the answer |
| --- | --- |
| cost basis | `cost_price` on `GET /trading/assets/positions/list` |
| the unrealised figure | `unrealized_profit_loss`, and `total_unrealized_profit_loss` on the balance |
| fee total | `commission.actual_commission` plus `fees[].actual_value` |
| realised profit | **not published** |

The fourth is a count, not a belief. Across the pinned 26-page corpus a field
named `realized…` appears **0** times; the positive control, `unrealized…`,
appears **6**. `total_day_profit_loss` is a day figure and not a realised one.

### 7. US-person eligibility

Webull is the first of the five brokers that refuses no state.

| product | the legal entity | states named |
| --- | --- | --- |
| equities | Webull Financial LLC, SEC-registered broker dealer, FINRA / SIPC / NYSE / NASDAQ / CBOE EDGX | **0** |
| futures | Webull Futures LLC, a CFTC-registered Futures Commission Merchant, NFA member | **0** |
| crypto | Webull Pay LLC, with Bakkt Crypto Solutions, LLC in three jurisdictions | **3**, and **0** refused |

Quoted whole:

> "Webull now offers live cryptocurrency trading through Webull Pay LLC. U.S.
> customers can buy, sell, and hold a wide range of digital assets, including
> Bitcoin (BTC), Ethereum (ETH), Solana (SOL), and more, directly through the
> Webull app."

> "For residents in New York, Guam and Northern Mariana Islands only: Webull Pay
> LLC has collaborated with Bakkt Crypto Solutions, LLC ("Bakkt") to provide you
> convenient access to cryptocurrency trading. Webull Pay LLC and Bakkt are
> separate entities."

> "Customers outside of New York, Guam, or the Northern Mariana Islands: Your
> crypto assets are held and safeguarded by Coinbase, a leading, regulated
> crypto service provider… Customers in New York, Guam, or the Northern Mariana
> Islands: Your crypto assets are managed by Bakkt Crypto Solutions, LLC
> ("Bakkt"), which handles both trade execution and the secure storage of your
> holdings."

> "Webull Financial LLC and Webull Pay LLC are separate entities."

> "Futures and cleared swaps trading is offered by Webull Futures LLC, a CFTC
> registered Futures Commission Merchant with the Commodity Futures Trading
> Commission (CFTC) and a Member of the National Futures Association (NFA)…
> Futures accounts are not protected by the Securities Investor Protection
> Corporation (SIPC)."

What differs in the three named jurisdictions is the provider, the maintenance
window, the day-order expiry and the floor — $1.00 minimum order in place of
$2.00 — not the door. This is the opposite of Schwab, where forex is closed to
Ohio and Arizona and crypto to New York and Louisiana. Reporting it as a refusal
would have closed three jurisdictions that are open.

**The instrument.** The window was 600 to 1,100 characters, not the 420 that
reported zero on all three of cryptocom's geo pages, and every table was read as
text after the tags were stripped. Positive control: the same instrument on
`trading-investing/crypto` found the Bakkt clause and the separate-entities
clause. Negative control: on the same page it found **0** occurrences each of
"Ohio", "Arizona", "Louisiana", "Nevada" and "Puerto Rico" while finding **3**
of "New York", so it could see a state name when one was present.

### 8. The ticker collision

Webull's own symbology decides, in two places.

```
served futures product codes          22
shaped like a US equity ticker        22   every one is three characters
carried as an order symbol             0
```

Quoted whole from the contract record's own schema: "Futures contract symbol used
in trading and market data, e.g. front-month or continuous contract code such as
ESZ5, ESmain, etc." So `MCD` is McDonald's as an equity symbol and Micro CAD/USD
only as a futures `code`; the order carries `MCDZ6` or `MCDmain`. `MET`
(MetLife), `SIL` (a silver-miners fund) and `MES` read the same way. The second
decider is `instrument_type`, required on every order and on every instrument
record, so a symbol never has to carry its sector.

`NOK` needs no row: there is no spot forex here, so the krone is not a market and
`NOK` is Nokia's ADR alone. `AMD` and `COP` read the same way. A webull crypto
symbol is one token with no separator, `BTCUSD`, and `STABLECOIN_DENYLIST` in
`src/exchange/market_inspector_fetcher.py` is read on a `base/quote` split that
such a symbol never takes.

### 9. The `CITED_` tables

| table | rows gained | why |
| --- | --- | --- |
| `CITED_UNIT_RULES` | **6** | crypto fractional, the other five whole |
| `CITED_VENUE_SESSIONS` | **6** | stocks `us_equity`, the other five `continuous` |
| `CITED_VENUE_ORDER_TYPES` | **6** | every product's own list carries a market order |
| `CITED_CASH_MARKET_BUY` | **0** | the cash amount is capped below one share |
| `CITED_VENUE_SETTLEMENT` | **0** | **3** settlement words in the corpus, all three field names on one route; an invented settlement phrase names **0** |
| `CITED_VENUE_BASE_SECTORS` | **0** | the collision is settled by `instrument_type`; the coin set is behind a credential, with **3** of "70+" named publicly |
| `CITED_VENUE_MARKET_SECTORS` | **0** | `product_class_name` answers every contract and `instrument_type` every other market |

## The eight connections, driven

Every drive ran with `HOME` and `USERPROFILE` redirected to a temp directory and
no venue contacted.

| # | the connection | driven | the control |
| --- | --- | --- | --- |
| 1 | `BROKER_CONNECTORS` | 6 ids; `broker_connector_class("webull")` answers `WebullConnector` | an invented id answers None |
| 2 | `venues_for_class` | the venue is offered in **6 of 6** sectors | an invented id is offered in **0** |
| 3 | the credential form | `known_venues` holds it; the wizard offers **26** | an invented id is not in `known_venues` |
| 4 | a Start press | `broker_serves_sector` answers True on all six | False on an invented sector and on an invented venue |
| 5 | market rules recorded | **7** rule rows written, six sectors read back | an empty asset list writes **0** rows and erases none; an invented venue reads back `{}` |
| 6 | the order shape | a body composed for all six sectors | an `OPTION` and an `EVENT` record each raise |
| 7 | a built variant | all six sectors answer a built variant and `variant_holds_market` True | an invented variant name answers False |
| 8 | the gate log | `trade/gate/webull/<sector>/gate.log` for all six, `gate_log_files` lists **6** | a sector never written is listed **0** times |

The recorded rows, read back off the recording:

```
10YV6    step=1.0    tick=0.001   size=1000.0  session=continuous  expiry=1793318400000
AAPL     step=1.0    tick=None    size=None    session=us_equity   expiry=None
BTCUSD   step=1e-08  tick=0.01    size=None    session=continuous  expiry=None   min_cost=2.0
M6EZ6    step=1.0    tick=0.0001  size=12500.0 session=continuous  expiry=1797206400000
MGCZ6    step=1.0    tick=0.1     size=10.0    session=continuous  expiry=1798502400000
MNQZ6    step=1.0    tick=0.25    size=2.0     session=continuous  expiry=1797552000000
```

The variant each one selects, driven at a real price:

```
AAPL     stocks         Whole Unit Scrumming   built  holds
BTCUSD   crypto         Crypto Scrumming       built  holds
MNQZ6    indices        Index Scrumming        built  holds
M6EZ6    forex          Forex Scrumming        built  holds
MGCZ6    commodities    Commodity Scrumming    built  holds
10YV6    futures_perps  Futures Scrumming      built  holds
```

`contract_size` is read off every contract record's own `size`, which gives row
10 of issue #1192 its second venue.

## The signature, with the venue's own proof

The algorithm is published in full: the path, then every query parameter and six
signing headers sorted by name and joined as `name=value`, then the uppercase
MD5 of the body, URL-encoded, keyed by the App Secret with `&` appended, digested
with HMAC-SHA1 and base64 encoded. Quoted whole: "`x-signature` and `x-version`
do **not** participate in signing."

Webull publishes a worked example and its answer: "If your output matches
`kvlS6opdZDhEBo5jq40nHYXaLvM=`, your implementation is correct."

```
computed by request_signature   kvlS6opdZDhEBo5jq40nHYXaLvM=
published by the venue          kvlS6opdZDhEBo5jq40nHYXaLvM=
CONTROL one wrong key byte      z43azGVxjcbnch1/8hpk6aCvKn0=   differs
CONTROL the body dropped        L1d4zL2x6UmLQ5ja7jnTOjFYjEk=   differs
```

`connect` runs that proof before it sends anything, so a signature defect is
named instead of being read as a bad credential.

## The six sectors

| point | the answer, shared by all six |
| --- | --- |
| order route | `POST /trading/orders/place` |
| order shape | one item in `new_orders`, nine required fields |
| position read | `GET /trading/assets/positions/list`, with `cost_price` and `unrealized_profit_loss` |
| fill read | `GET /trading/orders/historical-orders/list` then `GET /trading/orders/get` |
| candles | `/market-data/stocks/bars/list`, `/market-data/crypto/bars/list`, `/market-data/futures/bars/list` |
| bot variant | `VARIANT_WHOLE_UNIT` for five sectors, the crypto variant for one |

| sector | market list | verdict | the named cost |
| --- | --- | --- | --- |
| stocks | `/trading/instruments/stocks/profiles/list`, `US_STOCK` | **yes** | an individual OpenAPI application, approved in 1–2 business days |
| crypto | `/trading/instruments/crypto/profiles/list`, `US_CRYPTO` | **yes-if** | "A crypto account opened through the Webull App" |
| commodities | `/trading/instruments/futures/contracts/list`, `US_FUTURES` | **yes-if** | "A futures-enabled account (open via the Webull App if not already enabled)" |
| forex | the same contracts route | **yes-if** | the same futures permission |
| indices | the same contracts route | **yes-if** | the same futures permission |
| futures_perps | the same contracts route | **yes-if** | the same futures permission, with "Sufficient margin in your account" |

Forex is the sector the screen did not offer, and the venue names it itself. Its
own futures product navigation, quoted whole: "Nano Futures Micro Futures Equity
Index Futures **FX Futures** Metals Futures Energy Futures Interest Rates
Futures Agricultural Futures CME Crypto Futures CDE Crypto Futures". Its own
Trading API page, quoted whole: "The Futures API lets you trade futures
contracts across indices, interest rates, currencies, agriculture, metals,
energies, and crypto."

The 22 contracts Webull's own futures table serves, with their multipliers and
tick sizes, sorted into the sectors this platform draws:

| sector | count | the codes |
| --- | --- | --- |
| forex | 5 | M6E, M6A, MCD, M6B, MSF |
| commodities | 5 | MGC, SIL, MHG, MCL, MNG |
| indices | 4 | MNQ, MES, MYM, M2K |
| crypto | 4 | MBT, MET, MSL, MXP |
| the contract form alone | 4 | 10Y, 30Y, 2YY, 5YY |

5 + 5 + 4 + 4 + 4 = 22. The control: an invented product name, "Palladium",
matches **0** rows of the same table.

### What is refused rather than sized

```
instrument_type words published        5   EQUITY OPTION FUTURES CRYPTO EVENT
mapped to a sector                     3   EQUITY CRYPTO FUTURES
refused by order_body                  2   OPTION EVENT
```

`OPTION` names options and `EVENT` names Webull's own prediction market. Both
reach a real order on Webull, neither is a sector this platform draws, and
`src/stocks/webull_connector.py, in order_body` raises on both rather than
sizing one. Driven: an option symbol and an event symbol each raise, naming the
word and the three the order may carry.

The four Micro Yield contracts take `FUTURES_DEFAULT_SECTOR`, the contract form,
which **is** a sector this platform draws — the reading
`src/stocks/ibkr_connector.py, in FUTURES_FAMILY_SECTORS` already takes for the
same family. The comment posted on issue #1192 before this build called them
refused; that was wrong and is corrected here and in the manual.

## The detours searched

Before any sector could read "no", and none did.

| detour | the reading that shut it |
| --- | --- |
| a spot forex route | **0** of the 223 indexed entries names forex, FX or a currency pair; the control, "futures", names **9**. The sector's order is the currency future |
| an index order | "Index Options" is a Webull product and an option is no sector here; the sector's order is the index future |
| a second documentation host | `developer.webull.com/api-doc/` serves a shell on every path, identical bytes for an invented one; `/apis/` is the live prefix |
| a page's script rather than its markup | three help pages served the shell byte for byte; the rendered page at `help/faq/11094-…` carried the same subject in its markup |
| a market clock | the Trading API publishes none; the one trading calendar sits under the Broker API behind a separate credential |
| a fill-grain ledger | the venue publishes order-grain fills only — `filled_quantity`, `filled_price`, `filled_time` — and no execution route |
| a fee on the history route | absent; the detail route carries it, and `list_fills` reads it there |
| a cash-amount order | published, and capped below one share, so it buys a fraction and never a position |
| a different account type | the Broker API is the enterprise path and the Connect API the OAuth path; both need a registration this unit did not make |

## Defects this unit found in its own first shape

Seven, all found by driving the readers against the venue's own published reply
schemas before the pull request was opened.

1. `StockPosition` was built with `qty` and `cost_basis`; the dataclass declares
   `quantity` and no cost basis at all.
2. `StockOrder` was built with `id`, `qty` and `filled_avg_price`; the dataclass
   declares `order_id`, `quantity` and `avg_fill_price`.
3. `StockOrder.side`, `order_type` and `time_in_force` were given strings; they
   are typed enums, so `order_type_named` and `time_in_force_named` now read the
   venue's own word back into one.
4. `order_items` read `data` alone, so it answered **0** orders on
   `ORDER_ITEM_ROUTE`, whose `orders` array sits at the top level with no `data`.
   That is the one route carrying the fee.
5. `_parse_order` read the place reply through `order_items`, which answered
   nothing: that reply is flat, four ids and no nesting, so the order id was
   lost on every placement.
6. `_bars` wrote `t`, `o`, `h`, `l`, `c`, `v` and read a `bars` key.
   `broker_exchange.candle_rows` reads `timestamp`, `open`, `high`, `low`,
   `close`, `volume`, and the venue nests its candles under `result` — twice for
   the stock route. Every bar would have been dropped.
7. `fill_record` wrote `transaction_time` as a float. `broker_trade` reads it
   through `bar_epoch_ms`, which takes an ISO 8601 string alone, so every fill's
   moment read **0.0**. `iso_moment` now writes the string and `filled_time_ms`
   carries the number the connector's own window filter needs.

The last three are the same class: a fix that did not reach the field the
consumer reads. Driven after the repair, `broker_trade` answers
`fee=0.0126 currency='USD' amount=3.0 price=180.25 ts=1760000000.0`, and before
it answered `ts=0.0`.

## The arithmetic

```
venues_for_class offered webull     5    before this unit
the platform draws                  6
difference                          1    forex
control, an invented venue id       0    sectors offered

venues_for_class offers webull      6    after this unit
broker_serves_sector answers True   6
offered minus actionable            0
actionable minus offered            0
```

Before this unit `broker_serves_sector("webull", …)` answered False on all six
sectors, because `BROKER_CONNECTORS` held no `webull` row at all.

The manual edit is add-only, proved against `git show origin/current:` on
`docs/manual/15-venue-compatibility.md`, decoded as UTF-8:

```
before    420,912 bytes   7,922 sentences
after     439,213 bytes   8,241 sentences
added                       319 sentences
MISSING                       0 sentences
CONTROL A   a reword inside one sentence      MISSING 1   caught
CONTROL B   a sentence appended after a stop  MISSING 0   unchanged
BINARY      the before bytes open the after bytes, exactly
```
