"""What Qt paints for every style value that carries transparency."""

from __future__ import annotations

import re
from typing import Any

import pytest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from qt_pixel import ensure_app, pixel_at, render_widget

from src.gui import design_system as ds
from src.gui.color_alpha import rgba
from src.gui.main_tabs import bot_live_settings_surface as bls
from src.gui.main_tabs import fleet_replay_panel_surface as frp
from src.gui.main_tabs import nuclear_mode_panel_surface as nmp
from src.gui.main_tabs import settings_dialog_surface as sds
from src.gui.main_tabs import trading_tab_surface as tts

GROUND = "#404040"
FLEET_TEAL = "#00cccc"
CARD_EDGE_ALPHA = 68
BANNER_EDGE_ALPHA = 85
MARGIN_PX = 10
CARD_W_PX = 120
CARD_H_PX = 60

ALPHA_TOP = 255
CHANNEL_TOP = 255

EIGHT_DIGIT = re.compile(r"#[0-9a-fA-F]{8}")


def channels(color: str) -> tuple:
    """The three channels of a `#rgb` or `#rrggbb` colour."""
    digits = color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(one * 2 for one in digits)
    return tuple(int(digits[at : at + 2], 16) for at in (0, 2, 4))


def over(color: str, ground: str, alpha: int) -> str:
    """`color` at `alpha` composited over an opaque `ground`, as #rrggbb."""
    top = channels(color)
    under = channels(ground)
    mixed = [
        round((top[at] * alpha + under[at] * (ALPHA_TOP - alpha)) / ALPHA_TOP)
        for at in range(3)
    ]
    return "#" + "".join(f"{one:02x}" for one in mixed)


ROUNDING_ALLOWANCE = 1

FRAME = "frame"
LABEL = "label"
BUTTON = "button"


def near(drawn: str, wanted: str) -> bool:
    """Two colours agree within the rounding Qt's own blend allows."""
    return all(
        abs(one - other) <= ROUNDING_ALLOWANCE
        for one, other in zip(channels(drawn), channels(wanted))
    )


def painted(sheet: str, kind: str = FRAME) -> dict:
    """The edge and middle colours Qt paints for one style sheet."""
    ensure_app()
    host = QWidget()
    host.setStyleSheet(f"QWidget {{ background: {GROUND}; }}")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(MARGIN_PX, MARGIN_PX, MARGIN_PX, MARGIN_PX)
    if kind == LABEL:
        card: QWidget = QLabel("  X  ", host)
    elif kind == BUTTON:
        card = QPushButton("X", host)
    else:
        card = QFrame(host)
    card.setStyleSheet(sheet)
    card.setMinimumSize(CARD_W_PX, CARD_H_PX)
    layout.addWidget(card)
    try:
        image = render_widget(
            host,
            size=(CARD_W_PX + MARGIN_PX * 2, CARD_H_PX + MARGIN_PX * 2),
        )
        middle = QPoint(MARGIN_PX + CARD_W_PX // 2, MARGIN_PX + CARD_H_PX // 2)
        edge = QPoint(MARGIN_PX, MARGIN_PX + CARD_H_PX // 2)
        return {"edge": pixel_at(image, edge), "middle": pixel_at(image, middle)}
    finally:
        host.deleteLater()


BADGE_STATES = ("running", "idle", "paused", "error", "stopped", "cooldown")


@pytest.mark.parametrize("state", BADGE_STATES)
def test_a_state_badge_is_tinted_by_the_colour_of_its_own_state(state: str):
    """Eight digits made this fully transparent, opaque, or unreadable."""
    colour = bls.STATE_COLORS[state]
    drawn = painted(f"QLabel {{ {bls.state_style(state)} }}", LABEL)
    wanted = over(colour, GROUND, bls.STATE_BACKGROUND_ALPHA)
    assert near(drawn["middle"], wanted), (state, drawn, wanted)
    assert drawn["middle"] != GROUND, (state, drawn)
    assert not near(drawn["middle"], colour), (state, drawn)


def test_a_badge_for_an_unknown_state_is_tinted_by_the_neutral_colour():
    """`#ccc` and `#cccccc` are one colour, and both must reach the fill."""
    drawn = painted("QLabel { " + bls.state_style("nonesuch") + " }", LABEL)
    wanted = over(bls.STATE_UNKNOWN_BG, GROUND, bls.STATE_BACKGROUND_ALPHA)
    assert near(drawn["middle"], wanted), (drawn, wanted)
    assert drawn["middle"] != GROUND, drawn
    assert bls.STATE_UNKNOWN_BG == bls.STATE_UNKNOWN_FG


def swapped(sheet: str, colour: str, alpha: int) -> str:
    """`sheet` with one rgba value written back as the eight digits it replaced."""
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(one * 2 for one in digits)
    written = f"#{digits}{alpha:02x}"
    assert rgba(colour, alpha) in sheet, (colour, alpha, sheet)
    return sheet.replace(rgba(colour, alpha), written)


def trading_card(layer: str) -> str:
    return tts.placeholder_card_style(tts.LAYER_ACCENT[layer])


def nuclear_header() -> str:
    return (
        "QFrame{background:"
        + nmp.HEADER_CARD_BG
        + ";border:1px solid "
        + nmp.HEADER_CARD_BORDER
        + ";border-radius:6px;}"
    )


def glow_fill(name: str) -> str:
    return f"QFrame {{ background: {getattr(ds, name)}; border: none; }}"


#: name, the shipped sheet, the colour and alpha in it, the widget, the sample.
SITES = (
    ("badge running", lambda: bls.state_style("running"), ds.SUCCESS, 34, LABEL, "m"),
    ("badge paused", lambda: bls.state_style("paused"), ds.WARNING, 34, LABEL, "m"),
    ("badge error", lambda: bls.state_style("error"), ds.ERROR, 34, LABEL, "m"),
    ("nav button", lambda: bls.NAV_BUTTON_STYLE, ds.PRIMARY, 85, BUTTON, "e"),
    ("fleet header", lambda: frp.HEADER_STYLE, FLEET_TEAL, 68, FRAME, "e"),
    ("nuclear header", nuclear_header, nmp.GOLD, 68, FRAME, "e"),
    (
        "stock banner",
        lambda: f"QLabel {{ {sds.STOCK_BANNER_STYLE} }}",
        sds.STOCK_BANNER_COLOR,
        BANNER_EDGE_ALPHA,
        LABEL,
        "e",
    ),
    ("crypto card", lambda: trading_card("crypto"), ds.LAYER_CRYPTO, 68, FRAME, "e"),
    ("stock card", lambda: trading_card("stock"), ds.LAYER_STOCK, 68, FRAME, "e"),
    ("GLOW_PRIMARY", lambda: glow_fill("GLOW_PRIMARY"), ds.PRIMARY, 51, FRAME, "m"),
    (
        "GLOW_SECONDARY",
        lambda: glow_fill("GLOW_SECONDARY"),
        ds.SECONDARY,
        51,
        FRAME,
        "m",
    ),
    ("SCRIM", lambda: glow_fill("SCRIM"), "#000000", 136, FRAME, "m"),
    (
        "GLOW_PRIMARY_EDGE",
        lambda: glow_fill("GLOW_PRIMARY_EDGE"),
        ds.PRIMARY,
        85,
        FRAME,
        "m",
    ),
    (
        "GLOW_PRIMARY_FAINT",
        lambda: glow_fill("GLOW_PRIMARY_FAINT"),
        ds.PRIMARY,
        34,
        FRAME,
        "m",
    ),
)


@pytest.mark.parametrize("name,sheet_of,colour,alpha,kind,sample", SITES)
def test_each_site_painted_another_colour_while_its_alpha_was_written_last(
    name: str, sheet_of: Any, colour: str, alpha: int, kind: str, sample: str
):
    """The same intent written as eight digits, side by side with the fix."""
    at = "middle" if sample == "m" else "edge"
    sheet = sheet_of()
    after = painted(sheet, kind)[at]
    before = painted(swapped(sheet, colour, alpha), kind)[at]
    assert before != after, (name, before, after)
    assert near(
        after, over(colour, painted(bare_of(sheet, colour, alpha), kind)[at], alpha)
    ), (
        name,
        after,
    )


def bare_of(sheet: str, colour: str, alpha: int) -> str:
    """`sheet` with the one alpha-bearing colour turned fully see-through."""
    return sheet.replace(rgba(colour, alpha), rgba(colour, 0))


SHORT_FORM_BADGES = (
    ("idle", ds.CARD_METRIC_LABEL, "#88822"),
    ("stopped", ds.TEXT_MUTED, "#66622"),
    ("nonesuch", ds.TEXT_NEUTRAL, "#ccc22"),
)


@pytest.mark.parametrize("state,colour,five_digits", SHORT_FORM_BADGES)
def test_a_five_digit_badge_colour_painted_no_fill_at_all(
    state: str, colour: str, five_digits: str
):
    """A short colour with an alpha pair appended is unreadable, so Qt drew nothing."""
    dropped = painted(f"QLabel {{ background: {five_digits}; }}", LABEL)["middle"]
    assert dropped == GROUND, (state, dropped)
    drawn = painted(f"QLabel {{ {bls.state_style(state)} }}", LABEL)["middle"]
    assert drawn != GROUND, (state, drawn)
    assert near(drawn, over(colour, GROUND, bls.STATE_BACKGROUND_ALPHA)), (state, drawn)


def edge_agrees(sheet: str, colour: str, alpha: int, kind: str = FRAME) -> tuple:
    """The edge Qt paints, and the edge that colour at that alpha would give."""
    drawn = painted(sheet, kind)["edge"]
    bare = painted(sheet.replace(rgba(colour, alpha), rgba(colour, 0)), kind)["edge"]
    return drawn, over(colour, bare, alpha), bare


def test_the_nav_buttons_edge_carries_the_primary_tint():
    """`#00ffcc55` is alpha zero in Qt, so this edge had no colour at all."""
    drawn, wanted, bare = edge_agrees(bls.NAV_BUTTON_STYLE, ds.PRIMARY, 85, kind=BUTTON)
    assert near(drawn, wanted), (drawn, wanted, bare)
    assert drawn != bare, (drawn, bare)


def test_the_fleet_replay_header_carries_a_teal_edge():
    """`#00cccc44` is alpha zero in Qt, so this header had no edge."""
    drawn, wanted, bare = edge_agrees(frp.HEADER_STYLE, FLEET_TEAL, CARD_EDGE_ALPHA)
    assert near(drawn, wanted), (drawn, wanted, bare)
    assert drawn != bare, (drawn, bare)


def test_the_nuclear_mode_header_carries_a_gold_edge_and_not_a_red_one():
    """`#ffcc4444` painted an opaque dull red `#cc4444`."""
    sheet = (
        "QFrame{background:"
        + nmp.HEADER_CARD_BG
        + ";border:1px solid "
        + nmp.HEADER_CARD_BORDER
        + ";border-radius:6px;}"
    )
    drawn, wanted, bare = edge_agrees(sheet, nmp.GOLD, CARD_EDGE_ALPHA)
    assert near(drawn, wanted), (drawn, wanted, bare)
    assert not near(drawn, "#cc4444"), drawn


def test_the_stock_banner_edge_is_blue_and_not_lime():
    """`#6699ff55` painted a lime green, measured `#416b2b` on a dark ground."""
    drawn, wanted, bare = edge_agrees(
        f"QLabel {{ {sds.STOCK_BANNER_STYLE} }}",
        sds.STOCK_BANNER_COLOR,
        BANNER_EDGE_ALPHA,
        kind=LABEL,
    )
    assert near(drawn, wanted), (drawn, wanted, bare)
    assert channels(drawn)[2] > channels(drawn)[1], drawn


@pytest.mark.parametrize("layer", ("crypto", "stock"))
def test_a_trading_layer_card_carries_its_own_accent_on_the_edge(layer: str):
    """Crypto had no edge at all and stock's was a 40% lime green."""
    accent = tts.LAYER_ACCENT[layer]
    drawn, wanted, bare = edge_agrees(
        tts.placeholder_card_style(accent),
        accent,
        tts.PLACEHOLDER_CARD_BORDER_ALPHA,
    )
    assert near(drawn, wanted), (layer, drawn, wanted, bare)
    assert drawn != bare, (layer, drawn, bare)


GLOW_TOKENS = (
    ("GLOW_PRIMARY", ds.PRIMARY, 51),
    ("GLOW_SECONDARY", ds.SECONDARY, 51),
    ("GLOW_PRIMARY_EDGE", ds.PRIMARY, 85),
    ("GLOW_PRIMARY_FAINT", ds.PRIMARY, 34),
    ("SCRIM", "#000000", 136),
)


@pytest.mark.parametrize("name,base,alpha", GLOW_TOKENS)
def test_a_glow_token_fills_with_its_base_colour_at_its_own_alpha(
    name: str, base: str, alpha: int
):
    """GLOW_PRIMARY and SCRIM painted nothing; GLOW_SECONDARY painted green."""
    value = getattr(ds, name)
    drawn = painted(f"QFrame {{ background: {value}; border: none; }}")
    wanted = over(base, GROUND, alpha)
    assert near(drawn["middle"], wanted), (name, drawn, wanted)
    assert drawn["middle"] != GROUND, (name, drawn)


def alpha_bearing_values() -> dict:
    """Every style value the Qt-side modules publish, by where it is written."""
    found = {
        "design_system.GLOW_PRIMARY": ds.GLOW_PRIMARY,
        "design_system.GLOW_SECONDARY": ds.GLOW_SECONDARY,
        "design_system.GLOW_PRIMARY_EDGE": ds.GLOW_PRIMARY_EDGE,
        "design_system.GLOW_PRIMARY_FAINT": ds.GLOW_PRIMARY_FAINT,
        "design_system.SCRIM": ds.SCRIM,
        "bot_live_settings.NAV_BUTTON_STYLE": bls.NAV_BUTTON_STYLE,
        "fleet_replay.HEADER_STYLE": frp.HEADER_STYLE,
        "nuclear_mode.HEADER_CARD_BORDER": nmp.HEADER_CARD_BORDER,
        "settings_dialog.STOCK_BANNER_STYLE": sds.STOCK_BANNER_STYLE,
    }
    for state in BADGE_STATES + ("nonesuch",):
        found[f"bot_live_settings.state_style({state})"] = bls.state_style(state)
    for layer, accent in tts.LAYER_ACCENT.items():
        found[f"trading_tab.placeholder_card_style({layer})"] = (
            tts.placeholder_card_style(accent)
        )
    from src.gui import theme_engine

    for theme in theme_engine.THEMES.values():
        found[f"theme_engine.{theme.name}.border_accent"] = theme.border_accent
        found[f"theme_engine.{theme.name}.glow_color"] = theme.glow_color
    return found


def test_no_qt_style_value_carries_an_eight_digit_colour():
    """One value read alpha first by Qt and alpha last by a browser."""
    carrying = {
        where: EIGHT_DIGIT.findall(value)
        for where, value in alpha_bearing_values().items()
        if EIGHT_DIGIT.search(value)
    }
    assert not carrying, carrying


THREE_PLACES = {
    "a bare value": "#00ffcc55",
    "a whole sheet": "QFrame { background: #112233; border: 1px solid #00ffcc55; }",
    "a hover block": (
        "QPushButton { background: #112233; }"
        "QPushButton:hover { background: #00ffcc55; }"
        "QPushButton:disabled { border: 1px solid #ff00aa22; }"
    ),
}


@pytest.mark.parametrize("where", sorted(THREE_PLACES))
def test_the_survey_reads_an_eight_digit_colour_in_every_kind_of_place(where: str):
    """A walk over declarations alone never enters a `:hover` block."""
    assert EIGHT_DIGIT.findall(THREE_PLACES[where]), where


def test_the_survey_stays_quiet_on_the_values_the_modules_ship():
    """The survey answers nothing because there is nothing, not because it is idle."""
    for value in alpha_bearing_values().values():
        assert not EIGHT_DIGIT.findall(value), value
    assert EIGHT_DIGIT.findall(
        "QPushButton:disabled { border: 1px solid " + ds.PRIMARY + "22; }"
    )


def test_the_helper_refuses_a_colour_or_an_alpha_it_cannot_read():
    """A bad value must raise here rather than reach a sheet as unread text."""
    assert rgba("#ccc", 34) == rgba("#cccccc", 34)
    for bad in ("#cc", "#ccccc", "nonesuch", "#gggggg"):
        with pytest.raises(ValueError):
            rgba(bad, 34)
    for bad_alpha in (-1, 256, 1.5, True, "34"):
        with pytest.raises(ValueError):
            rgba("#cccccc", bad_alpha)
