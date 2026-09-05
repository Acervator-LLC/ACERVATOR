"""BTC/USD and ETH/USD rate feed with satoshi, wei and gwei equivalents.

``CurrencyRateMonitor.refresh_from_connectors`` polls ``get_ticker`` on the
first connector answering both pairs, and ``snapshot`` returns the cached
``CurrencyRates``. Readers reach it through ``get_currency_monitor``:
``main_window`` (which feeds ``IndicatorVotingPanel.update_currency_rates``),
``table_cells``, ``table_cells_surface`` and the Live Settings tab.
``CurrencyRates`` is held in memory only and starts empty in a new process.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from .lazy_singleton import LazySingleton

logger = logging.getLogger("acervator.currency_rate_monitor")

DEFAULT_REFRESH_SECONDS = 60.0
SATOSHI_PER_BTC = 100_000_000
WEI_PER_ETH = 10**18
WEI_PER_GWEI = 10**9


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
    source: str = "none"  # exchange id, "manual", or "none"
    error: Optional[str] = None

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
    (``main_window._schedule_async``); the monitor owns no timer and
    ``is_stale`` is its only pacing.
    """

    def __init__(self, refresh_seconds: float = DEFAULT_REFRESH_SECONDS):
        self._refresh_s = float(refresh_seconds)
        self._snapshot = CurrencyRates()

    @property
    def refresh_seconds(self) -> float:
        return self._refresh_s

    def snapshot(self) -> CurrencyRates:
        return self._snapshot

    def is_stale(self, now: Optional[float] = None) -> bool:
        """True when the last snapshot is older than the refresh
        interval (2× tolerance for jitter)."""
        return self._snapshot.age_seconds(now) > (self._refresh_s * 2)

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
        errors: list = []
        btc = 0.0
        eth = 0.0
        source = "none"
        for eid, connector in connectors.items():
            try:
                btc_ticker = await connector.get_ticker("BTC/USD")
                eth_ticker = await connector.get_ticker("ETH/USD")
            except Exception as _exc:  # noqa: BLE001 - per-connector probe
                errors.append(f"{eid}: {_exc}")
                continue
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

_MONITOR: LazySingleton[CurrencyRateMonitor] = LazySingleton(
    CurrencyRateMonitor,
    "the currency rate feed",
    "BTC/USD and ETH/USD, and the satoshi and wei denominated prices "
    "derived from them, will hold their last value and stop updating.",
)


def get_currency_monitor() -> Optional[CurrencyRateMonitor]:
    """Return the shared monitor, or None while the feed is down.

    Never raises. None means skip the currency rates this tick.
    """
    return _MONITOR.get()


def reset_currency_monitor_for_tests() -> None:
    """Clear the singleton and its cooling-off — test-only helper."""
    _MONITOR.reset()
