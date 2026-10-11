"""
fidelity_connector.py — Fidelity Investments broker connector.

``FidelityConnector`` answers ``BrokerBase`` for ``VENUE_ID``, so
``MainWindow._connect_broker_for_bot`` builds it and a bot on this venue stops
falling to the crypto path. ``ORDER_ROUTE_UNPUBLISHED`` is why ``connect``
answers False and ``place_order`` raises: Fidelity publishes no order route a
program may call, for any sector. ``PUBLISHED_PRODUCTS`` carries the product
vocabulary its own pages settle, and ``asset_sector`` and ``asset_rules`` read
each record with no host contacted.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from ..exchange.base import MarketRules
from ..trading.scrumming.sizing import ORDER_TYPES_WITH_MARKET
from .broker_base import (
    AccountInfo,
    BrokerBase,
    OrderSide,
    OrderType,
    StockOrder,
    StockPosition,
    StockQuote,
    TimeInForce,
)
from .market_hours import eastern_at

logger = logging.getLogger("acervator.stocks.fidelity")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``FidelityConnector.exchange_id`` answers and the sector tables in
#: ``trading.scrumming.sizing`` are keyed by.
VENUE_ID = "fidelity"

#: Why ``connect`` opens no session and ``place_order`` composes nothing.
#: Fidelity has no API host: ``api.fidelity.com``, ``developer.fidelity.com``,
#: ``developers.fidelity.com`` and ``apis.fidelity.com`` each have no DNS
#: record, where ``www.fidelity.com`` and ``institutional.fidelity.com`` both
#: resolve. Over the 53 pages its four live hosts serve, 888,215 characters,
#: "API", "OAuth", "SDK", "endpoint", "swagger", "OpenAPI", "webhook", "FIX",
#: "programmatic", "automated trading" and "application programming" each name
#: 0, against "Fidelity" 3381 and "trading" 1159. Its own two doors are a
#: log-in: "Institutional clients can log in below to access the Fidelity
#: Digital Assets Custody and Trading Platform" and "U.S. individual investors
#: can log in and trade through their Fidelity Crypto accounts."
ORDER_ROUTE_UNPUBLISHED = (
    "Fidelity publishes no order route a program may call, on any host and for "
    "any sector, so no order body is composed and no session is opened"
)

#: The hosts this venue's readings came off, which ``connect`` contacts none of.
#: ``institutional.fidelity.com`` is the advisor site and publishes no order
#: route either: over the 9670 URLs its own contentSitemap.xml lists,
#: "integration-xchange", "integration", "developer" and "oauth" each name 0.
PRODUCT_HOSTS = (
    "www.fidelity.com",
    "www.fidelitydigitalassets.com",
    "capitalmarkets.fidelity.com",
    "institutional.fidelity.com",
)

#: The sector each product word in Fidelity's own Investment Accounts & Products
#: enumeration belongs to, read off that page on 2026-10-11. It lists the
#: products in words — "Mutual funds, Stocks, ETFs, Fixed income bonds & CDs,
#: Options, Crypto, Alternative investments, Margin trading, Precious metals,
#: International" — and four of them reach a sector this platform draws. A word
#: outside this table reaches no sector and ``order_refusal`` names it.
PRODUCT_SECTORS: dict[str, str] = {
    "crypto": "crypto",
    "equity": "stocks",
    "index_fund_share": "indices",
    "commodity_fund_share": "commodities",
    "precious_metal": "commodities",
}

#: The product words Fidelity sells that name no sector this platform draws, so
#: an order naming one is refused and never sized under another sector's rule.
#: Options, mutual funds, fixed income, annuities, IPOs and alternatives each
#: appear in the venue's own enumeration and none maps onto the six sectors.
PRODUCTS_WITHOUT_SECTOR = (
    "option",
    "mutual_fund",
    "fixed_income",
    "annuity",
    "ipo",
    "alternative",
)

#: What ``order_refusal`` says about a record whose product word is one
#: ``PRODUCTS_WITHOUT_SECTOR`` names: a product Fidelity sells that this
#: platform draws no sector for.
NO_SECTOR_PRODUCT = (
    "{word} is a product Fidelity sells and this platform draws no sector for, "
    "so no order is sized for {symbol}"
)

#: What ``order_refusal`` says about a record whose product word is in neither
#: ``PRODUCT_SECTORS`` nor ``PRODUCTS_WITHOUT_SECTOR``.
UNKNOWN_PRODUCT = (
    "{word} is no product word Fidelity's own pages name, so no order is sized "
    "for {symbol}"
)

#: What ``order_refusal`` says about a record carrying no product word at all.
NO_PRODUCT_WORD = "no product word is recorded for {symbol}, so no order is sized"

#: What ``order_refusal`` says about an order outside the window Fidelity
#: publishes for that product's own order desk.
OUTSIDE_ORDER_WINDOW = (
    "Fidelity takes a {word} order between {open:g}:00 and {close:g}:00 Eastern "
    "and the moment reads {hour:.2f}, so no order is sized for {symbol}"
)

#: The field a Fidelity product record carries its product word under, which
#: ``PRODUCT_SECTORS`` and ``PRODUCTS_WITHOUT_SECTOR`` are keyed by.
PRODUCT_FIELD = "product"

#: The five assets Fidelity Crypto lists, each named on its own pages. FIDD is
#: the Fidelity Digital Dollar, "a stablecoin pegged 1:1 to the US dollar and
#: issued by Fidelity Digital Assets as an ERC-20 token on the Ethereum
#: network", which records under crypto beside USDC and USDT and never under
#: forex.
CRYPTO_ASSETS = ("BTC", "ETH", "LTC", "SOL", "FIDD")

#: The quote leg Fidelity Crypto prices every coin against, its own ticket
#: taking a dollar amount or a coin amount.
CRYPTO_QUOTE = "USD"

#: The smallest crypto order Fidelity Crypto publishes, in quote currency:
#: "Fidelity Crypto supports trade sizes as low as $1."
CRYPTO_ORDER_USD_MIN = 1.0

#: The largest crypto order Fidelity Crypto publishes per asset, in quote
#: currency, read off its own Trading basics page: "$5,000,000 for bitcoin
#: (BTC), ethereum (ETH), and Fidelity Digital Dollar (FIDD) / $2,000,000 for
#: solana (SOL) / $1,000,000 for litecoin (LTC)".
CRYPTO_ORDER_USD_MAX: dict[str, float] = {
    "BTC": 5_000_000.0,
    "ETH": 5_000_000.0,
    "FIDD": 5_000_000.0,
    "SOL": 2_000_000.0,
    "LTC": 1_000_000.0,
}

#: The fee Fidelity Digital Assets publishes per crypto fill, as a fraction of
#: the executed market value: "Fidelity Digital Assets calculates the trading
#: fee on buy and sell transactions as 1% of the market value of executed
#: orders." Before 2025-12-04 the same 1% was carried in the price as a spread.
CRYPTO_FILL_FEE = 0.01

#: The share of available cash a crypto order may name when it names a coin
#: amount, and the share of a holding a sale may name when it names a dollar
#: amount: "you can buy crypto with up to 95% of your available cash when
#: placing buy orders in coin amounts."
CRYPTO_CASH_SHARE_MAX = 0.95

#: The decimal places a Fidelity equity or fund order may name, with the step
#: that follows: "Fractional share quantities can be entered out to 3 decimal
#: places (.001) as long as the value of the order is at least $1.00.
#: Executions will be rounded down to the nearest .001 shares."
EQUITY_QUANTITY_DECIMALS = 3
EQUITY_AMOUNT_INCREMENT = 10.0**-EQUITY_QUANTITY_DECIMALS

#: The smallest equity or fund order Fidelity publishes, in quote currency, the
#: same figure its Compare Online Brokers table gives: "For fractional share
#: trading, Fidelity's minimum transaction value is $1.00."
EQUITY_ORDER_USD_MIN = 1.0

#: The step a precious-metal order takes, from its own table: "Order quantity
#: Whole ounces, or whole numbers of coins."
METAL_AMOUNT_INCREMENT = 1.0

#: The smallest precious-metal order Fidelity publishes, in quote currency:
#: "Minimum initial investment $2,500."
METAL_ORDER_USD_MIN = 2500.0

#: The window Fidelity's own precious-metals table gives its order desk, in
#: Eastern hours: "Order hours 8:00 a.m.-3:00 p.m. ET (limited due to
#: volatility in the precious metals market)". Neither this nor the crypto
#: window is a word ``sizing.SESSIONS_DECLARED`` holds, so
#: ``CITED_VENUE_SESSIONS`` takes no row for either sector.
METAL_ORDER_HOUR_OPEN = 8.0
METAL_ORDER_HOUR_CLOSE = 15.0

#: The window Fidelity Crypto publishes: "Trading in Fidelity Crypto accounts
#: is available 23 hours a day, from 1 a.m. ET until midnight", with a
#: scheduled maintenance event keeping trading unavailable until 4 a.m. ET.
CRYPTO_ORDER_HOUR_OPEN = 1.0
CRYPTO_ORDER_HOUR_CLOSE = 24.0

#: The Eastern window each product word's own order desk publishes, which
#: ``order_window`` answers and ``order_refusal`` reads. The equity route is
#: absent because ``equity_session`` carries its three windows, and because
#: ``sizing.SESSION_US_EQUITY`` already governs its size and its order type.
PRODUCT_WINDOWS: dict[str, tuple] = {
    "crypto": (CRYPTO_ORDER_HOUR_OPEN, CRYPTO_ORDER_HOUR_CLOSE),
    "precious_metal": (METAL_ORDER_HOUR_OPEN, METAL_ORDER_HOUR_CLOSE),
}

#: The three equity windows Fidelity publishes, in Eastern hours. Its own FAQ
#: gives the two extended ones: "Orders for the premarket session can be placed
#: from 7:00 a.m. to 9:28 a.m. ET. Orders in the after-hours session can be
#: placed from 4:00 p.m. to 8:00 p.m. ET." The premarket opens three hours later
#: than ``market_hours.PRE_MARKET_OPEN``, so this venue's own boundary is read
#: and not the shared one.
EQUITY_PREMARKET_HOUR_OPEN = 7.0
EQUITY_PREMARKET_HOUR_CLOSE = 9.0 + 28.0 / 60.0
EQUITY_REGULAR_HOUR_OPEN = 9.5
EQUITY_REGULAR_HOUR_CLOSE = 16.0
EQUITY_AFTERHOURS_HOUR_CLOSE = 20.0

#: The session word ``equity_session`` answers, one per window Fidelity
#: publishes. ``SESSION_CLOSED`` is every hour outside all three.
SESSION_PREMARKET = "premarket"
SESSION_REGULAR = "regular"
SESSION_AFTER_HOURS = "after_hours"
SESSION_CLOSED = "closed"

#: The two windows Fidelity accepts a limit order and nothing else in, quoted
#: whole: "Fidelity will accept limit orders in the extended-hours trading
#: sessions; all other order types are ineligible for trading during
#: extended-hours."
SESSIONS_LIMIT_ONLY = (SESSION_PREMARKET, SESSION_AFTER_HOURS)

#: The one window a fraction may be ordered in, quoted whole: "Both
#: dollar-based and fractional share orders are only eligible for execution
#: during normal market hours."
SESSION_FRACTION_ALLOWED = SESSION_REGULAR

#: The days Fidelity takes to settle a securities sale, from its own
#: cash-account page: "most securities have a settlement date that occurs on
#: trade date plus 1 business days (T+1)."
EQUITY_SETTLEMENT_DAYS = 1.0

#: Every product record Fidelity's own pages name by symbol, which
#: ``list_assets`` answers with no host contacted. The five crypto assets and
#: the three spot crypto ETPs are named on its own crypto pages; the four metals
#: are its own precious-metals table, keyed by the metal because the venue
#: prices coins and bars per Troy ounce. No equity, index-fund or commodity-fund
#: symbol beyond the three ETPs is published: the venue gives a count, "more
#: than 7,000 US Stocks and ETFs", and names no list, so this table claims none.
PUBLISHED_PRODUCTS: tuple = (
    {"symbol": "BTC/USD", "product": "crypto", "name": "bitcoin"},
    {"symbol": "ETH/USD", "product": "crypto", "name": "ethereum"},
    {"symbol": "LTC/USD", "product": "crypto", "name": "litecoin"},
    {"symbol": "SOL/USD", "product": "crypto", "name": "solana"},
    {"symbol": "FIDD/USD", "product": "crypto", "name": "Fidelity Digital Dollar"},
    {"symbol": "FBTC", "product": "crypto", "name": "Fidelity Wise Origin Bitcoin"},
    {"symbol": "FETH", "product": "crypto", "name": "Fidelity Ethereum"},
    {"symbol": "FSOL", "product": "crypto", "name": "Fidelity Solana"},
    {"symbol": "XAU", "product": "precious_metal", "name": "gold"},
    {"symbol": "XAG", "product": "precious_metal", "name": "silver"},
    {"symbol": "XPT", "product": "precious_metal", "name": "platinum"},
    {"symbol": "XPD", "product": "precious_metal", "name": "palladium"},
)

#: The separator Fidelity Crypto's own ticket puts between a coin and its quote
#: currency, which no equity or metal symbol carries.
CRYPTO_SYMBOL_SEPARATOR = "/"


def product_word(asset: Any) -> str:
    """The ``PRODUCT_FIELD`` word one Fidelity product record carries, lowered,
    and "" for an ``asset`` that is not a record."""
    if not isinstance(asset, dict):
        return ""
    return str(asset.get(PRODUCT_FIELD) or "").strip().lower()


def crypto_symbol(symbol: Any) -> bool:
    """Whether ``symbol`` names a Fidelity Crypto coin: a
    ``CRYPTO_SYMBOL_SEPARATOR`` with a ``CRYPTO_ASSETS`` member before it and
    ``CRYPTO_QUOTE`` after it."""
    held = str(symbol or "")
    if CRYPTO_SYMBOL_SEPARATOR not in held:
        return False
    base, _, quote = held.partition(CRYPTO_SYMBOL_SEPARATOR)
    return base.strip().upper() in CRYPTO_ASSETS and (
        quote.strip().upper() == CRYPTO_QUOTE
    )


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one Fidelity product record names, and None where its own
    fields name none.

    ``venue_market_sector`` is read first and ``venue_base_sector`` second, the
    precedence ``ccxt_connector.market_asset_class`` takes, then the record's
    own ``PRODUCT_FIELD`` word through ``PRODUCT_SECTORS``.
    """
    from ..trading.scrumming.sizing import venue_base_sector, venue_market_sector

    if not isinstance(asset, dict):
        return None
    symbol = str(asset.get("symbol") or "")
    named = venue_market_sector(VENUE_ID, symbol)
    if named:
        return str(named)
    base = symbol.partition(CRYPTO_SYMBOL_SEPARATOR)[0]
    cited = venue_base_sector(VENUE_ID, base)
    if cited:
        return str(cited)
    return PRODUCT_SECTORS.get(product_word(asset))


def equity_session(moment_s: Any) -> str:
    """The window Fidelity accepts an equity order in at ``moment_s``, epoch
    seconds, read off its own three published boundaries.

    ``SESSION_CLOSED`` for every weekend, holiday and hour outside all three,
    with ``market_hours.session_at`` answering the first two.
    """
    from .market_hours import MarketSession, session_at

    if type(moment_s) not in (int, float) or not math.isfinite(float(moment_s)):
        return SESSION_CLOSED
    if session_at(float(moment_s)) in (MarketSession.WEEKEND, MarketSession.HOLIDAY):
        return SESSION_CLOSED
    eastern = eastern_at(float(moment_s))
    hour = eastern.hour + eastern.minute / 60.0 + eastern.second / 3600.0
    if EQUITY_PREMARKET_HOUR_OPEN <= hour < EQUITY_PREMARKET_HOUR_CLOSE:
        return SESSION_PREMARKET
    if EQUITY_REGULAR_HOUR_OPEN <= hour < EQUITY_REGULAR_HOUR_CLOSE:
        return SESSION_REGULAR
    if EQUITY_REGULAR_HOUR_CLOSE <= hour < EQUITY_AFTERHOURS_HOUR_CLOSE:
        return SESSION_AFTER_HOURS
    return SESSION_CLOSED


def session_takes_market_order(session: Any) -> bool:
    """Whether Fidelity accepts an order type other than a limit in ``session``.

    False for both ``SESSIONS_LIMIT_ONLY`` windows and for ``SESSION_CLOSED``,
    the venue's own rule being "all other order types are ineligible for
    trading during extended-hours".
    """
    return str(session or "") == SESSION_REGULAR


def session_takes_fraction(session: Any) -> bool:
    """Whether Fidelity accepts a fractional quantity in ``session``.

    True for ``SESSION_FRACTION_ALLOWED`` alone, so a scrum of 1.57 shares has
    no entry shape in either extended window and ``sizing.session_unit_rule``
    raises it to whole shares there.
    """
    return str(session or "") == SESSION_FRACTION_ALLOWED


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float, and None for anything else.

    A Fidelity product table writes a minimum as ``$2,500``, so the dollar sign
    and the thousands separator are dropped before the parse.
    """
    if type(value) not in (int, float, str):
        return None
    try:
        parsed = float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one Fidelity product record publishes.

    ``read`` is False for anything that is not a record, an unnamed rule is
    None, and the step and the dollar floor come from the venue's own figures
    per product: a coin amount, a three-decimal share, or a whole ounce.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    word = product_word(asset)
    if word == "precious_metal":
        return MarketRules(
            amount_increment=METAL_AMOUNT_INCREMENT,
            min_cost=METAL_ORDER_USD_MIN,
            order_types=ORDER_TYPES_WITH_MARKET,
        )
    if word == "crypto" and crypto_symbol(asset.get("symbol")):
        base = str(asset.get("symbol") or "").partition(CRYPTO_SYMBOL_SEPARATOR)[0]
        return MarketRules(
            min_cost=CRYPTO_ORDER_USD_MIN,
            order_types=ORDER_TYPES_WITH_MARKET,
            quote_increment=rule_number(CRYPTO_ORDER_USD_MAX.get(base.upper())),
        )
    return MarketRules(
        amount_increment=EQUITY_AMOUNT_INCREMENT,
        min_cost=EQUITY_ORDER_USD_MIN,
        order_types=ORDER_TYPES_WITH_MARKET,
        settlement_days=EQUITY_SETTLEMENT_DAYS,
    )


def order_window(asset: Any) -> Optional[tuple]:
    """The Eastern hours Fidelity publishes for one product record's own order
    desk, and None for a record whose window is the equity session.

    A crypto fund share takes the equity session and not the crypto ticket's 23
    hours, so ``crypto_symbol`` decides that row and ``PRODUCT_FIELD`` the rest.
    """
    word = product_word(asset)
    if word == "crypto" and not crypto_symbol(
        asset.get("symbol") if isinstance(asset, dict) else None
    ):
        return None
    return PRODUCT_WINDOWS.get(word)


def order_refusal(asset: Any, symbol: Any, moment_s: Any = None) -> str:
    """Why no order is composed for one Fidelity product record, and "" where
    the record's own product word names a sector and ``moment_s`` falls inside
    that product's published window.

    ``ORDER_ROUTE_UNPUBLISHED`` is the refusal every record takes after this
    one, so a record passing here is still never sent.
    """
    word = product_word(asset)
    if not word:
        return NO_PRODUCT_WORD.format(symbol=str(symbol))
    if word in PRODUCTS_WITHOUT_SECTOR:
        return NO_SECTOR_PRODUCT.format(word=word, symbol=str(symbol))
    if word not in PRODUCT_SECTORS:
        return UNKNOWN_PRODUCT.format(word=word, symbol=str(symbol))
    window = order_window(asset)
    if window is None or moment_s is None:
        return ""
    if type(moment_s) not in (int, float) or not math.isfinite(float(moment_s)):
        return ""
    eastern = eastern_at(float(moment_s))
    hour = eastern.hour + eastern.minute / 60.0 + eastern.second / 3600.0
    opens, closes = window
    if opens <= hour < closes:
        return ""
    return OUTSIDE_ORDER_WINDOW.format(
        word=word, open=opens, close=closes, hour=hour, symbol=str(symbol)
    )


def declared_order_types(asset: Any = None) -> str:
    """``ORDER_TYPES_WITH_MARKET`` for every Fidelity market, its own Order
    Types FAQ publishing a market order on every product it sells and its
    crypto ticket publishing the same.

    The extended-hours limit rule is a session narrowing, which
    ``sizing.session_order_types`` applies over this answer.
    """
    del asset
    return ORDER_TYPES_WITH_MARKET


class FidelityConnector(BrokerBase):
    """Fidelity Investments broker connector.

    ``SECTORS_SERVED`` is left empty so every sector takes this broker's route
    and reads ``ORDER_ROUTE_UNPUBLISHED``, and ``place_order`` raises that
    sentence in place of a body composed against unread field names.
    """

    #: Left empty on purpose, the reading the etrade unit landed. A narrowed set
    #: would send a bot on a sector outside it down the crypto path, and ccxt
    #: 4.5.85 carries no ``fidelity``, so the bot would fail with no sentence.
    #: ``asset_class_surface.EXTRA_VENUE_CLASSES`` is what narrows the screen to
    #: the four sectors this venue lists a product in.
    SECTORS_SERVED: tuple = ()

    #: Fidelity publishes no API host at all, so it publishes no paper one
    #: either and ``MainWindow._open_broker_session`` opens a live session.
    HAS_PAPER_ROUTE: bool = False

    #: Fidelity publishes no ledger route, no page size and no continuation
    #: token, so ``BrokerExchange.get_my_trades`` raises its own sentence and
    #: never reaches ``list_fills``. No walk is written at all, because a walk
    #: with no published cap reads a short page as the end of the history.
    PUBLISHES_FILL_HISTORY: bool = False

    def __init__(self):
        super().__init__(VENUE_ID)
        self._assets = [dict(one) for one in PUBLISHED_PRODUCTS]

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Answer False with ``ORDER_ROUTE_UNPUBLISHED`` in ``session_refusal``,
        contacting no host.

        ``open_session`` keeps that refusal word for word, and the operator's
        status log carries it in place of a silent failure.
        """
        del api_key, api_secret, paper
        self._session_refusal = ORDER_ROUTE_UNPUBLISHED
        logger.info("Fidelity session not opened: %s", ORDER_ROUTE_UNPUBLISHED)
        return False

    async def disconnect(self):
        """Mark this broker disconnected; ``connect`` opened no session."""
        self._connected = False

    async def get_account(self) -> AccountInfo:
        """An empty ``AccountInfo``, the answer with no session open."""
        return AccountInfo()

    async def get_positions(self) -> list[StockPosition]:
        """No ``StockPosition``, the answer with no session open."""
        return []

    async def get_position(self, symbol: str) -> Optional[StockPosition]:
        """None for every ``symbol``, the answer with no session open."""
        del symbol
        return None

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float = 0,
        stop_price: float = 0,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> StockOrder:
        """Raise ``NotImplementedError`` naming ``ORDER_ROUTE_UNPUBLISHED``.

        A body composed from field names this module never read would send an
        order shaped by a belief, and ``symbol`` reaches no venue.
        """
        del side, quantity, order_type, limit_price, stop_price, time_in_force
        raise NotImplementedError(f"{ORDER_ROUTE_UNPUBLISHED}, including {symbol}")

    async def cancel_order(self, order_id: str) -> bool:
        """False for every ``order_id``, since ``place_order`` sends none."""
        del order_id
        return False

    async def get_order(self, order_id: str) -> StockOrder:
        """An empty ``StockOrder``, since ``place_order`` sends none."""
        del order_id
        return StockOrder()

    async def get_open_orders(self) -> list[StockOrder]:
        """No ``StockOrder``, since ``place_order`` sends none."""
        return []

    async def get_quote(self, symbol: str) -> StockQuote:
        """An empty ``StockQuote`` for ``symbol``.

        Fidelity publishes no quote route, every price it serves sitting behind
        the log-in its own pages name.
        """
        return StockQuote(symbol=symbol)

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """No bar for ``symbol``, since Fidelity publishes no price-history
        route."""
        del symbol, timeframe, limit
        return []

    async def get_market_status(self) -> dict:
        """A closed market, since Fidelity publishes no market-status route."""
        return {"is_open": False, "next_open": "", "next_close": ""}

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every record ``PUBLISHED_PRODUCTS`` holds, kept for ``held_assets``
        and ``record_markets``.

        No host is contacted: these are the products Fidelity's own pages name
        by symbol, so ``record_markets`` writes a rule row and a sector per
        market with no session opened.
        """
        del status
        self._assets = [dict(one) for one in PUBLISHED_PRODUCTS]
        return list(self._assets)

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own product records
        publishes, read through ``asset_rules`` so no host is contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own product records names, read
        through ``asset_sector`` so no host is contacted."""
        return asset_sector(asset)


__all__ = [
    "CRYPTO_ASSETS",
    "CRYPTO_CASH_SHARE_MAX",
    "CRYPTO_FILL_FEE",
    "CRYPTO_ORDER_HOUR_CLOSE",
    "CRYPTO_ORDER_HOUR_OPEN",
    "CRYPTO_ORDER_USD_MAX",
    "CRYPTO_ORDER_USD_MIN",
    "CRYPTO_QUOTE",
    "CRYPTO_SYMBOL_SEPARATOR",
    "EQUITY_AFTERHOURS_HOUR_CLOSE",
    "EQUITY_AMOUNT_INCREMENT",
    "EQUITY_ORDER_USD_MIN",
    "EQUITY_PREMARKET_HOUR_CLOSE",
    "EQUITY_PREMARKET_HOUR_OPEN",
    "EQUITY_QUANTITY_DECIMALS",
    "EQUITY_REGULAR_HOUR_CLOSE",
    "EQUITY_REGULAR_HOUR_OPEN",
    "EQUITY_SETTLEMENT_DAYS",
    "METAL_AMOUNT_INCREMENT",
    "METAL_ORDER_HOUR_CLOSE",
    "METAL_ORDER_HOUR_OPEN",
    "METAL_ORDER_USD_MIN",
    "NO_PRODUCT_WORD",
    "NO_SECTOR_PRODUCT",
    "ORDER_ROUTE_UNPUBLISHED",
    "OUTSIDE_ORDER_WINDOW",
    "PRODUCTS_WITHOUT_SECTOR",
    "PRODUCT_FIELD",
    "PRODUCT_HOSTS",
    "PRODUCT_SECTORS",
    "PRODUCT_WINDOWS",
    "PUBLISHED_PRODUCTS",
    "SESSIONS_LIMIT_ONLY",
    "SESSION_AFTER_HOURS",
    "SESSION_CLOSED",
    "SESSION_FRACTION_ALLOWED",
    "SESSION_PREMARKET",
    "SESSION_REGULAR",
    "UNKNOWN_PRODUCT",
    "VENUE_ID",
    "FidelityConnector",
    "asset_rules",
    "asset_sector",
    "crypto_symbol",
    "declared_order_types",
    "equity_session",
    "order_refusal",
    "order_window",
    "product_word",
    "rule_number",
    "session_takes_fraction",
    "session_takes_market_order",
]
