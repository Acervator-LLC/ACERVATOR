"""In-memory validation of the supported-exchange registry.

Provenance
==========
The repo-root ``EXCHANGE_DIAGNOSTIC.py`` was an interactive, network-hitting
support script: it looped over a *hardcoded* copy of the exchange list, made
live HTTP calls to each venue, then prompted (via ``input()``) for API
credentials to test an authenticated connection. None of that can run in CI —
it needs the network, a human, and secrets — so the connectivity tool now
lives at ``tools/exchange_diagnostic.py`` where an operator can still run it.

What was genuinely testable in that script was buried at the bottom: the
assertion that every exchange Acervator claims to support resolves to a real
CCXT exchange class. That check is extracted here and pointed at the *real*
registry in ``src.exchange.ccxt_connector`` — the diagnostic's hardcoded list
was a duplicate of it — so a drift between the two can no longer hide.

Everything here runs in memory. No sockets, no files, no prompts.
"""

from __future__ import annotations

import pytest

from src.exchange.ccxt_connector import (
    PASSPHRASE_EXCHANGES,
    PREFLIGHT_URLS,
    SUPPORTED_EXCHANGES,
    US_RESTRICTED_EXCHANGES,
    resolve_ccxt_class,
)

ccxt = pytest.importorskip("ccxt", reason="ccxt is a runtime dependency")


@pytest.mark.parametrize("exchange_id", sorted(SUPPORTED_EXCHANGES))
def test_every_supported_exchange_has_a_ccxt_class(exchange_id):
    """Each supported exchange must resolve to an importable CCXT class.

    Uses the connector's own ``resolve_ccxt_class`` — the exact resolution
    production uses — so this test fails if the registry ever drifts from
    what CCXT provides, whichever way CCXT renames things next. (This is the
    test that caught gateio→gate / huobi→htx on ccxt 4.5.74.)
    """
    ccxt_id = SUPPORTED_EXCHANGES[exchange_id]
    assert resolve_ccxt_class(ccxt, ccxt_id) is not None, (
        f"{exchange_id!r} maps to CCXT id {ccxt_id!r}, which this version of "
        f"ccxt ({ccxt.__version__}) does not provide (even via a known alias)"
    )


def test_preflight_urls_cover_every_supported_exchange():
    """The registry and its preflight URLs must not drift apart."""
    assert set(PREFLIGHT_URLS) == set(SUPPORTED_EXCHANGES)


@pytest.mark.parametrize("exchange_id", sorted(PREFLIGHT_URLS))
def test_preflight_urls_are_https(exchange_id):
    """Every preflight endpoint must be HTTPS — a credential-bearing client
    must never be pointed at a plaintext URL."""
    url = PREFLIGHT_URLS[exchange_id]
    assert url.startswith("https://"), f"{exchange_id}: {url!r} is not HTTPS"


class _FakeCcxt:
    """A stand-in ccxt module exposing only the post-rename class names."""

    class gate:  # noqa: N801 - mirrors ccxt's lowercase class names
        pass

    class htx:  # noqa: N801
        pass


def test_resolver_falls_back_to_the_renamed_class():
    """gateio→gate and huobi→htx must resolve through the alias fallback even
    when the historical name is absent (the ccxt 4.5.x situation)."""
    fake = _FakeCcxt()
    assert resolve_ccxt_class(fake, "gateio") is _FakeCcxt.gate
    assert resolve_ccxt_class(fake, "huobi") is _FakeCcxt.htx


def test_resolver_prefers_the_historical_name_when_present():
    """On older ccxt where the historical name still exists, it wins — the
    fallback must not override a present class."""

    class _OldCcxt:
        class gateio:  # noqa: N801
            pass

        class gate:  # noqa: N801
            pass

    assert resolve_ccxt_class(_OldCcxt(), "gateio") is _OldCcxt.gateio


def test_resolver_returns_none_for_an_unknown_id():
    """An id with no class and no alias resolves to None, not an exception."""
    assert resolve_ccxt_class(_FakeCcxt(), "nonesuch") is None


def test_passphrase_and_restricted_sets_reference_known_exchanges():
    """The auxiliary sets must only name exchanges that actually exist in the
    registry; a stale id here silently disables its handling."""
    known = set(SUPPORTED_EXCHANGES)
    assert PASSPHRASE_EXCHANGES <= known, PASSPHRASE_EXCHANGES - known
    assert US_RESTRICTED_EXCHANGES <= known, US_RESTRICTED_EXCHANGES - known
