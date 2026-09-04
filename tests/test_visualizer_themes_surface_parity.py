"""The shipped visualizer theme table and the Qt-free surface, side by side.

A failure means the view model carries a different theme, a different
tier palette, a different colour, a different transparency, a different
shown name, a different tier for a balance or a different refusal than
``src.gui.visualizer.themes`` ships.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import visualizer_themes_surface as surface
from src.gui.visualizer import themes as shipped
from tests.fixtures.host_fonts import skip_unless_no_fonts, skip_unless_real_fonts
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src/gui/visualizer/themes.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/visualizer_themes_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
WIRED_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
TOPIC_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"

METHOD_NAME = "visualizer_themes.state"

PIXEL_SIZE = (700, 320)

THEME_TOTAL = 4
TIER_TOTAL = 4
THEME_FIELD_TOTAL = 10
TIER_FIELD_TOTAL = 6

# Every canvas theme, in the order the shipped table builds them.
EXPECTED_THEME_NAMES = ("nebula", "matrix", "quantum", "ocean")

# Every tier palette, in the order the shipped table builds them.
EXPECTED_TIER_NAMES = ("harvest", "great", "bumper", "ekthelius")

# Every field of a theme row, in the order the shipped table writes them.
EXPECTED_THEME_FIELDS = (
    "name",
    "bg",
    "accent",
    "accent2",
    "success",
    "warning",
    "error",
    "text",
    "grid",
    "particle",
)

# Every field of a tier row, in the order the shipped table writes them.
EXPECTED_TIER_FIELDS = ("name", "base", "shadow", "highlight", "accent", "glow")

# Every value of every canvas theme, typed out here rather than read
# from either module. Neither side can satisfy this table by copying the
# other, and an edit made to both files together is still reported.
EXPECTED_THEMES = {
    "nebula": {
        "name": "Nebula",
        "bg": "#080414ff",
        "accent": "#7850ffff",
        "accent2": "#ff3cb4ff",
        "success": "#00ffa0ff",
        "warning": "#ffc800ff",
        "error": "#ff2850ff",
        "text": "#c8c8f0ff",
        "grid": "#3c287828",
        "particle": "#b478ff50",
    },
    "matrix": {
        "name": "Matrix",
        "bg": "#000800ff",
        "accent": "#00ff41ff",
        "accent2": "#00b42dff",
        "success": "#00ff64ff",
        "warning": "#c8ff00ff",
        "error": "#ff0000ff",
        "text": "#00dc37ff",
        "grid": "#003c0f28",
        "particle": "#00ff413c",
    },
    "quantum": {
        "name": "Quantum Circuit",
        "bg": "#0a0f19ff",
        "accent": "#00c8ffff",
        "accent2": "#00ffc8ff",
        "success": "#00ff88ff",
        "warning": "#ffb400ff",
        "error": "#ff3250ff",
        "text": "#b4dcffff",
        "grid": "#003c5a28",
        "particle": "#00c8ff3c",
    },
    "ocean": {
        "name": "Deep Ocean",
        "bg": "#050a1eff",
        "accent": "#0096ffff",
        "accent2": "#00dcb4ff",
        "success": "#00e6aaff",
        "warning": "#ffc832ff",
        "error": "#ff3c5aff",
        "text": "#a0c8f0ff",
        "grid": "#00285028",
        "particle": "#0078c832",
    },
}

# Every value of every tier palette, typed out here as well.
EXPECTED_TIERS = {
    "harvest": {
        "name": "Harvest",
        "base": "#50b46eff",
        "shadow": "#28648cff",
        "highlight": "#b4dc82ff",
        "accent": "#d2f0a0ff",
        "glow": "#78dc96ff",
    },
    "great": {
        "name": "Great",
        "base": "#3cc8b4ff",
        "shadow": "#146482ff",
        "highlight": "#96f0d2ff",
        "accent": "#c8fae6ff",
        "glow": "#5ae6c8ff",
    },
    "bumper": {
        "name": "Bumper",
        "base": "#dc9646ff",
        "shadow": "#6e3c78ff",
        "highlight": "#fadc8cff",
        "accent": "#ffebaaff",
        "glow": "#f0b45aff",
    },
    "ekthelius": {
        "name": "Ekthelius",
        "base": "#c8aa50ff",
        "shadow": "#462882ff",
        "highlight": "#fae6a0ff",
        "accent": "#dcb4ffff",
        "glow": "#e6c878ff",
    },
}

EXPECTED_THEME_DISPLAY_NAMES = {
    "nebula": "Nebula",
    "matrix": "Matrix",
    "quantum": "Quantum Circuit",
    "ocean": "Deep Ocean",
}

EXPECTED_TIER_DISPLAY_NAMES = {
    "harvest": "Harvest",
    "great": "Great",
    "bumper": "Bumper",
    "ekthelius": "Ekthelius",
}

EXPECTED_CEILINGS_USD = {"harvest": 100, "great": 1_000, "bumper": 10_000}

EXPECTED_TOP_TIER = "ekthelius"

THEME_COLOUR_FIELDS = tuple(f for f in EXPECTED_THEME_FIELDS if f != "name")
TIER_COLOUR_FIELDS = tuple(f for f in EXPECTED_TIER_FIELDS if f != "name")

THEME_FIELD_CASES = [
    (theme, field) for theme in EXPECTED_THEME_NAMES for field in EXPECTED_THEME_FIELDS
]
TIER_FIELD_CASES = [
    (tier, field) for tier in EXPECTED_TIER_NAMES for field in EXPECTED_TIER_FIELDS
]

# The awkward names a caller may ask for. None is a theme and none is a
# tier.
UNKNOWN_NAMES = {
    "empty": "",
    "zero": "0",
    "negative": "-1",
    "a_thousand_million": "1000000000",
    "one_billionth": "1e-09",
    "infinity": "inf",
    "minus_infinity": "-inf",
    "not_a_number": "nan",
    "unicode": "Δ→⚡",
    "long": "X" * 200,
    "markup": "<b>nebula</b>",
    "apostrophe": "it's",
    "uppercase": "NEBULA",
    "spaced": " nebula ",
    "newline": "nebula\nmatrix",
    "dotted": "themes.nebula",
    "display": "Deep Ocean",
    "private": "_TIER_PALETTES",
    "dunder": "__all__",
    "quoted": '"nebula"',
}

# The values a caller may send where a name belongs.
NON_STRING_NAMES: tuple = (None, 0, -1, 9.5, True, [], ["nebula"], {}, (), b"nebula")

# Every balance the tier mapping may be asked for, and what each is.
NUMBER_CASES = {
    "zero": 0,
    "zero_as_a_decimal": 0.0,
    "negative": -1,
    "one_billionth": 1e-9,
    "under_the_first_ceiling": 99.99,
    "at_the_first_ceiling": 100,
    "at_the_first_ceiling_as_a_decimal": 100.0,
    "under_the_second_ceiling": 999.99,
    "at_the_second_ceiling": 1_000,
    "under_the_third_ceiling": 9_999.99,
    "at_the_third_ceiling": 10_000,
    "a_thousand_million": 1_000_000_000,
    "infinity": math.inf,
    "minus_infinity": -math.inf,
    "not_a_number": math.nan,
    "true": True,
    "false": False,
    "empty_text": "",
    "number_as_text": "100",
    "unicode_text": "Δ→⚡",
    "long_text": "X" * 200,
    "markup_text": "<b>100</b>",
    "apostrophe_text": "it's",
    "newline_text": "100\n200",
    "uppercase_text": "HARVEST",
    "nothing": None,
    "empty_list": [],
    "empty_table": {},
    "empty_tuple": (),
    "bytes": b"100",
}

# The tier every balance above maps to, typed out here.
EXPECTED_TIERS_FOR_NUMBERS = {
    "zero": "harvest",
    "zero_as_a_decimal": "harvest",
    "negative": "harvest",
    "one_billionth": "harvest",
    "under_the_first_ceiling": "harvest",
    "at_the_first_ceiling": "great",
    "at_the_first_ceiling_as_a_decimal": "great",
    "under_the_second_ceiling": "great",
    "at_the_second_ceiling": "bumper",
    "under_the_third_ceiling": "bumper",
    "at_the_third_ceiling": "ekthelius",
    "a_thousand_million": "ekthelius",
    "infinity": "ekthelius",
    "minus_infinity": "harvest",
    "not_a_number": "ekthelius",
    "true": "harvest",
    "false": "harvest",
}

REFUSED_NUMBER_CASES = tuple(
    name for name in NUMBER_CASES if name not in EXPECTED_TIERS_FOR_NUMBERS
)

ANSWERED_NUMBER_CASES = tuple(EXPECTED_TIERS_FOR_NUMBERS)

REFUSAL_FORMAT = "'<' not supported between instances of %r and 'int'"

# The three colours whose red, green and blue are not all different. A
# swap of two matching channels paints the same pixel, so each is read
# off both sides as text instead.
EQUAL_CHANNEL_COLOURS = (
    ("themes", "nebula", "text"),
    ("themes", "matrix", "bg"),
    ("themes", "matrix", "error"),
)

# The two pairs inside one theme whose red, green and blue match and
# whose transparency does not.
NEAR_REPEATED_COLOURS = (
    ("matrix", "accent", "particle"),
    ("quantum", "accent", "particle"),
)

# The eight colours that are partly see-through.
SEE_THROUGH_TOTAL = 8

TIER_PALETTE_READERS = 0


# The shipped tables, put back after every test


def _copied_qcolor_table(table):
    """One shipped table copied row by row, colours included."""
    from PySide6.QtGui import QColor

    return {
        key: {
            field: (value if isinstance(value, str) else QColor(value))
            for field, value in row.items()
        }
        for key, row in table.items()
    }


PRISTINE_THEMES = _copied_qcolor_table(shipped.THEMES)
PRISTINE_TIERS = _copied_qcolor_table(shipped.TIER_PALETTES)


def restore_shipped_tables():
    """Put both shipped tables back to what the shipped module defined."""
    for live, pristine in (
        (shipped.THEMES, PRISTINE_THEMES),
        (shipped.TIER_PALETTES, PRISTINE_TIERS),
    ):
        for key in [key for key in live if key not in pristine]:
            del live[key]
        for key, row in pristine.items():
            live.setdefault(key, {})
            live[key].clear()
            live[key].update(row)


@pytest.fixture(autouse=True)
def shipped_tables_unchanged():
    """Restore both shipped tables before and after every test in this file."""
    restore_shipped_tables()
    yield
    restore_shipped_tables()


# The two sides, read into one shape


def hex_from_qcolor(colour):
    """One shipped colour as the eight-digit `#rrggbbaa` text."""
    return "#%02x%02x%02x%02x" % (
        colour.red(),
        colour.green(),
        colour.blue(),
        colour.alpha(),
    )


def shipped_row(table, key, fields):
    """One shipped row, every colour turned into `#rrggbbaa` text."""
    row = table[key]
    return {
        field: (
            row[field] if isinstance(row[field], str) else hex_from_qcolor(row[field])
        )
        for field in fields
    }


def shipped_themes():
    """Every shipped canvas theme as text."""
    return {
        key: shipped_row(shipped.THEMES, key, EXPECTED_THEME_FIELDS)
        for key in shipped.THEMES
    }


def shipped_tiers():
    """Every shipped tier palette as text."""
    return {
        key: shipped_row(shipped.TIER_PALETTES, key, EXPECTED_TIER_FIELDS)
        for key in shipped.TIER_PALETTES
    }


def surface_themes():
    """Every surface canvas theme as text."""
    return {key: dict(row) for key, row in surface.THEMES.items()}


def surface_tiers():
    """Every surface tier palette as text."""
    return {key: dict(row) for key, row in surface.TIER_PALETTES.items()}


def outcome(call, value):
    """What one side did with `value`: answered with what, or refused how."""
    try:
        return {"did": "answered", "value": repr(call(value))}
    except Exception as refused:
        return {
            "did": "refused",
            "error": type(refused).__name__,
            "message": str(refused),
        }


def shipped_snapshot():
    """Everything the shipped module holds, in one comparable shape."""
    return {
        "themes": shipped_themes(),
        "theme_names": list(shipped.THEMES),
        "tier_palettes": shipped_tiers(),
        "tier_names": list(shipped.TIER_PALETTES),
        "theme_field_order": {key: list(row) for key, row in shipped.THEMES.items()},
        "tier_field_order": {
            key: list(row) for key, row in shipped.TIER_PALETTES.items()
        },
        "tiers_for_numbers": {
            name: outcome(shipped._tier_from_target_balance, value)
            for name, value in NUMBER_CASES.items()
        },
        "balance_text": {name: repr(value) for name, value in NUMBER_CASES.items()},
    }


def surface_snapshot():
    """Everything the surface holds, in the same shape."""
    return {
        "themes": surface_themes(),
        "theme_names": list(surface.THEME_NAMES),
        "tier_palettes": surface_tiers(),
        "tier_names": list(surface.TIER_NAMES),
        "theme_field_order": {key: list(row) for key, row in surface.THEMES.items()},
        "tier_field_order": {
            key: list(row) for key, row in surface.TIER_PALETTES.items()
        },
        "tiers_for_numbers": {
            name: outcome(surface.tier_for_target_balance, value)
            for name, value in NUMBER_CASES.items()
        },
        "balance_text": {name: repr(value) for name, value in NUMBER_CASES.items()},
    }


def digest(payload):
    """A stable hash over one side's whole answer."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
    ).hexdigest()


def differences(left, right, trail=""):
    """Every place two snapshots hold a different value, named by its path."""
    found = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                found.append("%s/%s" % (trail, key))
                continue
            found.extend(differences(left[key], right[key], "%s/%s" % (trail, key)))
        return found
    if repr(left) != repr(right):
        found.append("%s: %r against %r" % (trail, left, right))
    return found


def app():
    """The process application object every render needs."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


# The panel painted from one side's colours

SWATCH = 44

SWATCH_ORDER = tuple("theme_" + field for field in THEME_COLOUR_FIELDS) + tuple(
    "tier_" + field for field in TIER_COLOUR_FIELDS
)


def shipped_paint_values(theme_name, tier_name):
    """One shipped theme and one shipped tier as four numbers per colour."""
    theme_row = shipped.THEMES[theme_name]
    tier_row = shipped.TIER_PALETTES[tier_name]
    values = {
        "theme_shown_name": theme_row["name"],
        "tier_shown_name": tier_row["name"],
    }
    for field in THEME_COLOUR_FIELDS:
        colour = theme_row[field]
        values["theme_" + field] = [
            colour.red(),
            colour.green(),
            colour.blue(),
            colour.alpha(),
        ]
    for field in TIER_COLOUR_FIELDS:
        colour = tier_row[field]
        values["tier_" + field] = [
            colour.red(),
            colour.green(),
            colour.blue(),
            colour.alpha(),
        ]
    return sealed(values)


def surface_paint_values(theme_name, tier_name):
    """One surface theme and one surface tier as four numbers per colour."""
    theme_row = surface.THEMES[theme_name]
    tier_row = surface.TIER_PALETTES[tier_name]
    values = {
        "theme_shown_name": theme_row["name"],
        "tier_shown_name": tier_row["name"],
    }
    for field in THEME_COLOUR_FIELDS:
        values["theme_" + field] = list(surface.channels(theme_row[field]))
    for field in TIER_COLOUR_FIELDS:
        values["tier_" + field] = list(surface.channels(tier_row[field]))
    return sealed(values)


def rgba_text(parts):
    """One colour as the `rgba(...)` text a style sheet reads."""
    return "rgba(%d, %d, %d, %d)" % tuple(parts)


def build_panel(values):
    """One window painted from one side's colours, and from nothing else.

    A heading in the theme's own text colour on its own background, a
    caption in the tier's base colour, and one swatch for each of the
    fourteen colours over a white ground so a partly see-through colour
    shows its transparency. `values` is the only source, so the same
    call on the two sides is the parity comparison.
    """
    from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

    unaltered(values)
    app()
    root = QWidget()
    root.setStyleSheet("QWidget { background: #ffffff; }")
    outer = QVBoxLayout(root)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(6)

    heading = QLabel(values["theme_shown_name"])
    heading.setStyleSheet(
        "QLabel { background: %s; color: %s; font-size: 24px; padding: 4px; }"
        % (rgba_text(values["theme_bg"]), rgba_text(values["theme_text"]))
    )
    outer.addWidget(heading)

    caption = QLabel(values["tier_shown_name"])
    caption.setStyleSheet(
        "QLabel { background: %s; color: %s; font-size: 16px; padding: 3px; }"
        % (rgba_text(values["tier_shadow"]), rgba_text(values["tier_highlight"]))
    )
    outer.addWidget(caption)

    grid = QGridLayout()
    grid.setSpacing(4)
    for index, key in enumerate(SWATCH_ORDER):
        cell = QFrame()
        cell.setFixedSize(SWATCH, SWATCH)
        cell.setStyleSheet(
            "QFrame { background: %s; border: 4px solid %s; }"
            % (rgba_text(values[key]), rgba_text(values["theme_accent2"]))
        )
        grid.addWidget(cell, index // 7, index % 7)
    outer.addLayout(grid)
    return root


def colour_count(image):
    """How many different colours one render painted."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return len(seen)


# The two sides, value for value


@pytest.mark.parametrize("theme,field", THEME_FIELD_CASES)
def test_every_theme_field_carries_the_shipped_value(theme, field):
    """A canvas theme's value differs between the two sides."""
    old = shipped_themes()[theme][field]
    new = surface.THEMES[theme][field]
    assert new == old, "%s.%s: shipped %r, surface %r" % (theme, field, old, new)


@pytest.mark.parametrize("theme,field", THEME_FIELD_CASES)
def test_every_theme_field_matches_the_value_typed_here(theme, field):
    """A canvas theme's value was changed on both sides together."""
    assert surface.THEMES[theme][field] == EXPECTED_THEMES[theme][field]
    assert shipped_themes()[theme][field] == EXPECTED_THEMES[theme][field]


@pytest.mark.parametrize("tier,field", TIER_FIELD_CASES)
def test_every_tier_field_carries_the_shipped_value(tier, field):
    """A tier palette's value differs between the two sides."""
    old = shipped_tiers()[tier][field]
    new = surface.TIER_PALETTES[tier][field]
    assert new == old, "%s.%s: shipped %r, surface %r" % (tier, field, old, new)


@pytest.mark.parametrize("tier,field", TIER_FIELD_CASES)
def test_every_tier_field_matches_the_value_typed_here(tier, field):
    """A tier palette's value was changed on both sides together."""
    assert surface.TIER_PALETTES[tier][field] == EXPECTED_TIERS[tier][field]
    assert shipped_tiers()[tier][field] == EXPECTED_TIERS[tier][field]


def test_the_two_sides_differ_nowhere():
    """The two sides hold a different value somewhere."""
    found = differences(shipped_snapshot(), surface_snapshot())
    assert found == [], found


def test_the_two_sides_hash_the_same():
    """The two whole answers hash apart."""
    old = digest(shipped_snapshot())
    new = digest(surface_snapshot())
    assert new == old, "shipped %s, surface %s" % (old, new)


def test_the_sample_hashes_are_reported():
    """A sample hash is missing or is not a hash."""
    samples = {
        "whole_answer": digest(shipped_snapshot()),
        "themes": digest(shipped_themes()),
        "tier_palettes": digest(shipped_tiers()),
        "nebula": digest(shipped_themes()["nebula"]),
        "harvest": digest(shipped_tiers()["harvest"]),
    }
    for name, value in samples.items():
        assert len(value) == 64, (name, value)
        assert set(value) <= set("0123456789abcdef"), (name, value)
    assert len(set(samples.values())) == len(samples), samples
    for name, value in samples.items():
        counterpart = {
            "whole_answer": digest(surface_snapshot()),
            "themes": digest(surface_themes()),
            "tier_palettes": digest(surface_tiers()),
            "nebula": digest(surface_themes()["nebula"]),
            "harvest": digest(surface_tiers()["harvest"]),
        }[name]
        assert counterpart == value, name


def test_two_different_real_inputs_hash_apart():
    """The hash gives one value for every input, so it tells nothing apart.

    Two real themes and two real tiers, one of each taken from each
    side. A pass proves the hash reports a difference, so the matches
    above are not green by being unable to fail.
    """
    assert digest(shipped_themes()["nebula"]) != digest(surface_themes()["matrix"])
    assert digest(shipped_tiers()["harvest"]) != digest(surface_tiers()["bumper"])
    assert digest(shipped_themes()["quantum"]) != digest(surface_tiers()["great"])


def test_the_same_input_hashes_the_same_twice():
    """The hash moves between two runs over one input."""
    assert digest(surface_snapshot()) == digest(surface_snapshot())
    assert digest(shipped_themes()) == digest(shipped_themes())
    assert digest(surface_themes()["ocean"]) == digest(surface_themes()["ocean"])


def test_a_whole_number_and_a_decimal_are_told_apart():
    """A whole number and a decimal read alike, so a swap went unseen."""
    assert 100 == 100.0
    assert repr(100) != repr(100.0)
    assert digest({"balance": repr(100)}) != digest({"balance": repr(100.0)})
    assert surface.tier_for_target_balance(100) == "great"
    assert surface.tier_for_target_balance(100.0) == "great"
    assert shipped._tier_from_target_balance(100) == "great"
    payload = surface.build_view_model(target_balance=100)
    assert payload["target_balance_text"] == "100"
    assert surface.build_view_model(target_balance=100.0)["target_balance_text"] == (
        "100.0"
    )


def test_two_not_a_numbers_are_compared_as_text():
    """Not-a-number compared to itself reported a difference that is not one."""
    assert math.nan != math.nan
    assert repr(math.nan) == repr(math.nan)
    old = outcome(shipped._tier_from_target_balance, math.nan)
    new = outcome(surface.tier_for_target_balance, math.nan)
    assert new == old, (old, new)
    assert new == {"did": "answered", "value": "'ekthelius'"}
    assert surface.build_view_model(target_balance=math.nan)["tier"] == "ekthelius"
    assert surface.build_view_model(target_balance=math.nan)[
        "target_balance_text"
    ] == repr(math.nan)


def test_the_theme_names_and_their_order_match():
    """The canvas themes came back in a different order or a different set."""
    assert list(shipped.THEMES) == list(EXPECTED_THEME_NAMES)
    assert list(surface.THEME_NAMES) == list(EXPECTED_THEME_NAMES)
    assert list(surface.THEMES) == list(shipped.THEMES)
    assert len(surface.THEMES) == THEME_TOTAL


def test_the_tier_names_and_their_order_match():
    """The tier palettes came back in a different order or a different set."""
    assert list(shipped.TIER_PALETTES) == list(EXPECTED_TIER_NAMES)
    assert list(surface.TIER_NAMES) == list(EXPECTED_TIER_NAMES)
    assert list(surface.TIER_PALETTES) == list(shipped.TIER_PALETTES)
    assert len(surface.TIER_PALETTES) == TIER_TOTAL


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_every_theme_row_keeps_the_shipped_field_order(theme):
    """A theme's fields are in a different order on the two sides."""
    assert list(shipped.THEMES[theme]) == list(EXPECTED_THEME_FIELDS)
    assert list(surface.THEMES[theme]) == list(EXPECTED_THEME_FIELDS)
    assert len(surface.THEMES[theme]) == THEME_FIELD_TOTAL


@pytest.mark.parametrize("tier", EXPECTED_TIER_NAMES)
def test_every_tier_row_keeps_the_shipped_field_order(tier):
    """A tier's fields are in a different order on the two sides."""
    assert list(shipped.TIER_PALETTES[tier]) == list(EXPECTED_TIER_FIELDS)
    assert list(surface.TIER_PALETTES[tier]) == list(EXPECTED_TIER_FIELDS)
    assert len(surface.TIER_PALETTES[tier]) == TIER_FIELD_TOTAL


def test_the_shown_names_match():
    """A shown name differs between the two sides."""
    assert surface.DISPLAY_NAMES == EXPECTED_THEME_DISPLAY_NAMES
    assert surface.TIER_DISPLAY_NAMES == EXPECTED_TIER_DISPLAY_NAMES
    for key, shown in EXPECTED_THEME_DISPLAY_NAMES.items():
        assert shipped.THEMES[key]["name"] == shown, key
    for key, shown in EXPECTED_TIER_DISPLAY_NAMES.items():
        assert shipped.TIER_PALETTES[key]["name"] == shown, key


def test_the_colour_fields_are_the_field_names_without_the_shown_name():
    """The colour list kept the shown name, or dropped a colour."""
    assert surface.NAME_FIELD == "name"
    assert surface.THEME_COLOUR_FIELDS == THEME_COLOUR_FIELDS
    assert surface.TIER_COLOUR_FIELDS == TIER_COLOUR_FIELDS
    assert len(surface.THEME_COLOUR_FIELDS) == THEME_FIELD_TOTAL - 1
    assert len(surface.TIER_COLOUR_FIELDS) == TIER_FIELD_TOTAL - 1
    assert surface.NAME_FIELD not in surface.THEME_COLOUR_FIELDS
    assert surface.NAME_FIELD not in surface.TIER_COLOUR_FIELDS


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_every_colour_is_eight_hex_digits(theme):
    """A colour is written short, and the screen would report it long."""
    for field in THEME_COLOUR_FIELDS:
        value = surface.THEMES[theme][field]
        assert len(value) == 9, (theme, field, value)
        assert value.startswith("#"), (theme, field, value)
        assert value == value.lower(), (theme, field, value)
        assert set(value[1:]) <= set("0123456789abcdef"), (theme, field, value)


@pytest.mark.parametrize("tier", EXPECTED_TIER_NAMES)
def test_every_tier_colour_is_eight_hex_digits(tier):
    """A tier colour is written short, and the screen would report it long."""
    for field in TIER_COLOUR_FIELDS:
        value = surface.TIER_PALETTES[tier][field]
        assert len(value) == 9, (tier, field, value)
        assert value == value.lower(), (tier, field, value)
        assert set(value[1:]) <= set("0123456789abcdef"), (tier, field, value)


def test_the_partly_see_through_colours_carry_the_shipped_transparency():
    """A colour's transparency differs between the two sides."""
    found = []
    for theme in EXPECTED_THEME_NAMES:
        for field in THEME_COLOUR_FIELDS:
            value = surface.THEMES[theme][field]
            alpha = surface.channels(value)[3]
            assert alpha == shipped.THEMES[theme][field].alpha(), (theme, field)
            if alpha != 255:
                found.append((theme, field, alpha))
    assert len(found) == SEE_THROUGH_TOTAL, found
    assert ("nebula", "grid", 40) in found
    assert ("ocean", "particle", 50) in found


def test_channels_splits_a_colour_into_its_four_numbers():
    """The colour splitter reported the wrong numbers."""
    assert surface.channels("#3c287828") == (60, 40, 120, 40)
    assert surface.channels("#ffffffff") == (255, 255, 255, 255)
    assert surface.channels("#00000000") == (0, 0, 0, 0)
    for theme in EXPECTED_THEME_NAMES:
        for field in THEME_COLOUR_FIELDS:
            colour = shipped.THEMES[theme][field]
            assert surface.channels(surface.THEMES[theme][field]) == (
                colour.red(),
                colour.green(),
                colour.blue(),
                colour.alpha(),
            ), (theme, field)


# The tier a balance maps to


@pytest.mark.parametrize("case", sorted(NUMBER_CASES))
def test_both_sides_do_the_same_thing_with_every_balance(case):
    """One side answered where the other refused, or answered differently."""
    value = NUMBER_CASES[case]
    old = outcome(shipped._tier_from_target_balance, value)
    new = outcome(surface.tier_for_target_balance, value)
    assert new == old, "%s: shipped %r, surface %r" % (case, old, new)


@pytest.mark.parametrize("case", ANSWERED_NUMBER_CASES)
def test_every_balance_that_answers_maps_to_the_tier_typed_here(case):
    """A balance maps to a different tier than the one typed here."""
    value = NUMBER_CASES[case]
    wanted = EXPECTED_TIERS_FOR_NUMBERS[case]
    assert surface.tier_for_target_balance(value) == wanted, case
    assert shipped._tier_from_target_balance(value) == wanted, case
    assert surface.tier_answer(value) == (wanted, "")


@pytest.mark.parametrize("case", REFUSED_NUMBER_CASES)
def test_every_balance_that_is_refused_is_refused_the_same_way(case):
    """A refusal came back with a different error or different wording."""
    value = NUMBER_CASES[case]
    with pytest.raises(TypeError) as old:
        shipped._tier_from_target_balance(value)
    with pytest.raises(TypeError) as new:
        surface.tier_for_target_balance(value)
    assert str(new.value) == str(old.value), case
    assert str(new.value) == REFUSAL_FORMAT % type(value).__name__, case
    assert surface.tier_answer(value) == ("", str(old.value)), case


def test_the_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every input did the same thing, so the comparison sees one path."""
    did = {
        outcome(surface.tier_for_target_balance, value)["did"]
        for value in NUMBER_CASES.values()
    }
    assert did == {"answered", "refused"}, did
    assert len(ANSWERED_NUMBER_CASES) == 17, len(ANSWERED_NUMBER_CASES)
    assert len(REFUSED_NUMBER_CASES) == 13, len(REFUSED_NUMBER_CASES)
    assert len(NUMBER_CASES) == 30


def test_the_ceilings_are_the_shipped_thresholds():
    """A tier boundary moved on one side."""
    assert surface.TIER_CEILINGS_USD == EXPECTED_CEILINGS_USD
    assert list(surface.TIER_CEILINGS_USD) == ["harvest", "great", "bumper"]
    assert surface.TOP_TIER == EXPECTED_TOP_TIER
    assert set(surface.TIER_CEILINGS_USD) | {surface.TOP_TIER} == set(
        EXPECTED_TIER_NAMES
    )
    for tier, ceiling in EXPECTED_CEILINGS_USD.items():
        assert shipped._tier_from_target_balance(ceiling - 0.01) == tier, tier
        assert surface.tier_for_target_balance(ceiling - 0.01) == tier, tier


def test_the_tier_answer_reports_the_refusal_instead_of_raising():
    """The wrapper raised where it should report."""
    answered, refusal = surface.tier_answer(50)
    assert (answered, refusal) == ("harvest", "")
    refused_tier, refused_message = surface.tier_answer("50")
    assert refused_tier == ""
    assert refused_message == REFUSAL_FORMAT % "str"
    assert surface.NOT_ASKED == ""


# Looking a theme or a tier up


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_a_known_theme_comes_back_whole(theme):
    """A theme lookup came back short."""
    assert surface.has_theme(theme) is True
    assert surface.theme_colours(theme) == EXPECTED_THEMES[theme]
    assert surface.theme_colours(theme) == shipped_themes()[theme]


@pytest.mark.parametrize("tier", EXPECTED_TIER_NAMES)
def test_a_known_tier_comes_back_whole(tier):
    """A tier lookup came back short."""
    assert surface.has_tier(tier) is True
    assert surface.tier_colours(tier) == EXPECTED_TIERS[tier]
    assert surface.tier_colours(tier) == shipped_tiers()[tier]


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_an_unknown_name_returns_an_empty_table_on_both_sides(case):
    """An unknown name came back as a theme or a tier."""
    name = UNKNOWN_NAMES[case]
    assert name not in shipped.THEMES, case
    assert name not in shipped.TIER_PALETTES, case
    assert surface.has_theme(name) is False, case
    assert surface.has_tier(name) is False, case
    assert surface.theme_colours(name) == {}, case
    assert surface.tier_colours(name) == {}, case
    assert surface.NO_PALETTE == {}


@pytest.mark.parametrize("value", NON_STRING_NAMES, ids=repr)
def test_a_name_that_is_not_text_asks_for_nothing(value):
    """A number where a name belongs was read as a name."""
    assert surface.requested_name(value) == ""
    assert surface.has_theme(value) is False
    assert surface.has_tier(value) is False
    assert surface.theme_colours(value) == {}
    assert surface.tier_colours(value) == {}


def test_a_lookup_hands_back_a_copy():
    """A caller that edits a lookup changed the table for everyone."""
    row = surface.theme_colours("nebula")
    row["bg"] = "#ffffffff"
    assert surface.THEMES["nebula"]["bg"] == "#080414ff"
    tier = surface.tier_colours("harvest")
    tier["base"] = "#ffffffff"
    assert surface.TIER_PALETTES["harvest"]["base"] == "#50b46eff"


def test_the_lookup_can_report_a_missing_name():
    """The lookup returns a theme for every name, so it never refuses."""
    assert surface.theme_colours("nebula") != {}
    assert surface.theme_colours("nebul") == {}
    assert surface.tier_colours("harvest") != {}
    assert surface.tier_colours("harves") == {}


# What the shipped module has, and where each item went

SHIPPED_DEFINITIONS = ("_tier_from_target_balance",)

SURFACE_FUNCTIONS = (
    "tier_for_target_balance",
    "tier_answer",
    "has_theme",
    "has_tier",
    "theme_colours",
    "tier_colours",
    "channels",
    "requested_name",
    "build_view_model",
    "view_model",
)

# Every item the shipped module holds, and what stands for it here.
COUNTERPARTS = {
    "TIER_PALETTES": "TIER_PALETTES",
    "THEMES": "THEMES",
    "_tier_from_target_balance": "tier_for_target_balance",
}


def module_functions(module):
    """Every real function a module defines. A signal is callable and is not one."""
    return {
        name
        for name, value in vars(module).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def module_classes(module):
    """Every class a module defines."""
    return {
        name
        for name, value in vars(module).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def class_methods(owner):
    """Every real method a class defines. A signal is callable and is not one."""
    return {name for name, value in vars(owner).items() if inspect.isfunction(value)}


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    shipped_text = SHIPPED_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert shipped_text.count(".connect(") == 0
    assert surface_text.count(".connect(") == 0
    assert len(surface.ACTIONS) == shipped_text.count(".connect(")
    assert len(surface.ACTIONS) == surface_text.count(".connect(")


def test_the_connect_counter_can_see_a_wiring():
    """The wiring counter reported none because it can never report one."""
    neighbour = WIRED_NEIGHBOUR_PATH.read_text(encoding="utf-8")
    assert neighbour.count(".connect(") > 0, WIRED_NEIGHBOUR_PATH


def test_the_two_sides_declare_no_timer_and_no_bus_topic():
    """The surface gained a timer or a bus topic the table never had."""
    shipped_text = SHIPPED_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert shipped_text.count("QTimer") == 0
    assert surface_text.count("QTimer") == 0
    assert shipped_text.count(".subscribe(") == 0
    assert surface_text.count(".subscribe(") == 0
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.BUS_TOPICS == ()
    assert surface.SKIN == {}
    assert surface.ACTIONS == {}


def test_the_timer_and_topic_counters_can_see_one():
    """The timer and topic counters reported none because they see nothing."""
    neighbour = TIMER_NEIGHBOUR_PATH.read_text(encoding="utf-8")
    assert neighbour.count("QTimer") > 0, TIMER_NEIGHBOUR_PATH
    topics = TOPIC_NEIGHBOUR_PATH.read_text(encoding="utf-8")
    assert topics.count(".subscribe(") > 0, TOPIC_NEIGHBOUR_PATH


def test_the_two_sides_define_the_same_number_of_classes():
    """A class appeared on one side and not the other."""
    assert module_classes(shipped) == set()
    assert module_classes(surface) == set()
    assert len(module_classes(shipped)) == len(module_classes(surface))


def test_the_class_counter_can_see_a_class():
    """The class counter reported none because it can never report one."""
    from src.gui.main_tabs import table_cells_surface as neighbour

    found = module_classes(neighbour)
    assert len(found) > 0, "the counter cannot see a class anywhere"
    assert "TableCellsModel" in found


def test_every_shipped_item_has_a_counterpart():
    """An item on the shipped side has nothing standing for it."""
    assert module_functions(shipped) == set(SHIPPED_DEFINITIONS)
    assert len(module_functions(shipped)) == 1
    for old_name, new_name in COUNTERPARTS.items():
        assert hasattr(shipped, old_name), old_name
        assert hasattr(surface, new_name), new_name
    assert len(COUNTERPARTS) == 3
    assert callable(surface.tier_for_target_balance)
    assert isinstance(surface.THEMES, dict)
    assert isinstance(surface.TIER_PALETTES, dict)


def test_the_function_counter_can_see_a_function_and_excludes_a_signal():
    """The counter reported none, or counted a signal as a method.

    A signal is callable and is not a method. The counter is pointed at
    a neighbouring class that carries one, and must report the class's
    methods while leaving the signal out.
    """
    from src.gui import launcher

    signal = vars(launcher.ModeCard)["clicked"]
    assert callable(signal), "the signal is not callable, so nothing is excluded"
    assert not inspect.isfunction(signal)
    methods = class_methods(launcher.ModeCard)
    assert "clicked" not in methods, methods
    assert "mousePressEvent" in methods, methods
    assert len(methods) > 0
    assert len(module_functions(shipped)) > 0


def test_the_surface_functions_are_reachable_and_described():
    """A named helper is missing, or carries no description."""
    assert module_functions(surface) == set(SURFACE_FUNCTIONS)
    assert len(SURFACE_FUNCTIONS) == 10
    for name in SURFACE_FUNCTIONS:
        member = getattr(surface, name)
        assert callable(member), name
        assert (member.__doc__ or "").strip(), name
    with pytest.raises(AttributeError):
        surface.no_such_helper()


def test_nothing_in_the_product_reads_the_tier_palettes():
    """The tier table gained a reader, so the count below is stale."""
    readers = 0
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path in (SHIPPED_PATH, SURFACE_PATH):
            continue
        readers += path.read_text(encoding="utf-8").count("TIER_PALETTES")
    assert readers == TIER_PALETTE_READERS, readers
    assert (REPO_ROOT / "src/gui/bot_visualizer.py").read_text(encoding="utf-8").count(
        "from .visualizer.themes import THEMES"
    ) == 1


# The surface without Qt


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
    assert imported == {"__future__", "typing"}


def test_the_import_reader_can_see_a_qt_import():
    """The import reader reported none because it can never report one."""
    tree = ast.parse(SHIPPED_PATH.read_text(encoding="utf-8"))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in imported), imported


def test_the_surface_carries_its_own_copy_of_every_value(monkeypatch):
    """The surface read its values off the module it replaces.

    A surface that imported the shipped table would follow it, and the
    whole comparison above would be one side read twice. The shipped
    value is moved and the surface must not move with it.
    """
    from PySide6.QtGui import QColor

    for table, key, field, moved, kept in (
        (shipped.THEMES, "nebula", "bg", QColor(1, 2, 3, 4), "#080414ff"),
        (shipped.THEMES, "matrix", "accent", QColor(9, 9, 9), "#00ff41ff"),
        (shipped.TIER_PALETTES, "harvest", "base", QColor(7, 6, 5), "#50b46eff"),
        (shipped.TIER_PALETTES, "ekthelius", "name", "Moved", "Ekthelius"),
    ):
        was = table[key][field]
        monkeypatch.setitem(table[key], field, moved)
        assert table[key][field] is moved, field
        if field == "name":
            assert surface.TIER_PALETTES[key][field] == kept, field
            assert surface.TIER_DISPLAY_NAMES[key] == kept, field
        else:
            live = surface.THEMES if table is shipped.THEMES else surface.TIER_PALETTES
            assert live[key][field] == kept, field
            assert (
                surface.build_view_model()[
                    "themes" if table is shipped.THEMES else "tier_palettes"
                ][key][field]
                == kept
            ), field
        monkeypatch.undo()
        assert table[key][field] is was, field


def test_the_independence_check_can_report():
    """The independence check moved nothing, so it proves nothing."""
    from PySide6.QtGui import QColor

    was = shipped.THEMES["ocean"]["bg"]
    shipped.THEMES["ocean"]["bg"] = QColor(1, 2, 3)
    try:
        assert hex_from_qcolor(shipped.THEMES["ocean"]["bg"]) == "#010203ff"
        assert shipped_themes()["ocean"]["bg"] != surface.THEMES["ocean"]["bg"]
        assert differences(shipped_snapshot(), surface_snapshot()) != []
    finally:
        shipped.THEMES["ocean"]["bg"] = was
    assert differences(shipped_snapshot(), surface_snapshot()) == []


def test_the_shipped_module_mutates_no_shared_state():
    """Reading the shipped table changed it for the next test."""
    before = digest(shipped_snapshot())
    for theme in EXPECTED_THEME_NAMES:
        shipped_row(shipped.THEMES, theme, EXPECTED_THEME_FIELDS)
    for tier in EXPECTED_TIER_NAMES:
        shipped_row(shipped.TIER_PALETTES, tier, EXPECTED_TIER_FIELDS)
    for value in NUMBER_CASES.values():
        outcome(shipped._tier_from_target_balance, value)
    assert digest(shipped_snapshot()) == before


def test_the_surface_mutates_no_shared_state():
    """Calling the surface changed its own tables."""
    before = digest(surface_snapshot())
    surface.build_view_model("nebula", "harvest", 500)
    surface.view_model({"name": "ocean", "tier": "bumper", "target_balance": "x"})
    surface.theme_colours("nebula")["bg"] = "#ffffffff"
    assert digest(surface_snapshot()) == before


# The pictures

PICTURE_CASES = tuple(zip(EXPECTED_THEME_NAMES, EXPECTED_TIER_NAMES))


@pytest.mark.parametrize("theme,tier", PICTURE_CASES)
def test_the_two_sides_paint_one_picture(theme, tier):
    """The surface painted a different window than the shipped table."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(
            build_panel(shipped_paint_values(theme, tier)), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            build_panel(surface_paint_values(theme, tier)), PIXEL_SIZE
        ),
        note="%s with %s" % (theme, tier),
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real themes and two real tiers, one pair taken from each side. A
    pass proves the comparison reports a window painted differently, so
    the matches above are not green by being unable to fail.
    """
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            build_panel(shipped_paint_values("nebula", "harvest")), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            build_panel(surface_paint_values("matrix", "great")), PIXEL_SIZE
        ),
        note="nebula with harvest against matrix with great",
    )


@pytest.mark.parametrize("theme,tier", PICTURE_CASES)
def test_the_painted_window_shows_more_than_one_colour(theme, tier):
    """The two sides matched because the window painted one flat colour."""
    app()
    image = render_offscreen(build_panel(surface_paint_values(theme, tier)), PIXEL_SIZE)
    assert image.width() == PIXEL_SIZE[0]
    assert image.height() == PIXEL_SIZE[1]
    found = colour_count(image)
    assert found > 1, "%s with %s painted %d colour" % (theme, tier, found)


@skip_unless_no_fonts
def test_two_shown_names_of_equal_length_measure_alike_with_no_fonts():
    """The host reports no fonts and the glyphs still have their own widths."""
    app()
    from PySide6.QtWidgets import QLabel

    first = QLabel(surface.DISPLAY_NAMES["nebula"])
    second = QLabel(surface.DISPLAY_NAMES["matrix"])
    assert len(first.text()) == len(second.text()) == 6
    assert first.sizeHint().width() == second.sizeHint().width()


@skip_unless_real_fonts
def test_two_shown_names_of_different_length_measure_apart_with_real_fonts():
    """The host reports fonts and every glyph still has one width."""
    app()
    from PySide6.QtWidgets import QLabel

    short = QLabel(surface.DISPLAY_NAMES["matrix"])
    long = QLabel(surface.DISPLAY_NAMES["quantum"])
    assert len(short.text()) < len(long.text())
    assert short.sizeHint().width() < long.sizeHint().width()


# The five things no picture of this table can report, each with the
# check that does cover it.
BLIND_TO_THE_PICTURE = {
    "shown_names": "test_the_shown_names_match",
    "equal_channel_colours": "test_the_equal_channel_colours_are_compared_as_text",
    "near_repeated_colours": "test_the_near_repeated_colours_are_compared_by_field",
    "field_order": "test_every_theme_row_keeps_the_shipped_field_order",
    "tier_for_a_balance": "test_both_sides_do_the_same_thing_with_every_balance",
}


def test_the_equal_channel_colours_are_compared_as_text():
    """A colour whose channels match had two of them swapped."""
    found = []
    for theme in EXPECTED_THEME_NAMES:
        for field in THEME_COLOUR_FIELDS:
            value = surface.THEMES[theme][field]
            if len({value[1:3], value[3:5], value[5:7]}) < 3:
                found.append(("themes", theme, field))
    assert tuple(found) == EQUAL_CHANNEL_COLOURS, found
    for _, theme, field in EQUAL_CHANNEL_COLOURS:
        assert surface.THEMES[theme][field] == shipped_themes()[theme][field]
        assert surface.THEMES[theme][field] == EXPECTED_THEMES[theme][field]
    assert ("themes", "matrix", "error") in EQUAL_CHANNEL_COLOURS
    assert ("themes", "nebula", "bg") not in EQUAL_CHANNEL_COLOURS


def test_the_near_repeated_colours_are_compared_by_field():
    """Two fields carrying one colour were swapped and nothing moved."""
    found = []
    for theme in EXPECTED_THEME_NAMES:
        seen = {}
        for field in THEME_COLOUR_FIELDS:
            seen.setdefault(surface.THEMES[theme][field][:7], []).append(field)
        for fields in seen.values():
            if len(fields) > 1:
                found.append((theme, *fields))
    assert tuple(found) == NEAR_REPEATED_COLOURS, found
    for theme, first, second in NEAR_REPEATED_COLOURS:
        for field in (first, second):
            assert surface.THEMES[theme][field] == shipped_themes()[theme][field]
            assert surface.THEMES[theme][field] == EXPECTED_THEMES[theme][field]
        assert surface.THEMES[theme][first] != surface.THEMES[theme][second]


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report.

    Five things never reach a pixel comparison, each named here with the
    check that does cover it. The shown names paint the same box glyphs
    on a host with no fonts. Three colours have two matching channels, so
    a swap of those two paints the same pixel. Two pairs inside one theme
    carry the same red, green and blue. The order of the fields and the
    tier a balance maps to are read, not drawn.
    """
    assert len(BLIND_TO_THE_PICTURE) == 5
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# The bridge


def test_view_model_is_json_serialisable():
    """A value in the payload cannot cross the bridge."""
    for params in (
        {},
        {"name": "nebula", "tier": "harvest", "target_balance": 500},
        {"name": "nope", "tier": "nope", "target_balance": math.inf},
        {"name": 9, "tier": [], "target_balance": "x"},
    ):
        text = json.dumps(surface.view_model(params), ensure_ascii=True)
        assert json.loads(text)["theme_names"] == list(EXPECTED_THEME_NAMES)


def test_the_payload_carries_every_theme_and_every_tier():
    """The payload came back short of a theme, a tier or a value."""
    payload = surface.build_view_model()
    assert payload["themes"] == shipped_themes()
    assert payload["tier_palettes"] == shipped_tiers()
    assert payload["theme_names"] == list(EXPECTED_THEME_NAMES)
    assert payload["tier_names"] == list(EXPECTED_TIER_NAMES)
    assert payload["display_names"] == EXPECTED_THEME_DISPLAY_NAMES
    assert payload["tier_display_names"] == EXPECTED_TIER_DISPLAY_NAMES
    assert len(payload["themes"]) == THEME_TOTAL
    assert len(payload["tier_palettes"]) == TIER_TOTAL


def test_the_payload_carries_the_four_numbers_of_every_colour():
    """A colour reached the payload without its four numbers."""
    payload = surface.build_view_model()
    for theme in EXPECTED_THEME_NAMES:
        assert list(payload["theme_channels"][theme]) == list(THEME_COLOUR_FIELDS)
        for field in THEME_COLOUR_FIELDS:
            colour = shipped.THEMES[theme][field]
            assert payload["theme_channels"][theme][field] == [
                colour.red(),
                colour.green(),
                colour.blue(),
                colour.alpha(),
            ], (theme, field)
    for tier in EXPECTED_TIER_NAMES:
        assert list(payload["tier_channels"][tier]) == list(TIER_COLOUR_FIELDS)


def test_the_payload_hands_back_a_copy():
    """A caller that edits the payload changed the table for everyone."""
    payload = surface.build_view_model()
    payload["themes"]["nebula"]["bg"] = "#ffffffff"
    payload["tier_palettes"]["harvest"]["base"] = "#ffffffff"
    payload["tier_ceilings_usd"]["harvest"] = 1
    assert surface.THEMES["nebula"]["bg"] == "#080414ff"
    assert surface.TIER_PALETTES["harvest"]["base"] == "#50b46eff"
    assert surface.TIER_CEILINGS_USD["harvest"] == 100
    assert surface.build_view_model()["themes"]["nebula"]["bg"] == "#080414ff"


def test_the_payload_answers_the_request_it_is_given():
    """The payload ignored the theme, the tier or the balance it was asked for."""
    payload = surface.build_view_model("ocean", "bumper", 5_000)
    assert payload["requested_theme"] == "ocean"
    assert payload["requested_tier"] == "bumper"
    assert payload["theme"] == EXPECTED_THEMES["ocean"]
    assert payload["tier_palette"] == EXPECTED_TIERS["bumper"]
    assert payload["unknown_theme"] == []
    assert payload["unknown_tier"] == []
    assert payload["tier"] == "bumper"
    assert payload["tier_refusal"] == ""
    assert payload["target_balance_text"] == "5000"


def test_the_payload_asked_for_nothing_reports_nothing():
    """The payload named a theme before one was asked for."""
    payload = surface.build_view_model()
    assert payload["requested_theme"] == ""
    assert payload["requested_tier"] == ""
    assert payload["theme"] == {}
    assert payload["tier_palette"] == {}
    assert payload["unknown_theme"] == [""]
    assert payload["unknown_tier"] == [""]
    assert payload["tier"] == ""
    assert payload["tier_refusal"] == REFUSAL_FORMAT % "NoneType"
    assert payload["target_balance_text"] == "None"


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_the_payload_refuses_an_unknown_name(case):
    """An unknown name came back as a theme instead of a refusal."""
    name = UNKNOWN_NAMES[case]
    payload = surface.build_view_model(name, name, 10)
    assert payload["unknown_theme"] == [name], case
    assert payload["unknown_tier"] == [name], case
    assert payload["theme"] == {}, case
    assert payload["tier_palette"] == {}, case
    assert payload["tier"] == "harvest", case


def test_bridge_registers_the_visualizer_themes_method():
    """The renderer cannot reach the theme table through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == METHOD_NAME
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 21,
                "method": surface.METHOD,
                "params": {"name": "quantum", "tier": "great", "target_balance": 500},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["theme"] == EXPECTED_THEMES["quantum"]
    assert result["tier_palette"] == EXPECTED_TIERS["great"]
    assert result["tier"] == "great"
    assert result["themes"] == shipped_themes()


def test_the_bridge_registration_is_two_lines_and_no_more():
    """The bridge grew more than the one registration this unit adds."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    assert text.count("visualizer_themes_surface") == 3
    assert (
        "visualizer_themes_surface.METHOD: visualizer_themes_surface.view_model" in text
    )
    assert "        visualizer_themes_surface,\n" in text


def test_the_bridge_import_list_stays_alphabetical():
    """A new import went in out of order."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    block = text.split("from src.gui.main_tabs import (")[1].split(")")[0]
    names = [line.strip().rstrip(",") for line in block.splitlines() if line.strip()]
    assert names == sorted(names), names
    assert "visualizer_themes_surface" in names


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_the_bridge_carries_every_theme(theme):
    """One theme came back wrong over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 22, "method": surface.METHOD, "params": {"name": theme}}),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["theme"] == shipped_themes()[theme]
    assert answer["result"]["requested_theme"] == theme


@pytest.mark.parametrize("case", sorted(NUMBER_CASES))
def test_the_bridge_answers_every_balance(case):
    """A balance ended the request instead of coming back as a tier."""
    from src.core import desktop_bridge

    value = NUMBER_CASES[case]
    try:
        params = json.loads(json.dumps({"target_balance": value}))
    except (TypeError, ValueError):
        pytest.skip("%s cannot be written as JSON" % case)
    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 23, "method": surface.METHOD, "params": params}), registry
    )
    assert answer["ok"] is True, case
    result = answer["result"]
    if case in EXPECTED_TIERS_FOR_NUMBERS:
        assert result["tier"] == EXPECTED_TIERS_FOR_NUMBERS[case], case
        assert result["tier_refusal"] == "", case
    else:
        assert result["tier"] == "", case
        assert result["tier_refusal"].startswith("'<' not supported"), case


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """A parameter the surface does not read ended the request."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 24,
                "method": surface.METHOD,
                "params": {"name": "ocean", "invented": [1, 2], "group": "x"},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["requested_theme"] == "ocean"
    assert "invented" not in answer["result"]


def test_the_bridge_reads_a_name_that_is_not_a_string():
    """A number where a theme name belongs ended the request."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    for value in (0, -1, 9.5, None, [], {}):
        answer = desktop_bridge.handle_line(
            json.dumps({"id": 25, "method": surface.METHOD, "params": {"name": value}}),
            registry,
        )
        assert answer["ok"] is True, repr(value)
        assert answer["result"]["requested_theme"] == "", repr(value)
        assert answer["result"]["theme"] == {}, repr(value)


def test_the_table_is_the_same_on_every_call():
    """The table changed between two calls, so a caller sees a moving answer."""
    first = surface.view_model({"name": "nebula"})
    second = surface.view_model({})
    third = surface.view_model({"name": "nebula"})
    assert first["themes"] == second["themes"] == third["themes"]
    assert first == third
    assert digest(first) == digest(third)
    assert second["requested_theme"] == ""


# The surface without Qt, proved in a process of its own

BLOCK_QT = (
    "import sys\n"
    "class Refuse:\n"
    "    def find_module(self, name, path=None):\n"
    "        return self\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('PySide6', 'shiboken6'):\n"
    "            raise ImportError('Qt is blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, Refuse())\n"
)

BRIDGE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.core import desktop_bridge\n"
    "registry = desktop_bridge.build_registry()\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'visualizer_themes.state',\n"
    "    'params': {'name': 'quantum', 'tier': 'bumper',\n"
    "               'target_balance': 5000}}), registry)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame}))\n"
)

TABLE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.main_tabs import visualizer_themes_surface as s\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'theme_count': len(s.THEME_NAMES), 'tier_count': len(s.TIER_NAMES),\n"
    "    'themes': {n: dict(v) for n, v in s.THEMES.items()},\n"
    "    'tiers': {n: dict(v) for n, v in s.TIER_PALETTES.items()},\n"
    "    'missing_theme': s.theme_colours('NOPE'),\n"
    "    'missing_tier': s.tier_colours('NOPE'),\n"
    "    'tier_for_500': s.tier_for_target_balance(500),\n"
    "    'refusal': s.tier_answer('500')[1]}))\n"
)

SHIPPED_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.visualizer import themes as t\n"
    "print(json.dumps({'has_themes': hasattr(t, 'THEMES'),\n"
    "    'has_tiers': hasattr(t, 'TIER_PALETTES'),\n"
    "    'has_mapper': hasattr(t, '_tier_from_target_balance')}))\n"
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
    """Reaching the theme table pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["theme"] == EXPECTED_THEMES["quantum"]
    assert result["tier_palette"] == EXPECTED_TIERS["bumper"]
    assert result["tier"] == "bumper"
    assert result["theme_names"] == list(EXPECTED_THEME_NAMES)


def test_the_surface_carries_every_value_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(TABLE_PROBE)
    assert answered["qt"] is False
    assert answered["theme_count"] == THEME_TOTAL
    assert answered["tier_count"] == TIER_TOTAL
    assert answered["themes"] == shipped_themes()
    assert answered["tiers"] == shipped_tiers()
    assert answered["missing_theme"] == {}
    assert answered["missing_tier"] == {}
    assert answered["tier_for_500"] == "great"
    assert answered["refusal"] == REFUSAL_FORMAT % "str"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import sys\nimport PySide6.QtCore\n" + BRIDGE_PROBE.replace(BLOCK_QT, "")
    )
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_qt_block_stops_a_module_that_imports_qt():
    """The Qt block let a module through that imports PySide6."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from PySide6.QtGui import QColor\n"
        "    blocked = False\n"
        "except ImportError:\n"
        "    blocked = True\n"
        "print(json.dumps({'blocked': blocked}))\n"
    )
    assert run_script(probe)["blocked"] is True


def test_the_shipped_table_disappears_where_qt_cannot_be_imported():
    """The shipped table survives without Qt, so nothing needed replacing."""
    answered = run_script(SHIPPED_PROBE)
    assert answered["has_themes"] is False
    assert answered["has_tiers"] is False
    assert answered["has_mapper"] is False


# Nothing the surface holds is left out of the snapshot

# Every constant the surface exports, and the payload key that carries
# it. A comparison reading 10 of 21 constants passes whether the other
# 11 match or not; this closes that gap for every one of them at once.
PAYLOAD_KEYS = {
    "THEME_FIELD_NAMES": "theme_field_names",
    "TIER_FIELD_NAMES": "tier_field_names",
    "THEME_COLOUR_FIELDS": "theme_colour_fields",
    "TIER_COLOUR_FIELDS": "tier_colour_fields",
    "THEMES": "themes",
    "TIER_PALETTES": "tier_palettes",
    "THEME_NAMES": "theme_names",
    "TIER_NAMES": "tier_names",
    "DISPLAY_NAMES": "display_names",
    "TIER_DISPLAY_NAMES": "tier_display_names",
    "TIER_CEILINGS_USD": "tier_ceilings_usd",
    "TOP_TIER": "top_tier",
    "ACTIONS": "actions",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "BUS_TOPICS": "bus_topics",
    "SKIN": "skin",
}

# The four constants no snapshot key carries, each with the check that
# covers it. `METHOD` is the name the bridge registers under.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_bridge_registers_the_visualizer_themes_method",
    "NAME_FIELD": "test_the_colour_fields_are_the_field_names_without_the_shown_name",
    "NO_PALETTE": "test_an_unknown_name_returns_an_empty_table_on_both_sides",
    "NOT_ASKED": "test_a_name_that_is_not_text_asks_for_nothing",
}

CONSTANT_TOTAL = 21

PAYLOAD_KEY_TOTAL = 28

REQUEST_ONLY_KEYS = {
    "requested_theme",
    "requested_tier",
    "theme",
    "tier_palette",
    "theme_channels",
    "tier_channels",
    "unknown_theme",
    "unknown_tier",
    "target_balance_text",
    "tier",
    "tier_refusal",
}

CONSTANT_TYPES = (str, int, dict, tuple)


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and isinstance(value, CONSTANT_TYPES)
        and not callable(value)
    }


def test_every_constant_the_surface_holds_reaches_the_snapshot():
    """A constant the surface exports is in no snapshot the tests read.

    A comparison that reads some of the constants passes whether the
    rest match or not. Every constant is accounted for here: a snapshot
    key, or one of the four named below with the check that covers it.
    """
    payload = surface.build_view_model()
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = payload[PAYLOAD_KEYS[name]]
            assert list(carried) == list(value), name
            if isinstance(value, dict):
                for key in value:
                    assert carried[key] == value[key], (name, key)
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 17
    assert len(NOT_IN_THE_SNAPSHOT) == 4


def test_every_snapshot_key_carries_a_constant_the_surface_holds():
    """The snapshot grew a key no constant on the surface backs."""
    payload = surface.build_view_model()
    assert set(payload) == set(PAYLOAD_KEYS.values()) | REQUEST_ONLY_KEYS
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in REQUEST_ONLY_KEYS:
        assert key in payload, key


def test_the_completeness_checks_can_report():
    """The completeness checks passed because they look at nothing.

    A constant that reaches no snapshot key and no named exception must
    land in the unaccounted list, and a payload key backed by nothing
    must fall outside the two named sets.
    """
    payload = surface.build_view_model()
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in surface_constants()
    assert "THEMES" in surface_constants()
    assert "TIER_CEILINGS_USD" in surface_constants()
    assert "tier_for_target_balance" not in surface_constants()
    assert "view_model" not in surface_constants()
    assert "invented_key" not in set(PAYLOAD_KEYS.values()) | REQUEST_ONLY_KEYS
    assert "invented_key" not in payload
    assert set(PAYLOAD_KEYS.values()) & REQUEST_ONLY_KEYS == set()
