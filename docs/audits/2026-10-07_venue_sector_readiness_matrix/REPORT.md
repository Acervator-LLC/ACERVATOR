# Venue and Sector Readiness Matrix

**Mode: Reference.**

This report covers issue #881. It establishes, per exchange and per sector,
whether a bot can place an order there today. It builds nothing. No file under
`src/`, `main.py`, `tools/` or `dev_harness/` changed, and no page under
`docs/manual/` changed.

**FALSIFICATION.** This report is wrong if any cited path or symbol is absent
from the tree it ships on, if a cell called READY turns out to refuse a real
order, if a venue called out of a sector lists a product in it, or if the
recorded market rules change the counts after this date.

---

## What the operator asked for

> This is a multi-sector platform. It offers crypto. It has to be able to
> support fractional sells for this but probably needs a whole unit scrumming
> variant for stocks or sectors that do not offer fractional transactions.

> Make sure each exchange appears under each sector with which it is
> compatible. Make sure each exchange product suite is properly filtered under
> each sector for it has offerings.

> Essentially, I need you to verify that each exchange is integrated end to end
> and is able to receive orders via API and our bots within each sector that the
> given exchange offers products.

> Anchor in code. Functionality with Coinbase must be mirrored. And augmented to
> satisfy the other sectors.

So the question per cell is not whether the venue allows the order. It is
whether our code can place it there today, measured against what our code
already does for Coinbase.

---

## The error this corrects

Issue #881 carries one line that rejects six venues:

```
Schwab, Tradier, tastytrade, TD Ameritrade, Fidelity and Robinhood fail the
cycle test. None of the six places a fractional sale over its interface.
```

That line is wrong about four of the six, right about one, and moot about the
last. Each reading below was fetched from the firm's own page on 2026-10-07.

| Firm | the line says | the firm's own page says |
| --- | --- | --- |
| Schwab | no fractional sale | a Stock Slice fraction is "held or sold individually" |
| Robinhood | no fractional sale | "buy or sell a fractional share" above one dollar |
| tastytrade | no fractional sale | crypto takes eight decimals; equities are not documented |
| Fidelity | no fractional sale | real-time fractional trading exists; no public order interface does |
| Tradier | no fractional sale | correct — "in whole numbers" |
| TD Ameritrade | no fractional sale | moot — the developer host has no DNS record |

The rule the line generalised is real, and it belongs to one sector on one
venue. Coinbase's own order documentation states it and its exact boundary.

```
In pre-market, after-hours, overnight, or multi-session trading, specify a
positive whole-share base_size; quote_size and fractional sizing are not
supported.
```

Coinbase's own product record then makes the fraction a property of the product
rather than of the venue: each product carries a `fractionable` boolean and a
minimum notional size beside it. So the whole-share rule is equities, outside
the regular session, on one venue.

A fractional sale is a property of a venue **and a sector**, not of a venue. A
venue leaves a sector only when it lists no product in that sector, or when no
order path our code can reach exists for it.

```
fractional sell available   the original scrumming logic works there
whole units only            that sector needs the whole-unit variant
```

---

## The Coinbase baseline — the path every order travels

This is the spine of the matrix. Every other cell is measured against this list,
because it is what works today.

```
ScrummingBot.tick
  TickPhaseMixin._tick_execute_scrum        sizes the excess above target
  TickPhaseMixin._tick_execute_fold         sizes the re-entry
    BotContainer.guarded_place_order        the one site every live order passes
      BotContainer._get_market_rules        the venue's own rules, cached
        CCXTConnector.get_markets           load_markets plus _sector_products
          ccxt_connector.market_rules       min, step, tick off one product record
          ccxt_connector.declared_order_types   the venue's own has map
          ccxt_connector.market_asset_class     the sector per market
          market_rules_store.record_venue       writes the recording
        sizing.venue_session                the session the pair publishes
        sizing.order_types_for              record first, cited table second
        sizing.venue_settlement_days        the settle delay the pair publishes
      BotContainer._asset_class             the sector, from the recording
      sizing.market_unit_rule               recorded step first, sector row second
      sizing.sized_order                    floors onto the step, refuses below min
        sizing.amount_on_increment
        sizing.steps_below_minimum
      MarketRules.price_on_tick             min_cost measured at the booked price
      sizing.outside_session                holds an order outside the session
      sizing.venue_variant                  the variant this market needs
      sizing.variant_holds_market           refuses a variant we do not hold
      sizing.position_minimum_refusal       two units to open a whole-unit position
      sizing.variant_replaces_market_order  a limit price where no market order
      idempotency.derive_coid               the deterministic client order id
      CCXTConnector.place_order
        ccxt amount_to_precision            the venue's own step, applied again
        ccxt fetch_ticker                   a price for a market buy that needs one
        ccxt price_to_precision             the venue's own tick
        ccxt create_order                   the venue call
```

Four things in that list are venue-specific, and each already sits at one site
with a generic branch. Nothing in the path is written for Coinbase alone.

```
the market-order capability    declared_order_types reads ccxt's own has map
the market-buy price rule      place_order fetches a ticker for any venue
the client-order-id field      four branches: coinbase, binance, kraken, default
the PEM secret shape           one branch, coinbase only, on the secret text
```

---

## What the program knows today

Three readings, all taken on 2026-10-07 with the home redirected to a scratch
directory and the live recording read as a copy.

The recorded rules hold one venue. The store is
`src/exchange/market_rules_store.py` and the file sits under the runtime home,
read through its own `load_document`.

```
venues recorded                 1   coinbase
market rows recorded         1142
rows carrying a sector label    0
rows carrying a size step    1142   817 fractional, 325 whole
rows carrying order types    1142   all "market and limit"
rows carrying an expiry       100
```

Zero of 1142 rows carry a sector. `BotContainer._asset_class` answers crypto
whenever the recording holds no sector for a symbol, so **every live order today
is sized as a crypto order**, whatever sector the market belongs to.

The manual's own venue page records what the recording should hold once the
sector products land. It was measured on 4 October 2026 and the live recording
does not match it.

| what the recording holds for Coinbase | the manual's expected | live, 2026-10-07 |
| --- | --- | --- |
| rows in all | about 2,135 | 1,142 |
| crypto | 1,123 | 1,142, all unlabelled |
| commodities | 21 | 0 |
| stocks | about 990 | 0 |

The equity and commodity rows have never reached his recording. The code that
records them exists on `current` and the build he launches predates it, which
the next section measures.

Classifying all 1142 recorded symbols through the program's own
`market_asset_class` gives the sector split the program would read if the labels
were written.

```
crypto           890
futures_perps    227   99 of them expiring
forex             21   euro, Australian dollar, pound and Singapore tokens
commodities         4   tokenised gold
stocks              0
indices             0
```

Two caveats on that split, and both are limits of the reading, not of the code.
The recording stores no product type, so a Coinbase equity product would be read
as crypto by this reconstruction rather than as stocks. The recording stores no
futures asset label either, so a commodity-underlying or index-underlying
contract is read as futures and perpetuals.

Nothing filters a market list by sector. The classifier has exactly two callers
and both are inside `CCXTConnector.get_markets`, writing the recording.

```
market_asset_class        2 callers, both writing the recording
recorded_classes          1 reader, BotContainer._asset_class
venue_served_classes      0 readers outside asset_class_surface
```

The bot wizard asks the operator for a sector and drops the answer. Its own
`get_config` returns an asset-class key and a sizing-mode key; `BotConfig`
declares neither, and `bot_config_kwargs` keeps only the fields `BotConfig`
declares.

```
BotConfig fields naming a venue or sector:  exchange_id, and nothing else
```

---

## Why the recording carries no sector — the build, not the code

The sector mechanisms are on `current` and have never run. The build the
operator launches predates them.

The recording was rewritten at 13:45 on 2026-10-07 and read back at 14:18 with
byte-identical content: one venue, 1142 rows, zero sectors. So this is not a
stale file from an old run. The running build wrote it that way today.

That build is `Acervator-0.2.0-dev.2194.ge3dcc15f-qt`, whose commit is dated
2026-10-04 and sits 33 commits behind `current`. Comparing it against `current`
over the three modules an order's rules travel through:

```
symbol                      launched build   current
CLASS_FIELD                              0         6
_sector_products                         0         3
VENUE_CLASS_PRODUCT_TYPES                0         3
market_asset_class                       0         3
declared_order_types                     4         4
expiry_ms                                5         5
VARIANT_ROLLING_POSITION                 9         9
```

The three rows that read the same are exactly the three facts the recording
does carry: order types on all 1142 rows, an expiry on 100, and the
rolling-position variant selecting on those 100. The four rows that read zero
are exactly the four facts it lacks: no sector label, no equity product fetch,
no product-type map and no classifier.

So the first step in the sector work is a rebuild, not a line of code. Four
mechanisms already written would begin recording sectors and fetching equity
products on the next launch of a current build.

```
after a rebuild   the recording gains a sector per market and the equity
                  products the venue serves, so _asset_class stops answering
                  crypto for every market
still needed      the whole-unit variant, the rolling-position variant, a
                  sector on BotConfig, a product list narrowed by sector, and
                  the broker construction
```

## The venue and sector grid the program draws

This is what `asset_class_surface.venue_classes` answers for every venue id the
tree names, read 2026-10-07.

| Venue id | crypto | stocks | commodities | forex | indices | futures_perps |
| --- | --- | --- | --- | --- | --- | --- |
| coinbase | yes | yes | yes | yes | yes | yes |
| binance | yes | - | - | - | - | - |
| bitfinex | yes | - | - | - | - | - |
| bitget | yes | - | - | - | - | - |
| bitstamp | yes | - | - | - | - | - |
| bybit | yes | - | - | - | - | - |
| cryptocom | yes | - | - | - | - | - |
| gateio | yes | - | - | - | - | - |
| gemini | yes | - | - | - | - | - |
| huobi | yes | - | - | - | - | - |
| kraken | yes | - | - | - | - | - |
| kucoin | yes | - | - | - | - | - |
| mexc | yes | - | - | - | - | - |
| okx | yes | - | - | - | - | - |
| poloniex | yes | - | - | - | - | - |
| alpaca | - | yes | - | - | - | - |
| etrade | - | yes | - | - | - | - |
| fidelity | - | yes | - | - | - | - |
| ibkr | - | yes | - | - | - | - |
| interactivebrokers | - | yes | - | - | - | - |
| schwab | - | yes | - | - | - | - |
| tastytrade | - | yes | - | - | - | - |
| tdameritrade | - | yes | - | - | - | - |
| webull | - | yes | - | - | - | - |

Twenty-nine of the one hundred forty-four cells carry a yes. Coinbase carries
six and every other venue carries one. Two venue ids name one firm, because
`EQUITY_VENUES` holds both of Interactive Brokers' ids.

---

## The matrix

Twenty-six venues by six sectors is one hundred fifty-six cells: the
twenty-four venue ids the tree names, plus Tradier and Robinhood, which the
directive and issue #881 name and the tree does not.

Four readings sit behind each verdict — the venue's offering, whether a
fractional sell is available, the order path our code holds, and the rules
recorded. The verdicts:

```
READY     our code can place that order today and the path is named
BLOCKED   the venue lists the product, our code cannot reach it
ABSENT    the venue lists no product in that sector
WRONG     the program lists this sector for this venue and the venue has none
```

A verdict marked with a question mark is one whose venue offering could not be
fetched. It still counts as its verdict, because the program reaches nothing
there either way, and all twenty-eight are named at the end of this report.

| Venue | crypto | stocks | commodities | forex | indices | futures_perps |
| --- | --- | --- | --- | --- | --- | --- |
| coinbase | READY | BLOCKED | BLOCKED | READY | BLOCKED | BLOCKED |
| binance | READY | BLOCKED | BLOCKED | BLOCKED | BLOCKED? | BLOCKED |
| kraken | READY | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| gemini | READY | ABSENT | BLOCKED | BLOCKED | ABSENT | BLOCKED |
| bitstamp | READY | ABSENT | BLOCKED | BLOCKED | ABSENT | ABSENT |
| cryptocom | READY | BLOCKED | BLOCKED? | BLOCKED? | BLOCKED? | BLOCKED |
| okx | READY | BLOCKED | BLOCKED | ABSENT | BLOCKED | BLOCKED |
| bybit | READY | BLOCKED? | BLOCKED? | BLOCKED? | BLOCKED? | BLOCKED |
| poloniex | READY | BLOCKED? | ABSENT | ABSENT | BLOCKED? | BLOCKED? |
| huobi | READY | BLOCKED | ABSENT | BLOCKED? | BLOCKED? | BLOCKED? |
| kucoin | READY | BLOCKED | BLOCKED | BLOCKED? | BLOCKED? | BLOCKED |
| gateio | READY | BLOCKED | BLOCKED | BLOCKED? | BLOCKED? | BLOCKED? |
| mexc | READY | BLOCKED | ABSENT | BLOCKED? | BLOCKED? | BLOCKED |
| bitget | READY | BLOCKED | BLOCKED | BLOCKED? | BLOCKED | BLOCKED |
| bitfinex | READY | ABSENT | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| alpaca | BLOCKED | BLOCKED | BLOCKED | ABSENT | BLOCKED | ABSENT |
| ibkr | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| interactivebrokers | ABSENT | WRONG | ABSENT | ABSENT | ABSENT | ABSENT |
| schwab | BLOCKED | BLOCKED | BLOCKED | BLOCKED? | BLOCKED | BLOCKED |
| tastytrade | BLOCKED | BLOCKED | BLOCKED | ABSENT | BLOCKED | BLOCKED |
| webull | BLOCKED | BLOCKED | BLOCKED | ABSENT | BLOCKED | BLOCKED |
| etrade | ABSENT | BLOCKED | BLOCKED | ABSENT | BLOCKED | ABSENT |
| fidelity | BLOCKED? | BLOCKED | BLOCKED? | BLOCKED? | BLOCKED? | BLOCKED? |
| tdameritrade | ABSENT | WRONG | ABSENT | ABSENT | ABSENT | ABSENT |
| tradier | ABSENT | BLOCKED | BLOCKED | ABSENT | BLOCKED | ABSENT |
| robinhood | BLOCKED | BLOCKED | BLOCKED | ABSENT | BLOCKED | BLOCKED |

### The four totals

```
READY       16
BLOCKED    106
ABSENT      32
WRONG        2
            ---
total      156
```

READY is every crypto cell plus Coinbase forex. BLOCKED is every cell where a
venue lists the product and our code cannot place the order; 28 of the 106 carry
an unfetched offering. ABSENT is every cell where the venue lists no product,
and every one rests on a two-sided control described below. WRONG is two cells
and both are named.

---

## Crypto — 15 venues, all READY

Every one of the fifteen reaches the same path. A connector constructs for any
id in `SUPPORTED_EXCHANGES`, the settings dialog offers all fifteen, and
`get_markets` records any of them on first connect.

The order-type reading was taken twice: from each venue's own ccxt capability
map on 2026-10-07, and from each venue's own order documentation on the same
day. The two agree on all fifteen.

| Venue | createMarketOrder | order types read | US account |
| --- | --- | --- | --- |
| coinbase | True | market and limit | traded |
| kraken | True | market and limit | offered |
| gemini | False | limit only | offered |
| bitstamp | True | market and limit | offered |
| cryptocom | True | market and limit | offered |
| okx | True | market and limit | offered |
| binance | True | market and limit | IP refused a US address |
| bybit | True | market and limit | IP refused a US address |
| poloniex | True | market and limit | terms refuse a US account |
| huobi | True | market and limit | terms refuse a US account |
| kucoin | True | market and limit | terms refuse a US account |
| gateio | True | market and limit | terms refuse a US account |
| mexc | True | market and limit | terms refuse a US account |
| bitget | True | market and limit | terms refuse a US account |
| bitfinex | True | market and limit | terms refuse a US account |

Gemini declines a market order and both readings say so. Its own order page
accepts only a limit and a stop-limit type, and tells the caller to use an
immediate-or-cancel limit at an aggressive price instead. Our code already
answers that: the record reads limit only, `venue_variant` selects the
limit-only variant, `VARIANTS_BUILT` holds it, and
`variant_replaces_market_order` prices a limit at the venue's own tick.

The venue's own options also name which venues price a market buy by its total
cost rather than its size.

```
market buy requires a price, True    coinbase, gateio, huobi, poloniex
market buy requires a price, False   okx
the option is unset                  the other ten
```

The connector fetches a ticker for every market buy that arrives with no price,
whatever the venue, so all four are already covered.

No venue in this set imposes a whole-unit rule on crypto. The nine US-refused
accounts are an account matter, not a code matter, and they are stated in the
table rather than folded into a verdict.

---

## Stocks — the sector the matrix changes most

Nine of the fifteen crypto venues list tokenised equities or equity perpetuals,
and eight of those nine sell a fraction of a share. Every figure below is the
smallest sellable piece the venue's own system published on 2026-10-07.

| Venue | product | smallest sellable piece |
| --- | --- | --- |
| coinbase | EQUITY product type, with a per-product fraction flag | fractional in session, whole shares outside it |
| binance | tokenised equities | 0.001 share |
| kraken | tokenised equities and funds, 131 assets | about one dollar |
| kucoin | a dedicated Stocks market, five symbols | 0.001 share |
| gateio | tokenised equities | 0.0001 share |
| bitget | tokenised equities, 36 assets | 0.0001 share |
| okx | equity perpetual | 0.01 share |
| cryptocom | equity perpetual | 0.01 share |
| mexc | equity perpetual, whole contracts of 0.01 share | one contract |

Three crypto venues list no equity and the reading is controlled: Gemini's 468
symbols, Bitstamp's 383 pairs and Bitfinex's 342 exchange pairs all returned
complete, with no equity ticker in any of them. HTX carries equity symbols whose
state reads offline, so nothing there is sellable today.

On our side, one broker's connector is written and nothing constructs it.
`AlpacaConnector` appears once outside its own module, in that class's own
docstring. `StockMainWindow` is defined and nothing builds it. The other brokers
have no connector module at all, and `BrokerBase.place_order` is abstract with
Alpaca as its only subclass.

Coinbase lists stocks and the recording holds none of them, nothing filters a
product list by sector, no session row exists for the pair, and the cited rule
names whole units while the whole-unit variant is not one the program holds.

```
the cited unit rule for stocks on coinbase    whole
the cited session for stocks on coinbase      absent, so nothing holds an order
the variants the program holds                limit-only order, none
the whole-unit variant                        not held
```

---

## Commodities — ten venues, almost all through tokenised gold

Tokenised gold is the common product and every venue that lists it sells it in
fractions. Bitfinex is the widest: silver, platinum, palladium and oil beside
gold. Readings taken 2026-10-07.

| Venue | commodity product | fractional |
| --- | --- | --- |
| coinbase | tokenised gold spot, plus commodity perpetuals | yes on spot |
| binance | tokenised gold, 0.0001 step | yes |
| kraken | a gold fund token, plus gold, silver, oil and gas futures | yes on the token |
| kucoin | tokenised gold, 0.0001 step | yes |
| gateio | tokenised gold, 0.001 step | yes |
| bitget | tokenised gold, four decimals | yes |
| okx | tokenised gold, plus a crude oil perpetual | yes on gold, no on the perpetual |
| gemini | tokenised gold, 0.0001 minimum | yes |
| bitstamp | tokenised gold against dollar and euro | yes |
| bitfinex | gold spot, plus gold, silver, palladium, platinum and oil perpetuals | yes on spot |

Three venues list none and the reading is controlled: HTX, MEXC and Poloniex
each returned an empty result for a gold token against a populated result for
their own main crypto pair on the same endpoint.

Every equity broker reaches commodities as a fund share, and a fund share sizes
like a share. The program lists no broker under commodities.

The four tokenised rows in the live Coinbase recording size as ordinary spot
markets and an order on them would place. The 21 commodity contracts the manual
records would not: they carry a whole step and an expiry, and an expiring market
selects the rolling-position variant the program does not hold.

---

## Forex — two venues list a real currency pair

This is the sector the research narrowed rather than widened. Only two of the
fifteen crypto venues list a market whose two legs are both national
currencies, read 2026-10-07.

```
gemini      a euro-dollar market, 0.1 minimum, limit only
bitstamp    a euro-dollar market, five decimals, market and limit
```

Three more list a currency market whose other leg is a dollar stablecoin, which
is the same shape Coinbase lists and not a pair of national currencies.

```
bitfinex    euro and pound perpetuals against a dollar stablecoin, plus two
            spot pairs of the same shape
kraken      currency perpetuals through its European entity; the global futures
            host answered that every instrument it serves is a crypto one
coinbase    21 markets the program reads as forex, each a currency token
            against a dollar stablecoin or a fiat quote
```

OKX lists none and the reading is controlled: a euro-dollar underlying returned
the venue's own "index does not exist" code while three other underlyings
returned live instruments on the same endpoint.

Coinbase lists no market with two national-currency legs, and its own product
list carries three stablecoin-against-fiat markets.

```
recorded markets the program reads as forex   21
with a fractional step                        17
with a whole step                              4
order types                                   market and limit
the cited unit rule for forex on coinbase     fractional
```

Those 21 place today, which is why the cell reads READY. Whether a euro token
against a dollar stablecoin counts as a forex market is a product judgment and
it is his to make.

Among the brokers, only Interactive Brokers documents a direct currency security
type, sizeable by the second currency's notional. Alpaca, tastytrade, Tradier
and E\*TRADE list none; Robinhood, Webull and Schwab reach currencies only as
futures.

---

## Indices — five venues, mostly as perpetuals or fund tokens

Read 2026-10-07.

```
bitfinex   eight national index perpetuals
okx        a perpetual on a large US index fund
bitget     an index fund token, four decimals
kraken     index futures through its European entity
gateio     an index fund token seen in the pair list, not confirmed alone
```

Gemini and Bitstamp list none and both readings are controlled by a complete
symbol list. Coinbase lists index products: its own derivatives overview names
equity and commodity perpetuals without naming a contract, and the program's own
comment in `asset_class_surface` records its classifier answering indices for
six of the venue's products. The live recording holds none.

An index contract carries a whole step and an expiry, so it selects the
rolling-position variant that the program does not hold. Every broker reaches
index exposure as a fund share.

---

## Futures and perpetuals — the sector with the most recorded product

Coinbase's recording holds 227 contract markets, 99 with an expiry. This is
where the split between a placeable order and a refused one is sharpest.

```
recorded futures and perpetual rows   227
with an expiry                         99   rolling-position variant, not held
without an expiry                     128   admitted
with a whole step                     140
with a fractional step                 87
```

A dated contract refuses a buy and is allowed to sell, because
`variant_permits_close` makes one exception for a position already open in an
expiring market. A perpetual with a whole step is admitted, because
`variant_holds_market` admits the whole-unit variant when the recorded step
reads whole units.

Thirteen crypto venues list a perpetual or a dated contract and the program
lists one venue under the sector. Bitstamp lists none and the reading is
controlled: its 383 pairs returned complete with no contract among them, and its
own interface page publishes only spot endpoints.

---

## Every WRONG cell

```
tdameritrade, stocks           the developer host has no DNS record, measured
                               2026-10-07; the firm folded into Schwab. The id
                               names no venue that can take an order and the
                               row is on his screen today

interactivebrokers, stocks     a second id for the firm the other id already
                               names; one firm occupies two rows, so one of the
                               two is wrong
```

Both are rows the operator sees now. Neither is a venue that lists no product;
both are venue ids naming no reachable venue, which is the same defect the
WRONG column exists to catch.

### How the method could have found a WRONG cell

The WRONG count is two, so the method needs showing. Take a venue and sector
the program records and confirm the venue serves it.

Coinbase and crypto: the program lists it, the recording holds 890 crypto rows
read through the program's own classifier, and the venue's own product list
answered 696 spot products on 2026-10-07. The cell is not wrong and the check
said so.

Now the same check with the sector moved. Coinbase and indices: the program
lists it, and the live recording holds zero index rows. The check reported a
mismatch, which is exactly what it would report for a genuinely wrong row. It
reads BLOCKED rather than WRONG only because the venue does list index products,
so the mismatch is in our recording. Run against an id naming no reachable
venue, the same check reported WRONG, and it did so twice.

---

## One READY cell, traced end to end

Coinbase and forex. The operator picks the Forex sector, the Coinbase venue and
a euro-token market, and the bot scrums.

```
ScrummingBot.tick
  sizing.priced_usd           reads the position value
  sizing.target_delta_usd     reads the excess above target
TickPhaseMixin._tick_execute_scrum
  sizes the units to sell
BotContainer.guarded_place_order
  refuses a non-finite or non-positive amount
  BotContainer._get_market_rules
    CCXTConnector.get_markets
      ccxt load_markets answers the product record
      ccxt_connector.market_rules reads step 0.01, min 0.01, tick 1e-08
      ccxt_connector.declared_order_types reads market and limit
      market_rules_store.record_venue writes the row
    sizing.venue_session answers continuous
    sizing.order_types_for answers market and limit
  BotContainer._asset_class answers crypto, because the row carries no sector
  sizing.market_unit_rule reads the recorded step, answers fractional
  sizing.sized_order floors the units onto 0.01, refuses below 0.01
  MarketRules.price_on_tick books the price on 1e-08
  sizing.outside_session answers False, the session is continuous
  sizing.venue_variant answers the plain variant, which the program holds
  sizing.variant_holds_market answers True
  idempotency.derive_coid builds the client order id
CCXTConnector.place_order
  ccxt amount_to_precision applies the venue's own step
  ccxt create_order sends it with the client order id
```

One step in that trace is wrong and the order still places. The sector answers
crypto rather than forex, because the recording carries no sector. The recorded
step answers before the sector row, so the size is right anyway. The sector row
would only matter if the venue published no step.

---

## One BLOCKED cell, with its missing piece

Alpaca and stocks. The venue lists equities, the fractional sell is documented
to nine decimal places and marked long, the connector is written, and nothing
constructs it.

```
present   src/stocks/broker_base.py             BrokerBase, the equities contract
present   src/stocks/alpaca_connector.py        AlpacaConnector, place_order written
present   src/stocks/alpaca_connector.py        asset_rules, one asset record read
present   src/exchange/market_rules_store.py    record_venue, the recording writer
absent    nothing calls AlpacaConnector
absent    nothing calls BrokerBase.record_markets
absent    BotConfig carries no field naming a broker rather than an exchange
absent    nothing hands a broker to BotContainer as its exchange
```

The missing piece is the construction and the wiring, not the connector. One
site builds a crypto connector from stored credentials, in
`src/gui/main_window.py`, and no equivalent site builds a broker one.

One thing a wiring unit must not take from a single page: Alpaca's own
documentation disagrees with itself on which order types carry a fractional
quantity. Its order reference says market and day; its fractional-trading page
says market, limit, stop and stop-limit with day; its orders page says a market
order is refused for a fractional quantity. All three agree that the time in
force is day and that the sell is placeable.

---

## Robinhood

The operator raised Robinhood specifically. Every reading below was fetched from
a Robinhood-owned page on 2026-10-07.

```
crypto      offered, through a separate crypto account. Fractional, buy and
            sell, from one cent. Market, limit, stop and stop-limit
stocks      US listed shares, funds and closed-end funds, plus some warrants,
            preferreds and over-the-counter equities. Fractional, buy and sell,
            above one dollar
commodities commodity futures through a derivatives account, plus commodity
            fund shares as ordinary tickers
forex       no spot currency market. Currencies appear only as a futures class
indices     cash-settled index options on five indices, plus index fund shares
futures     futures across equities, energy, currencies, crypto and metals;
            dated against perpetual is not stated on the page
```

**Is a fractional sell placeable over Robinhood's current public interface?**
Four answers, because the account and the interface differ, and shares and
crypto differ.

```
shares, in the account      yes. "buy or sell a fractional share" above $1
shares, over the interface  not documented. The only public equities route is
                            an agent protocol server, launched 2026-05-27,
                            equities only, and its order tool's quantity
                            parameter was not reachable
crypto, in the account      yes. "buy or sell crypto at fractional amounts"
crypto, over the interface  not established. Robinhood's own support page names
                            a place-crypto-order action in two versions; the
                            endpoint page renders in script and returned one
                            word to a fetch
```

Robinhood does have a public documented crypto trading interface, announced on
2024-05-30, which is after #881's line was written. So the firm's rejection was
wrong twice: the fraction is sellable, and a public programmatic route exists.

On our side Robinhood has no venue id, no connector and no row on his screen.
Its cells are BLOCKED before any venue fact is read, because there is nothing
here to reach it with.

---

## The variant answer — one per sector, not one per venue

The operator's hypothesis holds and his doubt was right.

> Should be able to augment the original to submit crypto orders on all offered
> exchanges and similarly one variant for each sector that work across all
> compatible exchanges for that sector.

> Can have exchange-specific scrumming variants that are called smartly based on
> the selected exchange but doubt this is needed.

Across the fifteen crypto venues there are exactly three differences in order
formatting, and every one already sits at a single site with a generic branch.

```
the market-order capability    read from ccxt's own has map, and it answered
                              for 15 of 15 venues on 2026-10-07
the market-buy price rule      the connector fetches a ticker for any venue
                              with no price; four venues require it, all pass
the client-order-id field      four branches at one site, the fourth being
                              ccxt's canonical name, which ccxt translates
```

**No per-venue variant is needed.** The one venue that looks like it needs one,
Gemini, is already served by the limit-only variant the program holds, selected
from the venue's own capability map rather than from a table. The venue's own
order page confirms the map.

The variants the program names are shaped by market form, not by venue, and that
is the right axis.

```
a market naming a unit count on a venue taking a market order    built
a market on a venue declaring no market order                    built
a market whose smallest order costs more than the excess         not held
a market whose size is a whole share                             not built
a market the venue expires on a date                             not built
```

A sector maps onto those forms, so one variant per sector is the right unit of
work. Nothing found in this audit forces an exception for any single venue.

---

## Which sectors need the whole-unit variant

The recorded size step decides this market by market, and
`sizing.recorded_unit_rule` reads it: a step of one unit or more takes whole
units, a smaller step takes fractions. Measured over the live recording on
2026-10-07, within each sector the program's own classifier assigns.

| Sector | fractional step | whole step |
| --- | --- | --- |
| crypto | 710 | 180 |
| futures_perps | 87 | 140 |
| forex | 17 | 4 |
| commodities | 3 | 1 |
| stocks | 0 | 0, no row recorded |
| indices | 0 | 0, no row recorded |

Every sector holds whole-step markets, crypto included. 180 of 890 recorded
crypto markets take whole units, so the whole-unit variant is not a stocks
feature. It is needed in every sector the platform trades.

Two sectors need it before they can trade at all, and the venue pages agree.

```
stocks    a share is whole wherever a broker declines fractions, and whole on
          Coinbase outside the regular session whatever the product flag says
indices   an index contract is a whole contract
```

And one sector needs a second variant beside it.

```
futures_perps   99 of 227 recorded markets carry an expiry, so the sector needs
                the rolling-position variant as well as the whole-unit one
```

Three venues size a whole contract rather than a fraction, each from its own
system on 2026-10-07: KuCoin's perpetual lot is one contract, MEXC's minimum
volume is one contract, and OKX's crude oil perpetual steps in whole contracts.
A contract that represents a hundredth of a share is still one contract.

---

## Mirrored, then augmented, per sector

Mirroring the Coinbase path gives a sector the order path, the rules reading,
the sizing and the order-type choice. Each sector then needs what the mirrored
path does not carry.

### crypto

Mirrored and complete. The path, the rules, the sizing and the order types all
reach every supported venue.

```
augment   nothing for the path
augment   the whole-unit variant, for the 180 recorded whole-step markets
```

### stocks

```
mirrored  the order path, through a broker constructed the way a crypto
          connector is constructed
augment   a session, because a share does not trade at every hour; the session
          hold is built and the cited table holds one row
augment   a session-dependent unit rule, because Coinbase's own page takes a
          fraction in session and only whole shares outside it
augment   settlement, because a sale's cash is not available at once; the
          unsettled-cash cap is built and the cited table holds one row
augment   the whole-unit variant, for a broker declining fractions
augment   a sector label on the recording, so the bot knows it is not crypto
```

### commodities

```
mirrored  the order path for a fund share and for a tokenised metal, which both
          size as ordinary markets
augment   the rolling-position variant, for a dated commodity contract
augment   the whole-unit variant, for a contract priced above the excess
augment   the equity session and settlement, for a commodity fund share
```

### forex

```
mirrored  complete for the 21 token pairs on Coinbase today
augment   nothing for those pairs
augment   a lot size, if a dedicated currency firm is ever connected, because a
          currency lot is neither a fraction nor a whole unit
```

### indices

```
mirrored  the order path
augment   the whole-unit variant, because an index contract is one contract
augment   the rolling-position variant, because it expires
augment   a sector label on the recording; no index row is recorded today
```

### futures_perps

```
mirrored  the order path, and 128 of 227 recorded markets already place
augment   the rolling-position variant, which decides whether a position rolls
          into the next contract or closes before expiry
augment   the whole-unit variant, for the 140 whole-step markets
augment   a contract size, because a venue's lot can be one contract standing
          for a fraction of the underlying
```

---

## Cells that cannot be judged without placing an order

Three readings in this report stop short of a verdict, and none is guessable.

```
whether a venue's own rejection message differs from the trading library's typed
error, which decides whether a refusal reads as a lost connection or a refused
order

whether a Coinbase equity product's recorded step matches what the venue
enforces at order time; the recording holds no equity row to compare

whether a whole-unit market the program admits is accepted by the venue at two
units, which the opening-position refusal assumes
```

Each needs an order placed, and this unit places none.

---

## What the control measured

One control, and it separates what the venue offers from what our code reaches.

Every cell was counted into exactly one verdict and the four totals above sum to
156, which is 26 venues by 6 sectors. Then a READY cell was traced function by
function, a BLOCKED cell's missing piece was named as a list of present and
absent sites, and both WRONG cells were named.

The WRONG count is two, which is small enough that the method needs proving. The
proof is in the section above: the same check run on a cell that is not wrong
reported no mismatch, and run on a cell with a recording gap reported the
mismatch it would report for a wrong row.

---

## The readings behind the figures

Every figure came from one of four readings, all taken on 2026-10-07.

```
the recording    the runtime market rules, copied and read read-only, through
                 load_document and recorded_rules
the program      the real functions driven on that recording with the home
                 redirected to a scratch directory, the home printed first
the venue maps   each ccxt exchange class's own has map and options, ccxt
                 4.5.85, constructed offline with no venue call
the venue pages  public documentation and public product endpoints, fetched
                 live, each with its date
```

The home redirect was confirmed by printing the resolved home before any import.
The live recording was never opened for writing and the credentials file was
never opened at all. No order was placed, priced, amended or cancelled, and no
authenticated endpoint was touched.

### The order-type reader's own control

`declared_order_types` was driven against three maps it must refuse, so its
fifteen answers are not a reader that answers anything.

```
the capability map is not a dictionary   refused
the market-order value is a string       refused
the limit-order value is False           refused
```

### The sector classifier's own control

`market_asset_class` was driven against six planted records, one per sector, and
answered each correctly.

```
a fiat pair          forex
a coin pair          crypto
an equity product    stocks
a commodity future   commodities
an index future      indices
a perpetual          futures_perps
```

### The venue-document instrument's own control

A page that does not exist was fetched on every documentation host relied on,
before any venue row was trusted. Five crypto hosts returned a clean not-found
with no body, so a missing page is distinguishable from a real one.

Two hosts failed that test and both failures are recorded rather than smoothed
over. One broker documentation host returned a full navigation tree with a
success code for a page that does not exist, so every row from that host rests
on topic-specific quoted content rather than on a success code. One venue's
support host returned a complete page for a fabricated article id, carrying only
the sentence that the article does not exist, and no row rests on that host.

Three further outcomes separate a real absence from our own blindness, and the
split is what makes the ABSENT column trustworthy.

```
not found        the page is gone and the host is alive
forbidden        the host is alive and refusing us; no absence claimed
no DNS record    the host itself is gone; a stronger absence than not found
```

Two developer hosts returned no DNS record: TD Ameritrade's and Fidelity's. The
same instrument read five other brokers' developer portals in the same session,
so it is not blind to developer portals.

Every ABSENT cell also rests on a two-sided reading of the venue's own product
endpoint: a known-present symbol beside a known-absent one on the same URL
shape, so each zero has a matching one.

```
a gold token absent beside a main crypto pair present   huobi, mexc, poloniex
an equity symbol absent beside a gold token present      okx
a currency underlying absent beside three present        okx
a complete symbol list with no equity in it              gemini, bitstamp, bitfinex
```

A truncated product list never produced an ABSENT cell. Where a list did not
return whole, the cell reads BLOCKED with its offering marked unfetched.

### The twenty-eight cells whose venue offering was not fetched

```
binance     indices
cryptocom   commodities, forex, indices
bybit       stocks, commodities, forex, indices
poloniex    stocks, indices, futures_perps
huobi       forex, indices, futures_perps
kucoin      forex, indices
gateio      forex, indices, futures_perps
mexc        forex, indices
bitget      forex
schwab      forex
fidelity    crypto, commodities, forex, indices, futures_perps
```

What blocked each: one venue's futures host refused a US address with no mirror;
three of Bybit's own hosts refused or timed out, leaving it the one venue with
no product established; several product lists returned truncated; and two
broker hosts refused every request including the control. Confirming these is
the first step of the sector-coverage work, not a wiring step.

---

### The twenty-eight cells, each answered from the venue's own page

Every one of the twenty-eight was read again on 2026-10-07. Each verdict rests
on the venue's own published page and on nothing else. No venue was contacted in
any other way. No endpoint was called, no account was opened, no key was held
and no order was placed. The sector each verdict uses is the sector the program
itself assigns, in `src/exchange/ccxt_connector.py`, in `market_asset_class`.

Three answers are possible. The venue offers a product in that sector, the venue
does not offer one, or the venue publishes no answer a reader can quote. The
third answer is written wherever it is true. It is never replaced by a reading
taken from a sibling venue or from a connector library.

| Venue | Sector | Verdict | An order takes |
| --- | --- | --- | --- |
| binance | indices | offers | no published step |
| cryptocom | commodities | offers | a fraction |
| cryptocom | forex | offers | a whole contract |
| cryptocom | indices | offers | no published step |
| bybit | stocks | no published answer | no published step |
| bybit | commodities | no published answer | no published step |
| bybit | forex | no published answer | no published step |
| bybit | indices | no published answer | no published step |
| poloniex | stocks | offers | a fraction |
| poloniex | indices | offers | a fraction |
| poloniex | futures_perps | offers | a whole contract |
| huobi | forex | no published answer | no published step |
| huobi | indices | does not offer | no product to size |
| huobi | futures_perps | offers | a whole contract |
| kucoin | forex | offers | a fraction |
| kucoin | indices | offers | a fraction |
| gateio | forex | offers | no published step |
| gateio | indices | offers | no published step |
| gateio | futures_perps | offers | a whole contract |
| mexc | forex | offers | a fraction |
| mexc | indices | does not offer | no product to size |
| bitget | forex | offers | no published step |
| schwab | forex | no published answer | no published step |
| fidelity | crypto | offers | no published step |
| fidelity | commodities | offers | a whole share |
| fidelity | forex | does not offer | no product to size |
| fidelity | indices | offers | a whole share |
| fidelity | futures_perps | does not offer | no product to size |

#### The three counts

```
offers                18
does not offer         4
no published answer    6
                      ---
total                 28
```

The total is the twenty-eight named above this section. It was counted twice
before any page was read: the matrix carries twenty-eight question-marked cells,
and the named list carries twenty-eight across eleven venue ids. The two
readings agree.

#### The page behind every verdict

Each entry carries the URL and the sentence that page carries.

```
binance, indices — offers
  binance.com/en/support/announcement/binance-futures-launches-defi-composite
  -index-perpetual-contract-with-up-to-50x-leverage-ebee6da5df3946519fdb9ab27
  706d1a4
  "Binance Futures will launch a DEFI/USDT composite index perpetual contract"
  "The underlying asset of the DEFI Composite Index perpetual contract consists
  of a basket of decentralized finance (DeFi) protocol tokens listed on
  Binance."
  The index is a basket of crypto tokens, not an equity index.

cryptocom, commodities — offers
  crypto.com/en/product-news/exchange-tokenized-perpetual-gold-markets
  "Eligible users on the Crypto.com Exchange can now access tokenized gold
  markets through: XAUT (Tether Gold) PAXG (Pax Gold)"
  crypto.com/en/product-news/exchange-tradfi-perpetuals-launch
  "Trade Gold (XAU), Silver (XAG), Platinum (XPT), Palladium (XPD), and Copper
  (XCU)."
  crypto.com/us/crypto/learn/what-is-tokenized-gold-how-does-it-work
  "As low as $0.01. Tokens like PAXG or XAUT are divisible to 18 decimal
  places."

cryptocom, forex — offers
  help.crypto.com/en/articles/8462828-about-strike-options
  "Strike Options are available for the following Forex pairs: AUD/USD,
  EUR/USD, GBP/USD, USD/JPY"
  "The position limit for FX Strike Options is 2,500"
  A contract is priced between US$0 and US$10, so the order is a contract count.

cryptocom, indices — offers
  crypto.com/en/product-news/exchange-tradfi-perpetuals-launch
  "Position on the Nasdaq-100 (QQQ) and S&P 500 (SPY) benchmarks."
  The page names leverage and no order step.

bybit, stocks — no published answer
bybit, commodities — no published answer
bybit, forex — no published answer
bybit, indices — no published answer
  Eight Bybit paths were read on five Bybit hosts. Seven timed out at 60
  seconds, including the host root. One answered.
  bybit-exchange.github.io/docs/v5/intro
  "V5 unifies the APIs of various trading products into one, providing users
  the capability to trade Spot, Derivatives and Options contracts with a single
  API."
  That page names no stock, commodity, currency or index product. The pages
  that would answer are on the hosts that timed out. Bybit is the one venue
  with nothing established.

poloniex, stocks — offers
  poloniex.com/price/Wrapped-Intercontinental-Exchange-Tokenized-Stock-
  (xStock)-wICEx
  "Wrapped Intercontinental Exchange Tokenized Stock (xStock) (wICEx) is a
  cryptocurrency and operates on the X Layer platform."
  The page carries a 24-hour volume and a Trade action on Poloniex.

poloniex, indices — offers
  poloniex.com/price/Wrapped-Nasdaq-Tokenized-ETF-(xStock)-WQQQX
  "Wrapped Nasdaq Tokenized ETF (xStock) (wQQQx)"
  "Buy your first wQQQx on Poloniex"

poloniex, futures_perps — offers
  api-docs.poloniex.com/v3/futures/api/market/get-product-info
  "Contract face value, e.g., 0.001 BTC (per contract) - applicable only to
  futures trading"
  "Order size precision. The amount of futures trades is measured in Cont,
  while the amount of spot trades is measured in the base currency."

  The fraction for the two spot cells above comes from the same host.
  api-docs.poloniex.com/spot/api/public/reference-data
  "minQuantity and minAmount refer to the minimum size of the order."
  The field quantityScale is the decimal precision for quantity.

huobi, forex — no published answer
  HTX's market and support hosts returned an empty body on every path read.
  Its own documentation host answered and names no currency pair.
  huobiapi.github.io/docs/spot/v1/en/
  "Take the symbol BTC/USDT as an example, BTC is the base currency, and USDT
  is the quote currency."
  No fiat quote currency is named anywhere on that page. HTX's own pages name
  a EUR deposit, a EUR withdrawal and a EUR quick trade, none of which is a
  market.

huobi, indices — does not offer
  huobiapi.github.io/docs/usdt_swap/v1/en/
  The page covers USDT-margined swap and futures contracts only. It names
  contract codes of the form "BTC-USDT" and "BTC-USDT-CW" and no index
  product.
  huobiapi.github.io/docs/spot/v1/en/ names no index product either. The index
  HTX publishes is a price reference used to mark a crypto contract.

huobi, futures_perps — offers
  huobiapi.github.io/docs/usdt_swap/v1/en/
  Swap contracts are perpetual and take the form "BTC-USDT". Futures contracts
  are deliverable and take the form "BTC-USDT-CW" for the current week and
  "BTC-USDT-NQ" for the next quarter. The page names no contract-size field.

kucoin, forex — offers
  kucoin.com/announcement/en-eur-trading-pairs-to-go-live-on-kucoin
  "The BTC/EUR, ETH/EUR and USDT/EUR fiat trading pairs will be released on
  KuCoin at 12:00:00(UTC) on Jun 28, 2022"
  USDT/EUR is the row with two currency legs.

kucoin, indices — offers
  kucoin.com/announcement/en-kucoin-spot-to-list-xstocks-spyx-crclx-tslax-
  mstrx-nvdax
  "SPYX/USDT, CRCLX/USDT, TSLAX/USDT, MSTRX/USDT and NVDAX/USDT"
  "SPYX/USDT, CRCLX/USDT, and TSLAX/USDT will open at 09:00 on July 18, 2025
  (UTC)"
  SPYX tracks the S&P 500 ETF. One other KuCoin page disagrees: its
  how-to-buy page for the same asset reads "Although KuCoin currently does not
  support SP500 xStock (SPYX)". The listing announcement is the product record
  and the how-to-buy page is a guide, so the announcement decides the cell.

  The fraction for both KuCoin cells comes from KuCoin's own order rules.
  kucoin.com/docs-new/rest/spot-trading/market-data/get-all-symbols
  "baseIncrement": "0.00000001" and "baseMinSize": "0.00001"

gateio, forex — offers
gateio, indices — offers
  gate.com/announcements/article/49240
  "contracts for difference (CFD) covering traditional financial assets,
  including gold, foreign exchange, stock indices, commodities and popular
  equities."
  gate.com/docs/developers/apiv4/en/
  The same host names "comprehensive CFD API endpoints for MT5-based forex and
  CFD trading". Neither page names an order step.

gateio, futures_perps — offers
  gate.com/docs/developers/apiv4/en/
  The documentation lists "Spot & Margin, Perpetual Futures, Delivery Futures,
  CFD, Stock, Options, Unified, Alpha, CrossEx".
  "order_size_min, order_size_max, trade_size, position_size"
  A futures order is a contract count against a quanto_multiplier.

mexc, forex — offers
  mexc.com/announcements/article/mexc-will-launch-eur-related-trading-pair-on-
  mexc-spot-17827791519517
  "USDT/EUR" at "2024-11-06 09:00 (UTC)" and "USDC/EUR" at "2024-11-07 07:00
  (UTC)"
  mexcdevelop.github.io/apidocs/spot_v3_en/
  "baseSizePrecision": "0.0001" is the min order quantity.

mexc, indices — does not offer
  mexc.com/price/nasdaq-xstock
  The page marks Nasdaq xStock (QQQX) "Unlisted" and states "This token data is
  sourced from third parties. MEXC acts solely as an information aggregator."
  mexc.com/stocks
  "RealStocks (held via a regulated broker partner), Tokenized Stocks that
  trade 24/7 with self-custody, and Stock Futures with up to 200x leverage."
  That list names equities and equity futures and no index product.

bitget, forex — offers
  bitget.com/support/articles/12560603776372
  "USDT/EUR, BTC/EUR, ETH/EUR, USDT/GBP, BTC/GBP ETH/GBP"
  USDT/EUR and USDT/GBP are the rows with two currency legs. Bitget's own API
  documentation host served an account overview on every spot symbol path read,
  so the order step has no answer this method can quote.

schwab, forex — no published answer
  Five Schwab paths were read on three Schwab hosts and every one refused.
  schwab.com/forex and schwab.com/futures/forex-trading and
  schwab.com/node/42546 answered "We're sorry, but we were unable to authorize
  your request." content.schwab.com returned 403 and international.schwab.com
  returned 403. The page exists and this method cannot read it, so no absence
  is claimed.

fidelity, crypto — offers
  fidelity.com/crypto/overview
  "Buy, sell, and transfer crypto like bitcoin, ethereum, and solana, all
  backed by industry-leading security."
  The page names no order step.

fidelity, commodities — offers
  fidelity.com/trading/investment-choices/overview
  The page lists "Precious metals", described as "Buy gold, silver, platinum,
  and palladium".

fidelity, forex — does not offer
  fidelity.com/trading/investment-choices/overview
  The page lists every investment type Fidelity offers and names no currency or
  forex product.
  fidelity.com/trading/commissions-margin-rates
  The page prices stocks, ETFs, options, bonds, CDs, mutual funds and U.S.
  Treasury, and names no forex product. Its one foreign-exchange line is
  "Foreign exchange wire: Up to 3% of principal", a wire fee and not a market.

fidelity, indices — offers
  fidelity.com/mutual-funds/fidelity-funds/why-index-funds
  The page lists index funds by ticker, among them "Fidelity 500 Index Fund
  (FXAIX)" and "Fidelity ZERO Total Market Index Fund (FZROX)".
  A fund share is a whole share.

fidelity, futures_perps — does not offer
  fidelity.com/trading/commissions-margin-rates
  The page names no futures product.
  fidelity.com/trading/investment-choices/overview
  The page names no futures product.
```

#### Four cells move verdict

BLOCKED means the venue lists the product and our code cannot reach it. Four of
the twenty-eight hold no product, so ABSENT is the verdict they take.

| Cell | The matrix reads | The research reads |
| --- | --- | --- |
| huobi, indices | BLOCKED? | ABSENT |
| mexc, indices | BLOCKED? | ABSENT |
| fidelity, forex | BLOCKED? | ABSENT |
| fidelity, futures_perps | BLOCKED? | ABSENT |

OVERTAKEN, and the four totals above are kept as written. The totals that follow
from this research are BLOCKED 102 and ABSENT 36, with READY 16 and WRONG 2
unchanged. The sum is still 156. Nothing the program does changes, because the
program reaches none of the four either way.

#### The hosts that refused, and the absences not claimed

Two venues answered nothing a verdict can rest on, and both are recorded as a
refusal and not as an absence.

```
bybit     7 of 8 paths timed out at 60 s, the host root among them
schwab    5 of 5 paths refused on 3 hosts, 2 of them with 403
```

Two further hosts served a page body that carries no product content. HTX's
market and support hosts returned an empty body on every path read. Bitget's API
documentation host served an account overview on every path read. Neither
produced an absence.

#### This method's own two-sided control

The method is one reading: fetch the venue's own page and quote the sentence it
carries. It was proved able to return both answers before any cell was trusted.

```
it can return no published answer
  bybit-exchange.github.io/docs/v5/acervator-control-page-does-not-exist
  HTTP 404 Not Found, no body
  kucoin.com/announcement/en-kucoin-supports-euro-eur-fiat-trading
  HTTP 404 Not Found, no body

it can return a confirmation
  the cell read was binance and commodities, already established in the matrix
  binance.com/en/trade/PAXG_USDT
  "Trade PAXG/USDT Spot | Crypto, bStocks & tCommodities | Binance"
  the tokenised gold market read back as listed
```

One host failed the control and no verdict rests on its status code. A fabricated
article id on Binance's support host returned the live FAQ landing page with a
success code. The Binance verdict above therefore rests on the quoted content of
the announcement page and not on the code that page returned.

---

## One finding about a page this report does not change

The manual's venue page states that Coinbase serves no forex and that forex has
no connected venue. The program's own classifier reads 21 forex markets in the
live Coinbase recording, and the surface's own comment records 20, so that
sentence is contradicted by the code beside it. The venue's own product list
agrees with the page on the narrow point that no market has two national-currency
legs, which makes this a disagreement about what counts as a currency market.

The page is not edited here. Another unit holds the manual.
