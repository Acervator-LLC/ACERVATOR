# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole Console tab drawn by React inside ``QWebEngineView``.

``ConsoleReactTab`` replaces every Qt control ``ConsoleTabMixin`` builds and
holds the same parts under ``log_pane``, ``signal_view``, ``pause_button``,
``pause_indicator`` and ``pause_refresh``, so the main window drives either
side with one set of calls. ``ConsoleTabPage`` carries the page's own calls
back to ``run_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from .main_tabs import console_tab_surface as surface
from .main_tabs.console_log_handler import _QtLogHandler
from .react_history_panel import page_html

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, ConsoleReactTab is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_console_tab")

ACTION_PREFIX = "acervator-act:"

#: The element ``console_tab.js`` draws the tab into.
TAB_ROOT_ID = "tab-root"

ACCESSIBLE_NAME = "React Console Tab"

#: The style sheet the page carries.
TAB_STYLE_ASSETS: tuple[str, ...] = ("console_tab.css",)

#: The scripts the page carries. Order is load order.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "header_strip.js",
    "console_tab.js",
)

TAB_BODY = f'<div id="{TAB_ROOT_ID}"></div>'

#: The two buttons the page reports back rather than answering itself.
HOST_ACTIONS: tuple[str, ...] = ("toggle_console_pause", "clear_log_pane")

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function () {
      return Promise.resolve(null);
    }
  };

  document.addEventListener("click", function (event) {
    var at = event.target;
    while (at) {
      if (typeof at.getAttribute === "function") {
        var action = at.getAttribute("data-action");
        if (action !== null) {
          console.log("%(act)s" + JSON.stringify({ key: action }));
          return;
        }
      }
      at = at.parentElement;
    }
  });

  global.acervatorConsoleTabDrawn = function () {
    return document.getElementById("%(tab)s") !== null;
  };
})(window);""" % {
    "act": ACTION_PREFIX,
    "tab": TAB_ROOT_ID,
}


def tab_html(theme: object = None) -> str:
    """The whole tab page as one string, with no network fetch."""
    return page_html(
        TAB_STYLE_ASSETS, TAB_SCRIPT_ASSETS, TAB_BODY, theme, (HOST_SCRIPT,)
    )


def push_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page and redraws it.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside
    a JSON string and are JavaScript line terminators.
    """
    body = json.dumps(model, ensure_ascii=True)
    return (
        "window.acervatorSetConsole("
        + body
        + ");window.acervatorConsole.renderTab("
        + 'document.getElementById("'
        + TAB_ROOT_ID
        + '"), '
        + body
        + ");"
    )


class PagePane:
    """One console pane held as blocks and drawn by the page.

    Answers the calls the main window makes on a ``QPlainTextEdit``:
    ``clear``, ``blockCount``, ``maximumBlockCount``, ``document`` and
    ``appendHtml``.
    """

    def __init__(self, owner, pane) -> None:
        self._owner = owner
        self._pane = pane

    def clear(self) -> None:
        """Empty the pane, the way the Clear button does."""
        self._pane.clear()
        self._owner.redraw()

    def append_line(self, text: str, channels: list) -> None:
        """Append one line in ``channels`` and redraw."""
        body = str(text)
        self._pane.insert(body if self._pane.is_empty() else "\n" + body, channels)
        self._owner.redraw()

    def appendHtml(self, markup: str) -> None:  # noqa: N802
        """Append one line of markup, as ``QPlainTextEdit.appendHtml`` does.

        The tags come out and the line keeps the first colour they named.
        """
        self.append_line(surface.line_text(markup), surface.line_channels(markup))

    def blockCount(self) -> int:  # noqa: N802
        """Blocks held. An empty pane counts as one, as the Qt pane does."""
        return self._pane.block_count()

    def maximumBlockCount(self) -> int:  # noqa: N802
        """The cap past which the oldest blocks fall off."""
        return self._pane.max_blocks

    def toPlainText(self) -> str:  # noqa: N802
        """Every block joined by newlines, as the Qt pane reports it."""
        return self._pane.text()

    def isEmpty(self) -> bool:  # noqa: N802
        """True while no block has been appended."""
        return self._pane.is_empty()

    def document(self) -> "PagePane":
        """The pane itself, which answers ``isEmpty``."""
        return self


class PageButton:
    """The Pause button as the main window drives it."""

    def __init__(self, owner, text: str) -> None:
        self._owner = owner
        self._text = text
        self._checked = False

    def isChecked(self) -> bool:  # noqa: N802
        """Whether the Pause button is pressed in."""
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        """Press the button in or out and redraw."""
        self._checked = bool(checked)
        self._owner.redraw()

    def setText(self, text: str) -> None:  # noqa: N802
        """Show ``text`` on the button and redraw."""
        self._text = str(text)
        self._owner.redraw()

    def text(self) -> str:
        """The words the button shows."""
        return self._text


class PageLabel:
    """The buffered-message indicator as the main window drives it."""

    def __init__(self, owner, text: str) -> None:
        self._owner = owner
        self._text = text

    def setText(self, text: str) -> None:  # noqa: N802
        """Show ``text`` beside the Pause button and redraw."""
        self._text = str(text)
        self._owner.redraw()

    def text(self) -> str:
        """The words the indicator shows."""
        return self._text


if _HAS_WEBENGINE:

    class ConsoleTabPage(QWebEnginePage):
        """Routes the page's ``acervator-act:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class ConsoleReactTab(QWidget):
        """The Console tab with its control bar and both panes drawn by React.

        ``log_pane`` and ``signal_view`` are the two panes, ``pause_button``
        and ``pause_indicator`` the two control-bar parts, and
        ``pause_refresh`` the timer the pause state starts and stops.
        """

        def __init__(self, parent=None, theme: object = None) -> None:
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._page_ready = False
            self._last_model: dict = {}
            self._log = surface.ConsolePane(surface.PANE_MAX_BLOCKS)
            self._signals = surface.ConsolePane(surface.SIGNAL_MAX_BLOCKS)
            self._ledger = surface.SignalLedger()
            self.log_pane = PagePane(self, self._log)
            self.signal_view = PagePane(self, self._signals)
            self.pause_button = PageButton(self, surface.PAUSE_BUTTON_TEXT)
            self.pause_indicator = PageLabel(self, surface.PAUSE_INDICATOR_TEXT)
            self.pause_refresh = QTimer(self)
            self.pause_refresh.setInterval(surface.PAUSE_REFRESH_INTERVAL_MS)
            # Every append asks for a redraw; the pushes of one event-loop turn
            # coalesce into one, so a drain of 200 signal rows pushes the page once.
            self._redraw_timer = QTimer(self)
            self._redraw_timer.setSingleShot(True)
            self._redraw_timer.setInterval(0)
            self._redraw_timer.timeout.connect(self._push_now)
            self.log_handler = _QtLogHandler(None, painter=self._paint_log_line)
            self.log_handler.setFormatter(
                logging.Formatter(surface.LOG_FORMAT, datefmt=surface.LOG_DATEFMT)
            )
            self.log_handler.setLevel(surface.HANDLER_LEVEL)
            self._pressed: Optional[Callable[[str], None]] = None

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = ConsoleTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(tab_html(theme))
            layout.addWidget(self._web, 1)

        # -- what the render path pushes through -------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last payload pushed, empty before the first push."""
            return dict(self._last_model)

        def ledger(self) -> surface.SignalLedger:
            """The seven drain counters the health timer reads."""
            return self._ledger

        def on_pressed(self, handler: Callable[[str], None]) -> None:
            """Take the callable the main window answers a button press with."""
            self._pressed = handler

        def redraw(self) -> None:
            """Ask for one push of both panes on the next event-loop turn; the
            asks of one turn coalesce into one ``_push_now``."""
            if not self._redraw_timer.isActive():
                self._redraw_timer.start()

        def _push_now(self) -> None:
            """Build the payload from both panes and push it to the page."""
            model = surface.build_view_model(self._log, self._signals, self._ledger)
            model["pause_button"] = {
                **model["pause_button"],
                "text": self.pause_button.text(),
                "checked": self.pause_button.isChecked(),
            }
            model["pause_indicator"] = {
                **model["pause_indicator"],
                "text": self.pause_indicator.text(),
            }
            model["timers"] = {
                **model["timers"],
                "pause_refresh": {
                    "interval_ms": surface.PAUSE_REFRESH_INTERVAL_MS,
                    "running": self.pause_refresh.isActive(),
                },
            }
            self._last_model = model
            if self._page_ready:
                self._run(push_script(model))

        # -- what the page reports back ----------------------------------

        def run_action(self, payload: str) -> None:
            """Run the Pause or the Clear the page reports."""
            try:
                key = str(json.loads(payload).get("key") or "")
            except ValueError:
                logger.warning("Console page sent an action that is not JSON")
                return
            if key == surface.ACTIONS["pause_button.clicked"]:
                self.pause_button.setChecked(not self.pause_button.isChecked())
            elif key != surface.ACTIONS["clear_button.clicked"]:
                return
            if self._pressed is not None:
                self._pressed(key)
            elif key == surface.ACTIONS["clear_button.clicked"]:
                self.log_pane.clear()

        # -- internals ----------------------------------------------------

        def _paint_log_line(
            self, message: str, red: int, green: int, blue: int
        ) -> None:
            self.log_pane.append_line(message, [red, green, blue])

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Console tab page failed to load")
                return
            self.redraw()
