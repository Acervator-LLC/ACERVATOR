"""The single home-relative root for the chart images ATA-SPM posts carry.

``ATA_POST_ROOT`` is a sibling of ``~/.acervator`` and of ``~/.acervator_logs``,
``ATA_POST_ROOT_ENV`` redirects it, and ``get_ata_post_root`` creates it.
``post_image_path`` names one PNG per asset, timeframe and call time under the
root, and ``venue_post_path`` names one file under the ``venue_post_root`` of
one push target. ``prune_post_images`` holds the newest
``POST_IMAGES_KEPT_PER_MARKET`` files of each market and suffix in one store.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.ata_post_paths")

ATA_POST_ROOT_ENV = "ACERVATOR_ATA_POST_ROOT"

ATA_POST_ROOT: Path = Path.home() / ".acervator_ata_posts"

POST_IMAGE_NAME_FORMAT = "{symbol}_{timeframe}_{stamp}.png"

POST_STEM_FORMAT = "{symbol}_{timeframe}_{stamp}"

POST_IMAGE_SUFFIX = ".png"

#: The plain-text message beside a venue folder's image.
POST_TEXT_SUFFIX = ".txt"

#: The Internet Shortcut holding a venue's compose address, opened on one click.
POST_INTENT_SUFFIX = ".url"

#: The suffixes a venue folder holds, which its ``prune_post_images`` reads.
POST_FILE_SUFFIXES = (POST_IMAGE_SUFFIX, POST_TEXT_SUFFIX, POST_INTENT_SUFFIX)

#: ``POST_IMAGE_NAME_FORMAT`` writes symbol, timeframe and stamp, and
#: ``name_part`` folds every underscore, so the name splits into three.
POST_IMAGE_NAME_FIELDS = 3

#: ``ata_spm_push.format_run`` keys its pulls by symbol and timeframe, last
#: write winning, so one image per market is every image a post can name.
POST_IMAGES_KEPT_PER_MARKET = 1

#: The order ``stamp_order`` gives a name whose stamp is not a whole number.
UNREAD_STAMP = -1

PRUNE_LOG = (
    "ATA post store: removed %d image(s), reclaimed %d byte(s), kept %d, refused %d"
)
PRUNE_REFUSED_LOG = "ATA post image %s stayed, the host holds it: %s"

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9]+")


@dataclass(frozen=True)
class PrunedPostImages:
    """What one ``prune_post_images`` took out of the ATA post root.

    ``refused`` counts the images the host still held open, which stay.
    """

    removed: int = 0
    bytes_reclaimed: int = 0
    kept: int = 0
    refused: int = 0


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


def venue_post_root(venue: object, root: Optional[Path] = None) -> Path:
    """The folder one push target's files land in, under ``get_ata_post_root(root)``, created."""
    held = get_ata_post_root(root) / name_part(venue)
    held.mkdir(parents=True, exist_ok=True)
    return held


def venue_post_roots(venues: object, root: Optional[Path] = None) -> list:
    """One ``venue_post_root`` per name in ``venues``, every folder created."""
    return [venue_post_root(one, root) for one in venues or ()]


def venue_post_path(
    venue: object,
    symbol: object,
    timeframe: object,
    stamp: object,
    suffix: str = POST_IMAGE_SUFFIX,
    root: Optional[Path] = None,
) -> Path:
    """The file for one call under ``venue_post_root(venue, root)``, named as ``post_image_path`` names it."""
    return venue_post_root(venue, root) / (
        POST_STEM_FORMAT.format(
            symbol=name_part(symbol),
            timeframe=name_part(timeframe),
            stamp=name_part(stamp),
        )
        + suffix
    )


def market_of(path: object, suffixes: tuple = (POST_IMAGE_SUFFIX,)) -> Optional[tuple]:
    """The asset and timeframe one post file name carries, or None.

    A file outside ``suffixes`` or not shaped by ``POST_STEM_FORMAT`` reads as
    no market, so ``prune_post_images`` leaves it where it is.
    """
    held = Path(str(path))
    if held.suffix not in suffixes:
        return None
    fields = held.stem.split("_")
    if len(fields) != POST_IMAGE_NAME_FIELDS:
        return None
    return (fields[0], fields[1])


def stamp_order(path: object) -> tuple:
    """The sort key putting one market's newest post image first.

    The stamp is the call's last bar, which rises as bars close, and the name
    settles two images carrying one stamp.
    """
    held = Path(str(path))
    stamp = held.stem.split("_")[-1]
    return (int(stamp) if stamp.isdigit() else UNREAD_STAMP, held.name)


def prune_post_images(
    kept_path: Optional[Path] = None,
    root: Optional[Path] = None,
    suffixes: tuple = (POST_IMAGE_SUFFIX,),
) -> PrunedPostImages:
    """Hold each market's newest post files under the root, remove the older.

    Only ``get_ata_post_root(root)`` is read and only names ``market_of``
    reads under ``suffixes``, every file sharing the stem of ``kept_path``
    stays whatever its ``stamp_order``, and a file the host holds open refuses
    deletion.
    """
    store = get_ata_post_root(root)
    written = Path(str(kept_path)).stem if kept_path else ""
    markets: dict = {}
    for one in store.iterdir():
        if not one.is_file():
            continue
        market = market_of(one, suffixes)
        if market is not None:
            markets.setdefault(market + (one.suffix,), []).append(one)
    found = PrunedPostImages()
    for images in markets.values():
        images.sort(key=stamp_order, reverse=True)
        found = _prune_market(images, written, found)
    logger.info(
        PRUNE_LOG, found.removed, found.bytes_reclaimed, found.kept, found.refused
    )
    return found


def _prune_market(
    images: list,
    written: str,
    found: PrunedPostImages,
) -> PrunedPostImages:
    """Remove one market's files of one suffix past ``POST_IMAGES_KEPT_PER_MARKET``."""
    removed = found.removed
    reclaimed = found.bytes_reclaimed
    kept = found.kept
    refused = found.refused
    for index, one in enumerate(images):
        if index < POST_IMAGES_KEPT_PER_MARKET or one.stem == written:
            kept += 1
            continue
        try:
            size = one.stat().st_size
            one.unlink()
        except OSError as exc:
            refused += 1
            logger.debug(PRUNE_REFUSED_LOG, one.name, exc)
            continue
        removed += 1
        reclaimed += size
    return PrunedPostImages(
        removed=removed, bytes_reclaimed=reclaimed, kept=kept, refused=refused
    )


__all__ = [
    "ATA_POST_ROOT",
    "ATA_POST_ROOT_ENV",
    "POST_FILE_SUFFIXES",
    "POST_IMAGE_NAME_FIELDS",
    "POST_IMAGE_NAME_FORMAT",
    "POST_IMAGE_SUFFIX",
    "POST_IMAGES_KEPT_PER_MARKET",
    "POST_INTENT_SUFFIX",
    "POST_STEM_FORMAT",
    "POST_TEXT_SUFFIX",
    "PrunedPostImages",
    "get_ata_post_root",
    "market_of",
    "name_part",
    "post_image_path",
    "prune_post_images",
    "stamp_order",
    "venue_post_path",
    "venue_post_root",
    "venue_post_roots",
]
