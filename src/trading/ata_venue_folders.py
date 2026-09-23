"""ata_venue_folders.py -- one folder per push target, filled for posting by hand.

``write_venue_posts`` runs once per call phase three charts, and for every row
of ``ata_spm_push.PUSH_TARGETS`` it draws that target's own message at the foot
of the chart, writes the same message as plain text beside it, and for each
``INTENT_FORMATS`` row writes the compose address as an Internet Shortcut.
Every file lands under ``ata_post_paths.venue_post_root`` and no venue is
contacted.
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..core.signal_contract import emit as _pin_emit
from ..gui.native_chart import ChartImage, render_chart_png
from . import ata_post_paths, ata_spm, ata_spm_push

logger = logging.getLogger("acervator.ata_venue_folders")

#: The pin ``write_venue_post`` writes once per venue image, through ``_pin_emit``:
#: the written size against the row's size.
IMAGE_SIZE_PIN = "inspector.ata.image_size"

#: X's Web Intent opens the compose window with ``text`` filled in.
X_INTENT_FORMAT = "https://x.com/intent/post?text={text}"

#: WhatsApp's Click-to-Chat address opens the app with ``text`` typed and the
#: chat left for the operator to pick.
WHATSAPP_INTENT_FORMAT = "https://wa.me/?text={text}"

#: The compose address one target documents; a target absent here writes none.
INTENT_FORMATS = {
    ata_spm_push.TARGET_X: X_INTENT_FORMAT,
    ata_spm_push.TARGET_WHATSAPP: WHATSAPP_INTENT_FORMAT,
}

#: The Internet Shortcut form the operating system opens in the browser.
INTENT_SHORTCUT_FORMAT = "[InternetShortcut]\nURL={url}\n"

TEXT_ENCODING = "utf-8"
TEXT_NEWLINE = "\n"

#: Stands between the title line and the body where the target holds a title.
TITLE_SEPARATOR = "\n\n"

NO_INTENT = ""

VENUE_WRITTEN_LOG = "ATA venue folder %s: %s %s written at %dx%d, %d %s of %d"
VENUE_FAILED_LOG = "ATA venue folder %s: %s %s not written: %s"
VENUE_IMAGE_REFUSED_LOG = "ATA venue folder %s: %s %s image refused: %s"


@dataclass(frozen=True)
class VenuePost:
    """What one push target's folder holds for one call, and the limit that shaped it."""

    target: str
    image: ChartImage
    text_path: str
    intent_path: str = NO_INTENT
    title: str = ""
    body: str = ""
    measured: int = 0
    body_limit: int = ata_spm_push.NO_LIMIT_PUBLISHED
    count_unit: str = ata_spm_push.COUNT_CHARACTERS
    dropped: int = ata_spm_push.NO_DROPPED


def post_text(post: Any) -> str:
    """The text one folder carries: ``post.title`` over ``post.body`` where the target holds a title."""
    title = str(getattr(post, "title", "") or "")
    body = str(getattr(post, "body", "") or "")
    return TITLE_SEPARATOR.join((title, body)) if title else body


def intent_url(post: Any) -> str:
    """The compose address ``INTENT_FORMATS`` names for ``post.target``, carrying ``post.body``."""
    written = INTENT_FORMATS.get(str(getattr(post, "target", "")))
    if written is None:
        return NO_INTENT
    return written.format(
        text=urllib.parse.quote(str(getattr(post, "body", "")), safe="")
    )


def write_text(path: Path, text: str) -> str:
    """Write ``text`` at ``path`` in ``TEXT_ENCODING`` with ``TEXT_NEWLINE`` endings."""
    path.write_text(text, encoding=TEXT_ENCODING, newline=TEXT_NEWLINE)
    return str(path)


def write_venue_post(
    vote: Any,
    pull: Any,
    candles: Any,
    target: Any,
    max_supporting_indicators: Any = ata_spm.NO_INDICATOR_CAP,
    root: Optional[Path] = None,
) -> VenuePost:
    """Fill one target's folder for one call from ``ata_spm_push.format_post``.

    The image is ``target.image_width_px`` by ``target.image_height_px`` with
    ``post.body`` at its foot, the text file carries ``post_text``, ``candles``
    are ``native_chart.Candle`` rows, and ``prune_post_images`` runs on the
    folder once the files are written.
    """
    post = ata_spm_push.format_post(vote, pull, target, max_supporting_indicators)
    stamp = int(candles[-1].time) if candles else ata_spm.NO_TIMESTAMP
    image_path = ata_post_paths.venue_post_path(
        target.name,
        vote.symbol,
        vote.timeframe,
        stamp,
        ata_post_paths.POST_IMAGE_SUFFIX,
        root,
    )
    width_px = int(target.image_width_px)
    height_px = int(target.image_height_px)
    image = render_chart_png(
        candles,
        vote.symbol,
        ata_spm.timeframe_label(vote.timeframe),
        image_path,
        voters=[one.indicator for one in ata_spm.confirming_signals(vote)],
        max_overlays=int(max_supporting_indicators or ata_spm.NO_INDICATOR_CAP),
        direction=vote.direction_text,
        readings=[(one.indicator, one.message) for one in pull.messages or ()],
        caption=post.body,
        width_px=width_px,
        height_px=height_px,
    )
    if not image.path:
        logger.warning(
            VENUE_IMAGE_REFUSED_LOG,
            target.name,
            vote.symbol,
            vote.timeframe,
            image.note,
        )
    _pin_emit(
        IMAGE_SIZE_PIN,
        actual=[image.width_px, image.height_px],
        expected=[width_px, height_px],
        context={
            "venue": target.name,
            "symbol": vote.symbol,
            "timeframe": vote.timeframe,
            "width": width_px,
            "height": height_px,
            "overlays": list(image.drawn),
            "path": image.path,
            "note": image.note,
        },
    )
    text_path = write_text(
        image_path.with_suffix(ata_post_paths.POST_TEXT_SUFFIX), post_text(post)
    )
    address = intent_url(post)
    intent_path = NO_INTENT
    if address:
        intent_path = write_text(
            image_path.with_suffix(ata_post_paths.POST_INTENT_SUFFIX),
            INTENT_SHORTCUT_FORMAT.format(url=address),
        )
    ata_post_paths.prune_post_images(
        image_path, root=image_path.parent, suffixes=ata_post_paths.POST_FILE_SUFFIXES
    )
    logger.info(
        VENUE_WRITTEN_LOG,
        target.name,
        vote.symbol,
        vote.timeframe,
        image.width_px,
        image.height_px,
        post.measured,
        post.count_unit,
        post.body_limit,
    )
    return VenuePost(
        target=target.name,
        image=image,
        text_path=text_path,
        intent_path=intent_path,
        title=post.title,
        body=post.body,
        measured=post.measured,
        body_limit=post.body_limit,
        count_unit=post.count_unit,
        dropped=post.dropped,
    )


def write_venue_posts(
    vote: Any,
    pull: Any,
    candles: Any,
    max_supporting_indicators: Any = ata_spm.NO_INDICATOR_CAP,
    targets: Any = ata_spm_push.PUSH_TARGETS,
    root: Optional[Path] = None,
) -> dict:
    """One ``write_venue_post`` per row of ``targets``, keyed by target name.

    A folder the host refuses to write is logged under ``VENUE_FAILED_LOG``
    and the other folders are still filled.
    """
    held = ata_spm.chart_candles(candles)
    written: dict = {}
    for target in targets:
        try:
            written[target.name] = write_venue_post(
                vote, pull, held, target, max_supporting_indicators, root
            )
        except OSError as exc:
            logger.warning(
                VENUE_FAILED_LOG, target.name, vote.symbol, vote.timeframe, exc
            )
    return written


__all__ = [
    "INTENT_FORMATS",
    "INTENT_SHORTCUT_FORMAT",
    "TITLE_SEPARATOR",
    "VenuePost",
    "WHATSAPP_INTENT_FORMAT",
    "X_INTENT_FORMAT",
    "intent_url",
    "post_text",
    "write_text",
    "write_venue_post",
    "write_venue_posts",
]
