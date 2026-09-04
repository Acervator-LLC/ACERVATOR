"""The shipped Proof of Accumulation tab and the Qt-free surface, side by side.

A failure means the view model carries a different label, a different
table row, a different colour, a different widget tree, a different
recorded call or a different path than ``CompetitionTab``.

No test here reads or writes the operator's runtime tree, opens a socket
or generates a key. Every identity, ledger and rating value below is
invented and lives in a throwaway directory.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import competition_tab as shipped
from src.gui.main_tabs import competition_tab_surface as surface
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

TAB_PATH = REPO_ROOT / "src/gui/competition_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/competition_tab_surface.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"

PIXEL_SIZE = (900, 700)

# The counts the shipped tab carries, each measured off the file by the
# same counter that is pointed at a neighbour which really has one.
TAB_CONNECT_SITES = 0
TAB_TIMER_BUILDS = 0
TAB_BUS_SITES = 0
TAB_ELEMENT_BUILDS = 29
CONTROL_CONNECT_SITES = 1
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_ELEMENT_BUILDS = 3

# Invented values. None of these is a real key, a real wallet or a real
# node. The relay address is text the tab prints and nothing dials.
BOT_KEY = "aa11bb22cc33dd44ee55ff66aa77bb88cc99dd00ee11ff22aa33bb44cc55dd66"
OTHER_KEY = "ff00ee11dd22cc33bb44aa55ff66ee77dd88cc99bb00aa11ff22ee33dd44cc55"
SHORT_KEY = "abc"
PRIVATE_KEY_B64 = base64.b64encode(bytes(32)).decode()

STAMP_ONE = 1_700_000_000.0
STAMP_TWO = 1_700_086_400.0
BILLION_STAMP = 1_000_000_000.0

UNICODE_TEXT = "Δ_fold→⚡"
MARKUP_TEXT = "<b>tier</b>"
NEWLINE_TEXT = "two\nlines"
APOSTROPHE_TEXT = "Ekthelius' Fold"
LONG_TEXT = "x" * 200
WRONG_CAPITALS_TIER = "harvest"

TODAY_MARK = "<the day this ran>"
UNSEEDED_KEY_MARK = "<a key this test did not seed>"
DATE_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY_SHAPE = re.compile(r"^[0-9a-f]{64}$")
SEEDED_VALUES = frozenset({BOT_KEY, OTHER_KEY})

WIDGETS_HELD: list = []
WORKSPACES: list = []


@pytest.fixture(scope="module", autouse=True)
def _clear_workspaces():
    """Remove every throwaway directory this file wrote."""
    yield
    for path in WORKSPACES:
        shutil.rmtree(path, ignore_errors=True)


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


# Invented inputs, and the stand-ins both sides are driven with


def award(**over):
    """One award's values, with the happy award as the base."""
    base = {
        "tier_name": "Harvest",
        "tier_emoji": "H",
        "amount": 10,
        "competition_id": "comp-1",
        "timestamp": STAMP_ONE,
    }
    base.update(over)
    return base


def rating(**over):
    """One leaderboard row, as the rating registry hands it over."""
    base = {
        "rank": 1,
        "bot_id": BOT_KEY[:12] + "...",
        "rating": 1300,
        "w": 3,
        "l": 1,
        "win_rate": "75%",
    }
    base.update(over)
    return base


def summary(minted=60, remaining=9_999_940, holders=1):
    """One global supply summary, as the token ledger hands it over."""
    return {
        "total_minted": minted,
        "remaining": remaining,
        "total_holders": holders,
    }


def ledger_of(bot_id, balance=60, awards=(), supply=None):
    """One ledger stand-in both sides are driven with."""
    return surface.LedgerSnapshot(
        balances={bot_id: balance},
        awards={bot_id: surface.build_awards(awards)},
        summary=summary() if supply is None else supply,
    )


def identity_of(bot_id):
    """One identity stand-in both sides are driven with."""
    return surface.IdentitySnapshot(bot_id)


AWARD_CASES: dict = {
    "happy": [award(tier_name="Gold Fold", tier_emoji="G", amount=50), award()],
    "empty": [],
    "zero_amount": [award(amount=0)],
    "negative_amount": [award(amount=-5)],
    "thousand_million": [award(amount=1_000_000_000)],
    "one_billionth": [award(amount=1e-9)],
    "whole_number": [award(amount=12)],
    "decimal_number": [award(amount=12.0)],
    "infinite_amount": [award(amount=float("inf"))],
    "minus_infinite_amount": [award(amount=float("-inf"))],
    "not_a_number_amount": [award(amount=float("nan"))],
    "unicode": [award(tier_name=UNICODE_TEXT, competition_id=UNICODE_TEXT)],
    "markup": [award(tier_name=MARKUP_TEXT, competition_id=MARKUP_TEXT)],
    "newline": [award(tier_name=NEWLINE_TEXT, competition_id=NEWLINE_TEXT)],
    "apostrophe": [award(tier_name=APOSTROPHE_TEXT, competition_id=APOSTROPHE_TEXT)],
    "long": [award(tier_name=LONG_TEXT, competition_id=LONG_TEXT)],
    "wrong_capitals": [award(tier_name=WRONG_CAPITALS_TIER)],
    "every_tier": [award(tier_name=name) for name in surface.TIER_COLORS],
    "number_where_text_belongs": [award(competition_id=5)],
    "billion_stamp": [award(timestamp=BILLION_STAMP)],
    "zero_stamp": [award(timestamp=0)],
    "over_the_cap": [award(competition_id=f"comp-{index}") for index in range(9)],
    "text_where_a_number_belongs": [award(amount="many")],
    "no_amount_at_all": [award(amount=None)],
    "negative_stamp": [award(timestamp=-5)],
    "infinite_stamp": [award(timestamp=float("inf"))],
    "minus_infinite_stamp": [award(timestamp=float("-inf"))],
    "not_a_number_stamp": [award(timestamp=float("nan"))],
    "text_stamp": [award(timestamp="noon")],
    "no_stamp_at_all": [award(timestamp=None)],
}

SUPPLY_CASES: dict = {
    "happy": (summary(), 1),
    "zero": (summary(0, 10_000_000, 0), 1),
    "negative": (summary(-5, -5, -5), 1),
    "thousand_million": (summary(1_000_000_000, 1_000_000_000, 1_000_000_000), 1),
    "one_billionth": (summary(1e-9, 1e-9, 1e-9), 1),
    "whole_number": (summary(12, 12, 12), 1),
    "decimal_number": (summary(12.0, 12.0, 12.0), 1),
    "infinite": (summary(float("inf"), float("-inf"), float("nan")), 1),
    "unicode_holders": (summary(60, 9_999_940, UNICODE_TEXT), 1),
    "second_season": (summary(), 2),
    "fiftieth_season": (summary(), 50),
    "hundredth_season": (summary(), 100),
    "season_zero": (summary(), 0),
    "season_negative": (summary(), -1),
    "season_decimal": (summary(), 2.0),
    "season_true": (summary(), True),
    "season_infinite": (summary(), float("inf")),
    "season_minus_infinite": (summary(), float("-inf")),
    "season_not_a_number": (summary(), float("nan")),
    "season_is_text": (summary(), "one"),
    "season_is_missing": (summary(), None),
    "minted_is_text": (summary("many", 1, 1), 1),
    "no_minted_key": ({"remaining": 1, "total_holders": 1}, 1),
    "no_remaining_key": ({"total_minted": 1, "total_holders": 1}, 1),
    "no_holders_key": ({"total_minted": 1, "remaining": 1}, 1),
    "no_keys_at_all": ({}, 1),
}

SUPPLY_REFUSING = (
    "season_zero",
    "season_negative",
    "season_minus_infinite",
    "season_not_a_number",
    "season_is_text",
    "season_is_missing",
    "minted_is_text",
    "no_minted_key",
    "no_remaining_key",
    "no_holders_key",
    "no_keys_at_all",
)

IDENTITY_CASES: dict = {
    "held": BOT_KEY,
    "other": OTHER_KEY,
    "short": SHORT_KEY,
    "empty_key": "",
    "unicode_key": UNICODE_TEXT,
    "long_key": LONG_TEXT,
    "markup_key": MARKUP_TEXT,
    "newline_key": NEWLINE_TEXT,
    "apostrophe_key": APOSTROPHE_TEXT,
    "no_identity": None,
    "number_where_text_belongs": 12,
}

IDENTITY_REFUSING = ("number_where_text_belongs",)

LEADERBOARD_CASES: dict = {
    "happy": [rating()],
    "empty": [],
    "two": [
        rating(),
        rating(
            rank=2, bot_id=OTHER_KEY[:12] + "...", rating=1200, w=1, l=3, win_rate="25%"
        ),
    ],
    "ten": [rating(rank=index + 1, rating=1300 - index) for index in range(10)],
    "zero_rating": [rating(rating=0, w=0, l=0, win_rate="0%")],
    "negative_rating": [rating(rating=-100, w=-1, l=-1)],
    "thousand_million": [rating(rating=1_000_000_000)],
    "one_billionth": [rating(rating=1e-9)],
    "whole_number": [rating(rating=12)],
    "decimal_number": [rating(rating=12.0)],
    "infinite": [rating(rating=float("inf"))],
    "minus_infinite": [rating(rating=float("-inf"))],
    "not_a_number": [rating(rating=float("nan"))],
    "unicode": [rating(bot_id=UNICODE_TEXT, win_rate=UNICODE_TEXT)],
    "markup": [rating(bot_id=MARKUP_TEXT, win_rate=MARKUP_TEXT)],
    "newline": [rating(bot_id=NEWLINE_TEXT, win_rate=NEWLINE_TEXT)],
    "apostrophe": [rating(bot_id=APOSTROPHE_TEXT, win_rate=APOSTROPHE_TEXT)],
    "long": [rating(bot_id=LONG_TEXT, win_rate=LONG_TEXT)],
    "wrong_capitals": [rating(bot_id="AA11BB22CC33...")],
    "number_where_text_belongs": [rating(bot_id=7, win_rate=9)],
    "no_rank_key": [{"bot_id": "x", "rating": 1, "w": 1, "l": 1, "win_rate": "5%"}],
    "no_win_rate_key": [{"rank": 1, "bot_id": "x", "rating": 1, "w": 1, "l": 1}],
}

LEADERBOARD_REFUSING = ("no_rank_key", "no_win_rate_key")

# A cell built from a number prints nothing on the widget side and
# carries the number on the surface side. The pair is read apart
# rather than compared as equal.
CELL_KEPT_BY_ONE_SIDE = ("number_where_text_belongs",)


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


def masked(value):
    """One value with anything the platform chose replaced by a marker.

    A key this test did not seed was made by the machine, and a date
    equal to today came off the machine's clock. Both are hidden so the
    comparison reads the product. A seeded key and a seeded date are
    kept.
    """
    if isinstance(value, str):
        if KEY_SHAPE.match(value) and value not in SEEDED_VALUES:
            return UNSEEDED_KEY_MARK
        if DATE_SHAPE.match(value) and value == time.strftime("%Y-%m-%d"):
            return TODAY_MARK
        return value
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
        run()
        return {"error": "", "headline": ""}
    except Exception as exc:
        return {"error": type(exc).__name__, "headline": str(exc).splitlines()[:1]}


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
            colour = "" if brush.style() == Qt.NoBrush else QColor(brush.color()).name()
            cells.append(
                {
                    "text": item.text(),
                    "color": colour,
                    "alignment": (
                        surface.ALIGNMENT
                        if int(item.textAlignment()) == 132
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


def hold(widget):
    """Keep one widget alive so no later read reaches a collected object."""
    WIDGETS_HELD.append(widget)
    return widget


# The four panels, driven on both sides from one stand-in


def old_identity_panel(bot_id):
    """Drive the shipped Bot Identity panel over one key."""
    app()
    identity = None if bot_id is None else identity_of(bot_id)
    panel = hold(shipped._IdentityPanel(identity))
    row = layout_entries(panel.inner())[0]
    return {
        "labels": [[found.text(), found.styleSheet()] for found in layout_entries(row)],
        "title": panel.title(),
        "accessible": panel.accessibleName(),
    }


def new_identity_panel(bot_id):
    """Drive the surface's Bot Identity panel over the same key."""
    identity = None if bot_id is None else identity_of(bot_id)
    panel = surface.CompetitionTabModel(identity=identity).identity_panel()
    if panel["held"]:
        labels = [
            [panel["short_text"], panel["short_style"]],
            [panel["full_text"], panel["full_style"]],
        ]
    else:
        labels = [[panel["empty_text"], surface.EMPTY_STYLE]]
    return {
        "labels": labels,
        "title": surface.IDENTITY_SECTION_TITLE.upper(),
        "accessible": surface.SECTION_ACCESSIBLE_NAME,
    }


def old_wallet_panel(name):
    """Drive the shipped ACRV Wallet panel over one award list."""
    from PySide6.QtWidgets import QTableWidget

    app()
    awards = AWARD_CASES[name]
    panel = hold(shipped._WalletPanel(ledger_of(BOT_KEY, 60, awards), BOT_KEY))
    entries = layout_entries(panel.inner())
    body = entries[1]
    if isinstance(body, QTableWidget):
        found = {
            "rows": canon_cells(read_table(body)),
            "columns": [
                body.horizontalHeaderItem(index).text()
                for index in range(body.columnCount())
            ],
            "column_count": body.columnCount(),
            "max_height": body.maximumHeight(),
            "vertical_header_visible": body.verticalHeader().isVisible(),
            "edit_triggers_value": int(body.editTriggers().value),
            "empty_text": None,
        }
    else:
        found = {
            "rows": [],
            "columns": [],
            "column_count": 0,
            "max_height": None,
            "vertical_header_visible": None,
            "edit_triggers_value": None,
            "empty_text": body.text(),
        }
    found["balance_text"] = entries[0].text()
    found["balance_style"] = entries[0].styleSheet()
    return found


def new_wallet_panel(name):
    """Drive the surface's ACRV Wallet panel over the same award list."""
    awards = AWARD_CASES[name]
    model = surface.CompetitionTabModel(
        identity=identity_of(BOT_KEY), ledger=ledger_of(BOT_KEY, 60, awards)
    )
    panel = model.wallet_panel()
    if panel["rows"]:
        found = {
            "rows": canon_cells(panel["rows"]),
            "columns": list(surface.AWARD_COLUMNS),
            "column_count": surface.AWARD_COLUMN_COUNT,
            "max_height": panel["max_height"],
            "vertical_header_visible": surface.VERTICAL_HEADER_VISIBLE,
            "edit_triggers_value": surface.EDIT_TRIGGERS_NONE_VALUE,
            "empty_text": None,
        }
    else:
        found = {
            "rows": [],
            "columns": [],
            "column_count": 0,
            "max_height": None,
            "vertical_header_visible": None,
            "edit_triggers_value": None,
            "empty_text": panel["empty_text"],
        }
    found["balance_text"] = panel["balance_text"]
    found["balance_style"] = panel["balance_style"]
    return found


def old_supply_panel(name):
    """Drive the shipped Global Supply panel over one summary and season."""
    app()
    supply, season = SUPPLY_CASES[name]
    panel = hold(shipped._SupplyPanel(ledger_of(BOT_KEY, 0, (), supply), season))
    row = layout_entries(panel.inner())[0]
    columns = []
    for column in layout_entries(row):
        label, value = layout_entries(column)
        columns.append(
            {
                "label_text": label.text(),
                "label_style": label.styleSheet(),
                "label_alignment": int(label.alignment()),
                "value_text": value.text(),
                "value_style": value.styleSheet(),
                "value_alignment": int(value.alignment()),
            }
        )
    return {"columns": columns}


def new_supply_panel(name):
    """Drive the surface's Global Supply panel over the same values."""
    supply, season = SUPPLY_CASES[name]
    model = surface.CompetitionTabModel(
        ledger=ledger_of(BOT_KEY, 0, (), supply), season=season
    )
    return {
        "columns": [
            {
                "label_text": column["label_text"],
                "label_style": column["label_style"],
                "label_alignment": surface.ALIGNMENT_VALUE,
                "value_text": column["value_text"],
                "value_style": column["value_style"],
                "value_alignment": surface.ALIGNMENT_VALUE,
            }
            for column in model.supply_panel()
        ]
    }


def old_leaderboard_panel(name):
    """Drive the shipped Elo Leaderboard panel over one ranked list."""
    from PySide6.QtWidgets import QTableWidget

    app()
    panel = hold(
        shipped._LeaderboardPanel(surface.RegistrySnapshot(LEADERBOARD_CASES[name]))
    )
    body = layout_entries(panel.inner())[0]
    if isinstance(body, QTableWidget):
        return {
            "rows": canon_cells(read_table(body)),
            "columns": [
                body.horizontalHeaderItem(index).text()
                for index in range(body.columnCount())
            ],
            "column_count": body.columnCount(),
            "vertical_header_visible": body.verticalHeader().isVisible(),
            "edit_triggers_value": int(body.editTriggers().value),
            "empty_text": None,
        }
    return {
        "rows": [],
        "columns": [],
        "column_count": 0,
        "vertical_header_visible": None,
        "edit_triggers_value": None,
        "empty_text": body.text(),
    }


def new_leaderboard_panel(name):
    """Drive the surface's Elo Leaderboard panel over the same list."""
    model = surface.CompetitionTabModel(
        registry=surface.RegistrySnapshot(LEADERBOARD_CASES[name])
    )
    panel = model.leaderboard_panel()
    if panel["rows"]:
        return {
            "rows": canon_cells(panel["rows"]),
            "columns": list(surface.LEADERBOARD_COLUMNS),
            "column_count": surface.LEADERBOARD_COLUMN_COUNT,
            "vertical_header_visible": surface.VERTICAL_HEADER_VISIBLE,
            "edit_triggers_value": surface.EDIT_TRIGGERS_NONE_VALUE,
            "empty_text": None,
        }
    return {
        "rows": [],
        "columns": [],
        "column_count": 0,
        "vertical_header_visible": None,
        "edit_triggers_value": None,
        "empty_text": panel["empty_text"],
    }


def drive(old, new, name):
    """Run one case through both sides and hand back the two answers."""
    old_outcome = {}
    new_outcome = {}
    old_state: dict = {}
    new_state: dict = {}

    def run_old():
        old_state.update(old(name))

    def run_new():
        new_state.update(new(name))

    old_outcome = guarded(run_old)
    new_outcome = guarded(run_new)
    return (
        {"outcome": old_outcome, "state": old_state},
        {"outcome": new_outcome, "state": new_state},
    )


# Side by side, value for value and by hash


@pytest.mark.parametrize("name", sorted(IDENTITY_CASES))
def test_the_identity_panel_is_the_shipped_panels(name):
    """The surface painted a different Bot Identity panel."""
    old, new = drive(
        lambda case: old_identity_panel(IDENTITY_CASES[case]),
        lambda case: new_identity_panel(IDENTITY_CASES[case]),
        name,
    )
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(set(AWARD_CASES) - set(CELL_KEPT_BY_ONE_SIDE)))
def test_the_wallet_panel_is_the_shipped_panels(name):
    """The surface painted a different ACRV Wallet panel."""
    old, new = drive(old_wallet_panel, new_wallet_panel, name)
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(SUPPLY_CASES))
def test_the_supply_panel_is_the_shipped_panels(name):
    """The surface painted a different Global Supply panel."""
    old, new = drive(old_supply_panel, new_supply_panel, name)
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize(
    "name", sorted(set(LEADERBOARD_CASES) - set(CELL_KEPT_BY_ONE_SIDE))
)
def test_the_leaderboard_panel_is_the_shipped_panels(name):
    """The surface painted a different Elo Leaderboard panel."""
    old, new = drive(old_leaderboard_panel, new_leaderboard_panel, name)
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name


def test_a_number_where_text_belongs_is_kept_by_one_side_only():
    """A non-text cell value stopped being reported the way each side reports it.

    A table cell built from a number takes the item-type argument, so the
    cell prints nothing and carries the number as its type. The surface
    carries the number itself. Both answers are read here rather than
    assumed equal.
    """
    from PySide6.QtWidgets import QTableWidget

    app()
    panel = hold(
        shipped._WalletPanel(
            ledger_of(BOT_KEY, 60, AWARD_CASES["number_where_text_belongs"]), BOT_KEY
        )
    )
    table = layout_entries(panel.inner())[1]
    assert isinstance(table, QTableWidget)
    assert table.item(0, 2).text() == ""
    assert table.item(0, 2).type() == 5
    assert table.item(0, 0).text() == "H Harvest"
    assert new_wallet_panel("number_where_text_belongs")["rows"][0][2]["text"] == 5
    board = hold(
        shipped._LeaderboardPanel(
            surface.RegistrySnapshot(LEADERBOARD_CASES["number_where_text_belongs"])
        )
    )
    cells = layout_entries(board.inner())[0]
    assert cells.item(0, 1).text() == ""
    assert cells.item(0, 1).type() == 7
    assert cells.item(0, 0).text() == "1"
    assert new_leaderboard_panel("number_where_text_belongs")["rows"][0][1]["text"] == 7


def test_the_sample_hashes_are_reported():
    """Two sides agreed by both carrying nothing at all."""
    samples = {}
    for name in ("happy", "empty", "unicode", "every_tier", "long"):
        old, new = drive(old_wallet_panel, new_wallet_panel, name)
        samples[name] = (digest(old), digest(new))
        assert samples[name][0] == samples[name][1], name
    assert len({pair[0] for pair in samples.values()}) == 5, samples
    again, _ = drive(old_wallet_panel, new_wallet_panel, "happy")
    assert digest(again) == samples["happy"][0]
    moved = json.loads(json.dumps(readable(again), default=str))
    moved["state"]["balance_text"] = "1 ACRV"
    assert digest(moved) != digest(again)


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash reports one value for every input, so it proves nothing."""
    happy_old, happy_new = drive(old_wallet_panel, new_wallet_panel, "happy")
    empty_old, empty_new = drive(old_wallet_panel, new_wallet_panel, "empty")
    assert digest(happy_old) != digest(empty_new)
    assert digest(empty_old) != digest(happy_new)
    assert digest(happy_old) == digest(happy_new)
    assert digest(empty_old) == digest(empty_new)


def test_a_whole_number_and_a_decimal_are_told_apart():
    """The comparison folded 12 and 12.0 into one value."""
    whole_old, whole_new = drive(old_wallet_panel, new_wallet_panel, "whole_number")
    decimal_old, decimal_new = drive(
        old_wallet_panel, new_wallet_panel, "decimal_number"
    )
    assert digest(whole_old) == digest(whole_new)
    assert digest(decimal_old) == digest(decimal_new)
    assert digest(whole_old) != digest(decimal_old)
    assert whole_old["state"]["rows"][0][1]["text"] == "12"
    assert decimal_old["state"]["rows"][0][1]["text"] == "12.0"
    assert numbered(12) != numbered(12.0)
    assert numbered(12) == ["int", "12"]
    assert numbered(12.0) == ["float", "12.0"]


def test_two_not_a_numbers_built_apart_compare_equal():
    """A not-a-number compared to itself reported a difference that is not one."""
    first = float("nan")
    second = float("nan")
    assert first is not second
    assert first != second
    assert math.isnan(first) and math.isnan(second)
    assert numbered(first) == numbered(second)
    assert numbered(first) != numbered(0.0)
    old, new = drive(old_wallet_panel, new_wallet_panel, "not_a_number_amount")
    assert readable(new) == readable(old)
    assert old["state"]["rows"][0][1]["text"] == "nan"


def test_the_masking_rule_keeps_a_seeded_value_and_hides_a_chosen_one():
    """The mask hid a value this test seeded, or kept one the machine chose."""
    today = time.strftime("%Y-%m-%d")
    assert masked(BOT_KEY) == BOT_KEY
    assert masked(OTHER_KEY) == OTHER_KEY
    assert masked("f" * 64) == UNSEEDED_KEY_MARK
    assert masked(today) == TODAY_MARK
    assert masked("2023-11-14") == "2023-11-14"
    assert masked({"a": [today, BOT_KEY]}) == {"a": [TODAY_MARK, BOT_KEY]}
    assert masked("not a key") == "not a key"
    old, new = drive(old_wallet_panel, new_wallet_panel, "no_stamp_at_all")
    assert old["state"]["rows"][0][3]["text"] == today
    assert readable(old)["state"]["rows"][0][3]["text"] == TODAY_MARK
    assert readable(new) == readable(old)


# What each side did with an input it would not take


def outcomes(old, new, cases):
    """What each side did with every case: answered, or refused and how."""
    found = {}
    for name in cases:
        old_side, new_side = drive(old, new, name)
        found[name] = (old_side["outcome"], new_side["outcome"])
    return found


def test_the_supply_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    found = outcomes(old_supply_panel, new_supply_panel, SUPPLY_CASES)
    refused = {name for name, pair in found.items() if pair[0]["error"]}
    answered = set(found) - refused
    assert refused == set(SUPPLY_REFUSING), sorted(refused)
    assert len(answered) >= 15, sorted(answered)
    for name, (old_side, new_side) in found.items():
        assert new_side == old_side, (name, old_side, new_side)
    assert found["season_zero"][0]["error"] == "ValueError"
    assert found["no_minted_key"][0]["error"] == "KeyError"
    assert found["minted_is_text"][0]["error"] == "ValueError"
    assert found["happy"][0]["error"] == ""


def test_the_wallet_outcomes_hold_both_an_answer_and_a_refusal():
    """Every award case answered, so the refusal comparison proves nothing."""
    found = outcomes(old_wallet_panel, new_wallet_panel, AWARD_CASES)
    refused = {name for name, pair in found.items() if pair[0]["error"]}
    answered = set(found) - refused
    assert refused, "no award case refused"
    assert len(answered) >= 15, sorted(answered)
    for name, (old_side, new_side) in found.items():
        assert new_side == old_side, (name, old_side, new_side)
    assert found["text_where_a_number_belongs"][0]["error"] == "ValueError"
    assert found["no_amount_at_all"][0]["error"] == "TypeError"
    assert found["infinite_stamp"][0]["error"] == "OverflowError"
    assert found["not_a_number_stamp"][0]["error"] == "ValueError"
    assert found["text_stamp"][0]["error"] == "TypeError"
    assert found["happy"][0]["error"] == ""


def test_the_identity_and_leaderboard_outcomes_hold_both_answers():
    """A refusal on one side went unnoticed on the other."""
    identity = outcomes(
        lambda case: old_identity_panel(IDENTITY_CASES[case]),
        lambda case: new_identity_panel(IDENTITY_CASES[case]),
        IDENTITY_CASES,
    )
    assert {name for name, pair in identity.items() if pair[0]["error"]} == set(
        IDENTITY_REFUSING
    )
    assert identity["number_where_text_belongs"][0]["error"] == "TypeError"
    board = outcomes(old_leaderboard_panel, new_leaderboard_panel, LEADERBOARD_CASES)
    assert {name for name, pair in board.items() if pair[0]["error"]} == set(
        LEADERBOARD_REFUSING
    )
    assert board["no_rank_key"][0]["error"] == "KeyError"
    for found in (identity, board):
        for name, (old_side, new_side) in found.items():
            assert new_side == old_side, (name, old_side, new_side)


def test_the_refusal_comparison_reports_two_different_wordings():
    """The refusal check passes whatever the two sides said."""
    one = guarded(lambda: surface.season_budget(0))
    two = guarded(lambda: surface.season_budget(-9))
    assert one["error"] == two["error"] == "ValueError"
    assert one != two
    assert one["headline"] != two["headline"]
    assert one["headline"] == ["Season must be ≥ 1, got 0"]
    answered = guarded(lambda: surface.season_budget(1))
    assert answered == {"error": "", "headline": ""}
    assert answered != one


def test_the_refusal_wording_is_read_off_the_shipped_side():
    """The two sides refuse a low season with different words."""
    from src.competition import season_reward

    for season in (0, -1, -1000):
        old_side = guarded(lambda value=season: season_reward(value))
        new_side = guarded(lambda value=season: surface.season_budget(value))
        assert old_side == new_side, season
        assert old_side["error"] == "ValueError", season
    assert season_reward(1) == surface.season_budget(1) == 500_000
    assert season_reward(2) == surface.season_budget(2) == 425_000
    assert season_reward(100) == surface.season_budget(100) == 100


# The paths every case reaches


def test_every_wallet_and_leaderboard_case_reaches_the_path_it_names():
    """A case stopped reaching the path it stands for."""
    reached = {}
    for name, awards in AWARD_CASES.items():
        model = surface.CompetitionTabModel(
            identity=identity_of(BOT_KEY), ledger=ledger_of(BOT_KEY, 60, awards)
        )
        guarded(model.wallet_panel)
        reached[name] = model.wallet_path
    assert reached["happy"] == surface.WALLET_PATH_AWARDS
    assert reached["empty"] == surface.WALLET_PATH_EMPTY
    assert set(reached.values()) <= set(surface.WALLET_PATHS) | {surface.NO_PATH}
    assert set(surface.WALLET_PATHS) <= set(reached.values())
    ranked = {}
    for name, rows in LEADERBOARD_CASES.items():
        model = surface.CompetitionTabModel(registry=surface.RegistrySnapshot(rows))
        guarded(model.leaderboard_panel)
        ranked[name] = model.leaderboard_path
    assert ranked["happy"] == surface.LEADERBOARD_PATH_RANKED
    assert ranked["empty"] == surface.LEADERBOARD_PATH_EMPTY
    assert set(surface.LEADERBOARD_PATHS) <= set(ranked.values())


def test_the_identity_and_balance_paths_are_both_reached():
    """A load or a balance path stopped being reachable."""
    model = surface.CompetitionTabModel(identity=identity_of(BOT_KEY))
    assert model.load_identity() is model.identity
    assert model.identity_path == surface.IDENTITY_PATH_LOADED
    refusing = surface.IdentitySnapshot(BOT_KEY, error=RuntimeError("no key"))
    model = surface.CompetitionTabModel(identity=refusing)
    assert model.load_identity() is None
    assert model.identity_path == surface.IDENTITY_PATH_REFUSED
    assert model.identity is None
    assert set(surface.IDENTITY_PATHS) == {"loaded", "refused"}
    held = surface.CompetitionTabModel(
        identity=identity_of(BOT_KEY), ledger=ledger_of(BOT_KEY, 60)
    )
    assert held.get_wallet_balance() == 60
    assert held.balance_path == surface.BALANCE_PATH_HELD
    lonely = surface.CompetitionTabModel(ledger=ledger_of(BOT_KEY, 60))
    assert lonely.get_wallet_balance() == 0
    assert lonely.balance_path == surface.BALANCE_PATH_NO_IDENTITY
    assert set(surface.BALANCE_PATHS) == {"held", "no_identity"}


# The whole tab, built from real files in a throwaway directory


def workspace(bot_id=BOT_KEY, awards=(), elo=(), broken=()):
    """One throwaway directory holding the three files the tab reads."""
    path = Path(tempfile.mkdtemp(prefix="acervator-competition-"))
    WORKSPACES.append(str(path))
    if bot_id is not None:
        (path / "bot_identity.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "bot_id": bot_id,
                    "created_at": STAMP_ONE,
                    "pubkey_hex": bot_id,
                    "privkey_b64": PRIVATE_KEY_B64,
                }
            ),
            encoding="utf-8",
        )
    events = [
        {
            "event_id": f"event-{index}",
            "bot_id": bot_id,
            "competition_id": item["competition_id"],
            "season": 1,
            "tier_name": item["tier_name"],
            "tier_emoji": item["tier_emoji"],
            "amount": item["amount"],
            "timestamp": item["timestamp"],
            "competition_root": "root",
            "rank_pct": 0.4,
        }
        for index, item in enumerate(awards)
    ]
    (path / "acrv_ledger.json").write_text(
        json.dumps({"version": 1, "total_cap": 10_000_000, "events": events}),
        encoding="utf-8",
    )
    (path / "elo_registry.json").write_text(
        json.dumps(
            {
                "ratings": {
                    row["bot_id"]: {
                        "bot_id": row["bot_id"],
                        "rating": row["rating"],
                        "wins": row["wins"],
                        "losses": row["losses"],
                        "last_competed": 0.0,
                        "consecutive_top1": 0,
                    }
                    for row in elo
                },
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    for name in broken:
        (path / name).write_text("{not json", encoding="utf-8")
    return path


# Every case writes an identity file, valid or unreadable, so the tab
# always loads a key rather than making one. No test here generates a
# key or writes one to disk.
BROKEN_IDENTITY = ("bot_identity.json",)

TAB_CASES: dict = {
    "full": {
        "bot_id": BOT_KEY,
        "awards": [
            award(
                tier_name="Gold Fold", tier_emoji="G", amount=50, timestamp=STAMP_TWO
            ),
            award(),
        ],
        "elo": [{"bot_id": BOT_KEY, "rating": 1300, "wins": 3, "losses": 1}],
    },
    "bare": {
        "bot_id": BOT_KEY,
        "awards": [],
        "elo": [],
        "broken": BROKEN_IDENTITY,
    },
    "identity_only": {"bot_id": BOT_KEY, "awards": [], "elo": []},
    "board_only": {
        "bot_id": BOT_KEY,
        "awards": [],
        "elo": [
            {"bot_id": BOT_KEY, "rating": 1300, "wins": 3, "losses": 1},
            {"bot_id": OTHER_KEY, "rating": 1200, "wins": 1, "losses": 3},
        ],
        "broken": BROKEN_IDENTITY,
    },
    "identity_and_board": {
        "bot_id": BOT_KEY,
        "awards": [],
        "elo": [{"bot_id": BOT_KEY, "rating": 1300, "wins": 3, "losses": 1}],
    },
}


def tab_workspace(name):
    """One throwaway directory for one whole-tab case."""
    case = TAB_CASES[name]
    return workspace(
        bot_id=case["bot_id"],
        awards=case["awards"],
        elo=case["elo"],
        broken=case.get("broken", ()),
    )


def qt_kind(found):
    """The Qt class one object is, whatever Python class it wears."""
    if isinstance(found, str):
        return found
    for owner in type(found).__mro__:
        if owner.__name__.startswith("Q"):
            return owner.__name__
    return type(found).__name__


BASE_NAMES = (
    "tab",
    "header_row",
    "title",
    "header_stretch",
    "subtitle",
    "separator",
    "scroll",
    "container",
)
NETWORK_NAMES = (
    "network_section",
    "status_row",
    "status_dot",
    "status_label",
    "status_stretch",
    "network_info",
    "url_row",
    "url_label",
    "relay_field",
    "connect_button",
)


def expected_names(has_identity, has_awards, has_board):
    """The node names the tab builds, in build order, for one shape."""
    names = list(BASE_NAMES)
    names += ["identity_section", "identity_row"]
    names += ["identity_short", "identity_full"] if has_identity else ["identity_empty"]
    names += ["panels_row", "wallet_section", "balance_label"]
    names += ["awards_table"] if has_awards else ["awards_empty"]
    names += ["supply_section", "supply_row"]
    for index in range(5):
        names += [
            f"supply_column_{index}",
            f"supply_label_{index}",
            f"supply_value_{index}",
        ]
    names += ["leaderboard_section"]
    names += ["leaderboard_table"] if has_board else ["leaderboard_empty"]
    names += list(NETWORK_NAMES)
    names += ["inner_stretch"]
    return names


LABEL_KEYS = ("text", "style_sheet")
SECTION_KEYS = (
    "title",
    "accessible_name",
    "style_sheet",
    "layout",
    "margins",
    "spacing",
)
TABLE_KEYS = (
    "columns",
    "column_count",
    "row_count",
    "resize_mode_value",
    "vertical_header_visible",
    "edit_triggers_value",
)

NODE_KEYS: dict = {
    "tab": ("accessible_name", "layout", "margins", "spacing", "style_sheet"),
    "header_row": (),
    "title": LABEL_KEYS,
    "header_stretch": (),
    "subtitle": LABEL_KEYS,
    "separator": ("frame_shape_value", "style_sheet"),
    "scroll": ("resizable", "frame_shape_value"),
    "container": ("layout", "spacing"),
    "identity_section": SECTION_KEYS,
    "identity_row": (),
    "identity_short": LABEL_KEYS,
    "identity_full": LABEL_KEYS,
    "identity_empty": LABEL_KEYS,
    "panels_row": (),
    "wallet_section": SECTION_KEYS,
    "balance_label": LABEL_KEYS,
    "awards_table": TABLE_KEYS + ("max_height",),
    "awards_empty": LABEL_KEYS,
    "supply_section": SECTION_KEYS,
    "supply_row": (),
    "leaderboard_section": SECTION_KEYS,
    "leaderboard_table": TABLE_KEYS,
    "leaderboard_empty": LABEL_KEYS,
    "network_section": SECTION_KEYS,
    "status_row": (),
    "status_dot": LABEL_KEYS,
    "status_label": LABEL_KEYS,
    "status_stretch": (),
    "network_info": LABEL_KEYS + ("word_wrap",),
    "url_row": (),
    "url_label": LABEL_KEYS,
    "relay_field": LABEL_KEYS + ("enabled",),
    "connect_button": LABEL_KEYS + ("enabled",),
    "inner_stretch": (),
}
for _index in range(5):
    NODE_KEYS[f"supply_column_{_index}"] = ()
    NODE_KEYS[f"supply_label_{_index}"] = LABEL_KEYS + ("alignment_value",)
    NODE_KEYS[f"supply_value_{_index}"] = LABEL_KEYS + ("alignment_value",)


def widget_value(found, key):
    """One declared value, read off a real widget."""
    from PySide6.QtWidgets import QHeaderView

    if key == "text":
        return found.text()
    if key == "style_sheet":
        return found.styleSheet()
    if key == "accessible_name":
        return found.accessibleName()
    if key == "title":
        return found.title()
    if key == "layout":
        return type(found.layout()).__name__
    if key == "margins":
        margins = found.layout().contentsMargins()
        return [margins.left(), margins.top(), margins.right(), margins.bottom()]
    if key == "spacing":
        return found.layout().spacing()
    if key == "frame_shape_value":
        return int(found.frameShape().value)
    if key == "resizable":
        return found.widgetResizable()
    if key == "alignment_value":
        return int(found.alignment())
    if key == "word_wrap":
        return found.wordWrap()
    if key == "enabled":
        return found.isEnabled()
    if key == "columns":
        return [
            found.horizontalHeaderItem(index).text()
            for index in range(found.columnCount())
        ]
    if key == "column_count":
        return found.columnCount()
    if key == "row_count":
        return found.rowCount()
    if key == "resize_mode_value":
        return int(found.horizontalHeader().sectionResizeMode(0).value)
    if key == "vertical_header_visible":
        return found.verticalHeader().isVisible()
    if key == "edit_triggers_value":
        return int(found.editTriggers().value)
    if key == "max_height":
        return found.maximumHeight()
    assert QHeaderView is not None
    raise AssertionError(f"no reader for {key!r}")


def old_tree(tab, names):
    """The shipped tab's widget tree, walked in build order."""
    from PySide6.QtWidgets import QScrollArea

    nodes: list = []

    def visit(found, parent):
        position = len(nodes)
        name = names[position]
        nodes.append(
            {
                "name": name,
                "kind": qt_kind(found),
                "parent": parent,
                "values": {key: widget_value(found, key) for key in NODE_KEYS[name]},
            }
        )
        if isinstance(found, str):
            return
        if isinstance(found, QScrollArea):
            visit(found.widget(), position)
            return
        inner = found.layout() if hasattr(found, "layout") else found
        if inner is None:
            return
        if hasattr(inner, "count"):
            for entry in layout_entries(inner):
                visit(entry, position)

    visit(tab, -1)
    return nodes


def new_tree(nodes, names):
    """The surface's widget tree in the same positional shape."""
    place = {node["name"]: index for index, node in enumerate(nodes)}
    return [
        {
            "name": node["name"],
            "kind": node["kind"] if node["kind"] != "stretch" else "stretch",
            "parent": place.get(node["parent"], -1),
            "values": {key: node[key] for key in NODE_KEYS[names[index]]},
        }
        for index, node in enumerate(nodes)
    ]


def kind_for_layout(node):
    """The Qt class a layout or stretch node stands for."""
    return node["kind"]


def old_tab(name):
    """One real CompetitionTab, held so no read reaches a collected widget.

    The identity file is read before and after, so a run that generated
    a key rather than loading one is reported.
    """
    app()
    path = tab_workspace(name)
    before = (path / "bot_identity.json").read_bytes()
    tab = hold(shipped.CompetitionTab(data_dir=str(path)))
    assert (path / "bot_identity.json").read_bytes() == before, name
    return tab


def new_model(name):
    """The surface model for one whole-tab case, built from the same values."""
    case = TAB_CASES[name]
    held = case["bot_id"] is not None and "bot_identity.json" not in case.get(
        "broken", ()
    )
    bot_id = case["bot_id"] if held else ""
    awards = sorted(case["awards"], key=lambda item: item["timestamp"], reverse=True)
    minted = sum(item["amount"] for item in case["awards"])
    board = sorted(case["elo"], key=lambda row: row["rating"], reverse=True)
    rows = [
        {
            "rank": index + 1,
            "bot_id": row["bot_id"][:12] + "...",
            "rating": row["rating"],
            "w": row["wins"],
            "l": row["losses"],
            "win_rate": f"{row['wins'] / max(1, row['wins'] + row['losses']):.0%}",
        }
        for index, row in enumerate(board)
    ]
    return surface.CompetitionTabModel(
        identity=identity_of(bot_id) if held else None,
        ledger=surface.LedgerSnapshot(
            balances={bot_id: minted},
            awards={bot_id: surface.build_awards(awards if held else ())},
            summary=summary(
                minted,
                10_000_000 - minted,
                1 if case["awards"] else 0,
            ),
        ),
        registry=surface.RegistrySnapshot(rows),
        season=1,
        data_dir="competition_data",
    )


def tab_shape(name):
    """Whether one whole-tab case shows an identity, awards and a board."""
    model = new_model(name)
    return (
        model.identity is not None,
        bool(model.ledger.awards(model.bot_id())),
        bool(model.registry.leaderboard(surface.LEADERBOARD_TOP_N)),
    )


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_case_inputs_are_what_the_real_ledger_and_registry_produce(name):
    """The case table states values the real ledger and registry do not."""
    from src.competition import RatingRegistry, TokenLedger

    path = tab_workspace(name)
    ledger = TokenLedger(str(path / "acrv_ledger.json")).load()
    registry = RatingRegistry(str(path / "elo_registry.json")).load()
    model = new_model(name)
    bot_id = model.bot_id()
    assert (
        ledger.supply_summary()["total_minted"]
        == model.ledger.supply_summary()["total_minted"]
    ), name
    assert (
        ledger.supply_summary()["remaining"]
        == model.ledger.supply_summary()["remaining"]
    ), name
    assert (
        ledger.supply_summary()["total_holders"]
        == model.ledger.supply_summary()["total_holders"]
    ), name
    assert [item.competition_id for item in ledger.awards(bot_id)] == [
        item.competition_id for item in model.ledger.awards(bot_id)
    ], name
    assert registry.leaderboard(
        surface.LEADERBOARD_TOP_N
    ) == model.registry.leaderboard(surface.LEADERBOARD_TOP_N), name


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_whole_tab_tree_is_the_shipped_tabs(name):
    """A widget appeared on one side, moved parent, or changed a value."""
    names = expected_names(*tab_shape(name))
    tab = old_tab(name)
    model = new_model(name)
    old = old_tree(tab, names)
    new = new_tree(model.setup_ui(), names)
    assert [node["name"] for node in new] == names, name
    assert readable(new) == readable(old), name
    assert digest(new) == digest(old), name
    assert len(old) == len(names), name


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_whole_tab_cells_and_balance_are_the_shipped_tabs(name):
    """A table cell or the wallet balance drifted between the two sides."""
    from PySide6.QtWidgets import QTableWidget

    tab = old_tab(name)
    model = new_model(name)
    tables = tab.findChildren(QTableWidget)
    old_rows = [canon_cells(read_table(found)) for found in tables]
    new_rows = [
        canon_cells(rows)
        for rows in (
            model.wallet_panel()["rows"],
            model.leaderboard_panel()["rows"],
        )
        if rows
    ]
    assert readable(new_rows) == readable(old_rows), name
    assert tab.get_wallet_balance() == model.get_wallet_balance(), name


def test_the_tree_comparison_reports_a_swap_of_two_nodes():
    """The tree check passes whatever order the two sides built in."""
    names = expected_names(*tab_shape("full"))
    model = new_model("full")
    built = new_tree(model.setup_ui(), names)
    swapped = list(built)
    swapped[2], swapped[4] = swapped[4], swapped[2]
    assert swapped != built
    assert digest(swapped) != digest(built)
    assert built[2]["values"]["text"] == surface.TAB_TITLE
    assert swapped[2]["values"]["text"] == surface.TAB_SUBTITLE


def test_the_tab_is_built_where_the_operator_pointed_it():
    """The tab wrote its files somewhere other than the directory it was given."""
    path = tab_workspace("full")
    tab = hold(shipped.CompetitionTab(data_dir=str(path)))
    assert tab._data_dir == path
    assert sorted(found.name for found in path.iterdir()) == [
        "acrv_ledger.json",
        "bot_identity.json",
        "elo_registry.json",
    ]
    assert surface.CompetitionTabModel().data_dir == surface.DATA_DIR_DEFAULT
    assert surface.DATA_DIR_DEFAULT == "competition_data"
    assert [surface.IDENTITY_FILE, surface.LEDGER_FILE, surface.REGISTRY_FILE] == [
        "bot_identity.json",
        "acrv_ledger.json",
        "elo_registry.json",
    ]


def test_the_tab_refuses_a_broken_ledger_and_a_broken_registry():
    """A file the tab cannot read stopped stopping the tab."""
    app()
    for broken in ("acrv_ledger.json", "elo_registry.json"):
        path = workspace(bot_id=BOT_KEY, broken=(broken,))
        outcome = guarded(
            lambda where=path: shipped.CompetitionTab(data_dir=str(where))
        )
        assert outcome["error"] == "JSONDecodeError", broken
    good = workspace(bot_id=BOT_KEY)
    assert (
        guarded(lambda: hold(shipped.CompetitionTab(data_dir=str(good))))["error"] == ""
    )


def test_a_broken_identity_file_leaves_the_tab_without_one():
    """The tab stopped surviving an identity file it cannot read."""
    app()
    path = workspace(bot_id=BOT_KEY, broken=("bot_identity.json",))
    tab = hold(shipped.CompetitionTab(data_dir=str(path)))
    assert tab._identity is None
    assert tab.get_wallet_balance() == 0
    model = surface.CompetitionTabModel(
        identity=surface.IdentitySnapshot(BOT_KEY, error=ValueError("bad file"))
    )
    assert model.load_identity() is None
    assert model.get_wallet_balance() == 0
    assert model.identity_path == surface.IDENTITY_PATH_REFUSED


def test_the_tab_delegates_its_key_to_the_identity_object():
    """The tab stopped asking the identity object for the key.

    A stand-in replaces the identity class for the length of this test,
    so no key is generated and no key file is written.
    """
    app()
    path = workspace(bot_id=None)
    (path / "bot_identity.json").unlink(missing_ok=True)
    asked: list = []

    class Recorder:
        def __init__(self, key_path):
            asked.append(key_path)

        def generate(self):
            return identity_of(BOT_KEY)

    original = shipped.BotIdentity
    shipped.BotIdentity = Recorder
    try:
        tab = hold(shipped.CompetitionTab(data_dir=str(path)))
    finally:
        shipped.BotIdentity = original
    assert shipped.BotIdentity is original
    assert asked == [str(path / "bot_identity.json")]
    assert tab._identity is not None
    assert tab._identity.bot_id == BOT_KEY
    assert not (path / "bot_identity.json").exists()


def test_the_step_sequence_is_the_shipped_tabs():
    """A sequence of steps left the two sides in different states."""
    tab = old_tab("full")
    model = new_model("full")
    old_steps = [tab.get_wallet_balance(), tab.get_wallet_balance()]
    tab._identity = None
    old_steps.append(tab.get_wallet_balance())
    new_steps = [model.get_wallet_balance(), model.get_wallet_balance()]
    model.load_identity(surface.IdentitySnapshot(BOT_KEY, error=RuntimeError("gone")))
    new_steps.append(model.get_wallet_balance())
    assert new_steps == old_steps
    assert old_steps == [60, 60, 0]
    assert [call[0] for call in model.calls] == [
        "balance.start",
        "balance.return",
        "balance.start",
        "balance.return",
        "load.start",
        "load.return",
        "balance.start",
        "balance.return",
    ]
    assert model.calls[-1] == ["balance.return", "no_identity", 0]
    assert model.balance_path == surface.BALANCE_PATH_NO_IDENTITY


def test_the_recorded_calls_are_compared_as_values():
    """The ordered call list reached no pixel and was never compared."""
    model = new_model("full")
    model.setup_ui()
    assert [call[0] for call in model.calls] == [
        "setup.start",
        "identity.start",
        "identity.return",
        "setup.identity",
        "wallet.start",
        "wallet.return",
        "setup.wallet",
        "supply.start",
        "supply.return",
        "setup.supply",
        "leaderboard.start",
        "leaderboard.return",
        "setup.leaderboard",
        "setup.network",
        "setup.return",
    ]
    assert model.calls[-1] == ["setup.return", 46]
    bare = new_model("bare")
    bare.setup_ui()
    assert bare.calls[-1] == ["setup.return", 45]
    assert [call[0] for call in bare.calls] == [call[0] for call in model.calls]


# The surface writes its own values


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so a broken value moves both sides."""
    app()
    original = shipped.CYAN
    try:
        shipped.CYAN = "#123456"
        assert surface.CYAN == "#00FFEE"
        assert surface.TITLE_STYLE.count("#00FFEE") == 1
        moved = hold(shipped.CompetitionTab(data_dir=str(tab_workspace("full"))))
        names = expected_names(*tab_shape("full"))
        old = old_tree(moved, names)
        new = new_tree(new_model("full").setup_ui(), names)
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
        "identity_section",
        "wallet_section",
        "supply_section",
        "supply_value_0",
        "supply_value_1",
        "supply_value_2",
        "supply_value_3",
        "supply_value_4",
        "leaderboard_section",
        "network_section",
    ], differing
    assert old[2]["values"]["style_sheet"].count("#123456") == 1
    assert new[2]["values"]["style_sheet"].count("#00FFEE") == 1
    restored = old_tree(
        hold(shipped.CompetitionTab(data_dir=str(tab_workspace("full")))), names
    )
    assert readable(restored) == readable(new)


# Counting what the shipped file wires, waits on, and builds

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


def count_text(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, names):
    """How many times one file constructs any of `names`."""
    text = path.read_text(encoding="utf-8")
    return sum(len(re.findall(r"\b%s\s*\(" % name, text)) for name in names)


def declared_widget_classes(path):
    """Every class one file declares that ends up being a screen element.

    A class whose base is a widget is one, and so is a class whose base
    is another such class, however many steps away.
    """
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
    """How many screen elements one file builds, its own classes included.

    A class whose base is a widget is itself one element on the screen,
    so the count is the widgets constructed inside the file plus the
    widget classes the file declares.
    """
    return count_built(path, WIDGET_NAMES_BUILT) + len(declared_widget_classes(path))


def test_the_tab_wires_no_signal():
    """A signal wiring appeared on one side and not the other."""
    assert count_text(TAB_PATH, ".connect(") == TAB_CONNECT_SITES == 0
    assert count_text(SURFACE_PATH, ".connect(") == 0
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES == 1
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == count_text(TAB_PATH, ".connect(")


def test_the_tab_starts_no_timer():
    """A wait appeared on one side and not the other."""
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(TAB_PATH, timer_names) == TAB_TIMER_BUILDS == 0
    assert count_built(SURFACE_PATH, timer_names) == 0
    assert count_built(TIMER_CONTROL_PATH, timer_names) == CONTROL_TIMER_BUILDS == 1
    assert count_text(TIMER_CONTROL_PATH, "QTimer") > CONTROL_TIMER_BUILDS
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
        for name in ("full", "bare"):
            old_tab(name)
            new_model(name).setup_ui()
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()


def test_the_tab_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(TAB_PATH, ".subscribe(") == TAB_BUS_SITES == 0
    assert count_text(SURFACE_PATH, ".subscribe(") == 0
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_text(TAB_PATH, ".subscribe(")


def test_the_screen_elements_the_tab_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(TAB_PATH) == TAB_ELEMENT_BUILDS == 29
    assert (
        count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    ), count_elements(ELEMENT_CONTROL_PATH)
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert declared_widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert declared_widget_classes(TAB_PATH) == {
        "_Section",
        "_IdentityPanel",
        "_WalletPanel",
        "_SupplyPanel",
        "_LeaderboardPanel",
        "CompetitionTab",
    }
    assert count_built(TAB_PATH, WIDGET_NAMES_BUILT) == 23
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == set()
    names = expected_names(*tab_shape("full"))
    built = new_tree(new_model("full").setup_ui(), names)
    painted = [
        node["name"]
        for node in built
        if node["kind"] not in ("stretch", "QHBoxLayout", "QVBoxLayout")
    ]
    assert len(painted) == 32, painted
    assert len(built) == 46
    assert len(built) - len(painted) == 14


# Every class and every method has a counterpart


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A signal is callable and is not a method, so it is excluded by name.
    A factory and a read-only value are not callable at all, so asking
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
    from src.competition.bot_identity import BotIdentity
    from src.competition.token_ledger import AwardRecord
    from src.gui import launcher

    assert callable(Signal())
    assert "clicked" in vars(launcher.ModeCard)
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert not callable(vars(AwardRecord)["from_dict"])
    assert "from_dict" in members(AwardRecord)
    assert "verify_trade" in members(BotIdentity)
    assert not callable(vars(BotIdentity)["short_id"])
    assert "short_id" in members(BotIdentity)
    assert "short_id" in members(surface.IdentitySnapshot)


CLASS_MAP = {
    "_Section": "section_node",
    "_IdentityPanel": "CompetitionTabModel.identity_panel",
    "_WalletPanel": "CompetitionTabModel.wallet_panel",
    "_SupplyPanel": "CompetitionTabModel.supply_panel",
    "_LeaderboardPanel": "CompetitionTabModel.leaderboard_panel",
    "CompetitionTab": "CompetitionTabModel",
}

METHOD_MAP = {
    "_Section.__init__": "section_node",
    "_Section.inner": "widget_children",
    "_IdentityPanel.__init__": "CompetitionTabModel.identity_panel",
    "_WalletPanel.__init__": "CompetitionTabModel.wallet_panel",
    "_SupplyPanel.__init__": "CompetitionTabModel.supply_panel",
    "_LeaderboardPanel.__init__": "CompetitionTabModel.leaderboard_panel",
    "CompetitionTab.__init__": "CompetitionTabModel.__init__",
    "CompetitionTab._load_identity": "CompetitionTabModel.load_identity",
    "CompetitionTab._setup_ui": "CompetitionTabModel.setup_ui",
    "CompetitionTab.get_wallet_balance": "CompetitionTabModel.get_wallet_balance",
}

HELPER_MAP = {
    "tier_lookup": "tier_color",
    "balance_line": "balance_text",
    "award_day": "award_date",
    "identity_line": "identity_text",
    "identity_tail": "identity_tail_text",
    "table_cell": "cell",
    "widget_node": "widget",
    "section_panel": "section_node",
    "table_height": "award_table_height",
    "season_pool": "season_budget",
    "children_of": "widget_children",
    "place_of": "widget_index",
    "awards_from_values": "build_awards",
    "model_from_values": "build_model",
    "payload": "build_view_model",
    "bridge_handler": "view_model",
}

MODEL_MEMBERS = {
    "__init__",
    "bot_id",
    "load_identity",
    "identity_panel",
    "wallet_panel",
    "_award_row",
    "supply_panel",
    "leaderboard_panel",
    "_leaderboard_row",
    "get_wallet_balance",
    "setup_ui",
    "_identity_nodes",
    "_wallet_nodes",
    "_supply_nodes",
    "_leaderboard_nodes",
    "_network_nodes",
}

SURFACE_ONLY_CLASSES = (
    "AwardSnapshot",
    "IdentitySnapshot",
    "LedgerSnapshot",
    "RegistrySnapshot",
)


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
    assert shipped_classes() == set(CLASS_MAP)
    assert len(CLASS_MAP) == 6
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found[f"{name}.{member}"] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 10
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 16
    assert members(surface.CompetitionTabModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 16
    for name in SURFACE_ONLY_CLASSES:
        assert callable(getattr(surface, name)), name


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "get_wallet_balance" in members(shipped.CompetitionTab)
    assert "_setup_ui" in members(shipped.CompetitionTab)
    assert "inner" in members(shipped._Section)
    assert "CompetitionTab" not in MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("CompetitionTabModel.no_such_member")
    assert MODEL_MEMBERS - {"setup_ui"} != MODEL_MEMBERS
    assert members(surface.CompetitionTabModel) - {"wallet_panel"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"CompetitionTab.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"CompetitionTab"} != shipped_classes()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    tab_init = list(inspect.signature(shipped.CompetitionTab.__init__).parameters)
    assert tab_init == ["self", "parent", "data_dir"]
    model_init = list(
        inspect.signature(surface.CompetitionTabModel.__init__).parameters
    )
    assert model_init == [
        "self",
        "identity",
        "ledger",
        "registry",
        "season",
        "data_dir",
    ]
    assert (
        inspect.signature(shipped.CompetitionTab.__init__)
        .parameters["data_dir"]
        .default
        == "competition_data"
    )
    assert (
        inspect.signature(surface.CompetitionTabModel.__init__)
        .parameters["data_dir"]
        .default
        == surface.DATA_DIR_DEFAULT
    )
    assert list(
        inspect.signature(shipped.CompetitionTab.get_wallet_balance).parameters
    ) == list(
        inspect.signature(surface.CompetitionTabModel.get_wallet_balance).parameters
    )
    assert list(inspect.signature(shipped._SupplyPanel.__init__).parameters) == [
        "self",
        "ledger",
        "season",
        "parent",
    ]
    assert (
        inspect.signature(shipped._SupplyPanel.__init__).parameters["season"].default
        == surface.DEFAULT_SEASON
    )


def modules_importing(module, skip=()):
    """Every file under src that imports the module named exactly `module`.

    The name is matched whole. ``competition_tab_surface`` is a
    different module from ``competition_tab``, and a match on part of a
    name would count one as the other.
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


def files_naming(needle, skip=()):
    """Every file under src whose text names `needle`."""
    return [
        str(path)
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if path not in skip and needle in path.read_text(encoding="utf-8")
    ]


def test_the_tab_is_reached_by_no_other_module():
    """The tab is wired into a window, so the count of readers is wrong.

    The conversion itself names the tab, so the new surface and the tab
    are left out of the count; a count that keeps them reads the
    conversion as a reader.
    """
    readers = modules_importing("competition_tab", skip=(SURFACE_PATH, TAB_PATH))
    assert readers == [], readers
    known = modules_importing("design_system")
    assert len(known) > 5, known
    assert str(SURFACE_PATH) not in known
    assert modules_importing("competition_tab_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    assert files_naming("src.gui.competition_tab", skip=(SURFACE_PATH, TAB_PATH)) == []
    assert files_naming("src.gui.competition_tab") == [str(SURFACE_PATH)]


# The tab paints, and the two sides paint the same pixels


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    return sealed(surface.build_view_model(new_model(name)))


def fill_table(table, node, rows):
    """One table built from the payload alone, filled from one case's rows."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    table.setColumnCount(node["column_count"])
    table.setRowCount(node["row_count"])
    table.setHorizontalHeaderLabels(node["columns"])
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode(node["resize_mode_value"])
    )
    table.verticalHeader().setVisible(node["vertical_header_visible"])
    table.setEditTriggers(QTableWidget.EditTrigger(node["edit_triggers_value"]))
    if "max_height" in node:
        table.setMaximumHeight(node["max_height"])
    for row_index, row in enumerate(rows):
        for column, found in enumerate(row):
            item = QTableWidgetItem(found["text"])
            item.setTextAlignment(Qt.AlignmentFlag(132))
            if found["color"]:
                item.setForeground(QColor(found["color"]))
            table.setItem(row_index, column, item)


def tab_painted_by_the_model(payload):
    """One tab built only from the surface's view model."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QTableWidget,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    nodes = {node["name"]: node for node in payload["widgets"]}
    tab = hold(QWidget())
    tab.setAccessibleName(nodes["tab"]["accessible_name"])
    root = QVBoxLayout(tab)
    root.setContentsMargins(*nodes["tab"]["margins"])
    root.setSpacing(nodes["tab"]["spacing"])

    def label(name):
        node = nodes[name]
        found = QLabel(node["text"])
        found.setStyleSheet(node["style_sheet"])
        if "alignment_value" in node:
            found.setAlignment(Qt.AlignmentFlag(node["alignment_value"]))
        if "word_wrap" in node:
            found.setWordWrap(node["word_wrap"])
        return found

    def section(name):
        node = nodes[name]
        box = QGroupBox()
        box.setAccessibleName(node["accessible_name"])
        box.setStyleSheet(node["style_sheet"])
        box.setTitle(node["title"])
        inner = QVBoxLayout(box)
        inner.setContentsMargins(*node["margins"])
        inner.setSpacing(node["spacing"])
        return box, inner

    header = QHBoxLayout()
    header.addWidget(label("title"))
    header.addStretch()
    header.addWidget(label("subtitle"))
    root.addLayout(header)

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape(nodes["separator"]["frame_shape_value"]))
    separator.setStyleSheet(nodes["separator"]["style_sheet"])
    root.addWidget(separator)

    scroll = QScrollArea()
    scroll.setWidgetResizable(nodes["scroll"]["resizable"])
    scroll.setFrameShape(QFrame.Shape(nodes["scroll"]["frame_shape_value"]))
    container = QWidget()
    inner = QVBoxLayout(container)
    inner.setSpacing(nodes["container"]["spacing"])

    identity_box, identity_inner = section("identity_section")
    identity_row = QHBoxLayout()
    for name in ("identity_short", "identity_full", "identity_empty"):
        if name in nodes:
            identity_row.addWidget(label(name))
    identity_inner.addLayout(identity_row)
    inner.addWidget(identity_box)

    panels_row = QHBoxLayout()
    wallet_box, wallet_inner = section("wallet_section")
    wallet_inner.addWidget(label("balance_label"))
    if "awards_table" in nodes:
        table = QTableWidget()
        fill_table(table, nodes["awards_table"], payload["wallet_panel"]["rows"])
        wallet_inner.addWidget(table)
    else:
        wallet_inner.addWidget(label("awards_empty"))
    panels_row.addWidget(wallet_box)

    supply_box, supply_inner = section("supply_section")
    supply_row = QHBoxLayout()
    for index in range(5):
        column = QVBoxLayout()
        column.addWidget(label(f"supply_label_{index}"))
        column.addWidget(label(f"supply_value_{index}"))
        supply_row.addLayout(column)
    supply_inner.addLayout(supply_row)
    panels_row.addWidget(supply_box)
    inner.addLayout(panels_row)

    board_box, board_inner = section("leaderboard_section")
    if "leaderboard_table" in nodes:
        table = QTableWidget()
        fill_table(
            table, nodes["leaderboard_table"], payload["leaderboard_panel"]["rows"]
        )
        board_inner.addWidget(table)
    else:
        board_inner.addWidget(label("leaderboard_empty"))
    inner.addWidget(board_box)

    network_box, network_inner = section("network_section")
    status_row = QHBoxLayout()
    status_row.addWidget(label("status_dot"))
    status_row.addWidget(label("status_label"))
    status_row.addStretch()
    network_inner.addLayout(status_row)
    network_inner.addWidget(label("network_info"))
    url_row = QHBoxLayout()
    url_row.addWidget(label("url_label"))
    relay = QLineEdit(nodes["relay_field"]["text"])
    relay.setEnabled(nodes["relay_field"]["enabled"])
    relay.setStyleSheet(nodes["relay_field"]["style_sheet"])
    url_row.addWidget(relay)
    connect = QPushButton(nodes["connect_button"]["text"])
    connect.setEnabled(nodes["connect_button"]["enabled"])
    connect.setStyleSheet(nodes["connect_button"]["style_sheet"])
    url_row.addWidget(connect)
    network_inner.addLayout(url_row)
    inner.addWidget(network_box)
    inner.addStretch()

    scroll.setWidget(container)
    root.addWidget(scroll)
    return tab


@pytest.mark.parametrize("name", sorted(TAB_CASES))
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a tab the shipped tab does not."""
    app()
    old_side = render_offscreen(old_tab(name), PIXEL_SIZE)
    new_side = render_offscreen(
        tab_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the second side paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_tab("full"), PIXEL_SIZE),
        new_side=render_offscreen(
            tab_painted_by_the_model(model_payload("bare")), PIXEL_SIZE
        ),
        note="full against bare",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_tab("bare"), PIXEL_SIZE),
        new_side=render_offscreen(
            tab_painted_by_the_model(model_payload("board_only")), PIXEL_SIZE
        ),
        note="bare against board_only",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_tab("full"), PIXEL_SIZE),
        new_side=render_offscreen(
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


def test_the_tab_declares_no_skin_of_its_own():
    """A colour the surface ships is one the tab never paints."""
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.TAB_STYLE_SHEET == ""
    assert old_tab("full").styleSheet() == ""
    skinned = tab_painted_by_the_model(model_payload("full"))
    skinned.setStyleSheet("QWidget { background: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(old_tab("full"), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a skin the tab does not paint",
    )
    assert_pictures_match(
        old_side=render_widget(old_tab("full"), PIXEL_SIZE),
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


# What a picture cannot see


def test_the_accessible_names_are_compared_as_strings():
    """The names a screen reader announces reached no pixel."""
    from PySide6.QtWidgets import QGroupBox

    app()
    tab = old_tab("full")
    assert tab.accessibleName() == surface.ACCESSIBLE_NAME == "Competition Tab"
    boxes = tab.findChildren(QGroupBox)
    assert len(boxes) == 5
    assert {box.accessibleName() for box in boxes} == {surface.SECTION_ACCESSIBLE_NAME}
    assert surface.SECTION_ACCESSIBLE_NAME == "Section"
    assert [box.title() for box in boxes] == [
        title.upper() for title in surface.SECTION_TITLES
    ]


def test_the_disabled_field_and_button_are_compared_as_values():
    """The relay field or the Connect button became usable, unseen by a render."""
    from PySide6.QtWidgets import QLineEdit, QPushButton

    app()
    tab = old_tab("full")
    field = tab.findChild(QLineEdit)
    button = tab.findChild(QPushButton)
    assert field.isEnabled() is surface.RELAY_FIELD_ENABLED is False
    assert button.isEnabled() is surface.CONNECT_BUTTON_ENABLED is False
    assert field.text() == surface.RELAY_URL == "wss://relay.acervator.io"
    assert button.text() == surface.CONNECT_BUTTON_TEXT == "Connect  (v3.9.0)"
    assert surface.BUTTONS_ENABLED == {"connect_button": False}
    assert len(tab.findChildren(QPushButton)) == 1
    assert len(tab.findChildren(QLineEdit)) == 1


def test_the_layout_numbers_are_compared_as_values():
    """A margin or a spacing drifted between the two sides."""
    app()
    tab = old_tab("bare")
    margins = tab.layout().contentsMargins()
    assert (
        (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        )
        == surface.CONTENT_MARGINS
        == (10, 8, 10, 8)
    )
    assert tab.layout().spacing() == surface.CONTENT_SPACING == 8
    assert surface.SECTION_MARGINS == (8, 16, 8, 8)
    assert surface.SECTION_SPACING == 6
    assert surface.INNER_SPACING == 8
    section = shipped._Section("Bot Identity")
    inner = section.inner().contentsMargins()
    assert (
        inner.left(),
        inner.top(),
        inner.right(),
        inner.bottom(),
    ) == surface.SECTION_MARGINS
    assert section.inner().spacing() == surface.SECTION_SPACING


def test_the_table_settings_are_compared_as_values():
    """A header or an edit rule drifted between the two sides."""
    from PySide6.QtWidgets import QHeaderView, QTableWidget

    app()
    tab = old_tab("full")
    awards, board = tab.findChildren(QTableWidget)
    assert [
        awards.horizontalHeaderItem(index).text()
        for index in range(awards.columnCount())
    ] == list(surface.AWARD_COLUMNS)
    assert [
        board.horizontalHeaderItem(index).text() for index in range(board.columnCount())
    ] == list(surface.LEADERBOARD_COLUMNS)
    for table in (awards, board):
        header = table.horizontalHeader()
        assert header.sectionResizeMode(0) == QHeaderView.Stretch
        assert int(header.sectionResizeMode(0).value) == surface.HEADER_RESIZE_VALUE
        assert table.verticalHeader().isVisible() is surface.VERTICAL_HEADER_VISIBLE
        assert int(table.editTriggers().value) == surface.EDIT_TRIGGERS_NONE_VALUE
    assert awards.maximumHeight() == surface.award_table_height(2) == 80
    assert surface.award_table_height(0) == 28
    assert surface.award_table_height(4) == 120
    assert surface.award_table_height(400) == surface.AWARD_TABLE_MAX_HEIGHT_PX
    assert int(QTableWidget().editTriggers().value) == (
        surface.EDIT_TRIGGERS_DEFAULT_VALUE
    )


def test_the_label_alignment_is_compared_as_a_value():
    """The centred supply columns stopped being centred."""
    from PySide6.QtWidgets import QLabel

    app()
    tab = old_tab("bare")
    alignments = [int(found.alignment()) for found in tab.findChildren(QLabel)]
    assert alignments.count(surface.ALIGNMENT_VALUE) == 10
    assert (
        alignments.count(surface.LABEL_DEFAULT_ALIGNMENT_VALUE) == len(alignments) - 10
    )
    assert surface.ALIGNMENT_VALUE == 132
    assert surface.LABEL_DEFAULT_ALIGNMENT_VALUE == 129
    assert surface.ALIGNMENT == "AlignCenter"


def test_the_frame_shapes_are_compared_as_values():
    """A separator or a scroll frame changed shape, unseen by a render."""
    from PySide6.QtWidgets import QFrame, QScrollArea

    app()
    tab = old_tab("bare")
    scroll = tab.findChild(QScrollArea)
    assert int(scroll.frameShape().value) == surface.SCROLL_FRAME_SHAPE_VALUE == 0
    assert scroll.widgetResizable() is surface.SCROLL_RESIZABLE is True
    separators = [
        found
        for found in tab.findChildren(QFrame)
        if int(found.frameShape().value) == surface.SEPARATOR_FRAME_SHAPE_VALUE
    ]
    assert len(separators) == 1
    assert surface.SEPARATOR_FRAME_SHAPE_VALUE == 4
    assert surface.SEPARATOR_FRAME_SHAPE == "HLine"
    assert surface.SCROLL_FRAME_SHAPE == "NoFrame"


def test_the_word_wrap_on_the_notice_is_compared_as_a_value():
    """The network notice stopped wrapping, unseen by this size of render."""
    from PySide6.QtWidgets import QLabel

    app()
    tab = old_tab("bare")
    wrapped = [found for found in tab.findChildren(QLabel) if found.wordWrap()]
    assert len(wrapped) == 1
    assert wrapped[0].text() == surface.NETWORK_LINE_JOIN.join(surface.NETWORK_LINES)
    assert surface.INFO_WORD_WRAP is True
    assert len(surface.NETWORK_LINES) == 12
    assert surface.NETWORK_LINES[0].startswith("A real PoA competition")
    assert surface.NETWORK_LINES.count("") == 2


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
    assert "competition_tab.state" in noisy[0]
    assert len(seen) == before_removal


BLIND_TO_THE_PICTURE = {
    "accessible_name": "test_the_accessible_names_are_compared_as_strings",
    "section_accessible_name": "test_the_accessible_names_are_compared_as_strings",
    "field_enabled": "test_the_disabled_field_and_button_are_compared_as_values",
    "button_enabled": "test_the_disabled_field_and_button_are_compared_as_values",
    "content_margins": "test_the_layout_numbers_are_compared_as_values",
    "content_spacing": "test_the_layout_numbers_are_compared_as_values",
    "section_margins": "test_the_layout_numbers_are_compared_as_values",
    "section_spacing": "test_the_layout_numbers_are_compared_as_values",
    "header_resize_mode": "test_the_table_settings_are_compared_as_values",
    "vertical_header_visible": "test_the_table_settings_are_compared_as_values",
    "edit_triggers": "test_the_table_settings_are_compared_as_values",
    "table_max_height": "test_the_table_settings_are_compared_as_values",
    "label_alignment": "test_the_label_alignment_is_compared_as_a_value",
    "frame_shape": "test_the_frame_shapes_are_compared_as_values",
    "scroll_resizable": "test_the_frame_shapes_are_compared_as_values",
    "word_wrap": "test_the_word_wrap_on_the_notice_is_compared_as_a_value",
    "recorded_calls": "test_the_recorded_calls_are_compared_as_values",
    "refusal_type": "test_the_supply_outcomes_hold_both_an_answer_and_a_refusal",
    "timer_delay": "test_the_tab_starts_no_timer",
    "bus_topic": "test_the_tab_subscribes_to_no_bus_topic",
    "signal_wiring": "test_the_tab_wires_no_signal",
    "wallet_balance": "test_the_whole_tab_cells_and_balance_are_the_shipped_tabs",
    "data_dir": "test_the_tab_is_built_where_the_operator_pointed_it",
    "bridge_warning": "test_the_bridge_writes_no_warning_for_this_tab",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 24
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# Every value reaches the compared snapshot


def freeze(value):
    """One value as a single comparable string."""

    def plain(found):
        if isinstance(found, tuple):
            return [plain(item) for item in found]
        if isinstance(found, list):
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
        if isinstance(value, surface.CompetitionTabModel):
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
    payloads = [surface.build_view_model(new_model(name)) for name in TAB_CASES]
    loaded = new_model("full")
    loaded.load_identity()
    payloads.append(surface.build_view_model(loaded))
    refused = surface.CompetitionTabModel(
        identity=surface.IdentitySnapshot(BOT_KEY, error=RuntimeError("gone")),
        ledger=ledger_of(BOT_KEY, 0),
    )
    refused.load_identity()
    payloads.append(surface.build_view_model(refused))
    tiers = surface.CompetitionTabModel(
        identity=identity_of(BOT_KEY),
        ledger=ledger_of(BOT_KEY, 60, AWARD_CASES["every_tier"]),
        registry=surface.RegistrySnapshot(LEADERBOARD_CASES["two"]),
        season=2,
    )
    payloads.append(surface.build_view_model(tiers))
    payloads.append(surface.build_view_model(surface.build_model(None)))
    return payloads


COVERED_ELSEWHERE = {
    "SECTION_TITLES": "test_the_accessible_names_are_compared_as_strings",
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
    assert len(constants) > 90, len(constants)
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
    "accessible_name": ("ACCESSIBLE_NAME",),
    "section_accessible_name": ("SECTION_ACCESSIBLE_NAME",),
    "widgets": ("model.setup_ui",),
    "widget_names": ("model.setup_ui",),
    "widget_kinds": ("model.setup_ui",),
    "widget_parents": ("model.setup_ui",),
    "widget_children": ("model.setup_ui",),
    "widget_index": ("model.setup_ui",),
    "buttons_enabled": ("BUTTONS_ENABLED",),
    "content_margins": ("CONTENT_MARGINS",),
    "content_spacing": ("CONTENT_SPACING",),
    "section_margins": ("SECTION_MARGINS",),
    "section_spacing": ("SECTION_SPACING",),
    "inner_spacing": ("INNER_SPACING",),
    "scroll_resizable": ("SCROLL_RESIZABLE",),
    "scroll_frame_shape": ("SCROLL_FRAME_SHAPE",),
    "scroll_frame_shape_value": ("SCROLL_FRAME_SHAPE_VALUE",),
    "separator_frame_shape": ("SEPARATOR_FRAME_SHAPE",),
    "separator_frame_shape_value": ("SEPARATOR_FRAME_SHAPE_VALUE",),
    "section_titles": ("SECTION_TITLES",),
    "section_names": ("SECTION_TITLES",),
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
    "styles": (
        "LABEL_STYLE",
        "VAL_STYLE",
        "MONO_STYLE",
        "SECTION_STYLE",
        "TITLE_STYLE",
        "SUBTITLE_STYLE",
        "BALANCE_STYLE",
        "SUPPLY_VALUE_STYLE",
        "SEPARATOR_STYLE",
        "DOT_STYLE",
        "STATUS_STYLE",
        "INFO_STYLE",
        "URL_LABEL_STYLE",
        "RELAY_FIELD_STYLE",
        "CONNECT_BUTTON_STYLE",
        "EMPTY_STYLE",
    ),
    "texts": (
        "TAB_TITLE",
        "TAB_SUBTITLE",
        "NO_IDENTITY_TEXT",
        "NO_AWARDS_TEXT",
        "NO_MATCHES_TEXT",
        "DOT_TEXT",
        "NOT_CONNECTED_TEXT",
        "RELAY_LABEL",
        "RELAY_URL",
        "CONNECT_BUTTON_TEXT",
        "IDENTITY_FORMAT",
        "IDENTITY_TAIL",
        "BALANCE_FORMAT",
        "AWARD_TIER_FORMAT",
        "AWARD_AMOUNT_FORMAT",
        "AWARD_DATE_FORMAT",
        "SUPPLY_NUMBER_FORMAT",
        "LEADERBOARD_RECORD_FORMAT",
        "NETWORK_LINE_JOIN",
        "SEASON_TOO_LOW_MESSAGE",
    ),
    "network_lines": ("NETWORK_LINES",),
    "info_word_wrap": ("INFO_WORD_WRAP",),
    "relay_field_enabled": ("RELAY_FIELD_ENABLED",),
    "connect_button_enabled": ("CONNECT_BUTTON_ENABLED",),
    "award_columns": ("AWARD_COLUMNS",),
    "award_column_count": ("AWARD_COLUMN_COUNT",),
    "award_row_height_px": ("AWARD_ROW_HEIGHT_PX",),
    "award_table_padding_px": ("AWARD_TABLE_PADDING_PX",),
    "award_table_max_height_px": ("AWARD_TABLE_MAX_HEIGHT_PX",),
    "tier_column": ("TIER_COLUMN",),
    "leaderboard_columns": ("LEADERBOARD_COLUMNS",),
    "leaderboard_column_count": ("LEADERBOARD_COLUMN_COUNT",),
    "leaderboard_top_n": ("LEADERBOARD_TOP_N",),
    "leaderboard_keys": (
        "LEADERBOARD_RANK_KEY",
        "LEADERBOARD_BOT_KEY",
        "LEADERBOARD_RATING_KEY",
        "LEADERBOARD_WINS_KEY",
        "LEADERBOARD_LOSSES_KEY",
        "LEADERBOARD_WIN_RATE_KEY",
    ),
    "leaderboard_lead_row": ("LEADERBOARD_LEAD_ROW",),
    "leaderboard_lead_column": ("LEADERBOARD_LEAD_COLUMN",),
    "supply_labels": ("SUPPLY_LABELS",),
    "supply_keys": ("MINTED_KEY", "REMAINING_KEY", "HOLDERS_KEY"),
    "supply_constants": (
        "TOTAL_SUPPLY_CAP",
        "INITIAL_REWARD",
        "DECAY_FACTOR",
        "MIN_SEASON_REWARD",
        "GENESIS_SEASON",
    ),
    "identity_full_chars": ("IDENTITY_FULL_CHARS",),
    "alignment": ("ALIGNMENT",),
    "alignment_value": ("ALIGNMENT_VALUE",),
    "label_default_alignment_value": ("LABEL_DEFAULT_ALIGNMENT_VALUE",),
    "header_resize_mode": ("HEADER_RESIZE_MODE",),
    "header_resize_value": ("HEADER_RESIZE_VALUE",),
    "vertical_header_visible": ("VERTICAL_HEADER_VISIBLE",),
    "edit_triggers_none": ("EDIT_TRIGGERS_NONE",),
    "edit_triggers_none_value": ("EDIT_TRIGGERS_NONE_VALUE",),
    "edit_triggers_default_value": ("EDIT_TRIGGERS_DEFAULT_VALUE",),
    "data_dir_default": ("DATA_DIR_DEFAULT",),
    "data_dir": ("model.data_dir",),
    "state_files": ("IDENTITY_FILE", "LEDGER_FILE", "REGISTRY_FILE"),
    "default_season": ("DEFAULT_SEASON",),
    "season": ("model.season",),
    "identity_paths": ("IDENTITY_PATHS",),
    "wallet_paths": ("WALLET_PATHS",),
    "leaderboard_paths": ("LEADERBOARD_PATHS",),
    "balance_paths": ("BALANCE_PATHS",),
    "no_path": ("NO_PATH",),
    "actions": ("ACTIONS",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "skin": ("SKIN",),
    "tab_style_sheet": ("TAB_STYLE_SHEET",),
    "identity_panel": ("model.identity_panel",),
    "wallet_panel": ("model.wallet_panel",),
    "supply_panel": ("model.supply_panel",),
    "leaderboard_panel": ("model.leaderboard_panel",),
    "wallet_balance": ("model.get_wallet_balance",),
    "bot_id": ("model.bot_id",),
    "has_identity": ("model.identity",),
    "identity_path": ("model.identity_path",),
    "wallet_path": ("model.wallet_path",),
    "leaderboard_path": ("model.leaderboard_path",),
    "balance_path": ("model.balance_path",),
    "calls": ("model.calls",),
}


def resolve_source(name, model, held=None):
    """The value one named source holds, on the surface or on the model.

    ``held`` carries a value read before the model was driven again.
    Reading one panel appends to the call list, so the list has to come
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
    if key == "has_identity":
        return value is (resolve_source(sources[0], model, held) is not None)
    if key in ("widgets", "widget_names", "widget_kinds", "widget_parents"):
        return bool(value)
    if key in ("widget_children", "widget_index"):
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
    model = new_model("full")
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    assert len(payload) == 84
    fresh = new_model("full")
    surface.build_view_model(fresh)
    held = {"model.calls": [list(call) for call in fresh.calls]}
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(fresh, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, fresh, held), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = new_model("full")
    payload = surface.build_view_model(model)
    assert backed("alignment", payload["alignment"], ("ALIGNMENT",), model)
    assert not backed("alignment", "AlignLeft", ("ALIGNMENT",), model)
    assert not backed("award_columns", ["Tier"], ("AWARD_COLUMNS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("season", 9, ("model.season",), model)


# The shipped module keeps nothing between tabs


def test_the_shipped_tab_changes_no_value_the_next_tab_reads():
    """One tab left a changed value behind for the next one."""
    before = {
        name: value
        for name, value in vars(shipped).items()
        if isinstance(value, (str, int, float, dict, tuple))
        and not name.startswith("__")
    }
    for name in TAB_CASES:
        old_tab(name)
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


# The bridge


BRIDGE_STATE = {
    "identity": {"bot_id": BOT_KEY},
    "balance": 60,
    "awards": [
        {
            "tier_name": "Gold Fold",
            "tier_emoji": "G",
            "amount": 50,
            "competition_id": "comp-2",
            "timestamp": STAMP_TWO,
        }
    ],
    "summary": {"total_minted": 60, "remaining": 9_999_940, "total_holders": 1},
    "leaderboard": [
        {
            "rank": 1,
            "bot_id": BOT_KEY[:12] + "...",
            "rating": 1300,
            "w": 3,
            "l": 1,
            "win_rate": "75%",
        }
    ],
    "season": 1,
}


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.build_view_model(new_model("full"))
    encoded = json.loads(json.dumps(payload))
    assert encoded["method"] == "competition_tab.state"
    assert encoded["accessible_name"] == "Competition Tab"
    assert encoded["wallet_balance"] == 60
    assert encoded["wallet_path"] == "awards"
    assert encoded["leaderboard_path"] == "ranked"
    assert encoded["balance_path"] == "held"
    assert encoded["award_columns"] == ["Tier", "Amount", "Competition", "Date"]
    assert encoded["alignment_value"] == 132
    assert encoded["content_margins"] == [10, 8, 10, 8]
    assert encoded["actions"] == {}
    assert encoded["timers"] == {}
    assert encoded["bus_topics"] == []
    assert encoded["skin"] == {}
    assert len(encoded["widgets"]) == 46
    assert encoded["supply_panel"][0]["value_text"] == "10,000,000"


def test_bridge_registers_the_competition_tab_method():
    """The renderer cannot reach the competition tab through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "competition_tab.state"
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {"id": 71, "method": surface.METHOD, "params": {"state": BRIDGE_STATE}}
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["wallet_balance"] == 60
    assert result["bot_id"] == BOT_KEY
    assert result["has_identity"] is True
    assert len(result["wallet_panel"]["rows"]) == 1
    assert result["wallet_panel"]["rows"][0][0]["text"] == "G Gold Fold"
    assert len(result["leaderboard_panel"]["rows"]) == 1
    assert result["supply_panel"][3]["value_text"] == "500,000"
    desktop_bridge.handle_line(
        json.dumps({"id": 72, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


def test_the_bridge_answers_an_empty_tab_and_keeps_it_until_a_reset():
    """The surface forgot the tab between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 73, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    first = call({"state": BRIDGE_STATE})
    assert first["wallet_balance"] == 60
    kept = call({})
    assert kept["wallet_balance"] == 60
    fresh = call({"reset": True})
    assert fresh["wallet_balance"] == 0
    assert fresh["has_identity"] is False
    assert fresh["wallet_path"] == "empty"
    assert fresh["leaderboard_path"] == "empty"
    assert len(fresh["widgets"]) == 45
    call({"reset": True})


def test_the_bridge_reports_a_state_it_cannot_read():
    """A bad request ended the session instead of answering."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 74, "method": surface.METHOD, "params": {"state": 5}}),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"
    desktop_bridge.handle_line(
        json.dumps({"id": 75, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


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
    "json.dumps({'id': 1, 'method': 'competition_tab.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + "import json, sys\n"
    "from src.gui.main_tabs import competition_tab_surface as s\n"
    "model = s.build_model({'identity': {'bot_id': '%s'},\n"
    "    'balance': 60,\n"
    "    'awards': [{'tier_name': 'Gold Fold', 'tier_emoji': 'G',\n"
    "        'amount': 50, 'competition_id': 'comp-2',\n"
    "        'timestamp': 1700086400.0}],\n"
    "    'summary': {'total_minted': 60, 'remaining': 9999940,\n"
    "        'total_holders': 1},\n"
    "    'leaderboard': [{'rank': 1, 'bot_id': 'aa11bb22cc33...',\n"
    "        'rating': 1300, 'w': 3, 'l': 1, 'win_rate': '75%%'}],\n"
    "    'season': 1})\n"
    "payload = s.build_view_model(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'widgets': len(payload['widgets']),\n"
    "    'balance': payload['wallet_balance'],\n"
    "    'wallet_rows': payload['wallet_panel']['rows'],\n"
    "    'supply': [c['value_text'] for c in payload['supply_panel']],\n"
    "    'board_rows': payload['leaderboard_panel']['rows'],\n"
    "    'wallet_path': payload['wallet_path'],\n"
    "    'calls': len(payload['calls'])}))\n"
) % BOT_KEY


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
    """Reaching the competition tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == "competition_tab.state"
    assert result["accessible_name"] == "Competition Tab"
    assert result["award_columns"] == ["Tier", "Amount", "Competition", "Date"]
    assert result["wallet_balance"] == 0
    assert result["content_margins"] == [10, 8, 10, 8]
    assert len(result["widgets"]) == 45


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_paints_the_tab_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["widgets"] == 46
    assert answered["balance"] == 60
    assert answered["wallet_path"] == "awards"
    assert answered["supply"] == ["10,000,000", "60", "9,999,940", "500,000", "1"]
    assert [found["text"] for found in answered["wallet_rows"][0]] == [
        "G Gold Fold",
        "50",
        "comp-2",
        "2023-11-15",
    ]
    assert answered["wallet_rows"][0][0]["color"] == "#FFAA00"
    assert [found["text"] for found in answered["board_rows"][0]] == [
        "1",
        "aa11bb22cc33...",
        "1300",
        "3/1",
        "75%",
    ]
    assert answered["calls"] == 25


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
        "from src.gui import competition_tab\n"
        "print(json.dumps({'has_qt': competition_tab._QT,\n"
        "    'stub': competition_tab.CompetitionTab().__class__.__name__}))\n"
    )
    answered = run_script(probe)
    assert answered["has_qt"] is False
    assert answered["stub"] == "CompetitionTab"


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
    alpha_imports = {
        node.module
        for node in ast.walk(
            ast.parse(
                (SURFACE_PATH.parent.parent / "color_alpha.py").read_text(
                    encoding="utf-8"
                )
            )
        )
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("PySide6") for name in alpha_imports), alpha_imports
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
        "connect",
        "socket",
    ):
        assert forbidden not in reached, forbidden
    assert surface.RELAY_URL.startswith("wss://")
    assert surface.RELAY_URL in surface.NETWORK_LINES[4]
