"""The logo one asset draws by, fetched once and kept on disk.

``LogoCache.resolve`` walks a listing's candidate addresses, keeps the bytes of
the first one answering an image under ``LOGO_CACHE_DIR``, and answers a
``LogoAnswer``. Where no candidate answers and a ``page_url`` is given, it reads
that page and tries the icon addresses the page declares itself, which
``declared_icons`` reads off its own link tags; that is the third location a
browser looks in and it is what resolves a site serving neither standard one.
``image_extension`` decides whether a body is an image at all and
what it is kept as, so a page served with no failure code is never kept. An asset
no address answers for is remembered, so the walk runs once per asset and every
call after it reads the kept file or the kept reason.
The addresses themselves come from the asset registries; this module holds no
asset and names no market sector. ``kept_name`` decides the file name, so a
symbol carrying a separator or a parent-directory step stays inside
``cache_dir``.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .safe_url import SafeRequest, safe_urlopen

logger = logging.getLogger("acervator.asset_logos")

LOGO_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "logos"

#: The file name extensions ``LogoCache.kept_path`` looks for, in that order.
LOGO_EXTENSIONS: tuple[str, ...] = ("png", "svg", "jpg", "ico", "gif", "bmp", "webp")

#: The leading bytes each image format begins with, and the extension a body
#: carrying them is kept under. A length alone cannot tell an image from an
#: error page: measured 2026-09-26, one keyless icon address answered 6,186
#: bytes of HTML and no failure code, and a length check kept it as a PNG.
IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"\x00\x00\x01\x00", "ico"),
    (b"BM", "bmp"),
)

#: What a WebP body carries: the container head, then the format mark.
WEBP_HEAD = b"RIFF"
WEBP_MARK = b"WEBP"
WEBP_EXTENSION = "webp"

#: An SVG is text, so it is read by its own tag inside ``SIGNATURE_WINDOW``.
SVG_MARK = b"<svg"
SVG_EXTENSION = "svg"

#: The leading text of a page, never of an image.
HTML_MARKS: tuple[bytes, ...] = (b"<!doctype html", b"<html", b"<!-- ")

#: How far into a body a text mark is looked for.
SIGNATURE_WINDOW = 512

#: A link tag whose ``rel`` names an icon, and the address inside it. A site
#: that serves neither standard icon location still declares its own mark here,
#: which is where a browser reads it from.
ICON_LINK_TAG = re.compile(
    rb"""<link\b[^>]*\brel\s*=\s*["'][^"']*\bicon\b[^"']*["'][^>]*>""", re.IGNORECASE
)
ICON_LINK_HREF = re.compile(rb"""\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

#: How much of a page ``_read_page`` takes while looking for its link tags.
PAGE_WINDOW = 200_000

#: What ``kept_name`` puts in place of a character a file name may not carry. A
#: symbol arrives from outside this repository, so a pair like ``EUR/USD`` and a
#: name holding a parent-directory step must both stay inside ``cache_dir``.
KEPT_NAME_GAP = "-"

#: The least length a kept body may have, so a truncated or empty answer is
#: never kept as an image.
MIN_LOGO_BYTES = 100

LOGO_TIMEOUT_S = 10.0
LOGO_USER_AGENT = "Acervator"

NO_SOURCE_REASON = "no logo address is known for {symbol}"
NO_ANSWER_REASON = "no logo address answered an image for {symbol}"
PAGE_REFUSED_LOG = "asset logo: %s answered no page for %s: %s"
PAGE_DECLARED_LOG = "asset logo: %s declares %d icon address(es) for %s"

LOGO_KEPT_LOG = "asset logo: kept %s for %s, %d bytes"
LOGO_REFUSED_LOG = "asset logo: %s answered no image for %s: %s"
LOGO_SHORT_LOG = "asset logo: %s answered %d bytes for %s, under %d"
LOGO_NOT_IMAGE_LOG = "asset logo: %s answered %d bytes for %s starting %r, not an image"

#: What a logo read raises: a transport or HTTP failure, a refused scheme, and
#: a body the reader cannot take bytes from.
LOGO_READ_ERRORS = (OSError, ValueError, TypeError, AttributeError)


def image_extension(body: bytes) -> str:
    """The extension ``body``'s own leading bytes name, empty when it is not an image."""
    if not isinstance(body, bytes) or len(body) < MIN_LOGO_BYTES:
        return ""
    head = body[:SIGNATURE_WINDOW].lstrip().lower()
    if head.startswith(HTML_MARKS):
        return ""
    for signature, extension in IMAGE_SIGNATURES:
        if body.startswith(signature):
            return extension
    if body[:4] == WEBP_HEAD and WEBP_MARK in body[:16]:
        return WEBP_EXTENSION
    if SVG_MARK in head:
        return SVG_EXTENSION
    return ""


def declared_icons(page_url: str, body: bytes) -> tuple[str, ...]:
    """Every icon address ``body``'s own link tags declare, absolute against ``page_url``."""
    if not isinstance(body, bytes) or not page_url:
        return ()
    found: list[str] = []
    for tag in ICON_LINK_TAG.finditer(body[:PAGE_WINDOW]):
        href = ICON_LINK_HREF.search(tag.group(0))
        if href is None:
            continue
        address = urllib.parse.urljoin(
            page_url, href.group(1).decode("utf-8", "replace").strip()
        )
        if address not in found:
            found.append(address)
    return tuple(found)


def kept_name(symbol: str) -> str:
    """``symbol`` as the file name stem a kept logo takes, every other character ``KEPT_NAME_GAP``."""
    text = str(symbol).strip().upper()
    return "".join(
        one if one.isascii() and one.isalnum() else KEPT_NAME_GAP for one in text
    )


@dataclass(frozen=True)
class LogoAnswer:
    """One asset's kept logo ``path``, the ``source_url`` it came from, or a ``reason``."""

    symbol: str
    path: Optional[Path] = None
    source_url: str = ""
    reason: str = ""

    @property
    def has_logo(self) -> bool:
        """True when ``path`` names the file this asset's logo was kept in."""
        return self.path is not None


class LogoCache:
    """Keeps one logo file per asset under ``cache_dir`` and remembers the refusals.

    ``cache_dir`` defaults to ``LOGO_CACHE_DIR`` and is created on the first
    write, never at construction, so building a cache writes nothing.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Hold ``cache_dir`` and the refusals; no directory is made and no file is read."""
        self._cache_dir: Path = Path(cache_dir) if cache_dir else LOGO_CACHE_DIR
        self._refusals: dict[str, str] = {}

    @property
    def cache_dir(self) -> Path:
        """The directory ``resolve`` keeps every logo file in."""
        return self._cache_dir

    def kept_path(self, symbol: str) -> Optional[Path]:
        """The kept logo file for ``symbol``, None while no ``LOGO_EXTENSIONS`` file exists."""
        stem = kept_name(symbol)
        if not stem:
            return None
        for extension in LOGO_EXTENSIONS:
            path = self._cache_dir / f"{stem}.{extension}"
            if path.exists():
                return path
        return None

    def refusal(self, symbol: str) -> str:
        """The remembered reason ``symbol`` has no logo, empty while none is remembered."""
        return self._refusals.get(str(symbol).strip().upper(), "")

    def resolve(
        self,
        symbol: str,
        candidates: Iterable[str],
        timeout_s: float = LOGO_TIMEOUT_S,
        *,
        page_url: str = "",
        no_source_reason: str = "",
    ) -> LogoAnswer:
        """``symbol``'s kept logo, fetching ``candidates`` then ``page_url``'s own icons at most once ever."""
        name = str(symbol).strip().upper()
        if not name:
            return LogoAnswer(symbol=name, reason=NO_SOURCE_REASON.format(symbol=name))

        kept = self.kept_path(name)
        if kept is not None:
            return LogoAnswer(symbol=name, path=kept)

        remembered = self._refusals.get(name)
        if remembered:
            return LogoAnswer(symbol=name, reason=remembered)

        addresses = [str(one) for one in candidates if str(one).strip()]
        page = str(page_url).strip()
        if not addresses and not page:
            reason = no_source_reason or NO_SOURCE_REASON.format(symbol=name)
            self._refusals[name] = reason
            return LogoAnswer(symbol=name, reason=reason)

        answer = self._walk(name, addresses, timeout_s)
        if answer is not None:
            return answer

        if page:
            body = self._read_page(page, name, timeout_s)
            if body is not None:
                spare = [
                    one for one in declared_icons(page, body) if one not in addresses
                ]
                logger.debug(PAGE_DECLARED_LOG, page, len(spare), name)
                answer = self._walk(name, spare, timeout_s)
                if answer is not None:
                    return answer

        reason = NO_ANSWER_REASON.format(symbol=name)
        self._refusals[name] = reason
        return LogoAnswer(symbol=name, reason=reason)

    def _walk(
        self, symbol: str, addresses: Iterable[str], timeout_s: float
    ) -> Optional[LogoAnswer]:
        """The answer for the first of ``addresses`` holding an image, None when none does."""
        for address in addresses:
            read = self._read(address, symbol, timeout_s)
            if read is None:
                continue
            body, extension = read
            path = self._keep(symbol, body, extension)
            logger.info(LOGO_KEPT_LOG, path.name, symbol, len(body))
            return LogoAnswer(symbol=symbol, path=path, source_url=address)
        return None

    def _read_page(
        self, address: str, symbol: str, timeout_s: float
    ) -> Optional[bytes]:
        """``address``'s first ``PAGE_WINDOW`` bytes, None when it answers nothing."""
        try:
            request = SafeRequest(address)
            request.add_header("User-Agent", LOGO_USER_AGENT)
            with safe_urlopen(request, timeout=timeout_s) as response:
                body = response.read(PAGE_WINDOW)
        except LOGO_READ_ERRORS as exc:
            closer = getattr(exc, "close", None)
            if callable(closer):
                closer()
            logger.debug(PAGE_REFUSED_LOG, address, symbol, exc)
            return None
        return body if isinstance(body, bytes) else None

    def _read(
        self, address: str, symbol: str, timeout_s: float
    ) -> Optional[tuple[bytes, str]]:
        """``address``'s body with the extension ``image_extension`` reads off it, else None."""
        try:
            request = SafeRequest(address)
            request.add_header("User-Agent", LOGO_USER_AGENT)
            with safe_urlopen(request, timeout=timeout_s) as response:
                body = response.read()
        except LOGO_READ_ERRORS as exc:
            closer = getattr(exc, "close", None)
            if callable(closer):
                closer()
            logger.debug(LOGO_REFUSED_LOG, address, symbol, exc)
            return None
        if not isinstance(body, bytes) or len(body) < MIN_LOGO_BYTES:
            logger.debug(
                LOGO_SHORT_LOG, address, len(body or b""), symbol, MIN_LOGO_BYTES
            )
            return None
        extension = image_extension(body)
        if not extension:
            logger.debug(LOGO_NOT_IMAGE_LOG, address, len(body), symbol, body[:16])
            return None
        return body, extension

    def _keep(self, symbol: str, body: bytes, extension: str) -> Path:
        """Write ``body`` to ``kept_name``'s ``extension`` file, making ``cache_dir`` first."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{kept_name(symbol)}.{extension}"
        path.write_bytes(body)
        return path
