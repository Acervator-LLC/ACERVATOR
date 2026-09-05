"""crypto_news_ticker.py — the cycling crypto news strip.

``CryptoNewsTicker`` shows one headline at a time, advancing every
``CYCLE_INTERVAL_MS`` and refetching every ``REFRESH_INTERVAL_MS``.
``_FetchWorker`` runs ``fetch_all`` on a ``QThread`` in ``_LIVE_WORKERS``,
reading the ten ``NEWS_SOURCES`` through ``safe_urlopen`` under
``MAX_FEED_BYTES``. ``parse_rss`` builds ``NewsHeadline`` objects with
``defusedxml``, which refuses an entity declaration or an external reference.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from dataclasses import dataclass
from functools import partial
from typing import Callable, Optional

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from ..core.safe_url import SafeRequest, safe_urlopen

try:
    from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Qt, Signal
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout

    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False

logger = logging.getLogger("acervator.crypto_news_ticker")


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


# defusedxml keeps forbid_dtd off, so a feed with a bare doctype still parses.


def parse_rss(
    xml_bytes: bytes, source: NewsSource, limit: int = 10
) -> list[NewsHeadline]:
    """Return up to ``limit`` ``NewsHeadline`` objects parsed from ``xml_bytes``.

    Reads RSS 2.0 ``<item>`` and Atom ``<entry>`` elements; a malformed feed,
    or one ``DefusedXmlException`` refuses, returns [].
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
    """Convert an RFC-2822 or ISO-8601 ``raw`` string to unix seconds, or 0.0."""
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

        _r = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(_r).timestamp()
    except (TypeError, ValueError):
        pass
    return 0.0


DEFAULT_TIMEOUT_S = 8.0
FETCH_USER_AGENT = "Mozilla/5.0 (compatible; AcervatorNewsTicker/1.0; +local)"

# MAX_FEED_BYTES bounds one response body before any parser sees it.
MAX_FEED_BYTES = 4 * 1024 * 1024

# DEFAULT_TIMEOUT_S is per socket operation; FETCH_BUDGET_S caps a whole
# fetch_all, and FETCH_POLL_S is how often the collector re-reads the stop flag.
FETCH_BUDGET_S = DEFAULT_TIMEOUT_S * 2
FETCH_POLL_S = 0.05
READ_CHUNK_BYTES = 64 * 1024


def _never_stop() -> bool:
    """Default ``should_stop``: nothing has asked for a stop."""
    return False


def fetch_one(
    source: NewsSource,
    timeout: float = DEFAULT_TIMEOUT_S,
    should_stop: Callable[[], bool] = _never_stop,
    deadline: Optional[float] = None,
) -> list[NewsHeadline]:
    """Fetch and parse one ``source``, returning [] on any error.

    ``should_stop`` is polled before the socket opens and again between body
    chunks, and ``deadline`` is the ``time.monotonic()`` instant past which
    ``_read_bounded`` abandons the body.
    """
    if should_stop():
        return []
    try:
        # SafeRequest refuses a non-http(s) scheme at construction;
        # safe_urlopen checks again over an opener with no file or ftp handler.
        req = SafeRequest(source.url)
        req.add_header("User-Agent", FETCH_USER_AGENT)
        req.add_header(
            "Accept",
            "application/rss+xml, application/atom+xml, "
            "application/xml, text/xml, */*",
        )
        with safe_urlopen(req, timeout=timeout) as resp:
            body = _read_bounded(resp, source, should_stop, deadline)
        if body is None:
            return []
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
        # SafeRequest raises ValueError for a scheme outside the allowlist.
        logger.warning(
            "crypto_news_ticker: %s refused before fetch: %s", source.name, _refused
        )
        return []
    except Exception as _exc:  # noqa: BLE001 - per-feed best-effort
        logger.debug("crypto_news_ticker: %s fetch failed: %s", source.name, _exc)
        return []


def _read_bounded(
    resp, source: NewsSource, should_stop: Callable[[], bool], deadline: Optional[float]
) -> Optional[bytes]:
    """Read a response body in ``READ_CHUNK_BYTES`` chunks, or None if abandoned.

    Reading stops one byte past ``MAX_FEED_BYTES``, and returns None once
    ``should_stop`` is true or ``deadline`` has passed.
    """
    parts: list[bytes] = []
    taken = 0
    while True:
        if should_stop():
            logger.debug(
                "crypto_news_ticker: %s read abandoned, stop requested", source.name
            )
            return None
        if deadline is not None and time.monotonic() > deadline:
            logger.debug(
                "crypto_news_ticker: %s read abandoned, fetch budget " "spent",
                source.name,
            )
            return None
        remaining = MAX_FEED_BYTES + 1 - taken
        if remaining <= 0:
            break
        chunk = resp.read(min(READ_CHUNK_BYTES, remaining))
        if not chunk:
            break
        parts.append(chunk)
        taken += len(chunk)
    return b"".join(parts)


def fetch_all(
    sources: tuple[NewsSource, ...] = NEWS_SOURCES,
    per_source_limit: int = 5,
    should_stop: Callable[[], bool] = _never_stop,
    budget_s: float = FETCH_BUDGET_S,
) -> list[NewsHeadline]:
    """Fetch every source in parallel, merged by ``published_ts`` descending.

    Returns within ``budget_s``, and within ``FETCH_POLL_S`` of ``should_stop``
    turning true; a feed that has not answered by then is dropped.
    """
    deadline = time.monotonic() + budget_s
    out: list[NewsHeadline] = []
    pool = ThreadPoolExecutor(
        max_workers=min(len(sources), 10), thread_name_prefix="news-fetch"
    )
    try:
        pending = {
            pool.submit(fetch_one, s, DEFAULT_TIMEOUT_S, should_stop, deadline)
            for s in sources
        }
        while pending:
            if should_stop():
                logger.debug(
                    "crypto_news_ticker: fetch stopped with %d feed(s) " "outstanding",
                    len(pending),
                )
                break
            left = deadline - time.monotonic()
            if left <= 0:
                logger.warning(
                    "crypto_news_ticker: fetch budget of %.1fs spent "
                    "with %d feed(s) outstanding",
                    budget_s,
                    len(pending),
                )
                break
            done, pending = futures_wait(
                pending, timeout=min(FETCH_POLL_S, left), return_when=FIRST_COMPLETED
            )
            for f in done:
                try:
                    headlines = f.result()
                    out.extend(headlines[:per_source_limit])
                except Exception as _exc:  # noqa: BLE001 - per-feed best-effort
                    logger.debug("crypto_news_ticker: aggregate raised %s", _exc)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    out.sort(key=lambda h: h.published_ts, reverse=True)
    return out


if _HAS_QT:

    CYCLE_INTERVAL_MS = 15_000
    REFRESH_INTERVAL_MS = 60 * 60 * 1000

    # _stop_worker waits this long, then abandons the thread undestroyed:
    # destroying a running QThread ends the process in std::terminate.
    _STOP_WAIT_MS = 2000

    # _RETIRE_WAIT_MS covers only the unwinding after finished is delivered.
    _RETIRE_WAIT_MS = 1000

    _LIVE_WORKERS: "dict[QThread, _FetchWorker]" = {}

    def _retire_worker_thread(thread: QThread) -> None:
        """Destroy a fetch thread once ``isRunning`` is false.

        Runs on the GUI thread from ``QThread.finished``; a thread still
        running keeps its ``_LIVE_WORKERS`` entry and is not destroyed.
        """
        try:
            if thread.isRunning() and not thread.wait(_RETIRE_WAIT_MS):
                logger.error(
                    "crypto_news_ticker: fetch thread signalled finished "
                    "but is still running after %d ms; left alive rather "
                    "than destroyed",
                    _RETIRE_WAIT_MS,
                )
                return
        except RuntimeError:  # pragma: no cover
            _LIVE_WORKERS.pop(thread, None)  # already destroyed
            return
        _LIVE_WORKERS.pop(thread, None)
        thread.deleteLater()

    @atexit.register
    def _release_worker_threads_at_exit() -> None:
        """Stop every ``_LIVE_WORKERS`` thread before the interpreter tears down.

        Calls ``request_stop`` on each worker, then ``quit`` and ``wait`` on
        each thread, and logs one that outlasts ``_STOP_WAIT_MS``.
        """
        for _thread, _worker in list(_LIVE_WORKERS.items()):
            try:
                _worker.request_stop()
            except RuntimeError:  # pragma: no cover
                continue
        for _thread, _worker in list(_LIVE_WORKERS.items()):
            try:
                _thread.requestInterruption()
                _thread.quit()
                stopped = _thread.wait(_STOP_WAIT_MS)
            except RuntimeError:  # pragma: no cover
                _LIVE_WORKERS.pop(_thread, None)
                continue
            if not stopped:
                logger.error(
                    "crypto_news_ticker: fetch thread still running at "
                    "interpreter exit after %d ms; abandoned undestroyed",
                    _STOP_WAIT_MS,
                )
            _LIVE_WORKERS.pop(_thread, None)
            _thread.deleteLater()

    class _FetchWorker(QObject):
        """Run ``fetch_all`` on a worker thread and emit the result.

        ``headlinesReady`` carries the headlines and ``failed`` an error
        string; ``request_stop`` sets the ``threading.Event`` the fetch polls.
        """

        headlinesReady = Signal(list)
        failed = Signal(str)

        def __init__(self, parent: Optional[QObject] = None) -> None:
            """Build a worker whose stop flag is clear."""
            super().__init__(parent)
            self._stop = threading.Event()

        def request_stop(self) -> None:
            """Ask the fetch to abandon its outstanding feeds."""
            self._stop.set()

        def is_stopping(self) -> bool:
            """True once ``request_stop`` has been called."""
            return self._stop.is_set()

        def run(self) -> None:
            """Fetch, and emit nothing once ``request_stop`` has been called.

            Quits ``QThread.currentThread`` in a ``finally``, and never the
            ``QCoreApplication`` thread.
            """
            try:
                try:
                    headlines = fetch_all(should_stop=self._stop.is_set)
                except Exception as _exc:  # noqa: BLE001 - thread guard
                    if not self._stop.is_set():
                        self.failed.emit(f"{type(_exc).__name__}: {_exc}")
                    return
                if not self._stop.is_set():
                    self.headlinesReady.emit(headlines)
            finally:
                _thread = QThread.currentThread()
                _app = QCoreApplication.instance()
                if _thread is not None and (
                    _app is None or _thread is not _app.thread()
                ):
                    _thread.quit()

    class CryptoNewsTicker(QWidget):
        """Header-strip cycling news ticker.

        ``start`` begins the fetch and the cycling, ``stop`` halts both timers
        and the worker, ``force_refresh`` fetches at once, and
        ``current_headlines`` reads the cached queue. ``eventFilter`` pauses
        on hover and opens the current headline with ``webbrowser.open``.
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

        def start(self) -> None:
            self.force_refresh()
            self._cycle_timer.start()
            self._refresh_timer.start()

        def stop(self) -> None:
            """Halt both timers and the in-flight fetch, if any.

            Safe to call more than once, and while ``_FetchWorker`` is running.
            """
            self._cycle_timer.stop()
            self._refresh_timer.stop()
            self._stop_worker()

        def force_refresh(self) -> None:
            if self._worker_thread is not None:
                # _worker_thread is cleared by finished, never by a failed wait.
                return
            # The thread takes no parent; _LIVE_WORKERS holds it until it stops.
            thread = QThread()
            worker = _FetchWorker()
            _LIVE_WORKERS[thread] = worker
            self._worker_thread = thread
            self._worker = worker
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.headlinesReady.connect(self._on_headlines)
            worker.failed.connect(self._on_fetch_failed)
            # _retire_worker_thread is module-level, so _LIVE_WORKERS still
            # empties once the widget holding _teardown_worker is destroyed.
            thread.finished.connect(self._teardown_worker)
            thread.finished.connect(partial(_retire_worker_thread, thread))
            thread.start()

        def current_headlines(self) -> list[NewsHeadline]:
            return list(self._headlines)

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
            """Clear ``_worker_thread`` and ``_worker`` after ``finished``.

            Destruction belongs to ``_retire_worker_thread``, not here.
            """
            self._worker_thread = None
            self._worker = None

        def _stop_worker(self) -> None:
            """Ask the fetch to stop and wait ``_STOP_WAIT_MS`` for it.

            ``headlinesReady`` and ``failed`` are disconnected first, and a
            worker already reporting ``is_stopping`` returns at once; a thread
            that does not stop keeps both references and its
            ``_LIVE_WORKERS`` entry.
            """
            thread = self._worker_thread
            worker = self._worker
            if thread is None:
                return
            if worker is not None and worker.is_stopping():
                return
            if worker is not None:
                for _sig in (worker.headlinesReady, worker.failed):
                    try:
                        _sig.disconnect()
                    except (RuntimeError, TypeError):
                        pass  # never connected, or already gone
                worker.request_stop()
            try:
                thread.requestInterruption()
                thread.quit()
                stopped = thread.wait(_STOP_WAIT_MS)
            except RuntimeError:  # pragma: no cover
                self._worker_thread = None
                self._worker = None
                return
            if not stopped:
                # _worker_thread stays set, so force_refresh starts no second fetch.
                logger.error(
                    "crypto_news_ticker: fetch thread did not stop "
                    "within %d ms; abandoned undestroyed rather than "
                    "aborting the process",
                    _STOP_WAIT_MS,
                )
                return
            self._worker_thread = None
            self._worker = None
            _retire_worker_thread(thread)

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
