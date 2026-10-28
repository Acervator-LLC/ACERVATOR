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
The Fold-Tranche panel (``gui/bot_live_settings.py``), ``HysteresisGate``
in ``gate_chain.py``, the cartridge hold and the stack open in
``scrumming_bot.py``, and ``hypothetical_reading`` in
``ata_gate_scan.py`` all read this module. Nothing in the gate path adds
the two fields itself.

THE TWO EXECUTOR REFUSALS IN ``scrumming/execution.py`` KEEP THEIR OWN
READ. ``_execute_sell`` and ``_execute_buy`` read the fee as
``getattr(config, "trading_fee_pct", 0.6)`` with no ``or 0.6``, so a
configured 0.0 reads as 0.0 there and as 0.6 here. Routing them through
this reader would change the distance those two refusals apply on a
zero-fee record, so it is named here, not done here.

THE THIRD TERM IS THE BAND EXTENSION, AND IT IS ABSENT UNLESS A BAND IS
PASSED
The operator's placement rule names three terms: the minimum opposing
trade distance, the trading fee, and the Bollinger Band extension where
one is present. ``band_extension_pct`` is that third term. It reads the
one declaration, ``BotConfig.bb_tolerance_pct``, and applies it the way
``indicators/bb_proximity.detect_bb_proximity`` does -- a share of the
band's own span, not of the price -- then states the result as a
percentage of the reference price so the three terms add.

``minimum_opposing_trade_distance_pct`` takes it as a third argument
defaulting to ``BAND_EXTENSION_ABSENT_PCT``, so every caller that passes
two arguments answers exactly what it answered before. No caller passes a
band today: the band would make the distance per-tranche, and the fold
gate's consumer ``scrumming/sizing.eligible_fold_tranches`` takes one
factor for the whole queue. Wiring it reaches that function,
``scrumming/tick_phases.py``, ``paper/paper_run.py`` and
``simulator/back_test.py``.

A GUIDE ABOVE THE PRICE IT IS MEASURED FROM IS UNREPRESENTABLE, NOT
CHECKED FOR
``fold_rebuy_factor_from_pct`` clamps its own argument, so the factor it
returns lies in ``[0.5, 1.0]`` for every input including a negative
percentage. ``fold_rebuy_price`` multiplies a sell reference by that
factor, so its answer is at or below the price handed to it and no
caller can produce one above it. The previous reading of
``fold_rebuy_factor_from_pct`` trusted its caller to clamp first, and a
negative percentage returned a factor above 1.0.

Public API:
    minimum_opposing_trade_distance_pct(interval_pct, fee_pct) -> float
    fold_rebuy_factor_from_pct(otd_pct) -> float
    fold_rebuy_factor(interval_pct, fee_pct) -> float
    minimum_opposing_trade_distance_pct_from_config(config) -> float
    band_extension_pct(upper, lower, tolerance_pct, reference_price) -> float
    fold_rebuy_price(sell_ref_price, otd_pct) -> float

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

# The band extension a caller that holds no Bollinger Band contributes.
BAND_EXTENSION_ABSENT_PCT = 0.0


def clamped_otd_pct(otd_pct: float) -> float:
    """``otd_pct`` held inside ``OTD_MIN_PCT`` and ``OTD_MAX_PCT``."""
    return max(OTD_MIN_PCT, min(OTD_MAX_PCT, float(otd_pct)))


def band_extension_pct(
    upper: float,
    lower: float,
    tolerance_pct: float,
    reference_price: float,
) -> float:
    """The band extension as a percentage of ``reference_price``.

    ``upper`` and ``lower`` are the Bollinger Band prices and
    ``tolerance_pct`` is ``BotConfig.bb_tolerance_pct``, applied to the
    band's own span exactly as ``detect_bb_proximity`` applies it.
    Answers ``BAND_EXTENSION_ABSENT_PCT`` where no band is present --
    the span is not above zero, or ``reference_price`` is not above
    zero.
    """
    span = float(upper) - float(lower)
    price = float(reference_price)
    if span <= 0.0 or price <= 0.0:
        return BAND_EXTENSION_ABSENT_PCT
    return span * (float(tolerance_pct) / 100.0) / price * 100.0


def minimum_opposing_trade_distance_pct(
    interval_pct: float,
    fee_pct: float,
    extension_pct: float = BAND_EXTENSION_ABSENT_PCT,
) -> float:
    """The clamped percentage an opposing trade must travel.

    ``interval_pct`` is ``config.scrumming_interval_pct``; ``fee_pct`` is
    ``config.trading_fee_pct``; ``extension_pct`` is what
    ``band_extension_pct`` answered for this tranche, or
    ``BAND_EXTENSION_ABSENT_PCT`` where the caller holds no band. All
    three are coerced with ``float()``, so a
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
    total = float(interval_pct) + float(fee_pct) + float(extension_pct)
    return clamped_otd_pct(total)


def fold_rebuy_factor_from_pct(otd_pct: float) -> float:
    """Convert an OTD percentage to a FOLD rebuy factor.

    Multiply a tranche's ``ref`` by this to get the HIGHEST price at
    which that tranche is still eligible to be re-bought:

        eligible  <=>  ticker.last <= ref * factor

    ``clamped_otd_pct`` holds the argument inside ``OTD_MIN_PCT`` and
    ``OTD_MAX_PCT`` first, so the factor lies in ``[0.5, 1.0]`` for
    every input and a negative percentage cannot lift it above 1.0.
    """
    return 1.0 - (clamped_otd_pct(otd_pct) / 100.0)


def fold_rebuy_price(sell_ref_price: float, otd_pct: float) -> float:
    """The highest price a tranche sold at ``sell_ref_price`` may be re-bought at.

    ``sell_ref_price`` is the tranche's ``ref``, the price its scrum
    sold at, and never ``initial_buy_price``. Because
    ``fold_rebuy_factor_from_pct`` cannot answer above 1.0, this answer
    is at or below ``sell_ref_price`` for every ``otd_pct``.
    """
    return float(sell_ref_price) * fold_rebuy_factor_from_pct(otd_pct)


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

    THE CARTRIDGE HOLD AND THE STACK OPEN IN `scrumming_bot` CALL IT.
    The two executor refusals in `scrumming/execution.py` do not; see
    the module docstring for the zero-fee reason.

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
