"""The desktop bridge answers out of the running program, not out of the request.

`build_registry(live)` binds the History surface to a `LiveSystem`, `main.py`
publishes the History tab's trades into it, and `serve_on_thread` answers the
pipe away from the caller's thread. Each test drives the real handler through
`handle_line`; `test_no_live_system_leaves_the_answer_empty` is the negative
direction for every live assertion here.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src.core.desktop_bridge import (  # noqa: E402
    BRIDGE_THREAD_NAME,
    LiveSystem,
    build_registry,
    handle_line,
    serve,
    serve_on_thread,
)
from src.exchange import history_read_contract as hrc  # noqa: E402

# The contract's own date floor, so a fill dated from it survives apply_filters.
FROM_FLOOR = float(hrc.default_filters(0).from_ts)
TRADE_TS = FROM_FLOOR + 3600.0
FETCH_TS = FROM_FLOOR + 7200.0

REQUEST = json.dumps(
    {
        "id": 7,
        "method": "history.view_model",
        "params": {"page": 0, "now_ts": FETCH_TS},
    }
)


def _reader_of(entries: list) -> Any:
    """A fresh iterator per call, the shape the live-log readers return."""

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter(list(entries))

    return _read


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read empty gate and voting logs, never the operator's own."""
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of([]))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of([]))


class RefusingExchange:
    """A venue that answers nothing. Any attribute read raises."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the bridge reached the exchange for {name!r}")


def _live_fleet() -> tuple[Any, Any, Any]:
    """Return a real `BotManager`, its one real `BotContainer`, and its config."""
    from src.trading.bot_container import BotConfig, BotContainer, BotManager

    config = BotConfig(exchange_id="coinbase", base_currency="USD", target_asset="CHIP")
    bot = BotContainer(config, RefusingExchange())
    manager = BotManager()
    manager._bots[bot.bot_id] = bot
    return manager, bot, config


def _trade(symbol: str) -> dict:
    """One normalised fill for ``symbol``, carrying no bot id of its own."""
    return {
        "id": "t-1",
        "exchange": "coinbase",
        "symbol": symbol,
        "side": "BUY",
        "amount": 2.0,
        "price": 10.0,
        "cost": 20.0,
        "fee": 0.01,
        "fee_currency": "USD",
        "timestamp": TRADE_TS,
    }


def _cell(result: dict, row: int, key: str) -> dict:
    """Return one cell of one drawn row, by its ``key``."""
    for candidate in result["page"]["rows"][row]["cells"]:
        if candidate["key"] == key:
            return candidate
    raise KeyError(key)


def _answered(registry: dict) -> dict:
    """Send ``REQUEST`` through ``handle_line`` and return its result."""
    response = handle_line(REQUEST, registry)
    assert response["ok"], response
    return response["result"]


def _colours(image: Any) -> set:
    """Return every distinct pixel colour in ``image``."""
    return {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
    }


def test_the_answer_carries_a_bot_label_the_request_never_supplied() -> None:
    """The live fleet names the bot; ``REQUEST`` carries no bot id at all.

    A failure means ``REQUEST``, not the running ``BotManager``, decided the
    Bot column.
    """
    manager, bot, config = _live_fleet()
    live = LiveSystem(bot_manager=manager)
    live.publish("history", trades=[_trade(config.symbol)], last_fetched_ts=FETCH_TS)

    result = _answered(build_registry(live))

    assert bot.bot_id not in REQUEST, REQUEST
    assert result["loaded"] == 1, result["summary"]
    assert _cell(result, 0, "bot")["text"] == f"{config.target_asset}/{bot.bot_id[-4:]}"


def test_no_live_system_leaves_the_answer_empty() -> None:
    """The same ``REQUEST`` against ``build_registry()`` draws nothing.

    A failure means ``build_registry`` no longer answers as it does for the
    child process every existing surface test drives.
    """
    result = _answered(build_registry())

    assert result["loaded"] == 0, result
    assert result["page"]["rows"] == [], result["page"]


def test_a_live_system_holding_no_trades_answers_from_the_request() -> None:
    """Before the first refresh ``live_view_model`` still reads its own params."""
    manager, _bot, config = _live_fleet()
    registry = build_registry(LiveSystem(bot_manager=manager))
    line = json.dumps(
        {
            "id": 8,
            "method": "history.view_model",
            "params": {
                "page": 0,
                "now_ts": FETCH_TS,
                "trades": [_trade(config.symbol)],
            },
        }
    )
    response = handle_line(line, registry)

    assert response["ok"], response
    assert response["result"]["loaded"] == 1, response["result"]
    assert len(response["result"]["page"]["rows"]) == 1, response["result"]["page"]


def test_publishing_a_section_replaces_the_previous_one_whole() -> None:
    """A second ``publish`` drops the trades the first one recorded."""
    live = LiveSystem()
    live.publish("history", trades=[_trade("CHIP/USD")], last_fetched_ts=FETCH_TS)
    live.publish("history", trades=[], last_fetched_ts=FETCH_TS + 60)

    assert live.section("history") == {"trades": [], "last_fetched_ts": FETCH_TS + 60}
    assert live.section("nothing_published") == {}


def test_the_serve_loop_answers_away_from_the_calling_thread() -> None:
    """``serve_on_thread`` runs the handler on ``BRIDGE_THREAD_NAME``.

    A failure means ``serve`` would read the pipe on the thread that started
    it, which in ``main.py`` is the thread that draws the window.
    """
    seen: dict = {}

    def recording_handler(params: dict) -> dict:
        del params
        seen["thread"] = threading.current_thread().name
        seen["ident"] = threading.get_ident()
        return {"served": True}

    request_r, request_w = os.pipe()
    reply_r, reply_w = os.pipe()
    thread = serve_on_thread(
        os.fdopen(request_r, "rb"),
        os.fdopen(reply_w, "wb"),
        {"history.view_model": recording_handler},
    )
    try:
        with os.fdopen(request_w, "wb") as writer:
            writer.write(REQUEST.encode("utf-8") + b"\n")
            writer.flush()
            with os.fdopen(reply_r, "rb") as reader:
                frame = json.loads(reader.readline().decode("utf-8"))
    finally:
        thread.join(timeout=5.0)

    assert frame["result"] == {"served": True}, frame
    assert seen["thread"] == BRIDGE_THREAD_NAME, seen
    assert seen["ident"] != threading.get_ident(), seen


def test_serve_called_directly_answers_on_the_calling_thread() -> None:
    """The control for ``BRIDGE_THREAD_NAME``: ``serve`` alone stays here.

    A failure means ``recording_handler`` reports another thread on every
    path, and the assertion above proves nothing.
    """
    seen: dict = {}

    def recording_handler(params: dict) -> dict:
        del params
        seen["ident"] = threading.get_ident()
        return {"served": True}

    request_r, request_w = os.pipe()
    reply_r, reply_w = os.pipe()
    with os.fdopen(request_w, "wb") as writer:
        writer.write(REQUEST.encode("utf-8") + b"\n")
    with os.fdopen(request_r, "rb") as reader, os.fdopen(reply_w, "wb") as writer:
        answered = serve(reader, writer, {"history.view_model": recording_handler})
    os.close(reply_r)

    assert answered == 1
    assert seen["ident"] == threading.get_ident(), seen


def test_bridge_requested_reads_the_flag_and_nothing_else() -> None:
    """``main.bridge_requested`` answers True only for ``main.BRIDGE_FLAG``."""
    import main

    assert main.bridge_requested(["main.py", main.BRIDGE_FLAG]) is True
    assert main.bridge_requested(["main.py"]) is False
    assert main.bridge_requested(["main.py", "--child", "--no-watchdog"]) is False
    assert main.bridge_requested([]) is False


def test_wire_history_publisher_refuses_a_window_with_no_history_tab() -> None:
    """``main.wire_history_publisher`` returns None when ``_history_tab`` is None."""
    import main

    class NoTabs:
        _history_tab = None

    assert main.wire_history_publisher(LiveSystem(), NoTabs()) is None


def test_a_history_refresh_reaches_the_bridge_answer() -> None:
    """A ``history_refreshed`` emit fills the answer ``handle_line`` returns.

    A failure means ``wire_history_publisher`` connected nothing and the
    ``LiveSystem`` section stays empty through every refresh.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")

    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    import main

    QApplication.instance() or QApplication([])

    class Tab(QObject):
        history_refreshed = Signal(list)

        def __init__(self) -> None:
            super().__init__()
            self._last_fetched_ts = FETCH_TS

    class Window:
        def __init__(self, tab: Any) -> None:
            self._history_tab = tab

    manager, bot, config = _live_fleet()
    live = LiveSystem(bot_manager=manager)
    tab = Tab()
    slot = main.wire_history_publisher(live, Window(tab))
    assert slot is not None

    empty_before = _answered(build_registry(live))
    assert empty_before["loaded"] == 0, empty_before

    tab.history_refreshed.emit([_trade(config.symbol)])
    result = _answered(build_registry(live))

    assert result["loaded"] == 1, result["summary"]
    assert _cell(result, 0, "bot")["text"] == f"{config.target_asset}/{bot.bot_id[-4:]}"


def test_the_publisher_fills_the_section_on_the_thread_that_emits() -> None:
    """``publish_history`` runs before ``emit`` returns, on the emitting thread.

    A failure means ``wire_history_publisher`` delivered across threads and
    ``main.py`` would hand the GUI thread's work to another one.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")

    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    import main

    QApplication.instance() or QApplication([])

    class Tab(QObject):
        history_refreshed = Signal(list)

        def __init__(self) -> None:
            super().__init__()
            self._last_fetched_ts = FETCH_TS

    class Window:
        def __init__(self, tab: Any) -> None:
            self._history_tab = tab

    live = LiveSystem()
    tab = Tab()
    assert main.wire_history_publisher(live, Window(tab)) is not None
    assert live.section("history") == {}

    emitter = threading.get_ident()
    tab.history_refreshed.emit([_trade("CHIP/USD")])

    assert len(live.section("history")["trades"]) == 1, live.section("history")
    assert threading.get_ident() == emitter


def _is_torn(held: dict) -> bool:
    """Answer whether a section's trade count disagrees with ``last_fetched_ts``.

    Every section published below pairs ``last_fetched_ts`` with that many
    trades, so a disagreement can only come from a half-written section.
    """
    return len(held["trades"]) != int(held["last_fetched_ts"])


def _publish_count(holder: Any, count: int) -> None:
    """Publish ``count`` trades against a matching ``last_fetched_ts``."""
    holder.publish(
        "history",
        trades=[_trade("CHIP/USD")] * count,
        last_fetched_ts=float(count),
    )


def test_a_reader_never_sees_a_half_written_section() -> None:
    """No ``LiveSystem.section`` read tears while another thread republishes.

    A failure means the thread running ``serve`` read one refresh's trades
    against another refresh's ``last_fetched_ts``.
    """
    live = LiveSystem()
    _publish_count(live, 0)
    stop = threading.Event()
    torn: list = []

    def writer() -> None:
        count = 0
        while not stop.is_set():
            count = (count + 1) % 5
            _publish_count(live, count)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        for _ in range(20000):
            held = live.section("history")
            if _is_torn(held):
                torn.append(held)
    finally:
        stop.set()
        thread.join(timeout=5.0)

    assert torn == [], torn[:3]


def test_control_is_torn_reports_a_section_written_one_field_at_a_time() -> None:
    """``_is_torn`` reports the read taken between two field writes.

    A failure means the loop above could report nothing and its empty
    ``torn`` says nothing about ``LiveSystem.publish``.
    """

    class TornHolder:
        """A holder writing each field on its own, read between the two."""

        def __init__(self) -> None:
            self.held = {"trades": [], "last_fetched_ts": 0.0}
            self.seen: list = []

        def publish_one_field_at_a_time(self, count: int) -> None:
            self.held["trades"] = [_trade("CHIP/USD")] * count
            self.seen.append(dict(self.held))
            self.held["last_fetched_ts"] = float(count)
            self.seen.append(dict(self.held))

    holder = TornHolder()
    holder.publish_one_field_at_a_time(3)

    assert [_is_torn(one) for one in holder.seen] == [True, False], holder.seen


def test_the_main_window_still_paints_after_the_bridge_wiring() -> None:
    """The real ``MainWindow`` constructs and paints more than one colour.

    ``render_widget`` draws it offscreen, and a bare ``QWidget`` is the
    control ``_colours`` must report as one colour.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QWidget

    from src.gui.main_window import MainWindow
    from tests.qt_pixel import ensure_app, render_widget

    ensure_app()
    blank = QWidget()
    blank.resize(400, 300)
    blank_colours = _colours(render_widget(blank, size=(400, 300)))

    window = MainWindow(bot_manager=None, settings_manager=None)
    try:
        assert window.windowTitle().startswith("Acervator v"), window.windowTitle()
        painted = _colours(render_widget(window, size=(400, 300)))
    finally:
        window.close()
        window.deleteLater()

    assert len(blank_colours) == 1, blank_colours
    assert len(painted) > 1, painted


def test_start_bridge_serves_this_process_and_rebinds_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main.start_bridge`` answers on this process's pipe and moves ``sys.stdout``.

    A failure means a print inside the backend would land in a protocol frame
    and the shell would drop the response.
    """
    import main

    manager, bot, config = _live_fleet()
    live = LiveSystem(bot_manager=manager)
    live.publish("history", trades=[_trade(config.symbol)], last_fetched_ts=FETCH_TS)

    request_r, request_w = os.pipe()
    reply_r, reply_w = os.pipe()

    class Stdin:
        buffer = os.fdopen(request_r, "rb")

    class Stdout:
        buffer = os.fdopen(reply_w, "wb")

    monkeypatch.setattr(sys, "stdin", Stdin())
    monkeypatch.setattr(sys, "stdout", Stdout())
    thread = main.start_bridge(live)
    try:
        assert sys.stdout is sys.stderr
        with os.fdopen(request_w, "wb") as writer:
            writer.write(REQUEST.encode("utf-8") + b"\n")
            writer.flush()
            with os.fdopen(reply_r, "rb") as reader:
                frame = json.loads(reader.readline().decode("utf-8"))
    finally:
        thread.join(timeout=5.0)

    assert frame["ok"], frame
    assert frame["result"]["loaded"] == 1, frame["result"]
    assert (
        _cell(frame["result"], 0, "bot")["text"]
        == f"{config.target_asset}/{bot.bot_id[-4:]}"
    )


def test_the_bridge_thread_never_blocks_its_starter() -> None:
    """``serve_on_thread`` returns while nothing has reached the pipe.

    A failure means ``main.start_bridge`` would hold the GUI thread until the
    shell sent its first request.
    """
    request_r, request_w = os.pipe()
    reply_r, reply_w = os.pipe()

    started = time.monotonic()
    thread = serve_on_thread(
        os.fdopen(request_r, "rb"), os.fdopen(reply_w, "wb"), build_registry()
    )
    elapsed = time.monotonic() - started

    assert thread.is_alive() or thread.daemon
    assert elapsed < 2.0, elapsed
    os.close(request_w)
    thread.join(timeout=5.0)
    os.close(reply_r)
    assert not thread.is_alive()
