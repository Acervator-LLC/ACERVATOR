"""WCAG 2.1 contrast arithmetic, declared once for every surface that audits a colour.

``contrast_ratio`` carries the published relative-luminance formula and
``validate_contrast`` applies ``AA_FLOOR`` or ``AA_LARGE_FLOOR``.
``src.design_system`` imports all four names back for ``contrast_self_test`` and
for the manual build. ``src.gui.theme_engine`` measures a typed accent against
the theme's own ground in ``accented``, and this module imports neither
matplotlib nor Qt.
"""

from __future__ import annotations

#: The contrast floor WCAG 2.1 SC 1.4.3 sets for normal text.
AA_FLOOR = 4.5

#: The contrast floor SC 1.4.3 sets for large text.
AA_LARGE_FLOOR = 3.0

#: The digit count of the ``#rgb`` form, which doubles into ``#rrggbb``.
SHORT_HEX_DIGITS = 3
CHANNEL_DIGITS = 2


def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    """Return the three 0-to-1 channels of ``hex_str``, in ``#rgb`` or ``#rrggbb``."""
    h = hex_str.lstrip("#")
    if len(h) == SHORT_HEX_DIGITS:
        h = "".join(digit * CHANNEL_DIGITS for digit in h)
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def _relative_luminance(rgb):
    """Return the WCAG 2.1 relative luminance of ``rgb``."""

    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """Return the contrast ratio of ``fg`` against ``bg``, from 1 to 21."""
    l1 = _relative_luminance(_hex_to_rgb(fg))
    l2 = _relative_luminance(_hex_to_rgb(bg))
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def validate_contrast(fg: str, bg: str, large_text: bool = False) -> tuple[bool, float]:
    """Return whether ``fg`` on ``bg`` clears the AA floor, and the measured ratio.

    ``large_text`` lowers that floor from ``AA_FLOOR`` to ``AA_LARGE_FLOOR``.
    """
    ratio = contrast_ratio(fg, bg)
    threshold = AA_LARGE_FLOOR if large_text else AA_FLOOR
    return ratio >= threshold, round(ratio, 2)
