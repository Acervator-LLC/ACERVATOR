"""The shipped Live Bot Settings window and the Qt-free surface, side by side.

A failure means the view model carries a different title, a different
heading, a different state colour, a different button, a different
tooltip, a different tab, a different pending line, a different applied
line, a different recorded step or a different refusal than
``BotLiveSettingsDialog``.

No test here reads or writes the operator's runtime tree, opens a socket
or reaches an exchange. Every bot id, pair, balance and manager below is
invented.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import bot_live_settings as shipped
from src.gui.main_tabs import bot_live_settings_surface as surface
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
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

WINDOW_PATH = REPO_ROOT / "src/gui/bot_live_settings.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/bot_live_settings_surface.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_CONTROL_PATH = REPO_ROOT / "src/gui/stock_main_window.py"

PIXEL_SIZE = (760, 200)

# Counts measured off the file by the same counter that is pointed at a
# neighbour which really has one.
WINDOW_CONNECT_SITES = 4
WINDOW_TIMER_BUILDS = 0
WINDOW_BUS_SITES = 0
WINDOW_SIGNAL_BUILDS = 1
WINDOW_ELEMENT_BUILDS = 10
CONTROL_CONNECT_SITES = 1
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_SIGNAL_BUILDS = 3
CONTROL_ELEMENT_BUILDS = 3

# Invented values. No pair, bot id or balance below is the operator's.
PLAIN_ASSET = "CHIP"
UNICODE_ASSET = "Δ⚡"
MARKUP_ASSET = "<b>X</b>"
APOSTROPHE_ASSET = "Ekthelius" + chr(39) + "s"
NEWLINE_BOT_ID = "two\nlines-one-bot"
LONG_BOT_ID = "x" * 200
PLAIN_BOT_ID = "bot-alpha-0001-beta"
LOWER_BOT_ID = "BOT-Alpha-0001"

WIDGETS_HELD: list = []


# ---------------------------------------------------------------------
# The application object, and the widgets a render must outlive
# ---------------------------------------------------------------------


def app():
    """The one application object every widget below is built under."""
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance() or QApplication([])


def hold(widget):
    """Keep `widget` alive for the whole run and return it."""
    WIDGETS_HELD.append(widget)
    return widget


@pytest.fixture(autouse=True)
def own_shared_state(monkeypatch):
    """Give this test its own market inspector and its own bus.

    Both are one object for the whole process and the shipped window
    reaches them while it builds its tabs, so a reading one test leaves
    behind would decide what a later test draws. A NEW object is handed
    out rather than a cleared one: clearing walks only the fields the
    holder declares.
    """
    from src.trading import market_inspector

    assert hasattr(
        market_inspector, "_GLOBAL_INSPECTOR"
    ), "the shared inspector was renamed; this guard now resets nothing"
    monkeypatch.setattr(market_inspector, "_GLOBAL_INSPECTOR", None)
    yield market_inspector


# ---------------------------------------------------------------------
# The case table: one spec drives both sides
# ---------------------------------------------------------------------


def spec(**over):
    """One window's whole input, as plain values."""
    found = {
        "asset": PLAIN_ASSET,
        "bot_id": PLAIN_BOT_ID,
        "state": "running",
        "mode": "scrumming",
        "siblings": (),
        "symbol": None,
    }
    found.update(over)
    return found


CASES = {
    "happy": spec(),
    "empty": spec(asset="", bot_id="", symbol=""),
    "zero": spec(symbol=0, bot_id="0"),
    "negative": spec(symbol=-250.75),
    "thousand_million": spec(symbol=1_000_000_000.0),
    "one_billionth": spec(symbol=0.000_000_001),
    "unicode": spec(asset=UNICODE_ASSET, bot_id=UNICODE_ASSET + "-0001"),
    "long_two_hundred": spec(bot_id=LONG_BOT_ID),
    "markup": spec(asset=MARKUP_ASSET, bot_id="<i>bot</i>-0001"),
    "apostrophe": spec(asset=APOSTROPHE_ASSET, bot_id=APOSTROPHE_ASSET + "-1"),
    "wrong_capitals": spec(bot_id=LOWER_BOT_ID, state="RunNing"),
    "newline": spec(bot_id=NEWLINE_BOT_ID),
    "number_where_text": spec(symbol=12),
    "infinity": spec(symbol=float("inf")),
    "minus_infinity": spec(symbol=float("-inf")),
    "not_a_number": spec(symbol=float("nan")),
    "unknown_state": spec(state="melting"),
    "stopped": spec(state="stopped"),
    "idle": spec(state="idle"),
    "paused": spec(state="paused"),
    "error_state": spec(state="error"),
    "cooldown": spec(state="cooldown"),
    "extractor": spec(mode="extractor", asset="*"),
    "two_siblings": spec(siblings=(PLAIN_BOT_ID, "bot-beta-0002")),
    "three_siblings": spec(
        siblings=(PLAIN_BOT_ID, "bot-beta-0002", "bot-gamma-0003"),
    ),
    "one_sibling": spec(siblings=(PLAIN_BOT_ID,)),
    "unlisted_bot": spec(siblings=("bot-beta-0002", "bot-gamma-0003")),
}

CASE_NAMES = tuple(sorted(CASES))

REFUSING_CASES = {
    "bot_id_is_a_number": spec(bot_id=7),
    "state_is_a_number": spec(state=3),
    "mode_is_a_number": spec(mode=5),
    "bot_id_is_none": spec(bot_id=None),
    "state_is_none": spec(state=None),
}

SEQUENCES = {
    "raise_then_lower": ("target_balance", 250.0, "target_balance", 50.0),
    "edit_then_revert": ("target_balance", 250.0, "target_balance", 100.0),
    "two_fields": ("target_balance", 250.0, "visibility", "internal"),
}

AGE_SECONDS = (
    0,
    0.4,
    1,
    59,
    59.9,
    60,
    61,
    3599,
    3600,
    3601,
    86399,
    86400,
    86401,
    -1,
    -60,
    1_000_000_000.0,
    0.000_000_001,
    True,
)
REFUSING_AGES = (float("-inf"), "abc", None, [1])


# ---------------------------------------------------------------------
# Building the shipped window
# ---------------------------------------------------------------------


class Exchange:
    """The one value a bot reads off its exchange while it is built."""

    exchange_id = "test"


class Manager:
    """The manager the window asks for its sibling bot ids."""

    def __init__(self, bot_ids=(), ids_raise=None, save_raises=None, can_save=True):
        self._bots = {str(one): object() for one in bot_ids}
        self.ids_raise = ids_raise
        self.save_raises = save_raises
        self.saves: list = []
        if ids_raise is not None:
            self._bots = BrokenMapping(ids_raise)
        if can_save:
            self.save_all_state = self._save

    def _save(self):
        if self.save_raises is not None:
            raise self.save_raises
        self.saves.append(1)


class BrokenMapping(dict):
    """A bot register that refuses to list its keys."""

    def __init__(self, error):
        super().__init__()
        self.error = error

    def keys(self):
        raise self.error


def shipped_bot(one):
    """One running bot, built the way the window is handed one."""
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.extractor_bot import ExtractorBot
    from src.trading.scrumming_bot import ScrummingBot

    mode = BotMode.EXTRACTOR if one["mode"] == "extractor" else BotMode.SCRUMMING
    config = make_bot_config(
        mode,
        exchange_id="test",
        base_currency="USD",
        target_asset="*" if mode is BotMode.EXTRACTOR else one["asset"] or "CHIP",
        target_balance=100.0,
    )
    if mode is BotMode.EXTRACTOR:
        bot = ExtractorBot(config, Exchange())
    else:
        bot = ScrummingBot(config, Exchange(), enable_phantoms=False)
    if one["symbol"] is not None:
        bot.config.symbol = one["symbol"]
    elif one["asset"] == "":
        bot.config.symbol = ""
    bot.bot_id = one["bot_id"]
    bot.state = StateValue(one["state"])
    bot.config.mode = ModeValue(one["mode"])
    return bot


class StateValue:
    """A bot state that answers ``value``, as the shipped enum does."""

    def __init__(self, value):
        self.value = value


class ModeValue:
    """A bot mode that answers ``value``, as the shipped enum does."""

    def __init__(self, value):
        self.value = value


def old_window(one, manager=None):
    """The shipped window, opened for one spec."""
    app()
    return hold(shipped.BotLiveSettingsDialog(shipped_bot(one), manager, None))


def old_window_for(name):
    """The shipped window for one named case, with its manager."""
    one = CASES[name]
    manager = Manager(one["siblings"]) if one["siblings"] else None
    return old_window(one, manager)


#: What the shipped config holds for the fields an edit run touches.
SHIPPED_CONFIG_FIELDS = {"target_balance": 100.0, "visibility": "orderbook"}


def new_model_for(name, fields=None):
    """The surface's window for one named case, built."""
    one = CASES[name]
    model = surface.BotLiveSettingsModel(
        surface.BotSource(
            config=surface.BotConfigSource(
                symbol=surface_symbol(one), mode=one["mode"], fields=fields
            ),
            bot_id=one["bot_id"],
            state=one["state"],
        ),
        surface.BotManagerSource(one["siblings"]) if one["siblings"] else None,
    )
    model.build()
    return model


def surface_symbol(one):
    """The pair the shipped config settles on, handed to the surface."""
    if one["symbol"] is not None:
        return one["symbol"]
    if one["asset"] == "":
        return ""
    if one["mode"] == "extractor":
        return "*/USD"
    return "%s/USD" % one["asset"]


# ---------------------------------------------------------------------
# Reading each side into one comparable shape
# ---------------------------------------------------------------------


def read_old(window):
    """Every value the shipped window shows, read off the built window."""
    from PySide6.QtGui import QShortcut

    layout = window.layout()
    header_row = layout.itemAt(0).layout()
    button_row = layout.itemAt(2).layout()
    header = header_row.itemAt(0).widget()
    state = header_row.itemAt(1).widget()
    prev = header_row.itemAt(3).widget()
    following = header_row.itemAt(4).widget()
    apply_button = button_row.itemAt(1).widget()
    close = button_row.itemAt(2).widget()
    tabs = window._tabs
    return {
        "title": window.windowTitle(),
        "minimum_size_px": [window.minimumWidth(), window.minimumHeight()],
        "header_label": header.text(),
        "header_style": header.styleSheet(),
        "state_label": state.text(),
        "state_style": state.styleSheet(),
        "prev_label": prev.text(),
        "prev_tooltip": prev.toolTip(),
        "next_label": following.text(),
        "next_tooltip": following.toolTip(),
        "nav_style": prev.styleSheet(),
        "next_style": following.styleSheet(),
        "nav_shown": prev.isVisibleTo(window),
        "next_shown": following.isVisibleTo(window),
        "tabs": [tabs.tabText(index) for index in range(tabs.count())],
        "current_tab": window.active_tab_index(),
        "apply_label": apply_button.text(),
        "apply_style": apply_button.styleSheet(),
        "apply_enabled": apply_button.isEnabled(),
        "close_label": close.text(),
        "close_style": close.styleSheet(),
        "change_label": window._change_lbl.text(),
        "change_style": window._change_lbl.styleSheet(),
        "changes": dict(window._changes),
        "siblings": list(window._sibling_bot_ids()),
        "pending_navigate_to": window._pending_navigate_to,
        "shortcuts": sorted(
            one.key().toString() for one in window.findChildren(QShortcut)
        ),
        "fold_sort_key": window._fold_sort_key,
        "style_sheet": window.styleSheet(),
    }


def read_new(model):
    """Every value the surface's window shows, read off its payload."""
    payload = surface.build_view_model(model)
    return {
        "title": payload["title"],
        "minimum_size_px": payload["minimum_size_px"],
        "header_label": payload["header_label"],
        "header_style": payload["header_style"],
        "state_label": payload["state_label"],
        "state_style": payload["state_style"],
        "prev_label": payload["prev_label"],
        "prev_tooltip": payload["prev_tooltip"],
        "next_label": payload["next_label"],
        "next_tooltip": payload["next_tooltip"],
        "nav_style": payload["nav_style"],
        "next_style": payload["nav_style"],
        "nav_shown": payload["nav_shown"],
        "next_shown": payload["nav_shown"],
        "tabs": payload["tabs"],
        "current_tab": payload["current_tab"],
        "apply_label": payload["apply_label"],
        "apply_style": payload["apply_style"],
        "apply_enabled": payload["apply_enabled"],
        "close_label": payload["close_label"],
        "close_style": payload["close_style"],
        "change_label": payload["change_label"],
        "change_style": payload["change_style"],
        "changes": payload["changes"],
        "siblings": payload["siblings"],
        "pending_navigate_to": payload["pending_navigate_to"],
        "shortcuts": sorted(pair[0] for pair in payload["shortcuts"]),
        "fold_sort_key": payload["fold_sort_key"],
        "style_sheet": payload["style_sheet"],
    }


def numbered(value):
    """One number as its own text, so a whole number and a decimal differ.

    ``12`` and ``12.0`` compare equal and hash apart, and a not-a-number
    is never equal to itself, so both are read as text before any
    comparison.
    """
    if isinstance(value, bool):
        return "bool:%s" % value
    if isinstance(value, float):
        if math.isnan(value):
            return "float:nan"
        return "float:%r" % value
    if isinstance(value, int):
        return "int:%d" % value
    return value


def readable(value):
    """One value as nested text, ordered so a swap changes it."""
    if isinstance(value, dict):
        return [
            [readable(key), readable(item)]
            for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
        ]
    if isinstance(value, (list, tuple)):
        return [readable(item) for item in value]
    return repr(numbered(value))


def digest(reading):
    """SHA-256 over every value one side reported, at every depth."""
    return hashlib.sha256(
        json.dumps(
            {key: readable(value) for key, value in sorted(reading.items())}
        ).encode("utf-8")
    ).hexdigest()


def both_sides_agree(name, note=""):
    """Fail unless the two sides report one value and one hash."""
    old_side = read_old(old_window_for(name))
    new_side = read_new(new_model_for(name))
    assert set(old_side) == set(new_side), sorted(set(old_side) ^ set(new_side))
    differences = [
        key
        for key in sorted(old_side)
        if readable(old_side[key]) != readable(new_side[key])
    ]
    assert differences == [], "%s%s: old %r new %r" % (
        name,
        " " + note if note else "",
        {key: old_side[key] for key in differences},
        {key: new_side[key] for key in differences},
    )
    assert digest(old_side) == digest(new_side), name
    return old_side, new_side


# ---------------------------------------------------------------------
# Both sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_window_is_the_shipped_window(name):
    """The surface reports a different window than the shipped one."""
    both_sides_agree(name)


def undriven(table, driven):
    """Every name in one table that no run drives."""
    return sorted(set(table) - set(driven))


def test_the_coverage_check_reports_a_case_no_run_drives():
    """The coverage check passes whatever a table grows."""
    assert undriven(CASES, CASE_NAMES) == []
    assert undriven(dict(CASES, a_case_no_run_drives=None), CASE_NAMES) == [
        "a_case_no_run_drives"
    ]
    assert undriven(APPLY_RUNS, ()) == sorted(APPLY_RUNS)


def test_every_case_in_the_table_is_driven():
    """A case sits in the table and no test ever drives it."""
    assert undriven(CASES, CASE_NAMES) == []
    assert len(CASES) >= 25, len(CASES)
    for name in REFUSING_CASES:
        assert name not in CASES, name


def test_the_sample_hashes_are_reported():
    """The hash reader answers nothing, so a hash comparison means nothing."""
    samples = {name: digest(read_new(new_model_for(name))) for name in sorted(CASES)}
    assert len({len(one) for one in samples.values()}) == 1
    assert len(set(samples.values())) > 1, samples
    assert all(len(one) == 64 for one in samples.values()), samples


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash gives one answer whatever it is given."""
    old_happy = digest(read_old(old_window_for("happy")))
    new_unicode = digest(read_new(new_model_for("unicode")))
    assert old_happy != new_unicode
    new_happy = digest(read_new(new_model_for("happy")))
    old_unicode = digest(read_old(old_window_for("unicode")))
    assert new_happy != old_unicode
    assert old_happy == new_happy
    assert old_unicode == new_unicode


def test_the_same_input_hashes_the_same_twice():
    """The hash moves between two readings of one input."""
    assert digest(read_new(new_model_for("happy"))) == digest(
        read_new(new_model_for("happy"))
    )
    assert digest(read_old(old_window_for("happy"))) == digest(
        read_old(old_window_for("happy"))
    )


def test_a_whole_number_and_a_decimal_are_told_apart():
    """A whole number and a decimal compare equal, so a change is invisible."""
    assert 12 == 12.0
    assert readable(12) != readable(12.0)
    assert readable(True) != readable(1)
    assert readable({"a": 12}) != readable({"a": 12.0})


def test_two_not_a_numbers_compare_equal_as_text():
    """A not-a-number never equals itself, so it reads as a difference."""
    left = float("nan")
    right = float("nan")
    assert left != left
    assert left != right
    assert readable(left) == readable(right)
    assert readable(left) != readable(float("inf"))


PLATFORM_CHOSEN_KEYS = ("style_sheet",)


def platform_chosen(reading):
    """One reading with every value the platform decides taken out.

    The window sets no style sheet of its own, so what a reading holds
    there is whatever the running application put on it.
    """
    return {
        key: value for key, value in reading.items() if key not in PLATFORM_CHOSEN_KEYS
    }


def test_the_machine_rule_keeps_a_seeded_value_and_hides_an_unseeded_one():
    """The rule hides a value the product sets, or keeps one it does not."""
    reading = read_new(new_model_for("happy"))
    assert "title" in platform_chosen(reading)
    assert "style_sheet" not in platform_chosen(reading)
    assert platform_chosen({"style_sheet": "x", "title": "y"}) == {"title": "y"}


# ---------------------------------------------------------------------
# Where both sides refuse, the TYPE is compared and never the wording
# ---------------------------------------------------------------------


def refusal_of(run):
    """The type one side refuses with, or None when it answered."""
    try:
        run()
    except BaseException as exc:
        return type(exc).__name__
    return None


def headline_of(run):
    """The first line of the message one side refused with."""
    try:
        run()
    except BaseException as exc:
        return str(exc).splitlines()[0] if str(exc) else ""
    return ""


REFUSING_CASE_NAMES = tuple(sorted(REFUSING_CASES))


@pytest.mark.parametrize("name", REFUSING_CASE_NAMES)
def test_a_refused_window_refuses_the_same_way_on_both_sides(name):
    """One side built a window the other refused to build."""
    one = REFUSING_CASES[name]

    def old_side():
        return old_window(one)

    def new_side():
        model = surface.BotLiveSettingsModel(
            surface.BotSource(
                config=surface.BotConfigSource(
                    symbol=surface_symbol(one), mode=one["mode"]
                ),
                bot_id=one["bot_id"],
                state=one["state"],
            )
        )
        model.build()
        return model

    old_refusal = refusal_of(old_side)
    new_refusal = refusal_of(new_side)
    assert old_refusal is not None, name
    assert old_refusal == new_refusal, name


def test_the_refusal_comparison_holds_more_than_one_type():
    """Every case refuses alike, so a swapped type would read as a match."""
    found = set()
    for one in REFUSING_CASES.values():

        def new_side(one=one):
            model = surface.BotLiveSettingsModel(
                surface.BotSource(
                    config=surface.BotConfigSource(
                        symbol=surface_symbol(one), mode=one["mode"]
                    ),
                    bot_id=one["bot_id"],
                    state=one["state"],
                )
            )
            model.build()

        found.add(refusal_of(new_side))
    assert len(found) > 1, found
    assert None not in found, found


def test_the_refusal_reader_reports_two_different_wordings():
    """The two sides word a refusal alike, so wording would compare clean."""

    def old_side():
        return old_window(REFUSING_CASES["bot_id_is_a_number"])

    def new_side():
        model = surface.BotLiveSettingsModel(
            surface.BotSource(bot_id=7, config=surface.BotConfigSource())
        )
        model.build()

    assert refusal_of(old_side) == refusal_of(new_side)
    assert headline_of(old_side) != "" or headline_of(new_side) != ""


@pytest.mark.parametrize("seconds", AGE_SECONDS)
def test_one_age_reads_the_same_on_both_sides(seconds):
    """The two sides put a different age in front of the operator."""
    assert shipped.BotLiveSettingsDialog._format_age(seconds) == surface.format_age(
        seconds
    )


def test_an_age_that_cannot_be_measured_refuses_the_same_way():
    """One side printed an age where the other refused."""
    for seconds in REFUSING_AGES:
        old_refusal = refusal_of(
            lambda seconds=seconds: shipped.BotLiveSettingsDialog._format_age(seconds)
        )
        new_refusal = refusal_of(lambda seconds=seconds: surface.format_age(seconds))
        assert old_refusal is not None, seconds
        assert old_refusal == new_refusal, seconds
    assert (
        len({refusal_of(lambda s=s: surface.format_age(s)) for s in REFUSING_AGES}) > 1
    )


def test_an_unbounded_age_prints_the_same_words_on_both_sides():
    """One side printed a bounded age where the other printed a word."""
    for seconds in (float("inf"), float("nan")):
        assert shipped.BotLiveSettingsDialog._format_age(seconds) == surface.format_age(
            seconds
        )


# ---------------------------------------------------------------------
# The size the window opens at
# ---------------------------------------------------------------------

SIZE_CASES = {
    "content_fits": (700, 800, 400, 300, 1000, 2000, 1920, 1080),
    "content_is_taller_than_the_screen": (700, 800, 400, 300, 1000, 9000, 1920, 1080),
    "nothing_asked_for": (0, 0, 0, 0, 0, 0, 1920, 1080),
    "tiny_display": (700, 800, 400, 300, 1000, 2000, 300, 300),
    "unbounded_display": (700, 800, 400, 300, 1977, 2789, 4000, 4000),
    "negative_content": (700, 800, 400, 300, -50, -50, 1920, 1080),
}


SIZE_CASE_NAMES = tuple(sorted(SIZE_CASES))


@pytest.mark.parametrize("name", SIZE_CASE_NAMES)
def test_the_opening_size_is_the_shipped_size(name):
    """The window opens at a different size than the shipped window."""
    hint_w, hint_h, page_w, page_h, content_w, content_h, screen_w, screen_h = (
        SIZE_CASES[name]
    )
    old_needed = shipped.dialog_content_size_px(
        hint_w, hint_h, page_w, page_h, content_w, content_h
    )
    new_needed = surface.dialog_content_size_px(
        hint_w, hint_h, page_w, page_h, content_w, content_h
    )
    assert old_needed == new_needed, name
    assert shipped.dialog_open_size_px(
        old_needed[0], old_needed[1], screen_w, screen_h, 640, 720
    ) == surface.dialog_open_size_px(
        new_needed[0], new_needed[1], screen_w, screen_h, 640, 720
    ), name


def test_every_size_case_in_the_table_is_driven():
    """A size case sits in the table and no test ever drives it."""
    assert undriven(SIZE_CASES, SIZE_CASE_NAMES) == []


def test_the_screen_margins_are_the_shipped_margins():
    """The window is given a different margin than the shipped window."""
    assert (
        shipped.DIALOG_SCREEN_MARGIN_W_PX
        == surface.DIALOG_SCREEN_MARGIN_W_PX
        == surface.build_view_model(surface.build_model())["screen_margin_w_px"]
    )
    assert (
        shipped.DIALOG_SCREEN_MARGIN_H_PX
        == surface.DIALOG_SCREEN_MARGIN_H_PX
        == surface.build_view_model(surface.build_model())["screen_margin_h_px"]
    )


def test_the_tab_demand_is_read_the_same_way_on_both_sides():
    """The two sides read a different demand off the same tabs."""
    from PySide6.QtWidgets import QLabel, QScrollArea, QTabWidget

    app()
    tabs = hold(QTabWidget())
    pages = []
    for width, height in ((300, 200), (900, 1400), (120, 90)):
        content = QLabel("x")
        content.setFixedSize(width, height)
        wrapper = QScrollArea()
        wrapper.setWidgetResizable(True)
        wrapper.setWidget(content)
        tabs.addTab(wrapper, "t%d" % width)
        wrapper.ensurePolished()
        content.ensurePolished()
        pages.append(
            (
                (content.sizeHint().width(), content.sizeHint().height()),
                (wrapper.sizeHint().width(), wrapper.sizeHint().height()),
            )
        )
    assert shipped.tab_content_demand_px(tabs) == surface.tab_content_demand_px(pages)
    assert surface.tab_content_demand_px(()) == (0, 0, 0, 0)
    assert surface.tab_content_demand_px([None]) == (0, 0, 0, 0)


# ---------------------------------------------------------------------
# One edit, and what the window does with it
# ---------------------------------------------------------------------


def old_edited(name, steps):
    """The shipped window after one run of edits."""
    window = old_window_for(name)
    for field, value in steps:
        window._mark_changed(field, value)
    return window


def new_edited(name, steps):
    """The surface's window after the same run of edits."""
    model = new_model_for(name, SHIPPED_CONFIG_FIELDS)
    for field, value in steps:
        model.mark_changed(field, value)
    return model


EDIT_RUNS = {
    "one_field": (("target_balance", 250.0),),
    "same_value": (("target_balance", 100.0),),
    "two_fields": (("target_balance", 250.0), ("visibility", "internal")),
    "edit_then_revert": (("target_balance", 250.0), ("target_balance", 100.0)),
    "unknown_field": (("no_such_field", 5),),
    "text_where_number": (("target_balance", "20.0"),),
    "number_where_text": (("visibility", 12),),
    "not_a_number": (("target_balance", float("nan")),),
    "infinity": (("target_balance", float("inf")),),
    "minus_infinity": (("target_balance", float("-inf")),),
    "one_billionth": (("target_balance", 0.000_000_001),),
    "thousand_million": (("target_balance", 1_000_000_000.0),),
    "negative": (("target_balance", -1.0),),
    "unicode": (("visibility", UNICODE_ASSET),),
    "markup": (("visibility", "<b>on</b>"),),
    "apostrophe": (("visibility", APOSTROPHE_ASSET),),
    "newline": (("visibility", "two\nlines"),),
    "long_two_hundred": (("visibility", "y" * 200),),
    "empty": (("visibility", ""),),
    "zero": (("target_balance", 0.0),),
    "three_then_two_back": (
        ("target_balance", 250.0),
        ("visibility", "internal"),
        ("target_balance", 100.0),
        ("visibility", "orderbook"),
    ),
}


EDIT_RUN_NAMES = tuple(sorted(EDIT_RUNS))


@pytest.mark.parametrize("run", EDIT_RUN_NAMES)
def test_one_run_of_edits_leaves_the_same_pending_line(run):
    """The two sides report a different pending change to the operator."""
    steps = EDIT_RUNS[run]
    old_side = read_old(old_edited("happy", steps))
    new_side = read_new(new_edited("happy", steps))
    for key in ("change_label", "change_style", "apply_enabled", "changes"):
        assert readable(old_side[key]) == readable(new_side[key]), "%s %s" % (run, key)
    assert digest(old_side) == digest(new_side), run


def test_every_edit_run_in_the_table_is_driven():
    """An edit run sits in the table and no test ever drives it."""
    assert undriven(EDIT_RUNS, EDIT_RUN_NAMES) == []


def test_a_phantom_field_is_read_off_the_bot_not_the_config():
    """A phantom edit compared against the config, which never holds it."""
    window = old_window_for("happy")
    window._bot._phantoms_enabled = True
    window._bot._phantom_timeframes = ["1m", "5m"]
    window._bot._coordinator = ModeValue("x")
    window._bot._coordinator.lock_candle_count = 3
    model = new_model_for("happy")
    model.bot = surface.BotSource(
        config=surface.BotConfigSource(),
        runtime={
            surface.PHANTOM_ENABLE_ATTRIBUTE: True,
            surface.PHANTOM_TIMEFRAMES_ATTRIBUTE: ["1m", "5m"],
            surface.COORDINATOR_ATTRIBUTE: Coordinator(3),
        },
    )
    for field, value in (
        ("enable_phantoms", True),
        ("enable_phantoms", False),
        ("phantom_timeframes", ["1m", "5m"]),
        ("phantom_timeframes", ("1m", "5m")),
        ("phantom_timeframes", ["1m"]),
        ("lock_candle_count", 3),
        ("lock_candle_count", 9),
    ):
        window._mark_changed(field, value)
        model.mark_changed(field, value)
        assert readable(dict(window._changes)) == readable(
            surface.build_view_model(model)["changes"]
        ), field
    assert window._changes != {}


class Coordinator:
    """The phantom coordinator, holding only the reading the window asks for."""

    def __init__(self, lock_candle_count):
        self.lock_candle_count = lock_candle_count


def test_a_lock_edit_with_no_coordinator_is_recorded_on_both_sides():
    """One side found a lock value where the other found no coordinator."""
    window = old_window_for("happy")
    window._bot._coordinator = None
    model = new_model_for("happy")
    model.bot = surface.BotSource(config=surface.BotConfigSource())
    window._mark_changed("lock_candle_count", 9)
    model.mark_changed("lock_candle_count", 9)
    assert readable(dict(window._changes)) == readable(
        surface.build_view_model(model)["changes"]
    )
    assert window._changes == {"lock_candle_count": 9}


# ---------------------------------------------------------------------
# Applying edits, including the routes that refuse
# ---------------------------------------------------------------------


class Sent:
    """The signal the window sends when edits are applied."""

    def __init__(self):
        self.sent: list = []

    def emit(self, bot_id, changes):
        self.sent.append([bot_id, dict(changes)])


APPLY_RUNS = {
    "plain_field": {
        "changes": {"visibility": "internal"},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "routed_applied": {
        "changes": {"target_balance": 250.0},
        "routes": {"set_target_balance_live": {"applied": True}},
        "config": {"target_balance": 100.0},
    },
    "routed_refused": {
        "changes": {"target_balance": 250.0},
        "routes": {
            "set_target_balance_live": {"applied": False, "reason": "below floor"}
        },
        "config": {"target_balance": 100.0},
    },
    "routed_refused_without_a_reason": {
        "changes": {"target_balance": 250.0},
        "routes": {"set_target_balance_live": {"applied": False}},
        "config": {"target_balance": 100.0},
    },
    "routed_raised": {
        "changes": {"target_balance": 250.0},
        "routes": {"set_target_balance_live": ValueError("nope")},
        "config": {"target_balance": 100.0},
    },
    "route_absent": {
        "changes": {"target_balance": 250.0},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "unknown_field": {"changes": {"no_such_field": 5}, "routes": {}, "config": {}},
    "nothing_pending": {"changes": {}, "routes": {}, "config": {}},
    "two_fields": {
        "changes": {"visibility": "internal", "hedge_balance": 5.0},
        "routes": {"set_hedge_balance_live": {"applied": True}},
        "config": {"visibility": "orderbook", "hedge_balance": 200.0},
    },
    "text_where_number": {
        "changes": {"target_balance": "20.0"},
        "routes": {"set_target_balance_live": {"applied": True}},
        "config": {"target_balance": 100.0},
    },
    "not_a_number": {
        "changes": {"target_balance": float("nan")},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "infinity": {
        "changes": {"target_balance": float("inf")},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "minus_infinity": {
        "changes": {"target_balance": float("-inf")},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "zero": {
        "changes": {"target_balance": 0.0},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "negative": {
        "changes": {"target_balance": -1.0},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "thousand_million": {
        "changes": {"target_balance": 1_000_000_000.0},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "one_billionth": {
        "changes": {"target_balance": 0.000_000_001},
        "routes": {},
        "config": {"target_balance": 100.0},
    },
    "unicode": {
        "changes": {"visibility": UNICODE_ASSET},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "markup": {
        "changes": {"visibility": "<b>on</b>"},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "apostrophe": {
        "changes": {"visibility": APOSTROPHE_ASSET},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "newline": {
        "changes": {"visibility": "two\nlines"},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "long_two_hundred": {
        "changes": {"visibility": "y" * 200},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "empty": {
        "changes": {"visibility": ""},
        "routes": {},
        "config": {"visibility": "orderbook"},
    },
    "phantom_applied": {
        "changes": {"enable_phantoms": True},
        "routes": {},
        "config": {},
        "phantom": {"applied": {"enable_phantoms": True}, "caveats": ["restart"]},
    },
    "phantom_raised": {
        "changes": {"enable_phantoms": True},
        "routes": {},
        "config": {},
        "phantom_raises": RuntimeError("bad"),
    },
    "phantom_without_a_method": {
        "changes": {"enable_phantoms": True},
        "routes": {},
        "config": {},
    },
    "phantom_and_a_plain_field": {
        "changes": {"enable_phantoms": True, "visibility": "internal"},
        "routes": {},
        "config": {"visibility": "orderbook"},
        "phantom": {"applied": {"enable_phantoms": True}, "caveats": []},
    },
}


class AppliedBot:
    """A bot that answers the live-update methods one apply run names."""

    def __init__(self, run):
        self.bot_id = PLAIN_BOT_ID
        self.config = AppliedConfig(run["config"])
        self.route_calls: list = []
        self.phantom_calls: list = []
        self._routes = dict(run["routes"])
        self._phantom = run.get("phantom")
        self._phantom_raises = run.get("phantom_raises")
        for name in self._routes:
            setattr(self, name, self._runner(name))
        if self._phantom is not None or self._phantom_raises is not None:
            self.update_phantom_config = self._phantom_update

    def _runner(self, name):
        def run(value):
            self.route_calls.append([name, value])
            answer = self._routes[name]
            if isinstance(answer, BaseException):
                raise answer
            return answer

        return run

    def _phantom_update(self, **changes):
        self.phantom_calls.append(dict(changes))
        if self._phantom_raises is not None:
            raise self._phantom_raises
        return dict(self._phantom or {})


class AppliedConfig:
    """The config an apply run writes onto.

    Carries the pair and the mode the surface's config carries, so both
    sides start from one set of fields and an extra write is reported.
    """

    def __init__(self, fields):
        self.symbol = "CHIP/USD"
        self.mode = "scrumming"
        for name, value in fields.items():
            setattr(self, name, value)


def old_applied(run):
    """The shipped window driven through one apply run."""
    window = old_window_for("happy")
    window._bot = AppliedBot(run)
    window._changes = dict(run["changes"])
    window.settings_changed = Sent()
    window._apply_changes()
    return window


def new_applied(run):
    """The surface's window driven through the same apply run."""
    model = new_model_for("happy")
    model.bot = surface.BotSource(
        config=surface.BotConfigSource(fields=run["config"]),
        bot_id=PLAIN_BOT_ID,
        routes=run["routes"],
        phantom_answer=run.get("phantom"),
        phantom_raises=run.get("phantom_raises"),
        with_phantom_update=(
            run.get("phantom") is not None or run.get("phantom_raises") is not None
        ),
    )
    model.changes = dict(run["changes"])
    model.apply_changes()
    return model


def read_old_applied(window):
    """What the shipped window shows and sends after an apply."""
    return {
        "change_label": window._change_lbl.text(),
        "change_style": window._change_lbl.styleSheet(),
        "apply_enabled": window._apply_btn.isEnabled(),
        "changes": dict(window._changes),
        "sent": [list(one) for one in window.settings_changed.sent],
        "routes": [list(one) for one in window._bot.route_calls],
        "phantoms": [dict(one) for one in window._bot.phantom_calls],
        "config": {
            name: value
            for name, value in vars(window._bot.config).items()
            if not name.startswith("_")
        },
    }


def read_new_applied(model):
    """What the surface's window shows and sends after the same apply."""
    payload = surface.build_view_model(model)
    return {
        "change_label": payload["change_label"],
        "change_style": payload["change_style"],
        "apply_enabled": payload["apply_enabled"],
        "changes": payload["changes"],
        "sent": payload["sent"],
        "routes": [list(one) for one in model.bot.route_calls],
        "phantoms": [dict(one) for one in model.bot.phantom_calls],
        "config": {
            name: value
            for name, value in vars(model.bot.config).items()
            if not name.startswith("_")
        },
    }


APPLY_RUN_NAMES = tuple(sorted(APPLY_RUNS))


@pytest.mark.parametrize("run", APPLY_RUN_NAMES)
def test_one_apply_run_reaches_the_same_bot_the_same_way(run):
    """The two sides sent a different edit to the bot, or told the operator so."""
    old_side = read_old_applied(old_applied(APPLY_RUNS[run]))
    new_side = read_new_applied(new_applied(APPLY_RUNS[run]))
    differences = [
        key
        for key in sorted(old_side)
        if readable(old_side[key]) != readable(new_side[key])
    ]
    assert differences == [], "%s: old %r new %r" % (
        run,
        {key: old_side[key] for key in differences},
        {key: new_side[key] for key in differences},
    )
    assert digest(old_side) == digest(new_side), run


def test_every_apply_run_in_the_table_is_driven():
    """An apply run sits in the table and no test ever drives it."""
    assert undriven(APPLY_RUNS, APPLY_RUN_NAMES) == []
    assert len(APPLY_RUNS) >= 25, len(APPLY_RUNS)


def test_the_apply_comparison_reports_a_run_that_went_differently():
    """The apply comparison passes whatever the surface sends."""
    old_side = read_old_applied(old_applied(APPLY_RUNS["plain_field"]))
    new_side = read_new_applied(new_applied(APPLY_RUNS["unknown_field"]))
    assert digest(old_side) != digest(new_side)
    assert readable(old_side["sent"]) != readable(new_side["sent"])
    other = read_new_applied(new_applied(APPLY_RUNS["two_fields"]))
    assert digest(old_side) != digest(other)


def test_a_refused_route_looks_the_same_to_the_operator_as_an_applied_one():
    """The window tells the operator apart a refused change from an applied one.

    The bot answered ``applied: False`` with a reason, and the window
    still counted it and wrote the applied line in the applied colour.
    Nothing the operator can see differs from a change that landed. Both
    sides do this, so the two hashes match; the reason reaches the log
    line only.
    """
    applied_side = read_old_applied(old_applied(APPLY_RUNS["routed_applied"]))
    refused_side = read_old_applied(old_applied(APPLY_RUNS["routed_refused"]))
    assert digest(applied_side) == digest(refused_side)
    assert applied_side["change_label"] == refused_side["change_label"]
    assert applied_side["change_style"] == refused_side["change_style"]
    assert "REFUSED" not in refused_side["change_label"]
    assert digest(
        read_new_applied(new_applied(APPLY_RUNS["routed_refused"]))
    ) == digest(refused_side)
    refused_model = new_applied(APPLY_RUNS["routed_refused"])
    assert [line[0] for line in refused_model.logged] == [
        surface.ROUTE_REFUSED_LOG,
        surface.APPLIED_LOG,
    ]
    assert "below floor" in refused_model.applied[0]


def test_an_apply_after_a_refused_edit_still_clears_the_pending_line():
    """A refused route left the window saying the edit is still pending."""
    window = old_applied(APPLY_RUNS["routed_refused"])
    model = new_applied(APPLY_RUNS["routed_refused"])
    assert window._changes == {}
    assert surface.build_view_model(model)["changes"] == {}
    assert window._change_lbl.text() == surface.build_view_model(model)["change_label"]
    assert window._apply_btn.isEnabled() is False


# ---------------------------------------------------------------------
# Step sequences, including one that refuses part way
# ---------------------------------------------------------------------

STEP_RUNS = {
    "edit_apply_edit": (
        ("mark", "visibility", "internal"),
        ("apply", None, None),
        ("mark", "visibility", "orderbook"),
    ),
    "edit_apply_apply": (
        ("mark", "visibility", "internal"),
        ("apply", None, None),
        ("apply", None, None),
    ),
    "apply_with_nothing_pending": (("apply", None, None),),
    "edit_revert_apply": (
        ("mark", "visibility", "internal"),
        ("mark", "visibility", "orderbook"),
        ("apply", None, None),
    ),
    "edit_refuse_edit": (
        ("mark", "visibility", "internal"),
        ("mark", "age", "abc"),
        ("mark", "visibility", "orderbook"),
    ),
}


def old_stepped(steps):
    """The shipped window driven through one step sequence."""
    window = old_window_for("happy")
    window._bot = AppliedBot(
        {"changes": {}, "routes": {}, "config": {"visibility": "orderbook"}}
    )
    window.settings_changed = Sent()
    refusals = []
    for kind, field, value in steps:
        try:
            if kind == "mark":
                if field == "age":
                    shipped.BotLiveSettingsDialog._format_age(value)
                else:
                    window._mark_changed(field, value)
            else:
                window._apply_changes()
        except Exception as exc:
            refusals.append(type(exc).__name__)
    return window, refusals


def new_stepped(steps):
    """The surface's window driven through the same step sequence."""
    model = new_model_for("happy")
    model.bot = surface.BotSource(
        config=surface.BotConfigSource(fields={"visibility": "orderbook"}),
        bot_id=PLAIN_BOT_ID,
    )
    refusals = []
    for kind, field, value in steps:
        try:
            if kind == "mark":
                if field == "age":
                    surface.format_age(value)
                else:
                    model.mark_changed(field, value)
            else:
                model.apply_changes()
        except Exception as exc:
            refusals.append(type(exc).__name__)
    return model, refusals


STEP_RUN_NAMES = tuple(sorted(STEP_RUNS))


@pytest.mark.parametrize("run", STEP_RUN_NAMES)
def test_a_step_sequence_leaves_both_sides_in_one_state(run):
    """A sequence of steps left the two sides showing different things."""
    old_window_after, old_refusals = old_stepped(STEP_RUNS[run])
    new_model_after, new_refusals = new_stepped(STEP_RUNS[run])
    assert old_refusals == new_refusals, run
    old_side = read_old_applied(old_window_after)
    new_side = read_new_applied(new_model_after)
    assert digest(old_side) == digest(new_side), "%s: old %r new %r" % (
        run,
        old_side,
        new_side,
    )


def test_every_step_run_in_the_table_is_driven():
    """A step run sits in the table and no test ever drives it."""
    assert undriven(STEP_RUNS, STEP_RUN_NAMES) == []


def test_a_sequence_that_refuses_part_way_still_holds_the_earlier_edits():
    """A refusal mid-run threw away the edits taken before it."""
    _window, refusals = old_stepped(STEP_RUNS["edit_refuse_edit"])
    assert refusals == ["TypeError"], refusals
    _model, new_refusals = new_stepped(STEP_RUNS["edit_refuse_edit"])
    assert new_refusals == refusals


def test_the_sequence_check_reports_a_step_that_went_differently():
    """The sequence check passes whatever the surface does in the middle."""
    old_side = read_old_applied(old_stepped(STEP_RUNS["edit_apply_edit"])[0])
    new_side = read_new_applied(new_stepped(STEP_RUNS["apply_with_nothing_pending"])[0])
    assert digest(old_side) != digest(new_side)


# ---------------------------------------------------------------------
# Walking the swarm
# ---------------------------------------------------------------------

NAVIGATE_RUNS = {
    "next_from_the_first": (("bot-a", "bot-b", "bot-c"), "bot-a", 1),
    "prev_from_the_first": (("bot-a", "bot-b", "bot-c"), "bot-a", -1),
    "next_from_the_last": (("bot-a", "bot-b", "bot-c"), "bot-c", 1),
    "prev_from_the_last": (("bot-a", "bot-b", "bot-c"), "bot-c", -1),
    "two_bots_next": (("bot-a", "bot-b"), "bot-a", 1),
    "two_bots_prev": (("bot-a", "bot-b"), "bot-a", -1),
    "one_bot": (("bot-a",), "bot-a", 1),
    "no_bots": ((), "bot-a", 1),
    "bot_left_the_fleet_next": (("bot-b", "bot-c"), "bot-a", 1),
    "bot_left_the_fleet_prev": (("bot-b", "bot-c"), "bot-a", -1),
}


NAVIGATE_RUN_NAMES = tuple(sorted(NAVIGATE_RUNS))


@pytest.mark.parametrize("run", NAVIGATE_RUN_NAMES)
def test_one_walk_of_the_swarm_lands_on_the_same_bot(run):
    """The two sides moved the operator to a different bot."""
    ids, here, direction = NAVIGATE_RUNS[run]
    window = old_window(spec(bot_id=here), Manager(ids))
    window._navigate_to_sibling(direction)
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource(), bot_id=here),
        surface.BotManagerSource(ids),
    )
    model.build()
    model.navigate_to_sibling(direction)
    payload = surface.build_view_model(model)
    assert window._pending_navigate_to == payload["pending_navigate_to"], run
    assert list(window._sibling_bot_ids()) == payload["siblings"], run


def test_every_walk_in_the_table_is_driven():
    """A walk sits in the table and no test ever drives it."""
    assert undriven(NAVIGATE_RUNS, NAVIGATE_RUN_NAMES) == []


def test_the_walk_check_reports_two_different_landings():
    """The walk check passes whatever bot the surface lands on."""
    ids = ("bot-a", "bot-b", "bot-c")
    window = old_window(spec(bot_id="bot-a"), Manager(ids))
    window._navigate_to_sibling(1)
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource(), bot_id="bot-a"),
        surface.BotManagerSource(ids),
    )
    model.build()
    model.navigate_to_sibling(-1)
    assert (
        window._pending_navigate_to
        != surface.build_view_model(model)["pending_navigate_to"]
    )


def test_a_manager_that_cannot_list_its_bots_leaves_both_sides_alone():
    """One side crashed where the other reported no siblings."""
    window = old_window(spec(), Manager(ids_raise=RuntimeError("register gone")))
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()),
        surface.BotManagerSource(ids_raise=RuntimeError("register gone")),
    )
    model.build()
    payload = surface.build_view_model(model)
    assert window._sibling_bot_ids() == payload["siblings"] == []
    assert window._prev_btn.isVisibleTo(window) is payload["nav_shown"] is False


def test_the_sibling_reader_reports_a_real_list():
    """The sibling reader answers empty whatever the manager holds."""
    window = old_window(spec(), Manager(("bot-a", "bot-b")))
    assert window._sibling_bot_ids() == ["bot-a", "bot-b"]
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()),
        surface.BotManagerSource(("bot-a", "bot-b")),
    )
    assert model.sibling_bot_ids() == ["bot-a", "bot-b"]


def test_the_prev_and_next_buttons_step_the_way_the_window_names_them():
    """A button moved the operator the wrong way round the swarm."""
    ids = ("bot-a", "bot-b", "bot-c")
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource(), bot_id="bot-b"),
        surface.BotManagerSource(ids),
    )
    model.build()
    model.navigate_to_next()
    assert model.pending_navigate_to == "bot-c"
    model.navigate_to_prev()
    assert model.pending_navigate_to == "bot-a"
    assert surface.PREV_STEP == -1
    assert surface.NEXT_STEP == 1


# ---------------------------------------------------------------------
# Saving the fleet in this click
# ---------------------------------------------------------------------

SAVE_RUNS = {
    "manager_on_the_window": ("window", None),
    "manager_on_the_bot": ("bot", None),
    "no_manager": ("none", None),
    "manager_without_a_save": ("no_save", None),
    "save_raises": ("window", RuntimeError("disk gone")),
    "save_raises_with_no_message": ("window", ValueError("")),
}


SAVE_RUN_NAMES = tuple(sorted(SAVE_RUNS))


@pytest.mark.parametrize("run", SAVE_RUN_NAMES)
def test_one_save_reports_the_same_answer_on_both_sides(run):
    """One side said the fleet was saved where the other said it was not."""
    where, raises = SAVE_RUNS[run]
    manager = None if where in ("none",) else Manager(save_raises=raises)
    if where == "no_save":
        manager = Manager(can_save=False)
    window = old_window_for("happy")
    window._bm = manager if where == "window" else None
    if where == "bot":
        window._bot._bot_manager = manager
    new_manager = (
        None
        if manager is None
        else surface.BotManagerSource(save_raises=raises, can_save=(where != "no_save"))
    )
    model = surface.BotLiveSettingsModel(
        surface.BotSource(
            config=surface.BotConfigSource(),
            manager=new_manager if where == "bot" else surface.NO_MANAGER,
        ),
        new_manager if where == "window" else None,
    )
    assert window._save_fleet_state_now("Fold tranches") == model.save_fleet_state_now(
        "Fold tranches"
    ), run


def test_every_save_run_in_the_table_is_driven():
    """A save run sits in the table and no test ever drives it."""
    assert undriven(SAVE_RUNS, SAVE_RUN_NAMES) == []


def test_the_save_check_reports_two_different_answers():
    """The save check passes whatever the surface answers."""
    saved = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()),
        surface.BotManagerSource(),
    ).save_fleet_state_now("x")
    refused = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource())
    ).save_fleet_state_now("x")
    assert saved != refused
    assert saved == (True, "")


def test_the_window_prefers_its_own_manager_over_the_bots():
    """The window reached past the manager it was handed."""
    window_manager = Manager()
    bot_manager = Manager()
    window = old_window_for("happy")
    window._bm = window_manager
    window._bot._bot_manager = bot_manager
    assert window._bot_manager_for_save() is window_manager
    on_bot = surface.BotManagerSource()
    on_window = surface.BotManagerSource()
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource(), manager=on_bot), on_window
    )
    assert model.bot_manager_for_save() is on_window


def test_the_window_falls_back_to_the_bots_manager():
    """The window found no manager where the bot carried one."""
    bot_manager = Manager()
    window = old_window_for("happy")
    window._bm = None
    window._bot._bot_manager = bot_manager
    assert window._bot_manager_for_save() is bot_manager
    on_bot = surface.BotManagerSource()
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource(), manager=on_bot)
    )
    assert model.bot_manager_for_save() is on_bot


# ---------------------------------------------------------------------
# The surface writes out its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    before = shipped.ds.PRIMARY
    kept_style = surface.HEADER_STYLE_FORMAT.format(color_hex=surface.HEADER_COLOR)
    shipped.ds.PRIMARY = "#123456"
    try:
        moved = read_old(old_window_for("happy"))
        kept = read_new(new_model_for("happy"))
        assert "#123456" in moved["header_style"]
        assert kept["header_style"] == kept_style
        assert "#123456" not in kept["header_style"]
        differences = [
            key
            for key in sorted(set(moved) & set(kept))
            if readable(moved[key]) != readable(kept[key])
        ]
        assert differences == [
            "apply_style",
            "header_style",
            "nav_style",
            "next_style",
        ], differences
    finally:
        shipped.ds.PRIMARY = before
    both_sides_agree("happy", "after the value was put back")


def test_the_shipped_file_is_not_named_by_the_surface():
    """The surface reaches into the window it replaces."""
    imported = imports_of(SURFACE_PATH)
    assert not any("bot_live_settings" == name for name in imported), imported
    assert not any("live_settings" in name for name in imported), imported


def imports_of(path):
    """Every module name one file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found.update(alias.name for alias in node.names)
    return found


# ---------------------------------------------------------------------
# Counting what the shipped file wires, waits on, and builds
# ---------------------------------------------------------------------

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
    "QTabWidget",
)


def count_text(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, names):
    """How many times one file constructs any of `names`."""
    text = path.read_text(encoding="utf-8")
    return sum(len(re.findall(r"\b%s\s*\(" % name, text)) for name in names)


def declared_classes(path):
    """Every class one file declares, wherever it is declared."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def declared_widget_classes(path):
    """Every class one file declares that ends up being a screen element."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
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
    return count_built(path, WIDGET_NAMES_BUILT) + len(declared_widget_classes(path))


def test_the_window_wires_four_actions_and_the_surface_names_four():
    """A wiring appeared on one side and not the other."""
    assert count_text(WINDOW_PATH, ".connect(") == WINDOW_CONNECT_SITES == 4
    assert count_text(SURFACE_PATH, ".connect(") == 0
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES == 1
    assert len(surface.ACTIONS) == count_text(WINDOW_PATH, ".connect(")
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.BotLiveSettingsModel, name)), name


def test_the_window_builds_no_timer_of_its_own():
    """A wait appeared on one side and not the other.

    The window file builds no timer. The window it composes does start
    one, from the Settings tab it hosts, so the watcher below names the
    file the timer came from rather than reporting a bare count.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(WINDOW_PATH, timer_names) == WINDOW_TIMER_BUILDS == 0
    assert count_built(SURFACE_PATH, timer_names) == 0
    assert count_built(TIMER_CONTROL_PATH, timer_names) == CONTROL_TIMER_BUILDS == 1
    assert count_text(TIMER_CONTROL_PATH, "QTimer") > CONTROL_TIMER_BUILDS
    started: list = []
    first_start = QObject.startTimer
    first_timer = QTimer.start
    first_single = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", where_from()))
        return first_start(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", where_from()))
        return first_timer(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", where_from()))
        return first_single(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        old_window_for("happy")
        old_started = list(started)
        started.clear()
        new_model_for("happy")
        new_started = list(started)
        started.clear()
        control = QTimer()
        control.start(5)
        control.stop()
        control_started = list(started)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert [name for name, _where in old_started] == ["QTimer.start"], old_started
    assert [where for _name, where in old_started] == [
        "src/gui/live_settings/settings_tab.py"
    ], old_started
    assert new_started == []
    assert control_started == [("QTimer.start", OUTSIDE_SRC)], control_started
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == WINDOW_TIMER_BUILDS


OUTSIDE_SRC = ""


def where_from():
    """The file under src that called into the timer, or none of them.

    Read by walking the stack for the nearest frame under ``src``, so a
    call from a test reports no source file and a call from a tab
    reports that tab.
    """
    import traceback

    source = REPO_ROOT / "src"
    for frame in reversed(traceback.extract_stack()):
        found = Path(frame.filename).resolve()
        if found.is_relative_to(source):
            return found.relative_to(REPO_ROOT).as_posix()
    return OUTSIDE_SRC


def test_the_window_declares_one_signal_and_the_surface_names_it():
    """A signal declaration appeared on one side and not the other."""
    from PySide6.QtCore import Signal

    app()
    signal_names = ("Signal",)
    assert count_built(WINDOW_PATH, signal_names) == WINDOW_SIGNAL_BUILDS == 1
    assert count_built(SURFACE_PATH, signal_names) == 0
    assert count_built(SIGNAL_CONTROL_PATH, signal_names) == CONTROL_SIGNAL_BUILDS == 3
    assert count_text(SIGNAL_CONTROL_PATH, "Signal") > CONTROL_SIGNAL_BUILDS
    declared = vars(shipped.BotLiveSettingsDialog)[surface.SIGNAL_NAME]
    assert isinstance(declared, Signal)
    assert surface.SIGNAL_NAME == "settings_changed"


def test_the_window_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(WINDOW_PATH, ".subscribe(") == WINDOW_BUS_SITES == 0
    assert count_text(SURFACE_PATH, ".subscribe(") == 0
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_text(WINDOW_PATH, ".subscribe(")


def test_the_screen_elements_the_window_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(WINDOW_PATH) == WINDOW_ELEMENT_BUILDS == 10
    assert count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert declared_widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert declared_widget_classes(WINDOW_PATH) == {"BotLiveSettingsDialog"}
    assert count_built(WINDOW_PATH, WIDGET_NAMES_BUILT) == 9
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == set()


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(NESTED_CLASS_CONTROL_PATH)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    top_level = {
        node.name
        for node in ast.parse(
            NESTED_CLASS_CONTROL_PATH.read_text(encoding="utf-8")
        ).body
        if isinstance(node, ast.ClassDef)
    }
    assert top_level == set(), top_level
    assert declared_classes(WINDOW_PATH) == {"BotLiveSettingsDialog"}
    assert {
        node.name
        for node in ast.parse(WINDOW_PATH.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
    } == set()


# ---------------------------------------------------------------------
# Every class and every method has a counterpart
# ---------------------------------------------------------------------


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A signal is callable and is not a method, so it is excluded by name.
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


def test_the_member_counter_excludes_a_signal_and_finds_both_quiet_shapes():
    """The counter counts a signal, or misses a factory or a read-only value."""
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
    assert surface.SIGNAL_NAME not in members(shipped.BotLiveSettingsDialog)


CLASS_MAP = {"BotLiveSettingsDialog": "BotLiveSettingsModel"}

METHOD_MAP = {
    "BotLiveSettingsDialog.__init__": "BotLiveSettingsModel.build",
    "BotLiveSettingsDialog.open_at_content_size": (
        "BotLiveSettingsModel.open_at_content_size"
    ),
    "BotLiveSettingsDialog._sibling_bot_ids": "BotLiveSettingsModel.sibling_bot_ids",
    "BotLiveSettingsDialog._navigate_to_sibling": (
        "BotLiveSettingsModel.navigate_to_sibling"
    ),
    "BotLiveSettingsDialog.active_tab_index": "BotLiveSettingsModel.active_tab_index",
    "BotLiveSettingsDialog._wrap_scrollable": "BotLiveSettingsModel.wrap_scrollable",
    "BotLiveSettingsDialog._configure_form": "BotLiveSettingsModel.configure_form",
    "BotLiveSettingsDialog._mark_changed": "BotLiveSettingsModel.mark_changed",
    "BotLiveSettingsDialog._apply_changes": "BotLiveSettingsModel.apply_changes",
    "BotLiveSettingsDialog._bot_manager_for_save": (
        "BotLiveSettingsModel.bot_manager_for_save"
    ),
    "BotLiveSettingsDialog._save_fleet_state_now": (
        "BotLiveSettingsModel.save_fleet_state_now"
    ),
    "BotLiveSettingsDialog._format_age": "format_age",
}

FUNCTION_MAP = {
    "tab_content_demand_px": "tab_content_demand_px",
    "dialog_content_size_px": "dialog_content_size_px",
    "dialog_open_size_px": "dialog_open_size_px",
}

HELPER_MAP = {
    "prev_button": "BotLiveSettingsModel.navigate_to_prev",
    "next_button": "BotLiveSettingsModel.navigate_to_next",
    "close_button": "BotLiveSettingsModel.accept",
    "shortcut_wiring": "BotLiveSettingsModel.install_shortcuts",
    "phantom_route": "BotLiveSettingsModel.send_phantom",
    "one_field_route": "BotLiveSettingsModel.send_one",
    "pending_original": "BotLiveSettingsModel.original_value",
    "window_title_words": "window_title",
    "header_words": "header_text",
    "state_words": "state_text",
    "state_colours": "state_style",
    "tabs_by_mode": "tabs_for_mode",
    "pending_line": "pending_text",
    "applied_line": "applied_text",
    "bot_stand_in": "BotSource",
    "config_stand_in": "BotConfigSource",
    "manager_stand_in": "BotManagerSource",
    "model_from_a_bot": "build_model",
    "shared_window": "pane_model",
    "whole_state": "build_view_model",
    "bridge_handler": "view_model",
}

MODEL_MEMBERS = {
    "__init__",
    "build",
    "install_shortcuts",
    "open_at_content_size",
    "wrap_scrollable",
    "configure_form",
    "sibling_bot_ids",
    "navigate_to_sibling",
    "navigate_to_prev",
    "navigate_to_next",
    "accept",
    "active_tab_index",
    "original_value",
    "mark_changed",
    "apply_changes",
    "send_phantom",
    "send_one",
    "bot_manager_for_save",
    "save_fleet_state_now",
}


def resolve(dotted):
    """The member a dotted name in a map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_classes():
    """Every class the shipped module declares, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def shipped_functions():
    """Every function the shipped module declares, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """A class, a method or a function exists on one side and not the other."""
    app()
    assert shipped_classes() == set(CLASS_MAP)
    assert shipped_functions() == set(FUNCTION_MAP), sorted(
        shipped_functions() ^ set(FUNCTION_MAP)
    )
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 12
    for target in (
        set(METHOD_MAP.values())
        | set(CLASS_MAP.values())
        | set(FUNCTION_MAP.values())
        | set(HELPER_MAP.values())
    ):
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 21
    assert members(surface.BotLiveSettingsModel) == MODEL_MEMBERS, sorted(
        members(surface.BotLiveSettingsModel) ^ MODEL_MEMBERS
    )
    assert len(MODEL_MEMBERS) == 19
    assert declared_classes(WINDOW_PATH) == set(CLASS_MAP)


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "_apply_changes" in members(shipped.BotLiveSettingsDialog)
    assert "_mark_changed" in members(shipped.BotLiveSettingsDialog)
    assert "BotLiveSettingsDialog" not in MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("BotLiveSettingsModel.no_such_member")
    assert MODEL_MEMBERS - {"apply_changes"} != MODEL_MEMBERS
    assert members(surface.BotLiveSettingsModel) - {"build"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"BotLiveSettingsDialog.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"BotLiveSettingsDialog"} != shipped_classes()
    assert shipped_functions() - {"dialog_open_size_px"} != shipped_functions()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments its callers pass it."""
    import inspect

    app()
    assert list(
        inspect.signature(shipped.BotLiveSettingsDialog.__init__).parameters
    ) == ["self", "bot", "bot_manager", "parent"]
    assert list(inspect.signature(surface.BotLiveSettingsModel.__init__).parameters)[
        :3
    ] == ["self", "bot", "bot_manager"]
    for old_name, new_name in (
        ("_mark_changed", "mark_changed"),
        ("_navigate_to_sibling", "navigate_to_sibling"),
        ("_save_fleet_state_now", "save_fleet_state_now"),
        ("_sibling_bot_ids", "sibling_bot_ids"),
        ("_bot_manager_for_save", "bot_manager_for_save"),
        ("active_tab_index", "active_tab_index"),
        ("_apply_changes", "apply_changes"),
    ):
        old_side = list(
            inspect.signature(
                getattr(shipped.BotLiveSettingsDialog, old_name)
            ).parameters
        )
        new_side = list(
            inspect.signature(
                getattr(surface.BotLiveSettingsModel, new_name)
            ).parameters
        )
        assert old_side == new_side, (old_name, old_side, new_side)
    for name in ("dialog_content_size_px", "dialog_open_size_px"):
        assert list(inspect.signature(getattr(shipped, name)).parameters) == list(
            inspect.signature(getattr(surface, name)).parameters
        ), name
    assert list(inspect.signature(surface.view_model).parameters) == ["params"]


def modules_importing(module, skip=()):
    """Every file under src that imports the module named exactly `module`."""
    found = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path in skip:
            continue
        names = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names += [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        if any(name.split(".")[-1] == module for name in names):
            found.append(str(path))
    return found


def test_the_window_is_reached_by_its_hosts_and_the_surface_by_the_bridge():
    """The count of readers is wrong, so a lost reader would pass unseen."""
    readers = modules_importing("bot_live_settings", skip=(SURFACE_PATH, WINDOW_PATH))
    assert str(REPO_ROOT / "src/gui/main_window.py") in readers, readers
    assert len(readers) == 5, readers
    assert modules_importing("bot_live_settings_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    known = modules_importing("design_system")
    assert len(known) > 5, known


# ---------------------------------------------------------------------
# The window paints, and the two sides paint the same pixels
# ---------------------------------------------------------------------

PICTURE_CASES = (
    "happy",
    "empty",
    "unicode",
    "markup",
    "apostrophe",
    "long_two_hundred",
    "stopped",
    "unknown_state",
    "idle",
    "extractor",
    "two_siblings",
)


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def old_window_for_picture(name):
    """The shipped window with its tab body out of the frame.

    Each tab is its own screen and its own comparison. What is compared
    here is the part this window owns: the header, the state badge, the
    two navigation buttons, the button row and the change line.
    """
    window = old_window_for(name)
    window._tabs.setVisible(False)
    return window


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    return sealed(surface.build_view_model(new_model_for(name)))


def window_painted_by_the_model(payload):
    """One window built only from the surface's view model."""
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    window = hold(QDialog())
    window.setWindowTitle(payload["title"])
    window.setMinimumSize(*payload["minimum_size_px"])
    layout = QVBoxLayout(window)
    header_row = QHBoxLayout()
    header = QLabel(payload["header_label"])
    header.setStyleSheet(payload["header_style"])
    header_row.addWidget(header)
    state = QLabel(payload["state_label"])
    state.setStyleSheet(payload["state_style"])
    header_row.addWidget(state)
    header_row.addStretch()
    previous = QPushButton(payload["prev_label"])
    previous.setStyleSheet(payload["nav_style"])
    previous.setToolTip(payload["prev_tooltip"])
    header_row.addWidget(previous)
    following = QPushButton(payload["next_label"])
    following.setStyleSheet(payload["nav_style"])
    following.setToolTip(payload["next_tooltip"])
    header_row.addWidget(following)
    previous.setVisible(payload["nav_shown"])
    following.setVisible(payload["nav_shown"])
    layout.addLayout(header_row)
    tabs = QTabWidget()
    for name in payload["tabs"]:
        tabs.addTab(QWidget(), name)
    layout.addWidget(tabs)
    tabs.setVisible(False)
    button_row = QHBoxLayout()
    button_row.addStretch()
    apply_button = QPushButton(payload["apply_label"])
    apply_button.setStyleSheet(payload["apply_style"])
    apply_button.setEnabled(payload["apply_enabled"])
    button_row.addWidget(apply_button)
    close = QPushButton(payload["close_label"])
    close.setStyleSheet(payload["close_style"])
    button_row.addWidget(close)
    layout.addLayout(button_row)
    change = QLabel(payload["change_label"])
    change.setStyleSheet(payload["change_style"])
    layout.addWidget(change)
    return window


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a window the shipped window does not."""
    app()
    old_side = render_offscreen(old_window_for_picture(name), PIXEL_SIZE)
    new_side = render_offscreen(
        window_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_window_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("stopped")), PIXEL_SIZE
        ),
        note="a running bot against a stopped one",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_window_for_picture("stopped"), PIXEL_SIZE),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("two_siblings")), PIXEL_SIZE
        ),
        note="a lone bot against one with siblings",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_window_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("happy")
    payload["header_label"] = "moved"
    with pytest.raises(AssertionError):
        window_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        window_painted_by_the_model({"header_label": ""})
    assert window_painted_by_the_model(model_payload("happy")) is not None


def test_the_window_declares_no_skin_of_its_own():
    """A colour the surface ships is one the window never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    assert "QWidget" not in surface.NAV_BUTTON_STYLE
    assert "QWidget" not in surface.APPLY_STYLE
    assert "QWidget" not in surface.HEADER_STYLE_FORMAT
    skinned = window_painted_by_the_model(model_payload("happy"))
    skinned.setStyleSheet("QWidget { background-color: #3a1414; }")
    assert_pictures_differ(
        old_side=render_offscreen(old_window_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(skinned, PIXEL_SIZE),
        note="a rule the window does not set",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_window_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


EQUAL_CHANNEL_COLOURS = ("#888", "#666", "#ccc")


def test_a_state_colour_reaches_the_badge_whatever_its_digit_count():
    """A short state colour and its six-digit twin tint the badge differently."""
    alpha = surface.STATE_BACKGROUND_ALPHA
    for colour in EQUAL_CHANNEL_COLOURS:
        digits = colour.lstrip("#")
        assert len(set(digits)) == 1, colour
        widened = "#" + "".join(one * 2 for one in digits)
        assert surface.rgba(colour, alpha) == surface.rgba(widened, alpha), colour
    assert surface.rgba("#0a1b2c", alpha) != surface.rgba("#2c1b0a", alpha)
    assert surface.STATE_COLORS[surface.STATE_STOPPED] == shipped.ds.TEXT_MUTED
    assert surface.STATE_UNKNOWN_BG == surface.STATE_UNKNOWN_FG
    assert shipped.ds.CARD_METRIC_LABEL == surface.STATE_COLORS[surface.STATE_IDLE]


def test_the_state_colours_are_compared_as_exact_text():
    """A state colour moved on one side and the comparison read it as a match."""
    for state in sorted(surface.STATE_COLORS):
        old_side = read_old(old_window(spec(state=state)))
        new_side = read_new(
            surface_model_for_state(state),
        )
        assert old_side["state_style"] == new_side["state_style"], state
        assert surface.STATE_COLORS[state] in new_side["state_style"], state


def surface_model_for_state(state):
    """The surface's window for one bot state."""
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource(), state=state)
    )
    model.build()
    return model


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font database."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding fonts measured every glyph the same width."""
    app()
    assert app_font_advance_px(WIDE_LABEL) > app_font_advance_px(NARROW_LABEL)


# ---------------------------------------------------------------------
# What a picture cannot see
# ---------------------------------------------------------------------

UNPAINTED = {
    "prev_tooltip": "test_the_tooltips_are_compared_as_strings",
    "next_tooltip": "test_the_tooltips_are_compared_as_strings",
    "minimum_size_px": "test_the_minimum_size_is_compared_as_the_ask",
    "current_tab": "test_the_active_tab_is_compared_as_a_number",
    "pending_navigate_to": "test_one_walk_of_the_swarm_lands_on_the_same_bot",
    "siblings": "test_the_sibling_reader_reports_a_real_list",
    "shortcuts": "test_the_shortcuts_are_compared_as_the_keys_asked_for",
    "fold_sort_key": "test_the_fold_sort_default_is_compared_as_a_string",
    "style_sheet": "test_the_window_declares_no_skin_of_its_own",
    "changes": "test_one_run_of_edits_leaves_the_same_pending_line",
    "tabs": "test_the_tabs_are_compared_as_names",
    "title": "test_the_title_is_compared_as_a_string",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no picture shows is compared by no test either."""
    reading = read_new(new_model_for("happy"))
    for key, name in UNPAINTED.items():
        assert key in reading, key
        assert callable(globals()[name]), name
    painted = set(reading) - set(UNPAINTED)
    assert painted, sorted(reading)
    assert "header_label" in painted


def test_the_tooltips_are_compared_as_strings():
    """A tooltip moved on one side and the comparison read it as a match."""
    old_side = read_old(old_window_for("happy"))
    new_side = read_new(new_model_for("happy"))
    assert old_side["prev_tooltip"] == new_side["prev_tooltip"]
    assert old_side["next_tooltip"] == new_side["next_tooltip"]
    assert old_side["prev_tooltip"] != old_side["next_tooltip"]
    assert "Ctrl+Left" in new_side["prev_tooltip"]
    assert "Ctrl+Right" in new_side["next_tooltip"]


def test_the_minimum_size_is_compared_as_the_ask():
    """The platform rewrote the minimum, so the read-back is not the ask."""
    old_side = read_old(old_window_for("happy"))
    assert old_side["minimum_size_px"] == [640, 720]
    assert read_new(new_model_for("happy"))["minimum_size_px"] == [640, 720]
    assert [surface.MINIMUM_W_PX, surface.MINIMUM_H_PX] == [640, 720]


def test_the_active_tab_is_compared_as_a_number():
    """The active tab moved on one side and read as a match."""
    window = old_window_for("happy")
    assert window.active_tab_index() == 0
    window._tabs.setCurrentIndex(2)
    assert window.active_tab_index() == 2
    model = new_model_for("happy")
    assert model.active_tab_index() == 0
    model.current_tab = 2
    assert model.active_tab_index() == 2


def test_an_active_tab_that_cannot_be_read_falls_back_to_the_first():
    """One side crashed where the other named the first tab."""
    window = old_window_for("happy")
    window._tabs = None
    assert window.active_tab_index() == 0
    model = new_model_for("happy")
    model.current_tab = "not a number"
    assert model.active_tab_index() == 0


def test_the_shortcuts_are_compared_as_the_keys_asked_for():
    """A keyboard shortcut appeared on one side and not the other."""
    old_side = read_old(old_window_for("two_siblings"))
    new_side = read_new(new_model_for("two_siblings"))
    assert old_side["shortcuts"] == new_side["shortcuts"] == ["Ctrl+Left", "Ctrl+Right"]
    lone = read_old(old_window_for("happy"))
    assert lone["shortcuts"] == read_new(new_model_for("happy"))["shortcuts"] == []


def test_a_window_whose_shortcuts_refuse_still_opens():
    """A refused shortcut closed the window instead of being written down."""
    model = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()),
        surface.BotManagerSource(("bot-a", "bot-b")),
        shortcuts_raise=RuntimeError("no shortcut"),
    )
    model.build()
    payload = surface.build_view_model(model)
    assert payload["shortcuts"] == []
    assert payload["title"] != ""
    assert [line[0] for line in payload["logged"]] == [surface.SHORTCUT_FAILED_LOG]


def test_the_fold_sort_default_is_compared_as_a_string():
    """The row order the window starts on moved on one side."""
    assert (
        shipped.BotLiveSettingsDialog._fold_sort_key
        == surface.BotLiveSettingsModel.fold_sort_key
        == surface.FOLD_SORT_QUEUE_ORDER
    )
    assert surface.FOLD_SORT_QUEUE_ORDER == "Queue order"


def test_the_tabs_are_compared_as_names():
    """A tab appeared on one side and not the other."""
    assert read_old(old_window_for("happy"))["tabs"] == surface.tabs_for_mode(
        "scrumming"
    )
    assert read_old(old_window_for("extractor"))["tabs"] == surface.tabs_for_mode(
        "extractor"
    )
    assert surface.tabs_for_mode("scrumming") != surface.tabs_for_mode("extractor")
    assert surface.tabs_for_mode("no such mode") == ["Status", "Settings"]
    assert len(surface.TAB_PLAN) == 8


def test_the_title_is_compared_as_a_string():
    """The window title moved on one side and read as a match."""
    old_side = read_old(old_window_for("happy"))
    assert old_side["title"] == read_new(new_model_for("happy"))["title"]
    assert old_side["title"].startswith("Bot Settings")
    assert (
        surface.window_title("A/USD", "0123456789") == "Bot Settings — A/USD [01234567]"
    )
    assert surface.BOT_ID_SHORT_LENGTH == 8


def test_the_form_settings_are_the_shipped_form_settings():
    """A form row would be sized differently on the two sides."""
    from PySide6.QtWidgets import QFormLayout

    app()
    window = old_window_for("happy")
    form = QFormLayout()
    window._configure_form(form)
    model = new_model_for("happy")
    model.configure_form({})
    record = surface.build_view_model(model)["forms"][-1]
    assert form.horizontalSpacing() == record["horizontal_spacing_px"]
    assert form.verticalSpacing() == record["vertical_spacing_px"]
    margins = form.contentsMargins()
    assert [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ] == record["margins_px"]
    assert form.fieldGrowthPolicy().name == record["field_growth"]
    assert form.rowWrapPolicy().name == record["row_wrap"]


def test_the_scroller_is_asked_for_the_same_thing_on_both_sides():
    """A tab would scroll on one side and not the other."""
    from PySide6.QtWidgets import QFrame, QLabel

    app()
    window = old_window_for("happy")
    scroller = window._wrap_scrollable(QLabel("x"))
    record = new_model_for("happy").wrap_scrollable("Status")
    assert scroller.widgetResizable() is record[1]
    assert scroller.frameShape() == QFrame.NoFrame
    assert QFrame.NoFrame.name == record[2]


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


def freeze(value):
    """One value as a single comparable string."""

    def plain(found):
        if isinstance(found, (tuple, list)):
            return [plain(item) for item in found]
        if isinstance(found, dict):
            return {str(key): plain(item) for key, item in found.items()}
        return found

    return json.dumps(plain(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    import inspect

    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if isinstance(value, (surface.BotLiveSettingsModel, logging.Logger)):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    for name in CASES:
        payloads.append(surface.build_view_model(new_model_for(name)))
    for run in EDIT_RUNS:
        payloads.append(surface.build_view_model(new_edited("happy", EDIT_RUNS[run])))
    for run in APPLY_RUNS:
        payloads.append(surface.build_view_model(new_applied(APPLY_RUNS[run])))
    for run in STEP_RUNS:
        payloads.append(surface.build_view_model(new_stepped(STEP_RUNS[run])[0]))
    for run in NAVIGATE_RUNS:
        ids, here, direction = NAVIGATE_RUNS[run]
        model = surface.BotLiveSettingsModel(
            surface.BotSource(config=surface.BotConfigSource(), bot_id=here),
            surface.BotManagerSource(ids),
        )
        model.build()
        model.navigate_to_sibling(direction)
        payloads.append(surface.build_view_model(model))
    refusing = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()),
        surface.BotManagerSource(("bot-a", "bot-b")),
        shortcuts_raise=RuntimeError("no shortcut"),
    )
    refusing.build()
    payloads.append(surface.build_view_model(refusing))
    saved = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()), surface.BotManagerSource()
    )
    saved.build()
    saved.save_fleet_state_now("Fold tranches")
    payloads.append(surface.build_view_model(saved))
    failing = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource()),
        surface.BotManagerSource(save_raises=RuntimeError("disk gone")),
    )
    failing.build()
    failing.save_fleet_state_now("Wire credits")
    payloads.append(surface.build_view_model(failing))
    unsaved = surface.BotLiveSettingsModel(
        surface.BotSource(config=surface.BotConfigSource())
    )
    unsaved.build()
    unsaved.save_fleet_state_now("Lifetime counters")
    payloads.append(surface.build_view_model(unsaved))
    formed = new_model_for("happy")
    formed.configure_form({})
    payloads.append(surface.build_view_model(formed))
    sized = new_model_for("happy")
    sized.build(pages=(((1000, 2000), (400, 300)),), hint=(700, 800), available=None)
    payloads.append(surface.build_view_model(sized))
    closed = new_model_for("happy")
    closed.accept()
    payloads.append(surface.build_view_model(closed))
    for state in surface.STATE_COLORS:
        payloads.append(surface.build_view_model(surface_model_for_state(state)))
    payloads.append(surface.build_view_model(surface.build_model(build_now=True)))
    payloads.append(surface.build_view_model(surface.build_model()))
    return payloads


COVERED_ELSEWHERE = {
    "PANE_MODEL": "test_importing_the_surface_reads_no_bot",
    "LOGGER_NAME": "test_the_surface_names_the_logger_the_window_writes_under",
    "ModelCall": "test_the_recorded_steps_are_compared_as_values",
    "NO_MANAGER": "test_the_window_falls_back_to_the_bots_manager",
    "AGE_SECONDS_FORMAT": "test_one_age_reads_the_same_on_both_sides",
    "AGE_MINUTES_FORMAT": "test_one_age_reads_the_same_on_both_sides",
    "STATE_BACKGROUND_ALPHA": (
        "test_a_state_colour_reaches_the_badge_whatever_its_digit_count"
    ),
    "SECONDS_PER_MINUTE": "test_one_age_reads_the_same_on_both_sides",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped window."""
    constants = surface_constants()
    assert len(constants) > 80, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "APPLY_LABEL" in missing_from_payload(surface_constants(), thinned)
    assert "TAB_PLAN" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": "METHOD",
    "logger_name": "LOGGER_NAME",
    "title": "model.title",
    "title_format": "WINDOW_TITLE_FORMAT",
    "bot_id_short_length": "BOT_ID_SHORT_LENGTH",
    "minimum_size_px": "model.minimum_size_px",
    "minimum_w_px": "MINIMUM_W_PX",
    "minimum_h_px": "MINIMUM_H_PX",
    "screen_margin_w_px": "DIALOG_SCREEN_MARGIN_W_PX",
    "screen_margin_h_px": "DIALOG_SCREEN_MARGIN_H_PX",
    "opened_size_px": "model.opened_size_px",
    "header_label": "model.header_label",
    "header_format": "HEADER_FORMAT",
    "header_style": "model.header_style",
    "header_style_format": "HEADER_STYLE_FORMAT",
    "header_color": "HEADER_COLOR",
    "state_label": "model.state_label",
    "state_label_format": "STATE_LABEL_FORMAT",
    "state_style": "model.state_style",
    "state_style_format": "STATE_STYLE_FORMAT",
    "state_colors": "STATE_COLORS",
    "state_unknown_fg": "STATE_UNKNOWN_FG",
    "state_unknown_bg": "STATE_UNKNOWN_BG",
    "state_running": "STATE_RUNNING",
    "state_idle": "STATE_IDLE",
    "state_paused": "STATE_PAUSED",
    "state_error": "STATE_ERROR",
    "state_stopped": "STATE_STOPPED",
    "state_cooldown": "STATE_COOLDOWN",
    "nav_style": "NAV_BUTTON_STYLE",
    "prev_label": "PREV_LABEL",
    "next_label": "NEXT_LABEL",
    "prev_tooltip": "PREV_TOOLTIP",
    "next_tooltip": "NEXT_TOOLTIP",
    "prev_step": "PREV_STEP",
    "next_step": "NEXT_STEP",
    "nav_shown": "model.nav_shown",
    "nav_shown_above_siblings": "NAV_SHOWN_ABOVE_SIBLINGS",
    "nav_needs_siblings": "NAV_NEEDS_SIBLINGS",
    "siblings": "model.sibling_bot_ids",
    "pending_navigate_to": "model.pending_navigate_to",
    "accepted": "model.accepted",
    "tabs": "model.tabs",
    "tab_plan": "TAB_PLAN",
    "wrapped_tabs": "model.wrapped_tabs",
    "current_tab": "model.active_tab_index",
    "first_tab_index": "FIRST_TAB_INDEX",
    "no_tabs": "NO_TABS",
    "tab_status": "TAB_STATUS",
    "tab_settings": "TAB_SETTINGS",
    "tab_fold_tranches": "TAB_FOLD_TRANCHES",
    "tab_stack_tranches": "TAB_STACK_TRANCHES",
    "tab_bot_swarm": "TAB_BOT_SWARM",
    "tab_market_inspector": "TAB_MARKET_INSPECTOR",
    "tab_phantom_bots": "TAB_PHANTOM_BOTS",
    "tab_positions_held": "TAB_POSITIONS_HELD",
    "mode_scrumming": "MODE_SCRUMMING",
    "mode_extractor": "MODE_EXTRACTOR",
    "any_mode": "ANY_MODE",
    "installed_by_host": "INSTALLED_BY_HOST",
    "installed_by_window": "INSTALLED_BY_WINDOW",
    "scroll_resizable": "SCROLL_RESIZABLE",
    "scroll_frame_shape": "SCROLL_FRAME_SHAPE",
    "form_field_growth": "FORM_FIELD_GROWTH",
    "form_row_wrap": "FORM_ROW_WRAP",
    "form_horizontal_spacing_px": "FORM_HORIZONTAL_SPACING_PX",
    "form_vertical_spacing_px": "FORM_VERTICAL_SPACING_PX",
    "form_margins_px": "FORM_MARGINS_PX",
    "forms": "model.forms",
    "apply_label": "APPLY_LABEL",
    "apply_style": "APPLY_STYLE",
    "apply_enabled": "model.apply_enabled",
    "apply_enabled_at_start": "APPLY_ENABLED_AT_START",
    "close_label": "CLOSE_LABEL",
    "close_style": "CLOSE_STYLE",
    "change_label": "model.change_label",
    "change_style": "model.change_style",
    "change_empty_text": "CHANGE_EMPTY_TEXT",
    "change_pending_format": "CHANGE_PENDING_FORMAT",
    "change_field_separator": "CHANGE_FIELD_SEPARATOR",
    "change_pending_style": "CHANGE_PENDING_STYLE",
    "change_applied_format": "CHANGE_APPLIED_FORMAT",
    "change_applied_style": "CHANGE_APPLIED_STYLE",
    "changes": "model.changes",
    "no_changes": "NO_CHANGES",
    "applied": "model.applied",
    "applied_entry_format": "APPLIED_ENTRY_FORMAT",
    "applied_synced_format": "APPLIED_SYNCED_FORMAT",
    "applied_refused_format": "APPLIED_REFUSED_FORMAT",
    "applied_error_format": "APPLIED_ERROR_FORMAT",
    "applied_entry_separator": "APPLIED_ENTRY_SEPARATOR",
    "applied_join": "APPLIED_JOIN",
    "sent": "model.sent",
    "signal_name": "SIGNAL_NAME",
    "phantom_fields": "PHANTOM_FIELDS",
    "phantom_enable_field": "PHANTOM_ENABLE_FIELD",
    "phantom_timeframes_field": "PHANTOM_TIMEFRAMES_FIELD",
    "phantom_lock_field": "PHANTOM_LOCK_FIELD",
    "phantom_enable_attribute": "PHANTOM_ENABLE_ATTRIBUTE",
    "phantom_timeframes_attribute": "PHANTOM_TIMEFRAMES_ATTRIBUTE",
    "coordinator_attribute": "COORDINATOR_ATTRIBUTE",
    "coordinator_lock_attribute": "COORDINATOR_LOCK_ATTRIBUTE",
    "phantom_update_method": "PHANTOM_UPDATE_METHOD",
    "phantom_applied_key": "PHANTOM_APPLIED_KEY",
    "phantom_caveats_key": "PHANTOM_CAVEATS_KEY",
    "runtime_routed": "RUNTIME_ROUTED",
    "route_applied_key": "ROUTE_APPLIED_KEY",
    "route_reason_key": "ROUTE_REASON_KEY",
    "route_unknown_reason": "ROUTE_UNKNOWN_REASON",
    "shortcuts": "model.shortcuts",
    "shortcut_plan": "SHORTCUTS",
    "shortcut_failed_log": "SHORTCUT_FAILED_LOG",
    "logged": "model.logged",
    "phantom_caveat_log": "PHANTOM_CAVEAT_LOG",
    "phantom_failed_log": "PHANTOM_FAILED_LOG",
    "route_refused_log": "ROUTE_REFUSED_LOG",
    "route_raised_log": "ROUTE_RAISED_LOG",
    "applied_log": "APPLIED_LOG",
    "save_failed_log": "SAVE_FAILED_LOG",
    "save_method": "SAVE_METHOD",
    "bot_manager_attribute": "BOT_MANAGER_ATTRIBUTE",
    "no_manager_reason": "NO_MANAGER_REASON",
    "saved_reason": "SAVED_REASON",
    "save_failed_format": "SAVE_FAILED_FORMAT",
    "age_seconds_format": "AGE_SECONDS_FORMAT",
    "age_minutes_format": "AGE_MINUTES_FORMAT",
    "age_hours_format": "AGE_HOURS_FORMAT",
    "age_days_format": "AGE_DAYS_FORMAT",
    "seconds_per_minute": "SECONDS_PER_MINUTE",
    "seconds_per_hour": "SECONDS_PER_HOUR",
    "seconds_per_day": "SECONDS_PER_DAY",
    "fold_sort_key": "model.fold_sort_key",
    "fold_sort_queue_order": "FOLD_SORT_QUEUE_ORDER",
    "no_siblings": "NO_SIBLINGS",
    "no_navigation": "NO_NAVIGATION",
    "actions": "ACTIONS",
    "timers": "TIMERS",
    "timer_delays_ms": "TIMER_DELAYS_MS",
    "bus_topics": "BUS_TOPICS",
    "skin": "SKIN",
    "style_sheet": "STYLE_SHEET",
    "call_names": "CALL_NAMES",
    "calls": "model.calls",
}

FREE_SHAPE_KEYS = ("calls",)


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
        return found() if callable(found) else found
    return getattr(surface, name)


def backed(key, value, name, model):
    """Whether one payload key carries exactly what its named source holds."""
    resolved = resolve_source(name, model)
    if key in FREE_SHAPE_KEYS:
        return len(value) == len(resolved)
    return freeze(value) == freeze(resolved)


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = new_model_for("happy")
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    fresh = new_model_for("happy")
    payload = surface.build_view_model(fresh)
    for key, name in PAYLOAD_KEY_SOURCES.items():
        if name.startswith("model."):
            assert hasattr(fresh, name.split(".", 1)[1]), name
        else:
            assert hasattr(surface, name), name
        assert backed(key, payload[key], name, fresh), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = new_model_for("happy")
    payload = surface.build_view_model(model)
    assert backed("apply_label", payload["apply_label"], "APPLY_LABEL", model)
    assert not backed("apply_label", "Apply", "APPLY_LABEL", model)
    assert not backed("tab_plan", [["Status"]], "TAB_PLAN", model)
    assert not backed("skin", {"a": "b"}, "SKIN", model)
    assert not backed("title", "moved", "model.title", model)
    assert not backed("calls", [], "model.calls", model)


def test_the_recorded_steps_are_compared_as_values():
    """A recorded step moved and the comparison read it as a match."""
    payload = surface.build_view_model(new_model_for("happy"))
    names = [call[0] for call in payload["calls"]]
    assert names[0] == surface.BUILD_START
    assert names[-1] == surface.BUILD_SIZED
    assert surface.BUILD_TAB in names
    assert set(names) <= set(payload["call_names"]), sorted(
        set(names) - set(payload["call_names"])
    )
    extractor = surface.build_view_model(new_model_for("extractor"))
    assert [call[0] for call in extractor["calls"]] != names
    assert surface.ModelCall is list


def test_the_surface_names_the_logger_the_window_writes_under():
    """The surface writes under a logger the window does not use."""
    assert surface.LOGGER_NAME == shipped.logger.name == "acervator.gui"


# ---------------------------------------------------------------------
# What the shipped module keeps between windows
# ---------------------------------------------------------------------


def test_the_shipped_module_changes_no_value_the_next_window_reads():
    """One window left a changed value behind for the next one."""
    app()
    before = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    for name in sorted(CASES):
        old_window_for(name)
    after = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    assert after == before


def test_the_shipped_window_reaches_the_process_wide_market_inspector():
    """The window changes no shared state, so no test can disturb another."""
    from src.trading import market_inspector

    app()
    assert market_inspector._GLOBAL_INSPECTOR is None
    old_window_for("happy")
    assert market_inspector._GLOBAL_INSPECTOR is not None


def test_each_test_is_given_its_own_market_inspector(own_shared_state):
    """Two tests share one inspector, so the order they run in decides both."""
    assert own_shared_state._GLOBAL_INSPECTOR is None
    old_window_for("happy")
    assert own_shared_state._GLOBAL_INSPECTOR is not None


def test_each_test_is_given_its_own_market_inspector_again():
    """The inspector the test above built survived into this one."""
    from src.trading import market_inspector

    assert market_inspector._GLOBAL_INSPECTOR is None


def test_the_surface_keeps_no_value_between_two_windows():
    """One window left a changed value behind for the next one."""
    first = new_model_for("happy")
    first.mark_changed("visibility", "internal")
    second = surface.BotLiveSettingsModel(surface.BotSource())
    assert second.changes == {}
    assert second.calls == []
    assert second.tabs == []
    assert first.changes != second.changes


def test_the_surface_declares_its_class_default_and_not_an_instance_value():
    """The row order default moved onto one window and not the class."""
    assert "fold_sort_key" in vars(surface.BotLiveSettingsModel)
    assert "fold_sort_key" not in vars(
        surface.BotLiveSettingsModel(surface.BotSource())
    )
    assert "_fold_sort_key" in vars(shipped.BotLiveSettingsDialog)


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    payload = surface.build_view_model(new_model_for("happy"))
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_window_method():
    """The renderer cannot reach the settings window over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "bot_live_settings.state"
    assert registered[surface.METHOD] is surface.view_model


def test_the_bridge_import_list_is_alphabetical():
    """A surface was added to the bridge out of order."""
    tree = ast.parse((REPO_ROOT / "src/core/desktop_bridge.py").read_text("utf-8"))
    listed = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            listed = [alias.name for alias in node.names]
    assert listed == sorted(listed), listed
    assert "bot_live_settings_surface" in listed


def test_the_bridge_keeps_the_window_until_a_reset():
    """The window forgets the operator's edits between two requests."""
    surface.view_model({"reset": True})
    first = surface.view_model(
        {"bot": {"symbol": "A/USD", "mode": "scrumming", "bot_id": "bot-a"}}
    )
    assert first["title"] == "Bot Settings — A/USD [bot-a]"
    second = surface.view_model({"mark": {"visibility": "internal"}})
    assert second["changes"] == {"visibility": "internal"}
    third = surface.view_model({"reset": True})
    assert third["changes"] == {}
    surface.view_model({"reset": True})


def test_the_bridge_drives_every_step_the_window_takes():
    """A step the window takes cannot be reached over the bridge."""
    surface.view_model({"reset": True})
    answered = surface.view_model(
        {
            "bot": {"symbol": "A/USD", "mode": "scrumming", "bot_id": "bot-a"},
            "siblings": ["bot-a", "bot-b"],
            "mark": {"visibility": "internal"},
            "apply": True,
            "navigate": 1,
        }
    )
    assert answered["tabs"] == surface.tabs_for_mode("scrumming")
    assert answered["nav_shown"] is True
    assert answered["pending_navigate_to"] == "bot-b"
    assert answered["change_label"].startswith("Applied")
    surface.view_model({"reset": True})


def test_the_bridge_reports_a_window_it_cannot_read():
    """The bridge swallowed a refusal and answered as if it had a window."""
    from src.core import desktop_bridge

    frame = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 1,
                "method": surface.METHOD,
                "params": {"reset": True, "bot": {"bot_id": 7}},
            }
        ),
        desktop_bridge.build_registry(),
    )
    assert frame["ok"] is False
    assert frame["error"]["type"] == "TypeError"
    surface.view_model({"reset": True})


# ---------------------------------------------------------------------
# Without Qt at all
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'bot_live_settings.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + """
import json
import sys

from src.gui.main_tabs import bot_live_settings_surface as s

model = s.build_model(
    s.BotSource(
        config=s.BotConfigSource(
            symbol='CHIP/USD',
            mode='scrumming',
            fields={'visibility': 'orderbook'},
        ),
        bot_id='bot-alpha-0001',
        state='running',
    ),
    s.BotManagerSource(['bot-alpha-0001', 'bot-beta-0002']),
    build_now=True,
)
model.mark_changed('visibility', 'internal')
model.apply_changes()
payload = s.build_view_model(model)
print(json.dumps({'qt': 'PySide6' in sys.modules,
                  'title': payload['title'],
                  'header': payload['header_label'],
                  'state_style': payload['state_style'],
                  'tabs': payload['tabs'],
                  'nav_shown': payload['nav_shown'],
                  'apply_label': payload['apply_label'],
                  'change_label': payload['change_label'],
                  'sent': payload['sent'],
                  'shortcuts': payload['shortcuts'],
                  'calls': len(payload['calls'])}))
"""


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the settings window pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["apply_label"] == surface.APPLY_LABEL
    assert result["tabs"] == []


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_window_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["title"] == "Bot Settings — CHIP/USD [bot-alph]"
    assert answered["header"] == "CHIP/USD  •  SCRUMMING"
    assert answered["tabs"] == surface.tabs_for_mode("scrumming")
    assert answered["nav_shown"] is True
    assert answered["apply_label"] == surface.APPLY_LABEL
    assert answered["change_label"] == surface.applied_text(1)
    assert answered["sent"] == [["bot-alpha-0001", {"visibility": "internal"}]]
    assert answered["shortcuts"] == [["Ctrl+Left", -1], ["Ctrl+Right", 1]]
    assert answered["calls"] > 10


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


WINDOW_IMPORT_PROBE = """
import json

try:
    from src.gui import bot_live_settings as w

    out = {'imported': True,
           'has_qt': w._HAS_QT,
           'has_window': hasattr(w, 'BotLiveSettingsDialog'),
           'sizes': list(w.dialog_open_size_px(1, 1, 4000, 4000, 640, 720))}
except Exception as exc:
    out = {'imported': False,
           'error': type(exc).__name__,
           'headline': str(exc)}
print(json.dumps(out))
"""


def test_the_window_file_loads_without_qt_but_builds_no_window():
    """The window file needs Qt to be read, or it builds a window without it.

    The file guards its own Qt import and reports ``_HAS_QT`` False, so
    it loads where Qt cannot. What it does not do is carry the window:
    the class body sits behind that guard, so nothing can be opened.
    """
    answered = run_script(BLOCK_QT + WINDOW_IMPORT_PROBE)
    assert answered["imported"] is True, answered
    assert answered["has_qt"] is False, answered
    assert answered["has_window"] is False, answered
    assert answered["sizes"] == [640, 720], answered
    assert "_HAS_QT" in WINDOW_PATH.read_text(encoding="utf-8")


IMPORT_PROBE = """
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-window-probe-'))
at_import = root / 'at-import'
on_request = root / 'on-request'
at_import.mkdir()
on_request.mkdir()
os.environ['ACERVATOR_SETTINGS_ROOT'] = str(at_import)

from src.gui.main_tabs import bot_live_settings_surface as s

built_at_import = s.PANE_MODEL is not None
files_at_import = sorted(one.name for one in at_import.iterdir())
os.environ['ACERVATOR_SETTINGS_ROOT'] = str(on_request)
window = s.pane_model()
answer = {'built_at_import': built_at_import,
          'built_on_request': window is s.PANE_MODEL,
          'files_at_import': files_at_import,
          'files_on_request': sorted(one.name for one in on_request.iterdir()),
          'root_at_import': str(at_import),
          'root_on_request': os.environ['ACERVATOR_SETTINGS_ROOT'],
          'qt': 'PySide6' in sys.modules}
shutil.rmtree(root, ignore_errors=True)
print(json.dumps(answer))
"""


def test_importing_the_surface_reads_no_bot():
    """Loading the surface built a window, which reads the operator's own bot.

    The settings root is aimed at one folder while the surface is
    imported and at a second folder before the first request. Nothing is
    built until the request, so neither folder is read at import.
    """
    answered = run_script(IMPORT_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["files_at_import"] == [], answered
    assert answered["files_on_request"] == [], answered
    assert answered["root_at_import"] != answered["root_on_request"], answered
    assert answered["qt"] is False, answered


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    imported = imports_of(SURFACE_PATH)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    window_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(WINDOW_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in window_imports), window_imports


def test_the_surface_opens_no_file_and_no_socket():
    """The surface reached for a file, a network address or a browser."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in (
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "mkdir",
        "urlopen",
        "connect",
        "socket",
        "listen",
    ):
        assert forbidden not in reached, forbidden
    text = SURFACE_PATH.read_text(encoding="utf-8")
    assert "webbrowser" not in text
    assert "acervator_logs" not in text
    assert "Path.home" not in text


def test_the_surface_file_has_unix_line_endings():
    """The file carries carriage returns, which the build machine rejects."""
    assert SURFACE_PATH.read_bytes().count(b"\r") == 0
    assert Path(__file__).read_bytes().count(b"\r") == 0
