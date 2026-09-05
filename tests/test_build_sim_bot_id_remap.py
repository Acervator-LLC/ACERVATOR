"""Sim bots must carry the PERSISTED bot id, not a fresh uuid4 (C20).

WHY THIS IS THE FIRST STEP OF THE WIRE WORK, NOT PART OF IT.

`ScrummingBot.__init__` mints `str(uuid.uuid4())[:8]`
(bot_container.py:881) and nothing overrides it on the sim path. The
persisted per-bot `config` carries no `bot_id` at all — 0 of 35 verified —
so the sim fleet has always run under ids that exist nowhere else.

Smart Wires are keyed by the persisted id. `get_outgoing_wires(source_id)`
looks up `self._wires.get(source_id, {})` (smart_wire.py:344-346) and
`distribute_fold_profit` is called with `source_id=self.bot_id`
(`src/trading/smart_wire.py`). Import 40 wires keyed by live ids, register 40
bots keyed by uuid4s, and the two never meet: `import_wires` does no
existence check (smart_wire.py:456-478), so it cheerfully reports 40 while
`_route_scrum_proceeds_via_wires` takes its early return
(scrumming_bot.py:1788-1789) on every single scrum.

That is why this lands BEFORE the manager exists. Done afterwards, a green
"40 wires imported" log sits on top of a harness routing $0.00, and the
cascade's own exit criterion passes while the feature does nothing.

THE JOIN KEY ALREADY EXISTED AND WAS READ BY NOTHING.
`bot_state_loader.py:86` stamps `cfg_copy.setdefault("_src_bot_id", ...)`.
Grep of src/ found exactly one other occurrence: a comment. It is also
excluded from the dropped-keys debug log by the underscore filter at
fleet_replay_controller.py:304-306, so its uselessness was invisible.

Live's own restore is the mechanism being mirrored here, not a new
invention: `BotManager.restore_bots_from_state` in
`src/trading/container/restore.py`, `# Preserve original bot ID` /
`bot.bot_id = bid`, which is precisely why live's `import_wires` works.

SCOPE. This file pins the id only. Whether wires actually route is a
separate question with its own test, because an id that matches proves
nothing about money moving.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.simulator.fleet.fleet_replay_controller import (  # noqa: E501
    live_bot_id,
    sim_bot_id,  # noqa: E402
    FleetReplayController,
)

STEP = 300_000
BASE = 1_700_000_000_000


def _candles(n=8, px=100.0):
    return [[BASE + i * STEP, px, px * 1.01, px * 0.99, px, 10.0] for i in range(n)]


def _cfg(symbol, src_id, target=100.0):
    return {
        "mode": "scrumming",
        "symbol": symbol,
        "target_balance": target,
        "target_asset": symbol.split("/")[0],
        "base_currency": symbol.split("/")[1],
        "_src_bot_id": src_id,
    }


def _built(configs, symbols=None, acts=None):
    ctl = FleetReplayController(
        configs=configs,
        candles_by_symbol={
            s: _candles() for s in (symbols or [c["symbol"] for c in configs])
        },
        activity_log_cb=(acts.append if acts is not None else None),
    )
    ctl._build_sim()
    return ctl


class TestTheInstrumentWorks:
    def test_bots_are_actually_constructed(self):
        """POSITIVE CONTROL. Every id assertion below is vacuous on an
        empty fleet, and `_build_sim` returns early in several ways."""
        ctl = _built([_cfg("BTC/USD", "aaaa1111"), _cfg("ETH/USD", "bbbb2222")])
        assert len(ctl._bots) == 2


class TestTheIdIsThePersistedOne:
    def test_every_sim_bot_carries_its_persisted_id(self):
        ctl = _built(
            [
                _cfg("BTC/USD", "aaaa1111"),
                _cfg("ETH/USD", "bbbb2222"),
                _cfg("SOL/USD", "cccc3333"),
            ]
        )
        assert {live_bot_id(b.bot_id) for b in ctl._bots} == {
            "aaaa1111",
            "bbbb2222",
            "cccc3333",
        }

    def test_the_id_is_not_a_fresh_uuid(self):
        """The discriminating assertion. A uuid4 hex slice is 8 chars of
        [0-9a-f] — so is 'aaaa1111'. Comparing shape would pass on the
        unfixed baseline; only comparing the VALUE catches it."""
        ctl = _built([_cfg("BTC/USD", "deadbeef")])
        assert ctl._bots[0].bot_id == sim_bot_id("deadbeef")
        assert live_bot_id(ctl._bots[0].bot_id) == "deadbeef"

    def test_ids_stay_distinct_across_the_fleet(self):
        configs = [_cfg(f"SYM{i}/USD", f"bot{i:05d}") for i in range(12)]
        ctl = _built(configs)
        ids = [b.bot_id for b in ctl._bots]
        assert len(set(ids)) == len(ids) == 12
        assert all(i.startswith("simulated_") for i in ids)

    def test_a_bot_without_a_tablet_does_not_consume_an_id(self):
        """Partial fleets are normal — only symbols with a Stone Tablet
        spawn. The ids must follow the bots that exist, not the configs."""
        ctl = FleetReplayController(
            configs=[_cfg("BTC/USD", "aaaa1111"), _cfg("NOTAPE/USD", "bbbb2222")],
            candles_by_symbol={"BTC/USD": _candles()},
        )
        ctl._build_sim()
        assert {live_bot_id(b.bot_id) for b in ctl._bots} == {"aaaa1111"}


class TestSyntheticFleetsAreLegITIMATEAndKeepTheirUuids:
    """CORRECTED DESIGN — recorded because the first version of this file
    asserted the opposite and was wrong.

    The first draft raised whenever `_src_bot_id` was absent from a
    config. That broke 8 existing tests, and chasing the breakage found
    the real reason: `topology_stress._config_for` builds configs
    from PROPOSAL bot entries — hypothetical bots that do not exist in
    bot_state and never will. There is no persisted id to carry and
    nothing to join to. Raising there would have broken the Nuclear
    topology stress backtester at runtime.

    That is the same defect C18 shipped: a precondition hand-built
    configs cannot satisfy, which breaks the caller instead of the bug.

    So the check moved from the CONFIG to the FLEET. A fleet with no
    persisted ids anywhere is synthetic and legitimate. A fleet where
    SOME configs carry the key and others do not cannot be anything but
    a broken join, and that is what raises.
    """

    def test_a_fleet_with_no_persisted_ids_keeps_uuids(self):
        cfg = _cfg("BTC/USD", "aaaa1111")
        del cfg["_src_bot_id"]
        ctl = _built([cfg])
        assert len(ctl._bots) == 1
        assert ctl._bots[0].bot_id  # a uuid4, not empty
        assert live_bot_id(ctl._bots[0].bot_id) != "aaaa1111"

    def test_a_synthetic_fleet_says_so_rather_than_going_quiet(self):
        """Silence is what let the id mismatch survive the whole life of
        the harness. A synthetic fleet is fine; an UNANNOUNCED one is
        how a bot_state replay that lost its key reads as normal."""
        cfg = _cfg("BTC/USD", "aaaa1111")
        del cfg["_src_bot_id"]
        acts: list[str] = []
        _built([cfg], acts=acts)
        assert any("SYNTHETIC" in a for a in acts), acts

    def test_a_joined_fleet_says_so_too(self):
        acts: list[str] = []
        _built([_cfg("BTC/USD", "aaaa1111")], acts=acts)
        assert any("joined to bot_state" in a for a in acts), acts


class TestAPartialJoinFailsLoudly:
    """The case that cannot be anything but a defect."""

    def test_a_fleet_with_some_ids_missing_raises(self):
        good = _cfg("BTC/USD", "aaaa1111")
        bad = _cfg("ETH/USD", "bbbb2222")
        del bad["_src_bot_id"]
        with pytest.raises(KeyError, match="_src_bot_id"):
            _built([good, bad])

    def test_an_empty_id_among_populated_ones_raises(self):
        with pytest.raises(KeyError, match="_src_bot_id"):
            _built([_cfg("BTC/USD", "aaaa1111"), _cfg("ETH/USD", "")])

    def test_the_error_names_the_symbol_and_the_ratio(self):
        """A bare KeyError across a 35-bot fleet says nothing about which
        config is malformed, nor how bad the split is."""
        good = _cfg("BTC/USD", "aaaa1111")
        bad = _cfg("PENGU/USD", "bbbb2222")
        del bad["_src_bot_id"]
        with pytest.raises(KeyError, match="PENGU/USD"):
            _built([good, bad])
        with pytest.raises(KeyError, match="1 of 2"):
            _built([good, dict(bad)])


class TestTheLoaderStillSuppliesTheKey:
    """The remap is only as good as its source. If `bot_state_loader`
    ever stops stamping the key, every replay starts raising — which is
    the intended failure, but this test says WHY."""

    @staticmethod
    def _state_file(tmp_path, bots):
        """A throwaway bot_state.json. NEVER points at ~/.acervator —
        the operator's live state is read-only to this suite."""
        p = tmp_path / "bot_state.json"
        p.write_text(json.dumps({"bots": bots}), encoding="utf-8")
        return p

    def test_the_loader_stamps_src_bot_id(self, tmp_path):
        from src.simulator.fleet.bot_state_loader import (
            load_bot_configs_from_state,
        )

        p = self._state_file(
            tmp_path,
            {
                "abc12345": {"config": {"mode": "scrumming", "symbol": "BTC/USD"}},
                "def67890": {"config": {"mode": "scrumming", "symbol": "ETH/USD"}},
            },
        )
        out = load_bot_configs_from_state(p, mode_filter="scrumming")
        assert {c["_src_bot_id"] for c in out} == {"abc12345", "def67890"}

    def test_the_loader_does_not_overwrite_an_existing_key(self, tmp_path):
        """`setdefault`, not `[...] =` — pinned because a caller may
        already have joined the id in."""
        from src.simulator.fleet.bot_state_loader import (
            load_bot_configs_from_state,
        )

        p = self._state_file(
            tmp_path,
            {
                "abc12345": {
                    "config": {
                        "mode": "scrumming",
                        "symbol": "BTC/USD",
                        "_src_bot_id": "preset99",
                    }
                }
            },
        )
        out = load_bot_configs_from_state(p, mode_filter="scrumming")
        assert out[0]["_src_bot_id"] == "preset99"

    def test_the_key_survives_into_what_build_sim_iterates(self, tmp_path):
        """The join has two hops and the second is easy to lose: the
        BotConfig passthrough filter at fleet_replay_controller.py:257-261
        keeps only BotConfig fields, and `_src_bot_id` is not one. It
        survives because `_build_sim` iterates the RAW dicts, not the
        typed configs. Pinned so a future tidy-up cannot quietly break it.
        """
        from src.simulator.fleet.bot_state_loader import (
            load_bot_configs_from_state,
        )

        p = self._state_file(
            tmp_path,
            {
                "abc12345": {
                    "config": {
                        "mode": "scrumming",
                        "symbol": "BTC/USD",
                        "target_balance": 100.0,
                        "target_asset": "BTC",
                        "base_currency": "USD",
                    }
                }
            },
        )
        cfgs = load_bot_configs_from_state(p, mode_filter="scrumming")
        ctl = FleetReplayController(
            configs=cfgs, candles_by_symbol={"BTC/USD": _candles()}
        )
        ctl._build_sim()
        assert [b.bot_id for b in ctl._bots] == [sim_bot_id("abc12345")]
        assert [live_bot_id(b.bot_id) for b in ctl._bots] == ["abc12345"]
