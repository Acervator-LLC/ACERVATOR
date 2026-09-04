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


def _uniform_rows(count: int) -> list[dict]:
    """``count`` newest-first CHIP rows, one minute apart."""
    return [
        _row(f"p-{i:04d}", ts=BASE_TS - i * 60, price=10.0 + (i % 17))
        for i in range(count)
    ]


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


@pytest.mark.parametrize("module", ["react_history_panel.py", "history_tab.py"])
def test_no_back_channel_exists_so_the_page_cannot_write(module: str) -> None:
    """The write proof is structural: there is no path page -> Python.

    A ``QWebChannel`` or a ``setWebChannel`` would give the page a
    callable Python object, and "read-only" would stop being a property
    of the wiring. Both the host module and the tab that embeds it are
    scanned, because either could open the channel.

    ``row_count`` is not a back channel. Python asks and JavaScript
    answers one number; the page can raise nothing of its own and holds
    no Python object.
    """
    code = _code_of(REPO / "src" / "gui" / module)
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

    The candlestick chart used to fetch its charting library from a CDN
    and drew nothing offline. It carries that library now, so the same
    rule is asserted over both pages rather than as a contrast between
    them.
    """
    from src.gui import tradingview_chart as chart

    pattern = r"<(?:script|link|img|iframe)[^>]*\b(?:src|href)\s*="
    colors = dict(chart.CHART_THEMES["cyberpunk_dark"])
    colors["symbol"] = "BTC/USDT"
    for name, html in (
        ("history panel", rhp.panel_html()),
        ("candlestick chart", chart.page_html(colors)),
    ):
        external = re.findall(pattern, html)
        assert external == [], f"{name} declares external assets: {external}"


def test_the_external_asset_check_can_see_a_tag_that_is_there() -> None:
    """The check reports nothing whatever the page declares."""
    pattern = r"<(?:script|link|img|iframe)[^>]*\b(?:src|href)\s*="
    seeded = rhp.panel_html() + "<" + 'script src="x.js">' + "</" + "script>"
    assert re.findall(pattern, seeded) != []


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
    REPO / "src" / "trading" / "scrumming" / "execution.py",
    REPO / "src" / "trading" / "scrumming" / "fold_tranches.py",
    REPO / "src" / "trading" / "scrumming" / "reconciliation.py",
    REPO / "src" / "trading" / "scrumming" / "tick_phases.py",
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
# 8. The Qt host -- the shipped History tab
# ═══════════════════════════════════════════════════════════════════════


def _history_tab(qapp, trades: list, from_ts: float = BASE_TS - 86_400):
    """A real ``HistoryTab``, loaded, driven through its own controls.

    Rows are placed where a completed fetch places them and the tab's own
    ``_populate_filter_options`` and ``_apply_filters`` run, so the render
    reached here is the one the operator's Apply reaches.
    """
    import time

    from PySide6.QtCore import QDateTime
    from src.gui.history_tab import HistoryTab

    tab = HistoryTab()
    tab.set_bot_manager(_bot_manager())
    deadline = time.time() + 30.0
    while not tab._table.page_ready and time.time() < deadline:
        qapp.processEvents()
    assert tab._table.page_ready, "the tab's own document never loaded"

    # The From edit defaults to the 2026-04-01 launch date, which is after
    # the fixture's instants. Driving the date control is the point.
    tab._from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(from_ts)))
    tab._last_fetched_ts = BASE_TS
    tab._all_trades = list(trades)
    tab._populate_filter_options()
    tab._apply_filters()
    qapp.processEvents()
    return tab


def _tab_dom(tab) -> dict:
    return json.loads(_eval_in(tab._table._web, _DOM_DUMP_JS))


def test_the_react_variant_gives_the_history_tab_the_web_table() -> None:
    """The React build resolves History to the web table, not a Qt table."""
    from PySide6.QtWidgets import QTableWidget

    from src._variant import QT, REACT
    from src.gui.history_table_variant import history_table_class

    react = history_table_class(REACT)
    assert react.__name__ == "HistoryWebTable", (
        "the React build must draw History with the web table; got " + react.__name__
    )
    assert not issubclass(react, QTableWidget), (
        "the React History table must not be a QTableWidget; got " + react.__name__
    )

    qt = history_table_class(QT)
    assert qt is not react, (
        "the two builds exist to be compared, so they must not resolve to one "
        "class; both gave " + qt.__name__
    )


def test_the_qtablewidget_scan_can_see_a_real_table() -> None:
    """The control: the same scan DOES find a QTableWidget in real code.

    Without it, a scan that stripped everything would report the History
    tab clean whatever it held.
    """
    code = _code_of(REPO / "src" / "gui" / "alerts_tab.py")
    assert "QTableWidget" in code, "the scan stripped the code, not the prose"


def _window_wiring() -> str:
    """The window module and every per-tab builder, concatenated.

    Each ``addTab`` call now sits in the mixin that builds that tab.
    """
    gui = REPO / "src" / "gui"
    parts = [gui / "main_window.py"]
    parts += sorted((gui / "main_tabs").glob("*.py"))
    return "\n".join(p.read_text(encoding="utf-8") for p in parts)


def test_there_is_exactly_one_history_tab() -> None:
    """One tab named History, and no second renderer beside it."""
    wiring = _window_wiring()
    added = re.findall(r'addTab\([^,]+,\s*"([^"]*[Hh]istory[^"]*)"\)', wiring)
    assert added == ["History"], added
    assert "ReactHistoryPanel" not in wiring
    from src.gui.history_tab import HistoryTab

    assert HistoryTab.PAGE_SIZE == hrc.PAGE_SIZE


def test_the_canonical_tab_order_still_holds() -> None:
    """History keeps its place in the seven-tab order."""
    wiring = (REPO / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
    block = wiring[wiring.index("CANONICAL_TAB_ORDER = [") :]
    block = block[: block.index("]")]
    names = re.findall(r'"([^"]+)"', block)
    assert names == [
        "Trading",
        "Market Inspector",
        "Bot Swarm",
        "Asset Charts",
        "History",
        "Simulator",
        "Console",
    ], names


def test_the_shipped_tab_renders_the_contract_into_its_own_view(qapp) -> None:
    """The DOM of the TAB, not of a page the test built for itself.

    Every other browser test drives a ``_Page`` this file constructs. This
    one reads ``HistoryTab._table._web`` -- the view the application puts
    on screen -- so the whole path from the trade rows through
    ``_apply_filters``, ``_render_page`` and ``runJavaScript`` into the
    DOM is covered once, end to end.
    """
    trades = _mixed_rows()
    tab = _history_tab(qapp, trades)
    try:
        dom = _tab_dom(tab)
        _assert_not_vacuous(dom)
        expected = hrc.build_page(
            hrc.apply_filters(trades, tab._current_filters()), 0, _bot_manager()
        )
        assert len(dom["rows"]) == len(expected.rows) == len(trades)
        compared = 0
        for shown, want in zip(dom["rows"], expected.rows):
            assert shown["trade_id"] == want.trade_id
            for cell_dom, cell in zip(shown["cells"], want.cells):
                assert cell_dom["key"] == cell.key
                assert cell_dom["text"] == cell.text, cell.key
                assert cell_dom["color"] == (cell.color or ""), cell.key
                assert cell_dom["tooltip"] == (cell.tooltip or ""), cell.key
                compared += 3
        assert compared == len(expected.rows) * len(hrc.COLUMNS) * 3
        print(
            f"R6 SHIPPED-TAB AGREEMENT rows={len(dom['rows'])} "
            f"cells={len(dom['rows']) * len(hrc.COLUMNS)} comparisons={compared}"
        )
    finally:
        tab.deleteLater()


def test_the_tab_draws_no_duplicate_chrome(qapp) -> None:
    """The page draws the table only; the tab keeps its own controls.

    Two summary lines or two pagers on one tab would be the migration
    leaving a second copy of the chrome behind.
    """
    tab = _history_tab(qapp, _mixed_rows())
    try:
        dom = _tab_dom(tab)
        _assert_not_vacuous(dom)
        assert dom["summary"] is None, "the page drew a second summary line"
        assert dom["pager"] is None, "the page drew a second pager"
        assert dom["filters"] == {}, "the page drew a second filter bar"
        # And the Qt controls that own those jobs are populated.
        assert "trades shown" in tab._summary.text()
        assert tab._page_label.text().startswith("Page 1 /")
        assert tab._exch_combo.count() > 1
    finally:
        tab.deleteLater()


def test_the_chrome_flag_control_the_page_draws_it_when_asked(page) -> None:
    """The control for the test above: the same page CAN draw chrome.

    Without this, a page that had lost its summary, filters and pager
    entirely would pass ``test_the_tab_draws_no_duplicate_chrome``.
    """
    page.push(_model(_mixed_rows()))
    dom = page.dom()
    _assert_not_vacuous(dom)
    assert dom["summary"], "the default chrome draws no summary"
    assert dom["pager"] is not None
    assert set(dom["filters"]) == {"exchange", "symbol", "side"}


def test_the_tab_pager_walks_pages_in_the_dom(qapp) -> None:
    """Prev and Next move the rows the browser shows."""
    trades = _uniform_rows(hrc.PAGE_SIZE + 3)
    tab = _history_tab(qapp, trades)
    try:
        first = [r["trade_id"] for r in _tab_dom(tab)["rows"]]
        assert len(first) == hrc.PAGE_SIZE
        tab._next_page()
        qapp.processEvents()
        second = [r["trade_id"] for r in _tab_dom(tab)["rows"]]
        assert len(second) == 3
        assert set(first).isdisjoint(second)
        assert tab._page_label.text().startswith("Page 2 /")
        tab._prev_page()
        qapp.processEvents()
        assert [r["trade_id"] for r in _tab_dom(tab)["rows"]] == first
    finally:
        tab.deleteLater()


def test_a_filter_narrows_the_rows_the_tab_shows(qapp) -> None:
    """Driving the Side combo changes what the browser draws."""
    trades = _mixed_rows()
    tab = _history_tab(qapp, trades)
    try:
        before = len(_tab_dom(tab)["rows"])
        assert before == len(trades)
        tab._side_combo.setCurrentText("SELL")
        tab._apply_filters()
        qapp.processEvents()
        dom = _tab_dom(tab)
        wanted = [t for t in trades if t["side"] == "SELL"]
        assert 0 < len(wanted) < before, "the fixture cannot show a narrowing"
        assert len(dom["rows"]) == len(wanted)
        for row in dom["rows"]:
            side = [c for c in row["cells"] if c["key"] == "side"][0]
            assert side["text"] == "SELL"
    finally:
        tab.deleteLater()


def test_reset_puts_every_filter_back(qapp) -> None:
    """Reset returns the five controls to their opening values."""
    tab = _history_tab(qapp, _mixed_rows())
    try:
        tab._side_combo.setCurrentText("SELL")
        tab._exch_combo.setCurrentIndex(1)
        tab._reset_filters()
        qapp.processEvents()
        assert tab._side_combo.currentIndex() == 0
        assert tab._exch_combo.currentIndex() == 0
        assert tab._sym_combo.currentIndex() == 0
        assert tab._from_dt.dateTime().toString("yyyy-MM-dd HH:mm") == (
            "2026-04-01 00:00"
        )
    finally:
        tab.deleteLater()


# ═══════════════════════════════════════════════════════════════════════
# 9. The gate lights, and the tooltips that carry markup
# ═══════════════════════════════════════════════════════════════════════


_LIGHT_DUMP_JS = r"""
JSON.stringify(Array.prototype.map.call(
  document.querySelectorAll(
    "#panel-rows tr td[data-col-key=gates] .gate-lights .light"),
  function (el) {
    return {
      bank: el.getAttribute("data-light-bank"),
      label: el.getAttribute("data-light-label"),
      state: el.getAttribute("data-light-state"),
      color: el.getAttribute("data-light-color"),
      painted: window.getComputedStyle(
        el.querySelector(".light-dot")).backgroundColor,
      shown: el.querySelector(".light-label").textContent
    };
  }))
"""


def test_the_gate_lights_are_the_simulators_nineteen(qapp, monkeypatch) -> None:
    """Nineteen labelled lights, the Simulator's own order and colours.

    The Qt cell this replaces was ``sim_visuals.GateLightsCell``. What is
    compared here is the vocabulary module both surfaces now paint from,
    so a light that disagrees is a rendering fault and not a second map.
    """
    import src.trading.live_log_reader as llr
    from src.trading.gate_vocabulary import gate_light_row

    trades = _mixed_rows()
    manager = _bot_manager()
    entries = [
        _gate_entry(
            hrc.resolve_bot_id_for_row(manager, t),
            t["timestamp"],
            scrum_blockers=["delta<=0"],
        )
        for t in trades
    ]
    assert all(e["bot_id"] for e in entries), "no row resolved to a bot"
    monkeypatch.setattr(llr, "live_gate_decisions", _reader_of(entries))

    tab = _history_tab(qapp, trades)
    try:
        lights = json.loads(_eval_in(tab._table._web, _LIGHT_DUMP_JS))
        want_per_row = gate_light_row(False, False, ["delta<=0"], [], "")
        assert len(want_per_row) == 19
        assert lights, "no gate light reached the DOM"
        assert len(lights) % 19 == 0, len(lights)
        assert any(
            w["state"] == "blocked" for w in want_per_row
        ), "the fixture lights no red gate; agreement would be vacuous"
        for i, light in enumerate(lights):
            want = want_per_row[i % 19]
            assert light["bank"] == want["bank"]
            assert light["label"] == want["label"] == light["shown"]
            assert light["state"] == want["state"]
            assert light["color"] == want["color"]
            rgb = want["color"].lstrip("#")
            triple = tuple(int(rgb[j : j + 2], 16) for j in (0, 2, 4))
            assert (
                light["painted"] == f"rgb({triple[0]}, {triple[1]}, {triple[2]})"
            ), light
        print(f"R6 GATE LIGHTS drawn={len(lights)} per_row=19")
    finally:
        tab.deleteLater()


def test_the_gate_lights_control_no_record_draws_none(qapp) -> None:
    """The control: a row with no gate record draws no lights at all.

    Nineteen grey lights on an unrecorded row would say "evaluated,
    nothing fired". The empty-log fixture is the default here, so this
    also proves the test above was not passing on leftover state.
    """
    tab = _history_tab(qapp, _mixed_rows())
    try:
        count = _eval_in(
            tab._table._web,
            'document.querySelectorAll("#panel-rows .gate-lights .light").length',
        )
        assert count == 0, count
    finally:
        tab.deleteLater()


_RICH_TOOLTIP = "<b>Grade: A</b>\nExcellent \u2014 traded near a local extreme"
_PLAIN_TOOLTIP = "BB-below-upper-detect(bb_pos=0.50<0.88)\n  blocked by  delta"


def _probe_tooltip(page, text: str) -> dict:
    """Render ``text`` the way a hovered cell renders it, and read it."""
    return json.loads(
        page.js(
            "JSON.stringify((function () {"
            "var n = window.acervatorRenderTooltip(" + json.dumps(text) + ");"
            "return {mode: n.getAttribute('data-tooltip-mode'),"
            " text: n.textContent,"
            " bold: n.querySelectorAll('b').length,"
            " tags: n.querySelectorAll('*').length,"
            " html: n.innerHTML,"
            " pwned: String(window.__pwned)};"
            "})())"
        )
    )


def test_a_rich_tooltip_renders_as_markup_not_as_source(page) -> None:
    """Qt renders a tooltip's HTML. A ``title=`` attribute would not.

    The page draws its own tooltip so the markup reaches the operator
    rendered, the way ``setToolTip`` rendered it.
    """
    shown = _probe_tooltip(page, _RICH_TOOLTIP)
    assert shown["mode"] == "rich"
    assert shown["bold"] == 1, shown
    assert "<b>" not in shown["text"], "the markup reached the screen as source"
    assert "Grade: A" in shown["text"]
    assert "Excellent" in shown["text"]


def test_the_real_voting_tooltip_renders_its_spans(page) -> None:
    """The builder's own output, not a literal written for the test."""
    from src.exchange.history_helpers import voting_cell_tooltip

    entry = _voting_entry("bot-aaaa1111", BASE_TS, "BULLISH", 0.42)
    tip = voting_cell_tooltip(entry)
    assert "<span" in tip, "the builder emits no markup; the test is vacuous"
    shown = _probe_tooltip(page, tip)
    assert shown["mode"] == "rich"
    assert "<span" not in shown["text"]
    assert "bull" in shown["text"]
    assert shown["tags"] >= 3, shown


def test_a_plain_tooltip_keeps_its_newlines(page) -> None:
    """A tooltip with no markup is drawn as text, line breaks intact."""
    shown = _probe_tooltip(page, _PLAIN_TOOLTIP)
    assert shown["mode"] == "plain"
    assert shown["tags"] == 0
    assert shown["text"] == _PLAIN_TOOLTIP


def test_the_tooltip_control_source_text_would_be_visible(page) -> None:
    """The control: a tooltip drawn as a ``title`` shows its own markup.

    Without this, a renderer that stripped every tag would also pass the
    rich-text test, and the operator would see nothing at all.
    """
    literal = json.loads(
        page.js(
            "JSON.stringify((function () {"
            "var n = document.createElement('div');"
            "n.setAttribute('title', " + json.dumps(_RICH_TOOLTIP) + ");"
            "return {title: n.getAttribute('title'),"
            " bold: n.querySelectorAll('b').length};"
            "})())"
        )
    )
    assert literal["bold"] == 0
    assert "<b>" in literal["title"], "the control cannot show the defect"


def test_a_tooltip_carrying_a_handler_cannot_run_it(page) -> None:
    """Markup is sanitized into the tooltip; an event handler is dropped.

    Tooltip text is built from gate and voting log records, so it is not
    a literal the author controls.
    """
    hostile = "<b>ok</b><img src=x onerror='window.__pwned=1'>tail"
    shown = _probe_tooltip(page, hostile)
    assert shown["pwned"] == "undefined"
    assert "onerror" not in shown["html"]
    assert "<img" not in shown["html"]
    assert shown["text"] == "oktail"
    assert "<b>ok</b>" in shown["html"], "the allowed markup was stripped too"


def test_a_cell_tooltip_shows_after_the_hover_delay(page) -> None:
    """Hovering a cell puts its tooltip on screen, rendered.

    The delay matches QToolTip's wake time, so the read below polls
    rather than assuming the tooltip is already up.
    """
    import time

    page.push(_model(_mixed_rows()))
    _assert_not_vacuous(page.dom())
    carried = page.js(
        "(function () {"
        "var td = document.querySelector("
        '"#panel-rows tr td[data-col-key=grade]");'
        'td.dispatchEvent(new MouseEvent("mouseover", '
        "{bubbles: true, clientX: 20, clientY: 20}));"
        'return td.getAttribute("data-cell-tooltip");'
        "})()"
    )
    assert carried and "<b>" in carried, "the hovered cell carries no markup"
    deadline = time.time() + 10.0
    state = "hidden"
    while state != "shown" and time.time() < deadline:
        state = page.js(
            'document.getElementById("panel-tooltip").getAttribute("data-state")'
        )
    assert state == "shown", "the tooltip never appeared on hover"
    body = json.loads(
        page.js(
            "JSON.stringify((function () {"
            "var n = document.getElementById('panel-tooltip');"
            "return {mode: n.getAttribute('data-tooltip-mode'),"
            " text: n.textContent, bold: n.querySelectorAll('b').length};"
            "})())"
        )
    )
    assert body["mode"] == "rich", body
    assert body["bold"] >= 1, body
    assert "<b>" not in body["text"]
