"""The Qt Phantom Bots tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, a
different colour, a different column, a different number format, a
different tooltip, a different layout number, a different branch or a
different refusal than ``PhantomBotsTabMixin`` builds on the same input.
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import phantom_bots_tab_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
    load_run_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_PATH = REPO_ROOT / "src" / "gui" / "live_settings" / "phantom_bots_tab.py"
SURFACE_PATH = REPO_ROOT / "src" / "gui" / "main_tabs" / "phantom_bots_tab_surface.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_BUILT_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_NONE_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
TIMER_RUN_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
BUS_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_CONTROL_PATH = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

PIXEL_SIZE = (1100, 900)

TAB_CONNECT_SITES = 3
CONTROL_CONNECT_SITES = 1
TAB_SIGNAL_BUILDS = 0
CONTROL_SIGNAL_BUILDS = 3
TAB_TIMER_BUILDS = 0
CONTROL_TIMER_BUILDS = 1
CONTROL_TIMER_NONE_BUILDS = 0
CONTROL_TIMER_RUNS = 5
TAB_THREAD_BUILDS = 0
TAB_BUS_SUBSCRIBES = 0
TAB_BUS_EMITS = 0
CONTROL_BUS_SUBSCRIBES = 2
CONTROL_BUS_EMITS = 5
TAB_ELEMENT_BUILDS = 33
CONTROL_ELEMENT_BUILDS = 3
TAB_LAYOUT_BUILDS = 8
TAB_CLASS_TOTAL = 1
TAB_METHOD_TOTAL = 2
PAYLOAD_KEY_TOTAL = 49
CONSTANT_TOTAL = 164

WIDGET_NAMES_BUILT = (
    "QWidget",
    "QLabel",
    "QPushButton",
    "QTableWidget",
    "QTableWidgetItem",
    "QGroupBox",
    "QFrame",
    "QScrollArea",
    "QLineEdit",
    "QComboBox",
    "QCheckBox",
    "QSpinBox",
    "QTextEdit",
    "QProgressBar",
    "QSplitter",
    "QDialog",
)
LAYOUT_NAMES_BUILT = ("QHBoxLayout", "QVBoxLayout", "QFormLayout", "QGridLayout")


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
# The bot, its config, its phantoms and its coordinator, as the test owns
# them. The Qt tab is driven with these; the surface is driven with its
# own. Neither side reads the other's.
# ---------------------------------------------------------------------


class Config:
    """The bot config the tab reads its exchange from."""

    def __init__(self, exchange_id):
        self.exchange_id = exchange_id


class Phantom:
    """One shadow bot the per-phantom table reads a status dict from."""

    def __init__(self, status, raises=None):
        self.status = status
        self.raises = raises

    def get_status(self):
        if self.raises is not None:
            raise self.raises
        return self.status


class Manager:
    """The phantom manager the tab asks for this bot's shadow bots."""

    def __init__(self, phantoms=None, raises=None):
        self.phantoms = list(phantoms or [])
        self.raises = raises
        self.asked = []

    def get_phantoms(self, bot_id):
        self.asked.append(bot_id)
        if self.raises is not None:
            raise self.raises
        return self.phantoms


class Coordinator:
    """The cross-bot coordinator the tab reads its locks from."""

    def __init__(self, lock_candle_count=2, locks=None, raises=None, with_count=True):
        if with_count:
            self.lock_candle_count = lock_candle_count
        self.locks = list(locks or [])
        self.raises = raises

    def get_active_locks(self):
        if self.raises is not None:
            raise self.raises
        return self.locks


class Bot:
    """The running bot the tab reads every phantom setting from."""

    def __init__(
        self,
        exchange_id=None,
        enabled=False,
        started=False,
        timeframes=None,
        locked=False,
        lock_timeframe="",
        bot_id="",
        manager=None,
        coordinator=None,
        with_config=True,
        missing=None,
    ):
        if with_config:
            self.config = Config(exchange_id)
        absent = list(missing or ())
        held = [
            ["_phantoms_enabled", enabled],
            ["_phantoms_started", started],
            ["_phantom_timeframes", timeframes],
            ["_phantom_locked", locked],
            ["_phantom_lock_timeframe", lock_timeframe],
            ["bot_id", bot_id],
            ["_phantom_mgr", manager],
            ["_coordinator", coordinator],
        ]
        for name, value in held:
            if name not in absent:
                setattr(self, name, value)


HOST_ACCESSIBLE_NAME = "Phantom Bots tab host"


def host_class():
    """The window the tab lives in, holding only what the mixin declares."""
    from PySide6.QtWidgets import QWidget

    from src.gui.live_settings.phantom_bots_tab import PhantomBotsTabMixin

    class Host(PhantomBotsTabMixin, QWidget):
        def __init__(self, bot):
            super().__init__()
            self.setAccessibleName(HOST_ACCESSIBLE_NAME)
            self._bot = bot
            self.forms = []
            self.changes = []

        def _configure_form(self, form):
            self.forms.append(form)

        def _mark_changed(self, field, value):
            self.changes.append([field, value])

    return Host


# ---------------------------------------------------------------------
# The inputs. One spec drives both sides.
# ---------------------------------------------------------------------

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's phantom"


def status(**named):
    """One phantom status dict with every field the table row reads."""
    fields = {
        "timeframe": "1h",
        "state": "RUNNING",
        "target_balance": 1234.5678,
        "total_trades": 7,
        "realized_pnl_exchange": -12.3456,
        "last_summary": {"bullish": 5, "bearish": 2, "confidence": 0.6125},
    }
    fields.update(named)
    return fields


def lock(**named):
    """One cross-bot lock with every field the lock row reads."""
    fields = {
        "source_tf": "6h",
        "source_bot": "BOT-OTHER",
        "locked_direction": "BULLISH",
        "candles_remaining": 3,
    }
    fields.update(named)
    return fields


STATUSES_HAPPY = [
    status(),
    status(
        timeframe="4h",
        state="IDLE",
        target_balance=0.0,
        total_trades=0,
        realized_pnl_exchange=0.0,
        last_summary={"bullish": 0, "bearish": 0, "confidence": 0.0},
    ),
    status(
        timeframe="1d",
        state="LOCKED",
        target_balance=99.5,
        total_trades=41,
        realized_pnl_exchange=8.75,
        last_summary={"bullish": 1, "bearish": 9, "confidence": 0.3},
    ),
]

STATUSES_GROWN = [
    status(
        timeframe="12h",
        state="WOUND",
        target_balance=987654.321,
        total_trades=9999,
        realized_pnl_exchange=4321.5,
        last_summary={"bullish": 88, "bearish": 3, "confidence": 0.9975},
    ),
    status(
        timeframe="30m",
        state="HELD",
        target_balance=0.005,
        total_trades=1,
        realized_pnl_exchange=-0.0009,
        last_summary={"bullish": 0, "bearish": 12, "confidence": 0.1},
    ),
]

LOCKS_HAPPY = [
    lock(),
    lock(source_tf="1d", source_bot="BOT-1", locked_direction="BEARISH"),
    lock(source_tf="2h", source_bot="BOT-9", locked_direction="NEUTRAL"),
]

LOCKS_GROWN = [
    lock(source_tf="1w", source_bot="BOT-77", locked_direction="BEARISH"),
    lock(source_tf="5m", source_bot="BOT-1", locked_direction="BULLISH"),
]


def spec(name, **named):
    """One driving set: the bot readings, its phantoms and its steps."""
    made = {
        "name": name,
        "exchange_id": "coinbase",
        "enabled": True,
        "started": True,
        "timeframes": ["1h", "4h", "1d"],
        "locked": True,
        "lock_timeframe": "6h",
        "bot_id": "BOT-1",
        "with_config": True,
        "missing": (),
        "manager": True,
        "manager_raises": None,
        "statuses": STATUSES_HAPPY,
        "status_raises": (),
        "coordinator": True,
        "coordinator_with_count": True,
        "lock_candle_count": 3,
        "locks": LOCKS_HAPPY,
        "locks_raise": None,
        "steps": (),
    }
    made.update(named)
    return made


SPECS = [
    spec("happy"),
    spec("no_phantoms_and_no_locks", statuses=[], locks=[]),
    spec("no_phantoms", statuses=[]),
    spec("no_locks", locks=[]),
    spec("no_manager", manager=False),
    spec("no_coordinator", coordinator=False, locks=[]),
    spec("manager_refuses", manager_raises=RuntimeError("manager is gone")),
    spec("locks_refuse", locks_raise=RuntimeError("coordinator is gone")),
    spec("one_phantom_refuses_its_status", status_raises=(1,)),
    spec("every_phantom_refuses_its_status", status_raises=(0, 1, 2)),
    spec("phantom_with_no_parent", bot_id="", missing=("bot_id",)),
    spec("a_lock_from_this_bot", locks=[lock(source_bot="BOT-1")]),
    spec("a_lock_from_another_bot", locks=[lock(source_bot="BOT-OTHER")]),
    spec("bare_phantom", statuses=[{}]),
    spec("bare_lock", locks=[{}]),
    spec("phantoms_disabled", enabled=False, started=False, statuses=[], locks=[]),
    spec("phantoms_not_started", started=False, statuses=[], locks=[]),
    spec("phantoms_started_without_state", statuses=[], locks=[]),
    spec("disabled_with_phantoms", enabled=False, started=False),
    spec("unlocked", locked=False),
    spec("locked_without_a_timeframe", lock_timeframe=""),
    spec("no_configured_timeframes", timeframes=[]),
    spec("timeframes_are_none", timeframes=None),
    spec("a_timeframe_the_tab_never_lists", timeframes=["3m", "1h"]),
    spec("exchange_is_binance", exchange_id="binance"),
    spec("exchange_is_kraken", exchange_id="kraken"),
    spec("exchange_is_unknown", exchange_id="a-venue-nobody-added"),
    spec("exchange_is_none", exchange_id=None),
    spec("exchange_is_empty", exchange_id=""),
    spec("exchange_is_wrong_capitals", exchange_id="COINBASE"),
    spec("exchange_is_a_number", exchange_id=42),
    spec("exchange_is_unicode", exchange_id=UNICODE_TEXT),
    spec("exchange_is_markup", exchange_id=MARKUP_TEXT),
    spec("exchange_has_an_apostrophe", exchange_id=APOSTROPHE_TEXT),
    spec("exchange_has_a_newline", exchange_id=NEWLINE_TEXT),
    spec("exchange_is_two_hundred_characters", exchange_id=LONG_TEXT),
    spec("no_config_on_the_bot", with_config=False),
    spec("lock_count_is_out_of_range_high", lock_candle_count=99),
    spec("lock_count_is_out_of_range_low", lock_candle_count=-5),
    spec("lock_count_is_zero", lock_candle_count=0),
    spec("lock_count_is_a_decimal", lock_candle_count=2.9),
    spec("lock_count_is_a_thousand_million", lock_candle_count=1_000_000_000),
    spec("lock_count_is_missing", coordinator_with_count=False),
    spec("lock_count_is_text", lock_candle_count="two"),
    spec("lock_count_is_infinite", lock_candle_count=math.inf),
    spec("lock_count_is_minus_infinite", lock_candle_count=-math.inf),
    spec("lock_count_is_not_a_number", lock_candle_count=math.nan),
    spec("target_is_zero", statuses=[status(target_balance=0)]),
    spec("target_is_negative", statuses=[status(target_balance=-1234.5678)]),
    spec("target_is_a_thousand_million", statuses=[status(target_balance=1e9)]),
    spec("target_is_one_billionth", statuses=[status(target_balance=1e-9)]),
    spec("target_is_none", statuses=[status(target_balance=None)]),
    spec("target_is_infinite", statuses=[status(target_balance=math.inf)]),
    spec("target_is_minus_infinite", statuses=[status(target_balance=-math.inf)]),
    spec("target_is_not_a_number", statuses=[status(target_balance=math.nan)]),
    spec("target_is_text", statuses=[status(target_balance="lots")]),
    spec("pnl_is_zero", statuses=[status(realized_pnl_exchange=0.0)]),
    spec("pnl_is_negative_zero", statuses=[status(realized_pnl_exchange=-0.0)]),
    spec("pnl_is_a_thousand_million", statuses=[status(realized_pnl_exchange=1e9)]),
    spec("pnl_is_one_billionth", statuses=[status(realized_pnl_exchange=1e-9)]),
    spec("pnl_is_infinite", statuses=[status(realized_pnl_exchange=math.inf)]),
    spec("pnl_is_minus_infinite", statuses=[status(realized_pnl_exchange=-math.inf)]),
    spec("pnl_is_not_a_number", statuses=[status(realized_pnl_exchange=math.nan)]),
    spec("pnl_is_text", statuses=[status(realized_pnl_exchange="none")]),
    spec("pnl_key_is_absent", statuses=[{"timeframe": "1h", "state": "RUNNING"}]),
    spec("trades_is_text", statuses=[status(total_trades="many")]),
    spec("trades_is_negative", statuses=[status(total_trades=-4)]),
    spec("trades_is_a_thousand_million", statuses=[status(total_trades=1_000_000_000)]),
    spec("trades_is_none", statuses=[status(total_trades=None)]),
    spec(
        "confidence_at_the_strong_edge",
        statuses=[status(last_summary={"bullish": 1, "bearish": 1, "confidence": 0.5})],
    ),
    spec(
        "confidence_at_the_fair_edge",
        statuses=[
            status(last_summary={"bullish": 1, "bearish": 1, "confidence": 0.25})
        ],
    ),
    spec(
        "confidence_below_the_fair_edge",
        statuses=[
            status(last_summary={"bullish": 1, "bearish": 1, "confidence": 0.2499})
        ],
    ),
    spec(
        "confidence_is_negative",
        statuses=[status(last_summary={"bullish": 1, "bearish": 1, "confidence": -1})],
    ),
    spec(
        "confidence_is_infinite",
        statuses=[status(last_summary={"confidence": math.inf})],
    ),
    spec(
        "confidence_is_not_a_number",
        statuses=[status(last_summary={"confidence": math.nan})],
    ),
    spec("confidence_is_text", statuses=[status(last_summary={"confidence": "high"})]),
    spec("summary_is_none", statuses=[status(last_summary=None)]),
    spec("summary_is_empty", statuses=[status(last_summary={})]),
    spec("summary_is_absent", statuses=[status(last_summary=None)]),
    spec("summary_is_text", statuses=[status(last_summary="nope")]),
    spec(
        "votes_are_unicode", statuses=[status(last_summary={"bullish": UNICODE_TEXT})]
    ),
    spec("state_is_unicode", statuses=[status(state=UNICODE_TEXT)]),
    spec("state_is_markup", statuses=[status(state=MARKUP_TEXT)]),
    spec("state_has_an_apostrophe", statuses=[status(state=APOSTROPHE_TEXT)]),
    spec("state_has_a_newline", statuses=[status(state=NEWLINE_TEXT)]),
    spec("state_is_two_hundred_characters", statuses=[status(state=LONG_TEXT)]),
    spec("state_is_a_number", statuses=[status(state=1234567890123)]),
    spec("timeframe_cell_is_a_number", statuses=[status(timeframe=15)]),
    spec("status_is_a_list", statuses=[["a", "b"]]),
    spec("status_is_none", statuses=[None]),
    spec("many_phantoms", statuses=[status(timeframe=str(n)) for n in range(24)]),
    spec("candles_is_zero", locks=[lock(candles_remaining=0)]),
    spec("candles_is_negative", locks=[lock(candles_remaining=-3)]),
    spec("candles_is_a_decimal", locks=[lock(candles_remaining=2.9)]),
    spec("candles_is_none", locks=[lock(candles_remaining=None)]),
    spec(
        "candles_is_a_thousand_million", locks=[lock(candles_remaining=1_000_000_000)]
    ),
    spec("candles_is_text", locks=[lock(candles_remaining="two")]),
    spec("candles_is_infinite", locks=[lock(candles_remaining=math.inf)]),
    spec("candles_is_not_a_number", locks=[lock(candles_remaining=math.nan)]),
    spec("direction_is_lower_case", locks=[lock(locked_direction="bullish")]),
    spec("direction_names_both", locks=[lock(locked_direction="BULLISH BEARISH")]),
    spec("direction_is_a_number", locks=[lock(locked_direction=7)]),
    spec("direction_is_unicode", locks=[lock(locked_direction=UNICODE_TEXT)]),
    spec("source_bot_is_a_number", bot_id=7, locks=[lock(source_bot=7)]),
    spec("source_bot_is_markup", locks=[lock(source_bot=MARKUP_TEXT)]),
    spec("source_bot_is_two_hundred_characters", locks=[lock(source_bot=LONG_TEXT)]),
    spec("lock_is_a_list", locks=[["x"]]),
    spec("lock_timeframe_is_unicode", lock_timeframe=UNICODE_TEXT),
    spec("lock_timeframe_is_a_number", lock_timeframe=99),
    spec("bot_id_is_none", bot_id=None),
    spec(
        "every_phantom_setting_is_absent",
        missing=(
            "_phantoms_enabled",
            "_phantoms_started",
            "_phantom_timeframes",
            "_phantom_locked",
            "_phantom_lock_timeframe",
        ),
        statuses=[],
        locks=[],
    ),
    spec("switch_one_timeframe_on", steps=(("timeframe", "2h", True),)),
    spec("switch_one_timeframe_off", steps=(("timeframe", "1h", False),)),
    spec(
        "switch_a_timeframe_the_exchange_refuses",
        steps=(("timeframe", "4h", True),),
    ),
    spec(
        "switch_a_timeframe_twice",
        steps=(
            ("timeframe", "2h", True),
            ("timeframe", "2h", True),
        ),
    ),
    spec("switch_phantoms_off", steps=(("enable", False),)),
    spec("switch_phantoms_on_again", steps=(("enable", False), ("enable", True))),
    spec("switch_phantoms_to_what_they_are", steps=(("enable", True),)),
    spec("move_the_lock_count", steps=(("lock", 7),)),
    spec("move_the_lock_count_above_its_ceiling", steps=(("lock", 99),)),
    spec("move_the_lock_count_below_its_floor", steps=(("lock", -4),)),
    spec("move_the_lock_count_to_what_it_is", steps=(("lock", 3),)),
    spec(
        "a_full_sequence",
        steps=(
            ("enable", False),
            ("timeframe", "2h", True),
            ("lock", 9),
            ("timeframe", "1h", False),
            ("build",),
        ),
    ),
    spec(
        "a_sequence_that_refuses_part_way",
        steps=(
            ("enable", False),
            ("timeframe", "9h", True),
            ("lock", 5),
        ),
    ),
    spec(
        "a_sequence_whose_last_step_refuses",
        steps=(("lock", 6), ("timeframe", "nope", True)),
    ),
    spec("a_step_nobody_declared", steps=(("fly",),)),
]

SPEC_NAMES = [one["name"] for one in SPECS]
BY_NAME = {one["name"]: one for one in SPECS}


def test_every_spec_carries_its_own_name():
    """Two specs share a name, so one drives twice and the other never."""
    assert len(BY_NAME) == len(SPECS), sorted(
        name for name in SPEC_NAMES if SPEC_NAMES.count(name) > 1
    )
    assert len(SPEC_NAMES) == len(SPECS)


# ---------------------------------------------------------------------
# Driving the two sides
# ---------------------------------------------------------------------


def old_bot(one):
    """The bot the Qt tab reads, built from the spec."""
    manager = None
    if one["manager"]:
        manager = Manager(
            [
                Phantom(
                    body,
                    (
                        RuntimeError("phantom is gone")
                        if index in one["status_raises"]
                        else None
                    ),
                )
                for index, body in enumerate(one["statuses"])
            ],
            one["manager_raises"],
        )
    coordinator = None
    if one["coordinator"]:
        coordinator = Coordinator(
            one["lock_candle_count"],
            one["locks"],
            one["locks_raise"],
            one["coordinator_with_count"],
        )
    return Bot(
        exchange_id=one["exchange_id"],
        enabled=one["enabled"],
        started=one["started"],
        timeframes=one["timeframes"],
        locked=one["locked"],
        lock_timeframe=one["lock_timeframe"],
        bot_id=one["bot_id"],
        manager=manager,
        coordinator=coordinator,
        with_config=one["with_config"],
        missing=one["missing"],
    )


def new_bot(one):
    """The bot the surface reads, built from the same spec."""
    manager = None
    if one["manager"]:
        manager = surface.PhantomManagerSource(
            [
                surface.PhantomSource(
                    body,
                    (
                        RuntimeError("phantom is gone")
                        if index in one["status_raises"]
                        else None
                    ),
                )
                for index, body in enumerate(one["statuses"])
            ],
            one["manager_raises"],
        )
    coordinator = None
    if one["coordinator"]:
        coordinator = surface.CoordinatorSource(
            one["lock_candle_count"],
            one["locks"],
            one["locks_raise"],
            one["coordinator_with_count"],
        )
    return surface.BotSource(
        exchange_id=one["exchange_id"],
        enabled=one["enabled"],
        started=one["started"],
        timeframes=one["timeframes"],
        locked=one["locked"],
        lock_timeframe=one["lock_timeframe"],
        bot_id=one["bot_id"],
        manager=manager,
        coordinator=coordinator,
        with_config=one["with_config"],
        missing=one["missing"],
    )


def take_qt_step(host, tab, step):
    """Move one Qt control the way the operator moves it."""
    name = step[0]
    if name == surface.STEP_BUILD:
        return host._create_phantom_bots_tab()
    if name == surface.STEP_ENABLE:
        host._phantom_enable.setChecked(bool(step[1]))
        return tab
    if name == surface.STEP_TIMEFRAME:
        host._phantom_tf_checks[step[1]].setChecked(bool(step[2]))
        return tab
    if name == surface.STEP_LOCK:
        host._phantom_lock.setValue(step[1])
        return tab
    raise LookupError(name)


def run_qt_steps(host, tab, steps):
    """Take each Qt step in order and report the one that refused."""
    wanted = list(steps or ())
    for index, step in enumerate(wanted):
        try:
            tab = take_qt_step(host, tab, step)
        except Exception as exc:
            return tab, {
                "refused_at": index,
                "refused_step": step[0],
                "refusal": type(exc).__name__,
                "steps_taken": index,
            }
    return tab, {
        "refused_at": surface.NO_REFUSAL_INDEX,
        "refused_step": surface.NO_REFUSAL_NAME,
        "refusal": surface.NO_REFUSAL_NAME,
        "steps_taken": len(wanted),
    }


def drive_old(one):
    """Build the Qt tab, take the spec's steps, and hand it back."""
    app()
    bot = old_bot(one)
    host = host_class()(bot)
    tab = host._create_phantom_bots_tab()
    tab, taken = run_qt_steps(host, tab, one["steps"])
    return {"tab": tab, "host": host, "bot": bot, "steps": taken}


def drive_new(one):
    """Build the surface model and take the same steps."""
    bot = new_bot(one)
    model = surface.PhantomBotsTabModel(bot)
    model.build()
    taken = model.run_steps(one["steps"])
    return {"model": model, "bot": bot, "steps": taken}


# ---------------------------------------------------------------------
# Reading the two sides
# ---------------------------------------------------------------------


def layout_order(layout):
    """The class of each item the layout holds, in the order it was added."""
    order = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        order.append("stretch" if widget is None else type(widget).__name__)
    return order


def group_titled(tab, start):
    """The box inside the tab whose title starts with `start`."""
    from PySide6.QtWidgets import QGroupBox

    outer = tab.layout()
    for index in range(outer.count()):
        widget = outer.itemAt(index).widget()
        if isinstance(widget, QGroupBox) and widget.title().startswith(start):
            return widget
    return None


def table_inside(group):
    """The one table a box holds, or nothing when it holds none."""
    from PySide6.QtWidgets import QTableWidget

    if group is None:
        return None
    for child in group.children():
        if isinstance(child, QTableWidget):
            return child
    return None


def qt_table_state(table, column_count):
    """Every value one Qt table can be asked for."""
    from PySide6.QtCore import Qt

    if table is None:
        return {
            "columns": [],
            "column_count": 0,
            "max_height_px": 0,
            "row_count": 0,
            "rows": [],
            "row_colors": [],
            "header_resize_mode": surface.HEADER_RESIZE_MODE,
            "vertical_header_visible": surface.VERTICAL_HEADER_VISIBLE,
            "edit_triggers": surface.EDIT_TRIGGERS,
            "alternating_row_colors": surface.ALTERNATING_ROW_COLORS,
        }
    rows = []
    colors = []
    for row in range(table.rowCount()):
        texts = []
        painted = []
        for column in range(column_count):
            cell = table.item(row, column)
            texts.append(surface.MISSING_TEXT if cell is None else cell.text())
            brush = None if cell is None else cell.data(Qt.ItemDataRole.ForegroundRole)
            painted.append(None if brush is None else brush.color().name())
        rows.append(texts)
        colors.append(painted)
    header = table.horizontalHeader()
    return {
        "columns": [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ],
        "column_count": table.columnCount(),
        "max_height_px": table.maximumHeight(),
        "row_count": table.rowCount(),
        "rows": rows,
        "row_colors": colors,
        "header_resize_mode": header.sectionResizeMode(0).name,
        "vertical_header_visible": not table.verticalHeader().isHidden(),
        "edit_triggers": table.editTriggers().name,
        "alternating_row_colors": table.alternatingRowColors(),
    }


def qt_form_rows(form):
    """Every row of one Qt form: its label, its value and its skin."""
    from PySide6.QtWidgets import QFormLayout

    rows = []
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.ItemRole.LabelRole).widget()
        field = form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
        rows.append([label.text(), field.text(), field.styleSheet()])
    return rows


def qt_trace(driven):
    """Every value the built Qt tab can be asked for, as plain data."""
    from PySide6.QtWidgets import QLabel

    tab = driven["tab"]
    host = driven["host"]
    outer = tab.layout()
    info = outer.itemAt(0).widget()
    enable_group = group_titled(tab, surface.ENABLE_GROUP_TITLE)
    tf_group = group_titled(tab, surface.TF_GROUP_TITLE)
    lock_group = group_titled(tab, surface.LOCK_GROUP_TITLE)
    summary_group = group_titled(tab, surface.SUMMARY_GROUP_TITLE)
    phantom_group = group_titled(tab, "Per-Phantom State")
    locks_group = group_titled(tab, "Active Locks")
    hint = tf_group.layout().itemAt(0).widget()
    empty = None
    for index in range(outer.count()):
        widget = outer.itemAt(index).widget()
        if isinstance(widget, QLabel) and widget is not info:
            empty = widget
    return {
        "accessible_name": tab.accessibleName(),
        "container": {"spacing_px": outer.spacing()},
        "order": layout_order(outer),
        "info_label": [info.text(), info.styleSheet(), info.wordWrap()],
        "enable_group": enable_group.title(),
        "enable_check": [
            host._phantom_enable.text(),
            host._phantom_enable.isChecked(),
        ],
        "timeframe_group": tf_group.title(),
        "timeframe_hint": [hint.text(), hint.styleSheet(), hint.wordWrap()],
        "timeframe_checks": [
            [name, box.isChecked(), box.isEnabled(), box.toolTip()]
            for name, box in host._phantom_tf_checks.items()
        ],
        "lock_group": lock_group.title(),
        "lock_spin": [
            host._phantom_lock.value(),
            host._phantom_lock.minimum(),
            host._phantom_lock.maximum(),
            host._phantom_lock.toolTip(),
            qt_form_rows(lock_group.layout())[0][0],
        ],
        "summary_group": summary_group.title(),
        "summary_rows": qt_form_rows(summary_group.layout()),
        "forms_configured": len(host.forms),
        "phantom_group": {
            "title": (
                surface.PHANTOM_GROUP_TITLE_FORMAT.format(count=0)
                if phantom_group is None
                else phantom_group.title()
            ),
            "shown": phantom_group is not None,
        },
        "phantom_table": qt_table_state(
            table_inside(phantom_group), surface.PHANTOM_COLUMN_COUNT
        ),
        "locks_group": {
            "title": (
                surface.LOCKS_GROUP_TITLE_FORMAT.format(count=0)
                if locks_group is None
                else locks_group.title()
            ),
            "shown": locks_group is not None,
        },
        "locks_table": qt_table_state(
            table_inside(locks_group), surface.LOCK_COLUMN_COUNT
        ),
        "empty_label": (
            {"shown": False}
            if empty is None
            else {
                "shown": True,
                "text": empty.text(),
                "style_sheet": empty.styleSheet(),
                "word_wrap": empty.wordWrap(),
            }
        ),
        "changes": [list(one) for one in host.changes],
        "steps": driven["steps"],
    }


def surface_trace(driven):
    """The same values, read from the Qt-free view model."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    order = ["QLabel", "QGroupBox", "QGroupBox", "QGroupBox", "QGroupBox"]
    if payload["phantom_group"]["shown"]:
        order.append("QGroupBox")
    if payload["locks_group"]["shown"]:
        order.append("QGroupBox")
    if payload["empty_label"]["shown"]:
        order.append("QLabel")
    order.append("stretch")
    phantom = dict(payload["phantom_table"])
    phantom.update(payload["table_rules"])
    phantom.pop("pnl_column")
    phantom.pop("confidence_column")
    locks = dict(payload["locks_table"])
    locks.update(payload["table_rules"])
    locks.pop("source_bot_column")
    locks.pop("direction_column")
    if not payload["phantom_group"]["shown"]:
        phantom = qt_table_state(None, surface.PHANTOM_COLUMN_COUNT)
    if not payload["locks_group"]["shown"]:
        locks = qt_table_state(None, surface.LOCK_COLUMN_COUNT)
    return {
        "accessible_name": payload["accessible_name"],
        "container": {"spacing_px": payload["container"]["spacing_px"]},
        "order": order,
        "info_label": [
            payload["info_label"]["text"],
            payload["info_label"]["style_sheet"],
            payload["info_label"]["word_wrap"],
        ],
        "enable_group": payload["enable_group"]["title"],
        "enable_check": [
            payload["enable_check"]["text"],
            payload["enable_check"]["checked"],
        ],
        "timeframe_group": payload["timeframe_group"]["title"],
        "timeframe_hint": [
            payload["timeframe_hint"]["text"],
            payload["timeframe_hint"]["style_sheet"],
            payload["timeframe_hint"]["word_wrap"],
        ],
        "timeframe_checks": [list(one) for one in payload["timeframe_checks"]],
        "lock_group": payload["lock_group"]["title"],
        "lock_spin": [
            payload["lock_spin"]["value"],
            payload["lock_spin"]["minimum"],
            payload["lock_spin"]["maximum"],
            payload["lock_spin"]["tooltip"],
            payload["lock_spin"]["row_label"],
        ],
        "summary_group": payload["summary_group"]["title"],
        "summary_rows": [list(one) for one in payload["summary_rows"]],
        "forms_configured": payload["forms"]["configured"],
        "phantom_group": {
            "title": payload["phantom_group"]["title"],
            "shown": payload["phantom_group"]["shown"],
        },
        "phantom_table": phantom,
        "locks_group": {
            "title": payload["locks_group"]["title"],
            "shown": payload["locks_group"]["shown"],
        },
        "locks_table": locks,
        "empty_label": (
            {
                "shown": True,
                "text": payload["empty_label"]["text"],
                "style_sheet": payload["empty_label"]["style_sheet"],
                "word_wrap": payload["empty_label"]["word_wrap"],
            }
            if payload["empty_label"]["shown"]
            else {"shown": False}
        ),
        "changes": [list(one) for one in payload["changes"]],
        "steps": driven["steps"],
    }


def outcome(work):
    """What one side did: the value it answered, or the type it refused with.

    The wording of a refusal is never read. Two hosts word one refusal
    differently, so a wording check states a fact about the machine.
    """
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {"outcome": "refused", "error": type(exc).__name__}


def old_outcome(one):
    return outcome(lambda: qt_trace(drive_old(one)))


def new_outcome(one):
    return outcome(lambda: surface_trace(drive_new(one)))


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_the_two_sides_describe_the_same_tab(name):
    """A control, colour, column, number, tooltip or branch differs."""
    one = BY_NAME[name]
    old = old_outcome(one)
    new = new_outcome(one)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert new["value"] == old["value"], name
    assert digest(new["value"]) == digest(old["value"]), name


REFUSING_SPECS = (
    "lock_count_is_text",
    "lock_count_is_infinite",
    "lock_count_is_minus_infinite",
    "lock_count_is_not_a_number",
    "target_is_text",
    "pnl_is_text",
    "confidence_is_text",
    "summary_is_text",
    "status_is_a_list",
    "status_is_none",
    "candles_is_text",
    "candles_is_infinite",
    "candles_is_not_a_number",
    "lock_is_a_list",
)

REFUSAL_TYPES = ("ValueError", "TypeError", "OverflowError", "AttributeError")


def test_both_answers_and_refusals_are_in_the_measured_set():
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for one in SPECS:
        old = old_outcome(one)
        (answered if old["outcome"] == "answered" else refused).append(one["name"])
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert set(refused) == set(REFUSING_SPECS), sorted(
        set(refused) ^ set(REFUSING_SPECS)
    )
    assert len(answered) + len(refused) == len(SPECS)
    assert len(answered) == len(SPECS) - len(REFUSING_SPECS)


@pytest.mark.parametrize("name", REFUSING_SPECS)
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """One side refused an input the other accepted, or named another type."""
    one = BY_NAME[name]
    old = old_outcome(one)
    new = new_outcome(one)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert new["error"] == old["error"], (name, old, new)
    assert old["error"] in REFUSAL_TYPES, old


def test_every_refusal_type_the_tab_can_raise_is_driven():
    """Only one kind of refusal was ever compared, so the rest are unmeasured."""
    seen = {old_outcome(BY_NAME[name])["error"] for name in REFUSING_SPECS}
    assert seen == {"ValueError", "OverflowError", "AttributeError"}, sorted(seen)
    assert len(seen) > 1, seen


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    happy = old_outcome(BY_NAME["happy"])["value"]
    grown = old_outcome(spec("grown", statuses=STATUSES_GROWN, locks=LOCKS_GROWN))[
        "value"
    ]
    assert happy != grown
    assert digest(happy) != digest(grown)
    assert digest(happy) == digest(old_outcome(BY_NAME["happy"])["value"])
    assert len(digest(happy)) == 64


def test_two_different_real_inputs_are_told_apart_in_both_directions():
    """The comparison passes whatever the second side holds.

    One real input is driven through the Qt tab and another through the
    surface, then the two are swapped, so neither side can be the one
    that carries the difference.
    """
    grown = spec("grown", statuses=STATUSES_GROWN, locks=LOCKS_GROWN)
    happy = BY_NAME["happy"]
    old_happy = digest(old_outcome(happy)["value"])
    old_grown = digest(old_outcome(grown)["value"])
    new_happy = digest(new_outcome(happy)["value"])
    new_grown = digest(new_outcome(grown)["value"])
    assert old_happy != new_grown, "the Qt happy tab hashed like the surface grown tab"
    assert old_grown != new_happy, "the Qt grown tab hashed like the surface happy tab"
    assert old_happy == new_happy
    assert old_grown == new_grown


@pytest.mark.parametrize(
    "name",
    [
        "happy",
        "no_phantoms_and_no_locks",
        "bare_phantom",
        "a_full_sequence",
        "many_phantoms",
    ],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 21, sorted(value)
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# ---------------------------------------------------------------------
# Step sequences
# ---------------------------------------------------------------------

STEP_SEQUENCES = (
    ("a_full_sequence", -1, "", "", 5),
    ("a_sequence_that_refuses_part_way", 1, "timeframe", "KeyError", 1),
    ("a_sequence_whose_last_step_refuses", 1, "timeframe", "KeyError", 1),
    ("a_step_nobody_declared", 0, "fly", "LookupError", 0),
    ("switch_a_timeframe_twice", -1, "", "", 2),
    ("move_the_lock_count_above_its_ceiling", -1, "", "", 1),
)


@pytest.mark.parametrize("name,refused_at,refused_step,refusal,taken", STEP_SEQUENCES)
def test_a_step_sequence_stops_at_the_same_step_on_both_sides(
    name, refused_at, refused_step, refusal, taken
):
    """A sequence ran further on one side, or refused with another type."""
    one = BY_NAME[name]
    old = drive_old(one)["steps"]
    new = drive_new(one)["steps"]
    assert old == new, (name, old, new)
    assert old["refused_at"] == refused_at, old
    assert old["refused_step"] == refused_step, old
    assert old["refusal"] == refusal, old
    assert old["steps_taken"] == taken, old


def test_a_sequence_that_refuses_leaves_the_steps_it_already_took():
    """A refusal part way rolled back the steps that had already run."""
    one = BY_NAME["a_sequence_that_refuses_part_way"]
    old = drive_old(one)
    new = drive_new(one)
    assert old["host"].changes == [[surface.ENABLE_FIELD, False]]
    assert new["model"].changes == [[surface.ENABLE_FIELD, False]]
    assert old["host"]._phantom_enable.isChecked() is False
    assert new["model"].enable_checked is False


def test_a_repeated_step_tells_the_host_nothing_the_second_time():
    """A switch set to the value it holds reported a change anyway."""
    twice = BY_NAME["switch_a_timeframe_twice"]
    old = drive_old(twice)
    new = drive_new(twice)
    assert len(old["host"].changes) == 1, old["host"].changes
    assert old["host"].changes == new["model"].changes
    same = drive_old(BY_NAME["switch_phantoms_to_what_they_are"])
    assert same["host"].changes == []
    assert drive_new(BY_NAME["switch_phantoms_to_what_they_are"])["model"].changes == []


def test_the_step_recorder_survives_a_run_that_refuses_part_way():
    """The recorder lost everything the run did before it refused."""
    one = BY_NAME["a_sequence_whose_last_step_refuses"]
    old = drive_old(one)
    new = drive_new(one)
    assert old["host"].changes == [[surface.LOCK_FIELD, 6]]
    assert new["model"].changes == [[surface.LOCK_FIELD, 6]]
    assert old["steps"]["refused_at"] == 1
    assert new["steps"]["refused_at"] == 1


def test_every_step_the_surface_declares_is_driven():
    """A step the surface names is never taken by any spec."""
    driven = set()
    for one in SPECS:
        for step in one["steps"]:
            driven.add(step[0])
    assert surface.STEP_BUILD in driven
    assert driven >= {
        surface.STEP_BUILD,
        surface.STEP_ENABLE,
        surface.STEP_TIMEFRAME,
        surface.STEP_LOCK,
    }, sorted(driven)
    assert set(surface.build_view_model(surface.PhantomBotsTabModel())["steps"]) <= (
        driven | {"fly"}
    )


# ---------------------------------------------------------------------
# The enumeration: wiring, classes, methods, signals, threads, timers,
# bus traffic and screen elements, counted in both forms
# ---------------------------------------------------------------------


def call_name(node):
    """The name a call reaches for, or nothing when it reaches for none."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def count_calls(path, names):
    """How many times one file really calls any of `names`.

    Read from the parsed file rather than from its text, so a name
    written inside a comment or a string is not counted as a call.
    """
    return sum(
        1
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and call_name(node) in names
    )


def count_text(path, needle):
    """How many times one wiring call appears in one file's text."""
    return path.read_text(encoding="utf-8").count(needle)


def dotted(node):
    """The dotted name a node spells, as text."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path):
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
                [
                    dotted(node.func.value),
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                ]
            )
    return sorted(found)


def declared_classes(path):
    """Every class one file declares, wherever it is declared."""
    return {
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    }


def widget_classes(path):
    """Every class one file declares that ends up being a screen element."""
    classes = [
        node for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    ]
    found: set = set()
    growing = True
    while growing:
        growing = False
        for node in classes:
            if node.name in found:
                continue
            for base in node.bases:
                name = (
                    base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                )
                if name.startswith("Q") or name in found:
                    found.add(node.name)
                    growing = True
                    break
    return found


def count_elements(path):
    """How many screen elements one file builds, its own classes included."""
    return count_calls(path, WIDGET_NAMES_BUILT) + len(widget_classes(path))


def timers_run_without_building(path):
    """Every wait one file starts without building a timer of its own."""
    return [
        call_name(node)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and call_name(node) in ("singleShot", "startTimer")
    ]


def bus_subscribe_sites(path):
    """Every ``subscribe(`` site in `path`, whatever holds the bus."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and call_name(node) == "subscribe"
    ]


def bus_emit_sites(path):
    """Every ``emit(`` site in `path`, whatever holds the bus.

    A counter that demands a named receiver misses
    ``get_event_bus().emit(...)``, which names nothing the reader can
    match, so the receiver is not looked at.
    """
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and call_name(node) == "emit"
    ]


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A report is callable and is not a method, so it is excluded by name.
    A read-only value is not callable at all, so asking ``callable``
    alone misses it.
    """
    import inspect

    from PySide6.QtCore import Signal

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if inspect.isfunction(value) or isinstance(
            value, (property, classmethod, staticmethod)
        ):
            found.add(name)
    return found


def test_the_member_counter_excludes_a_report_and_finds_both_quiet_shapes():
    """The counter counts a report, or misses a factory or a read-only value."""
    from PySide6.QtCore import Signal

    from src.gui import indicator_panel, launcher

    app()
    panel = indicator_panel.IndicatorVotingPanel
    assert callable(Signal())
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert isinstance(vars(panel)["_reading_fingerprint"], staticmethod)
    assert "_reading_fingerprint" in members(panel)
    assert isinstance(vars(panel)["lock_timeframe"], property)
    assert not callable(vars(panel)["lock_timeframe"])
    assert "lock_timeframe" in members(panel)
    assert isinstance(vars(panel)["selected_bot_id"], property)
    assert not callable(vars(panel)["selected_bot_id"])
    assert "selected_bot_id" in members(panel)


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(NESTED_CLASS_CONTROL_PATH)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    top_level = {
        node.name
        for node in parsed(NESTED_CLASS_CONTROL_PATH).body
        if isinstance(node, ast.ClassDef)
    }
    assert top_level != found, "the nested-class case is gone, so this control is stale"
    assert declared_classes(TAB_PATH) == {"PhantomBotsTabMixin"}
    assert len(declared_classes(TAB_PATH)) == TAB_CLASS_TOTAL


QT_SIGNAL_NAMES = {
    "self._phantom_enable.toggled": "phantom_enable.toggled",
    "cb.toggled": "timeframe_check.toggled",
    "self._phantom_lock.valueChanged": "lock_spin.valueChanged",
}
QT_TARGET_NAMES = {
    "lambda": "lambda",
    "self._phantom_tfs_changed": "_phantom_tfs_changed",
}


def test_the_connect_sets_match():
    """The Qt tab wires a signal the surface names no action for."""
    sites = connect_sites(TAB_PATH)
    assert len(sites) == TAB_CONNECT_SITES, sites
    assert count_text(TAB_PATH, ".connect(") == len(sites)
    named = {QT_SIGNAL_NAMES[signal] for signal, _target in sites}
    assert named == set(surface.ACTIONS), sorted(named ^ set(surface.ACTIONS))
    assert len(surface.ACTIONS) == TAB_CONNECT_SITES
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.PhantomBotsTabModel, target)), target
    assert {QT_TARGET_NAMES[target] for _signal, target in sites} == {
        "lambda",
        "_phantom_tfs_changed",
    }
    assert count_text(SURFACE_PATH, ".connect(") == 0


def test_the_wiring_counter_can_report():
    """The wiring counter returns nothing whatever a file wires."""
    assert (
        len(connect_sites(WIRING_CONTROL_PATH)) == CONTROL_CONNECT_SITES == 1
    ), connect_sites(WIRING_CONTROL_PATH)
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES
    assert len(connect_sites(BUS_CONTROL_PATH)) > TAB_CONNECT_SITES


SHIPPED_METHODS = {
    "_create_phantom_bots_tab": "PhantomBotsTabModel.build",
    "_phantom_tfs_changed": "PhantomBotsTabModel.timeframes_changed",
}

SURFACE_CLASSES = {
    "PhantomBotsTabModel": "PhantomBotsTabMixin",
    "BotConfig": "the config PhantomBotsTabMixin reads its exchange from",
    "BotSource": "the running bot PhantomBotsTabMixin reads",
    "PhantomSource": "one shadow bot the per-phantom table reads",
    "PhantomManagerSource": "the manager the tab asks for this bot's phantoms",
    "CoordinatorSource": "the coordinator the tab reads its locks from",
}

SURFACE_MODEL_MEMBERS = {
    "__init__",
    "clear",
    "build",
    "enable_changed",
    "timeframes_changed",
    "lock_changed",
    "take_step",
    "run_steps",
}


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped tab gained or lost a class or a method."""
    from src.gui.live_settings import phantom_bots_tab as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["PhantomBotsTabMixin"], classes
    assert len(classes) == TAB_CLASS_TOTAL
    found = sorted(members(shipped.PhantomBotsTabMixin))
    assert found == sorted(SHIPPED_METHODS), found
    assert len(found) == TAB_METHOD_TOTAL
    for counterpart in SHIPPED_METHODS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart
    declared = sorted(
        name
        for node in parsed(TAB_PATH).body
        if isinstance(node, ast.ClassDef)
        for sub in node.body
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
        for name in [sub.name]
    )
    assert declared == sorted(SHIPPED_METHODS), declared


def test_an_annotation_is_not_counted_as_a_method():
    """An annotation creates no attribute, and a loose counter reads one."""
    from src.gui.live_settings.phantom_bots_tab import PhantomBotsTabMixin

    names = vars(PhantomBotsTabMixin)
    for annotated in ("_bot", "_configure_form", "_mark_changed", "_phantom_tf_checks"):
        assert annotated not in names, annotated
        assert annotated in PhantomBotsTabMixin.__annotations__, annotated
    assert sorted(members(PhantomBotsTabMixin)) == sorted(SHIPPED_METHODS)


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["PhantomBotsTabModel"] == "PhantomBotsTabMixin"
    assert members(surface.PhantomBotsTabModel) == SURFACE_MODEL_MEMBERS, sorted(
        members(surface.PhantomBotsTabModel) ^ SURFACE_MODEL_MEMBERS
    )


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "InventedModel" not in SURFACE_CLASSES
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        getattr(surface.PhantomBotsTabModel, "invented_method")
    assert "invented_method" not in members(surface.PhantomBotsTabModel)


def test_the_tab_declares_no_signal_and_the_signal_counter_can_report():
    """A report declaration appeared on one side and not the other."""
    assert count_calls(TAB_PATH, ("Signal",)) == TAB_SIGNAL_BUILDS == 0
    assert count_calls(SURFACE_PATH, ("Signal",)) == 0
    assert surface.SIGNAL_COUNT == TAB_SIGNAL_BUILDS
    assert (
        count_calls(SIGNAL_CONTROL_PATH, ("Signal",)) == CONTROL_SIGNAL_BUILDS == 3
    ), count_calls(SIGNAL_CONTROL_PATH, ("Signal",))
    text_count = len(
        re.findall(r"\bSignal\b", SIGNAL_CONTROL_PATH.read_text(encoding="utf-8"))
    )
    assert text_count > CONTROL_SIGNAL_BUILDS, text_count


def test_the_tab_starts_no_thread_and_the_thread_counter_can_report():
    """A worker appeared on one side and not the other."""
    from PySide6.QtCore import QThread

    app()
    assert count_calls(TAB_PATH, ("QThread",)) == TAB_THREAD_BUILDS == 0
    assert count_calls(SURFACE_PATH, ("QThread",)) == 0
    assert surface.THREAD_COUNT == TAB_THREAD_BUILDS
    started: list = []
    first_start = QThread.start
    QThread.start = lambda self, *found, **named: started.append(type(self).__name__)
    try:
        drive_old(BY_NAME["happy"])
        drive_new(BY_NAME["happy"])
        quiet = list(started)
        QThread().start()
    finally:
        QThread.start = first_start
    assert quiet == [], quiet
    assert started == ["QThread"], started


def test_the_tab_builds_no_timer_and_both_timer_counters_can_report():
    """A wait appeared on one side and not the other.

    Two counters, because a file can start a wait it never built. The
    tab builds none and starts none; one neighbour builds one and
    another starts five without building any.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    assert count_calls(TAB_PATH, ("QTimer",)) == TAB_TIMER_BUILDS == 0
    assert count_text(TAB_PATH, "QTimer") == 0
    assert count_calls(SURFACE_PATH, ("QTimer",)) == 0
    assert timers_run_without_building(TAB_PATH) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert (
        count_calls(TIMER_BUILT_CONTROL_PATH, ("QTimer",)) == CONTROL_TIMER_BUILDS == 1
    )
    assert count_text(TIMER_BUILT_CONTROL_PATH, "QTimer") > CONTROL_TIMER_BUILDS
    assert (
        count_calls(TIMER_NONE_CONTROL_PATH, ("QTimer",))
        == CONTROL_TIMER_NONE_BUILDS
        == 0
    )
    assert TIMER_BUILT_CONTROL_PATH.name == TIMER_NONE_CONTROL_PATH.name
    assert TIMER_BUILT_CONTROL_PATH != TIMER_NONE_CONTROL_PATH
    run_only = timers_run_without_building(TIMER_RUN_CONTROL_PATH)
    assert len(run_only) == CONTROL_TIMER_RUNS == 5, run_only

    started: list = []
    first_object = QObject.startTimer
    first_start = QTimer.start
    first_single = QTimer.singleShot
    QObject.startTimer = lambda self, *found, **named: started.append("startTimer")
    QTimer.start = lambda self, *found, **named: started.append("QTimer.start")
    QTimer.singleShot = lambda *found, **named: started.append("singleShot")
    try:
        drive_old(BY_NAME["happy"])
        drive_new(BY_NAME["happy"])
        quiet = list(started)
        QTimer.singleShot(0, lambda: None)
    finally:
        QObject.startTimer = first_object
        QTimer.start = first_start
        QTimer.singleShot = first_single
    assert quiet == [], quiet
    assert started == ["singleShot"], started


def test_the_tab_reaches_the_bus_in_neither_direction():
    """A bus wiring appeared on one side and not the other.

    Both directions are counted. The tab neither listens nor speaks, so
    both counters are pointed at a neighbouring screen that does both.
    """
    assert bus_subscribe_sites(TAB_PATH) == []
    assert bus_emit_sites(TAB_PATH) == []
    assert len(bus_subscribe_sites(TAB_PATH)) == TAB_BUS_SUBSCRIBES == 0
    assert len(bus_emit_sites(TAB_PATH)) == TAB_BUS_EMITS == 0
    assert bus_subscribe_sites(SURFACE_PATH) == []
    assert bus_emit_sites(SURFACE_PATH) == []
    assert surface.BUS_TOPICS == ()
    assert surface.BUS_EMITS == ()
    listens = bus_subscribe_sites(BUS_CONTROL_PATH)
    speaks = bus_emit_sites(BUS_CONTROL_PATH)
    assert len(listens) == CONTROL_BUS_SUBSCRIBES == 2, listens
    assert len(speaks) == CONTROL_BUS_EMITS == 5, speaks


def test_the_emit_counter_finds_a_speaker_with_no_name():
    """A counter demanding a named receiver misses an unnamed one.

    ``get_event_bus().emit(...)`` names nothing the reader can match on
    the left of the dot, so a filter keyed on a receiver name reports
    fewer emits than the file holds.
    """
    speaks = bus_emit_sites(BUS_CONTROL_PATH)
    unnamed = [one for one in speaks if one == "emit"]
    named = [one for one in speaks if one != "emit"]
    assert len(unnamed) == 2, speaks
    assert len(named) == 3, speaks
    assert len(unnamed) + len(named) == CONTROL_BUS_EMITS
    assert "bus.emit" in named


def test_the_screen_elements_the_tab_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(TAB_PATH) == TAB_ELEMENT_BUILDS == 33
    assert widget_classes(TAB_PATH) == set()
    assert count_calls(TAB_PATH, WIDGET_NAMES_BUILT) == TAB_ELEMENT_BUILDS
    assert count_calls(TAB_PATH, LAYOUT_NAMES_BUILT) == TAB_LAYOUT_BUILDS == 8
    assert count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    assert widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert count_calls(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert count_elements(SURFACE_PATH) == 0
    assert count_calls(SURFACE_PATH, LAYOUT_NAMES_BUILT) == 0


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------

PAYLOAD_KEYS = {
    "ACCESSIBLE_NAME": "accessible_name",
    "ACTIONS": "actions",
    "ALTERNATING_ROW_COLORS": "table_rules.alternating_row_colors",
    "BEARISH_KEY": "keys.bearish",
    "BEARISH_MARK": "texts.bearish_mark",
    "BOT_ID_ATTRIBUTE": "attributes.bot_id",
    "BULLISH_KEY": "keys.bullish",
    "BULLISH_MARK": "texts.bullish_mark",
    "BUS_EMITS": "bus_emits",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CANDLES_FORMAT": "formats.candles",
    "CANDLES_KEY": "keys.candles",
    "CONFIDENCE_COLUMN": "phantom_table.confidence_column",
    "CONFIDENCE_FAIR_AT": "thresholds.confidence_fair_at",
    "CONFIDENCE_FORMAT": "formats.confidence",
    "CONFIDENCE_KEY": "keys.confidence",
    "CONFIDENCE_STRONG_AT": "thresholds.confidence_strong_at",
    "CONFIG_ATTRIBUTE": "attributes.config",
    "CONTENT_MARGINS_SET": "container.margins_set",
    "CONTENT_SPACING_PX": "container.spacing_px",
    "COORDINATOR_ATTRIBUTE": "attributes.coordinator",
    "DEFAULT_BOT_ID": "defaults.bot_id",
    "DEFAULT_CONFIDENCE": "defaults.confidence",
    "DEFAULT_COUNT": "defaults.count",
    "DEFAULT_LOCK_TIMEFRAME": "defaults.lock_timeframe",
    "DEFAULT_MONEY": "defaults.money",
    "DEFAULT_VOTES": "defaults.votes",
    "DIRECTION_COLUMN": "locks_table.direction_column",
    "DIRECTION_KEY": "keys.direction",
    "EDIT_TRIGGERS": "table_rules.edit_triggers",
    "EMPTY_DISABLED_TEXT": "empty_texts.disabled",
    "EMPTY_NOT_STARTED_TEXT": "empty_texts.not_started",
    "EMPTY_NO_STATE_TEXT": "empty_texts.no_state",
    "EMPTY_STYLE_FORMAT": "formats.empty_style",
    "EMPTY_WORD_WRAP": "empty_label.word_wrap",
    "ENABLED_ATTRIBUTE": "attributes.enabled",
    "ENABLED_ROW_LABEL": "labels.enabled_row",
    "ENABLE_CHECK_TEXT": "enable_check.text",
    "ENABLE_FIELD": "fields.enable",
    "ENABLE_GROUP_TITLE": "enable_group.title",
    "EXCHANGE_ID_ATTRIBUTE": "attributes.exchange_id",
    "FALLBACK_TIMEFRAMES": "fallback_timeframes",
    "FLAG_STYLE_FORMAT": "formats.flag_style",
    "FORM_CONFIGURED_BY_HOST": "forms.configured_by_host",
    "HEADER_RESIZE_MODE": "table_rules.header_resize_mode",
    "INFO_STYLE_FORMAT": "formats.info_style",
    "INFO_TEXT": "info_label.text",
    "INFO_WORD_WRAP": "info_label.word_wrap",
    "LOCKED_ATTRIBUTE": "attributes.locked",
    "LOCKED_STYLE_FORMAT": "formats.locked_style",
    "LOCKED_TEXT_FORMAT": "formats.locked_text",
    "LOCKS_GROUP_TITLE_FORMAT": "locks_group.title_format",
    "LOCK_COLUMNS": "locks_table.columns",
    "LOCK_COLUMN_COUNT": "locks_table.column_count",
    "LOCK_COUNT_ATTRIBUTE": "attributes.lock_count",
    "LOCK_DEFAULT": "thresholds.lock_default",
    "LOCK_FIELD": "fields.lock",
    "LOCK_GROUP_TITLE": "lock_group.title",
    "LOCK_MAX": "lock_spin.maximum",
    "LOCK_MIN": "lock_spin.minimum",
    "LOCK_ROW_LABEL": "lock_spin.row_label",
    "LOCK_STATE_ROW_LABEL": "labels.lock_state_row",
    "LOCK_TABLE_MAX_HEIGHT_PX": "locks_table.max_height_px",
    "LOCK_TIMEFRAME_ATTRIBUTE": "attributes.lock_timeframe",
    "LOCK_TOOLTIP": "lock_spin.tooltip",
    "LOSS_COLOR": "colors.loss",
    "MISSING_TEXT": "texts.missing",
    "NOTE_COLOR": "colors.note",
    "NO_CELL_COLOR": "no_cell_color",
    "NO_CONFIG": "no_config",
    "NO_EMPTY_TEXT": "empty_texts.none",
    "NO_EXCHANGE_ID": "no_exchange_id",
    "NO_REFUSAL_INDEX": "no_refusal.index",
    "NO_REFUSAL_NAME": "no_refusal.name",
    "NO_TEXT": "texts.no",
    "NO_TIMEFRAMES_TEXT": "texts.no_timeframes",
    "OFF_COLOR": "colors.off",
    "ON_COLOR": "colors.on",
    "PHANTOM_COLUMNS": "phantom_table.columns",
    "PHANTOM_COLUMN_COUNT": "phantom_table.column_count",
    "PHANTOM_GROUP_TITLE_FORMAT": "phantom_group.title_format",
    "PHANTOM_MANAGER_ATTRIBUTE": "attributes.phantom_manager",
    "PHANTOM_TABLE_MAX_HEIGHT_PX": "phantom_table.max_height_px",
    "PNL_COLUMN": "phantom_table.pnl_column",
    "PNL_FORMAT": "formats.pnl",
    "PNL_GAIN_ABOVE": "thresholds.pnl_gain_above",
    "PNL_KEY": "keys.pnl",
    "PNL_LOSS_BELOW": "thresholds.pnl_loss_below",
    "SIGNAL_COUNT": "signal_count",
    "SOURCE_BOT_COLUMN": "locks_table.source_bot_column",
    "SOURCE_BOT_KEY": "keys.source_bot",
    "SOURCE_TF_KEY": "keys.source_tf",
    "STARTED_ATTRIBUTE": "attributes.started",
    "STARTED_ROW_LABEL": "labels.started_row",
    "STATE_KEY": "keys.state",
    "SUMMARY_GROUP_TITLE": "summary_group.title",
    "SUMMARY_KEY": "keys.summary",
    "TARGET_FORMAT": "formats.target",
    "TARGET_KEY": "keys.target",
    "TF_GROUP_TITLE": "timeframe_group.title",
    "TF_HINT_STYLE_FORMAT": "formats.hint_style",
    "TF_HINT_TEXT": "timeframe_hint.text",
    "TF_HINT_WORD_WRAP": "timeframe_hint.word_wrap",
    "TF_SUPPORTED_TOOLTIP_FORMAT": "formats.tf_supported_tooltip",
    "TF_UNSUPPORTED_TOOLTIP_FORMAT": "formats.tf_unsupported_tooltip",
    "THIS_BOT_COLOR": "colors.this_bot",
    "THIS_BOT_FORMAT": "formats.this_bot",
    "THREAD_COUNT": "thread_count",
    "TIMEFRAMES": "timeframes",
    "TIMEFRAMES_ATTRIBUTE": "attributes.timeframes",
    "TIMEFRAMES_FIELD": "fields.timeframes",
    "TIMEFRAMES_ROW_LABEL": "labels.timeframes_row",
    "TIMEFRAME_JOIN": "texts.timeframe_join",
    "TIMEFRAME_KEY": "keys.timeframe",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TRADES_FORMAT": "formats.trades",
    "TRADES_KEY": "keys.trades",
    "UNKNOWN_EXCHANGE_TEXT": "texts.unknown_exchange",
    "UNLOCKED_STYLE_FORMAT": "formats.unlocked_style",
    "UNLOCKED_TEXT": "texts.unlocked",
    "VERTICAL_HEADER_VISIBLE": "table_rules.vertical_header_visible",
    "VOTES_FORMAT": "formats.votes",
    "WAITING_COLOR": "colors.waiting",
    "YES_TEXT": "texts.yes",
}

LIST_MEMBERS = {
    "STEP_BUILD": "steps",
    "STEP_ENABLE": "steps",
    "STEP_TIMEFRAME": "steps",
    "STEP_LOCK": "steps",
}

CALL_CONSTANTS = (
    "BUILD_START",
    "BUILD_INFO",
    "BUILD_ENABLE",
    "BUILD_TF_ALLOWED",
    "BUILD_TF_FALLBACK",
    "BUILD_TF_CHECK",
    "BUILD_LOCK_FORM",
    "BUILD_LOCK_FROM_COORDINATOR",
    "BUILD_LOCK_WITHOUT_COORDINATOR",
    "BUILD_LOCK_CLAMPED",
    "BUILD_SUMMARY_FORM",
    "BUILD_SUMMARY_ROW",
    "BUILD_SCRUM_LOCKED",
    "BUILD_SCRUM_UNLOCKED",
    "BUILD_PHANTOMS",
    "BUILD_PHANTOMS_FAILED",
    "BUILD_NO_MANAGER",
    "BUILD_PHANTOM_TABLE",
    "BUILD_PHANTOM_ROW",
    "BUILD_PHANTOM_STATUS_FAILED",
    "BUILD_LOCKS",
    "BUILD_LOCKS_FAILED",
    "BUILD_NO_COORDINATOR",
    "BUILD_LOCK_TABLE",
    "BUILD_LOCK_ROW",
    "BUILD_EMPTY_DISABLED",
    "BUILD_EMPTY_NOT_STARTED",
    "BUILD_EMPTY_NO_STATE",
    "BUILD_RETURN",
    "ENABLE_CHANGED",
    "TIMEFRAMES_CHANGED",
    "LOCK_CHANGED",
)

# The two values no snapshot key carries, each with the check that
# covers it. METHOD is the name the bridge registers under and
# PANE_MODEL is the tab state the bridge keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_phantom_bots_method",
    "PANE_MODEL": "test_the_bridge_resets_the_tab_state_on_request",
}

STATE_ONLY_KEYS = {
    "allowed_timeframes",
    "calls",
    "changes",
    "exchange_id",
    "stretch_shown",
    "summary_rows",
    "timeframe_checks",
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
    payload = surface.build_view_model(surface.PhantomBotsTabModel())
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
                assert type(carried) is type(value), name
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
    assert (
        len(PAYLOAD_KEYS)
        + len(LIST_MEMBERS)
        + len(CALL_CONSTANTS)
        + len(NOT_IN_THE_SNAPSHOT)
        == CONSTANT_TOTAL
    )
    assert len(CALL_CONSTANTS) == len(surface.CALL_NAMES)


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.PhantomBotsTabModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= set(LIST_MEMBERS.values())
    answered.add("call_names")
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL == len(answered | STATE_ONLY_KEYS)
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing.

    A value that reaches no snapshot path and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model(surface.PhantomBotsTabModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "PHANTOM_COLUMNS" in surface_constants()
    assert "EMPTY_DISABLED_TEXT" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "PhantomBotsTabModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for one in SPECS:
        if one["name"] in REFUSING_SPECS:
            continue
        for call in drive_new(one)["model"].calls:
            seen.add(call[0])
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    empty = drive_new(BY_NAME["no_phantoms_and_no_locks"])["model"]
    assert empty.empty_shown is True
    assert empty.phantom_group_shown is False
    assert empty.locks_group_shown is False
    filled = drive_new(BY_NAME["happy"])["model"]
    assert filled.empty_shown is False
    assert filled.phantom_group_shown is True
    assert filled.locks_group_shown is True


# ---------------------------------------------------------------------
# The surface carries its own values
# ---------------------------------------------------------------------


class MovedTokens:
    """A token table whose colours are unlike any the design system holds."""

    SUCCESS = "#111111"
    ERROR = "#222222"
    CARD_METRIC_LABEL = "#333333"
    TEXT_INACTIVE = "#444444"
    FOLD_RATIO_AMBER = "#555555"
    FOLD_SOURCE_MANUAL = "#666666"


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_tab(monkeypatch):
    """The surface read its values off the tab it replaces.

    A surface that read the shipped tab would follow it, and the whole
    comparison above would be one side read twice. The shipped tab's
    tokens are moved and the surface must not move with them.
    """
    app()
    from src.gui.live_settings import phantom_bots_tab as shipped

    first = shipped.ds
    one = BY_NAME["happy"]
    before = qt_trace(drive_old(one))
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved = qt_trace(drive_old(one))
    assert MovedTokens.CARD_METRIC_LABEL in moved["info_label"][1]
    assert MovedTokens.SUCCESS in moved["summary_rows"][0][2]
    assert MovedTokens.CARD_METRIC_LABEL not in before["info_label"][1]
    new = surface_trace(drive_new(one))
    assert MovedTokens.CARD_METRIC_LABEL not in new["info_label"][1]
    assert MovedTokens.SUCCESS not in new["summary_rows"][0][2]
    assert new["info_label"] == before["info_label"]
    assert new["summary_rows"] == before["summary_rows"]
    monkeypatch.undo()
    assert shipped.ds is first
    assert qt_trace(drive_old(one))["info_label"] == before["info_label"]


def test_the_surface_does_not_follow_a_tab_that_builds_nothing(monkeypatch):
    """The surface asked the shipped tab to build its controls."""
    app()
    from src.gui.live_settings import phantom_bots_tab as shipped

    first = shipped.PhantomBotsTabMixin._create_phantom_bots_tab
    payload = surface.build_view_model(surface.PhantomBotsTabModel())
    monkeypatch.setattr(
        shipped.PhantomBotsTabMixin, "_create_phantom_bots_tab", lambda self: None
    )
    host = host_class()(old_bot(BY_NAME["happy"]))
    assert host._create_phantom_bots_tab() is None
    again = surface.build_view_model(surface.PhantomBotsTabModel())
    assert again == payload
    assert again["phantom_table"]["columns"] == list(surface.PHANTOM_COLUMNS)
    assert again["info_label"]["text"] == surface.INFO_TEXT
    monkeypatch.undo()
    assert shipped.PhantomBotsTabMixin._create_phantom_bots_tab is first
    assert host_class()(old_bot(BY_NAME["happy"]))._create_phantom_bots_tab()


def test_the_shipped_tab_writes_to_no_shared_table():
    """The shipped tab changed something every later test would inherit."""
    app()
    from src.gui import design_system
    from src.gui.live_settings import phantom_bots_tab as shipped

    watched = (
        "SUCCESS",
        "ERROR",
        "CARD_METRIC_LABEL",
        "TEXT_INACTIVE",
        "FOLD_RATIO_AMBER",
        "FOLD_SOURCE_MANUAL",
    )
    before_tokens = {name: getattr(design_system, name) for name in watched}
    before_module = sorted(vars(shipped))
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["a_full_sequence"])
    assert {name: getattr(design_system, name) for name in watched} == before_tokens
    assert sorted(vars(shipped)) == before_module
    assert shipped.ds is design_system


def test_the_shipped_tab_edits_only_the_dialog_it_was_handed():
    """The tab changed the bot, the phantom list or a lock it was given."""
    app()
    one = BY_NAME["happy"]
    bot = old_bot(one)
    statuses_before = json.dumps(one["statuses"], sort_keys=True, default=repr)
    locks_before = json.dumps(one["locks"], sort_keys=True, default=repr)
    given = list(bot._phantom_mgr.phantoms)
    host = host_class()(bot)
    before_bot = sorted(vars(bot))
    host._create_phantom_bots_tab()
    assert sorted(vars(bot)) == before_bot
    assert bot._phantom_mgr.phantoms == given
    assert json.dumps(one["statuses"], sort_keys=True, default=repr) == statuses_before
    assert json.dumps(one["locks"], sort_keys=True, default=repr) == locks_before
    assert bot._coordinator.locks == one["locks"]
    for name in ("_phantom_enable", "_phantom_lock", "_phantom_tf_checks"):
        assert hasattr(host, name), name
    assert bot._phantom_mgr.asked == [one["bot_id"]]


def test_the_surface_edits_only_its_own_model():
    """The surface changed the bot, the phantom list or a lock it was given."""
    one = BY_NAME["happy"]
    bot = new_bot(one)
    statuses_before = json.dumps(one["statuses"], sort_keys=True, default=repr)
    locks_before = json.dumps(one["locks"], sort_keys=True, default=repr)
    before_bot = sorted(vars(bot))
    model = surface.PhantomBotsTabModel(bot)
    model.build()
    model.run_steps((("enable", False), ("lock", 8)))
    assert sorted(vars(bot)) == before_bot
    assert json.dumps(one["statuses"], sort_keys=True, default=repr) == statuses_before
    assert json.dumps(one["locks"], sort_keys=True, default=repr) == locks_before
    assert getattr(bot, surface.ENABLED_ATTRIBUTE) is True
    assert bot._coordinator.lock_candle_count == one["lock_candle_count"]


def without_the_session_counters(payload):
    """One payload without the parts that count the whole session.

    The branch trail, the changes the host was told about and the
    number of forms it configured all outlive one build, because the
    dialog outlives the tab it rebuilds.
    """
    kept = dict(payload)
    for name in ("calls", "changes", "forms"):
        kept.pop(name)
    return kept


def test_a_second_build_carries_only_its_own_boxes():
    """A rebuilt tab kept a row the first build put there."""
    one = BY_NAME["happy"]
    model = surface.PhantomBotsTabModel(new_bot(one))
    model.build()
    first = without_the_session_counters(surface.build_view_model(model))
    model.build()
    assert without_the_session_counters(surface.build_view_model(model)) == first
    model.bot = new_bot(BY_NAME["no_phantoms_and_no_locks"])
    model.build()
    second = surface.build_view_model(model)
    assert second["phantom_table"]["row_count"] == 0
    assert second["locks_table"]["row_count"] == 0
    assert second["empty_label"]["shown"] is True


def test_a_rebuild_keeps_the_changes_the_host_was_already_told():
    """A rebuilt tab wiped the pending changes the dialog holds."""
    one = BY_NAME["a_full_sequence"]
    old = drive_old(one)
    new = drive_new(one)
    assert old["host"].changes == new["model"].changes
    assert len(old["host"].changes) == 4, old["host"].changes
    assert old["steps"]["steps_taken"] == 5


# ---------------------------------------------------------------------
# The colours
# ---------------------------------------------------------------------

DECLARED_COLORS = (
    ("on", surface.ON_COLOR),
    ("waiting", surface.WAITING_COLOR),
    ("off", surface.OFF_COLOR),
    ("loss", surface.LOSS_COLOR),
    ("note", surface.NOTE_COLOR),
    ("this_bot", surface.THIS_BOT_COLOR),
)


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    app()
    written = {name: canonical(value) for name, value in DECLARED_COLORS}
    assert len(set(written.values())) == len(written), written
    assert all(len(value) == 7 for value in written.values()), written


def test_the_colours_that_cannot_report_a_channel_swap_are_named():
    """A colour with three equal channels reads the same with two swapped.

    Such a colour proves nothing about a swap, so it is compared by its
    exact text instead. Two of the six are grey, and naming them here
    keeps the limit visible rather than hidden inside a passing check.
    """
    app()
    from src.gui import design_system

    equal_channelled = []
    for name, value in DECLARED_COLORS:
        written = canonical(value)
        if written[1:3] == written[3:5] == written[5:7]:
            equal_channelled.append(name)
    assert equal_channelled == ["off", "note"], equal_channelled
    assert surface.NOTE_COLOR == design_system.CARD_METRIC_LABEL
    assert surface.OFF_COLOR == design_system.TEXT_INACTIVE
    assert canonical(surface.NOTE_COLOR) == "#888888"
    assert canonical(surface.OFF_COLOR) == "#aaaaaa"
    assert canonical("#888")[1:3] == canonical("#888")[5:7]


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    app()
    assert canonical(surface.ON_COLOR) == "#00ff88"
    assert canonical("#0088ff") != canonical(surface.ON_COLOR)
    assert canonical(surface.LOSS_COLOR) == "#ff3366"
    assert canonical("#3366ff") != canonical(surface.LOSS_COLOR)
    assert canonical(surface.THIS_BOT_COLOR) != canonical("#ccff00")


@pytest.mark.parametrize(
    "pnl,expected",
    [
        (4.5, surface.ON_COLOR),
        (-4.5, surface.LOSS_COLOR),
        (0.0, surface.OFF_COLOR),
        (-0.0, surface.OFF_COLOR),
        (1e-9, surface.ON_COLOR),
        (math.inf, surface.ON_COLOR),
        (-math.inf, surface.LOSS_COLOR),
        (math.nan, surface.OFF_COLOR),
    ],
)
def test_the_profit_colour_follows_the_profit_exactly(pnl, expected):
    """A profit of exactly nothing was painted as a gain or a loss."""
    assert surface.pnl_color(pnl) == expected


@pytest.mark.parametrize(
    "confidence,expected",
    [
        (0.75, surface.ON_COLOR),
        (0.50, surface.ON_COLOR),
        (0.4999, surface.WAITING_COLOR),
        (0.25, surface.WAITING_COLOR),
        (0.2499, surface.NO_CELL_COLOR),
        (0.0, surface.NO_CELL_COLOR),
        (-1.0, surface.NO_CELL_COLOR),
        (math.inf, surface.ON_COLOR),
        (math.nan, surface.NO_CELL_COLOR),
    ],
)
def test_the_agreement_colour_follows_the_agreement_exactly(confidence, expected):
    """An agreement at the edge took the colour of the band below it."""
    assert surface.confidence_color(confidence) == expected


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("BULLISH", surface.ON_COLOR),
        ("BEARISH", surface.LOSS_COLOR),
        ("BULLISH BEARISH", surface.ON_COLOR),
        ("bullish", surface.NO_CELL_COLOR),
        ("NEUTRAL", surface.NO_CELL_COLOR),
        ("?", surface.NO_CELL_COLOR),
        ("", surface.NO_CELL_COLOR),
    ],
)
def test_the_lock_colour_follows_the_direction_exactly(direction, expected):
    """A direction in the wrong capitals took a real lock colour."""
    assert surface.direction_color(direction) == expected


@pytest.mark.parametrize(
    "started,enabled,expected",
    [
        (True, True, surface.ON_COLOR),
        (True, False, surface.ON_COLOR),
        (False, True, surface.WAITING_COLOR),
        (False, False, surface.OFF_COLOR),
    ],
)
def test_the_started_colour_follows_both_flags(started, enabled, expected):
    """A phantom set that is on but not running was painted as running."""
    assert surface.started_color(started, enabled) == expected


@pytest.mark.parametrize(
    "requested,kept",
    [(0, 1), (1, 1), (2, 2), (10, 10), (11, 10), (99, 10), (-5, 1), (2.9, 2)],
)
def test_the_lock_count_keeps_the_nearest_value_in_range(requested, kept):
    """A lock count outside the box's range reached the operator unchanged."""
    assert surface.clamp_lock(requested) == kept


def test_the_lock_count_clamp_matches_the_number_box(monkeypatch):
    """The surface clamps a lock count the Qt box does not clamp."""
    from PySide6.QtWidgets import QSpinBox

    app()
    box = QSpinBox()
    box.setRange(surface.LOCK_MIN, surface.LOCK_MAX)
    for requested in (0, 1, 2, 10, 11, 99, -5):
        box.setValue(requested)
        assert box.value() == surface.clamp_lock(requested), requested
    assert box.minimum() == surface.LOCK_MIN
    assert box.maximum() == surface.LOCK_MAX


# ---------------------------------------------------------------------
# The timeframes
# ---------------------------------------------------------------------


def test_the_tab_lists_every_timeframe_the_venue_map_knows():
    """The tab lists a timeframe no exchange serves, or misses one."""
    from src.exchange.timeframes import ALL_TIMEFRAMES

    assert surface.TIMEFRAMES == ALL_TIMEFRAMES
    assert surface.FALLBACK_TIMEFRAMES == ALL_TIMEFRAMES
    assert len(surface.TIMEFRAMES) == len(set(surface.TIMEFRAMES))


@pytest.mark.parametrize(
    "exchange_id,supported",
    [
        ("coinbase", 8),
        ("binance", 11),
        ("kraken", 8),
        ("a-venue-nobody-added", 11),
        (None, 11),
        ("", 11),
        ("COINBASE", 8),
        (42, 11),
    ],
)
def test_the_supported_timeframes_follow_the_exchange(exchange_id, supported):
    """A timeframe the exchange refuses was left switchable."""
    assert len(surface.allowed_timeframes(exchange_id)) == supported


def test_a_timeframe_the_exchange_refuses_is_greyed_on_both_sides():
    """A timeframe the exchange refuses stayed switchable on one side."""
    one = BY_NAME["happy"]
    old = qt_trace(drive_old(one))["timeframe_checks"]
    new = surface_trace(drive_new(one))["timeframe_checks"]
    assert old == new
    greyed = [row[0] for row in old if not row[2]]
    assert greyed == ["4h", "12h", "1w"], greyed
    assert [row[0] for row in old if row[1]] == ["1h", "1d"], old
    assert one["timeframes"] == ["1h", "4h", "1d"]


def test_a_greyed_timeframe_is_never_ticked_even_when_configured():
    """A configured timeframe the exchange refuses was shown as active."""
    one = BY_NAME["happy"]
    checks = surface_trace(drive_new(one))["timeframe_checks"]
    by_name = {row[0]: row for row in checks}
    assert "4h" in one["timeframes"]
    assert by_name["4h"][1] is False
    assert by_name["4h"][2] is False
    assert by_name["1h"][1] is True


def test_the_note_on_a_greyed_timeframe_names_the_exchange():
    """The note on a greyed timeframe says nothing about which venue."""
    assert surface.timeframe_tooltip("4h", False, "coinbase") == (
        "4h: NOT supported by exchange (coinbase)"
    )
    assert surface.timeframe_tooltip("4h", True, "coinbase") == "4h: supported"
    checks = surface_trace(drive_new(BY_NAME["happy"]))["timeframe_checks"]
    assert [row[3] for row in checks if not row[2]] == [
        surface.timeframe_tooltip(name, False, "coinbase")
        for name in ("4h", "12h", "1w")
    ]


def test_the_unknown_exchange_note_is_never_shown():
    """The unknown-exchange note reaches the operator, so it needs a check.

    A bot with no config takes the full timeframe set, so every switch
    is supported and the greyed note is never built. The value the tab
    would have put there is unreachable on every driven input.
    """
    seen = set()
    for one in SPECS:
        if one["name"] in REFUSING_SPECS:
            continue
        for row in drive_new(one)["model"].timeframe_checks:
            seen.add(row[3])
    assert seen, "no note was built at all"
    assert not [note for note in seen if surface.UNKNOWN_EXCHANGE_TEXT in note], sorted(
        note for note in seen if surface.UNKNOWN_EXCHANGE_TEXT in note
    )
    without = drive_new(BY_NAME["no_config_on_the_bot"])["model"]
    assert [row[2] for row in without.timeframe_checks] == [True] * len(
        surface.TIMEFRAMES
    )
    assert surface.timeframe_tooltip("4h", False, surface.UNKNOWN_EXCHANGE_TEXT) == (
        "4h: NOT supported by exchange (?)"
    )


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


def model_payload(one=None):
    """The view model after the same driving, stamped."""
    driven = drive_new(one or BY_NAME["happy"])
    return sealed(surface.build_view_model(driven["model"]))


def widget_painted_by_the_tab(one=None):
    """The tab the shipped Qt mixin builds, after the same driving."""
    return drive_old(one or BY_NAME["happy"])["tab"]


def fill_table(payload_table, column_count, rules):
    """One table built only from the values a payload carries."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget
    from PySide6.QtWidgets import QTableWidgetItem

    table = QTableWidget()
    table.setColumnCount(payload_table["column_count"])
    table.setHorizontalHeaderLabels(payload_table["columns"])
    table.horizontalHeader().setSectionResizeMode(
        getattr(QHeaderView.ResizeMode, rules["header_resize_mode"])
    )
    table.setRowCount(payload_table["row_count"])
    table.setMaximumHeight(payload_table["max_height_px"])
    table.setAlternatingRowColors(rules["alternating_row_colors"])
    table.setEditTriggers(
        getattr(QAbstractItemView.EditTrigger, rules["edit_triggers"])
    )
    for row, cells in enumerate(payload_table["rows"]):
        for column in range(column_count):
            cell = QTableWidgetItem(cells[column])
            painted = payload_table["row_colors"][row][column]
            if painted is not None:
                cell.setForeground(QColor(painted))
            table.setItem(row, column, cell)
    return table


def widget_painted_by_the_model(payload):
    """A tab built only from the payload, never from the shipped mixin.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtWidgets import (
        QCheckBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    app()
    screen = QWidget()
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    outer.setSpacing(payload["container"]["spacing_px"])

    info = QLabel(payload["info_label"]["text"])
    info.setStyleSheet(payload["info_label"]["style_sheet"])
    info.setWordWrap(payload["info_label"]["word_wrap"])
    outer.addWidget(info)

    enable_group = QGroupBox(payload["enable_group"]["title"])
    enable_column = QVBoxLayout(enable_group)
    enable = QCheckBox(payload["enable_check"]["text"])
    enable.setChecked(payload["enable_check"]["checked"])
    enable_column.addWidget(enable)
    outer.addWidget(enable_group)

    tf_group = QGroupBox(payload["timeframe_group"]["title"])
    tf_column = QVBoxLayout(tf_group)
    hint = QLabel(payload["timeframe_hint"]["text"])
    hint.setStyleSheet(payload["timeframe_hint"]["style_sheet"])
    hint.setWordWrap(payload["timeframe_hint"]["word_wrap"])
    tf_column.addWidget(hint)
    tf_row = QHBoxLayout()
    for name, ticked, live, note in payload["timeframe_checks"]:
        box = QCheckBox(name)
        box.setChecked(ticked)
        box.setEnabled(live)
        box.setToolTip(note)
        tf_row.addWidget(box)
    tf_column.addLayout(tf_row)
    outer.addWidget(tf_group)

    lock_group = QGroupBox(payload["lock_group"]["title"])
    lock_form = QFormLayout(lock_group)
    spin = QSpinBox()
    spin.setRange(payload["lock_spin"]["minimum"], payload["lock_spin"]["maximum"])
    spin.setValue(payload["lock_spin"]["value"])
    spin.setToolTip(payload["lock_spin"]["tooltip"])
    lock_form.addRow(payload["lock_spin"]["row_label"], spin)
    outer.addWidget(lock_group)

    summary_group = QGroupBox(payload["summary_group"]["title"])
    summary_form = QFormLayout(summary_group)
    for label, value, style_sheet in payload["summary_rows"]:
        field = QLabel(value)
        field.setStyleSheet(style_sheet)
        summary_form.addRow(label, field)
    outer.addWidget(summary_group)

    if payload["phantom_group"]["shown"]:
        group = QGroupBox(payload["phantom_group"]["title"])
        column = QVBoxLayout(group)
        column.addWidget(
            fill_table(
                payload["phantom_table"],
                payload["phantom_table"]["column_count"],
                payload["table_rules"],
            )
        )
        outer.addWidget(group)

    if payload["locks_group"]["shown"]:
        group = QGroupBox(payload["locks_group"]["title"])
        column = QVBoxLayout(group)
        column.addWidget(
            fill_table(
                payload["locks_table"],
                payload["locks_table"]["column_count"],
                payload["table_rules"],
            )
        )
        outer.addWidget(group)

    if payload["empty_label"]["shown"]:
        empty = QLabel(payload["empty_label"]["text"])
        empty.setStyleSheet(payload["empty_label"]["style_sheet"])
        empty.setWordWrap(payload["empty_label"]["word_wrap"])
        outer.addWidget(empty)

    outer.addStretch()
    return screen


PICTURE_SPECS = [
    "happy",
    "no_phantoms_and_no_locks",
    "phantoms_disabled",
    "exchange_is_binance",
    "bare_phantom",
    "a_lock_from_this_bot",
    "state_is_unicode",
]


@pytest.mark.parametrize("name", PICTURE_SPECS)
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


def test_the_picture_comparison_can_report_a_difference_in_both_directions():
    """The picture check passes whatever the second side paints.

    Two real bots, one driven into each side, then swapped, so a pass
    proves the comparison reports a tab painted differently whichever
    side carries which input.
    """
    app()
    grown = spec("grown", statuses=STATUSES_GROWN, locks=LOCKS_GROWN)
    happy = BY_NAME["happy"]
    assert STATUSES_HAPPY != STATUSES_GROWN
    assert LOCKS_HAPPY != LOCKS_GROWN
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_tab(happy), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(grown)), PIXEL_SIZE
        ),
        note="the happy bot on the Qt side against the grown bot on the surface",
    )
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_tab(grown), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(happy)), PIXEL_SIZE
        ),
        note="the grown bot on the Qt side against the happy bot on the surface",
    )


@pytest.mark.parametrize("name", PICTURE_SPECS)
def test_the_painted_tab_shows_more_than_one_colour(name):
    """The two sides matched because the tab painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    counted = []
    for image in (
        render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        seen = set()
        for x in range(0, image.width(), 5):
            for y in range(0, image.height(), 5):
                seen.add(QColor(image.pixelColor(x, y)).name())
        counted.append(len(seen))
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"
    assert counted[0] > 1 and counted[1] > 1, (name, counted)


NO_SKIN_RULE = "QGroupBox { background: #1b6ec2; border: 3px solid #c21b6e; }"


def test_a_skin_neither_side_sets_changes_the_picture():
    """The render carries no skin at all, so a lost skin would not show.

    A rule neither the shipped tab nor the surface declares is applied
    to the built tab. A picture that does not move under it is a picture
    that carries no skin, and every skin comparison above would pass on
    a tab painted plain.
    """
    app()
    plain = widget_painted_by_the_model(model_payload())
    skinned = widget_painted_by_the_model(model_payload())
    assert NO_SKIN_RULE not in surface.EMPTY_STYLE_FORMAT
    assert NO_SKIN_RULE not in TAB_PATH.read_text(encoding="utf-8")
    assert NO_SKIN_RULE not in SURFACE_PATH.read_text(encoding="utf-8")
    skinned.setStyleSheet(NO_SKIN_RULE)
    assert_pictures_differ(
        old_side=render_offscreen(plain, PIXEL_SIZE),
        new_side=render_offscreen(skinned, PIXEL_SIZE),
        note="the same tab with and without a rule neither side sets",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload()
    payload["summary_rows"][0][1] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(
            surface.build_view_model(surface.PhantomBotsTabModel())
        )


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one
    em per character, so two strings of equal length need equal width.
    With a font database the glyphs decide the width. Both answers are
    handled here and the file is run both ways.
    """
    app()
    load_run_fonts()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert (
            narrow != wide
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow == wide
        ), "the host reports no fonts and the glyphs still have their own widths"


@skip_unless_no_fonts
def test_two_equal_length_timeframes_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length names still differ."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_two_equal_length_timeframes_measure_apart_with_fonts():
    """The glyphs decide their own width, and two names still measure alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# ---------------------------------------------------------------------
# What a picture cannot see, read off both sides instead
# ---------------------------------------------------------------------


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The accessible name, the edit rule, the table height ceiling, the
    tooltips and the two configure calls paint nothing. Each is read off
    the shipped tab and off the surface directly.
    """
    app()
    one = BY_NAME["happy"]
    old = qt_trace(drive_old(one))
    new = surface_trace(drive_new(one))
    assert new["accessible_name"] == old["accessible_name"] == ""
    assert new["forms_configured"] == old["forms_configured"] == 2
    assert new["lock_spin"][3] == old["lock_spin"][3] == surface.LOCK_TOOLTIP
    for key in ("edit_triggers", "max_height_px", "vertical_header_visible"):
        assert new["phantom_table"][key] == old["phantom_table"][key], key
        assert new["locks_table"][key] == old["locks_table"][key], key
    assert old["phantom_table"]["edit_triggers"] == "NoEditTriggers"
    assert old["phantom_table"]["max_height_px"] == 280
    assert old["locks_table"]["max_height_px"] == 220
    assert old["phantom_table"]["vertical_header_visible"] is True
    assert [row[3] for row in old["timeframe_checks"]] == [
        row[3] for row in new["timeframe_checks"]
    ]


def box_of(layout):
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


def test_a_missing_cell_and_a_plain_cell_are_told_apart():
    """A cell that does not exist reads the same as a cell with no colour.

    Every cell the tab builds carries text, so a missing cell would be
    a lost cell rather than a plain one. The reader is pointed at a
    table with a row it never filled to prove it can tell them apart.
    """
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    app()
    tab = widget_painted_by_the_tab(BY_NAME["happy"])
    table = table_inside(group_titled(tab, "Per-Phantom State"))
    for row in range(table.rowCount()):
        for column in range(surface.PHANTOM_COLUMN_COUNT):
            assert table.item(row, column) is not None, (row, column)
    bare = QTableWidget()
    bare.setColumnCount(2)
    bare.setHorizontalHeaderLabels(["here", "gone"])
    bare.setRowCount(1)
    bare.setItem(0, 0, QTableWidgetItem("here"))
    assert bare.item(0, 0) is not None
    assert bare.item(0, 1) is None
    assert qt_table_state(bare, 2)["rows"][0] == ["here", surface.MISSING_TEXT]


def test_the_profit_column_reads_the_key_the_phantom_never_writes():
    """The two sides disagree about which profit key the tab reads.

    The shipped tab reads ``realized_pnl_exchange`` off a phantom's
    status. Both sides read the same key, so the column matches. The
    real producer is checked in
    ``test_the_real_phantom_status_drives_both_sides``.
    """
    one = spec("real_keys", statuses=[status(realized_pnl_exchange=0)])
    old = qt_trace(drive_old(one))
    new = surface_trace(drive_new(one))
    assert old["phantom_table"]["rows"] == new["phantom_table"]["rows"]
    assert surface.PNL_KEY == "realized_pnl_exchange"
    assert old["phantom_table"]["rows"][0][surface.PNL_COLUMN] == "$+0.0000"


REAL_PHANTOM_STATUS = {
    "phantom_id": "BOT-1:1h",
    "parent_bot_id": "BOT-1",
    "timeframe": "1h",
    "state": "running",
    "target_balance": 250.0,
    "total_trades": 6,
    "realised_pnl": 12.3456,
    "last_summary": {"bullish": 4, "bearish": 1, "net_score": 3, "confidence": 0.66},
}


def test_the_real_phantom_status_drives_both_sides():
    """The two sides read a real phantom status differently."""
    from src.trading.phantom_balance import PhantomBalanceBot

    one = spec("real_status", statuses=[dict(REAL_PHANTOM_STATUS)])
    old = qt_trace(drive_old(one))
    new = surface_trace(drive_new(one))
    assert old["phantom_table"] == new["phantom_table"]
    produced = set(REAL_PHANTOM_STATUS)
    assert "get_status" in members(PhantomBalanceBot)
    assert surface.PNL_KEY not in produced, sorted(produced)
    assert "realised_pnl" in produced
    assert old["phantom_table"]["rows"][0][surface.PNL_COLUMN] == "$+0.0000"
    assert REAL_PHANTOM_STATUS["realised_pnl"] != 0


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


@pytest.fixture
def fresh_pane_model():
    """Put the tab state the bridge keeps back exactly as it was found."""
    first = surface.PANE_MODEL
    surface.PANE_MODEL = surface.PhantomBotsTabModel()
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
    "exchange_id": "coinbase",
    "enabled": True,
    "started": True,
    "timeframes": ["1h", "1d"],
    "locked": True,
    "lock_timeframe": "6h",
    "bot_id": "BOT-1",
    "lock_candle_count": 3,
    "phantoms": STATUSES_HAPPY,
    "locks": LOCKS_HAPPY,
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_phantom_bots_method():
    """The renderer cannot reach the Phantom Bots tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "phantom_bots_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["phantom_table"]["columns"] == list(surface.PHANTOM_COLUMNS)
    assert result["enable_check"]["text"] == surface.ENABLE_CHECK_TEXT


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_tab_state_on_request():
    """The tab state the bridge keeps was never cleared."""
    filled = bridge_answer({"reset": True, "bot": BRIDGE_BOT})["result"]
    assert filled["phantom_table"]["row_count"] == 3
    assert filled["locks_table"]["row_count"] == 3
    assert filled["lock_spin"]["value"] == 3
    kept = bridge_answer({})["result"]
    assert kept["phantom_table"]["row_count"] == 3
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["phantom_table"]["row_count"] == 0
    assert cleared["locks_table"]["row_count"] == 0
    assert cleared["empty_label"]["shown"] is False
    assert cleared["calls"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_runs_a_step_sequence():
    """A step taken over the bridge reached no control at all."""
    answer = bridge_answer(
        {
            "reset": True,
            "bot": BRIDGE_BOT,
            "steps": [["build"], ["enable", False], ["lock", 99]],
        }
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["enable_check"]["checked"] is False
    assert result["lock_spin"]["value"] == surface.LOCK_MAX
    assert result["changes"] == [
        [surface.ENABLE_FIELD, False],
        [surface.LOCK_FIELD, surface.LOCK_MAX],
    ]
    refused = bridge_answer(
        {"reset": True, "bot": BRIDGE_BOT, "steps": [["build"], ["timeframe", "9h", 1]]}
    )
    assert refused["ok"] is True
    assert refused["result"]["changes"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reset": True, "bot": BRIDGE_BOT})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["phantom_table"]["row_count"] == 3
    assert encoded["result"]["summary_rows"][0][1] == surface.YES_TEXT


BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'phantom_bots_tab.state', 'params': {'reset': True,\n"
    "    'bot': {'exchange_id': 'coinbase', 'enabled': True, 'started': True,\n"
    "    'timeframes': ['1h'], 'bot_id': 'BOT-1', 'lock_candle_count': 4,\n"
    "    'phantoms': [{'timeframe': '1h', 'state': 'RUNNING',\n"
    "    'target_balance': 250.0, 'total_trades': 6,\n"
    "    'realized_pnl_exchange': 12.5,\n"
    "    'last_summary': {'bullish': 4, 'bearish': 1, 'confidence': 0.66}}],\n"
    "    'locks': [{'source_tf': '6h', 'source_bot': 'BOT-1',\n"
    "    'locked_direction': 'BULLISH', 'candles_remaining': 2}]}}}),\n"
    "    desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules,\n"
    "    'reached': REACHED, 'opened': OPENED, 'written': WRITTEN,\n"
    "    'home': str(HOME),\n"
    "    'made': sorted(str(one) for one in HOME.rglob('*'))}))\n"
)

WATCH_PRELUDE = """
import builtins, os, socket, sys, tempfile
from pathlib import Path

HOME = Path(tempfile.mkdtemp(prefix='acervator-phantom-'))
os.environ['HOME'] = str(HOME)
os.environ['USERPROFILE'] = str(HOME)
os.environ.pop('ACERVATOR_TEST_HOME', None)

OPENED = []
WRITTEN = []
REACHED = []
_real_open = open


def _watched_open(file, mode='r', *found, **named):
    OPENED.append(str(file))
    if set(mode) & set('wxa+'):
        WRITTEN.append(str(file))
    return _real_open(file, mode, *found, **named)


def _refuse(address, *found, **named):
    REACHED.append(str(address))
    raise OSError('this probe may not reach outside the process')


builtins.open = _watched_open
socket.create_connection = _refuse
socket.socket.connect = lambda self, address, *a, **k: _refuse(address)
"""

REACH_OUT = (
    "import socket\n"
    "try:\n"
    "    socket.create_connection(('a-host-nobody-runs.invalid', 443), timeout=1)\n"
    "except Exception:\n"
    "    pass\n"
)


def run_probe(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    where["PYTHONPATH"] = str(REPO_ROOT)
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
    """Reaching the Phantom Bots tab pulled Qt into the backend."""
    answered = run_probe(WATCH_PRELUDE + BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["phantom_table"]["rows"] == [
        ["1h", "RUNNING", "$250.00", "6", "$+12.5000", "4/1", "66.00%"]
    ]
    assert result["locks_table"]["rows"] == [["6h", "BOT-1 (this bot)", "BULLISH", "2"]]
    assert result["lock_spin"]["value"] == 4
    assert len(result["allowed_timeframes"]) == 8


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe(WATCH_PRELUDE + "import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_a_child_process_writes_no_file_under_a_throwaway_home():
    """Answering over the bridge wrote into the operator's own tree."""
    answered = run_probe(WATCH_PRELUDE + BRIDGE_PROBE)
    assert answered["made"] == [], answered["made"]
    under_home = [one for one in answered["opened"] if answered["home"] in one]
    assert under_home == [], under_home
    assert answered["written"] == [], answered["written"]


def test_the_throwaway_home_check_in_a_child_can_report_a_file():
    """The throwaway-home check reports nothing whatever a child writes."""
    seeded = run_probe(
        WATCH_PRELUDE
        + "with open(HOME / 'seeded.json', 'w', encoding='utf-8',\n"
        + "          newline='\\n') as seed:\n"
        + "    seed.write('{}')\n"
        + BRIDGE_PROBE
    )
    assert [Path(one).name for one in seeded["made"]] == ["seeded.json"], seeded["made"]
    under_home = [one for one in seeded["opened"] if seeded["home"] in one]
    assert [Path(one).name for one in under_home] == ["seeded.json"], under_home
    assert [Path(one).name for one in seeded["written"]] == ["seeded.json"]


def test_a_child_process_makes_no_connection():
    """Answering over the bridge reached outside the process."""
    answered = run_probe(WATCH_PRELUDE + BRIDGE_PROBE)
    assert answered["reached"] == [], answered["reached"]


def test_the_connection_counter_reaches_the_child_process():
    """The connection counter reports nothing whatever a child reaches for."""
    reached = run_probe(WATCH_PRELUDE + REACH_OUT + BRIDGE_PROBE)
    assert len(reached["reached"]) == 1, reached["reached"]
    assert "a-host-nobody-runs.invalid" in reached["reached"][0]
    assert reached["frame"]["ok"] is True


# ---------------------------------------------------------------------
# The throwaway home and the network, in this process
# ---------------------------------------------------------------------


@pytest.fixture
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    Each test is given its own counter, so the number never depends on
    what ran before it.
    """
    attempted: list = []

    def refuse(where):
        attempted.append(where)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *_found, **_named):
        return refuse(address)

    def watched_create(address, *_found, **_named):
        return refuse(address)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", watched_connect)
    monkeypatch.setattr(socket, "create_connection", watched_create)
    yield attempted


def test_no_driven_case_makes_a_connection(refuse_outside_connections):
    """A driven case reached outside the process."""
    app()
    for one in SPECS:
        old_outcome(one)
        new_outcome(one)
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_a_connection(refuse_outside_connections):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("a-host-nobody-runs.invalid", 443)
    second = ("another-host-nobody-runs.invalid", 80)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections
    assert second in refuse_outside_connections


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    app()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ACERVATOR_TEST_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for one in SPECS:
        old_outcome(one)
        new_outcome(one)
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


# ---------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------


class CountedClock:
    """Count every clock reading taken while it is in place."""

    def __init__(self):
        self.reads: list = []
        self.first = (
            time.time,
            time.monotonic,
            time.perf_counter,
            datetime.datetime,
        )

    def __enter__(self):
        counter = self

        class Stopped(self.first[3]):
            @classmethod
            def now(cls, tz=None):
                counter.reads.append("datetime.now")
                return cls(2026, 1, 1, tzinfo=tz)

        time.time = lambda: counter.reads.append("time") or 0.0
        time.monotonic = lambda: counter.reads.append("monotonic") or 0.0
        time.perf_counter = lambda: counter.reads.append("perf_counter") or 0.0
        datetime.datetime = Stopped
        return self

    def __exit__(self, _kind, _value, _trace):
        time.time, time.monotonic, time.perf_counter = self.first[:3]
        datetime.datetime = self.first[3]
        return False


def test_neither_side_reads_the_clock():
    """A value on the screen changes with the time of day."""
    app()
    with CountedClock() as counted:
        drive_old(BY_NAME["happy"])
        drive_new(BY_NAME["happy"])
        quiet = list(counted.reads)
        time.time()
        datetime.datetime.now()
        loud = list(counted.reads)
    assert quiet == [], quiet
    assert loud == ["time", "datetime.now"], loud
    assert time.time is not None
    assert datetime.datetime(2026, 1, 1).year == 2026


def test_the_clock_is_put_back_after_a_run_that_refuses():
    """A stopped clock was left in place for every later test."""
    app()
    before = (time.time, time.monotonic, time.perf_counter, datetime.datetime)
    with CountedClock():
        with pytest.raises(Exception):
            drive_new(BY_NAME["lock_count_is_text"])
    assert (time.time, time.monotonic, time.perf_counter, datetime.datetime) == before
    assert time.time() > 0


# ---------------------------------------------------------------------
# Order independence
# ---------------------------------------------------------------------


def test_each_side_holds_its_own_bot_and_its_own_model():
    """The two sides shared an object, so one could move the other."""
    one = BY_NAME["happy"]
    old = drive_old(one)
    new = drive_new(one)
    assert old["bot"] is not new["bot"]
    assert type(old["bot"]) is not type(new["bot"])
    assert old["bot"]._phantom_mgr is not new["bot"]._phantom_mgr
    assert old["host"]._phantom_tf_checks is not new["model"].timeframe_checks
    assert type(old["bot"]).__module__ == __name__
    assert type(new["bot"]).__module__ == surface.__name__


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_shared_tab_state_is_put_back_after_a_bridge_call():
    """The tab state the bridge keeps leaked into every later test."""
    first = surface.PANE_MODEL
    bridge_answer({"reset": True, "bot": BRIDGE_BOT})
    assert surface.PANE_MODEL is not first
    assert surface.PANE_MODEL.phantom_count == 3


def test_the_swapped_token_table_is_watched_during_the_drive(monkeypatch):
    """A swap was read after the drive, so it proves nothing about the drive."""
    app()
    from src.gui.live_settings import phantom_bots_tab as shipped

    first = shipped.ds
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    during = shipped.ds
    moved = qt_trace(drive_old(BY_NAME["happy"]))
    assert during is MovedTokens
    assert shipped.ds is MovedTokens, "the swap did not hold for the whole drive"
    assert MovedTokens.SUCCESS in moved["summary_rows"][0][2]
    monkeypatch.undo()
    assert shipped.ds is first


def test_the_swapped_token_table_is_put_back_after_a_refusal(monkeypatch):
    """A swap was left in place because the drive refused before the undo."""
    app()
    from src.gui.live_settings import phantom_bots_tab as shipped

    first = shipped.ds
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    with pytest.raises(Exception):
        drive_old(BY_NAME["lock_count_is_text"])
    assert shipped.ds is MovedTokens
    monkeypatch.undo()
    assert shipped.ds is first
    assert qt_trace(drive_old(BY_NAME["happy"]))["summary_rows"][0][2] == (
        surface.FLAG_STYLE_FORMAT.format(color_hex=surface.ON_COLOR)
    )


def test_the_file_reads_no_state_another_test_left_behind():
    """A test read a value an earlier test wrote, so the order decides it."""
    one = BY_NAME["happy"]
    first = digest(new_outcome(one)["value"])
    for other in ("no_phantoms_and_no_locks", "a_full_sequence", "many_phantoms"):
        new_outcome(BY_NAME[other])
    assert digest(new_outcome(one)["value"]) == first
    assert digest(old_outcome(one)["value"]) == first


# ---------------------------------------------------------------------
# The file runs in the CI fast lane
# ---------------------------------------------------------------------


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences
