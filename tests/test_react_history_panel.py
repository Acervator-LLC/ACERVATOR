"""Issue #128 unit R4 — the React History panel renders the contract.

WHAT IS BEING PROVED, AND AGAINST WHAT
======================================
``src/gui/react_history_panel.py`` draws History a second time, in
React, inside the Chromium PySide6 ships. The claim under test is that
it draws exactly what ``src/exchange/history_read_contract.py`` serves
and derives nothing of its own.

THE EVIDENCE IS THE DOM, NOT THE PAYLOAD
========================================
The agreement tests read text, colour and tooltip back out of a live
``QWebEngineView`` with ``runJavaScript``. Comparing the Python payload
to the Python contract would compare a dict to the function that built
it, which is an instrument agreeing with itself.

THE VACUOUS-PASS CONTROL
========================
A panel that renders nothing disagrees with nothing. Every agreement
test asserts a non-empty row count and non-empty cell text BEFORE it
asserts agreement, and ``test_dom_agreement_control_*`` proves those
assertions can fail.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

from src.exchange import history_read_contract as hrc  # noqa: E402
from src.gui import react_history_panel as rhp  # noqa: E402

BASE_TS = 1_750_000_000.0

#: Digests of the vendored React UMD bundles, taken when they were
#: downloaded from unpkg on 2026-08-26. React 18.3.1.
VENDOR_SHA256 = {
    "vendor/react.production.min.js": (
        "d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd"
    ),
    "vendor/react-dom.production.min.js": (
        "35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d"
    ),
}


# ── fixtures ───────────────────────────────────────────────────────────


def _reader_of(entries: list) -> Any:
    """A FRESH iterator per call, as the live-log readers give."""

    def _read(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return iter(list(entries))

    return _read


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read EMPTY live logs. Without this the suite parses the
    operator's 262 MB gate log."""
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of([]))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", _reader_of([]))


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
        "fee_currency": fee_currency,
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc) if ts > 0 else None,
    }


def _mixed_rows(count: int = 13) -> list[dict]:
    """Newest-first rows that light up every branch in the render path.

    Deliberately NOT uniform: identical rows make an agreement test pass
    against a renderer that ignores its input.
    """
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


@pytest.fixture(scope="module")
def qapp():
    """The QApplication every browser test runs against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


# ── the browser driver ─────────────────────────────────────────────────

_JS_TIMEOUT_MS = 30_000


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


class _Page:
    """A loaded QWebEngineView whose DOM can be read synchronously.

    ``runJavaScript`` answers through a callback, so each read spins a
    nested ``QEventLoop`` with a ceiling. A read that times out returns
    the sentinel rather than the previous answer, so a stalled browser
    cannot be mistaken for agreement.
    """

    TIMED_OUT = object()

    def __init__(self, html: str):
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._wait_signal(self._view.loadFinished, lambda: self._view.setHtml(html))

    def _wait_signal(self, signal, trigger) -> Any:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _catch(value: Any = None) -> None:
            box.setdefault("v", value)
            loop.quit()

        signal.connect(_catch)
        trigger()
        QTimer.singleShot(_JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        return box.get("v", self.TIMED_OUT)

    def js(self, script: str) -> Any:
        """Evaluate ``script`` and return its value."""
        return _eval_in(self._view, script)

    def push(self, model: dict) -> None:
        """Send one view model over the same statement the panel sends."""
        self.js(rhp.state_push_script(model))

    def dom(self) -> dict:
        """Read the whole rendered table back out of the DOM."""
        return json.loads(self.js(_DOM_DUMP_JS))

    def close(self) -> None:
        self._view.deleteLater()


# Reads what the SCREEN shows: `innerText` for text, the computed colour
# for colour, the `title` attribute for tooltip. Serialised to JSON so
# one round trip carries the whole table.
_DOM_DUMP_JS = r"""
JSON.stringify((function () {
  var err = document.getElementById("panel-error");
  var out = {
    error: err ? err.textContent : null,
    headers: [],
    rows: [],
    summary: null,
    pager: null,
    filters: {}
  };
  var summary = document.getElementById("panel-summary");
  if (summary) { out.summary = summary.textContent; }
  var label = document.getElementById("pager-label");
  var counts = document.getElementById("pager-counts");
  if (counts) {
    out.pager = {
      label: label ? label.textContent : null,
      page: Number(counts.getAttribute("data-page")),
      pages: Number(counts.getAttribute("data-pages")),
      total: Number(counts.getAttribute("data-total")),
      page_size: Number(counts.getAttribute("data-page-size")),
      row_count: Number(counts.getAttribute("data-row-count")),
      prev_enabled: !document.getElementById("pager-prev").disabled,
      next_enabled: !document.getElementById("pager-next").disabled
    };
  }
  document.querySelectorAll("#panel-table thead th").forEach(function (th) {
    out.headers.push({
      key: th.getAttribute("data-col-key"),
      header: th.textContent,
      tooltip: th.getAttribute("title")
    });
  });
  document.querySelectorAll("#panel-rows tr").forEach(function (tr) {
    var cells = [];
    tr.querySelectorAll("td").forEach(function (td) {
      var lights = td.querySelector(".gate-lights");
      var shown = td.cloneNode(true);
      var strip = shown.querySelector(".gate-lights");
      if (strip) { strip.remove(); }
      cells.push({
        key: td.getAttribute("data-col-key"),
        text: shown.textContent,
        color: td.getAttribute("data-cell-color"),
        tooltip: td.getAttribute("data-cell-tooltip"),
        painted: window.getComputedStyle(td).color,
        light_count: lights
          ? Number(lights.getAttribute("data-light-count"))
          : null
      });
    });
    out.rows.push({
      trade_id: tr.getAttribute("data-trade-id"),
      timestamp: Number(tr.getAttribute("data-timestamp")),
      cells: cells
    });
  });
  ["exchange", "symbol", "side"].forEach(function (k) {
    var sel = document.getElementById("filter-" + k);
    if (!sel) { return; }
    out.filters[k] = {
      value: sel.value,
      disabled: sel.disabled,
      options: Array.prototype.map.call(sel.options, function (o) {
        return o.value;
      })
    };
  });
  return out;
})())
"""


@pytest.fixture
def page(qapp):
    """One loaded panel page, torn down after the test."""
    del qapp
    loaded = _Page(rhp.panel_html())
    yield loaded
    loaded.close()


def _model(trades: list, page_index: int = 0, filters=None) -> dict:
    return rhp.build_view_model(
        trades,
        filters if filters is not None else hrc.HistoryFilters(),
        page_index,
        _bot_manager(),
        last_fetched_ts=BASE_TS,
        now_ts=BASE_TS + 5,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. The hosting story, verified rather than cited
# ═══════════════════════════════════════════════════════════════════════


def test_web_widget_is_a_bundled_hidden_import() -> None:
    """The spec ships the web widget and excludes no Qt web module."""
    from tools.spec_common import COMMON_HIDDENIMPORTS, EXCLUDES

    assert "PySide6.QtWebEngineWidgets" in COMMON_HIDDENIMPORTS
    web_excludes = [e for e in EXCLUDES if "web" in e.lower() or "Qt" in e]
    assert (
        web_excludes == []
    ), f"a Qt web module is excluded from the build: {web_excludes}"


def test_the_panel_assets_reach_the_frozen_build() -> None:
    """The assets sit under a directory the spec already ships.

    ``datas_candidates`` pairs the whole ``src`` tree to ``src``, so a
    file under ``src/gui/web/`` needs no spec change. Measured against
    the spec, NOT against a build: no build was run for this unit.
    """
    from tools.spec_common import datas_candidates

    shipped = [Path(s).resolve() for s, _ in datas_candidates(str(REPO))]
    assets = (REPO / "src" / "gui" / "web").resolve()
    assert any(
        assets == root or root in assets.parents for root in shipped
    ), f"{assets} is under no datas pair in {shipped}"


def test_the_bridge_is_the_one_tradingview_chart_uses() -> None:
    """``runJavaScript``, and no second web host."""
    source = (REPO / "src" / "gui" / "react_history_panel.py").read_text(
        encoding="utf-8"
    )
    assert "runJavaScript" in source
    assert "QWebEngineView" in source
    chart = (REPO / "src" / "gui" / "tradingview_chart.py").read_text(encoding="utf-8")
    assert "runJavaScript" in chart and "QWebEngineView" in chart


def _code_of(path: Path) -> str:
    """The module's CODE, with docstrings and comments removed.

    A name discussed in prose is not a call. Scanning raw text would let
    this module's own docstring -- which explains why QWebChannel is not
    used -- fail the test that says it is not used.
    """
    import io
    import tokenize

    source = path.read_text(encoding="utf-8")
    kept: list[str] = []
    previous = tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and previous in (
            tokenize.INDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.DEDENT,
        ):
            continue  # a docstring: the only string in statement position
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT):
            previous = tok.type
        else:
            previous = tok.type
        kept.append(tok.string)
    return " ".join(kept)


def test_no_back_channel_exists_so_the_page_cannot_write() -> None:
    """The write proof is structural: there is no path page -> Python.

    A ``QWebChannel`` or a ``setWebChannel`` here would give the page a
    callable Python object, and "read-only" would stop being a property
    of the wiring.
    """
    code = _code_of(REPO / "src" / "gui" / "react_history_panel.py")
    for forbidden in ("QWebChannel", "setWebChannel", "setUrlRequestInterceptor"):
        assert forbidden not in code, f"{forbidden} opens a path back into Python"


def test_no_back_channel_control_the_scan_can_see_a_real_call() -> None:
    """The control: the same scan DOES find the name in real code.

    Without this, a scan that strips everything would pass the test
    above on a module that really did open a channel.
    """
    code = _code_of(REPO / "src" / "gui" / "react_history_panel.py")
    assert "runJavaScript" in code, "the scan stripped the code, not the prose"
    prose = (REPO / "src" / "gui" / "react_history_panel.py").read_text(
        encoding="utf-8"
    )
    assert (
        "QWebChannel" in prose
    ), "the docstring that makes this test non-trivial is gone"


# ═══════════════════════════════════════════════════════════════════════
# 2. Assets: vendored, pinned, self-contained
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("name", sorted(VENDOR_SHA256))
def test_vendored_react_matches_its_digest(name: str) -> None:
    """The bundle on disk is the one that was downloaded."""
    raw = (rhp.asset_dir() / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == VENDOR_SHA256[name]
    assert b"\r" not in raw, "a carriage return reached a file written as LF"


def test_the_page_fetches_nothing_from_the_network(page) -> None:
    """No CDN, measured by the browser rather than by a string search.

    ``performance.getEntriesByType("resource")`` is Chromium's own record
    of every request the document made. A substring hunt for ``http://``
    cannot do this job: React's bundle carries the XML namespace URIs
    ``http://www.w3.org/1999/xhtml`` and ``.../2000/svg``, which are
    identifiers and are never dereferenced.
    """
    page.push(_model(_mixed_rows()))
    _assert_not_vacuous(page.dom())
    fetched = json.loads(
        page.js(
            "JSON.stringify(performance.getEntriesByType('resource')"
            ".map(function(e){return e.name;}))"
        )
    )
    assert fetched == [], f"the page fetched {fetched}"


def test_the_page_declares_no_external_asset() -> None:
    """And no tag asks for one, so an offline start cannot go blank.

    ``tradingview_chart.py:72`` pulls its charting library from unpkg,
    so that chart is empty with no network. This page inlines everything.
    """
    html = rhp.panel_html()
    external = re.findall(r"<(?:script|link|img|iframe)[^>]*\b(?:src|href)\s*=", html)
    assert external == [], f"the page declares external assets: {external}"
    chart = (REPO / "src" / "gui" / "tradingview_chart.py").read_text(encoding="utf-8")
    assert "unpkg.com" in chart, "the contrast this test draws is gone; re-check it"


def test_vendor_bundles_carry_no_script_terminator() -> None:
    """An inline ``<script>`` ends at the first ``</script>`` anywhere
    inside it, including inside a JS string literal."""
    for name in rhp.ASSET_NAMES:
        assert "</script" not in rhp.read_asset(name).lower(), name


def test_read_asset_names_the_file_it_could_not_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Break the assets and the error carries the path, not a blank
    page."""
    monkeypatch.setattr(rhp, "asset_dir", lambda: tmp_path)
    with pytest.raises(rhp.HistoryPanelAssetMissing) as caught:
        rhp.read_asset("history_panel.js")
    assert "history_panel.js" in str(caught.value)
    assert str(tmp_path) in str(caught.value)


def test_panel_html_survives_percent_and_braces_in_the_bundle() -> None:
    """React's minified bundle carries both. A ``%`` or ``format``
    interpolation would raise; joining does not."""
    assert "%" in rhp.read_asset("vendor/react-dom.production.min.js")
    html = rhp.panel_html()
    assert html.startswith("<!DOCTYPE html>")
    assert 'id="root"' in html
    assert len(html) > 100_000


# ═══════════════════════════════════════════════════════════════════════
# 3. The DOM shows what the contract serves
# ═══════════════════════════════════════════════════════════════════════


def _assert_not_vacuous(dom: dict, blank_ok: frozenset = frozenset()) -> None:
    """The control that stops an empty panel agreeing with everything.

    ``blank_ok`` names the columns the CONTRACT itself serves empty for
    the fixture in hand. It defaults to nothing, so every other test
    keeps the strict rule.
    """
    assert dom["error"] is None, dom["error"]
    assert len(dom["rows"]) > 0, "no rows rendered; agreement would be vacuous"
    assert len(dom["headers"]) == len(hrc.COLUMNS)
    cells = [c for r in dom["rows"] for c in r["cells"]]
    assert len(cells) == len(dom["rows"]) * len(hrc.COLUMNS)
    blank = [c["key"] for c in cells if c["text"] == "" and c["key"] not in blank_ok]
    assert blank == [], f"a blank cell cannot evidence agreement: {blank}"


def test_dom_renders_all_thirteen_columns(page) -> None:
    page.push(_model(_mixed_rows()))
    dom = page.dom()
    _assert_not_vacuous(dom)
    assert [h["key"] for h in dom["headers"]] == list(hrc.COLUMN_KEYS)
    assert [h["header"] for h in dom["headers"]] == [c.header for c in hrc.COLUMNS]
    assert [h["tooltip"] for h in dom["headers"]] == [
        c.header_tooltip for c in hrc.COLUMNS
    ]


def test_dom_cells_agree_with_the_contract_cell_for_cell(page) -> None:
    """Every text, colour and tooltip on screen against the contract's.

    The contract is re-derived here from the trade rows, not read off
    the payload the panel built, so this compares two independent walks
    of the same source.
    """
    trades = _mixed_rows()
    page.push(_model(trades))
    dom = page.dom()
    _assert_not_vacuous(dom)

    filtered = hrc.apply_filters(trades, hrc.HistoryFilters())
    expected = hrc.build_page(filtered, 0, _bot_manager())
    assert len(dom["rows"]) == len(expected.rows)

    compared = 0
    for shown, want in zip(dom["rows"], expected.rows):
        assert shown["trade_id"] == want.trade_id
        assert shown["timestamp"] == want.timestamp
        assert len(shown["cells"]) == len(want.cells)
        for cell_dom, cell in zip(shown["cells"], want.cells):
            assert cell_dom["key"] == cell.key
            assert cell_dom["text"] == cell.text, cell.key
            assert cell_dom["color"] == (cell.color or ""), cell.key
            assert cell_dom["tooltip"] == (cell.tooltip or ""), cell.key
            compared += 3
    assert compared == len(expected.rows) * len(hrc.COLUMNS) * 3
    print(
        f"R4 DOM AGREEMENT rows={len(dom['rows'])} "
        f"cells={len(dom['rows']) * len(hrc.COLUMNS)} comparisons={compared}"
    )


def test_a_colour_the_contract_sets_is_actually_painted(page) -> None:
    """The colour reaches the pixel, not only the attribute.

    A cell whose ``color`` the contract sets must have that colour in the
    browser's COMPUTED style. Reading only ``data-cell-color`` would pass
    on a stylesheet that overrules every cell.
    """
    page.push(_model(_mixed_rows()))
    dom = page.dom()
    _assert_not_vacuous(dom)

    coloured = [
        c for r in dom["rows"] for c in r["cells"] if c["key"] == "side" and c["color"]
    ]
    assert coloured, "no side cell carried a colour; the check would be vacuous"
    for cell in coloured:
        want = cell["color"].lstrip("#")
        rgb = tuple(int(want[i : i + 2], 16) for i in (0, 2, 4))
        assert cell["painted"] == f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})", cell


def test_dom_agreement_control_a_blank_table_is_caught() -> None:
    """The vacuous-pass guard fails when handed an empty table."""
    with pytest.raises(AssertionError, match="agreement would be vacuous"):
        _assert_not_vacuous({"error": None, "rows": [], "headers": []})


def test_dom_agreement_control_a_blank_cell_is_caught() -> None:
    """And when handed a table of empty cells."""
    blank = {
        "error": None,
        "headers": [{"key": c.key} for c in hrc.COLUMNS],
        "rows": [{"cells": [{"key": c.key, "text": ""} for c in hrc.COLUMNS]}],
    }
    with pytest.raises(AssertionError, match="blank cell"):
        _assert_not_vacuous(blank)


def test_dom_agreement_control_a_declared_blank_does_not_blind_the_guard() -> None:
    """Declaring one column blank-ok must not excuse the other twelve."""
    blank = {
        "error": None,
        "headers": [{"key": c.key} for c in hrc.COLUMNS],
        "rows": [{"cells": [{"key": c.key, "text": ""} for c in hrc.COLUMNS]}],
    }
    with pytest.raises(AssertionError, match="blank cell"):
        _assert_not_vacuous(blank, blank_ok=frozenset({"bot"}))


def test_the_filter_options_the_contract_exposes_are_on_screen(page) -> None:
    trades = _mixed_rows()
    page.push(_model(trades))
    dom = page.dom()
    _assert_not_vacuous(dom)
    want = hrc.filter_options(trades)
    for key in ("exchange", "symbol", "side"):
        assert dom["filters"][key]["options"] == want[key], key
        assert dom["filters"][key]["value"] == hrc.ALL
        assert dom["filters"][key]["disabled"] is True


def test_a_filter_narrows_the_rendered_rows(page) -> None:
    trades = _mixed_rows()
    filters = hrc.HistoryFilters(symbol="RAVE/USD")
    page.push(_model(trades, filters=filters))
    dom = page.dom()
    _assert_not_vacuous(dom)
    expected = hrc.apply_filters(trades, filters)
    assert 0 < len(expected) < len(trades), "the filter must retain some and drop some"
    assert len(dom["rows"]) == len(expected)
    assert {r["trade_id"] for r in dom["rows"]} == {r["id"] for r in expected}


def test_the_summary_line_on_screen_is_the_contract_s(page) -> None:
    trades = _mixed_rows()
    page.push(_model(trades))
    dom = page.dom()
    _assert_not_vacuous(dom)
    want = hrc.summary_line(
        hrc.apply_filters(trades, hrc.HistoryFilters()),
        len(trades),
        BASE_TS,
        BASE_TS + 5,
    )
    assert dom["summary"] == want


# ═══════════════════════════════════════════════════════════════════════
# 4. Paging boundaries: 1, PAGE_SIZE, PAGE_SIZE + 1
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "count,index,rows_on_page,pages,prev,next_",
    [
        (1, 0, 1, 1, False, False),
        (hrc.PAGE_SIZE, 0, hrc.PAGE_SIZE, 1, False, False),
        (hrc.PAGE_SIZE + 1, 0, hrc.PAGE_SIZE, 2, False, True),
        (hrc.PAGE_SIZE + 1, 1, 1, 2, True, False),
    ],
)
def test_paging_boundary_on_screen(
    page, count: int, index: int, rows_on_page: int, pages: int, prev: bool, next_: bool
) -> None:
    """The pager the browser draws, at one row, exactly PAGE_SIZE and
    PAGE_SIZE + 1."""
    trades = _mixed_rows(count)
    page.push(_model(trades, page_index=index))
    dom = page.dom()
    _assert_not_vacuous(dom)
    assert len(dom["rows"]) == rows_on_page
    assert dom["pager"]["row_count"] == rows_on_page
    assert dom["pager"]["pages"] == pages
    assert dom["pager"]["total"] == count
    assert dom["pager"]["page"] == index
    assert dom["pager"]["page_size"] == hrc.PAGE_SIZE
    assert dom["pager"]["prev_enabled"] is prev
    assert dom["pager"]["next_enabled"] is next_
    assert dom["pager"]["label"] == hrc.page_label(index, count)


def test_page_two_shows_the_rows_page_one_did_not(page) -> None:
    """Both pages, disjoint, covering the whole set."""
    trades = _mixed_rows(hrc.PAGE_SIZE + 1)
    page.push(_model(trades, page_index=0))
    first = {r["trade_id"] for r in page.dom()["rows"]}
    page.push(_model(trades, page_index=1))
    second = {r["trade_id"] for r in page.dom()["rows"]}
    assert len(first) == hrc.PAGE_SIZE and len(second) == 1
    assert first.isdisjoint(second)
    assert first | second == {r["id"] for r in trades}


# ═══════════════════════════════════════════════════════════════════════
# 5. Break the bridge
# ═══════════════════════════════════════════════════════════════════════


def test_a_page_that_was_never_pushed_says_so(page) -> None:
    """No push means the banner, not a blank table that agrees with
    everything."""
    dom = page.dom()
    assert dom["rows"] == []
    assert dom["error"] is not None
    assert "Python never called acervatorSetState" in dom["error"]


@pytest.mark.parametrize(
    "payload,fragment",
    [
        (None, "Python never called acervatorSetState"),
        ({"columns": []}, "no page, summary, filters, filter_options, loaded"),
        ("a string", "delivered a string, not an object"),
    ],
)
def test_a_broken_payload_names_the_real_problem(page, payload, fragment) -> None:
    """Each fault the bridge can deliver names itself on screen."""
    page.js("window.acervatorSetState(" + json.dumps(payload) + ");")
    dom = page.dom()
    assert dom["rows"] == []
    assert dom["error"] is not None and fragment in dom["error"], dom["error"]


def test_the_bridge_recovers_after_a_broken_payload(page) -> None:
    """A fault is not sticky: the next good push draws the table.

    Without this the banner tests would pass on a page that can only ever
    show a banner.
    """
    page.js("window.acervatorSetState(null);")
    assert page.dom()["error"] is not None
    page.push(_model(_mixed_rows()))
    _assert_not_vacuous(page.dom())


def test_a_severed_push_leaves_the_last_good_render(page, monkeypatch) -> None:
    """Cut the statement the bridge sends and the screen stops changing.

    Proves the DOM is downstream of ``state_push_script``: if the tests
    were reading a table the page built for itself, blanking the push
    would change nothing.
    """
    page.push(_model(_mixed_rows(5)))
    before = page.dom()
    assert len(before["rows"]) == 5

    monkeypatch.setattr(rhp, "state_push_script", lambda payload: "0;")
    page.push(_model(_mixed_rows(9)))
    after = page.dom()
    assert len(after["rows"]) == 5, "the severed push still reached the DOM"

    monkeypatch.undo()
    page.push(_model(_mixed_rows(9)))
    assert len(page.dom()["rows"]) == 9, "the restored push did not reach the DOM"


# ═══════════════════════════════════════════════════════════════════════
# 6. The JSON injection shape
# ═══════════════════════════════════════════════════════════════════════


#: Values that break the quote-wrapping injection shape. The last two
#: are legal inside a JSON string and are line terminators in JS.
HOSTILE_TEXT = 'IT\'S "x" \u2028 \u2029 </script> \\ end'


def test_hostile_text_in_the_data_survives_the_bridge(page) -> None:
    """The defect shape ``tradingview_chart.py:_run_js`` carries.

    It builds ``f"setCandles('{json.dumps(x)}')"``: JSON inside a
    single-quoted JS string. ``json.dumps`` does not escape ``'``, so one
    apostrophe ends the string and the rest executes. This module embeds
    the JSON as a bare expression, so the same characters arrive intact.
    """
    trades = _mixed_rows(2)
    trades[0]["symbol"] = HOSTILE_TEXT
    page.push(_model(trades))
    dom = page.dom()
    # NAMED, NOT FIXED, and it belongs to R3 rather than to this panel:
    # `history_read_contract._bot_cell` serves "" -- not the "-" every
    # other empty gets -- when no bot matches the symbol, and a hostile
    # symbol matches none. The panel renders that "" faithfully, which is
    # what this test is here to show.
    _assert_not_vacuous(dom, blank_ok=frozenset({"bot"}))
    shown = {c["key"]: c["text"] for c in dom["rows"][0]["cells"]}
    assert shown["symbol"] == HOSTILE_TEXT
    assert shown["bot"] == "", "the contract stopped serving a blank bot cell"


def test_the_push_statement_escapes_the_two_js_line_terminators() -> None:
    """U+2028 and U+2029 are legal in JSON and end a JS statement."""
    script = rhp.state_push_script({"t": "a\u2028b\u2029c"})
    assert "\u2028" not in script and "\u2029" not in script
    assert "\\u2028" in script and "\\u2029" in script


def test_injection_control_the_chart_shape_breaks_on_the_same_data(page) -> None:
    """The control that gives the test above its meaning.

    Both statements go to the SAME browser. The shipped one evaluates;
    the quote-wrapping one raises a SyntaxError. Without this control the
    test above would pass on data that no shape could break.
    """
    payload = {"symbol": HOSTILE_TEXT}
    safe = rhp.state_push_script(payload)
    unsafe = "window.acervatorSetState('" + json.dumps(payload) + "');"

    def verdict(statement: str) -> str:
        wrapped = (
            "(function(){try{eval("
            + json.dumps(statement, ensure_ascii=True)
            + ");return 'ok';}catch(e){return e.name;}})()"
        )
        return page.js(wrapped)

    assert verdict(safe) == "ok", "the shipped shape does not evaluate"
    assert verdict(unsafe) == "SyntaxError", "the chart shape survived hostile data"


# ═══════════════════════════════════════════════════════════════════════
# 7. The panel writes nothing
# ═══════════════════════════════════════════════════════════════════════

_TRADING_STATE_FILES = (
    REPO / "src" / "trading" / "scrumming_bot.py",
    REPO / "src" / "exchange" / "history_read_contract.py",
    REPO / "src" / "gui" / "history_tab.py",
)


def test_rendering_leaves_trading_state_byte_identical(page) -> None:
    """Byte digests of the trading sources, before and after a render.

    A weak check on its own; it is the file-level half of the structural
    proof in ``test_no_back_channel_exists_so_the_page_cannot_write``.
    """
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in _TRADING_STATE_FILES
    }
    trades = _mixed_rows()
    page.push(_model(trades))
    _assert_not_vacuous(page.dom())
    after = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in _TRADING_STATE_FILES
    }
    assert before == after


def test_building_a_view_model_does_not_mutate_the_trades(page=None) -> None:
    """The trade rows the History tab owns come back unchanged."""
    del page
    trades = _mixed_rows()
    snapshot = json.dumps(trades, default=str, sort_keys=True)
    rhp.build_view_model(trades, hrc.HistoryFilters(), 0, _bot_manager())
    assert json.dumps(trades, default=str, sort_keys=True) == snapshot


def test_the_module_opens_no_file_for_writing() -> None:
    """No write mode anywhere in the panel."""
    source = (REPO / "src" / "gui" / "react_history_panel.py").read_text(
        encoding="utf-8"
    )
    for shape in ('"w"', "'w'", '"a"', "'a'", '"wb"', "write_text", "write_bytes"):
        assert shape not in source, f"{shape} is a write"


# ═══════════════════════════════════════════════════════════════════════
# 8. The Qt host
# ═══════════════════════════════════════════════════════════════════════


def test_the_panel_widget_renders_the_contract_end_to_end(qapp) -> None:
    """Drive the real widget: hand it trades the way main_window does."""
    del qapp
    panel = rhp.ReactHistoryPanel()
    try:
        panel.set_bot_manager(_bot_manager())
        trades = _mixed_rows()
        panel.on_history_refreshed(trades)
        model = panel.view_model()
        assert model["page"]["total"] == len(trades)
        assert len(model["page"]["rows"]) == len(trades)
        assert [c["key"] for c in model["columns"]] == list(hrc.COLUMN_KEYS)
        assert model["filter_options"] == hrc.filter_options(trades)
    finally:
        panel.deleteLater()


def test_the_panel_pager_walks_pages(qapp) -> None:
    del qapp
    panel = rhp.ReactHistoryPanel()
    try:
        panel.set_bot_manager(_bot_manager())
        panel.on_history_refreshed(_mixed_rows(hrc.PAGE_SIZE + 1))
        assert panel.view_model()["page"]["page"] == 0
        panel._on_next()
        assert panel.view_model()["page"]["page"] == 1
        assert len(panel.view_model()["page"]["rows"]) == 1
        panel._on_next()
        assert panel.view_model()["page"]["page"] == 1, "clamped at the last page"
        panel._on_prev()
        assert panel.view_model()["page"]["page"] == 0
    finally:
        panel.deleteLater()


def test_the_panel_combos_carry_the_contract_options(qapp) -> None:
    del qapp
    panel = rhp.ReactHistoryPanel()
    try:
        trades = _mixed_rows()
        panel.set_bot_manager(_bot_manager())
        panel.on_history_refreshed(trades)
        want = hrc.filter_options(trades)
        for key, combo in panel._combos.items():
            shown = [combo.itemText(i) for i in range(combo.count())]
            assert shown == want[key], key
    finally:
        panel.deleteLater()


def test_the_existing_history_tab_is_untouched() -> None:
    """Both panels exist after this unit. The Qt tab is the reference."""
    from src.gui.history_tab import HistoryTab

    assert HistoryTab.PAGE_SIZE == hrc.PAGE_SIZE
    wiring = (REPO / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert 'addTab(self._history_tab, "History")' in wiring
    assert 'addTab(panel, "History (React)")' in wiring
    assert wiring.index('addTab(self._history_tab, "History")') < wiring.index(
        'addTab(panel, "History (React)")'
    ), "the Qt tab must still be built first; it is the reference"


def test_the_shipped_widget_renders_into_its_own_view(qapp) -> None:
    """The DOM of the WIDGET, not of a page the test built for itself.

    Every other browser test drives a ``_Page`` this file constructs. This
    one reads ``ReactHistoryPanel._web`` -- the view the application puts
    on screen -- so the whole path from ``on_history_refreshed`` through
    ``render_now`` and ``runJavaScript`` into the DOM is covered once,
    end to end.
    """
    import time

    panel = rhp.ReactHistoryPanel()
    try:
        panel.set_bot_manager(_bot_manager())
        deadline = time.time() + 30.0
        while not panel._page_ready and time.time() < deadline:
            qapp.processEvents()
        assert panel._page_ready, "the panel's own document never loaded"

        trades = _mixed_rows()
        panel.on_history_refreshed(trades)
        dom = json.loads(_eval_in(panel._web, _DOM_DUMP_JS))
        _assert_not_vacuous(dom)

        expected = hrc.build_page(
            hrc.apply_filters(trades, hrc.HistoryFilters()), 0, _bot_manager()
        )
        assert len(dom["rows"]) == len(expected.rows) == len(trades)
        assert [r["trade_id"] for r in dom["rows"]] == [
            r.trade_id for r in expected.rows
        ]
        assert dom["pager"]["total"] == len(trades)
        assert dom["summary"] == panel.view_model()["summary"]
    finally:
        panel.deleteLater()
