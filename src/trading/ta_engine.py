"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
ta_engine.py — Technical Analysis Engine v1.1
==============================================
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ THE INDICATORS NO LONGER LIVE HERE. Issue #73 moved each    │
# │ one into its own module under src/trading/indicators/.      │
# │ This file now holds the CONSUMER — the VotingEngine — and   │
# │ re-exports the package, so every existing import path       │
# │ ``from ..trading.ta_engine import X`` still resolves.       │
# │                                                             │
# │ WHY ONE FILE EACH. Indicator formulae are PUBLISHED. Each   │
# │ indicator has its own discrete maths and is never blended   │
# │ with another's. Nineteen of them in one file made that a    │
# │ habit; one file each makes it structural, and               │
# │ tests/test_one_indicator_per_module.py fails if a module    │
# │ grows a second indicator or reaches into another's maths.   │
# │                                                             │
# │ Three novel inventions live in the package:                 │
# │                                                             │
# │ 1. detect_bb_proximity() — Landing Strip v1                 │
# │    indicators/bb_proximity.py                               │
# │    Detects HA body consolidation at BB band extremes.       │
# │    Returns BBProximityResult with landing_strip flag.       │
# │                                                             │
# │ 2. detect_landing_strip_v2() — Tightening Detection         │
# │    indicators/landing_strip.py                              │
# │    Gradient-based: measures if consecutive HA bodies are     │
# │    SHRINKING (each smaller than the last). More reliable    │
# │    than v1's absolute threshold. Inspired by CogNex edge    │
# │    detection from semiconductor wafer inspection.           │
# │    Uses compute_heikin_ashi() internally — confirmed [HA✓]. │
# │                                                             │
# │ 3. compute_heikin_ashi() — HA candle computation            │
# │    indicators/heikin_ashi.py                                │
# │    Used for BOTH chart rendering AND LS detection.          │
# │    HA smooths noise; body_pct measures trend exhaustion.    │
# │                                                             │
# │ POSITION-AWARE TA (the BONK insight):                       │
# │    The same VX/MACD signal means different things at        │
# │    different BB positions. Strong VX bullish AT the upper   │
# │    band = price being PUSHED into resistance = SELL signal. │
# │    Same signal in the MIDDLE = weak/ignore.                 │
# │    This reinterpretation happens in the simulator's         │
# │    _sim_scrumming_tick(), NOT in this file.                 │
# │                                                             │
# │ Import path: from ..trading.ta_engine import ...            │
# │ (NOT from .ta_engine — that's the bug that killed LS v2)   │
# └─────────────────────────────────────────────────────────────┘

Comprehensive TA signal processing for Accumulation Trading bots.

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

The VotingEngine below aggregates signals across indicators AND
timeframes, producing a final consensus with configurable thresholds.
It is the only thing in this file that computes, and it computes
nothing itself: it calls each indicator and adds up the votes.
"""

from __future__ import annotations

import time
from typing import Optional

# ── THE PACKAGE'S FRONT DOOR ────────────────────────────────────────────
# Nineteen call sites across src/, tools/ and tests/ import these names
# from `ta_engine`. The names are re-exported rather than moved so the
# split changes no caller, and `__all__` states that the re-export is
# deliberate rather than a leftover.
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
    # The seven leading-underscore names are re-exported DELIBERATELY.
    # `tests/test_ta_suffix_bit_identity.py` and
    # `tests/test_ta_engine_degenerate_abstention.py` import `_sma`,
    # `_sma_tail`, `_stdev`, `_stdev_tail` from here, and this list is
    # what says so: without it they read as dead imports left behind by
    # the issue #73 split.
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


# ===========================================================================
# VOTING ENGINE
# ===========================================================================

# Default indicator weights
DEFAULT_WEIGHTS = {
    "bollinger_bands": 1.0,
    "vortex": 0.9,
    "macd": 1.2,
    "stochastic_rsi": 1.0,
    "ichimoku": 1.1,
    "volume": 0.8,
    "slingshot": 1.0,
    "adx": 1.0,     # P2.9 / MEM-200 — trend-strength signal. Structural tier.
    # ── v3.19.17: indicator-coverage P0 closure (Trading-Discipline Arc #2) ──
    # Three voters previously built as full classes (Sessions 15-17 era) but
    # never wired into VotingEngine. Filed as UNWIRED in the v3.19.16
    # indicator-coverage audit. Wiring matches v3.19.16 ADX template.
    "kaufman_er":  1.0,   # Perry Kaufman Efficiency Ratio (regime classifier)
    "supertrend":  1.0,   # Oliver Seban ATR-trailing trend (reactive flip)
    "zscore":      0.9,   # Statistical extremity (longer window than BB)
    # ── v3.19.18: last UNWIRED indicator from v3.19.16 audit closed ──
    # Plain RSI weighted lower than StochRSI (1.0) because they overlap;
    # StochRSI is the more refined two-stage indicator. Both voting now —
    # the small redundancy is acceptable because RSI's classical 70/30
    # divergence detection still adds independent information.
    "rsi":         0.8,
}


class _TAInstrumentationOff(Exception):
    """Raised to skip the emitter block when no sink is installed.

    A sentinel rather than a flag so the existing `try` around the
    instrumentation is the single exit — the block is one unit, and
    half-emitting it would produce a
    `ta.07.003.postcondition.computed` with no matching
    `ta.07.004.postcondition.raw.*` rows.
    """


TA_RAW_PREFIX = "ta.07.004.postcondition.raw."


"""The literal head of the per-indicator raw pin, 07-004.

Queue item 10.2. Every consumer that recovers the indicator from the
record name reads the leaf as `name[len(TA_RAW_PREFIX):]`. Before this
constant existed, `fleet_replay_controller` sliced with a hardcoded 7 —
the length of the old `ta.raw.` prefix — so the rename would have made
its filter match nothing and the `ta.invariants` rollup would have
reported `actual=0` violations over `indicators=0` on every run. A
passing record asserting that no indicator ever broke its bound,
produced by a filter that saw no indicators at all.

THE LITERAL IN THE PIN IS THE AUTHORITY, not this constant. The pin
spells the prefix out inside its own f-string because
`tools/emitter_registry_check.py` reads the name off the syntax tree: a
name assembled from a variable renders as `{}{}`, loses its subsystem
token and falls out of the register. So this is a copy, and
`tests/test_ta_raw_prefix_consumer.py` fails when the copy drifts from
the string the engine actually emits.
"""


class VotingEngine:
    """
    Aggregates signals from all indicators into a consensus vote.

    Features:
      - Weighted voting: each indicator's contribution is scaled by
        its weight × confidence.
      - Confidence threshold: consensus is only actionable if total
        confidence exceeds a minimum threshold.
      - Multi-timeframe: can aggregate across timeframes with higher
        timeframes weighted more heavily.
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
            # P2.9 / MEM-200 — ADX trend-strength indicator. Class fully
            # implemented since Session 15 but never consumed. Added to
            # address Manual Part 6 L4 (Oscillators Lead) objection.
            ADXIndicator(weight=self.weights.get("adx", 1.0)),
            # ── v3.19.17 (Trading-Discipline Arc #2 — indicator-coverage P0) ──
            # Three indicators built as full classes but never wired. Surfaced
            # by docs/audits/2026-05-22_indicator_coverage_audit.md and elevated
            # to P0 by operator 2026-05-22 ("the TA engine not being built
            # properly is also P0"). Wired into VotingEngine here; KaufmanER
            # additionally gets a discrete GateContext field + dedicated
            # SCRUM-suppressor gate (EfficiencyRatioRegimeGate) — see
            # gate_chain.py. The L3.b "ER is the Anti-pattern substitute"
            # claim in Part 6 — false at write time — becomes true with this
            # wiring.
            KaufmanERIndicator(weight=self.weights.get("kaufman_er", 1.0)),
            SupertrendIndicator(weight=self.weights.get("supertrend", 1.0)),
            ZScoreIndicator(weight=self.weights.get("zscore", 0.9)),
            # ── v3.19.18 — last UNWIRED indicator closed ──
            # Plain RSI refactored from dict-returning to Signal-returning
            # compute() in this ship (closes the v3.19.16 audit P0 fully).
            # See class docstring + _compute_metrics() for the dict form
            # that any external consumer of the rich detail still needs.
            RSIIndicator(weight=self.weights.get("rsi", 0.8)),
        ]

    def compute_all(
        self, candles: list[Candle], timeframe: str = "1h",
        symbol: Optional[str] = None,
    ) -> VotingSummary:

        # sadp: R28  # TA computation: fail-loudly on insufficient candles(R28)
        """
        Run all indicators on *candles* and aggregate into a VotingSummary.
        """
        # 10.3 phase 2 — BRACKET THE REAL WORK, not the emit.
        #
        # This is the operation `ta.07.003.postcondition.computed`
        # observes, so it is the only interval that emitter may honestly
        # claim. `time.monotonic()` because a wall clock can step
        # backwards; measured resolution on the target machine is 1e-07,
        # so a sub-millisecond compute is still distinguishable.
        #
        # COST, MEASURED rather than assumed, because this runs on every
        # candle of every live bot: `time.monotonic()` is 38 ns a call,
        # so the pair adds ~76 ns to a compute_all that runs every
        # indicator over the whole window. The emit block below is
        # skipped entirely when nobody is collecting; this is not,
        # deliberately, because the timer must bracket the work whether
        # or not a sink was installed before it started.
        _dur_t0 = time.monotonic()
        signals: list[Signal] = []
        for ind in self._indicators:
            sig = ind.compute(candles, timeframe)
            signals.append(sig)
        _dur_elapsed = time.monotonic() - _dur_t0

        # ── DIRECTIVE 2 EMITTER — "actual per-candle TA every tick" ──
        #
        # THE SIGNAL THAT DID NOT EXIST. Nothing anywhere counted TA
        # computations, so a run's artifacts could not distinguish
        # "TA on 100% of candles" from "TA on 2%". That is why the
        # per-candle-TA claim survived: it was unfalsifiable, not merely
        # unchecked.
        #
        # THIS is the true count — every TA computation in the platform
        # passes through here. It is not inferred from a tick counter or
        # from a config flag; the emit happens where the work happens.
        #
        # `window` is recorded because directive 2 is about per-CANDLE
        # computation: without the input length, a value cannot be
        # independently recomputed and the emitter would only prove that
        # something ran, not that it ran on the right data.
        #
        # Costs nothing when no sink is installed — a dict lookup and a
        # return. Live runs collect nothing unless a sink is set.
        try:
            from src.core.signal_contract import emit as _ta_emit
            from src.core.signal_contract import get_sink as _ta_sink
            if _ta_sink() is None:
                # Nothing is collecting. Skip the whole block rather
                # than build context dicts and evaluate invariants for
                # a call that returns None on its first line — this
                # runs on every candle of every live bot.
                raise _TAInstrumentationOff
            _ta_emit("ta.07.003.postcondition.computed", actual=len(signals),
                     expected=len(self._indicators),
                     duration=_dur_elapsed,
                     context={"timeframe": timeframe,
                              "window": len(candles)})

            # ── RAW INDICATOR VALUES ────────────────────────────────
            # Operator directive 2026-08-08: "Should also explore
            # capturing the raw indicator values so we [have] more
            # comparative data."
            #
            # `Signal.details` already holds each indicator's own
            # internals — bollinger's upper/middle/lower/bb_position,
            # rsi's rsi, macd's macd_line/signal_line/histogram,
            # zscore's z/sma/std. Nothing persisted them, so a run's
            # artifacts held a DIRECTION and a CONFIDENCE but not the
            # numbers those were derived from. Two runs could disagree
            # with no way to see where they diverged.
            #
            # Recorded per indicator, not as one blob, so a single
            # indicator can be queried across a whole run.
            #
            # `candle_ts` and `window` are what make a value
            # RECOMPUTABLE: with the closing timestamp and the input
            # length, the same value can be derived independently from
            # the tablet and compared. A raw value with no address is
            # not comparative data.
            _last_ts = None
            if candles:
                # int, not float. Candle.timestamp is a float, so a
                # millisecond epoch was being recorded as
                # 1776789300000.0 -- which cannot represent every ms
                # past 2^53 and forces a cast to join against tablet
                # ints. This is an ADDRESS; it must be exact.
                _raw_ts = getattr(candles[-1], "timestamp", None)
                if _raw_ts is not None:
                    try:
                        _last_ts = int(_raw_ts)
                    except (TypeError, ValueError):
                        _last_ts = None
            from src.trading import ta_invariants as _ta_inv
            for _sig in signals:
                _details = dict(_sig.details or {})
                # THE RECORD NOW CARRIES A VERDICT, NOT JUST A VALUE.
                #
                # Every `ta.07.004.postcondition.raw.*` record used to
                # emit with no
                # `expected`, so `Signal.ok` came back None and the row
                # was a transcript. ADX sat at up to 761.5 — seven times
                # its definitional maximum — across 1174 such rows and
                # nothing objected, because nothing had been ASKED to.
                #
                # `check` returns (None, None) when it has no applicable
                # bound, which reproduces the old behaviour exactly for
                # indicators and warm-up paths it cannot speak to. It
                # never raises.
                _ok, _rule = _ta_inv.check(_sig.indicator, _details)
                _ta_emit(
                    f"ta.07.004.postcondition.raw.{_sig.indicator}",
                    actual=_details,
                    expected=_rule, ok=_ok,
                    context={"timeframe": timeframe,
                             "window": len(candles),
                             # WITHOUT THE SYMBOL THE ADDRESS IS
                             # INCOMPLETE. candle_ts alone does not say
                             # WHICH tablet the value came from, so a
                             # raw record could not be joined back to
                             # its own input and independently
                             # recomputed -- the whole point of keeping
                             # it. Optional so live callers are
                             # unaffected.
                             "symbol": symbol,
                             "candle_ts": _last_ts,
                             "direction": _sig.direction.name,
                             "confidence": round(float(_sig.confidence), 6),
                             "weight": float(_sig.weight)})
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
        """
        Combine VotingSummaries from multiple timeframes.
        Higher timeframes are weighted more heavily by default.

        Default timeframe weights:
          5m=0.5, 15m=0.7, 1h=1.0, 4h=1.3, 1d=1.5
        """
        tf_weights = timeframe_weights or {
            "1m": 0.3, "5m": 0.5, "15m": 0.7, "30m": 0.85,
            "1h": 1.0, "2h": 1.1, "4h": 1.3, "6h": 1.35,
            "12h": 1.4, "1d": 1.5, "1w": 1.6,
        }

        all_signals: list[Signal] = []
        for summary in summaries:
            tf_w = tf_weights.get(summary.timeframe, 1.0)
            for sig in summary.signals:
                # Apply timeframe weight multiplier
                boosted = Signal(
                    indicator=sig.indicator,
                    timeframe=sig.timeframe,
                    direction=sig.direction,
                    confidence=sig.confidence,
                    weight=sig.weight * tf_w,
                    details=sig.details,
                    timestamp=sig.timestamp,
                    # THE FLAG MUST SURVIVE THE COPY. `_aggregate` reads
                    # `abstained` off the signals THIS loop builds, not
                    # off the originals, so a rebuild that dropped it
                    # would put every abstaining voter's timeframe-
                    # boosted weight back into the multi-timeframe
                    # denominator while the per-timeframe one stayed
                    # correct -- the repair working everywhere except
                    # the number the fleet actually reads.
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

        # THE DENOMINATOR IS THE WEIGHT THAT VOTED — issue #100.
        # ------------------------------------------------------
        # `consensus_confidence` is a WEIGHTED ARITHMETIC MEAN of each
        # voter's signed conviction `direction x confidence`, taken in
        # absolute value. The published definition of that mean fixes
        # its denominator: it is the sum of the weights of the data
        # points INCLUDED IN THE CALCULATION. A voter that abstained
        # contributed no data point, so its weight is not one of them.
        #
        # This line used to read `sum(s.weight for s in signals)`. That
        # summed the weight of every voter the engine ASKED, not the
        # weight of every voter that ANSWERED, so an indicator with too
        # little history to evaluate its own formula still occupied a
        # share of the maximum the numerator was measured against. The
        # displayed number was diluted by a quantity no candle produced.
        #
        # The panel already told the operator this was the rule.
        # `src/gui/indicator_panel.py:1025` documents the field as
        # "|Net| / total_weight_of_active_voters" -- the code and its
        # own tooltip disagreed, and the tooltip was right.
        #
        # MEASURED over 406 stone tablets, the abstaining share of the
        # old denominator, by tape length:
        #     35 bars  34.21% mean   42.74% worst tablet   406/406 hit
        #     40 bars  25.68% mean   42.74% worst tablet   406/406 hit
        #     60 bars   9.44% mean   17.95% worst tablet   406/406 hit
        #    100 bars   0.06% mean   25.64% worst tablet     3/406 hit
        #    200 bars   0.06% mean   25.64% worst tablet     3/406 hit
        #    400 bars   0.14% mean   41.03% worst tablet     6/406 hit
        # The live fetch is 100 candles (`scrumming_bot.py:7500`), where
        # only a degenerate book abstains -- but a bot that has just
        # spawned holds the short tape, and there the dilution is a
        # third of the denominator on every symbol measured.
        #
        # WHEN NOBODY VOTED. `voted_weight` is then exactly 0.0 and so
        # is `net`: an abstention is NEUTRAL, `weighted_score` multiplies
        # by `direction.value == 0`, and neither score accumulates. The
        # quotient is 0/0, which is UNDEFINED and is not a confidence of
        # any size. This returns 0.0 -- no vote -- which is the rule
        # `tests/test_ta_engine_degenerate_abstention.py` already holds
        # every division in this package to. It is NOT a guard against
        # ZeroDivisionError standing in for a decision; the decision is
        # that an engine with no voters has no consensus.
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


# ---------------------------------------------------------------------------
# Convenience: single-function TA analysis
# ---------------------------------------------------------------------------
def analyze(
    candles_by_timeframe: dict[str, list[list[float]]],
    weights: Optional[dict[str, float]] = None,
) -> tuple[VotingSummary, dict[str, VotingSummary]]:
    """
    Run full TA analysis across multiple timeframes.

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
