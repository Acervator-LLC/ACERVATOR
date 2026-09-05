"""``history_read_contract`` serves exactly what the History tab renders.

Both sides run on the same trade rows, filters and page index, and
``test_the_contract_agrees_with_the_tab_cell_for_cell`` compares the thirteen
column texts, the foregrounds, the tooltips, the Simulator gate-light cell and
the two labels. ``test_the_agreement_fixture_is_not_vacuous`` runs first and
refuses a fixture whose columns are empty or single-valued. Filters, dropdowns,
the local-midnight default date, paging, the CSV export and ``json.dumps``
round-tripping are each pinned, and the contract is proved to write nothing.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange import history_read_contract as hrc  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope: the
    # pure-contract tests below have to run on a box without Qt.
    from PySide6.QtWidgets import QApplication

    from src.gui.history_tab import HistoryTab


# The instant every fixture row hangs off. Fixed, so a grade, a join
# bucket and a page label cannot move with the wall clock.
BASE_TS = 1_750_000_000.0


def _reader_of(entries: list) -> Any:
    """Stand in for a live-log reader: a FRESH iterator on every call.

    The tab and the contract each call the reader once. One shared
    iterator would leave the second caller an empty log and make the two
    sides disagree for a reason that is not the contract's.
    """

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter(list(entries))

    return _read


def _returns(value: Any) -> Any:
    """Stand in for a Qt dialog: accepts anything, answers ``value``."""

    def _call(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return value

    return _call


# ── fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """The QApplication the Qt comparisons run against.

    ``importorskip`` is inside the fixture, not at module scope: the
    contract-only tests are pure Python and must still run without Qt. A
    skipped test is not evidence.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test reads EMPTY live logs unless it says otherwise.

    Both the tab's inline joiner and ``history_helpers`` import the two
    readers from ``src.trading.live_log_reader`` at CALL time, so one
    patch on the module covers both sides of the comparison. Without it
    the suite would parse the operator's 262 MB live gate log.
    """
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of([]))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of([]))


# ── the bot manager both sides read ────────────────────────────────────


class _Cfg:
    def __init__(self, symbol: str, target: str, exchange_id: str = "coinbase"):
        self.symbol = symbol
        self.target_asset = target
        self.exchange_id = exchange_id


class _Bot:
    def __init__(self, bot_id: str, symbol: str, target: str):
        self.bot_id = bot_id
        self.config = _Cfg(symbol, target)


class _BotManager:
    """The two attributes both read paths take off the manager."""

    def __init__(self, bots: Optional[dict] = None):
        self._async_loop = None
        self._bots = bots or {}


def _bot_manager() -> _BotManager:
    return _BotManager(
        {
            "a": _Bot("bot-aaaa1111", "CHIP/USD", "CHIP"),
            "b": _Bot("bot-bbbb2222", "RAVE/USD", "RAVE"),
        }
    )


# ── the trade rows ─────────────────────────────────────────────────────


def _row(
    tid: str,
    symbol: str = "CHIP/USD",
    exchange: str = "coinbase",
    side: str = "BUY",
    ts: float = BASE_TS,
    price: float = 10.0,
    amount: float = 2.0,
    fee: float = 0.01,
    fee_currency: str = "USD",
) -> dict:
    """One normalized row, the exact shape ``normalize_trade`` returns."""
    return {
        "id": tid,
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": price,
        "cost": amount * price,
        "fee": fee,
        "fee_currency": fee_currency,
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc) if ts > 0 else None,
    }


def _mixed_rows() -> list[dict]:
    """Newest-first rows that light up every branch in the render path.

    Deliberately NOT uniform. A fixture of identical rows makes an
    agreement test pass on a contract that ignores its input.
    """
    rows: list[dict] = []
    for i in range(8):
        rows.append(
            _row(
                f"chip-{i}",
                symbol="CHIP/USD",
                side="BUY" if i % 2 == 0 else "SELL",
                ts=BASE_TS - i * 60,
                price=10.0 + i * 1.5,
                amount=0.5 + i,
            )
        )
    for i in range(5):
        rows.append(
            _row(
                f"rave-{i}",
                symbol="RAVE/USD",
                side="SELL" if i % 2 == 0 else "BUY",
                ts=BASE_TS - 600 - i * 60,
                price=250.0 - i * 7.25,
                amount=0.001 * (i + 1),
                fee=0.0 if i == 0 else 0.5,
                fee_currency="" if i == 0 else "EUR",
            )
        )
    rows.append(_row("kraken-0", exchange="kraken", ts=BASE_TS - 1200))
    rows.append(_row("orphan-0", symbol="ZZZ/USD", ts=BASE_TS - 1260))
    rows.append(_row("x" * 40, symbol="CHIP/USD", ts=BASE_TS - 1320, side="SELL"))
    rows.append(_row("sideless", symbol="CHIP/USD", ts=BASE_TS - 1380, side=""))
    return rows


def _uniform_rows(count: int) -> list[dict]:
    """``count`` newest-first CHIP rows, one minute apart."""
    return [
        _row(f"p-{i:04d}", ts=BASE_TS - i * 60, price=10.0 + (i % 17))
        for i in range(count)
    ]


# ── gate + voting entries, built to the reader's own schema ────────────


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _gate_entry(
    bot_id: str,
    ts: float,
    *,
    scrum_armed: bool = False,
    fold_armed: bool = False,
    scrum_blockers: Optional[list] = None,
    fold_blockers: Optional[list] = None,
) -> dict:
    """One gate.log entry carrying every field the validator requires."""
    return {
        "timestamp": _iso(ts),
        "category": "gate_decision",
        "bot_id": bot_id,
        "data": {
            "symbol": "CHIP/USD",
            "state": "TRACK",
            "scrum_armed": scrum_armed,
            "fold_armed": fold_armed,
            "scrum_blockers": list(scrum_blockers or []),
            "fold_blockers": list(fold_blockers or []),
            "landing_strip_side": "upper" if scrum_armed else "",
        },
    }


def _voting_entry(bot_id: str, ts: float, direction: str, net: float) -> dict:
    """One voting.log entry carrying a VotingSummary-shaped panel."""
    return {
        "timestamp": _iso(ts),
        "category": "voting_panel_snapshot",
        "bot_id": bot_id,
        "data": {
            "side": direction,
            "panel": {
                "direction": direction,
                "net_score": net,
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
                    },
                    {
                        "indicator": "macd",
                        "direction": -1,
                        "confidence": 0.4,
                        "weight": 0.5,
                        "timeframe": "4h",
                    },
                ],
            },
        },
    }


# ── reading each side ──────────────────────────────────────────────────


_JS_TIMEOUT_MS = 30_000

# Returns each cell's text with the gate-light strip removed, plus the lights drawn.
_DOM_DUMP_JS = r"""
JSON.stringify((function () {
  var out = {rows: [], lights: [], error: null};
  var err = document.getElementById("panel-error");
  if (err) { out.error = err.textContent; }
  document.querySelectorAll("#panel-rows tr").forEach(function (tr) {
    var cells = [];
    tr.querySelectorAll("td").forEach(function (td) {
      var shown = td.cloneNode(true);
      var strip = shown.querySelector(".gate-lights");
      if (strip) { strip.remove(); }
      cells.push({
        key: td.getAttribute("data-col-key"),
        text: shown.textContent,
        color: td.getAttribute("data-cell-color") || null,
        tooltip: td.getAttribute("data-cell-tooltip") || null
      });
    });
    out.rows.push(cells);
    var lit = tr.querySelectorAll(".gate-lights .light");
    if (lit.length === 0) {
      out.lights.push(null);
    } else {
      out.lights.push(Array.prototype.map.call(lit, function (el) {
        return {
          bank: el.getAttribute("data-light-bank"),
          label: el.getAttribute("data-light-label"),
          state: el.getAttribute("data-light-state"),
          color: el.getAttribute("data-light-color")
        };
      }));
    }
  });
  return out;
})())
"""


def _eval_in(view: Any, script: str) -> Any:
    """Evaluate ``script`` in ``view`` and return its value.

    ``runJavaScript`` answers through a callback, so this spins a nested
    ``QEventLoop`` with a ceiling. A read that times out raises rather
    than returning the previous answer, so a stalled browser cannot be
    mistaken for agreement.
    """
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    box: dict = {}

    def _catch(value: Any) -> None:
        box.setdefault("v", value)
        loop.quit()

    view.page().runJavaScript(script, _catch)
    QTimer.singleShot(_JS_TIMEOUT_MS, loop.quit)
    loop.exec()
    assert "v" in box, f"the browser never answered: {script[:80]}"
    return box["v"]


def _tab(qapp: Any, bot_manager: Any) -> HistoryTab:
    """A HistoryTab whose page has finished loading."""
    from src.gui.history_tab import HistoryTab as _HistoryTab

    tab = _HistoryTab()
    tab.set_bot_manager(bot_manager)
    deadline = time.time() + 30.0
    while not tab._table.page_ready and time.time() < deadline:
        qapp.processEvents()
    assert tab._table.page_ready, "the tab's own document never loaded"
    return tab


def _tab_render(tab: HistoryTab, rows: list[dict], page: int = 0) -> dict:
    """Drive the real ``_render_page`` and read the BROWSER back out.

    The tab now renders through the contract, so comparing its payload
    against the contract would be the instrument agreeing with itself.
    What is read here is the DOM the page drew, which is the far side of
    a JSON round trip through the one-way bridge.
    """
    tab._all_trades = list(rows)
    tab._filtered = list(rows)
    tab._page = page
    tab._render_page()

    dom = json.loads(_eval_in(tab._table._web, _DOM_DUMP_JS))
    assert dom["error"] is None, dom["error"]
    return {
        "rows": dom["rows"],
        "lights": dom["lights"],
        "page_label": tab._page_label.text(),
        "prev_enabled": tab._prev_btn.isEnabled(),
        "next_enabled": tab._next_btn.isEnabled(),
        "page": tab._page,
    }


def _contract_render(rows: list[dict], page: int, bot_manager: Any) -> dict:
    """The same rendering, taken off the contract."""
    built = hrc.build_page(rows, page, bot_manager)
    out_rows = [
        [
            {
                "key": c.key,
                "text": c.text,
                "color": c.color or None,
                "tooltip": c.tooltip or None,
            }
            for c in row.cells
        ]
        for row in built.rows
    ]
    lights = [
        None if row.gate_lights is None else list(row.gate_lights["lights"])
        for row in built.rows
    ]
    return {
        "rows": out_rows,
        "lights": lights,
        "page_label": built.page_label,
        "prev_enabled": built.prev_enabled,
        "next_enabled": built.next_enabled,
        "page": built.page,
    }


def _assert_same(tab_side: dict, contract_side: dict) -> None:
    """Cell for cell, naming the row, the column and both values."""
    assert len(contract_side["rows"]) == len(tab_side["rows"]), (
        f"row count: tab {len(tab_side['rows'])}, "
        f"contract {len(contract_side['rows'])}"
    )
    for row_i, (tab_row, con_row) in enumerate(
        zip(tab_side["rows"], contract_side["rows"])
    ):
        assert len(tab_row) == len(con_row) == len(hrc.COLUMNS)
        for col, (tab_cell, con_cell) in enumerate(zip(tab_row, con_row)):
            key = hrc.COLUMNS[col].key
            assert tab_cell["key"] == key == con_cell["key"]
            assert con_cell["text"] == tab_cell["text"], (
                f"row {row_i} column {col} ({key}) text: "
                f"tab {tab_cell['text']!r}, contract {con_cell['text']!r}"
            )
            assert con_cell["color"] == tab_cell["color"], (
                f"row {row_i} column {col} ({key}) color: "
                f"tab {tab_cell['color']!r}, contract {con_cell['color']!r}"
            )
            assert con_cell["tooltip"] == tab_cell["tooltip"], (
                f"row {row_i} column {col} ({key}) tooltip differs: "
                f"tab {str(tab_cell['tooltip'])[:120]!r}, "
                f"contract {str(con_cell['tooltip'])[:120]!r}"
            )
    assert contract_side["lights"] == tab_side["lights"]
    assert contract_side["page_label"] == tab_side["page_label"]
    assert contract_side["prev_enabled"] == tab_side["prev_enabled"]
    assert contract_side["next_enabled"] == tab_side["next_enabled"]
    assert contract_side["page"] == tab_side["page"]


# ── the vacuous-pass control, run before the agreement ─────────────────


def test_the_agreement_fixture_is_not_vacuous(qapp) -> None:
    """Both sides must render something before "they match" means anything.

    A contract returning nothing agrees with an empty tab. A contract
    returning thirteen empty strings agrees with a blank table. This
    refuses both, on the same fixture the agreement test uses, and it
    refuses a fixture that exercises only one branch per column.
    """
    rows = _mixed_rows()
    assert len(rows) == 17

    manager = _bot_manager()
    tab_side = _tab_render(_tab(qapp, manager), rows)
    con_side = _contract_render(rows, 0, manager)

    assert len(tab_side["rows"]) == 17
    assert len(con_side["rows"]) == 17

    for col in range(13):
        key = hrc.COLUMNS[col].key
        tab_texts = [r[col]["text"] for r in tab_side["rows"]]
        con_texts = [r[col]["text"] for r in con_side["rows"]]
        assert any(t for t in tab_texts), f"tab column {col} ({key}) is entirely empty"
        assert any(
            t for t in con_texts
        ), f"contract column {col} ({key}) is entirely empty"

    # The columns whose agreement is worth proving must vary. One value
    # in a column proves the column, not the rule that fills it.
    for col, minimum in ((4, 3), (8, 3), (10, 2)):
        distinct = {r[col]["text"] for r in tab_side["rows"]}
        assert len(distinct) >= minimum, (
            f"column {col} ({hrc.COLUMNS[col].key}) shows only "
            f"{sorted(distinct)}; the fixture exercises one branch"
        )

    # And a colour must actually be set somewhere, or the colour half of
    # the comparison is comparing None against None on every cell.
    assert any(cell["color"] for row in tab_side["rows"] for cell in row)
    assert any(cell["color"] for row in con_side["rows"] for cell in row)


# ── the agreement ──────────────────────────────────────────────────────


def test_the_contract_agrees_with_the_tab_cell_for_cell(qapp) -> None:
    """17 rows, 13 columns, text and colour and tooltip, plus the footer."""
    rows = _mixed_rows()
    manager = _bot_manager()
    tab_side = _tab_render(_tab(qapp, manager), rows)
    con_side = _contract_render(rows, 0, manager)
    assert len(tab_side["rows"]) == 17
    _assert_same(tab_side, con_side)


def test_the_contract_agrees_when_the_gate_and_voting_logs_have_entries(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The join, driven with real entries rather than an empty reader.

    Without this the Gates and Voting columns agree only on "no record",
    which is the one value both sides reach without reading anything.
    """
    import src.trading.live_log_reader as llr

    rows = _mixed_rows()
    gate_entries = [
        _gate_entry("bot-aaaa1111", BASE_TS, scrum_armed=True),
        _gate_entry(
            "bot-aaaa1111",
            BASE_TS - 60,
            fold_blockers=["delta<=0", "TA-not-bearish"],
        ),
        _gate_entry(
            "bot-aaaa1111",
            BASE_TS - 120,
            scrum_armed=True,
            fold_armed=True,
        ),
        _gate_entry("bot-bbbb2222", BASE_TS - 600, scrum_blockers=["no-tranches"]),
    ]
    voting_entries = [
        _voting_entry("bot-aaaa1111", BASE_TS, "BUY", 0.61),
        _voting_entry("bot-aaaa1111", BASE_TS - 60, "SELL", -0.42),
        _voting_entry("bot-bbbb2222", BASE_TS - 600, "", 0.0),
    ]
    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of(gate_entries))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of(voting_entries))

    manager = _bot_manager()
    tab_side = _tab_render(_tab(qapp, manager), rows)
    con_side = _contract_render(rows, 0, manager)

    # The control for this test: the join must have landed on something.
    gates_texts = [r[11]["text"] for r in tab_side["rows"]]
    assert any(t != "no record" for t in gates_texts), gates_texts
    voting_texts = [r[12]["text"] for r in tab_side["rows"]]
    assert any(t != "—" for t in voting_texts), voting_texts
    lit = [w for w in tab_side["lights"] if w is not None]
    assert lit, "no gate record joined; the light comparison would be vacuous"
    assert all(len(w) == 19 for w in lit), [len(w) for w in lit]
    states = {light["state"] for row in lit for light in row}
    assert len(states) >= 3, f"the fixture lights one state only: {states}"

    _assert_same(tab_side, con_side)


# ── filters ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filters",
    [
        hrc.HistoryFilters(),
        hrc.HistoryFilters(exchange="coinbase"),
        hrc.HistoryFilters(symbol="RAVE/USD"),
        hrc.HistoryFilters(side="SELL"),
        hrc.HistoryFilters(from_ts=int(BASE_TS - 600), to_ts=int(BASE_TS - 120)),
        hrc.HistoryFilters(
            from_ts=int(BASE_TS - 1400),
            to_ts=int(BASE_TS),
            exchange="coinbase",
            symbol="CHIP/USD",
            side="BUY",
        ),
    ],
)
def test_the_filters_retain_the_rows_the_tab_retains(
    qapp,
    filters: hrc.HistoryFilters,
) -> None:
    """Drive the tab's real ``_apply_filters`` through its real widgets."""
    from PySide6.QtCore import QDateTime

    rows = _mixed_rows()
    manager = _bot_manager()
    tab = _tab(qapp, manager)
    tab._all_trades = list(rows)
    tab._last_fetched_ts = time.time()
    tab._populate_filter_options()
    if filters.from_ts:
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(filters.from_ts))
    else:
        tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(0))
    if filters.to_ts:
        tab._to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(filters.to_ts))
    else:
        tab._to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(0))
    tab._exch_combo.setCurrentText(filters.exchange)
    tab._sym_combo.setCurrentText(filters.symbol)
    tab._side_combo.setCurrentText(filters.side)
    tab._apply_filters()

    # Read the bounds back off the widgets, not off the integers typed in above.
    effective = hrc.HistoryFilters(
        from_ts=tab._from_dt.dateTime().toSecsSinceEpoch(),
        to_ts=tab._to_dt.dateTime().toSecsSinceEpoch(),
        exchange=tab._exch_combo.currentText(),
        symbol=tab._sym_combo.currentText(),
        side=tab._side_combo.currentText(),
    )
    # `setCurrentText` silently no-ops on a non-editable combo missing the value.
    assert effective.exchange == filters.exchange
    assert effective.symbol == filters.symbol
    assert effective.side == filters.side

    kept = hrc.apply_filters(rows, effective)
    assert [r["id"] for r in kept] == [r["id"] for r in tab._filtered]
    assert kept, "every filter row in this table must retain something"
    if filters != hrc.HistoryFilters():
        assert len(kept) < len(rows), "this filter narrowed nothing"


def test_the_filter_options_match_the_two_dropdowns(qapp) -> None:
    """Entry for entry, in order, sentinel included."""
    rows = _mixed_rows()
    tab = _tab(qapp, _bot_manager())
    tab._all_trades = list(rows)
    tab._populate_filter_options()

    options = hrc.filter_options(rows)
    tab_exchanges = [
        tab._exch_combo.itemText(i) for i in range(tab._exch_combo.count())
    ]
    tab_symbols = [tab._sym_combo.itemText(i) for i in range(tab._sym_combo.count())]
    tab_sides = [tab._side_combo.itemText(i) for i in range(tab._side_combo.count())]

    assert len(tab_exchanges) > 1 and len(tab_symbols) > 1
    assert options["exchange"] == tab_exchanges
    assert options["symbol"] == tab_symbols
    assert options["side"] == tab_sides


def test_the_default_from_date_matches_the_tab_to_the_second(qapp) -> None:
    """LOCAL midnight on 2026-04-01, which is not UTC midnight.

    A failure here means the contract would fetch from a different
    instant than the tab does, and the operator would see a different
    number of trades on the two surfaces.
    """
    tab = _tab(qapp, _bot_manager())
    defaults = hrc.default_filters()
    assert defaults.from_ts == tab._from_dt.dateTime().toSecsSinceEpoch()

    tab._reset_filters()
    assert defaults.from_ts == tab._from_dt.dateTime().toSecsSinceEpoch()
    assert tab._exch_combo.currentText() == defaults.exchange
    assert tab._sym_combo.currentText() == defaults.symbol
    assert tab._side_combo.currentText() == defaults.side


# ── paging, driven at the boundary ─────────────────────────────────────


@pytest.mark.parametrize("count", [1, hrc.PAGE_SIZE, hrc.PAGE_SIZE + 1])
def test_paging_agrees_at_the_boundary(qapp, count: int) -> None:
    """One row, exactly a full page, and one row past a full page."""
    rows = _uniform_rows(count)
    manager = _bot_manager()
    tab = _tab(qapp, manager)

    expected_pages = 1 if count <= hrc.PAGE_SIZE else 2
    assert hrc.page_count(count) == expected_pages

    for page in range(expected_pages):
        tab_side = _tab_render(tab, rows, page)
        con_side = _contract_render(rows, page, manager)
        assert len(tab_side["rows"]) == min(hrc.PAGE_SIZE, count - page * hrc.PAGE_SIZE)
        _assert_same(tab_side, con_side)


def test_a_page_past_the_last_is_clamped_the_way_the_tab_clamps(qapp) -> None:
    rows = _uniform_rows(hrc.PAGE_SIZE + 1)
    manager = _bot_manager()
    tab_side = _tab_render(_tab(qapp, manager), rows, page=7)
    con_side = _contract_render(rows, 7, manager)
    assert tab_side["page"] == 1
    assert len(tab_side["rows"]) == 1
    _assert_same(tab_side, con_side)


def test_an_empty_filtered_set_reads_the_same_on_both_sides(qapp) -> None:
    """The one case where agreeing on nothing is the correct answer.

    It is asserted explicitly so the vacuous case is covered by a test
    that SAYS it is the vacuous case, rather than by the agreement test
    quietly passing on it.
    """
    manager = _bot_manager()
    tab_side = _tab_render(_tab(qapp, manager), [])
    con_side = _contract_render([], 0, manager)
    assert tab_side["rows"] == []
    assert tab_side["page_label"] == "No matches"
    _assert_same(tab_side, con_side)


# ── the summary line ───────────────────────────────────────────────────


def test_the_summary_line_matches_the_tab(qapp) -> None:
    """Both branches: no fetch yet, and a fetch some seconds ago."""
    rows = _mixed_rows()
    manager = _bot_manager()
    tab = _tab(qapp, manager)

    _tab_render(tab, rows)
    assert tab._summary.text() == hrc.summary_line(rows, len(rows), 0.0)
    assert "no fetch yet" in tab._summary.text()

    # The half-second offset keeps both integer truncations one side of a boundary.
    now = time.time()
    tab._last_fetched_ts = now - 5.5
    tab._render_page()
    assert tab._summary.text() == hrc.summary_line(
        rows, len(rows), now - 5.5, now_ts=now
    )
    assert "fetched 5s ago" in tab._summary.text()


# ── the CSV export ─────────────────────────────────────────────────────


def test_the_csv_rows_match_the_file_the_tab_writes(
    qapp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Read the tab's own artifact back through ``csv.reader``.

    The comparison is against the FILE, not against the rows handed to
    the writer -- a formatting difference that raised per row would leave
    the two lists equal and the file short.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    rows = _mixed_rows()
    manager = _bot_manager()
    tab = _tab(qapp, manager)
    tab._all_trades = list(rows)
    tab._filtered = list(rows)

    target = tmp_path / "history.csv"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(_returns((str(target), ""))),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(_returns(None)))
    tab._export_csv()

    with open(target, "r", newline="", encoding="utf-8") as handle:
        written = list(csv.reader(handle))

    assert len(written) == len(rows) + 1, "the export wrote a short file"
    assert written[0] == list(hrc.CSV_HEADER)
    assert hrc.csv_rows(rows, manager) == written[1:]


# ── the column specification ───────────────────────────────────────────


def test_the_column_spec_matches_the_tab_header(qapp) -> None:
    """Thirteen headers, in order, plus the three header tooltips.

    Read out of the rendered ``thead``, so this measures the header row
    the operator sees rather than the column list that was pushed.
    """
    tab = _tab(qapp, _bot_manager())
    _tab_render(tab, _mixed_rows())
    headers = json.loads(
        _eval_in(
            tab._table._web,
            "JSON.stringify(Array.prototype.map.call("
            'document.querySelectorAll("#panel-table thead th"),'
            "function (th) { return {"
            'key: th.getAttribute("data-col-key"),'
            "header: th.textContent,"
            'tooltip: th.getAttribute("title") || ""'
            "}; }))",
        )
    )
    assert len(headers) == len(hrc.COLUMNS) == 13
    for column, shown in zip(hrc.COLUMNS, headers):
        assert shown["key"] == column.key
        assert shown["header"] == column.header, (
            f"column {column.index}: tab {shown['header']!r}, "
            f"contract {column.header!r}"
        )
        assert shown["tooltip"] == column.header_tooltip
    assert tab.PAGE_SIZE == hrc.PAGE_SIZE


def test_the_status_strings_are_the_ones_the_tab_shows(qapp) -> None:
    """Three states driven for real; two pinned against the source.

    ``idle``, ``no_bot_manager`` and ``no_async_loop`` are reachable
    without an event loop, so they are read off the real QLabel.
    ``fetching`` and ``timeout`` need a live future and a sixty-second
    wait respectively; they are pinned as literals in the tab's source,
    which is the surface that would change if someone reworded them.
    """
    tab = _tab(qapp, _bot_manager())
    assert tab._summary.text() == hrc.STATUS_TEXT["idle"]

    tab.set_bot_manager(None)
    tab.refresh()
    assert tab._summary.text() == hrc.STATUS_TEXT["no_bot_manager"]

    tab.set_bot_manager(_BotManager())
    tab.refresh()
    assert tab._summary.text() == hrc.STATUS_TEXT["no_async_loop"]

    source = (REPO / "src" / "gui" / "history_tab.py").read_text(encoding="utf-8")
    assert hrc.STATUS_TEXT["fetching"] in source
    # The tab splits the timeout message across two adjacent literals.
    assert "Fetch timeout (60s). Exchange may be rate-" in source
    assert "limited; try again." in source
    assert "poll_timer.setInterval(400)" in source
    assert "> 60.0" in source
    assert hrc.FETCH_POLL_INTERVAL_S == 0.4
    assert hrc.FETCH_TIMEOUT_S == 60.0


# ── the contract writes nothing ────────────────────────────────────────


def _digest(obj: Any) -> str:
    """A stable digest of an object graph, for a before/after comparison.

    ``default=repr`` is what lets a live ``ScrummingBot`` be digested at
    all. Every object is the SAME object on both reads, so a repr that
    carries an identity is identical unless the object itself changed;
    a mutated list, dict or float shows because its repr shows.
    """
    payload = json.dumps(obj, sort_keys=True, default=repr).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class _StubExchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


def _real_bot() -> Any:
    """A real ``ScrummingBot`` on a real ``BotConfig``, 110 attributes."""
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    config = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="coinbase",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
    )
    config.symbol = "CHIP/USD"
    return ScrummingBot(config, _StubExchange(), enable_phantoms=False)


def _manager_state(manager: Any) -> dict:
    """The manager's own state, with each bot expanded to ITS state.

    ``repr`` of a bot is ``<ScrummingBot object at 0x...>`` and does not
    move when the bot's lots do, so a digest taken over reprs would
    report "nothing was written" about any in-place mutation. Each bot is
    replaced by a digest of its ``vars`` instead.
    """
    out: dict = {}
    for name, value in vars(manager).items():
        if name == "_bots":
            out[name] = {
                bot_id: _digest(vars(bot)) for bot_id, bot in sorted(value.items())
            }
        else:
            out[name] = repr(value)
    return out


@pytest.mark.usefixtures("qapp")
def test_the_contract_writes_nothing_to_a_real_bot() -> None:
    """Drive the whole read path against a real bot and a real manager.

    Every entry point the contract offers a client is called: the filter
    options, the filter pass, the pager, the page build, the summary and
    the CSV rows. The bot's state, the manager's state and the trade rows
    handed in are digested before and after and must be identical.

    A failure means the read contract mutated trading state, which is the
    single property that put History first in the migration order.

    WHAT THIS CONTROL CANNOT SEE, measured rather than assumed. It is a
    VALUE control, not a write-access control. A planted
    ``row["cost"] = row["cost"]`` -- a real assignment that stores the
    value already there -- was driven through it and did NOT go red,
    because no state moved. Catching that would need a recording proxy
    around every dict and every bot, and it would be proving something
    the contract does not claim: the claim is that trading state is
    unchanged, not that no ``__setitem__`` runs.
    """
    from src.trading.bot_container import BotManager

    bot = _real_bot()

    # `BotManager()` subscribes handlers on the process-wide bus and cannot retract them.
    manager = BotManager.__new__(BotManager)
    manager._bots = {bot.bot_id: bot}
    manager._async_loop = None

    rows = _mixed_rows()
    before_bot = _digest(vars(bot))
    before_manager = _digest(_manager_state(manager))
    before_rows = _digest(rows)

    options = hrc.filter_options(rows)
    kept = hrc.apply_filters(rows, hrc.HistoryFilters())
    page = hrc.build_page(kept, 0, manager)
    label = hrc.page_label(0, len(kept))
    summary = hrc.summary_line(kept, len(rows), 0.0)
    exported = hrc.csv_rows(kept, manager)
    ordered = hrc.sort_trades(rows)

    # The read must have produced something, or "it wrote nothing" is a
    # statement about a call that did nothing.
    assert len(page.rows) == 17
    assert len(exported) == 17
    assert len(ordered) == 17
    assert options["exchange"] == ["(all)", "coinbase", "kraken"]
    assert label == "Page 1 / 1 (17 trades)"
    assert summary.startswith("17 of 17 trades shown")

    assert _digest(vars(bot)) == before_bot, "the contract mutated the bot"
    assert (
        _digest(_manager_state(manager)) == before_manager
    ), "the contract mutated the bot manager"
    assert _digest(rows) == before_rows, "the contract mutated its input rows"


@pytest.mark.usefixtures("qapp")
def test_the_digest_notices_a_change() -> None:
    """The other half of the write control.

    A digest that returns the same string for two different object graphs
    would report "nothing was written" about a mutation that really
    happened. Four are driven -- a rebound scalar, a list mutated in
    place, a bot's state moving beneath the manager, and a row edited --
    and each must move the digest.

    It moves on a CHANGED value. A write that stores the value already
    there does not move it, and the write test above says so.
    """
    from src.trading.bot_container import BotManager

    bot = _real_bot()
    assert "_current_holdings" in vars(bot)
    assert "_main_lots" in vars(bot)

    # A rebound scalar.
    before = _digest(vars(bot))
    bot._current_holdings = float(bot._current_holdings or 0.0) + 1.0
    assert _digest(vars(bot)) != before

    # A list mutated IN PLACE, which is the shape a careless read path
    # actually produces and the shape an identity-only digest misses.
    before = _digest(vars(bot))
    bot._main_lots.append({"units": 1.0, "initial_buy_price": 2.0})
    assert _digest(vars(bot)) != before

    # The manager view: a bot added, and a bot's own state moved.
    manager = BotManager.__new__(BotManager)
    manager._bots = {bot.bot_id: bot}
    manager._async_loop = None
    before = _digest(_manager_state(manager))
    bot._main_lots.append({"units": 3.0, "initial_buy_price": 4.0})
    assert _digest(_manager_state(manager)) != before
    before = _digest(_manager_state(manager))
    manager._bots["extra"] = _real_bot()
    assert _digest(_manager_state(manager)) != before

    # And an input row.
    rows = _mixed_rows()
    row_digest = _digest(rows)
    rows[0]["price"] = rows[0]["price"] + 1.0
    assert _digest(rows) != row_digest


# ── serialisability ────────────────────────────────────────────────────


@pytest.mark.usefixtures("qapp")
def test_everything_the_contract_serves_survives_json() -> None:
    """No Qt type, no datetime, nothing a JSON encoder refuses.

    A failure means a client could not receive the value over any
    transport, which is the whole point of a read contract.
    """
    rows = _mixed_rows()
    manager = _bot_manager()
    page = hrc.build_page(rows, 0, manager)

    encoded = json.dumps(page.as_dict())
    decoded = json.loads(encoded)
    assert len(decoded["rows"]) == 17
    assert [c["key"] for c in decoded["rows"][0]["cells"]] == list(hrc.COLUMN_KEYS)

    json.dumps(hrc.filter_options(rows))
    json.dumps(hrc.default_filters().as_dict())
    json.dumps(hrc.csv_rows(rows, manager))
    json.dumps(
        {
            "page_size": hrc.PAGE_SIZE,
            "row_order": hrc.ROW_ORDER,
            "sides": list(hrc.SIDES),
            "status": hrc.STATUS_TEXT,
            "csv_header": list(hrc.CSV_HEADER),
            "columns": [
                {
                    "index": c.index,
                    "key": c.key,
                    "header": c.header,
                    "header_tooltip": c.header_tooltip,
                }
                for c in hrc.COLUMNS
            ],
        }
    )


def test_the_contract_imports_no_qt() -> None:
    """The module is backend code and must stay loadable without PySide6.

    Read as source text, because importing it in a process that has
    already imported Qt for another test cannot answer the question.
    """
    source = (REPO / "src" / "exchange" / "history_read_contract.py").read_text(
        encoding="utf-8"
    )
    assert "PySide6" not in source
    assert "QtWidgets" not in source
    assert "from src.gui" not in source


# ── the pure pieces, without Qt ─────────────────────────────────────────


def test_page_arithmetic_over_the_whole_boundary() -> None:
    """Every page count and clamp from zero rows to two full pages.

    Pure arithmetic, so it runs on a box with no Qt. The Qt agreement at
    1, 100 and 101 rows is above; this closes the arithmetic between and
    around them.
    """
    assert hrc.page_count(0) == 1
    assert hrc.page_count(1) == 1
    assert hrc.page_count(hrc.PAGE_SIZE) == 1
    assert hrc.page_count(hrc.PAGE_SIZE + 1) == 2
    assert hrc.page_count(2 * hrc.PAGE_SIZE) == 2
    assert hrc.page_count(2 * hrc.PAGE_SIZE + 1) == 3

    assert hrc.clamp_page(-4, 250) == 0
    assert hrc.clamp_page(0, 0) == 0
    assert hrc.clamp_page(99, 250) == 2
    assert hrc.clamp_page(2, 250) == 2

    rows = _uniform_rows(hrc.PAGE_SIZE + 1)
    assert len(hrc.page_slice(rows, 0)) == hrc.PAGE_SIZE
    assert len(hrc.page_slice(rows, 1)) == 1
    assert len(hrc.page_slice(rows, 9)) == 1
    assert hrc.page_slice([], 0) == []
    assert hrc.page_label(0, 0) == "No matches"


def test_the_row_order_is_newest_first() -> None:
    """``sort_trades`` states the order the fetch already produces."""
    scrambled = [
        _row("a", ts=BASE_TS - 100),
        _row("b", ts=BASE_TS),
        _row("c", ts=BASE_TS - 50),
    ]
    assert [r["id"] for r in hrc.sort_trades(scrambled)] == ["b", "c", "a"]
    assert hrc.ROW_ORDER == "timestamp_desc"
    # The input is not reordered in place.
    assert [r["id"] for r in scrambled] == ["a", "b", "c"]
