"""``TASignalProvider`` produces a per-symbol ``TASnapshot``.

``evaluate`` fetches OHLCV for one symbol, runs ``VotingEngine.compute_all``
and ``detect_bb_proximity``, then packs both results and the direction
primitives into a ``TASnapshot``. It returns None when the fetch raises, when
``candles_from_raw`` raises, or when fewer than ``min_candles_for_signal``
candles come back. ``TASnapshot`` holds TA primitives only, with no
operator-flag or bot-state fields.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from .ta_engine import (
    BBProximityResult,
    SignalDirection,
    VotingEngine,
    VotingSummary,
    candles_from_raw,
    detect_bb_proximity,
)

logger = logging.getLogger("acervator.ta_signal_provider")


@dataclass
class TASnapshot:
    """``TASignalProvider.evaluate`` returns one of these per symbol per tick.

    ``voting_summary`` and ``bb_proximity_result`` carry the full objects
    behind promoted scalars such as ``net_score`` and ``bb_position``.
    """

    symbol: str
    timeframe: str

    bullish_count: int
    bearish_count: int
    neutral_count: int
    net_score: float
    consensus_confidence: float
    consensus_direction: SignalDirection

    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: float
    bb_near_upper: bool
    bb_near_lower: bool

    landing_strip: bool
    landing_strip_side: str
    landing_strip_candles: int

    is_bullish: bool
    is_bearish: bool
    trend_hold: bool
    trend_strength: float

    voting_summary: VotingSummary
    bb_proximity_result: BBProximityResult


class TASignalProvider:
    """``TASignalProvider`` wraps one ``exchange`` connector.

    ``evaluate`` recomputes from candles on every call and keeps no per-symbol
    state. ``confidence_threshold`` reaches ``VotingEngine`` and filters
    nothing in ``evaluate``.
    """

    def __init__(
        self,
        exchange: Any,
        *,
        timeframe: str = "1h",
        weights: Optional[dict[str, float]] = None,
        confidence_threshold: float = 0.3,
        bb_proximity_tolerance_pct: float = 1.0,
        ohlcv_limit: int = 100,
        trend_strength_threshold: float = 0.65,
        min_candles_for_signal: int = 30,
    ) -> None:
        self._exchange = exchange
        self._timeframe = timeframe
        self._voting_engine = VotingEngine(
            confidence_threshold=confidence_threshold,
            weights=weights,
        )
        self._bb_tolerance = float(bb_proximity_tolerance_pct)
        self._ohlcv_limit = int(ohlcv_limit)
        self._trend_strength_threshold = float(trend_strength_threshold)
        self._min_candles = int(min_candles_for_signal)

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def voting_engine(self) -> VotingEngine:
        """Return the ``VotingEngine`` built from the constructor's ``weights``."""
        return self._voting_engine

    async def evaluate(self, symbol: str) -> Optional[TASnapshot]:
        """Return a ``TASnapshot`` for ``symbol``, or None.

        None means the OHLCV fetch or ``candles_from_raw`` raised, or fewer
        than ``min_candles_for_signal`` candles came back.
        """
        try:
            raw = await self._exchange.get_ohlcv(
                symbol,
                timeframe=self._timeframe,
                limit=self._ohlcv_limit,
            )
        except Exception as exc:
            logger.debug(
                "TASignalProvider %s: get_ohlcv raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        try:
            candles = candles_from_raw(raw)
        except Exception as exc:
            logger.debug(
                "TASignalProvider %s: candles_from_raw raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        if len(candles) < self._min_candles:
            return None

        try:
            summary = self._voting_engine.compute_all(candles, self._timeframe)
        except Exception as exc:
            logger.debug(
                "TASignalProvider %s: voting compute_all raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        try:
            bb_result = detect_bb_proximity(candles, tolerance_pct=self._bb_tolerance)
        except Exception as exc:
            logger.debug(
                "TASignalProvider %s: detect_bb_proximity raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        direction = summary.consensus_direction
        is_bullish = direction == SignalDirection.BULLISH
        is_bearish = direction == SignalDirection.BEARISH

        # The 20-candle window is fixed; only the threshold it feeds is configurable.
        if len(candles) >= 20:
            recent = candles[-20:]
            bull_in_recent = sum(1 for c in recent if c.close > c.open)
            trend_strength = bull_in_recent / 20.0
        else:
            trend_strength = 0.5
        trend_hold = trend_strength > self._trend_strength_threshold

        return TASnapshot(
            symbol=symbol,
            timeframe=self._timeframe,
            bullish_count=summary.bullish_count,
            bearish_count=summary.bearish_count,
            neutral_count=summary.neutral_count,
            net_score=summary.net_score,
            consensus_confidence=summary.consensus_confidence,
            consensus_direction=direction,
            bb_upper=bb_result.upper,
            bb_middle=bb_result.middle,
            bb_lower=bb_result.lower,
            bb_position=bb_result.bb_position,
            bb_near_upper=bb_result.near_upper,
            bb_near_lower=bb_result.near_lower,
            landing_strip=bb_result.landing_strip,
            landing_strip_side=bb_result.landing_strip_side,
            landing_strip_candles=bb_result.landing_strip_candles,
            is_bullish=is_bullish,
            is_bearish=is_bearish,
            trend_hold=trend_hold,
            trend_strength=trend_strength,
            voting_summary=summary,
            bb_proximity_result=bb_result,
        )
