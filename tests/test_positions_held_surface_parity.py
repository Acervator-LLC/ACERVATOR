"""The Qt Positions Held tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, a
different colour, a different column, a different number format, a
different layout number, a different message box, a different button or
a different branch than ``PositionsHeldTabMixin`` builds on the same
input.
"""

from __future__ import annotations

import ast
import asyncio
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

from PySide6.QtWidgets import QMessageBox as QtMessageBox

from src.gui.main_tabs import positions_held_surface as surface
from tests.fixtures.host_fonts import (
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "positions_held_tab.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (1100, 720)

CONNECT_TOTAL = 1
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 1
SHIPPED_FUNCTION_TOTAL = 3
PAYLOAD_KEY_TOTAL = 38
CONSTANT_TOTAL = 131


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


# ---------------------------------------------------------------------
# The bot, its config and the bot manager, as the test owns them. The Qt
# tab is driven with these; the surface is driven with its own. Neither
# side reads the other's.
# ---------------------------------------------------------------------


class Config:
    """The bot config the tab reads one field from."""

    def __init__(self, base_currency):
        self.base_currency = base_currency


class Bot:
    """The Extractor bot the tab reads its pool and its positions from."""

    def __init__(
        self,
        base_currency=None,
        chunk_size_usd=0.0,
        chunk_free_base=0.0,
        chunk_size_base=0.0,
        extracted_total=0.0,
        pool_color_name="green",
        positions=None,
        pool_color_raises=None,
        positions_raise=None,
        fire_raises=None,
        with_config=True,
    ):
        if with_config:
            self.config = Config(base_currency)
        self._chunk_size_usd = chunk_size_usd
        self._chunk_free_base = chunk_free_base
        self._chunk_size_base = chunk_size_base
        self._chunk_extracted_total = extracted_total
        self.pool_color_name = pool_color_name
        self.positions = list(positions or [])
        self.pool_color_raises = pool_color_raises
        self.positions_raise = positions_raise
        self.fire_raises = fire_raises
        self.fired = []

    def pool_color(self):
        if self.pool_color_raises is not None:
            raise self.pool_color_raises
        return self.pool_color_name

    def positions_for_gui(self):
        if self.positions_raise is not None:
            raise self.positions_raise
        return self.positions

    def manual_fire_position(self, pair):
        if self.fire_raises is not None:
            raise self.fire_raises
        self.fired.append(pair)
        return ["close", pair]


class Manager:
    """The bot manager the fire path asks for its async loop."""

    def __init__(self, loop=None, with_loop=True):
        if with_loop:
            self._async_loop = loop


LOOP_STANDIN = ["a running loop"]

HOST_ACCESSIBLE_NAME = "Positions Held tab host"


# ---------------------------------------------------------------------
# The message boxes and the loop hand-off, recorded rather than shown
# ---------------------------------------------------------------------


#: The button set Qt gives a warning or an information box when the
#: caller passes none. Read once, before any swap of the Qt name.
OK_FROM_QT = QtMessageBox.StandardButton.Ok.value
YES_FROM_QT = QtMessageBox.StandardButton.Yes
NO_FROM_QT = QtMessageBox.StandardButton.No


RECORDED_BOXES: list = []
RECORDED_ARGUMENT_COUNTS: list = []


class BoxRecorder:
    """Stands in for ``QMessageBox`` and records every box the tab raises.

    ``question`` answers with whatever ``ANSWER`` holds, which is how the
    operator's Yes or No is driven. ``Yes`` and ``No`` are the real
    values, so the shipped comparison against them is unchanged.
    """

    ANSWER = None

    Yes = YES_FROM_QT
    No = NO_FROM_QT

    @staticmethod
    def question(_parent, title, text, buttons, default):
        RECORDED_ARGUMENT_COUNTS.append(5)
        RECORDED_BOXES.append(
            {
                "icon": surface.QUESTION_ICON,
                "title": title,
                "text": text,
                "buttons_value": int(buttons.value),
                "default_button_value": int(default.value),
            }
        )
        return BoxRecorder.ANSWER

    @staticmethod
    def warning(_parent, title, text):
        RECORDED_ARGUMENT_COUNTS.append(3)
        RECORDED_BOXES.append(
            {
                "icon": surface.WARNING_ICON,
                "title": title,
                "text": text,
                "buttons_value": OK_FROM_QT,
                "default_button_value": surface.NO_DEFAULT_BUTTON_VALUE,
            }
        )
        return None

    @staticmethod
    def information(_parent, title, text):
        RECORDED_ARGUMENT_COUNTS.append(3)
        RECORDED_BOXES.append(
            {
                "icon": surface.INFORMATION_ICON,
                "title": title,
                "text": text,
                "buttons_value": OK_FROM_QT,
                "default_button_value": surface.NO_DEFAULT_BUTTON_VALUE,
            }
        )
        return None


SCHEDULED: list = []


class Schedule:
    """Where the shipped fire path hands its close, and what it does."""

    RAISES = None

    @staticmethod
    def run(coro, loop):
        if Schedule.RAISES is not None:
            raise Schedule.RAISES
        SCHEDULED.append([coro, loop])
        return len(SCHEDULED)


class QtSeams:
    """Swap the two Qt seams the fire path uses, and put them back.

    ``PySide6.QtWidgets.QMessageBox`` and
    ``asyncio.run_coroutine_threadsafe`` are process-wide names. Both are
    read before the swap and written back on the way out, so the run
    order of the file cannot leave either one changed.
    """

    def __init__(self, answer=None, schedule_raises=None):
        self.answer = answer
        self.schedule_raises = schedule_raises
        self.widgets = None
        self.first_box = None
        self.first_schedule = None

    def __enter__(self):
        import PySide6.QtWidgets as widgets

        self.widgets = widgets
        self.first_box = widgets.QMessageBox
        self.first_schedule = asyncio.run_coroutine_threadsafe
        RECORDED_BOXES.clear()
        RECORDED_ARGUMENT_COUNTS.clear()
        SCHEDULED.clear()
        BoxRecorder.ANSWER = self.answer
        Schedule.RAISES = self.schedule_raises
        widgets.QMessageBox = BoxRecorder
        asyncio.run_coroutine_threadsafe = Schedule.run
        return self

    def __exit__(self, _kind, _value, _trace):
        self.widgets.QMessageBox = self.first_box
        asyncio.run_coroutine_threadsafe = self.first_schedule
        BoxRecorder.ANSWER = None
        Schedule.RAISES = None
        return False


def host_class():
    """The window the tab lives in, holding only what the mixin declares."""
    from PySide6.QtWidgets import QWidget

    from src.gui.live_settings.positions_held_tab import PositionsHeldTabMixin

    class Host(PositionsHeldTabMixin, QWidget):
        def __init__(self, bot, manager):
            super().__init__()
            self.setAccessibleName(HOST_ACCESSIBLE_NAME)
            self._bot = bot
            self._bm = manager
            self.forms = []

        def _configure_form(self, form):
            self.forms.append(form)

    return Host


# ---------------------------------------------------------------------
# The inputs. One scenario drives both sides.
# ---------------------------------------------------------------------


def position(**named):
    """One open position with every field the table row reads."""
    fields = {
        "pair": "ETH/BTC",
        "state": "drawdown",
        "tier": 2,
        "alt_units": 1.23456789,
        "entry_usd": 1234.5678,
        "current_usd_approx": 1180.25,
        "delta_pct_usd_approx": -4.3625,
        "corrections_fired": 3,
    }
    fields.update(named)
    return fields


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's pair"

POSITIONS_HAPPY = [
    position(),
    position(
        pair="SOL/BTC",
        state="bullish_exit",
        tier=1,
        alt_units=9.5,
        delta_pct_usd_approx=7.25,
        corrections_fired=0,
    ),
    position(
        pair="XRP/BTC",
        state="in_flight",
        tier=3,
        alt_units=0.0,
        delta_pct_usd_approx=0.0,
        corrections_fired=11,
    ),
]

POSITIONS_GROWN = [
    position(
        pair="DOGE/BTC",
        state="in_flight",
        tier=9,
        alt_units=987654.321,
        entry_usd=0.00012,
        current_usd_approx=99999.5,
        delta_pct_usd_approx=812.5,
        corrections_fired=99,
    ),
    position(
        pair="LTC/BTC",
        state="bullish_exit",
        tier=4,
        alt_units=55.5,
        entry_usd=777.25,
        current_usd_approx=1.5,
        delta_pct_usd_approx=-99.75,
        corrections_fired=1,
    ),
]


def scenario(name, **named):
    """One driving set: the bot readings, the manager and the fire click."""
    spec = {
        "name": name,
        "base_currency": "BTC",
        "chunk_size_usd": 250.75,
        "chunk_free_base": 0.00512345,
        "chunk_size_base": 0.00040001,
        "extracted_total": 0.00218,
        "pool_color": "yellow",
        "pool_color_raises": None,
        "positions": POSITIONS_HAPPY,
        "positions_raise": None,
        "fire_raises": None,
        "with_config": True,
        "manager": True,
        "with_loop": True,
        "loop": LOOP_STANDIN,
        "fire_row": None,
        "fire_answer": None,
        "schedule_raises": None,
    }
    spec.update(named)
    return spec


SCENARIOS = [
    scenario("happy"),
    scenario("empty_positions", positions=[]),
    scenario("no_positions_reading", positions_raise=RuntimeError("bot is gone")),
    scenario("pool_color_failed", pool_color_raises=RuntimeError("no pool")),
    scenario("pool_color_red", pool_color="red"),
    scenario("pool_color_green", pool_color="green"),
    scenario("pool_color_unknown", pool_color="teal"),
    scenario("pool_color_empty", pool_color=""),
    scenario("pool_color_wrong_capitals", pool_color="GREEN"),
    scenario("pool_color_is_a_number", pool_color=7),
    scenario("chunk_values_are_none", chunk_size_usd=None, chunk_free_base=None),
    scenario("chunk_values_are_zero", chunk_size_usd=0, chunk_size_base=0),
    scenario(
        "chunk_values_are_negative",
        chunk_size_usd=-250.75,
        chunk_free_base=-0.5,
        extracted_total=-0.00218,
    ),
    scenario(
        "chunk_values_are_a_thousand_million",
        chunk_size_usd=1e9,
        chunk_free_base=1e9,
        chunk_size_base=1e9,
        extracted_total=1e9,
    ),
    scenario(
        "chunk_values_are_one_billionth",
        chunk_size_usd=1e-9,
        chunk_free_base=1e-9,
        chunk_size_base=1e-9,
        extracted_total=1e-9,
    ),
    scenario("chunk_value_is_infinite", chunk_size_usd=math.inf),
    scenario("base_currency_is_unicode", base_currency=UNICODE_TEXT),
    scenario("base_currency_is_markup", base_currency=MARKUP_TEXT),
    scenario("base_currency_has_an_apostrophe", base_currency=APOSTROPHE_TEXT),
    scenario("base_currency_has_a_newline", base_currency=NEWLINE_TEXT),
    scenario("base_currency_is_two_hundred_characters", base_currency=LONG_TEXT),
    scenario("base_currency_is_a_number", base_currency=42),
    scenario("base_currency_is_none", base_currency=None),
    scenario("bare_position", positions=[{}]),
    scenario(
        "zero_everywhere",
        positions=[
            position(
                tier=0,
                alt_units=0.0,
                entry_usd=0.0,
                current_usd_approx=0.0,
                delta_pct_usd_approx=0.0,
                corrections_fired=0,
            )
        ],
    ),
    scenario(
        "negative_everywhere",
        positions=[
            position(
                tier=-2,
                alt_units=-1.5,
                entry_usd=-1234.5,
                current_usd_approx=-1180.0,
                delta_pct_usd_approx=-99.99,
                corrections_fired=-3,
            )
        ],
    ),
    scenario(
        "a_thousand_million",
        positions=[
            position(
                tier=1_000_000_000,
                alt_units=1e9,
                entry_usd=1e9,
                current_usd_approx=1e9,
                delta_pct_usd_approx=1e9,
                corrections_fired=1_000_000_000,
            )
        ],
    ),
    scenario(
        "one_billionth",
        positions=[
            position(
                alt_units=1e-9,
                entry_usd=1e-9,
                current_usd_approx=1e-9,
                delta_pct_usd_approx=1e-9,
            )
        ],
    ),
    scenario(
        "unicode",
        positions=[position(pair=UNICODE_TEXT, state=UNICODE_TEXT)],
    ),
    scenario(
        "two_hundred_characters",
        positions=[position(pair=LONG_TEXT, state=LONG_TEXT)],
    ),
    scenario(
        "markup_inside_a_text_field",
        positions=[position(pair=MARKUP_TEXT, state=MARKUP_TEXT)],
    ),
    scenario(
        "an_apostrophe",
        positions=[position(pair=APOSTROPHE_TEXT, state=APOSTROPHE_TEXT)],
    ),
    scenario(
        "wrong_capitals",
        positions=[
            position(state="DRAWDOWN"),
            position(pair="SOL/BTC", state="Bullish_Exit"),
        ],
    ),
    scenario(
        "a_name_with_a_newline",
        positions=[position(pair=NEWLINE_TEXT, state=NEWLINE_TEXT)],
    ),
    scenario(
        "a_number_where_text_belongs",
        positions=[position(pair=1234567890123, state=42)],
    ),
    scenario(
        "text_where_a_number_belongs",
        positions=[position(alt_units="cheap")],
    ),
    scenario(
        "text_where_a_whole_number_belongs",
        positions=[position(tier="second")],
    ),
    scenario(
        "text_where_a_chunk_number_belongs",
        chunk_size_usd="lots",
    ),
    scenario(
        "none_where_a_number_belongs",
        positions=[position(current_usd_approx=None)],
    ),
    scenario(
        "infinity_where_a_number_belongs",
        positions=[
            position(
                alt_units=math.inf,
                entry_usd=-math.inf,
                current_usd_approx=math.inf,
                delta_pct_usd_approx=math.inf,
            )
        ],
    ),
    scenario(
        "infinity_where_a_whole_number_belongs",
        positions=[position(tier=math.inf)],
    ),
    scenario("no_config_on_the_bot", with_config=False),
    scenario("fire_declined", fire_row=0, fire_answer="no"),
    scenario("fire_dispatched", fire_row=0, fire_answer="yes"),
    scenario("fire_on_a_later_row", fire_row=2, fire_answer="yes"),
    scenario("fire_without_a_manager", manager=False, fire_row=0, fire_answer="yes"),
    scenario("fire_without_a_loop", with_loop=False, fire_row=0, fire_answer="yes"),
    scenario("fire_with_a_loop_of_none", loop=None, fire_row=0, fire_answer="yes"),
    scenario(
        "fire_schedule_failed",
        fire_row=0,
        fire_answer="yes",
        schedule_raises=RuntimeError("loop is closed"),
    ),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}


def answer_value(spec):
    """The button value the operator's answer stands for."""
    if spec["fire_answer"] == "yes":
        return YES_FROM_QT
    return NO_FROM_QT


def surface_answer_value(spec):
    """The same answer, as the surface names it."""
    if spec["fire_answer"] == "yes":
        return surface.YES_BUTTON_VALUE
    return surface.NO_BUTTON_VALUE


# ---------------------------------------------------------------------
# Driving the two sides
# ---------------------------------------------------------------------


def old_bot(spec):
    return Bot(
        base_currency=spec["base_currency"],
        chunk_size_usd=spec["chunk_size_usd"],
        chunk_free_base=spec["chunk_free_base"],
        chunk_size_base=spec["chunk_size_base"],
        extracted_total=spec["extracted_total"],
        pool_color_name=spec["pool_color"],
        positions=spec["positions"],
        pool_color_raises=spec["pool_color_raises"],
        positions_raise=spec["positions_raise"],
        fire_raises=spec["fire_raises"],
        with_config=spec["with_config"],
    )


def old_manager(spec):
    if not spec["manager"]:
        return None
    return Manager(spec["loop"], with_loop=spec["with_loop"])


def new_bot(spec):
    bot = surface.BotSource(
        base_currency=spec["base_currency"],
        chunk_size_usd=spec["chunk_size_usd"],
        chunk_free_base=spec["chunk_free_base"],
        chunk_size_base=spec["chunk_size_base"],
        extracted_total=spec["extracted_total"],
        pool_color_name=spec["pool_color"],
        positions=spec["positions"],
        pool_color_raises=spec["pool_color_raises"],
        positions_raise=spec["positions_raise"],
        fire_raises=spec["fire_raises"],
    )
    if not spec["with_config"]:
        del bot.config
    return bot


def new_manager(spec):
    if not spec["manager"]:
        return None
    manager = surface.ManagerSource(spec["loop"])
    if not spec["with_loop"]:
        delattr(manager, surface.ASYNC_LOOP_ATTRIBUTE)
    return manager


def drive_old(spec):
    """Build the Qt tab, click the Fire button asked for, and hand it back."""
    app()
    bot = old_bot(spec)
    host = host_class()(bot, old_manager(spec))
    with QtSeams(answer_value(spec), spec["schedule_raises"]):
        tab = host._create_positions_held_tab()
        if spec["fire_row"] is not None:
            table = host_table(tab)
            table.cellWidget(spec["fire_row"], surface.FIRE_COLUMN).click()
        boxes = list(RECORDED_BOXES)
        scheduled = len(SCHEDULED)
        argument_counts = list(RECORDED_ARGUMENT_COUNTS)
    return {
        "tab": tab,
        "host": host,
        "bot": bot,
        "boxes": boxes,
        "scheduled": scheduled,
        "argument_counts": argument_counts,
    }


def drive_new(spec):
    """Build the surface model and take the same two steps."""
    bot = new_bot(spec)
    sink = surface.ScheduleSink(spec["schedule_raises"])
    model = surface.PositionsHeldTabModel(bot, new_manager(spec), sink)
    model.build()
    if spec["fire_row"] is not None:
        pair = model.fire_pairs[spec["fire_row"]]
        model.fire_handler(pair)(surface_answer_value(spec))
    return {"model": model, "bot": bot, "sink": sink}


# ---------------------------------------------------------------------
# Reading the two sides
# ---------------------------------------------------------------------


def host_table(tab):
    """The positions table inside the built tab."""
    return tab.layout().itemAt(1).widget()


def layout_order(layout):
    """The class of each item the layout holds, in the order it was added."""
    order = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        order.append("stretch" if widget is None else type(widget).__name__)
    return order


def form_rows(form):
    """Every row of the summary form: its label, its value and its skin."""
    from PySide6.QtWidgets import QFormLayout

    rows = []
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.ItemRole.LabelRole).widget()
        field = form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
        rows.append([label.text(), field.text(), field.styleSheet()])
    return rows


def qt_table_state(table):
    """Every value the Qt positions table can be asked for."""
    from PySide6.QtCore import Qt

    rows = []
    colors = []
    for row in range(table.rowCount()):
        texts = []
        painted = []
        for col in range(surface.CELL_COLUMN_COUNT):
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
        "vertical_header_visible": not table.verticalHeader().isHidden(),
        "edit_triggers": table.editTriggers().name,
        "selection_behavior": table.selectionBehavior().name,
        "alternating_row_colors": table.alternatingRowColors(),
        "cell_alignment_value": (
            table.item(0, 0).textAlignment()
            if table.rowCount()
            else surface.CELL_ALIGNMENT_VALUE
        ),
        "row_count": table.rowCount(),
        "rows": rows,
        "row_colors": colors,
    }


EMPTY_TABLE_STATE = {
    "columns": list(surface.COLUMNS),
    "column_count": surface.COLUMN_COUNT,
    "header_resize_mode": surface.HEADER_RESIZE_MODE,
    "vertical_header_visible": surface.VERTICAL_HEADER_VISIBLE,
    "edit_triggers": surface.EDIT_TRIGGERS,
    "selection_behavior": surface.SELECTION_BEHAVIOR,
    "alternating_row_colors": surface.ALTERNATING_ROW_COLORS,
    "cell_alignment_value": surface.CELL_ALIGNMENT_VALUE,
    "row_count": 0,
    "rows": [],
    "row_colors": [],
}


def qt_trace(driven):
    """Every value the built Qt tab can be asked for, as plain data."""
    tab = driven["tab"]
    outer = tab.layout()
    group = outer.itemAt(0).widget()
    form = group.layout()
    order = layout_order(outer)
    table_shown = order[1] == "QTableWidget"
    if table_shown:
        table = outer.itemAt(1).widget()
        table_state = qt_table_state(table)
        buttons = [
            table.cellWidget(row, surface.FIRE_COLUMN)
            for row in range(table.rowCount())
        ]
        fire_button = {
            "text": buttons[0].text(),
            "fixed_height_px": buttons[0].height(),
            "style_sheet": buttons[0].styleSheet(),
            "count": len(buttons),
        }
        footer = outer.itemAt(2).widget()
        footer_state = {
            "text": footer.text(),
            "style_sheet": footer.styleSheet(),
            "word_wrap": footer.wordWrap(),
            "shown": True,
        }
        empty_state = {"shown": False}
    else:
        table_state = dict(EMPTY_TABLE_STATE)
        fire_button = {
            "text": surface.FIRE_BUTTON_TEXT,
            "fixed_height_px": surface.FIRE_BUTTON_HEIGHT_PX,
            "style_sheet": surface.FIRE_BUTTON_STYLE,
            "count": 0,
        }
        empty = outer.itemAt(1).widget()
        empty_state = {
            "text": empty.text(),
            "style_sheet": empty.styleSheet(),
            "word_wrap": empty.wordWrap(),
            "shown": True,
        }
        footer_state = {"shown": False}
    return {
        "accessible_name": tab.accessibleName(),
        "container": {"spacing_px": outer.spacing()},
        "order": order,
        "summary_group": {"title": group.title()},
        "summary_form": {"configured": len(driven["host"].forms) == 1},
        "summary_rows": form_rows(form),
        "positions_table": table_state,
        "fire_button": fire_button,
        "empty_label": empty_state,
        "footer_label": footer_state,
        "boxes": driven["boxes"],
        "scheduled": driven["scheduled"],
        "fired": list(driven["bot"].fired),
        "table_stretch": outer.stretch(1) if table_shown else 0,
    }


def surface_trace(driven):
    """The same values, read from the Qt-free view model."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    table = payload["positions_table"]
    order = ["QGroupBox"]
    if table["shown"]:
        order.extend(["QTableWidget", "QLabel"])
    else:
        order.extend(["QLabel", "stretch"])
    rows = [[row[0], row[1], ""] for row in payload["summary_rows"]]
    if rows:
        rows[0][2] = payload["pool_label"]["style_sheet"]
    fire_button = {
        "text": payload["fire_button"]["text"],
        "fixed_height_px": payload["fire_button"]["fixed_height_px"],
        "style_sheet": payload["fire_button"]["style_sheet"],
        "count": len(payload["fire_button"]["pairs"]),
    }
    empty = payload["empty_label"]
    footer = payload["footer_label"]
    return {
        "accessible_name": payload["accessible_name"],
        "container": {"spacing_px": payload["container"]["spacing_px"]},
        "order": order,
        "summary_group": dict(payload["summary_group"]),
        "summary_form": {"configured": payload["summary_form"]["configured"]},
        "summary_rows": rows,
        "positions_table": {
            key: table[key]
            for key in (
                "columns",
                "column_count",
                "header_resize_mode",
                "vertical_header_visible",
                "edit_triggers",
                "selection_behavior",
                "alternating_row_colors",
                "cell_alignment_value",
                "row_count",
                "rows",
                "row_colors",
            )
        },
        "fire_button": fire_button,
        "empty_label": (
            {
                "text": empty["text"],
                "style_sheet": empty["style_sheet"],
                "word_wrap": empty["word_wrap"],
                "shown": True,
            }
            if empty["shown"]
            else {"shown": False}
        ),
        "footer_label": (
            {
                "text": footer["text"],
                "style_sheet": footer["style_sheet"],
                "word_wrap": footer["word_wrap"],
                "shown": True,
            }
            if footer["shown"]
            else {"shown": False}
        ),
        "boxes": payload["boxes"],
        "scheduled": len(driven["sink"].scheduled),
        "fired": list(driven["bot"].fired),
        "table_stretch": table["stretch"] if table["shown"] else 0,
    }


STANDIN_NAMES = {"BotSource": "Bot", "ManagerSource": "Manager"}


def plain_message(text: str) -> str:
    """One error message with the surface's stand-in class names folded out."""
    for standin, owned in STANDIN_NAMES.items():
        text = text.replace(standin, owned)
    return text


def outcome(work):
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": plain_message(str(exc)),
        }


def old_outcome(spec):
    return outcome(lambda: qt_trace(drive_old(spec)))


def new_outcome(spec):
    return outcome(lambda: surface_trace(drive_new(spec)))


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_tab(name):
    """A control, colour, column, number, box or branch differs between them."""
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


REFUSING_SCENARIOS = (
    "text_where_a_number_belongs",
    "text_where_a_whole_number_belongs",
    "text_where_a_chunk_number_belongs",
    "none_where_a_number_belongs",
    "infinity_where_a_whole_number_belongs",
    "no_config_on_the_bot",
    "pool_color_is_a_number",
)


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
    assert len(answered) == len(SCENARIOS) - len(REFUSING_SCENARIOS)


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """One side refused an input the other accepted, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in (
        "ValueError",
        "TypeError",
        "OverflowError",
        "AttributeError",
    )


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    happy = old_outcome(BY_NAME["happy"])["value"]
    grown = old_outcome(scenario("grown", positions=POSITIONS_GROWN))["value"]
    assert happy != grown
    assert digest(happy) != digest(grown)
    assert digest(happy) == digest(old_outcome(BY_NAME["happy"])["value"])
    assert len(digest(happy)) == 64


@pytest.mark.parametrize(
    "name", ["happy", "empty_positions", "bare_position", "fire_dispatched"]
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 14, sorted(value)
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# ---------------------------------------------------------------------
# The Fire button, driven down all four of its paths
# ---------------------------------------------------------------------


FIRE_SCENARIOS = (
    ("fire_declined", surface.OUTCOME_DECLINED, 1, 0),
    ("fire_dispatched", surface.OUTCOME_DISPATCHED, 2, 1),
    ("fire_on_a_later_row", surface.OUTCOME_DISPATCHED, 2, 1),
    ("fire_without_a_manager", surface.OUTCOME_NO_LOOP, 2, 0),
    ("fire_without_a_loop", surface.OUTCOME_NO_LOOP, 2, 0),
    ("fire_with_a_loop_of_none", surface.OUTCOME_NO_LOOP, 2, 0),
    ("fire_schedule_failed", surface.OUTCOME_SCHEDULE_FAILED, 2, 0),
)


@pytest.mark.parametrize("name,outcome_name,box_total,scheduled", FIRE_SCENARIOS)
def test_the_fire_button_takes_the_same_path_on_both_sides(
    name, outcome_name, box_total, scheduled
):
    """A Fire click ended somewhere else on one of the two sides."""
    spec = BY_NAME[name]
    old = qt_trace(drive_old(spec))
    driven = drive_new(spec)
    new = surface_trace(driven)
    assert old["boxes"] == new["boxes"], name
    assert len(old["boxes"]) == box_total, old["boxes"]
    assert old["scheduled"] == new["scheduled"] == scheduled
    assert driven["model"].outcome == outcome_name
    assert old["fired"] == new["fired"]


def test_every_fire_path_is_in_the_measured_set():
    """A path the Fire button can take was never driven."""
    taken = set()
    for name, _outcome, _boxes, _scheduled in FIRE_SCENARIOS:
        taken.add(drive_new(BY_NAME[name])["model"].outcome)
    assert taken == set(
        [
            surface.OUTCOME_DECLINED,
            surface.OUTCOME_NO_LOOP,
            surface.OUTCOME_SCHEDULE_FAILED,
            surface.OUTCOME_DISPATCHED,
        ]
    ), sorted(taken)
    assert drive_new(BY_NAME["happy"])["model"].outcome is surface.NO_OUTCOME


def test_a_declined_fire_closes_no_position():
    """Answering No closed the position anyway."""
    declined = drive_old(BY_NAME["fire_declined"])
    dispatched = drive_old(BY_NAME["fire_dispatched"])
    assert declined["bot"].fired == []
    assert declined["scheduled"] == 0
    assert dispatched["bot"].fired == [POSITIONS_HAPPY[0]["pair"]]
    assert dispatched["scheduled"] == 1
    quiet = drive_new(BY_NAME["fire_declined"])
    loud = drive_new(BY_NAME["fire_dispatched"])
    assert quiet["bot"].fired == []
    assert loud["bot"].fired == [POSITIONS_HAPPY[0]["pair"]]


def test_each_row_fires_only_its_own_position():
    """One row's button closed another row's position."""
    spec = BY_NAME["fire_on_a_later_row"]
    old = drive_old(spec)
    new = drive_new(spec)
    third = POSITIONS_HAPPY[2]["pair"]
    assert old["bot"].fired == [third]
    assert new["bot"].fired == [third]
    assert third != POSITIONS_HAPPY[0]["pair"]
    assert surface.confirm_text(third) in old["boxes"][0]["text"]
    assert old["boxes"][0]["text"] == surface.confirm_box(third)["text"]


BOT_REFUSAL = "position already closed"


def test_a_bot_that_refuses_the_close_is_swallowed_by_the_qt_event_loop():
    """A refusal from the bot reached nobody, or reached the operator.

    The shipped tab asks the bot for the close outside its own try, so a
    bot that refuses raises inside the click handler. Qt catches it
    there and no box is shown. The surface hands the same error back to
    its caller.
    """
    from pytestqt.exceptions import capture_exceptions

    app()
    spec = scenario(
        "bot_refuses",
        fire_row=0,
        fire_answer="yes",
        fire_raises=ValueError(BOT_REFUSAL),
    )
    with capture_exceptions() as caught:
        old = drive_old(spec)
    assert [kind.__name__ for kind, _value, _trace in caught] == ["ValueError"], caught
    assert [str(value) for _kind, value, _trace in caught] == [BOT_REFUSAL]
    assert old["boxes"] == [surface.confirm_box(POSITIONS_HAPPY[0]["pair"])]
    assert old["scheduled"] == 0
    with pytest.raises(ValueError) as reported:
        drive_new(spec)
    assert str(reported.value) == BOT_REFUSAL
    with capture_exceptions() as quiet:
        drive_old(BY_NAME["fire_dispatched"])
    assert quiet == [], quiet


def test_the_warning_and_information_boxes_use_the_default_button_set():
    """The shipped boxes ask for buttons the surface does not declare."""
    old = drive_old(BY_NAME["fire_without_a_manager"])
    assert old["argument_counts"] == [5, 3], old["argument_counts"]
    assert surface.OK_BUTTON_VALUE == OK_FROM_QT
    assert surface.NO_DEFAULT_BUTTON_VALUE == 0
    assert old["boxes"][1]["buttons_value"] == surface.OK_BUTTON_VALUE


def test_the_confirm_box_defaults_to_no():
    """The confirm box would close a position on a stray Return press."""
    old = drive_old(BY_NAME["fire_declined"])
    confirm = old["boxes"][0]
    assert confirm["buttons_value"] == surface.CONFIRM_BUTTONS_VALUE
    assert confirm["default_button_value"] == surface.CONFIRM_DEFAULT_BUTTON_VALUE
    assert surface.CONFIRM_DEFAULT_BUTTON_VALUE == surface.NO_BUTTON_VALUE
    assert surface.CONFIRM_BUTTONS_VALUE != surface.YES_BUTTON_VALUE


def test_the_declared_button_values_are_the_real_ones():
    """The surface names a button value Qt does not use."""
    assert surface.YES_BUTTON_VALUE == QtMessageBox.StandardButton.Yes.value
    assert surface.NO_BUTTON_VALUE == QtMessageBox.StandardButton.No.value
    assert surface.OK_BUTTON_VALUE == QtMessageBox.StandardButton.Ok.value
    assert (
        surface.CONFIRM_BUTTONS_VALUE
        == (QtMessageBox.StandardButton.Yes | QtMessageBox.StandardButton.No).value
    )


def test_the_two_qt_seams_are_put_back_after_a_run():
    """A swapped Qt name was left in place for every later test."""
    import PySide6.QtWidgets as widgets

    before_box = widgets.QMessageBox
    before_schedule = asyncio.run_coroutine_threadsafe
    drive_old(BY_NAME["fire_dispatched"])
    assert widgets.QMessageBox is before_box
    assert asyncio.run_coroutine_threadsafe is before_schedule
    assert widgets.QMessageBox is not BoxRecorder


# ---------------------------------------------------------------------
# The enumeration: signals, classes, methods, functions, timers, topics
# ---------------------------------------------------------------------


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
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                )
            )
    return sorted(found)


QT_SIGNAL_NAMES = {"fire_btn.clicked": "fire_button.clicked"}
QT_TARGET_NAMES = {"_make_fire_handler": "fire_handler"}


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
    assert ("fire_btn.clicked", "_make_fire_handler") in sites
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert len(connect_sites(BUS_NEIGHBOUR)) > CONNECT_TOTAL


SHIPPED_FUNCTIONS = {
    "_create_positions_held_tab": "PositionsHeldTabModel.build",
    "_make_fire_handler": "PositionsHeldTabModel.fire_handler",
    "_on_fire": "PositionsHeldTabModel.fire",
}

SHIPPED_METHODS = {"_create_positions_held_tab": "PositionsHeldTabModel.build"}

SURFACE_CLASSES = {
    "PositionsHeldTabModel": "PositionsHeldTabMixin",
    "BotConfig": "the config PositionsHeldTabMixin reads its base currency from",
    "BotSource": "the Extractor bot PositionsHeldTabMixin reads",
    "ManagerSource": "the bot manager the fire path asks for its loop",
    "ScheduleSink": "asyncio.run_coroutine_threadsafe, which the fire path calls",
}

SURFACE_MODEL_METHODS = ("__init__", "build", "fire", "fire_handler")


def source_functions(path) -> list:
    """Every function the source declares, nested ones included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def shipped_methods() -> list:
    """Every method the shipped class declares, read off the class object."""
    from src.gui.live_settings.positions_held_tab import PositionsHeldTabMixin

    return sorted(
        name
        for name, value in vars(PositionsHeldTabMixin).items()
        if callable(value) and not name.startswith("__")
    )


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped tab gained or lost a class, a method or a function."""
    from src.gui.live_settings import positions_held_tab as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["PositionsHeldTabMixin"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    methods = shipped_methods()
    assert methods == sorted(SHIPPED_METHODS), methods
    assert len(methods) == SHIPPED_METHOD_TOTAL
    functions = source_functions(TAB_SOURCE)
    assert functions == sorted(SHIPPED_FUNCTIONS), functions
    assert len(functions) == SHIPPED_FUNCTION_TOTAL
    for counterpart in SHIPPED_FUNCTIONS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_a_signal_is_not_counted_as_a_method():
    """A signal is callable, so a loose counter reads it as a method.

    The shipped class declares one method and three annotations. The
    annotations create no attribute, and nothing on the class is a
    signal, so the method count is one and stays one.
    """
    from src.gui.live_settings.positions_held_tab import PositionsHeldTabMixin

    names = vars(PositionsHeldTabMixin)
    assert "_bot" not in names
    assert "_bm" not in names
    assert "_configure_form" not in names
    assert PositionsHeldTabMixin.__annotations__ == {
        "_bm": "Any",
        "_bot": "Any",
        "_configure_form": "Callable[..., Any]",
    }
    assert shipped_methods() == ["_create_positions_held_tab"]


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["PositionsHeldTabModel"] == "PositionsHeldTabMixin"
    model_methods = sorted(
        name
        for name, value in vars(surface.PositionsHeldTabModel).items()
        if callable(value) and (not name.startswith("__") or name == "__init__")
    )
    assert model_methods == sorted(SURFACE_MODEL_METHODS), model_methods


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "_on_fire" in SHIPPED_FUNCTIONS
    assert "InventedModel" not in SURFACE_CLASSES
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        getattr(surface.PositionsHeldTabModel, "invented_method")


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


def test_the_tab_holds_no_timer_and_the_counter_can_report():
    """The tab runs a timer the surface declares no delay for.

    The shipped tab holds none, so the counter is pointed at a
    neighbouring screen that really does run one. A counter that
    returned nothing on both would be no measurement.
    """
    assert timer_sites(TAB_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1, "the timer counter reports nothing"


def test_the_tab_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The tab listens on a topic the surface names none of.

    The shipped tab listens on none, so the counter is pointed at a
    neighbouring screen that really does subscribe.
    """
    assert bus_sites(TAB_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------


PAYLOAD_KEYS = {
    "ACCESSIBLE_NAME": "accessible_name",
    "ACTIONS": "actions",
    "ALTERNATING_ROW_COLORS": "positions_table.alternating_row_colors",
    "ALT_UNITS_FORMAT": "formats.alt_units",
    "ALT_UNITS_KEY": "keys.alt_units",
    "ASYNC_LOOP_ATTRIBUTE": "attributes.async_loop",
    "BULLISH_EXIT_COLOR": "colors.bullish_exit",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CELL_ALIGNMENT": "positions_table.cell_alignment",
    "CELL_ALIGNMENT_VALUE": "positions_table.cell_alignment_value",
    "CELL_COLUMN_COUNT": "positions_table.cell_column_count",
    "CHUNK_FREE_BASE_ATTRIBUTE": "attributes.chunk_free_base",
    "CHUNK_FREE_ROW_FORMAT": "formats.chunk_free_row",
    "CHUNK_FREE_VALUE_FORMAT": "formats.chunk_free_value",
    "CHUNK_SIZE_BASE_ATTRIBUTE": "attributes.chunk_size_base",
    "CHUNK_SIZE_ROW_FORMAT": "formats.chunk_size_row",
    "CHUNK_SIZE_USD_ATTRIBUTE": "attributes.chunk_size_usd",
    "CHUNK_SIZE_VALUE_FORMAT": "formats.chunk_size_value",
    "COLUMNS": "positions_table.columns",
    "COLUMN_COUNT": "positions_table.column_count",
    "CONFIRM_BUTTONS_VALUE": "button_values.confirm_buttons",
    "CONFIRM_DEFAULT_BUTTON_VALUE": "button_values.confirm_default",
    "CONFIRM_TEXT_FORMAT": "formats.confirm_text",
    "CONFIRM_TITLE": "titles.confirm",
    "CONTENT_MARGINS_SET": "container.margins_set",
    "CONTENT_SPACING_PX": "container.spacing_px",
    "CORRECTIONS_FORMAT": "formats.corrections",
    "CORRECTIONS_KEY": "keys.corrections",
    "CURRENT_FORMAT": "formats.current",
    "CURRENT_KEY": "keys.current",
    "DEFAULT_ALT_UNITS": "defaults.alt_units",
    "DEFAULT_CHUNK_BASE": "defaults.chunk_base",
    "DEFAULT_CHUNK_USD": "defaults.chunk_usd",
    "DEFAULT_CORRECTIONS": "defaults.corrections",
    "DEFAULT_CURRENT_USD": "defaults.current_usd",
    "DEFAULT_DELTA_PCT": "defaults.delta_pct",
    "DEFAULT_ENTRY_USD": "defaults.entry_usd",
    "DEFAULT_PAIR": "defaults.pair",
    "DEFAULT_STATE": "defaults.state",
    "DEFAULT_TIER": "defaults.tier",
    "DELTA_COLUMN": "positions_table.delta_column",
    "DELTA_DOWN_COLOR": "colors.delta_down",
    "DELTA_FORMAT": "formats.delta",
    "DELTA_KEY": "keys.delta",
    "DELTA_UP_COLOR": "colors.delta_up",
    "DISPATCHED_TEXT_FORMAT": "formats.dispatched_text",
    "DISPATCHED_TITLE": "titles.dispatched",
    "DRAWDOWN_COLOR": "colors.drawdown",
    "EDIT_TRIGGERS": "positions_table.edit_triggers",
    "EMPTY_STYLE": "empty_label.style_sheet",
    "EMPTY_TEXT": "empty_label.text",
    "EMPTY_WORD_WRAP": "empty_label.word_wrap",
    "ENTRY_FORMAT": "formats.entry",
    "ENTRY_KEY": "keys.entry",
    "EXTRACTED_ROW_FORMAT": "formats.extracted_row",
    "EXTRACTED_TOTAL_ATTRIBUTE": "attributes.extracted_total",
    "EXTRACTED_VALUE_FORMAT": "formats.extracted_value",
    "FIRE_BUTTON_HEIGHT_PX": "fire_button.fixed_height_px",
    "FIRE_BUTTON_STYLE": "fire_button.style_sheet",
    "FIRE_BUTTON_TEXT": "fire_button.text",
    "FIRE_COLUMN": "positions_table.fire_column",
    "FOOTER_STYLE": "footer_label.style_sheet",
    "FOOTER_TEXT": "footer_label.text",
    "FOOTER_WORD_WRAP": "footer_label.word_wrap",
    "HEADER_RESIZE_MODE": "positions_table.header_resize_mode",
    "INFORMATION_ICON": "icons.information",
    "NO_BUTTON_VALUE": "button_values.no",
    "NO_CELL_COLOR": "no_cell_color",
    "NO_DEFAULT_BUTTON_VALUE": "button_values.no_default",
    "NO_LOOP_TEXT": "texts.no_loop",
    "NO_LOOP_TITLE": "titles.no_loop",
    "NO_OUTCOME": "no_outcome",
    "OK_BUTTON_VALUE": "button_values.ok",
    "OPEN_STATE_COLOR": "colors.open_state",
    "PAIR_FORMAT": "formats.pair",
    "PAIR_KEY": "keys.pair",
    "POOL_COLOR_HEX": "pool_color_map",
    "POOL_FALLBACK": "pool_fallback",
    "POOL_ROW_LABEL": "labels.pool_row",
    "POOL_STYLE_FORMAT": "formats.pool_style",
    "POOL_TEXT_FORMAT": "formats.pool_text",
    "POOL_UNKNOWN_HEX": "pool_unknown_hex",
    "QUESTION_ICON": "icons.question",
    "SCHEDULE_FAILED_TEXT_FORMAT": "formats.schedule_failed_text",
    "SCHEDULE_FAILED_TITLE": "titles.schedule_failed",
    "SELECTION_BEHAVIOR": "positions_table.selection_behavior",
    "STATE_COLUMN": "positions_table.state_column",
    "STATE_KEY": "keys.state",
    "SUMMARY_FORM_CONFIGURED_BY_HOST": "summary_form.configured_by_host",
    "SUMMARY_GROUP_TITLE": "summary_group.title",
    "TABLE_STRETCH": "positions_table.stretch",
    "TIER_FORMAT": "formats.tier",
    "TIER_KEY": "keys.tier",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "VERTICAL_HEADER_VISIBLE": "positions_table.vertical_header_visible",
    "WARNING_ICON": "icons.warning",
    "YES_BUTTON_VALUE": "button_values.yes",
}

# The values carried as one member of a list the payload holds.
LIST_MEMBERS = {
    "POOL_GREEN": "pool_names",
    "POOL_YELLOW": "pool_names",
    "POOL_RED": "pool_names",
    "STATE_DRAWDOWN": "state_names",
    "STATE_BULLISH_EXIT": "state_names",
    "OUTCOME_DECLINED": "outcomes",
    "OUTCOME_NO_LOOP": "outcomes",
    "OUTCOME_SCHEDULE_FAILED": "outcomes",
    "OUTCOME_DISPATCHED": "outcomes",
}

# The twenty-one branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "BUILD_START",
    "BUILD_FORM",
    "BUILD_POOL_COLOR",
    "BUILD_POOL_FAILED",
    "BUILD_SUMMARY_ROW",
    "BUILD_POSITIONS",
    "BUILD_POSITIONS_FAILED",
    "BUILD_EMPTY",
    "BUILD_TABLE",
    "BUILD_ROW",
    "BUILD_FIRE_CONNECTED",
    "BUILD_FOOTER",
    "BUILD_RETURN",
    "FIRE_START",
    "FIRE_CONFIRM",
    "FIRE_DECLINED",
    "FIRE_NO_LOOP",
    "FIRE_CORO",
    "FIRE_SCHEDULED",
    "FIRE_SCHEDULE_FAILED",
    "FIRE_DISPATCHED",
)

# The two values no snapshot key carries, each with the check that
# covers it. METHOD is the name the bridge registers under and
# PANE_MODEL is the tab state the bridge keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_positions_held_method",
    "PANE_MODEL": "test_the_bridge_resets_the_tab_state_on_request",
}

STATE_ONLY_KEYS = {
    "boxes",
    "calls",
    "fire_outcome",
    "pool_color",
    "pool_color_hex",
    "pool_label",
    "summary_rows",
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
    member of a list the snapshot holds, one of the branch markers, or
    one of the two named with the check that covers it.
    """
    payload = surface.build_view_model(surface.PositionsHeldTabModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == list(value), name
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
    assert len(PAYLOAD_KEYS) == 99
    assert len(LIST_MEMBERS) == 9
    assert len(CALL_CONSTANTS) == 21
    assert len(NOT_IN_THE_SNAPSHOT) == 2


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.PositionsHeldTabModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= set(LIST_MEMBERS.values())
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
    payload = surface.build_view_model(surface.PositionsHeldTabModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "COLUMNS" in surface_constants()
    assert "FOOTER_TEXT" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "PositionsHeldTabModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(call[0] for call in drive_new(spec)["model"].calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    empty = drive_new(BY_NAME["empty_positions"])["model"]
    assert [call[0] for call in empty.calls].count(surface.BUILD_EMPTY) == 1
    assert empty.footer_shown is False
    assert empty.table_shown is False
    filled = drive_new(BY_NAME["happy"])["model"]
    assert [call[0] for call in filled.calls].count(surface.BUILD_EMPTY) == 0
    assert filled.footer_shown is True
    assert filled.table_shown is True


# ---------------------------------------------------------------------
# The surface carries its own values
# ---------------------------------------------------------------------


class MovedTokens:
    """A token table whose colours are unlike any the design system holds."""

    SUCCESS = "#111111"
    WARNING = "#222222"
    ERROR = "#333333"
    TEXT_MED = "#444444"
    TEXT_EMPTY_STATE = "#555555"
    WARNING_STRONG = "#666666"
    SETTINGS_WARNING_HOVER = "#777777"


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_tab(monkeypatch):
    """The surface read its values off the tab it replaces.

    A surface that read the shipped tab would follow it, and the whole
    comparison above would be one side read twice. The shipped tab's
    tokens are moved and the surface must not move with them.
    """
    app()
    from src.gui.live_settings import positions_held_tab as shipped

    first = shipped.ds
    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec))
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved = qt_trace(drive_old(spec))
    assert MovedTokens.WARNING in moved["summary_rows"][0][2]
    assert MovedTokens.WARNING_STRONG in moved["fire_button"]["style_sheet"]
    assert MovedTokens.WARNING not in before["summary_rows"][0][2]
    new = surface_trace(drive_new(spec))
    assert MovedTokens.WARNING not in new["summary_rows"][0][2]
    assert MovedTokens.WARNING_STRONG not in new["fire_button"]["style_sheet"]
    assert new["summary_rows"] == before["summary_rows"]
    assert new["fire_button"] == before["fire_button"]
    monkeypatch.undo()
    assert shipped.ds is first
    assert qt_trace(drive_old(spec))["fire_button"] == before["fire_button"]


def test_the_surface_does_not_follow_a_tab_that_builds_nothing(monkeypatch):
    """The surface asked the shipped tab to build its controls."""
    app()
    from src.gui.live_settings import positions_held_tab as shipped

    first = shipped.PositionsHeldTabMixin._create_positions_held_tab
    payload = surface.build_view_model(surface.PositionsHeldTabModel())
    monkeypatch.setattr(
        shipped.PositionsHeldTabMixin,
        "_create_positions_held_tab",
        lambda self: None,
    )
    host = host_class()(old_bot(BY_NAME["happy"]), None)
    assert host._create_positions_held_tab() is None
    again = surface.build_view_model(surface.PositionsHeldTabModel())
    assert again == payload
    assert again["positions_table"]["columns"] == list(surface.COLUMNS)
    assert again["footer_label"]["text"] == surface.FOOTER_TEXT
    monkeypatch.undo()
    assert shipped.PositionsHeldTabMixin._create_positions_held_tab is first
    assert host_class()(old_bot(BY_NAME["happy"]), None)._create_positions_held_tab()


def test_the_shipped_tab_writes_to_no_shared_table():
    """The shipped tab changed something every later test would inherit.

    The tab reads the design tokens and builds widgets. It writes no
    module value, so two builds from one bot leave the token table and
    the tab module exactly as they were.
    """
    app()
    from src.gui import design_system
    from src.gui.live_settings import positions_held_tab as shipped

    before_tokens = {
        name: getattr(design_system, name)
        for name in ("SUCCESS", "WARNING", "ERROR", "TEXT_MED", "TEXT_EMPTY_STATE")
    }
    before_module = sorted(vars(shipped))
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["fire_dispatched"])
    after_tokens = {name: getattr(design_system, name) for name in before_tokens}
    assert after_tokens == before_tokens
    assert sorted(vars(shipped)) == before_module
    assert shipped.ds is design_system


# ---------------------------------------------------------------------
# The colours
# ---------------------------------------------------------------------


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


def test_the_state_colours_are_the_ones_qt_paints():
    """The surface names a state colour Qt does not paint."""
    app()
    from PySide6.QtCore import Qt

    assert canonical(Qt.red) == surface.DRAWDOWN_COLOR
    assert canonical(Qt.yellow) == surface.BULLISH_EXIT_COLOR
    assert canonical(Qt.green) == surface.OPEN_STATE_COLOR
    assert surface.DELTA_UP_COLOR == surface.OPEN_STATE_COLOR
    assert surface.DELTA_DOWN_COLOR == surface.DRAWDOWN_COLOR


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    app()
    written = {
        name: canonical(value)
        for name, value in (
            ("drawdown", surface.DRAWDOWN_COLOR),
            ("bullish_exit", surface.BULLISH_EXIT_COLOR),
            ("open_state", surface.OPEN_STATE_COLOR),
            ("pool_green", surface.POOL_COLOR_HEX[surface.POOL_GREEN]),
            ("pool_yellow", surface.POOL_COLOR_HEX[surface.POOL_YELLOW]),
            ("pool_red", surface.POOL_COLOR_HEX[surface.POOL_RED]),
            ("pool_unknown", surface.POOL_UNKNOWN_HEX),
        )
    }
    assert len(set(written.values())) == len(written), written
    assert all(len(value) == 7 for value in written.values()), written


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    app()
    assert canonical(surface.DRAWDOWN_COLOR) != canonical("#00ff00")
    assert canonical(surface.POOL_COLOR_HEX[surface.POOL_GREEN]) == "#00ff88"
    assert canonical("#008800") != canonical(surface.POOL_COLOR_HEX[surface.POOL_GREEN])
    assert canonical(surface.POOL_COLOR_HEX[surface.POOL_YELLOW]) != canonical(
        "#00aaff"
    )


def test_no_declared_colour_has_three_equal_channels():
    """A colour with equal channels reads the same with any two swapped.

    Such a colour cannot report a channel swap, so it would need an
    exact-text check instead. None of the tab's colours is one.
    """
    app()
    equal_channelled = []
    for name, value in (
        ("drawdown", surface.DRAWDOWN_COLOR),
        ("bullish_exit", surface.BULLISH_EXIT_COLOR),
        ("open_state", surface.OPEN_STATE_COLOR),
        ("pool_green", surface.POOL_COLOR_HEX[surface.POOL_GREEN]),
        ("pool_yellow", surface.POOL_COLOR_HEX[surface.POOL_YELLOW]),
        ("pool_red", surface.POOL_COLOR_HEX[surface.POOL_RED]),
        ("pool_unknown", surface.POOL_UNKNOWN_HEX),
    ):
        written = canonical(value)
        if written[1:3] == written[3:5] == written[5:7]:
            equal_channelled.append(name)
    assert equal_channelled == [], equal_channelled
    assert canonical("#888")[1:3] == canonical("#888")[5:7]


@pytest.mark.parametrize(
    "state,expected",
    [
        ("drawdown", surface.DRAWDOWN_COLOR),
        ("bullish_exit", surface.BULLISH_EXIT_COLOR),
        ("in_flight", surface.OPEN_STATE_COLOR),
        ("DRAWDOWN", surface.OPEN_STATE_COLOR),
        ("", surface.OPEN_STATE_COLOR),
    ],
)
def test_the_state_colour_follows_the_state_exactly(state, expected):
    """A state read in the wrong capitals took the drawdown colour."""
    assert surface.state_color(state) == expected


@pytest.mark.parametrize(
    "delta,expected",
    [
        (4.5, surface.DELTA_UP_COLOR),
        (-4.5, surface.DELTA_DOWN_COLOR),
        (0.0, surface.NO_CELL_COLOR),
        (-0.0, surface.NO_CELL_COLOR),
        (math.inf, surface.DELTA_UP_COLOR),
        (-math.inf, surface.DELTA_DOWN_COLOR),
    ],
)
def test_the_change_colour_follows_the_change_exactly(delta, expected):
    """A change of exactly nothing was painted as a gain or a loss."""
    assert surface.delta_color(delta) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("green", "#00ff88"),
        ("yellow", "#ffaa00"),
        ("red", "#ff3366"),
        ("teal", "#a8a8c5"),
        ("", "#a8a8c5"),
        ("GREEN", "#a8a8c5"),
    ],
)
def test_the_pool_colour_follows_the_pool_name_exactly(name, expected):
    """A pool name nobody set took a real pool colour."""
    assert surface.pool_color_hex(name) == expected


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


def model_payload(spec=None):
    """The view model after the same driving, stamped."""
    driven = drive_new(spec or BY_NAME["happy"])
    return sealed(surface.build_view_model(driven["model"]))


def widget_painted_by_the_tab(spec=None):
    """The tab the shipped Qt mixin builds, after the same driving."""
    return drive_old(spec or BY_NAME["happy"])["tab"]


def widget_painted_by_the_model(payload):
    """A tab built only from the payload, never from the shipped mixin.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QFormLayout,
        QGroupBox,
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    app()
    screen = QWidget()
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    outer.setSpacing(payload["container"]["spacing_px"])

    group = QGroupBox(payload["summary_group"]["title"])
    form = QFormLayout(group)
    for index, (label, value) in enumerate(payload["summary_rows"]):
        field = QLabel(value)
        if index == 0:
            field.setStyleSheet(payload["pool_label"]["style_sheet"])
        form.addRow(label, field)
    outer.addWidget(group)

    if payload["empty_label"]["shown"]:
        empty = QLabel(payload["empty_label"]["text"])
        empty.setWordWrap(payload["empty_label"]["word_wrap"])
        empty.setStyleSheet(payload["empty_label"]["style_sheet"])
        outer.addWidget(empty)
        outer.addStretch()
        return screen

    declared = payload["positions_table"]
    table = QTableWidget()
    table.setColumnCount(declared["column_count"])
    table.setHorizontalHeaderLabels(declared["columns"])
    table.setRowCount(declared["row_count"])
    table.horizontalHeader().setSectionResizeMode(
        getattr(QHeaderView.ResizeMode, declared["header_resize_mode"])
    )
    table.verticalHeader().setVisible(declared["vertical_header_visible"])
    table.setEditTriggers(
        getattr(QAbstractItemView.EditTrigger, declared["edit_triggers"])
    )
    table.setSelectionBehavior(
        getattr(QAbstractItemView.SelectionBehavior, declared["selection_behavior"])
    )
    table.setAlternatingRowColors(declared["alternating_row_colors"])
    for row, cells in enumerate(declared["rows"]):
        for col, text in enumerate(cells):
            cell = QTableWidgetItem(text)
            cell.setTextAlignment(Qt.AlignmentFlag(declared["cell_alignment_value"]))
            painted = declared["row_colors"][row][col]
            if painted is not None:
                cell.setForeground(QColor(painted))
            table.setItem(row, col, cell)
        button = QPushButton(payload["fire_button"]["text"])
        button.setFixedHeight(payload["fire_button"]["fixed_height_px"])
        button.setStyleSheet(payload["fire_button"]["style_sheet"])
        table.setCellWidget(row, declared["fire_column"], button)
    outer.addWidget(table, stretch=declared["stretch"])

    footer = QLabel(payload["footer_label"]["text"])
    footer.setWordWrap(payload["footer_label"]["word_wrap"])
    footer.setStyleSheet(payload["footer_label"]["style_sheet"])
    outer.addWidget(footer)
    return screen


PICTURE_SCENARIOS = [
    "happy",
    "empty_positions",
    "pool_color_failed",
    "unicode",
    "bare_position",
    "negative_everywhere",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different tab than the shipped mixin."""
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

    Two real position lists, one driven into each side. Every row
    carries a different pair, state and amount, so a pass proves the
    comparison reports a tab painted differently.
    """
    app()
    other = scenario("grown", positions=POSITIONS_GROWN)
    assert POSITIONS_HAPPY != POSITIONS_GROWN
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_tab(BY_NAME["happy"]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(other)), PIXEL_SIZE
        ),
        note="the happy positions against the grown positions",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_tab_shows_more_than_one_colour(name):
    """The two sides matched because the tab painted one flat colour."""
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
    payload["positions_table"]["rows"][0][0] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(
            surface.build_view_model(surface.PositionsHeldTabModel())
        )


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


@skip_unless_no_fonts
def test_two_equal_length_pairs_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length names still differ."""
    app()
    from PySide6.QtWidgets import QLabel

    assert (
        QLabel("IIII/BTC").sizeHint().width() == QLabel("WWWW/BTC").sizeHint().width()
    )


@skip_unless_real_fonts
def test_two_equal_length_pairs_measure_apart_with_fonts():
    """The glyphs decide their own width, and two names still measure alike."""
    app()
    from PySide6.QtWidgets import QLabel

    assert (
        QLabel("IIII/BTC").sizeHint().width() != QLabel("WWWW/BTC").sizeHint().width()
    )


# ---------------------------------------------------------------------
# What a picture cannot see, read off both sides instead
# ---------------------------------------------------------------------


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The accessible name, the edit and selection rules, the hidden
    vertical header, the table's stretch and the summary form's
    configure call paint nothing. Each is read off the shipped tab and
    off the surface directly.
    """
    app()
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert new["accessible_name"] == old["accessible_name"] == ""
    assert new["summary_form"] == old["summary_form"] == {"configured": True}
    assert new["table_stretch"] == old["table_stretch"] == surface.TABLE_STRETCH
    for key in ("edit_triggers", "selection_behavior", "vertical_header_visible"):
        assert new["positions_table"][key] == old["positions_table"][key], key
    assert old["positions_table"]["vertical_header_visible"] is False
    assert old["positions_table"]["edit_triggers"] == "NoEditTriggers"
    assert old["positions_table"]["selection_behavior"] == "SelectRows"


def test_the_cell_alignment_is_read_off_both_sides():
    """The cells are centred on one side and left alone on the other."""
    app()
    old = qt_trace(drive_old(BY_NAME["happy"]))
    new = surface_trace(drive_new(BY_NAME["happy"]))
    assert (
        new["positions_table"]["cell_alignment_value"]
        == old["positions_table"]["cell_alignment_value"]
    )
    assert old["positions_table"]["cell_alignment_value"] == 132


def test_the_message_box_texts_are_read_off_both_sides():
    """A box the operator reads was compared by picture, which never shows it."""
    app()
    for name in ("fire_declined", "fire_without_a_manager", "fire_schedule_failed"):
        old = drive_old(BY_NAME[name])
        new = drive_new(BY_NAME[name])
        assert old["boxes"] == new["model"].boxes, name
        assert old["boxes"], name
    dispatched = drive_old(BY_NAME["fire_dispatched"])
    assert dispatched["boxes"][1]["title"] == surface.DISPATCHED_TITLE
    assert dispatched["boxes"][1]["icon"] == surface.INFORMATION_ICON


def box_of(layout) -> list:
    """One layout's four margins, as plain numbers."""
    margins = layout.contentsMargins()
    return [margins.left(), margins.top(), margins.right(), margins.bottom()]


def untouched_layout_margins():
    """The margins and spacing a fresh column layout starts with.

    The holder widget is kept alive for the read: a layout whose owner
    is collected raises rather than reporting.
    """
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    plain = QVBoxLayout(holder)
    reading = (box_of(plain), plain.spacing())
    assert holder.layout() is plain
    return reading


def test_the_outer_layout_sets_no_margins_on_either_side():
    """The tab set its own margins on one side and not on the other."""
    app()
    untouched, untouched_spacing = untouched_layout_margins()
    tab = widget_painted_by_the_tab(BY_NAME["happy"])
    built = widget_painted_by_the_model(model_payload(BY_NAME["happy"]))
    for layout in (tab.layout(), built.layout()):
        assert box_of(layout) == untouched
        assert layout.spacing() == surface.CONTENT_SPACING_PX
    assert surface.CONTENT_MARGINS_SET is False
    assert untouched_spacing != surface.CONTENT_SPACING_PX


def test_the_fire_column_holds_a_button_and_no_cell():
    """The Fire column carries a text cell, which no button can be clicked in."""
    app()
    from PySide6.QtWidgets import QPushButton

    tab = widget_painted_by_the_tab(BY_NAME["happy"])
    table = host_table(tab)
    for row in range(table.rowCount()):
        assert table.item(row, surface.FIRE_COLUMN) is None
        assert isinstance(table.cellWidget(row, surface.FIRE_COLUMN), QPushButton)
    assert table.item(0, 0) is not None
    assert table.cellWidget(0, 0) is None


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


@pytest.fixture
def fresh_pane_model():
    """Put the tab state the bridge keeps back exactly as it was found."""
    first = surface.PANE_MODEL
    surface.PANE_MODEL = surface.PositionsHeldTabModel()
    yield
    surface.PANE_MODEL = first


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


BRIDGE_BOT = {
    "base_currency": "BTC",
    "chunk_size_usd": 250.75,
    "chunk_free_base": 0.00512345,
    "chunk_size_base": 0.00040001,
    "extracted_total": 0.00218,
    "pool_color": "yellow",
    "positions": POSITIONS_HAPPY,
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_positions_held_method():
    """The renderer cannot reach the Positions Held tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "positions_held_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["positions_table"]["columns"] == list(surface.COLUMNS)
    assert result["fire_button"]["text"] == surface.FIRE_BUTTON_TEXT


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_tab_state_on_request():
    """The tab state the bridge keeps was never cleared."""
    filled = bridge_answer({"reset": True, "bot": BRIDGE_BOT})["result"]
    assert filled["positions_table"]["row_count"] == 3
    assert filled["footer_label"]["shown"] is True
    assert filled["pool_color"] == "yellow"
    kept = bridge_answer({})["result"]
    assert kept["positions_table"]["row_count"] == 3
    assert kept["pool_color"] == "yellow"
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["positions_table"]["row_count"] == 0
    assert cleared["positions_table"]["shown"] is False
    assert cleared["pool_color"] == surface.POOL_FALLBACK
    assert cleared["calls"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_runs_the_fire_path():
    """A Fire click over the bridge reached no path at all."""
    answer = bridge_answer(
        {
            "reset": True,
            "bot": BRIDGE_BOT,
            "manager": {"async_loop": "a loop"},
            "fire_pair": POSITIONS_HAPPY[0]["pair"],
            "fire_answer": surface.YES_BUTTON_VALUE,
        }
    )
    assert answer["ok"] is True
    assert answer["result"]["fire_outcome"] == surface.OUTCOME_DISPATCHED
    declined = bridge_answer(
        {
            "reset": True,
            "bot": BRIDGE_BOT,
            "manager": {"async_loop": "a loop"},
            "fire_pair": POSITIONS_HAPPY[0]["pair"],
            "fire_answer": surface.NO_BUTTON_VALUE,
        }
    )
    assert declined["result"]["fire_outcome"] == surface.OUTCOME_DECLINED


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reset": True, "bot": BRIDGE_BOT})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["positions_table"]["row_count"] == 3
    assert encoded["result"]["summary_rows"][0][1] == "<b>YELLOW</b>"


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'positions_held_tab.state', 'params':"
    " {'reset': True, 'bot': {'base_currency': 'BTC', 'chunk_size_usd': 250.75,"
    " 'positions': [{'pair': 'ETH/BTC', 'state': 'drawdown', 'tier': 2,"
    " 'alt_units': 1.5, 'entry_usd': 100.0, 'current_usd_approx': 90.0,"
    " 'delta_pct_usd_approx': -10.0, 'corrections_fired': 1}]}}}),"
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
    """Reaching the Positions Held tab pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["positions_table"]["row_count"] == 1
    assert result["positions_table"]["rows"][0] == [
        "ETH/BTC",
        "DRAWDOWN",
        "2",
        "1.500000",
        "$100.0000",
        "$90.0000",
        "-10.00%",
        "1",
    ]
    assert result["summary_rows"][1][1] == "0.00000000 / $250.75"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
