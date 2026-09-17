# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Simulator's Bot Settings window drawn by React inside ``QWebEngineView``,
forked from ``react_bot_live_settings``.

``SimBotDetailReactDialog`` replaces every Qt control ``SimBotDetailDialog._setup_ui``
builds and inherits ``_mark_changed``, ``_apply_changes``, ``_navigate_to_sibling``
and ``active_tab_index`` unchanged, so an edit is refused by the same route.
``TAB_PLAN`` names the module, the surface model and the page space each tab
draws into; ``SimBotDetailPage`` carries the page's edits and presses back to
``apply_edit`` and ``run_action``, and ``run_action`` hands every press inside
a tab to ``refuse_press``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ...simulator.tablet_source import SendRefused
from ..main_tabs import bot_live_settings_surface as surface
from ..main_tabs import live_settings_tab_surface as settings_surface
from ..react_history_panel import page_html
from . import sim_bot_live_settings_surface as sim_surface

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the dialog is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.sim_react_bot_detail")

EDIT_PREFIX = "acervator-edit:"
ACTION_PREFIX = "acervator-act:"

#: The element ``sim_bot_live_settings.js`` draws the whole window into.
WINDOW_ROOT_ID = "window-root"

ACCESSIBLE_NAME = "React Sim Bot Detail"

#: One tab: its name, its page space, its renderer global and its surface module.
TAB_PLAN: tuple = (
    ("Status", "status-page", "acervatorSimLiveStatus", "sim_live_status_tab_surface"),
    (
        "Settings",
        "settings-page",
        "acervatorSimLiveSettingsTab",
        "sim_live_settings_tab_surface",
    ),
    (
        "Fold Tranches",
        "fold-tranches-page",
        "acervatorSimFoldTranchesTab",
        "sim_fold_tranches_tab_surface",
    ),
    (
        "Stack Tranches",
        "stack-tranches-page",
        "acervatorSimStackTranchesTab",
        "sim_stack_tranches_tab_surface",
    ),
    (
        "Bot Swarm",
        "bot-swarm-page",
        "acervatorSimBotSwarmSettingsTab",
        "sim_bot_swarm_tab_surface",
    ),
    (
        "Market Inspector",
        "market-inspector-page",
        "acervatorSimInspectorTab",
        "sim_market_inspector_tab_surface",
    ),
    (
        "Phantom Bots",
        "phantom-bots-page",
        "acervatorSimPhantomBotsTab",
        "sim_phantom_bots_tab_surface",
    ),
    (
        "Positions Held",
        "positions-held-page",
        "acervatorSimPositionsHeld",
        "sim_positions_held_surface",
    ),
)

#: The model class each surface module builds its payload from.
MODEL_BY_SURFACE: dict[str, str] = {
    "sim_live_status_tab_surface": "SimLiveStatusTabModel",
    "sim_live_settings_tab_surface": "SimLiveSettingsTabModel",
    "sim_fold_tranches_tab_surface": "SimFoldTranchesTabModel",
    "sim_stack_tranches_tab_surface": "SimStackTranchesTabModel",
    "sim_bot_swarm_tab_surface": "SimBotSwarmTabModel",
    "sim_market_inspector_tab_surface": "SimMarketInspectorTabModel",
    "sim_phantom_bots_tab_surface": "SimPhantomBotsTabModel",
    "sim_positions_held_surface": "SimPositionsHeldTabModel",
}

#: The style sheet the page carries, Live's own.
WINDOW_STYLE_ASSETS: tuple[str, ...] = ("bot_live_settings.css",)

#: The scripts the page carries. Order is load order.
WINDOW_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    # Owns the Qt style-sheet parser every part of this window skins from.
    "header_strip.js",
    "fold_tokens.js",
    "fold_chrome.js",
    "sim_live_status_tab.js",
    "sim_live_settings_tab.js",
    "sim_fold_tranches_tab.js",
    "sim_stack_tranches_tab.js",
    "sim_bot_swarm_settings_tab.js",
    "sim_market_inspector_tab.js",
    "sim_phantom_bots_tab.js",
    "sim_positions_held.js",
    "sim_bot_live_settings.js",
)

WINDOW_BODY = f'<div id="{WINDOW_ROOT_ID}"></div>'

#: The count of tab pages the window drew, read back off the page.
PAGE_COUNT_JS = "document.querySelectorAll('[data-part$=\"-page\"]').length"

#: The payload keys ``sim_bot_live_settings.js`` draws the pending-change line from.
CHANGE_LABEL_KEY = "change_label"
CHANGE_STYLE_KEY = "change_style"

#: The key a payload carries when its tab could not be built from the bot.
FAULT_KEY = "tab_fault"

#: What a page shows in place of a tab its surface refused.
FAULT_TEXT = "{tab} is unavailable for this bot: {reason}"

#: The footer keys the window answers itself.
APPLY_KEY = "apply-button"
CLOSE_KEY = "close-button"
PREV_KEY = "prev-button"
NEXT_KEY = "next-button"

#: The press names the tab modules send, each to the view method it asks.
FOLD_PRESSES = {
    "clear_button.clicked": "clear_fold_tranches",
    "wire_button.clicked": "clear_pending_wire_credits",
    "counters_button.clicked": "clear_lifetime_tranche_counters",
    "arbiter_button.clicked": "toggle_tranche_arbiter",
}
STACK_PRESSES = {
    "clear_button.clicked": "clear_stack_tranches",
    "counters_button.clicked": "clear_stack_lifetime_counters",
}
SETTINGS_PRESSES = {
    "cb_reset_all_btn": "reset_circuit_breaker",
    "self_destruct_btn": "self_destruct",
}
FIRE_KEY = "fire-button"

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

  global.acervatorSimBotDetailDraw = function (window_model, tab_models) {
    global.acervatorSimBotLiveSettings.renderWindow(root(), window_model);
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
      api.renderTab(space, model);
      drawn += 1;
    });
    return drawn;
  };

  global.acervatorSimBotDetailDrawn = function () {
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
    console.log(
      "%(edit)s" + JSON.stringify({ name: name, value: readValue(node, kind) })
    );
  });

  document.addEventListener("click", function (event) {
    var at = event.target;
    while (at) {
      if (typeof at.getAttribute === "function") {
        var part = at.getAttribute("data-part");
        if (part === "tab-button") {
          console.log(
            "%(act)s" + JSON.stringify({ tab: at.getAttribute("data-key") })
          );
          return;
        }
        if (part !== null && part.indexOf("button") >= 0) {
          console.log(
            "%(act)s" +
              JSON.stringify({
                key: part,
                name: at.getAttribute("data-name"),
                index: at.getAttribute("data-index")
              })
          );
          return;
        }
      }
      at = at.parentElement;
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


def push_script(window_model: dict, tab_models: dict) -> str:
    """The one JS statement that hands both payloads to the page.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorSimBotDetailDraw("
        + json.dumps(window_model, ensure_ascii=True)
        + ", "
        + json.dumps(tab_models, ensure_ascii=True)
        + ");"
    )


def field_for(name: str) -> str:
    """The bot config field one Settings-tab control name edits, or ''."""
    try:
        return str(settings_surface.spec_for(name).get("field") or "")
    except (KeyError, StopIteration):
        return ""


def tab_payload(
    module_name: str, bot: Any, now_ts: float, tab: str = "", rates: Any = None
) -> dict:
    """One tab's payload, built from ``bot`` by that tab's own sim surface.

    A model taking ``now`` is built at ``now_ts``, so every tranche age is
    measured from the push. A surface that raises answers a payload carrying
    ``FAULT_KEY`` and ``FAULT_TEXT``.
    """
    import importlib
    import inspect

    module = importlib.import_module("src.gui.simulator." + module_name)
    model_class = getattr(module, MODEL_BY_SURFACE[module_name])
    builder = module.build_view_model
    try:
        accepted = inspect.signature(model_class).parameters
        if "rates" in accepted:
            model = model_class(bot, rates=rates)
        elif "now" in accepted:
            model = model_class(bot, now=now_ts)
        else:
            model = model_class(bot)
        if "build_now" in inspect.signature(builder).parameters:
            return builder(model, build_now=True)
        if "now_ts" in inspect.signature(model.build).parameters:
            model.build(now_ts)
        else:
            model.build()
        return builder(model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s built no payload: %s", module_name, exc)
        reason = f"{type(exc).__name__}: {exc}"
        return {FAULT_KEY: FAULT_TEXT.format(tab=tab or module_name, reason=reason)}


def press_method(current_tab: str, key: str, name: str) -> str:
    """The view method one press inside ``current_tab`` asks, or ''."""
    if key == FIRE_KEY:
        if current_tab == surface.TAB_POSITIONS_HELD:
            return "manual_fire_position"
        return "manual_fire_tranche"
    if current_tab == surface.TAB_FOLD_TRANCHES:
        return FOLD_PRESSES.get(name, "")
    if current_tab == surface.TAB_STACK_TRANCHES:
        return STACK_PRESSES.get(name, "")
    if current_tab == surface.TAB_SETTINGS:
        return SETTINGS_PRESSES.get(name, "")
    return ""


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


#: The two classes ``_build`` makes, kept so one import builds them once.
_BUILT: dict = {}


def _build() -> dict:
    """Define the page and the window class over the Simulator's Qt window."""
    from .sim_bot_detail import SimBotDetailDialog

    class SimBotDetailPage(QWebEnginePage):
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

    class SimBotDetailReactDialog(SimBotDetailDialog):
        """The Simulator's Bot Settings window with every tab drawn by React."""

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

            self._model = sim_surface.build_model(bot, self._sibling_ids)
            self._model.build()
            self._page_ready = False
            self._built = False
            self._last_window: dict = {}
            self._last_tabs: dict = {}
            self._tabs = PageTabs(self, list(self._model.tabs))
            self._apply_btn = PagePress(self, "apply_btn", surface.APPLY_LABEL)
            self._change_lbl = PageText(self)
            self._cb_reset_all_btn = PagePress(self, "cb_reset_all_btn")
            self._apply_btn.setEnabled(False)
            self._built = True

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = SimBotDetailPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(window_html())
            layout.addWidget(self._web, 1)
            self.open_at_content_size()
            self._log_opened(list(self._tabs._names))

        # -- sizing, which the Qt side takes off its tab pages -----------

        def open_at_content_size(self, available: tuple | None = None) -> tuple:
            """Open at the size the surface asks for and report it."""
            width, height = self._model.open_at_content_size(available=available)
            self.resize(int(width), int(height))
            return int(width), int(height)

        # -- what the render path pushes through -------------------------

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
            window = sim_surface.build_view_model(self._model)
            window["current_tab"] = self._tabs.currentIndex()
            window["tabs"] = list(self._tabs._names)
            window[CHANGE_LABEL_KEY] = self._change_lbl.text()
            sheet = self._change_lbl.styleSheet()
            if sheet:
                window[CHANGE_STYLE_KEY] = sheet
            window["apply_enabled"] = self._apply_btn.isEnabled()
            now_ts = time.time()
            tabs: dict = {}
            for name, part, _api, module_name in TAB_PLAN:
                if self._tabs.indexOf(name) < 0:
                    continue
                tabs[part] = tab_payload(
                    module_name, self._bot, now_ts, name, self._denom_rates
                )
            self._last_window = window
            self._last_tabs = tabs
            if self._page_ready:
                self._run(push_script(window, tabs))

        # -- what the page reports back ----------------------------------

        def apply_edit(self, payload: str) -> None:
            """Take one operator edit and record it the way the widget did."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Sim settings page sent an edit that is not JSON")
                return
            field = field_for(str(asked.get("name") or ""))
            if not field:
                return
            self._mark_changed(field, asked.get("value"))

        def run_action(self, payload: str) -> None:
            """Run the tab, the footer press or the refused press the page reports."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Sim settings page sent an action that is not JSON")
                return
            if "tab" in asked:
                self._tabs.setCurrentIndex(self._tabs.indexOf(str(asked["tab"])))
                return
            key = str(asked.get("key") or "")
            if key == APPLY_KEY:
                self._apply_changes()
            elif key == CLOSE_KEY:
                QTimer.singleShot(0, self.accept)
            elif key == PREV_KEY:
                # Deferred one turn: the host opens the next window after this
                # one accepts, and a web view opened inside a console callback
                # never finishes loading.
                QTimer.singleShot(
                    0, lambda: self._navigate_to_sibling(surface.PREV_STEP)
                )
            elif key == NEXT_KEY:
                QTimer.singleShot(
                    0, lambda: self._navigate_to_sibling(surface.NEXT_STEP)
                )
            else:
                self.refuse_press(key, str(asked.get("name") or ""), asked.get("index"))

        def refuse_press(self, key: str, name: str, index: Any) -> str:
            """Ask the view for the press ``key``/``name`` names; report the refusal."""
            current = self._tabs.tabText(self._tabs.currentIndex())
            method = press_method(current, key, name)
            if not method:
                return ""
            try:
                if method == "manual_fire_tranche":
                    getattr(self._bot, method)(int(index or 0))
                elif method == "manual_fire_position":
                    getattr(self._bot, method)(name)
                elif method == "reset_circuit_breaker":
                    getattr(self._bot, method)("all")
                else:
                    getattr(self._bot, method)()
            except SendRefused as exc:
                logger.warning(
                    "Bot %s: %s refused: %s", self._bot.bot_id[:8], method, exc
                )
                self._change_lbl.setStyleSheet(sim_surface.CHANGE_REFUSED_STYLE)
                self._change_lbl.setText(str(exc))
                return str(exc)
            return ""

        # -- internals ----------------------------------------------------

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Sim Bot Settings page failed to load")
                return
            self.redraw()

    return {
        "SimBotDetailPage": SimBotDetailPage,
        "SimBotDetailReactDialog": SimBotDetailReactDialog,
    }


def dialog_class() -> type:
    """The React window class, defined on the first call and kept after."""
    if not _BUILT:
        _BUILT.update(_build())
    return _BUILT["SimBotDetailReactDialog"]


def __getattr__(name: str):
    """Answer ``SimBotDetailReactDialog`` and ``SimBotDetailPage`` lazily.

    Reading either name defines them; importing this module does not.
    """
    if name in ("SimBotDetailPage", "SimBotDetailReactDialog"):
        if not _HAS_WEBENGINE:
            raise AttributeError(name)
        if not _BUILT:
            _BUILT.update(_build())
        return _BUILT[name]
    raise AttributeError(name)
