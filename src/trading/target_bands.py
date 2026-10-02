"""The two bands that decide whether a position is ON TARGET.

``at_target_dust_band`` is the band ``ScrummingBot.tick`` parks inside;
``manual_fire_dust_band`` is the wider one Manual Fire refuses inside.
``target_territory`` and ``manual_fire_will_noop`` answer the same two
questions from a position value, which is what the dashboard holds.
"""

from __future__ import annotations

from typing import Any

#: The tick's park band as a fraction of target; ScrummingBot.tick exits inside it.
AT_TARGET_PCT = 0.001

#: Manual Fire's own no-op band, as a fraction of target; ten times
#: ``AT_TARGET_PCT``.
MANUAL_FIRE_PCT = 0.01

#: Floor for both bands, in quote currency.
BAND_FLOOR_USD = 0.01

#: The three answers ``target_territory`` returns, named once for its readers.
TERRITORY_SCRUM = "scrum"
TERRITORY_FOLD = "fold"
TERRITORY_AT_TARGET = "at_target"


def at_target_dust_band(target_balance: float) -> float:
    """The band inside which the tick parks: 0.1% of target, min $0.01."""
    return max(float(target_balance) * AT_TARGET_PCT, BAND_FLOOR_USD)


def manual_fire_dust_band(target_balance: float) -> float:
    """The band inside which Manual Fire refuses: 1% of target, min $0.01."""
    return max(float(target_balance) * MANUAL_FIRE_PCT, BAND_FLOOR_USD)


def target_delta(position_value: float, target_balance: float) -> float:
    """``position_value`` less ``target_balance``, positive above target.

    ``target_territory`` and the Ammo cell both read the sign from here.
    """
    return float(position_value) - float(target_balance)


def ammo_target(live_target_balance: Any, configured_target_balance: Any) -> float:
    """The target an Ammo reading is measured against.

    The engine's grown target wherever the bot carries one, and the
    configured ``target_balance`` as the fallback. The bot list's Ammo
    cell and the header strip's AMMO total both take their second
    operand from here, so the row and the list cannot disagree.
    """
    live = float(live_target_balance or 0.0)
    if live:
        return live
    return float(configured_target_balance or 0.0)


def target_territory(position_value: float, target_balance: float) -> str:
    """``"scrum"``, ``"fold"`` or ``"at_target"`` for one position.

    A position further from ``target_balance`` than ``at_target_dust_band``
    has surplus to sell above it and a deficit to buy below it.
    """
    delta = target_delta(position_value, target_balance)
    band = at_target_dust_band(target_balance)
    if delta > band:
        return TERRITORY_SCRUM
    if delta < -band:
        return TERRITORY_FOLD
    return TERRITORY_AT_TARGET


def manual_fire_will_noop(position_value: float, target_balance: float) -> bool:
    """True when Manual Fire would log a no-op instead of trading.

    ``_execute_manual_rebalance`` refuses inside ``manual_fire_dust_band``;
    this answers the same question from a position value.
    """
    return abs(target_delta(position_value, target_balance)) <= manual_fire_dust_band(
        target_balance
    )
