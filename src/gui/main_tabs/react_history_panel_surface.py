"""react_history_panel_surface.py -- the React History table, without Qt.

Describes the History tab's table: the page it builds from disk, the
palette it paints that page in, the one statement it pushes into the
page, and the view model that statement carries. The shipped table hosts
a browser inside a Qt widget, so nothing the operator reads is painted
by Qt; every value below is the whole of what reaches the screen.

``HistoryPanelModel`` holds the host's state. ``set_model`` keeps one
view model and pushes it when the page is up. ``row_count`` asks the page
how many rows it drew. ``_on_load_finished`` records whether the page
came up and pushes anything held while it was down. ``panel_html``
builds the page, ``palette`` picks its six chrome colours, and
``state_push_script`` writes the one statement the host sends.

``build_view_model`` is the contract's answer and nothing else: it
chooses which ``src.exchange.history_read_contract`` functions to call
and in what order, and derives no value of its own.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``react_history_panel.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.react_history_panel`` or from the chart's theme
table, so a value changed on one side alone is reported. Nothing here
imports Qt.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.exchange import history_read_contract as hrc

METHOD = "react_history_panel.state"

ACCESSIBLE_NAME = "React History Table"
LOGGER_NAME = "acervator.gui.react_history"

ASSET_NAMES: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "history_panel.js",
)
STYLE_ASSET = "history_panel.css"
ASSET_SUBDIR = "web"
ASSET_ENCODING = "utf-8"
ASSET_NEWLINE = ""
ASSET_READ_MODE = "r"
BUNDLE_ATTR = "_MEIPASS"
BUNDLE_PARTS: tuple[str, ...] = ("src", "gui", "web")
ASSET_ERROR_FORMAT = "History panel asset not readable: {path} ({error})"

TABLE_ONLY_CHROME = {"summary": False, "filters": False, "pager": False}
ROW_COUNT_JS = 'document.querySelectorAll("#panel-rows tr").length'

DEFAULT_THEME = "cyberpunk_dark"

THEME_CHROME = {
    "cyberpunk_dark": {
        "bg": "#0a0a0f",
        "text": "#e0e0f0",
        "grid": "#1a1a28",
        "border": "#2a2a44",
        "accent": "#00ffcc",
        "btn_bg": "#12121a",
    },
    "neon_light": {
        "bg": "#f5f5fa",
        "text": "#1a1a2e",
        "grid": "#e5e5f0",
        "border": "#ccccdd",
        "accent": "#6600cc",
        "btn_bg": "#eeeef5",
    },
    "classic_terminal": {
        "bg": "#0a0a0a",
        "text": "#00ff00",
        "grid": "#181818",
        "border": "#003300",
        "accent": "#00ff00",
        "btn_bg": "#111111",
    },
    "minimal_modern": {
        "bg": "#fafafa",
        "text": "#1a1a1a",
        "grid": "#e8e8e8",
        "border": "#e0e0e0",
        "accent": "#2563eb",
        "btn_bg": "#f0f0f0",
    },
    "glass_metal": {
        "bg": "#1c1c24",
        "text": "#d0d0e0",
        "grid": "#2c2c3a",
        "border": "#3a3a50",
        "accent": "#88ccff",
        "btn_bg": "#242430",
    },
}

THEME_NAMES: tuple[str, ...] = (
    "cyberpunk_dark",
    "neon_light",
    "classic_terminal",
    "minimal_modern",
    "glass_metal",
)

PALETTE_KEYS: tuple[str, ...] = (
    "--bg",
    "--text",
    "--grid",
    "--border",
    "--accent",
    "--btn-bg",
)
PALETTE_SOURCE_KEYS: tuple[str, ...] = (
    "bg",
    "text",
    "grid",
    "border",
    "accent",
    "btn_bg",
)

HTML_DOCTYPE = "<!DOCTYPE html>"
HTML_HEAD_OPEN = '<html><head><meta charset="utf-8">'
HTML_STYLE_OPEN = "<style>"
HTML_ROOT_OPEN = ":root{"
HTML_ROOT_CLOSE = "}"
HTML_STYLE_CLOSE = "</style></head><body>"
HTML_ROOT_DIV = '<div id="root"></div>'
HTML_SCRIPT_OPEN = "<script>"
HTML_SCRIPT_CLOSE = "</script>"
HTML_TAIL = "</body></html>"
HTML_JOIN = "\n"
OVERRIDE_FORMAT = "{key}:{value};"
OVERRIDE_JOIN = ""

DATE_FORMAT = "%Y-%m-%d %H:%M"
DATE_ANY_TEXT = "(any)"
DATE_INACTIVE_MAX = 0

PUSH_FUNCTION = "window.acervatorSetState"
PUSH_PREFIX = "window.acervatorSetState("
PUSH_SUFFIX = ");"
PUSH_ENSURE_ASCII = True

PANEL_KIND = "QWidget"
WEB_KIND = "QWebEngineView"
LAYOUT_KIND = "QVBoxLayout"
CONTENT_MARGINS: tuple[int, int, int, int] = (0, 0, 0, 0)
CONTENT_SPACING = 0
WEB_STRETCH = 1
PANEL_STYLE_SHEET = ""

DEFAULT_PAGE = 0
DEFAULT_LAST_FETCHED_TS = 0.0
NO_CHROME: dict = {}

LOAD_FAILED_MESSAGE = "React History page failed to load"
LOAD_FAILED_LEVEL = "WARNING"

NO_PATH = ""

SET_MODEL_PATH_HELD = "held"
SET_MODEL_PATH_PUSHED = "pushed"
SET_MODEL_PATHS: tuple[str, ...] = (SET_MODEL_PATH_HELD, SET_MODEL_PATH_PUSHED)

ROW_COUNT_PATH_REFUSED = "refused"
ROW_COUNT_PATH_ASKED = "asked"
ROW_COUNT_PATHS: tuple[str, ...] = (ROW_COUNT_PATH_REFUSED, ROW_COUNT_PATH_ASKED)

LOAD_PATH_FAILED = "failed"
LOAD_PATH_READY = "ready"
LOAD_PATH_PUSHED = "pushed"
LOAD_PATHS: tuple[str, ...] = (LOAD_PATH_FAILED, LOAD_PATH_READY, LOAD_PATH_PUSHED)

BUILD_START = "build.start"
BUILD_HTML = "build.html"
BUILD_RETURN = "build.return"
SET_MODEL_START = "set_model.start"
SET_MODEL_RETURN = "set_model.return"
ROW_COUNT_START = "row_count.start"
ROW_COUNT_ASK = "row_count.ask"
ROW_COUNT_RETURN = "row_count.return"
LOAD_START = "load.start"
LOAD_LOGGED = "load.logged"
LOAD_RETURN = "load.return"
PUSH_CALL = "push"

ACTIONS = {"web.loadFinished": "_on_load_finished"}

BRIDGE_ACTIONS: tuple[str, ...] = (
    "set_model",
    "row_count",
    "load_finished",
)

TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
SKIN: dict[str, str] = {}


def widget(name: str, kind: str, parent: str, **values: Any) -> dict:
    """One node of the host's widget tree, with its parent and its values."""
    return {"name": name, "kind": kind, "parent": parent, **values}


WIDGETS = (
    widget(
        "panel",
        PANEL_KIND,
        "",
        accessible_name=ACCESSIBLE_NAME,
        layout=LAYOUT_KIND,
        margins=CONTENT_MARGINS,
        spacing=CONTENT_SPACING,
        style_sheet=PANEL_STYLE_SHEET,
    ),
    widget(
        "web",
        WEB_KIND,
        "panel",
        stretch=WEB_STRETCH,
    ),
)

WIDGET_NAMES: tuple[str, ...] = tuple(node["name"] for node in WIDGETS)
WIDGET_KINDS = {node["name"]: node["kind"] for node in WIDGETS}
WIDGET_PARENTS = {node["name"]: node["parent"] for node in WIDGETS}
WIDGET_CHILDREN = {
    parent: tuple(node["name"] for node in WIDGETS if node["parent"] == parent)
    for parent in dict.fromkeys(node["parent"] for node in WIDGETS)
}
WIDGET_INDEX = {
    node["name"]: WIDGET_CHILDREN[node["parent"]].index(node["name"])
    for node in WIDGETS
}
BUTTON_NAMES: tuple[str, ...] = ()
BUTTONS_ENABLED: dict[str, bool] = {}


class HistoryPanelAssetMissing(RuntimeError):
    """An asset the page cannot be drawn without is not on disk."""


def asset_dir() -> Path:
    """The directory holding the panel's JS and CSS.

    Two candidates, in order. The directory beside the GUI package covers
    running from source. ``sys._MEIPASS`` covers the frozen build, where
    the whole ``src`` directory is shipped to ``<bundle>/src``.
    """
    beside_package = Path(__file__).resolve().parents[1] / ASSET_SUBDIR
    if beside_package.is_dir():
        return beside_package
    bundle = getattr(sys, BUNDLE_ATTR, None)
    if bundle:
        return Path(bundle).joinpath(*BUNDLE_PARTS)
    return beside_package


def read_asset(name: str) -> str:
    """Return one asset's text, or raise naming the path that is missing.

    Reads as UTF-8 with newline translation off, so a CRLF checkout of a
    ``.js`` file cannot put a stray carriage return into the page.
    """
    path = asset_dir() / name
    try:
        with open(
            path, ASSET_READ_MODE, encoding=ASSET_ENCODING, newline=ASSET_NEWLINE
        ) as handle:
            return handle.read()
    except OSError as exc:
        raise HistoryPanelAssetMissing(
            ASSET_ERROR_FORMAT.format(path=path, error=type(exc).__name__)
        ) from exc


def palette(theme: str) -> dict:
    """The six chrome colours one theme paints the page in.

    A theme the table does not carry falls back to the default theme.
    """
    colors = THEME_CHROME.get(theme) or THEME_CHROME[DEFAULT_THEME]
    return {
        key: colors[source] for key, source in zip(PALETTE_KEYS, PALETTE_SOURCE_KEYS)
    }


def page_html(
    style_assets: tuple,
    script_assets: tuple,
    body: str,
    theme: str = DEFAULT_THEME,
    inline_scripts: tuple = (),
) -> str:
    """One page, self-contained: no network fetch, no CDN.

    Built by joining, never by ``%`` or ``str.format``: the minified
    React bundle carries both ``%`` and braces, and either would raise.
    """
    overrides = OVERRIDE_JOIN.join(
        OVERRIDE_FORMAT.format(key=key, value=value)
        for key, value in palette(theme).items()
    )
    parts = [HTML_DOCTYPE, HTML_HEAD_OPEN, HTML_STYLE_OPEN]
    for name in style_assets:
        parts.append(read_asset(name))
    parts.extend([HTML_ROOT_OPEN, overrides, HTML_ROOT_CLOSE, HTML_STYLE_CLOSE, body])
    for name in script_assets:
        parts.append(HTML_SCRIPT_OPEN)
        parts.append(read_asset(name))
        parts.append(HTML_SCRIPT_CLOSE)
    for source in inline_scripts:
        parts.append(HTML_SCRIPT_OPEN)
        parts.append(source)
        parts.append(HTML_SCRIPT_CLOSE)
    parts.append(HTML_TAIL)
    return HTML_JOIN.join(parts)


def panel_html(theme: str = DEFAULT_THEME) -> str:
    """The whole page, self-contained: no network fetch, no CDN."""
    return page_html((STYLE_ASSET,), ASSET_NAMES, HTML_ROOT_DIV, theme)


def date_text(ts: int) -> str:
    """A filter bound as text. 0 means the bound is inactive."""
    if ts <= DATE_INACTIVE_MAX:
        return DATE_ANY_TEXT
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(DATE_FORMAT)


def build_view_model(
    trades: list,
    filters: Any,
    page: int = DEFAULT_PAGE,
    bot_manager: Any = None,
    last_fetched_ts: float = DEFAULT_LAST_FETCHED_TS,
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
        "from_text": date_text(filters.from_ts),
        "to_text": date_text(filters.to_ts),
        "chrome": dict(chrome) if chrome else dict(NO_CHROME),
    }


def state_push_script(payload: dict) -> str:
    """The one JS statement the host sends into the page.

    ``ensure_ascii=True`` escapes every non-ASCII code point, U+2028 and
    U+2029 among them. Those two are legal inside a JSON string and are
    line terminators in JavaScript, so leaving them raw would end the
    statement mid-value.
    """
    encoded = json.dumps(payload, ensure_ascii=PUSH_ENSURE_ASCII)
    return PUSH_PREFIX + encoded + PUSH_SUFFIX


class HistoryPanelModel:
    """The History table's host: its page, its state, and its three paths.

    ``set_model`` keeps one view model and pushes it when the page is up.
    ``row_count`` asks the page for the row count it drew.
    ``_on_load_finished`` records whether the page came up. Every step is
    appended to ``calls`` in the order the shipped host makes it, every
    pushed statement to ``pushes``, every read script to ``scripts``, and
    every log line to ``logs``.
    """

    def __init__(self, parent: Any = None, theme: str = DEFAULT_THEME) -> None:
        self.calls: list = []
        self.calls.append([BUILD_START, theme])
        self.parent = parent
        self.theme = theme
        self.accessible_name = ACCESSIBLE_NAME
        self.margins = CONTENT_MARGINS
        self.spacing = CONTENT_SPACING
        self.stretch = WEB_STRETCH
        self.connected = dict(ACTIONS)
        self._last_model: dict = {}
        self._page_ready = False
        self.pushes: list = []
        self.scripts: list = []
        self.callbacks: list = []
        self.logs: list = []
        self.set_model_path = NO_PATH
        self.row_count_path = NO_PATH
        self.load_path = NO_PATH
        self.html = panel_html(theme)
        self.calls.append([BUILD_HTML, len(self.html)])
        self.calls.append([BUILD_RETURN, len(WIDGETS)])

    @property
    def page_ready(self) -> bool:
        """True once the document exists and can be pushed to."""
        return self._page_ready

    def model(self) -> dict:
        """The payload of the most recent push. Empty before the first."""
        return dict(self._last_model)

    def set_model(self, model: dict) -> dict:
        """Hold the model and push it if the document is up.

        A model handed over before the page loads is pushed by the load
        handler instead, so nothing is dropped on the way in.
        """
        self.calls.append([SET_MODEL_START, self._page_ready])
        self._last_model = model
        if self._page_ready:
            self._push(model)
            return self._set_model_finish(SET_MODEL_PATH_PUSHED)
        return self._set_model_finish(SET_MODEL_PATH_HELD)

    def _set_model_finish(self, path: str) -> dict:
        """Keep the push path and report how many statements were sent."""
        self.set_model_path = path
        answer = {"path": path, "pushes": len(self.pushes)}
        self.calls.append([SET_MODEL_RETURN, path, len(self.pushes)])
        return answer

    def row_count(self, callback: Callable[[Any], None]) -> bool:
        """Ask the page how many rows it drew. Answers through ``callback``.

        Returns False and asks nothing when the document is not up: no
        rows are on screen and there is nothing to count. The caller
        decides what an unread count means.
        """
        self.calls.append([ROW_COUNT_START, self._page_ready])
        if not self._page_ready:
            self._row_count_finish(ROW_COUNT_PATH_REFUSED)
            return False
        self.scripts.append(ROW_COUNT_JS)
        self.callbacks.append(callback)
        self.calls.append([ROW_COUNT_ASK, ROW_COUNT_JS, callable(callback)])
        self._row_count_finish(ROW_COUNT_PATH_ASKED)
        return True

    def _row_count_finish(self, path: str) -> dict:
        """Keep the row-count path and report how many reads were asked."""
        self.row_count_path = path
        answer = {"path": path, "scripts": len(self.scripts)}
        self.calls.append([ROW_COUNT_RETURN, path, len(self.scripts)])
        return answer

    def _push(self, model: dict) -> None:
        """Send one view model into the page as one JS statement."""
        statement = state_push_script(model)
        self.pushes.append(statement)
        self.calls.append([PUSH_CALL, len(statement)])

    def _on_load_finished(self, ok: bool) -> dict:
        """Record whether the page came up and push anything held."""
        self.calls.append([LOAD_START, bool(ok)])
        self._page_ready = bool(ok)
        if not ok:
            self.logs.append([LOAD_FAILED_LEVEL, LOAD_FAILED_MESSAGE])
            self.calls.append([LOAD_LOGGED, LOAD_FAILED_MESSAGE])
            return self._load_finish(LOAD_PATH_FAILED)
        if self._last_model:
            self._push(self._last_model)
            return self._load_finish(LOAD_PATH_PUSHED)
        return self._load_finish(LOAD_PATH_READY)

    def _load_finish(self, path: str) -> dict:
        """Keep the load path and report the state the page is left in."""
        self.load_path = path
        answer = {"path": path, "page_ready": self._page_ready}
        self.calls.append([LOAD_RETURN, path, self._page_ready])
        return answer


PANEL_MODEL = HistoryPanelModel()


def build_filters(spec: Optional[dict]) -> Any:
    """The contract's filters built from a request's plain values."""
    supplied = spec or {}
    known = {
        key: supplied[key] for key in hrc.HistoryFilters().as_dict() if key in supplied
    }
    return hrc.HistoryFilters(**known)


def build_payload(
    model: HistoryPanelModel,
    request: Optional[dict] = None,
    action: str = "",
) -> dict:
    """Return the whole host state as one serialisable dict."""
    asked = request or {}
    view: Optional[dict] = None
    if "trades" in asked or "filters" in asked:
        view = build_view_model(
            asked.get("trades") or [],
            build_filters(asked.get("filters")),
            page=int(asked.get("page") or DEFAULT_PAGE),
            last_fetched_ts=float(
                asked.get("last_fetched_ts") or DEFAULT_LAST_FETCHED_TS
            ),
            now_ts=asked.get("now_ts"),
            chrome=asked.get("chrome"),
        )
    if action == "set_model":
        model.set_model(view if view is not None else dict(asked.get("model") or {}))
    elif action == "row_count":
        model.row_count(len)
    elif action == "load_finished":
        model._on_load_finished(bool(asked.get("ok", True)))
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "logger_name": LOGGER_NAME,
        "widgets": [dict(node) for node in WIDGETS],
        "widget_names": list(WIDGET_NAMES),
        "widget_kinds": dict(WIDGET_KINDS),
        "widget_parents": dict(WIDGET_PARENTS),
        "widget_children": {
            parent: list(names) for parent, names in WIDGET_CHILDREN.items()
        },
        "widget_index": dict(WIDGET_INDEX),
        "button_names": list(BUTTON_NAMES),
        "buttons_enabled": dict(BUTTONS_ENABLED),
        "panel_kind": PANEL_KIND,
        "web_kind": WEB_KIND,
        "layout_kind": LAYOUT_KIND,
        "content_margins": list(CONTENT_MARGINS),
        "content_spacing": CONTENT_SPACING,
        "web_stretch": WEB_STRETCH,
        "panel_style_sheet": PANEL_STYLE_SHEET,
        "asset_names": list(ASSET_NAMES),
        "style_asset": STYLE_ASSET,
        "asset_subdir": ASSET_SUBDIR,
        "asset_encoding": ASSET_ENCODING,
        "asset_newline": ASSET_NEWLINE,
        "asset_read_mode": ASSET_READ_MODE,
        "bundle_attr": BUNDLE_ATTR,
        "bundle_parts": list(BUNDLE_PARTS),
        "asset_error_format": ASSET_ERROR_FORMAT,
        "asset_dir": str(asset_dir()),
        "table_only_chrome": dict(TABLE_ONLY_CHROME),
        "row_count_js": ROW_COUNT_JS,
        "default_theme": DEFAULT_THEME,
        "theme_names": list(THEME_NAMES),
        "theme_chrome": {name: dict(colors) for name, colors in THEME_CHROME.items()},
        "palette_keys": list(PALETTE_KEYS),
        "palette_source_keys": list(PALETTE_SOURCE_KEYS),
        "palette": palette(model.theme),
        "html_parts": [
            HTML_DOCTYPE,
            HTML_HEAD_OPEN,
            HTML_STYLE_OPEN,
            HTML_ROOT_OPEN,
            HTML_ROOT_CLOSE,
            HTML_STYLE_CLOSE,
            HTML_ROOT_DIV,
            HTML_SCRIPT_OPEN,
            HTML_SCRIPT_CLOSE,
            HTML_TAIL,
        ],
        "html_join": HTML_JOIN,
        "override_format": OVERRIDE_FORMAT,
        "override_join": OVERRIDE_JOIN,
        "html_length": len(model.html),
        "date_format": DATE_FORMAT,
        "date_any_text": DATE_ANY_TEXT,
        "date_inactive_max": DATE_INACTIVE_MAX,
        "push_function": PUSH_FUNCTION,
        "push_prefix": PUSH_PREFIX,
        "push_suffix": PUSH_SUFFIX,
        "push_ensure_ascii": PUSH_ENSURE_ASCII,
        "default_page": DEFAULT_PAGE,
        "default_last_fetched_ts": DEFAULT_LAST_FETCHED_TS,
        "no_chrome": dict(NO_CHROME),
        "load_failed_message": LOAD_FAILED_MESSAGE,
        "load_failed_level": LOAD_FAILED_LEVEL,
        "no_path": NO_PATH,
        "set_model_paths": list(SET_MODEL_PATHS),
        "row_count_paths": list(ROW_COUNT_PATHS),
        "load_paths": list(LOAD_PATHS),
        "call_names": [
            BUILD_START,
            BUILD_HTML,
            BUILD_RETURN,
            SET_MODEL_START,
            SET_MODEL_RETURN,
            ROW_COUNT_START,
            ROW_COUNT_ASK,
            ROW_COUNT_RETURN,
            LOAD_START,
            LOAD_LOGGED,
            LOAD_RETURN,
            PUSH_CALL,
        ],
        "actions": dict(ACTIONS),
        "bridge_actions": list(BRIDGE_ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
        "theme": model.theme,
        "page_ready": model.page_ready,
        "state": model.model(),
        "view": view,
        "pushes": list(model.pushes),
        "scripts": list(model.scripts),
        "callback_count": len(model.callbacks),
        "logs": [list(line) for line in model.logs],
        "set_model_path": model.set_model_path,
        "row_count_path": model.row_count_path,
        "load_path": model.load_path,
        "has_parent": model.parent is not None,
        "connected": dict(model.connected),
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``react_history_panel.state``.

    Reads ``reset``, ``theme``, ``action`` and the view-model request
    values from the request parameters. The host keeps the page it built
    and the model it holds between calls, so the model persists;
    ``reset`` is what a fresh open sends.
    """
    global PANEL_MODEL
    if params.get("reset", False):
        PANEL_MODEL = HistoryPanelModel(theme=params.get("theme") or DEFAULT_THEME)
    return build_payload(PANEL_MODEL, params, params.get("action", ""))
