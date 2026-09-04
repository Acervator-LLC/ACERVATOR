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

import ssl
import urllib.error
import urllib.request

import pytest

from src.exchange.ccxt_connector import (
    CCXT_DECIMAL_PLACES,
    CCXT_SIGNIFICANT_DIGITS,
    CCXT_TICK_SIZE,
    PASSPHRASE_EXCHANGES,
    PREFLIGHT_URLS,
    SUPPORTED_EXCHANGES,
    US_ACCOUNT_RESTRICTED_EXCHANGES,
    US_IP_BLOCKED_EXCHANGES,
    US_RESTRICTED_EXCHANGES,
    VERIFIED_EXCHANGES,
    exchange_label,
    list_supported_exchanges,
    resolve_ccxt_class,
)
from src.exchange.timeframes import ALL_TIMEFRAMES, available_timeframes

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


_NO_NETWORK = "no network in this test"
_FILE_URL = "file:///etc/passwd"
_HTTPS_URL = "https://example.invalid/ping"


class _RecordingUrlopen:
    """A urlopen stand-in: it records each URL in `opened`, then raises."""

    def __init__(self, opened: list[str]) -> None:
        self.opened = opened

    def __call__(self, request, timeout, context) -> None:
        """Record `request` and raise `urllib.error.URLError`."""
        del timeout, context
        self.opened.append(request.full_url)
        raise urllib.error.URLError(_NO_NETWORK)


def test_the_diagnostic_opens_no_url_outside_https(monkeypatch) -> None:
    """`_check_public_endpoints` refuses a non-https entry without opening it."""
    from tools import exchange_diagnostic as diag

    opened: list[str] = []
    monkeypatch.setattr(diag, "PREFLIGHT_URLS", {"evil": _FILE_URL})
    monkeypatch.setattr(diag.urllib.request, "urlopen", _RecordingUrlopen(opened))
    results = diag._check_public_endpoints(ssl.create_default_context())

    assert opened == [], f"the diagnostic opened {opened}"
    assert results["evil"][0] == "REFUSED", f"got {results['evil']!r}, wanted REFUSED"


def test_the_diagnostic_allows_an_https_entry(monkeypatch) -> None:
    """The refusal is not blanket: an https entry still reaches `urlopen`."""
    from tools import exchange_diagnostic as diag

    opened: list[str] = []
    monkeypatch.setattr(diag, "PREFLIGHT_URLS", {"good": _HTTPS_URL})
    monkeypatch.setattr(diag.urllib.request, "urlopen", _RecordingUrlopen(opened))
    results = diag._check_public_endpoints(ssl.create_default_context())

    assert opened == [_HTTPS_URL], f"opened {opened}"
    assert results["good"][0] == "FAIL", f"got {results['good']!r}"


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


def test_ccxt_precision_mode_constants_match_the_installed_ccxt():
    """The mirrored precisionMode integers must equal ccxt's own.

    ``precision_to_decimals`` branches on these. If ccxt renumbers them
    the connector would read every tick size under the wrong rule and
    report a wrong decimal-place count for every market, silently.
    """
    assert CCXT_DECIMAL_PLACES == ccxt.DECIMAL_PLACES
    assert CCXT_SIGNIFICANT_DIGITS == ccxt.SIGNIFICANT_DIGITS
    assert CCXT_TICK_SIZE == ccxt.TICK_SIZE


def test_us_restricted_is_the_union_of_its_two_causes():
    """A geo-IP refusal and an account-eligibility refusal are different
    facts established by different methods. The connect path warns on
    both, so the union must stay exact and the causes must not overlap."""
    assert US_RESTRICTED_EXCHANGES == (
        US_IP_BLOCKED_EXCHANGES | US_ACCOUNT_RESTRICTED_EXCHANGES
    )
    assert not (US_IP_BLOCKED_EXCHANGES & US_ACCOUNT_RESTRICTED_EXCHANGES)


def test_verified_exchanges_names_only_venues_that_have_traded():
    """Coinbase is the only venue Acervator has ever traded on. Adding an
    id here asserts real order placement, fills and balance reads on that
    venue; this test is the place that claim has to be defended."""
    assert VERIFIED_EXCHANGES == {"coinbase"}
    assert VERIFIED_EXCHANGES <= set(SUPPORTED_EXCHANGES)
    assert US_IP_BLOCKED_EXCHANGES <= set(SUPPORTED_EXCHANGES)
    assert US_ACCOUNT_RESTRICTED_EXCHANGES <= set(SUPPORTED_EXCHANGES)


@pytest.mark.parametrize("exchange_id", sorted(SUPPORTED_EXCHANGES))
def test_every_unverified_or_blocked_venue_says_so_in_its_label(exchange_id):
    """A venue that cannot be reached, or has never been traded on, must
    not appear in a picker looking like the one that has."""
    label = exchange_label(exchange_id)
    if exchange_id in US_IP_BLOCKED_EXCHANGES:
        assert "blocked from US" in label
    elif exchange_id not in VERIFIED_EXCHANGES:
        assert "untested" in label
    else:
        assert "untested" not in label and "blocked" not in label
    assert ("passphrase required" in label) == (exchange_id in PASSPHRASE_EXCHANGES)


def test_listing_carries_the_status_of_every_registry_entry():
    """``list_supported_exchanges`` is the data surface for the pickers;
    each row must carry the verification and reachability facts."""
    rows = {r["id"]: r for r in list_supported_exchanges()}
    assert set(rows) == set(SUPPORTED_EXCHANGES)
    for eid, row in rows.items():
        assert row["verified"] == (eid in VERIFIED_EXCHANGES)
        assert row["us_ip_blocked"] == (eid in US_IP_BLOCKED_EXCHANGES)
        assert row["label"] == exchange_label(eid)


@pytest.mark.parametrize("exchange_id", sorted(SUPPORTED_EXCHANGES))
def test_no_supported_venue_falls_through_the_permissive_timeframe_default(
    exchange_id,
):
    """An exchange absent from the timeframe map is handed all eleven
    timeframes. Six declared venues offer fewer than that, and requesting
    one they lack returns an empty candle array — the TA engine then sees
    too few candles and holds, with no error anywhere."""
    offered = available_timeframes(exchange_id)
    assert offered, exchange_id
    if set(offered) == set(ALL_TIMEFRAMES):
        from src.exchange import timeframes as tf_module

        assert exchange_id in tf_module._AVAILABILITY, (
            f"{exchange_id} returns the full set only because it is missing "
            f"from _AVAILABILITY, not because it was measured to offer it"
        )
