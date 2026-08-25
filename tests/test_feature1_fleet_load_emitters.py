"""FEATURE 1 — "Loads bot_state fleet as sim bots."

Operator directive, with its qualifier: "The ONLY source beyond the user adding
new bots manually must be a fleet load that references bot_state and ALL PIECES
/ FUNCTIONS of the fleet must import."

WHAT EXISTED BEFORE: `meta.json` `config.bots` — a COUNT. A count cannot
evidence WHICH bots loaded, whether their ids mirror live, or which sections of
each bot_state entry the loader has no carry for.

10.4 — THE SECTION COUNT ABOVE WAS STALE AND IS CORRECTED. It used to read
"5 sections drop whole (`stats` 36 keys, `scrumming_state` 38 keys, ...)".
v3.24.81 added carries for both, under `_src_scrumming_state` and `_src_stats`,
and the claim was never updated — in this docstring or in the pin's own
`dropped` context. What the loader genuinely has no carry for is
`phantom_config`, `phantoms_enabled`, `saved_at` and `state_when_saved`.

These tests RETRIEVE emitter data. They do not re-implement the check — they
read what the emitter recorded, which is the point of the emitter existing.
Retrieved records are frozen; nothing here can mutate them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.signal_contract import SignalSink, set_sink  # noqa: E402
from src.gui.simulator_tab.fleet.bot_state_loader import (  # noqa: E402
    load_bot_configs_from_state,
    load_smart_wires_from_state,
)

# TEST FIXTURE state — synthetic, never the operator's file.
FIXTURE = {
    "bots": {
        "aaaa1111": {
            "bot_id": "aaaa1111",
            "config": {"mode": "scrumming", "symbol": "BTC/USD"},
            "stats": {"position_value": 1.0},
            "scrumming_state": {"target_balance": 252.1},
            "saved_at": 1.0,
            "state_when_saved": "running",
            "phantoms_enabled": False,
        },
        "bbbb2222": {
            "bot_id": "bbbb2222",
            "config": {"mode": "scrumming", "symbol": "ETH/USD"},
            "stats": {"position_value": 2.0},
            "scrumming_state": {"target_balance": 101.5},
            "saved_at": 1.0,
            "state_when_saved": "running",
            "phantoms_enabled": False,
        },
        "cccc3333": {
            "bot_id": "cccc3333",
            "config": {"mode": "extractor", "symbol": "SOL/USD"},
        },
    },
    "smart_wires": [
        {"source_id": "aaaa1111", "target_id": "bbbb2222", "pct": 20.0},
        {"source_id": "bbbb2222", "target_id": "aaaa1111", "pct": 10.0},
        "not-a-dict",
    ],
}


@pytest.fixture
def sink():
    s = SignalSink(flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(None)


@pytest.fixture
def state_file(tmp_path):
    import json

    p = tmp_path / "bot_state.json"
    p.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return p


class TestTheEmittersFireAtAll:
    """POSITIVE CONTROL. Every assertion below is vacuous if the loader
    emits nothing — which is exactly the state this feature was in."""

    def test_loading_a_fleet_emits(self, sink, state_file):
        load_bot_configs_from_state(path=state_file)
        assert sink.names(), "the fleet load recorded nothing at all"

    def test_the_declared_signals_are_present(self, sink, state_file):
        load_bot_configs_from_state(path=state_file)
        load_smart_wires_from_state(path=state_file)
        for name in (
            "fleet.03.001.postcondition.bots_loaded",
            "fleet.03.002.invariant.bot_ids_mirror_live",
            "fleet.03.003.invariant.sections_imported",
            "fleet.03.004.postcondition.wires_loaded",
        ):
            assert sink.count(name) == 1, f"{name} did not fire exactly once"


class TestEachRecordCarriesTheContract:
    """name / location / expected / actual — the operator's four."""

    def test_bots_loaded_carries_expected_and_actual(self, sink, state_file):
        load_bot_configs_from_state(path=state_file)
        r = sink.records("fleet.03.001.postcondition.bots_loaded")[0]
        assert r.expected == 2  # two scrumming bots in the fixture
        assert r.actual == 2
        assert r.ok is True
        assert r.site.startswith("bot_state_loader.py:")

    def test_wires_loaded_carries_expected_and_actual(self, sink, state_file):
        load_smart_wires_from_state(path=state_file)
        r = sink.records("fleet.03.004.postcondition.wires_loaded")[0]
        assert r.expected == 3  # 3 rows persisted...
        assert r.actual == 2  # ...2 well-formed
        assert r.ok is False, "a dropped wire row must not read as success"


class TestItRecordsTheAllPiecesGap:
    """The qualifier the old count could not evidence."""

    def test_dropped_sections_are_the_ones_genuinely_dropped(self, sink, state_file):
        """10.4 (F3) - THE `dropped` LIST WAS WRONG, AND IT MATTERED.

        It named `stats` and `scrumming_state`. Both are carried, thirty
        lines above the emitter, as `_src_scrumming_state` and
        `_src_stats`. A reader trusting this record would go looking for
        an import bug that does not exist, while the sections the loader
        really has no carry for went unnamed.

        IF THIS FAILS: the register and the record disagree about what
        the sim starts from, and neither can be trusted about the other.
        """
        out = load_bot_configs_from_state(path=state_file)
        r = sink.records("fleet.03.003.invariant.sections_imported")[0]
        dropped = set(r.context["dropped"])
        assert dropped == {
            "saved_at",
            "state_when_saved",
            "phantoms_enabled",
        }, f"the loader has no carry for exactly these; got {dropped}"
        assert not dropped & {
            "stats",
            "scrumming_state",
        }, "both are carried and must not be reported as dropped"
        # checked against the PRODUCT, not only the context.
        assert "_src_scrumming_state" in out[0]
        assert "_src_stats" in out[0]

    def test_a_complete_import_reads_as_a_pass(self, sink, state_file):
        """Both fixture scrumming bots supply all four carried sections
        and all four land, so this fixture IS a complete import.

        The old test asserted ok is False here, on the reasoning that
        "all pieces import is false today". That stopped being true in
        v3.24.81 and the assertion outlived it.
        """
        load_bot_configs_from_state(path=state_file)
        r = sink.records("fleet.03.003.invariant.sections_imported")[0]
        assert r.ok is True, f"nothing was lost here; context={r.context}"
        assert r.actual == 8  # 2 eligible bots x 4 carries
        assert r.expected == 8
        assert r.context["missing_total"] == 0

    def test_an_incomplete_import_is_marked_failing(self, sink, tmp_path):
        """THE FAILING SIDE, which the invariant above needs to mean
        anything. A `stats` section present but not a dict is skipped by
        the loader's own guard and vanishes without a word."""
        import copy
        import json as _json

        broken = copy.deepcopy(FIXTURE)
        broken["bots"]["bbbb2222"]["stats"] = "not-a-dict"
        path = tmp_path / "bot_state.json"
        path.write_text(_json.dumps(broken), encoding="utf-8")
        load_bot_configs_from_state(path=path)
        r = sink.records("fleet.03.003.invariant.sections_imported")[0]
        assert r.ok is False, "a section that vanished must not read as a pass"
        assert r.actual == 7
        assert r.expected == 8
        assert tuple(r.context["missing"]) == ("bbbb2222.stats",)


class TestBotIdTraceability:
    """'sim_bot_id and paper_bot_id should mirror live bot IDs so that
    everything is traceable.'"""

    def test_the_ids_are_recorded_not_just_counted(self, sink, state_file):
        load_bot_configs_from_state(path=state_file)
        r = sink.records("fleet.03.002.invariant.bot_ids_mirror_live")[0]
        assert r.actual == ("aaaa1111", "bbbb2222")  # frozen
        assert r.ok is True

    def test_a_mismatch_would_be_caught(self, sink, tmp_path):
        """NEGATIVE CONTROL — the emitter must be able to FAIL. An emitter
        that cannot report a mismatch proves nothing when it reports a
        match."""
        import json

        bad = {
            "bots": {
                "zzzz9999": {"bot_id": "DIFFERENT", "config": {"mode": "scrumming"}}
            }
        }
        p = tmp_path / "s.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        load_bot_configs_from_state(path=p)
        r = sink.records("fleet.03.002.invariant.bot_ids_mirror_live")[0]
        # _src_bot_id is stamped from the MAP KEY, which is the live id
        assert r.actual == ("zzzz9999",)
        assert r.expected == ("zzzz9999",)


class TestRetrievedDataIsNotMutable:
    def test_records_are_frozen(self, sink, state_file):
        load_bot_configs_from_state(path=state_file)
        r = sink.records("fleet.03.001.postcondition.bots_loaded")[0]
        with pytest.raises(Exception):
            r.actual = 999

    def test_retrieval_is_a_tuple(self, sink, state_file):
        load_bot_configs_from_state(path=state_file)
        assert isinstance(sink.records("fleet.03.001.postcondition.bots_loaded"), tuple)


class TestTheEmittersCostNothingWhenUncollected:
    """Instrumentation on a load path must not require a sink."""

    def test_loading_without_a_sink_works(self, state_file):
        set_sink(None)
        cfgs = load_bot_configs_from_state(path=state_file)
        assert len(cfgs) == 2
