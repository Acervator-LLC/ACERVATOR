"""The one way a colour in this repository carries transparency."""

from __future__ import annotations

__all__ = ["rgba"]

RGBA_FORMAT = "rgba({red},{green},{blue},{alpha})"

SHORT_HEX_DIGITS = 3
LONG_HEX_DIGITS = 6
CHANNEL_DIGITS = 2
HEX_RADIX = 16
ALPHA_LOWEST = 0
ALPHA_HIGHEST = 255


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
