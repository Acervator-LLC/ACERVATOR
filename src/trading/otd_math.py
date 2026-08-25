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

Public API:
    minimum_opposing_trade_distance_pct(interval_pct, fee_pct) -> float
    fold_rebuy_factor_from_pct(otd_pct) -> float
    fold_rebuy_factor(interval_pct, fee_pct) -> float

FALSIFICATION: this module is wrong if (a)
``minimum_opposing_trade_distance_pct`` ever returns a value outside
``[OTD_MIN_PCT, OTD_MAX_PCT]``, (b) ``fold_rebuy_factor`` ever returns a
value outside ``[0.5, 1.0]``, (c) a zero fee does not reproduce the
interval-only factor exactly, or (d) the returned distance is not
monotonically non-decreasing in either input while both stay under the
clamp.
"""

from __future__ import annotations

# The Minimum Opposing Trade Distance must stay inside these bounds for
# a sane gate. Below 0 the gate would over-fire (a rebuy at or above the
# tranche's own ref); above 50 it would lock out (demanding the price
# halve before any tranche is eligible).
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
