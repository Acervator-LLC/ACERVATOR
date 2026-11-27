"""BTC/USD and ETH/USD rate feed with satoshi, wei and gwei equivalents.

``CurrencyRateMonitor.refresh_from_connectors`` polls ``get_ticker`` on the
first connector answering both pairs, and ``snapshot`` returns the cached
``CurrencyRates``. Readers reach it through ``get_currency_monitor``:
``main_window`` (which feeds ``IndicatorVotingPanel.update_currency_rates``),
``table_cells``, ``table_cells_surface`` and the Live Settings tab.
``CurrencyRates`` is held in memory only and starts empty in a new process.

A replacement built for a stopped feed takes the previous reading through
``_carry_rates``, so the strip and the Target-denom cells keep their last
figures. ``_carry_rates`` sets that reading's ``held``, and its ``source``
stays the venue name the strip draws.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, replace
from typing import Optional

from .lazy_singleton import LazySingleton

logger = logging.getLogger("acervator.currency_rate_monitor")

DEFAULT_REFRESH_SECONDS = 60.0
NO_FEED_RATES_ERROR = "the public feed returned no BTC/USD + ETH/USD price"
SATOSHI_PER_BTC = 100_000_000
WEI_PER_ETH = 10**18
WEI_PER_GWEI = 10**9
NO_SOURCE = "none"


@dataclass
class CurrencyRates:
    """Snapshot of the most recent rate feed."""

    btc_usd: float = 0.0
    eth_usd: float = 0.0
    sat_per_dollar: float = 0.0
    sat_per_cent: float = 0.0
    wei_per_dollar: float = 0.0
    wei_per_cent: float = 0.0
    gwei_per_dollar: float = 0.0
    gwei_per_cent: float = 0.0
    last_updated: float = 0.0  # epoch seconds
    source: str = NO_SOURCE  # exchange id, "manual", or NO_SOURCE
    error: Optional[str] = None
    held: bool = False  # True on a reading _carry_rates moved onto a rebuilt monitor

    def age_seconds(self, now: Optional[float] = None) -> float:
        _now = time.time() if now is None else now
        if self.last_updated <= 0:
            return float("inf")
        return max(0.0, _now - self.last_updated)

    def has_btc(self) -> bool:
        return self.btc_usd > 0.0

    def has_eth(self) -> bool:
        return self.eth_usd > 0.0


class CurrencyRateMonitor:
    """BTC/ETH-USD sampler holding one ``CurrencyRates`` snapshot.

    ``refresh_from_connectors`` is a coroutine the caller schedules
    (``main_window._schedule_coalesced``); the monitor owns no timer and
    ``is_stale`` is its only pacing.
    """

    def __init__(self, refresh_seconds: float = DEFAULT_REFRESH_SECONDS):
        self._refresh_s = float(refresh_seconds)
        self._snapshot = CurrencyRates()
        #: True while ``refresh_from_feed`` waits on its two ticker reads.
        self._feed_asking = False
        #: Connectors ``refresh_from_connectors`` waits on now.
        self._reads_on_way = 0
        #: Epoch seconds of the first read asked since the last answer; 0.0 once answered.
        self._unanswered_since = 0.0

    @property
    def refresh_seconds(self) -> float:
        return self._refresh_s

    @property
    def reading(self) -> bool:
        """True while either refresh waits on its source."""
        return self._feed_asking or self._reads_on_way > 0

    def snapshot(self) -> CurrencyRates:
        return self._snapshot

    def hold_reading(self, reading: CurrencyRates) -> CurrencyRates:
        """Adopt ``reading`` as this monitor's snapshot, with no poll.

        ``_carry_rates`` calls it so a replacement monitor starts from the
        stopped one's ``CurrencyRates`` instead of zeros.
        """
        self._snapshot = reading
        return self._snapshot

    def is_stale(self, now: Optional[float] = None) -> bool:
        """True when the last snapshot is older than the refresh
        interval (2× tolerance for jitter)."""
        return self._snapshot.age_seconds(now) > (self._refresh_s * 2)

    def has_stopped(self, now: Optional[float] = None) -> bool:
        """True when no read is ``reading`` and reads asked over ``refresh_seconds`` ago have no answer."""
        if self.reading or self._unanswered_since <= 0:
            return False
        _now = time.time() if now is None else now
        return _now - self._unanswered_since > self._refresh_s

    def _note_asked(self) -> None:
        """Start ``_unanswered_since`` at the first read asked since the last answer."""
        if self._unanswered_since <= 0:
            self._unanswered_since = time.time()

    @staticmethod
    def _derive(btc_usd: float, eth_usd: float) -> tuple:
        """Compute the sat/wei/gwei derived rates. Safe against 0-input."""
        sat_dollar = SATOSHI_PER_BTC / btc_usd if btc_usd > 0 else 0.0
        sat_cent = sat_dollar * 0.01
        wei_dollar = WEI_PER_ETH / eth_usd if eth_usd > 0 else 0.0
        wei_cent = wei_dollar * 0.01
        gwei_dollar = wei_dollar / WEI_PER_GWEI
        gwei_cent = wei_cent / WEI_PER_GWEI
        return (sat_dollar, sat_cent, wei_dollar, wei_cent, gwei_dollar, gwei_cent)

    def update_from_prices(
        self,
        btc_usd: float,
        eth_usd: float,
        source: str = "manual",
        now: Optional[float] = None,
    ) -> CurrencyRates:
        """Manually apply BTC/ETH USD prices (for tests / cache re-hydrate).

        Real callers use ``refresh_from_connectors`` instead.
        """
        sd, sc, wd, wc, gd, gc = self._derive(btc_usd, eth_usd)
        self._unanswered_since = 0.0
        self._snapshot = CurrencyRates(
            btc_usd=float(btc_usd),
            eth_usd=float(eth_usd),
            sat_per_dollar=sd,
            sat_per_cent=sc,
            wei_per_dollar=wd,
            wei_per_cent=wc,
            gwei_per_dollar=gd,
            gwei_per_cent=gc,
            last_updated=time.time() if now is None else now,
            source=source,
            error=None,
        )
        return self._snapshot

    async def refresh_from_feed(self, feed, force: bool = False) -> CurrencyRates:
        """Read BTC/USD and ETH/USD through ``feed.ticker`` on a worker thread.

        ``feed`` is a keyless public source such as ``LiveFeedSource``; a fresh snapshot, or ``_feed_asking``, keeps it.
        """
        if self._feed_asking or (not force and not self.is_stale()):
            return self._snapshot
        self._note_asked()
        self._feed_asking = True
        try:
            btc = await asyncio.to_thread(feed.ticker, "BTC/USD")
            eth = await asyncio.to_thread(feed.ticker, "ETH/USD")
        finally:
            self._feed_asking = False
        if btc and eth and btc > 0 and eth > 0:
            return self.update_from_prices(btc, eth, source=str(feed.venue()))
        self._snapshot.error = NO_FEED_RATES_ERROR
        return self._snapshot

    async def refresh_from_connectors(
        self, connectors: dict, force: bool = False
    ) -> CurrencyRates:
        """Poll the first connector able to answer BTC/USD + ETH/USD.

        Silently skips a refresh if the previous snapshot is still
        fresh (unless ``force=True``). Returns the current snapshot.
        """
        if not connectors:
            self._snapshot.error = "no exchange connectors attached"
            return self._snapshot
        if not force and not self.is_stale():
            return self._snapshot
        self._note_asked()
        errors: list = []
        btc = 0.0
        eth = 0.0
        source = "none"
        for eid, connector in connectors.items():
            self._reads_on_way += 1
            try:
                btc_ticker = await connector.get_ticker("BTC/USD")
                eth_ticker = await connector.get_ticker("ETH/USD")
            except Exception as _exc:  # noqa: BLE001 - per-connector probe
                errors.append(f"{eid}: {_exc}")
                continue
            finally:
                self._reads_on_way -= 1
            btc = float(getattr(btc_ticker, "last", 0) or 0)
            eth = float(getattr(eth_ticker, "last", 0) or 0)
            if btc > 0 and eth > 0:
                source = eid
                break
        if btc > 0 and eth > 0:
            self.update_from_prices(btc, eth, source=source)
        else:
            self._snapshot.error = (
                "; ".join(errors)
                if errors
                else "no connector returned BTC/USD + ETH/USD"
            )
        return self._snapshot


# Process-wide shared monitor


def _monitor_has_stopped(monitor: CurrencyRateMonitor) -> bool:
    """True when ``monitor`` holds a reading and ``CurrencyRateMonitor.has_stopped`` reports it.

    ``_MONITOR`` passes this as ``has_stopped``, and a monitor whose
    ``last_updated`` is still zero is never reported stopped.
    """
    return monitor.snapshot().last_updated > 0 and monitor.has_stopped()


def _carry_rates(
    previous: CurrencyRateMonitor, replacement: CurrencyRateMonitor
) -> None:
    """Move ``previous``'s ``CurrencyRates`` onto ``replacement`` with ``held`` set.

    ``_MONITOR`` passes this as ``carry_reading``; a monitor whose
    ``last_updated`` is still zero carries nothing.
    """
    reading = previous.snapshot()
    if reading.last_updated <= 0:
        return
    replacement.hold_reading(replace(reading, held=True))


_MONITOR: LazySingleton[CurrencyRateMonitor] = LazySingleton(
    CurrencyRateMonitor,
    "the currency rate feed",
    "BTC/USD and ETH/USD, and the satoshi and wei denominated prices "
    "derived from them, will hold their last value and stop updating.",
    has_stopped=_monitor_has_stopped,
    carry_reading=_carry_rates,
)


def get_currency_monitor() -> Optional[CurrencyRateMonitor]:
    """Return the shared monitor, or None while the feed is down.

    Never raises. None means skip the currency rates this tick.
    """
    return _MONITOR.get()


def reset_currency_monitor_for_tests() -> None:
    """Clear the singleton and its cooling-off — test-only helper."""
    _MONITOR.reset()
