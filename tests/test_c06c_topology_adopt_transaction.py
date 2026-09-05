"""Adopting a topology must not misroute a wire, overwrite one silently, or lie.

``_Stub`` binds ``_topology_wire_collisions``, ``_wire_is_registered``,
``_snapshot_wires_for_adopt`` and ``_report_adopt_orphans`` off ``MainWindow`` and
runs them against a ``SmartWireManager`` and a fake bot manager. ``_AdoptStub``
adds ``_adopt_topology_proposal`` itself, with ``_create_bot`` standing in for the
Bot Wizard and ``_WireBus`` carrying ``wire.created`` into the engine. The ``adopt``
fixture replaces ``QMessageBox`` and roots every snapshot at ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.gui.main_window import MainWindow  # noqa: E402
from src.trading.smart_wire import SmartWireManager  # noqa: E402


class _FakeStateManager:
    def __init__(self, d):
        self._dir = d


class _FakeBotManager:
    def __init__(self, mgr, state_dir=None):
        self.smart_wire_manager = mgr
        self._state_manager = _FakeStateManager(state_dir) if state_dir else None
        self.bots: list[dict] = []

    def list_bots(self) -> list[dict]:
        """Return the roster ``_adopt_topology_proposal`` reads before and after
        each wizard run."""
        return list(self.bots)


class _Log:
    def __init__(self):
        self.entries = []

    def log(self, msg, level="info"):
        self.entries.append((level, msg))

    def text(self):
        return "\n".join(m for _, m in self.entries)


class _Stub:
    """Minimal stand-in for MainWindow: the helpers only touch
    _bot_manager and _status_log."""

    def __init__(self, mgr, state_dir=None):
        self._bot_manager = _FakeBotManager(mgr, state_dir)
        self._status_log = _Log()

    # Bind the real implementations under test.
    _wire_manager = MainWindow._wire_manager
    _wire_is_registered = MainWindow._wire_is_registered
    _topology_wire_collisions = MainWindow._topology_wire_collisions
    _snapshot_wires_for_adopt = MainWindow._snapshot_wires_for_adopt
    _report_adopt_orphans = MainWindow._report_adopt_orphans


@pytest.fixture
def mgr():
    return SmartWireManager()


# ---------------------------------------------------------------- 2 --
class TestOverwriteIsDisclosed:
    def test_a_fresh_wire_reports_no_replacement(self, mgr):
        res = mgr.register_wire("a", "b", 20.0)
        assert res["applied"] is True
        assert res["replaced_pct"] is None

    def test_an_overwrite_reports_the_prior_pct(self, mgr):
        """THE defect: this used to be indistinguishable from the case
        above."""
        mgr.register_wire("a", "b", 20.0)
        res = mgr.register_wire("a", "b", 50.0)
        assert res["applied"] is True
        assert res["replaced_pct"] == 20.0
        assert res["pct"] == 50.0

    def test_the_overwrite_still_happens(self, mgr):
        """Negative control. Disclosure must not have quietly turned
        into refusal -- that would change engine behaviour for every
        other caller."""
        mgr.register_wire("a", "b", 20.0)
        mgr.register_wire("a", "b", 50.0)
        assert mgr.get_outgoing_wires("a")["b"] == 50.0

    def test_a_refused_wire_is_still_refused(self, mgr):
        for bad in (0, -5, 101, "x", None):
            res = mgr.register_wire("a", "b", bad)
            assert res["applied"] is False, f"pct={bad!r} was accepted"


# ---------------------------------------------------------------- 1 --
class TestCollisionPreflight:
    def test_it_finds_an_existing_pair(self, mgr):
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = _Stub(mgr)
        got = stub._topology_wire_collisions(
            [{"source_asset": "ETH", "target_asset": "BTC", "pct": 50.0}],
            {"ETH": "bot_eth", "BTC": "bot_btc"},
        )
        assert len(got) == 1
        assert got[0]["current_pct"] == 20.0
        assert got[0]["proposed_pct"] == 50.0

    def test_it_reports_nothing_when_nothing_collides(self, mgr):
        """Positive control for the test above: if this returned a
        collision too, the finder would be matching everything."""
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = _Stub(mgr)
        got = stub._topology_wire_collisions(
            [{"source_asset": "SOL", "target_asset": "BTC", "pct": 50.0}],
            {"SOL": "bot_sol", "BTC": "bot_btc"},
        )
        assert got == []

    def test_a_new_bot_cannot_collide(self, mgr):
        """An unresolved asset has no bot yet, so it has no wires."""
        stub = _Stub(mgr)
        got = stub._topology_wire_collisions(
            [{"source_asset": "ETH", "target_asset": "BTC", "pct": 50.0}],
            {"BTC": "bot_btc"},
        )  # ETH not yet created
        assert got == []

    def test_it_never_raises_on_junk(self, mgr):
        """A pre-flight that can abort the adopt is worse than one that
        discloses nothing."""
        stub = _Stub(mgr)
        assert (
            stub._topology_wire_collisions(
                [None, {}, {"source_asset": object()}], {"A": "b"}
            )
            == []
        )

    def test_no_manager_means_no_claim(self):
        stub = _Stub(None)
        assert (
            stub._topology_wire_collisions(
                [{"source_asset": "ETH", "target_asset": "BTC", "pct": 5.0}],
                {"ETH": "e", "BTC": "b"},
            )
            == []
        )


# ---------------------------------------------------------------- 3 --
class TestEngineReadBack:
    def test_a_registered_wire_reads_back_true(self, mgr):
        mgr.register_wire("a", "b", 20.0)
        assert _Stub(mgr)._wire_is_registered("a", "b") is True

    def test_a_refused_wire_reads_back_false(self, mgr):
        """THE defect: the adopt counted this as drawn."""
        mgr.register_wire("a", "b", 999.0)  # refused
        assert _Stub(mgr)._wire_is_registered("a", "b") is False

    def test_unknown_is_not_reported_as_refused(self):
        """With no manager the caller is confirming an emit it already
        made; a missing engine is not evidence of rejection, and
        answering False would flag every healthy adopt as broken."""
        assert _Stub(None)._wire_is_registered("a", "b") is True


# ---------------------------------------------------------------- 4 --
class TestSnapshotAndOrphans:
    def test_the_snapshot_captures_the_pre_adopt_wires(self, mgr, tmp_path):
        mgr.register_wire("a", "b", 20.0)
        mgr.register_wire("b", "c", 30.0)
        stub = _Stub(mgr, state_dir=tmp_path)
        dest = stub._snapshot_wires_for_adopt("my topology")
        assert dest is not None and dest.exists()
        # Never the operator's tree.
        assert tmp_path in dest.parents
        body = json.loads(dest.read_text(encoding="utf-8"))
        assert body["title"] == "my topology"
        pairs = {(w["source_id"], w["target_id"], w["pct"]) for w in body["wires"]}
        assert pairs == {("a", "b", 20.0), ("b", "c", 30.0)}

    def test_snapshot_failure_does_not_raise(self, mgr):
        """It must never abort the adopt; it returns None instead."""
        stub = _Stub(mgr, state_dir=Path("\x00nonexistent"))
        assert stub._snapshot_wires_for_adopt("t") is None

    def test_orphans_are_named(self, mgr):
        stub = _Stub(mgr)
        stub._report_adopt_orphans(["abcdef1234", "ffff000011"])
        msg = stub._status_log.text()
        assert "abcdef12" in msg and "ffff0000" in msg
        assert "2 bot(s)" in msg

    def test_no_orphans_says_nothing(self, mgr):
        """Negative control: an adopt that created nothing must not
        report phantom leftovers."""
        stub = _Stub(mgr)
        stub._report_adopt_orphans([])
        assert stub._status_log.entries == []

    def test_the_report_removes_no_bot(self, mgr):
        """Destroying a bot the operator may have wanted is the worse failure, so
        ``_report_adopt_orphans`` leaves the roster it names untouched."""
        stub = _Stub(mgr)
        stub._bot_manager.bots = [{"bot_id": "abcdef1234"}, {"bot_id": "ffff000011"}]
        stub._report_adopt_orphans(["abcdef1234", "ffff000011"])
        assert [b["bot_id"] for b in stub._bot_manager.bots] == [
            "abcdef1234",
            "ffff000011",
        ]


# ------------------------------------------------------------ policy --


class _Spool:
    """Collects the toast ``_adopt_topology_proposal`` raises at the end."""

    def __init__(self):
        self.notices: list[tuple[str, str]] = []

    def notify(self, text, level="info"):
        """Record one toast."""
        self.notices.append((level, text))


class _WireBus:
    """A bus whose ``wire.created`` reaches ``SmartWireManager.register_wire``."""

    def __init__(self, mgr):
        self._mgr = mgr
        self.emitted: list[dict] = []

    def emit(self, topic, **payload):
        """Record a ``wire.created`` event and register it with the engine."""
        if topic != "wire.created":
            return
        self.emitted.append(dict(payload))
        self._mgr.register_wire(
            payload["source_id"], payload["target_id"], payload["pct"]
        )


class _AdoptStub(_Stub):
    """A ``_Stub`` that also runs the real ``_adopt_topology_proposal``.

    ``_create_bot`` appends the next entry of ``wizard_makes`` to the roster, and
    ``moments`` records the order the adopt reached each step in.
    """

    _adopt_topology_proposal = MainWindow._adopt_topology_proposal
    _report_adopt_orphans = MainWindow._report_adopt_orphans

    def __init__(self, mgr, state_dir, wizard_makes=()):
        assert state_dir is not None, (
            "_snapshot_wires_for_adopt falls back to ~/.acervator when the bot "
            "manager carries no state manager; every adopt run needs a tmp_path"
        )
        super().__init__(mgr, state_dir)
        self._bus = _WireBus(mgr)
        self._spool = _Spool()
        self.wizard_makes = list(wizard_makes)
        self.wizard_calls: list[dict] = []
        self.moments: list[str] = []
        self.question_text = ""

    def _create_bot(self, **wizard_kwargs):
        """Record ``wizard_kwargs`` and add the next ``wizard_makes`` entry."""
        self.moments.append("create_bot")
        self.wizard_calls.append(wizard_kwargs)
        if self.wizard_makes:
            self._bot_manager.bots.append(self.wizard_makes.pop(0))

    def _snapshot_wires_for_adopt(self, title):
        """Record the moment, then take the real snapshot."""
        self.moments.append("snapshot")
        return MainWindow._snapshot_wires_for_adopt(self, title)


@pytest.fixture
def adopt(mgr, tmp_path, monkeypatch):
    """Run the real ``_adopt_topology_proposal`` with ``QMessageBox`` replaced.

    ``tmp_path`` is the state root, so ``_snapshot_wires_for_adopt`` never reaches
    its ``_DEFAULT_DIR`` fallback under the operator's home.
    """
    from PySide6.QtWidgets import QMessageBox

    def _run(proposal, wizard_makes=(), answer_ok=True):
        stub = _AdoptStub(mgr, tmp_path, wizard_makes)

        def _question(_parent, _title, text, *_a, **_kw):
            stub.moments.append("confirm")
            stub.question_text = text
            return QMessageBox.Ok if answer_ok else QMessageBox.Cancel

        def _warning(_parent, _title, text, *_a, **_kw):
            stub.moments.append("warning")
            return QMessageBox.Ok

        monkeypatch.setattr(QMessageBox, "question", staticmethod(_question))
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))
        stub._adopt_topology_proposal(proposal)
        return stub

    return _run


ETH_TO_BTC = {
    "title": "eth to btc",
    "bots": [
        {"asset": "ETH", "existing_bot_id": "bot_eth"},
        {"asset": "BTC", "existing_bot_id": "bot_btc"},
    ],
    "wires": [{"source_asset": "ETH", "target_asset": "BTC", "pct": 50.0}],
}


class TestAdoptAppliesTheWholeTopology:
    """A wire pct is an ordinary user setting, so a colliding pair is applied and
    disclosed, never skipped."""

    def test_a_colliding_wire_is_applied_at_the_proposed_rate(self, mgr, adopt):
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = adopt(ETH_TO_BTC)
        assert stub._bus.emitted == [
            {"source_id": "bot_eth", "target_id": "bot_btc", "pct": 50.0}
        ]
        assert mgr.get_outgoing_wires("bot_eth")["bot_btc"] == 50.0

    def test_a_fresh_wire_is_applied_the_same_way(self, mgr, adopt):
        """Positive control: the collision is not what makes the wire land."""
        stub = adopt(ETH_TO_BTC)
        assert len(stub._bus.emitted) == 1
        assert mgr.get_outgoing_wires("bot_eth")["bot_btc"] == 50.0

    def test_the_operator_is_shown_the_old_and_new_rate(self, mgr, adopt):
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = adopt(ETH_TO_BTC)
        assert "ALREADY EXIST" in stub.question_text, stub.question_text
        assert "20.00% -> 50.00%" in stub.question_text, stub.question_text

    def test_a_fresh_wire_discloses_no_change(self, adopt):
        """Negative control: the disclosure appears only where a rate is
        replaced."""
        stub = adopt(ETH_TO_BTC)
        assert "ALREADY EXIST" not in stub.question_text, stub.question_text


class TestTheOrderIsDiscloseConfirmSnapshotApply:
    def test_the_snapshot_is_taken_after_the_confirm(self, mgr, adopt):
        """Disclosure, then the operator's answer, then the rollback file, then the
        wires; a snapshot taken first would record a state nobody had agreed to."""
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = adopt(ETH_TO_BTC)
        assert stub.moments == ["confirm", "snapshot"], stub.moments

    def test_a_cancel_snapshots_nothing_and_draws_nothing(self, mgr, adopt):
        """Positive control for the order above: nothing after the confirm runs
        when the operator answers Cancel."""
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = adopt(ETH_TO_BTC, answer_ok=False)
        assert stub.moments == ["confirm"], stub.moments
        assert stub._bus.emitted == []
        assert mgr.get_outgoing_wires("bot_eth")["bot_btc"] == 20.0

    def test_the_snapshot_file_holds_the_rate_the_adopt_replaced(
        self, mgr, adopt, tmp_path
    ):
        """The rollback path is a real file carrying the pre-adopt wires."""
        mgr.register_wire("bot_eth", "bot_btc", 20.0)
        stub = adopt(ETH_TO_BTC)
        saved = sorted((tmp_path / "topology_snapshots").glob("*.json"))
        assert len(saved) == 1, saved
        body = json.loads(saved[0].read_text(encoding="utf-8"))
        pairs = {(w["source_id"], w["target_id"], w["pct"]) for w in body["wires"]}
        assert pairs == {("bot_eth", "bot_btc", 20.0)}
        assert stub._bus.emitted, "the adopt stopped before drawing the wire"


NEW_ETH = {
    "title": "new eth bot",
    "bots": [
        {"asset": "ETH", "suggested_target_usd": 25.0},
        {"asset": "BTC", "existing_bot_id": "bot_btc"},
    ],
    "wires": [{"source_asset": "ETH", "target_asset": "BTC", "pct": 50.0}],
}


SOL_BOT = [{"bot_id": "made_sol", "symbol": "SOL/USD"}]
ETH_BOT = [{"bot_id": "made_eth", "symbol": "ETH/USD"}]


class TestTheNewBotsAssetIsValidatedBeforeItIsBound:
    def test_a_wrong_asset_draws_no_wire(self, mgr, adopt):
        """The wizard makes a SOL bot for an ETH proposal; binding it would route
        this topology's wires out of the wrong asset."""
        stub = adopt(NEW_ETH, wizard_makes=SOL_BOT)
        assert stub._bus.emitted == []
        assert mgr.get_outgoing_wires("made_sol") == {}
        assert "ABORTED" in stub._status_log.text()

    def test_the_matching_asset_is_bound_and_wired(self, adopt):
        """Positive control: the same run with an ETH bot draws the wire, so the
        refusal above is the guard and not a broken harness."""
        stub = adopt(NEW_ETH, wizard_makes=ETH_BOT)
        assert stub._bus.emitted == [
            {"source_id": "made_eth", "target_id": "bot_btc", "pct": 50.0}
        ]

    def test_the_wrongly_made_bot_is_named_and_left_in_place(self, adopt):
        stub = adopt(NEW_ETH, wizard_makes=SOL_BOT)
        assert "made_sol" in stub._status_log.text()
        assert [b["bot_id"] for b in stub._bot_manager.bots] == ["made_sol"]

    def test_a_cancelled_wizard_aborts_and_draws_nothing(self, adopt):
        """A wizard that creates no bot ends the adopt before any wire."""
        stub = adopt(NEW_ETH, wizard_makes=[])
        assert stub._bus.emitted == []
        assert "wizard cancelled" in stub._status_log.text()
