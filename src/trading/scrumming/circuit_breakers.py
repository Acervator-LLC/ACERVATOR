"""Circuit-breaker logic for ScrummingBot: single-candle move interrupts.

Soft breaker is a time delay that interrupts one side of the market for a
cooldown; hard breaker pauses the bot until an operator reset.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ..bot_container import BotState
from ..container.config import BotConfig

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


class CircuitBreakerMixin(_Host):
    # ScrummingBot.__init__ assigns each of these; _Host resolves back to
    # ScrummingBot, so the annotations break that cycle for a type reader.
    state: BotState
    _cb_hard_tripped: bool
    _cb_hard_tripped_at: float
    _cb_hard_trip_pct: float
    _cb_soft_active_side: Optional[str]
    _cb_soft_cooldown_remaining: int
    _cb_soft_tripped_at: float
    _cb_soft_trip_pct: float
    _cb_last_candle_ts: float
    _cb_unreadable_named: tuple

    def _check_circuit_breakers(self, candles) -> bool:
        """Evaluate the most recent candle for circuit-breaker triggers.

        Single-candle move % = ``(high - low) / open × 100``. Direction is
        inferred from close vs open: close >= open interrupts the SCRUM side
        (don't sell into a pump); close < open interrupts the FOLD side
        (don't buy a falling knife).

        A hard trip pauses the bot (``BotState.PAUSED``) until an operator
        reset. A soft trip sets ``_cb_soft_active_side`` and a cooldown that
        decrements per fresh candle, re-opening that side at zero.

        Returns True while either breaker is blocking trades on either side.
        Idempotent per candle timestamp — the same candle never double-trips.
        """
        if not candles:
            return self._cb_hard_tripped or self._cb_soft_active_side is not None
        candle = candles[-1]
        figures = breaker_figures(self.config)
        move = breaker_move(candle, figures)
        if move is None:
            return self._cb_hard_tripped or self._cb_soft_active_side is not None
        o = move.open_px
        h = move.high
        l = move.low
        c = move.close

        # Idempotency: skip if this candle was already evaluated. A timestamp
        # that is not a number reads 0, which makes every candle fresh.
        try:
            ts = float(getattr(candle, "timestamp", 0) or 0)
        except (TypeError, ValueError):
            ts = 0.0
        already_seen = ts > 0 and ts == self._cb_last_candle_ts
        if not already_seen and ts > 0:
            self._cb_last_candle_ts = ts

        move_pct = move.move_pct
        direction = move.direction

        hard_pct = figures.hard_pct
        soft_pct = figures.soft_pct

        if figures.unreadable and not already_seen:
            self._name_unreadable_breaker_figures(figures)

        # --- Hard breaker (highest priority) ---
        # Only trip on a fresh candle and not already tripped.
        if not already_seen and not self._cb_hard_tripped and move.hard_trips:
            self._cb_hard_tripped = True
            self._cb_hard_tripped_at = time.time()
            self._cb_hard_trip_pct = move_pct
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
                    f"(direction={direction}, OHLC: ${o:.8f}/${h:.8f}/"
                    f"${l:.8f}/${c:.8f}). Bot PAUSED — operator reset "
                    f"required. All trade paths interrupted."
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
            return True

        # If hard is already tripped, all gates remain closed.
        if self._cb_hard_tripped:
            return True

        # --- Soft breaker cooldown decrement on each fresh candle ---
        if (
            not already_seen
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

        # --- Soft breaker check ---
        # Only trip on a fresh candle, not already soft-tripped.
        if not already_seen and self._cb_soft_active_side is None and move.soft_side:
            side = move.soft_side
            cooldown = figures.cooldown_candles
            self._cb_soft_active_side = side
            self._cb_soft_cooldown_remaining = cooldown
            self._cb_soft_tripped_at = time.time()
            self._cb_soft_trip_pct = move_pct
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SOFT CIRCUIT BREAKER TRIPPED: single-candle move "
                    f"{move_pct:.2f}% ≥ soft threshold {soft_pct:.2f}% "
                    f"(direction={direction}, side={side.upper()}). "
                    f"Cooldown: {cooldown} candles before re-open. "
                    f"OHLC: ${o:.8f}/${h:.8f}/${l:.8f}/${c:.8f}."
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
            return True

        return self._cb_hard_tripped or self._cb_soft_active_side is not None

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
