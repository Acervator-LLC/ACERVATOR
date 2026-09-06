# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The main window's tab bar, drawn by React inside ``QWebEngineView``.

``MainTabBookReact`` answers the tab-book calls ``MainWindow._setup_ui`` and
``_reorder_main_tabs`` make, keeps a ``QTabWidget`` with a hidden bar as the
page stack, and draws the labels and the selection in React above it.
``MainWindowChromePage`` carries the bar's presses back to ``run_action``.

The page runs ``desktop/renderer/panel_host.js`` and
``desktop/renderer/tab_bar.js``, the Electron shell's own navigation, so the
window and the shell draw one bar.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from .main_tabs import design_system_surface
from .react_history_panel import page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, MainTabBookReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_main_window")

ACTION_PREFIX = "acervator-act:"

#: The element the bar draws into, and the one its panel hosts sit in.
TABS_ID = "tabs"
PANELS_ID = "panels"

ACCESSIBLE_NAME = "React Main Tab Book"
BAR_ACCESSIBLE_NAME = "React Main Window Tab Bar"

BAR_HEIGHT_PX = 44

#: The scripts the page carries from ``src/gui/web``. Order is load order.
BAR_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "design_tokens.js",
    "main_window.js",
)

#: The shell's own navigation, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPTS: tuple[str, ...] = ("panel_host.js", "tab_bar.js")

#: The shell's own bar skin, read from ``desktop/renderer``.
SHELL_STYLE = "tab_bar.css"

RENDERER_DIRNAME = "renderer"
DESKTOP_DIRNAME = "desktop"


class ChromeAssetMissing(RuntimeError):
    """A shell asset the bar cannot be drawn without is not on disk."""


def renderer_dir() -> Path:
    """The directory holding the Electron shell's renderer scripts.

    ``__file__`` covers running from source; ``sys._MEIPASS`` covers the
    React build, which carries ``desktop/renderer`` inside the bundle.
    """
    from_source = (
        Path(__file__).resolve().parents[2] / DESKTOP_DIRNAME / RENDERER_DIRNAME
    )
    if from_source.is_dir():
        return from_source
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / DESKTOP_DIRNAME / RENDERER_DIRNAME
    return from_source


def read_renderer_asset(name: str) -> str:
    """Return one shell asset's text, or raise ``ChromeAssetMissing``.

    ``newline=""`` keeps a CRLF checkout from reaching the page.
    """
    path = renderer_dir() / name
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise ChromeAssetMissing(
            f"Shell asset not readable: {path} ({type(exc).__name__})"
        ) from exc


def host_script() -> str:
    """The page's own glue: the design tokens, the tab set and the presses.

    ``acervatorMainWindowSetTabs`` registers one stub panel per label so the
    shell's bar has a screen to draw a tab for, and reports a press and a
    drop back over the console channel.
    """
    tokens = json.dumps(design_system_surface.view_model({}), ensure_ascii=True)
    return _HOST_SOURCE % {
        "act": ACTION_PREFIX,
        "tabs": TABS_ID,
        "panels": PANELS_ID,
        "tokens": tokens,
    }


_HOST_SOURCE = """(function (global) {
  "use strict";

  var TABS = "%(tabs)s";
  var PANELS = "%(panels)s";

  global.acervatorSetTokens(%(tokens)s);
  global.acervatorTokens.apply(document.documentElement);

  function report(payload) {
    console.log("%(act)s" + JSON.stringify(payload));
  }

  function stub() {
    return {
      render: function (target) {
        return target;
      }
    };
  }

  global.acervatorMainWindowSetTabs = function (labels, selected) {
    var host = global.acervatorPanelHost;
    var bar = global.acervatorTabBar;
    bar.forget();
    host.forget();
    var declared = [];
    for (var index = 0; index < labels.length; index++) {
      declared.push(labels[index] + ".js");
      host.register(stub(), labels[index]);
    }
    global.ACERVATOR_MODULES = declared;
    var panels = document.getElementById(PANELS);
    panels.textContent = "";
    var drawn = bar.build(
      document.getElementById(TABS),
      panels,
      function (from, to) {
        report({ move: { from: from, to: to } });
      }
    );
    if (selected) {
      bar.select(selected);
    }
    return drawn;
  };

  global.acervatorMainWindowSelect = function (name) {
    global.acervatorTabBar.select(name);
    return global.acervatorTabBar.selected();
  };

  global.acervatorMainWindowLabels = function () {
    var found = [];
    var buttons = document
      .getElementById(TABS)
      .querySelectorAll("[" + global.acervatorTabBar.tabAttribute + "]");
    for (var index = 0; index < buttons.length; index++) {
      found.push(buttons[index].textContent);
    }
    return found;
  };

  document.addEventListener("click", function (event) {
    var at = event.target;
    while (at) {
      var name =
        typeof at.getAttribute === "function"
          ? at.getAttribute(global.acervatorTabBar.tabAttribute)
          : null;
      if (name !== null) {
        report({ tab: name });
        return;
      }
      at = at.parentElement;
    }
  });
})(window);"""


def chrome_html(theme: str = "cyberpunk_dark") -> str:
    """The whole bar page as one string, with no network fetch."""
    body = (
        "<style>"
        + read_renderer_asset(SHELL_STYLE)
        + "</style>"
        + f'<nav id="{TABS_ID}"></nav><div id="{PANELS_ID}" hidden></div>'
    )
    inline = tuple(read_renderer_asset(name) for name in SHELL_SCRIPTS)
    return page_html((), BAR_SCRIPT_ASSETS, body, theme, inline + (host_script(),))


def set_tabs_script(labels: list, selected: Optional[str]) -> str:
    """The one JS statement that hands the page its tab set and selection."""
    return (
        "window.acervatorMainWindowSetTabs("
        + json.dumps(list(labels), ensure_ascii=True)
        + ", "
        + json.dumps(selected, ensure_ascii=True)
        + ");"
    )


def select_script(label: Optional[str]) -> str:
    """The one JS statement that marks ``label`` as the selected tab."""
    return (
        "window.acervatorMainWindowSelect("
        + json.dumps(label, ensure_ascii=True)
        + ");"
    )


#: The JS expression that reads back the labels the browser drew, in order.
LABELS_JS = "window.acervatorMainWindowLabels()"


if _HAS_WEBENGINE:

    class MainWindowChromePage(QWebEnginePage):
        """Routes the bar's ``acervator-`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the bar."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class MainTabBookReact(QWidget):
        """The main tab book with its bar in React and its pages in Qt.

        Answers ``addTab``, ``insertTab``, ``count``, ``tabText``, ``widget``,
        ``indexOf``, ``currentIndex``, ``setCurrentIndex``, ``setMovable`` and
        ``tabBar`` over the ``QTabWidget`` it holds, whose own bar is hidden.
        """

        def __init__(self, parent=None) -> None:
            """Build the hidden-bar page stack; the React bar waits for a show."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._book = QTabWidget(self)
            self._book.tabBar().hide()
            self._web: Any = None
            self._page_ready = False
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self._layout.addWidget(self._book, 1)
            self.currentChanged = self._book.currentChanged
            self._book.currentChanged.connect(self._on_current_changed)
            self._book.tabBar().tabMoved.connect(self._on_tab_moved)

        # -- the QTabWidget calls the window makes ------------------------

        def addTab(self, widget, label: str) -> int:
            """Add ``widget`` under ``label`` and redraw the bar."""
            index = self._book.addTab(widget, label)
            self._push_tabs()
            return index

        def insertTab(self, index: int, widget, label: str) -> int:
            """Insert ``widget`` under ``label`` at ``index`` and redraw the bar."""
            at = self._book.insertTab(index, widget, label)
            self._push_tabs()
            return at

        def count(self) -> int:
            """How many tabs the book holds."""
            return self._book.count()

        def tabText(self, index: int) -> str:
            """The label of the tab at ``index``."""
            return self._book.tabText(index)

        def widget(self, index: int):
            """The page of the tab at ``index``."""
            return self._book.widget(index)

        def indexOf(self, widget) -> int:
            """The index of ``widget``, or -1."""
            return self._book.indexOf(widget)

        def currentIndex(self) -> int:
            """The index of the tab on show."""
            return self._book.currentIndex()

        def setCurrentIndex(self, index: int) -> None:
            """Show the tab at ``index``."""
            self._book.setCurrentIndex(index)

        def tabBar(self):
            """The hidden ``QTabBar`` that carries the order and the pages."""
            return self._book.tabBar()

        def setMovable(self, movable: bool) -> None:
            """Let a press drag a tab to another slot."""
            self._book.setMovable(movable)

        # -- the bar ------------------------------------------------------

        def labels(self) -> list:
            """Every tab label, left to right."""
            return [self._book.tabText(at) for at in range(self._book.count())]

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def bar_view(self):
            """The web view the bar draws in, or None before the first show."""
            return self._web

        def showEvent(self, event) -> None:
            """Draw the React bar the first time the book is shown."""
            super().showEvent(event)
            self.build_bar()

        def build_bar(self) -> None:
            """Create the bar's web view and load its page, once."""
            if self._web is not None:
                return
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(BAR_ACCESSIBLE_NAME)
            self._web.setFixedHeight(BAR_HEIGHT_PX)
            self._web_page = MainWindowChromePage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(chrome_html())
            self._layout.insertWidget(0, self._web)

        def run_action(self, payload: str) -> None:
            """Apply one press the bar reported: a tab, or a dropped tab."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("The tab bar sent an action that is not JSON")
                return
            name = request.get("tab")
            if name is not None:
                labels = self.labels()
                if name in labels:
                    self._book.setCurrentIndex(labels.index(name))
                return
            move = request.get("move") or {}
            if "from" in move and "to" in move:
                self._book.tabBar().moveTab(int(move["from"]), int(move["to"]))

        # -- internals ----------------------------------------------------

        def _run(self, script: str) -> None:
            if self._web is not None and self._page_ready:
                self._web.page().runJavaScript(script)

        def _push_tabs(self) -> None:
            index = self._book.currentIndex()
            selected = self._book.tabText(index) if index >= 0 else None
            self._run(set_tabs_script(self.labels(), selected))

        def _on_current_changed(self, index: int) -> None:
            if index >= 0:
                self._run(select_script(self._book.tabText(index)))

        def _on_tab_moved(self, frm: int, to: int) -> None:
            del frm, to
            self._push_tabs()

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React main window tab bar failed to load")
                return
            self._push_tabs()
