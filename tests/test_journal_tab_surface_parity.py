"""The Qt Journal tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, a
different colour, a different column, a different number format, a
different layout number, a different splitter request, a different
button or a different branch than ``JournalTab`` builds on the same
input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import journal_tab_surface as surface
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "journal_tab.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (1180, 780)
SPLIT_SIZE = (900, 640)

CONNECT_TOTAL = 3
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 5
PAYLOAD_KEY_TOTAL = 50
CONSTANT_TOTAL = 193


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


# The three services, as the test owns them. The Qt tab is driven with
# these; the surface is driven with its own. Neither side reads the
# other's.


class Journal:
    """The trade journal the Qt tab reads its statistics and entries from."""

    def __init__(self, statistics=None, entries=None):
        self.statistics = dict(statistics or {})
        self.entries = list(entries or [])
        self.query: dict = {}

    def get_statistics(self):
        return self.statistics

    def get_entries(self, bot_id="", hours=24, limit=500):
        self.query = {"bot_id": bot_id, "hours": hours, "limit": limit}
        return self.entries


class Recovery:
    """The crash-recovery service the Qt tab reads its snapshot line from."""

    def __init__(self, info=None):
        self.info = dict(info or {})

    def get_recovery_info(self):
        return self.info


class Reconciliation:
    """The reconciliation engine the Qt tab reads its last result from."""

    def __init__(self, result=None):
        self.result = dict(result) if result else None

    def get_latest_result(self):
        return self.result


# The inputs. One scenario drives both sides.


def entry(**named):
    """One journal entry with every field the screen reads."""
    fields = {
        "timestamp": 1_700_000_000,
        "bot_id": "bot-abcdef-0123456789",
        "symbol": "BTC/USD",
        "action": "SCRUM",
        "side": "sell",
        "price": 51234.5678,
        "quantity": 0.01234567,
        "cost": 632.44,
        "pnl": 12.3456,
        "ta_direction": "BULLISH",
        "ta_confidence": 0.725,
        "ta_timeframe": "1h",
        "ta_signals": {"RSI": "BULLISH", "MACD": "BEARISH", "BB": "NEUTRAL"},
        "exchange_id": "coinbase",
        "order_id": "ORD-99",
        "execution_strategy": "limit",
        "slippage_pct": 0.0125,
        "reason": "target exceeded by 4.2 percent, selling the surplus",
    }
    fields.update(named)
    return fields


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"

STATS = {"total_entries": 3, "unique_bots": 2, "total_pnl": 1234.5678}
RECOVERY_FRESH = {
    "has_snapshot": True,
    "snapshot_age": 12.6,
    "snapshot_bots": 4,
    "journal_files": 7,
}
RECOVERY_OLD = {
    "has_snapshot": True,
    "snapshot_age": 3725.0,
    "snapshot_bots": 9,
    "journal_files": 21,
}
RECON_RESULT = {
    "timestamp": 1_700_000_500,
    "exchange": "coinbase",
    "orphaned_count": 3,
}

BOT_STATUSES = [
    {"bot_id": "bot-abcdef-0123456789", "symbol": "BTC/USD"},
    {"bot_id": "bot-ghijkl-9876543210", "symbol": "ETH/USD"},
]

ENTRIES_HAPPY = [
    entry(),
    entry(bot_id="bot-ghijkl-9876543210", symbol="ETH/USD", pnl=-4.5, action="FOLD"),
    entry(bot_id="bot-mnopqr-5555555555", symbol="SOL/USD", ta_direction="NEUTRAL"),
]

ENTRIES_GROWN = [
    entry(pnl=-99.25, price=1.0, quantity=900.0, ta_direction="BEARISH"),
    entry(bot_id="zzz-000", symbol="XRP/USD", pnl=777.5, action="SCRUM"),
    entry(bot_id="qqq-111", symbol="DOGE/USD", pnl=0.0, ta_direction="BULLISH"),
]


def scenario(name, **named):
    """One driving set: the three readings, the bot list and the row picked."""
    spec = {
        "name": name,
        "statistics": STATS,
        "entries": ENTRIES_HAPPY,
        "recovery_info": RECOVERY_FRESH,
        "reconciliation_result": RECON_RESULT,
        "bot_statuses": BOT_STATUSES,
        "selected_row": 0,
        "refresh_takes_services": False,
    }
    spec.update(named)
    return spec


SCENARIOS = [
    scenario("happy"),
    scenario("services_given_to_refresh", refresh_takes_services=True),
    scenario("no_journal", statistics=None, entries=None, selected_row=None),
    scenario("no_recovery", recovery_info=None),
    scenario("no_reconciliation", reconciliation_result=None),
    scenario("no_reconciliation_result", reconciliation_result={}),
    scenario("no_snapshot", recovery_info={"has_snapshot": False, "journal_files": 2}),
    scenario("snapshot_over_a_minute", recovery_info=RECOVERY_OLD),
    scenario(
        "snapshot_exactly_a_minute",
        recovery_info={"has_snapshot": True, "snapshot_age": 60, "snapshot_bots": 1},
    ),
    scenario("empty_recovery_info", recovery_info={"has_snapshot": True}),
    scenario("empty_statistics", statistics={}),
    scenario("empty_entries", entries=[], selected_row=None),
    scenario("empty_bot_list", bot_statuses=[]),
    scenario("no_bot_list", bot_statuses=None),
    scenario("row_below_the_list", selected_row=-1),
    scenario("row_above_the_list", selected_row=99),
    scenario("bot_without_a_symbol", bot_statuses=[{"bot_id": "solo-1234567890"}]),
    scenario("bot_without_an_id", bot_statuses=[{"symbol": "LTC/USD"}]),
    scenario("bare_entry", entries=[{}], selected_row=0),
    scenario(
        "zero_everywhere",
        statistics={"total_entries": 0, "unique_bots": 0, "total_pnl": 0},
        entries=[entry(price=0, quantity=0, cost=0, pnl=0, ta_confidence=0)],
    ),
    scenario(
        "negative_everywhere",
        statistics={"total_entries": -3, "unique_bots": -1, "total_pnl": -50.5},
        entries=[
            entry(price=-1.5, quantity=-2.25, cost=-3.75, pnl=-4.5, slippage_pct=-0.5)
        ],
    ),
    scenario(
        "a_thousand_million",
        statistics={"total_entries": 1_000_000_000, "total_pnl": 1e9},
        entries=[entry(price=1e9, quantity=1e9, cost=1e9, pnl=1e9)],
    ),
    scenario(
        "one_billionth",
        statistics={"total_pnl": 1e-9},
        entries=[entry(price=1e-9, quantity=1e-9, cost=1e-9, pnl=1e-9)],
    ),
    scenario(
        "unicode",
        entries=[entry(symbol=UNICODE_TEXT, reason=UNICODE_TEXT, action=UNICODE_TEXT)],
        bot_statuses=[{"bot_id": UNICODE_TEXT, "symbol": UNICODE_TEXT}],
    ),
    scenario(
        "two_hundred_characters",
        entries=[entry(reason=LONG_TEXT, symbol=LONG_TEXT, order_id=LONG_TEXT)],
    ),
    scenario(
        "markup_inside_a_text_field",
        entries=[entry(reason=MARKUP_TEXT, symbol=MARKUP_TEXT, side=MARKUP_TEXT)],
    ),
    scenario(
        "wrong_capitals",
        entries=[
            entry(ta_direction="bullish", ta_signals={"RSI": "bearish"}),
            entry(ta_direction="Bearish", ta_signals={"MACD": "Bullish"}),
        ],
    ),
    scenario(
        "a_name_with_a_newline",
        entries=[entry(symbol=NEWLINE_TEXT, reason=NEWLINE_TEXT)],
        bot_statuses=[{"bot_id": NEWLINE_TEXT, "symbol": NEWLINE_TEXT}],
    ),
    scenario(
        "text_where_a_number_belongs",
        entries=[entry(price="cheap")],
    ),
    scenario(
        "text_where_a_number_belongs_in_stats",
        statistics={"total_pnl": "lots"},
    ),
    scenario(
        "infinity_where_a_number_belongs",
        entries=[entry(price=math.inf, quantity=-math.inf, pnl=math.inf)],
        statistics={"total_pnl": math.inf},
    ),
    scenario(
        "infinity_as_a_timestamp",
        entries=[entry(timestamp=math.inf)],
    ),
    scenario(
        "a_number_where_a_bot_id_belongs",
        entries=[entry(bot_id=1234567890123)],
    ),
    scenario(
        "none_where_a_number_belongs",
        entries=[entry(pnl=None)],
    ),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}


# Driving the two sides


def old_services(spec):
    """The three readings the Qt tab is given, or None where absent."""
    has_journal = spec["statistics"] is not None or spec["entries"] is not None
    journal = Journal(spec["statistics"], spec["entries"]) if has_journal else None
    recovery = (
        Recovery(spec["recovery_info"]) if spec["recovery_info"] is not None else None
    )
    result = spec["reconciliation_result"]
    reconciliation = Reconciliation(result) if result is not None else None
    return journal, reconciliation, recovery


def new_services(spec):
    """The same three readings, built from the surface's own holders."""
    has_journal = spec["statistics"] is not None or spec["entries"] is not None
    journal = (
        surface.JournalSource(spec["statistics"], spec["entries"])
        if has_journal
        else None
    )
    recovery = (
        surface.RecoverySource(spec["recovery_info"])
        if spec["recovery_info"] is not None
        else None
    )
    result = spec["reconciliation_result"]
    reconciliation = (
        surface.ReconciliationSource(result) if result is not None else None
    )
    return journal, reconciliation, recovery


def drive_old(spec):
    """Build the Qt tab, run the same three steps, and hand it back."""
    from src.gui.journal_tab import JournalTab

    app()
    journal, reconciliation, recovery = old_services(spec)
    if spec["refresh_takes_services"]:
        tab = JournalTab()
    else:
        tab = JournalTab(journal, reconciliation, recovery)
    if spec["bot_statuses"] is not None:
        tab.update_bot_filter(spec["bot_statuses"])
    if spec["refresh_takes_services"]:
        tab.refresh(journal, reconciliation, recovery)
    else:
        tab.refresh()
    if spec["selected_row"] is not None:
        tab._on_entry_selected(spec["selected_row"], 0, -1, -1)
    return tab, journal


def drive_new(spec):
    """Build the surface model and run the same three steps."""
    journal, reconciliation, recovery = new_services(spec)
    if spec["refresh_takes_services"]:
        model = surface.JournalTabModel()
    else:
        model = surface.JournalTabModel(journal, reconciliation, recovery)
    if spec["bot_statuses"] is not None:
        model.update_bot_filter(spec["bot_statuses"])
    if spec["refresh_takes_services"]:
        model.refresh(journal, reconciliation, recovery)
    else:
        model.refresh()
    if spec["selected_row"] is not None:
        model.entry_selected(spec["selected_row"], 0, -1, -1)
    return model, journal


# Reading the two sides


def margins(layout):
    box = layout.contentsMargins()
    return [box.left(), box.top(), box.right(), box.bottom()]


def layout_order(layout):
    """The class of each item the layout holds, in the order it was added."""
    from PySide6.QtWidgets import QLayout

    order = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is not None:
            order.append(type(widget).__name__)
        elif isinstance(item.layout(), QLayout):
            order.append(type(item.layout()).__name__)
        else:
            order.append("stretch")
    return order


def combo_state(box):
    """Every value one Qt drop list can be asked for."""
    return {
        "items": [[box.itemText(i), box.itemData(i)] for i in range(box.count())],
        "index": box.currentIndex(),
        "current_data": box.currentData(),
        "current_text": box.currentText(),
        "count": box.count(),
        "signals_blocked": box.signalsBlocked(),
    }


def table_state(table):
    """Every value the Qt trade table can be asked for."""
    from PySide6.QtCore import Qt

    rows = []
    colors = []
    for row in range(table.rowCount()):
        texts = []
        painted = []
        for col in range(table.columnCount()):
            cell = table.item(row, col)
            texts.append(None if cell is None else cell.text())
            brush = None if cell is None else cell.data(Qt.ItemDataRole.ForegroundRole)
            painted.append(None if brush is None else brush.color().name())
        rows.append(texts)
        colors.append(painted)
    header = table.horizontalHeader()
    return {
        "columns": [
            table.horizontalHeaderItem(col).text() for col in range(table.columnCount())
        ],
        "column_count": table.columnCount(),
        "header_resize_mode": header.sectionResizeMode(0).name,
        "alternating_row_colors": table.alternatingRowColors(),
        "edit_triggers": table.editTriggers().name,
        "vertical_header_visible": not table.verticalHeader().isHidden(),
        "selection_behavior": table.selectionBehavior().name,
        "cell_alignment_value": (
            table.item(0, 0).textAlignment() if table.rowCount() else 132
        ),
        "row_count": table.rowCount(),
        "rows": rows,
        "row_colors": colors,
    }


def qt_parts(tab):
    """Every widget the tab builds, found by walking its layouts."""
    outer = tab.layout()
    header = outer.itemAt(0).layout()
    splitter = outer.itemAt(1).widget()
    journal_group = splitter.widget(0)
    bottom = splitter.widget(1)
    detail_group = bottom.widget(0)
    recovery_group = bottom.widget(1)
    recovery_layout = recovery_group.layout()
    button_row = recovery_layout.itemAt(4).layout()
    return {
        "outer": outer,
        "header": header,
        "stats_label": header.itemAt(0).widget(),
        "bot_label": header.itemAt(2).widget(),
        "bot_filter": header.itemAt(3).widget(),
        "period_label": header.itemAt(4).widget(),
        "period_filter": header.itemAt(5).widget(),
        "splitter": splitter,
        "journal_group": journal_group,
        "journal_table": journal_group.layout().itemAt(0).widget(),
        "bottom_splitter": bottom,
        "detail_group": detail_group,
        "detail_view": detail_group.layout().itemAt(0).widget(),
        "recovery_group": recovery_group,
        "recovery_layout": recovery_layout,
        "snapshot_label": recovery_layout.itemAt(0).widget(),
        "recon_label": recovery_layout.itemAt(1).widget(),
        "orphans_label": recovery_layout.itemAt(2).widget(),
        "journal_files_label": recovery_layout.itemAt(3).widget(),
        "button_row": button_row,
        "recon_button": button_row.itemAt(0).widget(),
        "snapshot_button": button_row.itemAt(1).widget(),
    }


def qt_trace(tab, journal):
    """Every value the built Qt tab can be asked for, as plain data."""
    parts = qt_parts(tab)
    splitter = parts["splitter"]
    bottom = parts["bottom_splitter"]
    detail = parts["detail_view"]

    def label(name):
        widget = parts[name]
        return {"text": widget.text(), "style_sheet": widget.styleSheet()}

    def button(name):
        widget = parts[name]
        return {
            "text": widget.text(),
            "style_sheet": widget.styleSheet(),
            "enabled": widget.isEnabled(),
        }

    def group(name):
        widget = parts[name]
        return {"title": widget.title(), "style_sheet": widget.styleSheet()}

    return {
        "accessible_name": tab.accessibleName(),
        "container": {
            "margins_px": margins(parts["outer"]),
            "spacing_px": parts["outer"].spacing(),
        },
        "header_order": layout_order(parts["header"]),
        "stats_label": label("stats_label"),
        "bot_label": {"text": parts["bot_label"].text()},
        "period_label": {"text": parts["period_label"].text()},
        "bot_filter": dict(
            combo_state(parts["bot_filter"]),
            minimum_width_px=parts["bot_filter"].minimumWidth(),
        ),
        "period_filter": combo_state(parts["period_filter"]),
        "splitter": {
            "orientation": splitter.orientation().name.lower(),
            "handle_width_px": splitter.handleWidth(),
            "children_collapsible": splitter.childrenCollapsible(),
            "child_count": splitter.count(),
        },
        "bottom_splitter": {
            "orientation": bottom.orientation().name.lower(),
            "handle_width_px": bottom.handleWidth(),
            "children_collapsible": bottom.childrenCollapsible(),
            "child_count": bottom.count(),
        },
        "journal_group": group("journal_group"),
        "detail_group": group("detail_group"),
        "recovery_group": group("recovery_group"),
        "journal_table": table_state(parts["journal_table"]),
        "detail_view": {
            "read_only": detail.isReadOnly(),
            "font_family": detail.font().family(),
            "font_point_size": detail.font().pointSize(),
            "style_sheet": detail.styleSheet(),
        },
        "snapshot_label": label("snapshot_label"),
        "recon_label": label("recon_label"),
        "orphans_label": label("orphans_label"),
        "journal_files_label": label("journal_files_label"),
        "recon_button": button("recon_button"),
        "snapshot_button": button("snapshot_button"),
        "recovery_order": layout_order(parts["recovery_layout"]),
        "button_row_order": layout_order(parts["button_row"]),
        "entry_query": dict(journal.query) if journal is not None else {},
        "entry_count": len(tab._current_entries),
    }


def surface_trace(model, payload):
    """The same values, read from the Qt-free view model."""
    table = payload["journal_table"]
    detail = payload["detail_view"]
    return {
        "accessible_name": payload["accessible_name"],
        "container": dict(payload["container"]),
        "header_order": [
            "stretch" if name == "stretch" else WIDGET_CLASS[name]
            for name in payload["header_order"]
        ],
        "stats_label": dict(payload["stats_label"]),
        "bot_label": dict(payload["bot_label"]),
        "period_label": dict(payload["period_label"]),
        "bot_filter": {
            key: value
            for key, value in payload["bot_filter"].items()
            if key != "default_index"
        },
        "period_filter": {
            key: value
            for key, value in payload["period_filter"].items()
            if key != "default_index"
        },
        "splitter": {
            "orientation": payload["splitter"]["orientation"],
            "handle_width_px": payload["splitter"]["handle_width_px"],
            "children_collapsible": payload["splitter"]["children_collapsible"],
            "child_count": len(payload["splitter"]["children"]),
        },
        "bottom_splitter": {
            "orientation": payload["bottom_splitter"]["orientation"],
            "handle_width_px": payload["bottom_splitter"]["handle_width_px"],
            "children_collapsible": payload["bottom_splitter"]["children_collapsible"],
            "child_count": len(payload["bottom_splitter"]["children"]),
        },
        "journal_group": dict(payload["journal_group"]),
        "detail_group": dict(payload["detail_group"]),
        "recovery_group": dict(payload["recovery_group"]),
        "journal_table": {
            "columns": table["columns"],
            "column_count": table["column_count"],
            "header_resize_mode": table["header_resize_mode"],
            "alternating_row_colors": table["alternating_row_colors"],
            "edit_triggers": table["edit_triggers"],
            "vertical_header_visible": table["vertical_header_visible"],
            "selection_behavior": table["selection_behavior"],
            "cell_alignment_value": table["cell_alignment_value"],
            "row_count": table["row_count"],
            "rows": table["rows"],
            "row_colors": table["row_colors"],
        },
        "detail_view": {
            "read_only": detail["read_only"],
            "font_family": detail["font_family"],
            "font_point_size": detail["font_point_size"],
            "style_sheet": detail["style_sheet"],
        },
        "snapshot_label": dict(payload["snapshot_label"]),
        "recon_label": dict(payload["recon_label"]),
        "orphans_label": dict(payload["orphans_label"]),
        "journal_files_label": dict(payload["journal_files_label"]),
        "recon_button": dict(payload["recon_button"]),
        "snapshot_button": dict(payload["snapshot_button"]),
        "recovery_order": [LAYOUT_CLASS[name] for name in payload["recovery_order"]],
        "button_row_order": [
            LAYOUT_CLASS[name] for name in payload["button_row_order"]
        ],
        "entry_query": payload["entry_query"],
        "entry_count": payload["entry_count"],
    }


WIDGET_CLASS = {
    "stats_label": "QLabel",
    "bot_label": "QLabel",
    "bot_filter": "QComboBox",
    "period_label": "QLabel",
    "period_filter": "QComboBox",
}

LAYOUT_CLASS = {
    "snapshot_label": "QLabel",
    "recon_label": "QLabel",
    "orphans_label": "QLabel",
    "journal_files_label": "QLabel",
    "recon_button": "QPushButton",
    "snapshot_button": "QPushButton",
    "button_row": "QHBoxLayout",
    "stretch": "stretch",
}


def outcome(work):
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc),
        }


def old_outcome(spec):
    return outcome(lambda: qt_trace(*drive_old(spec)))


def new_outcome(spec):
    def read():
        model, journal = drive_new(spec)
        return surface_trace(model, surface.build_view_model(model))

    return outcome(read)


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_screen(name):
    """A control, colour, column, number or branch differs between them."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["message"] == old["message"], (name, old, new)
        return
    assert new["value"] == old["value"], name
    assert digest(new["value"]) == digest(old["value"]), name


def test_both_answers_and_refusals_are_in_the_measured_set():
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for spec in SCENARIOS:
        old = old_outcome(spec)
        (answered if old["outcome"] == "answered" else refused).append(spec["name"])
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert set(refused) == set(REFUSING_SCENARIOS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)


REFUSING_SCENARIOS = (
    "text_where_a_number_belongs",
    "text_where_a_number_belongs_in_stats",
    "infinity_as_a_timestamp",
    "a_number_where_a_bot_id_belongs",
    "none_where_a_number_belongs",
)


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """One side refused an input the other accepted, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in ("ValueError", "TypeError", "OSError", "OverflowError")


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    happy = old_outcome(BY_NAME["happy"])["value"]
    grown = old_outcome(BY_NAME["a_thousand_million"])["value"]
    assert happy != grown
    assert digest(happy) != digest(grown)
    assert digest(happy) == digest(old_outcome(BY_NAME["happy"])["value"])
    assert len(digest(happy)) == 64


@pytest.mark.parametrize("name", ["happy", "zero_everywhere", "bare_entry"])
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 25, sorted(value)
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# The detail pane, driven into a real text box on both sides


DETAIL_SCENARIOS = [
    "happy",
    "bare_entry",
    "zero_everywhere",
    "negative_everywhere",
    "a_thousand_million",
    "one_billionth",
    "unicode",
    "two_hundred_characters",
    "markup_inside_a_text_field",
    "wrong_capitals",
    "a_name_with_a_newline",
    "row_below_the_list",
    "row_above_the_list",
]


def text_box_from(payload):
    """A bare text box carrying only what the payload declares."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QTextEdit

    declared = payload["detail_view"]
    box = QTextEdit()
    box.setReadOnly(declared["read_only"])
    box.setFont(QFont(declared["font_family"], declared["font_point_size"]))
    box.setStyleSheet(declared["style_sheet"])
    box.setHtml(declared["html"])
    return box


@pytest.mark.parametrize("name", DETAIL_SCENARIOS)
def test_the_detail_pane_holds_the_same_text(name):
    """The detail pane shows a different line, colour or order."""
    app()
    spec = BY_NAME[name]
    tab, _journal = drive_old(spec)
    model, _source = drive_new(spec)
    payload = surface.build_view_model(model)
    mine = text_box_from(payload)
    assert mine.toPlainText() == tab._detail_view.toPlainText(), name
    assert mine.toHtml() == tab._detail_view.toHtml(), name
    assert digest(mine.toHtml()) == digest(tab._detail_view.toHtml()), name


def test_the_detail_comparison_tells_two_entries_apart():
    """The detail comparison passes whatever the second entry says."""
    app()
    one, _a = drive_old(BY_NAME["happy"])
    other, _b = drive_old(BY_NAME["negative_everywhere"])
    assert one._detail_view.toPlainText() != other._detail_view.toPlainText()
    assert digest(one._detail_view.toHtml()) != digest(other._detail_view.toHtml())


def test_a_row_outside_the_list_leaves_the_detail_pane_empty():
    """A row the table does not hold wrote a detail pane anyway."""
    app()
    for name in ("row_below_the_list", "row_above_the_list"):
        tab, _journal = drive_old(BY_NAME[name])
        model, _source = drive_new(BY_NAME[name])
        assert tab._detail_view.toPlainText() == ""
        assert model.detail_html == surface.NO_DETAIL_HTML
    filled, _c = drive_old(BY_NAME["happy"])
    assert filled._detail_view.toPlainText() != ""


NON_TEXT_ENTRY = [entry(symbol=42, action=7, ta_direction=13, ta_timeframe=1)]


def test_a_table_value_that_is_not_text_is_dropped_by_the_shipped_screen():
    """The shipped screen keeps a cell value that is not text.

    Qt reads a number handed to a table cell as the cell's kind, not as
    its wording, so the shipped screen paints an empty cell and the
    number never reaches the operator. The surface carries the number
    through. Both behaviours are pinned here; the surface does not copy
    the loss.
    """
    app()
    spec = scenario("non_text_cell", entries=NON_TEXT_ENTRY)
    old = qt_trace(*drive_old(spec))
    model, _journal = drive_new(spec)
    new = surface.build_view_model(model)
    assert old["journal_table"]["rows"][0][2] == ""
    assert old["journal_table"]["rows"][0][3] == ""
    assert old["journal_table"]["rows"][0][8] == ""
    assert new["journal_table"]["rows"][0][2] == 42
    assert new["journal_table"]["rows"][0][3] == 7
    assert new["journal_table"]["rows"][0][8] == 13
    text_row = qt_trace(*drive_old(BY_NAME["happy"]))["journal_table"]["rows"][0]
    assert text_row[2] == "BTC/USD"


def bot_filter_after_a_bot_leaves():
    """Both sides after a selected bot drops out of the list."""
    from src.gui.journal_tab import JournalTab

    app()
    tab = JournalTab()
    tab.update_bot_filter(BOT_STATUSES)
    tab._filter_bot.setCurrentIndex(2)
    model = surface.JournalTabModel()
    model.update_bot_filter(BOT_STATUSES)
    model.bot_filter.set_current_index(2)
    assert tab._filter_bot.currentData() == model.bot_filter.current_data()
    tab.update_bot_filter(BOT_STATUSES[:1])
    model.update_bot_filter(BOT_STATUSES[:1])
    return tab, model


def test_a_bot_that_leaves_the_list_loses_the_selection():
    """The bot drop list keeps a bot the fleet no longer runs."""
    tab, model = bot_filter_after_a_bot_leaves()
    assert combo_state(tab._filter_bot) == model.bot_filter.state()
    assert model.bot_filter.count() == 2
    assert model.bot_filter.current_data() == surface.ALL_BOTS_DATA
    assert surface.FILTER_LOST in [call[0] for call in model.calls]


def test_a_bot_that_stays_keeps_the_selection():
    """The bot drop list drops a selection the new list still holds."""
    from src.gui.journal_tab import JournalTab

    app()
    tab = JournalTab()
    tab.update_bot_filter(BOT_STATUSES)
    tab._filter_bot.setCurrentIndex(2)
    kept = tab._filter_bot.currentData()
    tab.update_bot_filter(list(reversed(BOT_STATUSES)))
    model = surface.JournalTabModel()
    model.update_bot_filter(BOT_STATUSES)
    model.bot_filter.set_current_index(2)
    model.update_bot_filter(list(reversed(BOT_STATUSES)))
    assert combo_state(tab._filter_bot) == model.bot_filter.state()
    assert model.bot_filter.current_data() == kept
    assert surface.FILTER_RESTORED in [call[0] for call in model.calls]


# The enumeration: signals, classes, methods, timers, bus topics


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    "lambda" if isinstance(target, ast.Lambda) else dotted(target),
                )
            )
    return sorted(found)


QT_SIGNAL_NAMES = {
    "self._filter_bot.currentIndexChanged": "bot_filter.currentIndexChanged",
    "self._filter_hours.currentIndexChanged": "period_filter.currentIndexChanged",
    "self._journal_table.currentCellChanged": "journal_table.currentCellChanged",
}

QT_TARGET_NAMES = {
    "lambda": "refresh",
    "self._on_entry_selected": "entry_selected",
}


def test_the_connect_sets_match():
    """The Qt tab connects a signal the surface names no action for."""
    sites = connect_sites(TAB_SOURCE)
    assert len(sites) == CONNECT_TOTAL, sites
    translated = {
        QT_SIGNAL_NAMES[signal]: QT_TARGET_NAMES[target] for signal, target in sites
    }
    assert translated == surface.ACTIONS
    assert len(surface.ACTIONS) == CONNECT_TOTAL


def test_the_connect_reader_finds_the_real_sites():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites(TAB_SOURCE)
    assert (
        "self._journal_table.currentCellChanged",
        "self._on_entry_selected",
    ) in sites
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert len(connect_sites(BUS_NEIGHBOUR)) > CONNECT_TOTAL


SHIPPED_METHODS = {
    "__init__": "JournalTabModel.__init__",
    "_setup_ui": "build_view_model",
    "_on_entry_selected": "JournalTabModel.entry_selected",
    "refresh": "JournalTabModel.refresh",
    "update_bot_filter": "JournalTabModel.update_bot_filter",
}

SURFACE_CLASSES = {
    "JournalTabModel": "JournalTab",
    "ComboBox": "JournalTab._filter_bot and JournalTab._filter_hours",
    "JournalSource": "the trade journal JournalTab.refresh reads",
    "RecoverySource": "the crash-recovery service JournalTab.refresh reads",
    "ReconciliationSource": "the reconciliation engine JournalTab.refresh reads",
}


def shipped_methods() -> list:
    """Every method the shipped class declares, read off the class object."""
    from src.gui.journal_tab import JournalTab

    return sorted(
        name
        for name, value in vars(JournalTab).items()
        if callable(value) and not name.startswith("__") or name == "__init__"
    )


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped screen gained or lost a class or a method."""
    from src.gui import journal_tab

    classes = [
        name
        for name, value in vars(journal_tab).items()
        if isinstance(value, type) and value.__module__ == journal_tab.__name__
    ]
    assert classes == ["JournalTab"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    found = shipped_methods()
    assert found == sorted(SHIPPED_METHODS), found
    assert len(found) == SHIPPED_METHOD_TOTAL
    for counterpart in SHIPPED_METHODS.values():
        holder, _, attribute = counterpart.partition(".")
        target = getattr(surface, holder)
        assert callable(
            getattr(target, attribute) if attribute else target
        ), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["JournalTabModel"] == "JournalTab"


def test_the_method_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "update_bot_filter" in SHIPPED_METHODS
    assert not hasattr(surface, "InventedModel")
    assert "InventedModel" not in SURFACE_CLASSES
    with pytest.raises(AttributeError):
        getattr(surface, "InventedModel")


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def test_the_screen_holds_no_timer_and_the_counter_can_report():
    """The screen runs a timer the surface declares no delay for.

    The shipped screen holds none, so the counter is pointed at a
    neighbouring screen that really does run one. A counter that
    returned nothing on both would be no measurement.
    """
    assert timer_sites(TAB_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1, "the timer counter reports nothing"


def test_the_screen_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The screen listens on a topic the surface names none of.

    The shipped screen listens on none, so the counter is pointed at a
    neighbouring screen that really does subscribe.
    """
    assert bus_sites(TAB_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


# The completeness check


PAYLOAD_KEYS = {
    "ACCENT_COLOR": "colors.accent",
    "ACCESSIBLE_NAME": "accessible_name",
    "ACTIONS": "actions",
    "ACTION_LABEL": "labels.action",
    "ALTERNATING_ROW_COLORS": "journal_table.alternating_row_colors",
    "BEARISH": "bearish",
    "BLANK_LINE": "titles.blank",
    "BOTTOM_SPLITTER_CHILDREN": "bottom_splitter.children",
    "BOTTOM_SPLITTER_SIZES_PX": "bottom_splitter.requested_sizes_px",
    "BOT_FILTER_ITEM_FORMAT": "formats.bot_filter_item",
    "BOT_FILTER_MIN_WIDTH_PX": "bot_filter.minimum_width_px",
    "BOT_ID_FILTER_SLICE": "slices.filter_bot_id",
    "BOT_LABEL": "labels.bot",
    "BOT_LABEL_TEXT": "bot_label.text",
    "BULLISH": "bullish",
    "BUS_TOPICS": "bus_topics",
    "BUTTON_ENABLED": "recon_button.enabled",
    "BUTTON_ROW_ORDER": "button_row_order",
    "CALL_NAMES": "call_names",
    "CELL_ALIGNMENT": "journal_table.cell_alignment",
    "CELL_ALIGNMENT_VALUE": "journal_table.cell_alignment_value",
    "COLORS": "colors",
    "COLOR_SPAN_FORMAT": "formats.color_span",
    "COLUMNS": "journal_table.columns",
    "COLUMN_COUNT": "journal_table.column_count",
    "CONFIDENCE_LABEL": "labels.confidence",
    "CONTAINER_MARGINS_PX": "container.margins_px",
    "CONTAINER_SPACING_PX": "container.spacing_px",
    "COST_LABEL": "labels.cost",
    "DEFAULTS": "defaults",
    "DEFAULT_ACTION": "defaults.action",
    "DEFAULT_BOT_ID": "defaults.bot_id",
    "DEFAULT_CONFIDENCE": "defaults.confidence",
    "DEFAULT_COST": "defaults.cost",
    "DEFAULT_DIRECTION_DETAIL": "defaults.direction_detail",
    "DEFAULT_DIRECTION_ROW": "defaults.direction_row",
    "DEFAULT_EXCHANGE_ID": "defaults.exchange_id",
    "DEFAULT_FILTER_SYMBOL": "defaults.filter_symbol",
    "DEFAULT_HAS_SNAPSHOT": "defaults.has_snapshot",
    "DEFAULT_HOURS": "defaults.hours",
    "DEFAULT_JOURNAL_FILES": "defaults.journal_files",
    "DEFAULT_ORDER_ID": "defaults.order_id",
    "DEFAULT_ORPHANED_COUNT": "defaults.orphaned_count",
    "DEFAULT_PNL": "defaults.pnl",
    "DEFAULT_PRICE": "defaults.price",
    "DEFAULT_QUANTITY": "defaults.quantity",
    "DEFAULT_REASON_DETAIL": "defaults.reason_detail",
    "DEFAULT_REASON_ROW": "defaults.reason_row",
    "DEFAULT_SIDE": "defaults.side",
    "DEFAULT_SLIPPAGE_PCT": "defaults.slippage_pct",
    "DEFAULT_SNAPSHOT_AGE_S": "defaults.snapshot_age_s",
    "DEFAULT_SNAPSHOT_BOTS": "defaults.snapshot_bots",
    "DEFAULT_STRATEGY": "defaults.strategy",
    "DEFAULT_SYMBOL": "defaults.symbol",
    "DEFAULT_TEXTS": "default_texts",
    "DEFAULT_TIMEFRAME": "defaults.timeframe",
    "DEFAULT_TIMESTAMP": "defaults.timestamp",
    "DEFAULT_TOTAL_ENTRIES": "defaults.total_entries",
    "DEFAULT_TOTAL_PNL": "defaults.total_pnl",
    "DEFAULT_UNIQUE_BOTS": "defaults.unique_bots",
    "DETAIL_BOT_ID_SLICE": "slices.detail_bot_id",
    "DETAIL_CONFIDENCE_FORMAT": "formats.detail_confidence",
    "DETAIL_COST_FORMAT": "formats.detail_cost",
    "DETAIL_FONT_FAMILY": "detail_view.font_family",
    "DETAIL_FONT_POINT_SIZE": "detail_view.font_point_size",
    "DETAIL_GROUP_TITLE": "detail_group.title",
    "DETAIL_JOIN": "detail_view.join",
    "DETAIL_LABEL_GAP": "formats.label_gap",
    "DETAIL_LABEL_SUFFIX": "formats.label_suffix",
    "DETAIL_PNL_FORMAT": "formats.detail_pnl",
    "DETAIL_PRICE_FORMAT": "formats.detail_price",
    "DETAIL_QUANTITY_FORMAT": "formats.detail_quantity",
    "DETAIL_READ_ONLY": "detail_view.read_only",
    "DETAIL_SLIPPAGE_FORMAT": "formats.detail_slippage",
    "DETAIL_STYLE": "detail_view.style_sheet",
    "DETAIL_TITLE": "titles.detail",
    "DETAIL_TITLE_TEXT": "titles.detail_text",
    "DIRECTION_COLUMN": "journal_table.direction_column",
    "DIRECTION_LABEL": "labels.direction",
    "EDIT_TRIGGERS": "journal_table.edit_triggers",
    "ENTRY_LIMIT": "defaults.entry_limit",
    "EXCHANGE_LABEL": "labels.exchange",
    "FIELD_LINE_FORMAT": "formats.field_line",
    "FORMATS": "formats",
    "GROUP_STYLE": "journal_group.style_sheet",
    "HEADER_ORDER": "header_order",
    "HEADER_RESIZE_MODE": "journal_table.header_resize_mode",
    "INFO_COLOR": "colors.info",
    "JOURNAL_FILES_FORMAT": "formats.journal_files",
    "JOURNAL_FILES_LABEL_TEXT": "default_texts.journal_files",
    "JOURNAL_GROUP_TITLE": "journal_group.title",
    "LABELS": "labels",
    "LINE_WEIGHT": "detail_view.line_weight",
    "MUTED_COLOR": "colors.muted",
    "NEGATIVE_COLOR": "colors.negative",
    "NO_CELL_COLOR": "no_cell_color",
    "NO_DATA": "no_data",
    "NO_DETAIL_HTML": "no_detail_html",
    "NO_SELECTION_INDEX": "no_selection_index",
    "NO_TEXT": "no_text",
    "ORDER_ID_LABEL": "labels.order_id",
    "ORPHANS_FORMAT": "formats.orphans",
    "ORPHANS_LABEL_TEXT": "default_texts.orphans",
    "OUTER_SPLITTER_CHILDREN": "splitter.children",
    "OUTER_SPLITTER_SIZES_PX": "splitter.requested_sizes_px",
    "PERIOD_DEFAULT_INDEX": "period_filter.default_index",
    "PERIOD_ITEMS": "period_items",
    "PERIOD_LABEL_TEXT": "period_label.text",
    "PNL_COLUMN": "journal_table.pnl_column",
    "PNL_LABEL": "labels.pnl",
    "PNL_LINE_FORMAT": "formats.pnl_line",
    "POSITIVE_COLOR": "colors.positive",
    "PRICE_LABEL": "labels.price",
    "QUANTITY_LABEL": "labels.quantity",
    "REASON_LABEL": "labels.reason",
    "RECON_BUTTON_STYLE": "recon_button.style_sheet",
    "RECON_BUTTON_TEXT": "recon_button.text",
    "RECON_LABEL_TEXT": "default_texts.recon",
    "RECON_TEXT_FORMAT": "formats.recon_text",
    "RECOVERY_GROUP_TITLE": "recovery_group.title",
    "RECOVERY_LABEL_STYLE": "snapshot_label.style_sheet",
    "RECOVERY_ORDER": "recovery_order",
    "ROW_BOT_ID_SLICE": "slices.row_bot_id",
    "ROW_PNL_FORMAT": "formats.row_pnl",
    "ROW_PRICE_FORMAT": "formats.row_price",
    "ROW_QUANTITY_FORMAT": "formats.row_quantity",
    "ROW_REASON_SLICE": "slices.row_reason",
    "ROW_TIME_FORMAT": "formats.row_time",
    "SECONDS_PER_MINUTE": "seconds_per_minute",
    "SELECTION_BEHAVIOR": "journal_table.selection_behavior",
    "SIDE_LABEL": "labels.side",
    "SKIN": "skin",
    "SLICES": "slices",
    "SLIPPAGE_LABEL": "labels.slippage",
    "SNAPSHOT_BUTTON_STYLE": "snapshot_button.style_sheet",
    "SNAPSHOT_BUTTON_TEXT": "snapshot_button.text",
    "SNAPSHOT_LABEL_TEXT": "default_texts.snapshot",
    "SNAPSHOT_MINUTES_FORMAT": "formats.snapshot_minutes",
    "SNAPSHOT_MINUTE_CUTOFF_S": "snapshot_minute_cutoff_s",
    "SNAPSHOT_SECONDS_FORMAT": "formats.snapshot_seconds",
    "SNAPSHOT_TEXT_FORMAT": "formats.snapshot_text",
    "SPLITTER_CHILDREN_COLLAPSIBLE": "splitter.children_collapsible",
    "SPLITTER_HANDLE_WIDTH_PX": "splitter.handle_width_px",
    "SPLITTER_HORIZONTAL": "bottom_splitter.orientation",
    "SPLITTER_VERTICAL": "splitter.orientation",
    "STATS_LABEL_STYLE": "stats_label.style_sheet",
    "STATS_LABEL_TEXT": "default_texts.stats",
    "STATS_TEXT_FORMAT": "formats.stats",
    "STRATEGY_LABEL": "labels.strategy",
    "SYMBOL_LABEL": "labels.symbol",
    "TA_CONTEXT_TITLE": "titles.ta_context",
    "TA_CONTEXT_TITLE_TEXT": "titles.ta_context_text",
    "TIMEFRAME_LABEL": "labels.timeframe",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TIME_LABEL": "labels.time",
    "TITLES": "titles",
    "TITLE_LINE_FORMAT": "formats.title_line",
    "TITLE_WEIGHT": "detail_view.title_weight",
    "VERTICAL_HEADER_VISIBLE": "journal_table.vertical_header_visible",
    "VOTES_COLOR": "colors.votes",
    "VOTES_TITLE": "titles.votes",
    "VOTES_TITLE_TEXT": "titles.votes_text",
    "VOTE_INDENT": "formats.vote_indent",
    "VOTE_JOIN": "formats.vote_join",
    "VOTE_LINE_FORMAT": "formats.vote_line",
}

# The two values of the always-present first drop-list item.
LIST_MEMBERS = {"ALL_BOTS_TEXT": "all_bots_item", "ALL_BOTS_DATA": "all_bots_item"}

# The twenty-two branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "REFRESH_START",
    "REFRESH_NO_JOURNAL",
    "REFRESH_STATS",
    "REFRESH_QUERY",
    "REFRESH_ROWS",
    "REFRESH_NO_RECOVERY",
    "REFRESH_SNAPSHOT",
    "REFRESH_NO_SNAPSHOT",
    "REFRESH_FILES",
    "REFRESH_NO_RECON",
    "REFRESH_RECON",
    "REFRESH_NO_RESULT",
    "REFRESH_RETURN",
    "DETAIL_START",
    "DETAIL_SKIPPED",
    "DETAIL_VOTES",
    "DETAIL_SET",
    "FILTER_START",
    "FILTER_ITEM",
    "FILTER_RESTORED",
    "FILTER_LOST",
    "FILTER_RETURN",
)

# The three values no snapshot key carries, each with the check that
# covers it. METHOD is the name the bridge registers under, LOGGER_NAME
# the logger the shipped screen names, and PANE_MODEL the screen state
# the bridge keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_journal_tab_method",
    "LOGGER_NAME": "test_the_surface_names_the_same_logger_as_the_screen",
    "PANE_MODEL": "test_the_bridge_resets_the_screen_state_on_request",
}

STATE_ONLY_KEYS = {
    "calls",
    "entry_count",
    "entry_query",
    "journal_files_label",
    "orphans_label",
    "recon_label",
}


def at_path(payload, path):
    """The payload value one dotted path names."""
    found = payload
    for step in path.split("."):
        found = found[step]
    return found


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a snapshot path, a
    member of the first drop-list item, one of the branch markers, or
    one of the three named with the check that covers it.
    """
    payload = surface.build_view_model(surface.JournalTabModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == [
                    list(inner) if isinstance(inner, tuple) else inner
                    for inner in value
                ], name
            else:
                assert carried == value, name
        elif name in LIST_MEMBERS:
            assert value in payload[LIST_MEMBERS[name]], name
        elif name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 166
    assert len(CALL_CONSTANTS) == 22
    assert len(LIST_MEMBERS) == 2
    assert len(NOT_IN_THE_SNAPSHOT) == 3


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.JournalTabModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= set(LIST_MEMBERS.values())
    answered.add("call_names")
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing.

    A value that reaches no snapshot path and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model(surface.JournalTabModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "COLUMNS" in surface_constants()
    assert "GROUP_STYLE" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "JournalTabModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        model, _journal = drive_new(spec)
        seen.update(call[0] for call in model.calls)
    _tab, dropped = bot_filter_after_a_bot_leaves()
    seen.update(call[0] for call in dropped.calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    skipped, _a = drive_new(BY_NAME["no_snapshot"])
    assert [call[0] for call in skipped.calls].count(surface.REFRESH_NO_SNAPSHOT) == 1
    assert skipped.snapshot_text == surface.SNAPSHOT_LABEL_TEXT
    written, _b = drive_new(BY_NAME["happy"])
    assert [call[0] for call in written.calls].count(surface.REFRESH_SNAPSHOT) == 1
    assert written.snapshot_text != surface.SNAPSHOT_LABEL_TEXT


# The surface carries its own values


class FrozenClock:
    """A clock whose three readings are fixed and unlike any real one."""

    @staticmethod
    def ctime(_when):
        return "MOVED CTIME"

    @staticmethod
    def localtime(_when):
        return (1999, 1, 1, 3, 4, 5, 0, 1, 0)

    @staticmethod
    def strftime(_pattern, _parts):
        return "99:99:99"


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_screen(monkeypatch):
    """The surface read its values off the screen it replaces.

    A surface that read the shipped screen would follow it, and the
    whole comparison above would be one side read twice. The shipped
    clock is moved and the surface must not move with it.
    """
    app()
    from src.gui import journal_tab as shipped

    spec = BY_NAME["happy"]
    before = qt_trace(*drive_old(spec))
    monkeypatch.setattr(shipped, "time", FrozenClock)
    moved = qt_trace(*drive_old(spec))
    assert moved["journal_table"]["rows"][0][0] == "99:99:99"
    assert before["journal_table"]["rows"][0][0] != "99:99:99"
    model, _journal = drive_new(spec)
    payload = surface.build_view_model(model)
    assert payload["journal_table"]["rows"][0][0] != "99:99:99"
    assert payload["journal_table"]["rows"] == before["journal_table"]["rows"]
    monkeypatch.undo()
    assert qt_trace(*drive_old(spec))["journal_table"]["rows"][0][0] != "99:99:99"


def test_the_surface_does_not_follow_a_screen_that_builds_nothing(monkeypatch):
    """The surface asked the shipped screen to build its controls."""
    app()
    from src.gui import journal_tab as shipped

    payload = surface.build_view_model(surface.JournalTabModel())
    monkeypatch.setattr(shipped.JournalTab, "_setup_ui", lambda self: None)
    stripped = shipped.JournalTab()
    assert stripped.layout() is None
    assert not hasattr(stripped, "_journal_table")
    again = surface.build_view_model(surface.JournalTabModel())
    assert again == payload
    assert again["journal_table"]["columns"] == list(surface.COLUMNS)
    monkeypatch.undo()
    assert shipped.JournalTab().layout() is not None


def test_the_surface_names_the_same_logger_as_the_screen():
    """The surface names a logger the shipped screen does not use."""
    from src.gui import journal_tab as shipped

    assert surface.LOGGER_NAME == shipped.logger.name
    assert surface.LOGGER_NAME == "acervator.gui"


# The splitter sizes are a request, not a read-back


def plain_splitter(orientation, requested, size):
    """Two blank panes in a splitter, given one size request."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter, QWidget

    app()
    split = QSplitter(
        Qt.Orientation.Vertical
        if orientation == "vertical"
        else Qt.Orientation.Horizontal
    )
    split.setHandleWidth(surface.SPLITTER_HANDLE_WIDTH_PX)
    split.setChildrenCollapsible(surface.SPLITTER_CHILDREN_COLLAPSIBLE)
    for _ in requested:
        split.addWidget(QWidget())
    split.resize(size[0], size[1])
    split.setSizes(list(requested))
    return split.sizes()


def test_a_different_size_request_settles_differently():
    """The platform ignores the size request, so requesting is unmeasurable.

    The panes are never given the sizes asked for. What proves the two
    sides ask for the same thing is that a different request settles at
    a different read-back.
    """
    size = (900, 640)
    asked = plain_splitter("vertical", surface.OUTER_SPLITTER_SIZES_PX, size)
    other = plain_splitter("vertical", surface.BOTTOM_SPLITTER_SIZES_PX, size)
    assert asked != list(surface.OUTER_SPLITTER_SIZES_PX)
    assert asked != other, (asked, other)
    assert plain_splitter("vertical", surface.OUTER_SPLITTER_SIZES_PX, size) == asked


def test_the_two_sides_ask_for_the_same_splitter_sizes():
    """The surface asks for a pane split the shipped screen does not."""
    app()
    tab, _journal = drive_old(BY_NAME["happy"])
    payload = model_payload(BY_NAME["happy"])
    rebuilt = widget_painted_by_the_model(payload)
    render_offscreen(tab, SPLIT_SIZE)
    render_offscreen(rebuilt, SPLIT_SIZE)
    parts = qt_parts(tab)
    mine = rebuilt_parts(rebuilt)
    assert parts["splitter"].size() == mine["splitter"].size()
    assert parts["splitter"].sizes() == mine["splitter"].sizes()
    assert parts["bottom_splitter"].sizes() == mine["bottom_splitter"].sizes()
    assert len(parts["splitter"].sizes()) == 2


# The colours


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    app()
    written = {name: canonical(value) for name, value in surface.COLORS.items()}
    assert len(set(written.values())) == len(surface.COLORS), written
    assert written["muted"] == "#888888"
    assert all(len(value) == 7 for value in written.values()), written


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    app()
    assert canonical(surface.POSITIVE_COLOR) == "#00ff88"
    assert canonical("#0088ff") != canonical(surface.POSITIVE_COLOR)
    assert canonical(surface.NEGATIVE_COLOR) != canonical("#66ff33")


def test_the_muted_grey_is_compared_as_text_because_its_channels_are_equal():
    """A colour with three equal channels was left to a colour check.

    ``#888`` reads the same with any two channels swapped, so no colour
    check can report a swap in it. It is compared as exact text inside
    the detail pane, which the detail comparison covers.
    """
    app()
    swapped = canonical("#888")
    assert swapped == canonical(surface.MUTED_COLOR)
    assert surface.MUTED_COLOR in surface.FIELD_LINE_FORMAT
    assert surface.MUTED_COLOR in surface.PNL_LINE_FORMAT
    model, _journal = drive_new(BY_NAME["happy"])
    payload = surface.build_view_model(model)
    assert payload["detail_view"]["html"].count(surface.MUTED_COLOR) == 18


# The pictures


ORIENTATIONS = {"vertical": "Vertical", "horizontal": "Horizontal"}

RECOVERY_DEFAULTS = {
    "snapshot_label": "snapshot",
    "recon_label": "recon",
    "orphans_label": "orphans",
    "journal_files_label": "journal_files",
}


def model_payload(spec=None):
    """The view model after the same driving, stamped."""
    model, _journal = drive_new(spec or BY_NAME["happy"])
    return sealed(surface.build_view_model(model))


def widget_painted_by_the_tab(spec=None):
    """The screen the shipped Qt tab builds, after the same driving."""
    tab, _journal = drive_old(spec or BY_NAME["happy"])
    return tab


def widget_painted_by_the_model(payload):
    """A screen built only from the payload, never from the shipped tab.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QComboBox,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    app()

    def drop_list(declared):
        box = QComboBox()
        for text, data in declared["items"]:
            box.addItem(text, data)
        box.setCurrentIndex(declared["index"])
        return box

    def styled_label(declared):
        label = QLabel(declared["text"])
        label.setStyleSheet(declared["style_sheet"])
        return label

    def styled_button(declared):
        button = QPushButton(declared["text"])
        button.setStyleSheet(declared["style_sheet"])
        button.setEnabled(declared["enabled"])
        return button

    def group(declared):
        box = QGroupBox(declared["title"])
        box.setStyleSheet(declared["style_sheet"])
        return box

    def splitter_for(declared):
        split = QSplitter(
            getattr(Qt.Orientation, ORIENTATIONS[declared["orientation"]])
        )
        split.setHandleWidth(declared["handle_width_px"])
        split.setChildrenCollapsible(declared["children_collapsible"])
        return split

    screen = QWidget()
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    outer.setContentsMargins(*payload["container"]["margins_px"])
    outer.setSpacing(payload["container"]["spacing_px"])

    header = QHBoxLayout()
    stats_label = QLabel(payload["default_texts"]["stats"])
    stats_label.setStyleSheet(payload["stats_label"]["style_sheet"])
    header.addWidget(stats_label)
    header.addStretch()
    bot_filter = QComboBox()
    bot_filter.addItem(*payload["all_bots_item"])
    bot_filter.setMinimumWidth(payload["bot_filter"]["minimum_width_px"])
    header.addWidget(QLabel(payload["bot_label"]["text"]))
    header.addWidget(bot_filter)
    header.addWidget(QLabel(payload["period_label"]["text"]))
    header.addWidget(drop_list(payload["period_filter"]))
    outer.addLayout(header)

    splitter = splitter_for(payload["splitter"])
    journal_group = group(payload["journal_group"])
    journal_layout = QVBoxLayout(journal_group)
    declared = payload["journal_table"]
    table = QTableWidget()
    table.setColumnCount(declared["column_count"])
    table.setHorizontalHeaderLabels(declared["columns"])
    table.horizontalHeader().setSectionResizeMode(
        getattr(QHeaderView.ResizeMode, declared["header_resize_mode"])
    )
    table.setAlternatingRowColors(declared["alternating_row_colors"])
    table.setEditTriggers(
        getattr(QAbstractItemView.EditTrigger, declared["edit_triggers"])
    )
    table.verticalHeader().setVisible(declared["vertical_header_visible"])
    table.setSelectionBehavior(
        getattr(QAbstractItemView.SelectionBehavior, declared["selection_behavior"])
    )
    journal_layout.addWidget(table)
    splitter.addWidget(journal_group)

    bottom = splitter_for(payload["bottom_splitter"])
    detail_group = group(payload["detail_group"])
    detail_layout = QVBoxLayout(detail_group)
    shown = payload["detail_view"]
    detail_view = QTextEdit()
    detail_view.setReadOnly(shown["read_only"])
    detail_view.setFont(QFont(shown["font_family"], shown["font_point_size"]))
    detail_view.setStyleSheet(shown["style_sheet"])
    detail_layout.addWidget(detail_view)
    bottom.addWidget(detail_group)

    recovery_group = group(payload["recovery_group"])
    recovery_layout = QVBoxLayout(recovery_group)
    recovery_labels = {}
    for name, default in RECOVERY_DEFAULTS.items():
        line = QLabel(payload["default_texts"][default])
        line.setStyleSheet(payload[name]["style_sheet"])
        recovery_labels[name] = line
        recovery_layout.addWidget(line)
    button_row = QHBoxLayout()
    button_row.addWidget(styled_button(payload["recon_button"]))
    button_row.addWidget(styled_button(payload["snapshot_button"]))
    recovery_layout.addLayout(button_row)
    recovery_layout.addStretch()
    bottom.addWidget(recovery_group)

    bottom.setSizes(list(payload["bottom_splitter"]["requested_sizes_px"]))
    splitter.addWidget(bottom)
    splitter.setSizes(list(payload["splitter"]["requested_sizes_px"]))
    outer.addWidget(splitter)

    bot_filter.clear()
    for text, data in payload["bot_filter"]["items"]:
        bot_filter.addItem(text, data)
    bot_filter.setCurrentIndex(payload["bot_filter"]["index"])

    stats_label.setText(payload["stats_label"]["text"])
    table.setRowCount(declared["row_count"])
    for row, cells in enumerate(declared["rows"]):
        for col, text in enumerate(cells):
            cell = QTableWidgetItem(text)
            cell.setTextAlignment(Qt.AlignmentFlag(declared["cell_alignment_value"]))
            painted = declared["row_colors"][row][col]
            if painted is not None:
                cell.setForeground(QColor(painted))
            table.setItem(row, col, cell)
    for name, line in recovery_labels.items():
        line.setText(payload[name]["text"])
    detail_view.setHtml(shown["html"])
    return screen


def rebuilt_parts(screen):
    """The rebuilt screen's two splitters, found by walking its layouts."""
    outer = screen.layout()
    splitter = outer.itemAt(1).widget()
    return {"splitter": splitter, "bottom_splitter": splitter.widget(1)}


PICTURE_SCENARIOS = ["happy", "empty_entries", "no_snapshot", "unicode", "bare_entry"]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different screen than the shipped tab."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real journals, one driven into each side. Every row carries a
    different amount, so a pass proves the comparison reports a screen
    painted differently.
    """
    app()
    other = scenario("grown", entries=ENTRIES_GROWN)
    assert ENTRIES_HAPPY != ENTRIES_GROWN
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_tab(BY_NAME["happy"]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(other)), PIXEL_SIZE
        ),
        note="the happy journal against the grown journal",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_screen_shows_more_than_one_colour(name):
    """The two sides matched because the screen painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        assert image.width() == PIXEL_SIZE[0]
        assert image.height() == PIXEL_SIZE[1]
        seen = set()
        for x in range(0, image.width(), 5):
            for y in range(0, image.height(), 5):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload()
    payload["journal_table"]["rows"][0][2] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.build_view_model(surface.JournalTabModel()))


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one
    em per character, so two strings of equal length need equal width.
    With a font database the glyphs decide the width. Both answers are
    handled here and the file is run both ways.
    """
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert (
            narrow.sizeHint().width() != wide.sizeHint().width()
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow.sizeHint().width() == wide.sizeHint().width()
        ), "the host reports no fonts and the glyphs still have their own widths"


# What a picture cannot see, read off both sides instead


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The accessible name, the value behind each drop-list item, the
    filter values the journal was queried with, the edit and selection
    rules and the vertical header's hidden state paint nothing. Each is
    read off the shipped tab and off the surface directly.
    """
    app()
    spec = BY_NAME["happy"]
    old = qt_trace(*drive_old(spec))
    model, _journal = drive_new(spec)
    new = surface_trace(model, surface.build_view_model(model))
    for key in ("accessible_name", "entry_query"):
        assert new[key] == old[key], key
    assert new["bot_filter"]["items"] == old["bot_filter"]["items"]
    assert new["period_filter"]["items"] == old["period_filter"]["items"]
    assert (
        new["journal_table"]["edit_triggers"] == old["journal_table"]["edit_triggers"]
    )
    assert (
        new["journal_table"]["selection_behavior"]
        == old["journal_table"]["selection_behavior"]
    )
    assert (
        new["journal_table"]["vertical_header_visible"]
        == old["journal_table"]["vertical_header_visible"]
    )
    assert old["accessible_name"] == "Journal Tab"
    assert old["entry_query"] == {"bot_id": "", "hours": 24, "limit": 500}
    assert old["journal_table"]["vertical_header_visible"] is False


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


def test_the_bridge_registers_the_journal_tab_method():
    """The renderer cannot reach the Journal screen over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "journal_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["journal_table"]["columns"] == list(surface.COLUMNS)
    assert result["recon_button"]["text"] == surface.RECON_BUTTON_TEXT


def test_the_bridge_resets_the_screen_state_on_request():
    """The screen state the bridge keeps was never cleared."""
    filled = bridge_answer(
        {
            "reset": True,
            "statistics": STATS,
            "entries": ENTRIES_HAPPY,
            "recovery_info": RECOVERY_FRESH,
            "reconciliation_result": RECON_RESULT,
            "bot_statuses": BOT_STATUSES,
            "selected_row": 0,
        }
    )["result"]
    assert filled["journal_table"]["row_count"] == 3
    assert filled["bot_filter"]["count"] == 3
    assert filled["detail_view"]["html"] != surface.NO_DETAIL_HTML
    kept = bridge_answer({})["result"]
    assert kept["bot_filter"]["count"] == 3
    assert kept["detail_view"]["html"] == filled["detail_view"]["html"]
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["journal_table"]["row_count"] == 0
    assert cleared["bot_filter"]["count"] == 1
    assert cleared["detail_view"]["html"] == surface.NO_DETAIL_HTML
    assert cleared["stats_label"]["text"] == surface.STATS_LABEL_TEXT


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(
        {"reset": True, "statistics": STATS, "entries": ENTRIES_HAPPY}
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["journal_table"]["row_count"] == 3
    assert encoded["result"]["entry_query"] == {
        "bot_id": "",
        "hours": 24,
        "limit": 500,
    }


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'journal_tab.state', 'params':"
    " {'reset': True, 'statistics': {'total_entries': 2, 'unique_bots': 1,"
    " 'total_pnl': 5.5}, 'entries': [{'symbol': 'BTC/USD', 'pnl': 1.25}]}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude):
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
    """Reaching the Journal screen pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["journal_table"]["row_count"] == 1
    assert (
        result["stats_label"]["text"] == "Journal: 2 entries | 1 bots | P/L: $+5.5000"
    )


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
