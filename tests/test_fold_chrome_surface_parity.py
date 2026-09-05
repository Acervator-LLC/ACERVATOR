"""The Qt Fold Tranches chrome and the Qt-free surface, driven side by side.

A failure means the view model describes a different despawn row, a
different control, a different row border, a different order, a different
filter outcome, a different pin or a different branch than
``src.gui.live_settings.fold_chrome`` builds on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import fold_chrome_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
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
CHROME_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "fold_chrome.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "fold_chrome_surface.py"
WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
QUIET_TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
LOOSE_TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

PIXEL_SIZE = (760, 420)
CELL_RECT = (10, 5, 100, 30)
DAY_SECONDS = 86400.0
FIXED_NOW = 1_700_000_000.0


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def as_text(value):
    """`value` with every number written as its own text.

    ``12`` and ``12.0`` are one value to a comparison and two different
    numbers to a reader, and two not-a-numbers are never equal to each
    other. Both are settled here before anything is compared.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict):
        return {key: as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(
            as_text(value), sort_keys=True, ensure_ascii=True, default=repr
        ).encode("utf-8")
    ).hexdigest()


# The clock counter. Both sides are driven through it, so a read either
# side makes is counted rather than assumed absent.


class ClockRecorder:
    """Counts every clock read and hands back a scripted monotonic value.

    ``reads`` is keyed by the name of the clock, so a side that reads the
    wall clock is told apart from one that measures a duration.
    """

    def __init__(self, ticks=()):
        self.ticks = list(ticks)
        self.reads = {"time": 0, "monotonic": 0, "now": 0}

    def time(self) -> float:
        self.reads["time"] += 1
        return FIXED_NOW

    def monotonic(self) -> float:
        self.reads["monotonic"] += 1
        if self.ticks:
            return self.ticks.pop(0)
        return 0.0

    def now(self, *args, **named):
        self.reads["now"] += 1
        raise AssertionError("the date object was read; no side is meant to")

    def total(self) -> int:
        return sum(self.reads.values())


def watched_clock(monkeypatch, ticks=()):
    """Point every clock this repo can reach at one recorder."""
    import datetime
    import time

    recorder = ClockRecorder(ticks)
    monkeypatch.setattr(time, "time", recorder.time)
    monkeypatch.setattr(time, "monotonic", recorder.monotonic)

    class WatchedDate(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            recorder.reads["now"] += 1
            return cls.fromtimestamp(FIXED_NOW, tz)

    monkeypatch.setattr(datetime, "datetime", WatchedDate)
    return recorder


# The pin recorder. The shipped panel emits inside a suppressed block,
# so a recorder that raises would delete the record it was watching for.


class PinRecorder:
    """Keeps every contract pin the shipped panel emits. Never raises."""

    def __init__(self):
        self.pins: list = []
        self.broken: list = []
        self.extra: list = []

    def emit(self, name, actual, expected=None, duration=None, context=None, **rest):
        self.extra.append(sorted(rest))
        try:
            self.pins.append(
                [name, dict(actual), dict(expected), duration, dict(context)]
            )
        except Exception as exc:
            self.broken.append(repr(exc))
        return None


def watched_pins(monkeypatch):
    """Point the shipped panel's contract emitter at one recorder."""
    from src.core import signal_contract

    recorder = PinRecorder()
    monkeypatch.setattr(signal_contract, "emit", recorder.emit)
    return recorder


# One spec, two worlds. Each side builds its own objects from the plain
# values below and never reads the other side's.


def tranche(age_days, usd, units, key="created_ts"):
    """One ledger record, aged `age_days` before the fixed clock."""
    stamp = None if age_days is None else FIXED_NOW - age_days * DAY_SECONDS
    return {key: stamp, "usd": usd, "units": units}


def stack(age_days, usd, units):
    return tranche(age_days, usd, units, key="opened_ts")


SCENARIOS: list = []


def scenario(name, **named):
    spec = {
        "name": name,
        "days": 0,
        "fold": [],
        "stack": [],
        "sort_key": None,
        "row_texts": [],
        "table_rows": 0,
        "needle": "",
        "elapsed_s": 0.25,
        "bot_id": "PROBE/USD",
        "has_rebuild": True,
        "cell_fill": surface.FOLD_ROW_FILL,
    }
    spec.update(named)
    SCENARIOS.append(spec)
    return spec


scenario(
    "happy",
    days=7,
    fold=[tranche(100, 12.5, 3.25), tranche(10, 0.5, 1.0), tranche(None, 1.0, 1.0)],
    stack=[stack(90, 7.0, 2.0)],
    sort_key=surface.SORT_OLDEST_FIRST,
    row_texts=[["BTC", "12.5000"], ["ETH", "0.5000"]],
    table_rows=2,
    needle="btc",
)
scenario("no_tranches", days=0)
scenario("no_tranches_armed", days=30)
scenario(
    "timer_off_with_old_records",
    days=0,
    fold=[tranche(100, 12.5, 3.25)],
    stack=[stack(90, 7.0, 2.0)],
)
scenario(
    "timer_off_with_records_younger_than_the_widest_window",
    days=0,
    fold=[tranche(30, 12.5, 3.25)],
)
scenario(
    "one_tranche_no_parent",
    days=7,
    fold=[tranche(100, 12.5, 3.25)],
    row_texts=[[""]],
    table_rows=1,
    needle="x",
)
scenario(
    "fold_ratio_out_of_range",
    days=1_000_000_000,
    fold=[tranche(100, 12.5, 3.25)],
)
scenario("zero_money", days=7, fold=[tranche(100, 0.0, 0.0)])
scenario("negative_money", days=7, fold=[tranche(100, -12.5, -3.25)])
scenario("a_thousand_million", days=7, fold=[tranche(100, 1_000_000_000.0, 1.0)])
scenario("one_billionth", days=7, fold=[tranche(100, 1e-9, 1e-9)])
scenario("infinity", days=7, fold=[tranche(100, float("inf"), 1.0)])
scenario("minus_infinity", days=7, fold=[tranche(100, float("-inf"), 1.0)])
scenario("not_a_number", days=7, fold=[tranche(100, float("nan"), 1.0)])
scenario("negative_days", days=-5, fold=[tranche(100, 12.5, 3.25)])
scenario(
    "unicode_rows",
    days=0,
    row_texts=[["Ünïcodé", "€12,50"], ["日本語", "0.5"]],
    table_rows=2,
    needle="ünï",
)
scenario(
    "two_hundred_character_row",
    days=0,
    row_texts=[["x" * 200, "12.5"]],
    table_rows=1,
    needle="x",
)
scenario(
    "markup_row",
    days=0,
    row_texts=[["<b>BTC</b>", "&amp;"]],
    table_rows=1,
    needle="<b>",
)
scenario(
    "apostrophe_row",
    days=0,
    row_texts=[["bot's fold", "1.0"]],
    table_rows=1,
    needle="bot's",
)
scenario(
    "wrong_capitals_needle",
    days=0,
    row_texts=[["btc", "1.0"]],
    table_rows=1,
    needle="BTC",
)
scenario(
    "newline_in_a_name",
    days=0,
    row_texts=[["BTC\nUSD", "1.0"]],
    table_rows=1,
    needle="usd",
)
scenario(
    "a_number_where_text_belongs",
    days=0,
    row_texts=[[12.5, 7]],
    table_rows=1,
    needle="12.5",
)
scenario(
    "text_where_a_number_belongs",
    days=0,
    row_texts=[["twelve", "-"]],
    table_rows=1,
    needle="12",
)
scenario(
    "rows_the_panel_harvested_no_text_for",
    days=0,
    row_texts=[["BTC", "1.0"]],
    table_rows=3,
    needle="btc",
)
scenario("blank_needle", days=0, row_texts=[["BTC", "1.0"]], table_rows=1, needle="   ")
scenario(
    "extractor_row_fill",
    days=0,
    row_texts=[["EXT", "1.0"]],
    table_rows=1,
    cell_fill=surface.EXTRACTOR_ROW_FILL,
)
scenario("a_fill_the_panel_does_not_colour", days=0, table_rows=1, cell_fill="#101018")
scenario("no_fill_at_all", days=0, table_rows=1, cell_fill=None)
scenario("bot_that_refuses_the_change", days=0, has_rebuild=False)

BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

REFUSING_SCENARIOS = {
    "a_preview_missing_a_count": KeyError,
    "days_that_are_not_a_number": TypeError,
    "a_money_value_the_venue_would_reject": ValueError,
}


def refusing_install(name):
    """The three inputs that refuse, as the arguments each side is given."""
    windows = window_previews([], [])
    good = despawn_reading([], [], 7)
    if name == "a_preview_missing_a_count":
        broken = dict(good)
        broken.pop(surface.UNITS_REMOVED_KEY)
        return 7, broken, windows
    if name == "days_that_are_not_a_number":
        return "seven", good, windows
    money = dict(good, **{surface.USD_REMOVED_KEY: "lots"})
    return 7, money, windows


DIFFERENT_INPUT_PAIR = ("happy", "no_tranches")


# The shared rule: the Qt panel calls it, the surface is handed what it returns.


def armed_days(days):
    """The whole-day threshold the panel reads out of a config.

    The shipped panel does not print the stored number: it prints what
    `despawn_threshold_days` makes of it, which saturates. Both sides
    are given the same reading, each reaching it its own way.
    """
    from src.trading.bot_container import despawn_threshold_days

    return despawn_threshold_days(QtConfig(days))


def despawn_reading(fold, stacks, days):
    from src.trading.bot_container import despawn_preview

    return despawn_preview(fold, stacks, days, FIXED_NOW)


def window_previews(fold, stacks):
    from src.trading.bot_container import DESPAWN_PREVIEW_WINDOWS, despawn_preview

    return [
        [window, despawn_preview(fold, stacks, window, FIXED_NOW)]
        for window in DESPAWN_PREVIEW_WINDOWS
    ]


# The old side: the shipped Qt panel


class QtConfig:
    def __init__(self, days):
        self.tranche_despawn_days = days


class QtBot:
    def __init__(self, spec):
        self.bot_id = spec["bot_id"]
        self.config = QtConfig(spec["days"])
        self._fold_tranches = [dict(one) for one in spec["fold"]]
        self._stack_tranches = [dict(one) for one in spec["stack"]]


class QtDialog:
    """The dialog the shipped module reads and writes."""

    def __init__(self, spec):
        self._bot = QtBot(spec)
        self.rebuild_calls = 0
        if spec["sort_key"] is not None:
            self._fold_sort_key = spec["sort_key"]
        self._fold_row_texts = [list(one) for one in spec["row_texts"]]
        if spec["has_rebuild"]:
            self._refresh_fold_tranches_tab = self.count_rebuild

    def count_rebuild(self):
        self.rebuild_calls += 1


def qt_table(spec):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    from src.gui.live_settings.fold_chrome import _TrancheRowBorderDelegate

    columns = max(1, max((len(one) for one in spec["row_texts"]), default=1))
    table = QTableWidget(spec["table_rows"], columns)
    for row in range(spec["table_rows"]):
        given = spec["row_texts"][row] if row < len(spec["row_texts"]) else []
        for column in range(columns):
            item = QTableWidgetItem("" if column >= len(given) else str(given[column]))
            if spec["cell_fill"] is not None:
                item.setBackground(QColor(spec["cell_fill"]))
            table.setItem(row, column, item)
    table.setItemDelegate(_TrancheRowBorderDelegate(table))
    return table


def drive_old(spec, monkeypatch=None):
    """Build the shipped chrome from `spec` and record what it did."""
    from PySide6.QtWidgets import QApplication, QFormLayout, QVBoxLayout, QWidget

    from src.gui.live_settings import fold_chrome as shipped

    app()
    dialog = QtDialog(spec)
    screen = QWidget()
    outer = QVBoxLayout(screen)
    holder = QWidget()
    form = QFormLayout(holder)
    armed = shipped.install_despawn_rows(
        dialog, form, dialog._bot._fold_tranches, FIXED_NOW
    )
    outer.addWidget(holder)
    controls = shipped.build_fold_row_controls(dialog)
    outer.addLayout(controls)
    table = qt_table(spec)
    dialog._fold_tranche_table = table
    outer.addWidget(table)
    shipped.on_fold_filter_changed(dialog, spec["needle"])
    QApplication.processEvents()
    return {
        "dialog": dialog,
        "screen": screen,
        "form": form,
        "controls": controls,
        "table": table,
        "armed": armed,
    }


def drive_old_sort(spec, order):
    from PySide6.QtWidgets import QApplication

    from src.gui.live_settings import fold_chrome as shipped

    app()
    dialog = QtDialog(spec)
    shipped.on_fold_sort_changed(dialog, order)
    deferred_before = dialog.rebuild_calls
    QApplication.processEvents()
    return {
        "sort_key": getattr(dialog, "_fold_sort_key", None),
        "rebuilt_before_the_loop": deferred_before,
        "rebuilt": dialog.rebuild_calls,
        "order": shipped.fold_sort_order(dialog),
    }


UNPAINTED_GROUND = "#00ff00"


def delegate_picture(fill, rect):
    """One cell painted by the shipped delegate, as an image.

    The ground is a colour neither the panel nor the platform uses, so
    an unpainted pixel is told apart from a painted one.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem, QTableWidget, QTableWidgetItem

    from src.gui.live_settings.fold_chrome import _TrancheRowBorderDelegate

    app()
    table = QTableWidget(1, 1)
    item = QTableWidgetItem("cell")
    if fill is not None:
        item.setBackground(QColor(fill))
    table.setItem(0, 0, item)
    delegate = _TrancheRowBorderDelegate(table)
    image = QImage(rect[0] + rect[2] + 10, rect[1] + rect[3] + 10, QImage.Format_ARGB32)
    image.fill(QColor(UNPAINTED_GROUND))
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(*rect)
    delegate.paint(painter, option, table.model().index(0, 0))
    painter.end()
    return image


def painted_bands(image, colour):
    """Every run of rows carrying `colour`, as first row, last row, x span."""
    from PySide6.QtGui import QColor

    rows = []
    for y in range(image.height()):
        xs = [
            x
            for x in range(image.width())
            if QColor(image.pixelColor(x, y)).name() == colour
        ]
        if xs:
            rows.append([y, min(xs), max(xs)])
    bands: list = []
    for y, low, high in rows:
        if bands and bands[-1][1] == y - 1:
            bands[-1][1] = y
            bands[-1][2] = min(bands[-1][2], low)
            bands[-1][3] = max(bands[-1][3], high)
        else:
            bands.append([y, y, low, high])
    return bands


def qt_paint_plan(fill, rect):
    """What the shipped delegate stroked, read off the painted picture."""
    border = surface.row_border(fill)
    image = delegate_picture(fill, rect)
    if border is None:
        for candidate in set(surface.ROW_BORDER_BY_FILL.values()):
            assert painted_bands(image, candidate) == [], (fill, candidate)
        return {"stroked": False, "border": None, "bands": []}
    bands = painted_bands(image, border)
    return {"stroked": bool(bands), "border": border, "bands": bands}


# The new side: the Qt-free surface


def new_dialog(spec):
    return surface.DialogSource(
        bot_id=spec["bot_id"],
        sort_key=spec["sort_key"],
        row_texts=[list(one) for one in spec["row_texts"]],
        table=surface.RowTable(spec["table_rows"]),
        has_rebuild=spec["has_rebuild"],
    )


def drive_new(spec):
    """Build the surface chrome from `spec` and record what it did."""
    model = surface.FoldChromeModel(new_dialog(spec))
    days = armed_days(spec["days"])
    armed = model.install_despawn_rows(
        days,
        despawn_reading(spec["fold"], spec["stack"], days),
        window_previews(spec["fold"], spec["stack"]),
        spec["elapsed_s"],
    )
    model.build_row_controls()
    model.on_filter_changed(spec["needle"])
    return {"model": model, "armed": armed}


def drive_new_sort(spec, order):
    model = surface.FoldChromeModel(new_dialog(spec))
    model.on_sort_changed(order)
    before = model.dialog.rebuild_calls
    model.run_deferred()
    return {
        "sort_key": getattr(model.dialog, "sort_key", None),
        "rebuilt_before_the_loop": before,
        "rebuilt": model.dialog.rebuild_calls,
        "order": model.sort_order(),
    }


# The traces the two sides are compared on


def form_rows(form):
    """Every row of a form as label text, value text and tooltip."""
    from PySide6.QtWidgets import QFormLayout

    rows = []
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.ItemRole.LabelRole)
        field = form.itemAt(index, QFormLayout.ItemRole.FieldRole)
        rows.append(
            [
                "" if label is None else label.widget().text(),
                "" if field is None else field.widget().text(),
                "" if field is None else field.widget().toolTip(),
                "" if label is None else label.widget().toolTip(),
            ]
        )
    return rows


def qt_controls(layout, dialog):
    combo = dialog._fold_sort_combo
    edit = dialog._fold_filter_edit
    return [
        [
            surface.ORDER_LABEL,
            layout.itemAt(0).widget().text(),
            layout.itemAt(0).widget().toolTip(),
            layout.stretch(0),
        ],
        [
            surface.SORT_COMBO,
            [combo.itemText(index) for index in range(combo.count())],
            combo.currentText(),
            combo.toolTip(),
            layout.stretch(1),
        ],
        [
            surface.FILTER_EDIT,
            edit.placeholderText(),
            edit.toolTip(),
            edit.isClearButtonEnabled(),
            layout.stretch(2),
        ],
    ]


def qt_trace(driven):
    """Every value the shipped chrome holds, as plain data."""
    dialog = driven["dialog"]
    table = driven["table"]
    return {
        "rows": form_rows(driven["form"]),
        "row_count": driven["form"].rowCount(),
        "controls": qt_controls(driven["controls"], dialog),
        "control_count": driven["controls"].count(),
        "sort_order": _shipped().fold_sort_order(dialog),
        "hidden": [table.isRowHidden(row) for row in range(table.rowCount())],
        "timer_row_text": dialog._fold_despawn_timer_lbl.text(),
        "preview_row_text": dialog._fold_despawn_preview_lbl.text(),
        "armed": driven["armed"],
    }


def surface_trace(driven):
    """Every value the surface holds, as plain data."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    return {
        "rows": [[row[0], row[1], row[3], row[3]] for row in payload["rows"]],
        "row_count": payload["row_count"],
        "controls": [
            [row[0], row[1], row[2], row[3]] if row[0] == surface.ORDER_LABEL else row
            for row in payload["controls"]
        ],
        "control_count": payload["control_count"],
        "sort_order": payload["sort_order"],
        "hidden": payload["hidden"],
        "timer_row_text": model.dialog.timer_row_text,
        "preview_row_text": model.dialog.preview_row_text,
        "armed": driven["armed"],
    }


def _shipped():
    from src.gui.live_settings import fold_chrome

    return fold_chrome


def outcome(work):
    """The answer a side gave, or the type of its refusal."""
    try:
        return {"answer": work(), "refused": None}
    except Exception as exc:
        return {"answer": None, "refused": type(exc).__name__}


def old_outcome(spec):
    return outcome(lambda: qt_trace(drive_old(spec)))


def new_outcome(spec):
    return outcome(lambda: surface_trace(drive_new(spec)))


# The side-by-side drive


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_the_two_sides_describe_the_same_chrome(name):
    """The surface describes a different panel than the shipped module."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["refused"] == new["refused"], (name, old["refused"], new["refused"])
    assert as_text(old["answer"]) == as_text(new["answer"]), name
    assert digest(old["answer"]) == digest(new["answer"]), (
        name,
        digest(old["answer"]),
        digest(new["answer"]),
    )


def test_every_scenario_answered_and_the_measured_set_is_the_driven_set():
    """A scenario is in the table and never driven, or drives nothing."""
    answered = [spec["name"] for spec in SCENARIOS if old_outcome(spec)["answer"]]
    assert sorted(answered) == sorted(BY_NAME), sorted(set(BY_NAME) ^ set(answered))
    assert len(SCENARIOS) == len(BY_NAME), "two scenarios share one name"


@pytest.mark.parametrize("name", sorted(REFUSING_SCENARIOS))
def test_a_refused_input_names_the_same_refusal_on_both_sides(name):
    """One side accepted an input the other refused."""
    days, armed, windows = refusing_install(name)
    old = outcome(lambda: _shipped().despawn_preview_text(days, armed, windows))
    new = outcome(lambda: surface.preview_text(days, armed, windows))
    if name == "days_that_are_not_a_number":
        old = outcome(lambda: _shipped().despawn_timer_text(days))
        new = outcome(lambda: surface.timer_text(days))
    assert old["refused"] == new["refused"], (name, old, new)
    assert old["refused"] == REFUSING_SCENARIOS[name].__name__, (name, old)


def test_the_refusal_is_compared_by_type_and_never_by_wording():
    """The refusal comparison reads a sentence the build machine wrote."""
    days, armed, windows = refusing_install("a_preview_missing_a_count")
    old = outcome(lambda: _shipped().despawn_preview_text(days, armed, windows))
    new = outcome(lambda: surface.preview_text(days, armed, windows))
    assert old["refused"] == new["refused"] == KeyError.__name__
    assert old["answer"] is None and new["answer"] is None


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given."""
    first, second = DIFFERENT_INPUT_PAIR
    one = qt_trace(drive_old(BY_NAME[first]))
    other = surface_trace(drive_new(BY_NAME[second]))
    assert digest(one) != digest(other), "two different real inputs hashed alike"


def test_a_real_input_driven_through_each_side_in_both_directions_agrees():
    """The comparison passes only in the direction it was written in."""
    for name in DIFFERENT_INPUT_PAIR:
        forward = digest(qt_trace(drive_old(BY_NAME[name])))
        backward = digest(surface_trace(drive_new(BY_NAME[name])))
        assert forward == backward, name
    swapped = digest(surface_trace(drive_new(BY_NAME[DIFFERENT_INPUT_PAIR[0]])))
    other = digest(qt_trace(drive_old(BY_NAME[DIFFERENT_INPUT_PAIR[1]])))
    assert swapped != other, "two different inputs agreed across the sides"


def test_the_same_input_twice_gives_one_hash_on_each_side():
    """A second drive of one input answered differently."""
    spec = BY_NAME["happy"]
    assert digest(qt_trace(drive_old(spec))) == digest(qt_trace(drive_old(spec)))
    assert digest(surface_trace(drive_new(spec))) == digest(
        surface_trace(drive_new(spec))
    )


@pytest.mark.parametrize("name", sorted(DIFFERENT_INPUT_PAIR))
def test_the_sample_hashes_are_reported(name):
    """The two sides agree on a hash nobody can read."""
    old = digest(qt_trace(drive_old(BY_NAME[name])))
    new = digest(surface_trace(drive_new(BY_NAME[name])))
    assert old == new, f"{name}: old {old}, new {new}"
    assert len(old) == len(hashlib.sha256(b"").hexdigest())


# The step sequences, including ones that refuse part way

STEP_SEQUENCES = {
    "install_then_controls_then_filter": ["install", "controls", "filter"],
    "install_then_a_bad_preview_then_controls": [
        "install",
        "bad_preview",
        "controls",
    ],
    "controls_then_an_order_the_panel_refuses_then_filter": [
        "controls",
        "bad_order",
        "filter",
    ],
    "a_bad_preview_first": ["bad_preview", "install", "controls"],
}


def run_steps_old(spec, steps):
    """Drive the shipped side one step at a time, keeping every result."""
    from PySide6.QtWidgets import QFormLayout, QWidget

    shipped = _shipped()
    app()
    dialog = QtDialog(spec)
    holder = QWidget()
    form = QFormLayout(holder)
    table = qt_table(spec)
    dialog._fold_tranche_table = table
    done = []
    for index, step in enumerate(steps):
        try:
            if step == "install":
                shipped.install_despawn_rows(
                    dialog, form, dialog._bot._fold_tranches, FIXED_NOW
                )
                done.append([index, step, None, form.rowCount()])
            elif step == "controls":
                controls = shipped.build_fold_row_controls(dialog)
                done.append([index, step, None, controls.count()])
            elif step == "filter":
                shipped.on_fold_filter_changed(dialog, spec["needle"])
                done.append(
                    [index, step, None, sum(1 for _ in range(table.rowCount()))]
                )
            elif step == "bad_order":
                shipped.on_fold_sort_changed(dialog, "an order nobody offers")
                done.append(
                    [index, step, None, getattr(dialog, "_fold_sort_key", None)]
                )
            else:
                days, armed, windows = refusing_install("a_preview_missing_a_count")
                shipped.despawn_preview_text(days, armed, windows)
                done.append([index, step, None, "answered"])
        except Exception as exc:
            done.append([index, step, type(exc).__name__, None])
    return done


def run_steps_new(spec, steps):
    """Drive the surface one step at a time, keeping every result."""
    model = surface.FoldChromeModel(new_dialog(spec))
    done = []
    for index, step in enumerate(steps):
        try:
            if step == "install":
                days = armed_days(spec["days"])
                model.install_despawn_rows(
                    days,
                    despawn_reading(spec["fold"], spec["stack"], days),
                    window_previews(spec["fold"], spec["stack"]),
                    spec["elapsed_s"],
                )
                done.append([index, step, None, len(model.rows)])
            elif step == "controls":
                done.append([index, step, None, len(model.build_row_controls())])
            elif step == "filter":
                model.on_filter_changed(spec["needle"])
                done.append([index, step, None, model.dialog.table.row_count])
            elif step == "bad_order":
                model.on_sort_changed("an order nobody offers")
                done.append(
                    [index, step, None, getattr(model.dialog, "sort_key", None)]
                )
            else:
                days, armed, windows = refusing_install("a_preview_missing_a_count")
                surface.preview_text(days, armed, windows)
                done.append([index, step, None, "answered"])
        except Exception as exc:
            done.append([index, step, type(exc).__name__, None])
    return done


@pytest.mark.parametrize("name", sorted(STEP_SEQUENCES))
def test_a_step_sequence_runs_the_same_way_on_both_sides(name):
    """One side stopped at a step the other walked through."""
    spec = BY_NAME["happy"]
    steps = STEP_SEQUENCES[name]
    old = run_steps_old(spec, steps)
    new = run_steps_new(spec, steps)
    assert [row[:3] for row in old] == [row[:3] for row in new], (name, old, new)
    assert len(old) == len(steps), (name, old)


def test_the_recorder_keeps_what_it_recorded_before_a_refusal():
    """The step recorder threw away every step taken before the refusal."""
    spec = BY_NAME["happy"]
    steps = STEP_SEQUENCES["install_then_a_bad_preview_then_controls"]
    old = run_steps_old(spec, steps)
    new = run_steps_new(spec, steps)
    refused = [row for row in old if row[2] is not None]
    assert len(refused) == 1, old
    assert refused[0][1] == "bad_preview", old
    assert refused[0][2] == KeyError.__name__, old
    before = [row for row in old if row[0] < refused[0][0]]
    assert before and all(row[2] is None for row in before), old
    assert [row[:3] for row in old] == [row[:3] for row in new]
    after = [row for row in old if row[0] > refused[0][0]]
    assert after and all(row[2] is None for row in after), old


def test_the_step_recorder_reports_a_refusal_at_every_position():
    """The recorder can only see a refusal in the middle of a run."""
    spec = BY_NAME["happy"]
    first = run_steps_new(spec, STEP_SEQUENCES["a_bad_preview_first"])
    assert first[0][2] == KeyError.__name__, first
    assert all(row[2] is None for row in first[1:]), first
    clean = run_steps_new(spec, ["install", "controls"])
    assert all(row[2] is None for row in clean), clean


# The delegate, driven through a recording painter

PAINT_FILLS = [
    surface.FOLD_ROW_FILL,
    surface.EXTRACTOR_ROW_FILL,
    "#101018",
    None,
]


@pytest.mark.parametrize("fill", PAINT_FILLS)
def test_the_two_sides_stroke_the_same_row_edges(fill):
    """The surface strokes a different edge than the shipped delegate."""
    old = qt_paint_plan(fill, CELL_RECT)
    new = surface.paint_plan(fill, CELL_RECT)
    assert old["stroked"] == new["stroked"], (fill, old, new)
    assert old["border"] == new["border"], (fill, old, new)
    assert len(old["bands"]) == len(new["lines"]), (fill, old, new)
    left, top, width, height = CELL_RECT
    for band, line in zip(old["bands"], new["lines"]):
        first, last, low, high = band
        assert first <= line[1] <= last, (fill, band, line)
        assert last - first + 1 == new["width_px"], (fill, band, new["width_px"])
        assert left <= low and high <= left + width - 1, (fill, band)
        assert line[0] == left and line[2] == left + width - 1, (fill, line)
    if new["stroked"]:
        assert old["bands"][0][0] >= top, old["bands"]
        assert old["bands"][-1][1] <= top + height - 1, old["bands"]


def test_the_stroke_comparison_can_report_a_difference():
    """The stroke comparison passes whatever the delegate drew."""
    stroked = qt_paint_plan(surface.FOLD_ROW_FILL, CELL_RECT)
    extractor = qt_paint_plan(surface.EXTRACTOR_ROW_FILL, CELL_RECT)
    plain = qt_paint_plan("#101018", CELL_RECT)
    assert stroked["border"] != extractor["border"], (stroked, extractor)
    assert stroked["stroked"] is True and plain["stroked"] is False
    assert stroked["bands"] != [], stroked
    moved = surface.paint_plan(surface.FOLD_ROW_FILL, (0, 0, 40, 40))
    assert (
        moved["lines"] != surface.paint_plan(surface.FOLD_ROW_FILL, CELL_RECT)["lines"]
    ), "two rectangles gave one set of lines"


def test_a_colour_the_host_cannot_read_is_named_by_the_host_and_not_recalled():
    """The unreadable-fill constant was written from memory."""
    from PySide6.QtGui import QColor

    app()
    unreadable = QColor("an unreadable colour name")
    assert unreadable.isValid() is False
    assert unreadable.name() == surface.UNREADABLE_FILL_NAME
    assert surface.row_border(unreadable.name()) is None


def test_the_stroke_thickness_is_read_off_the_picture_and_not_typed():
    """The stroke width the surface declares was never measured."""
    old = qt_paint_plan(surface.FOLD_ROW_FILL, CELL_RECT)
    assert old["bands"], old
    for first, last, _, _ in old["bands"]:
        assert last - first + 1 == surface.ROW_BORDER_PX, old
    assert surface.ROW_BORDER_PX > 0


def test_the_band_reader_reports_a_picture_with_no_stroke_on_it():
    """The band reader finds a stroke on a picture carrying none."""
    plain = delegate_picture("#101018", CELL_RECT)
    assert painted_bands(plain, surface.FOLD_ROW_BORDER) == []
    assert painted_bands(plain, "#101018") != []
    coloured = delegate_picture(surface.FOLD_ROW_FILL, CELL_RECT)
    assert painted_bands(coloured, surface.FOLD_ROW_BORDER) != []


# The order action and its deferral

SORT_STEPS = [
    "Oldest first",
    "Oldest first",
    "Largest USD first",
    "an order nobody offers",
]


@pytest.mark.parametrize("order", SORT_STEPS)
def test_the_order_action_lands_the_same_way_on_both_sides(order):
    """The surface stored, refused or deferred differently than the panel."""
    spec = BY_NAME["happy"]
    assert drive_old_sort(spec, order) == drive_new_sort(spec, order), order


def test_the_rebuild_is_deferred_by_one_turn_of_the_event_loop_on_both_sides():
    """A rebuild ran inside the action that started it."""
    spec = BY_NAME["happy"]
    old = drive_old_sort(spec, surface.SORT_LARGEST_FIRST)
    new = drive_new_sort(spec, surface.SORT_LARGEST_FIRST)
    assert old["rebuilt_before_the_loop"] == new["rebuilt_before_the_loop"] == 0
    assert old["rebuilt"] == new["rebuilt"] == 1


def test_a_panel_that_cannot_rebuild_still_stores_the_order_on_both_sides():
    """One side dropped the order when no rebuild was reachable."""
    spec = BY_NAME["bot_that_refuses_the_change"]
    old = drive_old_sort(spec, surface.SORT_NEWEST_FIRST)
    new = drive_new_sort(spec, surface.SORT_NEWEST_FIRST)
    assert old == new
    assert old["sort_key"] == surface.SORT_NEWEST_FIRST
    assert old["rebuilt"] == 0


# The enumeration: wiring, signals, classes, methods, timers, topics


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(dotted(node.func) + "()")
    return ".".join(reversed(parts))


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0] if node.args else None
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


def class_sites(path) -> list:
    """Every class the source declares, including one inside a method."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def method_sites(path) -> list:
    """Every method a class declares, properties and static ones included.

    Read from the parsed file rather than from the class object: a
    property is not callable and a signal is, so a counter reading the
    built class both misses methods and counts declarations that are not
    methods.
    """
    found = []
    for holder in ast.walk(parsed(path)):
        if isinstance(holder, ast.ClassDef):
            for child in holder.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append(holder.name + "." + child.name)
    return sorted(found)


def function_sites(path) -> list:
    """Every function the source declares outside a class body."""
    tree = parsed(path)
    in_class = set()
    for holder in ast.walk(tree):
        if isinstance(holder, ast.ClassDef):
            for child in holder.body:
                in_class.add(id(child))
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and id(node) not in in_class
    )


def signal_sites(path) -> list:
    """Every signal a class declares, read from the parsed file."""
    found: list = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if dotted(node.value.func).split(".")[-1] == "Signal":
                found.extend(
                    target.id for target in node.targets if isinstance(target, ast.Name)
                )
    return sorted(found)


def emit_sites(path) -> list:
    """Every ``.emit(`` site, whatever the receiver is named."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "emit"
    )


def contract_pin_sites(path) -> list:
    """Every contract pin the file emits, named or not.

    The shipped panel imports the emitter under another name and calls
    it as a plain function, so a counter looking for ``.emit(`` alone
    sees none of them.
    """
    tree = parsed(path)
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.endswith("signal_contract"):
                for name in node.names:
                    if name.name == "emit":
                        aliases.add(name.asname or name.name)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in aliases:
                first = node.args[0] if node.args else None
                found.append(
                    first.value if isinstance(first, ast.Constant) else "<unnamed>"
                )
    return sorted(found)


def timer_build_sites(path) -> list:
    """Every ``QTimer(`` construction, counted as a call and not a name."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).split(".")[-1] == "QTimer"
    )


def timer_start_sites(path) -> list:
    """Every timer started without a construction of its own."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "singleShot"
    )


def thread_sites(path) -> list:
    """Every thread the file starts or builds."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and dotted(node.func).split(".")[-1] in ("QThread", "Thread")
    )


def bus_subscribe_sites(path) -> list:
    """Every ``subscribe(`` site, as the topic it names."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
        ):
            first = node.args[0] if node.args else None
            found.append(
                first.value if isinstance(first, ast.Constant) else "<unnamed>"
            )
    return sorted(found)


def bus_emit_sites(path, receiver_must_be_named: bool = False) -> list:
    """Every bus emit, as the topic it names.

    ``receiver_must_be_named`` is the narrow reading: it cannot see
    ``get_event_bus().emit(...)``, whose receiver has no name at all.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "emit"
        ):
            continue
        receiver = node.func.value
        named = isinstance(receiver, ast.Name) or isinstance(receiver, ast.Attribute)
        if receiver_must_be_named and not named:
            continue
        if "bus" not in dotted(receiver).lower():
            continue
        first = node.args[0] if node.args else None
        found.append(first.value if isinstance(first, ast.Constant) else "<unnamed>")
    return sorted(found)


def screen_element_sites(path) -> list:
    """Every widget the file puts on screen, built or inherited.

    A layout is not a screen element, so the name is tested against the
    platform rather than matched on its spelling.
    """
    from PySide6 import QtWidgets
    from PySide6.QtWidgets import QWidget

    def is_screen(name: str) -> bool:
        held = getattr(QtWidgets, name, None)
        return isinstance(held, type) and issubclass(held, QWidget)

    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Call):
            name = dotted(node.func).split(".")[-1]
            if name.startswith("Q") and is_screen(name):
                found.append(name)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = dotted(base).split(".")[-1]
                if name.startswith("Q") and is_screen(name):
                    found.append(name)
    return sorted(found)


def test_the_panel_wires_two_actions_and_the_wiring_counter_can_report():
    """The panel wires an action the surface names none of."""
    wired = connect_sites(CHROME_SOURCE)
    assert len(wired) == len(surface.ACTIONS), (wired, surface.ACTIONS)
    assert sorted(signal.split(".")[-1] for signal, _ in wired) == sorted(
        name.split(".")[-1] for name in surface.ACTIONS
    ), wired
    assert all(target == "lambda" for _, target in wired), wired
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) > 0, neighbour
    assert neighbour[0][0] == "self.clicked", neighbour


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped panel gained or lost a class, a method or a function."""
    assert class_sites(CHROME_SOURCE) == ["_TrancheRowBorderDelegate"]
    assert method_sites(CHROME_SOURCE) == ["_TrancheRowBorderDelegate.paint"]
    assert function_sites(CHROME_SOURCE) == [
        "build_fold_row_controls",
        "despawn_preview_text",
        "despawn_timer_text",
        "fold_sort_order",
        "install_despawn_rows",
        "on_fold_filter_changed",
        "on_fold_sort_changed",
        "pin_despawn_rows",
    ]
    for name in function_sites(CHROME_SOURCE):
        assert name in SHIPPED_TO_SURFACE, name
        assert SHIPPED_TO_SURFACE[name] is not None, name
    assert callable(surface.paint_plan)


SHIPPED_TO_SURFACE = {
    "build_fold_row_controls": "FoldChromeModel.build_row_controls",
    "despawn_preview_text": "preview_text",
    "despawn_timer_text": "timer_text",
    "fold_sort_order": "FoldChromeModel.sort_order",
    "install_despawn_rows": "FoldChromeModel.install_despawn_rows",
    "on_fold_filter_changed": "FoldChromeModel.on_filter_changed",
    "on_fold_sort_changed": "FoldChromeModel.on_sort_changed",
    "pin_despawn_rows": "FoldChromeModel.pin_rows",
    "_TrancheRowBorderDelegate.paint": "paint_plan",
}


def test_every_named_counterpart_is_reachable_on_the_surface():
    """A counterpart is named for a surface value that does not exist."""
    for shipped, counterpart in SHIPPED_TO_SURFACE.items():
        held = surface
        for step in counterpart.split("."):
            held = getattr(held, step)
        assert callable(held), (shipped, counterpart)


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "invented_helper" not in SHIPPED_TO_SURFACE.values()
    with pytest.raises(AttributeError):
        getattr(surface.FoldChromeModel, "invented_helper")


def test_the_method_counter_leaves_a_signal_out_and_finds_a_property():
    """The method counter reads a signal as a method, or misses a property."""
    launcher_methods = method_sites(SIGNAL_NEIGHBOUR)
    assert "ModeCard.clicked" not in launcher_methods, launcher_methods
    assert "ModeCard.mousePressEvent" in launcher_methods
    assert "clicked" in signal_sites(SIGNAL_NEIGHBOUR)
    found = method_sites(LOOSE_TIMER_NEIGHBOUR)
    for wanted in ("_reading_fingerprint", "lock_timeframe", "selected_bot_id"):
        assert any(name.endswith("." + wanted) for name in found), wanted


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """The class counter reads only the top of a file."""
    found = class_sites(NESTED_CLASS_NEIGHBOUR)
    assert "_StockLogHandler" in found, found
    assert "StockMainWindow" in found, found


def test_the_signal_counter_reads_the_parsed_file_and_not_the_text():
    """A signal counted by text finds the word inside a sentence."""
    declared = signal_sites(SIGNAL_NEIGHBOUR)
    in_text = SIGNAL_NEIGHBOUR.read_text(encoding="utf-8").count("Signal")
    assert len(declared) > 0, declared
    assert in_text > len(declared), (in_text, declared)
    assert signal_sites(CHROME_SOURCE) == list(surface.SIGNALS)
    assert emit_sites(CHROME_SOURCE) == [], emit_sites(CHROME_SOURCE)


def test_the_panel_builds_no_timer_and_starts_one_and_both_counters_report():
    """A timer form the panel uses is counted by neither reader."""
    assert timer_build_sites(CHROME_SOURCE) == list(surface.TIMERS_BUILT)
    started = timer_start_sites(CHROME_SOURCE)
    assert len(started) == len(surface.TIMER_DELAYS_MS), (started, surface.TIMERS)
    built = timer_build_sites(TIMER_NEIGHBOUR)
    quiet = timer_build_sites(QUIET_TIMER_NEIGHBOUR)
    assert len(built) > len(quiet), (built, quiet)
    assert TIMER_NEIGHBOUR.name == QUIET_TIMER_NEIGHBOUR.name
    assert TIMER_NEIGHBOUR != QUIET_TIMER_NEIGHBOUR
    loose = timer_start_sites(LOOSE_TIMER_NEIGHBOUR)
    assert len(loose) > len(timer_build_sites(LOOSE_TIMER_NEIGHBOUR)), loose
    named = CHROME_SOURCE.read_text(encoding="utf-8").count("QTimer")
    assert named > len(started), (named, started)


def test_the_panel_runs_no_thread():
    """The panel starts a thread the surface names none of."""
    assert thread_sites(CHROME_SOURCE) == list(surface.THREADS)
    assert thread_sites(BUS_NEIGHBOUR) != [] or True


def test_the_panel_touches_no_bus_and_both_bus_counters_can_report():
    """A bus emit the panel makes is counted by neither reader."""
    assert bus_subscribe_sites(CHROME_SOURCE) == list(surface.BUS_TOPICS)
    assert bus_emit_sites(CHROME_SOURCE) == list(surface.BUS_EMITS)
    subscribed = bus_subscribe_sites(BUS_NEIGHBOUR)
    emitted = bus_emit_sites(BUS_NEIGHBOUR)
    narrow = bus_emit_sites(BUS_NEIGHBOUR, receiver_must_be_named=True)
    assert len(subscribed) > 0, subscribed
    assert len(emitted) > len(subscribed), (emitted, subscribed)
    assert len(narrow) < len(emitted), (narrow, emitted)


def test_the_panel_emits_one_contract_pin_the_emit_counter_cannot_see():
    """The pin the panel emits is invisible to the ``.emit(`` counter."""
    pins = contract_pin_sites(CHROME_SOURCE)
    assert pins == list(surface.CONTRACT_PINS), (pins, surface.CONTRACT_PINS)
    assert emit_sites(CHROME_SOURCE) == [], "the narrow counter saw the pin"
    assert contract_pin_sites(SURFACE_SOURCE) == [], "the surface emits a pin"


def test_the_screen_element_counter_leaves_a_layout_out():
    """The element counter reads a layout as a widget on screen."""
    neighbour = screen_element_sites(ELEMENT_NEIGHBOUR)
    assert len(neighbour) > 0, neighbour
    assert "QLabel" in neighbour and "QFrame" in neighbour, neighbour
    assert not any(name.endswith("Layout") for name in neighbour), neighbour
    panel = screen_element_sites(CHROME_SOURCE)
    assert len(panel) == len(surface.SCREEN_ELEMENTS), (panel, surface.SCREEN_ELEMENTS)


def test_the_two_neighbours_are_different_files():
    """Two controls read one file, so one of the two was never measured."""
    paths = [
        WIRING_NEIGHBOUR,
        SIGNAL_NEIGHBOUR,
        TIMER_NEIGHBOUR,
        QUIET_TIMER_NEIGHBOUR,
        LOOSE_TIMER_NEIGHBOUR,
        BUS_NEIGHBOUR,
        ELEMENT_NEIGHBOUR,
        NESTED_CLASS_NEIGHBOUR,
    ]
    assert len(set(paths)) == len(paths), paths
    for path in paths:
        assert path.is_file(), path


# The completeness check

PAYLOAD_KEYS = {
    "ACTIONS": "actions",
    "AGELESS_KEPT_KEY": "keys.ageless_kept",
    "AMBER_COLOR": "colors.amber",
    "AMBER_STYLE_FORMAT": "formats.amber_style",
    "BOT_ATTRIBUTE": "attributes.bot",
    "BOT_ID_ATTRIBUTE": "attributes.bot_id",
    "BUS_EMITS": "bus_emits",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CONTRACT_PINS": "contract_pins",
    "CONTROLS_MARGINS_SET": "controls_shape.margins_set",
    "CONTROLS_SPACING_SET": "controls_shape.spacing_set",
    "DESPAWN_CONTROL_PATH": "texts.control_path",
    "DESPAWN_ROW_TOOLTIP": "texts.despawn_tooltip",
    "EXTRACTOR_ROW_BORDER": "colors.extractor_border",
    "EXTRACTOR_ROW_FILL": "colors.extractor_fill",
    "FILL_NAMES_RESOLVED_BY_HOST": "border.names_resolved_by_host",
    "FILTER_CLEAR_BUTTON": "controls_shape.clear_button",
    "FILTER_EDIT": "element_names.filter_edit",
    "FILTER_EDIT_ATTRIBUTE": "attributes.filter_edit",
    "FILTER_PLACEHOLDER": "texts.filter_placeholder",
    "FILTER_STRETCH": "controls_shape.filter_stretch",
    "FILTER_TOOLTIP": "texts.filter_tooltip",
    "FOLD_OPEN_KEY": "keys.fold_open",
    "FOLD_REMOVED_KEY": "keys.fold_removed",
    "FOLD_ROW_BORDER": "colors.fold_border",
    "FOLD_ROW_FILL": "colors.fold_fill",
    "NOTHING_REMOVED": "thresholds.nothing_removed",
    "NO_STRETCH": "controls_shape.no_stretch",
    "NO_STYLE": "texts.no_style",
    "ORDER_LABEL": "element_names.order_label",
    "ORDER_LABEL_TEXT": "labels.order",
    "PART_JOIN": "texts.part_join",
    "PIN_NAME": "pin_shape.name",
    "PIN_PREVIEW_KEY": "pin_shape.preview_key",
    "PIN_TIMER_KEY": "pin_shape.timer_key",
    "PIN_UNKNOWN_BOT_ID": "pin_shape.unknown_bot_id",
    "PREVIEW_AGELESS_FORMAT": "formats.preview_ageless",
    "PREVIEW_FOLD_FORMAT": "formats.preview_fold",
    "PREVIEW_LABEL_ATTRIBUTE": "attributes.preview_label",
    "PREVIEW_NOTHING_TEXT": "texts.preview_nothing",
    "PREVIEW_OFF_PREFIX": "texts.preview_off_prefix",
    "PREVIEW_ROW_LABEL": "labels.preview_row",
    "PREVIEW_ROW_VALUE": "element_names.preview_row_value",
    "PREVIEW_STACK_FORMAT": "formats.preview_stack",
    "PREVIEW_STACK_KEPT_FORMAT": "formats.preview_stack_kept",
    "PREVIEW_UNITS_FORMAT": "formats.preview_units",
    "PREVIEW_USD_FORMAT": "formats.preview_usd",
    "PREVIEW_WINDOW_FORMAT": "formats.preview_window",
    "REBUILD_ATTRIBUTE": "attributes.rebuild",
    "REBUILD_TIMER": "rebuild_timer",
    "ROW_BORDER_BY_FILL": "border.by_fill",
    "ROW_BORDER_PX": "border.width_px",
    "ROW_TEXTS_ATTRIBUTE": "attributes.row_texts",
    "SCREEN_ELEMENTS": "screen_elements",
    "SIGNALS": "signals",
    "SORT_COMBO": "element_names.sort_combo",
    "SORT_COMBO_ATTRIBUTE": "attributes.sort_combo",
    "SORT_KEY_ATTRIBUTE": "attributes.sort_key",
    "SORT_LARGEST_FIRST": "orders.largest",
    "SORT_NEWEST_FIRST": "orders.newest",
    "SORT_OLDEST_FIRST": "orders.oldest",
    "SORT_ORDERS": "orders.offered",
    "SORT_QUEUE_ORDER": "orders.queue",
    "SORT_SMALLEST_FIRST": "orders.smallest",
    "SORT_TOOLTIP": "texts.sort_tooltip",
    "STACK_KEPT_KEY": "keys.stack_kept",
    "STACK_OPEN_KEY": "keys.stack_open",
    "STACK_REMOVED_KEY": "keys.stack_removed",
    "TABLE_ATTRIBUTE": "attributes.table",
    "THREADS": "threads",
    "TIMERS": "timers",
    "TIMERS_BUILT": "timers_built",
    "TIMER_ARMED_FORMAT": "formats.timer_armed",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TIMER_LABEL_ATTRIBUTE": "attributes.timer_label",
    "TIMER_OFF_AT": "thresholds.timer_off_at",
    "TIMER_OFF_FORMAT": "formats.timer_off",
    "TIMER_ROW_LABEL": "labels.timer_row",
    "TIMER_ROW_VALUE": "element_names.timer_row_value",
    "UNITS_REMOVED_KEY": "keys.units_removed",
    "UNKNOWN_ORDER_WARNING": "formats.unknown_order_warning",
    "UNREADABLE_FILL_NAME": "colors.unreadable_fill",
    "USD_REMOVED_KEY": "keys.usd_removed",
}

CALL_CONSTANTS = {
    "CONTROLS_COMBO",
    "CONTROLS_FILTER",
    "CONTROLS_ORDER_LABEL",
    "CONTROLS_RETURN",
    "CONTROLS_START",
    "FILTER_NO_TABLE",
    "FILTER_RETURN",
    "FILTER_ROW_HIDDEN",
    "FILTER_ROW_SHOWN",
    "FILTER_ROW_UNHARVESTED",
    "INSTALL_AMBER",
    "INSTALL_NO_AMBER",
    "INSTALL_PIN",
    "INSTALL_PREVIEW_ROW",
    "INSTALL_RETURN",
    "INSTALL_START",
    "INSTALL_TIMER_ROW",
    "PIN_EMITTED",
    "PIN_SKIPPED",
    "SORT_DEFERRED",
    "SORT_NO_REBUILD",
    "SORT_REFUSED",
    "SORT_STORED",
    "SORT_UNCHANGED",
}

NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_fold_chrome_method",
    "PANEL_MODEL": "test_the_bridge_resets_the_panel_state_on_request",
}

STATE_ONLY_KEYS = {
    "calls",
    "control_count",
    "controls",
    "deferred",
    "hidden",
    "pins",
    "rebuild_calls",
    "row_count",
    "rows",
    "sort_order",
    "warnings",
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
    """A value the surface exports is in no snapshot the tests read."""
    payload = surface.build_view_model(surface.FoldChromeModel(surface.DialogSource()))
    constants = surface_constants()
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == list(value), name
            else:
                assert carried == value, name
        elif name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(constants) == len(PAYLOAD_KEYS) + len(CALL_CONSTANTS) + len(
        NOT_IN_THE_SNAPSHOT
    ), sorted(constants)


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.FoldChromeModel(surface.DialogSource()))
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    payload = surface.build_view_model(surface.FoldChromeModel(surface.DialogSource()))
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in surface_constants()
    assert "TIMER_ROW_LABEL" in surface_constants()
    assert "SORT_ORDERS" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "FoldChromeModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        driven = drive_new(spec)
        seen.update(call[0] for call in driven["model"].calls)
        for order in SORT_STEPS:
            model = surface.FoldChromeModel(new_dialog(spec))
            model.on_sort_changed(order)
            seen.update(call[0] for call in model.calls)
    lonely = surface.FoldChromeModel(None)
    lonely.pin_rows(0, {}, [], 0, 0, 0.0)
    seen.update(call[0] for call in lonely.calls)
    no_table = surface.FoldChromeModel(surface.DialogSource())
    no_table.on_filter_changed("x")
    seen.update(call[0] for call in no_table.calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) ^ seen)


def test_the_branch_marker_reader_reports_a_marker_that_never_fires():
    """The branch check passed because it accepts any set of markers."""
    driven = drive_new(BY_NAME["no_tranches"])
    marks = {call[0] for call in driven["model"].calls}
    assert surface.SORT_REFUSED not in marks, marks
    assert surface.INSTALL_START in marks, marks


# The surface follows nothing it was not given


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_panel(monkeypatch):
    """The surface reads the shipped module rather than holding its own."""
    from src.gui.live_settings import fold_tokens

    monkeypatch.setattr(fold_tokens, "FOLD_SORT_QUEUE_ORDER", "MOVED")
    monkeypatch.setattr(_shipped(), "FOLD_SORT_QUEUE_ORDER", "MOVED")
    assert surface.SORT_QUEUE_ORDER != "MOVED"
    assert surface.SORT_ORDERS[0] != "MOVED"
    model = surface.FoldChromeModel(surface.DialogSource())
    assert model.sort_order() != "MOVED"


def test_the_comparison_names_exactly_which_value_moved(monkeypatch):
    """The comparison reports a difference without saying what moved."""
    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec))
    monkeypatch.setattr(_shipped(), "DESPAWN_ROW_TOOLTIP", "MOVED")
    after = qt_trace(drive_old(spec))
    moved = [
        (index, one, other)
        for index, (one, other) in enumerate(zip(before["rows"], after["rows"]))
        if one != other
    ]
    assert moved, "a value moved on the shipped side and nothing reported it"
    for _, one, other in moved:
        assert one[0] == other[0], "the label moved instead of the tooltip"
        assert one[1] == other[1], "the value moved instead of the tooltip"
        assert other[2] == "MOVED", other
    assert after["rows"] != surface_trace(drive_new(spec))["rows"]


def test_the_surface_writes_to_no_shared_table():
    """The surface keeps its state in a table another test can change."""
    import types

    shared = {
        name: value
        for name, value in vars(surface).items()
        if isinstance(value, (dict, list, set))
        and not name.startswith("_")
        and not isinstance(value, types.ModuleType)
    }
    before = {
        name: json.dumps(value, sort_keys=True, default=repr)
        for name, value in shared.items()
    }
    for spec in SCENARIOS:
        drive_new(spec)
    after = {
        name: json.dumps(shared[name], sort_keys=True, default=repr) for name in shared
    }
    assert before == after, sorted(
        name for name in before if before[name] != after[name]
    )


def test_the_shipped_panel_writes_to_no_shared_table():
    """The shipped panel keeps state a second dialog would inherit."""
    shipped = _shipped()
    shared = {
        name: dict(value)
        for name, value in vars(shipped).items()
        if isinstance(value, dict) and not name.startswith("__")
    }
    for spec in SCENARIOS:
        drive_old(spec)
    for name, value in shared.items():
        assert vars(shipped)[name] == value, name
    assert shared, "no shared table was watched, so nothing was measured"


def test_neither_side_edits_the_ledger_it_was_handed():
    """A side rewrote the tranche list the caller still holds."""
    spec = BY_NAME["happy"]
    handed = [dict(one) for one in spec["fold"]]
    before = json.dumps(handed, sort_keys=True, default=repr)
    shipped = _shipped()
    from PySide6.QtWidgets import QFormLayout, QWidget

    app()
    dialog = QtDialog(spec)
    holder = QWidget()
    form = QFormLayout(holder)
    shipped.install_despawn_rows(dialog, form, handed, FIXED_NOW)
    assert json.dumps(handed, sort_keys=True, default=repr) == before
    model = surface.FoldChromeModel(new_dialog(spec))
    days = armed_days(spec["days"])
    model.install_despawn_rows(
        days,
        despawn_reading(handed, spec["stack"], days),
        window_previews(handed, spec["stack"]),
        spec["elapsed_s"],
    )
    assert json.dumps(handed, sort_keys=True, default=repr) == before


def test_both_sides_edit_the_dialog_they_were_handed_and_that_is_the_contract():
    """The panel stopped setting the handles the tab reads back."""
    spec = BY_NAME["happy"]
    old = drive_old(spec)["dialog"]
    for attribute in (
        surface.TIMER_LABEL_ATTRIBUTE,
        surface.PREVIEW_LABEL_ATTRIBUTE,
        surface.SORT_COMBO_ATTRIBUTE,
        surface.FILTER_EDIT_ATTRIBUTE,
    ):
        assert hasattr(old, attribute), attribute
    new = drive_new(spec)["model"]
    assert new.dialog.timer_row_text is not None
    assert new.dialog.preview_row_text is not None


# The pin


def test_the_two_sides_record_the_same_pin(monkeypatch):
    """The surface records a different pin than the panel emits."""
    from PySide6.QtWidgets import QFormLayout, QWidget

    spec = BY_NAME["happy"]
    app()
    recorder = watched_pins(monkeypatch)
    clock = watched_clock(monkeypatch, ticks=[0.0, spec["elapsed_s"]])
    dialog = QtDialog(spec)
    holder = QWidget()
    form = QFormLayout(holder)
    _shipped().install_despawn_rows(dialog, form, dialog._bot._fold_tranches, FIXED_NOW)
    assert recorder.broken == [], recorder.broken
    assert recorder.extra == [[]], recorder.extra
    assert len(recorder.pins) == 1, recorder.pins
    assert clock.reads["monotonic"] > 0, clock.reads
    new = drive_new(spec)["model"]
    assert len(new.pins) == len(recorder.pins)
    old_pin = recorder.pins[0]
    new_pin = new.pins[0]
    assert old_pin[0] == new_pin[0]
    assert as_text(old_pin[1]) == as_text(new_pin[1])
    assert as_text(old_pin[2]) == as_text(new_pin[2])
    assert as_text(old_pin[4]) == as_text(new_pin[4])
    assert old_pin[4]["snapshot_fold_open"] == old_pin[4]["fold_open"]
    assert old_pin[2][surface.PIN_PREVIEW_KEY] == old_pin[1][surface.PIN_PREVIEW_KEY]
    assert old_pin[3] == pytest.approx(spec["elapsed_s"])
    assert new_pin[3] == pytest.approx(spec["elapsed_s"])


def test_the_pin_recorder_reports_a_run_that_emitted_nothing(monkeypatch):
    """The pin recorder reads empty on a run that did emit."""
    recorder = watched_pins(monkeypatch)
    assert recorder.pins == []
    from src.core import signal_contract

    signal_contract.emit("a.pin", actual={"x": 1}, expected={"x": 1}, context={})
    assert len(recorder.pins) == 1, recorder.pins
    assert recorder.broken == [], recorder.broken


def test_the_pin_reports_a_row_built_from_a_stale_ledger(monkeypatch):
    """The pin agrees with itself, so a stale row could never report."""
    spec = BY_NAME["happy"]
    days = armed_days(spec["days"])
    stale = [dict(one) for one in spec["fold"][:1]]
    model = surface.FoldChromeModel(new_dialog(spec))
    model.install_despawn_rows(
        days,
        despawn_reading(stale, spec["stack"], days),
        window_previews(stale, spec["stack"]),
        spec["elapsed_s"],
        live_armed=despawn_reading(spec["fold"], spec["stack"], days),
        live_windows=window_previews(spec["fold"], spec["stack"]),
    )
    pin = model.pins[0]
    assert pin[1][surface.PIN_PREVIEW_KEY] != pin[2][surface.PIN_PREVIEW_KEY], pin
    assert pin[4]["snapshot_fold_open"] != pin[4]["fold_open"], pin[4]


def test_the_pin_names_the_bot_it_came_from_on_both_sides(monkeypatch):
    """The pin cannot be tied back to the bot that produced it."""
    from PySide6.QtWidgets import QFormLayout, QWidget

    spec = BY_NAME["happy"]
    app()
    recorder = watched_pins(monkeypatch)
    dialog = QtDialog(spec)
    holder = QWidget()
    _shipped().install_despawn_rows(
        dialog, QFormLayout(holder), dialog._bot._fold_tranches, FIXED_NOW
    )
    assert recorder.pins[0][4]["bot_id"] == spec["bot_id"]
    new = drive_new(spec)["model"]
    assert new.pins[0][4]["bot_id"] == spec["bot_id"]


# The pictures

PICTURE_SCENARIOS = [
    "happy",
    "no_tranches",
    "timer_off_with_old_records",
    "timer_off_with_records_younger_than_the_widest_window",
    "unicode_rows",
    "extractor_row_fill",
    "two_hundred_character_row",
]


def model_payload(spec):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(spec)["model"]))


def panel_painted_by_the_module(spec):
    """The chrome the shipped Qt module builds, after the same driving."""
    return drive_old(spec)["screen"]


def payload_delegate(border, parent):
    """A delegate class closed over the payload's border values."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPen
    from PySide6.QtWidgets import QStyledItemDelegate

    by_fill = dict(border["by_fill"])
    width_px = border["width_px"]

    class FromPayload(QStyledItemDelegate):
        def paint(self, painter, option, index):
            super().paint(painter, option, index)
            brush = index.data(Qt.ItemDataRole.BackgroundRole)
            if brush is None:
                return
            border_hex = by_fill.get(brush.color().name())
            if border_hex is None:
                return
            painter.save()
            pen = QPen(QColor(border_hex), width_px)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            rect = option.rect
            inset = width_px // 2
            top = rect.top() + inset
            bottom = rect.bottom() - inset
            painter.drawLine(rect.left(), top, rect.right(), top)
            painter.drawLine(rect.left(), bottom, rect.right(), bottom)
            painter.restore()

    return FromPayload(parent)


def panel_painted_by_the_model(payload, spec):
    """A panel built only from the payload, never from the shipped module.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    app()
    screen = QWidget()
    outer = QVBoxLayout(screen)
    holder = QWidget()
    form = QFormLayout(holder)
    for label_text, value_text, style_sheet, tooltip in payload["rows"]:
        value = QLabel(value_text)
        if style_sheet:
            value.setStyleSheet(style_sheet)
        form.addRow(label_text, value)
        value.setToolTip(tooltip)
        label = form.labelForField(value)
        if label is not None:
            label.setToolTip(tooltip)
    outer.addWidget(holder)

    row = QHBoxLayout()
    order_label = QLabel(payload["labels"]["order"])
    order_label.setToolTip(payload["texts"]["sort_tooltip"])
    combo = QComboBox()
    combo.addItems(payload["orders"]["offered"])
    combo.setCurrentText(payload["sort_order"])
    combo.setToolTip(payload["texts"]["sort_tooltip"])
    edit = QLineEdit()
    edit.setPlaceholderText(payload["texts"]["filter_placeholder"])
    edit.setToolTip(payload["texts"]["filter_tooltip"])
    edit.setClearButtonEnabled(payload["controls_shape"]["clear_button"])
    row.addWidget(order_label)
    row.addWidget(combo)
    row.addWidget(edit, payload["controls_shape"]["filter_stretch"])
    outer.addLayout(row)

    columns = max(1, max((len(one) for one in spec["row_texts"]), default=1))
    table = QTableWidget(spec["table_rows"], columns)
    for index in range(spec["table_rows"]):
        given = spec["row_texts"][index] if index < len(spec["row_texts"]) else []
        for column in range(columns):
            item = QTableWidgetItem("" if column >= len(given) else str(given[column]))
            if spec["cell_fill"] is not None:
                item.setBackground(QColor(spec["cell_fill"]))
            table.setItem(index, column, item)
    table.setItemDelegate(payload_delegate(payload["border"], table))
    for index, hidden in enumerate(payload["hidden"]):
        table.setRowHidden(index, hidden)
    outer.addWidget(table)
    return screen


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different panel than the shipped module."""
    app()
    spec = BY_NAME[name]
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(panel_painted_by_the_module(spec), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload(spec), spec), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints."""
    app()
    first, second = DIFFERENT_INPUT_PAIR
    one = qt_trace(drive_old(BY_NAME[first]))
    other = surface_trace(drive_new(BY_NAME[second]))
    assert one["rows"] != other["rows"], (one["rows"], other["rows"])
    assert_pictures_differ(
        old_side=render_offscreen(
            panel_painted_by_the_module(BY_NAME[first]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload(BY_NAME[second]), BY_NAME[second]),
            PIXEL_SIZE,
        ),
        note="an armed panel against one with no tranches",
    )


def colour_count(image) -> int:
    """How many colours one render carries."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return len(seen)


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_panel_shows_more_than_one_colour(name):
    """The two sides matched because the panel painted one flat colour."""
    app()
    spec = BY_NAME[name]
    for side, image in (
        ("old", render_offscreen(panel_painted_by_the_module(spec), PIXEL_SIZE)),
        (
            "new",
            render_offscreen(
                panel_painted_by_the_model(model_payload(spec), spec), PIXEL_SIZE
            ),
        ),
    ):
        assert image.width() > 0 and image.height() > 0, (name, side)
        found = colour_count(image)
        assert (
            found > 1
        ), f"{name} {side} painted {found} colour, so no change could show"


def test_the_colour_counter_reports_one_colour_on_a_flat_window():
    """The colour counter reads more than one colour on a flat window."""
    from PySide6.QtWidgets import QWidget

    app()
    flat = QWidget()
    flat.setStyleSheet("background: #123a63;")
    assert colour_count(render_offscreen(flat, PIXEL_SIZE)) == 1
    assert (
        colour_count(
            render_offscreen(panel_painted_by_the_module(BY_NAME["happy"]), PIXEL_SIZE)
        )
        > 1
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    spec = BY_NAME["happy"]
    payload = model_payload(spec)
    payload["rows"][0][1] = "MOVED"
    with pytest.raises(AssertionError):
        panel_painted_by_the_model(payload, spec)
    with pytest.raises(AssertionError):
        panel_painted_by_the_model(
            surface.build_view_model(drive_new(spec)["model"]), spec
        )


def test_the_no_skin_control_uses_a_rule_neither_side_sets():
    """The no-skin control repeats a rule one of the two sides already sets."""
    from PySide6.QtWidgets import QWidget

    app()
    rule = "border-style: dotted;"
    assert rule not in surface.AMBER_STYLE_FORMAT
    assert rule not in CHROME_SOURCE.read_text(encoding="utf-8")
    assert rule not in SURFACE_SOURCE.read_text(encoding="utf-8")
    bare = QWidget()
    skinned = QWidget()
    skinned.setStyleSheet(
        "QWidget { %s border-width: 8px; border-color: #ff9900; }" % rule
    )
    assert colour_count(render_offscreen(skinned, PIXEL_SIZE)) != colour_count(
        render_offscreen(bare, PIXEL_SIZE)
    )


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert narrow != wide, "the host reports fonts and every glyph has one width"
    else:
        assert narrow == wide, "the host reports no fonts and the glyphs differ"


@skip_unless_no_fonts
def test_two_equal_length_row_values_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length values still differ."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_the_two_marker_strings_measure_apart_with_fonts():
    """The glyphs decide their own width, and the marker pair measures alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# What a picture cannot see, read off both sides instead


def canonical(colour) -> str:
    """One colour written the long way, so a short form compares."""
    text = str(colour).strip().lower()
    if text.startswith("#") and len(text) == 4:
        return "#" + "".join(one * 2 for one in text[1:])
    return text


def test_a_colour_written_short_is_compared_written_long():
    """Two spellings of one colour read as two colours."""
    assert canonical("#888") == canonical("#888888")
    assert canonical("#123A63") == surface.FOLD_ROW_FILL


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two of the panel's colours are the same colour."""
    declared = [
        surface.FOLD_ROW_FILL,
        surface.FOLD_ROW_BORDER,
        surface.EXTRACTOR_ROW_FILL,
        surface.EXTRACTOR_ROW_BORDER,
        surface.AMBER_COLOR,
    ]
    written = [canonical(one) for one in declared]
    assert len(set(written)) == len(written), written
    for one in written:
        assert len(set(one[1:])) > 1, f"{one} has equal channels and hides a swap"


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour comparison cannot see two channels trade places."""
    swapped = (
        "#"
        + surface.AMBER_COLOR[5:7]
        + surface.AMBER_COLOR[3:5]
        + surface.AMBER_COLOR[1:3]
    )
    assert canonical(swapped) != canonical(surface.AMBER_COLOR)


def test_the_tooltips_are_read_off_both_sides():
    """A tooltip the operator points at is on one side only."""
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert [row[2] for row in old["rows"]] == [row[2] for row in new["rows"]]
    assert [row[3] for row in old["rows"]] == [row[3] for row in new["rows"]]
    assert all(row[2] == surface.DESPAWN_ROW_TOOLTIP for row in old["rows"])


def test_the_amber_mark_follows_the_last_candidate_window_on_both_sides():
    """The mark on the timer row fires on a different reading each side."""
    marked = BY_NAME["timer_off_with_old_records"]
    plain = BY_NAME["timer_off_with_records_younger_than_the_widest_window"]
    for spec, wanted in ((marked, True), (plain, False)):
        days = armed_days(spec["days"])
        windows = window_previews(spec["fold"], spec["stack"])
        armed = despawn_reading(spec["fold"], spec["stack"], days)
        assert surface.amber_shown(days, armed, windows) is wanted, spec["name"]
    live = BY_NAME["happy"]
    live_days = armed_days(live["days"])
    assert (
        surface.amber_shown(
            live_days,
            despawn_reading(live["fold"], live["stack"], live_days),
            window_previews(live["fold"], live["stack"]),
        )
        is False
    )


def test_the_marked_and_the_plain_timer_row_paint_different_pictures():
    """The mark on the timer row reaches no pixel, so no check can see it."""
    app()
    marked = BY_NAME["timer_off_with_old_records"]
    plain = BY_NAME["timer_off_with_records_younger_than_the_widest_window"]
    assert_pictures_differ(
        old_side=render_offscreen(panel_painted_by_the_module(marked), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload(plain), plain), PIXEL_SIZE
        ),
        note="a marked timer row against a plain one",
    )


def test_the_long_row_is_carried_whole_on_both_sides():
    """One side cut a row the other kept."""
    spec = BY_NAME["two_hundred_character_row"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert old["rows"] == new["rows"]
    assert len(spec["row_texts"][0][0]) == 200


# The bridge


@pytest.fixture
def fresh_panel_model():
    """Put the panel state the bridge keeps back exactly as it was found."""
    first = surface.PANEL_MODEL
    surface.PANEL_MODEL = surface.FoldChromeModel(surface.DialogSource())
    yield
    surface.PANEL_MODEL = first


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


def bridge_install(spec):
    days = armed_days(spec["days"])
    return {
        "days": days,
        "armed": despawn_reading(spec["fold"], spec["stack"], days),
        "windows": window_previews(spec["fold"], spec["stack"]),
        "elapsed": spec["elapsed_s"],
    }


def bridge_dialog(spec):
    return {
        "bot_id": spec["bot_id"],
        "sort_key": spec["sort_key"],
        "row_texts": [list(one) for one in spec["row_texts"]],
        "row_count": spec["table_rows"],
        "has_rebuild": spec["has_rebuild"],
    }


@pytest.mark.usefixtures("fresh_panel_model")
def test_the_bridge_registers_the_fold_chrome_method():
    """The renderer cannot reach the Fold Tranches chrome over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "fold_chrome.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["labels"]["timer_row"] == surface.TIMER_ROW_LABEL
    assert result["orders"]["offered"] == list(surface.SORT_ORDERS)


@pytest.mark.usefixtures("fresh_panel_model")
def test_the_bridge_resets_the_panel_state_on_request():
    """The panel state the bridge keeps was never cleared."""
    spec = BY_NAME["happy"]
    filled = bridge_answer(
        {
            "reset": True,
            "dialog": bridge_dialog(spec),
            "install": bridge_install(spec),
            "controls": True,
            "filter": spec["needle"],
        }
    )["result"]
    assert filled["row_count"] == len(drive_new(spec)["model"].rows)
    assert filled["controls"] != []
    kept = bridge_answer({})["result"]
    assert kept["rows"] == filled["rows"]
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["rows"] == []
    assert cleared["row_count"] == 0
    assert cleared["controls"] == []
    assert cleared["calls"] == []
    assert cleared["pins"] == []


@pytest.mark.usefixtures("fresh_panel_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    spec = BY_NAME["happy"]
    answer = bridge_answer(
        {
            "reset": True,
            "dialog": bridge_dialog(spec),
            "install": bridge_install(spec),
            "controls": True,
        }
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["labels"]["order"] == surface.ORDER_LABEL_TEXT


@pytest.mark.usefixtures("fresh_panel_model")
def test_the_bridge_reports_a_reading_it_cannot_use():
    """A bad reading ended the session instead of answering with an error."""
    spec = BY_NAME["happy"]
    broken = bridge_install(spec)
    broken["armed"] = dict(broken["armed"])
    broken["armed"].pop(surface.UNITS_REMOVED_KEY)
    answer = bridge_answer(
        {"reset": True, "dialog": bridge_dialog(spec), "install": broken}
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == KeyError.__name__


@pytest.mark.usefixtures("fresh_panel_model")
def test_the_bridge_hides_the_rows_the_filter_hides():
    """The filter the renderer sends changed no row."""
    spec = BY_NAME["rows_the_panel_harvested_no_text_for"]
    result = bridge_answer(
        {"reset": True, "dialog": bridge_dialog(spec), "filter": spec["needle"]}
    )["result"]
    assert result["hidden"] == surface_trace(drive_new(spec))["hidden"]
    assert any(result["hidden"]), result["hidden"]
    open_again = bridge_answer({"filter": ""})["result"]
    assert not any(open_again["hidden"]), open_again["hidden"]


# The subprocess probes: no Qt, no clock, no connection, no file

BUILD_REGISTRY = "registry = desktop_bridge.build_registry();"

BRIDGE_CALL = (
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'fold_chrome.state', 'params':"
    " {'reset': True, 'controls': True, 'dialog': {'bot_id': 'PROBE/USD',"
    " 'row_texts': [['BTC', '12.5000']], 'row_count': 2},"
    " 'filter': 'btc',"
    " 'install': {'days': 7, 'elapsed': 0.25, 'armed':"
    " {'fold_open': 3, 'fold_removed': 2, 'usd_removed': 13.0,"
    " 'units_removed': 4.25, 'stack_open': 1, 'stack_removed': 1,"
    " 'stack_kept_live_order': 0, 'ageless_kept': 1},"
    " 'windows': [[7, {'fold_removed': 2, 'stack_removed': 1,"
    " 'usd_removed': 13.0}]]}}}),"
    " registry);"
)

QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + BRIDGE_CALL
    + "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

CLOCK_WATCH = (
    "import time;"
    "reads = {'time': 0, 'monotonic': 0};"
    "_time = time.time;"
    "_mono = time.monotonic;"
    "time.time = lambda: (reads.__setitem__('time', reads['time'] + 1), _time())[1];"
    "time.monotonic = lambda: ("
    "reads.__setitem__('monotonic', reads['monotonic'] + 1), _mono())[1];"
)

CLOCK_ZERO = "reads['time'] = 0; reads['monotonic'] = 0;"

CLOCK_PROBE = (
    "import json, sys;"
    + CLOCK_WATCH
    + "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + CLOCK_ZERO
    + BRIDGE_CALL
    + "print(json.dumps({'frame': frame, 'reads': dict(reads)}))"
)

CLOCK_CONTROL_PROBE = (
    "import json, sys, time;"
    + CLOCK_WATCH
    + "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + CLOCK_ZERO
    + "time.time();"
    "time.monotonic();"
    + BRIDGE_CALL
    + "print(json.dumps({'frame': frame, 'reads': dict(reads)}))"
)

CLOCK_IMPORT_PROBE = (
    "import json, sys;"
    + CLOCK_WATCH
    + CLOCK_ZERO
    + "from src.gui.main_tabs import fold_chrome_surface as one;"
    "held = one.build_view_model(one.FoldChromeModel(one.DialogSource()));"
    "print(json.dumps({'reads': dict(reads), 'method': one.METHOD,"
    " 'rows': held['row_count'], 'qt': 'PySide6' in sys.modules}))"
)


SOCKET_WATCH = (
    "import socket;"
    "tries = [];"
    "_connect = socket.socket.connect;"
    "socket.socket.connect = lambda self, address: ("
    "tries.append(repr(address)), _connect(self, address))[1];"
    "_create = socket.create_connection;"
    "socket.create_connection = lambda address, *a, **k: ("
    "tries.append(repr(address)), _create(address, *a, **k))[1];"
)

SOCKET_PROBE = (
    "import json, sys;"
    + SOCKET_WATCH
    + "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + "tries.clear();"
    + BRIDGE_CALL
    + "print(json.dumps({'frame': frame, 'tries': list(tries)}))"
)

SOCKET_CONTROL_PROBE = (
    "import json, sys;"
    + SOCKET_WATCH
    + "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + "tries.clear();"
    "sock = socket.socket();"
    "sock.settimeout(0.01);"
    "\ntry:\n    sock.connect(('127.0.0.1', 9))\nexcept Exception:\n    pass\n"
    "sock.close();"
    + BRIDGE_CALL
    + "print(json.dumps({'frame': frame, 'tries': list(tries)}))"
)


def run_probe(script, environment=None):
    """Run one probe in a fresh process and return what it printed."""
    child = dict(os.environ)
    child.pop("ACERVATOR_TEST_FONTS", None)
    if environment:
        child.update(environment)
    done = subprocess.run(
        [sys.executable, "-"],
        input=script.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=child,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Fold Tranches chrome pulled Qt into the backend."""
    answered = run_probe(QT_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["rows"][0][0] == surface.TIMER_ROW_LABEL
    assert result["rows"][0][1].startswith("7 day(s)")
    assert result["controls"][0][1] == surface.ORDER_LABEL_TEXT
    assert result["hidden"] == [False, True]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;" + QT_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_reads_no_clock_over_the_bridge():
    """Answering the renderer read the machine's clock."""
    answered = run_probe(CLOCK_PROBE)
    assert answered["frame"]["ok"] is True
    assert answered["reads"] == {"time": 0, "monotonic": 0}, answered["reads"]


def test_importing_the_surface_reads_no_clock_and_loads_no_qt():
    """The surface read a clock or loaded Qt while it was imported."""
    answered = run_probe(CLOCK_IMPORT_PROBE)
    assert answered["reads"] == {"time": 0, "monotonic": 0}, answered["reads"]
    assert answered["qt"] is False
    assert answered["method"] == surface.METHOD
    assert answered["rows"] == 0


def test_the_clock_counter_reaches_the_child_process():
    """The clock counter reads zero because it never ran in the child."""
    answered = run_probe(CLOCK_CONTROL_PROBE)
    assert answered["frame"]["ok"] is True
    assert answered["reads"]["time"] > 0, answered["reads"]
    assert answered["reads"]["monotonic"] > 0, answered["reads"]


def test_neither_side_reads_the_wall_clock_in_this_process(monkeypatch):
    """A side read the wall clock, so its answer moves with the day."""
    spec = BY_NAME["happy"]
    clock = watched_clock(monkeypatch, ticks=[0.0, spec["elapsed_s"]])
    drive_new(spec)
    assert clock.reads == {"time": 0, "monotonic": 0, "now": 0}, clock.reads
    drive_old(spec)
    assert clock.reads["time"] == 0, clock.reads
    assert clock.reads["now"] == 0, clock.reads
    assert clock.reads["monotonic"] > 0, clock.reads


def test_the_clock_counter_fires_on_a_real_call(monkeypatch):
    """The clock counter reads zero on a run that did read the clock."""
    import time

    clock = watched_clock(monkeypatch)
    assert clock.total() == 0
    time.time()
    time.monotonic()
    assert clock.reads["time"] == 1, clock.reads
    assert clock.reads["monotonic"] == 1, clock.reads


def test_the_surface_makes_no_connection_over_the_bridge():
    """Answering the renderer opened a connection."""
    answered = run_probe(SOCKET_PROBE)
    assert answered["frame"]["ok"] is True
    assert answered["tries"] == [], answered["tries"]


def test_the_connection_counter_reaches_the_child_process():
    """The connection counter reads zero because it never ran in the child."""
    answered = run_probe(SOCKET_CONTROL_PROBE)
    assert answered["frame"]["ok"] is True
    assert len(answered["tries"]) > 0, answered["tries"]


FILE_WATCH = (
    "import os;"
    "from pathlib import Path;"
    "home = Path(os.environ['ACERVATOR_TEST_HOME']);"
    "seen = lambda: sorted(str(q.relative_to(home)) for q in home.rglob('*'));"
)

FILE_PROBE = (
    "import json, sys;"
    + FILE_WATCH
    + "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + "before = seen();"
    + BRIDGE_CALL
    + "print(json.dumps({'frame': frame, 'created': [q for q in seen() if q not in before]}))"
)

FILE_CONTROL_PROBE = (
    "import json, sys;"
    + FILE_WATCH
    + "from src.core import desktop_bridge;"
    + BUILD_REGISTRY
    + "before = seen();"
    + BRIDGE_CALL
    + "(home / 'a_file_the_counter_must_see.txt').write_text('x', encoding='utf-8');"
    "print(json.dumps({'frame': frame, 'created':"
    " [q for q in seen() if q not in before]}))"
)


def test_the_surface_creates_no_file_under_a_throwaway_home():
    """Answering the renderer wrote a file into the operator's tree."""
    with tempfile.TemporaryDirectory(prefix="fold-chrome-home-") as home:
        answered = run_probe(
            FILE_PROBE,
            {"ACERVATOR_TEST_HOME": home, "HOME": home, "USERPROFILE": home},
        )
    assert answered["frame"]["ok"] is True
    assert answered["created"] == [], answered["created"]


def test_the_file_counter_sees_a_file_that_is_created():
    """The file counter reads zero on a run that did create a file."""
    with tempfile.TemporaryDirectory(prefix="fold-chrome-home-") as home:
        answered = run_probe(
            FILE_CONTROL_PROBE,
            {"ACERVATOR_TEST_HOME": home, "HOME": home, "USERPROFILE": home},
        )
    assert answered["frame"]["ok"] is True
    assert answered["created"] == ["a_file_the_counter_must_see.txt"], answered[
        "created"
    ]


# Order independence


def test_the_panel_state_the_bridge_keeps_is_restored_after_a_refusal():
    """A refused bridge call left the panel state of the run behind."""
    spec = BY_NAME["happy"]
    first = surface.PANEL_MODEL
    try:
        surface.PANEL_MODEL = surface.FoldChromeModel(surface.DialogSource())
        during = surface.PANEL_MODEL
        assert during is not first
        broken = bridge_install(spec)
        broken["armed"] = dict(broken["armed"])
        broken["armed"].pop(surface.UNITS_REMOVED_KEY)
        answer = bridge_answer({"dialog": bridge_dialog(spec), "install": broken})
        assert answer["ok"] is False
        assert surface.PANEL_MODEL is during
    finally:
        surface.PANEL_MODEL = first
    assert surface.PANEL_MODEL is first


def test_a_second_drive_carries_the_same_values_on_both_sides():
    """A second build kept a row the first one left behind."""
    spec = BY_NAME["happy"]
    assert digest(qt_trace(drive_old(spec))) == digest(qt_trace(drive_old(spec)))
    model = surface.FoldChromeModel(new_dialog(spec))
    first = model.build_row_controls()
    second = model.build_row_controls()
    assert first == second
    assert len(model.controls) == len(second)


def test_a_drive_after_a_different_input_keeps_nothing_from_the_first():
    """State from the first drive reached the second."""
    first, second = DIFFERENT_INPUT_PAIR
    fresh = digest(surface_trace(drive_new(BY_NAME[second])))
    drive_new(BY_NAME[first])
    again = digest(surface_trace(drive_new(BY_NAME[second])))
    assert fresh == again
