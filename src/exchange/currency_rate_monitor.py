"""currency_rate_monitor.py — persistent BTC/USD + ETH/USD rate feed.

Also derives satoshi- and wei-denominated equivalents used across the
GUI to give operators granular price awareness (per operator directive
2026-07-27, see docs/audits/2026-07-27_interop_usd_denom_settlement_audit_and_design.md
§ 3.3).

Sourcing:
    Any connected exchange connector — polls ``get_ticker('BTC/USD')``
    and ``get_ticker('ETH/USD')`` on a 60 s cadence. Rate-limited
    against the connector's own executor (MEM-220). Snapshot cached
    in memory; readers pull via ``snapshot()``.

Consumers (v3.23.41):
    * ``IndicatorVotingPanel.update_currency_rates()`` — header row.

Derived rates:
    * ``sat_per_dollar = 100_000_000 / (BTC/USD)``
    * ``sat_per_cent   = 1_000_000   / (BTC/USD)``
    * ``wei_per_dollar = 1e18 / (ETH/USD)``
    * ``wei_per_cent   = 1e16 / (ETH/USD)``

Not persisted — a fresh process starts with an empty snapshot and
populates on the first successful poll.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.currency_rate_monitor")

DEFAULT_REFRESH_SECONDS = 60.0
SATOSHI_PER_BTC = 100_000_000            # 1 BTC = 1e8 satoshi
WEI_PER_ETH = 10 ** 18                   # 1 ETH = 1e18 wei
WEI_PER_GWEI = 10 ** 9                   # 1 gwei = 1e9 wei — v3.23.50


@dataclass
class CurrencyRates:
    """Snapshot of the most recent rate feed."""
    btc_usd: float = 0.0
    eth_usd: float = 0.0
    sat_per_dollar: float = 0.0
    sat_per_cent: float = 0.0
    wei_per_dollar: float = 0.0
    wei_per_cent: float = 0.0
    # v3.23.50 — gwei-per-dollar / gwei-per-cent derived rates. Operator
    # directive 2026-07-28: the raw wei display was scientific-notation-
    # heavy (5.297e+14) which visually suggested more precision than the
    # sat side (1,567). Switching the panel readout to gwei (1e9 wei)
    # matches the sat-shape "big integer with commas" while remaining
    # exact — no rounding, just a base-1e9 rescale.
    gwei_per_dollar: float = 0.0
    gwei_per_cent: float = 0.0
    last_updated: float = 0.0            # epoch seconds
    source: str = "none"                 # exchange id or "cache"/"none"
    error: Optional[str] = None          # last failure text, if any

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
    """Periodic BTC/ETH-USD sampler.

    Not a QThread — the update coroutine is scheduled onto the main
    async loop by the caller (main_window's ``_schedule_async``). The
    monitor itself is pure: no Qt, no timers of its own. Callers do
    the pacing.
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
        # v3.23.50 — gwei-per-* derived from wei-per-* via /1e9.
        gwei_dollar = wei_dollar / WEI_PER_GWEI
        gwei_cent = wei_cent / WEI_PER_GWEI
        return (sat_dollar, sat_cent, wei_dollar, wei_cent,
                gwei_dollar, gwei_cent)

    def update_from_prices(
        self, btc_usd: float, eth_usd: float,
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
                "; ".join(errors) if errors
                else "no connector returned BTC/USD + ETH/USD")
        return self._snapshot


# ---------------------------------------------------------------------
# Process-wide shared monitor
# ---------------------------------------------------------------------

_GLOBAL_MONITOR: Optional[CurrencyRateMonitor] = None


def get_currency_monitor() -> CurrencyRateMonitor:
    global _GLOBAL_MONITOR
    if _GLOBAL_MONITOR is None:
        _GLOBAL_MONITOR = CurrencyRateMonitor()
    return _GLOBAL_MONITOR
