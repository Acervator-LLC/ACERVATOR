"""v3.24.30 — pin tests for emit-contract observation.

Operator directive 2026-08-05:

    "You also develop emit detection intelligence... We are always
    dealing with expected inputs and outputs. Each are formatted a
    certain way, should contain certain data, and should appear or be
    produced as expected."

WHAT THIS CATCHES
=================
Producer/consumer schema drift, which is silent on both sides: the
producer emits successfully, the consumer reads successfully and gets
None. Three real instances found in this codebase within one session:

1. ``trade.filled`` carries the trade kind as ``type``. The Nuclear
   verifier read ``action`` (the LOG schema's name). Result: 665 trades
   observed, 0 features recorded, coverage reported 0/17 while the run
   looked healthy.

2. ``trade.filled`` has TWO payload shapes — five sites nest under
   ``data={...}``, five pass kwargs flat. A consumer handling only one
   silently misses half the fills.

3. ``scrumming_bot.py:8568`` (HEDGE rebalance) emitted ``size`` and no
   ``amount``. ``LogManager._on_trade_filled_bus`` reads
   ``merged.get("amount", 0)``, so every hedge rebalance was written to
   the live trade.log with **amount=0.0**. The fill quantity was absent
   from the trade record entirely.

The third is a live data-integrity defect found by running the observer,
not by reading code.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.emit_contracts import (  # noqa: E402
    CONTRACTS,
    EmitContract,
    EmitObserver,
    format_observer_lines,
)


class _Event:
    def __init__(self, data):
        self.data = data


def _obs():
    return EmitObserver()


# ── the three failure classes ────────────────────────────────────

def test_missing_required_field_is_reported():
    """The HEDGE case: `size` present, `amount` absent."""
    o = _obs()
    o.observe("trade.filled", {
        "bot_id": "b", "side": "buy", "type": "HEDGE",
        "price": 1.0, "size": 5.0})
    v = [x for x in o.violations if x.kind == "missing_field"]
    assert v, "missing `amount` not reported"
    assert "amount" in v[0].detail


def test_complete_payload_produces_no_violation():
    o = _obs()
    o.observe("trade.filled", {
        "bot_id": "b", "side": "BUY", "amount": 2.0, "price": 10.0,
        "type": "SCRUM"})
    assert not [x for x in o.violations if x.kind == "missing_field"]


def test_bad_value_is_reported():
    o = _obs()
    o.observe("trade.filled", {
        "side": "SIDEWAYS", "amount": 1.0, "price": 1.0})
    assert [x for x in o.violations if x.kind == "bad_value"]


def test_never_emitted_is_reported_only_after_finish():
    """A topic that never fires is the highest-value finding, but it
    can only be known once the run is over."""
    o = _obs()
    assert not [x for x in o.violations if x.kind == "never_emitted"]
    o.finish()
    kinds = [x for x in o.violations if x.kind == "never_emitted"]
    assert len(kinds) == len(CONTRACTS)


def test_observed_topic_is_not_flagged_never_emitted():
    o = _obs()
    o.observe("trade.filled", {
        "side": "BUY", "amount": 1.0, "price": 1.0})
    o.finish()
    assert not [x for x in o.violations
                if x.kind == "never_emitted" and x.topic == "trade.filled"]


# ── both payload shapes ──────────────────────────────────────────

def test_nested_payload_is_unwrapped():
    """Five emit sites nest under data={...}; a contract that only
    checked the top level would report every field missing."""
    o = _obs()
    o.observe("trade.filled", {
        "bot_id": "b",
        "data": {"side": "SELL", "amount": 3.0, "price": 9.0,
                 "type": "SCRUM"}})
    assert not [x for x in o.violations if x.kind == "missing_field"]


def test_flat_payload_is_accepted():
    """The other five sites pass kwargs flat, with no data wrapper."""
    o = _obs()
    o.observe("trade.filled", {
        "bot_id": "b", "side": "BUY", "amount": 3.0, "price": 9.0,
        "type": "ENTRY"})
    assert not [x for x in o.violations if x.kind == "missing_field"]


def test_field_presence_makes_a_rename_diagnosable():
    """Seeing `type: N` next to a consumer expecting `action` is the
    whole diagnosis in one line."""
    o = _obs()
    for _ in range(3):
        o.observe("trade.filled", {
            "side": "BUY", "amount": 1.0, "price": 1.0, "type": "SCRUM"})
    pres = o.to_dict()["field_presence"]["trade.filled"]
    assert pres.get("type") == 3
    assert "action" not in pres


# ── it must never break the producer ─────────────────────────────

def test_observation_never_raises_on_garbage():
    o = _obs()
    for junk in (None, [], "text", 42, {"data": "not-a-dict"}):
        o.observe("trade.filled", junk)   # must not raise


def test_unknown_topic_is_ignored():
    o = _obs()
    o.observe("no.such.topic", {"anything": 1})
    assert o.seen.get("no.such.topic") is None


def test_handler_swallows_downstream_errors():
    """A failing observation must not propagate into the bus emit and
    take down a trading tick."""
    o = _obs()
    handler = o._make_handler("trade.filled")

    class _Bad:
        @property
        def data(self):
            raise RuntimeError("boom")

    handler(_Bad())    # must not raise


def test_attach_refuses_a_busless_object():
    assert _obs().attach(None) is False
    assert _obs().attach(object()) is False


# ── repeated violations collapse ─────────────────────────────────

def test_repeat_violations_are_counted_not_duplicated():
    o = _obs()
    for _ in range(7):
        o.observe("trade.filled", {"side": "buy", "price": 1.0})
    v = [x for x in o.violations if x.kind == "missing_field"]
    assert len(v) == 1
    assert v[0].count == 7


def test_report_lines_lead_with_violations():
    o = _obs()
    o.observe("trade.filled", {"side": "buy", "price": 1.0})
    o.finish()
    lines = format_observer_lines(o)
    assert any("VIOLATIONS" in ln for ln in lines)


# ── custom contracts ─────────────────────────────────────────────

def test_custom_contract_is_honoured():
    c = EmitContract(topic="x.y", required=("q",), nested_key=None)
    o = EmitObserver(contracts=(c,))
    o.observe("x.y", {"z": 1})
    assert [v for v in o.violations if "q" in v.detail]
