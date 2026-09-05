"""The History tab and its surface answer the same question the same way.

``src.gui.main_tabs.history_tab_surface`` describes the chrome and the
controls that ``src.gui.history_tab`` still paints in Qt: the filter bar,
the summary line, the pager, the busy bar and the export button. These
tests drive the real widget and the real surface over the same rows and
compare what each one produces. Nothing here reads a source file; every
value is taken off a live widget or a returned model.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src.core import desktop_bridge  # noqa: E402
from src.exchange import history_read_contract as hrc  # noqa: E402
from src.gui.main_tabs import history_tab_surface as hts  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import QDateTime, QPoint  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QProgressBar,
    QPushButton,
)

from src.gui.history_tab import HistoryTab  # noqa: E402
from tests import qt_pixel  # noqa: E402

ROWS_PER_PAGE = hrc.PAGE_SIZE


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    running = QApplication.instance()
    if isinstance(running, QApplication):
        return running
    return QApplication(sys.argv)


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read EMPTY live logs, so the join never parses the operator's."""
    import src.trading.live_log_reader as llr

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter([])

    monkeypatch.setattr(llr, "live_gate_decisions", _read)
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _read)


class _Cfg:
    def __init__(self, symbol: str, ticker: str) -> None:
        self.symbol = symbol
        self.target_asset = ticker
        self.exchange_id = "coinbase"


class _Bot:
    def __init__(self, bot_id: str, symbol: str, ticker: str) -> None:
        self.bot_id = bot_id
        self.config = _Cfg(symbol, ticker)


class _BotManager:
    def __init__(self) -> None:
        self._async_loop: Optional[Any] = None
        self._bots = {
            "a": _Bot("bot-aaaa1111", "CHIP/USD", "CHIP"),
            "b": _Bot("bot-bbbb2222", "RAVE/USD", "RAVE"),
        }


def _row(tid: str, ts: float, symbol: str, exchange: str, side: str) -> dict:
    return {
        "id": tid,
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "amount": 2.0,
        "price": 10.0,
        "cost": 20.0,
        "fee": 0.01,
        "fee_currency": "USD",
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc),
    }


def _rows(newest_ts: float, count: int) -> list[dict]:
    """Rows stepping back a minute each, over two symbols and two venues."""
    return [
        _row(
            f"trade-{i}",
            newest_ts - i * 60,
            "CHIP/USD" if i % 2 == 0 else "RAVE/USD",
            "coinbase" if i % 3 else "kraken",
            "BUY" if i % 2 == 0 else "SELL",
        )
        for i in range(count)
    ]


def _loaded(
    monkeypatch: pytest.MonkeyPatch, count: int = 6
) -> tuple[HistoryTab, float]:
    """A tab holding ``count`` rows, on a clock frozen just past its own
    To bound so both sides read one instant."""
    tab = HistoryTab()
    tab.set_bot_manager(_BotManager())
    frozen = float(tab._to_dt.dateTime().toSecsSinceEpoch() + 60)

    import src.gui.history_tab as history_tab

    monkeypatch.setattr(history_tab.time, "time", lambda: frozen)
    tab._all_trades = _rows(frozen - 120, count)
    tab._last_fetched_ts = frozen - 30
    tab._populate_filter_options()
    tab._apply_filters()
    return tab, frozen


def _surface_of(tab: HistoryTab, frozen: float, **over: Any) -> dict:
    """The surface's answer for exactly the state the tab is in."""
    return hts.build_view_model(
        tab._all_trades,
        tab._current_filters(),
        page=tab._page,
        bot_manager=tab._bot_manager,
        last_fetched_ts=tab._last_fetched_ts,
        now_ts=frozen,
        **over,
    )


def _children(tab: HistoryTab, kind: type) -> list:
    return tab.findChildren(kind)


def _painted_colours(widget: Any, size: tuple[int, int] = (420, 26)) -> set:
    """Every colour the widget actually renders, sampled off the image."""
    image = qt_pixel.render_widget(widget, size=size)
    return {
        qt_pixel.pixel_at(image, QPoint(x, y))
        for y in range(image.height())
        for x in range(image.width())
    }


def test_the_surface_summary_is_the_line_the_tab_paints(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One summary line, not two."""
    del qapp
    tab, frozen = _loaded(monkeypatch)
    try:
        painted = tab._summary.text()
        assert "trades shown" in painted, f"the tab painted no summary: {painted!r}"
        assert painted == _surface_of(tab, frozen)["summary"]["text"], (
            "the summary the tab paints and the summary the surface serves "
            f"disagree: tab={painted!r}"
        )
    finally:
        tab.deleteLater()


def test_the_surface_page_label_is_the_label_the_tab_paints(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One page counter, not two."""
    del qapp
    tab, frozen = _loaded(monkeypatch, count=ROWS_PER_PAGE * 2 + 5)
    try:
        for page in (0, 1, 2):
            tab._page = page
            tab._render_page()
            painted = tab._page_label.text()
            assert painted.startswith("Page "), f"no page counter: {painted!r}"
            assert painted == _surface_of(tab, frozen)["pager"]["label"], (
                f"page {page}: the tab paints {painted!r} and the surface "
                "serves something else"
            )
    finally:
        tab.deleteLater()


def test_the_surface_says_no_matches_when_the_tab_does(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control on the label test: the empty wording agrees too."""
    del qapp
    tab, frozen = _loaded(monkeypatch)
    try:
        assert tab._page_label.text().startswith("Page "), "started with no rows"
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(frozen + 3600)))
        tab._apply_filters()
        painted = tab._page_label.text()
        assert painted == "No matches", f"filter kept rows: {painted!r}"
        assert painted == _surface_of(tab, frozen)["pager"]["label"]
    finally:
        tab.deleteLater()


def test_the_surface_button_states_are_the_tab_button_states(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prev and Next open and close on the same pages."""
    del qapp
    tab, frozen = _loaded(monkeypatch, count=ROWS_PER_PAGE * 2 + 5)
    try:
        seen = set()
        for page in (0, 1, 2):
            tab._page = page
            tab._render_page()
            served = _surface_of(tab, frozen)["buttons"]
            enabled = {entry["key"]: entry["enabled"] for entry in served}
            for key, button in (("prev", tab._prev_btn), ("next", tab._next_btn)):
                seen.add(button.isEnabled())
                assert button.isEnabled() == enabled[key], (
                    f"page {page}: the tab's {key} button is "
                    f"{button.isEnabled()} and the surface says {enabled[key]}"
                )
        assert seen == {True, False}, (
            "every page left both buttons in one state, so the comparison "
            f"never had to discriminate; saw {seen}"
        )
    finally:
        tab.deleteLater()


def test_the_surface_filter_options_are_the_combo_contents(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The three dropdowns offer what the surface offers."""
    del qapp
    tab, frozen = _loaded(monkeypatch)
    try:
        served = {
            combo["key"]: combo["options"]
            for combo in _surface_of(tab, frozen)["filters"]["combos"]
        }
        for key, combo in (
            ("exchange", tab._exch_combo),
            ("symbol", tab._sym_combo),
            ("side", tab._side_combo),
        ):
            shown = [combo.itemText(i) for i in range(combo.count())]
            assert len(shown) > 1, f"{key} offers only {shown}"
            assert shown == served[key], (
                f"{key}: the tab offers {shown} and the surface offers "
                f"{served[key]}"
            )
    finally:
        tab.deleteLater()


def test_the_surface_draws_the_rows_the_tab_retained(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The filter keeps one set of rows, and both sides page it alike."""
    del qapp
    tab, frozen = _loaded(monkeypatch)
    try:
        tab._sym_combo.setCurrentText("CHIP/USD")
        tab._apply_filters()
        kept = [r["id"] for r in tab._filtered]
        assert kept, "the filter kept nothing, so the comparison is vacuous"
        assert len(kept) < len(tab._all_trades), "the filter excluded nothing"
        served = _surface_of(tab, frozen)["page"]
        assert served["total"] == len(kept), (
            f"the tab retained {len(kept)} rows and the surface counted "
            f"{served['total']}"
        )
    finally:
        tab.deleteLater()


def test_the_surface_names_every_button_the_tab_builds(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Six buttons, with the labels and tooltips the tab gives them."""
    del qapp
    tab, frozen = _loaded(monkeypatch)
    try:
        served = _surface_of(tab, frozen)["buttons"]
        assert len(served) == 6, f"the surface names {len(served)} buttons"
        built = {
            button.text(): button.toolTip() for button in _children(tab, QPushButton)
        }
        for entry in served:
            assert entry["text"] in built, (
                f"the surface names a {entry['text']!r} button the tab does "
                f"not build; the tab builds {sorted(built)}"
            )
            assert built[entry["text"]] == entry["tooltip"], (
                f"{entry['text']!r}: the tab's tooltip is "
                f"{built[entry['text']]!r} and the surface's is "
                f"{entry['tooltip']!r}"
            )
    finally:
        tab.deleteLater()


def test_the_summary_line_is_painted_in_the_colour_the_surface_publishes(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen, not the widget's own report of itself."""
    del qapp
    tab, _ = _loaded(monkeypatch)
    try:
        painted = _painted_colours(tab._summary)
        assert hts.SUMMARY_TEXT_COLOUR.lower() in painted, (
            f"the summary line paints no {hts.SUMMARY_TEXT_COLOUR} pixel; "
            f"it painted {sorted(painted)}"
        )
    finally:
        tab.deleteLater()


def test_the_pixel_scan_can_miss_a_colour(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control on the paint test: the scan is not answering yes to all."""
    del qapp
    tab, _ = _loaded(monkeypatch)
    try:
        assert "#ff00ff" not in _painted_colours(tab._summary), (
            "the scan reports a colour the label never paints, so its "
            "sibling's green means nothing"
        )
    finally:
        tab.deleteLater()


def test_the_surface_describes_the_widgets_the_tab_actually_builds(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every kind the surface declares is on screen in that number."""
    del qapp
    tab, _ = _loaded(monkeypatch)
    try:
        counted = {
            "QComboBox": len(_children(tab, QComboBox)),
            "QDateTimeEdit": len(_children(tab, QDateTimeEdit)),
            "QPushButton": len(_children(tab, QPushButton)),
            "QProgressBar": len(_children(tab, QProgressBar)),
        }
        declared: dict[str, int] = {}
        for kind in hts.WIDGET_KINDS.values():
            declared[kind] = declared.get(kind, 0) + 1
        for kind, built in counted.items():
            assert built == declared.get(kind, 0), (
                f"the tab builds {built} {kind} and the surface declares "
                f"{declared.get(kind, 0)}"
            )
    finally:
        tab.deleteLater()


def test_the_progress_bar_hides_until_a_fetch_is_in_flight(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The busy bar's two states, both asserted."""
    del qapp
    tab, frozen = _loaded(monkeypatch)
    try:
        assert _surface_of(tab, frozen)["progress"]["visible"] is False
        assert _surface_of(tab, frozen, fetching=True)["progress"]["visible"] is True
        assert hts.buttons_enabled(0, 0, fetching=True)["refresh"] is False
        assert hts.buttons_enabled(0, 0, fetching=False)["refresh"] is True
    finally:
        tab.deleteLater()


def test_the_bridge_serves_the_history_tab_method() -> None:
    """The surface is reachable over the bridge, and answers."""
    registry = desktop_bridge.build_registry()
    assert (
        hts.METHOD in registry
    ), f"{hts.METHOD} is not registered; the renderer cannot reach it"
    answered = desktop_bridge.dispatch(hts.METHOD, {"trades": []}, registry)
    assert answered["pager"]["label"] == "No matches"
    assert [entry["key"] for entry in answered["buttons"]] == list(hts.BUTTON_NAMES)


def test_a_status_key_replaces_the_summary_line() -> None:
    """Before a fetch the tab paints a status, and so does the surface."""
    served = desktop_bridge.dispatch(
        hts.METHOD,
        {"trades": [], "status": "idle"},
        desktop_bridge.build_registry(),
    )
    assert served["summary"]["text"] == hrc.STATUS_TEXT["idle"]
    plain = desktop_bridge.dispatch(
        hts.METHOD, {"trades": []}, desktop_bridge.build_registry()
    )
    assert plain["summary"]["text"] != hrc.STATUS_TEXT["idle"], (
        "the status text shows with no status asked for, so the sibling "
        "assertion proves nothing"
    )
