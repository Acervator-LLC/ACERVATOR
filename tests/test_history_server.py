"""The React History panel is served over loopback HTTP, and cannot trade.

FOUR PROPERTIES, EACH ABLE TO FAIL ON ITS OWN

    1. THE SERVER SERVES. A real socket on 127.0.0.1 answers the shell,
       the assets and the data endpoint. The assertions read the bytes
       that came back over the wire, not the functions that built them.
    2. THE DATA ENDPOINT CARRIES WHAT THE FRONTEND READS. Every key in
       ``history_panel.js``'s ``REQUIRED_KEYS`` is asserted by name, and
       so is every field its ``Cell``, ``Row`` and ``Pager`` components
       read. Dropping one turns this file red.
    3. NO QT IN THE SERVING PATH. The import closure of
       ``src.web.history_server`` is walked, and the closure is then
       re-imported with ``import PySide6`` raising and asked to serve.
    4. NO ORDER PATH. The same closure is walked for any call to an
       order-placing name. ``test_order_path_walk_reports_a_reacher``
       points that walk at a module that does reach one.

THE VACUOUS-PASS CONTROL

A server that answers an empty payload agrees with every claim about
what it does not carry. Every payload assertion below runs after a
non-empty row check, and ``test_payload_control_no_rows_is_caught``
proves that check fails when it should.
"""

from __future__ import annotations

import ast
import http.client
import importlib
import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange import history_read_contract as hrc
from src.web import history_server as hs

BASE_TS = 1_750_000_000.0

REQUEST_TIMEOUT_S = 10.0
"""Every request here is to a socket on this machine. One that needs
longer than this is hung, not slow."""

FRONTEND_REQUIRED_KEYS = (
    "columns",
    "page",
    "summary",
    "filters",
    "filter_options",
    "loaded",
)
"""``history_panel.js:REQUIRED_KEYS``. A payload missing any of these
draws the error banner instead of the table."""

CELL_FIELDS = ("key", "value", "text", "color", "tooltip")
"""What ``history_panel.js:Cell`` reads off every cell."""

PAGE_FIELDS = (
    "rows",
    "page",
    "pages",
    "total",
    "page_size",
    "page_label",
    "prev_enabled",
    "next_enabled",
)
"""What ``history_panel.js:Panel`` and ``Pager`` read off the page."""

ORDER_CALL_NAMES = frozenset(
    {
        "place_order",
        "create_order",
        "cancel_order",
        "edit_order",
        "create_market_buy_order",
        "create_market_sell_order",
        "create_limit_buy_order",
        "create_limit_sell_order",
    }
)
"""Names that submit or withdraw an order at a venue. ``place_order`` is
declared at ``src/exchange/base.py:216``; the ``create_*`` and
``cancel_order`` names are the ccxt calls
``src/exchange/ccxt_connector.py`` makes."""

QT_ROOTS = frozenset({"PySide6", "PyQt5", "PyQt6", "shiboken6"})


# -- fixtures ----------------------------------------------------------


def _reader_of(entries: list) -> Any:
    """A FRESH iterator per call, as the live-log readers give."""

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter(list(entries))

    return _read


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read EMPTY live logs. Without this the suite parses the
    operator's gate log."""
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of([]))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of([]))


def _row(
    tid: str,
    symbol: str = "CHIP/USD",
    exchange: str = "coinbase",
    side: str = "BUY",
    ts: float = BASE_TS,
    price: float = 10.0,
    amount: float = 2.0,
    fee: float = 0.01,
) -> dict:
    """One normalized row, the shape ``normalize_trade`` returns."""
    return {
        "id": tid,
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": price,
        "cost": amount * price,
        "fee": fee,
        "fee_currency": "USD",
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc),
    }


def _mixed_rows(count: int = 7) -> list:
    """Newest-first rows that differ in every column a renderer could
    ignore."""
    return [
        _row(
            f"{'chip' if i % 2 == 0 else 'rave'}-{i}",
            symbol="CHIP/USD" if i % 2 == 0 else "RAVE/USD",
            exchange="coinbase" if i % 3 else "kraken",
            side="BUY" if i % 2 == 0 else "SELL",
            ts=BASE_TS - i * 60,
            price=10.0 + i * 1.5,
            amount=0.5 + i,
            fee=0.01 * (i + 1),
        )
        for i in range(count)
    ]


def _run(server: hs.HistoryServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _stop(server: hs.HistoryServer, thread: threading.Thread) -> None:
    server.shutdown()
    thread.join(timeout=REQUEST_TIMEOUT_S)
    server.server_close()


@pytest.fixture
def served() -> Iterator[hs.HistoryServer]:
    """A live server on a free loopback port, closed on the way out.

    ``port=0`` asks the kernel for a free port, so two suite runs at
    once cannot collide, and ``server_close`` releases it.
    """
    server = hs.HistoryServer(_mixed_rows, port=0)
    thread = _run(server)
    try:
        yield server
    finally:
        _stop(server, thread)


def _request(
    server: hs.HistoryServer, path: str, method: str = "GET"
) -> tuple[int, bytes, str]:
    """Status, body and Content-Type for one request over a real socket.

    ``http.client`` and not a URL opener: the connection names the host
    and port directly, so no scheme can be substituted for ``http``.
    """
    connection = http.client.HTTPConnection(
        hs.LOOPBACK_HOST, server.port, timeout=REQUEST_TIMEOUT_S
    )
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return (
            response.status,
            response.read(),
            response.headers.get("Content-Type", ""),
        )
    finally:
        connection.close()


# -- 1. the server serves ----------------------------------------------


def test_the_server_binds_loopback_only(served: hs.HistoryServer) -> None:
    """A bind on any other interface puts the operator's trade history
    on the network."""
    assert served.server_address[0] == "127.0.0.1"
    assert hs.LOOPBACK_HOST == "127.0.0.1"
    assert served.url == f"http://127.0.0.1:{served.port}"


def test_the_shell_loads_every_asset_it_names(served: hs.HistoryServer) -> None:
    """A shell naming an asset the server does not serve draws a blank
    page in the browser, and nothing else here would say so."""
    status, body, content_type = _request(served, "/")
    assert status == 200
    assert content_type == hs.HTML_CONTENT_TYPE
    html = body.decode("utf-8")
    named = re.findall(r'"(' + hs.ASSET_PREFIX + r'[^"]+)"', html)
    assert len(named) == 4, named
    for path in named:
        asset_status, asset_body, _ = _request(served, path)
        assert asset_status == 200, path
        assert asset_body, path


def test_the_shell_hands_the_endpoint_to_the_panel(served: hs.HistoryServer) -> None:
    """The bootstrap is the only wire between the data endpoint and the
    renderer. Without it the page draws the error banner."""
    html = _request(served, "/")[1].decode("utf-8")
    assert hs.DATA_ROUTE in html
    assert "window.acervatorSetState" in html


def test_the_assets_are_the_files_on_disk(served: hs.HistoryServer) -> None:
    """A served asset that differs from the file the Qt host inlines is
    a second copy of the frontend."""
    for name, expected_type in (
        ("history_panel.js", hs.ASSET_CONTENT_TYPES[".js"]),
        ("history_panel.css", hs.ASSET_CONTENT_TYPES[".css"]),
        ("vendor/react.production.min.js", hs.ASSET_CONTENT_TYPES[".js"]),
    ):
        status, body, content_type = _request(served, hs.ASSET_PREFIX + name)
        assert status == 200, name
        assert content_type == expected_type, name
        assert body == (hs.asset_dir() / name).read_bytes(), name


def test_an_unknown_route_is_404(served: hs.HistoryServer) -> None:
    """A 200 for a route the server does not implement lets a missing
    endpoint read as a working one."""
    status, body, content_type = _request(served, "/api/orders")
    assert status == 404
    assert content_type == hs.JSON_CONTENT_TYPE
    assert "error" in json.loads(body.decode("utf-8"))


# -- 2. the data endpoint carries what the frontend reads --------------


def _payload(server: hs.HistoryServer, query: str = "") -> dict:
    status, body, content_type = _request(server, hs.DATA_ROUTE + query)
    assert status == 200
    assert content_type == hs.JSON_CONTENT_TYPE
    return json.loads(body.decode("utf-8"))


def test_the_endpoint_carries_every_key_the_frontend_requires(
    served: hs.HistoryServer,
) -> None:
    """A payload missing one of these draws the error banner, not the
    table."""
    payload = _payload(served)
    assert payload["page"]["rows"], "vacuous: no rows to disagree about"
    missing = [key for key in FRONTEND_REQUIRED_KEYS if key not in payload]
    assert missing == [], missing


def test_the_endpoint_carries_every_page_and_cell_field(
    served: hs.HistoryServer,
) -> None:
    """A cell missing ``text`` or ``color`` draws blank or uncoloured,
    and the contract stops being what the screen shows."""
    payload = _payload(served)
    page = payload["page"]
    assert page["rows"], "vacuous: no rows to disagree about"
    for name in PAGE_FIELDS:
        assert name in page, name
    for row in page["rows"]:
        assert row["trade_id"]
        assert len(row["cells"]) == len(hrc.COLUMNS)
        for cell in row["cells"]:
            for name in CELL_FIELDS:
                assert name in cell, (row["trade_id"], cell.get("key"), name)


def test_the_endpoint_agrees_with_the_contract_cell_for_cell(
    served: hs.HistoryServer,
) -> None:
    """The served text is the contract's text. A server that formatted a
    number of its own would be the second implementation of History."""
    payload = _payload(served)
    rows = payload["page"]["rows"]
    assert rows, "vacuous: no rows to disagree about"
    expected = hrc.build_page(hrc.sort_trades(_mixed_rows()), 0, None)
    assert len(rows) == len(expected.rows)
    for served_row, expected_row in zip(rows, expected.rows):
        assert served_row["trade_id"] == expected_row.trade_id
        for cell, expected_cell in zip(served_row["cells"], expected_row.cells):
            assert cell["key"] == expected_cell.key
            assert cell["text"] == expected_cell.text
            assert cell["color"] == expected_cell.color


def test_the_endpoint_reads_its_filters_off_the_query(
    served: hs.HistoryServer,
) -> None:
    """A query the server ignored would serve the unfiltered page while
    reporting the filter as applied."""
    payload = _payload(served, "?side=SELL&symbol=RAVE/USD")
    assert payload["filters"]["side"] == "SELL"
    assert payload["filters"]["symbol"] == "RAVE/USD"
    rows = payload["page"]["rows"]
    assert rows, "vacuous: no rows to disagree about"
    for row in rows:
        cells = {cell["key"]: cell["text"] for cell in row["cells"]}
        assert cells["side"] == "SELL"
        assert cells["symbol"] == "RAVE/USD"


def test_the_endpoint_serves_the_page_the_query_names() -> None:
    """A server that ignored ``page`` would serve page 0 forever."""
    trades = [_row(f"p-{i:04d}", ts=BASE_TS - i * 60) for i in range(hrc.PAGE_SIZE + 5)]
    first = hs.history_payload(trades, "page=0")
    second = hs.history_payload(trades, "page=1")
    assert len(first["page"]["rows"]) == hrc.PAGE_SIZE
    assert len(second["page"]["rows"]) == 5
    assert first["page"]["rows"][0]["trade_id"] != second["page"]["rows"][0]["trade_id"]


def test_the_default_source_serves_no_trades() -> None:
    """The entry point's source. A source that reached an exchange would
    need a credential."""
    assert hs.no_trades() == []
    payload = hs.history_payload(hs.no_trades(), "")
    assert payload["loaded"] == 0
    assert payload["page"]["rows"] == []


def test_the_entry_point_binds_loopback_and_serves_no_trades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main`` is what a host starts. A bind off loopback, or a source
    other than the empty one, would put this process on the network or
    give it a reason to hold a credential."""
    seen: dict = {}

    def _record(server: hs.HistoryServer) -> None:
        seen["address"] = server.server_address
        seen["source"] = server.trade_source

    monkeypatch.setattr(hs.HistoryServer, "serve_forever", _record)
    assert hs.main(["--port", "0"]) == 0
    assert seen["address"][0] == hs.LOOPBACK_HOST
    assert seen["source"] is hs.no_trades


def test_payload_control_no_rows_is_caught() -> None:
    """THE VACUOUS-PASS CONTROL. Every assertion above runs after a
    non-empty row check; this shows that check fails when it should."""
    payload = hs.history_payload([], "")
    with pytest.raises(AssertionError):
        assert payload["page"]["rows"], "vacuous: no rows to disagree about"


# -- 3. no Qt in the serving path --------------------------------------


def _module_path(name: str) -> Path:
    return REPO / Path(*name.split(".")).with_suffix(".py")


def _imports_of(name: str) -> tuple[set, set]:
    """(dotted names imported, top-level roots imported) for one module.

    Reads function-local imports as well as top-level ones: a deferred
    import reaches the same code at run time, and a walk that skipped it
    would report a closure smaller than the one that runs.
    """
    dotted: set = set()
    roots: set = set()
    path = _module_path(name)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dotted.add(alias.name)
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            dotted.add(node.module)
            dotted.update(f"{node.module}.{a.name}" for a in node.names)
            roots.add(node.module.split(".")[0])
    return dotted, roots


def import_closure(entry: str) -> tuple[set, set]:
    """Every first-party module reachable from ``entry``, and every
    third-party root any of them imports."""
    modules: set = set()
    roots: set = set()
    queue = [entry]
    while queue:
        name = queue.pop()
        if name in modules or not _module_path(name).is_file():
            continue
        modules.add(name)
        dotted, module_roots = _imports_of(name)
        roots |= module_roots
        queue.extend(dotted)
    return modules, roots


def test_the_serving_closure_names_no_qt_module() -> None:
    """A Qt import in the serving path makes the server need a display
    and defeats the React boundary."""
    modules, roots = import_closure("src.web.history_server")
    assert "src.exchange.history_read_contract" in modules
    assert "src.web.history_view_model" in modules
    assert QT_ROOTS & roots == set()


def test_the_closure_walk_reports_a_qt_importer() -> None:
    """THE CONTROL for the walk above. Pointed at a module that does
    import Qt, it must say so."""
    _, roots = import_closure("src.gui.react_history_panel")
    assert "PySide6" in roots


def test_the_server_serves_with_pyside6_unimportable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proof the closure walk only predicts.

    Every module in the closure is dropped from ``sys.modules`` and
    every ``PySide6`` entry is set to ``None``, which makes ``import
    PySide6`` raise ``ImportError``. The closure is then imported from
    source again and asked to serve.
    """
    modules, _ = import_closure("src.web.history_server")
    for name in list(sys.modules):
        if name in modules or name == "PySide6" or name.startswith("PySide6."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "PySide6", None)
    with pytest.raises(ImportError):
        importlib.import_module("PySide6")

    fresh = importlib.import_module("src.web.history_server")
    assert fresh is not hs
    assert "PySide6" not in [
        name for name in sys.modules if sys.modules[name] is not None
    ]

    server = fresh.HistoryServer(fresh.no_trades, port=0)
    thread = _run(server)
    try:
        status, body, _ = _request(server, fresh.DATA_ROUTE)
        shell_status, shell_body, _ = _request(server, "/")
    finally:
        _stop(server, thread)
    assert status == 200
    assert shell_status == 200
    assert shell_body
    payload = json.loads(body.decode("utf-8"))
    missing = [key for key in FRONTEND_REQUIRED_KEYS if key not in payload]
    assert missing == [], missing


# -- 4. no order path --------------------------------------------------


def order_calls_in(entry: str) -> set:
    """Order-placing names called anywhere in ``entry``'s closure.

    Reads the callee, not any identifier: a dict key or a docstring that
    happens to say ``place_order`` is not a call and does not count.
    """
    found: set = set()
    modules, _ = import_closure(entry)
    for name in modules:
        path = _module_path(name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called: Optional[str] = None
            if isinstance(node.func, ast.Attribute):
                called = node.func.attr
            elif isinstance(node.func, ast.Name):
                called = node.func.id
            if called in ORDER_CALL_NAMES:
                found.add(f"{name}:{called}")
    return found


def test_no_order_call_is_reachable_from_the_server() -> None:
    """The serving process must not be able to trade. Two instances that
    can both trade one account is the hazard this closes."""
    assert order_calls_in("src.web.history_server") == set()


def test_order_path_walk_reports_a_reacher() -> None:
    """THE CONTROL for the walk above. ``bot_container`` awaits
    ``self.exchange.place_order`` at ``src/trading/bot_container.py:489``,
    so a walk that reports nothing there is blind."""
    found = order_calls_in("src.trading.bot_container")
    assert any(hit.endswith(":place_order") for hit in found), sorted(found)


def test_the_handler_implements_no_mutating_method() -> None:
    """A ``do_POST`` would give the read-only surface a write door.
    ``BaseHTTPRequestHandler`` answers 501 for every verb it has no
    ``do_*`` for."""
    implemented = {name for name in vars(hs.HistoryHandler) if name.startswith("do_")}
    assert implemented == {"do_GET"}


def test_a_post_is_refused(served: hs.HistoryServer) -> None:
    """Measured, not inferred: the 501 above is what the socket
    answers."""
    status, _, _ = _request(served, hs.DATA_ROUTE, method="POST")
    assert status == 501


# -- asset traversal ---------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/assets/../../../main.py",
        "/assets/%2e%2e/%2e%2e/main.py",
        "/assets/",
        "/assets/history_panel.js/../../history_tab.py",
        "/assets/vendor",
    ],
)
def test_a_path_outside_the_asset_root_resolves_to_nothing(path: str) -> None:
    """A traversal that resolved would serve source files off the
    operator's disk."""
    assert hs.resolve_asset(path) is None


def test_a_path_inside_the_asset_root_resolves() -> None:
    """THE CONTROL for the traversal rejections above: the same function
    must still find a real asset."""
    resolved = hs.resolve_asset("/assets/vendor/react.production.min.js")
    assert resolved is not None
    assert resolved.is_file()
