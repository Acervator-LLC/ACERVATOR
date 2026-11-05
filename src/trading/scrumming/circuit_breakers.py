"""Circuit-breaker logic for ScrummingBot: single-candle move interrupts.

Soft breaker is a time delay that interrupts one side of the market for a
cooldown; hard breaker holds every order of the bot until an operator reset.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from ...exchange.data_pool import TF_SECONDS
from ..bot_container import BotState
from ..container.config import BotConfig
from ..indicators.types import Candle, candles_from_raw

logger = logging.getLogger("acervator.scrumming")

if TYPE_CHECKING:
    from ..scrumming_bot import ScrummingBot as _Host
else:
    _Host = object

#: Each breaker field and the figure ``BotConfig`` declares for it, so no
#: reader holds a copy of a figure.
BREAKER_DEFAULTS: dict = {
    "circuit_breaker_soft_pct": BotConfig.circuit_breaker_soft_pct,
    "circuit_breaker_hard_pct": BotConfig.circuit_breaker_hard_pct,
    "circuit_breaker_cooldown_candles": BotConfig.circuit_breaker_cooldown_candles,
}

SOFT_PCT_FIELD = "circuit_breaker_soft_pct"
HARD_PCT_FIELD = "circuit_breaker_hard_pct"
COOLDOWN_FIELD = "circuit_breaker_cooldown_candles"

BREAKER_OFF_PCT = 0.0
MIN_COOLDOWN_CANDLES = 1
PERCENT_PER_RATIO_UNIT = 100.0

SCRUM_SIDE = "scrum"
FOLD_SIDE = "fold"
NO_SIDE = ""
UP_DIRECTION = "up"
DOWN_DIRECTION = "down"

UNREADABLE_FORMAT = "{field}={value!r}"

#: ``BotConfig.ta_timeframe`` default, read where a config holds an empty one.
DEFAULT_TIMEFRAME = "1h"
#: The rows ``ScrummingBot.tick`` asks ``_get_ohlcv`` for.
CANDLE_ROWS = 100
MS_PER_SECOND = 1000.0

#: What ``CircuitBreakerMixin.order_hold_reason`` answers while the hard breaker holds.
HARD_HOLD_FORMAT = (
    "the hard circuit breaker tripped at {pct:.2f}% and holds every order until "
    "Reset All Breakers is pressed"
)


@dataclass(frozen=True)
class BreakerFigures:
    """The two breaker thresholds and the soft cooldown one config carries.

    ``unreadable`` names every field whose stored value did not parse and so
    fell back to its ``BREAKER_DEFAULTS`` figure.
    """

    soft_pct: float
    hard_pct: float
    cooldown_candles: int
    unreadable: tuple = ()


@dataclass(frozen=True)
class BreakerMove:
    """One candle's high-to-low move against both breaker thresholds.

    ``soft_side`` is the side the soft breaker shuts, or ``NO_SIDE`` while the
    move stays under ``BreakerFigures.soft_pct``.
    """

    open_px: float
    high: float
    low: float
    close: float
    move_pct: float
    direction: str
    hard_trips: bool
    soft_side: str


def breaker_figures(settings) -> BreakerFigures:
    """``settings`` read into a ``BreakerFigures``, naming what did not parse.

    A value that is not a number reads its ``BREAKER_DEFAULTS`` figure, and
    ``cooldown_candles`` is never below ``MIN_COOLDOWN_CANDLES``.
    """
    unreadable: list = []
    pcts: dict = {}
    for field in (SOFT_PCT_FIELD, HARD_PCT_FIELD):
        raw = getattr(settings, field, BREAKER_DEFAULTS[field])
        try:
            pcts[field] = float(raw)
        except (TypeError, ValueError):
            pcts[field] = float(BREAKER_DEFAULTS[field])
            unreadable.append(UNREADABLE_FORMAT.format(field=field, value=raw))

    raw_cooldown = getattr(settings, COOLDOWN_FIELD, BREAKER_DEFAULTS[COOLDOWN_FIELD])
    if not raw_cooldown:
        raw_cooldown = BREAKER_DEFAULTS[COOLDOWN_FIELD]
    try:
        cooldown = int(raw_cooldown)
    except (TypeError, ValueError):
        cooldown = int(BREAKER_DEFAULTS[COOLDOWN_FIELD])
        unreadable.append(
            UNREADABLE_FORMAT.format(field=COOLDOWN_FIELD, value=raw_cooldown)
        )

    return BreakerFigures(
        soft_pct=pcts[SOFT_PCT_FIELD],
        hard_pct=pcts[HARD_PCT_FIELD],
        cooldown_candles=max(MIN_COOLDOWN_CANDLES, cooldown),
        unreadable=tuple(unreadable),
    )


def breaker_move(candle, figures: BreakerFigures) -> Optional[BreakerMove]:
    """One candle read against ``figures``, or None while it is not a candle.

    The move is ``high - low`` against ``pct / 100 * open``, and the close
    against the open picks the side the soft breaker shuts.
    """
    try:
        open_px = float(candle.open)
        high = float(candle.high)
        low = float(candle.low)
        close = float(candle.close)
    except (TypeError, ValueError, AttributeError):
        return None
    if open_px <= 0:
        return None
    reach = high - low
    hard_trips = (
        figures.hard_pct > BREAKER_OFF_PCT
        and reach >= figures.hard_pct / PERCENT_PER_RATIO_UNIT * open_px
    )
    soft_trips = (
        figures.soft_pct > BREAKER_OFF_PCT
        and reach >= figures.soft_pct / PERCENT_PER_RATIO_UNIT * open_px
    )
    direction = UP_DIRECTION if close >= open_px else DOWN_DIRECTION
    side = SCRUM_SIDE if direction == UP_DIRECTION else FOLD_SIDE
    return BreakerMove(
        open_px=open_px,
        high=high,
        low=low,
        close=close,
        move_pct=reach / open_px * PERCENT_PER_RATIO_UNIT,
        direction=direction,
        hard_trips=hard_trips,
        soft_side=side if soft_trips else NO_SIDE,
    )


def candle_stamp(candle: Any) -> float:
    """``candle.timestamp`` as a float, 0.0 where it is not a number."""
    try:
        return float(getattr(candle, "timestamp", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def forming_candle(
    held: Optional[Candle],
    rows: list,
    period_s: float,
    now_s: float,
    price: Any,
) -> Optional[Candle]:
    """The candle open at ``now_s`` with ``price`` added to its range.

    ``rows[-1]``, else ``held``, places the candle on the venue's ``period_s``
    grid, a row at that open supplies its open, and ``held`` carries the range
    earlier ticks saw. A ``price`` that is not a positive number answers ``held``.
    """
    try:
        last = float(price)
    except (TypeError, ValueError):
        return held
    if isinstance(price, bool) or not math.isfinite(last) or last <= 0.0:
        return held
    newest = rows[-1] if rows else None
    anchor = newest or held
    if anchor is None:
        return None
    anchor_ms = candle_stamp(anchor)
    period_ms = period_s * MS_PER_SECOND
    periods = max(0, math.floor((now_s * MS_PER_SECOND - anchor_ms) / period_ms))
    opened_ms = anchor_ms + periods * period_ms
    same = [
        candle
        for candle in (newest, held)
        if candle is not None and candle_stamp(candle) == opened_ms
    ]
    return Candle(
        timestamp=opened_ms,
        open=same[0].open if same else last,
        high=max([last, *(candle.high for candle in same)]),
        low=min([last, *(candle.low for candle in same)]),
        close=last,
        volume=0.0,
    )


class CircuitBreakerMixin(_Host):
    # ScrummingBot.__init__ assigns each of these; _Host resolves back to
    # ScrummingBot, so the annotations break that cycle for a type reader.
    state: BotState
    _cb_hard_tripped: bool
    _cb_hard_tripped_at: float
    _cb_hard_trip_pct: float
    _cb_hard_candle_ts: float
    _cb_soft_active_side: Optional[str]
    _cb_soft_cooldown_remaining: int
    _cb_soft_tripped_at: float
    _cb_soft_trip_pct: float
    _cb_soft_candle_ts: float
    _cb_last_candle_ts: float
    _cb_row_ts: float
    _cb_forming: Optional[Candle]
    _cb_unreadable_named: tuple
    _manual_fire_pending: bool

    def order_hold_reason(self) -> str:
        """``HARD_HOLD_FORMAT`` while ``_cb_hard_tripped`` holds, empty otherwise."""
        if not self._cb_hard_tripped:
            return ""
        return HARD_HOLD_FORMAT.format(pct=self._cb_hard_trip_pct)

    async def _tick_breaker_holds(self, ticker: Any, position_usd: float) -> bool:
        """Read the pooled candles and ``ticker.last`` into the breakers, and answer
        True while ``_cb_hard_tripped`` holds, which ends ``ScrummingBot.tick``."""
        timeframe = self.config.ta_timeframe or DEFAULT_TIMEFRAME
        try:
            raw = await self._get_ohlcv(
                self.config.symbol, timeframe=timeframe, limit=CANDLE_ROWS
            )
            candles = candles_from_raw(raw)
        except Exception as _read_exc:
            logger.debug(
                "Bot %s breaker candles unavailable: %s", self.bot_id, _read_exc
            )
            candles = []
        try:
            self._check_circuit_breakers(candles, getattr(ticker, "last", None))
        except Exception as _cb_exc:
            logger.warning(
                "Bot %s circuit breaker check raised %s: %s",
                self.bot_id,
                type(_cb_exc).__name__,
                _cb_exc,
            )
        if not self._cb_hard_tripped:
            return False
        self.stats.position_value = position_usd
        if self._manual_fire_pending:
            self._manual_fire_pending = False
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"MANUAL FIRE WAITS: {self.order_hold_reason()}.",
            )
        self._emit_gate_decision_at_quiet_tick("cb-hard-tripped")
        return True

    def _check_circuit_breakers(self, candles, price=None) -> bool:
        """Read every candle ``_unread_candles`` names for circuit-breaker triggers.

        Single-candle move % = ``(high - low) / open × 100``. Direction is
        inferred from close vs open: close >= open interrupts the SCRUM side
        (don't sell into a pump); close < open interrupts the FOLD side
        (don't buy a falling knife).

        A hard trip holds every order (``order_hold_reason``) and reads
        ``BotState.PAUSED`` until an operator reset. A soft trip sets
        ``_cb_soft_active_side`` and a cooldown that decrements per fresh
        candle, re-opening that side at zero.

        Returns True while either breaker is blocking trades on either side.
        """
        figures = breaker_figures(self.config)
        for candle in self._unread_candles(candles, price):
            self._read_breaker_candle(candle, figures)
        return self._cb_hard_tripped or self._cb_soft_active_side is not None

    def _unread_candles(self, candles, price) -> list:
        """The rows of ``candles`` from ``_cb_row_ts`` on, then ``_cb_forming`` grown
        by ``price`` in place of its own row; a first read takes the newest row alone.

        ``MarketDataPool`` serves one slot for a whole timeframe, so ``price`` is
        what grows the open candle between two slot fetches.
        """
        rows = list(candles or [])
        unread = rows[-1:]
        if self._cb_row_ts > 0.0:
            unread = [row for row in rows if candle_stamp(row) >= self._cb_row_ts]
        if rows:
            self._cb_row_ts = candle_stamp(rows[-1])
        period_s = TF_SECONDS.get(self.config.ta_timeframe or DEFAULT_TIMEFRAME)
        if period_s is None:
            return unread
        self._cb_forming = forming_candle(
            self._cb_forming, rows, period_s, time.time(), price
        )
        forming = self._cb_forming
        if forming is None:
            return unread
        opened_ms = candle_stamp(forming)
        return [row for row in unread if candle_stamp(row) != opened_ms] + [forming]

    def _read_breaker_candle(self, candle, figures: BreakerFigures) -> None:
        """Count ``candle`` when it is newer than ``_cb_last_candle_ts``, and trip each
        breaker it has reached; a timestamp of 0 makes every read fresh."""
        move = breaker_move(candle, figures)
        if move is None:
            return
        ts = candle_stamp(candle)
        fresh = ts <= 0.0 or ts > self._cb_last_candle_ts
        if fresh and ts > 0.0:
            self._cb_last_candle_ts = ts

        if figures.unreadable and fresh:
            self._name_unreadable_breaker_figures(figures)

        hard_is_new = ts <= 0.0 or ts > self._cb_hard_candle_ts
        if not self._cb_hard_tripped and move.hard_trips and hard_is_new:
            self._trip_hard_breaker(move, figures, ts)
            return

        if self._cb_hard_tripped:
            return

        if (
            fresh
            and self._cb_soft_active_side is not None
            and self._cb_soft_cooldown_remaining > 0
        ):
            self._cb_soft_cooldown_remaining -= 1
            if self._cb_soft_cooldown_remaining <= 0:
                old_side = self._cb_soft_active_side
                self._cb_soft_active_side = None
                self._cb_soft_trip_pct = 0.0
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SOFT CIRCUIT BREAKER RESET: cooldown elapsed; "
                        f"{old_side.upper()} side re-opens. Normal trade "
                        f"flow resumed."
                    ),
                )

        soft_is_new = ts <= 0.0 or ts > self._cb_soft_candle_ts
        if self._cb_soft_active_side is None and move.soft_side and soft_is_new:
            self._trip_soft_breaker(move, figures, ts)

    def _trip_hard_breaker(
        self, move: BreakerMove, figures: BreakerFigures, ts: float
    ) -> None:
        """Set ``_cb_hard_tripped`` and ``BotState.PAUSED``, record ``ts`` in
        ``_cb_hard_candle_ts``, and write the trip to ``bot.log``."""
        move_pct = move.move_pct
        hard_pct = figures.hard_pct
        self._cb_hard_tripped = True
        self._cb_hard_tripped_at = time.time()
        self._cb_hard_trip_pct = move_pct
        self._cb_hard_candle_ts = ts
        try:
            self.state = BotState.PAUSED
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_check_circuit_breakers",
                type(_sup).__name__,
                _sup,
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"HARD CIRCUIT BREAKER TRIPPED: single-candle move "
                f"{move_pct:.2f}% ≥ hard threshold {hard_pct:.2f}% "
                f"(direction={move.direction}, OHLC: ${move.open_px:.8f}/"
                f"${move.high:.8f}/${move.low:.8f}/${move.close:.8f}). Bot PAUSED — "
                f"operator reset required. All trade paths interrupted."
            ),
        )
        try:
            self._emit_trade_notification(
                "ALL",
                "REFUSED",
                f"HARD breaker @ {move_pct:.2f}% (≥ {hard_pct:.2f}%)",
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_check_circuit_breakers",
                type(_sup).__name__,
                _sup,
            )

    def _trip_soft_breaker(
        self, move: BreakerMove, figures: BreakerFigures, ts: float
    ) -> None:
        """Set ``_cb_soft_active_side`` and its cooldown, record ``ts`` in
        ``_cb_soft_candle_ts``, and write the trip to ``bot.log``."""
        move_pct = move.move_pct
        side = move.soft_side
        cooldown = figures.cooldown_candles
        self._cb_soft_active_side = side
        self._cb_soft_cooldown_remaining = cooldown
        self._cb_soft_tripped_at = time.time()
        self._cb_soft_trip_pct = move_pct
        self._cb_soft_candle_ts = ts
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"SOFT CIRCUIT BREAKER TRIPPED: single-candle move "
                f"{move_pct:.2f}% ≥ soft threshold {figures.soft_pct:.2f}% "
                f"(direction={move.direction}, side={side.upper()}). "
                f"Cooldown: {cooldown} candles before re-open. "
                f"OHLC: ${move.open_px:.8f}/${move.high:.8f}/${move.low:.8f}/"
                f"${move.close:.8f}."
            ),
        )
        try:
            self._emit_trade_notification(
                side.upper(),
                "REFUSED",
                f"SOFT breaker @ {move_pct:.2f}% on {side.upper()} side",
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_check_circuit_breakers",
                type(_sup).__name__,
                _sup,
            )

    def _name_unreadable_breaker_figures(self, figures: BreakerFigures) -> None:
        """Write one bot.log line naming each unreadable breaker field.

        The line repeats only when ``BreakerFigures.unreadable`` differs from
        the set ``_cb_unreadable_named`` already carries.
        """
        if figures.unreadable == getattr(self, "_cb_unreadable_named", ()):
            return
        self._cb_unreadable_named = figures.unreadable
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"CIRCUIT BREAKER FIGURE UNREADABLE: "
                f"{', '.join(figures.unreadable)}. The declared figures are "
                f"used — soft {figures.soft_pct:.2f}%, hard "
                f"{figures.hard_pct:.2f}%, cooldown "
                f"{figures.cooldown_candles} candles — and both breakers "
                f"stay armed."
            ),
        )

    def reset_circuit_breaker(self, scope: str = "all") -> dict:
        """Operator-initiated circuit breaker reset.

        The soft breaker also self-resets on cooldown elapse; the hard
        breaker only clears through this call. ``scope`` is 'all', 'soft',
        or 'hard' (clearing hard resumes the bot if PAUSED). Returns
        ``{'applied': [...], 'scope': ...}`` and never raises — fail-soft
        for GUI buttons.
        """
        applied: list[str] = []
        scope_norm = (scope or "all").lower()
        if scope_norm not in ("all", "soft", "hard"):
            scope_norm = "all"

        if scope_norm in ("all", "soft") and self._cb_soft_active_side is not None:
            old_side = self._cb_soft_active_side
            old_pct = self._cb_soft_trip_pct
            self._cb_soft_active_side = None
            self._cb_soft_cooldown_remaining = 0
            self._cb_soft_trip_pct = 0.0
            self._cb_soft_tripped_at = 0.0
            applied.append(
                f"soft breaker cleared (was {old_side.upper()} " f"@ {old_pct:.2f}%)"
            )

        if scope_norm in ("all", "hard") and self._cb_hard_tripped:
            old_pct = self._cb_hard_trip_pct
            self._cb_hard_tripped = False
            self._cb_hard_tripped_at = 0.0
            self._cb_hard_trip_pct = 0.0
            self._held_orders_named.clear()
            try:
                if self.state == BotState.PAUSED:
                    self.state = BotState.RUNNING
                    applied.append("bot resumed from PAUSED → RUNNING")
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "reset_circuit_breaker",
                    type(_sup).__name__,
                    _sup,
                )
            applied.append(f"hard breaker cleared (was @ {old_pct:.2f}%)")

        msg_tail = "; ".join(applied) if applied else "no circuit breakers active"
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"CIRCUIT BREAKER RESET ({scope_norm}): {msg_tail}",
            )
        except (
            Exception
        ) as _sup:  # An emit failure reaches the debug log and no bot.log line.
            logger.debug(
                "suppressed in %s: %s: %s",
                "reset_circuit_breaker",
                type(_sup).__name__,
                _sup,
            )
        return {"applied": applied, "scope": scope_norm}

    def _bb_detect_thresholds(self) -> tuple[float, float]:
        """Return ``(lower_detect, upper_detect)`` thresholds in ``bb_pos``
        terms from ``config.scrum_detect_pct``.

        With the ``bb_pos`` convention (0.0 = lower band, 0.5 = midline,
        1.0 = upper band): SCRUM requires ``bb_pos >= upper_detect`` and
        FOLD requires ``bb_pos <= lower_detect``. ``scrum_detect_pct`` is
        the percent distance from midline to band, so 75 gives
        ``upper_detect = 0.875`` and ``lower_detect = 0.125``.
        """
        # None-sentinel default so a legitimate 0 isn't coerced to 75 by
        # `or` truthiness.
        _raw = getattr(self.config, "scrum_detect_pct", None)
        try:
            detect_pct = float(_raw) if _raw is not None else 75.0
        except (TypeError, ValueError):
            detect_pct = 75.0
        detect_frac = max(0.0, min(1.0, detect_pct / 100.0))
        half = detect_frac * 0.5
        return (0.5 - half, 0.5 + half)
