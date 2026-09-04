"""The shipped bot status table and the Qt-free surface, side by side.

A failure means the view model carries a different cell, a different
colour, a different tooltip, a different button, a different highlight,
a different recorded call or a different refusal than ``BotStatusTable``.

No test here reads or writes the operator's runtime tree, opens a socket
or reaches an exchange. Every bot id, symbol, price and balance below is
invented.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import bot_status_table_surface as surface  # noqa: E402
from src.gui.widgets import bot_status_table as shipped  # noqa: E402
from tests.fixtures.host_fonts import (  # noqa: E402
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (  # noqa: E402
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

TABLE_PATH = REPO_ROOT / "src/gui/widgets/bot_status_table.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/bot_status_table_surface.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_CONTROL_PATH = REPO_ROOT / "src/gui/stock_main_window.py"

PIXEL_SIZE = (1000, 240)

# Counts measured off the file by the same counter that is pointed at a
# neighbour which really has one.
TABLE_CONNECT_SITES = 4
TABLE_TIMER_BUILDS = 0
TABLE_BUS_SITES = 0
TABLE_SIGNAL_BUILDS = 0
TABLE_ELEMENT_BUILDS = 6
CONTROL_CONNECT_SITES = 1
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_SIGNAL_BUILDS = 3
CONTROL_ELEMENT_BUILDS = 3

# Invented values. No bot id, symbol or balance below is the operator's.
UNICODE_BOT_ID = "Δ_fold→⚡"
UNICODE_SYMBOL = "Δ/USD"
MARKUP_BOT_ID = "<b>bot</b>"
MARKUP_SYMBOL = "<i>X</i>/USD"
APOSTROPHE_BOT_ID = "Ekthelius" + chr(39) + " Fold"
NEWLINE_BOT_ID = "two\nlines"
LONG_BOT_ID = "x" * 200
SEEDED_ICON_ASSET = "XRP"

ICON_MARK = "<a logo this machine happens to hold>"
AGE_MARK = "<a price age this test did not seed>"
SEEDED_AGES = frozenset({None})

WIDGETS_HELD: list = []
ICON_REQUESTS: list = []


# The privacy register is process-wide, and the table WRITES to it.
# Every test is given its own and the process one is put back.


@pytest.fixture(autouse=True)
def own_privacy_registry(tmp_path, monkeypatch):
    """Give this test its own register and restore the process one after.

    ``get_privacy_mask_registry`` returns one object for the whole
    process, both sides reach it through that one function, and a header
    click writes to it, so a mask a test leaves set would decide what a
    later test paints. A NEW object is handed out rather than a cleared
    one: clearing walks only the field ids the register declares.
    Autosave is off and the path is a temporary one, so no test writes a
    settings file.
    """
    from src.core import privacy_mask_registry as registry_module

    fresh = registry_module.PrivacyMaskRegistry(
        settings_path=tmp_path / "settings.json", autosave=False
    )
    monkeypatch.setattr(registry_module, "_SINGLETON", fresh)
    yield fresh


@pytest.fixture(autouse=True)
def watch_icon_requests(monkeypatch):
    """Record every coin logo the two sides ask this machine for."""
    from src.gui import bot_wizard

    real = bot_wizard._get_coin_icon

    def watched(symbol, size=20, download=True):
        ICON_REQUESTS.append([symbol, size, download])
        return real(symbol, size, download=download)

    monkeypatch.setattr(bot_wizard, "_get_coin_icon", watched)
    ICON_REQUESTS.clear()
    yield ICON_REQUESTS


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


# Invented bot statuses, and the case table both sides are driven with


def bot(**over):
    """One bot status, with a running scrumming bot as the base."""
    base = {
        "bot_id": "bot-alpha-0001",
        "symbol": "XRP/USD",
        "mode": "scrumming",
        "state": "running",
        "exchange": "coinbase",
        "current_holdings": 104.8,
        "quote_to_usd": 1.0,
        "live_target_balance": 50.0,
        "target_balance": 40.0,
        "stats": {"total_trades": 7, "position_value": 149.85, "current_price": 1.43},
    }
    base.update(over)
    return base


CASES: dict = {
    "happy": [bot(armed_action="scrum", auto_fire={"scrum_armed": True})],
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
    "not_scrumming": [bot(mode="extractor")],
    "no_bot_id": [bot(bot_id="", mode="extractor")],
    "number_where_text_belongs": [bot(symbol=5)],
    "text_where_a_number_belongs": [
        bot(live_target_balance="many", target_balance="many")
    ],
    "state_is_a_number": [bot(state=7)],
    "no_stats_at_all": [bot(stats={})],
    "pending_price": [
        bot(
            current_holdings=3.0,
            stats={"total_trades": 1, "position_value": 0.0, "current_price": 0.0},
        )
    ],
    "empty_position": [
        bot(
            current_holdings=0.0,
            stats={"total_trades": 0, "position_value": 0.0, "current_price": 0.0},
        )
    ],
    "stale_position": [
        bot(
            current_holdings=0.0,
            stats={"total_trades": 2, "position_value": 88.0, "current_price": 0.0},
        )
    ],
    "fold_armed": [bot(armed_action="fold", auto_fire={"fold_armed": True})],
    "fold_override": [
        bot(armed_action="fold", auto_fire={"fold_blockers": ["bb", "htf"]})
    ],
    "fold_ceiling": [
        bot(
            armed_action="fold",
            position_ceiling_enabled=True,
            ceiling_ratio=1.2,
            position_ceiling_usd=200.0,
        )
    ],
    "scrum_override": [
        bot(armed_action="scrum", auto_fire={"scrum_blockers": ["rsi"]})
    ],
    "phase_fire": [bot(scrum_target_mode="fire")],
    "phase_track": [bot(scrum_target_mode="track")],
    "phase_search": [bot(scrum_target_mode="search")],
    "inactive": [bot(state="stopped")],
    "cooldown": [bot(state="cooldown")],
    "idle": [bot(state="idle")],
    "error_state": [bot(state="error")],
    "paused": [bot(state="paused")],
    "starting": [bot(state="starting")],
    "unknown_state": [bot(state="hibernating")],
    "ceiling_approach": [
        bot(
            armed_action="scrum",
            auto_fire={"scrum_armed": True},
            position_ceiling_enabled=True,
            ceiling_ratio=0.7,
            position_ceiling_usd=200.0,
            fold_rate_taper=0.4,
        )
    ],
    "ceiling_normal": [
        bot(
            armed_action="scrum",
            auto_fire={"scrum_armed": True},
            position_ceiling_enabled=True,
            ceiling_ratio=0.2,
            position_ceiling_usd=200.0,
        )
    ],
    "detonation": [
        bot(
            armed_action="scrum",
            auto_fire={"scrum_armed": True},
            detonation_enabled=True,
            detonation_timeframe="4h",
        )
    ],
    "ceiling_without_an_amount": [
        bot(
            armed_action="scrum",
            auto_fire={"scrum_armed": True},
            position_ceiling_enabled=True,
            ceiling_ratio=0.7,
        )
    ],
    "detonation_without_a_timeframe": [
        bot(
            armed_action="scrum",
            auto_fire={"scrum_armed": True},
            detonation_enabled=True,
            detonation_timeframe=None,
        )
    ],
    "unknown_exchange": [bot(exchange="nowhere")],
    "no_symbol": [bot(symbol="")],
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
}

# The five inputs both sides refuse, named so the outcome check can
# prove its set holds a refusal as well as an answer.
REFUSING = (
    "number_where_text_belongs",
    "text_where_a_number_belongs",
    "state_is_a_number",
    "ceiling_without_an_amount",
    "detonation_without_a_timeframe",
    "three_rows_second_refuses",
)

SEQUENCES: dict = {
    "shrink": ["three_rows", "one_row"],
    "grow": ["one_row", "three_rows"],
    "empty_then_full": ["empty", "three_rows"],
    "full_then_empty": ["three_rows", "empty"],
    "same_twice": ["happy", "happy"],
    "skip_then_fill": ["not_scrumming", "happy"],
    "fill_then_skip": ["happy", "not_scrumming"],
    "shrink_then_refuse": ["four_rows", "three_rows_second_refuses"],
    "refuse_then_answer": ["state_is_a_number", "happy"],
    "three_steps": ["four_rows", "three_rows_second_refuses", "one_row"],
}

PICTURE_CASES = (
    "happy",
    "empty",
    "zero_target",
    "three_rows",
    "fold_armed",
    "fold_ceiling",
    "phase_fire",
    "phase_track",
    "phase_search",
    "inactive",
    "idle",
    "not_scrumming",
    "unicode",
    "no_symbol",
    "stale_position",
)


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


def platform_chosen(value):
    """One value with anything the machine chose replaced by a marker.

    Whether a coin logo is on this machine decides ``icon_found``, and a
    warm shared price cache decides ``price_age_s``. Both are hidden so
    the comparison reads the product. Everything this test seeded is
    kept.
    """
    if isinstance(value, dict):
        found = {}
        for key, item in value.items():
            if key == "icon_found":
                found[key] = ICON_MARK
            elif key == "price_age_s" and item not in SEEDED_AGES:
                found[key] = AGE_MARK
            else:
                found[key] = platform_chosen(item)
        return found
    if isinstance(value, (list, tuple)):
        return [platform_chosen(item) for item in value]
    return value


def canon_colour(value):
    """One colour in a single spelling, so ``#888`` and ``#888888`` agree."""
    from PySide6.QtGui import QColor

    if not value:
        return ""
    return QColor(value).name().lower()


def readable(value):
    """One value ready to compare: numbers as text, machine values hidden."""
    return platform_chosen(numbered(value))


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


def button_shape(text, enabled, style_sheet, tooltip, height, glow, blur):
    """One button's values, in the one shape both sides are read into."""
    return {
        "text": text,
        "enabled": enabled,
        "style_sheet": style_sheet,
        "tooltip": tooltip,
        "height": height,
        "glow": canon_colour(glow),
        "glow_blur": float(blur),
    }


def old_button(found):
    """One real button read off the shipped table."""
    from PySide6.QtGui import QColor

    if found is None:
        return None
    glow = found.graphicsEffect()
    return button_shape(
        found.text(),
        found.isEnabled(),
        found.styleSheet(),
        found.toolTip(),
        found.maximumHeight(),
        QColor(glow.color()).name() if glow else "",
        glow.blurRadius() if glow else 0.0,
    )


def new_button(found):
    """One button the surface described."""
    if found is None:
        return None
    return button_shape(
        found["text"],
        found["enabled"],
        found["style_sheet"],
        found["tooltip"],
        found["height"],
        found.get("glow", ""),
        found.get("glow_blur_radius", 0.0),
    )


def read_old(table):
    """One real table read cell by cell off the widget."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                cells.append(None)
                continue
            brush = item.foreground()
            cells.append(
                {
                    "text": item.text(),
                    "color": (
                        ""
                        if brush.style() == Qt.NoBrush
                        else canon_colour(QColor(brush.color()).name())
                    ),
                    "tooltip": item.toolTip(),
                    "alignment": int(item.textAlignment()),
                    "underline": item.font().underline(),
                    "url": item.data(Qt.UserRole) or "",
                    "icon_found": not item.icon().isNull(),
                }
            )
        rows.append(
            {
                "cells": cells,
                "fire": old_button(table.cellWidget(row, surface.FIRE_COLUMN)),
                "detail": old_button(table.cellWidget(row, surface.DETAIL_COLUMN)),
            }
        )
    return {
        "headers": [
            {
                "text": table.horizontalHeaderItem(column).text(),
                "tooltip": table.horizontalHeaderItem(column).toolTip(),
            }
            for column in range(table.columnCount())
        ],
        "column_count": table.columnCount(),
        "row_count": table.rowCount(),
        "rows": rows,
        "selected": table.get_selected_bot_id(),
        "bot_ids": list(table._bot_ids),
    }


def read_new(payload):
    """One surface payload read into the shape the widget is read into."""
    rows = []
    for row in payload["rows"]:
        cells = [
            (
                None
                if found is None
                else {
                    "text": found["text"],
                    "color": canon_colour(found["color"]),
                    "tooltip": found["tooltip"],
                    "alignment": found["alignment_value"],
                    "underline": found["underline"],
                    "url": found["chart_url"],
                    "icon_found": ICON_MARK,
                }
            )
            for found in row["cells"]
        ]
        rows.append(
            {
                "cells": cells,
                "fire": new_button(row["fire"]),
                "detail": new_button(row["detail"]),
            }
        )
    return {
        "headers": [
            {"text": found["text"], "tooltip": found["tooltip"]}
            for found in payload["headers"]
        ],
        "column_count": payload["column_count"],
        "row_count": payload["row_count"],
        "rows": rows,
        "selected": payload["selected_bot_id"],
        "bot_ids": payload["bot_ids"],
    }


# Driving both sides from one case


def old_table(names=(), on_bot_clicked=None, on_fire_clicked=None):
    """The shipped table, driven through each named case in turn."""
    app()
    table = hold(
        shipped.BotStatusTable(
            on_bot_clicked=on_bot_clicked, on_fire_clicked=on_fire_clicked
        )
    )
    for name in names:
        table.update_bots(CASES[name])
    return table


def new_model(names=(), on_bot_clicked=None, on_fire_clicked=None):
    """The surface model, driven through each named case in turn."""
    model = surface.BotStatusTableModel(
        on_bot_clicked=on_bot_clicked, on_fire_clicked=on_fire_clicked
    )
    for name in names:
        model.update_bots(CASES[name])
    return model


def drive(names):
    """Both sides through the same step sequence, read into one shape.

    Returns the two states, the two outcomes and the two logo request
    lists, so a caller compares what each side did as well as what it
    holds.
    """
    ICON_REQUESTS.clear()
    table = old_table()
    old_outcome = guarded(lambda: [table.update_bots(CASES[name]) for name in names])
    old_icons = [[found[0], found[1]] for found in ICON_REQUESTS]
    model = surface.BotStatusTableModel()
    new_outcome = guarded(lambda: [model.update_bots(CASES[name]) for name in names])
    new_icons = [
        [call[1], call[2]] for call in model.calls if call[0] == surface.ROW_ICON
    ]
    return {
        "old": read_old(table),
        "new": read_new(surface.build_view_model(model)),
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "old_icons": old_icons,
        "new_icons": new_icons,
    }


def both_sides_agree(run, note):
    """Fail unless the two sides did the same thing and hold the same state."""
    assert (
        run["old_outcome"] == run["new_outcome"]
    ), "%s: the shipped table and the surface refused differently: %r against %r" % (
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
    assert run["old_icons"] == run["new_icons"], "%s: %r against %r" % (
        note,
        run["old_icons"],
        run["new_icons"],
    )


# The two sides, case by case


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_table_is_the_shipped_tables(name):
    """The surface describes a table the shipped table does not paint."""
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


def test_the_sample_hashes_are_reported():
    """The comparison reports no hash, so nothing can be checked by hand."""
    happy = drive(["happy"])
    empty = drive(["empty"])
    assert len(digest(happy["old"])) == 64
    assert digest(happy["old"]) == digest(happy["new"])
    assert digest(empty["old"]) == digest(empty["new"])
    assert digest(happy["old"]) != digest(empty["old"])


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash gives one value for every table, so it tells nothing apart."""
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
    """The reader reports a difference between two not-a-numbers that is none."""
    first = float("nan")
    second = float("inf") - float("inf")
    assert first != second
    assert readable(first) == readable(second)
    assert digest({"a": first}) == digest({"a": second})
    assert readable(float("inf")) != readable(float("-inf"))


def test_the_machine_rule_keeps_a_seeded_value_and_hides_a_chosen_one():
    """The rule hides a value this test seeded, or keeps one the machine chose."""
    body = {"icon_asset": SEEDED_ICON_ASSET, "icon_found": True, "price_age_s": 41.5}
    found = platform_chosen(body)
    assert found["icon_asset"] == SEEDED_ICON_ASSET
    assert found["icon_found"] == ICON_MARK
    assert found["price_age_s"] == AGE_MARK
    assert platform_chosen({"price_age_s": None})["price_age_s"] is None
    assert platform_chosen({"icon_found": False})["icon_found"] == ICON_MARK


# What each side DID: answered, or refused with which wording


def outcomes(names):
    """What each side did for each named case, on both sides."""
    return {name: drive([name])["old_outcome"] for name in names}


def test_the_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    found = outcomes(sorted(CASES))
    answered = [name for name, done in found.items() if not done["error"]]
    refused = [name for name, done in found.items() if done["error"]]
    assert answered, found
    assert refused, found
    assert sorted(refused) == sorted(REFUSING), sorted(set(refused) ^ set(REFUSING))
    assert len(answered) + len(refused) == len(CASES)


@pytest.mark.parametrize("name", sorted(REFUSING))
def test_a_refused_input_refuses_the_same_way_on_both_sides(name):
    """One side answered an input the other refused, or worded it differently."""
    run = drive([name])
    assert run["old_outcome"]["error"], name
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    both_sides_agree(run, name)


def test_the_refusal_comparison_reports_two_different_wordings():
    """The refusal comparison passes whatever wording a side produces."""
    found = outcomes(sorted(REFUSING))
    headlines = {name: done["headline"] for name, done in found.items()}
    assert len(set(map(str, headlines.values()))) > 1, headlines
    assert guarded(lambda: 1) != guarded(lambda: 1 / 0)
    assert guarded(lambda: int("x"))["error"] == "ValueError"
    assert guarded(lambda: int("x"))["headline"] != guarded(lambda: 1 / 0)["headline"]


# Step sequences, including one that refuses part way


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_a_step_sequence_is_the_shipped_tables(name):
    """A rewrite left the surface holding rows the shipped table does not."""
    both_sides_agree(drive(SEQUENCES[name]), name)


def test_a_shrink_then_a_refusal_leaves_the_same_rows_on_both_sides():
    """A shrink that refuses part way left different rows on the two sides."""
    run = drive(SEQUENCES["shrink_then_refuse"])
    both_sides_agree(run, "shrink_then_refuse")
    assert run["old_outcome"]["error"] == "AttributeError"
    assert run["old"]["row_count"] == len(CASES["three_rows_second_refuses"])
    assert run["old"]["bot_ids"] == ["alpha", "beta"]
    third = run["old"]["rows"][2]["cells"][0]
    assert third is not None, "the row left behind carries no first cell"
    assert third["text"] == "gamma", third
    assert run["new"]["rows"][2]["cells"][0]["text"] == "gamma"


def test_the_sequence_check_reports_a_row_left_behind():
    """The sequence check passes whatever a rewrite leaves on screen."""
    kept = drive(SEQUENCES["shrink_then_refuse"])
    fresh = drive(["three_rows_second_refuses"])
    assert kept["old"]["row_count"] == fresh["old"]["row_count"]
    assert digest(kept["old"]) != digest(fresh["old"]), "the left-behind row is unseen"
    assert fresh["old"]["rows"][2]["cells"][0] is None
    assert kept["old"]["rows"][2]["cells"][0] is not None


# The highlight follows the bot, not the row


def test_the_highlight_follows_the_bot_not_the_row():
    """A refresh left the highlight on a row holding a different bot."""
    app()
    table = old_table(["three_rows"])
    table.selectRow(2)
    assert table.get_selected_bot_id() == "gamma"
    model = new_model(["three_rows"])
    model.select_row(2)
    assert model.get_selected_bot_id() == "gamma"
    swapped = [CASES["three_rows"][2], CASES["three_rows"][0]]
    table.update_bots(swapped)
    model.update_bots(swapped)
    assert table.get_selected_bot_id() == "gamma"
    assert model.get_selected_bot_id() == "gamma"
    assert table.currentRow() == 0
    assert model.current_row == 0


def test_a_bot_that_left_the_fleet_clears_the_highlight_on_both_sides():
    """The highlight stayed on a row after its bot left the fleet."""
    app()
    table = old_table(["three_rows"])
    table.selectRow(2)
    model = new_model(["three_rows"])
    model.select_row(2)
    table.update_bots(CASES["one_row"])
    model.update_bots(CASES["one_row"])
    assert table.get_selected_bot_id() == ""
    assert model.get_selected_bot_id() == ""
    assert table.currentRow() == model.current_row == -1


def test_a_detail_press_selects_its_own_row_first():
    """The Detail button opened a dialog with another row still highlighted."""
    app()
    old_seen: list = []
    new_seen: list = []
    table = old_table(["three_rows"], on_bot_clicked=old_seen.append)
    model = new_model(["three_rows"], on_bot_clicked=new_seen.append)
    table._on_detail("beta")
    model.on_detail("beta")
    assert old_seen == new_seen == ["beta"]
    assert table.get_selected_bot_id() == model.get_selected_bot_id() == "beta"
    table._on_detail("")
    model.on_detail("")
    assert table.get_selected_bot_id() == model.get_selected_bot_id() == "beta"


def test_a_fire_press_hands_over_the_bot_on_both_sides():
    """Manual Fire reached the engine with a different bot on one side."""
    app()
    old_seen: list = []
    new_seen: list = []
    table = old_table(["three_rows"], on_fire_clicked=old_seen.append)
    model = new_model(["three_rows"], on_fire_clicked=new_seen.append)
    table._on_fire("gamma")
    model.on_fire("gamma")
    assert old_seen == new_seen == ["gamma"]
    assert surface.BotStatusTableModel().on_fire("nobody") is None


def test_a_press_with_no_handler_wired_does_nothing_on_both_sides():
    """A press with nothing wired raised instead of doing nothing."""
    app()
    table = old_table(["one_row"])
    model = new_model(["one_row"])
    assert table._on_detail("alpha") is None
    assert model.on_detail("alpha") is None
    assert table._on_fire("alpha") is None
    assert model.on_fire("alpha") is None


def test_the_selection_reader_reports_a_row_that_is_not_selected():
    """The selection reader answers a bot id whatever the highlight holds."""
    app()
    table = old_table(["three_rows"])
    model = new_model(["three_rows"])
    assert table.get_selected_bot_id() == model.get_selected_bot_id() == ""
    table.selectRow(1)
    model.select_row(1)
    assert table.get_selected_bot_id() == model.get_selected_bot_id() == "beta"
    table.clearSelection()
    model.clear_selection()
    assert table.get_selected_bot_id() == model.get_selected_bot_id() == ""


def test_a_symbol_press_opens_the_chart_on_both_sides():
    """The Symbol cell opened a different address, or none at all."""
    import webbrowser

    app()
    opened: list = []
    real = webbrowser.open
    webbrowser.open = lambda url, new=0: opened.append([url, new])
    try:
        table = old_table(["happy"])
        table._on_cell_clicked(0, surface.SYMBOL_COLUMN)
        table._on_cell_clicked(0, surface.MODE_COLUMN)
        table._on_cell_clicked(9, surface.SYMBOL_COLUMN)
    finally:
        webbrowser.open = real
    model = new_model(["happy"])
    assert model.on_cell_clicked(0, surface.SYMBOL_COLUMN) == opened[0][0]
    assert model.on_cell_clicked(0, surface.MODE_COLUMN) == ""
    assert model.on_cell_clicked(9, surface.SYMBOL_COLUMN) == ""
    assert len(opened) == 1, opened
    assert opened[0][1] == surface.BROWSER_NEW_WINDOW
    assert model.opened_urls == [opened[0][0]]


def test_a_symbol_press_on_an_unlisted_exchange_opens_nothing():
    """A cell with no chart address opened one anyway."""
    import webbrowser

    app()
    opened: list = []
    real = webbrowser.open
    webbrowser.open = lambda url, new=0: opened.append([url, new])
    try:
        old_table(["unknown_exchange"])._on_cell_clicked(0, surface.SYMBOL_COLUMN)
    finally:
        webbrowser.open = real
    assert opened == []
    assert (
        new_model(["unknown_exchange"]).on_cell_clicked(0, surface.SYMBOL_COLUMN) == ""
    )


# The header dot hides and shows a column


def header_press(columns, name="happy"):
    """Both sides pressing the same headers, each from one register state.

    The register is process-wide and both sides write to it, so the
    second side would start from what the first side left. It is put
    back to the state the first side started from.
    """
    start = registry().to_dict()
    table = old_table([name])
    for column in columns:
        table._on_header_clicked(column)
    old_state = registry().to_dict()
    old_read = read_old(table)
    registry().load_from_dict(start)
    model = new_model([name])
    for column in columns:
        model.on_header_clicked(column)
    new_state = registry().to_dict()
    new_read = read_new(surface.build_view_model(model))
    return {
        "old": old_read,
        "new": new_read,
        "old_state": old_state,
        "new_state": new_state,
        "table": table,
        "model": model,
    }


@pytest.mark.parametrize("column", sorted(surface.PRIVACY_FIELD_BY_COL))
def test_a_header_press_hides_the_column_on_both_sides(column):
    """A header press hid a different column on one side than the other."""
    app()
    run = header_press([column])
    assert readable(run["old"]) == readable(run["new"])
    assert run["old_state"] == run["new_state"]
    assert run["old_state"][surface.PRIVACY_FIELD_BY_COL[column]] is True
    shown = (
        run["old"]["rows"][0]["fire"]["text"]
        if column == surface.FIRE_COLUMN
        else run["old"]["rows"][0]["cells"][column]["text"]
    )
    assert shown == "****", (column, shown)


def test_a_header_press_on_the_detail_column_changes_nothing():
    """The Detail column carries a mask it must not have."""
    app()
    before = readable(read_old(old_table(["happy"])))
    run = header_press([surface.DETAIL_COLUMN])
    assert readable(run["old"]) == before
    assert readable(run["new"]) == before
    assert run["old_state"] == run["new_state"]
    assert run["old_state"] == {field: False for field in registry().known_field_ids()}


def test_a_second_header_press_shows_the_column_again():
    """A column stayed hidden after a second press."""
    app()
    run = header_press([0, 0])
    assert run["old_state"]["bot_table.bot_id"] is False
    assert run["old_state"] == run["new_state"]
    assert readable(run["old"]) == readable(run["new"])
    assert run["old"]["rows"][0]["cells"][0]["text"] == "bot-alpha-0001"


def test_a_header_press_before_any_row_paints_nothing():
    """A press with no rows yet raised instead of doing nothing."""
    app()
    start = registry().to_dict()
    table = old_table()
    table._on_header_clicked(0)
    old_read = read_old(table)
    registry().load_from_dict(start)
    model = surface.BotStatusTableModel()
    model.on_header_clicked(0)
    new_read = read_new(surface.build_view_model(model))
    assert old_read["row_count"] == new_read["row_count"] == 0
    assert readable(old_read) == readable(new_read)


def test_a_broken_register_leaves_the_headers_alone_on_both_sides():
    """A register that cannot be read took the table down with it."""
    from src.core import privacy_mask_registry as registry_module

    app()
    table = old_table(["happy"])
    model = new_model(["happy"])
    before = readable(read_old(table))
    real = registry_module.get_privacy_mask_registry

    def refuse():
        raise RuntimeError("register gone")

    registry_module.get_privacy_mask_registry = refuse
    shipped.get_privacy_mask_registry = refuse
    surface.get_privacy_mask_registry = refuse
    try:
        table._on_header_clicked(0)
        model.on_header_clicked(0)
        table._refresh_header_dots()
        model.refresh_header_dots()
    finally:
        registry_module.get_privacy_mask_registry = real
        shipped.get_privacy_mask_registry = real
        surface.get_privacy_mask_registry = real
    assert readable(read_old(table)) == before
    assert readable(read_new(surface.build_view_model(model))) == before


# The surface holds its own values


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    before = dict(shipped.BotStatusTable.STATE_COLORS)
    before_labels = shipped.SCRUMMING_COLUMNS.labels
    from PySide6.QtGui import QColor

    shipped.BotStatusTable.STATE_COLORS = dict(before)
    shipped.BotStatusTable.STATE_COLORS["running"] = QColor("#123456")
    try:
        moved = read_old(old_table(["happy"]))
        kept = read_new(surface.build_view_model(new_model(["happy"])))
        assert moved["rows"][0]["cells"][2]["color"] == "#123456"
        assert kept["rows"][0]["cells"][2]["color"] == canon_colour(
            surface.STATE_COLORS["running"]
        )
        assert kept["rows"][0]["cells"][2]["color"] != "#123456"
        differences = [
            key
            for key in ("headers", "row_count", "bot_ids", "selected", "column_count")
            if readable(moved[key]) != readable(kept[key])
        ]
        assert differences == [], differences
    finally:
        shipped.BotStatusTable.STATE_COLORS = before
    assert shipped.SCRUMMING_COLUMNS.labels == before_labels
    both_sides_agree(drive(["happy"]), "after the value was put back")


def test_the_shipped_file_is_not_named_by_the_surface():
    """The surface reaches into the widget it replaces."""
    text = SURFACE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("widgets" in name for name in imported), imported


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


def declared_classes(path):
    """Every class one file declares, wherever it is declared.

    A class inside an ``if``, inside a method or inside another class is
    still a class, so the whole tree is walked rather than its top level.
    """
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
                if (
                    name.startswith("Q")
                    or name in found
                    or name.endswith("TableWidget")
                ):
                    found.add(node.name)
                    growing = True
                    break
    return found


def count_elements(path):
    """How many screen elements one file builds, its own classes included."""
    return count_built(path, WIDGET_NAMES_BUILT) + len(declared_widget_classes(path))


def test_the_table_wires_four_signals_and_the_surface_names_four_actions():
    """A wiring appeared on one side and not the other."""
    assert count_text(TABLE_PATH, ".connect(") == TABLE_CONNECT_SITES == 4
    assert count_text(SURFACE_PATH, ".connect(") == 0
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES == 1
    assert len(surface.ACTIONS) == count_text(TABLE_PATH, ".connect(")
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.BotStatusTableModel, name)), name


def test_the_table_starts_no_timer():
    """A wait appeared on one side and not the other."""
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(TABLE_PATH, timer_names) == TABLE_TIMER_BUILDS == 0
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
        old_table(["happy", "three_rows"])
        new_model(["happy", "three_rows"])
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


def test_the_table_declares_no_signal_of_its_own():
    """A signal declaration appeared on one side and not the other."""
    signal_names = ("Signal",)
    assert count_built(TABLE_PATH, signal_names) == TABLE_SIGNAL_BUILDS == 0
    assert count_built(SURFACE_PATH, signal_names) == 0
    assert count_built(SIGNAL_CONTROL_PATH, signal_names) == CONTROL_SIGNAL_BUILDS == 3
    assert count_text(SIGNAL_CONTROL_PATH, "Signal") > CONTROL_SIGNAL_BUILDS


def test_the_table_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(TABLE_PATH, ".subscribe(") == TABLE_BUS_SITES == 0
    assert count_text(SURFACE_PATH, ".subscribe(") == 0
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_text(TABLE_PATH, ".subscribe(")


def test_the_screen_elements_the_table_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(TABLE_PATH) == TABLE_ELEMENT_BUILDS == 6
    assert count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert declared_widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert declared_widget_classes(TABLE_PATH) == {"BotStatusTable"}
    assert count_built(TABLE_PATH, WIDGET_NAMES_BUILT) == 5
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == set()


def test_the_class_counter_finds_a_class_declared_inside_another():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(NESTED_CLASS_CONTROL_PATH)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    assert len(found) == 4, sorted(found)
    tree = ast.parse(NESTED_CLASS_CONTROL_PATH.read_text(encoding="utf-8"))
    top_level = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert top_level == set(), top_level
    assert declared_classes(TABLE_PATH) == {"BotStatusTable"}
    assert {
        node.name
        for node in ast.parse(TABLE_PATH.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
    } == set()


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


CLASS_MAP = {"BotStatusTable": "BotStatusTableModel"}

METHOD_MAP = {
    "BotStatusTable.__init__": "BotStatusTableModel.__init__",
    "BotStatusTable._on_header_clicked": "BotStatusTableModel.on_header_clicked",
    "BotStatusTable._refresh_header_dots": "BotStatusTableModel.refresh_header_dots",
    "BotStatusTable.update_bots": "BotStatusTableModel.update_bots",
    "BotStatusTable._on_detail": "BotStatusTableModel.on_detail",
    "BotStatusTable._on_cell_clicked": "BotStatusTableModel.on_cell_clicked",
    "BotStatusTable._on_fire": "BotStatusTableModel.on_fire",
    "BotStatusTable.get_selected_bot_id": "BotStatusTableModel.get_selected_bot_id",
}

HELPER_MAP = {
    "_mag": "target_text",
    "_apply_glow": "BotStatusTableModel._fire_button",
    "_risk_suffix": "BotStatusTableModel.risk_suffix",
    "_reanchor_bot_selection": "BotStatusTableModel.reanchor_selection",
    "_select_row_for_bot": "BotStatusTableModel.select_row_for_bot",
    "column_spec": "build_view_model",
    "bridge_handler": "view_model",
    "model_from_statuses": "build_model",
}

MODEL_MEMBERS = {
    "__init__",
    "refresh_header_dots",
    "on_header_clicked",
    "set_row_count",
    "update_bots",
    "set_cell",
    "cell_at",
    "_write_row",
    "_target_value",
    "_ammo_cell",
    "_symbol_cell",
    "_fire_button",
    "_armed_fire",
    "risk_suffix",
    "_detail_button",
    "get_selected_bot_id",
    "select_row",
    "clear_selection",
    "_row_has_first_cell",
    "reanchor_selection",
    "select_row_for_bot",
    "on_detail",
    "on_fire",
    "on_cell_clicked",
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
    assert len(METHOD_MAP) == 8
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 8
    assert members(surface.BotStatusTableModel) == MODEL_MEMBERS, sorted(
        members(surface.BotStatusTableModel) ^ MODEL_MEMBERS
    )
    assert len(MODEL_MEMBERS) == 24
    assert declared_classes(TABLE_PATH) == set(CLASS_MAP)


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "update_bots" in members(shipped.BotStatusTable)
    assert "get_selected_bot_id" in members(shipped.BotStatusTable)
    assert "BotStatusTable" not in MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("BotStatusTableModel.no_such_member")
    assert MODEL_MEMBERS - {"update_bots"} != MODEL_MEMBERS
    assert members(surface.BotStatusTableModel) - {"on_fire"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"BotStatusTable.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"BotStatusTable"} != shipped_classes()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    app()
    assert list(inspect.signature(shipped.BotStatusTable.__init__).parameters) == [
        "self",
        "on_bot_clicked",
        "on_fire_clicked",
        "parent",
    ]
    assert list(inspect.signature(surface.BotStatusTableModel.__init__).parameters) == [
        "self",
        "on_bot_clicked",
        "on_fire_clicked",
    ]
    assert list(
        inspect.signature(shipped.BotStatusTable.update_bots).parameters
    ) == list(inspect.signature(surface.BotStatusTableModel.update_bots).parameters)
    old_click = list(
        inspect.signature(shipped.BotStatusTable._on_cell_clicked).parameters
    )
    new_click = list(
        inspect.signature(surface.BotStatusTableModel.on_cell_clicked).parameters
    )
    assert len(old_click) == len(new_click) == 3
    assert old_click[:2] == new_click[:2] == ["self", "row"]
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


def test_the_table_is_reached_by_the_window_and_the_surface_by_the_bridge():
    """The count of readers is wrong, so a lost reader would pass unseen."""
    readers = modules_importing("bot_status_table", skip=(SURFACE_PATH, TABLE_PATH))
    assert readers == [
        str(REPO_ROOT / "src/gui/main_window.py"),
        str(REPO_ROOT / "src/gui/widgets/bot_selection.py"),
        str(REPO_ROOT / "src/gui/widgets/exchange_tab.py"),
    ], readers
    assert modules_importing("bot_status_table_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    known = modules_importing("design_system")
    assert len(known) > 5, known


# The table paints, and the two sides paint the same pixels


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    return sealed(surface.build_view_model(new_model([name])))


def table_painted_by_the_model(payload):
    """One table built only from the surface's view model."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QGraphicsDropShadowEffect,
        QHeaderView,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )

    from src.gui.bot_wizard import _get_coin_icon

    payload = unaltered(payload)
    app()
    table = hold(QTableWidget())
    table.setColumnCount(payload["column_count"])
    table.setHorizontalHeaderLabels([found["text"] for found in payload["headers"]])
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    for column, width in payload["fixed_widths"].items():
        header.setSectionResizeMode(int(column), QHeaderView.Fixed)
        table.setColumnWidth(int(column), width)
    table.setAlternatingRowColors(payload["alternating_row_colors"])
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(payload["vertical_header_visible"])
    for column, found in enumerate(payload["headers"]):
        item = table.horizontalHeaderItem(column)
        if item:
            item.setToolTip(found["tooltip"])
    table.setRowCount(payload["row_count"])
    for index, row in enumerate(payload["rows"]):
        for column, found in enumerate(row["cells"]):
            if found is None:
                continue
            item = QTableWidgetItem(found["text"])
            item.setTextAlignment(Qt.AlignmentFlag(found["alignment_value"]))
            if found["icon_asset"]:
                icon = _get_coin_icon(
                    found["icon_asset"],
                    found["icon_size"],
                    download=payload["icon_download"],
                )
                if icon:
                    item.setIcon(icon)
            if found["chart_url"]:
                item.setData(Qt.UserRole, found["chart_url"])
            if found["color"]:
                item.setForeground(QColor(found["color"]))
            if found["underline"]:
                shape = item.font()
                shape.setUnderline(True)
                item.setFont(shape)
            if found["tooltip"]:
                item.setToolTip(found["tooltip"])
            table.setItem(index, column, item)
        if row["fire"]:
            fire = QPushButton(row["fire"]["text"])
            fire.setFixedHeight(row["fire"]["height"])
            fire.setFocusPolicy(Qt.NoFocus)
            fire.setEnabled(row["fire"]["enabled"])
            fire.setStyleSheet(row["fire"]["style_sheet"])
            fire.setToolTip(row["fire"]["tooltip"])
            if row["fire"]["glow"]:
                glow = QGraphicsDropShadowEffect(fire)
                glow.setColor(QColor(row["fire"]["glow"]))
                glow.setBlurRadius(row["fire"]["glow_blur_radius"])
                glow.setOffset(*row["fire"]["glow_offset"])
                fire.setGraphicsEffect(glow)
            table.setCellWidget(index, payload["fire_column"], fire)
        if row["detail"]:
            detail = QPushButton(row["detail"]["text"])
            detail.setFixedHeight(row["detail"]["height"])
            detail.setStyleSheet(row["detail"]["style_sheet"])
            detail.setToolTip(row["detail"]["tooltip"])
            table.setCellWidget(index, payload["detail_column"], detail)
    return table


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a table the shipped table does not."""
    app()
    old_side = render_offscreen(old_table([name]), PIXEL_SIZE)
    new_side = render_offscreen(
        table_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_table(["happy"]), PIXEL_SIZE),
        new_side=render_offscreen(
            table_painted_by_the_model(model_payload("three_rows")), PIXEL_SIZE
        ),
        note="one row against three",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_table(["three_rows"]), PIXEL_SIZE),
        new_side=render_offscreen(
            table_painted_by_the_model(model_payload("empty")), PIXEL_SIZE
        ),
        note="three rows against none",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_table(["happy"]), PIXEL_SIZE),
        new_side=render_offscreen(
            table_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("happy")
    payload["rows"][0]["cells"][0]["text"] = "moved"
    with pytest.raises(AssertionError):
        table_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        table_painted_by_the_model({"rows": []})
    assert table_painted_by_the_model(model_payload("happy")) is not None


def test_the_table_declares_no_skin_of_its_own():
    """A colour the surface ships is one the table never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    assert old_table(["happy"]).styleSheet() == ""
    assert "gridline-color" not in surface.FIRE_STYLE_HEAD
    skinned = table_painted_by_the_model(model_payload("happy"))
    skinned.setStyleSheet("QTableWidget { gridline-color: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(old_table(["happy"]), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a rule the table does not set",
    )
    assert_pictures_match(
        old_side=render_widget(old_table(["happy"]), PIXEL_SIZE),
        new_side=render_widget(
            table_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


def test_the_column_widths_are_compared_as_asked_for():
    """The width a column was given differs between the two sides."""
    app()
    assert surface.FIXED_WIDTHS == dict(shipped.SCRUMMING_COLUMNS.fixed_widths)
    assert sorted(surface.FIXED_WIDTHS) == [
        surface.FIRE_COLUMN,
        surface.DETAIL_COLUMN,
    ]
    assert surface.FIXED_WIDTHS[surface.FIRE_COLUMN] == 70
    assert surface.FIXED_WIDTHS[surface.DETAIL_COLUMN] == 60


def test_the_platform_keeps_the_width_the_column_was_given():
    """The header refused the width it was given, so the ask is not the paint."""
    app()
    table = old_table(["happy"])
    built = table_painted_by_the_model(model_payload("happy"))
    for column, asked in surface.FIXED_WIDTHS.items():
        assert table.columnWidth(column) == asked, (column, asked)
        assert built.columnWidth(column) == asked, (column, asked)
    narrow = table_painted_by_the_model(model_payload("happy"))
    narrow.setColumnWidth(surface.FIRE_COLUMN, 4)
    floor = narrow.horizontalHeader().minimumSectionSize()
    assert narrow.columnWidth(surface.FIRE_COLUMN) == floor, floor
    assert floor > 4, floor
    for column, asked in surface.FIXED_WIDTHS.items():
        assert asked > floor, (column, asked, floor)


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


def test_the_header_tooltips_are_compared_as_strings():
    """The words the header explains itself with reached no pixel."""
    app()
    table = old_table(["happy"])
    model = new_model(["happy"])
    old_tips = [
        table.horizontalHeaderItem(column).toolTip()
        for column in range(table.columnCount())
    ]
    new_tips = [found["tooltip"] for found in model.headers]
    assert old_tips == new_tips
    assert len(old_tips) == surface.COLUMN_COUNT == 10
    assert old_tips[surface.DETAIL_COLUMN] == ""
    assert "Privacy: REVEALED" in old_tips[0]


def test_the_cell_tooltips_are_compared_as_strings():
    """The words a cell explains itself with reached no pixel."""
    app()
    run = drive(["happy"])
    old_tips = [found["tooltip"] for found in run["old"]["rows"][0]["cells"] if found]
    new_tips = [found["tooltip"] for found in run["new"]["rows"][0]["cells"] if found]
    assert old_tips == new_tips
    assert any(tip for tip in old_tips), old_tips


def test_the_fire_tooltip_is_compared_as_a_string():
    """The words the Fire button explains itself with reached no pixel."""
    app()
    for name in ("fold_ceiling", "ceiling_approach", "detonation", "scrum_override"):
        run = drive([name])
        assert run["old"]["rows"][0]["fire"]["tooltip"] == (
            run["new"]["rows"][0]["fire"]["tooltip"]
        ), name
        assert run["old"]["rows"][0]["fire"]["tooltip"], name


def test_the_chart_address_is_compared_as_a_string():
    """The address the Symbol cell holds reached no pixel."""
    app()
    run = drive(["happy"])
    old_url = run["old"]["rows"][0]["cells"][surface.SYMBOL_COLUMN]["url"]
    new_url = run["new"]["rows"][0]["cells"][surface.SYMBOL_COLUMN]["url"]
    assert old_url == new_url
    assert old_url.startswith("https://"), old_url
    assert drive(["unknown_exchange"])["new"]["rows"][0]["cells"][1]["url"] == ""


def test_the_idle_colour_is_compared_as_exact_text():
    """The idle colour is three equal channels, so a swap reads as no change.

    ``#888`` cannot show a channel swap however it is compared, so the
    shipped value and the surface's are compared as exact text.
    """
    app()
    assert surface.STATE_COLORS["idle"] == "#888"
    assert str(shipped.BotStatusTable.STATE_COLORS["idle"].name()) == "#888888"
    assert canon_colour("#888") == canon_colour("#888888") == "#888888"
    swapped = "#" + surface.STATE_COLORS["idle"][3:] + surface.STATE_COLORS["idle"][1:3]
    assert canon_colour(swapped) == canon_colour(surface.STATE_COLORS["idle"])
    for state, colour in surface.STATE_COLORS.items():
        assert canon_colour(colour) == canon_colour(
            shipped.BotStatusTable.STATE_COLORS[state].name()
        ), state
    assert len(surface.STATE_COLORS) == len(shipped.BotStatusTable.STATE_COLORS) == 7


def test_the_button_focus_policy_is_compared_as_a_value():
    """The Fire button took focus and scrolled the table under the operator."""
    from PySide6.QtCore import Qt

    app()
    table = old_table(["happy"])
    fire = table.cellWidget(0, surface.FIRE_COLUMN)
    detail = table.cellWidget(0, surface.DETAIL_COLUMN)
    assert fire.focusPolicy() == Qt.NoFocus
    assert surface.FOCUS_POLICY == "NoFocus"
    payload = surface.build_view_model(new_model(["happy"]))
    assert payload["rows"][0]["fire"]["focus_policy"] == surface.FOCUS_POLICY
    assert "focus_policy" not in payload["rows"][0]["detail"]
    assert detail.focusPolicy() != Qt.NoFocus


def test_the_glow_is_compared_as_asked_for():
    """The glow the button was given differs between the two sides."""
    app()
    run = drive(["happy"])
    assert (
        run["old"]["rows"][0]["fire"]["glow"] == run["new"]["rows"][0]["fire"]["glow"]
    )
    assert run["old"]["rows"][0]["fire"]["glow"] == canon_colour(
        surface.FIRE_GLOWS["scrum_armed"]
    )
    table = old_table(["happy"])
    effect = table.cellWidget(0, surface.FIRE_COLUMN).graphicsEffect()
    assert effect.blurRadius() == float(surface.GLOW_BLUR_RADIUS)
    assert isinstance(effect.blurRadius(), float)
    assert isinstance(surface.GLOW_BLUR_RADIUS, int)
    assert (effect.xOffset(), effect.yOffset()) == surface.GLOW_OFFSET
    assert drive(["phase_track"])["old"]["rows"][0]["fire"]["glow"] == ""


def test_the_masked_columns_are_compared_as_text():
    """A hidden column showed its value on one side and not the other."""
    app()
    for field in surface.PRIVACY_FIELD_BY_COL.values():
        registry().set_masked(field, True)
    run = drive(["happy"])
    both_sides_agree(run, "every column hidden")
    texts = [found["text"] for found in run["old"]["rows"][0]["cells"] if found]
    assert texts == ["****"] * 8, texts
    assert run["old"]["rows"][0]["fire"]["text"] == "****"
    assert run["new"]["rows"][0]["fire"]["text"] == "****"
    assert run["old"]["rows"][0]["detail"]["text"] == surface.DETAIL_LABEL


def warnings_from(logger_name, run):
    """Every warning one named logger emits while `run` is running.

    The handler is attached to the named logger, never through a
    capture fixture: this project's loggers do not pass their records
    up, so a fixture reading the root logger would see nothing. It is
    detached even when `run` refuses part way.
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
    target.setLevel(logging.WARNING)
    try:
        guarded(run)
    finally:
        target.removeHandler(handler)
        target.setLevel(was)
    return found


def test_the_skipped_row_writes_the_same_warning_on_both_sides():
    """A row the table refuses to paint is announced differently on one side."""
    app()
    old_said = warnings_from(
        "src.gui.widgets.bot_status_table",
        lambda: old_table(["not_scrumming"]),
    )
    new_said = warnings_from(
        surface.SKIP_LOGGER_NAME, lambda: new_model(["not_scrumming"])
    )
    assert old_said == new_said, (old_said, new_said)
    assert len(old_said) == 1, old_said
    assert "extractor" in old_said[0]
    assert "Skipping row" in old_said[0]


def test_the_warning_recorder_can_report():
    """The recorder sees nothing whatever the code says, so silence is empty."""
    said = warnings_from(
        surface.SKIP_LOGGER_NAME,
        lambda: logging.getLogger(surface.SKIP_LOGGER_NAME).warning("a seeded line"),
    )
    assert said == ["a seeded line"]
    quiet = warnings_from(surface.SKIP_LOGGER_NAME, lambda: new_model(["happy"]))
    assert quiet == []
    survived = warnings_from(
        surface.SKIP_LOGGER_NAME,
        lambda: [
            logging.getLogger(surface.SKIP_LOGGER_NAME).warning("before the refusal"),
            new_model(["state_is_a_number"]),
        ],
    )
    assert survived == ["before the refusal"]
    assert logging.getLogger(surface.SKIP_LOGGER_NAME).handlers == []


BLIND_TO_THE_PICTURE = {
    "header tooltips": "test_the_header_tooltips_are_compared_as_strings",
    "cell tooltips": "test_the_cell_tooltips_are_compared_as_strings",
    "fire tooltip": "test_the_fire_tooltip_is_compared_as_a_string",
    "chart address": "test_the_chart_address_is_compared_as_a_string",
    "idle colour": "test_the_idle_colour_is_compared_as_exact_text",
    "focus policy": "test_the_button_focus_policy_is_compared_as_a_value",
    "glow": "test_the_glow_is_compared_as_asked_for",
    "masked columns": "test_the_masked_columns_are_compared_as_text",
    "skipped-row warning": "test_the_skipped_row_writes_the_same_warning_on_both_sides",
    "column widths": "test_the_column_widths_are_compared_as_asked_for",
    "highlight": "test_the_highlight_follows_the_bot_not_the_row",
    "bot id list": "test_a_shrink_then_a_refusal_leaves_the_same_rows_on_both_sides",
    "logo request": "test_the_logo_request_is_compared_as_a_value",
    "broken chart lookup": (
        "test_a_broken_chart_registry_leaves_the_cell_plain_on_both_sides"
    ),
    "broken register": "test_a_broken_register_leaves_the_headers_empty_on_the_surface",
    "recorded calls": "test_the_recorded_calls_are_compared_as_values",
    "refusal wording": "test_the_refusal_comparison_reports_two_different_wordings",
}


def test_the_logo_request_is_compared_as_a_value():
    """Whether a logo is on this machine is hidden, so the ask is the check."""
    app()
    run = drive(["happy"])
    assert run["old_icons"] == run["new_icons"]
    assert run["old_icons"] == [[SEEDED_ICON_ASSET, surface.ICON_ASSET_SIZE_PX]]
    assert drive(["no_symbol"])["old_icons"] == []
    assert (
        drive(["three_rows"])["old_icons"]
        == [[SEEDED_ICON_ASSET, surface.ICON_ASSET_SIZE_PX]] * 3
    )


def test_the_recorded_calls_are_compared_as_values():
    """The recorded steps are a list nothing reads, so a lost step is unseen."""
    model = new_model(["three_rows"])
    names = [call[0] for call in model.calls]
    assert names.count(surface.ROW_BUILT) == 3
    assert names.count(surface.FIRE_BUILT) == 3
    assert names.count(surface.DETAIL_BUILT) == 3
    assert surface.ROW_COUNT_SET in names
    assert surface.HEADER_REFRESHED in names
    skipped = new_model(["not_scrumming"])
    assert [call[0] for call in skipped.calls].count(surface.ROW_SKIPPED) == 1
    payload = surface.build_view_model(model)
    assert payload["calls"] == [list(call) for call in model.calls]


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 17
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


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
        if isinstance(value, (surface.BotStatusTableModel, logging.Logger)):
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
        model = surface.BotStatusTableModel()
        guarded(lambda: model.update_bots(CASES[name]))
        payloads.append(surface.build_view_model(model))
    for steps in SEQUENCES.values():
        model = surface.BotStatusTableModel()
        for step in steps:
            guarded(lambda step=step: model.update_bots(CASES[step]))
        payloads.append(surface.build_view_model(model))
    pressed = surface.BotStatusTableModel()
    pressed.update_bots(CASES["three_rows"])
    pressed.on_header_clicked(0)
    pressed.on_header_clicked(surface.DETAIL_COLUMN)
    pressed.on_detail("beta")
    pressed.on_fire("beta")
    pressed.on_cell_clicked(0, surface.SYMBOL_COLUMN)
    pressed.on_cell_clicked(0, surface.MODE_COLUMN)
    payloads.append(surface.build_view_model(pressed))
    payloads.append(surface.build_view_model(surface.build_model(CASES["happy"])))
    payloads.append(surface.build_view_model(surface.build_model()))
    anchored = surface.BotStatusTableModel()
    anchored.update_bots(CASES["three_rows"])
    anchored.select_row(2)
    anchored.update_bots(CASES["one_row"])
    payloads.append(surface.build_view_model(anchored))
    payloads.append(surface.build_view_model(refusing_register_model()))
    payloads.append(surface.build_view_model(refusing_chart_model()))
    return payloads


def refusing_register_model():
    """One model built while the privacy register cannot be read."""

    def refuse():
        raise RuntimeError("register gone")

    real = surface.get_privacy_mask_registry
    surface.get_privacy_mask_registry = refuse
    try:
        return surface.BotStatusTableModel()
    finally:
        surface.get_privacy_mask_registry = real


def refusing_chart_model():
    """One model built while the chart address cannot be looked up."""

    def refuse(exchange_id, symbol):
        raise RuntimeError("chart registry gone for %s %s" % (exchange_id, symbol))

    real = surface.chart_url
    surface.chart_url = refuse
    try:
        model = surface.BotStatusTableModel()
        model.update_bots(CASES["happy"])
        return model
    finally:
        surface.chart_url = real


COVERED_ELSEWHERE = {
    "PANE_MODEL": "test_the_bridge_keeps_the_table_until_a_reset",
    "LOGGER_NAME": "test_the_surface_writes_under_the_logger_it_names",
    "CellCall": "test_the_recorded_calls_are_compared_as_values",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped table."""
    constants = surface_constants()
    assert len(constants) > 90, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_a_broken_chart_registry_leaves_the_cell_plain_on_both_sides():
    """A broken chart lookup took the whole table paint down with it."""
    app()
    model = refusing_chart_model()
    payload = surface.build_view_model(model)
    cell = payload["rows"][0]["cells"][surface.SYMBOL_COLUMN]
    assert cell["chart_url"] == ""
    assert cell["underline"] is False
    assert cell["text"] == "XRP/USD"
    assert surface.ROW_SYMBOL_LINK_FAILED in [call[0] for call in model.calls]
    quiet = surface.BotStatusTableModel()
    quiet.update_bots(CASES["happy"])
    assert surface.ROW_SYMBOL_LINK_FAILED not in [call[0] for call in quiet.calls]


def test_a_broken_register_leaves_the_headers_empty_on_the_surface():
    """A register that cannot be read left the surface with stale headers."""
    model = refusing_register_model()
    assert model.headers == []
    assert surface.HEADER_FAILED in [call[0] for call in model.calls]
    assert surface.BotStatusTableModel().headers != []


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "COLUMN_LABELS" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "columns": ("COLUMN_LABELS",),
    "column_count": ("COLUMN_COUNT",),
    "column_tooltips": ("COLUMN_TOOLTIPS",),
    "fixed_widths": ("FIXED_WIDTHS",),
    "privacy_field_by_col": ("PRIVACY_FIELD_BY_COL",),
    "state_colors": ("STATE_COLORS",),
    "default_state_color": ("DEFAULT_STATE_COLOR",),
    "revealed_glyph": ("REVEALED_GLYPH",),
    "masked_glyph": ("MASKED_GLYPH",),
    "state_masked": ("STATE_MASKED",),
    "state_revealed": ("STATE_REVEALED",),
    "headers": ("model.headers",),
    "rows": ("model.rows",),
    "row_count": ("model.rows",),
    "skipped_rows": ("model.skipped_rows",),
    "bot_ids": ("model.bot_ids",),
    "selected_bot_id": ("model.get_selected_bot_id",),
    "current_row": ("model.current_row",),
    "has_selection": ("model.has_selection",),
    "alignment": ("ALIGNMENT",),
    "alignment_value": ("ALIGNMENT_VALUE",),
    "fire_column": ("FIRE_COLUMN",),
    "detail_column": ("DETAIL_COLUMN",),
    "button_columns": ("BUTTON_COLUMNS",),
    "symbol_column": ("SYMBOL_COLUMN",),
    "mode_column": ("MODE_COLUMN",),
    "target_btc_column": ("TARGET_BTC_COLUMN",),
    "target_eth_column": ("TARGET_ETH_COLUMN",),
    "ammo_column": ("AMMO_COLUMN",),
    "fire_paths": ("FIRE_PATHS",),
    "fire_styles": ("FIRE_STYLES",),
    "fire_glows": ("FIRE_GLOWS",),
    "fire_label": ("FIRE_LABEL",),
    "fire_mask_field": ("FIRE_MASK_FIELD",),
    "detail_label": ("DETAIL_LABEL",),
    "detail_style": ("DETAIL_STYLE",),
    "detail_tooltip": ("DETAIL_TIP",),
    "button_height": ("BUTTON_HEIGHT_PX",),
    "focus_policy": ("FOCUS_POLICY",),
    "glow_blur_radius": ("GLOW_BLUR_RADIUS",),
    "glow_offset": ("GLOW_OFFSET",),
    "glows": ("model.glows",),
    "icon_size": ("ICON_ASSET_SIZE_PX",),
    "icon_download": ("ICON_DOWNLOAD",),
    "link_color": ("LINK_COLOR",),
    "link_underline": ("LINK_UNDERLINE",),
    "browser_new_window": ("BROWSER_NEW_WINDOW",),
    "opened_urls": ("model.opened_urls",),
    "detail_clicks": ("model.detail_clicks",),
    "fire_clicks": ("model.fire_clicks",),
    "mode_scrumming": ("MODE_SCRUMMING",),
    "active_states": ("ACTIVE_STATES",),
    "unknown_state_text": ("UNKNOWN_STATE_TEXT",),
    "no_target_text": ("NO_TARGET_TEXT",),
    "skip_bot_id_length": ("SKIP_BOT_ID_LENGTH",),
    "skip_bot_id_missing": ("SKIP_BOT_ID_MISSING",),
    "ceiling_hard_stop_ratio": ("CEILING_HARD_STOP_RATIO",),
    "ceiling_approach_ratio": ("CEILING_APPROACH_RATIO",),
    "percent_scale": ("PERCENT_SCALE",),
    "default_fold_taper": ("DEFAULT_FOLD_TAPER",),
    "default_detonation_timeframe": ("DEFAULT_DETONATION_TIMEFRAME",),
    "default_quote_to_usd": ("DEFAULT_QUOTE_TO_USD",),
    "fire_tooltips": (
        "FIRE_TIP_SCRUM_SOLID",
        "FIRE_TIP_SCRUM_OUTLINE",
        "FIRE_TIP_FOLD_CEILING",
        "FIRE_TIP_FOLD_SOLID",
        "FIRE_TIP_FOLD_OUTLINE",
        "FIRE_TIP_PHASE_FIRE",
        "FIRE_TIP_PHASE_TRACK",
        "FIRE_TIP_PHASE_SEARCH",
        "FIRE_TIP_NOT_SCRUMMING",
    ),
    "fire_inactive_tooltip_format": ("FIRE_TIP_INACTIVE_FORMAT",),
    "header_text_format": ("HEADER_TEXT_FORMAT",),
    "header_state_tip_format": ("HEADER_STATE_TIP_FORMAT",),
    "mode_tip_format": ("MODE_TIP_FORMAT",),
    "link_tip_format": ("LINK_TIP_FORMAT",),
    "blockers_tip_format": ("BLOCKERS_TIP_FORMAT",),
    "blockers_separator": ("BLOCKERS_SEPARATOR",),
    "ceiling_reached_format": ("CEILING_REACHED_FORMAT",),
    "ceiling_approach_format": ("CEILING_APPROACH_FORMAT",),
    "ceiling_normal_format": ("CEILING_NORMAL_FORMAT",),
    "detonation_format": ("DETONATION_FORMAT",),
    "skip_log_format": ("SKIP_LOG_FORMAT",),
    "chart_url_skipped_log": ("CHART_URL_SKIPPED_LOG",),
    "chart_open_failed_log": ("CHART_OPEN_FAILED_LOG",),
    "fire_style_head": ("FIRE_STYLE_HEAD",),
    "no_glow": ("NO_GLOW",),
    "no_blockers_text": ("NO_BLOCKERS_TEXT",),
    "empty_text": ("EMPTY_TEXT",),
    "symbol_separator": ("SYMBOL_SEPARATOR",),
    "quote_btc": ("QUOTE_BTC",),
    "quote_eth": ("QUOTE_ETH",),
    "no_selection_row": ("NO_SELECTION_ROW",),
    "no_selection_bot_id": ("NO_SELECTION_BOT_ID",),
    "no_target_value": ("NO_TARGET_VALUE",),
    "no_price": ("NO_PRICE",),
    "no_holdings": ("NO_HOLDINGS",),
    "no_trades": ("NO_TRADES",),
    "sorting_enabled": ("SORTING_ENABLED",),
    "selection_behavior": ("SELECTION_BEHAVIOR",),
    "edit_triggers": ("EDIT_TRIGGERS",),
    "alternating_row_colors": ("ALTERNATING_ROW_COLORS",),
    "vertical_header_visible": ("VERTICAL_HEADER_VISIBLE",),
    "header_resize_mode": ("HEADER_RESIZE_MODE",),
    "fixed_resize_mode": ("FIXED_RESIZE_MODE",),
    "skin": ("SKIN",),
    "style_sheet": ("STYLE_SHEET",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "actions": ("ACTIONS",),
    "logger_name": ("LOGGER_NAME",),
    "skip_logger_name": ("SKIP_LOGGER_NAME",),
    "calls": ("model.calls",),
}

FREE_SHAPE_KEYS = ("headers", "rows", "glows", "calls")


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
    if key in FREE_SHAPE_KEYS:
        return len(value) == len(resolve_source(sources[0], model, held))
    if key == "row_count":
        return value == len(resolve_source(sources[0], model, held))
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
    model = new_model(["three_rows"])
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    fresh = new_model(["three_rows"])
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
    model = new_model(["happy"])
    payload = surface.build_view_model(model)
    assert backed("alignment", payload["alignment"], ("ALIGNMENT",), model)
    assert not backed("alignment", "AlignLeft", ("ALIGNMENT",), model)
    assert not backed("columns", ["Bot ID"], ("COLUMN_LABELS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("row_count", 9, ("model.rows",), model)
    assert not backed("current_row", 9, ("model.current_row",), model)


# What the shipped module keeps between tables


def test_the_shipped_module_changes_no_value_the_next_table_reads():
    """One table left a changed value behind for the next one."""
    app()
    before = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    before_colors = {
        state: colour.name()
        for state, colour in shipped.BotStatusTable.STATE_COLORS.items()
    }
    for name in CASES:
        guarded(lambda name=name: old_table([name]))
    after = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    assert after == before
    assert {
        state: colour.name()
        for state, colour in shipped.BotStatusTable.STATE_COLORS.items()
    } == before_colors
    assert shipped.SCRUMMING_COLUMNS.labels == surface.COLUMN_LABELS


def test_the_shipped_table_writes_to_the_process_wide_privacy_register():
    """The shipped table changes no shared state, so no test can disturb another."""
    app()
    live = registry()
    assert live.is_masked("bot_table.bot_id") is False
    old_table(["happy"])._on_header_clicked(0)
    assert live.is_masked("bot_table.bot_id") is True
    assert registry() is live


def test_each_test_is_given_its_own_register():
    """Two tests share one register, so the order they run in decides both."""
    from src.core import privacy_mask_registry as registry_module

    assert registry() is registry_module._SINGLETON
    assert registry().is_masked("bot_table.ammo") is False
    registry().set_masked("bot_table.ammo", True)


def test_each_test_is_given_its_own_register_again():
    """The mask the test above set survived into this one."""
    assert registry().is_masked("bot_table.ammo") is False


def test_no_test_writes_a_settings_file(own_privacy_registry, tmp_path):
    """A header press wrote the operator's live settings file."""
    app()
    run = header_press([1])
    assert not (tmp_path / "settings.json").exists()
    assert list(tmp_path.iterdir()) == []
    assert run["old_state"]["bot_table.symbol"] is True
    assert own_privacy_registry.is_masked("bot_table.symbol") is True


def test_the_surface_keeps_no_value_between_two_models():
    """One model left a changed value behind for the next one."""
    first = new_model(["three_rows"])
    second = surface.BotStatusTableModel()
    assert second.rows == []
    assert second.bot_ids == []
    assert second.calls != first.calls
    assert first.rows is not second.rows


# The bridge


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    payload = surface.build_view_model(new_model(["three_rows"]))
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_bot_status_table_method():
    """The renderer cannot reach the bot table over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "bot_status_table.state"
    assert registered[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )
    assert answer["ok"] is True
    assert answer["result"]["columns"] == list(surface.COLUMN_LABELS)


def test_the_bridge_import_list_is_alphabetical():
    """The bridge import list drifted out of order."""
    from src.core import desktop_bridge

    source = Path(desktop_bridge.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            names = [alias.name for alias in node.names]
    assert names == sorted(names), names
    assert "bot_status_table_surface" in names
    assert names.index("bot_selection_surface") + 1 == names.index(
        "bot_status_table_surface"
    )


def test_the_bridge_keeps_the_table_until_a_reset():
    """The table forgot its rows between two calls, or kept them past a reset."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 5, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    filled = ask({"statuses": CASES["three_rows"]})
    assert filled["row_count"] == 3
    assert ask({})["row_count"] == 3
    assert ask({"reset": True})["row_count"] == 0
    assert surface.PANE_MODEL.rows == []


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


def test_the_surface_writes_under_the_logger_it_names():
    """The surface writes under a name no operator log is collected from."""
    assert surface.LOGGER_NAME == "acervator.gui"
    assert surface.logger.name == surface.LOGGER_NAME
    assert shipped.logger.name == surface.LOGGER_NAME
    assert surface.SKIP_LOGGER_NAME == surface.__name__


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
    "json.dumps({'id': 1, 'method': 'bot_status_table.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import bot_status_table_surface as s\n"
    "model = s.build_model([{'bot_id': 'bot-alpha-0001', 'symbol': 'XRP/USD',\n"
    "    'mode': 'scrumming', 'state': 'running', 'exchange': 'coinbase',\n"
    "    'current_holdings': 104.8, 'quote_to_usd': 1.0,\n"
    "    'live_target_balance': 50.0, 'target_balance': 40.0,\n"
    "    'armed_action': 'scrum', 'auto_fire': {'scrum_armed': True},\n"
    "    'stats': {'total_trades': 7, 'position_value': 149.85,\n"
    "        'current_price': 1.43}}])\n"
    "payload = s.build_view_model(model)\n"
    "row = payload['rows'][0]\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'columns': payload['columns'],\n"
    "    'row_count': payload['row_count'],\n"
    "    'texts': [c['text'] for c in row['cells'] if c],\n"
    "    'colors': [c['color'] for c in row['cells'] if c],\n"
    "    'url': row['cells'][1]['chart_url'],\n"
    "    'fire_path': row['fire']['path'],\n"
    "    'fire_style': row['fire']['style_sheet'],\n"
    "    'headers': [h['text'] for h in payload['headers']],\n"
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
    """Reaching the bot table pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["columns"] == list(surface.COLUMN_LABELS)
    assert result["row_count"] == 0
    assert result["headers"][0]["text"] == "● Bot ID"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_paints_the_table_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["row_count"] == 1
    assert answered["columns"] == list(surface.COLUMN_LABELS)
    assert answered["texts"] == [
        "bot-alpha-0001",
        "XRP/USD",
        "scrumming",
        "7",
        "$50.0000",
        "pending",
        "pending",
        "$99.8640",
    ]
    assert answered["colors"][1] == surface.LINK_COLOR
    assert answered["colors"][2] == surface.STATE_COLORS["running"]
    assert answered["url"].endswith("/XRP-USD")
    assert answered["fire_path"] == surface.FIRE_PATH_SCRUM_SOLID
    assert answered["fire_style"] == surface.FIRE_STYLE_SCRUM_SOLID
    assert answered["headers"][0] == "● Bot ID"
    assert answered["calls"] > 5


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_paints_the_table():
    """The Qt block let the shipped table through.

    The shipped file guards its own Qt import and sets ``_HAS_QT``
    False, but its package imports Qt unguarded, so the module cannot
    be reached at all without Qt and that fallback never runs.
    """
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui.widgets import bot_status_table as t\n"
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
    assert "_HAS_QT" in TABLE_PATH.read_text(encoding="utf-8")


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
    table_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(TABLE_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in table_imports), table_imports


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
