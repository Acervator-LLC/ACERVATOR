"""The Simulator's YTD trade path: the trade files on disk, read only.

``YtdTradeSource`` answers ``root``, ``root_state``, ``entries``, ``entry_for``,
``symbols``, ``trades``, ``trade_path`` and ``gaps`` from the files under
``ytd_root_path``, the directory ``get_ytd_root`` resolves. It holds no venue
and defines no write, and ``__getattr__`` raises ``SendRefused`` for every other
name, so an order, a cancellation or a venue write cannot be expressed through
it. ``root_state`` reads the directory itself, so a missing directory is read
before the store's readers create it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..core.log_paths import get_log_root
from ..exchange.ytd_trade_store import (
    MANIFEST_NAME,
    YTD_TRADES_ROOT_ENV,
    TradeGap,
    YtdFileEntry,
    YtdTrade,
    read_gaps,
    read_manifest,
    read_trade_file,
)
from .tablet_source import SendRefused

#: Every name ``YtdTradeSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = (
    "root",
    "root_state",
    "entries",
    "entry_for",
    "symbols",
    "trades",
    "trade_path",
    "gaps",
)

#: The bucket ``get_exchange_history_dir`` names under ``get_log_root``.
EXCHANGE_HISTORY_BUCKET = "exchange_history"

#: What ``root_state`` answers: no directory, a directory holding nothing, a
#: directory holding files but no ``MANIFEST_NAME``, or a manifest to read.
ROOT_MISSING = "missing"
ROOT_EMPTY = "empty"
ROOT_NO_MANIFEST = "no_manifest"
ROOT_READY = "ready"


def ytd_root_path() -> Path:
    """The directory ``get_ytd_root`` resolves, without creating it: the
    ``YTD_TRADES_ROOT_ENV`` override when set, else ``EXCHANGE_HISTORY_BUCKET``
    under ``get_log_root``."""
    override = os.environ.get(YTD_TRADES_ROOT_ENV)
    if override:
        return Path(override)
    return get_log_root() / EXCHANGE_HISTORY_BUCKET


class YtdTradeSource:
    """The YTD trade files on disk, as MANIFEST rows and ``YtdTrade`` rows."""

    def __init__(self, root: Optional[Path] = None) -> None:
        """Read from ``root``, or from ``ytd_root_path()`` when it is None;
        neither is created here."""
        self._root = Path(root) if root is not None else ytd_root_path()

    def root(self) -> Path:
        """The directory ``entries``, ``trades`` and ``gaps`` read."""
        return self._root

    def root_state(self) -> str:
        """``ROOT_MISSING`` with no directory at ``root``, ``ROOT_EMPTY`` when
        it holds nothing, ``ROOT_NO_MANIFEST`` when it holds files but no
        ``MANIFEST_NAME``, else ``ROOT_READY``; nothing is created."""
        if not self._root.is_dir():
            return ROOT_MISSING
        if not any(self._root.iterdir()):
            return ROOT_EMPTY
        if not (self._root / MANIFEST_NAME).is_file():
            return ROOT_NO_MANIFEST
        return ROOT_READY

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

    def trade_path(self, entry: YtdFileEntry) -> Optional[Path]:
        """The file ``entry`` names under ``root`` when it lies on disk, else
        None."""
        path = self._root / entry.file
        return path if path.is_file() else None

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
    "EXCHANGE_HISTORY_BUCKET",
    "READ_NAMES",
    "ROOT_EMPTY",
    "ROOT_MISSING",
    "ROOT_NO_MANIFEST",
    "ROOT_READY",
    "SendRefused",
    "YtdTradeSource",
    "ytd_root_path",
]
