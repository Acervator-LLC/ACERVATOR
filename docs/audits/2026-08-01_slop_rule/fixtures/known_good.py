"""Fixture: zero slop defects. Should produce 0 findings.

- Try/except used sparingly (below 3× threshold).
- Short functions.
- Small file.
"""

from __future__ import annotations


def get_value(text: str) -> int | None:
    """Parse an int or return None cleanly."""
    try:
        return int(text)
    except ValueError:
        return None


def use_it() -> None:
    print(get_value("42"))
