# Venue Compatibility

Reference. Every venue this platform can reach through an API, set beside the
asset classes it serves, the shape its orders take, and whether an accumulation
bot can trade on it unchanged.

A scrum sells the excess above a dollar target. That excess is an arbitrary
fraction of the held asset, so one question decides each venue: does the
fraction survive the venue's own size rule.

The index is [README.md](README.md). The connectors behind the crypto path are
described in [13-live-evidence.md](13-live-evidence.md), the screen that adds a
venue is in [08-tabs/settings.md](08-tabs/settings.md), and the per-class
fractional reading the simulator works from is in
[08-tabs/simulator.md](08-tabs/simulator.md).

No venue was contacted to write this page. Every venue fact below was read from
the publisher's own page outside this repository and handed to the page on
2026-09-24. Every tree fact carries its file and line.

## What a scrum asks of a venue

A scrum computes a size and submits it. Two steps stand between that size and
the venue: one truncates it to the venue's decimal places and refuses a size
under the venue's minimum, and one rounds it again inside the crypto connector.

```python
# src/trading/scrumming/execution.py:1581
                amount=amount,

# src/trading/bot_container.py:226
        if _min_amount > 0 and _below_min:

# src/exchange/ccxt_connector.py:1061
        amount = self._ex.amount_to_precision(symbol, amount)
```

The minimum and the decimal places come off the market record the connector
reads, held per symbol. A lookup that fails gives no minimum and eight decimal
places, so the refusal stands down.

```python
# src/trading/bot_container.py:116
        """Return ``(min_amount, min_cost, amount_precision)`` for
        ``symbol``, cached; ``(0.0, 0.0, 8)`` on any lookup failure."""
```

The broker path carries neither step. It names the size `quantity` and sends it
unchanged.

```python
# src/stocks/broker_base.py:145
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,

# src/stocks/alpaca_connector.py:176
            "qty": str(quantity),
```

Nothing in the running program builds that path. Outside its own module and the
stock window's own files, the broker connector is named once, in a docstring.

```python
# src/simulator/portfolios.py:26
"""The ``SUPPORTED_BROKERS`` key of the one broker connector, ``AlpacaConnector``."""
```

## The venues and the classes they serve

Fifteen crypto venues are offered. One has ever traded. The equity venue list
holds nine ids for eight firms, and two of those firms have no API to reach.

| Venue | Classes served | Reachable from the United States | Credential shape | Source |
| ----- | -------------- | -------------------------------- | ---------------- | ------ |
| coinbase | crypto spot; US futures products over the same API | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67`; Coinbase developer documentation, Advanced Trade US derivatives |
| kraken | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| gateio | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| mexc | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| bitfinex | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| gemini | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| bitstamp | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| cryptocom | crypto spot | no refusal recorded, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:67` |
| kucoin | crypto spot | no refusal recorded, 2026-08-28 | key, secret and passphrase | `src/exchange/ccxt_connector.py:102` |
| okx | crypto spot | no refusal recorded, 2026-08-28 | key, secret and passphrase | `src/exchange/ccxt_connector.py:102` |
| bitget | crypto spot | no refusal recorded, 2026-08-28 | key, secret and passphrase | `src/exchange/ccxt_connector.py:102` |
| binance | crypto spot | no, public endpoints refused a US address, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:113` |
| bybit | crypto spot | no, public endpoints refused a US address, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:113` |
| poloniex | crypto spot | no, the terms refuse a US account, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:119` |
| huobi | crypto spot | no, the terms refuse a US account, 2026-08-28 | key and secret | `src/exchange/ccxt_connector.py:119` |
| Alpaca | equities and exchange-traded funds, which is every commodity row this tree carries | yes, US broker | key and secret | `src/gui/main_tabs/asset_class_surface.py:33`; Alpaca fractional trading documentation, read 2026-09-24 |
| Interactive Brokers | equities, funds, futures and 100 or more currency pairs | yes, US broker | a TWS session, shape not stated by the pages read | `src/gui/main_tabs/asset_class_surface.py:33`; Interactive Brokers TWS API documentation, read 2026-09-24 |
| Schwab | equities and options, individual accounts | yes, US broker | issued on the Schwab developer portal, shape not stated by the pages read | `src/gui/main_tabs/asset_class_surface.py:33`; Schwab Trader API developer portal, read 2026-09-24 |
| tastytrade | equities, options, futures and crypto, through one API | yes, US broker | not stated by the pages read | `src/gui/main_tabs/asset_class_surface.py:33`; tastytrade API documentation, read 2026-09-24 |
| E\*TRADE | equities | yes, US broker | not stated by the pages read | `src/gui/main_tabs/asset_class_surface.py:33`; E\*TRADE developer documentation, read 2026-09-24 |
| Webull | equities | yes, US broker | not stated by the pages read | `src/gui/main_tabs/asset_class_surface.py:33`; the fractional-support table TradersPost publishes for the brokers it connects, read 2026-09-24 |
| TD Ameritrade | none reachable | no, the API was discontinued on 10 May 2024 and registrations did not carry over | none | `src/gui/main_tabs/asset_class_surface.py:33`; Charles Schwab notice of the discontinuation, read 2026-09-24 |
| Fidelity | none reachable | no retail trading API is published | none | `src/gui/main_tabs/asset_class_surface.py:33`; Fidelity, read 2026-09-24 |
| OANDA | forex | yes, CFTC-registered and NFA-regulated | a v20 REST token, shape not stated by the pages read | OANDA v20 REST API documentation, read 2026-09-24 |
| FOREX.com | forex | yes, CFTC-registered and NFA-regulated | not stated by the pages read | FOREX.com, a StoneX brand, read 2026-09-24 |
| tastyfx | forex | yes, CFTC-registered and NFA-regulated | not stated by the pages read | tastyfx, the US brand of IG, read 2026-09-24 |
| Tradovate | commodity and index futures | yes, US broker | not stated by the pages read | Tradovate, read 2026-09-24 |
| NinjaTrader | commodity and index futures, with direct access to CME Group, Eurex, ICE and Coinbase Derivatives | yes, US broker | not stated by the pages read | NinjaTrader Clearing, read 2026-09-24 |

Two things in the table come from the tree rather than from a venue. The nine
equity ids name eight firms, because one firm carries two.

```python
# src/gui/main_tabs/asset_class_surface.py:33
EQUITY_VENUES = frozenset(
    {
        "alpaca",
        "ibkr",
        "schwab",
        "tdameritrade",
        "webull",
        "tastytrade",
        "fidelity",
        "etrade",
        "interactivebrokers",
    }
)
```

Every commodity row this tree carries is a US-listed fund share, so an equity
broker serves that class. The four spot metal rows name no venue at all, and
the fund rows name a price source rather than a place to send an order.

```python
# src/trading/ata_asset_maps.py:437
METALS_SPOT: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, form=FORM_SPOT)
    for one in ("XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD")
)

# src/trading/ata_asset_maps.py:444
METALS_PHYSICAL: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one, form=FORM_ETF)
    for one in ("GLD", "SLV", "PPLT", "PALL")
)
```

## How an order names its size

A venue names an order's size in one of three ways: units of the base asset, a
share count, or a whole contract. The smallest step and the minimum are the two
figures that decide whether a scrum can run.

| Venue | How the size is named | Smallest step | Minimum | Source |
| ----- | --------------------- | ------------- | ------- | ------ |
| coinbase, spot | units of the base currency | the product's own increment field | the product's own minimum size field | Coinbase Create a new order and Get Product, quoted with their read date in [08-tabs/simulator.md](08-tabs/simulator.md) |
| coinbase, US futures | not stated by the pages read | not stated by the pages read | not stated by the pages read | Coinbase developer documentation, Advanced Trade US derivatives, read 2026-09-24 |
| the other fourteen crypto venues | units of the base currency | published per product by each venue, not stated by the pages read | published per product by each venue, not stated by the pages read | each venue's own product record |
| Alpaca | either a share quantity or a dollar amount, never both in one order | nine decimal places of a share | 1.00 USD on a buy | Alpaca fractional trading documentation, read 2026-09-24 |
| Interactive Brokers | a share or contract quantity | not stated by the pages read; a minimum price increment is published per contract | not stated by the pages read; an oversized order is refused with error 201 | Interactive Brokers TWS API order limitations and minimum increment pages, read 2026-09-24 |
| Schwab | not stated by the pages read | not stated by the pages read | not stated by the pages read | Schwab Trader API developer portal, read 2026-09-24 |
| tastytrade | not stated by the pages read | not stated by the pages read | not stated by the pages read | tastytrade API documentation, read 2026-09-24 |
| E\*TRADE | not stated by the pages read | not stated by the pages read | not stated by the pages read | E\*TRADE developer documentation, read 2026-09-24 |
| Webull | a share quantity | two decimal places of a share | not stated by the pages read | the fractional-support table TradersPost publishes for the brokers it connects, read 2026-09-24 |
| OANDA | units of the base currency | one unit, in place of a thousand-unit micro lot | one unit | OANDA v20 REST API documentation, read 2026-09-24 |
| FOREX.com, tastyfx | not stated by the pages read | not stated by the pages read | not stated by the pages read | each firm's own documentation, read 2026-09-24 |
| Tradovate, NinjaTrader | whole contracts | the contract specification of the product, not stated by the pages read | the contract specification of the product, not stated by the pages read | each product's contract specification |

A cell reading "not stated by the pages read" is a gap, not a zero. What closes
each one is named beside it: the venue's product record for a crypto step, the
firm's order specification page for a broker, and the exchange's contract
specification for a futures product.

## Whether a scrum's excess survives the size rule

A scrum's excess is an arbitrary fraction. A venue whose smallest step is
coarser than that fraction cannot carry the strategy unchanged.

Two questions decide a venue, and every row answers both with a yes or a no.
The first is whether an order can be placed over an API at all. The second is
whether the excess survives the venue's size rule. Readings taken 2026-09-24
from each venue's own published documentation, and from the fractional-support
table TradersPost publishes for the brokers it connects.

| Venue | Orders over an API | Does the excess survive | Why, and where the reading came from |
| ----- | ----------------- | ----------------------- | ------------------------------------ |
| coinbase, spot | yes | yes | nine decimal places, and the size is truncated to the product's decimal places and refused under the product's minimum before the API is called, at `src/trading/bot_container.py:226`. Coinbase developer documentation, read 2026-09-24 |
| coinbase, US futures | yes | no | a futures contract is whole, so an excess under one contract cannot be sold. Coinbase developer documentation, Advanced Trade US derivatives, read 2026-09-24 |
| kraken, kucoin, okx, gateio, bitget, mexc, bitfinex, gemini, bitstamp, cryptocom | yes | yes | nine decimal places. Each venue's own documentation, read 2026-09-24 |
| binance, bybit | yes, and the address is refused from the United States | yes | nine decimal places. Each venue's own documentation, read 2026-09-24. The refusal is a tree reading dated 2026-08-28, at `src/exchange/ccxt_connector.py:113` |
| poloniex, huobi | yes, and a United States account is restricted | yes | nine decimal places. Each venue's own documentation, read 2026-09-24. The restriction is a tree reading dated 2026-08-28, at `src/exchange/ccxt_connector.py:119` |
| Alpaca | yes | yes | nine decimal places on a share quantity. The 1.00 USD floor is published for a buy, and the tree sends a share quantity and never a dollar amount, at `src/stocks/alpaca_connector.py:176`. Alpaca fractional trading documentation, read 2026-09-24 |
| Webull | yes | yes | two decimal places on a share quantity, which is finer than one dollar on any share this fleet holds. The fractional-support table TradersPost publishes, read 2026-09-24 |
| Interactive Brokers | yes | no | a quantity order rounds down to whole shares, and a fraction is reached only by naming a cash amount. Interactive Brokers TWS API documentation, read 2026-09-24 |
| Schwab | yes | no | the Trader API places no fractional order at all. Schwab Trader API developer portal, read 2026-09-24 |
| tastytrade | yes | no | a fractional quantity is not carried for automated trading. tastytrade API documentation, read 2026-09-24 |
| E\*TRADE | yes | no | it sells no fractional share of an individual stock. E\*TRADE developer documentation, read 2026-09-24 |
| TD Ameritrade | no | no | the API closed on 10 May 2024. Charles Schwab notice of the discontinuation, read 2026-09-24 |
| Fidelity | no | no | it publishes no trading API. Fidelity, read 2026-09-24 |
| OANDA, FOREX.com, tastyfx | yes | no | they size in whole currency units, so an excess under one unit cannot be sold and an excess above it is cut to whole units. Each firm's own documentation, read 2026-09-24 |
| Tradovate, NinjaTrader | yes | no | a futures contract is whole. Each product's contract specification, read 2026-09-24 |

Two limits apply to every row of that column. The truncation and the minimum
refusal run only on the crypto path, so a broker order reaches the venue
unsized. And a market lookup that fails leaves the bot with no minimum and
eight assumed decimal places, which stands the refusal down for that symbol.

```python
# src/trading/bot_container.py:130
            fallback = (0.0, 0.0, 8)
            self._market_limits_cache[symbol] = fallback
```

## Two variants cover every venue

The verdict column above falls into two groups and no more. A venue that reads
yes needs nothing new. Every venue that reads no is served by one second shape,
not by a shape of its own.

The first variant is the bot that runs today. It names a unit count, which is
the share quantity the broker connector already sends, quoted higher up this
page. It trades crypto and Alpaca unchanged.

The second variant names a cash amount instead of a unit count. Interactive
Brokers reaches a fraction that way. Alpaca carries the same field beside its
quantity. Schwab, tastytrade and E\*TRADE take the whole-share order that shape
produces. One variant covers all five.

```python
# PROPOSED, not present. The broker contract names a quantity alone.
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float | None = None,
        notional_usd: float | None = None,
        order_type: OrderType = OrderType.MARKET,
    ) -> StockOrder:
```

Futures sit under the second variant and carry one further condition. A position
small enough that its excess is under one contract cannot be scrummed at all,
which is a reading each market answers for itself.

## Cells on this page that the 2026-09-24 readings overtake

The size table above was written from what each venue's own size pages state.
The fractional readings taken on 2026-09-24 close several of its gaps. Each
earlier cell is quoted whole, and the reading that overtakes it sits beneath.

The four broker rows of the size table:

```
| Interactive Brokers | a share or contract quantity | not stated by the pages read; a minimum price increment is published per contract | not stated by the pages read; an oversized order is refused with error 201 | Interactive Brokers TWS API order limitations and minimum increment pages, read 2026-09-24 |
| Schwab | not stated by the pages read | not stated by the pages read | not stated by the pages read | Schwab Trader API developer portal, read 2026-09-24 |
| tastytrade | not stated by the pages read | not stated by the pages read | not stated by the pages read | tastytrade API documentation, read 2026-09-24 |
| E\*TRADE, Tradier, TradeStation | not stated by the pages read | not stated by the pages read | not stated by the pages read | each firm's developer documentation, read 2026-09-24 |
```

Overtaken on 2026-09-24. Each of those brokers steps in whole shares.
Interactive Brokers rounds a quantity order down and reaches a fraction only
through a cash amount. Schwab places no fractional order over the Trader API.
tastytrade does not carry a fractional quantity for automated trading. E\*TRADE
sells no fractional share of an individual stock.

The futures and currency rows of the size table:

```
| coinbase, US futures | not stated by the pages read | not stated by the pages read | not stated by the pages read | Coinbase developer documentation, Advanced Trade US derivatives, read 2026-09-24 |
| FOREX.com, tastyfx | not stated by the pages read | not stated by the pages read | not stated by the pages read | each firm's own documentation, read 2026-09-24 |
| Tradovate, NinjaTrader | whole contracts | the contract specification of the product, not stated by the pages read | the contract specification of the product, not stated by the pages read | each product's contract specification |
```

Overtaken on 2026-09-24. FOREX.com and tastyfx size in whole currency units, as
OANDA does. A futures contract is whole, at Tradovate, at NinjaTrader and on
Coinbase's US derivatives products, so one contract is the step.

The paragraph that follows the size table:

```
A cell reading "not stated by the pages read" is a gap, not a zero. What closes
each one is named beside it: the venue's product record for a crypto step, the
firm's order specification page for a broker, and the exchange's contract
specification for a futures product.
```

Overtaken on 2026-09-24 for the broker, the currency and the futures rows. The
crypto steps are the gaps that remain, and each venue's own product record still
closes one.

The row that recorded the last venue this page could not describe:

```
One id in the equity venue list has no reading behind it.

| webull | the id sits in `EQUITY_VENUES` and no page about it was read | Webull's own developer documentation: whether it publishes a trading API, its order fields, its smallest share step and its minimum |
```

Overtaken on 2026-09-24. Webull publishes a trading API, and its share quantity
carries two decimal places, so it sits in the tables above. Every id in the
equity venue list is now described.

Tradier and TradeStation are not on this page. No reading of 2026-09-24 states
whether either carries a fractional share.

## Where each venue fact was read

Each publisher's page was opened as a document outside this repository and
handed to this page on 2026-09-24. No endpoint was called, no credential was
sent, and no account page was opened. A rule a page does not state is written as
not stated rather than filled in.

```
Coinbase          Create a new order; Get Product; Advanced Trade US derivatives
Alpaca            fractional trading documentation
Interactive Brokers  TWS API order limitations; TWS API minimum increment
Schwab            Trader API developer portal; the TD Ameritrade discontinuation notice
tastytrade        API documentation
E*TRADE           developer documentation
Webull            the fractional-support table TradersPost publishes
Fidelity          the retail product pages, which publish no trading API
OANDA             v20 REST API documentation
FOREX.com         StoneX brand pages
tastyfx           IG US brand pages
Tradovate         product and API pages
NinjaTrader       NinjaTrader Clearing exchange access pages
```

The crypto venue set, the passphrase set and the two refusal sets are readings
this repository holds, dated in the file that carries them.

```python
# src/exchange/ccxt_connector.py:109
# Date the venue facts below were last measured.
VENUE_MEASUREMENT_DATE: str = "2026-08-28"
```
