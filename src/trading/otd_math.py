"""Minimum Opposing Trade Distance (pure math, no I/O).

THE RULE
An opposing trade must move the price far enough to clear BOTH legs of
the round trip: the operator's scrumming interval AND the exchange fee
paid on each leg. Operator directive 2026-04-25, recorded at
``bot_container.py:358-362``:

    "total scrum interval will now be the setting plus trading fees
     which are 0.6% at the highest on Coinbase"

and the governing principle, 2026-08-12:

    "Functionality should be mirrored between either side of the
     ladder."

WHY THIS MODULE EXISTS
The distance was computed at four sites and one of them omitted the
fee. ``HysteresisGate`` (``gate_chain.py:405``), the FOLD blocker
diagnostic and the STACK open all read ``scrumming_interval_pct +
trading_fee_pct``; the per-tranche FOLD eligibility filter read
``scrumming_interval_pct`` alone, so a tranche could be re-bought at a
price that cleared its interval but still lost the round trip to fees.
Four copies of one rule is how the copies drift. This module is the one
definition.

THE CLAMP APPLIES TO THE SUM, NOT TO THE INTERVAL
The bound exists to keep the rebuy factor inside ``[0.5, 1.0]`` -- a
property of the TOTAL distance, not of the interval input. Clamping the
interval to 50 first and then adding a 0.6 fee yields 50.6%, a factor of
0.494, which breaches the very floor the clamp asserts. Post-sum is the
only order under which the clamp's stated invariant holds.

A consequence worth naming: when ``interval + fee`` already exceeds
``OTD_MAX_PCT`` the fee is absorbed by the clamp and behaviour is
unchanged. Live intervals are ~1.0%, so the clamp binds only on
misconfiguration.

This module is pure -- no imports from ``src.trading`` (avoids circular
deps), no exchange calls, no state.

WHERE THE INPUTS COME FROM IS PART OF THE ONE DEFINITION
The arithmetic is single-sourced here and the READS were not. The
Fold-Tranche panel did its own read, took the interval and NOT the fee,
and printed a rebuy price above the one the executor applies -- six
false greens on live tranches, measured 2026-08-23. One definition of
the arithmetic does not stop a caller feeding it different inputs, so
``minimum_opposing_trade_distance_pct_from_config`` below defines the
read as well.

WHICH CALLERS USE IT TODAY, AND WHICH DO NOT
The Fold-Tranche panel (``gui/bot_live_settings.py``) calls it. The two
executor sites -- the autonomous tick fold gate and the manual-rebalance
refusal in ``scrumming_bot.py`` -- still spell the ``getattr`` pair
inline. The reader reproduces their coercion exactly, quirk for quirk.

THAT IS STILL TWO STATEMENTS OF ONE DEFAULT, AND IT IS NAMED, NOT
HIDDEN. Routing those two sites through this reader is the obvious
finish and is NOT done here.

Public API:
    minimum_opposing_trade_distance_pct(interval_pct, fee_pct) -> float
    fold_rebuy_factor_from_pct(otd_pct) -> float
    fold_rebuy_factor(interval_pct, fee_pct) -> float
    minimum_opposing_trade_distance_pct_from_config(config) -> float

FALSIFICATION: this module is wrong if (a)
``minimum_opposing_trade_distance_pct`` ever returns a value outside
``[OTD_MIN_PCT, OTD_MAX_PCT]``, (b) ``fold_rebuy_factor`` ever returns a
value outside ``[0.5, 1.0]``, (c) a zero fee does not reproduce the
interval-only factor exactly, or (d) the returned distance is not
monotonically non-decreasing in either input while both stay under the
clamp.
"""

from __future__ import annotations

# Clamp bounds, in percent, for the Minimum Opposing Trade Distance.
OTD_MIN_PCT = 0.0
OTD_MAX_PCT = 50.0


def minimum_opposing_trade_distance_pct(interval_pct: float, fee_pct: float) -> float:
    """The clamped percentage an opposing trade must travel.

    ``interval_pct`` is ``config.scrumming_interval_pct``; ``fee_pct`` is
    ``config.trading_fee_pct``. Both are coerced with ``float()``, so a
    non-numeric config value raises ``TypeError``/``ValueError`` out of
    this function rather than being absorbed here.

    What the CALLER then does is a separate matter, and this docstring
    does not get to claim otherwise: the fold gate in
    ``scrumming_bot.tick`` wraps the call in
    ``except (TypeError, ValueError)`` and falls back to an OTD of 0.0,
    which is no distance gate at all. That fallback predates the fee and
    is unchanged by it. It is named here so the behaviour is not
    discovered by surprise.

    Returns a value in ``[OTD_MIN_PCT, OTD_MAX_PCT]``.
    """
    total = float(interval_pct) + float(fee_pct)
    return max(OTD_MIN_PCT, min(OTD_MAX_PCT, total))


def fold_rebuy_factor_from_pct(otd_pct: float) -> float:
    """Convert an already-clamped OTD percentage to a FOLD rebuy factor.

    Multiply a tranche's ``ref`` by this to get the HIGHEST price at
    which that tranche is still eligible to be re-bought:

        eligible  <=>  ticker.last <= ref * factor
    """
    return 1.0 - (float(otd_pct) / 100.0)


def fold_rebuy_factor(interval_pct: float, fee_pct: float) -> float:
    """``minimum_opposing_trade_distance_pct`` expressed as a factor."""
    return fold_rebuy_factor_from_pct(
        minimum_opposing_trade_distance_pct(interval_pct, fee_pct)
    )


def minimum_opposing_trade_distance_pct_from_config(
    config: object,
) -> float:
    """Return the OTD percentage a bot's own config asks for.

    THIS FUNCTION IS THE PLACE A SURFACE ASKS. The Fold-Tranche panel
    calls it, so no GUI code names either config field or either
    default. A surface that repeats the `getattr` pair is a second
    reader, and a second reader is how the panel came to omit the fee.

    THE TWO EXECUTOR SITES IN `scrumming_bot` DO NOT CALL IT YET. See
    the module docstring for why, and for what proves the agreement
    meanwhile.

    ``config`` is read by attribute only. No I/O, no state, and this
    module still imports nothing from ``src.trading``.

    THE COERCION IS REPRODUCED EXACTLY AS THE EXECUTOR SPELLS IT, quirk
    included: `or 0.6` on the fee means a fee configured to exactly
    0.0 is read as 0.6, because 0.0 is falsy. That is the live
    behaviour of the gate that trades, so it is the behaviour every
    surface must show. It is named here, not repaired here -- a
    surface that disagreed with the executor about a zero fee would
    be the very defect this function exists to end.

    Raises ``TypeError``/``ValueError`` on a non-numeric config value,
    for the reason `minimum_opposing_trade_distance_pct` states: what
    the caller does about that is the caller's posture, and the live
    callers deliberately differ. The tick falls back to an OTD of 0.0;
    the manual rebalance refuses the fire; the panel falls back to no
    price gate and still renders, because a raise there does not open
    the Bot Settings dialog at all.
    """
    return minimum_opposing_trade_distance_pct(
        getattr(config, "scrumming_interval_pct", 0) or 0,
        getattr(config, "trading_fee_pct", 0.6) or 0.6,
    )
