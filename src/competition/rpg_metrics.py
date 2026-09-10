"""One bot's trading profile, converted into the RPG metrics a participant plays.

``profile_metrics`` reads a persisted bot record, a ``bot.gate_decision``
payload, a ``trade.filled`` payload, a ``TradeGrade`` and a voting-panel
snapshot, and answers one entry a metric. ``METRIC_SOURCES`` names the field
behind each metric, and a metric whose field is absent answers None.
``METRIC_SEAMS`` names what no field under ``src`` holds.
"""

from __future__ import annotations

SELL = "SELL"
BUY = "BUY"

#: The field behind each metric, as the emitter or the record names it.
METRIC_SOURCES: dict[str, str] = {
    "max_health_usd": "scrumming_state.target_balance",
    "base_health_usd": "scrumming_state.anchor_target_balance",
    "levelled_health_usd": "compounding_snapshot.accrued_growth_usd",
    "level_gain_cap_usd": "compounding_snapshot.cycle_growth_budget_usd",
    "level_gain_cap_pct": "config.max_target_growth_pct",
    "current_health_usd": "max_health_usd + scrum_fixture.delta",
    "wound_pct": "GateContext.delta_pct",
    "damage_usd": "stats.ytd_scrummed_usd",
    "damage_hit_usd": "trade.filled.usd on a SELL",
    "healing_usd": "stats.ytd_folded_usd",
    "healing_hit_usd": "trade.filled.usd on a BUY",
    "heal_pending_count": "tranche_snapshot.fold_count",
    "heal_pending_usd": "tranche_snapshot.fold_total_usd",
    "accuracy": "TradeGrade.execution_score",
    "accuracy_bps": "TradeGrade.execution_bps",
    "efficacy_timing": "TradeGrade.timing_score",
    "efficacy_outcome": "TradeGrade.outcome_score",
    "efficacy_strategic": "TradeGrade.strategic_score",
    "grade_numeric": "TradeGrade.overall_numeric",
    "grade_letter": "TradeGrade.overall",
    "crit_confidence": "VotingSummary.consensus_confidence",
    "fumble_adjusted": "stats.verify_adjusted",
    "fumble_canceled": "stats.verify_canceled",
    "fumble_errors": "stats.consecutive_errors",
    "pool_usd": "stats.standing_surplus_usd",
    "cash_usd": "stats.cash_balance_usd",
    "blocked": "bot.gate_decision scrum_blockers and fold_blockers",
}

#: Metrics this package must create. No field under ``src`` holds any of them.
METRIC_SEAMS: tuple[str, ...] = (
    "experience",
    "level",
    "character class",
    "gear",
    "enemy",
    "threat",
    "guild",
)

#: Every name ``profile_metrics`` answers.
METRIC_NAMES: tuple[str, ...] = tuple(METRIC_SOURCES)


def _read(holder: object, name: str) -> object:
    """Return ``holder[name]`` for a mapping, ``holder.name`` for an object."""
    if isinstance(holder, dict):
        return holder.get(name)
    return getattr(holder, name, None)


def _number(holder: object, name: str) -> float | None:
    """Return the named value as a float, or None when it is absent or not numeric."""
    value = _read(holder, name)
    if type(value) is int:
        return float(value)
    if type(value) is float:
        return value
    return None


def _whole(holder: object, name: str) -> int | None:
    """Return the named value as an int, or None when it is absent or not numeric."""
    value = _number(holder, name)
    return None if value is None else int(value)


def _words(holder: object, name: str) -> str | None:
    """Return the named value as a non-empty string, or None."""
    value = _read(holder, name)
    if type(value) is not str or value == "":
        return None
    return value


def _labels(holder: object, name: str) -> list[str]:
    """Return the named list's string members, or an empty list."""
    value = _read(holder, name)
    if not isinstance(value, list):
        return []
    return [member for member in value if type(member) is str]


def health_metrics(record: object, gate: object) -> dict:
    """Return the health pool, from the dollar target and the distance from it.

    ``current_health_usd`` needs ``scrum_fixture.delta`` off ``gate`` and
    answers None without one.
    """
    scrumming = _read(record, "scrumming_state")
    config = _read(record, "config")
    compounding = _read(gate, "compounding_snapshot")
    maximum = _number(scrumming, "target_balance")
    delta = _number(_read(gate, "scrum_fixture"), "delta")
    current = None if maximum is None or delta is None else maximum + delta
    return {
        "max_health_usd": maximum,
        "base_health_usd": _number(scrumming, "anchor_target_balance"),
        "levelled_health_usd": _number(compounding, "accrued_growth_usd"),
        "level_gain_cap_usd": _number(compounding, "cycle_growth_budget_usd"),
        "level_gain_cap_pct": _number(config, "max_target_growth_pct"),
        "current_health_usd": current,
        "wound_pct": _number(gate, "delta_pct"),
    }


def cycle_metrics(record: object, gate: object, fill: object) -> dict:
    """Return damage from the scrum half of the cycle and healing from the fold half.

    ``damage_hit_usd`` and ``healing_hit_usd`` read one ``fill`` and split on
    its ``side``.
    """
    stats = _read(record, "stats")
    tranches = _read(gate, "tranche_snapshot")
    side = _words(fill, "side")
    hit = _number(fill, "usd")
    return {
        "damage_usd": _number(stats, "ytd_scrummed_usd"),
        "damage_hit_usd": hit if side == SELL else None,
        "healing_usd": _number(stats, "ytd_folded_usd"),
        "healing_hit_usd": hit if side == BUY else None,
        "heal_pending_count": _whole(tranches, "fold_count"),
        "heal_pending_usd": _number(tranches, "fold_total_usd"),
    }


def grade_metrics(grade: object) -> dict:
    """Return accuracy and efficacy, from the sub-scores of one graded trade."""
    return {
        "accuracy": _number(grade, "execution_score"),
        "accuracy_bps": _number(grade, "execution_bps"),
        "efficacy_timing": _number(grade, "timing_score"),
        "efficacy_outcome": _number(grade, "outcome_score"),
        "efficacy_strategic": _number(grade, "strategic_score"),
        "grade_numeric": _number(grade, "overall_numeric"),
        "grade_letter": _words(grade, "overall"),
    }


def condition_metrics(record: object, gate: object, voting: object) -> dict:
    """Return the crit reading, the fumble counts, the pool and the gate labels.

    ``crit_confidence`` is the reading; the confidence a crit fires at is unset.
    """
    stats = _read(record, "stats")
    return {
        "crit_confidence": _number(voting, "consensus_confidence"),
        "fumble_adjusted": _whole(stats, "verify_adjusted"),
        "fumble_canceled": _whole(stats, "verify_canceled"),
        "fumble_errors": _whole(stats, "consecutive_errors"),
        "pool_usd": _number(stats, "standing_surplus_usd"),
        "cash_usd": _number(stats, "cash_balance_usd"),
        "blocked": _labels(gate, "scrum_blockers") + _labels(gate, "fold_blockers"),
    }


def profile_metrics(
    record: object,
    gate: object = None,
    fill: object = None,
    grade: object = None,
    voting: object = None,
) -> dict:
    """Return every name in ``METRIC_NAMES``, off ``record`` and the readings beside it."""
    metrics: dict = {}
    metrics.update(health_metrics(record, gate))
    metrics.update(cycle_metrics(record, gate, fill))
    metrics.update(grade_metrics(grade))
    metrics.update(condition_metrics(record, gate, voting))
    return metrics


def read_metrics(metrics: dict) -> dict:
    """Return only the entries of ``metrics`` that carry a value."""
    return {
        name: value
        for name, value in metrics.items()
        if value is not None and value != []
    }
