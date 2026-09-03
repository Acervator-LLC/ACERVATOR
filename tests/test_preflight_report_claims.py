"""The pre-flight report states what the exchange answered, never a default."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui import preflight_check as shipped
from src.gui.main_tabs import preflight_check_surface as surface

PAIR = "RAVE/USD"
EXCHANGE = "coinbase"
BALANCE = 500.0
LIVE_TICKER = {"last": 0.0123}
TICK_SIZE_MODE = 4

REPORTED_ACTIVE_MARKET = {
    "active": True,
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}
NO_ACTIVE_FLAG_MARKET = {
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}

ACTIVE_YES_LINE = "Market active: Yes"
ACTIVE_NO_LINE = "Market active: No"
ACTIVE_UNREPORTED_LINE = "Market active: not reported"
PRICE_FIGURE_MARK = "Current price: $"
PRICE_UNREAD_LINE = "Current price: not read"

TICKER_DOWN = RuntimeError("ticker endpoint is down")
INACTIVE_WARNING_MARK = "Market reported as inactive"
ELAPSED_FIELD = "elapsed_ms"


class FakeExchange:
    """One ccxt exchange whose market and ticker answers are steerable."""

    market: dict = {}
    ticker: dict = {}
    ticker_error: Any = None
    precisionMode = TICK_SIZE_MODE

    def __init__(self, config: dict) -> None:
        self.config = dict(config)

    def load_markets(self) -> dict:
        return {PAIR: dict(type(self).market)}

    def fetch_ticker(self, symbol: str) -> dict:
        if type(self).ticker_error is not None:
            raise type(self).ticker_error
        assert symbol == PAIR
        return dict(type(self).ticker)


def install_ccxt(
    monkeypatch: pytest.MonkeyPatch,
    market: dict,
    ticker: dict,
    ticker_error: Any = None,
) -> None:
    """Put one steerable ccxt module in place of the installed one."""
    module = types.ModuleType("ccxt")
    setattr(
        module,
        EXCHANGE,
        type(
            "SpecExchange",
            (FakeExchange,),
            {"market": market, "ticker": ticker, "ticker_error": ticker_error},
        ),
    )
    monkeypatch.setitem(sys.modules, "ccxt", module)


def shipped_result(
    monkeypatch: pytest.MonkeyPatch,
    market: dict,
    ticker: dict,
    ticker_error: Any = None,
) -> Any:
    """The PreflightResult src/gui/preflight_check.py returns for one market."""
    install_ccxt(monkeypatch, market, ticker, ticker_error)
    found = shipped.check_symbol(EXCHANGE, PAIR, BALANCE)
    assert found.success, found.message
    return found


def shipped_report(
    monkeypatch: pytest.MonkeyPatch,
    market: dict,
    ticker: dict,
    ticker_error: Any = None,
) -> str:
    """The report format_result_for_user writes for one market."""
    return shipped.format_result_for_user(
        shipped_result(monkeypatch, market, ticker, ticker_error)
    )


def surface_result(
    monkeypatch: pytest.MonkeyPatch,
    market: dict,
    ticker: dict,
    ticker_error: Any = None,
) -> dict:
    """The result PreflightModel.check returns for one market."""
    install_ccxt(monkeypatch, market, ticker, ticker_error)
    model = surface.PreflightModel()
    found = model.check(EXCHANGE, PAIR, BALANCE)
    assert found["success"], found["message"]
    return found


def surface_report(
    monkeypatch: pytest.MonkeyPatch,
    market: dict,
    ticker: dict,
    ticker_error: Any = None,
) -> str:
    """The report PreflightModel.format_result writes for one market."""
    install_ccxt(monkeypatch, market, ticker, ticker_error)
    model = surface.PreflightModel()
    found = model.check(EXCHANGE, PAIR, BALANCE)
    assert found["success"], found["message"]
    return model.format_result(found)


def test_a_market_carrying_no_active_flag_is_not_reported_as_active(monkeypatch):
    """The shipped report defaulted this to Yes, which the exchange never said."""
    report = shipped_report(monkeypatch, NO_ACTIVE_FLAG_MARKET, LIVE_TICKER)
    assert ACTIVE_YES_LINE not in report, report
    assert ACTIVE_UNREPORTED_LINE in report, report


def test_the_active_claim_still_reads_a_reported_active_market_as_active(monkeypatch):
    """A market answering active True must still draw Yes in the report."""
    report = shipped_report(monkeypatch, REPORTED_ACTIVE_MARKET, LIVE_TICKER)
    assert ACTIVE_YES_LINE in report, report
    assert ACTIVE_UNREPORTED_LINE not in report, report


def test_the_surface_report_names_an_unreported_active_flag_the_same_way(monkeypatch):
    """The surface report must carry the shipped report's unreported wording."""
    report = surface_report(monkeypatch, NO_ACTIVE_FLAG_MARKET, LIVE_TICKER)
    assert ACTIVE_YES_LINE not in report, report
    assert ACTIVE_UNREPORTED_LINE in report, report


def test_the_surface_active_claim_still_reads_a_reported_market_as_active(monkeypatch):
    """The surface must still draw Yes where the market answered active True."""
    report = surface_report(monkeypatch, REPORTED_ACTIVE_MARKET, LIVE_TICKER)
    assert ACTIVE_YES_LINE in report, report
    assert ACTIVE_UNREPORTED_LINE not in report, report


def test_an_unreported_active_flag_raises_no_inactive_warning(monkeypatch):
    """No warning may claim the exchange reported a market it never described."""
    found = shipped_result(monkeypatch, NO_ACTIVE_FLAG_MARKET, LIVE_TICKER)
    assert found.warnings == [], found.warnings


def test_a_market_answering_active_false_still_raises_the_inactive_warning(monkeypatch):
    """A market answering active False must keep its inactive warning."""
    market = dict(REPORTED_ACTIVE_MARKET, active=False)
    found = shipped_result(monkeypatch, market, LIVE_TICKER)
    assert [one for one in found.warnings if INACTIVE_WARNING_MARK in one], found
    report = shipped_report(monkeypatch, market, LIVE_TICKER)
    assert ACTIVE_NO_LINE in report, report


def test_a_price_the_ticker_never_answered_is_named_as_not_read(monkeypatch):
    """The shipped report drew nothing where fetch_ticker raised."""
    report = shipped_report(
        monkeypatch, REPORTED_ACTIVE_MARKET, {}, ticker_error=TICKER_DOWN
    )
    assert PRICE_UNREAD_LINE in report, report
    assert PRICE_FIGURE_MARK not in report, report


def test_the_unread_price_claim_still_reads_an_answered_price_as_a_figure(monkeypatch):
    """A ticker answering a price must still draw that figure in the report."""
    report = shipped_report(monkeypatch, REPORTED_ACTIVE_MARKET, LIVE_TICKER)
    assert PRICE_FIGURE_MARK in report, report
    assert PRICE_UNREAD_LINE not in report, report


def test_the_surface_report_names_an_unread_price_the_same_way(monkeypatch):
    """The surface report must carry the shipped report's unread wording."""
    report = surface_report(
        monkeypatch, REPORTED_ACTIVE_MARKET, {}, ticker_error=TICKER_DOWN
    )
    assert PRICE_UNREAD_LINE in report, report
    assert PRICE_FIGURE_MARK not in report, report


def test_the_surface_unread_price_claim_still_draws_an_answered_price(monkeypatch):
    """The surface must still draw the figure a live ticker answered."""
    report = surface_report(monkeypatch, REPORTED_ACTIVE_MARKET, LIVE_TICKER)
    assert PRICE_FIGURE_MARK in report, report
    assert PRICE_UNREAD_LINE not in report, report


def test_a_price_the_ticker_answered_as_zero_is_not_named_as_unread(monkeypatch):
    """A zero the ticker did answer is a measured zero, not an unread price."""
    found = shipped_result(monkeypatch, REPORTED_ACTIVE_MARKET, {"last": 0.0})
    report = shipped.format_result_for_user(found)
    assert PRICE_UNREAD_LINE not in report, report
    assert PRICE_FIGURE_MARK not in report, report


def test_both_sides_carry_the_same_reported_flags_for_the_same_market(monkeypatch):
    """The surface result and the shipped result must agree field by field."""
    import dataclasses

    old = dataclasses.asdict(
        shipped_result(monkeypatch, NO_ACTIVE_FLAG_MARKET, {}, TICKER_DOWN)
    )
    new = surface_result(monkeypatch, NO_ACTIVE_FLAG_MARKET, {}, TICKER_DOWN)
    old.pop(ELAPSED_FIELD)
    new.pop(ELAPSED_FIELD)
    assert old == new
    assert new["active_reported"] is False
    assert new["price_read"] is False
