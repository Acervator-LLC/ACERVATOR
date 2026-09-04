"""Circuit-breaker logic for ScrummingBot: single-candle move interrupts.

Soft breaker is a time delay that interrupts one side of the market for a
cooldown; hard breaker pauses the bot until an operator reset.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..bot_container import BotState

logger = logging.getLogger("acervator.scrumming")

if TYPE_CHECKING:
    from ..scrumming_bot import ScrummingBot as _Host
else:
    _Host = object


class CircuitBreakerMixin(_Host):
    state: BotState

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
        try:
            o = float(candle.open)
            h = float(candle.high)
            l = float(candle.low)
            c = float(candle.close)
        except (TypeError, ValueError, AttributeError):
            return self._cb_hard_tripped or self._cb_soft_active_side is not None
        if o <= 0:
            return self._cb_hard_tripped or self._cb_soft_active_side is not None

        # Idempotency: skip if this candle was already evaluated.
        ts = float(getattr(candle, "timestamp", 0) or 0)
        already_seen = ts > 0 and ts == self._cb_last_candle_ts
        if not already_seen and ts > 0:
            self._cb_last_candle_ts = ts

        move_pct = (h - l) / o * 100.0
        _move_abs = h - l  # same threshold, expressed in price
        direction = "up" if c >= o else "down"

        hard_pct = float(getattr(self.config, "circuit_breaker_hard_pct", 35.0))
        soft_pct = float(getattr(self.config, "circuit_breaker_soft_pct", 25.0))

        # --- Hard breaker (highest priority) ---
        # Only trip on a fresh candle and not already tripped.
        if (
            not already_seen
            and not self._cb_hard_tripped
            and hard_pct > 0
            and _move_abs >= hard_pct / 100.0 * o
        ):
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
                    "CANCELLED",
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
        if (
            not already_seen
            and self._cb_soft_active_side is None
            and soft_pct > 0
            and _move_abs >= soft_pct / 100.0 * o
        ):
            side = "scrum" if direction == "up" else "fold"
            cooldown = max(
                1, int(getattr(self.config, "circuit_breaker_cooldown_candles", 3) or 3)
            )
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
                    "CANCELLED",
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
        ) as _sup:  # R28-OK: best-effort optional update / telemetry probe
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
