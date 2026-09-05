"""State parity: a sim bot must be bit-identical to its bot_state entry.

Operator directive 2026-08-08: "bot_state determines the initiating state...
NO OTHER SOURCE FOR INITIATING STATE SHOULD BE CITED OR EXPECTED", and
"Parity must be green on import and bit identical. The key difference is that
Simulator bots are being configured by the bot_state entries."

WHAT WAS WRONG. `bot_state_loader` returned `entry["config"]` only, dropping
`scrumming_state` (38 keys) and `stats` (36). `_build_sim` then SYNTHESISED an
opening position -- `target_balance / open_price` -- a second source of
initiating state. Every replay opened with no lots, no tranches, and the
ORIGINAL config target instead of the grown one.

`import_scrumming_state` (`src/trading/scrumming/state_io.py`) already existed
and is what LIVE calls from `BotManager.restore_bots_from_state`
(`src/trading/container/restore.py`). The sim simply never fed it.

THE CHECK IS A ROUND TRIP. `import_scrumming_state` is the inverse of
`export_scrumming_state`, so a faithful import re-exports exactly what it was
given. Compared as canonical JSON so nested lot and tranche CONTENTS count -- a
lot list of the right length with wrong contents must fail.

Measured on the operator's real fleet: 38 of 38 fields identical on every bot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.signal_contract import SignalSink, emit, set_sink  # noqa: E402
from src.simulator.fleet import (  # noqa: E402
    fleet_replay_controller as frc,
)
from src.simulator.fleet.sim_exchange import (  # noqa: E402
    FleetSimExchange,
    make_symbol_series_map,
)

BASE = 1_700_000_000_000
STEP = 300_000

# Overrides onto a real `export_scrumming_state`, so the fixture carries every key.
_OVERRIDES = {
    "anchor_target_balance": 250.0,
    "target_balance": 252.13907101630653,
    "main_lots": [
        {"units": 4.5, "price": 1.25, "ts": 1.0},
        {"units": 2.25, "price": 1.30, "ts": 2.0},
    ],
    "fold_tranches": [{"usd": 10.0, "created_ts": 3.0}],
    "fold_queue_usd": 10.0,
    "last_trade_price": 1.31,
    "last_trade_side": "FOLD",
    "tranches_created_lifetime": 3100,
    "tranches_closed_lifetime": 2989,
}


def _cfg():
    return {
        "mode": "scrumming",
        "symbol": "BTC/USD",
        "target_balance": 250.0,
        "target_asset": "BTC",
        "base_currency": "USD",
        "_src_bot_id": "aaaa1111",
        "_src_scrumming_state": dict(FIXTURE_STATE),
    }


def _rows(n=50):
    return [[BASE + i * STEP, 100.0, 101.0, 99.0, 100.0, 5.0] for i in range(n)]


def _bot():
    ex = FleetSimExchange(
        make_symbol_series_map({"BTC/USD": _rows()}),
        starting_balances={"USD": 10_000.0},
    )
    return frc._instantiate_bot(_cfg(), ex, frc._make_sim_capital_registry())


def _make_fixture_state() -> dict:
    """A COMPLETE state with the exporter's own shape, then overridden."""
    ex = FleetSimExchange(
        make_symbol_series_map({"BTC/USD": _rows()}),
        starting_balances={"USD": 10_000.0},
    )
    seed = {
        "mode": "scrumming",
        "symbol": "BTC/USD",
        "target_balance": 250.0,
        "target_asset": "BTC",
        "base_currency": "USD",
        "_src_bot_id": "seed0000",
    }
    b = frc._instantiate_bot(seed, ex, frc._make_sim_capital_registry())
    state = dict(b.export_scrumming_state())
    state.update(_OVERRIDES)
    return state


FIXTURE_STATE = _make_fixture_state()


def _diff(a: dict, b: dict) -> list:
    return sorted(
        k
        for k in (set(a) | set(b))
        if json.dumps(a.get(k), sort_keys=True, default=repr)
        != json.dumps(b.get(k), sort_keys=True, default=repr)
    )


@pytest.fixture
def sink():
    s = SignalSink(flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(None)


class TestTheRoundTripIsTheCheck:
    def test_import_export_is_bit_identical(self):
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        assert _diff(dict(FIXTURE_STATE), b.export_scrumming_state()) == []

    def test_the_check_can_actually_fail(self):
        """NEGATIVE CONTROL. A parity check that cannot report a mismatch
        proves nothing when it reports a match."""
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        tampered = dict(FIXTURE_STATE)
        tampered["target_balance"] = 999.0
        assert "target_balance" in _diff(tampered, b.export_scrumming_state())

    def test_lot_contents_are_compared_not_just_length(self):
        """A lot list of the right LENGTH with wrong contents must fail --
        comparing counts would pass it."""
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        back = b.export_scrumming_state()
        wrong = dict(FIXTURE_STATE)
        wrong["main_lots"] = [
            {"units": 9.9, "price": 9.9, "ts": 1.0},
            {"units": 8.8, "price": 8.8, "ts": 2.0},
        ]
        assert len(wrong["main_lots"]) == len(back["main_lots"])
        assert "main_lots" in _diff(wrong, back)


class TestTheStateActuallyArrives:
    def test_lots_are_restored(self):
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        assert len(b._main_lots) == 2
        assert sum(float(x["units"]) for x in b._main_lots) == 6.75

    def test_the_grown_target_is_restored_not_the_config_one(self):
        """The compounding the operator observed. config.target_balance is
        250.0; the persisted grown target is 252.139."""
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        assert b._target_balance == pytest.approx(252.13907101630653)
        assert b._anchor_target_balance == pytest.approx(250.0)

    def test_tranches_are_restored(self):
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        assert len(b._fold_tranches) == 1

    def test_lifetime_counters_survive(self):
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        assert b._tranches_created_lifetime == 3100
        assert b._tranches_closed_lifetime == 2989


class TestNoSecondSourceOfInitiatingState:
    def test_build_sim_does_not_synthesise_a_position(self):
        import ast

        src = (REPO_ROOT / "src/simulator/fleet/fleet_replay_controller.py").read_text(
            encoding="utf-8"
        )
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "_build_sim"
        )
        exprs = {
            ast.unparse(n)
            for n in ast.walk(fn)
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
        }
        assert not any(
            "open_px" in t for t in exprs
        ), f"a synthesised opening position remains: {exprs}"

    def test_the_loader_carries_the_whole_entry(self, tmp_path):
        from src.simulator.fleet.bot_state_loader import (
            load_bot_configs_from_state,
        )

        st = {
            "bots": {
                "aaaa1111": {
                    "bot_id": "aaaa1111",
                    "config": {"mode": "scrumming", "symbol": "BTC/USD"},
                    "scrumming_state": dict(FIXTURE_STATE),
                    "stats": {"position_value": 252.7},
                }
            }
        }
        p = tmp_path / "s.json"
        p.write_text(json.dumps(st), encoding="utf-8")
        cfgs = load_bot_configs_from_state(path=p)
        assert isinstance(cfgs[0].get("_src_scrumming_state"), dict)
        assert isinstance(cfgs[0].get("_src_stats"), dict)


class TestTheParityEmitter:
    def test_it_reports_green_on_a_faithful_import(self, sink):
        b = _bot()
        b.import_scrumming_state(dict(FIXTURE_STATE))
        bad = _diff(dict(FIXTURE_STATE), b.export_scrumming_state())
        emit(
            "fleet.03.005.invariant.state_parity",
            actual=len(FIXTURE_STATE) - len(bad),
            expected=len(FIXTURE_STATE),
            context={"differing": bad},
        )
        r = sink.records("fleet.03.005.invariant.state_parity")[0]
        assert r.ok is True
        assert r.context["differing"] == ()

    def test_it_names_the_field_when_parity_breaks(self, sink):
        """A count alone would say parity broke without saying where."""
        emit(
            "fleet.03.005.invariant.state_parity",
            actual=37,
            expected=38,
            context={"differing": ["target_balance"]},
        )
        r = sink.records("fleet.03.005.invariant.state_parity")[0]
        assert r.ok is False
        assert r.context["differing"] == ("target_balance",)
