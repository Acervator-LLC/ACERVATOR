"""v3.23.54 — pin tests for the crypto news ticker.

Fetch code is network-dependent so we exercise the RSS parser
directly with representative XML fixtures and the widget's public
behaviour with monkeypatched fetch_all. Never hits the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.crypto_news_ticker import (  # noqa: E402
    NEWS_SOURCES,
    NewsHeadline,
    NewsSource,
    parse_rss,
    _parse_ts,
)


class TestRSSParser:
    def test_rss_2_0_shape(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Sample</title>
  <item>
    <title>Bitcoin hits new high</title>
    <link>https://example.com/story-1</link>
    <pubDate>Mon, 28 Jul 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Ethereum upgrade shipped</title>
    <link>https://example.com/story-2</link>
    <pubDate>Sun, 27 Jul 2026 09:30:00 GMT</pubDate>
  </item>
</channel></rss>"""
        src = NewsSource("test", "Test Feed", "https://example.com/rss")
        out = parse_rss(xml, src)
        assert len(out) == 2
        assert out[0].title == "Bitcoin hits new high"
        assert out[0].url == "https://example.com/story-1"
        assert out[0].source is src
        assert out[0].published_ts > 0
        assert out[1].title == "Ethereum upgrade shipped"

    def test_atom_shape(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Sample Atom</title>
  <entry>
    <title>DeFi TVL crosses $200 B</title>
    <link href="https://example.com/atom-1" />
    <updated>2026-07-28T12:34:56Z</updated>
  </entry>
</feed>"""
        src = NewsSource("test", "Test Atom", "https://example.com/atom")
        out = parse_rss(xml, src)
        assert len(out) == 1
        assert out[0].title == "DeFi TVL crosses $200 B"
        assert out[0].url == "https://example.com/atom-1"

    def test_malformed_xml_returns_empty(self):
        out = parse_rss(b"<not-valid-xml", NEWS_SOURCES[0])
        assert out == []

    def test_missing_title_or_link_skipped(self):
        xml = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>No link here</title></item>
  <item><link>https://example.com/no-title</link></item>
  <item><title>Both present</title><link>https://example.com/ok</link></item>
</channel></rss>"""
        out = parse_rss(xml, NEWS_SOURCES[0])
        assert len(out) == 1
        assert out[0].title == "Both present"

    def test_limit_argument_respected(self):
        _entries = "".join(
            f"<item><title>t{i}</title>" f"<link>https://ex/{i}</link></item>"
            for i in range(20)
        )
        xml = b"<rss version='2.0'><channel>" + _entries.encode() + b"</channel></rss>"
        out = parse_rss(xml, NEWS_SOURCES[0], limit=5)
        assert len(out) == 5

    def test_title_truncated_at_220_chars(self):
        long_title = "A" * 500
        xml = (
            "<rss version='2.0'><channel><item>"
            f"<title>{long_title}</title><link>https://ex/</link>"
            "</item></channel></rss>"
        ).encode()
        out = parse_rss(xml, NEWS_SOURCES[0])
        assert len(out[0].title) == 220


class TestTimestampParse:
    def test_rfc2822(self):
        assert _parse_ts("Mon, 28 Jul 2026 12:00:00 GMT") > 0

    def test_iso8601_z_suffix(self):
        assert _parse_ts("2026-07-28T12:00:00Z") > 0

    def test_iso8601_offset(self):
        assert _parse_ts("2026-07-28T12:00:00+00:00") > 0

    def test_empty_returns_zero(self):
        assert _parse_ts("") == 0.0

    def test_garbage_returns_zero(self):
        assert _parse_ts("not a date") == 0.0


class TestNewsSourcesRegistry:
    def test_exactly_ten_sources(self):
        assert len(NEWS_SOURCES) == 10, (
            "Operator selected 10 free RSS feeds — a diff to add/remove "
            "sources should be intentional, not accidental."
        )

    def test_all_sources_have_https_urls(self):
        for s in NEWS_SOURCES:
            assert s.url.startswith(
                "https://"
            ), f"{s.name}: url must be HTTPS ({s.url!r})"

    def test_no_duplicate_slugs(self):
        slugs = [s.slug for s in NEWS_SOURCES]
        assert len(set(slugs)) == len(
            slugs
        ), "Duplicate slugs would cause lookup collisions."


class TestWidgetBehaviour:
    def test_ticker_cycles_headlines(self, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.crypto_news_ticker import CryptoNewsTicker

        # Feed 3 headlines directly (bypass network fetch)
        h1 = NewsHeadline("Bitcoin at 70k", "https://ex/1", NEWS_SOURCES[0], 100.0)
        h2 = NewsHeadline("ETH breaks 3k", "https://ex/2", NEWS_SOURCES[1], 90.0)
        h3 = NewsHeadline("Regs incoming", "https://ex/3", NEWS_SOURCES[2], 80.0)
        t = CryptoNewsTicker()
        t._on_headlines([h1, h2, h3])
        assert "Bitcoin at 70k" in t._label.text()
        assert "[1/3]" in t._label.text()

        t._advance()
        assert "ETH breaks 3k" in t._label.text()
        assert "[2/3]" in t._label.text()

        t._advance()
        assert "Regs incoming" in t._label.text()

        t._advance()  # wraps to first
        assert "Bitcoin at 70k" in t._label.text()

    def test_ticker_pauses_when_hovered(self, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.crypto_news_ticker import CryptoNewsTicker

        h1 = NewsHeadline("A", "https://ex/1", NEWS_SOURCES[0], 100.0)
        h2 = NewsHeadline("B", "https://ex/2", NEWS_SOURCES[1], 90.0)
        t = CryptoNewsTicker()
        t._on_headlines([h1, h2])
        # Simulate hover-enter → paused
        t._paused = True
        t._advance()
        assert "A" in t._label.text(), "paused advance must be a no-op"

    def test_empty_feed_shows_diagnostic(self, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.crypto_news_ticker import CryptoNewsTicker

        t = CryptoNewsTicker()
        t._on_headlines([])
        assert "no crypto news feeds reachable" in t._label.text()

    def test_cycle_interval_matches_operator_choice(self):
        """Operator picked 15s auto-advance in the v3.23.54 spec."""
        pytest.importorskip("PySide6.QtWidgets")
        from src.gui.crypto_news_ticker import CYCLE_INTERVAL_MS

        assert CYCLE_INTERVAL_MS == 15_000

    def test_hourly_refresh_interval(self):
        pytest.importorskip("PySide6.QtWidgets")
        from src.gui.crypto_news_ticker import REFRESH_INTERVAL_MS

        assert REFRESH_INTERVAL_MS == 60 * 60 * 1000
