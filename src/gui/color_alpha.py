"""The one way a colour in this repository carries transparency.

``rgba`` writes the alpha Qt reads: a byte running to 255. ``css_alpha``,
``css_rgba`` and ``css_colours`` rewrite that byte as the 0-to-1 share a
browser reads, so a surface can hand a renderer the same colour without
the engine painting it opaque.
"""

from __future__ import annotations

import colorsys
import re
from typing import Any

__all__ = ["coin_disc_color", "css_alpha", "css_colours", "css_rgba", "rgba"]

HUE_WHEEL = 360
DISC_SATURATION = 120
DISC_VALUE = 180

RGBA_FORMAT = "rgba({red},{green},{blue},{alpha})"

SHORT_HEX_DIGITS = 3
LONG_HEX_DIGITS = 6
CHANNEL_DIGITS = 2
HEX_RADIX = 16
ALPHA_LOWEST = 0
ALPHA_HIGHEST = 255

CSS_ALPHA_HIGHEST = 1
CSS_ALPHA_UNIT = 1.0 / ALPHA_HIGHEST

RGBA_CALL = re.compile(r"rgba\(([^()]*)\)")
RGBA_FIELDS = 4
ALPHA_AT = 3
FIELD_SPLIT = ","


def rgba(color: str, alpha: int) -> str:
    """One ``#rgb`` or ``#rrggbb`` colour as an ``rgba`` value under Qt's alpha byte."""
    if isinstance(alpha, bool) or not isinstance(alpha, int):
        raise ValueError(f"alpha {alpha!r} is not a whole number")
    if not ALPHA_LOWEST <= alpha <= ALPHA_HIGHEST:
        raise ValueError(f"alpha {alpha!r} is outside {ALPHA_LOWEST}-{ALPHA_HIGHEST}")
    digits = str(color).strip().lstrip("#")
    if len(digits) == SHORT_HEX_DIGITS:
        digits = "".join(one * CHANNEL_DIGITS for one in digits)
    if len(digits) != LONG_HEX_DIGITS:
        raise ValueError(f"colour {color!r} is not #rgb or #rrggbb")
    try:
        channels = [
            int(digits[at : at + CHANNEL_DIGITS], HEX_RADIX)
            for at in range(0, LONG_HEX_DIGITS, CHANNEL_DIGITS)
        ]
    except ValueError:
        raise ValueError(f"colour {color!r} is not #rgb or #rrggbb") from None
    return RGBA_FORMAT.format(
        red=channels[0],
        green=channels[1],
        blue=channels[2],
        alpha=alpha,
    )


def coin_disc_color(symbol: str) -> str:
    """The ``#rrggbb`` disc a coin badge paints for ``symbol`` when no logo is cached.

    ``_get_coin_icon`` and both bot tables read this one function, so the disc
    the Qt widget paints and the disc the renderer module draws cannot drift.
    """
    hue = sum(ord(char) for char in str(symbol)) % HUE_WHEEL
    red, green, blue = colorsys.hsv_to_rgb(
        hue / HUE_WHEEL, DISC_SATURATION / ALPHA_HIGHEST, DISC_VALUE / ALPHA_HIGHEST
    )
    return "#{:02x}{:02x}{:02x}".format(
        round(red * ALPHA_HIGHEST),
        round(green * ALPHA_HIGHEST),
        round(blue * ALPHA_HIGHEST),
    )


def css_alpha(alpha: float) -> float:
    """One Qt alpha byte as the share of full opacity a browser reads."""
    return alpha * CSS_ALPHA_UNIT


def _css_call(found: re.Match) -> str:
    fields = [part.strip() for part in found.group(1).split(FIELD_SPLIT)]
    if len(fields) != RGBA_FIELDS:
        return found.group(0)
    try:
        alpha = float(fields[ALPHA_AT])
    except ValueError:
        return found.group(0)
    if alpha <= CSS_ALPHA_HIGHEST:
        return found.group(0)
    fields[ALPHA_AT] = repr(css_alpha(alpha))
    return RGBA_FORMAT.format(
        red=fields[0],
        green=fields[1],
        blue=fields[2],
        alpha=fields[ALPHA_AT],
    )


def css_rgba(text: str) -> str:
    """One style value with every Qt alpha byte written as the share CSS reads.

    An alpha of one or less is already a share and is left alone, which
    is why an all-but-invisible Qt byte of 1 cannot be told from a fully
    opaque share and stays as it arrived. Everything that is not the
    fourth field of an ``rgba`` call is carried through untouched, so a
    Qt-only value such as ``qlineargradient`` keeps its own shape.
    """
    return RGBA_CALL.sub(_css_call, text)


def css_colours(value: Any) -> Any:
    """One published view model with every Qt alpha byte rewritten for CSS.

    A surface calls this on the payload it hands the renderer. Every
    string inside is rewritten by `css_rgba` and every other value is
    returned as it arrived, so the colours a browser paints from and the
    colours Qt paints from stay one table with two readings.
    """
    if isinstance(value, str):
        return css_rgba(value)
    if isinstance(value, dict):
        return {key: css_colours(item) for key, item in value.items()}
    if isinstance(value, list):
        return [css_colours(item) for item in value]
    if isinstance(value, tuple):
        return tuple(css_colours(item) for item in value)
    return value
