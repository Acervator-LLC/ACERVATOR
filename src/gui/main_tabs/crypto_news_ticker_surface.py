"""crypto_news_ticker_surface.py -- the news strip in the exchange header.

Describes the strip the operator sees between the Privacy Mode button
and the "+ New Bot" button. It holds one line of text that shows one
story at a time, changes story every 15 seconds, refetches every hour,
pauses while the pointer rests on it, and opens the story in the
default browser when it is clicked.

It also describes the fetch that fills it: ten feed addresses, the
reading of one feed body under a size cap and a deadline, the parsing
of both feed shapes, the merge of ten answers into one list newest
first, and the worker that carries all of it.

THE WORKER, AS DATA. ``WORKER_LIFECYCLE`` names what starts the fetch
worker, what holds it, what stops it, and what happens to it when the
strip is destroyed. The shipped strip builds its worker thread with no
owner, so a search for threads belonging to the strip finds none and
the fetch outlives the screen. That is described here, not repaired
here.

Nothing in this file reaches the network, the clock, the file system or
a browser. Each of those is handed in: ``request_factory`` and
``opener`` for the transport, ``clock`` for the time, ``open_url`` for
the browser. Nothing runs at import.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``crypto_news_ticker.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from functools import partial
from typing import Callable, Optional

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

logger = logging.getLogger("acervator.crypto_news_ticker")

METHOD = "crypto_news_ticker.state"

LOGGER_NAME = "acervator.crypto_news_ticker"

ACCESSIBLE_NAME = "Crypto News Ticker"


@dataclass(frozen=True)
class NewsSource:
    """One feed: its short name, its printed name and its address."""

    slug: str
    name: str
    url: str


NEWS_SOURCES: tuple = (
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

SOURCE_JOIN = " · "
TITLE_MAX_CHARS = 220
NO_TIMESTAMP = 0.0


@dataclass
class NewsHeadline:
    """One story: its words, its address, its feed and its publish time."""

    title: str
    url: str
    source: NewsSource
    published_ts: float = NO_TIMESTAMP

    def display_text(self) -> str:
        """The printed "Source, Title" line for this story."""
        return f"{self.source.name}{SOURCE_JOIN}{self.title}"


INITIAL_TEXT = "Fetching crypto news…"
NO_FEEDS_TEXT = "(no crypto news feeds reachable)"
UNAVAILABLE_TEXT = "(crypto news feeds unavailable)"
LABEL_TOOLTIP = (
    "Cycling crypto + fintech headlines from 10 free RSS "
    "feeds. Click to open story in default browser. "
    "Hover to pause auto-advance. Refreshes hourly."
)
LABEL_STYLE = "color: #cfe6ff; font-size: 11px;"
LABEL_CURSOR = "PointingHandCursor"
LABEL_TEXT_FLAGS = "TextSelectableByMouse"
LABEL_STRETCH = 1
LAYOUT_MARGINS = (6, 2, 6, 2)
LAYOUT_SPACING = 6
POSITION_FORMAT = "[{position}/{total}] "
HEADLINE_TOOLTIP_FORMAT = "{name} — click to open in default browser.\n{url}"

CYCLE_INTERVAL_MS = 15_000
REFRESH_INTERVAL_MS = 60 * 60 * 1000
STOP_WAIT_MS = 2000
RETIRE_WAIT_MS = 1000

DEFAULT_TIMEOUT_S = 8.0
FETCH_BUDGET_S = DEFAULT_TIMEOUT_S * 2
FETCH_POLL_S = 0.05
READ_CHUNK_BYTES = 64 * 1024
MAX_FEED_BYTES = 4 * 1024 * 1024
MAX_FETCH_WORKERS = 10
FETCH_USER_AGENT = "Mozilla/5.0 (compatible; AcervatorNewsTicker/1.0; +local)"
FETCH_ACCEPT = (
    "application/rss+xml, application/atom+xml, " "application/xml, text/xml, */*"
)
USER_AGENT_HEADER = "User-Agent"
ACCEPT_HEADER = "Accept"
PARSE_LIMIT = 10
PER_SOURCE_LIMIT = 5

ITEM_TAGS = ("item", "entry")
TITLE_TAGS = ("title",)
LINK_TAGS = ("link",)
DATE_TAGS = ("pubDate", "published", "updated")
LINK_HREF = "href"
NAMESPACE_MARK = "}"
NO_TEXT = ""

EVENT_ENTER = 10
EVENT_LEAVE = 11
EVENT_MOUSE_RELEASE = 3
BROWSER_NEW_TAB = 2

REFUSED_FEED_LOG = "crypto_news_ticker: %s feed refused, no headline taken from it: %s"
MALFORMED_FEED_LOG = "crypto_news_ticker: %s feed did not parse: %s"
OVERSIZED_FEED_LOG = (
    "crypto_news_ticker: %s response exceeded %d bytes; dropped unparsed"
)
ALLOWLIST_LOG = "crypto_news_ticker: %s refused before fetch: %s"
FETCH_FAILED_LOG = "crypto_news_ticker: %s fetch failed: %s"
READ_STOPPED_LOG = "crypto_news_ticker: %s read abandoned, stop requested"
READ_BUDGET_LOG = "crypto_news_ticker: %s read abandoned, fetch budget spent"
FETCH_STOPPED_LOG = "crypto_news_ticker: fetch stopped with %d feed(s) outstanding"
BUDGET_SPENT_LOG = (
    "crypto_news_ticker: fetch budget of %.1fs spent with %d feed(s) outstanding"
)
AGGREGATE_LOG = "crypto_news_ticker: aggregate raised %s"
STILL_RUNNING_LOG = (
    "crypto_news_ticker: fetch thread signalled finished but is still "
    "running after %d ms; left alive rather than destroyed"
)
AT_EXIT_LOG = (
    "crypto_news_ticker: fetch thread still running at interpreter exit "
    "after %d ms; abandoned undestroyed"
)
ABANDONED_LOG = (
    "crypto_news_ticker: fetch thread did not stop within %d ms; abandoned "
    "undestroyed rather than aborting the process"
)
WIDGET_FETCH_FAILED_LOG = "crypto_news_ticker fetch failed: %s"
OPEN_FAILED_LOG = "News ticker: open failed for %r: %s"

NO_SOURCES_REFUSAL = "a fetch needs at least one feed"

SKIN: dict = {}
STYLE_SHEET = ""
BUS_TOPICS: tuple = ()
TIMERS = {"cycle": CYCLE_INTERVAL_MS, "refresh": REFRESH_INTERVAL_MS}
TIMER_DELAYS_MS = (CYCLE_INTERVAL_MS, REFRESH_INTERVAL_MS)

ACTIONS = {
    "cycle_timeout": "advance",
    "refresh_timeout": "force_refresh",
    "thread_started": "run_worker",
    "headlines_ready": "on_headlines",
    "fetch_failed": "on_fetch_failed",
    "thread_finished_teardown": "teardown_worker",
    "thread_finished_retire": "retire_worker",
}

WORKER_NAME = "fetch"

# The shipped strip builds its fetch thread with no owner, so a search
# for threads under the strip returns none and a teardown keyed on that
# search reports the strip clean while the fetch runs on.
WORKER_LIFECYCLE = {
    WORKER_NAME: {
        "started_by": ("start", "force_refresh", "refresh_timeout"),
        "held_by": "live_workers",
        "owner": "",
        "stopped_by": ("stop", "run_end", "release_workers"),
        "retired_by": "retire_worker",
        "on_screen_destroyed": "keeps_running",
        "found_by_owner_search": False,
        "one_at_a_time": True,
        "stop_wait_ms": STOP_WAIT_MS,
        "retire_wait_ms": RETIRE_WAIT_MS,
    }
}

THREAD_COUNT = 1
TIMER_COUNT = 2

TICKER_BUILT = "ticker.built"
FETCH_STARTED = "fetch.started"
FETCH_SKIPPED = "fetch.skipped"
FETCH_RAN = "fetch.ran"
HEADLINES_TAKEN = "headlines.taken"
HEADLINES_EMPTY = "headlines.empty"
FETCH_REFUSED = "fetch.refused"
ADVANCED = "ticker.advanced"
ADVANCE_HELD = "ticker.held"
RENDERED = "ticker.rendered"
CYCLE_STARTED = "cycle.started"
CYCLE_STOPPED = "cycle.stopped"
REFRESH_STARTED = "refresh.started"
REFRESH_STOPPED = "refresh.stopped"
WORKER_TORN_DOWN = "worker.torndown"
WORKER_RETIRED = "worker.retired"
WORKER_ABANDONED = "worker.abandoned"
WORKER_ASKED_TWICE = "worker.asked_twice"
WORKER_ABSENT = "worker.absent"
HOVER_PAUSED = "hover.paused"
HOVER_RELEASED = "hover.released"
STORY_OPENED = "story.opened"
STORY_OPEN_FAILED = "story.open_failed"
EVENT_IGNORED = "event.ignored"

TickerCall = list


def localname(tag: str) -> str:
    """One element name with its namespace taken off."""
    return tag.split(NAMESPACE_MARK, 1)[-1] if NAMESPACE_MARK in tag else tag


def child_text(parent, names: tuple) -> str:
    """The trimmed words of the first child element named in `names`."""
    for child in parent:
        if localname(child.tag) in names and child.text:
            return child.text.strip()
    return NO_TEXT


def parse_ts(raw: str) -> float:
    """One published date as unix seconds, or zero when it cannot be read.

    Reads the mail date form first and the plain date form second. A
    plain date carrying no zone is read in the machine's own zone, which
    is what the shipped strip does.
    """
    if not raw:
        return NO_TIMESTAMP
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.timestamp()
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime

        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        pass
    return NO_TIMESTAMP


def parse_rss(xml_bytes: bytes, source: NewsSource, limit: int = PARSE_LIMIT) -> list:
    """The stories in one feed body, at most `limit` of them.

    Reads both feed shapes: the older one that puts the address in the
    element text, and the newer one that puts it in an attribute. A body
    that cannot be read gives no stories rather than a refusal. A body
    declaring its own text shortcuts gives no stories and says so at
    warning level, because a feed host that starts sending them is worth
    seeing.

    The count is checked after a story is taken, so a limit of zero still
    gives one story. That is what the shipped strip does.
    """
    if not xml_bytes:
        return []
    try:
        root = fromstring(xml_bytes)
    except DefusedXmlException as refused:
        logger.warning(REFUSED_FEED_LOG, source.name, refused)
        return []
    except ParseError as malformed:
        logger.debug(MALFORMED_FEED_LOG, source.name, malformed)
        return []
    found: list = []
    for item in root.iter():
        if localname(item.tag) not in ITEM_TAGS:
            continue
        title = child_text(item, TITLE_TAGS)
        link = child_text(item, LINK_TAGS)
        if not link:
            for child in item:
                if localname(child.tag) in LINK_TAGS:
                    href = child.get(LINK_HREF)
                    if href:
                        link = href
                        break
        published_ts = parse_ts(child_text(item, DATE_TAGS))
        if title and link:
            found.append(
                NewsHeadline(
                    title=title.strip()[:TITLE_MAX_CHARS],
                    url=link.strip(),
                    source=source,
                    published_ts=published_ts,
                )
            )
        if len(found) >= limit:
            break
    return found


def never_stop() -> bool:
    """The default stop flag: nothing has asked for a stop."""
    return False


def zero_clock() -> float:
    """The default clock: one fixed instant, so no read moves on its own."""
    return 0.0


def read_bounded(
    reader,
    source: NewsSource,
    should_stop: Callable[[], bool] = never_stop,
    deadline: Optional[float] = None,
    clock: Callable[[], float] = zero_clock,
) -> Optional[bytes]:
    """One feed body read in pieces, or nothing when it is abandoned.

    Re-reads the stop flag and the deadline between pieces. One byte over
    the cap is taken on purpose, so a body exactly at the cap stays
    tellable from one that is too big.
    """
    parts: list = []
    taken = 0
    while True:
        if should_stop():
            logger.debug(READ_STOPPED_LOG, source.name)
            return None
        if deadline is not None and clock() > deadline:
            logger.debug(READ_BUDGET_LOG, source.name)
            return None
        remaining = MAX_FEED_BYTES + 1 - taken
        if remaining <= 0:
            break
        piece = reader.read(min(READ_CHUNK_BYTES, remaining))
        if not piece:
            break
        parts.append(piece)
        taken += len(piece)
    return b"".join(parts)


def fetch_one(
    source: NewsSource,
    request_factory,
    opener,
    timeout: float = DEFAULT_TIMEOUT_S,
    should_stop: Callable[[], bool] = never_stop,
    deadline: Optional[float] = None,
    clock: Callable[[], float] = zero_clock,
) -> list:
    """The stories from one feed, or none when anything goes wrong.

    ``request_factory`` builds the request and refuses an address whose
    scheme is not allowed; ``opener`` opens it. Both are handed in, so
    this function reaches no network of its own.
    """
    if should_stop():
        return []
    try:
        request = request_factory(source.url)
        request.add_header(USER_AGENT_HEADER, FETCH_USER_AGENT)
        request.add_header(ACCEPT_HEADER, FETCH_ACCEPT)
        with opener(request, timeout=timeout) as response:
            body = read_bounded(response, source, should_stop, deadline, clock)
        if body is None:
            return []
        if len(body) > MAX_FEED_BYTES:
            logger.warning(OVERSIZED_FEED_LOG, source.name, MAX_FEED_BYTES)
            return []
        return parse_rss(body, source)
    except ValueError as refused:
        logger.warning(ALLOWLIST_LOG, source.name, refused)
        return []
    except Exception as failed:
        logger.debug(FETCH_FAILED_LOG, source.name, failed)
        return []


def pool_size(sources: tuple) -> int:
    """How many feeds the shipped strip reads at once."""
    return min(len(sources), MAX_FETCH_WORKERS)


def fetch_all(
    request_factory,
    opener,
    sources: tuple = NEWS_SOURCES,
    per_source_limit: int = PER_SOURCE_LIMIT,
    should_stop: Callable[[], bool] = never_stop,
    budget_s: float = FETCH_BUDGET_S,
    clock: Callable[[], float] = zero_clock,
) -> list:
    """Every feed merged into one list, newest story first.

    Gives back what arrived inside `budget_s` and drops the rest. An
    empty feed list refuses: the shipped strip asks its worker pool for
    no workers, and the pool refuses that with a ValueError.
    """
    if pool_size(sources) <= 0:
        raise ValueError(NO_SOURCES_REFUSAL)
    deadline = clock() + budget_s
    found: list = []
    outstanding = list(sources)
    while outstanding:
        if should_stop():
            logger.debug(FETCH_STOPPED_LOG, len(outstanding))
            break
        if deadline - clock() <= 0:
            logger.warning(BUDGET_SPENT_LOG, budget_s, len(outstanding))
            break
        source = outstanding.pop(0)
        try:
            stories = fetch_one(
                source,
                request_factory,
                opener,
                DEFAULT_TIMEOUT_S,
                should_stop,
                deadline,
                clock,
            )
            found.extend(stories[:per_source_limit])
        except Exception as failed:
            logger.debug(AGGREGATE_LOG, failed)
    found.sort(key=lambda story: story.published_ts, reverse=True)
    return found


class FetchThreadModel:
    """One fetch thread, as far as the strip reads it.

    The strip asks a thread four things: whether it runs, that it stop,
    how long to wait for that, and that it be destroyed once it really
    has stopped. Nothing here starts a thread of its own.
    """

    def __init__(self) -> None:
        self.running = False
        self.interrupted = False
        self.quits = 0
        self.waits: list = []
        self.deleted = False
        self.finished: list = []

    def start(self) -> None:
        """Mark the thread as running."""
        self.running = True

    def is_running(self) -> bool:
        """Whether the thread has started and not yet stopped."""
        return self.running

    def request_interruption(self) -> None:
        """Raise the thread's own interruption flag."""
        self.interrupted = True

    def quit(self) -> None:
        """Ask the thread's event loop to end.

        An ask, not a stop: the thread ends its own loop when it reaches
        it, so the caller learns the answer from ``wait``.
        """
        self.quits += 1

    def wait(self, timeout_ms: int) -> bool:
        """Wait for the thread to stop. True when it has stopped."""
        self.waits.append(timeout_ms)
        self.running = False
        return True

    def delete_later(self) -> None:
        """Destroy the thread."""
        self.deleted = True

    def emit_finished(self) -> None:
        """Run every receiver wired to the thread's finished report."""
        for receiver in list(self.finished):
            receiver()


class FetchWorkerModel:
    """The fetch itself, carried by one thread.

    Holds a stop flag the fetch reads between feeds. A stopped fetch
    reports nothing: the strip that asked for the stop is going away, and
    an answer delivered to it reaches an object that is gone.
    """

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher
        self.stopping = False
        self.headlines_ready: list = []
        self.failed: list = []
        self.thread: Optional[FetchThreadModel] = None

    def request_stop(self) -> None:
        """Ask the fetch to abandon its outstanding feeds."""
        self.stopping = True

    def is_stopping(self) -> bool:
        """True once a stop has been asked for."""
        return self.stopping

    def disconnect(self) -> None:
        """Detach both reports, so a late answer reaches nothing."""
        self.headlines_ready = []
        self.failed = []

    def run(self) -> None:
        """Fetch, report, and end the thread carrying it, whatever happens."""
        try:
            try:
                stories = self.fetcher() if self.fetcher else []
            except Exception as failed:
                if not self.stopping:
                    self.say_failed(f"{type(failed).__name__}: {failed}")
                return
            if not self.stopping:
                self.say_ready(stories)
        finally:
            if self.thread is not None:
                self.thread.quit()
                self.thread.emit_finished()

    def say_ready(self, stories: list) -> None:
        """Hand one fetch answer to every receiver."""
        for receiver in list(self.headlines_ready):
            receiver(stories)

    def say_failed(self, message: str) -> None:
        """Hand one fetch refusal to every receiver."""
        for receiver in list(self.failed):
            receiver(message)


def retire_worker(thread: FetchThreadModel, live_workers: dict) -> None:
    """Destroy a fetch thread, but only once it has really stopped.

    A thread that reports finished while it still runs keeps its place in
    the register and is destroyed by nobody.
    """
    if thread.is_running() and not thread.wait(RETIRE_WAIT_MS):
        logger.error(STILL_RUNNING_LOG, RETIRE_WAIT_MS)
        return
    live_workers.pop(thread, None)
    thread.delete_later()


def release_workers(live_workers: dict) -> None:
    """Stop every live fetch thread before the program ends.

    A running thread whose last hold is dropped at shutdown ends the
    process with no report, so every one is asked to stop first. One that
    will not stop is abandoned rather than destroyed.
    """
    for worker in list(live_workers.values()):
        worker.request_stop()
    for thread in list(live_workers):
        thread.request_interruption()
        thread.quit()
        stopped = thread.wait(STOP_WAIT_MS)
        if not stopped:
            logger.error(AT_EXIT_LOG, STOP_WAIT_MS)
        live_workers.pop(thread, None)
        thread.delete_later()


class CryptoNewsTickerModel:
    """The news strip: one line of text, two waits and one fetch worker.

    ``start`` fetches now and starts both waits. ``stop`` ends both waits
    and the fetch. ``advance`` moves to the next story unless the pointer
    rests on the strip. Every step is appended to ``calls``.
    """

    def __init__(
        self,
        fetcher=None,
        open_url=None,
        clock=None,
        live_workers=None,
    ) -> None:
        self.fetcher = fetcher
        self.open_url = open_url
        self.clock = clock if clock is not None else zero_clock
        self.live_workers = {} if live_workers is None else live_workers
        self.calls: list = []
        self.opened: list = []
        self.headlines: list = []
        self.index = 0
        self.paused = False
        self.last_refresh_ts = NO_TIMESTAMP
        self.label_text = INITIAL_TEXT
        self.label_tooltip = LABEL_TOOLTIP
        self.cycle_running = False
        self.refresh_running = False
        self.worker_thread: Optional[FetchThreadModel] = None
        self.worker: Optional[FetchWorkerModel] = None
        self.fetches_started = 0
        self.calls.append([TICKER_BUILT])

    # ----- the two waits -----

    def start(self) -> None:
        """Fetch now and start both waits."""
        self.force_refresh()
        self.cycle_running = True
        self.refresh_running = True
        self.calls.append([CYCLE_STARTED, CYCLE_INTERVAL_MS])
        self.calls.append([REFRESH_STARTED, REFRESH_INTERVAL_MS])

    def stop(self) -> None:
        """End both waits and the fetch, if one is running."""
        self.cycle_running = False
        self.refresh_running = False
        self.calls.append([CYCLE_STOPPED])
        self.calls.append([REFRESH_STOPPED])
        self.stop_worker()

    # ----- the fetch -----

    def force_refresh(self) -> None:
        """Start a fetch now, unless one is already running.

        The thread is built with NO owner. The register below is the only
        hold on it, so destroying the strip destroys neither the thread
        nor the fetch it carries.
        """
        if self.worker_thread is not None:
            self.calls.append([FETCH_SKIPPED])
            return
        thread = FetchThreadModel()
        worker = FetchWorkerModel(self.fetcher)
        worker.thread = thread
        self.live_workers[thread] = worker
        self.worker_thread = thread
        self.worker = worker
        worker.headlines_ready.append(self.on_headlines)
        worker.failed.append(self.on_fetch_failed)
        thread.finished.append(self.teardown_worker)
        thread.finished.append(lambda: retire_worker(thread, self.live_workers))
        thread.start()
        self.fetches_started += 1
        self.calls.append([FETCH_STARTED, self.fetches_started])

    def run_worker(self) -> None:
        """Run the fetch the way the thread's started report runs it."""
        if self.worker is None:
            self.calls.append([WORKER_ABSENT])
            return
        self.calls.append([FETCH_RAN])
        self.worker.run()

    def current_headlines(self) -> list:
        """The stories the strip is cycling through."""
        return list(self.headlines)

    def on_headlines(self, headlines: list) -> None:
        """Take a fetch answer. An empty answer keeps the stories held."""
        if headlines:
            self.headlines = list(headlines)
            self.index = 0
            self.last_refresh_ts = self.clock()
            self.calls.append([HEADLINES_TAKEN, len(self.headlines)])
            self.render_current()
        else:
            self.label_text = NO_FEEDS_TEXT
            self.calls.append([HEADLINES_EMPTY])

    def on_fetch_failed(self, message: str) -> None:
        """Take a fetch refusal. Stories already held stay on the strip."""
        logger.debug(WIDGET_FETCH_FAILED_LOG, message)
        self.calls.append([FETCH_REFUSED])
        if not self.headlines:
            self.label_text = UNAVAILABLE_TEXT

    def advance(self) -> None:
        """Move to the next story, unless the pointer rests on the strip."""
        if self.paused or not self.headlines:
            self.calls.append([ADVANCE_HELD])
            return
        self.index = (self.index + 1) % len(self.headlines)
        self.calls.append([ADVANCED, self.index])
        self.render_current()

    def render_current(self) -> None:
        """Write the story under the index onto the strip."""
        if not self.headlines:
            return
        story = self.headlines[self.index]
        prefix = POSITION_FORMAT.format(
            position=self.index + 1, total=len(self.headlines)
        )
        self.label_text = prefix + story.display_text()
        self.label_tooltip = HEADLINE_TOOLTIP_FORMAT.format(
            name=story.source.name, url=story.url
        )
        self.calls.append([RENDERED, self.index])

    def teardown_worker(self) -> None:
        """Forget a fetch thread that has finished."""
        self.worker_thread = None
        self.worker = None
        self.calls.append([WORKER_TORN_DOWN])

    def retire_worker(self) -> None:
        """Destroy the fetch thread the strip last started."""
        thread = self.worker_thread
        if thread is None:
            self.calls.append([WORKER_ABSENT])
            return
        retire_worker(thread, self.live_workers)
        self.calls.append([WORKER_RETIRED])

    def stop_worker(self) -> None:
        """Ask the fetch to stop and wait for it with a real bound.

        The reports are detached first, so an answer already on its way
        lands on nothing. A wait that fails abandons the thread and keeps
        both holds, so a second ask adds nothing and writes nothing.
        """
        thread = self.worker_thread
        worker = self.worker
        if thread is None:
            self.calls.append([WORKER_ABSENT])
            return
        if worker is not None and worker.is_stopping():
            self.calls.append([WORKER_ASKED_TWICE])
            return
        if worker is not None:
            worker.disconnect()
            worker.request_stop()
        thread.request_interruption()
        thread.quit()
        stopped = thread.wait(STOP_WAIT_MS)
        if not stopped:
            logger.error(ABANDONED_LOG, STOP_WAIT_MS)
            self.calls.append([WORKER_ABANDONED])
            return
        self.worker_thread = None
        self.worker = None
        retire_worker(thread, self.live_workers)
        self.calls.append([WORKER_RETIRED])

    # ----- what the pointer does -----

    def handle_event(self, event_type: int, on_label: bool = True) -> bool:
        """One pointer event on the strip. True when the strip took it."""
        if not on_label:
            self.calls.append([EVENT_IGNORED, event_type])
            return False
        if event_type == EVENT_ENTER:
            self.paused = True
            self.calls.append([HOVER_PAUSED])
            return False
        if event_type == EVENT_LEAVE:
            self.paused = False
            self.calls.append([HOVER_RELEASED])
            return False
        if event_type == EVENT_MOUSE_RELEASE and self.headlines:
            story = self.headlines[self.index]
            try:
                if self.open_url is not None:
                    self.open_url(story.url, BROWSER_NEW_TAB)
                self.opened.append(story.url)
                self.calls.append([STORY_OPENED, story.url])
            except Exception as failed:
                logger.warning(OPEN_FAILED_LOG, story.url, failed)
                self.calls.append([STORY_OPEN_FAILED, type(failed).__name__])
            return True
        self.calls.append([EVENT_IGNORED, event_type])
        return False


PANE_MODEL: Optional[CryptoNewsTickerModel] = None

PANE_FETCHER: Optional[Callable[[], list]] = None

FETCH_THREAD_NAME = "acervator-news-fetch"


def build_model(headlines=None, clock=None) -> CryptoNewsTickerModel:
    """One strip already holding `headlines`, for a fresh paint."""
    model = CryptoNewsTickerModel(clock=clock)
    if headlines:
        model.on_headlines(list(headlines))
    return model


def use_fetch(request_factory, opener, clock: Callable[[], float]) -> None:
    """Hold the transport ``pane_model`` builds its strip's fetch from.

    ``request_factory`` and ``opener`` are handed in by whoever registers
    ``view_model``, so this module still reaches no network of its own.
    """
    global PANE_FETCHER, PANE_MODEL
    PANE_FETCHER = partial(fetch_all, request_factory, opener, clock=clock)
    PANE_MODEL = None


def pane_model() -> CryptoNewsTickerModel:
    """The strip this process is showing, built on the first request."""
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = CryptoNewsTickerModel(fetcher=PANE_FETCHER)
    return PANE_MODEL


def start_fetch(model: CryptoNewsTickerModel) -> Optional[threading.Thread]:
    """Run ``model.run_worker`` away from the request that asked for it.

    The strip keeps ``INITIAL_TEXT`` on the line until the answer lands,
    which is what the shipped strip shows while its worker runs.
    """
    if model.worker is None:
        return None
    thread = threading.Thread(
        target=model.run_worker, name=FETCH_THREAD_NAME, daemon=True
    )
    thread.start()
    return thread


def source_view(source: NewsSource) -> dict:
    """One feed, ready for the renderer."""
    return {"slug": source.slug, "name": source.name, "url": source.url}


def headline_view(headline: NewsHeadline) -> dict:
    """One story, ready for the renderer."""
    return {
        "title": headline.title,
        "url": headline.url,
        "source": source_view(headline.source),
        "published_ts": headline.published_ts,
        "display_text": headline.display_text(),
    }


def headline_from(row: dict) -> NewsHeadline:
    """One story built from what the renderer sent."""
    named = row.get("source") or {}
    return NewsHeadline(
        title=row.get("title", NO_TEXT),
        url=row.get("url", NO_TEXT),
        source=NewsSource(
            named.get("slug", NO_TEXT),
            named.get("name", NO_TEXT),
            named.get("url", NO_TEXT),
        ),
        published_ts=row.get("published_ts", NO_TIMESTAMP),
    )


def lifecycle_view() -> dict:
    """The worker lifecycle, ready for the renderer."""
    return {
        name: {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in row.items()
        }
        for name, row in WORKER_LIFECYCLE.items()
    }


def build_view_model(model: CryptoNewsTickerModel) -> dict:
    """Everything the renderer needs to draw one news strip."""
    return {
        "method": METHOD,
        "accessible_name": ACCESSIBLE_NAME,
        "label_text": model.label_text,
        "label_tooltip": model.label_tooltip,
        "label_style": LABEL_STYLE,
        "label_cursor": LABEL_CURSOR,
        "label_text_flags": LABEL_TEXT_FLAGS,
        "label_stretch": LABEL_STRETCH,
        "layout_margins": list(LAYOUT_MARGINS),
        "layout_spacing": LAYOUT_SPACING,
        "initial_text": INITIAL_TEXT,
        "no_feeds_text": NO_FEEDS_TEXT,
        "unavailable_text": UNAVAILABLE_TEXT,
        "position_format": POSITION_FORMAT,
        "headline_tooltip_format": HEADLINE_TOOLTIP_FORMAT,
        "headlines": [headline_view(story) for story in model.headlines],
        "index": model.index,
        "paused": model.paused,
        "last_refresh_ts": model.last_refresh_ts,
        "no_timestamp": NO_TIMESTAMP,
        "cycle_running": model.cycle_running,
        "refresh_running": model.refresh_running,
        "cycle_interval_ms": CYCLE_INTERVAL_MS,
        "refresh_interval_ms": REFRESH_INTERVAL_MS,
        "stop_wait_ms": STOP_WAIT_MS,
        "retire_wait_ms": RETIRE_WAIT_MS,
        "fetches_started": model.fetches_started,
        "worker_running": model.worker_thread is not None,
        "live_workers": len(model.live_workers),
        "opened": list(model.opened),
        "sources": [source_view(source) for source in NEWS_SOURCES],
        "source_join": SOURCE_JOIN,
        "title_max_chars": TITLE_MAX_CHARS,
        "default_timeout_s": DEFAULT_TIMEOUT_S,
        "fetch_budget_s": FETCH_BUDGET_S,
        "fetch_poll_s": FETCH_POLL_S,
        "read_chunk_bytes": READ_CHUNK_BYTES,
        "max_feed_bytes": MAX_FEED_BYTES,
        "max_fetch_workers": MAX_FETCH_WORKERS,
        "fetch_user_agent": FETCH_USER_AGENT,
        "fetch_accept": FETCH_ACCEPT,
        "user_agent_header": USER_AGENT_HEADER,
        "accept_header": ACCEPT_HEADER,
        "parse_limit": PARSE_LIMIT,
        "per_source_limit": PER_SOURCE_LIMIT,
        "item_tags": list(ITEM_TAGS),
        "title_tags": list(TITLE_TAGS),
        "link_tags": list(LINK_TAGS),
        "date_tags": list(DATE_TAGS),
        "link_href": LINK_HREF,
        "namespace_mark": NAMESPACE_MARK,
        "no_text": NO_TEXT,
        "event_enter": EVENT_ENTER,
        "event_leave": EVENT_LEAVE,
        "event_mouse_release": EVENT_MOUSE_RELEASE,
        "browser_new_tab": BROWSER_NEW_TAB,
        "no_sources_refusal": NO_SOURCES_REFUSAL,
        "refused_feed_log": REFUSED_FEED_LOG,
        "malformed_feed_log": MALFORMED_FEED_LOG,
        "oversized_feed_log": OVERSIZED_FEED_LOG,
        "allowlist_log": ALLOWLIST_LOG,
        "fetch_failed_log": FETCH_FAILED_LOG,
        "read_stopped_log": READ_STOPPED_LOG,
        "read_budget_log": READ_BUDGET_LOG,
        "fetch_stopped_log": FETCH_STOPPED_LOG,
        "budget_spent_log": BUDGET_SPENT_LOG,
        "aggregate_log": AGGREGATE_LOG,
        "still_running_log": STILL_RUNNING_LOG,
        "at_exit_log": AT_EXIT_LOG,
        "abandoned_log": ABANDONED_LOG,
        "widget_fetch_failed_log": WIDGET_FETCH_FAILED_LOG,
        "open_failed_log": OPEN_FAILED_LOG,
        "worker_name": WORKER_NAME,
        "worker_lifecycle": lifecycle_view(),
        "thread_count": THREAD_COUNT,
        "timer_count": TIMER_COUNT,
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "actions": dict(ACTIONS),
        "logger_name": LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``crypto_news_ticker.state``.

    Reads ``reset``, ``now``, ``headlines``, ``start``, ``hover``,
    ``advance``, ``click`` and ``stop`` from the request parameters. The
    strip keeps its stories and its place between calls because the
    shipped strip does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = CryptoNewsTickerModel()
    model = pane_model()
    if params.get("now") is not None:
        moment = float(params["now"])
        model.clock = lambda: moment
    headlines = params.get("headlines")
    if headlines is not None:
        model.on_headlines([headline_from(row) for row in headlines])
    if params.get("start", False):
        model.start()
        start_fetch(model)
    if params.get("hover") is not None:
        model.handle_event(EVENT_ENTER if params["hover"] else EVENT_LEAVE)
    for _step in range(int(params.get("advance", 0))):
        model.advance()
    if params.get("click", False):
        model.handle_event(EVENT_MOUSE_RELEASE)
    if params.get("stop", False):
        model.stop()
    return build_view_model(model)
