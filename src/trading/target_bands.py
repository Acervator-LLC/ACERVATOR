"""The two bands that decide whether a position is ON TARGET.

ONE SPELLING, READ BY THE TICK AND BY THE DASHBOARD. Both numbers were
written out twice: once in ``scrumming_bot.py``, where they stop a
trade, and once in ``src/gui/main_window.py``, where the Ammo cell
predicts what the tick will do. A dashboard that computes a trading
threshold itself can disagree with the engine, and the operator finds
out by pressing the button. Issue #128 R2 removed the second copy.

Qt-free by construction: nothing here imports a widget, and the GUI
calls in.
"""

from __future__ import annotations

#: The tick's park band, as a fraction of target. MEM-258: inside it
#: ``ScrummingBot.tick`` exits immediately -- no TA, no signals, no
#: buy or sell considered.
AT_TARGET_PCT = 0.001

#: Manual Fire's own no-op band, as a fraction of target. TEN TIMES
#: the band above, which is why the dashboard has to say so: between
#: the two, the autonomous engine still works the range and the button
#: silently returns "already within dust band".
MANUAL_FIRE_PCT = 0.01

#: Floor for both bands, in quote currency. A target small enough to
#: make a percentage band vanish still needs a band.
BAND_FLOOR_USD = 0.01


def at_target_dust_band(target_balance: float) -> float:
    """The band inside which the tick parks: 0.1% of target, min $0.01.

    Operator directive, MEM-258, verbatim: "IF THE GOD DAMN FUCKING
    CURRENT BALANCE EQUAL TARGET BALANCE NO SIGNAL LEAVES THE GOD DAMN
    PLATFORM."
    """
    return max(float(target_balance) * AT_TARGET_PCT, BAND_FLOOR_USD)


def manual_fire_dust_band(target_balance: float) -> float:
    """The band inside which Manual Fire refuses: 1% of target, min $0.01."""
    return max(float(target_balance) * MANUAL_FIRE_PCT, BAND_FLOOR_USD)


def target_territory(position_value: float, target_balance: float) -> str:
    """``"scrum"``, ``"fold"`` or ``"at_target"`` for one position.

    The tick's own test, stated once. A position above target by more
    than the band has surplus to sell; below it by more than the band
    has a deficit to buy; inside it, the tick exits early and neither
    is pending.
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

    ``_execute_manual_rebalance`` computes ``delta_usd`` at the tick's
    price and refuses inside ``manual_fire_dust_band``. This answers
    the same question from a position value, which is what a display
    has.
    """
    delta = float(position_value) - float(target_balance)
    return abs(delta) <= manual_fire_dust_band(target_balance)
