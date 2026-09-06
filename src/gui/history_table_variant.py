# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""history_table_variant.py -- pick the History table the build asked for.

``HistoryTab`` holds one table and does not care which. The React panel and
the Qt table answer the same three calls, so the choice is made once, by
``variant_surface`` under the name ``HISTORY_TABLE``.
"""

from __future__ import annotations

from .variant_surface import HISTORY_TABLE, surface_class


def history_table_class(variant: str | None = None):
    """Return the History table class for ``variant``, resolving when None.

    Raises ImportError when the chosen variant's widget is unavailable,
    which is what ``HistoryTab`` already catches and logs around its table
    construction.
    """
    return surface_class(HISTORY_TABLE, variant)
