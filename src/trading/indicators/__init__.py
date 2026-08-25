"""One indicator per module.

WHY THIS PACKAGE EXISTS. Indicator formulae are PUBLISHED. Each
indicator has its own discrete maths and is never blended with
another's. Issue #73 found nineteen of them in one 4,009-line file,
which made that rule a habit rather than a structure.

THE SEAM. Two modules hold what is genuinely shared, and neither one
computes an indicator's output:

  * ``types``   -- the signal vocabulary (SignalDirection, Signal,
                   VotingSummary), the candle domain (Candle,
                   CandleDomainError, candles_from_raw) and the unit
                   constants. Data and types only.
  * ``helpers`` -- the stateless scalar maths several published
                   formulae are each built from: the moving average,
                   the rolling deviation, the EMA, the true range.

Everything shared is a function, a frozen scalar, or a type. Nothing
shared is a mutable object handed to more than one reader.

Every other module holds exactly ONE indicator and imports only
``types``, ``helpers`` and the standard library. There is one declared
exception -- both Landing Strip detectors read ``compute_heikin_ashi``,
because Heikin Ashi is a candle TRANSFORM rather than a voter and both
detectors are defined in terms of it. That edge is named in
``tests/test_one_indicator_per_module.py``, which fails if a second one
appears or if any module grows a second indicator.

The public surface is unchanged: ``src/trading/ta_engine.py``
re-exports every name in this package, so ``from ..trading.ta_engine
import X`` still resolves for every existing caller.
"""

from __future__ import annotations

from .adx import ADXIndicator
from .atr import ATRIndicator
from .bb_proximity import BBProximityResult, detect_bb_proximity
from .bollinger import BollingerBands
from .fvg import (
    FVG_BEAR_BOOST,
    FVG_BULL_BOOST,
    FVG_LOOKBACK,
    FVG_PROXIMITY_PCT,
    FVGIndicator,
)
from .heikin_ashi import HACandle, compute_heikin_ashi
from .ichimoku import IchimokuCloud
from .kaufman_er import KaufmanERIndicator
from .landing_strip import TighteningResult, detect_landing_strip_v2
from .m_top import detect_m_top
from .macd import MACD
from .macd_taper import detect_macd_taper
from .rsi import RSIIndicator
from .slingshot import SlingshotIndicator
from .spring import detect_volume_confirmed_spring
from .stochastic_rsi import StochasticRSI
from .supertrend import SupertrendIndicator
from .types import (
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
from .volume import VolumeAnalysis
from .vortex import (
    VX_CEILING,
    VX_CEILING_PCT,
    VX_FLOOR,
    VX_FLOOR_PCT,
    VortexIndicator,
)
from .w_bottom import detect_w_bottom
from .zscore import ZScoreIndicator

#: The module that holds each indicator. The guard test reads this, so
#: a module added without a line here is a test failure, not a silence.
INDICATOR_MODULES = {
    "adx": "ADXIndicator",
    "atr": "ATRIndicator",
    "bb_proximity": "detect_bb_proximity",
    "bollinger": "BollingerBands",
    "fvg": "FVGIndicator",
    "heikin_ashi": "compute_heikin_ashi",
    "ichimoku": "IchimokuCloud",
    "kaufman_er": "KaufmanERIndicator",
    "landing_strip": "detect_landing_strip_v2",
    "m_top": "detect_m_top",
    "macd": "MACD",
    "macd_taper": "detect_macd_taper",
    "rsi": "RSIIndicator",
    "slingshot": "SlingshotIndicator",
    "spring": "detect_volume_confirmed_spring",
    "stochastic_rsi": "StochasticRSI",
    "supertrend": "SupertrendIndicator",
    "volume": "VolumeAnalysis",
    "vortex": "VortexIndicator",
    "w_bottom": "detect_w_bottom",
    "zscore": "ZScoreIndicator",
}

#: The two modules that carry what is genuinely shared. Neither one
#: computes an indicator's output.
SHARED_MODULES = ("types", "helpers")

__all__ = [
    "ADXIndicator",
    "ATRIndicator",
    "BBProximityResult",
    "BollingerBands",
    "Candle",
    "CandleDomainError",
    "FVGIndicator",
    "FVG_BEAR_BOOST",
    "FVG_BULL_BOOST",
    "FVG_LOOKBACK",
    "FVG_PROXIMITY_PCT",
    "HACandle",
    "HA_BODY_PCT_UNIT",
    "INDICATOR_MODULES",
    "IchimokuCloud",
    "KaufmanERIndicator",
    "MACD",
    "NO_SHRINK_RATIO",
    "PERCENT_PER_RATIO_UNIT",
    "RSIIndicator",
    "SHARED_MODULES",
    "Signal",
    "SignalDirection",
    "SlingshotIndicator",
    "StochasticRSI",
    "SupertrendIndicator",
    "TighteningResult",
    "VOLUME_SPIKE_PCT",
    "VX_CEILING",
    "VX_CEILING_PCT",
    "VX_FLOOR",
    "VX_FLOOR_PCT",
    "VolumeAnalysis",
    "VortexIndicator",
    "VotingSummary",
    "ZScoreIndicator",
    "candles_from_raw",
    "compute_heikin_ashi",
    "detect_bb_proximity",
    "detect_landing_strip_v2",
    "detect_m_top",
    "detect_macd_taper",
    "detect_volume_confirmed_spring",
    "detect_w_bottom",
]
