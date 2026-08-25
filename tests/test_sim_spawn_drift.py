"""Spawn-over-spawn drift for the simulator fleet (v3.24.99).

`load_sim_state` existed and had no caller. `save_sim_state` clobbers
~/.acervator/simulator_bot_state.json on every Load, so the persisted
document was write-only: nothing ever read it back and no Load could be
told apart from the one before it.

`diff_spawns` closes that loop. These tests cover it, and each one that
asserts "no drift" is paired with a case that produces drift, so a
helper that returned an empty result for every input would fail here.

NOTE ON PATHS: every test writes to tmp_path. Nothing here touches
~/.acervator.
"""

from __future__ import annotations

import json

import pytest

from src.gui.simulator_tab.fleet.simulator_bot_state import (
    SIM_STATE_PATH,
    diff_spawns,
    load_sim_state,
    save_sim_state,
)


def _doc(bots: dict) -> dict:
    """A spawn document shaped like `build_sim_state` output."""
    return {
        "schema": 1,
        "saved_at": 1_000.0,
        "bot_count": len(bots),
        "bots": {
            sim_id: {
                "bot_id": sim_id,
                "source_bot_id": sim_id.replace("simulated_", ""),
                "symbol": sym,
                "spawned_at": 1_000.0,
                "scrumming_state": {"units": 1.0},
                "source_state_at_load": src,
                "config": {"symbol": sym},
            }
            for sim_id, (sym, src) in bots.items()
        },
    }


def test_first_spawn_reports_first_spawn():
    """No prior document: every bot is new, and the flag says why."""
    cur = _doc({"simulated_a": ("BTC/USD", {"units": 1.0})})
    d = diff_spawns({}, cur)
    assert d["first_spawn"] is True
    assert d["added"] == ["simulated_a"]
    assert d["changed"] == []
    assert d["unchanged"] == 0


def test_identical_reload_reports_no_drift():
    bots = {
        "simulated_a": ("BTC/USD", {"units": 1.0}),
        "simulated_b": ("ETH/USD", {"units": 2.0}),
    }
    prev, cur = _doc(bots), _doc(bots)
    d = diff_spawns(prev, cur)
    assert d["first_spawn"] is False
    assert (d["added"], d["removed"], d["changed"]) == ([], [], [])
    assert d["unchanged"] == 2


def test_changed_live_source_is_detected():
    """POSITIVE CONTROL for the test above.

    Same two bots, one live source moved. If `diff_spawns` ever stops
    comparing, `test_identical_reload_reports_no_drift` still passes and
    this one fails. Neither test is meaningful without the other.
    """
    prev = _doc(
        {
            "simulated_a": ("BTC/USD", {"units": 1.0}),
            "simulated_b": ("ETH/USD", {"units": 2.0}),
        }
    )
    cur = _doc(
        {
            "simulated_a": ("BTC/USD", {"units": 1.5}),
            "simulated_b": ("ETH/USD", {"units": 2.0}),
        }
    )
    d = diff_spawns(prev, cur)
    assert d["changed"] == ["simulated_a"]
    assert d["unchanged"] == 1


def test_key_order_alone_is_not_drift():
    """`_canon` sorts keys. A dict rebuilt in another order is equal."""
    prev = _doc({"simulated_a": ("BTC/USD", {"units": 1.0, "z": 2, "a": 3})})
    cur = _doc({"simulated_a": ("BTC/USD", {"a": 3, "units": 1.0, "z": 2})})
    assert diff_spawns(prev, cur)["changed"] == []


def test_added_and_removed_bots():
    prev = _doc({"simulated_a": ("BTC/USD", {}), "simulated_b": ("ETH/USD", {})})
    cur = _doc({"simulated_b": ("ETH/USD", {}), "simulated_c": ("SOL/USD", {})})
    d = diff_spawns(prev, cur)
    assert d["added"] == ["simulated_c"]
    assert d["removed"] == ["simulated_a"]
    assert d["unchanged"] == 1


def test_sim_state_moving_is_not_drift():
    """A replay MUST move `scrumming_state`. That is not drift.

    Only `source_state_at_load` -- the live entry the bot was cloned
    from -- counts. This guards against someone widening the comparison
    to the whole document, which would flag every post-replay Load.
    """
    prev = _doc({"simulated_a": ("BTC/USD", {"units": 1.0})})
    cur = _doc({"simulated_a": ("BTC/USD", {"units": 1.0})})
    cur["bots"]["simulated_a"]["scrumming_state"] = {"units": 99.0}
    cur["bots"]["simulated_a"]["spawned_at"] = 5_000.0
    assert diff_spawns(prev, cur)["changed"] == []


def test_load_returns_empty_document_when_absent(tmp_path):
    d = load_sim_state(tmp_path / "nope.json")
    assert d["bots"] == {} and d["bot_count"] == 0


def test_load_survives_corrupt_file(tmp_path):
    p = tmp_path / "sim.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_sim_state(p)["bots"] == {}


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / "sim.json"
    doc = _doc({"simulated_a": ("BTC/USD", {"units": 1.0})})
    save_sim_state(doc, p)
    back = load_sim_state(p)
    assert back["bots"]["simulated_a"]["symbol"] == "BTC/USD"
    assert diff_spawns(back, doc)["changed"] == []


def test_save_refuses_the_live_bot_state_path(tmp_path, monkeypatch):
    """The live file is the operator's. Nothing here may write it.

    The guard compares resolved path IDENTITY, not the file name, so a
    stray `bot_state.json` elsewhere is a normal target. This test
    redirects BOT_STATE_PATH at a decoy and aims the write there. The
    real ~/.acervator/bot_state.json is never passed to `save_sim_state`
    -- if the guard regressed, a test that aimed at it would destroy the
    live fleet to prove a point.
    """
    import src.gui.simulator_tab.fleet.simulator_bot_state as sbs

    decoy = tmp_path / "bot_state.json"
    decoy.write_text(json.dumps({"bots": {"real": 1}}), encoding="utf-8")
    monkeypatch.setattr(sbs, "BOT_STATE_PATH", decoy)
    before = decoy.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to write"):
        sbs.save_sim_state(_doc({}), decoy)
    assert decoy.read_text(encoding="utf-8") == before
    assert not (tmp_path / "bot_state.json.tmp").exists()


def test_save_allows_a_normal_path(tmp_path, monkeypatch):
    """POSITIVE CONTROL: the guard must not refuse everything."""
    import src.gui.simulator_tab.fleet.simulator_bot_state as sbs

    monkeypatch.setattr(sbs, "BOT_STATE_PATH", tmp_path / "bot_state.json")
    out = sbs.save_sim_state(
        _doc({"simulated_a": ("BTC/USD", {})}), tmp_path / "sim.json"
    )
    assert out.exists()
    assert not (tmp_path / "bot_state.json").exists()


def test_sim_state_path_is_not_bot_state():
    assert SIM_STATE_PATH.name == "simulator_bot_state.json"
    assert SIM_STATE_PATH.name != "bot_state.json"
