"""The Scrum/Fold cycle's sizing arithmetic, one definition of each figure.

``ScrummingBot.tick``, ``TickPhaseMixin``, ``ExecutionEngineMixin`` and
``FoldTrancheAccountingMixin`` call these at the sites that computed each figure
inline, and ``back_test.walk`` calls the same functions over a ``SimPosition``.
``priced_usd`` through ``cartridge_threshold_usd`` each answer the expression
their Live site held, in that site's operand order, holding no state.
"""

from __future__ import annotations

#: The ``state`` an ``ExtractorBot`` writes on a position below its entry value.
DRAWDOWN_STATE = "drawdown"

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


def scrum_units(delta_usd: float, price: float) -> float:
    """The units a scrum sells: ``delta_usd`` at ``price``."""
    return abs(delta_usd) / price


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


def fold_spend_usd(eligible_usd: float, taper: float) -> float:
    """The USD a fold buys with: ``eligible_usd`` times ``taper``."""
    return eligible_usd * taper


def wallet_capped_spend_usd(spend_usd: float, available_usd: float) -> float:
    """``spend_usd`` held to ``available_usd``, the cap Manual Fire applies."""
    return min(spend_usd, available_usd)


def fold_units(spend_usd: float, price: float) -> float:
    """The units a buy of ``spend_usd`` at ``price`` books."""
    return spend_usd / price


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
    "DRAWDOWN_STATE",
    "TAPER_DROP",
    "TAPER_START_RATIO",
    "cartridge_threshold_usd",
    "cycle_growth_cap_usd",
    "delta_below_interval",
    "eligible_fold_tranches",
    "estimated_fee_usd",
    "fold_cap_remaining_usd",
    "fold_rate_taper",
    "fold_spend_usd",
    "fold_units",
    "plan_fold_consumption",
    "position_ceiling",
    "priced_usd",
    "ratio_to_ceiling",
    "sale_proceeds_usd",
    "scrum_units",
    "scrumming_interval_usd",
    "settle_fold_plan",
    "target_delta_pct",
    "target_delta_usd",
    "wallet_capped_spend_usd",
]
