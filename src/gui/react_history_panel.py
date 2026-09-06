"""The React History table, drawn inside ``QWebEngineView``.

``HistoryWebTable`` replaces the table widget ``HistoryTab`` used to hold.
``build_view_model`` returns only fields ``history_read_contract`` produced;
no cost, grade or colour is derived here. ``state_push_script`` embeds the
JSON as a bare JS expression and never wraps it in quotes.
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
    # Without Qt, HistoryWebTable is never defined and the import site fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_history")


#: The three files the page is built from. Order is load order.
ASSET_NAMES: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "history_panel.js",
)

STYLE_ASSET = "history_panel.css"

#: ``HistoryTab`` draws its own summary line, filter bar and pager.
TABLE_ONLY_CHROME = {"summary": False, "filters": False, "pager": False}

#: The JS expression that counts the rows the browser actually drew.
ROW_COUNT_JS = 'document.querySelectorAll("#panel-rows tr").length'


class HistoryPanelAssetMissing(RuntimeError):
    """An asset the page cannot be drawn without is not on disk."""


def asset_dir() -> Path:
    """The directory holding the panel's JS and CSS.

    ``__file__`` covers running from source; ``sys._MEIPASS`` covers the
    frozen build, which carries ``src/gui/web`` inside the bundle.
    """
    beside_module = Path(__file__).resolve().parent / "web"
    if beside_module.is_dir():
        return beside_module
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "src" / "gui" / "web"
    return beside_module


def read_asset(name: str) -> str:
    """Return one asset's text, or raise ``HistoryPanelAssetMissing``.

    ``newline=""`` keeps a CRLF checkout from reaching the page.
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
    """The six chrome colours, read from ``CHART_THEMES``.

    An unknown ``theme`` falls back to ``cyberpunk_dark``.
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


def page_html(
    style_assets: tuple,
    script_assets: tuple,
    body: str,
    theme: str = "cyberpunk_dark",
    inline_scripts: tuple = (),
) -> str:
    """One page as a string: styles, ``body``, the assets, then ``inline_scripts``.

    ``parts`` is joined, never ``%``-formatted: the minified bundles named in
    ``ASSET_NAMES`` carry both ``%`` and braces.
    """
    overrides = "".join(f"{k}:{v};" for k, v in _palette(theme).items())
    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<style>",
    ]
    for name in style_assets:
        parts.append(read_asset(name))
    parts.extend(
        [
            ":root{",
            overrides,
            "}",
            "</style></head><body>",
            body,
        ]
    )
    for name in script_assets:
        parts.append("<script>")
        parts.append(read_asset(name))
        parts.append("</script>")
    for source in inline_scripts:
        parts.append("<script>")
        parts.append(source)
        parts.append("</script>")
    parts.append("</body></html>")
    return "\n".join(parts)


def panel_html(theme: str = "cyberpunk_dark") -> str:
    """The whole page as one string, with no network fetch."""
    return page_html((STYLE_ASSET,), ASSET_NAMES, '<div id="root"></div>', theme)


def _date_text(ts: int) -> str:
    """``ts`` as UTC ``YYYY-MM-DD HH:MM``; a ``ts`` of 0 gives ``(any)``."""
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

    A supplied ``filtered`` skips the second ``hrc.apply_filters`` pass, and
    ``gate_index`` and ``voting_index`` keep ``hrc.build_page`` to one log
    read per page.
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
    """The one JS statement pushed into the page.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return "window.acervatorSetState(" + json.dumps(payload, ensure_ascii=True) + ");"


if _HAS_WEBENGINE:

    class HistoryWebTable(QWidget):
        """The History table, hosted in ``QWebEngineView``.

        ``set_model`` pushes one view model, ``model`` returns the last one
        pushed, ``page_ready`` reports the document state, and ``row_count``
        counts the rows the DOM drew.
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
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of ``_last_model``, empty before the first ``set_model``."""
            return dict(self._last_model)

        def set_model(self, model: dict) -> None:
            """Hold ``model`` in ``_last_model`` and push it when ``_page_ready``.

            ``_on_load_finished`` pushes a model handed over before the load.
            """
            self._last_model = model
            if self._page_ready:
                self._push(model)

        def row_count(self, callback: Callable[[Any], None]) -> bool:
            """Run ``ROW_COUNT_JS`` and hand the count to ``callback``.

            Returns False and calls nothing while ``_page_ready`` is False.
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
