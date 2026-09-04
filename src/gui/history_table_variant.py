# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""history_table_variant.py -- pick the History table the build asked for.

``HistoryTab`` holds one table and does not care which. The React panel and
the Qt table answer the same three calls, so the choice is made once, here,
from the variant the build stamped in.

The import is deferred into the call rather than taken at module import.
The React panel pulls in ``QtWebEngineWidgets`` and the Qt table pulls in
``QtWidgets``; importing both to use one would make every run pay for the
half it does not draw, and would make a missing WebEngine an import error
for the variant that never wanted it.
"""

from __future__ import annotations

from src._variant import QT, resolve_variant


def history_table_class(variant: str | None = None):
    """Return the History table class for ``variant``, resolving when None.

    Raises ImportError when the chosen variant's widget is unavailable,
    which is what ``HistoryTab`` already catches and logs around its table
    construction. Answering the other variant's widget instead would put a
    surface on screen that the build did not ask for, and the comparison
    the two builds exist for would be reading the same class twice.
    """
    chosen = resolve_variant() if variant is None else variant
    if chosen == QT:
        from .history_qt_table import HistoryQtTable

        return HistoryQtTable
    from .react_history_panel import HistoryWebTable

    return HistoryWebTable
