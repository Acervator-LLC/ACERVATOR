"""Drives history_tab.js from the model its Python surface publishes.

Node is not installed, so the module runs inside ``QJSEngine`` the way
every other renderer module in this repository is driven. React is not in
that engine, so the components are not rendered here; what is asserted is
everything the module decides before it draws -- which fields it demands,
which style it turns a Qt sheet into, which buttons it may answer itself,
and what it hands the one renderer that draws History's rows.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange import history_read_contract as hrc  # noqa: E402
from src.gui.main_tabs import history_tab_surface as surface  # noqa: E402
from tests.fixtures.web_js_modules import JsEngine, new_engine  # noqa: E402

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "history_tab.js"


class JsRuntime(JsEngine):
    module_path = MODULE_PATH
    setter = "acervatorHistoryTab.setTab"


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """A QJSEngine holding the module. ``qapp`` first: the engine needs
    a live QApplication and takes the process down without one."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_PATH.read_text(encoding="utf-8"))


def _row(tid: str, ts: float, side: str) -> dict:
    return {
        "id": tid,
        "exchange": "coinbase",
        "symbol": "CHIP/USD",
        "side": side,
        "amount": 2.0,
        "price": 10.0,
        "cost": 20.0,
        "fee": 0.01,
        "fee_currency": "USD",
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc),
    }


def _model(count: int = 4) -> dict:
    now = float(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
    trades = [
        _row(f"t{i}", now - i * 60, "BUY" if i % 2 else "SELL") for i in range(count)
    ]
    filters = hrc.default_filters(now)
    return surface.build_view_model(trades, filters, now_ts=now)


def _stub_panel(js: JsRuntime) -> None:
    """A table renderer that records what it was handed."""
    js.run(
        "var PUSHED = null; window.acervatorSetState = function (s) "
        "{ PUSHED = s; return 1; };"
    )


def test_the_module_runs_and_publishes_its_own_global(js: JsRuntime) -> None:
    """The file parses and exposes the surface a host binds to."""
    assert js.json("typeof acervatorHistoryTab") == "object"
    assert js.json("acervatorHistoryTab.method") == surface.METHOD


def test_a_whole_model_leaves_the_module_with_no_faults(js: JsRuntime) -> None:
    """The model the Python surface builds satisfies the module."""
    js.push(_model())
    assert js.json("acervatorHistoryTab.faults()") == []
    assert js.json("acervatorHistoryTab.isLoaded()") is True


def test_a_model_missing_a_field_is_reported(js: JsRuntime) -> None:
    """Positive control: the fault detector is not blind."""
    model = _model()
    del model["pager"]
    js.push(model)
    faults = js.json("acervatorHistoryTab.faults()")
    assert [one["field"] for one in faults] == ["pager"], faults
    assert js.json("acervatorHistoryTab.isLoaded()") is False


def test_the_module_demands_exactly_what_the_surface_publishes(
    js: JsRuntime,
) -> None:
    """No declared field the surface never sends, and none missing."""
    declared = sorted(js.json("acervatorHistoryTab.declaredFields()"))
    assert declared == sorted(
        _model()
    ), "the module and the surface disagree about the payload's fields"


def test_the_summary_style_sheet_becomes_a_css_style(js: JsRuntime) -> None:
    """The Qt sheet the tab wears is turned into properties a browser reads."""
    sheet = surface.SUMMARY_STYLE
    js.bind_json("SHEET", sheet)
    style = js.json("acervatorHistoryTab.styleOf(JSON.parse(SHEET))")
    assert style == {"color": "#aaaaaa", "padding": "2px 6px"}, style


def test_a_qt_only_value_is_dropped_rather_than_handed_to_the_browser(
    js: JsRuntime,
) -> None:
    """Control on the style test: a value only Qt understands does not pass."""
    js.bind_json("SHEET", "background: qlineargradient(x1:0); color: #112233;")
    style = js.json("acervatorHistoryTab.styleOf(JSON.parse(SHEET))")
    assert style == {"color": "#112233"}, style


def test_only_the_four_actions_the_surface_can_answer_are_bridged(
    js: JsRuntime,
) -> None:
    """Refresh needs an exchange and Export needs a file; neither is bridged."""
    bridged = js.json("acervatorHistoryTab.bridgedActions()")
    assert sorted(bridged) == ["apply", "next", "prev", "reset"]
    for key in surface.BUTTON_NAMES:
        js.bind_json("KEY", key)
        answered = js.json("acervatorHistoryTab.isBridged(JSON.parse(KEY))")
        assert answered is (key in bridged), key


def test_the_rows_go_to_the_one_renderer_that_draws_rows(js: JsRuntime) -> None:
    """The table is handed off, with the panel's own chrome turned off."""
    _stub_panel(js)
    model = _model()
    js.push(model)
    assert js.json("acervatorHistoryTab.pushRows(acervatorHistoryTab.state())") is True
    handed = js.json("PUSHED")
    assert handed["chrome"] == {
        "summary": False,
        "filters": False,
        "pager": False,
        "headers": True,
    }, "the panel would draw a second summary, filter bar and pager"
    assert handed["page"] == model["page"], "the rows were altered on the way"
    assert handed["page"]["rows"], "no rows were handed over at all"
    assert handed["columns"] == model["columns"]


def test_a_missing_table_renderer_is_reported_not_swallowed(
    js: JsRuntime,
) -> None:
    """Positive control: without the panel the hand-off says so."""
    js.push(_model())
    assert js.json("acervatorHistoryTab.pushRows(acervatorHistoryTab.state())") is False
    assert "acervatorSetState" in str(js.json("acervatorHistoryTab.loadError()"))


def test_no_bridge_is_reported_rather_than_raised(js: JsRuntime) -> None:
    """A host that binds no bridge gets a fault, not an exception."""
    js.run("acervatorHistoryTab.loadTab({});")
    assert "window.acervator.call" in str(js.json("acervatorHistoryTab.loadError()"))


def test_forget_clears_the_module_between_hosts(js: JsRuntime) -> None:
    """State does not survive a teardown."""
    js.push(_model())
    assert js.json("acervatorHistoryTab.state()") is not None
    js.run("acervatorHistoryTab.forget();")
    assert js.json("acervatorHistoryTab.state()") is None
    assert js.json("acervatorHistoryTab.faults()") == []
