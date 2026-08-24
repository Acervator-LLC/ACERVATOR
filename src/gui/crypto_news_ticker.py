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
    from PySide6.QtCore import (
        QCoreApplication, QObject, QThread, QTimer, Qt, Signal)
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout
    _HAS_QT = True
except ImportError:                                # pragma: no cover
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
    NewsSource("coindesk", "CoinDesk",
               "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    NewsSource("cointelegraph", "CoinTelegraph",
               "https://cointelegraph.com/rss"),
    NewsSource("decrypt", "Decrypt",
               "https://decrypt.co/feed"),
    NewsSource("bitcoinmagazine", "Bitcoin Magazine",
               "https://bitcoinmagazine.com/.rss/full/"),
    NewsSource("thedefiant", "The Defiant",
               "https://thedefiant.io/api/feed"),
    NewsSource("bankless", "Bankless",
               "https://newsletter.banklesshq.com/feed"),
    NewsSource("cryptoslate", "CryptoSlate",
               "https://cryptoslate.com/feed/"),
    NewsSource("cryptobriefing", "Crypto Briefing",
               "https://cryptobriefing.com/feed/"),
    NewsSource("cryptonews", "CryptoNews",
               "https://cryptonews.com/news/feed/"),
    NewsSource("bloomberg", "Bloomberg Crypto",
               "https://feeds.bloomberg.com/crypto/news.rss"),
)


@dataclass
class NewsHeadline:
    title: str
    url: str
    source: NewsSource
    published_ts: float = 0.0   # unix seconds; 0 when unknown

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

def parse_rss(xml_bytes: bytes, source: NewsSource,
              limit: int = 10) -> list[NewsHeadline]:
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
            "crypto_news_ticker: %s feed refused, no headline taken "
            "from it: %s", source.name, _refused)
        return []
    except ParseError as _malformed:
        logger.debug(
            "crypto_news_ticker: %s feed did not parse: %s",
            source.name, _malformed)
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
        pub_ts = _parse_ts(
            _child_text(item, ("pubDate", "published", "updated")))
        if title and link:
            out.append(NewsHeadline(
                title=title.strip()[:220],
                url=link.strip(),
                source=source,
                published_ts=pub_ts))
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
FETCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; AcervatorNewsTicker/1.0; +local)")

# Refusing entity declarations bounds what a feed can make the parser
# ALLOCATE, but not what it can make the socket READ. A plain oversized
# response still lands in memory before any parser sees it, ten of them
# at once on a GUI worker thread. 4 MiB is far above any RSS feed --
# the largest source here is a full-text feed, which runs in the low
# hundreds of KB -- and 4 MiB x 10 sources bounds the worst case at
# 40 MiB instead of at whatever ten third-party hosts choose to send.
MAX_FEED_BYTES = 4 * 1024 * 1024

# ------------------------------------------------------------------
# Bounds on the fetch itself. Issue #105.
#
# The old code had NO bound. ``fetch_one`` passed 8 s to
# ``safe_urlopen``, but that is a per-SOCKET-OPERATION timeout: a host
# that sends one byte every 7 s resets it on every read, so a single
# feed could hold the worker for as long as it liked. ``fetch_all``
# then asked ``as_completed`` for a 16 s timeout, but its
# ``TimeoutError`` is raised BY THE ITERATOR, outside the per-future
# ``try``, so it escaped the ``for`` and left the
# ``with ThreadPoolExecutor(...)`` block -- whose ``__exit__`` calls
# ``shutdown(wait=True)`` and BLOCKS until every feed finishes. The
# timeout converted itself into an unbounded wait.
#
# That is why ``wait(50)`` in the widget could never succeed. The
# repair is here, not in the wait: give the fetch a real deadline and
# a stop flag, so the worker thread returns and the wait has something
# to succeed at.
#
#   FETCH_BUDGET_S  total wall time for one fetch_all, whatever the
#                   ten hosts do. Kept at the number the old
#                   ``as_completed`` call already named -- one connect
#                   timeout plus one read timeout -- now ENFORCED.
#   FETCH_POLL_S    how long the collector blocks before it re-reads
#                   the stop flag. This is where the number 50 ms
#                   honestly belongs: it bounds a wait on a LOCAL
#                   condition variable, not on a network call.
#   READ_CHUNK_BYTES  body read granularity. The stop flag and the
#                   deadline are re-read between chunks, so a feed
#                   that streams slowly is abandoned instead of
#                   followed to its end.
FETCH_BUDGET_S = DEFAULT_TIMEOUT_S * 2
FETCH_POLL_S = 0.05
READ_CHUNK_BYTES = 64 * 1024


def _never_stop() -> bool:
    """Default ``should_stop``: nothing has asked for a stop."""
    return False


def fetch_one(source: NewsSource,
              timeout: float = DEFAULT_TIMEOUT_S,
              should_stop: Callable[[], bool] = _never_stop,
              deadline: Optional[float] = None) -> list[NewsHeadline]:
    """Blocking single-feed fetch + parse. Returns [] on any error.

    ``should_stop`` is polled before the socket opens and again between
    body chunks; ``deadline`` is a ``time.monotonic()`` instant past
    which the body is abandoned. Both exist so a teardown does not have
    to wait for a third-party host. Neither is an error: an abandoned
    feed returns [], the same as an unreachable one.
    """
    if should_stop():
        return []
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
            "application/xml, text/xml, */*")
        with safe_urlopen(req, timeout=timeout) as resp:
            body = _read_bounded(resp, source, should_stop, deadline)
        if body is None:
            return []
        if len(body) > MAX_FEED_BYTES:
            logger.warning(
                "crypto_news_ticker: %s response exceeded %d bytes; "
                "dropped unparsed", source.name, MAX_FEED_BYTES)
            return []
        return parse_rss(body, source)
    except ValueError as _refused:
        # The allowlist rejected this source before any socket opened.
        # Every NEWS_SOURCES entry is an https literal today, so this
        # can only fire once the source list carries a scheme it must
        # not have -- the one day it has to be loud, not debug.
        logger.warning(
            "crypto_news_ticker: %s refused before fetch: %s",
            source.name, _refused)
        return []
    except Exception as _exc:  # noqa: BLE001 - per-feed best-effort
        logger.debug(
            "crypto_news_ticker: %s fetch failed: %s",
            source.name, _exc)
        return []


def _read_bounded(resp, source: NewsSource,
                  should_stop: Callable[[], bool],
                  deadline: Optional[float]) -> Optional[bytes]:
    """Read a response body in chunks. Return None when abandoned.

    ``resp.read(MAX_FEED_BYTES + 1)`` in one call was correct about the
    size cap and blind to everything else: it could not be interrupted
    and it could not time out as a whole, because urllib's timeout
    restarts on every socket operation. Reading in chunks keeps the
    same cap -- one byte over, on purpose, so "exactly at the limit"
    stays distinguishable from "truncated" -- and adds two exits the
    single call did not have.

    Returning None rather than the partial bytes is deliberate. A
    truncated feed is not a shorter feed; it is XML that stops in the
    middle, and handing it to the parser would trade a clean abandon
    for a parse error logged as if the host were malformed.
    """
    parts: list[bytes] = []
    taken = 0
    while True:
        if should_stop():
            logger.debug(
                "crypto_news_ticker: %s read abandoned, stop requested",
                source.name)
            return None
        if deadline is not None and time.monotonic() > deadline:
            logger.debug(
                "crypto_news_ticker: %s read abandoned, fetch budget "
                "spent", source.name)
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


def fetch_all(sources: tuple[NewsSource, ...] = NEWS_SOURCES,
              per_source_limit: int = 5,
              should_stop: Callable[[], bool] = _never_stop,
              budget_s: float = FETCH_BUDGET_S) -> list[NewsHeadline]:
    """Fetch every source in parallel, merge, sort by pubDate
    descending (unknown timestamps sink to the end).

    Returns within ``budget_s``, and within ``FETCH_POLL_S`` of
    ``should_stop`` turning true, whatever the ten hosts do. Feeds that
    have not answered by then are dropped and the headlines that DID
    arrive are still returned -- a partial ticker beats an empty one.

    The pool is shut down with ``wait=False``. That is the line that
    makes the bound real: the old ``with`` block joined every worker on
    the way out, so a timeout above it bought nothing.
    """
    deadline = time.monotonic() + budget_s
    out: list[NewsHeadline] = []
    pool = ThreadPoolExecutor(max_workers=min(len(sources), 10),
                              thread_name_prefix="news-fetch")
    try:
        pending = {
            pool.submit(fetch_one, s, DEFAULT_TIMEOUT_S,
                        should_stop, deadline)
            for s in sources
        }
        while pending:
            if should_stop():
                logger.debug(
                    "crypto_news_ticker: fetch stopped with %d feed(s) "
                    "outstanding", len(pending))
                break
            left = deadline - time.monotonic()
            if left <= 0:
                logger.warning(
                    "crypto_news_ticker: fetch budget of %.1fs spent "
                    "with %d feed(s) outstanding", budget_s, len(pending))
                break
            done, pending = futures_wait(
                pending, timeout=min(FETCH_POLL_S, left),
                return_when=FIRST_COMPLETED)
            for f in done:
                try:
                    headlines = f.result()
                    out.extend(headlines[:per_source_limit])
                except Exception as _exc:  # noqa: BLE001 - per-feed best-effort
                    logger.debug(
                        "crypto_news_ticker: aggregate raised %s", _exc)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    out.sort(key=lambda h: h.published_ts, reverse=True)
    return out


# ------------------------------------------------------------------
# Widget — cycling QLabel ticker.
# ------------------------------------------------------------------

if _HAS_QT:

    CYCLE_INTERVAL_MS = 15_000
    REFRESH_INTERVAL_MS = 60 * 60 * 1000  # 1 hour

    # ----------------------------------------------------------------
    # Worker-thread ownership. Issue #105, with issue #58.
    #
    # THE DEFECT. ``force_refresh`` built ``QThread(self)`` -- a thread
    # PARENTED TO THE WIDGET -- and ``_teardown_worker`` called
    # ``wait(50)`` and then ``deleteLater()`` whatever the wait
    # returned. Two destructions of a RUNNING QThread followed from
    # that, and Qt answers both with ``std::terminate``: no traceback,
    # no failure summary, exit 127.
    #
    #   * ``stop()`` mid-fetch. ``wait(50)`` returns False silently --
    #     a timeout is not an exception, so the ``except`` around it
    #     caught nothing -- and ``deleteLater()`` destroyed the thread
    #     anyway.
    #   * DESTROYING THE WIDGET. A parent destroys its children. So any
    #     path that destroyed the tab inherited the abort without ever
    #     calling ``stop()``.
    #
    # Measured on this file before the repair, offscreen, with
    # ``fetch_all`` replaced by a 3 s sleep: both recipes exit 127.
    #
    # THE MODEL NOW. A fetch thread has NO PARENT and owns its own
    # lifetime. ``_LIVE_WORKERS`` holds the only strong reference to
    # the thread and to its worker until the thread really stops, so:
    #
    #   * destroying the widget destroys neither of them;
    #   * the worker cannot be collected mid-fetch, which is the
    #     "Signal source has been deleted" half recorded as issue #58;
    #   * nothing is destroyed until ``finished`` has been seen.
    #
    # WHAT stop() DOES WHEN THE THREAD WILL NOT STOP. Of the three
    # honest answers -- wait longer, abandon without destroying, refuse
    # to destroy the widget -- this takes the second. It abandons the
    # thread, keeps it registered so nothing destroys it, and logs at
    # ERROR so the fault has a line to read. It never destroys, because
    # destroying is the abort.
    #
    # WHY 2000 ms IS NOT ANOTHER 50. It is not a network bound; the
    # network is no longer on this path, because ``fetch_all`` polls
    # its stop flag every ``FETCH_POLL_S`` and shuts its pool down
    # without joining. After the flag is set the worker returns inside
    # one poll slice, sorts a list of at most 50 headlines, and the
    # event loop of the thread sees the pending ``quit()``. 2000 ms is
    # 40x that slice. A miss means something other than the fetch is
    # wrong, which is why the miss is logged rather than absorbed.
    _STOP_WAIT_MS = 2000

    # After ``finished`` is delivered the thread has only to unwind.
    # This wait covers that unwinding, not any work.
    _RETIRE_WAIT_MS = 1000

    _LIVE_WORKERS: "dict[QThread, _FetchWorker]" = {}

    def _retire_worker_thread(thread: QThread) -> None:
        """Destroy a fetch thread, but only once it has really stopped.

        Runs on the GUI thread from ``QThread.finished``. The guard is
        not defensive noise: ``finished`` is emitted from inside the
        thread, so a queued delivery can arrive while ``isRunning()``
        is still true. A thread that is still running keeps its
        registration and is destroyed by nobody.
        """
        try:
            if thread.isRunning() and not thread.wait(_RETIRE_WAIT_MS):
                logger.error(
                    "crypto_news_ticker: fetch thread signalled finished "
                    "but is still running after %d ms; left alive rather "
                    "than destroyed", _RETIRE_WAIT_MS)
                return
        except RuntimeError:                       # pragma: no cover
            _LIVE_WORKERS.pop(thread, None)        # already destroyed
            return
        _LIVE_WORKERS.pop(thread, None)
        thread.deleteLater()

    @atexit.register
    def _release_worker_threads_at_exit() -> None:
        """Stop every live fetch thread before the interpreter tears down.

        This hook is required, not tidiness. Measured, offscreen: a
        parentless running QThread whose last Python reference is
        dropped at interpreter shutdown EXITS 127, because Python owns
        the wrapper and frees the C++ thread under it. Two repairs that
        look right were measured and rejected: handing the thread to
        ``QCoreApplication`` as a parent still exits 127, because the
        application destructor then destroys a running child, and
        ``Shiboken.invalidate`` exits 127 as well.

        So the hook stops the threads, which after the ``fetch_all``
        repair they do. For any thread that still will not stop,
        ``deleteLater()`` is the measured survivor: it moves ownership
        to C++, and no event loop is left to deliver the deferred
        delete. That is safe HERE and nowhere else -- inside a running
        application the loop would deliver it and abort the process,
        which is exactly the shipped defect this file repairs.
        """
        for _thread, _worker in list(_LIVE_WORKERS.items()):
            try:
                _worker.request_stop()
            except RuntimeError:                   # pragma: no cover
                continue
        for _thread, _worker in list(_LIVE_WORKERS.items()):
            try:
                _thread.requestInterruption()
                _thread.quit()
                stopped = _thread.wait(_STOP_WAIT_MS)
            except RuntimeError:                   # pragma: no cover
                _LIVE_WORKERS.pop(_thread, None)
                continue
            if not stopped:
                logger.error(
                    "crypto_news_ticker: fetch thread still running at "
                    "interpreter exit after %d ms; abandoned undestroyed",
                    _STOP_WAIT_MS)
            _LIVE_WORKERS.pop(_thread, None)
            _thread.deleteLater()

    class _FetchWorker(QObject):
        """Runs fetch_all() in a worker thread; emits results back.

        Carries a plain ``threading.Event`` rather than the QThread
        interruption flag. ``fetch_all`` hands the flag to pool
        threads, and a Qt object read from a thread whose lifetime it
        does not control is a second lifetime problem. An Event has
        none.
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
            """Fetch on the worker thread; emit nothing once stopped.

            Ends by quitting its own thread, in a ``finally``. That is
            not tidiness. The fetch is one shot, but the thread runs an
            event loop, so it exits only when something calls ``quit``.
            Before, the only callers were the two result signals -- and
            a STOPPED fetch emits neither, and a widget that has been
            destroyed calls nothing at all. Both cases left an event
            loop spinning for the life of the process. Quitting from
            inside the run is the one path that covers every outcome,
            and ``currentThread()`` is the thread itself, so there is
            no other lifetime to be right about.
            """
            try:
                try:
                    headlines = fetch_all(should_stop=self._stop.is_set)
                except Exception as _exc:  # noqa: BLE001 - thread guard
                    if not self._stop.is_set():
                        self.failed.emit(f"{type(_exc).__name__}: {_exc}")
                    return
                # A stopped fetch stays silent. The widget that asked
                # for the stop is on its way out, and delivering a
                # result to it is how issue #58 reached a deleted
                # object.
                if not self._stop.is_set():
                    self.headlinesReady.emit(headlines)
            finally:
                # Never quit the GUI thread. `run` is only ever reached
                # from `QThread.started`, but a test or a future caller
                # that invokes it directly would otherwise stop the
                # event loop of the whole application from a finally.
                _thread = QThread.currentThread()
                _app = QCoreApplication.instance()
                if _thread is not None and (
                        _app is None or _thread is not _app.thread()):
                    _thread.quit()

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
                "Hover to pause auto-advance. Refreshes hourly.")
            self._label.setCursor(QCursor(Qt.PointingHandCursor))
            self._label.setStyleSheet(
                "color: #cfe6ff; font-size: 11px;")
            self._label.setTextInteractionFlags(
                Qt.TextSelectableByMouse)
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
            """Halt both timers and the in-flight fetch, if any.

            Safe to call more than once, and safe to call while a fetch
            is running. It never returns with a destroyed running
            thread behind it, which is the whole of issue #105.
            """
            self._cycle_timer.stop()
            self._refresh_timer.stop()
            self._stop_worker()

        def force_refresh(self) -> None:
            if self._worker_thread is not None:
                # Previous fetch still in flight — skip. The reference
                # is cleared by `finished`, not by a timed-out wait, so
                # this guard can no longer be talked into starting a
                # second fetch alongside a first (issue #58 tail).
                return
            # NO PARENT. A QThread parented to this widget makes
            # destroying the widget an attempt to destroy a running
            # thread, which Qt answers with std::terminate. The
            # registry below holds the reference instead, and drops it
            # only once the thread has really stopped.
            thread = QThread()
            worker = _FetchWorker()
            _LIVE_WORKERS[thread] = worker
            self._worker_thread = thread
            self._worker = worker
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.headlinesReady.connect(self._on_headlines)
            worker.failed.connect(self._on_fetch_failed)
            # No `result -> thread.quit` wiring here. `run` quits its
            # own thread in a finally, which also covers the outcomes
            # that emit nothing.
            # Two receivers, on purpose. The first is bound to this
            # widget and Qt drops it when the widget is destroyed; the
            # second is module-level and outlives the widget, so the
            # registry is emptied even when nobody is left to care.
            thread.finished.connect(self._teardown_worker)
            thread.finished.connect(partial(_retire_worker_thread,
                                            thread))
            thread.start()

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
            logger.debug(
                "crypto_news_ticker fetch failed: %s", msg)
            if not self._headlines:
                self._label.setText(
                    "(crypto news feeds unavailable)")

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
                f"{h.source.name} — click to open in default browser.\n"
                f"{h.url}")

        def _teardown_worker(self) -> None:
            """Forget a fetch thread that has finished.

            Reached from ``QThread.finished`` only. Destruction is not
            done here: ``_retire_worker_thread`` owns that, and it
            checks that the thread has really stopped first.
            """
            self._worker_thread = None
            self._worker = None

        def _stop_worker(self) -> None:
            """Ask the fetch to stop, and wait for it with a real bound.

            Order matters. The signals are detached FIRST, so a result
            that is already in flight lands on nothing instead of on a
            widget that is going away. Then the stop flag is set, the
            event loop of the thread is asked to quit, and the wait
            runs. Only a wait that SUCCEEDS permits destruction, and
            the destruction itself happens in
            ``_retire_worker_thread`` from ``finished``.

            ASKING TWICE DOES NOT DO THE WORK TWICE. When a wait fails
            the thread is abandoned and BOTH references stay set, so a
            later ``stop()`` -- an application close after a failed tab
            teardown, say -- arrives with the same worker still on the
            attribute. Without the guard below that second call:

              * detached signals that the first call already detached,
                which libpyside reports as ``Failed to disconnect
                (None) from signal`` -- the visible symptom, and the
                least of it;
              * blocked the GUI thread for another whole
                ``_STOP_WAIT_MS`` on a thread already flagged and
                already asked to quit;
              * wrote the abandon ERROR a second time, so the crash
                watchdog reads two failures where one happened.

            The last is why this is a correctness guard and not tidying
            up. A log the operator reads during a crash must not
            multiply its own entries by the number of times something
            polite called ``stop()``.

            ``is_stopping()`` is the whole test: it is set by
            ``request_stop`` on the first call and never cleared, and a
            worker that has finished has already had both references
            cleared by ``_teardown_worker``, so it cannot be reached
            here at all.
            """
            thread = self._worker_thread
            worker = self._worker
            if thread is None:
                return
            if worker is not None and worker.is_stopping():
                # Already asked, and the answer has not arrived yet.
                # `finished` clears the references whenever the thread
                # really stops; until then there is nothing to add.
                return
            if worker is not None:
                for _sig in (worker.headlinesReady, worker.failed):
                    try:
                        _sig.disconnect()
                    except (RuntimeError, TypeError):
                        pass          # never connected, or already gone
                worker.request_stop()
            try:
                thread.requestInterruption()
                thread.quit()
                stopped = thread.wait(_STOP_WAIT_MS)
            except RuntimeError:                   # pragma: no cover
                self._worker_thread = None
                self._worker = None
                return
            if not stopped:
                # Abandon it. Do NOT destroy it: destroying a running
                # QThread is the abort this repair exists to remove.
                # It stays in _LIVE_WORKERS, so nothing else destroys
                # it either, and `finished` retires it whenever it
                # arrives. _worker_thread stays set so force_refresh
                # will not start a second fetch beside this one.
                logger.error(
                    "crypto_news_ticker: fetch thread did not stop "
                    "within %d ms; abandoned undestroyed rather than "
                    "aborting the process", _STOP_WAIT_MS)
                return
            self._worker_thread = None
            self._worker = None
            _retire_worker_thread(thread)

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
                            "News ticker: open failed for %r: %s",
                            h.url, _wb_exc)
                    return True
            return super().eventFilter(watched, event)
