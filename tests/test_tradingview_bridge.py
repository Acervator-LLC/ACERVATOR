"""``TradingViewBridge`` alert parsing, auth, bind refusal and chart URL text.

``refuse_outside_connections`` counts every outward socket a test attempts, so
``get_chart_url`` is shown to build text without reaching tradingview.com.
``_start_basic_server`` is driven against a recording stand-in for
``http.server.HTTPServer``, and no test opens a listener.
"""

from __future__ import annotations

import asyncio
import http.server
import inspect
import ipaddress
import json
import logging
import socket
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.stocks.tradingview_bridge import BIND_ALL_INTERFACES, TradingViewBridge

STUB_BEARER = "bearer-value-under-test"


@pytest.fixture(autouse=True)
def refuse_outside_connections(monkeypatch):
    """Count and refuse every non-loopback connection a test in this module attempts.

    Loopback passes through, which the Windows ``asyncio`` event loop needs.
    """
    attempted: list = []
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def is_loopback(address) -> bool:
        try:
            return ipaddress.ip_address(address[0]).is_loopback
        except (ValueError, TypeError, IndexError):
            return False

    def watched_connect(self, address, *found, **named):
        if is_loopback(address):
            return real_connect(self, address, *found, **named)
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    def watched_create(address, *found, **named):
        if is_loopback(address):
            return real_create(address, *found, **named)
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket, "create_connection", watched_create)
    return attempted


def test_bind_all_interfaces_is_the_unspecified_ipv4_address():
    assert ipaddress.ip_address(BIND_ALL_INTERFACES).is_unspecified


def test_the_default_bind_host_is_a_loopback_address():
    assert ipaddress.ip_address(TradingViewBridge.DEFAULT_BIND_HOST).is_loopback


def test_start_refuses_all_interfaces_with_no_auth_token():
    bridge = TradingViewBridge(bind_host=BIND_ALL_INTERFACES)
    with pytest.raises(RuntimeError, match="refusing to start"):
        asyncio.run(bridge.start())
    assert bridge.running is False


def test_the_refusal_message_names_only_remedies_that_exist():
    bridge = TradingViewBridge(bind_host=BIND_ALL_INTERFACES)
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(bridge.start())
    message = str(raised.value)
    assert "set_auth_token" in message, message
    assert "force_unauthenticated_lan" in message, message
    assert "docs/" not in message, message


def test_check_auth_passes_every_request_while_no_token_is_set():
    bridge = TradingViewBridge()
    assert bridge._check_auth({}) is True


def test_check_auth_refuses_a_wrong_bearer_value():
    bridge = TradingViewBridge()
    bridge.set_auth_token(STUB_BEARER)
    assert bridge._check_auth({"Authorization": "Bearer wrong"}) is False


def test_check_auth_accepts_the_configured_bearer_value():
    bridge = TradingViewBridge()
    bridge.set_auth_token(STUB_BEARER)
    assert bridge._check_auth({"Authorization": f"Bearer {STUB_BEARER}"}) is True


def test_parse_alert_reads_the_json_body_shape():
    bridge = TradingViewBridge()
    body = json.dumps({"symbol": "aapl", "action": "BUY", "price": 185.5})
    alert = bridge._parse_alert(body)
    assert alert is not None
    assert (alert.symbol, alert.action) == ("AAPL", "buy")
    assert alert.price == pytest.approx(185.5)
    assert alert.raw == body


def test_parse_alert_reads_the_plain_text_body_shape():
    bridge = TradingViewBridge()
    alert = bridge._parse_alert("BUY AAPL @ 185.50")
    assert alert is not None
    assert (alert.symbol, alert.action) == ("AAPL", "buy")
    assert alert.price == pytest.approx(185.50)


def test_parse_alert_returns_none_for_a_one_word_body():
    bridge = TradingViewBridge()
    assert bridge._parse_alert("BUY") is None


def test_unregister_handler_drops_what_register_handler_added():
    bridge = TradingViewBridge()

    def handler(_alert):
        return None

    bridge.register_handler(handler)
    assert bridge._handlers == [handler]
    bridge.unregister_handler(handler)
    assert bridge._handlers == []


def test_get_chart_url_builds_text_and_opens_no_socket(refuse_outside_connections):
    url = TradingViewBridge.get_chart_url("AAPL", interval="60", theme="light")
    assert url.startswith("https://www.tradingview.com/widgetembed/")
    assert "symbol=AAPL" in url
    assert "interval=60" in url
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_sees_a_real_outward_address(
    refuse_outside_connections,
):
    """The counter reports nothing whatever a test reaches for."""
    with pytest.raises(OSError, match="outside the process"):
        socket.create_connection(("www.tradingview.com", 443), timeout=1)
    assert refuse_outside_connections == [("www.tradingview.com", 443)]


class RecordingServer:
    """Stands in for ``http.server.HTTPServer`` and binds nothing."""

    def __init__(self, address, handler_class) -> None:
        self.server_address = address
        self.RequestHandlerClass = handler_class

    def serve_forever(self) -> None:
        return None


class ImmediateThread:
    """Stands in for ``threading.Thread`` and runs its target on ``start``."""

    def __init__(self, target, daemon=False, name="") -> None:
        self._target = target
        self.daemon = daemon
        self.name = name

    def start(self) -> None:
        self._target()


@pytest.fixture()
def basic_server(monkeypatch):
    """Drive ``_start_basic_server`` onto ``RecordingServer`` and return it."""
    monkeypatch.setattr(http.server, "HTTPServer", RecordingServer)
    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    bridge = TradingViewBridge()
    asyncio.run(bridge._start_basic_server())
    return bridge


def test_start_basic_server_binds_the_configured_host_and_port(basic_server):
    assert isinstance(basic_server._server, RecordingServer)
    assert basic_server._server.server_address == (
        TradingViewBridge.DEFAULT_BIND_HOST,
        TradingViewBridge.DEFAULT_PORT,
    )


def test_the_basic_handler_logs_a_request_line_at_debug(basic_server, capture_log):
    handler_class = basic_server._server.RequestHandlerClass
    with capture_log("acervator.stocks.tradingview", logging.DEBUG) as records:
        handler_class.log_message(object(), "%s served", "a-request-line")
    assert records, "the handler logged nothing, so the message shape is unproven"
    assert records[0].getMessage() == "a-request-line served", records[0].getMessage()


def test_the_basic_handler_names_its_first_parameter_format(basic_server):
    handler_class = basic_server._server.RequestHandlerClass
    names = list(inspect.signature(handler_class.log_message).parameters)
    assert names[1] == "format", names
