"""Whether the host running the tests exposes a font database, and the
two guards that skip a test the answer makes invalid.

The offscreen platform takes its font database from the host: none
under ``QT_QPA_PLATFORM=offscreen`` on a Windows host, populated on a
Linux host with fontconfig. With none every family resolves to a box
font advancing one em per character, so two strings of equal length
paint the same picture whatever they say.

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

``ACERVATOR_TEST_FONTS=1`` loads DejaVu Sans into the offscreen driver,
so a host that ships no fonts runs the same file in both states.

FALSIFICATION
=============
Wrong if (a) ``QFontDatabase.families()`` names families the painter
cannot use, so a true answer no longer means a proportional advance,
(b) ``load_run_fonts`` reaches no ``QApplication``, when Qt has not yet
built the database and every guard reads no fonts, or (c) a guard is
applied to a test whose claim in fact holds in both states, which no
run would report because the guard only ever skips.
"""

from __future__ import annotations

import functools
import os

import pytest

# Must precede any QApplication construction. setdefault, not
# assignment: a caller that has already chosen a platform keeps it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FONT_ENV = "ACERVATOR_TEST_FONTS"

_loaded_families: list[str] = []


def load_run_fonts() -> None:
    """Build the application object and apply this run's font choice.

    ``ACERVATOR_TEST_FONTS=1`` adds DejaVu Sans to the offscreen driver
    and makes it the application font. Loads at most once per process,
    and does nothing when the run did not ask, so a host that already
    ships fonts keeps the ones it has.
    """
    from pathlib import Path

    import matplotlib
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication([])
    if os.environ.get(FONT_ENV) != "1" or _loaded_families:
        return
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    handle = QFontDatabase.addApplicationFont(str(ttf))
    families = QFontDatabase.applicationFontFamilies(handle)
    QApplication.setFont(QFont(families[0], 9))
    _loaded_families.extend(families)


def has_real_fonts() -> bool:
    """True when the platform exposes a font database.

    Imported by every parity test whose picture comparison changes
    direction with the host's fonts.
    """
    from PySide6.QtGui import QFontDatabase

    return len(QFontDatabase.families()) > 0


def _guard(test, wanted: bool):
    """Wrap `test` so it skips when the run's font state is not `wanted`."""

    @functools.wraps(test)
    def guarded(*args, **kwargs):
        load_run_fonts()
        found = has_real_fonts()
        if found is not wanted:
            pytest.skip(
                "needs a run %s a font database; this run has %s"
                % ("with" if wanted else "without", "one" if found else "none")
            )
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
