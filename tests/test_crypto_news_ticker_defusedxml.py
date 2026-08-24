"""Tests for the defusedxml adoption in src/gui/crypto_news_ticker.py.

WHAT A FAILURE MEANS is stated per class rather than per assert, because
the classes are the units of meaning here. Nothing below is forced red;
each test pins behaviour this change introduced or preserved, and the
sentence beside it says what the world would have to be like for the
test to go red.

The numbers quoted are measurements taken by driving the real
``parse_rss`` entry point of both trees, CPython 3.14.4 / expat 2.7.5,
before this file was written -- not predictions.

This file does NOT import ``xml.etree``. Comparing the new parser to the
old one is a real question, but importing the old one here would put
ruff S314 and semgrep use-defused-xml on the test file itself. The
comparison was run as a scratchpad measurement instead, and its results
are the numbers quoted below.
"""
from __future__ import annotations

import logging
import tracemalloc
from pathlib import Path

import pytest

# No sys.path insert and no E402 suppression: tests/conftest.py already
# puts the repo root on sys.path, and conftest is imported first.
from src.gui.crypto_news_ticker import (
    MAX_FEED_BYTES,
    NEWS_SOURCES,
    NewsSource,
    fetch_one,
    parse_rss,
)

SRC = NewsSource("t", "Test Feed", "https://example.invalid/rss")

CANARY = "XXE_CANARY_LOCAL_DISK_CONTENT"


# ------------------------------------------------------------------
# Payload builders. Every one is a real RSS 2.0 or Atom document, so
# the real entry point walks them exactly as it walks a feed.
# ------------------------------------------------------------------

def _entity_doc(body: str, refs: int = 1) -> bytes:
    """A feed that DECLARES one internal entity and references it."""
    return ("<?xml version='1.0'?>\n<!DOCTYPE rss [\n"
            f'  <!ENTITY big "{body}">\n'
            "]>\n<rss version='2.0'><channel><item><title>"
            + "&big;" * refs
            + "</title><link>https://example.invalid/e</link>"
              "</item></channel></rss>").encode()


def _billion_laughs() -> bytes:
    """The textbook bomb: 9 levels of ten-fold nesting."""
    decls = ['  <!ENTITY a0 "lol">']
    for i in range(1, 10):
        decls.append(f'  <!ENTITY a{i} "' + f"&a{i - 1};" * 10 + '">')
    return ("<?xml version='1.0'?>\n<!DOCTYPE rss [\n"
            + "\n".join(decls)
            + "\n]>\n<rss version='2.0'><channel><item>"
              "<title>&a9;</title>"
              "<link>https://example.invalid/bomb</link>"
              "</item></channel></rss>").encode()


def _deep_feed(depth: int) -> bytes:
    """A valid feed buried under ``depth`` nested wrapper elements."""
    head = "".join(f"<n{i}>" for i in range(depth))
    tail = "".join(f"</n{i}>" for i in reversed(range(depth)))
    return ("<rss version='2.0'><channel>" + head
            + "<item><title>Deep headline</title>"
              "<link>https://example.invalid/deep</link></item>"
            + tail + "</channel></rss>").encode()


# ------------------------------------------------------------------
# Entity declarations are refused.
#
# A FAILURE HERE MEANS a feed host can still make the ticker's worker
# thread expand entity text it chose, on a thread inside the trading
# GUI. That is the whole reason the parser was replaced, and the band
# that matters is the one BELOW expat's own guard, which is what
# TestSubThresholdBand covers.
# ------------------------------------------------------------------

class TestEntityDeclarationsRefused:
    def test_a_single_harmless_entity_declaration_is_refused(self):
        """The rule is the DECLARATION, not the size.

        Size is what expat's own amplification ceiling already judges,
        and it judges it badly -- see the sub-threshold test below.
        """
        assert parse_rss(_entity_doc("hello"), SRC) == []

    def test_billion_laughs_is_refused(self):
        assert parse_rss(_billion_laughs(), SRC) == []

    def test_unparsed_ndata_entity_is_refused(self):
        raw = (b"<?xml version='1.0'?>\n<!DOCTYPE r [\n"
               b" <!ENTITY img SYSTEM \"file:///c:/win.ini\" NDATA gif>\n"
               b" <!NOTATION gif PUBLIC \"gif\">\n]>\n"
               b"<rss version='2.0'><channel><item>"
               b"<title>t</title><link>https://example.invalid/n</link>"
               b"</item></channel></rss>")
        assert parse_rss(raw, SRC) == []

    def test_refusal_is_logged_as_a_warning_naming_the_source(
            self, capture_log):
        """A refused feed must not be a silent zero.

        A failure here means a feed host could start shipping entity
        declarations and the operator would see nothing but a shorter
        ticker.

        ``capture_log`` rather than ``caplog``: logging_engine sets
        ``acervator.propagate = False``, so once any earlier test has
        built it, ``caplog`` sees nothing from this logger.
        """
        with capture_log("acervator.crypto_news_ticker") as records:
            parse_rss(_entity_doc("x", refs=3), SRC)
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "Test Feed" in message
        assert "refused" in message


class TestSubThresholdBand:
    """The band expat's own guard does not cover.

    A FAILURE HERE MEANS the refusal is size-gated the same way expat's
    ceiling is, and the exact window the previous parser was vulnerable
    in is still open.

    Measured on the previous code, same bytes: PARSED, expanded to
    3,000,027 characters, 6,009,619 bytes of peak allocation, and
    RETURNED A HEADLINE.
    """

    def test_sub_threshold_blowup_is_refused(self):
        doc = _entity_doc("A" * 20_000, refs=150)
        assert len(doc) < 25_000, "payload must stay small to make the point"
        assert parse_rss(doc, SRC) == []

    def test_refusal_does_not_pay_for_the_expansion_first(self):
        """Refusing late is not refusing.

        A failure here means the bytes were expanded and then thrown
        away, so a feed host still sets the memory bill even though no
        headline comes out.

        Measured: 142,726 bytes peak under this parser against
        6,009,619 under the previous one on this payload, and
        59,097,148 on the billion-laughs document. The 4 MiB ceiling
        sits far above the first and far below the other two.
        """
        doc = _entity_doc("A" * 20_000, refs=150)
        parse_rss(_entity_doc("warm"), SRC)     # pay one-time parser setup
        tracemalloc.start()
        try:
            assert parse_rss(doc, SRC) == []
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak < 4 * 1024 * 1024, (
            f"parse allocated {peak} bytes refusing a {len(doc)}-byte feed")


# ------------------------------------------------------------------
# External entities.
#
# A FAILURE HERE MEANS a feed host can read the operator's local disk
# through the news ticker.
#
# HONEST FRAMING: the previous stdlib parser did not leak either --
# measured, both payloads below raised "undefined entity" and the file
# was never opened, because ElementTree installs no external-entity
# handler. These tests pin a PRESERVED property, not a repaired one.
# They exist because adopting a new parser is exactly when an inherited
# default can quietly change.
# ------------------------------------------------------------------

class TestExternalEntitiesNeverRead:
    def test_internal_dtd_file_entity_is_refused_and_never_read(
            self, tmp_path, capture_log):
        target = tmp_path / "secret.txt"
        target.write_text(CANARY, encoding="utf-8")
        raw = ("<?xml version='1.0'?>\n"
               f'<!DOCTYPE rss [ <!ENTITY xxe SYSTEM "{target.as_uri()}"> ]>\n'
               "<rss version='2.0'><channel><item>"
               "<title>&xxe;</title>"
               "<link>https://example.invalid/x</link>"
               "</item></channel></rss>").encode()

        with capture_log("acervator.crypto_news_ticker") as records:
            out = parse_rss(raw, SRC)

        assert out == []
        joined = " ".join(r.getMessage() for r in records)
        assert CANARY not in joined, "the file's content reached a log line"

    def test_external_dtd_subset_is_not_fetched(self, tmp_path):
        """The other XXE shape: the DTD itself lives on disk.

        A failure means the parser followed a SYSTEM identifier out of
        the document and into the filesystem.
        """
        dtd = tmp_path / "leak.dtd"
        dtd.write_text(f'<!ENTITY leak "{CANARY}">', encoding="utf-8")
        raw = ("<?xml version='1.0'?>\n"
               f'<!DOCTYPE rss SYSTEM "{dtd.as_uri()}">\n'
               "<rss version='2.0'><channel><item>"
               "<title>&leak;</title>"
               "<link>https://example.invalid/d</link>"
               "</item></channel></rss>").encode()

        out = parse_rss(raw, SRC)
        assert out == []
        assert all(CANARY not in h.title for h in out)


# ------------------------------------------------------------------
# A parser that blocks everything is not a fix.
#
# A FAILURE HERE MEANS the hardening is too broad and the operator's
# ticker goes blank. Every shape below was produced identically by the
# previous parser, measured side by side.
# ------------------------------------------------------------------

class TestOrdinaryFeedsStillParse:
    def test_rss_2_0_yields_headlines_in_order(self):
        raw = ("<?xml version='1.0' encoding='UTF-8'?>\n"
               '<rss version="2.0"><channel>\n'
               "  <title>Acervator Test Wire</title>\n"
               "  <item><title>Bitcoin clears 70k on ETF inflows</title>"
               "<link>https://example.invalid/story-1</link>"
               "<pubDate>Mon, 28 Jul 2026 12:00:00 GMT</pubDate></item>\n"
               "  <item><title>Cash &amp; carry spread narrows</title>"
               "<link>https://example.invalid/story-2</link>"
               "<pubDate>Sun, 27 Jul 2026 09:30:00 GMT</pubDate></item>\n"
               "</channel></rss>").encode()
        out = parse_rss(raw, SRC)
        assert [(h.title, h.url) for h in out] == [
            ("Bitcoin clears 70k on ETF inflows",
             "https://example.invalid/story-1"),
            ("Cash & carry spread narrows",
             "https://example.invalid/story-2"),
        ]
        assert out[0].published_ts > 0

    def test_atom_attribute_link_is_read(self):
        raw = (b"<?xml version='1.0' encoding='UTF-8'?>\n"
               b"<feed xmlns='http://www.w3.org/2005/Atom'>"
               b"<entry><title>DeFi TVL crosses 200B</title>"
               b"<link href='https://example.invalid/atom-1'/>"
               b"<updated>2026-07-28T12:34:56Z</updated></entry>"
               b"</feed>")
        out = parse_rss(raw, SRC)
        assert [(h.title, h.url) for h in out] == [
            ("DeFi TVL crosses 200B", "https://example.invalid/atom-1")]

    def test_predefined_and_numeric_references_survive(self):
        """Refusing DECLARATIONS must not break the five built-ins."""
        raw = (b"<rss version='2.0'><channel><item>"
               b"<title>A &amp; B &lt;C&gt; &#39;D&#x27;</title>"
               b"<link>https://example.invalid/e?a=1&amp;b=2</link>"
               b"</item></channel></rss>")
        out = parse_rss(raw, SRC)
        assert out[0].title == "A & B <C> 'D'"
        assert out[0].url == "https://example.invalid/e?a=1&b=2"

    def test_cdata_is_plain_text(self):
        raw = (b"<rss version='2.0'><channel><item>"
               b"<title><![CDATA[Cash & <carry>]]></title>"
               b"<link>https://example.invalid/c</link>"
               b"</item></channel></rss>")
        assert parse_rss(raw, SRC)[0].title == "Cash & <carry>"

    def test_a_doctype_without_entities_is_still_accepted(self):
        """forbid_dtd is deliberately left at the library default.

        A failure here means the hardening refuses a bare doctype, which
        is a real feed shape and not an attack.
        """
        raw = (b"<?xml version='1.0'?>\n<!DOCTYPE rss>\n"
               b"<rss version='2.0'><channel><item>"
               b"<title>Plain doctype</title>"
               b"<link>https://example.invalid/dt</link>"
               b"</item></channel></rss>")
        assert [h.title for h in parse_rss(raw, SRC)] == ["Plain doctype"]

    def test_limit_and_truncation_are_unchanged(self):
        entries = "".join(
            f"<item><title>t{i}</title>"
            f"<link>https://example.invalid/{i}</link></item>"
            for i in range(20))
        raw = ("<rss version='2.0'><channel>" + entries
               + "</channel></rss>").encode()
        assert len(parse_rss(raw, SRC, limit=5)) == 5

        long_raw = ("<rss version='2.0'><channel><item><title>"
                    + "A" * 500
                    + "</title><link>https://example.invalid/l</link>"
                      "</item></channel></rss>").encode()
        assert len(parse_rss(long_raw, SRC)[0].title) == 220


# ------------------------------------------------------------------
# The docstring's own contract: malformed returns [] rather than raise.
#
# A FAILURE HERE MEANS parse_rss raises into fetch_one's blanket
# handler, which turns a diagnosable feed problem into a debug line,
# and breaks the sentence written above the function.
# ------------------------------------------------------------------

class TestMalformedNeverRaises:
    @pytest.mark.parametrize("raw", [
        b"",
        b"<not-valid-xml",
        b"404 Not Found",
        b"<rss><channel><item><title>unclosed</title>",
        b"\xff\xfe\x00garbage",
    ])
    def test_returns_empty_list(self, raw):
        assert parse_rss(raw, SRC) == []

    @pytest.mark.parametrize("depth", [997, 2000])
    def test_deeply_nested_feed_returns_its_headline(self, depth):
        """The regression the hand-rolled element class introduced.

        A hand-written ``iter()`` that recursed once per nesting level
        raised RecursionError out of parse_rss at depth 996 on a
        12,854-byte document, breaking the contract above. The stdlib
        element type iterates with an explicit stack, so adopting
        defusedxml removes the recursion with the class.

        A failure here means that regression has come back.
        """
        out = parse_rss(_deep_feed(depth), SRC)
        assert [h.title for h in out] == ["Deep headline"]


# ------------------------------------------------------------------
# The response read is capped.
#
# A FAILURE HERE MEANS a feed host still chooses how many bytes land in
# the GUI process. Closing the entity path bounds what the PARSER can
# be made to allocate; it does nothing about a plain oversized body.
# ------------------------------------------------------------------

class _Resp:
    """A response stub that ADVANCES, like the stream it stands for.

    The first version of this stub returned ``self._body[:amount]`` on
    every call, from offset zero. That modelled a reader that calls
    ``read`` exactly once. ``fetch_one`` now reads the body in bounded
    chunks (issue #105, so a teardown does not have to wait out a
    third-party host), and a stub that never advances hands the same
    bytes back for ever. It reported an oversized feed where the real
    stream would have reported a small one.

    A stub that does not model the thing it replaces turns a correct
    change into a red test. This one keeps an offset.
    """

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0
        self.read_args: list[int | None] = []

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, amount: int | None = None) -> bytes:
        self.read_args.append(amount)
        if amount is None:
            chunk = self._body[self._offset:]
        else:
            chunk = self._body[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk


class TestResponseSizeCap:
    def test_cap_is_a_sane_size_for_a_feed(self):
        assert MAX_FEED_BYTES == 4 * 1024 * 1024

    def test_read_is_bounded_rather_than_unlimited(self, monkeypatch):
        """A failure means ``resp.read()`` was called with no argument,
        which reads until the peer stops sending.

        The read is now CHUNKED as well as capped (issue #105), so the
        assertion is on the shape of every request rather than on a
        single one: no request may be unbounded, none may exceed the
        chunk size, and the total asked for may not exceed the cap.
        """
        from src.gui import crypto_news_ticker as cnt
        resp = _Resp(b"<rss version='2.0'><channel><item>"
                     b"<title>Small</title>"
                     b"<link>https://example.invalid/s</link>"
                     b"</item></channel></rss>")
        monkeypatch.setattr(cnt, "safe_urlopen", lambda *_a, **_k: resp)
        assert [h.title for h in cnt.fetch_one(SRC)] == ["Small"]
        assert resp.read_args
        assert None not in resp.read_args
        assert all(a <= cnt.READ_CHUNK_BYTES
                   for a in resp.read_args if a is not None)
        assert sum(a for a in resp.read_args
                   if a is not None) <= MAX_FEED_BYTES + 1

    def test_oversized_body_is_dropped_and_logged(
            self, monkeypatch, capture_log):
        from src.gui import crypto_news_ticker as cnt
        oversized = (b"<rss version='2.0'><channel><item>"
                     b"<title>Huge</title>"
                     b"<link>https://example.invalid/h</link>"
                     b"</item></channel></rss>"
                     + b" " * (MAX_FEED_BYTES + 1))
        resp = _Resp(oversized)
        monkeypatch.setattr(cnt, "safe_urlopen", lambda *_a, **_k: resp)

        with capture_log("acervator.crypto_news_ticker") as records:
            out = cnt.fetch_one(SRC)

        assert out == []
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "exceeded" in warnings[0].getMessage()

    def test_a_body_exactly_at_the_cap_is_still_parsed(self, monkeypatch):
        """The boundary, driven rather than assumed.

        A failure here means the cap rejects a legal feed one byte
        early, which would silently drop a source.
        """
        from src.gui import crypto_news_ticker as cnt
        head = (b"<rss version='2.0'><channel><item>"
                b"<title>Edge</title>"
                b"<link>https://example.invalid/edge</link>"
                b"</item></channel><!--")
        tail = b"--></rss>"
        pad = MAX_FEED_BYTES - len(head) - len(tail)
        body = head + b"x" * pad + tail
        assert len(body) == MAX_FEED_BYTES
        monkeypatch.setattr(
            cnt, "safe_urlopen", lambda *_a, **_k: _Resp(body))
        assert [h.title for h in cnt.fetch_one(SRC)] == ["Edge"]


# ------------------------------------------------------------------
# H9 -- the fetch performs the allowlist instead of asserting it.
#
# A FAILURE HERE MEANS the scheme control is once again a comment
# beside a suppression rather than code that runs.
# ------------------------------------------------------------------

class TestFetchRoutesThroughSafeUrl:
    def test_module_holds_no_bare_urlopen_or_request(self):
        from src.gui import crypto_news_ticker as cnt
        assert not hasattr(cnt, "urlopen")
        assert not hasattr(cnt, "Request")
        assert hasattr(cnt, "safe_urlopen")
        assert hasattr(cnt, "SafeRequest")

    def test_source_file_carries_no_suppression_for_this_unit(self):
        path = (Path(__file__).resolve().parents[1]
                / "src" / "gui" / "crypto_news_ticker.py")
        text = path.read_text(encoding="utf-8")
        assert "S310" not in text
        assert "S314" not in text
        assert "nosec" not in text
        assert "type: ignore" not in text

    def test_fetch_one_hands_safe_urlopen_a_checked_request(
            self, monkeypatch):
        from src.core.safe_url import SafeRequest
        from src.gui import crypto_news_ticker as cnt

        seen: dict[str, object] = {}

        def _fake(req, *_a, **kw):
            seen["req"] = req
            seen["timeout"] = kw.get("timeout")
            return _Resp(b"<rss version='2.0'><channel><item>"
                         b"<title>Routed</title>"
                         b"<link>https://example.invalid/r</link>"
                         b"</item></channel></rss>")

        monkeypatch.setattr(cnt, "safe_urlopen", _fake)
        out = cnt.fetch_one(SRC, timeout=3.5)

        assert [h.title for h in out] == ["Routed"]
        assert isinstance(seen["req"], SafeRequest)
        assert seen["timeout"] == 3.5

    def test_headers_are_still_sent(self, monkeypatch):
        from src.gui import crypto_news_ticker as cnt
        seen: dict[str, dict[str, str]] = {}

        def _fake(req, *_a, **_kw):
            seen["headers"] = dict(req.headers)
            return _Resp(b"<rss/>")

        monkeypatch.setattr(cnt, "safe_urlopen", _fake)
        cnt.fetch_one(SRC)
        assert "AcervatorNewsTicker" in seen["headers"]["User-agent"]
        assert "application/rss+xml" in seen["headers"]["Accept"]

    def test_file_scheme_source_is_refused_and_never_read(
            self, tmp_path, capture_log):
        """The scheme family that already hid a real file:/// hole."""
        secret = tmp_path / "secret.xml"
        secret.write_text(
            "<rss version='2.0'><channel><item>"
            f"<title>{CANARY}</title>"
            "<link>https://example.invalid/leak</link>"
            "</item></channel></rss>",
            encoding="utf-8")
        bad = NewsSource("bad", "Bad Feed", secret.as_uri())
        assert bad.url.startswith("file:")

        with capture_log("acervator.crypto_news_ticker") as records:
            out = fetch_one(bad)

        assert out == []
        joined = " ".join(r.getMessage() for r in records)
        assert CANARY not in joined
        assert "Bad Feed" in joined
        assert "refused" in joined

    def test_every_shipped_source_survives_the_allowlist(self):
        from src.core.safe_url import SafeRequest
        for source in NEWS_SOURCES:
            assert SafeRequest(source.url).full_url == source.url


# ------------------------------------------------------------------
# The parse path is defusedxml's, not the stdlib's.
#
# A FAILURE HERE MEANS an edit swapped the import back and every test
# above would then be measuring the stdlib parser while still passing
# on the shapes it happens to agree about. This is the guard that makes
# the rest of the file mean what it says.
# ------------------------------------------------------------------

class TestTheParserIsTheDefusedOne:
    def test_module_fromstring_is_defusedxmls(self):
        import defusedxml.ElementTree as defused

        from src.gui import crypto_news_ticker as cnt
        assert cnt.fromstring is defused.fromstring

    def test_the_caught_type_is_the_type_actually_raised(self):
        """Driven, not asserted by name.

        The module catches ``DefusedXmlException``, the library's base
        class, so a refusal kind the library adds later is caught too.
        This drives the library directly and checks the exception that
        really comes out is the one the module really catches -- a
        mismatch would make every refusal escape as an unhandled error
        into fetch_one's blanket handler.
        """
        import defusedxml.ElementTree as defused

        from src.gui import crypto_news_ticker as cnt
        with pytest.raises(cnt.DefusedXmlException):
            defused.fromstring(_entity_doc("boom"))
