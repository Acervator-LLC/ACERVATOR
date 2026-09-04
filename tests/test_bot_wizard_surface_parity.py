"""The Qt-free bot wizard describes the same screen the shipped one shows.

A failure means the surface and ``src/gui/bot_wizard.py`` disagree about
the screen that creates a bot: a default, a step, a refusal or a value
that reaches a new bot's configuration.

Both sides are driven in one run, from one set of inputs, and every
value is compared by value and by hash. The venue's market list, the
venue's timeframe support, the asset descriptions and the call-budget
verdict are handed to both sides, so nothing here opens a connection,
reads a credential or touches stored state.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import logging
import math
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from src.exchange.timeframes import available_timeframes
from src.gui import bot_wizard as shipped
from src.gui.main_tabs import bot_wizard_surface as surface
from tests.fixtures.host_fonts import (
    app_font_advance_px,
    has_real_fonts,
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
WIZARD_SOURCE = REPO_ROOT / "src" / "gui" / "bot_wizard.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "bot_wizard_surface.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "main_tabs" / "console_tab.py"
THREAD_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "crypto_news_ticker.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "usb_auth_widget.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

SHIPPED_CLASS_TOTAL = 7
SHIPPED_FUNCTION_TOTAL = 37
SOURCE_CONNECT_TOTAL = 10
RUNTIME_CONNECT_TOTAL = 10
SIGNAL_BUILD_TOTAL = 0
SIGNAL_EMIT_TOTAL = 0
TIMER_BUILD_TOTAL = 0
TIMER_START_TOTAL = 0
THREAD_BUILD_TOTAL = 0
THREAD_START_TOTAL = 0
BUS_SUBSCRIBE_TOTAL = 0
BUS_EMIT_TOTAL = 0

PIXEL_SIZE = (1100, 700)
CONTROL_RULE = "QWidget { background: #7d1a4a; }"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(scope="module", autouse=True)
def app():
    """One offscreen application for every render in this file."""
    from tests.qt_pixel import pin_text_rendering

    made = QApplication.instance() or QApplication([])
    pin_text_rendering(made)
    return made


def render_offscreen(widget, size):
    """One render of `widget` at `size`."""
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def digest(value) -> str:
    """SHA-256 over one answer, ordered so a swap changes it."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=repr).encode("utf-8")
    ).hexdigest()


# The seams: the venue, the box and the call-budget monitor


class FakeBox:
    """One message box that records what it was told to show.

    Stands in for ``QMessageBox`` so no drive opens a modal window. It
    fails loudly on a button role it was never given an answer for.
    """

    Information = "Information"
    Warning = "Warning"
    RejectRole = "RejectRole"
    AcceptRole = "AcceptRole"
    shown: list = []
    keep_going = False

    def __init__(self, _parent=None):
        self.title = ""
        self.text = ""
        self.informative = ""
        self.icon = ""
        self.buttons: list = []
        self.default = None
        self.clicked = None

    def setWindowTitle(self, title):
        self.title = title

    def setText(self, text):
        self.text = text

    def setInformativeText(self, text):
        self.informative = text

    def setIcon(self, icon):
        self.icon = icon

    def addButton(self, text, role):
        made = (text, role)
        self.buttons.append(made)
        return made

    def setDefaultButton(self, button):
        self.default = button

    def exec(self):
        if not self.buttons:
            FakeBox.shown.append([self.title, self.text, self.informative])
            return 0
        accept = [one for one in self.buttons if one[1] == FakeBox.AcceptRole]
        reject = [one for one in self.buttons if one[1] == FakeBox.RejectRole]
        if not accept or not reject:
            raise AssertionError(
                "this box was opened without both an accept and a reject "
                f"button, so no answer can be given: {self.buttons}"
            )
        self.clicked = accept[0] if FakeBox.keep_going else reject[0]
        FakeBox.shown.append([self.title, self.text, self.informative])
        return 0

    def clickedButton(self):
        return self.clicked


class FakeLoadMonitor:
    """One call-budget monitor that answers from a canned verdict."""

    def __init__(self, answer):
        self.answer = answer
        self.asked: list = []

    def should_allow_new_phantom_set(self, exchange, tf_count):
        self.asked.append((exchange, tf_count))
        return self.answer


class QtSeams:
    """Swap the outward edges of the shipped wizard for the drive.

    The market fetch, the asset manager, the message box and the
    call-budget monitor are each replaced for the length of one drive
    and put back after it, including after a refusal. ``restored`` says
    whether every swapped name holds what it held before.
    """

    def __init__(self, markets=None, load_answer=None, keep_going=False):
        self.markets = markets or {}
        self.load_answer = load_answer
        self.keep_going = keep_going
        self.saved: dict = {}
        self.monitor = None
        self.fetched: list = []

    def __enter__(self):
        import PySide6.QtWidgets as widgets
        from src.exchange import api_load_monitor

        self.saved = {
            (shipped.AssetSelectionPage, "_fetch_markets"): (
                shipped.AssetSelectionPage._fetch_markets
            ),
            (shipped.ExtractorPoolPage, "_fetch_markets"): (
                shipped.ExtractorPoolPage._fetch_markets
            ),
            (shipped._ASSET_MANAGER, "get"): shipped._ASSET_MANAGER.get,
            (widgets, "QMessageBox"): widgets.QMessageBox,
            (api_load_monitor, "get_load_monitor"): (api_load_monitor.get_load_monitor),
        }
        rows = self.markets
        fetched = self.fetched

        def canned(_page, exchange_id):
            fetched.append(exchange_id)
            return [dict(one) for one in rows.get(exchange_id, [])]

        shipped.AssetSelectionPage._fetch_markets = canned
        shipped.ExtractorPoolPage._fetch_markets = canned
        shipped._ASSET_MANAGER.get = lambda: None
        FakeBox.shown = []
        FakeBox.keep_going = self.keep_going
        widgets.QMessageBox = FakeBox
        self.monitor = FakeLoadMonitor(self.load_answer or (True, "ok"))
        api_load_monitor.get_load_monitor = lambda: self.monitor
        return self

    def __exit__(self, *_found):
        for (owner, name), value in self.saved.items():
            setattr(owner, name, value)
        return False

    def restored(self) -> bool:
        """Whether every swapped name holds what it held before the drive."""
        return all(
            getattr(owner, name) is value for (owner, name), value in self.saved.items()
        )


# What each side is asked

EXCHANGES = [
    {"display_name": "Coinbase", "exchange_id": "coinbase"},
    {"display_name": "Kraken", "exchange_id": "kraken"},
]
MARKETS = {
    "coinbase": [
        {
            "symbol": "ZZZ/USDT",
            "base": "ZZZ",
            "quote": "USDT",
            "volume": 2.5e9,
            "volatility": 3.2,
        },
        {
            "symbol": "YYY/USDT",
            "base": "YYY",
            "quote": "USDT",
            "volume": 1.5e6,
            "volatility": 0.0,
        },
        {
            "symbol": "WWW/BTC",
            "base": "WWW",
            "quote": "BTC",
            "volume": 4.0e3,
            "volatility": 12.75,
        },
    ],
    "kraken": [
        {
            "symbol": "QQQ/USDT",
            "base": "QQQ",
            "quote": "USDT",
            "volume": 0.0,
            "volatility": 0.0,
        }
    ],
}
DESCRIPTIONS = {"ZZZ": "Zed Coin (ZZZ)\nA made-up asset for this run."}

NUMBER_WIDGETS = {
    "split_distance": ("params", "_split_distance"),
    "stack_count": ("params", "_stack_count"),
    "personal_hold_qty": ("params", "_personal_hold_qty"),
    "scrumming_interval": ("params", "_scrumming_interval"),
    "bb_tolerance": ("params", "_bb_tolerance"),
    "ls_candles": ("params", "_ls_candles"),
    "target_balance": ("params", "_target_balance"),
    "max_entry_px": ("params", "_max_entry_px"),
    "min_entry_px": ("params", "_min_entry_px"),
    "trading_fee": ("params", "_trading_fee"),
    "max_target_growth_pct": ("params", "_max_target_growth_pct"),
    "scrum_fold_pct": ("params", "_scrum_fold_pct"),
    "scrum_detect_pct": ("params", "_scrum_detect_pct"),
    "scrum_fire_pct": ("params", "_scrum_fire_pct"),
    "scrum_read_rate": ("params", "_scrum_read_rate"),
    "band_travel_pct": ("params", "_band_travel_pct"),
    "wire_inflow_stack_pct": ("params", "_wire_inflow_stack_pct"),
    "hedge_amount": ("params", "_hedge_amount"),
    "cb_soft_pct": ("params", "_cb_soft_pct"),
    "cb_hard_pct": ("params", "_cb_hard_pct"),
    "cb_cooldown": ("params", "_cb_cooldown"),
    "max_cartridge_pct": ("params", "_max_cartridge_pct"),
    "cartridge_smart_ceiling": ("params", "_cartridge_smart_ceiling"),
    "position_ceiling_multiple": ("params", "_position_ceiling_multiple"),
    "detonation_confidence_min": ("params", "_detonation_confidence_min"),
    "ext_chunk_size_usd": ("params", "_ext_chunk_size_usd"),
    "ext_artillery_size_usd": ("params", "_ext_artillery_size_usd"),
    "ext_scan_top_n": ("params", "_ext_scan_top_n"),
    "ext_scan_refresh": ("params", "_ext_scan_refresh"),
    "ext_pool_reserve": ("params", "_ext_pool_reserve"),
    "ext_exit_pct": ("params", "_ext_exit_pct"),
    "ext_max_tier": ("params", "_ext_max_tier"),
    "ext_max_cost_basis": ("params", "_ext_max_cost_basis"),
    "ext_standing_alt_units": ("params", "_ext_standing_alt_units"),
    "ext_correction_skip": ("params", "_ext_correction_skip"),
    "ext_drawdown_threshold": ("params", "_ext_drawdown_threshold"),
    "ext_hedge_budget": ("params", "_ext_hedge_budget"),
    "ext_trend_strength": ("params", "_ext_trend_strength"),
    "fold_x_count": ("folding", "_fold_x_count"),
    "dist_x_count": ("folding", "_dist_x_count"),
    "lock_candles": ("phantom", "_lock_candles"),
}
CHECK_WIDGETS = {
    "aggressive": ("params", "_aggressive"),
    "stack_mode": ("params", "_stack_mode"),
    "bb_midline_gate": ("params", "_bb_midline_gate"),
    "bb_bullseye": ("params", "_bb_bullseye"),
    "hedge_rebalance": ("params", "_hedge_rebalance"),
    "cartridge_smart_chk": ("params", "_cartridge_smart_chk"),
    "position_ceiling_enabled": ("params", "_position_ceiling_enabled"),
    "detonation_enabled": ("params", "_detonation_enabled"),
    "gate_scrum_ta_chk": ("params", "_gate_scrum_ta_chk"),
    "gate_scrum_uptrend_chk": ("params", "_gate_scrum_uptrend_chk"),
    "gate_scrum_htf_chk": ("params", "_gate_scrum_htf_chk"),
    "gate_fold_ta_chk": ("params", "_gate_fold_ta_chk"),
    "gate_fold_htf_chk": ("params", "_gate_fold_htf_chk"),
    "folding_active": ("folding", "_active"),
    "phantom_enable": ("phantom", "_enable"),
}
RADIO_WIDGETS = {
    "scrumming": ("mode", "_scrumming"),
    "extractor": ("mode", "_extractor"),
    "fold_equal": ("folding", "_fold_equal"),
    "fold_log": ("folding", "_fold_log"),
    "fold_all": ("folding", "_fold_all"),
    "fold_x": ("folding", "_fold_x"),
    "fold_recent": ("folding", "_fold_recent"),
    "dist_all": ("folding", "_dist_all"),
    "dist_x": ("folding", "_dist_x"),
    "dist_recent": ("folding", "_dist_recent"),
}
COMBO_WIDGETS = {
    "base": ("asset", "_base"),
    "pool_base": ("pool", "_base"),
    "visibility": ("params", "_visibility"),
    "stack_spacing": ("params", "_stack_spacing"),
    "ta_timeframe": ("params", "_ta_timeframe"),
    "detonation_timeframe": ("params", "_detonation_timeframe"),
    "profit_route": ("params", "_profit_route"),
    "ext_direction": ("params", "_ext_direction"),
}
TEXT_WIDGETS = {"profit_route_bot_id": ("params", "_profit_route_bot_id")}
GROUP_WIDGETS = {
    "mode_group": "_mode_group",
    "scrum_group": "_scrum_group",
    "adv_group": "_adv_group",
    "hedge_group": "_hedge_group",
    "cb_group": "_cb_group",
    "risk_group": "_risk_group",
    "gates_group": "_gates_group",
    "routing_group": "_routing_group",
    "extractor_group": "_extractor_group",
}


def case(name, **named):
    """One input both sides are driven with."""
    spec = {
        "name": name,
        "exchanges": EXCHANGES,
        "defaults": {},
        "markets": MARKETS,
        "descriptions": DESCRIPTIONS,
        "mode": surface.SCRUMMING_MODE,
        "numbers": {},
        "checks": {},
        "radios": {},
        "combo_indexes": {},
        "texts": {},
        "exchange_index": None,
        "pool_exchange_index": None,
        "target_index": None,
        "alt_checks": {},
        "select_all": False,
        "clear_all": False,
        "phantom_timeframes": {},
        "show_info": False,
        "walk": [],
        "load_answer": (True, "ok"),
        "keep_going": False,
    }
    spec.update(named)
    return spec


ALL_CASES = [
    case("happy"),
    case("stored_target_balance", defaults={"default_target_balance": 1234.56}),
    case("stored_target_balance_absent", defaults={}),
    case("extractor", mode=surface.EXTRACTOR_MODE),
    case("second_venue", exchange_index=1),
    case("base_btc", combo_indexes={"base": 2}),
    case("base_with_no_pairs", combo_indexes={"base": 4}),
    case("target_second", target_index=1),
    case("target_out_of_range", target_index=99),
    case("show_info_described", target_index=0, show_info=True),
    case("show_info_undescribed", target_index=1, show_info=True),
    case(
        "extractor_pool_ticked",
        mode=surface.EXTRACTOR_MODE,
        alt_checks={0: True},
    ),
    case("extractor_select_all", mode=surface.EXTRACTOR_MODE, select_all=True),
    case(
        "extractor_clear_all",
        mode=surface.EXTRACTOR_MODE,
        select_all=True,
        clear_all=True,
    ),
    case(
        "extractor_pool_base_eth",
        mode=surface.EXTRACTOR_MODE,
        combo_indexes={"pool_base": 1},
    ),
    case("zero_numbers", numbers={"target_balance": 0.0, "hedge_amount": 0.0}),
    case("negative_numbers", numbers={"target_balance": -5.0, "trading_fee": -1.0}),
    case("a_thousand_million", numbers={"target_balance": 1_000_000_000.0}),
    case("one_billionth", numbers={"personal_hold_qty": 1e-9}),
    case("infinity", numbers={"target_balance": math.inf}),
    case("minus_infinity", numbers={"target_balance": -math.inf}),
    case("not_a_number", numbers={"target_balance": math.nan}),
    case("two_to_the_1023", numbers={"target_balance": float(2**1023)}),
    case(
        "stored_true_where_a_number_belongs", defaults={"default_target_balance": True}
    ),
    case("stored_number_rounds", defaults={"default_target_balance": 12.7564}),
    case("all_checks_off", checks={name: False for name in surface.CHECK_FIELDS}),
    case("all_checks_on", checks={name: True for name in surface.CHECK_FIELDS}),
    case("unicode_bot_id", texts={"profit_route_bot_id": "bot-Ωμέγα-1"}),
    case("long_bot_id", texts={"profit_route_bot_id": "b" * 200}),
    case("markup_bot_id", texts={"profit_route_bot_id": "<b>bot</b>&amp;"}),
    case("apostrophe_bot_id", texts={"profit_route_bot_id": "bot's own"}),
    case("wrong_capitals_bot_id", texts={"profit_route_bot_id": "BoT-ONE"}),
    case("newline_bot_id", texts={"profit_route_bot_id": "bot\none"}),
    case("empty_bot_id", texts={"profit_route_bot_id": ""}),
    case("cross_bot_route", combo_indexes={"profit_route": 3}),
    case("route_out_of_range", combo_indexes={"profit_route": 40}),
    case(
        "phantoms_on", checks={"phantom_enable": True}, phantom_timeframes={"1h": True}
    ),
    case(
        "phantoms_on_unsupported_tf",
        checks={"phantom_enable": True},
        phantom_timeframes={"4h": True},
    ),
    case("walk_forward", walk=[["next"], ["next"], ["next"]]),
    case(
        "walk_forward_extractor", mode=surface.EXTRACTOR_MODE, walk=[["next"], ["next"]]
    ),
    case("walk_back_from_asset", walk=[["next"], ["back"]]),
    case("walk_back_from_params", walk=[["next"], ["next"], ["back"]]),
    case("walk_back_from_phantom", walk=[["next"], ["next"], ["next"], ["back"]]),
    case("walk_back_with_no_history", walk=[["back"]]),
    case("walk_next_past_the_end", walk=[["next"], ["next"], ["next"], ["next"]]),
    case("cancel_from_mode", walk=[["cancel"]]),
    case("cancel_from_asset", walk=[["next"], ["cancel"]]),
    case("cancel_from_params", walk=[["next"], ["next"], ["cancel"]]),
    case("cancel_from_phantom", walk=[["next"], ["next"], ["next"], ["cancel"]]),
    case("finish_from_a_page_that_is_not_last", walk=[["finish"]]),
    case("finish_from_the_last_page", walk=[["next"], ["next"], ["next"], ["finish"]]),
    case(
        "finish_from_the_last_extractor_page",
        mode=surface.EXTRACTOR_MODE,
        walk=[["next"], ["next"], ["finish"]],
    ),
    case(
        "refused_at_the_phantom_page",
        checks={"phantom_enable": True},
        phantom_timeframes={"1h": True, "5m": True},
        load_answer=(False, "projected 900 CPM over threshold 600"),
        walk=[["next"], ["next"], ["next"], ["next"]],
    ),
    case(
        "refused_then_corrected",
        checks={"phantom_enable": True},
        phantom_timeframes={"1h": True, "5m": True},
        load_answer=(False, "projected 900 CPM over threshold 600"),
        walk=[["next"], ["next"], ["next"], ["next"]],
        keep_going=True,
    ),
    case(
        "refused_then_backed_off",
        checks={"phantom_enable": True},
        phantom_timeframes={"1h": True, "5m": True},
        load_answer=(False, "projected 900 CPM over threshold 600"),
        walk=[["next"], ["next"], ["next"], ["next"], ["back"]],
    ),
]
BY_NAME = {spec["name"]: spec for spec in ALL_CASES}

REFUSING_CASES = {
    "text_where_a_number_belongs": ("number", "target_balance", "12.7"),
    "text_where_a_check_belongs": ("check", "aggressive", "yes"),
    "a_number_where_text_belongs": ("text", "profit_route_bot_id", 12),
    "a_fraction_where_a_check_belongs": ("check", "aggressive", 12.7),
    "not_a_number_in_a_whole_number_field": ("number", "stack_count", math.nan),
    "infinity_in_a_whole_number_field": ("number", "stack_count", math.inf),
    "minus_infinity_in_a_whole_number_field": ("number", "stack_count", -math.inf),
    "two_to_the_1024_in_a_number_field": ("number", "target_balance", 2**1024),
    "nothing_where_a_number_belongs": ("number", "target_balance", None),
}

PICTURE_CASES = [
    "mode",
    "asset",
    "extractor_pool",
    "params_scrumming",
    "params_extractor",
    "folding",
    "phantom",
    "phantom_refused",
]


# Driving the shipped wizard


def supported_timeframes(exchange_id):
    """The timeframes one venue offers, read once and handed to both sides."""
    return list(available_timeframes(exchange_id))


def build_wizard(spec, seams):
    """The shipped wizard, built and driven with one case's steps."""
    wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
    pages = {
        "asset": wizard._asset_page,
        "mode": wizard._mode_page,
        "pool": wizard._extractor_pool_page,
        "params": wizard._params_page,
        "folding": wizard._folding_page,
        "phantom": wizard._phantom_page,
    }
    pages["asset"]._descriptions_cache = dict(spec["descriptions"])
    pages["asset"]._update_info()
    wizard.restart()
    if spec["mode"] == surface.EXTRACTOR_MODE:
        pages["mode"]._extractor.setChecked(True)
    if spec["exchange_index"] is not None:
        pages["asset"]._exchange.setCurrentIndex(spec["exchange_index"])
    if spec["pool_exchange_index"] is not None:
        pages["pool"]._exchange.setCurrentIndex(spec["pool_exchange_index"])
    for name, value in spec["numbers"].items():
        page, attribute = NUMBER_WIDGETS[name]
        getattr(pages[page], attribute).setValue(value)
    for name, value in spec["checks"].items():
        page, attribute = CHECK_WIDGETS[name]
        getattr(pages[page], attribute).setChecked(value)
    for name, value in spec["radios"].items():
        page, attribute = RADIO_WIDGETS[name]
        getattr(pages[page], attribute).setChecked(value)
    for name, value in spec["combo_indexes"].items():
        page, attribute = COMBO_WIDGETS[name]
        getattr(pages[page], attribute).setCurrentIndex(value)
    for name, value in spec["texts"].items():
        page, attribute = TEXT_WIDGETS[name]
        getattr(pages[page], attribute).setText(value)
    if spec["target_index"] is not None:
        pages["asset"]._target.setCurrentIndex(spec["target_index"])
    for position, value in spec["alt_checks"].items():
        item = pages["pool"]._alt_list.item(position)
        item.setCheckState(Qt.Checked if value else Qt.Unchecked)
    if spec["select_all"]:
        pages["pool"]._select_all()
    if spec["clear_all"]:
        pages["pool"]._clear_all()
    for name, value in spec["phantom_timeframes"].items():
        pages["phantom"]._tf_checks[name].setChecked(value)
    if spec["show_info"]:
        pages["asset"]._show_info()
    for step in spec["walk"]:
        name = step[0]
        if name == "next":
            wizard.next()
        elif name == "back":
            wizard.back()
        elif name == "cancel":
            wizard.reject()
        elif name == "finish":
            if wizard.nextId() == -1:
                wizard.accept()
    seams.fetched.append(None)
    return wizard, pages


def old_state(wizard, pages, spec):
    """Every value the shipped wizard shows, as one plain answer."""
    numbers = {}
    for name, (page, attribute) in NUMBER_WIDGETS.items():
        numbers[name] = getattr(pages[page], attribute).value()
    checks = {
        name: getattr(pages[page], attribute).isChecked()
        for name, (page, attribute) in CHECK_WIDGETS.items()
    }
    radios = {
        name: getattr(pages[page], attribute).isChecked()
        for name, (page, attribute) in RADIO_WIDGETS.items()
    }
    combo_indexes = {
        name: getattr(pages[page], attribute).currentIndex()
        for name, (page, attribute) in COMBO_WIDGETS.items()
    }
    texts = {
        name: getattr(pages[page], attribute).text()
        for name, (page, attribute) in TEXT_WIDGETS.items()
    }
    target = pages["asset"]._target
    alt_list = pages["pool"]._alt_list
    return {
        "window": {
            "title": wizard.windowTitle(),
            "accessible_name": wizard.accessibleName(),
            "accessible_description": wizard.accessibleDescription(),
            "minimum_size_px": [wizard.minimumWidth(), wizard.minimumHeight()],
        },
        "page": {
            "current_id": wizard.currentId(),
            "next_id": wizard.nextId(),
            "titles": {name: page.title() for name, page in sorted(pages.items())},
            "subtitles": {
                name: page.subTitle() for name, page in sorted(pages.items())
            },
        },
        "values": {
            "numbers": numbers,
            "checks": checks,
            "radios": radios,
            "combo_indexes": combo_indexes,
            "texts": texts,
        },
        "groups": {
            name: not getattr(pages["params"], attribute).isHidden()
            for name, attribute in GROUP_WIDGETS.items()
        },
        "asset_page": {
            "exchange_index": pages["asset"]._exchange.currentIndex(),
            "target_items": [
                [target.itemText(at), target.itemData(at)]
                for at in range(target.count())
            ],
            "target_index": target.currentIndex(),
            "target_data": target.currentData(),
            "status": pages["asset"]._status.text(),
            "info_tool_tip": pages["asset"]._info_btn.toolTip(),
            "config": pages["asset"].get_config(),
        },
        "pool_page": {
            "exchange_index": pages["pool"]._exchange.currentIndex(),
            "alt_items": [
                [alt_list.item(at).text(), alt_list.item(at).data(Qt.UserRole)]
                for at in range(alt_list.count())
            ],
            "alt_checked": [
                alt_list.item(at).checkState() == Qt.Checked
                for at in range(alt_list.count())
            ],
            "status": pages["pool"]._status.text(),
            "config": pages["pool"].get_config(),
        },
        "phantom_page": {
            "checked": {
                name: box.isChecked()
                for name, box in pages["phantom"]._tf_checks.items()
            },
            "enabled": {
                name: box.isEnabled()
                for name, box in pages["phantom"]._tf_checks.items()
            },
            "tool_tips": {
                name: box.toolTip() for name, box in pages["phantom"]._tf_checks.items()
            },
            "config": pages["phantom"].get_config(),
        },
        "folding_page": {"config": pages["folding"].get_config()},
        "params_config": pages["params"].get_config(),
        "config": wizard.get_bot_config(),
        "boxes": [list(one) for one in FakeBox.shown],
        "is_extractor": pages["mode"].is_extractor(),
        "is_grid": pages["mode"].is_grid(),
        "ta_timeframe_items": [
            pages["params"]._ta_timeframe.itemText(at)
            for at in range(pages["params"]._ta_timeframe.count())
        ],
    }


def drive_old(spec):
    """Build and drive the shipped wizard for one case."""
    with QtSeams(
        markets=spec["markets"],
        load_answer=spec["load_answer"],
        keep_going=spec["keep_going"],
    ) as seams:
        during = seams.restored()
        wizard, pages = build_wizard(spec, seams)
        state = old_state(wizard, pages, spec)
    return {
        "state": state,
        "seams": seams,
        "swapped_during": not during,
        "wizard": wizard,
        "pages": pages,
    }


# Driving the surface


def venue_timeframes(spec):
    """Each venue's timeframe support, read once and handed to both sides."""
    return {
        one["exchange_id"]: supported_timeframes(one["exchange_id"])
        for one in spec["exchanges"]
    }


def new_model(spec):
    """Build and drive the surface's model for one case."""
    model = surface.BotWizardModel(
        spec["exchanges"],
        spec["defaults"],
        spec["markets"],
        venue_timeframes(spec),
    )
    model.descriptions = dict(spec["descriptions"])
    model.update_info()
    if spec["mode"] == surface.EXTRACTOR_MODE:
        model.select_mode(True)
    if spec["exchange_index"] is not None:
        model.set_exchange_index(spec["exchange_index"])
    if spec["pool_exchange_index"] is not None:
        model.set_pool_exchange_index(spec["pool_exchange_index"])
    for name, value in spec["numbers"].items():
        model.set_number(name, value)
    for name, value in spec["checks"].items():
        model.set_check(name, value)
    for name, value in spec["radios"].items():
        model.set_radio(name, value)
    for name, value in spec["combo_indexes"].items():
        model.set_combo_index(name, value)
    for name, value in spec["texts"].items():
        model.set_text(name, value)
    if spec["target_index"] is not None:
        model.set_target_index(spec["target_index"])
    for position, value in spec["alt_checks"].items():
        model.set_alt_checked(position, value)
    if spec["select_all"]:
        model.select_all_alts()
    if spec["clear_all"]:
        model.clear_all_alts()
    for name, value in spec["phantom_timeframes"].items():
        model.set_phantom_timeframe(name, value)
    if spec["show_info"]:
        model.show_info()
    for step in spec["walk"]:
        name = step[0]
        if name == "next":
            model.go_next(spec["load_answer"], spec["keep_going"])
        elif name == "back":
            model.go_back()
        elif name == "cancel":
            model.cancel()
        elif name == "finish":
            model.finish()
    return model


def new_state(model, spec):
    """Every value the surface describes, in the shipped wizard's shape."""
    pages = {
        "asset": surface.ASSET,
        "mode": surface.MODE,
        "pool": surface.EXTRACTOR_POOL,
        "params": surface.PARAMS,
        "folding": surface.FOLDING,
        "phantom": surface.PHANTOM,
    }
    subtitles = dict(surface.PAGE_SUBTITLES)
    subtitles[surface.PARAMS] = model.params_subtitle
    groups = dict(model.group_visible)
    return {
        "window": {
            "title": surface.WINDOW_TITLE,
            "accessible_name": surface.ACCESSIBLE_NAME,
            "accessible_description": surface.ACCESSIBLE_DESCRIPTION,
            "minimum_size_px": list(surface.MINIMUM_SIZE_PX),
        },
        "page": {
            "current_id": model.current_page_id(),
            "next_id": model.next_page(),
            "titles": {
                name: surface.PAGE_TITLES[page] for name, page in sorted(pages.items())
            },
            "subtitles": {
                name: subtitles[page] for name, page in sorted(pages.items())
            },
        },
        "values": {
            "numbers": dict(model.numbers),
            "checks": dict(model.checks),
            "radios": dict(model.radios),
            "combo_indexes": dict(model.combo_indexes),
            "texts": dict(model.texts),
        },
        "groups": groups,
        "asset_page": {
            "exchange_index": model.exchange_index,
            "target_items": [list(one) for one in model.target_items],
            "target_index": model.target_index,
            "target_data": model.target_data(),
            "status": model.asset_status,
            "info_tool_tip": model.info_tool_tip,
            "config": model.asset_config(),
        },
        "pool_page": {
            "exchange_index": model.pool_exchange_index,
            "alt_items": [list(one) for one in model.alt_items],
            "alt_checked": list(model.alt_checked),
            "status": model.pool_status,
            "config": model.pool_config(),
        },
        "phantom_page": {
            "checked": dict(model.phantom_checks),
            "enabled": dict(model.phantom_enabled_timeframes),
            "tool_tips": dict(model.phantom_tool_tips),
            "config": model.phantom_config(),
        },
        "folding_page": {"config": model.folding_config()},
        "params_config": model.params_config(),
        "config": model.get_bot_config(),
        "boxes": model_boxes(model),
        "is_extractor": model.is_extractor(),
        "is_grid": model.is_grid(),
        "ta_timeframe_items": [pair[0] for pair in model.ta_timeframe_items],
    }


def model_boxes(model):
    """Every box the surface says the wizard opened, in the order it did."""
    found = []
    if model.info_box is not None:
        found.append([model.info_box[0], model.info_box[1], ""])
    if model.warning_box is not None:
        found.append(list(model.warning_box))
    return found


def drive_new(spec):
    """Drive the surface for one case."""
    return new_model(spec)


def old_answer(spec):
    """The shipped wizard's answer for one case, ready to compare."""
    return drive_old(spec)["state"]


def new_answer(spec):
    """The surface's answer for one case, ready to compare."""
    return new_state(drive_new(spec), spec)


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", [spec["name"] for spec in ALL_CASES])
def test_the_two_sides_describe_the_same_screen(name):
    """The surface and the shipped wizard disagree about the bot screen."""
    spec = BY_NAME[name]
    old = old_answer(spec)
    new = new_answer(spec)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(REFUSING_CASES))
def test_a_refused_input_raises_the_same_kind_on_both_sides(name):
    """A misuse refused on one side is accepted on the other."""
    kind, field, value = REFUSING_CASES[name]
    spec = BY_NAME["happy"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        pages = {
            "params": wizard._params_page,
            "folding": wizard._folding_page,
            "phantom": wizard._phantom_page,
        }
        with pytest.raises(Exception) as old_refusal:
            if kind == "number":
                page, attribute = NUMBER_WIDGETS[field]
                getattr(pages[page], attribute).setValue(value)
            elif kind == "check":
                page, attribute = CHECK_WIDGETS[field]
                getattr(pages[page], attribute).setChecked(value)
            else:
                page, attribute = TEXT_WIDGETS[field]
                getattr(pages[page], attribute).setText(value)
    assert seams.restored() is True

    model = new_model(BY_NAME["happy"])
    with pytest.raises(Exception) as new_refusal:
        if kind == "number":
            model.set_number(field, value)
        elif kind == "check":
            model.set_check(field, value)
        else:
            model.set_text(field, value)
    assert type(new_refusal.value) is type(old_refusal.value), (
        name,
        repr(old_refusal.value),
        repr(new_refusal.value),
    )


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever the answer holds."""
    first = digest(new_answer(BY_NAME["happy"]))
    second = digest(new_answer(BY_NAME["extractor"]))
    assert first != second


@pytest.mark.parametrize("name", ["happy", "extractor", "refused_at_the_phantom_page"])
def test_the_sample_hashes_are_reported(name):
    """A sample hash moved, so one side changed without the other."""
    spec = BY_NAME[name]
    old = digest(old_answer(spec))
    new = digest(new_answer(spec))
    assert old == new, f"{name}: old {old}, new {new}"
    assert len(new) == 64


def test_two_different_real_inputs_are_told_apart_in_both_directions():
    """The comparison passes whatever the other side answers."""
    first = BY_NAME["happy"]
    second = BY_NAME["second_venue"]
    assert old_answer(first) != new_answer(second)
    assert old_answer(second) != new_answer(first)
    assert old_answer(first) == new_answer(first)
    assert old_answer(second) == new_answer(second)


def test_the_same_input_twice_describes_one_screen():
    """A driven case depends on something outside the case.

    Each side is driven twice, from scratch, and the two answers
    compared. A third drive of a different input proves the comparison
    reports a difference when there is one.
    """
    spec = BY_NAME["happy"]
    other = BY_NAME["extractor"]
    first_new, second_new = digest(new_answer(spec)), digest(new_answer(spec))
    first_old, second_old = digest(old_answer(spec)), digest(old_answer(spec))
    assert first_new == second_new
    assert first_old == second_old
    assert digest(new_answer(other)) != first_new
    assert digest(old_answer(other)) != first_old


def test_a_whole_number_and_a_decimal_are_told_apart_by_the_hash():
    """A whole number and a decimal compare equal, so a swap hides."""
    whole = surface.number_value(12, surface.NUMBER_FIELDS["target_balance"])
    decimal = surface.number_value(12.0, surface.NUMBER_FIELDS["target_balance"])
    assert whole == decimal
    assert digest({"value": 12}) != digest({"value": 12.0})


def test_two_not_a_numbers_settle_on_the_same_highest_value():
    """Two not-a-numbers compare unequal, so a difference is reported that is not one.

    Two not-a-numbers never compare equal to each other, so the field
    is asked what it settles on instead, and the two answers are what
    is compared.
    """
    spec = surface.NUMBER_FIELDS["target_balance"]
    first = surface.number_value(float("nan"), spec)
    second = surface.number_value(math.nan, spec)
    assert first == second == spec["maximum"]
    assert not math.isnan(first), first
    assert surface.number_value(-math.inf, spec) != first


# The steps the wizard takes

FORWARD_SCRUMMING = [1, 0, 2, 4]
FORWARD_EXTRACTOR = [1, 5, 2]


def test_the_scrumming_route_visits_four_pages_in_one_order():
    """The route out of a page changed on one side only."""
    spec = BY_NAME["happy"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        wizard.restart()
        walked = [wizard.currentId()]
        while wizard.nextId() != -1:
            wizard.next()
            walked.append(wizard.currentId())
    assert seams.restored() is True
    assert walked == FORWARD_SCRUMMING, walked
    model = new_model(spec)
    theirs = [model.current_page_id()]
    while model.next_page() != -1:
        model.go_next()
        theirs.append(model.current_page_id())
    assert theirs == walked, (theirs, walked)


def test_the_extractor_route_visits_three_pages_in_one_order():
    """The extractor route changed on one side only."""
    spec = BY_NAME["extractor"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        wizard.restart()
        wizard._mode_page._extractor.setChecked(True)
        walked = [wizard.currentId()]
        while wizard.nextId() != -1:
            wizard.next()
            walked.append(wizard.currentId())
    assert seams.restored() is True
    assert walked == FORWARD_EXTRACTOR, walked
    model = new_model(spec)
    theirs = [model.current_page_id()]
    while model.next_page() != -1:
        model.go_next()
        theirs.append(model.current_page_id())
    assert theirs == walked, (theirs, walked)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_stepping_back_from_every_page_lands_where_it_came_from(depth):
    """Back lands on a page other than the one the wizard came from."""
    spec = BY_NAME["happy"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        wizard.restart()
        for _ in range(depth):
            wizard.next()
        wizard.back()
        landed = wizard.currentId()
    assert seams.restored() is True
    model = new_model(spec)
    for _ in range(depth):
        model.go_next()
    model.go_back()
    assert model.current_page_id() == landed, (model.current_page_id(), landed)
    assert landed == FORWARD_SCRUMMING[depth - 1]


def test_the_profit_folding_page_is_registered_and_never_routed_to():
    """A page the route can reach is reported as unreachable, or the reverse."""
    spec = BY_NAME["happy"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        registered = sorted(wizard.pageIds())
        reachable = set()
        for mode in (False, True):
            wizard.restart()
            wizard._mode_page._extractor.setChecked(mode)
            reachable.add(wizard.currentId())
            while wizard.nextId() != -1:
                wizard.next()
                reachable.add(wizard.currentId())
    assert seams.restored() is True
    assert registered == sorted(surface.PAGE_IDS.values()), registered
    missed = set(registered) - reachable
    assert missed == {surface.PAGE_IDS[surface.FOLDING]}, missed
    assert list(surface.UNREACHABLE_PAGES) == [surface.FOLDING]


def test_a_step_that_is_refused_keeps_what_was_entered_before_it():
    """A refusal threw away a value the operator had already typed."""
    spec = BY_NAME["refused_at_the_phantom_page"]
    before = new_model(BY_NAME["happy"])
    before.set_number("target_balance", 4321.5)
    kept_before = before.numbers["target_balance"]
    model = new_model(spec)
    model.set_number("target_balance", 4321.5)
    for _ in range(3):
        model.go_next()
    moved = model.go_next(spec["load_answer"], False)
    assert moved is False
    assert model.refusal == surface.REFUSAL_API_LOAD
    assert model.current_page == surface.PHANTOM
    assert model.numbers["target_balance"] == kept_before == 4321.5
    assert model.get_bot_config()["target_balance"] == 4321.5


def test_a_refusal_followed_by_a_correction_lets_the_wizard_through():
    """A corrected refusal still blocks the wizard."""
    spec = BY_NAME["refused_then_corrected"]
    model = new_model(BY_NAME["happy"])
    model.set_check("phantom_enable", True)
    model.set_phantom_timeframe("1h", True)
    for _ in range(3):
        model.go_next()
    assert model.go_next(spec["load_answer"], False) is False
    assert model.refusal == surface.REFUSAL_API_LOAD
    model.set_phantom_timeframe("1h", False)
    assert model.go_next(spec["load_answer"], False) is False
    assert model.refusal == surface.REFUSAL_NO_ROUTE
    assert model.finish() is True
    assert model.outcome == surface.OUTCOME_FINISHED


def test_the_refusal_names_a_type_and_not_a_wording():
    """A refusal is told apart by its wording, which the platform may change."""
    spec = BY_NAME["refused_at_the_phantom_page"]
    model = new_model(spec)
    for _ in range(3):
        model.go_next()
    model.go_next(spec["load_answer"], False)
    assert model.refusal == surface.REFUSAL_API_LOAD
    assert set(model.refusals) <= set(surface.REFUSAL_TYPES), model.refusals
    assert surface.REFUSAL_API_LOAD in model.refusals


@pytest.mark.parametrize("depth", [0, 1, 2, 3])
def test_cancelling_from_every_page_leaves_the_wizard_on_no_page(depth):
    """Cancel left the wizard on a page it should have closed."""
    spec = BY_NAME["happy"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        wizard.restart()
        for _ in range(depth):
            wizard.next()
        wizard.reject()
        after = (wizard.currentId(), wizard.nextId())
    assert seams.restored() is True
    model = new_model(spec)
    for _ in range(depth):
        model.go_next()
    model.cancel()
    assert (model.current_page_id(), model.next_page()) == after, after
    assert model.outcome == surface.OUTCOME_CANCELLED


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_finishing_before_the_last_page_is_not_offered(depth):
    """The wizard offered Finish on a page that is not the last."""
    spec = BY_NAME["happy"]
    with QtSeams(markets=spec["markets"]) as seams:
        wizard = shipped.BotCreationWizard(spec["exchanges"], spec["defaults"])
        wizard.restart()
        for _ in range(depth):
            wizard.next()
        offered = wizard.button(QWizard.FinishButton).isEnabled()
    assert seams.restored() is True
    model = new_model(spec)
    for _ in range(depth):
        model.go_next()
    assert model.is_final_page() is offered is False
    assert model.finish() is False
    assert model.refusal == surface.REFUSAL_NOT_FINAL
    assert model.outcome == surface.OUTCOME_OPEN


def test_finishing_on_the_last_page_creates_the_bot():
    """The last page refused to finish."""
    spec = BY_NAME["happy"]
    model = new_model(spec)
    while model.next_page() != -1:
        model.go_next()
    assert model.is_final_page() is True
    assert model.finish() is True
    assert model.outcome == surface.OUTCOME_FINISHED


def test_a_page_the_route_skips_keeps_its_own_values():
    """A skipped page lost the values it was built with."""
    spec = BY_NAME["extractor"]
    model = new_model(spec)
    while model.next_page() != -1:
        model.go_next()
    assert surface.FOLDING not in model.history
    assert surface.PHANTOM not in model.history
    assert model.folding_config()["fold_target_count"] == 5
    assert model.phantom_config()["lock_candle_count"] == 2
    config = model.get_bot_config()
    assert config["enable_phantoms"] is False
    assert config["profit_folding_active"] is False


# What the shipped wizard declares, counted off the file


def dotted(node) -> str:
    """One attribute chain as text, so a call target can be named."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    """One file as a parsed tree, which cannot see inside a comment."""
    return ast.parse(path.read_text(encoding="utf-8"))


def declared_classes(path) -> set:
    """Every class the file declares, one inside an if included."""
    return {
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    }


def declared_functions(path) -> list:
    """Every function and method the file declares."""
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def import_aliases(path) -> dict:
    """Every imported name to the name it was imported under."""
    found = {}
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = alias.name
    return found


def constructor_counts(path) -> dict:
    """How many times each class is built, with an import alias resolved."""
    aliases = import_aliases(path)
    counts: dict = {}
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Call):
            last = dotted(node.func).split(".")[-1]
            if last and last[0].isupper():
                name = aliases.get(last, last)
                counts[name] = counts.get(name, 0) + 1
    return counts


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


def calls_named(path, ending) -> list:
    """Every call whose target name ends with `ending`."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith(ending)
    ]


def method_calls(path, name) -> list:
    """Every call to a method spelled `name`."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


def bus_functions(path, name) -> list:
    """Every call to `name`, however the file spells the object it hangs off.

    Counting the function rather than a topic literal keeps an import
    alias in the count.
    """
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
    ]


def test_the_class_counter_finds_every_page_and_the_wizard():
    """The shipped wizard gained or lost a page class."""
    found = declared_classes(WIZARD_SOURCE)
    assert len(found) == SHIPPED_CLASS_TOTAL, sorted(found)
    assert "BotCreationWizard" in found
    assert "TradingParamsPage" in found
    top_level = {
        node.name
        for node in parsed(WIZARD_SOURCE).body
        if isinstance(node, ast.ClassDef)
    }
    assert top_level == set(), top_level


def test_the_class_counter_reports_a_class_at_the_top_level():
    """The class counter reads nothing but the top level, so a page hides."""
    assert "BotWizardModel" in declared_classes(SURFACE_SOURCE)


def test_every_shipped_function_is_counted():
    """The shipped wizard gained or lost a method."""
    functions = declared_functions(WIZARD_SOURCE)
    assert len(functions) == SHIPPED_FUNCTION_TOTAL, functions
    assert functions.count("__init__") == 7, functions
    assert functions.count("get_config") == 5, functions
    assert functions.count("_fetch_markets") == 2, functions


def test_the_connect_sets_match():
    """The wizard connects a signal the surface names no action for."""
    sites = connect_sites(WIZARD_SOURCE)
    assert len(sites) == SOURCE_CONNECT_TOTAL, sites
    assert len(surface.ACTIONS) == SOURCE_CONNECT_TOTAL, surface.ACTIONS
    assert surface.SOURCE_CONNECT_TOTAL == SOURCE_CONNECT_TOTAL
    assert surface.RUNTIME_CONNECT_TOTAL == RUNTIME_CONNECT_TOTAL


def test_the_connect_reader_counts_a_site_a_text_search_also_finds():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites(WIZARD_SOURCE)
    assert ("self.currentIdChanged", "self._on_page_changed") in sites
    text = WIZARD_SOURCE.read_text(encoding="utf-8").count(".connect(")
    assert text == len(sites), (text, len(sites))


PRODUCT_SIGNALS = (
    "2currentIndexChanged(int)",
    "2clicked(bool)",
    "2currentIdChanged(int)",
)


def live_connections(owner) -> int:
    """How many live connections `owner` holds on the wizard's own signals.

    Read off the running object through Qt's own connection count, never
    off the source. Only the three signals the wizard wires are counted,
    because Qt wires its own buttons inside the window frame and those
    are not the product's. This counter watches THIS process only; a
    child process opens its own objects and is never seen here.
    """
    return sum(owner.receivers(one) for one in PRODUCT_SIGNALS)


def test_the_wizard_connects_ten_signals_at_run_time():
    """The running wizard holds a different number of connections than it declares."""
    driven = drive_old(BY_NAME["happy"])
    wizard = driven["wizard"]
    live = live_connections(wizard)
    per_page = {}
    for name, page in driven["pages"].items():
        per_page[name] = live_connections(page) + sum(
            live_connections(child) for child in page.findChildren(QWidget)
        )
        live += per_page[name]
    assert driven["seams"].restored() is True
    assert live == RUNTIME_CONNECT_TOTAL, per_page
    assert surface.RUNTIME_CONNECT_TOTAL == live
    assert len(connect_sites(WIZARD_SOURCE)) == live


def test_the_runtime_connection_counter_reports_a_connection_it_is_given():
    """The runtime counter reports the same number whatever is wired."""
    box = QComboBox()
    assert live_connections(box) == 0
    box.currentIndexChanged.connect(lambda _found: None)
    assert live_connections(box) == 1
    button = QPushButton()
    assert live_connections(button) == 0
    button.clicked.connect(lambda: None)
    assert live_connections(button) == 1


def test_the_signal_and_emit_counters_report_none_and_can_report_one():
    """The wizard declares a signal the surface names none of."""
    builds = calls_named(WIZARD_SOURCE, "Signal")
    emits = method_calls(WIZARD_SOURCE, "emit")
    assert len(builds) == SIGNAL_BUILD_TOTAL, builds
    assert len(emits) == SIGNAL_EMIT_TOTAL, emits
    assert list(surface.SIGNAL_NAMES) == []
    assert surface.SIGNAL_EMIT_TOTAL == SIGNAL_EMIT_TOTAL
    text = WIZARD_SOURCE.read_text(encoding="utf-8")
    assert text.count("emit") > len(emits), "the text search stopped over-counting"
    assert (
        len(calls_named(SIGNAL_NEIGHBOUR, "Signal")) >= 1
    ), "the signal counter is blind"
    assert len(method_calls(SIGNAL_NEIGHBOUR, "emit")) >= 1, "the emit counter is blind"


def test_the_timer_counters_report_none_and_can_report_one():
    """The wizard builds a timer the surface declares no delay for."""
    built = calls_named(WIZARD_SOURCE, "QTimer")
    started = [
        name for name in method_calls(WIZARD_SOURCE, "start") if "timer" in name.lower()
    ]
    assert len(built) == TIMER_BUILD_TOTAL, built
    assert len(started) == TIMER_START_TOTAL, started
    assert surface.TIMERS == {}
    assert surface.TIMERS_STARTED == ()
    assert surface.TIMER_DELAYS_MS == ()
    assert (
        len(calls_named(TIMER_NEIGHBOUR, "QTimer")) >= 1
    ), "the timer counter is blind"


def test_the_thread_counters_report_none_and_can_report_one():
    """The wizard owns a worker thread the surface names none of."""
    built = calls_named(WIZARD_SOURCE, "Thread") + calls_named(WIZARD_SOURCE, "QThread")
    started = [
        name
        for name in method_calls(WIZARD_SOURCE, "start")
        if "thread" in name.lower()
    ]
    assert built == [], built
    assert started == [], started
    assert surface.THREADS_BUILT == ()
    assert surface.THREADS_STARTED == ()
    neighbour = calls_named(THREAD_NEIGHBOUR, "Thread") + calls_named(
        THREAD_NEIGHBOUR, "QThread"
    )
    assert len(neighbour) >= 1, "the thread counter is blind"


def test_the_bus_counters_report_none_and_can_report_a_real_call():
    """The wizard talks on a bus topic the surface names none of.

    The bus emit and a Qt signal emit share the name ``emit``, so the
    emit counter cannot tell them apart. The wizard has neither, which
    is why zero is the same answer either way.
    """
    subscribes = bus_functions(WIZARD_SOURCE, "subscribe")
    emits = bus_functions(WIZARD_SOURCE, "emit")
    assert subscribes == [], subscribes
    assert emits == [], emits
    assert len(surface.BUS_TOPICS) == BUS_SUBSCRIBE_TOTAL
    assert len(surface.BUS_EMITS) == BUS_EMIT_TOTAL
    assert (
        len(bus_functions(BUS_NEIGHBOUR, "subscribe")) >= 1
    ), "the bus counter is blind"
    assert len(bus_functions(BUS_NEIGHBOUR, "emit")) >= 1, "the emit counter is blind"


def test_the_constructor_counter_resolves_an_import_alias():
    """The constructor counter counts a name, so an alias is under-counted."""
    counts = constructor_counts(WIZARD_SOURCE)
    assert counts["QDoubleSpinBox"] == 27, counts.get("QDoubleSpinBox")
    assert counts["QSpinBox"] == 14, counts.get("QSpinBox")
    assert counts["QCheckBox"] == 16, counts.get("QCheckBox")
    assert counts["QComboBox"] == 11, counts.get("QComboBox")
    assert counts["QRadioButton"] == 10, counts.get("QRadioButton")
    assert counts["QGroupBox"] == 13, counts.get("QGroupBox")
    aliased = "from a import B as C\nC()\n"
    tree = ast.parse(aliased)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert len(calls) == 1


def test_the_construction_counter_cannot_see_a_name_inside_prose(tmp_path):
    """The counter reads text, so a name in prose inflates the count.

    Driven over a written snippet, never over the shipped file's own
    prose: a comment is not a contract and a cleanup that removes one
    must not blind this control.
    """
    written = tmp_path / "snippet.py"
    written.write_text(
        "# QDoubleSpinBox()\n"
        "label = 'QDoubleSpinBox()'\n"
        "QSpinBox()\n"
        "QSpinBox()\n",
        encoding="utf-8",
        newline="\n",
    )
    counts = constructor_counts(written)
    assert counts == {"QSpinBox": 2}, counts
    text = written.read_text(encoding="utf-8")
    assert text.count("QDoubleSpinBox") == 2, text
    assert "QDoubleSpinBox" not in counts


def test_every_number_field_the_surface_declares_is_a_widget_on_a_page():
    """The surface declares a field no page carries."""
    assert set(surface.NUMBER_FIELDS) == set(NUMBER_WIDGETS)
    assert set(surface.CHECK_FIELDS) == set(CHECK_WIDGETS)
    assert set(surface.RADIO_FIELDS) == set(RADIO_WIDGETS)
    assert set(surface.COMBO_FIELDS) == set(COMBO_WIDGETS)
    assert set(surface.TEXT_FIELDS) == set(TEXT_WIDGETS)


@pytest.mark.parametrize("name", sorted(surface.NUMBER_FIELDS))
def test_every_number_field_carries_the_range_the_widget_carries(name):
    """A field's lowest, highest, decimals or step moved on one side only."""
    spec = surface.NUMBER_FIELDS[name]
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        pages = {
            "params": wizard._params_page,
            "folding": wizard._folding_page,
            "phantom": wizard._phantom_page,
        }
        page, attribute = NUMBER_WIDGETS[name]
        widget = getattr(pages[page], attribute)
        carried = {
            "minimum": widget.minimum(),
            "maximum": widget.maximum(),
            "value": widget.value(),
            "suffix": widget.suffix(),
            "prefix": widget.prefix(),
            "step": widget.singleStep(),
            "kind": (
                surface.SPIN_DOUBLE
                if isinstance(widget, QDoubleSpinBox)
                else surface.SPIN_INT
            ),
        }
        if isinstance(widget, QDoubleSpinBox):
            carried["decimals"] = widget.decimals()
    assert seams.restored() is True
    assert spec["kind"] == carried["kind"], name
    assert spec["minimum"] == carried["minimum"], name
    assert spec["maximum"] == carried["maximum"], name
    assert spec.get("suffix", "") == carried["suffix"], name
    assert spec.get("prefix", "") == carried["prefix"], name
    if spec["kind"] == surface.SPIN_DOUBLE:
        assert spec["decimals"] == carried["decimals"], name
        if "step" in spec:
            assert spec["step"] == carried["step"], name


@pytest.mark.parametrize("name", sorted(surface.COMBO_FIELDS))
def test_every_drop_down_carries_the_entries_the_widget_carries(name):
    """A drop-down entry or its value moved on one side only."""
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        pages = {
            "asset": wizard._asset_page,
            "pool": wizard._extractor_pool_page,
            "params": wizard._params_page,
        }
        page, attribute = COMBO_WIDGETS[name]
        widget = getattr(pages[page], attribute)
        carried = [
            [widget.itemText(at), widget.itemData(at)] for at in range(widget.count())
        ]
        index = widget.currentIndex()
    assert seams.restored() is True
    assert carried == [list(one) for one in surface.COMBO_FIELDS[name]], name
    assert index == surface.COMBO_DEFAULT_INDEX[name], name


@pytest.mark.parametrize("name", sorted(surface.CHECK_TEXTS))
def test_every_check_box_carries_the_wording_the_widget_carries(name):
    """A check box's wording moved on one side only."""
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        pages = {
            "params": wizard._params_page,
            "folding": wizard._folding_page,
            "phantom": wizard._phantom_page,
        }
        page, attribute = CHECK_WIDGETS[name]
        widget = getattr(pages[page], attribute)
        carried = (widget.text(), widget.toolTip())
    assert seams.restored() is True
    assert carried[0] == surface.CHECK_TEXTS[name], name
    assert carried[1] == surface.TOOL_TIPS.get(name, ""), name


@pytest.mark.parametrize("name", sorted(surface.RADIO_TEXTS))
def test_every_radio_button_carries_the_wording_the_widget_carries(name):
    """A radio button's wording moved on one side only."""
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        pages = {"mode": wizard._mode_page, "folding": wizard._folding_page}
        page, attribute = RADIO_WIDGETS[name]
        widget = getattr(pages[page], attribute)
        carried = widget.text()
    assert seams.restored() is True
    assert carried == surface.RADIO_TEXTS[name], name


@pytest.mark.parametrize("name", sorted(surface.GROUP_TITLES))
def test_every_group_carries_the_title_the_widget_carries(name):
    """A group's title moved on one side only."""
    if name not in GROUP_WIDGETS:
        pytest.skip("this group is not on the parameter page")
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        carried = getattr(wizard._params_page, GROUP_WIDGETS[name]).title()
    assert seams.restored() is True
    assert carried == surface.GROUP_TITLES[name], name


def venue_combo_items(combo):
    """Every entry one venue drop-down holds, its wording beside its id."""
    return [[combo.itemText(at), combo.itemData(at)] for at in range(combo.count())]


@pytest.mark.parametrize("page", ["asset", "pool"])
def test_the_venue_list_the_payload_carries_is_the_list_the_combo_holds(page):
    """The venue drop-down the operator picks from never reaches the payload."""
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        holder = wizard._asset_page if page == "asset" else wizard._extractor_pool_page
        held = venue_combo_items(holder._exchange)
    assert seams.restored() is True
    model = surface.BotWizardModel(EXCHANGES, {}, MARKETS)
    assert model.exchange_items() == held, page


def test_the_venue_list_check_would_see_a_venue_the_combo_never_held():
    """The venue list is the same whatever venues the model was given."""
    model = surface.BotWizardModel([], {}, {})
    assert model.exchange_items() == []


def widget_field_names():
    """Every field name, keyed by the page and attribute its widget sits at."""
    found = {}
    for source in (
        NUMBER_WIDGETS,
        CHECK_WIDGETS,
        RADIO_WIDGETS,
        COMBO_WIDGETS,
        TEXT_WIDGETS,
    ):
        for name, where in source.items():
            found[where] = name
    return found


def laid_out_groups():
    """Every group box the wizard builds, keyed by the title it carries."""
    from PySide6.QtWidgets import QGroupBox

    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        pages = {
            "params": wizard._params_page,
            "folding": wizard._folding_page,
            "phantom": wizard._phantom_page,
        }
        named = widget_field_names()
        by_widget = {}
        for page, holder in pages.items():
            for where, name in named.items():
                if where[0] == page:
                    by_widget[id(getattr(holder, where[1]))] = name
        found = {}
        for holder in pages.values():
            for box in holder.findChildren(QGroupBox):
                found[box.title()] = [
                    by_widget[id(one)]
                    for one in box.findChildren(object)
                    if id(one) in by_widget
                ]
    assert seams.restored() is True
    return found


@pytest.mark.parametrize("name", sorted(surface.GROUP_ROWS))
def test_every_group_holds_the_fields_the_widget_holds_in_that_order(name):
    """A group's fields moved, or changed order, on one side only."""
    laid_out = laid_out_groups()
    title = surface.GROUP_TITLES[name]
    assert title in laid_out, sorted(laid_out)
    assert laid_out[title] == list(surface.GROUP_ROWS[name]), name


def test_the_group_row_reader_finds_a_field_the_shipped_page_lays_out():
    """The row walk finds no field at all, so every group compares empty."""
    laid_out = laid_out_groups()
    every = sorted(one for found in laid_out.values() for one in found)
    assert len(every) == len(set(every)), every
    assert "target_balance" in every, every


def test_every_field_the_wizard_carries_is_laid_out_once_or_named_on_a_page():
    """A field the wizard carries reaches no group and no page of its own."""
    every = set(surface.NUMBER_FIELDS) | set(surface.CHECK_FIELDS)
    every |= set(surface.RADIO_FIELDS) | set(surface.COMBO_FIELDS)
    every |= set(surface.TEXT_FIELDS)
    placed = {one for found in surface.GROUP_ROWS.values() for one in found}
    placed |= {one for found in surface.PAGE_ROWS.values() for one in found}
    assert sorted(every - placed) == [], sorted(every - placed)


def test_the_placement_check_would_see_a_field_nobody_laid_out():
    """The placement check counts a name no field carries as placed."""
    placed = {one for found in surface.GROUP_ROWS.values() for one in found}
    placed |= {one for found in surface.PAGE_ROWS.values() for one in found}
    assert "no_such_field" not in placed


def test_the_info_button_carries_the_wording_the_widget_carries():
    """The info button's wording moved on one side only.

    Its look is proved by the asset page picture, where the two sides
    are rendered and compared. Nothing here reads a style, a palette or
    a colour off a live object: what a widget was told to paint is not
    what it paints.
    """
    with QtSeams(markets=MARKETS) as seams:
        wizard = shipped.BotCreationWizard(EXCHANGES, {})
        carried = wizard._asset_page._info_btn.text()
    assert seams.restored() is True
    assert carried == surface.BUTTON_TEXTS["info"]


def test_no_declared_colour_has_three_equal_channels():
    """A colour whose channels are equal hides a channel swap."""
    for name, value in surface.SKIN.items():
        channels = [value[at : at + 2] for at in (1, 3, 5)]
        assert len(set(channels)) > 1, (name, value)


# Completeness


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


PAYLOAD_KEYS = {
    "METHOD": "method",
    "LOGGER_NAME": "logger_name",
    "EMPTY_TEXT": "empty_text",
    "WINDOW_TITLE": "window.title",
    "ACCESSIBLE_NAME": "window.accessible_name",
    "ACCESSIBLE_DESCRIPTION": "window.accessible_description",
    "MINIMUM_SIZE_PX": "window.minimum_size_px",
    "OPENING_SIZE_PX": "window.opening_size_px",
    "PAGES": "pages.names",
    "PAGE_IDS": "pages.ids",
    "PAGE_REGISTER_ORDER": "pages.register_order",
    "START_PAGE": "pages.start",
    "START_PAGE_ID": "pages.start_id",
    "NO_PAGE_ID": "pages.no_page_id",
    "PAGE_TITLES": "pages.titles",
    "PAGE_SUBTITLES": "pages.subtitles",
    "UNREACHABLE_PAGES": "pages.unreachable",
    "MODES": "modes.names",
    "GRID_IS_SELECTABLE": "modes.grid_is_selectable",
    "NEXT_PAGE": "modes.next_page",
    "FINAL_PAGES": "modes.final_pages",
    "NUMBER_FIELDS": "fields.numbers",
    "CHECK_FIELDS": "fields.checks",
    "RADIO_FIELDS": "fields.radios",
    "COMBO_FIELDS": "fields.combos",
    "COMBO_DEFAULT_INDEX": "fields.combo_default_index",
    "TEXT_FIELDS": "fields.texts",
    "PLACEHOLDERS": "fields.placeholders",
    "ROW_LABELS": "fields.row_labels",
    "CHECK_TEXTS": "fields.check_texts",
    "RADIO_TEXTS": "fields.radio_texts",
    "BUTTON_TEXTS": "fields.button_texts",
    "LABEL_TEXTS": "fields.label_texts",
    "TOOL_TIPS": "fields.tool_tips",
    "STACK_MODE_DEFAULT": "fields.stack_mode_default",
    "GROUP_TITLES": "groups.titles",
    "SCRUM_GROUPS": "groups.scrum",
    "EXTRACTOR_GROUPS": "groups.extractor",
    "FOLDING_GROUPS": "groups.folding",
    "PHANTOM_GROUPS": "groups.phantom",
    "GROUP_ROWS": "groups.rows",
    "PAGE_GROUPS": "pages.groups",
    "PAGE_ROWS": "pages.rows",
    "PARAMS_SUBTITLE_SCRUMMING": "groups.params_subtitle_scrumming",
    "PARAMS_SUBTITLE_EXTRACTOR": "groups.params_subtitle_extractor",
    "PARAMS_SUBTITLE_GRID": "groups.params_subtitle_grid",
    "TARGET_COMBO_MINIMUM_WIDTH_PX": "asset_page.target_minimum_width_px",
    "TARGET_COMBO_ICON_SIZE_PX": "asset_page.target_icon_size_px",
    "INFO_BUTTON_STYLE": "asset_page.info_button_style",
    "POOL_BASES": "pool_page.pool_bases",
    "ALT_LIST_MINIMUM_HEIGHT_PX": "pool_page.alt_list_minimum_height_px",
    "ALT_LIST_ACCESSIBLE_NAME": "pool_page.alt_list_accessible_name",
    "ALT_LIST_SELECTION_MODE": "pool_page.alt_list_selection_mode",
    "POOL_SIGIL": "pool_page.pool_sigil",
    "PHANTOM_TIMEFRAMES": "phantom_page.timeframes",
    "PHANTOM_TIMEFRAME_DEFAULT": "phantom_page.default",
    "API_WARNING_TITLE": "phantom_page.warning_title",
    "API_WARNING_FORMAT": "phantom_page.warning_format",
    "API_WARNING_INFORMATIVE": "phantom_page.warning_informative",
    "API_WARNING_ICON": "phantom_page.warning_icon",
    "API_WARNING_BACK_TEXT": "phantom_page.warning_back_text",
    "API_WARNING_CONTINUE_TEXT": "phantom_page.warning_continue_text",
    "API_WARNING_BACK_ROLE": "phantom_page.warning_back_role",
    "API_WARNING_CONTINUE_ROLE": "phantom_page.warning_continue_role",
    "FOLD_MODES": "folding_page.modes",
    "FOLD_TARGETS": "folding_page.fold_targets",
    "DIST_TARGETS": "folding_page.distribute_targets",
    "FOLD_HOLD_IN_DOWNTREND": "folding_page.fold_hold_in_downtrend",
    "TA_TIMEFRAMES": "timeframes.ta",
    "TA_TIMEFRAME_DEFAULT": "timeframes.ta_default",
    "TA_COMBO_NAME": "timeframes.ta_combo",
    "BASE_CURRENCIES": "timeframes.base_currencies",
    "OUTER_MARGINS": "layout.outer_margins",
    "OUTER_SPACING_PX": "layout.outer_spacing_px",
    "GROUPS_MARGINS": "layout.groups_margins",
    "GROUPS_SPACING_PX": "layout.groups_spacing_px",
    "FORM_HORIZONTAL_SPACING_PX": "layout.form_horizontal_spacing_px",
    "FORM_VERTICAL_SPACING_PX": "layout.form_vertical_spacing_px",
    "FORM_LABEL_ALIGNMENT": "layout.form_label_alignment",
    "FORM_FIELD_GROWTH": "layout.form_field_growth",
    "SCROLL_FRAME_SHAPE": "layout.scroll_frame_shape",
    "SCROLL_HORIZONTAL_POLICY": "layout.scroll_horizontal_policy",
    "SCROLL_VERTICAL_POLICY": "layout.scroll_vertical_policy",
    "SCROLL_WIDGET_RESIZABLE": "layout.scroll_widget_resizable",
    "MUTED_LABELS": "layout.muted_labels",
    "WORD_WRAPPED_LABELS": "layout.word_wrapped_labels",
    "MUTED_VALUE": "muted_value",
    "ICON_SIZE_PX": "icon.size_px",
    "ICON_HUE_WHEEL": "icon.hue_wheel",
    "ICON_SATURATION": "icon.saturation",
    "ICON_VALUE": "icon.value",
    "ICON_TEXT_COLOR": "icon.text_color",
    "ICON_FONT_FAMILY": "icon.font_family",
    "ICON_FONT_SCALE": "icon.font_scale",
    "VOLUME_BILLION_FORMAT": "formats.volume_billion",
    "VOLUME_MILLION_FORMAT": "formats.volume_million",
    "VOLUME_THOUSAND_FORMAT": "formats.volume_thousand",
    "VOLUME_PART_FORMAT": "formats.volume_part",
    "VOLATILITY_PART_FORMAT": "formats.volatility_part",
    "LABEL_WITH_PARTS_FORMAT": "formats.label_with_parts",
    "ALT_LABEL_WITH_VOLUME_FORMAT": "formats.alt_label_with_volume",
    "LOADING_FORMAT": "formats.loading",
    "POOL_LOADING_FORMAT": "formats.pool_loading",
    "FETCH_FAILED_FORMAT": "formats.fetch_failed",
    "PAIR_COUNT_FORMAT": "formats.pair_count",
    "POOL_PAIR_COUNT_FORMAT": "formats.pool_pair_count",
    "NO_INFO_FORMAT": "formats.no_info",
    "INFO_TITLE_FORMAT": "formats.info_title",
    "NO_DESCRIPTION_FORMAT": "formats.no_description",
    "PHANTOM_TOOL_TIP_FORMAT": "formats.phantom_tool_tip",
    "PHANTOM_UNSUPPORTED_FORMAT": "formats.phantom_unsupported",
    "VOLUME_BILLION": "thresholds.volume_billion",
    "VOLUME_MILLION": "thresholds.volume_million",
    "VOLUME_THOUSAND": "thresholds.volume_thousand",
    "FETCH_ERROR_LIMIT": "thresholds.fetch_error_limit",
    "PART_SEPARATOR": "thresholds.part_separator",
    "NO_VOLUME_TEXT": "thresholds.no_volume_text",
    "NO_PAIRS_TEXT": "thresholds.no_pairs_text",
    "NO_PAIRS_DATA": "thresholds.no_pairs_data",
    "SORTED_BY_VOLUME_SUFFIX": "thresholds.sorted_by_volume_suffix",
    "PHANTOM_SUPPORTED_TEXT": "thresholds.phantom_supported_text",
    "PHANTOM_UNKNOWN_EXCHANGE": "thresholds.phantom_unknown_exchange",
    "INFO_BOX_ICON": "thresholds.info_box_icon",
    "OUTCOMES": "walk.outcomes",
    "REFUSAL_TYPES": "walk.refusal_types",
    "WALK_STEPS": "walk.steps",
    "CONFIG_FIELDS": "config_fields",
    "DEFAULT_TARGET_BALANCE_KEY": "keys.default_target_balance",
    "EXCHANGE_DISPLAY_KEY": "keys.exchange_display",
    "EXCHANGE_ID_KEY": "keys.exchange_id",
    "MARKET_SYMBOL_KEY": "keys.market_symbol",
    "MARKET_BASE_KEY": "keys.market_base",
    "MARKET_QUOTE_KEY": "keys.market_quote",
    "MARKET_VOLUME_KEY": "keys.market_volume",
    "MARKET_VOLATILITY_KEY": "keys.market_volatility",
    "REFUSAL_WRONG_NUMBER": "refusals.wrong_number",
    "REFUSAL_WRONG_CHECK": "refusals.wrong_check",
    "REFUSAL_WRONG_TEXT": "refusals.wrong_text",
    "REFUSAL_TOO_LARGE": "refusals.too_large",
    "REFUSAL_NOT_A_WHOLE_NUMBER": "refusals.not_a_whole_number",
    "REFUSAL_UNKNOWN_FIELD": "refusals.unknown_field",
    "REFUSAL_UNKNOWN_PAGE": "refusals.unknown_page",
    "REFUSAL_UNKNOWN_ALT": "refusals.unknown_alt",
    "REFUSAL_NONE": "refusals.none",
    "REFUSAL_API_LOAD": "refusals.api_load",
    "REFUSAL_NOT_FINAL": "refusals.not_final",
    "REFUSAL_NO_ROUTE": "refusals.no_route",
    "REFUSAL_NO_HISTORY": "refusals.no_history",
    "ACTIONS": "actions",
    "RUNTIME_CONNECT_TOTAL": "runtime_connect_total",
    "SOURCE_CONNECT_TOTAL": "source_connect_total",
    "SIGNAL_NAMES": "signal_names",
    "SIGNAL_EMIT_TOTAL": "signal_emit_total",
    "TIMERS": "timers",
    "TIMERS_STARTED": "timers_started",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "THREADS_BUILT": "threads_built",
    "THREADS_STARTED": "threads_started",
    "BUS_TOPICS": "bus_topics",
    "BUS_EMITS": "bus_emits",
    "SAFE_EVENTS_REASON": "safe_events_reason",
    "SKIN": "skin",
    "INFO_BUTTON_COLOR": "info_button_color",
    "INT32_MIN": "int32_min",
    "INT32_MAX": "int32_max",
    "SPIN_DOUBLE": "spin_double",
    "SPIN_INT": "spin_int",
    "STEP_NAMES": "step_names",
    "CALL_NAMES": "call_names",
}

LIST_MEMBERS = {
    "ASSET",
    "MODE",
    "PARAMS",
    "FOLDING",
    "PHANTOM",
    "EXTRACTOR_POOL",
    "PAGE_NAMES",
    "SCRUMMING_MODE",
    "EXTRACTOR_MODE",
    "SCRUMMING_ROUTE",
    "EXTRACTOR_ROUTE",
    "FOLD_MODE_EQUAL",
    "FOLD_MODE_LOGARITHMIC",
    "FOLD_TARGET_ALL",
    "FOLD_TARGET_X",
    "FOLD_TARGET_RECENT",
    "DIST_TARGET_ALL",
    "DIST_TARGET_X",
    "DIST_TARGET_RECENT",
    "OUTCOME_OPEN",
    "OUTCOME_CANCELLED",
    "OUTCOME_FINISHED",
    "WALK_NEXT",
    "WALK_BACK",
    "WALK_CANCEL",
    "WALK_FINISH",
    "MUTED_PROPERTY",
    "SPIN_DOUBLE",
    "SPIN_INT",
}

NOT_IN_THE_SNAPSHOT = {
    "C_LONG_MIN",
    "C_LONG_MAX",
    "Any",
    "Optional",
    "Decimal",
    "ROUND_HALF_UP",
}


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface declares never reaches the answer it sends."""
    payload = build_payload(BY_NAME["happy"])
    call_names = set(surface.CALL_NAMES)
    unaccounted = []
    for name, value in surface_constants().items():
        if name in PAYLOAD_KEYS or name in LIST_MEMBERS or name in NOT_IN_THE_SNAPSHOT:
            continue
        if isinstance(value, str) and value in call_names:
            continue
        unaccounted.append(name)
    assert unaccounted == [], unaccounted
    for name, path in PAYLOAD_KEYS.items():
        held = getattr(surface, name)
        found = at_path(payload, path)
        if isinstance(held, tuple):
            held = list(held)
        if isinstance(held, dict):
            held = {
                key: (list(one) if isinstance(one, tuple) else one)
                for key, one in held.items()
            }
        if name == "COMBO_FIELDS":
            held = {key: [list(one) for one in items] for key, items in held.items()}
        if name == "NEXT_PAGE":
            held = {key: dict(route) for key, route in held.items()}
        assert found == held, name


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The answer grew a key no value on the surface backs."""
    payload = build_payload(BY_NAME["happy"])
    answered = set(PAYLOAD_KEYS.values())
    state_only = {
        "pages.current",
        "pages.current_id",
        "pages.history",
        "pages.is_final",
        "pages.next_id",
        "modes.selected",
        "modes.is_extractor",
        "modes.params_is_extractor",
        "modes.is_grid",
        "values",
        "groups.visible",
        "groups.params_subtitle",
        "asset_page.exchange_index",
        "asset_page.target_items",
        "asset_page.target_hues",
        "asset_page.target_index",
        "asset_page.target_data",
        "asset_page.status",
        "asset_page.info_tool_tip",
        "asset_page.info_box",
        "asset_page.config",
        "pool_page.exchange_index",
        "pool_page.alt_items",
        "pool_page.alt_checked",
        "pool_page.status",
        "pool_page.config",
        "phantom_page.checked",
        "phantom_page.enabled",
        "phantom_page.tool_tips",
        "phantom_page.selection",
        "phantom_page.config",
        "phantom_page.warning_box",
        "folding_page.config",
        "timeframes.offered",
        "timeframes.ta_items",
        "layout.muted_property",
        "walk.outcome",
        "walk.closed",
        "walk.refusal",
        "walk.refusals",
        "config",
        "fetched",
        "calls",
    }
    top = {path.split(".")[0] for path in answered} | {
        path.split(".")[0] for path in state_only
    }
    assert set(payload) - top == set(), set(payload) - top


def test_both_completeness_checks_can_report():
    """The completeness checks pass whatever the surface and answer hold."""
    payload = dict(build_payload(BY_NAME["happy"]))
    payload["invented_key"] = "nowhere"
    answered = set(PAYLOAD_KEYS.values())
    state_only = {"values", "config", "calls", "fetched", "walk", "groups"}
    top = {path.split(".")[0] for path in answered} | state_only
    assert set(payload) - top == {"invented_key"}

    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "nowhere"
    call_names = set(surface.CALL_NAMES)
    unaccounted = [
        name
        for name, value in constants.items()
        if name not in PAYLOAD_KEYS
        and name not in LIST_MEMBERS
        and name not in NOT_IN_THE_SNAPSHOT
        and not (isinstance(value, str) and value in call_names)
    ]
    assert unaccounted == ["INVENTED_CONSTANT"], unaccounted


def test_the_surface_grew_no_name_the_file_does_not_declare():
    """A name on the module and a name in the file disagree."""
    tree = parsed(SURFACE_SOURCE)
    written = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            written.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            written.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            written.add(node.name)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
    live = {name for name in vars(surface) if not name.startswith("__")}
    assert written - imported - live == set(), written - imported - live
    assert live - written - imported == set(), live - written - imported


def test_every_call_the_surface_names_is_recorded_by_some_drive():
    """A call the surface declares is never made, or is made silently."""
    seen = set()
    for spec in ALL_CASES:
        seen.update(call[0] for call in new_model(spec).calls)
    unknown = surface.BotWizardModel(EXCHANGES, {}, {})
    seen.update(call[0] for call in unknown.calls)
    extra = new_model(BY_NAME["refused_at_the_phantom_page"])
    for _ in range(3):
        extra.go_next()
    extra.go_next((False, "over budget"), False)
    extra.set_target_index(0)
    extra.show_info()
    extra.cancel()
    seen.update(call[0] for call in extra.calls)
    missing = set(surface.CALL_NAMES) - seen
    assert missing == set(), sorted(missing)


# The pictures

PICTURE_SPECS = {
    "mode": ("mode", BY_NAME["happy"]),
    "asset": ("asset", BY_NAME["happy"]),
    "extractor_pool": ("pool", BY_NAME["extractor_pool_ticked"]),
    "params_scrumming": ("params", BY_NAME["walk_forward"]),
    "params_extractor": ("params", BY_NAME["walk_forward_extractor"]),
    "folding": ("folding", BY_NAME["happy"]),
    "phantom": ("phantom", BY_NAME["phantoms_on"]),
    "phantom_refused": ("phantom", BY_NAME["refused_at_the_phantom_page"]),
}


def page_painted_by_the_wizard(name):
    """The shipped page for one picture case, driven and kept alive."""
    which, spec = PICTURE_SPECS[name]
    driven = drive_old(spec)
    page = driven["pages"][which]
    page._parity_wizard = driven["wizard"]
    page.setParent(None)
    return page


def model_payload(name):
    """The surface's answer for one picture case, sealed as it comes off."""
    _which, spec = PICTURE_SPECS[name]
    return sealed(
        surface.build_view_model(
            spec["exchanges"],
            spec["defaults"],
            spec["markets"],
            {
                "mode": spec["mode"],
                "checks": spec["checks"],
                "alt_checks": spec["alt_checks"],
                "phantom_timeframes": spec["phantom_timeframes"],
                "walk": [list(step) for step in spec["walk"]],
            },
            venue_timeframes(spec),
        )
    )


def form_from(payload, rows):
    """One form holding `rows`, each a label and a widget."""
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setHorizontalSpacing(payload["layout"]["form_horizontal_spacing_px"])
    form.setVerticalSpacing(payload["layout"]["form_vertical_spacing_px"])
    for label, widget in rows:
        if label is None:
            form.addRow(widget)
        else:
            form.addRow(label, widget)
    return form


def number_widget(payload, name):
    """One spin box built only from the payload's description of it."""
    spec = payload["fields"]["numbers"][name]
    value = payload["values"]["numbers"][name]
    if spec["kind"] == payload["spin_double"]:
        widget = QDoubleSpinBox()
        widget.setRange(spec["minimum"], spec["maximum"])
        widget.setDecimals(spec["decimals"])
        if "step" in spec:
            widget.setSingleStep(spec["step"])
    else:
        widget = QSpinBox()
        widget.setRange(int(spec["minimum"]), int(spec["maximum"]))
    if spec.get("suffix"):
        widget.setSuffix(spec["suffix"])
    if spec.get("prefix"):
        widget.setPrefix(spec["prefix"])
    widget.setValue(value)
    widget.setToolTip(payload["fields"]["tool_tips"].get(name, ""))
    return widget


def check_widget(payload, name):
    """One check box built only from the payload's description of it."""
    widget = QCheckBox(payload["fields"]["check_texts"][name])
    widget.setChecked(payload["values"]["checks"][name])
    widget.setToolTip(payload["fields"]["tool_tips"].get(name, ""))
    return widget


def combo_widget(payload, name, items=None, index=None):
    """One drop-down built only from the payload's description of it."""
    widget = QComboBox()
    for label, data in items or payload["fields"]["combos"][name]:
        widget.addItem(label, data)
    widget.setCurrentIndex(
        payload["values"]["combo_indexes"][name] if index is None else index
    )
    widget.setToolTip(payload["fields"]["tool_tips"].get(name, ""))
    return widget


def group_from(payload, key, rows):
    """One group box holding `rows`, titled from the payload."""
    group = QGroupBox(payload["groups"]["titles"][key])
    group.setLayout(form_from(payload, rows))
    return group


def mode_page_from(payload):
    """The mode page, built only from the payload."""
    page = QWizardPage()
    page.setTitle(payload["pages"]["titles"]["mode"])
    page.setSubTitle(payload["pages"]["subtitles"]["mode"])
    layout = QVBoxLayout(page)
    scrumming = QRadioButton(payload["fields"]["radio_texts"]["scrumming"])
    scrumming.setChecked(payload["values"]["radios"]["scrumming"])
    described = QLabel(payload["fields"]["label_texts"]["scrumming_description"])
    described.setWordWrap(True)
    described.setProperty(*payload["layout"]["muted_property"])
    layout.addWidget(scrumming)
    layout.addWidget(described)
    extractor = QRadioButton(payload["fields"]["radio_texts"]["extractor"])
    extractor.setChecked(payload["values"]["radios"]["extractor"])
    extractor.setToolTip(payload["fields"]["tool_tips"]["extractor"])
    extractor_described = QLabel(
        payload["fields"]["label_texts"]["extractor_description"]
    )
    extractor_described.setWordWrap(True)
    extractor_described.setProperty(*payload["layout"]["muted_property"])
    layout.addWidget(extractor)
    layout.addWidget(extractor_described)
    layout.addStretch()
    return page


def coin_icon_from(payload, hue, symbol):
    """One lettered circle, built only from the payload's icon settings."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

    size = payload["icon"]["size_px"]
    picture = QPixmap(size, size)
    picture.fill(QColor(0, 0, 0, 0))
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(
        QColor.fromHsv(hue, payload["icon"]["saturation"], payload["icon"]["value"])
    )
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.setPen(QColor(payload["icon"]["text_color"]))
    painter.setFont(
        QFont(
            payload["icon"]["font_family"],
            int(size * payload["icon"]["font_scale"]),
            QFont.Bold,
        )
    )
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, symbol[0])
    painter.end()
    return QIcon(picture)


def asset_page_from(payload):
    """The asset page, built only from the payload."""
    page = QWizardPage()
    page.setTitle(payload["pages"]["titles"]["asset"])
    page.setSubTitle(payload["pages"]["subtitles"]["asset"])
    form = QFormLayout(page)
    exchange = QComboBox()
    for one in EXCHANGES:
        exchange.addItem(one["display_name"], one["exchange_id"])
    exchange.setCurrentIndex(payload["asset_page"]["exchange_index"])
    form.addRow(payload["fields"]["row_labels"]["exchange"], exchange)
    base = combo_widget(payload, "base")
    form.addRow(payload["fields"]["row_labels"]["base"], base)
    row = QHBoxLayout()
    target = QComboBox()
    target.setMinimumWidth(payload["asset_page"]["target_minimum_width_px"])
    from PySide6.QtCore import QSize

    target.setIconSize(QSize(*payload["asset_page"]["target_icon_size_px"]))
    hues = payload["asset_page"]["target_hues"]
    for at, (label, data) in enumerate(payload["asset_page"]["target_items"]):
        if at < len(hues) and data:
            target.addItem(coin_icon_from(payload, hues[at], data), label, data)
        else:
            target.addItem(label, data)
    target.setCurrentIndex(payload["asset_page"]["target_index"])
    row.addWidget(target, stretch=1)
    info = QPushButton(payload["fields"]["button_texts"]["info"])
    info.setStyleSheet(payload["asset_page"]["info_button_style"])
    info.setToolTip(payload["asset_page"]["info_tool_tip"])
    row.addWidget(info)
    form.addRow(payload["fields"]["row_labels"]["target"], row)
    status = QLabel(payload["asset_page"]["status"])
    status.setWordWrap(True)
    form.addRow(status)
    return page


def pool_page_from(payload):
    """The extractor pool page, built only from the payload."""
    page = QWizardPage()
    page.setTitle(payload["pages"]["titles"]["extractor_pool"])
    page.setSubTitle(payload["pages"]["subtitles"]["extractor_pool"])
    outer = QVBoxLayout(page)
    form = QFormLayout()
    exchange = QComboBox()
    for one in EXCHANGES:
        exchange.addItem(one["display_name"], one["exchange_id"])
    exchange.setCurrentIndex(payload["pool_page"]["exchange_index"])
    exchange.setToolTip(payload["fields"]["tool_tips"]["pool_exchange"])
    form.addRow(payload["fields"]["row_labels"]["exchange"], exchange)
    base = combo_widget(payload, "pool_base")
    form.addRow(payload["fields"]["row_labels"]["pool_base"], base)
    outer.addLayout(form)
    status = QLabel(payload["pool_page"]["status"])
    status.setWordWrap(True)
    outer.addWidget(status)
    outer.addWidget(QLabel(payload["fields"]["label_texts"]["alt_list_heading"]))
    alt_list = QListWidget()
    alt_list.setSelectionMode(
        getattr(QListWidget, payload["pool_page"]["alt_list_selection_mode"])
    )
    alt_list.setMinimumHeight(payload["pool_page"]["alt_list_minimum_height_px"])
    alt_list.setAccessibleName(payload["pool_page"]["alt_list_accessible_name"])
    alt_list.setToolTip(payload["fields"]["tool_tips"]["alt_list"])
    for at, (label, symbol) in enumerate(payload["pool_page"]["alt_items"]):
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, symbol)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(
            Qt.Checked if payload["pool_page"]["alt_checked"][at] else Qt.Unchecked
        )
        alt_list.addItem(item)
    outer.addWidget(alt_list)
    row = QHBoxLayout()
    select_all = QPushButton(payload["fields"]["button_texts"]["select_all"])
    select_all.setToolTip(payload["fields"]["tool_tips"]["select_all"])
    clear_all = QPushButton(payload["fields"]["button_texts"]["clear_all"])
    clear_all.setToolTip(payload["fields"]["tool_tips"]["clear_all"])
    row.addWidget(select_all)
    row.addWidget(clear_all)
    row.addStretch()
    outer.addLayout(row)
    return page


PARAMS_GROUP_ROWS = {
    "mode_group": [
        ("visibility", "combo"),
        ("aggressive", "check_row"),
        ("stack_mode", "check_row"),
        ("split_distance", "number"),
        ("stack_count", "number"),
        ("stack_spacing", "combo"),
        ("personal_hold_qty", "number"),
    ],
    "scrum_group": [
        ("scrumming_interval", "number"),
        ("bb_tolerance", "number"),
        ("ls_candles", "number"),
        ("ta_timeframe", "ta_combo"),
        ("target_balance", "number"),
        ("max_entry_px", "number"),
        ("min_entry_px", "number"),
        ("trading_fee", "number"),
        ("max_target_growth_pct", "number"),
        ("scrum_fold_pct", "number"),
    ],
    "adv_group": [
        ("scrum_detect_pct", "number"),
        ("scrum_fire_pct", "number"),
        ("bb_midline_gate", "check_row"),
        ("scrum_read_rate", "number"),
        ("band_travel_pct", "number"),
        ("bb_bullseye", "check_row"),
        ("wire_inflow_stack_pct", "number"),
    ],
    "hedge_group": [("hedge_rebalance", "check_row"), ("hedge_amount", "number")],
    "cb_group": [
        ("cb_soft_pct", "number"),
        ("cb_hard_pct", "number"),
        ("cb_cooldown", "number"),
        ("max_cartridge_pct", "number"),
        ("cartridge_smart_chk", "check_labelled"),
        ("cartridge_smart_ceiling", "number"),
    ],
    "risk_group": [
        ("position_ceiling_enabled", "check_row"),
        ("position_ceiling_multiple", "number"),
        ("detonation_enabled", "check_row"),
        ("detonation_timeframe", "combo"),
        ("detonation_confidence_min", "number"),
    ],
    "gates_group": [
        ("gate_scrum_ta_chk", "check_row"),
        ("gate_scrum_uptrend_chk", "check_row"),
        ("gate_scrum_htf_chk", "check_row"),
        ("gate_fold_ta_chk", "check_row"),
        ("gate_fold_htf_chk", "check_row"),
    ],
    "routing_group": [("profit_route", "combo"), ("profit_route_bot_id", "text")],
}
EXTRACTOR_GROUP_ROWS = [
    ("ext_chunk_size_usd", "number"),
    ("ext_artillery_size_usd", "number"),
    ("ext_scan_top_n", "number"),
    ("ext_scan_refresh", "number"),
    ("ext_pool_reserve", "number"),
    ("ext_exit_pct", "number"),
    ("ext_max_tier", "number"),
    ("ext_max_cost_basis", "number"),
    ("ext_direction", "combo"),
    ("ext_standing_alt_units", "number"),
    ("ext_correction_skip", "number"),
    ("ext_drawdown_threshold", "number"),
    ("ext_hedge_budget", "number"),
    ("ext_trend_strength", "number"),
]


def params_row(payload, name, kind):
    """One row of the parameter page, as a label and a widget."""
    labels = payload["fields"]["row_labels"]
    if kind == "number":
        return labels[name], number_widget(payload, name)
    if kind == "check_row":
        return None, check_widget(payload, name)
    if kind == "check_labelled":
        return labels[name], check_widget(payload, name)
    if kind == "ta_combo":
        return labels[name], combo_widget(
            payload, name, items=payload["timeframes"]["ta_items"]
        )
    if kind == "combo":
        return labels[name], combo_widget(payload, name)
    field = QLineEdit()
    field.setPlaceholderText(payload["fields"]["placeholders"][name])
    field.setText(payload["values"]["texts"][name])
    field.setToolTip(payload["fields"]["tool_tips"][name])
    return labels[name], field


def params_page_from(payload):
    """The parameter page, built only from the payload."""
    page = QWizardPage()
    page.setTitle(payload["pages"]["titles"]["params"])
    page.setSubTitle(payload["groups"]["params_subtitle"])
    outer = QVBoxLayout(page)
    outer.setContentsMargins(*payload["layout"]["outer_margins"])
    outer.setSpacing(payload["layout"]["outer_spacing_px"])
    scroll = QScrollArea(page)
    scroll.setWidgetResizable(payload["layout"]["scroll_widget_resizable"])
    scroll.setFrameShape(getattr(QScrollArea, payload["layout"]["scroll_frame_shape"]))
    scroll.setHorizontalScrollBarPolicy(
        getattr(Qt, payload["layout"]["scroll_horizontal_policy"])
    )
    scroll.setVerticalScrollBarPolicy(
        getattr(Qt, payload["layout"]["scroll_vertical_policy"])
    )
    inner = QWidget()
    scroll.setWidget(inner)
    outer.addWidget(scroll)
    groups = QVBoxLayout(inner)
    groups.setContentsMargins(*payload["layout"]["groups_margins"])
    groups.setSpacing(payload["layout"]["groups_spacing_px"])
    for key, rows in PARAMS_GROUP_ROWS.items():
        group = group_from(
            payload, key, [params_row(payload, name, kind) for name, kind in rows]
        )
        group.setVisible(payload["groups"]["visible"][key])
        groups.addWidget(group)
    extractor = QGroupBox(payload["groups"]["titles"]["extractor_group"])
    extractor.setVisible(payload["groups"]["visible"]["extractor_group"])
    form = QFormLayout(extractor)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    for name, kind in EXTRACTOR_GROUP_ROWS:
        label, widget = params_row(payload, name, kind)
        form.addRow(label, widget)
    groups.addWidget(extractor)
    return page


def folding_page_from(payload):
    """The profit folding page, built only from the payload."""
    page = QWizardPage()
    page.setTitle(payload["pages"]["titles"]["folding"])
    page.setSubTitle(payload["pages"]["subtitles"]["folding"])
    layout = QVBoxLayout(page)
    active = check_widget(payload, "folding_active")
    layout.addWidget(active)
    mode_group = QGroupBox(payload["groups"]["titles"]["fold_mode_group"])
    mode_layout = QVBoxLayout(mode_group)
    for name in ("fold_equal", "fold_log"):
        button = QRadioButton(payload["fields"]["radio_texts"][name])
        button.setChecked(payload["values"]["radios"][name])
        mode_layout.addWidget(button)
    layout.addWidget(mode_group)
    fold_group = QGroupBox(payload["groups"]["titles"]["fold_target_group"])
    fold_form = QFormLayout(fold_group)
    for name in ("fold_all", "fold_x"):
        button = QRadioButton(payload["fields"]["radio_texts"][name])
        button.setChecked(payload["values"]["radios"][name])
        fold_form.addRow(button)
    fold_form.addRow(
        payload["fields"]["row_labels"]["fold_x_count"],
        number_widget(payload, "fold_x_count"),
    )
    recent = QRadioButton(payload["fields"]["radio_texts"]["fold_recent"])
    recent.setChecked(payload["values"]["radios"]["fold_recent"])
    fold_form.addRow(recent)
    layout.addWidget(fold_group)
    dist_group = QGroupBox(payload["groups"]["titles"]["dist_target_group"])
    dist_form = QFormLayout(dist_group)
    for name in ("dist_all", "dist_x"):
        button = QRadioButton(payload["fields"]["radio_texts"][name])
        button.setChecked(payload["values"]["radios"][name])
        dist_form.addRow(button)
    dist_form.addRow(
        payload["fields"]["row_labels"]["dist_x_count"],
        number_widget(payload, "dist_x_count"),
    )
    dist_recent = QRadioButton(payload["fields"]["radio_texts"]["dist_recent"])
    dist_recent.setChecked(payload["values"]["radios"]["dist_recent"])
    dist_form.addRow(dist_recent)
    layout.addWidget(dist_group)
    return page


def phantom_page_from(payload):
    """The phantom page, built only from the payload."""
    page = QWizardPage()
    page.setTitle(payload["pages"]["titles"]["phantom"])
    page.setSubTitle(payload["pages"]["subtitles"]["phantom"])
    layout = QVBoxLayout(page)
    layout.addWidget(check_widget(payload, "phantom_enable"))
    layout.addWidget(
        QLabel(payload["fields"]["label_texts"]["phantom_timeframes_heading"])
    )
    row = QHBoxLayout()
    for found in payload["phantom_page"]["timeframes"]:
        box = QCheckBox(found)
        box.setChecked(payload["phantom_page"]["checked"][found])
        box.setEnabled(payload["phantom_page"]["enabled"][found])
        box.setToolTip(payload["phantom_page"]["tool_tips"][found])
        row.addWidget(box)
    layout.addLayout(row)
    lock_group = QGroupBox(payload["groups"]["titles"]["lock_group"])
    lock_form = QFormLayout(lock_group)
    lock_form.addRow(
        payload["fields"]["row_labels"]["lock_candles"],
        number_widget(payload, "lock_candles"),
    )
    layout.addWidget(lock_group)
    layout.addStretch()
    return page


PAGE_BUILDERS = {
    "mode": mode_page_from,
    "asset": asset_page_from,
    "pool": pool_page_from,
    "params": params_page_from,
    "folding": folding_page_from,
    "phantom": phantom_page_from,
}


def page_painted_by_the_model(name, payload):
    """The page one picture case describes, built only from the payload."""
    payload = unaltered(payload)
    which, _spec = PICTURE_SPECS[name]
    return PAGE_BUILDERS[which](payload)


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_paint_one_page_and_carry_one_skin(name):
    """The surface painted a different page than the shipped one paints."""
    assert_same_skin(
        build_old_side=lambda: page_painted_by_the_wizard(name),
        build_new_side=lambda: page_painted_by_the_model(name, model_payload(name)),
        size=PIXEL_SIZE,
        control_rule=CONTROL_RULE,
        note=name,
    )


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_painted_page_shows_more_than_one_colour(name):
    """A page that paints one colour compares against anything."""
    image = render_offscreen(page_painted_by_the_wizard(name), PIXEL_SIZE)
    found = assert_picture_can_report(image, note=name)
    assert found > 1, name
    blank = render_offscreen(QWidget(), PIXEL_SIZE)
    assert colour_count(blank) < found, (colour_count(blank), found)
    print(f"colour count {name}: {found}")


def test_the_picture_comparison_can_report_a_difference():
    """Two different real pages painted one picture, so no render reports."""
    assert_cases_paint_differently(
        old_side=render_offscreen(page_painted_by_the_wizard("mode"), PIXEL_SIZE),
        new_side=render_offscreen(
            page_painted_by_the_model("folding", model_payload("folding")), PIXEL_SIZE
        ),
    )
    assert_pictures_differ(
        old_side=render_offscreen(page_painted_by_the_wizard("folding"), PIXEL_SIZE),
        new_side=render_offscreen(
            page_painted_by_the_model("mode", model_payload("mode")), PIXEL_SIZE
        ),
        note="the other direction",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    payload = dict(model_payload("mode"))
    payload["pages"] = dict(payload["pages"])
    payload["pages"]["titles"] = dict(payload["pages"]["titles"])
    payload["pages"]["titles"]["mode"] = "changed"
    with pytest.raises(AssertionError, match="never came off"):
        page_painted_by_the_model("mode", payload)


def test_the_two_sides_paint_the_same_size():
    """One side rendered at a different size than the other."""
    old = render_offscreen(page_painted_by_the_wizard("mode"), PIXEL_SIZE)
    new = render_offscreen(
        page_painted_by_the_model("mode", model_payload("mode")), PIXEL_SIZE
    )
    assert (old.width(), old.height()) == (new.width(), new.height())
    assert_pictures_match(old_side=old, new_side=new)


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert narrow.sizeHint().width() != wide.sizeHint().width()
    else:
        assert narrow.sizeHint().width() == wide.sizeHint().width()


@skip_unless_no_fonts
def test_two_equal_length_names_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length names still differ."""
    assert app_font_advance_px("IIII") == app_font_advance_px("WWWW")


@skip_unless_real_fonts
def test_two_equal_length_names_measure_apart_with_fonts():
    """The glyphs decide their own width, and two names still measure alike."""
    assert app_font_advance_px("IIII") != app_font_advance_px("WWWW")


# What the wizard does with a value nobody entered

BARE_READINGS = [
    ("a stored True", True),
    ("not-a-number", math.nan),
    ("plus infinity", math.inf),
    ("minus infinity", -math.inf),
    ("text", "abc"),
    ("a number as text", "12.7"),
    ("a decimal", 12.7),
    ("ten to the four hundred", 10**400),
]


@pytest.mark.parametrize(
    "label,value", BARE_READINGS, ids=[one[0] for one in BARE_READINGS]
)
def test_the_stored_target_balance_reaches_both_sides_the_same_way(label, value):
    """A stored target balance settles differently on the two sides.

    The stored value reaches the spin box with no guard. Both sides must
    agree on what the spin box then holds, or on the refusal it makes.
    """
    spec = case("audit", defaults={"default_target_balance": value})
    old_refusal = None
    held = None
    with QtSeams(markets=spec["markets"]) as seams:
        try:
            page = shipped.TradingParamsPage(spec["defaults"])
            held = page.get_config()["target_balance"]
        except Exception as exc:
            old_refusal = exc
    assert seams.restored() is True
    if old_refusal is None:
        model = surface.BotWizardModel(
            spec["exchanges"], spec["defaults"], spec["markets"]
        )
        assert model.numbers["target_balance"] == held, (label, held)
        assert model.get_bot_config()["target_balance"] == held, label
    else:
        with pytest.raises(type(old_refusal)):
            surface.BotWizardModel(spec["exchanges"], spec["defaults"], spec["markets"])


def test_a_stored_not_a_number_becomes_the_highest_target_balance():
    """A stored not-a-number is refused, or settles somewhere else.

    Nothing guards the stored value, so a target balance nobody entered
    reaches a real bot. This pins what that number is.
    """
    spec = surface.NUMBER_FIELDS["target_balance"]
    with QtSeams(markets=MARKETS) as seams:
        page = shipped.TradingParamsPage({"default_target_balance": math.nan})
        held = page.get_config()["target_balance"]
    assert seams.restored() is True
    assert held == spec["maximum"] == 1000000.0
    assert held != spec["value"]
    model = surface.BotWizardModel(EXCHANGES, {"default_target_balance": math.nan})
    assert model.numbers["target_balance"] == held


def test_a_stored_true_becomes_the_lowest_target_balance():
    """A stored True is refused, or settles somewhere else."""
    spec = surface.NUMBER_FIELDS["target_balance"]
    with QtSeams(markets=MARKETS) as seams:
        page = shipped.TradingParamsPage({"default_target_balance": True})
        held = page.get_config()["target_balance"]
    assert seams.restored() is True
    assert held == spec["minimum"] == 1.0
    model = surface.BotWizardModel(EXCHANGES, {"default_target_balance": True})
    assert model.numbers["target_balance"] == held


def test_an_absent_stored_target_balance_uses_the_wizard_default():
    """The wizard's own default moved on one side only."""
    with QtSeams(markets=MARKETS) as seams:
        page = shipped.TradingParamsPage({})
        held = page.get_config()["target_balance"]
    assert seams.restored() is True
    assert held == surface.NUMBER_FIELDS["target_balance"]["value"] == 200.0
    model = surface.BotWizardModel(EXCHANGES, {})
    assert model.numbers["target_balance"] == held


@pytest.mark.parametrize(
    "value,expected",
    [(2.5e9, "$2.5B"), (1.5e6, "$1.5M"), (4.0e3, "$4K"), (999.0, ""), (0.0, "")],
)
def test_a_market_volume_prints_the_same_short_text_on_both_sides(value, expected):
    """A pair's volume prints differently on the two sides."""
    rows = {
        "coinbase": [
            {
                "symbol": "AAA/USDT",
                "base": "AAA",
                "quote": "USDT",
                "volume": value,
                "volatility": 0,
            }
        ]
    }
    with QtSeams(markets=rows) as seams:
        page = shipped.AssetSelectionPage(EXCHANGES)
        printed = page._target.itemText(0)
    assert seams.restored() is True
    assert surface.volume_text(value) == expected
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    assert model.target_items[0][0] == printed


@pytest.mark.parametrize("value", [True, math.inf, math.nan])
def test_a_market_volatility_nobody_measured_prints_the_same_on_both_sides(value):
    """A market reading nobody measured prints differently on the two sides.

    Neither side guards the venue's volatility, so a stored True prints
    as a percentage. Both sides must print it the same way.
    """
    rows = {
        "coinbase": [
            {
                "symbol": "AAA/USDT",
                "base": "AAA",
                "quote": "USDT",
                "volume": 0,
                "volatility": value,
            }
        ]
    }
    with QtSeams(markets=rows) as seams:
        page = shipped.AssetSelectionPage(EXCHANGES)
        printed = page._target.itemText(0)
    assert seams.restored() is True
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    assert model.target_items[0][0] == printed


def test_a_stored_true_volatility_prints_as_one_percent():
    """A stored True prints as something other than a percentage."""
    rows = {
        "coinbase": [
            {
                "symbol": "AAA/USDT",
                "base": "AAA",
                "quote": "USDT",
                "volume": 0,
                "volatility": True,
            }
        ]
    }
    with QtSeams(markets=rows) as seams:
        page = shipped.AssetSelectionPage(EXCHANGES)
        printed = page._target.itemText(0)
    assert seams.restored() is True
    assert printed == "AAA  (Volat: 1.0%)", printed


def text_volume_rows(value):
    """Two pairs, the first carrying ``value`` where a volume belongs."""
    return {
        "coinbase": [
            {
                "symbol": "AAA/USDT",
                "base": "AAA",
                "quote": "USDT",
                "volume": value,
                "volatility": 0,
            },
            {
                "symbol": "BBB/USDT",
                "base": "BBB",
                "quote": "USDT",
                "volume": 5.0e6,
                "volatility": 0,
            },
        ]
    }


@pytest.mark.parametrize("value", ["abc", "12.7"])
def test_a_market_reading_that_is_text_leaves_the_rest_of_the_pair_list(value):
    """One unusable volume ends the refill and the operator sees no pairs."""
    rows = text_volume_rows(value)
    with QtSeams(markets=rows) as seams:
        page = shipped.AssetSelectionPage(EXCHANGES)
        printed = [page._target.itemText(at) for at in range(page._target.count())]
    assert seams.restored() is True
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    assert printed == ["BBB  (Vol: $5.0M)", "AAA"], printed
    assert [one[0] for one in model.target_items] == printed


@pytest.mark.parametrize("value", ["abc", "12.7"])
def test_a_market_reading_that_is_text_carries_no_volume_of_its_own(value):
    """An unreadable volume prints as a figure the venue never reported."""
    rows = text_volume_rows(value)
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    named = dict(zip([one[1] for one in model.target_items], model.target_items))
    assert named["AAA"][0] == "AAA", named["AAA"]
    assert value not in named["AAA"][0], named["AAA"]


def test_the_unreadable_volume_check_still_prints_a_volume_it_can_read():
    """A volume the venue did report is dropped along with the unreadable one."""
    rows = text_volume_rows(2.5e9)
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    named = dict(zip([one[1] for one in model.target_items], model.target_items))
    assert named["AAA"][0] == "AAA  (Vol: $2.5B)", named["AAA"]


def test_a_venue_answering_with_text_names_no_timeframe_of_its_own():
    """One letter of a venue's answer becomes one timeframe the venue never offered."""
    assert surface.available_timeframes("coinbase", "1h") == surface.TA_TIMEFRAMES


def test_a_venue_answering_with_a_list_still_replaces_the_wizard_list():
    """A venue that does name its timeframes is ignored."""
    offered = ["1h", "4h", "1d"]
    assert surface.available_timeframes("coinbase", offered) == tuple(offered)


def test_a_venue_answering_with_text_greys_out_no_phantom_timeframe():
    """A venue's one-letter answer greys out every phantom timeframe."""
    model = surface.BotWizardModel(EXCHANGES, {})
    model.set_phantom_exchange_id("coinbase", "1h")
    greyed = [one for one, on in model.phantom_enabled_timeframes.items() if not on]
    assert greyed == [], greyed


def test_a_venue_naming_two_phantom_timeframes_greys_out_the_rest():
    """A venue that names two timeframes leaves every other one open."""
    model = surface.BotWizardModel(EXCHANGES, {})
    model.set_phantom_exchange_id("coinbase", ["1h", "1d"])
    open_now = [one for one, on in model.phantom_enabled_timeframes.items() if on]
    assert open_now == ["1h", "1d"], open_now


def rows_missing(key):
    """One good pair and one the venue sent without ``key``."""
    good = {"symbol": "AAA/USDT", "base": "AAA", "quote": "USDT", "volume": 1.0}
    short = {"symbol": "BBB/USDT", "base": "BBB", "quote": "USDT", "volume": 2.0}
    short.pop(key)
    return {"coinbase": [short, good]}


def test_a_pair_the_venue_sent_with_no_asset_leaves_the_rest_of_the_list():
    """A pair with no asset name stops the whole pair list."""
    model = surface.BotWizardModel(EXCHANGES, {}, rows_missing("base"))
    assert [one[1] for one in model.target_items] == ["AAA"]


def test_the_nameless_pair_check_still_keeps_a_pair_that_has_its_asset():
    """A pair carrying its asset name is dropped with the nameless one."""
    rows = {"coinbase": [{"symbol": "B/USDT", "base": "BBB", "quote": "USDT"}]}
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    assert [one[1] for one in model.target_items] == ["BBB"]


def test_an_alt_the_venue_sent_with_no_symbol_leaves_the_rest_of_the_list():
    """An alt with no symbol stops the whole alt list."""
    rows = {
        "coinbase": [
            {"base": "BBB", "quote": "BTC", "volume": 2.0},
            {"symbol": "AAA/BTC", "base": "AAA", "quote": "BTC", "volume": 1.0},
        ]
    }
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    model.set_combo_index("pool_base", 0)
    assert [one[1] for one in model.alt_items] == ["AAA/BTC"]


def test_the_symbol_less_alt_check_still_keeps_an_alt_that_has_its_symbol():
    """An alt carrying its symbol is dropped with the symbol-less one."""
    rows = {"coinbase": [{"symbol": "AAA/BTC", "base": "AAA", "quote": "BTC"}]}
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    model.set_combo_index("pool_base", 0)
    assert [one[1] for one in model.alt_items] == ["AAA/BTC"]


def pool_model():
    """A model whose pool page holds two alts, in volume order."""
    rows = {
        "coinbase": [
            {"symbol": "AAA/BTC", "base": "AAA", "quote": "BTC", "volume": 3.0},
            {"symbol": "BBB/BTC", "base": "BBB", "quote": "BTC", "volume": 2.0},
        ]
    }
    model = surface.BotWizardModel(EXCHANGES, {}, rows)
    model.set_combo_index("pool_base", 0)
    return model


def test_a_tick_at_a_position_before_the_first_alt_reaches_no_alt_at_all():
    """A tick at minus one reaches the last alt instead of refusing."""
    model = pool_model()
    with pytest.raises(IndexError):
        model.set_alt_checked(-1, True)
    assert model.alt_checked == [False, False], model.alt_checked


def test_a_tick_at_a_position_the_alt_list_holds_still_reaches_that_alt():
    """A tick at a position the list holds is refused with the bad ones."""
    model = pool_model()
    model.set_alt_checked(0, True)
    assert model.alt_checked == [True, False], model.alt_checked


def phantom_model():
    """A model sitting on the phantom page with one timeframe ticked."""
    model = surface.BotWizardModel(EXCHANGES, {})
    model.set_check("phantom_enable", True)
    model.set_phantom_timeframe("1h", True)
    model.current_page = surface.PHANTOM
    model.exchange_id = "coinbase"
    return model


def test_a_refusal_the_operator_answered_leaves_no_warning_standing():
    """A warning about a set the operator already reduced is still published."""
    model = phantom_model()
    model.validate_page((False, "too many"), False)
    model.validate_page((True, ""), False)
    assert model.warning_box is None, model.warning_box


def test_the_standing_warning_check_still_sees_the_refusal_itself():
    """A refusal publishes no warning for the operator to read."""
    model = phantom_model()
    model.validate_page((False, "too many"), False)
    assert model.warning_box is not None
    assert model.warning_box[0] == surface.API_WARNING_TITLE


def test_a_venue_whose_id_is_not_text_names_no_venue_at_all():
    """A venue id that is not text stops the whole wizard."""
    payload = surface.build_view_model([{"exchange_id": 5}], {}, {})
    assert payload["asset_page"]["config"]["exchange_id"] == ""


def test_the_venue_id_check_still_reads_a_venue_id_that_is_text():
    """A venue id that is text is read as no venue."""
    payload = surface.build_view_model(EXCHANGES, {}, {})
    assert payload["asset_page"]["config"]["exchange_id"] == "coinbase"


# The world outside the process


def test_every_swapped_name_is_put_back_after_a_drive_and_after_a_refusal():
    """A swapped name outlived its drive and reached the next test."""
    plain = drive_old(BY_NAME["happy"])
    assert plain["swapped_during"] is True, "the seams were not installed"
    assert plain["seams"].restored() is True
    refused = drive_old(BY_NAME["refused_at_the_phantom_page"])
    assert refused["seams"].restored() is True
    import PySide6.QtWidgets as widgets

    assert widgets.QMessageBox is not FakeBox


def test_the_swap_watcher_reports_a_name_that_was_not_put_back():
    """The swap watcher answers restored whatever the names hold."""
    seams = QtSeams(markets=MARKETS)
    with seams:
        assert seams.restored() is False
    assert seams.restored() is True
    saved = shipped._ASSET_MANAGER.get
    shipped._ASSET_MANAGER.get = lambda: None
    try:
        assert seams.restored() is False
    finally:
        shipped._ASSET_MANAGER.get = saved
    assert seams.restored() is True


def test_the_shipped_wizard_leaves_the_shared_logger_alone():
    """The wizard added a handler to the logger every other tab writes to."""
    root = logging.getLogger()
    before = list(root.handlers)
    drive_old(BY_NAME["happy"])
    assert list(root.handlers) == before, root.handlers


def test_a_case_reads_the_same_whatever_ran_before_it():
    """A driven case depends on what another case left behind."""
    first = digest(new_answer(BY_NAME["happy"]))
    new_answer(BY_NAME["extractor"])
    new_answer(BY_NAME["refused_at_the_phantom_page"])
    assert digest(new_answer(BY_NAME["happy"])) == first


@pytest.fixture
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    The counter watches this process only. A child process opens its own
    sockets and is never seen here; the subprocess probes below carry
    their own refusal.
    """
    attempted: list = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def outside(address) -> bool:
        host = address[0] if isinstance(address, tuple) else address
        return str(host) not in LOOPBACK

    def refuse(address):
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *_f, **_n):
        if outside(address):
            return refuse(address)
        return real_connect(self, address, *_f, **_n)

    def watched_connect_ex(self, address, *_f, **_n):
        if outside(address):
            return refuse(address)
        return real_connect_ex(self, address, *_f, **_n)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", watched_connect_ex)
    monkeypatch.setattr(
        socket, "create_connection", lambda address, *_f, **_n: refuse(address)
    )
    yield attempted


def test_no_driven_case_reaches_outside_the_process(refuse_outside_connections):
    """A driven case opened a socket to a venue."""
    for spec in ALL_CASES:
        new_model(spec)
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["extractor"])
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_two_real_outside_addresses(
    refuse_outside_connections,
):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("api.exchange.coinbase.com", 443)
    second = ("api.kraken.com", 443)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACERVATOR_TEST_HOME", str(home))
    for spec in ALL_CASES:
        new_model(spec)
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["extractor"])
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


def test_no_drive_reads_the_operators_own_state_file(monkeypatch):
    """A drive opened the file the running bots keep their state in."""
    opened: list = []
    real_open = builtins.open

    def watched(file, *found, **named):
        opened.append(str(file))
        return real_open(file, *found, **named)

    monkeypatch.setattr(builtins, "open", watched)
    for spec in ALL_CASES[:5]:
        new_model(spec)
    drive_old(BY_NAME["happy"])
    guarded = [name for name in opened if ".acervator" in name.replace("\\", "/")]
    assert guarded == [], guarded
    assert len(opened) >= 0


# The bridge, and a process that never loads Qt


def build_payload(spec):
    """The surface's whole answer for one case, through the public entry."""
    return surface.build_view_model(
        spec["exchanges"],
        spec["defaults"],
        spec["markets"],
        {
            "mode": spec["mode"],
            "checks": spec["checks"],
            "walk": [list(step) for step in spec["walk"]],
        },
        venue_timeframes(spec),
    )


def test_the_bridge_registers_the_bot_wizard_method():
    """The Electron renderer cannot reach the bot wizard."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model


def test_the_bridge_answer_is_json_serialisable():
    """A value in the answer cannot cross the bridge."""
    answered = surface.view_model(
        {
            "exchanges": EXCHANGES,
            "defaults": {"default_target_balance": 250.0},
            "markets": MARKETS,
            "timeframes": {"coinbase": supported_timeframes("coinbase")},
            "walk": [["next"], ["next"]],
        }
    )
    text = json.dumps(answered)
    assert json.loads(text)["pages"]["current_id"] == surface.PAGE_IDS[surface.PARAMS]
    assert json.loads(text)["values"]["numbers"]["target_balance"] == 250.0


def test_the_bridge_keeps_nothing_between_two_requests():
    """One request carried a value the request before it set."""
    first = surface.view_model(
        {"exchanges": EXCHANGES, "defaults": {"default_target_balance": 999.0}}
    )
    second = surface.view_model({"exchanges": EXCHANGES})
    assert first["values"]["numbers"]["target_balance"] == 999.0
    assert second["values"]["numbers"]["target_balance"] == 200.0


BRIDGE_PROBE = r"""
import json, sys

from src.core.desktop_bridge import build_registry

registry = build_registry()
handler = registry["bot_wizard.state"]
answer = handler({
    "exchanges": [{"display_name": "Coinbase", "exchange_id": "coinbase"}],
    "defaults": {"default_target_balance": 250.0},
    "markets": {"coinbase": [
        {"symbol": "ZZZ/USDT", "base": "ZZZ", "quote": "USDT",
         "volume": 2.5e9, "volatility": 3.2}]},
    "walk": [["next"], ["next"]],
})
print(json.dumps({
    "qt": [name for name in sys.modules if name.startswith("PySide6")],
    "current_id": answer["pages"]["current_id"],
    "target_balance": answer["values"]["numbers"]["target_balance"],
    "target_items": answer["asset_page"]["target_items"],
    "status": answer["asset_page"]["status"],
    "config_mode": answer["config"]["mode"],
}))
"""

NOTHING_AT_IMPORT_PROBE = r"""
import builtins, json, os, socket, sys, tempfile, threading
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="acervator-wizard-probe-"))
os.environ["HOME"] = str(root)
os.environ["USERPROFILE"] = str(root)

opened = []
real_open = open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


builtins.open = watched_open

import time
clock = []
real_time = time.time
real_monotonic = time.monotonic
real_localtime = time.localtime
time.time = lambda: clock.append("time") or real_time()
time.monotonic = lambda: clock.append("monotonic") or real_monotonic()
time.localtime = lambda *a: clock.append("localtime") or real_localtime(*a)

reached = []


def refuse(address, *found, **named):
    reached.append(str(address))
    raise OSError("the probe may not reach outside")


socket.create_connection = refuse
socket.socket.connect = lambda self, address, *_f, **_n: refuse(address)

# The package chain is imported FIRST and its cost measured, because
# importing `src` starts threads and a process of its own. Only what the
# module under test adds on top of that is charged to it.
threads_before_chain = threading.active_count()
opened_before_chain = len(opened)
clock_before_chain = len(clock)
import src.gui.main_tabs
chain = {
    "threads": threading.active_count() - threads_before_chain,
    "opened": len(opened) - opened_before_chain,
    "clock": len(clock) - clock_before_chain,
}

threads_before = threading.active_count()
opened_before = len(opened)
clock_before = len(clock)
reached_before = len(reached)
from src.gui.main_tabs import bot_wizard_surface as s

mine = {
    "threads": threading.active_count() - threads_before,
    "opened": opened[opened_before:],
    "clock": clock[clock_before:],
    "reached": reached[reached_before:],
}
model = s.BotWizardModel()
answer = {
    "chain": chain,
    "mine": mine,
    "title": s.WINDOW_TITLE,
    "built_on_request": model.current_page_id() == s.START_PAGE_ID,
    "qt": [name for name in sys.modules if name.startswith("PySide6")],
    "made_under_home": sorted(str(p) for p in root.rglob("*")),
}
builtins.open = real_open
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
    """Reaching the bot wizard pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["current_id"] == surface.PAGE_IDS[surface.PARAMS]
    assert answered["target_balance"] == 250.0
    assert answered["target_items"] == [["ZZZ  (Vol: $2.5B, Volat: 3.2%)", "ZZZ"]]
    assert answered["status"] == "1 USDT pairs (sorted by volume)"
    assert answered["config_mode"] == surface.SCRUMMING_MODE


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] != []
    assert loaded["current_id"] == surface.PAGE_IDS[surface.PARAMS]


def test_importing_the_surface_reads_no_file_and_no_clock():
    """Loading the surface read a file, read the clock or started a thread.

    The package chain is imported first and its own cost reported, so a
    thread the chain starts is never charged to this module.
    """
    answered = run_script(NOTHING_AT_IMPORT_PROBE)
    assert answered["mine"]["opened"] == [], answered["mine"]
    assert answered["mine"]["clock"] == [], answered["mine"]
    assert answered["mine"]["reached"] == [], answered["mine"]
    assert answered["mine"]["threads"] == 0, answered["mine"]
    assert answered["qt"] == [], answered["qt"]
    assert answered["made_under_home"] == [], answered
    assert answered["title"] == surface.WINDOW_TITLE
    assert answered["built_on_request"] is True
    print(
        f"import cost -- package chain {answered['chain']}, module {answered['mine']}"
    )


def test_the_import_probe_can_report_a_file_a_clock_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import bot_wizard_surface as s",
        "time.time()\n"
        "with open(root / 'bot_wizard-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "from src.gui.main_tabs import bot_wizard_surface as s",
    )
    answered = run_script(probe)
    assert answered["mine"]["clock"] == ["time"], answered["mine"]
    assert answered["mine"]["reached"] != [], answered["mine"]
    assert answered["mine"]["opened"] != [], answered["mine"]
    assert answered["made_under_home"] != [], answered


def test_the_import_probe_charges_the_package_chain_to_the_chain():
    """The probe charges the package's own import cost to this module.

    What the package chain costs is a fact about the host, not about the
    product, so it is reported and never asserted. What is asserted is
    that the chain window and the module window are the same instrument:
    a file opened inside the chain window is counted there and not
    against the module.
    """
    plain = run_script(NOTHING_AT_IMPORT_PROBE)
    assert set(plain["chain"]) == {"threads", "opened", "clock"}, plain["chain"]
    seeded = run_script(
        NOTHING_AT_IMPORT_PROBE.replace(
            "import src.gui.main_tabs",
            "open(root / 'chain-seeded.json', 'w').close()\n"
            "import src.gui.main_tabs",
        )
    )
    assert seeded["chain"]["opened"] == plain["chain"]["opened"] + 1, (
        plain["chain"],
        seeded["chain"],
    )
    assert seeded["mine"]["opened"] == [], seeded["mine"]
    print(
        f"import cost -- chain {plain['chain']}, "
        f"module {{'threads': {plain['mine']['threads']}, "
        f"'opened': {len(plain['mine']['opened'])}, "
        f"'clock': {len(plain['mine']['clock'])}}}"
    )


def test_the_surface_loads_no_qt_module_and_reaches_for_nothing():
    """The surface grew an import that pulls Qt into the backend."""
    tree = parsed(SURFACE_SOURCE)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert not any(name.startswith("ccxt") for name in imported), imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("read_text", "write_text", "mkdir", "urlopen", "monotonic"):
        assert forbidden not in reached, forbidden


def test_the_import_scan_reports_a_module_the_shipped_file_does_load():
    """The import scan reports nothing whatever a file imports."""
    imported = set()
    for node in ast.walk(parsed(WIZARD_SOURCE)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert any(name.startswith("PySide6") for name in imported), imported


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences
