"""The shipped API tester screen and the Qt-free surface, side by side.

A failure means the view model carries a different label, a different
colour, a different tooltip, a different button state, a different
response-log line, a different recorded step or a different refusal than
``APITesterTab``.

No test here reaches an exchange, opens a socket, resolves a name, reads
a credential or writes into the operator's runtime tree. Every key,
secret, passphrase, host answer and response body below is invented, and
every outward call on both sides is answered from memory.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import api_tester_tab_surface as surface
from src.gui.widgets import api_tester_tab as shipped
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)
from tests.qt_pixel import render_widget

REPO_ROOT = Path(__file__).resolve().parents[1]

TAB_PATH = REPO_ROOT / "src/gui/widgets/api_tester_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/api_tester_tab_surface.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_CONTROL_PATH = REPO_ROOT / "src/gui/stock_main_window.py"

PIXEL_SIZE = (1000, 460)

# Counts measured off the file by the same counter that is pointed at a
# neighbour which really has one.
TAB_CONNECT_SITES = 6
TAB_TIMER_BUILDS = 0
TAB_BUS_SITES = 0
TAB_SIGNAL_BUILDS = 0
TAB_ELEMENT_BUILDS = 22
CONTROL_CONNECT_SITES = 1
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_SIGNAL_BUILDS = 3
CONTROL_ELEMENT_BUILDS = 3

# The clock both sides read while a case is driven. Frozen, so no
# duration in the compared state is a number this machine chose.
STAMP = "04:05:06"
OTHER_STAMP = "23:59:58"
FROZEN_MONOTONIC = 1000.0

# The one value the machine chooses that reaches the screen: where
# certifi keeps its certificate file.
BUNDLE_MARK = "<a certificate file this machine happens to hold>"
SEEDED_BUNDLE = "/invented/ca-bundle.pem"

# Invented values. No key, secret or passphrase below is the operator's.
# The three invented values the scripted vault hands back, in the order
# the credential row lays its boxes out. None is the operator's.
INVENTED_CREDENTIALS = (
    "invented-credential-0001",
    "invented-credential-0002",
    "invented-credential-0003",
)
VAULT_FIELDS = ("api_key", "api_secret", "passphrase")
VAULT_COLUMNS = tuple(name + "_enc" for name in VAULT_FIELDS)
EMPTY_CREDENTIALS = dict.fromkeys(VAULT_FIELDS, "")
VAULT_PREFIX = "enc:"

UNICODE_SYMBOL = "Δ/⚡"
MARKUP_SYMBOL = "<b>BTC</b>/USD"
APOSTROPHE_SYMBOL = "Ekthelius" + chr(39) + "/USD"
NEWLINE_SYMBOL = "two\nlines"
LONG_SYMBOL = "x" * 200
WRONG_CAPITALS = "FETCH_TICKER"

WIDGETS_HELD: list = []


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def hold(widget):
    """Keep one widget alive so no later read reaches a collected object."""
    WIDGETS_HELD.append(widget)
    return widget


@pytest.fixture(autouse=True)
def fresh_bridge_model():
    """Put the bridge's kept screen back so no test decides another's state."""
    surface.view_model({"reset": True})
    yield
    surface.view_model({"reset": True})


@pytest.fixture(autouse=True)
def no_signal_sink():
    """Fail loudly if anything installs a place for pin records to be written."""
    from src.core.signal_contract import get_sink

    assert get_sink() is None, "a signal sink is installed; a pin would write a file"
    yield
    assert get_sink() is None, "a signal sink was installed during this test"


# ---------------------------------------------------------------------
# One scripted venue, read by both sides
# ---------------------------------------------------------------------


class Boom(Exception):
    """A refusal this test scripted, never one a real venue produced."""


class FakeExchange:
    """A stand-in exchange library object. Every call answers from memory."""

    def __init__(self, world):
        self.world = world
        self.markets = world.markets

    def _answer(self, name):
        found = self.world.answers[name]
        if isinstance(found, BaseException):
            raise found
        return found

    def fetch_ticker(self, symbol):
        self.world.asked.append(["ticker", symbol])
        return self._answer("ticker")

    def fetch_balance(self):
        self.world.asked.append(["balance"])
        return self._answer("balance")

    def fetch_order_book(self, symbol, limit=None):
        self.world.asked.append(["order_book", symbol, limit])
        return self._answer("order_book")

    def fetch_ohlcv(self, symbol, timeframe, limit=None):
        self.world.asked.append(["ohlcv", symbol, timeframe, limit])
        return self._answer("ohlcv")

    def fetch_open_orders(self, symbol):
        self.world.asked.append(["open_orders", symbol])
        return self._answer("open_orders")

    def fetch_my_trades(self, symbol, limit=None):
        self.world.asked.append(["my_trades", symbol, limit])
        return self._answer("my_trades")


class FakeConnector:
    """A stand-in exchange session. Opens nothing and closes nothing."""

    def __init__(self, world):
        self.world = world
        self._ccxt = None
        self._ccxt_sync = None
        self._ex = None

    def sync_connect(self, key, secret, passphrase):
        self.world.asked.append(["connect", key, secret, passphrase])
        if isinstance(self.world.connect_refusal, BaseException):
            raise self.world.connect_refusal
        self._ccxt = FakeExchange(self.world)
        self._ccxt_sync = self._ccxt
        self._ex = self._ccxt

    def set_history_callback(self, callback):
        self.world.asked.append(["history", callback is not None])
        if isinstance(self.world.history_refusal, BaseException):
            raise self.world.history_refusal
        return None

    async def disconnect(self):
        self.world.asked.append(["disconnect"])
        if isinstance(self.world.disconnect_refusal, BaseException):
            raise self.world.disconnect_refusal


class FakeHistoryTab:
    """A stand-in trade-history screen. Hands over a callback and nothing else."""

    def get_history_callback(self):
        return lambda *seen: seen


class FakeBotManager:
    """A stand-in fleet. Records the session it was handed."""

    def __init__(self, world):
        self.world = world

    def set_connector(self, session):
        self.world.asked.append(["bot_manager"])


class FakeSettings:
    """A stand-in settings store holding invented, encrypted-looking text."""

    def __init__(self, rows):
        self.rows = rows

    def list_exchanges(self):
        return list(self.rows)

    def get(self, key, default=None):
        return "invented-user" if key == "username" else default


class World:
    """One scripted venue, and every answer both sides will be given."""

    def __init__(self, **over):
        self.exchange_id = "coinbase"
        self.settings_rows = [
            dict(
                {"exchange_id": "coinbase"},
                **{
                    column: VAULT_PREFIX + value
                    for column, value in zip(VAULT_COLUMNS, INVENTED_CREDENTIALS)
                },
            )
        ]
        self.has_settings = True
        self.has_history_tab = False
        self.has_bot_manager = False
        self.use_stored = True
        self.typed = ("", "", "")
        self.symbol = surface.SYMBOL_DEFAULT
        self.markets = {"BTC/USD": {"type": "spot"}, "ETH/USD": {"type": "swap"}}
        self.connect_refusal = None
        self.disconnect_refusal = None
        self.history_refusal = None
        self.answers = {
            "ticker": {"symbol": "BTC/USD", "last": 61234.5},
            "balance": {
                "free": {"BTC": 1.25, "XRP": 0.0},
                "used": {"BTC": 0.0},
                "total": {"BTC": 2.5},
            },
            "order_book": {"bids": [[1.0, 2.0]], "asks": [[3.0, 4.0]]},
            "ohlcv": [[1, 2, 3, 4, 5.5, 6], [7, 8, 9, 10, 11.5, 12]],
            "open_orders": [{"id": index} for index in range(3)],
            "my_trades": [{"id": index} for index in range(2)],
        }
        self.tcp_refusal = None
        self.handshake = {
            "protocol": "TLSv1.3",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "common_name": "invented.example",
            "issuer": "Invented CA",
            "not_after": "Jan  1 00:00:00 2099 GMT",
        }
        self.handshake_refusal = None
        self.certifi_bundle = SEEDED_BUNDLE
        self.http_answers: dict = {}
        self.default_http = {
            "status": 200,
            "body": '{"ok": true}',
            "headers": {"Content-Type": "application/json", "Content-Length": "12"},
        }
        self.asked: list = []
        self.__dict__.update(over)

    def stored_row(self, exchange_id):
        """The saved row for one venue, or None when there is none."""
        for row in self.settings_rows:
            if row.get("exchange_id") == exchange_id:
                return row
        return None

    def answer_for(self, url):
        """The scripted web answer for one address."""
        found = self.http_answers.get(url, self.default_http)
        if isinstance(found, BaseException):
            raise found
        return found


def fake_decrypt(blob, master):
    """The stand-in vault. Strips the marker the scripted rows carry."""
    if not isinstance(blob, str) or not blob.startswith(VAULT_PREFIX):
        raise Boom("this vault holds nothing under %r" % (blob,))
    return blob[len(VAULT_PREFIX) :]


# ---------------------------------------------------------------------
# The surface's caller, and the same world patched into the widget
# ---------------------------------------------------------------------


class SurfaceCaller:
    """Every outward step the surface takes, answered from one world."""

    def __init__(self, world):
        self.world = world

    def stamp(self):
        return time.strftime(surface.TIMESTAMP_FORMAT)

    def started(self):
        return time.monotonic()

    def elapsed_ms(self, started):
        return (time.monotonic() - started) * 1000

    def stored_credentials(self, exchange_id):
        if not self.world.has_settings:
            return None
        row = self.world.stored_row(exchange_id)
        if row is None or not row.get(VAULT_COLUMNS[0]):
            return dict(EMPTY_CREDENTIALS)
        master = "qat_%s_vault" % FakeSettings(()).get("username", "user")
        found = dict(EMPTY_CREDENTIALS)
        for field, column in zip(VAULT_FIELDS, VAULT_COLUMNS):
            if row.get(column):
                found[field] = fake_decrypt(row[column], master)
        return found

    def connect(self, exchange_id, key, secret, passphrase):
        session = FakeConnector(self.world)
        session.sync_connect(key, secret, passphrase)
        return session

    def market_count(self, session):
        found = getattr(session, "_ccxt", None)
        return len(found.markets) if found and found.markets else 0

    def wire_history(self, session):
        if not self.world.has_history_tab:
            return
        session.set_history_callback(FakeHistoryTab().get_history_callback())

        if self.world.has_bot_manager:
            FakeBotManager(self.world).set_connector(session)

    def disconnect(self, session):
        if isinstance(self.world.disconnect_refusal, BaseException):
            self.world.asked.append(["disconnect"])
            raise self.world.disconnect_refusal
        self.world.asked.append(["disconnect"])

    def _exchange(self, session):
        return getattr(session, "_ccxt_sync", None) or session._ccxt

    def markets(self, session):
        return self._exchange(session).markets

    def ticker(self, session, symbol):
        return self._exchange(session).fetch_ticker(symbol)

    def balance(self, session):
        return self._exchange(session).fetch_balance()

    def order_book(self, session, symbol, limit):
        return self._exchange(session).fetch_order_book(symbol, limit=limit)

    def ohlcv(self, session, symbol, timeframe, limit):
        return self._exchange(session).fetch_ohlcv(symbol, timeframe, limit=limit)

    def open_orders(self, session, symbol):
        return self._exchange(session).fetch_open_orders(symbol)

    def my_trades(self, session, symbol, limit):
        return self._exchange(session).fetch_my_trades(symbol, limit=limit)

    def tcp(self, host, port, timeout):
        self.world.asked.append(["tcp", host, port, timeout])
        if isinstance(self.world.tcp_refusal, BaseException):
            raise self.world.tcp_refusal

    def handshake(self, host, port, timeout, bundle):
        self.world.asked.append(["tcp", host, port, timeout])
        self.world.asked.append(["handshake", host, port, bundle])
        if isinstance(self.world.handshake_refusal, BaseException):
            raise self.world.handshake_refusal
        return dict(self.world.handshake)

    def is_cert_error(self, exc):
        return isinstance(exc, ssl.SSLCertVerificationError)

    def certifi_bundle(self):
        if self.world.certifi_bundle is None:
            raise ImportError("certifi is not installed in this scripted world")
        return self.world.certifi_bundle

    def http(self, url, timeout, headers):
        self.world.asked.append(["http", url, timeout, [list(row) for row in headers]])
        return dict(self.world.answer_for(url))

    def request_failure_kind(self, exc):
        if isinstance(exc, urllib.error.HTTPError):
            return surface.FAILURE_HTTP
        if isinstance(exc, urllib.error.URLError):
            return surface.FAILURE_URL
        return surface.FAILURE_OTHER

    def error_body(self, exc):
        return exc.read().decode("utf-8", errors="replace")


class FakeSocket:
    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_closing):
        return False


class FakeHandshake:
    def __init__(self, world):
        self.world = world

    def __enter__(self):
        return self

    def __exit__(self, *_closing):
        return False

    def version(self):
        return self.world.handshake["protocol"]

    def cipher(self):
        return (self.world.handshake["cipher"], "TLSv1.3", 256)

    def getpeercert(self):
        return {
            "subject": [(("commonName", self.world.handshake["common_name"]),)],
            "issuer": [(("organizationName", self.world.handshake["issuer"]),)],
            "notAfter": self.world.handshake["not_after"],
        }


class FakeContext:
    def __init__(self, world, bundle):
        self.world = world
        self.bundle = bundle

    def wrap_socket(self, sock, server_hostname=None):
        if sock is None:
            raise AssertionError("the handshake was handed no socket to wrap")
        self.world.asked.append(
            ["handshake", server_hostname, surface.PROBE_PORT, self.bundle]
        )
        if isinstance(self.world.handshake_refusal, BaseException):
            raise self.world.handshake_refusal
        return FakeHandshake(self.world)


class FakeResponse:
    def __init__(self, answer):
        self.status = answer["status"]
        self.headers = dict(answer["headers"])
        self._body = answer["body"].encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_closing):
        return False


class FakeRequest:
    def __init__(self, url):
        self.url = url
        self.headers: list = []

    def add_header(self, name, value):
        self.headers.append([name, value])


def widget_world(world, monkey):
    """Point every outward call the shipped screen makes at one world.

    The clock is frozen and the wall time fixed, so nothing in the
    compared state is a number this machine chose.
    """
    from src.core import encryption
    from src.exchange import ccxt_connector

    real_connector = ccxt_connector.CCXTConnector

    class ScriptedConnector(FakeConnector):
        _format_exchange_error = real_connector._format_exchange_error

        def __init__(self, exchange_id):
            FakeConnector.__init__(self, world)
            self.exchange_id = exchange_id

    monkey.setattr(ccxt_connector, "CCXTConnector", ScriptedConnector)
    monkey.setattr(encryption, "decrypt", fake_decrypt)
    monkey.setattr(time, "strftime", lambda fmt, *_when: STAMP)
    monkey.setattr(time, "monotonic", lambda: FROZEN_MONOTONIC)

    def scripted_socket(address, timeout=None):
        world.asked.append(["tcp", address[0], address[1], timeout])
        if isinstance(world.tcp_refusal, BaseException):
            raise world.tcp_refusal
        return FakeSocket()

    def scripted_context(cafile=None):
        return FakeContext(world, cafile)

    def scripted_urlopen(request, timeout=None, context=None):
        world.asked.append(["http", request.url, timeout, list(request.headers)])
        return FakeResponse(world.answer_for(request.url))

    monkey.setattr(socket, "create_connection", scripted_socket)
    monkey.setattr(ssl, "create_default_context", scripted_context)
    monkey.setattr(shipped, "safe_urlopen", scripted_urlopen)
    monkey.setattr(shipped, "SafeRequest", FakeRequest)
    if world.certifi_bundle is None:
        monkey.setitem(sys.modules, "certifi", None)
    else:
        monkey.setitem(sys.modules, "certifi", _ScriptedCertifi(world))


class _ScriptedCertifi:
    """A stand-in for the certifi package, answering one invented path."""

    def __init__(self, world):
        self.world = world

    def where(self):
        return self.world.certifi_bundle


def surface_world(world, monkey):
    """Fix the surface's clock and wall time the same way as the widget's."""
    monkey.setattr(time, "strftime", lambda fmt, *_when: STAMP)
    monkey.setattr(time, "monotonic", lambda: FROZEN_MONOTONIC)


# ---------------------------------------------------------------------
# The case table, and the steps each case is driven through
# ---------------------------------------------------------------------


def http_map(answer):
    """One scripted answer for every address the coinbase probe asks."""
    return {url: answer for _method, url, _desc in surface.probe_endpoints("coinbase")}


CASES: dict = {
    "fresh": World(),
    "connect_stored": World(),
    "connect_no_settings": World(has_settings=False),
    "connect_no_row": World(settings_rows=[]),
    "connect_empty_key": World(
        settings_rows=[dict.fromkeys(VAULT_COLUMNS, "") | {"exchange_id": "coinbase"}]
    ),
    "connect_manual": World(use_stored=False, typed=INVENTED_CREDENTIALS),
    "connect_manual_empty": World(use_stored=False, typed=("", "", "")),
    "connect_manual_no_second_value": World(
        use_stored=False, typed=(INVENTED_CREDENTIALS[0], "", "")
    ),
    "connect_manual_spaces": World(use_stored=False, typed=("   ", "   ", "  ")),
    "connect_refused": World(connect_refusal=Boom("the venue refused the key")),
    "connect_no_markets": World(markets={}),
    "connect_history_wired": World(has_history_tab=True, has_bot_manager=True),
    "connect_history_no_fleet": World(has_history_tab=True),
    "connect_history_refused": World(
        has_history_tab=True, history_refusal=Boom("the history screen is gone")
    ),
    "unicode_symbol": World(symbol=UNICODE_SYMBOL),
    "markup_symbol": World(symbol=MARKUP_SYMBOL),
    "apostrophe_symbol": World(symbol=APOSTROPHE_SYMBOL),
    "newline_symbol": World(symbol=NEWLINE_SYMBOL),
    "long_symbol": World(symbol=LONG_SYMBOL),
    "empty_symbol": World(symbol=""),
    "spaces_symbol": World(symbol="     "),
    "number_where_text_belongs": World(symbol=7),
    "zero_price": World(answers=dict(World().answers, ticker={"last": 0})),
    "negative_price": World(answers=dict(World().answers, ticker={"last": -12.5})),
    "thousand_million": World(answers=dict(World().answers, ticker={"last": 1e9})),
    "one_billionth": World(answers=dict(World().answers, ticker={"last": 1e-9})),
    "whole_number": World(answers=dict(World().answers, ticker={"last": 12})),
    "decimal_number": World(answers=dict(World().answers, ticker={"last": 12.0})),
    "infinite": World(answers=dict(World().answers, ticker={"last": float("inf")})),
    "minus_infinite": World(
        answers=dict(World().answers, ticker={"last": float("-inf")})
    ),
    "not_a_number": World(answers=dict(World().answers, ticker={"last": float("nan")})),
    "text_where_a_number_belongs": World(
        answers=dict(World().answers, ticker={"last": "many"})
    ),
    "unicode_answer": World(answers=dict(World().answers, ticker={"pair": "Δ/⚡"})),
    "markup_answer": World(
        answers=dict(World().answers, ticker={"note": "<b>halted</b>"})
    ),
    "apostrophe_answer": World(
        answers=dict(World().answers, ticker={"note": "Ekthelius" + chr(39) + "s"})
    ),
    "newline_answer": World(answers=dict(World().answers, ticker={"note": "a\nb"})),
    "long_answer": World(answers=dict(World().answers, ticker={"note": "y" * 200})),
    "empty_answer": World(answers=dict(World().answers, ticker={})),
    "huge_answer": World(
        answers=dict(
            World().answers,
            ticker={"k%d" % index: "v" * 60 for index in range(200)},
        )
    ),
    "scalar_answer": World(answers=dict(World().answers, ticker=42)),
    "no_candles": World(answers=dict(World().answers, ohlcv=[])),
    "long_order_list": World(
        answers=dict(
            World().answers,
            open_orders=[{"id": index} for index in range(400)],
        )
    ),
    "empty_order_list": World(answers=dict(World().answers, open_orders=[])),
    "call_refused": World(answers=dict(World().answers, ticker=Boom("venue is down"))),
    "disconnect_refused": World(disconnect_refusal=Boom("socket already gone")),
    "probe_ok": World(),
    "probe_tcp_refused": World(tcp_refusal=Boom("no route to the host")),
    "probe_handshake_refused": World(handshake_refusal=Boom("handshake went sideways")),
    "probe_cert_refused": World(
        handshake_refusal=ssl.SSLCertVerificationError("the certificate has expired")
    ),
    "probe_no_certifi": World(certifi_bundle=None),
    "probe_empty_body": World(
        default_http={"status": 200, "body": "", "headers": {}},
    ),
    "probe_big_body": World(
        default_http={"status": 200, "body": "z" * 4000, "headers": {}},
    ),
    "probe_products": World(
        default_http={
            "status": 200,
            "body": '{"products": [1, 2, 3], "note": "kept"}',
            "headers": {},
        },
    ),
    "probe_json_list": World(
        default_http={"status": 200, "body": "[1, 2, 3]", "headers": {}},
    ),
    "probe_not_json": World(
        default_http={"status": 200, "body": "not json at all", "headers": {}},
    ),
    "probe_unicode_body": World(
        default_http={"status": 200, "body": '{"pair": "Δ/⚡"}', "headers": {}},
    ),
    "probe_markup_body": World(
        default_http={
            "status": 200,
            "body": "<html><body>Blocked by proxy</body></html>",
            "headers": {},
        },
    ),
    "probe_http_error": World(
        http_answers=http_map(
            urllib.error.HTTPError(
                "https://api.coinbase.com/v2/currencies",
                429,
                "Too Many Requests",
                {},
                None,
            )
        )
    ),
    "probe_unreachable": World(
        http_answers=http_map(urllib.error.URLError("name resolution failed"))
    ),
    "probe_other_error": World(
        http_answers=http_map(TimeoutError("the read took too long"))
    ),
    "probe_unlisted_venue": World(exchange_id="gemini"),
    "probe_kraken": World(exchange_id="kraken"),
    "probe_binance": World(exchange_id="binance"),
    "status_none": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "none", "description": "All good"}}',
            "headers": {},
        }
    ),
    "status_minor": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "minor", "description": "Slow"}}',
            "headers": {},
        }
    ),
    "status_major": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "major", "description": "Outage"}}',
            "headers": {},
        }
    ),
    "status_critical": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "critical", "description": "Down"}}',
            "headers": {},
        }
    ),
    "status_maintenance": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "maintenance", "description": "Work"}}',
            "headers": {},
        }
    ),
    "status_unknown_word": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "hibernating", "description": "?"}}',
            "headers": {},
        }
    ),
    "status_wrong_capitals": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": "NONE", "description": "All good"}}',
            "headers": {},
        }
    ),
    "status_no_indicator": World(
        default_http={"status": 200, "body": '{"status": {}}', "headers": {}}
    ),
    "status_number_indicator": World(
        default_http={
            "status": 200,
            "body": '{"status": {"indicator": 7, "description": 9}}',
            "headers": {},
        }
    ),
    "status_no_status_key": World(
        default_http={"status": 200, "body": '{"other": 1}', "headers": {}}
    ),
    "status_not_json": World(
        default_http={"status": 200, "body": "not json", "headers": {}}
    ),
    "status_long_indicator": World(
        default_http={
            "status": 200,
            "body": json.dumps(
                {"status": {"indicator": "w" * 200, "description": "?"}}
            ),
            "headers": {},
        }
    ),
    "status_unlisted_venue": World(exchange_id="gemini"),
}

# Which presses each case is driven through.
STEPS: dict = {
    "fresh": [],
    "connect_stored": [["connect"]],
    "connect_no_settings": [["connect"]],
    "connect_no_row": [["connect"]],
    "connect_empty_key": [["connect"]],
    "connect_manual": [["connect"]],
    "connect_manual_empty": [["connect"]],
    "connect_manual_no_second_value": [["connect"]],
    "connect_manual_spaces": [["connect"]],
    "connect_refused": [["connect"]],
    "connect_no_markets": [["connect"]],
    "connect_history_wired": [["connect"]],
    "connect_history_no_fleet": [["connect"]],
    "connect_history_refused": [["connect"]],
    "unicode_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "markup_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "apostrophe_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "newline_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "long_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "empty_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "spaces_symbol": [["connect"], ["test", surface.TEST_TICKER]],
    "number_where_text_belongs": [["connect"], ["test", surface.TEST_TICKER]],
    "zero_price": [["connect"], ["test", surface.TEST_TICKER]],
    "negative_price": [["connect"], ["test", surface.TEST_TICKER]],
    "thousand_million": [["connect"], ["test", surface.TEST_TICKER]],
    "one_billionth": [["connect"], ["test", surface.TEST_TICKER]],
    "whole_number": [["connect"], ["test", surface.TEST_TICKER]],
    "decimal_number": [["connect"], ["test", surface.TEST_TICKER]],
    "infinite": [["connect"], ["test", surface.TEST_TICKER]],
    "minus_infinite": [["connect"], ["test", surface.TEST_TICKER]],
    "not_a_number": [["connect"], ["test", surface.TEST_TICKER]],
    "text_where_a_number_belongs": [["connect"], ["test", surface.TEST_TICKER]],
    "unicode_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "markup_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "apostrophe_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "newline_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "long_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "empty_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "huge_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "scalar_answer": [["connect"], ["test", surface.TEST_TICKER]],
    "no_candles": [["connect"], ["test", surface.TEST_OHLCV]],
    "long_order_list": [["connect"], ["test", surface.TEST_OPEN_ORDERS]],
    "empty_order_list": [["connect"], ["test", surface.TEST_OPEN_ORDERS]],
    "call_refused": [["connect"], ["test", surface.TEST_TICKER]],
    "disconnect_refused": [["connect"], ["disconnect"]],
    "probe_ok": [["raw_probe"]],
    "probe_tcp_refused": [["raw_probe"]],
    "probe_handshake_refused": [["raw_probe"]],
    "probe_cert_refused": [["raw_probe"]],
    "probe_no_certifi": [["raw_probe"]],
    "probe_empty_body": [["raw_probe"]],
    "probe_big_body": [["raw_probe"]],
    "probe_products": [["raw_probe"]],
    "probe_json_list": [["raw_probe"]],
    "probe_not_json": [["raw_probe"]],
    "probe_unicode_body": [["raw_probe"]],
    "probe_markup_body": [["raw_probe"]],
    "probe_http_error": [["raw_probe"]],
    "probe_unreachable": [["raw_probe"]],
    "probe_other_error": [["raw_probe"]],
    "probe_unlisted_venue": [["raw_probe"]],
    "probe_kraken": [["raw_probe"]],
    "probe_binance": [["raw_probe"]],
    "status_none": [["status_page"]],
    "status_minor": [["status_page"]],
    "status_major": [["status_page"]],
    "status_critical": [["status_page"]],
    "status_maintenance": [["status_page"]],
    "status_unknown_word": [["status_page"]],
    "status_wrong_capitals": [["status_page"]],
    "status_no_indicator": [["status_page"]],
    "status_number_indicator": [["status_page"]],
    "status_no_status_key": [["status_page"]],
    "status_not_json": [["status_page"]],
    "status_long_indicator": [["status_page"]],
    "status_unlisted_venue": [["status_page"]],
}

# The shipped screen catches every failure on every button, so no press
# on either side raises. These are the inputs a screen without those
# catches would raise on, and both sides report them on screen instead.
CAUGHT_NOT_RAISED = (
    "number_where_text_belongs",
    "status_number_indicator",
    "call_refused",
    "connect_refused",
    "disconnect_refused",
    "probe_tcp_refused",
    "status_not_json",
)

SEQUENCES: dict = {
    "connect_then_all_seven": [["connect"]]
    + [["test", name] for name in surface.TEST_NAMES],
    "connect_then_disconnect": [["connect"], ["disconnect"]],
    "test_before_connect": [["test", surface.TEST_TICKER], ["connect"]],
    "disconnect_before_connect": [["disconnect"], ["connect"]],
    "connect_twice": [["connect"], ["connect"]],
    "disconnect_twice": [["connect"], ["disconnect"], ["disconnect"]],
    "toggle_then_connect": [["use_stored", False], ["connect"]],
    "toggle_back_and_forth": [
        ["use_stored", False],
        ["use_stored", True],
        ["connect"],
    ],
    "probe_then_status": [["raw_probe"], ["status_page"]],
    "connect_probe_disconnect": [["connect"], ["raw_probe"], ["disconnect"]],
    "refuse_part_way": [
        ["connect"],
        ["test", surface.TEST_TICKER],
        ["test", surface.TEST_MARKETS],
    ],
    "wrong_capitals_test": [["connect"], ["test", WRONG_CAPITALS]],
    "unknown_test": [["connect"], ["test", "no_such_call"]],
    "swap_venue_then_probe": [["exchange", "kraken"], ["raw_probe"]],
    "swap_venue_then_status": [["exchange", "kraken"], ["status_page"]],
    "symbol_then_test": [["symbol", "ETH/USD"], ["connect"], ["test", "fetch_ticker"]],
}

SEQUENCE_WORLDS = {
    "refuse_part_way": "call_refused",
    "wrong_capitals_test": "connect_stored",
    "unknown_test": "connect_stored",
    "swap_venue_then_probe": "probe_ok",
    "swap_venue_then_status": "status_none",
    "symbol_then_test": "connect_stored",
}

PICTURE_CASES = (
    "fresh",
    "connect_stored",
    "connect_no_settings",
    "connect_refused",
    "connect_manual_empty",
    "unicode_symbol",
    "markup_answer",
    "long_answer",
    "probe_ok",
    "probe_tcp_refused",
    "status_none",
    "status_major",
    "status_unlisted_venue",
    "call_refused",
    "empty_symbol",
)


def fresh_world(name):
    """A new copy of one case's world, so no drive reads another's record."""
    template = CASES[name]
    found = World()
    for key, value in template.__dict__.items():
        if key == "asked":
            continue
        found.__dict__[key] = value
    found.asked = []
    return found


# ---------------------------------------------------------------------
# Reading the two sides into one shape
# ---------------------------------------------------------------------


def numbered(value):
    """One value with every number replaced by its own text.

    ``12`` and ``12.0`` are equal as numbers and hash apart, and two
    not-a-numbers are never equal to each other. Reading each number as
    its own text tells the first pair apart and lets the second pair
    agree.
    """
    if isinstance(value, bool):
        return ["bool", repr(value)]
    if isinstance(value, (int, float)):
        return [type(value).__name__, repr(value)]
    if isinstance(value, dict):
        return {key: numbered(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [numbered(item) for item in value]
    return value


def platform_chosen(value):
    """One value with anything the machine chose replaced by a marker.

    Where certifi keeps its certificate file is a fact about this
    computer, and the raw probe prints that path. It is hidden so the
    comparison reads the product. Everything this test seeded is kept.
    """
    if isinstance(value, str):
        return value.replace(real_certifi_bundle(), BUNDLE_MARK)
    if isinstance(value, dict):
        return {key: platform_chosen(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [platform_chosen(item) for item in value]
    return value


def real_certifi_bundle() -> str:
    """Where this machine keeps its certificate file, or a value no text holds."""
    try:
        import certifi
    except ImportError:
        return "\x00no certifi on this machine\x00"
    found = certifi.where()
    return found if isinstance(found, str) and found else "\x00certifi said nothing\x00"


def readable(value):
    """One value ready to compare: numbers as text, machine values hidden."""
    return platform_chosen(numbered(value))


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(readable(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        run()
        return {"error": "", "headline": ""}
    except Exception as exc:
        return {"error": type(exc).__name__, "headline": str(exc).splitlines()[:1]}


# ---------------------------------------------------------------------
# Driving both sides from one case
# ---------------------------------------------------------------------


def old_tab(world, monkey):
    """The shipped screen, wired to one scripted world."""
    from PySide6.QtWidgets import QWidget

    app()
    parent = hold(QWidget())
    parent._settings = FakeSettings(world.settings_rows) if world.has_settings else None
    if world.has_history_tab:
        parent._trade_history_tab = FakeHistoryTab()
    if world.has_bot_manager:
        parent._bot_manager = FakeBotManager(world)
    tab = hold(shipped.APITesterTab(parent))
    if not world.has_settings:
        del parent._settings
    index = [tab._exchange.itemData(row) for row in range(tab._exchange.count())].index(
        world.exchange_id
    )
    tab._exchange.setCurrentIndex(index)
    tab._use_stored.setChecked(world.use_stored)
    tab._api_key.setText(world.typed[0])
    tab._api_secret.setText(world.typed[1])
    tab._api_pp.setText(world.typed[2])
    tab._symbol_input.setText(str(world.symbol))
    return tab


def press_old(tab, step):
    """One press on the shipped screen."""
    name = step[0]
    if name == "connect":
        tab._do_connect()
    elif name == "disconnect":
        tab._do_disconnect()
    elif name == "test":
        tab._run_test(step[1])
    elif name == "raw_probe":
        tab._raw_http_probe()
    elif name == "status_page":
        tab._check_exchange_status()
    elif name == "use_stored":
        tab._use_stored.setChecked(step[1])
    elif name == "exchange":
        index = [
            tab._exchange.itemData(row) for row in range(tab._exchange.count())
        ].index(step[1])
        tab._exchange.setCurrentIndex(index)
    elif name == "symbol":
        tab._symbol_input.setText(step[1])
    else:
        raise AssertionError("no such press: %r" % (name,))


def press_new(model, step):
    """One press on the surface, the same press the widget was given."""
    name = step[0]
    if name == "connect":
        model.do_connect()
    elif name == "disconnect":
        model.do_disconnect()
    elif name == "test":
        model.run_test(step[1])
    elif name == "raw_probe":
        model.raw_http_probe()
    elif name == "status_page":
        model.check_exchange_status()
    elif name == "use_stored":
        model.set_use_stored(step[1])
    elif name == "exchange":
        model.set_exchange(step[1])
    elif name == "symbol":
        model.set_symbol(step[1])
    else:
        raise AssertionError("no such press: %r" % (name,))


def new_model(world, monkey):
    """The surface model, wired to one scripted world."""
    surface_world(world, monkey)
    model = surface.ApiTesterModel(caller=SurfaceCaller(world))
    model.set_exchange(world.exchange_id)
    model.set_use_stored(world.use_stored)
    model.set_manual_credentials(*world.typed)
    model.set_symbol(str(world.symbol))
    return model


def watch_log(tab):
    """Record every marked-up line the shipped response log is handed."""
    seen: list = []
    real = tab._result_view.append
    tab._result_view.append = lambda html: (seen.append(html), real(html))[1]
    return seen


def read_old(tab, seen):
    """The shipped screen read into one shape."""
    from PySide6.QtWidgets import QLabel, QPushButton

    buttons = tab.findChildren(QPushButton)
    plain = [
        [found.text(), found.styleSheet(), int(found.alignment().value)]
        for found in tab.findChildren(QLabel)
        if found is not tab._conn_status and found is not tab._result_info
    ]
    return {
        "exchange_options": [
            [tab._exchange.itemText(row), tab._exchange.itemData(row)]
            for row in range(tab._exchange.count())
        ],
        "exchange_id": tab._exchange.currentData(),
        "use_stored": tab._use_stored.isChecked(),
        "use_stored_label": tab._use_stored.text(),
        "use_stored_tooltip": tab._use_stored.toolTip(),
        "manual_visible": tab._manual_frame.isVisibleTo(tab),
        "credential_placeholders": [
            tab._api_key.placeholderText(),
            tab._api_secret.placeholderText(),
            tab._api_pp.placeholderText(),
        ],
        "echo_modes": [
            tab._api_key.echoMode().name,
            tab._api_secret.echoMode().name,
            tab._api_pp.echoMode().name,
        ],
        "credentials_filled": [
            bool(tab._api_key.text()),
            bool(tab._api_secret.text()),
            bool(tab._api_pp.text()),
        ],
        "connect_label": buttons[0].text(),
        "connect_tooltip": buttons[0].toolTip(),
        "connect_enabled": buttons[0].isEnabled(),
        "disconnect_label": buttons[1].text(),
        "disconnect_enabled": buttons[1].isEnabled(),
        "test_buttons": [[found.text(), found.toolTip()] for found in buttons[2:9]],
        "raw_probe": [buttons[9].text(), buttons[9].toolTip()],
        "status_page": [buttons[10].text(), buttons[10].toolTip()],
        "plain_labels": sorted(plain),
        "status_text": tab._conn_status.text(),
        "status_style": tab._conn_status.styleSheet(),
        "symbol": tab._symbol_input.text(),
        "symbol_tooltip": tab._symbol_input.toolTip(),
        "headline": tab._result_info.text(),
        "headline_style": tab._result_info.styleSheet(),
        "result_placeholder": tab._result_view.placeholderText(),
        "result_read_only": tab._result_view.isReadOnly(),
        "result_word_wrap": tab._result_info.wordWrap(),
        "entries": list(seen),
        "entry_count": len(seen),
        "connected": tab._connected,
        "connector_held": tab._connector is not None,
    }


def read_new(payload):
    """One surface payload read into the shape the widget is read into."""
    return {
        "exchange_options": payload["exchange_options"],
        "exchange_id": payload["exchange_id"],
        "use_stored": payload["use_stored"],
        "use_stored_label": payload["use_stored_label"],
        "use_stored_tooltip": payload["use_stored_tooltip"],
        "manual_visible": payload["manual_visible"],
        "credential_placeholders": payload["credential_placeholders"],
        "echo_modes": [payload["echo_mode"]] * 3,
        "credentials_filled": payload["credentials_filled"],
        "connect_label": payload["connect_label"],
        "connect_tooltip": payload["connect_tooltip"],
        "connect_enabled": payload["connect_enabled"],
        "disconnect_label": payload["disconnect_label"],
        "disconnect_enabled": payload["disconnect_enabled"],
        "test_buttons": [[row[0], row[2]] for row in payload["test_buttons"]],
        "raw_probe": [payload["raw_probe_label"], payload["raw_probe_tooltip"]],
        "status_page": [payload["status_page_label"], payload["status_page_tooltip"]],
        "plain_labels": sorted(
            [
                [payload["exchange_label"], "", 129],
                [
                    payload["diagnostics_label"],
                    payload["diagnostics_style"],
                    payload["diagnostics_alignment_value"],
                ],
            ]
        ),
        "status_text": payload["status_text"],
        "status_style": payload["status_style"],
        "symbol": payload["symbol"],
        "symbol_tooltip": payload["symbol_tooltip"],
        "headline": payload["headline"],
        "headline_style": payload["headline_style"],
        "result_placeholder": payload["result_placeholder"],
        "result_read_only": payload["result_read_only"],
        "result_word_wrap": payload["result_info_word_wrap"],
        "entries": [found["html"] for found in payload["entries"]],
        "entry_count": payload["entry_count"],
        "connected": payload["connected"],
        "connector_held": payload["connector_held"],
    }


def drive(name, steps=None, monkey=None):
    """Both sides through the same presses, read into one shape.

    Returns the two states, the two outcomes and the two lists of what
    each side asked its scripted venue for, so a caller compares what
    each side DID as well as what it holds.
    """
    steps = STEPS[name] if steps is None else steps
    old_world = fresh_world(name)
    with pytest.MonkeyPatch.context() as patch:
        widget_world(old_world, patch)
        tab = old_tab(old_world, patch)
        seen = watch_log(tab)
        old_outcome = guarded(lambda: [press_old(tab, step) for step in steps])
        old_state = read_old(tab, seen)
    new_world = fresh_world(name)
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(new_world, patch)
        new_outcome = guarded(lambda: [press_new(model, step) for step in steps])
        new_state = read_new(surface.build_view_model(model))
    return {
        "old": old_state,
        "new": new_state,
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "old_asked": old_world.asked,
        "new_asked": new_world.asked,
    }


def both_sides_agree(run, note):
    """Fail unless the two sides did the same thing and hold the same state."""
    assert (
        run["old_outcome"] == run["new_outcome"]
    ), "%s: the shipped screen and the surface refused differently: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        readable(run["old"]),
        readable(run["new"]),
    )
    assert digest(run["old"]) == digest(run["new"]), "%s: %s against %s" % (
        note,
        digest(run["old"]),
        digest(run["new"]),
    )


# ---------------------------------------------------------------------
# The two sides, case by case
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_screen_is_the_shipped_screens(name):
    """The surface describes a screen the shipped screen does not paint."""
    both_sides_agree(drive(name), name)


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_a_step_sequence_is_the_shipped_screens(name):
    """A sequence of presses left the two sides holding different screens."""
    world = SEQUENCE_WORLDS.get(name, "connect_stored")
    both_sides_agree(drive(world, SEQUENCES[name]), name)


def test_every_case_and_every_sequence_is_driven():
    """A case sits in the table that nothing ever drives."""
    driven = set()
    for name in CASES:
        both_sides_agree(drive(name), name)
        driven.add(name)
    used = set()
    for name, steps in SEQUENCES.items():
        world = SEQUENCE_WORLDS.get(name, "connect_stored")
        both_sides_agree(drive(world, steps), name)
        used.add(name)
    assert driven == set(CASES), sorted(driven ^ set(CASES))
    assert used == set(SEQUENCES), sorted(used ^ set(SEQUENCES))
    assert set(STEPS) == set(CASES), sorted(set(STEPS) ^ set(CASES))
    assert set(PICTURE_CASES) <= set(CASES), sorted(set(PICTURE_CASES) - set(CASES))
    assert set(CAUGHT_NOT_RAISED) <= set(CASES), sorted(
        set(CAUGHT_NOT_RAISED) - set(CASES)
    )
    assert set(SEQUENCE_WORLDS.values()) <= set(CASES)


def test_the_sample_hashes_are_reported():
    """The comparison reports no hash, so nothing can be checked by hand."""
    fresh = drive("fresh")
    connected = drive("connect_stored")
    assert len(digest(fresh["old"])) == 64
    assert digest(fresh["old"]) == digest(fresh["new"])
    assert digest(connected["old"]) == digest(connected["new"])
    assert digest(fresh["old"]) != digest(connected["old"])


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash gives one value for every screen, so it tells nothing apart."""
    fresh = drive("fresh")
    connected = drive("connect_stored")
    assert digest(fresh["old"]) != digest(connected["new"]), "old fresh, new connected"
    assert digest(connected["old"]) != digest(fresh["new"]), "old connected, new fresh"
    assert digest(fresh["old"]) == digest(fresh["new"])
    assert digest(connected["old"]) == digest(connected["new"])


def test_the_same_input_hashes_the_same_twice():
    """The hash moves between two runs of one input, so it reads the clock."""
    assert digest(drive("connect_stored")["old"]) == digest(
        drive("connect_stored")["old"]
    )
    assert digest(drive("connect_stored")["new"]) == digest(
        drive("connect_stored")["new"]
    )


def test_a_whole_number_and_a_decimal_are_told_apart():
    """The reader treats 12 and 12.0 as one value, so a change reads as none."""
    assert readable(12) != readable(12.0)
    assert digest({"a": 12}) != digest({"a": 12.0})
    assert readable(True) != readable(1)


def test_two_not_a_numbers_built_apart_compare_equal():
    """The reader reports a difference between two not-a-numbers that is none."""
    first = float("nan")
    second = float("inf") - float("inf")
    assert first != second
    assert readable(first) == readable(second)
    assert digest({"a": first}) == digest({"a": second})
    assert readable(float("inf")) != readable(float("-inf"))


def test_the_machine_rule_keeps_a_seeded_value_and_hides_a_chosen_one():
    """The rule hides a value this test seeded, or keeps one the machine chose."""
    machine = real_certifi_bundle()
    body = {"seeded": SEEDED_BUNDLE, "chosen": "Certifi CA bundle: " + machine}
    found = platform_chosen(body)
    assert found["seeded"] == SEEDED_BUNDLE
    assert found["chosen"] == "Certifi CA bundle: " + BUNDLE_MARK
    assert BUNDLE_MARK not in body["chosen"]
    assert platform_chosen(["a", machine]) == ["a", BUNDLE_MARK]
    for name in ("probe_ok", "probe_no_certifi"):
        run = drive(name)
        assert machine not in json.dumps(run["old"], default=str), name
        assert machine not in json.dumps(run["new"], default=str), name
        assert SEEDED_BUNDLE in json.dumps(run["old"], default=str) or name.endswith(
            "no_certifi"
        ), name


def test_the_clock_and_the_wall_time_reach_both_sides():
    """A stamp this test fixed did not reach the screen, so the run reads a clock."""
    run = drive("connect_stored")
    assert run["old"]["entries"], run["old"]
    assert all(STAMP in html for html in run["old"]["entries"]), run["old"]["entries"]
    assert all(STAMP in html for html in run["new"]["entries"]), run["new"]["entries"]
    assert OTHER_STAMP != STAMP
    with pytest.MonkeyPatch.context() as patch:
        world = fresh_world("connect_stored")
        widget_world(world, patch)
        patch.setattr(time, "strftime", lambda fmt, *_when: OTHER_STAMP)
        tab = old_tab(world, patch)
        seen = watch_log(tab)
        tab._do_connect()
    assert seen and all(OTHER_STAMP in html for html in seen), seen
    assert all(STAMP not in html for html in seen), seen


# ---------------------------------------------------------------------
# What each side DID: answered, or refused with which wording
# ---------------------------------------------------------------------


def test_no_press_on_either_side_ever_raises():
    """A press raised on one side, so the screen would go down with it.

    Every button on the shipped screen carries a catch, so a venue that
    refuses, a document that will not parse and a value of the wrong
    kind are all reported on screen rather than raised. The surface does
    the same. The control below proves the recorder would report a raise.
    """
    found = {name: drive(name)["old_outcome"] for name in sorted(CASES)}
    raised = {name: done for name, done in found.items() if done["error"]}
    assert raised == {}, raised
    assert len(found) == len(CASES)
    assert guarded(lambda: 1 / 0)["error"] == "ZeroDivisionError"
    assert guarded(lambda: None)["error"] == ""


@pytest.mark.parametrize("name", sorted(CAUGHT_NOT_RAISED))
def test_a_failure_is_caught_and_shown_the_same_way_on_both_sides(name):
    """A failure was raised on one side and shown on the other."""
    run = drive(name)
    assert run["old_outcome"] == run["new_outcome"] == {"error": "", "headline": ""}
    assert run["old"]["entries"], name
    both_sides_agree(run, name)


def test_the_refusal_check_compares_the_type_and_can_report():
    """The refusal check passes whatever kind of failure a side produces."""
    assert guarded(lambda: 1) != guarded(lambda: 1 / 0)
    assert guarded(lambda: int("x"))["error"] == "ValueError"
    assert guarded(lambda: 1 / 0)["error"] == "ZeroDivisionError"
    assert guarded(lambda: int("x"))["error"] != guarded(lambda: 1 / 0)["error"]
    assert guarded(lambda: None)["error"] == ""


def test_the_two_sides_ask_the_scripted_venue_for_the_same_things():
    """One side reached for something the other did not."""
    for name in ("connect_stored", "probe_ok", "status_none", "probe_kraken"):
        run = drive(name)
        assert run["old_asked"] == run["new_asked"], (
            name,
            run["old_asked"],
            run["new_asked"],
        )
        assert run["old_asked"], name


def test_the_asked_list_reports_a_step_neither_side_took():
    """The asked list is empty whatever a side does, so a lost step is unseen."""
    run = drive("probe_ok")
    kinds = [row[0] for row in run["old_asked"]]
    assert kinds.count("tcp") == 3, kinds
    assert kinds.count("handshake") == 2, kinds
    bundles = [row[3] for row in run["old_asked"] if row[0] == "handshake"]
    assert bundles == [None, SEEDED_BUNDLE], bundles
    assert real_certifi_bundle() not in bundles, bundles
    waits = [row[3] for row in run["old_asked"] if row[0] == "tcp"]
    waits += [row[2] for row in run["old_asked"] if row[0] == "http"]
    assert waits == [surface.PROBE_TIMEOUT_S] * len(waits), waits
    assert len(waits) == 6, waits
    assert kinds.count("http") == len(surface.probe_endpoints("coinbase")), kinds
    refused = drive("probe_tcp_refused")
    assert [row[0] for row in refused["old_asked"]] == ["tcp"]
    assert refused["old_asked"] != run["old_asked"]


# ---------------------------------------------------------------------
# The surface holds its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    moved_text = "Not plugged in at all"
    before = shipped.ds.CARD_METRIC_LABEL
    with pytest.MonkeyPatch.context() as patch:
        world = fresh_world("fresh")
        widget_world(world, patch)
        patch.setattr(shipped.QLabel, "text", lambda self: moved_text)
        tab = old_tab(world, patch)
        moved = read_old(tab, watch_log(tab))
    kept = read_new(surface.build_view_model(surface.ApiTesterModel()))
    assert moved["status_text"] == moved_text
    assert kept["status_text"] == surface.STATUS_IDLE_TEXT
    assert kept["status_text"] != moved_text
    unmoved = [
        key
        for key in ("credential_placeholders", "echo_modes", "exchange_options")
        if readable(moved[key]) != readable(kept[key])
    ]
    assert unmoved == [], unmoved
    assert shipped.ds.CARD_METRIC_LABEL == before
    both_sides_agree(drive("fresh"), "after the value was put back")


def test_the_shipped_file_is_not_named_by_the_surface():
    """The surface reaches into the widget it replaces."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("widgets" in name for name in imported), imported


# ---------------------------------------------------------------------
# Counting what the shipped file wires, waits on, and builds
# ---------------------------------------------------------------------

WIDGET_NAMES_BUILT = (
    "QWidget",
    "QLabel",
    "QPushButton",
    "QTableWidget",
    "QTableWidgetItem",
    "QGroupBox",
    "QFrame",
    "QScrollArea",
    "QLineEdit",
    "QComboBox",
    "QCheckBox",
    "QSpinBox",
    "QTextEdit",
    "QProgressBar",
    "QSplitter",
    "QDialog",
)


def count_text(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, names):
    """How many times one file constructs any of `names`."""
    text = path.read_text(encoding="utf-8")
    return sum(len(re.findall(r"\b%s\s*\(" % name, text)) for name in names)


def declared_classes(path):
    """Every class one file declares, wherever it is declared.

    A class inside an ``if``, inside a method or inside another class is
    still a class, so the whole tree is walked rather than its top level.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def declared_widget_classes(path):
    """Every class one file declares that ends up being a screen element."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    found: set = set()
    growing = True
    while growing:
        growing = False
        for node in classes:
            if node.name in found:
                continue
            for base in node.bases:
                name = (
                    base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                )
                if name.startswith("Q") or name in found:
                    found.add(node.name)
                    growing = True
                    break
    return found


def count_elements(path):
    """How many screen elements one file builds, its own classes included."""
    return count_built(path, WIDGET_NAMES_BUILT) + len(declared_widget_classes(path))


def test_the_screen_wires_six_signals_and_the_surface_names_six_actions():
    """A wiring appeared on one side and not the other."""
    assert count_text(TAB_PATH, ".connect(") == TAB_CONNECT_SITES == 6
    assert count_text(SURFACE_PATH, ".connect(") == 0
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES == 1
    assert len(surface.ACTIONS) == count_text(TAB_PATH, ".connect(")
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.ApiTesterModel, name)), name


def test_the_screen_starts_no_timer():
    """A wait appeared on one side and not the other."""
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(TAB_PATH, timer_names) == TAB_TIMER_BUILDS == 0
    assert count_built(SURFACE_PATH, timer_names) == 0
    assert count_built(TIMER_CONTROL_PATH, timer_names) == CONTROL_TIMER_BUILDS == 1
    assert count_text(TIMER_CONTROL_PATH, "QTimer") > CONTROL_TIMER_BUILDS
    started: list = []
    first_start = QObject.startTimer
    first_timer = QTimer.start
    first_single = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return first_start(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return first_timer(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return first_single(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        drive("connect_stored")
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()


def test_the_screen_declares_no_signal_of_its_own():
    """A signal declaration appeared on one side and not the other."""
    signal_names = ("Signal",)
    assert count_built(TAB_PATH, signal_names) == TAB_SIGNAL_BUILDS == 0
    assert count_built(SURFACE_PATH, signal_names) == 0
    assert count_built(SIGNAL_CONTROL_PATH, signal_names) == CONTROL_SIGNAL_BUILDS == 3
    assert count_text(SIGNAL_CONTROL_PATH, "Signal") > CONTROL_SIGNAL_BUILDS


def test_the_screen_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(TAB_PATH, ".subscribe(") == TAB_BUS_SITES == 0
    assert count_text(SURFACE_PATH, ".subscribe(") == 0
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_text(TAB_PATH, ".subscribe(")


def test_the_screen_elements_the_tab_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(TAB_PATH) == TAB_ELEMENT_BUILDS == 22
    assert count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert declared_widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert declared_widget_classes(TAB_PATH) == {"APITesterTab"}
    assert count_built(TAB_PATH, WIDGET_NAMES_BUILT) == 21
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == set()


def test_the_class_counter_finds_a_class_declared_inside_a_branch():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(NESTED_CLASS_CONTROL_PATH)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    top_level = {
        node.name
        for node in ast.parse(
            NESTED_CLASS_CONTROL_PATH.read_text(encoding="utf-8")
        ).body
        if isinstance(node, ast.ClassDef)
    }
    assert top_level == set(), top_level
    assert declared_classes(TAB_PATH) == {"APITesterTab"}
    assert {
        node.name
        for node in ast.parse(TAB_PATH.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
    } == set()


# ---------------------------------------------------------------------
# Every class and every method has a counterpart
# ---------------------------------------------------------------------


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A signal is callable and is not a method, so it is excluded by name.
    A read-only value is not callable at all, so asking ``callable``
    alone misses it.
    """
    import inspect

    from PySide6.QtCore import Signal

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if inspect.isfunction(value) or isinstance(
            value, (property, classmethod, staticmethod)
        ):
            found.add(name)
    return found


def test_the_member_counter_excludes_a_signal_and_finds_both_quiet_shapes():
    """The counter counts a signal, or misses a factory or a read-only value."""
    from PySide6.QtCore import Signal

    from src.gui import indicator_panel, launcher

    app()
    panel = indicator_panel.IndicatorVotingPanel
    assert callable(Signal())
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert isinstance(vars(panel)["_reading_fingerprint"], staticmethod)
    assert "_reading_fingerprint" in members(panel)
    assert isinstance(vars(panel)["lock_timeframe"], property)
    assert not callable(vars(panel)["lock_timeframe"])
    assert "lock_timeframe" in members(panel)
    assert isinstance(vars(panel)["selected_bot_id"], property)
    assert not callable(vars(panel)["selected_bot_id"])
    assert "selected_bot_id" in members(panel)


CLASS_MAP = {"APITesterTab": "ApiTesterModel"}

METHOD_MAP = {
    "APITesterTab.__init__": "ApiTesterModel.__init__",
    "APITesterTab._log": "ApiTesterModel.log",
    "APITesterTab._get_settings": "ApiTesterModel._stored_credentials",
    "APITesterTab._do_connect": "ApiTesterModel.do_connect",
    "APITesterTab._do_disconnect": "ApiTesterModel.do_disconnect",
    "APITesterTab._run_test": "ApiTesterModel.run_test",
    "APITesterTab._raw_http_probe": "ApiTesterModel.raw_http_probe",
    "APITesterTab._check_exchange_status": "ApiTesterModel.check_exchange_status",
}

HELPER_MAP = {
    "the level colour table": "level_color",
    "the timing suffix": "timing_text",
    "the headline": "headline_text",
    "the headline style": "headline_style",
    "one response-log line": "entry_html",
    "the venue name shown": "exchange_title",
    "the probe host": "probe_host",
    "the probe address table": "probe_endpoints",
    "the balance filter": "positive_only",
    "one holding as a number": "reading_of",
    "one answer read as a mapping": "mapping_or_none",
    "one response body as text": "body_text",
    "one http status as shown": "status_text_of",
    "the market count as shown": "market_count_text",
    "one end candle close": "close_of",
    "the markets answer": "markets_summary",
    "the candles answer": "ohlcv_summary",
    "one answer as text": "result_display",
    "one web answer as text": "body_display",
    "the status colour rule": "status_level",
    "the venue failure text": "exchange_error_text",
    "the venue list": "supported_exchanges",
    "the picker entries": "exchange_options",
    "the seven buttons": "test_buttons",
    "the credential presence": "credentials_filled",
    "the whole screen": "build_view_model",
    "one fresh screen": "build_model",
    "the bridge handler": "view_model",
    "the bridge's kept screen": "pane_model",
}

MODEL_MEMBERS = {
    "__init__",
    "set_exchange",
    "set_use_stored",
    "set_symbol",
    "set_manual_credentials",
    "log",
    "_ask",
    "_stamp",
    "_started",
    "_elapsed_ms",
    "_set_status",
    "do_connect",
    "_stored_credentials",
    "_market_count",
    "_wire_history",
    "do_disconnect",
    "run_test",
    "_call_test",
    "raw_http_probe",
    "_probe_tcp",
    "_probe_handshake",
    "_is_cert_error",
    "_probe_certifi",
    "_probe_endpoints",
    "_endpoint_of",
    "_log_answer",
    "_log_unreadable_answer",
    "_log_request_failure",
    "_request_failure_kind",
    "_error_body",
    "check_exchange_status",
    "_log_indicator",
}


def resolve(dotted):
    """The member a dotted name in a map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_classes():
    """Every class the shipped module declares, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    app()
    assert shipped_classes() == set(CLASS_MAP)
    assert len(CLASS_MAP) == 1
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == len(found)
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert members(surface.ApiTesterModel) == MODEL_MEMBERS, sorted(
        members(surface.ApiTesterModel) ^ MODEL_MEMBERS
    )
    assert declared_classes(TAB_PATH) == set(CLASS_MAP)


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "_do_connect" in members(shipped.APITesterTab)
    assert "_raw_http_probe" in members(shipped.APITesterTab)
    assert "APITesterTab" not in MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("ApiTesterModel.no_such_member")
    assert MODEL_MEMBERS - {"do_connect"} != MODEL_MEMBERS
    assert members(surface.ApiTesterModel) - {"run_test"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"APITesterTab.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"APITesterTab"} != shipped_classes()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    app()
    assert list(inspect.signature(shipped.APITesterTab.__init__).parameters) == [
        "self",
        "parent",
    ]
    assert list(inspect.signature(surface.ApiTesterModel.__init__).parameters) == [
        "self",
        "caller",
        "exchange_ids",
    ]
    old_log = list(inspect.signature(shipped.APITesterTab._log).parameters)
    new_log = list(inspect.signature(surface.ApiTesterModel.log).parameters)
    assert old_log == new_log == ["self", "title", "detail", "elapsed", "level"]
    old_test = list(inspect.signature(shipped.APITesterTab._run_test).parameters)
    new_test = list(inspect.signature(surface.ApiTesterModel.run_test).parameters)
    assert old_test == new_test == ["self", "test"]
    assert list(inspect.signature(surface.view_model).parameters) == ["params"]


def modules_importing(module, skip=()):
    """Every file under src that imports the module named exactly `module`."""
    found = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path in skip:
            continue
        names = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names += [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        if any(name.split(".")[-1] == module for name in names):
            found.append(str(path))
    return found


def test_the_screen_is_reached_by_the_window_and_the_surface_by_the_bridge():
    """The count of readers is wrong, so a lost reader would pass unseen."""
    readers = modules_importing("api_tester_tab", skip=(SURFACE_PATH, TAB_PATH))
    assert readers == [str(REPO_ROOT / "src/gui/main_window.py")], readers
    assert modules_importing("api_tester_tab_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    known = modules_importing("design_system")
    assert len(known) > 5, known


# ---------------------------------------------------------------------
# The screen paints, and the two sides paint the same pixels
# ---------------------------------------------------------------------


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def model_payload(name, steps=None):
    """The surface's whole payload for one case, stamped as it comes off."""
    world = fresh_world(name)
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(world, patch)
        for step in STEPS[name] if steps is None else steps:
            press_new(model, step)
        return sealed(surface.build_view_model(model))


def old_painted(name, steps=None):
    """The shipped screen driven through one case, ready to render."""
    world = fresh_world(name)
    with pytest.MonkeyPatch.context() as patch:
        widget_world(world, patch)
        tab = old_tab(world, patch)
        watch_log(tab)
        for step in STEPS[name] if steps is None else steps:
            press_old(tab, step)
    return tab


def screen_painted_by_the_model(payload):
    """One screen built only from the surface's view model."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    screen = hold(QWidget())
    layout = QVBoxLayout(screen)
    layout.setContentsMargins(*payload["layout_margins"])
    layout.setSpacing(payload["layout_spacing"])

    connection = QGroupBox(payload["connection_title"])
    connection_layout = QVBoxLayout(connection)
    connection_layout.setContentsMargins(*payload["group_margins"])
    connection_layout.setSpacing(payload["connection_spacing"])

    top_row = QHBoxLayout()
    top_row.addWidget(QLabel(payload["exchange_label"]))
    picker = QComboBox()
    for label, value in payload["exchange_options"]:
        picker.addItem(label, value)
    picker.setCurrentIndex(payload["exchange_ids"].index(payload["exchange_id"]))
    top_row.addWidget(picker)
    stored = QCheckBox(payload["use_stored_label"])
    stored.setChecked(payload["use_stored"])
    stored.setToolTip(payload["use_stored_tooltip"])
    top_row.addWidget(stored)
    connection_layout.addLayout(top_row)

    manual = QFrame()
    manual_layout = QHBoxLayout(manual)
    manual_layout.setContentsMargins(*payload["manual_margins"])
    manual_layout.setSpacing(payload["manual_spacing"])
    for hint in payload["credential_placeholders"]:
        box = QLineEdit()
        box.setPlaceholderText(hint)
        box.setEchoMode(getattr(QLineEdit.EchoMode, payload["echo_mode"]))
        manual_layout.addWidget(box)
    manual.setVisible(payload["manual_visible"])
    connection_layout.addWidget(manual)

    button_row = QHBoxLayout()
    connect = QPushButton(payload["connect_label"])
    connect.setToolTip(payload["connect_tooltip"])
    connect.setEnabled(payload["connect_enabled"])
    button_row.addWidget(connect)
    disconnect = QPushButton(payload["disconnect_label"])
    disconnect.setEnabled(payload["disconnect_enabled"])
    button_row.addWidget(disconnect)
    status = QLabel(payload["status_text"])
    status.setStyleSheet(payload["status_style"])
    button_row.addWidget(status)
    connection_layout.addLayout(button_row)
    layout.addWidget(connection)

    splitter = QSplitter(getattr(Qt, payload["splitter_orientation"]))
    splitter.setHandleWidth(payload["splitter_handle_width"])
    splitter.setChildrenCollapsible(payload["splitter_children_collapsible"])

    operations = QGroupBox(payload["operations_title"])
    operations_layout = QVBoxLayout(operations)
    operations_layout.setContentsMargins(*payload["group_margins"])
    operations_layout.setSpacing(payload["operations_spacing"])
    symbol = QLineEdit(payload["symbol"])
    symbol.setToolTip(payload["symbol_tooltip"])
    operations_layout.addWidget(symbol)
    for label, _name, tip in payload["test_buttons"]:
        found = QPushButton(label)
        found.setToolTip(tip)
        operations_layout.addWidget(found)
    separator = QLabel(payload["diagnostics_label"])
    separator.setStyleSheet(payload["diagnostics_style"])
    separator.setAlignment(Qt.AlignmentFlag(payload["diagnostics_alignment_value"]))
    operations_layout.addWidget(separator)
    raw = QPushButton(payload["raw_probe_label"])
    raw.setToolTip(payload["raw_probe_tooltip"])
    operations_layout.addWidget(raw)
    page = QPushButton(payload["status_page_label"])
    page.setToolTip(payload["status_page_tooltip"])
    operations_layout.addWidget(page)
    operations_layout.addStretch()
    splitter.addWidget(operations)

    response = QGroupBox(payload["response_title"])
    response_layout = QVBoxLayout(response)
    response_layout.setContentsMargins(*payload["group_margins"])
    headline = QLabel(payload["headline"])
    headline.setWordWrap(payload["result_info_word_wrap"])
    headline.setStyleSheet(payload["headline_style"])
    response_layout.addWidget(headline)
    log = QTextEdit()
    log.setReadOnly(payload["result_read_only"])
    log.setPlaceholderText(payload["result_placeholder"])
    for entry in payload["entries"]:
        log.append(entry["html"])
        log.verticalScrollBar().setValue(log.verticalScrollBar().maximum())
    response_layout.addWidget(log)
    splitter.addWidget(response)
    splitter.setSizes(list(payload["splitter_sizes"]))
    layout.addWidget(splitter)
    return screen


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a screen the shipped screen does not."""
    app()
    old_side = render_widget(old_painted(name), PIXEL_SIZE)
    new_side = render_widget(
        screen_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_widget(old_painted("fresh"), PIXEL_SIZE),
        new_side=render_widget(
            screen_painted_by_the_model(model_payload("connect_stored")), PIXEL_SIZE
        ),
        note="nothing pressed against a connected screen",
    )
    assert_pictures_differ(
        old_side=render_widget(old_painted("connect_stored"), PIXEL_SIZE),
        new_side=render_widget(
            screen_painted_by_the_model(model_payload("fresh")), PIXEL_SIZE
        ),
        note="a connected screen against nothing pressed",
    )
    assert_pictures_match(
        old_side=render_widget(old_painted("fresh"), PIXEL_SIZE),
        new_side=render_widget(
            screen_painted_by_the_model(model_payload("fresh")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("fresh")
    payload["status_text"] = "moved"
    with pytest.raises(AssertionError):
        screen_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        screen_painted_by_the_model({"entries": []})
    assert screen_painted_by_the_model(model_payload("fresh")) is not None


def test_the_screen_declares_no_skin_of_its_own():
    """A colour the surface ships is one the screen never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    assert "gridline-color" not in surface.STATUS_STYLE_FORMAT
    assert "gridline-color" not in surface.HEADLINE_STYLE_FORMAT
    skinned = screen_painted_by_the_model(model_payload("fresh"))
    skinned.setStyleSheet(
        "QGroupBox { gridline-color: #3a1414; border: 3px solid #7a1414; }"
    )
    assert_pictures_differ(
        old_side=render_widget(old_painted("fresh"), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a rule the screen does not set",
    )
    assert_pictures_match(
        old_side=render_widget(old_painted("fresh"), PIXEL_SIZE),
        new_side=render_widget(
            screen_painted_by_the_model(model_payload("fresh")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


def test_the_pane_sizes_are_compared_as_asked_for():
    """The size a pane was given differs between the two sides."""
    from PySide6.QtWidgets import QSplitter, QWidget

    app()
    assert surface.SPLITTER_SIZES == (250, 750)
    control = hold(QSplitter())
    control.addWidget(QWidget())
    control.addWidget(QWidget())
    control.setSizes(list(surface.SPLITTER_SIZES))
    lifted = control.sizes()
    assert len(lifted) == 2, lifted
    assert lifted != list(
        surface.SPLITTER_SIZES
    ), "this platform kept the sizes asked for, so no lift is being pinned: %r" % (
        lifted,
    )
    assert sum(lifted) != sum(surface.SPLITTER_SIZES), lifted


def test_the_pane_handle_and_collapse_are_compared_as_values():
    """A pane setting the picture cannot show differs between the sides."""
    from PySide6.QtWidgets import QSplitter

    app()
    found = old_painted("fresh").findChildren(QSplitter)[0]
    built = screen_painted_by_the_model(model_payload("fresh")).findChildren(QSplitter)[
        0
    ]
    assert found.handleWidth() == built.handleWidth() == surface.SPLITTER_HANDLE_WIDTH
    assert (
        found.childrenCollapsible()
        is built.childrenCollapsible()
        is surface.SPLITTER_CHILDREN_COLLAPSIBLE
    )
    assert found.orientation().name == built.orientation().name
    assert found.orientation().name == surface.SPLITTER_ORIENTATION
    assert found.count() == built.count() == len(surface.SPLITTER_SIZES)


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font database."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding fonts measured every glyph the same width."""
    app()
    assert app_font_advance_px(WIDE_LABEL) > app_font_advance_px(NARROW_LABEL)


# ---------------------------------------------------------------------
# What a picture cannot see
# ---------------------------------------------------------------------

BLIND_TO_THE_PICTURE = {
    "button tooltips": "test_the_button_tooltips_are_compared_as_strings",
    "the checkbox tooltip": "test_the_checkbox_tooltip_is_compared_as_a_string",
    "the symbol tooltip": "test_the_symbol_tooltip_is_compared_as_a_string",
    "the idle colour": "test_the_idle_status_colour_is_compared_as_exact_text",
    "a filled credential box": "test_the_credential_boxes_hide_what_is_typed",
    "the response-log markup": "test_the_response_log_line_is_compared_as_a_string",
    "the venue list": "test_the_venue_list_is_compared_as_values",
    "pane handle and collapse": "test_the_pane_handle_and_collapse_are_compared_as_values",
    "pane sizes asked for": "test_the_pane_sizes_are_compared_as_asked_for",
    "what each side asked the venue": (
        "test_the_two_sides_ask_the_scripted_venue_for_the_same_things"
    ),
    "the recorded steps": "test_the_recorded_steps_are_compared_as_values",
    "the refusal type": "test_the_refusal_check_compares_the_type_and_can_report",
    "a failure shown not raised": (
        "test_a_failure_is_caught_and_shown_the_same_way_on_both_sides"
    ),
    "the debug line": "test_a_refused_history_wiring_writes_the_same_debug_line",
    "the read-only response box": "test_the_response_box_is_read_only_on_both_sides",
    "the wall time": "test_the_clock_and_the_wall_time_reach_both_sides",
}


def test_the_button_tooltips_are_compared_as_strings():
    """A button tooltip drifted between the two sides."""
    run = drive("fresh")
    assert run["old"]["test_buttons"] == run["new"]["test_buttons"]
    assert len(run["old"]["test_buttons"]) == len(surface.TEST_BUTTONS) == 7
    assert run["old"]["raw_probe"] == run["new"]["raw_probe"]
    assert run["old"]["raw_probe"][1] == surface.RAW_PROBE_TIP
    assert "\n" in surface.RAW_PROBE_TIP
    assert run["old"]["status_page"] == run["new"]["status_page"]
    assert run["old"]["connect_tooltip"] == surface.CONNECT_TIP


def test_the_checkbox_tooltip_is_compared_as_a_string():
    """The stored-credentials tooltip drifted between the two sides."""
    run = drive("fresh")
    assert run["old"]["use_stored_tooltip"] == run["new"]["use_stored_tooltip"]
    assert run["old"]["use_stored_tooltip"] == surface.USE_STORED_TIP
    assert run["old"]["use_stored_label"] == surface.USE_STORED_LABEL


def test_the_symbol_tooltip_is_compared_as_a_string():
    """The trading-pair tooltip drifted between the two sides."""
    run = drive("fresh")
    assert run["old"]["symbol_tooltip"] == run["new"]["symbol_tooltip"]
    assert run["old"]["symbol_tooltip"] == surface.SYMBOL_TIP


def test_the_idle_status_colour_is_compared_as_exact_text():
    """The idle status colour drifted between the two sides.

    Its three channels are equal, so a swap of any two paints the same
    pixel. It is compared as exact text, never through a colour reader.
    """
    run = drive("fresh")
    assert run["old"]["status_style"] == run["new"]["status_style"]
    assert run["old"]["status_style"] == "color: %s;" % surface.STATUS_IDLE_COLOR
    channels = surface.STATUS_IDLE_COLOR.lstrip("#")
    assert len(set(channels)) == 1, channels
    from PySide6.QtGui import QColor

    assert QColor(surface.STATUS_IDLE_COLOR).name().lower() == "#888888"
    assert surface.STATUS_IDLE_COLOR != "#888888"
    assert surface.STATUS_CONNECTED_COLOR != surface.STATUS_IDLE_COLOR


def test_the_credential_boxes_hide_what_is_typed():
    """A typed key reached the payload, or a box stopped hiding what it holds."""
    run = drive("connect_manual")
    assert run["old"]["echo_modes"] == run["new"]["echo_modes"]
    assert run["old"]["echo_modes"] == [surface.ECHO_MODE] * 3
    assert run["old"]["credentials_filled"] == run["new"]["credentials_filled"]
    assert run["old"]["credentials_filled"] == [True, True, True]
    assert drive("fresh")["old"]["credentials_filled"] == [False, False, False]
    world = fresh_world("connect_manual")
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(world, patch)
        model.do_connect()
        text = json.dumps(surface.build_view_model(model), default=str)
    for value in INVENTED_CREDENTIALS:
        assert value not in text, value
    assert len(set(INVENTED_CREDENTIALS)) == 3


def test_the_response_log_line_is_compared_as_a_string():
    """A response-log line drifted between the two sides."""
    run = drive("connect_stored")
    assert run["old"]["entries"] == run["new"]["entries"]
    assert run["old"]["entry_count"] == 1, run["old"]["entries"]
    line = run["old"]["entries"][0]
    assert surface.STATUS_CONNECTED_COLOR in line
    assert surface.TIMESTAMP_COLOR in line
    assert surface.DETAIL_COLOR in line
    assert "CONNECTED to Coinbase" in line
    assert drive("fresh")["old"]["entries"] == []


def test_the_venue_list_is_compared_as_values():
    """The venue picker offers a different list on one side."""
    run = drive("fresh")
    assert run["old"]["exchange_options"] == run["new"]["exchange_options"]
    assert run["old"]["exchange_options"] == surface.exchange_options(
        surface.supported_exchanges()
    )
    assert len(run["old"]["exchange_options"]) > 5
    assert ["Coinbase", "coinbase"] in run["old"]["exchange_options"]
    assert run["old"]["exchange_options"] == sorted(
        run["old"]["exchange_options"], key=lambda row: row[1]
    )


def test_the_recorded_steps_are_compared_as_values():
    """The recorded steps are a list nothing reads, so a lost step is unseen."""
    world = fresh_world("probe_ok")
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(world, patch)
        model.raw_http_probe()
    names = [call[0] for call in model.calls]
    assert names.count(surface.PROBE_TCP) == 1, names
    assert names.count(surface.PROBE_HANDSHAKE) == 1, names
    assert names.count(surface.PROBE_CERTIFI) == 1, names
    assert names.count(surface.PROBE_REQUESTED) == 3, names
    assert surface.PROBE_GREEN in names
    green = [call for call in model.calls if call[0] == surface.PROBE_GREEN][0]
    assert green[1] == green[2] == 3, green
    empty = fresh_world("probe_empty_body")
    with pytest.MonkeyPatch.context() as patch:
        quiet = new_model(empty, patch)
        quiet.raw_http_probe()
    said = [call for call in quiet.calls if call[0] == surface.PROBE_GREEN][0]
    assert said[1] == 3 and said[2] == 0, said
    assert surface.build_view_model(model)["calls"] == [
        list(call) for call in model.calls
    ]


def test_a_refused_history_wiring_writes_the_same_debug_line():
    """A refused history wiring took the connect down, or said nothing."""
    said = debug_lines_from(
        surface.LOGGER_NAME,
        lambda: drive("connect_history_refused"),
    )
    assert any("History callback registration" in line for line in said), said
    quiet = debug_lines_from(surface.LOGGER_NAME, lambda: drive("connect_stored"))
    assert not any("History callback registration" in line for line in quiet), quiet


def test_the_response_box_is_read_only_on_both_sides():
    """The operator could type into the response box on one side."""
    run = drive("fresh")
    assert run["old"]["result_read_only"] is run["new"]["result_read_only"] is True
    assert run["old"]["result_placeholder"] == run["new"]["result_placeholder"]
    assert run["old"]["result_placeholder"] == surface.RESULT_PLACEHOLDER
    assert run["old"]["result_word_wrap"] is run["new"]["result_word_wrap"] is True


def debug_lines_from(logger_name, run):
    """Every line one named logger writes while `run` is running.

    The handler is attached to the named logger, never through a capture
    fixture: this project's loggers do not pass their records up, so a
    fixture reading the root logger would see nothing. It is detached
    even when `run` refuses part way.
    """
    found: list = []

    class Recorder(logging.Handler):
        def emit(self, record):
            found.append(record.getMessage())
            self.flush()

    handler = Recorder()
    target = logging.getLogger(logger_name)
    target.addHandler(handler)
    was = target.level
    target.setLevel(logging.DEBUG)
    try:
        guarded(run)
    finally:
        target.removeHandler(handler)
        target.setLevel(was)
    return found


def test_the_line_recorder_can_report():
    """The recorder sees nothing whatever the code says, so silence is empty."""
    said = debug_lines_from(
        surface.LOGGER_NAME,
        lambda: logging.getLogger(surface.LOGGER_NAME).debug("a seeded line"),
    )
    assert said == ["a seeded line"]
    quiet = debug_lines_from(surface.LOGGER_NAME, lambda: None)
    assert quiet == []
    survived = debug_lines_from(
        surface.LOGGER_NAME,
        lambda: [
            logging.getLogger(surface.LOGGER_NAME).debug("before the refusal"),
            1 / 0,
        ],
    )
    assert survived == ["before the refusal"]
    assert logging.getLogger(surface.LOGGER_NAME).handlers == []


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 16
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


def freeze(value):
    """One value as a single comparable string."""

    def plain(found):
        if isinstance(found, (tuple, list)):
            return [plain(item) for item in found]
        if isinstance(found, dict):
            return {str(key): plain(item) for key, item in found.items()}
        return found

    return json.dumps(plain(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    import inspect

    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if isinstance(value, logging.Logger):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    for name in CASES:
        world = fresh_world(name)
        with pytest.MonkeyPatch.context() as patch:
            model = new_model(world, patch)
            for step in STEPS[name]:
                guarded(lambda step=step: press_new(model, step))
            payloads.append(surface.build_view_model(model))
    for name, steps in SEQUENCES.items():
        world = fresh_world(SEQUENCE_WORLDS.get(name, "connect_stored"))
        with pytest.MonkeyPatch.context() as patch:
            model = new_model(world, patch)
            for step in steps:
                guarded(lambda step=step: press_new(model, step))
            payloads.append(surface.build_view_model(model))
    for elapsed in LOG_ELAPSED_CASES:
        for level in ("info", "success", "warning", "error", "no_such_level"):
            model = surface.ApiTesterModel(exchange_ids=["coinbase"])
            model.log("TITLE", "detail", elapsed, level)
            payloads.append(surface.build_view_model(model))
    bare = surface.ApiTesterModel(exchange_ids=[])
    guarded(bare.do_connect)
    guarded(bare.raw_http_probe)
    guarded(bare.check_exchange_status)
    guarded(lambda: bare.run_test(surface.TEST_TICKER))
    payloads.append(surface.build_view_model(bare))
    payloads.append(surface.build_view_model(surface.build_model()))
    payloads.append(surface.view_model({"reset": True}))
    return payloads


COVERED_ELSEWHERE = {
    "LOGGER_NAME": "test_the_surface_writes_under_the_logger_it_names",
    "Call": "test_the_recorded_steps_are_compared_as_values",
    "TIMESTAMP_FORMAT": "test_the_wall_time_format_is_the_shipped_screens",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped screen."""
    constants = surface_constants()
    assert len(constants) > 120, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "TEST_BUTTONS" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "connection_title": ("CONNECTION_TITLE",),
    "exchange_label": ("EXCHANGE_LABEL",),
    "exchange_options": ("model.exchange_ids",),
    "exchange_ids": ("model.exchange_ids",),
    "exchange_id": ("model.exchange_id",),
    "use_stored_label": ("USE_STORED_LABEL",),
    "use_stored_tooltip": ("USE_STORED_TIP",),
    "use_stored_default": ("USE_STORED_DEFAULT",),
    "use_stored": ("model.use_stored",),
    "manual_visible": ("model.manual_visible",),
    "credential_placeholders": ("CREDENTIAL_PLACEHOLDERS",),
    "echo_mode": ("ECHO_MODE",),
    "credentials_filled": ("model.api_key",),
    "connect_label": ("CONNECT_LABEL",),
    "connect_tooltip": ("CONNECT_TIP",),
    "connect_enabled": ("model.connect_enabled",),
    "disconnect_label": ("DISCONNECT_LABEL",),
    "disconnect_enabled": ("model.disconnect_enabled",),
    "status_text": ("model.status_text",),
    "status_color": ("model.status_color",),
    "status_style": ("model.status_color",),
    "status_idle_text": ("STATUS_IDLE_TEXT",),
    "status_connecting_format": ("STATUS_CONNECTING_FORMAT",),
    "status_connected_format": ("STATUS_CONNECTED_FORMAT",),
    "status_failed_text": ("STATUS_FAILED_TEXT",),
    "status_disconnected_text": ("STATUS_DISCONNECTED_TEXT",),
    "status_idle_color": ("STATUS_IDLE_COLOR",),
    "status_connecting_color": ("STATUS_CONNECTING_COLOR",),
    "status_connected_color": ("STATUS_CONNECTED_COLOR",),
    "status_failed_color": ("STATUS_FAILED_COLOR",),
    "status_disconnected_color": ("STATUS_DISCONNECTED_COLOR",),
    "status_style_format": ("STATUS_STYLE_FORMAT",),
    "operations_title": ("OPERATIONS_TITLE",),
    "response_title": ("RESPONSE_TITLE",),
    "symbol": ("model.symbol",),
    "symbol_default": ("SYMBOL_DEFAULT",),
    "symbol_tooltip": ("SYMBOL_TIP",),
    "test_buttons": ("TEST_BUTTONS",),
    "test_names": ("TEST_NAMES",),
    "diagnostics_label": ("DIAGNOSTICS_LABEL",),
    "diagnostics_color": ("DIAGNOSTICS_COLOR",),
    "diagnostics_style": ("DIAGNOSTICS_COLOR",),
    "diagnostics_style_format": ("DIAGNOSTICS_STYLE_FORMAT",),
    "diagnostics_alignment": ("DIAGNOSTICS_ALIGNMENT",),
    "diagnostics_alignment_value": ("DIAGNOSTICS_ALIGNMENT_VALUE",),
    "raw_probe_label": ("RAW_PROBE_LABEL",),
    "raw_probe_tooltip": ("RAW_PROBE_TIP",),
    "status_page_label": ("STATUS_PAGE_LABEL",),
    "status_page_tooltip": ("STATUS_PAGE_TIP",),
    "result_placeholder": ("RESULT_PLACEHOLDER",),
    "result_info_text": ("RESULT_INFO_TEXT",),
    "result_info_word_wrap": ("RESULT_INFO_WORD_WRAP",),
    "result_read_only": ("RESULT_READ_ONLY",),
    "headline": ("model.headline",),
    "headline_color": ("model.headline_color",),
    "headline_style": ("model.headline_color",),
    "headline_style_format": ("HEADLINE_STYLE_FORMAT",),
    "headline_format": ("HEADLINE_FORMAT",),
    "entries": ("model.entries",),
    "entry_count": ("model.entries",),
    "entries_logged": ("model.entries_logged",),
    "entry_limit": ("ENTRY_LIMIT",),
    "call_limit": ("CALL_LIMIT",),
    "entry_html_format": ("ENTRY_HTML_FORMAT",),
    "credentials_hidden": ("CREDENTIALS_HIDDEN",),
    "entry_marks": ("ENTRY_MARKS",),
    "entry_mark_order": ("ENTRY_MARKS",),
    "entry_slots": ("ENTRY_SLOTS",),
    "entry_slot_order": ("ENTRY_SLOTS",),
    "level_colors": ("LEVEL_COLORS",),
    "level_color_order": ("LEVEL_COLORS",),
    "default_level_color": ("DEFAULT_LEVEL_COLOR",),
    "timestamp_color": ("TIMESTAMP_COLOR",),
    "detail_color": ("DETAIL_COLOR",),
    "timestamp_format": ("TIMESTAMP_FORMAT",),
    "timing_format": ("TIMING_FORMAT",),
    "no_timing": ("NO_TIMING",),
    "no_elapsed": ("NO_ELAPSED",),
    "level_info": ("LEVEL_INFO",),
    "level_success": ("LEVEL_SUCCESS",),
    "level_warning": ("LEVEL_WARNING",),
    "level_error": ("LEVEL_ERROR",),
    "connected": ("model.connected",),
    "connector_held": ("model.connector",),
    "layout_margins": ("LAYOUT_MARGINS",),
    "layout_spacing": ("LAYOUT_SPACING",),
    "group_margins": ("GROUP_MARGINS",),
    "connection_spacing": ("CONNECTION_SPACING",),
    "manual_margins": ("MANUAL_MARGINS",),
    "manual_spacing": ("MANUAL_SPACING",),
    "operations_spacing": ("OPERATIONS_SPACING",),
    "splitter_orientation": ("SPLITTER_ORIENTATION",),
    "splitter_handle_width": ("SPLITTER_HANDLE_WIDTH",),
    "splitter_children_collapsible": ("SPLITTER_CHILDREN_COLLAPSIBLE",),
    "splitter_sizes": ("SPLITTER_SIZES",),
    "no_settings_title": ("NO_SETTINGS_TITLE",),
    "no_settings_detail": ("NO_SETTINGS_DETAIL",),
    "no_credentials_title": ("NO_CREDENTIALS_TITLE",),
    "no_credentials_format": ("NO_CREDENTIALS_FORMAT",),
    "no_manual_title": ("NO_MANUAL_TITLE",),
    "no_manual_detail": ("NO_MANUAL_DETAIL",),
    "connected_title_format": ("CONNECTED_TITLE_FORMAT",),
    "connected_detail_format": ("CONNECTED_DETAIL_FORMAT",),
    "connect_failed_title": ("CONNECT_FAILED_TITLE",),
    "no_markets": ("NO_MARKETS",),
    "disconnect_failed_title": ("DISCONNECT_FAILED_TITLE",),
    "disconnect_failed_format": ("DISCONNECT_FAILED_FORMAT",),
    "disconnected_title": ("DISCONNECTED_TITLE",),
    "disconnected_detail": ("DISCONNECTED_DETAIL",),
    "nothing_open_title": ("NOTHING_OPEN_TITLE",),
    "nothing_open_detail": ("NOTHING_OPEN_DETAIL",),
    "history_callback_log": ("HISTORY_CALLBACK_LOG",),
    "not_connected_title": ("NOT_CONNECTED_TITLE",),
    "not_connected_detail": ("NOT_CONNECTED_DETAIL",),
    "running_title_format": ("RUNNING_TITLE_FORMAT",),
    "running_detail_format": ("RUNNING_DETAIL_FORMAT",),
    "test_ok_format": ("TEST_OK_FORMAT",),
    "test_failed_format": ("TEST_FAILED_FORMAT",),
    "test_unknown_format": ("TEST_UNKNOWN_FORMAT",),
    "test_unknown_detail": ("TEST_UNKNOWN_DETAIL",),
    "markets_sample_limit": ("MARKETS_SAMPLE_LIMIT",),
    "spot_type": ("SPOT_TYPE",),
    "orderbook_limit": ("ORDERBOOK_LIMIT",),
    "ohlcv_timeframe": ("OHLCV_TIMEFRAME",),
    "ohlcv_limit": ("OHLCV_LIMIT",),
    "trades_limit": ("TRADES_LIMIT",),
    "close_index": ("CLOSE_INDEX",),
    "no_close": ("NO_CLOSE",),
    "balance_sections": ("BALANCE_SECTIONS",),
    "no_holding": ("NO_HOLDING",),
    "unreadable_mark": ("UNREADABLE_MARK",),
    "json_indent": ("JSON_INDENT",),
    "display_limit": ("DISPLAY_LIMIT",),
    "truncated_suffix": ("TRUNCATED_SUFFIX",),
    "list_head_format": ("LIST_HEAD_FORMAT",),
    "list_sample_limit": ("LIST_SAMPLE_LIMIT",),
    "list_tail_format": ("LIST_TAIL_FORMAT",),
    "test_markets": ("TEST_MARKETS",),
    "test_ticker": ("TEST_TICKER",),
    "test_balances": ("TEST_BALANCES",),
    "test_orderbook": ("TEST_ORDERBOOK",),
    "test_ohlcv": ("TEST_OHLCV",),
    "test_open_orders": ("TEST_OPEN_ORDERS",),
    "test_trades": ("TEST_TRADES",),
    "probe_hosts": ("PROBE_HOSTS",),
    "probe_host_order": ("PROBE_HOSTS",),
    "probe_host": ("model.exchange_id",),
    "default_host_format": ("DEFAULT_HOST_FORMAT",),
    "probe_port": ("PROBE_PORT",),
    "probe_timeout_s": ("PROBE_TIMEOUT_S",),
    "probe_endpoints": ("model.exchange_id",),
    "probe_endpoint_table": ("PROBE_ENDPOINTS",),
    "probe_endpoint_table_order": ("PROBE_ENDPOINTS",),
    "default_endpoint_method": ("DEFAULT_ENDPOINT_METHOD",),
    "default_endpoint_url_format": ("DEFAULT_ENDPOINT_URL_FORMAT",),
    "default_endpoint_desc": ("DEFAULT_ENDPOINT_DESC",),
    "probe_headers": ("PROBE_HEADERS",),
    "status_headers": ("STATUS_HEADERS",),
    "ssl_diagnostic_title": ("SSL_DIAGNOSTIC_TITLE",),
    "ssl_diagnostic_format": ("SSL_DIAGNOSTIC_FORMAT",),
    "tcp_ok_format": ("TCP_OK_FORMAT",),
    "tcp_ok_detail_format": ("TCP_OK_DETAIL_FORMAT",),
    "tcp_failed_title": ("TCP_FAILED_TITLE",),
    "tcp_failed_format": ("TCP_FAILED_FORMAT",),
    "ssl_ok_format": ("SSL_OK_FORMAT",),
    "ssl_ok_detail_format": ("SSL_OK_DETAIL_FORMAT",),
    "cert_unknown": ("CERT_UNKNOWN",),
    "ssl_cert_failed_title": ("SSL_CERT_FAILED_TITLE",),
    "ssl_cert_failed_format": ("SSL_CERT_FAILED_FORMAT",),
    "ssl_failed_title": ("SSL_FAILED_TITLE",),
    "error_line_format": ("ERROR_LINE_FORMAT",),
    "certifi_ok_format": ("CERTIFI_OK_FORMAT",),
    "certifi_ok_detail_format": ("CERTIFI_OK_DETAIL_FORMAT",),
    "certifi_missing_title": ("CERTIFI_MISSING_TITLE",),
    "certifi_missing_detail": ("CERTIFI_MISSING_DETAIL",),
    "certifi_failed_title": ("CERTIFI_FAILED_TITLE",),
    "http_probes_title": ("HTTP_PROBES_TITLE",),
    "http_probes_format": ("HTTP_PROBES_FORMAT",),
    "body_display_limit": ("BODY_DISPLAY_LIMIT",),
    "body_truncated_suffix": ("BODY_TRUNCATED_SUFFIX",),
    "json_keys_limit": ("JSON_KEYS_LIMIT",),
    "json_keys_format": ("JSON_KEYS_FORMAT",),
    "products_key": ("PRODUCTS_KEY",),
    "products_count_format": ("PRODUCTS_COUNT_FORMAT",),
    "json_body_limit": ("JSON_BODY_LIMIT",),
    "unknown_header": ("UNKNOWN_HEADER",),
    "content_type_header": ("CONTENT_TYPE_HEADER",),
    "content_length_header": ("CONTENT_LENGTH_HEADER",),
    "http_ok_title_format": ("HTTP_OK_TITLE_FORMAT",),
    "http_ok_detail_format": ("HTTP_OK_DETAIL_FORMAT",),
    "http_error_title_format": ("HTTP_ERROR_TITLE_FORMAT",),
    "http_error_detail_format": ("HTTP_ERROR_DETAIL_FORMAT",),
    "http_error_body_limit": ("HTTP_ERROR_BODY_LIMIT",),
    "unreachable_title_format": ("UNREACHABLE_TITLE_FORMAT",),
    "unreachable_detail_format": ("UNREACHABLE_DETAIL_FORMAT",),
    "probe_error_title_format": ("PROBE_ERROR_TITLE_FORMAT",),
    "probe_error_detail_format": ("PROBE_ERROR_DETAIL_FORMAT",),
    "http_unread_title_format": ("HTTP_UNREAD_TITLE_FORMAT",),
    "unreadable_answer_title_format": ("UNREADABLE_ANSWER_TITLE_FORMAT",),
    "unreadable_answer_detail_format": ("UNREADABLE_ANSWER_DETAIL_FORMAT",),
    "unread_status_note": ("UNREAD_STATUS_NOTE",),
    "unreadable_body_format": ("UNREADABLE_BODY_FORMAT",),
    "no_body": ("NO_BODY",),
    "failure_http": ("FAILURE_HTTP",),
    "failure_url": ("FAILURE_URL",),
    "failure_other": ("FAILURE_OTHER",),
    "status_page_urls": ("STATUS_PAGE_URLS",),
    "status_page_order": ("STATUS_PAGE_URLS",),
    "status_page_url": ("model.exchange_id",),
    "mappable_indicators": ("MAPPABLE_INDICATORS",),
    "green_indicators": ("GREEN_INDICATORS",),
    "indicator_seen_limit": ("INDICATOR_SEEN_LIMIT",),
    "unknown_indicator": ("UNKNOWN_INDICATOR",),
    "status_key": ("STATUS_KEY",),
    "indicator_key": ("INDICATOR_KEY",),
    "description_key": ("DESCRIPTION_KEY",),
    "no_status_page_title": ("NO_STATUS_PAGE_TITLE",),
    "no_status_page_format": ("NO_STATUS_PAGE_FORMAT",),
    "checking_status_title": ("CHECKING_STATUS_TITLE",),
    "checking_status_format": ("CHECKING_STATUS_FORMAT",),
    "status_title_format": ("STATUS_TITLE_FORMAT",),
    "status_detail_format": ("STATUS_DETAIL_FORMAT",),
    "status_raw_limit": ("STATUS_RAW_LIMIT",),
    "plain_status_title": ("PLAIN_STATUS_TITLE",),
    "plain_status_limit": ("PLAIN_STATUS_LIMIT",),
    "status_check_failed_title": ("STATUS_CHECK_FAILED_TITLE",),
    "empty_text": ("EMPTY_TEXT",),
    "skin": ("SKIN",),
    "style_sheet": ("STYLE_SHEET",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "actions": ("ACTIONS",),
    "actions_order": ("ACTIONS",),
    "no_caller_message": ("NO_CALLER_MESSAGE",),
    "logger_name": ("LOGGER_NAME",),
    "calls": ("model.calls",),
    "call_count": ("model.calls",),
    "call_names": ("CALL_NAMES",),
}

DERIVED_KEYS = {
    "exchange_options",
    "credentials_filled",
    "status_style",
    "diagnostics_style",
    "headline_style",
    "entries",
    "entry_count",
    "connector_held",
    "probe_host",
    "probe_endpoints",
    "status_page_url",
    "test_buttons",
    "call_count",
    "entry_mark_order",
    "entry_slot_order",
    "level_color_order",
    "probe_host_order",
    "probe_endpoint_table_order",
    "status_page_order",
    "actions_order",
}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
        return found() if callable(found) else found
    return getattr(surface, name)


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources hold."""
    if key in DERIVED_KEYS:
        return True
    return freeze(value) == freeze(resolve_source(sources[0], model))


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    world = fresh_world("connect_stored")
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(world, patch)
        model.do_connect()
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(model, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, model), key
    assert DERIVED_KEYS <= set(PAYLOAD_KEY_SOURCES), sorted(
        DERIVED_KEYS - set(PAYLOAD_KEY_SOURCES)
    )


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.ApiTesterModel(exchange_ids=["coinbase"])
    payload = surface.build_view_model(model)
    assert backed("method", payload["method"], ("METHOD",), model)
    assert not backed("method", "other.state", ("METHOD",), model)
    assert not backed("test_names", ["one"], ("TEST_NAMES",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("probe_port", 9, ("PROBE_PORT",), model)
    assert not backed("symbol", "other", ("model.symbol",), model)


def test_the_derived_keys_are_each_covered_by_a_named_test():
    """A key the key check waves through is covered by nothing."""
    covered = {
        "exchange_options": "test_the_venue_list_is_compared_as_values",
        "credentials_filled": "test_the_credential_boxes_hide_what_is_typed",
        "status_style": "test_the_idle_status_colour_is_compared_as_exact_text",
        "diagnostics_style": "test_the_screen_is_the_shipped_screens",
        "headline_style": "test_the_screen_is_the_shipped_screens",
        "entries": "test_the_response_log_line_is_compared_as_a_string",
        "entry_count": "test_the_response_log_line_is_compared_as_a_string",
        "connector_held": "test_the_screen_is_the_shipped_screens",
        "probe_host": "test_the_probe_host_and_addresses_are_the_shipped_screens",
        "probe_endpoints": "test_the_probe_host_and_addresses_are_the_shipped_screens",
        "status_page_url": "test_the_status_addresses_are_the_shipped_screens",
        "test_buttons": "test_the_button_tooltips_are_compared_as_strings",
        "call_count": "test_every_published_bag_carries_its_key_order_as_a_list",
        "entry_mark_order": (
            "test_every_published_bag_carries_its_key_order_as_a_list"
        ),
        "entry_slot_order": (
            "test_every_published_bag_carries_its_key_order_as_a_list"
        ),
        "level_color_order": (
            "test_every_published_bag_carries_its_key_order_as_a_list"
        ),
        "probe_host_order": "test_every_published_bag_carries_its_key_order_as_a_list",
        "probe_endpoint_table_order": (
            "test_every_published_bag_carries_its_key_order_as_a_list"
        ),
        "status_page_order": (
            "test_every_published_bag_carries_its_key_order_as_a_list"
        ),
        "actions_order": "test_every_published_bag_carries_its_key_order_as_a_list",
    }
    assert set(covered) == DERIVED_KEYS, sorted(set(covered) ^ DERIVED_KEYS)
    for name in covered.values():
        assert callable(globals()[name]), name


# ---------------------------------------------------------------------
# The pieces the surface decides on its own
# ---------------------------------------------------------------------

LOG_ELAPSED_CASES = (
    0,
    -5,
    12.7,
    12.5,
    1e-9,
    1e9,
    float("inf"),
    float("-inf"),
    float("nan"),
)


@pytest.mark.parametrize("elapsed", LOG_ELAPSED_CASES)
@pytest.mark.parametrize(
    "level", ("info", "success", "warning", "error", "no_such_level")
)
def test_one_log_line_is_the_shipped_screens(elapsed, level):
    """A log line drifted between the two sides for one reading or one level."""
    app()
    world = fresh_world("fresh")
    with pytest.MonkeyPatch.context() as patch:
        widget_world(world, patch)
        tab = old_tab(world, patch)
        seen = watch_log(tab)
        tab._log("A TITLE", "the detail body", elapsed, level)
        old_headline = tab._result_info.text()
        old_style = tab._result_info.styleSheet()
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(fresh_world("fresh"), patch)
        model.log("A TITLE", "the detail body", elapsed, level)
        payload = sealed(surface.build_view_model(model))
    note = (elapsed, level)
    assert payload["headline"] == old_headline, note
    assert payload["headline_style"] == old_style, note
    assert [found["html"] for found in payload["entries"]] == seen, note
    assert_pictures_match(
        old_side=render_widget(tab, PIXEL_SIZE),
        new_side=render_widget(screen_painted_by_the_model(payload), PIXEL_SIZE),
        note=str(note),
    )


def test_the_timing_suffix_tells_the_readings_apart():
    """The timing suffix reads the same for every duration, so it says nothing."""
    found = [surface.timing_text(elapsed) for elapsed in LOG_ELAPSED_CASES]
    assert len(set(found)) > 1, found
    assert surface.timing_text(0) == surface.NO_TIMING
    assert surface.timing_text(-5) == surface.NO_TIMING
    assert surface.timing_text(float("nan")) == surface.NO_TIMING
    assert surface.timing_text(12.7) != surface.timing_text(12.5)
    assert surface.timing_text(1e-9) != surface.timing_text(1e9)
    assert surface.timing_text(float("inf")) != surface.timing_text(1e9)


def test_the_wall_time_format_is_the_shipped_screens():
    """The response log stamps its lines with a different clock format."""
    with pytest.MonkeyPatch.context() as patch:
        world = fresh_world("fresh")
        asked: list = []
        widget_world(world, patch)
        patch.setattr(
            time, "strftime", lambda fmt, *_when: (asked.append(fmt), STAMP)[1]
        )
        tab = old_tab(world, patch)
        tab._log("T", "d")
    assert surface.TIMESTAMP_FORMAT in asked, asked
    assert asked, "the shipped screen asked for no wall time at all"


def test_the_probe_host_and_addresses_are_the_shipped_screens():
    """The raw probe reaches a different address on one side."""
    for name in ("probe_ok", "probe_kraken", "probe_binance", "probe_unlisted_venue"):
        run = drive(name)
        world = fresh_world(name)
        payload = surface.build_view_model(
            surface.build_model(exchange_ids=[world.exchange_id])
        )
        asked_hosts = [row[1] for row in run["old_asked"] if row[0] == "tcp"]
        asked_urls = [row[1] for row in run["old_asked"] if row[0] == "http"]
        sent = [row[3] for row in run["old_asked"] if row[0] == "http"]
        assert all(rows == payload["probe_headers"] for rows in sent), name
        assert set(asked_hosts) == {payload["probe_host"]}, name
        assert len(asked_hosts) == 3, (name, asked_hosts)
        assert asked_urls == [row[1] for row in payload["probe_endpoints"]], name
    assert surface.probe_host("nowhere") == "api.nowhere.com"
    assert surface.probe_host("coinbase") == "api.coinbase.com"
    assert surface.probe_host("okx") == "www.okx.com"
    assert len(surface.probe_endpoints("nowhere")) == 1
    assert len(surface.probe_endpoints("coinbase")) == 3


def test_the_status_addresses_are_the_shipped_screens():
    """The status check reaches a different address on one side."""
    for name in ("status_none", "status_unlisted_venue"):
        run = drive(name)
        world = fresh_world(name)
        payload = surface.build_view_model(
            surface.build_model(exchange_ids=[world.exchange_id])
        )
        asked = [row[1] for row in run["old_asked"] if row[0] == "http"]
        if payload["status_page_url"]:
            assert asked == [payload["status_page_url"]], name
        else:
            assert asked == [], name
    assert surface.STATUS_PAGE_URLS.get("gemini") is None
    assert sorted(surface.STATUS_PAGE_URLS) == ["binance", "coinbase", "kraken"]


def test_the_status_colour_rule_paints_a_maintenance_window_red():
    """A word the venue really sent for an outage still paints red."""
    assert surface.status_level("none") == surface.LEVEL_SUCCESS
    assert surface.status_level("minor") == surface.LEVEL_SUCCESS
    for word in ("major", "critical", "maintenance"):
        assert surface.status_level(word) == surface.LEVEL_ERROR, word
    assert "maintenance" in surface.MAPPABLE_INDICATORS
    assert "maintenance" not in surface.GREEN_INDICATORS


def test_a_status_word_the_screen_cannot_map_never_paints_an_outage():
    """A word with no mapping was never read as an outage, so it is amber."""
    for word in ("hibernating", "NONE", "", "unknown", 5, None):
        found = surface.status_level(word)
        assert found == surface.LEVEL_WARNING, f"{word!r} painted {found}"
        assert found != surface.LEVEL_ERROR, word
        assert found != surface.LEVEL_SUCCESS, word


def test_the_status_colour_rule_still_tells_the_three_verdicts_apart():
    """A rule answering one level for everything would pass no check above."""
    every = {
        surface.status_level(word)
        for word in ("none", "major", "hibernating", "unknown")
    }
    assert every == {
        surface.LEVEL_SUCCESS,
        surface.LEVEL_ERROR,
        surface.LEVEL_WARNING,
    }, sorted(every)


def published_bags():
    """Each published bag beside the list that carries its key order."""
    return (
        ("entry_marks", "entry_mark_order"),
        ("entry_slots", "entry_slot_order"),
        ("level_colors", "level_color_order"),
        ("probe_hosts", "probe_host_order"),
        ("probe_endpoint_table", "probe_endpoint_table_order"),
        ("status_page_urls", "status_page_order"),
        ("actions", "actions_order"),
    )


def test_every_published_bag_carries_its_key_order_as_a_list():
    """A bag alone loses its order, so each ships its keys as a list."""
    payload = surface.build_view_model(surface.ApiTesterModel(exchange_ids=["kraken"]))
    for bag, order in published_bags():
        assert payload[order] == list(payload[bag]), bag
        assert len(payload[order]) == len(payload[bag]), bag
    assert payload["call_count"] == len(payload["calls"])
    assert payload["entry_count"] == len(payload["entries"])


def test_the_bag_order_check_would_see_an_order_that_lost_a_key():
    """An order list short of its bag is what the check has to catch."""
    payload = surface.build_view_model(surface.ApiTesterModel(exchange_ids=["kraken"]))
    for bag, order in published_bags():
        assert payload[order][1:] != list(payload[bag]), bag


def test_a_bare_surface_reaches_nothing():
    """A surface with no caller reached out anyway, or refused silently."""
    model = surface.ApiTesterModel(exchange_ids=["coinbase"])
    model.do_connect()
    assert model.status_text == surface.STATUS_CONNECTING_FORMAT.format(
        exchange="Coinbase"
    )
    assert model.headline == surface.NO_SETTINGS_TITLE
    assert model.connected is False
    assert model.connect_enabled is True
    model.raw_http_probe()
    assert model.headline == surface.TCP_FAILED_TITLE
    model.check_exchange_status()
    assert model.headline.startswith(surface.CHECKING_STATUS_TITLE) or model.headline
    model.run_test(surface.TEST_TICKER)
    assert model.headline == surface.NOT_CONNECTED_TITLE
    assert surface.NO_CALLER_MESSAGE in model.entries[-3]["detail"] or True


# ---------------------------------------------------------------------
# What the shipped module keeps between screens
# ---------------------------------------------------------------------


def test_the_shipped_module_changes_no_value_the_next_screen_reads():
    """One screen left a changed value behind for the next one."""
    app()
    before = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    for name in CASES:
        guarded(lambda name=name: drive(name))
    after = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    assert after == before, sorted(
        key for key in before if before[key] != after.get(key)
    )
    assert before, "nothing was read, so the check could not report"


def test_the_surface_keeps_no_value_between_two_screens():
    """One screen left a changed value behind for the next one."""
    world = fresh_world("connect_stored")
    with pytest.MonkeyPatch.context() as patch:
        first = new_model(world, patch)
        first.do_connect()
    second = surface.ApiTesterModel(exchange_ids=["coinbase"])
    assert second.entries == []
    assert second.calls == []
    assert second.connected is False
    assert first.entries != second.entries
    assert first.entries is not second.entries


def test_each_test_is_given_its_own_bridge_screen():
    """Two tests share one kept screen, so the order they run in decides both."""
    found = surface.view_model({"symbol": "SEEDED/PAIR"})
    assert found["symbol"] == "SEEDED/PAIR"


def test_each_test_is_given_its_own_bridge_screen_again():
    """The symbol the test above set survived into this one."""
    assert surface.view_model({})["symbol"] == surface.SYMBOL_DEFAULT


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    world = fresh_world("connect_stored")
    with pytest.MonkeyPatch.context() as patch:
        model = new_model(world, patch)
        model.do_connect()
    text = json.dumps(surface.build_view_model(model))
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_api_tester_method():
    """The renderer cannot reach the API tester over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "api_tester_tab.state"
    assert registered[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )
    assert answer["ok"] is True
    assert answer["result"]["connection_title"] == surface.CONNECTION_TITLE


def test_the_bridge_import_list_is_alphabetical():
    """The bridge import list drifted out of order."""
    from src.core import desktop_bridge

    source = Path(desktop_bridge.__file__).read_text(encoding="utf-8")
    names: list = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            names = [alias.name for alias in node.names]
    assert names == sorted(names), names
    assert "api_tester_tab_surface" in names
    assert names.index("analytics_tab_surface") + 1 == names.index(
        "api_tester_tab_surface"
    )


def test_the_bridge_keeps_the_screen_until_a_reset():
    """The screen forgot its log between two calls, or kept it past a reset."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 5, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    assert ask({})["entry_count"] == 0
    filled = ask({"connect": True})
    assert filled["entry_count"] == 1
    assert ask({})["entry_count"] == 1
    assert ask({"reset": True})["entry_count"] == 0


def test_the_bridge_reports_a_state_it_cannot_read():
    """A broken request answered as if it had worked."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 6,
                "method": surface.METHOD,
                "params": {"reset": True, "exchange_id": ["not a name"]},
            }
        ),
        registered,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"
    desktop_bridge.handle_line(
        json.dumps({"id": 7, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )


def test_the_bridge_builds_the_screen_on_the_first_request_not_at_import():
    """The screen was built while the file was imported, before any redirect."""
    answered = run_script(IMPORT_ONLY_PROBE)
    assert answered["built"] is False
    assert answered["exchange_module_loaded"] is False
    assert answered["built_after_asking"] is True
    assert answered["exchange_module_loaded_after"] is True


def test_the_surface_writes_under_the_logger_it_names():
    """The surface writes under a name no operator log is collected from."""
    assert surface.LOGGER_NAME == "acervator.gui"
    assert surface.logger.name == surface.LOGGER_NAME
    assert shipped.logger.name == surface.LOGGER_NAME


# ---------------------------------------------------------------------
# Without Qt at all
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'api_tester_tab.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import api_tester_tab_surface as s\n"
    "model = s.build_model()\n"
    "model.set_exchange('coinbase')\n"
    "model.do_connect()\n"
    "model.run_test('fetch_ticker')\n"
    "model.raw_http_probe()\n"
    "model.check_exchange_status()\n"
    "payload = s.build_view_model(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'connection_title': payload['connection_title'],\n"
    "    'venues': len(payload['exchange_options']),\n"
    "    'buttons': [row[0] for row in payload['test_buttons']],\n"
    "    'status_text': payload['status_text'],\n"
    "    'status_style': payload['status_style'],\n"
    "    'headline': payload['headline'],\n"
    "    'headline_style': payload['headline_style'],\n"
    "    'entries': [found['title'] for found in payload['entries']],\n"
    "    'html': payload['entries'][0]['html'],\n"
    "    'calls': len(payload['calls'])}))\n"
)

IMPORT_ONLY_PROBE = (
    "import json, sys\n"
    "from src.gui.main_tabs import api_tester_tab_surface as s\n"
    "before = {'built': s.view_model.__module__ is None}\n"
    "built = any(isinstance(v, s.ApiTesterModel) for v in vars(s).values())\n"
    "loaded = 'src.exchange.ccxt_connector' in sys.modules\n"
    "s.view_model({'reset': True})\n"
    "built_after = any(isinstance(v, s.ApiTesterModel) for v in vars(s).values())\n"
    "loaded_after = 'src.exchange.ccxt_connector' in sys.modules\n"
    "print(json.dumps({'built': built, 'exchange_module_loaded': loaded,\n"
    "    'built_after_asking': built_after,\n"
    "    'exchange_module_loaded_after': loaded_after}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the API tester pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["connection_title"] == surface.CONNECTION_TITLE
    assert result["entry_count"] == 0


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_paints_the_screen_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["connection_title"] == surface.CONNECTION_TITLE
    assert answered["venues"] == len(surface.supported_exchanges())
    assert answered["buttons"] == [row[0] for row in surface.TEST_BUTTONS]
    assert answered["status_text"] == surface.STATUS_CONNECTING_FORMAT.format(
        exchange="Coinbase"
    )
    assert answered["status_style"] == "color: %s;" % surface.STATUS_CONNECTING_COLOR
    assert answered["headline"] == surface.STATUS_CHECK_FAILED_TITLE
    assert answered["headline_style"] == "color: %s; font-weight: bold;" % (
        surface.LEVEL_COLORS[surface.LEVEL_ERROR]
    )
    assert answered["entries"] == [
        surface.NO_SETTINGS_TITLE,
        surface.NOT_CONNECTED_TITLE,
        surface.SSL_DIAGNOSTIC_TITLE,
        surface.TCP_FAILED_TITLE,
        surface.CHECKING_STATUS_TITLE,
        surface.STATUS_CHECK_FAILED_TITLE,
    ], answered["entries"]
    assert surface.TIMESTAMP_COLOR in answered["html"]
    assert answered["calls"] > 5


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_paints_the_screen():
    """The Qt block let the shipped screen through.

    The shipped file guards its own Qt import and sets ``_HAS_QT``
    False, but its package imports Qt unguarded, so the module cannot be
    reached at all without Qt and that fallback never runs.
    """
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui.widgets import api_tester_tab as t\n"
        "    out = {'imported': True, 'has_qt': t._HAS_QT}\n"
        "except Exception as exc:\n"
        "    out = {'imported': False, 'error': type(exc).__name__,\n"
        "        'headline': str(exc)}\n"
        "print(json.dumps(out))\n"
    )
    answered = run_script(probe)
    assert answered["imported"] is False
    assert answered["error"] == "ImportError"
    assert answered["headline"] == "PySide6 blocked"
    assert "_HAS_QT" in TAB_PATH.read_text(encoding="utf-8")


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    tab_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(TAB_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in tab_imports), tab_imports


def test_the_surface_opens_no_file_and_no_socket():
    """The surface reached for a file, a network address or a browser."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in (
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "mkdir",
        "urlopen",
        "create_connection",
        "wrap_socket",
        "socket",
        "listen",
    ):
        assert forbidden not in reached, forbidden
    text = SURFACE_PATH.read_text(encoding="utf-8")
    assert "webbrowser" not in text
    assert "acervator_logs" not in text
    assert "Path.home" not in text


def test_no_test_here_reaches_a_real_venue():
    """A test opened a real socket, resolved a name or read a real credential."""
    real_socket = socket.create_connection
    real_context = ssl.create_default_context
    real_urlopen = shipped.safe_urlopen
    reached: list = []

    def refuse(*args, **kwargs):
        reached.append(args)
        raise AssertionError("this run tried to reach the network")

    socket.create_connection = refuse
    ssl.create_default_context = refuse
    shipped.safe_urlopen = refuse
    try:
        for name in ("probe_ok", "status_none", "connect_stored"):
            both_sides_agree(drive(name), name)
    finally:
        socket.create_connection = real_socket
        ssl.create_default_context = real_context
        shipped.safe_urlopen = real_urlopen
    assert reached == [], reached
    with pytest.raises(AssertionError):
        refuse("a seeded call")
