"""market_pairs_scout.py — per-exchange multi-pair rate scout.

Sibling of ``currency_rate_monitor``. Where the currency monitor gives
BTC/USD + ETH/USD spot rates for the whole GUI, this scout gives every
trading pair the exchange lists, grouped by base asset, so callers can
ask "what pairs trade ETH on this exchange right now, and how are they
moving?".

Introduced 2026-07-28 as v3.23.47 in the multi-base coordination
cascade (see docs/audits/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md
§ 6, Cascade #2). Delivers the **read-only** cross-pair awareness that
the ScrummingBot needs before any smart-routing conversation can start.
The prior-art research
(docs/audits/2026-07-28_prior_art_multibase_coordination_research.md
§ 3) explicitly warned that DEX-pathfinder patterns are a category
error for a persistent-inventory scrumming bot — this module deliberately
does **not** rank / pick / route. It observes.

Sourcing:
    ``connector.get_all_tickers()`` — one bulk CCXT call per exchange
    per refresh cycle. On Coinbase this is the correct primitive
    (ccxt issue #26170: ``fetch_ticker`` vs ``fetch_tickers`` return
    different shapes; always use tickers-plural here for consistency).

Consumers (planned):
    * ScrummingBot — reads ``pairs_for(target_asset)`` in the tick to
      log divergence and, in a future cascade, potentially route.
    * Bot Details Status tab — renders "Target BTC / Target ETH"
      rows + Δ24h vs USD % (v3.23.48).
    * Any future calibration harness that wants historical spread /
      volume / drift per pair (data collected here in advance).

Not persisted — a fresh process starts with an empty snapshot and
populates on the first successful poll.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.market_pairs_scout")

DEFAULT_REFRESH_SECONDS = 10.0  # per prior-art research § 6.2


@dataclass
class PairSnapshot:
    """One trading pair on one exchange at one moment.

    Fields chosen so the same struct powers both the v3.23.48 GUI
    rendering AND any future Approach-B calibration work (spread,
    volume, drift are all here).
    """

    symbol: str  # e.g. "ETH/BTC"
    base: str  # e.g. "ETH"
    quote: str  # e.g. "BTC"
    last: float = 0.0  # last trade price, in quote units per base
    pct_24h: float = 0.0  # 24h % change, from ccxt ticker.percentage
    bid: float = 0.0  # best-bid price (quote per base)
    ask: float = 0.0  # best-ask price (quote per base)
    volume_24h: float = 0.0  # 24h base-unit volume
    exchange_id: str = ""
    last_updated: float = 0.0

    @property
    def spread(self) -> float:
        """Absolute quote-price spread (ask - bid); 0 when either is
        missing. Prefer ``spread_pct`` for cross-pair comparisons."""
        if self.ask <= 0 or self.bid <= 0:
            return 0.0
        return max(0.0, self.ask - self.bid)

    @property
    def spread_pct(self) -> float:
        """Spread as a percentage of mid, or 0 when unavailable."""
        if self.ask <= 0 or self.bid <= 0:
            return 0.0
        mid = 0.5 * (self.ask + self.bid)
        if mid <= 0:
            return 0.0
        return 100.0 * (self.ask - self.bid) / mid

    def age_seconds(self, now: Optional[float] = None) -> float:
        _now = time.time() if now is None else now
        if self.last_updated <= 0:
            return float("inf")
        return max(0.0, _now - self.last_updated)

    def usd_per_base(self, btc_usd: float, eth_usd: float) -> float:
        """Convert this pair's ``last`` into USD-per-base-unit.

        Uses the currency-rate-monitor's BTC/USD + ETH/USD as external
        reference for non-USD quote currencies. Returns 0 when the
        conversion cannot be computed (unknown quote + no known rate).
        """
        q = (self.quote or "").upper()
        if q in ("USD", "USDC", "USDT", "DAI"):
            return float(self.last or 0.0)
        if q == "BTC" and btc_usd > 0:
            return float(self.last or 0.0) * btc_usd
        if q == "ETH" and eth_usd > 0:
            return float(self.last or 0.0) * eth_usd
        return 0.0


class MarketPairsScout:
    """Per-exchange multi-pair rate scout.

    Not a QThread — pure Python. Caller (main_window / test harness)
    schedules ``refresh_from_connectors`` at ``refresh_seconds`` cadence.
    """

    def __init__(self, refresh_seconds: float = DEFAULT_REFRESH_SECONDS):
        self._refresh_s = float(refresh_seconds)
        # exchange_id -> { symbol -> PairSnapshot }
        self._snapshots: dict[str, dict[str, PairSnapshot]] = {}
        # exchange_id -> epoch_seconds of last successful poll
        self._last_refresh: dict[str, float] = {}
        # exchange_id -> last error message (kept for diagnostic display)
        self._last_error: dict[str, Optional[str]] = {}

    @property
    def refresh_seconds(self) -> float:
        return self._refresh_s

    def pairs_for(
        self,
        asset: str,
        exchange_id: Optional[str] = None,
    ) -> list[PairSnapshot]:
        """All pairs whose BASE == asset. If ``exchange_id`` is given,
        restrict to that exchange; otherwise merge across all
        exchanges the scout has polled. Deterministic order: symbol
        ascending.
        """
        _asset = (asset or "").upper()
        if not _asset:
            return []
        out: list[PairSnapshot] = []
        if exchange_id is not None:
            book = self._snapshots.get(exchange_id, {})
            out.extend(s for s in book.values() if s.base == _asset)
        else:
            for book in self._snapshots.values():
                out.extend(s for s in book.values() if s.base == _asset)
        out.sort(key=lambda s: s.symbol)
        return out

    def quote_currencies_for(
        self,
        asset: str,
        exchange_id: Optional[str] = None,
    ) -> list[str]:
        """Return the unique quote currencies (uppercased) for the
        given base asset across polled exchanges. Order deterministic.
        """
        return sorted({s.quote for s in self.pairs_for(asset, exchange_id)})

    def has_pair(
        self,
        base: str,
        quote: str,
        exchange_id: Optional[str] = None,
    ) -> bool:
        _b = (base or "").upper()
        _q = (quote or "").upper()
        for s in self.pairs_for(_b, exchange_id):
            if s.quote == _q:
                return True
        return False

    def get_pair(
        self,
        base: str,
        quote: str,
        exchange_id: Optional[str] = None,
    ) -> Optional[PairSnapshot]:
        _b = (base or "").upper()
        _q = (quote or "").upper()
        for s in self.pairs_for(_b, exchange_id):
            if s.quote == _q:
                return s
        return None

    def last_refresh(self, exchange_id: str) -> float:
        return float(self._last_refresh.get(exchange_id, 0.0))

    def last_error(self, exchange_id: str) -> Optional[str]:
        return self._last_error.get(exchange_id)

    def is_stale(
        self,
        exchange_id: str,
        now: Optional[float] = None,
    ) -> bool:
        """True when the exchange's last refresh was longer than
        2 × ``refresh_seconds`` ago (or never)."""
        _now = time.time() if now is None else now
        last = self.last_refresh(exchange_id)
        if last <= 0:
            return True
        return (_now - last) > (self._refresh_s * 2)

    # -------------------------------------------------------------
    # Ingest — either directly from a raw tickers dict (tests) or
    # by polling a set of connectors (production).
    # -------------------------------------------------------------

    def ingest_tickers(
        self,
        exchange_id: str,
        tickers: dict,
        now: Optional[float] = None,
    ) -> int:
        """Fold a raw CCXT ``fetch_tickers`` dict into the snapshot.

        Returns the number of pairs recorded. Tolerates partial /
        malformed rows silently (per-row exceptions logged at DEBUG,
        the good rows still make it in).
        """
        _now = time.time() if now is None else now
        book: dict[str, PairSnapshot] = {}
        good = 0
        for symbol, row in (tickers or {}).items():
            try:
                if not symbol or "/" not in symbol:
                    continue
                base, quote = symbol.split("/", 1)
                base = base.upper()
                quote = quote.upper()
                last = float(row.get("last", 0) or 0)
                if last <= 0:
                    # some Coinbase products list without last trade
                    last = float(row.get("close", 0) or 0)
                bid = float(row.get("bid", 0) or 0)
                ask = float(row.get("ask", 0) or 0)
                pct = float(row.get("percentage", 0) or 0)
                vol = float(row.get("baseVolume", 0) or 0)
                snap = PairSnapshot(
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    last=last,
                    pct_24h=pct,
                    bid=bid,
                    ask=ask,
                    volume_24h=vol,
                    exchange_id=exchange_id,
                    last_updated=_now,
                )
                book[symbol] = snap
                good += 1
            except Exception as _row_exc:  # noqa: BLE001 - per-row best-effort
                logger.debug(
                    "MarketPairsScout: skip row %s on %s (%s)",
                    symbol,
                    exchange_id,
                    _row_exc,
                )
        self._snapshots[exchange_id] = book
        self._last_refresh[exchange_id] = _now
        self._last_error[exchange_id] = None
        return good

    async def refresh_from_connectors(
        self,
        connectors: dict,
        force: bool = False,
    ) -> dict[str, int]:
        """Poll ``get_all_tickers`` on each connector, ingest results.

        Returns ``{exchange_id: pair_count}`` for each connector that
        answered. Connectors that fail are logged and their previous
        snapshot is retained (better stale than empty).

        Skips per-exchange refresh when the last snapshot is still
        fresh unless ``force=True``.
        """
        out: dict[str, int] = {}
        if not connectors:
            return out
        for eid, connector in connectors.items():
            if not force and not self.is_stale(eid):
                out[eid] = len(self._snapshots.get(eid, {}))
                continue
            try:
                raw = await connector.get_all_tickers()
                out[eid] = self.ingest_tickers(eid, raw)
            except Exception as _conn_exc:  # noqa: BLE001 - per-connector probe
                self._last_error[eid] = f"{type(_conn_exc).__name__}: {_conn_exc}"
                out[eid] = len(self._snapshots.get(eid, {}))
                logger.debug(
                    "MarketPairsScout: connector %s refresh failed: %s", eid, _conn_exc
                )
        return out


# ---------------------------------------------------------------------
# Process-wide shared scout
# ---------------------------------------------------------------------

_GLOBAL_SCOUT: Optional[MarketPairsScout] = None


def get_scout() -> MarketPairsScout:
    global _GLOBAL_SCOUT
    if _GLOBAL_SCOUT is None:
        _GLOBAL_SCOUT = MarketPairsScout()
    return _GLOBAL_SCOUT


def reset_scout_for_tests() -> None:
    """Clear the module singleton — test-only helper."""
    global _GLOBAL_SCOUT
    _GLOBAL_SCOUT = None
