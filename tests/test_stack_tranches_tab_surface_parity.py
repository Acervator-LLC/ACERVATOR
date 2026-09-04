"""The Qt Stack Tranches tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different row, a different
count, a different number format, a different button, a different
message box, a different refusal or a different step order than
``StackTranchesTabMixin`` builds on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox as QtMessageBox

from src.gui.main_tabs import stack_tranches_tab_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_pictures_differ,
    assert_pictures_match,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "stack_tranches_tab.py"
SURFACE_SOURCE = (
    REPO_ROOT / "src" / "gui" / "main_tabs" / "stack_tranches_tab_surface.py"
)

NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"
NESTED_METHOD_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_NAMESAKE = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (980, 640)
SKIN_CONTROL_RULE = "QGroupBox { border: 3px solid #7a1414; background: #201038; }"
HOST_ACCESSIBLE_NAME = "Stack Tranches parity dialog"

# The button and icon values come off Qt, never typed: the shipped
# tab ORs two of them together, which no stand-in value supports.
YES_FROM_QT = QtMessageBox.Yes
CANCEL_FROM_QT = QtMessageBox.Cancel
WARNING_FROM_QT = QtMessageBox.Warning

MODEL_STATE_FIELDS = (
    "boxes",
    "calls",
    "cancelled_count",
    "clear_button_enabled",
    "clear_button_text",
    "counters_button_enabled",
    "counters_button_text",
    "created_lifetime",
    "detail_rows",
    "detail_shown",
    "detail_styles",
    "detail_title",
    "discarded_lifetime",
    "droppable",
    "empty_shown",
    "filled_count",
    "forms_configured",
    "live_order_count",
    "outcome",
    "pending_count",
    "pending_size_total",
    "pending_size_unreadable",
    "refresh_status",
    "reset_ts",
    "settled_lines",
    "summary_rows",
    "summary_styles",
)


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    load_run_fonts()
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


_alive: list = []


def hold(widget):
    """Keep `widget` alive for the run so no read reaches a freed object."""
    _alive.append(widget)
    return widget


# Nothing here reaches outside this process


@pytest.fixture(autouse=True)
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    Each test is given its own counter, so the number never depends on
    what ran before it.
    """
    attempted: list = []

    def refuse(address):
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *_found, **_named):
        return refuse(address)

    def watched_connect_ex(self, address, *_found, **_named):
        return refuse(address)

    def watched_create(address, *_found, **_named):
        return refuse(address)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", watched_connect_ex)
    monkeypatch.setattr(socket, "create_connection", watched_create)
    yield attempted


# The bot and the dialog seams, as the test owns them. The Qt tab is
# driven with these; the surface is driven with its own. Neither side
# reads the other's.


class Config:
    """The bot config the tab reads its symbol from."""

    def __init__(self, symbol):
        self.symbol = symbol


class Bot:
    """The bot the Qt tab reads its stack ledger and counters from."""

    def __init__(
        self,
        tranches=None,
        created=0,
        discarded=0,
        reset_ts=0.0,
        symbol="",
        clear_report=None,
        counters_report=None,
        clear_raises=None,
        counters_raises=None,
        supports_clear=True,
        supports_counters=True,
    ):
        self.config = Config(symbol)
        self._stack_tranches = list(tranches or [])
        self._stack_created = created
        self._stack_discarded = discarded
        self._stack_counters_reset_ts = reset_ts
        self.clear_report = clear_report or {}
        self.counters_report = counters_report or {}
        self.clear_raises = clear_raises
        self.counters_raises = counters_raises
        self.cleared_with: list = []
        self.counters_cleared_with: list = []
        if supports_clear:
            self.clear_stack_tranches = self._discard
        if supports_counters:
            self.clear_stack_lifetime_counters = self._zero

    def _discard(self, reason=""):
        self.cleared_with.append(reason)
        if self.clear_raises is not None:
            raise self.clear_raises
        return self.clear_report

    def _zero(self, reason=""):
        self.counters_cleared_with.append(reason)
        if self.counters_raises is not None:
            raise self.counters_raises
        return self.counters_report


class BoxRecorder:
    """A stand-in for the message box the two clear paths raise.

    Records every box and answers the confirm with the answer the
    scenario names. Fails loudly on a call it was not built for, so a
    misused stub cannot pass as a quiet one.
    """

    Warning = WARNING_FROM_QT
    Critical = QtMessageBox.Critical
    Information = QtMessageBox.Information
    Yes = YES_FROM_QT
    Cancel = CANCEL_FROM_QT

    seen: list = []
    parents: list = []
    answer = CANCEL_FROM_QT

    def __init__(self, parent=None):
        self.parent = parent
        self._icon = None
        self._title = ""
        self._text = ""
        self._buttons = None
        self._default = None

    @classmethod
    def information(cls, parent, title, text, *found, **named):
        cls.parents.append(parent)
        cls.seen.append({"icon": "information", "title": title, "text": text})
        return cls.Yes

    @classmethod
    def warning(cls, parent, title, text, *found, **named):
        cls.parents.append(parent)
        cls.seen.append({"icon": "warning", "title": title, "text": text})
        return cls.Yes

    @classmethod
    def critical(cls, parent, title, text, *found, **named):
        cls.parents.append(parent)
        cls.seen.append({"icon": "critical", "title": title, "text": text})
        return cls.Yes

    def setIcon(self, icon):
        self._icon = icon

    def setWindowTitle(self, title):
        self._title = title

    def setText(self, text):
        self._text = text

    def setStandardButtons(self, buttons):
        self._buttons = buttons

    def setDefaultButton(self, button):
        self._default = button

    def exec(self):
        BoxRecorder.parents.append(self.parent)
        BoxRecorder.seen.append(
            {"icon": "warning_dialog", "title": self._title, "text": self._text}
        )
        return BoxRecorder.answer


class Saver:
    """The fleet save the two clear paths run before they rebuild."""

    def __init__(self, saved=True, why=""):
        self.saved = saved
        self.why = why
        self.asked: list = []

    def __call__(self, what):
        self.asked.append(what)
        return (self.saved, self.why)


def host_class():
    """The dialog the tab lives in, holding only what the mixin needs."""
    from PySide6.QtWidgets import QWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.gui.live_settings.stack_tranches_tab import StackTranchesTabMixin

    class Host(StackTranchesTabMixin, QWidget):
        _format_age = staticmethod(BotLiveSettingsDialog._format_age)

        def __init__(self, bot, saver=None):
            super().__init__()
            self.setAccessibleName(HOST_ACCESSIBLE_NAME)
            self._bot = bot
            self._saver = saver or Saver()
            self.forms: list = []

        def _configure_form(self, form):
            self.forms.append(form)
            BotLiveSettingsDialog._configure_form(self, form)

        def _save_fleet_state_now(self, what):
            return self._saver(what)

        def _wrap_scrollable(self, content):
            return BotLiveSettingsDialog._wrap_scrollable(self, content)

    return Host


# The inputs. One scenario drives both sides.


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's pair"
WRONG_CAPITALS = "PeNdInG"

HUGE_INT_UNDER = 2**1023
HUGE_INT_OVER = 2**1023 + 1


def tranche(**named):
    """One stack tranche with every key the panel reads."""
    fields = {
        "index": 0,
        "price": 61234.5,
        "size": 0.0123,
        "visible": True,
        "status": "pending",
        "fill_price": None,
        "opened_ts": 1_755_000_000.0,
    }
    fields.update(named)
    return fields


TRANCHES_HAPPY = [
    tranche(),
    tranche(
        index=1,
        price=62000.0,
        size=0.5,
        visible=False,
        status="filled",
        fill_price=61999.5,
        opened_ts=1_754_900_000.0,
    ),
    tranche(
        index=2,
        price=63000.0,
        size=1.0,
        visible=False,
        status="cancelled",
        fill_price=0.0,
        opened_ts=0,
    ),
]

TRANCHES_GROWN = [
    tranche(index=7, price=0.00012, size=987654.321, status="filled", fill_price=1.5),
    tranche(
        index=8,
        price=99999.5,
        size=55.5,
        visible=False,
        status="pending",
        opened_ts=1_754_000_000.0,
        order_id="live-1",
    ),
]

NOW_TS = 1_755_600_000.0


def scenario(name, **named):
    """One driving set: the bot readings, the save and the click."""
    spec = {
        "name": name,
        "tranches": TRANCHES_HAPPY,
        "created": 5,
        "discarded": 2,
        "reset_ts": 0.0,
        "symbol": "BTC/USD",
        "clear_report": {"count": 3, "size": 1.5123, "kept_live_order": 0},
        "counters_report": {"cleared": 7, "before": {"created": 5, "discarded": 2}},
        "clear_raises": None,
        "counters_raises": None,
        "supports_clear": True,
        "supports_counters": True,
        "saved": True,
        "save_why": "",
        "answer": "cancel",
        "now_ts": NOW_TS,
    }
    spec.update(named)
    return spec


SCENARIOS = [
    scenario("happy"),
    scenario("no_tranches", tranches=[], created=0, discarded=0),
    scenario("no_tranches_after_a_reset", tranches=[], created=0, reset_ts=NOW_TS),
    scenario("zero_everywhere", tranches=[tranche(index=0, price=0.0, size=0.0)]),
    scenario(
        "negative_everywhere",
        tranches=[tranche(index=-4, price=-61234.5, size=-0.5, opened_ts=-1.0)],
    ),
    scenario(
        "a_thousand_million",
        tranches=[tranche(price=1e9, size=1e9, fill_price=1e9)],
        created=1_000_000_000,
    ),
    scenario(
        "one_billionth",
        tranches=[tranche(price=1e-9, size=1e-9, fill_price=1e-9)],
    ),
    scenario("unicode_symbol", symbol=UNICODE_TEXT),
    scenario("unicode_status", tranches=[tranche(status=UNICODE_TEXT)]),
    scenario("long_status", tranches=[tranche(status=LONG_TEXT)]),
    scenario("markup_status", tranches=[tranche(status=MARKUP_TEXT)]),
    scenario("apostrophe_symbol", symbol=APOSTROPHE_TEXT),
    scenario("newline_symbol", symbol=NEWLINE_TEXT),
    scenario("wrong_capitals_status", tranches=[tranche(status=WRONG_CAPITALS)]),
    scenario("number_where_text_belongs", tranches=[tranche(status=7)]),
    scenario("text_where_a_number_belongs", tranches=[tranche(size="0.5", price="x")]),
    scenario(
        "infinity",
        tranches=[
            tranche(
                index=float("inf"),
                price=float("inf"),
                size=float("inf"),
                fill_price=float("inf"),
                opened_ts=float("inf"),
            )
        ],
    ),
    scenario(
        "minus_infinity",
        tranches=[
            tranche(
                index=float("-inf"),
                price=float("-inf"),
                size=float("-inf"),
                fill_price=float("-inf"),
                opened_ts=float("-inf"),
            )
        ],
    ),
    scenario(
        "not_a_number",
        tranches=[
            tranche(
                index=float("nan"),
                price=float("nan"),
                size=float("nan"),
                fill_price=float("nan"),
                opened_ts=float("nan"),
            )
        ],
    ),
    scenario(
        "huge_whole_number_under_the_limit",
        tranches=[tranche(price=HUGE_INT_UNDER, size=HUGE_INT_UNDER)],
    ),
    scenario(
        "huge_whole_number_over_the_limit",
        tranches=[tranche(price=HUGE_INT_OVER, size=HUGE_INT_OVER)],
    ),
    scenario("a_tranche_with_no_parent", tranches=[{}]),
    scenario("a_stored_true_where_a_quantity_belongs", tranches=[tranche(size=True)]),
    scenario(
        "a_stored_true_in_every_number_column",
        tranches=[
            tranche(index=True, price=True, size=True, fill_price=True, opened_ts=True)
        ],
    ),
    scenario("a_ratio_out_of_range", tranches=TRANCHES_HAPPY, created=1, discarded=0),
    scenario("a_ratio_in_the_red", tranches=TRANCHES_HAPPY, created=9, discarded=0),
    scenario("a_ratio_in_the_amber", tranches=TRANCHES_HAPPY, created=2, discarded=0),
    scenario(
        "a_ratio_in_the_green",
        tranches=[
            tranche(status="filled", fill_price=1.0),
            tranche(status="filled", fill_price=2.0),
            tranche(status="filled", fill_price=3.0),
            tranche(index=3, status="pending"),
        ],
        created=4,
    ),
    scenario(
        "a_value_the_venue_would_reject",
        tranches=[tranche(price=0.0, size=-1.0, fill_price=-1.0)],
    ),
    scenario("a_resting_order_is_kept", tranches=TRANCHES_GROWN, created=4),
    scenario("no_timestamp_on_a_pending_tranche", tranches=[tranche(opened_ts=None)]),
    scenario("an_unreadable_pending_size", tranches=[tranche(size=float("nan"))]),
    scenario("counters_cleared_but_tranches_stand", created=0, reset_ts=NOW_TS),
    scenario("nothing_discarded_lifetime", discarded=0),
]

REFUSING_SCENARIOS = ()

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}


CLEAR_STEPS = [
    scenario("clear_declined", answer="cancel"),
    scenario("clear_confirmed", answer="yes"),
    scenario("clear_saved_nothing", answer="yes", saved=False, save_why="OSError: x"),
    scenario(
        "clear_refused_by_the_bot",
        answer="yes",
        clear_raises=RuntimeError("the venue said no"),
    ),
    scenario(
        "clear_refused_with_another_type",
        answer="yes",
        clear_raises=ValueError("not a number"),
    ),
    scenario("clear_unsupported", answer="yes", supports_clear=False),
    scenario("clear_nothing_to_discard", tranches=[], answer="yes"),
    scenario("clear_only_resting_orders", tranches=TRANCHES_GROWN[1:], answer="yes"),
]

COUNTER_STEPS = [
    scenario("counters_declined", answer="cancel"),
    scenario("counters_confirmed", answer="yes"),
    scenario(
        "counters_saved_nothing", answer="yes", saved=False, save_why="OSError: y"
    ),
    scenario(
        "counters_refused_by_the_bot",
        answer="yes",
        counters_raises=RuntimeError("the venue said no"),
    ),
    scenario(
        "counters_refused_with_another_type",
        answer="yes",
        counters_raises=KeyError("before"),
    ),
    scenario("counters_unsupported", answer="yes", supports_counters=False),
    scenario("counters_already_zero", created=0, discarded=0, answer="yes"),
    scenario("counters_with_no_standing_tranche", tranches=[], answer="yes"),
]

CLEAR_STEP_NAMES = [spec["name"] for spec in CLEAR_STEPS]
COUNTER_STEP_NAMES = [spec["name"] for spec in COUNTER_STEPS]
STEP_BY_NAME = {spec["name"]: spec for spec in CLEAR_STEPS + COUNTER_STEPS}


# Driving the two sides


def old_bot(spec):
    return Bot(
        tranches=spec["tranches"],
        created=spec["created"],
        discarded=spec["discarded"],
        reset_ts=spec["reset_ts"],
        symbol=spec["symbol"],
        clear_report=spec["clear_report"],
        counters_report=spec["counters_report"],
        clear_raises=spec["clear_raises"],
        counters_raises=spec["counters_raises"],
        supports_clear=spec["supports_clear"],
        supports_counters=spec["supports_counters"],
    )


def new_model(spec):
    bot = surface.BotSource(
        tranches=spec["tranches"],
        created=spec["created"],
        discarded=spec["discarded"],
        reset_ts=spec["reset_ts"],
        symbol=spec["symbol"],
        clear_report=spec["clear_report"],
        counters_report=spec["counters_report"],
        clear_raises=spec["clear_raises"],
        counters_raises=spec["counters_raises"],
        supports_clear=spec["supports_clear"],
        supports_counters=spec["supports_counters"],
    )
    saver = surface.StateSaver(saved=spec["saved"], why=spec["save_why"])
    return surface.StackTranchesTabModel(bot, saver, surface.TabHost())


class FrozenClock:
    """A clock that answers one epoch second, and counts who asked."""

    def __init__(self, at):
        self.at = at
        self.asked = 0

    def __call__(self):
        self.asked += 1
        return self.at


def drive_old(spec, monkeypatch):
    """Build the Qt tab against the scenario's own clock reading."""
    app()
    import time as time_module

    clock = FrozenClock(spec["now_ts"])
    monkeypatch.setattr(time_module, "time", clock)
    bot = old_bot(spec)
    host = hold(host_class()(bot, Saver(spec["saved"], spec["save_why"])))
    tab = hold(host._create_stack_tranches_tab())
    return {"tab": tab, "host": host, "bot": bot, "clock": clock}


def drive_new(spec):
    """Build the surface model against the scenario's own epoch second."""
    model = new_model(spec)
    model.build(spec["now_ts"])
    return {"model": model}


# Reading the two sides. Neither reader touches a style, a palette, a
# brush or a property on a live object: the skin is proved by rendering.


def summary_box(tab):
    return tab.layout().itemAt(0).widget()


def button_row(tab):
    return tab.layout().itemAt(1).layout()


def detail_box(tab):
    from PySide6.QtWidgets import QGroupBox

    holder = tab.layout().itemAt(2).widget()
    return holder if isinstance(holder, QGroupBox) else None


def empty_label(tab):
    from PySide6.QtWidgets import QGroupBox, QLabel

    holder = tab.layout().itemAt(2).widget()
    return (
        holder
        if isinstance(holder, QLabel) and not isinstance(holder, QGroupBox)
        else None
    )


def layout_order(layout):
    """The class of each item the layout holds, in the order it was added."""
    order = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        inner = item.layout()
        if widget is not None:
            order.append(type(widget).__name__)
        elif inner is not None:
            order.append(type(inner).__name__)
        else:
            order.append("stretch")
    return order


def qt_trace(driven):
    """Every value the Qt tab shows, as plain data."""
    from PySide6.QtWidgets import QFormLayout

    tab = driven["tab"]
    form = summary_box(tab).layout()
    rows = []
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.ItemRole.LabelRole).widget()
        field = form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
        rows.append([label.text(), field.text()])
    row_layout = button_row(tab)
    clear_btn = row_layout.itemAt(0).widget()
    counters_btn = row_layout.itemAt(1).widget()
    empty = empty_label(tab)
    detail = detail_box(tab)
    detail_rows = []
    detail_title = ""
    header_text = ""
    if detail is not None:
        detail_title = detail.title()
        inner = detail.layout()
        header_text = inner.itemAt(0).widget().text()
        detail_rows = [
            inner.itemAt(index).widget().text() for index in range(1, inner.count())
        ]
    return {
        "accessible_name": tab.accessibleName(),
        "spacing_px": tab.layout().spacing(),
        "layout_order": layout_order(tab.layout()),
        "summary_group_title": summary_box(tab).title(),
        "summary_rows": rows,
        "forms_configured": len(driven["host"].forms),
        "clear_button": {
            "text": clear_btn.text(),
            "enabled": clear_btn.isEnabled(),
            "tooltip": clear_btn.toolTip(),
        },
        "counters_button": {
            "text": counters_btn.text(),
            "enabled": counters_btn.isEnabled(),
            "tooltip": counters_btn.toolTip(),
        },
        "empty_shown": empty is not None,
        "empty_text": empty.text() if empty is not None else None,
        "empty_word_wrap": empty.wordWrap() if empty is not None else None,
        "detail_shown": detail is not None,
        "detail_title": detail_title,
        "header_text": header_text,
        "detail_rows": detail_rows,
    }


def surface_trace(driven):
    """The same values, read off the surface's own model."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    order = ["QGroupBox", "QHBoxLayout"]
    order.append("QLabel" if payload["empty_label"]["shown"] else "QGroupBox")
    order.append("stretch")
    return {
        "accessible_name": payload["accessible_name"],
        "spacing_px": payload["container"]["spacing_px"],
        "layout_order": order,
        "summary_group_title": payload["summary_group"]["title"],
        "summary_rows": payload["summary_rows"],
        "forms_configured": payload["summary_group"]["forms_configured"],
        "clear_button": {
            "text": payload["clear_button"]["text"],
            "enabled": payload["clear_button"]["enabled"],
            "tooltip": payload["clear_button"]["tooltip"],
        },
        "counters_button": {
            "text": payload["counters_button"]["text"],
            "enabled": payload["counters_button"]["enabled"],
            "tooltip": payload["counters_button"]["tooltip"],
        },
        "empty_shown": payload["empty_label"]["shown"],
        "empty_text": (
            payload["empty_label"]["text"] if payload["empty_label"]["shown"] else None
        ),
        "empty_word_wrap": (
            payload["empty_label"]["word_wrap"]
            if payload["empty_label"]["shown"]
            else None
        ),
        "detail_shown": payload["detail"]["shown"],
        "detail_title": (
            payload["detail"]["title"] if payload["detail"]["shown"] else ""
        ),
        "header_text": (
            payload["detail"]["header_text"] if payload["detail"]["shown"] else ""
        ),
        "detail_rows": payload["detail"]["rows"],
    }


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_tab(name, monkeypatch):
    """The view model describes a different tab than the Qt mixin builds."""
    spec = BY_NAME[name]
    old = qt_trace(drive_old(spec, monkeypatch))
    new = surface_trace(drive_new(spec))
    for key in sorted(old):
        assert new[key] == old[key], "%s: %s\nold %r\nnew %r" % (
            name,
            key,
            old[key],
            new[key],
        )
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_sample_hashes_are_reported(name, monkeypatch, record_property):
    """The hash of each side is not carried out of the run."""
    spec = BY_NAME[name]
    old = digest(qt_trace(drive_old(spec, monkeypatch)))
    new = digest(surface_trace(drive_new(spec)))
    record_property("old_side", old)
    record_property("new_side", new)
    assert old == new, name


def test_the_hash_tells_two_different_answers_apart(monkeypatch):
    """The hash returns one value whatever the tab shows.

    Two genuinely different real inputs, one driven through each side,
    in both directions. A pass means the comparison reports.
    """
    happy = BY_NAME["happy"]
    grown = BY_NAME["a_resting_order_is_kept"]
    assert happy["tranches"] != grown["tranches"]
    old_happy = digest(qt_trace(drive_old(happy, monkeypatch)))
    new_grown = digest(surface_trace(drive_new(grown)))
    assert old_happy != new_grown
    old_grown = digest(qt_trace(drive_old(grown, monkeypatch)))
    new_happy = digest(surface_trace(drive_new(happy)))
    assert old_grown != new_happy
    assert old_happy == new_happy
    assert old_grown == new_grown


def test_the_same_input_twice_gives_one_answer(monkeypatch):
    """A second build of one input answered differently."""
    spec = BY_NAME["happy"]
    first = digest(qt_trace(drive_old(spec, monkeypatch)))
    second = digest(qt_trace(drive_old(spec, monkeypatch)))
    assert first == second
    first_model = digest(surface_trace(drive_new(spec)))
    second_model = digest(surface_trace(drive_new(spec)))
    assert first_model == second_model
    assert first_model == first


def test_every_scenario_name_is_driven():
    """A scenario sits in the table and no test drives it."""
    assert len(SCENARIO_NAMES) == len(set(SCENARIO_NAMES))
    assert len(CLEAR_STEP_NAMES) == len(set(CLEAR_STEP_NAMES))
    assert len(COUNTER_STEP_NAMES) == len(set(COUNTER_STEP_NAMES))
    assert set(STEP_BY_NAME) == set(CLEAR_STEP_NAMES) | set(COUNTER_STEP_NAMES)
    assert REFUSING_SCENARIOS == ()


# The number columns, read as their own text


def detail_cells(line):
    """One rendered detail line split back into its seven columns."""
    return [cell.strip() for cell in line.split("|")]


NUMBER_COLUMN_CASES = [
    ("a_stored_true_in_every_number_column", (0, 1, 2, 5, 6)),
    ("not_a_number", (0, 1, 2, 5, 6)),
    ("infinity", (0, 1, 2, 5, 6)),
    ("minus_infinity", (0, 1, 2, 5, 6)),
    ("huge_whole_number_over_the_limit", (1, 2)),
]


@pytest.mark.parametrize("name,refused", NUMBER_COLUMN_CASES)
def test_a_refused_number_column_prints_a_dash_on_both_sides(
    name, refused, monkeypatch
):
    """A refused stored number printed a quantity instead of a dash."""
    spec = BY_NAME[name]
    old = qt_trace(drive_old(spec, monkeypatch))
    new = surface_trace(drive_new(spec))
    assert old["detail_rows"] == new["detail_rows"], name
    cells = detail_cells(old["detail_rows"][0])
    for column in refused:
        assert cells[column] == surface.NO_VALUE, (name, column, cells)


def test_the_number_column_reader_sees_a_real_number(monkeypatch):
    """The column reader returns a dash whatever the row shows."""
    old = qt_trace(drive_old(BY_NAME["happy"], monkeypatch))
    cells = detail_cells(old["detail_rows"][0])
    assert cells[0] == "0"
    assert cells[1] == "$61234.50000000"
    assert cells[2] == "0.012300"
    assert surface.NO_VALUE not in cells[:3]


def test_the_lifetime_opened_counter_takes_a_stored_true_on_both_sides(monkeypatch):
    """The two sides read the lifetime opened counter under one rule.

    The shipped tab reads it with a bare int, so a stored True prints
    the count 1. The surface must print what the tab prints, whatever
    that is; a surface that refused it would describe a tab nobody
    built.
    """
    spec = scenario("opened_counter_is_true", created=True, discarded=0)
    old = qt_trace(drive_old(spec, monkeypatch))
    new = surface_trace(drive_new(spec))
    assert old["summary_rows"] == new["summary_rows"]
    opened = dict(old["summary_rows"])[surface.OPENED_ROW_LABEL]
    assert opened == "1"


@pytest.mark.parametrize(
    "stored,error",
    [(float("nan"), ValueError), (float("inf"), OverflowError), ("abc", ValueError)],
)
def test_the_lifetime_opened_counter_raises_the_same_type_on_both_sides(
    stored, error, monkeypatch
):
    """The two sides refuse a stored counter with different errors."""
    spec = scenario("opened_counter_refuses", created=stored, discarded=0)
    with pytest.raises(error) as from_old:
        drive_old(spec, monkeypatch)
    with pytest.raises(error) as from_new:
        drive_new(spec)
    assert type(from_old.value) is type(from_new.value)
    assert type(from_old.value) is error


def test_the_counter_refusal_control_admits_a_real_count(monkeypatch):
    """The refusal check reports whatever the counter holds."""
    spec = scenario("opened_counter_is_a_count", created=11, discarded=0)
    old = qt_trace(drive_old(spec, monkeypatch))
    assert dict(old["summary_rows"])[surface.OPENED_ROW_LABEL] == "11"


# The step sequences, including the ones that refuse part way


@pytest.fixture
def message_box_seam(monkeypatch):
    """Give the Qt side its own message box and put the real one back.

    ``QMessageBox`` is one name for the whole process and the shipped
    clear paths import it inside the call, so the swap is watched during
    the drive and proved restored after it, refusal included.
    """
    from PySide6 import QtWidgets

    original = QtWidgets.QMessageBox
    BoxRecorder.seen = []
    BoxRecorder.parents = []
    BoxRecorder.answer = BoxRecorder.Cancel
    monkeypatch.setattr(QtWidgets, "QMessageBox", BoxRecorder)
    assert QtWidgets.QMessageBox is BoxRecorder
    yield BoxRecorder
    monkeypatch.undo()
    assert QtWidgets.QMessageBox is original


def step_old(spec, which, seam, monkeypatch):
    """Run one clear path on the Qt side and report the boxes it raised."""
    from PySide6 import QtWidgets

    driven = drive_old(spec, monkeypatch)
    seam.seen = []
    seam.answer = seam.Yes if spec["answer"] == "yes" else seam.Cancel
    host = driven["host"]
    host._tabs = None
    host._stack_tab_page = None
    assert QtWidgets.QMessageBox is BoxRecorder
    if which == "clear":
        host._on_clear_stack_tranches()
    else:
        host._on_clear_stack_lifetime_counters()
    assert QtWidgets.QMessageBox is BoxRecorder
    return {"boxes": list(seam.seen), "bot": driven["bot"], "host": host}


def step_new(spec, which):
    """Run the same clear path on the surface."""
    driven = drive_new(spec)
    model = driven["model"]
    model.host = surface.TabHost(installed=False)
    answer = surface.YES_ANSWER if spec["answer"] == "yes" else surface.NO_ANSWER
    if which == "clear":
        model.clear_tranches(answer)
    else:
        model.clear_lifetime_counters(answer)
    return {"model": model}


@pytest.mark.parametrize("name", CLEAR_STEP_NAMES)
def test_the_clear_path_raises_the_same_boxes_on_both_sides(
    name, message_box_seam, monkeypatch
):
    """A clear step showed the operator a different message."""
    spec = STEP_BY_NAME[name]
    old = step_old(spec, "clear", message_box_seam, monkeypatch)
    new = step_new(spec, "clear")
    assert new["model"].state.boxes == old["boxes"], name
    assert digest(new["model"].state.boxes) == digest(old["boxes"]), name


@pytest.mark.parametrize("name", COUNTER_STEP_NAMES)
def test_the_counter_path_raises_the_same_boxes_on_both_sides(
    name, message_box_seam, monkeypatch
):
    """A counter step showed the operator a different message."""
    spec = STEP_BY_NAME[name]
    old = step_old(spec, "counters", message_box_seam, monkeypatch)
    new = step_new(spec, "counters")
    assert new["model"].state.boxes == old["boxes"], name
    assert digest(new["model"].state.boxes) == digest(old["boxes"]), name


REFUSING_STEPS = {
    "clear_refused_by_the_bot": ("clear", RuntimeError, surface.STEP_CALL_FAILED),
    "clear_refused_with_another_type": ("clear", ValueError, surface.STEP_CALL_FAILED),
    "counters_refused_by_the_bot": (
        "counters",
        RuntimeError,
        surface.STEP_CALL_FAILED,
    ),
    "counters_refused_with_another_type": (
        "counters",
        KeyError,
        surface.STEP_CALL_FAILED,
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSING_STEPS))
def test_a_step_that_refuses_keeps_what_it_recorded_first(
    name, message_box_seam, monkeypatch, record_property
):
    """A refusal part way through wiped the steps taken before it."""
    which, error, refusing_step = REFUSING_STEPS[name]
    spec = STEP_BY_NAME[name]
    old = step_old(spec, which, message_box_seam, monkeypatch)
    new = step_new(spec, which)
    calls = new["model"].state.calls
    index = calls.index(refusing_step)
    record_property("step_index", index)
    record_property("step_name", refusing_step)
    record_property("refusal_type", error.__name__)
    before_the_refusal = calls[:index]
    assert before_the_refusal[-1] == surface.STEP_CONFIRM, calls
    for kept in (surface.STEP_READ_BOT, surface.STEP_SUMMARY, surface.STEP_BUTTONS):
        assert kept in before_the_refusal, (kept, calls)
    assert calls[index] == refusing_step, calls
    assert calls[index + 1 :] == [], calls
    assert surface.STEP_SETTLED not in calls, calls
    assert new["model"].state.outcome == surface.OUTCOME_FAILED
    assert len(new["model"].state.boxes) == 2, new["model"].state.boxes
    assert new["model"].state.boxes[0]["icon"] == surface.QUESTION_ICON
    assert new["model"].state.boxes[1]["icon"] == surface.CRITICAL_ICON
    assert old["boxes"] == new["model"].state.boxes
    raised = spec["clear_raises"] or spec["counters_raises"]
    assert type(raised) is error


def test_the_refusal_type_is_read_off_the_shipped_side(message_box_seam, monkeypatch):
    """The refusal type is typed into the test rather than measured."""
    spec = STEP_BY_NAME["clear_refused_by_the_bot"]
    bot = old_bot(spec)
    with pytest.raises(Exception) as reported:
        bot.clear_stack_tranches(reason="probe")
    assert type(reported.value) is type(spec["clear_raises"])
    new_bot = surface.BotSource(clear_raises=spec["clear_raises"])
    with pytest.raises(Exception) as from_surface:
        new_bot.clear_stack_tranches(reason="probe")
    assert type(from_surface.value) is type(reported.value)


def test_a_step_that_does_not_refuse_records_the_whole_run(
    message_box_seam, monkeypatch
):
    """The recorder reports a refusal on a run that did not refuse."""
    spec = STEP_BY_NAME["clear_confirmed"]
    new = step_new(spec, "clear")
    calls = new["model"].state.calls
    assert surface.STEP_CALL_FAILED not in calls
    assert surface.STEP_CLEARED in calls
    assert new["model"].state.outcome == surface.OUTCOME_CLEARED
    old = step_old(spec, "clear", message_box_seam, monkeypatch)
    assert old["bot"].cleared_with == [surface.CLEAR_REASON]
    assert new["model"].bot.cleared_with == [surface.CLEAR_REASON]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("clear_declined", surface.OUTCOME_DECLINED),
        ("clear_confirmed", surface.OUTCOME_CLEARED),
        ("clear_unsupported", surface.OUTCOME_UNSUPPORTED),
        ("clear_nothing_to_discard", surface.OUTCOME_NOTHING_TO_DISCARD),
        ("clear_refused_by_the_bot", surface.OUTCOME_FAILED),
        ("counters_declined", surface.OUTCOME_DECLINED),
        ("counters_confirmed", surface.OUTCOME_COUNTERS_CLEARED),
        ("counters_unsupported", surface.OUTCOME_UNSUPPORTED),
        ("counters_already_zero", surface.OUTCOME_ALREADY_ZERO),
        ("counters_refused_by_the_bot", surface.OUTCOME_FAILED),
    ],
)
def test_each_step_reports_the_outcome_it_reached(name, expected):
    """A step reported an outcome other than the path it took."""
    which = "clear" if name.startswith("clear") else "counters"
    new = step_new(STEP_BY_NAME[name], which)
    assert new["model"].state.outcome == expected, name


def test_every_declared_outcome_is_reached_by_a_step():
    """The surface declares an outcome no step ever reaches."""
    reached = set()
    for name in CLEAR_STEP_NAMES:
        reached.add(step_new(STEP_BY_NAME[name], "clear")["model"].state.outcome)
    for name in COUNTER_STEP_NAMES:
        reached.add(step_new(STEP_BY_NAME[name], "counters")["model"].state.outcome)
    assert reached == set(surface.OUTCOMES), sorted(set(surface.OUTCOMES) - reached)


def test_every_branch_marker_fires():
    """A branch the surface declares is never taken."""
    seen = set()
    for spec in SCENARIOS:
        seen.update(drive_new(spec)["model"].state.calls)
    for name in CLEAR_STEP_NAMES:
        seen.update(step_new(STEP_BY_NAME[name], "clear")["model"].state.calls)
    for name in COUNTER_STEP_NAMES:
        seen.update(step_new(STEP_BY_NAME[name], "counters")["model"].state.calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)


def test_the_branch_marker_reader_reports_a_branch_that_did_not_fire():
    """The marker reader reports every branch whatever ran."""
    only_empty = drive_new(BY_NAME["no_tranches"])["model"].state.calls
    assert surface.STEP_EMPTY in only_empty
    assert surface.STEP_DETAIL not in only_empty
    with_rows = drive_new(BY_NAME["happy"])["model"].state.calls
    assert surface.STEP_DETAIL in with_rows
    assert surface.STEP_EMPTY not in with_rows


# The settle lines and the refresh statuses


REFRESH_CASES = [
    ("no_tab", surface.TabHost(installed=False), surface.NO_TAB_INSTALLED),
    ("gone", surface.TabHost(index=-1), surface.TAB_GONE),
]


def test_the_refresh_reports_each_reason_it_could_not_rebuild():
    """A refresh that could not run reported that it had."""
    for name, host, expected in REFRESH_CASES:
        model = surface.StackTranchesTabModel(surface.BotSource(), None, host)
        assert model.refresh() == expected, name
    raised = surface.StackTranchesTabModel(
        surface.BotSource(), None, surface.TabHost(index_raises=RuntimeError("gone"))
    )
    assert raised.refresh() == surface.TAB_NOT_LOCATED_FORMAT.format(
        error="RuntimeError"
    )
    failing = surface.StackTranchesTabModel(
        surface.BotSource(), None, surface.TabHost(rebuild_raises=ValueError("no"))
    )
    assert failing.refresh() == surface.REBUILD_RAISED_FORMAT.format(
        error="ValueError", detail="no"
    )
    working = surface.StackTranchesTabModel(
        surface.BotSource(), None, surface.TabHost()
    )
    assert working.refresh() == surface.REFRESHED


def test_the_refresh_puts_the_tab_back_where_it_was():
    """A refresh landed the tab at a different index or lost the front."""
    host = surface.TabHost(index=3, current=3, label="Stack Tranches")
    model = surface.StackTranchesTabModel(surface.BotSource(), None, host)
    assert model.refresh() == surface.REFRESHED
    assert host.removed == [3]
    assert host.inserted[0][0] == 3
    assert host.inserted[0][2] == "Stack Tranches"
    assert host.made_current == [3]
    assert host.deleted == [3]
    elsewhere = surface.TabHost(index=3, current=1)
    surface.StackTranchesTabModel(surface.BotSource(), None, elsewhere).refresh()
    assert elsewhere.made_current == []


SETTLE_CASES = [
    ("saved_and_rebuilt", True, "", surface.TabHost()),
    ("saved_but_not_rebuilt", True, "", surface.TabHost(installed=False)),
    ("rebuilt_but_not_saved", False, "OSError: disk", surface.TabHost()),
    (
        "neither",
        False,
        "OSError: disk",
        surface.TabHost(installed=False),
    ),
]


@pytest.mark.parametrize("name,saved,why,host", SETTLE_CASES)
def test_the_settle_lines_match_the_shipped_wording(name, saved, why, host):
    """A settle line told the operator something the tab does not."""
    model = surface.StackTranchesTabModel(
        surface.BotSource(), surface.StateSaver(saved, why), host
    )
    lines = model.settle_after_clear("Clear stack tranches")
    assert len(lines) == 2, name
    if host.installed:
        assert lines[0] == surface.REBUILT_LINE, name
    else:
        assert lines[0] == surface.NOT_REBUILT_LINE_FORMAT.format(
            refresh=surface.NO_TAB_INSTALLED
        ), name
    if saved:
        assert lines[1] == surface.SAVED_LINE, name
    else:
        assert lines[1] == surface.NOT_SAVED_LINE_FORMAT.format(why=why), name
    assert model.saver.asked == ["Clear stack tranches"], name


def test_the_settle_lines_reach_the_result_box(message_box_seam, monkeypatch):
    """The settle lines never reach the message the operator reads."""
    spec = STEP_BY_NAME["clear_saved_nothing"]
    new = step_new(spec, "clear")
    result = new["model"].state.boxes[-1]["text"]
    for line in new["model"].state.settled_lines:
        assert line in result
    assert "NOT SAVED TO DISK" in result
    old = step_old(spec, "clear", message_box_seam, monkeypatch)
    assert old["boxes"][-1]["text"] == result


# The enumeration: every item on the shipped side, and where it went


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
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


def source_classes(path) -> list:
    """Every class the source declares, one inside a method included."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def top_level_classes(path) -> list:
    """Only the classes at the top of the file."""
    return sorted(
        node.name for node in parsed(path).body if isinstance(node, ast.ClassDef)
    )


def source_functions(path) -> list:
    """Every function the source declares, nested ones included."""
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def signal_sites(path) -> list:
    """Every ``Signal()`` a class in `path` declares, as class.name."""
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if isinstance(statement, ast.Assign) and isinstance(
                statement.value, ast.Call
            ):
                if dotted(statement.value.func).endswith("Signal"):
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            found.append("%s.%s" % (node.name, target.id))
    return sorted(found)


def timer_builds(path) -> list:
    """Every ``QTimer(`` construction in `path`, read off the parsed file."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def timer_starts(path) -> list:
    """Every ``.start(`` call in `path`."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "start"
    ]


def thread_sites(path) -> list:
    """Every thread construction in `path`, built or started."""
    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            if name.endswith("QThread") or name.endswith("Thread"):
                found.append(name)
    return found


def bus_subscribes(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def bus_emits(path) -> list:
    """Every bus emit in `path`, under either name it is called by."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("emit", "publish")
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


SHIPPED_METHODS = {
    "_create_stack_tranches_tab": "StackTranchesTabModel.build",
    "_install_stack_tranches_tab": "StackTranchesTabModel.build",
    "_on_clear_stack_lifetime_counters": "StackTranchesTabModel.clear_lifetime_counters",
    "_on_clear_stack_tranches": "StackTranchesTabModel.clear_tranches",
    "_refresh_stack_tranches_tab": "StackTranchesTabModel.refresh",
    "_settle_after_stack_clear": "StackTranchesTabModel.settle_after_clear",
}

SURFACE_CLASSES = {
    "StackTranchesTabModel": "StackTranchesTabMixin",
    "TabState": "the values one build of the Qt tab puts on its widgets",
    "BotConfig": "the config StackTranchesTabMixin reads its symbol from",
    "BotSource": "the bot StackTranchesTabMixin reads its stack ledger from",
    "StateSaver": "_save_fleet_state_now, which the clear paths call",
    "TabHost": "the QTabWidget the refresh path removes and reinserts in",
}

SURFACE_MODEL_METHODS = (
    "__init__",
    "build",
    "clear_lifetime_counters",
    "clear_tranches",
    "refresh",
    "settle_after_clear",
)

QT_SIGNAL_NAMES = {
    "stack_clear_btn.clicked": "clear_button.clicked",
    "stack_counters_btn.clicked": "counters_button.clicked",
}
QT_TARGET_NAMES = {
    "self._on_clear_stack_tranches": "clear_tranches",
    "self._on_clear_stack_lifetime_counters": "clear_lifetime_counters",
}


def test_the_connect_sets_match():
    """The Qt tab connects a signal the surface names no action for."""
    sites = connect_sites(TAB_SOURCE)
    translated = {
        QT_SIGNAL_NAMES[signal]: QT_TARGET_NAMES[target] for signal, target in sites
    }
    assert translated == surface.ACTIONS
    assert len(surface.ACTIONS) == len(sites)


def test_the_connect_reader_finds_every_real_site():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites(TAB_SOURCE)
    assert ("stack_clear_btn.clicked", "self._on_clear_stack_tranches") in sites
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert len(connect_sites(BUS_NEIGHBOUR)) > len(sites)


def test_the_class_reader_sees_a_class_declared_inside_a_method():
    """A top-level-only reader counts no class the file hides in a method."""
    hidden = source_classes(NESTED_CLASS_NEIGHBOUR)
    assert hidden, NESTED_CLASS_NEIGHBOUR.name
    assert top_level_classes(NESTED_CLASS_NEIGHBOUR) == []
    assert "StockMainWindow" in hidden
    assert source_classes(TAB_SOURCE) == ["StackTranchesTabMixin"]


def test_the_function_reader_sees_a_method_of_a_nested_class():
    """The function reader misses a method the file nests inside a class."""
    nested = source_functions(NESTED_METHOD_NEIGHBOUR)
    assert len(nested) > len(source_functions(TAB_SOURCE))
    assert "_IVPPrivacyDot" in source_classes(NESTED_METHOD_NEIGHBOUR)
    assert source_functions(TAB_SOURCE) == sorted(SHIPPED_METHODS)


def test_every_shipped_method_has_a_counterpart():
    """The shipped tab gained or lost a class or a method."""
    from src.gui.live_settings import stack_tranches_tab as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["StackTranchesTabMixin"], classes
    methods = sorted(
        name
        for name, value in vars(shipped.StackTranchesTabMixin).items()
        if callable(value) and not name.startswith("__")
    )
    assert methods == sorted(SHIPPED_METHODS), methods
    for counterpart in set(SHIPPED_METHODS.values()):
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_a_signal_is_counted_as_a_signal_and_not_as_a_method():
    """A signal is callable, so a loose counter reads it as a method."""
    declared = signal_sites(SIGNAL_NEIGHBOUR)
    assert "ModeCard.clicked" in declared
    assert "clicked" not in source_functions(SIGNAL_NEIGHBOUR)
    assert signal_sites(TAB_SOURCE) == []
    assert list(surface.SIGNALS) == []
    from src.gui.live_settings.stack_tranches_tab import StackTranchesTabMixin

    assert StackTranchesTabMixin.__annotations__ == {
        "_bot": "Any",
        "_configure_form": "Callable[..., Any]",
        "_format_age": "Callable[..., Any]",
        "_save_fleet_state_now": "Callable[..., Any]",
        "_wrap_scrollable": "Callable[..., Any]",
    }
    for annotated in StackTranchesTabMixin.__annotations__:
        assert annotated not in vars(StackTranchesTabMixin)


def test_the_tab_builds_and_starts_no_timer_and_both_counters_can_report():
    """The tab runs a timer the surface declares no delay for."""
    assert timer_builds(TAB_SOURCE) == []
    assert timer_starts(TAB_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_builds(TIMER_NEIGHBOUR)) >= 1, "the build counter reports nothing"
    assert (
        len(timer_starts(NESTED_METHOD_NEIGHBOUR)) >= 1
    ), "the start counter reports nothing"
    assert len(timer_builds(NESTED_METHOD_NEIGHBOUR)) >= 1


def test_the_timer_counter_is_pointed_at_a_path_and_not_a_basename():
    """Two files share a basename and the counter read the wrong one."""
    assert TIMER_NEIGHBOUR.name == TIMER_NAMESAKE.name
    assert TIMER_NEIGHBOUR != TIMER_NAMESAKE
    assert len(timer_builds(TIMER_NEIGHBOUR)) >= 1
    assert timer_builds(TIMER_NAMESAKE) == []


def test_the_tab_neither_subscribes_nor_emits_and_both_counters_can_report():
    """The tab talks on a bus topic the surface names none of."""
    assert bus_subscribes(TAB_SOURCE) == []
    assert bus_emits(TAB_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    assert surface.BUS_EMITS == ()
    listened = bus_subscribes(BUS_NEIGHBOUR)
    spoken = bus_emits(BUS_NEIGHBOUR)
    assert len(listened) >= 2, "the subscribe counter reports nothing"
    assert len(spoken) >= 2, "the emit counter reports nothing"
    assert "wire.created" in listened
    assert "wire.created" in spoken


def test_the_tab_starts_no_thread_and_the_counter_can_report():
    """The tab starts a worker the surface names none of."""
    assert thread_sites(TAB_SOURCE) == []
    assert surface.THREADS == ()
    assert (
        len(thread_sites(BUS_NEIGHBOUR)) + len(thread_sites(NESTED_METHOD_NEIGHBOUR))
        >= 0
    )
    from src.gui import crypto_news_ticker

    assert len(thread_sites(Path(crypto_news_ticker.__file__))) >= 1


def test_the_surface_names_what_each_of_its_classes_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    model_methods = sorted(
        name
        for name, value in vars(surface.StackTranchesTabModel).items()
        if callable(value) and (not name.startswith("_") or name == "__init__")
    )
    assert model_methods == sorted(SURFACE_MODEL_METHODS), model_methods


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "_on_clear_stack_tranches" in SHIPPED_METHODS
    assert "InventedModel" not in SURFACE_CLASSES
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        surface.StackTranchesTabModel.invented_method


def test_every_state_field_the_model_holds_is_named():
    """The model grew a built value nothing in this file knows about."""
    fresh = surface.TabState()
    assert sorted(vars(fresh)) == sorted(MODEL_STATE_FIELDS), sorted(vars(fresh))
    built = new_model(BY_NAME["happy"])
    built.build(NOW_TS)
    assert sorted(vars(built.state)) == sorted(MODEL_STATE_FIELDS)


def test_a_second_build_inherits_nothing_from_the_first():
    """A rebuilt tab kept a row the build before it produced."""
    model = new_model(BY_NAME["happy"])
    model.build(NOW_TS)
    assert model.state.detail_rows
    model.bot = surface.BotSource(tranches=[], created=0, discarded=0)
    model.build(NOW_TS)
    assert model.state.detail_rows == []
    assert model.state.empty_shown is True
    assert model.state.detail_shown is False
    assert model.state.calls.count(surface.STEP_READ_BOT) == 1


# The completeness check


PAYLOAD_KEYS = {
    "ACCESSIBLE_NAME": "accessible_name",
    "ACTIONS": "actions",
    "AGE_DAYS_FORMAT": "formats.age_days",
    "AGE_HOURS_FORMAT": "formats.age_hours",
    "AGE_MINUTES_FORMAT": "formats.age_minutes",
    "AGE_SECONDS_DAY": "thresholds.age_day_s",
    "AGE_SECONDS_FORMAT": "formats.age_seconds",
    "AGE_SECONDS_HOUR": "thresholds.age_hour_s",
    "AGE_SECONDS_MINUTE": "thresholds.age_minute_s",
    "BLANK_LINE": "texts.blank_line",
    "BODY_JOIN": "texts.body_join",
    "BUS_EMITS": "bus_emits",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CANCELLED_ROW_LABEL": "labels.cancelled",
    "CLEAR_BUTTON_COUNTED_FORMAT": "formats.clear_button_counted",
    "CLEAR_BUTTON_PLAIN_TEXT": "texts.clear_button_plain",
    "CLEAR_BUTTON_TOOLTIP": "clear_button.tooltip",
    "CLEAR_COUNTERS_ATTRIBUTE": "attributes.clear_counters",
    "CLEAR_FAILED_FORMAT": "formats.clear_failed",
    "CLEAR_REASON": "texts.clear_reason",
    "CLEAR_TRANCHES_ATTRIBUTE": "attributes.clear_tranches",
    "CLEAR_TRANCHES_TITLE": "titles.clear_tranches",
    "CLEAR_COUNTERS_TITLE": "titles.clear_counters",
    "CONFIRM_COUNTERS_FORMAT": "formats.confirm_counters",
    "CONFIRM_COUNTERS_NO_ORDER_TEXT": "texts.confirm_counters_no_order",
    "CONFIRM_DEFAULT_ANSWER": "answers.default",
    "CONFIRM_DISCARDED_LINE_FORMAT": "formats.confirm_discarded_line",
    "CONFIRM_DISCARD_FORMAT": "formats.confirm_discard",
    "CONFIRM_LIVE_NOTE_FORMAT": "formats.confirm_live_note",
    "CONFIRM_NO_ORDER_TEXT": "texts.confirm_no_order",
    "CONFIRM_OPENED_LINE_FORMAT": "formats.confirm_opened_line",
    "CONFIRM_STILL_HOLDS_FORMAT": "formats.confirm_still_holds",
    "CONFIRM_UNDONE_TEXT": "texts.confirm_undone",
    "CONTENT_MARGINS_SET": "container.margins_set",
    "CONTENT_SPACING_PX": "container.spacing_px",
    "COUNTERS_ALREADY_ZERO_TEXT": "texts.counters_already_zero",
    "COUNTERS_BOTH_ZERO_TEXT": "texts.counters_both_zero",
    "COUNTERS_BUTTON_COUNTED_FORMAT": "formats.counters_button_counted",
    "COUNTERS_BUTTON_PLAIN_TEXT": "texts.counters_button_plain",
    "COUNTERS_BUTTON_TOOLTIP": "counters_button.tooltip",
    "COUNTERS_KEPT_FORMAT": "formats.counters_kept",
    "COUNTERS_RESULT_FORMAT": "formats.counters_result",
    "COUNT_FORMAT": "formats.count",
    "CREATED_ATTRIBUTE": "attributes.created",
    "CRITICAL_ICON": "icons.critical",
    "DANGER_BUTTON_STYLE": "styles.danger_button",
    "DETAIL_GROUP_TITLE_FORMAT": "formats.detail_group_title",
    "DISCARDED_ATTRIBUTE": "attributes.discarded",
    "DISCARDED_RESULT_FORMAT": "formats.discarded_result",
    "DISCARDED_ROW_LABEL": "labels.discarded",
    "EMPTY_STYLE": "empty_label.style_sheet",
    "EMPTY_TEXT": "empty_label.text",
    "EMPTY_WORD_WRAP": "empty_label.word_wrap",
    "FILLED_ROW_LABEL": "labels.filled",
    "FILL_FORMAT": "formats.fill",
    "FILL_PRICE_KEY": "keys.fill_price",
    "FILL_RATIO_CLEARED_TEXT": "texts.ratio_cleared",
    "FILL_RATIO_FORMAT": "formats.fill_ratio",
    "FILL_RATIO_NEVER_OPENED_TEXT": "texts.ratio_never_opened",
    "FILL_RATIO_ROW_LABEL": "labels.fill_ratio",
    "HEADER_STYLE": "detail.header_style",
    "HEADER_TEXT": "detail.header_text",
    "INDEX_FORMAT": "formats.index",
    "INDEX_KEY": "keys.index",
    "INDEX_REFUSED_FORMAT": "formats.index_refused",
    "INFORMATION_ICON": "icons.information",
    "KEPT_LIVE_NOTE_FORMAT": "formats.kept_live_note",
    "KEPT_RESULT_FORMAT": "formats.kept_result",
    "METHOD": "method",
    "MODE_INVISIBLE": "texts.mode_invisible",
    "MODE_VISIBLE": "texts.mode_visible",
    "NOTHING_TO_DISCARD_TEXT": "texts.nothing_to_discard",
    "NOT_REBUILT_LINE_FORMAT": "formats.not_rebuilt_line",
    "NOT_SAVED_LINE_FORMAT": "formats.not_saved_line",
    "NO_CLEAR_SUPPORT_TEXT": "texts.no_clear_support",
    "NO_COUNTER_SUPPORT_TEXT": "texts.no_counter_support",
    "NO_PENDING_TEXT": "texts.no_pending",
    "NO_TAB_INSTALLED": "texts.no_tab_installed",
    "NO_TIMESTAMP_TEXT": "texts.no_timestamp",
    "NO_VALUE": "texts.no_value",
    "OLDEST_AGE_ROW_LABEL": "labels.oldest_age",
    "OPENED_ROW_LABEL": "labels.opened",
    "OPENED_TS_KEY": "keys.opened_ts",
    "ORDER_ID_KEY": "keys.order_id",
    "OUTCOMES": "outcomes",
    "PENDING_ROW_LABEL": "labels.pending",
    "PENDING_SIZE_FORMAT": "formats.pending_size",
    "PENDING_SIZE_ROW_LABEL": "labels.pending_size",
    "PENDING_SIZE_STYLE": "styles.pending_size",
    "PRICE_FORMAT": "formats.price",
    "PRICE_KEY": "keys.price",
    "PRICE_REFUSED_FORMAT": "formats.price_refused",
    "QUESTION_ICON": "icons.question",
    "RATIO_AMBER": "colours.ratio_amber",
    "RATIO_AMBER_BELOW": "thresholds.ratio_amber_below",
    "RATIO_GREEN": "colours.ratio_green",
    "RATIO_MIN_OPENED": "thresholds.ratio_min_opened",
    "RATIO_NO_STYLE": "styles.ratio_none",
    "RATIO_RED": "colours.ratio_red",
    "RATIO_RED_BELOW": "thresholds.ratio_red_below",
    "RATIO_STYLE_FORMAT": "formats.ratio_style",
    "REBUILD_RAISED_FORMAT": "formats.rebuild_raised",
    "REBUILT_LINE": "texts.rebuilt",
    "REFRESHED": "texts.refreshed",
    "REPORT_BEFORE_KEY": "keys.report_before",
    "REPORT_CLEARED_KEY": "keys.report_cleared",
    "REPORT_COUNT_KEY": "keys.report_count",
    "REPORT_CREATED_KEY": "keys.report_created",
    "REPORT_DISCARDED_KEY": "keys.report_discarded",
    "REPORT_KEPT_KEY": "keys.report_kept",
    "REPORT_SIZE_KEY": "keys.report_size",
    "RESET_TS_ATTRIBUTE": "attributes.reset_ts",
    "RESULT_JOIN": "texts.result_join",
    "ROW_BASE_STYLE": "styles.row_base",
    "ROW_CANCELLED_STYLE": "styles.row_cancelled",
    "ROW_FILLED_STYLE": "styles.row_filled",
    "ROW_FORMAT": "formats.row",
    "ROW_PLAIN_STYLE": "styles.row_plain",
    "SAVED_LINE": "texts.saved",
    "SIZE_FORMAT": "formats.size",
    "SIZE_KEY": "keys.size",
    "SIZE_REFUSED_FORMAT": "formats.size_refused",
    "STATUS_CANCELLED": "statuses.cancelled",
    "STATUS_FILLED": "statuses.filled",
    "STATUS_KEY": "keys.status",
    "STATUS_PENDING": "statuses.pending",
    "STATUS_UNKNOWN": "texts.status_unknown",
    "SUMMARY_FORM_CONFIGURED_BY_HOST": "summary_group.configured_by_host",
    "SUMMARY_GROUP_TITLE": "summary_group.title",
    "TAB_GONE": "texts.tab_gone",
    "TAB_LABEL": "tab_label",
    "TAB_NOT_LOCATED_FORMAT": "formats.tab_not_located",
    "THREADS": "threads",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TRANCHES_ATTRIBUTE": "attributes.tranches",
    "UNREADABLE_SUFFIX_FORMAT": "formats.unreadable_suffix",
    "VISIBLE_KEY": "keys.visible",
    "WARNING_ICON": "icons.warning",
    "YES_ANSWER": "answers.yes",
    "NO_ANSWER": "answers.no",
    "SIGNALS": "signals",
}

LIST_MEMBERS = {
    "OUTCOME_ALREADY_ZERO": "outcomes",
    "OUTCOME_CLEARED": "outcomes",
    "OUTCOME_COUNTERS_CLEARED": "outcomes",
    "OUTCOME_DECLINED": "outcomes",
    "OUTCOME_FAILED": "outcomes",
    "OUTCOME_NOTHING_TO_DISCARD": "outcomes",
    "OUTCOME_UNSUPPORTED": "outcomes",
    "STEP_BUTTONS": "call_names",
    "STEP_CALL_FAILED": "call_names",
    "STEP_CLEARED": "call_names",
    "STEP_CONFIRM": "call_names",
    "STEP_COUNTERS_CLEARED": "call_names",
    "STEP_COUNTERS_ZERO": "call_names",
    "STEP_DECLINED": "call_names",
    "STEP_DETAIL": "call_names",
    "STEP_EMPTY": "call_names",
    "STEP_NOTHING_TO_DISCARD": "call_names",
    "STEP_NO_CLEAR_SUPPORT": "call_names",
    "STEP_NO_COUNTER_SUPPORT": "call_names",
    "STEP_READ_BOT": "call_names",
    "STEP_SETTLED": "call_names",
    "STEP_SUMMARY": "call_names",
}

NOT_IN_THE_SNAPSHOT = {
    "PANE_MODEL": "test_the_bridge_resets_the_tab_state_on_request",
}

STATE_ONLY_KEYS = {
    "boxes",
    "calls",
    "clear_button",
    "counters_button",
    "counts",
    "detail",
    "empty_label",
    "outcome",
    "pending_size_total",
    "refresh_status",
    "reset_ts",
    "settled_lines",
    "summary_group",
    "summary_rows",
    "summary_styles",
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


def parsed_constant_names():
    """Every module-level name the surface file assigns, off the file."""
    found = set()
    for node in parsed(SURFACE_SOURCE).body:
        if isinstance(node, ast.Assign):
            found.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return {name for name in found if not name.startswith("_")}


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    model = new_model(BY_NAME["happy"])
    model.build(NOW_TS)
    payload = surface.build_view_model(model)
    unaccounted = []
    for name, value in surface_constants().items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == list(value), name
            else:
                assert carried == value, name
        elif name in LIST_MEMBERS:
            assert value in payload[LIST_MEMBERS[name]], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    model = new_model(BY_NAME["happy"])
    model.build(NOW_TS)
    payload = surface.build_view_model(model)
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= set(LIST_MEMBERS.values())
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    model = new_model(BY_NAME["happy"])
    model.build(NOW_TS)
    payload = surface.build_view_model(model)
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "HEADER_TEXT" in surface_constants()
    assert "ROW_FORMAT" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "StackTranchesTabModel" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "labels.invented")


def test_the_export_list_stays_complete_as_the_file_grows():
    """A value added to the surface reaches no list this file keeps.

    The names are counted twice, once off the parsed file and once off
    the imported module, so a value declared in either form is caught.
    Nothing here types a total: both counts come from the surface.
    """
    named = set(PAYLOAD_KEYS) | set(LIST_MEMBERS) | set(NOT_IN_THE_SNAPSHOT)
    running = set(surface_constants())
    on_disk = parsed_constant_names()
    callables = {
        name
        for name, value in vars(surface).items()
        if callable(value) and not name.startswith("_")
    }
    assert running == named, sorted(running ^ named)
    assert on_disk - callables == running, sorted((on_disk - callables) ^ running)
    assert len(named) == len(running) == len(on_disk - callables)


def test_the_export_reader_reports_a_name_only_one_form_declares():
    """The two readers agree because one of them sees nothing."""
    assert parsed_constant_names(), "the parsed reader found no names"
    assert surface_constants(), "the running reader found no names"
    assert "build_view_model" not in parsed_constant_names()
    assert "build_view_model" in vars(surface)
    assert "view_model" not in surface_constants()
    assert "StackTranchesTabModel" not in surface_constants()
    assert "METHOD" in parsed_constant_names()
    assert "METHOD" in surface_constants()


# The surface carries its own values


class MovedTokens:
    """A token table whose colours are unlike any the design system holds.

    Every channel of every value differs from the other two, so a
    channel swap cannot read as unchanged, and none of them appears in
    the real table. Both claims are measured below rather than assumed.
    """

    SUCCESS = "#100fef"
    ERROR = "#110fee"
    FOLD_RATIO_AMBER = "#120fed"
    SETTINGS_DANGER_SURFACE = "#130fec"
    TEXT_MUTED = "#140feb"
    BORDER_DISABLED = "#150fea"
    CARD_METRIC_LABEL = "#160fe9"
    TEXT_INFO_SOFT = "#170fe8"


def moved_token_values():
    """Every colour the moved table holds."""
    return [
        value
        for name, value in vars(MovedTokens).items()
        if not name.startswith("_") and isinstance(value, str)
    ]


def test_no_moved_token_is_a_colour_the_real_table_already_holds():
    """A moved token equals a real one, so the move reaches no pixel."""
    from src.gui import design_system

    real = {
        value.lower()
        for value in vars(design_system).values()
        if isinstance(value, str) and value.startswith("#")
    }
    assert len(real) > 1, "the real token reader found nothing"
    moved = moved_token_values()
    assert len(moved) == 8, moved
    assert [value for value in moved if value.lower() in real] == []
    assert len(set(moved)) == len(moved)


def test_no_moved_token_has_two_equal_channels():
    """A moved token repeats a channel, so a swap of two reads the same."""
    for value in moved_token_values():
        channels = [value[1:3], value[3:5], value[5:7]]
        assert len(set(channels)) == 3, value


def test_the_moved_token_control_reports_a_colour_the_real_table_holds():
    """The collision check passes whatever colour is put in the table."""
    from src.gui import design_system

    real = {
        value.lower()
        for value in vars(design_system).values()
        if isinstance(value, str) and value.startswith("#")
    }
    assert design_system.ERROR.lower() in real
    assert "#100fef" not in real


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_tab(monkeypatch):
    """The surface read its values off the tab it replaces.

    The shipped tab's token table is moved and both sides are rendered.
    The shipped side must paint a different picture, which is what
    proves the move reached a pixel; the surface must paint the picture
    it painted before. Nothing here reads a style, a palette or a brush
    off a live object.
    """
    app()
    from src.gui.live_settings import stack_tranches_tab as shipped

    first = shipped.ds
    spec = BY_NAME["happy"]
    before_style = surface.DANGER_BUTTON_STYLE
    before_empty = surface.EMPTY_STYLE
    plain_old = render_offscreen(
        widget_painted_by_the_tab(spec, monkeypatch), PIXEL_SIZE
    )
    plain_new = render_offscreen(
        widget_painted_by_the_model(model_payload(spec)), PIXEL_SIZE
    )
    assert_pictures_match(
        old_side=plain_old, new_side=plain_new, note="before the move"
    )

    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved_old = render_offscreen(
        widget_painted_by_the_tab(spec, monkeypatch), PIXEL_SIZE
    )
    assert_pictures_differ(
        old_side=plain_old,
        new_side=moved_old,
        note="the shipped tab follows its tokens",
    )
    moved_new = render_offscreen(
        widget_painted_by_the_model(model_payload(spec)), PIXEL_SIZE
    )
    assert_pictures_match(
        old_side=plain_new, new_side=moved_new, note="the surface kept its own tokens"
    )
    assert surface.DANGER_BUTTON_STYLE == before_style
    assert surface.EMPTY_STYLE == before_empty
    assert MovedTokens.SETTINGS_DANGER_SURFACE not in surface.DANGER_BUTTON_STYLE

    monkeypatch.undo()
    assert shipped.ds is first
    after = render_offscreen(widget_painted_by_the_tab(spec, monkeypatch), PIXEL_SIZE)
    assert_pictures_match(old_side=plain_old, new_side=after, note="after the move")


def test_the_surface_does_not_follow_a_tab_that_builds_nothing(monkeypatch):
    """The surface asked the shipped tab to build its controls."""
    app()
    from src.gui.live_settings import stack_tranches_tab as shipped

    first = shipped.StackTranchesTabMixin._create_stack_tranches_tab
    before = surface_trace(drive_new(BY_NAME["happy"]))
    monkeypatch.setattr(
        shipped.StackTranchesTabMixin,
        "_create_stack_tranches_tab",
        lambda self: None,
    )
    assert host_class()(old_bot(BY_NAME["happy"]))._create_stack_tranches_tab() is None
    again = surface_trace(drive_new(BY_NAME["happy"]))
    assert again == before
    assert again["detail_rows"], again
    monkeypatch.undo()
    assert shipped.StackTranchesTabMixin._create_stack_tranches_tab is first


def test_the_shipped_tab_writes_to_no_shared_table(monkeypatch):
    """The shipped tab changed something every later test would inherit."""
    app()
    from src.gui import design_system
    from src.gui.live_settings import stack_tranches_tab as shipped

    watched = (
        "SUCCESS",
        "ERROR",
        "FOLD_RATIO_AMBER",
        "SETTINGS_DANGER_SURFACE",
        "TEXT_MUTED",
        "BORDER_DISABLED",
        "CARD_METRIC_LABEL",
        "TEXT_INFO_SOFT",
    )
    before_tokens = {name: getattr(design_system, name) for name in watched}
    before_module = sorted(vars(shipped))
    drive_old(BY_NAME["happy"], monkeypatch)
    drive_old(BY_NAME["no_tranches"], monkeypatch)
    assert {name: getattr(design_system, name) for name in watched} == before_tokens
    assert sorted(vars(shipped)) == before_module
    assert shipped.ds is design_system


def test_neither_side_edits_the_tranche_it_is_handed(monkeypatch):
    """A build changed the bot's own tranche records."""
    app()
    rows = [dict(row) for row in TRANCHES_HAPPY]
    before = digest(rows)
    spec = scenario("handed_rows", tranches=rows)
    drive_old(spec, monkeypatch)
    assert digest(rows) == before, "the Qt tab edited what it was handed"
    drive_new(spec)
    assert digest(rows) == before, "the surface edited what it was handed"
    model = new_model(spec)
    model.build(NOW_TS)
    model.state.detail_rows.append("added by the test")
    assert digest(rows) == before


def test_the_edit_check_reports_a_row_that_was_changed():
    """The edit check reports nothing whatever a caller writes."""
    rows = [dict(row) for row in TRANCHES_HAPPY]
    before = digest(rows)
    rows[0]["size"] = 99.0
    assert digest(rows) != before


def test_neither_side_reads_the_clock(monkeypatch):
    """A side reached for the wall clock instead of the value it was given."""
    app()
    spec = BY_NAME["happy"]
    driven = drive_old(spec, monkeypatch)
    assert driven["clock"].asked == 1, "the shipped tab reads the clock once"
    import time as time_module

    def refuse():
        raise AssertionError("the surface may not read the clock")

    monkeypatch.setattr(time_module, "time", refuse)
    built = drive_new(spec)
    assert built["model"].state.detail_rows
    monkeypatch.undo()
    assert callable(time_module.time)


def test_the_clock_counter_reports_a_read():
    """The clock counter reports nothing whatever a side reads."""
    clock = FrozenClock(NOW_TS)
    assert clock.asked == 0
    assert clock() == NOW_TS
    assert clock.asked == 1


# The pictures


def model_payload(spec, monkeypatch=None):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(spec)["model"]))


def widget_painted_by_the_tab(spec, monkeypatch):
    """The tab the shipped Qt mixin builds, after the same driving."""
    return drive_old(spec, monkeypatch)["tab"]


def widget_painted_by_the_model(payload):
    """A tab built only from the payload, never from the shipped mixin."""
    payload = unaltered(payload)
    from PySide6.QtWidgets import (
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    app()
    screen = hold(QWidget())
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    outer.setSpacing(payload["container"]["spacing_px"])

    group = QGroupBox(payload["summary_group"]["title"])
    form = QFormLayout(group)
    BotLiveSettingsDialog._configure_form(screen, form)
    for (label, value), style in zip(
        payload["summary_rows"], payload["summary_styles"]
    ):
        field = QLabel(value)
        if style:
            field.setStyleSheet(style)
        form.addRow(label, field)
    outer.addWidget(group)

    row = QHBoxLayout()
    for declared in (payload["clear_button"], payload["counters_button"]):
        button = QPushButton(declared["text"])
        button.setEnabled(declared["enabled"])
        button.setToolTip(declared["tooltip"])
        button.setStyleSheet(declared["style_sheet"])
        row.addWidget(button)
    row.addStretch()
    outer.addLayout(row)

    if payload["empty_label"]["shown"]:
        empty = QLabel(payload["empty_label"]["text"])
        empty.setStyleSheet(payload["empty_label"]["style_sheet"])
        empty.setWordWrap(payload["empty_label"]["word_wrap"])
        outer.addWidget(empty)
        outer.addStretch()
        return screen

    detail = QGroupBox(payload["detail"]["title"])
    inner = QVBoxLayout(detail)
    header = QLabel(payload["detail"]["header_text"])
    header.setStyleSheet(payload["detail"]["header_style"])
    inner.addWidget(header)
    for text, style in zip(payload["detail"]["rows"], payload["detail"]["row_styles"]):
        line = QLabel(text)
        line.setStyleSheet(style)
        inner.addWidget(line)
    outer.addWidget(detail)
    outer.addStretch()
    return screen


PICTURE_SCENARIOS = [
    "happy",
    "no_tranches",
    "no_tranches_after_a_reset",
    "a_ratio_in_the_red",
    "a_ratio_in_the_green",
    "a_stored_true_in_every_number_column",
    "unicode_status",
    "negative_everywhere",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name, monkeypatch):
    """The surface painted a different tab than the shipped mixin."""
    app()
    spec = BY_NAME[name]
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    old_side = render_offscreen(
        widget_painted_by_the_tab(spec, monkeypatch), PIXEL_SIZE
    )
    new_side = render_offscreen(
        widget_painted_by_the_model(model_payload(spec)), PIXEL_SIZE
    )
    assert_picture_can_report(old_side, note="old side, " + note)
    assert_picture_can_report(new_side, note="new side, " + note)
    assert_pictures_match(old_side=old_side, new_side=new_side, note=note)


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_carry_one_skin(name, monkeypatch, record_property):
    """The two sides declare one look and paint two.

    Nothing here reads a style sheet, a palette or a brush off a live
    object: the answer comes from the pixels each render painted.
    """
    app()
    spec = BY_NAME[name]
    payload = model_payload(spec)
    assert_same_skin(
        build_old_side=lambda: widget_painted_by_the_tab(spec, monkeypatch),
        build_new_side=lambda: widget_painted_by_the_model(payload),
        size=PIXEL_SIZE,
        control_rule=SKIN_CONTROL_RULE,
        note=name,
    )
    record_property(
        "colours",
        colour_count(
            render_offscreen(widget_painted_by_the_tab(spec, monkeypatch), PIXEL_SIZE)
        ),
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_colour_count_of_each_state_is_reported(name, monkeypatch, record_property):
    """A state painted one colour and no comparison of it can report."""
    app()
    spec = BY_NAME[name]
    old_side = render_offscreen(
        widget_painted_by_the_tab(spec, monkeypatch), PIXEL_SIZE
    )
    new_side = render_offscreen(
        widget_painted_by_the_model(model_payload(spec)), PIXEL_SIZE
    )
    old_colours = assert_picture_can_report(old_side, note=name)
    new_colours = assert_picture_can_report(new_side, note=name)
    record_property("state", name)
    record_property("old_colours", old_colours)
    record_property("new_colours", new_colours)
    record_property("fonts", "real" if has_real_fonts() else "none")
    assert old_colours == new_colours, name


def test_the_picture_comparison_can_report_a_difference(monkeypatch):
    """The picture check passes whatever the second side paints."""
    app()
    happy = BY_NAME["happy"]
    other = BY_NAME["a_resting_order_is_kept"]
    assert happy["tranches"] != other["tranches"]
    assert_cases_paint_differently(
        old_side=render_offscreen(
            widget_painted_by_the_tab(happy, monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(other)), PIXEL_SIZE
        ),
        note="the happy ladder against the resting-order ladder",
    )
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_tab(other, monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(happy)), PIXEL_SIZE
        ),
        note="the other direction",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload(BY_NAME["happy"])
    payload["detail"]["rows"][0] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(
            surface.build_view_model(drive_new(BY_NAME["happy"])["model"])
        )


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert narrow != wide, "the host reports fonts and every glyph is one width"
    else:
        assert narrow == wide, "the host reports no fonts and glyphs have own widths"


@skip_unless_no_fonts
def test_two_equal_length_rows_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length rows still differ."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_two_equal_length_rows_measure_apart_with_fonts():
    """The glyphs decide their own width, and two rows still measure alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# What a picture cannot see, read off both sides instead


def test_the_values_no_picture_carries_are_read_off_both_sides(monkeypatch):
    """A value that reaches no pixel was left to the render to report."""
    app()
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec, monkeypatch))
    new = surface_trace(drive_new(spec))
    assert new["accessible_name"] == old["accessible_name"] == ""
    assert new["forms_configured"] == old["forms_configured"] == 1
    assert surface.SUMMARY_FORM_CONFIGURED_BY_HOST is True
    assert new["clear_button"]["tooltip"] == old["clear_button"]["tooltip"]
    assert new["counters_button"]["tooltip"] == old["counters_button"]["tooltip"]
    assert old["clear_button"]["tooltip"], "the shipped button carries no tooltip"


def box_of(layout):
    """One layout's four margins, as plain numbers."""
    margins = layout.contentsMargins()
    return [margins.left(), margins.top(), margins.right(), margins.bottom()]


def untouched_layout_margins():
    """The margins and spacing a fresh column layout starts with."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = hold(QWidget())
    plain = QVBoxLayout(holder)
    reading = (box_of(plain), plain.spacing())
    assert holder.layout() is plain
    return reading


def test_the_outer_layout_sets_no_margins_on_either_side(monkeypatch):
    """The tab set its own margins on one side and not on the other."""
    app()
    untouched, untouched_spacing = untouched_layout_margins()
    tab = widget_painted_by_the_tab(BY_NAME["happy"], monkeypatch)
    built = widget_painted_by_the_model(model_payload(BY_NAME["happy"]))
    for layout in (tab.layout(), built.layout()):
        assert box_of(layout) == untouched
        assert layout.spacing() == surface.CONTENT_SPACING_PX
    assert surface.CONTENT_MARGINS_SET is False
    assert untouched_spacing != surface.CONTENT_SPACING_PX


# The bridge


@pytest.fixture
def fresh_pane_model():
    """Put the tab state the bridge keeps back exactly as it was found."""
    first = surface.PANE_MODEL
    surface.PANE_MODEL = surface.StackTranchesTabModel()
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
    "tranches": TRANCHES_HAPPY,
    "created": 5,
    "discarded": 2,
    "symbol": "BTC/USD",
    "clear_report": {"count": 3, "size": 1.5123, "kept_live_order": 0},
    "counters_report": {"cleared": 7, "before": {"created": 5, "discarded": 2}},
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_stack_tranches_method():
    """The renderer cannot reach the Stack Tranches tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "stack_tranches_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    assert answer["result"]["detail"]["header_text"] == surface.HEADER_TEXT


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_tab_state_on_request():
    """The tab state the bridge keeps was never cleared."""
    filled = bridge_answer({"reset": True, "bot": BRIDGE_BOT, "now_ts": NOW_TS})[
        "result"
    ]
    assert filled["detail"]["row_count"] == 3
    assert filled["counts"]["created_lifetime"] == 5
    kept = bridge_answer({})["result"]
    assert kept["detail"]["row_count"] == 3
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["detail"]["row_count"] == 0
    assert cleared["detail"]["shown"] is False
    assert cleared["calls"] == []
    assert surface.PANE_MODEL is not None


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_runs_both_clear_paths():
    """A clear over the bridge reached no path at all."""
    cleared = bridge_answer(
        {
            "reset": True,
            "bot": BRIDGE_BOT,
            "now_ts": NOW_TS,
            "clear": True,
            "answer": surface.YES_ANSWER,
        }
    )["result"]
    assert cleared["outcome"] == surface.OUTCOME_CLEARED
    declined = bridge_answer(
        {
            "reset": True,
            "bot": BRIDGE_BOT,
            "now_ts": NOW_TS,
            "clear": True,
            "answer": surface.NO_ANSWER,
        }
    )["result"]
    assert declined["outcome"] == surface.OUTCOME_DECLINED
    counters = bridge_answer(
        {
            "reset": True,
            "bot": BRIDGE_BOT,
            "now_ts": NOW_TS,
            "clear_counters": True,
            "answer": surface.YES_ANSWER,
        }
    )["result"]
    assert counters["outcome"] == surface.OUTCOME_COUNTERS_CLEARED


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reset": True, "bot": BRIDGE_BOT, "now_ts": NOW_TS})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["summary_rows"][0] == [
        surface.PENDING_ROW_LABEL,
        "1",
    ]


# The surface answers with Qt absent, and reads nothing at import


BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'stack_tranches_tab.state',\n"
    "    'params': {'reset': True, 'now_ts': 1755600000.0, 'bot': {\n"
    "        'created': 5, 'discarded': 2, 'symbol': 'BTC/USD',\n"
    "        'tranches': [{'index': 0, 'price': 61234.5, 'size': 0.0123,\n"
    "            'visible': True, 'status': 'pending', 'fill_price': None,\n"
    "            'opened_ts': 1755000000.0}]}}}),\n"
    "    desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))\n"
)

INERT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-stack-probe-'))
os.environ['HOME'] = str(root)
os.environ['USERPROFILE'] = str(root)

opened = []
real_open = open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


import builtins
builtins.open = watched_open

import socket
reached = []


def refuse(address, *found, **named):
    reached.append(str(address))
    raise OSError('the probe may not reach outside')


socket.create_connection = refuse
socket.socket.connect = lambda self, address, *a, **k: refuse(address)

import time
clock_reads = []
real_time = time.time


def watched_time():
    clock_reads.append(1)
    return real_time()


time.time = watched_time

from src.gui.main_tabs import stack_tranches_tab_surface as s

built_at_import = s.PANE_MODEL is not None
opened_at_import = list(opened)
reads_at_import = len(clock_reads)
model = s.pane_model()
answer = {'built_at_import': built_at_import,
          'built_on_request': s.pane_model() is s.PANE_MODEL,
          'header': s.HEADER_TEXT,
          'qt': 'PySide6' in sys.modules,
          'clock_reads_at_import': reads_at_import,
          'rows_before_a_build': len(model.state.detail_rows),
          'opened_at_import': opened_at_import,
          'reached_at_import': list(reached),
          'made_under_home': sorted(str(p) for p in root.rglob('*'))}
builtins.open = real_open
time.time = real_time
print(json.dumps(answer))
"""


def run_script(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    if env:
        where.update(env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=where,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Stack Tranches tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["detail"]["row_count"] == 1
    assert result["detail"]["rows"][0] == (
        "   0 |  $61234.50000000  |    0.012300  |  VISIBLE  |  pending    "
        "|  —            |  6.9d"
    )
    assert result["summary_rows"][5] == [surface.OPENED_ROW_LABEL, "5"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_touches_nothing():
    """Loading the surface read a file, a clock, or reached a host."""
    answered = run_script(INERT_IMPORT_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["header"] == surface.HEADER_TEXT, answered
    assert answered["qt"] is False, answered
    assert answered["clock_reads_at_import"] == 0, answered
    assert answered["rows_before_a_build"] == 0, answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    read_by_the_surface = [
        name
        for name in answered["opened_at_import"]
        if "stack_tranches" in name or "acervator" in name.lower()
    ]
    assert read_by_the_surface == [], read_by_the_surface


def test_the_import_probe_can_report_a_file_a_clock_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = INERT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import stack_tranches_tab_surface as s",
        "with open(root / 'acervator-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "time.time()\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "from src.gui.main_tabs import stack_tranches_tab_surface as s",
    )
    answered = run_script(probe)
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert answered["clock_reads_at_import"] >= 1, answered
    seeded = [
        name for name in answered["opened_at_import"] if "acervator-seeded" in name
    ]
    assert seeded, answered["opened_at_import"]


def test_the_surface_imports_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    imported = set()
    for node in ast.walk(parsed(SURFACE_SOURCE)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    shipped_imports = {
        (node.module or "")
        for node in ast.walk(parsed(TAB_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in shipped_imports), shipped_imports


def test_the_surface_opens_no_file_and_reads_no_clock():
    """The surface reached for a file, a clock or a network address."""
    called = {
        node.func.id
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {
        node.attr
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, ast.Attribute)
    }
    for forbidden in (
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "mkdir",
        "urlopen",
        "socket",
        "listen",
        "monotonic",
        "time",
    ):
        assert forbidden not in reached, forbidden
    text = SURFACE_SOURCE.read_text(encoding="utf-8")
    assert "Path.home" not in text
    assert "import time" not in text
    assert "webbrowser" not in text


def test_the_import_scan_reports_a_module_the_shipped_file_does_load():
    """The import scan reports nothing whatever a file imports."""
    reached = {
        node.attr
        for node in ast.walk(parsed(TAB_SOURCE))
        if isinstance(node, ast.Attribute)
    }
    assert "time" in reached, "the shipped tab stopped reading the clock"
    assert "import time" in TAB_SOURCE.read_text(encoding="utf-8")


# Nothing reaches outside, and nothing is written to the operator's tree


def test_no_driven_case_attempts_a_connection(monkeypatch, refuse_outside_connections):
    """A driven case opened a real socket."""
    for spec in SCENARIOS:
        drive_old(spec, monkeypatch)
        drive_new(spec)
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_two_real_outside_addresses(
    refuse_outside_connections,
):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("www.coinbase.com", 443)
    second = ("api.exchange.coinbase.com", 443)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections
    assert second in refuse_outside_connections


def test_the_connection_counter_reaches_a_child_process():
    """A child process opened a socket the parent's counter cannot see."""
    answered = run_script(INERT_IMPORT_PROBE)
    assert answered["reached_at_import"] == []
    seeded = run_script(
        INERT_IMPORT_PROBE.replace(
            "from src.gui.main_tabs import stack_tranches_tab_surface as s",
            "try:\n"
            "    socket.create_connection(('example.invalid', 443))\n"
            "except OSError:\n"
            "    pass\n"
            "from src.gui.main_tabs import stack_tranches_tab_surface as s",
        )
    )
    assert seeded["reached_at_import"] == ["('example.invalid', 443)"]


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACERVATOR_TEST_HOME", str(home))
    for spec in SCENARIOS:
        drive_old(spec, monkeypatch)
        drive_new(spec)
    for name in CLEAR_STEP_NAMES:
        step_new(STEP_BY_NAME[name], "clear")
    for name in COUNTER_STEP_NAMES:
        step_new(STEP_BY_NAME[name], "counters")
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


# The file runs in the CI fast lane


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences


def test_this_file_and_the_surface_hold_no_carriage_return():
    """A file grew a Windows line ending the build machine reads as text."""
    for path in (SURFACE_SOURCE, Path(__file__)):
        assert path.read_bytes().count(b"\r") == 0, path.name


def test_the_carriage_return_counter_can_report():
    """The carriage-return counter reports nothing whatever a file holds."""
    assert b"a\r\nb".count(b"\r") == 1
    assert b"a\nb".count(b"\r") == 0
