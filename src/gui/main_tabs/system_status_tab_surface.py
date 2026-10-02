"""system_status_tab_surface.py -- the Status tab's emitter network read-out as data.

``view_model`` answers the emitter network twice over: ``subsystems`` carries one
panel per subsystem prefix with that subsystem's own emitter read-outs, and ``tabs``
carries the same panels grouped under the tab each subsystem serves. The numbers
come from ``src.core.signal_contract.subsystem_health`` against the sink
installed in this process, so no value is held here.
"""

from __future__ import annotations

from src.core.signal_contract import (
    ENGINE_GROUP,
    HEALTH_GREEN,
    HEALTH_STATES,
    HEALTH_YELLOW,
    TAB_BY_SUBSYSTEM,
    get_sink,
    subsystem_health,
    tab_of,
)

METHOD = "system_status_tab.state"

HEADING = "Status"

LEGEND = (
    "Green and Yellow only. Green: every always-on emitter fired and nothing "
    "failed. Yellow: something failed, or an always-on emitter never fired. "
    "Red needs an expected rhythm per emitter and no emitter declares one."
)

NO_FEED_TEXT = "No emitter sink is installed in this process."
NO_RECORDS_TEXT = "no records this run"
NO_EMITTERS_TEXT = "no emitters"

#: The counter labels a subsystem panel and a tab group both draw, in draw
#: order. The first of each pair is the field the count is read from.
COUNT_LABELS = (
    ("emitters_declared", "declared"),
    ("emitters_fired", "fired"),
    ("emitters_silent", "silent"),
    ("always_on_silent", "always-on silent"),
    ("emitted", "records"),
    ("failed", "failed"),
)

#: The feed labels, read off the sink's own integrity counters.
FEED_LABELS = (
    ("path", "file"),
    ("emitted", "records"),
    ("retained", "in memory"),
    ("evicted", "evicted"),
    ("dropped", "dropped"),
)

#: The emitter read-out fields a subsystem panel draws, in column order. The
#: first of each pair is the field the value is read from.
EMITTER_COLUMNS = (
    ("name", "Emitter"),
    ("cadence", "Cadence"),
    ("emitted", "Fired"),
    ("failed", "Failed"),
    ("latest", "Latest value"),
)

EMITTER_FIELDS = tuple(pair[0] for pair in EMITTER_COLUMNS)

#: Every word the renderer module draws that no count or name supplies.
LABELS = {
    "subsystems": "By subsystem",
    "tabs": "By tab",
    "emitter_columns": [pair[1] for pair in EMITTER_COLUMNS],
    "counts": [list(pair) for pair in COUNT_LABELS],
    "feed": [list(pair) for pair in FEED_LABELS],
    "totals": [["subsystems", "subsystems"]] + [list(p) for p in COUNT_LABELS],
}

DECLARED_FIELDS = (
    "accessible_name",
    "built",
    "feed",
    "heading",
    "health_states",
    "labels",
    "legend",
    "method",
    "no_emitters_text",
    "no_feed_text",
    "no_records_text",
    "subsystems",
    "tabs",
    "totals",
)

#: The per-subsystem counters ``tabs`` adds up across the subsystems it holds.
ROLLED_COUNTS = (
    "emitters_declared",
    "emitters_fired",
    "emitters_silent",
    "always_on_silent",
    "emitted",
    "failed",
)


def _feed(sink) -> dict:
    """The sink's own integrity counters, or zeros when no sink is installed."""
    if sink is None:
        return {
            "installed": False,
            "path": None,
            "emitted": 0,
            "retained": 0,
            "evicted": 0,
            "dropped": 0,
        }
    held = sink.health()
    return {
        "installed": True,
        "path": held["path"],
        "emitted": held["emitted"],
        "retained": held["retained"],
        "evicted": held["evicted"],
        "dropped": held["dropped"],
    }


def _roll(rows: list) -> dict:
    """Sum ``ROLLED_COUNTS`` across ``rows`` and settle one health from them."""
    out = {name: sum(row[name] for row in rows) for name in ROLLED_COUNTS}
    out["health"] = None
    if out["failed"] or out["always_on_silent"]:
        out["health"] = HEALTH_YELLOW
    elif out["emitted"]:
        out["health"] = HEALTH_GREEN
    return out


def _tab_order() -> list:
    """The tab labels in bar order, then ``ENGINE_GROUP``, then any stray label."""
    from .main_window_surface import CANONICAL_TAB_ORDER

    order = list(CANONICAL_TAB_ORDER) + [ENGINE_GROUP]
    for label in sorted(set(TAB_BY_SUBSYSTEM.values())):
        if label not in order:
            order.append(label)
    return order


def _tab_rows(subsystems: list) -> list:
    """One row per tab label, carrying the subsystems that label holds."""
    held: dict = {}
    for row in subsystems:
        held.setdefault(row["tab"], []).append(row)
    rows = []
    for label in _tab_order():
        members = held.get(label, [])
        row = {
            "tab": label,
            "subsystems": [member["subsystem"] for member in members],
            **_roll(members),
        }
        rows.append(row)
    return rows


def _subsystem_rows(sink) -> list:
    """Every subsystem's read-out, in name order, each carrying its tab."""
    rows = []
    for subsystem, row in sorted(subsystem_health(sink).items()):
        rows.append({**row, "tab": tab_of(subsystem)})
    return rows


def view_model(params: dict) -> dict:
    """Bridge handler for ``system_status_tab.state``.

    Answers every name in ``DECLARED_FIELDS`` from the sink installed in this
    process, the same for any ``params``.
    """
    del params
    sink = get_sink()
    subsystems = _subsystem_rows(sink)
    return {
        "accessible_name": HEADING,
        "built": True,
        "feed": _feed(sink),
        "heading": HEADING,
        "health_states": list(HEALTH_STATES),
        "labels": LABELS,
        "legend": LEGEND,
        "method": METHOD,
        "no_emitters_text": NO_EMITTERS_TEXT,
        "no_feed_text": NO_FEED_TEXT,
        "no_records_text": NO_RECORDS_TEXT,
        "subsystems": subsystems,
        "tabs": _tab_rows(subsystems),
        "totals": {"subsystems": len(subsystems), **_roll(subsystems)},
    }
