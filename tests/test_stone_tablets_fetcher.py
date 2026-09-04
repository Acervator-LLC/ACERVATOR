"""v3.23.99 — pin tests for the exchange-agnostic Stone Tablets fetcher.

Coverage:
    F1  ExchangeAdapter is abstract — subclass must implement fetch_chunk
    F2  CoinbaseAdapter chunk_span_ms = 350 * 5m in ms
    F3  GapFiller.fill_asset skips work when already covered
    F4  GapFiller.fill_asset walks a single gap in chunks, ingests each
    F5  GapFiller.fill_asset records chunk errors without aborting the gap
    F6  TargetAssetDiscovery reads bot_state.json (deterministic order)
    F7  TargetAssetDiscovery prefers bot_manager over state file
    F8  BuildOrchestrator dispatches per-target to the right adapter
    F9  ensure_asset_coverage builds a tablet from nothing (first-time
        generation flow — operator directive 2026-08-01)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stone_tablets import (  # noqa: E402
    NATIVE_TIMEFRAME,
    StoneTabletsRegistry,
)
from src.trading.stone_tablets.fetcher import (  # noqa: E402
    STEP_5M_MS,
    BuildOrchestrator,
    CoinbaseAdapter,
    ExchangeAdapter,
    FetchAttempt,
    GapFiller,
    TargetAssetDiscovery,
    discover_all_exchange_markets,
)

_START_MS = 1_735_689_600_000  # 2025-01-01T00:00:00Z


# --------------------------------------------------------------------- #
# Fake adapter for tests — no network                                   #
# --------------------------------------------------------------------- #


class _FakeAdapter(ExchangeAdapter):
    exchange_id = "fake"
    chunk_limit = 10
    chunk_sleep_s = 0.0

    def __init__(self, script: list, connector=None):
        super().__init__(connector)
        self._script = list(script)  # list of FetchAttempt
        self.calls: list[tuple[int, int]] = []
        # What the fetcher ASKED for, not only when. The parameter
        # names are fixed by ExchangeAdapter.fetch_chunk, so an
        # override cannot rename them out of a dead-code report --
        # it has to use them.
        self.requested: list[tuple[str, str, str]] = []

    async def fetch_chunk(
        self, asset, quote, since_ms, until_ms, timeframe=NATIVE_TIMEFRAME
    ):
        self.calls.append((since_ms, until_ms))
        self.requested.append((asset, quote, timeframe))
        if self._script:
            return self._script.pop(0)
        # Default: generate a chunk of synthetic candles
        rows = [
            [since_ms + i * STEP_5M_MS, 100.0, 101.0, 99.0, 100.5, 5.0]
            for i in range(
                min(self.chunk_limit, (until_ms - since_ms) // STEP_5M_MS + 1)
            )
        ]
        return FetchAttempt(since_ms, until_ms, rows)


# --------------------------------------------------------------------- #
# F1                                                                    #
# --------------------------------------------------------------------- #


def test_exchange_adapter_is_abstract():
    base = ExchangeAdapter(connector=None)
    with pytest.raises(NotImplementedError):
        asyncio.run(base.fetch_chunk("BTC", "USD", 0, 1000, NATIVE_TIMEFRAME))


# --------------------------------------------------------------------- #
# F2                                                                    #
# --------------------------------------------------------------------- #


def test_coinbase_adapter_chunk_span():
    ad = CoinbaseAdapter(connector=None)
    assert ad.chunk_limit == 350
    assert ad.chunk_sleep_s == 1.3
    assert ad.chunk_span_ms == 350 * STEP_5M_MS  # ~29 hours in ms


# --------------------------------------------------------------------- #
# F3                                                                    #
# --------------------------------------------------------------------- #


def test_gap_filler_skips_when_covered(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    rows = [
        [_START_MS + i * STEP_5M_MS, 100.0, 101.0, 99.0, 100.5, 5.0] for i in range(20)
    ]
    reg.ingest_candles(
        asset="BTC",
        timeframe=NATIVE_TIMEFRAME,
        rows=rows,
        source="test",
        exchange_id="fake",
    )
    adapter = _FakeAdapter([])
    filler = GapFiller(reg, adapter)
    report = asyncio.run(
        filler.fill_asset("BTC", _START_MS, _START_MS + 19 * STEP_5M_MS)
    )
    assert report.gaps_requested == 0
    assert report.chunks_attempted == 0
    assert adapter.calls == []  # never called the exchange


# --------------------------------------------------------------------- #
# F4                                                                    #
# --------------------------------------------------------------------- #


def test_gap_filler_walks_gap_in_chunks_and_ingests(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    # No prior tablet → full window is a gap. 25 5m candles = 25 * step
    # Adapter chunk_limit = 10, so we need 3 chunks (10 + 10 + 5).
    adapter = _FakeAdapter([])
    filler = GapFiller(reg, adapter)
    until = _START_MS + 24 * STEP_5M_MS
    report = asyncio.run(filler.fill_asset("BTC", _START_MS, until))
    assert report.gaps_requested == 1
    assert report.chunks_attempted >= 1
    assert report.chunks_ok == report.chunks_attempted
    assert report.candles_appended > 0


# --------------------------------------------------------------------- #
# F5                                                                    #
# --------------------------------------------------------------------- #


def test_gap_filler_records_chunk_errors(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    # Script: first chunk errors, subsequent chunks succeed
    err = FetchAttempt(
        _START_MS, _START_MS + 9 * STEP_5M_MS, [], error="synthetic 429 rate-limit"
    )
    ok = FetchAttempt(
        _START_MS + 10 * STEP_5M_MS,
        _START_MS + 19 * STEP_5M_MS,
        [
            [_START_MS + (10 + i) * STEP_5M_MS, 100.0, 101.0, 99.0, 100.5, 5.0]
            for i in range(10)
        ],
    )
    adapter = _FakeAdapter([err, ok])
    filler = GapFiller(reg, adapter)
    report = asyncio.run(
        filler.fill_asset("BTC", _START_MS, _START_MS + 19 * STEP_5M_MS)
    )
    assert report.chunks_error >= 1
    assert report.chunks_ok >= 1
    assert any("synthetic 429" in e for e in report.errors)
    # Gap-fill did not abort — the OK chunk still ingested
    assert report.candles_appended > 0


# --------------------------------------------------------------------- #
# F6                                                                    #
# --------------------------------------------------------------------- #


def test_target_discovery_from_bot_state(tmp_path):
    state_path = tmp_path / "bot_state.json"
    state_path.write_text(
        json.dumps(
            {
                "bots": {
                    "bot-1": {
                        "config": {"symbol": "BTC/USD", "exchange_id": "coinbase"}
                    },
                    "bot-2": {
                        "config": {"symbol": "ETH/USD", "exchange_id": "coinbase"}
                    },
                    "bot-3": {"config": {"symbol": "XRP/USD", "exchange_id": "kraken"}},
                }
            }
        )
    )
    disc = TargetAssetDiscovery(bot_state_path=state_path)
    targets = disc.enumerate()
    assert sorted(targets) == [
        ("BTC", "coinbase"),
        ("ETH", "coinbase"),
        ("XRP", "kraken"),
    ]


# --------------------------------------------------------------------- #
# F7                                                                    #
# --------------------------------------------------------------------- #


def test_target_discovery_prefers_bot_manager(tmp_path):
    # bot_state.json says one thing, bot_manager says another —
    # bot_manager wins when it's non-empty.
    state_path = tmp_path / "bot_state.json"
    state_path.write_text(
        json.dumps({"bots": {"stale-bot": {"config": {"symbol": "OLD/USD"}}}})
    )

    class _FakeBotMgr:
        def __init__(self):
            b = SimpleNamespace()
            b.config = SimpleNamespace(symbol="NEW/USD", exchange_id="coinbase")
            self._bots = {"live-bot": b}

    disc = TargetAssetDiscovery(bot_manager=_FakeBotMgr(), bot_state_path=state_path)
    targets = disc.enumerate()
    assert targets == [("NEW", "coinbase")]


# --------------------------------------------------------------------- #
# F8                                                                    #
# --------------------------------------------------------------------- #


def test_build_orchestrator_dispatches_per_target(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    state_path = tmp_path / "bot_state.json"
    state_path.write_text(
        json.dumps(
            {
                "bots": {
                    "bot-1": {"config": {"symbol": "BTC/USD", "exchange_id": "fake"}},
                    "bot-2": {"config": {"symbol": "ETH/USD", "exchange_id": "fake"}},
                }
            }
        )
    )
    disc = TargetAssetDiscovery(bot_state_path=state_path)
    adapter = _FakeAdapter([])
    orch = BuildOrchestrator(
        registry=reg, adapters_by_exchange={"fake": adapter}, discovery=disc
    )
    report = asyncio.run(
        orch.build_ytd(since_ms=_START_MS, until_ms=_START_MS + 14 * STEP_5M_MS)
    )
    assert len(report.reports) == 2
    assets = sorted(r.asset for r in report.reports)
    assert assets == ["BTC", "ETH"]
    assert report.total_candles > 0


# --------------------------------------------------------------------- #
# F9                                                                    #
# --------------------------------------------------------------------- #


def test_discover_all_exchange_markets_filters_active_and_quote():
    """v3.24.4 F10 — discover walks connector.get_markets() and
    returns only active markets whose quote is in the filter."""
    from types import SimpleNamespace

    async def _get_markets():
        return [
            SimpleNamespace(base="BTC", quote="USD", active=True),
            SimpleNamespace(base="ETH", quote="USD", active=True),
            SimpleNamespace(base="ADA", quote="USDC", active=True),
            SimpleNamespace(base="XRP", quote="EUR", active=True),
            SimpleNamespace(base="OLD", quote="USD", active=False),
            SimpleNamespace(base="", quote="USD", active=True),
        ]

    fake = SimpleNamespace()
    fake.get_markets = _get_markets
    result = asyncio.run(discover_all_exchange_markets(fake))
    # BTC/USD, ETH/USD, ADA/USDC pass; XRP/EUR (quote filter),
    # OLD/USD (inactive), ""/USD (blank base) all excluded.
    assert result == [("ADA", "USDC"), ("BTC", "USD"), ("ETH", "USD")]


def test_discover_returns_empty_on_connector_none():
    result = asyncio.run(discover_all_exchange_markets(None))
    assert result == []


def test_build_universe_dispatches_per_discovered_market(tmp_path):
    """v3.24.4 F11 — build_universe fills every discovered market
    on the exchange, skipping any without a wired adapter."""
    from types import SimpleNamespace

    reg = StoneTabletsRegistry(root=tmp_path)

    async def _get_markets():
        return [
            SimpleNamespace(base="BTC", quote="USD", active=True),
            SimpleNamespace(base="ETH", quote="USDC", active=True),
        ]

    fake_conn = SimpleNamespace()
    fake_conn.get_markets = _get_markets
    adapter = _FakeAdapter([])
    adapter.exchange_id = "fake"
    orch = BuildOrchestrator(
        registry=reg,
        adapters_by_exchange={"fake": adapter},
        discovery=TargetAssetDiscovery(),
    )
    until = _START_MS + 14 * STEP_5M_MS
    report = asyncio.run(
        orch.build_universe(
            exchange_id="fake", connector=fake_conn, since_ms=_START_MS, until_ms=until
        )
    )
    assets = sorted(r.asset for r in report.reports)
    assert assets == ["BTC", "ETH"]
    assert report.total_candles > 0


def test_first_time_generation_flow(tmp_path):
    """Operator directive 2026-08-01: 'if a Stone Tablet does not
    exist for a simulated and back tested asset then one will be
    generated.' Verify the flow: registry empty for asset -->
    missing_ranges returns full window --> GapFiller walks chunks
    --> tablet created + populated."""
    reg = StoneTabletsRegistry(root=tmp_path)
    adapter = _FakeAdapter([])
    filler = GapFiller(reg, adapter)
    until = _START_MS + 24 * STEP_5M_MS
    # Registry has NO tablet for this asset — first-time generation
    assert not reg.has_coverage("BRANDNEW", _START_MS, until, exchange_id="fake")
    report = asyncio.run(filler.fill_asset("BRANDNEW", _START_MS, until))
    assert report.candles_appended > 0
    # After: coverage exists
    assert len(reg.coverage_summary()) >= 1
    branded = [c for c in reg.coverage_summary() if c.asset == "BRANDNEW"]
    assert branded
    assert branded[0].exchange_id == "fake"


def test_gap_filler_fetches_a_hole_between_two_covered_runs(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    covered = [0, 1, 2, 20, 21, 22]
    reg.ingest_candles(
        asset="HOLE",
        timeframe=NATIVE_TIMEFRAME,
        rows=[
            [_START_MS + i * STEP_5M_MS, 100.0, 101.0, 99.0, 100.5, 5.0]
            for i in covered
        ],
        source="test",
        exchange_id="fake",
    )
    until = _START_MS + 22 * STEP_5M_MS
    hole = (_START_MS + 3 * STEP_5M_MS, _START_MS + 19 * STEP_5M_MS)
    seen = reg.missing_ranges("HOLE", _START_MS, until, exchange_id="fake")
    assert seen == [hole], f"the interior hole was not reported: {seen}"

    adapter = _FakeAdapter([])
    report = asyncio.run(GapFiller(reg, adapter).fill_asset("HOLE", _START_MS, until))

    assert report.gaps_requested == 1, f"expected one gap, got {report.gaps_requested}"
    assert adapter.calls, "the adapter was never asked for the hole"
    assert adapter.calls[0][0] == hole[0], (
        f"first request started at {adapter.calls[0][0]}, "
        f"not at the first missing step {hole[0]}"
    )
    left = reg.missing_ranges("HOLE", _START_MS, until, exchange_id="fake")
    assert left == [], f"the window is still short after the fill: {left}"
