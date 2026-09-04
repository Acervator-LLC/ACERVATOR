"""Sim exchange that serves ``NuclearCandleSource`` tapes as markets.

The exchange maps synthetic base currencies (``TAPEA``, ``TAPEB``, ...)
onto candle-source tape ids, so a bot trades ``TAPEA/USD`` and never
sees which real instrument the tape replays. Tape ids come from
``NuclearCandleSource.list_tapes()``; the synthetic-base to tape-id map
is built from the source's wired tapes at construction.

``NuclearController`` constructs it and imports the module's
``_tape_id_to_base`` helper to build the bot's symbol.

Every refusal raises rather than settling quietly: an unknown symbol, a
foreign quote currency, an unwired tape, a non-positive amount, a
missing candle, and a balance too small to fund the order.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from ..exchange.base import (
    AssetInfo,
    Balance,
    ExchangeInterface,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Ticker,
    Trade,
)

from .nuclear_candle_source import NuclearCandleSource


def _tape_id_to_base(tape_id: str) -> str:
    """Tape id "A" to the synthetic base token "TAPEA" a bot trades as an asset.

    Shared with ``NuclearController``, which builds the bot's symbol
    from it.
    """
    return f"TAPE{tape_id}"


def _base_to_tape_id(base: str) -> Optional[str]:
    """Synthetic base "TAPEA" back to tape id "A"; None if not a TAPEx token."""
    if not base.startswith("TAPE"):
        return None
    rest = base[len("TAPE") :]
    return rest if rest else None


def _candle_to_ohlcv_row(c: tuple) -> list:
    """Source tuple is (ts_seconds, o, h, l, c, v); production contract
    is [[ts_ms, o, h, l, c, v], ...]."""
    return [
        int(c[0]) * 1000,
        float(c[1]),
        float(c[2]),
        float(c[3]),
        float(c[4]),
        float(c[5]),
    ]


class NuclearSimExchange(ExchangeInterface):
    """Simulated exchange backed by ``NuclearCandleSource`` tapes.

    ``get_markets`` advertises one symbol per wired tape ("TAPEA/USD",
    "TAPEB/USD", ...), each a full market, so several ``ScrummingBot``
    instances can run against different tapes on one exchange.

        src = NuclearCandleSource()
        src.wire("A")
        src.wire("B")
        ex = NuclearSimExchange(src, quote_seed=200.0)
    """

    def __init__(
        self,
        candle_source: NuclearCandleSource,
        quote_currency: str = "USD",
        quote_seed: float = 200.0,
        fee_pct: float = 0.0,
        exchange_id: str = "nuclear_sim",
    ) -> None:
        self._src = candle_source
        self._quote = quote_currency
        self._fee_pct = float(fee_pct)
        self._exchange_id = exchange_id
        self._connected = False
        # Explicit zero, not absent: ScrummingBot._tick_initialise refuses a
        # balance the exchange did not report.
        self._balances: dict[str, float] = {quote_currency: float(quote_seed)}
        for tid in candle_source.active_tapes():
            self._balances[_tape_id_to_base(tid)] = 0.0
        self._orders: dict[str, Order] = {}
        self._trades: list[Trade] = []
        self._asset_meta: dict[str, AssetInfo] = {}

    # ─── Properties (required by ExchangeInterface) ────────────────────

    @property
    def exchange_id(self) -> str:
        return self._exchange_id

    @property
    def display_name(self) -> str:
        return "Nuclear Sim"

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ─── Connection ────────────────────────────────────────────────────

    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        del api_key, api_secret, passphrase
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    # ─── Internal: symbol ↔ tape mapping ───────────────────────────────

    def _resolve_tape(self, symbol: str) -> str:
        """Map symbol "TAPEA/USD" to tape id "A".

        Raises ValueError for a symbol that is not BASE/QUOTE, a quote
        other than the configured one, a base that is not a TAPEx
        token, or a tape not wired into this exchange.
        """
        if "/" not in symbol:
            raise ValueError(
                f"NuclearSimExchange: symbol must be BASE/QUOTE, got " f"{symbol!r}"
            )
        base, quote = symbol.split("/", 1)
        if quote != self._quote:
            raise ValueError(
                f"NuclearSimExchange: quote {quote!r} != configured "
                f"quote {self._quote!r} (symbol={symbol!r})"
            )
        tid = _base_to_tape_id(base)
        if tid is None:
            raise ValueError(
                f"NuclearSimExchange: base {base!r} is not a TAPEx token "
                f"(symbol={symbol!r})"
            )
        if tid not in self._src.active_tapes():
            raise ValueError(
                f"NuclearSimExchange: tape {tid!r} is not wired into "
                f"this exchange. Wired: {self._src.active_tapes()}"
            )
        return tid

    # ─── Market data ───────────────────────────────────────────────────

    async def get_ticker(self, symbol: str) -> Ticker:
        tid = self._resolve_tape(symbol)
        c = self._src.current(tid)
        if c is None:
            raise RuntimeError(
                f"NuclearSimExchange.get_ticker: no candle data for "
                f"tape {tid!r} (symbol={symbol!r})"
            )
        ts, _o, _h, _l, close, vol = c
        spread = 0.0005  # 5 bps
        return Ticker(
            symbol=symbol,
            bid=close * (1 - spread / 2),
            ask=close * (1 + spread / 2),
            last=close,
            volume_24h=vol * 24.0,
            timestamp=float(ts),
        )

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        tid = self._resolve_tape(symbol)
        c = self._src.current(tid)
        if c is None:
            raise RuntimeError(
                f"NuclearSimExchange.get_orderbook: no data for " f"tape {tid!r}"
            )
        close = float(c[4])
        step = close * 0.001
        bids = [(close - step * (i + 1), 100.0) for i in range(limit)]
        asks = [(close + step * (i + 1), 100.0) for i in range(limit)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=time.time())

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[list[float]]:
        """Return the last ``limit`` candles ending at the tape cursor.

        ``timeframe`` is ignored — a tape carries one candle stream at
        its cached interval — and the rows come back in the production
        ``[[ts_ms, o, h, l, c, v], ...]`` shape.
        """
        del timeframe
        tid = self._resolve_tape(symbol)
        rows = self._src.history(tid, limit=limit)
        return [_candle_to_ohlcv_row(r) for r in rows]

    # ─── Account ───────────────────────────────────────────────────────

    async def get_balances(self) -> dict[str, Balance]:
        return {
            cur: Balance(
                currency=cur,
                free=float(free),
                used=0.0,
                total=float(free),
                absent=False,
            )
            for cur, free in self._balances.items()
        }

    async def get_balance(self, currency: str) -> Balance:
        free = float(self._balances.get(currency, 0.0))
        absent = currency not in self._balances
        return Balance(
            currency=currency, free=free, used=0.0, total=free, absent=absent
        )

    # ─── Orders ────────────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        del client_order_id
        if amount is None or amount <= 0:
            raise ValueError(
                f"NuclearSimExchange.place_order: amount must be "
                f"positive, got {amount!r}"
            )
        tid = self._resolve_tape(symbol)
        c = self._src.current(tid)
        if c is None:
            raise RuntimeError(
                f"NuclearSimExchange.place_order: no candle data for " f"tape {tid!r}"
            )
        fill_price = float(c[4])
        # min/max, not the limit itself: a BUY limit above the market, or a
        # SELL below it, fills at the close rather than its own worse price.
        # Nuclear is single-shot, so an uncrossed order never rests.
        _is_limit_kind = order_type in (OrderType.LIMIT, OrderType.IOC_LIMIT)
        _unfillable = False
        if _is_limit_kind and price is not None:
            _limit = float(price)
            _high = float(c[2])
            _low = float(c[3])
            _close = float(c[4])
            if side == OrderSide.BUY:
                if _low <= _limit:
                    fill_price = min(_limit, _close)
                else:
                    _unfillable = True
            else:
                if _high >= _limit:
                    fill_price = max(_limit, _close)
                else:
                    _unfillable = True

        if _unfillable:
            _order = Order(
                id=f"nuclear_{uuid.uuid4().hex[:12]}",
                symbol=symbol,
                side=side,
                type=order_type,
                amount=float(amount),
                price=float(price),
                filled=0.0,
                remaining=float(amount),
                # An IOC never rests, so an uncrossed one is CANCELLED, not OPEN.
                status=(
                    OrderStatus.CANCELLED
                    if order_type == OrderType.IOC_LIMIT
                    else OrderStatus.OPEN
                ),
                timestamp=time.time(),
                fee=0.0,
                fee_currency=symbol.split("/", 1)[1],
                average=0.0,
                raw={
                    "sim": True,
                    "candle_ts": int(c[0]),
                    "tape": tid,
                    "unfilled_reason": "limit not crossed by candle",
                },
            )
            self._orders[_order.id] = _order
            return _order

        base, quote = symbol.split("/", 1)
        notional = amount * fill_price
        fee = notional * self._fee_pct
        # `_adjust_balance` has no floor, so an unfunded order would settle
        # and leave the ledger negative while the run still reports P&L.
        _need_ccy, _need_qty, _have = (
            (quote, notional + fee, self._balances.get(quote, 0.0))
            if side == OrderSide.BUY
            else (base, amount, self._balances.get(base, 0.0))
        )
        # The 1e-12 tolerance admits an exactly funded order that float
        # error would otherwise refuse.
        if float(_have) + 1e-12 < float(_need_qty):
            raise ValueError(
                f"NuclearSimExchange.place_order: insufficient "
                f"{_need_ccy} — need {_need_qty:.10g}, have "
                f"{float(_have):.10g}. Refusing rather than settling a "
                f"trade the ledger cannot fund."
            )
        if side == OrderSide.BUY:
            self._adjust_balance(quote, -(notional + fee))
            self._adjust_balance(base, +amount)
        else:
            self._adjust_balance(quote, +(notional - fee))
            self._adjust_balance(base, -amount)
        order = Order(
            id=f"nuclear_{uuid.uuid4().hex[:12]}",
            symbol=symbol,
            side=side,
            type=order_type,
            amount=float(amount),
            price=fill_price,
            filled=float(amount),
            remaining=0.0,
            status=OrderStatus.FILLED,
            timestamp=time.time(),
            fee=fee,
            fee_currency=quote,
            average=fill_price,
            raw={"sim": True, "candle_ts": int(c[0]), "tape": tid},
        )
        self._orders[order.id] = order
        self._trades.append(
            Trade(
                id=order.id,
                symbol=symbol,
                side=side,
                amount=float(amount),
                price=fill_price,
                fee=fee,
                fee_currency=quote,
                timestamp=order.timestamp,
                raw={"sim": True, "order_id": order.id, "tape": tid},
            )
        )
        return order

    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        del symbol
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(
                f"NuclearSimExchange.cancel_order: unknown order " f"{order_id!r}"
            )
        return order

    async def get_order(self, order_id: str, symbol: str) -> Order:
        del symbol
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(
                f"NuclearSimExchange.get_order: unknown order " f"{order_id!r}"
            )
        return order

    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        del symbol
        return []

    async def get_my_trades(
        self, symbol: str, since: Optional[float] = None, limit: Optional[int] = None
    ) -> list:
        out = [t for t in self._trades if t.symbol == symbol]
        if since is not None:
            out = [t for t in out if t.timestamp >= since]
        if limit is not None:
            out = out[-int(limit) :]
        return out

    # ─── Asset discovery ───────────────────────────────────────────────

    async def get_markets(self) -> list[AssetInfo]:
        """One AssetInfo per wired tape: TAPEx/<QUOTE>."""
        out = []
        for tid in self._src.active_tapes():
            symbol = f"{_tape_id_to_base(tid)}/{self._quote}"
            if symbol not in self._asset_meta:
                self._asset_meta[symbol] = AssetInfo(
                    symbol=symbol,
                    base=_tape_id_to_base(tid),
                    quote=self._quote,
                    min_amount=1e-8,
                    # Placeholders, not the venue's own limits, and equal to
                    # FleetSimExchange so a strategy meets the same smallest
                    # order on both. `bot_container._get_market_limits` reads
                    # them from here, and nothing offline captures the real
                    # per-symbol values.
                    min_cost=1.0,
                    price_precision=8,
                    amount_precision=8,
                    maker_fee=self._fee_pct,
                    taker_fee=self._fee_pct,
                    active=True,
                    logo_url="",
                )
            out.append(self._asset_meta[symbol])
        return out

    async def get_asset_logo_url(self, currency: str) -> str:
        del currency
        return ""

    # ─── Helpers ───────────────────────────────────────────────────────

    def _adjust_balance(self, currency: str, delta: float) -> None:
        self._balances[currency] = self._balances.get(currency, 0.0) + float(delta)

    def snapshot(self) -> dict:
        return {
            "exchange_id": self._exchange_id,
            "connected": self._connected,
            "quote_currency": self._quote,
            "fee_pct": self._fee_pct,
            "balances": dict(self._balances),
            "n_orders": len(self._orders),
            "n_trades": len(self._trades),
            "candle_source": self._src.stats(),
        }
