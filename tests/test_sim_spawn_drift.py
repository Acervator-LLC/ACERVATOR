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
import os
from pathlib import Path

import pytest

from src.simulator.fleet.simulator_bot_state import (
    SIM_STATE_PATH,
    SIM_STATE_ROOT_ENV,
    bot_state_path,
    diff_spawns,
    load_sim_state,
    save_sim_state,
    sim_state_path,
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

    The decoy is placed by redirecting the ROOT, not by patching a
    module constant: the constant is no longer what `save_sim_state`
    reads, so patching it would test nothing and still pass.
    """
    import src.simulator.fleet.simulator_bot_state as sbs

    monkeypatch.setenv(sbs.SIM_STATE_ROOT_ENV, str(tmp_path))
    decoy = tmp_path / "bot_state.json"
    decoy.write_text(json.dumps({"bots": {"real": 1}}), encoding="utf-8")
    assert sbs.bot_state_path() == decoy
    before = decoy.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to write"):
        sbs.save_sim_state(_doc({}), decoy)
    assert decoy.read_text(encoding="utf-8") == before
    assert not (tmp_path / "bot_state.json.tmp").exists()


def test_save_allows_a_normal_path(tmp_path, monkeypatch):
    """POSITIVE CONTROL: the guard must not refuse everything."""
    import src.simulator.fleet.simulator_bot_state as sbs

    monkeypatch.setenv(sbs.SIM_STATE_ROOT_ENV, str(tmp_path))
    out = sbs.save_sim_state(
        _doc({"simulated_a": ("BTC/USD", {})}), tmp_path / "sim.json"
    )
    assert out.exists()
    assert not (tmp_path / "bot_state.json").exists()


def test_sim_state_path_is_not_bot_state():
    assert SIM_STATE_PATH.name == "simulator_bot_state.json"
    assert SIM_STATE_PATH.name != "bot_state.json"


def test_the_default_root_is_the_live_folder_when_the_variable_is_unset(monkeypatch):
    """CONTROL: the shipping application is unchanged.

    The operator runs Acervator with no such variable set. If this fails,
    the repair moved his own Simulator state file and the fleet he saved
    yesterday is invisible to the app today.

    Read-only: this asserts a resolved path and writes nothing.
    """
    monkeypatch.delenv(SIM_STATE_ROOT_ENV, raising=False)
    live = Path.home() / ".acervator"
    assert sim_state_path() == live / "simulator_bot_state.json"
    assert bot_state_path() == live / "bot_state.json"


def test_the_variable_redirects_both_paths(tmp_path, monkeypatch):
    """CONTROL: the override actually moves the destination."""
    monkeypatch.setenv(SIM_STATE_ROOT_ENV, str(tmp_path))
    assert sim_state_path() == tmp_path / "simulator_bot_state.json"
    assert bot_state_path() == tmp_path / "bot_state.json"
    assert Path.home() / ".acervator" not in sim_state_path().parents


def test_the_root_is_read_at_call_time_not_at_import_time(tmp_path, monkeypatch):
    """CONTROL: the binding moment, which is where the defect lived.

    A constant computed while the module is imported cannot be
    redirected by anything that runs afterwards -- and every fixture runs
    afterwards. Two different values inside ONE test can only agree if
    the environment is read on each call.
    """
    first = tmp_path / "one"
    second = tmp_path / "two"
    monkeypatch.setenv(SIM_STATE_ROOT_ENV, str(first))
    assert sim_state_path().parent == first
    monkeypatch.setenv(SIM_STATE_ROOT_ENV, str(second))
    assert sim_state_path().parent == second


def test_a_save_with_no_path_honours_the_override(tmp_path, monkeypatch):
    """CONTROL: the READ PATH, not just the resolver.

    `fleet_replay_panel` calls `save_sim_state(_state)` with no path.
    That call is the one that destroyed the operator's file, so the
    override has to reach THAT argument-free call, not merely a helper
    beside it.
    """
    monkeypatch.setenv(SIM_STATE_ROOT_ENV, str(tmp_path))
    out = save_sim_state(_doc({"simulated_a": ("BTC/USD", {})}))
    assert out == tmp_path / "simulator_bot_state.json"
    assert out.exists()
    assert load_sim_state()["bots"]["simulated_a"]["symbol"] == "BTC/USD"


def test_the_suite_wide_redirect_is_in_force():
    """CONTROL: a NEW test that forgets still cannot reach the folder.

    conftest sets the variable at import time for the whole session, so
    this holds for any test written later by anyone. No fixture is
    requested here on purpose -- this is what a forgetful test sees.
    """
    root = os.environ.get(SIM_STATE_ROOT_ENV)
    assert root, "conftest must set the sim-state root for the session"
    assert sim_state_path().parent == Path(root)
    assert sim_state_path().parent != Path.home() / ".acervator"


def test_conftest_uses_the_module_constant_by_name():
    """The conftest SETTER is locked to `SIM_STATE_ROOT_ENV`.

    conftest cannot import this module at collection time without
    pulling in the GUI package, so it spells the variable out. A rename
    must break a test here rather than silently un-redirect the suite --
    the same lock `test_crash_log_redirect.py` puts on the crash root.

    The `setdefault(` call is matched, not the bare name. A comment
    naming the variable is not a redirect; measured -- with the setter
    deleted and only the header comment left, a name-only check still
    passed.
    """
    text = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    assert f'setdefault("{SIM_STATE_ROOT_ENV}"' in text


def test_the_guard_still_refuses_the_live_fleet_file_under_a_redirect(
    tmp_path, monkeypatch
):
    """FALSIFIER KEPT: an override must not disarm the write guard.

    `test_save_refuses_the_live_bot_state_path` proves the guard refuses
    the fleet file under the ACTIVE root. This proves the redirect did
    not open a second door to the operator's real one.

    The refusal LIST is inspected. `save_sim_state` is NOT called with
    the live path: if the guard had regressed, a test that aimed a write
    at ~/.acervator/bot_state.json would destroy the operator's fleet to
    prove a point. Nothing here reads or writes that file.
    """
    import src.simulator.fleet.simulator_bot_state as sbs

    monkeypatch.setenv(SIM_STATE_ROOT_ENV, str(tmp_path))
    refused = sbs._refused_write_targets()
    assert tmp_path / "bot_state.json" in refused
    assert Path.home() / ".acervator" / "bot_state.json" in refused
