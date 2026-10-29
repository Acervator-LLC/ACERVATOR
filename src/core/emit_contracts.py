"""Expected-shape validation for bus emissions.

``SettledFill`` declares the fields every ``FILL_TOPIC`` announcement carries,
and ``read_settled_fill`` reads one back or raises ``FillShapeError``.
``CONTRACTS`` declares each topic's required fields, and ``EmitObserver``
collects one ``Violation`` per breach without raising into the producer.
``format_observer_lines`` renders what it collected.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, fields
from typing import Any, Optional

from .signal_contract import STALE_AFTER

logger = logging.getLogger("acervator.emit_contracts")


SILENCE_UNBOUNDED = "unbounded"
"""The topic declares no silence budget, so silence from it is not evidence."""

SILENCE_NEVER = "never"
"""A budget is declared and the topic has not emitted at all; its producer is
absent, which is not the same as stopped.
"""

SILENCE_WITHIN = "within"
"""The topic's last emission is inside its declared budget."""

SILENCE_OVERDUE = "overdue"
"""The topic emitted and then stopped for longer than its declared budget. This is
the reading a file of written records cannot give, because a record is only ever
written when something happened.
"""

SILENCE_READINGS = (
    SILENCE_UNBOUNDED,
    SILENCE_NEVER,
    SILENCE_WITHIN,
    SILENCE_OVERDUE,
)
"""The closed vocabulary. A topic declaring no budget returns only the first."""

LOOP_DRIVEN_SILENCE_BUDGET = STALE_AFTER
"""Seconds of silence after which a topic a bot's own evaluation loop drives reads
overdue. `STALE_AFTER` imported rather than copied, so the bus reading and the pin
reading cannot drift to two ages.
"""


@dataclass
class EmitContract:
    """The expected shape of one topic's payload.

    ``nested_key`` names the wrapper a topic such as ``pnl.event`` nests its
    payload under, and ``exclusive`` names fields of which exactly one is present.
    """

    topic: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    exclusive: tuple[str, ...] = ()
    vocab: dict = field(default_factory=dict)
    nested_key: Optional[str] = "data"
    description: str = ""
    silence_budget: Optional[float] = None
    """Seconds of silence after which this topic reads overdue. ``None`` for a topic
    a discrete trigger drives, where silence says nothing and the reading is
    ``SILENCE_UNBOUNDED`` rather than a fault.
    """

    def extract(self, event_data: dict) -> dict:
        if not isinstance(event_data, dict):
            return {}
        if self.nested_key:
            inner = event_data.get(self.nested_key)
            if isinstance(inner, dict):
                return inner
        return event_data


@dataclass
class Violation:
    topic: str
    kind: str  # "missing_field" | "bad_value" | "never_emitted"
    detail: str
    count: int = 1

    def key(self) -> tuple:
        return (self.topic, self.kind, self.detail)


FILL_TOPIC = "trade.filled"
"""The topic ``BotContainer._announce_fill`` sends each verified fill on, once."""

FILL_BUY = "BUY"
FILL_SELL = "SELL"
FILL_SIDES: tuple[str, ...] = (FILL_BUY, FILL_SELL)

FILL_FEE_FIELDS: tuple[str, ...] = ("fee_usd", "fee_refusal")
"""The two fee fields of a ``SettledFill``, of which a payload carries exactly one."""

FILL_NUMBER_FIELDS: tuple[str, ...] = ("amount", "price", "usd", "profit")
FILL_TEXT_FIELDS: tuple[str, ...] = ("bot_id", "type", "symbol", "exchange")


@dataclass(frozen=True)
class SettledFill:
    """One verified fill, in the shape every ``FILL_TOPIC`` announcement carries.

    ``amount`` is the units one booking settled at ``price``, and exactly one of
    ``fee_usd`` and ``fee_refusal`` is set.
    """

    bot_id: str
    side: str
    type: str
    amount: float
    price: float
    usd: float
    profit: float
    operator_initiated: bool
    symbol: str
    exchange: str
    fee_usd: Optional[float] = None
    fee_refusal: Optional[str] = None

    def payload(self) -> dict:
        """The field map ``FILL_TOPIC`` carries: each of ``SETTLED_FILL_FIELDS``
        and the fee field of ``FILL_FEE_FIELDS`` that is set.
        """
        out = {name: getattr(self, name) for name in SETTLED_FILL_FIELDS}
        for name in FILL_FEE_FIELDS:
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        return out


SETTLED_FILL_FIELDS: tuple[str, ...] = tuple(
    one.name for one in fields(SettledFill) if one.name not in FILL_FEE_FIELDS
)


class FillShapeError(ValueError):
    """A ``FILL_TOPIC`` announcement not in the shape ``SettledFill`` declares."""


def _is_number(value: Any) -> bool:
    """True for an int or a float, and False for a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fill_faults(event_data: dict) -> list[str]:
    """Each way ``event_data`` departs from ``SettledFill``, named by its field."""
    faults = [
        f"{name} absent" for name in SETTLED_FILL_FIELDS if name not in event_data
    ]
    held = [name for name in FILL_FEE_FIELDS if name in event_data]
    if len(held) != 1:
        faults.append(f"{len(held)} of {', '.join(FILL_FEE_FIELDS)} present, not 1")
    faults += [
        f"{name} is not a number"
        for name in (*FILL_NUMBER_FIELDS, "fee_usd")
        if name in event_data and not _is_number(event_data[name])
    ]
    faults += [
        f"{name} is not text"
        for name in (*FILL_TEXT_FIELDS, "fee_refusal")
        if name in event_data and not isinstance(event_data[name], str)
    ]
    if "side" in event_data and event_data["side"] not in FILL_SIDES:
        faults.append(f"side {event_data['side']!r} is not one of {FILL_SIDES}")
    if "operator_initiated" in event_data and not isinstance(
        event_data["operator_initiated"], bool
    ):
        faults.append("operator_initiated is not True or False")
    return faults


def read_settled_fill(event_data: Any) -> SettledFill:
    """The ``SettledFill`` one ``FILL_TOPIC`` announcement carries, with no field
    defaulted.

    Raises ``FillShapeError`` naming every fault ``_fill_faults`` finds.
    """
    if not isinstance(event_data, dict):
        raise FillShapeError(
            f"the announcement is a {type(event_data).__name__}, not a field map"
        )
    faults = _fill_faults(event_data)
    if faults:
        raise FillShapeError("; ".join(faults))
    return SettledFill(
        **{
            name: event_data[name]
            for name in (*SETTLED_FILL_FIELDS, *FILL_FEE_FIELDS)
            if name in event_data
        }
    )


TRADE_TYPES: tuple[str, ...] = (
    "SCRUM",
    "FOLD",
    "DIST",
    "ENTRY",
    "HEDGE",
    "MANUAL_SCRUM",
    "MANUAL_FOLD",
    "CARTRIDGE_SCRUM",
    "CARTRIDGE_FOLD",
    "WIRE_STACK_SCRUM",
    "WIRE_STACK_FOLD",
    "AUTO_DETONATION",
    "SELF_DESTRUCT",
    "MANUAL_TRANCHE_FOLD",
    "STACK_SPEND",
    "STACK_RUNG",
    "EXPIRY_CLOSE",
    "EXTRACTOR_ARTILLERY",
    "EXTRACTOR_EXIT",
)
"""Every ``SettledFill.type`` a completion point announces."""

CONTRACTS: tuple[EmitContract, ...] = (
    EmitContract(
        topic=FILL_TOPIC,
        required=SETTLED_FILL_FIELDS,
        optional=FILL_FEE_FIELDS,
        exclusive=FILL_FEE_FIELDS,
        vocab={"side": FILL_SIDES, "type": TRADE_TYPES},
        nested_key=None,
        description="One verified fill, flat, in the shape SettledFill "
        "declares. NOTE: the trade kind is `type` here, not `action` — the "
        "log schema uses `action`. `fee_usd` is the venue's own fee for this "
        "fill; `fee_refusal` replaces it when the venue reported none, and "
        "exactly one of the two is present.",
    ),
    EmitContract(
        topic="bot.gate_decision",
        required=("symbol",),
        optional=(
            "asset_class",
            "scrum_armed",
            "fold_armed",
            "scrum_blockers",
            "fold_blockers",
            "scrum_fixture",
            "fold_fixture",
        ),
        description="Gate evaluation snapshot at fire time. `asset_class` is "
        "the market's sector, and it picks the gate log the decision is "
        "written to beside the venue named in `exchange`.",
        silence_budget=LOOP_DRIVEN_SILENCE_BUDGET,
    ),
    EmitContract(
        topic="pnl.event",
        required=(),
        optional=("realised", "unrealised", "symbol"),
        description="P&L movement.",
    ),
    EmitContract(
        topic="ta.voting",
        required=(),
        optional=("panel", "timeframe"),
        description="Voting-engine snapshot.",
        silence_budget=LOOP_DRIVEN_SILENCE_BUDGET,
    ),
    EmitContract(
        topic="market_inspector.scan_started",
        required=("forced",),
        optional=("connector_count", "active_symbols"),
        nested_key=None,
        description="An HTF scan began. Flat payload: the Market Inspector "
        "emits its fields at the top level, not under `data`.",
    ),
    EmitContract(
        topic="market_inspector.scan_finished",
        required=("market_count", "duration_s"),
        optional=("signal_count", "pair_count", "source", "error"),
        nested_key=None,
        description="An HTF scan ended, carrying the markets it covered and "
        "how long it took, so a scan that found nothing is still recorded.",
    ),
)

_BY_TOPIC = {c.topic: c for c in CONTRACTS}


class EmitObserver:
    """Watches bus emissions and reports contract violations.

    Attach to SIM buses. Attaching to a live bus is permitted (this is
    read-only and never raises) but the caller should be deliberate
    about it.
    """

    def __init__(self, contracts: Optional[tuple] = None) -> None:
        self._contracts = {c.topic: c for c in (contracts or CONTRACTS)}
        self.seen: dict = {t: 0 for t in self._contracts}
        self._violations: dict = {}
        self.field_presence: dict = {t: {} for t in self._contracts}
        # `last_emission` maps topic to the monotonic reading of its last `observe`;
        # a topic absent from it has not emitted.
        self.last_emission: dict = {}

    def attach(self, bus: Any) -> bool:
        if bus is None or not hasattr(bus, "subscribe"):
            return False
        for topic in self._contracts:
            bus.subscribe(topic, self._make_handler(topic))
        return True

    def _make_handler(self, topic: str):
        def _handler(event: Any) -> None:
            try:
                self.observe(topic, getattr(event, "data", None) or {})
            except Exception as exc:  # noqa: BLE001 - observation must
                # never break the producer it is watching.
                logger.debug("emit observer(%s) failed: %s", topic, exc)

        return _handler

    def observe(self, topic: str, event_data: dict) -> None:
        contract = self._contracts.get(topic)
        if contract is None:
            return
        self.seen[topic] = self.seen.get(topic, 0) + 1
        self.last_emission[topic] = time.monotonic()
        payload = contract.extract(event_data)

        presence = self.field_presence.setdefault(topic, {})
        for k in payload:
            presence[k] = presence.get(k, 0) + 1

        for fieldname in contract.required:
            if fieldname not in payload:
                self._add(
                    Violation(
                        topic,
                        "missing_field",
                        f"required field {fieldname!r} absent; payload had "
                        f"{sorted(payload)[:8]}",
                    )
                )

        if contract.exclusive:
            held = [name for name in contract.exclusive if name in payload]
            if len(held) != 1:
                self._add(
                    Violation(
                        topic,
                        "bad_value" if held else "missing_field",
                        f"exactly one of {list(contract.exclusive)} expected; "
                        f"payload had {held}",
                    )
                )

        for fieldname, allowed in (contract.vocab or {}).items():
            if fieldname in payload:
                val = payload.get(fieldname)
                if val not in allowed:
                    self._add(
                        Violation(
                            topic,
                            "bad_value",
                            f"{fieldname}={val!r} not in {list(allowed)}",
                        )
                    )

    def _add(self, v: Violation) -> None:
        k = v.key()
        if k in self._violations:
            self._violations[k].count += 1
        else:
            self._violations[k] = v

    def finish(self) -> None:
        """Record topics that never fired.

        Called once at the end of a run. A declared topic with zero
        emissions is the highest-value finding here — it means either
        the producer is dead or the consumer is waiting on something
        that never comes.
        """
        for topic, n in self.seen.items():
            if n == 0:
                self._add(
                    Violation(
                        topic,
                        "never_emitted",
                        "declared but never emitted during this run",
                    )
                )

    def silence(self, now: Optional[float] = None) -> dict:
        """Return each declared topic's silence reading.

        `{topic: {"reading", "budget", "age"}}`, where `reading` is one
        of `SILENCE_READINGS`, `budget` is the contract's declared
        budget in seconds or None, and `age` is seconds since the
        topic's last emission or None when it never emitted. A topic
        with no budget reads `SILENCE_UNBOUNDED`, which states that its
        silence is not evidence rather than implying health. `now`
        defaults to `time.monotonic()`, so a caller replaying
        compressed time supplies its own clock.
        """
        at = time.monotonic() if now is None else float(now)
        out: dict = {}
        for topic, contract in self._contracts.items():
            budget = contract.silence_budget
            last = self.last_emission.get(topic)
            age = None if last is None else max(0.0, at - last)
            if budget is None or float(budget) <= 0.0:
                reading = SILENCE_UNBOUNDED
            elif age is None:
                reading = SILENCE_NEVER
            elif age > float(budget):
                reading = SILENCE_OVERDUE
            else:
                reading = SILENCE_WITHIN
            out[topic] = {"reading": reading, "budget": budget, "age": age}
        return out

    @property
    def violations(self) -> list:
        return sorted(
            self._violations.values(), key=lambda v: (v.kind, v.topic, v.detail)
        )

    def to_dict(self) -> dict:
        return {
            "topics_declared": len(self._contracts),
            "topics_seen": sum(1 for n in self.seen.values() if n > 0),
            "emissions": dict(sorted(self.seen.items())),
            "silence": dict(sorted(self.silence().items())),
            "violations": [
                {"topic": v.topic, "kind": v.kind, "detail": v.detail, "count": v.count}
                for v in self.violations
            ],
            "field_presence": {
                t: dict(sorted(f.items()))
                for t, f in sorted(self.field_presence.items())
            },
        }


def _silence_lines(silence: dict) -> list:
    """Render the silence readings: one tally line, then one line per topic that
    stopped or never started.

    A topic reading `SILENCE_UNBOUNDED` is counted and not listed, because
    silence from it is not evidence and a list of such topics would read as a
    list of faults.
    """
    if not silence:
        return []
    tally = {one: 0 for one in SILENCE_READINGS}
    named = []
    for topic, row in sorted(silence.items()):
        reading = str(row.get("reading") or SILENCE_UNBOUNDED)
        tally[reading] = tally.get(reading, 0) + 1
        if reading in (SILENCE_NEVER, SILENCE_OVERDUE):
            named.append((topic, reading, row.get("age"), row.get("budget")))
    out = [
        "  silence: "
        + ", ".join(f"{tally.get(one, 0)} {one}" for one in SILENCE_READINGS)
        + "  (unbounded means silence from that topic is not evidence)"
    ]
    for topic, reading, age, budget in named:
        shown = "no emission" if age is None else f"last {float(age):.1f}s ago"
        out.append(f"    [{reading}] {topic}: {shown}, budget {budget}s")
    return out


def format_observer_lines(obs: EmitObserver) -> list:
    """Operator-facing report.

    Field presence is printed for observed topics because that is what
    makes a rename diagnosable: seeing `type: 665` next to a consumer
    expecting `action` is the whole answer in one line.
    """
    d = obs.to_dict()
    out = [
        f"Emit contracts: {d['topics_seen']}/{d['topics_declared']} "
        "topic(s) observed",
    ]
    for topic, n in d["emissions"].items():
        fields = d["field_presence"].get(topic) or {}
        shown = ", ".join(f"{k}:{c}" for k, c in list(fields.items())[:8])
        out.append(
            f"  {topic:24} {n:>6} emission(s)" + (f"  [{shown}]" if shown else "")
        )
    out.extend(_silence_lines(d.get("silence") or {}))
    viols = d["violations"]
    if not viols:
        out.append("  no contract violations")
        return out
    out.append(f"  VIOLATIONS ({len(viols)}):")
    for v in viols:
        out.append(
            f"    [{v['kind']}] {v['topic']}: {v['detail']}"
            + (f"  (x{v['count']})" if v["count"] > 1 else "")
        )
    return out
