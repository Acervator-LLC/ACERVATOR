"""The Scrum/Fold cycle's sizing arithmetic, one definition of each figure.

``ScrummingBot.tick``, ``TickPhaseMixin``, ``ExecutionEngineMixin`` and
``FoldTrancheAccountingMixin`` call these at the sites that computed each figure
inline, and ``back_test.walk`` calls the same functions over a ``SimPosition``.
``priced_usd`` through ``cartridge_threshold_usd`` each answer the expression
their Live site held, in that site's operand order, holding no state.
``unit_rule`` answers the rule ``CITED_UNIT_RULES`` cites for an asset class on
a venue, ``scrum_units`` and ``fold_units`` size under that rule through
``sized_units``, and ``trim_fold_plan`` keeps what a whole-unit fold could not
spend in its tranches. ``plan_source_price`` reads the scrum price a fold plan
re-enters against, and ``opposing_trade_distances`` reads the distance between
each fold and that scrum over a run's pairs.
"""

from __future__ import annotations

import math
import statistics
from typing import Optional, Sequence

#: The ``state`` an ``ExtractorBot`` writes on a position below its entry value.
DRAWDOWN_STATE = "drawdown"

#: The two unit rules a venue's published documentation states for an asset
#: class: an order may name a fraction of a unit, or only whole units.
FRACTIONAL_UNITS = "fractional"
WHOLE_UNITS = "whole"
UNIT_RULES = (FRACTIONAL_UNITS, WHOLE_UNITS)

#: A unit count within this of a whole number reads as that whole number: the
#: ninth decimal, the most an Alpaca ``qty`` carries.
WHOLE_UNIT_GRAIN = 1e-9

#: The two asset classes the determination table cites, spelled as
#: ``ata_spm.ASSET_CLASSES`` spells them.
CLASS_CRYPTO = "crypto"
CLASS_STOCKS = "stocks"

#: The unit rule each ``(asset class, venue)`` trades under, one row per rule
#: the manual's determination table cites from the venue's published page. A
#: pair absent here has no cited rule and is not simulated.
CITED_UNIT_RULES: dict[tuple[str, str], str] = {
    (CLASS_CRYPTO, "coinbase"): FRACTIONAL_UNITS,
    (CLASS_STOCKS, "alpaca"): FRACTIONAL_UNITS,
}

#: ``position_ceiling`` clamps ``position_ceiling_multiple`` to this range.
CEILING_MULTIPLE_MIN = 1.0
CEILING_MULTIPLE_MAX = 10.0

#: ``fold_rate_taper`` reads full size under this ratio and nothing at 1.0.
TAPER_START_RATIO = 0.5

#: How much of the size ``fold_rate_taper`` takes off between the start ratio
#: and 1.0, so the taper lands at a tenth of the size there.
TAPER_DROP = 0.9


def priced_usd(units: float, price: float, quote_to_usd: float = 1.0) -> float:
    """``units`` at ``price`` in USD: the position value ``ScrummingBot.tick``
    reads and the notional ``_tick_execute_scrum`` sizes."""
    return units * price * quote_to_usd


def target_delta_usd(position_usd: float, target_balance: float) -> float:
    """The Target Delta: ``position_usd`` less ``target_balance``, positive above
    target."""
    return position_usd - target_balance


def target_delta_pct(delta_usd: float, target_balance: float) -> float:
    """``delta_usd`` as a percentage of ``target_balance``, the ``delta_pct``
    the tick logs."""
    return abs(delta_usd) / (target_balance + 1e-9) * 100


def scrumming_interval_usd(
    target_balance: float, scrumming_interval_pct: float
) -> float:
    """The scrumming interval in USD: ``scrumming_interval_pct`` of
    ``target_balance``."""
    return target_balance * scrumming_interval_pct / 100.0


def delta_below_interval(delta_usd: float, interval_usd: float) -> bool:
    """True when ``delta_usd`` sits inside ``interval_usd``, so the tick holds."""
    return abs(delta_usd) < interval_usd


def unit_rule(asset_class: str, venue: str) -> Optional[str]:
    """The unit rule ``CITED_UNIT_RULES`` cites for ``asset_class`` on
    ``venue``, or None when the table cites none for the pair."""
    return CITED_UNIT_RULES.get((str(asset_class), str(venue)))


def sized_units(units: float, rule: str) -> float:
    """``units`` under ``rule``: unchanged when fractional, floored to a whole
    number when whole, with a count within ``WHOLE_UNIT_GRAIN`` of a whole
    number read as that number."""
    if rule == FRACTIONAL_UNITS:
        return units
    if rule == WHOLE_UNITS:
        return float(math.floor(units + WHOLE_UNIT_GRAIN))
    raise ValueError(f"unit rule {rule!r} is not one of {UNIT_RULES}")


def scrum_units(delta_usd: float, price: float, rule: str) -> float:
    """The units a scrum sells: ``delta_usd`` at ``price``, sized under
    ``rule``."""
    return sized_units(abs(delta_usd) / price, rule)


def sale_proceeds_usd(gross_usd: float, fee_usd: float) -> float:
    """``gross_usd`` less ``fee_usd``, what a settled sell leaves the bot."""
    return gross_usd - fee_usd


def estimated_fee_usd(notional_usd: float, fee_pct: float) -> float:
    """``fee_pct`` of ``notional_usd``, the fee a run with no venue books; Live
    reads the venue's reported fee and never calls this."""
    return abs(notional_usd) * fee_pct / 100.0


def eligible_fold_tranches(
    tranches: list, ticker_last: float, otd_factor: float
) -> list:
    """The tranches in ``tranches`` whose ``ref`` times ``otd_factor`` is at or
    above ``ticker_last``."""
    return [t for t in tranches if ticker_last <= float(t.get("ref", 0)) * otd_factor]


def cycle_growth_cap_usd(
    target_balance: float, consumed_usd: float, growth_pct: float
) -> float:
    """The per-cycle growth cap: ``growth_pct`` of ``target_balance`` less
    ``consumed_usd``, never below zero."""
    base = max(0.0, target_balance - consumed_usd)
    return base * (growth_pct / 100.0)


def fold_cap_remaining_usd(cycle_cap_usd: float, consumed_usd: float) -> float:
    """What is left of ``cycle_cap_usd`` after ``consumed_usd``, never below
    zero: the room ``plan_fold_consumption`` plans under."""
    return max(0.0, cycle_cap_usd - consumed_usd)


def plan_fold_consumption(
    eligible: list, cap_remaining: float
) -> tuple[list, list, int]:
    """What one fold takes from each tranche in ``eligible`` under
    ``cap_remaining``: the ``(source, usd, units)`` plan, the slices taken, and
    how many tranches were part-consumed."""
    plan: list[tuple[dict, float, float]] = []
    slices: list[dict] = []
    running_usd = 0.0
    partial_count = 0
    for _t in eligible:
        room = cap_remaining - running_usd
        if room <= 1e-12:
            break
        tranche_usd = float(_t.get("usd", 0) or 0)
        tranche_units = float(_t.get("units", 0) or 0)
        if tranche_usd <= 0.0 or tranche_units <= 0.0:
            continue
        if tranche_usd <= room + 1e-9:
            take_usd = tranche_usd
            take_units = tranche_units
        else:
            take_usd = room
            take_units = tranche_units * (take_usd / tranche_usd)
            partial_count += 1
        slices.append(
            {
                "usd": take_usd,
                "units": take_units,
                "ref": float(_t.get("ref", 0) or 0),
                "initial_buy_price": _t["initial_buy_price"],
                "created_ts": _t.get("created_ts", 0.0),
            }
        )
        plan.append((_t, take_usd, take_units))
        running_usd += take_usd
    return plan, slices, partial_count


def settle_fold_plan(tranches: list, plan: list) -> tuple[list, int, int]:
    """Take from each source tranche in ``plan`` what it says, and answer the
    tranches left, how many records left ``tranches``, and how many were
    drained to nothing."""
    pre_remove = len(tranches)
    spent: set[int] = set()
    for src, took_usd, took_units in plan:
        src["usd"] = max(0.0, float(src.get("usd", 0) or 0) - took_usd)
        src["units"] = max(0.0, float(src.get("units", 0) or 0) - took_units)
        if src["usd"] <= 1e-9 or src["units"] <= 1e-12:
            spent.add(id(src))
        else:
            src["fold_partial_spent"] = True
    kept = [t for t in tranches if id(t) not in spent]
    return kept, pre_remove - len(kept), len(spent)


def plan_source_price(plan: list) -> float:
    """The scrum price a fold under ``plan`` re-enters against: each source
    tranche's ``ref`` weighted by the USD the plan takes from it; zero for an
    empty ``plan`` or one taking no USD."""
    taken_usd = sum(float(take_usd) for _src, take_usd, _units in plan)
    if taken_usd <= 0.0:
        return 0.0
    weighted = sum(
        float(src.get("ref", 0) or 0) * float(take_usd)
        for src, take_usd, _units in plan
    )
    return weighted / taken_usd


def opposing_trade_distance_pct(scrum_price: float, fold_price: float) -> float:
    """``scrum_price`` less ``fold_price`` as a percentage of ``scrum_price``,
    positive for a fold that re-entered below its scrum."""
    return 100.0 * (float(scrum_price) - float(fold_price)) / float(scrum_price)


def opposing_trade_distances(pairs: Sequence[Sequence[float]]) -> dict:
    """``opposing_trade_distance_pct`` over each ``(scrum_price, fold_price)``
    in ``pairs`` whose scrum price is above zero: the ``count``, the
    ``mean_pct``, the ``median_pct`` and the ``distances_pct``, the two figures
    None when ``count`` is zero."""
    distances = [
        opposing_trade_distance_pct(scrum, fold)
        for scrum, fold in pairs
        if float(scrum) > 0.0
    ]
    return {
        "count": len(distances),
        "mean_pct": statistics.mean(distances) if distances else None,
        "median_pct": statistics.median(distances) if distances else None,
        "distances_pct": distances,
    }


def fold_spend_usd(eligible_usd: float, taper: float) -> float:
    """The USD a fold buys with: ``eligible_usd`` times ``taper``."""
    return eligible_usd * taper


def wallet_capped_spend_usd(spend_usd: float, available_usd: float) -> float:
    """``spend_usd`` held to ``available_usd``, the cap Manual Fire applies."""
    return min(spend_usd, available_usd)


def fold_units(spend_usd: float, price: float, rule: str) -> float:
    """The units a buy of ``spend_usd`` at ``price`` books, sized under
    ``rule``."""
    return sized_units(spend_usd / price, rule)


def trim_fold_plan(plan: list, unspent_usd: float) -> list:
    """``plan`` with ``unspent_usd`` taken back off its last entries, dollars
    and units alike, so ``settle_fold_plan`` leaves in the tranches what a
    whole-unit fold could not spend."""
    left = float(unspent_usd)
    trimmed: list = []
    for source, take_usd, take_units in reversed(plan):
        if left <= 1e-12:
            trimmed.append((source, take_usd, take_units))
            continue
        given_back = min(left, take_usd)
        keep_usd = take_usd - given_back
        keep_units = take_units * (keep_usd / take_usd) if take_usd > 0.0 else 0.0
        left -= given_back
        if keep_usd > 1e-12:
            trimmed.append((source, keep_usd, keep_units))
    trimmed.reverse()
    return trimmed


def position_ceiling(anchor_target_balance: float, multiple: float) -> float:
    """``anchor_target_balance`` times ``multiple`` clamped to
    ``CEILING_MULTIPLE_MIN`` and ``CEILING_MULTIPLE_MAX``."""
    mult = max(CEILING_MULTIPLE_MIN, min(CEILING_MULTIPLE_MAX, multiple))
    return anchor_target_balance * mult


def ratio_to_ceiling(position_usd: float, ceiling_usd: float) -> float:
    """How much of ``ceiling_usd`` the position at ``position_usd`` fills."""
    return position_usd / ceiling_usd


def fold_rate_taper(ratio: float) -> float:
    """The multiplier on a fold's USD size for ``ratio``: full under
    ``TAPER_START_RATIO``, then linear by ``TAPER_DROP`` to 1.0, and nothing
    from 1.0 up."""
    if ratio >= 1.0:
        return 0.0
    if ratio < TAPER_START_RATIO:
        return 1.0
    return 1.0 - (ratio - TAPER_START_RATIO) / TAPER_START_RATIO * TAPER_DROP


def cartridge_threshold_usd(target_balance: float, cartridge_pct: float) -> float:
    """The Target Delta at which the cartridge fires: ``cartridge_pct`` of
    ``target_balance``."""
    return target_balance * cartridge_pct / 100.0


__all__ = [
    "CEILING_MULTIPLE_MAX",
    "CEILING_MULTIPLE_MIN",
    "CITED_UNIT_RULES",
    "CLASS_CRYPTO",
    "CLASS_STOCKS",
    "DRAWDOWN_STATE",
    "FRACTIONAL_UNITS",
    "TAPER_DROP",
    "TAPER_START_RATIO",
    "UNIT_RULES",
    "WHOLE_UNITS",
    "WHOLE_UNIT_GRAIN",
    "cartridge_threshold_usd",
    "cycle_growth_cap_usd",
    "delta_below_interval",
    "eligible_fold_tranches",
    "estimated_fee_usd",
    "fold_cap_remaining_usd",
    "fold_rate_taper",
    "fold_spend_usd",
    "fold_units",
    "opposing_trade_distance_pct",
    "opposing_trade_distances",
    "plan_fold_consumption",
    "plan_source_price",
    "position_ceiling",
    "priced_usd",
    "ratio_to_ceiling",
    "sale_proceeds_usd",
    "scrum_units",
    "scrumming_interval_usd",
    "settle_fold_plan",
    "sized_units",
    "target_delta_pct",
    "target_delta_usd",
    "trim_fold_plan",
    "unit_rule",
    "wallet_capped_spend_usd",
]
