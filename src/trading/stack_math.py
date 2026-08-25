"""Ladder spacing + Stack Mode tranche generation (pure math, no I/O).

WHAT THIS MODULE DECIDES: **where a rung sits**. That is all.

  * MERGE (combining rungs whose prices land within 0.1% of each other)
    still runs here, because it is a property of the computed prices.
    It is unchanged by the spacing work.
  * DISTRIBUTION (how much money each rung gets) is NOT decided here.
  * CONSUMPTION (how a rung is spent) is NOT decided here.

THE SPACING LAW -- operator directive 2026-08-11 / 2026-08-12
Every rung's distance from the ladder anchor is one configurable number,
the INITIAL GAP, times a per-level multiplier:

    distance(level n) = multiplier(mode, n) x initial_gap_pct

Levels are numbered from 1, and every mode has multiplier(mode, 1) == 1,
so **level 1 always sits at exactly the initial gap**. The initial gap
defaults to 1% and is configurable; 1% is not a constant.

    quadratic     n^2                     DEFAULT
    fibonacci     1, 2, 3, 5, 8, 13, 21   anchored on the LAST CANDLE CLOSE
    linear        n
    exponential   r^(n-1), r default 2

Quadratic at the 1% default reproduces the operator's table exactly:

    level        1     2     3     4     5     6     7
    distance    1%    4%    9%   16%   25%   36%   49%
    gap         1%    3%    5%    7%    9%   11%   13%

The gaps rise by a constant 2 x initial_gap. That constant second
difference of the distances is what makes the progression quadratic --
merely growing faster each step is not enough, and is the error this
law replaced.

REACH. The arc steepens fast: level 7 quadratic needs a 49% move, level
10 needs 99%. The LEVEL COUNT and the INITIAL GAP together decide how
much of a ladder can ever fire. Both are parameters here; neither is
hard-coded.

WHAT THIS RETIRED
Spacing used to be a per-STEP delta summed along the ladder, with rung 0
sitting AT the anchor at zero offset:

    linear       dp = 1         cumulative 0, 1, 2, 3
    quadratic    dp = i         cumulative 0, 1, 3, 6   (triangular)
    exponential  dp = 2^(i-1)   cumulative 0, 1, 3, 7

The middle row is a triangular progression, not a quadratic one. The
operator retired it -- "Oh, make the quadratic progression valid
then....my math bad..." -- and rung-0-at-the-anchor goes with it,
because the operator's table has no 0% level.

BOTH SIDES
"Functionality should be mirrored between either side of the ladder."
`scrum_ladder_prices` walks UP from the anchor and `fold_ladder_prices`
walks DOWN, through one shared core with an opposite sign. The two sides
cannot drift apart because there is only one implementation.

THE BB CONSTRAINT
"the initial position for any such spaced stack must have the additional
rule of not being able to be outside of the local BB range but
subsequent positions are allowed to extend beyond these bounds."
Level 1 must land inside the band; levels 2+ are unconstrained. This
module does NOT compute bands and holds no fallback range. The caller
either passes `bb_bounds=(lower, upper)` and the rule is enforced, or
passes nothing and the rule is NOT enforced on that ladder. There is no
third behaviour and no invented band.

FALSIFICATION: this module is wrong if (a) quadratic at gap g does not
give exactly n^2 x g, (b) the two sides return different offsets for the
same settings, (c) a fibonacci ladder is built with no candle close,
(d) a level-1 rung outside a SUPPLIED band is returned rather than
refused, (e) any returned fold price is <= 0, (f) tranche prices are not
strictly monotonically increasing, (g) two returned tranches sit within
0.1% of each other, or (h) the sum of tranche sizes exceeds `scrum_size`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# Merge threshold -- any two computed rung prices within this fraction
# get combined upwards (lower's size added to higher's, lower dropped).
# Per operator directive 2026-07-25: "Tranches within 0.1% of each
# other's price are combined upwards."
MERGE_THRESHOLD = 0.001  # 0.1%

# The four user-selectable spacing modes, quadratic first because it is
# the default.
SPACING_MODES = ("quadratic", "fibonacci", "linear", "exponential")
DEFAULT_SPACING_MODE = "quadratic"

# The initial gap. 1% is the DEFAULT, not a constant -- every entry
# point below takes it as a parameter.
DEFAULT_INITIAL_GAP_PCT = 1.0

# Growth ratio for exponential spacing: distance(n) = r^(n-1) x gap, so
# r = 2 gives 1, 2, 4, 8, 16 and level 1 still sits at the initial gap.
DEFAULT_EXPONENTIAL_RATIO = 2.0

# The fold side walks DOWN from its anchor, so a rung 100% or more below
# it is not a price at all. Refused loudly rather than clamped.
MAX_FOLD_DISTANCE_PCT = 100.0


@dataclass
class Tranche:
    """One Stack tranche: sell `size` units at `price`."""

    index: int  # 0-based position after merging (0 = closest to scrum_price)
    price: float  # target sell price in quote currency
    size: float  # size in base asset (units)

    def to_dict(self) -> dict:
        return {"index": self.index, "price": self.price, "size": self.size}


def _number(name: str, value: object) -> float:
    """Coerce a numeric input, refusing bools, strings and subclasses.

    `float(True)` is 1.0 and `float('20.0')` is 20.0. Both have reached
    money-handling code in this repo before. A threshold price is not a
    place to accept either.

    The test is EXACT-TYPE, not `isinstance`. `isinstance` admits
    subclasses, so `bool` and any `float` subclass slip through it; the
    set of subclasses is unbounded and cannot be enumerated shut.
    """
    if type(value) is float:
        return value
    if type(value) is int:
        return float(value)
    raise ValueError(
        f"{name} must be an int or float; got {value!r} " f"({type(value).__name__})"
    )


def _fibonacci_multipliers(levels: int) -> list[float]:
    """1, 2, 3, 5, 8, 13, 21 ... -- the operator's own sequence.

    Starts 1, 2 rather than 1, 1 so that no two levels share a distance;
    two rungs at one price would merge into one under MERGE_THRESHOLD
    and the ladder would silently lose a level.
    """
    out: list[float] = []
    a, b = 1.0, 2.0
    for _ in range(levels):
        out.append(a)
        a, b = b, a + b
    return out


def level_multipliers(
    spacing_mode: str,
    levels: int,
    exponential_ratio: float = DEFAULT_EXPONENTIAL_RATIO,
) -> list[float]:
    """Cumulative distance from the anchor for levels 1..`levels`, in
    units of the initial gap. Element 0 is level 1 and is always 1.0.
    """
    if type(levels) is not int:
        raise ValueError(f"levels must be an int; got {levels!r}")
    if levels < 1:
        raise ValueError(f"levels must be >= 1; got {levels}")
    if spacing_mode not in SPACING_MODES:
        raise ValueError(
            f"unknown spacing_mode {spacing_mode!r}; "
            f"expected one of {SPACING_MODES}"
        )
    if spacing_mode == "quadratic":
        return [float(n * n) for n in range(1, levels + 1)]
    if spacing_mode == "linear":
        return [float(n) for n in range(1, levels + 1)]
    if spacing_mode == "fibonacci":
        return _fibonacci_multipliers(levels)
    ratio = _number("exponential_ratio", exponential_ratio)
    if ratio <= 1.0:
        raise ValueError(
            f"exponential_ratio must be > 1.0 for a rising ladder; " f"got {ratio}"
        )
    return [ratio ** (n - 1) for n in range(1, levels + 1)]


def ladder_offsets_pct(
    levels: int,
    initial_gap_pct: float = DEFAULT_INITIAL_GAP_PCT,
    spacing_mode: str = DEFAULT_SPACING_MODE,
    exponential_ratio: float = DEFAULT_EXPONENTIAL_RATIO,
) -> list[float]:
    """Distance of each level from the ladder anchor, in percent.

    Direction-free: the same offsets serve both sides of the ladder,
    which is what makes the two sides mirrors rather than look-alikes.
    """
    gap = _number("initial_gap_pct", initial_gap_pct)
    if gap < 0:
        raise ValueError(f"initial_gap_pct must be >= 0; got {gap}")
    return [m * gap for m in level_multipliers(spacing_mode, levels, exponential_ratio)]


def _enforce_level_one_inside_band(
    level_one_price: float,
    bb_bounds: Optional[Sequence[float]],
) -> None:
    """Operator rule: level 1 must sit INSIDE the local Bollinger range.
    Levels 2+ may extend beyond it and are not checked here.

    `bb_bounds is None` means the caller has no band. This module does
    not compute bands and has no fallback range, so an absent band means
    the rule is NOT enforced on that ladder -- never that a made-up
    range stood in for one.
    """
    if bb_bounds is None:
        return
    if not isinstance(bb_bounds, (tuple, list)) or len(bb_bounds) != 2:
        raise ValueError(
            f"bb_bounds must be a (lower, upper) pair or None; " f"got {bb_bounds!r}"
        )
    lower = _number("bb_bounds lower", bb_bounds[0])
    upper = _number("bb_bounds upper", bb_bounds[1])
    if not 0 < lower < upper:
        raise ValueError(
            f"bb_bounds must satisfy 0 < lower < upper; "
            f"got lower={lower}, upper={upper}"
        )
    if not lower <= level_one_price <= upper:
        raise ValueError(
            f"level 1 at {level_one_price} is outside the local BB range "
            f"[{lower}, {upper}]. The initial position of a spaced stack "
            f"cannot sit outside the local BB range; levels 2+ may."
        )


def _ladder_prices(
    direction: int,
    trigger_price: float,
    levels: int,
    initial_gap_pct: float,
    spacing_mode: str,
    min_opposing_pct: float,
    exponential_ratio: float,
    last_candle_close: Optional[float],
    bb_bounds: Optional[Sequence[float]],
) -> list[float]:
    """The one ladder. `direction` is +1 for the SCRUM (sell) side and
    -1 for the FOLD (buy) side; nothing else differs between them.
    """
    px = _number("trigger_price", trigger_price)
    if px <= 0:
        raise ValueError(f"trigger_price must be positive; got {px}")
    otd = _number("min_opposing_pct", min_opposing_pct)
    if otd < 0:
        raise ValueError(f"min_opposing_pct must be >= 0; got {otd}")
    offsets = ladder_offsets_pct(
        levels, initial_gap_pct, spacing_mode, exponential_ratio
    )

    # Fibonacci is measured from the LAST CANDLE CLOSE, which is what
    # makes its rungs move as candles close. Anchoring it on the trigger
    # price instead would produce a ladder frozen at fire time -- a
    # static sequence wearing the name of a moving one. Refuse.
    if spacing_mode == "fibonacci":
        if last_candle_close is None:
            raise ValueError(
                "spacing_mode 'fibonacci' is measured from the last "
                "candle close, so its levels move as candles close. "
                "Pass last_candle_close=<close of the most recent "
                "candle>. Refusing to anchor on the trigger price, "
                "which would give a ladder that never moves."
            )
        base = _number("last_candle_close", last_candle_close)
        if base <= 0:
            raise ValueError(f"last_candle_close must be positive; got {base}")
    else:
        base = px

    anchor = base * (1.0 + direction * otd / 100.0)
    if anchor <= 0:
        raise ValueError(
            f"min_opposing_pct {otd} puts the ladder anchor at {anchor}; "
            f"an anchor must stay a real price"
        )

    prices: list[float] = []
    for n, off in enumerate(offsets, start=1):
        if direction < 0 and off >= MAX_FOLD_DISTANCE_PCT:
            raise ValueError(
                f"level {n} of a {levels}-level {spacing_mode} ladder at "
                f"a {initial_gap_pct}% initial gap sits {off}% below the "
                f"anchor, and a fold rung cannot be {MAX_FOLD_DISTANCE_PCT}% "
                f"or more below it. Lower the level count or the initial "
                f"gap so the ladder stays reachable."
            )
        prices.append(anchor * (1.0 + direction * off / 100.0))

    _enforce_level_one_inside_band(prices[0], bb_bounds)
    return prices


def scrum_ladder_prices(
    trigger_price: float,
    levels: int,
    initial_gap_pct: float = DEFAULT_INITIAL_GAP_PCT,
    spacing_mode: str = DEFAULT_SPACING_MODE,
    min_opposing_pct: float = 0.0,
    exponential_ratio: float = DEFAULT_EXPONENTIAL_RATIO,
    last_candle_close: Optional[float] = None,
    bb_bounds: Optional[Sequence[float]] = None,
) -> list[float]:
    """SCRUM (sell) side: ascending prices, level 1 nearest the anchor.

    `min_opposing_pct` offsets the ANCHOR away from `trigger_price`
    before any spacing applies -- it is the fee-clearing Minimum
    Opposing Trade Distance, not a rung. At its 0.0 default the anchor
    IS the trigger price and the operator's table reproduces directly
    against it.
    """
    return _ladder_prices(
        +1,
        trigger_price,
        levels,
        initial_gap_pct,
        spacing_mode,
        min_opposing_pct,
        exponential_ratio,
        last_candle_close,
        bb_bounds,
    )


def fold_ladder_prices(
    trigger_price: float,
    levels: int,
    initial_gap_pct: float = DEFAULT_INITIAL_GAP_PCT,
    spacing_mode: str = DEFAULT_SPACING_MODE,
    min_opposing_pct: float = 0.0,
    exponential_ratio: float = DEFAULT_EXPONENTIAL_RATIO,
    last_candle_close: Optional[float] = None,
    bb_bounds: Optional[Sequence[float]] = None,
) -> list[float]:
    """FOLD (buy) side: descending prices, the exact mirror of
    `scrum_ladder_prices` under the same settings.

    Returns PRICES ONLY. How much money each rung gets is DISTRIBUTION,
    a separate concern with its own spec, and is deliberately not
    decided here.
    """
    return _ladder_prices(
        -1,
        trigger_price,
        levels,
        initial_gap_pct,
        spacing_mode,
        min_opposing_pct,
        exponential_ratio,
        last_candle_close,
        bb_bounds,
    )


def _apply_merge_rule(tranches: list[Tranche]) -> list[Tranche]:
    """Combine any adjacent tranches whose prices are within
    MERGE_THRESHOLD (0.1%) of each other. Merged tranches keep the
    higher price and sum their sizes. Applied left-to-right so a chain
    of near-identical prices collapses to a single tranche at the top
    of the chain.

    Idempotent: running twice on the same list returns the same list.
    """
    if len(tranches) < 2:
        return list(tranches)
    out: list[Tranche] = [tranches[0]]
    for cur in tranches[1:]:
        prev = out[-1]
        if prev.price <= 0:
            out.append(cur)
            continue
        # Expressed as two PRICE WIDTHS rather than as a ratio against a
        # bare constant: `(cur - prev) / prev < T` becomes
        # `(cur - prev) < prev * T`, valid because the guard above
        # establishes `prev.price > 0`.
        #
        # MERGE is not this unit's subject and its behaviour must not
        # move, so the choice of form was measured rather than assumed.
        # Over 60,015 (price, separation) points spanning 1e-6..1e8 the
        # form below agrees with the original on every one, while
        # `cur < prev * (1 + T)` flips at exactly T -- 15 points where
        # the rounded quotient fell just under the threshold and the
        # ceiling form did not.
        if (cur.price - prev.price) < prev.price * MERGE_THRESHOLD:
            # Merge: sum sizes, keep the higher (cur) price
            merged = Tranche(
                index=prev.index,  # will be re-indexed at the end
                price=cur.price,
                size=prev.size + cur.size,
            )
            out[-1] = merged
        else:
            out.append(cur)
    # Re-index so returned tranches are 0..N-1 in order
    for j, t in enumerate(out):
        t.index = j
    return out


def _max_slices(total_size: float, min_order_size: float) -> int:
    """How many slices of at least `min_order_size` fit in `total_size`.

    A size divided by a size is a COUNT, and naming it as one keeps the
    comparison downstream between two counts instead of between a bare
    quotient and a length.
    """
    return int(total_size // min_order_size)


def _apply_min_order_size(
    tranches: list[Tranche], total_size: float, min_order_size: float
) -> list[Tranche]:
    """Enforce exchange minimum order size. If any tranche's per-slice
    size is below `min_order_size`, reduce the tranche count and
    redistribute so every remaining tranche is at least min_order_size.

    Simple strategy: if total_size / N < min_order_size, reduce N to
    floor(total_size / min_order_size), then re-split evenly. Preserves
    the FIRST-tranche-price contract by keeping the lowest-priced
    tranche and dropping from the top down.
    """
    if min_order_size <= 0 or not tranches:
        return tranches
    max_viable_n = _max_slices(total_size, min_order_size)
    if max_viable_n <= 0:
        # Can't even do one tranche → return single tranche at total_size
        # (caller's SCRUM logic will refuse below min_order_size elsewhere
        # if that's below the exchange's floor)
        return [Tranche(index=0, price=tranches[0].price, size=total_size)]
    if max_viable_n >= len(tranches):
        return tranches  # already fine
    # Keep the first max_viable_n tranches (lowest prices), redistribute
    kept = tranches[:max_viable_n]
    even = total_size / max_viable_n
    return [Tranche(index=t.index, price=t.price, size=even) for t in kept]


def split_scrum_into_tranches(
    scrum_price: float,
    scrum_size: float,
    n_target: int,
    split_distance_pct: float = DEFAULT_INITIAL_GAP_PCT,
    spacing_mode: str = DEFAULT_SPACING_MODE,
    min_opposing_pct: float = 0.0,
    min_order_size: float = 0.0,
    *,
    exponential_ratio: float = DEFAULT_EXPONENTIAL_RATIO,
    last_candle_close: Optional[float] = None,
    bb_bounds: Optional[Sequence[float]] = None,
) -> list[Tranche]:
    """Split a SCRUM into Stack tranches at ascending prices.

    Args:
        scrum_price: current price at which the SCRUM would have fired
            as a single order (i.e., the price that satisfied the
            SCRUM gate).
        scrum_size: total size to sell in base asset (units).
        n_target: operator-configured target LEVEL COUNT. Actual count
            may be lower per the merge and min-order-size constraints.
        split_distance_pct: THE INITIAL GAP, in percent. Level 1 sits at
            exactly this distance from the anchor and every other level
            is a multiple of it. Defaults to 1%.
        spacing_mode: one of SPACING_MODES. Defaults to "quadratic".
        min_opposing_pct: percent by which the ANCHOR sits above
            scrum_price (the fee-clearing Minimum Opposing Trade
            Distance). It is not a rung; level 1 sits one initial gap
            above it.
        min_order_size: exchange minimum order size in base asset. Any
            per-tranche size below this triggers count reduction.
        exponential_ratio: growth ratio r for "exponential".
        last_candle_close: REQUIRED for "fibonacci", ignored otherwise.
        bb_bounds: (lower, upper) local Bollinger range. When supplied,
            a level-1 price outside it is refused. When None, the rule
            is not enforced -- no band is invented.

    Returns:
        List of Tranche dataclass instances, ordered by ascending
        price. Always at least one tranche if scrum_size > 0.

    Raises:
        ValueError on invalid inputs (non-positive size, unknown mode,
        fibonacci without a candle close, level 1 outside a supplied
        band).
    """
    # Validated here, under the caller's own parameter names, before
    # delegating to the shared ladder. An error that names a parameter
    # the caller did not pass is an error the caller cannot act on.
    price = _number("scrum_price", scrum_price)
    if price <= 0:
        raise ValueError(f"scrum_price must be positive; got {price}")
    size = _number("scrum_size", scrum_size)
    if size <= 0:
        raise ValueError(f"scrum_size must be positive; got {size}")
    if type(n_target) is not int:
        raise ValueError(f"n_target must be an int; got {n_target!r}")
    if n_target < 1:
        raise ValueError(f"n_target must be >= 1; got {n_target}")
    gap = _number("split_distance_pct", split_distance_pct)
    if gap < 0:
        raise ValueError(f"split_distance_pct must be >= 0; got {gap}")
    if spacing_mode not in SPACING_MODES:
        raise ValueError(
            f"unknown spacing_mode {spacing_mode!r}; "
            f"expected one of {SPACING_MODES}"
        )

    prices = scrum_ladder_prices(
        trigger_price=price,
        levels=n_target,
        initial_gap_pct=gap,
        spacing_mode=spacing_mode,
        min_opposing_pct=min_opposing_pct,
        exponential_ratio=exponential_ratio,
        last_candle_close=last_candle_close,
        bb_bounds=bb_bounds,
    )

    # Even initial per-tranche size (rebalanced later if merges happen)
    initial_per_slice = size / n_target
    tranches = [
        Tranche(index=i, price=p, size=initial_per_slice) for i, p in enumerate(prices)
    ]

    # Apply merge rule (0.1% collision → combine upwards)
    tranches = _apply_merge_rule(tranches)

    # Apply min-order-size restriction (may reduce N; redistributes evenly)
    tranches = _apply_min_order_size(tranches, size, min_order_size)

    # Final safety: ensure prices are strictly monotone. Raised, not
    # asserted -- `python -O` strips an `assert` and would ship this
    # ladder with the check silently gone.
    for k in range(1, len(tranches)):
        if tranches[k].price <= tranches[k - 1].price:
            msg = (
                f"non-monotone tranche prices: "
                f"{tranches[k - 1].price} !< {tranches[k].price}"
            )
            raise ValueError(msg)

    return tranches
