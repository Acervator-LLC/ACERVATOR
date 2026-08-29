"""react_history_panel.py — the React History table. Issue #128 units R4, R6.

WHAT THIS IS
============
The History tab's table, drawn by React inside the Chromium that PySide6
already ships. ``HistoryTab`` in ``src/gui/history_tab.py`` embeds it in
place of the ``QTableWidget`` it used to hold. There is ONE History tab
and one renderer.

WHAT IT MAY NOT DO
==================
It computes nothing. Every string, every colour and every gate-light
state on screen is a field ``src.exchange.history_read_contract`` already
produced. A table that re-derived a cost, a grade, a colour or a light
would be the second implementation of History, which is the defect this
migration order exists to prevent.

THE HOSTING MECHANISM, AS MEASURED
==================================
``src/gui/tradingview_chart.py`` already runs HTML/JS inside
``QWebEngineView``, and ``tools/spec_common.py:153`` carries
``PySide6.QtWebEngineWidgets`` as a hidden import while the 10-name
``EXCLUDES`` list holds no Qt web entry. Measured on this machine,
PySide6 6.11.2: ``QtWebEngineProcess.exe`` -- the Chromium subprocess --
is present in the installed wheel. No Electron and no second web host.

THE BRIDGE IS ONE-WAY, AND THAT IS THE WRITE PROOF
==================================================
Python pushes JSON with ``QWebEnginePage.runJavaScript``. That is the
only bridge ``tradingview_chart.py`` uses and the only one used here.
The page has NO path back into Python, so "the table writes nothing" is
a property of the wiring rather than a claim a test has to keep proving.
The cost is that the page cannot raise its own events, so the Qt controls
in ``HistoryTab`` -- Refresh, Apply, Reset, the two date edits, the three
combos, Prev, Next and Export CSV -- stay Qt widgets. Electron or
``QWebChannel`` would move those into the page; neither is in this unit,
and ``PySide6.QtWebChannel`` is NOT in the frozen build's hidden imports.

Reads run the same way and are therefore ASYNCHRONOUS: ``row_count``
answers through a callback. Nothing here spins a nested event loop, which
on the GUI thread would re-enter the render it was called from.

NOT THE ``tradingview_chart.py`` INJECTION SHAPE
================================================
That file builds ``f"setCandles('{json.dumps(x)}')"``: JSON inside a
single-quoted JS string. ``json.dumps`` does not escape ``'``, so one
apostrophe in the data ends the string and the rest executes. History
cells carry free-text tooltips, so this module embeds the JSON as a bare
JS expression instead and never wraps it in quotes. Named, not fixed --
that call site belongs to its own file.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.exchange import history_read_contract as hrc

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Same form as history_tab.py: no Qt means no widget class, the
    # module still imports, and asking for the widget fails by name at
    # the import site. history_tab.py catches that and logs.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_history")


# --------------------------------------------------------------------- #
# Assets                                                                 #
# --------------------------------------------------------------------- #

#: The three files the page is built from. Order is load order.
ASSET_NAMES: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "history_panel.js",
)

STYLE_ASSET = "history_panel.css"

#: The chrome the page draws for a client that asks for none of it.
#: ``HistoryTab`` owns its own summary line, filter bar and pager.
TABLE_ONLY_CHROME = {"summary": False, "filters": False, "pager": False}

#: The JS expression that counts the rows the browser actually drew.
ROW_COUNT_JS = 'document.querySelectorAll("#panel-rows tr").length'


class HistoryPanelAssetMissing(RuntimeError):
    """An asset the page cannot be drawn without is not on disk."""


def asset_dir() -> Path:
    """The directory holding the panel's JS and CSS.

    Two candidates, in order. ``__file__`` covers running from source.
    ``sys._MEIPASS`` covers the frozen build, where
    ``tools/spec_common.py:datas_candidates`` ships the whole ``src``
    directory to ``<bundle>/src``. NOT MEASURED against a real build --
    no build was run for this unit.
    """
    beside_module = Path(__file__).resolve().parent / "web"
    if beside_module.is_dir():
        return beside_module
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "src" / "gui" / "web"
    return beside_module


def read_asset(name: str) -> str:
    """Return one asset's text, or raise naming the path that is missing.

    Reads as UTF-8 with newline translation off, so a CRLF checkout of a
    ``.js`` file cannot put a stray carriage return into the page.
    """
    path = asset_dir() / name
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise HistoryPanelAssetMissing(
            f"History panel asset not readable: {path} ({type(exc).__name__})"
        ) from exc


def _palette(theme: str) -> dict:
    """The six chrome colours, taken from the chart's theme table.

    Imported rather than restated: a second copy of the palette drifts
    from the first the next time a theme changes.
    """
    from .tradingview_chart import CHART_THEMES

    colors = CHART_THEMES.get(theme) or CHART_THEMES["cyberpunk_dark"]
    return {
        "--bg": colors["bg"],
        "--text": colors["text"],
        "--grid": colors["grid"],
        "--border": colors["border"],
        "--accent": colors["accent"],
        "--btn-bg": colors["btn_bg"],
    }


def panel_html(theme: str = "cyberpunk_dark") -> str:
    """The whole page, self-contained: no network fetch, no CDN.

    Built by joining, never by ``%`` or ``str.format``: the minified
    React bundle carries both ``%`` and braces, and either would raise.
    """
    overrides = "".join(f"{k}:{v};" for k, v in _palette(theme).items())
    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<style>",
        read_asset(STYLE_ASSET),
        ":root{",
        overrides,
        "}",
        "</style></head><body>",
        '<div id="root"></div>',
    ]
    for name in ASSET_NAMES:
        parts.append("<script>")
        parts.append(read_asset(name))
        parts.append("</script>")
    parts.append("</body></html>")
    return "\n".join(parts)


# --------------------------------------------------------------------- #
# The view model -- pure, no Qt, no browser                              #
# --------------------------------------------------------------------- #


def _date_text(ts: int) -> str:
    """A filter bound as text. 0 means the bound is inactive."""
    if ts <= 0:
        return "(any)"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def build_view_model(
    trades: list,
    filters: Any,
    page: int = 0,
    bot_manager: Any = None,
    last_fetched_ts: float = 0.0,
    now_ts: Optional[float] = None,
    filtered: Optional[list] = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
    chrome: Optional[dict] = None,
) -> dict:
    """Everything the page draws, as one JSON-serialisable dict.

    Every field is the contract's answer. This function chooses which of
    the contract's functions to call and in what order; it decides no
    value of its own.

    ``filtered`` is the retained set when the caller has already applied
    the filters and counted the result. Supplying it skips a second
    filter pass over the same rows; the contract's own pass runs when it
    is omitted.

    ``gate_index`` and ``voting_index`` are the caller's per-page join
    indexes. Supplying them keeps the log read to one per page.
    """
    retained = hrc.apply_filters(trades, filters) if filtered is None else filtered
    rendered = hrc.build_page(retained, page, bot_manager, gate_index, voting_index)
    return {
        "columns": [
            {
                "index": c.index,
                "key": c.key,
                "header": c.header,
                "header_tooltip": c.header_tooltip,
            }
            for c in hrc.COLUMNS
        ],
        "page": rendered.as_dict(),
        "summary": hrc.summary_line(retained, len(trades), last_fetched_ts, now_ts),
        "filters": filters.as_dict(),
        "filter_options": hrc.filter_options(trades),
        "loaded": len(trades),
        "from_text": _date_text(filters.from_ts),
        "to_text": _date_text(filters.to_ts),
        "chrome": dict(chrome) if chrome else {},
    }


def state_push_script(payload: dict) -> str:
    """The one JS statement the bridge sends.

    ``ensure_ascii=True`` escapes every non-ASCII code point, U+2028 and
    U+2029 among them. Those two are legal inside a JSON string and are
    line terminators in JavaScript, so leaving them raw would end the
    statement mid-value.
    """
    return "window.acervatorSetState(" + json.dumps(payload, ensure_ascii=True) + ");"


# --------------------------------------------------------------------- #
# The Qt host                                                            #
# --------------------------------------------------------------------- #

if _HAS_WEBENGINE:

    class HistoryWebTable(QWidget):
        """The History table, hosted in QWebEngineView.

        Public surface, all of it read-only:
          * set_model(model)      -- push one view model to the page
          * page_ready            -- True once the document has loaded
          * model()               -- what the last push carried
          * row_count(callback)   -- the DOM's own row count, async
        """

        def __init__(self, parent=None, theme: str = "cyberpunk_dark") -> None:
            super().__init__(parent)
            self.setAccessibleName("React History Table")
            self._last_model: dict = {}
            self._page_ready = False
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView()
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(theme))
            layout.addWidget(self._web, 1)

        # -- public ---------------------------------------------------
        @property
        def page_ready(self) -> bool:
            """True once the document exists and can be pushed to."""
            return self._page_ready

        def model(self) -> dict:
            """The payload of the most recent push. Empty before the first."""
            return dict(self._last_model)

        def set_model(self, model: dict) -> None:
            """Hold the model and push it if the document is up.

            A model handed over before ``loadFinished`` is pushed by the
            load handler instead, so nothing is dropped on the way in.
            """
            self._last_model = model
            if self._page_ready:
                self._push(model)

        def row_count(self, callback: Callable[[Any], None]) -> bool:
            """Ask the DOM how many rows it drew. Answers through
            ``callback``.

            Returns False and calls nothing when the document is not up:
            no rows are on screen and there is nothing to count. The
            caller decides what an unread count means.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(ROW_COUNT_JS, callback)
            return True

        # -- internals ------------------------------------------------
        def _push(self, model: dict) -> None:
            self._web.page().runJavaScript(state_push_script(model))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React History page failed to load")
                return
            if self._last_model:
                self._push(self._last_model)
