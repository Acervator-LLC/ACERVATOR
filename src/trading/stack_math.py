"""Ladder spacing and Stack Mode tranche generation (pure math, no I/O).

``ladder_offsets_pct`` places level n at ``level_multipliers(spacing_mode, n)``
times ``initial_gap_pct``, numbering levels from 1 and giving level 1 a
multiplier of 1.0 in every mode. ``scrum_ladder_prices`` walks up from the
anchor through ``_ladder_prices``, whose ``direction`` also carries the FOLD
sign for ``placement_floor_price``. ``split_scrum_into_tranches`` prices a
SCRUM ladder, then reshapes it with ``_apply_merge_rule`` and
``_apply_min_order_size``.

    quadratic     n^2                     DEFAULT_SPACING_MODE
    fibonacci     1, 2, 3, 5, 8, 13, 21   anchored on last_candle_close
    linear        n
    exponential   r^(n-1), r = DEFAULT_EXPONENTIAL_RATIO
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# _apply_merge_rule combines two rung prices closer than this fraction, 0.1%.
MERGE_THRESHOLD = 0.001

SPACING_MODES = ("quadratic", "fibonacci", "linear", "exponential")
DEFAULT_SPACING_MODE = "quadratic"

DEFAULT_INITIAL_GAP_PCT = 1.0

DEFAULT_EXPONENTIAL_RATIO = 2.0

# A fold offset at MAX_FOLD_DISTANCE_PCT would price the rung at zero.
MAX_FOLD_DISTANCE_PCT = 100.0


@dataclass
class Tranche:
    """One Stack tranche: sell `size` units at `price`."""

    index: int  # 0-based after merging, 0 nearest the scrum price
    price: float  # quote currency
    size: float  # base asset units

    def to_dict(self) -> dict:
        return {"index": self.index, "price": self.price, "size": self.size}


def _number(name: str, value: object) -> float:
    """Return `value` as a float, accepting only an exact `int` or `float`.

    The type test is exact: `bool`, `str` and every `float` subclass raise a
    ValueError naming `name`.
    """
    if type(value) is float:
        return value
    if type(value) is int:
        return float(value)
    raise ValueError(
        f"{name} must be an int or float; got {value!r} " f"({type(value).__name__})"
    )


def _fibonacci_multipliers(levels: int) -> list[float]:
    """Return `levels` multipliers from the sequence 1, 2, 3, 5, 8, 13, 21.

    The seed is 1, 2; no two elements repeat, and none collide under
    MERGE_THRESHOLD.
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
    """Return the distance of levels 1..`levels` from the anchor, in gaps.

    Element 0 is level 1 and is 1.0 for every entry of SPACING_MODES.
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
    """Return each level's distance from the ladder anchor, in percent.

    The offsets carry no direction; `_ladder_prices` applies the sign.
    """
    gap = _number("initial_gap_pct", initial_gap_pct)
    if gap < 0:
        raise ValueError(f"initial_gap_pct must be >= 0; got {gap}")
    return [m * gap for m in level_multipliers(spacing_mode, levels, exponential_ratio)]


def _validated_band(
    bb_bounds: Optional[Sequence[float]],
) -> Optional[tuple[float, float]]:
    """Return `bb_bounds` as a `(lower, upper)` pair, or None when it is None.

    A None result leaves `_enforce_level_one_inside_band` inactive; a pair
    failing `0 < lower < upper` raises ValueError.
    """
    if bb_bounds is None:
        return None
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
    return lower, upper


def placement_floor_price(
    direction: int,
    trigger_price: float,
    min_opposing_pct: float,
    band: Optional[tuple[float, float]] = None,
) -> Optional[float]:
    """Return the nearest price level 1 may occupy, from `trigger_price`.

    `direction` is +1 for the SCRUM side and -1 for the FOLD side; a `band`
    edge further out than `min_opposing_pct` replaces it, and a
    `min_opposing_pct` of 0 or less returns None.
    """
    if min_opposing_pct <= 0.0:
        return None
    floor_price = trigger_price * (1.0 + direction * min_opposing_pct / 100.0)
    if floor_price <= 0:
        raise ValueError(
            f"min_opposing_pct {min_opposing_pct} puts the placement floor "
            f"at {floor_price}; a floor must stay a real price"
        )
    if band is not None:
        opposing = band[1] if direction > 0 else band[0]
        if direction * (opposing - floor_price) > 0:
            return opposing
    return floor_price


def _enforce_level_one_inside_band(
    level_one_price: float,
    band: Optional[tuple[float, float]],
    direction: int,
    floor_price: Optional[float],
) -> None:
    """Raise ValueError when `level_one_price` sits outside `band`.

    Levels 2+ go unchecked, and a `level_one_price` past the `opposing` edge
    stands when `floor_price` sits further out than that edge.
    """
    if band is None:
        return
    lower, upper = band
    opposing = upper if direction > 0 else lower
    near = lower if direction > 0 else upper
    if direction * (level_one_price - opposing) > 0:
        if floor_price is not None and direction * (opposing - floor_price) < 0:
            return
    elif direction * (level_one_price - near) >= 0:
        return
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
    """Return one side's ladder prices, level 1 first.

    `direction` is +1 for the SCRUM (sell) side and -1 for the FOLD (buy)
    side; `last_candle_close` is required when `spacing_mode` is "fibonacci".
    """
    px = _number("trigger_price", trigger_price)
    if px <= 0:
        raise ValueError(f"trigger_price must be positive; got {px}")
    otd = _number("min_opposing_pct", min_opposing_pct)
    if otd < 0:
        raise ValueError(f"min_opposing_pct must be >= 0; got {otd}")
    band = _validated_band(bb_bounds)
    offsets = ladder_offsets_pct(
        levels, initial_gap_pct, spacing_mode, exponential_ratio
    )

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

    # A single positive lift scales every price and preserves their order.
    floor_price = placement_floor_price(direction, px, otd, band)
    if floor_price is not None and direction * (floor_price - prices[0]) > 0:
        lift = floor_price / prices[0]
        prices = [p * lift for p in prices]

    _enforce_level_one_inside_band(prices[0], band, direction, floor_price)
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
    """Return ascending SCRUM (sell) prices, level 1 nearest the anchor.

    `min_opposing_pct` lifts the anchor above `last_candle_close` under
    "fibonacci" and above `trigger_price` under every other `spacing_mode`.
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


def _apply_merge_rule(tranches: list[Tranche]) -> list[Tranche]:
    """Combine adjacent tranches whose prices are within MERGE_THRESHOLD.

    A merged Tranche keeps the higher `price` and the summed `size`, and the
    survivors are re-indexed from 0.
    """
    if len(tranches) < 2:
        return list(tranches)
    out: list[Tranche] = [tranches[0]]
    for cur in tranches[1:]:
        prev = out[-1]
        if prev.price <= 0:
            out.append(cur)
            continue
        # The prev.price > 0 guard above makes this width test equal a ratio.
        if (cur.price - prev.price) < prev.price * MERGE_THRESHOLD:
            merged = Tranche(
                index=prev.index,
                price=cur.price,
                size=prev.size + cur.size,
            )
            out[-1] = merged
        else:
            out.append(cur)
    for j, t in enumerate(out):
        t.index = j
    return out


def _max_slices(total_size: float, min_order_size: float) -> int:
    """Return how many slices of at least `min_order_size` fit in `total_size`."""
    return int(total_size // min_order_size)


def _apply_min_order_size(
    tranches: list[Tranche], total_size: float, min_order_size: float
) -> list[Tranche]:
    """Reduce the tranche count until each `size` reaches `min_order_size`.

    The survivors are the lowest-priced `_max_slices` of them, re-split evenly
    out of `total_size`; a `total_size` under `min_order_size` returns one
    Tranche carrying all of it.
    """
    if min_order_size <= 0 or not tranches:
        return tranches
    max_viable_n = _max_slices(total_size, min_order_size)
    if max_viable_n <= 0:
        return [Tranche(index=0, price=tranches[0].price, size=total_size)]
    if max_viable_n >= len(tranches):
        return tranches
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

    `scrum_ladder_prices` supplies the prices, then `_apply_merge_rule` and
    `_apply_min_order_size` reshape them.

    Args:
        scrum_price: the price one undivided SCRUM order would have sold at.
        scrum_size: total size to sell, in base asset units.
        n_target: target level count; merging and `min_order_size` lower it.
        split_distance_pct: the initial gap in percent, passed on as
            `initial_gap_pct`.
        spacing_mode: one of SPACING_MODES.
        min_opposing_pct: percent by which the anchor sits above the base
            price, and the floor `placement_floor_price` holds level 1 to.
        min_order_size: exchange minimum order size, in base asset units.
        exponential_ratio: growth ratio r for "exponential".
        last_candle_close: required for "fibonacci", ignored otherwise.
        bb_bounds: (lower, upper) local Bollinger range; None leaves
            `_enforce_level_one_inside_band` inactive.

    Returns:
        Tranche instances ordered by ascending `price`, at least one.

    Raises:
        ValueError on a non-positive size, an unknown `spacing_mode`,
        "fibonacci" without `last_candle_close`, or a level 1 outside
        `bb_bounds`.

    """
    # These raise under this function's parameter names, not the ladder's.
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

    initial_per_slice = size / n_target
    tranches = [
        Tranche(index=i, price=p, size=initial_per_slice) for i, p in enumerate(prices)
    ]

    tranches = _apply_merge_rule(tranches)
    tranches = _apply_min_order_size(tranches, size, min_order_size)

    # Raised, not asserted: `python -O` strips an `assert`.
    for k in range(1, len(tranches)):
        if tranches[k].price <= tranches[k - 1].price:
            msg = (
                f"non-monotone tranche prices: "
                f"{tranches[k - 1].price} !< {tranches[k].price}"
            )
            raise ValueError(msg)

    return tranches
