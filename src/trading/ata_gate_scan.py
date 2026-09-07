"""ata_gate_scan.py -- the live trade gates run over scanned price data.

``build_context`` fills a ``GateContext`` from one market's candles and its
``VotingSummary``. ``scan_gates`` hands that context to the chains
``build_scrumming_scrum_chain`` and ``build_scrumming_fold_chain`` build.
It answers a ``GateScan`` of ``GateReading`` rows, each naming one gate's
state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .container.config import BotConfig
from .gate_chain import (
    GateContext,
    build_scrumming_fold_chain,
    build_scrumming_scrum_chain,
)
from .indicators.bollinger import BollingerBands
from .indicators.landing_strip import detect_landing_strip_v2
from .indicators.types import SignalDirection
from .otd_math import minimum_opposing_trade_distance_pct

#: The keys ``BollingerBands.compute`` publishes in ``Signal.details``.
BAND_POSITION_KEY = "bb_position"
BAND_UPPER_KEY = "upper"
BAND_MIDDLE_KEY = "middle"
BAND_LOWER_KEY = "lower"

SCAN_EXCHANGE = "ata_smp_scan"
SCAN_QUOTE = "USD"
SYMBOL_SPLIT = "/"

STATE_LATCHED = "latched"
STATE_BLOCKED = "blocked"
STATE_NOT_RUN = "did not run"
STATE_HYPOTHETICAL = "hypothetical"

SIDE_SCRUM = "scrum"

#: The four gates a scan stands down; no hypothetical stands in for a
#: holding without inventing one.
NOT_APPLICABLE_GATES = (
    "delta_positive",
    "interval",
    "tranches_queued",
    "smart_ceiling",
)

#: The two gates a scan runs against an entry at the scanned price and
#: publishes as a distance.
HYPOTHETICAL_GATES = ("hysteresis_scrum", "hysteresis_fold")

POSITION_BOUND_GATES = NOT_APPLICABLE_GATES + HYPOTHETICAL_GATES

NOT_APPLICABLE_REASONS = {
    "delta_positive": "a scan holds nothing, and no surplus exists to test",
    "interval": "the same surplus, and a scan holds none of it",
    "tranches_queued": "a scan has no fold queue",
    "smart_ceiling": "a scan holds nothing, and any ceiling test passes",
}

HYPOTHETICAL_FORMAT = (
    "entry at ${price:.8f} would need ${required:.8f}, "
    "{distance:.2f}% away; no gate ran"
)

#: What a scan holds of a position: nothing on either side.
NO_DELTA = 0.0
NO_DELTA_PCT = 0.0
NO_TRANCHES = 0
NO_CEILING_USD = 0.0
NO_POSITION_USD = 0.0
BELOW_INTERVAL = True

MIDLINE_POSITION = 0.5
PERCENT_PER_RATIO_UNIT = 100.0
NO_BAND_VALUE = 0.0
DEFAULT_DETECT_PCT = 75.0
DEFAULT_SOFT_BREAKER_PCT = 25.0

#: ``ScrummingBot.tick`` reads the same two zones off ``bb_pos``.
UPPER_ZONE_FLOOR = 0.75
MIDDLE_ZONE = (0.35, 0.65)

#: The voter favours ``ScrummingBot.tick`` sums into ``position_boost``.
VORTEX_UPPER_FAVOUR = 0.12
VORTEX_MIDDLE_FAVOUR = -0.05
VORTEX_MIN_CONFIDENCE = 0.5
MACD_UPPER_FAVOUR = 0.08
MACD_MIDDLE_FAVOUR = -0.03
MACD_MIN_CONFIDENCE = 0.3
ICHIMOKU_BULL_FAVOUR = 0.05
ICHIMOKU_BEAR_FAVOUR = -0.05
STOCH_MIN_CONFIDENCE = 0.7
STOCH_BEAR_FAVOUR = 0.10
STOCH_BULL_FAVOUR = -0.08

#: The swing favours ``ScrummingBot.tick`` sums into the same total.
SWING_UPTREND_UPPER_FAVOUR = 0.05
SWING_UPTREND_MIDDLE_FAVOUR = -0.08
SWING_DOWNTREND_FAVOUR = 0.05
SWING_WINDOW = 20
SWING_CANDLES = SWING_WINDOW * 3

#: The landing-strip favour ``ScrummingBot.tick`` sums into the same skew.
LANDING_STRIP_FAVOUR = 0.15
LANDING_STRIP_STRENGTH_FAVOUR = 0.20
TIGHTENING_MIN_CANDLES = 25
TIGHTENING_MIN_CONSECUTIVE = 3
TIGHTENING_SHRINK_THRESHOLD = 0.90
TIGHTENING_TOLERANCE_PCT = 3.0

#: ``ScrummingBot.tick`` reads the trend from the last 20 candles.
TREND_CANDLES = 20
TREND_MIN_BULL_CANDLES = 13
TREND_MIN_BULL_SHARE = TREND_MIN_BULL_CANDLES / TREND_CANDLES

#: The band-touch tolerances ``ScrummingBot.tick`` spells inline.
BAND_TOUCH_TOLERANCE = 0.005
BAND_WICK_TOLERANCE = 0.002

RAMP_SEARCH = "search"
RAMP_TRACK = "track"
RAMP_FIRE = "fire"
BAND_SPAN_FLOOR = 1e-12
RETREAT_DIVISOR = 2.0

MIN_CANDLES_FOR_TA = 30
HTF_MIN_CONFIDENCE = 0.30
NO_WEIGHT = 0.0

DIRECTION_NAMES = {
    SignalDirection.BULLISH: "BULLISH",
    SignalDirection.BEARISH: "BEARISH",
    SignalDirection.NEUTRAL: "NEUTRAL",
}
BULLISH_NAME = DIRECTION_NAMES[SignalDirection.BULLISH]
BEARISH_NAME = DIRECTION_NAMES[SignalDirection.BEARISH]


@dataclass
class GateReading:
    """One gate as a scan read it: its side, its state and its evidence."""

    name: str
    side: str
    state: str
    detail: str = ""

    @property
    def ran(self) -> bool:
        """True while ``state`` is ``STATE_LATCHED`` or ``STATE_BLOCKED``."""
        return self.state in (STATE_LATCHED, STATE_BLOCKED)


@dataclass
class GateScan:
    """Every gate of both chains, as one market's scan read them."""

    symbol: str = ""
    timeframe: str = ""
    readings: list = field(default_factory=list)

    def named(self, state: Any) -> list:
        """The ``GateReading`` names in one state, in chain order."""
        return [one.name for one in self.readings if one.state == state]

    @property
    def latched(self) -> list:
        """The gates whose ``state`` is ``STATE_LATCHED``."""
        return self.named(STATE_LATCHED)

    @property
    def blocked(self) -> list:
        """The gates whose ``state`` is ``STATE_BLOCKED``."""
        return self.named(STATE_BLOCKED)

    @property
    def not_run(self) -> list:
        """Every gate whose ``GateReading.ran`` is False."""
        return [one.name for one in self.readings if not one.ran]

    @property
    def ran(self) -> int:
        """How many ``GateReading`` rows decided."""
        return sum(1 for one in self.readings if one.ran)


def scan_settings(symbol: Any) -> BotConfig:
    """The ``BotConfig`` one scanned market is gated with.

    ``SCAN_EXCHANGE`` names the scan, and every threshold is the
    ``BotConfig`` default.
    """
    named = str(symbol)
    base = named.partition(SYMBOL_SPLIT)[0] or named
    return BotConfig(
        exchange_id=SCAN_EXCHANGE,
        base_currency=SCAN_QUOTE,
        target_asset=base,
        symbol=named,
    )


def detect_thresholds(settings: Any) -> tuple:
    """The lower and upper detect thresholds in ``bb_pos`` terms.

    ``scrum_detect_pct`` is the percent of the midline-to-band distance,
    the reading ``CircuitBreakerMixin._bb_detect_thresholds`` takes.
    """
    raw = getattr(settings, "scrum_detect_pct", None)
    try:
        detect_pct = float(raw) if raw is not None else DEFAULT_DETECT_PCT
    except (TypeError, ValueError):
        detect_pct = DEFAULT_DETECT_PCT
    half = max(0.0, min(1.0, detect_pct / PERCENT_PER_RATIO_UNIT)) * MIDLINE_POSITION
    return (MIDLINE_POSITION - half, MIDLINE_POSITION + half)


def band_of(candles: Any) -> Optional[dict]:
    """``BollingerBands.compute`` upper, middle and lower over one window."""
    held = list(candles or [])
    if len(held) < TREND_CANDLES:
        return None
    details = getattr(BollingerBands().compute(held), "details", None) or {}
    upper = float(details.get(BAND_UPPER_KEY, NO_BAND_VALUE))
    lower = float(details.get(BAND_LOWER_KEY, NO_BAND_VALUE))
    if upper <= NO_BAND_VALUE or lower <= NO_BAND_VALUE:
        return None
    return {
        BAND_UPPER_KEY: upper,
        BAND_MIDDLE_KEY: float(details.get(BAND_MIDDLE_KEY, NO_BAND_VALUE)),
        BAND_LOWER_KEY: lower,
    }


def circuit_breaker_sides(candles: Any, soft_pct: Any) -> tuple:
    """Whether the newest candle trips the soft breaker on each side.

    The move is ``(high - low) / open`` against ``soft_pct``, and the
    close against the open picks the side.
    """
    held = list(candles or [])
    if not held:
        return (False, False)
    candle = held[-1]
    try:
        open_px = float(candle.open)
        high = float(candle.high)
        low = float(candle.low)
        close = float(candle.close)
        limit_ratio = float(soft_pct) / PERCENT_PER_RATIO_UNIT
    except (TypeError, ValueError, AttributeError):
        return (False, False)
    if open_px <= 0 or limit_ratio <= 0:
        return (False, False)
    move_ratio = (high - low) / open_px
    if move_ratio < limit_ratio:
        return (False, False)
    return (close >= open_px, close < open_px)


def ramp_step(mode: Any, price: Any, band: dict, settings: Any) -> str:
    """The ``RAMP_SEARCH``, ``RAMP_TRACK`` or ``RAMP_FIRE`` one candle moves to.

    The distance from ``BAND_MIDDLE_KEY`` against the band span decides
    it; the delta test ``_tick_target_ramp`` adds is dropped.
    """
    detect_frac = float(settings.scrum_detect_pct) / PERCENT_PER_RATIO_UNIT
    fire_frac = float(settings.scrum_fire_pct) / PERCENT_PER_RATIO_UNIT
    retreat_frac = detect_frac / RETREAT_DIVISOR
    middle = band[BAND_MIDDLE_KEY]
    edge = band[BAND_UPPER_KEY] if price > middle else band[BAND_LOWER_KEY]
    span = max(abs(edge - middle), BAND_SPAN_FLOOR)
    travel_frac = abs(price - middle) / span
    edge_gap_frac = abs(price - edge) / edge
    near_band = edge_gap_frac <= fire_frac
    if mode == RAMP_SEARCH:
        if near_band:
            return RAMP_FIRE
        return RAMP_TRACK if travel_frac >= detect_frac else RAMP_SEARCH
    if mode == RAMP_TRACK:
        if near_band:
            return RAMP_FIRE
        return RAMP_SEARCH if travel_frac < retreat_frac else RAMP_TRACK
    if not near_band and travel_frac >= detect_frac:
        return RAMP_TRACK
    return RAMP_SEARCH if travel_frac < retreat_frac else RAMP_FIRE


def ramp_mode(candles: Any, settings: Any) -> str:
    """The ramp state a walk of ``ramp_step`` over the whole window ends in.

    A scan carries no ramp from a previous tick, and the walk opens in
    ``RAMP_SEARCH``.
    """
    held = list(candles or [])
    mode = RAMP_SEARCH
    side = ""
    for at in range(TREND_CANDLES, len(held) + 1):
        band = band_of(held[:at])
        if band is None:
            continue
        price = float(held[at - 1].close)
        now = BAND_UPPER_KEY if price > band[BAND_MIDDLE_KEY] else BAND_LOWER_KEY
        if side and side != now:
            mode = RAMP_SEARCH
        side = now
        mode = ramp_step(mode, price, band, settings)
    return mode


def band_touch(price: Any, band: Any, candles: Any) -> tuple:
    """Whether ``price`` or the newest wick reaches the upper or lower band.

    ``BAND_TOUCH_TOLERANCE`` and ``BAND_WICK_TOLERANCE`` are the two
    tolerances ``ScrummingBot.tick`` reads around each band.
    """
    held = list(candles or [])
    upper = float(getattr(band, BAND_UPPER_KEY, NO_BAND_VALUE) or NO_BAND_VALUE)
    lower = float(getattr(band, BAND_LOWER_KEY, NO_BAND_VALUE) or NO_BAND_VALUE)
    if upper <= NO_BAND_VALUE or lower <= NO_BAND_VALUE:
        return (False, False)
    at_upper = abs(float(price) - upper) / upper < BAND_TOUCH_TOLERANCE
    at_lower = abs(float(price) - lower) / lower < BAND_TOUCH_TOLERANCE
    if held and not at_upper:
        at_upper = float(held[-1].high) >= upper * (1.0 - BAND_WICK_TOLERANCE)
    if held and not at_lower:
        at_lower = float(held[-1].low) <= lower * (1.0 + BAND_WICK_TOLERANCE)
    return (at_upper, at_lower)


def swing_favour(candles: Any, band_position: Any) -> float:
    """The higher-high and higher-low favour over three ``SWING_WINDOW`` windows.

    ``ScrummingBot.tick`` adds the same favour to ``position_boost``.
    """
    held = list(candles or [])
    if len(held) < SWING_CANDLES:
        return NO_WEIGHT
    highs = [float(one.high) for one in held[-SWING_CANDLES:]]
    lows = [float(one.low) for one in held[-SWING_CANDLES:]]
    recent_high = max(highs[-SWING_WINDOW:])
    prior_high = max(highs[-SWING_WINDOW * 2 : -SWING_WINDOW])
    recent_low = min(lows[-SWING_WINDOW:])
    prior_low = min(lows[-SWING_WINDOW * 2 : -SWING_WINDOW])
    at_upper = float(band_position) > UPPER_ZONE_FLOOR
    in_middle = MIDDLE_ZONE[0] <= float(band_position) <= MIDDLE_ZONE[1]
    if recent_high > prior_high and recent_low > prior_low:
        if at_upper:
            return SWING_UPTREND_UPPER_FAVOUR
        return SWING_UPTREND_MIDDLE_FAVOUR if in_middle else NO_WEIGHT
    if recent_high < prior_high and recent_low < prior_low:
        return SWING_DOWNTREND_FAVOUR
    return NO_WEIGHT


def vortex_favour(signal: Any, at_upper: Any, in_middle: Any) -> float:
    """The vortex favour, on a bullish vote at ``VORTEX_MIN_CONFIDENCE``."""
    if signal.direction != SignalDirection.BULLISH:
        return NO_WEIGHT
    if at_upper and signal.confidence > VORTEX_MIN_CONFIDENCE:
        return VORTEX_UPPER_FAVOUR
    return VORTEX_MIDDLE_FAVOUR if in_middle else NO_WEIGHT


def macd_favour(signal: Any, at_upper: Any, in_middle: Any) -> float:
    """The macd favour, on a bullish vote at ``MACD_MIN_CONFIDENCE``."""
    if signal.direction != SignalDirection.BULLISH:
        return NO_WEIGHT
    if at_upper and signal.confidence > MACD_MIN_CONFIDENCE:
        return MACD_UPPER_FAVOUR
    return MACD_MIDDLE_FAVOUR if in_middle else NO_WEIGHT


def ichimoku_favour(signal: Any, at_upper: Any, in_middle: Any) -> float:
    """The ichimoku favour, one value per direction and no band zone."""
    del at_upper, in_middle
    if signal.direction == SignalDirection.BULLISH:
        return ICHIMOKU_BULL_FAVOUR
    if signal.direction == SignalDirection.BEARISH:
        return ICHIMOKU_BEAR_FAVOUR
    return NO_WEIGHT


def stochastic_favour(signal: Any, at_upper: Any, in_middle: Any) -> float:
    """The stochastic_rsi favour, above ``STOCH_MIN_CONFIDENCE`` only."""
    del at_upper, in_middle
    if signal.confidence <= STOCH_MIN_CONFIDENCE:
        return NO_WEIGHT
    if signal.direction == SignalDirection.BEARISH:
        return STOCH_BEAR_FAVOUR
    return (
        STOCH_BULL_FAVOUR if signal.direction == SignalDirection.BULLISH else NO_WEIGHT
    )


#: The four voters ``ScrummingBot.tick`` reads for ``position_boost``.
VOTER_FAVOURS = {
    "vortex": vortex_favour,
    "macd": macd_favour,
    "ichimoku": ichimoku_favour,
    "stochastic_rsi": stochastic_favour,
}


def voter_favour(summary: Any, band_position: Any) -> float:
    """Every ``VOTER_FAVOURS`` reading off ``summary``, summed.

    ``ScrummingBot.tick`` sums the same four into ``position_boost``.
    """
    at_upper = float(band_position) > UPPER_ZONE_FLOOR
    in_middle = MIDDLE_ZONE[0] <= float(band_position) <= MIDDLE_ZONE[1]
    found = NO_WEIGHT
    for one in getattr(summary, "signals", []) or []:
        favour = VOTER_FAVOURS.get(one.indicator)
        if favour is not None:
            found += favour(one, at_upper, in_middle)
    return found


def landing_strip_favour(band: Any, candles: Any) -> float:
    """The landing-strip and tightening favour off the same two detectors.

    ``detect_bb_proximity`` names the strip on ``band`` and
    ``detect_landing_strip_v2`` names the tightening.
    """
    found = NO_WEIGHT
    if band is not None and getattr(band, "landing_strip", False):
        strength = float(getattr(band, "consolidation_strength", NO_WEIGHT))
        found = LANDING_STRIP_FAVOUR + strength * LANDING_STRIP_STRENGTH_FAVOUR
    held = list(candles or [])
    if len(held) < TIGHTENING_MIN_CANDLES:
        return found
    tightening = detect_landing_strip_v2(
        held,
        min_consecutive=TIGHTENING_MIN_CONSECUTIVE,
        shrink_threshold=TIGHTENING_SHRINK_THRESHOLD,
        bb_tolerance_pct=TIGHTENING_TOLERANCE_PCT,
    )
    if tightening.detected:
        found += float(tightening.confidence_boost)
    return found


def confidence_floor(summary: Any, band: Any, candles: Any) -> float:
    """The TA confidence floor a scan judges ``summary`` direction at.

    ``voter_favour``, ``swing_favour`` and ``landing_strip_favour`` are
    two of the three favours ``_skewed_confidence_floor`` divides by.
    """
    from .scrumming_bot import _skewed_confidence_floor

    position = float(getattr(band, BAND_POSITION_KEY, MIDLINE_POSITION))
    skew = (
        voter_favour(summary, position)
        + swing_favour(candles, position)
        + landing_strip_favour(band, candles)
    )
    return _skewed_confidence_floor(skew)


def bull_candle_count(candles: Any) -> int:
    """How many of the last ``TREND_CANDLES`` candles closed above their open."""
    held = list(candles or [])[-TREND_CANDLES:]
    return sum(1 for one in held if one.close > one.open)


def timeframe_weights(rows: Any, base_timeframe: Any, min_confidence: Any) -> list:
    """Each higher timeframe's ``rank * confidence`` weight and its net score.

    A timeframe at or below ``base_timeframe``, or under
    ``min_confidence``, carries no weight.
    """
    from .phantom_balance import tf_rank

    base_rank = tf_rank(str(base_timeframe))
    found: list = []
    for timeframe, row in dict(rows or {}).items():
        rank = tf_rank(str(timeframe))
        if rank <= base_rank:
            continue
        confidence = float(row.get("confidence", NO_WEIGHT) or NO_WEIGHT)
        if confidence < float(min_confidence):
            continue
        found.append(
            {
                "timeframe": str(timeframe),
                "weight": max(1, rank) * confidence,
                "net_score": float(row.get("net_score", NO_WEIGHT) or NO_WEIGHT),
                "direction": str(row.get("direction", "")),
            }
        )
    return found


def htf_bias(
    rows: Any, base_timeframe: Any, min_confidence: float = HTF_MIN_CONFIDENCE
) -> Optional[SignalDirection]:
    """The higher-timeframe consensus over ``timeframe_weights``.

    ``PhantomBalanceManager.get_higher_tf_bias`` weighs the same rows the
    same way; None answers that no higher timeframe was scanned.
    """
    weighted = timeframe_weights(rows, base_timeframe, min_confidence)
    if not weighted:
        return None
    bull = sum(one["weight"] for one in weighted if one["direction"] == BULLISH_NAME)
    bear = sum(one["weight"] for one in weighted if one["direction"] == BEARISH_NAME)
    if bull > bear:
        return SignalDirection.BULLISH
    if bear > bull:
        return SignalDirection.BEARISH
    return SignalDirection.NEUTRAL


def composite_net(
    rows: Any,
    base_timeframe: Any,
    base_net: Any,
    min_confidence: float = HTF_MIN_CONFIDENCE,
) -> float:
    """``base_net`` and every higher net score, weighted by rank and confidence.

    This is the Comp column of the Indicator Voting Panel, over the same
    ``timeframe_weights`` the live feed weighs.
    """
    from .phantom_balance import tf_rank

    base_rank = max(1, tf_rank(str(base_timeframe)))
    numerator = float(base_net) * base_rank
    denominator = float(base_rank)
    for one in timeframe_weights(rows, base_timeframe, min_confidence):
        numerator += one["net_score"] * one["weight"]
        denominator += one["weight"]
    if denominator <= NO_WEIGHT:
        return float(base_net)
    return numerator / denominator


def signal_detail(summary: Any, indicator: Any, key: Any) -> float:
    """One voter's published reading off ``summary``, or ``NO_WEIGHT``."""
    from .scrumming_bot import _extract_signal_detail

    return _extract_signal_detail(summary, str(indicator), str(key), NO_WEIGHT)


def build_context(
    symbol: Any,
    timeframe: Any,
    candles: Any,
    summary: Any,
    band: Any,
    rows: Any = None,
    settings: Any = None,
) -> GateContext:
    """One market's ``GateContext``, filled from price data and settings.

    Every position field carries what a scan holds, and ``read_chain``
    stands the six ``POSITION_BOUND_GATES`` down.
    """
    held = settings if settings is not None else scan_settings(symbol)
    price = float(candles[-1].close) if candles else NO_BAND_VALUE
    bb_pos = float(getattr(band, BAND_POSITION_KEY, MIDLINE_POSITION))
    lower_dt, upper_dt = detect_thresholds(held)
    floor = confidence_floor(summary, band, candles)
    direction = getattr(summary, "consensus_direction", SignalDirection.NEUTRAL)
    confidence = float(getattr(summary, "consensus_confidence", NO_WEIGHT))
    at_upper, at_lower = band_touch(price, band, candles)
    is_bullish = (
        direction in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
        and confidence >= floor
    )
    is_bearish = (
        direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
        and confidence >= floor
    )
    strip_side = str(getattr(band, "landing_strip_side", "") or "")
    if getattr(band, "landing_strip", False) and strip_side == "upper":
        is_bullish = True
    if getattr(band, "landing_strip", False) and strip_side == "lower":
        is_bearish = True
    trend_strength = bull_candle_count(candles) / TREND_CANDLES
    trend_hold = trend_strength > TREND_MIN_BULL_SHARE
    blocks_scrum, blocks_fold = circuit_breaker_sides(
        candles,
        getattr(held, "circuit_breaker_soft_pct", DEFAULT_SOFT_BREAKER_PCT),
    )
    bias = htf_bias(rows, timeframe)
    htf_blocks_scrum = bias == SignalDirection.BULLISH
    htf_blocks_fold = bias == SignalDirection.BEARISH
    midline_gate = bool(getattr(held, "bb_midline_gate", True))
    return GateContext(
        symbol=str(symbol),
        ticker_last=price,
        bb_pos=bb_pos,
        bb_upper_dt=upper_dt,
        bb_lower_dt=lower_dt,
        delta=NO_DELTA,
        delta_pct=NO_DELTA_PCT,
        below_interval=BELOW_INTERVAL,
        is_bullish=is_bullish,
        is_bearish=is_bearish,
        trend_hold=trend_hold,
        trend_strength=trend_strength,
        eff_direction_name=DIRECTION_NAMES.get(direction, ""),
        eff_is_bullish=is_bullish or not held.scrum_require_ta_bullish,
        eff_is_bearish=is_bearish or not held.fold_require_ta_bearish,
        eff_trend_hold=trend_hold and bool(held.scrum_hold_in_uptrend),
        eff_htf_blocks_scrum=htf_blocks_scrum and bool(held.scrum_defer_to_htf),
        eff_htf_blocks_fold=htf_blocks_fold and bool(held.fold_defer_to_htf),
        flag_require_ta_bullish=bool(held.scrum_require_ta_bullish),
        flag_hold_in_uptrend=bool(held.scrum_hold_in_uptrend),
        flag_defer_to_htf=bool(held.scrum_defer_to_htf),
        flag_fold_require_ta_bearish=bool(held.fold_require_ta_bearish),
        flag_fold_defer_to_htf=bool(held.fold_defer_to_htf),
        bb_above_upper_dt=(bb_pos >= upper_dt) or at_upper,
        bb_below_lower_dt=(bb_pos <= lower_dt) or at_lower,
        scrum_ok=(bb_pos > MIDLINE_POSITION) if midline_gate else True,
        fold_ok_midline=(bb_pos < MIDLINE_POSITION) if midline_gate else True,
        target_fires=ramp_mode(candles, held) == RAMP_FIRE,
        cb_blocks_scrum=blocks_scrum,
        cb_blocks_fold=blocks_fold,
        hyst_ok_scrum_side=False,
        hyst_ok_fold_side=False,
        hyst_armed_scrum_side=False,
        hyst_armed_fold_side=False,
        hyst_ref_scrum_side=price,
        hyst_ref_fold_side=price,
        mem253_at_ceiling=False,
        mem253_smart_ceiling_usd=NO_CEILING_USD,
        mem253_current_pos=NO_POSITION_USD,
        has_fold_tranches=False,
        n_fold_tranches=NO_TRANCHES,
        htf_bias_name=DIRECTION_NAMES.get(bias) if bias is not None else None,
        htf_blocks_scrum=htf_blocks_scrum,
        htf_blocks_fold=htf_blocks_fold,
        scrumming_interval_pct=float(held.scrumming_interval_pct),
        trading_fee_pct=float(held.trading_fee_pct),
        adx=signal_detail(summary, "adx", "adx"),
        efficiency_ratio=signal_detail(summary, "kaufman_er", "er"),
        z_score=signal_detail(summary, "zscore", "z"),
    )


def hypothetical_reading(context: GateContext, side: Any) -> str:
    """What one hysteresis gate publishes against an entry at ``ticker_last``.

    ``minimum_opposing_trade_distance_pct`` gives the distance, and
    ``HYPOTHETICAL_FORMAT`` prints a price with no verdict.
    """
    distance = minimum_opposing_trade_distance_pct(
        context.scrumming_interval_pct, context.trading_fee_pct
    )
    ratio = distance / PERCENT_PER_RATIO_UNIT
    factor = 1.0 + ratio if side == SIDE_SCRUM else 1.0 - ratio
    return HYPOTHETICAL_FORMAT.format(
        price=context.ticker_last,
        required=context.ticker_last * factor,
        distance=distance,
    )


def read_chain(chain: Any, context: GateContext) -> list:
    """One chain's gates as ``GateReading`` rows.

    The verdicts come off the ``ChainResult`` the shipped chain answered,
    and every ``POSITION_BOUND_GATES`` name is stood down.
    """
    result = chain.evaluate(context)
    blocked = dict(result.blocked)
    found: list = []
    for name in chain.gate_names():
        if name in NOT_APPLICABLE_GATES:
            found.append(
                GateReading(
                    name,
                    chain.side,
                    STATE_NOT_RUN,
                    NOT_APPLICABLE_REASONS[name],
                )
            )
        elif name in HYPOTHETICAL_GATES:
            found.append(
                GateReading(
                    name,
                    chain.side,
                    STATE_HYPOTHETICAL,
                    hypothetical_reading(context, chain.side),
                )
            )
        elif name in blocked:
            found.append(GateReading(name, chain.side, STATE_BLOCKED, blocked[name]))
        elif name in result.passed:
            found.append(GateReading(name, chain.side, STATE_LATCHED))
    return found


def scan_gates(
    symbol: Any,
    timeframe: Any,
    candles: Any,
    summary: Any,
    band: Any,
    rows: Any = None,
    settings: Any = None,
) -> GateScan:
    """Both chains run over one scanned market, as one ``GateScan``.

    A window under ``MIN_CANDLES_FOR_TA`` answers an empty ``GateScan``.
    """
    held = list(candles or [])
    if len(held) < MIN_CANDLES_FOR_TA or summary is None or band is None:
        return GateScan(symbol=str(symbol), timeframe=str(timeframe))
    context = build_context(symbol, timeframe, held, summary, band, rows, settings)
    readings = read_chain(build_scrumming_scrum_chain(), context) + read_chain(
        build_scrumming_fold_chain(), context
    )
    return GateScan(symbol=str(symbol), timeframe=str(timeframe), readings=readings)
