"""A ccxt-shaped exchange backed by Stone Tablets instead of the network.

Operator directive 2026-08-09: the Simulator must process Stone Tablet
and YTD data "in the exact same manner that Live Mode processes API
pulls from the exchange. It is just a different data source that I am
expecting you to handle in an identical, verifiable manner so that we
have a valid test environment on which to build."

WHY THIS SITS BELOW `CCXTConnector` AND NOT BESIDE IT
=====================================================
The Simulator previously satisfied that directive by RE-IMPLEMENTING the
connector. `FleetSimExchange` grew its own ticker, balance ledger, order
settlement, market metadata and fee arithmetic — a second implementation
of behaviour that already existed. Two implementations of one behaviour
cannot be held in agreement by inspection: a seam-by-seam audit found 16
divergences on fields the bot actually reads, and every one repaired only
reopens the moment live changes.

So this class does NOT implement the exchange interface. It implements
the raw `ccxt` surface — the 14 members `CCXTConnector` reaches through
its `_ex` property — and is attached via `connector.attach_backend()`.
Everything above that line is then the same code in both modes:
normalisation, `_parse_order`, fee reading, `AssetInfo` construction,
retry and rate-limit wrappers, and every documented ccxt quirk the bots
have been calibrated against.

THE QUIRK THAT MUST REPRODUCE, NOT BE RE-CODED
==============================================
`CCXTConnector.get_ohlcv` calls `fetch_ohlcv(symbol, timeframe, limit)`
— three positional arguments — against ccxt's real signature
`fetch_ohlcv(symbol, timeframe='1m', since=None, limit=None)`. The
requested limit therefore lands in the `since` slot and is never
applied; the exchange returns its own default page instead (Coinbase:
300). That defect is documented on `get_ohlcv` and is deliberately left
in place, because correcting it changes live TA and needs its own gated
cascade.

`fetch_ohlcv` below declares ccxt's real signature. It receives
`since=100, limit=None` from that call and returns a default page,
reproducing live's behaviour BY CONSTRUCTION. Nothing here special-cases
it, and when the defect is eventually fixed upstream this backend
follows automatically — which is the entire argument for putting the
seam here.

WHAT THIS OWNS AND WHAT IT DOES NOT
===================================
Owns: the replay clock, candle rows, balances, open orders, fills and
trade history — state and DATA.

Does not own: what any of it MEANS. No `Order`, no `Ticker`, no
`Balance`, no `AssetInfo` is constructed here. Those are the connector's
job, and letting this class build them would rebuild the divergence the
class exists to remove.

CAUSALITY. A live exchange cannot return a price stamped later than now.
Tablets in a fleet start on different dates, so a symbol whose tape has
not begun has NO price — `has_data()` reports that and the read methods
raise rather than serve row 0 from the symbol's own future.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

__all__ = ["TabletBackend", "TabletNotStarted"]

logger = logging.getLogger(__name__)

# Candles a page returns when the caller does not successfully specify a
# limit. Coinbase's default, and the value live actually receives on
# every call because of the `since`-slot defect described above.
DEFAULT_PAGE_SIZE = 300

NATIVE_TIMEFRAME = "5m"    # what the Stone Tablets store


class TabletNotStarted(Exception):
    """Raised when a symbol is read before its tablet begins.

    Deliberately an exception rather than an empty result. A silent
    empty would be indistinguishable from a quiet market, and the
    Simulator would keep ticking a bot that has no price — which is the
    exact defect this replaces.
    """


class TabletBackend:
    """Serves `ccxt`'s raw surface from Stone Tablet rows.

    Rows are `[ts_ms, open, high, low, close, volume]` exactly as the
    tablets store them, with `ts_ms` an int millisecond epoch on a fixed
    5m grid. Timestamps are passed through untouched — they are the
    ADDRESS a trade and a gate decision are keyed by, not a measurement
    to be re-typed.
    """

    def __init__(
        self,
        rows_by_symbol: dict[str, list[list]],
        balances: Optional[dict[str, float]] = None,
        markets: Optional[dict[str, dict]] = None,
        fee_rate_by_symbol: Optional[dict[str, float]] = None,
        default_fee_rate: float = 0.006,
        tf_rows: Optional[dict[tuple, list[list]]] = None,
    ) -> None:
        self._rows: dict[str, list[list]] = {
            str(s): [list(r) for r in (rows or [])]
            for s, rows in (rows_by_symbol or {}).items()}
        self._cursor: dict[str, int] = {s: 0 for s in self._rows}
        # Higher-timeframe series, keyed (symbol, timeframe). A request
        # for a timeframe with no series is an ERROR, not a fallback to
        # the native one -- serving 5m for a 1h request makes every
        # timeframe agree perfectly, which is not a signal, it is the
        # same signal counted N times, and it gates SCRUM.
        self._tf_rows: dict[tuple, list[list]] = {
            (str(k[0]), str(k[1])): [list(r) for r in v]
            for k, v in (tf_rows or {}).items()}
        self._tf_cursor: dict[tuple, int] = {k: 0 for k in self._tf_rows}
        self._balances: dict[str, float] = dict(balances or {})
        self._reserved: dict[str, float] = {}
        self._orders: dict[str, dict] = {}
        self._open: list[str] = []
        self._trades: list[dict] = []
        self._fee_by_symbol = dict(fee_rate_by_symbol or {})
        self._default_fee = float(default_fee_rate)
        self._opening_balances: dict[str, float] = dict(self._balances)
        # THE EXCHANGE REPORTS EVERY CURRENCY IT TRADES, INCLUDING THE
        # ONES THAT ARE ZERO.
        #
        # `FleetSimExchange`, which this class replaced in v3.24.84,
        # seeded both sides of every pair for exactly this reason:
        # "Seed every base + quote encountered so MEM-254's absent-side
        # handshake passes" (sim_exchange.py:130-136). The seeding was
        # not carried across, so `fetch_balance` reported only the quote
        # currencies the caller passed.
        #
        # WHAT THAT COST. `CCXTConnector.get_balance` marks a currency
        # the response OMITS as `absent=True` (ccxt_connector.py:1212),
        # and `ScrummingBot.tick` refuses to set `_initialised` on an
        # absent read (scrumming_bot.py:6664-6678). The refusal is
        # correct - two deterministic lies from the same filter still
        # agree - but here the read was not a lie, it was a currency the
        # backend simply never listed. So EVERY sim bot re-ran the init
        # handshake on EVERY tick, for ever, and no sim bot has been
        # initialised since v3.24.84.
        #
        # The handshake is two balance reads with `await
        # asyncio.sleep(0.25)` between them (scrumming_bot.py:6623).
        # Measured on a 50-candle 2-bot replay: 100 refusals, 25.73 s of
        # the run's 26.03 s spent in that sleep - 98.8%.
        #
        # `setdefault`, so a caller that states a currency keeps its
        # value; only the currencies the caller did not mention are
        # added, at zero. `_opening_balances` is captured ABOVE this
        # block so it still reflects the caller's intent rather than the
        # seeded scaffolding, which is what `FleetSimExchange` did too.
        for _sym in self._rows:
            _base, _sep, _quote = str(_sym).partition("/")
            if not _sep:
                continue
            self._balances.setdefault(_base.upper(), 0.0)
            self._balances.setdefault(_quote.upper(), 0.0)
        self._on_trade = None
        self._ticks = 0

        # The master clock is the UNION of every tablet's timestamps, so
        # a fleet whose tapes start on different dates advances on one
        # timeline. `has_data` is what keeps that from serving a price
        # before a symbol's tape opens.
        stamps: set = set()
        for rows in self._rows.values():
            for r in rows:
                stamps.add(int(r[0]))
        self._clock: list[int] = sorted(stamps)
        self._clock_i: int = 0

        self.markets: dict[str, dict] = dict(markets or {}) or {
            s: self._default_market(s) for s in self._rows}

    # -- market metadata ------------------------------------------------
    @staticmethod
    def _default_market(symbol: str) -> dict:
        """A ccxt market dict in the shape `get_markets` parses.

        Keys chosen to match what the connector actually reads:
        `active`, `base`, `quote`, `limits.amount.min`, `limits.cost.min`,
        `precision.price`, `precision.amount`, `maker`, `taker`.
        """
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
        # ccxt returns a STRING, and truncates rather than rounds. Both
        # matter: the connector re-floats the result, and rounding UP
        # here would submit more than the caller sized.
        factor = 10 ** prec
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
        """Has the clock reached this symbol's first candle?

        Stateless: a comparison of the clock against the tablet's first
        row, so it cannot drift out of step with the cursor the way a
        cached flag would.
        """
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

    def on_trade(self, callback) -> None:
        """Register a fill observer.

        The Simulator records every fill to its run log. Live gets the
        same information from the exchange's own trade stream, so this
        is replay plumbing, not a behavioural difference: no bot ever
        sees it.
        """
        self._on_trade = callback

    def cursor_for(self, symbol: str) -> int:
        """Index of the candle currently visible for *symbol*.

        Exposed instead of the raw series object so the Simulator can
        ask its question -- how far into this tape are we -- without
        reaching into private state and coupling to its shape.
        """
        return int(self._cursor.get(str(symbol), 0))

    def history(self, symbol: str, limit: int = 100) -> list[list]:
        """Visible rows for *symbol*, oldest-first, never past the cursor.

        The same data `fetch_ohlcv` serves, without the ccxt argument
        quirk -- this is for the Simulator's own observation pass, which
        is not pretending to be an exchange call.
        """
        return [list(r) for r in self._visible(symbol)[-int(limit):]]

    def symbols(self) -> list[str]:
        return sorted(self._rows)

    def balances(self) -> dict[str, float]:
        return dict(self._balances)

    def credit(self, currency: str, amount: float) -> None:
        """Seed a holding before the run starts.

        The Simulator opens each bot with the position bot_state says it
        already holds, which has to exist in the ledger or the first
        SELL fails a sufficiency check that live would have passed.
        """
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
                f"its tablet begins {int(rows[0][0])}")
        return rows[:self._cursor.get(sym, 0) + 1]

    def _last_close(self, symbol: str) -> float:
        return float(self._visible(symbol)[-1][4])

    # -- ccxt: market data ----------------------------------------------
    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m",
        since: Optional[int] = None, limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list[list]:
        """ccxt's real signature — see the module note on the quirk.

        `CCXTConnector.get_ohlcv` passes its limit positionally into
        `since`, so the common live call arrives here as
        `since=100, limit=None` and falls to the default page. That is
        live's actual behaviour, reproduced without being re-coded.
        """
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
                f"timeframe agree with itself; supply tf_rows[{key!r}].")
        ts = self.current_ts_ms()
        if ts is None or not rows or int(ts) < int(rows[0][0]):
            raise TabletNotStarted(f"{symbol} {tf} series has not begun")
        return [list(r) for r in rows[:self._tf_cursor.get(key, 0) + 1][-n:]]

    def fetch_ticker(self, symbol: str,
                     params: Optional[dict] = None) -> dict:
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

    def fetch_tickers(self, symbols: Optional[list] = None,
                      params: Optional[dict] = None) -> dict:
        out: dict = {}
        for sym in (symbols or list(self._rows)):
            try:
                out[str(sym)] = self.fetch_ticker(sym)
            except (TabletNotStarted, ValueError):
                # A symbol whose tape has not opened is absent from the
                # response, which is what a real exchange returns for a
                # symbol it has no data for.
                continue
        return out

    def fetch_order_book(self, symbol: str, limit: int = 20,
                         params: Optional[dict] = None) -> dict:
        px = self._last_close(symbol)
        return {"symbol": str(symbol), "bids": [[px, 1e9]],
                "asks": [[px, 1e9]], "timestamp": self.current_ts_ms()}

    # -- ccxt: account --------------------------------------------------
    def fetch_balance(self, params: Optional[dict] = None) -> dict:
        """ccxt balance shape: per-currency free/used/total plus mirrors."""
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
        self, symbol: str, type: str, side: str,  # noqa: A002 - ccxt name
        amount: float, price: Optional[float] = None,
        params: Optional[dict] = None,
    ) -> dict:
        sym = str(symbol)
        px_now = self._last_close(sym)
        oid = f"sim_{uuid.uuid4().hex[:16]}"
        order = {
            "id": oid, "symbol": sym, "type": str(type),
            "side": str(side).lower(), "amount": float(amount),
            "price": float(price) if price is not None else None,
            "filled": 0.0, "remaining": float(amount), "average": None,
            "cost": 0.0, "status": "open", "fee": None,
            "timestamp": self.current_ts_ms(),
            # ccxt echoes venue params back on the order's `info`. The
            # connector sends client_order_id here, and dropping it
            # would make sim orders untraceable in a way live ones are
            # not.
            "info": {"sim": True, "params": dict(params or {})},
            "clientOrderId": (params or {}).get("client_order_id"),
        }
        self._orders[oid] = order
        marketable = (
            str(type).lower() == "market"
            or price is None
            or (str(side).lower() == "buy" and float(price) >= px_now)
            or (str(side).lower() == "sell" and float(price) <= px_now))
        if marketable:
            self._settle(order, px_now if str(type).lower() == "market"
                         else float(price))
        else:
            self._open.append(oid)
        return dict(order)

    def _settle(self, order: dict, fill_px: float) -> None:
        """Fill an order and move the ledger.

        The FEE is written onto the order in ccxt's nested shape,
        because that is where the connector reads it from:
        `raw.get("fee", {}).get("cost")`. The Simulator computing a fee
        and stashing it somewhere else is how sim and live diverged on
        this field before.
        """
        sym = order["symbol"]
        base, _, quote = sym.partition("/")
        amount = float(order["amount"])
        notional = amount * float(fill_px)
        fee = notional * self._fee_rate(sym)

        if order["side"] == "buy":
            if self._balances.get(quote, 0.0) < notional + fee:
                order["status"] = "rejected"
                order["remaining"] = amount
                return
            self._adjust(quote, -(notional + fee))
            self._adjust(base, +amount)
        else:
            if self._balances.get(base, 0.0) < amount:
                order["status"] = "rejected"
                order["remaining"] = amount
                return
            self._adjust(base, -amount)
            self._adjust(quote, +(notional - fee))

        order.update({
            "status": "closed", "filled": amount, "remaining": 0.0,
            "average": float(fill_px), "price": order["price"] or float(fill_px),
            "cost": notional,
            "fee": {"cost": fee, "currency": quote,
                    "rate": self._fee_rate(sym)},
        })
        _t = {
            "id": f"t_{uuid.uuid4().hex[:12]}", "order": order["id"],
            "symbol": sym, "side": order["side"], "amount": amount,
            "price": float(fill_px), "cost": notional,
            "fee": {"cost": fee, "currency": quote},
            "timestamp": self.current_ts_ms(),
        }
        self._trades.append(_t)
        if self._on_trade is not None:
            try:
                self._on_trade(dict(_t))
            except Exception as exc:  # noqa: BLE001 - must not break a fill
                # A fill is real whether or not the observer survives
                # it, so this cannot raise -- but a silently dead
                # observer means the run log quietly stops recording
                # trades, which reads as "no trades happened".
                logger.warning(
                    "on_trade observer raised for %s fill: %s",
                    _t.get("symbol"), exc)

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
            if (o["side"] == "buy" and lo <= px) or (
                    o["side"] == "sell" and hi >= px):
                self._settle(o, px)
            else:
                still.append(oid)
        self._open = still

    def cancel_order(self, id: str, symbol: Optional[str] = None,  # noqa: A002
                     params: Optional[dict] = None) -> dict:
        o = self._orders.get(str(id))
        if o is None:
            raise ValueError(f"no such order {id!r}")
        if o["status"] == "open":
            o["status"] = "canceled"
            if str(id) in self._open:
                self._open.remove(str(id))
        return dict(o)

    def fetch_order(self, id: str, symbol: Optional[str] = None,  # noqa: A002
                    params: Optional[dict] = None) -> dict:
        o = self._orders.get(str(id))
        if o is None:
            raise ValueError(f"no such order {id!r}")
        return dict(o)

    def fetch_open_orders(self, symbol: Optional[str] = None,
                          since: Optional[int] = None,
                          limit: Optional[int] = None,
                          params: Optional[dict] = None) -> list[dict]:
        out = [dict(self._orders[i]) for i in self._open
               if i in self._orders]
        if symbol is not None:
            out = [o for o in out if o["symbol"] == str(symbol)]
        return out

    def fetch_my_trades(
        self, symbol: Optional[str] = None,
        since: Optional[int] = None, limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list[dict]:
        out = [dict(t) for t in self._trades]
        if symbol is not None:
            out = [t for t in out if t["symbol"] == str(symbol)]
        if since is not None:
            out = [t for t in out if int(t["timestamp"] or 0) >= int(since)]
        if limit:
            out = out[-int(limit):]
        return out
