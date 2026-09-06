"""The bridge writes a frame nobody asked for, and the shell can tell it apart.

`LiveSystem.publish` offers a frame to an attached `PushChannel`, which writes
it from the thread named `PUSH_THREAD_NAME` through the same `FrameWriter`
`serve` answers on. Each claim here is paired with the control that fails it:
an unlocked writer for the whole-frame check, a wider `backlog` for the bound,
and a direct `FrameWriter.write` for the thread and blocking checks.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, List

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src.core.desktop_bridge import (  # noqa: E402
    PROTOCOL_VERSION,
    PUSH_BACKLOG,
    PUSH_THREAD_NAME,
    FrameWriter,
    LiveSystem,
    PushChannel,
    build_registry,
    encode_frame,
    handle_line,
    push_frame,
    serve_and_push,
)
from src.exchange import history_surface  # noqa: E402

PAUSE_SECONDS = 0.75

JOIN_SECONDS = 10.0

PING = json.dumps({"id": 1, "method": "bridge.ping"})


def unparseable_lines(payload: bytes) -> int:
    """How many non-blank lines of ``payload`` are not one JSON object."""
    count = 0
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except ValueError:
            count += 1
    return count


class ListSink:
    """A byte sink recording every ``write`` and the thread that made it."""

    def __init__(self) -> None:
        """Start with no chunks and no recorded threads."""
        self.chunks: List[bytes] = []
        self.threads: List[str] = []

    def write(self, data: bytes) -> int:
        """Record ``data`` and the calling thread's name."""
        self.threads.append(threading.current_thread().name)
        self.chunks.append(data)
        return len(data)

    def flush(self) -> None:
        """Return without writing, as ``write`` has already recorded."""

    def payload(self) -> bytes:
        """Every recorded chunk joined in the order it was written."""
        return b"".join(self.chunks)


class SplitSink(ListSink):
    """A sink pausing its first writer halfway through that writer's bytes.

    ``paused`` is set once the first half is recorded; the writer then waits
    ``PAUSE_SECONDS`` for ``released``, which a second write sets and
    ``resumed_on_release`` records.
    """

    def __init__(self) -> None:
        """Start with both events clear and no writer seen."""
        super().__init__()
        self.paused = threading.Event()
        self.released = threading.Event()
        self.resumed_on_release: Any = None
        self._seen_first = False

    def write(self, data: bytes) -> int:
        """Split the first caller's bytes around a wait for a second caller."""
        if self._seen_first:
            super().write(data)
            self.released.set()
            return len(data)
        self._seen_first = True
        half = len(data) // 2
        super().write(data[:half])
        self.paused.set()
        self.resumed_on_release = self.released.wait(PAUSE_SECONDS)
        super().write(data[half:])
        return len(data)


class BlockedSink:
    """A sink whose ``write`` records nothing until ``release`` is set."""

    def __init__(self) -> None:
        """Start with ``entered`` and ``release`` clear and no chunks."""
        self.chunks: List[bytes] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def write(self, data: bytes) -> int:
        """Set ``entered``, wait for ``release``, then record ``data``."""
        self.entered.set()
        self.release.wait(30.0)
        self.chunks.append(data)
        return len(data)

    def flush(self) -> None:
        """Return without writing, as ``write`` has already recorded."""


class UnlockedWriter:
    """``FrameWriter`` with the lock taken out, the known-bad side of it."""

    def __init__(self, writer: Any) -> None:
        """Wrap ``writer`` with nothing guarding it."""
        self._writer = writer

    def write(self, data: bytes) -> int:
        """Write ``data`` and flush it, with no lock held."""
        written = self._writer.write(data)
        self._writer.flush()
        return written or 0

    def flush(self) -> None:
        """Return without writing, as ``write`` has already flushed."""


class CountingRegistry(dict):
    """A registry counting every handler call in ``calls``."""

    def __init__(self, registry: dict) -> None:
        """Wrap each handler of ``registry`` in a counting handler."""
        self.calls: List[str] = []
        super().__init__(
            {name: self._counted(name, fn) for name, fn in registry.items()}
        )

    def _counted(self, name: str, handler: Callable) -> Callable:
        """Return ``handler`` recording ``name`` in ``calls`` on every call."""

        def counted(params: dict) -> Any:
            self.calls.append(name)
            return handler(params)

        return counted


class PausingPush:
    """A push whose first ``offer`` waits for ``release`` before returning."""

    def __init__(self) -> None:
        """Start with ``entered`` and ``release`` clear and no offers."""
        self.offers: List[tuple] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self._seen_first = False

    def offer(self, section: str, values: dict) -> None:
        """Record the offer, and hold the first caller inside this call."""
        self.offers.append((section, dict(values)))
        if self._seen_first:
            return
        self._seen_first = True
        self.entered.set()
        self.release.wait(30.0)


class RefusingExchange:
    """A venue that answers nothing. Any attribute read raises."""

    def __getattr__(self, name: str) -> Any:
        """Refuse every attribute read, naming ``name``."""
        raise AssertionError(f"the bridge reached the exchange for {name!r}")


def _live_fleet() -> tuple:
    """Return a real ``BotManager``, its one real ``BotContainer``, and its config."""
    from src.trading.bot_container import BotConfig, BotContainer, BotManager

    config = BotConfig(exchange_id="coinbase", base_currency="USD", target_asset="CHIP")
    bot = BotContainer(config, RefusingExchange())
    manager = BotManager()
    manager._bots[bot.bot_id] = bot
    return manager, bot, config


def _pipe() -> tuple:
    """Return one pipe as a reading file and a writing file."""
    read_fd, write_fd = os.pipe()
    return os.fdopen(read_fd, "rb"), os.fdopen(write_fd, "wb")


def _first_frame(reader: Any) -> dict:
    """Return the first frame ``reader`` carries, failing after ``JOIN_SECONDS``."""
    held: List[bytes] = []

    def read_one() -> None:
        held.append(reader.readline())

    thread = threading.Thread(target=read_one, daemon=True)
    thread.start()
    thread.join(timeout=JOIN_SECONDS)
    assert held, f"no frame reached the pipe within {JOIN_SECONDS} seconds"
    return json.loads(held[0].decode("utf-8"))


def _race(make_writer: Callable) -> SplitSink:
    """Write a push and a response through ``make_writer`` at the same time.

    The pusher is paused inside the sink before the responder starts, so the
    responder always attempts its write while the pusher holds the sink.
    """
    sink = SplitSink()
    writer = make_writer(sink)
    push = encode_frame(push_frame("history", {"trades": []}))
    response = encode_frame({"id": 1, "ok": True, "result": {"protocol": 1}})

    pusher = threading.Thread(target=writer.write, args=(push,))
    responder = threading.Thread(target=writer.write, args=(response,))
    pusher.start()
    assert sink.paused.wait(JOIN_SECONDS), "the pusher never reached the sink"
    responder.start()
    pusher.join(timeout=JOIN_SECONDS)
    responder.join(timeout=JOIN_SECONDS)
    assert not pusher.is_alive() and not responder.is_alive(), "a writer hung"
    return sink


def test_a_publish_reaches_the_pipe_with_no_request_sent() -> None:
    """A push frame arrives carrying a value only the running fleet knows.

    A failure means the pipe stayed silent, or something answered a request
    that was never written into the reading end.
    """
    manager, bot, config = _live_fleet()
    live = LiveSystem(bot_manager=manager)
    registry = CountingRegistry(build_registry(live))
    request_reader, request_writer = _pipe()
    reply_reader, reply_writer = _pipe()
    thread = serve_and_push(request_reader, reply_writer, registry, live)
    try:
        live.publish("history", trades=[], symbol=config.symbol, bot=bot.bot_id)
        frame = _first_frame(reply_reader)
    finally:
        request_writer.close()
        thread.join(timeout=JOIN_SECONDS)
        reply_writer.close()

    assert frame["push"] == "history", frame
    assert "id" not in frame, frame
    assert frame["values"]["bot"] == bot.bot_id, (frame, bot.bot_id)
    assert registry.calls == [], registry.calls
    reply_reader.close()


def test_a_request_on_the_same_pipe_is_answered_and_counted() -> None:
    """The control for the push: the same pipe and counter do report a request.

    A failure means ``CountingRegistry.calls`` cannot record, and the empty
    list above says nothing about whether a request was answered.
    """
    live = LiveSystem()
    registry = CountingRegistry(build_registry(live))
    request_reader, request_writer = _pipe()
    reply_reader, reply_writer = _pipe()
    thread = serve_and_push(request_reader, reply_writer, registry, live)
    try:
        request_writer.write(PING.encode("utf-8") + b"\n")
        request_writer.flush()
        frame = _first_frame(reply_reader)
    finally:
        request_writer.close()
        thread.join(timeout=JOIN_SECONDS)
        reply_writer.close()

    assert frame["id"] == 1, frame
    assert "push" not in frame, frame
    assert registry.calls == ["bridge.ping"], registry.calls
    reply_reader.close()


def test_a_response_never_carries_the_key_a_push_is_found_by() -> None:
    """``handle_line`` answers without ``push``, and ``push_frame`` has no ``id``."""
    answered = handle_line(PING, build_registry())
    refused = handle_line(json.dumps({"id": 2, "method": "nope"}), build_registry())
    pushed = push_frame("history", {"trades": []})

    assert answered == {"id": 1, "ok": True, "result": {"protocol": PROTOCOL_VERSION}}
    assert "push" not in refused, refused
    assert pushed == {"push": "history", "values": {"trades": []}}


def test_no_push_attached_leaves_the_pipe_empty() -> None:
    """A ``LiveSystem`` nothing serves writes nothing however often it publishes.

    A failure means a program running with no shell pays for a channel it has
    no reader for.
    """
    reader, writer = _pipe()
    live = LiveSystem()
    for index in range(5):
        live.publish("history", trades=[], count=index)
    writer.close()
    payload = reader.read()
    reader.close()

    assert payload == b"", payload
    assert live.section("history") == {"trades": [], "count": 4}


def test_an_attached_push_puts_those_same_publishes_on_the_pipe() -> None:
    """The control for the empty pipe: the same reader does see five frames.

    A failure means the read above returns nothing whatever the bridge does.
    """
    reader, writer = _pipe()
    channel = PushChannel(FrameWriter(writer))
    live = LiveSystem()
    live.attach_push(channel)
    for index in range(5):
        live.publish("history", trades=[], count=index)
    channel.close()
    writer.close()
    payload = reader.read()
    reader.close()

    frames = [json.loads(line) for line in payload.splitlines() if line.strip()]
    assert [frame["values"]["count"] for frame in frames] == [0, 1, 2, 3, 4], frames


def test_a_push_and_a_response_under_one_writer_are_two_whole_frames() -> None:
    """``FrameWriter`` keeps the responder out until the pusher's frame is done.

    A failure means the two writers interleaved and the frontend's parser gets
    a line that is neither frame.
    """
    sink = _race(FrameWriter)
    payload = sink.payload()
    frames = [json.loads(line) for line in payload.splitlines() if line.strip()]
    keys = sorted(sorted(frame) for frame in frames)

    assert sink.resumed_on_release is False, "the responder was never in contention"
    assert unparseable_lines(payload) == 0, payload
    assert keys == [["id", "ok", "result"], ["push", "values"]], keys


def test_control_a_writer_with_no_lock_tears_the_two_frames() -> None:
    """The same race through ``UnlockedWriter`` produces two broken lines.

    A failure means ``unparseable_lines`` cannot report a torn frame, and its
    zero above proves nothing about ``FrameWriter``.
    """
    sink = _race(UnlockedWriter)
    payload = sink.payload()

    assert sink.resumed_on_release is True, "the responder never got in"
    assert unparseable_lines(payload) == 2, payload


def test_the_push_frame_is_written_on_the_bridge_push_thread() -> None:
    """The thread that publishes is not the thread that writes.

    A failure means the emitting thread carried the write, which in the running
    program is the thread that draws the window.
    """
    sink = ListSink()
    channel = PushChannel(FrameWriter(sink))
    live = LiveSystem()
    live.attach_push(channel)
    live.publish("history", trades=[])
    channel.close()

    assert sink.threads == [PUSH_THREAD_NAME], sink.threads
    assert threading.current_thread().name != PUSH_THREAD_NAME


def test_control_a_direct_write_records_the_calling_thread() -> None:
    """``ListSink`` reports whichever thread wrote, not a fixed name.

    A failure means the recorder always says ``PUSH_THREAD_NAME`` and the
    assertion above is satisfied by the instrument alone.
    """
    sink = ListSink()
    FrameWriter(sink).write(b"{}\n")

    assert sink.threads == [threading.current_thread().name], sink.threads


def test_publish_returns_while_the_pipe_is_still_blocked() -> None:
    """Four publishes complete while the pipe holds the first frame unwritten.

    A failure means a stalled shell would hold the thread that emitted the
    value, which in the running program is the thread that draws the window.
    """
    sink = BlockedSink()
    channel = PushChannel(FrameWriter(sink))
    live = LiveSystem()
    live.attach_push(channel)
    try:
        live.publish("history", trades=[], count=0)
        assert sink.entered.wait(JOIN_SECONDS), "the drain never reached the sink"
        for index in range(1, 5):
            live.publish("history", trades=[], count=index)

        assert sink.entered.is_set() and not sink.release.is_set()
        assert sink.chunks == [], sink.chunks
    finally:
        sink.release.set()
        channel.close()


def test_control_a_direct_write_to_that_pipe_does_not_return() -> None:
    """``BlockedSink`` really blocks, so the publishes above were handed off.

    A failure means the sink returns on its own and the test above would pass
    with no hand-off at all.
    """
    sink = BlockedSink()
    writer = FrameWriter(sink)
    thread = threading.Thread(target=writer.write, args=(b"{}\n",))
    thread.start()
    try:
        assert sink.entered.wait(JOIN_SECONDS), "the writer never reached the sink"
        thread.join(timeout=0.5)

        assert thread.is_alive(), "the blocked sink returned on its own"
    finally:
        sink.release.set()
        thread.join(timeout=JOIN_SECONDS)


def _fill_blocked_channel(backlog: int) -> tuple:
    """Offer 501 frames to a channel of ``backlog`` whose pipe is blocked."""
    sink = BlockedSink()
    channel = PushChannel(FrameWriter(sink), backlog=backlog)
    live = LiveSystem()
    live.attach_push(channel)
    live.publish("history", count=0)
    assert sink.entered.wait(JOIN_SECONDS), "the drain never reached the sink"
    for index in range(1, 501):
        live.publish("history", count=index)
    return sink, channel


def test_the_backlog_stops_at_its_bound_while_the_pipe_is_blocked() -> None:
    """501 publishes against a stuck pipe leave ``PUSH_BACKLOG`` frames held.

    A failure means the backlog grows with the publishes, and a shell that
    stops reading costs the running program memory without limit.
    """
    sink, channel = _fill_blocked_channel(PUSH_BACKLOG)
    try:
        assert channel.backlog == PUSH_BACKLOG, channel.backlog
    finally:
        sink.release.set()
        channel.close()


def test_control_a_wider_bound_holds_every_frame_the_narrow_one_dropped() -> None:
    """The same 501 publishes at a bound of 1000 leave 500 frames held.

    A failure means ``PushChannel.backlog`` cannot report a growing queue, and
    the bound above is not what limited it.
    """
    sink, channel = _fill_blocked_channel(1000)
    try:
        assert channel.backlog == 500, channel.backlog
    finally:
        sink.release.set()
        channel.close()


def _push_threads() -> set:
    """The identity of every live thread named ``PUSH_THREAD_NAME``."""
    return {one.ident for one in threading.enumerate() if one.name == PUSH_THREAD_NAME}


def test_a_live_system_with_no_push_starts_no_thread() -> None:
    """A thousand publishes with nothing attached start no drain thread.

    A failure means a program running with no shell pays for a thread it has
    no reader for.
    """
    before = _push_threads()
    live = LiveSystem()
    for index in range(1000):
        live.publish("history", count=index)

    assert _push_threads() - before == set()
    assert live.section("history") == {"count": 999}


def test_control_attaching_a_push_starts_exactly_one_thread() -> None:
    """The control for the thread count: attaching one adds one.

    A failure means ``_push_threads`` cannot see a drain thread and its empty
    difference above says nothing.
    """
    before = _push_threads()
    channel = PushChannel(FrameWriter(ListSink()))
    try:
        assert len(_push_threads() - before) == 1, _push_threads()
    finally:
        channel.close()

    assert _push_threads() - before == set()


def test_a_second_publish_waits_for_the_first_one_to_offer_its_frame() -> None:
    """``publish`` offers under the same lock that replaces the section.

    A failure means two emitting threads can interleave, and the older frame
    can reach the pipe after the newer one.
    """
    push = PausingPush()
    live = LiveSystem()
    live.attach_push(push)
    first = threading.Thread(target=live.publish, args=("history",), kwargs={"n": 0})
    second = threading.Thread(target=live.publish, args=("history",), kwargs={"n": 1})
    first.start()
    try:
        assert push.entered.wait(JOIN_SECONDS), "the first publish never offered"
        second.start()
        second.join(timeout=0.5)

        assert second.is_alive(), "the second publish overtook the first"
    finally:
        push.release.set()
        first.join(timeout=JOIN_SECONDS)
        second.join(timeout=JOIN_SECONDS)

    assert [values["n"] for _section, values in push.offers] == [0, 1], push.offers


def test_build_registry_with_no_argument_keeps_todays_table() -> None:
    """Only the History handler changes when a ``LiveSystem`` is passed.

    A failure means the push work moved, added or dropped a method the 74
    surfaces and the frontend reach the backend by.
    """
    plain = build_registry()
    lived = build_registry(LiveSystem())
    rebound = sorted(
        name
        for name in plain
        if name != "bridge.ping" and plain[name] is not lived[name]
    )

    assert set(plain) == set(lived)
    assert rebound == [history_surface.METHOD], rebound
    assert plain[history_surface.METHOD] is history_surface.view_model
    assert plain["bridge.ping"]({}) == {"protocol": PROTOCOL_VERSION}
