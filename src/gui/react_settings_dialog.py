# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole Settings dialog drawn by React inside ``QWebEngineView``.

``SettingsDialogReact`` replaces every Qt control ``SettingsDialog._setup_ui``
builds and inherits ``_load_current``, ``_save``, ``_add_exchange`` and every
other handler unchanged. The page-backed holders answer ``text``, ``value``,
``isChecked`` and ``currentData`` the way the widgets they replace do.
``SettingsDialogPage`` carries the page's edits and presses back to
``apply_edit`` and ``run_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import settings_dialog_surface as surface
from .react_history_panel import page_html
from .settings_dialog import _HAS_QT, SettingsDialog

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, SettingsDialogReact is never defined and its import fails.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_settings_dialog")

EDIT_PREFIX = "acervator-edit:"
ACTION_PREFIX = "acervator-act:"

#: The element ``settings_dialog.js`` draws the whole dialog into.
DIALOG_ROOT_ID = "dialog-root"

ACCESSIBLE_NAME = "React Settings Dialog"

#: The style sheet the page carries.
DIALOG_STYLE_ASSETS: tuple[str, ...] = ("settings_dialog.css",)

#: The three scripts the page carries. Order is load order.
DIALOG_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "settings_dialog.js",
)

DIALOG_BODY = f'<div id="{DIALOG_ROOT_ID}"></div>'

#: The count of drawn controls, read back off the page.
CONTROL_COUNT_JS = "document.querySelectorAll('[data-part=\"control\"]').length"

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function () {
      return Promise.resolve(null);
    }
  };

  var api = global.acervatorSettingsDialog;
  var root = document.getElementById("%(root)s");
  root.setAttribute("data-part", api.spacePart);

  function readValue(node, kind) {
    if (kind === "check" || kind === "radio") {
      return node.checked === true;
    }
    if (kind === "combo_text" || kind === "combo_data") {
      return node.selectedIndex;
    }
    if (kind === "spin" || kind === "slider") {
      return parseInt(node.value, 10);
    }
    if (kind === "double_spin") {
      return parseFloat(node.value);
    }
    return node.value;
  }

  function report(node) {
    var name = node.getAttribute("data-name");
    var kind = node.getAttribute("data-kind");
    if (name === null || kind === null) {
      return false;
    }
    console.log(
      "%(edit)s" + JSON.stringify({ name: name, value: readValue(node, kind) })
    );
    return true;
  }

  document.addEventListener("change", function (event) {
    report(event.target);
  });

  document.addEventListener("click", function (event) {
    var at = event.target;
    while (at) {
      if (typeof at.getAttribute === "function") {
        var part = at.getAttribute("data-part");
        if (part === "button") {
          console.log(
            "%(act)s" +
              JSON.stringify({ key: at.getAttribute("data-name") })
          );
          return;
        }
        if (part === "tab-button") {
          console.log(
            "%(act)s" +
              JSON.stringify({ tab: at.getAttribute("data-key") })
          );
          return;
        }
        if (part === "list-item") {
          console.log(
            "%(act)s" +
              JSON.stringify({ row: at.getAttribute("data-index") })
          );
          return;
        }
      }
      at = at.parentElement;
    }
  });

  global.acervatorSettingsDialogDrawn = function () {
    return root.querySelector('[data-part="settings-dialog"]') !== null;
  };
})(window);""" % {
    "edit": EDIT_PREFIX,
    "act": ACTION_PREFIX,
    "root": DIALOG_ROOT_ID,
}


def dialog_html(theme: str = "cyberpunk_dark") -> str:
    """The whole dialog page as one string, with no network fetch."""
    return page_html(
        DIALOG_STYLE_ASSETS, DIALOG_SCRIPT_ASSETS, DIALOG_BODY, theme, (HOST_SCRIPT,)
    )


def push_script(model: dict, tab: str) -> str:
    """The one JS statement that hands ``model`` to the page and draws ``tab``.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorSettingsDialog.fill("
        + 'document.getElementById("'
        + DIALOG_ROOT_ID
        + '"), '
        + json.dumps(model, ensure_ascii=True)
        + ", "
        + json.dumps(tab, ensure_ascii=True)
        + ");"
    )


class _Held:
    """One named value in the dialog's store, drawn by the page.

    ``owner`` holds the store and redraws; ``name`` is the control spec name.
    """

    def __init__(self, owner: Any, name: str) -> None:
        self._owner = owner
        self._name = name

    def _get(self) -> Any:
        return self._owner.store().values.get(self._name)

    def _put(self, value: Any) -> None:
        self._owner.set_value(self._name, value)

    def admit(self, value: Any) -> None:
        """Take one operator edit of this control from the page."""
        self._put(value)


class PageLine(_Held):
    """A line of text, as ``QLineEdit`` reports it."""

    def text(self) -> str:
        """The words typed in the field."""
        held = self._get()
        return "" if held is None else str(held)

    def setText(self, words: Any) -> None:  # noqa: N802
        """Put ``words`` in the field and redraw."""
        self._put("" if words is None else str(words))

    def clear(self) -> None:
        """Empty the field and redraw."""
        self._put("")

    def setVisible(self, shown: Any) -> None:  # noqa: N802
        """Show or hide the field and redraw."""
        self._owner.set_visible(self._name, bool(shown))


class PageTextArea(_Held):
    """A block of text, as ``QTextEdit`` reports it."""

    def toPlainText(self) -> str:  # noqa: N802
        """Every line in the box, with no markup."""
        held = self._get()
        return "" if held is None else str(held)

    def clear(self) -> None:
        """Empty the box and redraw."""
        self._put("")


class PageToggle(_Held):
    """A tick box or a radio button, as ``QCheckBox`` reports it."""

    def isChecked(self) -> bool:  # noqa: N802
        """True while the box is ticked."""
        return self._get() is True

    def setChecked(self, ticked: Any) -> None:  # noqa: N802
        """Tick or clear the box and redraw."""
        self._put(bool(ticked))


def radio_siblings(name: str) -> tuple:
    """Every other radio sharing one group box with ``name``.

    ``QGroupBox`` clears these when one radio inside it is ticked.
    """
    spec = surface.spec_for(name)
    return tuple(
        one["name"]
        for one in surface.CONTROL_SPECS
        if one["kind"] == surface.RADIO
        and one["tab"] == spec["tab"]
        and one["group"] == spec["group"]
        and one["name"] != name
    )


class PageRadio(PageToggle):
    """A radio button, exclusive inside its group box."""

    def setChecked(self, ticked: Any) -> None:  # noqa: N802
        """Tick this radio, clearing the others in its group box."""
        on = bool(ticked)
        if on:
            for other in radio_siblings(self._name):
                self._owner.store().values[other] = False
        self._put(on)

    def admit(self, value: Any) -> None:
        """Take one operator tick, clearing the others in its group box."""
        self.setChecked(value)


class PageNumber(_Held):
    """A number box or a slider, as ``QSpinBox`` reports it."""

    def value(self) -> Any:
        """The number the control is showing."""
        return self._get()

    def setValue(self, number: Any) -> None:  # noqa: N802
        """Show ``number`` and redraw. The spec's kind decides the type."""
        self._put(number)


class PageCombo(_Held):
    """A drop-down, as ``QComboBox`` reports it.

    ``items`` is the list the Qt side loads: a pair of words and data for a
    ``combo_data`` control, and plain words for a ``combo_text`` one.
    """

    def __init__(self, owner: Any, name: str, items: Any) -> None:
        super().__init__(owner, name)
        self._items = [
            list(one) if isinstance(one, (list, tuple)) else one for one in items
        ]

    def items(self) -> list:
        """The choices the drop-down offers, in painted order."""
        return list(self._items)

    def _at(self) -> Any:
        held = self._get()
        try:
            at = int(held)
        except (TypeError, ValueError):
            return None
        return self._items[at] if 0 <= at < len(self._items) else None

    def currentText(self) -> str:  # noqa: N802
        """The words the drop-down is showing."""
        one = self._at()
        if one is None:
            return ""
        return str(one[0]) if isinstance(one, list) else str(one)

    def currentData(self) -> Any:  # noqa: N802
        """The value carried beside the words, or None for a plain list."""
        one = self._at()
        if one is None:
            return None
        return one[1] if isinstance(one, list) else None

    def setCurrentIndex(self, at: Any) -> None:  # noqa: N802
        """Show the choice at ``at`` and redraw."""
        self._put(at)

    def setCurrentText(self, words: Any) -> None:  # noqa: N802
        """Show the choice whose words are ``words``, if the list holds it."""
        at = self.findText(words)
        if at >= 0:
            self._put(at)

    def findText(self, words: Any) -> int:  # noqa: N802
        """The position of ``words`` in the list, or -1."""
        for at, one in enumerate(self._items):
            found = one[0] if isinstance(one, list) else one
            if str(found) == str(words):
                return at
        return -1

    def findData(self, value: Any) -> int:  # noqa: N802
        """The position of the choice carrying ``value``, or -1."""
        for at, one in enumerate(self._items):
            if isinstance(one, list) and one[1] == value:
                return at
        return -1


class ListRow:
    """One line of a ``PageList``, as ``QListWidgetItem`` reports it."""

    def __init__(self, words: str) -> None:
        self._words = words

    def text(self) -> str:
        """The words on the line."""
        return self._words


class PageList(_Held):
    """The configured-exchange list, as ``QListWidget`` reports it."""

    def __init__(self, owner: Any, name: str) -> None:
        super().__init__(owner, name)
        self._current = -1

    def _lines(self) -> list:
        held = self._get()
        return list(held) if isinstance(held, list) else []

    def count(self) -> int:
        """How many lines the list holds."""
        return len(self._lines())

    def addItem(self, words: Any) -> None:  # noqa: N802
        """Append ``words`` as the last line and redraw."""
        lines = self._lines()
        lines.append(str(words))
        self._put(lines)

    def setCurrentRow(self, at: Any) -> None:  # noqa: N802
        """Select the line at ``at``."""
        try:
            self._current = int(at)
        except (TypeError, ValueError):
            self._current = -1

    def currentItem(self) -> Optional[ListRow]:  # noqa: N802
        """The selected line, or None while nothing is selected."""
        lines = self._lines()
        if 0 <= self._current < len(lines):
            return ListRow(lines[self._current])
        return None

    def row(self, item: Any) -> int:
        """The position of ``item`` in the list, or -1."""
        words = item.text() if item is not None else None
        lines = self._lines()
        return lines.index(words) if words in lines else -1

    def takeItem(self, at: Any) -> Optional[ListRow]:  # noqa: N802
        """Remove the line at ``at``, redraw, and return it."""
        lines = self._lines()
        try:
            found = int(at)
        except (TypeError, ValueError):
            return None
        if not 0 <= found < len(lines):
            return None
        words = lines.pop(found)
        self._current = -1
        self._put(lines)
        return ListRow(words)


class PageText:
    """A label the dialog writes words and a style into."""

    def __init__(self, owner: Any, name: str) -> None:
        self._owner = owner
        self._name = name

    def text(self) -> str:
        """The words the label is showing."""
        held = self._owner.store().texts.get(self._name)
        return "" if held is None else str(held)

    def setText(self, words: Any) -> None:  # noqa: N802
        """Show ``words`` and redraw."""
        self._owner.set_text(self._name, "" if words is None else str(words))

    def setStyleSheet(self, sheet: Any) -> None:  # noqa: N802
        """Paint the label with ``sheet`` and redraw."""
        self._owner.set_style(self._name, "" if sheet is None else str(sheet))


class PagePress:
    """A button the dialog turns on and off."""

    def __init__(self, owner: Any, name: str) -> None:
        self._owner = owner
        self._name = name

    def isEnabled(self) -> bool:  # noqa: N802
        """True while the button takes a press."""
        return self._owner.store().enabled.get(self._name) is True

    def setEnabled(self, on: Any) -> None:  # noqa: N802
        """Take presses or refuse them, and redraw."""
        self._owner.set_enabled(self._name, bool(on))


#: The holder class each control kind is drawn by.
HOLDER_BY_KIND = {
    surface.LINE: PageLine,
    surface.TEXT_AREA: PageTextArea,
    surface.CHECK: PageToggle,
    surface.RADIO: PageRadio,
    surface.SPIN: PageNumber,
    surface.DOUBLE_SPIN: PageNumber,
    surface.SLIDER: PageNumber,
    surface.LIST: PageList,
}

#: The labels the dialog writes into, beside the named controls.
TEXT_NAMES: tuple[str, ...] = (
    "api_feedback",
    "ai_status",
    "ai_hash",
    "ai_checks",
    "font_preview",
    "vol_label",
)

#: Every button the dialog turns on or off.
PRESS_NAMES: tuple[str, ...] = tuple(surface.BUTTON_NAMES_BY_TEXT.values())

#: What the page reports a press of each button as, and the method it runs.
ACTION_HANDLERS: dict[str, str] = {
    "test_btn": "_test_api_connection",
    "add_btn": "_add_exchange",
    "remove_btn": "_remove_exchange",
    "ai_test_btn": "_test_ai_handshake",
    "cancel_btn": "reject",
    "save_btn": "_save",
}

#: The control whose edit runs a method, and the method it runs.
EDIT_HANDLERS: dict[str, str] = {
    "new_exchange": "_on_exchange_changed",
    "font_family": "_update_font_preview",
    "font_size": "_update_font_preview",
    "sound_volume": "_on_sfx_volume_changed",
}


def combo_items(name: str, wing: str = surface.DEFAULT_WING) -> tuple:
    """The choices one drop-down offers, from the module the Qt side reads.

    ``theme_combo`` comes from ``theme_engine`` and ``new_exchange`` follows
    ``wing``; every other drop-down carries its list on its spec.
    """
    if name == "theme_combo":
        from .theme_engine import THEMES

        return tuple((tokens.display_name, key) for key, tokens in THEMES.items())
    if name == "new_exchange":
        return tuple(tuple(one) for one in surface.exchange_items(wing))
    return tuple(surface.spec_for(name).get("items") or ())


if _HAS_QT and _HAS_WEBENGINE:

    class SettingsDialogPage(QWebEnginePage):
        """Routes the page's ``acervator-`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the dialog that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an edit or a press to the owner and drop every other line."""
            del level, line, source
            if message.startswith(EDIT_PREFIX):
                self._owner.apply_edit(message[len(EDIT_PREFIX) :])
            elif message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class SettingsDialogReact(SettingsDialog):
        """The Settings dialog with all eleven tabs drawn by React."""

        def _setup_ui(self) -> None:
            """Build the one web view the whole dialog is drawn in.

            Every control the Qt dialog builds gets a page-backed holder under
            the same attribute name, so ``_load_current`` and ``_save`` run
            unchanged.
            """
            self._model = surface.SettingsDialogModel(wing=self._wing)
            self._model.build()
            self._tab = surface.TAB_TITLES[0]
            self._page_ready = False
            self._last_model: dict = {}
            self._passphrase_exchanges = surface.PASSPHRASE_EXCHANGE_IDS
            self._ta_weight_sliders: dict = {}
            self._phantom_tf_checks: dict = {}
            self._build_holders()

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = SettingsDialogPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(dialog_html(self._theme_name()))
            layout.addWidget(self._web, 1)

        # -- the store every holder reads and writes ---------------------

        def store(self) -> surface.SettingsDialogModel:
            """The dialog's values, texts, styles and enabled flags."""
            return self._model

        def set_value(self, name: str, value: Any) -> None:
            """Take ``value`` for ``name`` the way its control admits it."""
            self._model.admit(name, value)
            self.redraw()

        def set_text(self, name: str, words: str) -> None:
            """Show ``words`` in the label named ``name``."""
            self._model.texts[name] = words
            self.redraw()

        def set_style(self, name: str, sheet: str) -> None:
            """Paint the part named ``name`` with ``sheet``."""
            self._model.styles[name] = sheet
            self.redraw()

        def set_enabled(self, name: str, on: bool) -> None:
            """Let the part named ``name`` take a press, or refuse one."""
            self._model.enabled[name] = on
            self.redraw()

        def set_visible(self, name: str, shown: bool) -> None:
            """Draw the part named ``name``, or leave it out."""
            self._model.visible[name] = shown
            self.redraw()

        # -- what the render path pushes through -------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        @property
        def tab(self) -> str:
            """The tab the page is showing."""
            return self._tab

        def model(self) -> dict:
            """A copy of the last payload pushed, empty before the first push."""
            return dict(self._last_model)

        def redraw(self) -> None:
            """Build the payload from the store and push it to the page."""
            found = surface.build_view_model(self._model)
            found["control_specs"] = [
                (
                    {**spec, "items": [list(one) for one in combo_items(spec["name"])]}
                    if spec["kind"] in (surface.COMBO_TEXT, surface.COMBO_DATA)
                    else spec
                )
                for spec in found["control_specs"]
            ]
            self._last_model = found
            if self._page_ready:
                self._run(push_script(found, self._tab))

        def control_count(self, callback: Callable[[Any], None]) -> bool:
            """Count the drawn controls and hand the number to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(CONTROL_COUNT_JS, callback)
            return True

        # -- what the page reports back ----------------------------------

        def apply_edit(self, payload: str) -> None:
            """Take one operator edit and run whatever the control is wired to."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Settings page sent an edit that is not JSON")
                return
            name = str(asked.get("name") or "")
            if name not in self._holders:
                return
            self._holders[name].admit(asked.get("value"))
            if name == "pp_check":
                self._new_passphrase.setVisible(self._pp_check.isChecked())
            if name == "sound_volume":
                self._vol_label.setText(f"{self._sound_volume.value()}%")
            handler = EDIT_HANDLERS.get(name)
            if handler is not None:
                getattr(self, handler)()

        def run_action(self, payload: str) -> None:
            """Run the button, tab or list row the page reports."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Settings page sent an action that is not JSON")
                return
            if "tab" in asked:
                self.show_tab(str(asked.get("tab") or ""))
                return
            if "row" in asked:
                self._exchange_list.setCurrentRow(asked.get("row"))
                return
            handler = ACTION_HANDLERS.get(str(asked.get("key") or ""))
            if handler is not None:
                getattr(self, handler)()

        def show_tab(self, title: str) -> None:
            """Draw the tab named ``title`` and leave the others hidden."""
            if title in surface.TAB_TITLES:
                self._tab = title
                self.redraw()

        # -- internals ----------------------------------------------------

        def _theme_name(self) -> str:
            if not self._sm:
                return "cyberpunk_dark"
            return str(self._sm.get("theme", "cyberpunk_dark"))

        def _build_holders(self) -> None:
            self._holders: dict = {}
            for spec in surface.CONTROL_SPECS:
                name = spec["name"]
                kind = spec["kind"]
                if kind in (surface.COMBO_TEXT, surface.COMBO_DATA):
                    held: Any = PageCombo(self, name, combo_items(name))
                else:
                    held = HOLDER_BY_KIND[kind](self, name)
                self._holders[name] = held
                setattr(self, "_" + name, held)
            for name in TEXT_NAMES:
                setattr(self, "_" + name, PageText(self, name))
            for name in PRESS_NAMES:
                setattr(self, "_" + name, PagePress(self, name))

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Settings dialog page failed to load")
                return
            self.redraw()
