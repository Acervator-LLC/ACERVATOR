"""
src/trading/ta_signal_provider.py — Per-symbol TA producer (v3.19.0).

PURPOSE
───────
Extract the **producer-side** TA primitive composition that ScrummingBot
currently runs inline in `tick()` into a reusable, per-symbol API. The
ExtractorBot (v3.19.1) needs to evaluate TA signals on multiple pairs
each tick (its top-N watch list); having a single-symbol `evaluate(symbol)
→ TASnapshot` API avoids duplicating the candle-fetch + voting +
BB-proximity composition for every consumer.

SCOPE — what this module DOES
─────────────────────────────
  • Fetches OHLCV for a symbol via the supplied exchange connector.
  • Runs the `VotingEngine.compute_all` to produce a `VotingSummary`.
  • Runs `detect_bb_proximity` to produce a `BBProximityResult`.
  • Computes the raw `is_bullish` / `is_bearish` / `trend_hold` /
    `trend_strength` direction primitives using the same semantic
    ScrummingBot uses inline (`trend_strength = bull_count_in_last_20
    / 20`; `trend_hold = trend_strength > 0.65`).
  • Returns the composed result as a `TASnapshot` dataclass — flat,
    well-typed, serializable.

SCOPE — what this module DOES NOT do
─────────────────────────────────────
  • Apply operator-toggle flags (e.g. `flag_require_ta_bullish`). Those
    are bot-config dependent; the consumer bot applies them when
    building its `GateContext` (`eff_is_bullish = is_bullish if
    flag_require_ta_bullish else True`).
  • Apply stateful gates (Circuit Breaker, OTD hysteresis, Smart
    Cartridge). Those are bot-instance state; they live on the bot.
  • Apply ScrummingBot-specific overrides (band-travel trend override,
    ripe-harvest, etc.). Those compose with bot state + position and
    stay on the bot.
  • Replace ScrummingBot's inline TA computation. v3.19.0 ships the
    API only; ScrummingBot's existing inline TA stays as-is for now.
    Bit-identical migration of ScrummingBot to consume `TASignalProvider`
    + the 200-tick fixture parity test are deferred to a later ship
    (v3.19.0b or later) so this v3.19.0 has a tight, low-risk surface.

ARCHITECTURE
────────────
Each ScrummingBot or ExtractorBot instantiates ONE `TASignalProvider`
configured with the same indicator weights + thresholds the bot uses.
Per tick, the bot calls `await provider.evaluate(symbol)` for each
symbol it cares about. The provider returns `TASnapshot | None`
(None when candles unavailable or insufficient — typically <30
candles for full indicator warmup).

The bot then builds its `GateContext` using:
    snapshot = await provider.evaluate(symbol)
    if snapshot is None:
        return  # warmup; skip this tick for this symbol
    ctx = GateContext(
        ...,
        is_bullish=snapshot.is_bullish,
        bb_pos=snapshot.bb_position,
        ...,
        # apply operator flags + bot state HERE
        eff_is_bullish=(snapshot.is_bullish
                        if self.config.flag_require_ta_bullish else True),
        cb_blocks_scrum=self._cb_soft_active_side == "scrum",
        hyst_ok_scrum_side=self._hyst_ok_scrum_side,
        ...,
    )
    result = self._scrum_chain.evaluate(ctx)

FORWARD COMPATIBILITY
─────────────────────
This module is bot-agnostic. ScrummingBot's eventual migration (when
it lands) replaces the inline candle-fetch + VotingEngine + BB-proximity
calls with a single `await self._ta_provider.evaluate(self.config.symbol)`
call — same VotingSummary + BBProximityResult, same downstream gate
evaluation. ExtractorBot calls the same provider with each pair in its
watch list per tick.

sadp: R28  # TA producer: fail-loudly on bad data, fail-safe on insufficient candles
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .ta_engine import (
    BBProximityResult,
    Candle,
    SignalDirection,
    VotingEngine,
    VotingSummary,
    candles_from_raw,
    detect_bb_proximity,
)

logger = logging.getLogger("acervator.ta_signal_provider")


# ─────────────────────────────────────────────────────────────────────
# Data container
# ─────────────────────────────────────────────────────────────────────


@dataclass
class TASnapshot:
    """Raw TA signals for a single symbol at a single tick.

    Producer-only: contains TA primitives but NOT bot-state-dependent
    fields (operator-toggle-applied effective values, Circuit Breaker,
    OTD hysteresis, Smart Cartridge, etc.). Consumer bots apply their
    own config flags + bot-state-aware gates on top.

    Note: ``voting_summary`` and ``bb_proximity_result`` carry the
    full underlying objects for callers that need fields not promoted
    to the top level (e.g. the raw signal list, landing-strip
    consolidation strength).
    """

    # Identity
    symbol: str
    timeframe: str

    # Voting summary (promoted scalar fields)
    bullish_count: int
    bearish_count: int
    neutral_count: int
    net_score: float
    consensus_confidence: float
    consensus_direction: SignalDirection

    # BB proximity (promoted scalar fields)
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: float
    bb_near_upper: bool
    bb_near_lower: bool

    # Landing Strip detection (promoted from BBProximityResult)
    landing_strip: bool
    landing_strip_side: str
    landing_strip_candles: int

    # Direction primitives (computed; bot applies operator flags on top)
    is_bullish: bool
    is_bearish: bool
    trend_hold: bool
    trend_strength: float

    # Raw indicator outputs preserved for callers wanting unrestricted access
    voting_summary: VotingSummary
    bb_proximity_result: BBProximityResult


# ─────────────────────────────────────────────────────────────────────
# Provider
# ─────────────────────────────────────────────────────────────────────


class TASignalProvider:
    """Per-symbol TA snapshot producer.

    Construction is operator-config-driven (timeframe, indicator weights,
    confidence threshold, BB-proximity tolerance, OHLCV history depth).
    Each ``evaluate(symbol)`` call is a fresh computation — the provider
    holds no per-symbol state across ticks (the underlying VotingEngine
    is the only stateful component, and its state is indicator-weight
    configuration, not market data).

    The trend-strength + trend-hold semantic mirrors ScrummingBot's
    inline computation (``scrumming_bot.py:4875-4882``):

      ``trend_strength = (bull-count in last 20 candles) / 20``
      ``trend_hold = trend_strength > 0.65``

    This is the trend-detection HEURISTIC. ScrummingBot then applies
    additional state-dependent overrides (band-travel, ripe-harvest)
    on top — those overrides stay on the bot. ExtractorBot can apply
    its own; the provider's outputs are pre-override.
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
        """Exposed for callers that want to inspect indicator weights
        post-construction (e.g. operator GUI introspection)."""
        return self._voting_engine

    async def evaluate(self, symbol: str) -> Optional[TASnapshot]:
        """Compute a TASnapshot for ``symbol``.

        Returns:
            TASnapshot with all populated fields on success.
            None if the exchange returned no candles, raised, or returned
            fewer than ``min_candles_for_signal`` candles (warmup window).

        The None-on-warmup contract matches ScrummingBot's existing
        behavior of skipping the TA-dependent path on early ticks.
        """
        # Fetch candles. Failure → None (consumer skips this tick for
        # this symbol). Do NOT raise — exchanges can hiccup and a
        # tick should be skippable for one symbol without taking
        # down the whole bot.
        try:
            raw = await self._exchange.get_ohlcv(
                symbol,
                timeframe=self._timeframe,
                limit=self._ohlcv_limit,
            )
        except Exception as exc:  # R28-OK: TA fetch is per-tick best-effort
            logger.debug(
                "TASignalProvider %s: get_ohlcv raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        try:
            candles = candles_from_raw(raw)
        except Exception as exc:  # R28-OK: malformed candle data; skip tick
            logger.debug(
                "TASignalProvider %s: candles_from_raw raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        if len(candles) < self._min_candles:
            return None  # warmup

        # Run the indicator voting. The VotingEngine is the canonical
        # 7-indicator aggregator — same instance ScrummingBot uses
        # inline; just invoked from a different call site.
        try:
            summary = self._voting_engine.compute_all(candles, self._timeframe)
        except Exception as exc:  # R28-OK: voting failure; skip tick
            logger.debug(
                "TASignalProvider %s: voting compute_all raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        # BB proximity (also produces landing-strip detection).
        try:
            bb_result = detect_bb_proximity(candles, tolerance_pct=self._bb_tolerance)
        except Exception as exc:  # R28-OK: BB compute failure; skip tick
            logger.debug(
                "TASignalProvider %s: detect_bb_proximity raised %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        # Direction primitives.
        direction = summary.consensus_direction
        is_bullish = direction == SignalDirection.BULLISH
        is_bearish = direction == SignalDirection.BEARISH

        # Trend strength: fraction of recent green candles in the last
        # 20-bar window. Mirrors ScrummingBot's inline computation at
        # scrumming_bot.py:4875-4882. If fewer than 20 candles available,
        # default to 0.5 (neutral) — same fallback ScrummingBot uses.
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
