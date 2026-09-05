"""v3.23.68 — pin tests for market_inspector_topologies GUI surface.

Covers tests 10 + 12 from design doc § 8:
  10. TopologyPreviewDialog blocks Adopt when force_adopt_disabled
  12. dismiss suppresses proposal for 24 h; expiry sweep restores

Headless Qt (offscreen) — mirrors the pattern used across the
existing Qt pin-test files in this repo.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui.market_inspector_topologies import (  # noqa: E402
    MarketInspectorTopologies,
    TopologyPreviewDialog,
    DISMISS_TTL_SECONDS,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _make_proposal(pid: str = "test:AAA-BBB"):
    return {
        "id": pid,
        "archetype": "mean_reversion_pair",
        "title": "Mean-rev pair: AAA ↔ BBB",
        "created_ts": time.time(),
        "score": 82.0,
        "assets": ["AAA", "BBB"],
        "bots": [
            {
                "asset": "AAA",
                "quote": "USD",
                "symbol": "AAA/USD",
                "existing_bot_id": "",
                "role": "peer_a",
                "suggested_target_usd": 25.0,
            },
            {
                "asset": "BBB",
                "quote": "USD",
                "symbol": "BBB/USD",
                "existing_bot_id": "bot-42",
                "role": "peer_b",
                "suggested_target_usd": 100.0,
            },
        ],
        "wires": [
            {
                "source_asset": "AAA",
                "target_asset": "BBB",
                "pct": 25.0,
                "rationale": "anti-corr",
            },
            {
                "source_asset": "BBB",
                "target_asset": "AAA",
                "pct": 25.0,
                "rationale": "anti-corr",
            },
        ],
        "adopt_notes": ["Bidirectional 25% wires."],
    }


# ---- Test 10: Adopt blocked when force_adopt_disabled -------------------- #


def test_dialog_blocks_adopt_when_disabled(qapp):
    p = _make_proposal()
    dlg = TopologyPreviewDialog(p, force_adopt_disabled=True)
    assert dlg._adopt_btn.isEnabled() is False
    # Cancel button remains default and enabled
    assert dlg._cancel_btn.isEnabled() is True
    assert dlg._cancel_btn.isDefault() is True
    dlg.deleteLater()


def test_dialog_enables_adopt_when_flag_off(qapp):
    p = _make_proposal()
    dlg = TopologyPreviewDialog(p, force_adopt_disabled=False)
    assert dlg._adopt_btn.isEnabled() is True
    dlg.deleteLater()


def test_dialog_adopt_click_emits_proposal(qapp):
    p = _make_proposal("test:XYZ")
    dlg = TopologyPreviewDialog(p, force_adopt_disabled=False)
    captured = []
    dlg.adoptClicked.connect(lambda payload: captured.append(payload))
    dlg._on_adopt()
    assert len(captured) == 1
    assert captured[0]["id"] == "test:XYZ"
    dlg.deleteLater()


# ---- Test 12: dismiss suppresses for 24 h ------------------------------- #


def test_dismiss_suppresses_proposal(qapp):
    w = MarketInspectorTopologies()
    p = _make_proposal("test:DISM")
    w.set_proposal_source(lambda: [p])
    w.refresh()
    assert any(pp["id"] == "test:DISM" for pp in w._proposals)
    w.dismiss("test:DISM")
    assert w.is_dismissed("test:DISM") is True
    # A subsequent refresh must NOT re-render the dismissed proposal
    w.refresh()
    assert not any(pp["id"] == "test:DISM" for pp in w._proposals)
    w.deleteLater()


def test_dismiss_expires_after_ttl(qapp):
    w = MarketInspectorTopologies()
    now = 1_000_000.0
    w.dismiss("test:EXP", now=now)
    # Right before expiry -> still dismissed
    assert w.is_dismissed("test:EXP", now=now + DISMISS_TTL_SECONDS - 1) is True
    # After expiry -> no longer dismissed
    assert w.is_dismissed("test:EXP", now=now + DISMISS_TTL_SECONDS + 1) is False
    w.deleteLater()


def test_empty_source_shows_placeholder(qapp):
    w = MarketInspectorTopologies()
    w.set_proposal_source(lambda: [])
    w.refresh()
    assert w._proposals == []
    w.deleteLater()


def test_refresh_swallows_source_exception(qapp):
    w = MarketInspectorTopologies()

    def bad():
        raise RuntimeError("boom")

    w.set_proposal_source(bad)
    # Must not raise
    w.refresh()
    assert "Detector error" in w._status_lbl.text()
    w.deleteLater()


# ---- Test 11 (v3.23.69): adopt-live wiring ----------------------------- #


def _bind_adopt_helpers(fake):
    """Give a SimpleNamespace fake the sibling methods the orchestrator
    calls on ``self``.

    v3.24.37 (C06c) added a collision pre-flight, a wire snapshot, an
    engine read-back and an orphan report to ``_adopt_topology_proposal``.
    These tests bind the real orchestrator to a bare fake, so the fake
    has to carry the same surface -- exactly as it already does for
    ``_create_bot``. No assertion below changes.

    With a FakeBotMgr that has no ``smart_wire_manager``, every one of
    these degrades to its no-information answer (no collisions, no
    snapshot, read-back True), so the orchestrator behaves as it did
    before the helpers existed and these tests measure what they always
    measured.
    """
    from types import MethodType

    import src.gui.main_window as mw

    for name in (
        "_wire_manager",
        "_wire_is_registered",
        "_topology_wire_collisions",
        "_snapshot_wires_for_adopt",
        "_report_adopt_orphans",
    ):
        setattr(fake, name, MethodType(mw.MainWindow.__dict__[name], fake))


def test_adopt_button_enabled_by_default_v3_23_69(qapp):
    """Adopt was gated in v3.23.68; v3.23.69 flips the default to
    ENABLED so operator-facing preview modals can adopt live."""
    p = _make_proposal()
    dlg = TopologyPreviewDialog(p)  # default force_adopt_disabled
    assert dlg._adopt_btn.isEnabled() is True
    dlg.deleteLater()


def test_orchestrator_emits_wire_created_per_wire(qapp, monkeypatch):
    """v3.23.69 pin test 11 — on adopt confirm, the orchestrator
    emits ``wire.created`` on the bus once per proposal wire, with
    the resolved source/target bot_ids and the proposal pct.

    We reuse only the orchestrator method itself, bound to a bare
    fake object that supplies the attributes it reads. This avoids
    booting the entire main window (dozens of subsystems) while still
    exercising the real code path.
    """
    from types import MethodType, SimpleNamespace

    # Load the real orchestrator function from the module.
    import src.gui.main_window as mw

    orchestrator = mw.MainWindow.__dict__["_adopt_topology_proposal"]

    # Fake QMessageBox.question so the confirm prompt returns "Ok".
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Ok)

    emissions = []

    class FakeBus:
        def emit(self, event, **kwargs):
            emissions.append((event, kwargs))

    class FakeBotMgr:
        def list_bots(self):
            return [
                {
                    "bot_id": "bot-A",
                    "symbol": "AAA/USD",
                    "target_balance": 25.0,
                    "stats": {"position_value": 0.0},
                },
                {
                    "bot_id": "bot-B",
                    "symbol": "BBB/USD",
                    "target_balance": 25.0,
                    "stats": {"position_value": 0.0},
                },
            ]

    fake = SimpleNamespace()
    fake._bot_manager = FakeBotMgr()
    fake._bus = FakeBus()
    fake._status_log = SimpleNamespace(log=lambda *a, **kw: None)
    fake._spool = SimpleNamespace(notify=lambda *a, **kw: None)
    fake._create_bot = MethodType(lambda self, **kw: None, fake)
    _bind_adopt_helpers(fake)

    proposal = {
        "id": "test:orch",
        "archetype": "mean_reversion_pair",
        "title": "orchestrator test",
        "created_ts": 0.0,
        "score": 90.0,
        "assets": ["AAA", "BBB"],
        "bots": [
            {
                "asset": "AAA",
                "quote": "USD",
                "symbol": "AAA/USD",
                "existing_bot_id": "bot-A",
                "role": "peer_a",
                "suggested_target_usd": 25.0,
            },
            {
                "asset": "BBB",
                "quote": "USD",
                "symbol": "BBB/USD",
                "existing_bot_id": "bot-B",
                "role": "peer_b",
                "suggested_target_usd": 25.0,
            },
        ],
        "wires": [
            {
                "source_asset": "AAA",
                "target_asset": "BBB",
                "pct": 25.0,
                "rationale": "x",
            },
            {
                "source_asset": "BBB",
                "target_asset": "AAA",
                "pct": 25.0,
                "rationale": "y",
            },
        ],
        "adopt_notes": [],
    }
    # Both bots exist → no wizard invocations required.
    orchestrator(fake, proposal)
    events = [e for e in emissions if e[0] == "wire.created"]
    assert len(events) == 2
    payloads = [e[1] for e in events]
    assert {"bot-A", "bot-B"} == {p["source_id"] for p in payloads}
    assert {"bot-A", "bot-B"} == {p["target_id"] for p in payloads}
    assert all(p["pct"] == 25.0 for p in payloads)


def test_orchestrator_aborts_on_confirm_cancel(qapp, monkeypatch):
    """Cancel at the confirm gate → no wire.created emitted, no
    _create_bot called."""
    from types import MethodType, SimpleNamespace
    import src.gui.main_window as mw

    orchestrator = mw.MainWindow.__dict__["_adopt_topology_proposal"]

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Cancel)

    emissions = []
    create_calls = []

    class FakeBus:
        def emit(self, event, **kwargs):
            emissions.append((event, kwargs))

    class FakeBotMgr:
        def list_bots(self):
            return []

    fake = SimpleNamespace()
    fake._bot_manager = FakeBotMgr()
    fake._bus = FakeBus()
    fake._status_log = SimpleNamespace(log=lambda *a, **kw: None)
    fake._spool = SimpleNamespace(notify=lambda *a, **kw: None)

    def _fake_create(self, **kw):
        create_calls.append(kw)

    fake._create_bot = MethodType(_fake_create, fake)
    _bind_adopt_helpers(fake)

    proposal = {
        "id": "test:cancel",
        "archetype": "mean_reversion_pair",
        "title": "cancel gate test",
        "created_ts": 0.0,
        "score": 90.0,
        "assets": ["AAA"],
        "bots": [
            {
                "asset": "AAA",
                "quote": "USD",
                "symbol": "AAA/USD",
                "existing_bot_id": "",
                "role": "peer_a",
                "suggested_target_usd": 25.0,
            },
        ],
        "wires": [],
        "adopt_notes": [],
    }
    orchestrator(fake, proposal)
    assert create_calls == []
    assert emissions == []


def test_adopt_signal_reaches_pane_handler(qapp):
    """The dialog's adoptClicked signal must reach the pane's
    adoptRequested signal (so the pane can forward to the orchestrator
    wired via main_window.set_adopt_handler)."""
    from src.gui.market_inspector import MarketInspectorTab

    tab = MarketInspectorTab()
    captured = []
    tab.set_adopt_handler(lambda payload: captured.append(payload))

    p = _make_proposal("test:ADOPT")
    dlg = TopologyPreviewDialog(p)
    # The wiring `MarketInspectorTopologies._on_preview` does: the dialog's
    # preview signal forwards to the pane's `adoptRequested`.
    dlg.adoptClicked.connect(tab._topologies_pane.adoptRequested.emit)
    dlg._on_adopt()
    assert len(captured) == 1
    assert captured[0]["id"] == "test:ADOPT"
    tab.deleteLater()
