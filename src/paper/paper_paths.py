"""The single home-relative root for the Paper Trader's own log.

``PAPER_ROOT`` is a sibling of ``~/.acervator`` and of ``~/.acervator_logs``,
never a subdirectory of either, so no paper figure can land in a live tree.
``PAPER_TRADER_LOG_PATH`` names the file every paper action is appended to,
``PAPER_FLEET_NAME`` the paper fleet file ``PaperFleetSource`` writes, and
``get_paper_root`` creates the directory on first use. ``PAPER_ROOT_ENV``
redirects the root, which is how the suite keeps its writes out of the
operator's home.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PAPER_ROOT_ENV = "ACERVATOR_PAPER_ROOT"

PAPER_ROOT: Path = Path.home() / ".acervator_paper"

PAPER_TRADER_LOG_NAME = "paper_trader.log"

#: The paper fleet file under ``PAPER_ROOT``, in ``bot_state.json``'s shape.
PAPER_FLEET_NAME = "paper_fleet.json"


def get_paper_root(root: Optional[Path] = None) -> Path:
    """Return ``root``, the ``PAPER_ROOT_ENV`` path or ``PAPER_ROOT``, created."""
    if root is not None:
        resolved = Path(root)
    else:
        override = os.environ.get(PAPER_ROOT_ENV)
        resolved = Path(override) if override else PAPER_ROOT
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def paper_trader_log_path(root: Optional[Path] = None) -> Path:
    """Return ``PAPER_TRADER_LOG_NAME`` under ``get_paper_root(root)``."""
    return get_paper_root(root) / PAPER_TRADER_LOG_NAME


def paper_fleet_path(root: Optional[Path] = None) -> Path:
    """Return ``PAPER_FLEET_NAME`` under ``get_paper_root(root)``."""
    return get_paper_root(root) / PAPER_FLEET_NAME


__all__ = [
    "PAPER_FLEET_NAME",
    "PAPER_ROOT",
    "PAPER_ROOT_ENV",
    "PAPER_TRADER_LOG_NAME",
    "get_paper_root",
    "paper_fleet_path",
    "paper_trader_log_path",
]
