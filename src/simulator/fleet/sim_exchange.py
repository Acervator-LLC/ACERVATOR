"""Candle-driven fake exchange for Fleet Replay, over real symbols.

Serves per-symbol ``CandleSeries`` through the ``ExchangeInterface`` API,
so a bot trades BTC/USD or ETH/USD against stored candles instead of a
venue. ``NuclearSimExchange`` (``src/simulator/nuclear_sim_exchange.py``)
is the other simulated venue and serves synthetic TAPEA/TAPEB symbols.

Reachability: nothing under ``src/`` constructs ``FleetSimExchange``.
``FleetReplayController`` imports only ``make_symbol_series_map`` from
this module and runs against ``TabletBackend``
(``src/exchange/tablet_backend.py``). The class itself is built by tests.

Order execution:
    * MARKET fills at the current candle close.
    * LIMIT fills at the order price when the cursor's candle sweeps it
      (buy: low <= price, sell: high >= price), and otherwise rests
      until a later sweep or ``cancel_order``.
    * IOC_LIMIT runs the same sweep test and cancels instead of resting.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from ...exchange.base import (
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
from .candle_series import CandleSeries

logger = logging.getLogger("acervator.simulator.fleet.sim_exchange")


def make_symbol_series_map(
    symbol_rows: dict[str, list[list[float]]],
) -> dict[str, CandleSeries]:
    """Build ``{symbol: CandleSeries}`` from ``{symbol: rows}``.

    Takes the raw row shape the OHLCV fetchers already return, so a
    caller can hand fetched candles straight to ``FleetSimExchange``.
    """
    from .candle_series import build_candle_series_from_rows

    return {
        symbol: build_candle_series_from_rows(symbol, rows)
        for symbol, rows in (symbol_rows or {}).items()
    }


# Duplicate of ccxt_connector.EFFECTIVE_OHLCV_PAGE_SIZE; test_sim_live_ohlcv_parity
# asserts the two are equal.
LIVE_EFFECTIVE_PAGE_SIZE = 300


class FleetSimExchange(ExchangeInterface):
    """Real-symbol candle-driven fake exchange for Fleet Replay.

    Construction:
        series_map = make_symbol_series_map({
            "BTC/USD": [[ts_ms, o, h, l, c, v], ...],
            "ETH/USD": [...],
        })
        ex = FleetSimExchange(
            series_map,
            starting_balances={"USD": 10000.0},
            exchange_id="fleet_sim")

    Cursor advancement is the CALLER's job (controller pattern):
        ex.step()               # advance every symbol by one candle
        # or per-symbol:
        ex.step_symbol("BTC/USD")
    """

    # Mirrors stone_tablets.registry.NATIVE_TIMEFRAME; every other timeframe
    # rolls up from this one.
    NATIVE_TIMEFRAME: str = "5m"

    def __init__(
        self,
        series_map: dict[str, CandleSeries],
        starting_balances: Optional[dict[str, float]] = None,
        fee_pct: float = 0.0,
        fee_pct_by_symbol: Optional[dict] = None,
        exchange_id: str = "fleet_sim",
    ) -> None:
        if not isinstance(series_map, dict):
            raise TypeError(
                "FleetSimExchange: series_map must be a dict of symbol → "
                f"CandleSeries, got {type(series_map).__name__}"
            )
        self._series: dict[str, CandleSeries] = dict(series_map)
        # Optional per-(symbol, timeframe) series; no code writes it, so
        # get_ohlcv always falls back to the native map above.
        self._tf_series: dict[tuple, CandleSeries] = {}
        self._tf_fallback_warned: set = set()
        self._fee_pct = float(fee_pct)
        # FRACTIONS (0.016), not percents: BotConfig.trading_fee_pct is a
        # percent that ScrummingBot.tick divides by 100.
        self._fee_pct_by_symbol: dict[str, float] = {
            str(k): float(v) for k, v in (fee_pct_by_symbol or {}).items()
        }
        self._exchange_id = exchange_id
        self._connected = False
        # Currency to free amount; a currency that is missing is zero.
        self._balances: dict[str, float] = dict(starting_balances or {})
        # Copy of starting_balances taken before the seeding below;
        # nothing reads it.
        self._opening_balances: dict[str, float] = dict(starting_balances or {})
        # Seed both sides of every pair so get_balance reports absent=False.
        for sym in self._series:
            if "/" not in sym:
                continue
            base, quote = sym.split("/", 1)
            self._balances.setdefault(base.upper(), 0.0)
            self._balances.setdefault(quote.upper(), 0.0)
        # id to Order; filled and cancelled orders stay so get_order finds them.
        self._orders: dict[str, Order] = {}
        # Open order ids per symbol, so a sweep costs O(open) rather than
        # O(every order ever placed).
        self._open_by_symbol: dict[str, set[str]] = {}
        # Fill tape; get_my_trades filters this list.
        self._trades: list[Trade] = []
        # Optional callback invoked with each Trade; the replay controller
        # registers on TabletBackend instead.
        self._on_trade = None
        # Clock is built from the native map only: a rollup bucket can start
        # before the first native candle and would add unbacked ticks.
        from .master_clock import MasterClock

        self._master_clock = MasterClock.from_series(self._series.values())

    def fee_for(self, symbol: str) -> float:
        """Fee FRACTION for one symbol, falling back to the default.

        Per-symbol because a single exchange-wide rate cannot represent a
        fleet whose bots trade on different fee tiers.
        """
        return self._fee_pct_by_symbol.get(str(symbol), self._fee_pct)

    # ─── Properties ──────────────────────────────────────────────
    @property
    def exchange_id(self) -> str:
        return self._exchange_id

    @property
    def display_name(self) -> str:
        return "Fleet Sim"

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ─── Connect / disconnect (no-op) ────────────────────────────
    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        del api_key, api_secret, passphrase
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    # ─── Cursor control (called by the replay controller) ────────
    def step(self) -> bool:
        """Advance the master clock one timestamp and move every series.

        Each series moves to the candle whose ts is at or before the new
        master timestamp. A series whose first candle is later than that
        timestamp keeps its cursor at 0, so it is parked on a candle from
        its own future; ``has_data`` reports that condition and a caller
        must not tick a bot while it is False.

        Sweeps the open limit orders after the price step. Returns False
        when the master clock is exhausted.
        """
        if not self._master_clock.step():
            return False
        target_ts = self._master_clock.current_ts_ms()
        if target_ts is None:
            return False
        for series in self._series.values():
            # Return value ignored; has_data recomputes the same condition.
            series.step_to_ts(target_ts)
        # After the price step, sweep the open limit orders — any that
        # the new candle crosses should fill now, before the next tick.
        self._sweep_open_limit_orders()
        return True

    @property
    def master_clock(self):
        """The master clock, exposed for progress reporting."""
        return self._master_clock

    def total_clock_ticks(self) -> int:
        """Total ticks the replay will play: the size of the timestamp union."""
        return self._master_clock.total

    def has_data(self, symbol: str) -> bool:
        """Has the master clock reached this symbol's first candle?

        False during a symbol's lead-in, when the series is still parked
        on a candle from its own future. Callers must not run a bot on a
        symbol while this is False.

        Recomputed from the master timestamp and the series' first row on
        every call, so it cannot drift out of step with the cursor.
        """
        series = self._series.get(symbol)
        if series is None or not series.rows:
            return False
        ts = self._master_clock.current_ts_ms()
        if ts is None:
            return False
        try:
            return int(ts) >= int(series.rows[0][0])
        except (TypeError, ValueError, IndexError):
            return False

    def step_symbol(self, symbol: str) -> bool:
        s = self._series.get(symbol)
        if s is None:
            return False
        ok = s.step()
        self._sweep_open_limit_orders(only_symbol=symbol)
        return ok

    def on_trade(self, cb) -> None:
        """Register a callback ``cb(trade: Trade)`` fired on each fill."""
        self._on_trade = cb

    # ─── Market data ─────────────────────────────────────────────
    async def get_ticker(self, symbol: str) -> Ticker:
        series = self._series.get(symbol)
        if series is None:
            raise ValueError(f"FleetSimExchange.get_ticker: unknown symbol {symbol!r}")
        cur = series.get_current()
        if cur is None:
            raise RuntimeError(
                f"FleetSimExchange.get_ticker: no candle data for " f"{symbol!r}"
            )
        ts_ms, _o, _h, _l, close, vol = cur
        spread = 0.0005
        return Ticker(
            symbol=symbol,
            bid=close * (1.0 - spread / 2),
            ask=close * (1.0 + spread / 2),
            last=close,
            volume_24h=vol * 24.0,
            timestamp=float(ts_ms) / 1000.0,
        )

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        series = self._series.get(symbol)
        if series is None:
            raise ValueError(
                f"FleetSimExchange.get_orderbook: unknown symbol {symbol!r}"
            )
        cur = series.get_current()
        if cur is None:
            raise RuntimeError(
                f"FleetSimExchange.get_orderbook: no data for {symbol!r}"
            )
        close = float(cur[4])
        step = max(1e-9, close * 0.001)
        bids = [(close - step * (i + 1), 100.0) for i in range(limit)]
        asks = [(close + step * (i + 1), 100.0) for i in range(limit)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=time.time())

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[list[float]]:
        # Serves the (symbol, timeframe) series when one exists, else the
        # native series with a warning.
        _tf = str(timeframe or "").strip() or self.NATIVE_TIMEFRAME
        series = None
        _tf_map = getattr(self, "_tf_series", None)
        if _tf_map:
            series = _tf_map.get((symbol, _tf))
        if series is None:
            series = self._series.get(symbol)
            if series is not None and _tf != self.NATIVE_TIMEFRAME:
                # Once per (symbol, timeframe), so a replay does not repeat it.
                _seen = self._tf_fallback_warned
                if (symbol, _tf) not in _seen:
                    _seen.add((symbol, _tf))
                    logger.warning(
                        "FleetSimExchange: no %s series for %s; serving "
                        "the native %s series. Higher-timeframe TA for "
                        "this symbol is NOT independent.",
                        _tf,
                        symbol,
                        self.NATIVE_TIMEFRAME,
                    )
        if series is None:
            raise ValueError(f"FleetSimExchange.get_ohlcv: unknown symbol {symbol!r}")
        # Live ignores `limit` — CCXTConnector.get_ohlcv puts it in ccxt's
        # `since` slot — so it stays in the signature only for parity.
        return series.get_history(limit=LIVE_EFFECTIVE_PAGE_SIZE)

    # ─── Account ─────────────────────────────────────────────────
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

    # ─── Orders ──────────────────────────────────────────────────
    def _adjust_balance(self, currency: str, delta: float) -> None:
        self._balances[currency] = float(self._balances.get(currency, 0.0)) + float(
            delta
        )

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
                f"FleetSimExchange.place_order: amount must be positive, "
                f"got {amount!r}"
            )
        series = self._series.get(symbol)
        if series is None:
            raise ValueError(f"FleetSimExchange.place_order: unknown symbol {symbol!r}")
        cur = series.get_current()
        if cur is None:
            raise RuntimeError(
                f"FleetSimExchange.place_order: no candle data for " f"{symbol!r}"
            )
        base, quote = symbol.split("/", 1)
        base = base.upper()
        quote = quote.upper()

        order = Order(
            id=f"fleet_{uuid.uuid4().hex[:12]}",
            symbol=symbol,
            side=side,
            type=order_type,
            amount=float(amount),
            price=0.0 if price is None else float(price),
            remaining=float(amount),
            status=OrderStatus.OPEN,
            timestamp=time.time(),
        )

        if order_type == OrderType.MARKET:
            fill_price = float(cur[4])
            self._settle_fill(order, fill_price, base, quote)
        elif order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("FleetSimExchange.place_order: LIMIT requires price")
            fill_price = float(price)
            # If the current candle already sweeps this price, fill now.
            candle_low = float(cur[3])
            candle_high = float(cur[2])
            crosses = (side == OrderSide.BUY and candle_low <= fill_price) or (
                side == OrderSide.SELL and candle_high >= fill_price
            )
            if crosses:
                self._settle_fill(order, fill_price, base, quote)
            # else: order stays OPEN until _sweep_open_limit_orders
        elif order_type == OrderType.IOC_LIMIT:
            # Immediate-or-Cancel: the LIMIT crosses test, but it never rests.
            if price is None:
                raise ValueError(
                    "FleetSimExchange.place_order: IOC_LIMIT requires " "price"
                )
            _limit = float(price)
            _low = float(cur[3])
            _high = float(cur[2])
            _close = float(cur[4])
            _crosses = (side == OrderSide.BUY and _low <= _limit) or (
                side == OrderSide.SELL and _high >= _limit
            )
            if _crosses:
                # Fill no worse than the market was: the limit caps a BUY
                # and floors a SELL. NuclearSimExchange uses the same pair.
                _fp = (
                    min(_limit, _close)
                    if side == OrderSide.BUY
                    else max(_limit, _close)
                )
                self._settle_fill(order, _fp, base, quote)
            else:
                order.status = OrderStatus.CANCELLED
                order.filled = 0.0
                order.remaining = float(amount)
        else:
            raise ValueError(
                f"FleetSimExchange.place_order: unsupported type " f"{order_type!r}"
            )

        self._orders[order.id] = order
        if order.status == OrderStatus.OPEN:
            self._mark_open(order)
        return order

    def _mark_open(self, order: Order) -> None:
        """Add an order to the open index. See ``_open_by_symbol``."""
        self._open_by_symbol.setdefault(order.symbol, set()).add(order.id)

    def _unmark_open(self, order: Order) -> None:
        """Drop an order from the open index once it can no longer fill.

        Called on both fill and cancel. Missing this is the failure mode
        the index introduces: a stale id makes the sweep re-settle an
        already-filled order, double-counting the balance change.
        """
        ids = self._open_by_symbol.get(order.symbol)
        if ids is not None:
            ids.discard(order.id)
            if not ids:
                del self._open_by_symbol[order.symbol]

    def _cursor_index(self, symbol: str) -> Optional[int]:
        """Current candle index for a symbol, or None if unknown."""
        series = self._series.get(symbol)
        if series is None:
            return None
        try:
            return int(series.cursor)
        except (TypeError, ValueError, AttributeError):
            return None

    def _candle_address_for(self, symbol: str) -> str:
        """Stone Tablet address ``NNNNNN_TICKER`` for the candle under the
        cursor. Returns an empty string when it cannot be resolved, so a
        fill records without an address rather than with a wrong one."""
        idx = self._cursor_index(symbol)
        if idx is None:
            return ""
        try:
            from src.trading.stone_tablets.addressing import (
                format_address,
                ticker_from_symbol,
            )

            return format_address(ticker_from_symbol(symbol), idx)
        except Exception as exc:  # noqa: BLE001 - addressing is advisory
            logger.debug("candle address unavailable for %s@%s: %s", symbol, idx, exc)
            return ""

    def _settle_fill(
        self,
        order: Order,
        fill_price: float,
        base: str,
        quote: str,
    ) -> None:
        amount = float(order.amount)
        notional = amount * fill_price
        fee = notional * self.fee_for(order.symbol)
        # All four settle paths funnel here, so the affordability check
        # lives here and not at the place_order entry points.
        _need_ccy, _need_qty, _have = (
            (quote, notional + fee, self._balances.get(quote, 0.0))
            if order.side == OrderSide.BUY
            else (base, amount, self._balances.get(base, 0.0))
        )
        # 1e-12 admits an exactly funded order, matching NuclearSimExchange.
        if float(_have) + 1e-12 < float(_need_qty):
            raise ValueError(
                f"FleetSimExchange._settle_fill: insufficient "
                f"{_need_ccy} for {order.symbol} — need "
                f"{_need_qty:.10g}, have {float(_have):.10g}. Refusing "
                f"rather than settling a trade the ledger cannot fund."
            )
        if order.side == OrderSide.BUY:
            self._adjust_balance(quote, -(notional + fee))
            self._adjust_balance(base, +amount)
        else:
            self._adjust_balance(quote, +(notional - fee))
            self._adjust_balance(base, -amount)
        order.status = OrderStatus.FILLED
        self._unmark_open(order)
        order.filled = amount
        order.remaining = 0.0
        order.average = fill_price
        # Sim time from the master clock, in ms, converted to the seconds
        # Trade.timestamp carries. Wall-clock time would stamp every fill "now".
        _sim_ts_ms = self._master_clock.current_ts_ms()
        _sim_ts_s = (
            float(_sim_ts_ms) / 1000.0 if _sim_ts_ms is not None else time.time()
        )
        # Stone Tablet candle address, so a fill is traceable to the candle
        # it fired on. SimRunLog.record_trade stores it.
        _addr = self._candle_address_for(order.symbol)
        trade = Trade(
            id=f"t_{uuid.uuid4().hex[:12]}",
            symbol=order.symbol,
            side=order.side,
            amount=amount,
            price=fill_price,
            fee=fee,
            fee_currency=quote,
            timestamp=_sim_ts_s,
            raw={
                "order_id": order.id,
                "sim_master_ts_ms": _sim_ts_ms,
                "candle_address": _addr,
                "candle_index": self._cursor_index(order.symbol),
            },
        )
        # The Order carries the fee fields CCXTConnector populates on every
        # live order, so the two shapes match.
        order.fee = fee
        order.fee_currency = quote
        order.raw = {
            "order_id": order.id,
            "sim_master_ts_ms": _sim_ts_ms,
            "candle_address": _addr,
            "candle_index": self._cursor_index(order.symbol),
            "fill_price": fill_price,
            "notional": notional,
        }
        self._trades.append(trade)
        if self._on_trade is not None:
            try:
                self._on_trade(trade)
            except Exception as _cb_exc:  # noqa: BLE001 - callback surface
                logger.debug("FleetSimExchange on_trade cb raised: %s", _cb_exc)

    def _sweep_open_limit_orders(
        self,
        only_symbol: Optional[str] = None,
    ) -> int:
        """Fill any open LIMIT orders that the current candle sweeps.
        Returns count filled."""
        filled = 0
        # Candidates are resolved first, so a fill that mutates
        # _open_by_symbol cannot invalidate the loop.
        if only_symbol is not None:
            symbols = [only_symbol] if only_symbol in self._open_by_symbol else []
        else:
            symbols = list(self._open_by_symbol)
        candidates: list[Order] = []
        for sym in symbols:
            for oid in list(self._open_by_symbol.get(sym, ())):
                o = self._orders.get(oid)
                if o is not None:
                    candidates.append(o)
        for order in candidates:
            if order.status != OrderStatus.OPEN:
                continue
            series = self._series.get(order.symbol)
            if series is None:
                continue
            cur = series.get_current()
            if cur is None or order.price is None:
                continue
            candle_low = float(cur[3])
            candle_high = float(cur[2])
            crosses = (order.side == OrderSide.BUY and candle_low <= order.price) or (
                order.side == OrderSide.SELL and candle_high >= order.price
            )
            if not crosses:
                continue
            base, quote = order.symbol.split("/", 1)
            self._settle_fill(order, float(order.price), base.upper(), quote.upper())
            filled += 1
        return filled

    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        del symbol
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(
                f"FleetSimExchange.cancel_order: unknown order {order_id!r}"
            )
        if order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELLED
            self._unmark_open(order)
        return order

    async def get_order(self, order_id: str, symbol: str) -> Order:
        del symbol
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"FleetSimExchange.get_order: unknown order {order_id!r}")
        return order

    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
    ) -> list[Order]:
        return [
            o
            for o in self._orders.values()
            if o.status == OrderStatus.OPEN and (symbol is None or o.symbol == symbol)
        ]

    async def get_my_trades(
        self,
        symbol: str,
        since: Optional[float] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list:
        # params exists for signature parity with CCXTConnector, which
        # ScrummingBot.sync_ytd_trade_count calls with paginate and until.
        del params
        out = [t for t in self._trades if t.symbol == symbol]
        if since is not None:
            out = [t for t in out if t.timestamp >= float(since)]
        if limit is not None:
            out = out[-int(limit) :]
        return out

    # ─── Discovery ───────────────────────────────────────────────
    async def get_markets(self) -> list[AssetInfo]:
        out: list[AssetInfo] = []
        for sym in sorted(self._series.keys()):
            if "/" not in sym:
                continue
            base, quote = sym.split("/", 1)
            out.append(
                AssetInfo(
                    symbol=sym,
                    base=base.upper(),
                    quote=quote.upper(),
                    # Placeholder limits matching NuclearSimExchange; real ones are online only.
                    min_amount=1e-8,
                    min_cost=1.0,
                    amount_precision=8,
                    price_precision=8,
                    maker_fee=0.0,
                    taker_fee=0.0,
                    active=True,
                )
            )
        return out

    async def get_asset_logo_url(self, currency: str) -> str:
        del currency
        return ""


__all__ = ["FleetSimExchange", "make_symbol_series_map"]
