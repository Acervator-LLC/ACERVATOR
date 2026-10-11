"""
alpaca_connector.py — Alpaca Markets broker connector.

Alpaca provides commission-free stock trading with a robust API.
Supports paper trading for testing. REST + WebSocket.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..exchange.base import MarketRules
from .ibkr_connector import VENUE_ID as IBKR_VENUE_ID
from .ibkr_connector import IbkrConnector
from .robinhood_broker import VENUE_ID as ROBINHOOD_VENUE_ID
from .robinhood_broker import RobinhoodMcpBroker
from .schwab_connector import VENUE_ID as SCHWAB_VENUE_ID
from .schwab_connector import SchwabConnector
from .broker_base import (
    BrokerBase,
    AccountInfo,
    StockPosition,
    StockOrder,
    StockQuote,
    OrderType,
    OrderSide,
    TimeInForce,
    PositionSide,
)

logger = logging.getLogger("acervator.stocks.alpaca")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``AlpacaConnector.exchange_id`` answers and the two sector tables in
#: ``trading.scrumming.sizing`` are keyed by.
VENUE_ID = "alpaca"

# Alpaca API endpoints
PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"

# Supported brokers registry
SUPPORTED_BROKERS = {
    VENUE_ID: {
        "name": "Alpaca Markets",
        "paper_trading": True,
        "commission_free": True,
        "fractional_shares": True,
        "crypto_available": True,
        "api_docs": "https://docs.alpaca.markets/",
    },
    "tradingview_webhook": {
        "name": "TradingView Webhook",
        "paper_trading": False,
        "commission_free": False,
        "fractional_shares": False,
        "crypto_available": False,
        "api_docs": "Receives alerts from TradingView webhooks",
    },
}

#: The size a market trades in where its asset record reads ``fractionable``
#: False: one whole share, and no smaller amount the broker accepts.
WHOLE_SHARE_INCREMENT = 1.0

#: The sector each word of Alpaca's own ``AssetClass`` enum names, read off the
#: spec its ``/v2/assets`` reference page carries. The enum holds ten words:
#: ``us_equity``, ``us_option``, ``crypto``, ``crypto_perp``, ``treasury``,
#: ``corporate``, ``global_equity``, ``us_index``, ``us_equity_chain`` and
#: ``ipo``. Six are mapped here and four are not. ``us_option`` names a sector
#: the platform does not draw and its contracts are listed by a route of their
#: own; ``treasury`` and ``corporate`` are bonds, which is no sector here; and
#: ``us_equity_chain`` names an equity's option chain rather than a market.
#: ``PAXG`` is the one base code whose class word is wrong for its sector, and
#: ``sizing.CITED_VENUE_BASE_SECTORS`` carries it.
ASSET_CLASS_SECTORS: dict[str, str] = {
    "crypto": "crypto",
    "crypto_perp": "futures_perps",
    "global_equity": "stocks",
    "ipo": "stocks",
    "us_equity": "stocks",
    "us_index": "indices",
}

#: The separator Alpaca's own symbology puts between a crypto pair's two legs.
#: Its crypto reference states the pair "BTC/USD was previously referred to as
#: BTCUSD", and an equity symbol carries no separator at all.
CRYPTO_SYMBOL_SEPARATOR = "/"

#: The times in force Alpaca publishes for a crypto market. Its own order spec
#: reads "Crypto trading: gtc, ioc", its Crypto Spot Trading page reads "the
#: supported ``time_in_force`` values are ``gtc``, and ``ioc``", and
#: ``TimeInForce.DAY`` is in neither, so a market order composed with the day
#: default would carry a value the venue does not take.
CRYPTO_TIMES_IN_FORCE = (TimeInForce.GTC, TimeInForce.IOC)

#: The time in force a crypto market order takes in place of an unpublished one,
#: the first of ``CRYPTO_TIMES_IN_FORCE``.
CRYPTO_DEFAULT_TIME_IN_FORCE = TimeInForce.GTC

#: The activity type Alpaca's account-activities route lists one filled trade
#: under, first of the 42 words its own ``ActivityType`` enum holds.
FILL_ACTIVITY_TYPE = "FILL"

#: The largest ``page_size`` Alpaca's account-activities route accepts, which
#: its own reference gives as a maximum of 100 and a default of 100.
FILL_PAGE_SIZE_MAX = 100

#: Pages ``list_fills`` walks before it stops and logs a truncation. The route
#: takes no symbol, so one market's fills are found by reading the whole
#: account's activity, and this bounds that walk at 2000 records.
FILL_PAGES_MAX = 20


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float where the asset record published a
    number or a decimal string, else None.

    Alpaca writes ``min_order_size``, ``min_trade_increment`` and
    ``price_increment`` as decimal strings, so a string is a published rule.
    """
    if type(value) not in (int, float, str):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


def size_increment(asset: dict) -> Optional[float]:
    """The size step one asset record publishes: ``min_trade_increment`` where it
    names one, ``WHOLE_SHARE_INCREMENT`` where ``fractionable`` reads False, and
    None where the record published neither.

    ``fractionable`` carries only a bool, so any other value is a record this
    reader does not recognise and publishes no step.
    """
    published = rule_number(asset.get("min_trade_increment"))
    if published is not None:
        return published
    if asset.get("fractionable") is False:
        return WHOLE_SHARE_INCREMENT
    return None


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one Alpaca asset record names, and None where its own class
    word names none.

    ``CITED_VENUE_MARKET_SECTORS`` is read first and ``CITED_VENUE_BASE_SECTORS``
    second, the precedence ``ccxt_connector.market_asset_class`` already takes,
    so one table governs a broker market and a library market alike.
    """
    from ..trading.scrumming.sizing import venue_base_sector, venue_market_sector

    if not isinstance(asset, dict):
        return None
    symbol = str(asset.get("symbol") or "")
    named = venue_market_sector(VENUE_ID, symbol)
    if named:
        return str(named)
    base, _, _ = symbol.partition(CRYPTO_SYMBOL_SEPARATOR)
    cited = venue_base_sector(VENUE_ID, base)
    if cited:
        return str(cited)
    return ASSET_CLASS_SECTORS.get(str(asset.get("class") or "").strip().lower())


def crypto_symbol(symbol: Any) -> bool:
    """Whether ``symbol`` names a crypto pair rather than an equity.

    Alpaca spells a crypto pair with ``CRYPTO_SYMBOL_SEPARATOR`` and an equity
    with no separator, so the symbol alone names which order rules apply.
    """
    return CRYPTO_SYMBOL_SEPARATOR in str(symbol or "")


def published_time_in_force(symbol: Any, time_in_force: Any) -> Any:
    """The time in force Alpaca publishes for ``symbol``: ``time_in_force``
    where the venue takes it, and ``CRYPTO_DEFAULT_TIME_IN_FORCE`` where a
    crypto pair does not.

    ``place_order`` calls this before composing the body, so a market order
    carrying the equity default reaches a crypto market under a value the
    venue's own order spec names.
    """
    if not crypto_symbol(symbol):
        return time_in_force
    if time_in_force in CRYPTO_TIMES_IN_FORCE:
        return time_in_force
    return CRYPTO_DEFAULT_TIME_IN_FORCE


def activity_moment(moment_ms: Any) -> str:
    """``moment_ms`` as the UTC date-time Alpaca's activity route takes, and ""
    where it is no finite number.

    Alpaca's own reference states both ``YYYY-MM-DD`` and
    ``YYYY-MM-DDTHH:MM:SSZ`` are supported, and ``FillHistory`` pages in epoch
    milliseconds, so the conversion happens here.
    """
    if type(moment_ms) not in (int, float):
        return ""
    held = float(moment_ms)
    if not math.isfinite(held) or held <= 0.0:
        return ""
    return datetime.fromtimestamp(held / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def fill_page_size(limit: Any, ceiling: Optional[int] = FILL_PAGE_SIZE_MAX) -> int:
    """``limit`` clamped to at least 1 and to ``ceiling`` where one is named,
    with ``FILL_PAGE_SIZE_MAX`` answering a ``limit`` that is no number.

    ``list_fills`` passes a ``ceiling`` of None, so the answer is the record
    count a caller asked for across pages.
    """
    if type(limit) not in (int, float):
        return FILL_PAGE_SIZE_MAX if ceiling is None else ceiling
    held = int(limit)
    if held < 1:
        return 1
    return held if ceiling is None else min(held, ceiling)


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one Alpaca asset record publishes.

    ``read`` is False for anything that is not a record, and a rule the record
    does not name is None rather than zero.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    return MarketRules(
        min_amount=rule_number(asset.get("min_order_size")),
        amount_increment=size_increment(asset),
        price_increment=rule_number(asset.get("price_increment")),
    )


class AlpacaConnector(BrokerBase):
    """
    Alpaca Markets broker connector.

    Usage:
        connector = AlpacaConnector()
        await connector.connect(api_key, api_secret, paper=True)
        account = await connector.get_account()
        order = await connector.place_order("AAPL", OrderSide.BUY, 10)
    """

    #: The four sectors Alpaca's own ``AssetClass`` words reach through
    #: ``POST /v2/orders``: crypto from ``crypto``, stocks from ``us_equity``,
    #: commodities from its one gold token and indices from ``us_index``. Forex
    #: and futures are absent because the venue publishes no currency class word
    #: and no perpetual order route, so ``broker_serves_sector`` answers False
    #: for both instead of claiming every sector.
    SECTORS_SERVED: tuple = ("crypto", "stocks", "commodities", "indices")

    #: Alpaca publishes its own filled trades, so ``get_my_trades`` reads
    #: ``list_fills`` instead of refusing.
    PUBLISHES_FILL_HISTORY: bool = True

    def __init__(self):
        super().__init__(VENUE_ID)
        self._auth_headers: dict[str, str] = {}
        self._base_url = PAPER_BASE
        self._data_url = DATA_BASE
        self._paper = True
        self._session = None

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Connect to Alpaca API."""
        self._auth_headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }
        self._paper = paper
        self._base_url = PAPER_BASE if paper else LIVE_BASE

        try:
            # Test connection by fetching account
            account = await self.get_account()
            if account.account_id:
                self._connected = True
                logger.info(
                    "Connected to Alpaca (%s): equity=$%.2f, buying_power=$%.2f",
                    "paper" if paper else "LIVE",
                    account.equity,
                    account.buying_power,
                )
                return True
        except Exception as e:
            logger.error("Alpaca connection failed: %s", e)

        return False

    async def disconnect(self):
        """Disconnect from Alpaca."""
        self._connected = False
        if self._session:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("Alpaca session already closed: %s", exc)
            self._session = None

    async def get_account(self) -> AccountInfo:
        """Get Alpaca account info."""
        data = await self._request("GET", "/v2/account")
        return AccountInfo(
            account_id=data.get("id", ""),
            equity=float(data.get("equity", 0)),
            cash=float(data.get("cash", 0)),
            buying_power=float(data.get("buying_power", 0)),
            portfolio_value=float(data.get("portfolio_value", 0)),
            day_trade_count=int(data.get("daytrade_count", 0)),
            pattern_day_trader=data.get("pattern_day_trader", False),
            account_blocked=data.get("account_blocked", False),
            trading_blocked=data.get("trading_blocked", False),
        )

    async def get_positions(self) -> list[StockPosition]:
        """Get all open positions."""
        data = await self._request("GET", "/v2/positions")
        positions = []
        for p in data:
            qty = float(p.get("qty", 0))
            positions.append(
                StockPosition(
                    symbol=p.get("symbol", ""),
                    quantity=qty,
                    avg_entry_price=float(p.get("avg_entry_price", 0)),
                    current_price=float(p.get("current_price", 0)),
                    market_value=float(p.get("market_value", 0)),
                    unrealized_pnl=float(p.get("unrealized_pl", 0)),
                    unrealized_pnl_pct=float(p.get("unrealized_plpc", 0)) * 100,
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                )
            )
        return positions

    async def get_position(self, symbol: str) -> Optional[StockPosition]:
        """Get position for a specific symbol."""
        try:
            p = await self._request("GET", f"/v2/positions/{symbol}")
            qty = float(p.get("qty", 0))
            return StockPosition(
                symbol=p.get("symbol", ""),
                quantity=qty,
                avg_entry_price=float(p.get("avg_entry_price", 0)),
                current_price=float(p.get("current_price", 0)),
                market_value=float(p.get("market_value", 0)),
                unrealized_pnl=float(p.get("unrealized_pl", 0)),
                unrealized_pnl_pct=float(p.get("unrealized_plpc", 0)) * 100,
                side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
            )
        except Exception:
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
        """Place one order via Alpaca, sized as a ``qty`` unit count.

        Alpaca's own order spec offers ``notional`` beside ``qty`` and takes one
        or the other; this body composes ``qty`` alone, so every built variant's
        unit count reaches the venue unchanged. ``published_time_in_force``
        names the time in force the venue takes for the market, because a crypto
        pair does not take the equity day default.
        """
        held_tif = published_time_in_force(symbol, time_in_force)
        if held_tif is not time_in_force:
            logger.info(
                "Alpaca %s takes no %s time in force; sending %s",
                symbol,
                time_in_force.value,
                held_tif.value,
            )
        body = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side.value,
            "type": order_type.value,
            "time_in_force": held_tif.value,
        }
        if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and limit_price > 0:
            body["limit_price"] = str(limit_price)
        if order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price > 0:
            body["stop_price"] = str(stop_price)

        data = await self._request("POST", "/v2/orders", body)
        return self._parse_order(data)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            await self._request("DELETE", f"/v2/orders/{order_id}")
            return True
        except Exception:
            return False

    async def get_order(self, order_id: str) -> StockOrder:
        """Get order status."""
        data = await self._request("GET", f"/v2/orders/{order_id}")
        return self._parse_order(data)

    async def get_open_orders(self) -> list[StockOrder]:
        """Get all open orders."""
        data = await self._request("GET", "/v2/orders?status=open")
        return [self._parse_order(o) for o in data]

    async def get_quote(self, symbol: str) -> StockQuote:
        """Get latest quote."""
        data = await self._request(
            "GET", f"/v2/stocks/{symbol}/quotes/latest", base_url=self._data_url
        )
        quote = data.get("quote", {})
        return StockQuote(
            symbol=symbol,
            bid=float(quote.get("bp", 0)),
            ask=float(quote.get("ap", 0)),
            last=float(quote.get("bp", 0)),  # Approximate
            volume=0,
            timestamp=time.time(),
        )

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """Get OHLCV bars."""
        tf_map = {
            "1Min": "1Min",
            "5Min": "5Min",
            "15Min": "15Min",
            "1H": "1Hour",
            "1D": "1Day",
            "1W": "1Week",
            "1m": "1Min",
            "5m": "5Min",
            "15m": "15Min",
            "1h": "1Hour",
            "1d": "1Day",
            "1w": "1Week",
        }
        alpaca_tf = tf_map.get(timeframe, "1Day")

        data = await self._request(
            "GET",
            f"/v2/stocks/{symbol}/bars?timeframe={alpaca_tf}&limit={limit}",
            base_url=self._data_url,
        )

        bars = []
        for bar in data.get("bars", []):
            bars.append(
                {
                    "timestamp": bar.get("t", ""),
                    "open": float(bar.get("o", 0)),
                    "high": float(bar.get("h", 0)),
                    "low": float(bar.get("l", 0)),
                    "close": float(bar.get("c", 0)),
                    "volume": int(bar.get("v", 0)),
                }
            )
        return bars

    async def get_market_status(self) -> dict:
        """Get current market status."""
        data = await self._request("GET", "/v2/clock")
        return {
            "is_open": data.get("is_open", False),
            "next_open": data.get("next_open", ""),
            "next_close": data.get("next_close", ""),
        }

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every asset record the broker publishes for ``status``, held for
        ``held_assets`` so ``record_markets`` can write them."""
        answered = await self._request("GET", f"/v2/assets?status={status}")
        rows: list[Any] = answered if isinstance(answered, list) else []
        self._assets = [row for row in rows if isinstance(row, dict)]
        return list(self._assets)

    async def list_fills(
        self,
        symbol: str = "",
        since_ms: Optional[float] = None,
        until_ms: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Every ``FILL`` activity Alpaca publishes for ``symbol``, newest first,
        within the moments ``since_ms`` and ``until_ms`` bound and up to
        ``limit`` records.

        ``GET /v2/account/activities/FILL`` caps a page at
        ``FILL_PAGE_SIZE_MAX`` and takes no symbol, so this walks ``page_token``
        over the whole account's fills until ``limit`` of them name ``symbol``,
        until a page comes back short, or until ``FILL_PAGES_MAX`` pages have
        been read. A caller reads a short answer as the end of the ledger, so a
        walk that stops on the page ceiling is logged as a truncation.
        """
        query = [f"page_size={FILL_PAGE_SIZE_MAX}"]
        after = activity_moment(since_ms)
        if after:
            query.append(f"after={after}")
        until = activity_moment(until_ms)
        if until:
            query.append(f"until={until}")
        base = f"/v2/account/activities/{FILL_ACTIVITY_TYPE}?" + "&".join(query)
        wanted = fill_page_size(limit, ceiling=None)
        name = str(symbol or "")
        found: list[dict] = []
        next_page = ""
        pages = 0
        while pages < FILL_PAGES_MAX:
            path = base + (f"&page_token={next_page}" if next_page else "")
            answered = await self._request("GET", path)
            rows: list[Any] = answered if isinstance(answered, list) else []
            page = [row for row in rows if isinstance(row, dict)]
            pages += 1
            found.extend(
                row for row in page if not name or str(row.get("symbol") or "") == name
            )
            if len(page) < FILL_PAGE_SIZE_MAX or len(found) >= wanted:
                return found[:wanted]
            next_page = str(page[-1].get("id") or "")
            if not next_page:
                return found[:wanted]
        logger.warning(
            "Alpaca fills for %s stopped at %d pages with %d record(s); the "
            "ledger is longer than this walk read",
            name or "every market",
            pages,
            len(found),
        )
        return found[:wanted]

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own asset records publishes,
        read through ``asset_rules`` so no broker is contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own asset records names, read through
        ``asset_sector`` so no broker is contacted."""
        return asset_sector(asset)

    def _parse_order(self, data: dict) -> StockOrder:
        """Parse Alpaca order response."""
        return StockOrder(
            order_id=data.get("id", ""),
            symbol=data.get("symbol", ""),
            side=OrderSide(data.get("side", "buy")),
            order_type=OrderType(data.get("type", "market")),
            quantity=float(data.get("qty", 0)),
            limit_price=float(data.get("limit_price", 0) or 0),
            stop_price=float(data.get("stop_price", 0) or 0),
            time_in_force=TimeInForce(data.get("time_in_force", "day")),
            status=data.get("status", "new"),
            filled_qty=float(data.get("filled_qty", 0) or 0),
            avg_fill_price=float(data.get("filled_avg_price", 0) or 0),
        )

    async def _request(
        self, method: str, path: str, body: dict = None, base_url: str = None
    ) -> dict:
        """Make authenticated API request to Alpaca."""
        import aiohttp

        url = (base_url or self._base_url) + path
        headers = dict(self._auth_headers)

        if not self._session:
            self._session = aiohttp.ClientSession()

        async with self._session.request(
            method, url, headers=headers, json=body
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 204:
                return {}
            else:
                text = await resp.text()
                raise Exception(f"Alpaca API {resp.status}: {text}")


#: Each venue id in ``SUPPORTED_BROKERS`` that has a ``BrokerBase`` subclass.
#: ``tradingview_webhook`` publishes no order interface and holds no class.
# ``interactivebrokers`` holds no row and is the same firm as ``IBKR_VENUE_ID``:
# ``www.ibkr.com`` redirects to ``www.interactivebrokers.com`` and serves the
# same 240,678 bytes. Removing the second id reshapes the Exchanges tab, which
# is its own row, so this registry names the one the rest of the tree reads.
BROKER_CONNECTORS: dict[str, type[BrokerBase]] = {
    VENUE_ID: AlpacaConnector,
    IBKR_VENUE_ID: IbkrConnector,
    ROBINHOOD_VENUE_ID: RobinhoodMcpBroker,
    SCHWAB_VENUE_ID: SchwabConnector,
}


def broker_connector_class(venue_id: Any) -> Optional[type[BrokerBase]]:
    """The ``BrokerBase`` subclass ``BROKER_CONNECTORS`` holds for ``venue_id``,
    and None for a venue with no broker connector.

    ``MainWindow._connect_exchange_for_bot`` reads this through
    ``broker_serves_sector``, and a venue id answering None takes a crypto path.
    """
    if not isinstance(venue_id, str):
        return None
    return BROKER_CONNECTORS.get(venue_id.strip().lower())


def broker_sectors(venue_id: Any) -> tuple:
    """The ``BrokerBase.SECTORS_SERVED`` one venue's broker class declares, and
    () for a venue ``broker_connector_class`` answers None for.

    An empty tuple from a venue that does hold a class narrows nothing, which
    ``broker_serves_sector`` reads as every sector.
    """
    held = broker_connector_class(venue_id)
    if held is None:
        return ()
    return tuple(getattr(held, "SECTORS_SERVED", ()) or ())


def broker_serves_sector(venue_id: Any, sector: Any = "") -> bool:
    """Whether one venue's broker route trades ``sector``.

    A venue whose ``broker_sectors`` is empty serves every sector, and a venue
    naming its own answers False outside them.
    """
    if broker_connector_class(venue_id) is None:
        return False
    named = broker_sectors(venue_id)
    held = str(sector or "").strip().lower()
    if not named or not held:
        return True
    return held in named


__all__ = [
    "ASSET_CLASS_SECTORS",
    "BROKER_CONNECTORS",
    "CRYPTO_DEFAULT_TIME_IN_FORCE",
    "CRYPTO_SYMBOL_SEPARATOR",
    "CRYPTO_TIMES_IN_FORCE",
    "DATA_BASE",
    "FILL_ACTIVITY_TYPE",
    "FILL_PAGES_MAX",
    "FILL_PAGE_SIZE_MAX",
    "LIVE_BASE",
    "PAPER_BASE",
    "SUPPORTED_BROKERS",
    "VENUE_ID",
    "WHOLE_SHARE_INCREMENT",
    "AlpacaConnector",
    "activity_moment",
    "asset_rules",
    "asset_sector",
    "broker_connector_class",
    "broker_sectors",
    "broker_serves_sector",
    "crypto_symbol",
    "fill_page_size",
    "published_time_in_force",
    "rule_number",
    "size_increment",
]
