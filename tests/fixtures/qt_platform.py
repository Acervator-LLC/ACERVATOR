"""The Qt platform plugin the test process paints on.

``tests/conftest.py`` calls ``choose_qt_platform`` before pytest imports
any test module. Importing this module chooses nothing.
"""

from __future__ import annotations

import os

QT_PLATFORM_ENV = "QT_QPA_PLATFORM"

DEFAULT_QT_PLATFORM = "offscreen"


def resolve_qt_platform(requested: str | None) -> str:
    """Return the platform plugin name for a caller that asked for `requested`.

    A named platform comes back unchanged, so a CI job environment or an
    explicit local choice wins. None or blank returns
    ``DEFAULT_QT_PLATFORM``.
    """
    named = (requested or "").strip()
    return named or DEFAULT_QT_PLATFORM


def choose_qt_platform() -> str:
    """Write the resolved platform into the environment and return it.

    Assignment, not setdefault: a module-level setdefault reached later
    in the run cannot change what this wrote.
    """
    chosen = resolve_qt_platform(os.environ.get(QT_PLATFORM_ENV))
    os.environ[QT_PLATFORM_ENV] = chosen
    return chosen
