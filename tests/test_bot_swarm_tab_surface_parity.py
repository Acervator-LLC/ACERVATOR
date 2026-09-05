"""The Qt Bot Swarm tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different row, a different
cell, a different table, a different count, a different number format, a
different refusal or a different step order than ``BotSwarmTabMixin``
builds on the same stored fleet.
"""

from __future__ import annotations

import ast
import gc
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMetaMethod, QTimer
from PySide6.QtWidgets import QApplication, QHeaderView, QTableWidget, QWidget

from src.gui.main_tabs import bot_swarm_tab_surface as surface
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
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "bot_swarm_tab.py"
TAB_NAMESAKE = REPO_ROOT / "src" / "gui" / "main_tabs" / "bot_swarm_tab.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "bot_swarm_tab_surface.py"

NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"
NESTED_METHOD_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (980, 720)
SKIN_CONTROL_RULE = (
    "QGroupBox { border: 3px solid #7a1414; } QLabel { background: #201038; }"
)
HOST_ACCESSIBLE_NAME = "Bot Swarm parity dialog"

MODEL_STATE_FIELDS = (
    "active",
    "calls",
    "empty_shown",
    "forms_configured",
    "inbound_count",
    "inbound_rows",
    "inbound_shown",
    "inbound_title",
    "mature_ratio_pct",
    "mature_refused",
    "not_active_shown",
    "outbound_count",
    "outbound_rows",
    "outbound_shown",
    "outbound_title",
    "pending_rows",
    "pending_shown",
    "pending_title",
    "predominant_refused",
    "provenance_breakdown",
    "provenance_rows",
    "provenance_shown",
    "provenance_styles",
    "provenance_wraps",
    "summary_rows",
    "summary_shown",
    "summary_styles",
    "transactions_colours",
    "transactions_rows",
    "transactions_shown",
    "transactions_title",
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


_LIVE: list = []


def live(widget):
    """Keep `widget` alive until the running test ends, then destroy it."""
    _LIVE.append(widget)
    return widget


def destroy(widget) -> None:
    """Take `widget` down now, so no drive holds a tree it has read."""
    if widget in _LIVE:
        _LIVE.remove(widget)
    widget.setParent(None)
    widget.deleteLater()
    QApplication.processEvents()


@pytest.fixture(autouse=True)
def destroy_every_widget_this_test_built():
    """Destroy each test's widgets rather than carrying them all."""
    yield
    while _LIVE:
        widget = _LIVE.pop()
        widget.setParent(None)
        widget.deleteLater()
    if QApplication.instance() is not None:
        QApplication.processEvents()


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


# Both sides are handed the SAME stored rows and each loads them with its
# own stand-in.


class QtLedger:
    """One bot's wire ledger, as the manager holds it after a restore."""

    def __init__(self, row: dict):
        self.bot_id = row.get("bot_id", "")
        self.asset = row.get("asset", "")
        self.wired_in = row.get("wired_in", 0.0)
        self.wired_out = row.get("wired_out", 0.0)
        self.starting_balance = row.get("starting_balance", 0.0)
        self.provenance = row.get("provenance") or {}
        self.mature_profit_allocated = row.get("mature_profit_allocated", 0.0)
        self.mature_profit_total = row.get("mature_profit_total", 0.0)
        self.mature_profit_available = row.get("mature_profit_available", 0.0)
        self._named_source = row.get("predominant_source")
        self._raises = row.get("predominant_raises")

    @property
    def predominant_source(self):
        if self._raises is not None:
            raise self._raises
        if self._named_source is not None:
            return self._named_source
        funders = {
            key: value
            for key, value in dict(self.provenance).items()
            if key != "SEED" and value > 0
        }
        if not funders:
            return None
        return max(funders, key=funders.get)


class QtWire:
    """One wire event, as the manager's event feed holds it."""

    def __init__(self, row: dict):
        self.timestamp = row.get("timestamp", 0)
        self.source_bot = row.get("source_bot", "")
        self.target_bot = row.get("target_bot", "")
        self.amount = row.get("amount", 0.0)
        self.wire_type = row.get("wire_type", "")


class QtFleet:
    """The Smart Wire manager, loaded from stored rows with no coercion."""

    def __init__(self, stored: dict):
        self._wires: dict = {}
        for row in stored.get("wires") or []:
            self._wires.setdefault(row.get("source_id", ""), {})[
                row.get("target_id", "")
            ] = row.get("pct")
        self._ledgers = {
            row.get("bot_id", ""): QtLedger(row) for row in stored.get("ledgers") or []
        }
        self._transactions = [QtWire(row) for row in stored.get("transactions") or []]
        self._bot_refs = dict(stored.get("bot_refs") or {})


class QtBot:
    """The bot the Qt tab reads its swarm state off."""

    def __init__(self, spec: dict):
        self.bot_id = spec["bot_id"]
        stored = spec["fleet"]
        self._smart_wire_mgr = None if stored is None else QtFleet(stored)
        self._pending_wire_credits = spec["pending_credits"]
        self._pending_wire_ledger = list(spec["pending_ledger"])


def host_class():
    """The dialog the tab lives in, holding only what the mixin needs."""
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.gui.live_settings.bot_swarm_tab import BotSwarmTabMixin

    class Host(BotSwarmTabMixin, QWidget):
        _format_age = staticmethod(BotLiveSettingsDialog._format_age)

        def __init__(self, bot):
            super().__init__()
            self.setAccessibleName(HOST_ACCESSIBLE_NAME)
            self._bot = bot
            self.forms: list = []

        def _configure_form(self, form):
            self.forms.append(form)
            BotLiveSettingsDialog._configure_form(self, form)

    return Host


# One stored topology in the shape export_wires and export_ledgers write;
# every scenario is that topology with one value replaced.


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's pair"
WRONG_CAPITALS = "mR_fUnD"

HUGE_INT_UNDER = 2**1023
HUGE_INT_OVER = 2**1024
HUGE_INT_DECIMAL = 10**400

MINE = "BOT-A"
NOW_TS = 1_755_600_000.0
OLDER_TS = 1_755_000_000
RECENT_TS = 1_755_599_900


def wire_row(source, target, pct):
    """One saved wire, in the shape export_wires writes."""
    return {"source_id": source, "target_id": target, "pct": pct}


def ledger_row(bot_id, **named):
    """One saved ledger, in the shape export_ledgers writes."""
    row = {
        "bot_id": bot_id,
        "asset": "",
        "total_profit": 0.0,
        "available_profit": 0.0,
        "wired_in": 0.0,
        "wired_out": 0.0,
        "provenance": {},
        "starting_balance": 0.0,
        "mature_profit_allocated": 0.0,
        "mature_profit_total": 0.0,
        "mature_profit_available": 0.0,
    }
    row.update(named)
    return row


def tx_row(**named):
    """One wire event, as the manager appends it."""
    row = {
        "timestamp": OLDER_TS,
        "source_bot": MINE,
        "target_bot": "BOT-B",
        "amount": 12.5,
        "wire_type": "WIRE_BACK",
    }
    row.update(named)
    return row


def credit_row(**named):
    """One parked wire credit, as the bot restores it verbatim."""
    row = {"ts": OLDER_TS, "source": "BOT-D", "usd": 3.25, "ref": "fold-991"}
    row.update(named)
    return row


BASE_WIRES = [
    wire_row(MINE, "BOT-B", 12.5),
    wire_row(MINE, "BOT-C", 7.25),
    wire_row("BOT-D", MINE, 3.5),
    wire_row("BOT-E", MINE, 40.0),
    wire_row("BOT-D", "BOT-E", 5.0),
]

BASE_LEDGERS = [
    ledger_row(
        MINE,
        asset="BTC",
        wired_in=120.5,
        wired_out=45.25,
        starting_balance=500.0,
        provenance={"SEED": 400.0, "BOT-D": 100.5},
        mature_profit_allocated=30.0,
        mature_profit_total=210.0,
        mature_profit_available=180.0,
    ),
    ledger_row("BOT-B", asset="ETH"),
    ledger_row("BOT-C", asset="SOL"),
    ledger_row("BOT-D", asset="DOGE"),
    ledger_row("BOT-E", asset="LTC"),
]

BASE_TRANSACTIONS = [
    tx_row(),
    tx_row(target_bot="BOT-C", amount=4.75, timestamp=RECENT_TS),
    tx_row(source_bot="BOT-D", target_bot=MINE, amount=9.5, wire_type="MR_FUND"),
    tx_row(source_bot="BOT-E", target_bot=MINE, amount=1.25, timestamp=RECENT_TS),
    tx_row(source_bot="BOT-D", target_bot="BOT-E", amount=88.0),
]

BASE_CREDITS = [
    credit_row(),
    credit_row(ts=RECENT_TS, source="BOT-E", usd=0.75, ref="fold-992"),
]


def fleet(**named):
    """The stored fleet, with the named rows replaced."""
    stored = {
        "wires": BASE_WIRES,
        "ledgers": BASE_LEDGERS,
        "transactions": BASE_TRANSACTIONS,
        "bot_refs": {MINE: "bot-a-ref"},
    }
    stored.update(named)
    return stored


def mine_with(**named):
    """The stored fleet whose inspected bot's ledger carries `named`."""
    return fleet(ledgers=[ledger_row(MINE, **named)] + BASE_LEDGERS[1:])


def outbound_pct(value):
    """The stored fleet whose one outbound wire carries `value`."""
    return fleet(wires=[wire_row(MINE, "BOT-B", value)] + BASE_WIRES[2:])


def inbound_pct(value):
    """The stored fleet whose one inbound wire carries `value`."""
    return fleet(wires=BASE_WIRES[:2] + [wire_row("BOT-D", MINE, value)])


def scenario(name, **named):
    """One driving set: the bot id, the stored fleet and the clock."""
    spec = {
        "name": name,
        "bot_id": MINE,
        "fleet": fleet(),
        "pending_credits": 12.5,
        "pending_ledger": BASE_CREDITS,
        "now_ts": NOW_TS,
    }
    spec.update(named)
    return spec


SCENARIOS = [
    scenario("happy"),
    scenario("no_manager_attached", fleet=None),
    scenario(
        "an_empty_fleet",
        fleet=fleet(wires=[], ledgers=[], transactions=[], bot_refs={}),
        pending_credits=0,
        pending_ledger=[],
    ),
    scenario(
        "one_bot_and_nothing_else",
        fleet=fleet(wires=[], ledgers=[ledger_row(MINE, asset="BTC")], transactions=[]),
        pending_credits=0,
        pending_ledger=[],
    ),
    scenario(
        "no_wires_but_a_ledger",
        fleet=fleet(wires=[], transactions=[]),
        pending_credits=0,
        pending_ledger=[],
    ),
    scenario("no_pending_credits", pending_credits=0, pending_ledger=[]),
    scenario(
        "a_bot_the_fleet_does_not_know",
        bot_id="BOT-Z",
        pending_credits=0,
        pending_ledger=[],
    ),
    scenario("zero_everywhere", fleet=mine_with(asset="BTC")),
    scenario(
        "negative_everywhere",
        fleet=mine_with(
            asset="BTC",
            wired_in=-10.0,
            wired_out=-4.0,
            starting_balance=-1.0,
            mature_profit_total=-2.0,
            mature_profit_available=-3.0,
            mature_profit_allocated=-4.0,
            provenance={"BOT-D": -5.0},
        ),
    ),
    scenario(
        "a_thousand_million",
        fleet=mine_with(
            asset="BTC",
            wired_in=1e9,
            wired_out=1e9,
            starting_balance=1e9,
            mature_profit_total=1e9,
            mature_profit_available=1e9,
            provenance={"BOT-D": 1e9},
        ),
    ),
    scenario(
        "one_billionth",
        fleet=mine_with(
            asset="BTC",
            wired_in=1e-9,
            wired_out=1e-9,
            starting_balance=1e-9,
            mature_profit_total=1e-9,
            mature_profit_available=1e-9,
            provenance={"BOT-D": 1e-9},
        ),
    ),
    scenario("unicode_asset", fleet=mine_with(asset=UNICODE_TEXT)),
    scenario(
        "unicode_wire_type",
        fleet=fleet(transactions=[tx_row(wire_type=UNICODE_TEXT)]),
    ),
    scenario("a_two_hundred_character_asset", fleet=mine_with(asset=LONG_TEXT)),
    scenario("markup_in_an_asset", fleet=mine_with(asset=MARKUP_TEXT)),
    scenario(
        "an_apostrophe_in_a_credit_ref",
        pending_ledger=[credit_row(ref=APOSTROPHE_TEXT)],
    ),
    scenario(
        "a_newline_in_a_credit_source", pending_ledger=[credit_row(source=NEWLINE_TEXT)]
    ),
    scenario(
        "wrong_capitals_in_a_wire_type",
        fleet=fleet(transactions=[tx_row(wire_type=WRONG_CAPITALS)]),
    ),
    scenario("a_number_where_an_asset_belongs", fleet=mine_with(asset=7)),
    scenario("a_number_where_a_credit_ref_belongs", pending_ledger=[credit_row(ref=7)]),
    scenario(
        "text_where_a_credit_amount_belongs", pending_ledger=[credit_row(usd="3.25")]
    ),
    scenario(
        "text_where_a_wired_in_belongs", fleet=mine_with(asset="BTC", wired_in="120.5")
    ),
    scenario(
        "text_where_a_mature_profit_belongs",
        fleet=mine_with(asset="BTC", mature_profit_total="12.7"),
    ),
    scenario(
        "unreadable_text_where_a_mature_profit_belongs",
        fleet=mine_with(asset="BTC", mature_profit_total="abc"),
    ),
    scenario(
        "infinity",
        fleet=mine_with(
            asset="BTC",
            wired_in=float("inf"),
            wired_out=float("inf"),
            starting_balance=float("inf"),
            mature_profit_total=float("inf"),
            mature_profit_available=float("inf"),
        ),
    ),
    scenario(
        "minus_infinity",
        fleet=mine_with(
            asset="BTC",
            wired_in=float("-inf"),
            wired_out=float("-inf"),
            starting_balance=float("-inf"),
            mature_profit_total=float("-inf"),
            mature_profit_available=float("-inf"),
        ),
    ),
    scenario(
        "not_a_number",
        fleet=mine_with(
            asset="BTC",
            wired_in=float("nan"),
            wired_out=float("nan"),
            starting_balance=float("nan"),
            mature_profit_total=float("nan"),
            mature_profit_available=float("nan"),
            provenance={"BOT-D": float("nan")},
        ),
    ),
    scenario(
        "not_a_number_in_a_second_place",
        fleet=mine_with(asset="BTC", wired_in=float("nan"), wired_out=1.0),
    ),
    scenario(
        "a_huge_whole_number_inside_the_float_range",
        fleet=mine_with(
            asset="BTC", wired_in=HUGE_INT_UNDER, starting_balance=HUGE_INT_UNDER
        ),
    ),
    scenario(
        "a_huge_whole_number_outside_the_float_range",
        fleet=mine_with(
            asset="BTC", wired_in=HUGE_INT_OVER, starting_balance=HUGE_INT_OVER
        ),
    ),
    scenario(
        "a_stored_true_where_money_belongs",
        fleet=mine_with(
            asset="BTC", wired_in=True, wired_out=True, starting_balance=True
        ),
        pending_credits=True,
    ),
    scenario(
        "a_stored_true_in_a_credit",
        pending_ledger=[credit_row(ts=True, usd=True)],
    ),
    scenario("an_outbound_percent_of_twelve", fleet=outbound_pct(12)),
    scenario("an_outbound_percent_of_twelve_point_zero", fleet=outbound_pct(12.0)),
    scenario(
        "an_outbound_percent_that_is_not_a_number", fleet=outbound_pct(float("nan"))
    ),
    scenario("an_outbound_percent_of_infinity", fleet=outbound_pct(float("inf"))),
    scenario("an_outbound_percent_that_is_a_stored_true", fleet=outbound_pct(True)),
    scenario(
        "an_inbound_percent_that_is_not_a_number", fleet=inbound_pct(float("nan"))
    ),
    scenario("an_inbound_percent_that_is_text", fleet=inbound_pct("3.5")),
    scenario("an_inbound_percent_that_is_a_stored_true", fleet=inbound_pct(True)),
    scenario(
        "a_wire_event_amount_that_is_not_a_number",
        fleet=fleet(transactions=[tx_row(amount=float("nan"))] + BASE_TRANSACTIONS),
    ),
    scenario(
        "a_wire_event_time_that_is_not_a_number",
        fleet=fleet(transactions=[tx_row(timestamp=float("nan"))]),
    ),
    scenario(
        "a_predominant_funder_that_refuses",
        fleet=mine_with(asset="BTC", predominant_raises=ValueError("no funder")),
    ),
    scenario(
        "more_wire_events_than_the_tab_shows",
        fleet=fleet(transactions=[tx_row(amount=float(n)) for n in range(30)]),
    ),
]

REFUSING_SCENARIOS = [
    scenario("a_parked_credit_that_is_not_a_record", pending_ledger=["not a record"]),
    scenario(
        "a_second_parked_credit_that_is_not_a_record",
        pending_ledger=[credit_row(usd=5.0), "not a record"],
    ),
]

EXPECTED_REFUSALS = {
    "a_parked_credit_that_is_not_a_record": (AttributeError, surface.STEP_PENDING),
    "a_second_parked_credit_that_is_not_a_record": (
        AttributeError,
        surface.STEP_PENDING,
    ),
}

UNREADABLE_SCENARIOS = [
    scenario(
        "a_provenance_amount_that_is_text",
        fleet=mine_with(asset="BTC", provenance={"BOT-D": "100.5"}),
    ),
    scenario(
        "a_provenance_amount_outside_the_float_range",
        fleet=mine_with(asset="BTC", provenance={"BOT-D": HUGE_INT_DECIMAL}),
    ),
    scenario("an_outbound_percent_that_is_text", fleet=outbound_pct("12.5")),
    scenario("an_outbound_percent_that_is_missing", fleet=outbound_pct(None)),
    scenario(
        "an_outbound_percent_outside_the_float_range",
        fleet=outbound_pct(HUGE_INT_DECIMAL),
    ),
]

#: The cell each stored value no reading admits has to reach.
UNREADABLE_READERS = {
    "a_provenance_amount_that_is_text": "provenance_amount",
    "a_provenance_amount_outside_the_float_range": "provenance_amount",
    "an_outbound_percent_that_is_text": "outbound_percent",
    "an_outbound_percent_that_is_missing": "outbound_percent",
    "an_outbound_percent_outside_the_float_range": "outbound_percent",
}

BY_NAME = {
    spec["name"]: spec for spec in SCENARIOS + REFUSING_SCENARIOS + UNREADABLE_SCENARIOS
}
SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
REFUSING_NAMES = [spec["name"] for spec in REFUSING_SCENARIOS]
UNREADABLE_NAMES = [spec["name"] for spec in UNREADABLE_SCENARIOS]


# Driving the two sides


class FrozenClock:
    """A clock that answers one epoch second, and counts who asked."""

    def __init__(self, at):
        self.at = at
        self.asked = 0

    def __call__(self):
        self.asked += 1
        return self.at


def build_qt(spec, monkeypatch):
    """Build the Qt tab against the scenario's own clock reading."""
    app()
    import time as time_module

    clock = FrozenClock(spec["now_ts"])
    monkeypatch.setattr(time_module, "time", clock)
    host = live(host_class()(QtBot(spec)))
    tab = host._create_bot_swarm_tab()
    return {"tab": live(tab), "host": host, "clock": clock}


def build_surface(spec):
    """Build the surface model against the scenario's own epoch second."""
    model = surface.BotSwarmTabModel(
        surface.BotSource(
            bot_id=spec["bot_id"],
            fleet=(
                None
                if spec["fleet"] is None
                else surface.FleetLoad(
                    wires=spec["fleet"].get("wires"),
                    ledgers=spec["fleet"].get("ledgers"),
                    transactions=spec["fleet"].get("transactions"),
                    bot_refs=spec["fleet"].get("bot_refs"),
                )
            ),
            pending_credits=spec["pending_credits"],
            pending_ledger=spec["pending_ledger"],
        )
    )
    model.build(spec["now_ts"])
    return model


# Reading the two sides. Neither reader touches a style, a palette, a
# brush or a property on a live object: the skin is proved by rendering.


def group_boxes(tab):
    """Every group the tab put in its column, in order."""
    from PySide6.QtWidgets import QGroupBox

    layout = tab.layout()
    found = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QGroupBox):
            found.append(widget)
    return found


def loose_labels(tab):
    """Every label the tab put straight into its column, in order."""
    from PySide6.QtWidgets import QGroupBox, QLabel

    layout = tab.layout()
    return [
        layout.itemAt(index).widget()
        for index in range(layout.count())
        if isinstance(layout.itemAt(index).widget(), QLabel)
        and not isinstance(layout.itemAt(index).widget(), QGroupBox)
    ]


def form_rows(group):
    """One group's form, as label text against field text."""
    from PySide6.QtWidgets import QFormLayout

    form = group.layout()
    rows = []
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.ItemRole.LabelRole).widget()
        field = form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
        rows.append([label.text(), field.text()])
    return rows


def form_wraps(group):
    """Whether each field in one group's form wraps its text."""
    from PySide6.QtWidgets import QFormLayout

    form = group.layout()
    return [
        form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget().wordWrap()
        for index in range(form.rowCount())
    ]


def edit_trigger_name(table):
    """The table's edit rule, named rather than compared as a number."""
    if table.editTriggers() == QTableWidget.NoEditTriggers:
        return "NoEditTriggers"
    return repr(table.editTriggers())


def resize_mode_names(table):
    """Each column's resize rule, named rather than compared as a number."""
    header = table.horizontalHeader()
    names = []
    for column in range(table.columnCount()):
        mode = header.sectionResizeMode(column)
        names.append(
            "ResizeToContents" if mode == QHeaderView.ResizeToContents else repr(mode)
        )
    return names


def table_trace(group):
    """One table group, as plain data. `None` when the group is absent."""
    if group is None:
        return {"shown": False}
    table = group.layout().itemAt(0).widget()
    return {
        "shown": True,
        "title": group.title(),
        "column_count": table.columnCount(),
        "headers": [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ],
        "row_count": table.rowCount(),
        "cells": [
            [
                (
                    None
                    if table.item(row, column) is None
                    else table.item(row, column).text()
                )
                for column in range(table.columnCount())
            ]
            for row in range(table.rowCount())
        ],
        "max_height_px": table.maximumHeight(),
        "alternating": table.alternatingRowColors(),
        "edit_triggers": edit_trigger_name(table),
        "resize_modes": resize_mode_names(table),
    }


def layout_order(tab):
    """The class of each item the tab's column holds, in order."""
    layout = tab.layout()
    order = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        order.append("stretch" if widget is None else type(widget).__name__)
    return order


def qt_trace(built):
    """Every value the Qt tab shows, as plain data."""
    tab = built["tab"]
    groups = {group.title(): group for group in group_boxes(tab)}
    summary = groups.get(surface.SUMMARY_GROUP_TITLE)
    provenance = groups.get(surface.PROVENANCE_GROUP_TITLE)
    tables = {}
    for prefix, key in (
        ("Outbound Wires", "outbound"),
        ("Inbound Wires", "inbound"),
        ("Pending Wire Credits", "pending"),
        ("Recent Wire Transactions", "transactions"),
    ):
        found = [group for title, group in groups.items() if title.startswith(prefix)]
        tables[key] = table_trace(found[0] if found else None)
    labels = loose_labels(tab)
    inactive = labels[0] if labels and not built["host"].forms else None
    empty = labels[0] if labels and built["host"].forms else None
    return {
        "accessible_name": tab.accessibleName(),
        "spacing_px": tab.layout().spacing(),
        "layout_order": layout_order(tab),
        "forms_configured": len(built["host"].forms),
        "not_active": {
            "shown": inactive is not None,
            "text": None if inactive is None else inactive.text(),
            "word_wrap": None if inactive is None else inactive.wordWrap(),
        },
        "summary": {
            "shown": summary is not None,
            "rows": [] if summary is None else form_rows(summary),
        },
        "provenance": {
            "shown": provenance is not None,
            "rows": [] if provenance is None else form_rows(provenance),
            "word_wraps": [] if provenance is None else form_wraps(provenance),
        },
        "outbound": tables["outbound"],
        "inbound": tables["inbound"],
        "pending": tables["pending"],
        "transactions": tables["transactions"],
        "empty": {
            "shown": empty is not None,
            "text": None if empty is None else empty.text(),
            "word_wrap": None if empty is None else empty.wordWrap(),
        },
    }


def surface_table(payload, key, headers, max_height):
    """The same table values, read off the surface's own payload."""
    block = payload[key]
    if not block["shown"]:
        return {"shown": False}
    return {
        "shown": True,
        "title": block["title"],
        "column_count": len(headers),
        "headers": list(headers),
        "row_count": len(block["rows"]),
        "cells": [list(row) for row in block["rows"]],
        "max_height_px": max_height,
        "alternating": surface.TABLE_ALTERNATING_ROWS,
        "edit_triggers": surface.TABLE_EDIT_TRIGGERS,
        "resize_modes": [surface.TABLE_RESIZE_MODE] * len(headers),
    }


def surface_trace(model):
    """The same values, read off the surface's own model."""
    payload = surface.build_view_model(model)
    order = []
    if payload["not_active_label"]["shown"]:
        order.append("QLabel")
    if payload["summary_group"]["shown"]:
        order.append("QGroupBox")
    for key in (
        "provenance_group",
        "outbound_table",
        "inbound_table",
        "pending_table",
        "transactions_table",
    ):
        if payload[key]["shown"]:
            order.append("QGroupBox")
    if payload["empty_label"]["shown"]:
        order.append("QLabel")
    order.append("stretch")
    return {
        "accessible_name": payload["accessible_name"],
        "spacing_px": payload["container"]["spacing_px"],
        "layout_order": order,
        "forms_configured": payload["summary_group"]["forms_configured"],
        "not_active": {
            "shown": payload["not_active_label"]["shown"],
            "text": (
                payload["not_active_label"]["text"]
                if payload["not_active_label"]["shown"]
                else None
            ),
            "word_wrap": (
                payload["not_active_label"]["word_wrap"]
                if payload["not_active_label"]["shown"]
                else None
            ),
        },
        "summary": {
            "shown": payload["summary_group"]["shown"],
            "rows": [list(row) for row in payload["summary_group"]["rows"]],
        },
        "provenance": {
            "shown": payload["provenance_group"]["shown"],
            "rows": [list(row) for row in payload["provenance_group"]["rows"]],
            "word_wraps": list(payload["provenance_group"]["word_wraps"]),
        },
        "outbound": surface_table(
            payload,
            "outbound_table",
            surface.OUTBOUND_HEADERS,
            surface.WIRE_TABLE_MAX_HEIGHT_PX,
        ),
        "inbound": surface_table(
            payload,
            "inbound_table",
            surface.INBOUND_HEADERS,
            surface.WIRE_TABLE_MAX_HEIGHT_PX,
        ),
        "pending": surface_table(
            payload,
            "pending_table",
            surface.PENDING_HEADERS,
            surface.WIRE_TABLE_MAX_HEIGHT_PX,
        ),
        "transactions": surface_table(
            payload,
            "transactions_table",
            surface.TRANSACTIONS_HEADERS,
            surface.TRANSACTIONS_TABLE_MAX_HEIGHT_PX,
        ),
        "empty": {
            "shown": payload["empty_label"]["shown"],
            "text": (
                payload["empty_label"]["text"]
                if payload["empty_label"]["shown"]
                else None
            ),
            "word_wrap": (
                payload["empty_label"]["word_wrap"]
                if payload["empty_label"]["shown"]
                else None
            ),
        },
    }


def traced_qt(spec, monkeypatch):
    """The Qt trace, with the tab destroyed as soon as it is read."""
    built = build_qt(spec, monkeypatch)
    trace = qt_trace(built)
    destroy(built["tab"])
    destroy(built["host"])
    return trace


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_tab(name, monkeypatch):
    """The view model describes a different tab than the Qt mixin builds."""
    spec = BY_NAME[name]
    old = traced_qt(spec, monkeypatch)
    new = surface_trace(build_surface(spec))
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
    old = digest(traced_qt(spec, monkeypatch))
    new = digest(surface_trace(build_surface(spec)))
    record_property("old_side", old)
    record_property("new_side", new)
    assert old == new, name


def test_the_hash_tells_two_different_answers_apart(monkeypatch):
    """The hash returns one value whatever the tab shows.

    Two genuinely different real inputs, one driven through each side,
    in both directions. A pass means the comparison reports.
    """
    happy = BY_NAME["happy"]
    other = BY_NAME["no_wires_but_a_ledger"]
    assert happy["fleet"]["wires"] != other["fleet"]["wires"]
    old_happy = digest(traced_qt(happy, monkeypatch))
    new_other = digest(surface_trace(build_surface(other)))
    assert old_happy != new_other
    old_other = digest(traced_qt(other, monkeypatch))
    new_happy = digest(surface_trace(build_surface(happy)))
    assert old_other != new_happy
    assert old_happy == new_happy
    assert old_other == new_other


def test_the_same_input_twice_gives_one_answer(monkeypatch):
    """A second build of one input answered differently."""
    spec = BY_NAME["happy"]
    first = digest(traced_qt(spec, monkeypatch))
    second = digest(traced_qt(spec, monkeypatch))
    assert first == second
    first_model = digest(surface_trace(build_surface(spec)))
    second_model = digest(surface_trace(build_surface(spec)))
    assert first_model == second_model
    assert first_model == first


def test_a_whole_number_and_a_decimal_print_alike_and_store_apart(monkeypatch):
    """A whole number and a decimal were told apart by a printed cell."""
    whole = BY_NAME["an_outbound_percent_of_twelve"]
    decimal = BY_NAME["an_outbound_percent_of_twelve_point_zero"]
    assert whole["fleet"]["wires"][0]["pct"] == decimal["fleet"]["wires"][0]["pct"]
    assert digest([12]) != digest([12.0])
    assert digest(traced_qt(whole, monkeypatch)) == digest(
        traced_qt(decimal, monkeypatch)
    )
    assert digest(surface_trace(build_surface(whole))) == digest(
        surface_trace(build_surface(decimal))
    )


def test_two_not_a_numbers_are_compared_as_the_text_they_print(monkeypatch):
    """A not-a-number was compared as a number and read as a difference."""
    first = float("nan")
    second = float("nan")
    assert first != second
    spec = AUDIT_SITES["mature_profit_total"](float("nan"))
    old = traced_qt(spec, monkeypatch)
    new = surface_trace(build_surface(spec))
    printed = [row[1] for row in old["provenance"]["rows"]]
    assert "$nan" in printed, printed
    assert new["provenance"]["rows"] == old["provenance"]["rows"]


def test_every_scenario_name_is_driven():
    """A scenario sits in the table and no test drives it."""
    assert len(SCENARIO_NAMES) == len(set(SCENARIO_NAMES))
    assert len(REFUSING_NAMES) == len(set(REFUSING_NAMES))
    assert len(UNREADABLE_NAMES) == len(set(UNREADABLE_NAMES))
    assert set(BY_NAME) == (
        set(SCENARIO_NAMES) | set(REFUSING_NAMES) | set(UNREADABLE_NAMES)
    )
    assert set(EXPECTED_REFUSALS) == set(REFUSING_NAMES)
    assert set(UNREADABLE_READERS) == set(UNREADABLE_NAMES)


# The steps, including the ones that refuse part way


@pytest.mark.parametrize("name", REFUSING_NAMES)
def test_both_sides_refuse_the_same_way(name, monkeypatch, record_property):
    """One side printed a value the other side refused to print."""
    spec = BY_NAME[name]
    wanted, step = EXPECTED_REFUSALS[name]
    with pytest.raises(wanted) as from_qt:
        traced_qt(spec, monkeypatch)
    model = surface.BotSwarmTabModel(
        surface.BotSource(
            bot_id=spec["bot_id"],
            fleet=surface.FleetLoad(
                wires=spec["fleet"].get("wires"),
                ledgers=spec["fleet"].get("ledgers"),
                transactions=spec["fleet"].get("transactions"),
            ),
            pending_credits=spec["pending_credits"],
            pending_ledger=spec["pending_ledger"],
        )
    )
    with pytest.raises(wanted) as from_surface:
        model.build(spec["now_ts"])
    assert type(from_surface.value) is type(from_qt.value)
    assert model.state.calls[-1] == step, model.state.calls
    record_property("step_index", len(model.state.calls) - 1)
    record_property("step_name", step)
    record_property("refusal", type(from_qt.value).__name__)


def test_a_refusal_keeps_every_step_recorded_before_it():
    """A refused build lost the steps it had already run."""
    spec = BY_NAME["a_parked_credit_that_is_not_a_record"]
    model = surface.BotSwarmTabModel(
        surface.BotSource(
            bot_id=spec["bot_id"],
            fleet=surface.FleetLoad(
                wires=spec["fleet"]["wires"],
                ledgers=spec["fleet"]["ledgers"],
                transactions=spec["fleet"]["transactions"],
            ),
            pending_credits=spec["pending_credits"],
            pending_ledger=spec["pending_ledger"],
        )
    )
    with pytest.raises(AttributeError):
        model.build(spec["now_ts"])
    assert model.state.calls == [
        surface.STEP_READ_BOT,
        surface.STEP_READ_FLEET,
        surface.STEP_SUMMARY,
        surface.STEP_PROVENANCE,
        surface.STEP_PROVENANCE_BREAKDOWN,
        surface.STEP_OUTBOUND,
        surface.STEP_INBOUND,
        surface.STEP_PENDING,
    ], model.state.calls
    assert len(model.state.summary_rows) == 6
    assert len(model.state.provenance_rows) == 6
    assert len(model.state.outbound_rows) == 2
    assert model.state.pending_rows == []


def test_a_run_that_does_not_refuse_records_every_step():
    """The recorder reports the same steps whatever the build ran."""
    model = build_surface(BY_NAME["happy"])
    assert model.state.calls == [
        surface.STEP_READ_BOT,
        surface.STEP_READ_FLEET,
        surface.STEP_SUMMARY,
        surface.STEP_PROVENANCE,
        surface.STEP_PROVENANCE_BREAKDOWN,
        surface.STEP_OUTBOUND,
        surface.STEP_INBOUND,
        surface.STEP_PENDING,
        surface.STEP_TRANSACTIONS,
    ], model.state.calls
    empty = build_surface(BY_NAME["an_empty_fleet"])
    assert empty.state.calls[-1] == surface.STEP_EMPTY
    absent = build_surface(BY_NAME["no_manager_attached"])
    assert absent.state.calls == [surface.STEP_READ_BOT, surface.STEP_NOT_ACTIVE]


def test_a_surviving_row_matches_the_row_the_clean_build_printed():
    """A refused build left a row carrying a new label over old numbers."""
    readable = scenario(
        "readable_credits", pending_ledger=[credit_row(usd=5.0), credit_row(usd=6.0)]
    )
    clean = build_surface(readable)
    kept_rows = [list(row) for row in clean.state.pending_rows]
    spec = BY_NAME["a_second_parked_credit_that_is_not_a_record"]
    model = surface.BotSwarmTabModel(
        surface.BotSource(
            bot_id=spec["bot_id"],
            fleet=surface.FleetLoad(
                wires=spec["fleet"]["wires"],
                ledgers=spec["fleet"]["ledgers"],
                transactions=spec["fleet"]["transactions"],
            ),
            pending_credits=spec["pending_credits"],
            pending_ledger=spec["pending_ledger"],
        )
    )
    with pytest.raises(AttributeError):
        model.build(spec["now_ts"])
    survived = [list(row) for row in model.state.pending_rows]
    assert len(survived) < len(kept_rows), (survived, kept_rows)
    for index, row in enumerate(survived):
        assert row == kept_rows[index], (index, row, kept_rows[index])
    assert kept_rows[len(survived)][2] == surface.MONEY_FORMAT.format(value=6.0)


def test_a_second_build_inherits_nothing_from_the_first():
    """A rebuilt tab kept a row the build before it produced."""
    model = build_surface(BY_NAME["happy"])
    assert model.state.outbound_rows
    model.bot = surface.BotSource(bot_id=MINE, fleet=None)
    model.build(NOW_TS)
    assert model.state.outbound_rows == []
    assert model.state.summary_rows == []
    assert model.state.not_active_shown is True
    assert model.state.calls.count(surface.STEP_READ_BOT) == 1


# The stored fleet, through the real restore


def test_the_real_restore_accepts_the_stored_topology(record_property):
    """The topology every scenario is built from is not a real save."""
    from src.trading.smart_wire import SmartWireManager

    manager = SmartWireManager()
    accepted_wires = manager.import_wires(list(BASE_WIRES))
    accepted_ledgers = manager.import_ledgers(list(BASE_LEDGERS))
    record_property("wires_offered", len(BASE_WIRES))
    record_property("wires_accepted", accepted_wires)
    record_property("ledgers_offered", len(BASE_LEDGERS))
    record_property("ledgers_accepted", accepted_ledgers)
    assert accepted_wires == len(BASE_WIRES)
    assert accepted_ledgers == len(BASE_LEDGERS)
    assert manager._wires[MINE]["BOT-B"] == 12.5
    assert manager._ledgers[MINE].wired_in == 120.5


@pytest.mark.parametrize(
    "value",
    [float("nan"), "12.5", None, HUGE_INT_DECIMAL, True, float("inf"), 0.0],
)
def test_the_real_restore_reports_what_it_does_with_each_stored_percent(
    value, record_property
):
    """The real restore is claimed to admit a value it in fact refuses."""
    from src.trading.smart_wire import SmartWireManager

    manager = SmartWireManager()
    accepted = manager.import_wires([wire_row(MINE, "BOT-B", value)])
    stored = manager._wires.get(MINE, {}).get("BOT-B")
    record_property("stored_percent", repr(value))
    record_property("accepted_rows", accepted)
    record_property("value_after_restore", repr(stored))
    assert accepted in (0, 1)
    if accepted == 0:
        assert stored is None
    else:
        assert stored is not None


# The bare-reading audit: every number the tab reads out of stored state


AUDIT_VALUES = {
    "a_stored_true": True,
    "not_a_number": float("nan"),
    "infinity": float("inf"),
    "minus_infinity": float("-inf"),
    "text": "abc",
    "text_that_looks_like_a_number": "12.7",
    "a_real_decimal": 12.7,
    "a_huge_whole_number": HUGE_INT_DECIMAL,
}


def audit_reading(spec, monkeypatch):
    """Drive the Qt tab and report what it printed, or what it raised."""
    try:
        return {"printed": traced_qt(spec, monkeypatch), "raised": None}
    except Exception as exc:
        return {"printed": None, "raised": type(exc).__name__}


AUDIT_SITES = {
    "wired_in": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", wired_in=value)
    ),
    "wired_out": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", wired_out=value)
    ),
    "starting_balance": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", starting_balance=value)
    ),
    "mature_profit_total": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", mature_profit_total=value)
    ),
    "mature_profit_available": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", mature_profit_available=value)
    ),
    "mature_profit_allocated": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", mature_profit_allocated=value)
    ),
    "provenance_amount": lambda value: scenario(
        "audit", fleet=mine_with(asset="B", provenance={"BOT-D": value})
    ),
    "outbound_percent": lambda value: scenario("audit", fleet=outbound_pct(value)),
    "inbound_percent": lambda value: scenario("audit", fleet=inbound_pct(value)),
    "pending_wire_credits": lambda value: scenario("audit", pending_credits=value),
    "credit_time": lambda value: scenario(
        "audit", pending_ledger=[credit_row(ts=value)]
    ),
    "credit_amount": lambda value: scenario(
        "audit", pending_ledger=[credit_row(usd=value)]
    ),
    "wire_event_time": lambda value: scenario(
        "audit", fleet=fleet(transactions=[tx_row(timestamp=value)])
    ),
    "wire_event_amount": lambda value: scenario(
        "audit", fleet=fleet(transactions=[tx_row(amount=value)])
    ),
}


AUDIT_READERS = {
    "wired_in": lambda trace: trace["summary"]["rows"][2][1],
    "wired_out": lambda trace: trace["summary"]["rows"][3][1],
    "starting_balance": lambda trace: trace["provenance"]["rows"][0][1],
    "mature_profit_total": lambda trace: trace["provenance"]["rows"][2][1],
    "mature_profit_allocated": lambda trace: trace["provenance"]["rows"][3][1],
    "mature_profit_available": lambda trace: trace["provenance"]["rows"][4][1],
    "provenance_amount": lambda trace: trace["provenance"]["rows"][5][1],
    "outbound_percent": lambda trace: trace["outbound"]["cells"][0][1],
    "inbound_percent": lambda trace: trace["inbound"]["cells"][0][1],
    "pending_wire_credits": lambda trace: trace["summary"]["rows"][5][1],
    "credit_time": lambda trace: trace["pending"]["cells"][0][0],
    "credit_amount": lambda trace: trace["pending"]["cells"][0][2],
    "wire_event_time": lambda trace: trace["transactions"]["cells"][0][0],
    "wire_event_amount": lambda trace: trace["transactions"]["cells"][0][3],
}


@pytest.mark.parametrize("site", sorted(AUDIT_SITES))
def test_every_stored_number_reads_the_same_way_on_both_sides(
    site, monkeypatch, record_property
):
    """A hostile stored value reached one side and not the other."""
    table = {}
    for label, value in AUDIT_VALUES.items():
        spec = AUDIT_SITES[site](value)
        from_qt = audit_reading(spec, monkeypatch)
        try:
            from_surface = {
                "printed": surface_trace(build_surface(spec)),
                "raised": None,
            }
        except Exception as exc:
            from_surface = {"printed": None, "raised": type(exc).__name__}
        assert from_surface["raised"] == from_qt["raised"], (site, label)
        assert digest(from_surface["printed"]) == digest(from_qt["printed"]), (
            site,
            label,
        )
        table[label] = (
            from_qt["raised"]
            if from_qt["raised"]
            else AUDIT_READERS[site](from_qt["printed"])
        )
    record_property("site", site)
    record_property("readings", json.dumps(table, sort_keys=True))


def test_the_audit_reader_is_pointed_at_the_cell_the_value_lands_in(monkeypatch):
    """The audit reader reads a cell the driven value never reaches."""
    assert sorted(AUDIT_READERS) == sorted(AUDIT_SITES)
    marks = {
        "wired_in": (7.0, "$7.0000"),
        "wired_out": (8.0, "$8.0000"),
        "starting_balance": (9.0, "$9.0000"),
        "mature_profit_total": (11.0, "$11.0000"),
        "mature_profit_allocated": (13.0, "$13.0000"),
        "mature_profit_available": (17.0, "$17.0000"),
        "provenance_amount": (19.0, "BOT-D: $19.00"),
        "outbound_percent": (23.0, "23.00%"),
        "inbound_percent": (29.0, "29.00%"),
        "pending_wire_credits": (31.0, "$31.0000"),
        "credit_amount": (37.0, "$37.0000"),
    }
    for site, (value, printed) in marks.items():
        trace = traced_qt(AUDIT_SITES[site](value), monkeypatch)
        assert AUDIT_READERS[site](trace) == printed, site
    aged = traced_qt(AUDIT_SITES["credit_time"](NOW_TS - 120.0), monkeypatch)
    assert AUDIT_READERS["credit_time"](aged) == "2m"
    event = traced_qt(AUDIT_SITES["wire_event_time"](NOW_TS - 120.0), monkeypatch)
    assert AUDIT_READERS["wire_event_time"](event) == "2m"
    amount = traced_qt(AUDIT_SITES["wire_event_amount"](41.0), monkeypatch)
    assert AUDIT_READERS["wire_event_amount"](amount) == "$41.0000"


def test_the_audit_reader_reports_a_printed_value_and_a_refusal(monkeypatch):
    """The audit reader reports the same answer whatever the tab did."""
    printed = audit_reading(AUDIT_SITES["wired_in"](12.7), monkeypatch)
    assert printed["raised"] is None
    assert printed["printed"]["summary"]["rows"][2][1] == "$12.7000"
    refused = audit_reading(
        BY_NAME["a_parked_credit_that_is_not_a_record"], monkeypatch
    )
    assert refused["raised"] == "AttributeError"
    assert refused["printed"] is None


def test_the_two_percent_columns_read_alike(monkeypatch):
    """Both percent columns guard their stored value the same way."""
    outbound = audit_reading(AUDIT_SITES["outbound_percent"]("12.5"), monkeypatch)
    inbound = audit_reading(AUDIT_SITES["inbound_percent"]("3.5"), monkeypatch)
    assert outbound["raised"] is None
    assert inbound["raised"] is None
    assert AUDIT_READERS["outbound_percent"](outbound["printed"]) == surface.NO_VALUE
    assert AUDIT_READERS["inbound_percent"](inbound["printed"]) == surface.NO_VALUE


@pytest.mark.parametrize("name", UNREADABLE_NAMES)
def test_both_sides_draw_the_unreadable_mark_rather_than_stopping(name, monkeypatch):
    """A stored value no reading admits stopped the whole tab."""
    spec = BY_NAME[name]
    read = AUDIT_READERS[UNREADABLE_READERS[name]]
    from_qt = read(traced_qt(spec, monkeypatch))
    from_surface = read(surface_trace(build_surface(spec)))
    assert from_qt == from_surface, (name, from_qt, from_surface)
    assert surface.NO_VALUE in from_qt, (name, from_qt)


@pytest.mark.parametrize("site", sorted(set(UNREADABLE_READERS.values())))
def test_the_unreadable_mark_check_reads_a_cell_a_real_number_reaches(
    site, monkeypatch
):
    """The cell holds the mark because the reader looks at nothing."""
    printed = AUDIT_READERS[site](traced_qt(AUDIT_SITES[site](12.5), monkeypatch))
    assert surface.NO_VALUE not in printed, (site, printed)


def test_one_unreadable_mature_profit_empties_all_three_rows(monkeypatch):
    """One bad reading loses only its own row."""
    spec = AUDIT_SITES["mature_profit_total"]("abc")
    rows = dict(traced_qt(spec, monkeypatch)["provenance"]["rows"])
    zeroed = [value for label, value in rows.items() if "Mature" in label]
    assert zeroed == ["$0.0000", "$0.0000", "$0.0000"], rows
    model = build_surface(spec)
    assert model.state.mature_refused is True
    clean = build_surface(BY_NAME["happy"])
    assert clean.state.mature_refused is False


def test_a_refused_predominant_funder_reads_as_a_seed_funded_bot(monkeypatch):
    """A refused funder lookup is told apart from a seed-funded bot."""
    spec = BY_NAME["a_predominant_funder_that_refuses"]
    rows = dict(traced_qt(spec, monkeypatch)["provenance"]["rows"])
    assert rows[surface.PREDOMINANT_ROW_LABEL] == surface.NO_VALUE
    seeded = scenario("seeded", fleet=mine_with(asset="B", provenance={"SEED": 10.0}))
    seeded_rows = dict(traced_qt(seeded, monkeypatch)["provenance"]["rows"])
    assert seeded_rows[surface.PREDOMINANT_ROW_LABEL] == surface.NO_PREDOMINANT_TEXT
    assert (
        rows[surface.PREDOMINANT_ROW_LABEL]
        != seeded_rows[surface.PREDOMINANT_ROW_LABEL]
    )
    assert build_surface(spec).state.predominant_refused is True
    assert build_surface(seeded).state.predominant_refused is False


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


def import_aliases(path) -> dict:
    """Every imported name in `path`, mapped back to what it was called."""
    found = {}
    for node in ast.walk(parsed(path)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
    return found


def constructor_counts(path) -> dict:
    """How many times `path` builds each imported name, aliases resolved."""
    aliases = import_aliases(path)
    counts: dict = {}
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            resolved = aliases.get(name, name)
            counts[resolved] = counts.get(resolved, 0) + 1
    return counts


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`."""
    return [
        dotted(node.func.value)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
    ]


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


def connected_signals(widget) -> list:
    """Every signal on `widget` that has a receiver, by signature."""
    meta = widget.metaObject()
    found = []
    for index in range(meta.methodCount()):
        method = meta.method(index)
        if method.methodType() != QMetaMethod.MethodType.Signal:
            continue
        if widget.isSignalConnected(method):
            found.append(str(method.methodSignature(), "utf-8"))
    return found


def every_connection(root) -> list:
    """Every connected signal in the whole tree under `root`."""
    found = []
    for widget in [root] + root.findChildren(QWidget):
        for name in connected_signals(widget):
            found.append("%s.%s" % (type(widget).__name__, name))
    return found


_BARE_WIRING: dict = {}


def framework_wiring(widget_class) -> set:
    """What the framework itself wires on a widget of this class.

    Two framework-only constructions, because the framework wires
    different things in each: a bare instance, and one placed in a form
    row. Measured, `QFormLayout.addRow("text", widget)` connects the
    field widget's `destroyed` while a bare instance has nothing
    connected at all.

    A class the framework only ever builds for itself cannot be built
    bare; it lends nothing here and is covered by the bare instance of
    the widget that owns it.
    """
    from PySide6.QtWidgets import QFormLayout, QGroupBox

    name = widget_class.__name__
    if name not in _BARE_WIRING:
        try:
            probe = widget_class()
            holder = QGroupBox("baseline")
            QFormLayout(holder).addRow("baseline", widget_class())
        except (TypeError, NotImplementedError):
            _BARE_WIRING[name] = set()
        else:
            _BARE_WIRING[name] = set(every_connection(probe)) | set(
                every_connection(holder)
            )
            probe.deleteLater()
            holder.deleteLater()
    return _BARE_WIRING[name]


def product_connections(root) -> list:
    """Every connection in `root` that a bare widget of its class lacks.

    A QTableWidget wires its own scroll bars and header views the moment
    it is built, so counting the whole tree reports the framework rather
    than the product. Each class is measured against a fresh instance of
    itself and only the difference is counted.
    """
    baseline: set = set()
    for widget in [root] + root.findChildren(QWidget):
        baseline |= framework_wiring(type(widget))
    return sorted(set(every_connection(root)) - baseline)


SHIPPED_METHODS = {"_create_bot_swarm_tab": "BotSwarmTabModel.build"}

SURFACE_CLASSES = {
    "BotSwarmTabModel": "BotSwarmTabMixin",
    "TabState": "the values one build of the Qt tab puts on its widgets",
    "BotSource": "the bot BotSwarmTabMixin reads its swarm state off",
    "FleetLoad": "the SmartWireManager the platform restores from state",
    "LedgerRecord": "smart_wire.BotLedger, as the manager holds it",
    "WireRecord": "smart_wire.WireTransaction, as the feed holds it",
}

SURFACE_MODEL_METHODS = ("__init__", "build")


def test_the_shipped_tab_wires_no_signal_and_the_counter_can_report(
    monkeypatch, record_property
):
    """The tab wires a signal the surface names no action for."""
    built = build_qt(BY_NAME["happy"], monkeypatch)
    whole_tree = every_connection(built["tab"])
    scoped = product_connections(built["tab"])
    record_property("connections_in_the_whole_tree", len(whole_tree))
    record_property("connections_the_product_wired", len(scoped))
    record_property("connect_sites_in_the_source", len(connect_sites(TAB_SOURCE)))
    assert scoped == [], scoped
    assert surface.ACTIONS == {}
    assert len(whole_tree) > len(scoped), (len(whole_tree), len(scoped))
    destroy(built["tab"])
    destroy(built["host"])


def button_holder(wired: bool):
    """A holder with one button, connected or not, for the counter control."""
    from PySide6.QtWidgets import QPushButton, QVBoxLayout

    holder = live(QWidget())
    column = QVBoxLayout(holder)
    button = QPushButton("control")
    column.addWidget(button)
    if wired:
        button.clicked.connect(lambda: None)
    return holder


def test_the_connection_counter_reports_a_connection_the_product_makes():
    """The scoped counter reports nothing whatever the product wires."""
    from PySide6.QtWidgets import QVBoxLayout

    app()
    bare = live(QWidget())
    assert every_connection(bare) == []
    assert product_connections(bare) == []

    unwired = set(product_connections(button_holder(wired=False)))
    wired = set(product_connections(button_holder(wired=True)))
    assert unwired == set(), sorted(unwired)
    assert {"QPushButton.clicked()", "QPushButton.clicked(bool)"} <= wired, sorted(
        wired
    )

    table_holder = live(QWidget())
    table_column = QVBoxLayout(table_holder)
    table = QTableWidget()
    table.setColumnCount(2)
    table.setRowCount(2)
    table_column.addWidget(table)
    assert len(every_connection(table_holder)) > 10
    assert product_connections(table_holder) == []


def test_the_tab_builds_and_starts_no_timer_and_the_counter_can_report(monkeypatch):
    """The tab runs a timer the surface declares no delay for."""
    app()
    gc.collect()
    before = {id(found) for found in gc.get_objects() if isinstance(found, QTimer)}
    built = build_qt(BY_NAME["happy"], monkeypatch)
    gc.collect()
    made = [
        found
        for found in gc.get_objects()
        if isinstance(found, QTimer) and id(found) not in before
    ]
    assert made == [], made
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    destroy(built["tab"])
    destroy(built["host"])

    control = QTimer()
    control.start(1000)
    gc.collect()
    seen = [
        found
        for found in gc.get_objects()
        if isinstance(found, QTimer) and id(found) not in before
    ]
    assert control in seen, "the timer counter reports nothing"
    assert [found for found in seen if found.isActive()] == [control]
    control.stop()
    control.deleteLater()


def test_the_timer_counter_is_pointed_at_a_path_and_not_a_basename():
    """Two files share a basename and a reader took the wrong one."""
    assert TAB_SOURCE.name == TAB_NAMESAKE.name
    assert TAB_SOURCE != TAB_NAMESAKE
    assert source_classes(TAB_SOURCE) == ["BotSwarmTabMixin"]
    assert source_classes(TAB_NAMESAKE) == ["BotSwarmTabMixin"]
    assert source_functions(TAB_SOURCE) != source_functions(TAB_NAMESAKE)


def test_the_tab_starts_no_thread_and_the_counter_can_report(monkeypatch):
    """The tab starts a worker the surface names none of."""
    app()
    before = set(threading.enumerate())
    built = build_qt(BY_NAME["happy"], monkeypatch)
    assert set(threading.enumerate()) - before == set()
    assert surface.THREADS == ()
    destroy(built["tab"])
    destroy(built["host"])

    started = threading.Event()
    worker = threading.Thread(target=started.wait, name="swarm-parity-control")
    worker.start()
    assert set(threading.enumerate()) - before == {worker}
    started.set()
    worker.join(timeout=5)
    assert not worker.is_alive()


def test_the_tab_neither_subscribes_nor_emits_and_both_counters_can_report(
    monkeypatch,
):
    """The tab talks on a bus topic the surface names none of."""
    from src.core.event_bus import EventBus, get_event_bus

    app()
    listened: list = []
    spoken: list = []
    real_subscribe = EventBus.subscribe
    real_emit = EventBus.emit

    def watched_subscribe(self, topic, *found, **named):
        listened.append(topic)
        return real_subscribe(self, topic, *found, **named)

    def watched_emit(self, topic, *found, **named):
        spoken.append(topic)
        return real_emit(self, topic, *found, **named)

    monkeypatch.setattr(EventBus, "subscribe", watched_subscribe)
    monkeypatch.setattr(EventBus, "emit", watched_emit)
    built = build_qt(BY_NAME["happy"], monkeypatch)
    assert listened == [], listened
    assert spoken == [], spoken
    assert surface.BUS_TOPICS == ()
    assert surface.BUS_EMITS == ()
    destroy(built["tab"])
    destroy(built["host"])

    bus = get_event_bus()
    bus.subscribe("swarm.parity.control", lambda *_found: None)
    bus.emit("swarm.parity.control")
    assert listened == ["swarm.parity.control"], listened
    assert spoken == ["swarm.parity.control"], spoken
    monkeypatch.undo()
    assert EventBus.subscribe is real_subscribe
    assert EventBus.emit is real_emit


def test_the_shipped_mixin_declares_no_signal_and_the_reader_can_report():
    """A signal is callable, so a loose counter reads it as a method."""
    from PySide6.QtCore import Signal

    from src.gui.live_settings.bot_swarm_tab import BotSwarmTabMixin

    declared = [
        name
        for name, value in vars(BotSwarmTabMixin).items()
        if isinstance(value, Signal)
    ]
    assert declared == []
    assert list(surface.SIGNALS) == []
    from src.gui.launcher import ModeCard

    assert [
        name for name, value in vars(ModeCard).items() if isinstance(value, Signal)
    ] != []
    assert BotSwarmTabMixin.__annotations__ == {
        "_bot": "Any",
        "_configure_form": "Callable[..., Any]",
        "_format_age": "Callable[..., Any]",
    }
    for annotated in BotSwarmTabMixin.__annotations__:
        assert annotated not in vars(BotSwarmTabMixin)


def test_every_shipped_method_has_a_counterpart():
    """The shipped tab gained or lost a class or a method."""
    from src.gui.live_settings import bot_swarm_tab as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["BotSwarmTabMixin"], classes
    methods = sorted(
        name
        for name, value in vars(shipped.BotSwarmTabMixin).items()
        if callable(value) and not name.startswith("__")
    )
    assert methods == sorted(SHIPPED_METHODS), methods
    for counterpart in set(SHIPPED_METHODS.values()):
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_the_class_reader_sees_a_class_declared_inside_a_method():
    """A top-level-only reader counts no class the file hides in a method."""
    hidden = source_classes(NESTED_CLASS_NEIGHBOUR)
    assert hidden, NESTED_CLASS_NEIGHBOUR.name
    assert top_level_classes(NESTED_CLASS_NEIGHBOUR) == []
    assert "StockMainWindow" in hidden


def test_the_function_reader_sees_a_method_of_a_nested_class():
    """The function reader misses a method the file nests in a class."""
    nested = source_functions(NESTED_METHOD_NEIGHBOUR)
    assert len(nested) > len(source_functions(TAB_SOURCE))
    assert "_IVPPrivacyDot" in source_classes(NESTED_METHOD_NEIGHBOUR)
    assert source_functions(TAB_SOURCE) == sorted(SHIPPED_METHODS)


def test_the_constructor_counter_resolves_an_import_alias(record_property):
    """A counter read the alias and missed what the file really builds."""
    counts = constructor_counts(TAB_SOURCE)
    aliases = import_aliases(TAB_SOURCE)
    assert aliases["_as_finite_float"] == "as_finite_float"
    assert "_as_finite_float" not in counts
    assert counts["as_finite_float"] >= 6, counts.get("as_finite_float")
    record_property("constructors", json.dumps(counts, sort_keys=True))
    for built in ("QTableWidget", "QGroupBox", "QLabel", "QVBoxLayout"):
        assert counts.get(built, 0) >= 1, built


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
        for name, value in vars(surface.BotSwarmTabModel).items()
        if callable(value) and (not name.startswith("_") or name == "__init__")
    )
    assert model_methods == sorted(SURFACE_MODEL_METHODS), model_methods


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "_create_bot_swarm_tab" in SHIPPED_METHODS
    assert "InventedModel" not in SURFACE_CLASSES
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        surface.BotSwarmTabModel.invented_method


def test_the_shipped_tab_reads_the_bot_reference_table_and_uses_nothing(monkeypatch):
    """The tab reads a value it then uses, and the surface dropped it."""
    spec = BY_NAME["happy"]
    assert surface.BOT_REFS_READ_IS_UNUSED is True
    with_refs = traced_qt(spec, monkeypatch)
    without = scenario("no_refs", fleet=fleet(bot_refs={}))
    assert digest(traced_qt(without, monkeypatch)) == digest(with_refs)
    assert digest(surface_trace(build_surface(without))) == digest(
        surface_trace(build_surface(spec))
    )


def test_every_state_field_the_model_holds_is_named():
    """The model grew a built value nothing in this file knows about."""
    fresh = surface.TabState()
    assert sorted(vars(fresh)) == sorted(MODEL_STATE_FIELDS), sorted(vars(fresh))
    built = build_surface(BY_NAME["happy"])
    assert sorted(vars(built.state)) == sorted(MODEL_STATE_FIELDS)


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
    "ASSET_SUFFIX_FORMAT": "formats.asset_suffix",
    "BOLD_COLOUR_STYLE_FORMAT": "formats.bold_colour_style",
    "BOLD_COLOUR_STYLE_PREFIX": "styles.bold_colour_prefix",
    "BOT_ID_ATTRIBUTE": "attributes.bot_id",
    "BOT_REFS_ATTRIBUTE": "attributes.bot_refs",
    "BOT_REFS_READ_IS_UNUSED": "attributes.bot_refs_read_is_unused",
    "BUS_EMITS": "bus_emits",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CONTENT_MARGINS_SET": "container.margins_set",
    "CONTENT_SPACING_PX": "container.spacing_px",
    "CREDIT_REF_KEY": "keys.credit_ref",
    "CREDIT_SOURCE_KEY": "keys.credit_source",
    "CREDIT_TS_KEY": "keys.credit_ts",
    "CREDIT_USD_KEY": "keys.credit_usd",
    "EMPTY_REF_TEXT": "texts.empty_ref",
    "EMPTY_STYLE": "empty_label.style_sheet",
    "EMPTY_TEXT": "empty_label.text",
    "EMPTY_WORD_WRAP": "empty_label.word_wrap",
    "FORM_CONFIGURED_BY_HOST": "summary_group.configured_by_host",
    "INACTIVE_COLOUR": "colours.inactive",
    "INBOUND_COUNT_FORMAT": "formats.inbound_count",
    "INBOUND_GROUP_TITLE_FORMAT": "formats.inbound_group_title",
    "INBOUND_HEADERS": "inbound_table.headers",
    "INBOUND_ROW_LABEL": "labels.inbound",
    "IN_DIRECTION_COLOUR": "colours.in_direction",
    "IN_DIRECTION_TEXT": "texts.in_direction",
    "LEDGER_ASSET_FIELD": "fields.ledger_asset",
    "LEDGER_MATURE_ALLOCATED_FIELD": "fields.ledger_mature_allocated",
    "LEDGER_MATURE_AVAILABLE_FIELD": "fields.ledger_mature_available",
    "LEDGER_MATURE_TOTAL_FIELD": "fields.ledger_mature_total",
    "LEDGER_PREDOMINANT_FIELD": "fields.ledger_predominant",
    "LEDGER_PROVENANCE_FIELD": "fields.ledger_provenance",
    "LEDGER_STARTING_FIELD": "fields.ledger_starting",
    "LEDGER_WIRED_IN_FIELD": "fields.ledger_wired_in",
    "LEDGER_WIRED_OUT_FIELD": "fields.ledger_wired_out",
    "LEDGERS_ATTRIBUTE": "attributes.ledgers",
    "LINE_BREAK_TAG": "marks.line_break",
    "MATURE_ALLOCATED_ROW_LABEL": "labels.mature_allocated",
    "MATURE_AVAILABLE_COLOUR": "colours.mature_available",
    "MATURE_AVAILABLE_ROW_LABEL": "labels.mature_available",
    "MATURE_RATIO_FALLBACK_PCT": "thresholds.mature_ratio_fallback_pct",
    "MATURE_RATIO_ZERO": "thresholds.mature_zero",
    "MATURE_TOTAL_ROW_FORMAT": "formats.mature_total_row",
    "METHOD": "method",
    "MONEY_FORMAT": "formats.money",
    "NET_FLOW_ROW_LABEL": "labels.net_flow",
    "NET_NEGATIVE_COLOUR": "colours.net_negative",
    "NET_POSITIVE_COLOUR": "colours.net_positive",
    "NOT_ACTIVE_BREAKS": "not_active_label.breaks",
    "NOT_ACTIVE_LEAD": "not_active_label.lead",
    "NOT_ACTIVE_STRONG": "not_active_label.strong",
    "NOT_ACTIVE_STYLE": "not_active_label.style_sheet",
    "NOT_ACTIVE_TAIL": "not_active_label.tail",
    "NOT_ACTIVE_TEXT": "not_active_label.text",
    "NOT_ACTIVE_WORD_WRAP": "not_active_label.word_wrap",
    "NO_PREDOMINANT_TEXT": "texts.no_predominant",
    "NO_STYLE": "styles.none",
    "NO_VALUE": "texts.no_value",
    "OUTBOUND_COUNT_FORMAT": "formats.outbound_count",
    "OUTBOUND_GROUP_TITLE_FORMAT": "formats.outbound_group_title",
    "OUTBOUND_HEADERS": "outbound_table.headers",
    "OUTBOUND_ROW_LABEL": "labels.outbound",
    "OUT_DIRECTION_COLOUR": "colours.out_direction",
    "OUT_DIRECTION_TEXT": "texts.out_direction",
    "PCT_FORMAT": "formats.pct",
    "PENDING_COLOUR": "colours.pending",
    "PENDING_GROUP_TITLE_FORMAT": "formats.pending_group_title",
    "PENDING_HEADERS": "pending_table.headers",
    "PENDING_ROW_LABEL": "labels.pending",
    "PLAIN_COLOUR_STYLE_FORMAT": "formats.plain_colour_style",
    "PREDOMINANT_ROW_LABEL": "labels.predominant",
    "PROVENANCE_GROUP_TITLE": "titles.provenance",
    "PROVENANCE_JOIN": "texts.provenance_join",
    "PROVENANCE_MONEY_FORMAT": "formats.provenance_money",
    "PROVENANCE_REFUSED_FORMAT": "formats.provenance_refused",
    "PROVENANCE_ROW_LABEL": "labels.provenance",
    "PROVENANCE_STYLE": "styles.provenance",
    "PROVENANCE_WORD_WRAP": "provenance_group.word_wrap_when_shown",
    "SEED_SOURCE": "texts.seed_source",
    "SIGNALS": "signals",
    "SIGNED_MONEY_FORMAT": "formats.signed_money",
    "SMART_WIRE_ATTRIBUTE": "attributes.smart_wire",
    "STARTING_ROW_LABEL": "labels.starting",
    "STORED_ASSET_KEY": "keys.stored_asset",
    "STORED_BOT_ID_KEY": "keys.stored_bot_id",
    "STORED_MATURE_ALLOCATED_KEY": "keys.stored_mature_allocated",
    "STORED_PCT_KEY": "keys.stored_pct",
    "STORED_PROVENANCE_KEY": "keys.stored_provenance",
    "STORED_SOURCE_KEY": "keys.stored_source",
    "STORED_STARTING_BALANCE_KEY": "keys.stored_starting_balance",
    "STORED_TARGET_KEY": "keys.stored_target",
    "STORED_TOTAL_PROFIT_KEY": "keys.stored_total_profit",
    "STORED_WIRED_IN_KEY": "keys.stored_wired_in",
    "STORED_WIRED_OUT_KEY": "keys.stored_wired_out",
    "STRONG_CLOSE_TAG": "marks.strong_close",
    "STRONG_OPEN_TAG": "marks.strong_open",
    "STRONG_WEIGHT": "marks.strong_weight",
    "SUMMARY_GROUP_TITLE": "titles.summary",
    "TAB_LABEL": "tab_label",
    "TABLE_ALTERNATING_ROWS": "tables.alternating_rows",
    "TABLE_EDIT_TRIGGERS": "tables.edit_triggers",
    "TABLE_RESIZE_MODE": "tables.resize_mode",
    "THREADS": "threads",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TIMERS": "timers",
    "TRANSACTIONS_ATTRIBUTE": "attributes.transactions",
    "TRANSACTIONS_GROUP_TITLE_FORMAT": "formats.transactions_group_title",
    "TRANSACTIONS_HEADERS": "transactions_table.headers",
    "TRANSACTIONS_SHOWN_LIMIT": "thresholds.transactions_limit",
    "TRANSACTIONS_TABLE_MAX_HEIGHT_PX": "tables.transactions_max_height_px",
    "TX_AMOUNT_FIELD": "fields.tx_amount",
    "TX_SOURCE_FIELD": "fields.tx_source",
    "TX_TARGET_FIELD": "fields.tx_target",
    "TX_TIMESTAMP_FIELD": "fields.tx_timestamp",
    "TX_TYPE_FIELD": "fields.tx_type",
    "UNKNOWN_SOURCE_TEXT": "texts.unknown_source",
    "WIRE_CREDITS_ATTRIBUTE": "attributes.wire_credits",
    "WIRE_LEDGER_ATTRIBUTE": "attributes.wire_ledger",
    "WIRE_TABLE_MAX_HEIGHT_PX": "tables.wire_max_height_px",
    "WIRED_IN_COLOUR": "colours.wired_in",
    "WIRED_IN_ROW_LABEL": "labels.wired_in",
    "WIRED_OUT_COLOUR": "colours.wired_out",
    "WIRED_OUT_ROW_LABEL": "labels.wired_out",
    "WIRES_ATTRIBUTE": "attributes.wires",
}

LIST_MEMBERS = {
    "STEP_EMPTY": "call_names",
    "STEP_INBOUND": "call_names",
    "STEP_NOT_ACTIVE": "call_names",
    "STEP_OUTBOUND": "call_names",
    "STEP_PENDING": "call_names",
    "STEP_PROVENANCE": "call_names",
    "STEP_PROVENANCE_BREAKDOWN": "call_names",
    "STEP_READ_BOT": "call_names",
    "STEP_READ_FLEET": "call_names",
    "STEP_SUMMARY": "call_names",
    "STEP_TRANSACTIONS": "call_names",
}

NOT_IN_THE_SNAPSHOT = {"PANE_MODEL": "test_the_bridge_resets_the_tab_state_on_request"}

STATE_ONLY_KEYS = {
    "active",
    "calls",
    "container",
    "empty_label",
    "inbound_table",
    "not_active_label",
    "outbound_table",
    "pending_table",
    "provenance_group",
    "summary_group",
    "transactions_table",
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
    payload = surface.build_view_model(build_surface(BY_NAME["happy"]))
    unaccounted = []
    for name, value in surface_constants().items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == list(value), name
            else:
                assert carried == value, name
                assert type(carried) is type(value), name
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
    payload = surface.build_view_model(build_surface(BY_NAME["happy"]))
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= set(LIST_MEMBERS.values())
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    payload = surface.build_view_model(build_surface(BY_NAME["happy"]))
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "NOT_ACTIVE_TEXT" in surface_constants()
    assert "MONEY_FORMAT" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "BotSwarmTabModel" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "labels.invented")


def test_a_stored_true_is_not_folded_into_the_number_beside_it():
    """A boolean and the number one were kept in one set and merged."""
    both = [True, 1]
    assert len(set(both)) == 1
    assert len(both) == 2
    driven = [
        (name, type(value).__name__)
        for name, value in AUDIT_VALUES.items()
        if value is True or value == 1
    ]
    assert driven == [("a_stored_true", "bool")], driven


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
    assert "BotSwarmTabModel" not in surface_constants()
    assert "METHOD" in parsed_constant_names()
    assert "METHOD" in surface_constants()


# The surface carries its own values


class MovedTokens:
    """A token table whose colours are unlike any the design system holds.

    Every channel of every value differs from the other two, so a
    channel swap cannot read as unchanged, and none of them appears in
    the real table. Both claims are measured below rather than assumed.
    """

    TEXT_INACTIVE = "#100fef"
    SUCCESS = "#110fee"
    FOLD_RATIO_AMBER = "#120fed"
    ERROR = "#130fec"
    FOLD_SOURCE_MANUAL = "#140feb"
    TEXT_NEUTRAL = "#150fea"
    CARD_METRIC_LABEL = "#160fe9"


def moved_token_values():
    """Every colour the moved table holds."""
    return [
        value
        for name, value in vars(MovedTokens).items()
        if not name.startswith("_") and isinstance(value, str)
    ]


def real_token_values():
    """Every colour the design system holds."""
    from src.gui import design_system

    return {
        value.lower()
        for value in vars(design_system).values()
        if isinstance(value, str) and value.startswith("#")
    }


def test_no_moved_token_is_a_colour_the_real_table_already_holds():
    """A moved token equals a real one, so the move reaches no pixel."""
    real = real_token_values()
    assert len(real) > 1, "the real token reader found nothing"
    moved = moved_token_values()
    assert len(moved) == 7, moved
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

    real = real_token_values()
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
    from src.gui.live_settings import bot_swarm_tab as shipped

    first = shipped.ds
    spec = BY_NAME["happy"]
    before_style = surface.PROVENANCE_STYLE
    before_empty = surface.EMPTY_STYLE
    plain_old = render_offscreen(qt_widget(spec, monkeypatch), PIXEL_SIZE)
    plain_new = render_offscreen(model_widget(model_payload(spec)), PIXEL_SIZE)
    assert_pictures_match(
        old_side=plain_old, new_side=plain_new, note="before the move"
    )

    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved_old = render_offscreen(qt_widget(spec, monkeypatch), PIXEL_SIZE)
    assert_pictures_differ(
        old_side=plain_old,
        new_side=moved_old,
        note="the shipped tab follows its tokens",
    )
    moved_new = render_offscreen(model_widget(model_payload(spec)), PIXEL_SIZE)
    assert_pictures_match(
        old_side=plain_new, new_side=moved_new, note="the surface kept its own tokens"
    )
    assert surface.PROVENANCE_STYLE == before_style
    assert surface.EMPTY_STYLE == before_empty
    assert MovedTokens.TEXT_NEUTRAL not in surface.PROVENANCE_STYLE

    monkeypatch.undo()
    assert shipped.ds is first
    after = render_offscreen(qt_widget(spec, monkeypatch), PIXEL_SIZE)
    assert_pictures_match(old_side=plain_old, new_side=after, note="after the move")


def test_the_surface_does_not_follow_a_tab_that_builds_nothing(monkeypatch):
    """The surface asked the shipped tab to build its rows."""
    app()
    from src.gui.live_settings import bot_swarm_tab as shipped

    first = shipped.BotSwarmTabMixin._create_bot_swarm_tab
    before = surface_trace(build_surface(BY_NAME["happy"]))
    monkeypatch.setattr(
        shipped.BotSwarmTabMixin, "_create_bot_swarm_tab", lambda self: None
    )
    assert host_class()(QtBot(BY_NAME["happy"]))._create_bot_swarm_tab() is None
    again = surface_trace(build_surface(BY_NAME["happy"]))
    assert again == before
    assert again["outbound"]["cells"], again
    monkeypatch.undo()
    assert shipped.BotSwarmTabMixin._create_bot_swarm_tab is first


def test_the_shipped_tab_writes_to_no_shared_table(monkeypatch):
    """The shipped tab changed something every later test would inherit."""
    app()
    from src.gui import design_system
    from src.gui.live_settings import bot_swarm_tab as shipped

    watched = tuple(sorted(name for name in vars(MovedTokens) if name.isupper()))
    before_tokens = {name: getattr(design_system, name) for name in watched}
    before_module = sorted(vars(shipped))
    traced_qt(BY_NAME["happy"], monkeypatch)
    traced_qt(BY_NAME["an_empty_fleet"], monkeypatch)
    with pytest.raises(AttributeError):
        traced_qt(BY_NAME["a_parked_credit_that_is_not_a_record"], monkeypatch)
    assert {name: getattr(design_system, name) for name in watched} == before_tokens
    assert sorted(vars(shipped)) == before_module
    assert shipped.ds is design_system


def test_the_moved_table_is_seen_during_a_drive_and_gone_after_it(monkeypatch):
    """A swapped table outlived the drive that swapped it."""
    app()
    from src.gui import design_system
    from src.gui.live_settings import bot_swarm_tab as shipped

    seen: list = []
    real_configure = host_class()

    class Watcher(real_configure):
        def _configure_form(self, form):
            seen.append(shipped.ds)
            return super()._configure_form(form)

    monkeypatch.setattr(shipped, "ds", MovedTokens)
    tab = Watcher(QtBot(BY_NAME["happy"]))._create_bot_swarm_tab()
    assert seen and all(table is MovedTokens for table in seen), seen
    destroy(tab)
    monkeypatch.undo()
    assert shipped.ds is design_system

    monkeypatch.setattr(shipped, "ds", MovedTokens)
    with pytest.raises(AttributeError):
        Watcher(
            QtBot(BY_NAME["a_parked_credit_that_is_not_a_record"])
        )._create_bot_swarm_tab()
    monkeypatch.undo()
    assert shipped.ds is design_system


def test_neither_side_edits_the_stored_rows_it_is_handed(monkeypatch):
    """A build changed the fleet rows the platform restored."""
    app()
    rows = {
        "wires": [dict(row) for row in BASE_WIRES],
        "ledgers": [dict(row) for row in BASE_LEDGERS],
        "transactions": [dict(row) for row in BASE_TRANSACTIONS],
        "bot_refs": {MINE: "bot-a-ref"},
    }
    credits = [dict(row) for row in BASE_CREDITS]
    before = digest([rows, credits])
    spec = scenario("handed_rows", fleet=rows, pending_ledger=credits)
    traced_qt(spec, monkeypatch)
    assert digest([rows, credits]) == before, "the Qt tab edited what it was handed"
    model = build_surface(spec)
    assert digest([rows, credits]) == before, "the surface edited what it was handed"
    model.state.outbound_rows.append(["added by the test", "", ""])
    assert digest([rows, credits]) == before


def test_the_edit_check_reports_a_row_that_was_changed():
    """The edit check reports nothing whatever a caller writes."""
    rows = [dict(row) for row in BASE_WIRES]
    before = digest(rows)
    rows[0]["pct"] = 99.0
    assert digest(rows) != before


def test_neither_side_reads_the_clock(monkeypatch):
    """A side reached for the wall clock instead of the value it was given."""
    app()
    spec = BY_NAME["happy"]
    built = build_qt(spec, monkeypatch)
    assert built["clock"].asked == 1, "the shipped tab reads the clock once"
    destroy(built["tab"])
    destroy(built["host"])
    import time as time_module

    def refuse():
        raise AssertionError("the surface may not read the clock")

    monkeypatch.setattr(time_module, "time", refuse)
    model = build_surface(spec)
    assert model.state.outbound_rows
    monkeypatch.undo()
    assert callable(time_module.time)


def test_the_clock_counter_reports_a_read():
    """The clock counter reports nothing whatever a side reads."""
    clock = FrozenClock(NOW_TS)
    assert clock.asked == 0
    assert clock() == NOW_TS
    assert clock.asked == 1


# The pictures


def model_payload(spec):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(build_surface(spec)))


def qt_widget(spec, monkeypatch):
    """The tab the shipped Qt mixin builds, after the same driving."""
    return build_qt(spec, monkeypatch)["tab"]


def fill_table(payload_rows, headers, max_height, colours=None):
    """A table carrying only what the payload says it carries."""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.setRowCount(len(payload_rows))
    table.setMaximumHeight(max_height)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTableWidgetItem

    for row, cells in enumerate(payload_rows):
        for column, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if colours is not None and column == 1:
                item.setForeground(QColor(colours[row]))
            table.setItem(row, column, item)
    return table


def model_widget(payload):
    """A tab built only from the payload, never from the shipped mixin."""
    payload = unaltered(payload)
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    app()
    screen = live(QWidget())
    screen.setAccessibleName(payload["accessible_name"])
    column = QVBoxLayout(screen)
    column.setSpacing(payload["container"]["spacing_px"])

    if payload["not_active_label"]["shown"]:
        message = QLabel(payload["not_active_label"]["text"])
        message.setStyleSheet(payload["not_active_label"]["style_sheet"])
        message.setWordWrap(payload["not_active_label"]["word_wrap"])
        column.addWidget(message)
        column.addStretch()
        return screen

    summary = QGroupBox(payload["summary_group"]["title"])
    summary_form = QFormLayout(summary)
    BotLiveSettingsDialog._configure_form(screen, summary_form)
    for (label, value), style in zip(
        payload["summary_group"]["rows"], payload["summary_group"]["styles"]
    ):
        field = QLabel(value)
        if style:
            field.setStyleSheet(style)
        summary_form.addRow(label, field)
    column.addWidget(summary)

    if payload["provenance_group"]["shown"]:
        provenance = QGroupBox(payload["provenance_group"]["title"])
        provenance_form = QFormLayout(provenance)
        BotLiveSettingsDialog._configure_form(screen, provenance_form)
        for index, (label, value) in enumerate(payload["provenance_group"]["rows"]):
            field = QLabel(value)
            if payload["provenance_group"]["word_wraps"][index]:
                field.setWordWrap(True)
            style = payload["provenance_group"]["styles"][index]
            if style:
                field.setStyleSheet(style)
            provenance_form.addRow(label, field)
        column.addWidget(provenance)

    for key, headers, height in (
        ("outbound_table", payload["tables"]["outbound_headers"], None),
        ("inbound_table", payload["tables"]["inbound_headers"], None),
        ("pending_table", payload["tables"]["pending_headers"], None),
        (
            "transactions_table",
            payload["tables"]["transactions_headers"],
            payload["tables"]["transactions_max_height_px"],
        ),
    ):
        block = payload[key]
        if not block["shown"]:
            continue
        group = QGroupBox(block["title"])
        inner = QVBoxLayout(group)
        inner.addWidget(
            fill_table(
                block["rows"],
                headers,
                payload["tables"]["wire_max_height_px"] if height is None else height,
                block.get("direction_colours"),
            )
        )
        column.addWidget(group)

    if payload["empty_label"]["shown"]:
        empty = QLabel(payload["empty_label"]["text"])
        empty.setStyleSheet(payload["empty_label"]["style_sheet"])
        empty.setWordWrap(payload["empty_label"]["word_wrap"])
        column.addWidget(empty)

    column.addStretch()
    return screen


PICTURE_SCENARIOS = [
    "happy",
    "no_manager_attached",
    "an_empty_fleet",
    "no_wires_but_a_ledger",
    "not_a_number",
    "a_stored_true_where_money_belongs",
    "unicode_asset",
    "negative_everywhere",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name, monkeypatch):
    """The surface painted a different tab than the shipped mixin."""
    app()
    spec = BY_NAME[name]
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    old_side = render_offscreen(qt_widget(spec, monkeypatch), PIXEL_SIZE)
    new_side = render_offscreen(model_widget(model_payload(spec)), PIXEL_SIZE)
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
        build_old_side=lambda: qt_widget(spec, monkeypatch),
        build_new_side=lambda: model_widget(payload),
        size=PIXEL_SIZE,
        control_rule=SKIN_CONTROL_RULE,
        note=name,
    )
    record_property("state", name)
    record_property(
        "colours", colour_count(render_offscreen(model_widget(payload), PIXEL_SIZE))
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_colour_count_of_each_state_is_reported(name, monkeypatch, record_property):
    """A state painted one colour and no comparison of it can report."""
    app()
    spec = BY_NAME[name]
    old_side = render_offscreen(qt_widget(spec, monkeypatch), PIXEL_SIZE)
    new_side = render_offscreen(model_widget(model_payload(spec)), PIXEL_SIZE)
    old_colours = assert_picture_can_report(old_side, note=name)
    new_colours = assert_picture_can_report(new_side, note=name)
    record_property("state", name)
    record_property("old_colours", old_colours)
    record_property("new_colours", new_colours)
    record_property("fonts", "real" if has_real_fonts() else "none")
    assert old_colours == new_colours, name


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_skin_control_rule_moves_a_pixel_on_this_tab(name, monkeypatch):
    """The control rule reaches no pixel, so the skin check cannot report."""
    app()
    spec = BY_NAME[name]
    plain = render_offscreen(model_widget(model_payload(spec)), PIXEL_SIZE)
    skinned = model_widget(model_payload(spec))
    skinned.setStyleSheet(SKIN_CONTROL_RULE)
    assert_pictures_differ(
        old_side=plain,
        new_side=render_offscreen(skinned, PIXEL_SIZE),
        note="the control rule on the surface's own tab",
    )
    old_plain = render_offscreen(qt_widget(spec, monkeypatch), PIXEL_SIZE)
    old_skinned = qt_widget(spec, monkeypatch)
    old_skinned.setStyleSheet(SKIN_CONTROL_RULE)
    assert_pictures_differ(
        old_side=old_plain,
        new_side=render_offscreen(old_skinned, PIXEL_SIZE),
        note="the control rule on the shipped tab",
    )


def test_the_picture_comparison_can_report_a_difference(monkeypatch):
    """The picture check passes whatever the second side paints."""
    app()
    happy = BY_NAME["happy"]
    other = BY_NAME["no_wires_but_a_ledger"]
    assert happy["fleet"]["wires"] != other["fleet"]["wires"]
    assert_cases_paint_differently(
        old_side=render_offscreen(qt_widget(happy, monkeypatch), PIXEL_SIZE),
        new_side=render_offscreen(model_widget(model_payload(other)), PIXEL_SIZE),
        note="the wired bot against the unwired one",
    )
    assert_pictures_differ(
        old_side=render_offscreen(qt_widget(other, monkeypatch), PIXEL_SIZE),
        new_side=render_offscreen(model_widget(model_payload(happy)), PIXEL_SIZE),
        note="the other direction",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload(BY_NAME["happy"])
    payload["summary_group"]["rows"][0][1] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        model_widget(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        model_widget(surface.build_view_model(build_surface(BY_NAME["happy"])))


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
    old = traced_qt(spec, monkeypatch)
    new = surface_trace(build_surface(spec))
    assert new["accessible_name"] == old["accessible_name"] == ""
    assert new["forms_configured"] == old["forms_configured"] == 2
    assert surface.FORM_CONFIGURED_BY_HOST is True
    for key in ("outbound", "inbound", "pending", "transactions"):
        assert new[key]["edit_triggers"] == old[key]["edit_triggers"]
        assert new[key]["resize_modes"] == old[key]["resize_modes"]
        assert new[key]["max_height_px"] == old[key]["max_height_px"]
        assert new[key]["alternating"] == old[key]["alternating"] is True


def box_of(layout):
    """One layout's four margins, as plain numbers."""
    margins = layout.contentsMargins()
    return [margins.left(), margins.top(), margins.right(), margins.bottom()]


def untouched_layout_margins():
    """The margins and spacing a fresh column layout starts with."""
    from PySide6.QtWidgets import QVBoxLayout

    holder = live(QWidget())
    plain = QVBoxLayout(holder)
    reading = (box_of(plain), plain.spacing())
    assert holder.layout() is plain
    return reading


def test_the_outer_layout_sets_no_margins_on_either_side(monkeypatch):
    """The tab set its own margins on one side and not on the other."""
    app()
    untouched, untouched_spacing = untouched_layout_margins()
    tab = qt_widget(BY_NAME["happy"], monkeypatch)
    built = model_widget(model_payload(BY_NAME["happy"]))
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
    surface.PANE_MODEL = surface.BotSwarmTabModel()
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
    "bot_id": MINE,
    "fleet": {
        "wires": BASE_WIRES,
        "ledgers": BASE_LEDGERS,
        "transactions": BASE_TRANSACTIONS,
    },
    "pending_credits": 12.5,
    "pending_ledger": BASE_CREDITS,
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_bot_swarm_tab_method():
    """The renderer cannot reach the Bot Swarm tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "bot_swarm_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    assert answer["result"]["titles"]["summary"] == surface.SUMMARY_GROUP_TITLE


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_tab_state_on_request():
    """The tab state the bridge keeps was never cleared."""
    filled = bridge_answer({"reset": True, "bot": BRIDGE_BOT, "now_ts": NOW_TS})[
        "result"
    ]
    assert filled["outbound_table"]["count"] == 2
    assert filled["summary_group"]["rows"][0] == [
        surface.OUTBOUND_ROW_LABEL,
        "2 target(s)",
    ]
    kept = bridge_answer({})["result"]
    assert kept["outbound_table"]["count"] == 2
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["outbound_table"]["count"] == 0
    assert cleared["outbound_table"]["shown"] is False
    assert cleared["calls"] == []
    assert surface.PANE_MODEL is not None


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answers_for_a_bot_with_no_manager():
    """A bot with no Smart Wire manager reached the wrong answer."""
    answered = bridge_answer(
        {
            "reset": True,
            "bot": {"bot_id": MINE, "fleet": None},
            "now_ts": NOW_TS,
        }
    )["result"]
    assert answered["not_active_label"]["shown"] is True
    assert answered["summary_group"]["shown"] is False
    assert answered["active"] is False


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reset": True, "bot": BRIDGE_BOT, "now_ts": NOW_TS})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["pending_table"]["rows"][0][1] == "BOT-D"


# The surface answers with Qt absent, and reads nothing at import


BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'bot_swarm_tab.state',\n"
    "    'params': {'reset': True, 'now_ts': 1755600000.0, 'bot': {\n"
    "        'bot_id': 'BOT-A', 'pending_credits': 12.5,\n"
    "        'pending_ledger': [{'ts': 1755000000, 'source': 'BOT-D',\n"
    "            'usd': 3.25, 'ref': 'fold-991'}],\n"
    "        'fleet': {'wires': [{'source_id': 'BOT-A',\n"
    "                'target_id': 'BOT-B', 'pct': 12.5}],\n"
    "            'ledgers': [{'bot_id': 'BOT-A', 'asset': 'BTC',\n"
    "                'wired_in': 120.5, 'wired_out': 45.25}],\n"
    "            'transactions': []}}}}),\n"
    "    desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))\n"
)

INERT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-swarm-probe-'))
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

import threading
threads_before = threading.active_count()

import time
clock_reads = []
real_time = time.time


def watched_time():
    clock_reads.append(1)
    return real_time()


time.time = watched_time

from src.gui.main_tabs import bot_swarm_tab_surface as s

threads_at_import = threading.active_count() - threads_before
built_at_import = s.PANE_MODEL is not None
opened_at_import = list(opened)
reads_at_import = len(clock_reads)
model = s.pane_model()
answer = {'built_at_import': built_at_import,
          'built_on_request': s.pane_model() is s.PANE_MODEL,
          'summary_title': s.SUMMARY_GROUP_TITLE,
          'qt': 'PySide6' in sys.modules,
          'clock_reads_at_import': reads_at_import,
          'threads_started_at_import': threads_at_import,
          'rows_before_a_build': len(model.state.summary_rows),
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
    """Reaching the Bot Swarm tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["outbound_table"]["rows"] == [["BOT-B", "12.50%", "$0.0000"]]
    assert result["summary_group"]["rows"][2] == [
        surface.WIRED_IN_ROW_LABEL,
        "$120.5000",
    ]
    assert result["pending_table"]["rows"][0][0] == "6.9d"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_touches_nothing():
    """Loading the surface read a file, a clock, a thread or a host."""
    answered = run_script(INERT_IMPORT_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["summary_title"] == surface.SUMMARY_GROUP_TITLE, answered
    assert answered["qt"] is False, answered
    assert answered["clock_reads_at_import"] == 0, answered
    assert answered["threads_started_at_import"] == 0, answered
    assert answered["rows_before_a_build"] == 0, answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    read_by_the_surface = [
        name
        for name in answered["opened_at_import"]
        if "bot_swarm" in name or "acervator" in name.lower()
    ]
    assert read_by_the_surface == [], read_by_the_surface


def test_the_import_probe_can_report_a_file_a_clock_a_thread_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = INERT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import bot_swarm_tab_surface as s",
        "with open(root / 'acervator-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "time.time()\n"
        "_idle = threading.Event()\n"
        "_worker = threading.Thread(target=_idle.wait, daemon=True)\n"
        "_worker.start()\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "from src.gui.main_tabs import bot_swarm_tab_surface as s",
    )
    answered = run_script(probe)
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert answered["clock_reads_at_import"] >= 1, answered
    assert answered["threads_started_at_import"] >= 1, answered
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
        traced_qt(spec, monkeypatch)
        build_surface(spec)
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


def test_the_connection_counter_does_not_watch_a_child_process():
    """The in-process counter is claimed to see a child, and does not.

    The counter above patches this process only. A child gets its own
    counter inside the probe it runs, which is what reports for it.
    """
    answered = run_script(INERT_IMPORT_PROBE)
    assert answered["reached_at_import"] == []
    seeded = run_script(
        INERT_IMPORT_PROBE.replace(
            "from src.gui.main_tabs import bot_swarm_tab_surface as s",
            "try:\n"
            "    socket.create_connection(('example.invalid', 443))\n"
            "except OSError:\n"
            "    pass\n"
            "from src.gui.main_tabs import bot_swarm_tab_surface as s",
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
        traced_qt(spec, monkeypatch)
        build_surface(spec)
    for spec in UNREADABLE_SCENARIOS:
        traced_qt(spec, monkeypatch)
        build_surface(spec)
    for spec in REFUSING_SCENARIOS:
        wanted, _ = EXPECTED_REFUSALS[spec["name"]]
        with pytest.raises(wanted):
            traced_qt(spec, monkeypatch)
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
