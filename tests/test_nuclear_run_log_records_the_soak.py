"""The Nuclear run log must persist what a soak measured.

A soak's value is being able to read back which cycle failed, what the
coverage was and whether bus payloads carried the fields consumers read.
These pin that the data reaches `meta.json`, and that the API the
controller uses accepts the arguments it passes.
"""

from __future__ import annotations

import inspect
import json

import pytest

from src.core.emit_contracts import EmitObserver
from src.simulator.nuclear_fleet_controller import NuclearCycle, NuclearFleetController
from src.trading.nuclear_verification import SwarmFeatureVerifier
from src.trading.sim_run_log import SimRunLog


def _meta(log: SimRunLog) -> dict:
    directory = log.directory
    assert directory is not None, "the run log never created its directory"
    return json.loads((directory / "meta.json").read_text(encoding="utf-8"))


@pytest.fixture
def controller(tmp_path) -> NuclearFleetController:
    ctl = NuclearFleetController(max_cycles=1)
    ctl._log = SimRunLog(root=tmp_path)
    ctl._log.start_run(config={"mode": "nuclear"})
    return ctl


def test_record_gate_rejects_the_payload_keyword(tmp_path):
    """Positive control: the old call shape raises, it does not no-op."""
    params = inspect.signature(SimRunLog.record_gate).parameters
    assert "payload" not in params, (
        "record_gate grew a `payload` parameter; this control no longer "
        f"proves anything. Parameters: {list(params)}"
    )
    log = SimRunLog(root=tmp_path)
    log.start_run(config={})
    with pytest.raises(TypeError):
        log.record_gate(bot_id="nuclear", symbol="", payload={"a": 1})


def test_the_summary_carries_every_recorded_cycle(controller):
    controller._record_cycle(
        NuclearCycle(index=1, candles_played=300, trades_fired=7, noise_pct=0.05)
    )
    controller._record_cycle(NuclearCycle(index=2, candles_played=200, error="boom"))
    controller._teardown()

    cycles = _meta(controller._log)["summary"]["cycles"]
    assert [c["cycle"] for c in cycles] == [1, 2], (
        "both cycles must reach the run log summary; got " f"{cycles!r}"
    )
    assert cycles[0]["candles_played"] == 300
    assert cycles[0]["trades_fired"] == 7
    assert cycles[1]["error"] == "boom"


def test_the_summary_carries_the_coverage_report(controller):
    controller._verifier = SwarmFeatureVerifier()
    controller._teardown()

    summary = _meta(controller._log)["summary"]
    assert "coverage" in summary, (
        "the coverage report must reach the run log summary; keys were "
        f"{sorted(summary)}"
    )
    assert summary["coverage"] == controller._verifier.report.to_dict()


def test_the_summary_carries_the_emit_contract_report(controller):
    controller._emit_obs = EmitObserver()
    controller._teardown()

    summary = _meta(controller._log)["summary"]
    assert "emit_contracts" in summary, (
        "the emit-contract report must reach the run log summary; keys "
        f"were {sorted(summary)}"
    )
    assert summary["emit_contracts"] == controller._emit_obs.to_dict()


def test_no_verifier_leaves_the_coverage_key_absent(controller):
    """Negative half: absent data is absent, not an empty stand-in."""
    controller._teardown()

    summary = _meta(controller._log)["summary"]
    assert "coverage" not in summary
    assert "emit_contracts" not in summary
    assert summary["cycles"] == []
