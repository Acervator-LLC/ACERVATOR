"""The zone's trading logic: one boost from three signals, and ``zone_timing``.

Inside the BB Tolerance zone ``zone_timing`` reads the panel's vote to wait while price
goes deeper, or to re-zero the Target Delta now as it slips out. ``zone_side_boost`` raises
the bar for waiting by Max Cartridge Size, BB Proximity and the Landing Strip; ``ScrummingBot.tick``,
``tape_context`` and ``paper_tape_context`` call both.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

from .indicators.bb_proximity import PanelBand
from .indicators.types import Signal, SignalDirection

SCRUM_SIDE: str = "scrum"
FOLD_SIDE: str = "fold"

DEEPER_WAY: dict[str, SignalDirection] = {
    SCRUM_SIDE: SignalDirection.BULLISH,
    FOLD_SIDE: SignalDirection.BEARISH,
}
"""The vote direction that carries price deeper into each side's zone."""

ZONE_DEEPER: str = "deeper"
ZONE_SLIPPING: str = "slipping"

BULLSEYE_TOUCH_SHARE: float = 0.005
"""A close within this share of the band counts as a BB Bullseye touch."""

BULLSEYE_WICK_SHARE: float = 0.002
"""A wick within this share of the band counts as a BB Bullseye touch."""

TOUCH_CLOSE: str = "close"
TOUCH_WICK: str = "wick"


@dataclass(frozen=True)
class BoostFigures:
    """The three Settings figures, each a percent: per Max Cartridge Size past, at the band edge, per tapering candle."""

    cartridge_pct: float = 0.0
    proximity_pct: float = 0.0
    landing_strip_pct: float = 0.0


@dataclass(frozen=True)
class BoostScales:
    """One side's scales: Max Cartridge Sizes past the threshold, band closeness 0 to 1, tapering candles."""

    cartridge: float = 0.0
    proximity: float = 0.0
    taper_steps: int = 0


@dataclass(frozen=True)
class SideBoost:
    """``side_boost``'s answer: the voters the deeper way, the summed share and its scales."""

    voters: int
    share: float
    scales: BoostScales = BoostScales()


@dataclass(frozen=True)
class ZoneTiming:
    """``zone_timing``'s answer: ``ZONE_DEEPER`` or ``ZONE_SLIPPING``, the bar the vote met, and the boost."""

    reading: str
    bar: float
    boost: SideBoost


def _share_of(pct: Any) -> float:
    """``pct`` percent as a share; 0.0 for a negative, non-finite or unreadable figure."""
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value < 0.0:
        return 0.0
    return value / 100.0


def boost_figures(config: Any) -> BoostFigures:
    """The ``cartridge_boost_pct``, ``proximity_boost_pct`` and ``landing_strip_boost_pct`` ``config`` holds."""
    return BoostFigures(
        cartridge_pct=_share_of(getattr(config, "cartridge_boost_pct", 0.0)) * 100.0,
        proximity_pct=_share_of(getattr(config, "proximity_boost_pct", 0.0)) * 100.0,
        landing_strip_pct=_share_of(getattr(config, "landing_strip_boost_pct", 0.0))
        * 100.0,
    )


def voters_the_deeper_way(signals: Sequence[Signal], side: str) -> int:
    """Unabstained ``signals`` voting ``DEEPER_WAY[side]``."""
    way = DEEPER_WAY[side]
    return sum(
        1 for signal in signals if not signal.abstained and signal.direction == way
    )


def cartridge_scale(delta: float, threshold_usd: float) -> float:
    """Max Cartridge Sizes the Target Delta ``delta`` sits past ``threshold_usd``; 0.0 under it or with no threshold."""
    if not (math.isfinite(delta) and math.isfinite(threshold_usd)):
        return 0.0
    if threshold_usd <= 0.0:
        return 0.0
    return max(0.0, abs(delta) / threshold_usd - 1.0)


def band_touch(band: PanelBand | None, side: str, high: float, low: float) -> str:
    """BB Bullseye: ``TOUCH_CLOSE`` for ``band.close`` within ``BULLSEYE_TOUCH_SHARE`` of the ``side`` band, ``TOUCH_WICK`` for the wick within ``BULLSEYE_WICK_SHARE``, else empty."""
    if band is None:
        return ""
    edge = band.upper if side == SCRUM_SIDE else band.lower
    if edge <= 0.0:
        return ""
    if abs(band.close - edge) / edge < BULLSEYE_TOUCH_SHARE:
        return TOUCH_CLOSE
    if side == SCRUM_SIDE:
        wick = high >= edge * (1.0 - BULLSEYE_WICK_SHARE)
    else:
        wick = low <= edge * (1.0 + BULLSEYE_WICK_SHARE)
    return TOUCH_WICK if wick else ""


def proximity_scale(
    band: PanelBand | None, side: str, tolerance_pct: float, touching: bool
) -> float:
    """How close ``band.close`` sits to the ``side`` band within ``tolerance_pct`` of price: 1.0 at the edge or ``touching``."""
    if band is None or not math.isfinite(tolerance_pct) or tolerance_pct <= 0.0:
        return 0.0
    if touching:
        return 1.0
    if side == SCRUM_SIDE:
        gap = band.upper - band.close
    else:
        gap = band.close - band.lower
    gap_pct = gap / band.close * 100.0
    return min(1.0, max(0.0, 1.0 - gap_pct / tolerance_pct))


def landing_strip_steps(run: int, minimum: int) -> int:
    """``run`` tapering candles as Landing Strip steps; 0 under Landing Strip Candles ``minimum``."""
    return int(run) if int(run) >= max(1, int(minimum)) else 0


def boost_share(scales: BoostScales, figures: BoostFigures) -> float:
    """Each figure times its scale, summed, as a share."""
    return (
        _share_of(figures.cartridge_pct) * scales.cartridge
        + _share_of(figures.proximity_pct) * scales.proximity
        + _share_of(figures.landing_strip_pct) * scales.taper_steps
    )


def side_boost(
    side: str, signals: Sequence[Signal], scales: BoostScales, figures: BoostFigures
) -> SideBoost:
    """``boost_share`` of ``scales`` at ``figures``, with the ``signals`` voting ``side``'s deeper way."""
    return SideBoost(
        voters=voters_the_deeper_way(signals, side),
        share=boost_share(scales, figures),
        scales=scales,
    )


def zone_side_boost(
    side: str,
    signals: Sequence[Signal],
    *,
    band: PanelBand | None,
    tolerance_pct: float,
    bullseye: bool,
    high: float,
    low: float,
    cartridge: float,
    taper_run: int,
    taper_minimum: int,
    figures: BoostFigures,
) -> SideBoost:
    """``side_boost`` over the scales ``side`` reads off ``band``, the newest ``high`` and ``low``, ``cartridge`` and ``taper_run``."""
    touching = bullseye and bool(band_touch(band, side, high, low))
    scales = BoostScales(
        cartridge=cartridge,
        proximity=proximity_scale(band, side, tolerance_pct, touching),
        taper_steps=landing_strip_steps(taper_run, taper_minimum),
    )
    return side_boost(side, signals, scales, figures)


def zone_timing(
    side: str,
    direction: Optional[SignalDirection],
    confidence: float,
    line: float,
    boost: SideBoost,
) -> ZoneTiming:
    """``ZONE_DEEPER`` while the vote points ``DEEPER_WAY[side]`` at ``line`` times one plus ``boost.share`` or more, else ``ZONE_SLIPPING``."""
    bar = line * (1.0 + boost.share)
    finite = math.isfinite(confidence) and math.isfinite(bar)
    if finite and direction == DEEPER_WAY[side] and confidence >= bar:
        return ZoneTiming(reading=ZONE_DEEPER, bar=bar, boost=boost)
    return ZoneTiming(reading=ZONE_SLIPPING, bar=bar, boost=boost)


def zone_visit(
    open_side: str, upper: bool, lower: bool, delta: float, past_interval: bool
) -> tuple[str, str]:
    """``(open, late)``: the side whose zone visit stays open after this read, and the side taking a late turn now.

    A visit opens inside a side's zone with ``past_interval``; the first read after price leaves it, with ``open_side`` still the Target Delta's side, is that side's late turn.
    """
    if not past_interval:
        return ("", "")
    if upper and delta > 0:
        return (SCRUM_SIDE, "")
    if lower and delta < 0:
        return (FOLD_SIDE, "")
    if open_side == SCRUM_SIDE and delta > 0:
        return ("", SCRUM_SIDE)
    if open_side == FOLD_SIDE and delta < 0:
        return ("", FOLD_SIDE)
    return ("", "")


@dataclass(frozen=True)
class ZoneRead:
    """``read_zone``'s answer: each side's zone flag and ``zone_timing``, the panel band and the vote's line."""

    upper: bool
    lower: bool
    scrum: ZoneTiming
    fold: ZoneTiming
    band: PanelBand | None
    line: float

    @property
    def scrum_deeper(self) -> bool:
        """True inside the upper zone while ``scrum`` reads ``ZONE_DEEPER``."""
        return self.upper and self.scrum.reading == ZONE_DEEPER

    @property
    def fold_deeper(self) -> bool:
        """True inside the lower zone while ``fold`` reads ``ZONE_DEEPER``."""
        return self.lower and self.fold.reading == ZONE_DEEPER


def read_zone(
    signals: Sequence[Signal],
    direction: Optional[SignalDirection],
    confidence: float,
    delta: float,
    candles: Sequence[Any],
    *,
    tolerance_pct: float,
    taper_minimum: int,
    figures: BoostFigures,
    cartridge: float = 0.0,
    bullseye: bool = True,
) -> ZoneRead:
    """The BB Tolerance zone off ``panel_band`` of ``signals``, and ``zone_timing`` of each side at the vote's line."""
    from .indicators.bb_proximity import band_zone, panel_band
    from .indicators.landing_strip import tapering_run
    from .ta_engine import three_indicator_floor

    band = panel_band(signals)
    upper, lower = band_zone(band, delta, tolerance_pct)
    line = three_indicator_floor(0.0, signals)
    held = list(candles)
    run = tapering_run(held) if held else 0
    high = float(held[-1].high) if held else 0.0
    low = float(held[-1].low) if held else 0.0

    def timing(side: str) -> ZoneTiming:
        boost = zone_side_boost(
            side,
            signals,
            band=band,
            tolerance_pct=tolerance_pct,
            bullseye=bullseye,
            high=high,
            low=low,
            cartridge=cartridge,
            taper_run=run,
            taper_minimum=taper_minimum,
            figures=figures,
        )
        return zone_timing(side, direction, confidence, line, boost)

    return ZoneRead(
        upper=upper,
        lower=lower,
        scrum=timing(SCRUM_SIDE),
        fold=timing(FOLD_SIDE),
        band=band,
        line=line,
    )
