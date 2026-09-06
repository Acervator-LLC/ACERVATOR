"""The shipped exchange screen and the Qt-free surface, side by side.

A failure means the view model carries a different button, a different
colour, a different tooltip, a different heading, a different highlight,
a different command, a different recorded check or a different refusal
than ``ExchangeTab``.

No test here reads or writes the operator's runtime tree, opens a socket
or reaches an exchange. Every bot id, symbol, balance and pool report
below is invented.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import exchange_tab_surface as surface
from src.gui.widgets import exchange_tab as shipped
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


PIXEL_SIZE = (900, 220)

# Counts read off a built screen, not off the file. The suite seats
# `tests/fixtures/quiet_news_ticker.py` in place of the real strip, so these are
# the tab's own wiring and elements.
TAB_CONNECTIONS = 13
SURFACE_ACTION_TOTAL = 6
TAB_TIMER_BUILDS = 1
TAB_BUS_SITES = 0
TAB_SIGNAL_BUILDS = 0
TAB_ELEMENTS = 51
STAT_CARD_ELEMENTS = 2

# Invented values. No bot id, symbol or balance below is the operator's.
UNICODE_BOT_ID = "Δ_fold→⚡"
UNICODE_SYMBOL = "Δ/USD"
MARKUP_BOT_ID = "<b>bot</b>"
MARKUP_SYMBOL = "<i>X</i>/USD"
APOSTROPHE_BOT_ID = "Ekthelius" + chr(39) + " Fold"
NEWLINE_BOT_ID = "two\nlines"
LONG_BOT_ID = "x" * 200
EXCHANGE_ID = "coinbase"
EXCHANGE_NAME = "Coinbase"
OTHER_EXCHANGE_ID = "kraken"

WIDGETS_HELD: list = []
PINS_SEEN: list = []


# The privacy register is process-wide, and the screen WRITES to it.
# Every test is given its own and the process one is put back.


@pytest.fixture(autouse=True)
def own_privacy_registry(tmp_path, monkeypatch):
    """Give this test its own register and restore the process one after.

    ``get_privacy_mask_registry`` returns one object for the whole
    process, both sides reach it through that one function, and the
    Privacy Mode button writes to it, so a mask a test leaves set would
    decide what a later test paints. A NEW object is handed out rather
    than a cleared one: clearing walks only the field ids the register
    declares. Autosave is off and the path is a temporary one, so no
    test writes a settings file.
    """
    from src.core import privacy_mask_registry as registry_module

    fresh = registry_module.PrivacyMaskRegistry(
        settings_path=tmp_path / "settings.json", autosave=False
    )
    monkeypatch.setattr(registry_module, "_SINGLETON", fresh)
    yield fresh


@pytest.fixture(autouse=True)
def no_news_feed(monkeypatch):
    """Replace the news strip with one that reaches no network.

    The shipped strip starts a background fetch against ten feeds the
    moment it is built. Nothing in this file may open a socket, so the
    class the screen reaches for is replaced for every test.
    """
    from PySide6.QtWidgets import QWidget

    from src.gui import crypto_news_ticker

    class QuietTicker(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Crypto News Ticker")

        def start(self):
            QUIET_TICKER_STARTS.append(1)

    monkeypatch.setattr(crypto_news_ticker, "CryptoNewsTicker", QuietTicker)
    QUIET_TICKER_STARTS.clear()
    yield QuietTicker


QUIET_TICKER_STARTS: list = []


@pytest.fixture(autouse=True)
def watch_pins(monkeypatch):
    """Record every check the shipped screen sends, instead of sending it."""
    from src.core import signal_contract

    def recorder(
        name,
        actual,
        expected=None,
        ok=None,
        context=None,
        every=0.0,
        instance=None,
        module=None,
        duration=None,
    ):
        PINS_SEEN.append(
            {
                "name": name,
                "actual": actual,
                "expected": expected,
                "every": every,
                "instance": instance,
                "context": context,
                "verdict": ok,
                "seconds": duration,
                "module": module,
            }
        )
        return None

    monkeypatch.setattr(signal_contract, "emit", recorder)
    PINS_SEEN.clear()
    yield PINS_SEEN


def registry():
    """The register both sides read, through the accessor both sides call."""
    from src.core.privacy_mask_registry import get_privacy_mask_registry

    return get_privacy_mask_registry()


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def hold(widget):
    """Keep one widget alive so no later read reaches a collected object."""
    WIDGETS_HELD.append(widget)
    return widget


# Invented bot records, pool reports, and the case table both sides
# are driven with


def bot(**over):
    """One bot record, with a running scrumming bot as the base."""
    base = {
        "bot_id": "bot-alpha-0001",
        "symbol": "XRP/USD",
        "mode": "scrumming",
        "state": "running",
        "exchange": EXCHANGE_ID,
        "current_holdings": 104.8,
        "quote_to_usd": 1.0,
        "live_target_balance": 50.0,
        "target_balance": 40.0,
        "stats": {"total_trades": 7, "position_value": 149.85, "current_price": 1.43},
    }
    base.update(over)
    return base


def extractor(**over):
    """One bot record in extractor mode."""
    base = {"mode": "extractor", "bot_id": "ext-alpha-0001"}
    base.update(over)
    return bot(**base)


CASES: dict = {
    "happy": [bot()],
    "empty": [],
    "zero_target": [bot(live_target_balance=0.0, target_balance=0.0)],
    "negative_target": [bot(live_target_balance=-25.0)],
    "thousand_million": [bot(live_target_balance=1_000_000_000.0)],
    "one_billionth": [bot(live_target_balance=1e-9)],
    "whole_number": [bot(live_target_balance=12)],
    "decimal_number": [bot(live_target_balance=12.0)],
    "infinite": [bot(live_target_balance=float("inf"))],
    "minus_infinite": [bot(live_target_balance=float("-inf"))],
    "not_a_number": [bot(live_target_balance=float("nan"))],
    "unicode": [bot(bot_id=UNICODE_BOT_ID, symbol=UNICODE_SYMBOL)],
    "markup": [bot(bot_id=MARKUP_BOT_ID, symbol=MARKUP_SYMBOL)],
    "apostrophe": [bot(bot_id=APOSTROPHE_BOT_ID)],
    "newline": [bot(bot_id=NEWLINE_BOT_ID)],
    "long": [bot(bot_id=LONG_BOT_ID)],
    "wrong_capitals": [bot(mode="SCRUMMING")],
    "unknown_mode": [bot(mode="")],
    "no_mode_key": [{key: found for key, found in bot().items() if key != "mode"}],
    "no_bot_id": [bot(bot_id="")],
    "number_where_text_belongs": [bot(symbol=5)],
    "text_where_a_number_belongs": [
        bot(live_target_balance="many", target_balance="many")
    ],
    "state_is_a_number": [bot(state=7)],
    "stats_is_text": [bot(stats="nope")],
    "holdings_is_text": [bot(current_holdings="lots")],
    "extractor_state_is_a_number": [extractor(state=7)],
    "extractor_stats_is_text": [extractor(stats="nope")],
    "extractor_symbol_is_a_number": [extractor(symbol=5)],
    "extractor_target_is_text": [
        extractor(live_target_balance="many", target_balance="many")
    ],
    "one_extractor": [extractor()],
    "both_kinds": [bot(bot_id="scrum-1"), extractor(bot_id="ext-1")],
    "one_row": [bot(bot_id="alpha")],
    "three_rows": [bot(bot_id="alpha"), bot(bot_id="beta"), bot(bot_id="gamma")],
    "four_rows": [
        bot(bot_id="alpha"),
        bot(bot_id="beta"),
        bot(bot_id="gamma"),
        bot(bot_id="delta"),
    ],
    "three_rows_second_refuses": [
        bot(bot_id="alpha"),
        bot(bot_id="beta", state=7),
        bot(bot_id="gamma"),
    ],
    "three_rows_reordered": [
        bot(bot_id="gamma"),
        bot(bot_id="alpha"),
        bot(bot_id="beta"),
    ],
    "two_extractors": [extractor(bot_id="ext-a"), extractor(bot_id="ext-b")],
    "no_stats_at_all": [bot(stats={})],
}

# The inputs both sides refuse, named so the outcome check can prove its
# set holds a refusal as well as an answer.
REFUSING = (
    "number_where_text_belongs",
    "text_where_a_number_belongs",
    "state_is_a_number",
    "stats_is_text",
    "holdings_is_text",
    "extractor_state_is_a_number",
    "extractor_stats_is_text",
    "three_rows_second_refuses",
)

SEQUENCES: dict = {
    "shrink": ["three_rows", "one_row"],
    "grow": ["one_row", "three_rows"],
    "empty_then_full": ["empty", "three_rows"],
    "full_then_empty": ["three_rows", "empty"],
    "same_twice": ["happy", "happy"],
    "scrum_then_extractor": ["happy", "one_extractor"],
    "extractor_then_scrum": ["one_extractor", "happy"],
    "shrink_then_refuse": ["four_rows", "three_rows_second_refuses"],
    "refuse_then_answer": ["state_is_a_number", "happy"],
    "three_steps": ["four_rows", "three_rows_second_refuses", "one_row"],
    "reorder": ["three_rows", "three_rows_reordered"],
    "both_then_one": ["both_kinds", "one_row"],
}

PICTURE_CASES = (
    "happy",
    "empty",
    "one_extractor",
    "both_kinds",
    "three_rows",
    "unknown_mode",
    "unicode",
    "long",
)

POOL_CASES: dict = {
    "idle": {"ticker_slots": 0, "ohlcv_slots": 0, "balance_slots": 0},
    "awaiting": {
        "ticker_slots": 2,
        "ohlcv_slots": 1,
        "balance_slots": 1,
        "ticker_fetches": 1,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 3,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": None,
        "oldest_age_s": None,
        "stale_slots": 0,
    },
    "warm": {
        "ticker_slots": 2,
        "ohlcv_slots": 1,
        "balance_slots": 1,
        "ticker_fetches": 1,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 3,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": 1.4,
        "oldest_age_s": 22.6,
        "stale_slots": 1,
    },
    "no_hits_at_all": {
        "ticker_slots": 1,
        "ohlcv_slots": 0,
        "balance_slots": 0,
        "ticker_fetches": 0,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 0,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": 0.0,
        "oldest_age_s": 0.0,
        "stale_slots": 0,
    },
    "thousand_million_slots": {
        "ticker_slots": 1_000_000_000,
        "ohlcv_slots": 0,
        "balance_slots": 0,
        "ticker_fetches": 1,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 0,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": 1e-9,
        "oldest_age_s": 1_000_000_000.0,
        "stale_slots": 7,
    },
    "negative_age": {
        "ticker_slots": 1,
        "ohlcv_slots": 0,
        "balance_slots": 0,
        "ticker_fetches": 1,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 1,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": -3.0,
        "oldest_age_s": -1.0,
        "stale_slots": 0,
    },
    "infinite_age": {
        "ticker_slots": 1,
        "ohlcv_slots": 0,
        "balance_slots": 0,
        "ticker_fetches": 1,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 1,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": float("inf"),
        "oldest_age_s": float("-inf"),
        "stale_slots": 0,
    },
    "not_a_number_age": {
        "ticker_slots": 1,
        "ohlcv_slots": 0,
        "balance_slots": 0,
        "ticker_fetches": 1,
        "ohlcv_fetches": 0,
        "balance_fetches": 0,
        "ticker_hits": 1,
        "ohlcv_hits": 0,
        "balance_hits": 0,
        "freshest_age_s": float("nan"),
        "oldest_age_s": float("nan"),
        "stale_slots": 0,
    },
    "missing_a_key": {"ohlcv_slots": 1},
    "text_where_a_number_belongs": {
        "ticker_slots": "two",
        "ohlcv_slots": 0,
        "balance_slots": 0,
    },
}

POOL_REFUSING = ("missing_a_key", "text_where_a_number_belongs")

COMMANDS = ("start", "pause", "stop", "restart", "delete")


# Reading the two sides into one shape


def numbered(value):
    """One value with every number replaced by its own text.

    ``12`` and ``12.0`` are equal as numbers and hash apart, and two
    not-a-numbers are never equal to each other. Reading each number as
    its own text tells the first pair apart and lets the second pair
    agree.
    """
    if isinstance(value, bool):
        return ["bool", repr(value)]
    if isinstance(value, (int, float)):
        return [type(value).__name__, repr(value)]
    if isinstance(value, dict):
        return {key: numbered(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [numbered(item) for item in value]
    return value


TICKER_MARK = "<a news strip this machine happened to build>"
SEEDED_TICKER_STARTS = frozenset({0})


def platform_chosen(value):
    """One value with anything the machine chose replaced by a marker.

    Whether the replacement news strip really started is the machine's
    answer, not the product's. Everything this test seeded is kept.
    """
    if isinstance(value, dict):
        found = {}
        for key, item in value.items():
            if key == "ticker_starts" and item not in SEEDED_TICKER_STARTS:
                found[key] = TICKER_MARK
            else:
                found[key] = platform_chosen(item)
        return found
    if isinstance(value, (list, tuple)):
        return [platform_chosen(item) for item in value]
    return value


def readable(value):
    """One value ready to compare: machine values hidden, numbers as text."""
    return numbered(platform_chosen(value))


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(readable(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one drive, keeping either that it worked or how it refused.

    Only the refusal TYPE is kept. Python words one failure differently
    between versions, so a wording written down here would pin the
    machine this file was written on.
    """
    try:
        run()
        return {"error": ""}
    except Exception as exc:
        return {"error": type(exc).__name__}


def headline_of(run):
    """The first line of a refusal, read off whichever side is driven."""
    try:
        run()
        return ""
    except Exception as exc:
        return str(exc).splitlines()[:1]


def shown(widget):
    """Whether one widget was asked to be shown.

    ``isVisible`` answers False for every child of a window that was
    never opened, so it reads the platform rather than the ask.
    ``isHidden`` carries the ask itself.
    """
    return not widget.isHidden()


def old_tab(
    exchange_id=EXCHANGE_ID,
    exchange_name=EXCHANGE_NAME,
    names=(),
    ticker=True,
    **wiring,
):
    """One real exchange screen, driven through the named cases."""
    app()
    if not ticker:
        broken_ticker()
    tab = hold(shipped.ExchangeTab(exchange_id, exchange_name, **wiring))
    tab._pull_rate_timer.stop()
    for name in names:
        tab.update_bots(CASES[name])
    return tab


def broken_ticker():
    """Make the news strip refuse to be built, for this call only."""
    from src.gui import crypto_news_ticker

    class RefusingTicker:
        def __init__(self):
            raise RuntimeError("no feed")

    crypto_news_ticker.CryptoNewsTicker = RefusingTicker


def new_model(
    exchange_id=EXCHANGE_ID,
    exchange_name=EXCHANGE_NAME,
    names=(),
    ticker=True,
    **wiring,
):
    """One surface screen, driven through the named cases."""

    def build():
        return object()

    model = surface.ExchangeTabModel(
        exchange_id,
        exchange_name,
        news_ticker_factory=build if ticker else None,
        **wiring,
    )
    for name in names:
        model.update_bots(CASES[name])
    return model


def read_old(tab):
    """One shipped screen read into the one shape both sides use."""
    layout = tab.layout()
    command_bar = layout.itemAt(layout.count() - 1).layout()
    header = layout.itemAt(0).layout()
    return {
        "exchange_id": tab.exchange_id,
        "exchange_name": tab._exchange_name,
        "privacy_label": tab._privacy_mode_btn.text(),
        "privacy_tooltip": tab._privacy_mode_btn.toolTip(),
        "privacy_style": tab._privacy_mode_btn.styleSheet(),
        "privacy_focus": tab._privacy_mode_btn.focusPolicy().name,
        "add_bot_label": tab._add_bot_btn.text(),
        "add_bot_accent": tab._add_bot_btn.property("accent"),
        "pull_rate_text": tab._pull_rate_lbl.text(),
        "pull_rate_style": tab._pull_rate_lbl.styleSheet(),
        "pull_rate_tooltip": tab._pull_rate_lbl.toolTip(),
        "pull_rate_interval_ms": tab._pull_rate_timer.interval(),
        "scrum_label": tab._scrum_label.text(),
        "scrum_style": tab._scrum_label.styleSheet(),
        "scrum_visible": shown(tab._scrum_label),
        "scrum_table_visible": shown(tab._bot_table),
        "extractor_label": tab._extractor_label.text(),
        "extractor_style": tab._extractor_label.styleSheet(),
        "extractor_visible": shown(tab._extractor_label),
        "extractor_table_visible": shown(tab._extractor_table),
        "commands": [
            [
                command_bar.itemAt(index).widget().text(),
                bool(command_bar.itemAt(index).widget().property("danger")),
            ]
            for index in range(command_bar.count())
        ],
        "header_items": header.count(),
        "ticker_built": hasattr(tab, "_news_ticker"),
        "ticker_starts": len(QUIET_TICKER_STARTS),
        "last_clicked_table": tab._last_clicked_table,
        "scrum_table": read_old_table(tab._bot_table),
        "extractor_table": read_old_table(tab._extractor_table),
    }


def read_old_table(table):
    """One real bot table read as far as the screen reads it."""
    return {
        "bot_ids": list(table._bot_ids),
        "row_count": table.rowCount(),
        "drawn_rows": sum(
            1 for row in range(table.rowCount()) if table.item(row, 0) is not None
        ),
        "current_row": table.currentRow(),
        "has_selection": bool(table.selectedItems()),
        "selected_bot_id": table.get_selected_bot_id(),
    }


def read_new(payload):
    """One surface screen read into the one shape both sides use."""
    return {
        "exchange_id": payload["exchange_id"],
        "exchange_name": payload["exchange_name"],
        "privacy_label": payload["privacy_label"],
        "privacy_tooltip": payload["privacy_tooltip"],
        "privacy_style": payload["privacy_style"],
        "privacy_focus": payload["privacy_focus_policy"],
        "add_bot_label": payload["add_bot_label"],
        "add_bot_accent": payload["add_bot_accent"],
        "pull_rate_text": payload["pull_rate_text"],
        "pull_rate_style": payload["pull_rate_style"],
        "pull_rate_tooltip": payload["pull_rate_tooltip"],
        "pull_rate_interval_ms": payload["pull_rate_interval_ms"],
        "scrum_label": payload["scrum_section_label"],
        "scrum_style": payload["scrum_section_style"],
        "scrum_visible": payload["scrum_section_visible"],
        "scrum_table_visible": payload["scrum_section_visible"],
        "extractor_label": payload["extractor_section_label"],
        "extractor_style": payload["extractor_section_style"],
        "extractor_visible": payload["extractor_section_visible"],
        "extractor_table_visible": payload["extractor_section_visible"],
        "commands": [
            [label, label == payload["danger_command_label"]]
            for label, _command in payload["command_buttons"]
        ],
        "header_items": HEADER_ITEM_COUNT,
        "ticker_built": payload["news_ticker_built"],
        "ticker_starts": payload["news_ticker_started"],
        "last_clicked_table": payload["last_clicked_table"],
        "scrum_table": read_new_table(payload["scrum_table"]),
        "extractor_table": read_new_table(payload["extractor_table"]),
    }


HEADER_ITEM_COUNT = 3


def read_new_table(found):
    """One surface bot table read as far as the screen reads it."""
    return {
        "bot_ids": list(found["bot_ids"]),
        "row_count": found["row_count"],
        "drawn_rows": found["drawn_rows"],
        "current_row": found["current_row"],
        "has_selection": found["has_selection"],
        "selected_bot_id": found["selected_bot_id"],
    }


def pin_shape(pins):
    """Every recorded check in the one shape both sides are read into."""
    return [
        {
            "name": pin["name"],
            "actual": pin["actual"],
            "expected": pin["expected"],
            "every": pin["every"],
            "instance": pin["instance"],
            "context": dict(pin["context"] or {}),
            "verdict": pin.get("verdict"),
            "seconds": pin.get("seconds"),
        }
        for pin in pins
    ]


def fresh_register():
    """Hand out a new privacy register, so one side cannot decide the other.

    The register is process-wide and the Privacy button writes to it. The
    shipped screen and the surface both reach it through one accessor, so
    without this the first side to press leaves the second side pressing
    the opposite way.
    """
    import tempfile

    from src.core import privacy_mask_registry as registry_module

    registry_module._SINGLETON = registry_module.PrivacyMaskRegistry(
        settings_path=Path(tempfile.gettempdir()) / "never-written.json",
        autosave=False,
    )
    return registry_module._SINGLETON


def drive(names, presses=(), after=(), commands=(), pool=None, privacy=0):
    """Both sides through the same steps, read into one shape.

    Every step is guarded on its own, so a step that refuses does not
    swallow the steps after it and the two sides are compared on WHICH
    step refused as well as on what they hold.
    """
    QUIET_TICKER_STARTS.clear()
    PINS_SEEN.clear()
    fresh_register()
    old_log = RecordingLog()
    old_sent: list = []
    old_opened: list = []
    tab = old_tab(
        status_log=old_log,
        on_bot_cmd=lambda bot_id, command: old_sent.append([bot_id, command]),
        on_bot_clicked=old_opened.append,
    )
    old_outcome = [
        guarded(step)
        for step in old_steps(tab, names, presses, after, commands, pool, privacy)
    ]
    old_state = read_old(tab)
    old_pins = pin_shape(PINS_SEEN)

    fresh_register()
    new_log = RecordingLog()
    new_sent: list = []
    new_opened: list = []
    model = new_model(
        status_log=new_log,
        on_bot_cmd=lambda bot_id, command: new_sent.append([bot_id, command]),
        on_bot_clicked=new_opened.append,
    )
    new_outcome = [
        guarded(step)
        for step in new_steps(model, names, presses, after, commands, pool, privacy)
    ]
    new_state = read_new(surface.build_view_model(model))
    new_pins = pin_shape(model.pins)
    return {
        "old": old_state,
        "new": new_state,
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "old_pins": old_pins,
        "new_pins": new_pins,
        "old_log": old_log.lines,
        "new_log": new_log.lines,
        "old_sent": old_sent,
        "new_sent": new_sent,
        "old_opened": old_opened,
        "new_opened": new_opened,
    }


class RecordingLog:
    """The status strip, recording what the screen wrote to it."""

    def __init__(self):
        self.lines: list = []

    def log(self, message, level="info"):
        self.lines.append([message, level])


def old_steps(tab, names, presses, after, commands, pool, privacy):
    """Every step one shipped screen takes, each one on its own."""
    found = [lambda name=name: tab.update_bots(CASES[name]) for name in names]
    found += [
        lambda which=which, row=row: (
            tab._bot_table if which == "scrumming" else tab._extractor_table
        ).selectRow(row)
        for which, row in presses
    ]
    found += [lambda name=name: tab.update_bots(CASES[name]) for name in after]
    if pool is not None:
        found.append(lambda: with_pool(tab, pool))
    found += [lambda command=command: tab._cmd(command) for command in commands]
    found += [tab._on_global_privacy_clicked for _press in range(privacy)]
    return found


def with_pool(tab, name):
    """Drive the shipped freshness line from one invented pool report."""
    from src.exchange import data_pool

    summary = POOL_CASES[name]

    class InventedPool:
        def pull_rate_summary(self):
            return dict(summary)

    was = data_pool.get_data_pool
    data_pool.get_data_pool = lambda: InventedPool()
    try:
        tab._update_pull_rate_label()
    finally:
        data_pool.get_data_pool = was


def new_steps(model, names, presses, after, commands, pool, privacy):
    """Every step one surface screen takes, each one on its own."""
    found = [lambda name=name: model.update_bots(CASES[name]) for name in names]
    found += [
        lambda which=which, row=row: (
            model.select_scrum_row(row)
            if which == "scrumming"
            else model.select_extractor_row(row)
        )
        for which, row in presses
    ]
    found += [lambda name=name: model.update_bots(CASES[name]) for name in after]
    if pool is not None:
        found.append(lambda: with_surface_pool(model, pool))
    found += [lambda command=command: model.cmd(command) for command in commands]
    found += [model.on_global_privacy_clicked for _press in range(privacy)]
    return found


def with_surface_pool(model, name):
    """Drive the surface freshness line from one invented pool report."""
    summary = POOL_CASES[name]
    model.pool_reader = lambda: dict(summary)
    model.update_pull_rate_label()


def both_sides_agree(run, note):
    """Fail unless the two sides did the same thing and hold the same state."""
    assert (
        run["old_outcome"] == run["new_outcome"]
    ), "%s: the shipped screen and the surface refused differently: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        readable(run["old"]),
        readable(run["new"]),
    )
    assert digest(run["old"]) == digest(run["new"]), "%s: %s against %s" % (
        note,
        digest(run["old"]),
        digest(run["new"]),
    )
    assert readable(run["old_pins"]) == readable(
        run["new_pins"]
    ), "%s: %r against %r" % (
        note,
        run["old_pins"],
        run["new_pins"],
    )
    assert run["old_log"] == run["new_log"], (note, run["old_log"], run["new_log"])
    assert run["old_sent"] == run["new_sent"], (note, run["old_sent"], run["new_sent"])
    assert run["old_opened"] == run["new_opened"], note


# The two sides, case by case


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_screen_is_the_shipped_screens(name):
    """The surface describes a screen the shipped screen does not build."""
    both_sides_agree(drive([name]), name)


def test_every_case_in_the_table_is_driven():
    """A case sits in the table that nothing ever drives."""
    driven = set()
    for name in CASES:
        both_sides_agree(drive([name]), name)
        driven.add(name)
    for name, steps in SEQUENCES.items():
        both_sides_agree(drive(steps), name)
        driven.update(steps)
    assert driven == set(CASES), sorted(driven ^ set(CASES))
    assert len(CASES) == len(driven)
    assert set(PICTURE_CASES) <= set(CASES), sorted(set(PICTURE_CASES) - set(CASES))
    assert set(REFUSING) <= set(CASES), sorted(set(REFUSING) - set(CASES))


@pytest.mark.parametrize("name", sorted(POOL_CASES))
def test_the_freshness_line_is_the_shipped_line(name):
    """The surface writes a different data-pool line than the shipped screen."""
    both_sides_agree(drive(["happy"], pool=name), name)


def test_every_pool_report_in_the_table_is_driven():
    """A pool report sits in the table that nothing ever drives."""
    driven = set()
    for name in POOL_CASES:
        both_sides_agree(drive(["happy"], pool=name), name)
        driven.add(name)
    assert driven == set(POOL_CASES)
    assert set(POOL_REFUSING) <= set(POOL_CASES)


@pytest.mark.parametrize("command", COMMANDS)
def test_each_command_button_is_the_shipped_button(command):
    """One of the five commands reaches a different bot on the two sides."""
    run = drive(["three_rows"], presses=[["scrumming", 1]], commands=[command])
    both_sides_agree(run, command)
    assert run["old_sent"] == [["beta", command]], run["old_sent"]


def test_the_sample_hashes_are_reported():
    """The comparison reports no hash, so nothing can be checked by hand."""
    happy = drive(["happy"])
    empty = drive(["empty"])
    assert len(digest(happy["old"])) == 64
    assert digest(happy["old"]) == digest(happy["new"])
    assert digest(empty["old"]) == digest(empty["new"])
    assert digest(happy["old"]) != digest(empty["old"])


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash gives one value for every screen, so it tells nothing apart."""
    happy = drive(["happy"])
    rows = drive(["three_rows"])
    assert digest(happy["old"]) != digest(rows["new"]), "old happy against new rows"
    assert digest(rows["old"]) != digest(happy["new"]), "old rows against new happy"
    assert digest(happy["old"]) == digest(happy["new"])
    assert digest(rows["old"]) == digest(rows["new"])


def test_the_same_input_hashes_the_same_twice():
    """The hash moves between two runs of one input, so it reads the clock."""
    assert digest(drive(["happy"])["old"]) == digest(drive(["happy"])["old"])
    assert digest(drive(["happy"])["new"]) == digest(drive(["happy"])["new"])


def test_a_whole_number_and_a_decimal_are_told_apart():
    """The reader treats 12 and 12.0 as one value, so a change reads as none."""
    assert readable(12) != readable(12.0)
    assert digest({"a": 12}) != digest({"a": 12.0})
    assert readable(True) != readable(1)


def test_two_not_a_numbers_built_apart_compare_equal():
    """The reader calls two not-a-numbers different, reporting a false change."""
    first = float("nan")
    second = float("inf") - float("inf")
    assert first != second
    assert readable(first) == readable(second)
    assert digest({"a": first}) == digest({"a": second})
    assert readable(float("inf")) != readable(float("-inf"))


def test_the_machine_rule_keeps_a_seeded_value_and_hides_a_chosen_one():
    """The rule hiding the machine's answers hides a value this test seeded."""
    kept = readable({"row_count": 3, "ticker_starts": 0})
    assert kept["row_count"] == ["int", "3"]
    assert kept["ticker_starts"] == ["int", "0"]
    hidden = platform_chosen({"ticker_starts": 4})
    assert hidden["ticker_starts"] == TICKER_MARK
    assert platform_chosen({"ticker_starts": 0})["ticker_starts"] == 0


# What each side DID: answered, or refused with which type


def refusals(outcome):
    """The refusal type of every step that refused, in order."""
    return [step["error"] for step in outcome if step["error"]]


def outcomes(names):
    """How the shipped screen refused each named case, if it did."""
    return {name: refusals(drive([name])["old_outcome"]) for name in names}


def test_the_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    found = outcomes(sorted(CASES))
    answered = [name for name, done in found.items() if not done]
    refused = [name for name, done in found.items() if done]
    assert answered, found
    assert refused, found
    assert sorted(refused) == sorted(REFUSING), sorted(set(refused) ^ set(REFUSING))
    assert len(answered) + len(refused) == len(CASES)


@pytest.mark.parametrize("name", sorted(REFUSING))
def test_a_refused_input_refuses_the_same_way_on_both_sides(name):
    """One side answered an input the other refused, or refused differently."""
    run = drive([name])
    assert refusals(run["old_outcome"]), name
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    both_sides_agree(run, name)


@pytest.mark.parametrize("name", sorted(POOL_REFUSING))
def test_a_refused_pool_report_refuses_the_same_way_on_both_sides(name):
    """A pool report one side refuses is answered by the other."""
    run = drive(["happy"], pool=name)
    assert refusals(run["old_outcome"]), name
    assert run["old_outcome"] == run["new_outcome"], (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    both_sides_agree(run, name)


def test_the_refusal_comparison_holds_more_than_one_type():
    """Every refusal shares one type, so a swapped refusal reads as unchanged."""
    found = outcomes(sorted(REFUSING))
    kinds = {kind for done in found.values() for kind in done}
    assert len(kinds) > 1, found
    assert kinds == {"AttributeError", "TypeError", "ValueError"}, kinds
    assert guarded(lambda: 1) != guarded(lambda: 1 / 0)
    assert guarded(lambda: int("x"))["error"] == "ValueError"


def test_the_refusal_reader_reports_two_different_wordings():
    """Two refusals worded apart read the same, so a wording change is unseen.

    Both wordings are read off the shipped side. Neither is written down:
    Python words one failure differently between its own versions.
    """
    first = headline_of(lambda: old_tab(names=["state_is_a_number"]))
    second = headline_of(lambda: old_tab(names=["holdings_is_text"]))
    assert first, "the shipped screen answered an input it should refuse"
    assert second, "the shipped screen answered an input it should refuse"
    assert first != second, (first, second)
    assert headline_of(lambda: None) == ""


# Step sequences, including one that refuses part way


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_a_step_sequence_is_the_shipped_screens(name):
    """A rewrite left the surface holding rows the shipped screen does not."""
    both_sides_agree(drive(SEQUENCES[name]), name)


def test_a_shrink_then_a_refusal_leaves_the_same_rows_on_both_sides():
    """A shrink that refuses part way left different rows on the two sides."""
    run = drive(SEQUENCES["shrink_then_refuse"])
    both_sides_agree(run, "shrink_then_refuse")
    assert refusals(run["old_outcome"]) == ["AttributeError"]
    old_table = run["old"]["scrum_table"]
    assert old_table["row_count"] == len(CASES["three_rows_second_refuses"])
    assert old_table["bot_ids"] == ["alpha", "beta"]
    assert old_table["drawn_rows"] == 3, "a row left behind is not counted"
    assert run["new"]["scrum_table"]["drawn_rows"] == 3


def test_the_sequence_check_reports_a_row_left_behind():
    """The sequence check passes whatever a rewrite leaves on screen."""
    kept = drive(SEQUENCES["shrink_then_refuse"])
    fresh = drive(["three_rows_second_refuses"])
    assert (
        kept["old"]["scrum_table"]["row_count"]
        == fresh["old"]["scrum_table"]["row_count"]
    )
    assert digest(kept["old"]) != digest(fresh["old"]), "the left-behind row is unseen"
    assert fresh["old"]["scrum_table"]["drawn_rows"] == 2
    assert kept["old"]["scrum_table"]["drawn_rows"] == 3


def test_a_command_after_a_refused_rewrite_reaches_the_same_bot():
    """A refused rewrite left the two sides pointing at different bots."""
    run = drive(
        ["four_rows"],
        presses=[["scrumming", 3]],
        commands=["delete"],
    )
    both_sides_agree(run, "command after four rows")
    assert run["old_sent"] == [["delta", "delete"]]
    refused = drive(
        SEQUENCES["shrink_then_refuse"],
        presses=[["scrumming", 0]],
        commands=["delete"],
    )
    both_sides_agree(refused, "command after a refused shrink")
    assert refused["old_sent"] == [["alpha", "delete"]]
    assert [step["error"] for step in refused["old_outcome"]] == [
        "",
        "AttributeError",
        "",
        "",
    ]


# The highlight, the two tables, and where a command lands


def test_the_highlight_follows_the_bot_not_the_row():
    """A refresh left the highlight on a row holding a different bot."""
    run = drive(
        ["three_rows"],
        presses=[["scrumming", 2]],
        after=["three_rows_reordered"],
    )
    both_sides_agree(run, "reorder")
    assert run["old"]["scrum_table"]["selected_bot_id"] == "gamma"
    assert run["new"]["scrum_table"]["selected_bot_id"] == "gamma"


def test_a_bot_that_left_the_fleet_clears_the_highlight_on_both_sides():
    """The highlight stayed on a row after its bot left the fleet."""
    run = drive(["three_rows"], presses=[["scrumming", 2]])
    both_sides_agree(run, "before the bot left")
    assert run["old"]["scrum_table"]["selected_bot_id"] == "gamma"
    gone = drive(["three_rows"], presses=[["scrumming", 2]], after=["one_row"])
    assert gone["old"]["scrum_table"]["selected_bot_id"] == ""
    assert gone["new"]["scrum_table"]["selected_bot_id"] == ""


def test_highlighting_one_table_clears_the_other_on_both_sides():
    """Two rows stayed highlighted at once, so a command has two targets."""
    run = drive(
        ["both_kinds"],
        presses=[["scrumming", 0], ["extractor", 0]],
    )
    both_sides_agree(run, "extractor after scrumming")
    assert run["old"]["scrum_table"]["selected_bot_id"] == ""
    assert run["old"]["extractor_table"]["selected_bot_id"] == "ext-1"
    assert run["old"]["last_clicked_table"] == "extractor"
    back = drive(
        ["both_kinds"],
        presses=[["extractor", 0], ["scrumming", 0]],
    )
    both_sides_agree(back, "scrumming after extractor")
    assert back["old"]["extractor_table"]["selected_bot_id"] == ""
    assert back["old"]["last_clicked_table"] == "scrumming"


def test_a_command_reaches_the_table_the_operator_last_used():
    """A command landed on the bot in the table the operator did not choose."""
    run = drive(
        ["both_kinds"],
        presses=[["scrumming", 0], ["extractor", 0]],
        commands=["stop"],
    )
    both_sides_agree(run, "command after an extractor press")
    assert run["old_sent"] == [["ext-1", "stop"]]


def test_a_command_with_nothing_highlighted_writes_the_same_line():
    """The screen sent a command with no bot chosen, or said nothing about it."""
    run = drive(["three_rows"], commands=["stop"])
    both_sides_agree(run, "no highlight")
    assert run["old_sent"] == []
    assert run["old_log"] == [["Select a bot first.", "warning"]]
    assert run["new_log"] == [
        [surface.SELECT_FIRST_MESSAGE, surface.SELECT_FIRST_LEVEL]
    ]


def test_a_command_with_no_status_strip_still_sends_nothing():
    """A screen with no status strip refused differently on the two sides."""
    app()
    tab = old_tab()
    sent: list = []
    tab._on_bot_cmd = lambda bot_id, command: sent.append([bot_id, command])
    tab.update_bots(CASES["three_rows"])
    tab._cmd("stop")
    model = new_model(
        on_bot_cmd=lambda bot_id, command: sent.append([bot_id, command]),
    )
    model.update_bots(CASES["three_rows"])
    model.cmd("stop")
    assert sent == []
    assert model.logged == []


def test_a_command_with_no_handler_wired_sends_nothing_on_both_sides():
    """A screen with nothing wired to it refused differently on the two sides."""
    app()
    tab = old_tab(names=["three_rows"])
    tab._bot_table.selectRow(0)
    tab._cmd("delete")
    model = new_model(names=["three_rows"])
    model.select_scrum_row(0)
    model.cmd("delete")
    assert model.commands_sent == []
    assert read_old(tab)["scrum_table"]["selected_bot_id"] == "alpha"
    assert model.scrum_table.get_selected_bot_id() == "alpha"


def test_the_new_bot_button_names_its_own_exchange_on_both_sides():
    """The "+ New Bot" button asked for a bot on the wrong exchange."""
    app()
    asked: list = []
    tab = hold(
        shipped.ExchangeTab(OTHER_EXCHANGE_ID, "Kraken", on_new_bot=asked.append)
    )
    tab._pull_rate_timer.stop()
    tab._add_bot_btn.click()
    model = surface.ExchangeTabModel(
        OTHER_EXCHANGE_ID, "Kraken", on_new_bot=asked.append
    )
    model.on_new_bot_clicked()
    assert asked == [OTHER_EXCHANGE_ID, OTHER_EXCHANGE_ID]
    assert model.new_bot_asks == [OTHER_EXCHANGE_ID]


def test_a_new_bot_button_with_nothing_wired_asks_for_nothing():
    """An unwired button asked for a bot anyway."""
    app()
    tab = old_tab()
    tab._add_bot_btn.click()
    model = new_model()
    model.on_new_bot_clicked()
    assert model.new_bot_asks == []


def test_a_detail_press_chooses_its_own_table_on_both_sides():
    """A Detail press left the screen preferring the other table."""
    app()
    opened: list = []
    tab = old_tab(names=["both_kinds"], on_bot_clicked=opened.append)
    tab._extractor_table._on_detail("ext-1")
    model = new_model(names=["both_kinds"], on_bot_clicked=opened.append)
    model.extractor_clicked("ext-1")
    assert tab._last_clicked_table == "extractor"
    assert model.last_clicked_table == "extractor"
    assert opened == ["ext-1", "ext-1"]
    tab._bot_table._on_detail("scrum-1")
    model.scrum_clicked("scrum-1")
    assert tab._last_clicked_table == "scrumming"
    assert model.last_clicked_table == "scrumming"


# Privacy Mode


def test_the_privacy_button_flips_every_mask_on_both_sides():
    """The Privacy Mode button left some values on screen while it says hidden."""
    run = drive(["happy"], privacy=1)
    both_sides_agree(run, "one privacy press")
    assert run["old"]["privacy_label"] == surface.PRIVACY_LABEL_ON
    assert run["old"]["privacy_style"] == surface.PRIVACY_STYLE_ON
    assert all(registry().is_masked(found) for found in registry().known_field_ids())


def test_a_second_privacy_press_shows_every_value_again():
    """A second press left the values hidden, or the button lying about it."""
    run = drive(["happy"], privacy=2)
    both_sides_agree(run, "two privacy presses")
    assert run["old"]["privacy_label"] == surface.PRIVACY_LABEL_OFF
    assert run["old"]["privacy_style"] == surface.PRIVACY_STYLE_OFF
    assert not any(
        registry().is_masked(found) for found in registry().known_field_ids()
    )


def test_a_privacy_press_with_one_mask_already_set_hides_the_rest():
    """A part-hidden screen showed everything instead of hiding the rest."""
    app()
    field = registry().known_field_ids()[0]
    registry().set_masked(field, True)
    tab = old_tab()
    tab._on_global_privacy_clicked()
    assert tab._privacy_mode_btn.text() == surface.PRIVACY_LABEL_ON
    registry().set_all(False)
    registry().set_masked(field, True)
    model = new_model()
    model.on_global_privacy_clicked()
    assert model.privacy_label_text == surface.PRIVACY_LABEL_ON


def test_a_register_that_cannot_be_read_leaves_the_button_alone():
    """A broken register relabelled the button over a hidden screen."""
    app()

    def refuse():
        raise RuntimeError("register gone")

    before_register = registry()
    tab = old_tab()
    before = tab._privacy_mode_btn.text()
    model = new_model()
    was_shipped = shipped.get_privacy_mask_registry
    was_surface = surface.get_privacy_mask_registry
    shipped.get_privacy_mask_registry = refuse
    surface.get_privacy_mask_registry = refuse
    try:
        tab._on_global_privacy_clicked()
        model.on_global_privacy_clicked()
    finally:
        shipped.get_privacy_mask_registry = was_shipped
        surface.get_privacy_mask_registry = was_surface
    assert tab._privacy_mode_btn.text() == before
    assert model.privacy_label_text == before
    assert model.pins == []
    assert surface.PRIVACY_UNREADABLE in [call[0] for call in model.calls]
    assert registry() is before_register


def test_the_window_is_asked_to_repaint_after_a_privacy_press():
    """The other screens kept showing values this press was meant to hide."""
    app()
    asked: list = []

    class Window:
        def refresh_all_privacy_widgets(self):
            asked.append(1)

    model = new_model(window_refresh=Window().refresh_all_privacy_widgets)
    model.on_global_privacy_clicked()
    assert asked == [1]
    assert surface.WINDOW_REFRESHED in [call[0] for call in model.calls]
    quiet = new_model()
    quiet.on_global_privacy_clicked()
    assert surface.WINDOW_UNREACHABLE in [call[0] for call in quiet.calls]


def test_the_privacy_tooltip_names_a_count_the_register_does_not_hold():
    """The button's own words match the register, so no reader is misled.

    The tooltip both sides carry says eighteen fields. The register
    declares nineteen. The two sides carry the same words, which is what
    this file compares; the count itself is a defect in the shipped
    screen's tooltip.
    """
    app()
    declared = len(registry().known_field_ids())
    assert declared == 19, declared
    assert "ALL 18 privacy masks" in surface.PRIVACY_TOOLTIP
    assert old_tab()._privacy_mode_btn.toolTip() == surface.PRIVACY_TOOLTIP


# The five recorded checks


def test_the_recorded_checks_are_the_shipped_checks():
    """A check the shipped screen makes is missing from the surface."""
    run = drive(["both_kinds"])
    assert [pin["name"] for pin in run["old_pins"]] == [
        surface.PIN_EVERY_BOT_DRAWN,
        surface.PIN_SELECTION_SURVIVES,
    ]
    assert readable(run["old_pins"]) == readable(run["new_pins"])
    pressed = drive(["three_rows"], presses=[["scrumming", 0]], commands=["stop"])
    assert surface.PIN_COMMAND_ROUTED in [pin["name"] for pin in pressed["old_pins"]]
    flipped = drive(["happy"], privacy=1)
    names = [pin["name"] for pin in flipped["old_pins"]]
    assert surface.PIN_PRIVACY_APPLIED in names
    assert surface.PIN_PRIVACY_BUTTON in names
    assert len(set(names)) == 4


def test_a_dropped_bot_turns_the_coverage_check_red_on_both_sides():
    """A bot that reaches no table is counted as if it had been drawn."""
    run = drive(["wrong_capitals"])
    both_sides_agree(run, "wrong_capitals")
    drawn = [
        pin for pin in run["old_pins"] if pin["name"] == surface.PIN_EVERY_BOT_DRAWN
    ]
    assert drawn[0]["actual"] == 0
    assert drawn[0]["expected"] == 1
    healthy = drive(["happy"])
    good = [
        pin for pin in healthy["old_pins"] if pin["name"] == surface.PIN_EVERY_BOT_DRAWN
    ]
    assert good[0]["actual"] == good[0]["expected"] == 1


def test_the_check_recorder_can_report():
    """The recorder sees nothing whatever the screen sends, so silence is empty."""
    from src.core import signal_contract

    PINS_SEEN.clear()
    signal_contract.emit("a.seeded.check", actual=1, expected=1)
    assert [pin["name"] for pin in PINS_SEEN] == ["a.seeded.check"]
    PINS_SEEN.clear()
    guarded(lambda: old_tab(names=["state_is_a_number"]))
    assert PINS_SEEN == [], "a refused rewrite recorded a check"
    signal_contract.emit("after.the.refusal", actual=0)
    assert [pin["name"] for pin in PINS_SEEN] == ["after.the.refusal"]


def test_each_screen_names_its_own_exchange_in_every_check():
    """Two exchanges share one check, so a stopped screen hides behind another."""
    app()
    PINS_SEEN.clear()
    first = old_tab(EXCHANGE_ID, EXCHANGE_NAME)
    first.update_bots(CASES["happy"])
    second = old_tab(OTHER_EXCHANGE_ID, "Kraken")
    second.update_bots(CASES["happy"])
    named = {pin["instance"] for pin in PINS_SEEN if pin["instance"]}
    assert named == {EXCHANGE_ID, OTHER_EXCHANGE_ID}, named
    model = new_model(OTHER_EXCHANGE_ID, "Kraken", names=["happy"])
    assert {pin["instance"] for pin in model.pins} == {OTHER_EXCHANGE_ID}


# The surface holds its own values


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    before = shipped.ds.TEXT_MED
    moved_label = "Renamed Section"
    kept_style = surface.SCRUM_SECTION_STYLE
    shipped.ds.TEXT_MED = "#123456"
    try:
        moved = read_old(old_tab())
        moved["scrum_label"] = moved_label
        kept = read_new(surface.build_view_model(new_model()))
        assert "#123456" in moved["scrum_style"]
        assert kept["scrum_style"] == kept_style
        assert "#123456" not in kept["scrum_style"]
        differences = [
            key
            for key in sorted(set(moved) & set(kept))
            if readable(moved[key]) != readable(kept[key])
        ]
        assert differences == [
            "extractor_style",
            "privacy_style",
            "scrum_label",
            "scrum_style",
        ], differences
    finally:
        shipped.ds.TEXT_MED = before
    both_sides_agree(drive(["happy"]), "after the value was put back")


#: Refuses one module prefix at the meta path, then imports another and reports.
BLOCKED_IMPORT_PROBE = """
import importlib.abc
import json
import sys


class _Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        for blocked in %r:
            if name == blocked or name.startswith(blocked + '.'):
                raise ImportError('blocked in this probe: ' + name)
        return None


sys.meta_path.insert(0, _Refuse())
answer = {'imported': False, 'error': ''}
try:
    __import__(%r)
    answer['imported'] = True
except Exception as exc:
    answer['error'] = '%%s: %%s' %% (type(exc).__name__, exc)
answer['loaded'] = sorted(
    m for m in sys.modules if any(m.startswith(b) for b in %r))
print(json.dumps(answer))
"""

TAB_PATH = REPO_ROOT / "src/gui/widgets/exchange_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/exchange_tab_surface.py"
SHIPPED_TAB_MODULE = "src.gui.widgets.exchange_tab"
SURFACE_MODULE = "src.gui.main_tabs.exchange_tab_surface"


def blocked_import(blocked, module):
    """Import ``module`` in a fresh process with ``blocked`` refused, and report."""
    return run_script(BLOCKED_IMPORT_PROBE % (blocked, module, blocked))


def test_the_shipped_file_is_not_named_by_the_surface():
    """The surface reaches into the widget it replaces.

    ``blocked_import`` refuses ``SHIPPED_TAB_MODULE`` at the meta path, so a
    transitive import through any other module is refused too.
    """
    answered = blocked_import((SHIPPED_TAB_MODULE,), SURFACE_MODULE)
    assert answered["imported"] is True, answered
    assert answered["loaded"] == [], answered


def test_the_import_probe_refuses_the_shipped_tab():
    """POSITIVE CONTROL. ``blocked_import`` reports ``exchange_tab`` as
    unimportable, so the green above is a fact about the surface."""
    answered = blocked_import((SHIPPED_TAB_MODULE,), SHIPPED_TAB_MODULE)
    assert answered["imported"] is False, answered
    assert "blocked in this probe" in answered["error"], answered


# Counting what each side wires, waits on, and builds, off the built object


def classes_of(module):
    """Every class ``module`` declares itself, by name."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def test_the_screen_wires_its_signals_and_the_surface_wires_none():
    """A wiring appeared on one side and not the other.

    ``connections`` counts what building each side really wires, so a signal
    connected inside a widget the tab builds is counted the same as a literal one.
    """
    from tests.fixtures.qt_wiring_counts import connections

    app()
    wired, tab = connections(lambda: old_tab(names=["happy"]))
    assert tab is not None
    assert wired == TAB_CONNECTIONS == 13, wired

    surface_wired, model = connections(lambda: new_model(names=["happy"]))
    assert model is not None
    assert surface_wired == 0, surface_wired


def test_the_surface_names_one_action_per_thing_the_operator_can_do():
    """Each entry of ``ACTIONS`` names a real ``ExchangeTabModel`` method."""
    assert len(surface.ACTIONS) == SURFACE_ACTION_TOTAL == 6
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.ExchangeTabModel, name)), name


def test_the_connection_counter_can_report_a_wiring():
    """POSITIVE CONTROL for ``connections``. ``PrivacyDot`` wires one signal while
    it is built and is counted as one."""
    from tests.fixtures.qt_wiring_counts import connections
    from src.gui.widgets.privacy_dot import PrivacyDot

    app()
    wired, dot = connections(lambda: PrivacyDot("exchange_tab.probe"))
    hold(dot)
    assert wired == 1, wired


def test_the_screen_starts_one_timer_and_the_surface_names_one_wait():
    """A wait appeared on one side and not the other."""
    from PySide6.QtCore import QObject, QTimer

    app()
    started: list = []
    first_start = QObject.startTimer
    first_timer = QTimer.start
    first_single = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return first_start(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return first_timer(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return first_single(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        old_tab(names=["happy"])
        old_started = list(started)
        started.clear()
        new_model(names=["happy"])
        new_started = list(started)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert [name for name, _args in old_started] == ["QTimer.start"], old_started
    assert new_started == []
    assert surface.TIMERS == {"pull_rate": surface.PULL_RATE_INTERVAL_MS}
    assert surface.TIMER_DELAYS_MS == (surface.PULL_RATE_INTERVAL_MS,)
    assert len(surface.TIMERS) == TAB_TIMER_BUILDS


def declared_signals(owner):
    """Every ``Signal`` a class declares, by name."""
    from PySide6.QtCore import Signal

    return {n for n, v in vars(owner).items() if isinstance(v, Signal)}


def test_the_screen_declares_no_signal_of_its_own():
    """A signal declaration appeared on one side and not the other."""
    app()
    assert declared_signals(shipped.ExchangeTab) == set()
    assert len(declared_signals(shipped.ExchangeTab)) == TAB_SIGNAL_BUILDS
    assert declared_signals(surface.ExchangeTabModel) == set()


def test_the_signal_reader_can_report_a_declaration():
    """POSITIVE CONTROL. ``ModeCard`` declares a signal, so the empty sets above
    are facts about ``ExchangeTab``."""
    from src.gui.launcher import ModeCard

    app()
    assert declared_signals(ModeCard), "the signal reader cannot report"


def test_the_screen_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    from tests.fixtures.qt_wiring_counts import bus_subscriptions

    app()
    subscribed, tab = bus_subscriptions(lambda: old_tab(names=["happy"]))
    assert tab is not None
    assert subscribed == TAB_BUS_SITES == 0, subscribed

    surface_subscribed, model = bus_subscriptions(lambda: new_model(names=["happy"]))
    assert model is not None
    assert surface_subscribed == 0, surface_subscribed
    assert surface.BUS_TOPICS == ()


def test_the_bus_counter_can_report_a_subscription():
    """POSITIVE CONTROL for ``bus_subscriptions``. ``_subscribe_once`` takes one
    topic and is counted as one."""
    from tests.fixtures.qt_wiring_counts import bus_subscriptions
    from src.core.event_bus import get_event_bus

    def _subscribe_once():
        return get_event_bus().subscribe("exchange_tab.probe", lambda _e: None)

    seen, off = bus_subscriptions(_subscribe_once)
    off()
    assert seen == 1, seen


def screen_elements(widget):
    """Every Qt child widget one built screen carries."""
    from PySide6.QtWidgets import QWidget

    return widget.findChildren(QWidget)


def test_the_screen_builds_the_elements_it_is_counted_for():
    """The element counter cannot report, so its number means nothing."""
    app()
    built = screen_elements(old_tab(names=["happy"]))
    assert len(built) == TAB_ELEMENTS, len(built)


def test_the_surface_builds_no_screen_element_at_all():
    """The surface answers with a model, and a model is not a Qt widget."""
    from PySide6.QtWidgets import QWidget

    app()
    assert not isinstance(new_model(names=["happy"]), QWidget)


def test_the_element_counter_can_report_a_child():
    """POSITIVE CONTROL for ``screen_elements``. ``StatCard`` carries children and
    is counted for them."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    app()
    card = hold(StatCard("label", "value"))
    assert len(screen_elements(card)) == STAT_CARD_ELEMENTS, len(screen_elements(card))


def test_the_tab_declares_one_class_of_its_own():
    """``ExchangeTab`` is the only class ``src.gui.widgets.exchange_tab`` declares."""
    import inspect

    app()
    declared = {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }
    assert declared == {"ExchangeTab"}, sorted(declared)


# Every class and every method has a counterpart


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


CLASS_MAP = {"ExchangeTab": "ExchangeTabModel"}

METHOD_MAP = {
    "ExchangeTab.__init__": "ExchangeTabModel.__init__",
    "ExchangeTab._update_pull_rate_label": "ExchangeTabModel.update_pull_rate_label",
    "ExchangeTab._cmd": "ExchangeTabModel.cmd",
    "ExchangeTab.update_bots": "ExchangeTabModel.update_bots",
    "ExchangeTab._on_global_privacy_clicked": (
        "ExchangeTabModel.on_global_privacy_clicked"
    ),
    "ExchangeTab._refresh_privacy_mode_btn_style": (
        "ExchangeTabModel.refresh_privacy_mode_btn_style"
    ),
}

HELPER_MAP = {
    "_scrum_clicked": "ExchangeTabModel.scrum_clicked",
    "_extractor_clicked": "ExchangeTabModel.extractor_clicked",
    "_on_scrum_selection_changed": "ExchangeTabModel.on_scrum_selection_changed",
    "_on_extractor_selection_changed": (
        "ExchangeTabModel.on_extractor_selection_changed"
    ),
    "add_bot_button": "ExchangeTabModel.on_new_bot_clicked",
    "news_ticker_slot": "ExchangeTabModel.build_news_ticker",
    "hosted_table": "HostedTableModel",
    "bridge_handler": "view_model",
    "shared_screen": "pane_model",
    "model_from_statuses": "build_model",
    "whole_state": "build_view_model",
    "privacy_button_words": "privacy_label",
    "privacy_button_colours": "privacy_style",
    "freshness_line": "pull_rate_text",
    "cache_share": "hit_rate_pct",
    "route_by_mode": "statuses_for",
    "row_refusal": "refusing_check",
    "one_row_check": "check_refuses",
    "one_table_read": "table_view",
}

TAB_MODEL_MEMBERS = {
    "__init__",
    "build_news_ticker",
    "on_new_bot_clicked",
    "update_pull_rate_label",
    "scrum_clicked",
    "extractor_clicked",
    "on_scrum_selection_changed",
    "on_extractor_selection_changed",
    "select_scrum_row",
    "select_extractor_row",
    "update_bots",
    "cmd",
    "on_global_privacy_clicked",
    "refresh_privacy_mode_btn_style",
}

HOSTED_TABLE_MEMBERS = {
    "__init__",
    "row_count",
    "set_row_count",
    "drawn_rows",
    "get_selected_bot_id",
    "selected_items",
    "select_row",
    "clear_selection",
    "set_current_cell",
    "block_signals",
    "update_bots",
    "reanchor",
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


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    app()
    assert shipped_classes() == set(CLASS_MAP)
    assert len(CLASS_MAP) == 1
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 6
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 19
    assert members(surface.ExchangeTabModel) == TAB_MODEL_MEMBERS, sorted(
        members(surface.ExchangeTabModel) ^ TAB_MODEL_MEMBERS
    )
    assert len(TAB_MODEL_MEMBERS) == 14
    assert members(surface.HostedTableModel) == HOSTED_TABLE_MEMBERS, sorted(
        members(surface.HostedTableModel) ^ HOSTED_TABLE_MEMBERS
    )
    assert len(HOSTED_TABLE_MEMBERS) == 12
    assert classes_of(shipped) == set(CLASS_MAP)


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "update_bots" in members(shipped.ExchangeTab)
    assert "_cmd" in members(shipped.ExchangeTab)
    assert "ExchangeTab" not in TAB_MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("ExchangeTabModel.no_such_member")
    assert TAB_MODEL_MEMBERS - {"update_bots"} != TAB_MODEL_MEMBERS
    assert members(surface.ExchangeTabModel) - {"cmd"} != TAB_MODEL_MEMBERS
    assert HOSTED_TABLE_MEMBERS - {"reanchor"} != HOSTED_TABLE_MEMBERS
    assert set(METHOD_MAP) - {"ExchangeTab.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"ExchangeTab"} != shipped_classes()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    app()
    assert list(inspect.signature(shipped.ExchangeTab.__init__).parameters) == [
        "self",
        "exchange_id",
        "exchange_name",
        "on_new_bot",
        "on_bot_clicked",
        "on_bot_cmd",
        "on_bot_fire",
        "status_log",
        "parent",
    ]
    new_start = list(inspect.signature(surface.ExchangeTabModel.__init__).parameters)
    assert new_start[:8] == [
        "self",
        "exchange_id",
        "exchange_name",
        "on_new_bot",
        "on_bot_clicked",
        "on_bot_cmd",
        "on_bot_fire",
        "status_log",
    ]
    assert list(inspect.signature(shipped.ExchangeTab.update_bots).parameters) == list(
        inspect.signature(surface.ExchangeTabModel.update_bots).parameters
    )
    old_cmd = list(inspect.signature(shipped.ExchangeTab._cmd).parameters)
    new_cmd = list(inspect.signature(surface.ExchangeTabModel.cmd).parameters)
    assert old_cmd == new_cmd == ["self", "command"]
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


def test_the_screen_is_reached_by_the_window_and_the_surface_by_the_bridge():
    """The count of readers is wrong, so a lost reader would pass unseen."""
    readers = modules_importing("exchange_tab", skip=(SURFACE_PATH, TAB_PATH))
    assert readers == [str(REPO_ROOT / "src/gui/main_window.py")], readers
    assert modules_importing("exchange_tab_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    known = modules_importing("design_system")
    assert len(known) > 5, known


# The screen paints, and the two sides paint the same pixels


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def old_tab_for_picture(name):
    """One shipped screen with its two bot tables out of the frame.

    Each bot table is its own screen and its own comparison. What is
    compared here is the part this screen owns: the header, the
    freshness line, the two headings and the command bar. The news strip
    is made to refuse on both sides, so the header holds plain space and
    nothing on it depends on a feed.
    """
    app()
    tab = old_tab(names=[name], ticker=False)
    tab._bot_table.setVisible(False)
    tab._extractor_table.setVisible(False)
    return tab


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    return sealed(surface.build_view_model(new_model(names=[name], ticker=False)))


def screen_painted_by_the_model(payload):
    """One screen built only from the surface's view model."""
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt

    payload = unaltered(payload)
    app()
    screen = hold(QWidget())
    layout = QVBoxLayout(screen)
    header = QHBoxLayout()
    privacy = QPushButton(payload["privacy_label"])
    privacy.setToolTip(payload["privacy_tooltip"])
    privacy.setFocusPolicy(Qt.NoFocus)
    privacy.setStyleSheet(payload["privacy_style"])
    header.addWidget(privacy)
    if payload["header_stretch"]:
        header.addStretch()
    add_bot = QPushButton(payload["add_bot_label"])
    add_bot.setProperty("accent", payload["add_bot_accent"])
    header.addWidget(add_bot)
    layout.addLayout(header)
    freshness = QLabel(payload["pull_rate_text"])
    freshness.setStyleSheet(payload["pull_rate_style"])
    freshness.setToolTip(payload["pull_rate_tooltip"])
    layout.addWidget(freshness)
    scrum = QLabel(payload["scrum_section_label"])
    scrum.setStyleSheet(payload["scrum_section_style"])
    layout.addWidget(scrum)
    scrum.setVisible(payload["scrum_section_visible"])
    extractor_label = QLabel(payload["extractor_section_label"])
    extractor_label.setStyleSheet(payload["extractor_section_style"])
    layout.addWidget(extractor_label)
    extractor_label.setVisible(payload["extractor_section_visible"])
    command_bar = QHBoxLayout()
    for label, _command in payload["command_buttons"]:
        button = QPushButton(label)
        if label == payload["danger_command_label"]:
            button.setProperty("danger", True)
        command_bar.addWidget(button)
    layout.addLayout(command_bar)
    return screen


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a screen the shipped screen does not."""
    app()
    old_side = render_offscreen(old_tab_for_picture(name), PIXEL_SIZE)
    new_side = render_offscreen(
        screen_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_tab_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            screen_painted_by_the_model(model_payload("empty")), PIXEL_SIZE
        ),
        note="one scrumming bot against none",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_tab_for_picture("empty"), PIXEL_SIZE),
        new_side=render_offscreen(
            screen_painted_by_the_model(model_payload("one_extractor")), PIXEL_SIZE
        ),
        note="no bots against one extractor",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_tab_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            screen_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("happy")
    payload["privacy_label"] = "moved"
    with pytest.raises(AssertionError):
        screen_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        screen_painted_by_the_model({"privacy_label": ""})
    assert screen_painted_by_the_model(model_payload("happy")) is not None


def test_the_screen_declares_no_skin_of_its_own():
    """A colour the surface ships is one the screen never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    assert old_tab().styleSheet() == ""
    assert "QWidget" not in surface.PRIVACY_STYLE_ON
    assert "QWidget" not in surface.SCRUM_SECTION_STYLE
    assert "background-color" not in surface.SCRUM_SECTION_STYLE
    skinned = screen_painted_by_the_model(model_payload("happy"))
    skinned.setStyleSheet("QWidget { background-color: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(old_tab_for_picture("happy"), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a rule the screen does not set",
    )
    assert_pictures_match(
        old_side=render_widget(old_tab_for_picture("happy"), PIXEL_SIZE),
        new_side=render_widget(
            screen_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


def test_the_wait_is_compared_as_asked_for():
    """The wait the screen was given differs between the two sides."""
    app()
    tab = old_tab()
    assert tab._pull_rate_timer.interval() == surface.PULL_RATE_INTERVAL_MS == 1000
    assert surface.TIMER_DELAYS_MS == (1000,)


def test_the_platform_keeps_the_wait_the_timer_was_given():
    """The timer refused the wait it was given, so the ask is not the wait."""
    from PySide6.QtCore import QTimer

    app()
    timer = QTimer()
    timer.setInterval(surface.PULL_RATE_INTERVAL_MS)
    assert timer.interval() == surface.PULL_RATE_INTERVAL_MS
    timer.setInterval(-5)
    floor = timer.interval()
    assert floor >= 0, floor
    assert surface.PULL_RATE_INTERVAL_MS > floor


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


# What a picture cannot see


def test_the_privacy_tooltip_is_compared_as_a_string():
    """The words the Privacy button explains itself with reached no pixel."""
    app()
    assert old_tab()._privacy_mode_btn.toolTip() == surface.PRIVACY_TOOLTIP
    assert len(surface.PRIVACY_TOOLTIP) > 100
    assert "\n\n" in surface.PRIVACY_TOOLTIP


def test_the_freshness_tooltip_is_compared_as_a_string():
    """The words the freshness line explains itself with reached no pixel."""
    app()
    assert old_tab()._pull_rate_lbl.toolTip() == surface.PULL_RATE_TOOLTIP
    assert len(surface.PULL_RATE_TOOLTIP) > 100


def test_the_button_focus_policy_is_compared_as_a_value():
    """The Privacy button took keyboard focus on one side and not the other."""
    app()
    assert (
        old_tab()._privacy_mode_btn.focusPolicy().name == surface.PRIVACY_FOCUS_POLICY
    )
    assert surface.PRIVACY_FOCUS_POLICY == "NoFocus"


def test_the_focus_answer_says_what_the_policy_word_means():
    """The renderer reads a word it cannot resolve without the answer."""
    from PySide6.QtCore import Qt

    app()
    button = old_tab()._privacy_mode_btn
    assert surface.PRIVACY_FOCUSABLE is (button.focusPolicy() != Qt.NoFocus)
    assert surface.PRIVACY_FOCUSABLE is False


def test_the_danger_mark_is_compared_as_a_value():
    """The Delete button lost the mark that colours it as dangerous."""
    app()
    tab = old_tab()
    bar = tab.layout().itemAt(tab.layout().count() - 1).layout()
    marks = [
        [
            bar.itemAt(index).widget().text(),
            bar.itemAt(index).widget().property("danger"),
        ]
        for index in range(bar.count())
    ]
    assert marks == [
        ["Start", None],
        ["Pause", None],
        ["Stop", None],
        ["Restart", None],
        ["Delete", True],
    ], marks
    assert surface.DANGER_COMMAND_LABEL == "Delete"
    assert [label for label, _command in surface.COMMAND_BUTTONS] == [
        found[0] for found in marks
    ]


def test_the_accent_mark_is_compared_as_a_value():
    """The "+ New Bot" button lost the mark that colours it."""
    app()
    assert old_tab()._add_bot_btn.property("accent") is surface.ADD_BOT_ACCENT is True


def test_the_privacy_colours_are_compared_as_exact_text():
    """A swapped colour channel reads the same, so a wrong colour passes.

    Both colours are compared as text in one spelling. The ON ground has
    three different channels, so a channel swap changes the text. The OFF
    border has three equal channels and cannot show a swap at all, which
    is why it is compared as exact text and said so here.
    """
    on_ground = "#2d9d5f"
    on_border = "#3ed080"
    off_border = "#555555"
    assert on_ground in surface.PRIVACY_STYLE_ON
    assert on_border in surface.PRIVACY_STYLE_ON
    assert off_border in surface.PRIVACY_STYLE_OFF
    assert len({on_ground[1:3], on_ground[3:5], on_ground[5:7]}) == 3, on_ground
    assert len({on_border[1:3], on_border[3:5], on_border[5:7]}) == 3, on_border
    assert len({off_border[1:3], off_border[3:5], off_border[5:7]}) == 1, off_border
    assert on_ground == on_ground.lower()
    assert surface.PRIVACY_STYLE_ON != surface.PRIVACY_STYLE_OFF


def test_the_privacy_button_style_is_compared_as_a_string():
    """The Privacy button carries a different look on the two sides."""
    run = drive(["happy"])
    assert run["old"]["privacy_style"] == run["new"]["privacy_style"]
    assert run["old"]["privacy_style"] == surface.PRIVACY_STYLE_OFF
    hidden = drive(["happy"], privacy=1)
    assert hidden["old"]["privacy_style"] == hidden["new"]["privacy_style"]
    assert hidden["old"]["privacy_style"] == surface.PRIVACY_STYLE_ON


def test_the_hidden_section_is_compared_as_the_ask():
    """The platform decides what is shown, so the ask is what is compared."""
    app()
    tab = old_tab(names=["happy"])
    assert tab._scrum_label.isVisible() is False, "the parent window was never opened"
    assert tab._extractor_label.isVisible() is False
    assert shown(tab._scrum_label) is True
    assert shown(tab._extractor_label) is False
    empty = old_tab(names=["empty"])
    assert shown(empty._scrum_label) is False


def test_the_freshness_line_is_compared_as_a_string():
    """The freshness line reached the wrong words on one side."""
    run = drive(["happy"], pool="warm")
    assert run["old"]["pull_rate_text"] == run["new"]["pull_rate_text"]
    assert "freshest" in run["old"]["pull_rate_text"]
    assert "cache-hit 75%" in run["old"]["pull_rate_text"]
    idle = drive(["happy"], pool="idle")
    assert idle["old"]["pull_rate_text"] == surface.PULL_RATE_IDLE_TEXT


def test_the_recorded_steps_are_compared_as_values():
    """The recorded steps are a list nothing reads, so a lost step is unseen."""
    model = new_model(names=["both_kinds"])
    names = [call[0] for call in model.calls]
    assert names.count(surface.ROUTED) == 1
    assert names.count(surface.SECTIONS_SHOWN) == 1
    assert surface.TAB_BUILT in names
    assert surface.PRIVACY_RESTYLED in names
    refused = new_model()
    guarded(lambda: refused.update_bots(CASES["state_is_a_number"]))
    assert surface.ROW_REFUSED in [
        call[0] for call in refused.scrum_table.calls
    ], refused.scrum_table.calls
    payload = surface.build_view_model(model)
    assert payload["calls"] == [list(call) for call in model.calls]


BLIND_TO_THE_PICTURE = {
    "privacy tooltip": "test_the_privacy_tooltip_is_compared_as_a_string",
    "freshness tooltip": "test_the_freshness_tooltip_is_compared_as_a_string",
    "focus policy": "test_the_button_focus_policy_is_compared_as_a_value",
    "danger mark": "test_the_danger_mark_is_compared_as_a_value",
    "accent mark": "test_the_accent_mark_is_compared_as_a_value",
    "privacy colours": "test_the_privacy_colours_are_compared_as_exact_text",
    "privacy look": "test_the_privacy_button_style_is_compared_as_a_string",
    "hidden section": "test_the_hidden_section_is_compared_as_the_ask",
    "freshness line": "test_the_freshness_line_is_compared_as_a_string",
    "recorded steps": "test_the_recorded_steps_are_compared_as_values",
    "recorded checks": "test_the_recorded_checks_are_the_shipped_checks",
    "highlight": "test_the_highlight_follows_the_bot_not_the_row",
    "sibling clearing": "test_highlighting_one_table_clears_the_other_on_both_sides",
    "command target": "test_a_command_reaches_the_table_the_operator_last_used",
    "status line": "test_a_command_with_nothing_highlighted_writes_the_same_line",
    "wait length": "test_the_wait_is_compared_as_asked_for",
    "rows left behind": (
        "test_a_shrink_then_a_refusal_leaves_the_same_rows_on_both_sides"
    ),
    "refusal type": "test_a_refused_input_refuses_the_same_way_on_both_sides",
    "refusal wording": "test_the_refusal_reader_reports_two_different_wordings",
    "news strip": "test_a_news_strip_that_refuses_leaves_plain_space_on_both_sides",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 20
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


def test_a_news_strip_that_refuses_leaves_plain_space_on_both_sides():
    """A news strip that cannot be built moved the two buttons beside it."""
    app()
    tab = old_tab(ticker=False)
    assert not hasattr(tab, "_news_ticker")
    assert tab.layout().itemAt(0).layout().count() == HEADER_ITEM_COUNT
    model = new_model(ticker=False)
    assert model.news_ticker is None
    assert model.header_stretch is True
    assert surface.HEADER_STRETCH_ADDED in [call[0] for call in model.calls]
    built = new_model()
    assert built.news_ticker is not None
    assert built.header_stretch is False


def test_a_news_strip_that_raises_is_recorded_and_not_sent_on():
    """A refusing strip took the whole screen down with it."""

    def refuse():
        raise RuntimeError("no feed")

    model = surface.ExchangeTabModel(
        EXCHANGE_ID, EXCHANGE_NAME, news_ticker_factory=refuse
    )
    assert model.news_ticker is None
    assert model.header_stretch is True
    assert [surface.NEWS_TICKER_FAILED, "RuntimeError"] in model.calls


# The freshness line writes under the logger it names


def warnings_from(logger_name, run, level=logging.WARNING):
    """Every line one named logger emits while `run` is running.

    The handler is attached to the named logger, never through a capture
    fixture: this project's loggers do not pass their records up, so a
    fixture reading the root logger would see nothing. It is detached
    even when `run` refuses part way, and each record is flushed as it
    arrives.
    """
    found: list = []

    class Recorder(logging.Handler):
        def emit(self, record):
            found.append(record.getMessage())
            self.flush()

    handler = Recorder()
    target = logging.getLogger(logger_name)
    target.addHandler(handler)
    was = target.level
    target.setLevel(level)
    try:
        guarded(run)
    finally:
        target.removeHandler(handler)
        target.setLevel(was)
    return found


def test_the_refusing_news_strip_writes_the_same_line_on_both_sides():
    """A strip that cannot be built is announced differently on one side."""
    app()

    def refuse():
        raise RuntimeError("no feed")

    old_said = warnings_from(
        surface.LOGGER_NAME, lambda: old_tab(ticker=False), level=logging.DEBUG
    )
    new_said = warnings_from(
        surface.LOGGER_NAME,
        lambda: surface.ExchangeTabModel(
            EXCHANGE_ID, EXCHANGE_NAME, news_ticker_factory=refuse
        ),
        level=logging.DEBUG,
    )
    assert old_said == new_said, (old_said, new_said)
    assert len(old_said) == 1, old_said
    assert "news ticker failed" in old_said[0]


def test_the_line_recorder_can_report():
    """The recorder sees nothing whatever the code says, so silence is empty."""
    said = warnings_from(
        surface.LOGGER_NAME,
        lambda: logging.getLogger(surface.LOGGER_NAME).warning("a seeded line"),
    )
    assert said == ["a seeded line"]
    quiet = warnings_from(surface.LOGGER_NAME, lambda: new_model(names=["happy"]))
    assert quiet == []
    survived = warnings_from(
        surface.LOGGER_NAME,
        lambda: [
            logging.getLogger(surface.LOGGER_NAME).warning("before the refusal"),
            new_model(names=["state_is_a_number"]),
        ],
    )
    assert survived == ["before the refusal"]
    assert logging.getLogger(surface.LOGGER_NAME).handlers == []


def test_the_surface_writes_under_the_logger_it_names():
    """The surface writes under a name no operator log is collected from."""
    assert surface.LOGGER_NAME == "acervator.gui"
    assert surface.logger.name == surface.LOGGER_NAME
    assert shipped.logger.name == surface.LOGGER_NAME


# Every value reaches the compared snapshot


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
        if isinstance(value, (surface.ExchangeTabModel, logging.Logger)):
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
        model = new_model()
        guarded(lambda model=model, name=name: model.update_bots(CASES[name]))
        payloads.append(surface.build_view_model(model))
    for steps in SEQUENCES.values():
        model = new_model()
        for step in steps:
            guarded(lambda model=model, step=step: model.update_bots(CASES[step]))
        payloads.append(surface.build_view_model(model))
    for name in POOL_CASES:
        model = new_model(names=["happy"])
        summary = POOL_CASES[name]
        model.pool_reader = lambda summary=summary: dict(summary)
        guarded(model.update_pull_rate_label)
        payloads.append(surface.build_view_model(model))
    pressed = new_model(
        names=["both_kinds"],
        on_bot_cmd=lambda *found: None,
        on_new_bot=lambda exchange_id: None,
    )
    pressed.select_scrum_row(0)
    pressed.select_extractor_row(0)
    pressed.scrum_clicked("scrum-1")
    pressed.extractor_clicked("ext-1")
    for command in COMMANDS:
        pressed.cmd(command)
    pressed.on_new_bot_clicked()
    payloads.append(surface.build_view_model(pressed))
    refused = new_model(status_log=RecordingLog())
    refused.cmd("stop")
    payloads.append(surface.build_view_model(refused))
    flipped = new_model(names=["happy"], window_refresh=lambda: None)
    flipped.on_global_privacy_clicked()
    flipped.on_global_privacy_clicked()
    payloads.append(surface.build_view_model(flipped))
    windowless = new_model(names=["happy"])
    windowless.on_global_privacy_clicked()
    payloads.append(surface.build_view_model(windowless))
    payloads.append(surface.build_view_model(surface.build_model(statuses=[bot()])))
    payloads.append(surface.build_view_model(surface.build_model()))
    payloads.append(surface.build_view_model(refusing_register_model()))
    payloads.append(surface.build_view_model(refusing_ticker_model()))
    payloads.append(surface.build_view_model(unreadable_pool_model()))
    anchored = new_model(names=["three_rows"])
    anchored.select_scrum_row(2)
    anchored.update_bots(CASES["one_row"])
    payloads.append(surface.build_view_model(anchored))
    other = new_model(OTHER_EXCHANGE_ID, "Kraken", names=["one_extractor"])
    payloads.append(surface.build_view_model(other))
    return payloads


def refusing_register_model():
    """One screen built while the privacy register cannot be read."""

    def refuse():
        raise RuntimeError("register gone")

    real = surface.get_privacy_mask_registry
    surface.get_privacy_mask_registry = refuse
    try:
        model = surface.ExchangeTabModel(EXCHANGE_ID, EXCHANGE_NAME)
        model.on_global_privacy_clicked()
        return model
    finally:
        surface.get_privacy_mask_registry = real


def refusing_ticker_model():
    """One screen built while the news strip cannot be built."""

    def refuse():
        raise RuntimeError("no feed")

    return surface.ExchangeTabModel(
        EXCHANGE_ID, EXCHANGE_NAME, news_ticker_factory=refuse
    )


def unreadable_pool_model():
    """One screen whose data pool cannot be read."""

    def refuse():
        raise RuntimeError("pool gone")

    model = new_model(names=["happy"])
    model.pool_reader = refuse
    model.update_pull_rate_label()
    return model


COVERED_ELSEWHERE = {
    "PANE_MODEL": "test_importing_the_surface_reads_no_settings_file",
    "LOGGER_NAME": "test_the_surface_writes_under_the_logger_it_names",
    "TableCall": "test_the_recorded_steps_are_compared_as_values",
    "REFUSAL_TYPES": "test_a_refused_input_refuses_the_same_way_on_both_sides",
    "PIN_UNRECORDED": "test_a_register_that_cannot_be_read_leaves_the_button_alone",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped screen."""
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
    assert "COMMAND_BUTTONS" in missing_from_payload(surface_constants(), thinned)
    assert "PRIVACY_TOOLTIP" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "exchange_id": ("model.exchange_id",),
    "exchange_name": ("model.exchange_name",),
    "privacy_label": ("model.privacy_label_text",),
    "privacy_label_on": ("PRIVACY_LABEL_ON",),
    "privacy_label_off": ("PRIVACY_LABEL_OFF",),
    "privacy_tooltip": ("PRIVACY_TOOLTIP",),
    "privacy_style": ("model.privacy_style_sheet",),
    "privacy_style_on": ("PRIVACY_STYLE_ON",),
    "privacy_style_off": ("PRIVACY_STYLE_OFF",),
    "privacy_focus_policy": ("PRIVACY_FOCUS_POLICY",),
    "privacy_focusable": ("PRIVACY_FOCUSABLE",),
    "news_ticker_stretch": ("NEWS_TICKER_STRETCH",),
    "news_ticker_failed_log": ("NEWS_TICKER_FAILED_LOG",),
    "news_ticker_built": ("model.news_ticker",),
    "news_ticker_started": ("model.news_ticker_started",),
    "header_stretch": ("model.header_stretch",),
    "add_bot_label": ("ADD_BOT_LABEL",),
    "add_bot_accent": ("ADD_BOT_ACCENT",),
    "new_bot_asks": ("model.new_bot_asks",),
    "pull_rate_text": ("model.pull_rate_label_text",),
    "pull_rate_initial_text": ("PULL_RATE_INITIAL_TEXT",),
    "pull_rate_style": ("PULL_RATE_STYLE",),
    "pull_rate_tooltip": ("PULL_RATE_TOOLTIP",),
    "pull_rate_interval_ms": ("PULL_RATE_INTERVAL_MS",),
    "pull_rate_idle_text": ("PULL_RATE_IDLE_TEXT",),
    "pull_rate_awaiting_format": ("PULL_RATE_AWAITING_FORMAT",),
    "pull_rate_full_format": ("PULL_RATE_FULL_FORMAT",),
    "percent_scale": ("PERCENT_SCALE",),
    "no_slots": ("NO_SLOTS",),
    "no_hits": ("NO_HITS",),
    "scrum_section_label": ("SCRUM_SECTION_LABEL",),
    "scrum_section_style": ("SCRUM_SECTION_STYLE",),
    "scrum_section_visible": ("model.scrum_section_visible",),
    "extractor_section_label": ("EXTRACTOR_SECTION_LABEL",),
    "extractor_section_style": ("EXTRACTOR_SECTION_STYLE",),
    "extractor_section_visible": ("model.extractor_section_visible",),
    "command_buttons": ("COMMAND_BUTTONS",),
    "danger_command_label": ("DANGER_COMMAND_LABEL",),
    "commands_sent": ("model.commands_sent",),
    "scrum_table": ("model.scrum_table",),
    "extractor_table": ("model.extractor_table",),
    "last_clicked_table": ("model.last_clicked_table",),
    "default_table": ("DEFAULT_TABLE",),
    "table_scrumming": ("TABLE_SCRUMMING",),
    "table_extractor": ("TABLE_EXTRACTOR",),
    "table_neither": ("TABLE_NEITHER",),
    "mode_scrumming": ("MODE_SCRUMMING",),
    "mode_extractor": ("MODE_EXTRACTOR",),
    "no_mode": ("NO_MODE",),
    "default_exchange_id": ("DEFAULT_EXCHANGE_ID",),
    "default_exchange_name": ("DEFAULT_EXCHANGE_NAME",),
    "no_selection_row": ("NO_SELECTION_ROW",),
    "no_selection_bot_id": ("NO_SELECTION_BOT_ID",),
    "no_bot_id": ("NO_BOT_ID",),
    "no_number": ("NO_NUMBER",),
    "select_first_message": ("SELECT_FIRST_MESSAGE",),
    "select_first_level": ("SELECT_FIRST_LEVEL",),
    "logged": ("model.logged",),
    "bot_opens": ("model.bot_opens",),
    "pins": ("model.pins",),
    "pin_command_routed": ("PIN_COMMAND_ROUTED",),
    "pin_every_bot_drawn": ("PIN_EVERY_BOT_DRAWN",),
    "pin_selection_survives": ("PIN_SELECTION_SURVIVES",),
    "pin_privacy_applied": ("PIN_PRIVACY_APPLIED",),
    "pin_privacy_button": ("PIN_PRIVACY_BUTTON",),
    "refresh_every_s": ("REFRESH_EVERY_S",),
    "no_every": ("NO_EVERY",),
    "no_selection_moved": ("NO_SELECTION_MOVED",),
    "row_checks": ("ROW_CHECKS",),
    "checks_before_first_cell": ("CHECKS_BEFORE_FIRST_CELL",),
    "number_fields": ("NUMBER_FIELDS",),
    "check_stats": ("CHECK_STATS",),
    "check_numbers": ("CHECK_NUMBERS",),
    "check_symbol": ("CHECK_SYMBOL",),
    "check_state": ("CHECK_STATE",),
    "refusal_types": ("REFUSAL_TYPES",),
    "skin": ("SKIN",),
    "style_sheet": ("STYLE_SHEET",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "actions": ("ACTIONS",),
    "reset_param": ("RESET_PARAM",),
    "scrum_table_exchange_param": ("SCRUM_TABLE_EXCHANGE_PARAM",),
    "exchange_id_param": ("EXCHANGE_ID_PARAM",),
    "exchange_name_param": ("EXCHANGE_NAME_PARAM",),
    "statuses_param": ("STATUSES_PARAM",),
    "pool_summary_param": ("POOL_SUMMARY_PARAM",),
    "select_scrum_param": ("SELECT_SCRUM_PARAM",),
    "select_extractor_param": ("SELECT_EXTRACTOR_PARAM",),
    "pull_rate_param": ("PULL_RATE_PARAM",),
    "command_param": ("COMMAND_PARAM",),
    "new_bot_param": ("NEW_BOT_PARAM",),
    "privacy_param": ("PRIVACY_PARAM",),
    "logger_name": ("LOGGER_NAME",),
    "calls": ("model.calls",),
}

FREE_SHAPE_KEYS = ("calls", "pins", "row_checks")


def resolve_source(name, model, held=None):
    """The value one named source holds, on the surface or on the model."""
    if held and name in held:
        return held[name]
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
        return found() if callable(found) else found
    return getattr(surface, name)


def backed(key, value, sources, model, held=None):
    """Whether one payload key carries exactly what its named sources hold."""
    resolved = resolve_source(sources[0], model, held)
    if isinstance(resolved, surface.HostedTableModel):
        return freeze(value) == freeze(surface.table_view(resolved))
    if key in FREE_SHAPE_KEYS:
        return len(value) == len(resolved)
    if key == "news_ticker_built":
        return value is (resolved is not None)
    if key == "refusal_types":
        return list(value) == sorted(resolved)
    return freeze(value) == freeze(resolved)


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = new_model(names=["both_kinds"])
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    fresh = new_model(names=["both_kinds"])
    surface.build_view_model(fresh)
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(fresh, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, fresh), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = new_model(names=["happy"])
    payload = surface.build_view_model(model)
    assert backed("add_bot_label", payload["add_bot_label"], ("ADD_BOT_LABEL",), model)
    assert not backed("add_bot_label", "+ Bot", ("ADD_BOT_LABEL",), model)
    assert not backed(
        "command_buttons", [["Start", "start"]], ("COMMAND_BUTTONS",), model
    )
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("scrum_table", {}, ("model.scrum_table",), model)
    assert not backed(
        "last_clicked_table", "extractor", ("model.last_clicked_table",), model
    )


# What the shipped module keeps between screens


def test_the_shipped_module_changes_no_value_the_next_screen_reads():
    """One screen left a changed value behind for the next one."""
    app()
    before = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    for name in CASES:
        guarded(lambda name=name: old_tab(names=[name]))
    after = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    assert after == before


def test_the_shipped_screen_writes_to_the_process_wide_privacy_register():
    """The screen changes no shared state, so no test can disturb another."""
    app()
    live = registry()
    assert live.is_masked("bot_table.bot_id") is False
    old_tab()._on_global_privacy_clicked()
    assert live.is_masked("bot_table.bot_id") is True
    assert registry() is live


def test_each_test_is_given_its_own_register(own_privacy_registry):
    """Two tests share one register, so the order they run in decides both."""
    assert registry() is own_privacy_registry
    assert registry().is_masked("bot_table.ammo") is False
    registry().set_masked("bot_table.ammo", True)


def test_each_test_is_given_its_own_register_again():
    """The mask the test above set survived into this one."""
    assert registry().is_masked("bot_table.ammo") is False


def test_no_test_writes_a_settings_file(own_privacy_registry, tmp_path):
    """A privacy press wrote the operator's live settings file."""
    app()
    old_tab()._on_global_privacy_clicked()
    assert not (tmp_path / "settings.json").exists()
    assert list(tmp_path.iterdir()) == []
    assert own_privacy_registry.is_masked("bot_table.symbol") is True


def test_the_surface_keeps_no_value_between_two_screens():
    """One screen left a changed value behind for the next one."""
    first = new_model(names=["three_rows"])
    second = surface.ExchangeTabModel(EXCHANGE_ID, EXCHANGE_NAME)
    assert second.scrum_table.bot_ids == []
    assert second.pins == []
    assert second.calls != first.calls
    assert first.scrum_table is not second.scrum_table


# The bridge


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    payload = surface.build_view_model(new_model(names=["both_kinds"]))
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_exchange_tab_method():
    """The renderer cannot reach the exchange screen over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "exchange_tab.state"
    assert registered[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )
    assert answer["ok"] is True
    assert answer["result"]["add_bot_label"] == surface.ADD_BOT_LABEL


def test_the_bridge_registers_this_surface_once_and_by_identity():
    """The registry maps ``surface.METHOD`` to ``surface.view_model`` itself, and
    to nothing else."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert registry[surface.METHOD] is surface.view_model
    mine = [m for m, fn in registry.items() if fn is surface.view_model]
    assert mine == [surface.METHOD], mine


def test_the_bridge_answers_every_surface_it_registered():
    """POSITIVE CONTROL: the registry holds more than this one surface, so the
    single match above is a fact and not an empty registry."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert len(registry) > 1, sorted(registry)
    assert all(callable(fn) for fn in registry.values())


def test_the_bridge_keeps_the_screen_until_a_reset():
    """The screen forgot its rows between two calls, or kept them past a reset."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 5, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    filled = ask({"statuses": CASES["three_rows"]})
    assert filled["scrum_table"]["row_count"] == 3
    assert ask({})["scrum_table"]["row_count"] == 3
    assert ask({"reset": True})["scrum_table"]["row_count"] == 0
    assert surface.PANE_MODEL.scrum_table.bot_ids == []


def test_the_bridge_reports_a_state_it_cannot_read():
    """A broken request answered as if it had worked."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 6,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "statuses": [{"state": 7, "mode": "scrumming"}],
                },
            }
        ),
        registered,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"
    desktop_bridge.handle_line(
        json.dumps({"id": 7, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )


def test_the_bridge_drives_every_step_the_screen_takes():
    """A step the renderer sends never reaches the screen."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 8, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True, "exchange_id": OTHER_EXCHANGE_ID, "exchange_name": "Kraken"})
    found = ask({"statuses": CASES["both_kinds"], "select_extractor": 0})
    assert found["exchange_id"] == OTHER_EXCHANGE_ID
    assert found["last_clicked_table"] == "extractor"
    priced = ask({"pool_summary": POOL_CASES["idle"]})
    assert priced["pull_rate_text"] == surface.PULL_RATE_IDLE_TEXT
    hidden = ask({"privacy": True})
    assert hidden["privacy_label"] == surface.PRIVACY_LABEL_ON
    ask({"reset": True})


def test_every_control_is_driven_by_the_field_name_the_payload_publishes():
    """A request field the renderer can name but view_model never reads."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 9, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    published = ask({surface.RESET_PARAM: True})
    named = {
        published["select_scrum_param"]: 0,
        published["select_extractor_param"]: 0,
        published["command_param"]: "start",
        published["new_bot_param"]: True,
        published["pull_rate_param"]: True,
        published["privacy_param"]: True,
    }
    ask({surface.STATUSES_PARAM: CASES["both_kinds"]})
    for name, value in named.items():
        found = ask({name: value})
        assert isinstance(found, dict), name
    assert ask({})["last_clicked_table"] == "extractor"
    assert ask({})["privacy_label"] == surface.PRIVACY_LABEL_ON
    assert ask({})["commands_sent"] == []
    ask({surface.RESET_PARAM: True})


def test_the_control_check_names_a_field_the_handler_never_reads():
    """The check above passes any name, so one the handler ignores is named."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 10, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({surface.RESET_PARAM: True})
    ask({surface.STATUSES_PARAM: CASES["both_kinds"]})
    ask({"select_the_extractor": 0})
    assert ask({})["last_clicked_table"] == surface.DEFAULT_TABLE
    ask({surface.SELECT_EXTRACTOR_PARAM: 0})
    assert ask({})["last_clicked_table"] == surface.TABLE_EXTRACTOR
    ask({surface.RESET_PARAM: True})


# Without Qt at all

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
    "json.dumps({'id': 1, 'method': 'exchange_tab.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import exchange_tab_surface as s\n"
    "model = s.build_model('coinbase', 'Coinbase', [\n"
    "    {'bot_id': 'bot-alpha-0001', 'symbol': 'XRP/USD',\n"
    "     'mode': 'scrumming', 'state': 'running', 'exchange': 'coinbase',\n"
    "     'current_holdings': 104.8, 'quote_to_usd': 1.0,\n"
    "     'live_target_balance': 50.0, 'target_balance': 40.0,\n"
    "     'stats': {'total_trades': 7, 'position_value': 149.85,\n"
    "               'current_price': 1.43}},\n"
    "    {'bot_id': 'ext-alpha-0001', 'symbol': 'XRP/USD',\n"
    "     'mode': 'extractor', 'state': 'running', 'exchange': 'coinbase',\n"
    "     'current_holdings': 1.0, 'quote_to_usd': 1.0,\n"
    "     'live_target_balance': 10.0, 'target_balance': 10.0,\n"
    "     'stats': {'total_trades': 1, 'position_value': 1.0,\n"
    "               'current_price': 1.0}}])\n"
    "model.pool_reader = lambda: {'ticker_slots': 2, 'ohlcv_slots': 1,\n"
    "    'balance_slots': 1, 'ticker_fetches': 1, 'ohlcv_fetches': 0,\n"
    "    'balance_fetches': 0, 'ticker_hits': 3, 'ohlcv_hits': 0,\n"
    "    'balance_hits': 0, 'freshest_age_s': 1.4, 'oldest_age_s': 22.6,\n"
    "    'stale_slots': 1}\n"
    "model.update_pull_rate_label()\n"
    "payload = s.build_view_model(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'privacy_label': payload['privacy_label'],\n"
    "    'privacy_style': payload['privacy_style'],\n"
    "    'pull_rate_text': payload['pull_rate_text'],\n"
    "    'commands': payload['command_buttons'],\n"
    "    'scrum_rows': payload['scrum_table']['drawn_rows'],\n"
    "    'extractor_rows': payload['extractor_table']['drawn_rows'],\n"
    "    'scrum_shown': payload['scrum_section_visible'],\n"
    "    'extractor_shown': payload['extractor_section_visible'],\n"
    "    'pins': [pin['name'] for pin in payload['pins']],\n"
    "    'calls': len(payload['calls'])}))\n"
)


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
    """Reaching the exchange screen pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["add_bot_label"] == surface.ADD_BOT_LABEL
    assert result["scrum_table"]["row_count"] == 0
    assert result["privacy_label"] == surface.PRIVACY_LABEL_OFF


SETTINGS_PROBE = """
import json
import os
import shutil
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-settings-probe-'))
at_import = root / 'at-import'
on_request = root / 'on-request'
at_import.mkdir()
on_request.mkdir()
os.environ['ACERVATOR_SETTINGS_ROOT'] = str(at_import)

from src.core.privacy_mask_registry import (
    PRIVACY_FIELD_IDS,
    get_privacy_mask_registry,
)


def write_masks(folder, masked):
    body = {'privacy_mask': {field: masked for field in PRIVACY_FIELD_IDS}}
    (folder / 'settings.json').write_text(json.dumps(body), encoding='utf-8')


write_masks(at_import, False)
write_masks(on_request, True)

from src.gui.main_tabs import exchange_tab_surface as s

built_at_import = s.PANE_MODEL is not None
os.environ['ACERVATOR_SETTINGS_ROOT'] = str(on_request)
answer = {'built_at_import': built_at_import,
          'built_on_request': s.pane_model() is s.PANE_MODEL,
          'label': s.PANE_MODEL.privacy_label_text,
          'points_at': str(get_privacy_mask_registry().settings_path),
          'on_request_file': str(on_request / 'settings.json'),
          'fields': len(PRIVACY_FIELD_IDS)}
shutil.rmtree(root, ignore_errors=True)
print(json.dumps(answer))
"""


def test_importing_the_surface_reads_no_settings_file():
    """Loading the surface read the operator's own settings file.

    The register is aimed at one folder while the surface is imported
    and at a second folder before the first request. The screen reports
    the masks held in the second folder, so the file is read on the
    request and not at import.
    """
    answered = run_script(SETTINGS_PROBE)
    assert answered["fields"] > 0, answered
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["label"] == surface.PRIVACY_LABEL_ON, answered
    assert answered["points_at"] == answered["on_request_file"], answered


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_screen_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["privacy_label"] == surface.PRIVACY_LABEL_OFF
    assert answered["privacy_style"] == surface.PRIVACY_STYLE_OFF
    assert answered["commands"] == [list(pair) for pair in surface.COMMAND_BUTTONS]
    assert answered["scrum_rows"] == 1
    assert answered["extractor_rows"] == 1
    assert answered["scrum_shown"] is True
    assert answered["extractor_shown"] is True
    assert "freshest" in answered["pull_rate_text"]
    assert answered["pins"] == [
        surface.PIN_EVERY_BOT_DRAWN,
        surface.PIN_SELECTION_SURVIVES,
    ]
    assert answered["calls"] > 3


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_builds_the_screen():
    """The Qt block let the shipped screen through.

    The shipped file guards its own Qt import and sets ``_HAS_QT``
    False, but its package imports Qt unguarded, so the module cannot be
    reached at all without Qt and that fallback never runs.
    """
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui.widgets import exchange_tab as t\n"
        "    out = {'imported': True, 'has_qt': t._HAS_QT}\n"
        "except Exception as exc:\n"
        "    out = {'imported': False, 'error': type(exc).__name__,\n"
        "        'headline': str(exc)}\n"
        "print(json.dumps(out))\n"
    )
    answered = run_script(probe)
    assert answered["imported"] is False
    assert answered["error"] == "ImportError"
    assert answered["headline"] == "PySide6 blocked"


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend.

    ``blocked_import`` refuses ``PySide6`` and ``shiboken6`` at the meta path, so
    a transitive import through any other module is refused too.
    """
    answered = blocked_import(("PySide6", "shiboken6"), SURFACE_MODULE)
    assert answered["imported"] is True, answered
    assert answered["loaded"] == [], answered


def test_the_qt_probe_refuses_the_shipped_tab():
    """POSITIVE CONTROL. ``blocked_import`` reports ``exchange_tab`` as
    unimportable without Qt, so the green above is a fact about the surface."""
    answered = blocked_import(("PySide6", "shiboken6"), SHIPPED_TAB_MODULE)
    assert answered["imported"] is False, answered
    assert "blocked in this probe" in answered["error"], answered


#: Makes every file, socket and browser reach raise, then drives the surface.
NO_IO_PROBE = """
import builtins
import json
import pathlib
import socket
import webbrowser


class _Refused(Exception):
    pass


def _refuse(*a, **kw):
    raise _Refused('the surface reached outside the process')


builtins.open = _refuse
socket.socket = _refuse
webbrowser.open = _refuse
pathlib.Path.home = staticmethod(_refuse)
pathlib.Path.read_text = _refuse
pathlib.Path.write_text = _refuse
pathlib.Path.mkdir = _refuse

from src.gui.main_tabs import exchange_tab_surface as s

answer = {'reached_out': False, 'method': '', 'error': ''}
try:
    payload = s.view_model({})
    answer['method'] = payload['method']
except _Refused as exc:
    answer['reached_out'] = True
    answer['error'] = str(exc)
print(json.dumps(answer))
"""


def test_the_surface_opens_no_file_and_no_socket():
    """The surface reached for a file, a network address or a browser.

    ``NO_IO_PROBE`` makes each of those raise before the surface is imported, so
    a reach through any helper is caught as well as a direct one.
    """
    answered = run_script(NO_IO_PROBE)
    assert answered["reached_out"] is False, answered
    assert answered["method"] == surface.METHOD, answered


def test_the_no_io_probe_catches_a_reach():
    """POSITIVE CONTROL for ``NO_IO_PROBE``. The same refusals, with one
    deliberate ``open`` after them, are reported as a reach."""
    answered = run_script(
        NO_IO_PROBE.replace(
            "    payload = s.view_model({})",
            "    open('planted.txt')\n    payload = s.view_model({})",
        )
    )
    assert answered["reached_out"] is True, answered
