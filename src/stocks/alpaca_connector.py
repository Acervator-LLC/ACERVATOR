"""
alpaca_connector.py — Alpaca Markets broker connector.

Alpaca provides commission-free stock trading with a robust API.
Supports paper trading for testing. REST + WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

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

# Alpaca API endpoints
PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"

# Supported brokers registry
SUPPORTED_BROKERS = {
    "alpaca": {
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


class AlpacaConnector(BrokerBase):
    """
    Alpaca Markets broker connector.

    Usage:
        connector = AlpacaConnector()
        await connector.connect(api_key, api_secret, paper=True)
        account = await connector.get_account()
        order = await connector.place_order("AAPL", OrderSide.BUY, 10)
    """

    def __init__(self):
        super().__init__("alpaca")
        self._api_key = ""
        self._api_secret = ""
        self._base_url = PAPER_BASE
        self._data_url = DATA_BASE
        self._paper = True
        self._session = None

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Connect to Alpaca API."""
        self._api_key = api_key
        self._api_secret = api_secret
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
            except (
                Exception
            ):  # R28-OK: shutdown best-effort; session may already be closed
                pass
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
        """Place a stock order via Alpaca."""
        body = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side.value,
            "type": order_type.value,
            "time_in_force": time_in_force.value,
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
        headers = {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

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
