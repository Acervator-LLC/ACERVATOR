"""The two bands that decide whether a position is ON TARGET.

``at_target_dust_band`` is the band ``ScrummingBot.tick`` parks inside;
``manual_fire_dust_band`` is the wider one Manual Fire refuses inside.
``target_territory`` and ``manual_fire_will_noop`` answer the same two
questions from a position value, which is what the dashboard holds.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

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


def fleet_ammo(readings: Iterable[Sequence[Any]]) -> dict:
    """The header strip's three AMMO figures over one reading per bot.

    A reading is a position value in dollars, the engine's grown target and the
    configured ``target_balance``; a bot whose ``ammo_target`` is not above
    zero contributes nothing. Every fleet source publishes these three keys
    from here, so no two of them can sum one dollar figure differently.
    """
    total_usd = 0.0
    scrum_bots = 0
    fold_bots = 0
    for position_value, live_target, configured_target in readings:
        target_usd = ammo_target(live_target, configured_target)
        if target_usd > 0:
            total_usd += abs(target_delta(position_value, target_usd))
            where = target_territory(position_value, target_usd)
            if where == TERRITORY_SCRUM:
                scrum_bots += 1
            elif where == TERRITORY_FOLD:
                fold_bots += 1
    return {
        "total_target_delta_usd": round(total_usd, 4),
        "bots_scrum_territory": scrum_bots,
        "bots_fold_territory": fold_bots,
    }


def manual_fire_will_noop(position_value: float, target_balance: float) -> bool:
    """True when Manual Fire would log a no-op instead of trading.

    ``_execute_manual_rebalance`` refuses inside ``manual_fire_dust_band``;
    this answers the same question from a position value.
    """
    return abs(target_delta(position_value, target_balance)) <= manual_fire_dust_band(
        target_balance
    )
