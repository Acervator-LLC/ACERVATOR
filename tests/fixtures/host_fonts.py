"""Whether the host running the tests exposes a font database, and the
two guards that skip a test the answer makes invalid.

The offscreen platform takes its font database from the host: none
under ``QT_QPA_PLATFORM=offscreen`` on a Windows host, populated on a
Linux host with fontconfig. With none every family resolves to a box
font advancing one em per character, so two strings of equal length
paint the same picture whatever they say.

The platform itself comes from ``tests/conftest.py``. This module reads
the font state and never chooses it.

A parity test that compares rendered pictures asks this before it
decides which way its comparison must go. Importing this is the only
supported way to ask -- a test that asserts a fixed answer pins the
machine it was written on and fails on every other host.

    from tests.fixtures.host_fonts import has_real_fonts

A test whose claim holds in one font state only carries one of the two
guards instead of branching. A guard reads the state at call time,
after the run's font choice is applied, so a hand-written guard keyed
on anything else is never needed.

    from tests.fixtures.host_fonts import skip_unless_no_fonts

``NARROW_LABEL`` and ``WIDE_LABEL`` are the pair such a guard measures,
four narrow letters against four wide ones, and
``app_font_advance_px`` measures them in the application font. A font a
surface names for itself may be fixed-width -- the wire badge asks for
Consolas -- and under one no pair of equal-length strings separates,
whatever the host's font database says.

``ACERVATOR_TEST_FONTS=1`` loads DejaVu Sans into the offscreen driver,
so a host that ships no fonts runs the same file in both states. The
file comes from matplotlib, which lives in the ``charts`` extra and is
absent from the CI fast lane. Without it the loader lends nothing and
the run keeps the fonts the host itself ships.

FALSIFICATION
=============
Wrong if (a) ``QFontDatabase.families()`` names families the painter
cannot use, so a true answer no longer means a proportional advance,
(b) ``load_run_fonts`` reaches no ``QApplication``, when Qt has not yet
built the database and every guard reads no fonts, or (c) a guard is
applied to a test whose claim in fact holds in both states, which no
run would report because the guard only ever skips, or (d) the
application font is itself fixed-width, so ``NARROW_LABEL`` and
``WIDE_LABEL`` measure alike on a run that holds fonts, or (e)
importing this module changes ``QT_QPA_PLATFORM``.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

import pytest

FONT_ENV = "ACERVATOR_TEST_FONTS"

NARROW_LABEL = "iiii"
WIDE_LABEL = "WWWW"

_loaded_families: list[str] = []


def lendable_font_file() -> Path | None:
    """The font file this host can lend, or None when it has none.

    matplotlib ships DejaVu Sans and lives in the ``charts`` extra,
    which the CI fast lane does not install. An absent package is a
    None, never an error: lending is a convenience for a host with no
    fonts of its own.
    """
    try:
        import matplotlib
    except ImportError:
        return None
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    return ttf if ttf.is_file() else None


def load_run_fonts() -> bool:
    """Build the application object and apply this run's font choice.

    ``ACERVATOR_TEST_FONTS=1`` adds DejaVu Sans to the offscreen driver
    and makes it the application font. Loads at most once per process.
    True when this run holds a lent family. False when the run did not
    ask, or when no font file was found -- the caller then keeps the
    fonts the host itself ships.
    """
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication([])
    if os.environ.get(FONT_ENV) != "1":
        return False
    if _loaded_families:
        return True
    ttf = lendable_font_file()
    if ttf is None:
        return False
    handle = QFontDatabase.addApplicationFont(str(ttf))
    families = QFontDatabase.applicationFontFamilies(handle)
    if not families:
        return False
    QApplication.setFont(QFont(families[0], 9))
    _loaded_families.extend(families)
    return True


def _families() -> list[str]:
    """The families the platform names right now."""
    from PySide6.QtGui import QFontDatabase

    return list(QFontDatabase.families())


def has_real_fonts() -> bool:
    """True when the platform exposes a font database.

    Imported by every parity test whose picture comparison changes
    direction with the host's fonts.
    """
    return bool(_families())


def app_font_advance_px(text: str) -> int:
    """The printed width of `text` in the application font.

    The font a surface names for its own widgets may be fixed-width,
    where every glyph carries one advance. The application font is the
    proportional one, and the pair a font-state guard measures is
    measured here.
    """
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QFontMetrics(QApplication.font()).horizontalAdvance(text)


def missing_font_source() -> str:
    """Why this run holds no font database, named so a skip is actionable.

    Read by the real-fonts guard. A test that needs glyphs and does not
    get them says which of the two lending steps was absent instead of
    reporting only that the database is empty.
    """
    if os.environ.get(FONT_ENV) != "1":
        return "%s is not set to 1, so no font file was lent" % FONT_ENV
    if lendable_font_file() is None:
        return (
            "%s=1 but DejaVuSans.ttf was not found; it ships with "
            "matplotlib, which is in the charts extra" % FONT_ENV
        )
    return "a font file was lent and the platform still names no family"


def _guard(test, wanted: bool):
    """Wrap `test` so it skips when the run's font state is not `wanted`."""

    @functools.wraps(test)
    def guarded(*args, **kwargs):
        load_run_fonts()
        found = has_real_fonts()
        if found is not wanted:
            if wanted:
                reason = "needs a run with a font database; %s" % missing_font_source()
            else:
                reason = (
                    "needs a run without a font database; this run names "
                    "%d families" % len(_families())
                )
            pytest.skip(reason)
        return test(*args, **kwargs)

    return guarded


def skip_unless_no_fonts(test):
    """Skip `test` unless the run has no font database.

    Carries a claim that holds only where every family is a box font,
    such as two strings of equal length measuring the same width.
    """
    return _guard(test, wanted=False)


def skip_unless_real_fonts(test):
    """Skip `test` unless the run has a font database.

    Carries a claim that holds only where glyphs decide their own
    width, such as a measured string fitting a real display.
    """
    return _guard(test, wanted=True)
