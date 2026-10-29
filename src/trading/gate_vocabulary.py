"""gate_vocabulary.py -- the bot's gate labels, blocker map and light states.

Qt-free. The History table's gate cell
(``src/exchange/history_read_contract.py``) reads it.

The labels and the blocker prefixes are the ones ScrummingBot writes into
``_last_gate_state.{scrum,fold}_blockers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

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
    "CEIL",  # position ceiling
    "HTF",  # HTF-bearish
    "CB",  # circuit breaker
    "OTD",  # opposing-trade-distance hysteresis
)

# LS is an override, not a pass/fail gate, and never appears in a blocker list.
_GATE_OVERRIDE = "LS"

# One sentence of the module docstring above is overtaken. Quoted whole:
#   "The labels and the blocker prefixes are the ones ScrummingBot writes into
#   ``_last_gate_state.{scrum,fold}_blockers``."
# The prefixes also carry the ``Gate.name`` values ``ChainResult.blocked``
# reports, so a blocker named by either source resolves to the same label.
# Ordered most-specific-first; sorting breaks the prefix match.
_BLOCKER_PREFIXES: tuple[tuple[str, str], ...] = (
    # scrum -- specific before general
    ("target_fires", "FIRE"),
    ("below_interval", "INT"),
    ("BB-below-upper", "BB"),
    ("scrum_ok=False", "BB"),
    ("TA-conf-below-floor", "TA"),
    ("TA-not-bullish", "TA"),
    ("trend_hold", "TRND"),
    ("HTF-bullish", "HTF"),
    ("delta", "TGT"),
    # fold
    ("BB-above-lower", "BB"),
    ("fold_ok_midline", "MID"),
    ("TA-not-bearish", "TA"),
    ("no-tranches-queued", "TRNQ"),
    ("position-ceiling", "CEIL"),
    ("HTF-bearish", "HTF"),
    # shared
    ("CB-soft-trip", "CB"),
    ("CB-hard", "CB"),
    ("OTD-hyst", "OTD"),
    # Gate.name in src/trading/gate_chain.py, as ChainResult.blocked names it.
    ("circuit_breaker_scrum", "CB"),
    ("circuit_breaker_fold", "CB"),
    ("smart_ceiling", "CEIL"),
    ("hysteresis_scrum", "OTD"),
    ("hysteresis_fold", "OTD"),
    ("interval", "INT"),
    ("tranches_queued", "TRNQ"),
)

# The six light states and the colour each one paints. "override" is the LS
# light alone; "overridden" is a gate whose refusal an override replaced, and
# both paint the landing strip's cyan.
LIGHT_COLORS: dict[str, str] = {
    "override": "#22d3ee",
    "overridden": "#22d3ee",
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


def _labels_for(phrases: list) -> set[str]:
    """The set of gate labels the given refusal phrases name.

    ``gate_light_row`` reads it for a blocker list and for the refusals an
    override replaced.
    """
    hits: set[str] = set()
    for one in phrases or []:
        gate = gate_for_blocker(one)
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
    overridden: Optional[set] = None,
) -> str:
    """The state one light is in, a key of ``LIGHT_COLORS``.

    ``_GATE_OVERRIDE`` is decided ahead of ``evaluated``, and ``blocked``
    ahead of ``overridden``.
    """
    if label == _GATE_OVERRIDE:
        return "override" if ls_active else "not_evaluated"
    if not evaluated:
        return "not_evaluated"
    if label in blocked:
        return "blocked"
    if label in (overridden or ()):
        return "overridden"
    if armed:
        return "passed"
    return "not_the_blocker"


def gate_light_color(
    label: str,
    evaluated: bool,
    armed: bool,
    blocked: set,
    ls_active: bool,
    overridden: Optional[set] = None,
) -> str:
    """The "#rrggbb" one light paints."""
    return LIGHT_COLORS[
        gate_light_state(label, evaluated, armed, blocked, ls_active, overridden)
    ]


def gate_light_row(
    scrum_armed: bool,
    fold_armed: bool,
    scrum_blockers: Optional[list] = None,
    fold_blockers: Optional[list] = None,
    landing_strip_side: str = "",
    evaluated: bool = True,
    scrum_overridden: Optional[list] = None,
    fold_overridden: Optional[list] = None,
    scrum_not_run: Optional[list] = None,
    fold_not_run: Optional[list] = None,
) -> list[dict]:
    """The nineteen lights, in draw order: the scrum bank then the fold.

    ``scrum_overridden`` and ``fold_overridden`` carry each refusal an
    override replaced, and a gate ``scrum_not_run`` or ``fold_not_run`` names
    reads not evaluated.
    """
    scrum_blocked = _labels_for(scrum_blockers or [])
    fold_blocked = _labels_for(fold_blockers or [])
    scrum_replaced = _labels_for(scrum_overridden or [])
    fold_replaced = _labels_for(fold_overridden or [])
    side = str(landing_strip_side or "").lower()
    out: list[dict] = []
    for bank, gates, armed, blocked, ls_active, replaced, unread in (
        (
            "S",
            _GATE_ORDER_SCRUM,
            bool(scrum_armed),
            scrum_blocked,
            side == "upper",
            scrum_replaced,
            _labels_for(scrum_not_run or []),
        ),
        (
            "F",
            _GATE_ORDER_FOLD,
            bool(fold_armed),
            fold_blocked,
            side == "lower",
            fold_replaced,
            _labels_for(fold_not_run or []),
        ),
    ):
        for label in gates:
            state = gate_light_state(
                label,
                evaluated and label not in unread,
                armed,
                blocked,
                ls_active,
                replaced,
            )
            out.append(
                {
                    "bank": bank,
                    "label": label,
                    "state": state,
                    "color": LIGHT_COLORS[state],
                }
            )
    return out


SCRUM_BANK = "S"
FOLD_BANK = "F"


def bare_gate_name(blocker: Any) -> str:
    """A blocker phrase with the live figures it carries dropped.

    ``BB-below-upper-detect(bb_pos=0.39<0.88)`` answers
    ``BB-below-upper-detect``, so one gate refusing at two prices answers one name.
    """
    text = str(blocker)
    for mark in ("(", "="):
        cut = text.find(mark)
        if cut > 0:
            text = text[:cut]
    return text


@dataclass(frozen=True)
class LightReading:
    """One gate reading's ``gate_light_row`` lights, with ``armed``, ``blockers``,
    ``replaced`` and ``unmapped`` keyed by ``SCRUM_BANK`` and ``FOLD_BANK``."""

    lights: list
    armed: dict
    blockers: dict
    replaced: dict
    unmapped: dict


def light_reading(
    armed: dict,
    blockers: dict,
    replaced: dict,
    landing_strip_side: str = "",
    not_run: Optional[dict] = None,
) -> LightReading:
    """``gate_light_row`` over per-bank ``armed``, ``blockers`` and ``replaced``.

    A gate ``not_run`` names reads not evaluated, and each ``unknown_blockers``
    phrase is kept under ``unmapped`` by its ``bare_gate_name``.
    """
    unread = not_run or {}
    return LightReading(
        lights=gate_light_row(
            scrum_armed=bool(armed.get(SCRUM_BANK)),
            fold_armed=bool(armed.get(FOLD_BANK)),
            scrum_blockers=list(blockers.get(SCRUM_BANK) or []),
            fold_blockers=list(blockers.get(FOLD_BANK) or []),
            landing_strip_side=landing_strip_side,
            scrum_overridden=list(replaced.get(SCRUM_BANK) or []),
            fold_overridden=list(replaced.get(FOLD_BANK) or []),
            scrum_not_run=list(unread.get(SCRUM_BANK) or []),
            fold_not_run=list(unread.get(FOLD_BANK) or []),
        ),
        armed=dict(armed),
        blockers=dict(blockers),
        replaced=dict(replaced),
        unmapped={
            bank: [
                bare_gate_name(one)
                for one in unknown_blockers(blockers.get(bank) or [])
            ]
            for bank in (SCRUM_BANK, FOLD_BANK)
        },
    )


__all__ = [
    "BANK_MARKER_COLOR",
    "FOLD_BANK",
    "LIGHT_COLORS",
    "LIGHT_LABEL_COLOR",
    "SCRUM_BANK",
    "LightReading",
    "bare_gate_name",
    "gate_for_blocker",
    "gate_light_color",
    "gate_light_row",
    "gate_light_state",
    "light_reading",
    "unknown_blockers",
]
