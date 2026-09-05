"""Expected-shape validation for bus emissions.

``CONTRACTS`` declares each topic's required fields and ``TRADE_TYPES`` its
accepted trade vocabulary, both taken from the emit sites. ``EmitObserver``
collects one ``Violation`` per breach and never raises into the producer.
``format_observer_lines`` renders what it collected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("acervator.emit_contracts")


@dataclass
class EmitContract:
    """The expected shape of one topic's payload.

    ``nested_key`` handles the wrapper this codebase actually uses:
    ``bus.emit("trade.filled", bot_id=..., data={...})`` puts the real
    payload one level down, so a contract that checked the top level
    would report every required field missing.
    """

    topic: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    vocab: dict = field(default_factory=dict)
    nested_key: Optional[str] = "data"
    description: str = ""

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


# Field names come from the emit sites: trade.filled carries type, the log row action.

TRADE_TYPES: tuple[str, ...] = (
    "SCRUM",
    "FOLD",
    "CARTRIDGE_SCRUM",
    "CARTRIDGE_FOLD",
    "ENTRY",
    "HEDGE",
    "DIST",
    "AUTO_DETONATION",
    "SELF_DESTRUCT",
    "MANUAL_TRANCHE_FOLD",
)

CONTRACTS: tuple[EmitContract, ...] = (
    EmitContract(
        topic="trade.filled",
        required=("side", "amount", "price"),
        optional=("type", "usd", "profit", "operator_initiated"),
        vocab={"side": ("BUY", "SELL", "buy", "sell")},
        description="A fill. NOTE: the trade kind is `type` here, not "
        "`action` — the log schema uses `action`.",
    ),
    EmitContract(
        topic="bot.gate_decision",
        required=("symbol",),
        optional=(
            "scrum_armed",
            "fold_armed",
            "scrum_blockers",
            "fold_blockers",
            "scrum_fixture",
            "fold_fixture",
        ),
        description="Gate evaluation snapshot at fire time.",
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
            "violations": [
                {"topic": v.topic, "kind": v.kind, "detail": v.detail, "count": v.count}
                for v in self.violations
            ],
            "field_presence": {
                t: dict(sorted(f.items()))
                for t, f in sorted(self.field_presence.items())
            },
        }


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
