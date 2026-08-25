"""
src/gui/simulator_tab/nuclear_sim_exchange.py — Sim exchange adapter.

v3.18.8 (Phase B revision) — REWRITTEN per operator directive 2026-05-20:
ticker associations dropped. The exchange now maps SYNTHETIC base
currencies (TAPEA, TAPEB, TAPEC, ...) to NuclearCandleSource tape ids.
The bot trades a symbol like ``TAPEA/USD`` without ever knowing that
the underlying candle stream is real BTC 2023 data being played
forward-reverse-forward indefinitely.

This is the key conceptual change from v3.18.7:
  before  bot.exchange.get_ticker("BTC/USD")   — exchange tied to ticker
   now    bot.exchange.get_ticker("TAPEA/USD") — exchange tied to a tape

Tape IDs A/B/C... come from ``NuclearCandleSource.list_tapes()``.
The exchange is constructed with the set of tape ids it should serve,
and it auto-builds the synthetic-base ↔ tape_id mapping at construction.

R28 FL — unknown symbols, zero balances and negative amounts all raise
loud exceptions rather than silently failing.

A note on that line, because it was false for a long time. Until
v3.24.65 it claimed the zero-balance guarantee while `_adjust_balance`
was plain addition with no floor: a BUY with no quote currency settled
and drove the balance negative, and the constructor deliberately SEEDS
zero balances. v3.24.65 corrected the CLAIM (the code fix was C19's
SN-17 and rode separately); v3.24.66 added the precondition, so the
guarantee is now true and the claim is restored.

Both halves are pinned by tests/test_nuclear_limit_fill_price.py, which
asserts the docstring and the behaviour together — a docstring that
overstates its guarantees is worse than none, because the next cold
read trusts it instead of re-deriving.
"""

from __future__ import annotations

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

from .nuclear_candle_source import NuclearCandleSource


# ---------------------------------------------------------------------------
# Synthetic base / quote prefix helpers
# ---------------------------------------------------------------------------
# The bot's BotConfig.symbol is "BASE/QUOTE" where BASE is the asset.
# We name the synthetic base "TAPEA", "TAPEB", ... so:
#   bot.config.target_asset    = "TAPEA"   (a string token, not a real coin)
#   bot.config.base_currency   = "USD"     (the operator's seed pool)
#   bot.config.symbol          = "TAPEA/USD"
# Inside the exchange the "TAPEA" base resolves to candle source tape "A".
def _tape_id_to_base(tape_id: str) -> str:
    return f"TAPE{tape_id}"


def _base_to_tape_id(base: str) -> Optional[str]:
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
    """Simulated exchange backed by NuclearCandleSource tapes.

    Construction:
        src = NuclearCandleSource()
        # Wire tapes A and B so the exchange serves both.
        src.wire("A")
        src.wire("B")
        ex  = NuclearSimExchange(src, quote_balance={"USD": 200.0})

    The exchange's get_markets() advertises one symbol per wired tape
    ("TAPEA/USD", "TAPEB/USD", ...). Each is a fully-functional
    market; the bot can construct multiple ScrummingBot instances
    against different tapes if the operator wants multi-tape stress
    later (Phase C+).
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
        # Paper balance ledger. Seed quote + every wired tape's synthetic
        # base with explicit zero so MEM-254 init handshake (which
        # requires absent=False on both sides) passes.
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
        """Symbol "TAPEA/USD" → tape_id "A". Raises if the symbol is
        not in the form we expect or the tape isn't wired.
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
        Cache files are daily for both crypto (CoinGecko) and equity
        (Yahoo). We ignore the timeframe arg and return the raw stream
        — the bot's BB / Vortex / MACD all operate on the candle
        sequence regardless of nominal interval."""
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
        # v3.24.65 — a LIMIT fills only if the candle TRADED THROUGH it.
        #
        # This used to be `fill_price = float(price)`: whatever price
        # the caller named became the fill, with no comparison to the
        # candle at all. A BUY limit at $1.00 against a $100 candle
        # filled at $1.00.
        #
        # That is not an unrealistic resting model — it is free money,
        # and it gets better the further from market the order bids. Any
        # strategy evaluated here that places limit orders was scored
        # against a fabricated discount, so the harness actively
        # recommended the wrong behaviour.
        #
        #   BUY  fills iff low  <= limit, at min(limit, close)
        #   SELL fills iff high >= limit, at max(limit, close)
        #
        # min/max rather than the limit itself: a BUY limit ABOVE the
        # market must not fill at its own worse price when the market
        # was cheaper — that would fabricate a LOSS, the mirror of the
        # defect being removed. The limit stays a ceiling for a BUY and
        # a floor for a SELL.
        #
        # Nuclear is single-shot by design, so an unfillable order is
        # returned OPEN and unfilled rather than rested. Fleet's
        # resting/sweep model is deliberately NOT copied here — the two
        # venues stay forks; only the fill PRICE contract is shared.
        # v3.24.67 (C19 / SN-21) — IOC_LIMIT shares the crosses test.
        #
        # It used to match neither branch, so it fell through to the
        # market path and filled at the close with the limit DISCARDED.
        # A price cap the venue ignores is worse than no cap: the
        # operator reads a fill their real order would never have taken
        # — reproduced at 100.0 against a 99.0 limit.
        #
        # Fleet raised "unsupported type" on the same input. Two venues
        # failing in OPPOSITE directions is worse than both failing the
        # same way, because a result that appears on one and not the
        # other reads as a finding.
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
            # No fill, and NO ledger movement: recording a purchase that
            # did not happen is the same class of lie as the fill price
            # this replaces.
            _order = Order(
                id=f"nuclear_{uuid.uuid4().hex[:12]}",
                symbol=symbol,
                side=side,
                type=order_type,
                amount=float(amount),
                price=float(price),
                filled=0.0,
                remaining=float(amount),
                # IOC never rests — that is the difference that DEFINES
                # the type. An IOC left OPEN is a LIMIT, and reporting
                # one as the other tells the operator their
                # taker-forcing order got a maker fill.
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
        # v3.24.66 (C19 / SN-17) — sufficiency precondition.
        #
        # `_adjust_balance` is plain addition with no floor, so before
        # this a BUY with no quote currency settled and drove the
        # balance negative, and a SELL of coins never held settled too.
        #
        # That is quieter than it sounds: every number downstream of a
        # sim run is denominated in this ledger, so a replay that spends
        # money it never had still reports P&L, fill counts and
        # target-growth figures — computed against an impossible
        # starting position, with nothing indicating anything went
        # wrong. The run does not fail; it lies.
        #
        # Raises rather than refusing quietly: amount<=0, unknown symbol
        # and missing candle already raise here, an insufficient balance
        # is the same class of caller error, and a silent refusal would
        # reproduce the defect in a new shape — the caller carries on
        # believing it traded.
        #
        # The 1e-12 tolerance admits an EXACTLY funded order. Without
        # it, float error would suppress the last trade of many runs,
        # which is harder to notice than the defect being fixed.
        _need_ccy, _need_qty, _have = (
            (quote, notional + fee, self._balances.get(quote, 0.0))
            if side == OrderSide.BUY
            else (base, amount, self._balances.get(base, 0.0))
        )
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
                    # v3.24.68 (C19 / SN-20) — PLACEHOLDER, aligned with
                    # FleetSimExchange.
                    #
                    # Real per-symbol limits are NOT available offline:
                    # `bot_container._get_market_limits` reads them from
                    # `exchange.get_markets()`, which for a sim bot is
                    # this table, and nothing persists a captured copy.
                    # Serving genuine limits needs a capture step that
                    # does not exist, so SN-20's real-limits half is
                    # outstanding.
                    #
                    # What WAS fixable: this read 0.01 while Fleet read
                    # 1.00 — a 100x gap in the smallest order either
                    # harness accepts, so the same strategy produced
                    # different trade COUNTS on the two, and the
                    # difference read as a finding rather than an
                    # artefact.
                    #
                    # Aligned on the HIGHER floor deliberately. A
                    # too-low minimum lets the sim place orders the real
                    # exchange would refuse, so the harness reports
                    # fills that could never happen — false positives,
                    # in the direction that flatters a strategy. A
                    # too-high floor only suppresses trades, which shows
                    # up honestly as a lower trade count.
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
