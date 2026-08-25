"""H4 - wire hydration lost routes and recorded nothing anywhere.

THE DEFECT, as the suppression audit stated it
==============================================
``src/gui/bot_visualizer.py`` replayed each bot's ``smart_wire_routes``
as a ``wire.created`` event so the canvas paints the wire. Two
suppressions hid the failure path:

* ``# noqa: S112`` on the per-route handler. The checker said
  "try-except-continue detected, consider logging the exception". A
  route the bus rejected incremented nothing and logged nothing.
* ``# noqa: SIM105`` and ``# noqa: S110`` on the caller in
  ``BotVisualizationTab.__init__``. A total hydration failure was
  swallowed by ``pass``.

The method's own docstring says it "Returns count of events emitted".
The caller discarded the return value, so the one number that could
show the gap was thrown away.

MEASURED ON THE UNFIXED FILE, by driving the real path
======================================================
4 routes on disk, 2 painted, return value 2, log records ``[]``. A bus
that rejected one route: return value 1, log records ``[]``. No event
bus at all: return value 0, log records ``[]``. Construction with a
hydration that raised: the tab still built, log records ``[]``.

WHAT A FAILURE OF EACH TEST WOULD MEAN
======================================
``TestTheOracle`` - the sink cannot see this module's logger, so every
"was logged" and "was not logged" assertion in this file is void.
``acervator`` sets ``propagate = False``, so this is a real risk and
not a formality.

``TestARejectedRouteIsRecorded`` - a route the bus refuses is silently
dropped again. The overlay shows fewer wires than the state file holds
and the S112 finding is re-armed.

``TestARejectedRouteDoesNotStopTheRest`` - the record-keeping changed
the control flow, so one bad route now costs every route after it.
That would be a worse defect than the one being fixed.

``TestTheShortfallIsStated`` - the gap between routes on disk and wires
painted is invisible again.

``TestAFullyPaintedFleetIsQuiet`` - the shortfall warning fires when
there is no shortfall, so it carries no information and the test above
it passes for the wrong reason.

``TestNoEventBusIsRecorded`` - a total loss of hydration is silent
again.

``TestTheCallerConsumesTheCount`` - the caller throws the return value
away again. This is H4 itself. A source-text scan cannot see it: the
call is present in the text either way. Only the real constructor,
running with two different route counts, shows whether the number the
method returned reached the record.

``TestTheCallerRecordsAHydrationThatRaised`` - the outer handler
swallows a whole failed hydration again and the S110 finding is
re-armed.

NO TEST HERE READS ``~/.acervator/bot_state.json``. Every case installs
its own state through ``_load_bot_state_dict``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

import pytest
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from PySide6.QtCore import QCoreApplication

from src.core import event_bus as eb
from src.gui import bot_visualizer as bv

LOGGER_NAME = "acervator.gui.bot_visualizer"

CaptureLog = Callable[..., AbstractContextManager[list[logging.LogRecord]]]
InstallState = Callable[[dict[str, Any]], None]


def _state(routes: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Build the bot_state mapping that carries `routes` per source bot."""
    return {
        "bots": {
            bid: {"scrumming_state": {"smart_wire_routes": entries}}
            for bid, entries in routes.items()
        },
    }


# 4 routes on disk. Two are paintable. One has no destination and one
# has a zero percentage, so the shipped filter drops those two.
MIXED = _state(
    {
        "BTC-USD": [
            {"dest_bot_id": "ETH-USD", "pct": 25.0},
            {"dest_bot_id": "", "pct": 10.0},
        ],
        "SOL-USD": [
            {"dest_bot_id": "ADA-USD", "pct": 40.0},
            {"dest_bot_id": "DOGE-USD", "pct": 0.0},
        ],
    }
)
MIXED_ON_DISK = 4
MIXED_PAINTABLE = 2

TWO_PAINTABLE = _state(
    {
        "BTC-USD": [{"dest_bot_id": "ETH-USD", "pct": 25.0}],
        "SOL-USD": [{"dest_bot_id": "ADA-USD", "pct": 40.0}],
    }
)
ONE_PAINTABLE = _state(
    {
        "BTC-USD": [{"dest_bot_id": "ETH-USD", "pct": 25.0}],
    }
)


class _BusThatRejects:
    """A bus whose ``emit`` raises for one target and records the rest."""

    def __init__(self, reject: str) -> None:
        self.reject = reject
        self.delivered: list[str] = []

    def emit(self, topic: str, **kwargs: object) -> None:
        """Record the target, unless it is the one this bus rejects."""
        del topic
        target = str(kwargs.get("target_id", ""))
        if target == self.reject:
            msg = "bus rejected this route"
            raise RuntimeError(msg)
        self.delivered.append(target)


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    """Return the process application, creating an offscreen one if needed."""
    existing = QApplication.instance()
    if existing is not None:
        return existing
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication([])


@pytest.fixture
def on_disk(monkeypatch: pytest.MonkeyPatch) -> InstallState:
    """Return an installer that fixes what the hydration reads from disk."""

    def _install(state: dict[str, Any]) -> None:
        monkeypatch.setattr(
            bv.BotVisualizationTab,
            "_load_bot_state_dict",
            lambda _self: state,
        )

    return _install


def _bare_tab() -> bv.BotVisualizationTab:
    """Build an instance with no ``__init__``, so the method body runs alone."""
    return bv.BotVisualizationTab.__new__(bv.BotVisualizationTab)


def _messages(records: list[logging.LogRecord]) -> list[str]:
    """Render every captured record to its formatted message."""
    return [r.getMessage() for r in records]


def _built_tab(
    app: QCoreApplication,
) -> Iterator[bv.BotVisualizationTab]:
    """Construct the real tab, hand it over, then close it."""
    tab = bv.BotVisualizationTab()
    app.processEvents()
    try:
        yield tab
    finally:
        tab.close()
        app.processEvents()


class TestTheOracle:
    """A zero record count is a claim about the sink, not about the code."""

    def test_the_capture_fixture_sees_this_modules_logger(
        self,
        capture_log: CaptureLog,
    ) -> None:
        """Fail means every log assertion in this file is void."""
        with capture_log(LOGGER_NAME) as records:
            logging.getLogger(LOGGER_NAME).warning("canary")
        assert _messages(records) == ["canary"]


class TestARejectedRouteIsRecorded:
    """The S112 finding: a route the bus refuses must leave a record."""

    def test_the_rejected_route_is_named_with_its_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
        on_disk: InstallState,
        capture_log: CaptureLog,
    ) -> None:
        """Fail means a refused route is dropped in silence again."""
        on_disk(MIXED)
        bus = _BusThatRejects("ADA-USD")
        monkeypatch.setattr(eb, "get_event_bus", lambda: bus)
        with capture_log(LOGGER_NAME) as records:
            _bare_tab()._hydrate_smart_wire_routes_from_disk()
        named = [r for r in records if "SOL-USD -> ADA-USD" in r.getMessage()]
        assert named, _messages(records)
        assert named[0].exc_info is not None


class TestARejectedRouteDoesNotStopTheRest:
    """Record-keeping must not become a control-flow change."""

    def test_the_later_route_still_reaches_the_bus(
        self,
        monkeypatch: pytest.MonkeyPatch,
        on_disk: InstallState,
    ) -> None:
        """Fail means one bad route now costs every route after it."""
        on_disk(MIXED)
        bus = _BusThatRejects("ETH-USD")
        monkeypatch.setattr(eb, "get_event_bus", lambda: bus)
        painted = _bare_tab()._hydrate_smart_wire_routes_from_disk()
        assert bus.delivered == ["ADA-USD"]
        assert painted == 1


class TestTheShortfallIsStated:
    """The gap between routes on disk and wires painted must be recorded."""

    def test_the_record_states_painted_of_total(
        self,
        on_disk: InstallState,
        capture_log: CaptureLog,
    ) -> None:
        """Fail means the overlay can under-report the state file unseen."""
        on_disk(MIXED)
        with capture_log(LOGGER_NAME) as records:
            painted = _bare_tab()._hydrate_smart_wire_routes_from_disk()
        assert painted == MIXED_PAINTABLE
        stated = [m for m in _messages(records) if "under-reports" in m]
        assert stated, _messages(records)
        assert f"{MIXED_PAINTABLE} of {MIXED_ON_DISK} route(s)" in stated[0]
        assert "0 rejected by the bus, 2 unusable" in stated[0]


class TestAFullyPaintedFleetIsQuiet:
    """Paired control. The warning above must depend on a real shortfall."""

    def test_no_shortfall_record_when_every_route_is_painted(
        self,
        on_disk: InstallState,
        capture_log: CaptureLog,
    ) -> None:
        """Fail means the warning is unconditional and states nothing."""
        on_disk(TWO_PAINTABLE)
        with capture_log(LOGGER_NAME) as records:
            painted = _bare_tab()._hydrate_smart_wire_routes_from_disk()
        assert painted == 2
        assert [m for m in _messages(records) if "under-reports" in m] == []


class TestTheReturnedCountIsTheEventsDelivered:
    """The docstring claims the return value counts events emitted."""

    def test_the_real_bus_delivers_exactly_the_returned_count(
        self,
        on_disk: InstallState,
    ) -> None:
        """Fail means the docstring sentence is false."""
        on_disk(MIXED)
        seen: list[tuple[str, str]] = []
        bus = eb.get_event_bus()
        stop = bus.subscribe(
            "wire.created",
            lambda e: seen.append(
                (str(e.data.get("source_id")), str(e.data.get("target_id")))
            ),
        )
        try:
            painted = _bare_tab()._hydrate_smart_wire_routes_from_disk()
        finally:
            stop()
        assert painted == len(seen)
        assert seen == [("BTC-USD", "ETH-USD"), ("SOL-USD", "ADA-USD")]


class TestNoEventBusIsRecorded:
    """A total loss of hydration must not be silent."""

    def test_an_unavailable_bus_returns_zero_and_records_why(
        self,
        monkeypatch: pytest.MonkeyPatch,
        on_disk: InstallState,
        capture_log: CaptureLog,
    ) -> None:
        """Fail means every wire vanishes from the overlay with no trace."""
        on_disk(MIXED)

        def _no_bus() -> None:
            msg = "event bus down"
            raise RuntimeError(msg)

        monkeypatch.setattr(eb, "get_event_bus", _no_bus)
        with capture_log(LOGGER_NAME) as records:
            painted = _bare_tab()._hydrate_smart_wire_routes_from_disk()
        assert painted == 0
        errors = [r for r in records if r.levelno >= logging.ERROR]
        assert errors, _messages(records)
        assert errors[0].exc_info is not None


class TestTheCallerConsumesTheCount:
    """H4 itself. The constructor must record the number it received."""

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (ONE_PAINTABLE, 1),
            (TWO_PAINTABLE, 2),
        ],
    )
    def test_construction_records_the_count_the_method_returned(
        self,
        qapp: QCoreApplication,
        on_disk: InstallState,
        capture_log: CaptureLog,
        state: dict[str, Any],
        expected: int,
    ) -> None:
        """Fail means the return value is discarded again.

        Two route counts run through the same assertion, so a constant
        in the record cannot satisfy both.
        """
        on_disk(state)
        with capture_log(LOGGER_NAME) as records:
            for _tab in _built_tab(qapp):
                pass
        wanted = f"{expected} wire.created event(s) emitted"
        assert [m for m in _messages(records) if wanted in m], _messages(records)


class TestTheCallerRecordsAHydrationThatRaised:
    """The S110 finding: a whole failed hydration must leave a record."""

    def test_construction_survives_and_records_the_failure(
        self,
        qapp: QCoreApplication,
        monkeypatch: pytest.MonkeyPatch,
        capture_log: CaptureLog,
    ) -> None:
        """Fail means the tab hides a total hydration failure again."""

        def _raise(_self: object) -> int:
            msg = "hydration exploded"
            raise RuntimeError(msg)

        monkeypatch.setattr(
            bv.BotVisualizationTab,
            "_hydrate_smart_wire_routes_from_disk",
            _raise,
        )
        built = False
        with capture_log(LOGGER_NAME) as records:
            for tab in _built_tab(qapp):
                built = tab is not None
        assert built
        errors = [r for r in records if r.levelno >= logging.ERROR]
        assert errors, _messages(records)
        assert "wire hydration failed" in errors[0].getMessage()
        assert errors[0].exc_info is not None
