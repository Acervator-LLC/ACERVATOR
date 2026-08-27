"""Issue #128 R6 — the History tab keeps every control after the swap.

WHAT IS BEING PROVED
====================
``HistoryTab``'s ``QTableWidget`` is now a ``HistoryWebTable``: React
inside the Chromium PySide6 ships. Everything else in the tab is
unchanged. This module drives the twenty-one History functions named in
``docs/engineering-notes/2026-08-25_subsystem_capability_matrix.md`` (level two,
``HISTORY/*``) and asserts each one still does what it did.

DRIVEN, NOT INSPECTED. A control that exists is not a control that works.
The CSV file is read back off disk, the fetch runs, a filter narrows the
rows the BROWSER drew, and the Simulator's slot receives the list.

THE VACUOUS-PASS CONTROL
========================
A tab that renders nothing loses no feature detectably.
``test_the_fixture_is_not_vacuous`` asserts non-empty rows and non-empty
cells first, and ``test_a_severed_push_leaves_the_table_empty`` proves
that assertion can fail.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src.exchange import history_read_contract as hrc  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import QDateTime, QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

BASE_TS = 1_750_000_000.0
JS_TIMEOUT_MS = 30_000


# ── fixtures ───────────────────────────────────────────────────────────


def _reader_of(entries: list) -> Any:
    """A FRESH iterator per call, as the live-log readers give."""

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter(list(entries))

    return _read


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read EMPTY live logs unless a test says otherwise. Without this
    the suite parses the operator's gate log."""
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of([]))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of([]))


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    running = QApplication.instance()
    if isinstance(running, QApplication):
        return running
    return QApplication(sys.argv)


@pytest.fixture(scope="module")
def async_loop():
    """A real asyncio loop on its own thread, as the platform runs one."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5.0)
    loop.close()


class _Cfg:
    def __init__(self, symbol: str, ticker: str) -> None:
        self.symbol = symbol
        self.ticker = ticker
        self.exchange_id = "coinbase"


class _Bot:
    def __init__(self, bot_id: str, symbol: str, ticker: str) -> None:
        self.bot_id = bot_id
        self.config = _Cfg(symbol, ticker)


class _BotManager:
    def __init__(self, loop: Optional[Any] = None) -> None:
        self._async_loop = loop
        self._bots = {
            "a": _Bot("bot-aaaa1111", "CHIP/USD", "CHIP"),
            "b": _Bot("bot-bbbb2222", "RAVE/USD", "RAVE"),
        }


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


def _mixed_rows(count: int = 13) -> list[dict]:
    """Newest-first rows that light every branch in the render path."""
    rows: list[dict] = []
    for i in range(count):
        chip = i % 2 == 0
        rows.append(
            _row(
                f"{'chip' if chip else 'rave'}-{i}",
                symbol="CHIP/USD" if chip else "RAVE/USD",
                exchange="coinbase" if i % 3 else "kraken",
                side="BUY" if i % 2 == 0 else "SELL",
                ts=BASE_TS - i * 60,
                price=10.0 + i * 1.5,
                amount=0.5 + i,
                fee=0.0 if i == 3 else 0.01 * (i + 1),
            )
        )
    return rows


def _gate_entry(bot_id: str, ts: float, blockers: list) -> dict:
    return {
        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "category": "gate_decision",
        "bot_id": bot_id,
        "data": {
            "symbol": "CHIP/USD",
            "state": "TRACK",
            "scrum_armed": False,
            "fold_armed": False,
            "scrum_blockers": list(blockers),
            "fold_blockers": [],
            "landing_strip_side": "",
        },
    }


def _voting_entry(bot_id: str, ts: float) -> dict:
    return {
        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "category": "voting_panel_snapshot",
        "bot_id": bot_id,
        "data": {
            "side": "BUY",
            "panel": {
                "direction": "BUY",
                "net_score": 0.61,
                "timeframe": "1h",
                "bullish_count": 4,
                "bearish_count": 1,
                "neutral_count": 2,
                "consensus_confidence": 0.72,
                "signals": [
                    {
                        "indicator": "rsi",
                        "direction": 1,
                        "confidence": 0.8,
                        "weight": 1.0,
                        "timeframe": "1h",
                    }
                ],
            },
        },
    }


# ── the browser reader ─────────────────────────────────────────────────


def _code_of(path: Path) -> str:
    """The module's CODE, with docstrings and comments removed.

    A name discussed in prose is not a call. This tab's comments carry a
    changelog naming the fetcher it retired, so a raw text scan would
    report a second data source that is not there.
    """
    import io
    import tokenize

    kept: list[str] = []
    previous = tokenize.INDENT
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and previous in (
            tokenize.INDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.DEDENT,
        ):
            continue  # a docstring: the only string in statement position
        previous = tok.type
        kept.append(tok.string)
    return " ".join(kept)


def _eval_in(view: Any, script: str) -> Any:
    """Evaluate ``script`` in ``view``. A stalled browser raises.

    ``runJavaScript`` answers through a callback, so this spins a nested
    ``QEventLoop`` with a ceiling rather than returning the last answer.
    """
    loop = QEventLoop()
    box: dict = {}

    def _catch(value: Any) -> None:
        box.setdefault("v", value)
        loop.quit()

    view.page().runJavaScript(script, _catch)
    QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
    loop.exec()
    assert "v" in box, f"the browser never answered: {script[:60]}"
    return box["v"]


_DOM_JS = r"""
JSON.stringify((function () {
  var out = {headers: [], rows: [], lights: 0, error: null};
  var err = document.getElementById("panel-error");
  if (err) { out.error = err.textContent; }
  document.querySelectorAll("#panel-table thead th").forEach(function (th) {
    out.headers.push({
      key: th.getAttribute("data-col-key"),
      header: th.textContent,
      tooltip: th.getAttribute("title") || ""
    });
  });
  document.querySelectorAll("#panel-rows tr").forEach(function (tr) {
    var cells = {};
    tr.querySelectorAll("td").forEach(function (td) {
      var shown = td.cloneNode(true);
      var strip = shown.querySelector(".gate-lights");
      if (strip) { strip.remove(); }
      cells[td.getAttribute("data-col-key")] = {
        text: shown.textContent,
        color: td.getAttribute("data-cell-color") || "",
        tooltip: td.getAttribute("data-cell-tooltip") || ""
      };
    });
    out.rows.push({id: tr.getAttribute("data-trade-id"), cells: cells});
  });
  out.lights = document.querySelectorAll(
    "#panel-rows .gate-lights .light").length;
  return out;
})())
"""


def _pump(app: QApplication, ready: Callable[[], bool], timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if ready():
            return True
        time.sleep(0.005)
    app.processEvents()
    return ready()


def _tab(qapp: QApplication, loop: Optional[Any] = None):
    """A HistoryTab whose page has loaded."""
    from src.gui.history_tab import HistoryTab

    tab = HistoryTab()
    tab.set_bot_manager(_BotManager(loop))
    assert _pump(qapp, lambda: tab._table.page_ready), "the page never loaded"
    return tab


def _loaded(qapp: QApplication, trades: Optional[list] = None, loop: Any = None):
    """A HistoryTab holding ``trades``, filtered and rendered."""
    rows = _mixed_rows() if trades is None else trades
    tab = _tab(qapp, loop)
    tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 86_400)))
    tab._last_fetched_ts = BASE_TS
    tab._all_trades = list(rows)
    tab._populate_filter_options()
    tab._apply_filters()
    qapp.processEvents()
    return tab


def _dom(tab) -> dict:
    return json.loads(_eval_in(tab._table._web, _DOM_JS))


def _assert_not_vacuous(dom: dict) -> None:
    """Rows, and cells with text in them, before any claim of parity."""
    assert dom["error"] is None, dom["error"]
    assert dom["rows"], "the table drew no rows; every parity claim is vacuous"
    filled = [
        c["text"]
        for row in dom["rows"]
        for key, c in row["cells"].items()
        if key not in ("bot", "gates", "voting")
    ]
    assert any(t.strip() for t in filled), "every cell is blank"


# ═══════════════════════════════════════════════════════════════════════
# The vacuous-pass control, and the wiring cut that must go red
# ═══════════════════════════════════════════════════════════════════════


def test_the_fixture_is_not_vacuous(qapp: QApplication) -> None:
    """Thirteen rows, thirteen columns, and a colour actually set."""
    tab = _loaded(qapp)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        assert len(dom["rows"]) == 13
        assert len(dom["headers"]) == 13
        assert any(c["color"] for r in dom["rows"] for c in r["cells"].values())
    finally:
        tab.deleteLater()


def test_a_severed_push_leaves_the_table_empty(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE WIRING CONTROL. Cut the bridge; the guard must go red.

    ``state_push_script`` builds the only statement that crosses from the
    tab to the page. Sending an inert one leaves the page with no state,
    and the vacuous-pass guard every parity test runs first goes red
    naming the bridge rather than reporting an empty but healthy table.
    """
    from src.gui import react_history_panel as panel

    monkeypatch.setattr(panel, "state_push_script", lambda _payload: "void 0;")
    tab = _tab(qapp)
    try:
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 86_400)))
        tab._last_fetched_ts = BASE_TS
        tab._all_trades = _mixed_rows()
        tab._apply_filters()
        qapp.processEvents()
        dom = _dom(tab)
        assert dom["rows"] == []
        with pytest.raises(AssertionError, match="acervatorSetState"):
            _assert_not_vacuous(dom)
    finally:
        tab.deleteLater()


# ═══════════════════════════════════════════════════════════════════════
# HISTORY/trade-list
# ═══════════════════════════════════════════════════════════════════════


def test_from_the_exchange(
    qapp: QApplication, async_loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HISTORY/trade-list/from-the-exchange — the venue's own fill record.

    The real ``_kick_async_fetch`` runs; only the venue call is replaced.
    """
    import src.exchange.history_helpers as helpers

    seen: dict = {}

    async def _fake(bot_manager: Any, since_ts: float, *a: Any, **kw: Any) -> list:
        seen["bot_manager"] = bot_manager
        seen["since_ts"] = since_ts
        return _mixed_rows()

    monkeypatch.setattr(helpers, "fetch_all_history_chunked", _fake)
    tab = _tab(qapp, async_loop)
    try:
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 86_400)))
        tab.refresh()
        assert _pump(qapp, lambda: len(tab._all_trades) == 13), "no rows landed"
        assert seen["bot_manager"] is tab._bot_manager
        assert _pump(qapp, lambda: len(_dom(tab)["rows"]) == 13)
        _assert_not_vacuous(_dom(tab))
    finally:
        tab.deleteLater()


def test_the_table(qapp: QApplication) -> None:
    """HISTORY/trade-list/the-table — the thirteen-column list."""
    tab = _loaded(qapp)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        assert [h["key"] for h in dom["headers"]] == list(hrc.COLUMN_KEYS)
        assert [h["header"] for h in dom["headers"]] == [c.header for c in hrc.COLUMNS]
        for row in dom["rows"]:
            assert set(row["cells"]) == set(hrc.COLUMN_KEYS)
    finally:
        tab.deleteLater()


def test_cost_usd_column(qapp: QApplication) -> None:
    """HISTORY/trade-list/cost-usd-column — served unchanged.

    The matrix records this column as BROKEN: ``history_helpers.py:146``
    writes amount x price and the header says "Cost USD" whatever the
    quote currency is. The swap neither repairs nor worsens it, and this
    pins the value so a later repair is a deliberate change.
    """
    rows = _mixed_rows()
    tab = _loaded(qapp, rows)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        assert dom["headers"][7]["header"] == "Cost USD"
        for shown, want in zip(dom["rows"], rows):
            assert shown["cells"]["cost"]["text"] == f"${want['cost']:,.4f}"
            assert shown["cells"]["price"]["text"] == f"${want['price']:,.8f}"
    finally:
        tab.deleteLater()


def test_summary_line(qapp: QApplication) -> None:
    """HISTORY/trade-list/summary-line — counts, totals, fetch age."""
    rows = _mixed_rows()
    tab = _loaded(qapp, rows)
    try:
        _assert_not_vacuous(_dom(tab))
        text = tab._summary.text()
        buys = [r for r in rows if r["side"] == "BUY"]
        sells = [r for r in rows if r["side"] == "SELL"]
        assert f"{len(rows)} of {len(rows)} trades shown" in text
        assert f"BUYs: {len(buys)}" in text
        assert f"SELLs: {len(sells)}" in text
        assert f"${sum(r['cost'] for r in buys):,.2f}" in text
        assert "fetched" in text
    finally:
        tab.deleteLater()


def test_which_bot_made_it(qapp: QApplication) -> None:
    """HISTORY/trade-list/which-bot-made-it — the Bot column."""
    tab = _loaded(qapp)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        labels = {r["cells"]["bot"]["text"] for r in dom["rows"]}
        # "TICKER/last4 of the bot id", the label _resolve_bot_label builds.
        assert labels == {"CHIP/1111", "RAVE/2222"}, labels
        for shown, want in zip(dom["rows"], _mixed_rows()):
            ticker = want["symbol"].split("/")[0]
            assert shown["cells"]["bot"]["text"].startswith(ticker + "/")
    finally:
        tab.deleteLater()


def test_only_live_bots(qapp: QApplication) -> None:
    """HISTORY/trade-list/only-live-bots — no Simulator fill appears.

    The exclusion lives in ``history_helpers``' fetch, which walks the
    live bot manager's own (exchange, symbol) pairs. The tab must still
    take its rows from that fetcher and add no second source.
    """
    from src.gui import history_tab as hist

    source = Path(hist.__file__).read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if "import" in line and "fetch_all_history_chunked" in line
    ]
    assert len(imports) == 1, imports
    assert "history_helpers" in imports[0]
    # No second source. Scanned as CODE: the tab's comments carry a
    # changelog that names the retired fetcher in prose.
    code = _code_of(Path(hist.__file__))
    for forbidden in ("get_my_trades", "SimBot", "simulator_tab"):
        assert forbidden not in code, forbidden
    assert "fetch_all_history_chunked" in code


def test_the_second_source_scan_can_see_a_real_call() -> None:
    """The control: the same scan DOES find a venue call in real code."""
    code = _code_of(REPO / "src" / "exchange" / "history_helpers.py")
    assert "get_my_trades" in code, "the scan stripped the code, not the prose"


def test_busy_bar_and_timeout(
    qapp: QApplication, async_loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HISTORY/trade-list/busy-bar-and-timeout — spinner up, then down.

    The bar is asserted VISIBLE while the fetch is in flight, which a
    test that only looked afterwards would never see.
    """
    import src.exchange.history_helpers as helpers

    async def _slow(bot_manager: Any, since_ts: float, *a: Any, **kw: Any) -> list:
        del bot_manager, since_ts, a, kw
        await asyncio.sleep(0.8)
        return _mixed_rows()

    monkeypatch.setattr(helpers, "fetch_all_history_chunked", _slow)
    tab = _tab(qapp, async_loop)
    try:
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 86_400)))
        tab.refresh()
        assert tab._fetch_in_flight
        assert tab._progress.isVisibleTo(tab), "the busy bar never came up"
        assert not tab._refresh_btn.isEnabled(), "Refresh stayed clickable"
        assert tab._summary.text() == hrc.STATUS_TEXT["fetching"]
        assert _pump(qapp, lambda: not tab._fetch_in_flight)
        assert not tab._progress.isVisibleTo(tab), "the busy bar never went down"
        assert tab._refresh_btn.isEnabled()
    finally:
        tab.deleteLater()

    # The sixty-second give-up is pinned in the source: driving it would
    # cost a sixty-second wait, and the contract states the same number.
    source = (REPO / "src" / "gui" / "history_tab.py").read_text(encoding="utf-8")
    assert "> 60.0" in source
    assert "Fetch timeout (60s). Exchange may be rate-" in source
    assert hrc.FETCH_TIMEOUT_S == 60.0


# ═══════════════════════════════════════════════════════════════════════
# HISTORY/filters
# ═══════════════════════════════════════════════════════════════════════


def test_refresh_button(
    qapp: QApplication, async_loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HISTORY/filters/refresh-button — clicking it pulls fresh history."""
    import src.exchange.history_helpers as helpers

    calls: list = []

    async def _fake(bot_manager: Any, since_ts: float, *a: Any, **kw: Any) -> list:
        del bot_manager, a, kw
        calls.append(since_ts)
        return _mixed_rows()

    monkeypatch.setattr(helpers, "fetch_all_history_chunked", _fake)
    tab = _tab(qapp, async_loop)
    try:
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 86_400)))
        tab._refresh_btn.click()
        assert _pump(qapp, lambda: len(tab._all_trades) == 13)
        assert len(calls) == 1
        assert _pump(qapp, lambda: len(_dom(tab)["rows"]) == 13)
    finally:
        tab.deleteLater()


def test_refreshes_on_tab_open() -> None:
    """HISTORY/filters/refreshes-on-tab-open — the activation hook.

    ``_on_main_tab_changed`` is the wiring; it is read here rather than
    driven, because driving it needs a whole MainWindow.
    """
    wiring = (REPO / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
    handler = wiring[wiring.index("def _on_main_tab_changed") :]
    handler = handler[: handler.index("def _drain_signals")]
    assert 'if tab_name == "History":' in handler
    assert 'hist = getattr(self, "_history_tab", None)' in handler
    assert "hist.refresh()" in handler
    assert 'getattr(hist, "_last_fetched_ts", 0.0)' in handler
    from src.gui.history_tab import HistoryTab

    assert callable(HistoryTab.refresh)


def test_date_range(qapp: QApplication) -> None:
    """HISTORY/filters/date-range — From and To narrow the drawn rows."""
    rows = _mixed_rows()
    tab = _loaded(qapp, rows)
    try:
        assert len(_dom(tab)["rows"]) == 13
        # Keep the six newest: the fixture steps back one minute per row.
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 5 * 60)))
        tab._apply_filters()
        qapp.processEvents()
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        assert len(dom["rows"]) == 6, [r["id"] for r in dom["rows"]]
        # And the To bound narrows from the other end.
        tab._to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 3 * 60)))
        tab._apply_filters()
        qapp.processEvents()
        assert len(_dom(tab)["rows"]) == 3
    finally:
        tab.deleteLater()


def test_the_default_from_date_is_the_launch_date(qapp: QApplication) -> None:
    """HISTORY/filters/date-range — the tab opens on 2026-04-01."""
    tab = _tab(qapp)
    try:
        shown = tab._from_dt.dateTime().toString("yyyy-MM-dd HH:mm")
        assert shown == "2026-04-01 00:00"
        assert hrc.DEFAULT_FROM_LOCAL == (2026, 4, 1, 0, 0, 0)
    finally:
        tab.deleteLater()


def test_exchange_symbol_and_side(qapp: QApplication) -> None:
    """HISTORY/filters/exchange-symbol-and-side — three combos, driven."""
    rows = _mixed_rows()
    tab = _loaded(qapp, rows)
    try:
        options = hrc.filter_options(rows)
        for key, combo in (
            ("exchange", tab._exch_combo),
            ("symbol", tab._sym_combo),
        ):
            shown = [combo.itemText(i) for i in range(combo.count())]
            assert shown == options[key], key

        tab._sym_combo.setCurrentText("RAVE/USD")
        tab._apply_filters()
        qapp.processEvents()
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        want = [r for r in rows if r["symbol"] == "RAVE/USD"]
        assert 0 < len(want) < len(rows)
        assert len(dom["rows"]) == len(want)
        assert {r["cells"]["symbol"]["text"] for r in dom["rows"]} == {"RAVE/USD"}

        tab._sym_combo.setCurrentIndex(0)
        tab._side_combo.setCurrentText("BUY")
        tab._apply_filters()
        qapp.processEvents()
        assert {r["cells"]["side"]["text"] for r in _dom(tab)["rows"]} == {"BUY"}

        tab._side_combo.setCurrentIndex(0)
        tab._exch_combo.setCurrentText("kraken")
        tab._apply_filters()
        qapp.processEvents()
        assert {r["cells"]["exchange"]["text"] for r in _dom(tab)["rows"]} == {"kraken"}
    finally:
        tab.deleteLater()


def test_apply_button(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """HISTORY/filters/apply-button — narrows, and fetches when empty.

    The second half is the operator's 2026-05-31 report: Apply with no
    prior fetch produced "0 of 0 trades" forever.
    """
    rows = _mixed_rows()
    tab = _loaded(qapp, rows)
    try:
        tab._side_combo.setCurrentText("SELL")
        tab._apply_btn.click()
        qapp.processEvents()
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        assert len(dom["rows"]) == len([r for r in rows if r["side"] == "SELL"])
    finally:
        tab.deleteLater()

    fresh = _tab(qapp)
    try:
        kicked: list = []
        monkeypatch.setattr(
            type(fresh), "_kick_async_fetch", lambda _self: kicked.append(True)
        )
        fresh._apply_btn.click()
        assert kicked == [True], "Apply with no prior fetch did not fetch"
    finally:
        fresh.deleteLater()


def test_reset_button(qapp: QApplication) -> None:
    """HISTORY/filters/reset-button — every filter back, rows back."""
    rows = _mixed_rows()
    tab = _loaded(qapp, rows)
    try:
        tab._side_combo.setCurrentText("SELL")
        tab._sym_combo.setCurrentText("RAVE/USD")
        tab._apply_filters()
        qapp.processEvents()
        assert len(_dom(tab)["rows"]) < len(rows)

        tab._reset_btn.click()
        qapp.processEvents()
        assert tab._side_combo.currentIndex() == 0
        assert tab._sym_combo.currentIndex() == 0
        assert tab._exch_combo.currentIndex() == 0
        assert tab._from_dt.dateTime().toString("yyyy-MM-dd HH:mm") == (
            "2026-04-01 00:00"
        )
        # The launch-date default is after this fixture, so Reset empties
        # the view. That is the reset working, not the table failing.
        assert _dom(tab)["rows"] == []
        assert tab._page_label.text() == "No matches"
    finally:
        tab.deleteLater()


# ═══════════════════════════════════════════════════════════════════════
# HISTORY/trade-explanations
# ═══════════════════════════════════════════════════════════════════════


def test_grade_column(qapp: QApplication) -> None:
    """HISTORY/trade-explanations/grade-column — the A-to-F letter."""
    rows = [
        _row(f"g-{i}", ts=BASE_TS - i * 60, price=100.0 - i * 2.0) for i in range(12)
    ]
    tab = _loaded(qapp, rows)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        letters = [r["cells"]["grade"]["text"] for r in dom["rows"]]
        assert any(t and t != "—" for t in letters), letters
        want = hrc.build_page(rows, 0, _BotManager())
        assert letters == [r.cell("grade").text for r in want.rows]
        coloured = [r["cells"]["grade"]["color"] for r in dom["rows"]]
        assert any(coloured), "no grade cell carried a colour"
    finally:
        tab.deleteLater()


def test_gates_column(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """HISTORY/trade-explanations/gates-column — text plus nineteen lights."""
    import src.trading.live_log_reader as llr
    from src.trading.gate_vocabulary import gate_light_row

    rows = _mixed_rows()
    manager = _BotManager()
    entries = [
        _gate_entry(
            hrc.resolve_bot_id_for_row(manager, r), r["timestamp"], ["delta<=0"]
        )
        for r in rows
    ]
    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of(entries))

    tab = _loaded(qapp, rows)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        texts = {r["cells"]["gates"]["text"] for r in dom["rows"]}
        assert texts == {"S⊘ delta<=0"}, texts
        assert dom["lights"] == len(rows) * 19, dom["lights"]
        assert len(gate_light_row(False, False, ["delta<=0"], [], "")) == 19
        assert all(r["cells"]["gates"]["tooltip"] for r in dom["rows"])
    finally:
        tab.deleteLater()


def test_voting_column(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """HISTORY/trade-explanations/voting-column — the panel at trade time."""
    import src.trading.live_log_reader as llr

    rows = _mixed_rows()
    manager = _BotManager()
    entries = [
        _voting_entry(hrc.resolve_bot_id_for_row(manager, r), r["timestamp"])
        for r in rows
        if r["side"] == "BUY"
    ]
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of(entries))

    tab = _loaded(qapp, rows)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        texts = [r["cells"]["voting"]["text"] for r in dom["rows"]]
        assert "BUY +0.61" in texts, texts
        joined = [r for r in dom["rows"] if r["cells"]["voting"]["text"] != "—"]
        assert joined, "no voting record joined"
        assert all(r["cells"]["voting"]["color"] == "#00ff88" for r in joined)
    finally:
        tab.deleteLater()


def test_hover_text(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """HISTORY/trade-explanations/hover-text — and it RENDERS as markup.

    Qt rendered a tooltip's HTML. A ``title`` attribute would show the
    tags, so the page draws its own tooltip and this reads it back.
    """
    import src.trading.live_log_reader as llr

    rows = _mixed_rows()
    manager = _BotManager()
    monkeypatch.setattr(
        llr,
        "live_voting_panel_snapshots",
        _reader_of(
            [
                _voting_entry(hrc.resolve_bot_id_for_row(manager, r), r["timestamp"])
                for r in rows
            ]
        ),
    )
    tab = _loaded(qapp, rows)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        first = dom["rows"][0]["cells"]
        assert first["grade"]["tooltip"], "the Grade cell carries no hover text"
        assert first["gates"]["tooltip"]
        assert "<span" in first["voting"]["tooltip"], "the fixture has no markup"

        shown = json.loads(
            _eval_in(
                tab._table._web,
                "JSON.stringify((function () {"
                "var td = document.querySelector("
                '"#panel-rows tr td[data-col-key=voting]");'
                "var n = window.acervatorRenderTooltip("
                'td.getAttribute("data-cell-tooltip"));'
                "return {mode: n.getAttribute('data-tooltip-mode'),"
                " text: n.textContent, tags: n.querySelectorAll('*').length};"
                "})())",
            )
        )
        assert shown["mode"] == "rich"
        assert shown["tags"] >= 3
        assert "<span" not in shown["text"], "the markup reached the screen raw"
        assert "bull" in shown["text"]
    finally:
        tab.deleteLater()


# ═══════════════════════════════════════════════════════════════════════
# HISTORY/paging-and-export
# ═══════════════════════════════════════════════════════════════════════


def test_paging(qapp: QApplication) -> None:
    """HISTORY/paging-and-export/paging — Prev, Next, the page counter."""
    rows = [_row(f"p-{i:04d}", ts=BASE_TS - i * 60) for i in range(hrc.PAGE_SIZE + 7)]
    tab = _loaded(qapp, rows)
    try:
        dom = _dom(tab)
        _assert_not_vacuous(dom)
        assert len(dom["rows"]) == hrc.PAGE_SIZE
        assert tab._page_label.text() == f"Page 1 / 2 ({len(rows)} trades)"
        assert not tab._prev_btn.isEnabled()
        assert tab._next_btn.isEnabled()

        first_ids = [r["id"] for r in dom["rows"]]
        tab._next_btn.click()
        qapp.processEvents()
        second = _dom(tab)
        assert len(second["rows"]) == 7
        assert set(first_ids).isdisjoint(r["id"] for r in second["rows"])
        assert tab._page_label.text() == f"Page 2 / 2 ({len(rows)} trades)"
        assert tab._prev_btn.isEnabled()
        assert not tab._next_btn.isEnabled()

        tab._prev_btn.click()
        qapp.processEvents()
        assert [r["id"] for r in _dom(tab)["rows"]] == first_ids
    finally:
        tab.deleteLater()


def test_export_csv(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """HISTORY/paging-and-export/export-csv — the file, read back off disk.

    Every FILTERED row, not just the page on screen, and the eleven
    columns the tab has always written.
    """
    from src.gui import history_tab as hist

    rows = [_row(f"e-{i:04d}", ts=BASE_TS - i * 60) for i in range(hrc.PAGE_SIZE + 5)]
    tab = _loaded(qapp, rows)
    target = tmp_path / "history.csv"
    try:

        class _Dialog:
            @staticmethod
            def getSaveFileName(*a: Any, **kw: Any) -> tuple:
                del a, kw
                return str(target), "CSV files (*.csv)"

        class _Box:
            @staticmethod
            def information(*a: Any, **kw: Any) -> None:
                return None

            @staticmethod
            def warning(*a: Any, **kw: Any) -> None:
                return None

        monkeypatch.setattr(hist, "QFileDialog", _Dialog)
        monkeypatch.setattr(hist, "QMessageBox", _Box)
        assert len(_dom(tab)["rows"]) == hrc.PAGE_SIZE, "only one page is drawn"
        tab._export_btn.click()

        with open(target, "r", newline="", encoding="utf-8") as handle:
            written = list(csv.reader(handle))
        assert written[0] == [
            "timestamp_utc",
            "exchange",
            "symbol",
            "bot",
            "side",
            "amount",
            "price",
            "cost_usd",
            "fee",
            "fee_currency",
            "trade_id",
        ]
        assert len(written) - 1 == len(rows), "the file holds one page, not the set"
        assert written[1:] == hrc.csv_rows(rows, tab._bot_manager)
        assert [line[-1] for line in written[1:]] == [r["id"] for r in rows]
    finally:
        tab.deleteLater()


# ═══════════════════════════════════════════════════════════════════════
# HISTORY/feeds-the-simulator and HISTORY/emitter-network
# ═══════════════════════════════════════════════════════════════════════


def test_hands_over_ytd(
    qapp: QApplication, async_loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HISTORY/feeds-the-simulator/hands-over-ytd — the Simulator's slot.

    Connected to the same signal ``main_window`` connects, and driven by
    the same fetch, so this is the wire the Simulator front-load rides.
    """
    import src.exchange.history_helpers as helpers
    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    assert hasattr(FleetReplayPanel, "on_history_refreshed")
    wiring = (REPO / "src" / "gui" / "main_tabs" / "history_tab.py").read_text(
        encoding="utf-8"
    )
    assert "self._history_tab.history_refreshed.connect(" in wiring
    assert "fleet_panel.on_history_refreshed" in wiring

    rows = _mixed_rows()

    async def _fake(bot_manager: Any, since_ts: float, *a: Any, **kw: Any) -> list:
        del bot_manager, since_ts, a, kw
        return rows

    monkeypatch.setattr(helpers, "fetch_all_history_chunked", _fake)
    tab = _tab(qapp, async_loop)
    try:
        received: list = []
        tab.history_refreshed.connect(received.append)
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(BASE_TS - 86_400)))
        tab.refresh()
        assert _pump(qapp, lambda: bool(received)), "the Simulator feed never fired"
        assert len(received) == 1
        assert [r["id"] for r in received[0]] == [r["id"] for r in rows]
        # The list handed over is a copy: the Simulator cannot edit the
        # tab's rows out from under the table.
        assert received[0] is not tab._all_trades
    finally:
        tab.deleteLater()


def test_history_pins(qapp: QApplication) -> None:
    """HISTORY/emitter-network/history-pins — the seven emitters remain."""
    tab_source = (REPO / "src" / "gui" / "history_tab.py").read_text(encoding="utf-8")
    conn_source = (REPO / "src" / "exchange" / "ccxt_connector.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "history.05.002.postcondition.trades_stored",
        "history.05.003.postcondition.filter_options_built",
        "history.05.004.postcondition.filters_applied",
        "history.05.005.postcondition.page_rendered",
        "history.05.006.postcondition.joiner_indexes_built",
        "history.05.007.postcondition.csv_exported",
    ):
        assert token in tab_source, token
    assert "history.05.001" in conn_source
    del qapp
