"""Calibration for the ``LazySingleton`` cooling-off in the shipped getters.

A cached singleton whose construction fails leaves its cache at ``None``, so an
ungated getter re-constructs and re-logs on every GUI tick. Every count below is
taken over ``TICKS`` ticks of ``TICK_SECONDS`` against the shipped getters in
``currency_rate_monitor`` and ``market_pairs_scout``, not a replica.
"""

from __future__ import annotations

import logging

import pytest

from src.exchange import currency_rate_monitor as crm
from src.exchange import market_pairs_scout as mps
from src.exchange.lazy_singleton import LazySingleton

TICKS = 150
TICK_SECONDS = 2.0
#: Attempts the shipped 30 s→300 s backoff allows in 150 ticks.
EXPECTED_ATTEMPTS = 4

LOG_NAME = "acervator.lazy_singleton"


class Clock:
    """Monotonic stand-in the test advances by hand."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def tick(self, seconds: float = TICK_SECONDS) -> None:
        self.t += seconds


def _boom() -> object:
    """Raise the incident's exception."""
    raise TypeError("__init__() should return None, not 'NoneType'")


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def armed():
    """Point a shipped singleton at a test factory and clock, then restore.

    Only the failure and the clock are injected. The feature text, the
    impact text and the 30 s→300 s policy are the shipped ones.
    """
    restore: list[tuple[LazySingleton, object, object]] = []

    def _arm(singleton: LazySingleton, factory, clk) -> LazySingleton:
        restore.append((singleton, singleton._factory, singleton._fault._clock))
        singleton.reset()
        singleton._factory = factory
        singleton._fault._clock = clk
        return singleton

    yield _arm

    for singleton, factory, clk in restore:
        singleton._factory = factory
        singleton._fault._clock = clk
        singleton.reset()


def test_the_replaced_shape_storms_under_this_loop() -> None:
    """A low count from the fixed getter means nothing unless this reads 150."""
    calls = {"n": 0}
    cache = None

    def old_getter():
        nonlocal cache
        if cache is None:
            calls["n"] += 1
            cache = _boom()
        return cache

    for _ in range(TICKS):
        with pytest.raises(TypeError):
            old_getter()

    assert calls["n"] == TICKS


def test_currency_monitor_stops_storming(capture_log, clock, armed) -> None:
    """A count near 150 means the cooling-off does not gate construction."""
    guard = armed(crm._MONITOR, _boom, clock)

    with capture_log(LOG_NAME) as records:
        results = []
        for _ in range(TICKS):
            results.append(crm.get_currency_monitor())
            clock.tick()

    assert len(results) == TICKS
    assert all(r is None for r in results)
    assert guard.constructions == EXPECTED_ATTEMPTS
    assert len(records) == EXPECTED_ATTEMPTS
    assert guard.fault.suppressed_total == TICKS - EXPECTED_ATTEMPTS


def test_scout_stops_storming(capture_log, clock, armed) -> None:
    """A count near 150 means the scout retries at tick rate, as it did live."""
    guard = armed(mps._SCOUT, _boom, clock)

    with capture_log(LOG_NAME) as records:
        results = []
        for _ in range(TICKS):
            results.append(mps.get_scout())
            clock.tick()

    assert len(results) == TICKS
    assert all(r is None for r in results)
    assert guard.constructions == EXPECTED_ATTEMPTS
    assert len(records) == EXPECTED_ATTEMPTS


def test_first_failure_is_an_error_naming_the_feature(
    capture_log,
    clock,
    armed,
) -> None:
    """A DEBUG line, or one carrying only the exception, repeats the incident."""
    armed(crm._MONITOR, _boom, clock)

    with capture_log(LOG_NAME) as records:
        crm.get_currency_monitor()

    assert len(records) == 1
    first = records[0]
    assert first.levelno == logging.ERROR
    message = first.getMessage()
    assert "the currency rate feed" in message
    assert "BTC/USD and ETH/USD" in message
    assert "stop updating" in message
    assert "Trading and order placement are not affected" in message
    assert "__init__() should return None" in message
    assert message != "__init__() should return None, not 'NoneType'"


def test_repeats_are_summaries_not_per_tick_lines(
    capture_log,
    clock,
    armed,
) -> None:
    """Repeats at ERROR, or more than one line per window, are a re-flood."""
    armed(crm._MONITOR, _boom, clock)

    with capture_log(LOG_NAME) as records:
        for _ in range(TICKS):
            crm.get_currency_monitor()
            clock.tick()

    assert [r.levelno for r in records] == [
        logging.ERROR,
        logging.WARNING,
        logging.WARNING,
        logging.WARNING,
    ]
    summary = records[1].getMessage()
    assert "FEATURE STILL OFFLINE" in summary
    assert "call(s) were suppressed" in summary
    # Each window is longer than the last.
    assert "Next retry in 60 s" in summary
    assert "Next retry in 120 s" in records[2].getMessage()


def test_currency_monitor_recovers_and_says_so(
    capture_log,
    clock,
    armed,
) -> None:
    """A failure here means the feature stays dead until the operator restarts."""
    guard = armed(crm._MONITOR, _boom, clock)

    with capture_log(LOG_NAME) as records:
        assert crm.get_currency_monitor() is None
        assert guard.fault.offline is True

        guard._factory = crm.CurrencyRateMonitor
        clock.tick(31.0)
        recovered = crm.get_currency_monitor()

    assert isinstance(recovered, crm.CurrencyRateMonitor)
    assert guard.available is True
    assert crm.get_currency_monitor() is recovered
    assert guard.fault.offline is False

    # The feature is live, not merely non-None.
    recovered.update_from_prices(50_000.0, 3_000.0)
    assert recovered.snapshot().btc_usd == 50_000.0

    assert records[-1].levelno == logging.WARNING
    assert "FEATURE RESTORED" in records[-1].getMessage()
    assert "the currency rate feed" in records[-1].getMessage()


def test_scout_recovers_and_says_so(capture_log, clock, armed) -> None:
    """A failure here means the scout never returns without a restart."""
    guard = armed(mps._SCOUT, _boom, clock)

    with capture_log(LOG_NAME) as records:
        assert mps.get_scout() is None
        guard._factory = mps.MarketPairsScout
        clock.tick(31.0)
        recovered = mps.get_scout()

    assert isinstance(recovered, mps.MarketPairsScout)
    assert "FEATURE RESTORED" in records[-1].getMessage()


def test_normal_path_returns_a_working_monitor(capture_log) -> None:
    """A getter that always returns None never storms either. This separates them."""
    crm.reset_currency_monitor_for_tests()
    try:
        with capture_log(LOG_NAME) as records:
            first = crm.get_currency_monitor()
            second = crm.get_currency_monitor()

        assert isinstance(first, crm.CurrencyRateMonitor)
        assert second is first
        assert crm._MONITOR.constructions == 1
        assert records == []

        first.update_from_prices(60_000.0, 4_000.0)
        snap = first.snapshot()
        assert snap.btc_usd == 60_000.0
        assert snap.eth_usd == 4_000.0
        assert snap.sat_per_dollar == pytest.approx(100_000_000 / 60_000.0)
    finally:
        crm.reset_currency_monitor_for_tests()


def test_normal_path_returns_a_working_scout(capture_log) -> None:
    """A scout getter stuck at None would pass every storm test above."""
    mps.reset_scout_for_tests()
    try:
        with capture_log(LOG_NAME) as records:
            first = mps.get_scout()
            second = mps.get_scout()

        assert isinstance(first, mps.MarketPairsScout)
        assert second is first
        assert mps._SCOUT.constructions == 1
        assert records == []

        first.ingest_tickers(
            "coinbase",
            {
                "BTC/USD": {
                    "symbol": "BTC/USD",
                    "last": 60_000.0,
                    "percentage": 1.5,
                    "quoteVolume": 1_000.0,
                },
            },
        )
        pair = first.get_pair("BTC", "USD", exchange_id="coinbase")
        assert pair is not None
        assert pair.last == 60_000.0
    finally:
        mps.reset_scout_for_tests()


@pytest.mark.parametrize("getter_name", ["currency", "scout"])
def test_getter_never_raises(clock, armed, getter_name: str) -> None:
    """A raise here reaches a GUI pump on a live trading platform."""
    if getter_name == "currency":
        armed(crm._MONITOR, _boom, clock)
        getter = crm.get_currency_monitor
    else:
        armed(mps._SCOUT, _boom, clock)
        getter = mps.get_scout

    for _ in range(TICKS):
        assert getter() is None
        clock.tick()


def test_getter_never_raises_when_the_exception_cannot_be_rendered(
    clock,
    armed,
) -> None:
    """logging re-raises a __str__ that raises; unguarded, that reaches the pump."""

    class Unprintable(Exception):
        def __str__(self) -> str:
            raise MemoryError("no room to format")

    def explode() -> object:
        raise Unprintable

    guard = armed(crm._MONITOR, explode, clock)

    assert crm.get_currency_monitor() is None
    assert guard.fault.offline is True
    assert guard.fault.lost_reports == 0


@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_coin_icon_falls_back_and_stops_storming(
    capture_log,
    clock,
    armed,
    qt_app,
) -> None:
    """A count near 150, or a None icon, means the wizard storms or lost its rows."""
    from src.gui import bot_wizard

    assert qt_app is not None
    guard = armed(bot_wizard._ASSET_MANAGER, _boom, clock)

    with capture_log(LOG_NAME) as records:
        icons = []
        for _ in range(TICKS):
            icons.append(bot_wizard._get_coin_icon("WLFI"))
            clock.tick()

    assert len(icons) == TICKS
    assert all(icon is not None for icon in icons)
    assert all(not icon.isNull() for icon in icons)
    assert guard.constructions == EXPECTED_ATTEMPTS
    assert len(records) == EXPECTED_ATTEMPTS
    assert records[0].levelno == logging.ERROR
    assert "coin icons" in records[0].getMessage()
    assert "lettered circle" in records[0].getMessage()


def test_coin_icon_normal_path_builds_a_manager(capture_log, qt_app) -> None:
    """An always-None manager would pass the storm test above."""
    from src.gui import bot_wizard

    assert qt_app is not None
    bot_wizard._ASSET_MANAGER.reset()
    try:
        with capture_log(LOG_NAME) as records:
            icon = bot_wizard._get_coin_icon("BTC", download=False)

        assert icon is not None
        assert not icon.isNull()
        assert bot_wizard._ASSET_MANAGER.available is True
        assert bot_wizard._ASSET_MANAGER.constructions == 1
        assert records == []
    finally:
        bot_wizard._ASSET_MANAGER.reset()


def test_icon_load_failure_is_throttled_too(capture_log, clock, qt_app) -> None:
    """Per-symbol logo failures at DEBUG per tick are the same flood, renamed."""
    from src.gui import bot_wizard

    assert qt_app is not None

    class Manager:
        def get_logo_path(self, symbol):
            raise OSError(f"logo cache unreadable for {symbol}")

    fault = bot_wizard._ICON_LOAD_FAULT
    prior_clock = fault._clock
    bot_wizard._ASSET_MANAGER.reset()
    try:
        fault.reset()
        fault._clock = clock
        bot_wizard._ASSET_MANAGER._instance = Manager()

        with capture_log(LOG_NAME) as records:
            icons = []
            for _ in range(TICKS):
                icons.append(bot_wizard._get_coin_icon("WLFI"))
                clock.tick()

        assert all(icon is not None and not icon.isNull() for icon in icons)
        assert len(records) == EXPECTED_ATTEMPTS
        assert records[0].levelno == logging.ERROR
        assert "coin icon loading" in records[0].getMessage()
        assert "logo cache unreadable" in records[0].getMessage()
    finally:
        fault._clock = prior_clock
        fault.reset()
        bot_wizard._ASSET_MANAGER.reset()


def test_a_flapping_feature_does_not_emit_per_tick(capture_log, clock) -> None:
    """Without the window floor, alternating failure and recovery floods at 0.5 Hz."""
    from src.exchange.lazy_singleton import ThrottledFault

    fault = ThrottledFault("a flapping feed", "Readings stall.", clock=clock)
    window_ticks = int(30.0 / TICK_SECONDS)

    with capture_log(LOG_NAME) as records:
        for i in range(TICKS):
            if i % 2 == 0:
                fault.note_failure(RuntimeError("flap"))
            else:
                fault.note_success()
            clock.tick()

    assert len(records) <= TICKS // window_ticks + 1
    assert fault.failures_total == TICKS // 2
