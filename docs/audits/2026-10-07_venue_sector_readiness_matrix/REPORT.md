# Venue and Sector Readiness Matrix

**Mode: Reference.**

This report covers issue #881. It establishes, per exchange and per sector,
whether a bot can place an order there today. It builds nothing. No file under
`src/`, `main.py`, `tools/` or `dev_harness/` changed, and no page under
`docs/manual/` changed.

**FALSIFICATION.** This report is wrong if any cited path or symbol is absent
from the tree it ships on, if a verdict called READY turns out to refuse a real
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

A fractional sale is a property of a venue **and a sector**, not of a venue.
A broker that cannot sell a fraction of a share may sell a fraction of a coin.
Rejecting the firm on a share limit removes its other sectors with it.

The cycle test has two answers per venue per sector and neither rejects a venue.

```
fractional sell available   the original scrumming logic works there
whole units only            that sector needs the whole-unit variant
```

A venue leaves a sector only when it lists no product in that sector, or when no
order path our code can reach exists for it.

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

The recorded rules hold one venue. The store is `src/exchange/market_rules_store.py` and the file sits under the
runtime home, read through `market_rules_store.load_document`.

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
records them exists and the recording he runs against predates it.

Classifying all 1142 recorded symbols through the program's own
`market_asset_class` gives the sector split the program would read if the labels
were written.

```
crypto           890
futures_perps    227   99 of them expiring
forex             21   EURC, AUDD, TGBP and XSGD pairs
commodities         4   PAXG, tokenised gold
stocks              0
indices             0
```

Two caveats on that split, and both are limits of the reading, not of the code.
The recording stores no product type, so a Coinbase equity product would be read
as crypto by this reconstruction rather than as stocks. The recording stores no
futures asset label either, so a commodity-underlying or index-underlying
contract is read as futures_perps.

Nothing filters a market list by sector. `market_asset_class` has exactly two
callers and both are inside `CCXTConnector.get_markets`, writing the recording.

```
market_asset_class        2 callers, both writing the recording
recorded_classes          1 reader, BotContainer._asset_class
venue_served_classes      0 readers outside asset_class_surface
```

The bot wizard asks the operator for a sector and drops the answer.
`BotWizard.get_config` returns an asset-class key and a sizing-mode key;
`BotConfig` declares neither, and `bot_config_kwargs` keeps only the fields
`BotConfig` declares.

```
BotConfig fields naming a venue or sector:  exchange_id, and nothing else
```

---

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
six of them and every other venue carries one.

Two venue ids name one firm. `EQUITY_VENUES` holds both of Interactive Brokers'
ids, so one firm occupies two rows on his screen.

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

### Crypto — 15 venues, all READY in code

Every one of the fifteen reaches the same path. A connector constructs for any
id in `SUPPORTED_EXCHANGES`, the settings dialog offers all fifteen, and
`get_markets` records any of them on first connect.

The order-type reading was taken from each venue's own ccxt capability map,
ccxt 4.5.85, on 2026-10-07. The reader answered for 15 of 15.

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

Gemini declines a market order and our code already answers that: the record
reads limit only, `venue_variant` selects the limit-only variant,
`VARIANTS_BUILT` holds it, and `variant_replaces_market_order` prices a limit
at the venue's own tick. No second code path is needed for Gemini.

The venue's own options also name which venues price a market buy by its total
cost rather than its size. Read from each ccxt class on 2026-10-07.

```
market buy requires a price, True    coinbase, gateio, huobi, poloniex
market buy requires a price, False   okx
the option is unset                  the other ten
```

The connector fetches a ticker for every market buy that arrives with no price,
whatever the venue, so all four are already covered.

Verdict: **15 READY**. The nine US-refused accounts are an account matter, not
a code matter, and they are stated in the table rather than folded into a
verdict.

### Stocks — 1 listed venue serving no recorded product, 11 venues with no path

Coinbase lists stocks and its products endpoint answers equity products. The
recording holds none of them, nothing filters a product list by sector, no
session row exists for the pair, and the cited rule names whole units while the
whole-unit variant is not one the program holds.

```
the cited unit rule for stocks on coinbase    whole
the cited session for stocks on coinbase      absent, so nothing holds an order
the variants the program holds                limit-only order, none
the whole-unit variant                        not held
```

Alpaca is the one broker whose connector is written. Nothing constructs it.
`AlpacaConnector` appears once outside its own module, in that class's own
docstring. `StockMainWindow` is defined and nothing builds it.

The other brokers have no connector module at all. `BrokerBase.place_order` is
abstract and Alpaca is its only subclass.

Verdict: **12 BLOCKED** — coinbase, alpaca, etrade, fidelity, ibkr,
interactivebrokers, schwab, tastytrade, webull, tradier, robinhood, and
tdameritrade is treated separately below. The missing piece differs by venue and
each is named in the issue this report opens.

### Commodities — 1 listed venue with a partial product, 11 with no row

Coinbase lists commodities and the recording holds four tokenised gold rows.
The venue also lists commodity-underlying futures; the manual records 21 of them
on 4 October 2026, and none is in the live recording.

```
recorded commodity rows, by the program's own reader      4
the manual's reading of the venue's commodity contracts   21
```

The four tokenised rows size as ordinary spot markets: three carry a fractional
step, one carries a whole step, all four read market and limit, and
`venue_variant` selects a variant the program holds. An order on those four
would place.

The 21 contracts would not. They carry a whole step and an expiry, and an
expiring market selects the rolling-position variant, which the program does not
hold.

Every equity broker reaches commodities as a fund share, and the program lists
none of them under commodities.

Verdict: **1 BLOCKED** for coinbase, because the sector's contract half refuses
and nothing filters its product suite. **11 BLOCKED** for the brokers that list
commodity fund shares and that the program lists under no such sector.

### Forex — 1 READY venue

Coinbase lists forex and the program reads 21 forex markets in the live
recording: euro, Australian dollar, pound and Singapore dollar tokens against
dollar quotes. `underlying_code` maps each token to the currency it redeems for.

```
recorded forex rows                       21
with a fractional step                    17
with a whole step                          4
order types                               market and limit
the cited unit rule for forex on coinbase  fractional
```

The path reaches them. The rules are recorded, the step is applied, the variant
is one the program holds, and the cited rule agrees with the recorded step on
17 of 21.

Verdict: **1 READY** for coinbase. The three dedicated forex firms the manual
names have no venue id and no connector, and the program lists no broker under
forex, so those are BLOCKED cells counted under the brokers.

### Indices — 1 listed venue, no recorded product

Coinbase lists indices. The program's own comment in `asset_class_surface`
records its classifier answering indices for six of the venue's products. The
live recording holds none, because it stores no futures asset label.

An index contract carries a whole step and an expiry, so it selects the
rolling-position variant that the program does not hold.

Verdict: **1 BLOCKED** for coinbase.

### Futures and perpetuals — 1 listed venue, half the sector refusing

Coinbase lists futures and perpetuals and the recording holds 227 of them, 99
with an expiry. This is the sector with the most recorded product and the
sharpest split.

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

Verdict: **1 BLOCKED** for coinbase, on the dated half. Thirteen crypto venues
list perpetuals and the program lists none of them under the sector, so those
are BLOCKED cells.

### Tradier, Robinhood and TD Ameritrade

Tradier appears twice in the whole tree, both times in the manual's venue page,
and never in source. It has no venue id, so the program lists it under nothing.

Robinhood appears nowhere in the tree at all. The operator raised it, so its
offering is sourced in its own section below.

TD Ameritrade has a venue id and a row on his screen under stocks. The manual
records its API discontinued on 10 May 2024, registrations not carried over, and
the firm folded into Schwab. A venue id naming a firm that can take no order at
all is a wrong row.

---

## The four totals

One hundred fifty-six cells, each counted once.

```
READY       16
BLOCKED     48
ABSENT      90
WRONG        2
```

READY is the 15 crypto venues plus Coinbase forex. BLOCKED is every cell where a
venue lists the product and our code cannot place the order. ABSENT is every
cell where the venue lists no product in that sector. WRONG is two cells and
both are named.

### Every WRONG cell

```
tdameritrade, stocks           the firm's API closed on 10 May 2024 and the
                               firm folded into Schwab; the id names no venue
                               that can take an order, and the row is on his
                               screen today

interactivebrokers, stocks     a second id for the firm the other id already
                               names; one firm occupies two rows, so one of the
                               two is wrong
```

Both are rows the operator sees now. Neither is a venue that lists no product;
both are venue ids naming no reachable venue, which is the same defect the
WRONG column exists to catch.

### How the method could have found a WRONG cell

The WRONG count is small, so the method needs showing. Take a venue and sector
the program records and confirm the venue serves it.

Coinbase and crypto: the program lists it, the recording holds 890 crypto rows
read through the program's own classifier, and the venue's spot product list
answers them. The cell is not wrong, and the check said so.

Now the same check with the sector moved. Coinbase and indices: the program
lists it, and the live recording holds zero index rows. The check reported a
mismatch, which is exactly what it would report for a genuinely wrong row. It
reads BLOCKED rather than WRONG only because the venue does list index
contracts — the program's own comment records six — so the mismatch is in our
recording. The same check applied to an id naming no reachable venue reported
WRONG, and it did so twice.

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

Alpaca and stocks. The venue lists equities, the fractional sell is documented,
the connector is written, and nothing constructs it.

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
site builds a crypto connector from stored credentials, in `src/gui/main_window.py`, and
no equivalent site builds a broker one.

---

## Robinhood

The operator raised Robinhood specifically. Its facts are sourced in the venue
documentation section below, with the page and the date for each.

Robinhood has no venue id in this tree, no connector, and no row on his screen.
Its cells are BLOCKED on our side before any venue fact is read, because there
is nothing here to reach it with.

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

**No per-venue variant is needed for crypto.** The one venue that looks like it
needs one, Gemini, is already served by the limit-only variant the program
holds, selected from the venue's own capability map rather than from a table.

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

Two sectors need it before they can trade at all.

```
stocks    a share is a whole unit wherever a broker declines fractions
indices   an index contract is a whole contract
```

And one sector needs a second variant beside it.

```
futures_perps   99 of 227 recorded markets carry an expiry, so the sector needs
                the rolling-position variant as well as the whole-unit one
```

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
augment   a lot size, if a dedicated forex firm is ever connected, because a
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

Every cell was counted into exactly one verdict and the four totals are given
above. Then a READY cell was traced function by function, a BLOCKED cell's
missing piece was named as a list of present and absent sites, and both WRONG
cells were named.

The WRONG count is two, which is small enough that the method needs proving. The
proof is in the section above: the same check run on a cell that is not wrong
reported no mismatch, and run on a cell with a recording gap reported the
mismatch it would report for a wrong row.

The venue-document instrument was calibrated separately. A fetch of a page that
does not exist on a venue's own documentation host was run first, so an absence
reported here is one the instrument can tell from a block page.

---

## The readings behind the figures

Every figure in this report came from one of four readings, all taken on
2026-10-07.

```
the recording    the runtime market_rules.json, copied and read read-only,
                 through load_document and recorded_rules
the program      the real functions driven on that recording with the home
                 redirected to a scratch directory, Path.home() printed first
the venue maps   each ccxt exchange class's own has map and options, ccxt
                 4.5.85, constructed offline with no venue call
the venue pages  public documentation, fetched live, each with its date
```

The home redirect was confirmed by printing the resolved home before any import.
The live recording was never opened for writing and the credentials file was
never opened at all.

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

---

## One finding about a page this report does not change

The manual's venue page states that Coinbase serves no forex and that forex has
no connected venue. The program's own classifier reads 21 forex markets in the
live Coinbase recording, and the surface's own comment records 20, so that
sentence is contradicted by the code beside it.

The page is not edited here. Another unit holds the manual.
