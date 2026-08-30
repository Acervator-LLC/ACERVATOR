"""visualizer_themes_surface.py -- the four canvas themes and the four tier
palettes the bot visualizer paints from.

``THEMES`` holds one row per canvas theme: a shown name and nine
colours. ``TIER_PALETTES`` holds one row per bot tier: a shown name and
five colours. Every colour is written as ``#rrggbbaa``, the eight-digit
form CSS reads, so a colour that is partly see-through carries its own
transparency. ``channels`` splits one colour into its four numbers for a
caller that scales the transparency itself.

``tier_for_target_balance`` maps a bot's target balance to a tier key.
It compares the balance against each ceiling in ``TIER_CEILINGS_USD`` in
order and returns ``TOP_TIER`` when none is under. A value that cannot
be compared with a number raises, as the module this replaces does.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``visualizer_themes.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.visualizer.themes``, so a value changed on one side
alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any

METHOD = "visualizer_themes.state"

NAME_FIELD = "name"

TIER_FIELD_NAMES = ("name", "base", "shadow", "highlight", "accent", "glow")

THEME_FIELD_NAMES = (
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

TIER_COLOUR_FIELDS = tuple(f for f in TIER_FIELD_NAMES if f != NAME_FIELD)

THEME_COLOUR_FIELDS = tuple(f for f in THEME_FIELD_NAMES if f != NAME_FIELD)

TIER_PALETTES: dict[str, dict[str, str]] = {
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

THEMES: dict[str, dict[str, str]] = {
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

TIER_NAMES = tuple(TIER_PALETTES)

THEME_NAMES = tuple(THEMES)

TIER_DISPLAY_NAMES = {key: row[NAME_FIELD] for key, row in TIER_PALETTES.items()}

DISPLAY_NAMES = {key: row[NAME_FIELD] for key, row in THEMES.items()}

TIER_CEILINGS_USD = {"harvest": 100, "great": 1_000, "bumper": 10_000}

TOP_TIER = "ekthelius"

NO_PALETTE: dict[str, str] = {}

NOT_ASKED = ""

ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
SKIN: dict[str, str] = {}


def tier_for_target_balance(target_usd: float) -> str:
    """The tier key for a bot's target balance in dollars.

    Compares the balance against each ceiling in order and returns the
    first tier it is under, or ``TOP_TIER``. Raises TypeError for a
    value that cannot be compared with a number.
    """
    for tier, ceiling_usd in TIER_CEILINGS_USD.items():
        if target_usd < ceiling_usd:
            return tier
    return TOP_TIER


def tier_answer(target_usd: Any) -> tuple[str, str]:
    """The tier key for a balance, and the refusal text when there is none.

    Returns ``(tier, "")`` for a value that compares with a number, and
    ``(NOT_ASKED, message)`` for one that does not.
    """
    try:
        return tier_for_target_balance(target_usd), NOT_ASKED
    except TypeError as refused:
        return NOT_ASKED, str(refused)


def has_theme(name: Any) -> bool:
    """Whether the table holds a canvas theme under `name`."""
    return isinstance(name, str) and name in THEMES


def has_tier(name: Any) -> bool:
    """Whether the table holds a tier palette under `name`."""
    return isinstance(name, str) and name in TIER_PALETTES


def theme_colours(name: Any) -> dict:
    """One canvas theme's ten values, or an empty table for any other name."""
    if not has_theme(name):
        return dict(NO_PALETTE)
    return dict(THEMES[name])


def tier_colours(name: Any) -> dict:
    """One tier palette's six values, or an empty table for any other name."""
    if not has_tier(name):
        return dict(NO_PALETTE)
    return dict(TIER_PALETTES[name])


def channels(colour: str) -> tuple[int, int, int, int]:
    """The red, green, blue and transparency numbers of one `#rrggbbaa` colour."""
    digits = colour.lstrip("#")
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
        int(digits[6:8], 16),
    )


def requested_name(name: Any) -> str:
    """The name a caller asked for, and the empty string for anything else.

    A caller sending a number, a list or nothing asks for no name rather
    than for the text of that value.
    """
    return name if isinstance(name, str) else NOT_ASKED


def build_view_model(
    name: Any = None, tier: Any = None, target_balance: Any = None
) -> dict:
    """Return every theme, every tier palette and the answers for one request.

    `name` carries the canvas theme a caller asked for and `tier` the
    tier palette. A name the table does not hold comes back under
    `unknown_theme` or `unknown_tier` with an empty table beside it.
    `target_balance` is mapped to a tier key; a value that cannot be
    compared with a number comes back under `tier_refusal` with the text
    the comparison raised. The balance is reported as its own text, so a
    whole number and a decimal are told apart and a value outside the
    JSON number range still crosses the bridge.
    """
    asked_theme = requested_name(name)
    asked_tier = requested_name(tier)
    tier_key, refusal = tier_answer(target_balance)
    return {
        "theme_names": list(THEME_NAMES),
        "tier_names": list(TIER_NAMES),
        "theme_field_names": list(THEME_FIELD_NAMES),
        "tier_field_names": list(TIER_FIELD_NAMES),
        "theme_colour_fields": list(THEME_COLOUR_FIELDS),
        "tier_colour_fields": list(TIER_COLOUR_FIELDS),
        "display_names": dict(DISPLAY_NAMES),
        "tier_display_names": dict(TIER_DISPLAY_NAMES),
        "themes": {key: dict(row) for key, row in THEMES.items()},
        "tier_palettes": {key: dict(row) for key, row in TIER_PALETTES.items()},
        "theme_channels": {
            key: {field: list(channels(row[field])) for field in THEME_COLOUR_FIELDS}
            for key, row in THEMES.items()
        },
        "tier_channels": {
            key: {field: list(channels(row[field])) for field in TIER_COLOUR_FIELDS}
            for key, row in TIER_PALETTES.items()
        },
        "tier_ceilings_usd": dict(TIER_CEILINGS_USD),
        "top_tier": TOP_TIER,
        "requested_theme": asked_theme,
        "requested_tier": asked_tier,
        "theme": theme_colours(asked_theme),
        "tier_palette": tier_colours(asked_tier),
        "unknown_theme": [] if has_theme(asked_theme) else [asked_theme],
        "unknown_tier": [] if has_tier(asked_tier) else [asked_tier],
        "target_balance_text": repr(target_balance),
        "tier": tier_key,
        "tier_refusal": refusal,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``visualizer_themes.state``.

    Reads ``name``, ``tier`` and ``target_balance`` from the request
    parameters. The two tables are the same on every call, so there is no
    state to reset.
    """
    return build_view_model(
        params.get("name"), params.get("tier"), params.get("target_balance")
    )
