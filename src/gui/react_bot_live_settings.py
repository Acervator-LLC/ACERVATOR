# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole Live Bot Settings window drawn by React inside ``QWebEngineView``.

``BotLiveSettingsReactDialog`` replaces every Qt control
``BotLiveSettingsDialog._setup_ui`` builds and inherits ``_mark_changed``,
``_apply_changes``, ``_navigate_to_sibling`` and ``active_tab_index``
unchanged, so an edit reaches the bot by the same route. ``TAB_PLAN`` names
the module, the surface model and the page space each tab draws into.
``BotLiveSettingsPage`` carries the page's edits and presses back to
``apply_edit`` and ``run_action``.
"""

from __future__ import annotations

import json
import logging
from functools import partial
from typing import Any

from .main_tabs import bot_live_settings_surface as surface
from .main_tabs import fold_chrome_surface
from .main_tabs import fold_tranches_tab_surface as fold_surface
from .main_tabs import live_settings_tab_surface as settings_surface
from .main_tabs import phantom_bots_tab_surface as phantom_surface
from .react_history_panel import page_html

try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the dialog is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_bot_live_settings")

EDIT_PREFIX = "acervator-edit:"
ACTION_PREFIX = "acervator-act:"

#: The element ``bot_live_settings.js`` draws the whole window into.
WINDOW_ROOT_ID = "window-root"

ACCESSIBLE_NAME = "React Bot Live Settings"

#: One tab: its name, its page space, its renderer global and its surface module.
TAB_PLAN: tuple = (
    ("Status", "status-page", "acervatorLiveStatus", "live_status_tab_surface"),
    (
        "Settings",
        "settings-page",
        "acervatorLiveSettingsTab",
        "live_settings_tab_surface",
    ),
    (
        "Fold Tranches",
        "fold-tranches-page",
        "acervatorFoldTranchesTab",
        "fold_tranches_tab_surface",
    ),
    (
        "Stack Tranches",
        "stack-tranches-page",
        "acervatorStackTranchesTab",
        "stack_tranches_tab_surface",
    ),
    (
        "Bot Swarm",
        "bot-swarm-page",
        "acervatorBotSwarmSettingsTab",
        "bot_swarm_tab_surface",
    ),
    (
        "Market Inspector",
        "market-inspector-page",
        "acervatorInspectorTab",
        "market_inspector_tab_surface",
    ),
    (
        "Phantom Bots",
        "phantom-bots-page",
        "acervatorPhantomBotsTab",
        "phantom_bots_tab_surface",
    ),
    (
        "Positions Held",
        "positions-held-page",
        "acervatorPositionsHeld",
        "positions_held_surface",
    ),
)

#: The page space the Settings tab draws into, read off ``TAB_PLAN``.
SETTINGS_SPACE = next(
    part for name, part, _api, _module in TAB_PLAN if name == "Settings"
)

#: The TA Timeframe row's reading, which records through ``_ta_timeframe_picked``.
TIMEFRAME_READING = settings_surface.TIMEFRAME_READING

#: What the log says when the page sends a figure its box could not hold.
EDIT_REFUSED_LOG = "Live settings page sent %s=%r, which that box cannot hold"

#: The model class each surface module builds its payload from.
MODEL_BY_SURFACE: dict[str, str] = {
    "live_status_tab_surface": "LiveStatusTabModel",
    "live_settings_tab_surface": "LiveSettingsTabModel",
    "fold_tranches_tab_surface": "FoldTranchesTabModel",
    "stack_tranches_tab_surface": "StackTranchesTabModel",
    "bot_swarm_tab_surface": "BotSwarmTabModel",
    "market_inspector_tab_surface": "MarketInspectorTabModel",
    "phantom_bots_tab_surface": "PhantomBotsTabModel",
    "positions_held_surface": "PositionsHeldTabModel",
}

#: The style sheet the page carries.
WINDOW_STYLE_ASSETS: tuple[str, ...] = ("bot_live_settings.css",)

#: The scripts the page carries. Order is load order.
WINDOW_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    # Owns the Qt style-sheet parser every part of this window skins from.
    "header_strip.js",
    "fold_tokens.js",
    "fold_chrome.js",
    "live_status_tab.js",
    "live_settings_tab.js",
    "fold_tranches_tab.js",
    "stack_tranches_tab.js",
    "bot_swarm_settings_tab.js",
    "market_inspector_tab.js",
    "phantom_bots_tab.js",
    "positions_held.js",
    "bot_live_settings.js",
)

WINDOW_BODY = f'<div id="{WINDOW_ROOT_ID}"></div>'

#: The count of tab pages the window drew, read back off the page.
PAGE_COUNT_JS = "document.querySelectorAll('[data-part$=\"-page\"]').length"

#: The payload keys ``bot_live_settings.js`` draws the pending-change line from.
CHANGE_LABEL_KEY = "change_label"
CHANGE_STYLE_KEY = "change_style"

#: The payload key holding the box a press raised, and the part that answers it.
PRESS_BOX_KEY = "press_box"
BOX_BUTTON = "press-box-button"

#: The key a payload carries when its tab could not be built from the bot.
FAULT_KEY = "tab_fault"

#: What a page shows in place of a tab its surface refused.
FAULT_TEXT = "{tab} is unavailable for this bot: {reason}"

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function () {
      return Promise.resolve(null);
    }
  };

  var ROOT = "%(root)s";
  var PLAN = %(plan)s;
  var PRESS_INPUT = '[data-part="press-box-input"]';
  var PAGE_NODE = '[data-part$="-page"]';
  var typedFilter = "";

  function act(fields) {
    console.log("%(act)s" + JSON.stringify(fields));
  }

  // The page calls that carry a press no button click reports.
  var HANDLERS = {
    "fold-tranches-page": {
      onPick: function (order) {
        act({ key: "fold-order", value: order });
      },
      onType: function (needle) {
        typedFilter = needle;
        act({ key: "fold-filter", value: needle });
        global.acervatorFoldTranchesTab.renderTab(
          spaceFor("fold-tranches-page"), null, handlersFor("fold-tranches-page")
        );
      }
    },
    "phantom-bots-page": {
      onEnable: function (checked) {
        act({ key: "phantom", name: "enable_phantoms", value: checked });
      },
      onTimeframe: function (timeframe) {
        act({ key: "phantom", name: "phantom_timeframes", value: timeframe });
      },
      onLock: function (count) {
        act({ key: "phantom", name: "lock_candle_count", value: count });
      }
    }
  };

  function handlersFor(part) {
    var found = HANDLERS[part] || {};
    if (part === "fold-tranches-page") {
      found.typed = typedFilter;
    }
    return found;
  }

  function root() {
    return document.getElementById(ROOT);
  }

  function spaceFor(part) {
    var host = root();
    if (host === null) {
      return null;
    }
    return host.querySelector('[data-part="' + part + '"]');
  }

  global.acervatorBotLiveSettingsDraw = function (window_model, tab_models, chrome) {
    global.acervatorBotLiveSettings.drawWindow(root(), window_model);
    global.acervatorSetFoldChrome(chrome);
    var drawn = 0;
    PLAN.forEach(function (row) {
      var api = global[row[1]];
      var space = spaceFor(row[0]);
      var model = tab_models[row[0]];
      if (space === null || model === undefined) {
        return;
      }
      if (model !== null && model["%(fault)s"] !== undefined) {
        var note = document.createElement("p");
        note.setAttribute("data-part", "tab-fault");
        note.textContent = model["%(fault)s"];
        space.textContent = "";
        space.appendChild(note);
        drawn += 1;
        return;
      }
      if (!api) {
        return;
      }
      api.renderTab(space, model, handlersFor(row[0]));
      drawn += 1;
    });
    return drawn;
  };

  global.acervatorBotLiveSettingsDrawn = function () {
    var host = root();
    return host !== null &&
      host.querySelector('[data-part="bot-live-settings"]') !== null;
  };

  function readValue(node, kind) {
    if (kind === "check") {
      return node.checked === true;
    }
    if (kind === "combo_text" || kind === "combo_data") {
      return node.selectedIndex;
    }
    if (kind === "spin") {
      return parseInt(node.value, 10);
    }
    if (kind === "double_spin") {
      return parseFloat(node.value);
    }
    return node.value;
  }

  function outsideBox(node, kind, value) {
    if (kind !== "spin" && kind !== "double_spin") {
      return false;
    }
    var low = parseFloat(node.getAttribute("min"));
    var high = parseFloat(node.getAttribute("max"));
    return !isFinite(value) || value < low || value > high;
  }

  document.addEventListener("change", function (event) {
    var node = event.target;
    if (typeof node.getAttribute !== "function") {
      return;
    }
    var name = node.getAttribute("data-name");
    var kind = node.getAttribute("data-kind");
    if (name === null || kind === null) {
      return;
    }
    var value = readValue(node, kind);
    if (outsideBox(node, kind, value)) {
      node.value = node.defaultValue;
      return;
    }
    console.log("%(edit)s" + JSON.stringify({ name: name, value: value }));
  });

  function pressOf(node, event) {
    var page = node.closest(PAGE_NODE);
    var typed = document.querySelector(PRESS_INPUT);
    return {
      key: node.getAttribute("data-part"),
      name: node.getAttribute("data-name"),
      index: node.getAttribute("data-index"),
      number: node.getAttribute("data-number"),
      tranche: node.getAttribute("data-tranche-id"),
      child: node.getAttribute("data-child-bot-id"),
      value: node.getAttribute("data-value"),
      page: page === null ? null : page.getAttribute("data-part"),
      typed: typed === null ? null : typed.value,
      shift: event.shiftKey === true
    };
  }

  document.addEventListener("click", function (event) {
    var at = event.target;
    while (at) {
      if (typeof at.getAttribute === "function") {
        var part = at.getAttribute("data-part");
        if (part === "tab-button") {
          act({ tab: at.getAttribute("data-key") });
          return;
        }
        if (part !== null && part.indexOf("button") >= 0) {
          act(pressOf(at, event));
          return;
        }
      }
      at = at.parentElement;
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey !== true) {
      return;
    }
    if (event.key === "ArrowLeft") {
      act({ key: "prev-button" });
    } else if (event.key === "ArrowRight") {
      act({ key: "next-button" });
    }
  });
})(window);"""


def host_script() -> str:
    """The inline bridge, with the tab plan and the three keys baked in."""
    plan = json.dumps([[part, api] for _name, part, api, _surface in TAB_PLAN])
    return HOST_SCRIPT % {
        "root": WINDOW_ROOT_ID,
        "plan": plan,
        "edit": EDIT_PREFIX,
        "act": ACTION_PREFIX,
        "fault": FAULT_KEY,
    }


def window_html(theme: object = None) -> str:
    """The whole window page as one string, with no network fetch."""
    return page_html(
        WINDOW_STYLE_ASSETS,
        WINDOW_SCRIPT_ASSETS,
        WINDOW_BODY,
        theme,
        (host_script(),),
    )


def push_script(window_model: dict, tab_models: dict, chrome: Any = None) -> str:
    """The one JS statement that hands the three payloads to the page.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorBotLiveSettingsDraw("
        + json.dumps(window_model, ensure_ascii=True)
        + ", "
        + json.dumps(tab_models, ensure_ascii=True)
        + ", "
        + json.dumps(chrome, ensure_ascii=True)
        + ");"
    )


def field_for(name: str) -> str:
    """The bot config field one Settings-tab control name edits, or ''."""
    try:
        return str(settings_surface.spec_for(name).get("field") or "")
    except (KeyError, StopIteration):
        return ""


def tab_payload(
    module_name: str, bot: Any, now_ts: float, tab: str = "", shape: Any = None
) -> dict:
    """One tab's payload, built from ``bot`` by that tab's own surface.

    A surface that raises answers ``FAULT_KEY`` over ``FAULT_TEXT``, and ``shape``
    takes the built model before the payload is read from it.
    """
    import importlib
    import inspect

    try:
        module = importlib.import_module("src.gui.main_tabs." + module_name)
        model_class = getattr(module, MODEL_BY_SURFACE[module_name])
        builder = module.build_view_model
        model = model_class(bot)
        if hasattr(model, "now"):
            model.now = now_ts
        if "build_now" in inspect.signature(builder).parameters:
            if shape is None:
                return builder(model, build_now=True)
            model.build()
            shape(model)
            return builder(model)
        if "now_ts" in inspect.signature(model.build).parameters:
            model.build(now_ts)
        else:
            model.build()
        return builder(model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s built no payload: %s", module_name, exc)
        reason = f"{type(exc).__name__}: {exc}"
        return {FAULT_KEY: FAULT_TEXT.format(tab=tab or module_name, reason=reason)}


class PagePress:
    """A button the window turns on and off, as ``QPushButton`` reports it."""

    def __init__(self, owner: Any, name: str, words: str = "") -> None:
        self._owner = owner
        self._name = name
        self._words = words
        self._on = True

    def isEnabled(self) -> bool:  # noqa: N802
        """True while the button takes a press."""
        return self._on

    def setEnabled(self, on: Any) -> None:  # noqa: N802
        """Take presses or refuse them, and redraw."""
        self._on = bool(on)
        self._owner.redraw()

    def text(self) -> str:
        """The words the button shows."""
        return self._words

    def setText(self, words: Any) -> None:  # noqa: N802
        """Show ``words`` on the button and redraw."""
        self._words = "" if words is None else str(words)
        self._owner.redraw()


class PageText:
    """The pending-change line, as ``QLabel`` reports it."""

    def __init__(self, owner: Any, words: str = "") -> None:
        self._owner = owner
        self._words = words
        self._sheet = ""

    def text(self) -> str:
        """The words the line shows."""
        return self._words

    def setText(self, words: Any) -> None:  # noqa: N802
        """Show ``words`` and redraw."""
        self._words = "" if words is None else str(words)
        self._owner.redraw()

    def setStyleSheet(self, sheet: Any) -> None:  # noqa: N802
        """Paint the line with ``sheet`` and redraw."""
        self._sheet = "" if sheet is None else str(sheet)
        self._owner.redraw()

    def styleSheet(self) -> str:  # noqa: N802
        """The sheet the line was last given."""
        return self._sheet


class PageTabs:
    """The window's tab strip, as ``QTabWidget`` reports it."""

    def __init__(self, owner: Any, names: list) -> None:
        self._owner = owner
        self._names = list(names)
        self._at = 0

    def count(self) -> int:
        """How many tabs the bot's mode is given."""
        return len(self._names)

    def tabText(self, at: Any) -> str:  # noqa: N802
        """The name on the tab at ``at``, or '' beyond the end."""
        try:
            return self._names[int(at)]
        except (TypeError, ValueError, IndexError):
            return ""

    def currentIndex(self) -> int:  # noqa: N802
        """Which tab the window is showing."""
        return self._at

    def setCurrentIndex(self, at: Any) -> None:  # noqa: N802
        """Show the tab at ``at`` and redraw."""
        try:
            found = int(at)
        except (TypeError, ValueError):
            return
        if 0 <= found < len(self._names):
            self._at = found
            self._owner.redraw()

    def indexOf(self, name: Any) -> int:  # noqa: N802
        """Where ``name`` sits in the strip, or -1."""
        return self._names.index(name) if name in self._names else -1


class PageLabel:
    """A cell or a button a handler relabels, redrawn by the next ``redraw``."""

    def setText(self, words: Any) -> None:
        """Take ``words``; the next ``tab_payload`` reads them off the bot."""

    def setToolTip(self, words: Any) -> None:
        """Take ``words``; the next ``tab_payload`` reads them off the bot."""


class PageFoldTable:
    """The Fold Tranches rows ``on_fold_filter_changed`` hides, as ``QTableWidget``."""

    def __init__(self, rows: int) -> None:
        self.hidden = [False] * rows

    def rowCount(self) -> int:
        """How many rows the tab drew."""
        return len(self.hidden)

    def setRowHidden(self, row: int, hide: bool) -> None:
        """Hide or show the row at ``row``."""
        self.hidden[row] = bool(hide)


def plain_box_text(words: Any) -> str:
    """``words`` with the two Qt rich-text marks ``_on_fire_position`` uses taken out."""
    return (
        str(words).replace("<br>", "\n").replace("<b>", "").replace("</b>", "")
    )


class PageBoxes:
    """``QMessageBox`` on the page: the same calls, answered by ``page_box``."""

    Yes = 1
    No = 2
    Cancel = 4
    Ok = 8
    Warning = "warning"
    Information = "information"
    Critical = "critical"
    Question = "question"

    def __init__(self, parent: Any) -> None:
        self._parent = parent
        self._icon = PageBoxes.Information
        self._title = ""
        self._words = ""
        self._buttons = PageBoxes.Ok
        self._default = PageBoxes.Ok

    def setIcon(self, icon: Any) -> None:
        """Hold ``icon`` for ``exec``."""
        self._icon = icon

    def setWindowTitle(self, title: Any) -> None:
        """Hold ``title`` for ``exec``."""
        self._title = title

    def setText(self, words: Any) -> None:
        """Hold ``words`` for ``exec``."""
        self._words = words

    def setStandardButtons(self, buttons: int) -> None:
        """Hold ``buttons`` for ``exec``."""
        self._buttons = buttons

    def setDefaultButton(self, button: int) -> None:
        """Hold ``button`` for ``exec``."""
        self._default = button

    def exec(self) -> int:
        """Draw the box and answer the button the page pressed."""
        return self._parent.page_box(
            self._icon, self._title, self._words, self._buttons, self._default
        )[0]

    @staticmethod
    def information(parent: Any, title: Any, words: Any) -> int:
        """``QMessageBox.information`` on the page."""
        return parent.page_box(
            PageBoxes.Information, title, words, PageBoxes.Ok, PageBoxes.Ok
        )[0]

    @staticmethod
    def warning(parent: Any, title: Any, words: Any) -> int:
        """``QMessageBox.warning`` on the page."""
        return parent.page_box(
            PageBoxes.Warning, title, words, PageBoxes.Ok, PageBoxes.Ok
        )[0]

    @staticmethod
    def critical(parent: Any, title: Any, words: Any) -> int:
        """``QMessageBox.critical`` on the page."""
        return parent.page_box(
            PageBoxes.Critical, title, words, PageBoxes.Ok, PageBoxes.Ok
        )[0]

    @staticmethod
    def question(
        parent: Any, title: Any, words: Any, buttons: int, default: int
    ) -> int:
        """``QMessageBox.question`` on the page."""
        return parent.page_box(PageBoxes.Question, title, words, buttons, default)[0]


class PagePrompt:
    """``QInputDialog`` on the page: one typed answer through ``page_box``."""

    @staticmethod
    def getText(
        parent: Any, title: Any, words: Any, _echo: Any, _text: Any
    ) -> tuple:
        """Answer what the operator typed and whether OK took it."""
        pressed, typed = parent.page_box(
            PageBoxes.Question,
            title,
            words,
            PageBoxes.Ok | PageBoxes.Cancel,
            PageBoxes.Ok,
            True,
        )
        return typed, pressed == PageBoxes.Ok


#: The name a page button sends and the word it shows, for each box answer.
BOX_ANSWERS: tuple = (
    (PageBoxes.Yes, "yes", "Yes"),
    (PageBoxes.No, "no", "No"),
    (PageBoxes.Cancel, "cancel", "Cancel"),
    (PageBoxes.Ok, "ok", "OK"),
)


def box_payload(icon: Any, title: Any, words: Any, buttons: int, default: int) -> dict:
    """The ``press_box`` field of the window payload for one open box."""
    offered = [row for row in BOX_ANSWERS if buttons & row[0]]
    named = {row[0]: row[1] for row in BOX_ANSWERS}
    return {
        "icon": icon,
        "title": str(title),
        "text": plain_box_text(words),
        "buttons": [row[1] for row in offered],
        "words": {row[1]: row[2] for row in offered},
        "fallback": named.get(default),
        "input": False,
    }


#: The inherited handler each page button runs, by the page and the button's place.
CLEAR_HANDLERS: dict = {
    "fold-tranches-page": (
        "_on_clear_fold_tranches",
        "_on_clear_wire_credits",
        "_on_clear_lifetime_counters",
    ),
    "stack-tranches-page": (
        "_on_clear_stack_tranches",
        "_on_clear_stack_lifetime_counters",
    ),
}

#: The two classes ``_build`` makes, kept so one import builds them once.
_BUILT: dict = {}


def _build() -> dict:
    """Define the page and the window class over the shipped Qt window.

    The base class is imported here rather than at module load, so a walk of
    ``src.gui`` never reaches the window that reads the operator's bot.
    """
    from .bot_live_settings import BotLiveSettingsDialog
    from .live_settings.fold_chrome import (
        on_fold_filter_changed,
        on_fold_sort_changed,
    )

    class BotLiveSettingsPage(QWebEnginePage):
        """Routes the page's ``acervator-`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the window that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an edit or a press to the owner and drop every other line."""
            del level, line, source
            if message.startswith(EDIT_PREFIX):
                self._owner.apply_edit(message[len(EDIT_PREFIX) :])
            elif message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class BotLiveSettingsReactDialog(BotLiveSettingsDialog):
        """The Live Bot Settings window with every tab drawn by React."""

        def _setup_ui(self) -> None:
            """Build the one web view the whole window is drawn in.

            The header, the tab strip, the Apply button and the pending line
            become page-backed holders under the same attribute names, so
            ``_mark_changed`` and ``_apply_changes`` run unchanged.
            """
            bot = self._bot
            cfg = bot.config
            self.setWindowTitle(surface.window_title(cfg.symbol, bot.bot_id))
            self.setMinimumSize(surface.MINIMUM_W_PX, surface.MINIMUM_H_PX)

            self._model = surface.build_model(bot, self._bm)
            self._model.build()
            self._page_ready = False
            self._built = False
            self._last_window: dict = {}
            self._last_tabs: dict = {}
            self._tabs = PageTabs(self, list(self._model.tabs))
            self._apply_btn = PagePress(self, "apply_btn", surface.APPLY_LABEL)
            self._change_lbl = PageText(self)
            self._cb_reset_all_btn = PagePress(
                self, "cb_reset_all_btn", settings_surface.RESET_BUTTON_TEXT
            )
            self._apply_btn.setEnabled(False)
            self._open_boxes: list = []
            self._box_waiters: list = []
            self._fold_filter = ""
            self._fold_drawn: list = []
            self._phantom_steps: list = []
            self._read_phantom_timeframes()
            self._built = True

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = BotLiveSettingsPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(window_html())
            layout.addWidget(self._web, 1)
            self.open_at_content_size()

        # -- sizing, which the Qt side takes off its tab pages -----------

        def open_at_content_size(self, available: tuple | None = None) -> tuple:
            """Open at the size the surface asks for and report it."""
            width, height = self._model.open_at_content_size(available=available)
            self.resize(int(width), int(height))
            return int(width), int(height)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last window payload pushed."""
            return dict(self._last_window)

        def tab_models(self) -> dict:
            """A copy of the last payload pushed for each tab space."""
            return dict(self._last_tabs)

        def redraw(self) -> None:
            """Build the window payload and every tab payload, and push both."""
            import time

            if not getattr(self, "_built", False):
                return
            self._model.tabs = list(self._tabs._names)
            self._model.current_tab = self._tabs.currentIndex()
            window = surface.build_view_model(self._model)
            window["current_tab"] = self._tabs.currentIndex()
            window["tabs"] = list(self._tabs._names)
            window[CHANGE_LABEL_KEY] = self._change_lbl.text()
            sheet = self._change_lbl.styleSheet()
            if sheet:
                window[CHANGE_STYLE_KEY] = sheet
            window["apply_enabled"] = self._apply_btn.isEnabled()
            window[PRESS_BOX_KEY] = self._open_boxes[-1] if self._open_boxes else None
            now_ts = time.time()
            shapes = {
                "fold_tranches_tab_surface": self._shape_fold_tab,
                "phantom_bots_tab_surface": self._shape_phantom_tab,
            }
            tabs: dict = {}
            for name, part, _api, module_name in TAB_PLAN:
                if self._tabs.indexOf(name) < 0:
                    continue
                tabs[part] = tab_payload(
                    module_name, self._bot, now_ts, name, shapes.get(module_name)
                )
            reset = tabs.get(SETTINGS_SPACE, {}).get("reset_button")
            if reset is not None:
                reset["current_text"] = self._cb_reset_all_btn.text()
            self._last_window = window
            self._last_tabs = tabs
            if self._page_ready:
                self._run(push_script(window, tabs, self._chrome_payload()))

        def _chrome_payload(self) -> dict:
            """The Order and Filter payload ``fold_chrome.js`` draws above the table."""
            return fold_chrome_surface.view_model(
                {
                    "reset": True,
                    "controls": True,
                    "dialog": {
                        "bot_id": self._bot.bot_id,
                        "sort_key": self._fold_sort_key,
                    },
                }
            )

        def _shape_fold_tab(self, model: Any) -> None:
            """Keep the row order and filter ``on_fold_filter_changed`` reads on ``model``."""
            model.choose_order(self._fold_sort_key)
            self._fold_drawn = model.tranches()
            self._fold_row_texts = model.rows
            self._fold_tranche_table = PageFoldTable(len(model.rows))
            on_fold_filter_changed(self, self._fold_filter)
            model.row_filter = self._fold_filter
            model.hidden_rows = list(self._fold_tranche_table.hidden)

        def _shape_phantom_tab(self, model: Any) -> None:
            """Move the tab's controls to the steps waiting for Apply Changes."""
            model.run_steps(self._phantom_steps)

        def _read_phantom_timeframes(self) -> None:
            """Fill the four names ``_take_phantom_timeframe`` reads off the bot."""
            config = self._bot.config
            exchange_id = getattr(config, "exchange_id", None)
            self._phantom_tf_allowed = phantom_surface.allowed_timeframes(exchange_id)
            self._phantom_tf_exchange = exchange_id
            self._phantom_tf_parent = str(
                getattr(config, "ta_timeframe", None)
                or phantom_surface.PARENT_TIMEFRAME_DEFAULT
            )
            self._phantom_tf_current = phantom_surface.chosen_timeframe(
                phantom_surface.configured_timeframes(self._bot)
            )

        def take_phantom_step(self, field: str, value: Any) -> None:
            """Record one Phantom Bots control the way its Qt widget's signal does."""
            if field == phantom_surface.TIMEFRAMES_FIELD:
                step = [phantom_surface.STEP_TIMEFRAME, value]
                self._take_phantom_timeframe(value)
            elif field == phantom_surface.LOCK_FIELD:
                step = [phantom_surface.STEP_LOCK, int(value)]
                self._mark_changed(field, int(value))
            else:
                step = [phantom_surface.STEP_ENABLE, bool(value)]
                self._mark_changed(field, bool(value))
            self._phantom_steps = [
                held for held in self._phantom_steps if held[0] != step[0]
            ] + [step]

        def _message_boxes(self) -> type:
            """``PageBoxes``, so each inherited press asks on the page."""
            return PageBoxes

        def _text_prompts(self) -> type:
            """``PagePrompt``, so Self-Destruct's typed phrase is asked on the page."""
            return PagePrompt

        def page_box(
            self,
            icon: Any,
            title: Any,
            words: Any,
            buttons: int,
            default: int,
            typed: bool = False,
        ) -> tuple:
            """Draw one box, wait for the page's answer, and answer it and the text.

            ``QEventLoop`` waits here the way ``QMessageBox.exec`` waits.
            """
            box = box_payload(icon, title, words, buttons, default)
            box["input"] = typed
            box["answer"] = default if not typed else PageBoxes.Cancel
            box["typed"] = ""
            waiter = QEventLoop(self)
            self._open_boxes.append(box)
            self._box_waiters.append(waiter)
            self.redraw()
            waiter.exec()
            self._box_waiters.remove(waiter)
            self._open_boxes.remove(box)
            self.redraw()
            return box["answer"], box["typed"]

        def _answer_box(self, asked: dict) -> None:
            """Take the page's answer to the box on top and end its wait."""
            if not self._open_boxes:
                return
            named = {row[1]: row[0] for row in BOX_ANSWERS}
            box = self._open_boxes[-1]
            box["answer"] = named.get(str(asked.get("value")), box["answer"])
            box["typed"] = str(asked.get("typed") or "")
            self._box_waiters[-1].quit()

        def done(self, result: int) -> None:
            """End every wait ``page_box`` holds, then close the window."""
            for waiter in list(self._box_waiters):
                waiter.quit()
            super().done(result)

        def _show_hold(self) -> None:
            """Redraw the page, whose ``build_view_model`` reads ``hold_text`` itself."""
            self.redraw()

        def _refresh_fold_tranches_tab(self) -> str:
            """Redraw the page and answer what the Qt rebuild answers."""
            self.redraw()
            return "refreshed"

        def _refresh_stack_tranches_tab(self) -> str:
            """Redraw the page and answer what the Qt rebuild answers."""
            self.redraw()
            return "refreshed"

        def _fold_panel_shows(self) -> dict:
            """Report the Fold Tranches tab off the model the page was drawn from."""
            model = fold_surface.FoldTranchesTabModel(self._bot)
            model.build()
            return model.panel_shows()

        def _press_for(self, key: str, asked: dict) -> Any:
            """The inherited handler one page button runs, or None for no such button."""
            name = asked.get("name")
            page = str(asked.get("page") or "")
            if key == "row-button" and name == "cb_reset_all_btn":
                return partial(self._on_cb_reset_all, asked.get("shift") is True)
            if key == "row-button" and name == "self_destruct_btn":
                return self._on_self_destruct_clicked
            if key == "clear-button" and page in CLEAR_HANDLERS:
                return getattr(self, CLEAR_HANDLERS[page][int(asked["index"])])
            if key == "fire-button" and page == "positions-held-page":
                return partial(self._on_fire_position, str(name))
            if key == "fire-button":
                number = int(asked["number"])
                return partial(
                    self._on_fire_tranche_clicked, self._fold_drawn[number - 1], number
                )
            if key == "arbiter-button":
                return partial(
                    self._on_arbiter_toggle_clicked,
                    str(asked.get("tranche") or ""),
                    str(asked.get("child") or ""),
                    PageLabel(),
                    PageLabel(),
                )
            if key == "fold-order":
                return partial(on_fold_sort_changed, self, asked.get("value"))
            if key == "fold-filter":
                return partial(setattr, self, "_fold_filter", str(asked.get("value")))
            if key == "phantom":
                return partial(self.take_phantom_step, name, asked.get("value"))
            return None

        def _run_press(self, press: Any) -> None:
            """Run one page press and draw what it left."""
            press()
            self.redraw()

        def apply_edit(self, payload: str) -> None:
            """Take one operator edit and record it the way the widget did."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Live settings page sent an edit that is not JSON")
                return
            name = str(asked.get("name") or "")
            field = field_for(name)
            if not field:
                return
            held, value = settings_surface.admitted_edit(
                name, asked.get("value"), self._last_tabs.get(SETTINGS_SPACE)
            )
            if not held:
                logger.warning(EDIT_REFUSED_LOG, name, asked.get("value"))
                return
            if settings_surface.spec_for(name)["reading"] == TIMEFRAME_READING:
                self._ta_timeframe_picked(value)
                return
            self._mark_changed(field, value)

        def run_action(self, payload: str) -> None:
            """Run the tab, the Apply or the Close the page reports."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Live settings page sent an action that is not JSON")
                return
            key = str(asked.get("key") or "")
            if key == BOX_BUTTON:
                self._answer_box(asked)
                return
            if self._open_boxes:
                return
            if "tab" in asked:
                self._tabs.setCurrentIndex(self._tabs.indexOf(str(asked["tab"])))
                return
            if key == "apply-button":
                self._phantom_steps = []
                self._apply_changes()
            elif key == "close-button":
                self.accept()
            elif key == "prev-button":
                self._navigate_to_sibling(surface.PREV_STEP)
            elif key == "next-button":
                self._navigate_to_sibling(surface.NEXT_STEP)
            press = self._press_for(key, asked)
            if press is not None:
                QTimer.singleShot(0, partial(self._run_press, press))

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Live Bot Settings page failed to load")
                return
            self.redraw()

    return {
        "BotLiveSettingsPage": BotLiveSettingsPage,
        "BotLiveSettingsReactDialog": BotLiveSettingsReactDialog,
    }


def dialog_class() -> type:
    """The React window class, defined on the first call and kept after."""
    if not _BUILT:
        _BUILT.update(_build())
    return _BUILT["BotLiveSettingsReactDialog"]


def __getattr__(name: str):
    """Answer ``BotLiveSettingsReactDialog`` and ``BotLiveSettingsPage`` lazily.

    Reading either name defines them; importing this module does not.
    """
    if name in ("BotLiveSettingsPage", "BotLiveSettingsReactDialog"):
        if not _HAS_WEBENGINE:
            raise AttributeError(name)
        if not _BUILT:
            _BUILT.update(_build())
        return _BUILT[name]
    raise AttributeError(name)
