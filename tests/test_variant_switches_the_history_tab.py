"""The build variant decides which History tab is built, and it is visible.

Every test here constructs the real tab through ``variant_surface`` and reads
what was built: the Qt widget kinds on one side, the live DOM on the other.
The controls the React page draws are clicked in that DOM and the tab's own
state is read back, so a control that reaches nothing fails here.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src._variant import DEFAULT_VARIANT, QT, REACT  # noqa: E402
from src.exchange import history_read_contract as hrc  # noqa: E402
from src.gui import variant_surface  # noqa: E402
from src.gui.variant_surface import HISTORY, surface_class  # noqa: E402

#: Inside the tab's own default From bound, the 2026-04-01 launch date.
BASE_TS = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
JS_TIMEOUT_MS = 20_000
SETTLE_SECONDS = 15.0

CHROME_IDS = (
    "history-summary",
    "history-apply",
    "history-reset",
    "history-refresh",
    "history-prev",
    "history-next",
    "history-export",
    "history-from",
    "history-to",
    "history-exchange",
    "history-page-label",
)

QT_CONTROL_KINDS = (
    "QGroupBox",
    "QComboBox",
    "QDateTimeEdit",
    "QPushButton",
    "QProgressBar",
)

READ_CHROME_JS = (
    "JSON.stringify((function () {"
    "  var out = {};"
    "  %s.forEach(function (id) {"
    "    var node = document.getElementById(id);"
    "    out[id] = node === null ? null : (node.value || node.textContent);"
    "  });"
    '  out["rows"] = document.querySelectorAll("#panel-rows tr").length;'
    "  return out;"
    "})());"
) % json.dumps(list(CHROME_IDS))

PICK_KRAKEN_JS = (
    'var choice = document.getElementById("history-exchange");'
    'choice.value = "kraken";'
    'choice.dispatchEvent(new Event("change", { bubbles: true }));'
)


def _click(element_id: str) -> str:
    return 'document.getElementById("%s").click();' % element_id


# ── fixtures ───────────────────────────────────────────────────────────


def _reader_of(entries: list) -> Any:
    """A fresh iterator per call, as the live-log readers give."""

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter(list(entries))

    return _read


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``live_gate_decisions`` and ``live_voting_panel_snapshots`` at
    empty readers."""
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of([]))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of([]))


@pytest.fixture()
def registry_restored():
    """Put ``variant_surface``'s loader table back after a test adds to it."""
    before = dict(variant_surface._LOADERS)
    yield
    variant_surface._LOADERS.clear()
    variant_surface._LOADERS.update(before)


# ── helpers ────────────────────────────────────────────────────────────


def _trades(count: int) -> list:
    """``count`` rows, a third of them on kraken, one minute apart."""
    out = []
    for index in range(count):
        stamp = BASE_TS - index * 60
        out.append(
            {
                "id": "t%d" % index,
                "exchange": "kraken" if index % 3 == 0 else "coinbase",
                "symbol": "CHIP/USD",
                "side": "BUY" if index % 2 else "SELL",
                "amount": 2.0,
                "price": 10.0,
                "cost": 20.0,
                "fee": 0.01,
                "fee_currency": "USD",
                "timestamp": stamp,
                "datetime": datetime.fromtimestamp(stamp, tz=timezone.utc),
            }
        )
    return out


def _widget_kinds(widget) -> dict:
    """How many of each widget class sit under ``widget``."""
    from PySide6.QtWidgets import QWidget

    kinds: dict = {}
    for child in widget.findChildren(QWidget):
        name = type(child).__name__
        kinds[name] = kinds.get(name, 0) + 1
    return kinds


def _evaluate(view, script: str) -> Any:
    """Evaluate ``script`` in ``view`` and return its value."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    box: dict = {}

    def _catch(value: Any = None) -> None:
        box.setdefault("value", value)
        loop.quit()

    view.page().runJavaScript(script, _catch)
    QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
    loop.exec()
    assert "value" in box, "the browser never answered: " + script[:60]
    return box["value"]


def _until(qapp, holds: Callable[[], bool], seconds: float = SETTLE_SECONDS) -> bool:
    """Run the event loop until ``holds`` is true or ``seconds`` pass."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if holds():
            return True
        qapp.processEvents()
    return holds()


def _react_tab(qapp, trades: Optional[list] = None):
    """A loaded ``HistoryReactTab`` holding ``trades``, its first page drawn."""
    tab = surface_class(HISTORY, REACT)()
    assert _until(qapp, lambda: tab.page_ready), "the React tab's page never loaded"
    if trades is not None:
        tab._all_trades = list(trades)
        tab._last_fetched_ts = BASE_TS
        tab._populate_filter_options()
        tab._apply_filters()
        qapp.processEvents()
    return tab


def _chrome(tab) -> dict:
    """What the page's own chrome elements say right now."""
    return json.loads(_evaluate(tab._web, READ_CHROME_JS))


def _screens_that_do_not_switch() -> list:
    """Registered screens whose two variants resolve to one class."""
    return [
        screen
        for screen in variant_surface.screens()
        if surface_class(screen, QT) is surface_class(screen, REACT)
    ]


class _OneClass:
    """A stand-in ``_one_class`` hands back on both sides."""


def _one_class() -> type:
    """Return ``_OneClass`` whichever variant asked."""
    return _OneClass


# ── the seam decides, and the check can report when it stops ───────────


def test_every_registered_screen_builds_a_different_class_per_variant() -> None:
    """The flag changes what is built, for every screen the seam holds."""
    assert _screens_that_do_not_switch() == [], (
        "these screens build one class under both variants, so the variant "
        "flag changes nothing on them"
    )


@pytest.mark.usefixtures("registry_restored")
def test_a_screen_answering_one_class_both_ways_is_reported() -> None:
    """Positive control: the walk above is not blind to a dead variant."""
    variant_surface.register("probe screen", _one_class, _one_class)
    assert _screens_that_do_not_switch() == ["probe screen"]


def test_the_seam_holds_the_history_tab_and_the_history_table() -> None:
    """Both History choices are made in one place."""
    assert set(variant_surface.screens()) == {HISTORY, variant_surface.HISTORY_TABLE}


def test_an_unset_variant_still_answers_the_default() -> None:
    """``resolve_variant``'s default is unchanged by the seam."""
    assert DEFAULT_VARIANT == REACT
    assert variant_surface.draws_react(HISTORY, DEFAULT_VARIANT) is True
    assert variant_surface.draws_react(HISTORY, QT) is False


def test_the_react_history_tab_is_a_history_tab() -> None:
    """The main window reads refresh and get_history_callback off either."""
    assert issubclass(surface_class(HISTORY, REACT), surface_class(HISTORY, QT))


class _TabHolder:
    """Carries the ``_main_tabs`` and ``_bot_manager`` a tab builder reads."""

    def __init__(self, tabs: Any) -> None:
        self._main_tabs = tabs
        self._bot_manager = None
        self._history_tab: Any = None


def test_the_main_windows_history_builder_adds_the_variants_own_tab(
    qapp, monkeypatch
) -> None:
    """``_build_history_tab`` adds whichever tab the running variant names."""
    from types import MethodType

    from PySide6.QtWidgets import QTabWidget

    from src.gui.main_tabs.history_tab import HistoryTabMixin

    built = {}
    for variant in (QT, REACT):
        monkeypatch.setenv("ACERVATOR_VARIANT", variant)
        tabs = QTabWidget()
        holder = _TabHolder(tabs)
        MethodType(HistoryTabMixin.__dict__["_build_history_tab"], holder)()
        assert [tabs.tabText(i) for i in range(tabs.count())] == ["History"]
        built[variant] = type(holder._history_tab).__name__
        tabs.deleteLater()
    assert built == {QT: "HistoryTab", REACT: "HistoryReactTab"}, built


# ── what each variant actually builds ──────────────────────────────────


def test_the_qt_variant_builds_the_history_tab_in_qt_widgets(qapp) -> None:
    """The Qt build draws the filter box, the buttons and the progress bar."""
    tab = surface_class(HISTORY, QT)()
    kinds = _widget_kinds(tab)
    assert kinds.get("QGroupBox") == 1, kinds
    assert kinds.get("QComboBox") == 3, kinds
    assert kinds.get("QDateTimeEdit") == 2, kinds
    assert kinds.get("QPushButton") == 6, kinds
    assert kinds.get("QProgressBar") == 1, kinds
    tab.deleteLater()


def test_the_react_variant_builds_no_qt_history_controls(qapp) -> None:
    """The React build draws one web view and none of those widgets."""
    tab = surface_class(HISTORY, REACT)()
    kinds = _widget_kinds(tab)
    assert kinds.get("QWebEngineView") == 1, kinds
    for kind in QT_CONTROL_KINDS:
        assert kind not in kinds, f"the React build still builds a {kind}: {kinds}"
    tab.deleteLater()


def test_the_react_variant_draws_the_whole_tab_chrome_in_the_page(qapp) -> None:
    """Summary, filters, both pager buttons and the rows come from React."""
    tab = _react_tab(qapp, _trades(250))
    drawn = _chrome(tab)
    for element_id in CHROME_IDS:
        assert drawn[element_id] is not None, f"{element_id} was never drawn: {drawn}"
    assert drawn["history-page-label"] == hrc.page_label(0, 250)
    assert drawn["history-refresh"] == "Refresh"
    assert drawn["rows"] == hrc.PAGE_SIZE, drawn
    tab.deleteLater()


def test_the_qt_variant_draws_none_of_that_chrome_in_its_page(qapp) -> None:
    """Control on the read above: the Qt build's page holds the table alone."""
    tab = surface_class(HISTORY, QT)()
    assert _until(qapp, lambda: tab._table.page_ready), "the Qt table never loaded"
    drawn = json.loads(_evaluate(tab._table._web, READ_CHROME_JS))
    assert [drawn[one] for one in CHROME_IDS] == [None] * len(CHROME_IDS), drawn
    tab.deleteLater()


# ── the controls the page draws reach the tab ──────────────────────────


def test_the_pages_next_button_turns_the_tabs_page(qapp) -> None:
    """Clicking Next in the page advances the tab and redraws the label."""
    tab = _react_tab(qapp, _trades(250))
    assert tab._page == 0
    _evaluate(tab._web, _click("history-next"))
    assert _until(qapp, lambda: tab._page == 1), "Next never reached the tab"
    assert _until(
        qapp, lambda: _chrome(tab)["history-page-label"] == hrc.page_label(1, 250)
    ), "the tab turned the page and the page never redrew"
    tab.deleteLater()


def test_the_tab_stays_on_its_page_while_nothing_is_clicked(qapp) -> None:
    """Positive control: running the loop alone does not turn the page."""
    tab = _react_tab(qapp, _trades(250))
    assert _until(qapp, lambda: tab._page != 0, 2.0) is False
    assert tab._page == 0
    tab.deleteLater()


def test_a_filter_the_page_reports_reaches_the_tab(qapp) -> None:
    """Choosing kraken in the page filters the tab's own retained rows."""
    rows = _trades(250)
    tab = _react_tab(qapp, rows)
    assert tab._current_filters().exchange == hrc.ALL
    assert len(tab._filtered) == 250
    _evaluate(tab._web, PICK_KRAKEN_JS)
    assert _until(
        qapp, lambda: tab._current_filters().exchange == "kraken"
    ), "the filter the page reported never reached the tab"
    kraken = [row for row in rows if row["exchange"] == "kraken"]
    assert len(tab._filtered) == len(kraken)
    tab.deleteLater()


def test_the_pages_reset_button_returns_the_tab_to_every_row(qapp) -> None:
    """Reset in the page clears the filter the tab is holding."""
    tab = _react_tab(qapp, _trades(250))
    _evaluate(tab._web, PICK_KRAKEN_JS)
    assert _until(qapp, lambda: tab._current_filters().exchange == "kraken")
    _evaluate(tab._web, _click("history-reset"))
    assert _until(
        qapp, lambda: tab._current_filters().exchange == hrc.ALL
    ), "Reset never reached the tab"
    assert len(tab._filtered) == 250
    tab.deleteLater()


def test_the_pages_refresh_button_reaches_the_tabs_fetch(qapp) -> None:
    """Refresh is not bridged, so the host answers it and the tab reports."""
    tab = _react_tab(qapp, _trades(4))
    assert tab._status != hrc.STATUS_TEXT["no_bot_manager"]
    _evaluate(tab._web, _click("history-refresh"))
    assert _until(
        qapp, lambda: tab._status == hrc.STATUS_TEXT["no_bot_manager"]
    ), "Refresh never reached the tab's fetch"
    assert _chrome(tab)["history-summary"] == hrc.STATUS_TEXT["no_bot_manager"]
    tab.deleteLater()


def test_the_pages_export_button_reaches_the_tabs_export(qapp, monkeypatch) -> None:
    """Export is not bridged either, so the host answers it."""
    tab = _react_tab(qapp, _trades(4))
    exported: list = []
    monkeypatch.setattr(
        type(tab), "_export_csv", lambda self: exported.append("called")
    )
    _evaluate(tab._web, _click("history-export"))
    assert _until(qapp, lambda: exported == ["called"]), "Export never reached the tab"
    tab.deleteLater()


def test_a_bridged_button_does_not_reach_the_export(qapp, monkeypatch) -> None:
    """Control on the export route: Apply is answered without it."""
    tab = _react_tab(qapp, _trades(4))
    exported: list = []
    monkeypatch.setattr(
        type(tab), "_export_csv", lambda self: exported.append("called")
    )
    _evaluate(tab._web, _click("history-apply"))
    assert _until(qapp, lambda: exported == ["called"], 2.0) is False
    assert exported == []
    tab.deleteLater()
