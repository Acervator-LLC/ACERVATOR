"""signal_contract.py -- the emitter contract for the platform's signal network.

Defines `Signal`, the frozen record `emit()` produces, and `SignalSink`,
the buffered sink that stores and rotates them under
`~/.acervator_logs/signals/`. A satisfied expectation is recorded the
same as a violated one, so a call site that never ran and one that
always passed are both visible.
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

RETAIN_ROWS = 350_000
"""Signal records kept in memory at once; older ones are evicted from memory but remain
in the file on disk.
"""

MAX_FILE_BYTES = 50 * 1024 * 1024
"""Byte size at which the sink's file rotates to `.1`."""

FILE_BACKUP_COUNT = 5
"""Backup files kept when the sink's file rotates."""


# The digest ladder
# A second log beside the main one, admitting one record per
# DIGEST_MIN_INTERVAL seconds per identity.
# Suppressed records fold into the next admitted line's `folded` count.

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


# The cadence category
# always_on pins are reached by a loop, timer or stream every pass;
# toggle pins need a discrete trigger.

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

_ALWAYS_ON_PINS: tuple[str, ...] = (
    "bot.01.002.postcondition.capital_reservation",
    "sim.06.011.postcondition.price_chart.fed",
    "sim.06.012.postcondition.gate_status.rendered",
    "ta.07.003.postcondition.computed",
    "ta.07.004.postcondition.raw.{}",
    "tick.08.001.event.throttled",
    "tick.08.002.event.worked",
    "charts.13.001.invariant.panels_mounted",
    "charts.13.002.postcondition.panel_symbols_current",
    "charts.13.004.postcondition.panel_refreshed",
    "charts.13.005.invariant.panels_fresh",
    "console.14.001.invariant.records_rendered",
    "console.14.002.invariant.view_holds_rendered",
    "console.14.003.invariant.drain_alive",
    "exchange.15.002.invariant.every_bot_reaches_a_table",
    "exchange.15.003.invariant.selection_survives_refresh",
)
"""The sixteen pins a loop or a timer reaches on every pass, categorised
`CADENCE_ALWAYS_ON`.
"""

_TOGGLE_PINS: tuple[str, ...] = (
    "bot.01.001.postcondition.capital_reservation",
    "bot.01.003.postcondition.adoption_capped",
    "extractor.02.001.postcondition.tranche_contained",
    "extractor.02.002.invariant.arrival_atomic",
    "fleet.03.001.postcondition.bots_loaded",
    "fleet.03.002.invariant.bot_ids_mirror_live",
    "fleet.03.003.invariant.sections_imported",
    "fleet.03.004.postcondition.wires_loaded",
    "fleet.03.005.invariant.state_parity",
    "fleet.03.006.postcondition.state_imported",
    "fleet.03.007.postcondition.positions_seeded_from_lots",
    "fleet.03.008.postcondition.lotless_opened_locked",
    "gui.04.001.postcondition.voting_panel.fit",
    "gui.04.002.postcondition.clear_settled",
    "gui.04.003.postcondition.despawn_rows_match_ledger",
    "history.05.001.postcondition.scan_complete",
    "history.05.002.postcondition.trades_stored",
    "history.05.003.postcondition.filter_options_built",
    "history.05.004.postcondition.filters_applied",
    "history.05.005.postcondition.page_rendered",
    "history.05.006.postcondition.joiner_indexes_built",
    "history.05.007.postcondition.csv_exported",
    "sim.06.001.postcondition.candles_stepped",
    "sim.06.002.postcondition.bot_ticks_did_work",
    "sim.06.003.counter.ticks_before_tape",
    "sim.06.004.counter.trades_fired",
    "sim.06.005.invariant.exceptions",
    "sim.06.006.event.window_played",
    "sim.06.007.postcondition.fleet_spawned",
    "sim.06.008.invariant.state_persisted",
    "sim.06.009.invariant.spawn_drift",
    "sim.06.010.postcondition.bot_table.rendered",
    "sim.06.013.state_transition.mode_selected",
    "sim.06.014.event.log.line",
    "ta.07.001.postcondition.coverage_per_bot",
    "ta.07.002.invariant.invariants",
    "tick.08.003.event.exit_dust_band",
    "topology.09.001.state_transition.bot_attached",
    "topology.09.002.postcondition.wires_received",
    "ytd.10.001.gauge.trades_fetched",
    "ytd.10.002.postcondition.fleet_symbol_coverage",
    "ytd.10.003.gauge.per_symbol_counts",
    "swarm.11.001.postcondition.sim_run_registered",
    "swarm.11.002.postcondition.paper_run_registered",
    "trading.12.001.postcondition.tab_assembled",
    "trading.12.002.postcondition.exchange_tab_routed",
    "trading.12.003.postcondition.exchange_tabs_synced",
    "trading.12.004.postcondition.active_layer_alias",
    "trading.12.005.postcondition.activity_log_paused",
    "trading.12.006.postcondition.notification_relayed",
    "charts.13.003.postcondition.timeframe_rearmed",
    "console.14.004.postcondition.pause_quiets_both_panes",
    "console.14.005.postcondition.pause_buffer_delivered",
    "exchange.15.001.postcondition.command_routed_to_chosen_table",
    "exchange.15.004.postcondition.privacy_applied_to_every_field",
    "exchange.15.005.postcondition.privacy_button_matches_registry",
    "apitest.16.001.postcondition.label_matches_session",
    "apitest.16.002.postcondition.session_released",
    "apitest.16.003.postcondition.reported_ok_ran_a_test",
    "apitest.16.004.postcondition.green_probe_read_a_body",
    "apitest.16.005.postcondition.indicator_is_mappable",
    "instance.17.001.postcondition.auto_start_permitted",
)
"""The sixty-two pins that need a trigger. Silence from one is normal."""

CADENCE_BY_NAME = MappingProxyType(
    {
        **{pin: CADENCE_ALWAYS_ON for pin in _ALWAYS_ON_PINS},
        **{pin: CADENCE_TOGGLE for pin in _TOGGLE_PINS},
    }
)
"""Every pin's declared category, by current name. 78 entries."""

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
    not measured, never 0.0 for "not measured".
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
                    if _aux is not None and float(every or 0.0) > _aux[1]:
                        _aux[1] = float(every or 0.0)
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
            sub = r.name.split(".", 1)[0]
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


def get_sink() -> Optional[SignalSink]:
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
    flush_every: int = 500,
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
                    )
                )
    except OSError:
        return ()
    return tuple(out)
