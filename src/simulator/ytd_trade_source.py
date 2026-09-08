"""The Simulator's YTD trade path: the trade files on disk, read only.

``YtdTradeSource`` answers ``root``, ``entries``, ``entry_for``, ``symbols``,
``trades`` and ``gaps`` from the files under ``get_ytd_root``. It holds no venue
and defines no write, and ``__getattr__`` raises ``SendRefused`` for every other
name, so an order, a cancellation or a venue write cannot be expressed through
it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..exchange.ytd_trade_store import (
    TradeGap,
    YtdFileEntry,
    YtdTrade,
    get_ytd_root,
    read_gaps,
    read_manifest,
    read_trade_file,
)
from .tablet_source import SendRefused

#: Every name ``YtdTradeSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = ("root", "entries", "entry_for", "symbols", "trades", "gaps")


class YtdTradeSource:
    """The YTD trade files on disk, as MANIFEST rows and ``YtdTrade`` rows."""

    def __init__(self, root: Optional[Path] = None) -> None:
        """Read from ``root``, or from ``get_ytd_root()`` when it is None."""
        self._root = Path(root) if root is not None else get_ytd_root()

    def root(self) -> Path:
        """The directory ``entries``, ``trades`` and ``gaps`` read."""
        return self._root

    def entries(self) -> list[YtdFileEntry]:
        """Every MANIFEST row under ``root``, by exchange_id, symbol then
        year."""
        return sorted(
            read_manifest(self._root),
            key=lambda entry: (entry.exchange_id, entry.symbol, entry.year),
        )

    def entry_for(
        self, exchange_id: str, symbol: str, year: int
    ) -> Optional[YtdFileEntry]:
        """The entry for ``exchange_id``, ``symbol`` and ``year``, or None."""
        for entry in self.entries():
            if (entry.exchange_id, entry.symbol, entry.year) == (
                exchange_id,
                symbol,
                int(year),
            ):
                return entry
        return None

    def symbols(self, exchange_id: Optional[str] = None) -> list[str]:
        """The symbols the entries name, narrowed to ``exchange_id`` when
        given."""
        return sorted(
            {
                entry.symbol
                for entry in self.entries()
                if exchange_id is None or entry.exchange_id == exchange_id
            }
        )

    def trades(self, entry: YtdFileEntry) -> list[YtdTrade]:
        """``entry``'s trade rows, oldest first; an absent file answers an empty
        list."""
        trade_file = read_trade_file(self._root / entry.file)
        return list(trade_file.trades) if trade_file is not None else []

    def gaps(self) -> list[TradeGap]:
        """Every period under ``root`` that no trade file covers."""
        return read_gaps(self._root)

    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"YtdTradeSource answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )


__all__ = [
    "READ_NAMES",
    "SendRefused",
    "YtdTradeSource",
]
