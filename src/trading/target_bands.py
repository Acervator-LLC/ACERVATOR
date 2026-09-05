"""The two bands that decide whether a position is ON TARGET.

``at_target_dust_band`` is the band ``ScrummingBot.tick`` parks inside;
``manual_fire_dust_band`` is the wider one Manual Fire refuses inside.
``target_territory`` and ``manual_fire_will_noop`` answer the same two
questions from a position value, which is what the dashboard holds.
"""

from __future__ import annotations

#: The tick's park band, as a fraction of target. Inside it
#: ``ScrummingBot.tick`` exits before any TA or signal, unless a manual
#: fire is pending.
AT_TARGET_PCT = 0.001

#: Manual Fire's own no-op band, as a fraction of target; ten times
#: ``AT_TARGET_PCT``.
MANUAL_FIRE_PCT = 0.01

#: Floor for both bands, in quote currency.
BAND_FLOOR_USD = 0.01


def at_target_dust_band(target_balance: float) -> float:
    """The band inside which the tick parks: 0.1% of target, min $0.01."""
    return max(float(target_balance) * AT_TARGET_PCT, BAND_FLOOR_USD)


def manual_fire_dust_band(target_balance: float) -> float:
    """The band inside which Manual Fire refuses: 1% of target, min $0.01."""
    return max(float(target_balance) * MANUAL_FIRE_PCT, BAND_FLOOR_USD)


def target_territory(position_value: float, target_balance: float) -> str:
    """``"scrum"``, ``"fold"`` or ``"at_target"`` for one position.

    A position further from ``target_balance`` than ``at_target_dust_band``
    has surplus to sell above it and a deficit to buy below it.
    """
    delta = float(position_value) - float(target_balance)
    band = at_target_dust_band(target_balance)
    if delta > band:
        return "scrum"
    if delta < -band:
        return "fold"
    return "at_target"


def manual_fire_will_noop(position_value: float, target_balance: float) -> bool:
    """True when Manual Fire would log a no-op instead of trading.

    ``_execute_manual_rebalance`` refuses inside ``manual_fire_dust_band``;
    this answers the same question from a position value.
    """
    delta = float(position_value) - float(target_balance)
    return abs(delta) <= manual_fire_dust_band(target_balance)
