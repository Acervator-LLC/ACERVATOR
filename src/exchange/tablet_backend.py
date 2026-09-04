"""A ccxt-shaped exchange backed by Stone Tablets instead of the network."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from ccxt.base.errors import InsufficientFunds

__all__ = ["TabletBackend", "TabletNotStarted"]

logger = logging.getLogger(__name__)

# Candles fetch_ohlcv returns when limit is unset.
DEFAULT_PAGE_SIZE = 300

NATIVE_TIMEFRAME = "5m"  # what the Stone Tablets store


class TabletNotStarted(Exception):
    """Raised when a symbol is read before its tablet begins."""


class TabletBackend:
    """Serves ccxt's raw surface from Stone Tablet rows."""

    def __init__(
        self,
        rows_by_symbol: dict[str, list[list]],
        balances: Optional[dict[str, float]] = None,
        markets: Optional[dict[str, dict]] = None,
        fee_rate_by_symbol: Optional[dict[str, float]] = None,
        default_fee_rate: float = 0.006,
        tf_rows: Optional[dict[tuple, list[list]]] = None,
    ) -> None:
        # Rows are [ts_ms, open, high, low, close, volume], ms epoch on a 5m grid.
        self._rows: dict[str, list[list]] = {
            str(s): [list(r) for r in (rows or [])]
            for s, rows in (rows_by_symbol or {}).items()
        }
        self._cursor: dict[str, int] = {s: 0 for s in self._rows}
        # Higher-timeframe series keyed (symbol, timeframe);
        # fetch_ohlcv raises when one is missing.
        self._tf_rows: dict[tuple, list[list]] = {
            (str(k[0]), str(k[1])): [list(r) for r in v]
            for k, v in (tf_rows or {}).items()
        }
        self._tf_cursor: dict[tuple, int] = {k: 0 for k in self._tf_rows}
        self._balances: dict[str, float] = dict(balances or {})
        self._reserved: dict[str, float] = {}
        self._orders: dict[str, dict] = {}
        self._open: list[str] = []
        self._trades: list[dict] = []
        self._fee_by_symbol = dict(fee_rate_by_symbol or {})
        self._default_fee = float(default_fee_rate)
        self._opening_balances: dict[str, float] = dict(self._balances)
        # Every traded currency is listed, at zero if unheld, so
        # get_balance never marks it absent.
        for _sym in self._rows:
            _base, _sep, _quote = str(_sym).partition("/")
            if not _sep:
                continue
            self._balances.setdefault(_base.upper(), 0.0)
            self._balances.setdefault(_quote.upper(), 0.0)
        self._on_trade = None
        self._ticks = 0

        # The clock is the union of every tablet's timestamps, so tapes
        # with different start dates share one timeline.
        stamps: set = set()
        for rows in self._rows.values():
            for r in rows:
                stamps.add(int(r[0]))
        self._clock: list[int] = sorted(stamps)
        self._clock_i: int = 0

        self.markets: dict[str, dict] = dict(markets or {}) or {
            s: self._default_market(s) for s in self._rows
        }

    # -- market metadata ------------------------------------------------
    @staticmethod
    def _default_market(symbol: str) -> dict:
        """Return a ccxt market dict in the shape get_markets parses."""
        base, _, quote = str(symbol).partition("/")
        return {
            "id": str(symbol).replace("/", "-"),
            "symbol": str(symbol),
            "base": base,
            "quote": quote or "USD",
            "active": True,
            "limits": {"amount": {"min": 0.0}, "cost": {"min": 1.0}},
            "precision": {"price": 8, "amount": 8},
            "maker": 0.006,
            "taker": 0.012,
        }

    def market(self, symbol: str) -> dict:
        try:
            return self.markets[str(symbol)]
        except KeyError:
            raise ValueError(f"no market for {symbol!r}") from None

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        prec = int(self.market(symbol)["precision"]["amount"])
        # ccxt truncates rather than rounds; rounding up would submit
        # more than the caller sized.
        factor = 10**prec
        return f"{int(float(amount) * factor) / factor:.{prec}f}"

    def price_to_precision(self, symbol: str, price: float) -> str:
        prec = int(self.market(symbol)["precision"]["price"])
        return f"{float(price):.{prec}f}"

    # -- clock ----------------------------------------------------------
    def current_ts_ms(self) -> Optional[int]:
        if not self._clock or self._clock_i >= len(self._clock):
            return None
        return self._clock[self._clock_i]

    def has_data(self, symbol: str) -> bool:
        """Return True once the clock reaches this symbol's first candle."""
        rows = self._rows.get(str(symbol))
        ts = self.current_ts_ms()
        if not rows or ts is None:
            return False
        return int(ts) >= int(rows[0][0])

    def step(self) -> bool:
        """Advance one master timestamp. False when the tape is spent."""
        if self._clock_i + 1 >= len(self._clock):
            return False
        self._clock_i += 1
        target = self._clock[self._clock_i]
        for sym, rows in self._rows.items():
            i = self._cursor.get(sym, 0)
            while i + 1 < len(rows) and int(rows[i + 1][0]) <= target:
                i += 1
            self._cursor[sym] = i
        for key, rows in self._tf_rows.items():
            j = self._tf_cursor.get(key, 0)
            while j + 1 < len(rows) and int(rows[j + 1][0]) <= target:
                j += 1
            self._tf_cursor[key] = j
        self._ticks += 1
        self._sweep_open_orders()
        return True

    # -- replay control (used by the Simulator, never by a bot) ---------
    def total_clock_ticks(self) -> int:
        """Master timestamps in the tape, for progress reporting."""
        return len(self._clock)

    def ticks_elapsed(self) -> int:
        return self._ticks

    def clock_window(self) -> tuple[int | None, int | None]:
        """First and last master timestamp in ms, or (None, None) when empty."""
        if not self._clock:
            return (None, None)
        return (int(self._clock[0]), int(self._clock[-1]))

    def on_trade(self, callback) -> None:
        """Register a callback _settle invokes with each fill dict."""
        self._on_trade = callback

    def cursor_for(self, symbol: str) -> int:
        """Index of the candle currently visible for *symbol*."""
        return int(self._cursor.get(str(symbol), 0))

    def history(self, symbol: str, limit: int = 100) -> list[list]:
        """Visible rows for *symbol*, oldest-first, never past the cursor."""
        return [list(r) for r in self._visible(symbol)[-int(limit) :]]

    def symbols(self) -> list[str]:
        return sorted(self._rows)

    def balances(self) -> dict[str, float]:
        return dict(self._balances)

    def credit(self, currency: str, amount: float) -> None:
        """Add *amount* of *currency* to the ledger before the run starts."""
        self._adjust(str(currency), float(amount))

    def mark_opening_balances(self) -> None:
        """Freeze the post-seeding ledger as the run's starting point."""
        self._opening_balances = dict(self._balances)

    def snapshot(self) -> dict:
        """Ledger state for the Nuclear run report."""
        return {
            "balances": dict(self._balances),
            "opening_balances": dict(self._opening_balances),
            "trades": len(self._trades),
            "open_orders": len(self._open),
            "clock_ticks": self._ticks,
            "clock_ts_ms": self.current_ts_ms(),
        }

    def _visible(self, symbol: str) -> list[list]:
        """Rows up to and including the cursor — never beyond it."""
        sym = str(symbol)
        rows = self._rows.get(sym)
        if not rows:
            raise ValueError(f"no candles for {sym!r}")
        if not self.has_data(sym):
            raise TabletNotStarted(
                f"{sym} has no candle at master ts {self.current_ts_ms()}; "
                f"its tablet begins {int(rows[0][0])}"
            )
        return rows[: self._cursor.get(sym, 0) + 1]

    def _last_close(self, symbol: str) -> float:
        return float(self._visible(symbol)[-1][4])

    # -- ccxt: market data ----------------------------------------------
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[int] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list[list]:
        """Return the last *limit* visible rows for *symbol* at *timeframe*."""
        tf = str(timeframe or "").strip() or NATIVE_TIMEFRAME
        n = int(limit) if limit else DEFAULT_PAGE_SIZE
        if tf == NATIVE_TIMEFRAME:
            return [list(r) for r in self._visible(symbol)[-n:]]
        key = (str(symbol), tf)
        rows = self._tf_rows.get(key)
        if rows is None:
            raise ValueError(
                f"no {tf} series for {symbol!r}. Serving the native "
                f"{NATIVE_TIMEFRAME} series instead would make every "
                f"timeframe agree with itself; supply tf_rows[{key!r}]."
            )
        ts = self.current_ts_ms()
        if ts is None or not rows or int(ts) < int(rows[0][0]):
            raise TabletNotStarted(f"{symbol} {tf} series has not begun")
        return [list(r) for r in rows[: self._tf_cursor.get(key, 0) + 1][-n:]]

    def fetch_ticker(self, symbol: str, params: Optional[dict] = None) -> dict:
        rows = self._visible(symbol)
        last = float(rows[-1][4])
        ts = int(rows[-1][0])
        return {
            "symbol": str(symbol),
            "timestamp": ts,
            "last": last,
            "close": last,
            "bid": last,
            "ask": last,
            "high": float(rows[-1][2]),
            "low": float(rows[-1][3]),
            "baseVolume": float(rows[-1][5]),
            "quoteVolume": float(rows[-1][5]) * last,
            "info": {"sim_master_ts_ms": self.current_ts_ms()},
        }

    def fetch_tickers(
        self, symbols: Optional[list] = None, params: Optional[dict] = None
    ) -> dict:
        out: dict = {}
        for sym in symbols or list(self._rows):
            try:
                out[str(sym)] = self.fetch_ticker(sym)
            except (TabletNotStarted, ValueError):
                # A symbol whose tape has not opened is absent from the response.
                continue
        return out

    def fetch_order_book(
        self, symbol: str, limit: int = 20, params: Optional[dict] = None
    ) -> dict:
        px = self._last_close(symbol)
        return {
            "symbol": str(symbol),
            "bids": [[px, 1e9]],
            "asks": [[px, 1e9]],
            "timestamp": self.current_ts_ms(),
        }

    # -- ccxt: account --------------------------------------------------
    def fetch_balance(self, params: Optional[dict] = None) -> dict:
        """Return the ccxt balance shape: per-currency free/used/total plus mirrors."""
        out: dict = {"info": {}, "free": {}, "used": {}, "total": {}}
        for cur, total in self._balances.items():
            used = float(self._reserved.get(cur, 0.0))
            free = float(total) - used
            out[cur] = {"free": free, "used": used, "total": float(total)}
            out["free"][cur] = free
            out["used"][cur] = used
            out["total"][cur] = float(total)
        return out

    def _adjust(self, currency: str, delta: float) -> None:
        self._balances[currency] = self._balances.get(currency, 0.0) + delta

    def _fee_rate(self, symbol: str) -> float:
        return float(self._fee_by_symbol.get(str(symbol), self._default_fee))

    # -- ccxt: orders ---------------------------------------------------
    def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[dict] = None,
    ) -> dict:
        sym = str(symbol)
        px_now = self._last_close(sym)
        oid = f"sim_{uuid.uuid4().hex[:16]}"
        order = {
            "id": oid,
            "symbol": sym,
            "type": str(type),
            "side": str(side).lower(),
            "amount": float(amount),
            "price": float(price) if price is not None else None,
            "filled": 0.0,
            "remaining": float(amount),
            "average": None,
            "cost": 0.0,
            "status": "open",
            "fee": None,
            "timestamp": self.current_ts_ms(),
            # ccxt echoes venue params back on the order's info.
            "info": {"sim": True, "params": dict(params or {})},
            "clientOrderId": (params or {}).get("client_order_id"),
        }
        self._orders[oid] = order
        marketable = (
            str(type).lower() == "market"
            or price is None
            or (str(side).lower() == "buy" and float(price) >= px_now)
            or (str(side).lower() == "sell" and float(price) <= px_now)
        )
        if marketable:
            _px = px_now if str(type).lower() == "market" else float(price)
            if not self._settle(order, _px):
                # _settle moved no balance on the refusal, so
                # _shortfall re-reads the same wallet.
                raise InsufficientFunds(self._shortfall(order, _px))
        else:
            self._open.append(oid)
        return dict(order)

    def _shortfall(self, order: dict, fill_px: float) -> str:
        """Return why this order cannot settle, or "" when it can."""
        sym = order["symbol"]
        base, _, quote = sym.partition("/")
        amount = float(order["amount"])
        notional = amount * float(fill_px)
        fee = notional * self._fee_rate(sym)
        if order["side"] == "buy":
            have = float(self._balances.get(quote, 0.0))
            need = notional + fee
            if have < need:
                return (
                    f"{sym} buy {amount:.8f} at {fill_px:.8f} needs "
                    f"{need:.8f} {quote} (notional {notional:.8f} + fee "
                    f"{fee:.8f}) but the wallet holds {have:.8f} {quote}"
                )
            return ""
        have = float(self._balances.get(base, 0.0))
        if have < amount:
            return (
                f"{sym} sell {amount:.8f} needs {amount:.8f} {base} but "
                f"the wallet holds {have:.8f} {base}"
            )
        return ""

    def _settle(self, order: dict, fill_px: float) -> bool:
        """Fill *order* at *fill_px* and move the ledger, True when filled."""
        sym = order["symbol"]
        base, _, quote = sym.partition("/")
        amount = float(order["amount"])
        notional = amount * float(fill_px)
        fee = notional * self._fee_rate(sym)

        if self._shortfall(order, fill_px):
            order["status"] = "rejected"
            order["remaining"] = amount
            return False
        if order["side"] == "buy":
            self._adjust(quote, -(notional + fee))
            self._adjust(base, +amount)
        else:
            self._adjust(base, -amount)
            self._adjust(quote, +(notional - fee))

        order.update(
            {
                "status": "closed",
                "filled": amount,
                "remaining": 0.0,
                "average": float(fill_px),
                "price": order["price"] or float(fill_px),
                "cost": notional,
                "fee": {"cost": fee, "currency": quote, "rate": self._fee_rate(sym)},
            }
        )
        _t = {
            "id": f"t_{uuid.uuid4().hex[:12]}",
            "order": order["id"],
            "symbol": sym,
            "side": order["side"],
            "amount": amount,
            "price": float(fill_px),
            "cost": notional,
            "fee": {"cost": fee, "currency": quote},
            "timestamp": self.current_ts_ms(),
        }
        self._trades.append(_t)
        if self._on_trade is not None:
            try:
                self._on_trade(dict(_t))
            except Exception as exc:  # noqa: BLE001
                # The fill already moved the ledger, so an observer
                # error is logged, not raised.
                logger.warning(
                    "on_trade observer raised for %s fill: %s", _t.get("symbol"), exc
                )
        return True

    def _sweep_open_orders(self) -> None:
        """Fill resting orders the new candle crosses."""
        still: list[str] = []
        for oid in self._open:
            o = self._orders.get(oid)
            if o is None or o["status"] != "open":
                continue
            try:
                rows = self._visible(o["symbol"])
            except (TabletNotStarted, ValueError):
                still.append(oid)
                continue
            hi, lo = float(rows[-1][2]), float(rows[-1][3])
            px = float(o["price"]) if o["price"] is not None else None
            if px is None:
                still.append(oid)
                continue
            if (o["side"] == "buy" and lo <= px) or (o["side"] == "sell" and hi >= px):
                self._settle(o, px)
            else:
                still.append(oid)
        self._open = still

    def cancel_order(
        self,
        id: str,
        symbol: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> dict:
        o = self._orders.get(str(id))
        if o is None:
            raise ValueError(f"no such order {id!r}")
        if o["status"] == "open":
            o["status"] = "canceled"
            if str(id) in self._open:
                self._open.remove(str(id))
        return dict(o)

    def fetch_order(
        self,
        id: str,
        symbol: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> dict:
        o = self._orders.get(str(id))
        if o is None:
            raise ValueError(f"no such order {id!r}")
        return dict(o)

    def fetch_open_orders(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list[dict]:
        out = [dict(self._orders[i]) for i in self._open if i in self._orders]
        if symbol is not None:
            out = [o for o in out if o["symbol"] == str(symbol)]
        return out

    def fetch_my_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list[dict]:
        out = [dict(t) for t in self._trades]
        if symbol is not None:
            out = [t for t in out if t["symbol"] == str(symbol)]
        if since is not None:
            out = [t for t in out if int(t["timestamp"] or 0) >= int(since)]
        if limit:
            out = out[-int(limit) :]
        return out
