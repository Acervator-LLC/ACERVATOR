"""
schwab_connector.py — Charles Schwab broker connector.

``SchwabConnector`` answers ``BrokerBase`` for ``VENUE_ID``, so
``MainWindow._connect_broker_for_bot`` builds it and ``BotContainer`` reaches it
through ``BrokerExchange``. ``FUTURES_FAMILY_SECTORS``, ``CURRENCY_LEGS`` and
``asset_sector`` carry the product vocabulary Schwab's own open pages settle,
and ``ORDER_ROUTE`` names the one order route its own API host serves.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from ..exchange.base import MarketRules
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

logger = logging.getLogger("acervator.stocks.schwab")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``SchwabConnector.exchange_id`` answers and the sector tables in
#: ``trading.scrumming.sizing`` are keyed by.
VENUE_ID = "schwab"

#: The one host Schwab's own API products answer on, and the one order route it
#: serves. Censused over 18 trader paths on 2026-10-11 with no credential sent:
#: a route that exists answers 401 and a route that does not answers 404, and
#: ``/trader/v1/futures/orders`` and ``/trader/v1/forex/orders`` both answer
#: 404. This path takes every sector's order or no path does.
API_BASE = "https://api.schwabapi.com"
ORDER_ROUTE = "/trader/v1/accounts/{account}/orders"

#: The route listing one account's own executed trades, which answers 401 with
#: no credential. ``/trader/v1/accounts/{n}/activities`` answers 404, so the
#: transaction list is the only fill ledger this venue publishes.
TRANSACTIONS_ROUTE = "/trader/v1/accounts/{account}/transactions"

#: Why ``list_fills`` answers no fill. Schwab publishes ``TRANSACTIONS_ROUTE``
#: and publishes its record's fields nowhere a credential-free reader reaches, so
#: a reader of this ledger would name fields it never read.
FILL_RECORD_UNPUBLISHED = (
    "Schwab publishes the transactions route and not its record's fields, so no "
    "fill is read"
)

#: Why ``place_order`` composes nothing. Schwab's developer portal serves one
#: JavaScript shell of 55,033 bytes for a real product page and an invented slug
#: alike, and the content behind it answers 401 at the same 83 bytes for both, so
#: the fields ``ORDER_ROUTE`` takes are published to a signed-in developer only.
ORDER_BODY_UNPUBLISHED = (
    "Schwab serves the fields its order route takes only to a signed-in "
    "developer, so no order body is composed"
)

#: The sector each family Schwab's own futures-markets table names belongs to,
#: read off that table on 2026-10-11. It lists 163 rows over 139 unique
#: contracts, and the 24 rows under Micros each repeat a row in another family,
#: so every symbol carries a family outside Micros. Interest Rates maps to no
#: sector this platform draws, so its 7 contracts record under none.
FUTURES_FAMILY_SECTORS: dict[str, str] = {
    "agriculture": "commodities",
    "crypto": "crypto",
    "currency": "forex",
    "energy": "commodities",
    "metals": "commodities",
    "single stock": "stocks",
    "softs": "commodities",
    "stock indices": "indices",
}

#: The leading character Schwab's own tables put before a futures symbol, which
#: every one of its 139 contracts carries and no equity symbol does.
FUTURES_SYMBOL_PREFIX = "/"

#: The separator Schwab's own currency table puts between a pair's two legs, as
#: in ``EUR/USD``. Each of its 70 pairs carries it and no equity symbol does.
CURRENCY_SYMBOL_SEPARATOR = "/"

#: Every currency leg Schwab's own table "Currency pairs available at Schwab"
#: names, read 2026-10-11. The table renders 11 of the 12 rows it declares and
#: lists 70 pairs over these 19 codes, against the page's own headline "Access
#: to over 65 currency pairs". A pair with a leg of this set on both sides holds
#: two currencies, which places it in the forex sector. ``NOK`` is here and is
#: also Nokia's listed equity, which ``currency_pair_symbol`` separates: the
#: venue writes the krone only as a leg of a pair and the company as a bare code.
CURRENCY_LEGS: frozenset[str] = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "ILS",
        "JPY",
        "MXN",
        "NOK",
        "NZD",
        "PLN",
        "SEK",
        "SGD",
        "USD",
        "ZAR",
    }
)

#: The sector a record naming no family and no currency pair falls to. Every
#: Schwab symbol that is neither a contract nor a pair is a listed equity or
#: fund share, which its own fractional-shares page gives as "most U.S.-listed
#: stocks and ETFs".
BARE_SYMBOL_SECTOR = "stocks"


def futures_symbol(symbol: Any) -> bool:
    """Whether ``symbol`` carries ``FUTURES_SYMBOL_PREFIX``, which every Schwab
    contract carries and no equity or currency pair does."""
    return str(symbol or "").startswith(FUTURES_SYMBOL_PREFIX)


def currency_pair_symbol(symbol: Any) -> bool:
    """Whether ``symbol`` names one of Schwab's currency pairs.

    A pair carries ``CURRENCY_SYMBOL_SEPARATOR`` with a member of
    ``CURRENCY_LEGS`` on each side, so ``futures_symbol`` and a bare equity code
    both answer False here.
    """
    held = str(symbol or "")
    if futures_symbol(held) or CURRENCY_SYMBOL_SEPARATOR not in held:
        return False
    base, _, quote = held.partition(CURRENCY_SYMBOL_SEPARATOR)
    return base.strip().upper() in CURRENCY_LEGS and (
        quote.strip().upper() in CURRENCY_LEGS
    )


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one Schwab asset record names, and None where its own fields
    name none.

    ``venue_market_sector`` is read first and ``venue_base_sector`` second, the
    precedence ``ccxt_connector.market_asset_class`` takes, then the record's own
    ``family`` through ``FUTURES_FAMILY_SECTORS``, then ``currency_pair_symbol``
    and ``BARE_SYMBOL_SECTOR``.
    """
    from ..trading.scrumming.sizing import venue_base_sector, venue_market_sector

    if not isinstance(asset, dict):
        return None
    symbol = str(asset.get("symbol") or "")
    named = venue_market_sector(VENUE_ID, symbol)
    if named:
        return str(named)
    base = symbol.lstrip(FUTURES_SYMBOL_PREFIX).partition(CURRENCY_SYMBOL_SEPARATOR)[0]
    cited = venue_base_sector(VENUE_ID, base)
    if cited:
        return str(cited)
    family = FUTURES_FAMILY_SECTORS.get(str(asset.get("family") or "").strip().lower())
    if family:
        return family
    if currency_pair_symbol(symbol):
        return "forex"
    if futures_symbol(symbol) or not symbol:
        return None
    return BARE_SYMBOL_SECTOR


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float, and None for anything else.

    A Schwab product table writes its Multiplier as ``$12,500`` and its Minimum
    Tick Size as a decimal, so the dollar sign and the thousands separator are
    dropped before the parse.
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
    """The ``MarketRules`` one Schwab asset record publishes.

    ``read`` is False for anything that is not a record, an unnamed rule is
    None, and ``contract_size`` carries the Multiplier Schwab's own futures
    table gives every one of its 139 contracts.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    return MarketRules(
        min_amount=rule_number(asset.get("min_amount")),
        amount_increment=rule_number(asset.get("amount_increment")),
        price_increment=rule_number(asset.get("tick_size")),
        contract_size=rule_number(asset.get("multiplier")),
    )


# Three firms carry Schwab's sectors, each named on its own pages: Charles
# Schwab & Co., Inc. for the equity, Charles Schwab Futures and Forex LLC for the
# 139 contracts and the 70-pair currency desk, and Charles Schwab Premier Bank,
# SSB for spot crypto. One API host serves the first two and none serves the
# third: the phrase "application programming" appears 0 times in the 118,303
# characters of the Cryptocurrency Account Agreement.
class SchwabConnector(BrokerBase):
    """Charles Schwab broker connector.

    ``SECTORS_SERVED`` names the six sectors Schwab's own product tables list a
    market in, and ``place_order`` raises ``ORDER_BODY_UNPUBLISHED`` until that
    order spec is read.
    """

    #: The six sectors Schwab's own product tables list a market in: stocks from
    #: its equity universe and 55 single-stock futures, commodities from 47
    #: contracts, indices from 14, crypto from 8, forex from 8 contracts beside
    #: 70 spot pairs, and futures_perps from all 139 contracts, every one dated
    #: and none perpetual.
    SECTORS_SERVED: tuple = (
        "crypto",
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    )

    #: Schwab's own developer portal lists 6 API products and no sandbox product
    #: among them, so ``broker_paper_route`` answers False and
    #: ``MainWindow._open_broker_session`` opens a live session.
    HAS_PAPER_ROUTE: bool = False

    #: Schwab publishes ``TRANSACTIONS_ROUTE`` and not its record's fields, so
    #: ``BrokerExchange.get_my_trades`` raises its own sentence and never reaches
    #: ``list_fills``.
    PUBLISHES_FILL_HISTORY: bool = False

    def __init__(self):
        super().__init__(VENUE_ID)
        self._auth_headers: dict[str, str] = {}
        self._base_url = API_BASE
        self._account = ""

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Hold ``api_key`` as the bearer token Schwab's API host takes, and
        answer False with ``ORDER_BODY_UNPUBLISHED`` in ``session_refusal``.

        ``open_session`` keeps that refusal word for word, and the operator's
        status log carries it.
        """
        del api_secret, paper
        self._auth_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._session_refusal = ORDER_BODY_UNPUBLISHED
        logger.info("Schwab session not opened: %s", ORDER_BODY_UNPUBLISHED)
        return False

    async def disconnect(self):
        """Drop the held token and mark this broker disconnected."""
        self._auth_headers = {}
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
        """Raise ``NotImplementedError`` naming ``ORDER_ROUTE`` and
        ``ORDER_BODY_UNPUBLISHED``.

        A body composed from field names this module never read would send an
        order shaped by a belief, and ``symbol`` reaches no venue.
        """
        del side, quantity, order_type, limit_price, stop_price, time_in_force
        raise NotImplementedError(
            f"Schwab publishes {ORDER_ROUTE} and {ORDER_BODY_UNPUBLISHED}, so "
            f"no order is sent for {symbol}"
        )

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

        Every ``/marketdata/v1/`` route on Schwab's own host answers 401 with no
        credential, and no price is read.
        """
        return StockQuote(symbol=symbol)

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """No bar for ``symbol``, since ``/marketdata/v1/pricehistory`` answers
        401 with no credential."""
        del symbol, timeframe, limit
        return []

    async def get_market_status(self) -> dict:
        """A closed market, since ``/marketdata/v1/markets`` answers 401 with no
        credential."""
        return {"is_open": False, "next_open": "", "next_close": ""}

    async def list_assets(self, status: str = "active") -> list[dict]:
        """No asset record, which ``record_markets`` reads as a session that did
        not open.

        ``/trader/v1/accounts`` and every ``/marketdata/v1/`` route answer 401
        with no credential, and an empty list keeps the rows already recorded.
        """
        del status
        self._assets = []
        return []

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own asset records publishes,
        read through ``asset_rules`` so no broker is contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own asset records names, read through
        ``asset_sector`` so no broker is contacted."""
        return asset_sector(asset)


__all__ = [
    "API_BASE",
    "BARE_SYMBOL_SECTOR",
    "CURRENCY_LEGS",
    "CURRENCY_SYMBOL_SEPARATOR",
    "FILL_RECORD_UNPUBLISHED",
    "FUTURES_FAMILY_SECTORS",
    "FUTURES_SYMBOL_PREFIX",
    "ORDER_BODY_UNPUBLISHED",
    "ORDER_ROUTE",
    "TRANSACTIONS_ROUTE",
    "VENUE_ID",
    "SchwabConnector",
    "asset_rules",
    "asset_sector",
    "currency_pair_symbol",
    "futures_symbol",
    "rule_number",
]
