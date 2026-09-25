"""signal_contract.py -- the emitter contract for the platform's signal network.

Defines `Signal`, the frozen record `emit()` produces, and `SignalSink`,
the buffered sink that stores and rotates them under
`~/.acervator_logs/signals/`. A satisfied expectation is recorded the
same as a violated one, so a call site that never ran and one that
always passed are both visible. `route_thread` sends the calling
thread's emits to another `SignalSink` until `unroute_thread`; the
Simulator routes each run's worker thread to its own sink under the sim
bucket, so `get_sink` answers per thread.
"""

from __future__ import annotations

import json
import math
import sys
import threading
import time
from collections import deque
from types import MappingProxyType
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_FLUSH_EVERY = 200
"""Rows buffered in memory before `flush()` writes them to disk."""

PROCESS_SINK_FLUSH_EVERY = 500
"""Rows the sink `install_process_sink` builds buffers before `flush()`; a sink
built to match it, such as the Simulator's, reads this figure.
"""

RETAIN_ROWS = 350_000
"""Signal records kept in memory at once; older ones are evicted from memory but remain
in the file on disk.
"""

MAX_FILE_BYTES = 50 * 1024 * 1024
"""Byte size at which the sink's file rotates to `.1`."""

FILE_BACKUP_COUNT = 5
"""Backup files kept when the sink's file rotates."""


DIGEST_MIN_INTERVAL = 10.0
"""Seconds an identity must wait before its next digest-log line is admitted."""

DIGEST_FILE_BYTES = 16 * 1024 * 1024
"""Byte size at which the digest file rotates to `.1`."""

DIGEST_BACKUP_COUNT = 5
"""Backup files kept when the digest file rotates."""


FRESH_WITHIN = 0.5
"""Age below which a pin reads as just fired, in seconds."""

STALE_AFTER = 660.0
"""Age above which any pin reads as stale via `pin_state`/`timing`, in seconds."""

MAX_IDENTITIES = 10_000
"""Distinct `(name, site)` identities the last-seen map tracks; further identities are
recorded but not timed.
"""

PIN_NEVER = "never"
"""No record with this identity has ever entered this sink; distinct from `PIN_STALE`,
which requires a prior emission.
"""

PIN_FRESH = "fresh"
"""This identity emitted within `fresh_within` seconds."""

PIN_CURRENT = "current"
"""This identity emitted between `fresh_within` and `stale_after` seconds ago."""

PIN_STALE = "stale"
"""This identity last emitted more than `stale_after` seconds ago."""

PIN_STATES = (PIN_NEVER, PIN_FRESH, PIN_CURRENT, PIN_STALE)
"""The four pin states. `PIN_NEVER` carries `age=None` and `n=0`; the others carry a
float age and a positive count.
"""


CADENCE_ALWAYS_ON = "always_on"
"""A self-driven loop, timer or stream reaches this pin on every pass."""

CADENCE_TOGGLE = "toggle"
"""This pin needs a discrete trigger. Silence from it says nothing."""

CADENCE_CATEGORIES = (CADENCE_ALWAYS_ON, CADENCE_TOGGLE)
"""The closed vocabulary. Two terms, declared per pin, never inferred."""

ALWAYS_ON_WORST_HEALTHY_GAP = 4.736
"""Widest gap, in seconds, any measured always-on identity produced; the basis for
`ALWAYS_ON_STALE_AFTER`.
"""

ALWAYS_ON_STALE_AFTER = 10.0
"""Age above which an untimed always-on pin reads as late in `cadence_verdict`, in
seconds.
"""

ALWAYS_ON_SLACK = ALWAYS_ON_STALE_AFTER / ALWAYS_ON_WORST_HEALTHY_GAP
"""Ratio applied to a throttled pin's own `every=` window to get its stale budget; see
`always_on_stale_after`.
"""

MISCATEGORY_MEAN_INTERVAL = 2.814
"""Mean interval, in seconds, at or below which a declared `toggle` reads as
`CADENCE_TOGGLE_AT_LOOP_RATE`.
"""

MISCATEGORY_MIN_SAMPLES = 100
"""Emissions required before a toggle's mean interval is compared against
`MISCATEGORY_MEAN_INTERVAL`.
"""

CADENCE_ON_TIME = "on_time"
"""An always-on pin emitted inside its own budget."""

CADENCE_STALE = "stale"
"""An always-on pin has not emitted inside its own budget."""

CADENCE_NEVER_FIRED = "never_fired"
"""An always-on pin the sink has no record of at all."""

CADENCE_NOT_APPLICABLE = "not_applicable"
"""A toggle pin, for which no cadence is expected."""

CADENCE_TOGGLE_AT_LOOP_RATE = "toggle_at_loop_rate"
"""A pin declared `toggle` that is emitting at always-on rate."""

CADENCE_UNDECLARED = "undeclared"
"""No cadence category is declared for this pin name."""

CADENCE_VERDICTS = (
    CADENCE_ON_TIME,
    CADENCE_STALE,
    CADENCE_NEVER_FIRED,
    CADENCE_NOT_APPLICABLE,
    CADENCE_TOGGLE_AT_LOOP_RATE,
    CADENCE_UNDECLARED,
)
"""Every verdict a cadence row can carry."""

_ALWAYS_ON_PINS: dict[str, str] = {
    "bot.01.002.postcondition.capital_reservation": (
        "the no-raise arm of a call every tick of every bot makes"
    ),
    "ta.07.003.postcondition.computed": (
        "the indicator compute every worked tick of every bot runs"
    ),
    "ta.07.004.postcondition.raw.{}": (
        "the reporting loop of that same per-tick compute"
    ),
    "tick.08.001.event.throttled": (
        "the throttle arm of the tick loop; the loop's own pacing takes it, not any "
        "event"
    ),
    "tick.08.002.event.worked": "the work arm of the same tick loop",
    "charts.13.001.invariant.panels_mounted": (
        "the 2000 ms dashboard timer calls `update_charts` while any bot exists"
    ),
    "charts.13.002.postcondition.panel_symbols_current": (
        "the same timer, the same call"
    ),
    "charts.13.004.postcondition.panel_refreshed": (
        "the same 2000 ms timer schedules `fetch_chart_data`"
    ),
    "charts.13.005.invariant.panels_fresh": "the same scheduled pass",
    "charts.indicators.drawn": (
        "the same `fetch_chart_data` pass calls `set_candles` on every fetch that "
        "returns candles"
    ),
    "console.14.001.invariant.records_rendered": (
        "the Console's 5000 ms health timer, which runs for the life of the window"
    ),
    "console.14.002.invariant.view_holds_rendered": "the same health timer",
    "console.14.003.invariant.drain_alive": "the same health timer",
    "exchange.15.002.invariant.every_bot_reaches_a_table": (
        "the 2000 ms dashboard timer calls `update_bots` once per exchange tab"
    ),
    "exchange.15.003.invariant.selection_survives_refresh": (
        "the same timer, the same call"
    ),
    "swarm.11.003.invariant.frame_cadence": (
        "the Bot Swarm animation timer folds every frame gap and reports each "
        "five-second window"
    ),
}
"""The sixteen pins a loop or a timer reaches on every pass, categorised
`CADENCE_ALWAYS_ON`. Each value is the reason, read at the call site.
"""

_TOGGLE_PINS: dict[str, str] = {
    "bot.01.001.postcondition.capital_reservation": (
        "the `except` arm only; the reservation ensure has to raise"
    ),
    "bot.01.003.postcondition.adoption_capped": (
        "only when the operator's holdings exceed the adoption cap"
    ),
    "extractor.02.001.postcondition.tranche_contained": (
        "only when an extractor tranche arrives at the parent bot"
    ),
    "extractor.02.002.invariant.arrival_atomic": (
        "the same arrival; nothing arrives on the loop's own account"
    ),
    "gui.04.001.postcondition.voting_panel.fit": (
        "a show or a resize event on the voting panel"
    ),
    "gui.04.002.postcondition.clear_settled": (
        "the operator accepts a Clear in the dialog"
    ),
    "gui.04.003.postcondition.despawn_rows_match_ledger": (
        "the operator opens or rebuilds the Fold Tranches tab"
    ),
    "history.05.001.postcondition.scan_complete": (
        "the history scan thread, started once per venue connect"
    ),
    "history.05.002.postcondition.trades_stored": "the operator presses Refresh",
    "history.05.003.postcondition.filter_options_built": (
        "the operator loads or refreshes the tab"
    ),
    "history.05.004.postcondition.filters_applied": (
        "the operator presses Apply or Reset"
    ),
    "history.05.005.postcondition.page_rendered": "the operator turns a page",
    "history.05.006.postcondition.joiner_indexes_built": "the operator turns a page",
    "history.05.007.postcondition.csv_exported": "the operator presses Export CSV",
    "tick.08.003.event.exit_dust_band": (
        "only when the position sits inside the dust band"
    ),
    "topology.09.001.state_transition.bot_attached": "a bot joins the wire topology",
    "topology.09.002.postcondition.wires_received": "one wire import",
    "swarm.11.001.postcondition.sim_run_registered": (
        "a sim run registers with the swarm view"
    ),
    "swarm.11.002.postcondition.paper_run_registered": (
        "a paper run registers with the swarm view"
    ),
    "trading.12.001.postcondition.tab_assembled": (
        "the window assembles its UI once per process"
    ),
    "trading.12.002.postcondition.exchange_tab_routed": "an exchange tab is added",
    "trading.12.003.postcondition.exchange_tabs_synced": "the settings dialog closes",
    "trading.12.004.postcondition.active_layer_alias": (
        "the operator switches the trading wing"
    ),
    "trading.12.005.postcondition.activity_log_paused": (
        "the operator presses the Activity Log pause button"
    ),
    "trading.12.006.postcondition.notification_relayed": (
        "the legacy notify stub relays a message"
    ),
    "trading.12.007.postcondition.trade_line_drawn_as_trade": (
        "only a message the Activity Log paints that names a trade"
    ),
    "charts.13.003.postcondition.timeframe_rearmed": (
        "the operator moves a panel's timeframe combo"
    ),
    "console.14.004.postcondition.pause_quiets_both_panes": (
        "the operator presses Pause"
    ),
    "console.14.005.postcondition.pause_buffer_delivered": (
        "the operator presses Resume"
    ),
    "exchange.15.001.postcondition.command_routed_to_chosen_table": (
        "the operator presses a bot command button"
    ),
    "exchange.15.004.postcondition.privacy_applied_to_every_field": (
        "the operator presses the global privacy button"
    ),
    "exchange.15.005.postcondition.privacy_button_matches_registry": "the same press",
    "apitest.16.001.postcondition.label_matches_session": (
        "one `clicked` connection; the tab owns no timer"
    ),
    "apitest.16.002.postcondition.session_released": (
        "one `clicked` connection; the tab owns no timer"
    ),
    "apitest.16.003.postcondition.reported_ok_ran_a_test": (
        "one `clicked` connection; the tab owns no timer"
    ),
    "apitest.16.004.postcondition.green_probe_read_a_body": (
        "one `clicked` connection; the tab owns no timer"
    ),
    "apitest.16.005.postcondition.indicator_is_mappable": (
        "one `clicked` connection; the tab owns no timer"
    ),
    "instance.17.001.postcondition.auto_start_permitted": (
        "one launch decision per process start"
    ),
    "charts.annotations.drawn": (
        "a paint pass writes it only when the annotation counts moved since the last "
        "pass"
    ),
    "charts.ata.rendered": "an ATA call from the Inspector is drawn on the chart",
    "charts.crosshair.shown": "the pointer is over the chart",
    "charts.indicator.toggled": "the operator switches one overlay on or off",
    "charts.theme.applied": (
        "a theme is applied to the chart, at build or on the operator's change"
    ),
    "charts.view.changed": "the operator pans, zooms or resets the chart window",
    "inspector.ata.candidate": (
        "a finished scan lands its calls on the push board, once per new entry"
    ),
    "inspector.ata.chime": "a hit or a confirmation sounds the chime",
    "inspector.ata.follow_up_read": (
        "the follow-up clock reads a watched call's candle when it is due; no hit, no "
        "timer, no read"
    ),
    "inspector.ata.handoff": "the operator presses Post on the push board",
    "inspector.ata.hit": "a scan's vote passes the judge",
    "inspector.ata.image_size": "a venue folder post writes its image",
    "inspector.ata.market_read": "one market's candles are read inside a scan",
    "inspector.ata.scan_finished": "a scan the operator pressed ends",
    "inspector.ata.scan_pressed": "the operator presses Scan Now or Scan All",
    "inspector.ata.scan_started": "the scan thread starts after that press",
    "inspector.ata.sent": "an API post is sent to a venue",
    "inspector.ata.ticker_resolved": (
        "a Scan press with text in the ticker field resolves that text"
    ),
    "inspector.ata.volume_order": "a scan orders one asset class's markets by volume",
    "inspector.scan.list_source": "the same order; the class's market list is read",
    "inspector.scan.progress": (
        "a running scan reports every `PROGRESS_PIN_EVERY` markets read"
    ),
    "sim.backtest.bot_walked": "one bot's walk ends inside a run the operator started",
    "sim.battery.portfolio_finished": "a Portfolio Battery run ends",
    "sim.battery.portfolio_started": "a Portfolio Battery run starts",
    "sim.bot.htf_bias": (
        "a tick inside a run the operator started, on the run's own routed sink; "
        "between runs the loop does not exist"
    ),
    "sim.bot.stats_written": "a snapshot inside the same run, on the same routed sink",
    "sim.fleet.clear_pressed": "the operator presses Clear Fleet",
    "sim.fleet.cleared": "the same press, after the fleet is cleared",
    "sim.fleet.mode_shown": "the operator picks a sim mode, or the tab builds",
    "sim.layer.flipped": "the operator presses the flip button",
    "sim.replay.marks_drawn": (
        "the replay draws at build, on a fleet change, a flip, a chooser change, a "
        "bot selection or a retrieval"
    ),
    "sim.run.start_pressed": "the operator presses Start Run",
    "sim.sink.routed": "a run's sink is unrouted at the run's end, once per run",
    "sim.tablet.refused": "a tablet retrieval inside a battery run is refused",
    "sim.tablet.retrieved": "a tablet retrieval inside a battery run lands",
}
"""The seventy-two pins that need a trigger. Silence from one is normal. Each
value is the reason, read at the call site.
"""

# Overtaken: "The seventy-two pins that need a trigger." `_TOGGLE_PINS` holds 73.

CADENCE_BY_NAME = MappingProxyType(
    {
        **{pin: CADENCE_ALWAYS_ON for pin in _ALWAYS_ON_PINS},
        **{pin: CADENCE_TOGGLE for pin in _TOGGLE_PINS},
    }
)
"""Every pin's declared category, by current name. 87 entries."""

# Overtaken: "87 entries." `CADENCE_BY_NAME` holds 89, and held 88 before this pin.

_NAME_TEMPLATE = "{}"
"""How a templated pin name is written; the trailing `{}` stands for a leaf built at run
time.
"""


def _template_matches(pattern: str, name: str) -> bool:
    """Return whether `name` matches templated `pattern`.

    Requires exactly one `{}` in `pattern`, and a non-empty leaf.
    """
    if pattern.count(_NAME_TEMPLATE) != 1:
        return False
    head, _, tail = pattern.partition(_NAME_TEMPLATE)
    return (
        name.startswith(head)
        and name.endswith(tail)
        and len(name) > len(head) + len(tail)
    )


def cadence_of(name: str) -> Optional[str]:
    """Return this pin's declared cadence category, or None when undeclared."""
    got = CADENCE_BY_NAME.get(name)
    if got is not None:
        return got
    for pattern, category in CADENCE_BY_NAME.items():
        if _template_matches(pattern, name):
            return category
    return None


def always_on_stale_after(throttle: float = 0.0) -> float:
    """Return the stale budget for an always-on pin, in seconds.

    `throttle` is the pin's declared `every=` window, or 0.0 for none.
    """
    if throttle and throttle > 0.0:
        return max(ALWAYS_ON_STALE_AFTER, ALWAYS_ON_SLACK * float(throttle))
    return ALWAYS_ON_STALE_AFTER


def cadence_verdict(
    declared: Optional[str],
    age: Optional[float],
    n: int,
    mean_interval: Optional[float],
    stale_after: float,
) -> str:
    """Return a cadence verdict from `declared`, `age`, `n` and `mean_interval`.

    A `toggle` always returns `CADENCE_NOT_APPLICABLE` unless it is
    emitting at loop rate; see `CADENCE_TOGGLE_AT_LOOP_RATE`.
    """
    if declared is None:
        return CADENCE_UNDECLARED
    if declared == CADENCE_TOGGLE:
        if (
            n >= MISCATEGORY_MIN_SAMPLES
            and mean_interval is not None
            and mean_interval <= MISCATEGORY_MEAN_INTERVAL
        ):
            return CADENCE_TOGGLE_AT_LOOP_RATE
        return CADENCE_NOT_APPLICABLE
    if n <= 0 or age is None:
        return CADENCE_NEVER_FIRED
    return CADENCE_STALE if age > stale_after else CADENCE_ON_TIME


def _mean_interval(
    first_mono: Optional[float], last_mono: float, count: int
) -> Optional[float]:
    """Return the mean seconds between emissions, else None if under two occurred."""
    if first_mono is None or count < 2:
        return None
    return (last_mono - first_mono) / (count - 1)


def _cadence_row(
    name: str,
    site: str,
    snapshot: tuple,
    aux: tuple,
    now: float,
    stale_after: Optional[float],
) -> dict:
    """Build one cadence row: category, predicted band, observed values, verdict."""
    last_mono, count, last_ts, last_dt = snapshot
    first_mono, throttle = aux
    declared = cadence_of(name)
    budget = (
        always_on_stale_after(throttle) if stale_after is None else float(stale_after)
    )
    mean = _mean_interval(first_mono, last_mono, count)
    age = now - last_mono
    return {
        "name": name,
        "site": site,
        "declared": declared,
        "predicted": {
            "max_interval": budget if declared == CADENCE_ALWAYS_ON else None,
            "min_mean_interval": (
                MISCATEGORY_MEAN_INTERVAL if declared == CADENCE_TOGGLE else None
            ),
        },
        "observed": {
            "age": age,
            "n": count,
            "mean_interval": mean,
            "throttle": throttle,
            "last_ts": last_ts,
            "last_dt": last_dt,
        },
        "verdict": cadence_verdict(declared, age, count, mean, budget),
    }


def _never_fired_rows(seen_names: set) -> dict:
    """Return a row for every always-on pin absent from `seen_names`."""
    rows: dict = {}
    for pin, category in CADENCE_BY_NAME.items():
        if category != CADENCE_ALWAYS_ON or pin in seen_names:
            continue
        if _NAME_TEMPLATE in pin:
            continue
        rows[(pin, "")] = {
            "name": pin,
            "site": "",
            "declared": category,
            "predicted": {
                "max_interval": ALWAYS_ON_STALE_AFTER,
                "min_mean_interval": None,
            },
            "observed": {
                "age": None,
                "n": 0,
                "mean_interval": None,
                "throttle": 0.0,
                "last_ts": None,
                "last_dt": None,
            },
            "verdict": CADENCE_NEVER_FIRED,
        }
    return rows


SUBSYSTEM_SEPARATOR = "."
"""The character that ends the subsystem part of an emitter name."""

ENGINE_GROUP = "Engine"
"""The group a subsystem's emitters fall under when they serve no tab of their own."""

TAB_BY_SUBSYSTEM = MappingProxyType(
    {
        "apitest": ENGINE_GROUP,
        "bot": ENGINE_GROUP,
        "charts": "Charts",
        "console": "Console",
        "exchange": "Live",
        "extractor": ENGINE_GROUP,
        "fleet": "Sim",
        "gui": ENGINE_GROUP,
        "history": "History",
        "inspector": "Inspector",
        "instance": ENGINE_GROUP,
        "sim": "Sim",
        "status": "Status",
        "swarm": "Swarm",
        "ta": ENGINE_GROUP,
        "tick": ENGINE_GROUP,
        "topology": ENGINE_GROUP,
        "trading": "Live",
        "ytd": ENGINE_GROUP,
    }
)
"""The tab each subsystem prefix serves, by the tab's bar label. Every prefix
`CADENCE_BY_NAME` declares is named here; a prefix it does not name reads as
`ENGINE_GROUP` in `tab_of` until it is placed.
"""

HEALTH_GREEN = "green"
"""No retained record of this subsystem failed and every always-on emitter it declares
fired.
"""

HEALTH_YELLOW = "yellow"
"""A retained record of this subsystem failed, or an always-on emitter it declares never
fired.
"""

HEALTH_RED = "red"
"""Never returned, because no emitter declares an expected rhythm and silence cannot be
told from idleness.
"""

HEALTH_STATES = (HEALTH_GREEN, HEALTH_YELLOW)
"""The states `subsystem_health` returns; `HEALTH_RED` is not one of them."""


def subsystem_of(name: str) -> str:
    """Return the subsystem `name` belongs to, the part before its first dot."""
    return name.split(SUBSYSTEM_SEPARATOR, 1)[0]


def tab_of(subsystem: str) -> str:
    """Return the tab `subsystem`'s emitters serve, or `ENGINE_GROUP` when none does."""
    return TAB_BY_SUBSYSTEM.get(subsystem, ENGINE_GROUP)


def declared_subsystems() -> tuple:
    """Every subsystem `CADENCE_BY_NAME` declares an emitter for, in name order."""
    return tuple(sorted({subsystem_of(emitter) for emitter in CADENCE_BY_NAME}))


def declared_emitter_for(name: str) -> Optional[str]:
    """Return the declared emitter `name` is, exactly or as a template leaf, else None."""
    if name in CADENCE_BY_NAME:
        return name
    for pattern in CADENCE_BY_NAME:
        if _template_matches(pattern, name):
            return pattern
    return None


def _emitted_by_name(sink: "SignalSink") -> dict:
    """Return `{emitter name: emissions this run}`, counted across the name's sites."""
    counts: dict = {}
    for (name, _site), row in sink.timing().items():
        counts[name] = counts.get(name, 0) + int(row["n"])
    return counts


def _retained_by_name(sink: "SignalSink") -> dict:
    """Return `{emitter name: {failed, latest}}` over the records still in memory."""
    out: dict = {}
    for record in sink.records():
        row = out.setdefault(record.name, {"failed": 0, "latest": None})
        if record.ok is False:
            row["failed"] += 1
        row["latest"] = render(record.actual)
    return out


def _blank_emitter(name: str, cadence: str) -> dict:
    """Return one emitter read-out with no activity recorded against it yet."""
    return {
        "name": name,
        "cadence": cadence,
        "emitted": 0,
        "failed": 0,
        "latest": None,
    }


def _emitter_rows(emitted: dict, retained: dict) -> dict:
    """Return `{(subsystem, emitter): read-out}` for every declared and emitted name."""
    rows: dict = {
        (subsystem_of(emitter), emitter): _blank_emitter(emitter, cadence)
        for emitter, cadence in CADENCE_BY_NAME.items()
    }
    for name, count in emitted.items():
        emitter = declared_emitter_for(name)
        key = (subsystem_of(name), emitter or name)
        row = rows.setdefault(key, _blank_emitter(name, CADENCE_UNDECLARED))
        row["emitted"] += count
    for name, seen in retained.items():
        emitter = declared_emitter_for(name)
        key = (subsystem_of(name), emitter or name)
        row = rows.setdefault(key, _blank_emitter(name, CADENCE_UNDECLARED))
        row["failed"] += seen["failed"]
        row["latest"] = seen["latest"]
    return rows


def _blank_subsystem(subsystem: str) -> dict:
    """Return one subsystem's read-out with no emitter counted into it yet."""
    return {
        "subsystem": subsystem,
        "health": None,
        "emitters_declared": 0,
        "emitters_fired": 0,
        "emitters_silent": 0,
        "always_on_declared": 0,
        "always_on_silent": 0,
        "toggle_declared": 0,
        "toggle_silent": 0,
        "undeclared": 0,
        "emitted": 0,
        "failed": 0,
        "emitters": [],
    }


def _count_emitter(bucket: dict, row: dict) -> None:
    """Add one emitter read-out to its subsystem's counters."""
    bucket["emitters"].append(row)
    bucket["emitted"] += row["emitted"]
    bucket["failed"] += row["failed"]
    if row["cadence"] == CADENCE_UNDECLARED:
        bucket["undeclared"] += 1
        return
    bucket["emitters_declared"] += 1
    silent = row["emitted"] == 0
    bucket["emitters_silent" if silent else "emitters_fired"] += 1
    always_on = row["cadence"] == CADENCE_ALWAYS_ON
    bucket["always_on_declared" if always_on else "toggle_declared"] += 1
    if silent:
        bucket["always_on_silent" if always_on else "toggle_silent"] += 1


def subsystem_health(sink: Optional["SignalSink"]) -> dict:
    """Return one health read-out per subsystem, from `CADENCE_BY_NAME` and `sink`.

    `emitted` counts every emission this run; `failed` and `latest` read only
    the records still in memory. `health` is None for a subsystem that
    recorded nothing. A None `sink` returns the declared emitters with every
    count at zero.
    """
    emitted = {} if sink is None else _emitted_by_name(sink)
    retained = {} if sink is None else _retained_by_name(sink)
    rows: dict = {}
    for (subsystem, _emitter), row in sorted(_emitter_rows(emitted, retained).items()):
        _count_emitter(rows.setdefault(subsystem, _blank_subsystem(subsystem)), row)
    for bucket in rows.values():
        if bucket["failed"] or bucket["always_on_silent"]:
            bucket["health"] = HEALTH_YELLOW
        elif bucket["emitted"]:
            bucket["health"] = HEALTH_GREEN
    return rows


def _utc_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(
        ts if ts is not None else time.time(), tz=timezone.utc
    ).isoformat()


def _json_default(o: Any) -> Any:
    """Frozen containers are not JSON types; unwrap them for the file."""
    if isinstance(o, MappingProxyType):
        return dict(o)
    if isinstance(o, (frozenset, set)):
        return sorted(o, key=repr)
    return repr(o)


def freeze(value: Any) -> Any:
    """Return an immutable, recursive snapshot of `value`.

    A dict becomes a read-only view; a list or tuple becomes a tuple;
    a set or frozenset becomes a frozenset. Other values pass through
    unchanged.
    """
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze(v) for v in value)
    return value


def render(value: Any) -> str:
    """Return a human-readable form of a value `freeze()` produced."""
    if isinstance(value, MappingProxyType):
        inner = ", ".join(f"{k!r}: {render(v)}" for k, v in value.items())
        return "{" + inner + "}"
    if isinstance(value, tuple):
        return "[" + ", ".join(render(v) for v in value) + "]"
    if isinstance(value, frozenset):
        return "{" + ", ".join(render(v) for v in sorted(value, key=repr)) + "}"
    return repr(value)


def _caller_site(depth: int = 2) -> str:
    """Return `file:line` of the calling frame at the given stack `depth`."""
    try:
        f = sys._getframe(depth)
        return f"{Path(f.f_code.co_filename).name}:{f.f_lineno}"
    except Exception:  # noqa: BLE001 - location is best-effort
        return "?"


def _caller_module(depth: int = 2) -> str:
    """Return the calling frame's module name at stack `depth`."""
    try:
        f = sys._getframe(depth)
        mod = f.f_globals.get("__name__")
        if mod:
            return str(mod)
        return Path(f.f_code.co_filename).stem
    except Exception:  # noqa: BLE001 - best-effort
        return "?"


NAME_COLUMN = 53
"""Width of the padded name column in `Signal.message`; names longer than this are never
truncated.
"""


@dataclass(frozen=True)
class Signal:
    """One observation, with the expectation it was judged against.

    Frozen; retrieval returns tuples of these so a caller cannot mutate
    what was captured. `expected` is None for a bare observation; `ok`
    is the verdict, None when nothing was judged. `actual` is always
    recorded. `site` and `module` are auto-captured from the caller's
    frame. `kind` is `"check"` when judged against an expectation,
    `"sample"` otherwise. `count` is how many observations this record
    stands for when a throttle has folded several into one line. `dt`
    is the interval since the previous emission of this `(name, site)`,
    None when none was measured. `nth` is the 1-based ordinal of this
    emission for its identity, 0 when never measured. `duration` is how
    long the observed operation took, supplied by the caller; None when
    not measured, never 0.0 for "not measured". `cadence`, `budget_s`
    and `tab` are stamped by `SignalSink.emit` from `cadence_of`,
    `always_on_stale_after` and `tab_of`, so a record can be judged
    without the register that wrote it; `cadence` and `tab` are None for
    a name the register does not declare, and `budget_s` is None for
    every pin that is not always-on.
    """

    name: str
    site: str
    actual: Any
    expected: Any = None
    ok: Optional[bool] = None
    seq: int = 0
    ts: str = ""
    context: Optional[dict] = None
    module: str = ""
    kind: str = "check"
    count: int = 1
    dt: Optional[float] = None
    nth: int = 0
    duration: Optional[float] = None
    cadence: Optional[str] = None
    budget_s: Optional[float] = None
    tab: Optional[str] = None

    def to_json(self, extra: Optional[dict] = None) -> str:
        """Return this record as a JSON line.

        `extra` appends fields after the declared ones; it cannot
        overwrite them.
        """
        payload = {
            "ts": self.ts,
            "seq": self.seq,
            "module": self.module,
            "name": self.name,
            "subsystem": subsystem_of(self.name),
            "kind": self.kind,
            "ok": self.ok,
            "expected": self.expected,
            "actual": self.actual,
            "count": self.count,
            "dt": self.dt,
            "nth": self.nth,
            "duration": self.duration,
            "site": self.site,
            "context": self.context or {},
            "cadence": self.cadence,
            "budget_s": self.budget_s,
            "tab": self.tab,
        }
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=_json_default, separators=(",", ":"))

    def message(self) -> str:
        """Return the operator-facing text line for this record.

        Columns: `HH:MM:SS  module  name  VERDICT  detail`, name padded
        to `NAME_COLUMN` and never truncated. `VERDICT` is `PASS`,
        `FAIL`, or `----` for an unjudged sample. A `FAIL` line carries
        `expected` and `actual`; a `sample` line carries `actual` alone.
        """
        t = (self.ts or "")[11:19] or "--:--:--"
        mod = (self.module or "?").rsplit(".", 1)[-1][:18]
        verdict = "----" if self.ok is None else ("PASS" if self.ok else "FAIL")
        parts = [f"{t}  {mod:<18} {self.name:<{NAME_COLUMN}} {verdict}"]
        if self.ok is False:
            parts.append(
                f" expected={render(self.expected)}" f" actual={render(self.actual)}"
            )
        elif self.kind == "sample":
            parts.append(f" {render(self.actual)}")
        if self.count > 1:
            parts.append(f" x{self.count}")
        if self.context:
            inner = " ".join(f"{k}={render(v)}" for k, v in self.context.items())
            parts.append(f"  [{inner}]")
        return "".join(parts)


def _as_float(value: Any) -> Optional[float]:
    """Return `value` as a float when it is exactly `int` or `float`, else None."""
    if type(value) is float:
        return value
    if type(value) is int:
        if not -sys.float_info.max <= value <= sys.float_info.max:
            return None
        return float(value)
    return None


def _as_ordinal(value: Any) -> int:
    """Return `value` as a positive int when it is exactly `int` and > 0, else 0."""
    if type(value) is int and value > 0:
        return value
    return 0


def _as_cadence(value: Any) -> Optional[str]:
    """Return `value` when it is one of `CADENCE_CATEGORIES`, else None."""
    if type(value) is str and value in CADENCE_CATEGORIES:
        return value
    return None


def _as_budget(value: Any) -> Optional[float]:
    """Return `value` as a finite float above 0.0, else None."""
    got = _as_float(value)
    if got is None or not math.isfinite(got) or got <= 0.0:
        return None
    return got


def _as_tab(value: Any) -> Optional[str]:
    """Return `value` when it is a non-empty string, else None."""
    if type(value) is str and value:
        return value
    return None


def _as_measured_duration(value: Any) -> Optional[float]:
    """Return `value` as a rounded, non-negative, finite float, or None."""
    if value is None:
        return None
    if type(value) is int:
        # Comparing avoids the `OverflowError` `float()` raises on a very large int.
        if not -sys.float_info.max <= value <= sys.float_info.max:
            return None
        value = float(value)
    if type(value) is not float:
        return None
    if not math.isfinite(value):
        return None
    if value < 0.0:
        return None
    return round(value, 7)


def _classify(
    name: str,
    site: str,
    now: float,
    snapshot: Optional[tuple],
    fresh_within: float,
    stale_after: float,
) -> dict:
    """Return one of the four `PIN_STATES` for this identity's timing view.

    `snapshot` is None when the identity has never been seen.
    `stale_after` is raised to `fresh_within` when passed smaller, so
    the fresh band is never unreachable.
    """
    if snapshot is None:
        return {
            "name": name,
            "site": site,
            "state": PIN_NEVER,
            "age": None,
            "n": 0,
            "last_ts": None,
            "last_dt": None,
        }
    last_mono, count, last_ts, last_dt = snapshot
    age = now - last_mono
    limit = max(float(stale_after), float(fresh_within))
    if age <= float(fresh_within):
        state = PIN_FRESH
    elif age <= limit:
        state = PIN_CURRENT
    else:
        state = PIN_STALE
    return {
        "name": name,
        "site": site,
        "state": state,
        "age": age,
        "n": count,
        "last_ts": last_ts,
        "last_dt": last_dt,
    }


class SignalSink:
    """Buffered, append-only, thread-safe sink for `Signal` records.

    Holds a bounded in-memory window of records plus a bounded
    last-seen map by identity, flushes to a rotating JSONL file, and
    answers timing and cadence queries about pins that stopped emitting.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        flush_every: int = DEFAULT_FLUSH_EVERY,
        enabled: bool = True,
        max_bytes: int = MAX_FILE_BYTES,
        backup_count: int = FILE_BACKUP_COUNT,
        retain_rows: int = RETAIN_ROWS,
        max_identities: int = MAX_IDENTITIES,
        digest_interval: float = DIGEST_MIN_INTERVAL,
        digest_max_bytes: int = DIGEST_FILE_BYTES,
        digest_backup_count: int = DIGEST_BACKUP_COUNT,
    ) -> None:
        self.path = path
        self.flush_every = max(1, int(flush_every))
        self.enabled = enabled
        # `max_bytes <= 0` disables rotation; `backup_count` is clamped to at least one.
        self._max_bytes = max(0, int(max_bytes))
        self._backup_count = max(1, int(backup_count))
        # `retain_rows` is clamped to at least one.
        self._retain = max(1, int(retain_rows))
        # `_buf` and `_all` are bounded deques, so memory is capped regardless of
        # session length.
        self._buf: deque = deque(maxlen=self._retain)
        self._all: deque = deque(maxlen=self._retain)
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        # `_seen` maps (name, site) to [last_monotonic, count, last_ts, last_dt].
        self._seen: dict = {}
        # `_cadence` maps identity to [first_monotonic, throttle], set beside `_seen`.
        self._cadence: dict = {}
        # `_declared` maps a name to (cadence, tab); both are fixed for a name, so the
        # register is walked once per name instead of once per record.
        self._declared: dict = {}
        self._max_identities = max(1, int(max_identities))
        self._identity_overflow = 0
        self._seq = 0
        self._dropped = 0
        self._evicted = 0
        self._rotate_failures = 0
        # Counts a `duration` `emit` refused; see `_as_measured_duration`.
        self._duration_rejected = 0
        # `digest_interval <= 0` disables the digest ladder entirely.
        self._digest_interval = max(0.0, float(digest_interval))
        self._digest_max_bytes = max(0, int(digest_max_bytes))
        self._digest_backup_count = max(1, int(digest_backup_count))
        # `_digest_since` maps identity to seconds accumulated since its last admitted
        # digest line.
        self._digest_since: dict = {}
        # `_digest_pending` maps identity to observations folded since its last admitted
        # line.
        self._digest_pending: dict = {}
        self._digest_admitted = 0
        self._digest_folded = 0
        self._digest_dropped = 0
        self._digest_rotate_failures = 0
        self._digest_identity_overflow = 0

    def _declared_for(self, name: str) -> tuple:
        """Return `(cadence, tab)` for `name`, from `cadence_of` and `tab_of`.

        Caches the pair per name up to `_max_identities`; past that the
        register is read on every emit rather than remembered.
        """
        got = self._declared.get(name)
        if got is not None:
            return got
        pair = (cadence_of(name), tab_of(subsystem_of(name)))
        if len(self._declared) < self._max_identities:
            self._declared[name] = pair
        return pair

    def emit(
        self,
        name: str,
        actual: Any,
        expected: Any = None,
        ok: Optional[bool] = None,
        context: Optional[dict] = None,
        site: Optional[str] = None,
        module: Optional[str] = None,
        count: int = 1,
        duration: Optional[float] = None,
        every: float = 0.0,
    ) -> Optional[Signal]:
        """Record one observation; never raises, never blocks on I/O.

        Returns None when the sink is disabled. `ok` is derived by
        equality when `expected` is given and no verdict is supplied.
        """
        if not self.enabled:
            return None
        try:
            if ok is None and expected is not None:
                ok = bool(actual == expected)
            # `site` and `module` are read from the stack before the lock is taken.
            _name = str(name)
            _site = site or _caller_site(2)
            _mod = module or _caller_module(2)
            # `_as_measured_duration` runs before the lock; it is a pure function of
            # `duration`.
            _dur = _as_measured_duration(duration)
            _dur_refused = duration is not None and _dur is None
            with self._lock:
                self._seq += 1
                if _dur_refused:
                    self._duration_rejected += 1
                # `_now` (monotonic) and `_ts` (wall clock) are read one line apart,
                # inside the lock.
                _now = time.monotonic()
                _ts = _utc_iso()
                _prev = self._seen.get((_name, _site))
                # The identity's widest `every=` window, which sets an always-on
                # pin's budget; an untracked identity falls back to this call's own.
                _window = float(every or 0.0)
                if _prev is None:
                    # First emission of this identity: `dt` stays None, nothing to
                    # compare.
                    _dt = None
                    _nth = 1
                    if len(self._seen) < self._max_identities:
                        self._seen[(_name, _site)] = [_now, 1, _ts, None]
                        self._cadence[(_name, _site)] = [_now, float(every or 0.0)]
                    else:
                        # Past `MAX_IDENTITIES`, the record is kept but `nth=0`: not
                        # timed.
                        _nth = 0
                        self._identity_overflow += 1
                else:
                    # `_dt` rounds to 1e-07, the clock's own resolution; a sub-
                    # resolution gap rounds to 0.0.
                    _dt = round(_now - _prev[0], 7)
                    _nth = _prev[1] + 1
                    _prev[0] = _now
                    _prev[1] = _nth
                    _prev[2] = _ts
                    _prev[3] = _dt
                    # The widest `every=` window across call sites sharing an identity
                    # sets its budget.
                    _aux = self._cadence.get((_name, _site))
                    if _aux is not None:
                        if _window > _aux[1]:
                            _aux[1] = _window
                        _window = _aux[1]
                _cadence, _tab = self._declared_for(_name)
                sig = Signal(
                    name=_name,
                    site=_site,
                    module=_mod,
                    actual=freeze(actual),
                    expected=freeze(expected),
                    ok=ok,
                    kind=("sample" if expected is None and ok is None else "check"),
                    count=int(count) if count else 1,
                    seq=self._seq,
                    ts=_ts,
                    dt=_dt,
                    nth=_nth,
                    duration=_dur,
                    context=freeze(context) if context else None,
                    cadence=_cadence,
                    budget_s=(
                        always_on_stale_after(_window)
                        if _cadence == CADENCE_ALWAYS_ON
                        else None
                    ),
                    tab=_tab,
                )
                # `_evicted` (from `_all`) is not a loss, already on disk; `_dropped`
                # (from `_buf`) is.
                if len(self._all) == self._retain:
                    self._evicted += 1
                if len(self._buf) == self._retain:
                    self._dropped += 1
                self._buf.append(sig)
                self._all.append(sig)
                due = len(self._buf) >= self.flush_every
            if due:
                self.flush()
            return sig
        except Exception:  # noqa: BLE001 - instrumentation must never break the app
            return None

    def _rotate_if_needed(self) -> None:
        """Roll the sink's file to `<name>.1` once it reaches `max_bytes`.

        Called with `_io_lock` held, so a rename cannot interleave with
        another thread's append.
        """
        self._roll(self.path, self._max_bytes, self._backup_count)

    @staticmethod
    def _roll(path: Optional[Path], max_bytes: int, backup_count: int) -> None:
        """Shift one file ladder by one place if it has reached `max_bytes`.

        Uses `Path.replace`, which succeeds on Windows even when the
        destination already exists.
        """
        if path is None or max_bytes <= 0:
            return
        if not path.is_file():
            return
        if path.stat().st_size < max_bytes:
            return
        for i in range(backup_count - 1, 0, -1):
            src = path.parent / f"{path.name}.{i}"
            dst = path.parent / f"{path.name}.{i + 1}"
            if src.exists():
                src.replace(dst)
        path.replace(path.parent / f"{path.name}.1")

    @property
    def digest_path(self) -> Optional[Path]:
        """Return the digest ladder's path beside the main file, or None.

        `session.jsonl` becomes `session.digest.jsonl`.
        """
        if self.path is None:
            return None
        p = self.path
        return p.with_name(f"{p.stem}.digest{p.suffix}")

    def _digest_rows(self, rows: Iterable[Signal]) -> list:
        """Return `(record, folded)` pairs: the digest ladder's share of `rows`.

        A record is admitted at most once per `DIGEST_MIN_INTERVAL`
        seconds per identity; suppressed records are folded into the
        next admitted line's `folded` count.
        """
        if self._digest_interval <= 0.0:
            return []
        out = []
        for r in rows:
            key = (r.name, r.site)
            prev = self._digest_since.get(key)
            if prev is None:
                # Past `MAX_IDENTITIES`, a new identity is still admitted but no entry
                # is kept.
                if len(self._digest_since) < self._max_identities:
                    self._digest_since[key] = 0.0
                else:
                    self._digest_identity_overflow += 1
                out.append((r, self._digest_pending.pop(key, 0) + 1))
                self._digest_admitted += 1
                continue
            since = prev + (r.dt or 0.0)
            if since < self._digest_interval:
                self._digest_since[key] = since
                self._digest_pending[key] = self._digest_pending.get(key, 0) + 1
                self._digest_folded += 1
                continue
            self._digest_since[key] = 0.0
            out.append((r, self._digest_pending.pop(key, 0) + 1))
            self._digest_admitted += 1
        return out

    def _write_digest(self, rows: Iterable[Signal]) -> None:
        """Append the digest ladder's admitted lines for `rows`.

        Called with `_io_lock` held. Writes nothing when nothing was
        admitted.
        """
        admitted = self._digest_rows(rows)
        if not admitted:
            return
        target = self.digest_path
        if target is None:
            return
        try:
            self._roll(target, self._digest_max_bytes, self._digest_backup_count)
        except OSError:
            self._digest_rotate_failures += 1
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8", errors="replace") as fh:
                for r, folded in admitted:
                    fh.write(r.to_json({"folded": folded}) + "\n")
        except OSError:
            self._digest_dropped += len(admitted)

    def flush(self) -> None:
        """Append the buffered records to disk; append-only, never rewrites.

        Returns without draining the buffer when `path` is None, so
        records survive until a run directory is assigned.
        """
        if self.path is None:
            return
        with self._lock:
            rows, self._buf = self._buf, deque(maxlen=self._retain)
        if not rows:
            return
        with self._io_lock:
            try:
                self._rotate_if_needed()
            except OSError:
                # `rotate_failures` surfaces a rotation that could not run.
                self._rotate_failures += 1
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", errors="replace") as fh:
                    for r in rows:
                        fh.write(r.to_json() + "\n")
            except OSError:
                # `_dropped` counts records that could not be written.
                self._dropped += len(rows)
            # The digest is written after the main file, inside the same `_io_lock`.
            self._write_digest(rows)

    # Returns tuples of frozen records; a caller cannot mutate what was captured.

    def records(self, name: Optional[str] = None) -> tuple:
        """Every record still retained in memory, newest last.

        Older records were evicted from memory but remain on disk; see
        `health()['evicted']`.
        """
        with self._lock:
            rows = tuple(self._all)
        if name is None:
            return rows
        return tuple(r for r in rows if r.name == name)

    def since(self, seq: int) -> tuple:
        """Records with `seq` greater than the given watermark, newest last.

        Walks backward from the newest record and stops at the first
        `seq` at or below the watermark, since `seq` increases
        monotonically under `_lock`.
        """
        with self._lock:
            newest_first = []
            for record in reversed(self._all):
                if record.seq <= seq:
                    break
                newest_first.append(record)
        newest_first.reverse()
        return tuple(newest_first)

    def count(self, name: Optional[str] = None) -> int:
        return len(self.records(name))

    def violations(self) -> tuple:
        return tuple(r for r in self.records() if r.ok is False)

    def names(self) -> tuple:
        return tuple(sorted({r.name for r in self.records()}))

    def by_subsystem(self, subsystem: Optional[str] = None) -> dict:
        """Return records grouped by subsystem, the part of `name` before the first dot.

        Pass `subsystem` to return only that bucket.
        """
        buckets: dict = {}
        for r in self.records():
            sub = subsystem_of(r.name)
            if subsystem is not None and sub != subsystem:
                continue
            buckets.setdefault(sub, []).append(r)
        return {k: tuple(v) for k, v in buckets.items()}

    def stats(self) -> dict:
        """Per-signal totals. The shape an operator or an audit reads."""
        out: dict = {}
        for r in self.records():
            s = out.setdefault(
                r.name, {"n": 0, "ok": 0, "bad": 0, "unjudged": 0, "site": r.site}
            )
            s["n"] += 1
            if r.ok is True:
                s["ok"] += 1
            elif r.ok is False:
                s["bad"] += 1
            else:
                s["unjudged"] += 1
        return out

    # These three answer questions about a pin that stopped, without waiting for a
    # record.

    def identities(self) -> tuple:
        """Every `(name, site)` identity this sink has recorded, sorted."""
        with self._lock:
            return tuple(sorted(self._seen))

    def pin_state(
        self,
        name: str,
        site: str,
        fresh_within: float = FRESH_WITHIN,
        stale_after: float = STALE_AFTER,
    ) -> dict:
        """Return one identity's current timing state, without waiting for a new record.

        Returns `{name, site, state, age, n, last_ts, last_dt}`. `state`
        is one of `PIN_STATES`; `age` and `last_dt` are None only for
        `PIN_NEVER`.
        """
        # `now` is read inside the lock so `age` cannot go negative against a concurrent
        # `emit`.
        with self._lock:
            prev = self._seen.get((name, site))
            snapshot = None if prev is None else tuple(prev)
            now = time.monotonic()
        return _classify(name, site, now, snapshot, fresh_within, stale_after)

    def timing(
        self,
        name: Optional[str] = None,
        fresh_within: float = FRESH_WITHIN,
        stale_after: float = STALE_AFTER,
    ) -> dict:
        """`{(name, site): pin_state}` for every identity seen so far.

        Pass `name` to restrict to that name's identities. Never reports
        `PIN_NEVER`: an identity that never emitted is absent from the map.
        """
        # One clock reading, inside the lock, ages every row against the same instant.
        with self._lock:
            snap = {
                key: tuple(value)
                for key, value in self._seen.items()
                if name is None or key[0] == name
            }
            now = time.monotonic()
        return {
            key: _classify(key[0], key[1], now, value, fresh_within, stale_after)
            for key, value in snap.items()
        }

    def cadence_report(
        self, stale_after: Optional[float] = None, *, include_never: bool = True
    ) -> dict:
        """`{(name, site): row}`: each pin's declared cadence verdict.

        A `toggle` returns `CADENCE_NOT_APPLICABLE` unless it is emitting
        at loop rate. `stale_after` overrides the per-pin budget when
        given. `include_never` adds a row for every recorded always-on
        pin this sink has no record of.
        """
        # One clock reading, inside the lock, for the whole report; see `pin_state`.
        with self._lock:
            snap = {
                key: (tuple(value), tuple(self._cadence.get(key, (None, 0.0))))
                for key, value in self._seen.items()
            }
            now = time.monotonic()
        rows = {
            key: _cadence_row(key[0], key[1], value, aux, now, stale_after)
            for key, (value, aux) in snap.items()
        }
        if include_never:
            rows.update(_never_fired_rows({name for name, _ in snap}))
        return rows

    def health(self) -> dict:
        """Sink integrity counters, so a partial record set is visible.

        `retained` and `evicted` describe the in-memory window;
        `dropped` counts records that never reached disk.
        """
        return {
            "emitted": self._seq,
            "buffered": len(self._buf),
            "retained": len(self._all),
            "evicted": self._evicted,
            "dropped": self._dropped,
            # `rotate_failures`: a rotation that could not run; nothing was lost.
            "rotate_failures": self._rotate_failures,
            # `duration_rejected`: a `duration` `emit` refused; the record itself was
            # kept.
            "duration_rejected": self._duration_rejected,
            # `identities`: the last-seen map's current size.
            "identities": len(self._seen),
            "identity_overflow": self._identity_overflow,
            "path": str(self.path) if self.path else None,
            # `digest_folded` counts records the digest thinned; each survives verbatim
            # on the main file.
            "digest_admitted": self._digest_admitted,
            "digest_folded": self._digest_folded,
            "digest_dropped": self._digest_dropped,
            "digest_rotate_failures": self._digest_rotate_failures,
            "digest_identity_overflow": self._digest_identity_overflow,
            "digest_interval": self._digest_interval,
            "digest_path": (str(self.digest_path) if self.digest_path else None),
        }


_ACTIVE: Optional[SignalSink] = None
_ACTIVE_LOCK = threading.Lock()

# `_ROUTES` maps a thread ident to the sink that thread's emits reach instead of
# `_ACTIVE`; empty until a thread calls `route_thread`.
_ROUTES: dict = {}
_ROUTES_LOCK = threading.Lock()


_THROTTLE_LOCK = threading.Lock()
_THROTTLE: dict = {}


def _throttle_admit(name: str, site: str, every: float, instance: Optional[str] = None):
    """Admit this observation, or fold it into the next one.

    Returns the count of observations the admitted record stands for,
    or None when suppressed. Keyed by `(name, site, instance)`; two
    live objects sharing one call site must declare distinct `instance`
    values to be counted separately.
    """
    now = time.monotonic()
    with _THROTTLE_LOCK:
        key = (name, site, None if instance is None else str(instance))
        last, pending = _THROTTLE.get(key, (None, 0))
        if last is not None and (now - last) < every:
            _THROTTLE[key] = (last, pending + 1)
            return None
        _THROTTLE[key] = (now, 0)
        return pending + 1


def reset_throttle() -> None:
    """Forget every rate-limit window. For tests and run boundaries."""
    with _THROTTLE_LOCK:
        _THROTTLE.clear()


def set_sink(sink: Optional[SignalSink]) -> None:
    """Install the process sink. A run owns its sink and clears it after."""
    global _ACTIVE
    with _ACTIVE_LOCK:
        _ACTIVE = sink


def route_thread(sink: SignalSink) -> None:
    """Send every `emit` raised on the calling thread to `sink` until `unroute_thread`."""
    with _ROUTES_LOCK:
        _ROUTES[threading.get_ident()] = sink


def unroute_thread() -> None:
    """Return the calling thread's emits to the process sink `set_sink` installed."""
    with _ROUTES_LOCK:
        _ROUTES.pop(threading.get_ident(), None)


def get_sink() -> Optional[SignalSink]:
    """The sink the calling thread emits into: its `route_thread` sink when one
    is set, else the process sink."""
    if _ROUTES:
        with _ROUTES_LOCK:
            routed = _ROUTES.get(threading.get_ident())
        if routed is not None:
            return routed
    with _ACTIVE_LOCK:
        return _ACTIVE


def emit(
    name: str,
    actual: Any,
    expected: Any = None,
    ok: Optional[bool] = None,
    context: Optional[dict] = None,
    every: float = 0.0,
    instance: Optional[str] = None,
    module: Optional[str] = None,
    duration: Optional[float] = None,
) -> Optional[Signal]:
    """Module-level emit; the connection point every call site uses.

    A plain function, not a bus subscription, so no sink reference is
    needed at the call site. With no sink installed this is a dict
    lookup and a return. `instance` distinguishes live objects sharing
    one `every=` throttle window; it has no effect without `every`.
    """
    sink = get_sink()
    if sink is None:
        return None
    _site = _caller_site(2)
    _mod = module or _caller_module(2)
    if every and every > 0:
        # `every=N` admits one record per N seconds per identity; a failing check is
        # never suppressed.
        _judged = (
            ok
            if ok is not None
            else (bool(actual == expected) if expected is not None else None)
        )
        if _judged is not False:
            _n = _throttle_admit(name, _site, float(every), instance)
            if _n is None:
                return None
            return sink.emit(
                name,
                actual,
                expected=expected,
                ok=ok,
                context=context,
                site=_site,
                module=_mod,
                count=_n,
                duration=duration,
                every=float(every),
            )
    return sink.emit(
        name,
        actual,
        expected=expected,
        ok=ok,
        context=context,
        site=_site,
        module=_mod,
        duration=duration,
        every=float(every or 0.0),
    )


def install_process_sink(
    log_dir: Optional[Path] = None,
    flush_every: int = PROCESS_SINK_FLUSH_EVERY,
) -> Optional["SignalSink"]:
    """Install the sink the whole process emits into; call once from `main()`.

    Writes to `<log_dir or ~/.acervator_logs/signals>/session.jsonl`,
    bounded by rotation and by `RETAIN_ROWS`. Returns None, never
    raising, if the log directory cannot be opened.
    """
    try:
        base = (
            Path(log_dir) if log_dir else (Path.home() / ".acervator_logs" / "signals")
        )
        base.mkdir(parents=True, exist_ok=True)
        # The filename is constant; every process appends to and rotates the same file.
        sink = SignalSink(flush_every=flush_every)
        sink.path = base / "session.jsonl"
        set_sink(sink)
        return sink
    except OSError:
        return None


def read_records(path: Path) -> tuple:
    """Read a captured JSONL file back as frozen `Signal` records.

    Skips a line that fails to decode; a field that fails to coerce
    restores its "not measured" default rather than dropping the record.
    """
    out: list[Signal] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ctx = d.get("context")
                out.append(
                    Signal(
                        name=d.get("name", ""),
                        site=d.get("site", ""),
                        actual=freeze(d.get("actual")),
                        expected=freeze(d.get("expected")),
                        ok=d.get("ok"),
                        seq=int(d.get("seq", 0) or 0),
                        ts=d.get("ts", ""),
                        context=freeze(ctx) if ctx else None,
                        module=d.get("module") or "",
                        kind=d.get("kind") or "check",
                        count=int(d.get("count") or 1),
                        # A missing `dt` restores None, not 0.0; a missing `nth`
                        # restores 0, not 1.
                        dt=_as_float(d.get("dt")),
                        nth=_as_ordinal(d.get("nth")),
                        # A missing `duration` restores None, not 0.0, which would claim
                        # a measured instant.
                        duration=_as_float(d.get("duration")),
                        # A line written before these three carried them restores None
                        # for each, which reads as "the writer declared nothing".
                        cadence=_as_cadence(d.get("cadence")),
                        budget_s=_as_budget(d.get("budget_s")),
                        tab=_as_tab(d.get("tab")),
                    )
                )
    except OSError:
        return ()
    return tuple(out)
