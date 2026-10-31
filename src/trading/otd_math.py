"""Minimum Opposing Trade Distance arithmetic, with no I/O, no state and no import from ``src.trading``.

``minimum_opposing_trade_distance_pct`` sums the interval, the fee and the band extension, and never answers under ``ROUND_TRIP_FEES`` fees.
``wired_distance_pct`` lifts that distance by the wire share of the price it leaves.
``distance_settings`` reads the three settings and the venue fee once, and raises ``DistanceSettingUnreadable`` naming a setting that holds no number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

# Clamp bounds, in percent, for the Minimum Opposing Trade Distance.
OTD_MIN_PCT = 0.0
OTD_MAX_PCT = 50.0

# The band extension a caller that holds no Bollinger Band contributes.
BAND_EXTENSION_ABSENT_PCT = 0.0

#: The wire share of a sale that routed nothing along a wire.
WIRE_ABSENT_PCT = 0.0

#: The whole of a sale's proceeds, in percent: the most a wire share, or a distance carrying one, reaches.
WHOLE_PCT = 100.0

#: ``trading_fee_pct`` where a config names none, the Coinbase Advanced Trade taker maximum.
DEFAULT_TRADING_FEE_PCT = 0.6

#: The fees one scrum and the fold answering it pay: one sell, one buy.
ROUND_TRIP_FEES = 2

#: ``band_travel_pct`` where a config names none, which adds no band extension.
BAND_TRAVEL_OFF_PCT = 0.0

NOT_A_NUMBER = "not a number"
BELOW_ZERO = "below zero"


class DistanceSettingUnreadable(ValueError):
    """``setting`` holds ``value``, which ``setting_pct`` cannot read as the number a distance needs."""

    def __init__(self, setting: str, value: object, reason: str = NOT_A_NUMBER) -> None:
        self.setting = setting
        self.value = value
        self.reason = reason
        super().__init__(f"{setting} holds {value!r}, {reason}")


def _holds_nothing(held: object) -> bool:
    """True where ``held`` is None, zero, empty or False."""
    try:
        return not held
    except (TypeError, ValueError):
        return False


def setting_pct(
    config: object, setting: str, unset_pct: Optional[float] = None
) -> float:
    """``config``'s ``setting`` as a finite float, or ``unset_pct`` where one is given and the setting holds nothing."""
    held: Any = getattr(config, setting, None)
    if unset_pct is not None and _holds_nothing(held):
        return float(unset_pct)
    try:
        read = float(held)
    except (TypeError, ValueError, OverflowError):
        raise DistanceSettingUnreadable(setting, held) from None
    if not math.isfinite(read):
        raise DistanceSettingUnreadable(setting, held)
    return read


def trading_fee_pct_from_config(config: object, venue_fee_pct: float = 0.0) -> float:
    """``config.trading_fee_pct``, or ``DEFAULT_TRADING_FEE_PCT`` where it names none, raised to a higher ``venue_fee_pct``."""
    fee = setting_pct(config, "trading_fee_pct", DEFAULT_TRADING_FEE_PCT)
    if fee < 0.0:
        raise DistanceSettingUnreadable(
            "trading_fee_pct", getattr(config, "trading_fee_pct", None), BELOW_ZERO
        )
    venue = float(venue_fee_pct or 0.0)
    if math.isfinite(venue) and venue > fee:
        return venue
    return fee


def clamped_otd_pct(otd_pct: float) -> float:
    """``otd_pct`` held inside ``OTD_MIN_PCT`` and ``OTD_MAX_PCT``."""
    return max(OTD_MIN_PCT, min(OTD_MAX_PCT, float(otd_pct)))


def clamped_wire_pct(wire_pct: float) -> float:
    """``wire_pct`` held inside ``WIRE_ABSENT_PCT`` and ``WHOLE_PCT``."""
    return max(WIRE_ABSENT_PCT, min(WHOLE_PCT, float(wire_pct)))


def wired_distance_pct(distance_pct: float, wire_pct: float) -> float:
    """``distance_pct`` plus ``clamped_wire_pct`` of ``wire_pct`` taken off the price ``distance_pct`` leaves.

    A buy-back at it returns the share of units an unwired sale's buy-back at ``distance_pct`` returns, and ``WIRE_ABSENT_PCT`` answers ``distance_pct`` unchanged.
    """
    distance = float(distance_pct)
    return distance + clamped_wire_pct(wire_pct) * (1.0 - distance / 100.0)


def band_extension_pct(
    upper: float,
    lower: float,
    travel_pct: float,
    reference_price: float,
) -> float:
    """The band extension as a percentage of ``reference_price``, with
    ``travel_pct`` from ``BotConfig.band_travel_pct`` applied to the span
    between ``upper`` and ``lower`` exactly as ``scrumming_bot.tick``
    applies it.

    Answers ``BAND_EXTENSION_ABSENT_PCT`` where ``travel_pct``, that span
    or ``reference_price`` is not above zero.
    """
    span = float(upper) - float(lower)
    price = float(reference_price)
    travel = float(travel_pct)
    if travel <= 0.0 or span <= 0.0 or price <= 0.0:
        return BAND_EXTENSION_ABSENT_PCT
    return span * (travel / 100.0) / price * 100.0


def band_extension_pct_from_config(
    config: object,
    upper: float,
    lower: float,
    reference_price: float,
) -> float:
    """``band_extension_pct`` at ``config``'s ``band_travel_pct``, read by ``setting_pct``."""
    return band_extension_pct(
        upper,
        lower,
        setting_pct(config, "band_travel_pct", BAND_TRAVEL_OFF_PCT),
        reference_price,
    )


def minimum_opposing_trade_distance_pct(
    interval_pct: float,
    fee_pct: float,
    extension_pct: float = BAND_EXTENSION_ABSENT_PCT,
    wire_pct: float = WIRE_ABSENT_PCT,
) -> float:
    """``ROUND_TRIP_FEES`` times ``fee_pct`` where ``interval_pct`` plus ``extension_pct`` is under ``fee_pct``, else those three summed, clamped, then ``wired_distance_pct`` of ``wire_pct``.

    Raises ``ValueError`` where any of the four is not a finite number."""
    terms = (float(interval_pct), float(fee_pct), float(extension_pct), float(wire_pct))
    if not all(math.isfinite(term) for term in terms):
        raise ValueError(f"opposing trade distance terms {terms!r} are not all finite")
    interval, fee, extension, wire = terms
    if interval + extension < fee:
        return wired_distance_pct(clamped_otd_pct(ROUND_TRIP_FEES * fee), wire)
    return wired_distance_pct(clamped_otd_pct(interval + fee + extension), wire)


@dataclass(frozen=True)
class DistanceSettings:
    """The interval, the fee and the band travel one distance reads, each read by ``setting_pct``."""

    interval_pct: float
    fee_pct: float
    band_travel_pct: float

    def distance_pct(
        self,
        band_upper: float = 0.0,
        band_lower: float = 0.0,
        reference_price: float = 0.0,
        wire_pct: float = WIRE_ABSENT_PCT,
    ) -> float:
        """``minimum_opposing_trade_distance_pct`` at one band and ``wire_pct``, with ``BAND_EXTENSION_ABSENT_PCT`` where no band is held."""
        return minimum_opposing_trade_distance_pct(
            self.interval_pct,
            self.fee_pct,
            band_extension_pct(
                band_upper, band_lower, self.band_travel_pct, reference_price
            ),
            wire_pct,
        )

    def distance_at_band(
        self, band: Any = None, wire_pct: float = WIRE_ABSENT_PCT
    ) -> float:
        """``distance_pct`` at ``band``'s ``upper``, ``lower`` and ``middle``, each 0.0 where ``band`` holds none."""
        return self.distance_pct(
            float(getattr(band, "upper", 0.0) or 0.0),
            float(getattr(band, "lower", 0.0) or 0.0),
            float(getattr(band, "middle", 0.0) or 0.0),
            wire_pct,
        )


def distance_settings(config: object, venue_fee_pct: float = 0.0) -> DistanceSettings:
    """The ``DistanceSettings`` ``config`` holds, with ``trading_fee_pct_from_config`` raising the fee to ``venue_fee_pct``."""
    return DistanceSettings(
        interval_pct=setting_pct(config, "scrumming_interval_pct"),
        fee_pct=trading_fee_pct_from_config(config, venue_fee_pct),
        band_travel_pct=setting_pct(config, "band_travel_pct", BAND_TRAVEL_OFF_PCT),
    )


def fold_rebuy_factor_from_pct(otd_pct: float) -> float:
    """Convert an OTD percentage to a FOLD rebuy factor.

    Multiply a tranche's ``ref`` by this to get the HIGHEST price at
    which that tranche is still eligible to be re-bought:

        eligible  <=>  ticker.last <= ref * factor

    The argument is held inside ``OTD_MIN_PCT`` and ``WHOLE_PCT`` first,
    the bound ``wired_distance_pct`` reaches, so the factor lies in
    ``[0.0, 1.0]`` for every input and a negative percentage cannot lift
    it above 1.0.
    """
    return 1.0 - (max(OTD_MIN_PCT, min(WHOLE_PCT, float(otd_pct))) / 100.0)


def fold_rebuy_price(sell_ref_price: float, otd_pct: float) -> float:
    """The highest price a tranche sold at ``sell_ref_price`` may be re-bought at.

    ``sell_ref_price`` is the tranche's ``ref``, the price its scrum
    sold at, and never ``initial_buy_price``. Because
    ``fold_rebuy_factor_from_pct`` cannot answer above 1.0, this answer
    is at or below ``sell_ref_price`` for every ``otd_pct``.
    """
    return float(sell_ref_price) * fold_rebuy_factor_from_pct(otd_pct)


def opposing_sale_price(buy_ref_price: float, otd_pct: float) -> float:
    """The lowest price a unit bought at ``buy_ref_price`` may sell at,
    ``clamped_otd_pct`` of ``otd_pct`` above it."""
    return float(buy_ref_price) * (1.0 + clamped_otd_pct(otd_pct) / 100.0)


def minimum_opposing_trade_distance_pct_from_config(
    config: object,
    band_upper: float = 0.0,
    band_lower: float = 0.0,
    reference_price: float = 0.0,
    venue_fee_pct: float = 0.0,
) -> float:
    """The distance ``config`` and ``venue_fee_pct`` ask for at one band, read through ``distance_settings``.

    Raises ``DistanceSettingUnreadable`` naming the first of the three settings that holds no number.
    """
    return distance_settings(config, venue_fee_pct).distance_pct(
        band_upper, band_lower, reference_price
    )
