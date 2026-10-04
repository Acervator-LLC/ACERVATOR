# Market Inspector Tab

Reference. The higher-timeframe scanner, the ATA-SMP publisher and the topology
proposal pane. First step of [the promotion pipeline](promotion-pipeline.md).

## What builds it

`MarketInspectorTabMixin._build_market_inspector_tab` in
`src/gui/main_tabs/market_inspector_tab.py` constructs the tab and wires its
three injection points before adding it to the row.

The tab splits horizontally. The left half holds the scanner and the ATA-SMP
publisher. The right half holds the approval bucket, the proposal cards and the
Phantom Bot zone.

## The six zones

The screen draws six zones, three down each side. ATA-SMP, Opposing Trades and
Multi-Exchange Arbitrage run down the left. ATA-SMP Ready to Send, Bot Swarm
Topologies and Phantom Bot HTF Signals run down the right. One function names
each side in screen order, so a zone cannot appear on one host and go missing on
the other.

`src/gui/main_tabs/market_inspector_surface.py` — the rows each side draws

```python
def left_module_rows(
    run: Any,
    scan_state: Any,
    pair_count: Any,
    connectors: Any,
    sector_count: Any = 0,
) -> list:
    """The three left-side regions as key, title and status, in screen order."""
```

The left pane divides its height by a fixed share. ATA-SMP takes two shares and
the other two zones take one each.

`src/gui/main_tabs/market_inspector_surface.py` — the heights the zones take

```python
LEFT_MODULE_SHARES = (2, 1, 1)
```

Every zone works the same way. It shows one entry at a time, with a left arrow, a
right arrow and a line saying which entry is on screen out of how many the zone
holds. An arrow press wraps at both ends, so the last entry steps forward to the
first.

`src/gui/main_tabs/market_inspector_surface.py` — what one arrow press does

```python
def step_to(at: Any, total: Any, by: Any) -> int:
    """The entry index one arrow press moves to, wrapping at both ends."""
```

Clicking the entry opens it. The four expanded lines are the test, the window,
the result, and why that answer let the entry through. Every zone's open entry
takes one height whatever buttons it carries.

`src/gui/main_tabs/market_inspector_surface.py` — the four names an open entry carries

```python
DETAIL_TEST_NAME = "Test"
DETAIL_WINDOW_NAME = "Window"
DETAIL_RESULT_NAME = "Result"
DETAIL_REASON_NAME = "Why it is here"
```

A zone holding nothing keeps its waiting sentence as the headline and reports a
position of "0 of 0". An empty zone reads as a state rather than as a zone that
failed to draw.

| Zone | What its line says while it holds nothing |
| ---- | ---------------------------------------- |
| ATA-SMP | "No sector added. Name one and press Scan Now." |
| Opposing Trades | The scan state: not asked, running, or finished with its three counts |
| Multi-Exchange Arbitrage | The venues in reach, or that no exchange source is wired |
| ATA-SMP Ready to Send | "The last scan left no post. Nothing to approve." |
| Bot Swarm Topologies | One of three sentences, by scan state |
| Phantom Bot HTF Signals | "Phantom Bot source not wired." |

The Qt build gives every zone a `ProposalStepper`. The two web hosts give every
zone a `ZoneStepper`. Both are written from one description of the zone, so a
zone's lines are decided in one place.

`src/gui/market_inspector.py` — the Qt widget every zone uses

```python
class ProposalStepper(QWidget):
    """One zone's entries shown one at a time, with arrows and a expansion.
```

`src/gui/main_tabs/market_inspector_surface.py` — the rest of the zone description

```python
LEFT_MODULE_KEYS = (ATA_SPM_MODULE, OPPOSING_TRADES_MODULE, ARBITRAGE_MODULE)

def right_zone_rows(run: Any, bucket: Any = None) -> list:
    """The three right-side zones as key, title and status, in screen order."""

def zone_view(run: Any, bucket: Any, board: Any) -> dict:
    """One zone's headline, position line, counter, entry rows and actions."""
```

The window sizes each group from `LEFT_MODULE_SHARES`, and the page turns the same
tuple into a flex value, reading an equal share for anything that is not a positive
number.

`src/gui/web/market_inspector.js` — the share one zone takes on the page

```javascript
const EQUAL_SHARE = 1;
const SHARE_FLEX_TAIL = 0;
function shareFlex(share) { ... }
```

## Left half: the scanner

### The signal tables

A filter row carries a Refresh button and an "Include active markets" checkbox.
The default hides the markets already under a bot, which keeps the table on entry
opportunities.

`HTF Signals` lists one row per market: Asset, Signal, Score, Daily, Weekly,
Active.

`Opposing Pairs (cointegration, Engle-Granger + Johansen, p<=0.05)` lists Long
side, Short side, Method, Window, Statistic, Correlation and the combined score.

### The ATA-SMP control row

The zone draws three lines. The ticker field sits on the first line with the
sector menu beside it. The four timeframe buttons sit under their own heading on
the second. Scan Now, Scan All and Settings sit on the third. Every control sits
inside the pane from 700 pixels of tab width upward, with no scroll bar.

`src/gui/main_tabs/market_inspector_surface.py` — the three line names

```python
TIMEFRAME_TITLE = "Timeframe"
SECTOR_ROW_PART = "sector-row"
SCAN_ROW_PART = "scan-row"
```

Each group of buttons breaks at the count the pane's own width holds. The window
asks the same function the page asks, so both hosts wrap at one count.

`src/gui/main_tabs/market_inspector_surface.py` — how many cells fit a line

```python
def columns_for(
    available: int, cell: int, spacing: int = SETTINGS_ROW_SPACING_PX
) -> int:
```

Both hosts read the same pane width, because the window sets the splitter handle to
the theme's own value rather than to the toolkit's default, and the page leaves the
same gap.

| Tab width | Venue and category buttons on a line | Settings rows on a line |
| --------- | ------------------------------------ | ----------------------- |
| 700 | 2 | 1 |
| 900 | 3 | 1 |
| 1400 | 6 | 2 |
| 1960 | 8 | 2 |

`src/gui/main_tabs/market_inspector_surface.py` — the gap between the two panes

```python
SPLITTER_HANDLE_PX = 7
BUTTON_COLUMNS = 4
```

The timeframe grid wraps after `BUTTON_COLUMNS` cells, as the Level 1 groups do. A
ticked timeframe, a held venue credential and the chosen asset class are one state
and take one look, and the field's own lines take one size in both hosts.

`src/gui/main_tabs/market_inspector_surface.py` — the look a pressed control takes

```python
CHECKED_BUTTON_STYLE = (
    f"background:{ds.PRIMARY}; color:{ds.ON_PRIMARY}; border-color:{ds.PRIMARY};"
)
DETAIL_STYLE = "color: #ccc; font-size: 11px;"
```

Every row of the field takes that one size, in both hosts.

### The asset classes and their sectors

Four classes ship. The published taxonomies name them: the S&P GSCI methodology
makes commodities an asset class with sectors under it, and ISO 10962, the CFI
standard, sorts each product by its own form rather than by a class of its own.

> S&P GSCI groups energy as petroleum and natural gas

`src/trading/ata_spm.py` — the class set every button, menu and scan reads

```python
ASSET_CLASSES = (CLASS_CRYPTO, CLASS_STOCKS, CLASS_COMMODITIES, CLASS_FOREX)
```

The operator asked for the published names rather than this project's own.

> I just want to adopt the standard categorization and language so that the implementation is professional and accurate...

A retired class name still resolves.

| The name given | The class it answers |
| -------------- | -------------------- |
| `metals` | commodities |
| `energy` | commodities |
| `derivatives` | crypto, because a futures product takes the class of its underlying |
| a name neither taxonomy holds | none; the press is refused |

A refused name runs no scan, so no class is scanned with no timeframes behind it.

`src/trading/ata_spm.py` — the class one name resolves to

```python
def asset_class_named(name: Any) -> str:
```

`src/trading/ata_asset_maps.py` — the sector one name resolves to

```python
def sector_named(typed: Any) -> str:
```

The sectors each class holds, and how many markets the shipped map lists in each. A
crypto list and a stocks list are read at press time instead, from the venue's own
products list and the screener, so those two counts move with the venue.

| Class | Sector | Markets the map lists |
| ----- | ------ | --------------------- |
| crypto | by sector tag | read at press time |
| stocks | portfolio | 47 |
| commodities | energy | 4 |
| commodities | industrial metals | 2 |
| commodities | precious metals | 8 |
| commodities | agriculture | 0 |
| commodities | livestock | 0 |
| forex | major | 7 |
| forex | minor | 21 |
| forex | exotic | 0 |

A sector holding no market is not drawn as a sector the scan can walk. Its count
is drawn under the ticker field with the reason it holds nothing.

`src/gui/main_tabs/market_inspector_surface.py` — the line an empty sector takes

```python
TICKER_EMPTY_SECTORS_FORMAT = "{sectors}: 0 market(s) listed, {reason}."
```

Commodities reads "agriculture, livestock: 0 market(s) listed, no fund listed in
dollars holds them, and this map carries no futures." Forex reads "exotic: 0
market(s) listed, no pair is named for this tier yet."

One function builds that line for any class, from the sectors the map declares and
lists nothing for.

`src/gui/main_tabs/market_inspector_surface.py` — the line, and what it reads

```python
def empty_sector_line(asset_class: Any) -> str:
    """``TICKER_EMPTY_SECTORS_FORMAT`` over ``ata_asset_maps.unlisted_sectors``."""
```

`src/trading/ata_asset_maps.py` — the sectors a class holds, and the ones it lists nothing for

```python
def sectors_for(asset_class: Any) -> tuple:
def unlisted_sectors(asset_class: Any) -> tuple:
```

`src/trading/ata_spm.py` — the name a typed sector's own rows carry

```python
def sector_key_of(rows: Any, typed: Any) -> str:
```

A typed sector takes the name its own rows carry, so a retired sector name draws the
headline of the sector holding its markets.

### What each class can reach, and what it can trade

Every class answers two questions apart. The first is whether a retail trader can
reach the market from home. The second is whether a venue is wired here that can
place an order on it. ATA-SMP scans a market either way, for its charts.

| Class | Reachable from home | Venue wired |
| ----- | ------------------- | ----------- |
| crypto | yes, a retail account on a crypto venue takes orders over its API | yes, the connector the live bots trade on |
| stocks | yes, a retail broker account takes equity orders over its API | no, no broker connector is reachable |
| commodities | yes, every listed row is an ETF share a retail broker account buys | no, the same missing broker connector |
| forex | yes, a retail account at a registered dealer takes spot orders | no, no dealer connector exists |

The four commodity spot pairs carry no venue at all. A futures row in any class is
reachable and unwired: the venue takes orders on its US futures products, and the
futures adapter reads candles and places none.

### The form each listing carries

Every row draws the form its product takes. The form rides on the row; no control
was added and no menu gained an entry.

| Listing | Form drawn |
| ------- | ---------- |
| a crypto pair on the exchange | `spot` |
| a commodity spot pair | `spot` |
| a fund share | `ETF` |
| a portfolio equity or a screener quote | `equity` |
| a dated venue contract | `future` |
| a perpetual venue contract | `perpetual` |

`src/trading/ata_asset_maps.py` — where a futures product is placed

```python
def futures_placement(product: Any) -> tuple[str, str, str]:
    """The underlying, the class and the sector one futures product takes."""
```

A root neither the record nor the root table resolves is held back, named on the
order line and counted. Nothing is guessed.

### The ticker field

The field names one market, read on demand. Typing narrows a list the program
already holds. Nothing is fetched on a keystroke and no venue is asked.

`src/gui/main_tabs/market_inspector_surface.py` — the field and what it says

```python
TICKER_FIELD_PLACEHOLDER = "Ticker"
TICKER_FIELD_TOOLTIP = (
    "Name one market to read on demand. Typing offers the tickers the "
    "sector menu beside it holds."
)
```

The operator named the field, and said what it is for.

> Sector Field - Incorrect naming... This entry field is for reading specific, individual markets on demand and will require TICKER recognition...

Each offer names its class, its form, whether a bot can deploy there, and whether
a bot can size a scrum on it. Offers come prefix matches first, the chosen class
first inside each, then matches holding the text later in the name.

`src/gui/main_tabs/market_inspector_surface.py` — one offered row

```python
TICKER_OFFER_FORMAT = "{symbol}  ({asset_class} · {form} · {deploy} · {tradeable})"
TICKER_MATCH_LIMIT = 8
```

Typed text is folded to upper case, outer spaces are stripped, and a hyphen, an
underscore or an inner space reads as a slash. The folded text is matched against
each class's names, the chosen class first.

`src/gui/main_tabs/market_inspector_surface.py` — the separators one name may carry

```python
TICKER_SEPARATORS = ("-", "_", " ")
TICKER_JOIN = "/"
```

| Typed | Resolves to | Class |
| ----- | ----------- | ----- |
| `a15`, `A15/USD`, `a15-usd`, `A15USD` | A15 on the exchange | crypto |
| `gld`, `GLD/USD` | GLD on the chart venue | commodities |
| `eur/usd`, `eurusd`, ` eur usd ` | EUR/USD on the chart venue | forex |
| `A15/EUR` | nothing; that quote is not one the connector route reads | — |
| `ZZZQ` | nothing; no class lists it | — |

A name the chosen class does not hold but another class does moves the class box
to the class holding it, redraws the four timeframe buttons for that class, and
writes one line to the Activity Log.

`src/trading/ata_spm.py` — the line a move writes

```python
CLASS_MOVED_TEXT = (
    "ATA-SPM ticker {ticker} is listed under {placed}; "
    "the class box moves from {chosen} to {placed}"
)
```

`src/gui/main_tabs/market_inspector_surface.py` — the rows one keystroke offers

```python
def ticker_offers(typed: Any, asset_class: Any, connectors: Any = None) -> TickerOffers:
    """The offered rows and the names left off them, together."""

def class_tickers(asset_class: Any) -> list:
def class_walk(asset_class: Any) -> list:
```

`class_walk` answers `ata_spm.ASSET_CLASSES` with the chosen class first, so a typed
name is matched against that class before any other.

`src/gui/main_tabs/market_inspector_surface.py` — where one typed name lands

```python
def market_listing(ticker: Any, asset_class: Any) -> Optional[Any]:
    """The ``ata_spm.TickerPlacement`` a typed ticker names, across every class."""

def placements_of(typed: Any, asset_class: Any) -> list:
```

`src/trading/ata_spm.py` — what a placement carries

```python
@dataclass(frozen=True)
class TickerPlacement:
    """One typed name, the listing it resolved to, and the class holding it."""

    listing: Any
    asset_class: str
    typed: str = ""
```

A name no class holds is refused under the field, nothing runs, and no venue is
asked.

`src/trading/ata_spm.py` — the refusal a name no class holds takes

```python
TICKER_UNHELD_FORMAT = "No class lists ticker {ticker}. Pick one the field offers."
```

`src/gui/main_tabs/market_inspector_surface.py` — the line a sector with no list takes

```python
TICKER_NO_LIST_FORMAT = "No ticker list for {sector}. A typed name still scans."
```

A sector whose list is read at press time says so instead, and a typed name still
scans.

`src/gui/main_tabs/market_inspector_surface.py` — the line a read-at-press list carries

```python
TICKER_PRESS_LIST_FORMAT = (
    "Scan Now reads the {sector} list from {source}. A typed name still scans."
)

def ticker_note(asset_class: Any, connectors: Any = None) -> str:
    """The one line under the field: the empty sectors, the press list, or a refusal."""

def ticker_offer(listing: Any, asset_class: Any, connectors: Any = None) -> str:
```

The Qt completer shows the offered row and writes the bare symbol into the field. The
page's option carries the offer as its label and the symbol as its value.

### Whether a bot can size a scrum

One function answers whether a bot can size a scrum on a market. A scrum sells the
excess above a dollar target, and a venue accepts an order only at or above its
own published minimum, stepped onto its own increment.

`src/trading/scrumming/sizing.py` — the three answers

```python
def tradeable_answer(
    rules: Any, price: Any = None, excess_usd: float = REFERENCE_SCRUM_EXCESS_USD
) -> str:
```

| Answer | Drawn as | What it means |
| ------ | -------- | ------------- |
| yes | `can size a scrum` | the smallest order the venue accepts costs no more than the excess |
| no | `cannot size a scrum` | it costs more, so a scrum would have nothing to submit |
| unknown | `size rules not read` | no market record was obtained |

An unknown is never read as either other, and such a market stays on the list. A
market answering no is kept off the offered list, counted and named.

`src/gui/main_tabs/market_inspector_surface.py` — the line a refused market takes

```python
TICKER_UNTRADEABLE_FORMAT = (
    "{count} market(s) left off, the smallest order costs more "
    "than a scrum's excess: {names}"
)
```

The excess the answer measures against is the largest one the saved fleet can
produce. The highest Target Balance in the fleet is 350 dollars and every bot
carries the same 5 per cent scrumming interval, so the largest excess is 17
dollars 50.

`src/trading/scrumming/sizing.py` — the reference excess

```python
LARGEST_FLEET_TARGET_USD = 350.0
FLEET_SCRUMMING_INTERVAL_PCT = 5.0
REFERENCE_SCRUM_EXCESS_USD = scrumming_interval_usd(
    LARGEST_FLEET_TARGET_USD, FLEET_SCRUMMING_INTERVAL_PCT
)
```

The venue's published minimum is ceiled onto its own increment, valued at the
venue's own last price, and never falls under the venue's minimum order cost.

`src/trading/scrumming/sizing.py` — the smallest order the venue accepts

```python
def smallest_order_usd(rules: Any, price: Any) -> Optional[float]:
```

`src/exchange/market_inspector_fetcher.py` — where its rules come from

```python
def trading_rules(
    exchange_connectors: Any, accepted_quotes: Any = DEFAULT_QUOTES
) -> dict[str, tuple]:
```

The rules and the price come off the market table each connector has already
loaded, as one `MarketRules` row per market. No venue is asked. The crypto rows the
sector scan lists carry no size rules, so on that path the answer reads unknown for
every crypto row; the ticker field reads rules off each connector's table and
answers all three.

### The timeframe row

The asset class sets which four timeframes the buttons offer. Each button draws on
while its timeframe is ticked, and reads its key at the press from the row the
class shows. Crypto is the fast set and every other class shares the slower one.

`src/trading/ata_spm.py` — the two sets

```python
CRYPTO_TIMEFRAMES = ("5m", "1h", "1d", "1w")
SLOWER_TIMEFRAMES = ("1h", "1d", "1w", "1M")
```

A fresh board carries the whole set its class lists, so all four draw on until one
is pressed off. A timeframe press made before any sector exists is held on the
board and given to the sector the next press adds.

### Scan Now

Scan Now reads one press. What it reads depends on the field.

| The field | What the press reads |
| --------- | -------------------- |
| a ticker the class lists | that one market, on every ticked timeframe |
| a sector name the map lists | that sector's own assets |
| empty | the class's markets in its own order, until the hit target lands |

`src/gui/main_tabs/market_inspector_surface.py` — the button and what it says

```python
SCAN_NOW_LABEL = "Scan Now"
SCAN_NOW_TOOLTIP = (
    "Scan this sector now on the timeframes ticked beside it, without "
    "waiting for a rotation."
)
```

The operator asked for the empty field to walk the sector by volume.

> ATA-SMP - Scan Now - Seems to be expecting a Ticker field entry. This is
> incorrect. If Ticker field has no entry, this button must scan sector's
> markets (on each selected TF) in order of decreasing volume until x total
> number of "hits" (across all selected TFs for the sector; add under settings,
> default is 3) are found.

He had asked for the button twice before it worked.

> ATA-SMP - Please proceed back to ATA-SMP and get my Scan button working.
> Unitize and apply same work flow under the correct Issue. It still does
> nothing as of the build I am currently running.

> Simulator - Scan Now - I should not have to have anything in the Ticker
> field. Stocks is saying 'no ticker list'. This is scaffolded, unverified
> garbage. I watched you perform various operations while working on this.
> How the fuck is it that after I launch the build, not a god damn thing has
> improved with this fucking button.

Every mention of the Simulator in those words names this tab.

> Make sure you correct my incorrect verbatims because SImulator does not have Scan Now...Inspector and ATA-SMP do.

The button is disabled and reads `Scanning…` from the press until the answer or
the failure crosses back. A press made while a scan runs writes a busy line to the
Activity Log at warning.

`src/trading/ata_spm.py` — the label a running scan draws

```python
SCAN_BUSY_LABEL = "Scanning…"
SCAN_BUSY_TEXT = "ATA-SPM scan pressed while a scan is running; press ignored"
```

### Scan All

A second button sits beside Scan Now at its size, in both builds. One press walks
every class the sector menu holds, in menu order, on every timeframe that class
scans, over every market its list holds, with no stop at a hit count.

`src/gui/main_tabs/market_inspector_surface.py` — the second button

```python
SCAN_ALL_LABEL = "Scan All"
SCAN_ALL_PART = "scan-all"
```

The operator asked for it, and for the confirmation timers beside it.

> ATA-SMP - Add a Scan All button which will scan every market in every TF for every market in every sector. Have noticed that scans run really fast which is good but just do not to risk overloading a free API or something. For the attached image, I want the Confirmation Timers for prior Hits to appear here. Can be just a small ticker pair with a theme-consistent timer which triggers the rescan on completion.

A Scan Now pressed after a Scan All drops those sectors before it walks, so it
walks its own class and not every class.

`src/trading/ata_spm.py` — what the counter says during a walk

```python
SCAN_ALL_PROGRESS_FORMAT = (
    "Scanning {asset_class} ({at} of {sectors}) · {read} of {total} · {hits} hit(s)"
)
SCAN_ALL_LISTING_FORMAT = (
    "Scanning {asset_class} ({at} of {sectors}) · reading the market list"
)
```

The hits count over every sector, because the chime sounds when that count rises.
A per-sector reset would leave the second sector's first hits silent.

### The pace a walk holds

Scan All keeps every read to a host at least a published gap. The crypto venue
publishes ten requests a second for its public endpoints; the chart venue
publishes no limit, so a refusal is its only signal.

`src/trading/ata_spm.py` — the gaps and the waits

```python
EXCHANGE_PACE_S = 0.2
YAHOO_PACE_S = 0.5
EXCHANGE_RATE_LIMIT_WAIT_S = 10.0
YAHOO_RATE_LIMIT_WAIT_S = 60.0
```

The gap is measured from the end of the last read. A refusal is read as a wait,
never as a burst: the walk holds that host for the venue's own retry figure when
the answer carried one, else the table's seconds, and reads that market once more.
A second refusal stands. Scan Now reads through no pace.

`src/trading/ata_spm.py` — the read every walk goes through

```python
def paced_read(pace: Any, host: Any, read: Any) -> tuple:
    """One read held to ``pace`` on ``host``, retried once on a rate refusal."""
```

A walk hands both its vote step and its chart step one market memo, so a venue is
asked once per market per timeframe rather than twice.

`src/trading/ata_spm.py` — the memo both steps read

```python
class MarketMemo:
    """One market's candles, read once and answered to every later caller."""
```

### The order a walk reads

Every class is walked largest first, by the figure that class publishes. The open
entry's first line names the source, the markets read in order, and the count not
read.

| Class | The figure the order uses |
| ----- | ------------------------ |
| crypto with a connector | the venue's own 24-hour quote volume |
| crypto with no connector | name order on the public products list, no volume figure |
| stocks | the screener's own volume ranking |
| commodities | the last complete daily bar's volume times its close |
| forex | map order; every pair's bar carries volume 0, so no figure exists |

`src/gui/main_tabs/market_inspector_surface.py` — the ranked list one class answers

```python
def class_markets(asset_class: Any, connectors: Any = None) -> list:
    """Every market a class holds as an ``ata_spm.MarketOrder``, largest first."""

def class_volumes(exchange_connectors: Any) -> dict:
def listing_volumes(rows: Any) -> dict:
```

A stablecoin is dropped from a crypto ordering. A market the venue no longer trades
is placed on the order's own dead list rather than in the walk.

`src/trading/ata_asset_maps.py` — the figure a non-crypto class is ranked by

```python
VOLUME_TIMEFRAME = RA_TIMEFRAME
VOLUME_WINDOW_DAYS = 7
NO_VOLUME_FIGURE = 0.0

def venue_quote_volume(listing: Any, read: Any = None) -> Optional[float]:
    """``complete_bar``'s volume times its close, or ``NO_VOLUME_FIGURE``."""
```

The bar measured is the newest one stamped before today, which is a closed session,
so the figure does not move through the day. Volume times close puts it in dollars
beside crypto's quote volume.

`src/trading/ata_spm.py` — the lines the order takes

```python
VOLUME_LINE_FORMAT = "{asset_class} by volume"
MAP_ORDER_LINE_FORMAT = "{asset_class} in map order"
ORDER_LINE_FORMAT = "Order by {source}: {markets}"
ORDER_UNREAD_FORMAT = "{markets} ({unread} not read)"
ORDER_UNFIGURED_FORMAT = "{source}, {unfigured} with no figure last by name"
MAP_ORDER_SOURCE_TEXT = "map order, no volume figure"
```

A market the venue no longer trades never reaches the list and is never fetched.
A futures product the venue answers no candle for on any granularity is dropped
where the list is built, and both counts sit on the order line.

`src/trading/ata_spm.py` — the two tails the order line carries

```python
ORDER_DEAD_FORMAT = "{line}; {count} not trading, never fetched: {names}"
ORDER_NO_CANDLE_FORMAT = (
    "{line}; {count} dropped, the venue answered no candle "
    "on any granularity: {names}"
)
```

A dropped product stays reachable by name: typed into the ticker field it still
resolves and still scans. The candle route serves two granularities and the weekly
line rolls up from the daily one, so the read asks the hourly granularity, then the
daily one, and stops at the first that answers.

`src/trading/ata_asset_maps.py` — the two readings behind the rule

```python
def venue_granularities(venue: Any) -> tuple:
def candle_served(symbol: Any, read: Any = None) -> bool:
```

### A hit, and the target that stops a walk

A hit is a vote the live trade gates would fire on. The zone's count, the Activity
Log's hit lines and the approval bucket count one thing.

`src/trading/ata_gate_scan.py` — the one verdict

```python
    @property
    def would_fire(self) -> bool:
        """True while either chain would fire, which is what a post needs."""
        return self.firing_side != NO_SIDE
```

Each market is read on every ticked timeframe first, because the gate chains read
a market's other timeframes through the panel rows. Votes are then judged in
timeframe order. The hit that reaches the target ends the walk, and markets after
it are not read.

`src/trading/ata_spm.py` — the target, and what an unreadable count reads as

```python
DEFAULT_HITS_PER_SCAN = 3

def hits_target(asked: Any) -> int:
    """``asked`` as a whole number, or ``DEFAULT_HITS_PER_SCAN`` below one."""
```

An empty box, a zero and a negative number all read as three, so no scan can stop
before it has read anything.

A reversal vote is a market on one timeframe whose twelve-voter consensus and its
Bollinger voter name the same non-neutral direction. It is still read and still
shown, in each sector's reversal-call count, and it no longer decides what
publishes.

`src/trading/ata_spm.py` — what a reversal vote is

```python
    @property
    def is_reversal(self) -> bool:
        """The consensus and the band voter naming one non-neutral direction."""
        if SignalDirection.NEUTRAL in (self.direction, self.band_direction):
            return False
        return self.band_direction == self.direction
```

`src/trading/ata_spm.py` — the lines each kind of entry takes

```python
VOLUME_META_FORMAT = "{read} market(s) read · {hits} hit(s) · {stop}"
STOPPED_AT_TARGET_TEXT = "stopped at target"
SECTOR_EXHAUSTED_TEXT = "sector exhausted"
SECTOR_LINE_FORMAT = "{sector} ({asset_class})"
SECTOR_META_FORMAT = "{assets} asset(s) · {votes} vote(s) · {calls} reversal call(s)"
MARKET_LINE_FORMAT = "{ticker} in {asset_class}"
MARKET_META_FORMAT = "1 market on {venue} · {votes} vote(s) · {hits} hit(s)"
MARKET_TIMEFRAME_FORMAT = "{candles} candle(s) · {reading}"
MARKET_HIT_READING = "{direction} vote, hit"
MARKET_REFUSED_READING = "{direction} vote, refused by the gates"
MARKET_NO_VOTE_READING = "no vote"
```

The zone's status line counts sectors and markets apart, so a run holding both counts
both.

`src/trading/ata_spm.py` — what one walk answers and how far it goes

```python
NO_HIT_TARGET = 0

def walks_order(scan: Any) -> bool:
    """True for a ``walk_all`` sector and for a ``hit_target`` above ``NO_HIT_TARGET``."""
```

A board builds one walking sector per class, tells the counter which list it is
reading, and runs them. The walk hands a callable one progress record after each market
and each hit, and one builder writes the line each record carries.

`src/trading/ata_spm.py` — the walk and the records it hands back

```python
def compute_all(self, ticked: Any, hits: Any) -> None:
def _scan_until_hits(sector: Any, sources: Any, target: Any, on_progress: Any) -> tuple:
def market_line(progress: Any) -> str:

class ScanProgress:
class WalkProgress:
```

### What the field draws while a walk runs

The field draws the Indicator Voting Panel of the market under read, and nothing
else. The panel is one row per timeframe that answered candles, one cell per
voter, plus the Net, Comp and Conf columns, in the colours the Live tab's own
panel uses. The title names the market, the word `reading`, and the tally of
bullish, bearish and neutral votes.

`src/gui/main_tabs/market_inspector_surface.py` — one builder, two callers

```python
def panel_grid(symbol: Any, label: Any, rows: Any, lines: Any = ()) -> Optional[dict]:
    """One voting grid, for a called asset or for the market under read."""
```

The operator asked for that panel and for the text to go.

> ATA-SMP - The scanner freaking works but we do have some issues. Derivatives sector list is empty. Metals only has four in its list and I am pretty sure its a more complex sector than this but could be wrong. I see a series of floating windows rapidly appearing and disappearing over the ATA-SMP panel once the scan gets going. The field where the IVP fields are supposed to appear during the read initially displays text but this gets very small very fast before disappearing completely and the floating windows appear with some containing text before vanishing. I was able to get three hits and three charts generated. Very good progress.

> Observed a very strange issue with the lower information panel when attempting to scroll down to see more text. This seemed to trigger a chart re-read loop of some kind. During this I saw the rapidly spawning and despawning windows again. Need to get rid of the informational text during reads and only display the really nice looking IVP information that has only been visible in the larger floating windows up to this point. The IVP data keeps the symbology consistent and its really well designed from what I have seen of it. We have no use a for a repeating spool of identical data lines.

The field holds where the operator left it. Neither host drags its scroll to the
bottom on a progress. The grid asks 592 pixels: a 44-pixel timeframe column, six
58-pixel voter columns, two 52-pixel columns and a 96-pixel Conf column. It draws
whole at a 1400-pixel tab. At 900 and 700 the last three columns sit past the pane
edge with a horizontal scroll bar under them.

`src/gui/main_tabs/market_inspector_surface.py` — the grid, its widths and its two callers

```python
PANEL_SUMMARY_FORMAT = "▲ {bullish}  ▼ {bearish}  ─ {neutral}"

def panel_column_widths() -> tuple:
def panel_table(rows: Any) -> list:
def panel_summary_text(rows: Any) -> str:
def panel_tally(row: Any, direction: Any) -> int:
def scan_panel(progress: Any) -> Optional[dict]:
```

`voting_panel` is the called asset's grid, drawn in an open entry with its gate chain
lines under it. `scan_panel` is the same grid for the market under read, with no gate
line, because no chain has run over that market.

`src/trading/ata_spm.py` — the rows one market answers

```python
def panel_rows_for(symbol: Any, timeframes: Any) -> dict:
```

The per-market read line still exists, with the same four things, written to the
Activity Log instead of the field.

`src/trading/ata_spm.py` — the line each market read writes

```python
SCAN_MARKET_LINE_FORMAT = "{symbol} · {timeframes} · {votes} vote(s) · {verdict}"
SCAN_MARKET_HIT_FORMAT = "hit on {labels}"
SCAN_MARKET_BLOCKED_FORMAT = "no hit: the gates blocked {names}"
SCAN_MARKET_NO_VOTE_TEXT = "no hit: no vote"
SCAN_MARKET_UNREAD_TEXT = "no candles"
```

### The counter

The counter sits at the right end of the stepper's position row, just above the
field, in both builds. It is empty while no scan runs.

The operator placed it there.

> Can see the scan counter in the upper left corner of the lower section.
> Would rather have this counter just above and at the right corner of the
> same field. Then have the field display the results of each scanned market.

`src/trading/ata_spm.py` — what the counter says during one class's walk

```python
SCAN_PROGRESS_FORMAT = "Scanning {asset_class} · {read} of {total} · {hits} hit(s)"
SCAN_LISTING_FORMAT = "Scanning {asset_class} · reading the market list"
```

### What a scan reports

An empty table can mean three different things. The note under it says which: no
scan has run yet, a scan is running, or a scan finished and found nothing.

`src/gui/main_tabs/market_inspector_surface.py` — the sentence an empty table carries

```python
def empty_table_text(scan_state: Any, noun: Any) -> str:
    """The sentence an empty table carries for one scan state.

    ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` and ``SCAN_FINISHED`` each get
    their own wording, so the three never read alike.
    """
```

`scan_state` reports the same three states to both renderers, so the React side
draws the note the way the window does.

A scan ends with one note on the Activity Log. The note names the markets no venue
lists, the timeframes no venue serves, the markets that answered no candle, and
each market no built bot variant trades with that market's own reason.

`src/trading/ata_spm.py` — three of the four sentences a note can carry

```python
UNLISTED_TEXT = "No configured venue lists {symbols}."
UNSERVED_TEXT = "No venue serves {labels}."
UNTRADEABLE_TEXT = "Read and not traded, no bot variant trades {symbols}: {reason}"
```

`src/gui/main_tabs/market_inspector_surface.py` — the fourth

```python
NO_CANDLE_TEXT = "No candles came back for {symbols}."
```

The note groups markets by reason and writes one sentence per group. A symbol is
named as unread only when every ticked timeframe came back empty for it. No market
leaves the scan: a named market keeps its place in the asset list, the charts and
the reports.

`src/trading/ata_spm.py` — the separator between two reasons

```python
UNTRADEABLE_SEPARATOR = ". "
```

Each timeframe keeps that market's last close beside the candle count it already
keeps, and the note reads those closes rather than asking a venue.

`src/trading/ata_spm.py` — the closes the note reads

```python
def scanned_closes(timeframes: Any) -> dict:
    """The last close each market answered, the first timeframe that read one."""
```

A timeframe holding too few candles is reported, never voted. The floor is thirty
candles, the number the gate scan already requires.

`src/trading/ata_spm.py` — the floor, and the line it is reported on

```python
MIN_CANDLES_TO_VOTE = ata_gate_scan.MIN_CANDLES_FOR_TA

TIMEFRAME_VOTE_FORMAT = (
    "{votes} vote(s), {unread} without candles, {short} under {floor} candles"
)
```

The floor earns its place. On twenty-five hourly candles seven of the twelve
voters abstain for want of history, and the remaining five still produce a
direction.

The scan also writes to the log, one line per phase. Every line is written at info
on the `acervator` logger, so the system log and the Console pane carry it.

`src/trading/ata_spm.py` — the lines one press writes

```python
SCAN_PRESSED_TEXT = (
    "ATA-SPM scan pressed: {asset_class} on {timeframes}, "
    "ticker '{ticker}', target {hits} hit(s)"
)
MARKET_READ_TEXT = "ATA-SPM read {symbol} on {label} from {venue}: {candles} candle(s)"
MARKET_EMPTY_TEXT = "ATA-SPM read {symbol} on {label} from {venue}: no candles"
MARKET_REFUSED_TEXT = "ATA-SPM read {symbol} on {label} from {venue}: refused, {reason}"
HIT_TEXT = "ATA-SPM hit: {call}"
SCAN_FINISHED_TEXT = "ATA-SPM scan finished: {headline} · {meta}. {method}"
SCAN_NOTE_TEXT = "ATA-SPM scan finished: {note}"
SCAN_EMPTY_TEXT = "ATA-SPM scan finished: no sector to scan"
SCAN_FAILED_TEXT = "ATA-SPM scan failed: {error}"
```

Each line crosses to the Activity Log on one signal carrying the message and its
level. A read that answered candles draws at info. A read that answered none, the
busy line, and a finished line with no vote draw at warning. A scan that raised
draws at error.

`src/gui/market_inspector.py` — the signal that carries a phase line

```python
    scanLogged = Signal(str, str)
```

The candle source names where it read, what it read, and why it read nothing.

`src/trading/ata_asset_maps.py` — the four refusals a read can name

```python
UNMAPPED_TEXT = "no map lists {symbol}"
NO_VENUE_TEXT = "no configured venue lists {symbol}"
UNSERVED_TEXT = "{venue} does not serve {timeframe}"
NO_ADAPTER_TEXT = "no fetcher serves {venue}"
```

Each module names its own, so the scan note's sentence and one read's refusal are two
constants and not one.

`src/gui/main_tabs/market_inspector_surface.py` — the source one read names

```python
CANDLES_FROM_SCAN = "universe scan"

def sector_candle_read(symbol: Any, timeframe: Any, sources: Any) -> tuple:
    """Where one read went, what it read, and why it read nothing."""
```

A mapped name names its own venue. A crypto name served from the held scan names the
scan, and one read through a connector names the exchange.

### Opposing Pairs

The zone draws the pairs kept on the last scan. A market reaches long or short
only when two or more of its timeframes sit at the same Bollinger extreme. A
thirty-day return correlation in the configured negative window raises a
candidate, and a test for a long-run equilibrium then decides it.

`src/trading/market_inspector.py` — `MarketInspector._find_opposing_pairs`

```python
def _find_opposing_pairs(self, signals: list, closes_by_symbol: dict) -> list:
    """Enumerate long × short candidates; keep the cointegrated ones.

    The 30-day return correlation raises a candidate and no longer decides
    it: ``cointegration_test`` runs on the full close series and a pair it
    refuses never reaches the table.
    """
    longs = [s for s in signals if s.direction == "long" and s.score >= 0.3]
    shorts = [s for s in signals if s.direction == "short" and s.score >= 0.3]
```

Two markets can move opposite each other for a year with no relationship holding
between them. The test is cointegration in both of its standard forms, taken from
statsmodels, and a pair passes only when both reject the null of no cointegration:
Engle-Granger at a significance of 0.05, and Johansen above its ninety-five per
cent critical value for rank zero.

`src/trading/pair_selection.py` — what a pair has to clear

```python
WINDOW_BARS = 365
MIN_OBSERVATIONS = 120
SIGNIFICANCE = 0.05
```

`src/trading/pair_selection.py` — the two published tests

```python
def engle_granger_p_value(left: Any, right: Any) -> float:
    """The two-step p-value, from ``statsmodels.tsa.stattools.coint``."""

def johansen_trace(left: Any, right: Any) -> tuple:
    """The rank-zero trace statistic and its 95% critical value."""
```

A pair with fewer than 120 daily closes is not tested and not shown. A flat series
is refused before the correlation package is imported, under a method and a reason of
its own rather than as a test result.

`src/trading/pair_selection.py` — the refusal a flat series takes

```python
METHOD_CORRELATION = "correlation"
FLAT_SERIES_DETAIL = "series holds one repeated price"

def is_flat(series: Any) -> bool:
```

Both packages are imported inside the three functions that call them, and nowhere
else, so the application starts before either is loaded. Both are declared, and
the bundle carries both, so the test runs in the built application and in a
source run alike. A missing package is re-raised as itself rather than recorded
as a refused pair.

`pyproject.toml` — the two packages the tests need

```toml
"scipy>=1.18.1",
"statsmodels>=0.15.0",
```

`tools/spec_common.py` — the packages the bundle still leaves out

```python
EXCLUDES: tuple[str, ...] = ("tkinter", "matplotlib", "PIL", ...)
```

A name in that list must not also sit in `dependencies`. The two statistics
packages sit in `dependencies` and not in the list, which is what lets the
Opposing Pairs table and the Bot Swarm Topologies zone draw rows.

The zone's own line names the whole funnel: markets read, markets with a
direction, pairs tested, and whether any held equilibrium.

`src/gui/main_tabs/market_inspector_surface.py` — the three counts and where each is read

```python
def scan_counts(signals: Any, tested: Any) -> dict:
    """Markets read, markets with a direction, and pairs the test ran on."""
```

## Where the analysis happens

`MarketInspector` in `src/trading/market_inspector.py` owns the maths. One method
drives the whole pipeline and keeps the results on the analyzer.

`src/trading/market_inspector.py` — `MarketInspector.scan_universe`

```python
def scan_universe(
    self,
    candles_by_symbol_by_tf: dict,
    active_symbols: set,
    closes_by_symbol: dict,
) -> None:
```

Two steps run under it.

| Step | Produces |
| ---- | -------- |
| `_analyze_tf` | One `TimeframeAnalysis` per timeframe |
| `_score_market` | One `MarketSignal` per market |

One analyzer instance serves two readers. `get_shared_inspector` returns it, the
tab owns the fetch cycle and writes into it, and the per-bot Market Inspector page
in the Bot Details dialog reads back out of it through `build_per_bot_view`. One
analyzer, two readers, no second copy of the score.

`src/trading/market_inspector.py` — what one finished scan leaves on the analyzer

```python
    last_signals: list
    last_tested: list
    last_closes: dict
```

`last_tested` holds one entry per candidate the equilibrium test ran on, whether it
passed or not, and the Opposing Trades funnel line is the one reader of it.

The per-bot page is drawn from one description of the screen. It returns the rows,
the groups, the words, the colours and the layout numbers as values. The Qt side
draws them as widgets and the React side draws them as elements.

`src/gui/main_tabs/market_inspector_tab_surface.py` — `per_bot_view`

```python
def per_bot_view(bot: Any) -> dict:
    """The per-bot Market Inspector screen as values, read off the shared
    analyzer's most recent scan.
```

## Fetching

`set_exchange_source` binds a connectors getter and the application scheduler, so
the tab always sees the current connector dict rather than a snapshot taken at
build time.

The fetch serves its last network result while that result stays young enough, and
the Refresh button passes a flag that goes to the network regardless.

`src/exchange/market_inspector_fetcher.py` — `fetch_htf_universe`

```python
async def fetch_htf_universe(
    exchange_connectors: dict,
    active_symbols: Optional[set] = None,
    top_n: int = DEFAULT_TOP_N,
    progress_cb=None,
    force_network: bool = False,
    min_refresh_s: float = DEFAULT_MIN_REFRESH_S,
) -> FetchResult:
```

Three helpers do the work inside it.

| Helper | What it does |
| ------ | ------------ |
| `_pick_universe` | Ranks each connector's bulk tickers by 24-hour quote volume |
| `_fetch_one_symbol` | Pulls per-symbol OHLCV on the connector's single-worker executor |
| `weekly_from_daily` | Derives the weekly series when the venue lists no weekly timeframe |

The weekly series is one definition. It calls the stone tablets' own rollup with
the week bucket moved onto Monday 00:00 UTC, the day the chart venue stamps its
weekly bar with.

`src/exchange/market_inspector_fetcher.py` — the weekly line

```python
def weekly_from_daily(daily: list[_Candle]) -> list[_Candle]:
    """One weekly _Candle per calendar week of daily, through weekly_rows_from_daily."""
```

The scan asks a venue only for what its own table lists.

`src/exchange/market_inspector_fetcher.py` — the timeframes one connector serves

```python
DAILY_TIMEFRAME = "1d"
WEEKLY_TIMEFRAME = "1w"

def exchange_timeframes(connector: Any) -> tuple:
    """The timeframes one connector's own table lists, with 1w where 1d is."""
```

`src/trading/market_inspector.py` — the three the Refresh scan names

```python
HTF_TIMEFRAMES = ("1d", "1w", "1M")
```

Every crypto row carries that table, and a listing answers whether it serves one
timeframe. Where no table is found, the public route's own granularity set answers
instead. A market must sit at the same Bollinger extreme on two of those timeframes
to carry a direction, so the Refresh scan's two series decide it.

`src/trading/stone_tablets/ra_fetcher.py` — the granularities the public route serves

```python
class CoinbasePublicCandles(ExchangeAdapter):
    GRANULARITY_S = {"1d": 86_400, "1h": 3_600, "5m": 300}
```

`src/exchange/market_inspector_fetcher.py` — the two product lists and the volume read

```python
def public_products() -> tuple:
def trading_products(exchange_connectors: Any) -> tuple:
def public_candles(symbol: Any, timeframe: Any, bars: Any) -> list:
async def fetch_quote_volumes(
    exchange_connectors: dict, min_refresh_s: float = DEFAULT_MIN_REFRESH_S
) -> dict[str, float]:
```

`src/gui/main_tabs/market_inspector_surface.py` — the two readers the scan asks after the maps

```python
def connector_candles(symbol: Any, timeframe: Any, connectors: Any) -> list:
def inspector_candles(symbol: Any, timeframe: Any) -> list:
def inspector_scan_age() -> float:
```

A product reaches a walk only while the venue says its status is online and its
trading is not disabled. A name the map holds and the venue does not trade goes on
the order's dead list.

`src/exchange/market_inspector_fetcher.py` — the week the rollup uses

```python
DAY_MS = 86_400_000
MONDAY_OFFSET_MS = 4 * DAY_MS
DAYS_PER_WEEK = 7
WEEK_MS = DAYS_PER_WEEK * DAY_MS
```

A request to the public crypto route is held to 300 candles, and the bars a read
asks for are held to that ceiling before the start is computed, so the window ends
at the press.

`src/exchange/market_inspector_fetcher.py` — the window one read asks for

```python
        count = min(int(bars), RA_CHUNK_DAYS)
```

The market-data cache is shared. A crypto name with a Refresh under fifteen
minutes old uses the candles Refresh read; past that the scan reads again.

`src/gui/main_tabs/market_inspector_surface.py` — the window a held scan serves

```python
CANDLES_FRESH_SECONDS = DEFAULT_MIN_REFRESH_S
```

The scan asks three questions in order and stops at the first that answers: a
listing in the asset maps, a fresh inspector scan, then the connectors. A crypto
scan with no exchange connected reads the products list and the candles through the
application's own public route.

`src/gui/main_tabs/market_inspector_surface.py` — the three sources, in order

```python
def sector_candles(symbol: Any, timeframe: Any, sources: Any) -> tuple:
    """The candles one market answers, from the first source that has them."""
```

`src/trading/ata_asset_maps.py` — the listing one name resolves to, and its candles

```python
def listing_of(symbol: Any) -> Optional[AssetListing]:
def venue_candles(listing: Any, timeframe: Any) -> list:
def venue_candle_read(listing: Any, timeframe: Any) -> tuple:
```

`src/trading/ata_spm.py` — the markets one class and sector hold

```python
def markets_of(asset_class: Any, sector: Any = "") -> tuple:
```

Both hosts hand the model its asset source and its candle source where they are built,
so neither reads `None` for the life of the screen.

`src/gui/main_tabs/market_inspector_surface.py` and `src/gui/market_inspector.py` — the wiring

```python
self.set_ata_sources(sector_assets, self.scanned_candles)
self.set_ata_sources(sector_assets, self._scanned_candles)
```

Three readers serve the sources: one answers the assets a named sector holds from the
shipped sector map, one answers the four timeframes a class scans, and one names each
market the note reports as read and not traded.

`src/gui/main_tabs/market_inspector_surface.py` — the assets one sector holds

```python
def sector_assets(sector: Any, asset_class: Any) -> list:
```

`src/trading/ata_spm.py` — the timeframes a class scans, and the markets it did not trade

```python
def timeframes_for(asset_class: Any) -> tuple:
def untradeable_markets(scan: Any) -> list:
```

The sector map itself is loaded by `load_sector_map` in
`src/trading/topology_proposals.py`, which is the one copy the topology detectors read
as well.

### The venues and the timeframes each serves

The chart venue answers four intervals and spells two of them differently from the
way the engine names them.

`src/trading/stone_tablets/ra_fetcher.py` — the engine's word, and the endpoint's

```python
YAHOO_INTERVALS: dict[str, str] = {
    "1h": "1h",
    RA_TIMEFRAME: "1d",
    "1w": "1wk",
    "1M": "1mo",
}
```

It refuses an hourly window longer than 729 days: 729 answers and 730 returns an
error. The adapter records that reach and moves the start of a longer request
forward, so an over-long ask returns the candles that exist instead of nothing. The
other three intervals answered a twenty-five year request in full, so no limit is
recorded for them.

`src/trading/stone_tablets/ra_fetcher.py` — the days each interval reaches

```python
YAHOO_REACH_DAYS: dict[str, int] = {
    "1h": 729,
    RA_TIMEFRAME: UNCAPPED_REACH_DAYS,
    "1w": UNCAPPED_REACH_DAYS,
    "1M": UNCAPPED_REACH_DAYS,
}
```

The futures route serves an hourly and a daily granularity at 350 candles a
request, and its weekly line rolls up from its daily one.

`src/trading/stone_tablets/ra_fetcher.py` — the futures candle route

```python
class CoinbaseFuturesCandles(ExchangeAdapter):
    exchange_id = "coinbase-futures"
    chunk_limit = FUTURES_CANDLE_CAP
    BASE_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"
```

Every venue candle is stamped in seconds, the unit the connector's candles, the
chart's time axis and the confirmation timer already read. The chart venue's futures
list is read with its own timeout, and the crypto sector keeps its daily and weekly
series on the exchange row.

`src/trading/ata_asset_maps.py` — the futures read, and the unit every row is stamped in

```python
FUTURES_TIMEOUT_S = 20.0
MS_PER_S = 1000
VENUE_EXCHANGE: (RA_TIMEFRAME, "1w"),

def futures_listings(timeout_s: float = FUTURES_TIMEOUT_S) -> tuple:
    """The venue's futures rows, their figures, and a refusal where it answered none."""
```

### The asset maps

One row describes one asset a sector holds, with the venue and ticker carrying it.

`src/trading/ata_asset_maps.py` — one asset, and where it is carried

```python
@dataclass(frozen=True)
class AssetListing:
    """One asset a sector holds, with the venue and ticker carrying it.

    ``quote`` is the currency the venue prices ``ticker`` in, which
    ``YahooChartAdapter.fetch_chunk`` checks its answer against.
    """

    symbol: str
    quote: str = USD
    venue: str = NO_VENUE
    ticker: str = ""
```

Forex is the class built end to end, and its tiers are liquidity tiers. The major
tier is the seven pairs that hold the dollar. The minor tier is every cross of two
of those currencies with no dollar in it, twenty-one pairs. The exotic tier is
defined and holds no pair, because no pair is named for it.

`src/trading/ata_asset_maps.py` — the two tiers that carry names

```python
FOREX_MAJOR: tuple[AssetListing, ...] = tuple(
    _yahoo_fx(one)
    for one in (
        "EUR/USD",
        "USD/JPY",
        "GBP/USD",
        "USD/CHF",
        "AUD/USD",
        "NZD/USD",
        "USD/CAD",
    )
)

CROSS_ORDER: tuple[str, ...] = ("EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY")

FOREX_MINOR: tuple[AssetListing, ...] = tuple(
    _yahoo_fx(f"{base}/{quote}")
    for at, base in enumerate(CROSS_ORDER)
    for quote in CROSS_ORDER[at + 1 :]
)
```

Commodities carries funds and not futures. A futures chart longer than a few months
joins two or more contracts together, and every join is a price step nobody traded.
This platform sells against a dollar target, so an invented step moves every level
behind it. A fund holds the metal, prices in dollars, and has no expiry and no roll.

`src/trading/ata_asset_maps.py` — the listed instrument for each metal

```python
METALS_PHYSICAL: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("GLD", "SLV", "PPLT", "PALL")
)
METALS_BASE: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("CPER", "DBB")
)
```

The four commodity spot pairs stay in the map and stay unlisted. A metal spot quote
is a dealer market with no public listing, so no free venue carries it, and all four
spellings answer HTTP 404.

`src/trading/ata_asset_maps.py` — the map, its sector names and where each figure came from

```python
SECTOR_MAJOR = "major"
SECTOR_MINOR = "minor"
SECTOR_EXOTIC = "exotic"
FOREX_EXOTIC: tuple[AssetListing, ...] = ()

METALS_SPOT: tuple[AssetListing, ...]
MAPS: dict[str, dict[str, tuple]]
MAP_SOURCES: dict[str, str]
```

`MAPS` is the one structure every ticker list, sector list and scan reads, and
`MAP_SOURCES` names the published document each class's taxonomy came from.

Energy carries the two groups the published index names, petroleum and gas. Its
four funds are USO for WTI crude, BNO for Brent crude, UGA for gasoline and UNG
for natural gas. No fund holding heating oil or gasoil is listed, because both
answered no rows.

`src/trading/ata_asset_maps.py` — the energy rows

```python
ENERGY_PETROLEUM: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("USO", "BNO", "UGA")
)
ENERGY_GAS: tuple[AssetListing, ...] = (
    AssetListing(symbol="UNG", quote=USD, venue=VENUE_YAHOO, ticker="UNG"),
)
```

The operator added the energy sector.

> ATA-SMP - New Market Sector - Energy - Not sure how I forgot to add this...

> ATA-SMP - Energy sector also only has four entries in its list. Probably not complete...

Every forex pair the map names sends volume 0 on every bar. Two of the twelve
voters read volume, and the volume voter abstains on such a series rather than
standing a number in. Spot currency trading has no single published volume
anywhere, and a currency future's volume is not the pair's.

`src/trading/indicators/zscore.py` — which of the two values the reading holds

```python
smoothed = _vwma(z_series, z_volumes, self.smoothing_period)
z_volume_weighted = smoothed is not None
z = z_raw if smoothed is None else smoothed
```

The daily open is kept in every formula that reads it. Three read it: the volume
voter, Heikin Ashi and the landing strip. Each of the three is the published
formula. A fund opens at an auction, so its open is a traded price beyond doubt,
and a gap between an open and the previous close is what any daily bar does when
the market stops trading between bars.

A venue row whose open or close sits outside its own high and low is not a candle.
Each such row is refused on its own, the rest are kept, and nothing is clamped or
invented.

`src/trading/ata_asset_maps.py` — the conversion, one row at a time

```python
def _candles_of(ticker: str, rows: Any) -> list:
    """Every row ``candles_from_raw`` accepts, one row at a time.

    A venue row whose open or close sits outside its own high and low is not
    a candle, and it is counted into ``VENUE_ROWS_REFUSED_LOG``.
    """
```

### The stocks list

At press time the stocks list is the chart venue's predefined most-active screener,
unauthenticated, ranked by regular market volume, each quote carrying its sector.

`src/trading/ata_asset_maps.py` — the screener the list is read from

```python
SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
SCREENER_ID = "most_actives"
SCREENER_COUNT = 100
```

Where the screener refuses or answers no quote, the list is the portfolio equities
the simulator holds: every non-crypto name the other maps do not carry, 47 names,
in map order. The order line names which list was read.

`src/trading/ata_asset_maps.py` — the two lists, and the read behind the first

```python
STOCKS_PORTFOLIO: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in SYMBOLS
    if one not in CRYPTO_SYMBOLS and one not in _MAPPED_FUNDS
)

def screener_listings() -> tuple:
    """The screener's own quotes, through the request route the chart adapter uses."""
```

`src/gui/main_tabs/market_inspector_surface.py` — the two source lines

```python
STOCKS_SCREENER_SOURCE_FORMAT = "{source}, {sectors} sector(s)"
STOCKS_PORTFOLIO_SOURCE_FORMAT = (
    "RA portfolio equities in map order, the screener refused: {refusal}"
)
```

The operator set the rule for a source that is not free.

> If we are having difficulty sourcing the data for free we will need to implement an API driven solution or get clever...

### The futures list

Derivatives is not a class. Each futures product takes the class of its underlying,
and the product list is read at press time from the venue's own public route,
ranked by its own 24-hour volume times price.

`src/trading/ata_asset_maps.py` — where the futures list comes from

```python
FUTURES_PRODUCTS_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"
FUTURES_PRODUCT_TYPE = "FUTURE"
FUTURES_SOURCE_TEXT = "coinbase futures and perpetuals, 24 h volume x price"
```

The operator reported the empty slots that rule closed.

> Inspector -> ATA-SMP -> Market Sectors -> Several slots for derivatives are empty or were showing no candles returned.

## Right half: topology proposals

`MarketInspectorTopologies` in `src/gui/market_inspector_topologies.py` renders one
card per proposal and opens a preview dialog on Preview.

The engine behind the cards takes a plain dictionary, which keeps it free of any
exchange or bot-manager coupling. It unions the detectors, drops overlapping
proposals by asset and caps the result.

`src/trading/topology_proposals.py` — `detect_all_topologies`

```python
def detect_all_topologies(
    context: dict[str, Any],
    cap: int = PROPOSAL_CAP,
) -> list[dict[str, Any]]:
    """Union every detector's proposals, dedupe them and cap at ``cap``.
```

Four detectors feed it.

| Detector | Shape | Members it needs |
| -------- | ----- | ---------------- |
| `detect_momentum_funnel` | Correlated cluster, leader into laggers | 3 |
| `detect_mean_reversion_pair` | Anti-correlated pair, wired both ways | 2 |
| `detect_sector_cluster` | Same-sector star, hub into spokes | 4 |
| `detect_distance_to_band` | One asset, scrum-deep into fold-deep | 2 |

Three of the four read the closes a finished Inspector scan writes. The fourth
reads the bot roster alone and pairs a scrum-deep bot with a fold-deep bot on the
same asset.

Two helpers read from disk under `src/trading/`. `suggested_target_usd` sizes each
proposed bot from the asset target defaults, and the sector map names each asset's
sector.

The pane reads the detector again the moment a scan finishes, on its own Refresh
press, and on its ten-minute timer. Both panes answer that read under one name, so
the Qt widget and the React host take the same call. A pane whose read raises is
asked once, the tab logs a warning, and the scan still finishes.

`src/gui/market_inspector.py` — the one refresh both hosts call

```python
def _refresh_proposals(self) -> None:
    """Read the detectors again and redraw the pane, at most once per trigger."""
```

An empty pane says which of three states it is in.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — the three sentences

```python
def empty_proposals_text(scan_state: Any) -> str:
    """The sentence an empty proposals pane carries for one scan state."""
```

Before any scan it reads "No proposals yet. The detector reads the closes the
scanner writes, so press Refresh on the left half first." While a scan runs it
reads "A scan is running. Proposals are built from what it finds." Afterwards it
reads "No proposals right now.  Try Refresh, or wait for market state to shift."

The pane's button reads Refresh, because the zone title already says what is being
refreshed.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — the label and its width

```python
REFRESH_TEXT = "Refresh"
REFRESH_TOOLTIP = "Rerun topology detectors on current market state."
REFRESH_WIDTH_PX = 96
HEADER_WORD_WRAP = True
```

`current_topology_proposals` answers two different things. It answers `None` when
the right pane never built or refused the read, and a list when the pane answered,
so an empty list means the pane holds no proposals. The reader in the Simulator tab
passes both answers on rather than flattening them.

`src/gui/main_tabs/market_inspector_surface.py` — the two answers a reader gets

```python
    def current_topology_proposals(self) -> Optional[list]:
        """The proposals on display, for a simulator to read and wire.

        ``None`` says the right pane never built or refused the read,
        and a list says the pane answered, so an empty pane and an absent
        one never look alike to a caller.
        """
```

## Dismissal

Dismissing a card hides it for a day, and the dismissal survives a restart. The
pane writes each held id against the second it lapses at into the operator's
settings, under `topology_dismissed_proposals`.

`src/gui/market_inspector_topologies.py` — `_persist_dismissed`

```python
def _persist_dismissed(self) -> None:
    """Write ``_dismissed`` to the store, recording a refusal."""
    if self._dismiss_store is None:
        return
    try:
        self._dismiss_store.set(DISMISS_SETTINGS_KEY, dict(self._dismissed))
```

A write the store refuses leaves the card hidden for the session and puts the
cause on the line beside Refresh, which reads `Dismissal NOT saved:` in place of
the count until the next write lands. The pane stays up either way.

`src/core/settings.py` — `AppSettings.topology_dismissed_proposals` is the field
the write lands in. `set_dismiss_store` hands the pane the settings manager it
persists through, and the pane never resolves settings itself. Entries already
lapsed are dropped at load and written back out, so a day's suppression is not
extended across a restart and the stored set does not grow without bound.

## Adopt

The pane emits an adopt request and the window handles it. The handler counts the
new bots and their combined budget, asks which of the proposed wires already exist
and would change, and shows all of it before anything is created.

`src/gui/main_window.py` — `_adopt_topology_proposal`

```python
def _adopt_topology_proposal(self, proposal: dict) -> None:
    """Confirm, open the wizard for each new bot, then emit `wire.created`."""
```

An adopt that aborts part way calls `_report_adopt_orphans`, which names the bot
ids it created and left unwired. Adopt is the only control on this screen that
creates anything.

## Push to the Simulator, the Paper Trader and Live

Both candidate zones carry a Push to Sim button. An open Opposing Trades entry
draws it under the pair's headline, and the topology preview draws it beside
Adopt. One press sends the candidate's bots to the Simulator, which holds them
under its Back Test mode and leaves that mode in force.

`src/gui/main_tabs/market_inspector_surface.py` — the one button both zones draw

```python
def push_to_sim_actions() -> list:
    """Push to Sim, the one button an open candidate entry draws."""
    return [
        action_row(
            PUSH_TO_SIM_PART,
            PUSH_TO_SIM_LABEL,
            PUSH_TO_SIM_TOOLTIP,
            PUSH_TO_SIM_WIDTH_PX,
        )
    ]
```

A topology names several bots and the wires between them; an opposing pair names
two assets and no wire. Both reduce to the same payload — rows of one market and
one dollar target, plus the wires — and the Simulator turns each row into a held
bot on the venue its Stone Tablet was recorded on.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — a proposal's payload

```python
def proposal_push_candidates(proposal: Any) -> dict:
    """One proposal as ``{"bots", "wires"}``, the payload a push takes.

    Each bot is a ``{"symbol", "target_usd"}`` row and each wire is a
    ``{"source_asset", "target_asset", "pct"}`` row, so the routing the
    proposal describes travels with the bots it names.
    """
```

An asset no Stone Tablet names has no tape for Back Test to walk, so the push is
refused whole. The Activity Log names the asset, nothing is held, and the run
mode does not move. The same refusal is written when no Simulator tab is built.

`src/gui/simulator/sim_trading_tab_surface.py` — the refusal the operator reads

```python
PUSH_NO_TABLET_FORMAT = (
    "Push to Sim refused: no Stone Tablet names {assets}, so Back Test has no "
    "tape to walk. The run mode is unchanged."
)
```

A wire is refused the same way. Its two ends name markets, and the push creates
one simulated bot per market, so a wire whose source or target names a market
the push did not create has no bot to reach. A wire naming one market at both
ends has only one bot to reach, which is what `detect_distance_to_band` builds:
it pairs a scrum-deep live bot with a fold-deep live bot on the same market, and
those two collapse to one simulated bot. Either gap refuses the whole push,
names the wire and says why.

`src/gui/simulator/sim_trading_tab_surface.py` — the wire refusals

```python
PUSH_WIRE_UNHELD_FORMAT = "{source} to {target}: nothing was pushed for {asset}"
PUSH_WIRE_SELF_FORMAT = (
    "{source} to {target}: both ends are the one bot pushed for {source}"
)
```

A pushed bot is a simulated record, never a live bot and never an order. It
reaches the Simulator's own fleet file and its own bus, and the live engine and
the live logs see nothing of it. A pushed wire is the same: it is registered on
the Simulator's own `SimWireManager` and never on the live `SmartWireManager`.

The Paper Trader has no mode a candidate could land under, so no push targets
it. Live takes no push either. The two targets are named on
[the promotion pipeline page](promotion-pipeline.md).

### Push to Paper

That first sentence is overtaken, and it is kept above as it stands. The Paper
Trader still has no mode a candidate could land under, and a push targets it
anyway. Both candidate zones carry a Push to Paper button beside Push to Sim,
and one press spawns one paper scrumming bot per market the candidate names.

`src/gui/main_tabs/market_inspector_surface.py` — the two buttons an open entry
draws

```python
def candidate_push_actions() -> list:
    """Both destination buttons an open candidate entry draws, Push to Sim then
    Push to Paper."""
    return [*push_to_sim_actions(), *push_to_paper_actions()]
```

The payload is the same one Push to Sim takes. Paper reads its venue live, so
it needs no Stone Tablet: every pushed bot takes the venue the Paper Trader's
own `PaperExchange` names. The wires travel with the bots, and a wire that
cannot reach two different pushed bots refuses the whole push, exactly as it
does on the Simulator.

`src/paper/fleet_source.py` — where a pushed candidate lands on Paper

```python
def push_candidate(
    self,
    candidate: Any,
    exchange_id: str = "",
    ta_timeframe: str = "",
) -> dict:
```

No run mode is named anywhere on this press, and the Activity Log line names
none. [The Paper Trader page](paper-trader.md) carries what the spawned bots
read and what each refusal says. Live still takes no push.

## ATA-SMP

The eight phases sit outside the screen. Phases one to three and phase eight run in
`src/trading/ata_spm.py`, and phases four to seven run in
`src/trading/ata_spm_push.py`. The screen reads what they produce and draws it; it
computes none of it.

`src/trading/ata_spm.py` — the phases one press runs

```python
def run(
    sectors: Any,
    asset_source: Optional[Callable] = None,
    candle_source: Optional[Callable] = None,
    engine: Optional[VotingEngine] = None,
    message_format: Optional[str] = None,
    clock: Optional[Callable] = None,
) -> AtaSpmRun:
    """Phases one, two, three and eight in order, as one ``AtaSpmRun``."""
```

| Phase | Module | What it produces |
| ----- | ------ | ---------------- |
| 1 Evaluate | `ata_spm.evaluate` | One scan per sector, per ticked timeframe |
| 2 Identify | `ata_spm.identify` | The votes carrying a reversal, strongest first |
| 3 Pull | `ata_spm.pull` | The chart, its bands, and one message per confirming voter |
| 4 Format | `ata_spm_push.format_post` | One post per push target |
| 5 Distribute | `ata_spm_push.distribute` | One delivery record per post |
| 6 Ready to Send | `ata_spm_push.ReadyToSend` | The bucket the operator approves from |
| 7 Follow-Up | `ata_spm_push.FollowUpWatch` | What the market did after a published call |
| 8 Timeframes | `ata_spm.agreement_for` | Every timeframe the asset voted on, and their verdict |

A run answers one readback line naming the sectors scanned, the calls found, the
charts pulled and the markets the gates refused.

`src/trading/ata_spm.py` — the line a finished run leaves

```python
PHASE_RUN_FORMAT = (
    "{phase}: {sectors} sector(s), {calls} call(s), {pulls} chart(s), "
    "{refused} refused by the gates"
)
```

Phase eight answers whether the other timeframes agree with the call. It walks
every vote the same asset produced in the run, names the direction each one read,
and lists the timeframes that read the opposite. A neutral vote is neither
agreement nor contradiction.

`src/trading/ata_spm.py` — the three verdicts phase eight can write

```python
AGREEMENT_AGREED_TEXT = "Every timeframe agrees."
AGREEMENT_SINGLE_TEXT = "Only one timeframe voted."
AGREEMENT_CONTRADICTED_FORMAT = "Contradicted on {labels}."
```

Phase eight also caps a scan. Each sector takes only as many timeframes as the
rounds so far show will fit inside one candle of the shortest timeframe the class
scans. The rest are recorded as deferred and named on the zone, so a shortened scan
is visible rather than silent.

### The gate chain over scanned prices

One judgement decides whether a market is charted and posted, and it is the live
trade gate chain. If the chain says Acervator would take the trade, the chart is
drawn and the post joins the approval bucket. If it does not, no chart is drawn and
nothing reaches the bucket.

Both chains the bots build are evaluated, unchanged, against a context filled from
one market's candles and its voting summary. Nothing on the live path changes: the
bots build the only two contexts inside their own tick, and this is a third caller.

`src/trading/ata_gate_scan.py` — both live chains, over scanned prices

```python
readings = read_chain(build_scrumming_scrum_chain(), context) + read_chain(
    build_scrumming_fold_chain(), context
)
```

Twenty-four gates run across the two chains, fourteen on the scrum side and ten on the
fold side. Eighteen decide from price and settings alone. Six need a position the scan
does not hold, and the scan never invents one. Four of the six stand down by name, and
two publish a distance instead of a verdict.

`src/trading/ata_gate_scan.py` — the six, split by what a scan can honestly say

```python
NOT_APPLICABLE_GATES = (
    "delta_positive",
    "interval",
    "tranches_queued",
    "smart_ceiling",
)
HYPOTHETICAL_GATES = ("hysteresis_scrum", "hysteresis_fold")
```

The four stood-down gates appear in the expansion by name, marked as not run, each
with the reason. A post must never imply a gate latched when no gate ran.

`src/trading/ata_gate_scan.py` — the reason each stood-down gate publishes

```python
NOT_APPLICABLE_REASONS = {
    "delta_positive": "a scan holds nothing, and no surplus exists to test",
    "interval": "the same surplus, and a scan holds none of it",
    "tranches_queued": "a scan has no fold queue",
    "smart_ceiling": "a scan holds nothing, and any ceiling test passes",
}
```

The two hysteresis gates run against a hypothetical entry at the scanned price and
publish the price a reversal would have to reach, with no verdict attached. At the
instant of the scan the pivot equals the price, so both sides would refuse; the
number is the reading, and the refusal is not.

`src/trading/ata_gate_scan.py` — what a hypothetical row prints

```python
HYPOTHETICAL_FORMAT = (
    "entry at ${price:.8f} would need ${required:.8f}, "
    "{distance:.2f}% away; no gate ran"
)
```

Opposing Trade Distance is one sum: the bot's scrumming interval percentage plus
its trading fee percentage, clamped between 0 and 50. It is a formula over
settings, so a scan computes it exactly as a bot does.

`src/trading/otd_math.py` — the whole formula

```python
total = float(interval_pct) + float(fee_pct)
return max(OTD_MIN_PCT, min(OTD_MAX_PCT, total))
```

Landing Strip is the second number. The band-proximity detector reads whether price
has sat against a Bollinger band for a run of candles, and it answers a side. An
upper strip is a sell reversal and a lower strip is a buy reversal. The side and
the candle count are both published beside the distance.

`src/gui/main_tabs/market_inspector_surface.py` — the line carrying both numbers

```python
GATE_DISTANCE_FORMAT = "opposing trade distance {pct:.2f}% · landing strip {strip}"
```

A second strip detector runs inside the gate scan and feeds the confidence floor
rather than the direction. It lowers the floor the TA consensus must clear, the way
the live tick lowers it, so the scan and a bot judge a market at one bar. The one
term a scan loses is the band-priority favour, which arms only on a signed delta,
so a scan reads at a stricter floor than a bot holding a position. The floor is the
chain's own; no second threshold is written on the posting path.

`src/trading/ata_gate_scan.py` — the scan's readings and the floor it reads

```python
@dataclass(frozen=True)
class GateScan:
    """Every gate reading over one market, with the side that would fire."""

    confidence_floor: float = 0.0
```

`src/trading/ta_engine.py` — the candle floor the engine sets

```python
MIN_CANDLES_FOR_TA = 30
```

A chart with too few candles produces no gate scan at all. The floor is 30 candles,
and the line says so rather than reporting an empty result as a clean one.

`src/gui/main_tabs/market_inspector_surface.py` — the two lines the expansion heads

```python
NO_GATE_TEXT = "No gate ran. The chart carried too few candles."
GATE_COUNT_FORMAT = (
    "{ran} of {total} gate(s) ran · {latched} latched · {blocked} blocked "
    "· {stood_down} did not run"
)
```

A refused market is still on the record. Its gate scan is kept, so a reader sees
that the market was judged, which gates blocked it and why.

`src/trading/ata_spm.py` — what is drawn and when

```python
    image = (
        render_pull_image(vote, candles, max_supporting_indicators, messages)
        if gates.would_fire
        else ChartImage()
    )
```

### The voting panel a called asset carries

ATA-SMP carries its own Indicator Voting Panel. It is a clone of the live one,
drawn inside an open entry, and it reads only the markets ATA-SMP scanned. No live
bot's market reaches it, and it reaches no live bot.

`src/gui/main_tabs/market_inspector_surface.py` — the panel and what feeds it

```python
def voting_panel(pull: Any) -> Optional[dict]:
    """The Indicator Voting Panel one scanned asset carries, as its rows.

    The rows are the timeframes ATA-SMP read for this asset alone, and
    every cell is drawn from ``indicator_panel_surface``.
    """
```

### The settings page

The Settings button swaps the zone for a page of buttons that takes the whole left
column, so nothing is squeezed into a strip and no scroll bar appears. That page is
Level 1. A press on a venue button opens that venue's own sign-in page, which is
Level 1A.

`src/gui/main_tabs/market_inspector_surface.py` — the two pages the zone shows

```python
LEVEL_ONE = "level-1"
LEVEL_ONE_A = "level-1a"
```

Level 1 carries three groups and a Back button. SM Accounts holds one button per
push target. Asset Category holds one button per asset class, and the pressed one
is the class a scan uses. Settings holds the six values a phase reads.

`src/gui/main_tabs/market_inspector_surface.py` — the three group names

```python
SM_ACCOUNTS_TITLE = "SM Accounts"
ASSET_CATEGORY_TITLE = "Asset Category"
ATA_SETTINGS_TITLE = "Settings"
```

| Setting | Which phase reads it | Starts at |
| ------- | -------------------- | --------- |
| Max posts per hour | The send ceiling | unset, and an unset ceiling releases nothing |
| Max supporting indicators | Phase four, capping the evidence lines and the chart overlays | unset, and every confirming voter is drawn |
| Confirmation share % | Phase seven, sizing the target a call must reach | 0, and a call reads open |
| Standardised message text | Phase three, wording each indicator message | the standard wording |
| Hits per scan | The walk's stop target | 3 |
| Confirmation read candles | Phase seven, spacing each read after the first | 3 |

A held venue credential, the asset class a scan uses and a ticked timeframe are one
state, painted in the theme's primary colour under its on-primary text in both
builds.

`src/gui/main_tabs/market_inspector_surface.py` — the setting keys and the rows they draw

```python
SETTING_CONFIRMATION_SHARE = "confirmation_share_pct"
SETTING_CONFIRMATION_CANDLES = "confirmation_candles"
SETTING_ROWS: tuple[tuple[str, str], ...] = (...)
COUNT_SETTINGS = (SETTING_HITS_PER_SCAN, SETTING_CONFIRMATION_CANDLES)

def setting_rows(settings: Any) -> list:
def set_setting(settings: Any, key: Any, typed: Any) -> None:
```

`SETTING_ROWS` names each row and `COUNT_SETTINGS` says which take a whole number, so
both hosts draw the page and write a value with no host code of their own. A count
read as text, or under one, takes its own default.

`src/trading/ata_spm_push.py` — the count read safely, and what persists

```python
def read_candles(asked: Any) -> int:
    """``asked`` as a whole number, or ``DEFAULT_CONFIRMATION_CANDLES`` below one."""

PERSISTED_SETTINGS = ("hits_per_scan", "confirmation_share_pct", "confirmation_candles")
```

Three settings persist. Hits per scan, the confirmation share and the confirmation
read candles are written on every change and read back when the page is built. The
other three live for the life of the process.

`src/trading/ata_spm_push.py` — where the persisted settings sit

```python
def settings_path() -> Path:
    """``Path.home() / STATE_DIR_NAME / ATA_SPM_SETTINGS_NAME``."""
```

A typed message format may carry four keys in braces. A format naming any other
key, or one the formatter cannot parse, no longer stops the scan: the standard
wording is written and one warning names the key.

`src/trading/ata_spm.py` — the keys a message format may carry

```python
MESSAGE_FORMAT_KEYS = ("label", "reading", "direction", "confidence")
MESSAGE_FORMAT_REFUSED_LOG = (
    "ATA-SPM message format refused, %s; the standard wording is used. Keys: %s"
)
```

### The push targets

Ten targets ship. Adding one is adding a row: no phase names a target, and every
screen and folder writer reads the rows, so a new row needs no screen edit. Signal
publishes no way for a program to post into a group and is not a row.

The operator asked for the three that joined last, and ruled on Signal.

> ATA-SMP - Need to add post / message distribution for Discord, Telegram, WhatsApp, and Signal.

> ATA-SMP - For Signal, if its not being used for this sort of thing then we can skip it.

| Target | Body ceiling | Title ceiling | Counted in | Image |
| ------ | ------------ | ------------- | ---------- | ----- |
| X | 280 | none | Weighted characters | 1200 by 675 |
| Instagram | 2200 | none | Characters | 1080 by 1350 |
| LinkedIn | 3000 | none | Characters | 1200 by 627 |
| TikTok | 4000 | 90 | UTF-16 runes | 1080 by 1920 |
| Facebook | none published | none | Characters | 1200 by 630 |
| Threads | 500 | none | UTF-8 with emoji | 1080 by 1350 |
| Reddit | 40000 | 300 | Characters | 1200 by 628 |
| Discord | 2000 | none | Characters | 1200 by 675 |
| Telegram | 1024 | none | Characters | 1280 by 720 |
| WhatsApp | 65536 | none | Characters | 1200 by 675 |

Every number came off the platform's own documentation and each one is cited on its
own page. Where a platform publishes no number, the row records that rather than
carrying a guess. TikTok's title is empty because the header alone is over 90.

[The push target rules](../../audits/2026-09-06_ata_platform_rules.md) — one
section per target, with the page each number came from

```
Facebook   body ceiling: no number published
           the row carries NO_LIMIT_PUBLISHED, and phase four applies none
```

Two platforms named at the start are not rows, and both were left out for the same
reason: a rendered chart has no route in. One publishes an idea through its website
and states that it has no API for it. The other's upload endpoint accepts video
only.

One row describes one target, and one tuple of rows is every screen's source.

`src/trading/ata_spm_push.py` — the row, and the names every screen reads

```python
@dataclass(frozen=True)
class PushTarget:
    """One push target: its sections, its ceilings, its header and its image size."""

PUSH_TARGETS: tuple[PushTarget, ...] = (...)
TARGET_NAMES = tuple(one.name for one in PUSH_TARGETS)
SECTION_CALL = "call"
SECTION_INDICATORS = "indicators"
COUNT_WEIGHTED = "weighted"
```

`src/trading/ata_spm_push.py` — the header one row takes, and the row that names its own

```python
TARGET_X = "X"
TARGET_WHATSAPP = "WhatsApp"

PushTarget(
    TARGET_X,
    (SECTION_CALL, SECTION_INDICATORS),
    body_limit=280,
    count_unit=COUNT_WEIGHTED,
    header=X_HEADER,
    image_width_px=1200,
    image_height_px=675,
)

def target_header(target: Any) -> str:
    """The row's own header, ``FIXED_HEADER`` where the row names none."""
```

### The post text

One routine writes every piece of post text. It puts the header on top, the
evidence under it, and the organisation address at the bottom. No caller supplies
the address and no caller can remove it. The body, the caption, the thread root and
the title all carry it, on every target.

`src/trading/ata_spm_push.py` — the post, written once

```python
def compose(lines: Any, header: Any = FIXED_HEADER) -> str:
    """``header`` over ``lines`` over ``ORGANIZATION_URL``.

    ``fit_to_target`` drops ``lines`` to reach a ceiling and reaches neither
    ``header`` nor ``ORGANIZATION_URL``.
    """
```

The header is a field on the venue's row, and every row takes the fixed header
unless it names its own. Nine rows take it and the X row names a short header. A
venue is changed by editing its row; nothing branches on a venue's name.

`src/trading/ata_spm_push.py` — the two headers and the address

```python
FIXED_HEADER = (
    "This is not investment advice. It is a demonstration of Ekthelius's "
    "proprietary TA engine housed in the Acervator governance execution "
    "platform."
)
X_HEADER = "Not investment advice. Acervator TA engine demonstration."
ORGANIZATION_URL = "https://github.com/Acervator-LLC"
```

The fixed header measures 144 in every unit, because it is plain ASCII. On X, with
the call line, the address at 23 weighted characters and two separators, the floor
is 122 of 280, leaving 158 for evidence. The short header measures 57 weighted
units and keeps three facts: that it is not investment advice, that it is
Acervator, and that it is a TA engine demonstration. The words are the operator's
to change; the three facts are not.

He asked for the shorter one.

> Should shorten specifically for X and maintain a consistent level of valuable data...

Phase four holds each body under its target's ceiling. It drops evidence lines,
longest first, and never the header or the address. A line drops whole, so no price
or band value is cut mid-digit, and the post says how many sentences were left out.

`src/trading/ata_spm_push.py` — what the fitter drops, and what it will not

```python
def fit_to_target(ranked: Any, target: Any) -> tuple:
```

Where a venue holds a title, the title stands on the first line, then a blank line,
then the body.

### The chart a post carries

The picture is drawn by the Charts tab's own renderer. No second drawing engine was
written for posts, because two engines drift apart and only one of them is the
screen the operator watches. The renderer's drawing state and paint routine sit in
a plain object. The Charts tab's chart is that object with a window around it, and
a post image is that object with a picture file around it.

`src/gui/native_chart.py` — one paint routine, two places to send it

```python
class ChartPainter:
    """The chart's drawing state and its paint routine, with no window around it."""

        def paint_to(self, p: QPainter, w: int, h: int) -> None:
            """Draw the whole chart onto ``p`` over a ``w`` by ``h`` area.

            The painter's device is the caller's: a widget from ``paintEvent``
            and a ``QImage`` from ``render_chart_png``.
            """
```

The operator asked for the two to be one renderer.

> Refining our chart renderer (the one currently used under the Asset Charts Tab) will allow us to upgrade the visuals for one and align this to visuals of out going SM posts thus unifying direct usage with SM exposure.

> Refining our chart renderer ... will allow us to upgrade the visuals for one and align this to visuals of out going SM posts thus unifying direct usage with SM exposure.

> let's migrate to the Charts tab and do its visual upgrades. After its chart renderer is fully upgraded, it will need to be migrated to ATA-SMP.

> After its chart renderer is fully upgraded, it will need to be migrated to ATA-SMP.

The split was forced by where a scan runs. Pressing Scan Now hands the work to a
background worker so the screen keeps drawing, and the drawing toolkit will not
build a window on a background worker. Driven, it does not raise an error that
could be caught; it kills the program. A picture file has no such rule, so the post
image is drawn straight onto the file and no window is made.

`src/gui/market_inspector.py` — the worker the scan runs on

```python
            self._scan_thread = threading.Thread(
                target=self._compute_scan,
                args=(settings.message_format, settings.max_supporting_indicators),
                name=ATA_SCAN_THREAD_NAME,
                daemon=True,
            )
```

The indicators on the picture are the ones that voted for the call, not the ones
the Charts tab happens to have switched on. Each overlay in the chart's registry
names the voter it draws, so the picture is chosen by the vote. All twelve voters
carry an overlay, and the header line names any voter the cap cut.

`src/gui/native_chart.py` — the overlays one vote draws

```python
def overlays_for_voters(voters: Any, max_overlays: int = NO_OVERLAY_CAP) -> tuple:
    """The overlay keys drawing ``voters``, and the voters no overlay draws."""
```

`src/gui/native_chart.py` — the overlay names its voter

```python
    ChartOverlay(
        key="bb",
        label="BB",
        colour_field="chart_band",
        pane=PRICE_PANE,
        occludes=False,
        draw="_draw_bollinger",
        tooltip="Bollinger Bands (20, 2σ) with cloud fill",
        voter="bollinger_bands",
    ),
```

**Max supporting indicators** decides how many are drawn. It was already the cap on
how many confirming sentences a post carries, and it is the same cap on the chart.
No second setting was added, and an unset value caps nothing.

`src/trading/ata_spm.py` — the unset cap, and the voters one call confirmed

```python
NO_INDICATOR_CAP = 0

def confirming_signals(vote: Any) -> list:
def timeframe_label(timeframe: Any) -> str:
```

`src/gui/native_chart.py` — what reached the picture and what did not

```python
@dataclass
class ChartImage:
    """One rendered chart on disk, and what the renderer could not draw.

    ``drawn`` and ``undrawn`` name voters: ``undrawn`` holds the ones no
    overlay draws and the ones ``max_overlays`` cut.
    """
```

The chart states the call. Three marks are drawn, and each one is earned. A badge
in the top right names the direction. A dashed rule and a triangle mark the last
bar, which is the bar the vote was made on. A strip under the time axis carries one
row per confirming voter: a square in the colour of the line that drew that voter,
and the sentence phase three wrote for it. A voter with no line still gets a row,
in the dim colour. Nothing is drawn that a voter did not read.

`src/gui/native_chart.py` — the direction and the readings the picture takes

```python
        def set_call(self, direction: str, readings=()) -> None:
            """Take one reversal direction and one reading line per voter.

            ``readings`` are ``(voter, text)`` pairs and ``_draw_call`` paints
            them under the time axis.
            """
```

A chart with no call set draws no badge, no bar mark and no strip, and keeps the
height it had before. The Charts tab is unchanged by any of it.

Phase three answers one record per call, and that record carries the file.

`src/trading/ata_spm.py` — the picture the pull holds

```python
@dataclass
class ChartPull:
    """The chart one reversal call was made on, and its confirming messages.

    ``image`` is that chart rendered to a PNG, which the post's caption
    captions.
    """
```

A venue image whose caller names no theme paints in the theme the window is in, and
the message stamp at its foot takes that theme's own axis text colour. A venue
image carries no resize grip; only a chart in a window draws one.

`src/gui/native_chart.py` — the theme one image paints in

```python
painter.set_theme(tokens if tokens is not None else theme_in_force())
```

Each venue takes its image at the size that venue's own page publishes for a single
image post. The two Meta feeds take the tallest shape one of them accepts, which
gives the panes the most room.

`src/trading/ata_spm_push.py` — the two figures each row carries

```python
    image_width_px: int = DEFAULT_IMAGE_WIDTH_PX
    image_height_px: int = DEFAULT_IMAGE_HEIGHT_PX
```

A height the natural layout fits draws the natural layout, and any height left over
goes to the price pane. A height the layout does not fit compresses in one order:
each sub-pane shrinks from its readable height toward its fold height; then the
reading strip folds from one row per reading to one row of voter names with their
swatches; then the price pane shrinks from its layout floor toward its paint floor.
The strip folds because the caption already carries every reading's sentence.

`src/gui/main_tabs/market_inspector_surface.py` — the grid's own column widths

```python
PANEL_TF_WIDTH_PX = 44
PANEL_CELL_WIDTH_PX = 58
PANEL_NET_WIDTH_PX = 52
PANEL_CONF_WIDTH_PX = 96
```

`src/gui/main_tabs/native_chart_surface.py` — the four heights the fold moves between

```python
TAG_HEIGHT_PX = 14
SUB_PANE_PLOT_BANDS = 7
SUB_PANE_LABEL_PX = TAG_HEIGHT_PX
SUB_PANE_READABLE_PX = SUB_PANE_LABEL_PX + SUB_PANE_PLOT_BANDS * TAG_HEIGHT_PX
SUB_PANE_FOLD_PX = 28
PRICE_PANE_LAYOUT_FLOOR_PX = 220
PRICE_PANE_PAINT_FLOOR_PX = 120
```

A sub-pane's readable height is 112 pixels, a label row over seven plot bands, and it
folds to 28.

A height under the least layout is refused by name. The folder keeps its text file
and the emitter row for that venue reads not ok.

`src/gui/native_chart.py` — the refusal a short image takes

```python
NO_IMAGE_HEIGHT = 0

def strip_folded(width: int, height: int, readings: Any) -> bool:
def _least_height_for_panes(width_px: int) -> int:
def _minimum_height_for_panes(width_px: int) -> int:

IMAGE_TOO_SHORT_NOTE = (
    "{width}x{height} cannot hold the panes: {least} px is the least "
    "height at that width."
)
```

Each chart image carries its wording on it: the header, the call's own headline,
then the address. The message takes 55 pixels at the foot of the image, 8 of
padding above, 8 below and 13 for each of its three lines. A chart given no message
is 55 pixels shorter and carries none.

`src/trading/ata_spm.py` — the wording one image carries

```python
def post_caption(vote: AssetVote) -> str:
    """The header, the call's headline and the address, as the image's foot."""
```

Each bucket entry draws that picture scaled to the entry's width: a thumbnail closed
and a larger view open, each at the height its own shape needs. An entry whose post
names no file on disk draws a rectangle strip.

`src/gui/main_tabs/market_inspector_surface.py` — the two sizes one entry draws

```python
THUMBNAIL_WIDTH_PX = 120
THUMBNAIL_HEIGHT_PX = 36
PREVIEW_WIDTH_PX = 320
PREVIEW_HEIGHT_PX = 160
```

`src/gui/main_tabs/market_inspector_surface.py` — the picture one entry draws

```python
NO_IMAGE_SIZE = (0, 0)

def chart_image(post: Any) -> tuple:
    """That post's own PNG as a data address and its size, or ``NO_IMAGE_SIZE``."""
```

The Qt entry decodes that address into an image; the page places one image element
with the same address in the same box. Both hosts read one `post_chart` payload.

### The venue folders

The chart root holds one folder per venue, named for it. Each venue folder holds
that venue's own version of every call: the chart with the venue's message at its
foot, the same message as plain text beside it, and for X and WhatsApp a compose
address as an Internet Shortcut.

`src/trading/ata_post_paths.py` — the root and one venue's folder

```python
ATA_POST_ROOT: Path = Path.home() / ".acervator_ata_posts"

def venue_post_root(venue: Any, root: Any = None) -> Path:
    """One venue's own folder under the post root."""
```

The operator asked for the folders and for the message on each image.

> Ready to Send Bucket - Want a folder button that opens the chart image directory. Want the standardized message marked on each image. Want this loading push candidates via a functioning market scanner...

> Should have a catered folder for each venue.

> Seems most of this stuff is price gated so will also need a folder where charts customed for each venue can be viewed and manually posted.

The files are written inside phase three from the candles already held, in the same
call that draws the root picture, so no venue is asked for a candle twice. A market
the live gate chains refuse writes nothing anywhere.

`src/trading/ata_venue_folders.py` — the folder write

```python
def write_venue_posts(vote: Any, candles: Any, posts: Any) -> dict:
def write_text(path: Path, body: str) -> None:
```

`src/gui/native_chart.py` — the wording the painter stamps at the foot

```python
        def set_caption(self, text: str) -> None:
```

`FormattedPost.folder_path` names the venue folder each post's files sit in.

`src/trading/ata_post_paths.py` — the files one venue folder holds

```python
POST_TEXT_SUFFIX = ".txt"

def get_ata_post_root() -> Path:
def post_image_path(symbol: Any, timeframe: Any, stamp: Any) -> Path:
def prune_post_images(path: Path) -> tuple:
```

`src/trading/ata_spm_push.py` — what one post names on disk

```python
@dataclass(frozen=True)
class FormattedPost:
    """One venue's post: its body, its title, and the files its folder holds."""

def venue_files(pull: Any, target: Any) -> tuple:
```

`src/trading/ata_venue_folders.py` — the two compose addresses

```python
X_INTENT_FORMAT = "https://x.com/intent/post?text={text}"
WHATSAPP_INTENT_FORMAT = "https://wa.me/?text={text}"
INTENT_SHORTCUT_FORMAT = "[InternetShortcut]\nURL={url}\n"
```

The folder keeps the newest picture of each market and removes the older ones. A
market is one asset on one timeframe, so one asset on the hourly chart and the same
asset on the daily chart are two markets and each keeps its own newest picture.

`src/trading/ata_post_paths.py` — how many stay, and why that number

```python
#: ``ata_spm_push.format_run`` keys its pulls by symbol and timeframe, last
#: write winning, so one image per market is every image a post can name.
POST_IMAGES_KEPT_PER_MARKET = 1
```

Nothing in the application can name an older picture, so nothing loses one. Phase
seven does not need one either: it reads the chart again from the market data, never
from the folder, and the post it writes is text.

The trim happens on the same press that draws a picture, so the folder is never
larger than one scan's worth of pictures plus the newest of every market scanned
before. It reads one folder, the one its own file names, and goes no deeper. A file
whose name a post picture could not have produced is not touched. A picture being
written is never taken: the protection is the operating system's own refusal, and a
refused file survives, is reported as refused, and goes on the next press.

`src/trading/ata_post_paths.py` — the line every trim writes

```python
PRUNE_LOG = (
    "ATA post store: removed %d image(s), reclaimed %d byte(s), kept %d, refused %d"
)
```

The Chart Folder button opens the root, so every venue folder is in view, and the
press writes one Activity Log line naming the folder it opened. The folder's
address is handed to the operating system's own handler. No browser is driven and
nothing is typed into one.

`src/gui/main_tabs/market_inspector_surface.py` — the line and the hand-off

```python
CHART_FOLDER_OPENED_LOG = "ATA chart folder opened: %s"

def chart_folder_line(root: Any) -> str:
def page_links(page: Any) -> tuple:
def link_segments(text: Any) -> list:
```

`src/trading/ata_spm_push.py` — the hand-off to the operating system

```python
def open_path(path: Any) -> bool:
```

`page_links` is the whole list a press may name on the open page. Any other address
opens nothing and the window records the refusal.

### Sending

Every post waits in the approval bucket. The operator approves or declines each one,
and no button sends a declined post.

`src/gui/main_tabs/market_inspector_surface.py` — the five buttons the bucket carries

```python
APPROVE_LABEL = "Approve"
DECLINE_LABEL = "Decline"
POST_SELECTED_LABEL = "Post Selected"
POST_ALL_LABEL = "Post All"
FULL_AUTO_LABEL = "Send Bucket Full Auto"
```

The three send buttons share one width, the width that already held the longest
wording, and wrap at the count the zone holds: one at a 700-pixel tab, two at 900,
three at 1400 and above.

`src/gui/main_tabs/market_inspector_surface.py` — the shared button width

```python
BUCKET_BUTTON_WIDTH_PX = 184
```

Each post takes one of three routes. The route is decided by the post's own venue
and what is held for it.

`src/trading/ata_spm_push.py` — the three routes

```python
ROUTE_API = "api"
ROUTE_INTENT = "intent"
ROUTE_FOLDER = "folder"
```

| Route | Which posts take it | What a press does |
| ----- | ------------------- | ----------------- |
| api | Discord and Telegram, once held and the ceiling is set | one request carrying the text and the picture |
| intent | X and WhatsApp | hands the shortcut to the operating system's handler; the picture is attached by hand |
| folder | every other venue | hands the venue folder to the operating system's handler |

Discord and Telegram are the two API senders. Both take a typed credential rather
than a browser sign-in.

`src/trading/ata_spm_send.py` — the two senders

```python
SEND_ROUTES = {
    TARGET_DISCORD: send_discord,
    TARGET_TELEGRAM: send_telegram,
}

def build_sender(settings: Any, transport: Any = None) -> ApiSender:
```

The two target names those keys use are declared beside the rows, in
`src/trading/ata_spm_push.py`.

`src/trading/ata_spm_push.py` — which route a post takes, and which targets a sender serves

```python
def route_for(post: Any, settings: Any) -> str:
def deliver_one(post: Any, sender: Any, now: Any) -> Any:
def sender_takes(sender: Any, target: Any) -> bool:
```

A sender serves every target while it names none of its own, which is what a
`RecordedDestination` does, and otherwise only the ones it names.

One request per post, as multipart form data, through the same address opener the
sign-ins use. A venue answering 429 is read for its wait. A 401 or 403 is read as
the credential refused, with what the venue said. A caption over its venue's ceiling
is refused before any request, with the ceiling and the measure named. Nothing
retries by itself; the post waits in the bucket for the next press.

`src/trading/ata_spm_send.py` — the three refusals a send reports

```python
RATE_LIMITED_FORMAT = "429, retry after {seconds:g} s"
CREDENTIAL_REFUSED_FORMAT = "{http}, the credential was refused: {said}"
HTTP_REFUSED_FORMAT = "{http}, {said}"
```

The operator set the bound on how far this goes.

> This will have to do. Do not want to build something that risks myself or others being banned.

All three send routes obey one ceiling, counted over the hour ending now. The
ceiling starts unset, and an unset ceiling releases nothing: a fresh install cannot
publish until the operator sets a number.

`src/trading/ata_spm_push.py` — the ceiling every send route obeys

```python
def allows(self, now: float, ceiling: Any) -> bool:
    """Whether one more post fits under ``ceiling`` at ``now``."""
    limit = int(ceiling or NO_CEILING_SET)
    if limit <= NO_CEILING_SET:
        return False
    return self.sent_within_hour(now) < limit
```

`src/trading/ata_spm_push.py` — the two refusals a held post reports

```python
NO_CEILING_TEXT = "Max posts per hour is unset. Nothing leaves."
RATE_HELD_TEXT = "{sent} post(s) sent this hour, ceiling {ceiling}."
```

A second guard holds a repost back. A ticker reaches one push target once an hour,
whatever composed the post, so a second call on the same ticker is refused exactly
like a repeat of the first.

`src/trading/ata_spm_push.py` — the hour the guard measures

```python
def allows(self, now: float, symbol: Any, target: Any) -> bool:
    """Whether an hour has passed since ``symbol`` last reached ``target``."""
    gap = self.since(now, symbol, target)
    return gap is NO_SEND_RECORDED or gap >= SECONDS_PER_HOUR
```

`src/trading/ata_spm_push.py` — what a held post reports

```python
REPOST_HELD_FORMAT = (
    "{symbol} reached {target} {minutes:.0f} minute(s) ago; "
    "one post per ticker per hour."
)
```

Each bucket entry's status line carries its venue, its approval state, and then the
last press's outcome.

`src/trading/ata_spm_push.py` — the five outcomes a status line can carry

```python
STATUS_SENT_FORMAT = "sent · {destination}"
STATUS_NOT_SENT_FORMAT = "not sent · {detail}"
STATUS_IN_FOLDER_TEXT = "in folder"
STATUS_INTENT_OPENED_TEXT = "intent handed to the OS"
STATUS_INTENT_READY_TEXT = "intent ready"
```

Before any press the badge carries the confirmation timer's status instead.

`src/gui/main_tabs/market_inspector_surface.py` — the badge one entry's head row draws

```python
def bucket_badge(held: Any) -> tuple:
    """The last press's delivery, else the timer's own status."""
```

`src/trading/ata_venue_folders.py` — the text one post writes beside its picture

```python
def post_text(post: Any) -> str:
```

Every press runs on its own thread, one per press, and records cross back to the
window thread. A press made while one runs is refused on the Activity Log.

`src/gui/market_inspector.py` — the hand-off thread

```python
HAND_OFF_THREAD_NAME = "ata-smp-hand-off"
HAND_OFF_BUSY_TEXT = "ATA-SPM %s pressed while a hand-off is running; press ignored"
```

`src/trading/ata_spm_push.py` — the lines a press writes

```python
PRESS_LINE_FORMAT = "ATA-SPM hand-off: {line}"
NOTHING_APPROVED_TEXT = (
    "ATA-SPM Post All: no post is approved. Approve one, then press again."
)
FULL_AUTO_TOGGLED_FORMAT = "ATA-SPM Send Bucket Full Auto: {state}."
```

Every send writes one block on the Live tab's API Interaction Log naming the venue,
the action, the post, the text length, the image size and the message id or the
refusal. The recorded endpoint names the route with the token left out.

`src/trading/ata_spm_send.py` — the two recorded endpoints

```python
DISCORD_LOGGED_ENDPOINT = DISCORD_API_BASE + "/<id>/<token>?" + DISCORD_WAIT_QUERY
TELEGRAM_LOGGED_ENDPOINT = TELEGRAM_API_BASE + "/bot<token>/" + TELEGRAM_SEND_PHOTO
```

Every entry the connector records reaches that log from whatever thread made it.
The main window carries one signal and one receiver, and the Live tab registers the
receiver, so an entry from a scan thread crosses the signal and lands on the GUI
thread. The receiver refuses any other thread and writes a violation file instead.

`src/gui/main_window.py` — the crossing every API entry takes

```python
    apiEntryLogged = Signal(object)

    def _cross_api_event(self, entry: Any) -> None:
    def _on_api_event(self, entry: Any) -> None:
```

The scan's own progress and its failure cross the same way, and the tab hands the
inspector the Live tab's Activity Log pane. Where that pane is absent the phase
lines reach the log alone, and the tab says so.

`src/gui/market_inspector.py` — the three signals and the log the tab writes to

```python
    scanProgressed = Signal(object)
    scanFailed = Signal(str)
    ACTIVITY_INFO = "info"

    def _say(self, message: str, level: str = ACTIVITY_INFO) -> None:
    def _on_scan_progress(self, progress: Any) -> None:
    def _set_scan_busy(self, busy: bool) -> None:
    def set_activity_log(self, log: Any) -> None:
```

### The venue sign-in pages

Level 1A shows the venue name, the address it posts to, the permissions it asks for,
and one box per value that venue needs. It shows no other venue's boxes.

`src/trading/ata_spm_push.py` — what one press opens

```python
    def open_credentials(self, target: Any) -> Optional[str]:
        """Show one push target's Level 1A page, and answer which target it draws."""
        found = push_target(target)
        if found is None:
            return None
        self.settings_open = True
        self.credential_target = found.name
        self.connect_result = None
        return self.credential_target
```

Each venue row declares two sets. The fields are the values the operator types,
which a venue hands him when he registers an application. The issued set is the
values the sign-in obtains, which are never typed.

| Venue | Boxes on its page | The sign-in issues | Posts to |
| ----- | ----------------- | ------------------ | -------- |
| X | Client ID, Client secret | Access token, Refresh token | `https://api.x.com/2/tweets` |
| Instagram | App ID, App secret | Instagram user id, Access token | `/<IG_ID>/media` then `/<IG_ID>/media_publish` |
| LinkedIn | Client ID, Linkedin-Version | Access token | `https://api.linkedin.com/rest/posts` |
| TikTok | Client key, Client secret, Verified URL prefix | Open id, Access token, Refresh token | `/v2/post/publish/content/init/` |
| Facebook | App ID, App secret | Page id, Page access token | `/<page_id>/feed` and `/<page_id>/photos` |
| Threads | App ID, App secret | Threads user id, Access token | `/<threads-user-id>/threads` then `/threads_publish` |
| Reddit | App ID, App secret, Subreddit, User agent | Access token, Refresh token | `https://www.reddit.com/api/v1/access_token` then `/api/submit` |
| Discord | Webhook URL | none | the channel's own webhook |
| Telegram | Bot token, Chat id | none | the bot's `sendPhoto` |
| WhatsApp | none | none | the Click-to-Chat address in the venue folder |

Every value came off that platform's own published documentation, recorded in
[the platform rules audit](../../audits/2026-09-06_ata_platform_rules.md).

Seven venues use three-legged OAuth: not one issues a working token from an app id
and a secret alone. The operator sends himself to the venue in a browser, approves
there, and the venue sends a code back to the program. A venue reads as held on
Level 1 only once both sets are in the vault, so the button turns on when the
sign-in has actually run.

| Venue | Approval address | Token address |
| ----- | ---------------- | ------------- |
| X | `https://x.com/i/oauth2/authorize` | `https://api.x.com/2/oauth2/token` |
| Instagram | `https://www.instagram.com/oauth/authorize` | `https://api.instagram.com/oauth/access_token` |
| LinkedIn | `https://www.linkedin.com/oauth/native-pkce/authorization` | `https://www.linkedin.com/oauth/v2/accessToken` |
| TikTok | `https://www.tiktok.com/v2/auth/authorize/` | `https://open.tiktokapis.com/v2/oauth/token/` |
| Facebook | `https://www.facebook.com/v25.0/dialog/oauth` | `https://graph.facebook.com/v25.0/oauth/access_token` |
| Threads | `https://threads.com/oauth/authorize` | `https://graph.threads.com/oauth/access_token` |
| Reddit | `https://www.reddit.com/api/v1/authorize` | `https://www.reddit.com/api/v1/access_token` |

X, LinkedIn and TikTok require PKCE for a desktop program, so those three send a
`code_challenge` on the approval call and a code verifier on the token call. Every
route sends its own `redirect_uri` on both calls.

Three venues take a second call after the exchange: Instagram and Threads trade the first
token for one that lasts sixty days, and Facebook trades for a long-lived user
token and then reads the Page token off the account. Reddit authenticates with HTTP
Basic, refuses a generic user agent, and issues no refresh token unless the request
asks for a permanent duration. TikTok names its client field `client_key`.
LinkedIn's native address takes no client secret at all.

| Venue | How it renews |
| ----- | ------------- |
| X | by itself, refresh token grant, which needs `offline.access` |
| Reddit | by itself, refresh token grant |
| TikTok | by itself, refresh token grant, valid 365 days |
| Instagram | by itself, once the token is 24 hours old |
| Threads | by itself, once the token is 24 hours old |
| Facebook | no renewal; a long-lived Page token carries no expiry date |
| LinkedIn | does not renew; partner-only, and he approves again every 60 days |

Six of the seven bind a loopback listener. It binds the loopback address and
nothing else, serves exactly one request, refuses a reply carrying a state it did
not generate, and closes. It never outlives one sign-in.

`src/trading/ata_spm_signin.py` — the listener, and the two ports

```python
LOOPBACK_HOST = "127.0.0.1"
EPHEMERAL_PORT = 0
FIXED_CALLBACK_PORT = 8723
CALLBACK_TIMEOUT_SECONDS = 180.0
TRANSPORT_TIMEOUT_SECONDS = 30.0
```

Four venues check the redirect character for character and publish no wildcard, so
no address a random port produces can ever match. Those four bind one declared
port, and Level 1A prints it. LinkedIn asks a native client for a random port and
TikTok publishes a wildcard port, so those two keep the operating system's port.

| Venue | The redirect to register |
| ----- | ----------------------- |
| X | `http://127.0.0.1:8723/callback` |
| Instagram | `http://127.0.0.1:8723/callback` |
| LinkedIn | nothing; its native page asks for no registered address |
| TikTok | `http://127.0.0.1:*/callback` |
| Facebook | `https://www.facebook.com/connect/login_success.html` |
| Threads | `http://127.0.0.1:8723/callback` |
| Reddit | `http://127.0.0.1:8723/callback` |

Facebook is the seventh, and it opens no listener. Meta requires HTTPS for an OAuth
redirect and publishes one desktop address, and it answers a desktop app in the
fragment of that address rather than with a code. A fragment never leaves the
browser, so the program draws the browser itself, for one sign-in at a time.

`src/trading/ata_spm_signin.py` — the desktop reply Facebook sends

```python
DESKTOP_RESPONSE_TYPE = "token"
FACEBOOK_DESKTOP_REDIRECT = "https://www.facebook.com/connect/login_success.html"
```

`src/gui/sign_in_view.py` — the browser the program draws

```python
class SignInView(QDialog):
    """One modal sign-in view, one web view, no address bar and no context menu."""
```

The sign-in view reaches exactly two addresses: the venue's approval address and
the venue's published redirect. Every other host ends the sign-in on the spot. It
opens no second window, cancels every download the venue's page asks for, and
empties the cookie jar of the off-the-record profile it held. Reaching the redirect
ends the sign-in and the reply's fragment is read. The operator closing the window
ends it, and so does 180 seconds passing.

`src/trading/ata_spm_signin.py` — the two hosts one sign-in may reach

```python
def sign_in_hosts(authorize_url: Any, redirect_address: Any) -> tuple:
    """The only two hosts one sign-in view may load."""
```

Discord and Telegram issue no token, so Connect checks that the typed value reads
as the form the venue's own page prints. It opens no browser and reaches no venue.
A webhook address or a bot token in another form is refused on the page, with the
form named. WhatsApp needs no sign-in at all.

`src/gui/main_tabs/market_inspector_surface.py` — the two wordings a typed venue carries

```python
SIGN_IN_TYPED_TEXT = (
    "Connect checks what you typed and holds it. No browser opens and no "
    "venue is reached."
)
SIGN_IN_NONE_TEXT = (
    "No sign-in. The post goes through the venue folder and the compose address."
)
```

Level 1A returns to Level 1 by itself only when the venue accepts. An empty box, a
missing route and a refusal from the venue each keep the page open and print what
failed.

`src/trading/ata_spm_push.py` — the four wordings Connect can print

```python
CONNECT_OK_FORMAT = "{target} accepted the credential."
CONNECT_FAILED_FORMAT = "{target} refused the sign-in: {error}"
MISSING_FIELD_FORMAT = "{label} is empty."
NO_CONNECTOR_FORMAT = "No sign-in route wired for {target}."
```

A refusal names the venue's own reason. The published standard puts that reason in
two fields, and only those two are read out.

`src/trading/ata_spm_signin.py` — the three refusal wordings

```python
HTTP_REFUSAL_FORMAT = "HTTP {status} {reason}"
VENUE_SAID_FORMAT = "{http}, and the venue said {said}"
VENUE_REASON_FORMAT = "{error}: {description}"
```

Every outcome writes one log line naming the target, whether it succeeded, and the
detail. The message line takes one colour per outcome, read by both builds: no
colour before a press, the theme's error colour on a refusal, and its success
colour on an acceptance.

`src/gui/main_tabs/market_inspector_surface.py` — the colour one outcome takes

```python
NO_COLOR = ""
MESSAGE_REFUSED_COLOUR = ds.ERROR
MESSAGE_ACCEPTED_COLOUR = ds.SUCCESS

def message_colour(answered: Any) -> str:
    """``NO_COLOR`` before a press, else the refused or the accepted colour."""
```

A pasted value is trimmed before it is judged and before it reaches a venue, and a
box holding only spaces is still reported empty.

`src/trading/ata_spm_push.py` — what Connect reads, and what it answers

```python
def connect_credentials(self, target: Any) -> ConnectResult:
def missing_field(self, target: Any) -> Optional[str]:
def typed_credential(self, target: Any, field: Any) -> str:
def set_credential_text(self, target: Any, field: Any, typed: Any) -> None:
def store_credential(self, target: Any, field: Any, value: Any) -> bool:
def set_connector(self, connector: Any) -> None:
def set_vault(self, vault: Any) -> None:
CONNECT_RESULT_LOG = "ATA-SPM sign-in on %s: accepted=%s, %s"
```

`src/trading/ata_spm_signin.py` — the two typed routes, and how a refusal is read

```python
REFUSAL_BODY_LIMIT = 4096

class SignInError(Exception):
    """A venue's own refusal, carrying ``refusal_text``."""

def sign_in_discord(typed: Any, session: Any) -> Any:
def sign_in_telegram(typed: Any, session: Any) -> Any:
def urlopen_transport(request: Any) -> Any:
```

Each host builds the session those routes run in, through `sign_in_session` on its own
side.

A refusal body is read up to that limit and no further.

`src/gui/sign_in_view.py` — what the sign-in view refuses

```python
class SignInPage(QWebEnginePage):
    def createWindow(self, kind: Any) -> None:
        """None, so no second window opens."""

    def _refuse_download(self, item: Any) -> None:
    def _release(self) -> None:
    def reach(self, url: Any) -> bool:
```

### The credential vault

The tokens are kept in one file outside the repository, encrypted under the same
passphrase every other stored credential in the product uses.

`src/core/encryption.py` — where the tokens sit

```python
DEFAULT_VAULT_PATH = Path.home() / ".acervator" / "ata_spm_credentials.json"
```

A keystroke writes memory and a finished box writes the vault. A box is finished
when the operator leaves it. A held value stores under its own key and an emptied
box deletes that key. A vault write runs the key derivation at the published
iteration count, which is why a write on leaving the box costs one such write rather
than one per keystroke.

`src/core/encryption.py` — the derivation cost

```python
_KDF_ITERATIONS = 600_000  # OWASP PBKDF2-HMAC-SHA256 guidance
```

`src/trading/ata_spm_push.py` — the key one value is held under

```python
VAULT_KEY_FORMAT = "{target}:{field}"

def vault_key(name: Any, field: Any) -> str:
```

`src/core/encryption.py` — the vault, and the two reads the page makes on every paint

```python
class CredentialVault:
    def store(self, key: str, value: str, salt: str) -> None:
    def delete(self, key: str) -> None:

class FileVault(CredentialVault):
    """A ``CredentialVault`` reading ``DEFAULT_VAULT_PATH`` and writing it on store."""

def default_vault() -> FileVault:
def vault_phrase(username: str) -> str:
def has_exchange(key: str) -> bool:
def encrypt(value: str, phrase: str) -> str:
```

`has_exchange` answers whether a value is held without decrypting one, which is why
Level 1A can ask it on every paint.

Nothing typed on the page reaches a view model, a render or a log. The page
publishes each box as a name and a wording and no value, plus the keys the vault
holds something for. A held box's wording says so, and typing into it replaces what
is held when the operator leaves it.

`src/gui/main_tabs/market_inspector_surface.py` — what one page publishes

```python
def credential_page(target: Any) -> dict:
    """One venue's page: its lines, its boxes as name and wording, and no value."""
```

`src/trading/ata_spm_push.py` — the keys the vault holds something for

```python
def held_fields(self, target: Any) -> tuple:
```

`src/gui/main_tabs/market_inspector_surface.py` — the wording a held box carries

```python
CREDENTIAL_HELD_PLACEHOLDER = "Held · type to replace"
```

`src/trading/ata_spm_push.py` — what a credential row on Level 1 publishes

```python
CREDENTIAL_HELD_TEXT = "held"
CREDENTIAL_MISSING_TEXT = "not held"
```

A page the operator filled before a restart takes Connect without being typed
again. There is no Save credentials control: Connect is what stores. The exchange
keys sit in the settings file and the push-target tokens in the vault file, two
files under one passphrase.

### What each venue needs before its page can work

Every platform issues these values only to an application the operator has
registered with that platform. The software cannot obtain a registration, so each
page names what is needed and where to register.

| Venue | Where to register | Review and cost |
| ----- | ----------------- | --------------- |
| X | `https://console.x.com` | no review; a paid usage plan, about $0.015 a post and about $0.20 with a link |
| Instagram | `developers.facebook.com/apps/creation/` | no review, free; a professional account on a Page, and a role on his own app |
| LinkedIn | `www.linkedin.com/developers/apps` | two tiers of review; a registered company, a verified Page, a screencast, and LinkedIn must switch on its native flow by hand |
| TikTok | `developers.tiktok.com/apps` | audit for a public post, free; until the audit, only he can see what it posts |
| Facebook | `developers.facebook.com/apps/creation/` | no review, free; a Page he administers and a role on his own app |
| Threads | `developers.facebook.com/apps/creation/` | no review, free; a Threads profile and a role on his own app |
| Reddit | `www.reddit.com/prefs/apps` | no review, free; register an app and pick a subreddit |

Meta grants standard access to every permission automatically, and it reaches any
account holding a role on the app, so Instagram, Facebook and Threads need no app
review. TikTok restricts every post an unaudited client makes to private viewing.
LinkedIn is the one venue that may refuse him outright, and its page states both
gates rather than offering a Connect that looks like it will work.

A word on a page becomes a link only where it names a host and a path. Every address
the open page publishes reaches the browser, and every address it does not publish
opens nothing and is recorded as refused. Nothing the operator typed and nothing a
venue answered is ever a link.

`src/gui/main_tabs/market_inspector_surface.py` — which words are links

```python
def link_address(word: Any) -> str:
    """``word`` as an openable address where it names a host and a path, else empty."""
```

### The hit chime

A hit sounds one chime the moment the window learns of it. A confirmation sounds one
more. A failed call sounds nothing. The tone is the Audio Suite's own generator, one
preset joining its table, rendered once per process to a short wav with a decay
applied and played through one output on the tab.

`src/gui/audio_suite.py` — the chime

```python
CHIME_PRESET = "Hit Chime"
CHIME_PARTIALS = [(1.0, 0.45), (2.0, 0.18), (3.0, 0.09), (4.16, 0.05)]
CHIME_SECONDS = 0.6
CHIME_BASE_HZ = 880.0
```

The chime plays at 0.5, the volume the suite's music player opens at. The Audio
Suite holds no mute control, so the chime has no mute and no slider of its own.

The operator asked for the chime and the timer together.

> Simulator - Scan Now - ... There should be a chime when there is a hit. Once a hit is made, an isolated confirmation read timer starts based on the original hit's TF. The confirmation read mechanic should be partially documented already if not implemented...

### The confirmation read timer

Each hit starts its own timer the moment it lands in the approval bucket. The first
read waits for the candle the hit was read on to close. Every read after it waits a
count of closed candles of the hit's own timeframe, and that count is a setting
starting at three. A daily hit reads again three days on; a weekly hit three weeks
on.

`src/trading/ata_spm_push.py` — the grid each read lands on

```python
DEFAULT_CONFIRMATION_CANDLES = 3
ONE_CANDLE = 1

def next_read_ts(
    at_ts: Any, timeframe: Any, now: Any, candles: int = ONE_CANDLE
) -> float:
```

The operator set that spacing.

> Confirmation timers are too short and should be a multiple of the timeframe on which the hit occurred i.e. a weekly chart confirmation read should not be happening again in a few days but in a few weeks and a daily chart should happen in a few days rather than a few hours.

The grid is anchored at the first close, so a read the venue delayed and a retry both
land back on it. A changed count re-anchors a running timer: it keeps the grid
beginning at the hit's own candle close and takes the new step.

`src/trading/ata_spm_push.py` — the seconds one candle takes

```python
TIMEFRAME_SECONDS = {"5m": 300, "1h": 3600, "1d": 86400, "1w": 604800}
MONTH_TIMEFRAME = "1M"
```

A weekly candle closes at Monday 00:00 UTC, the instant the fetcher's rollup and
the chart venue both stamp a week with. A monthly candle closes at the first instant
of the month.

A venue that has not published the awaited candle is read again after a short wait,
a bounded number of times, then at the next close.

`src/trading/ata_spm_push.py` — the retry

```python
FOLLOW_UP_RETRY_S = 60.0
FOLLOW_UP_RETRY_CAP = 5
```

The tab's own clock wakes once a second and hands every due timer to one worker
thread. The worker reads the market's newest candles through the scan's own route
and judges the call. The outcome crosses back to the window thread, which writes the
entry, the field, the Activity Log and the emitter row.

The verdict counts closed candles and reads no clock; the timer reads the clock only
to choose when to read. The candles counted are those opened at or after the call's
bar open whose close time is at or before the read, so the call's own candle is
candle one once it closes. A venue's partial bar is never read as a close.

`src/trading/ata_spm_push.py` — the candles one read counts

```python
def closed_candles(candles: Any, timeframe: Any, closed_before: Any) -> list:
    """The candles of ``candles`` that opened at or after the call and have closed."""
```

Three outcomes exist.

`src/trading/ata_spm_push.py` — the three verdicts

```python
OUTCOME_CONFIRMED = "confirmed"
OUTCOME_FAILED = "failed"
OUTCOME_OPEN = "open"
```

Price moving the favourable way as far as the confirmation target confirms the call.
The target is a share of the run from the call's close to the Bollinger midline, and
the midline is recomputed on every candle after the call rather than frozen at it.
The share is the confirmation share setting, and a share of zero sets no target, so
the read says so instead of claiming a result.

`src/trading/ata_spm.py` — the moving target phase seven measures against

```python
def midline_after(candles: Any, at: Any) -> list:
    """The Bollinger middle band at every candle after index ``at``.

    ``BollingerBands`` computes its published band on each window, so the
    target phase seven measures against moves with the market.
    """
```

A target exists only while the midline lies on the side the call expects the run to
go: above a bullish close, below a bearish one. While the midline lies behind the
call, the read stays open and says so.

`src/trading/ata_spm_push.py` — whether a target exists yet

```python
def midline_ahead(direction_text: Any, call_close: Any, midline: Any) -> bool:
    """Whether the midline lies on the side the call expects the run to go."""
```

The trend carrying on for three candles in a row fails the call. A continuation is
evidence against a reversal call, so the two outcomes are not the same shape. The
count is in the call's own timeframe, and no wall clock is read, so a daily call
cannot fail on the afternoon it was made.

`src/trading/ata_spm_push.py` — the candles a failure needs

```python
CONTINUATION_CANDLE_FLOOR = 3
```

A call short of that floor is not ready. The read then says how far the trend has
run against the call instead of claiming a result, and no candle is invented to
reach the floor.

`src/trading/ata_spm_push.py` — the wording a call under the floor carries

```python
FOLLOW_UP_NOT_READY_FORMAT = (
    "the trend has held for {run} of the {floor} candles a failure needs, "
    "last close {close:g}, target {target:g} not reached"
)
```

A settled call stops being watched and an open one stays, so no call is posted on
twice. A settled call's follow-up post is one per venue and lands in the bucket as
the scan's own entries do. A timer stops when its read settles the call, or when its
entry leaves the bucket.

`src/trading/ata_spm_push.py` — the status a timer publishes

```python
BUCKET_META_FOLLOW_UP_FORMAT = "{target} · {state} · {follow_up}"
FOLLOW_UP_STATUS_OPEN_FORMAT = "open · next read {when}"
FOLLOW_UP_STATUS_SETTLED_FORMAT = "{state} · close {close:g}"
```

`src/trading/ata_spm_push.py` — the lines a timer and a read write

```python
FOLLOW_UP_TIMER_LINE_FORMAT = (
    "ATA-SPM confirmation timer for {symbol} {label}: next read {when}"
)
FOLLOW_UP_READ_OPEN_LINE_FORMAT = (
    "ATA-SPM confirmation read for {symbol} {label}: {state}, next read {when}"
)
FOLLOW_UP_READ_SETTLED_LINE_FORMAT = (
    "ATA-SPM confirmation read for {symbol} {label}: {state}, close {close:g}"
)
```

### The timer tiles

The region right of the Timeframe row, the scan line and the stepper holds one tile
per watched call, in both builds. A tile reads the market and its timeframe on its
first line, with a small red cross at the right, and the time to the call's next
read on its second, counted down once a second on the tab's own clock. At zero the
read fires and the tile reads `reading` until the outcome crosses back. An open call
then counts down to its next close; a confirmed or failed call reads its outcome and
its close. A settled call's tile stays until its entry leaves the bucket.

`src/trading/ata_spm_push.py` — what a tile reads

```python
TIMER_PAIR_FORMAT = "{symbol} {label}"
TIMER_COUNTDOWN_FORMAT = "{hours:02d}:{minutes:02d}:{seconds:02d}"
TIMER_COUNTDOWN_DAYS_FORMAT = "{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
TIMER_READING_TEXT = "reading"
```

Tiles wrap by the region's width at 132 pixels each, the width the widest pair a
class lists takes at the caption size. The region is 110 pixels tall, three tile
rows, and scrolls past that, so the tiles never push the stepper and the field down
the zone. While no call is watched the region reads "No confirmation timer
running."

The cross opens one pop-up naming the pair. No leaves the tile, its countdown and
its timer standing. Yes removes that tile and its timer and nothing else: the call
keeps its entry in the bucket, the bucket keeps its count, and every other tile
keeps its countdown. The Activity Log records the removal.

`src/gui/main_tabs/market_inspector_surface.py` — the cross and its question

```python
TIMER_CLOSE_PART = "timer-close"
TIMER_CLOSE_TEXT = "×"
TIMER_DROP_TITLE = "Delete confirmation timer"
```

The operator asked for the cross.

> Confirmation Reading timers need a small red 'x' for their deletion and this provides a confirmation pop up.

The pop-up comes from the host in both builds, the way the hit chime does, so both
builds ask the same question.

`src/trading/ata_spm_push.py` — the rows the region draws, and what a removal takes

```python
@dataclass(frozen=True)
class TimerTile:
    """One watched call's pair, its countdown and its outcome."""

@dataclass
class FollowUpTimer:
    """One call's next read, its read count and the count it steps by."""

def timer_tiles(self) -> list:
def drop_timer(self, value: Any) -> bool:
    """Drop one open timer from ``timers`` or one call from ``settled``."""
def watch_run(self, run: Any, candles: Any) -> None:
def take_outcome(self, outcome: Any, candles: Any) -> None:
def after_scan(self, run: Any) -> None:
def candle_close_ts(at_ts: Any, timeframe: Any) -> float:
```

The Qt widget draws those rows as frames and the page draws the same rows from its
own skin, with the cross as its own element. The clock's tick hands the page the rows
alone, so a countdown moves without the whole payload.

The tile takes its colours from the theme's own tokens, so a theme change moves them.

```python
tile ground     SURFACE_INPUT      border        OUTLINE
the pair        TEXT_HIGH          countdown     PRIMARY
reading         WARNING            confirmed     SUCCESS      failed  ERROR
```

The Qt widget draws those rows as frames and the page draws the same rows as its own
elements. Each cross carries that row's own value, and both hosts reach one method on
the tab, which opens the pop-up and drops the timer on a Yes.

`src/gui/market_inspector.py` — the Qt tiles and the question

```python
class TimerTiles:
    def _build_tile(self, row: Any) -> QFrame:
    def show_tiles(self, rows: Any) -> None:

    def _ask_drop_timer(self, value: Any) -> None:
```

`src/gui/web/market_inspector.js` — the page's own cross

```javascript
function TimerClose({ closeValue }) { ... }
```

### The called markets the Charts tab keeps watching

Reaching the approval bucket does a second thing. The market joins a list the Charts
tab keeps, so the operator can watch a called market long after the post about it
has gone or been declined.

The board answers one row per market, never one per post. A market called on two
timeframes is still one market being watched, and the row carries the timeframes it
was called on and the vote of the most recent call.

`src/trading/ata_spm_push.py` — the row the Charts tab reads

```python
@dataclass(frozen=True)
class WatchedMarket:
    """One market on the ATA-SMP chart list, and the call that queued it."""

    symbol: str
    vote: str = VOTE_NEITHER
    timeframes: tuple = ()
```

Three places hold a called market and the board reads all three, oldest first: the
calls phase seven has settled, the calls it is still watching, and the posts sitting
in the bucket now. Filling the bucket from a new scan therefore does not drop an
older market from the chart list. The settled calls are read in key order, so the
list comes back in the same order every time.

A watched call is told apart by its asset, its timeframe and its bar's open time,
and by nothing else, so a hit recorded while a retired class name was chosen still
resolves and draws its tile.

`src/gui/market_inspector.py` — what this screen offers the Charts tab

```python
def watched_markets(self) -> list:
    """The markets ATA-SMP has called, for the Charts tab's second list.

    ``PushBoard.watched_markets`` is the one set phase seven also reads.
    """
    return self._push_board.watched_markets()
```

The screen hands that reader to the Charts tab when it is built. Nothing is copied
across, so the two screens cannot disagree about which markets are called. What the
Charts tab does with the list is on [the Charts tab page](asset-charts.md).

## Multi-Exchange Arbitrage

`src/trading/arbitrage.py` holds the cross-exchange price monitor and its spread
tracking. No module under `src/` imports it. The zone names the venues in reach and
stops there: it draws no arbitrage panel. The first two proposal forms are on screen;
the third is not.

In development.

## Phantom Bot HTF Signals

The zone is named, sized and drawn, and the row that builds it writes the same
sentence on every call. Nothing feeds it.

`src/gui/main_tabs/market_inspector_surface.py` — the row that never varies

```python
PHANTOM_HTF_ZONE = "phantom_htf"
PHANTOM_HTF_GROUP_TITLE = "Phantom Bot HTF Signals"
PHANTOM_HTF_UNWIRED_TEXT = "Phantom Bot source not wired."

[PHANTOM_HTF_ZONE, PHANTOM_HTF_GROUP_TITLE, PHANTOM_HTF_UNWIRED_TEXT],
```

In development.

## The asset logo library

An asset's mark is a library on disk, divided into a folder per asset class and a
folder per sector inside it. The library is filled by a step the operator starts
himself. Creating a position reads that library and never fetches.

`src/trading/logo_library.py` — where one asset's mark is filed

```python
def library_folder(asset_class: Any, sector: str = "") -> str:
    """``kept_folder(f"{asset_class}/{sector}")``, every segment sanitised."""
```

An asset with no sector tag sits in the class folder itself; no sector is guessed.
Every folder segment is sanitised the way a file name already is, so a sector named
with a space becomes one hyphenated folder.

The library covers every asset the connected venues list plus every asset the maps
hold: 542 assets, filed into 25 folders.

| Folder | Marks | Folder | Marks |
| ------ | ----- | ------ | ----- |
| crypto | 361 | crypto/interop | 5 |
| stocks/portfolio | 47 | crypto/oracle | 5 |
| forex/minor | 21 | commodities/energy | 4 |
| crypto/l1 | 18 | crypto/depin | 3 |
| crypto/dex | 9 | crypto/identity | 3 |
| crypto/defi | 8 | crypto/wallet-infra | 3 |
| crypto/meme | 8 | commodities/industrial-metals | 2 |
| commodities/precious-metals | 8 | crypto/payments | 2 |
| crypto/ai | 7 | crypto/privacy | 2 |
| crypto/l2 | 7 | crypto/stablecoin | 2 |
| forex/major | 7 | crypto/storage | 2 |
| crypto/gaming | 6 | crypto/rwa | 1 |
| | | crypto/wrapped | 1 |

The fill takes its asset list from the order rules already recorded for each venue,
not from a fresh venue call. Nothing is asked of any exchange or broker while the
library fills.

`src/trading/logo_library.py` — where the asset list comes from

```python
def venue_bases(document: Optional[dict] = None) -> tuple[str, ...]:
    """Every base asset the recorded venues list, sorted, each folded by ``underlying_base``."""
```

A venue lists some contracts on a multiple of an asset. The base is folded back onto
the asset only when the remainder names an asset some source already lists, so no
name is shortened on a guess.

```
1000A10   ->  A10      A10 is a recorded base
1000MOG   ->  MOG       MOG is a recorded base
1000PEPE  ->  PEPE      PEPE is a recorded base
1000SHIB  ->  SHIB      SHIB is a recorded base
00        ->  00        nothing is left after the digits
1INCH     ->  1INCH     INCH is not a recorded base
2Z        ->  2Z        Z is not a recorded base
```

Nothing in the running program starts the fill. It is started by hand, and it
refuses outright while the application holds the lock on the runtime directory.

```
python -m src.trading.logo_library --reads 40
python -m src.trading.logo_library --list
```

`src/trading/logo_library.py` — the refusal while the fleet trades

```python
TRADING_REFUSAL = (
    "the application is running and holds the instance lock; close it first"
)
```

The gap between two reads is 0.5 seconds, the figure the market scan already uses
for a host that publishes no limit. The hold after a rate refusal is 60 seconds. A
run is bounded by the number of addresses it may read, and a run that stops leaves
the marks it kept on disk and the unresolved assets in a file beside them, so the
next run reads only what is left.

`src/trading/logo_library.py` — where the unresolved assets are written

```python
UNRESOLVED_NAME = "unresolved.json"
```

An asset written to that file is skipped by every later run, including one whose
source has since come back.

`src/core/asset_logos.py` — the walk, its budget and what it answers

```python
LOGO_TIMEOUT_S = 10.0

class LogoBudgetSpent(RuntimeError):
    """Raised where a run has read every address it was allowed."""

class LogoCache:
    def read_budget(self, count: int) -> None:
    def kept_path(self, symbol: str) -> Optional[Path]:

@dataclass(frozen=True)
class LogoAnswer:
    """One asset's kept file, or the reason no address served an image."""

def resolve(
    symbol: Any,
    candidates: Any,
    timeout_s: float = LOGO_TIMEOUT_S,
    *,
    page_url: str = "",
    no_source_reason: str = "",
    folder: str = "",
) -> LogoAnswer:
```

`src/trading/logo_library.py` — how a ticker is settled against the coin list

```python
def choose_coin(ticker: Any, records: Any) -> Optional[dict]:
    """The coin a ticker names: by recorded name, by a lone rank, then by margin."""

def underlying_base(base: Any, known: Any) -> str:
```

### Where a mark is looked for

A crypto asset's mark is looked up in two steps. One read names every coin and its
id; a second read names the picture each id serves. A ticker is not a coin id, so an
address built out of a ticker is a guess, and the address the ticker used to build
serves a web page rather than an image.

`src/exchange/crypto_assets.py` — the retired guess

```python
SYMBOL_ICON_URL = "https://www.cryptocompare.com/media/img/cc_icons/{symbol}.png"
```

`src/exchange/crypto_assets.py` — the two reads behind a coin's mark

```python
COIN_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"
COIN_MARKETS_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&per_page={size}&page=1&ids={ids}"
)
```

A ticker several coins carry is settled by the recorded name, then by a lone market
rank, then by a rank far better than the next. A ticker it cannot settle is written
down with its candidates and no address.

`src/trading/logo_library.py` — how far apart two ranks must sit

```python
COIN_RANK_MARGIN = 10.0
```

Every other asset is read from the organisation's own domain, at the two standard
locations a site serves its own icon at. Where neither answers an image, the
organisation's own page is read and the icon that page declares is asked next, and
last the share image the page declares. No third party is contacted, no key is held,
and nothing has to appear on the screen.

`src/trading/ata_asset_maps.py` — the two standard locations, and the domains they are read from

```python
ORGANISATION_ICON_FORMATS: tuple[str, ...] = (
    "https://{domain}/apple-touch-icon.png",
    "https://{domain}/favicon.ico",
)
ORGANISATION_SITES: dict[str, str]
```

`src/core/asset_logos.py` — the last location a mark is looked for

```python
SHARE_IMAGE_TAG: re.Pattern[str]
```

`SHARE_IMAGE_TAG` matches a meta tag whose property or name is the page's own share
image, folding case, so a page that answers its own document at every icon address
still yields one picture.

`src/core/asset_logos.py` — the icons a page declares for itself

```python
def declared_icons(page_url: Any, body: Any) -> tuple[str, ...]:
    """Every icon address one page declares, and its own share image last."""
```

A fund share and a currency pair answer their organisation's own site. Every other
US-listed ticker answers the regulator's own company page, which is keyed on the
ticker alone and needs no lookup, so an equity the map never carried still answers.
A metal quote answers nothing, because a metal has no issuer.

`src/trading/ata_asset_maps.py` — the regulator route

```python
REGISTRY_URL_FORMAT = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
    "&ticker={ticker}&type=10-K&dateb=&owner=include&count=10"
)
```

The regulator's own company page carries a web-address field and that field is
empty, so the register names the company and not its site.

No logo read reaches a trading venue's own domain.

`src/trading/ata_asset_maps.py` — the domains no read reaches

```python
VENUE_DOMAINS: frozenset[str] = frozenset({"coinbase.com", "sofi.com"})
```

A kept body must be an image, read from the body's own leading bytes rather than its
length. A length floor alone kept a web page as a picture once; the signature does
not.

`src/core/asset_logos.py` — the signatures a kept body must carry

```python
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"\x00\x00\x01\x00", "ico"),
    (b"BM", "bmp"),
)
```

The file name is built from the symbol, with every character a file name may not
carry replaced by one gap character, so a currency pair is kept under a hyphenated
name.

`src/core/asset_logos.py` — the file name

```python
def kept_name(symbol: str) -> str:
    """``symbol`` as the file name stem a kept logo takes, every other character ``KEPT_NAME_GAP``."""
    text = str(symbol).strip().upper()
    return "".join(
        one if one.isascii() and one.isalnum() else KEPT_NAME_GAP for one in text
    )
```

Reading a mark back by its symbol alone finds it at whatever depth it sits, so the
bot list and the wizard need no knowledge of the folders.

### What the library holds

| Sector | Targets | Marks kept | Resolving nothing |
| ------ | ------- | ---------- | ----------------- |
| crypto | 453 | 362 | 91 |
| stocks | 47 | 38 | 9 |
| currencies | 28 | 24 | 4 |
| commodities | 14 | 10 | 4 |
| total | 542 | 434 | 108 |

The 434 marks take 7,455,763 bytes and carry 395 distinct pictures: 311 PNG, 82
JPEG, 37 ICO and 4 WebP, the smallest 660 bytes and the largest 175,010. Every
picture two assets share belongs to one issuer, so seven fund shares share one asset
manager's mark and each currency group shares its central bank's.

Seven reasons cover every asset that resolves nothing.

| Reason | Assets |
| ------ | ------ |
| several coins carry the ticker at comparable market rank | 67 |
| no coin record carries the ticker, or its name | 22 |
| every address answered something that is not an image | 7 |
| the company no longer trades | 4 |
| a metal quote with no issuer | 4 |
| several coins carry the ticker and none carries a market rank | 2 |
| the domain names a trading venue | 2 |

The 22 with no coin record are venue index and derivative products. Four
organisations answer this platform's own user agent with a refusal, and one serves a
certificate this machine cannot verify. Nothing was relaxed to reach any of them.

Two sentences this page used to carry are overtaken, and both are quoted whole.

> "A stock, a fund share, a metal and a currency pair do not resolve the way a coin does."

> "the 47 stocks rows have no logo address
>     a company's own domain is not a fact this repository holds for a ticker,
>     and no keyless service keyed on a ticker was accepted"

A stock and a fund share now resolve from the organisation's own domain, and 43 of
the 47 stock rows carry a logo address. A metal quote still resolves nothing.

### Opening an asset's own organisation

Every address offered as openable is checked for its scheme first, and a refused one
is an empty address carrying the reason it is empty. Some schemes open a local file
or run a script instead of visiting a site, and an address for an asset arrives from
outside this repository. The check reads the same allowed set the guarded fetch
reads, so the two cannot drift apart.

`src/core/safe_url.py` — the check every offered address passes

```python
def openable_url(
    url: object,
    allowed_schemes: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
```

The file, javascript, vbscript and data schemes open nothing. An empty address
answers that no address is known.

### Where a mark is drawn

Six places draw an asset icon and all six read the library. A row draws the kept
file or the lettered disc and never waits on a network read.

`src/gui/main_tabs/bot_status_table_surface.py` — the size a row draws

```python
LOGO_SIZE_PX = 32
ROW_HEIGHT_PX = LOGO_SIZE_PX + 2 * ROW_LOGO_MARGIN_PX
```

Six of the 434 marks offer only 16 pixels, because their own source serves a
16-pixel icon, and those six draw at their own size in both builds. A row with no
mark draws its symbol exactly as it does today. None of the kept images enters the
repository: the library directory is ignored.

`src/gui/bot_wizard.py` — the one reader every drawing place uses

```python
KEPT_LOGOS = LogoCache()
```

`resolve` is never called from a wizard, and nothing there fetches. The six places that
draw an asset icon are the three bot wizards and the three Extractor bot tables, one
pair each under the live, the paper and the simulator directories.

```
src/gui/bot_wizard.py                       src/gui/widgets/extractor_bot_table.py
src/gui/paper/paper_bot_wizard.py           src/gui/paper/paper_extractor_bot_table.py
src/gui/simulator/sim_bot_wizard.py         src/gui/simulator/sim_extractor_bot_table.py
```

## What the emitters write

Every row below goes through one wire and nothing else. A topic declared in
`src/core/emit_contracts.py` is a tracked emitter, and a run that never fires it is
reported.

The operator set what the network is for.

> Entire idea for the Emitter Network is to provide us signals for verifying proper software function resulting from all user actions or automated sequences.

> Entire idea for the Emitter Network is to provide us signals for verifying proper software function resulting from all user actions or automated sequences...

> For this, will need to verify and / or wire in Emitter Network and update what the Inspector's subsystems (including ATA-SMP) write to the logs. Entire idea for the Emitter Network is to provide us signals for verifying proper software function resulting from all user actions or automated sequences...

| Topic | Written | Carries |
| ----- | ------- | ------- |
| `market_inspector.scan_started` | one per Refresh | forced, connector count, active symbols |
| `market_inspector.scan_finished` | one per Refresh | market count, duration, signals, pairs, source, error |
| `inspector.ata.scan_pressed` | one per press | whether a thread started, against True |
| `inspector.ata.scan_started` | one per press | the thread's name, against the scan thread's name |
| `inspector.ata.market_read` | one per market read | the candle count, against the vote floor |
| `inspector.ata.scan_finished` | one per press | markets read, against markets listed |
| `inspector.ata.volume_order` | one per class read | markets with a figure, against markets listed |
| `inspector.ata.hit` | one per hit | the running count, against the target |
| `inspector.ata.ticker_resolved` | one per press with text typed | the class the text landed in, against the class chosen |
| `inspector.scan.progress` | every ten markets and at the end | class, read, total, hits |
| `inspector.scan.list_source` | one per list read | class, source, count, the names not trading |
| `inspector.ata.candidate` | one per bucket entry | whether the image is on disk |
| `inspector.ata.image_size` | one per venue image | the written size, against the row's size |
| `inspector.ata.handoff` | one per post a press took | venue, route, outcome, destination |
| `inspector.ata.sent` | one per request | venue, symbol, timeframe, status, message id, elapsed |
| `inspector.ata.chime` | one per chime | its cause, the hits it covers, whether the player took it |
| `inspector.ata.follow_up_read` | one per read | candles counted, against candles the clock says have closed |

Each topic is named by one constant, so a topic and its writer cannot drift apart.

```python
SCAN_PRESSED_PIN, SCAN_STARTED_PIN, MARKET_READ_PIN, SCAN_FINISHED_PIN
CANDIDATE_PIN, HANDOFF_PIN, SENT_PIN, IMAGE_SIZE_PIN
CHIME_PIN, FOLLOW_UP_READ_PIN
```

## Bridge

Three methods serve this screen, and the renderer modules carry the matching names.

| Bridge method | Serves |
| ------------- | ------ |
| `market_inspector.state` | The scanner and its two tables |
| `market_inspector_tab.state` | The per-bot page in the Bot Details dialog |
| `market_inspector_topologies.state` | The proposal cards |

Each bridge method reads one object, and the two hosts build one each.

| Object | Where it is built | What it is |
| ------ | ----------------- | ---------- |
| `MarketInspectorTab` | `src/gui/market_inspector.py` | the Qt widget tree, its steppers and its clock |
| `MarketInspectorScreenModel` | `src/gui/main_tabs/market_inspector_surface.py` | the same screen as values, which the React host draws |
| `AtaSpmSettings` | both of the above | the six settings, the vault and the sign-in route |
| `SectorScan` | `src/trading/ata_spm.py` | one sector's or one market's walk and its result |
| `SignInSession` | `src/trading/ata_spm_signin.py` | one sign-in's listener, its state value and its transport |
| `ScanNowButton`, `PostChart`, `TimerTiles`, `TimerClose`, `ZONE_COUNTER` | `src/gui/web/market_inspector.js` | the page's own elements, drawn from `ata_spm_skin` |
| `PaneWidthPage` | `src/gui/market_inspector.py` | the Qt page that relays its own width to its rows |

The window relays that width on every splitter move, which is what keeps the button
row and the settings rows inside their zone.

`src/gui/market_inspector.py` — the redraws a width change and a progress run

```python
    def _size_zones(self) -> None:
    def _relay_bucket_row(self) -> None:
    def _render_ata_row(self) -> None:
    def _show_lines(self, rows: Any) -> None:
    def _show_panels(self, panels: Any) -> None:
    def _show_panel_lines(self, rows: Any) -> None:
    def _show_actions(self, actions: Any) -> None:
    def _drop_panel_box(self) -> None:
```

`src/gui/main_tabs/market_inspector_tab.py` — where the Activity Log pane is handed over

```python
    def _wire_ata_activity_log(self) -> None:
```

Each of those hides a widget before it reparents it, so no parentless widget is ever
shown and no window floats over the panel. The proposals pane builds its own detector
context, and a scan writes one sector's votes at a time.

```python
MainWindow._build_topology_proposals    the detector context
SectorBoard.load_run                    the bucket one finished run replaces
ata_spm._vote_one                       one market's vote on one timeframe
market_inspector_topologies.pane_view    the pane as values
registry._rollup                        the one calendar-bucket rollup
```

The narrative for the whole screen is on [the tabs page](../08-tabs.md). The tab
index is on [the subsystem README](README.md).
