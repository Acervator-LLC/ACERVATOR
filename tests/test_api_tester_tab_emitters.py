"""Pins the five API Tester emitters -- queue item #10.9, subsystem `apitest`.

    apitest.16.001.postcondition.label_matches_session
    apitest.16.002.postcondition.session_released
    apitest.16.003.postcondition.reported_ok_ran_a_test
    apitest.16.004.postcondition.green_probe_read_a_body
    apitest.16.005.postcondition.indicator_is_mappable

THIS IS THE ONLY TAB ON THE PLATFORM THAT HOLDS LIVE EXCHANGE API
CREDENTIALS IN MEMORY. `_api_key`, `_api_secret` and `_api_pp` are
`QLineEdit`s in `Password` echo mode, and `_do_connect` decrypts a
stored key out of the settings vault when "Use stored credentials" is
ticked. An emitter context is SERIALISED TO DISK, append-only, in plain
text, into `~/.acervator_logs/signals/`. One careless context field
would write the operator's live key into that file, and the operator
trades real money on those keys.

SO THE CREDENTIAL RULE IS THE GATE ON THIS MODULE, AND IT IS DRIVEN
TWICE, TWO DIFFERENT WAYS.
`test_no_context_expression_reads_a_credential_widget` walks the syntax
tree of all five pins and refuses any reference to the three credential
widgets or to the symbol box.
`test_no_sentinel_credential_reaches_the_serialised_records` puts a
known sentinel string into the key, the secret, the passphrase AND the
symbol box, drives every path in the tab that emits -- including a
venue error whose MESSAGE carries the sentinel, which is the way a real
key escapes -- writes every record with the sink's own writer, and
asserts the sentinel appears nowhere in the bytes on disk. That test
carries its own positive control: it asserts the file really holds the
five pin names first, because an absence proved against an empty file
is an absence of evidence.

NO TEST HERE REACHES A VENUE, AND THAT IS ENFORCED RATHER THAN
INTENDED. An autouse fixture replaces `socket.create_connection` -- the
single funnel every outbound TCP connection in this tree passes
through, `urllib` and `http.client` included -- with a tripwire that
RECORDS AND RAISES. A test that drives a network path replaces it in
turn with a counting fake, which is the seam, and asserts the count.
`test_no_test_in_this_module_reached_a_venue` reads the tripwire's
ledger at the end and asserts it is empty.

THE FAILURE SHAPE THIS TAB HAS IS A GREEN OVER NOTHING, and each pin
reports it in a different place: a connect that painted "Connected"
while holding no session (`16-001`), a disconnect that reports a closed
session while an AUTHENTICATED one is still open (`16-002`), a test
that logs `<test> OK` for a name the dispatch chain does not know
(`16-003`), a probe that reports HTTP 200 having read an empty body
(`16-004`), and a status verdict derived from a word the tab cannot map
(`16-005`). Every one of those five is driven here as a falsifier.

NOTHING READS AN ARGUMENT BACK AS THOUGH IT WERE A RESULT. `16-001` and
`16-002` read the connection label off the widget and the session off
the connector. `16-003` reads the headline off `_result_info` after
`_log` painted it, and reads the result object's own identity for the
other side. `16-004` counts two different things about the same probes.
`16-005` reads the word out of the parsed document.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`. The sink's
file is written under `tmp_path`.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import socket
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

import pytest

# `tests/conftest.py` puts the repository root on `sys.path` before any
# test module is imported, so these import normally rather than after a
# path insert. THAT IS WHY THERE IS NO `# noqa: E402` HERE: they are at
# the top because they belong there, not because a suppression was
# written over a real finding.
from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink

# Set before any fixture imports PySide6, which is this module's only
# route to Qt. Nothing above touches it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:                       # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope: the
    # source-reading tests below are pure Python and have to run on a box
    # without Qt. A skipped test is not evidence, so the skip is scoped
    # to the fixture and not to the module.
    from PySide6.QtWidgets import QApplication

CONNECTED = "apitest.16.001.postcondition.label_matches_session"
RELEASED = "apitest.16.002.postcondition.session_released"
RAN = "apitest.16.003.postcondition.reported_ok_ran_a_test"
PROBED = "apitest.16.004.postcondition.green_probe_read_a_body"
INDICATOR = "apitest.16.005.postcondition.indicator_is_mappable"

APITEST_PINS = (CONNECTED, RELEASED, RAN, PROBED, INDICATOR)

MAIN_WINDOW = REPO / "src" / "gui" / "main_window.py"

# The production geometry, restated so the tests drive the real thing.
COINBASE_PROBES = 3
STATUSPAGE_VOCABULARY = ("none", "minor", "major", "critical",
                         "maintenance")

# THE SENTINEL. Twenty characters of mixed case and digits, with no
# word and no punctuation in it, so that EVERY four-character window of
# it is also unlikely to appear in a file of JSON by accident. That
# property is what lets the test below hunt for fragments rather than
# only for the whole string.
#
# MEASURED, NOT ASSUMED. The first version of this test looked for the
# whole sentinel and for one word inside it. A planted leak of
# `self._api_key.text()[:6]` -- a six-character PREFIX, which is
# exactly how a key gets logged "safely" -- passed it. A prefix is a
# leak: it shrinks the search space for anyone holding the file. So
# the test now refuses every fragment of four characters or more, and
# the plant that slipped past is one of the mutations this unit was
# checked against.
SENTINEL = "Kx7qZv93RtLm5PwB2sYd"

# Substrings that must never appear in a record this tab writes. The
# first six are the credential vocabulary; `bot_id` is here because
# every other tab's register row forbids it and this tab is no
# exception.
FORBIDDEN = ("api_key", "apikey", "secret", "passphrase", "password",
             "credential", "token", "bot_id")

# The widgets whose text is a secret, plus the symbol box, which sits
# one row below three password fields and holds operator free text.
CREDENTIAL_WIDGETS = ("_api_key", "_api_secret", "_api_pp",
                      "_symbol_input")

# The two context KEYS allowed to contain a word from FORBIDDEN, named
# here so the ban stays a ban everywhere else. `credentials_supplied`
# is the one presence boolean this tab records; `used_stored_
# credentials` is the checkbox's own state and is not
# credential-derived at all. Both are KEYS. No VALUE anywhere in this
# tab is computed from a credential except the first of these two.
DECLARED_CREDENTIAL_KEYS = ("credentials_supplied",
                            "used_stored_credentials")


def _tcp_dials() -> int:
    """How many times `_raw_http_probe` dials before the sweep.

    Three diagnostics run above the endpoint loop: a raw TCP connect,
    an SSL handshake and an SSL handshake through certifi's CA bundle.
    The third is skipped by an `ImportError` guard on a box without
    certifi, so the count is READ from the interpreter rather than
    assumed.
    """
    import importlib.util

    return 3 if importlib.util.find_spec("certifi") is not None else 2


# Every outbound TCP connection the tripwire below intercepted. Read at
# the end of the module by `test_no_test_in_this_module_reached_a_venue`.
_ESCAPED: list = []


# ── the network tripwire ───────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_venue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every real outbound connection, and remember the attempt.

    `socket.create_connection` is the single funnel. `urllib`'s HTTPS
    handler reaches it through `http.client.HTTPConnection.connect`,
    and the tab's own TCP and SSL diagnostics call it directly, so one
    patch covers both routes.

    A test that needs a connection to appear to succeed replaces this
    with its own counting fake. That is the seam, and the count is
    asserted where it is used. Anything else lands in `_ESCAPED` AND
    raises, so a test that silently reached a venue fails here rather
    than passing quietly.
    """

    def _tripwire(address: Any, *args: Any, **kwargs: Any) -> Any:
        _ESCAPED.append((address, args, kwargs))
        message = (f"a test tried to reach the network: {address!r} "
                   f"{args!r} {kwargs!r}")
        raise AssertionError(message)

    monkeypatch.setattr(socket, "create_connection", _tripwire,
                        raising=True)


# ── Qt fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """The QApplication the widget tests run against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


# ── the stand-ins, each one a network seam ─────────────────────────────


class _StubExchange:
    """A ccxt exchange handle with no socket under it.

    `_run_test` resolves `_ccxt_sync` and calls these directly, so this
    is the object the tab's seven test buttons really talk to.
    """

    def __init__(self) -> None:
        self.markets = {"BTC/USDT": {"type": "spot"},
                        "ETH/USDT": {"type": "spot"}}
        self.calls: list[str] = []

    def fetch_ticker(self, symbol: str) -> dict:
        self.calls.append("fetch_ticker")
        return {"symbol": symbol, "bid": 1.0, "ask": 2.0, "last": 1.5}

    def fetch_balance(self) -> dict:
        self.calls.append("fetch_balance")
        return {"free": {"BTC": 1.0, "ETH": 0.0},
                "used": {}, "total": {"BTC": 1.0}}

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        self.calls.append("fetch_order_book")
        return {"symbol": symbol, "bids": [], "asks": [], "limit": limit}

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    limit: int = 50) -> list:
        self.calls.append(f"fetch_ohlcv {timeframe}")
        return [[0, 1.0, 2.0, 0.5, 1.5, 10.0]
                for _ in range(min(limit, 3))]

    def fetch_open_orders(self, symbol: str) -> list:
        self.calls.append(f"fetch_open_orders {symbol}")
        return []

    def fetch_my_trades(self, symbol: str, limit: int = 20) -> list:
        self.calls.append("fetch_my_trades")
        return [{"id": "1", "symbol": symbol}][:limit]


class _StubConnector:
    """A `CCXTConnector` with the network taken out from under it.

    THE KNOBS ARE CLASS ATTRIBUTES, reset by `_connector_class` for
    every test, so a test declares the fault it wants before the button
    is pressed.

    IT NEVER STORES A KEY. `calls` records presence booleans only, so
    even the test scaffolding cannot become the thing that leaks.
    """

    calls: list = []
    raise_on_connect: Exception | None = None
    leave_handle_empty: bool = False
    raise_on_disconnect: Exception | None = None
    built: list = []

    def __init__(self, exchange_id: str) -> None:
        self.exchange_id = exchange_id
        self.display_name = exchange_id.capitalize()
        self._ccxt = None
        self._ccxt_sync: Any = None
        self.closed = False
        type(self).built.append(exchange_id)

    def sync_connect(self, api_key: str, api_secret: str,
                     passphrase: str | None = None) -> None:
        type(self).calls.append(
            ("sync_connect", self.exchange_id,
             bool(api_key), bool(api_secret), bool(passphrase)))
        if type(self).raise_on_connect is not None:
            raise type(self).raise_on_connect
        if not type(self).leave_handle_empty:
            self._ccxt_sync = _StubExchange()

    @property
    def _ex(self) -> Any:
        """The handle every later call resolves through, as production."""
        return self._ccxt_sync or self._ccxt

    async def disconnect(self) -> None:
        type(self).calls.append(("disconnect", self.exchange_id))
        if type(self).raise_on_disconnect is not None:
            raise type(self).raise_on_disconnect
        self.closed = True

    def set_history_callback(self, callback: Any) -> None:
        type(self).calls.append(
            ("set_history_callback", callback is not None))

    @staticmethod
    def _format_exchange_error(exc: Exception) -> str:
        """What the tab paints into its own result view on a failure.

        The real one splices the venue's message, the URL and the
        response body together. This one does the same for the message,
        deliberately: the sentinel test needs the operator-facing text
        to CARRY the sentinel so that the record can be shown not to.
        """
        return f"{type(exc).__name__}: {exc}"


class _Response:
    """What `safe_urlopen` returns: a context manager over a body."""

    def __init__(self, body: bytes, status: int = 200,
                 headers: dict | None = None) -> None:
        self.status = status
        self.headers = headers or {"Content-Type": "application/json",
                                   "Content-Length": str(len(body))}
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: Any) -> None:
        """No exception is swallowed, which is what None says."""


class _Opener:
    """A counting stand-in for `safe_urlopen`. Makes no request."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []
        self.transport: list[tuple] = []

    def __call__(self, req: Any, timeout: float = 10.0,
                 context: Any = None) -> Any:
        self.urls.append(getattr(req, "full_url", str(req)))
        self.transport.append((timeout, context is not None))
        answer = (self.responses.pop(0) if self.responses
                  else _Response(b"{}"))
        if isinstance(answer, Exception):
            raise answer
        return answer


class _Socket:
    """A counting stand-in for a connected TCP socket."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_Socket":
        return self

    def __exit__(self, *exc: Any) -> None:
        """No exception is swallowed, which is what None says."""


class _Dialler:
    """A counting stand-in for `socket.create_connection`."""

    def __init__(self) -> None:
        self.addresses: list = []
        self.extras: list = []

    def __call__(self, address: Any, *args: Any, **kwargs: Any) -> _Socket:
        self.addresses.append(address)
        self.extras.append((args, kwargs))
        return _Socket()


@pytest.fixture()
def connector_class(monkeypatch: pytest.MonkeyPatch) -> type:
    """Install `_StubConnector` where `_do_connect` resolves the real one.

    `_do_connect` imports `CCXTConnector` from
    `src.exchange.ccxt_connector` INSIDE the method, on both the success
    and the failure branch, so the module attribute is the seam.
    """
    from src.exchange import ccxt_connector as cc

    _StubConnector.calls = []
    _StubConnector.built = []
    _StubConnector.raise_on_connect = None
    _StubConnector.leave_handle_empty = False
    _StubConnector.raise_on_disconnect = None
    monkeypatch.setattr(cc, "CCXTConnector", _StubConnector, raising=True)
    return _StubConnector


@contextlib.contextmanager
def _tab(qapp: QApplication, *,
         exchange_id: str = "coinbase") -> Iterator[Any]:
    """A REAL `APITesterTab`, parented to nothing and wired to nothing.

    The tab owns no timer and starts no thread, so there is nothing to
    stop on the way in. `_use_stored` is UNCHECKED, which is the manual
    path -- the one that reads the three password boxes -- because that
    is the path a credential can escape from.
    """
    from src.gui import main_window as mw

    tab = mw.APITesterTab()
    index = tab._exchange.findData(exchange_id)
    assert index >= 0, exchange_id
    tab._exchange.setCurrentIndex(index)
    tab._use_stored.setChecked(False)
    try:
        yield tab
    finally:
        tab.setParent(None)
        tab.deleteLater()
        qapp.processEvents()


# ── sink helpers ───────────────────────────────────────────────────────


@contextlib.contextmanager
def _collect(path: Path | None = None) -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None.

    `set_sink` is process-global; restoring None would switch the
    instrument off for whatever ran before this test. `path` is given
    only by the sentinel test, which needs the sink's own writer to put
    bytes on a disk -- under `tmp_path`, never under the operator's log
    directory.
    """
    sink = SignalSink(path=path, flush_every=1)
    previous = sc.get_sink()
    sc.reset_throttle()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)
        sc.reset_throttle()


def _records(sink: SignalSink, name: str) -> list:
    return [r for r in sink.records() if r.name == name]


def _only(sink: SignalSink, name: str) -> Any:
    """The single record under this name, or a failure that says so."""
    got = _records(sink, name)
    assert len(got) == 1, f"{name}: expected 1 record, got {len(got)}"
    return got[0]


def _last(sink: SignalSink, name: str) -> Any:
    got = _records(sink, name)
    assert got, f"{name}: no record"
    return got[-1]


def _statuspage(indicator: str = "none",
                description: str = "All Systems Operational") -> bytes:
    """One Statuspage v2 summary document, as the venues really serve it."""
    body: dict = {"page": {"id": "x"},
                  "status": {"description": description}}
    if indicator is not None:
        body["status"]["indicator"] = indicator
    return json.dumps(body).encode("utf-8")


# ── the syntax tree ────────────────────────────────────────────────────


def _apitest_emit_calls() -> list[ast.Call]:
    """Every `_api_emit(...)` call node in `main_window.py`.

    Read from the syntax tree, the way `tools/emitter_registry_check.py`
    reads them. A regex over the source would answer a different
    question. The alias is this tab's own, so the Exchange tab's
    `_ex_emit` calls cannot land in this set.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_api_emit"]


def _pin_name(call: ast.Call) -> str:
    first = call.args[0]
    assert isinstance(first, ast.Constant)
    return str(first.value)


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _class_node() -> ast.ClassDef:
    """The `APITesterTab` class node.

    Scoped to the class, because `_log` and `update_bots` and their kin
    are defined on several classes in this file and a tree-wide search
    would return whichever one `ast.walk` reached first.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "APITesterTab":
            return node
    message = f"APITesterTab not found in {MAIN_WINDOW}"
    raise AssertionError(message)


def _span(function: str) -> tuple[int, int]:
    """The first and last line of one method of `APITesterTab`."""
    for node in _class_node().body:
        if (isinstance(node, ast.FunctionDef) and node.name == function
                and node.end_lineno is not None):
            return (node.lineno, node.end_lineno)
    message = f"APITesterTab.{function} not found in {MAIN_WINDOW}"
    raise AssertionError(message)


# ── 16-001  the label agrees with the session ──────────────────────────


def test_a_connect_that_holds_a_session_is_green(
        qapp: QApplication, connector_class: type) -> None:
    """The ordinary case, so the red below is a verdict and not a mood."""
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        rec = _only(sink, CONNECTED)
        assert tab._conn_status.text().startswith("Connected")
        assert tab._connector is not None
    assert rec.ok is True, rec.context
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["exchange"] == "coinbase"
    assert rec.context["used_stored_credentials"] is False
    assert rec.context["credentials_supplied"] is True
    assert rec.context["connector_held"] is True
    assert rec.context["disconnect_enabled"] is True
    # The `sync_connect` bracket. A stub returns fast, so the only
    # honest assertion is that a real measurement was taken.
    assert rec.duration is not None
    assert rec.duration >= 0.0
    assert connector_class.calls[0][0] == "sync_connect"


def test_a_connected_label_over_no_session_is_reported(
        qapp: QApplication, connector_class: type) -> None:
    """THE FALSIFIER for `16-001`, and it is the tab's own failure shape.

    `sync_connect` returns without raising and leaves the connector
    with no exchange handle. The tab paints "Connected: Coinbase (0
    markets)", enables Disconnect and reports success -- and every
    button pressed afterwards resolves `None` and fails.
    """
    connector_class.leave_handle_empty = True
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        rec = _only(sink, CONNECTED)

        # THE FALSE GREEN, asserted on the widgets before the pin is
        # read. The pin is only worth anything if the tab really does
        # claim a connection it does not have.
        assert tab._conn_status.text().startswith("Connected")
        assert tab._disconnect_btn.isEnabled() is True
        assert tab._connector is not None
        assert tab._connector._ex is None

    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True
    assert rec.context["connector_held"] is True
    assert rec.context["credentials_supplied"] is True


def test_a_failed_connect_reports_an_honest_green(
        qapp: QApplication, connector_class: type) -> None:
    """A refusal by the venue: the label says Failed and nothing is held.

    The pin is in the `finally`, so this path is on the record. Both
    sides are False, which is agreement, and the record says the
    credentials WERE supplied -- which is what tells this apart from
    the empty-box refusal below.
    """
    connector_class.raise_on_connect = RuntimeError("venue said no")
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        rec = _only(sink, CONNECTED)
        assert tab._conn_status.text() == "Failed"
        assert tab._connector is None
        assert tab._connect_btn.isEnabled() is True
    assert rec.ok is True
    assert rec.actual is False
    assert rec.expected is False
    assert rec.context["credentials_supplied"] is True
    # NO DURATION: `sync_connect` raised, so nothing completed and a
    # number here would be fabricated.
    assert rec.duration is None


def test_an_empty_credential_box_refuses_and_says_so(
        qapp: QApplication, connector_class: type) -> None:
    """The early return inside the try is on the record too.

    The label is still "Connecting to ...", which does not start with
    "Connected", so the pin agrees with the screen. The presence
    boolean is what tells this refusal apart from the venue's.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("")
        tab._api_secret.setText("")
        tab._do_connect()
        rec = _only(sink, CONNECTED)
        assert tab._conn_status.text().startswith("Connecting")
        assert connector_class.built == []
    assert rec.ok is True
    assert rec.actual is False
    assert rec.expected is False
    assert rec.context["credentials_supplied"] is False
    assert rec.duration is None


# ── 16-002  the session was really released ────────────────────────────


def test_a_clean_disconnect_is_green(
        qapp: QApplication, connector_class: type) -> None:
    """Connect, disconnect, and the screen and the session agree."""
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        connector = tab._connector
        tab._do_disconnect()
        rec = _only(sink, RELEASED)
        assert connector.closed is True
        assert tab._connector is None
        assert tab._conn_status.text() == "Disconnected"
    assert rec.ok is True
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["exchange"] == "coinbase"
    assert rec.context["connector_held"] is True
    assert rec.context["failure_class"] == ""
    assert rec.duration is not None


def test_a_disconnect_that_left_the_session_open_is_reported(
        qapp: QApplication, connector_class: type) -> None:
    """THE FALSIFIER for `16-002`, and it is the worst state in the tab.

    The close raises inside the worker. `_do_disconnect` drops the
    connector reference anyway and writes "Disconnected", so an
    AUTHENTICATED SESSION stays open with nothing left that can reach
    it -- and the screen asserts the opposite.
    """
    connector_class.raise_on_disconnect = ConnectionResetError("boom")
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        connector = tab._connector
        tab._do_disconnect()
        rec = _only(sink, RELEASED)

        # THE STATE THE OPERATOR IS LEFT IN, asserted before the pin.
        assert connector.closed is False
        assert tab._connector is None
        assert tab._conn_status.text() == "Disconnected"

    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True
    assert rec.context["failure_class"] == "ConnectionResetError"
    # THE CLASS NAME AND NOT THE MESSAGE. "boom" stands in for a venue
    # error that quotes the request, and some echo the key.
    assert "boom" not in json.dumps(dict(rec.context))


def test_a_disconnect_with_nothing_connected_is_green(
        qapp: QApplication, connector_class: type) -> None:
    """The button is reachable with no connector, and reports honestly."""
    with _collect() as sink, _tab(qapp) as tab:
        tab._do_disconnect()
        rec = _only(sink, RELEASED)
    assert rec.ok is True
    assert rec.actual is True
    assert rec.context["connector_held"] is False
    # NO DURATION: there was no close to time.
    assert rec.duration is None


def _host_without_the_exchange_widget(connector: Any) -> Any:
    """The REAL `_do_disconnect` on a host that has no `_exchange`.

    `tests/test_main_window_suppression_repairs.py` drives this method
    exactly this way to cover the H3 disconnect repair without building
    a whole tab, and its host carries only what the method needed
    BEFORE `16-002` existed. Reproduced here rather than borrowed,
    because that file is testing something else and must not have to
    grow an attribute to carry this tab's instrumentation.
    """
    from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit

    from src.gui import main_window as mw

    names = ("_do_disconnect", "_log")
    host = type("NoExchangeHost", (),
                {name: getattr(mw.APITesterTab, name)
                 for name in names})()
    host._connector = connector
    host._connected = True
    host._connect_btn = QPushButton()
    host._disconnect_btn = QPushButton()
    host._conn_status = QLabel()
    host._result_info = QLabel()
    host._result_view = QTextEdit()
    assert not hasattr(host, "_exchange")
    return host


def test_the_pin_adds_no_precondition_to_its_host(
        qapp: QApplication, connector_class: type) -> None:
    """INSTRUMENTATION MAY NOT MAKE ITS HOST NEED MORE THAN IT DID.

    `16-002` reads `_exchange` for its context and nothing else in
    `_do_disconnect` touches that widget, so an unguarded read turned a
    pin into a precondition: a caller that had always been able to
    drive this method on a host without the combo box would raise
    AttributeError, and the pin would have taken down the thing it
    observes.

    THE VERDICT IS HELD AGAINST A REAL TAB, not against a restatement
    of it. The same clean disconnect is driven twice -- once on a real
    `APITesterTab` and once on the host that has no `_exchange` -- and
    the two records are compared field by field. `ok`, `actual`,
    `expected` and every context value but ONE are identical; the one
    that differs is `exchange`, which degrades to None on the host that
    cannot answer for it. A failure here means either the pin can raise
    inside its host again, or the guard has started costing something
    other than that single context field.
    """
    connector = connector_class("coinbase")
    with _collect() as sink:
        with _tab(qapp) as tab:
            tab._api_key.setText("k")
            tab._api_secret.setText("s")
            tab._do_connect()
            tab._do_disconnect()
        on_a_tab = _only(sink, RELEASED)

    host = _host_without_the_exchange_widget(connector)
    with _collect() as sink:
        # No `pytest.raises` and no try: an AttributeError here IS the
        # regression, and it must surface as this test's own failure.
        host._do_disconnect()
        hostless = _only(sink, RELEASED)

    assert connector.closed is True
    assert host._connector is None
    assert host._conn_status.text() == "Disconnected"

    assert hostless.ok is on_a_tab.ok is True
    assert hostless.actual is on_a_tab.actual is True
    assert hostless.expected is on_a_tab.expected is True
    assert hostless.duration is not None

    on_a_tab_context = dict(on_a_tab.context)
    hostless_context = dict(hostless.context)
    assert on_a_tab_context["exchange"] == "coinbase"
    assert hostless_context["exchange"] is None
    del on_a_tab_context["exchange"], hostless_context["exchange"]
    assert hostless_context == on_a_tab_context


# ── 16-003  the OK headline came from a call ───────────────────────────


def test_a_test_that_ran_is_green(
        qapp: QApplication, connector_class: type) -> None:
    """A real dispatch arm, through the stub handle, with a payload."""
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        tab._symbol_input.setText("BTC/USDT")
        tab._run_test("fetch_ticker")
        rec = _only(sink, RAN)
        assert tab._connector._ccxt_sync.calls == ["fetch_ticker"]
    assert rec.ok is True
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["test"] == "fetch_ticker"
    assert rec.context["result_kind"] == "dict"
    assert rec.context["result_entries"] == 4
    assert rec.context["truncated"] is False
    assert rec.duration is not None
    # THE SYMBOL IS NOT ON THE RECORD. It is operator free text from a
    # box one row below three password fields.
    assert "symbol" not in rec.context


def test_an_ok_headline_for_a_test_that_never_ran_is_reported(
        qapp: QApplication, connector_class: type) -> None:
    """THE FALSIFIER for `16-003`, and the arm is live in the source.

    The dispatch chain's last arm answers a name it does not know with
    an empty dict and falls straight through to the success log, so the
    operator reads `<test> OK` for a call that never happened.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        tab._run_test("fetch_everything")
        rec = _only(sink, RAN)

        # THE FALSE GREEN ON SCREEN, before the pin is read.
        assert tab._result_info.text().startswith("fetch_everything OK")
        assert tab._connector._ccxt_sync.calls == []

    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True
    assert rec.context["test"] == "fetch_everything"
    assert rec.context["result_entries"] == 0
    # NO DURATION on the arm that ran nothing.
    assert rec.duration is None


def test_a_failed_test_writes_no_success_record(
        qapp: QApplication, connector_class: type) -> None:
    """The failure branch has no pin, and that is deliberate.

    A test that raised paints `<test> FAILED` in red. There is no false
    green to report, and a record there would be a second name for
    something the operator already sees.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()

        def _boom(symbol: str) -> dict:
            message = "ticker exploded"
            raise RuntimeError(message)

        tab._connector._ccxt_sync.fetch_ticker = _boom
        tab._run_test("fetch_ticker")
        assert _records(sink, RAN) == []
        assert "FAILED" in tab._result_info.text()


def test_an_empty_list_result_is_still_green(
        qapp: QApplication, connector_class: type) -> None:
    """No open orders is a real answer, and must not read as nothing.

    This is the pin's boundary. A count-based `actual` would paint an
    honest empty result red, which is why the pin reads the result
    object's IDENTITY instead.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        tab._run_test("fetch_open_orders")
        rec = _only(sink, RAN)
    assert rec.ok is True
    assert rec.actual is True
    assert rec.context["result_kind"] == "list"
    assert rec.context["result_entries"] == 0


def test_a_test_pressed_before_connecting_writes_no_record(
        qapp: QApplication, connector_class: type) -> None:
    """The guard returns before anything runs, so nothing is claimed."""
    with _collect() as sink, _tab(qapp) as tab:
        tab._run_test("fetch_ticker")
        assert _records(sink, RAN) == []
        assert tab._result_info.text().startswith("ERROR")


# ── 16-004  every green probe read a body ──────────────────────────────


def _probe(qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
           responses: list) -> tuple:
    """Drive `_raw_http_probe` with the TCP dial and the opener cut.

    Returns the tab, the dialler and the opener so a caller can assert
    what was really attempted. The SSL diagnostics between the two are
    left alone: they receive the fake socket, the real `ssl` module
    refuses it, and the tab logs the refusal -- which is the honest
    outcome and reaches no venue.
    """
    from src.gui import main_window as mw

    dialler = _Dialler()
    opener = _Opener(responses)
    monkeypatch.setattr(socket, "create_connection", dialler, raising=True)
    monkeypatch.setattr(mw, "safe_urlopen", opener, raising=True)
    return dialler, opener


def test_every_green_probe_read_a_body(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """All three Coinbase endpoints answer with a body: green."""
    with _collect() as sink, _tab(qapp) as tab:
        dialler, opener = _probe(
            qapp, monkeypatch,
            [_Response(b'{"products": [1, 2]}'),
             _Response(b'{"data": []}'),
             _Response(b'[{"id": "BTC-USD"}]')])
        tab._raw_http_probe()
        rec = _only(sink, PROBED)
        assert set(dialler.addresses) == {("api.coinbase.com", 443)}
        assert len(dialler.addresses) == _tcp_dials()
        assert len(opener.urls) == COINBASE_PROBES
    assert rec.ok is True
    assert rec.actual == COINBASE_PROBES
    assert rec.expected == COINBASE_PROBES
    assert rec.context["exchange"] == "coinbase"
    assert rec.context["host"] == "api.coinbase.com"
    assert rec.context["endpoints"] == COINBASE_PROBES
    assert rec.context["attempted"] == COINBASE_PROBES
    assert rec.context["not_green"] == 0
    assert tuple(rec.context["http_statuses"]) == (200, 200, 200)
    assert rec.duration is not None


def test_a_green_probe_that_read_nothing_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE FALSIFIER for `16-004`.

    The middle endpoint answers 200 with an empty body. The tab paints
    the same green headline as the two that returned payloads, and the
    operator -- who is pressing this button because nothing else works
    -- reads three successes.
    """
    with _collect() as sink, _tab(qapp) as tab:
        _dialler, opener = _probe(
            qapp, monkeypatch,
            [_Response(b'{"products": [1]}'),
             _Response(b"", status=200,
                       headers={"Content-Type": "application/json"}),
             _Response(b'[{"id": "BTC-USD"}]')])
        tab._raw_http_probe()
        rec = _only(sink, PROBED)

        # THE FALSE GREEN ON SCREEN: three success headlines.
        assert tab._result_view.toPlainText().count("HTTP 200") == 3
        assert len(opener.urls) == COINBASE_PROBES

    assert rec.ok is False
    assert rec.actual == COINBASE_PROBES - 1
    assert rec.expected == COINBASE_PROBES
    assert rec.context["not_green"] == 0


def test_a_probe_that_raised_is_in_neither_count(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable endpoint is an error the operator already sees.

    It must not turn the pin red: the pin asks about the GREENS, and a
    reported failure is not a false green. `not_green` carries it.
    """
    import urllib.error

    with _collect() as sink, _tab(qapp) as tab:
        _dialler, opener = _probe(
            qapp, monkeypatch,
            [_Response(b'{"products": [1]}'),
             urllib.error.URLError("dns"),
             _Response(b'[{"id": "BTC-USD"}]')])
        tab._raw_http_probe()
        rec = _only(sink, PROBED)
        assert len(opener.urls) == COINBASE_PROBES
    assert rec.ok is True
    assert rec.actual == COINBASE_PROBES - 1
    assert rec.expected == COINBASE_PROBES - 1
    assert rec.context["attempted"] == COINBASE_PROBES
    assert rec.context["not_green"] == 1


def test_a_probe_that_never_reached_tcp_writes_no_record(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_raw_http_probe` returns before the sweep when TCP fails.

    Nothing was probed, so there is nothing to report and the pin is
    silent rather than green on an empty sweep.
    """
    from src.gui import main_window as mw

    def _refuse(address: Any, *args: Any, **kwargs: Any) -> Any:
        message = f"no route to {address!r} {args!r} {kwargs!r}"
        raise OSError(message)

    opener = _Opener([])
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)
    monkeypatch.setattr(mw, "safe_urlopen", opener, raising=True)
    with _collect() as sink, _tab(qapp) as tab:
        tab._raw_http_probe()
        assert _records(sink, PROBED) == []
        assert opener.urls == []
        assert "TCP FAILED" in tab._result_info.text()


# ── 16-005  the status word is one the tab can map ─────────────────────


def _status(qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
            body: bytes) -> Any:
    from src.gui import main_window as mw

    opener = _Opener([_Response(body)])
    monkeypatch.setattr(mw, "safe_urlopen", opener, raising=True)
    return opener


def test_a_status_page_the_tab_can_map_is_green(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """Coinbase's own document, with the published indicator."""
    with _collect() as sink, _tab(qapp) as tab:
        opener = _status(qapp, monkeypatch, _statuspage("none"))
        tab._check_exchange_status()
        rec = _only(sink, INDICATOR)
        assert opener.urls == [
            "https://status.coinbase.com/api/v2/status.json"]
    assert rec.ok is True
    assert rec.actual == "none"
    assert tuple(rec.expected) == STATUSPAGE_VOCABULARY
    assert rec.context["exchange"] == "coinbase"
    assert rec.context["http_status"] == 200
    assert rec.context["level_shown"] == "success"
    assert rec.context["body_bytes"] > 0
    assert rec.duration is not None


def test_a_declared_outage_is_still_a_green_verdict(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real outage is a word the tab CAN map, so the pin agrees.

    The pin judges the vocabulary, not the weather. `level_shown` says
    the operator was shown red.
    """
    with _collect() as sink, _tab(qapp) as tab:
        _status(qapp, monkeypatch, _statuspage("critical", "Major outage"))
        tab._check_exchange_status()
        rec = _only(sink, INDICATOR)
    assert rec.ok is True
    assert rec.actual == "critical"
    assert rec.context["level_shown"] == "error"


def test_a_missing_indicator_painted_as_an_outage_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE FALSIFIER for `16-005`.

    The document carries a `status` block with no `indicator`. The
    tab's own `get` supplies "unknown", the mapping sends everything
    outside none/minor to red, and the operator is shown an outage the
    venue never declared.
    """
    with _collect() as sink, _tab(qapp) as tab:
        _status(qapp, monkeypatch,
                json.dumps({"status": {"description": "?"}}).encode())
        tab._check_exchange_status()
        rec = _only(sink, INDICATOR)

        # THE FALSE RED ON SCREEN, before the pin is read.
        assert tab._result_info.text().startswith("STATUS: ?")

    assert rec.ok is False
    assert rec.actual == ""
    assert rec.context["level_shown"] == "error"


def test_an_untrusted_indicator_is_capped_before_it_is_recorded(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """The word is venue text, so its length on the record is bounded."""
    with _collect() as sink, _tab(qapp) as tab:
        _status(qapp, monkeypatch, _statuspage("z" * 500))
        tab._check_exchange_status()
        rec = _only(sink, INDICATOR)
    assert rec.ok is False
    assert rec.actual == "z" * 32


def test_an_exchange_with_no_status_page_writes_no_record(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """The method returns before any fetch, and claims nothing."""
    from src.gui import main_window as mw

    opener = _Opener([])
    monkeypatch.setattr(mw, "safe_urlopen", opener, raising=True)
    with _collect() as sink, _tab(qapp, exchange_id="gemini") as tab:
        tab._check_exchange_status()
        assert _records(sink, INDICATOR) == []
        assert opener.urls == []


# ── the credential gate ────────────────────────────────────────────────


def test_no_context_expression_reads_a_credential_widget() -> None:
    """THE RULE, held against the syntax tree of all five pins.

    Every expression that reaches `actual`, `expected` or any context
    value is walked. A reference to `_api_key`, `_api_secret`, `_api_pp`
    or `_symbol_input` fails the test wherever it appears -- as a value,
    as a length, as a hash, or as anything else.
    """
    calls = _apitest_emit_calls()
    assert len(calls) == 5

    for call in calls:
        judged: list[ast.expr] = list(call.args[1:])
        for field in ("actual", "expected", "ok", "duration", "context"):
            node = _keyword(call, field)
            if node is not None:
                judged.append(node)
        rendered = " ".join(ast.dump(node) for node in judged)
        for widget in CREDENTIAL_WIDGETS:
            assert widget not in rendered, (_pin_name(call), widget)
        # The two declared KEYS are removed before the ban is applied,
        # so `credentials_supplied` cannot launder a real hit on
        # "credential" past this test.
        stripped = rendered.lower()
        for declared in DECLARED_CREDENTIAL_KEYS:
            stripped = stripped.replace(declared, "")
        for banned in FORBIDDEN:
            assert banned not in stripped, (_pin_name(call), banned)


def test_the_presence_boolean_is_the_only_credential_derived_value(
) -> None:
    """One boolean, named, and it is a `bool()` of nothing else.

    `credentials_supplied` is the single value in this tab computed
    from a credential. This test reads the expression it is bound from
    and asserts it is exactly `bool(key) and bool(secret)` -- so a
    later edit that made it a length, a prefix or a hash fails here.
    """
    source = MAIN_WINDOW.read_text(encoding="utf-8")
    tree = ast.parse(source)
    bindings = [node for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_supplied"
                        for t in node.targets)]
    assert len(bindings) == 2, "expected the None seed and one binding"
    expressions = sorted(ast.unparse(node.value) for node in bindings)
    assert expressions == ["False", "bool(key) and bool(secret)"]


def test_no_sentinel_credential_reaches_the_serialised_records(
        qapp: QApplication, connector_class: type,
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """THE GATE ON THIS UNIT, driven end to end against the real writer.

    A known sentinel goes into the key, the secret, the passphrase AND
    the symbol box. Every path in the tab that emits is driven --
    including a venue error whose MESSAGE carries the sentinel, which
    is how a real key escapes, and the stored-credentials path. The
    records are then written by `SignalSink.flush`, the sink's own
    writer, into a file under `tmp_path`, and the bytes are searched.

    THE POSITIVE CONTROL COMES FIRST. The file is asserted to hold all
    five pin names before the sentinel is looked for, because an
    absence proved against an empty file is an absence of evidence.
    """
    from src.gui import main_window as mw

    path = tmp_path / "signals" / "session.jsonl"
    opener = _Opener([_Response(b'{"products": [1]}'),
                      _Response(b""),
                      _Response(b'[{"id": "x"}]'),
                      _Response(_statuspage("none"))])
    dialler = _Dialler()

    with _collect(path) as sink, _tab(qapp) as tab:
        monkeypatch.setattr(socket, "create_connection", dialler,
                            raising=True)
        monkeypatch.setattr(mw, "safe_urlopen", opener, raising=True)

        tab._api_key.setText(SENTINEL)
        tab._api_secret.setText(SENTINEL)
        tab._api_pp.setText(SENTINEL)
        tab._symbol_input.setText(SENTINEL)

        # 1. a connect that works, 2. a test that ran, 3. the
        # do-nothing arm, 4. the probe sweep, 5. the status page,
        # 6. a disconnect that failed.
        tab._do_connect()
        tab._run_test("fetch_ticker")
        # The do-nothing arm. Its name is NOT the sentinel: `test` is
        # the fixed vocabulary the seven buttons pass and is recorded
        # deliberately, so feeding the sentinel in here would be this
        # test putting it on the record itself rather than the tab
        # leaking it.
        tab._run_test("fetch_everything")
        tab._raw_http_probe()
        tab._check_exchange_status()
        connector_class.raise_on_disconnect = RuntimeError(SENTINEL)
        tab._do_disconnect()

        # 7. A VENUE ERROR THAT ECHOES THE KEY. This is the shape that
        # puts a live credential into an error message, and the tab
        # paints it into its own result view.
        connector_class.raise_on_connect = RuntimeError(
            f"401 unauthorized for key={SENTINEL}")
        tab._do_connect()

        # 8. the stored-credentials branch, which reaches the settings
        # vault and returns before any network call.
        tab._use_stored.setChecked(True)
        tab._do_connect()

        # The operator really can see the sentinel on screen. That is
        # the widget, not a file, and it is where a secret is allowed
        # to be.
        assert SENTINEL in tab._result_view.toPlainText()

        sink.flush()

    written = path.read_bytes()

    # THE POSITIVE CONTROL.
    for name in APITEST_PINS:
        assert name.encode() in written, name
    assert written.count(b"\n") >= len(APITEST_PINS)

    # THE GATE, AND IT REFUSES FRAGMENTS.
    #
    # A prefix, a suffix or any middle run of four characters or more
    # is a leak: it shrinks the search space for anyone holding the
    # file, and a "safe" last-four or first-six is the commonest way a
    # key reaches a log. A HASH is a leak too, because a secret this
    # short is brute-forceable, so the three digests of the whole
    # sentinel and of its head are refused by name.
    text = written.decode("utf-8", errors="replace")
    for start in range(len(SENTINEL)):
        for end in range(start + 4, len(SENTINEL) + 1):
            fragment = SENTINEL[start:end]
            assert fragment not in text, fragment

    for value in (SENTINEL, SENTINEL[:8], SENTINEL[-4:]):
        for algorithm in ("md5", "sha1", "sha256"):
            digest = hashlib.new(algorithm, value.encode()).hexdigest()
            assert digest not in text, (algorithm, value)

    # A LENGTH IS A LEAK TOO, and it is the one fragment hunting cannot
    # see. Nothing in this tab may record it, which is why
    # `test_no_context_expression_reads_a_credential_widget` reads the
    # syntax tree: that test is this one's other half, not a
    # duplicate.
    for record in sink.records():
        rendered = record.to_json()
        assert SENTINEL not in rendered, record.name
        assert SENTINEL not in record.message(), record.name


def test_no_record_from_this_tab_carries_a_forbidden_key(
        qapp: QApplication, connector_class: type,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The context KEYS are read at run time, not from the source.

    The syntax-tree test above reads the literals. This one reads the
    dictionaries the sink really received, so a key built at run time
    would be caught too.
    """
    from src.gui import main_window as mw

    monkeypatch.setattr(socket, "create_connection", _Dialler(),
                        raising=True)
    monkeypatch.setattr(mw, "safe_urlopen",
                        _Opener([_Response(_statuspage("none"))]),
                        raising=True)
    with _collect() as sink, _tab(qapp) as tab:
        tab._api_key.setText("k")
        tab._api_secret.setText("s")
        tab._do_connect()
        tab._run_test("fetch_ticker")
        tab._check_exchange_status()
        tab._do_disconnect()
        assert len(sink.records()) == 4
        for record in sink.records():
            for key in (record.context or {}):
                if key in DECLARED_CREDENTIAL_KEYS:
                    continue
                for banned in FORBIDDEN:
                    assert banned not in key.lower(), (record.name, key)


# ── the shape, read off the syntax tree ────────────────────────────────


def test_every_pin_in_this_tab_carries_a_duration() -> None:
    """E8 in this tab: all five may, and all five do.

    Every site sits behind a network operation, which is what the other
    five instrumented tabs mostly do not have. The value is None on
    every path where no operation completed, which the pin tests above
    assert one by one.
    """
    carriers = {_pin_name(call) for call in _apitest_emit_calls()
                if _keyword(call, "duration") is not None}
    assert carriers == set(APITEST_PINS)


def test_no_pin_in_this_tab_carries_a_throttle() -> None:
    """Item #14 reads this, so it is asserted and not narrated.

    Every path in this tab is a button press. Silence from any of these
    five says nothing about the tab's health, so none may fold.
    """
    for call in _apitest_emit_calls():
        assert _keyword(call, "every") is None, _pin_name(call)


def test_the_tab_owns_no_timer_so_a_finger_is_the_only_cadence() -> None:
    """The claim behind the test above, read off the class.

    A `QTimer` inside this class would give one of these pins a clock
    and make its silence readable -- which is the promise the register
    says this tab does not make.
    """
    source = ast.unparse(_class_node())
    assert "QTimer" not in source


def test_each_pin_sits_in_the_method_the_register_claims() -> None:
    """The cadence is a property of WHERE each pin sits."""
    placed = {_pin_name(call): call.lineno
              for call in _apitest_emit_calls()}
    assert set(placed) == set(APITEST_PINS)

    for method, expected in (
            ("_do_connect", {CONNECTED}),
            ("_do_disconnect", {RELEASED}),
            ("_run_test", {RAN}),
            ("_raw_http_probe", {PROBED}),
            ("_check_exchange_status", {INDICATOR})):
        low, high = _span(method)
        inside = {name for name, line in placed.items()
                  if low <= line <= high}
        assert inside == expected, method


def test_every_emitting_method_is_reached_by_exactly_one_button() -> None:
    """The cadence claim, held against the constructor's own wiring.

    Each of the five methods is connected once in `__init__` and from
    nowhere else in the class, so the operator's finger really is the
    rate limit.
    """
    klass = _class_node()
    connected: list[str] = []
    for node in ast.walk(klass):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect"):
            continue
        for argument in node.args:
            connected.append(ast.unparse(argument))

    for method in ("_do_connect", "_do_disconnect", "_raw_http_probe",
                   "_check_exchange_status"):
        hits = [c for c in connected if c.endswith(method)]
        assert len(hits) == 1, (method, hits)

    # `_run_test` is connected once, inside the loop that builds the
    # seven test buttons, through a lambda that binds the command.
    runs = [c for c in connected if "_run_test" in c]
    assert len(runs) == 1, runs
    assert runs[0].startswith("lambda")


def test_no_two_pins_share_a_line() -> None:
    """One pin per line.

    `signal_contract` keys both the fold window and the timing identity
    on (name, site), and `site` is `file:line`. Two pins on one line
    would be one identity to the wire and two to a reader.
    """
    lines = [call.lineno for call in _apitest_emit_calls()]
    assert len(lines) == len(set(lines)) == 5


def test_no_pin_compares_an_expression_with_itself() -> None:
    """E9, asked of this tab by the checker's own rule."""
    from tools.emitter_registry_check import collect_pins

    pins = [pin for pin in collect_pins(MAIN_WINDOW, REPO)
            if pin.name.startswith("apitest.")]
    assert len(pins) == 5
    assert [pin.name for pin in pins if pin.vacuous_check] == []
    assert [pin.name for pin in pins if not pin.carries_duration] == []


def test_every_context_names_its_exchange() -> None:
    """Without it a reader cannot tell which venue a record is about."""
    for call in _apitest_emit_calls():
        node = _keyword(call, "context")
        assert isinstance(node, ast.Dict), _pin_name(call)
        keys = [key.value for key in node.keys
                if isinstance(key, ast.Constant)]
        assert "exchange" in keys, _pin_name(call)


def test_the_register_row_for_every_pin_points_at_its_real_line() -> None:
    """The register is the join, and a stale line makes it a guess.

    The checker reports line drift as a WARNING and does not fail on
    it, which is a stated blind spot. This closes it for this tab's
    five rows.
    """
    from tools.emitter_registry_check import (
        REGISTRY_PATH,
        collect_pins,
        parse_registry,
    )

    registry = parse_registry(
        (REPO / REGISTRY_PATH).read_text(encoding="utf-8"))
    assert registry.parse_errors == []
    rows = {row.name: row for row in registry.rows
            if row.subsystem == "apitest"}
    assert set(rows) == set(APITEST_PINS)

    pins = {pin.name: pin for pin in collect_pins(MAIN_WINDOW, REPO)
            if pin.name.startswith("apitest.")}
    for name, row in rows.items():
        assert row.file == "src/gui/main_window.py", name
        assert row.line == pins[name].line, (
            f"{name}: register says {row.line}, the pin is at "
            f"{pins[name].line}")


# ── the tab still behaves exactly as it did ────────────────────────────


def _dump(tab: Any) -> tuple:
    """Everything the operator can see, with the clock taken out.

    `_log` stamps `[HH:MM:SS]` and `(NNms)` into the result view, and
    both move between two runs of the same script for reasons that have
    nothing to do with a collector being attached.
    """
    import re

    text = tab._result_view.toPlainText()
    text = re.sub(r"\[\d\d:\d\d:\d\d\]", "[--:--:--]", text)
    text = re.sub(r"\(\d+ms\)", "(--ms)", text)
    headline = re.sub(r"\(\d+ms\)", "(--ms)", tab._result_info.text())
    return (headline,
            tab._result_info.styleSheet(),
            text,
            tab._conn_status.text(),
            tab._conn_status.styleSheet(),
            tab._connect_btn.isEnabled(),
            tab._disconnect_btn.isEnabled(),
            tab._manual_frame.isVisible(),
            tab._connector is None,
            tab._connected)


def _script(qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
            connector_class: type) -> tuple:
    """One fixed operator script, run against whatever sink is installed."""
    from src.gui import main_window as mw

    connector_class.raise_on_connect = None
    connector_class.raise_on_disconnect = None
    connector_class.leave_handle_empty = False
    monkeypatch.setattr(socket, "create_connection", _Dialler(),
                        raising=True)
    monkeypatch.setattr(
        mw, "safe_urlopen",
        _Opener([_Response(b'{"products": [1]}'),
                 _Response(b""),
                 _Response(b'[{"id": "x"}]'),
                 _Response(_statuspage("none"))]),
        raising=True)

    with _tab(qapp) as tab:
        tab._api_key.setText("key-value")
        tab._api_secret.setText("secret-value")
        tab._do_connect()
        tab._symbol_input.setText("BTC/USDT")
        tab._run_test("fetch_ticker")
        tab._run_test("fetch_open_orders")
        tab._run_test("not_a_test")
        tab._raw_http_probe()
        tab._check_exchange_status()
        tab._do_disconnect()
        tab._do_disconnect()
        return _dump(tab)


def test_the_tab_renders_and_behaves_the_same_with_and_without_a_sink(
        qapp: QApplication, connector_class: type,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The pins observe and change nothing.

    The same fourteen-step script runs with no collector installed and
    then with a real one, and every widget the operator can see is
    compared byte for byte.
    """
    previous = sc.get_sink()
    sc.set_sink(None)
    try:
        without = _script(qapp, monkeypatch, connector_class)
    finally:
        sc.set_sink(previous)

    with _collect() as sink:
        with_sink = _script(qapp, monkeypatch, connector_class)
        assert len(sink.records()) == 8

    assert with_sink == without


def test_the_behaviour_probe_would_notice_a_change(
        qapp: QApplication, connector_class: type,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The positive control for the test above.

    A comparison that cannot fail proves nothing, so one character of
    the connection label is changed and the dump is asserted to move.
    """
    with _collect():
        baseline = _script(qapp, monkeypatch, connector_class)

    with _tab(qapp) as tab:
        tab._conn_status.setText("Disconnected.")
        moved = _dump(tab)

    assert moved[3] != baseline[3]


# ── the network gate, read last ────────────────────────────────────────


def test_no_test_in_this_module_reached_a_venue() -> None:
    """The tripwire's ledger, read after everything above has run.

    `socket.create_connection` is the single funnel for every outbound
    TCP connection in this tree. A test that forgot a stub raised at
    the attempt; this reports any attempt that happened at all, so the
    safety claim is a measurement rather than a design intention.
    """
    assert _ESCAPED == []
