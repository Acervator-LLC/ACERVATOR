"""react_history_panel.py — the React History panel. Issue #128 unit R4.

WHAT THIS IS
============
A second renderer for the SAME History data the Qt tab shows, drawn by
React inside the Chromium that PySide6 already ships. The Qt tab is not
touched and both tabs exist after this unit: the old one is the reference
the new one is judged against.

WHAT IT MAY NOT DO
==================
It computes nothing. Every string and every colour on screen is a field
``src.exchange.history_read_contract`` already produced. A panel that
re-derived a cost, a grade or a colour would be the third implementation
of History, which is the defect this migration order exists to prevent.

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
The page has NO path back into Python, so "the panel writes nothing" is
a property of the wiring rather than a claim a test has to keep proving.
The cost is that the page cannot raise its own events, so the Qt control
bar above it owns the filters and the pager. Electron or ``QWebChannel``
would move those controls into the page; neither is in this unit, and
``PySide6.QtWebChannel`` is NOT in the frozen build's hidden imports.

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
from typing import Any, Optional

from src.exchange import history_read_contract as hrc

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    _HAS_WEBENGINE = True
except ImportError:
    # Same form as history_tab.py: no Qt means no widget class, the
    # module still imports, and asking for the widget fails by name at
    # the import site. main_window.py catches that and logs.
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
) -> dict:
    """Everything the page draws, as one JSON-serialisable dict.

    Every field is the contract's answer. This function chooses which of
    the contract's functions to call and in what order; it decides no
    value of its own.
    """
    filtered = hrc.apply_filters(trades, filters)
    rendered = hrc.build_page(filtered, page, bot_manager)
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
        "summary": hrc.summary_line(filtered, len(trades), last_fetched_ts, now_ts),
        "filters": filters.as_dict(),
        "filter_options": hrc.filter_options(trades),
        "loaded": len(trades),
        "from_text": _date_text(filters.from_ts),
        "to_text": _date_text(filters.to_ts),
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

    class ReactHistoryPanel(QWidget):
        """React History, hosted in QWebEngineView.

        Public surface, all of it read-only:
          * set_bot_manager(bot_manager)
          * on_history_refreshed(trades)  -- the HistoryTab signal's slot
          * view_model()                  -- what the last push carried
        """

        def __init__(self, parent=None, theme: str = "cyberpunk_dark") -> None:
            super().__init__(parent)
            self.setAccessibleName("React History Panel")
            self._theme = theme
            self._bot_manager = None
            self._trades: list = []
            # NO DATE FLOOR. `default_filters()` starts at 2026-04-01,
            # which is the Qt tab's date edit and is applied to the FETCH.
            # This panel is handed the result of that fetch, so a second
            # floor here would hide rows the tab shows and make the two
            # renderers disagree for a reason that is not the renderer.
            self._filters = hrc.HistoryFilters()
            self._page = 0
            self._last_fetched_ts: float = 0.0
            self._last_model: dict = {}
            self._page_ready = False
            self._build_ui()

        # -- public ---------------------------------------------------
        def set_bot_manager(self, bot_manager) -> None:
            self._bot_manager = bot_manager

        def on_history_refreshed(self, trades: list) -> None:
            """Take the trade list the Qt HistoryTab just fetched.

            One fetcher for both panels. A second fetch here would double
            the exchange calls and could disagree with the tab this panel
            is measured against.
            """
            self._trades = list(trades or [])
            self._last_fetched_ts = _now()
            self._page = 0
            self._repopulate_combos()
            self.render_now()

        def view_model(self) -> dict:
            """The payload of the most recent push. Empty before the first."""
            return dict(self._last_model)

        # -- construction ---------------------------------------------
        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self._build_controls())

            self._web = QWebEngineView()
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._theme))
            layout.addWidget(self._web, 1)

        def _build_controls(self) -> QWidget:
            """The filter and pager bar.

            These live in Qt, not in the page: the bridge is one-way, so
            the page cannot deliver a click back to Python.
            """
            bar = QWidget(self)
            row = QHBoxLayout(bar)
            row.setContentsMargins(8, 6, 8, 6)
            row.setSpacing(8)

            self._combos: dict = {}
            for key in ("exchange", "symbol", "side"):
                label = QLabel(key.capitalize(), bar)
                combo = QComboBox(bar)
                combo.addItem(hrc.ALL)
                combo.setAccessibleName(f"React History {key} filter")
                combo.currentTextChanged.connect(self._on_filter_changed)
                self._combos[key] = combo
                row.addWidget(label)
                row.addWidget(combo)

            row.addStretch(1)

            self._prev_btn = QPushButton("Prev", bar)
            self._prev_btn.setAccessibleName("React History previous page")
            self._prev_btn.clicked.connect(self._on_prev)
            self._next_btn = QPushButton("Next", bar)
            self._next_btn.setAccessibleName("React History next page")
            self._next_btn.clicked.connect(self._on_next)
            self._page_lbl = QLabel(hrc.page_label(0, 0), bar)
            self._page_lbl.setAlignment(Qt.AlignCenter)
            self._page_lbl.setAccessibleName("React History page label")

            row.addWidget(self._prev_btn)
            row.addWidget(self._page_lbl)
            row.addWidget(self._next_btn)
            return bar

        # -- control-bar handlers -------------------------------------
        def _on_filter_changed(self, _text: str) -> None:
            self._filters = hrc.HistoryFilters(
                from_ts=self._filters.from_ts,
                to_ts=self._filters.to_ts,
                exchange=self._combos["exchange"].currentText(),
                symbol=self._combos["symbol"].currentText(),
                side=self._combos["side"].currentText(),
            )
            self._page = 0
            self.render_now()

        def _on_prev(self) -> None:
            self._page = max(0, self._page - 1)
            self.render_now()

        def _on_next(self) -> None:
            self._page += 1
            self.render_now()

        def _repopulate_combos(self) -> None:
            """Refill the three combos from the contract's option lists."""
            options = hrc.filter_options(self._trades)
            for key, combo in self._combos.items():
                keep = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(options[key])
                index = combo.findText(keep)
                combo.setCurrentIndex(index if index >= 0 else 0)
                combo.blockSignals(False)

        # -- render ---------------------------------------------------
        def render_now(self) -> None:
            """Rebuild the view model and push it. Never writes anything."""
            model = build_view_model(
                self._trades,
                self._filters,
                self._page,
                self._bot_manager,
                self._last_fetched_ts,
            )
            page = model["page"]
            self._page = page["page"]
            self._last_model = model
            self._page_lbl.setText(page["page_label"])
            self._prev_btn.setEnabled(page["prev_enabled"])
            self._next_btn.setEnabled(page["next_enabled"])
            if self._page_ready:
                self._push(model)

        def _push(self, model: dict) -> None:
            self._web.page().runJavaScript(state_push_script(model))

        def _on_load_finished(self, ok: bool) -> None:
            """Push once the document exists; before that there is no
            ``acervatorSetState`` to call."""
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React History page failed to load")
                return
            if self._last_model:
                self._push(self._last_model)
            else:
                self.render_now()


def _now() -> float:
    """Wall clock, one call site, so a test can patch one name."""
    import time

    return time.time()
