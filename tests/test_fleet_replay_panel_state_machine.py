"""The Fleet Replay panel Start, Stop and Reset are a correct state machine.

`_status_error` reports every failure path. `_on_reset_clicked` stops both
timers while `_controller` is still set, then nulls it and clears
`_gate_cells`; nulling first would leave `_refresh_progress` returning early
and both timers running. A second `_on_start_clicked` while a run is in flight
builds no second `FleetReplayController`.
"""

from __future__ import annotations

import sys

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from src.gui.simulator_tab.fleet.fleet_replay_panel import (  # noqa: F401
        FleetReplayPanel as _FleetReplayPanel,
    )

    _HAS_QT_PANEL = True
except ImportError:  # pragma: no cover - PySide6 absent
    _HAS_QT_PANEL = False


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, t):
        self.text = str(t)


class _Btn:
    def __init__(self):
        self.enabled = True

    def setEnabled(self, v):
        self.enabled = bool(v)


class _Timer:
    def __init__(self):
        self.running = True
        self.stops = 0

    def stop(self):
        self.running = False
        self.stops += 1

    def isActive(self):
        return self.running


class _Table:
    def setRowCount(self, _n):
        pass


class _Task:
    """Stands in for the asyncio task the controller creates."""

    def __init__(self, done: bool = False):
        self._done = done

    def done(self) -> bool:
        return self._done


class _Controller:
    """A double carrying what a running `FleetReplayController` carries.

    `started` distinguishes a loaded fleet, whose `_task` is None and whose
    `started_at_wall` is 0.0, from one that has ticked.
    """

    def __init__(self, boom=False, finished=False, started=True, task_done=None):
        self.stop_requested = False
        self._boom = boom
        self.progress = type(
            "P", (), {"finished": finished, "started_at_wall": 1.0 if started else 0.0}
        )()
        # A finished run has a completed task; a default of False alone would
        # build a controller that cannot exist.
        if task_done is None:
            task_done = finished
        self._task = _Task(done=task_done) if started else None

    def request_stop(self):
        if self._boom:
            raise RuntimeError("controller is wedged")
        self.stop_requested = True


def _panel(controller=None, confirm=True):
    """Built without Qt. The state machine is the subject, not the
    widget construction."""
    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    p = FleetReplayPanel.__new__(FleetReplayPanel)
    p._controller = controller
    p._configs = [{"symbol": "BTC/USD"}]
    p._gate_cells = {"BTC/USD": object()}
    p._ytd_trades = []
    p._status_lbl = _Label()
    p._progress_lbl = _Label()
    p._start_btn = _Btn()
    p._stop_btn = _Btn()
    p._fleet_table = _Table()
    p._progress_timer = _Timer()
    p._drain_timer = _Timer()
    p._async_loop_getter = None
    # Confirmation is injected so the test never opens a modal.
    p._confirm_reset = lambda: confirm
    return p


class TestTheHelperExists:
    def test_status_error_is_defined(self):
        """`FleetReplayPanel` carries a callable `_status_error`."""
        from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

        assert callable(
            getattr(FleetReplayPanel, "_status_error", None)
        ), "_status_error was never authored"

    def test_it_never_leaves_an_empty_status(self):
        """Exit gate: assert no failure path leaves status ''."""
        p = _panel()
        p._status_error("")
        assert p._status_lbl.text.strip() != ""

    def test_it_shows_the_reason_it_was_given(self):
        p = _panel()
        p._status_error("Cannot start: async loop unavailable.")
        assert "async loop unavailable" in p._status_lbl.text


class TestResetIsCorrectAndCannotHang:
    def test_reset_stops_both_timers(self):
        p = _panel(controller=_Controller())
        p._on_reset_clicked()
        assert not p._progress_timer.isActive()
        assert not p._drain_timer.isActive()

    def test_reset_nulls_the_controller(self):
        p = _panel(controller=_Controller())
        p._on_reset_clicked()
        assert p._controller is None

    def test_reset_clears_the_gate_cells(self):
        p = _panel(controller=_Controller())
        p._on_reset_clicked()
        assert p._gate_cells == {}

    def test_the_timers_are_stopped_before_the_controller_is_nulled(self):
        """Each timer's `stop` runs while `_controller` is still set.

        `_refresh_progress` returns early on a null controller, so a reset that
        nulls first never reaches the `stop` branch and both timers run on.
        """
        p = _panel(controller=_Controller())
        seen: list = []

        for timer in (p._progress_timer, p._drain_timer):
            real = timer.stop

            def _watch(_real=real):
                seen.append(p._controller)
                _real()

            timer.stop = _watch

        p._on_reset_clicked()

        assert len(seen) == 2, f"reset stopped {len(seen)} timers, not two"
        assert all(c is not None for c in seen), (
            "the controller was nulled before a timer was stopped; "
            "_refresh_progress returns early and the timer runs forever"
        )
        assert p._controller is None

    def test_a_wedged_controller_does_not_silently_swallow(self):
        """Reset used `except Exception: pass`, so a controller that
        refuses to stop produced a Reset that looked like it worked."""
        p = _panel(controller=_Controller(boom=True))
        p._on_reset_clicked()
        assert p._status_lbl.text.strip() != ""
        assert "stop" in p._status_lbl.text.lower()

    def test_reset_still_clears_the_fleet_on_the_happy_path(self):
        """NEGATIVE CONTROL: the existing behaviour must survive."""
        p = _panel(controller=_Controller())
        p._on_reset_clicked()
        assert p._configs == []
        assert p._start_btn.enabled is False


class TestResetConfirmsWhenARunIsInFlight:
    def test_it_asks_before_discarding_a_running_replay(self):
        p = _panel(controller=_Controller(finished=False), confirm=False)
        p._on_reset_clicked()
        assert p._controller is not None, "a declined confirmation still reset the run"
        assert p._configs != []

    def test_declining_leaves_the_timers_alone(self):
        p = _panel(controller=_Controller(finished=False), confirm=False)
        p._on_reset_clicked()
        assert p._progress_timer.isActive()

    def test_it_does_not_ask_when_nothing_is_running(self):
        """A confirm on every Reset trains the operator to click through
        it, which is worse than not asking."""
        asked = []
        p = _panel(controller=None)
        p._confirm_reset = lambda: asked.append(1) or True
        p._on_reset_clicked()
        assert asked == []

    def test_it_does_not_ask_for_a_fleet_that_was_only_loaded(self):
        """Load builds a controller. Nothing has run, so Reset has no
        work to discard and must not prompt.

        This is the state that refused Start: `finished` is False on a
        fleet that never ticked.
        """
        p = _panel(controller=_Controller(finished=False, started=False), confirm=False)
        assert p._run_in_flight() is False

    def test_it_does_not_ask_when_the_run_already_finished(self):
        asked = []
        p = _panel(controller=_Controller(finished=True))
        p._confirm_reset = lambda: asked.append(1) or True
        p._on_reset_clicked()
        assert asked == []


class TestStopReportsFailure:
    def test_a_wedged_controller_is_reported(self):
        """Stop swallowed request_stop() too: the operator pressed Stop
        and nothing changed on screen."""
        p = _panel(controller=_Controller(boom=True))
        p._on_stop_clicked()
        assert p._status_lbl.text.strip() != ""

    def test_the_happy_path_still_requests_stop(self):
        c = _Controller()
        p = _panel(controller=c)
        p._on_stop_clicked()
        assert c.stop_requested is True


class TestStartIsNotReentrant:
    def test_the_empty_fleet_return_says_why(self):
        """`if not self._configs: return` was bare — Start did nothing
        and explained nothing."""
        p = _panel()
        p._configs = []
        p._on_start_clicked()
        assert p._status_lbl.text.strip() != ""

    def test_a_second_start_while_running_is_refused(self):
        """Two controllers means the first run's timers and gate cells
        are orphaned with nothing pointing at them."""
        p = _panel(controller=_Controller(finished=False))
        p._on_start_clicked()
        assert p._status_lbl.text.strip() != ""
        assert (
            "already" in p._status_lbl.text.lower()
            or "running" in p._status_lbl.text.lower()
        )

    def test_a_refused_start_builds_no_second_controller(self, monkeypatch):
        """The running controller is still the one `_controller` holds.

        A `FleetReplayController` built during the refused start would orphan
        the first run's timers and gate cells.
        """
        from src.simulator.fleet import fleet_replay_controller as frc

        built: list = []

        def _refuse(*args, **kwargs):
            built.append((args, kwargs))
            raise AssertionError("a second controller was constructed")

        monkeypatch.setattr(frc, "FleetReplayController", _refuse, raising=True)

        running = _Controller(finished=False)
        p = _panel(controller=running)
        p._async_loop_getter = lambda: object()
        p._on_start_clicked()

        assert built == [], built
        assert p._controller is running
        assert "already" in p._status_lbl.text.lower()


class TestParitySkipIsReported:
    def test_the_status_names_it_when_ytd_is_empty(self):
        p = _panel()
        p._ytd_trades = []
        p._note_parity_state()
        assert "parity" in p._status_lbl.text.lower()
        assert "skip" in p._status_lbl.text.lower()

    def test_a_populated_ytd_set_does_not_claim_a_skip(self):
        """NEGATIVE CONTROL."""
        p = _panel()
        p._ytd_trades = [{"symbol": "BTC/USD"}]
        p._note_parity_state()
        assert "skip" not in p._status_lbl.text.lower()


_T0_MS = 1_776_778_500_000
_STEP_MS = 300_000


def _traded_tape():
    """A real `TabletBackend` that has settled fills, and its observer.

    The observer list is the SECOND WITNESS: the live history handed to
    the panel below is built from it, so the expected report is derived
    from what the tape did rather than from a written-down number.
    """
    from src.exchange.tablet_backend import TabletBackend

    rows = []
    px = 100.0
    for i in range(12):
        px *= 1.0 + ((i % 5) - 2) * 0.003
        rows.append([float(_T0_MS + i * _STEP_MS), px, px * 1.01, px * 0.99, px, 50.0])
    tape = TabletBackend({"CHIP/USD": rows}, balances={"USD": 10_000.0})
    seen: list = []
    tape.on_trade(seen.append)
    for i in range(6):
        assert tape.step() is True
        tape.create_order("CHIP/USD", "market", "buy" if i % 2 == 0 else "sell", 1.5)
    return tape, seen


def _panel_parity_lines(tape, live_trades) -> list[str]:
    """Run the shipped `_run_parity_comparison` over a stub panel.

    Called unbound on a `SimpleNamespace`, so no `QApplication` and no
    widget tree are needed: the method reads three attributes and
    writes to one callback.
    """
    from types import SimpleNamespace

    from src.gui.simulator_tab.fleet.fleet_replay_panel import (
        FleetReplayPanel,
    )

    lines: list[str] = []
    stub = SimpleNamespace(
        _controller=SimpleNamespace(tape=tape),
        _ytd_trades=list(live_trades),
        _performance_log_cb=lines.append,
    )
    FleetReplayPanel._run_parity_comparison(stub)
    return lines


@pytest.mark.skipif(
    not _HAS_QT_PANEL, reason="PySide6 not importable in this environment"
)
def test_the_panel_measures_parity_against_the_tape_s_own_fills() -> None:
    """THE MEASUREMENT, END TO END, on the shape the Simulator produces.

    Live history built from the tape's own fills must reproduce at
    100%: the two sides describe the same events. Anything less is the
    reader.

    This check is the reason the panel fix and the `compare_trades` fix
    are ONE change. With the panel still reading `_exchange._trades`
    the report says "sim produced 0 trades" — honest, and wrong about
    the run. With the panel fixed and the harness still reading the
    object shape, it says "0.0%" over six fills it never read — a
    measurement-shaped lie. Only both together produce the line below.
    """
    tape, observed = _traded_tape()
    assert len(observed) >= 2, len(observed)
    live = [
        {
            "timestamp": float(t["timestamp"]) / 1000.0,
            "symbol": t["symbol"],
            "side": t["side"],
            "amount": float(t["amount"]),
            "price": float(t["price"]),
        }
        for t in observed
    ]

    lines = _panel_parity_lines(tape, live)
    text = "\n".join(lines)

    assert "sim produced 0 trades" not in text, (
        "the panel still reports an empty sim tape against a tape that "
        f"settled {len(observed)} fill(s):\n{text}"
    )
    assert "Match rate: 100.0%" in text, (
        "the panel did not reproduce the tape's own fills:\n" + text
    )
    assert f"{len(observed):,} matched" in text, text
    assert "0 live-only" in text and "0 sim-only" in text, text


@pytest.mark.skipif(
    not _HAS_QT_PANEL, reason="PySide6 not importable in this environment"
)
def test_the_panel_still_says_so_when_no_live_history_is_loaded() -> None:
    """The honest skip is kept, not replaced.

    Parity needs both sides. With no YTD fetched the panel must say
    that, rather than reporting 0% against an empty live set.
    """
    tape, _observed = _traded_tape()
    text = "\n".join(_panel_parity_lines(tape, []))
    assert "no live trades loaded" in text, text
    assert "Match rate" not in text, text
