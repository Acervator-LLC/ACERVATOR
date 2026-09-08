"""The Simulator's data path: RA-StoneTablet files, read only.

``TabletSource`` answers ``root``, ``entries``, ``entry_for``, ``newest`` and
``candles`` from the files under ``RA_STONE_TABLETS_DIR``. It holds no venue
and defines no write, and ``__getattr__`` raises ``SendRefused`` for every
other name, so an order, a cancellation or a venue write cannot be expressed
through it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..trading.stone_tablets.ra_paths import RA_STONE_TABLETS_DIR
from ..trading.stone_tablets.storage import TabletEntry, read_manifest, read_tablet

TABLET_SUFFIX = ".json"

#: Every name ``TabletSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = ("root", "entries", "entry_for", "newest", "candles")


class SendRefused(AttributeError):
    """Raised when a name outside ``READ_NAMES`` is asked of ``TabletSource``."""


def tablet_key(entry: TabletEntry) -> str:
    """``entry.file`` without its ``.json`` suffix."""
    name = entry.file
    return name[: -len(TABLET_SUFFIX)] if name.endswith(TABLET_SUFFIX) else name


class TabletSource:
    """The RA-StoneTablets on disk, as MANIFEST rows and candle rows."""

    def __init__(self, root: Optional[Path] = None) -> None:
        """Read from ``root``, or from ``RA_STONE_TABLETS_DIR`` when it is None."""
        self._root = Path(root) if root is not None else RA_STONE_TABLETS_DIR

    def root(self) -> Path:
        """The directory ``entries`` and ``candles`` read."""
        return self._root

    def entries(self) -> list[TabletEntry]:
        """Every MANIFEST row under ``root``, by asset, year then exchange_id."""
        return sorted(
            read_manifest(self._root),
            key=lambda entry: (entry.asset, entry.year, entry.exchange_id),
        )

    def entry_for(self, key: str) -> Optional[TabletEntry]:
        """The entry whose ``tablet_key`` is ``key``, or None."""
        for entry in self.entries():
            if tablet_key(entry) == key:
                return entry
        return None

    def newest(self) -> Optional[TabletEntry]:
        """The entry with the latest ``last_ts_ms``; a tie breaks on the key."""
        rows = self.entries()
        if not rows:
            return None
        return max(rows, key=lambda entry: (entry.last_ts_ms, tablet_key(entry)))

    def candles(self, entry: TabletEntry) -> list[list[float]]:
        """``entry``'s ``[ts_ms, open, high, low, close, volume]`` rows.

        An unreadable or absent tablet answers an empty list.
        """
        tablet = read_tablet(self._root / entry.file)
        return [list(row) for row in tablet.candles] if tablet is not None else []

    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"TabletSource answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )


__all__ = [
    "READ_NAMES",
    "SendRefused",
    "TabletSource",
    "tablet_key",
]
