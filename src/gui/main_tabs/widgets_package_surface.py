"""widgets_package_surface.py -- the shared card and table skins as plain data.

Describes what ``src.gui.widgets`` builds for every widget in that folder:
the ``CardStyle`` skin, the two card presets the stock strip and the
analytics grid carry, the style sheets the card writes for its frame, its
caption and its amount, and the column setup the three bot tables share.
Colours, type sizes, paddings and radii come from ``design_system``
tokens, so a page carries the values the Qt widgets paint rather than a
second palette.

It also holds the behaviour the package owns rather than describes: the
text one amount renders, the per-call colour that overrides a skin, the
column widths a spec fixes and the ones it lets stretch, and the header
tooltips a spec attaches.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``widgets_package.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any
frontend.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .. import design_system as ds

METHOD = "widgets_package.state"

DEFAULT_VALUE = "---"
EMPTY_TEXT = ""

FRAME_SHAPE = "StyledPanel"
NO_FRAME_STYLE = ""

CARD_CLASS_NAME = "StatCard"
TABLE_CLASS_NAME = "ColumnarTableWidget"

BORDER_WIDTH_PX = 1
BORDER_KIND = "solid"
VALUE_WEIGHT = "bold"

RESIZE_STRETCH = "Stretch"
RESIZE_FIXED = "Fixed"
SELECTION_BEHAVIOUR = "SelectRows"
EDIT_TRIGGERS = "NoEditTriggers"
ALTERNATING_ROW_COLOURS = True
VERTICAL_HEADER_VISIBLE = False

# Qt stores a pixel count in a 32-bit signed integer and refuses anything
# that does not fit.
PIXEL_MIN = -(2**31)
PIXEL_MAX = 2**31 - 1

PADDING_PARTS = 4

DEFAULT_LABEL_COLOUR = ds.TEXT_MED
DEFAULT_VALUE_COLOUR = ds.TEXT_HIGH
DEFAULT_LABEL_SIZE_PX = ds.TYPE_CAPTION
DEFAULT_VALUE_SIZE_PX = ds.TYPE_CARD_VALUE
DEFAULT_PADDING_PX = (ds.SPACE_S, ds.SPACE_S, ds.SPACE_S, ds.SPACE_S)
DEFAULT_SPACING_PX = ds.SPACE_XXS
DEFAULT_SURFACE = None
DEFAULT_BORDER = None
DEFAULT_RADIUS_PX = ds.RADIUS_SM
DEFAULT_ACCESSIBLE_NAME = "Stat Card"

CARD_FIELDS = (
    "label_color",
    "value_color",
    "label_size",
    "value_size",
    "padding",
    "spacing",
    "surface",
    "border",
    "radius",
    "accessible_name",
)

CARD_DEFAULTS: dict = {
    "label_size": DEFAULT_LABEL_SIZE_PX,
    "value_size": DEFAULT_VALUE_SIZE_PX,
    "padding": DEFAULT_PADDING_PX,
    "spacing": DEFAULT_SPACING_PX,
    "surface": DEFAULT_SURFACE,
    "border": DEFAULT_BORDER,
    "radius": DEFAULT_RADIUS_PX,
    "accessible_name": DEFAULT_ACCESSIBLE_NAME,
}

SPEC_FIELDS = ("labels", "tooltips", "fixed_widths", "accessible_name")

SPEC_DEFAULTS: dict = {
    "tooltips": {},
    "fixed_widths": {},
    "accessible_name": EMPTY_TEXT,
}

EXPORTED_NAMES = (
    "CardStyle",
    "ColumnSpec",
    "ColumnarTableWidget",
    "METRIC_CARD",
    "STOCK_CARD",
    "StatCard",
)

VALUE_SET = "value_set"
VALUE_RECOLOURED = "value_recoloured"
VALUE_KEPT_SKIN_COLOUR = "value_kept_skin_colour"
CARD_BUILT = "card_built"
FRAME_SKINNED = "frame_skinned"
FRAME_LEFT_PLAIN = "frame_left_plain"
TABLE_BUILT = "table_built"
TABLE_NAMED = "table_named"
TABLE_UNNAMED = "table_unnamed"
COLUMN_FIXED = "column_fixed"
COLUMN_STRETCHED = "column_stretched"
WIDTH_OFF_THE_END = "width_off_the_end"
TOOLTIP_SET = "tooltip_set"
TOOLTIP_OFF_THE_END = "tooltip_off_the_end"

CALL_NAMES = (
    VALUE_SET,
    VALUE_RECOLOURED,
    VALUE_KEPT_SKIN_COLOUR,
    CARD_BUILT,
    FRAME_SKINNED,
    FRAME_LEFT_PLAIN,
    TABLE_BUILT,
    TABLE_NAMED,
    TABLE_UNNAMED,
    COLUMN_FIXED,
    COLUMN_STRETCHED,
    WIDTH_OFF_THE_END,
    TOOLTIP_SET,
    TOOLTIP_OFF_THE_END,
)

ACTIONS: dict = {}
SIGNALS: tuple = ()
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
THREADS: tuple = ()


def built_text(value: Any, part: str) -> str:
    """The text one built part carries, refusing what a label refuses.

    ``None`` builds an empty part. Anything that is not text is refused,
    naming the part and the type it was given, so a caller cannot build a
    card the Qt side would reject.
    """
    if value is None:
        return EMPTY_TEXT
    if not isinstance(value, str):
        raise TypeError(f"a card {part} is built from text, not {type(value).__name__}")
    return value


def table_name(value: Any) -> str:
    """The accessible name one table carries.

    A falsy name leaves the table unnamed rather than refusing, which is
    what the shipped table does with it.
    """
    if not value:
        return EMPTY_TEXT
    if not isinstance(value, str):
        raise TypeError(f"a table accessible name is text, not {type(value).__name__}")
    return value


def header_text(value: Any) -> str:
    """The header one column label carries.

    A label that is not text leaves the header blank rather than
    refusing, which is what the shipped table does with it.
    """
    return value if isinstance(value, str) else EMPTY_TEXT


def pixel_count(value: Any, part: str) -> int:
    """One layout number as the whole pixel count Qt stores.

    A decimal is cut towards zero and a true/false reads as one/zero,
    both as Qt does. Text and ``None`` are refused. A number outside the
    32-bit range Qt stores, and a not-a-number, are refused as too large.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        whole = value
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise OverflowError(f"a card {part} of {value} is not a pixel count")
        whole = int(value)
    else:
        raise TypeError(
            f"a card {part} is a whole number of pixels, not " f"{type(value).__name__}"
        )
    if whole < PIXEL_MIN or whole > PIXEL_MAX:
        raise OverflowError(f"a card {part} of {whole} is beyond what Qt stores")
    return whole


def padding_pixels(value: Any, part: str = "padding") -> tuple:
    """The four margins one padding carries, in left, top, right, bottom.

    Refuses anything that is not exactly four numbers, which is what the
    Qt call refuses.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise TypeError(
            f"a card {part} is four whole numbers, not {type(value).__name__}"
        )
    if len(value) != PADDING_PARTS:
        raise TypeError(
            f"a card {part} is {PADDING_PARTS} whole numbers, not {len(value)}"
        )
    return tuple(pixel_count(one, part) for one in value)


def card_style(label_color: Any, value_color: Any, **named: Any) -> dict:
    """One card skin as plain data, with every field the shipped skin has.

    Unnamed fields take the shipped defaults. Numbers that reach a Qt
    layout call are refused here on the same terms Qt refuses them; the
    colours and the type sizes are written into a style sheet, which
    takes whatever it is given.
    """
    unknown = sorted(set(named) - set(CARD_FIELDS))
    if unknown:
        raise TypeError(f"a card skin has no field named {unknown[0]!r}")
    skin = dict(CARD_DEFAULTS)
    skin.update(named)
    skin["label_color"] = label_color
    skin["value_color"] = value_color
    # Same order as the shipped card: accessible name, padding, spacing.
    skin["accessible_name"] = built_text(skin["accessible_name"], "accessible name")
    padding_pixels(skin["padding"])
    pixel_count(skin["spacing"], "spacing")
    skin["padding"] = tuple(skin["padding"])
    return {name: skin[name] for name in CARD_FIELDS}


DEFAULT_CARD = card_style(
    label_color=DEFAULT_LABEL_COLOUR,
    value_color=DEFAULT_VALUE_COLOUR,
)

STOCK_CARD = card_style(
    label_color=ds.CARD_STOCK_LABEL,
    value_color=ds.CARD_STOCK_VALUE,
    padding=(
        ds.SPACE_CARD_PAD,
        ds.SPACE_CARD_TIGHT,
        ds.SPACE_CARD_PAD,
        ds.SPACE_CARD_TIGHT,
    ),
    surface=ds.CARD_STOCK_SURFACE,
    border=ds.CARD_STOCK_BORDER,
    radius=ds.RADIUS_SM,
    accessible_name="Stock Stat Card",
)

METRIC_CARD = card_style(
    label_color=ds.CARD_METRIC_LABEL,
    value_color=ds.TEXT_HIGH,
    padding=(
        ds.SPACE_CARD_TIGHT,
        ds.SPACE_S,
        ds.SPACE_CARD_TIGHT,
        ds.SPACE_S,
    ),
    surface=ds.CARD_METRIC_SURFACE,
    border=ds.CARD_METRIC_BORDER,
    radius=ds.RADIUS_CARD,
    accessible_name="Metric Card",
)

PRESETS = {"default": DEFAULT_CARD, "stock": STOCK_CARD, "metric": METRIC_CARD}


def frame_style_sheet(skin: dict, class_name: str = CARD_CLASS_NAME) -> str:
    """The frame rule one card writes, keyed on its own runtime class name.

    A skin with no surface writes nothing, which leaves the application
    style sheet to paint the card.
    """
    if skin["surface"] is None:
        return NO_FRAME_STYLE
    return (
        f"{class_name} {{ background: {skin['surface']}; "
        f"border: {BORDER_WIDTH_PX}px {BORDER_KIND} {skin['border']}; "
        f"border-radius: {skin['radius']}px; }}"
    )


def label_style_sheet(skin: dict) -> str:
    """The rule one card writes for its caption."""
    return f"color: {skin['label_color']}; font-size: {skin['label_size']}px;"


def value_style_sheet(skin: dict, colour: Any = None) -> str:
    """The rule one card writes for its amount.

    ``colour`` overrides the skin's own value colour for this rule only;
    the type size and the weight are unchanged.
    """
    painted = colour or skin["value_color"]
    return (
        f"color: {painted}; "
        f"font-size: {skin['value_size']}px; "
        f"font-weight: {VALUE_WEIGHT};"
    )


def card_layout(skin: dict) -> dict:
    """The margins and the gap one card asks its column layout for.

    ``asked`` is the value the card hands the layout; the pixel count is
    what Qt keeps of it, with a decimal cut towards zero. Qt reports a
    negative gap back as the platform's own default, so the asked value
    is the one that states a product decision.
    """
    return {
        "margins_asked": list(skin["padding"]),
        "spacing_asked": skin["spacing"],
        "margins_px": list(padding_pixels(skin["padding"])),
        "spacing_px": pixel_count(skin["spacing"], "spacing"),
    }


class CardModel:
    """One shared stat card's state, with no Qt object behind it.

    Holds the skin, the caption, the amount, the colour the amount is
    painted in, and the calls the card has made, so a drive can be read
    step by step.
    """

    def __init__(
        self,
        label: Any,
        value: Any = DEFAULT_VALUE,
        skin: Optional[dict] = None,
    ) -> None:
        self.skin: dict = dict(skin or DEFAULT_CARD)
        self.label_text: str = built_text(label, "label")
        self.value_text: str = built_text(value, "value")
        self.value_colour: Any = self.skin["value_color"]
        self.calls: list = [CARD_BUILT]
        self.calls.append(
            FRAME_LEFT_PLAIN if self.skin["surface"] is None else FRAME_SKINNED
        )

    def set_value(self, value: Any, colour: Any = None) -> None:
        """Show ``value``, printed as text, in ``colour`` or the skin's own."""
        self.value_text = str(value)
        self.calls.append(VALUE_SET)
        if colour:
            self.calls.append(VALUE_RECOLOURED)
            self.value_colour = colour
        else:
            self.calls.append(VALUE_KEPT_SKIN_COLOUR)
            self.value_colour = self.skin["value_color"]

    def state(self, class_name: str = CARD_CLASS_NAME) -> dict:
        """The whole card as one serialisable dict."""
        return {
            "class_name": class_name,
            "accessible_name": self.skin["accessible_name"],
            "frame_shape": FRAME_SHAPE,
            "frame_style_sheet": frame_style_sheet(self.skin, class_name),
            "layout": card_layout(self.skin),
            "label": {
                "text": self.label_text,
                "style_sheet": label_style_sheet(self.skin),
            },
            "value": {
                "text": self.value_text,
                "style_sheet": value_style_sheet(self.skin, self.value_colour),
                "default_text": DEFAULT_VALUE,
            },
            "skin": dict(self.skin),
            "calls": list(self.calls),
        }


def column_spec(labels: Any, **named: Any) -> dict:
    """One table's columns as plain data, with the shipped defaults.

    Refuses a field the shipped spec does not carry, and refuses labels
    that cannot be counted, which is what the Qt call refuses.
    """
    unknown = sorted(set(named) - set(SPEC_FIELDS))
    if unknown:
        raise TypeError(f"a column spec has no field named {unknown[0]!r}")
    spec = dict(SPEC_DEFAULTS)
    spec.update(named)
    # Same order as the shipped table: accessible name, then labels.
    spec["accessible_name"] = table_name(spec["accessible_name"])
    spec["labels"] = tuple(labels)
    spec["tooltips"] = dict(spec["tooltips"])
    spec["fixed_widths"] = dict(spec["fixed_widths"])
    return {name: spec[name] for name in SPEC_FIELDS}


EMPTY_SPEC = column_spec(labels=())


def column_index(value: Any) -> int:
    """One column number as the whole number Qt indexes with."""
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, int):
        raise TypeError(
            f"a column number is a whole number, not {type(value).__name__}"
        )
    if value < PIXEL_MIN or value > PIXEL_MAX:
        raise OverflowError(f"a column number of {value} is beyond what Qt stores")
    return value


def numbered_columns(mapping: Any) -> dict:
    """One column-keyed mapping with its whole-number keys restored.

    A JSON object has text keys only, so a column number crosses the
    bridge as text. A key that is not a whole number is left as it came
    and refused later, where a Python caller's bad key is refused.
    """
    restored = {}
    for key, value in dict(mapping).items():
        if isinstance(key, str) and key.lstrip("-").isdigit():
            restored[int(key)] = value
        else:
            restored[key] = value
    return restored


class TableModel:
    """One shared bot table's columns, with no Qt object behind it.

    Holds the header for every column, the resize mode each one gets, the
    width the spec fixes, the tooltip it attaches, and the calls the
    table has made.
    """

    def __init__(self, spec: Optional[dict] = None) -> None:
        self.spec: dict = dict(spec or EMPTY_SPEC)
        self.calls: list = [TABLE_BUILT]
        self.column_count: int = len(self.spec["labels"])
        self.headers: list = [header_text(one) for one in self.spec["labels"]]
        self.resize_modes: list = [RESIZE_STRETCH] * self.column_count
        self.fixed_widths: dict = {}
        self.tooltips: list = [EMPTY_TEXT] * self.column_count
        self.accessible_name: str = self.spec["accessible_name"]
        self.calls.append(TABLE_UNNAMED if not self.accessible_name else TABLE_NAMED)
        self._fix_widths()
        self._attach_tooltips()

    def _fix_widths(self) -> None:
        """Fix the width of every column the spec names, in spec order."""
        for column, width in self.spec["fixed_widths"].items():
            at = column_index(column)
            pixels = pixel_count(width, "column width")
            if not 0 <= at < self.column_count:
                self.calls.append(WIDTH_OFF_THE_END)
                continue
            self.calls.append(COLUMN_FIXED)
            self.resize_modes[at] = RESIZE_FIXED
            self.fixed_widths[at] = pixels

    def _attach_tooltips(self) -> None:
        """Attach a tooltip to every header the spec names that exists."""
        for column, tip in self.spec["tooltips"].items():
            at = column_index(column)
            text = built_text(tip, "header tooltip")
            if not 0 <= at < self.column_count:
                self.calls.append(TOOLTIP_OFF_THE_END)
                continue
            self.calls.append(TOOLTIP_SET)
            self.tooltips[at] = text

    def stretched_columns(self) -> list:
        """Every column the spec left to stretch."""
        self.calls.append(COLUMN_STRETCHED)
        return [
            at for at, mode in enumerate(self.resize_modes) if mode == RESIZE_STRETCH
        ]

    def state(self) -> dict:
        """The whole table as one serialisable dict."""
        return {
            "class_name": TABLE_CLASS_NAME,
            "accessible_name": self.accessible_name,
            "column_count": self.column_count,
            "headers": list(self.headers),
            "resize_modes": list(self.resize_modes),
            "fixed_widths": {str(at): w for at, w in self.fixed_widths.items()},
            "tooltips": list(self.tooltips),
            "alternating_row_colours": ALTERNATING_ROW_COLOURS,
            "selection_behaviour": SELECTION_BEHAVIOUR,
            "edit_triggers": EDIT_TRIGGERS,
            "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
            "spec": {
                "labels": list(self.spec["labels"]),
                "tooltips": {str(k): v for k, v in self.spec["tooltips"].items()},
                "fixed_widths": {
                    str(k): v for k, v in self.spec["fixed_widths"].items()
                },
                "accessible_name": self.spec["accessible_name"],
            },
            "calls": list(self.calls),
        }


def build_view_model(card: CardModel, table: TableModel, class_name: str) -> dict:
    """Return the card, the table and the package's presets as one dict."""
    return {
        "card": card.state(class_name),
        "table": table.state(),
        "presets": {name: dict(skin) for name, skin in PRESETS.items()},
        "card_fields": list(CARD_FIELDS),
        "card_defaults": {
            "label_size": DEFAULT_LABEL_SIZE_PX,
            "value_size": DEFAULT_VALUE_SIZE_PX,
            "padding": list(DEFAULT_PADDING_PX),
            "spacing": DEFAULT_SPACING_PX,
            "surface": DEFAULT_SURFACE,
            "border": DEFAULT_BORDER,
            "radius": DEFAULT_RADIUS_PX,
            "accessible_name": DEFAULT_ACCESSIBLE_NAME,
        },
        "spec_fields": list(SPEC_FIELDS),
        "spec_defaults": {
            "tooltips": {},
            "fixed_widths": {},
            "accessible_name": EMPTY_TEXT,
        },
        "exported_names": list(EXPORTED_NAMES),
        "limits": {
            "card_class_name": CARD_CLASS_NAME,
            "table_class_name": TABLE_CLASS_NAME,
            "border_width_px": BORDER_WIDTH_PX,
            "border_kind": BORDER_KIND,
            "value_weight": VALUE_WEIGHT,
            "resize_stretch": RESIZE_STRETCH,
            "resize_fixed": RESIZE_FIXED,
            "pixel_min": PIXEL_MIN,
            "pixel_max": PIXEL_MAX,
            "padding_parts": PADDING_PARTS,
            "empty_text": EMPTY_TEXT,
            "no_frame_style": NO_FRAME_STYLE,
        },
        "actions": dict(ACTIONS),
        "signals": list(SIGNALS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "threads": list(THREADS),
        "call_names": list(CALL_NAMES),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``widgets_package.state``.

    Builds one card from ``label``, ``value`` and a named ``preset`` or an
    inline ``skin``, then one table from an inline ``spec``. ``set_value``
    drives the card's one behaviour, and ``class_name`` names the runtime
    class the frame rule is keyed on.
    """
    asked = params or {}
    named = asked.get("preset")
    skin = asked.get("skin")
    if skin is not None:
        chosen = card_style(**skin)
    elif named is not None:
        if named not in PRESETS:
            raise KeyError(f"no card preset named {named!r}")
        chosen = PRESETS[named]
    else:
        chosen = DEFAULT_CARD
    card = CardModel(asked.get("label"), asked.get("value", DEFAULT_VALUE), chosen)
    if "set_value" in asked:
        card.set_value(asked["set_value"], asked.get("set_colour"))
    spec = asked.get("spec")
    if spec is not None:
        spec = dict(spec)
        spec["tooltips"] = numbered_columns(spec.get("tooltips", {}))
        spec["fixed_widths"] = numbered_columns(spec.get("fixed_widths", {}))
    table = TableModel(column_spec(**spec) if spec is not None else None)
    if asked.get("stretched"):
        table.stretched_columns()
    return build_view_model(card, table, asked.get("class_name", CARD_CLASS_NAME))
