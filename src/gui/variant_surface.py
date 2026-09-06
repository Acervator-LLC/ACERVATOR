# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""One decision point for the Qt or the React build of a screen.

``register`` records a screen's two loaders. ``surface_class`` returns the
class the running variant selects and ``draws_react`` answers which side
that is. ``HISTORY`` is the only screen with both loaders today.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

from src._variant import QT, resolve_variant

HISTORY = "History"
HISTORY_TABLE = "History table"

Loader = Callable[[], type]

_LOADERS: Dict[str, Tuple[Loader, Loader]] = {}


def register(screen: str, qt_loader: Loader, react_loader: Loader) -> None:
    """Record the Qt loader and the React loader for ``screen``."""
    _LOADERS[screen] = (qt_loader, react_loader)


def screens() -> Tuple[str, ...]:
    """Every screen name ``register`` holds, in name order."""
    return tuple(sorted(_LOADERS))


def draws_react(screen: str, variant: str | None = None) -> bool:
    """True when ``variant`` selects the React loader for ``screen``.

    A ``variant`` of None asks ``resolve_variant`` for the running build.
    """
    chosen = resolve_variant() if variant is None else variant
    return chosen != QT and screen in _LOADERS


def surface_class(screen: str, variant: str | None = None) -> type:
    """Return the widget class ``screen`` builds under ``variant``.

    Raises KeyError for a screen ``register`` never recorded, and
    ImportError when the chosen side's widget cannot be imported.
    """
    qt_loader, react_loader = _LOADERS[screen]
    return react_loader() if draws_react(screen, variant) else qt_loader()


def _qt_history() -> type:
    """Import and return the Qt History tab."""
    from .history_tab import HistoryTab

    return HistoryTab


def _react_history() -> type:
    """Import and return the React History tab."""
    from .react_history_tab import HistoryReactTab

    return HistoryReactTab


def _qt_history_table() -> type:
    """Import and return the Qt History table."""
    from .history_qt_table import HistoryQtTable

    return HistoryQtTable


def _react_history_table() -> type:
    """Import and return the React History table."""
    from .react_history_panel import HistoryWebTable

    return HistoryWebTable


register(HISTORY, _qt_history, _react_history)
register(HISTORY_TABLE, _qt_history_table, _react_history_table)
