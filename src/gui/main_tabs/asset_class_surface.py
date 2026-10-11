"""The asset class taxonomy the header strip group and Add Exchange share.

Both variants read this module, so the Qt strip and the React page draw one
class list, one venue map and one Add Exchange label. The class list comes
from ``src.trading.ata_spm.ASSET_CLASSES`` at call time, so a class added to
that tuple reaches the group with no edit here.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .. import design_system as ds
from ..color_alpha import rgba

ADD_PREFIX = "＋ Add"

#: The alpha the checked button tints its accent with, as Qt reads it.
CHECKED_TINT_ALPHA = 40
HOVER_TINT_ALPHA = 70

# OVERTAKEN, quoted whole:
#   "The border and padding the button skin takes off its own text room."
# True today: the most the skin takes, since a segment past the first column
# suppresses its shared left border and one past the first row its shared top.
#: The border and padding the button skin takes off its own text room.
BUTTON_TEXT_PAD = 12

#: The text size one segment draws its class name at, in both variants.
SEGMENT_FONT_PX = 10

# OVERTAKEN, quoted whole:
#   "The narrowest one class button draws at. The group's floor is this times
#   the class count, which the counters share the header top row with."
# OVERTAKEN, quoted whole:
#   "True today: the square's side is this times its widest row's segment count,
#   because the segments fill a square rather than a line."
# True today: the floor segment_width_px may not fall below, which the widest
# class name sets above that floor.
#: The narrowest one class button draws at.
BUTTON_MIN_W = 34

#: The gap between two neighbouring segments, in both variants. Zero, so one
#: line draws between neighbours and never two.
GROUP_SPACING_PX = 0

#: The segments one row holds, fixed, so a further class divides the square's
#: height and never its width.
GRID_COLUMNS = 2

#: The radius the square's four outer corners carry, in both variants. Every
#: corner inside the square is zero.
OUTER_RADIUS_PX = 3

#: The ``segment_cell`` fields every class button carries into both variants.
CELL_KEYS = (
    "row",
    "column",
    "rows",
    "columns",
    "row_holds",
    "grid_column",
    "column_span",
)

#: The venue ids that trade equities. Every consumer reads this one name.
EQUITY_VENUES = frozenset(
    {
        "alpaca",
        # ibkr is the id Interactive Brokers' own hosts and the rest of this
        # tree read: api.ibkr.com serves its OpenAPI document, EXTRA_VENUE_CLASSES
        # carries its other five sectors, and ibkr_connector.VENUE_ID keys every
        # sizing row and every gate log for the firm.
        "ibkr",
        "schwab",
        # tdameritrade names no venue that still exists, read 2026-10-11 from
        # Schwab's own and TD's own hosts: developer.tdameritrade.com has no DNS
        # record at all, www.tdameritrade.com answers only Schwab's own
        # authorization wall, and "tdameritrade" and "ameritrade" each name 0 of
        # the 1637 pages Schwab's own sitemap lists, where "futures" names 88 and
        # an invented word names 0. The id stays in this set until the row that
        # reshapes the Exchanges tab removes it.
        "tdameritrade",
        "webull",
        "tastytrade",
        "fidelity",
        "etrade",
        # interactivebrokers names the same firm as "ibkr", read 2026-10-11 from
        # the firm's own hosts: www.ibkr.com redirects to
        # www.interactivebrokers.com and serves the same 240,678 bytes, and an
        # invented host answers 000 with no DNS record. This id is read on one
        # line of src/ and reaches one sector; "ibkr" is read in two files and
        # reaches six, holds the EXTRA_VENUE_CLASSES row and keys every sizing
        # row. The id stays in this set until the row that reshapes the Exchanges
        # tab removes it, as tdameritrade above does.
        "interactivebrokers",
        # OVERTAKEN, quoted whole:
        #   "robinhood_broker.VENUE_ID. The crypto id "robinhood" is a separate
        #   venue and stays out of this set."
        # True today: one id serves both. robinhood_broker.VENUE_ID and
        # robinhood_connector.VENUE_ID are the same string, and
        # broker_serves_sector picks the route from the bot's own sector.
        "robinhood",
    }
)

#: The wing words that predate the asset class taxonomy, mapped onto it.
LEGACY_CLASS_WORDS = {"stock": "stocks", "equities": "stocks", "equity": "stocks"}

#: The classes a trading layer stands behind. A class outside this set draws
#: its state and offers no venue.
LAYERED_CLASSES = frozenset(
    {"crypto", "stocks", "commodities", "forex", "indices", "futures_perps"}
)

#: Display names. A class absent here is titled from its own key.
#: ``layer_card`` indexes ``LAYER_LABEL``, so a layered class absent here
#: refuses the React page.
CLASS_NAMES = {
    "crypto": "Crypto",
    "stocks": "Stock",
    "derivatives": "Derivatives",
    "forex": "Forex",
    "commodities": "Commodities",
    "indices": "Indices",
    "futures_perps": "Futures / Perps",
}

#: What a venue is called in each class. Equities are brokered, not exchanged.
CLASS_VENUE_NOUNS = {"stocks": "Broker"}
DEFAULT_VENUE_NOUN = "Exchange"

#: Accents, every one an existing design system token. ``futures_perps`` keeps
#: the accent ``derivatives`` carried, which no live class draws.
CLASS_ACCENTS = {
    "crypto": ds.LAYER_CRYPTO,
    "stocks": ds.LAYER_STOCK,
    "derivatives": ds.SECONDARY,
    "forex": ds.INFO,
    "commodities": ds.WARNING,
    "indices": ds.ACCENT_GOLD,
    "futures_perps": ds.SECONDARY,
}
DEFAULT_ACCENT = ds.STATUS_NEUTRAL

# OVERTAKEN, quoted whole:
#   "Venues serving a class other than the one their own id implies. Coinbase's
#   products endpoint answers 1000 EQUITY products and labels 21 futures with a
#   commodity underlying; ``derivatives`` resolves onto crypto through
#   ``RETIRED_CLASSES``."
# OVERTAKEN, quoted whole:
#   "True today: the same entry also names forex, indices and futures_perps,
#   which ``market_asset_class`` answers for 20, 6 and 168 of the venue's
#   products."
# True today: twenty venue ids carry an extra sector, not Coinbase alone.
#: Venues serving a class other than the one their own id implies. Coinbase's
#: products endpoint answers 1000 EQUITY products and labels 21 futures with a
#: commodity underlying; ``derivatives`` resolves onto crypto through
#: ``RETIRED_CLASSES``.
EXTRA_VENUE_CLASSES = {
    "coinbase": (
        "derivatives",
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    ),
    "binance": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    # Bitfinex names every non-crypto perpetual in its own announcement feed:
    # "UK Oil", "Silver", "Palladium" and "Platinum" for commodities; "GERMANY
    # 40", "SPAIN 35", "EUROPE 50", "FRANCE 40", "UK 100", "AUSTRALIA 200",
    # "HONG KONG 50", "JAPAN 225" and the two implied-volatility indices for
    # indices; and "euro/tether" with "pound/tether" for forex, whose labels
    # read "Euro" and "Pound Sterling" on the venue's own currency map. Its
    # recording answers 9 commodities, 10 indices, 4 forex and 76 futures.
    # stocks is absent: 0 of 288 markets name a single company, and the 28
    # pairs ``pub:list:pair:securities`` holds are notes and funds its own
    # pages place on the Bitfinex Securities platform, "not the Bitfinex
    # exchange".
    "bitfinex": ("commodities", "forex", "indices", "futures_perps"),
    # Bitget's own instrument record publishes four sector words — stock,
    # crypto, metal and commodity — and no index word on any of its 4603 rows.
    # Its eight index-fund tokens, RSPYUSDT and RQQQUSDT among them, each
    # publish symbolType stock, so the indices row offers the venue and its
    # recording answers no market under that sector.
    "bitget": ("stocks", "commodities", "indices", "futures_perps"),
    # Bitstamp publishes asset_class on the 20 PERPETUAL rows of its own
    # /markets/ endpoint and on none of its 251 SPOT rows: CRYPTO 13,
    # COMMODITIES 4, ETF 2, FX 1. Its own launch page names the same four
    # families in words — "FX: EUR/USD", "Equity indices: QQQ, EWY",
    # "Commodities: Gold, Silver, WTI, Brent" and a crypto list holding PAXG —
    # so ETF names an index and not a company, and the indices row carries the
    # two ETF markets. stocks stays absent: 0 of 271 markets name a single
    # company and no row publishes a stock word. A US person reaches the 251
    # spot markets through Bitstamp USA, Inc. and none of the 20 perpetuals:
    # "Derivatives trading is not available to customers in the US, Canada,
    # Japan and some other countries."
    "bitstamp": ("commodities", "forex", "indices", "futures_perps"),
    "bybit": ("futures_perps",),
    # cryptocom publishes a product_type on 983 of the 988 markets its own
    # /public/get-instruments serves, and its reference page names the whole
    # vocabulary: COMMODITIES, EQUITY_IND, CURRENCIES, DIGITAL_CURRENCIES,
    # EVENTS, EQUITY, PRE_IPO. Six words sit on a live row — DIGITAL_CURRENCIES
    # 812, EQUITY 131, EQUITY_IND 28, COMMODITIES 8, PRE_IPO 3, CURRENCIES 1 —
    # so the venue names all five sectors here beside the crypto its registry
    # gives it. Its own help page calls the families "Stocks, Commodities,
    # Equity Index ETFs and Pre-IPO", which is why EQUITY_IND reaches indices
    # and PRE_IPO reaches stocks. A US person holds an account: its own Spot
    # Trading Geo-Restrictions list names 38 locations and not the United
    # States, and its U.S. Exchange terms read "'Available Jurisdiction' means
    # all eligible U.S. jurisdictions where the Exchange is available for your
    # use, except New York." Every stocks, indices and futures_perps market and
    # eight of the fourteen commodities markets are contracts, and the venue's
    # own Derivatives Trading Geo-Restrictions list names "United States US /
    # USA", so a US account reaches the 569 spot markets alone.
    "cryptocom": (
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    ),
    "gateio": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    # Gemini's own developer navigation names four product families — Spot
    # crypto, Perpetuals, Stocks and Prediction Markets — and no index family,
    # so the indices row stays absent. Stocks stays absent because its own
    # Stocks page publishes no order interface: "Stocks are currently available
    # in the Gemini UI. API trading and developer documentation are coming
    # soon." Its own /v1/symbols/details/all serves 348 rows, 13 of them
    # product_type swap, with Pax Gold and Tether Gold on four pairs each and
    # the Australian dollar and the euro against the dollar and USDC.
    "gemini": ("commodities", "forex", "futures_perps"),
    "huobi": ("stocks",),
    # Kraken quotes 12 spot pairs whose two legs are both a national currency
    # it lists, among them ZEURZUSD, ZGBPZUSD and AUDUSD.
    "kraken": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    # KuCoin publishes its own asset categories on two hosts. Its futures host
    # serves assetClass on all 691 contracts — CRYPTO 527, STOCK 155, METAL 6,
    # COMMODITY 3 — with marketType NASDAQ on the 155 and subMarketType naming
    # the exchange: US.STOCK 134, HK.STOCK 15, KR.STOCK 5, JP.STOCK 1. Its spot
    # host serves market on all 968 symbols, and its Stocks group holds the five
    # xStock pairs. The recording answers 160 stocks, 12 commodities and 527
    # futures. forex is added for two markets, USDC-EUR and USDT-EUR, which the
    # venue groups under its own FIAT word and names "USD Coin", "Tether" and
    # "Euro". indices is added with no market: the venue publishes no index word
    # in either vocabulary, and each of its thirteen index-fund and sector-fund
    # contracts — SPY, QQQ, IWM, TQQQ, SQQQ, SOXL, SOXS, UVXY, XLE, EWJ, EWY,
    # EWZ and KORU — publishes assetClass STOCK, the reading bitget and OKX took
    # on their own index-fund tokens.
    "kucoin": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    # mexc publishes its own trade zones on both of its hosts, and the zones
    # name all six sectors. Its spot exchangeInfo carries conceptPlates on all
    # 1890 rows — Tokenized Stocks 165 markets, Precious Metals 10, Pre-IPO 2,
    # Metals 1, Crude Oil 1 — and its contract detail carries conceptPlate on
    # 1028 of 1197 — Stock 469, stockindex 66, ETF 61, Commodities 19,
    # metalsfutures 17, metals 13, Forex 8, preipo 6, OIL 4. The recording
    # answers stocks 562, indices 72, commodities 36 and forex 16 beside crypto
    # 1704 and futures_perps 697, so every one of the five extra sectors holds a
    # market and commodities and forex each hold spot markets a US account can
    # reach. The venue is not IP-blocked: every one of its public endpoints
    # answered a United States address, and its own Help Center is a JavaScript
    # shell that serves no refusal clause either way.
    "mexc": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    # OKX's own instrument record numbers five asset categories — 1 Crypto,
    # 3 Stocks, 4 Commodities, 5 Forex, 6 Bonds — and no index number exists in
    # that vocabulary. Nine index-fund tickers are listed, SPY and QQQ among
    # them, and each publishes 3, so the indices row offers the venue and its
    # recording answers no market under that sector. The venue publishes 5 on
    # none of its 2191 instruments, so forex is absent from this row.
    "okx": ("stocks", "commodities", "indices", "futures_perps"),
    # OKX US publishes the same five asset categories on its own host and
    # applies them to 1152 spot rows: 1013 Crypto, 135 Stocks, 4 Commodities,
    # none Forex and no index number in the vocabulary. Eight index-fund
    # tickers are listed, XSPY and XQQQ among them, and each publishes Stocks,
    # so the indices row offers the venue and its recording answers no market
    # under that sector. futures_perps is absent because ccxt's okxus loads
    # spot alone and OKX INC's own Terms 1.1 define a spot platform. Every one
    # of the 135 stock markets is a Unified Tokenized Stock, whose own terms
    # state the holder "is not located in, incorporated in, or current
    # resident of the United States".
    "okxus": ("stocks", "commodities", "indices"),
    # Alpaca's own AssetClass enum names ten words and four of them reach a
    # sector this screen draws: crypto, us_equity, us_index and crypto_perp.
    # "stocks" arrives from EQUITY_VENUES, so this entry carries the rest.
    # commodities is its one gold token, PAXG/USD, which priced at 4185.0 on
    # the venue's own credential-free bar route; indices is us_index, whose
    # order route is an index option over the four underliers its own Index
    # Options page names, SPX, XSP, VIX and DJX. forex is absent because none
    # of the ten words names a currency and the venue's only forex surface is
    # two Market Data rate readings, latestrates-1 and rates-1, among the 259
    # endpoints of its own reference. futures_perps is absent because
    # crypto_perp sits in the enum and in none of the 696 pages of its own
    # documentation, which is an absence this unit reported as not established
    # rather than as a refusal. Alpaca is the first venue here whose own pages
    # require a US person: "Have a legal U.S. residential address within the 50
    # states or Puerto Rico".
    "alpaca": ("crypto", "commodities", "indices"),
    "etrade": ("commodities", "indices"),
    # Interactive Brokers' own OpenAPI document and contract pages name a
    # security type per sector, and all six are already offered here: crypto
    # from CRYPTO on Paxos and zerohash, stocks from STK and FUND, commodities
    # from CMDTY, forex from CASH, indices from IND and futures_perps from FUT.
    # "stocks" arrives from EQUITY_VENUES, so this entry carries the other five
    # and no sector is added or removed.
    # The product counts are the venue's own: 20 crypto tokens on its own FAQ
    # table, "over 10,000 US-listed stocks and ETFs" across "170+ markets
    # worldwide", one spot metal named USGOLD beside its Metals, Agriculture,
    # Energy and Softs futures families, "100+ Currency Pairs On 28 Currencies",
    # and its own Equity Indices and Volatility Indices futures families. No
    # perpetual: the word names 0 of the 13 ibkr pages read, where "futures"
    # names 265.
    # One eligibility rule names states and it belongs to commodities. Quoted
    # whole from its own US Spot Gold page: "US Gold is only available to legal
    # residents of the United States. US Gold is not available to legal
    # residents of Arizona, Montana, New Hampshire, and Rhode Island." The
    # account itself refuses no US person and requires none -- "IBKR accepts
    # applications from citizens or residents of most countries except those of
    # countries prohibited by the U.S. Office of Foreign Assets Control (OFAC)"
    # -- and its crypto FAQ names 103 eligible countries including the United
    # States, Puerto Rico, Guam, American Samoa, the Northern Mariana Islands
    # and the United States Virgin Islands, with no state excluded.
    # Indices reaches an order as the index future and not as a CFD:
    # products-cfds.php answers 200 with the title "Home | Interactive Brokers
    # LLC" and names "CFD" 0 times, where its six other product pages each
    # answer their own title.
    "ibkr": ("crypto", "commodities", "forex", "indices", "futures_perps"),
    # Schwab's own futures-markets table names ten product families and gives
    # every product a symbol, a multiplier, a tick size, a settlement word and
    # its trading hours: 163 rows over 139 unique contracts, because each of the
    # 24 Micros rows repeats a row in another family. Per sector the 139 are
    # stocks 55 under Single Stock, commodities 47 under Metals, Energy,
    # Agriculture and Softs, indices 14 under Stock Indices, crypto 8 under
    # Crypto and forex 8 under Currency, with 7 under Interest Rates, a sector
    # this screen does not draw. 55 + 47 + 14 + 8 + 8 + 7 = 139. "stocks"
    # arrives from EQUITY_VENUES, so this entry carries the other five.
    # forex is added here, and it is the sector the screen was missing: beside
    # the 8 Currency contracts the venue's own table "Currency pairs available
    # at Schwab" lists 70 spot pairs over 19 currency legs, its forex page reads
    # "Access to over 65 currency pairs", and its Forex Client Agreement names
    # the firm providing them, "Charles Schwab Futures and Forex LLC", as a
    # "Forex Dealer Member" of the NFA. Nothing on this screen offered any of
    # those 78 markets.
    # Three firms carry these sectors and three eligibility rules follow. The
    # site states "This site is designed for U.S. residents"; the forex page
    # states "Forex accounts are not available to residents of Ohio or
    # Arizona"; and the Cryptocurrency Account Agreement states crypto accounts
    # "are available exclusively to residents of all 50 United States except New
    # York and Louisiana", with U.S. territories excluded as well.
    "schwab": ("crypto", "commodities", "forex", "indices", "futures_perps"),
    # tastytrade's own Available Futures Products page names nine futures
    # families and 68 product codes, and every one of the 68 answers live on its
    # own credential-free /symbols/search/ route as instrument-type "Future",
    # where two invented codes answer nothing. Per sector the 68 are commodities
    # 27 under Energy, Metals, Agriculture and Livestock, indices 14 under Equity
    # Index and Volatility, forex 11 under Foreign Currency, crypto 5 under
    # Cryptocurrency, and 11 under Interest Rate, a family naming no sector this
    # screen draws, which leaves each of those 11 recording under futures_perps
    # alone. 27 + 14 + 11 + 5 + 11 = 68. Crypto also holds 26 spot coins its own
    # Available Cryptocurrencies page names, all 26 live. "stocks" arrives from
    # EQUITY_VENUES, so this entry carries the other five.
    # forex is added here, and it is the sector the screen was missing: beside
    # the 11 Foreign Currency contracts the venue's own data names a
    # "Currency Pair" instrument type, and SGD/JPY, EUR/USD, USD/JPY, GBP/USD,
    # USD/NOK and EUR/GBP all read it. Spot forex is a different firm and takes
    # no order here -- "Forex trading offered by tastyfx LLC... tastytrade and
    # tastyfx are separate legal entities" -- and "Currency Pair" sits in the
    # 14-word condition enum and in none of the 8 words the order route's own leg
    # enum holds, while 0 of its 84 published paths names a currency pair. The
    # sector's order is the currency future.
    # Indices reaches an order the same way: "Index" is in the condition enum and
    # not the leg enum, 0 of the 84 paths names an index, and its own
    # Instruments & Symbology page lists five tradeable kinds -- "an equity,
    # equity option, future, future option, or cryptocurrency" -- with neither
    # among them. SPX, VIX, NDX, RUT, XSP and DJX all answer instrument-type
    # "Index", and GLD answers "Equity" with etf true, so a fund share is an
    # order leg and an index is not.
    # No eligibility rule names a state. Quoted whole from its own International
    # Accounts page: "International customers are welcome to open individual
    # margin, individual cash, and joint accounts with tastytrade." Two
    # permissions are per product: futures needs "The Works", and
    # "Cryptocurrency trading is currently available exclusively for individual
    # accounts".
    "tastytrade": ("crypto", "commodities", "forex", "indices", "futures_perps"),
    "webull": ("crypto", "commodities", "indices", "futures_perps"),
    # One equity route, four sectors: each of these trades as a fund share, and
    # robinhood_broker.SECTORS_SERVED names the same four. "stocks" arrives from
    # EQUITY_VENUES and "crypto" from CRYPTO_CONNECTORS, so this one id reads
    # under all five sectors.
    "robinhood": ("commodities", "indices", "forex"),
}

#: The two articles a sentence takes before a sector name, and the first
#: letters taking the second.
#: The last recording read, under its ``recording_stamp``. One Live tab refresh
#: asks ``venue_classes`` once a bot, and the file is 235 KB.
_RECORDED_CACHE: dict = {}

ARTICLE_DEFAULT = "a"
ARTICLE_VOWEL = "an"
ARTICLE_VOWEL_LETTERS = "aeio"

NO_VENUE_NOTE = "No configured venue serves {name} yet."
NO_LAYER_NOTE = "{name} has no trading layer yet."
SERVED_NOTE = "{count} venue(s) serve {name}."
EMPTY_LABEL = "{name} — no venue yet"
EMPTY_TOOLTIP = "{note} Nothing is added for this class."
ADD_TOOLTIP = "Add {article} {name} {noun_lower} connection"


def asset_classes() -> tuple:
    """Every asset class the taxonomy declares, read at call time.

    ``src.trading.ata_spm.ASSET_CLASSES`` owns the tuple.
    """
    from src.trading.ata_spm import ASSET_CLASSES

    return tuple(ASSET_CLASSES)


# OVERTAKEN, quoted whole:
#   "``columns`` is the integer square root rounded up, so the grid is the one
#   nearest to square for that count."
# True today: ``columns`` is ``GRID_COLUMNS``, or ``count`` while that is
# smaller, and the rows follow, so a further class divides only the height.
def grid_shape(count: Any = None) -> tuple:
    """The rows and columns ``count`` segments divide the square into.

    ``columns`` is the integer square root rounded up, so the grid is the one
    nearest to square for that count, and a ``count`` of None reads the live
    class list.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return (0, 0)
    columns = min(GRID_COLUMNS, held)
    rows = math.ceil(held / columns)
    return (rows, columns)


def row_holds(count: Any = None) -> list:
    """How many segments each row of the square holds, the top row first.

    Every row but the last holds a full ``columns`` and the last holds what
    is left, so no row is empty.
    """
    held = len(asset_classes()) if count is None else int(count)
    rows, columns = grid_shape(held)
    if rows <= 0:
        return []
    counts = [columns] * (rows - 1)
    counts.append(held - columns * (rows - 1))
    return counts


def column_spans(columns: Any, holds: Any) -> list:
    """The grid columns each segment of one row spans, the leftmost first.

    ``holds`` segments share ``columns`` columns and the leftmost take the
    remainder one extra each, so every row fills the square's whole width.
    """
    wide = int(columns)
    many = int(holds)
    if many <= 0 or wide <= 0:
        return []
    base, extra = divmod(wide, many)
    return [base + (1 if at < extra else 0) for at in range(many)]


def segment_cell(at: Any, count: Any = None) -> dict:
    """Where segment ``at`` of ``count`` sits in the square, and what it spans.

    Carries the row, the column within that row, the grid column it starts at
    and the columns it spans, so a segment knows its place in two dimensions.
    """
    held = len(asset_classes()) if count is None else int(count)
    rows, columns = grid_shape(held)
    counts = row_holds(held)
    index = max(int(at), 0)
    row = 0
    before = 0
    for holds in counts:
        if index < before + holds:
            break
        before += holds
        row += 1
    if row >= len(counts):
        row = max(len(counts) - 1, 0)
        before = sum(counts[:row])
    holds = counts[row] if counts else 0
    column = index - before
    spans = column_spans(columns, holds)
    return {
        "row": row,
        "column": column,
        "rows": rows,
        "columns": columns,
        "row_holds": holds,
        "grid_column": sum(spans[:column]) if spans else 0,
        "column_span": spans[column] if spans and column < len(spans) else 1,
    }


def segment_font() -> Any:
    """The font one segment draws its class name in, at ``SEGMENT_FONT_PX``."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    running = QApplication.instance() is not None
    font = QFont(QApplication.font()) if running else QFont()
    font.setPixelSize(SEGMENT_FONT_PX)
    font.setBold(True)
    return font


def label_width_px(text: Any) -> int:
    """The room one class name takes at ``segment_font``, or 0 with no toolkit.

    ``QFontMetrics`` needs a running ``QApplication``, so a caller holding
    none reads 0 and ``segment_width_px`` answers ``BUTTON_MIN_W``.
    """
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        return 0
    from PySide6.QtGui import QFontMetrics

    return int(QFontMetrics(segment_font()).horizontalAdvance(str(text)))


def widest_label_px(labels: Any = None) -> int:
    """The widest declared class name's room at ``segment_font``."""
    names = (
        [display_name(each) for each in asset_classes()]
        if labels is None
        else [str(each) for each in labels]
    )
    return max((label_width_px(each) for each in names), default=0)


def reference_labels() -> list:
    """The class names ``group_side_px`` measures the square's side from.

    The first ``GRID_COLUMNS`` squared classes fill the square once, so a
    class past them divides the height and leaves the side alone.
    """
    held = asset_classes()[: GRID_COLUMNS * GRID_COLUMNS]
    return [display_name(each) for each in held]


def segment_width_px(labels: Any = None) -> int:
    """One segment's width: its widest class name plus ``BUTTON_TEXT_PAD``.

    ``BUTTON_MIN_W`` is the floor the measured width may not fall below, so a
    shorter class list never narrows a segment past it.
    """
    return max(BUTTON_MIN_W, widest_label_px(labels) + BUTTON_TEXT_PAD)


# OVERTAKEN, quoted whole:
#   "Its widest row holds ``columns`` segments of ``BUTTON_MIN_W`` each, so the
#   side follows the class count and no variant measures its own row height."
# True today: its widest row holds ``columns`` segments of ``segment_width_px``
# each, so the side follows the class count and the widest class name.
# OVERTAKEN, quoted whole:
#   "True today: its widest row holds ``columns`` segments of
#   ``segment_width_px`` each, so the side follows the class count and the
#   widest class name."
# True today: the side holds ``GRID_COLUMNS`` segments of ``reference_labels``
# room, so neither the class count nor a later class name moves it.
def group_side_px(count: Any = None, labels: Any = None) -> int:
    """The square's side in pixels, the same number in both variants.

    Its widest row holds ``columns`` segments of ``BUTTON_MIN_W`` each, so the
    side follows the class count and no variant measures its own row height.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return 0
    names = reference_labels() if labels is None else labels
    width = segment_width_px(names)
    return GRID_COLUMNS * width + (GRID_COLUMNS - 1) * GROUP_SPACING_PX


def segment_size_px(count: Any = None) -> tuple:
    """One segment's width and height in pixels, the same in both variants.

    The square's side divides by its columns and by its rows, so every one of
    ``count`` segments draws the same rectangle.
    """
    rows, columns = grid_shape(count)
    if rows <= 0 or columns <= 0:
        return (0, 0)
    side = group_side_px(count)
    width = (side - (columns - 1) * GROUP_SPACING_PX) // columns
    height = (side - (rows - 1) * GROUP_SPACING_PX) // rows
    return (width, height)


def grid_margins_px(count: Any = None) -> tuple:
    """The square's left, top, right and bottom margins, in that order.

    They carry what ``segment_size_px`` leaves of the side after an uneven
    division, so the segments stay equal and the side stays whole.
    """
    rows, columns = grid_shape(count)
    if rows <= 0 or columns <= 0:
        return (0, 0, 0, 0)
    width, height = segment_size_px(count)
    side = group_side_px(count)
    spare_w = side - columns * width - (columns - 1) * GROUP_SPACING_PX
    spare_h = side - rows * height - (rows - 1) * GROUP_SPACING_PX
    return (spare_w // 2, spare_h // 2, spare_w - spare_w // 2, spare_h - spare_h // 2)


def normalise(name: Any) -> str:
    """The declared asset class *name* names, or the first declared class.

    ``LEGACY_CLASS_WORDS`` resolves a stored ``"stock"`` onto ``"stocks"``,
    and ``ata_spm.RETIRED_CLASSES`` resolves a retired name onto the live
    class now holding its markets.
    """
    from src.trading.ata_spm import RETIRED_CLASSES

    classes = asset_classes()
    asked = str(name or "").strip().lower()
    asked = LEGACY_CLASS_WORDS.get(asked, asked)
    asked = RETIRED_CLASSES.get(asked, asked)
    if asked in classes:
        return asked
    return classes[0] if classes else ""


def display_name(name: Any) -> str:
    """The name a button and a label carry for one asset class."""
    key = normalise(name)
    return CLASS_NAMES.get(key, key.replace("_", " ").title())


def article(label: Any) -> str:
    """The article a sentence takes before one display name.

    Answers ``ARTICLE_VOWEL`` while the name opens on a letter in
    ``ARTICLE_VOWEL_LETTERS``, so the Indices layer reads "an Indices".
    """
    first = str(label or "").strip()[:1].lower()
    return ARTICLE_VOWEL if first in ARTICLE_VOWEL_LETTERS else ARTICLE_DEFAULT


def venue_noun(name: Any) -> str:
    """What one asset class calls a venue."""
    return CLASS_VENUE_NOUNS.get(normalise(name), DEFAULT_VENUE_NOUN)


def accent(name: Any) -> str:
    """The design system colour one asset class paints with."""
    return CLASS_ACCENTS.get(normalise(name), DEFAULT_ACCENT)


def ccxt_crypto_venues() -> frozenset:
    """Every venue id ``SUPPORTED_EXCHANGES`` lists, or none while it is absent."""
    try:
        from src.exchange.ccxt_connector import SUPPORTED_EXCHANGES
    except Exception:  # noqa: BLE001 - the connector is optional at import time
        return frozenset()
    return frozenset(SUPPORTED_EXCHANGES)


def written_crypto_venues() -> frozenset:
    """Every venue id ``CRYPTO_CONNECTORS`` holds a hand-written class for, or
    none while that connector is absent."""
    try:
        from src.exchange.robinhood_connector import hand_written_crypto_venues
    except Exception:  # noqa: BLE001 - the connector is optional at import time
        return frozenset()
    return frozenset(hand_written_crypto_venues())


def crypto_venues() -> frozenset:
    """Every venue id either crypto connector registry lists.

    ccxt carries no entry for a hand-written venue, so ``ccxt_crypto_venues``
    alone would list it under no sector.
    """
    return ccxt_crypto_venues() | written_crypto_venues()


def retired_onto(name: Any) -> str:
    """The live class one retired or legacy class name resolves onto.

    A name neither ``LEGACY_CLASS_WORDS`` nor ``RETIRED_CLASSES`` holds is
    answered unchanged, which ``asset_classes`` then drops.
    """
    from src.trading.ata_spm import RETIRED_CLASSES

    asked = str(name or "").strip().lower()
    asked = LEGACY_CLASS_WORDS.get(asked, asked)
    return RETIRED_CLASSES.get(asked, asked)


def recording_stamp() -> tuple:
    """The recording file's path, modification time and size, or an empty tuple
    while no file is there.

    ``recorded_venue_classes`` reads the recording again only when this moves.
    """
    try:
        from ...exchange.market_rules_store import store_path
    except ImportError:
        return ()
    try:
        target = store_path()
        held = target.stat()
    except OSError:
        return ()
    return (str(target), held.st_mtime_ns, held.st_size)


def recorded_venue_classes(document: Any = None) -> dict:
    """Every venue in the ``market_rules_store`` recording mapped to the asset
    classes its recorded rows carry under ``CLASS_FIELD``.

    ``document`` stands in for ``load_document`` and skips the
    ``recording_stamp`` cache, and neither asks a venue.
    """
    try:
        from ...exchange.market_rules_store import CLASS_FIELD, load_document
    except ImportError:
        return {}
    stamp = () if isinstance(document, dict) else recording_stamp()
    if stamp and _RECORDED_CACHE.get("stamp") == stamp:
        return dict(_RECORDED_CACHE["classes"])
    body = document if isinstance(document, dict) else load_document()
    declared = set(asset_classes())
    found: dict = {}
    for venue, rows in body.items():
        if not isinstance(rows, dict):
            continue
        held = set()
        for row in rows.values():
            if not isinstance(row, dict):
                continue
            named = retired_onto(row.get(CLASS_FIELD, ""))
            if named in declared:
                held.add(named)
        found[str(venue).strip().lower()] = frozenset(held)
    if stamp:
        _RECORDED_CACHE["stamp"] = stamp
        _RECORDED_CACHE["classes"] = dict(found)
    return found


def venue_classes(venue_id: Any, recorded: Any = None) -> frozenset:
    """Every asset class one venue could serve: the class its own registry
    lists it under, every class ``EXTRA_VENUE_CLASSES`` adds through
    ``retired_onto``, and every class its recorded rows carry.

    ``recorded`` stands in for ``recorded_venue_classes``, so one read of the
    recording serves a whole panel.
    """
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return frozenset()
    found = {retired_onto(one) for one in EXTRA_VENUE_CLASSES.get(asked, ())}
    if asked in EQUITY_VENUES:
        found.add("stocks")
    if asked in crypto_venues():
        found.add("crypto")
    held = recorded if isinstance(recorded, dict) else recorded_venue_classes()
    found |= set(held.get(asked, frozenset()))
    return frozenset(found & set(asset_classes()))


def venue_served_classes(venue_id: Any, document: Any = None) -> frozenset:
    """Every asset class one venue's recorded rows carry, the recording alone
    and no registry.

    A venue ``recorded_venue_classes`` holds no rows for answers empty, while
    ``venue_classes`` still answers what that venue could serve.
    """
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return frozenset()
    return frozenset(recorded_venue_classes(document).get(asked, frozenset()))


def recorded_symbol_classes(venue_id: Any) -> dict:
    """Every symbol one venue's recording holds mapped to its ``CLASS_FIELD``,
    empty while the recording cannot be read."""
    try:
        from ...exchange.market_rules_store import recorded_classes
    except ImportError:
        return {}
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return {}
    return recorded_classes(asked)


def symbol_class(venue_id: Any, symbol: Any, recorded: Any = None) -> str:
    """The class ``recorded_symbol_classes`` holds for ``symbol`` on
    ``venue_id``, else ``CLASS_CRYPTO``, the class ``BotContainer._asset_class``
    answers for a symbol the recording holds none for.

    Every surface narrowing a market by sector reads this, so a bot and the tab
    filtering it answer one class.
    """
    from src.trading.ata_spm import CLASS_CRYPTO

    held = recorded if isinstance(recorded, dict) else recorded_symbol_classes(venue_id)
    named = str(held.get(str(symbol or ""), "") or "")
    if not named:
        return CLASS_CRYPTO
    return retired_onto(named)


def markets_of_class(rows: Any, venue_id: Any, name: Any, recorded: Any = None) -> list:
    """Every market row of ``rows`` whose ``symbol_class`` on ``venue_id`` is
    one asset class, in the order given.

    OVERTAKEN, quoted whole: "An empty ``name`` narrows nothing." True today:
    ``normalise`` answers the first declared class for a name it does not
    recognise and never answers an empty string, so an empty ``name`` narrows
    to crypto and the guard below is unreachable.
    """
    key = normalise(name)
    listed = [one for one in (rows or []) if isinstance(one, dict)]
    if not key:
        return listed
    held = recorded if isinstance(recorded, dict) else recorded_symbol_classes(venue_id)
    return [
        row for row in listed if symbol_class(venue_id, row.get("symbol"), held) == key
    ]


def known_venues(recorded: Any = None) -> frozenset:
    """Every venue id the platform holds: ``crypto_venues``, ``EQUITY_VENUES``,
    every venue ``EXTRA_VENUE_CLASSES`` adds a sector for, and every venue
    ``recorded_venue_classes`` holds rows for, with ``recorded`` standing in for
    that read.

    ``venues_for_class`` narrows this by sector and ``init_wizard_surface``'s
    ``exchange_ids`` offers it whole, so neither list can hold a venue the other
    does not.
    """
    held = recorded if isinstance(recorded, dict) else recorded_venue_classes()
    return frozenset(
        set(crypto_venues()) | set(EQUITY_VENUES) | set(EXTRA_VENUE_CLASSES) | set(held)
    )


def venues_for_class(name: Any) -> frozenset:
    """Every venue id serving one asset class, a venue whose ``venue_classes``
    holds two classes answered for both.

    A venue ``recorded_venue_classes`` alone knows is answered for the classes
    its recorded rows carry.
    """
    key = normalise(name)
    recorded = recorded_venue_classes()
    return frozenset(
        vid for vid in known_venues(recorded) if key in venue_classes(vid, recorded)
    )


def serves(venue_id: Any, name: Any) -> bool:
    """Whether one venue serves one asset class."""
    return normalise(name) in venue_classes(venue_id)


def has_layer(name: Any) -> bool:
    """Whether a trading layer stands behind one asset class."""
    return normalise(name) in LAYERED_CLASSES


def layered_classes() -> tuple:
    """Every declared class a trading layer stands behind, in taxonomy order."""
    return tuple(name for name in asset_classes() if name in LAYERED_CLASSES)


def layer_page(name: Any) -> int:
    """The trading stack page one asset class draws.

    A layered class takes its position in ``layered_classes``, and every
    class without a layer draws the one page after them.
    """
    layered = layered_classes()
    key = normalise(name)
    return layered.index(key) if key in layered else len(layered)


def stack_pages() -> int:
    """How many pages the trading stack holds: one a layer, and one note page."""
    return len(layered_classes()) + 1


def class_state(name: Any) -> dict:
    """What one asset class holds, and the note it draws.

    A class ``venues_for_class`` answers empty carries ``NO_VENUE_NOTE``.
    """
    key = normalise(name)
    shown = display_name(key)
    venues = sorted(venues_for_class(key))
    layered = has_layer(key)
    if not venues:
        note = NO_VENUE_NOTE.format(name=shown)
    elif not layered:
        note = NO_LAYER_NOTE.format(name=shown)
    else:
        note = SERVED_NOTE.format(count=len(venues), name=shown)
    return {
        "class": key,
        "name": shown,
        "venues": venues,
        "venue_count": len(venues),
        "layer": layered,
        "served": bool(venues),
        "note": note,
        "accent": accent(key),
        "noun": venue_noun(key),
    }


def add_exchange_label(name: Any) -> str:
    """The Add Exchange button's text for one asset class.

    A class ``class_state`` reports unserved carries ``EMPTY_LABEL``.
    """
    state = class_state(name)
    if not state["served"]:
        return EMPTY_LABEL.format(name=state["name"])
    return f"{ADD_PREFIX} {state['name']} {state['noun']}"


def add_exchange_tooltip(name: Any) -> str:
    """The Add Exchange button's tooltip for one asset class."""
    state = class_state(name)
    if not state["served"]:
        return EMPTY_TOOLTIP.format(note=state["note"])
    return ADD_TOOLTIP.format(
        article=article(state["name"]),
        name=state["name"],
        noun_lower=state["noun"].lower(),
    )


def add_exchange_enabled(name: Any) -> bool:
    """Whether Add Exchange can act for one asset class."""
    return class_state(name)["served"]


def segment_box(cell: Any = None) -> str:
    """The border and radius declarations one segment carries at ``cell``.

    A segment past the first column drops its shared left border and one past
    the first row its shared top, and only a corner of the square is rounded.
    """
    place = cell if isinstance(cell, dict) else segment_cell(0, 1)
    row = int(place.get("row", 0))
    column = int(place.get("column", 0))
    rows = int(place.get("rows", 1))
    holds = int(place.get("row_holds", 1))
    corner = f"{OUTER_RADIUS_PX}px"
    said = [f"border: 1px solid {ds.OUTLINE}"]
    if column > 0:
        said.append("border-left: none")
    if row > 0:
        said.append("border-top: none")
    said.append("border-radius: 0px")
    last_row = rows - 1
    last_column = holds - 1
    top = row == 0
    bottom = row == last_row
    left = column == 0
    right = column == last_column
    if top and left:
        said.append(f"border-top-left-radius: {corner}")
    if top and right:
        said.append(f"border-top-right-radius: {corner}")
    if bottom and left:
        said.append(f"border-bottom-left-radius: {corner}")
    if bottom and right:
        said.append(f"border-bottom-right-radius: {corner}")
    return "; ".join(said) + "; "


# OVERTAKEN, quoted whole:
#   "The segmented group's skin for one accent colour."
# True today: the skin for one accent colour at one segment_cell.
def button_style(colour: Any, cell: Any = None) -> str:
    """The segmented group's skin for one accent colour."""
    tint = str(colour)
    return (
        "QPushButton { background: transparent; "
        f"color: {ds.TEXT_LOW}; {segment_box(cell)}"
        f"font-weight: bold; font-size: {SEGMENT_FONT_PX}px; "
        "padding: 2px 4px; }"
        f"QPushButton:hover {{ color: {tint}; border-color: {tint}; "
        f"background: {rgba(tint, HOVER_TINT_ALPHA)}; }}"
        f"QPushButton:checked {{ color: {tint}; border-color: {tint}; "
        f"background: {rgba(tint, CHECKED_TINT_ALPHA)}; }}"
        f"QPushButton:disabled {{ color: {ds.TEXT_PLACEHOLDER}; "
        f"border-color: {ds.OUTLINE}; }}"
    )


def class_button(name: Any, active: Any = None, cell: Any = None) -> dict:
    """One segmented group button, as both variants render it.

    The ``cell`` fields travel in the button, so both variants place the
    segment in the same grid row and column without recomputing it.
    """
    state = class_state(name)
    place = cell if isinstance(cell, dict) else segment_cell(0, 1)
    state["text"] = state["name"]
    state["checked"] = state["class"] == normalise(active) if active else False
    state["tooltip"] = state["note"]
    state.update(
        {key: place[key] for key in CELL_KEYS if key in place},
    )
    state["style_sheet"] = button_style(state["accent"], place)
    return state


def class_buttons(active: Any = None) -> list:
    """The whole segmented group, one button per declared asset class.

    Each button carries the ``segment_cell`` its index names, so the four
    segments at the square's corners round one corner each and no other does.
    """
    held = asset_classes()
    return [
        class_button(name, active, segment_cell(at, len(held)))
        for at, name in enumerate(held)
    ]


def window_title(name: Any) -> str:
    """The main window's title while one asset class is active."""
    return f"Acervator — {display_name(name).upper()} LAYER"


def selection_log(name: Any) -> str:
    """The line the status log carries when the active class changes."""
    state = class_state(name)
    return f"→ {state['name'].upper()} LAYER: {state['note']}"


def view_model(active: Any = None, stored: Optional[Any] = None) -> dict:
    """The whole group state as one serialisable dict, for the React page."""
    key = normalise(active if active is not None else stored)
    return {
        "active": key,
        "classes": list(asset_classes()),
        "buttons": class_buttons(key),
        "add_exchange": {
            "label": add_exchange_label(key),
            "tooltip": add_exchange_tooltip(key),
            "enabled": add_exchange_enabled(key),
        },
        "state": class_state(key),
    }
