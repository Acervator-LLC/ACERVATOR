"""The single home-relative root for RA-StoneTablets.

``RA_STONE_TABLETS_DIR`` is where the Portfolio Battery's historical prices are
kept, and ``get_ra_root`` creates it on first use. It is a sibling of
``~/.acervator/``, never a subdirectory of it: ``STONE_TABLETS_DIR`` in
``storage.py`` is the live fleet's tree and nothing here writes into it.
``RA_GAPS_PATH`` names the file recording every period a source returned no
data for.
"""

from __future__ import annotations

from pathlib import Path

_RA_ROOT: Path = Path.home() / ".acervator_ra_tablets"

RA_STONE_TABLETS_DIR: Path = _RA_ROOT
RA_GAPS_PATH: Path = _RA_ROOT / "GAPS.json"
RA_MANIFEST_PATH: Path = _RA_ROOT / "MANIFEST.json"


def get_ra_root() -> Path:
    """Return ``RA_STONE_TABLETS_DIR``, creating it and its parents."""
    _RA_ROOT.mkdir(parents=True, exist_ok=True)
    return _RA_ROOT


__all__ = [
    "RA_GAPS_PATH",
    "RA_MANIFEST_PATH",
    "RA_STONE_TABLETS_DIR",
    "get_ra_root",
]
