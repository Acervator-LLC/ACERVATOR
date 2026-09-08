"""The single home-relative root for the chart images ATA-SPM posts carry.

``ATA_POST_ROOT`` is a sibling of ``~/.acervator`` and of ``~/.acervator_logs``,
never a subdirectory of either, so a rendered image never lands in a live tree.
``post_image_path`` names one PNG per asset, timeframe and call time, and
``get_ata_post_root`` creates the directory on first use. ``ATA_POST_ROOT_ENV``
redirects the root, which is how the suite keeps its writes out of the
operator's home.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

ATA_POST_ROOT_ENV = "ACERVATOR_ATA_POST_ROOT"

ATA_POST_ROOT: Path = Path.home() / ".acervator_ata_posts"

POST_IMAGE_NAME_FORMAT = "{symbol}_{timeframe}_{stamp}.png"

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9]+")


def get_ata_post_root(root: Optional[Path] = None) -> Path:
    """Return ``root``, the ``ATA_POST_ROOT_ENV`` path or ``ATA_POST_ROOT``, created."""
    if root is not None:
        resolved = Path(root)
    else:
        override = os.environ.get(ATA_POST_ROOT_ENV)
        resolved = Path(override) if override else ATA_POST_ROOT
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def name_part(text: object) -> str:
    """Return ``text`` with every run of non-alphanumerics folded to one dash."""
    return _UNSAFE_NAME_CHARS.sub("-", str(text)).strip("-")


def post_image_path(
    symbol: object,
    timeframe: object,
    stamp: object,
    root: Optional[Path] = None,
) -> Path:
    """Return the PNG path for one call, under ``get_ata_post_root(root)``.

    ``BTC/USD`` becomes ``BTC-USD`` so the name is a legal file on every host,
    and ``stamp`` separates two calls on the same asset and timeframe.
    """
    return get_ata_post_root(root) / POST_IMAGE_NAME_FORMAT.format(
        symbol=name_part(symbol),
        timeframe=name_part(timeframe),
        stamp=name_part(stamp),
    )


__all__ = [
    "ATA_POST_ROOT",
    "ATA_POST_ROOT_ENV",
    "POST_IMAGE_NAME_FORMAT",
    "get_ata_post_root",
    "name_part",
    "post_image_path",
]
