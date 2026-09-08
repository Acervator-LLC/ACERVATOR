"""gate_vocabulary.py -- the bot's gate labels, blocker map and light states.

Qt-free. The History table's gate cell
(``src/exchange/history_read_contract.py``) reads it.

The labels and the blocker prefixes are the ones ScrummingBot writes into
``_last_gate_state.{scrum,fold}_blockers``.
"""

from __future__ import annotations

from typing import Optional

# Scrum and fold are asymmetric: the bot evaluates a different condition
# set on each side. 10 scrum labels, 9 fold labels, 19 lights per row.
_GATE_ORDER_SCRUM: tuple[str, ...] = (
    "TGT",  # delta<=0
    "INT",  # below_interval(delta% < scrumming_interval_pct)
    "BB",  # BB-below-upper-detect / scrum_ok=False
    "FIRE",  # target_fires=False (detect/fire state machine)
    "TA",  # TA-not-bullish
    "LS",  # landing-strip override, not a blocker
    "TRND",  # trend_hold(strength)
    "HTF",  # HTF-bullish
    "CB",  # circuit breaker
    "OTD",  # opposing-trade-distance hysteresis
)
_GATE_ORDER_FOLD: tuple[str, ...] = (
    "BB",  # BB-above-lower-detect
    "MID",  # fold_ok_midline=False
    "TA",  # TA-not-bearish
    "LS",  # landing-strip override
    "TRNQ",  # no-tranches-queued
    "CEIL",  # MEM-253 position ceiling
    "HTF",  # HTF-bearish
    "CB",  # circuit breaker
    "OTD",  # opposing-trade-distance hysteresis
)

# LS is an override, not a pass/fail gate, and never appears in a blocker list.
_GATE_OVERRIDE = "LS"

# Ordered most-specific-first; sorting breaks the prefix match.
_BLOCKER_PREFIXES: tuple[tuple[str, str], ...] = (
    # scrum -- specific before general
    ("target_fires", "FIRE"),
    ("below_interval", "INT"),
    ("BB-below-upper", "BB"),
    ("scrum_ok=False", "BB"),
    ("TA-not-bullish", "TA"),
    ("trend_hold", "TRND"),
    ("HTF-bullish", "HTF"),
    ("delta", "TGT"),
    # fold
    ("BB-above-lower", "BB"),
    ("fold_ok_midline", "MID"),
    ("TA-not-bearish", "TA"),
    ("no-tranches-queued", "TRNQ"),
    ("MEM-253", "CEIL"),
    ("HTF-bearish", "HTF"),
    # shared
    ("CB-soft-trip", "CB"),
    ("CB-hard", "CB"),
    ("OTD-hyst", "OTD"),
)

# The five light states and the colour each one paints.
LIGHT_COLORS: dict[str, str] = {
    "override": "#22d3ee",
    "not_evaluated": "#333340",
    "blocked": "#ff3366",
    "passed": "#00cc55",
    "not_the_blocker": "#c8901e",
}

LIGHT_LABEL_COLOR = "#9aa0b5"
BANK_MARKER_COLOR = "#6b7280"


def gate_for_blocker(blocker: str) -> str:
    """Map one blocker string to its gate label, or "" if unknown.

    An unknown blocker means the bot grew a condition the display does
    not represent. Callers surface it rather than discarding it.
    """
    text = str(blocker or "")
    for prefix, gate in _BLOCKER_PREFIXES:
        if text.startswith(prefix):
            return gate
    # A few sites prepend context to the blocker text, so a
    # contains-check runs before the mapping gives up.
    low = text.lower()
    for prefix, gate in _BLOCKER_PREFIXES:
        if prefix.lower() in low:
            return gate
    return ""


def _blocked_labels(blockers: list) -> set[str]:
    """The set of gate labels the given blocker phrases name."""
    hits: set[str] = set()
    for b in blockers or []:
        gate = gate_for_blocker(b)
        if gate:
            hits.add(gate)
    return hits


def unknown_blockers(blockers: list) -> list[str]:
    """Blocker phrases that map to no gate label."""
    return [str(b) for b in (blockers or []) if not gate_for_blocker(b)]


def gate_light_state(
    label: str,
    evaluated: bool,
    armed: bool,
    blocked: set,
    ls_active: bool,
) -> str:
    """The state one light is in. A key of ``LIGHT_COLORS``.

    Order is load-bearing: the override is decided before the evaluated
    check, so an active landing strip reads as an override rather than
    as an unevaluated gate.
    """
    if label == _GATE_OVERRIDE:
        return "override" if ls_active else "not_evaluated"
    if not evaluated:
        return "not_evaluated"
    if label in blocked:
        return "blocked"
    if armed:
        return "passed"
    return "not_the_blocker"


def gate_light_color(
    label: str,
    evaluated: bool,
    armed: bool,
    blocked: set,
    ls_active: bool,
) -> str:
    """The "#rrggbb" one light paints."""
    return LIGHT_COLORS[gate_light_state(label, evaluated, armed, blocked, ls_active)]


def gate_light_row(
    scrum_armed: bool,
    fold_armed: bool,
    scrum_blockers: Optional[list] = None,
    fold_blockers: Optional[list] = None,
    landing_strip_side: str = "",
    evaluated: bool = True,
) -> list[dict]:
    """The nineteen lights, in draw order: the scrum bank then the fold.

    Each entry carries ``bank`` ("S" or "F"), ``label``, ``state`` and
    ``color``. Serialisable: no Qt type crosses this boundary.
    """
    scrum_blocked = _blocked_labels(scrum_blockers or [])
    fold_blocked = _blocked_labels(fold_blockers or [])
    side = str(landing_strip_side or "").lower()
    out: list[dict] = []
    for bank, gates, armed, blocked, ls_active in (
        ("S", _GATE_ORDER_SCRUM, bool(scrum_armed), scrum_blocked, side == "upper"),
        ("F", _GATE_ORDER_FOLD, bool(fold_armed), fold_blocked, side == "lower"),
    ):
        for label in gates:
            state = gate_light_state(label, evaluated, armed, blocked, ls_active)
            out.append(
                {
                    "bank": bank,
                    "label": label,
                    "state": state,
                    "color": LIGHT_COLORS[state],
                }
            )
    return out


__all__ = [
    "BANK_MARKER_COLOR",
    "LIGHT_COLORS",
    "LIGHT_LABEL_COLOR",
    "gate_for_blocker",
    "gate_light_color",
    "gate_light_row",
    "gate_light_state",
    "unknown_blockers",
]
