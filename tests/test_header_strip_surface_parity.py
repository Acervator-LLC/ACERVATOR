"""The Qt header strip and the Qt-free surface, driven side by side."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from src.core.privacy_mask_registry import get_privacy_mask_registry
from src.gui.color_alpha import css_colours
from src.gui.main_tabs import header_strip_surface as surface
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
STRIP_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "header_strip.py"
WINDOW_SOURCE = REPO_ROOT / "src" / "gui" / "main_window.py"

FIELD_IDS = tuple(column["field_id"] for column in surface.KPI_COLUMNS) + tuple(
    card["field_id"] for card in surface.COUNTER_CARDS
)

WIDGET_CLASS = {
    "spendable": "SpendableProfitsWidget",
    "scrummed": "StatCard",
    "folded": "StatCard",
    "trades": "StatCard",
    "bots": "StatCard",
    "errors": "StatCard",
    "mode_button": "QPushButton",
}

CURSOR_SHAPE = {"arrow": "ArrowCursor", "pointing_hand": "PointingHandCursor"}

BRIDGE_METHOD = "header.strip"


def align_flag(name: str) -> int:
    """The Qt alignment integer one surface alignment name stands for."""
    from PySide6.QtCore import Qt

    parts = {
        "hcenter": Qt.AlignHCenter,
        "vcenter": Qt.AlignVCenter,
        "top": Qt.AlignTop,
        "bottom": Qt.AlignBottom,
    }
    flag = 0
    for part in name.split("|"):
        flag |= int(parts[part])
    return flag


@pytest.fixture(scope="module")
def qapp():
    """The application object every widget comparison renders against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    running = QApplication.instance()
    return running if running is not None else QApplication(sys.argv)


@pytest.fixture
def built(qapp):
    """The header strip built by the Qt mixin, and its host window."""
    from PySide6.QtWidgets import QMainWindow

    from src.gui.main_tabs.header_strip import HeaderStripMixin
    from src.gui.main_window import MainWindow

    class _Host(QMainWindow, HeaderStripMixin):
        """A window that supplies only what the strip's build calls."""

        def __init__(self) -> None:
            QMainWindow.__init__(self)
            self.setAccessibleName("Header strip parity host")
            self.error_log_opens = 0
            self.mode_toggles = 0

        def _show_error_log_dialog(self) -> None:
            self.error_log_opens += 1

        def _toggle_trading_mode(self) -> None:
            self.mode_toggles += 1

        def _update_mode_btn_style(self) -> None:
            MainWindow._update_mode_btn_style(self)

    host = _Host()
    host._build_header_strip()
    try:
        yield host
    finally:
        host.close()
        host.deleteLater()
        qapp.processEvents()


@pytest.fixture
def window(qapp):
    """A real main window, for the click actions the strip is wired to."""
    from src.gui.main_window import MainWindow

    made = MainWindow(bot_manager=None, settings_manager=None)
    try:
        yield made
    finally:
        made.close()
        made.deleteLater()
        qapp.processEvents()


@pytest.fixture
def revealed():
    """Every strip field unmasked, with the prior state put back after."""
    registry = get_privacy_mask_registry()
    prior = {field: registry.is_masked(field) for field in FIELD_IDS}
    for field in FIELD_IDS:
        registry.set_masked(field, False)
    try:
        yield registry
    finally:
        for field, was in prior.items():
            registry.set_masked(field, was)


def margins(layout) -> list:
    box = layout.contentsMargins()
    return [box.left(), box.top(), box.right(), box.bottom()]


def child_stretch(layout) -> list:
    return [layout.stretch(index) for index in range(layout.count())]


def label_state(label) -> dict:
    return {"text": label.text(), "style_sheet": label.styleSheet()}


def dot_state(dot) -> dict:
    return {
        "field_id": dot.field_id(),
        "text": dot.text(),
        "tooltip": dot.toolTip(),
        "style_sheet": dot.styleSheet(),
    }


def spendable_parts(widget) -> tuple:
    """The column layouts, separators and fixed gaps of the KPI panel."""
    outer = widget.layout()
    columns, separators, gaps = [], [], []
    for index in range(outer.count()):
        item = outer.itemAt(index)
        if item.layout() is not None:
            columns.append(item.layout())
        elif item.widget() is not None:
            separators.append(item.widget())
        else:
            gaps.append(item.spacerItem().sizeHint().width())
    return columns, separators, gaps


def top_row_names(host, top_row) -> list:
    """Each widget in the top row, named by the field that holds it."""
    by_widget = {
        id(host._spendable_widget): "spendable",
        id(host._stat_scrummed): "scrummed",
        id(host._stat_folded): "folded",
        id(host._stat_trades): "trades",
        id(host._stat_bots): "bots",
        id(host._stat_errors): "errors",
        id(host._mode_btn): "mode_button",
    }
    return [
        by_widget.get(id(top_row.itemAt(index).widget()), "unnamed")
        for index in range(top_row.count())
    ]


def card_parts(card) -> tuple:
    """The label, value and dot widgets of one counter card."""
    outer = card.layout()
    row = outer.itemAt(0).layout()
    return row, row.itemAt(1).widget(), outer.itemAt(1).widget(), card._privacy_dot


def qt_trace(host) -> dict:
    """Every value the built strip can be asked for, as plain data.

    The widget carries the alpha byte Qt reads and the surface publishes
    for a browser, so the widget's own values are read back through the
    same conversion the payload leaves under.
    """
    central = host.centralWidget()
    main_layout = central.layout()
    container = host._header_strip_container
    top_row = container.layout()
    panel = host._spendable_widget
    columns, separators, gaps = spendable_parts(panel)
    cards = [
        host._stat_scrummed,
        host._stat_folded,
        host._stat_trades,
        host._stat_bots,
        host._stat_errors,
    ]
    first_row, first_label, first_value, _ = card_parts(cards[0])
    mode = host._mode_btn
    trace = {
        "central_layout": {
            "margins_px": margins(main_layout),
            "spacing_px": main_layout.spacing(),
            "child_stretch": child_stretch(main_layout),
        },
        "top_row": {
            "margins_px": margins(top_row),
            "spacing_px": top_row.spacing(),
            "child_stretch": child_stretch(top_row),
        },
        "top_row_order": top_row_names(host, top_row),
        "top_row_classes": [
            type(top_row.itemAt(index).widget()).__name__
            for index in range(top_row.count())
        ],
        "isolated_tabs": list(surface.ISOLATED_TABS),
        "spendable": {
            "style_sheet": panel.styleSheet(),
            "layout": {
                "margins_px": margins(panel.layout()),
                "spacing_px": panel.layout().spacing(),
                "column_spacing_px": gaps[0],
                "column_margins_px": margins(columns[0]),
                "column_spacing": columns[0].spacing(),
                "frame_shape": panel.frameShape().name,
                "separator_align": int(separators[0].alignment()),
                "dot_align": int(columns[0].itemAt(2).alignment()),
            },
            "separator": label_state(separators[0]),
            "columns": [
                {
                    "label": column.itemAt(0).widget().text(),
                    "label_style": column.itemAt(0).widget().styleSheet(),
                    "label_tooltip": column.itemAt(0).widget().toolTip(),
                    "text": column.itemAt(1).widget().text(),
                    "style_sheet": column.itemAt(1).widget().styleSheet(),
                    "dot": dot_state(column.itemAt(2).widget()),
                }
                for column in columns
            ],
        },
        "card_layout": {
            "margins_px": margins(cards[0].layout()),
            "spacing_px": cards[0].layout().spacing(),
            "frame_shape": cards[0].frameShape().name,
            "label_align": int(first_label.alignment()),
            "value_align": int(first_value.alignment()),
            "dot_align": int(cards[0].layout().itemAt(2).alignment()),
        },
        "card_label_row": {
            "margins_px": margins(first_row),
            "spacing_px": first_row.spacing(),
            "order": [
                "label" if first_row.itemAt(i).widget() is not None else "stretch"
                for i in range(first_row.count())
            ],
        },
        "card_label_style": first_label.styleSheet(),
        "card_value_style": first_value.styleSheet(),
        "card_label_property": (
            "muted" if first_label.property("muted") else "not-muted"
        ),
        "card_value_property": (
            "heading" if first_value.property("heading") else "not-heading"
        ),
        "counters": [
            {
                "label": card_parts(card)[1].text(),
                "text": card_parts(card)[2].text(),
                "tooltip": card.toolTip(),
                "clickable": card._is_clickable,
                "cursor": card.cursor().shape().name,
                "field_id": card._privacy_field_id,
                "dot": dot_state(card_parts(card)[3]),
            }
            for card in cards
        ],
        "hidden_card": {
            "label": card_parts(host._stat_pnl)[1].text(),
            "text": card_parts(host._stat_pnl)[2].text(),
            "tooltip": host._stat_pnl.toolTip(),
            "visible": not host._stat_pnl.isHidden(),
            "field_id": host._stat_pnl._privacy_field_id,
            "in_top_row": any(
                top_row.itemAt(index).widget() is host._stat_pnl
                for index in range(top_row.count())
            ),
        },
        "mode_button": {
            "text": mode.text(),
            "checked": mode.isChecked(),
            "checkable": mode.isCheckable(),
            "minimum_width_px": mode.minimumWidth(),
            "horizontal_policy": mode.sizePolicy().horizontalPolicy().name,
            "vertical_policy": mode.sizePolicy().verticalPolicy().name,
            "tooltip": mode.toolTip(),
            "style_sheet": mode.styleSheet(),
        },
    }
    return css_colours(trace)


def surface_trace() -> dict:
    """The same values, read from the Qt-free view model."""
    model = surface.build_view_model(stats={}, exchange_count=0)
    layout = dict(model["spendable"]["layout"])
    layout["separator_align"] = align_flag(layout["separator_align"])
    layout["dot_align"] = align_flag(layout["dot_align"])
    card_layout = dict(model["card_layout"])
    for key in ("label_align", "value_align", "dot_align"):
        card_layout[key] = align_flag(card_layout[key])
    return {
        "central_layout": model["central_layout"],
        "top_row": model["top_row"],
        "top_row_order": model["top_row_order"],
        "top_row_classes": [WIDGET_CLASS[name] for name in model["top_row_order"]],
        "isolated_tabs": model["isolated_tabs"],
        "spendable": {
            "style_sheet": model["spendable"]["style_sheet"],
            "layout": layout,
            "separator": model["spendable"]["separator"],
            "columns": [
                {
                    "label": column["label"],
                    "label_style": column["label_style"],
                    "label_tooltip": column["label_tooltip"],
                    "text": column["initial_text"],
                    "style_sheet": column["initial_style"],
                    "dot": {
                        key: column["dot"][key]
                        for key in ("field_id", "text", "tooltip", "style_sheet")
                    },
                }
                for column in model["spendable"]["columns"]
            ],
        },
        "card_layout": card_layout,
        "card_label_row": model["card_label_row"],
        "card_label_style": model["card_label_style"],
        "card_value_style": model["card_value_style"],
        "card_label_property": model["card_label_property"],
        "card_value_property": model["card_value_property"],
        "counters": [
            {
                "label": card["label"],
                "text": card["initial_text"],
                "tooltip": card["tooltip"],
                "clickable": card["clickable"],
                "cursor": CURSOR_SHAPE[card["cursor"]],
                "field_id": card["field_id"],
                "dot": {
                    key: card["dot"][key]
                    for key in ("field_id", "text", "tooltip", "style_sheet")
                },
            }
            for card in model["counters"]
        ],
        "hidden_card": {
            "label": model["hidden_card"]["label"],
            "text": model["hidden_card"]["initial_text"],
            "tooltip": model["hidden_card"]["tooltip"],
            "visible": model["hidden_card"]["visible"],
            "field_id": model["hidden_card"]["field_id"],
            "in_top_row": False,
        },
        "mode_button": {
            "text": model["mode_button"]["text"],
            "checked": model["mode_button"]["checked"],
            "checkable": model["mode_button"]["checkable"],
            "minimum_width_px": model["mode_button"]["minimum_width_px"],
            "horizontal_policy": model["mode_button"]["horizontal_policy"],
            "vertical_policy": model["mode_button"]["vertical_policy"],
            "tooltip": model["mode_button"]["tooltip"],
            "style_sheet": model["mode_button"]["style_sheet"],
        },
    }


def digest(trace) -> str:
    return hashlib.sha256(
        json.dumps(trace, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def test_the_built_strip_and_the_surface_describe_the_same_strip(built, revealed):
    """A card, label, value, colour, tooltip, dot or size differs."""
    old = qt_trace(built)
    new = surface_trace()
    assert new == old
    assert digest(new) == digest(old)


def test_the_payload_carries_a_share_where_the_style_sheet_carries_a_byte():
    """Without this the comparison above passes on a payload that converted
    nothing, because both traces read through the same conversion."""
    payload = surface.build_view_model(stats={}, exchange_count=0)
    for written, published in (
        (surface.SPENDABLE_STYLE, payload["spendable"]["style_sheet"]),
        (
            surface.MODE_CARDS["crypto"]["style_sheet"],
            payload["mode_button"]["style_sheet"],
        ),
    ):
        assert "rgba(0,255,180,80)" in written or "rgba(0, 200, 160, 40)" in written
        assert published != written
        for call in published.split("rgba(")[1:]:
            alpha = call.split(")")[0].split(",")[3]
            assert float(alpha) <= 1, published


def test_the_trace_carries_every_part_of_the_strip(built, revealed):
    """The comparison passed by comparing an empty or partial trace."""
    old = qt_trace(built)
    assert set(old) == set(surface_trace())
    assert len(old) == 15
    assert old["top_row_order"] == [
        "spendable",
        "scrummed",
        "folded",
        "trades",
        "bots",
        "errors",
        "mode_button",
    ]
    assert old["top_row_classes"] == [
        "SpendableProfitsWidget",
        "StatCard",
        "StatCard",
        "StatCard",
        "StatCard",
        "StatCard",
        "QPushButton",
    ]
    assert "unnamed" not in old["top_row_order"]
    assert [column["label"] for column in old["spendable"]["columns"]] == [
        "SPENDABLE",
        "REALISED",
        "LOCKED",
        "MATURE",
        "EXCH",
    ]
    assert [card["label"] for card in old["counters"]] == [
        "Scrummed",
        "Folded",
        "Trades",
        "Bots",
        "Errors",
    ]
    assert [card["field_id"] for card in old["counters"]] == [
        "counter.scrummed",
        "counter.folded",
        "counter.trades",
        "counter.bots",
        "counter.errors",
    ]
    assert old["hidden_card"]["visible"] is False
    assert old["mode_button"]["text"] == "Crypto Mode"


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites() -> list:
    """Every ``.connect(`` site in the Qt strip, as signal and target."""
    tree = ast.parse(STRIP_SOURCE.read_text(encoding="utf-8"))
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
    "self._stat_errors.clicked": "errors.clicked",
    "self._mode_btn.clicked": "mode_button.clicked",
}

QT_TARGET_NAMES = {
    "self._show_error_log_dialog": "show_error_log_dialog",
    "self._toggle_trading_mode": "toggle_trading_mode",
}


def test_the_connect_sets_match():
    """The Qt strip connects a signal the surface names no action for."""
    sites = connect_sites()
    assert len(sites) == 2
    translated = {
        QT_SIGNAL_NAMES[signal]: QT_TARGET_NAMES[target] for signal, target in sites
    }
    assert translated == surface.ACTIONS


def test_the_connect_scan_finds_the_real_sites():
    """The connect scan returns an empty set whatever the source holds."""
    sites = connect_sites()
    assert ("self._mode_btn.clicked", "self._toggle_trading_mode") in sites
    assert STRIP_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)


def test_the_click_actions_reach_the_host(built):
    """A card or button click no longer calls what it is wired to."""
    built._stat_errors.clicked.emit()
    built._mode_btn.clicked.emit()
    assert built.error_log_opens == 1
    assert built.mode_toggles == 1


def refresh_statements() -> list:
    """The statements of ``_refresh_dashboard`` that fill the strip."""
    tree = ast.parse(WINDOW_SOURCE.read_text(encoding="utf-8"))
    body = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_refresh_dashboard":
            for statement in ast.walk(node):
                if isinstance(statement, (ast.Assign, ast.Expr, ast.If)):
                    body.append(statement)
    start = min(
        index
        for index, statement in enumerate(body)
        if "total_scrummed_usd" in ast.unparse(statement)
    )
    end = min(
        index
        for index, statement in enumerate(body)
        if "update_profits" in ast.unparse(statement)
    )
    return body[start : end + 1]


def window_stats_keys() -> set:
    """Every aggregate key the strip's own statements read."""
    keys = set()
    for statement in refresh_statements():
        for node in ast.walk(statement):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "agg"
            ):
                keys.add(node.args[0].value)
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "agg"
            ):
                keys.add(node.slice.value)
    return keys


def window_card_formats() -> dict:
    """The format each ``_stat_*`` card is set with, keyed by card name."""
    formats = {}
    for statement in refresh_statements():
        for node in ast.walk(statement):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set_value"
            ):
                continue
            name = dotted(node.func.value).rsplit("._stat_", 1)[-1]
            argument = node.args[0]
            if isinstance(argument, ast.JoinedStr):
                literal = "".join(
                    part.value
                    for part in argument.values
                    if isinstance(part, ast.Constant)
                )
                spec = "".join(
                    piece.value
                    for part in argument.values
                    if isinstance(part, ast.FormattedValue)
                    for piece in part.format_spec.values
                )
                formats[name] = (literal, spec)
            else:
                formats[name] = (dotted(argument.func), surface.COUNT_FORMAT)
    return formats


def test_the_card_formats_match_the_window():
    """The strip's numbers carry a different format than the window sets."""
    formats = window_card_formats()
    assert formats == {
        "scrummed": (surface.MONEY_PREFIX, surface.MONEY_FORMAT),
        "folded": (surface.MONEY_PREFIX, surface.MONEY_FORMAT),
        "pnl": (surface.MONEY_PREFIX, surface.PNL_FORMAT),
        "trades": ("str", surface.COUNT_FORMAT),
        "bots": ("str", surface.COUNT_FORMAT),
        "errors": ("str", surface.COUNT_FORMAT),
    }
    declared = {card["key"]: card["format"] for card in surface.COUNTER_CARDS}
    declared[surface.HIDDEN_CARD["key"]] = surface.HIDDEN_CARD["format"]
    assert {name: spec for name, (_, spec) in formats.items()} == declared


def test_the_stats_keys_match_the_window():
    """The surface reads an aggregate key the window's strip does not."""
    assert window_stats_keys() == set(surface.STATS_KEYS)
    assert len(surface.STATS_KEYS) == 8


def test_the_isolated_tabs_match_the_window():
    """The window hides the strip on a tab the surface does not name."""
    tree = ast.parse(WINDOW_SOURCE.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if "isolated_tabs" in ast.unparse(node.targets[0]):
            found.append({element.value for element in node.value.elts})
    assert found == [set(surface.ISOLATED_TABS)]


def test_the_window_hides_the_strip_on_the_isolated_tabs(window):
    """The strip shows on a tab the surface says hides it, or the reverse."""
    tabs = window._main_tabs
    seen = {}
    for index in range(tabs.count()):
        window._on_main_tab_changed(index)
        seen[tabs.tabText(index)] = not window._header_strip_container.isHidden()
    assert seen == {name: surface.strip_visible(name) for name in seen}
    hidden = {name for name, shown in seen.items() if not shown}
    assert hidden == set(surface.ISOLATED_TABS) & set(seen)
    assert hidden == {"Simulator"}
    assert len(seen) > len(hidden)


PROFITS_SCRIPTS = {
    "empty": {},
    "all_none": {
        "spendable": None,
        "total_realised": None,
        "locked": None,
        "mature": None,
        "exchange_count": 0,
    },
    "zero": {
        "spendable": 0,
        "total_realised": 0,
        "locked": 0,
        "mature": 0,
        "exchange_count": 0,
    },
    "negative_zero": {
        "spendable": -0.0,
        "total_realised": -0.0,
        "locked": -0.0,
        "mature": -0.0,
        "exchange_count": 0,
    },
    "positive": {
        "spendable": 1234.5,
        "total_realised": 9.005,
        "locked": 250.255,
        "mature": 0.001,
        "exchange_count": 3,
    },
    "negative_spendable": {
        "spendable": -12.5,
        "total_realised": -1.0,
        "locked": -2.0,
        "mature": -3.0,
        "exchange_count": 1,
    },
    "millions": {
        "spendable": 1234567.891,
        "total_realised": 9876543.219,
        "locked": 1000000,
        "mature": 999999.995,
        "exchange_count": 12,
    },
    "missing_realised": {"spendable": 5.0, "locked": None, "exchange_count": 2},
    "integers": {
        "spendable": 7,
        "total_realised": 8,
        "locked": 9,
        "mature": 10,
        "exchange_count": 11,
    },
    "tiny_negative": {
        "spendable": -0.004,
        "total_realised": -0.004,
        "locked": -0.005,
        "mature": -0.006,
        "exchange_count": 0,
    },
    "half_cent": {
        "spendable": 2.345,
        "total_realised": 2.355,
        "locked": 2.365,
        "mature": 2.375,
        "exchange_count": 0,
    },
}


def run_old_panel(payload) -> dict:
    """Drive the real KPI panel through one payload and trace its cells."""
    from src.gui.widgets.spendable_profits import SpendableProfitsWidget

    panel = SpendableProfitsWidget()
    panel.update_profits(payload)
    columns, _separators, _gaps = spendable_parts(panel)
    keys = [column["key"] for column in surface.KPI_COLUMNS]
    traced = {}
    for key, column in zip(keys, columns, strict=True):
        value = column.itemAt(1).widget()
        traced[key] = {
            "text": value.text(),
            "style_sheet": value.styleSheet(),
            "tooltip": value.toolTip(),
        }
    panel.deleteLater()
    return traced


def run_new_panel(payload) -> dict:
    """Drive the Qt-free panel model through the same payload."""
    return surface.kpi_cells(payload)


@pytest.mark.parametrize("name", sorted(PROFITS_SCRIPTS))
def test_the_panel_renders_the_same_cells(qapp, revealed, name):
    """A KPI cell's text, colour or tooltip differs from the Qt panel."""
    payload = PROFITS_SCRIPTS[name]
    old = run_old_panel(payload)
    new = run_new_panel(payload)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(PROFITS_SCRIPTS))
def test_the_panel_trace_measured_something(qapp, revealed, name):
    """The panel comparison passed on an empty trace."""
    old = run_old_panel(PROFITS_SCRIPTS[name])
    assert set(old) == {column["key"] for column in surface.KPI_COLUMNS}
    assert all(cell["text"] for cell in old.values())


def test_the_panel_scripts_reach_every_spendable_branch(qapp, revealed):
    """A spendable branch was never driven, so its colour was not compared."""
    styles = {
        run_old_panel(payload)["spendable"]["style_sheet"]
        for payload in PROFITS_SCRIPTS.values()
    }
    assert styles == {
        surface.VALUE_STYLE_MUTED,
        surface.VALUE_STYLE_HIGHLIGHT,
        surface.VALUE_STYLE_NEGATIVE,
    }
    empties = {
        key
        for payload in PROFITS_SCRIPTS.values()
        for key, cell in run_old_panel(payload).items()
        if cell["text"] == surface.EMPTY_TEXT
    }
    assert empties == {
        "spendable",
        "total_realised",
        "locked",
        "mature",
        "exchanges",
    }


STATS_SCRIPTS = {
    "empty": {},
    "zeros": {
        "total_scrummed_usd": 0.0,
        "total_folded_usd": 0.0,
        "total_trades": 0,
        "running": 0,
        "total_errors_lifetime": 0,
        "total_realised_pnl": 0.0,
    },
    "none_amounts": {
        "total_scrummed_usd": None,
        "total_folded_usd": None,
        "total_trades": 0,
        "running": 0,
        "total_errors_lifetime": 0,
        "total_realised_pnl": None,
    },
    "typical": {
        "total_scrummed_usd": 1234.567,
        "total_folded_usd": 890.125,
        "total_trades": 42,
        "running": 3,
        "total_errors_lifetime": 7,
        "total_realised_pnl": 12.34567,
    },
    "negative": {
        "total_scrummed_usd": -5.5,
        "total_folded_usd": -0.004,
        "total_trades": -1,
        "running": 0,
        "total_errors_lifetime": 0,
        "total_realised_pnl": -0.00005,
    },
    "millions": {
        "total_scrummed_usd": 1234567.891,
        "total_folded_usd": 9876543.215,
        "total_trades": 1000000,
        "running": 250,
        "total_errors_lifetime": 99999,
        "total_realised_pnl": 1234567.89125,
    },
    "string_counts": {
        "total_scrummed_usd": "12.5",
        "total_folded_usd": "0",
        "total_trades": "17",
        "running": "2",
        "total_errors_lifetime": "0",
        "total_realised_pnl": "3.5",
    },
}


def run_old_cards(stats) -> dict:
    """Drive real cards with the values the window formats from `stats`."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    scrummed = float(stats.get("total_scrummed_usd", 0.0) or 0.0)
    folded = float(stats.get("total_folded_usd", 0.0) or 0.0)
    texts = {
        "scrummed": f"${scrummed:,.2f}",
        "folded": f"${folded:,.2f}",
        "trades": str(stats.get("total_trades", 0)),
        "bots": str(stats.get("running", 0)),
        "errors": str(stats.get("total_errors_lifetime", 0)),
    }
    traced = {}
    for card in surface.COUNTER_CARDS:
        widget = StatCard(card["label"], card["initial_text"])
        widget.attach_privacy_dot(card["field_id"])
        widget.set_value(texts[card["key"]])
        traced[card["key"]] = widget.layout().itemAt(1).widget().text()
        widget.deleteLater()
    return traced


@pytest.mark.parametrize("name", sorted(STATS_SCRIPTS))
def test_the_counter_cards_render_the_same_text(qapp, revealed, name):
    """A counter card's rendered number differs from the Qt card."""
    stats = STATS_SCRIPTS[name]
    old = run_old_cards(stats)
    new = surface.counter_cells(stats)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(STATS_SCRIPTS))
def test_the_hidden_card_renders_the_same_text(qapp, revealed, name):
    """The hidden P/L card's number differs from the Qt card."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    stats = STATS_SCRIPTS[name]
    widget = StatCard("P/L", "$0.00")
    widget.set_value(f"${float(stats.get('total_realised_pnl', 0.0) or 0.0):+,.4f}")
    old = widget.layout().itemAt(1).widget().text()
    widget.deleteLater()
    assert surface.hidden_card_text(stats) == old


@pytest.mark.parametrize("name", sorted(STATS_SCRIPTS))
def test_the_profits_payload_matches_the_window(qapp, name):
    """The payload the panel receives differs from the window's."""
    stats = dict(STATS_SCRIPTS[name])
    for wallet, position, count in ((0.0, 0.0, 0), (5.0, 0.0, 1), (0.0, 9.0, 2)):
        stats["wallet_cash_usd"] = wallet
        stats["crypto_position_value_usd"] = position
        known = wallet > 0 or position > 0
        expected = {
            "spendable": wallet if known else None,
            "total_realised": None,
            "locked": position if known else None,
            "mature": None,
            "exchange_count": count,
        }
        assert surface.profits_payload(stats, count) == expected


MASK_SCRIPTS = {
    "none": (),
    "spendable_only": ("kpi.spendable",),
    "counters_only": (
        "counter.scrummed",
        "counter.folded",
        "counter.trades",
        "counter.bots",
        "counter.errors",
    ),
    "all": FIELD_IDS,
}


@pytest.mark.parametrize("name", sorted(MASK_SCRIPTS))
def test_the_masked_values_match(qapp, revealed, name):
    """A masked cell shows a different string than the Qt widget does."""
    for field in MASK_SCRIPTS[name]:
        revealed.set_masked(field, True)
    payload = PROFITS_SCRIPTS["positive"]
    stats = STATS_SCRIPTS["typical"]
    old = {"panel": run_old_panel(payload), "cards": run_old_cards(stats)}
    new = {"panel": surface.kpi_cells(payload), "cards": surface.counter_cells(stats)}
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(MASK_SCRIPTS))
def test_the_masked_dots_match(qapp, revealed, name):
    """A privacy dot's glyph, tooltip or skin differs from the Qt dot."""
    from src.gui.widgets.privacy_dot import PrivacyDot

    for field in MASK_SCRIPTS[name]:
        revealed.set_masked(field, True)
    old, new = {}, {}
    for field in FIELD_IDS:
        dot = PrivacyDot(field)
        old[field] = dot_state(dot)
        dot.deleteLater()
        model = surface.privacy_dot(field)
        new[field] = {key: model[key] for key in old[field]}
    assert new == old
    assert digest(new) == digest(old)


def test_the_mask_scripts_change_what_is_shown(qapp, revealed):
    """The mask scripts never masked anything, so nothing was compared."""
    payload = PROFITS_SCRIPTS["positive"]
    clear = run_old_panel(payload)["spendable"]["text"]
    revealed.set_masked("kpi.spendable", True)
    assert run_old_panel(payload)["spendable"]["text"] != clear
    assert run_old_panel(payload)["spendable"]["text"] == "****"


TOOLTIP_SCRIPTS = [
    (surface.ERRORS_TOOLTIP, surface.ERRORS_CLICK_TOOLTIP),
    ("", "Click to open the error log."),
    ("base", ""),
    ("", ""),
    ("holds Click me already", "Click me"),
    ("  padded  ", "tail"),
    ("base", "base"),
]


@pytest.mark.parametrize("base,suffix", TOOLTIP_SCRIPTS)
def test_the_click_tooltip_matches(qapp, base, suffix):
    """A clickable card's tooltip differs from the Qt card's."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    card = StatCard("probe", "0")
    card.setToolTip(base)
    card.set_clickable(True, suffix)
    old = card.toolTip()
    cursor = card.cursor().shape().name
    card.deleteLater()
    assert surface.click_tooltip(base, suffix) == old
    assert cursor == CURSOR_SHAPE["pointing_hand"]


def test_the_unclickable_card_keeps_its_cursor(qapp):
    """A card that never opted in reports the clickable cursor."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    card = StatCard("probe", "0")
    assert card._is_clickable is False
    assert card.cursor().shape().name == CURSOR_SHAPE["arrow"]
    card.set_clickable(False, "ignored")
    assert card.cursor().shape().name == CURSOR_SHAPE["arrow"]
    card.deleteLater()


@pytest.mark.parametrize("mode", ["crypto", "stock"])
def test_the_mode_skin_matches(built, revealed, mode):
    """The mode button's skin differs from the one the window applies."""
    from tests.qt_pixel import render_widget

    built._trading_mode = mode
    built._update_mode_btn_style()
    card = surface.mode_card(mode)
    assert card["style_sheet"] == built._mode_btn.styleSheet()
    other = "stock" if mode == "crypto" else "crypto"
    assert surface.MODE_CARDS[other]["color"] not in built._mode_btn.styleSheet()
    assert card["color"] in built._mode_btn.styleSheet()
    shipped = built._mode_btn
    shipped.setParent(None)
    assert_pictures_match(
        old_side=render_widget(shipped, size=MODE_BUTTON_SIZE),
        new_side=render_widget(
            mode_button_painted_by_the_model(mode, surface.DEFAULT_MODE),
            size=MODE_BUTTON_SIZE,
        ),
        note=mode,
    )


def test_the_mode_toggle_matches(window):
    """The mode button's text, state, skin or title differs after a toggle."""
    from tests.qt_pixel import render_widget

    seen = []
    for _ in range(2):
        window._toggle_trading_mode()
        shipped = window._mode_btn
        parent = shipped.parentWidget()
        shipped.setParent(None)
        try:
            assert_pictures_match(
                old_side=render_widget(shipped, size=MODE_BUTTON_SIZE),
                new_side=render_widget(
                    mode_button_painted_by_the_model(window._trading_mode),
                    size=MODE_BUTTON_SIZE,
                ),
                note=window._trading_mode,
            )
        finally:
            shipped.setParent(parent)
        seen.append(
            {
                "mode": window._trading_mode,
                "text": window._mode_btn.text(),
                "checked": window._mode_btn.isChecked(),
                "style_sheet": window._mode_btn.styleSheet(),
                "window_title": window.windowTitle(),
            }
        )
    expected = [
        {
            "mode": name,
            "text": surface.mode_card(name)["text"],
            "checked": surface.mode_card(name)["checked"],
            "style_sheet": surface.mode_card(name)["style_sheet"],
            "window_title": surface.mode_card(name)["window_title"],
        }
        for name in ("stock", "crypto")
    ]
    assert seen == expected
    assert digest(seen) == digest(expected)


def test_the_mode_card_falls_back_to_crypto():
    """An unknown wing reads as something other than the built state."""
    for unknown in ("", "equity", None, 0):
        assert surface.mode_card(unknown)["mode"] == "crypto"
    assert surface.mode_card("stock")["mode"] == "stock"


def test_the_bridge_serves_the_strip():
    """The frontend cannot reach the strip through the desktop bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD == BRIDGE_METHOD
    assert BRIDGE_METHOD in registry
    result = desktop_bridge.dispatch(BRIDGE_METHOD, {}, registry)
    assert result == surface.build_view_model(stats={}, exchange_count=0)


def test_the_handler_reads_its_parameters():
    """A request parameter reaches nothing, so the page cannot steer."""
    model = surface.view_model(
        {
            "stats": {"total_trades": 5},
            "exchange_count": 4,
            "mode": "stock",
            "tab_name": "Simulator",
            "profits": {"spendable": -1.0, "exchange_count": 4},
        }
    )
    assert model["mode_button"]["text"] == "Stock Mode"
    assert model["visible"] is False
    assert model["counters"][2]["text"] == "5"
    assert model["spendable"]["columns"][0]["text"] == "$-1.00"
    assert model["spendable"]["columns"][0]["style_sheet"] == (
        surface.VALUE_STYLE_NEGATIVE
    )


RENDER_SIZE = (1200, 90)
MODE_BUTTON_SIZE = (200, 40)


def mode_button_painted_by_the_model(mode, state_mode=None):
    """A bare button filled only from the mode cards, never from the window."""
    from PySide6.QtWidgets import QPushButton, QSizePolicy

    skin = surface.mode_card(mode)
    state = surface.mode_card(state_mode if state_mode is not None else mode)
    button = QPushButton(state["text"])
    button.setMinimumWidth(skin["minimum_width_px"])
    button.setSizePolicy(
        getattr(QSizePolicy.Policy, skin["horizontal_policy"]),
        getattr(QSizePolicy.Policy, skin["vertical_policy"]),
    )
    button.setCheckable(skin["checkable"])
    button.setChecked(state["checked"])
    button.setToolTip(skin["tooltip"])
    button.setStyleSheet(skin["style_sheet"])
    return button


#: The highlight skin reaches a widget only once an amount is measured.
HIGHLIGHT_PROFITS = {
    "spendable": 12.5,
    "total_realised": None,
    "locked": None,
    "mature": None,
    "exchange_count": 1,
}

PAINTED_COLOURS = (
    surface.SPENDABLE_LABEL_STYLE,
    surface.KPI_LABEL_STYLE,
    surface.VALUE_STYLE_HIGHLIGHT,
    surface.VALUE_STYLE_DEFAULT,
    surface.SEPARATOR_STYLE,
    surface.CARD_LABEL_STYLE,
    surface.CARD_VALUE_STYLE,
    surface.DOT_STYLE,
)


def declared_colour(style_sheet: str) -> str:
    """The first ``color:`` value one surface stylesheet declares."""
    head = style_sheet.split("color:", 1)[1]
    return head.split(";", 1)[0].strip().lower()


def strip_style_sheets(built) -> str:
    """Every style sheet the built strip's own widgets carry, joined."""
    from PySide6.QtWidgets import QWidget

    container = built._header_strip_container
    sheets = [container.styleSheet()]
    sheets.extend(widget.styleSheet() for widget in container.findChildren(QWidget))
    return " ".join(sheets)


@pytest.mark.parametrize("style_sheet", PAINTED_COLOURS)
def test_every_declared_colour_is_carried_by_the_strip(built, revealed, style_sheet):
    """A colour the view model declares is on no widget of the strip."""
    from tests.qt_pixel import render_widget

    built._spendable_widget.update_profits(HIGHLIGHT_PROFITS)
    assert declared_colour(style_sheet) in strip_style_sheets(built), style_sheet
    shipped = built._mode_btn
    shipped.setParent(None)
    assert_pictures_match(
        old_side=render_widget(shipped, size=MODE_BUTTON_SIZE),
        new_side=render_widget(
            mode_button_painted_by_the_model(surface.DEFAULT_MODE),
            size=MODE_BUTTON_SIZE,
        ),
    )


@pytest.mark.parametrize("mode", ["crypto", "stock"])
def test_the_mode_button_pixel_check_reports_the_wrong_skin(built, revealed, mode):
    """The image comparison passes whatever the mirror paints."""
    from tests.qt_pixel import render_widget

    built._trading_mode = mode
    built._update_mode_btn_style()
    other = "stock" if mode == "crypto" else "crypto"
    shipped = built._mode_btn
    shipped.setParent(None)
    assert_pictures_differ(
        old_side=render_widget(shipped, size=MODE_BUTTON_SIZE),
        new_side=render_widget(
            mode_button_painted_by_the_model(other, surface.DEFAULT_MODE),
            size=MODE_BUTTON_SIZE,
        ),
        note=mode,
    )


def test_the_strip_carries_only_the_wing_it_was_built_in(built, revealed):
    """The strip declares a colour of the wing it is not showing."""
    carried = strip_style_sheets(built)
    assert surface.MODE_CARDS["crypto"]["color"] in carried
    assert surface.MODE_CARDS["stock"]["color"] not in carried
    assert "#ff00ff" not in carried
    assert surface.DEFAULT_MODE == "crypto"
