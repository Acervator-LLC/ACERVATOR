"""The shipped news strip and the Qt-free surface, side by side.

A failure means the view model carries a different word, a different
colour, a different tooltip, a different story, a different order, a
different wait, a different recorded step or a different refusal than
``CryptoNewsTicker``.

No test here reads or writes the operator's runtime tree, opens a
socket, reaches a feed host or opens a browser. Every feed body, story
and address below is invented, and every outward call is handed in.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import crypto_news_ticker as shipped
from src.gui.main_tabs import crypto_news_ticker_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.qt_wiring_counts import (
    bus_subscriptions_watched,
    connections_watched,
    io_watched,
    module_pulls,
    qt_free,
    timers_watched,
)
from tests.fixtures.quiet_news_ticker import (
    fetch_threads_running,
    install_quiet_ticker,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

STRIP_PATH = REPO_ROOT / "src/gui/crypto_news_ticker.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/crypto_news_ticker_surface.py"

PIXEL_SIZE = (620, 40)

FROZEN_NOW = 1_700_000_000.5

WIDGETS_HELD: list = []


# Nothing here reaches outside this process


@pytest.fixture(autouse=True)
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    The strip's whole job is fetching from ten hosts, so a stub that
    slipped would open a real socket. Each test is given its own counter,
    so the number never depends on what ran before it.
    """
    attempted: list = []

    def refuse(where):
        attempted.append(where)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *_found, **_named):
        return refuse(address)

    def watched_connect_ex(self, address, *_found, **_named):
        return refuse(address)

    def watched_create(address, *_found, **_named):
        return refuse(address)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", watched_connect_ex)
    monkeypatch.setattr(socket, "create_connection", watched_create)
    yield attempted


@pytest.fixture(autouse=True)
def own_worker_register(monkeypatch):
    """Give the shipped side its own worker register and empty it after.

    ``_LIVE_WORKERS`` is one dict for the whole process and the shipped
    strip writes to it, so a worker one test leaves behind would be
    counted by the next.
    """
    fresh: dict = {}
    monkeypatch.setattr(shipped, "_LIVE_WORKERS", fresh)
    yield fresh
    fresh.clear()


@pytest.fixture(autouse=True)
def no_fetch_thread_survives_this_test():
    """Fail the test that leaves a news fetch thread running behind it."""
    yield
    assert fetch_threads_running() == 0, "a news fetch thread outlived this test"


class FrozenTime:
    """The clock the shipped strip reads, held at one instant."""

    def __init__(self, moment=FROZEN_NOW):
        self.moment = moment

    def time(self):
        """The wall clock, as the shipped strip reads it."""
        return self.moment

    def monotonic(self):
        """The counting clock, as the shipped strip reads it."""
        return self.moment

    def __repr__(self):
        """One reading, spelled the same whichever instance holds it."""
        return "FrozenTime(%r)" % self.moment


def frozen_clock(moment=FROZEN_NOW):
    """The clock the surface is handed, held at the same instant."""
    return lambda: moment


# One starting state, handed to both sides


def rss(items, header=b'<?xml version="1.0"?>'):
    """One older-shape feed body holding `items`."""
    body = b"".join(items)
    return header + b'<rss version="2.0"><channel>' + body + b"</channel></rss>"


def item(title, link=b"https://story.invalid/1", date=None):
    """One story element for an older-shape feed body."""
    parts = b"<item><title>" + title + b"</title><link>" + link + b"</link>"
    if date is not None:
        parts += b"<pubDate>" + date + b"</pubDate>"
    return parts + b"</item>"


ATOM = (
    b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
    b"<entry><title>Atom story</title>"
    b'<link href="https://story.invalid/atom"/>'
    b"<published>2025-08-04T10:00:00Z</published></entry></feed>"
)

LONG_TITLE = b"x" * 300
TWO_HUNDRED = b"y" * 200
UNICODE_TITLE = "Δ fold ⚡ ünïcode".encode("utf-8")
MARKUP_TITLE = b"&lt;b&gt;bold&lt;/b&gt;"
APOSTROPHE_TITLE = b"Ekthelius&apos; Fold"
NEWLINE_TITLE = b"two\nlines"
WRONG_CAPITALS = b'<?xml version="1.0"?><RSS><CHANNEL><ITEM><TITLE>T</TITLE>'
WRONG_CAPITALS += b"<LINK>https://story.invalid/1</LINK></ITEM></CHANNEL></RSS>"

FEED_BODIES: dict = {
    "happy": rss([item(b"First", date=b"Mon, 04 Aug 2025 10:00:00 +0000")]),
    "atom": ATOM,
    "empty": b"",
    "no_items": rss([]),
    "many_items": rss(
        [
            item(b"M%d" % index, b"https://story.invalid/%d" % index)
            for index in range(8)
        ]
    ),
    "malformed": b"<rss><channel><item><title>x",
    "not_xml": b"just text, no angle brackets at all",
    "entities": (
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY boom "expanded">]>'
        b"<rss><channel><item><title>&boom;</title>"
        b"<link>https://story.invalid/1</link></item></channel></rss>"
    ),
    "doctype_no_entity": (
        b'<?xml version="1.0"?><!DOCTYPE rss>'
        b"<rss><channel><item><title>T</title>"
        b"<link>https://story.invalid/1</link></item></channel></rss>"
    ),
    "title_without_link": b"<rss><channel><item><title>T</title></item></channel></rss>",
    "link_without_title": (
        b"<rss><channel><item><link>https://story.invalid/1</link>"
        b"</item></channel></rss>"
    ),
    "unicode": rss([item(UNICODE_TITLE)]),
    "markup": rss([item(MARKUP_TITLE)]),
    "apostrophe": rss([item(APOSTROPHE_TITLE)]),
    "newline": rss([item(NEWLINE_TITLE)]),
    "two_hundred_characters": rss([item(TWO_HUNDRED)]),
    "long_title": rss([item(LONG_TITLE)]),
    "padded_title": rss([item(b"   spaced   ", b"   https://story.invalid/1   ")]),
    "wrong_capitals": WRONG_CAPITALS,
    "zero_date": rss([item(b"T", date=b"0")]),
    "negative_date": rss([item(b"T", date=b"-1")]),
    "text_where_a_date_belongs": rss([item(b"T", date=b"not a date at all")]),
    "iso_date": (
        b"<rss><channel><item><title>T</title>"
        b"<link>https://story.invalid/1</link>"
        b"<published>2025-08-04T10:00:00Z</published></item></channel></rss>"
    ),
    "iso_date_no_zone": (
        b"<rss><channel><item><title>T</title>"
        b"<link>https://story.invalid/1</link>"
        b"<updated>2025-08-04T10:00:00</updated></item></channel></rss>"
    ),
    "namespaced": (
        b'<?xml version="1.0"?><rss xmlns="http://purl.org/rss/1.0/">'
        b"<channel><item><title>Namespaced</title>"
        b"<link>https://story.invalid/1</link></item></channel></rss>"
    ),
    "atom_link_without_href": (
        b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        b"<entry><title>T</title><link/></entry></feed>"
    ),
    "empty_title": rss([item(b"")]),
}

PARSE_REFUSING: tuple = ()

TIE_DATE = b"Mon, 04 Aug 2025 10:00:00 +0000"


def merge_date(index):
    """One date per feed, so no two stories in a merge tie.

    Ten feeds are read at once and the worker pool hands back whichever
    finished first, so two stories carrying one date reach the merge in
    an order the machine chose. Every merge case therefore holds its own
    date, and the tied case is driven on its own.
    """
    return b"Mon, 04 Aug 2025 %02d:00:00 +0000" % index


def merge_sources(count=4):
    """One feed list both sides are handed, in one order."""
    return tuple(
        ("feed%d" % index, "Feed %d" % index, "https://feed%d.invalid/rss" % index)
        for index in range(count)
    )


def merge_bodies(sources):
    """One story per feed, each with its own date, keyed by address."""
    return {
        source[2]: rss(
            [
                item(
                    b"Story %d" % index,
                    b"https://story.invalid/%d" % index,
                    merge_date(index),
                )
            ]
        )
        for index, source in enumerate(sources)
    }


def tie_bodies(sources):
    """One story per feed, every one carrying the same date."""
    return {
        source[2]: rss(
            [item(b"Tie %d" % index, b"https://story.invalid/%d" % index, TIE_DATE)]
        )
        for index, source in enumerate(sources)
    }


class Reader:
    """One feed body, read the way a response body is read."""

    def __init__(self, body):
        self.body = body
        self.taken = 0
        self.reads: list = []

    def read(self, size=-1):
        """The next piece of the body, at most `size` bytes."""
        self.reads.append(size)
        if size is None or size < 0:
            piece = self.body[self.taken :]
        else:
            piece = self.body[self.taken : self.taken + size]
        self.taken += len(piece)
        return piece

    def __enter__(self):
        return self

    def __exit__(self, *found):
        return False


class Request:
    """One request, recording the headers the strip adds to it."""

    def __init__(self, url):
        self.url = url
        self.headers: list = []

    def add_header(self, name, value):
        """Record one header the strip asked for."""
        self.headers.append([name, value])


REFUSAL_KINDS = {
    "refused": lambda: OSError("the host refused the connection"),
    "timed_out": lambda: TimeoutError("the host answered nothing in time"),
    "gone": lambda: ConnectionResetError("the host closed the connection"),
}


def transport(bodies, refusals=None, requests=None, timeouts=None):
    """One transport both sides are handed, over one body table.

    `bodies` maps an address to the bytes that address answers with.
    `refusals` maps an address to the name of a refusal it raises
    instead. An address in neither table refuses as an unknown host.
    Every request built and every timeout asked for is recorded.
    """
    refusals = refusals or {}
    kept = requests if requests is not None else []
    waits = timeouts if timeouts is not None else []

    def request_factory(url):
        request = Request(url)
        kept.append(request)
        return request

    def opener(request, timeout=None):
        waits.append(timeout)
        if request.url in refusals:
            raise REFUSAL_KINDS[refusals[request.url]]()
        if request.url not in bodies:
            raise OSError("no such host in this test")
        return Reader(bodies[request.url])

    return request_factory, opener


def refusing_request_factory(url):
    """A request builder that refuses the address before any socket."""
    raise ValueError("this scheme is not allowed")


# Reading the two sides into one shape


def numbered(value):
    """One value with every number replaced by its own text.

    ``12`` and ``12.0`` are equal as numbers and hash apart, and two
    not-a-numbers are never equal to each other. Reading each number as
    its own text tells the first pair apart and lets the second pair
    agree.
    """
    if isinstance(value, bool):
        return ["bool", repr(value)]
    if isinstance(value, (int, float)):
        return [type(value).__name__, repr(value)]
    if isinstance(value, dict):
        return {key: numbered(found) for key, found in value.items()}
    if isinstance(value, (list, tuple)):
        return [numbered(found) for found in value]
    return value


TIE_MARK = "<an order the worker pool happened to finish in>"


def platform_chosen(value):
    """One merged list with a tied run put in one order.

    Ten feeds are read at once, and the pool hands back whichever
    finished first. Stories carrying the SAME date therefore reach the
    merge in an order the machine chose, not one the product chose, so a
    tied run is read as a set of stories rather than as a sequence.
    """
    if isinstance(value, dict):
        return {key: platform_chosen(found) for key, found in value.items()}
    if isinstance(value, (list, tuple)):
        return [platform_chosen(found) for found in value]
    return value


def tie_folded(stories):
    """One merged list with each tied run sorted by its own words."""
    folded: list = []
    run: list = []
    last = None
    for story in stories:
        moment = story["published_ts"]
        if run and moment != last:
            folded.extend(sorted(run, key=json.dumps))
            run = []
        run.append(story)
        last = moment
    folded.extend(sorted(run, key=json.dumps))
    return folded


def readable(value):
    """One value ready to compare: numbers as their own text."""
    return numbered(platform_chosen(value))


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(readable(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one step, keeping either that it worked or how it refused.

    Only the refusal TYPE is kept. Python words one failure differently
    between its own versions, so a wording written down here would pin
    the machine this file was written on.
    """
    try:
        run()
        return {"error": ""}
    except Exception as exc:
        return {"error": type(exc).__name__}


def headline_of(run):
    """The first line of a refusal, read off whichever side is driven."""
    try:
        run()
        return ""
    except Exception as exc:
        return str(exc).splitlines()[:1]


def story_shape(story):
    """One story read into the one shape both sides are read into."""
    return {
        "title": story.title,
        "url": story.url,
        "slug": story.source.slug,
        "name": story.source.name,
        "source_url": story.source.url,
        "published_ts": story.published_ts,
        "display_text": story.display_text(),
    }


def stories_shape(stories):
    """Every story read into the one shape both sides are read into."""
    return [story_shape(story) for story in stories]


# Parsing one feed body


def parse_both(name, limit=None):
    """One feed body through each side's parser, read into one shape."""
    old_source = shipped.NewsSource("feed", "Feed", "https://feed.invalid/rss")
    new_source = surface.NewsSource("feed", "Feed", "https://feed.invalid/rss")
    body = FEED_BODIES[name]
    if limit is None:
        old_run = lambda: shipped.parse_rss(body, old_source)
        new_run = lambda: surface.parse_rss(body, new_source)
    else:
        old_run = lambda: shipped.parse_rss(body, old_source, limit)
        new_run = lambda: surface.parse_rss(body, new_source, limit)
    old_kept: list = []
    new_kept: list = []
    old_outcome = guarded(lambda: old_kept.extend(old_run()))
    new_outcome = guarded(lambda: new_kept.extend(new_run()))
    return {
        "old": stories_shape(old_kept),
        "new": stories_shape(new_kept),
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
    }


def both_parsers_agree(run, note):
    """Fail unless the two parsers took the same stories from one body."""
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        run["old"],
        run["new"],
    )
    assert digest(run["old"]) == digest(run["new"]), "%s: %s against %s" % (
        note,
        digest(run["old"]),
        digest(run["new"]),
    )


@pytest.mark.parametrize("name", sorted(FEED_BODIES))
def test_the_two_parsers_take_the_same_stories(name):
    """The surface reads a feed body differently than the shipped strip."""
    both_parsers_agree(parse_both(name), name)


def test_every_feed_body_in_the_table_is_driven():
    """A feed body sits in the table that nothing ever drives."""
    driven = set()
    for name in FEED_BODIES:
        both_parsers_agree(parse_both(name), name)
        driven.add(name)
    assert driven == set(FEED_BODIES), sorted(driven ^ set(FEED_BODIES))
    assert len(FEED_BODIES) == len(driven)
    assert set(PICTURE_CASES) <= set(STRIP_STEPS), sorted(
        set(PICTURE_CASES) - set(STRIP_STEPS)
    )


@pytest.mark.parametrize("limit", [-1, 0, 1, 2, 7, 10, 1_000_000_000])
def test_a_story_limit_takes_the_same_count_on_both_sides(limit):
    """One side took a different number of stories for one limit."""
    both_parsers_agree(parse_both("many_items", limit=limit), str(limit))


def test_a_limit_of_zero_still_takes_one_story_on_both_sides():
    """The count is checked before a story is taken, not after."""
    run = parse_both("many_items", limit=0)
    assert len(run["old"]) == 1, run["old"]
    assert len(run["new"]) == 1, run["new"]
    assert len(parse_both("many_items", limit=3)["old"]) == 3


def test_a_title_longer_than_the_cap_is_cut_at_the_same_place():
    """One side kept more of a long title than the other."""
    run = parse_both("long_title")
    both_parsers_agree(run, "long_title")
    assert len(run["old"][0]["title"]) == surface.TITLE_MAX_CHARS
    assert len(run["new"][0]["title"]) == surface.TITLE_MAX_CHARS
    short = parse_both("two_hundred_characters")
    assert len(short["old"][0]["title"]) == 200


def test_a_feed_declaring_its_own_shortcuts_gives_no_story_on_either_side():
    """A feed body that declares text shortcuts was read anyway."""
    run = parse_both("entities")
    both_parsers_agree(run, "entities")
    assert run["old"] == []
    assert parse_both("doctype_no_entity")["old"], "a plain doctype must still read"


DATE_TEXTS = (
    "",
    "Mon, 04 Aug 2025 10:00:00 +0000",
    "Mon, 04 Aug 2025 10:00:00 GMT",
    "2025-08-04T10:00:00Z",
    "2025-08-04T10:00:00+02:00",
    "2025-08-04T10:00:00.500+02:00",
    "2025-08-04T10:00:00",
    "0",
    "-1",
    "1000000000",
    "not a date at all",
    "2025-13-45T99:00:00Z",
    "Δ",
    "y" * 200,
    "two\nlines",
    "<b>date</b>",
    "MON, 04 AUG 2025 10:00:00 +0000",
    "inf",
    "-inf",
    "nan",
)


@pytest.mark.parametrize("raw", DATE_TEXTS)
def test_a_published_date_reads_the_same_on_both_sides(raw):
    """One side read a published date differently than the other.

    The number itself is never written down. A plain date carrying no
    zone is read in the machine's own zone, so the value belongs to the
    host and only the agreement between the two sides is the product's.
    """
    old = guarded(lambda: shipped._parse_ts(raw))
    new = guarded(lambda: surface.parse_ts(raw))
    assert old == new, (raw, old, new)
    assert readable(shipped._parse_ts(raw)) == readable(surface.parse_ts(raw))


def test_the_date_reader_reports_a_real_date_and_an_unreadable_one():
    """The date reader gives one value for every text, so it reads nothing."""
    real = surface.parse_ts("Mon, 04 Aug 2025 10:00:00 +0000")
    unreadable = surface.parse_ts("not a date at all")
    assert real != unreadable
    assert unreadable == surface.NO_TIMESTAMP == 0.0
    assert real > 0
    assert shipped._parse_ts("Mon, 04 Aug 2025 10:00:00 +0000") == real


NAMESPACED_TAGS = (
    "item",
    "{http://purl.org/rss/1.0/}item",
    "{}item",
    "}item",
    "a}b}c",
    "",
    "Δ}entry",
)


@pytest.mark.parametrize("tag", NAMESPACED_TAGS)
def test_an_element_name_loses_its_namespace_the_same_way(tag):
    """One side reads a namespaced element name differently."""
    assert shipped._localname(tag) == surface.localname(tag), tag


# Fetching one feed


FETCH_CASES: dict = {
    "happy": {"body": "happy"},
    "atom": {"body": "atom"},
    "nothing": {"body": "empty"},
    "malformed": {"body": "malformed"},
    "not_xml": {"body": "not_xml"},
    "unicode": {"body": "unicode"},
    "markup": {"body": "markup"},
    "apostrophe": {"body": "apostrophe"},
    "newline": {"body": "newline"},
    "long_title": {"body": "long_title"},
    "two_hundred_characters": {"body": "two_hundred_characters"},
    "wrong_capitals": {"body": "wrong_capitals"},
    "text_where_a_date_belongs": {"body": "text_where_a_date_belongs"},
    "refused": {"refusal": "refused"},
    "timed_out": {"refusal": "timed_out"},
    "gone": {"refusal": "gone"},
    "unknown_host": {"body": None},
    "scheme_refused": {"body": "happy", "bad_scheme": True},
    "stopped": {"body": "happy", "stop": True},
    "past_deadline": {"body": "happy", "deadline": FROZEN_NOW - 1.0},
    "deadline_ahead": {"body": "happy", "deadline": FROZEN_NOW + 1.0},
    "oversized": {"body": "oversized"},
    "exactly_at_the_cap": {"body": "at_cap"},
}

FETCH_REFUSING: tuple = ()

FEED_URL = "https://feed.invalid/rss"


def fetch_body_table(name):
    """The body table one fetch case is driven with."""
    spec = FETCH_CASES[name]
    body = spec.get("body")
    if body is None:
        return {}
    if body == "oversized":
        return {FEED_URL: b"x" * (surface.MAX_FEED_BYTES + 5)}
    if body == "at_cap":
        return {FEED_URL: b"x" * surface.MAX_FEED_BYTES}
    return {FEED_URL: FEED_BODIES[body]}


def fetch_both(name, monkeypatch):
    """One fetch case through each side, read into one shape."""
    spec = FETCH_CASES[name]
    bodies = fetch_body_table(name)
    refusals = {FEED_URL: spec["refusal"]} if "refusal" in spec else {}
    should_stop = (lambda: True) if spec.get("stop") else shipped._never_stop
    deadline = spec.get("deadline")

    old_requests: list = []
    old_timeouts: list = []
    old_factory, old_opener = transport(bodies, refusals, old_requests, old_timeouts)
    if spec.get("bad_scheme"):
        old_factory = refusing_request_factory
    monkeypatch.setattr(shipped, "SafeRequest", old_factory)
    monkeypatch.setattr(shipped, "safe_urlopen", old_opener)
    monkeypatch.setattr(shipped, "time", FrozenTime())
    old_source = shipped.NewsSource("feed", "Feed", FEED_URL)
    old_kept: list = []
    old_outcome = guarded(
        lambda: old_kept.extend(
            shipped.fetch_one(
                old_source, shipped.DEFAULT_TIMEOUT_S, should_stop, deadline
            )
        )
    )

    new_requests: list = []
    new_timeouts: list = []
    new_factory, new_opener = transport(bodies, refusals, new_requests, new_timeouts)
    if spec.get("bad_scheme"):
        new_factory = refusing_request_factory
    new_source = surface.NewsSource("feed", "Feed", FEED_URL)
    new_kept: list = []
    new_outcome = guarded(
        lambda: new_kept.extend(
            surface.fetch_one(
                new_source,
                new_factory,
                new_opener,
                surface.DEFAULT_TIMEOUT_S,
                should_stop,
                deadline,
                frozen_clock(),
            )
        )
    )
    return {
        "old": stories_shape(old_kept),
        "new": stories_shape(new_kept),
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "old_headers": [request.headers for request in old_requests],
        "new_headers": [request.headers for request in new_requests],
        "old_timeouts": old_timeouts,
        "new_timeouts": new_timeouts,
    }


def both_fetches_agree(run, note):
    """Fail unless the two sides fetched the same stories the same way."""
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        run["old"],
        run["new"],
    )
    assert digest(run["old"]) == digest(run["new"]), note
    assert run["old_headers"] == run["new_headers"], "%s: %r against %r" % (
        note,
        run["old_headers"],
        run["new_headers"],
    )
    assert run["old_timeouts"] == run["new_timeouts"], "%s: %r against %r" % (
        note,
        run["old_timeouts"],
        run["new_timeouts"],
    )


@pytest.mark.parametrize("name", sorted(FETCH_CASES))
def test_one_feed_fetches_the_same_way_on_both_sides(name, monkeypatch):
    """The surface fetched one feed differently than the shipped strip."""
    both_fetches_agree(fetch_both(name, monkeypatch), name)


def test_every_fetch_case_in_the_table_is_driven(monkeypatch):
    """A fetch case sits in the table that nothing ever drives."""
    driven = set()
    for name in FETCH_CASES:
        both_fetches_agree(fetch_both(name, monkeypatch), name)
        driven.add(name)
    assert driven == set(FETCH_CASES), sorted(driven ^ set(FETCH_CASES))


def test_a_fetch_that_refuses_gives_no_story_and_no_refusal(monkeypatch):
    """A host that refuses took the whole strip down with it."""
    for name in ("refused", "timed_out", "gone", "unknown_host"):
        run = fetch_both(name, monkeypatch)
        both_fetches_agree(run, name)
        assert run["old"] == [], name
        assert run["old_outcome"] == {"error": ""}, name
    answered = fetch_both("happy", monkeypatch)
    assert answered["old"], "a reachable host gave nothing, so the zero says little"


def test_a_body_over_the_cap_is_dropped_and_one_at_the_cap_is_read(monkeypatch):
    """The size cap dropped the wrong body, or dropped none at all."""
    over = fetch_both("oversized", monkeypatch)
    both_fetches_agree(over, "oversized")
    assert over["old"] == []
    at_cap = fetch_both("exactly_at_the_cap", monkeypatch)
    both_fetches_agree(at_cap, "exactly_at_the_cap")
    assert at_cap["old"] == [], "a body of padding holds no story"
    assert surface.MAX_FEED_BYTES == 4 * 1024 * 1024


def test_the_two_headers_the_strip_adds_are_the_same_on_both_sides(monkeypatch):
    """The strip named itself differently to a feed host on one side."""
    run = fetch_both("happy", monkeypatch)
    assert run["old_headers"] == [
        [
            ["User-Agent", surface.FETCH_USER_AGENT],
            ["Accept", surface.FETCH_ACCEPT],
        ]
    ], run["old_headers"]
    assert run["new_headers"] == run["old_headers"]
    assert shipped.FETCH_USER_AGENT == surface.FETCH_USER_AGENT
    assert run["old_timeouts"] == [surface.DEFAULT_TIMEOUT_S], run["old_timeouts"]
    assert run["new_timeouts"] == run["old_timeouts"]
    assert shipped.DEFAULT_TIMEOUT_S == surface.DEFAULT_TIMEOUT_S == 8.0


def test_the_body_is_read_in_pieces_of_one_size_on_both_sides(monkeypatch):
    """One side read a feed body in a different number of pieces."""
    body = b"z" * (surface.READ_CHUNK_BYTES * 2 + 11)
    old_reader = Reader(body)
    new_reader = Reader(body)
    old_source = shipped.NewsSource("feed", "Feed", FEED_URL)
    new_source = surface.NewsSource("feed", "Feed", FEED_URL)
    monkeypatch.setattr(shipped, "time", FrozenTime())
    old_taken = shipped._read_bounded(old_reader, old_source, shipped._never_stop, None)
    new_taken = surface.read_bounded(new_reader, new_source)
    assert old_taken == new_taken == body
    assert old_reader.reads == new_reader.reads, (old_reader.reads, new_reader.reads)
    assert len(old_reader.reads) > 2, old_reader.reads


def test_a_read_that_is_stopped_gives_nothing_rather_than_a_short_body():
    """A stopped read handed back the part it had, which is not a feed."""
    body = b"z" * 64
    old_source = shipped.NewsSource("feed", "Feed", FEED_URL)
    new_source = surface.NewsSource("feed", "Feed", FEED_URL)
    stop = lambda: True
    assert shipped._read_bounded(Reader(body), old_source, stop, None) is None
    assert surface.read_bounded(Reader(body), new_source, stop) is None
    assert surface.read_bounded(Reader(body), new_source) == body


def test_a_read_past_its_deadline_gives_nothing_on_both_sides(monkeypatch):
    """A read that ran past its deadline was followed to the end anyway."""
    monkeypatch.setattr(shipped, "time", FrozenTime())
    body = b"z" * 64
    old_source = shipped.NewsSource("feed", "Feed", FEED_URL)
    new_source = surface.NewsSource("feed", "Feed", FEED_URL)
    spent = FROZEN_NOW - 1.0
    ahead = FROZEN_NOW + 1.0
    assert (
        shipped._read_bounded(Reader(body), old_source, shipped._never_stop, spent)
        is None
    )
    assert (
        surface.read_bounded(
            Reader(body), new_source, surface.never_stop, spent, frozen_clock()
        )
        is None
    )
    assert (
        shipped._read_bounded(Reader(body), old_source, shipped._never_stop, ahead)
        == body
    )
    assert (
        surface.read_bounded(
            Reader(body), new_source, surface.never_stop, ahead, frozen_clock()
        )
        == body
    )


def test_the_default_stop_flag_is_clear_on_both_sides():
    """The default stop flag asks for a stop, so no fetch ever runs."""
    assert shipped._never_stop() is False
    assert surface.never_stop() is False
    assert surface.zero_clock() == 0.0


# Merging every feed


MERGE_CASES: dict = {
    "four_feeds": {},
    "one_feed": {"count": 1},
    "ten_feeds": {"count": 10},
    "no_feeds": {"count": 0},
    "stopped": {"stop": True},
    "no_budget": {"budget_s": 0.0},
    "negative_budget": {"budget_s": -5.0},
    "one_billionth_budget": {"budget_s": 1e-9},
    "thousand_million_budget": {"budget_s": 1_000_000_000.0},
    "infinite_budget": {"budget_s": float("inf")},
    "minus_infinite_budget": {"budget_s": float("-inf")},
    "not_a_number_budget": {"budget_s": float("nan")},
    "limit_zero": {"per_source_limit": 0},
    "limit_one": {"per_source_limit": 1},
    "limit_negative": {"per_source_limit": -1},
    "limit_thousand_million": {"per_source_limit": 1_000_000_000},
    "one_feed_refuses": {"refuse": (1,)},
    "every_feed_refuses": {"refuse": (0, 1, 2, 3)},
    "one_feed_is_malformed": {"malformed": (2,)},
    "one_feed_is_empty": {"empty": (0,)},
    "one_feed_times_out": {"refuse": (3,), "kind": "timed_out"},
}

MERGE_REFUSING = ("no_feeds",)


def merge_body_table(spec, sources):
    """The body table and refusal table one merge case is driven with."""
    bodies = merge_bodies(sources)
    for index in spec.get("malformed", ()):
        bodies[sources[index][2]] = FEED_BODIES["malformed"]
    for index in spec.get("empty", ()):
        bodies[sources[index][2]] = FEED_BODIES["empty"]
    kind = spec.get("kind", "refused")
    refusals = {sources[index][2]: kind for index in spec.get("refuse", ())}
    return bodies, refusals


def merge_both(name, monkeypatch):
    """One merge case through each side, read into one shape."""
    spec = MERGE_CASES[name]
    sources = merge_sources(spec.get("count", 4))
    bodies, refusals = merge_body_table(spec, sources)
    should_stop = (lambda: True) if spec.get("stop") else shipped._never_stop
    budget_s = spec.get("budget_s", surface.FETCH_BUDGET_S)
    per_source_limit = spec.get("per_source_limit", surface.PER_SOURCE_LIMIT)

    old_factory, old_opener = transport(bodies, refusals)
    monkeypatch.setattr(shipped, "SafeRequest", old_factory)
    monkeypatch.setattr(shipped, "safe_urlopen", old_opener)
    monkeypatch.setattr(shipped, "time", FrozenTime())
    old_sources = tuple(shipped.NewsSource(*row) for row in sources)
    old_kept: list = []
    old_outcome = guarded(
        lambda: old_kept.extend(
            shipped.fetch_all(old_sources, per_source_limit, should_stop, budget_s)
        )
    )

    new_factory, new_opener = transport(bodies, refusals)
    new_sources = tuple(surface.NewsSource(*row) for row in sources)
    new_kept: list = []
    new_outcome = guarded(
        lambda: new_kept.extend(
            surface.fetch_all(
                new_factory,
                new_opener,
                new_sources,
                per_source_limit,
                should_stop,
                budget_s,
                frozen_clock(),
            )
        )
    )
    return {
        "old": stories_shape(old_kept),
        "new": stories_shape(new_kept),
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
    }


def both_merges_agree(run, note):
    """Fail unless the two sides merged the same stories in one order."""
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        run["old"],
        run["new"],
    )
    assert digest(run["old"]) == digest(run["new"]), note


@pytest.mark.parametrize("name", sorted(MERGE_CASES))
def test_the_two_sides_merge_every_feed_the_same_way(name, monkeypatch):
    """The surface merged ten feeds differently than the shipped strip."""
    both_merges_agree(merge_both(name, monkeypatch), name)


def test_every_merge_case_in_the_table_is_driven(monkeypatch):
    """A merge case sits in the table that nothing ever drives."""
    driven = set()
    for name in MERGE_CASES:
        both_merges_agree(merge_both(name, monkeypatch), name)
        driven.add(name)
    assert driven == set(MERGE_CASES), sorted(driven ^ set(MERGE_CASES))
    assert set(MERGE_REFUSING) <= set(MERGE_CASES)


def test_the_merged_list_puts_the_newest_story_first(monkeypatch):
    """The merged list is in the order the feeds answered, not by date."""
    run = merge_both("four_feeds", monkeypatch)
    both_merges_agree(run, "four_feeds")
    dates = [story["published_ts"] for story in run["old"]]
    assert dates == sorted(dates, reverse=True), dates
    assert len(set(dates)) == len(dates), "the case must hold no tie"
    assert len(run["old"]) == 4


def test_an_empty_feed_list_refuses_on_both_sides(monkeypatch):
    """One side read no feeds where the other refused to try."""
    run = merge_both("no_feeds", monkeypatch)
    assert run["old_outcome"]["error"] == "ValueError", run["old_outcome"]
    assert run["new_outcome"]["error"] == "ValueError", run["new_outcome"]
    assert run["old_outcome"] == run["new_outcome"]
    assert merge_both("one_feed", monkeypatch)["old_outcome"] == {"error": ""}
    assert surface.pool_size(()) == 0
    assert surface.pool_size(surface.NEWS_SOURCES) == surface.MAX_FETCH_WORKERS
    assert surface.pool_size(surface.NEWS_SOURCES[:3]) == 3


def test_a_merge_with_no_budget_gives_nothing_on_both_sides(monkeypatch):
    """A merge with its budget already spent read the feeds anyway."""
    for name in ("no_budget", "negative_budget", "minus_infinite_budget"):
        run = merge_both(name, monkeypatch)
        both_merges_agree(run, name)
        assert run["old"] == [], name
    assert merge_both("four_feeds", monkeypatch)["old"], "a real budget read nothing"


def test_a_stopped_merge_gives_nothing_on_both_sides(monkeypatch):
    """A merge asked to stop kept reading feeds."""
    run = merge_both("stopped", monkeypatch)
    both_merges_agree(run, "stopped")
    assert run["old"] == []


def test_a_tied_merge_holds_the_same_stories_on_both_sides(monkeypatch):
    """One side lost a story when every feed carried the same date.

    Ten feeds are read at once and the worker pool hands back whichever
    finished first, so the order inside a tied run belongs to the
    machine. The stories themselves belong to the product, and that is
    what is compared.
    """
    sources = merge_sources(4)
    bodies = tie_bodies(sources)
    old_factory, old_opener = transport(bodies)
    monkeypatch.setattr(shipped, "SafeRequest", old_factory)
    monkeypatch.setattr(shipped, "safe_urlopen", old_opener)
    monkeypatch.setattr(shipped, "time", FrozenTime())
    old_stories = stories_shape(
        shipped.fetch_all(tuple(shipped.NewsSource(*row) for row in sources))
    )
    new_factory, new_opener = transport(bodies)
    new_stories = stories_shape(
        surface.fetch_all(
            new_factory,
            new_opener,
            tuple(surface.NewsSource(*row) for row in sources),
            clock=frozen_clock(),
        )
    )
    assert len(old_stories) == len(new_stories) == 4
    assert len({story["published_ts"] for story in old_stories}) == 1
    assert tie_folded(old_stories) == tie_folded(new_stories)


def test_the_tie_reader_reports_a_lost_story_and_keeps_a_real_order():
    """The tie reader hides a lost story, or hides a real reordering."""
    tied = [
        {"title": "b", "published_ts": 1.0},
        {"title": "a", "published_ts": 1.0},
    ]
    assert tie_folded(tied) == tie_folded(list(reversed(tied)))
    assert tie_folded(tied) != tie_folded(tied[:1])
    dated = [
        {"title": "a", "published_ts": 2.0},
        {"title": "b", "published_ts": 1.0},
    ]
    assert tie_folded(dated) != tie_folded(list(reversed(dated)))
    assert tie_folded([]) == []


# The strip on screen


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def hold(widget):
    """Keep one widget alive so no later read reaches a collected object."""
    WIDGETS_HELD.append(widget)
    return widget


STORY_SPECS: dict = {
    "one": [("First", "https://story.invalid/1", "CoinDesk", 3.0)],
    "two": [
        ("First", "https://story.invalid/1", "CoinDesk", 3.0),
        ("Second", "https://story.invalid/2", "Decrypt", 2.0),
    ],
    "three": [
        ("First", "https://story.invalid/1", "CoinDesk", 3.0),
        ("Second", "https://story.invalid/2", "Decrypt", 2.0),
        ("Third", "https://story.invalid/3", "Bankless", 1.0),
    ],
    "unicode": [("Δ fold ⚡", "https://story.invalid/Δ", "CoinTelegraph", 3.0)],
    "markup": [("<b>bold</b>", "https://story.invalid/b", "<i>Src</i>", 3.0)],
    "apostrophe": [("Ekthelius' Fold", "https://story.invalid/a", "CoinDesk", 3.0)],
    "newline": [("two\nlines", "https://story.invalid/n", "Coin\nDesk", 3.0)],
    "two_hundred": [("y" * 200, "https://story.invalid/y", "CoinDesk", 3.0)],
    "empty_words": [("", "", "", 0.0)],
    "zero_date": [("Zero", "https://story.invalid/z", "CoinDesk", 0.0)],
    "negative_date": [("Back", "https://story.invalid/b", "CoinDesk", -1.0)],
    "thousand_million": [("Far", "https://story.invalid/f", "CoinDesk", 1e9)],
    "one_billionth": [("Tiny", "https://story.invalid/t", "CoinDesk", 1e-9)],
    "whole_number_date": [("Whole", "https://story.invalid/w", "CoinDesk", 12)],
    "decimal_date": [("Decimal", "https://story.invalid/d", "CoinDesk", 12.0)],
    "infinite": [("Ever", "https://story.invalid/i", "CoinDesk", float("inf"))],
    "minus_infinite": [("Never", "https://story.invalid/m", "CoinDesk", float("-inf"))],
    "not_a_number": [("Unknown", "https://story.invalid/u", "CoinDesk", float("nan"))],
    "number_where_text_belongs": [(5, "https://story.invalid/5", "CoinDesk", 3.0)],
    "text_where_a_number_belongs": [("Text", "https://story.invalid/x", "CD", "soon")],
    "wrong_capitals": [("FIRST", "HTTPS://STORY.INVALID/1", "COINDESK", 3.0)],
}


def build_stories(name, module):
    """The stories one case holds, built for one side out of one spec."""
    return [
        module.NewsHeadline(
            title=title,
            url=url,
            source=module.NewsSource(named.lower(), named, "https://feed.invalid/rss"),
            published_ts=moment,
        )
        for title, url, named, moment in STORY_SPECS[name]
    ]


STRIP_STEPS: dict = {
    "fresh": [],
    "one_story": [["headlines", "one"]],
    "two_stories": [["headlines", "two"]],
    "three_stories": [["headlines", "three"]],
    "advance_once": [["headlines", "two"], ["advance"]],
    "advance_twice": [["headlines", "two"], ["advance"], ["advance"]],
    "advance_past_the_end": [
        ["headlines", "three"],
        ["advance"],
        ["advance"],
        ["advance"],
    ],
    "advance_with_no_story": [["advance"]],
    "advance_while_held": [["headlines", "two"], ["hover_enter"], ["advance"]],
    "advance_after_release": [
        ["headlines", "two"],
        ["hover_enter"],
        ["advance"],
        ["hover_leave"],
        ["advance"],
    ],
    "empty_answer": [["headlines", None]],
    "empty_answer_after_stories": [["headlines", "two"], ["headlines", None]],
    "refusal": [["failed", "boom"]],
    "refusal_after_stories": [["headlines", "two"], ["failed", "boom"]],
    "refusal_then_stories": [["failed", "boom"], ["headlines", "two"]],
    "unicode": [["headlines", "unicode"]],
    "markup": [["headlines", "markup"]],
    "apostrophe": [["headlines", "apostrophe"]],
    "newline": [["headlines", "newline"]],
    "two_hundred": [["headlines", "two_hundred"]],
    "empty_words": [["headlines", "empty_words"]],
    "zero_date": [["headlines", "zero_date"]],
    "negative_date": [["headlines", "negative_date"]],
    "thousand_million": [["headlines", "thousand_million"]],
    "one_billionth": [["headlines", "one_billionth"]],
    "whole_number_date": [["headlines", "whole_number_date"]],
    "decimal_date": [["headlines", "decimal_date"]],
    "infinite": [["headlines", "infinite"]],
    "minus_infinite": [["headlines", "minus_infinite"]],
    "not_a_number": [["headlines", "not_a_number"]],
    "number_where_text_belongs": [["headlines", "number_where_text_belongs"]],
    "text_where_a_number_belongs": [["headlines", "text_where_a_number_belongs"]],
    "wrong_capitals": [["headlines", "wrong_capitals"]],
    "click_one": [["headlines", "one"], ["click"]],
    "click_after_advance": [["headlines", "two"], ["advance"], ["click"]],
    "click_with_no_story": [["click"]],
    "click_refused": [["headlines", "one"], ["click_refused"]],
    "hover_only": [["hover_enter"]],
    "event_elsewhere": [["headlines", "one"], ["elsewhere"]],
    "unknown_event": [["headlines", "one"], ["unknown_event"]],
    "shrink": [["headlines", "three"], ["advance"], ["advance"], ["headlines", "one"]],
    "grow": [["headlines", "one"], ["headlines", "three"], ["advance"]],
    "same_twice": [["headlines", "two"], ["headlines", "two"]],
    "answer_is_not_a_list": [["headlines_raw", 5]],
    "answer_is_a_number_where_a_list_belongs": [["headlines_raw", 1_000_000_000]],
    "refuse_part_way": [
        ["headlines", "two"],
        ["headlines_raw", 5],
        ["advance"],
    ],
    "click_after_a_refused_step": [
        ["headlines", "two"],
        ["headlines_raw", 5],
        ["click"],
    ],
}

STRIP_REFUSING: tuple = ()

PICTURE_CASES = (
    "fresh",
    "one_story",
    "two_stories",
    "advance_once",
    "empty_answer",
    "refusal",
    "unicode",
    "two_hundred",
)


class StubbornThread(surface.FetchThreadModel):
    """A fetch thread that will not stop inside the wait it is given."""

    def wait(self, timeout_ms):
        """Record the wait and report that the thread is still running."""
        self.waits.append(timeout_ms)
        return False


class StrayEvent:
    """One event type the strip is not wired for."""

    UNKNOWN = 77


def old_strip(monkeypatch, opens, refuse_open=False):
    """One real news strip, wired to record what it opens."""
    app()
    monkeypatch.setattr(shipped, "time", FrozenTime())

    def open_url(url, new=0):
        if refuse_open:
            raise OSError("no browser on this machine")
        opens.append([url, new])

    monkeypatch.setattr(webbrowser, "open", open_url)
    return hold(shipped.CryptoNewsTicker())


def new_strip(opens, refuse_open=False):
    """One surface news strip, wired to record what it opens."""

    def open_url(url, new=0):
        if refuse_open:
            raise OSError("no browser on this machine")
        opens.append([url, new])

    return surface.CryptoNewsTickerModel(open_url=open_url, clock=frozen_clock())


def old_steps(strip, steps, opens):
    """Every step one shipped strip takes, each one on its own."""
    from PySide6.QtCore import QEvent

    found = []
    for step in steps:
        name = step[0]
        if name == "headlines":
            spec = step[1]
            stories = build_stories(spec, shipped) if spec else []
            found.append(lambda stories=stories: strip._on_headlines(stories))
        elif name == "headlines_raw":
            found.append(lambda raw=step[1]: strip._on_headlines(raw))
        elif name == "failed":
            found.append(lambda message=step[1]: strip._on_fetch_failed(message))
        elif name == "advance":
            found.append(strip._advance)
        elif name == "hover_enter":
            found.append(
                lambda: strip.eventFilter(strip._label, QEvent(QEvent.Type.Enter))
            )
        elif name == "hover_leave":
            found.append(
                lambda: strip.eventFilter(strip._label, QEvent(QEvent.Type.Leave))
            )
        elif name in ("click", "click_refused"):
            found.append(
                lambda: strip.eventFilter(
                    strip._label, QEvent(QEvent.Type.MouseButtonRelease)
                )
            )
        elif name == "elsewhere":
            found.append(
                lambda: strip.eventFilter(strip, QEvent(QEvent.Type.MouseButtonRelease))
            )
        elif name == "unknown_event":
            found.append(
                lambda: strip.eventFilter(
                    strip._label, QEvent(QEvent.Type(StrayEvent.UNKNOWN))
                )
            )
        else:
            raise AssertionError("no such step: %r" % name)
    return found


def new_steps(model, steps, opens):
    """Every step one surface strip takes, each one on its own."""
    found = []
    for step in steps:
        name = step[0]
        if name == "headlines":
            spec = step[1]
            stories = build_stories(spec, surface) if spec else []
            found.append(lambda stories=stories: model.on_headlines(stories))
        elif name == "headlines_raw":
            found.append(lambda raw=step[1]: model.on_headlines(raw))
        elif name == "failed":
            found.append(lambda message=step[1]: model.on_fetch_failed(message))
        elif name == "advance":
            found.append(model.advance)
        elif name == "hover_enter":
            found.append(lambda: model.handle_event(surface.EVENT_ENTER))
        elif name == "hover_leave":
            found.append(lambda: model.handle_event(surface.EVENT_LEAVE))
        elif name in ("click", "click_refused"):
            found.append(lambda: model.handle_event(surface.EVENT_MOUSE_RELEASE))
        elif name == "elsewhere":
            found.append(
                lambda: model.handle_event(surface.EVENT_MOUSE_RELEASE, on_label=False)
            )
        elif name == "unknown_event":
            found.append(lambda: model.handle_event(StrayEvent.UNKNOWN))
        else:
            raise AssertionError("no such step: %r" % name)
    return found


def read_old_strip(strip):
    """One shipped strip read into the one shape both sides use."""
    layout = strip.layout()
    margins = layout.contentsMargins()
    return {
        "accessible_name": strip.accessibleName(),
        "label_text": strip._label.text(),
        "label_tooltip": strip._label.toolTip(),
        "label_style": strip._label.styleSheet(),
        "cursor": strip._label.cursor().shape().name,
        "text_flags": strip._label.textInteractionFlags().name,
        "stretch": layout.stretch(0),
        "margins": [
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ],
        "spacing": layout.spacing(),
        "index": strip._index,
        "paused": strip._paused,
        "stories": stories_shape(strip.current_headlines()),
        "cycle_running": strip._cycle_timer.isActive(),
        "refresh_running": strip._refresh_timer.isActive(),
        "cycle_interval_ms": strip._cycle_timer.interval(),
        "refresh_interval_ms": strip._refresh_timer.interval(),
        "worker_running": strip._worker_thread is not None,
        "last_refresh_ts": strip._last_refresh_ts,
    }


def read_new_strip(payload, model):
    """One surface strip read into the one shape both sides use."""
    return {
        "accessible_name": payload["accessible_name"],
        "label_text": payload["label_text"],
        "label_tooltip": payload["label_tooltip"],
        "label_style": payload["label_style"],
        "cursor": payload["label_cursor"],
        "text_flags": payload["label_text_flags"],
        "stretch": payload["label_stretch"],
        "margins": list(payload["layout_margins"]),
        "spacing": payload["layout_spacing"],
        "index": payload["index"],
        "paused": payload["paused"],
        "stories": stories_shape(model.current_headlines()),
        "cycle_running": payload["cycle_running"],
        "refresh_running": payload["refresh_running"],
        "cycle_interval_ms": payload["cycle_interval_ms"],
        "refresh_interval_ms": payload["refresh_interval_ms"],
        "worker_running": payload["worker_running"],
        "last_refresh_ts": payload["last_refresh_ts"],
    }


def drive(name, monkeypatch):
    """Both sides through the same steps, read into one shape."""
    steps = STRIP_STEPS[name]
    refuse_open = any(step[0] == "click_refused" for step in steps)

    old_opens: list = []
    old = old_strip(monkeypatch, old_opens, refuse_open)
    old_outcome = [guarded(step) for step in old_steps(old, steps, old_opens)]
    old_state = read_old_strip(old)

    new_opens: list = []
    model = new_strip(new_opens, refuse_open)
    new_outcome = [guarded(step) for step in new_steps(model, steps, new_opens)]
    new_state = read_new_strip(surface.build_view_model(model), model)
    return {
        "old": old_state,
        "new": new_state,
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "old_opens": old_opens,
        "new_opens": new_opens,
    }


def both_strips_agree(run, note):
    """Fail unless the two strips did the same thing and hold one state."""
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        readable(run["old"]),
        readable(run["new"]),
    )
    assert digest(run["old"]) == digest(run["new"]), "%s: %s against %s" % (
        note,
        digest(run["old"]),
        digest(run["new"]),
    )
    assert run["old_opens"] == run["new_opens"], "%s: %r against %r" % (
        note,
        run["old_opens"],
        run["new_opens"],
    )


@pytest.mark.parametrize("name", sorted(STRIP_STEPS))
def test_the_strip_is_the_shipped_strip(name, monkeypatch):
    """The surface describes a strip the shipped strip does not build."""
    both_strips_agree(drive(name, monkeypatch), name)


def test_every_step_sequence_in_the_table_is_driven(monkeypatch):
    """A step sequence sits in the table that nothing ever drives."""
    driven = set()
    for name in STRIP_STEPS:
        both_strips_agree(drive(name, monkeypatch), name)
        driven.add(name)
    assert driven == set(STRIP_STEPS), sorted(driven ^ set(STRIP_STEPS))
    assert len(STRIP_STEPS) == len(driven)


def test_a_sequence_that_refuses_part_way_leaves_the_same_strip(monkeypatch):
    """A step that refused left the two sides showing different words."""
    run = drive("refuse_part_way", monkeypatch)
    both_strips_agree(run, "refuse_part_way")
    kinds = [step["error"] for step in run["old_outcome"]]
    assert kinds[1] != "", kinds
    assert kinds[0] == "", kinds
    assert run["old"]["stories"], "the strip lost the stories it already had"


def test_the_outcomes_hold_both_an_answer_and_a_refusal(monkeypatch):
    """Every step answered, or every step refused, so the set proves nothing."""
    answered = []
    refused = []
    for name in STRIP_STEPS:
        run = drive(name, monkeypatch)
        for step in run["old_outcome"]:
            (refused if step["error"] else answered).append(name)
    assert answered, "no step answered"
    assert refused, "no step refused"


def test_the_file_drives_more_than_one_kind_of_refusal(monkeypatch):
    """Every refusal shares one type, so a swapped refusal reads as unchanged."""
    kinds = set()
    for name in STRIP_STEPS:
        kinds.update(
            step["error"]
            for step in drive(name, monkeypatch)["old_outcome"]
            if step["error"]
        )
    kinds.update(
        merge_both(name, monkeypatch)["old_outcome"]["error"] for name in MERGE_REFUSING
    )
    kinds.add(
        guarded(lambda: shipped.parse_rss(FEED_BODIES["malformed"], None))["error"]
    )
    assert len(kinds) > 1, kinds
    assert kinds == {"TypeError", "ValueError", "AttributeError"}, kinds
    assert guarded(lambda: 1) != guarded(lambda: 1 / 0)
    assert guarded(lambda: int("x"))["error"] == "ValueError"


def test_the_refusal_reader_reports_two_different_wordings(monkeypatch):
    """Two refusals worded apart read the same, so a wording change is unseen.

    Both wordings are read off the shipped side. Neither is written down:
    Python words one failure differently between its own versions.
    """
    first = headline_of(lambda: shipped.parse_rss(FEED_BODIES["malformed"], None))
    second = headline_of(lambda: shipped.fetch_all(()))
    assert first, "a misuse the shipped strip answered"
    assert second, "a misuse the shipped strip answered"
    assert first != second, (first, second)
    assert headline_of(lambda: None) == ""


def test_the_sample_hashes_are_reported(monkeypatch):
    """The comparison reports no hash, so nothing can be checked by hand."""
    one = drive("one_story", monkeypatch)
    fresh = drive("fresh", monkeypatch)
    assert len(digest(one["old"])) == 64
    assert digest(one["old"]) == digest(one["new"])
    assert digest(fresh["old"]) == digest(fresh["new"])
    assert digest(one["old"]) != digest(fresh["old"])


def test_two_genuinely_different_real_inputs_hash_apart(monkeypatch):
    """The hash gives one value for every strip, so it tells nothing apart."""
    one = drive("one_story", monkeypatch)
    three = drive("three_stories", monkeypatch)
    assert digest(one["old"]) != digest(three["new"]), "old one against new three"
    assert digest(three["old"]) != digest(one["new"]), "old three against new one"
    assert digest(one["old"]) == digest(one["new"])
    assert digest(three["old"]) == digest(three["new"])


def test_the_same_input_hashes_the_same_twice(monkeypatch):
    """The hash moves between two runs of one input, so it reads the clock."""
    assert digest(drive("two_stories", monkeypatch)["old"]) == digest(
        drive("two_stories", monkeypatch)["old"]
    )
    assert digest(drive("two_stories", monkeypatch)["new"]) == digest(
        drive("two_stories", monkeypatch)["new"]
    )


def test_a_whole_number_and_a_decimal_are_told_apart():
    """The reader treats 12 and 12.0 as one value, so a change reads as none."""
    assert readable(12) != readable(12.0)
    assert digest({"a": 12}) != digest({"a": 12.0})
    assert readable(True) != readable(1)


def test_two_not_a_numbers_built_apart_compare_equal():
    """The reader calls two not-a-numbers different, reporting a false change."""
    first = float("nan")
    second = float("inf") - float("inf")
    assert first != second
    assert readable(first) == readable(second)
    assert digest({"a": first}) == digest({"a": second})
    assert readable(float("inf")) != readable(float("-inf"))


# The fetch worker, and what owns it


def instant_fetch(stories):
    """A fetch that answers at once with `stories`, reaching no host."""

    def fetch(**_named):
        return list(stories)

    return fetch


def settle(strip, app_object, passes=40):
    """Let a finished fetch thread report back to the shipped strip."""
    for _pass in range(passes):
        app_object.processEvents()
        if strip._worker_thread is None:
            return True
    return False


def run_old_fetch(monkeypatch, stories, register):
    """One shipped strip through one whole fetch, read into one shape."""
    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch(stories))
    strip = hold(shipped.CryptoNewsTicker())
    strip.start()
    thread = strip._worker_thread
    started = 1 if thread is not None else 0
    if thread is not None:
        thread.wait(shipped._STOP_WAIT_MS)
    settled = settle(strip, found)
    strip.stop()
    return {
        "started": started,
        "settled": settled,
        "state": read_old_strip(strip),
        "registered": len(register),
    }


def run_new_fetch(stories):
    """One surface strip through one whole fetch, read into one shape."""
    model = surface.CryptoNewsTickerModel(
        fetcher=instant_fetch(stories), clock=frozen_clock()
    )
    model.start()
    model.run_worker()
    model.stop()
    return {
        "started": model.fetches_started,
        "settled": model.worker_thread is None,
        "state": read_new_strip(surface.build_view_model(model), model),
        "registered": len(model.live_workers),
    }


def test_a_whole_fetch_leaves_the_same_strip_on_both_sides(
    monkeypatch, own_worker_register
):
    """One side finished a fetch holding a different strip than the other."""
    old = run_old_fetch(monkeypatch, build_stories("two", shipped), own_worker_register)
    new = run_new_fetch(build_stories("two", surface))
    assert old["started"] == new["started"] == 1
    assert old["settled"] is new["settled"] is True
    assert old["registered"] == new["registered"] == 0
    assert readable(old["state"]) == readable(new["state"]), (
        old["state"],
        new["state"],
    )
    assert digest(old["state"]) == digest(new["state"])


def test_a_fetch_that_answers_nothing_leaves_the_same_words(
    monkeypatch, own_worker_register
):
    """An empty answer left the two sides showing different words."""
    old = run_old_fetch(monkeypatch, [], own_worker_register)
    new = run_new_fetch([])
    assert old["state"]["label_text"] == new["state"]["label_text"]
    assert old["state"]["label_text"] == surface.NO_FEEDS_TEXT
    assert readable(old["state"]) == readable(new["state"])


def test_a_second_fetch_beside_a_first_is_refused_on_both_sides(monkeypatch):
    """A second fetch started beside one already running."""
    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    held = threading.Event()

    def blocking(**_named):
        held.wait(5.0)
        return []

    monkeypatch.setattr(shipped, "fetch_all", blocking)
    strip = hold(shipped.CryptoNewsTicker())
    strip.force_refresh()
    first = strip._worker_thread
    strip.force_refresh()
    assert strip._worker_thread is first
    assert len(shipped._LIVE_WORKERS) == 1
    held.set()
    assert first.wait(shipped._STOP_WAIT_MS) is True
    assert settle(strip, found) is True
    assert len(shipped._LIVE_WORKERS) == 0

    model = surface.CryptoNewsTickerModel(clock=frozen_clock())
    model.force_refresh()
    only = model.worker_thread
    model.force_refresh()
    assert model.worker_thread is only
    assert model.fetches_started == 1
    assert len(model.live_workers) == 1
    assert surface.FETCH_SKIPPED in [call[0] for call in model.calls]
    model.run_worker()
    assert model.worker_thread is None
    assert len(model.live_workers) == 0


def test_the_fetch_thread_has_no_owner_on_either_side(monkeypatch):
    """The fetch thread gained an owner, so the two sides describe it apart."""
    from PySide6.QtCore import QThread

    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    held = threading.Event()
    monkeypatch.setattr(shipped, "fetch_all", lambda **_named: (held.wait(5.0), [])[1])
    strip = hold(shipped.CryptoNewsTicker())
    strip.start()
    thread = strip._worker_thread
    assert thread.parent() is None, "the fetch thread gained an owner"
    assert strip.findChildren(QThread) == [], "a search under the strip found it"
    assert thread.isRunning() is True
    assert len(shipped._LIVE_WORKERS) == 1
    held.set()
    assert thread.wait(shipped._STOP_WAIT_MS) is True
    assert settle(strip, found) is True
    strip.stop()

    row = surface.WORKER_LIFECYCLE[surface.WORKER_NAME]
    assert row["owner"] == ""
    assert row["found_by_owner_search"] is False
    assert row["held_by"] == "live_workers"
    assert row["on_screen_destroyed"] == "keeps_running"


def test_the_fetch_outlives_a_destroyed_strip_on_the_shipped_side(monkeypatch):
    """The fetch stopped when the strip was destroyed, so nothing outlives it.

    This is the shape the surface records as data. A search for threads
    under the strip is what the suite teardown makes, and it finds none.
    """
    from PySide6.QtCore import QThread
    from shiboken6 import Shiboken

    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    held = threading.Event()
    monkeypatch.setattr(shipped, "fetch_all", lambda **_named: (held.wait(5.0), [])[1])
    strip = shipped.CryptoNewsTicker()
    strip.start()
    thread = strip._worker_thread
    assert [one for one in strip.findChildren(QThread) if one.isRunning()] == []
    strip.hide()
    strip.setParent(None)
    strip.deleteLater()
    found.processEvents()
    assert thread.isRunning() is True, "the fetch stopped with the strip"
    assert len(shipped._LIVE_WORKERS) == 1
    assert Shiboken.isValid(strip) is True, "the strip was destroyed under the fetch"
    held.set()
    assert thread.wait(shipped._STOP_WAIT_MS) is True
    found.processEvents()
    assert len(shipped._LIVE_WORKERS) == 0


def test_the_shared_stand_in_starts_no_fetch_thread_where_the_real_one_does(
    monkeypatch,
):
    """The stand-in opens a fetch, or the counter cannot see a real one."""
    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    held = threading.Event()
    monkeypatch.setattr(shipped, "fetch_all", lambda **_named: (held.wait(5.0), [])[1])
    real = hold(shipped.CryptoNewsTicker())
    real.start()
    assert fetch_threads_running() == 1, "the counter cannot see a real fetch thread"
    held.set()
    assert real._worker_thread.wait(shipped._STOP_WAIT_MS) is True
    assert settle(real, found) is True
    real.stop()
    assert fetch_threads_running() == 0

    stand_in = install_quiet_ticker(monkeypatch)
    quiet = hold(stand_in())
    quiet.start()
    assert fetch_threads_running() == 0, "the stand-in started a fetch thread"
    assert shipped.CryptoNewsTicker is stand_in


def test_asking_a_stopped_fetch_to_stop_again_does_nothing_on_both_sides():
    """A second stop waited again and wrote the abandon line twice."""
    thread = StubbornThread()
    worker = surface.FetchWorkerModel()
    worker.thread = thread
    register = {thread: worker}
    model = surface.CryptoNewsTickerModel(live_workers=register)
    model.worker_thread = thread
    model.worker = worker
    thread.start()
    model.stop_worker()
    assert surface.WORKER_ABANDONED in [call[0] for call in model.calls]
    assert thread.waits == [surface.STOP_WAIT_MS]
    model.stop_worker()
    assert thread.waits == [surface.STOP_WAIT_MS], "a second stop waited again"
    assert [call[0] for call in model.calls].count(surface.WORKER_ABANDONED) == 1
    assert surface.WORKER_ASKED_TWICE in [call[0] for call in model.calls]
    assert thread.deleted is False, "an abandoned thread was destroyed"


def test_a_thread_that_will_not_stop_is_kept_rather_than_destroyed():
    """A running thread was destroyed, which ends the whole program."""
    stubborn = StubbornThread()
    stubborn.start()
    kept = {stubborn: surface.FetchWorkerModel()}
    surface.retire_worker(stubborn, kept)
    assert stubborn.deleted is False
    assert kept, "a running thread was dropped from the register"
    assert stubborn.waits == [surface.RETIRE_WAIT_MS]
    stopping = surface.FetchThreadModel()
    stopping.start()
    register = {stopping: surface.FetchWorkerModel()}
    surface.retire_worker(stopping, register)
    assert stopping.deleted is True
    assert register == {}


def test_every_live_worker_is_stopped_before_the_program_ends():
    """A running fetch was left behind when the program ended."""
    first = surface.FetchThreadModel()
    second = surface.FetchThreadModel()
    first.start()
    second.start()
    workers = {first: surface.FetchWorkerModel(), second: surface.FetchWorkerModel()}
    register = dict(workers)
    quiet = lines_from(surface.LOGGER_NAME, lambda: surface.release_workers(register))
    assert register == {}
    assert first.deleted is True and second.deleted is True
    assert first.interrupted is True and second.interrupted is True
    assert all(worker.is_stopping() for worker in workers.values())
    assert first.waits == [surface.STOP_WAIT_MS]
    assert quiet == [], quiet
    stubborn = StubbornThread()
    stubborn.start()
    said = lines_from(
        surface.LOGGER_NAME,
        lambda: surface.release_workers({stubborn: surface.FetchWorkerModel()}),
    )
    assert said == [["ERROR", surface.AT_EXIT_LOG]], said


def test_a_stopped_fetch_reports_nothing_back():
    """A fetch that was stopped still handed its answer to a strip."""
    thread = surface.FetchThreadModel()
    worker = surface.FetchWorkerModel(lambda: ["a story"])
    worker.thread = thread
    told: list = []
    worker.headlines_ready.append(told.append)
    worker.request_stop()
    worker.run()
    assert told == [], "a stopped fetch reported back"
    quiet = surface.FetchWorkerModel(lambda: ["a story"])
    quiet.thread = surface.FetchThreadModel()
    heard: list = []
    quiet.headlines_ready.append(heard.append)
    quiet.run()
    assert heard == [["a story"]]


def test_a_fetch_that_raises_reports_a_refusal_rather_than_ending_the_thread():
    """A fetch that raised took its thread down with it."""
    thread = surface.FetchThreadModel()
    worker = surface.FetchWorkerModel(lambda: 1 / 0)
    worker.thread = thread
    said: list = []
    worker.failed.append(said.append)
    thread.start()
    worker.run()
    assert len(said) == 1, said
    assert said[0].startswith("ZeroDivisionError"), said
    assert thread.quits == 1, "the thread was left running"
    stopped = surface.FetchWorkerModel(lambda: 1 / 0)
    stopped.thread = surface.FetchThreadModel()
    quiet: list = []
    stopped.failed.append(quiet.append)
    stopped.request_stop()
    stopped.run()
    assert quiet == []


def test_a_detached_report_reaches_nothing():
    """A late answer landed on a strip that was going away."""
    worker = surface.FetchWorkerModel(lambda: ["a story"])
    worker.thread = surface.FetchThreadModel()
    told: list = []
    worker.headlines_ready.append(told.append)
    worker.disconnect()
    worker.run()
    assert told == []
    assert worker.headlines_ready == [] and worker.failed == []


# Counting what the shipped file wires, waits on, and builds


def test_the_strip_wires_seven_signals_and_the_surface_names_seven_actions(monkeypatch):
    """A wiring appeared on one side and not the other."""
    app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch([]))
    with connections_watched() as made:
        strip = hold(shipped.CryptoNewsTicker())
        strip.start()
    strip.stop()
    assert len(made) == len(surface.ACTIONS) == 7, made
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.CryptoNewsTickerModel, name)), name


def test_the_connection_counter_can_see_a_wiring():
    """POSITIVE CONTROL for ``connections_watched``: an empty block records
    nothing and two ``timeout`` wirings record two."""
    from PySide6.QtCore import QTimer

    app()
    timer = hold(QTimer())
    with connections_watched() as quiet:
        pass
    assert quiet == []
    with connections_watched() as made:
        timer.timeout.connect(lambda: None)
        timer.timeout.connect(lambda: None)
    assert len(made) == 2, made


def test_a_finished_fetch_thread_is_torn_down_and_retired(monkeypatch):
    """Both ``finished()`` receivers run: one clears ``_worker_thread`` and
    the other drops the thread from ``_LIVE_WORKERS``."""
    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch([]))
    strip = hold(shipped.CryptoNewsTicker())
    strip.start()
    thread = strip._worker_thread
    assert thread is not None
    assert thread in shipped._LIVE_WORKERS, sorted(map(str, shipped._LIVE_WORKERS))
    thread.wait(shipped._STOP_WAIT_MS)
    assert settle(strip, found), "the fetch never reported back"
    assert strip._worker_thread is None, "the teardown receiver never ran"
    assert thread not in shipped._LIVE_WORKERS, "the retire receiver never ran"


def test_the_strip_starts_two_timers_and_the_surface_names_two_waits(monkeypatch):
    """A wait appeared on one side and not the other."""
    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch([]))
    with timers_watched() as seen:
        strip = hold(shipped.CryptoNewsTicker())
        strip.start()
        if strip._worker_thread is not None:
            strip._worker_thread.wait(shipped._STOP_WAIT_MS)
        settle(strip, found)
        strip.stop()
    started = [name for name, _args in seen if name != "QTimer()"]
    with timers_watched() as quiet:
        model = surface.CryptoNewsTickerModel(clock=frozen_clock())
        model.start()
        model.run_worker()
        model.stop()
    assert started == ["QTimer.start", "QTimer.start"], seen
    assert quiet == [], quiet
    assert surface.TIMERS == {
        "cycle": surface.CYCLE_INTERVAL_MS,
        "refresh": surface.REFRESH_INTERVAL_MS,
    }
    assert len(surface.TIMERS) == len(started) == surface.TIMER_COUNT
    assert surface.TIMER_DELAYS_MS == (
        surface.CYCLE_INTERVAL_MS,
        surface.REFRESH_INTERVAL_MS,
    )


def test_the_timer_counter_can_see_a_wait():
    """POSITIVE CONTROL for ``timers_watched``: one ``QTimer.start`` inside
    the block is recorded."""
    from PySide6.QtCore import QTimer

    app()
    timer = hold(QTimer())
    with timers_watched() as seen:
        timer.start(250)
    assert ("QTimer.start", (250,)) in seen, seen


def test_the_strip_starts_one_thread_and_the_surface_names_one_worker(monkeypatch):
    """A worker appeared on one side and not the other."""
    from PySide6.QtCore import QThread

    found = app()
    started: list = []
    first_start = QThread.start

    def watch_start(self, *found_args, **found_named):
        started.append(type(self).__name__)
        return first_start(self, *found_args, **found_named)

    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch([]))
    QThread.start = watch_start
    try:
        strip = hold(shipped.CryptoNewsTicker())
        strip.start()
        if strip._worker_thread is not None:
            strip._worker_thread.wait(shipped._STOP_WAIT_MS)
        settle(strip, found)
        strip.stop()
        old_started = list(started)
        started.clear()
        model = surface.CryptoNewsTickerModel(clock=frozen_clock())
        model.start()
        model.run_worker()
        model.stop()
        new_started = list(started)
    finally:
        QThread.start = first_start
    assert len(old_started) == surface.THREAD_COUNT == 1, old_started
    assert new_started == []
    assert surface.THREAD_COUNT == len(surface.WORKER_LIFECYCLE) == 1
    assert model.fetches_started == 1


def test_the_strip_declares_two_signals_and_the_surface_names_two_reports():
    """The two reports the worker sends, read off the built worker."""
    from PySide6.QtCore import QMetaMethod

    app()
    worker = shipped._FetchWorker()
    meta = worker.metaObject()
    declared = sorted(
        bytes(meta.method(index).methodSignature()).decode("utf-8")
        for index in range(meta.methodOffset(), meta.methodCount())
        if meta.method(index).methodType() == QMetaMethod.MethodType.Signal
    )
    assert declared == ["failed(QString)", "headlinesReady(QVariantList)"], declared

    model = surface.FetchWorkerModel()
    assert model.headlines_ready == [] and model.failed == []
    assert callable(model.say_ready) and callable(model.say_failed)


def test_the_strip_subscribes_to_no_bus_topic(monkeypatch):
    """A bus wiring appeared on one side and not the other."""
    app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch([]))
    with bus_subscriptions_watched() as taken:
        strip = hold(shipped.CryptoNewsTicker())
        strip.start()
        strip.stop()
        model = surface.CryptoNewsTickerModel(clock=frozen_clock())
        model.start()
        model.run_worker()
        model.stop()
    assert taken == [], taken
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == len(taken)


def test_the_bus_counter_can_see_a_subscription():
    """POSITIVE CONTROL for ``bus_subscriptions_watched``: one ``subscribe``
    inside the block is recorded."""
    from src.core.event_bus import EventBus

    bus = EventBus()
    with bus_subscriptions_watched() as taken:
        bus.subscribe("probe.topic", lambda _event: None)
    assert taken == ["probe.topic"], taken


def test_the_screen_elements_the_strip_builds_are_counted():
    """The strip paints one label inside one layout; the surface paints none."""
    from PySide6.QtWidgets import QLabel, QLayout, QWidget

    app()
    strip = hold(shipped.CryptoNewsTicker())
    assert isinstance(strip, QWidget)
    labels = strip.findChildren(QLabel)
    assert len(labels) == 1, [one.text() for one in labels]
    assert strip.findChildren(QLayout) == [strip.layout()]
    assert not any(
        isinstance(value, type) and issubclass(value, QWidget)
        for value in vars(surface).values()
    )


def test_the_strip_builds_one_layout_and_one_pointer_shape():
    """The margins and the pointer shape the built strip really carries."""
    from PySide6.QtWidgets import QLabel

    app()
    strip = hold(shipped.CryptoNewsTicker())
    margins = strip.layout().contentsMargins()
    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == surface.LAYOUT_MARGINS
    label = strip.findChildren(QLabel)[0]
    assert label.cursor().shape().name == surface.LABEL_CURSOR


# Every class and every method has a counterpart


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A report is callable and is not a method, so it is excluded by name.
    A read-only value is not callable at all, so asking ``callable``
    alone misses it.
    """
    import inspect

    from PySide6.QtCore import Signal

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if inspect.isfunction(value) or isinstance(
            value, (property, classmethod, staticmethod)
        ):
            found.add(name)
    return found


def test_the_member_counter_excludes_a_report_and_finds_both_quiet_shapes():
    """The counter counts a report, or misses a factory or a read-only value."""
    from PySide6.QtCore import Signal

    from src.gui import indicator_panel, launcher

    app()
    panel = indicator_panel.IndicatorVotingPanel
    assert callable(Signal())
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert isinstance(vars(panel)["_reading_fingerprint"], staticmethod)
    assert "_reading_fingerprint" in members(panel)
    assert isinstance(vars(panel)["lock_timeframe"], property)
    assert not callable(vars(panel)["lock_timeframe"])
    assert "lock_timeframe" in members(panel)
    assert isinstance(vars(panel)["selected_bot_id"], property)
    assert not callable(vars(panel)["selected_bot_id"])
    assert "selected_bot_id" in members(panel)
    assert "headlinesReady" not in members(shipped._FetchWorker)
    assert isinstance(vars(shipped._FetchWorker)["headlinesReady"], Signal)


CLASS_MAP = {
    "NewsSource": "NewsSource",
    "NewsHeadline": "NewsHeadline",
    "_FetchWorker": "FetchWorkerModel",
    "CryptoNewsTicker": "CryptoNewsTickerModel",
}

METHOD_MAP = {
    "NewsSource.__init__": "NewsSource.__init__",
    "NewsHeadline.__init__": "NewsHeadline.__init__",
    "NewsHeadline.display_text": "NewsHeadline.display_text",
    "_FetchWorker.__init__": "FetchWorkerModel.__init__",
    "_FetchWorker.request_stop": "FetchWorkerModel.request_stop",
    "_FetchWorker.is_stopping": "FetchWorkerModel.is_stopping",
    "_FetchWorker.run": "FetchWorkerModel.run",
    "CryptoNewsTicker.__init__": "CryptoNewsTickerModel.__init__",
    "CryptoNewsTicker.start": "CryptoNewsTickerModel.start",
    "CryptoNewsTicker.stop": "CryptoNewsTickerModel.stop",
    "CryptoNewsTicker.force_refresh": "CryptoNewsTickerModel.force_refresh",
    "CryptoNewsTicker.current_headlines": "CryptoNewsTickerModel.current_headlines",
    "CryptoNewsTicker._on_headlines": "CryptoNewsTickerModel.on_headlines",
    "CryptoNewsTicker._on_fetch_failed": "CryptoNewsTickerModel.on_fetch_failed",
    "CryptoNewsTicker._advance": "CryptoNewsTickerModel.advance",
    "CryptoNewsTicker._render_current": "CryptoNewsTickerModel.render_current",
    "CryptoNewsTicker._teardown_worker": "CryptoNewsTickerModel.teardown_worker",
    "CryptoNewsTicker._stop_worker": "CryptoNewsTickerModel.stop_worker",
    "CryptoNewsTicker.eventFilter": "CryptoNewsTickerModel.handle_event",
}

HELPER_MAP = {
    "_localname": "localname",
    "_child_text": "child_text",
    "_parse_ts": "parse_ts",
    "parse_rss": "parse_rss",
    "_never_stop": "never_stop",
    "_read_bounded": "read_bounded",
    "fetch_one": "fetch_one",
    "fetch_all": "fetch_all",
    "_retire_worker_thread": "retire_worker",
    "_release_worker_threads_at_exit": "release_workers",
    "worker_thread": "FetchThreadModel",
    "pool_workers": "pool_size",
    "clock_reading": "zero_clock",
    "bridge_handler": "view_model",
    "shared_screen": "pane_model",
    "model_from_stories": "build_model",
    "whole_state": "build_view_model",
    "one_feed": "source_view",
    "one_story": "headline_view",
    "story_from_the_renderer": "headline_from",
    "worker_lifecycle": "lifecycle_view",
    "thread_run": "FetchWorkerModel.run",
}

TICKER_MODEL_MEMBERS = {
    "__init__",
    "start",
    "stop",
    "force_refresh",
    "run_worker",
    "current_headlines",
    "on_headlines",
    "on_fetch_failed",
    "advance",
    "render_current",
    "teardown_worker",
    "retire_worker",
    "stop_worker",
    "handle_event",
}

FETCH_WORKER_MEMBERS = {
    "__init__",
    "request_stop",
    "is_stopping",
    "disconnect",
    "run",
    "say_ready",
    "say_failed",
}

FETCH_THREAD_MEMBERS = {
    "__init__",
    "start",
    "is_running",
    "request_interruption",
    "quit",
    "wait",
    "delete_later",
    "emit_finished",
}


def resolve(dotted):
    """The member a dotted name in a map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_classes():
    """Every class the shipped module declares, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    app()
    assert shipped_classes() == set(CLASS_MAP), sorted(
        shipped_classes() ^ set(CLASS_MAP)
    )
    assert len(CLASS_MAP) == 4
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 19
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 22
    assert members(surface.CryptoNewsTickerModel) == TICKER_MODEL_MEMBERS, sorted(
        members(surface.CryptoNewsTickerModel) ^ TICKER_MODEL_MEMBERS
    )
    assert len(TICKER_MODEL_MEMBERS) == 14
    assert members(surface.FetchWorkerModel) == FETCH_WORKER_MEMBERS, sorted(
        members(surface.FetchWorkerModel) ^ FETCH_WORKER_MEMBERS
    )
    assert len(FETCH_WORKER_MEMBERS) == 7
    assert members(surface.FetchThreadModel) == FETCH_THREAD_MEMBERS, sorted(
        members(surface.FetchThreadModel) ^ FETCH_THREAD_MEMBERS
    )
    assert len(FETCH_THREAD_MEMBERS) == 8


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "force_refresh" in members(shipped.CryptoNewsTicker)
    assert "_advance" in members(shipped.CryptoNewsTicker)
    assert "CryptoNewsTicker" not in TICKER_MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("CryptoNewsTickerModel.no_such_member")
    assert TICKER_MODEL_MEMBERS - {"advance"} != TICKER_MODEL_MEMBERS
    assert members(surface.CryptoNewsTickerModel) - {"stop"} != TICKER_MODEL_MEMBERS
    assert FETCH_WORKER_MEMBERS - {"run"} != FETCH_WORKER_MEMBERS
    assert FETCH_THREAD_MEMBERS - {"wait"} != FETCH_THREAD_MEMBERS
    assert set(METHOD_MAP) - {"CryptoNewsTicker.start"} != set(METHOD_MAP)
    assert shipped_classes() - {"CryptoNewsTicker"} != shipped_classes()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments its callers pass it."""
    import inspect

    app()
    assert list(inspect.signature(shipped.parse_rss).parameters) == [
        "xml_bytes",
        "source",
        "limit",
    ]
    assert list(inspect.signature(surface.parse_rss).parameters) == [
        "xml_bytes",
        "source",
        "limit",
    ]
    assert list(inspect.signature(shipped.fetch_one).parameters) == [
        "source",
        "timeout",
        "should_stop",
        "deadline",
    ]
    assert list(inspect.signature(surface.fetch_one).parameters) == [
        "source",
        "request_factory",
        "opener",
        "timeout",
        "should_stop",
        "deadline",
        "clock",
    ]
    assert list(inspect.signature(shipped.fetch_all).parameters) == [
        "sources",
        "per_source_limit",
        "should_stop",
        "budget_s",
    ]
    assert list(inspect.signature(surface.fetch_all).parameters) == [
        "request_factory",
        "opener",
        "sources",
        "per_source_limit",
        "should_stop",
        "budget_s",
        "clock",
    ]
    assert list(inspect.signature(surface.view_model).parameters) == ["params"]
    assert list(
        inspect.signature(shipped.CryptoNewsTicker.current_headlines).parameters
    ) == list(
        inspect.signature(surface.CryptoNewsTickerModel.current_headlines).parameters
    )


def test_the_exchange_tab_builds_the_strip():
    """The exchange tab stopped putting the strip in its header."""
    from src.gui.widgets.exchange_tab import ExchangeTab

    app()
    tab = hold(ExchangeTab("coinbase", "Coinbase"))
    try:
        assert isinstance(tab._news_ticker, shipped.CryptoNewsTicker)
        assert tab._news_ticker.parent() is not None, "the strip is not in the header"
    finally:
        tab._news_ticker.stop()


def test_the_bridge_reaches_the_surface():
    """The bridge registry stopped carrying the strip's method."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert registry[surface.METHOD] is surface.view_model
    from_surface = sorted(
        method
        for method, handler in registry.items()
        if getattr(handler, "__module__", "") == surface.__name__
    )
    assert from_surface == [surface.METHOD], from_surface


# The surface holds its own values


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file(monkeypatch):
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    before = shipped.CYCLE_INTERVAL_MS
    kept_words = surface.INITIAL_TEXT
    shipped.CYCLE_INTERVAL_MS = 999
    try:
        monkeypatch.setattr(shipped, "time", FrozenTime())
        moved = read_old_strip(hold(shipped.CryptoNewsTicker()))
        moved["label_text"] = "Renamed"
        kept = read_new_strip(
            surface.build_view_model(surface.CryptoNewsTickerModel()),
            surface.CryptoNewsTickerModel(),
        )
        assert moved["cycle_interval_ms"] == 999
        assert kept["cycle_interval_ms"] == surface.CYCLE_INTERVAL_MS == 15_000
        assert kept["label_text"] == kept_words
        differences = [
            key
            for key in sorted(set(moved) & set(kept))
            if readable(moved[key]) != readable(kept[key])
        ]
        assert differences == ["cycle_interval_ms", "label_text"], differences
    finally:
        shipped.CYCLE_INTERVAL_MS = before
    both_strips_agree(drive("one_story", monkeypatch), "after the value was put back")


def test_the_shipped_file_is_not_named_by_the_surface():
    """Loading the surface pulled the strip or a widget module in behind it."""
    pulled = module_pulls("src.gui.main_tabs.crypto_news_ticker_surface")
    assert "src.gui.main_tabs.crypto_news_ticker_surface" in pulled, pulled
    assert "src.gui.crypto_news_ticker" not in pulled, pulled
    assert [name for name in pulled if ".widgets." in name] == [], pulled


def test_the_module_pull_reader_reports_the_strip():
    """POSITIVE CONTROL for ``module_pulls``: the strip's own import pulls it."""
    pulled = module_pulls("src.gui.crypto_news_ticker")
    assert "src.gui.crypto_news_ticker" in pulled, pulled


# The strip paints, and the two sides paint the same pixels


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def old_strip_for_picture(name, monkeypatch):
    """One shipped strip driven through one case, ready to render."""
    opens: list = []
    strip = old_strip(monkeypatch, opens)
    for step in old_steps(strip, STRIP_STEPS[name], opens):
        guarded(step)
    return strip


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    opens: list = []
    model = new_strip(opens)
    for step in new_steps(model, STRIP_STEPS[name], opens):
        guarded(step)
    return sealed(surface.build_view_model(model))


def strip_painted_by_the_model(payload):
    """One strip built only from the surface's view model."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

    payload = unaltered(payload)
    app()
    screen = hold(QWidget())
    screen.setAccessibleName(payload["accessible_name"])
    layout = QHBoxLayout(screen)
    left, top, right, bottom = payload["layout_margins"]
    layout.setContentsMargins(left, top, right, bottom)
    layout.setSpacing(payload["layout_spacing"])
    label = QLabel(payload["label_text"])
    label.setToolTip(payload["label_tooltip"])
    label.setCursor(QCursor(getattr(Qt, payload["label_cursor"])))
    label.setStyleSheet(payload["label_style"])
    label.setTextInteractionFlags(
        getattr(Qt.TextInteractionFlag, payload["label_text_flags"])
    )
    layout.addWidget(label, stretch=payload["label_stretch"])
    return screen


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_render_the_same_pixels(name, monkeypatch):
    """The surface paints a strip the shipped strip does not."""
    app()
    old_side = render_offscreen(old_strip_for_picture(name, monkeypatch), PIXEL_SIZE)
    new_side = render_offscreen(
        strip_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases(monkeypatch):
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            old_strip_for_picture("one_story", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            strip_painted_by_the_model(model_payload("fresh")), PIXEL_SIZE
        ),
        note="one story against none",
    )
    assert_pictures_differ(
        old_side=render_offscreen(
            old_strip_for_picture("fresh", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            strip_painted_by_the_model(model_payload("refusal")), PIXEL_SIZE
        ),
        note="the first words against the refusal words",
    )
    assert_pictures_match(
        old_side=render_offscreen(
            old_strip_for_picture("one_story", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            strip_painted_by_the_model(model_payload("one_story")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("one_story")
    payload["label_text"] = "moved"
    with pytest.raises(AssertionError):
        strip_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        strip_painted_by_the_model({"label_text": ""})
    assert strip_painted_by_the_model(model_payload("one_story")) is not None


def test_the_strip_declares_no_skin_of_its_own(monkeypatch):
    """A colour the surface ships is one the strip never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    assert old_strip(monkeypatch, []).styleSheet() == ""
    assert "QWidget" not in surface.LABEL_STYLE
    assert "background-color" not in surface.LABEL_STYLE
    skinned = strip_painted_by_the_model(model_payload("one_story"))
    skinned.setStyleSheet("QWidget { background-color: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(
            old_strip_for_picture("one_story", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a rule the strip does not set",
    )
    assert_pictures_match(
        old_side=render_widget(
            old_strip_for_picture("one_story", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_widget(
            strip_painted_by_the_model(model_payload("one_story")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


def test_the_two_waits_are_compared_as_asked_for(monkeypatch):
    """The wait the strip was given differs between the two sides."""
    app()
    strip = old_strip(monkeypatch, [])
    assert strip._cycle_timer.interval() == surface.CYCLE_INTERVAL_MS == 15_000
    assert strip._refresh_timer.interval() == surface.REFRESH_INTERVAL_MS == 3_600_000
    assert surface.TIMER_DELAYS_MS == (15_000, 3_600_000)


def test_the_platform_keeps_the_wait_the_timer_was_given():
    """The timer refused the wait it was given, so the ask is not the wait."""
    from PySide6.QtCore import QTimer

    app()
    timer = QTimer()
    timer.setInterval(surface.CYCLE_INTERVAL_MS)
    assert timer.interval() == surface.CYCLE_INTERVAL_MS
    timer.setInterval(-5)
    floor = timer.interval()
    assert floor >= 0, floor
    assert surface.CYCLE_INTERVAL_MS > floor


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font database."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding fonts measured every glyph the same width."""
    app()
    assert app_font_advance_px(WIDE_LABEL) > app_font_advance_px(NARROW_LABEL)


# What a picture cannot see


def test_the_strip_tooltip_is_compared_as_a_string(monkeypatch):
    """The words the strip explains itself with reached no pixel."""
    app()
    assert old_strip(monkeypatch, [])._label.toolTip() == surface.LABEL_TOOLTIP
    assert len(surface.LABEL_TOOLTIP) > 100
    assert "Refreshes hourly." in surface.LABEL_TOOLTIP


def test_the_story_tooltip_is_compared_as_a_string(monkeypatch):
    """The address a story would open reached no pixel."""
    run = drive("one_story", monkeypatch)
    assert run["old"]["label_tooltip"] == run["new"]["label_tooltip"]
    assert "https://story.invalid/1" in run["old"]["label_tooltip"]
    assert "\n" in run["old"]["label_tooltip"]
    assert run["old"]["label_tooltip"] != surface.LABEL_TOOLTIP


def test_the_pointer_shape_is_compared_as_a_value(monkeypatch):
    """The strip stopped showing a hand, so no one knows it can be clicked."""
    app()
    assert old_strip(monkeypatch, [])._label.cursor().shape().name == (
        surface.LABEL_CURSOR
    )
    assert surface.LABEL_CURSOR == "PointingHandCursor"


def test_the_text_can_be_selected_on_both_sides(monkeypatch):
    """The words on the strip stopped being selectable."""
    app()
    flags = old_strip(monkeypatch, [])._label.textInteractionFlags()
    assert flags.name == surface.LABEL_TEXT_FLAGS
    assert surface.LABEL_TEXT_FLAGS == "TextSelectableByMouse"


def test_the_strip_colour_is_compared_as_exact_text():
    """A swapped colour channel reads the same, so a wrong colour passes.

    The colour is compared as text in one spelling. Its three channels
    differ, so a channel swap changes the text.
    """
    words = "#cfe6ff"
    assert words in surface.LABEL_STYLE
    assert len({words[1:3], words[3:5], words[5:7]}) == 3, words
    assert words == words.lower()
    assert "font-size: 11px" in surface.LABEL_STYLE


def test_the_strip_layout_is_compared_as_the_ask(monkeypatch):
    """The platform decides the spacing, so the ask is what is compared."""
    run = drive("one_story", monkeypatch)
    assert run["old"]["margins"] == run["new"]["margins"] == [6, 2, 6, 2]
    assert run["old"]["spacing"] == run["new"]["spacing"] == 6
    assert run["old"]["stretch"] == run["new"]["stretch"] == 1


def test_the_paused_flag_is_compared_as_a_value(monkeypatch):
    """The strip kept advancing while the pointer rested on it."""
    held = drive("advance_while_held", monkeypatch)
    assert held["old"]["paused"] is True
    assert held["old"]["index"] == held["new"]["index"] == 0
    released = drive("advance_after_release", monkeypatch)
    assert released["old"]["paused"] is False
    assert released["old"]["index"] == released["new"]["index"] == 1


def test_what_a_click_opens_is_compared_as_a_value(monkeypatch):
    """The strip opened the wrong story, or opened none at all."""
    run = drive("click_after_advance", monkeypatch)
    both_strips_agree(run, "click_after_advance")
    assert run["old_opens"] == [["https://story.invalid/2", 2]], run["old_opens"]
    quiet = drive("click_with_no_story", monkeypatch)
    assert quiet["old_opens"] == []


def test_a_browser_that_refuses_is_compared_as_a_value(monkeypatch):
    """A browser that refused took the whole strip down with it."""
    run = drive("click_refused", monkeypatch)
    both_strips_agree(run, "click_refused")
    assert run["old_opens"] == []
    assert run["old_outcome"][-1] == {"error": ""}
    assert surface.BROWSER_NEW_TAB == 2


def test_the_recorded_steps_are_compared_as_values(monkeypatch):
    """The recorded steps are a list nothing reads, so a lost step is unseen."""
    opens: list = []
    model = new_strip(opens)
    for step in new_steps(model, STRIP_STEPS["advance_once"], opens):
        step()
    names = [call[0] for call in model.calls]
    assert names.count(surface.HEADLINES_TAKEN) == 1
    assert names.count(surface.ADVANCED) == 1
    assert names.count(surface.RENDERED) == 2
    assert surface.TICKER_BUILT in names
    payload = surface.build_view_model(model)
    assert payload["calls"] == [list(call) for call in model.calls]


def test_the_worker_lifecycle_is_compared_as_values(monkeypatch):
    """The worker lifecycle is a value nothing reads, so a wrong one is unseen."""
    model = surface.CryptoNewsTickerModel(clock=frozen_clock())
    payload = surface.build_view_model(model)
    row = payload["worker_lifecycle"][surface.WORKER_NAME]
    assert row["started_by"] == ["start", "force_refresh", "refresh_timeout"]
    assert row["stopped_by"] == ["stop", "run_end", "release_workers"]
    assert row["found_by_owner_search"] is False
    assert row["stop_wait_ms"] == shipped._STOP_WAIT_MS == 2000
    assert row["retire_wait_ms"] == shipped._RETIRE_WAIT_MS == 1000
    assert surface.lifecycle_view() == payload["worker_lifecycle"]


BLIND_TO_THE_PICTURE = {
    "strip tooltip": "test_the_strip_tooltip_is_compared_as_a_string",
    "story tooltip": "test_the_story_tooltip_is_compared_as_a_string",
    "pointer shape": "test_the_pointer_shape_is_compared_as_a_value",
    "selectable text": "test_the_text_can_be_selected_on_both_sides",
    "strip colour": "test_the_strip_colour_is_compared_as_exact_text",
    "layout ask": "test_the_strip_layout_is_compared_as_the_ask",
    "paused flag": "test_the_paused_flag_is_compared_as_a_value",
    "what a click opens": "test_what_a_click_opens_is_compared_as_a_value",
    "a refusing browser": "test_a_browser_that_refuses_is_compared_as_a_value",
    "recorded steps": "test_the_recorded_steps_are_compared_as_values",
    "worker lifecycle": "test_the_worker_lifecycle_is_compared_as_values",
    "two waits": "test_the_two_waits_are_compared_as_asked_for",
    "worker owner": "test_the_fetch_thread_has_no_owner_on_either_side",
    "one fetch at a time": "test_a_second_fetch_beside_a_first_is_refused_on_both_sides",
    "story order": "test_the_merged_list_puts_the_newest_story_first",
    "story limit": "test_a_story_limit_takes_the_same_count_on_both_sides",
    "title cap": "test_a_title_longer_than_the_cap_is_cut_at_the_same_place",
    "size cap": "test_a_body_over_the_cap_is_dropped_and_one_at_the_cap_is_read",
    "the two headers": "test_the_two_headers_the_strip_adds_are_the_same_on_both_sides",
    "read pieces": "test_the_body_is_read_in_pieces_of_one_size_on_both_sides",
    "published date": "test_a_published_date_reads_the_same_on_both_sides",
    "refusal type": "test_the_file_drives_more_than_one_kind_of_refusal",
    "refusal wording": "test_the_refusal_reader_reports_two_different_wordings",
    "log lines": "test_the_strip_writes_the_same_lines_on_both_sides",
    "one layout, one pointer": "test_the_strip_builds_one_layout_and_one_pointer_shape",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 25
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# The strip writes under the logger it names


def lines_from(logger_name, run, level=logging.DEBUG):
    """Every line one named logger emits while `run` is running.

    The handler is attached to the named logger, never through a capture
    fixture: this project's loggers do not pass their records up, so a
    fixture reading the root logger would see nothing. It is detached
    even when `run` refuses part way, and each record is flushed as it
    arrives.
    """
    found: list = []

    class Recorder(logging.Handler):
        def emit(self, record):
            found.append([record.levelname, record.msg])
            self.flush()

    handler = Recorder()
    target = logging.getLogger(logger_name)
    target.addHandler(handler)
    was = target.level
    target.setLevel(level)
    try:
        guarded(run)
    finally:
        target.removeHandler(handler)
        target.setLevel(was)
    return found


LOG_CASES = {
    "refused_feed": "entities",
    "malformed_feed": "malformed",
}


@pytest.mark.parametrize("name", sorted(LOG_CASES))
def test_the_strip_writes_the_same_lines_on_both_sides(name):
    """The two sides said different things about one feed body."""
    body = FEED_BODIES[LOG_CASES[name]]
    old_source = shipped.NewsSource("feed", "Feed", FEED_URL)
    new_source = surface.NewsSource("feed", "Feed", FEED_URL)
    old_said = lines_from(
        surface.LOGGER_NAME, lambda: shipped.parse_rss(body, old_source)
    )
    new_said = lines_from(
        surface.LOGGER_NAME, lambda: surface.parse_rss(body, new_source)
    )
    assert old_said == new_said, (old_said, new_said)
    assert len(old_said) == 1, old_said


def test_a_feed_over_the_size_cap_is_announced_the_same_way(monkeypatch):
    """The two sides said different things about an oversized body."""
    bodies = {FEED_URL: b"x" * (surface.MAX_FEED_BYTES + 5)}
    old_factory, old_opener = transport(bodies)
    monkeypatch.setattr(shipped, "SafeRequest", old_factory)
    monkeypatch.setattr(shipped, "safe_urlopen", old_opener)
    monkeypatch.setattr(shipped, "time", FrozenTime())
    old_said = lines_from(
        surface.LOGGER_NAME,
        lambda: shipped.fetch_one(shipped.NewsSource("feed", "Feed", FEED_URL)),
    )
    new_factory, new_opener = transport(bodies)
    new_said = lines_from(
        surface.LOGGER_NAME,
        lambda: surface.fetch_one(
            surface.NewsSource("feed", "Feed", FEED_URL), new_factory, new_opener
        ),
    )
    assert old_said == new_said, (old_said, new_said)
    assert old_said and old_said[0][0] == "WARNING", old_said


def test_the_line_recorder_can_report():
    """The recorder sees nothing whatever the code says, so silence is empty."""
    said = lines_from(
        surface.LOGGER_NAME,
        lambda: logging.getLogger(surface.LOGGER_NAME).warning("a seeded line"),
    )
    assert said == [["WARNING", "a seeded line"]]
    source = surface.NewsSource("feed", "Feed", FEED_URL)
    quiet = lines_from(
        surface.LOGGER_NAME, lambda: surface.parse_rss(FEED_BODIES["happy"], source)
    )
    assert quiet == []
    survived = lines_from(
        surface.LOGGER_NAME,
        lambda: [
            logging.getLogger(surface.LOGGER_NAME).warning("before the refusal"),
            surface.parse_rss(b"<rss/>", None),
        ],
    )
    assert survived == [["WARNING", "before the refusal"]]
    assert logging.getLogger(surface.LOGGER_NAME).handlers == []


def test_the_surface_writes_under_the_logger_it_names():
    """The surface writes under a name no operator log is collected from."""
    assert surface.LOGGER_NAME == "acervator.crypto_news_ticker"
    assert surface.logger.name == surface.LOGGER_NAME
    assert shipped.logger.name == surface.LOGGER_NAME


# Every value reaches the compared snapshot


def freeze(value):
    """One value as a single comparable string."""

    def plain(found):
        if isinstance(found, (tuple, list)):
            return [plain(item) for item in found]
        if isinstance(found, dict):
            return {str(key): plain(item) for key, item in found.items()}
        return found

    return json.dumps(plain(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    import inspect

    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if isinstance(value, (surface.CryptoNewsTickerModel, logging.Logger)):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    for name in STRIP_STEPS:
        opens: list = []
        model = new_strip(opens)
        for step in new_steps(model, STRIP_STEPS[name], opens):
            guarded(step)
        payloads.append(surface.build_view_model(model))
    running = surface.CryptoNewsTickerModel(
        fetcher=instant_fetch(build_stories("two", surface)), clock=frozen_clock()
    )
    running.start()
    payloads.append(surface.build_view_model(running))
    running.run_worker()
    running.stop()
    payloads.append(surface.build_view_model(running))
    skipped = surface.CryptoNewsTickerModel(clock=frozen_clock())
    skipped.force_refresh()
    skipped.force_refresh()
    payloads.append(surface.build_view_model(skipped))
    skipped.run_worker()
    absent = surface.CryptoNewsTickerModel(clock=frozen_clock())
    absent.run_worker()
    absent.stop_worker()
    absent.retire_worker()
    payloads.append(surface.build_view_model(absent))
    stubborn = StubbornThread()
    stubborn.start()
    abandoned = surface.CryptoNewsTickerModel(clock=frozen_clock())
    abandoned.worker_thread = stubborn
    abandoned.worker = surface.FetchWorkerModel()
    abandoned.live_workers[stubborn] = abandoned.worker
    abandoned.stop_worker()
    abandoned.stop_worker()
    payloads.append(surface.build_view_model(abandoned))
    abandoned.live_workers.clear()
    retired = surface.CryptoNewsTickerModel(clock=frozen_clock())
    retired.force_refresh()
    retired.retire_worker()
    payloads.append(surface.build_view_model(retired))
    payloads.append(
        surface.build_view_model(
            surface.build_model(build_stories("three", surface), frozen_clock())
        )
    )
    payloads.append(surface.build_view_model(surface.build_model()))
    refusing = surface.CryptoNewsTickerModel(
        open_url=lambda url, new: 1 / 0, clock=frozen_clock()
    )
    refusing.on_headlines(build_stories("one", surface))
    refusing.handle_event(surface.EVENT_MOUSE_RELEASE)
    payloads.append(surface.build_view_model(refusing))
    return payloads


COVERED_ELSEWHERE = {
    "PANE_MODEL": "test_importing_the_surface_reads_no_file",
    "LOGGER_NAME": "test_the_surface_writes_under_the_logger_it_names",
    "TickerCall": "test_the_recorded_steps_are_compared_as_values",
    "NEWS_SOURCES": "test_the_ten_feed_addresses_are_the_shipped_addresses",
    "PARSE_LIMIT": "test_a_story_limit_takes_the_same_count_on_both_sides",
    "WORKER_LIFECYCLE": "test_the_worker_lifecycle_is_compared_as_values",
    "TICKER_BUILT": "test_the_recorded_steps_are_compared_as_values",
    "FETCH_STARTED": "test_the_recorded_steps_are_compared_as_values",
    "FETCH_SKIPPED": "test_a_second_fetch_beside_a_first_is_refused_on_both_sides",
    "FETCH_RAN": "test_the_recorded_steps_are_compared_as_values",
    "HEADLINES_TAKEN": "test_the_recorded_steps_are_compared_as_values",
    "HEADLINES_EMPTY": "test_the_recorded_steps_are_compared_as_values",
    "FETCH_REFUSED": "test_the_recorded_steps_are_compared_as_values",
    "ADVANCED": "test_the_recorded_steps_are_compared_as_values",
    "ADVANCE_HELD": "test_the_recorded_steps_are_compared_as_values",
    "RENDERED": "test_the_recorded_steps_are_compared_as_values",
    "CYCLE_STARTED": "test_the_recorded_steps_are_compared_as_values",
    "CYCLE_STOPPED": "test_the_recorded_steps_are_compared_as_values",
    "REFRESH_STARTED": "test_the_recorded_steps_are_compared_as_values",
    "REFRESH_STOPPED": "test_the_recorded_steps_are_compared_as_values",
    "WORKER_TORN_DOWN": "test_the_recorded_steps_are_compared_as_values",
    "WORKER_RETIRED": "test_a_thread_that_will_not_stop_is_kept_rather_than_destroyed",
    "WORKER_ABANDONED": (
        "test_asking_a_stopped_fetch_to_stop_again_does_nothing_on_both_sides"
    ),
    "WORKER_ASKED_TWICE": (
        "test_asking_a_stopped_fetch_to_stop_again_does_nothing_on_both_sides"
    ),
    "WORKER_ABSENT": "test_the_recorded_steps_are_compared_as_values",
    "HOVER_PAUSED": "test_the_paused_flag_is_compared_as_a_value",
    "HOVER_RELEASED": "test_the_paused_flag_is_compared_as_a_value",
    "STORY_OPENED": "test_what_a_click_opens_is_compared_as_a_value",
    "STORY_OPEN_FAILED": "test_a_browser_that_refuses_is_compared_as_a_value",
    "EVENT_IGNORED": "test_the_recorded_steps_are_compared_as_values",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped strip."""
    constants = surface_constants()
    assert len(constants) > 60, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "LABEL_TOOLTIP" in missing_from_payload(surface_constants(), thinned)
    assert "FETCH_USER_AGENT" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "label_text": ("model.label_text",),
    "label_tooltip": ("model.label_tooltip",),
    "label_style": ("LABEL_STYLE",),
    "label_cursor": ("LABEL_CURSOR",),
    "label_text_flags": ("LABEL_TEXT_FLAGS",),
    "label_stretch": ("LABEL_STRETCH",),
    "layout_margins": ("LAYOUT_MARGINS",),
    "layout_spacing": ("LAYOUT_SPACING",),
    "initial_text": ("INITIAL_TEXT",),
    "no_feeds_text": ("NO_FEEDS_TEXT",),
    "unavailable_text": ("UNAVAILABLE_TEXT",),
    "position_format": ("POSITION_FORMAT",),
    "headline_tooltip_format": ("HEADLINE_TOOLTIP_FORMAT",),
    "headlines": ("model.headlines",),
    "index": ("model.index",),
    "paused": ("model.paused",),
    "last_refresh_ts": ("model.last_refresh_ts",),
    "no_timestamp": ("NO_TIMESTAMP",),
    "cycle_running": ("model.cycle_running",),
    "refresh_running": ("model.refresh_running",),
    "cycle_interval_ms": ("CYCLE_INTERVAL_MS",),
    "refresh_interval_ms": ("REFRESH_INTERVAL_MS",),
    "stop_wait_ms": ("STOP_WAIT_MS",),
    "retire_wait_ms": ("RETIRE_WAIT_MS",),
    "fetches_started": ("model.fetches_started",),
    "worker_running": ("model.worker_thread",),
    "live_workers": ("model.live_workers",),
    "opened": ("model.opened",),
    "sources": ("NEWS_SOURCES",),
    "source_join": ("SOURCE_JOIN",),
    "title_max_chars": ("TITLE_MAX_CHARS",),
    "default_timeout_s": ("DEFAULT_TIMEOUT_S",),
    "fetch_budget_s": ("FETCH_BUDGET_S",),
    "fetch_poll_s": ("FETCH_POLL_S",),
    "read_chunk_bytes": ("READ_CHUNK_BYTES",),
    "max_feed_bytes": ("MAX_FEED_BYTES",),
    "max_fetch_workers": ("MAX_FETCH_WORKERS",),
    "fetch_user_agent": ("FETCH_USER_AGENT",),
    "fetch_accept": ("FETCH_ACCEPT",),
    "user_agent_header": ("USER_AGENT_HEADER",),
    "accept_header": ("ACCEPT_HEADER",),
    "parse_limit": ("PARSE_LIMIT",),
    "per_source_limit": ("PER_SOURCE_LIMIT",),
    "item_tags": ("ITEM_TAGS",),
    "title_tags": ("TITLE_TAGS",),
    "link_tags": ("LINK_TAGS",),
    "date_tags": ("DATE_TAGS",),
    "link_href": ("LINK_HREF",),
    "namespace_mark": ("NAMESPACE_MARK",),
    "no_text": ("NO_TEXT",),
    "event_enter": ("EVENT_ENTER",),
    "event_leave": ("EVENT_LEAVE",),
    "event_mouse_release": ("EVENT_MOUSE_RELEASE",),
    "browser_new_tab": ("BROWSER_NEW_TAB",),
    "no_sources_refusal": ("NO_SOURCES_REFUSAL",),
    "refused_feed_log": ("REFUSED_FEED_LOG",),
    "malformed_feed_log": ("MALFORMED_FEED_LOG",),
    "oversized_feed_log": ("OVERSIZED_FEED_LOG",),
    "allowlist_log": ("ALLOWLIST_LOG",),
    "fetch_failed_log": ("FETCH_FAILED_LOG",),
    "read_stopped_log": ("READ_STOPPED_LOG",),
    "read_budget_log": ("READ_BUDGET_LOG",),
    "fetch_stopped_log": ("FETCH_STOPPED_LOG",),
    "budget_spent_log": ("BUDGET_SPENT_LOG",),
    "aggregate_log": ("AGGREGATE_LOG",),
    "still_running_log": ("STILL_RUNNING_LOG",),
    "at_exit_log": ("AT_EXIT_LOG",),
    "abandoned_log": ("ABANDONED_LOG",),
    "widget_fetch_failed_log": ("WIDGET_FETCH_FAILED_LOG",),
    "open_failed_log": ("OPEN_FAILED_LOG",),
    "worker_name": ("WORKER_NAME",),
    "worker_lifecycle": ("WORKER_LIFECYCLE",),
    "thread_count": ("THREAD_COUNT",),
    "timer_count": ("TIMER_COUNT",),
    "skin": ("SKIN",),
    "style_sheet": ("STYLE_SHEET",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "actions": ("ACTIONS",),
    "logger_name": ("LOGGER_NAME",),
    "calls": ("model.calls",),
}

FREE_SHAPE_KEYS = ("calls", "headlines", "worker_lifecycle", "sources", "opened")


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
        return found() if callable(found) else found
    return getattr(surface, name)


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources hold."""
    resolved = resolve_source(sources[0], model)
    if key == "worker_running":
        return value is (resolved is not None)
    if key == "live_workers":
        return value == len(resolved)
    if key in FREE_SHAPE_KEYS:
        return len(value) == len(resolved)
    return freeze(value) == freeze(resolved)


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = surface.build_model(build_stories("two", surface), frozen_clock())
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    fresh = surface.build_model(build_stories("two", surface), frozen_clock())
    surface.build_view_model(fresh)
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(fresh, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, fresh), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.build_model(build_stories("one", surface), frozen_clock())
    payload = surface.build_view_model(model)
    assert backed("label_style", payload["label_style"], ("LABEL_STYLE",), model)
    assert not backed("label_style", "color: red;", ("LABEL_STYLE",), model)
    assert not backed("timers", {"cycle": 1}, ("TIMERS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("headlines", [], ("model.headlines",), model)
    assert not backed("index", 7, ("model.index",), model)


def test_the_ten_feed_addresses_are_the_shipped_addresses():
    """A feed address moved on one side and not the other."""
    old = [(one.slug, one.name, one.url) for one in shipped.NEWS_SOURCES]
    new = [(one.slug, one.name, one.url) for one in surface.NEWS_SOURCES]
    assert old == new, (old, new)
    assert len(new) == 10
    assert len({one[0] for one in new}) == 10
    assert all(one[2].startswith("https://") for one in new), new


# What the shipped module keeps between strips


def test_the_shipped_module_keeps_a_worker_register_for_the_whole_process(
    monkeypatch, own_worker_register
):
    """The module keeps no shared value, so no test can disturb another."""
    found = app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    held = threading.Event()
    monkeypatch.setattr(shipped, "fetch_all", lambda **_named: (held.wait(5.0), [])[1])
    assert shipped._LIVE_WORKERS is own_worker_register
    assert len(own_worker_register) == 0
    strip = hold(shipped.CryptoNewsTicker())
    strip.start()
    assert len(own_worker_register) == 1, "the register is not the shared one"
    held.set()
    assert strip._worker_thread.wait(shipped._STOP_WAIT_MS) is True
    assert settle(strip, found) is True
    strip.stop()
    assert len(own_worker_register) == 0


def test_each_side_is_given_its_own_worker_register(own_worker_register):
    """Two sides share one register, so one side counts the other's worker."""
    model = surface.CryptoNewsTickerModel(clock=frozen_clock())
    model.force_refresh()
    assert len(model.live_workers) == 1
    assert len(own_worker_register) == 0, "the surface wrote into the shipped register"
    second = surface.CryptoNewsTickerModel(clock=frozen_clock())
    assert second.live_workers == {}
    assert second.live_workers is not model.live_workers
    model.run_worker()
    assert model.live_workers == {}


def test_the_shipped_module_changes_no_other_value_the_next_strip_reads(monkeypatch):
    """One strip left a changed value behind for the next one."""
    app()
    monkeypatch.setattr(shipped, "time", FrozenTime())
    monkeypatch.setattr(shipped, "fetch_all", instant_fetch([]))
    before = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value) and name != "_LIVE_WORKERS"
    }
    for name in STRIP_STEPS:
        opens: list = []
        strip = old_strip(monkeypatch, opens)
        for step in old_steps(strip, STRIP_STEPS[name], opens):
            guarded(step)
    after = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value) and name != "_LIVE_WORKERS"
    }
    assert after == before


def test_the_surface_keeps_no_value_between_two_strips():
    """One strip left a changed value behind for the next one."""
    first = surface.build_model(build_stories("three", surface), frozen_clock())
    second = surface.CryptoNewsTickerModel()
    assert second.headlines == []
    assert second.calls != first.calls
    assert second.label_text == surface.INITIAL_TEXT
    assert first.headlines is not second.headlines


# The bridge


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    payload = surface.build_view_model(
        surface.build_model(build_stories("three", surface), frozen_clock())
    )
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_news_strip_method():
    """The renderer cannot reach the news strip over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "crypto_news_ticker.state"
    assert registered[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )
    assert answer["ok"] is True
    assert answer["result"]["label_text"] == surface.INITIAL_TEXT


def test_the_bridge_keeps_the_strip_until_a_reset():
    """The strip forgot its stories between two calls, or kept them past a reset."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 5, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    stories = [
        {
            "title": "First",
            "url": "https://story.invalid/1",
            "source": {"slug": "cd", "name": "CoinDesk", "url": FEED_URL},
            "published_ts": 3.0,
        },
        {
            "title": "Second",
            "url": "https://story.invalid/2",
            "source": {"slug": "dc", "name": "Decrypt", "url": FEED_URL},
            "published_ts": 2.0,
        },
    ]
    filled = ask({"headlines": stories, "now": FROZEN_NOW})
    assert len(filled["headlines"]) == 2
    assert filled["label_text"].startswith("[1/2] ")
    assert filled["last_refresh_ts"] == FROZEN_NOW
    assert ask({})["index"] == 0
    assert ask({"advance": 1})["index"] == 1
    assert ask({"reset": True})["headlines"] == []
    assert surface.PANE_MODEL.headlines == []


def test_the_bridge_reports_a_state_it_cannot_read():
    """A broken request answered as if it had worked."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 6,
                "method": surface.METHOD,
                "params": {"reset": True, "advance": "twice"},
            }
        ),
        registered,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"
    desktop_bridge.handle_line(
        json.dumps({"id": 7, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )


def test_the_bridge_drives_every_step_the_strip_takes():
    """A step the renderer sends never reaches the strip."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 8, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    stories = [
        {
            "title": "First",
            "url": "https://story.invalid/1",
            "source": {"slug": "cd", "name": "CoinDesk", "url": FEED_URL},
            "published_ts": 3.0,
        },
        {
            "title": "Second",
            "url": "https://story.invalid/2",
            "source": {"slug": "dc", "name": "Decrypt", "url": FEED_URL},
            "published_ts": 2.0,
        },
    ]
    ask({"reset": True, "now": FROZEN_NOW})
    filled = ask({"headlines": stories})
    assert filled["index"] == 0
    held = ask({"hover": True, "advance": 1})
    assert held["paused"] is True and held["index"] == 0
    moved = ask({"hover": False, "advance": 1})
    assert moved["paused"] is False and moved["index"] == 1
    clicked = ask({"click": True})
    assert clicked["opened"] == ["https://story.invalid/2"]
    started = ask({"start": True})
    assert started["cycle_running"] is True
    assert started["fetches_started"] == 1
    stopped = ask({"stop": True})
    assert stopped["cycle_running"] is False
    ask({"reset": True})


# Without Qt at all

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'crypto_news_ticker.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import crypto_news_ticker_surface as s\n"
    "stories = [s.NewsHeadline('First', 'https://story.invalid/1',\n"
    "               s.NewsSource('cd', 'CoinDesk', 'https://feed.invalid/rss'), 3.0),\n"
    "           s.NewsHeadline('Second', 'https://story.invalid/2',\n"
    "               s.NewsSource('dc', 'Decrypt', 'https://feed.invalid/rss'), 2.0)]\n"
    "model = s.build_model(stories, lambda: 1700000000.5)\n"
    "model.advance()\n"
    "payload = s.build_view_model(model)\n"
    "parsed = s.parse_rss(b'<rss><channel><item><title>T</title>'\n"
    "    b'<link>https://story.invalid/9</link></item></channel></rss>',\n"
    "    s.NewsSource('cd', 'CoinDesk', 'https://feed.invalid/rss'))\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'label_text': payload['label_text'],\n"
    "    'label_tooltip': payload['label_tooltip'],\n"
    "    'label_style': payload['label_style'],\n"
    "    'index': payload['index'],\n"
    "    'stories': len(payload['headlines']),\n"
    "    'sources': len(payload['sources']),\n"
    "    'lifecycle': payload['worker_lifecycle'],\n"
    "    'parsed': [one.display_text() for one in parsed],\n"
    "    'calls': len(payload['calls'])}))\n"
)

NOTHING_AT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-strip-probe-'))
os.environ['HOME'] = str(root)
os.environ['USERPROFILE'] = str(root)

opened = []
real_open = open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


import builtins
builtins.open = watched_open

import socket
reached = []


def refuse(address, *found, **named):
    reached.append(str(address))
    raise OSError('the probe may not reach outside')


socket.create_connection = refuse
socket.socket.connect = lambda self, address, *a, **k: refuse(address)

from src.gui.main_tabs import crypto_news_ticker_surface as s

built_at_import = s.PANE_MODEL is not None
opened_at_import = list(opened)
model = s.pane_model()
answer = {'built_at_import': built_at_import,
          'built_on_request': s.pane_model() is s.PANE_MODEL,
          'label': model.label_text,
          'opened_at_import': opened_at_import,
          'reached_at_import': list(reached),
          'made_under_home': sorted(str(p) for p in root.rglob('*'))}
builtins.open = real_open
print(json.dumps(answer))
"""


def run_script(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    if env:
        where.update(env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=where,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the news strip pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["label_text"] == surface.INITIAL_TEXT
    assert result["headlines"] == []
    assert len(result["sources"]) == 10


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_strip_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["label_text"] == "[2/2] Decrypt · Second"
    assert answered["label_tooltip"].startswith("Decrypt")
    assert answered["label_style"] == surface.LABEL_STYLE
    assert answered["index"] == 1
    assert answered["stories"] == 2
    assert answered["sources"] == 10
    assert answered["parsed"] == ["CoinDesk · T"]
    assert answered["lifecycle"][surface.WORKER_NAME]["found_by_owner_search"] is False
    assert answered["calls"] > 3


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_shipped_strip_carries_no_screen_where_qt_is_absent():
    """The shipped strip built its screen without the interface library.

    Its Qt import is guarded, so the module loads and its feed reading
    still works. The strip itself, its worker and its worker register are
    all declared inside that guard, so none of them exists. The surface
    carries the whole screen in the same process.
    """
    probe = BLOCK_QT + (
        "import json\n"
        "from src.gui import crypto_news_ticker as t\n"
        "print(json.dumps({'has_qt': t._HAS_QT,\n"
        "    'has_strip': hasattr(t, 'CryptoNewsTicker'),\n"
        "    'has_worker': hasattr(t, '_FetchWorker'),\n"
        "    'has_register': hasattr(t, '_LIVE_WORKERS'),\n"
        "    'has_parse': hasattr(t, 'parse_rss')}))\n"
    )
    answered = run_script(probe)
    assert answered["has_qt"] is False
    assert answered["has_strip"] is False
    assert answered["has_worker"] is False
    assert answered["has_register"] is False
    assert answered["has_parse"] is True
    loaded = run_script(
        "import json\n"
        "from src.gui import crypto_news_ticker as t\n"
        "print(json.dumps({'has_qt': t._HAS_QT,\n"
        "    'has_strip': hasattr(t, 'CryptoNewsTicker')}))\n"
    )
    assert loaded["has_qt"] is True
    assert loaded["has_strip"] is True


def test_importing_the_surface_reads_no_file():
    """Loading the surface read a file, reached a host, or built the strip.

    The home directory is pointed at a throwaway folder and every file
    open and every outward connection is recorded before the surface is
    imported.
    """
    answered = run_script(NOTHING_AT_IMPORT_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["label"] == surface.INITIAL_TEXT, answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    read_by_the_surface = [
        name
        for name in answered["opened_at_import"]
        if "crypto_news_ticker" in name or "acervator" in name.lower()
    ]
    assert read_by_the_surface == [], read_by_the_surface


def test_the_import_probe_can_report_a_file_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import crypto_news_ticker_surface as s",
        "with open(root / 'acervator-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "from src.gui.main_tabs import crypto_news_ticker_surface as s",
    )
    answered = run_script(probe)
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    seeded = [
        name for name in answered["opened_at_import"] if "acervator-seeded" in name
    ]
    assert seeded, answered["opened_at_import"]


SURFACE_DRIVE = (
    "stories = [m.NewsHeadline('First', 'https://story.invalid/1',\n"
    "    m.NewsSource('cd', 'CoinDesk', 'https://feed.invalid/rss'), 3.0),\n"
    "    m.NewsHeadline('Second', 'https://story.invalid/2',\n"
    "    m.NewsSource('dc', 'Decrypt', 'https://feed.invalid/rss'), 2.0)]\n"
    "model = m.build_model(stories, lambda: 1700000000.5)\n"
    "model.advance()\n"
    "m.build_view_model(model)\n"
    "m.parse_rss(b'<rss><channel><item><title>T</title>'\n"
    "    b'<link>https://story.invalid/9</link></item></channel></rss>',\n"
    "    m.NewsSource('cd', 'CoinDesk', 'https://feed.invalid/rss'))\n"
)


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    answered = qt_free(
        "src.gui.main_tabs.crypto_news_ticker_surface", "CryptoNewsTickerModel"
    )
    assert answered["imported"] is True, answered
    assert answered["qt"] == [], answered


def test_the_qt_block_stops_the_class_that_paints_the_strip():
    """POSITIVE CONTROL for ``qt_free``: ``CryptoNewsTicker`` is absent when
    Qt is refused."""
    answered = qt_free("src.gui.crypto_news_ticker", "CryptoNewsTicker")
    assert answered["imported"] is False, answered
    assert answered["error"] == "AttributeError", answered


def test_the_surface_opens_no_file_no_socket_and_no_browser():
    """The surface reached for a file, a network address or a browser."""
    answered = io_watched("src.gui.main_tabs.crypto_news_ticker_surface", SURFACE_DRIVE)
    assert answered["touched"] == [], answered


def test_the_io_watch_reports_a_route_that_was_reached():
    """POSITIVE CONTROL for ``io_watched``: a driven open and a driven
    browser call are both recorded."""
    answered = io_watched(
        "src.gui.main_tabs.crypto_news_ticker_surface",
        "open(m.__file__).close()\n"
        "import webbrowser\n"
        "try:\n"
        "    webbrowser.open('https://example.invalid')\n"
        "except Exception:\n"
        "    pass\n",
    )
    assert "open" in answered["touched"], answered
    assert "webbrowser" in answered["touched"], answered


# Nothing reaches outside, and nothing is written to the operator's tree


def test_no_connection_is_attempted_while_both_sides_are_driven(
    monkeypatch, refuse_outside_connections
):
    """A driven case opened a real socket to a feed host."""
    for name in FEED_BODIES:
        parse_both(name)
    for name in FETCH_CASES:
        fetch_both(name, monkeypatch)
    for name in MERGE_CASES:
        merge_both(name, monkeypatch)
    for name in STRIP_STEPS:
        drive(name, monkeypatch)
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_two_real_outside_addresses(
    refuse_outside_connections,
):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("www.coindesk.com", 443)
    second = ("feeds.bloomberg.com", 443)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections
    assert second in refuse_outside_connections


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in FEED_BODIES:
        parse_both(name)
    for name in FETCH_CASES:
        fetch_both(name, monkeypatch)
    for name in STRIP_STEPS:
        drive(name, monkeypatch)
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


# The file runs in the CI fast lane


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences
