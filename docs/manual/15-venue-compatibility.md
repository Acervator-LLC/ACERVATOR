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

OVERTAKEN, and the sentence above is kept as written. Three steps stand between
that size and the venue. The order gate floors the size onto the venue's own
published `amount_increment`, it refuses a size that steps under the venue's
`min_amount` or that floors to nothing, and the crypto connector rounds the
result again. The flooring runs through `sized_order`, the one function the
Simulator and the Paper Trader size with.

```python
# src/trading/bot_container.py:260
        _sized = sized_order(
            _amt, unit_rule(CLASS_CRYPTO, self.config.exchange_id), _rules
        )

# src/trading/bot_container.py:283
        if 0.0 < _sized.units < _amt:

# src/exchange/ccxt_connector.py:1128
        amount = self._ex.amount_to_precision(symbol, amount)
```

Two citations in the block below quote lines
`src/trading/bot_container.py` no longer holds at any line:
`if _min_amount > 0 and _below_min:` and the docstring naming
`(min_amount, min_cost, amount_precision)`. The block above carries the lines the
file holds today.

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
| coinbase, spot | yes | yes | nine decimal places, and the size is truncated to the product's decimal places and refused under the product's minimum before the API is called, at `src/trading/bot_container.py:264`. Coinbase developer documentation, read 2026-09-24 |
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

### 2026-09-24 - the failed-lookup half of that paragraph is repaired

The sentence above is kept as written:

> And a market lookup that fails leaves the bot with no minimum and
> eight assumed decimal places, which stands the refusal down for that symbol.

That is what the code did. The true sentence is: a market lookup that fails
leaves the bot with no minimum, which it now holds as unknown rather than as
zero, so the refusal makes no comparison instead of silently passing every
size; the bot says so on the Console, and the failure is no longer remembered,
so the next order reads the market again.

The block quoted above is replaced by the block below. The coinbase, spot row
in the table still holds: while the lookup succeeds, the truncation and the
refusal are unchanged.

`src/trading/bot_container.py` — what a failed lookup answers now

```python
        unread = MarketRules(read=False)
        ...
            # A failure is not cached: caching it left the guard blind for the
            # container's life after one transient error.
            return unread
```

The record that replaced the tuple, and the comparison the guard now calls, are
described under
[13-live-evidence.md](13-live-evidence.md).

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

The refusal quoted at the top of this page, cited there to line 226 of
`src/trading/bot_container.py`:

```
        if _min_amount > 0 and _below_min:
```

Overtaken on 2026-09-24. The guard now reads a market record rather than three
loose numbers, and the refusal it makes sits at line 236 of the same file. The
verdict table above cites the new line.

## A market answers the same question for itself

The verdict column above is per venue and was read from published pages. A
market answers the same question from the figures its own record carries, and
the Market Inspector's ticker rows draw that answer.

```python
def tradeable_answer(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
```

### One rule, three answers

A market can be traded by the built variant when the smallest order the venue
accepts costs no more than the excess a scrum submits. The smallest order is
the venue's published minimum size, ceiled onto its own size increment, valued
at the venue's own last price, and never under its minimum order cost.

| answer | drawn on the row | when |
| --- | --- | --- |
| yes | `can size a scrum` | the smallest order costs no more than the excess |
| no | `cannot size a scrum` | it costs more |
| unknown | `size rules not read` | no market record was obtained |

Unknown is a third answer and never folds into either other. `MarketRules`
carries an unpublished rule as `None` and sets `read` to False when no record
was obtained at all, so a venue that publishes nothing and a venue nobody
reached are told apart.

```python
# src/exchange/base.py:122
    ``None`` is a rule the venue did not publish, never a rule of zero, and
    ``read`` is False when no market record was obtained at all.
```

### The excess the rule measures against

The excess figure is the largest one the saved fleet produces. Every bot in it
carries the same 5 per cent scrumming interval and the highest Target Balance
is 350 dollars.

```python
# src/trading/scrumming/sizing.py
LARGEST_FLEET_TARGET_USD = 350.0
FLEET_SCRUMMING_INTERVAL_PCT = 5.0

REFERENCE_SCRUM_EXCESS_USD = scrumming_interval_usd(
    LARGEST_FLEET_TARGET_USD, FLEET_SCRUMMING_INTERVAL_PCT
)
```

The largest is the right end of the fleet, not the smallest. `cannot size a
scrum` has to mean no bot at any target this fleet carries could size one
there. Read off a copy of the saved fleet: 38 bots, one interval value, targets
from 25 to 350 dollars, and an excess from 1 dollar 25 to 17 dollars 50. A
caller that knows one bot's own interval passes it instead.

### Which venues this reaches today

Only the crypto connector loads a market table, so only its markets answer yes
or no. Every other row answers unknown until a broker connector is wired. That
matches the verdict column: no Coinbase spot product reads `cannot size a
scrum`, because its minimum order cost is one dollar on most products and ten
on ether, and both sit under the excess.

The whole-share brokers, the whole-unit currency dealers and the futures venues
that read no in the verdict column are the markets the `no` answer is for. None
of them is wired, so none is drawn today.

### What this entry overtakes on this page

Nothing. Every sentence above it stands as written, and this entry only adds
the per-market answer beside the per-venue verdict.

The answer is for the one variant that exists, the bot that names a unit count.
The second variant names a cash amount and nothing in the tree constructs it,
so the ticker rows answer for the built variant alone and the offered list is
narrowed by that answer. It widens when the second variant lands.

## 2026-09-25 - the price step and the fraction declaration

A venue publishes three order rules, not two. Beside the smallest size it will
accept and the step that size moves by, it publishes the step a price moves by.
Coinbase names that third one `quote_increment` on its own product record, and
the record a bot reads now carries it.

```python
# src/exchange/base.py:131
    min_amount: Optional[float] = None  # base units
    min_cost: Optional[float] = None  # quote units
    amount_increment: Optional[float] = None  # base units a size steps by
    price_increment: Optional[float] = None  # quote units a price steps by
    read: bool = True
```

Read off four recorded Coinbase products: bitcoin and ether step by one cent,
TE-FOOD steps by a hundredth of a cent, and a product that publishes no step at
all carries the step as absent rather than as zero.

### The price a venue books

A venue does not book the price a bot names. It moves that price to its own
nearest step and books the result, so the money an order is worth is the size
times the stepped price. The minimum order cost is now compared against that
number.

```python
# src/trading/bot_container.py:294
                # The venue books a price on its own tick, so min_cost is
                # compared against the notional at that price.
                _booked_px = _rules.price_on_tick(_px)
```

The refusal the operator reads on the Console names both figures, so a price
that moved and a price that did not are told apart.

```
PRE-FLIGHT REJECTED: SELL ETH/USD notional $0.3631 (0.0001000000 x
$3630.98000000) is below min_cost $10.0000. Priced at $3630.98000000 on a
price tick of 0.01. API not called.
```

A sub-cent market keeps its digits. A product priced at 0.0000037 dollars with a
step of a ten-millionth of a dollar reads `$0.00000370` on that line, because
every step is taken in exact decimal arithmetic and never by cutting a price to
a fixed number of places.

### Whether a market can be held in fractions

The size step already answers it, and no separate field says it again. A market
whose step is under one unit accepts a fraction of a unit; a market whose step is
a whole unit or larger takes whole units only; a market whose step the venue
never published answers neither.

```python
# src/exchange/base.py:133
    amount_increment: Optional[float] = None  # base units a size steps by
```

Read off the recorded products: bitcoin steps by a hundred-millionth and ether by
a ten-thousandth, so both take fractions. TE-FOOD and the expiring contract both
step by 1, so both take whole units only.

A field carrying the same answer a second time was written and then taken out,
because nothing in the running program read it. The reader arrives with the layer
that sizes an amount onto the step, and with the layer that picks the bot variant
a market needs. Until then the step is the answer.

### A floor of zero the venue never published

The unknown row of the three-answer table above is kept as written. It says the
unknown answer is drawn when no market record was obtained.

The true row is: the unknown answer is drawn when no market record was obtained,
and also when the venue published no size rule and no minimum order cost, because
the smallest order then costs an unknown amount rather than nothing.

A market that published nothing used to be offered as tradeable with a smallest
order of zero dollars. Zero is not a floor the venue gave; it is the figure left
over when no floor was read.

```python
# src/trading/scrumming/sizing.py:149
    if amount is None:
        return floor_usd if cost_published else None
```

A minimum cost the venue published **as** zero is a different thing, and it stays
a known floor of zero. Both were driven, and they answer differently.

| What the venue published | Smallest order | Answer |
| --- | --- | --- |
| nothing at all | not known | size rules not read |
| a minimum size alone | that size at the last price | yes or no |
| a size step alone | one step at the last price | yes or no |
| a minimum cost of zero, no size rule | zero dollars | yes |
| every rule | the larger of the two floors | yes or no |

Only the first row moves. Every market that published enough to answer still
answers, including a market whose venue published a minimum size and no step.
That matters for one venue Acervator offers: of 104 exchange classes in the
trading library, 102 publish a step-shaped size rule and 2 do not, and one of
those 2 is on the offered list.

Nothing else on this page is overtaken. The per-venue verdict column, the excess
figure and the two-variant reading all stand as written.

### The tuple this record replaced

The block under *What a scrum asks of a venue* is kept as written. It quotes a
docstring saying the lookup returns a minimum amount, a minimum cost and an
amount precision, cached, and zero, zero and eight on any lookup failure.

That tuple is gone. The bot reads a record instead, and the record holds an
unpublished rule as absent.

```python
# src/trading/bot_container.py
    async def _get_market_rules(self, symbol: str) -> "MarketRules":
        """Return the venue's published ``MarketRules`` for ``symbol``, cached,
        and an all-``None`` record when the lookup fails or the venue lists no
        such market."""
```

### Which step actually changes the size

The first sentence of *What a scrum asks of a venue* is kept as written. It says
two steps stand between the computed size and the venue, one of which truncates
the size.

Driven on the seven order readings above, the size the bot computes reaches the
connector unchanged in every one of them: 1234.56789 in and 1234.56789 out,
0.012345678912345 in and 0.012345678912345 out. The guard reads the market's
rules to refuse a size under the minimum and a notional under the minimum cost,
and it changes no size. The one place a size is stepped is the connector, at the
line quoted in that section. The docstring that said otherwise now carries the
true sentence beneath it.

### What the broker path still carries

Nothing. `src/stocks/broker_base.py` names no size rule, no price step and no
market record, and no code in the tree constructs a broker connector, so there
is nothing on that path for a rule to reach. The crypto record carries the
rules; the two order contracts stay separate.

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

## 2026-09-25 - a back-tested order obeys the venue that would execute it

The Simulator and the Paper Trader reach no venue, so they could not read a
venue's order rules. They sized every order from a two-row table of cited unit
rules instead, and that table carries one fact: whether fractions are allowed.
An order sized that way says nothing about whether the venue would take it.

The live connector already reads each market's record. It now writes what it
read, once per read, into a recording under the runtime home, and the Simulator
and the Paper Trader read the recording.

```python
# src/exchange/market_rules_store.py:28
def store_path() -> Path:
    return Path.home() / ".acervator" / STORE_NAME
```

### What the recording changes about a back test

An order's amount is floored onto the venue's own size step, and an amount under
the venue's own minimum fills nothing. Where no recording exists for the market,
the cited table still answers, and the run says which of the two sized each
order.

```python
# src/trading/scrumming/sizing.py:272
def sized_order(units: float, rule: Optional[str], rules: Any = None) -> SizedOrder:
```

### The two figures a run reports

Every fill row on a Back Test report carries a **sized by** cell reading either
`recorded venue rules` or `cited unit rule`. Every bot row carries an **orders
refused** count, and the Activity Log names the reason behind each count.

Measured on `ADA_5m_2026_coinbase`, 5,102 bars rolled to one hour, one bot at a
$350 target, sockets refused and the home redirected:

| Recorded size step | Orders filled | Orders refused | Fills on the step | Whole-unit fills |
| ------------------ | ------------- | -------------- | ----------------- | ---------------- |
| a hundredth of a unit | 21 | 710 | 21 of 21 | 0 of 21 |
| one whole unit | 20 | 709 | 20 of 20 | 20 of 20 |
| a hundredth, minimum 200 units | 0 | 25 | none to read | none to read |
| nothing recorded | 21 | 0 | not measurable | 0 of 21 |

The last row is the reading the Simulator gave before this change: amounts such
as `92.62189809510927` units, which sit on no step Coinbase publishes. The same
tape with a recorded step reads `92.61`, and with a whole-unit step reads `92`.

### Why the refusal count runs high

A fold spends what its queued tranches hold. Many of those spends buy under a
tenth of a unit, and Coinbase refuses an order that small. Those 710 orders were
previously booked as fills. A refused fold consumes no tranche, so the tranches
accumulate and a later fold fills at a legal size.

### What the recording does not yet reach

The minimum order cost is recorded and is not yet measured against a
back-tested order's notional. The live order guard already compares it, at
`src/trading/bot_container.py:305`. The live path also still sizes on the cited
fractional rule and does not floor onto the step.

OVERTAKEN, and the sentence above is kept as written. The live path floors onto
the venue's published step. `src/trading/bot_container.py:260` calls
`sized_order` at the one site every live order passes, so a recorded
`amount_increment` floors the amount, a recorded `min_amount` refuses it at
`:264`, and an amount that floors to nothing refuses at `:273`. The sized amount
reaches the VolumeGuard branch and `exchange.place_order` alike, and `min_cost` is
measured on it.

Driven on a bare host with the home redirected, every socket but loopback
refused, and an exchange stand-in that raises on every order call, an amount of
`92.62189809510927` units reaches the venue as `92.62` on a recorded hundredth
step and as `92.0` on a whole-unit step. The same amount reaches the venue
unchanged where the venue published no step. Of 10 amount-and-rule pairs driven,
**0** reach the venue larger than they were handed and **0** submit where they
previously refused.

A market whose venue published no step is not sized and is not refused on that
ground. `0.0 < _sized.units < _amt` guards the assignment, which refuses a larger
amount whatever answers it.

## 2026-09-25 - every venue set beside every other, and the verdict per venue

This page already answers one question per venue: does a scrum's excess survive
the venue's own size rule. That is one of five things the bot needs. This entry
adds the other four, sets all five side by side, and closes with a single yes or
no per venue.

Nothing above this heading is deleted or reworded. Two cells are overtaken and
both are quoted whole under *What this entry overtakes and what it corrects*.

### What the bot as written requires of a venue

Five requirements, each read off the tree. A venue meeting all five is traded by
the bot that exists today, with no variant.

```
1  a connector the running program constructs
   src/exchange/ccxt_connector.py:284   CCXTConnector, 30 importing sites
   src/stocks/broker_base.py:108        BrokerBase, no caller

2  an order whose size is a count of base units
   src/exchange/base.py:299   place_order(symbol, side, order_type, amount, price, ...)

3  a market order, a limit order, and a limit order carried immediate-or-cancel
   src/exchange/base.py:30    OrderType MARKET, LIMIT, IOC_LIMIT

4  a size rule the record can hold, and a smallest order under the excess
   src/trading/scrumming/sizing.py:272   sized_order

5  a market record the connector can read
   src/exchange/ccxt_connector.py:245    market_rules
```

### Whether Acervator itself can reach a venue today

The reachability column higher up this page answers whether the venue accepts a
United States account. This one answers a different question: does the running
program hold code that submits an order there.

| Venue | Class | A connector the program constructs | What was measured |
| ----- | ----- | ---------------------------------- | ----------------- |
| the fifteen crypto ids | crypto | yes, one connector serves all fifteen | `git grep` finds 30 sites importing the crypto connector |
| Alpaca | stocks | no | the one broker connector is imported by nothing |
| Interactive Brokers, Schwab, tastytrade, E\*TRADE, Webull, TD Ameritrade, Fidelity | stocks | no | no module names any of the seven |
| OANDA, FOREX.com, tastyfx | forex | no | no venue list holds a forex id |
| Tradovate, NinjaTrader | futures | no | no venue list holds a futures id |

Two searches over the git index give that column, and the second is the control
for the first.

```
git grep -n alpaca_connector -- src/ main.py tools/
  -> src/stocks/alpaca_connector.py:2, its own docstring, and nothing else

git grep -n broker_base -- src/ main.py tools/
  -> src/stocks/alpaca_connector.py:14, and the module's own docstring

control, the same command on the crypto connector
git grep -n ccxt_connector -- src/ main.py tools/
  -> 30 sites, one of them importing it under an alias
```

The equities order path is a contract with no caller. A venue served only by
that path cannot be traded today whatever its own rules allow, and that is the
reason every stocks row above reads no.

### Every venue's order shape, set side by side

One order, two contracts, and the differences are visible in one table. The
crypto contract names an amount and hands it to the trading library, which
translates to each venue's own endpoint. The broker contract names a quantity
and posts it as JSON.

| | Crypto, the fifteen ids | Alpaca, the one broker | Interactive Brokers, Schwab, tastytrade, E\*TRADE | OANDA, FOREX.com, tastyfx | Tradovate, NinjaTrader |
| --- | --- | --- | --- | --- | --- |
| What an order must carry | symbol, side, type, amount, optional price, optional client order id | symbol, side, quantity, type, time in force, optional limit and stop prices | not stated by the pages read | not stated by the pages read | not stated by the pages read |
| Size named as | a count of base units | a share count, sent as a string | a share count | a count of currency units | a whole contract count |
| Price named as | a float moved to the venue's own tick | a string, only on a limit or stop order | a per-contract minimum increment | not stated by the pages read | the product's own tick |
| Order types the tree sends | market, limit, limit with immediate-or-cancel | market, limit, stop, stop limit, trailing stop are declared; nothing sends one | none, no connector exists | none, no connector exists | none, no connector exists |
| How it is submitted | the library's own create-order call | a POST to the broker's orders endpoint | not reached | not reached | not reached |
| Where it is read | `src/exchange/base.py:299` | `src/stocks/alpaca_connector.py:180` | this page's venue table | this page's venue table | this page's venue table |

Three differences the crypto path already absorbs per venue, and each is a line
in one connector rather than a variant.

```
src/exchange/ccxt_connector.py:1169   the client-order-id field name per venue
                                      coinbase   client_order_id
                                      binance    newClientOrderId
                                      kraken     userref
                                      every other  clientOrderId

src/exchange/ccxt_connector.py:1183   no venue carries an immediate-or-cancel
                                      type, so it is sent as a limit order
                                      carrying timeInForce IOC

src/exchange/ccxt_connector.py:1132   a spot market buy on Coinbase needs a
                                      price, so a ticker is fetched first
```

### The order types each crypto venue declares

The trading library publishes a capability map per exchange class. Read as
installed, with every socket refused and no venue contacted, it answers which
order shapes each of the fifteen offered venues declares.

| Venue | market order | limit order | market buy by cash amount | market sell by cash amount |
| ----- | ------------ | ----------- | ------------------------- | -------------------------- |
| binance | yes | yes | yes | yes |
| bitfinex | yes | yes | not declared | not declared |
| bitget | yes | yes | yes | no |
| bitstamp | yes | yes | not declared | not declared |
| bybit | yes | yes | yes | yes |
| coinbase | yes | yes | yes | no |
| cryptocom | yes | yes | no | no |
| gateio | yes | yes | yes | no |
| gemini | **no** | yes | not declared | not declared |
| huobi | yes | yes | yes | no |
| kraken | yes | yes | yes | no |
| kucoin | yes | yes | yes | yes |
| mexc | yes | yes | yes | yes |
| okx | yes | yes | yes | yes |
| poloniex | yes | yes | yes | no |

Three counts fall out of that table and each one bears on a variant. Every one
of the fifteen declares a limit order. Fourteen declare a market order, and the
exception is gemini. Eleven declare a market buy by cash amount, and only five
declare the sell side of it.

```
createOrder                     15 of 15
createLimitOrder                15 of 15
createMarketOrder               14 of 15   gemini declares it False
createMarketBuyOrderWithCost    11 of 15
createMarketSellOrderWithCost    5 of 15
createStopLimitOrder            11 of 15
createStopMarketOrder            8 of 15

control, the same reader on a capability the library does not carry
  has["createOrder"]          -> True
  has["zzNoSuchCapability"]   -> None
  keys in coinbase.has        -> 246
```

The fifth line matters more than its size suggests. A scrum sells, and a cash
amount reaches the sell side at a third of the offered venues.

### The size rule shape, and the two venues that publish none

The record a bot reads holds a size step. Of the 104 exchange classes the
installed trading library carries, 102 publish a step-shaped size rule and 2
publish significant-digit precision instead. One of those two is on the offered
list.

| Reading | Figure |
| ------- | ------ |
| exchange classes in the installed library | 104 |
| classes publishing a step-shaped size rule | 102 |
| classes publishing significant digits instead | 2, bitfinex and bithumb |
| of those two, on Acervator's offered list | 1, bitfinex |

Two controls sit beside that count. The reader answers a step under the
step-shaped mode and nothing under the significant-digit one, which makes the
figure 2 a fact about the venues rather than about the reader. Every class was
read with the socket constructor replaced by one that raises.

```
precision_to_increment("0.01", TICK_SIZE)           -> 0.01
precision_to_increment("2",    DECIMAL_PLACES)      -> 0.01
precision_to_increment("5",    SIGNIFICANT_DIGITS)  -> None

104 classes instantiated, 0 failed, sockets refused for the whole census
```

Driven on the five rule shapes a record can carry, the order gate floors an
amount only where a step was published. A venue publishing a minimum and no
step keeps its minimum refusal and takes no flooring.

| What the record carries | An amount of 92.62189809510927 becomes | Sized by |
| ----------------------- | -------------------------------------- | -------- |
| step 0.01, minimum 0.1 | 92.62 | recorded venue rules |
| minimum 0.1, no step | 92.62189809510927 | recorded venue rules |
| no minimum, no step | 92.62189809510927 | cited unit rule |
| step 1.0, minimum 1.0 | 92.0 | recorded venue rules |
| no record read | 92.62189809510927 | cited unit rule |

The control on that table is an amount under the minimum, which refuses rather
than sizing, so an empty refusal above is a reading and not a silence.

```
sized_order(0.05, fractional, MarketRules(min_amount=0.1))
  -> units 0.0, refusal "below the venue's minimum size"
```

The trading library still rounds the amount inside the connector for every
venue, so a significant-digit venue is not handed raw float digits. bitfinex
carries its own override of that rounding. Read with a planted market record and
no network, an amount of 92.62189809510927 came back as 92.62189 for a published
5 and as 92.62189809 for a published 8.

```
coinbase, published step 0.01   -> "92.62"
coinbase, published step 1.0    -> "92"
bitfinex, published 5           -> "92.62189"
bitfinex, published 8           -> "92.62189809"
bithumb,  published 4           -> "92.6218"
```

### Can the bot as written trade here

The deliverable. One row per venue, two yes-or-no columns, and every no naming
what would have to change. The first column asks whether the bot's own order
shape fits the venue's rules. The second asks whether an order can reach the
venue at all from this program and a United States account.

| Venue | The bot's shape fits | An order can reach it today | What the no is |
| ----- | -------------------- | --------------------------- | -------------- |
| coinbase, spot | yes | yes | — |
| kraken | yes | yes | — |
| kucoin | yes | yes | — |
| okx | yes | yes | — |
| gateio | yes | yes | — |
| bitget | yes | yes | — |
| mexc | yes | yes | — |
| bitstamp | yes | yes | — |
| cryptocom | yes | yes | — |
| bitfinex | yes | yes | — |
| gemini | **no** | yes | the venue declares no market order, and the bot names a market order at nine of the thirteen places it names an order type |
| binance | yes | **no** | the venue refuses a United States address; the bot's shape is not the obstacle |
| bybit | yes | **no** | the venue refuses a United States address; the bot's shape is not the obstacle |
| poloniex | yes | **no** | the venue restricts a United States account; the bot's shape is not the obstacle |
| huobi | yes | **no** | the venue restricts a United States account; the bot's shape is not the obstacle |
| coinbase, US futures | **no** | **no** | a contract is whole, and an excess under one contract cannot be sold |
| Alpaca | yes | **no** | nothing constructs the broker connector, so the order path has no caller |
| Webull | yes | **no** | nothing constructs a connector for it, and none exists |
| Interactive Brokers | **no** | **no** | a quantity order rounds down to whole shares, and no connector exists |
| Schwab | **no** | **no** | the Trader API places no fractional order, and no connector exists |
| tastytrade | **no** | **no** | no fractional quantity for automated trading, and no connector exists |
| E\*TRADE | **no** | **no** | no fractional share of an individual stock, and no connector exists |
| TD Ameritrade | **no** | **no** | the API closed on 10 May 2024 |
| Fidelity | **no** | **no** | no retail trading API is published |
| OANDA | **no** | **no** | whole currency units, and no connector exists |
| FOREX.com | **no** | **no** | whole currency units, and no connector exists |
| tastyfx | **no** | **no** | whole currency units, and no connector exists |
| Tradovate | **no** | **no** | a contract is whole, and no connector exists |
| NinjaTrader | **no** | **no** | a contract is whole, and no connector exists |

Ten venues answer yes to both. Every one of the ten is crypto spot, and every
one is reached by the single connector the program already constructs.

Four rows say no to the second column for a reason no variant can absorb: the
venue itself refuses the account. Nine rows say no because no connector exists.
Those nine are a construction that is missing, not a rule the bot cannot satisfy.

Two verdicts on this page are not answered and are written as such rather than
guessed. Whether each whole-share broker accepts a sell named as a cash amount
is not stated by any page read for this manual, and each firm's own
order-submission page answers it. The order types Schwab, tastytrade, E\*TRADE,
Interactive Brokers and the three currency dealers accept are likewise not
stated, and each firm's own order specification answers that.

### The variants this comparison implies

Three, and no more. Each is named by what it absorbs. None is built here, and
one of the three cannot be designed until a decision on the issue is answered.

The first names a cash amount where the bot names a unit count. It is already
proposed higher up this page and it absorbs a whole-share size rule. It reaches
Interactive Brokers, Schwab, tastytrade and E\*TRADE, and Alpaca carries the
same field beside its quantity.

```
# PROPOSED, not present. Quoted from this page's own proposal above.
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float | None = None,
        notional_usd: float | None = None,
        order_type: OrderType = OrderType.MARKET,
    ) -> StockOrder:
```

The second sends a limit order where the bot sends a market order. It absorbs
one venue, gemini, which is the only one of the fifteen that declares no market
order. It is the smallest of the three and it changes one field.

```
# PROPOSED, not present. The order type a venue declines is replaced.
#   gemini declares createMarketOrder False; createLimitOrder True.
#   A market order becomes a limit order priced to cross.
```

The third holds an excess until it reaches one whole unit, then sells one. It
absorbs every market whose smallest order costs more than a scrum's excess:
each futures venue, the three currency dealers, and any market whose own row
already reads that it cannot size a scrum. **It cannot be designed yet.** The
issue's first open decision is whether such a market is refused or whether the
scrum trigger changes for it, and the two answers build different variants.

```
In development. Decision 1 on the issue owns it.
```

Nineteen of the twenty-nine rows above need no variant at all. Ten trade today,
four are refused by their own venue, and nine wait on a connector rather than on
a shape. Saying so is the useful answer, and inventing a fourth variant to round
the list out would not be.

### What this entry overtakes and what it corrects

One sentence of this page is overtaken. It is kept as written:

> The verdict column above falls into two groups and no more. A venue that reads
> yes needs nothing new. Every venue that reads no is served by one second shape,
> not by a shape of its own.

The true sentence is: the verdict column falls into two groups on the size rule
alone, and the whole requirement set splits the no group into three. A
whole-share venue is served by the cash-amount shape. A venue declining a market
order is served by a limit-only shape, which the size rule cannot see. A market
whose smallest order costs more than the excess is served by neither, and waits
on the issue's first open decision.

One citation on this page has moved and the cells that carry it are kept as
written. The venue table names the equity venue list at line 33 of its module,
in nine of its source cells. That constant now sits at line 46, and line 33
holds a comment about button spacing.

```
src/gui/main_tabs/asset_class_surface.py:46   EQUITY_VENUES, nine ids
src/gui/main_tabs/asset_class_surface.py:65   LAYERED_CLASSES, crypto and stocks
```

Two further citations elsewhere in this arc have moved the same way, and both
name a constant that exists. The cited unit rule table sits at line 57 of its
module rather than line 46, and the per-venue candle lengths sit at line 47 of
theirs rather than line 50.

Every other sentence above stands as written. The per-venue size table, the
excess figure, the three-answer rule and the per-market answer are unchanged by
this entry.

## 2026-09-25 - a venue's own rules select the bot variant

A venue's own published rules pick the bot's shape. No setting offers the choice
and no screen exposes it. One function reads one market's record and answers with
a variant name, and the order path acts on that name at the single site every
live order passes. A record nothing has read selects the bot as written.

```python
# src/trading/scrumming/sizing.py:280
def venue_variant(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
    if rules is None or not getattr(rules, "read", False):
        return VARIANT_NONE
    if tradeable_answer(rules, price, excess_usd) == TRADEABLE_NO:
        return VARIANT_WHOLE_UNIT
    if getattr(rules, "order_types", None) == ORDER_TYPES_LIMIT_ONLY:
        return VARIANT_LIMIT_ONLY
    return VARIANT_NONE
```

### Which markets each variant states it can trade

Four names exist, counting the bot as written, and each one is named by the
market shape it absorbs. The program holds two of the four, and one function
answers per market whether the variant that market selects is one of the two.

```python
# src/trading/scrumming/sizing.py:264
VARIANT_MARKETS: dict[str, str] = {
    VARIANT_NONE: "a market naming a unit count on a venue taking a market order",
    VARIANT_LIMIT_ONLY: "a market on a venue declaring no market order",
    VARIANT_CASH_AMOUNT: "a market whose size is a whole share",
    VARIANT_WHOLE_UNIT: "a market whose smallest order costs more than the excess",
}

#: The variants the running program holds. ``VARIANT_CASH_AMOUNT`` has no caller
#: to reach it and ``VARIANT_WHOLE_UNIT`` waits on the scrum trigger's ruling.
VARIANTS_BUILT = frozenset({VARIANT_NONE, VARIANT_LIMIT_ONLY})
```

### The limit-only variant, and the one venue it reaches

The limit-only variant is built. It sends a limit order where the bot sends a
market order, and it changes one field. Gemini is its one venue. The order-type
table cites two pairs, Gemini is the only one of the two declaring no market
order, and a pair absent from that table declares nothing and is never read as
declining a type.

```python
# src/trading/scrumming/sizing.py:147
CITED_VENUE_ORDER_TYPES: dict[tuple[str, str], str] = {
    (CLASS_CRYPTO, "coinbase"): ORDER_TYPES_WITH_MARKET,
    (CLASS_CRYPTO, "gemini"): ORDER_TYPES_LIMIT_ONLY,
}
```

### The two variants named and not built

The cash-amount variant is named and nothing reaches it, because the equities
order path has no caller. The broker base declares the order method and no module
calls it, and no file outside its own imports the one broker connector that
exists.

```
src/stocks/broker_base.py:145      place_order, declared, called by nothing
src/stocks/alpaca_connector.py     imported by no file in src/, main.py or tools/
```

The whole-unit variant is named and waits on a decision that is the operator's.
It would hold an excess until that excess reaches one whole unit, then sell one
unit. Refusing a market too small to scrum and changing that market's scrum
trigger build two different variants, and the issue's first open decision picks
between them.

```
In development. Decision 1 on the issue owns it.
```

### A market no variant trades is scanned, charted and reported

Exclusion is from trading, not from sight. A scan keeps such a symbol in its own
asset list and names it in a field of its own, so the market still draws its
chart and still reports. Every order path refuses that market carrying the
reason, and the reason names the variant the market needs beside the shape that
variant absorbs.

```python
# src/trading/ata_spm.py:955
    #: The symbols this scan read that no built bot variant trades, kept in
    #: ``assets`` so each one still charts and still reports.
    untradeable: tuple = ()
```

### The variant sentences this entry overtakes

Two passages above are overtaken. Both are kept as written. The first is the
count under the variants this comparison implies:

> Three, and no more. Each is named by what it absorbs. None is built here, and
> one of the three cannot be designed until a decision on the issue is answered.

The true sentence is: four variant names exist, counting the bot as written, and
the program holds two of them. The limit-only variant is built and Gemini is its
one venue. The cash-amount variant is named and has no caller. The whole-unit
variant is named and waits on the issue's first open decision.

The second is the heading over the earlier proposal:

> Two variants cover every venue

The true count is four names, two of them built. That heading counts the two
shapes the size rule can see, a unit count and a cash amount. It counts neither
the order-type shape, which the size rule cannot see, nor the whole-unit shape,
which waits on a ruling.

## 2026-09-25 - what each count over the verdict table measures

The verdict table above holds twenty-nine rows, and the prose around it carries
four counts of them. Three of the four are right about three different questions,
and the fourth matches no set the table holds. The figures below name the
question each count answers.

### The recount, and the control it was taken with

Read from the table's own two verdict columns, and from its reason column counted
by phrase:

```
rows in the table                                   29
the bot's shape fits reads yes                      16
both columns read yes                               10
the reason names the venue refusing the account      4
the reason ends "and no connector exists"            9
the reason names a connector at all                 11
rows a named variant absorbs                        11
rows no named variant absorbs                       18
```

The counter was calibrated on those same twenty-nine rows before any figure above
was taken. Three reason phrases the table carries returned 5, 3 and 1, and a
phrase planted for the purpose returned nothing and exited non-zero.

Three different questions therefore produce three different counts over one set
of rows, and none of the three is wrong about its own question. Sixteen rows need
no variant, because the bot's shape already fits the venue. Eighteen rows are
absorbed by no named variant, because no shape helps a venue that refuses the
account or a connector that is missing. Eleven rows are absorbed by a named
variant: four by the cash-amount shape, one by the limit-only shape, and six by
the whole-unit shape.

### The counting sentences this entry overtakes

Two passages are overtaken. Both are kept as written. The first is the closing
count:

> Nineteen of the twenty-nine rows above need no variant at all. Ten trade today,
> four are refused by their own venue, and nine wait on a connector rather than on
> a shape.

The true sentence is: sixteen of the twenty-nine rows read yes in the
bot's-shape-fits column, which is the column that says a variant is not needed.
The three figures beside that count answer three different questions and sum to
twenty-three, leaving six rows outside all three — gemini, coinbase US futures,
Alpaca, Webull, TD Ameritrade and Fidelity.

The second is the connector count above the variant list:

> Nine rows say no because no connector exists. Those nine are a construction
> that is missing, not a rule the bot cannot satisfy.

The true sentence is: nine rows carry a reason cell ending in that phrase, and
ten rows name a connector that does not exist, because the Webull cell words the
same absence differently. The Alpaca cell names a connector that does exist and
has no caller, which is why the figure for a missing connector is ten rather than
eleven.

## 2026-09-26 - a venue's expiry stops a buy and not a sale, and cash the venue has not settled is not spent twice

A venue can close a market on a date of its own, and it can take days to hand
over the cash from a sale. The record a bot reads carries both of those facts
now, beside the size and price rules already on this page. A venue that
publishes neither leaves both absent, and absent changes nothing.

```python
# src/exchange/base.py:141
    expiry_ms: Optional[float] = None  # epoch ms the venue closes the contract on
    settlement_days: Optional[float] = None  # days the venue takes to settle a sale
```

### The two rules the record carries beside the other four

Two members read the expiry. The first answers whether the venue published one
at all. The second answers how many days remain, and it turns negative once the
date has passed. A record holding no expiry answers False and nothing.

```python
    @property
    def expires(self) -> bool:
        """True while ``expiry_ms`` is a finite positive epoch, and False for the
        None a venue publishing no expiry carries."""

    def days_to_expiry(self, moment_s: float) -> Optional[float]:
        """Days from ``moment_s`` to ``expiry_ms``, negative once it has passed.

        None while ``expires`` is False or ``moment_s`` is not a finite number.
        """
```

### A buy refuses on every order path, and a sale passes

A market that publishes an expiry selects a fifth variant name, and the program
does not hold it. The function asks the expiry question first, before the size
question and before the order-type question, so a market with a date on it never
reaches either of them.

```python
# src/trading/scrumming/sizing.py:331
VARIANT_ROLLING_POSITION = "rolling position"

VARIANT_MARKETS[VARIANT_ROLLING_POSITION] = "a market the venue expires on a date"

# src/trading/scrumming/sizing.py:375
    if getattr(rules, "expires", False):
        return VARIANT_ROLLING_POSITION
```

Three order paths read that answer, one per data source, and each of the three
refuses a buy into such a market by name. The scan keeps the symbol in its own
asset list and names it in a field of its own, exactly as it does for any other
market no built variant trades.

```
src/trading/bot_container.py:370     the live order path
src/paper/paper_run.py:507           the Paper Trader's fold
src/simulator/back_test.py:1297      the back test's fold
src/trading/ata_spm.py:1323          the scan naming the market
```

### Why the two sides differ

The asymmetry looks inconsistent until a reader has the reason. Buying into a
market the venue removes on its own date takes on a thing that ends; the bot
would accumulate into a market that stops existing, and no rule in the tree yet
says which contract a position rolls into. Selling out of a position already
held takes on nothing. A bot holding such a position keeps scrumming it down by
its own cycles and closes it before the date, and nothing rebuys it.

```python
# src/trading/bot_container.py:375
        _closing = variant_permits_close(_variant) and side == OrderSide.SELL

        if not variant_built(_variant) and not _closing:
            self._refuse_order(...)
```

The sell that passes says so where the operator watches. The Console line names
the days left and states that nothing will rebuy the position.

```
CLOSING AN EXPIRING MARKET: SELL <symbol> <units> is submitted where a BUY is
refused, because the venue expires this contract in <n> days (rolling
position). Nothing rebuys it.
```

### A fold waits while the venue holds the cash

A sale whose cash the venue has not handed over has not returned its money, and
spending it would spend the same dollars twice. One figure answers how much of a
fold's own cash sits inside the delay, and a second holds the rebuy to the
wallet less that figure. With nothing to spend, the fold fills nothing, names the
reason, and leaves its tranches queued for the next round.

```python
# src/trading/scrumming/sizing.py:169
CITED_VENUE_SETTLEMENT: dict[tuple[str, str], float] = {
    (CLASS_CRYPTO, "coinbase"): 0.0,
}

HELD_UNSETTLED_CASH = "the venue has not settled the sale"

def unsettled_usd(tranches, moment_s, settlement_days) -> float:
def spend_less_unsettled_usd(spend, cash_usd, held_usd) -> float:
```

A cited delay of zero is a venue returning the cash at once, and it holds
nothing. A pair absent from that table publishes no delay, which also holds
nothing. Only a positive figure can hold a fold back.

### Where the settlement hold reaches

Two of the three folds read the delay at the point they size a rebuy. The third,
the live autonomous fold, does not read it. Live's manual rebalance does read it
and names the held amount on the Console.

```
src/paper/paper_run.py:542           the Paper Trader's fold reads the delay
src/simulator/back_test.py:1333      the back test's fold reads the delay
src/trading/scrumming/execution.py:953   live's manual rebalance reads the delay
the live autonomous fold             does not read the delay
```

The one venue this program records cites zero days, so no fold on any path holds
cash today. A venue citing a positive figure would reach the two folds above and
leave the live autonomous one spending cash it does not yet have.

### Which markets carry an expiry today

None of them. The recording every back test and every paper run reads holds one
venue and 1,146 markets, and not one row carries an expiry. The recording holds
only four field names, and the expiry is not among them, because the recording
predates the field. Each such row answers absent, which is exactly what a venue
publishing no expiry answers.

```
recorded coinbase markets                                1146
rows with a non-null expiry                                 0
CONTROL rows with a non-null minimum size                1146
CONTROL rows with a non-null minimum cost                1146
CONTROL rows with a planted absent key                      0
rows carrying a dated contract suffix                     100
dated rows with a non-null expiry                           0
CONTROL dated rows with a non-null minimum cost           100
distinct symbols the saved fleet names                     38
of those, symbols carrying a dated contract suffix          0
CONTROL of those, symbols carrying a quote separator       38
```

The controls sit in the same run as the figures they support, so a zero above is
a reading of the file and not of the reader. Two of the rows matter together: one
hundred recorded symbols carry a dated contract suffix and none of them carries
an expiry, because the recording predates the field. A fresh recording of that
venue would fill those hundred rows, and those hundred markets would then select
the fifth variant.

This reaches no live market. No symbol the saved fleet trades carries a dated
contract suffix, no recorded row carries an expiry, and the settlement table
cites this venue at zero days.

### The sentences on this page that this entry overtakes

Nine passages are overtaken. Each one stays exactly as written, with the sentence
that is true today beneath it.

The first is the count of a venue's order rules:

> A venue publishes three order rules, not two.

The true sentence is: a venue's own product record publishes five rules, not
three. The four already named on this page sit beside the date the venue closes
the contract on. Three further fields on the record come from cited tables
rather than from the product record, and they are the trading session, the order
types and the settlement delay.

The second is the field block under that sentence. It lists four rules and the
read flag, and it stays as written. The true block carries eight fields before
that flag: the four it already lists, then the trading session, the order types,
the expiry and the settlement delay.

```python
# src/exchange/base.py:135
    min_amount: Optional[float] = None  # base units
    min_cost: Optional[float] = None  # quote units
    amount_increment: Optional[float] = None  # base units a size steps by
    price_increment: Optional[float] = None  # quote units a price steps by
    session: Optional[str] = None  # the session name the venue publishes
    order_types: Optional[str] = None  # the order types the venue declares
    expiry_ms: Optional[float] = None  # epoch ms the venue closes the contract on
    settlement_days: Optional[float] = None  # days the venue takes to settle a sale
    read: bool = True
```

The third is the variant function quoted under *a venue's own rules select the
bot variant*. The block stands as written, and the function answers the
rolling-position name first, before the size question and the order-type
question it already showed.

The fourth is the count of variant names:

> Four names exist, counting the bot as written, and each one is named by the
> market shape it absorbs. The program holds two of the four, and one function
> answers per market whether the variant that market selects is one of the two.

The true sentence is: five names exist, counting the bot as written, and the
program still holds two of them. The fifth name is the rolling position, which
the program names and does not build.

The fifth is the market table quoted under that count. It stands as written, and
it carries a fifth row now, naming a market the venue expires on a date.

The sixth is the heading over the unbuilt variants:

> The two variants named and not built

The true count is three named and not built: the cash-amount variant with no
caller, the whole-unit variant waiting on a decision, and the rolling position
waiting on the rule that names which contract a position rolls into.

The seventh is the sentence about what an order path does with such a market:

> Every order path refuses that market carrying the reason, and the reason names
> the variant the market needs beside the shape that variant absorbs.

The true sentence is: every order path refuses a buy into that market carrying
the reason, and one unbuilt variant lets a sale out of it through. The rolling
position is that one, and only a sell passes.

The eighth and ninth are the two corrected counts written when the variants were
first set out:

> The true sentence is: four variant names exist, counting the bot as written,
> and the program holds two of them.

> The true count is four names, two of them built.

The same figure overtakes both. Five variant names exist and the program holds two
of them.
