"""The TA VotingEngine, and the front door of the indicator package.

Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights
reserved.

The indicators live one per module under ``src/trading/indicators/``. This
module holds their consumer, the VotingEngine, and re-exports the package so
every existing ``ta_engine`` import path still resolves.

Indicator formulae are published, and each indicator computes its own maths
from candles alone. ``tests/test_one_indicator_per_module.py`` fails when a
module grows a second indicator or reaches into another's maths.

Indicators, one module each under ``src/trading/indicators/``:
  1. Bollinger Bands — price position within bands, squeeze detection
  2. Vortex Indicator — VI+ / VI- crossovers for trend direction
  3. MACD — histogram direction, signal crossovers, divergence
  4. Stochastic RSI — overbought/oversold with K/D crossovers
  5. Ichimoku Cloud — Tenkan/Kijun cross, price vs cloud, future cloud
  6. Volume — OBV trend, volume spikes, accumulation/distribution
  7. Slingshot Indicator — momentum reversal detection via band breaks
  8. ADX / DMI — trend strength
  9. Supertrend — ATR trailing trend flip
 10. Z-Score — statistical extremity over a longer window than BB
 11. Kaufman Efficiency Ratio — market-quality regime classifier
 12. RSI — classical Wilder overbought / oversold with divergence
 13. ATR — volatility, an absolute measure
 14. FVG — fair-value-gap structural imbalance zones
 15. Heikin Ashi — the candle transform the Landing Strips read
 16. MACD taper — histogram deceleration and the wedge
 17. Landing Strip v1 — HA consolidation at a band extreme
 18. Landing Strip v2 — three-layer tightening
 19. Wyckoff Spring, W-Bottom, M-Top — structural detectors

Each voting indicator produces a Signal with:
  - direction: bullish (+1) / bearish (-1) / neutral (0)
  - confidence: 0.0 to 1.0
  - weight: configurable per-indicator importance

The VotingEngine aggregates those signals across indicators and timeframes
into a consensus. It computes no indicator maths itself: it calls each
indicator and adds up the votes.
"""

from __future__ import annotations

import time
from typing import Optional

# Re-exported rather than moved, so the split into one module each changed no caller.
from .indicators.adx import ADXIndicator
from .indicators.atr import ATRIndicator
from .indicators.bb_proximity import BBProximityResult, detect_bb_proximity
from .indicators.bollinger import BollingerBands
from .indicators.fvg import (
    FVG_BEAR_BOOST,
    FVG_BULL_BOOST,
    FVG_LOOKBACK,
    FVG_PROXIMITY_PCT,
    FVGIndicator,
)
from .indicators.heikin_ashi import HACandle, compute_heikin_ashi
from .indicators.helpers import (
    _ema,
    _sma,
    _sma_tail,
    _stdev,
    _stdev_tail,
    _true_range,
    _window_has_no_range,
)
from .indicators.ichimoku import IchimokuCloud
from .indicators.kaufman_er import KaufmanERIndicator
from .indicators.landing_strip import TighteningResult, detect_landing_strip_v2
from .indicators.m_top import detect_m_top
from .indicators.macd import MACD
from .indicators.macd_taper import detect_macd_taper
from .indicators.rsi import RSIIndicator
from .indicators.slingshot import SlingshotIndicator
from .indicators.spring import detect_volume_confirmed_spring
from .indicators.stochastic_rsi import StochasticRSI
from .indicators.supertrend import SupertrendIndicator
from .indicators.types import (
    HA_BODY_PCT_UNIT,
    NO_SHRINK_RATIO,
    PERCENT_PER_RATIO_UNIT,
    VOLUME_SPIKE_PCT,
    Candle,
    CandleDomainError,
    Signal,
    SignalDirection,
    VotingSummary,
    candles_from_raw,
)
from .indicators.volume import VolumeAnalysis
from .indicators.vortex import (
    VX_CEILING,
    VX_CEILING_PCT,
    VX_FLOOR,
    VX_FLOOR_PCT,
    VortexIndicator,
)
from .indicators.w_bottom import detect_w_bottom
from .indicators.zscore import ZScoreIndicator

__all__ = [
    # tests/test_ta_suffix_bit_identity.py imports the four underscore stats
    # names from here.
    "_ema",
    "_sma",
    "_sma_tail",
    "_stdev",
    "_stdev_tail",
    "_true_range",
    "_window_has_no_range",
    "ADXIndicator",
    "ATRIndicator",
    "BBProximityResult",
    "BollingerBands",
    "Candle",
    "CandleDomainError",
    "DEFAULT_WEIGHTS",
    "FVGIndicator",
    "FVG_BEAR_BOOST",
    "FVG_BULL_BOOST",
    "FVG_LOOKBACK",
    "FVG_PROXIMITY_PCT",
    "HACandle",
    "HA_BODY_PCT_UNIT",
    "IchimokuCloud",
    "KaufmanERIndicator",
    "MACD",
    "NO_SHRINK_RATIO",
    "PERCENT_PER_RATIO_UNIT",
    "RSIIndicator",
    "Signal",
    "SignalDirection",
    "SlingshotIndicator",
    "StochasticRSI",
    "SupertrendIndicator",
    "TA_RAW_PREFIX",
    "TighteningResult",
    "VOLUME_SPIKE_PCT",
    "VX_CEILING",
    "VX_CEILING_PCT",
    "VX_FLOOR",
    "VX_FLOOR_PCT",
    "VolumeAnalysis",
    "VortexIndicator",
    "VotingEngine",
    "VotingSummary",
    "ZScoreIndicator",
    "analyze",
    "candles_from_raw",
    "compute_heikin_ashi",
    "detect_bb_proximity",
    "detect_landing_strip_v2",
    "detect_m_top",
    "detect_macd_taper",
    "detect_volume_confirmed_spring",
    "detect_w_bottom",
]


DEFAULT_WEIGHTS = {
    "bollinger_bands": 1.0,
    "vortex": 0.9,
    "macd": 1.2,
    "stochastic_rsi": 1.0,
    "ichimoku": 1.1,
    "volume": 0.8,
    "slingshot": 1.0,
    "adx": 1.0,
    "kaufman_er": 1.0,  # Perry Kaufman Efficiency Ratio (regime classifier)
    "supertrend": 1.0,  # Olivier Seban ATR-trailing trend (reactive flip)
    "zscore": 0.9,  # Statistical extremity over a longer window than BB
    # Both are built on Wilder's RSI, so this vote overlaps stochastic_rsi.
    "rsi": 0.8,
}


class _TAInstrumentationOff(Exception):
    """Raised to skip the emitter block when no sink is installed."""


# Head of the raw emitter name; tests/test_ta_raw_prefix_consumer.py fails
# when this copy drifts from the emitter.
TA_RAW_PREFIX = "ta.07.004.postcondition.raw."


class VotingEngine:
    """Aggregates signals from all indicators into a consensus vote.

    Weighted voting: each indicator's contribution is scaled by its weight
    times its confidence, and the consensus is the absolute weighted mean of
    those contributions over the voters that did not abstain.

    ``confidence_threshold`` is held for callers to read; this class does not
    apply it. Nothing here filters or suppresses a consensus below it.

    Multi-timeframe: ``aggregate_multi_timeframe`` combines summaries from
    several timeframes, weighting higher timeframes more heavily.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._indicators = self._create_indicators()

    def _create_indicators(self) -> list:
        """Instantiate all indicator instances with configured weights."""
        return [
            BollingerBands(weight=self.weights.get("bollinger_bands", 1.0)),
            VortexIndicator(weight=self.weights.get("vortex", 0.9)),
            MACD(weight=self.weights.get("macd", 1.2)),
            StochasticRSI(weight=self.weights.get("stochastic_rsi", 1.0)),
            IchimokuCloud(weight=self.weights.get("ichimoku", 1.1)),
            VolumeAnalysis(weight=self.weights.get("volume", 0.8)),
            SlingshotIndicator(weight=self.weights.get("slingshot", 1.0)),
            ADXIndicator(weight=self.weights.get("adx", 1.0)),
            KaufmanERIndicator(weight=self.weights.get("kaufman_er", 1.0)),
            SupertrendIndicator(weight=self.weights.get("supertrend", 1.0)),
            ZScoreIndicator(weight=self.weights.get("zscore", 0.9)),
            RSIIndicator(weight=self.weights.get("rsi", 0.8)),
        ]

    def compute_all(
        self,
        candles: list[Candle],
        timeframe: str = "1h",
        symbol: Optional[str] = None,
    ) -> VotingSummary:
        """Run all indicators on *candles* and aggregate into a VotingSummary.

        Every indicator abstains rather than raising when *candles* is too
        short for its own formula, so a short tape returns a summary with no
        voters instead of an error.
        """
        # time.monotonic(), not a wall clock, because a wall clock can step backwards.
        _dur_t0 = time.monotonic()
        signals: list[Signal] = []
        for ind in self._indicators:
            sig = ind.compute(candles, timeframe)
            signals.append(sig)
        _dur_elapsed = time.monotonic() - _dur_t0

        # `window` records the input length, so a value can be recomputed
        # from the same candles.
        try:
            from src.core.signal_contract import emit as _ta_emit
            from src.core.signal_contract import get_sink as _ta_sink

            if _ta_sink() is None:
                # This runs on every candle of every live bot.
                raise _TAInstrumentationOff
            _ta_emit(
                "ta.07.003.postcondition.computed",
                actual=len(signals),
                expected=len(self._indicators),
                duration=_dur_elapsed,
                context={"timeframe": timeframe, "window": len(candles)},
            )

            # `Signal.details` carries each indicator's own internals,
            # recorded one row each.
            _last_ts = None
            if candles:
                # int, not float: a float ms epoch needs a cast to join
                # against tablet ints.
                _raw_ts = getattr(candles[-1], "timestamp", None)
                if _raw_ts is not None:
                    try:
                        _last_ts = int(_raw_ts)
                    except (TypeError, ValueError):
                        _last_ts = None
            from src.trading import ta_invariants as _ta_inv

            for _sig in signals:
                _details = dict(_sig.details or {})
                # `check` returns (None, None) when no bound applies, and never raises.
                _ok, _rule = _ta_inv.check(_sig.indicator, _details)
                _ta_emit(
                    f"ta.07.004.postcondition.raw.{_sig.indicator}",
                    actual=_details,
                    expected=_rule,
                    ok=_ok,
                    context={
                        "timeframe": timeframe,
                        "window": len(candles),
                        # candle_ts alone does not say which tablet the
                        # value came from.
                        "symbol": symbol,
                        "candle_ts": _last_ts,
                        "direction": _sig.direction.name,
                        "confidence": round(float(_sig.confidence), 6),
                        "weight": float(_sig.weight),
                    },
                )
        except _TAInstrumentationOff:
            pass
        except Exception:  # noqa: BLE001,S110 - instrumentation is advisory
            pass

        return self._aggregate(signals, timeframe)

    def aggregate_multi_timeframe(
        self,
        summaries: list[VotingSummary],
        timeframe_weights: Optional[dict[str, float]] = None,
    ) -> VotingSummary:
        """Combine VotingSummaries from multiple timeframes.

        Higher timeframes are weighted more heavily by default.
        """
        tf_weights = timeframe_weights or {
            "1m": 0.3,
            "5m": 0.5,
            "15m": 0.7,
            "30m": 0.85,
            "1h": 1.0,
            "2h": 1.1,
            "4h": 1.3,
            "6h": 1.35,
            "12h": 1.4,
            "1d": 1.5,
            "1w": 1.6,
        }

        all_signals: list[Signal] = []
        for summary in summaries:
            tf_w = tf_weights.get(summary.timeframe, 1.0)
            for sig in summary.signals:
                boosted = Signal(
                    indicator=sig.indicator,
                    timeframe=sig.timeframe,
                    direction=sig.direction,
                    confidence=sig.confidence,
                    weight=sig.weight * tf_w,
                    details=sig.details,
                    timestamp=sig.timestamp,
                    # `_aggregate` reads `abstained` off these rebuilt
                    # signals, not the originals.
                    abstained=sig.abstained,
                )
                all_signals.append(boosted)

        return self._aggregate(all_signals, "multi")

    def _aggregate(self, signals: list[Signal], timeframe: str) -> VotingSummary:
        """Compute voting totals from a list of signals."""
        bullish = 0
        bearish = 0
        neutral = 0
        bull_score = 0.0
        bear_score = 0.0

        for sig in signals:
            ws = sig.weighted_score
            if sig.direction == SignalDirection.BULLISH:
                bullish += 1
                bull_score += abs(ws)
            elif sig.direction == SignalDirection.BEARISH:
                bearish += 1
                bear_score += abs(ws)
            else:
                neutral += 1

        net = bull_score - bear_score

        # A weighted mean divides by the weight of the points included, and an
        # abstention is not one; it is NEUTRAL, so it adds nothing to `net`.
        # `IndicatorVotingPanel._setup_ui` states the same rule in its Conf tooltip.
        voted_weight = sum(s.weight for s in signals if not s.abstained)
        consensus_conf = abs(net) / voted_weight if voted_weight > 0.0 else 0.0

        return VotingSummary(
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            total_bullish_score=round(bull_score, 4),
            total_bearish_score=round(bear_score, 4),
            net_score=round(net, 4),
            consensus_confidence=round(min(1.0, consensus_conf), 4),
            signals=signals,
            timeframe=timeframe,
        )


def analyze(
    candles_by_timeframe: dict[str, list[list[float]]],
    weights: Optional[dict[str, float]] = None,
) -> tuple[VotingSummary, dict[str, VotingSummary]]:
    """Run full TA analysis across multiple timeframes.

    Parameters
    ----------
    candles_by_timeframe : dict
        Maps timeframe string to OHLCV lists: {"1h": [[ts,O,H,L,C,V], ...], ...}
    weights : dict, optional
        Custom indicator weights.

    Returns
    -------
    (multi_summary, per_timeframe)
        Overall multi-timeframe consensus and per-timeframe summaries.

    """
    engine = VotingEngine(weights=weights)
    per_tf: dict[str, VotingSummary] = {}

    for tf, raw in candles_by_timeframe.items():
        candles = candles_from_raw(raw)
        per_tf[tf] = engine.compute_all(candles, tf)

    multi = engine.aggregate_multi_timeframe(list(per_tf.values()))
    return multi, per_tf
