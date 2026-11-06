"""The distribution sale's sets, each the extra units one fold bought beside the
price it paid."""

from __future__ import annotations

import math
from typing import Optional, Sequence

from ..container.config import as_finite_float
from ..otd_math import opposing_sale_price
from .sizing import UNITS_DUST

DIST_UNITS_KEY = "units"
DIST_FOLD_PRICE_KEY = "fold_price"
DIST_LADDER_TRIED_KEY = "ladder_tried"


def dist_set(
    units: object, fold_price: object, *, ladder_tried: bool = False
) -> Optional[dict]:
    """One set of ``units`` bought at ``fold_price``, None where either is not a
    positive finite number."""
    held = as_finite_float(units)
    paid = as_finite_float(fold_price)
    if held is None or paid is None or held <= UNITS_DUST or paid <= 0.0:
        return None
    return {
        DIST_UNITS_KEY: held,
        DIST_FOLD_PRICE_KEY: paid,
        DIST_LADDER_TRIED_KEY: bool(ladder_tried),
    }


def dist_units(sets: Sequence[dict]) -> float:
    """The ``DIST_UNITS_KEY`` figures of ``sets``, summed by ``math.fsum``."""
    return math.fsum(float(one[DIST_UNITS_KEY]) for one in sets)


def dist_floor_price(record: dict, otd_pct: float) -> float:
    """``opposing_sale_price`` of ``record``'s ``DIST_FOLD_PRICE_KEY`` at
    ``otd_pct``."""
    return opposing_sale_price(record[DIST_FOLD_PRICE_KEY], otd_pct)


def dist_sets_clearing(
    sets: Sequence[dict], price: float, otd_pct: float
) -> list[dict]:
    """The sets in ``sets`` whose ``dist_floor_price`` at ``otd_pct`` sits at or
    under ``price``."""
    return [one for one in sets if dist_floor_price(one, otd_pct) <= price]


def take_off_dist_sets(
    sets: list[dict], units: float, fold_price_cap: float, dust: float = UNITS_DUST
) -> float:
    """Take ``units`` off ``sets`` priced at or under ``fold_price_cap``, lowest
    first, drop each one taken down to ``dust``, and answer the units untaken."""
    left = max(0.0, float(units))
    eligible = sorted(
        (one for one in sets if one[DIST_FOLD_PRICE_KEY] <= fold_price_cap),
        key=lambda one: one[DIST_FOLD_PRICE_KEY],
    )
    spent: set[int] = set()
    for one in eligible:
        if left <= UNITS_DUST:
            break
        take = min(float(one[DIST_UNITS_KEY]), left)
        one[DIST_UNITS_KEY] = float(one[DIST_UNITS_KEY]) - take
        left -= take
        if one[DIST_UNITS_KEY] <= max(dust, UNITS_DUST):
            spent.add(id(one))
    sets[:] = [one for one in sets if id(one) not in spent]
    return left


def dist_sets_from_saved(stored: object) -> list[dict]:
    """The ``dist_set`` records rebuilt from a saved ``stored`` list, dropping
    every unreadable entry."""
    if not isinstance(stored, list):
        return []
    rebuilt = (
        dist_set(
            entry.get(DIST_UNITS_KEY),
            entry.get(DIST_FOLD_PRICE_KEY),
            ladder_tried=entry.get(DIST_LADDER_TRIED_KEY) is True,
        )
        for entry in stored
        if isinstance(entry, dict)
    )
    return [record for record in rebuilt if record is not None]
