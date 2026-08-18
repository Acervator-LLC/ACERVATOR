"""sim_exchange.py — Fleet Replay simulated exchange.

Serves REAL symbols (BTC/USD, ETH/USD, CHIP/USD, …) from per-symbol
CandleSeries. Contrast with the retired NuclearSimExchange which
tied the exchange to TAPEA/TAPEB synthetic tokens (that architecture
was fine for stress cycling one tape but incompatible with running
the actual live fleet against actual YTD data).

Order execution model (v3.23.72 MVP):
    * MARKET  → fills at current candle close
    * LIMIT   → fills at the specified price IF the cursor's candle
      swept through it (buy: candle low ≤ price; sell: candle high
      ≥ price). Otherwise the order stays open until the sweep or
      cancel_order.

Balance ledger + fee accounting follow the retired
NuclearSimExchange pattern (sound piece isolated per operator
directive 2026-07-31).

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from ....exchange.base import (
    AssetInfo, Balance, ExchangeInterface,
    Order, OrderBook, OrderSide, OrderStatus, OrderType, Ticker, Trade,
)
from .candle_series import CandleSeries

logger = logging.getLogger("acervator.simulator.fleet.sim_exchange")


def make_symbol_series_map(
    symbol_rows: dict[str, list[list[float]]],
) -> dict[str, CandleSeries]:
    """Convenience: build ``{symbol: CandleSeries}`` from raw
    ``{symbol: rows}`` (matches the shape History-Refresh + OHLCV
    fetchers already produce)."""
    from .candle_series import build_candle_series_from_rows
    return {
        symbol: build_candle_series_from_rows(symbol, rows)
        for symbol, rows in (symbol_rows or {}).items()}


# v3.24.83 — mirrors `ccxt_connector.EFFECTIVE_OHLCV_PAGE_SIZE`.
#
# DUPLICATED ON PURPOSE. The Simulator does not import from the live
# exchange layer. `test_sim_live_ohlcv_parity.py` asserts the two
# constants are equal, so the duplication cannot drift silently — the
# test is the bridge, not the code.
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

    # v3.24.64 (C18) — the interval the tape is stored at. Mirrors
    # stone_tablets.registry.NATIVE_TIMEFRAME; every other timeframe is
    # a deterministic roll-up of this one, so this is the series that
    # always exists and the only one the master clock is built from.
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
                f"CandleSeries, got {type(series_map).__name__}")
        self._series: dict[str, CandleSeries] = dict(series_map)
        # v3.24.64 (C18 / SN-1) — optional per-(symbol, timeframe)
        # series. The native map above stays authoritative for the
        # master clock: rollup buckets can begin before the first native
        # candle, and a clock built from their union would gain ticks no
        # native candle backs.
        self._tf_series: dict[tuple, CandleSeries] = {}
        self._tf_fallback_warned: set = set()
        self._fee_pct = float(fee_pct)
        # v3.24.32 — PER-SYMBOL fees, as FRACTIONS.
        #
        # One exchange-wide rate cannot represent the live fleet: 24 of
        # 35 bots pay 1.6% and 11 pay 0.6%. Previously fee_pct was 0.0
        # and the sim charged nothing at all, biasing the accumulation
        # curve upward on every single trade — measured at $122.99
        # uncharged across 510 fills / $7,687.18 notional in one run.
        #
        # UNIT TRAP: values here are FRACTIONS (0.016), while
        # BotConfig.trading_fee_pct is a PERCENT (1.6) consumed as
        # `_eff_pct / 100.0` at scrumming_bot.py:10021. The caller
        # converts; passing a percent straight in would charge 160%.
        self._fee_pct_by_symbol: dict[str, float] = {
            str(k): float(v) for k, v in (fee_pct_by_symbol or {}).items()}
        self._exchange_id = exchange_id
        self._connected = False
        # Balance ledger: currency → free amount. Missing = zero.
        self._balances: dict[str, float] = dict(starting_balances or {})
        # v3.24.26 — immutable snapshot of what the wallet opened with.
        # `_balances` mutates as the replay trades, so without this a
        # caller cannot answer "what did this run actually change?" —
        # which is the only question an accumulation backtest asks.
        # Captured before the base/quote seeding below so it reflects
        # the caller's intent, not the seeded scaffolding.
        self._opening_balances: dict[str, float] = dict(
            starting_balances or {})
        # Seed every base + quote encountered so MEM-254's
        # absent-side handshake passes.
        for sym in self._series:
            if "/" not in sym:
                continue
            base, quote = sym.split("/", 1)
            self._balances.setdefault(base.upper(), 0.0)
            self._balances.setdefault(quote.upper(), 0.0)
        # Order book (id → Order). Open + closed both retained so
        # get_order() can look up recent history.
        self._orders: dict[str, Order] = {}
        # v3.24.20 — index of OPEN orders by symbol.
        #
        # _sweep_open_limit_orders used to walk list(self._orders.values())
        # on every candle step. self._orders never shrinks — filled and
        # cancelled orders stay in it for get_my_trades / get_order — so
        # the sweep was O(every order ever placed) per candle, i.e.
        # quadratic in trade count over a run, plus a full list() copy
        # each time.
        #
        # This index holds only orders that are actually fillable, so the
        # sweep is O(open orders for the symbol). It must be kept in sync
        # at all three status transitions: creation (place_order), fill
        # (_settle_fill) and cancellation (cancel_order).
        self._open_by_symbol: dict[str, set[str]] = {}
        # Trade tape (list of Trade). Sim's parity output.
        self._trades: list[Trade] = []
        # Optional callback fired every time a trade is executed —
        # used by the FleetReplayController to update a live counter.
        self._on_trade = None
        # v3.24.3 — master clock. Union of every series's timestamps
        # sorted ascending. Fleet controller's tick loop advances the
        # clock; step() applies the current master timestamp to every
        # series so they hold synchronized wall-clock time even when
        # their coverage lengths / start offsets differ. Prior
        # index-based stepping produced 15-65 minute drift between
        # series (verified: ALLO/USDC drifts 3900s from BTC/USD when
        # both stepped 100 indices).
        from .master_clock import MasterClock
        self._master_clock = MasterClock.from_series(
            self._series.values())

    def fee_for(self, symbol: str) -> float:
        """Fee FRACTION for one symbol, falling back to the default.

        Per-symbol because the live fleet is not uniform: 24 of 35 bots
        pay 1.6% and 11 pay 0.6%, so a single exchange-wide rate would
        misprice most of the fleet either way.
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
    async def connect(self, api_key: str, api_secret: str,
                      passphrase: str = "") -> None:
        del api_key, api_secret, passphrase
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    # ─── Cursor control (called by the replay controller) ────────
    def step(self) -> bool:
        """v3.24.3 — advance the master clock one timestamp; every
        series moves its cursor to the candle whose ts <= the master
        timestamp.

        v3.24.83 — THE CAUSALITY CLAIM THAT USED TO BE HERE WAS FALSE.

        It read: "Series without a candle at that ts hold their previous
        candle (last-seen price, no future data — causal)."

        A series that has not STARTED has no previous candle to hold.
        `step_to_ts` returns False and leaves the cursor at 0 when the
        master timestamp precedes the series' first candle, and this
        method discarded that bool — so the series served `rows[0]`, its
        FIRST candle, which is stamped AFTER the master clock.

        The master clock is the UNION of every series' timestamps, so it
        begins at the earliest tablet in the fleet. On the operator's
        fleet 13 of 35 symbols start later than that: GROVE's tablet
        begins 2026-07-06 against a union origin of 2026-01-01, so it
        had a 186-day lead-in during which every tick served a price
        from its own future.

        A live exchange cannot do this. That is the whole point of the
        Simulator being a valid test environment, so the bool is now
        honoured and `has_data()` exposes the condition to the caller.

        Returns False when the master clock is exhausted."""
        if not self._master_clock.step():
            return False
        target_ts = self._master_clock.current_ts_ms()
        if target_ts is None:
            return False
        for series in self._series.values():
            # Return value deliberately not discarded any more; the
            # causal state it reports is what `has_data` publishes.
            series.step_to_ts(target_ts)
        # After the price step, sweep the open limit orders — any that
        # the new candle crosses should fill now, before the next tick.
        self._sweep_open_limit_orders()
        return True

    @property
    def master_clock(self):
        """v3.24.3 — expose read-only clock for progress reporting."""
        return self._master_clock

    def total_clock_ticks(self) -> int:
        """v3.24.3 — union-size total ticks the sim will play."""
        return self._master_clock.total

    def has_data(self, symbol: str) -> bool:
        """Has the master clock reached this symbol's first candle?

        The causal question a live exchange never has to answer: before
        a symbol's tablet begins there is no price to serve, because no
        price EXISTED yet. Callers must not run a bot on a symbol for
        which this is False — its series is parked on a candle from the
        future.

        Stateless on purpose. The condition is a pure comparison of the
        master timestamp against the series' first row, so it cannot
        drift out of sync with the cursor the way a cached "started"
        flag would.
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
            raise ValueError(
                f"FleetSimExchange.get_ticker: unknown symbol {symbol!r}")
        cur = series.get_current()
        if cur is None:
            raise RuntimeError(
                f"FleetSimExchange.get_ticker: no candle data for "
                f"{symbol!r}")
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
                f"FleetSimExchange.get_orderbook: unknown symbol {symbol!r}")
        cur = series.get_current()
        if cur is None:
            raise RuntimeError(
                f"FleetSimExchange.get_orderbook: no data for {symbol!r}")
        close = float(cur[4])
        step = max(1e-9, close * 0.001)
        bids = [(close - step * (i + 1), 100.0) for i in range(limit)]
        asks = [(close + step * (i + 1), 100.0) for i in range(limit)]
        return OrderBook(
            symbol=symbol, bids=bids, asks=asks, timestamp=time.time())

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100,
    ) -> list[list[float]]:
        # v3.24.64 (C18 / SN-1) — the timeframe is HONOURED.
        #
        # This used to `del timeframe` and serve one series per symbol,
        # so all six phantoms read the IDENTICAL 5m sequence into
        # get_higher_tf_bias. Six timeframes agreeing perfectly is not a
        # signal; it is the same signal counted six times, and it gates
        # SCRUM.
        #
        # `_tf_series` is populated per (symbol, timeframe) when the run
        # is built. A timeframe with no series falls back to the native
        # one EXPLICITLY and says so, rather than silently pretending a
        # 4h read succeeded.
        _tf = str(timeframe or "").strip() or self.NATIVE_TIMEFRAME
        series = None
        _tf_map = getattr(self, "_tf_series", None)
        if _tf_map:
            series = _tf_map.get((symbol, _tf))
        if series is None:
            series = self._series.get(symbol)
            if series is not None and _tf != self.NATIVE_TIMEFRAME:
                # Once per (symbol, tf): a silent fallback here is how
                # six phantoms end up agreeing again.
                _seen = self._tf_fallback_warned
                if (symbol, _tf) not in _seen:
                    _seen.add((symbol, _tf))
                    logger.warning(
                        "FleetSimExchange: no %s series for %s; serving "
                        "the native %s series. Higher-timeframe TA for "
                        "this symbol is NOT independent.",
                        _tf, symbol, self.NATIVE_TIMEFRAME)
        if series is None:
            raise ValueError(
                f"FleetSimExchange.get_ohlcv: unknown symbol {symbol!r}")
        # v3.24.20 — the per-row copy that used to wrap this call is
        # gone. ``get_history`` already builds fresh lists
        # (``[list(r) for r in self.rows[start:end]]``), so mapping
        # ``_ohlcv_row_from_series`` — itself just ``list(row)`` — over
        # the result copied 100 freshly-allocated lists into 100 more.
        #
        # That was 200 list allocations per bot per candle; across a
        # 35-bot / ~15,000-candle replay, ~105 million.
        #
        # The removed copy protected nothing: the lists returned by
        # get_history are already private to this call, and the
        # defensive copy that guards the immutable series against caller
        # mutation is the one INSIDE get_history, which stays.
        # v3.24.83 — SERVE WHAT LIVE ACTUALLY SERVES, NOT WHAT WAS ASKED.
        #
        # Operator directive 2026-08-09: "the Simulator needs to process
        # Stone Tablet and YTD data in the exact same manner that Live
        # Mode processes API pulls from the exchange... just a different
        # data source... in an identical, verifiable manner."
        #
        # Live never honours `limit`. `CCXTConnector.get_ohlcv` passes it
        # into ccxt's `since` slot, so the exchange returns its own
        # default page size — 300 on Coinbase — for every live call.
        # `ScrummingBot` asks for 100 at scrumming_bot.py:6223 and
        # receives 300.
        #
        # Honouring `limit` here made the Simulator feed TA 100 candles
        # where live feeds 300. That is not a smaller sample of the same
        # thing: Heikin-Ashi is a forward recurrence seeded at index 0
        # and EMA is SMA-seeded, so the window length changes the seed
        # and therefore every downstream value. MEASURED across 12 fleet
        # symbols, 288 windows: the TA consensus DIRECTION differed on
        # 1.4% of them, and net_score differed on nearly all.
        #
        # A replay that feeds a different window than live cannot be
        # used to check whether a gate latches the same way, which is
        # the Simulator's entire purpose.
        #
        # `limit` stays in the signature because the live one has it and
        # the two must stay swappable.
        return series.get_history(limit=LIVE_EFFECTIVE_PAGE_SIZE)

    # ─── Account ─────────────────────────────────────────────────
    async def get_balances(self) -> dict[str, Balance]:
        return {
            cur: Balance(currency=cur, free=float(free),
                         used=0.0, total=float(free), absent=False)
            for cur, free in self._balances.items()}

    async def get_balance(self, currency: str) -> Balance:
        free = float(self._balances.get(currency, 0.0))
        absent = currency not in self._balances
        return Balance(
            currency=currency, free=free, used=0.0,
            total=free, absent=absent)

    # ─── Orders ──────────────────────────────────────────────────
    def _adjust_balance(self, currency: str, delta: float) -> None:
        self._balances[currency] = float(
            self._balances.get(currency, 0.0)) + float(delta)

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
                f"got {amount!r}")
        series = self._series.get(symbol)
        if series is None:
            raise ValueError(
                f"FleetSimExchange.place_order: unknown symbol {symbol!r}")
        cur = series.get_current()
        if cur is None:
            raise RuntimeError(
                f"FleetSimExchange.place_order: no candle data for "
                f"{symbol!r}")
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
                raise ValueError(
                    "FleetSimExchange.place_order: LIMIT requires price")
            fill_price = float(price)
            # If the current candle already sweeps this price, fill now.
            candle_low = float(cur[3])
            candle_high = float(cur[2])
            crosses = (
                (side == OrderSide.BUY and candle_low <= fill_price)
                or (side == OrderSide.SELL and candle_high >= fill_price))
            if crosses:
                self._settle_fill(order, fill_price, base, quote)
            # else: order stays OPEN until _sweep_open_limit_orders
        elif order_type == OrderType.IOC_LIMIT:
            # v3.24.67 (C19 / SN-21) — Immediate-or-Cancel.
            #
            # This used to hit the `else` below and abort the run with
            # "unsupported type", so a bot in AGGRESSIVE mode could not
            # be replayed in Fleet at all. That is not a Stack Mode
            # dependency as the cascade plan says: `scrumming_bot.py`
            # already selects IOC_LIMIT whenever Aggressive is on, so
            # this is a shipped feature the harness could not run.
            #
            # Semantics: the LIMIT crosses test, plus the one difference
            # that DEFINES the type — it never rests. An IOC that rests
            # is a LIMIT, and a simulator that converts one into the
            # other tells the operator their taker-forcing order got a
            # maker fill.
            if price is None:
                raise ValueError(
                    "FleetSimExchange.place_order: IOC_LIMIT requires "
                    "price")
            _limit = float(price)
            _low = float(cur[3])
            _high = float(cur[2])
            _close = float(cur[4])
            _crosses = (
                (side == OrderSide.BUY and _low <= _limit)
                or (side == OrderSide.SELL and _high >= _limit))
            if _crosses:
                # min/max, matching NuclearSimExchange: the limit is a
                # ceiling for a BUY and a floor for a SELL, but a fill
                # must not be WORSE than the market actually was.
                _fp = (min(_limit, _close) if side == OrderSide.BUY
                       else max(_limit, _close))
                self._settle_fill(order, _fp, base, quote)
            else:
                order.status = OrderStatus.CANCELLED
                order.filled = 0.0
                order.remaining = float(amount)
        else:
            raise ValueError(
                f"FleetSimExchange.place_order: unsupported type "
                f"{order_type!r}")

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
        """v3.24.17 — ``NNNNNN_TICKER`` for the candle under the
        cursor. Empty string when it cannot be resolved; the fill
        still records, it just carries no address rather than a
        wrong one."""
        idx = self._cursor_index(symbol)
        if idx is None:
            return ""
        try:
            from src.trading.stone_tablets.addressing import (
                format_address, ticker_from_symbol)
            return format_address(ticker_from_symbol(symbol), idx)
        except Exception as exc:  # noqa: BLE001 - addressing is advisory
            logger.debug(
                "candle address unavailable for %s@%s: %s",
                symbol, idx, exc)
            return ""

    def _settle_fill(
        self, order: Order, fill_price: float,
        base: str, quote: str,
    ) -> None:
        amount = float(order.amount)
        notional = amount * fill_price
        fee = notional * self.fee_for(order.symbol)
        # v3.24.66 (C19 / SN-17) — sufficiency precondition.
        #
        # Placed HERE rather than in place_order because this is the
        # single mutation choke point: all three settle paths (MARKET,
        # LIMIT-crosses, and the open-order sweep) funnel through it. A
        # guard at the entry points would have to be written three times
        # and would miss the sweep, which settles orders placed on an
        # earlier tick when the balance may since have been spent.
        #
        # `_adjust_balance` is plain addition with no floor, so before
        # this a BUY with no quote currency settled and drove the
        # balance negative, and a SELL of coins never held settled too.
        # Every downstream sim number is denominated in this ledger, so
        # the run did not fail — it reported P&L against an impossible
        # starting position.
        #
        # 1e-12 tolerance admits an EXACTLY funded order; without it
        # float error would silently suppress the last trade of many
        # runs. Matches NuclearSimExchange.place_order so the two venues
        # cannot disagree about what is affordable.
        _need_ccy, _need_qty, _have = (
            (quote, notional + fee, self._balances.get(quote, 0.0))
            if order.side == OrderSide.BUY
            else (base, amount, self._balances.get(base, 0.0)))
        if float(_have) + 1e-12 < float(_need_qty):
            raise ValueError(
                f"FleetSimExchange._settle_fill: insufficient "
                f"{_need_ccy} for {order.symbol} — need "
                f"{_need_qty:.10g}, have {float(_have):.10g}. Refusing "
                f"rather than settling a trade the ledger cannot fund.")
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
        # v3.24.5 — timestamp = master-clock sim time (not wall).
        # Parity harness compares sim trades to live trades by ts;
        # using wall-clock made every sim trade timestamped "now"
        # regardless of what SIM tick it fired on, so parity was
        # unmeasurable. Master-clock ts is in ms since epoch (same
        # units as live trade.timestamp), converted to seconds
        # here to match the Trade dataclass convention.
        _sim_ts_ms = self._master_clock.current_ts_ms()
        _sim_ts_s = (float(_sim_ts_ms) / 1000.0
                     if _sim_ts_ms is not None else time.time())
        # v3.24.17 — stamp the Stone Tablet candle address on every
        # fill. Operator directive 2026-08-03: fills should be tied to
        # the "expected Stone Tablet Candle Address" so a sim trade is
        # traceable to the exact candle it fired on.
        #
        # SimRunLog.record_trade already accepted candle_address, but
        # nothing ever supplied one, so the field was empty on every
        # persisted sim trade — the address existed as a parameter and
        # not as data.
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
            raw={"order_id": order.id,
                 "sim_master_ts_ms": _sim_ts_ms,
                 "candle_address": _addr,
                 "candle_index": self._cursor_index(order.symbol)},
        )
        # v3.24.83 — THE ORDER CARRIES THE SAME FILL FACTS AS LIVE.
        #
        # Operator directive 2026-08-09: "If the code is not bit
        # identical to live and only varies by calling the Stone Tablets
        # and YTD as its source of data, you have failed."
        #
        # The fee was already computed correctly above and stamped on
        # the Trade; the Order was left with `fee`, `fee_currency` and
        # `raw` at their defaults while `CCXTConnector` populates all
        # three on every live order. "Nothing reads them yet" is not a
        # reason to leave them empty — it just means the divergence has
        # not been noticed yet.
        order.fee = fee
        order.fee_currency = quote
        order.raw = {"order_id": order.id,
                     "sim_master_ts_ms": _sim_ts_ms,
                     "candle_address": _addr,
                     "candle_index": self._cursor_index(order.symbol),
                     "fill_price": fill_price,
                     "notional": notional}
        self._trades.append(trade)
        if self._on_trade is not None:
            try:
                self._on_trade(trade)
            except Exception as _cb_exc:  # noqa: BLE001 - callback surface
                logger.debug(
                    "FleetSimExchange on_trade cb raised: %s", _cb_exc)

    def _sweep_open_limit_orders(
        self, only_symbol: Optional[str] = None,
    ) -> int:
        """Fill any open LIMIT orders that the current candle sweeps.
        Returns count filled."""
        filled = 0
        # v3.24.20 — walk only the open index, not every order ever
        # placed. Symbols are resolved first so a fill mutating
        # _open_by_symbol mid-iteration cannot invalidate the loop.
        if only_symbol is not None:
            symbols = ([only_symbol]
                       if only_symbol in self._open_by_symbol else [])
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
            crosses = (
                (order.side == OrderSide.BUY and candle_low <= order.price)
                or (order.side == OrderSide.SELL
                    and candle_high >= order.price))
            if not crosses:
                continue
            base, quote = order.symbol.split("/", 1)
            self._settle_fill(order, float(order.price), base.upper(),
                              quote.upper())
            filled += 1
        return filled

    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        del symbol
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(
                f"FleetSimExchange.cancel_order: unknown order {order_id!r}")
        if order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELLED
            self._unmark_open(order)
        return order

    async def get_order(self, order_id: str, symbol: str) -> Order:
        del symbol
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(
                f"FleetSimExchange.get_order: unknown order {order_id!r}")
        return order

    async def get_open_orders(
        self, symbol: Optional[str] = None,
    ) -> list[Order]:
        return [
            o for o in self._orders.values()
            if o.status == OrderStatus.OPEN
            and (symbol is None or o.symbol == symbol)]

    async def get_my_trades(
        self, symbol: str,
        since: Optional[float] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list:
        # v3.24.17 — accept `params` for call-signature parity with
        # the CCXT connector. ScrummingBot.sync_ytd_trade_count
        # passes params={"paginate": True, "until": ...}; without
        # this the call raised TypeError on EVERY bot on EVERY sync,
        # so sim trade counts never populated and each run emitted
        # 35 identical failures. The sim has no pagination — one
        # in-memory list — so the value is deliberately ignored
        # rather than partially honoured.
        del params
        out = [t for t in self._trades if t.symbol == symbol]
        if since is not None:
            out = [t for t in out if t.timestamp >= float(since)]
        if limit is not None:
            out = out[-int(limit):]
        return out

    # ─── Discovery ───────────────────────────────────────────────
    async def get_markets(self) -> list[AssetInfo]:
        out: list[AssetInfo] = []
        for sym in sorted(self._series.keys()):
            if "/" not in sym:
                continue
            base, quote = sym.split("/", 1)
            out.append(AssetInfo(
                symbol=sym, base=base.upper(), quote=quote.upper(),
                # v3.24.68 (C19 / SN-20) — PLACEHOLDER, not real venue
                # limits. Real per-symbol limits are not available
                # offline; nothing persists a captured copy, so serving
                # them needs a capture step that does not exist.
                # NuclearSimExchange carries the same values so the two
                # harnesses cannot report different trade counts for the
                # same strategy. Keep them in step.
                min_amount=1e-8, min_cost=1.0,
                amount_precision=8, price_precision=8,
                maker_fee=0.0, taker_fee=0.0, active=True))
        return out

    async def get_asset_logo_url(self, currency: str) -> str:
        del currency
        return ""


__all__ = ["FleetSimExchange", "make_symbol_series_map"]
