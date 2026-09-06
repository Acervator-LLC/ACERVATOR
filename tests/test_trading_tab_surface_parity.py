"""The Qt Trading tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, colour,
size, tooltip, caption, splitter, timer, buffer or watchdog line than
``TradingTabMixin`` builds and runs on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.gui.main_tabs import trading_tab_surface as surface

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "trading_tab.py"

ALIGN_CENTER = "center"

SPLITTER_VARIABLE = {
    "main_splitter": "main_splitter",
    "top_splitter": "top_splitter",
    "bottom_splitter": "bottom_splitter",
    "log_splitter": "log_splitter",
}


@pytest.fixture(scope="module")
def qapp():
    """The application object the widget comparisons render against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    running = QApplication.instance()
    return running if running is not None else QApplication(sys.argv)


@pytest.fixture
def booted(qapp):
    """The Trading tab built by the Qt mixin, with its tab widget.

    The API log's listener list is restored afterwards, so the module
    leaves nothing behind for the rest of the suite.
    """
    from PySide6.QtWidgets import QTabWidget, QWidget

    from src.exchange.api_logger import get_api_log
    from src.gui.main_tabs.trading_tab import TradingTabMixin

    api_log = get_api_log()
    saved_listeners = list(api_log._listeners)

    class _Host(QWidget, TradingTabMixin):
        def __init__(self, tabs) -> None:
            QWidget.__init__(self)
            self.setAccessibleName("Trading tab parity host")
            self._main_tabs = tabs
            self._bot_manager = None
            self.add_exchange_calls = 0

        def _add_exchange(self, *args) -> None:
            self.add_exchange_calls += 1

        def _on_api_event(self, *args) -> None:
            return None

    tabs = QTabWidget()
    host = _Host(tabs)
    host._build_trading_tab()
    try:
        yield host, tabs
    finally:
        host._activity_log_watchdog_timer.stop()
        api_log._listeners[:] = saved_listeners
        host.deleteLater()
        tabs.deleteLater()
        qapp.processEvents()


def run_watchdog_once(host) -> None:
    """Fire the Qt watchdog. It is a closure reachable only by its timer."""
    host._activity_log_watchdog_timer.timeout.emit()


def style_tokens(sheet, checked=False) -> dict:
    """The declared values inside one pause button's stylesheet.

    Read from the Qt widget's own sheet, so the surface's tokens are
    compared against the string the widget carries rather than against
    themselves.
    """
    blocks = {}
    for chunk in sheet.split("}"):
        if "{" not in chunk:
            continue
        selector, body = chunk.split("{", 1)
        blocks[selector.strip()] = {
            part.split(":", 1)[0].strip(): part.split(":", 1)[1].strip()
            for part in body.split(";")
            if ":" in part
        }
    base = blocks["QPushButton"]
    hover = blocks.get("QPushButton:hover", {})
    found = {
        "background": base["background"],
        "color": base["color"],
        "border": base["border"],
        "border_radius_px": int(base["border-radius"].removesuffix("px")),
        "padding_px": [
            int(value.removesuffix("px")) for value in base["padding"].split()
        ],
        "font_size_px": int(base["font-size"].removesuffix("px")),
        "hover_background": hover["background"],
    }
    if checked:
        skin = blocks["QPushButton:checked"]
        found["checked_background"] = skin["background"]
        found["checked_color"] = skin["color"]
        found["checked_border"] = skin["border"]
    return found


def document_blocks(view) -> list:
    """Every block of a plain-text view, in order."""
    found = []
    block = view.document().begin()
    while block.isValid():
        found.append(block.text())
        block = block.next()
    return found


def margins(layout) -> list:
    box = layout.contentsMargins()
    return [box.left(), box.top(), box.right(), box.bottom()]


def align_name(flag) -> str:
    """The surface's alignment name for one Qt alignment value."""
    from PySide6.QtCore import Qt

    return ALIGN_CENTER if int(flag) == int(Qt.AlignCenter) else str(int(flag))


def child_name(widget, host) -> str:
    """The surface's name for one splitter child, found by identity.

    Each name is decided by a landmark the child holds, so two children
    swapped in a splitter report swapped names rather than the order the
    test expected.
    """
    from PySide6.QtWidgets import QSplitter

    if widget is host._trading_stack:
        return "trading_stack"
    if widget is host._indicator_panel:
        return "indicator_panel"
    if isinstance(widget, QSplitter):
        if widget.indexOf(host._trading_stack) >= 0:
            return "top_splitter"
        held = [widget.widget(index) for index in range(widget.count())]
        if any(isinstance(child, QSplitter) for child in held):
            return "bottom_splitter"
        return "log_splitter"
    if host._status_log.parentWidget() is widget:
        return "activity_pane"
    if host._api_log_view.parentWidget() is widget:
        return "api_pane"
    raise LookupError(widget)


def splitter_trace(split, key, host) -> dict:
    names = [child_name(split.widget(index), host) for index in range(split.count())]
    return {
        "orientation": split.orientation().name.lower(),
        "handle_width_px": split.handleWidth(),
        "children_collapsible": split.childrenCollapsible(),
        "children": names,
        "sizes_px": requested_sizes()[key],
    }


def requested_sizes() -> dict:
    """The list each ``setSizes`` call in the Qt tab is given, by splitter.

    Read from the source because ``QSplitter.sizes()`` reports the
    distribution for the splitter's current height, not the request.
    """
    tree = ast.parse(TAB_SOURCE.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setSizes"
            and isinstance(node.func.value, ast.Name)
        ):
            found[SPLITTER_VARIABLE[node.func.value.id]] = ast.literal_eval(
                node.args[0]
            )
    return found


def card_order(card_layout) -> list:
    """The empty-state card's slots, named by the widget in each.

    Both labels carry the same class, so the first is read as the title
    and any later one as the hint; the text and skin compared for each
    slot are what tell a swap of the two apart.
    """
    from PySide6.QtWidgets import QPushButton

    names = []
    for index in range(card_layout.count()):
        widget = card_layout.itemAt(index).widget()
        if isinstance(widget, QPushButton):
            names.append("add_button")
        else:
            names.append("hint" if "title" in names else "title")
    return names


def accent_of(sheet: str) -> str:
    """The layer accent the card's border carries, read back out of its rgba."""
    written = sheet.split("1px solid ")[1].split(";")[0].strip()
    fields = written[len("rgba(") : -1].split(",")
    return "#" + "".join(f"{int(one.strip()):02x}" for one in fields[:3])


def layer_tabs_trace(host, index) -> dict:
    """One layer's exchange tabs, the tab on show and the empty-state tab."""
    page = host._trading_stack.widget(index)
    tab_widget = page.layout().itemAt(0).widget()
    tabs_map = host._crypto_exchange_tabs if index == 0 else host._stock_exchange_tabs
    held = getattr(host, "_crypto_placeholder" if index == 0 else "_stock_placeholder")
    on_show = tab_widget.currentWidget()
    return {
        "exchange_tabs": {
            eid: tab_widget.tabText(tab_widget.indexOf(tab))
            for eid, tab in tabs_map.items()
        },
        "current_exchange": next(
            (eid for eid, tab in tabs_map.items() if tab is on_show), ""
        ),
        "placeholder_shown": held is not None and tab_widget.indexOf(held) >= 0,
    }


def layer_trace(host, index) -> dict:
    """One built layer page, read back as plain data."""
    page = host._trading_stack.widget(index)
    page_layout = page.layout()
    tab_widget = page_layout.itemAt(0).widget()
    corner = tab_widget.cornerWidget()
    placeholder = tab_widget.widget(0)
    outer = placeholder.layout()
    card = outer.itemAt(0).widget()
    card_layout = card.layout()
    title = card_layout.itemAt(0).widget()
    add = card_layout.itemAt(1).widget()
    hint = card_layout.itemAt(2).widget()
    return {
        "key": corner.text().split()[-2].lower(),
        "label": corner.text().split()[-2],
        "accent": accent_of(card.styleSheet()),
        "page_layout": {
            "margins_px": margins(page_layout),
            "children": ["tab_widget"],
        },
        "add_button": {
            "text": corner.text(),
            "tooltip": corner.toolTip(),
            "minimum_width_px": corner.minimumWidth(),
            "corner_widget": tab_widget.cornerWidget() is not None,
        },
        "placeholder": {
            "tab_title": tab_widget.tabText(0),
            "align": align_name(outer.itemAt(0).alignment()),
            "spacing_px": card_layout.spacing(),
            "order": card_order(card_layout),
            "outer_layout": {
                "margins_px": margins(outer),
                "spacing_px": outer.spacing(),
            },
            "card": {
                "minimum_size_px": [card.minimumWidth(), card.minimumHeight()],
                "style_sheet": card.styleSheet(),
                "layout": {
                    "margins_px": margins(card_layout),
                    "spacing_px": card_layout.spacing(),
                },
            },
            "title": {
                "text": title.text(),
                "style_sheet": title.styleSheet(),
                "align": align_name(title.alignment()),
            },
            "add_button": {
                "text": add.text(),
                "minimum_size_px": [add.minimumWidth(), add.minimumHeight()],
                "style_sheet": add.styleSheet(),
                "align": align_name(card_layout.itemAt(1).alignment()),
            },
            "hint": {
                "text": hint.text(),
                "style_sheet": hint.styleSheet(),
                "align": align_name(hint.alignment()),
            },
        },
        **layer_tabs_trace(host, index),
    }


def qt_trace(host, tabs) -> dict:
    """Every value the built Qt tab can be asked for, as plain data."""
    container = tabs.widget(0)
    outer = container.layout()
    main_split = outer.itemAt(0).widget()
    top_split = main_split.widget(0)
    bottom_split = main_split.widget(1)
    log_split = bottom_split.widget(0)
    activity = log_split.widget(0)
    activity_layout = activity.layout()
    activity_header = activity_layout.itemAt(0).layout()
    activity_label = activity_header.itemAt(0).widget()
    api = log_split.widget(1)
    api_layout = api.layout()
    api_header = api_layout.itemAt(0).layout()
    api_label = api_header.itemAt(0).widget()
    view = host._api_log_view
    button = host._activity_pause_btn
    api_button = host._api_pause_btn
    layers = [layer_trace(host, index) for index in range(host._trading_stack.count())]
    return {
        "tab_title": tabs.tabText(0),
        "container": {
            "margins_px": margins(outer),
            "spacing_px": outer.spacing(),
            "children": ["main_splitter"],
        },
        "main_splitter": splitter_trace(main_split, "main_splitter", host),
        "top_splitter": splitter_trace(top_split, "top_splitter", host),
        "bottom_splitter": splitter_trace(bottom_split, "bottom_splitter", host),
        "log_splitter": splitter_trace(log_split, "log_splitter", host),
        "equity_exchange_ids": sorted(host._equity_exchange_ids),
        "trading_stack": {
            "pages": [layer["key"] for layer in layers],
            "current_index": host._trading_stack.currentIndex(),
        },
        "layers": layers,
        "alias_layer": (
            "crypto" if host._tab_widget is host._crypto_tab_widget else "stock"
        ),
        "chart_present": host._chart is not None,
        "activity_pane": {
            "layout": {
                "margins_px": margins(activity_layout),
                "spacing_px": activity_layout.spacing(),
                "children": ["header_row", "status_log"],
            },
            "header_row": {
                "margins_px": margins(activity_header),
                "spacing_px": activity_header.spacing(),
            },
            "header_row_order": header_order(activity_header),
            "label": {
                "text": activity_label.text(),
                "style_sheet": activity_label.styleSheet(),
            },
            "pause_button": {
                "text": button.text(),
                "checkable": button.isCheckable(),
                "checked": button.isChecked(),
                "tooltip": button.toolTip(),
                "style_sheet": button.styleSheet(),
                **style_tokens(button.styleSheet(), checked=True),
            },
            "status_log": {
                "maximum_height_px": host._status_log.maximumHeight(),
                "notify_relay": host._spool._log is host._status_log,
            },
        },
        "api_pane": {
            "layout": {
                "margins_px": margins(api_layout),
                "spacing_px": api_layout.spacing(),
                "children": ["header_row", "log_view"],
            },
            "header_row": {
                "margins_px": margins(api_header),
                "spacing_px": api_header.spacing(),
            },
            "header_row_order": header_order(api_header),
            "label": {
                "text": api_label.text(),
                "style_sheet": api_label.styleSheet(),
            },
            "pause_button": {
                "text": api_button.text(),
                "checkable": api_button.isCheckable(),
                "checked": api_button.isChecked(),
                "tooltip": api_button.toolTip(),
                "style_sheet": api_button.styleSheet(),
                **style_tokens(api_button.styleSheet()),
            },
            "pause_buffer": {
                "paused": host._api_log_paused,
                "buffered": len(host._api_log_pause_buffer),
                "cap": host._api_log_pause_buffer_cap,
            },
            "log_view": {
                "read_only": view.isReadOnly(),
                "tab_index": tab_index(view),
                "placeholder": view.placeholderText(),
                "tooltip": view.toolTip(),
                "wrap": view.lineWrapMode().name != "NoWrap",
                "max_blocks": view.maximumBlockCount(),
                "text": view.toPlainText(),
                "blocks": document_blocks(view),
                "block_count": view.blockCount(),
                "is_empty": view.document().isEmpty(),
            },
        },
        "watchdog": {
            "interval_ms": host._activity_log_watchdog_timer.interval(),
            "running": host._activity_log_watchdog_timer.isActive(),
            "silence_sec": watchdog_thresholds()[0],
            "alert_throttle_sec": watchdog_thresholds()[1],
            "critical_sec": watchdog_thresholds()[2],
            "critical_throttle_sec": watchdog_thresholds()[3],
            "last_errors": host._activity_log_last_errors,
            "alert_sent_at": host._activity_log_alert_sent_at,
            "critical_sent_at": host._activity_log_critical_sent_at,
        },
        "api_log_listener": api_listener_name(host),
        "actions": translated_connect_sites(),
    }


HEADER_SLOT = {"QLabel": "label", "QPushButton": "pause_button"}

TAB_ORDER_INDEX = 0
NO_TAB_ORDER_INDEX = -1


def tab_index(view) -> int:
    """The tab-order place a focusable Qt view takes on a page."""
    from PySide6.QtCore import Qt

    if view.focusPolicy() == Qt.FocusPolicy.NoFocus:
        return NO_TAB_ORDER_INDEX
    return TAB_ORDER_INDEX


def api_listener_name(host) -> str:
    """The handler the built tab left on the shared API interaction log."""
    from src.exchange.api_logger import get_api_log

    listeners = get_api_log()._listeners
    for callback in listeners:
        if getattr(callback, "__self__", None) is host:
            return callback.__name__.lstrip("_")
    return ""


def header_order(row) -> list:
    """The slots of one pane header row, named by the widget in each."""
    names = []
    for index in range(row.count()):
        widget = row.itemAt(index).widget()
        names.append(
            "stretch" if widget is None else HEADER_SLOT[type(widget).__name__]
        )
    return names


def watchdog_thresholds() -> tuple:
    """The four second thresholds the Qt watchdog compares against.

    Each is the right side of a ``>`` test, taken in source order: the
    silence window, its re-alert throttle, the critical window and its
    own throttle.
    """
    tree = ast.parse(TAB_SOURCE.read_text(encoding="utf-8"))
    watchdog = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_activity_log_watchdog"
    )
    found = []
    for node in ast.walk(watchdog):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        right = node.comparators[0]
        if isinstance(node.ops[0], ast.Gt) and isinstance(right, ast.Constant):
            found.append((right.lineno, right.col_offset, right.value))
    return tuple(value for _line, _col, value in sorted(found))


def surface_trace() -> dict:
    """The same values, read from the Qt-free view model."""
    return surface.build_view_model()


def digest(trace) -> str:
    return hashlib.sha256(
        json.dumps(trace, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def test_the_built_tab_and_the_surface_describe_the_same_tab(booted):
    """A control, colour, size, tooltip, caption or counter differs."""
    host, tabs = booted
    old = qt_trace(host, tabs)
    new = surface_trace()
    assert new == old
    assert digest(new) == digest(old)


def test_the_trace_carries_every_part_of_the_tab(booted):
    """The comparison passed by comparing an empty or partial trace."""
    host, tabs = booted
    old = qt_trace(host, tabs)
    assert set(old) == set(surface_trace())
    assert len(old) == 16
    assert old["api_log_listener"] == "on_api_event"
    assert [layer["label"] for layer in old["layers"]] == ["Crypto", "Stock"]
    assert old["layers"][0]["accent"] != old["layers"][1]["accent"]
    assert len(old["equity_exchange_ids"]) == 9
    assert old["activity_pane"]["header_row_order"] == [
        "label",
        "stretch",
        "pause_button",
    ]
    assert old["api_pane"]["log_view"]["max_blocks"] == 2000
    assert old["watchdog"]["interval_ms"] == 60000


def test_the_two_pause_buttons_are_not_the_same_control(booted):
    """The trace reads one pause button twice, so a swap would not show."""
    host, _tabs = booted
    assert host._activity_pause_btn is not host._api_pause_btn
    activity = surface.activity_pause_button()
    api = surface.api_pause_button()
    assert activity["text"] != api["text"]
    assert activity["tooltip"] != api["tooltip"]
    assert activity["style_sheet"] != api["style_sheet"]
    assert "checked" in activity["style_sheet"]
    assert "checked" not in api["style_sheet"]


def test_the_layer_trace_reads_an_exchange_tab_the_layer_holds(booted):
    """The trace reports an empty layer whatever the tab widget holds."""
    host, _tabs = booted
    from PySide6.QtWidgets import QWidget

    pane = QWidget()
    widget = host._crypto_tab_widget
    widget.removeTab(widget.indexOf(host._crypto_placeholder))
    host._crypto_placeholder = None
    widget.addTab(pane, "Coinbase")
    host._crypto_exchange_tabs["coinbase"] = pane
    try:
        read = layer_tabs_trace(host, 0)
    finally:
        host._crypto_exchange_tabs.pop("coinbase")
        widget.removeTab(widget.indexOf(pane))
        pane.deleteLater()
    assert read["exchange_tabs"] == {"coinbase": "Coinbase"}, read
    assert read["current_exchange"] == "coinbase", read
    assert read["placeholder_shown"] is False, read


def test_a_layer_card_carries_the_exchanges_it_is_given():
    """The surface reports an empty layer whatever exchanges it is given."""
    card = surface.layer_card("crypto", {"coinbase": "Coinbase"})
    assert card["exchange_tabs"] == {"coinbase": "Coinbase"}, card
    assert card["current_exchange"] == "coinbase", card
    assert card["placeholder_shown"] is False, card
    empty = surface.layer_card("crypto")
    assert empty["exchange_tabs"] == {}, empty
    assert empty["current_exchange"] == "", empty
    assert empty["placeholder_shown"] is True, empty


def test_the_stock_layer_takes_the_equity_exchanges():
    """An equity exchange lands on the crypto layer the operator watches."""
    routed = surface.layer_exchanges(
        [
            {"exchange_id": "coinbase", "display_name": "Coinbase"},
            {"exchange_id": "alpaca", "display_name": "Alpaca"},
            {"exchange_id": "", "display_name": "Nameless"},
        ]
    )
    assert routed["crypto"] == {"coinbase": "Coinbase"}, routed
    assert routed["stock"] == {"alpaca": "Alpaca"}, routed


def test_an_exchange_with_no_display_name_is_captioned_from_its_id():
    """A blank caption reaches the tab bar."""
    assert surface.exchange_display_name({"exchange_id": "kraken"}) == "Kraken"
    assert (
        surface.exchange_display_name({"exchange_id": "kraken", "display_name": ""})
        == "Kraken"
    )
    assert (
        surface.exchange_display_name({"exchange_id": "kraken", "display_name": "KR"})
        == "KR"
    )


def test_the_aliases_point_at_the_crypto_layer(booted):
    """An alias points at the stock layer, which the operator cannot see."""
    host, _tabs = booted
    assert host._tab_widget is host._crypto_tab_widget
    assert host._tab_widget is not host._stock_tab_widget
    assert host._empty_placeholder is host._crypto_placeholder
    assert host._empty_placeholder is not host._stock_placeholder
    assert host._exchange_tabs is host._crypto_exchange_tabs
    assert host._exchange_tabs is not host._stock_exchange_tabs
    assert surface.ALIAS_LAYER == "crypto"


def test_the_stack_holds_the_layers_in_the_declared_order(booted):
    """A layer sits on the page the surface gives the other one."""
    host, _tabs = booted
    crypto_page = host._crypto_tab_widget.parentWidget()
    stock_page = host._stock_tab_widget.parentWidget()
    assert host._trading_stack.count() == 2
    assert host._trading_stack.indexOf(crypto_page) == 0
    assert host._trading_stack.indexOf(stock_page) == 1
    assert host._trading_stack.currentIndex() == 0
    assert surface.LAYER_ORDER == ("crypto", "stock")


def test_the_bottom_splitter_is_given_a_size_for_a_child_it_lacks(booted):
    """The second bottom size reaches a child, or the surface hides that."""
    host, tabs = booted
    container = tabs.widget(0)
    bottom = container.layout().itemAt(0).widget().widget(1)
    assert bottom.count() == 1
    assert len(surface.BOTTOM_SPLITTER["children"]) == 1
    assert len(surface.BOTTOM_SPLITTER["sizes_px"]) == 2
    assert requested_sizes()["bottom_splitter"] == [120, 300]


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites() -> list:
    """Every ``.connect(`` site in the Qt tab, as signal and target."""
    tree = ast.parse(TAB_SOURCE.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            found.append((dotted(node.func.value), dotted(node.args[0])))
    return sorted(found)


QT_SIGNAL_NAMES = {
    "add_btn.clicked": "layer.add_button.clicked",
    "ph_add.clicked": "layer.placeholder_add_button.clicked",
    "self._activity_pause_btn.toggled": "activity_pause_button.toggled",
    "self._api_pause_btn.toggled": "api_pause_button.toggled",
    "self._activity_log_watchdog_timer.timeout": "watchdog_timer.timeout",
}

QT_TARGET_NAMES = {
    "self._add_exchange": "add_exchange",
    "_on_activity_pause_toggled": "toggle_activity_pause",
    "_on_api_pause_toggled": "toggle_api_pause",
    "_activity_log_watchdog": "run_activity_log_watchdog",
}


def translated_connect_sites() -> dict:
    return {
        QT_SIGNAL_NAMES[signal]: QT_TARGET_NAMES[target]
        for signal, target in connect_sites()
    }


def test_the_connect_sets_match():
    """The Qt tab connects a signal the surface names no action for."""
    sites = connect_sites()
    assert len(sites) == 5
    assert translated_connect_sites() == surface.ACTIONS


def test_the_connect_reader_finds_the_real_sites():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites()
    assert ("add_btn.clicked", "self._add_exchange") in sites
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)


def test_both_add_buttons_of_both_layers_call_add_exchange(booted):
    """An add button is wired to nothing, or to the wrong handler."""
    host, _tabs = booted
    for index in range(2):
        page = host._trading_stack.widget(index)
        tab_widget = page.layout().itemAt(0).widget()
        tab_widget.cornerWidget().click()
        card = tab_widget.widget(0).layout().itemAt(0).widget()
        card.layout().itemAt(1).widget().click()
    assert host.add_exchange_calls == 4


ACTIVITY_TOGGLE_SCRIPT = [True, False, True, True, False, False]


def test_the_activity_pause_toggle_matches(booted):
    """The pause toggle leaves a caption or a log state the surface denies."""
    host, _tabs = booted
    button = host._activity_pause_btn
    old = []
    new = []
    for checked in ACTIVITY_TOGGLE_SCRIPT:
        button.setChecked(checked)
        old.append(
            {
                "text": button.text(),
                "checked": button.isChecked(),
                "paused": host._status_log.is_paused(),
            }
        )
        card = surface.activity_pause_button(checked)
        new.append(
            {
                "text": card["text"],
                "checked": card["checked"],
                "paused": surface.activity_toggle(checked)["paused"],
            }
        )
    assert new == old
    assert digest(new) == digest(old)
    assert old[0]["text"] == "▶  Resume Console"
    assert old[1]["text"] == "⏸  Pause Console"


def test_the_activity_toggle_names_the_status_log_call():
    """The toggle resumes when it should pause, or the reverse."""
    assert surface.activity_toggle(True)["status_log"] == "pause"
    assert surface.activity_toggle(False)["status_log"] == "resume"


PAUSE = "pause"
RESUME = "resume"
HOLD = "hold"
SHOW = "show"


def run_old_api_pane(script, host):
    """Drive the built Qt API log through the script and trace it.

    The view, the buffer and the button are emptied first, so a second
    run inside one test starts where the first one did.
    """
    button = host._api_pause_btn
    view = host._api_log_view
    button.setChecked(False)
    host._api_log_pause_buffer.clear()
    view.clear()
    trace = []
    for step in script:
        if step[0] == PAUSE:
            button.setChecked(True)
        elif step[0] == RESUME:
            button.setChecked(False)
        elif step[0] == HOLD:
            host._api_log_pause_buffer.append(step[1])
        else:
            view.appendPlainText(step[1])
        trace.append(
            {
                "text": view.toPlainText(),
                "block_count": view.blockCount(),
                "is_empty": view.document().isEmpty(),
                "paused": host._api_log_paused,
                "buffered": len(host._api_log_pause_buffer),
                "button_text": button.text(),
            }
        )
    return trace


def run_new_api_pane(script, max_blocks=surface.API_LOG_MAX_BLOCKS):
    """Drive the Qt-free buffer and pane through the same script."""
    buffer = surface.ApiPauseBuffer()
    pane = surface.ApiLogPane(max_blocks)
    trace = []
    for step in script:
        if step[0] == PAUSE:
            buffer.toggle(True, pane)
        elif step[0] == RESUME:
            buffer.toggle(False, pane)
        elif step[0] == HOLD:
            buffer.hold(step[1])
        else:
            pane.append(step[1])
        trace.append(
            {
                "text": pane.text(),
                "block_count": pane.block_count(),
                "is_empty": pane.is_empty(),
                "paused": buffer.paused,
                "buffered": len(buffer.lines),
                "button_text": surface.api_pause_button(buffer.paused)["text"],
            }
        )
    return trace


API_SCRIPTS = {
    "flush_three": [
        (PAUSE,),
        (HOLD, "one"),
        (HOLD, "two"),
        (HOLD, "three"),
        (RESUME,),
    ],
    "flush_one": [(PAUSE,), (HOLD, "only"), (RESUME,)],
    "flush_none": [(PAUSE,), (RESUME,)],
    "resume_while_running": [(RESUME,), (RESUME,)],
    "pause_twice": [(PAUSE,), (HOLD, "a"), (PAUSE,), (HOLD, "b"), (RESUME,)],
    "onto_existing_text": [
        (SHOW, "already here"),
        (PAUSE,),
        (HOLD, "held"),
        (RESUME,),
    ],
    "empty_line": [(PAUSE,), (HOLD, ""), (RESUME,)],
    "blank_only": [(PAUSE,), (HOLD, ""), (HOLD, ""), (RESUME,)],
    "embedded_newline": [(PAUSE,), (HOLD, "first\nsecond"), (RESUME,)],
    "trailing_newline": [(PAUSE,), (HOLD, "tail\n"), (RESUME,)],
    "unicode_line": [(PAUSE,), (HOLD, "⚠ £ fee 0.5%"), (RESUME,)],
    "flush_then_hold_again": [
        (PAUSE,),
        (HOLD, "x"),
        (RESUME,),
        (PAUSE,),
        (HOLD, "y"),
        (RESUME,),
    ],
    "show_while_paused": [(PAUSE,), (HOLD, "held"), (SHOW, "bypass"), (RESUME,)],
}


@pytest.mark.parametrize("name", sorted(API_SCRIPTS))
def test_the_api_log_buffers_hold_the_same_text(booted, name):
    """A step fills the Qt-free API log differently from the Qt view."""
    host, _tabs = booted
    old = run_old_api_pane(API_SCRIPTS[name], host)
    new = run_new_api_pane(API_SCRIPTS[name])
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(API_SCRIPTS))
def test_the_api_trace_measured_something(booted, name):
    """The API comparison passed on an empty trace."""
    host, _tabs = booted
    old = run_old_api_pane(API_SCRIPTS[name], host)
    assert len(old) == len(API_SCRIPTS[name])
    assert any(step["paused"] for step in old) or name == "resume_while_running"


def test_the_flush_writes_the_resume_marker(booted):
    """The marker names the wrong count, or is written when nothing was held."""
    host, _tabs = booted
    old = run_old_api_pane(API_SCRIPTS["flush_three"], host)
    assert old[-1]["text"].splitlines()[-1] == (
        "--- (resumed; 3 buffered line(s) above) ---"
    )
    assert surface.resume_marker(3) == old[-1]["text"].splitlines()[-1]
    empty = run_old_api_pane(API_SCRIPTS["flush_none"], host)
    assert "resumed" not in empty[-1]["text"]


def test_the_api_log_view_evicts_at_its_cap(booted):
    """The cap never bites, so no eviction was compared."""
    host, _tabs = booted
    script = [(SHOW, f"r{n}") for n in range(surface.API_LOG_MAX_BLOCKS + 5)]
    old = run_old_api_pane(script, host)
    new = run_new_api_pane(script)
    assert new == old
    assert old[-1]["block_count"] == surface.API_LOG_MAX_BLOCKS
    assert old[-1]["text"].splitlines()[0] == "r5"


def test_the_pause_buffer_stops_at_its_cap():
    """The buffer grows past the cap the tab declares."""
    buffer = surface.ApiPauseBuffer(3)
    for index in range(10):
        buffer.hold(f"line{index}")
    assert buffer.lines == ["line0", "line1", "line2"]
    assert surface.API_PAUSE_BUFFER_CAP == 2000


class _StubLog:
    """A status log that answers ``health_stats`` from a script."""

    def __init__(self, readings) -> None:
        self.readings = list(readings)
        self.written: list = []

    def health_stats(self) -> dict:
        reading = self.readings.pop(0)
        if reading is None:
            raise RuntimeError("stat fetch failed")
        return dict(reading)

    def force_log(self, message, level="warning") -> None:
        self.written.append((message, level))


class _StubBot:
    def __init__(self, state) -> None:
        self.state = type("S", (), {"value": state})()


class _StubManager:
    def __init__(self, states) -> None:
        self._bots = {str(i): _StubBot(state) for i, state in enumerate(states)}


CLOCK = 1_800_000_000.0


def stats(errors=0, age=0.0, paused=False, buffered=0, blocks=1, last=""):
    return {
        "paused": paused,
        "pause_buffer_size": buffered,
        "last_render_age_sec": age,
        "total_renders": 0,
        "render_errors": errors,
        "last_render_error": last,
        "document_blocks": blocks,
    }


WATCHDOG_SCRIPTS = {
    "quiet": ([(stats(), [], CLOCK)], []),
    "first_render_error": (
        [(stats(errors=2, last="ValueError: boom"), [], CLOCK)],
        ["render_error"],
    ),
    "same_error_count_twice": (
        [
            (stats(errors=2, last="a"), [], CLOCK),
            (stats(errors=2, last="a"), [], CLOCK + 1000.0),
        ],
        ["render_error"],
    ),
    "error_count_grows": (
        [
            (stats(errors=1, last="a"), [], CLOCK),
            (stats(errors=4, last="b"), [], CLOCK + 1000.0),
        ],
        ["render_error", "render_error"],
    ),
    "error_count_falls": (
        [
            (stats(errors=5, last="a"), [], CLOCK),
            (stats(errors=2, last="b"), [], CLOCK + 1000.0),
        ],
        ["render_error"],
    ),
    "silence_without_bots": ([(stats(age=900.0), [], CLOCK)], []),
    "silence_with_idle_bots": (
        [(stats(age=900.0), ["stopped", "paused"], CLOCK)],
        [],
    ),
    "silence_at_threshold": ([(stats(age=600.0), ["running"], CLOCK)], []),
    "silence_just_over": ([(stats(age=600.1), ["running"], CLOCK)], ["silence"]),
    "silence_throttled": (
        [
            (stats(age=700.0), ["running"], CLOCK),
            (stats(age=700.0), ["running"], CLOCK + 100.0),
        ],
        ["silence"],
    ),
    "silence_throttle_expires": (
        [
            (stats(age=700.0), ["running"], CLOCK),
            (stats(age=700.0), ["running"], CLOCK + 700.0),
        ],
        ["silence", "silence"],
    ),
    "critical_at_threshold": ([(stats(age=1800.0), ["running"], CLOCK)], ["silence"]),
    "critical_just_over": (
        [(stats(age=1800.1), ["running"], CLOCK)],
        ["silence", "critical"],
    ),
    "critical_throttled": (
        [
            (stats(age=2000.0), ["running"], CLOCK),
            (stats(age=2000.0), ["running"], CLOCK + 1000.0),
        ],
        ["silence", "critical", "silence"],
    ),
    "error_and_silence_together": (
        [(stats(errors=3, age=2000.0, last="x"), ["running", "running"], CLOCK)],
        ["render_error", "silence", "critical"],
    ),
    "unreadable_stats": ([(None, ["running"], CLOCK)], []),
    "unreadable_then_readable": (
        [(None, ["running"], CLOCK), (stats(errors=1), ["running"], CLOCK + 1000.0)],
        ["render_error"],
    ),
    "paused_log_reported": (
        [(stats(age=700.0, paused=True, buffered=12, blocks=44), ["running"], CLOCK)],
        ["silence"],
    ),
    "many_running_bots": (
        [(stats(age=700.0), ["running"] * 7 + ["stopped"], CLOCK)],
        ["silence"],
    ),
}


def run_old_watchdog(steps, host, monkeypatch):
    """Drive the built Qt watchdog through the steps and trace it."""
    log = _StubLog([step[0] for step in steps])
    host._status_log = log
    trace = []
    for _reading, states, now in steps:
        host._bot_manager = _StubManager(states) if states else None
        monkeypatch.setattr(time, "time", lambda now=now: now)
        run_watchdog_once(host)
        trace.append(
            {
                "written": list(log.written),
                "last_errors": host._activity_log_last_errors,
                "alert_sent_at": host._activity_log_alert_sent_at,
                "critical_sent_at": host._activity_log_critical_sent_at,
            }
        )
    return trace


def run_new_watchdog(steps):
    """Drive the Qt-free watchdog through the same steps."""
    state = surface.WatchdogState()
    written: list = []
    trace: list = []
    for reading, states, now in steps:
        running = surface.running_bots(states)
        written.extend(
            surface.watchdog_tick(
                state,
                reading,
                now,
                running=running,
                bots_active=bool(states) and running > 0,
            )
        )
        trace.append(
            {
                "written": [list(pair) for pair in written],
                "last_errors": state.last_errors,
                "alert_sent_at": state.alert_sent_at,
                "critical_sent_at": state.critical_sent_at,
            }
        )
    return trace


def normalise(trace) -> list:
    return [
        {**step, "written": [list(pair) for pair in step["written"]]} for step in trace
    ]


@pytest.mark.parametrize("name", sorted(WATCHDOG_SCRIPTS))
def test_the_watchdog_writes_the_same_lines(booted, monkeypatch, name):
    """The Qt-free watchdog writes a line the Qt watchdog would not."""
    host, _tabs = booted
    steps, _expected = WATCHDOG_SCRIPTS[name]
    old = normalise(run_old_watchdog(steps, host, monkeypatch))
    new = run_new_watchdog(steps)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(WATCHDOG_SCRIPTS))
def test_the_watchdog_scripts_reach_the_branches_they_name(booted, monkeypatch, name):
    """A script names a branch its input never reaches."""
    host, _tabs = booted
    steps, expected = WATCHDOG_SCRIPTS[name]
    old = run_old_watchdog(steps, host, monkeypatch)
    kinds = []
    for message, _level in old[-1]["written"]:
        if "new render" in message:
            kinds.append("render_error")
        elif "CRITICAL" in message:
            kinds.append("critical")
        else:
            kinds.append("silence")
    assert kinds == expected


def test_the_watchdog_line_texts_match_character_for_character(booted, monkeypatch):
    """A watchdog line differs from the Qt line by a character."""
    host, _tabs = booted
    steps = [
        (
            stats(
                errors=3, age=2000.4, paused=True, buffered=9, blocks=77, last="E: x"
            ),
            ["running", "running"],
            CLOCK,
        )
    ]
    old = run_old_watchdog(steps, host, monkeypatch)[-1]["written"]
    assert old[0][0] == surface.render_error_text(3, 3, "E: x")
    assert old[1][0] == surface.silence_text(2000.4, 2, True, 9, 77)
    assert old[2][0] == surface.critical_text(2000.4)
    assert [level for _text, level in old] == ["error", "warning", "error"]


def test_an_unreadable_stats_reading_writes_nothing(booted, monkeypatch, capture_log):
    """A failed health read raised, or wrote a line, instead of warning."""
    host, _tabs = booted
    host._status_log = _StubLog([None])
    host._bot_manager = _StubManager(["running"])
    monkeypatch.setattr(time, "time", lambda: CLOCK)
    with capture_log("acervator.gui", logging.WARNING) as records:
        run_watchdog_once(host)
    assert host._status_log.written == []
    assert host._activity_log_last_errors == 0
    assert [record.msg for record in records] == [surface.WATCHDOG_STAT_FAILURE_FORMAT]
    assert surface.watchdog_tick(surface.WatchdogState(), None, CLOCK) == []


def test_a_bot_manager_without_bots_reads_as_idle(booted, monkeypatch):
    """A bot manager with no bot map is read as if bots were running."""
    host, _tabs = booted
    host._status_log = _StubLog([stats(age=5000.0)])
    host._bot_manager = object()
    monkeypatch.setattr(time, "time", lambda: CLOCK)
    run_watchdog_once(host)
    assert host._status_log.written == []


RENDER_SIZE = (900, 700)
BUTTON_GROUND_INSET = 3


@pytest.fixture
def painted(booted):
    """The Trading tab rendered once, with the widgets it was drawn from.

    The container is taken out of the tab widget first. A widget inside a
    layout is resized back by its parent, so a render of one asks for a
    size it never gets.
    """
    from PySide6.QtWidgets import QApplication

    from qt_pixel import render_widget

    host, tabs = booted
    container = tabs.widget(0)
    tabs.removeTab(0)
    container.setParent(None)
    try:
        yield host, container, render_widget(container, size=RENDER_SIZE)
    finally:
        container.deleteLater()
        QApplication.processEvents()


def colour_at(image, container, widget, point) -> str:
    from qt_pixel import pixel_at

    return pixel_at(image, widget.mapTo(container, point))


def ground_point(widget):
    from PySide6.QtCore import QPoint

    return QPoint(BUTTON_GROUND_INSET, BUTTON_GROUND_INSET)


def test_both_pause_buttons_paint_the_declared_ground(painted):
    """A pause button paints a colour the view model does not declare."""
    host, container, image = painted
    for button, card in (
        (host._activity_pause_btn, surface.activity_pause_button()),
        (host._api_pause_btn, surface.api_pause_button()),
    ):
        assert (
            colour_at(image, container, button, ground_point(button))
            == card["background"]
        )


def test_only_the_activity_button_paints_a_checked_ground(painted):
    """The two buttons share a checked skin, or the model swapped them."""
    from qt_pixel import render_widget

    host, container, _image = painted
    activity = host._activity_pause_btn
    api = host._api_pause_btn
    activity.setChecked(True)
    api.setChecked(True)
    try:
        checked = render_widget(container, size=RENDER_SIZE)
        assert (
            colour_at(checked, container, activity, ground_point(activity))
            == surface.activity_pause_button(True)["checked_background"]
        )
        assert (
            colour_at(checked, container, api, ground_point(api))
            == surface.api_pause_button(True)["background"]
        )
    finally:
        activity.setChecked(False)
        api.setChecked(False)
    back = render_widget(container, size=RENDER_SIZE)
    assert (
        colour_at(back, container, activity, ground_point(activity))
        == surface.activity_pause_button()["background"]
    )


def test_the_pixel_reader_reports_a_wrong_colour(painted):
    """The pixel check passes whatever the widget painted."""
    from PySide6.QtCore import QPoint

    from qt_pixel import assert_pixel_colour

    host, container, image = painted
    button = host._activity_pause_btn
    point = button.mapTo(container, ground_point(button))
    assert_pixel_colour(container, point, surface.activity_pause_button()["background"])
    with pytest.raises(AssertionError):
        assert_pixel_colour(container, point, "#ffffff")
    with pytest.raises(IndexError):
        colour_at(image, container, button, QPoint(-5000, -5000))


def test_the_parts_sit_where_the_view_model_orders_them(painted):
    """A part sits somewhere other than the order the model declares."""
    host, container, _image = painted
    main_split = container.layout().itemAt(0).widget()
    top = main_split.widget(0)
    bottom = main_split.widget(1)
    logs = bottom.widget(0)

    def box(widget):
        top_left = widget.mapTo(container, widget.rect().topLeft())
        return top_left.x(), top_left.y(), widget.width(), widget.height()

    stack = box(host._trading_stack)
    panel = box(host._indicator_panel)
    activity = box(logs.widget(0))
    api = box(logs.widget(1))
    label = box(logs.widget(0).layout().itemAt(0).layout().itemAt(0).widget())
    button = box(host._activity_pause_btn)
    status = box(host._status_log)
    assert box(top)[1] < box(bottom)[1]
    assert stack[0] < panel[0]
    assert activity[0] < api[0]
    assert label[0] < button[0]
    assert status[1] >= label[1] + label[3]
    assert surface.TOP_SPLITTER["children"] == ["trading_stack", "indicator_panel"]
    assert surface.LOG_SPLITTER["children"] == ["activity_pane", "api_pane"]


def test_the_bridge_registers_the_trading_tab_method():
    """The renderer cannot reach the Trading tab surface over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 12,
                "method": surface.METHOD,
                "params": {"layer": "stock", "activity_paused": True},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["tab_title"] == "Trading"
    assert answer["result"]["trading_stack"]["current_index"] == 1
    assert answer["result"]["watchdog"]["interval_ms"] == 60000


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'trading.tab', 'params':"
    " {'api_lines': ['first call'], 'layer': 'crypto'}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def _run_probe(prelude):
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Trading tab surface pulled Qt into the backend."""
    answered = _run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["api_pane"]["log_view"]["text"] == "first call"
    assert result["layers"][0]["add_button"]["text"] == "＋ Add Crypto Exchange"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = _run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
