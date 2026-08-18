"""C06c: adopting a topology must not misroute, overwrite, or lie.

FOUR DEFECTS, ALL LIVE-MONEY

1. UNVALIDATED ASSET BINDING (the serious one)
   The adopt opens the Bot Wizard with ``exchange_id=""`` and only
   ``default_target_balance`` overridden -- the symbol is neither
   pre-filled nor constrained. Whatever bot came out was then bound to
   the proposal's asset with no check at all:

       asset_to_bot[asset] = sorted(new_ids)[0]

   So a proposal asking for an ETH bot, satisfied by an operator who
   created a SOL bot, would draw the proposal's ETH->BTC wire FROM the
   SOL bot. Fold profit then routes out of the wrong asset, permanently,
   and nothing downstream ever flags it.

2. SILENT OVERWRITE
   ``register_wire`` did ``setdefault(src, {})[tgt] = p`` and returned
   ``applied: True`` whether or not it had just replaced a hand-tuned
   percentage. The caller could not tell "new wire" from "destroyed the
   operator's 20% and put 50% there".

3. THE ENGINE'S REFUSAL WAS DISCARDED
   ``BotManager._on_wire_created_mgr`` threw the result away.
   ``register_wire`` refuses a pct that is non-numeric, <= 0, or > 100 --
   and every refusal was dropped, so the canvas drew a wire the engine
   never accepted. The adopt's "12/12 wires drawn" counted EMITS, not
   registrations, and could report a clean success for a topology the
   engine took none of.

4. NO SNAPSHOT, NO DISCLOSURE OF ORPHANS
   Nothing recorded the pre-adopt topology, and an abort at bot 4 of 6
   left bots 1-3 in place while saying only "aborted".

WHAT IS AND IS NOT TESTED HERE
The helpers are exercised directly against a fake bot manager rather
than through a constructed MainWindow -- the adopt itself needs a wizard,
a bus, and a live roster. That means these pins cover the collision
pre-flight, the read-back, the snapshot, and the orphan report, plus the
engine-level overwrite disclosure. The end-to-end wizard sequence is NOT
covered and still needs the operator's manual confirmation.
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
        self._state_manager = (
            _FakeStateManager(state_dir) if state_dir else None)


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
            {"ETH": "bot_eth", "BTC": "bot_btc"})
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
            {"SOL": "bot_sol", "BTC": "bot_btc"})
        assert got == []

    def test_a_new_bot_cannot_collide(self, mgr):
        """An unresolved asset has no bot yet, so it has no wires."""
        stub = _Stub(mgr)
        got = stub._topology_wire_collisions(
            [{"source_asset": "ETH", "target_asset": "BTC", "pct": 50.0}],
            {"BTC": "bot_btc"})          # ETH not yet created
        assert got == []

    def test_it_never_raises_on_junk(self, mgr):
        """A pre-flight that can abort the adopt is worse than one that
        discloses nothing."""
        stub = _Stub(mgr)
        assert stub._topology_wire_collisions(
            [None, {}, {"source_asset": object()}], {"A": "b"}) == []

    def test_no_manager_means_no_claim(self):
        stub = _Stub(None)
        assert stub._topology_wire_collisions(
            [{"source_asset": "ETH", "target_asset": "BTC", "pct": 5.0}],
            {"ETH": "e", "BTC": "b"}) == []


# ---------------------------------------------------------------- 3 --
class TestEngineReadBack:
    def test_a_registered_wire_reads_back_true(self, mgr):
        mgr.register_wire("a", "b", 20.0)
        assert _Stub(mgr)._wire_is_registered("a", "b") is True

    def test_a_refused_wire_reads_back_false(self, mgr):
        """THE defect: the adopt counted this as drawn."""
        mgr.register_wire("a", "b", 999.0)      # refused
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
        pairs = {(w["source_id"], w["target_id"], w["pct"])
                 for w in body["wires"]}
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

    def test_orphans_are_not_deleted(self, mgr):
        """Destroying a bot the operator may have wanted is a worse
        failure than leaving one. The report must not remove them."""
        import inspect
        src = inspect.getsource(MainWindow._report_adopt_orphans)
        assert "delete" not in src.lower().replace("deleted", "")


# ------------------------------------------------------------ policy --
class TestAdoptAppliesTheWholeTopology:
    """D23, ruled by the operator 2026-08-06: a wire pct is an ordinary
    user setting, adjustable whenever they like, so there was no
    permission question to ask. An earlier revision gated this behind a
    policy constant and skipped collisions, which produced a topology
    matching NEITHER the proposal nor the prior state -- adopt
    "AAA->BBB 25%" and silently keep 10%. What matters is disclosure
    plus a way back, both of which exist."""

    def test_no_policy_gate_remains(self):
        import inspect
        src = inspect.getsource(MainWindow._adopt_topology_proposal)
        assert "ADOPT_MAY_OVERWRITE" not in src, (
            "the adopt still branches on an overwrite policy; a pct is "
            "a user setting, not a permission")

    def test_colliding_pairs_are_not_skipped(self):
        """The whole proposal must be applied. A 'continue' that drops
        a disclosed pair is what this decision removed."""
        import inspect
        src = inspect.getsource(MainWindow._adopt_topology_proposal)
        assert "skip_pairs" not in src

    def test_the_change_is_disclosed_before_it_is_applied(self):
        """The whole ordering: disclose old -> new, ask, snapshot, then
        mutate. Matching on the CALL, not the name, since the rationale
        comment above also mentions the helper."""
        import inspect
        src = inspect.getsource(MainWindow._adopt_topology_proposal)
        assert "ALREADY EXIST" in src
        disclose = src.index("Adopting CHANGES them")
        confirm = src.index("QMessageBox.question")
        snapshot = src.index("self._snapshot_wires_for_adopt(")
        assert disclose < confirm < snapshot, (
            f"expected disclose < confirm < snapshot, got "
            f"{disclose} / {confirm} / {snapshot}")

    def test_a_rollback_path_exists(self):
        """Disclosure without recovery would just be a warning."""
        import inspect
        src = inspect.getsource(MainWindow._adopt_topology_proposal)
        assert "self._snapshot_wires_for_adopt(" in src

    def test_the_binding_is_validated_before_use(self):
        """Structural pin on defect 1 -- the misrouting guard must sit
        between the wizard and the asset_to_bot assignment."""
        import inspect
        src = inspect.getsource(MainWindow._adopt_topology_proposal)
        assert "made_base" in src
        assert src.index("made_base != asset") < src.index(
            "asset_to_bot[asset] = chosen")
