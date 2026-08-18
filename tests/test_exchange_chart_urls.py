"""v3.23.54 — pin tests for exchange_chart_urls.chart_url.

Operator directive 2026-07-28: clickable Symbol cell should open
the correct chart in the default browser. This test file locks
the URL shapes so a future edit doesn't silently ship a broken
chart link.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.exchange_chart_urls import (  # noqa: E402
    chart_url,
    supported_exchanges,
)


class TestKnownExchanges:
    def test_coinbase(self):
        assert chart_url("coinbase", "BTC/USD") == (
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")

    def test_coinbase_aliases(self):
        # ccxt uses "coinbaseexchange" for some builds
        for eid in ("coinbase", "coinbaseexchange", "coinbasepro"):
            assert chart_url(eid, "CHIP/USD") == (
                "https://www.coinbase.com/advanced-trade/spot/CHIP-USD")

    def test_kraken_lowercase(self):
        assert chart_url("kraken", "ETH/USD") == (
            "https://pro.kraken.com/app/trade/eth-usd")

    def test_binance_uses_underscore(self):
        assert chart_url("binance", "BTC/USDT") == (
            "https://www.binance.com/en/trade/BTC_USDT")

    def test_binance_us(self):
        assert chart_url("binanceus", "BTC/USD") == (
            "https://www.binance.us/en/trade/BTC_USD")

    def test_gemini_uses_no_separator(self):
        assert chart_url("gemini", "BTC/USD") == (
            "https://exchange.gemini.com/trade/BTCUSD")

    def test_bitfinex_colon(self):
        assert chart_url("bitfinex", "BTC/USD") == (
            "https://trading.bitfinex.com/t/BTC:USD")


class TestInputNormalization:
    def test_case_insensitive_exchange(self):
        assert chart_url("Coinbase", "BTC/USD") == (
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")
        assert chart_url("KRAKEN", "BTC/USD") == (
            "https://pro.kraken.com/app/trade/btc-usd")

    def test_symbol_dash_separator(self):
        assert chart_url("coinbase", "BTC-USD") == (
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")

    def test_symbol_underscore_separator(self):
        assert chart_url("coinbase", "BTC_USD") == (
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")

    def test_lowercase_symbol_uppercased(self):
        assert chart_url("coinbase", "btc/usd") == (
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")


class TestFailureModes:
    def test_unknown_exchange_returns_none(self):
        assert chart_url("mystery-exchange", "BTC/USD") is None

    def test_empty_exchange_returns_none(self):
        assert chart_url("", "BTC/USD") is None

    def test_empty_symbol_returns_none(self):
        assert chart_url("coinbase", "") is None

    def test_malformed_symbol_no_separator(self):
        assert chart_url("coinbase", "BTCUSD") is None

    def test_symbol_with_only_separator(self):
        assert chart_url("coinbase", "/") is None

    def test_symbol_with_empty_quote(self):
        assert chart_url("coinbase", "BTC/") is None

    def test_symbol_with_empty_base(self):
        assert chart_url("coinbase", "/USD") is None


class TestClickHandler:
    """v3.23.54 — click on Symbol cell dispatches to webbrowser.open
    with the URL built by chart_url."""

    def test_click_opens_url_via_webbrowser(self, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import (
            QApplication, QTableWidgetItem)
        from PySide6.QtCore import Qt
        _app = QApplication.instance() or QApplication([])
        from src.gui.main_window import BotStatusTable

        opened = {"url": None}

        def _fake_open(url, new=0):
            opened["url"] = url
            return True

        import webbrowser
        monkeypatch.setattr(webbrowser, "open", _fake_open)

        tbl = BotStatusTable()
        tbl.setRowCount(1)
        item = QTableWidgetItem("BTC/USD")
        item.setData(
            Qt.UserRole,
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")
        tbl.setItem(0, 1, item)
        tbl._on_cell_clicked(0, 1)
        assert opened["url"] == (
            "https://www.coinbase.com/advanced-trade/spot/BTC-USD")

    def test_click_non_symbol_col_is_noop(self, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import (
            QApplication, QTableWidgetItem)
        from PySide6.QtCore import Qt
        _app = QApplication.instance() or QApplication([])
        from src.gui.main_window import BotStatusTable

        called = {"n": 0}
        import webbrowser
        monkeypatch.setattr(
            webbrowser, "open",
            lambda *a, **k: called.__setitem__("n", called["n"] + 1))

        tbl = BotStatusTable()
        tbl.setRowCount(1)
        item = QTableWidgetItem("$200.0000")
        item.setData(Qt.UserRole, "https://should.not.open/")
        tbl.setItem(0, 4, item)   # Target column
        tbl._on_cell_clicked(0, 4)
        assert called["n"] == 0, (
            "Only col 1 (Symbol) should be clickable — Target/Ammo/Fire "
            "must not fire the chart-URL handler.")

    def test_click_symbol_without_url_is_noop(self, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import (
            QApplication, QTableWidgetItem)
        _app = QApplication.instance() or QApplication([])
        from src.gui.main_window import BotStatusTable

        called = {"n": 0}
        import webbrowser
        monkeypatch.setattr(
            webbrowser, "open",
            lambda *a, **k: called.__setitem__("n", called["n"] + 1))

        tbl = BotStatusTable()
        tbl.setRowCount(1)
        item = QTableWidgetItem("BTC/USD")  # no UserRole URL set
        tbl.setItem(0, 1, item)
        tbl._on_cell_clicked(0, 1)
        assert called["n"] == 0, (
            "Missing UserRole URL (unknown exchange) → click is a no-op.")


class TestRegistry:
    def test_supported_exchanges_covers_core_set(self):
        ex = set(supported_exchanges())
        # Must at least cover the exchanges Acervator currently ships
        # connectors for.
        assert "coinbase" in ex
        assert "kraken" in ex
        assert "binance" in ex

    def test_supported_exchanges_all_produce_urls(self):
        for eid in supported_exchanges():
            url = chart_url(eid, "BTC/USD")
            assert url is not None and url.startswith("http"), (
                f"exchange {eid!r} listed as supported but URL builder "
                f"produced {url!r}.")
