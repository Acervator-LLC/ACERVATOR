"""crypto_news_ticker.py — cycling crypto + fintech news widget.

Introduced 2026-07-28 as v3.23.54 per operator directive. Sits in
the header strip of the main window (between the Privacy Mode
toggle and the + New Bot button), cycles one headline every 15 s,
hourly refresh from 10 free public RSS feeds, click-to-open in
default browser, hover-to-pause.

Feed bytes are untrusted: they arrive from ten third-party hosts over
the open internet, on a worker thread of a trading GUI. Parsing is
therefore done by ``defusedxml``, the maintained library the Python
documentation points at for exactly this, rather than by
``xml.etree.ElementTree`` or by a hand-hardened expat parser of our
own. ``defusedxml`` costs one dependency; it is written by people who
work on these attacks, and it replaces code we would otherwise have to
be right about ourselves.

Measured, CPython 3.14.4 / expat 2.7.5, driving the real ``parse_rss``:

  * A 20,922-byte feed declaring one 20,000-character entity and
    referencing it 150 times expanded to 3,000,027 characters under
    ``xml.etree.ElementTree`` and RETURNED A HEADLINE. expat's own
    amplification guard does not activate that low. Under
    ``defusedxml`` the same bytes raise ``EntitiesForbidden`` and
    ``parse_rss`` returns [].
  * The textbook billion-laughs document is 701 bytes. Under
    ``xml.etree.ElementTree`` it cost 59,097,148 bytes of peak
    allocation and 0.51 s before expat refused it. Under
    ``defusedxml`` it costs 15,551 bytes and 0.0001 s, because the
    declaration is refused instead of expanded.

External entity resolution is NOT a regression being fixed here: the
stdlib parser installs no external-entity handler, so a ``file://``
entity was already unresolved and reported as an undefined entity.
Measured both ways, the local file was never read. ``defusedxml``
turns that inherited default into an explicit refusal.

Fetches go through ``src.core.safe_url``, so a feed URL naming a
scheme outside the http/https allowlist is refused rather than opened,
and the response body is read under a fixed cap. Fetches run in a
background QThread so the GUI never blocks on network I/O.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from ..core.safe_url import SafeRequest, safe_urlopen

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout

    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False

logger = logging.getLogger("acervator.crypto_news_ticker")


# ------------------------------------------------------------------
# Feed sources — operator-selected 10 free public RSS feeds.
# ------------------------------------------------------------------


@dataclass(frozen=True)
class NewsSource:
    slug: str
    name: str
    url: str


NEWS_SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        "coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"
    ),
    NewsSource("cointelegraph", "CoinTelegraph", "https://cointelegraph.com/rss"),
    NewsSource("decrypt", "Decrypt", "https://decrypt.co/feed"),
    NewsSource(
        "bitcoinmagazine", "Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"
    ),
    NewsSource("thedefiant", "The Defiant", "https://thedefiant.io/api/feed"),
    NewsSource("bankless", "Bankless", "https://newsletter.banklesshq.com/feed"),
    NewsSource("cryptoslate", "CryptoSlate", "https://cryptoslate.com/feed/"),
    NewsSource("cryptobriefing", "Crypto Briefing", "https://cryptobriefing.com/feed/"),
    NewsSource("cryptonews", "CryptoNews", "https://cryptonews.com/news/feed/"),
    NewsSource(
        "bloomberg", "Bloomberg Crypto", "https://feeds.bloomberg.com/crypto/news.rss"
    ),
)


@dataclass
class NewsHeadline:
    title: str
    url: str
    source: NewsSource
    published_ts: float = 0.0  # unix seconds; 0 when unknown

    def display_text(self) -> str:
        """Composed 'Source · Title' string, trimmed for the strip."""
        return f"{self.source.name} · {self.title}"


# ------------------------------------------------------------------
# RSS parsing — defusedxml, tolerant of RSS 2.0 and Atom.
#
# ``defusedxml.ElementTree.fromstring`` builds the same element objects
# ``xml.etree.ElementTree.fromstring`` builds, from the same expat
# engine, with two handlers installed that REFUSE instead of expand:
# an entity declaration raises ``EntitiesForbidden`` and an external
# reference raises ``ExternalReferenceForbidden``. Both derive from
# ``DefusedXmlException``. Everything downstream of the parse -- the
# ``{uri}local`` tag spelling, ``.text`` stopping at the first child,
# ``iter()`` in document order -- is unchanged, because it is the same
# element type this module has always walked.
#
# A DTD with no entity declarations is still accepted. The library's
# ``forbid_dtd`` default is left alone deliberately: the danger is the
# declaration, which is refused, and a feed carrying a bare doctype is
# a real shape that must keep working.
# ------------------------------------------------------------------


def parse_rss(
    xml_bytes: bytes, source: NewsSource, limit: int = 10
) -> list[NewsHeadline]:
    """Return up to ``limit`` NewsHeadlines parsed from ``xml_bytes``.

    Supports the two common feed shapes we care about:
      - RSS 2.0: <rss><channel><item><title/><link/><pubDate/>
      - Atom:    <feed xmlns='...atom'><entry><title/><link href=/>
    Malformed feeds return [] rather than raise. So do feeds that
    declare an XML entity or reference an external one, but those are
    logged at WARNING rather than DEBUG: a feed host that starts
    shipping entity declarations is worth seeing, where a dropped
    fetch is routine.
    """
    if not xml_bytes:
        return []
    try:
        root = fromstring(xml_bytes)
    except DefusedXmlException as _refused:
        logger.warning(
            "crypto_news_ticker: %s feed refused, no headline taken " "from it: %s",
            source.name,
            _refused,
        )
        return []
    except ParseError as _malformed:
        logger.debug(
            "crypto_news_ticker: %s feed did not parse: %s", source.name, _malformed
        )
        return []
    out: list[NewsHeadline] = []
    # RSS 2.0 path
    for item in root.iter():
        _tag = _localname(item.tag)
        if _tag not in ("item", "entry"):
            continue
        title = _child_text(item, ("title",))
        link = _child_text(item, ("link",))
        # Atom links are attribute-based; RSS puts URL in text.
        if not link:
            for child in item:
                if _localname(child.tag) == "link":
                    _href = child.get("href")
                    if _href:
                        link = _href
                        break
        pub_ts = _parse_ts(_child_text(item, ("pubDate", "published", "updated")))
        if title and link:
            out.append(
                NewsHeadline(
                    title=title.strip()[:220],
                    url=link.strip(),
                    source=source,
                    published_ts=pub_ts,
                )
            )
        if len(out) >= limit:
            break
    return out


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _child_text(parent, names: tuple) -> str:
    for child in parent:
        if _localname(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _parse_ts(raw: str) -> float:
    """Best-effort RFC-2822 or ISO-8601 → unix seconds. Returns 0
    on failure — display uses insertion order rather than pubDate
    when timestamps are unknown."""
    if not raw:
        return 0.0
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.timestamp()
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime

        # Handle common ISO-8601 shapes (with/without Z, with fractional s).
        _r = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(_r).timestamp()
    except (TypeError, ValueError):
        pass
    return 0.0


# ------------------------------------------------------------------
# Fetch — synchronous per source, parallelised via a thread pool.
# ------------------------------------------------------------------

DEFAULT_TIMEOUT_S = 8.0
FETCH_USER_AGENT = "Mozilla/5.0 (compatible; AcervatorNewsTicker/1.0; +local)"

# Refusing entity declarations bounds what a feed can make the parser
# ALLOCATE, but not what it can make the socket READ. A plain oversized
# response still lands in memory before any parser sees it, ten of them
# at once on a GUI worker thread. 4 MiB is far above any RSS feed --
# the largest source here is a full-text feed, which runs in the low
# hundreds of KB -- and 4 MiB x 10 sources bounds the worst case at
# 40 MiB instead of at whatever ten third-party hosts choose to send.
MAX_FEED_BYTES = 4 * 1024 * 1024


def fetch_one(
    source: NewsSource, timeout: float = DEFAULT_TIMEOUT_S
) -> list[NewsHeadline]:
    """Blocking single-feed fetch + parse. Returns [] on any error."""
    try:
        # The scheme allowlist is PERFORMED here, not asserted in a
        # comment. SafeRequest refuses a scheme outside http/https at
        # CONSTRUCTION, and safe_urlopen checks again at open time over
        # an opener carrying no file, ftp or data handler -- so a
        # non-http(s) source has no transport even if the policy check
        # were bypassed. See src/core/safe_url.py.
        req = SafeRequest(source.url)
        req.add_header("User-Agent", FETCH_USER_AGENT)
        req.add_header(
            "Accept",
            "application/rss+xml, application/atom+xml, "
            "application/xml, text/xml, */*",
        )
        with safe_urlopen(req, timeout=timeout) as resp:
            # One byte over the cap is read on purpose: it is what
            # distinguishes "exactly at the limit" from "truncated".
            body = resp.read(MAX_FEED_BYTES + 1)
        if len(body) > MAX_FEED_BYTES:
            logger.warning(
                "crypto_news_ticker: %s response exceeded %d bytes; "
                "dropped unparsed",
                source.name,
                MAX_FEED_BYTES,
            )
            return []
        return parse_rss(body, source)
    except ValueError as _refused:
        # The allowlist rejected this source before any socket opened.
        # Every NEWS_SOURCES entry is an https literal today, so this
        # can only fire once the source list carries a scheme it must
        # not have -- the one day it has to be loud, not debug.
        logger.warning(
            "crypto_news_ticker: %s refused before fetch: %s", source.name, _refused
        )
        return []
    except Exception as _exc:  # noqa: BLE001 - per-feed best-effort
        logger.debug("crypto_news_ticker: %s fetch failed: %s", source.name, _exc)
        return []


def fetch_all(
    sources: tuple[NewsSource, ...] = NEWS_SOURCES, per_source_limit: int = 5
) -> list[NewsHeadline]:
    """Fetch every source in parallel, merge, sort by pubDate
    descending (unknown timestamps sink to the end)."""
    out: list[NewsHeadline] = []
    with ThreadPoolExecutor(max_workers=min(len(sources), 10)) as pool:
        futures = {pool.submit(fetch_one, s): s for s in sources}
        for f in as_completed(futures, timeout=DEFAULT_TIMEOUT_S * 2):
            try:
                headlines = f.result()
                out.extend(headlines[:per_source_limit])
            except Exception as _exc:  # noqa: BLE001 - per-feed best-effort
                logger.debug("crypto_news_ticker: aggregate raised %s", _exc)
    out.sort(key=lambda h: h.published_ts, reverse=True)
    return out


# ------------------------------------------------------------------
# Widget — cycling QLabel ticker.
# ------------------------------------------------------------------

if _HAS_QT:

    CYCLE_INTERVAL_MS = 15_000
    REFRESH_INTERVAL_MS = 60 * 60 * 1000  # 1 hour

    class _FetchWorker(QObject):
        """Runs fetch_all() in a worker thread; emits results back."""

        headlinesReady = Signal(list)
        failed = Signal(str)

        def run(self):
            try:
                headlines = fetch_all()
                self.headlinesReady.emit(headlines)
            except Exception as _exc:  # noqa: BLE001 - thread guard
                self.failed.emit(f"{type(_exc).__name__}: {_exc}")

    class CryptoNewsTicker(QWidget):
        """Header-strip cycling news ticker. Public API:

        - ``start()``: kick off first fetch + start cycling
        - ``stop()``: halt both timers + any in-flight worker
        - ``force_refresh()``: fetch NOW (bypass hourly gate)
        - ``current_headlines()``: read the cached queue

        Emits nothing; user interaction (click) routes through
        webbrowser.open directly.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Crypto News Ticker")
            self._headlines: list[NewsHeadline] = []
            self._index: int = 0
            self._paused: bool = False
            self._last_refresh_ts: float = 0.0
            self._worker_thread: Optional[QThread] = None
            self._worker: Optional[_FetchWorker] = None

            hb = QHBoxLayout(self)
            hb.setContentsMargins(6, 2, 6, 2)
            hb.setSpacing(6)

            self._label = QLabel("Fetching crypto news…")
            self._label.setToolTip(
                "Cycling crypto + fintech headlines from 10 free RSS "
                "feeds. Click to open story in default browser. "
                "Hover to pause auto-advance. Refreshes hourly."
            )
            self._label.setCursor(QCursor(Qt.PointingHandCursor))
            self._label.setStyleSheet("color: #cfe6ff; font-size: 11px;")
            self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._label.installEventFilter(self)
            hb.addWidget(self._label, stretch=1)

            self._cycle_timer = QTimer(self)
            self._cycle_timer.setInterval(CYCLE_INTERVAL_MS)
            self._cycle_timer.timeout.connect(self._advance)

            self._refresh_timer = QTimer(self)
            self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
            self._refresh_timer.timeout.connect(self.force_refresh)

        # -- Public --

        def start(self) -> None:
            self.force_refresh()
            self._cycle_timer.start()
            self._refresh_timer.start()

        def stop(self) -> None:
            self._cycle_timer.stop()
            self._refresh_timer.stop()
            self._teardown_worker()

        def force_refresh(self) -> None:
            if self._worker_thread is not None:
                # Previous fetch still in flight — skip.
                return
            self._worker_thread = QThread(self)
            self._worker = _FetchWorker()
            self._worker.moveToThread(self._worker_thread)
            self._worker_thread.started.connect(self._worker.run)
            self._worker.headlinesReady.connect(self._on_headlines)
            self._worker.failed.connect(self._on_fetch_failed)
            self._worker.headlinesReady.connect(self._worker_thread.quit)
            self._worker.failed.connect(self._worker_thread.quit)
            self._worker_thread.finished.connect(self._teardown_worker)
            self._worker_thread.start()

        def current_headlines(self) -> list[NewsHeadline]:
            return list(self._headlines)

        # -- Slots --

        def _on_headlines(self, headlines: list) -> None:
            if headlines:
                self._headlines = list(headlines)
                self._index = 0
                self._last_refresh_ts = time.time()
                self._render_current()
            else:
                self._label.setText("(no crypto news feeds reachable)")

        def _on_fetch_failed(self, msg: str) -> None:
            logger.debug("crypto_news_ticker fetch failed: %s", msg)
            if not self._headlines:
                self._label.setText("(crypto news feeds unavailable)")

        def _advance(self) -> None:
            if self._paused or not self._headlines:
                return
            self._index = (self._index + 1) % len(self._headlines)
            self._render_current()

        def _render_current(self) -> None:
            if not self._headlines:
                return
            h = self._headlines[self._index]
            _prefix = f"[{self._index + 1}/{len(self._headlines)}] "
            self._label.setText(_prefix + h.display_text())
            self._label.setToolTip(
                f"{h.source.name} — click to open in default browser.\n" f"{h.url}"
            )

        def _teardown_worker(self) -> None:
            if self._worker_thread is not None:
                try:
                    self._worker_thread.wait(50)
                except (
                    Exception
                ):  # noqa: BLE001, S110 - thread wait best-effort during teardown
                    pass
                self._worker_thread.deleteLater()
            self._worker_thread = None
            self._worker = None

        # -- Event filter for hover-pause + click-to-open --

        def eventFilter(self, watched, event) -> bool:
            if watched is self._label:
                et = event.type()
                # QEvent.Enter = 10, Leave = 11, MouseButtonRelease = 3
                if et == 10:
                    self._paused = True
                    return False
                if et == 11:
                    self._paused = False
                    return False
                if et == 3 and self._headlines:
                    h = self._headlines[self._index]
                    try:
                        import webbrowser

                        webbrowser.open(h.url, new=2)
                    except Exception as _wb_exc:  # noqa: BLE001
                        logger.warning(
                            "News ticker: open failed for %r: %s", h.url, _wb_exc
                        )
                    return True
            return super().eventFilter(watched, event)
