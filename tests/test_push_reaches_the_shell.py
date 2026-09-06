"""A publish in the running program reaches the Electron side unasked.

``main.start_bridge`` serves through ``serve_and_push``, ``desktop/main.js``
routes a frame carrying ``push`` to ``deliverPush`` and ``broadcastPush``, and
``desktop/preload.js`` exposes ``onPush``. ``MAIN_STUBS`` and ``PRELOAD_STUBS``
stand in for ``electron``, ``child_process`` and ``path`` while ``_run`` drives
the shipped scripts in ``QJSEngine``. ``test_control_the_old_join_leaves_the
_same_publish_off_the_pipe`` is the negative direction for the Python join.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, List

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src.core.desktop_bridge import (  # noqa: E402
    LiveSystem,
    build_registry,
    push_frame,
    serve_on_thread,
)
from tests.fixtures.web_js_modules import drain_events, new_engine  # noqa: E402

SHELL = REPO / "desktop"
MAIN_JS = SHELL / "main.js"
PRELOAD_JS = SHELL / "preload.js"

JOIN_SECONDS = 10.0

WRAPPER_HEAD = "(function(require, module, exports, process, __dirname, __filename){\n"
WRAPPER_TAIL = "\n})"

WRAPPER_ARGS = '(req, module, module.exports, proc, "desktop", "desktop/script.js");\n'

MAIN_STUBS = """
var recorded = {sent: [], stderr: [], pushed: [], handled: [], loaded: []};
var feed = null;
var child = {
  stdout: {
    setEncoding: function () {},
    on: function (name, fn) { if (name === "data") { feed = fn; } }
  },
  stderr: {setEncoding: function () {}, on: function () {}},
  stdin: {write: function (text) { recorded.sent.push(text); }, end: function () {}},
  on: function () {}
};
var windows = [];
function FakeWindow(options) {
  var self = this;
  this.options = options;
  this.destroyed = false;
  this.isDestroyed = function () { return self.destroyed; };
  this.loadFile = function (file) { recorded.loaded.push(file); };
  this.webContents = {
    isDestroyed: function () { return self.destroyed; },
    send: function (channel, section, values) {
      recorded.pushed.push({channel: channel, section: section, values: values});
    }
  };
  windows.push(this);
}
FakeWindow.getAllWindows = function () { return windows; };
var electron = {
  app: {
    whenReady: function () {
      return {then: function (fn) { fn(); return {then: function () {}}; }};
    },
    on: function () {},
    quit: function () {}
  },
  BrowserWindow: FakeWindow,
  ipcMain: {handle: function (channel) { recorded.handled.push(channel); }}
};
function req(name) {
  if (name === "electron") { return electron; }
  if (name === "child_process") { return {spawn: function () { return child; }}; }
  if (name === "path") {
    return {join: function () {
      return Array.prototype.slice.call(arguments).join("/");
    }};
  }
  throw new Error("the shell asked for " + name);
}
var proc = {
  env: {},
  platform: "win32",
  stderr: {write: function (text) { recorded.stderr.push(text); }}
};
var module = {exports: {}};
"""

PRELOAD_STUBS = """
var recorded = {invoked: []};
var exposed = null;
var listeners = [];
var electron = {
  contextBridge: {
    exposeInMainWorld: function (name, api) { exposed = {name: name, api: api}; }
  },
  ipcRenderer: {
    on: function (channel, fn) { listeners.push({channel: channel, fn: fn}); },
    removeListener: function (channel, fn) {
      listeners = listeners.filter(function (one) { return one.fn !== fn; });
    },
    invoke: function (channel, method, params) {
      recorded.invoked.push([channel, method, params]);
      return {then: function () {}};
    }
  }
};
function deliver(channel, section, values) {
  var reached = 0;
  listeners.forEach(function (one) {
    if (one.channel === channel) { one.fn({}, section, values); reached++; }
  });
  return reached;
}
function req(name) {
  if (name === "electron") { return electron; }
  throw new Error("the preload asked for " + name);
}
var proc = {env: {}, platform: "win32"};
var module = {exports: {}};
"""


def _wrapped(path: Path) -> str:
    """The file at ``path`` as a callable function expression."""
    return WRAPPER_HEAD + path.read_text(encoding="utf-8") + WRAPPER_TAIL


@pytest.fixture()
def js(qapp: Any) -> Any:
    """A factory for a ``QJSEngine`` held for the length of one test."""
    assert qapp is not None
    held: List[Any] = []

    def make() -> Any:
        engine = new_engine()
        held.append(engine)
        return engine

    return make


def _run(make: Any, stubs: str, path: Path, scenario: str, read: str = "") -> Any:
    """Run ``path`` against ``stubs``, then ``scenario``, and return its JSON.

    ``read`` is evaluated after ``drain_events`` for a scenario whose value a
    promise continuation fills in.
    """
    engine = make()
    source = (
        "(function () {\n"
        + stubs
        + "("
        + _wrapped(path)
        + ")"
        + WRAPPER_ARGS
        + "var shell = module.exports;\nvar G = this;\n"
        + scenario
        + "\n})()"
    )
    result = engine.evaluate(source, path.name)
    assert not result.isError(), path.name + ": " + result.toString()
    drain_events()
    if read:
        result = engine.evaluate(read, path.name + ":read")
        assert not result.isError(), path.name + ": " + result.toString()
    text = result.toString()
    return None if text == "undefined" else json.loads(text)


def _line(frame: dict) -> str:
    """``frame`` as the one line of text a chunk of the pipe carries."""
    return json.dumps(frame) + "\\n"


class RefusingExchange:
    """``RefusingExchange`` answers nothing; every attribute read raises."""

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
    """``os.pipe`` as a reading file and a writing file."""
    read_fd, write_fd = os.pipe()
    return os.fdopen(read_fd, "rb"), os.fdopen(write_fd, "wb")


def _first_frame(reader: Any) -> Any:
    """The first frame ``reader`` carries, or None after ``JOIN_SECONDS``."""
    held: List[bytes] = []

    def read_one() -> None:
        held.append(reader.readline())

    thread = threading.Thread(target=read_one, daemon=True)
    thread.start()
    thread.join(timeout=JOIN_SECONDS)
    if not held or not held[0]:
        return None
    return json.loads(held[0].decode("utf-8"))


def _serve_and_publish(start: Any, monkeypatch: pytest.MonkeyPatch) -> tuple:
    """Start the bridge through ``start``, publish the fleet, read one frame."""
    manager, bot, config = _live_fleet()
    live = LiveSystem(bot_manager=manager)
    request_reader, request_writer = _pipe()
    reply_reader, reply_writer = _pipe()

    class Stdin:
        buffer = request_reader

    class Stdout:
        buffer = reply_writer

    monkeypatch.setattr(sys, "stdin", Stdin())
    monkeypatch.setattr(sys, "stdout", Stdout())
    thread = start(live)
    try:
        live.publish("history", trades=[], symbol=config.symbol, bot=bot.bot_id)
        frame = _first_frame(reply_reader)
    finally:
        request_writer.close()
        thread.join(timeout=JOIN_SECONDS)
        reply_writer.close()
        reply_reader.close()
    return frame, bot


def test_start_bridge_puts_a_publish_on_the_pipe_with_no_request_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main.start_bridge`` carries a ``BotContainer`` id nothing asked for.

    A failure means ``start_bridge`` attached no ``PushChannel`` to ``live``.
    """
    import main

    frame, bot = _serve_and_publish(main.start_bridge, monkeypatch)

    assert frame is not None, "no frame reached the pipe"
    assert frame["push"] == "history", frame
    assert "id" not in frame, frame
    assert frame["values"]["bot"] == bot.bot_id, (frame, bot.bot_id)


def test_control_the_old_join_leaves_the_same_publish_off_the_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``serve_on_thread`` is the call ``main.py`` made before, and it pushes none.

    A failure means ``_first_frame`` reports a frame on every path.
    """

    def start_the_old_way(live: LiveSystem) -> Any:
        channel = sys.stdout.buffer
        sys.stdout = sys.stderr
        return serve_on_thread(sys.stdin.buffer, channel, build_registry(live))

    frame, _bot = _serve_and_publish(start_the_old_way, monkeypatch)

    assert frame is None, frame


def test_a_push_line_from_the_backend_reaches_a_subscriber(js: Any) -> None:
    """``Bridge.onPush`` is called with the section and values off the pipe.

    A failure means ``onFrame`` drops a ``push`` frame at the ``pending`` lookup.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        var bridge = new shell.Bridge();
        var seen = [];
        bridge.onPush(function (section, values) {
          seen.push({section: section, values: values});
        });
        bridge.onData('"""
        + _line(push_frame("history", {"bot": "live-only"}))
        + """');
        return JSON.stringify({seen: seen, pending: bridge.pending.size});
        """,
    )

    assert observed["seen"] == [{"section": "history", "values": {"bot": "live-only"}}]
    assert observed["pending"] == 0, observed


def test_a_response_line_reaches_its_waiter_and_no_subscriber(js: Any) -> None:
    """A frame carrying ``id`` resolves its ``pending`` waiter and no ``onPush``.

    A failure means ``deliverPush`` is handed every frame ``onFrame`` reads.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        var bridge = new shell.Bridge();
        var seen = [];
        var answered = [];
        bridge.child = child;
        bridge.call("bridge.ping", {}).then(function (result) {
          answered.push(result);
        });
        bridge.onPush(function (section, values) {
          seen.push({section: section, values: values});
        });
        var before = bridge.pending.size;
        bridge.onData('"""
        + _line({"id": 1, "ok": True, "result": {"protocol": 1}})
        + """');
        G.OBSERVED = {
          seen: seen,
          answered: answered,
          before: before,
          after: bridge.pending.size
        };
        """,
        read="JSON.stringify(OBSERVED)",
    )

    assert observed["seen"] == [], observed
    assert observed["before"] == 1 and observed["after"] == 0, observed
    assert observed["answered"] == [{"protocol": 1}], observed


def test_a_push_and_a_response_in_one_chunk_are_told_apart(js: Any) -> None:
    """``onData`` splits one chunk into a ``push`` frame and an ``id`` frame.

    A failure means ``onFrame`` loses one of the two frames in flight.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        var bridge = new shell.Bridge();
        var seen = [];
        var answered = [];
        bridge.child = child;
        bridge.call("bridge.ping", {}).then(function (result) {
          answered.push(result);
        });
        bridge.onPush(function (section, values) {
          seen.push({section: section, values: values});
        });
        bridge.onData('"""
        + _line(push_frame("history", {"bot": "live-only"}))
        + _line({"id": 1, "ok": True, "result": {"protocol": 1}})
        + """');
        G.OBSERVED = {
          seen: seen,
          answered: answered,
          pending: bridge.pending.size
        };
        """,
        read="JSON.stringify(OBSERVED)",
    )

    assert observed["seen"] == [{"section": "history", "values": {"bot": "live-only"}}]
    assert observed["answered"] == [{"protocol": 1}], observed
    assert observed["pending"] == 0, observed


def test_the_shell_sends_every_push_to_the_window_it_opened(js: Any) -> None:
    """``broadcastPush`` reaches ``webContents.send`` on ``PUSH_CHANNEL``.

    A failure means ``createWindow`` opens a window no push is delivered to.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        feed('"""
        + _line(push_frame("history", {"bot": "live-only"}))
        + """');
        return JSON.stringify({
          pushed: recorded.pushed,
          channel: shell.PUSH_CHANNEL,
          windows: windows.length,
          stderr: recorded.stderr
        });
        """,
    )

    assert observed["windows"] == 1, observed
    assert observed["channel"] == "acervator:push", observed
    assert observed["pushed"] == [
        {
            "channel": "acervator:push",
            "section": "history",
            "values": {"bot": "live-only"},
        }
    ], observed
    assert observed["stderr"] == [], observed


def test_a_shell_with_no_subscriber_holds_nothing_and_reports_nothing(js: Any) -> None:
    """A hundred ``push`` frames leave ``pending``, ``pushHandlers``, ``buffer`` empty.

    A failure means a shell with no ``onPush`` handler pays for the channel.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        var bridge = new shell.Bridge();
        for (var n = 0; n < 100; n++) {
          bridge.onData('{"push": "history", "values": {"n": ' + n + '}}\\n');
        }
        return JSON.stringify({
          pending: bridge.pending.size,
          handlers: bridge.pushHandlers.size,
          buffer: bridge.buffer,
          stderr: recorded.stderr
        });
        """,
    )

    assert observed["pending"] == 0, observed
    assert observed["handlers"] == 0, observed
    assert observed["buffer"] == "", observed
    assert observed["stderr"] == [], observed


def test_control_one_subscriber_receives_every_one_of_those_frames(js: Any) -> None:
    """The same hundred frames all reach one ``onPush`` handler.

    A failure means ``onData`` delivers nothing and the empty counts above
    measure the feed.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        var bridge = new shell.Bridge();
        var seen = [];
        bridge.onPush(function (section, values) { seen.push(values.n); });
        for (var n = 0; n < 100; n++) {
          bridge.onData('{"push": "history", "values": {"n": ' + n + '}}\\n');
        }
        return JSON.stringify({count: seen.length, first: seen[0], last: seen[99]});
        """,
    )

    assert observed["count"] == 100, observed
    assert observed["first"] == 0 and observed["last"] == 99, observed


def test_a_failing_subscriber_never_stops_the_next_one(js: Any) -> None:
    """One ``onPush`` handler that throws leaves the next one called.

    A failure means ``deliverPush`` stops at the first handler that raises.
    """
    observed = _run(
        js,
        MAIN_STUBS,
        MAIN_JS,
        """
        var bridge = new shell.Bridge();
        var seen = [];
        bridge.onPush(function () { throw new Error("panel refused"); });
        bridge.onPush(function (section) { seen.push(section); });
        bridge.onData('"""
        + _line(push_frame("history", {"bot": "live-only"}))
        + """');
        return JSON.stringify({seen: seen, stderr: recorded.stderr});
        """,
    )

    assert observed["seen"] == ["history"], observed
    assert len(observed["stderr"]) == 1, observed
    assert "panel refused" in observed["stderr"][0], observed


def test_the_preload_exposes_a_receiver_on_the_channel_the_shell_sends_on(
    js: Any,
) -> None:
    """``exposed.api.onPush`` subscribes on the channel ``shell.PUSH_CHANNEL`` names.

    A failure means the renderer hears on a channel ``broadcastPush`` never uses.
    """
    observed = _run(
        js,
        PRELOAD_STUBS,
        PRELOAD_JS,
        """
        var seen = [];
        var off = exposed.api.onPush(function (section, values) {
          seen.push({section: section, values: values});
        });
        var reached = deliver("acervator:push", "history", {bot: "live-only"});
        return JSON.stringify({
          world: exposed.name,
          api: Object.keys(exposed.api).sort(),
          channel: listeners[0].channel,
          reached: reached,
          seen: seen,
          off: typeof off
        });
        """,
    )
    channel = _run(
        js, MAIN_STUBS, MAIN_JS, "return JSON.stringify(shell.PUSH_CHANNEL);"
    )

    assert observed["world"] == "acervator", observed
    assert observed["api"] == ["call", "onPush"], observed
    assert observed["reached"] == 1, observed
    assert observed["channel"] == channel, (observed["channel"], channel)
    assert observed["seen"] == [{"section": "history", "values": {"bot": "live-only"}}]
    assert observed["off"] == "function", observed


def test_the_receiver_hands_back_the_way_to_stop_listening(js: Any) -> None:
    """``off`` takes the relay off ``listeners`` and the next send reaches nobody.

    A failure means ``onPush`` subscribes a handler that can never come off.
    """
    observed = _run(
        js,
        PRELOAD_STUBS,
        PRELOAD_JS,
        """
        var seen = [];
        var off = exposed.api.onPush(function (section) { seen.push(section); });
        var before = deliver("acervator:push", "history", {});
        off();
        var after = deliver("acervator:push", "history", {});
        return JSON.stringify({
          seen: seen,
          before: before,
          after: after,
          left: listeners.length
        });
        """,
    )

    assert observed["before"] == 1 and observed["after"] == 0, observed
    assert observed["seen"] == ["history"], observed
    assert observed["left"] == 0, observed
