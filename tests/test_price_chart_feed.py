"""The price chart is actually fed, and with whole candles.

Operator task 2026-08-08 (screenshot area 4): "This display is mostly
working for the VWAP play back but need to add stone tablet candle play
back as well."

THE REGRESSION THIS EXISTS TO CATCH. `_collect_visual_snapshot` read
the current candle from `exchange._series[sym].get_current()`. When the
Simulator moved onto `CCXTConnector` + `TabletBackend` (v3.24.84),
`_series` stopped existing on either object. `getattr(exchange,
"_series", {})` returned an empty dict, so `close` stayed None and the
chart drew nothing on every refresh. Nothing raised.

WHY A TEST AND NOT ONLY AN EMITTER. Operator, 2026-08-08: "Emitters
don't work unless program is running or a debug is performed." Correct,
and it disposes of the claim that the emitter would have caught this:
`set_sink` has one caller, so in an ordinary GUI run nothing is
collecting and `sim.06.011.postcondition.price_chart.fed` is inert. These tests run in the
release gate with no program running, which is what makes them the
actual guard. The emitter is the complement -- it reports during a real
replay, when someone is collecting.

The two are different instruments for different moments, and only this
one runs unattended.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete every top-level widget after each test.

    These tests build whole SimulatorTab / FleetReplayPanel trees. Qt
    keeps a parentless widget alive for the life of the process, so
    without this they accumulate across the suite until the run dies
    with a segfault (exit 139, and once 127) partway through -- no
    failure summary, just truncated output. The crash point moved
    between runs, which is what identified it as accumulation rather
    than one bad test.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:                                   # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()

SYMS = ("CHIP/USD", "SPK/USD")
T0 = 1_776_778_500_000
STEP = 300_000


def _qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:                                   # pragma: no cover
        pytest.skip("PySide6 unavailable")
    return QApplication.instance() or QApplication([])


def _rows(n=400, px0=1.0):
    out, px = [], px0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.002
        out.append([T0 + i * STEP, px, px * 1.006, px * 0.994, px, 90.0])
    return out


def _panel_with_run():
    """A panel wired to a controller mid-replay, as the GUI has it."""
    _qapp()
    from src.gui.simulator_tab.fleet.fleet_replay_panel import (
        FleetReplayPanel)
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        FleetReplayController)
    cfgs = [{"mode": "scrumming", "symbol": s,
             "target_balance": 100.0, "target_asset": s.split("/")[0],
             "base_currency": "USD", "_src_bot_id": f"bot{i:04d}"}
            for i, s in enumerate(SYMS)]
    ctl = FleetReplayController(
        configs=cfgs,
        candles_by_symbol={s: _rows() for s in SYMS},
        smart_wires=[], tick_delay_s=0.0, max_candles=50,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None)
    ctl._build_sim()
    for _ in range(120):
        ctl._tape.step()
    p = FleetReplayPanel()
    p._controller = ctl
    return p, ctl


class TestTheFeedProducesCandles:
    def test_close_is_present_for_every_symbol(self):
        """THE REGRESSION PIN. `close` was None on every symbol."""
        p, _ = _panel_with_run()
        snap = p._collect_visual_snapshot()
        per = snap.get("per_symbol") or {}
        assert per, "snapshot carried no symbols at all"
        missing = [s for s, e in per.items() if e.get("close") is None]
        assert not missing, f"no close for: {missing}"

    def test_the_whole_bar_is_present(self):
        """Candle playback needs OHLC, not a close."""
        p, _ = _panel_with_run()
        per = p._collect_visual_snapshot().get("per_symbol") or {}
        for sym, e in per.items():
            for k in ("ts", "open", "high", "low", "close", "volume"):
                assert e.get(k) is not None, f"{sym} missing {k}"

    def test_the_bar_is_internally_consistent(self):
        """high >= max(open, close) and low <= min(open, close), or the
        chart would draw a wick inside its own body."""
        p, _ = _panel_with_run()
        per = p._collect_visual_snapshot().get("per_symbol") or {}
        for sym, e in per.items():
            assert e["high"] >= max(e["open"], e["close"]), sym
            assert e["low"] <= min(e["open"], e["close"]), sym

    def test_the_timestamp_is_the_tablet_int(self):
        """Candle timestamps are the tablet's exact int ms address."""
        p, _ = _panel_with_run()
        per = p._collect_visual_snapshot().get("per_symbol") or {}
        for sym, e in per.items():
            assert isinstance(e["ts"], int), f"{sym} ts is {type(e['ts'])}"
            assert (e["ts"] - T0) % STEP == 0, f"{sym} ts off the 5m grid"

    def test_the_candle_advances_with_the_clock(self):
        """A feed that returns the same bar forever looks alive and is
        not. Stepping the tape must move the candle."""
        p, ctl = _panel_with_run()
        first = p._collect_visual_snapshot()["per_symbol"][SYMS[0]]["ts"]
        for _ in range(10):
            ctl._tape.step()
        later = p._collect_visual_snapshot()["per_symbol"][SYMS[0]]["ts"]
        assert later > first, (first, later)


class TestTheFeedDoesNotServeTheFuture:
    def test_the_candle_never_leads_the_master_clock(self):
        p, ctl = _panel_with_run()
        per = p._collect_visual_snapshot().get("per_symbol") or {}
        clock = ctl._tape.current_ts_ms()
        for sym, e in per.items():
            assert e["ts"] <= clock, f"{sym} served a future candle"


class TestTheEmitterExistsForRuntime:
    def test_the_feed_emitter_is_declared(self):
        """The runtime complement. It only reports when a sink is
        installed, which is why the tests above are the real guard."""
        src = (REPO_ROOT / "src/gui/simulator_tab/fleet"
               / "fleet_replay_panel.py").read_text(encoding="utf-8")
        assert "sim.06.011.postcondition.price_chart.fed" in src
