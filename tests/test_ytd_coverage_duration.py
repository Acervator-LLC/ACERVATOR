"""Pins the duration on `ytd.10.002.postcondition.fleet_symbol_coverage`.

Queue item 10.3. This is the pin the classification of 2026-08-19 left
in its Group C -- "possible, but the site needs work first" -- under the
heading *siblings that would double-count*: three pins fire inside one
`_do_fetch()`, and the audit could not say which of them owned the
fetch.

THE RULE ANSWERED IT, AND THAT IS WHY THE ANSWER IS NOT A PREFERENCE.
`ytd.10.001` and `ytd.10.003` are `gauge`s. A gauge samples a value at
an instant, so rule E8 in `tools/emitter_registry_check.py` refuses a
duration on one -- and refuses it in SOURCE, not by convention.
`ytd.10.002` is the only `postcondition` in that function, so it is the
only pin that may own the fetch, and the double-count the audit warned
about cannot arise. Nothing was chosen; the type decided.

WHAT THE BRACKET SPANS, AND WHAT IT DELIBERATELY DOES NOT
=========================================================
It opens one line above `await fetch_all_history_chunked(...)` and
closes one line below it. So it holds the venue walk and neither the
per-symbol tally under it, nor the fleet-symbol set the emit block
builds, nor the three emit calls themselves. Those are the pin's own
bookkeeping, and folding them in would time the check with the work.

WHY THIS SITE IS WORTH A NUMBER AT ALL
======================================
It is the slowest single operation the Fleet Replay panel performs.
`fleet_replay_panel.py` records the measurement that made that plain:
a wall-clock 15 s timer once declared the fetch done before
`fetch_all_history_chunked` had finished, because a 4040-trade walk
takes longer than 15 s, and the panel then read an empty `_ytd_trades`
and reported "no trades" while the fetch was still running. Item 17's
"slow downs" is exactly this.

HOW IT IS DRIVEN
================
Through the REAL `_on_fetch_ytd_clicked`, called UNBOUND against a
stand-in panel, with only the venue call replaced. `FleetReplayPanel`
is defined inside a lazy factory and its `__init__` builds Qt widgets,
so constructing one is not available here; calling the method unbound
is the same code with a different `self`. Asserting that `duration=`
appears in the source would not catch a bracket that spans the emit
instead of the fetch, which is the whole failure this file exists to
refuse.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Iterator, Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

OWNER = "ytd.10.002.postcondition.fleet_symbol_coverage"
GAUGES = (
    "ytd.10.001.gauge.trades_fetched",
    "ytd.10.003.gauge.per_symbol_counts",
)

# The two workloads. The lever is `asyncio.sleep` on the fetch's own
# loop, which is where the real call waits on the network, and it never
# touches the clock, the emit call or the `duration` argument.
#
# WIDER THAN THE IN-PROCESS SITES, AND FOR A REASON. This lever crosses
# a thread boundary -- the coroutine is scheduled onto a loop running in
# another thread -- so the readings carry scheduling noise the
# single-threaded sites do not. 0.02 s against 0.30 s is 15x, against
# the 2x the predicate asks for.
LEVER_SHORT_S = 0.02
LEVER_LONG_S = 0.30
FLOOR_S = LEVER_LONG_S / 2.0
DEADLINE_S = 20.0

FLEET_SYMBOL = "CHIP/USD"


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    """Did the recorded duration MOVE with the work.

    A named function so the same rule can be driven in both directions.
    Requiring only `!=` would pass on a float wobble, so this asks that
    the longer fetch record a materially longer duration.
    """
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


def _tracks_the_fetch(short: Optional[float],
                      long_: Optional[float]) -> bool:
    """`_tracks`, with a floor under the long reading.

    The floor is the part a ratio cannot do. Move the stop clock above
    the await and both readings collapse to the cost of two
    `time.monotonic()` calls; two values that small differ by more than
    a factor of two on ordinary jitter, so a ratio alone ACCEPTS the
    blinding it exists to catch. The long lever waits 0.30 s inside the
    fetch, so a reading under half of that is a bracket that did not
    span it, whatever its ratio.

    This ADDS the floor and relaxes nothing.
    """
    if short is None or long_ is None:
        return False
    if long_ < FLOOR_S:
        return False
    return _tracks(short, long_)


def test_the_predicate_can_fail() -> None:
    """The other half of the lever. No loop and no panel needed.

    A predicate only ever driven the passing way is a claim about the
    predicate. Each pair below is a real blinding of this site.
    """
    # A collapsed bracket. The RATIO accepts it; the floor refuses it.
    assert _tracks(1.0e-07, 4.0e-07) is True
    assert _tracks_the_fetch(1.0e-07, 4.0e-07) is False
    # A literal substituted for the measurement: no movement at all.
    assert _tracks_the_fetch(LEVER_LONG_S, LEVER_LONG_S) is False
    # The bracket read backwards.
    assert _tracks_the_fetch(LEVER_LONG_S, LEVER_SHORT_S) is False
    # An absent duration is not a passing one.
    assert _tracks_the_fetch(None, LEVER_LONG_S) is False
    assert _tracks_the_fetch(LEVER_SHORT_S, None) is False
    # And the real shape passes, so the predicate is not simply strict.
    assert _tracks_the_fetch(LEVER_SHORT_S, LEVER_LONG_S) is True


class _Label:
    """The panel's status label, reduced to the one method used."""

    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:      # noqa: N802 - Qt name
        self.text = text


class _Button:
    """The panel's Fetch button, reduced to the one method used."""

    def __init__(self) -> None:
        self.enabled = True

    def setEnabled(self, value: bool) -> None:  # noqa: N802 - Qt name
        self.enabled = bool(value)


class _Panel:
    """The attributes `_on_fetch_ytd_clicked` actually reads.

    Written out rather than mocked so a field the method starts reading
    tomorrow fails loudly here instead of returning a silent stand-in.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop_getter = lambda: loop
        self._bot_manager = object()
        self._configs = [{"symbol": FLEET_SYMBOL}]
        self._ytd_trades: list = []
        self._status_lbl = _Label()
        self._fetch_ytd_btn = _Button()


@pytest.fixture()
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    """A real loop on its own thread, which is where the panel puts it.

    `_on_fetch_ytd_clicked` schedules with
    `asyncio.run_coroutine_threadsafe`, so a loop running in THIS thread
    would never advance and nothing would be measured.
    """
    made = asyncio.new_event_loop()
    thread = threading.Thread(target=made.run_forever, daemon=True)
    thread.start()
    try:
        yield made
    finally:
        made.call_soon_threadsafe(made.stop)
        thread.join(timeout=DEADLINE_S)
        made.close()


def _drive(monkeypatch: pytest.MonkeyPatch,
           made: asyncio.AbstractEventLoop,
           wait_s: float) -> SignalSink:
    """Run the real method once against a slow venue; return the sink."""
    import src.gui.history_helpers as helpers
    import src.gui.simulator_tab.fleet.fleet_replay_panel as panel_mod

    async def _slow_fetch(_bot_manager: Any, _since_ts: float) -> list:
        await asyncio.sleep(wait_s)
        return [{"symbol": FLEET_SYMBOL, "id": "t1"}]

    class _NoTimer:
        """The Qt bounce, with the Qt taken out.

        `_bounce_to_qt` marshals back onto the GUI thread. There is no
        GUI thread here and the callback only relabels a widget, so it
        is dropped. Nothing inside the bracket runs through it.
        """

        @staticmethod
        def singleShot(_ms: int, _fn: Any) -> None:   # noqa: N802
            return None

    monkeypatch.setattr(
        helpers, "fetch_all_history_chunked", _slow_fetch)
    monkeypatch.setattr(panel_mod, "QTimer", _NoTimer)

    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        panel = _Panel(made)
        FleetReplayPanel._on_fetch_ytd_clicked(panel)
        end = time.monotonic() + DEADLINE_S
        while time.monotonic() < end:
            if [r for r in sink.records() if r.name == OWNER]:
                break
            time.sleep(0.005)
    finally:
        sc.set_sink(previous)
    return sink


def _duration(sink: SignalSink) -> Optional[float]:
    found = [r for r in sink.records() if r.name == OWNER]
    if not found:
        return None
    return found[-1].duration


def _fastest(monkeypatch: pytest.MonkeyPatch,
             made: asyncio.AbstractEventLoop,
             wait_s: float, samples: int = 3) -> Optional[float]:
    """The lowest of `samples` readings.

    A scheduling pause can only ADD to an elapsed-time reading: the
    operating system can take the thread away inside the bracket, it
    cannot hand back time that was never spent. So every sample is the
    true cost plus non-negative noise and the smallest is the closest
    estimate this machine can give. Nothing is averaged and no recorded
    value is adjusted; the only thing added is repetition.
    """
    best: Optional[float] = None
    for _ in range(samples):
        got = _duration(_drive(monkeypatch, made, wait_s))
        if got is None:
            return None
        best = got if best is None else min(best, got)
    return best


def test_the_coverage_pin_fires_and_carries_a_duration(
        monkeypatch: pytest.MonkeyPatch,
        loop: asyncio.AbstractEventLoop) -> None:
    """POSITIVE CONTROL. Without this, a silent site reads as a pass."""
    sink = _drive(monkeypatch, loop, LEVER_SHORT_S)
    found = [r for r in sink.records() if r.name == OWNER]
    assert found, (
        "the coverage pin never fired, so every measurement below "
        "would be about nothing.")
    rec = found[-1]
    assert rec.duration is not None
    assert isinstance(rec.duration, float)
    assert rec.duration >= 0.0
    assert rec.duration < DEADLINE_S
    # The ingress guard refused nothing, so the site passed a real
    # measurement rather than a flag or a string coerced into one.
    assert sink.health()["duration_rejected"] == 0


def test_the_two_gauges_carry_no_duration(
        monkeypatch: pytest.MonkeyPatch,
        loop: asyncio.AbstractEventLoop) -> None:
    """THE SIBLING CONTROL, and the reason the owner is unambiguous.

    Three pins fire in one `_do_fetch`. If a second one also carried
    the fetch time, the two would report the same number under
    different names and item 17 would compute health from the
    duplicate. The register declares both gauges `forbidden`; this
    reads the records rather than the register.
    """
    sink = _drive(monkeypatch, loop, LEVER_SHORT_S)
    for name in GAUGES:
        found = [r for r in sink.records() if r.name == name]
        assert found, f"{name} never fired"
        assert found[-1].duration is None, (
            f"{name} is a gauge and carries a duration. A gauge samples "
            f"a value at an instant, so the number is fabricated, and "
            f"it double-counts the fetch that 10-002 already owns.")


def test_the_duration_tracks_the_venue_walk(
        monkeypatch: pytest.MonkeyPatch,
        loop: asyncio.AbstractEventLoop) -> None:
    """Two known waits must produce two DIFFERENT recorded values.

    Present-but-constant passes an existence check and fails this one.
    """
    short = _fastest(monkeypatch, loop, LEVER_SHORT_S)
    long_ = _fastest(monkeypatch, loop, LEVER_LONG_S)
    assert _tracks_the_fetch(short, long_), (
        f"10-002 records a duration that does not move with the fetch: "
        f"short={short!r} long={long_!r}. The register declares this pin "
        f"measured, so the bracket must span the await.")


def test_the_duration_excludes_the_tally_below_the_await(
        monkeypatch: pytest.MonkeyPatch,
        loop: asyncio.AbstractEventLoop) -> None:
    """The bracket closes BELOW the await and ABOVE the tally.

    Tracking says the number moves with the fetch. This says it does
    not swallow what follows the fetch, which is what stops the bracket
    being widened later. The short wait is 0.02 s, so a reading anywhere
    near the long lever would mean the close moved.
    """
    got = _duration(_drive(monkeypatch, loop, LEVER_SHORT_S))
    assert got is not None
    assert got < FLOOR_S, (
        f"10-002 recorded {got!r} s across a {LEVER_SHORT_S} s fetch. "
        f"The bracket has grown past the await it is supposed to hold.")
