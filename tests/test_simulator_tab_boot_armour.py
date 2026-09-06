"""A failing Nuclear panel must not take the whole application down.

WHY THIS LANDS BEFORE THE NUCLEAR REPOINT.

`simulator_tab.py` imports and constructs the Nuclear panel with NO guard,
while the sibling `FleetReplayPanel` eight lines above IS guarded — imported
in a try/except that falls back to `FleetReplayPanel = None`, and constructed
behind `if FleetReplayPanel is not None:` with a QLabel placeholder otherwise.

Nothing wraps the Nuclear import or construction, and nothing upstream catches
either: `SimulatorTab()` in main_window, `_setup_ui()`, and `MainWindow(...)`
in main.py are all unguarded on that path. So an exception in the Nuclear panel
constructor does not degrade the Simulator tab — it kills startup.

The repoint edits that constructor. Arming the boot path first is the
difference between "the Nuclear tab shows a message" and "Acervator does not
launch", which is the operator's stated bar for this work.

THE GUARD MUST BE AUDIBLE. `main_window.py` already records NF-162: a silent
guard that failed on every boot with nothing ever saying so. A swallowed panel
that leaves no trace is a worse failure than a crash, because a crash gets
investigated. The except routes to the activity log.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def exploding_nuclear(monkeypatch):
    """Make the Nuclear panel constructor raise, the way a bad repoint would.

    ``variant_surface`` picks the Qt panel or the React panel, and both
    loaders read their class at call time, so both names are replaced.
    """
    import src.gui.simulator_tab.nuclear_mode_panel as npanel

    class _Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("nuclear panel construction failed")

    monkeypatch.setattr(npanel, "NuclearModePanel", _Boom)
    import src.gui.simulator_tab.simulator_tab as stab

    monkeypatch.setattr(stab, "NuclearModePanel", _Boom, raising=False)
    import src.gui.react_nuclear_mode_panel as rpanel

    monkeypatch.setattr(rpanel, "NuclearModeReactPanel", _Boom, raising=False)
    return _Boom


class TestTheFixtureItself:
    """POSITIVE CONTROL. If the patched class does not actually raise, every
    survival assertion below passes for the wrong reason."""

    def test_the_exploding_panel_really_explodes(self, exploding_nuclear):
        with pytest.raises(RuntimeError, match="nuclear panel"):
            exploding_nuclear()

    def test_the_real_panel_constructs_when_not_patched(self, qapp):
        """NEGATIVE CONTROL — the tab must be buildable at all, or the
        survival test proves nothing about the guard."""
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        tab = SimulatorTab()
        assert tab is not None
        assert getattr(tab, "nuclear_mode", None) is not None


class TestTheTabSurvivesAFailingNuclearPanel:
    def test_simulator_tab_still_constructs(self, qapp, exploding_nuclear):
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        tab = SimulatorTab()
        assert tab is not None, (
            "a failing Nuclear panel took down the Simulator tab, and nothing "
            "upstream catches it — this is an application-startup failure"
        )

    def test_fleet_replay_is_unaffected(self, qapp, exploding_nuclear):
        """The primary parity harness must not be collateral damage."""
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        tab = SimulatorTab()
        assert getattr(tab, "fleet_replay", None) is not None

    def test_the_stack_still_has_both_pages(self, qapp, exploding_nuclear):
        """The mode bar adds two tabs unconditionally. If the stack loses a
        page, selecting Nuclear Mode indexes past the end."""
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        tab = SimulatorTab()
        assert tab._stack.count() == 2

    def test_selecting_nuclear_mode_does_not_raise(self, qapp, exploding_nuclear):
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        tab = SimulatorTab()
        tab._stack.setCurrentIndex(1)
        assert tab._stack.currentIndex() == 1


class TestTheFailureIsAudible:
    """NF-162 was a silent guard that failed on every boot with nothing
    saying so. A swallowed panel must leave a trace."""

    def test_the_failure_reaches_a_log(self, qapp, exploding_nuclear, monkeypatch):
        """Observes the module logger DIRECTLY rather than through caplog.

        An earlier version used `caplog`, which passed alone and failed in
        the full suite. `logging_engine.py:341` sets
        `logging.getLogger("acervator").propagate = False`, so once any
        other test initialises the logging engine, records from
        `acervator.simulator_tab` stop at that ancestor and never reach
        caplog's root handler. The test was asserting on a delivery path
        another test globally disables — a real isolation defect in the
        test, not a flake to re-run.
        """
        import src.gui.simulator_tab.simulator_tab as stab

        seen: list[str] = []

        class _Rec:
            def exception(self, msg, *a, **kw):
                seen.append(str(msg) % a if a else str(msg))

            def __getattr__(self, _name):
                return lambda *a, **kw: None

        monkeypatch.setattr(stab, "logger", _Rec())
        stab.SimulatorTab()
        assert any(
            "nuclear" in m.lower() for m in seen
        ), f"the guard swallowed the failure silently; captured={seen}"

    def test_the_placeholder_says_what_happened(self, qapp, exploding_nuclear):
        """The operator clicking Nuclear Mode must see WHY it is empty, not a
        blank pane — mirroring FleetReplayPanel's own fallback label."""
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        tab = SimulatorTab()
        page = tab._stack.widget(1)
        text = getattr(page, "text", lambda: "")()
        assert "nuclear" in text.lower()
