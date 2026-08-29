"""Whether the host running the tests exposes a font database.

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

FALSIFICATION
=============
Wrong if (a) ``QFontDatabase.families()`` names families the painter
cannot use, so a true answer no longer means a proportional advance,
or (b) it is called before a ``QApplication`` exists, when Qt has not
yet built the database. Callers construct the application first.
"""

from __future__ import annotations


def has_real_fonts() -> bool:
    """True when the platform exposes a font database.

    Imported by every parity test whose picture comparison changes
    direction with the host's fonts.
    """
    from PySide6.QtGui import QFontDatabase

    return len(QFontDatabase.families()) > 0
