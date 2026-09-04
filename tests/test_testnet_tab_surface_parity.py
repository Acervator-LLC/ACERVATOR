"""The shipped Local Testnet tab and the Qt-free surface, side by side.

A failure means the view model carries a different label, a different
table row, a different colour, a different widget tree, a different log
line, a different recorded call or a different path than ``TestnetTab``.

No test here reads or writes the operator's runtime tree, opens a socket
or makes a key. Every chain, wallet and hash value below is invented.
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
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import testnet_tab as shipped
from src.gui.main_tabs import testnet_tab_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.qt_pixel import render_widget
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

TAB_PATH = REPO_ROOT / "src/gui/testnet_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/testnet_tab_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"

PIXEL_SIZE = (1000, 800)

# The counts the shipped tab carries, each measured off the file by the
# same counter that is pointed at a neighbour which really has one.
TAB_CONNECT_SITES = 9
TAB_TIMER_BUILDS = 1
TAB_BUS_SITES = 0
TAB_WIDGET_BUILDS = 15
TAB_WIDGET_CLASSES = 1
TAB_ELEMENT_BUILDS = 16
TAB_CLASS_STATEMENTS = 2
CONTROL_CONNECT_SITES = 1
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_ELEMENT_BUILDS = 3

# Invented values. None of these is a real wallet, a real key or a real
# node. The chain id is text the tab prints and nothing dials.
BLOCK_HASH = "0x" + "ab12" * 16
PARENT_HASH = "0x" + "cd34" * 16
OTHER_BLOCK_HASH = "0x" + "ef56" * 16
TX_HASH = "0x" + "1122" * 16
OTHER_TX_HASH = "0x" + "3344" * 16
ADDRESS_ONE = "0x" + "aa11" * 10
ADDRESS_TWO = "0x" + "bb22" * 10
ADDRESS_THREE = "0x" + "cc33" * 10
UNSEEDED_HASH = "0x" + "9f" * 32

STAMP_ONE = 1_700_000_000.0
STAMP_TWO = 1_700_000_060.0
FROZEN_NOW = 1_700_003_600.0

UNICODE_TEXT = "Δ_fold→⚡"
MARKUP_TEXT = "<b>tier</b>"
NEWLINE_TEXT = "two\nlines"
APOSTROPHE_TEXT = "Ekthelius' Fold"
LONG_TEXT = "x" * 200
WRONG_CAPITALS_TIER = "harvest"
WRONG_CAPITALS_EVENT = "adjudicated"

CLOCK_MARK = "<a stamp this test did not seed>"
UNSEEDED_HASH_MARK = "<a hash this test did not seed>"
CLOCK_SHAPE = re.compile(r"\d\d:\d\d:\d\d")
HASH_SHAPE = re.compile(r"0x[0-9a-f]{40,}")
SEEDED_VALUES = frozenset(
    {
        BLOCK_HASH,
        PARENT_HASH,
        OTHER_BLOCK_HASH,
        TX_HASH,
        OTHER_TX_HASH,
        ADDRESS_ONE,
        ADDRESS_TWO,
        ADDRESS_THREE,
        "12:00:00",
    }
)

SEEDED_STAMP = "12:00:00"

WIDGETS_HELD: list = []


@pytest.fixture(scope="module", autouse=True)
def refuse_every_key():
    """Fail the run if anything under test mints a real key pair.

    ``run_demo_competition`` on the real local testnet makes one Ed25519
    key pair per bot and writes it to a file. Nothing in this file drives
    it, and this guard is what proves it.
    """
    from src.competition import bot_identity

    original = bot_identity.BotIdentity.generate

    def refuse(self):
        raise AssertionError("a test asked for a real key pair: %s" % self._key_path)

    bot_identity.BotIdentity.generate = refuse
    try:
        yield
    finally:
        bot_identity.BotIdentity.generate = original


def test_the_key_guard_can_report():
    """The key guard is not installed, so no test could ever trip it."""
    from src.competition import bot_identity

    with pytest.raises(AssertionError) as raised:
        bot_identity.BotIdentity("an-invented-path.json").generate()
    assert "real key pair" in str(raised.value)
    assert not Path("an-invented-path.json").exists()


def test_no_test_here_reaches_the_real_local_testnet():
    """A test drove the real chain, which makes keys and mines blocks."""
    from src.competition.local_testnet import LocalTestnet

    assert "run_demo_competition" in vars(LocalTestnet)
    net = net_of()
    assert type(net) is surface.TestnetSnapshot
    assert not isinstance(net, LocalTestnet)
    assert net.run_demo_competition() == result()
    assert net.runs == [{"n_bots": 3, "season": 1, "symbol": "BTC/USDT"}]


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


class frozen_clock:
    """Hold ``time.time`` at one value for both sides of one drive.

    The shipped tab and the surface both read the clock through the same
    ``time`` module, so one freeze reaches both. ``time.strftime`` reads
    the real clock and is not frozen; the log stamp is masked instead.
    """

    def __init__(self, now=FROZEN_NOW):
        self.now = now
        self.original = None

    def __enter__(self):
        self.original = time.time
        time.time = lambda: self.now
        return self

    def __exit__(self, *_):
        time.time = self.original
        return False


class watched_log:
    """Capture every line the tab hands to its log, before Qt rewrites it."""

    def __init__(self):
        self.lines: list = []
        self.original = None

    def __enter__(self):
        from PySide6.QtWidgets import QTextEdit

        self.original = QTextEdit.append
        captured = self.lines
        first = self.original

        def watch(widget, text):
            captured.append(text)
            return first(widget, text)

        QTextEdit.append = watch
        return self

    def __exit__(self, *_):
        from PySide6.QtWidgets import QTextEdit

        QTextEdit.append = self.original
        return False


class answered_dialog:
    """Answer the reset tab's confirmation without opening a window."""

    def __init__(self, confirmed):
        self.confirmed = confirmed
        self.original = None
        self.asked: list = []

    def __enter__(self):
        from PySide6.QtWidgets import QMessageBox

        self.original = QMessageBox.question
        asked = self.asked
        wanted = QMessageBox.Yes if self.confirmed else QMessageBox.No

        def answer(*args, **kwargs):
            asked.append([args[1], args[2]] if len(args) > 2 else list(args))
            return wanted

        QMessageBox.question = staticmethod(answer)
        return self

    def __exit__(self, *_):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.question = self.original
        return False


# ---------------------------------------------------------------------
# Invented inputs, and the stand-ins both sides are driven with
# ---------------------------------------------------------------------


def block(**over):
    """One mined block's values, with the happy block as the base."""
    base = {
        "number": 1,
        "block_hash": BLOCK_HASH,
        "parent_hash": PARENT_HASH,
        "timestamp": STAMP_ONE,
        "transactions": [TX_HASH, OTHER_TX_HASH],
    }
    base.update(over)
    return base


def tx(**over):
    """One transaction's values, with the happy transaction as the base."""
    base = {
        "tx_hash": TX_HASH,
        "block_number": 1,
        "from_addr": ADDRESS_ONE,
        "to_addr": ADDRESS_TWO,
        "function_name": "adjudicate",
        "args": {"comp": "c-1"},
        "gas_used": 50_000,
        "timestamp": STAMP_ONE,
    }
    base.update(over)
    return base


def event(**over):
    """One contract event's values, with the happy event as the base."""
    base = {
        "block_number": 1,
        "tx_hash": TX_HASH,
        "contract": "Registry",
        "event_name": "Adjudicated",
        "args": {"a": 1, "b": 2, "c": 3, "d": 4},
        "timestamp": STAMP_ONE,
    }
    base.update(over)
    return base


def stats(**over):
    """One competition summary, as the local testnet hands it over."""
    base = {
        "block_number": 3,
        "total_transactions": 2,
        "total_events": 4,
        "total_competitions": 1,
        "acrv_total_supply": 500_000,
        "acrv_remaining": 9_500_000,
        "tier_counts": {"Harvest": 1},
    }
    base.update(over)
    return base


def result(**over):
    """One finished competition, as the runner hands it over."""
    base = {
        "competition_id": "comp-1",
        "winner_wallet": ADDRESS_ONE,
        "winner_tier": "Harvest",
        "tokens_awarded": 500_000,
        "adj_tx_hash": TX_HASH,
    }
    base.update(over)
    return base


def chain_of(blocks=(), transactions=(), events=()):
    """One chain stand-in both sides are driven with."""
    return surface.ChainSnapshot(
        blocks=[surface.BlockSnapshot(**row) for row in blocks],
        transactions=[surface.TxSnapshot(**row) for row in transactions],
        events=[surface.EventSnapshot(**row) for row in events],
        block_number=len(blocks),
    )


def net_of(chain=None, balances=None, mint_log=None, summary=None, outcome=None):
    """One local testnet stand-in both sides are driven with."""
    return surface.TestnetSnapshot(
        chain=surface.ChainSnapshot() if chain is None else chain,
        acrv=surface.AcrvSnapshot(balances=balances, mint_log=mint_log),
        stats=stats() if summary is None else summary,
        result=result() if outcome is None else outcome,
    )


BLOCK_CASES: dict = {
    "happy": [block(), block(number=2, block_hash=OTHER_BLOCK_HASH)],
    "empty": [],
    "zero": [block(number=0, timestamp=0, transactions=[])],
    "negative": [block(number=-5, timestamp=-500)],
    "thousand_million": [block(number=1_000_000_000, timestamp=1_000_000_000)],
    "one_billionth": [block(timestamp=FROZEN_NOW - 1e-9)],
    "whole_number": [block(number=12, timestamp=FROZEN_NOW - 12)],
    "decimal_number": [block(number=12.0, timestamp=FROZEN_NOW - 12.0)],
    "unicode": [block(block_hash=UNICODE_TEXT)],
    "markup": [block(block_hash=MARKUP_TEXT)],
    "apostrophe": [block(block_hash=APOSTROPHE_TEXT)],
    "newline": [block(block_hash=NEWLINE_TEXT)],
    "long": [block(block_hash=LONG_TEXT)],
    "wrong_capitals": [block(block_hash=BLOCK_HASH.upper())],
    "list_of_transactions": [block(transactions=[TX_HASH, OTHER_TX_HASH])],
    "tuple_of_transactions": [block(transactions=(TX_HASH, OTHER_TX_HASH))],
    "over_the_limit": [block(number=index) for index in range(20)],
    "number_where_text_belongs": [block(block_hash=5)],
    "text_where_a_number_belongs": [block(timestamp="noon")],
    "no_timestamp_at_all": [block(timestamp=None)],
    "infinite_stamp": [block(timestamp=float("inf"))],
    "minus_infinite_stamp": [block(timestamp=float("-inf"))],
    "not_a_number_stamp": [block(timestamp=float("nan"))],
}

BLOCK_REFUSING = (
    "text_where_a_number_belongs",
    "no_timestamp_at_all",
    "infinite_stamp",
    "minus_infinite_stamp",
    "not_a_number_stamp",
    "number_where_text_belongs",
)

TX_CASES: dict = {
    "happy": [tx(), tx(tx_hash=OTHER_TX_HASH, function_name="mint")],
    "empty": [],
    "zero": [tx(gas_used=0)],
    "negative": [tx(gas_used=-1)],
    "thousand_million": [tx(gas_used=1_000_000_000)],
    "one_billionth": [tx(gas_used=1e-9)],
    "whole_number": [tx(gas_used=12)],
    "decimal_number": [tx(gas_used=12.0)],
    "unicode": [tx(function_name=UNICODE_TEXT, from_addr=UNICODE_TEXT)],
    "markup": [tx(function_name=MARKUP_TEXT)],
    "apostrophe": [tx(function_name=APOSTROPHE_TEXT)],
    "newline": [tx(function_name=NEWLINE_TEXT)],
    "long": [tx(function_name=LONG_TEXT, from_addr=LONG_TEXT)],
    "wrong_capitals": [tx(function_name="ADJUDICATE")],
    "over_the_limit": [tx(tx_hash="0x%040d" % index) for index in range(20)],
    "infinite_gas": [tx(gas_used=float("inf"))],
    "minus_infinite_gas": [tx(gas_used=float("-inf"))],
    "not_a_number_gas": [tx(gas_used=float("nan"))],
    "text_where_a_number_belongs": [tx(gas_used="many")],
    "no_gas_at_all": [tx(gas_used=None)],
    "number_where_text_belongs": [tx(from_addr=7)],
}

TX_REFUSING = (
    "text_where_a_number_belongs",
    "no_gas_at_all",
    "number_where_text_belongs",
)

EVENT_CASES: dict = {
    "happy": [event(), event(event_name="TokensMinted")],
    "empty": [],
    "every_name": [event(event_name=name) for name in surface.EVENT_COLORS],
    "unknown_name": [event(event_name="SomethingElse")],
    "wrong_capitals": [event(event_name=WRONG_CAPITALS_EVENT)],
    "no_args": [event(args={})],
    "one_arg": [event(args={"only": 1})],
    "over_the_arg_limit": [event(args={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})],
    "zero": [event(block_number=0, args={"n": 0})],
    "negative": [event(block_number=-5, args={"n": -5})],
    "thousand_million": [event(args={"n": 1_000_000_000})],
    "one_billionth": [event(args={"n": 1e-9})],
    "whole_number": [event(args={"n": 12})],
    "decimal_number": [event(args={"n": 12.0})],
    "infinite": [event(args={"n": float("inf")})],
    "minus_infinite": [event(args={"n": float("-inf")})],
    "not_a_number": [event(args={"n": float("nan")})],
    "unicode": [event(event_name=UNICODE_TEXT, args={UNICODE_TEXT: UNICODE_TEXT})],
    "markup": [event(event_name=MARKUP_TEXT, args={"m": MARKUP_TEXT})],
    "apostrophe": [event(event_name=APOSTROPHE_TEXT)],
    "newline": [event(event_name=NEWLINE_TEXT, args={"n": NEWLINE_TEXT})],
    "long": [event(event_name=LONG_TEXT, args={"l": LONG_TEXT})],
    "over_the_limit": [event(block_number=index) for index in range(25)],
    "number_where_text_belongs": [event(event_name=5)],
    "no_args_at_all": [event(args=None)],
}

EVENT_REFUSING = ()

HOLDER_CASES: dict = {
    "happy": (
        {ADDRESS_ONE: 5 * 10**18, ADDRESS_TWO: 2 * 10**18},
        [{"recipient": ADDRESS_ONE, "tier": "Harvest"}],
    ),
    "empty": ({}, []),
    "zero": ({ADDRESS_ONE: 0}, []),
    "negative": ({ADDRESS_ONE: -(10**18)}, []),
    "thousand_million": ({ADDRESS_ONE: 1_000_000_000 * 10**18}, []),
    "one_billionth": ({ADDRESS_ONE: 10**9}, []),
    "whole_number": ({ADDRESS_ONE: 12 * 10**18}, []),
    "decimal_number": ({ADDRESS_ONE: 12.0 * 10**18}, []),
    "infinite": ({ADDRESS_ONE: float("inf")}, []),
    "minus_infinite": ({ADDRESS_ONE: float("-inf")}, []),
    "not_a_number": ({ADDRESS_ONE: float("nan")}, []),
    "every_tier": (
        {
            "0x%040d" % index: (index + 1) * 10**18
            for index in range(len(surface.TIER_COLORS))
        },
        [
            {"recipient": "0x%040d" % index, "tier": name}
            for index, name in enumerate(surface.TIER_COLORS)
        ],
    ),
    "wrong_capitals_tier": (
        {ADDRESS_ONE: 10**18},
        [{"recipient": ADDRESS_ONE, "tier": WRONG_CAPITALS_TIER}],
    ),
    "unknown_tier": (
        {ADDRESS_ONE: 10**18},
        [{"recipient": ADDRESS_ONE, "tier": UNICODE_TEXT}],
    ),
    "unicode_wallet": ({UNICODE_TEXT: 10**18}, []),
    "markup_wallet": ({MARKUP_TEXT: 10**18}, []),
    "apostrophe_wallet": ({APOSTROPHE_TEXT: 10**18}, []),
    "newline_wallet": ({NEWLINE_TEXT: 10**18}, []),
    "long_wallet": ({LONG_TEXT: 10**18}, []),
    "over_the_limit": ({"0x%040d" % index: index * 10**18 for index in range(20)}, []),
    "text_where_a_number_belongs": ({ADDRESS_ONE: "many"}, []),
    "no_balance_at_all": ({ADDRESS_ONE: None}, []),
    "number_where_text_belongs": ({7: 10**18}, []),
}

HOLDER_REFUSING = (
    "text_where_a_number_belongs",
    "no_balance_at_all",
    "number_where_text_belongs",
)

STATS_CASES: dict = {
    "happy": stats(),
    "zero": stats(
        block_number=0,
        total_transactions=0,
        total_events=0,
        total_competitions=0,
        acrv_total_supply=0,
        acrv_remaining=0,
    ),
    "negative": stats(block_number=-5, acrv_total_supply=-5, acrv_remaining=-5),
    "thousand_million": stats(
        acrv_total_supply=1_000_000_000, acrv_remaining=1_000_000_000
    ),
    "one_billionth": stats(acrv_total_supply=1e-9, acrv_remaining=1e-9),
    "whole_number": stats(block_number=12, acrv_total_supply=12),
    "decimal_number": stats(block_number=12.0, acrv_total_supply=12.0),
    "infinite": stats(acrv_total_supply=float("inf")),
    "minus_infinite": stats(acrv_total_supply=float("-inf")),
    "not_a_number": stats(acrv_total_supply=float("nan")),
    "unicode": stats(block_number=UNICODE_TEXT),
    "markup": stats(block_number=MARKUP_TEXT),
    "apostrophe": stats(block_number=APOSTROPHE_TEXT),
    "newline": stats(block_number=NEWLINE_TEXT),
    "long": stats(block_number=LONG_TEXT),
    "number_where_text_belongs": stats(block_number=7),
    "text_where_a_number_belongs": stats(acrv_total_supply="many"),
    "no_supply_key": {
        "block_number": 1,
        "total_transactions": 1,
        "total_events": 1,
        "total_competitions": 1,
        "acrv_remaining": 1,
    },
    "no_keys_at_all": {},
}

STATS_REFUSING = (
    "text_where_a_number_belongs",
    "no_supply_key",
    "no_keys_at_all",
)

RESULT_CASES: dict = {
    "happy": result(),
    "zero": result(tokens_awarded=0),
    "negative": result(tokens_awarded=-5),
    "thousand_million": result(tokens_awarded=1_000_000_000),
    "one_billionth": result(tokens_awarded=1e-9),
    "whole_number": result(tokens_awarded=12),
    "decimal_number": result(tokens_awarded=12.0),
    "infinite": result(tokens_awarded=float("inf")),
    "minus_infinite": result(tokens_awarded=float("-inf")),
    "not_a_number": result(tokens_awarded=float("nan")),
    "unicode": result(competition_id=UNICODE_TEXT, winner_tier=UNICODE_TEXT),
    "markup": result(competition_id=MARKUP_TEXT),
    "apostrophe": result(competition_id=APOSTROPHE_TEXT),
    "newline": result(competition_id=NEWLINE_TEXT),
    "long": result(competition_id=LONG_TEXT, winner_wallet=LONG_TEXT),
    "wrong_capitals": result(winner_tier=WRONG_CAPITALS_TIER),
    "empty_wallet": result(winner_wallet=""),
    "number_where_text_belongs": result(winner_wallet=7),
    "text_where_a_number_belongs": result(tokens_awarded="many"),
    "no_tokens_at_all": result(tokens_awarded=None),
}

BRIDGE_RESULT_CASES: dict = dict(RESULT_CASES)
BRIDGE_RESULT_CASES.update(
    {
        "failed": {"error": "worker exploded"},
        "failed_unicode": {"error": UNICODE_TEXT},
        "failed_markup": {"error": MARKUP_TEXT},
        "failed_newline": {"error": NEWLINE_TEXT},
        "failed_number": {"error": 7},
        "no_competition_id": {"winner_wallet": ADDRESS_ONE, "winner_tier": "Harvest"},
        "nothing_at_all": {},
    }
)

TAB_CASES: dict = {
    "full": {
        "blocks": BLOCK_CASES["happy"],
        "transactions": TX_CASES["happy"],
        "events": EVENT_CASES["happy"],
        "holders": HOLDER_CASES["happy"],
        "summary": STATS_CASES["happy"],
    },
    "bare": {
        "blocks": [],
        "transactions": [],
        "events": [],
        "holders": HOLDER_CASES["empty"],
        "summary": STATS_CASES["zero"],
    },
    "tiers": {
        "blocks": BLOCK_CASES["happy"],
        "transactions": TX_CASES["happy"],
        "events": EVENT_CASES["every_name"],
        "holders": HOLDER_CASES["every_tier"],
        "summary": STATS_CASES["thousand_million"],
    },
}


# ---------------------------------------------------------------------
# Reading the two sides into one shape
# ---------------------------------------------------------------------


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


def hide_clock(found):
    """Replace one clock stamp unless this test seeded that exact stamp."""
    return found.group(0) if found.group(0) in SEEDED_VALUES else CLOCK_MARK


def hide_hash(found):
    """Replace one long hash unless this test seeded that exact hash."""
    return found.group(0) if found.group(0) in SEEDED_VALUES else UNSEEDED_HASH_MARK


def masked(value):
    """One value with anything the platform chose replaced by a marker.

    A clock stamp this test did not seed came off the machine's clock,
    and a hash this test did not seed was made by the machine. Both are
    hidden so the comparison reads the product. A seeded stamp and a
    seeded hash are kept.
    """
    if isinstance(value, str):
        found = CLOCK_SHAPE.sub(hide_clock, value)
        return HASH_SHAPE.sub(hide_hash, found)
    if isinstance(value, dict):
        return {key: masked(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [masked(item) for item in value]
    return value


def readable(value):
    """One value ready to compare: numbers as text, platform values hidden."""
    return masked(numbered(value))


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(readable(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        return {"answer": run(), "error": "", "headline": ""}
    except Exception as exc:
        return {
            "answer": None,
            "error": type(exc).__name__,
            "headline": str(exc).splitlines()[:1],
        }


def canon_colour(value):
    """One colour in a single spelling, so ``#888`` and ``#888888`` agree."""
    from PySide6.QtGui import QColor

    if not value:
        return ""
    return QColor(value).name().lower()


def canon_cells(rows):
    """One table's rows as text, canonical colour and alignment."""
    return [
        [
            {
                "text": found["text"],
                "color": canon_colour(found["color"]),
                "alignment": found["alignment"],
            }
            for found in row
        ]
        for row in rows
    ]


def read_table(table):
    """One real table's rows, read cell by cell off the widget."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                cells.append({"text": None, "color": "", "alignment": ""})
                continue
            brush = item.foreground()
            colour = (
                ""
                if brush.style() == Qt.NoBrush
                else QColor(brush.color()).name().lower()
            )
            cells.append(
                {
                    "text": item.text(),
                    "color": colour,
                    "alignment": (
                        surface.ALIGNMENT
                        if int(item.textAlignment()) == surface.ALIGNMENT_VALUE
                        else str(int(item.textAlignment()))
                    ),
                }
            )
        rows.append(cells)
    return rows


def layout_entries(layout):
    """Every direct entry of one layout, in the order it was added."""
    found = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is not None:
            found.append(item.widget())
        elif item.layout() is not None:
            found.append(item.layout())
        else:
            found.append("stretch")
    return found


# ---------------------------------------------------------------------
# Driving the two sides
# ---------------------------------------------------------------------


def qt_bridge(signals=surface.BRIDGE_SIGNALS):
    """A shared bridge stand-in with real signals, for the shipped side."""
    from PySide6.QtCore import QObject, Signal

    members = {
        "chain_updated": Signal(),
        "competition_completed": Signal(dict),
        "chain_reset": Signal(str),
    }
    built = type(
        "BuiltBridge",
        (QObject,),
        {name: value for name, value in members.items() if name in signals},
    )
    found = built()
    found.requests = []
    found.resets = []
    found.request_competition = found.requests.append
    found.reset = lambda reason="user-requested": found.resets.append(reason)
    return found


def old_tab(case, bridge=None):
    """Build the shipped tab over one case's stand-in."""
    app()
    testnet = net_of(
        chain=chain_of(
            case.get("blocks", ()),
            case.get("transactions", ()),
            case.get("events", ()),
        ),
        balances=dict(case.get("holders", ({}, []))[0]),
        mint_log=list(case.get("holders", ({}, []))[1]),
        summary=dict(case.get("summary", stats())),
        outcome=case.get("result"),
    )
    return hold(shipped.TestnetTab(None, testnet, bridge)), testnet


def new_model(case, bridge=None):
    """Build the surface's model over the same case's stand-in."""
    testnet = net_of(
        chain=chain_of(
            case.get("blocks", ()),
            case.get("transactions", ()),
            case.get("events", ()),
        ),
        balances=dict(case.get("holders", ({}, []))[0]),
        mint_log=list(case.get("holders", ({}, []))[1]),
        summary=dict(case.get("summary", stats())),
        outcome=case.get("result"),
    )
    model = surface.TestnetTabModel(testnet, bridge)
    model.setup_ui()
    return model, testnet


def old_refreshed(case):
    """Drive the shipped tab's whole refresh and read what it holds."""
    with frozen_clock():
        tab, testnet = old_tab(case)
        tab._refresh_all()
    return {
        "stat_values": {key: box.text() for key, box in tab._stat_vals.items()},
        "blocks": read_table(tab._block_tbl),
        "transactions": read_table(tab._tx_tbl),
        "events": read_table(tab._evt_tbl),
        "holders": read_table(tab._tok_tbl),
        "failures": sorted(
            name
            for name in surface.REFRESH_NAMES
            if getattr(tab, "_refresh_%s_fails" % name, 0)
        ),
    }


def new_refreshed(case):
    """Drive the surface's whole refresh and read what it holds."""
    model, _ = new_model(case)
    named = model.refresh_all(FROZEN_NOW)
    return {
        "stat_values": dict(model.stat_values),
        "blocks": canon_cells(model.block_rows),
        "transactions": canon_cells(model.tx_rows),
        "events": canon_cells(model.event_rows),
        "holders": canon_cells(model.holder_rows),
        "failures": sorted(set(named)),
    }


SINGLE_READS = {
    "blocks": ("_refresh_blocks", "_block_tbl", "refresh_blocks", "block_rows"),
    "transactions": ("_refresh_blocks", "_tx_tbl", "refresh_blocks", "tx_rows"),
    "events": ("_refresh_events", "_evt_tbl", "refresh_events", "event_rows"),
    "holders": ("_refresh_holders", "_tok_tbl", "refresh_holders", "holder_rows"),
    "summary": ("_refresh_stats", None, "refresh_stats", "stat_values"),
}


def old_single(case, key):
    """Drive one refresh method on the shipped tab and let it refuse."""
    method, table, _, _ = SINGLE_READS[key]
    with frozen_clock():
        tab, _ = old_tab(case)
        getattr(tab, method)()
    if table is None:
        return {name: box.text() for name, box in tab._stat_vals.items()}
    return read_table(getattr(tab, table))


def new_single(case, key):
    """Drive the same refresh method on the surface and let it refuse."""
    _, table, method, attribute = SINGLE_READS[key]
    model, _ = new_model(case)
    run = getattr(model, method)
    if method == "refresh_blocks":
        run(FROZEN_NOW)
    else:
        run()
    found = getattr(model, attribute)
    return dict(found) if table is None else canon_cells(found)


def case_of(name, table, key):
    """One case built from one of the four input tables."""
    if key == "holders":
        return {"holders": table[name], "summary": stats()}
    if key == "summary":
        return {"summary": table[name]}
    return {key: table[name], "summary": stats()}


def drive(name, table, key):
    """Read both sides over one case, answered or refused, in one run."""
    case = case_of(name, table, key)
    return (
        guarded(lambda: old_single(case, key)),
        guarded(lambda: new_single(case, key)),
    )


def compare(name, table, key):
    """Fail unless the two sides answered alike, or refused alike."""
    old, new = drive(name, table, key)
    assert new["error"] == old["error"], (name, old, new)
    assert new["headline"] == old["headline"], (name, old, new)
    assert readable(new["answer"]) == readable(old["answer"]), name
    assert digest(new["answer"]) == digest(old["answer"]), name
    return old, new


# ---------------------------------------------------------------------
# Value for value, and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(BLOCK_CASES))
def test_the_block_table_is_the_shipped_tabs(name):
    """The surface filled the Block Explorer differently."""
    compare(name, BLOCK_CASES, "blocks")


@pytest.mark.parametrize("name", sorted(TX_CASES))
def test_the_transaction_table_is_the_shipped_tabs(name):
    """The surface filled the Transaction Log differently."""
    compare(name, TX_CASES, "transactions")


@pytest.mark.parametrize("name", sorted(EVENT_CASES))
def test_the_event_table_is_the_shipped_tabs(name):
    """The surface filled the Contract Events table differently."""
    compare(name, EVENT_CASES, "events")


@pytest.mark.parametrize("name", sorted(HOLDER_CASES))
def test_the_holder_table_is_the_shipped_tabs(name):
    """The surface filled the Token Holders table differently."""
    compare(name, HOLDER_CASES, "holders")


@pytest.mark.parametrize("name", sorted(STATS_CASES))
def test_the_chain_status_values_are_the_shipped_tabs(name):
    """The surface filled the Chain Status row differently."""
    compare(name, STATS_CASES, "summary")


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_whole_refresh_is_the_shipped_tabs(name):
    """The surface refreshed the whole tab differently."""
    old = old_refreshed(TAB_CASES[name])
    new = new_refreshed(TAB_CASES[name])
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name


REFUSING_CASE = {
    "blocks": BLOCK_CASES["not_a_number_stamp"],
    "transactions": TX_CASES["happy"],
    "events": EVENT_CASES["happy"],
    "holders": HOLDER_CASES["no_balance_at_all"],
    "summary": stats(),
}


def broken_after_build(case, summary):
    """Build both sides on a good summary, then break it before refreshing."""
    app()
    with frozen_clock():
        tab, old_net = old_tab(case)
        old_net.stats = dict(summary)
        tab._refresh_all()
    model, new_net = new_model(case)
    new_net.stats = dict(summary)
    named = model.refresh_all(FROZEN_NOW)
    old_side = {
        "failures": sorted(
            name
            for name in surface.REFRESH_NAMES
            if getattr(tab, "_refresh_%s_fails" % name, 0)
        ),
        "blocks": read_table(tab._block_tbl),
        "holders": read_table(tab._tok_tbl),
    }
    new_side = {
        "failures": sorted(set(named)),
        "blocks": canon_cells(model.block_rows),
        "holders": canon_cells(model.holder_rows),
    }
    return old_side, new_side


def test_a_whole_refresh_names_its_failures_instead_of_refusing():
    """A refresh that failed ended the whole refresh, or was never named."""
    old, new = broken_after_build(REFUSING_CASE, {})
    assert old["failures"] == ["blocks", "holders", "stats"], old["failures"]
    assert new["failures"] == old["failures"]
    assert readable(new) == readable(old)
    assert digest(new) == digest(old)
    quiet_old, quiet_new = broken_after_build(TAB_CASES["full"], stats())
    assert quiet_old["failures"] == []
    assert quiet_new["failures"] == []
    assert readable(quiet_new) == readable(quiet_old)


def test_the_sample_hashes_are_reported():
    """The hash of a driven case is not a hash."""
    samples = {name: digest(new_refreshed(TAB_CASES[name])) for name in TAB_CASES}
    for name, found in samples.items():
        assert re.fullmatch(r"[0-9a-f]{64}", found), (name, found)
    assert len(set(samples.values())) == len(samples), samples
    assert digest(new_refreshed(TAB_CASES["full"])) == samples["full"]


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash is one value whatever it is given, so it tells nothing apart."""
    old_full = digest(old_refreshed(TAB_CASES["full"]))
    new_full = digest(new_refreshed(TAB_CASES["full"]))
    old_bare = digest(old_refreshed(TAB_CASES["bare"]))
    new_bare = digest(new_refreshed(TAB_CASES["bare"]))
    assert old_full == new_full
    assert old_bare == new_bare
    assert old_full != new_bare, "the old full case hashed as the new bare case"
    assert new_full != old_bare, "the new full case hashed as the old bare case"
    assert digest(new_refreshed(TAB_CASES["full"])) == new_full


def test_a_whole_number_and_a_decimal_are_told_apart():
    """A whole number and a decimal read as one value."""
    assert readable(12) != readable(12.0)
    assert digest({"n": 12}) != digest({"n": 12.0})
    old_whole, new_whole = compare("whole_number", BLOCK_CASES, "blocks")
    old_decimal, new_decimal = compare("decimal_number", BLOCK_CASES, "blocks")
    assert new_whole["answer"][0][0]["text"] == "12"
    assert new_decimal["answer"][0][0]["text"] == "12.0"
    assert digest(new_whole["answer"]) != digest(new_decimal["answer"])
    assert digest(old_whole["answer"]) != digest(old_decimal["answer"])


def test_two_not_a_numbers_built_apart_compare_equal():
    """Two not-a-numbers read as different values, so every case reports one."""
    first = float("nan")
    second = float("nan") * 1
    assert first != second
    assert math.isnan(first) and math.isnan(second)
    assert readable(first) == readable(second)
    assert digest({"n": first}) == digest({"n": second})
    assert digest({"n": first}) != digest({"n": 0.0})


def test_a_list_and_a_tuple_of_the_same_values_read_alike():
    """A list and a tuple of one set of values read as different tables."""
    assert readable([1, 2]) == readable((1, 2))
    assert digest({"t": [TX_HASH]}) == digest({"t": (TX_HASH,)})
    _, new_list = compare("list_of_transactions", BLOCK_CASES, "blocks")
    _, new_tuple = compare("tuple_of_transactions", BLOCK_CASES, "blocks")
    assert digest(new_list["answer"]) == digest(new_tuple["answer"])


def test_the_masking_rule_keeps_a_seeded_value_and_hides_a_chosen_one():
    """The mask hides a value this test seeded, or keeps one the machine made."""
    assert masked(BLOCK_HASH) == BLOCK_HASH
    assert masked(ADDRESS_ONE) == ADDRESS_ONE
    assert masked(SEEDED_STAMP) == SEEDED_STAMP
    assert masked(UNSEEDED_HASH) == UNSEEDED_HASH_MARK
    assert masked("07:41:09") == CLOCK_MARK
    assert masked({"a": [UNSEEDED_HASH, BLOCK_HASH]}) == {
        "a": [UNSEEDED_HASH_MARK, BLOCK_HASH]
    }
    assert masked("not a stamp") == "not a stamp"


def test_the_frozen_clock_reaches_both_sides():
    """The clock was never frozen, so the block age is the host's, not the tab's."""
    real = time.time()
    with frozen_clock():
        assert time.time() == FROZEN_NOW
        assert shipped.time.time() == FROZEN_NOW
        assert surface.time.time() == FROZEN_NOW
    assert time.time() >= real
    assert time.time() != FROZEN_NOW
    with frozen_clock(FROZEN_NOW + 100):
        moved = surface.block_age(STAMP_ONE, time.time())
    with frozen_clock():
        held = surface.block_age(STAMP_ONE, time.time())
    assert moved != held, (moved, held)


# ---------------------------------------------------------------------
# Both sides answered, or both refused, with the same wording
# ---------------------------------------------------------------------


def outcomes(table, key):
    """Every case's outcome on both sides, answered or refused."""
    return {name: drive(name, table, key) for name in sorted(table)}


@pytest.mark.parametrize(
    "table,key,refusing",
    [
        (BLOCK_CASES, "blocks", BLOCK_REFUSING),
        (TX_CASES, "transactions", TX_REFUSING),
        (EVENT_CASES, "events", EVENT_REFUSING),
        (HOLDER_CASES, "holders", HOLDER_REFUSING),
    ],
    ids=["blocks", "transactions", "events", "holders"],
)
def test_the_refresh_outcomes_are_the_shipped_tabs(table, key, refusing):
    """One side answered where the other refused, or refused differently."""
    found = outcomes(table, key)
    for name, (old, new) in found.items():
        assert new["error"] == old["error"], (name, old, new)
        assert new["headline"] == old["headline"], (name, old, new)
    named = sorted(name for name, (old, _) in found.items() if old["error"])
    assert named == sorted(refusing), named


def test_the_refresh_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    every = {}
    for table, key in (
        (BLOCK_CASES, "blocks"),
        (TX_CASES, "transactions"),
        (HOLDER_CASES, "holders"),
        (STATS_CASES, "summary"),
    ):
        every.update(
            {
                "%s.%s" % (key, name): old["error"]
                for name, (old, _) in outcomes(table, key).items()
            }
        )
    kinds = set(every.values())
    assert "" in kinds, every
    assert kinds - {""}, every
    assert "OverflowError" in kinds, sorted(kinds)
    assert "ValueError" in kinds, sorted(kinds)
    assert "TypeError" in kinds, sorted(kinds)


def test_the_stats_outcomes_are_the_shipped_tabs():
    """One side answered the Chain Status row where the other refused."""
    found = outcomes(STATS_CASES, "summary")
    for name, (old, new) in found.items():
        assert new["error"] == old["error"], (name, old, new)
        assert new["headline"] == old["headline"], (name, old, new)
    named = sorted(name for name, (old, _) in found.items() if old["error"])
    assert named == sorted(STATS_REFUSING), named


def test_the_refusal_comparison_reports_two_different_wordings():
    """The refusal comparison passes whatever the two sides said."""
    first = guarded(lambda: int(float("inf")))
    second = guarded(lambda: int(float("nan")))
    assert first["error"] == "OverflowError"
    assert second["error"] == "ValueError"
    assert first["error"] != second["error"]
    assert first["headline"] != second["headline"]
    same = guarded(lambda: int(float("inf")))
    assert same["headline"] == first["headline"]


def test_the_refusal_wording_is_read_off_the_shipped_side():
    """The wording was typed into the test instead of read off the tab."""
    case = case_of("no_keys_at_all", STATS_CASES, "summary")
    old = guarded(lambda: old_refreshed(case))
    new = guarded(lambda: new_refreshed(case))
    assert old["error"] == "KeyError"
    assert new["error"] == old["error"]
    assert new["headline"] == old["headline"]
    assert old["headline"] != [""]


# ---------------------------------------------------------------------
# Step sequences, not only single inputs
# ---------------------------------------------------------------------


def old_steps(steps, bridge_signals=surface.BRIDGE_SIGNALS):
    """Run one sequence of button presses against the shipped tab."""
    app()
    bridge = qt_bridge(bridge_signals) if bridge_signals is not None else None
    with frozen_clock(), watched_log() as log:
        tab, testnet = old_tab(TAB_CASES["full"], bridge)
        for step in steps:
            run_step_on_tab(tab, step)
    return {
        "log": log.lines,
        "run_enabled": tab._run_btn.isEnabled(),
        "stress_enabled": tab._stress_btn.isEnabled(),
        "comp_count": tab._comp_count,
        "requests": [request_fields(item) for item in getattr(bridge, "requests", [])],
        "resets": list(getattr(bridge, "resets", [])),
        "prices": dict(testnet.prices),
        "runs": [dict(item) for item in testnet.runs],
        "stat_values": {key: box.text() for key, box in tab._stat_vals.items()},
    }


def request_fields(request):
    """One queued competition request, read as the fields it carries."""
    import dataclasses

    if dataclasses.is_dataclass(request):
        return dataclasses.asdict(request)
    return dict(request)


def run_step_on_tab(tab, step):
    """Run one named step against the shipped tab."""
    name = step["do"]
    if name == "run":
        tab._run_btn.click()
    elif name == "stress":
        tab._stress_btn.click()
    elif name == "reset":
        with answered_dialog(step["confirmed"]):
            tab._reset_btn.click()
    elif name == "bridge_done":
        tab._on_bridge_competition(step["result"])
    elif name == "price":
        tab._btc_price.setValue(step["price"])
    elif name == "refresh":
        tab._refresh_all()
    elif name == "chain_reset":
        tab._bridge.chain_reset.emit(step["reason"])
    else:
        raise ValueError("unknown step: %r" % name)


def new_steps(steps, bridge_signals=surface.BRIDGE_SIGNALS):
    """Run the same sequence against the surface's model."""
    bridge = surface.BridgeSnapshot() if bridge_signals is not None else None
    if bridge is not None:
        bridge.SIGNALS = tuple(bridge_signals)
    model, testnet = new_model(TAB_CASES["full"], bridge)
    for step in steps:
        run_step_on_model(model, step)
    return {
        "log": model.log_lines,
        "run_enabled": model.run_enabled,
        "stress_enabled": model.stress_enabled,
        "comp_count": model.comp_count,
        "requests": [request_fields(item) for item in getattr(bridge, "requests", [])],
        "resets": list(getattr(bridge, "resets", [])),
        "prices": dict(testnet.prices),
        "runs": [dict(item) for item in testnet.runs],
        "stat_values": dict(model.stat_values),
    }


def run_step_on_model(model, step):
    """Run one named step against the surface's model, button gate included.

    A press on a switched-off button does nothing at all, the way a click
    on a disabled widget does nothing.
    """
    name = step["do"]
    if name == "run":
        if not model.run_enabled:
            return
        model.run_competition(
            surface.SYMBOL_DEFAULT,
            surface.SEASON_DEFAULT,
            surface.BOTS_DEFAULT,
            FROZEN_NOW,
        )
    elif name == "stress":
        if not model.stress_enabled:
            return
        model.stress_test(surface.SYMBOL_DEFAULT, surface.SEASON_DEFAULT, FROZEN_NOW)
    elif name == "reset":
        model.reset_chain(step["confirmed"], FROZEN_NOW)
    elif name == "bridge_done":
        model.on_bridge_competition(step["result"], FROZEN_NOW)
    elif name == "price":
        model.set_mock_price(step["price"])
    elif name == "refresh":
        model.refresh_all(FROZEN_NOW)
    elif name == "chain_reset":
        model.chain_reset_message(step["reason"])
    else:
        raise ValueError("unknown step: %r" % name)


SEQUENCES: dict = {
    "run_once": [{"do": "run"}],
    "run_twice": [{"do": "run"}, {"do": "run"}],
    "stress_once": [{"do": "stress"}],
    "run_then_stress": [{"do": "run"}, {"do": "stress"}],
    "run_then_done": [
        {"do": "run"},
        {"do": "bridge_done", "result": result()},
    ],
    "run_then_failed": [
        {"do": "run"},
        {"do": "bridge_done", "result": {"error": "worker exploded"}},
    ],
    "stress_then_done": [
        {"do": "stress"},
        {"do": "bridge_done", "result": result()},
        {"do": "bridge_done", "result": result(competition_id="comp-2")},
    ],
    "reset_confirmed": [{"do": "reset", "confirmed": True}],
    "reset_cancelled": [{"do": "reset", "confirmed": False}],
    "reset_then_run": [{"do": "reset", "confirmed": True}, {"do": "run"}],
    "price_then_run": [{"do": "price", "price": 70_000}, {"do": "run"}],
    "price_below_the_floor": [{"do": "price", "price": 1}],
    "price_above_the_ceiling": [{"do": "price", "price": 999_999}],
    "refresh_twice": [{"do": "refresh"}, {"do": "refresh"}],
    "chain_reset_signal": [{"do": "chain_reset", "reason": "schema upgrade"}],
    "chain_reset_unicode": [{"do": "chain_reset", "reason": UNICODE_TEXT}],
    "everything": [
        {"do": "price", "price": 70_000},
        {"do": "run"},
        {"do": "bridge_done", "result": result()},
        {"do": "stress"},
        {"do": "bridge_done", "result": {"error": "no"}},
        {"do": "reset", "confirmed": True},
        {"do": "refresh"},
    ],
}


def stamped(lines):
    """One log, with every clock stamp hidden and every number read as text."""
    return readable(lines)


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_the_step_sequence_is_the_shipped_tabs(name):
    """A sequence of presses left the surface in a different state."""
    old = old_steps(SEQUENCES[name])
    new = new_steps(SEQUENCES[name])
    assert stamped(new["log"]) == stamped(old["log"]), name
    assert new["run_enabled"] == old["run_enabled"], name
    assert new["stress_enabled"] == old["stress_enabled"], name
    assert new["comp_count"] == old["comp_count"], name
    assert readable(new["requests"]) == readable(old["requests"]), name
    assert readable(new["resets"]) == readable(old["resets"]), name
    assert readable(new["prices"]) == readable(old["prices"]), name
    assert readable(new["runs"]) == readable(old["runs"]), name
    assert digest(stamped(new)) == digest(stamped(old)), name


def test_the_sequence_comparison_reports_two_different_sequences():
    """The sequence comparison passes whatever the second sequence did."""
    one = digest(stamped(new_steps(SEQUENCES["run_once"])))
    two = digest(stamped(new_steps(SEQUENCES["stress_once"])))
    assert one != two
    assert digest(stamped(old_steps(SEQUENCES["run_once"]))) == one
    assert digest(stamped(old_steps(SEQUENCES["stress_once"]))) == two
    assert digest(stamped(old_steps(SEQUENCES["run_once"]))) != two


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_the_step_sequence_without_a_bridge_is_the_shipped_tabs(name):
    """A sequence with no bridge left the surface in a different state."""
    steps = [step for step in SEQUENCES[name] if step["do"] != "chain_reset"]
    if not steps:
        pytest.skip("this sequence only drives a bridge signal")
    old = guarded(lambda: old_steps(steps, bridge_signals=None))
    new = guarded(lambda: new_steps(steps, bridge_signals=None))
    assert new["error"] == old["error"], (name, old, new)
    if old["answer"] is None:
        return
    assert stamped(new["answer"]["log"]) == stamped(old["answer"]["log"]), name
    assert new["answer"]["comp_count"] == old["answer"]["comp_count"], name
    assert readable(new["answer"]["runs"]) == readable(old["answer"]["runs"]), name


def test_a_bridge_missing_a_signal_is_handled_the_same_way():
    """One side kept running past a bridge signal the other side refused."""
    signals = ("chain_updated", "chain_reset")
    old = old_steps([{"do": "run"}], bridge_signals=signals)
    new = new_steps([{"do": "run"}], bridge_signals=signals)
    assert readable(new["requests"]) == readable(old["requests"])
    assert len(old["requests"]) == 1
    assert stamped(new["log"]) == stamped(old["log"])


def test_a_second_unique_wiring_keeps_one_delivery_on_both_sides():
    """A repeated wiring delivers twice on one side and once on the other."""
    app()
    bridge = qt_bridge()
    with frozen_clock():
        tab, _ = old_tab(TAB_CASES["full"], bridge)
        tab._run_competition()
        tab._run_competition()
    assert len(bridge.requests) == 2
    seen: list = []
    tab._on_bridge_competition = seen.append
    bridge.competition_completed.emit(result())
    assert len(seen) == 1, seen
    model = surface.BridgeSnapshot()
    assert model.connect("competition_completed") is True
    assert model.connect("competition_completed") is False
    assert model.wired == ["competition_completed"]


def test_a_click_on_a_switched_off_button_does_nothing():
    """A switched-off button still runs, so the gate on it does nothing."""
    app()
    bridge = qt_bridge()
    with frozen_clock():
        tab, _ = old_tab(TAB_CASES["full"], bridge)
        tab._run_btn.click()
        assert tab._run_btn.isEnabled() is False
        tab._run_btn.click()
    assert len(bridge.requests) == 1
    model, _ = new_model(TAB_CASES["full"], surface.BridgeSnapshot())
    run_step_on_model(model, {"do": "run"})
    assert model.run_enabled is False
    run_step_on_model(model, {"do": "run"})
    assert len(model.bridge.requests) == 1


# ---------------------------------------------------------------------
# One finished competition, run inline and taken off the bridge
# ---------------------------------------------------------------------


def old_run_result(outcome):
    """Drive the shipped inline run over one finished competition."""
    case = dict(TAB_CASES["full"])
    case["result"] = outcome
    with frozen_clock(), watched_log() as log:
        tab, _ = old_tab(case)
        tab._run_competition()
    return {
        "log": log.lines,
        "comp_count": tab._comp_count,
        "run_enabled": tab._run_btn.isEnabled(),
    }


def new_run_result(outcome):
    """Drive the surface's inline run over the same finished competition."""
    case = dict(TAB_CASES["full"])
    case["result"] = outcome
    model, _ = new_model(case)
    model.run_competition(now=FROZEN_NOW)
    return {
        "log": model.log_lines,
        "comp_count": model.comp_count,
        "run_enabled": model.run_enabled,
    }


def old_bridge_result(outcome):
    """Drive the shipped bridge callback over one finished competition."""
    with frozen_clock(), watched_log() as log:
        tab, _ = old_tab(TAB_CASES["full"], qt_bridge())
        tab._on_bridge_competition(outcome)
    return {
        "log": log.lines,
        "comp_count": tab._comp_count,
        "run_enabled": tab._run_btn.isEnabled(),
        "stress_enabled": tab._stress_btn.isEnabled(),
    }


def new_bridge_result(outcome):
    """Drive the surface's bridge callback over the same competition."""
    model, _ = new_model(TAB_CASES["full"], surface.BridgeSnapshot())
    model.on_bridge_competition(outcome, FROZEN_NOW)
    return {
        "log": model.log_lines,
        "comp_count": model.comp_count,
        "run_enabled": model.run_enabled,
        "stress_enabled": model.stress_enabled,
    }


@pytest.mark.parametrize("name", sorted(RESULT_CASES))
def test_the_inline_run_is_the_shipped_tabs(name):
    """The surface logged a finished competition differently."""
    outcome = RESULT_CASES[name]
    old = guarded(lambda: old_run_result(outcome))
    new = guarded(lambda: new_run_result(outcome))
    assert new["error"] == old["error"], (name, old, new)
    assert new["headline"] == old["headline"], (name, old, new)
    assert stamped(new["answer"]) == stamped(old["answer"]), name
    assert digest(stamped(new["answer"])) == digest(stamped(old["answer"])), name


@pytest.mark.parametrize("name", sorted(BRIDGE_RESULT_CASES))
def test_the_bridge_callback_is_the_shipped_tabs(name):
    """The surface took a finished competition off the bridge differently."""
    outcome = BRIDGE_RESULT_CASES[name]
    old = guarded(lambda: old_bridge_result(outcome))
    new = guarded(lambda: new_bridge_result(outcome))
    assert new["error"] == old["error"], (name, old, new)
    assert new["headline"] == old["headline"], (name, old, new)
    assert stamped(new["answer"]) == stamped(old["answer"]), name
    assert digest(stamped(new["answer"])) == digest(stamped(old["answer"])), name


def test_the_result_outcomes_hold_an_answer_a_logged_error_and_a_refusal():
    """Every result case ended alike, so the set of outcomes proves nothing."""
    inline = {
        name: guarded(lambda: old_run_result(RESULT_CASES[name]))
        for name in sorted(RESULT_CASES)
    }
    logged = {
        name
        for name, found in inline.items()
        if found["answer"] and any("Error:" in line for line in found["answer"]["log"])
    }
    quiet = {
        name for name, found in inline.items() if found["answer"] and name not in logged
    }
    assert logged, sorted(inline)
    assert quiet, sorted(inline)
    assert logged & quiet == set()
    over = {
        name: guarded(lambda: old_bridge_result(BRIDGE_RESULT_CASES[name]))
        for name in sorted(BRIDGE_RESULT_CASES)
    }
    kinds = {found["error"] for found in over.values()}
    assert "" in kinds, kinds
    assert kinds - {""}, kinds
    failed = {
        name
        for name, found in over.items()
        if found["answer"]
        and any("Competition failed" in line for line in found["answer"]["log"])
    }
    assert failed, sorted(over)


def test_the_two_winner_lines_use_different_ellipses():
    """One ellipsis was copied over the other, so the two lines read alike."""
    inline = new_run_result(result())["log"]
    over = new_bridge_result(result())["log"]
    inline_winner = [line for line in inline if "Winner:" in line][0]
    over_winner = [line for line in over if "Winner:" in line][0]
    assert "..." in inline_winner and "\u2026" not in inline_winner
    assert "\u2026" in over_winner
    assert inline_winner != over_winner
    old_inline = [line for line in old_run_result(result())["log"] if "Winner:" in line]
    old_over = [
        line for line in old_bridge_result(result())["log"] if "Winner:" in line
    ]
    assert stamped(old_inline) == stamped([inline_winner])
    assert stamped(old_over) == stamped([over_winner])


# ---------------------------------------------------------------------
# Every path the tab can take is reached
# ---------------------------------------------------------------------


def test_every_named_path_is_reached_on_both_sides():
    """A path the surface names is never driven, so it is never compared."""
    reached = {"run": set(), "stress": set(), "reset": set(), "bridge": set()}
    model, _ = new_model(TAB_CASES["full"], surface.BridgeSnapshot())
    model.run_competition()
    reached["run"].add(model.run_path)
    model.stress_test()
    reached["stress"].add(model.stress_path)
    model.reset_chain(True)
    reached["reset"].add(model.reset_path)
    model.reset_chain(False)
    reached["reset"].add(model.reset_path)
    model.on_bridge_competition(result())
    reached["bridge"].add(model.bridge_path)
    model.on_bridge_competition({"error": "no"})
    reached["bridge"].add(model.bridge_path)
    plain, _ = new_model(TAB_CASES["full"])
    plain.run_competition(now=FROZEN_NOW)
    reached["run"].add(plain.run_path)
    plain.stress_test(now=FROZEN_NOW)
    reached["stress"].add(plain.stress_path)
    plain.reset_chain(True, FROZEN_NOW)
    reached["reset"].add(plain.reset_path)
    broken, broken_net = new_model(TAB_CASES["full"])
    broken_net.error = RuntimeError("chain gone")
    broken.run_competition(now=FROZEN_NOW)
    reached["run"].add(broken.run_path)
    broken.stress_test(now=FROZEN_NOW)
    reached["stress"].add(broken.stress_path)
    assert reached["run"] == set(surface.RUN_PATHS), reached["run"]
    assert reached["stress"] == set(surface.STRESS_PATHS), reached["stress"]
    assert reached["reset"] == set(surface.RESET_PATHS), reached["reset"]
    assert reached["bridge"] == set(surface.BRIDGE_PATHS), reached["bridge"]
    assert set(surface.WIRED_PATHS) == {model.wired_path, plain.wired_path}


def test_the_path_names_are_all_different():
    """Two paths share one name, so reaching one reads as reaching the other."""
    every = (
        surface.RUN_PATHS
        + surface.STRESS_PATHS
        + surface.RESET_PATHS
        + surface.BRIDGE_PATHS
        + surface.WIRED_PATHS
    )
    assert len(set(every)) == len(every), every
    assert len(every) == 13


# ---------------------------------------------------------------------
# The whole widget tree
# ---------------------------------------------------------------------


def qt_kind(found):
    """The class name of one Qt object, as the surface names it."""
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QFrame,
        QGroupBox,
        QLabel,
        QPushButton,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTextEdit,
        QWidget,
    )

    for kind in (
        QGroupBox,
        QTableWidget,
        QTextEdit,
        QComboBox,
        QDoubleSpinBox,
        QSpinBox,
        QPushButton,
        QLabel,
        QSplitter,
        QFrame,
        QWidget,
    ):
        if isinstance(found, kind):
            return kind.__name__
    return type(found).__name__


def qt_tree(tab):
    """Every Qt node of the shipped tab, in the order the tab builds it."""
    from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QSplitter, QVBoxLayout

    found = [{"kind": "QWidget", "object": tab, "parent": -1}]

    def visit(layout, parent):
        for entry in layout_entries(layout):
            if entry == "stretch":
                found.append({"kind": "stretch", "object": None, "parent": parent})
                continue
            if isinstance(entry, (QVBoxLayout, QHBoxLayout)):
                found.append(
                    {
                        "kind": type(entry).__name__,
                        "object": entry,
                        "parent": parent,
                    }
                )
                visit(entry, len(found) - 1)
                continue
            kind = qt_kind(entry)
            found.append({"kind": kind, "object": entry, "parent": parent})
            here = len(found) - 1
            if isinstance(entry, QSplitter):
                for index in range(entry.count()):
                    child = entry.widget(index)
                    found.append(
                        {"kind": qt_kind(child), "object": child, "parent": here}
                    )
                    inner = child.layout()
                    if inner is not None:
                        visit(inner, len(found) - 1)
                continue
            if isinstance(entry, QGroupBox) and entry.layout() is not None:
                visit(entry.layout(), here)

    visit(tab.layout(), 0)
    return found


def widget_value(found, key):
    """One declared value, read off the real Qt object it was set on."""
    from PySide6.QtWidgets import QHeaderView

    node = found["object"]
    if key == "accessible_name":
        return node.accessibleName()
    if key == "layout":
        return type(node.layout()).__name__
    if key == "margins":
        margins = node.layout().contentsMargins()
        return [margins.left(), margins.top(), margins.right(), margins.bottom()]
    if key == "spacing":
        return node.layout().spacing()
    if key == "style_sheet":
        return node.styleSheet()
    if key == "text":
        return node.text()
    if key == "title":
        return node.title()
    if key == "alignment":
        return (
            surface.ALIGNMENT
            if node.alignment().value == surface.ALIGNMENT_VALUE
            else str(node.alignment().value)
        )
    if key == "frame_shape_value":
        return node.frameShape().value
    if key == "enabled":
        return node.isEnabled()
    if key == "minimum":
        return node.minimum()
    if key == "maximum":
        return node.maximum()
    if key == "value":
        return node.value()
    if key == "decimals":
        return node.decimals()
    if key == "fixed_width":
        return node.maximumWidth()
    if key == "items":
        return [node.itemText(index) for index in range(node.count())]
    if key == "current_text":
        return node.currentText()
    if key == "current_index":
        return node.currentIndex()
    if key == "read_only":
        return node.isReadOnly()
    if key == "max_height":
        return node.maximumHeight()
    if key == "orientation_value":
        return node.orientation().value
    if key == "handle_width":
        return node.handleWidth()
    if key == "children_collapsible":
        return node.childrenCollapsible()
    if key == "columns":
        return [
            node.horizontalHeaderItem(index).text()
            for index in range(node.columnCount())
        ]
    if key == "column_count":
        return node.columnCount()
    if key == "header_resize_value":
        return node.horizontalHeader().sectionResizeMode(0).value
    if key == "vertical_header_visible":
        return node.verticalHeader().isVisible()
    if key == "edit_triggers_value":
        return node.editTriggers().value
    if key == "selection_behavior_value":
        return node.selectionBehavior().value
    del QHeaderView
    raise KeyError(key)


IGNORED_KEYS = ("name", "kind", "parent")


def old_tree(tab, nodes):
    """The shipped tab's tree, read for exactly the keys the surface names."""
    qt = qt_tree(tab)
    assert len(qt) == len(nodes), (len(qt), len(nodes))
    found = []
    for index, (node, side) in enumerate(zip(nodes, qt, strict=True)):
        values = {
            key: widget_value(side, key) for key in node if key not in IGNORED_KEYS
        }
        parent = "" if side["parent"] < 0 else nodes[side["parent"]]["name"]
        found.append(
            {
                "name": node["name"],
                "kind": side["kind"],
                "parent": parent,
                "values": values,
            }
        )
        del index
    return found


def new_tree(nodes):
    """The surface's tree in the same shape the shipped tree is read into."""
    return [
        {
            "name": node["name"],
            "kind": node["kind"],
            "parent": node["parent"],
            "values": {
                key: value for key, value in node.items() if key not in IGNORED_KEYS
            },
        }
        for node in nodes
    ]


def tree_pair(name):
    """The two trees for one case, read on the same machine in one run."""
    app()
    with frozen_clock():
        tab, _ = old_tab(TAB_CASES[name])
    model, _ = new_model(TAB_CASES[name])
    nodes = model.setup_ui()
    return old_tree(tab, nodes), new_tree(nodes)


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_whole_tab_tree_is_the_shipped_tabs(name):
    """The surface built a widget the shipped tab does not build."""
    old, new = tree_pair(name)
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name
    assert len(new) == 53, len(new)


def test_the_tree_comparison_reports_a_swap_of_two_nodes():
    """The tree comparison passes whatever order the surface builds in."""
    old, new = tree_pair("full")
    swapped = list(new)
    first = next(i for i, node in enumerate(swapped) if node["name"] == "run_button")
    second = next(i for i, node in enumerate(swapped) if node["name"] == "reset_button")
    swapped[first], swapped[second] = swapped[second], swapped[first]
    assert readable(swapped) != readable(old)
    assert digest(swapped) != digest(old)
    thinned = new[:-1]
    assert readable(thinned) != readable(old)


def test_the_tree_reader_reads_the_two_sides_apart():
    """The tree reader reads one side twice, so a difference cannot appear."""
    old_full, new_full = tree_pair("full")
    old_bare, new_bare = tree_pair("bare")
    assert digest(new_full) != digest(new_bare)
    assert digest(old_full) != digest(old_bare)
    assert digest(old_full) == digest(new_full)
    assert digest(old_bare) == digest(new_bare)


def test_the_tab_uses_the_testnet_it_was_given():
    """The tab built its own chain instead of using the shared one."""
    app()
    given = net_of(summary=stats(block_number=4242))
    assert bool(given) is True, "a falsy stand-in makes the tab build its own chain"
    tab = hold(shipped.TestnetTab(None, given, None))
    assert tab._testnet is given
    assert tab._stat_vals["Block"].text() == "4242"
    model = surface.TestnetTabModel(given)
    model.setup_ui()
    assert model.testnet is given
    assert model.stat_values["Block"] == "4242"


# ---------------------------------------------------------------------
# The surface writes its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so a broken value moves both sides."""
    app()
    original = shipped.CYAN
    try:
        shipped.CYAN = "#123456"
        assert surface.CYAN == "#00FFEE"
        assert surface.TITLE_STYLE.count("#00FFEE") == 1
        old, new = tree_pair("full")
    finally:
        shipped.CYAN = original
    assert shipped.CYAN == "#00FFEE"
    differing = [
        node["name"]
        for index, node in enumerate(new)
        if readable(node["values"]) != readable(old[index]["values"])
    ]
    assert differing == [
        "title",
        "status_section",
        "stat_value_0",
        "stat_value_1",
        "stat_value_2",
        "stat_value_3",
        "stat_value_4",
        "stat_value_5",
        "run_section",
        "bots_spin",
        "symbol_combo",
        "season_spin",
        "run_button",
        "blocks_section",
        "transactions_section",
        "events_section",
        "holders_section",
        "log_section",
    ], differing
    moved = next(node for node in old if node["name"] == "title")
    assert moved["values"]["style_sheet"].count("#123456") == 1
    kept = next(node for node in new if node["name"] == "title")
    assert kept["values"]["style_sheet"].count("#00FFEE") == 1
    restored_old, restored_new = tree_pair("full")
    assert readable(restored_old) == readable(restored_new)


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
    "QDoubleSpinBox",
    "QTextEdit",
    "QProgressBar",
    "QSplitter",
    "QDialog",
    "QMessageBox",
)


def count_text(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, names):
    """How many times one file constructs any of `names`."""
    text = path.read_text(encoding="utf-8")
    return sum(len(re.findall(r"\b%s\s*\(" % name, text)) for name in names)


def class_statements(path):
    """Every class statement one file holds, nested classes included.

    A class inside another class, and a class inside an ``if``, are both
    classes the file builds. Counting names alone would collapse two
    classes that share one name into one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def declared_widget_classes(path):
    """Every class statement one file makes that ends up a screen element.

    A class whose base is a widget is one, and so is a class whose base is
    another such class, however many steps away.
    """
    nodes = class_statements(path)
    found: list = []
    names: set = set()
    growing = True
    while growing:
        growing = False
        for node in nodes:
            if node in found:
                continue
            for base in node.bases:
                name = (
                    base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                )
                if name.startswith("Q") or name in names:
                    found.append(node)
                    names.add(node.name)
                    growing = True
                    break
    return found


def count_elements(path):
    """How many screen elements one file builds, its own classes included."""
    return count_built(path, WIDGET_NAMES_BUILT) + len(declared_widget_classes(path))


def test_the_tab_wires_nine_signals():
    """A signal wiring appeared on one side and not the other."""
    assert count_text(TAB_PATH, ".connect(") == TAB_CONNECT_SITES == 9
    assert count_text(SURFACE_PATH, ".connect(") == 1
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES == 1
    assert len(surface.ACTIONS) == TAB_CONNECT_SITES
    assert sorted(surface.ACTIONS) == [
        "bridge.chain_reset",
        "bridge.chain_updated",
        "bridge.competition_completed@run",
        "bridge.competition_completed@stress",
        "oracle_price.valueChanged",
        "refresh_timer.timeout",
        "reset_button.clicked",
        "run_button.clicked",
        "stress_button.clicked",
    ]
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.TestnetTabModel, target)), target


def test_the_tab_starts_one_timer():
    """A wait appeared on one side and not the other."""
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(TAB_PATH, timer_names) == TAB_TIMER_BUILDS == 1
    assert count_text(TAB_PATH, "QTimer") > TAB_TIMER_BUILDS
    assert count_built(SURFACE_PATH, timer_names) == 0
    assert count_built(TIMER_CONTROL_PATH, timer_names) == CONTROL_TIMER_BUILDS == 1
    assert count_built(REPO_ROOT / "src/gui/main_tabs/history_tab.py", timer_names) == 0
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
        with frozen_clock():
            old_tab(TAB_CASES["full"])
        observed = list(started)
        started.clear()
        new_model(TAB_CASES["full"])
        quiet = list(started)
        QTimer().start(250)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert started == [("QTimer.start", (250,))]
    assert observed == [("QTimer.start", (surface.REFRESH_INTERVAL_MS,))], observed
    assert quiet == []
    assert surface.TIMERS == {"refresh": surface.REFRESH_INTERVAL_MS}
    assert surface.TIMER_DELAYS_MS == (3000,)
    assert surface.AUTOSTART_TIMERS == ("refresh",)


def test_the_tab_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(TAB_PATH, ".subscribe(") == TAB_BUS_SITES == 0
    assert count_text(SURFACE_PATH, ".subscribe(") == 0
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_text(TAB_PATH, ".subscribe(")


def test_the_screen_elements_the_tab_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_built(TAB_PATH, WIDGET_NAMES_BUILT) == TAB_WIDGET_BUILDS == 15
    assert len(declared_widget_classes(TAB_PATH)) == TAB_WIDGET_CLASSES == 1
    assert count_elements(TAB_PATH) == TAB_ELEMENT_BUILDS == 16
    assert (
        count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    ), count_elements(ELEMENT_CONTROL_PATH)
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert [node.name for node in declared_widget_classes(ELEMENT_CONTROL_PATH)] == [
        "StatCard"
    ]
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == []
    model, _ = new_model(TAB_CASES["full"])
    built = model.setup_ui()
    painted = [
        node
        for node in built
        if node["kind"] not in ("stretch", "QHBoxLayout", "QVBoxLayout")
    ]
    scaffold = [
        node
        for node in built
        if node["kind"] in ("stretch", "QHBoxLayout", "QVBoxLayout")
    ]
    assert len(built) == 53
    assert len(scaffold) == 13, [node["name"] for node in scaffold]
    assert len(painted) == len(built) - len(scaffold) == 40


def test_the_class_counter_finds_a_class_inside_a_branch():
    """The class counter reads two same-named classes as one."""
    nodes = class_statements(TAB_PATH)
    assert len(nodes) == TAB_CLASS_STATEMENTS == 2
    assert [node.name for node in nodes] == ["TestnetTab", "TestnetTab"]
    assert len({node.name for node in nodes}) == 1
    nested = class_statements(REPO_ROOT / "src/gui/launcher.py")
    assert len(nested) > len({node.name for node in nested}) or len(nested) > 1
    assert len(class_statements(SURFACE_PATH)) == 8


# ---------------------------------------------------------------------
# Every class and every method has a counterpart
# ---------------------------------------------------------------------


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A signal is callable and is not a method, so it is excluded by name. A
    factory and a read-only value are not callable at all, so asking
    ``callable`` alone misses both.
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

    from src.competition.local_testnet import LocalTestnet
    from src.competition.token_ledger import AwardRecord
    from src.gui import launcher

    assert callable(Signal())
    assert "clicked" in vars(launcher.ModeCard)
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert not callable(vars(AwardRecord)["from_dict"])
    assert "from_dict" in members(AwardRecord)
    assert not callable(vars(LocalTestnet)["chain"])
    assert "chain" in members(LocalTestnet)
    assert "run_demo_competition" in members(LocalTestnet)


CLASS_MAP = {
    "TestnetTab": "TestnetTabModel",
}

METHOD_MAP = {
    "TestnetTab.__init__": "TestnetTabModel.__init__",
    "TestnetTab._refresh_all": "TestnetTabModel.refresh_all",
    "TestnetTab._setup_ui": "TestnetTabModel.setup_ui",
    "TestnetTab._msg": "TestnetTabModel.msg",
    "TestnetTab._refresh_stats": "TestnetTabModel.refresh_stats",
    "TestnetTab._reset_chain": "TestnetTabModel.reset_chain",
    "TestnetTab._run_competition": "TestnetTabModel.run_competition",
    "TestnetTab._on_bridge_competition": "TestnetTabModel.on_bridge_competition",
    "TestnetTab._stress_test": "TestnetTabModel.stress_test",
    "TestnetTab._refresh_blocks": "TestnetTabModel.refresh_blocks",
    "TestnetTab._refresh_events": "TestnetTabModel.refresh_events",
    "TestnetTab._refresh_holders": "TestnetTabModel.refresh_holders",
}

HELPER_MAP = {
    "_section": "section_node",
    "_lbl": "label_node",
    "_table": "table_node",
    "_add_row": "row_cells",
}

SURFACE_HELPERS = (
    "label_style",
    "event_color",
    "tier_color",
    "short_hash",
    "block_age",
    "holder_balance",
    "event_args_text",
    "log_line",
    "stat_text",
    "cell",
    "widget",
    "widget_children",
    "widget_index",
    "request_payload",
    "oracle_value",
    "build_chain",
    "build_model",
    "constant_view",
    "build_view_model",
    "view_model",
)

MODEL_MEMBERS = {
    "__init__",
    "wire",
    "_wire_signal",
    "chain_reset_message",
    "msg",
    "refresh_stats",
    "refresh_blocks",
    "refresh_events",
    "refresh_holders",
    "refresh_all",
    "_name_failure",
    "reset_chain",
    "run_competition",
    "on_bridge_competition",
    "stress_test",
    "set_mock_price",
    "setup_ui",
    "_status_nodes",
    "_run_nodes",
    "_split_nodes",
}

SURFACE_ONLY_CLASSES = (
    "BlockSnapshot",
    "TxSnapshot",
    "EventSnapshot",
    "ChainSnapshot",
    "AcrvSnapshot",
    "TestnetSnapshot",
    "BridgeSnapshot",
)


def resolve(dotted):
    """The member a dotted name in a map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_classes():
    """Every class the shipped module binds, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    assert shipped_classes() == set(CLASS_MAP)
    assert len(CLASS_MAP) == 1
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 12
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for name, target in HELPER_MAP.items():
        assert callable(getattr(shipped, name)), name
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 4
    for name in SURFACE_HELPERS:
        assert callable(resolve(name)), name
    assert members(surface.TestnetTabModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 20
    for name in SURFACE_ONLY_CLASSES:
        assert callable(getattr(surface, name)), name


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "_refresh_holders" in members(shipped.TestnetTab)
    assert "_setup_ui" in members(shipped.TestnetTab)
    assert "TestnetTab" not in MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("TestnetTabModel.no_such_member")
    assert MODEL_MEMBERS - {"setup_ui"} != MODEL_MEMBERS
    assert members(surface.TestnetTabModel) - {"refresh_all"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"TestnetTab.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"TestnetTab"} != shipped_classes()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    tab_init = list(inspect.signature(shipped.TestnetTab.__init__).parameters)
    assert tab_init == ["self", "parent", "shared_testnet", "bridge"]
    model_init = list(inspect.signature(surface.TestnetTabModel.__init__).parameters)
    assert model_init == ["self", "testnet", "bridge"]
    for name in ("parent", "shared_testnet", "bridge"):
        assert (
            inspect.signature(shipped.TestnetTab.__init__).parameters[name].default
            is None
        ), name
    assert list(inspect.signature(shipped._lbl).parameters) == [
        "text",
        "color",
        "size",
        "bold",
    ]
    lbl = inspect.signature(shipped._lbl).parameters
    assert lbl["color"].default == surface.LABEL_DEFAULT_COLOR
    assert lbl["size"].default == surface.LABEL_DEFAULT_SIZE
    assert lbl["bold"].default == surface.LABEL_DEFAULT_BOLD
    table = inspect.signature(shipped._table).parameters
    assert table["max_h"].default == surface.TABLE_DEFAULT_MAX_HEIGHT_PX
    assert list(inspect.signature(shipped._add_row).parameters) == [
        "tbl",
        "values",
        "colors",
    ]


HELPER_SIZE = (240, 60)


def label_from_the_surface(color, size, bold):
    """One label built from the look the surface declares for it."""
    from PySide6.QtWidgets import QLabel

    made = hold(QLabel("x"))
    made.setStyleSheet(surface.label_style(color, size, bold))
    return made


def section_from_the_surface(title):
    """One panel built from the look the surface declares for it."""
    from PySide6.QtWidgets import QGroupBox

    node = surface.section_node("status_section", title, "tab")
    made = hold(QGroupBox(node["title"]))
    made.setStyleSheet(node["style_sheet"])
    return made


LABEL_LOOKS = (
    (surface.MUTED, surface.STAT_KEY_SIZE, False),
    (surface.CYAN, surface.STAT_VALUE_SIZE, True),
    (surface.GREEN, 10, False),
    (surface.LABEL_DEFAULT_COLOR, surface.LABEL_DEFAULT_SIZE, False),
)


def test_the_shipped_helpers_paint_what_the_surface_declares():
    """A shared helper paints one look on one side and another on the other."""
    app()
    for color, size, bold in LABEL_LOOKS:
        assert_pictures_match(
            old_side=render_widget(
                hold(shipped._lbl("x", color, size, bold)), HELPER_SIZE
            ),
            new_side=render_widget(
                label_from_the_surface(color, size, bold), HELPER_SIZE
            ),
            note="label %s/%s/%s" % (color, size, bold),
        )
    assert_pictures_differ(
        old_side=render_widget(
            hold(shipped._lbl("x", surface.CYAN, 14, True)), HELPER_SIZE
        ),
        new_side=render_widget(
            label_from_the_surface(surface.MUTED, 9, False), HELPER_SIZE
        ),
        note="two different real looks",
    )
    assert_pictures_match(
        old_side=render_widget(
            hold(shipped._section(surface.STATUS_SECTION_TITLE)), PIXEL_SIZE
        ),
        new_side=render_widget(
            section_from_the_surface(surface.STATUS_SECTION_TITLE), PIXEL_SIZE
        ),
        note="the panel look",
    )
    assert_pictures_differ(
        old_side=render_widget(
            hold(shipped._section(surface.STATUS_SECTION_TITLE)), PIXEL_SIZE
        ),
        new_side=render_widget(
            section_from_the_surface(surface.LOG_SECTION_TITLE), PIXEL_SIZE
        ),
        note="two different real panels",
    )


def test_the_shipped_helpers_answer_what_the_surface_answers():
    """A shared helper answers differently on the two sides."""
    app()
    box = hold(shipped._section(surface.STATUS_SECTION_TITLE))
    node = surface.section_node("status_section", surface.STATUS_SECTION_TITLE, "tab")
    assert box.title() == node["title"] == "CHAIN STATUS"
    table = hold(shipped._table(list(surface.BLOCK_COLUMNS), 160))
    built = surface.table_node("t", "p", surface.BLOCK_COLUMNS, 160)
    assert table.maximumHeight() == built["max_height"]
    assert table.columnCount() == built["column_count"]
    assert [
        table.horizontalHeaderItem(index).text() for index in range(table.columnCount())
    ] == built["columns"]
    shipped._add_row(table, ["a", 2, "c", "d"], [surface.CYAN, None, "", surface.RED])
    made = surface.row_cells(["a", 2, "c", "d"], [surface.CYAN, None, "", surface.RED])
    assert read_table(table) == canon_cells([made])
    assert made[1]["color"] == surface.NO_COLOR
    assert read_table(table)[0][1]["color"] == surface.NO_COLOR
    assert read_table(table)[0][0]["color"] == canon_colour(surface.CYAN)


# ---------------------------------------------------------------------
# Nothing else reaches the tab
# ---------------------------------------------------------------------


def modules_importing(module, skip=()):
    """Every file under src that imports the module named exactly `module`.

    The name is matched whole. ``testnet_tab_surface`` is a different
    module from ``testnet_tab``, and a match on part of a name would count
    one as the other.
    """
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


def test_the_whole_name_is_matched_not_a_part_of_it():
    """A part-of-a-name match reads the conversion as a reader of the tab."""
    assert modules_importing("testnet_tab_surface") == [str(BRIDGE_PATH)]
    assert str(SURFACE_PATH) not in modules_importing("testnet_tab")
    known = modules_importing("design_system")
    assert len(known) > 5, known
    assert str(SURFACE_PATH) not in known
    assert modules_importing("no_such_module_anywhere") == []


def test_the_tab_is_reached_by_no_other_module():
    """A module grew a reader of the shipped tab, or one was always there."""
    readers = modules_importing("testnet_tab", skip=(SURFACE_PATH, TAB_PATH))
    assert readers == [], readers
    named = [
        str(path)
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if path not in (SURFACE_PATH, TAB_PATH)
        and "src.gui.testnet_tab" in path.read_text(encoding="utf-8")
    ]
    assert named == [], named


# ---------------------------------------------------------------------
# The tab paints, and the two sides paint the same pixels
# ---------------------------------------------------------------------


def colour_count(image):
    """How many distinct colours one render holds."""
    found = set()
    for y in range(0, image.height(), 7):
        for x in range(0, image.width(), 7):
            found.add(image.pixel(x, y))
    return len(found)


def model_payload(name):
    """One sealed payload, taken as it comes off the surface."""
    model, _ = new_model(TAB_CASES[name])
    model.refresh_all(FROZEN_NOW)
    return sealed(surface.build_view_model(model))


def fill_table(table, rows):
    """Fill one built table from the rows the payload carries."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtWidgets import QTableWidgetItem

    for row in rows:
        index = table.rowCount()
        table.insertRow(index)
        for column, found in enumerate(row):
            item = QTableWidgetItem(found["text"])
            item.setTextAlignment(Qt.AlignCenter)
            if found["color"]:
                item.setForeground(QBrush(QColor(found["color"])))
            table.setItem(index, column, item)
    table.scrollToBottom()


def tab_painted_by_the_model(payload):
    """Build one Qt tab from the surface's payload alone."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    nodes = {node["name"]: node for node in payload["widgets"]}
    built: dict = {}
    tab = hold(QWidget())
    tab.setAccessibleName(nodes["tab"]["accessible_name"])
    root = QVBoxLayout(tab)
    root.setContentsMargins(*nodes["tab"]["margins"])
    root.setSpacing(nodes["tab"]["spacing"])
    built["tab"] = root

    def add(parent, thing):
        holder = built[parent]
        if isinstance(holder, QSplitter):
            holder.addWidget(thing)
        elif isinstance(thing, (QVBoxLayout, QHBoxLayout)):
            holder.addLayout(thing)
        else:
            holder.addWidget(thing)

    for node in payload["widgets"][1:]:
        kind = node["kind"]
        name = node["name"]
        parent = node["parent"]
        if kind == "stretch":
            built[parent].addStretch()
            continue
        if kind in ("QVBoxLayout", "QHBoxLayout"):
            made = QVBoxLayout() if kind == "QVBoxLayout" else QHBoxLayout()
            add(parent, made)
            built[name] = made
            continue
        if kind == "QLabel":
            made = QLabel(node["text"])
            made.setStyleSheet(node["style_sheet"])
            if node.get("alignment") == surface.ALIGNMENT:
                made.setAlignment(Qt.AlignCenter)
        elif kind == "QFrame":
            made = QFrame()
            made.setFrameShape(QFrame.HLine)
            made.setStyleSheet(node["style_sheet"])
        elif kind == "QGroupBox":
            made = QGroupBox(node["title"])
            made.setStyleSheet(node["style_sheet"])
            QVBoxLayout(made)
        elif kind == "QSpinBox":
            made = QSpinBox()
            made.setRange(node["minimum"], node["maximum"])
            made.setValue(node["value"])
            made.setFixedWidth(node["fixed_width"])
            made.setStyleSheet(node["style_sheet"])
        elif kind == "QComboBox":
            made = QComboBox()
            made.addItems(node["items"])
            made.setFixedWidth(node["fixed_width"])
            made.setStyleSheet(node["style_sheet"])
        elif kind == "QDoubleSpinBox":
            made = QDoubleSpinBox()
            made.setRange(node["minimum"], node["maximum"])
            made.setValue(node["value"])
            made.setDecimals(node["decimals"])
            made.setFixedWidth(node["fixed_width"])
            made.setStyleSheet(node["style_sheet"])
        elif kind == "QPushButton":
            made = QPushButton(node["text"])
            made.setStyleSheet(node["style_sheet"])
            made.setEnabled(node["enabled"])
        elif kind == "QSplitter":
            made = QSplitter(Qt.Horizontal)
            made.setHandleWidth(node["handle_width"])
            made.setChildrenCollapsible(node["children_collapsible"])
        elif kind == "QTableWidget":
            made = QTableWidget(0, node["column_count"])
            made.setHorizontalHeaderLabels(node["columns"])
            made.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            made.verticalHeader().setVisible(node["vertical_header_visible"])
            made.setEditTriggers(QTableWidget.NoEditTriggers)
            made.setSelectionBehavior(QTableWidget.SelectRows)
            made.setMaximumHeight(node["max_height"])
            made.setStyleSheet(node["style_sheet"])
        elif kind == "QTextEdit":
            made = QTextEdit()
            made.setReadOnly(node["read_only"])
            made.setMaximumHeight(node["max_height"])
            made.setStyleSheet(node["style_sheet"])
        else:
            raise AssertionError("unknown kind %r" % kind)
        if kind == "QGroupBox":
            add(parent, made)
            built[name] = made.layout()
            built[name + "@box"] = made
        else:
            add(parent, made)
            built[name] = made
    for name, key in (
        ("blocks_table", "blocks"),
        ("transactions_table", "transactions"),
        ("events_table", "events"),
        ("holders_table", "holders"),
    ):
        fill_table(built[name], payload["rows"][key])
    for line in payload["log_lines"]:
        built["log_view"].append(line)
    return tab


def old_painted(name):
    """The shipped tab, refreshed, ready to render."""
    app()
    with frozen_clock():
        tab, _ = old_tab(TAB_CASES[name])
        tab._refresh_all()
    return tab


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a tab the shipped tab does not."""
    app()
    old_side = render_widget(old_painted(name), PIXEL_SIZE)
    new_side = render_widget(tab_painted_by_the_model(model_payload(name)), PIXEL_SIZE)
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the second side paints."""
    app()
    assert_pictures_differ(
        old_side=render_widget(old_painted("full"), PIXEL_SIZE),
        new_side=render_widget(
            tab_painted_by_the_model(model_payload("bare")), PIXEL_SIZE
        ),
        note="full against bare",
    )
    assert_pictures_differ(
        old_side=render_widget(old_painted("bare"), PIXEL_SIZE),
        new_side=render_widget(
            tab_painted_by_the_model(model_payload("tiers")), PIXEL_SIZE
        ),
        note="bare against tiers",
    )
    assert_pictures_match(
        old_side=render_widget(old_painted("full"), PIXEL_SIZE),
        new_side=render_widget(
            tab_painted_by_the_model(model_payload("full")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the host, not the product."""
    payload = model_payload("full")
    payload["widgets"][2]["text"] = "moved"
    with pytest.raises(AssertionError):
        tab_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        tab_painted_by_the_model({"widgets": []})
    assert tab_painted_by_the_model(model_payload("full")) is not None


def declared_skin(tab):
    """The look one tab carries in its own right, before any child paints."""
    return tab.styleSheet()


def test_the_tab_declares_no_skin_of_its_own():
    """A colour the surface ships is one the tab never paints."""
    app()
    assert surface.SKIN == {}
    assert surface.TAB_STYLE_SHEET == ""
    assert declared_skin(old_painted("full")) == surface.TAB_STYLE_SHEET
    skinned = tab_painted_by_the_model(model_payload("full"))
    skinned.setStyleSheet("QWidget { background: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(old_painted("full"), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a skin the tab does not paint",
    )
    assert_pictures_match(
        old_side=render_widget(old_painted("full"), PIXEL_SIZE),
        new_side=render_widget(
            tab_painted_by_the_model(model_payload("full")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


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


def test_the_accessible_name_is_compared_as_a_string():
    """The name a screen reader announces reached no pixel."""
    app()
    tab = old_painted("full")
    assert tab.accessibleName() == surface.ACCESSIBLE_NAME == "Testnet Tab"
    model, _ = new_model(TAB_CASES["full"])
    assert model.accessible_name == tab.accessibleName()


def test_the_layout_numbers_are_compared_as_values():
    """The margins and the spacing reached no pixel this size can report."""
    app()
    tab = old_painted("full")
    margins = tab.layout().contentsMargins()
    assert [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ] == list(surface.CONTENT_MARGINS)
    assert tab.layout().spacing() == surface.CONTENT_SPACING == 6


def test_the_table_settings_are_compared_as_values():
    """A table setting the shipped tab makes reached no pixel."""
    from PySide6.QtWidgets import QTableWidget

    app()
    tab = old_painted("full")
    tables = [
        tab._block_tbl,
        tab._tx_tbl,
        tab._evt_tbl,
        tab._tok_tbl,
    ]
    heights = [
        surface.BLOCK_TABLE_MAX_HEIGHT_PX,
        surface.TX_TABLE_MAX_HEIGHT_PX,
        surface.EVENT_TABLE_MAX_HEIGHT_PX,
        surface.HOLDER_TABLE_MAX_HEIGHT_PX,
    ]
    for table, height in zip(tables, heights, strict=True):
        assert table.horizontalHeader().sectionResizeMode(0).value == (
            surface.HEADER_RESIZE_VALUE
        )
        assert table.verticalHeader().isVisible() is surface.VERTICAL_HEADER_VISIBLE
        assert table.editTriggers().value == surface.EDIT_TRIGGERS_NONE_VALUE
        assert table.selectionBehavior().value == (
            surface.SELECTION_BEHAVIOR_ROWS_VALUE
        )
        assert table.maximumHeight() == height
    fresh = QTableWidget(0, 1)
    assert fresh.editTriggers().value == surface.EDIT_TRIGGERS_DEFAULT_VALUE
    assert fresh.selectionBehavior().value == (surface.SELECTION_BEHAVIOR_DEFAULT_VALUE)
    assert surface.EDIT_TRIGGERS_DEFAULT_VALUE != surface.EDIT_TRIGGERS_NONE_VALUE


def test_the_label_alignment_is_compared_as_a_value():
    """The centred stat labels reached no pixel a difference could show in."""
    from PySide6.QtWidgets import QLabel

    app()
    tab = old_painted("full")
    for box in tab._stat_vals.values():
        assert box.alignment().value == surface.ALIGNMENT_VALUE == 132
    plain = hold(QLabel("x"))
    assert plain.alignment().value == surface.LABEL_DEFAULT_ALIGNMENT_VALUE == 129


def test_the_frame_and_splitter_numbers_are_compared_as_values():
    """The separator shape and the splitter handle reached no pixel."""
    from PySide6.QtWidgets import QFrame, QSplitter

    app()
    tab = old_painted("full")
    frames = [
        found
        for found in tab.findChildren(QFrame)
        if found.frameShape().value == surface.SEPARATOR_FRAME_SHAPE_VALUE
    ]
    assert frames, "the separator is gone"
    splitters = tab.findChildren(QSplitter)
    assert len(splitters) == 1
    assert splitters[0].handleWidth() == surface.SPLITTER_HANDLE_WIDTH_PX == 5
    assert splitters[0].childrenCollapsible() is False
    assert splitters[0].orientation().value == surface.SPLITTER_ORIENTATION_VALUE


def test_the_log_lines_are_compared_as_the_markup_the_tab_wrote():
    """Qt rewrites the log, so the read-back hides what the tab produced."""
    old = old_steps(SEQUENCES["run_once"])
    new = new_steps(SEQUENCES["run_once"])
    assert old["log"], "the shipped tab wrote nothing to its log"
    assert stamped(new["log"]) == stamped(old["log"])
    assert all("<span" in line for line in old["log"])
    assert surface.LOG_LINE_FORMAT.startswith('<span style="color:#445566">')
    assert CLOCK_MARK in json.dumps(stamped(old["log"]))


def test_the_spin_box_rewrites_a_value_outside_its_range():
    """The spin box kept a value outside its range, so the range does nothing."""
    app()
    tab = old_painted("full")
    tab._btc_price.setValue(999_999)
    assert tab._btc_price.value() == surface.ORACLE_MAXIMUM
    tab._btc_price.setValue(1)
    assert tab._btc_price.value() == surface.ORACLE_MINIMUM
    tab._n_bots.setValue(99)
    assert tab._n_bots.value() == surface.BOTS_MAXIMUM
    tab._season.setValue(0)
    assert tab._season.value() == surface.SEASON_MINIMUM
    assert tab._btc_price.minimum() == surface.ORACLE_MINIMUM
    assert tab._btc_price.maximum() == surface.ORACLE_MAXIMUM


def test_the_recorded_calls_are_compared_as_values():
    """The step sequence the surface records is never read."""
    model, _ = new_model(TAB_CASES["full"])
    model.refresh_all(FROZEN_NOW)
    names = [call[0] for call in model.calls]
    assert names[0] == surface.WIRE_DONE
    assert surface.SETUP_START in names
    assert surface.REFRESH_START in names
    assert surface.BLOCKS_RETURN in names
    assert set(names) <= set(surface.CALL_NAMES), set(names) - set(surface.CALL_NAMES)
    moved = list(model.calls)
    moved[0], moved[1] = moved[1], moved[0]
    assert readable(moved) != readable(model.calls)


def test_the_bridge_writes_no_warning_for_this_tab():
    """A failed call was silent, or the handler could never see one."""
    from src.core import desktop_bridge

    seen: list = []

    class Catcher(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    logger = logging.getLogger("acervator.core.desktop_bridge")
    handler = Catcher()
    logger.addHandler(handler)
    try:
        registry = desktop_bridge.build_registry()
        desktop_bridge.handle_line(
            json.dumps({"id": 1, "method": surface.METHOD, "params": {"reset": True}}),
            registry,
        )
        quiet = list(seen)
        desktop_bridge.handle_line(
            json.dumps({"id": 2, "method": surface.METHOD, "params": {"state": 5}}),
            registry,
        )
        noisy = list(seen)
    finally:
        logger.removeHandler(handler)
    before_removal = len(seen)
    desktop_bridge.handle_line(
        json.dumps({"id": 3, "method": surface.METHOD, "params": {"state": 5}}),
        desktop_bridge.build_registry(),
    )
    assert quiet == []
    assert len(noisy) == 1
    assert "testnet_tab.state" in noisy[0]
    assert len(seen) == before_removal


def test_the_refresh_failure_trail_is_compared_as_values():
    """A refresh failure was silent on one side and named on the other."""
    model, broken = new_model(TAB_CASES["full"])
    broken.error = RuntimeError("chain gone")
    for _ in range(5):
        model.refresh_all(FROZEN_NOW)
    counts = [
        getattr(model, surface.REFRESH_FAIL_ATTRIBUTE.format(name=name), 0)
        for name in surface.REFRESH_NAMES
    ]
    assert counts == [surface.REFRESH_FAIL_LIMIT, 0, 0, 0], counts
    assert len(model.stderr_lines) == surface.REFRESH_FAIL_LIMIT
    assert len(model.log_records) == surface.REFRESH_FAIL_LIMIT
    assert model.stderr_lines[0].startswith("TestnetTab._refresh_stats: RuntimeError")
    app()
    with frozen_clock():
        tab = hold(
            shipped.TestnetTab(
                None,
                net_of(summary=stats()),
                None,
            )
        )
        tab._testnet.error = RuntimeError("chain gone")
        for _ in range(5):
            tab._refresh_all()
    assert tab._refresh_stats_fails == surface.REFRESH_FAIL_LIMIT
    assert getattr(tab, "_refresh_blocks_fails", 0) == 0


BLIND_TO_THE_PICTURE = {
    "accessible_name": "test_the_accessible_name_is_compared_as_a_string",
    "content_margins": "test_the_layout_numbers_are_compared_as_values",
    "content_spacing": "test_the_layout_numbers_are_compared_as_values",
    "header_resize_mode": "test_the_table_settings_are_compared_as_values",
    "vertical_header_visible": "test_the_table_settings_are_compared_as_values",
    "edit_triggers": "test_the_table_settings_are_compared_as_values",
    "selection_behavior": "test_the_table_settings_are_compared_as_values",
    "table_max_height": "test_the_table_settings_are_compared_as_values",
    "label_alignment": "test_the_label_alignment_is_compared_as_a_value",
    "frame_shape": "test_the_frame_and_splitter_numbers_are_compared_as_values",
    "splitter_handle": "test_the_frame_and_splitter_numbers_are_compared_as_values",
    "log_markup": "test_the_log_lines_are_compared_as_the_markup_the_tab_wrote",
    "spin_range": "test_the_spin_box_rewrites_a_value_outside_its_range",
    "recorded_calls": "test_the_recorded_calls_are_compared_as_values",
    "refusal_type": "test_the_refresh_outcomes_are_the_shipped_tabs",
    "timer_delay": "test_the_tab_starts_one_timer",
    "bus_topic": "test_the_tab_subscribes_to_no_bus_topic",
    "signal_wiring": "test_the_tab_wires_nine_signals",
    "button_enabled": "test_the_step_sequence_is_the_shipped_tabs",
    "comp_count": "test_the_step_sequence_is_the_shipped_tabs",
    "oracle_price": "test_the_step_sequence_is_the_shipped_tabs",
    "bridge_request": "test_the_step_sequence_is_the_shipped_tabs",
    "winner_ellipsis": "test_the_two_winner_lines_use_different_ellipses",
    "chain_reset_reason": "test_the_step_sequence_is_the_shipped_tabs",
    "refresh_failures": "test_the_refresh_failure_trail_is_compared_as_values",
    "bridge_warning": "test_the_bridge_writes_no_warning_for_this_tab",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 26
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


def freeze(value):
    """One value as a single comparable string."""

    def plain(found):
        if isinstance(found, (tuple, list)):
            return [plain(item) for item in found]
        if isinstance(found, dict):
            return {key: plain(item) for key, item in found.items()}
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
        if isinstance(value, surface.TestnetTabModel):
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
    for name in TAB_CASES:
        model, _ = new_model(TAB_CASES[name])
        model.refresh_all(FROZEN_NOW)
        payloads.append(surface.build_view_model(model))
    wired, _ = new_model(TAB_CASES["full"], surface.BridgeSnapshot())
    wired.run_competition()
    wired.stress_test()
    wired.reset_chain(True)
    wired.reset_chain(False)
    wired.on_bridge_competition(result())
    wired.on_bridge_competition({"error": "no"})
    wired.chain_reset_message("schema upgrade")
    wired.set_mock_price(surface.ORACLE_DEFAULT)
    payloads.append(surface.build_view_model(wired))
    plain, _ = new_model(TAB_CASES["full"])
    plain.run_competition(now=FROZEN_NOW)
    plain.stress_test(now=FROZEN_NOW)
    plain.reset_chain(True, FROZEN_NOW)
    payloads.append(surface.build_view_model(plain))
    broken, broken_net = new_model(TAB_CASES["full"])
    broken_net.error = RuntimeError("chain gone")
    broken.refresh_all(FROZEN_NOW)
    broken.run_competition(now=FROZEN_NOW)
    broken.stress_test(now=FROZEN_NOW)
    broken_net.error = None
    payloads.append(surface.build_view_model(broken))
    missing = surface.BridgeSnapshot()
    missing.SIGNALS = ("chain_updated",)
    refused = surface.TestnetTabModel(net_of(), missing)
    refused.setup_ui()
    refused.run_competition()
    payloads.append(surface.build_view_model(refused))
    payloads.append(surface.build_view_model(surface.build_model(None)))
    payloads.append(surface.build_view_model(surface.build_model({"bridge": True})))
    return payloads


COVERED_ELSEWHERE = {
    "CALL_NAMES": "test_the_recorded_calls_are_compared_as_values",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped tab."""
    constants = surface_constants()
    assert len(constants) > 130, len(constants)
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
    assert "TAB_TITLE" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "logger_name": ("LOGGER_NAME",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "widgets": ("model.setup_ui",),
    "widget_names": ("model.setup_ui",),
    "widget_kinds": ("model.setup_ui",),
    "widget_parents": ("model.setup_ui",),
    "widget_children": ("model.setup_ui",),
    "widget_index": ("model.setup_ui",),
    "tab_title": ("TAB_TITLE",),
    "net_label_text": ("NET_LABEL_TEXT",),
    "chain_id": ("CHAIN_ID",),
    "section_titles": ("SECTION_TITLES",),
    "colors": (
        "CYAN",
        "GREEN",
        "AMBER",
        "RED",
        "MAGENTA",
        "MUTED",
        "PANEL",
        "NO_COLOR",
    ),
    "tier_colors": ("TIER_COLORS",),
    "tier_fallback_color": ("TIER_FALLBACK_COLOR",),
    "event_colors": ("EVENT_COLORS",),
    "event_fallback_color": ("EVENT_FALLBACK_COLOR",),
    "styles": (
        "SECTION_STYLE",
        "TABLE_STYLE",
        "TITLE_STYLE",
        "SEPARATOR_STYLE",
        "SPIN_STYLE",
        "COMBO_STYLE",
        "PRICE_STYLE",
        "RUN_BUTTON_STYLE",
        "STRESS_BUTTON_STYLE",
        "RESET_BUTTON_STYLE",
        "LOG_STYLE",
        "LABEL_STYLE_FORMAT",
    ),
    "label_weights": ("LABEL_WEIGHT_BOLD", "LABEL_WEIGHT_NORMAL"),
    "label_defaults": (
        "LABEL_DEFAULT_COLOR",
        "LABEL_DEFAULT_SIZE",
        "LABEL_DEFAULT_BOLD",
    ),
    "stat_keys": ("STAT_KEYS",),
    "stat_source_keys": ("STAT_SOURCE_KEYS",),
    "stat_supply_keys": ("STAT_SUPPLY_KEYS",),
    "stat_placeholder": ("STAT_PLACEHOLDER",),
    "stat_sizes": ("STAT_KEY_SIZE", "STAT_VALUE_SIZE"),
    "stat_formats": ("STAT_COUNT_FORMAT", "STAT_SUPPLY_FORMAT"),
    "stat_values": ("model.stat_values",),
    "control_labels": ("BOTS_LABEL", "SYMBOL_LABEL", "SEASON_LABEL", "ORACLE_LABEL"),
    "bots": ("BOTS_MINIMUM", "BOTS_MAXIMUM", "BOTS_DEFAULT", "BOTS_WIDTH_PX"),
    "season": (
        "SEASON_MINIMUM",
        "SEASON_MAXIMUM",
        "SEASON_DEFAULT",
        "SEASON_WIDTH_PX",
    ),
    "symbols": ("SYMBOLS",),
    "symbol_default": ("SYMBOL_DEFAULT",),
    "symbol_width_px": ("SYMBOL_WIDTH_PX",),
    "oracle": (
        "ORACLE_MINIMUM",
        "ORACLE_MAXIMUM",
        "ORACLE_DEFAULT",
        "ORACLE_DECIMALS",
        "ORACLE_WIDTH_PX",
    ),
    "oracle_held": (
        "ORACLE_MINIMUM_VALUE",
        "ORACLE_MAXIMUM_VALUE",
        "ORACLE_DEFAULT_VALUE",
    ),
    "request_no_round": ("REQUEST_NO_ROUND",),
    "oracle_symbol": ("ORACLE_SYMBOL",),
    "button_texts": ("RUN_BUTTON_TEXT", "STRESS_BUTTON_TEXT", "RESET_BUTTON_TEXT"),
    "buttons_enabled": ("model.run_enabled", "model.stress_enabled"),
    "columns": ("BLOCK_COLUMNS", "TX_COLUMNS", "EVENT_COLUMNS", "HOLDER_COLUMNS"),
    "table_max_heights": (
        "BLOCK_TABLE_MAX_HEIGHT_PX",
        "TX_TABLE_MAX_HEIGHT_PX",
        "EVENT_TABLE_MAX_HEIGHT_PX",
        "HOLDER_TABLE_MAX_HEIGHT_PX",
        "TABLE_DEFAULT_MAX_HEIGHT_PX",
    ),
    "log_max_height_px": ("LOG_MAX_HEIGHT_PX",),
    "log_read_only": ("LOG_READ_ONLY",),
    "row_limits": (
        "BLOCK_ROW_LIMIT",
        "TX_ROW_LIMIT",
        "EVENT_ROW_LIMIT",
        "HOLDER_ROW_LIMIT",
        "EVENT_ARG_LIMIT",
    ),
    "hash_chars": (
        "BLOCK_HASH_CHARS",
        "TX_HASH_CHARS",
        "FROM_ADDR_CHARS",
        "WALLET_CHARS",
        "WINNER_CHARS",
        "ADJ_TX_CHARS",
    ),
    "hash_tail": ("HASH_TAIL",),
    "row_colors": ("BLOCK_ROW_COLORS", "TX_ROW_COLORS"),
    "formats": (
        "BLOCK_AGE_FORMAT",
        "GAS_FORMAT",
        "HOLDER_BALANCE_FORMAT",
        "EVENT_ARG_FORMAT",
        "EVENT_ARG_JOIN",
        "LOG_TIME_FORMAT",
        "LOG_LINE_FORMAT",
    ),
    "token_decimals": ("TOKEN_DECIMALS",),
    "no_tier_text": ("NO_TIER_TEXT",),
    "rows": (
        "model.block_rows",
        "model.tx_rows",
        "model.event_rows",
        "model.holder_rows",
    ),
    "log_lines": ("model.log_lines",),
    "actions": ("ACTIONS",),
    "bridge_signals": ("BRIDGE_SIGNALS",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "autostart_timers": ("AUTOSTART_TIMERS",),
    "refresh_interval_ms": ("REFRESH_INTERVAL_MS",),
    "refresh_names": ("REFRESH_NAMES",),
    "refresh_fail_limit": ("REFRESH_FAIL_LIMIT",),
    "refresh_fail_attribute": ("REFRESH_FAIL_ATTRIBUTE",),
    "refresh_stderr_format": ("REFRESH_STDERR_FORMAT",),
    "refresh_log_format": ("REFRESH_LOG_FORMAT",),
    "refresh_failures": ("model.refresh_failures",),
    "wiring_refusals": ("model.wiring_refusals",),
    "stderr_lines": ("model.stderr_lines",),
    "log_records": ("model.log_records",),
    "bus_topics": ("BUS_TOPICS",),
    "content_margins": ("CONTENT_MARGINS",),
    "content_spacing": ("CONTENT_SPACING",),
    "splitter": (
        "SPLITTER_HANDLE_WIDTH_PX",
        "SPLITTER_CHILDREN_COLLAPSIBLE",
        "SPLITTER_ORIENTATION",
        "SPLITTER_ORIENTATION_VALUE",
    ),
    "alignment": ("ALIGNMENT",),
    "alignment_value": ("ALIGNMENT_VALUE",),
    "label_default_alignment_value": ("LABEL_DEFAULT_ALIGNMENT_VALUE",),
    "separator_frame_shape": ("SEPARATOR_FRAME_SHAPE",),
    "separator_frame_shape_value": ("SEPARATOR_FRAME_SHAPE_VALUE",),
    "header_resize_mode": ("HEADER_RESIZE_MODE",),
    "header_resize_value": ("HEADER_RESIZE_VALUE",),
    "vertical_header_visible": ("VERTICAL_HEADER_VISIBLE",),
    "edit_triggers_none": ("EDIT_TRIGGERS_NONE",),
    "edit_triggers_none_value": ("EDIT_TRIGGERS_NONE_VALUE",),
    "edit_triggers_default_value": ("EDIT_TRIGGERS_DEFAULT_VALUE",),
    "selection_behavior_rows": ("SELECTION_BEHAVIOR_ROWS",),
    "selection_behavior_rows_value": ("SELECTION_BEHAVIOR_ROWS_VALUE",),
    "selection_behavior_default_value": ("SELECTION_BEHAVIOR_DEFAULT_VALUE",),
    "reset_dialog": ("RESET_DIALOG_TITLE", "RESET_DIALOG_TEXT"),
    "reset_messages": (
        "RESET_BRIDGE_REASON",
        "RESET_BRIDGE_MESSAGE",
        "RESET_STANDALONE_MESSAGE",
    ),
    "chain_reset_message": ("CHAIN_RESET_MESSAGE",),
    "chain_reset_color": ("CHAIN_RESET_COLOR",),
    "run_messages": (
        "RUN_STARTING_MESSAGE",
        "RUN_COMPLETE_MESSAGE",
        "RUN_WINNER_MESSAGE",
        "RUN_ADJ_MESSAGE",
        "RUN_ERROR_MESSAGE",
    ),
    "bridge_messages": (
        "BRIDGE_WINNER_MESSAGE",
        "BRIDGE_FAILED_MESSAGE",
        "BRIDGE_UNKNOWN_COMPETITION",
        "BRIDGE_UNKNOWN_TIER",
        "BRIDGE_NO_WINNER",
        "BRIDGE_NO_TOKENS",
    ),
    "stress_messages": (
        "STRESS_STARTING_MESSAGE",
        "STRESS_DONE_MESSAGE",
        "STRESS_TIER_MESSAGE",
        "STRESS_TIER_FORMAT",
        "STRESS_TIER_JOIN",
        "STRESS_ERROR_MESSAGE",
    ),
    "stress_counts": ("STRESS_COUNT", "STRESS_BOTS"),
    "result_keys": (
        "RESULT_COMPETITION_KEY",
        "RESULT_WINNER_KEY",
        "RESULT_TIER_KEY",
        "RESULT_TOKENS_KEY",
        "RESULT_ADJ_KEY",
    ),
    "error_key": ("ERROR_KEY",),
    "tier_counts_key": ("TIER_COUNTS_KEY",),
    "request_fields": ("REQUEST_FIELDS",),
    "empty_chain_stats": ("EMPTY_CHAIN_STATS",),
    "reset_attributes": ("RESET_ATTRIBUTES",),
    "skin": ("SKIN",),
    "tab_style_sheet": ("TAB_STYLE_SHEET",),
    "no_color": ("NO_COLOR",),
    "no_path": ("NO_PATH",),
    "run_paths": ("RUN_PATHS",),
    "stress_paths": ("STRESS_PATHS",),
    "reset_paths": ("RESET_PATHS",),
    "bridge_paths": ("BRIDGE_PATHS",),
    "wired_paths": ("WIRED_PATHS",),
    "call_names": ("CALL_NAMES",),
    "wired_path": ("model.wired_path",),
    "run_path": ("model.run_path",),
    "stress_path": ("model.stress_path",),
    "reset_path": ("model.reset_path",),
    "bridge_path": ("model.bridge_path",),
    "comp_count": ("model.comp_count",),
    "has_bridge": ("model.bridge",),
    "calls": ("model.calls",),
}


def resolve_source(name, model, held=None):
    """The value one named source holds, on the surface or on the model.

    ``held`` carries a value read before the model was driven again.
    Building the payload appends to the call list, so the list has to come
    from before the loop or it grows while it is being checked.
    """
    if held and name in held:
        return held[name]
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
        return found() if callable(found) else found
    return getattr(surface, name)


def backed(key, value, sources, model, held=None):
    """Whether one payload key carries exactly what its named sources hold."""
    if key == "has_bridge":
        return value is (resolve_source(sources[0], model, held) is not None)
    if key in (
        "widgets",
        "widget_names",
        "widget_kinds",
        "widget_parents",
        "widget_children",
        "widget_index",
    ):
        return bool(value)
    resolved = [resolve_source(name, model, held) for name in sources]
    if len(sources) == 1:
        return freeze(value) == freeze(resolved[0])
    if isinstance(value, dict):
        return sorted(freeze(item) for item in value.values()) == sorted(
            freeze(item) for item in resolved
        )
    return [freeze(item) for item in value] == [freeze(item) for item in resolved]


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model, _ = new_model(TAB_CASES["full"])
    model.refresh_all(FROZEN_NOW)
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    assert len(payload) == 118
    fresh, _ = new_model(TAB_CASES["full"])
    fresh.refresh_all(FROZEN_NOW)
    surface.build_view_model(fresh)
    held = {
        "model.calls": [list(call) for call in fresh.calls],
        "model.block_rows": [list(row) for row in fresh.block_rows],
        "model.tx_rows": [list(row) for row in fresh.tx_rows],
        "model.event_rows": [list(row) for row in fresh.event_rows],
        "model.holder_rows": [list(row) for row in fresh.holder_rows],
        "model.stat_values": dict(fresh.stat_values),
    }
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(fresh, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, fresh, held), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model, _ = new_model(TAB_CASES["full"])
    payload = surface.build_view_model(model)
    assert backed("alignment", payload["alignment"], ("ALIGNMENT",), model)
    assert not backed("alignment", "AlignLeft", ("ALIGNMENT",), model)
    assert not backed("symbols", ["BTC/USDT"], ("SYMBOLS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("comp_count", 9, ("model.comp_count",), model)


def test_both_completeness_checks_can_report():
    """Neither completeness check can report, so both pass by emptiness."""
    constants = surface_constants()
    assert len(missing_from_payload(constants, set())) > 100
    model, _ = new_model(TAB_CASES["full"])
    payload = surface.build_view_model(model)
    assert set(payload) - {"method"} != set(PAYLOAD_KEY_SOURCES)
    assert not backed("method", "another.method", ("METHOD",), model)


# ---------------------------------------------------------------------
# The shipped module keeps nothing between tabs
# ---------------------------------------------------------------------


def test_the_shipped_tab_changes_no_value_the_next_tab_reads():
    """One tab left a changed value behind for the next one."""
    before = {
        name: value
        for name, value in vars(shipped).items()
        if isinstance(value, (str, int, float, dict, tuple))
        and not name.startswith("__")
    }
    for name in TAB_CASES:
        old_refreshed(TAB_CASES[name])
    old_steps(SEQUENCES["everything"])
    after = {
        name: value
        for name, value in vars(shipped).items()
        if isinstance(value, (str, int, float, dict, tuple))
        and not name.startswith("__")
    }
    assert freeze(after) == freeze(before)
    assert shipped.TIER_COLORS == surface.TIER_COLORS
    moved = dict(before)
    moved["CYAN"] = "#000000"
    assert freeze(moved) != freeze(before)


def test_the_surface_keeps_nothing_between_models():
    """One model left a changed value behind for the next one."""
    first, _ = new_model(TAB_CASES["full"])
    first.refresh_all(FROZEN_NOW)
    first.msg("noise", surface.RED)
    second, _ = new_model(TAB_CASES["full"])
    assert second.log_lines == []
    assert second.comp_count == 0
    assert second.stat_values != {}
    third, _ = new_model(TAB_CASES["full"])
    third.refresh_all(FROZEN_NOW)
    assert digest(third.block_rows) == digest(first.block_rows)


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------

BRIDGE_STATE = {
    "chain": {
        "blocks": [dict(block())],
        "transactions": [dict(tx())],
        "events": [dict(event())],
        "block_number": 1,
    },
    "balances": {ADDRESS_ONE: 5 * 10**18},
    "mint_log": [{"recipient": ADDRESS_ONE, "tier": "Harvest"}],
    "stats": stats(),
    "result": result(),
}


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model, _ = new_model(TAB_CASES["full"])
    payload = surface.build_view_model(model)
    encoded = json.loads(json.dumps(payload))
    assert encoded["method"] == surface.METHOD
    assert encoded["widget_names"] == payload["widget_names"]
    assert len(encoded) == len(payload)


def test_bridge_registers_the_testnet_tab_method():
    """The renderer cannot reach this tab, because nothing registered it."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    frame = desktop_bridge.handle_line(
        json.dumps(
            {"id": 7, "method": surface.METHOD, "params": {"state": BRIDGE_STATE}}
        ),
        registry,
    )
    assert frame["ok"] is True
    found = frame["result"]
    assert found["method"] == surface.METHOD
    assert found["accessible_name"] == surface.ACCESSIBLE_NAME
    assert found["has_bridge"] is False
    assert len(found["widgets"]) == 53
    assert found["stat_values"]["Block"] == "3"
    assert "no_such_method.state" not in registry


def test_the_bridge_answers_an_empty_tab_and_keeps_it_until_a_reset():
    """The bridge builds a new tab on every call, or never builds one."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 1, "method": surface.METHOD, "params": params}), registry
        )["result"]

    call({"reset": True})
    empty = call({})
    assert empty["stat_values"]["Remaining"] == "10,000,000"
    seeded = call({"state": BRIDGE_STATE})
    assert seeded["stat_values"]["Block"] == "3"
    kept = call({})
    assert kept["stat_values"]["Block"] == "3"
    assert call({"reset": True})["stat_values"]["Block"] == "0"


def test_the_bridge_reports_a_state_it_cannot_read():
    """A request the surface cannot read is answered as if it were good."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    frame = desktop_bridge.handle_line(
        json.dumps({"id": 2, "method": surface.METHOD, "params": {"state": 5}}),
        registry,
    )
    assert frame["ok"] is False
    assert frame["error"]["type"] in ("AttributeError", "TypeError")
    good = desktop_bridge.handle_line(
        json.dumps({"id": 3, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )
    assert good["ok"] is True


def test_the_bridge_import_list_stays_alphabetical():
    """The bridge import list drifted out of order."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    block = re.search(r"from src\.gui\.main_tabs import \((.*?)\)", text, re.S).group(1)
    names = [line.strip().rstrip(",") for line in block.strip().split("\n")]
    assert names == sorted(names), names
    assert "testnet_tab_surface" in names
    assert len(names) == len(set(names))


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
    "json.dumps({'id': 1, 'method': 'testnet_tab.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import testnet_tab_surface as s\n"
    "state = %s\n"
    "model = s.build_model(state)\n"
    "model.refresh_all(%r)\n"
    "payload = s.build_view_model(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'widgets': len(payload['widgets']),\n"
    "    'stat_values': payload['stat_values'],\n"
    "    'blocks': payload['rows']['blocks'],\n"
    "    'transactions': payload['rows']['transactions'],\n"
    "    'events': payload['rows']['events'],\n"
    "    'holders': payload['rows']['holders'],\n"
    "    'calls': len(payload['calls'])}))\n"
) % (json.dumps(BRIDGE_STATE), FROZEN_NOW)


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
    """Reaching the testnet tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    found = answered["frame"]["result"]
    assert found["method"] == "testnet_tab.state"
    assert found["accessible_name"] == "Testnet Tab"
    assert found["columns"]["blocks"] == ["Block", "Txs", "Hash", "Age"]
    assert found["content_margins"] == [10, 8, 10, 8]
    assert len(found["widgets"]) == 53


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_paints_the_tab_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["widgets"] == 53
    assert answered["stat_values"]["Block"] == "3"
    assert answered["stat_values"]["ACRV Minted"] == "500,000"
    assert answered["stat_values"]["Remaining"] == "9,500,000"
    assert [found["text"] for found in answered["blocks"][0]] == [
        "1",
        "2",
        BLOCK_HASH[:18] + "...",
        "3600s ago",
    ]
    assert answered["blocks"][0][0]["color"] == surface.CYAN
    assert [found["text"] for found in answered["transactions"][0]] == [
        TX_HASH[:14] + "...",
        "adjudicate",
        ADDRESS_ONE[:10] + "...",
        "50,000",
    ]
    assert [found["text"] for found in answered["events"][0]] == [
        "1",
        "Adjudicated",
        "a=1  b=2  c=3",
    ]
    assert [found["text"] for found in answered["holders"][0]] == [
        ADDRESS_ONE[:14] + "...",
        "5.0",
        "Harvest",
    ]
    assert answered["calls"] > 10


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_paints_the_tab():
    """The Qt block let the shipped tab through."""
    probe = BLOCK_QT + (
        "import json\n"
        "from src.gui import testnet_tab\n"
        "print(json.dumps({'has_qt': testnet_tab._QT,\n"
        "    'stub': testnet_tab.TestnetTab().__class__.__name__}))\n"
    )
    answered = run_script(probe)
    assert answered["has_qt"] is False
    assert answered["stub"] == "TestnetTab"


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {"__future__", "time", "typing", "color_alpha"}
    tab_tree = ast.parse(TAB_PATH.read_text(encoding="utf-8"))
    tab_imports = {
        (node.module or "")
        for node in ast.walk(tab_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in tab_imports), tab_imports


def test_the_surface_opens_no_file_and_no_socket():
    """The surface reached for a file, a network address or a key."""
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
        "socket",
        "generate",
        "home",
    ):
        assert forbidden not in reached, forbidden
    text = SURFACE_PATH.read_text(encoding="utf-8")
    for forbidden in ("http://", "https://", "wss://", ".acervator"):
        assert forbidden not in text, forbidden
    assert surface.CHAIN_ID == 84532
    assert str(surface.CHAIN_ID) in surface.NET_LABEL_TEXT


# ---------------------------------------------------------------------
# Where the alpha byte turns into the share CSS reads
# ---------------------------------------------------------------------


def alpha_fields(text):
    """The fourth field of every ``rgba`` call one style value carries."""
    return [
        part.split(")")[0].split(",")[3].strip()
        for part in str(text).split("rgba(")[1:]
        if len(part.split(")")[0].split(",")) == 4
    ]


def byte_alphas(text):
    """Every alpha in one style value that counts in bytes, as CSS cannot."""
    return [one for one in alpha_fields(text) if float(one) > 1]


def test_the_alpha_reader_names_a_byte_and_passes_a_share():
    """Without this the measurement below is a reader that sees nothing."""
    assert byte_alphas("background:rgba(0,255,238,38);") == ["38"]
    assert byte_alphas("background:rgba(0,255,238,0.15);") == []
    assert alpha_fields("border:1px solid #00FFEE;") == []


def test_no_style_this_tab_publishes_counts_its_alpha_in_bytes():
    """A byte reaching CSS paints opaque, and no error says so."""
    written = []
    for name, sheet in surface.build_view_model()["styles"].items():
        written += [(name, one) for one in byte_alphas(sheet)]
    assert not written, written


def test_the_bridge_answer_turns_a_byte_into_a_share_the_plain_build_keeps(
    monkeypatch,
):
    """The two sides of the boundary answer differently for one value."""
    monkeypatch.setattr(surface, "SECTION_STYLE", "background:rgba(0,255,238,38);")
    kept = surface.build_view_model()["styles"]["section"]
    published = surface.view_model({"reset": True})["styles"]["section"]
    assert byte_alphas(kept) == ["38"], kept
    assert byte_alphas(published) == [], published
    assert alpha_fields(published) == [repr(38 / 255)], published


def test_a_share_crosses_the_boundary_unchanged(monkeypatch):
    """The positive control: the boundary rewrites a byte and nothing else."""
    monkeypatch.setattr(surface, "SECTION_STYLE", "background:rgba(0,255,238,0.15);")
    published = surface.view_model({"reset": True})["styles"]["section"]
    assert published == surface.build_view_model()["styles"]["section"]
    assert alpha_fields(published) == ["0.15"]


# ---------------------------------------------------------------------
# The poll the renderer asks for, which the shipped tab runs on a timer
# ---------------------------------------------------------------------


def test_a_bridge_call_asking_for_a_refresh_fills_all_four_tables():
    """The renderer could never draw a block, because nothing refreshed."""
    filled = surface.view_model(
        {"reset": True, "state": BRIDGE_STATE, "refresh": True, "now": FROZEN_NOW}
    )["rows"]
    assert sorted(filled) == ["blocks", "events", "holders", "transactions"]
    for name, rows in filled.items():
        assert rows, name
    assert filled["blocks"][0][0]["text"] == "1"
    assert filled["holders"][0][2]["text"] == "Harvest"


def test_a_bridge_call_without_that_ask_leaves_the_four_tables_empty():
    """The positive control: the fill above comes from the ask, not the state."""
    empty = surface.view_model({"reset": True, "state": BRIDGE_STATE})["rows"]
    assert sorted(empty) == ["blocks", "events", "holders", "transactions"]
    for name, rows in empty.items():
        assert rows == [], name
