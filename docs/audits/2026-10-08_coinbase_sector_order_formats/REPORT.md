# Coinbase Sector Order Formats

**Mode: Reference.**

This report covers issue #1192. It establishes how Coinbase requires an order to
be formatted in each of the six sectors it serves, and names the bot variant
each format demands. It builds nothing. No file under `src/`, `main.py`,
`tools/` or `dev_harness/` changed, and no page under `docs/manual/` changed.

**FALSIFICATION.** This report is wrong if a field named here is absent from
Coinbase's own published specification, if a sector's order body accepts a field
this report calls refused, if the platform's order call passes a field this
report says it omits, or if the recorded granularity changes the per-sector
counts after this date.

The variant is an output of the order format, not an input. The question each
section answers is whether the sector's published format fits the order call the
Scrumming Bot makes today, and where it does not, what the difference is.

---

## What was read

Coinbase publishes a machine-readable specification of its own trading
interface. That specification is the ground for every field named below,
because it carries the required flag, the enumerated values and the description
text for each field in one document. The narrative reference pages were read
beside it, and where the two disagree the disagreement is shown.

```
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/advanced-trade-spec.yaml
    HTTP 200, 408,110 bytes, 11,005 lines, read 2026-10-08

https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/create-order
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/get-order
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/close-position
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/preview-orders
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/get-product
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/list-products
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/futures/list-futures-positions
https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/guides/orders
https://docs.cdp.coinbase.com/llms.txt
    HTTP 200, 59,286 bytes, 437 lines, read 2026-10-08
```

No credential was sent. No account was created. No order of any kind was placed
or previewed. Every reading is of a public page.

Three pages on the venue's help host refused the request with HTTP 403 and
served no body: the stock order types page, the US derivatives order management
page, and the perpetual futures product specifications page. That refusal is a
host refusal, not a sign-in gate, and no sector rests on those three pages.

---

## How the platform names an order today

One function reaches a venue. `src/trading/bot_container.py, in
BotContainer.guarded_place_order` is the gate every live order passes, and
`src/exchange/ccxt_connector.py, in CCXTConnector.place_order` is the only site
that calls out. The call carries six values and nothing else.

```
symbol           the market
side             OrderSide.BUY or OrderSide.SELL
order_type       OrderType.MARKET, LIMIT or IOC_LIMIT
amount           a count of base units, floored onto the recorded step
price            a quote price, or None
client_order_id  a string
```

`OrderType` is declared in `src/exchange/base.py` and holds exactly three
members. The connector translates the third itself: it sends a limit order with
a time-in-force parameter of IOC, because the trading library has no
immediate-or-cancel type of its own.

The order rules the platform holds per market are also fewer than the venue
publishes. `MarketRules` in `src/exchange/base.py` carries eight fields.

```
min_amount        min_cost          amount_increment    price_increment
session           order_types       expiry_ms           settlement_days
```

`src/exchange/ccxt_connector.py, in market_rules` fills five of those eight
from one loaded market record. The sector label is written beside them by
`src/exchange/market_rules_store.py, in record_venue` under the key
`asset_class`, and read back by `recorded_classes`.

### What the trading library sends

The platform hands its six values to the library, and the library builds
Coinbase's own order body. The library's code path decides which body, so it is
read here out of the library's own module rather than described. The installed
version is ccxt 4.5.85, and the file read is its Coinbase module.

```
OrderType.MARKET, a spot market, side BUY
    order_configuration = {"market_market_ioc": {"quote_size": amount x price}}

OrderType.MARKET, every other case
    order_configuration = {"market_market_ioc": {"base_size": amount}}

OrderType.LIMIT
    order_configuration = {"limit_limit_gtc": {"base_size": amount,
                                               "limit_price": price,
                                               "post_only": post_only}}

OrderType.IOC_LIMIT
    order_configuration = {"sor_limit_ioc": {"base_size": amount,
                                             "limit_price": price}}
```

This is the first thing to record and it corrects a settled row. On a spot
market buy the library does not send the unit count the platform sized. It
multiplies that count by the price and sends the product as a quote size, which
is a cash amount. The base step the platform floored onto is not the step the
venue applies to that order. On every sell, and on every market that is not
spot, a base size is sent.

Two further fields the library sets only on request:

```
margin_type    sent only when a marginMode parameter is passed
leverage       named in the library's own documented parameters
```

`CCXTConnector.place_order` passes neither. It passes a client order id, and for
Coinbase it names the field `client_order_id`, which is the venue's own name.

---

## The venue's one endpoint

Coinbase publishes one order submission for all six sectors.

```
POST /api/v3/brokerage/orders        summary: Create Order
```

Its body is the schema named `NewOrderRequest`. Four fields are required and
nine are optional.

```
required
  client_order_id       "A unique ID provided for the order"
  product_id            "Canonical product identifier for the order. For
                         equities, use the product_id returned by the Products
                         API, not the display ticker."
  side                  BUY or SELL
  order_configuration   "the order type, size, etc"

optional
  leverage                      "The amount of leverage for the order
                                 (default is 1.0)."
  margin_type                   "Margin Type for this order (default is CROSS)."
  retail_portfolio_id           deprecated
  preview_id
  attached_order_configuration  "Only TriggerBracketGtc is eligible."
  sor_preference
  prediction_metadata
  equity_order_metadata         "Equity-specific order instructions. For equity
                                 products, use this field to select the trading
                                 session and time in force."
  cost_basis_method
```

`order_configuration` is a choice of twelve keys, and the time in force is part
of the key rather than a field beside it.

```
market_market_ioc            limit_limit_gtc           stop_limit_stop_limit_gtc
market_market_fok            limit_limit_gtd           stop_limit_stop_limit_gtd
sor_limit_ioc                limit_limit_fok           trigger_bracket_gtc
twap_limit_gtd               scaled_limit_gtc          trigger_bracket_gtd
```

Three size fields appear inside those keys, and the specification describes each
one the same way everywhere it appears.

```
base_size       "The amount of the first Asset in the Trading Pair. For
                 example, on the BTC-USD Order Book, BTC is the Base Asset."
quote_size      "The amount of the second Asset in the Trading Pair."
currency_size   "quote_size converted to the user's native currency. Empty when
                 the order is not sized in quote or when rates are unavailable."
```

The order-management guide states the rule that decides which to send:

> To buy a product, provide a quote_size or base_size; to sell, provide a
> base_size.

The granularity is published per product, not per sector, by the Get Product
endpoint.

```
base_increment   "Minimum amount base value can be increased or decreased at
                  once."
quote_increment  "Minimum amount quote value can be increased or decreased at
                  once."
base_min_size    "Minimum size that can be represented of base currency."
price_increment  "Minimum amount price can be increased or decreased at once."
```

### The venue has only four product types, and none of them is a sector

This is the structural finding, and it decides three of the six sections below.
The specification's own product type enumeration carries six values, and the
list-products endpoint accepts the same six as a query filter.

```
UNKNOWN_PRODUCT_TYPE    SPOT    FUTURE    EQUITY    OPTION_GROUP    FUTURE_GROUP
```

There is no commodities type, no forex type and no indices type. Those three
sectors are reached by reading a label off a futures product, and the label set
is published too.

```
UNKNOWN_FUTURES_ASSET_TYPE    FUTURES_ASSET_TYPE_STOCKS
FUTURES_ASSET_TYPE_CRYPTO     FUTURES_ASSET_TYPE_COMMODITIES
FUTURES_ASSET_TYPE_METALS     FUTURES_ASSET_TYPE_INDICES
FUTURES_ASSET_TYPE_ENERGY
```

Its own description says what the set is for:

> Asset type for futures/derivatives products. Other product types (Equity,
> Prediction Market) will have their own enums.

So the venue serves three order shapes, not six: a spot shape, a contract shape
and an equity shape. The six sectors the platform draws map onto those three.

---

## Crypto

Crypto is the sector the original call was written for, and it fits. The product
type is SPOT. The size is a count of the base currency on a sell, and either a
count or a cash amount on a buy. The granularity is the product's own base
increment and base minimum size, both published per product, and both of which
`market_rules` already reads. All twelve order configurations apply. The close
is the same shape as the open, because a sell takes a base size exactly as a buy
does.

```
the endpoint      POST /api/v3/brokerage/orders, product_type SPOT
the fields        client_order_id, product_id, side, order_configuration
the size field    base_size on a sell; base_size or quote_size on a buy
the granularity   base_increment per product, a fraction on 714 of 894
                  recorded rows and a whole unit on 180
the order types   all twelve configurations
time in force     carried by the configuration key; IOC, FOK, GTC, GTD
the close         the same shape, base_size
anything extra    none required; leverage and margin_type both default
```

**Verdict: the original call fits, and one correction stands beside it.** The
call reaches the venue, the fields it passes are all accepted, and no required
field is missing. The correction is the library's spot market buy: it converts
the unit count to a cash amount before sending, so the platform's own base-step
flooring does not govern that one order. The whole-unit variant already selects
on 180 of this sector's own recorded markets, which is a per-market reading and
not a sector reading.

---

## Stocks

Stocks do not fit, and the reason is not the one the settled row names. The
venue does not require a whole unit. It requires a whole unit **outside the
normal session** and permits a fraction or a cash amount inside it, subject to a
per-product permission flag. The order body carries a field for nothing else:
`equity_order_metadata`, with a session and a time in force inside it.

The create-order page states the rule in full, and the specification's own
session description states it again:

> **Equities:** Use the canonical `product_id` returned by the Products API,
> not the display ticker. Include `equity_order_metadata` to select the trading
> session and time in force. Use `market_market_ioc` with `MARKET_GFD` for
> market orders, which are supported only during the normal session. Use
> `limit_limit_gtc` with `LIMIT_GFD` or `LIMIT_GTC` for limit orders. In
> pre-market, after-hours, overnight, or multi-session trading, specify a
> positive whole-share `base_size`; `quote_size` and fractional sizing are not
> supported. Attached orders are not supported for equities.

> Equity execution session. NORMAL is regular market hours and is the only
> session that supports market orders. PRE_MARKET, AFTER_HOURS, OVERNIGHT, and
> MULTI_SESSION accept only whole-share limit orders. MULTI_SESSION spans
> multiple eligible sessions.

The two enumerations inside the metadata field:

```
equity_trading_session
  UNKNOWN_EQUITY_TRADING_SESSION      EQUITY_TRADING_SESSION_MULTI_SESSION
  EQUITY_TRADING_SESSION_NORMAL       EQUITY_TRADING_SESSION_OVERNIGHT
  EQUITY_TRADING_SESSION_AFTER_HOURS  EQUITY_TRADING_SESSION_PRE_MARKET

displayed_order_config
  UNKNOWN_DISPLAYED_ORDER_CONFIG      MARKET_GFD
  INSTANT_GFD                         EXERCISE_GFD
  LIMIT_GFD                           LIMIT_GTC
```

The size is not one shape. The venue publishes a per-product permission set that
names separate permissions for each size shape on each side, so which of three
sizings is legal is a product-level reading, not a sector-level one.

```
equity_trading_flags
  tradable                 "Whether at least one buy or sell flow is enabled"
  buy_whole_shares         "Whether buying a whole number of shares is enabled."
  buy_fractional_shares    "Whether buying a fractional number of shares is
                            enabled."
  buy_notional             "Whether buying by quote-currency amount is enabled."
  sell_whole_shares        "Whether selling a whole number of shares is
                            enabled."
  sell_fractional_shares   "Whether selling a fractional number of shares is
                            enabled."
  sell_notional            "Whether selling by quote-currency amount is
                            enabled."
```

Three more published fields decide an equity order and have no counterpart in
`MarketRules`:

```
fractionable                 "Whether the product supports fractional-share
                              trading. Check equity_trading_flags for side- and
                              size-specific permissions."
fractional_notional_min_size "Minimum quote-currency amount for a fractional or
                              notional order."
liquidate_only               "Whether the product may only be sold to reduce an
                              existing position."
```

A per-session flag sits beside them, on the trading window the venue publishes
for the day. The field is named `limit_only`, and its description reads "Whether
only limit orders are supported during this session."

```
the endpoint      POST /api/v3/brokerage/orders, product_type EQUITY
the fields        the four required, plus equity_order_metadata carrying
                  equity_trading_session and displayed_order_config
the size field    a base size, a quote size or a notional amount, chosen per
                  product off equity_trading_flags and narrowed by the session
the granularity   a whole share outside the normal session; a fraction inside
                  it where fractionable is true, floored by
                  fractional_notional_min_size
the order types   two of the twelve: market_market_ioc with MARKET_GFD, in the
                  normal session only; limit_limit_gtc with LIMIT_GFD or
                  LIMIT_GTC. Attached orders are refused
time in force     named by displayed_order_config, not by the configuration key
the close         not the same shape in every session. A sell outside the
                  normal session is a whole-share limit order, so a fractional
                  holding cannot be fully closed there
anything extra    the canonical product id, never the display ticker;
                  trading_halted refuses a new order; liquidate_only refuses a
                  buy; cost_basis_method applies to the sale
```

**Verdict: stocks demand a NEW variant, and it is neither of the two already
named.** The whole-unit variant is wrong because the venue takes a fraction in
the normal session. The cash-amount variant is wrong because a cash amount is
one of three permitted shapes and is refused outside the normal session. What
distinguishes this format is that the legal size shape is a function of two
inputs the platform holds no field for: the session the order will execute in,
and a per-product permission flag. The same market takes three different size
shapes at three different hours of the same day.

### Reachability of this sector today

The format is not reachable through the connector that places orders. The
library's Coinbase module asks the products endpoint for two product types,
FUTURE and FUTURE with a perpetual expiry type, beside the spot default. It
never asks for EQUITY, and the word equity appears zero times in that module, so
the library has no code path that can set the equity metadata field.

The platform asks for the type itself instead.
`src/exchange/ccxt_connector.py, in CCXTConnector._sector_products` reads
`VENUE_CLASS_PRODUCT_TYPES`, which names EQUITY for the stocks sector on
Coinbase, and calls the venue's public products endpoint directly. Each row it
receives is then parsed by the library's own spot-market parser, which reads no
equity product detail record, so the fractionable flag, the fractional notional
minimum and the trading flags reach no field of `MarketRules`.

One field the platform does pass is refused for this sector. The third member of
`OrderType` becomes the configuration `sor_limit_ioc`, and that is not one of
the two configurations the venue permits for an equity product.

---

## Futures and Perpetuals

The settled row holds, and the venue adds four fields to it. The product type is
FUTURE, and the expiry type separates the two halves of the sector.

```
contract_expiry_type
  UNKNOWN_CONTRACT_EXPIRY_TYPE    EXPIRING    PERPETUAL
```

The product id is not a currency pair. The venue's own example of one is a root,
a date and a venue suffix, published on both the positions endpoint and the
close endpoint:

> product_id: "The trading pair (e.g. 'BIT-28JUL23-CDE')."

The position is held in contracts, and the close is sized in contracts. Both
sentences are the venue's own.

> number_of_contracts: "The size of your position in contracts"

> size: "The amount of contracts that should be closed."

The close is a second endpoint, not the order endpoint. Its body carries three
fields, two of them required.

```
POST close position
  client_order_id   required
  product_id        required
  size              optional, "The amount of contracts that should be closed."
```

The margin mode and the leverage are published on the order body itself, and the
margin mode's own title names the sector it is for.

> MarginType reflects the margin type of an order, used for Intx Perps trades

```
margin_type   CROSS, "Cross margin applies margin to the position of the entire
              portfolio"
              ISOLATED, "Isolated margin applies margin to a single position"
leverage      "The amount of leverage for the order (default is 1.0)."
```

The contract's own shape is published per product, inside the futures product
detail record, and none of these reaches `MarketRules`:

```
contract_size          contract_root_unit     contract_expiry
contract_expiry_type   contract_code          time_to_expiry_ms
venue                  non_crypto             twenty_four_by_seven
```

A perpetual carries four more on its own detail record: an open interest, a
funding rate, a funding time and a maximum leverage. Funding is a cash flow
against an open position at a published time. It does not change the
submission, so it is recorded here and not counted as an order-format
difference.

### The two pages that disagree

The venue's pages disagree on what a base size means for a contract. The
specification describes that field identically on every one of the twelve
configurations, including the ones a contract order uses:

> base_size: "The amount of the first Asset in the Trading Pair. For example,
> on the BTC-USD Order Book, BTC is the Base Asset."

The positions endpoint and the close endpoint both say a futures size is a
contract count, quoted above. A web search returned a third version, that a
dated futures market order requires a base size as a number of contracts and
rejects a quote size. That version was not found on any page read directly, so
it is recorded as unverified and nothing here rests on it.

This report ranks on the specification for what a submission carries, because
the specification is the document that states the required flag and the field
description for the body being sent. It ranks on the positions and close
endpoints for what a position is held in, because those are the endpoints that
report and act on the position. Both readings are consistent with one reading of
the sector: the venue's step for a contract market is one contract, so a base
size of one and a contract count of one are the same number.

The recording agrees with that. Of 168 recorded rows in this sector, 115 step in
whole units and 74 carry an expiry.

```
the endpoint      POST /api/v3/brokerage/orders, product_type FUTURE
the fields        the four required, plus leverage and margin_type
the size field    a base size, which for a contract market is a contract count
                  by the step; no quote size is published for this sector
the granularity   one contract on 115 of 168 recorded rows; a fraction on 53,
                  which are perpetuals quoted finer than one contract
the order types   all twelve, and market_market_fok is published as available
                  for perpetuals only
time in force     carried by the configuration key
the close         a second endpoint, close position, whose size is a contract
                  count; or an ordinary sell with a base size
anything extra    leverage, margin_type, contract_size, contract_root_unit,
                  contract_expiry, contract_expiry_type, max_leverage, and a
                  product id of a root, a date and a venue suffix
```

**Verdict: the dated-contract variant already named, plus two fields the call
cannot set.** The size rule is the whole-unit rule, already selected per market
by `recorded_unit_rule` in `src/trading/scrumming/sizing.py`. The expiry close
is already read per order by `expiry_close_decision`. What the call cannot do is
name a leverage or a margin mode, so every order this sector takes is sent at
the venue's defaults of one times leverage and cross margin. That is a published
field the platform has no value for, and it is the same gap in the two sectors
below.

---

## Commodities

Commodities has no product type of its own, so it has no order format of its
own. The venue reaches the sector two ways, and the platform's own classifier
reads both. `src/exchange/ccxt_connector.py, in market_asset_class` answers
commodities when the market carries one of three published futures asset
labels, and again when the base asset is a precious-metal code.

```
COMMODITY_FUTURES_ASSET_TYPES
  FUTURES_ASSET_TYPE_COMMODITIES
  FUTURES_ASSET_TYPE_ENERGY
  FUTURES_ASSET_TYPE_METALS
```

So a commodities order is either a contract order or a spot order, and which
one is a per-market reading. The recording shows both shapes present. Of 25
recorded rows, 18 step in whole units and carry an expiry, which is the dated
contract shape. The other 7 step in fractions and carry no expiry, which is the
spot shape.

```
the endpoint      POST /api/v3/brokerage/orders. No product type names this
                  sector; its markets are product_type FUTURE carrying a
                  commodity asset label, or product_type SPOT on a
                  metal-backed token
the fields        the contract fields for the 18, the spot fields for the 7
the size field    a base size on both shapes
the granularity   one contract on 18 of 25 recorded rows; a fraction on 7, as
                  fine as a hundred-thousandth
the order types   all twelve
time in force     carried by the configuration key
the close         the same shape as the open on the spot markets; a contract
                  count on the contracts
anything extra    the contract fields for the 18, including an expiry; nothing
                  beyond the spot fields for the 7
```

**Verdict: no variant of its own. It demands the two shapes already named,
chosen per market.** A commodities market is a dated contract or a spot token,
and the recorded step already separates them. The sector adds no field the two
shapes above do not carry. The unset leverage and margin mode apply to the 18
contracts exactly as they apply to the futures sector.

---

## Forex

The venue publishes no forex. That is the finding, and it is a positive reading
rather than an absence of evidence, because the venue publishes a closed list of
what it does serve and forex is not on it.

```
the product type enumeration        no FOREX value
the futures asset type enumeration  no FOREX value
the specification, 11,005 lines     the string FOREX appears 0 times
the documentation index, 437 lines  the string forex appears 0 times
```

For comparison, in the same specification the string EQUITY appears 53 times,
PERPETUAL 7 times, COMMODITIES once and INDICES once. The instrument that reads
zero for forex reads non-zero for every sector the venue does serve, so the zero
is a reading and not a failure to search.

The manual already carries this, on
[`docs/manual/15-venue-compatibility.md`](../../manual/15-venue-compatibility.md):

> **There is no forex on this endpoint.** The venue refuses the word, and none
> of the types it accepts answers a currency pair.

The twenty forex rows in the recording are therefore not a venue product type.
They are produced by the platform's own classifier.
`src/exchange/ccxt_connector.py, in market_asset_class` answers forex when
`underlying_code` answers for the base asset and for the quote asset both, and
that function answers for any of the published currency codes the venue's own
currency list carries, for a precious-metal code, and for a tokenised
underlying. A spot market with a currency on each leg therefore reads as forex.

Those twenty rows carry the spot shape. Sixteen step in fractions and four in
whole units, none carries an expiry, and seventeen carry a one-dollar minimum
notional, which is the figure 866 of 894 crypto spot rows carry.

One row in the twenty carries a ten-dollar minimum notional instead. That is the
figure 94 of 168 futures rows and all 6 indices rows carry, and no crypto spot
row carries it. The classifier's forex test runs before its contract test, so a
contract whose two legs are both currency codes reads as forex rather than as a
contract. That one row is consistent with a contract read as forex, and it is a
reading of the recording rather than a venue statement.

```
the endpoint      no published answer. The venue publishes no forex product
                  type and no forex order submission
the fields        no published answer
the size field    no published answer
the granularity   no published answer. The recording's 20 rows carry the spot
                  granularity, a fraction on 16 and a whole unit on 4
the order types   no published answer
time in force     no published answer
the close         no published answer
anything extra    no published answer
```

**Verdict: no variant. The sector's markets take the crypto spot format, because
they are crypto spot markets.** This confirms from the venue's own pages what
the eleventh row of the build order concluded from the step distribution alone:
no currency-lot rule is needed, because no venue the platform connects sizes a
currency lot. The one row carrying a derivatives minimum notional is the finding
worth acting on, and it is a classifier ordering, not an order format.

---

## Indices

Indices has no product type of its own either. The venue reaches it with one
published futures asset label, and
`src/exchange/ccxt_connector.py, in market_asset_class` reads that label.

```
INDEX_FUTURES_ASSET_TYPES
  FUTURES_ASSET_TYPE_INDICES
```

So an indices order is a contract order. The recording holds six rows, and every
one of them is the perpetual half of the contract shape rather than the dated
half. All six step in fractions, five at a hundredth and one at a thousandth.
None carries an expiry. All six carry a ten-dollar minimum notional and a
one-cent price tick.

```
the endpoint      POST /api/v3/brokerage/orders. No product type names this
                  sector; its markets are product_type FUTURE carrying the
                  index asset label, with a perpetual expiry type
the fields        the four required, plus leverage and margin_type
the size field    a base size
the granularity   a fraction on all 6 recorded rows, five at a hundredth and
                  one at a thousandth; a ten-dollar minimum notional on all 6
the order types   all twelve, and market_market_fok for perpetuals
time in force     carried by the configuration key
the close         the same shape as the open, or the close position endpoint
anything extra    leverage, margin_type, max_leverage, a funding rate and a
                  funding time, and a product id naming a perpetual
```

**Verdict: no variant. It demands the contract shape already named, and the
whole-unit rule never selects on it.** Every recorded step in this sector is a
fraction, so the scrum's excess survives the size rule and the original call
fits the submission unchanged. What does not fit is the same two unset fields as
the futures sector: no leverage and no margin mode reach the body, so every
indices order is sent at one times leverage on cross margin.

---

## The recording beside the pages

The recording was read with the home directory redirected to a scratch directory
before any module under `src/` was imported, and the redirect was printed to
prove it took.

```
Path.home() after redirect:   ...\scratchpad\cbfmt\home
Path.home() after src import: ...\scratchpad\cbfmt\home
recording exists: True
CLASS_FIELD = asset_class
row count: 1146
sample row keys: amount_increment, asset_class, expiry_ms, min_amount,
                 min_cost, order_types, price_increment
```

The row counts match the figures the issue carries, and the per-sector step
distribution is the recorded granularity.

| Sector | rows | fractional step | whole step | carrying an expiry |
| --- | --- | --- | --- | --- |
| crypto | 894 | 714 | 180 | 0 |
| futures/perps | 168 | 53 | 115 | 74 |
| stocks | 33 | 25 | 8 | 8 |
| commodities | 25 | 7 | 18 | 18 |
| forex | 20 | 16 | 4 | 0 |
| indices | 6 | 6 | 0 | 0 |

The recorded granularity agrees with the published pages, because both are
per-product. The venue publishes a base increment per product and the recording
holds one step per symbol, so there is no sector-level granularity on either
side to disagree about. Three disagreements of a different kind do stand.

**The recording holds no quote step.** The venue publishes a quote increment
beside the base increment, and `market_rules` maps the venue's price increment
to one field and nothing to a quote step. On a spot market buy the library sends
a quote size, so the step the venue applies to that order is the one the
recording does not hold.

**The recording holds no contract size.** The venue publishes a contract size
and a contract root unit per futures product. `MarketRules` has no field for
either, which is what the tenth row of the build order already records as
unbuilt. The 115 whole-stepping rows in the futures sector and the 18 in
commodities are therefore sized as one base unit each, and the venue reads them
as one contract each. Those two numbers agree only while the step is one.

**The recording holds no session, on any row.** All 1,146 rows carry a session
of None and a settlement of None. The venue publishes a session for every equity
product, through its equity product detail record and its trading-window record,
and the stocks sector's size rule depends on which session the order will
execute in. So the one field the stocks format turns on is recorded as absent on
every row of that sector.

The order types field reads the same on all 1,146 rows: the string "market and
limit". That is `declared_order_types` in
`src/exchange/ccxt_connector.py` reading the library's capability map once per
venue and stamping it onto every market, so it is a venue reading and not a
product reading. The venue publishes a per-product limit-only flag and a
per-session limit-only flag, and neither reaches a recorded row.

---

## Controls on the method

The brief owes a reading on both sides. Both are reported.

**The method returns a confirmation for something already established.** The
create-order page and the specification both answer for the fields the issue
already names. The spot market buy needing a price, which the connector handles
by fetching a ticker, is confirmed by the library's own refusal text and by the
venue's rule that a buy may be sized in quote. The optional leverage and margin
type fields the issue does not name are published on the order body, and that is
the finding the control was run to be sure the method could reach.

**The method returns no published answer for a page that is absent.** An
invented documentation path for a forex order submission was requested and the
host answered HTTP 404 with no body.

```
https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/create-order-forex
    HTTP 404 Not Found
```

The host does not answer success for an invented path, so the status code is
informative here rather than meaningless. Even so, nothing in the forex section
rests on that code. It rests on quoted content: a closed product type
enumeration with no forex value, and a zero count for the string in a
specification that returns non-zero counts for every sector the venue does
serve.

A second kind of negative was also recorded. Three real pages answered HTTP 200
and carried no answer to the question asked of them. The US derivatives guide,
the perpetuals guide and the derivatives technical guide each returned a page,
and none of them states whether a futures size is a contract count or a base
unit count. Those are recorded as no published answer on those pages, not as a
missing page.

**The harness was proved able to fail.** The documentation archetype was run on
both calibration bodies.

```
harness_fixtures/docs_archetype/known_good.md    exit 0, passed True
harness_fixtures/docs_archetype/known_bad.md     exit 1, passed False
```

All eight of its tools reported available on the passing run, with none missing
and none in error: proselint, vale, structure, story, updates, cover,
scaffolding, hallucination.

---

## The variant each sector demands

| Sector | The venue's product shape | The size field | The variant the format demands | New? |
| --- | --- | --- | --- | --- |
| crypto | SPOT | a base size on a sell, a base size or a quote size on a buy | the original call, with the whole-unit variant selecting per market | no |
| stocks | EQUITY | a whole share, a fraction or a notional amount, by session and by product flag | **a session-and-permission variant** | **yes** |
| futures/perps | FUTURE, expiry type EXPIRING or PERPETUAL | a base size, one contract per step | the dated-contract variant, plus a leverage and a margin mode the call cannot set | no |
| commodities | FUTURE with a commodity asset label, or SPOT on a metal-backed token | a base size on both | the dated-contract variant on 18 of 25 rows, the original call on 7 | no |
| forex | none published | no published answer | none; its recorded markets are crypto spot markets | no |
| indices | FUTURE with the index asset label, perpetual | a base size | the original call on the submission, plus the same unset leverage and margin mode | no |

One sector demands a variant that does not exist. Three sectors share the two
shapes already named. One sector has no published format at all, and its markets
are already covered by the first row.

### The published fields the platform's call has no value for

Every one of these is published on Coinbase's order body or product record, and
no value for it exists anywhere in the call chain from
`BotContainer.guarded_place_order` to `CCXTConnector.place_order`.

```
on the order body
  leverage                      margin_type
  equity_order_metadata         attached_order_configuration
  sor_preference                preview_id
  cost_basis_method             currency_size

on the product record
  contract_size                 contract_root_unit
  quote_increment               fractionable
  fractional_notional_min_size  equity_trading_flags
  liquidate_only                trading_halted
  limit_only                    max_leverage
```

### The field the platform passes that a sector's endpoint does not accept

One, and it belongs to the stocks sector. The third member of `OrderType`
becomes the configuration `sor_limit_ioc`, and Coinbase permits an equity order
only as a market configuration with MARKET_GFD in the normal session, or as a
good-till-cancelled limit configuration with LIMIT_GFD or LIMIT_GTC. An
immediate-or-cancel limit is not on that list.

A second case is narrower than a refusal and is recorded for accuracy. On a spot
market buy the library sends a quote size, which the venue accepts for spot and
refuses for an equity order outside the normal session. The same translation that
is correct for crypto would be refused for stocks.

---

## Related pages

- [`docs/manual/15-venue-compatibility.md`](../../manual/15-venue-compatibility.md)
  — the venue table and the variant definitions this report reads against
- [`docs/manual/16-sector-exchange-product-tree.md`](../../manual/16-sector-exchange-product-tree.md)
  — the sector, venue and product levels
- [`docs/audits/2026-10-07_venue_sector_readiness_matrix/REPORT.md`](../2026-10-07_venue_sector_readiness_matrix/REPORT.md)
  — which venue reaches which sector
- [`docs/audits/2026-10-07_expiry_action_research/REPORT.md`](../2026-10-07_expiry_action_research/REPORT.md)
  — what a contract does at its expiry
