"""Base-currency Extractor: the multi-pair, multi-target inversion of ScrummingBot.

Where ScrummingBot anchors to a TARGET BALANCE of an *alt* asset and
grows USD value through volatility, the Extractor anchors to a POOL of
a *base* asset and grows BASE UNIT COUNT through volatility: it pulls
a fixed USD slice of the base currency, buys into an alt pair during a
dip, sells back during a rally, and returns more base than it spent.
It runs many alt pairs concurrently.

STATE MACHINE (per pair)
────────────────────────
    PENDING ──bearish─→ IN_FLIGHT ──bullish exit──→ PENDING
                            │              (gain locks to pool)
                            ↓
                        DRAWDOWN ──recovery──→ IN_FLIGHT

ExtractorBots do not spawn child bots; multi-asset reach comes from
this bot's own top-N watch-list scan, not from spawn cascades.

Depends on ``sum_sibling_base_currency_claims`` (claim-aware
base-currency capacity check), ``verify_buy_safe_or_refuse`` in
``buy_safety.py`` (fail-closed state-vs-exchange check on every
artillery buy), and ``TASignalProvider`` in
``ta_signal_provider.py`` (one per bot, evaluated per pair per tick).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ..exchange.base import OrderType
from .bot_container import (
    DOLLAR_PEGGED_CURRENCIES,
    BotContainer,
    BotConfig,
    BotMode,
)
from .buy_safety import verify_buy_safe_or_refuse
from .phantom_balance import TIMEFRAME_SECONDS
from .ta_signal_provider import TASignalProvider, TASnapshot

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

logger = logging.getLogger("acervator.extractor")


# Percent-to-ratio conversion factor used by update_usd_per_base_rate().
PERCENT_PER_RATIO_UNIT = 100.0

POSITION_STATE_PENDING = "pending"  # (transitional — never persisted on a Position)
POSITION_STATE_IN_FLIGHT = "in_flight"
POSITION_STATE_DRAWDOWN = "drawdown"
POSITION_STATE_BULLISH_EXIT = "bullish_exit"


# Only ARBITER_SIBLING closes a tranche today; ARBITER_PARENT records an intention.
ARBITER_PARENT = "parent"
ARBITER_SIBLING = "sibling"

ARBITER_LABELS = {
    ARBITER_PARENT: "Parent",
    ARBITER_SIBLING: "Sibling",
}


def normalize_arbiter(value: object) -> str:
    """Coerce any value to exactly one of the two arbiter values.

    Only the exact string ``"parent"`` (stripped, lower-cased) reads as
    ``ARBITER_PARENT``; everything else, including a non-string, reads
    as ``ARBITER_SIBLING``. Never raises: `import_state` calls this per
    restored position, and a raise there would drop the whole record.
    """
    if not isinstance(value, str):
        return ARBITER_SIBLING
    text = value.strip().lower()
    return ARBITER_PARENT if text == ARBITER_PARENT else ARBITER_SIBLING


def arbiter_label(value: object) -> str:
    """Return the operator-facing word: ``Parent`` or ``Sibling``."""
    return ARBITER_LABELS[normalize_arbiter(value)]


def other_arbiter(value: object) -> str:
    """Return the value a toggle moves to. Two values, so a flip."""
    normalized = normalize_arbiter(value)
    return ARBITER_SIBLING if normalized == ARBITER_PARENT else ARBITER_PARENT


@dataclass
class ExtractorPosition:
    """One artillery round in flight against a pair.

    Exactly one active ExtractorPosition exists per pair. Created on
    artillery fire (PENDING to IN_FLIGHT) and removed once the exit
    sells the alt units back to base.
    """

    pair: str
    state: str

    # Original entry — base-units AND USD reference, captured at firing time
    artillery_size_base: float
    artillery_size_usd_at_entry: float

    # Current position state
    alt_units: float
    entry_price_base_per_alt: float
    avg_buy_price_base_per_alt: float
    cost_basis_base: float

    opened_at: float = 0.0

    # Zero means never priced, not a price of zero.
    last_price_base_per_alt: float = 0.0
    last_priced_at: float = 0.0

    # Who may close this tranche: ARBITER_PARENT or ARBITER_SIBLING.
    arbiter: str = ARBITER_SIBLING


class ExtractorBot(BotContainer):
    """Multi-pair base-currency Extractor.

    Implements the per-tick logic described in the module docstring.
    Does not spawn child bots and never registers with the MR
    Inspector spawn controller; multi-asset reach comes from the
    within-bot top-N watch list, not from spawning.
    """

    DEFAULT_TIMEFRAME = "1h"

    def __init__(
        self,
        config: BotConfig,
        exchange: ExchangeInterface,
        enable_phantoms: bool = False,  # Extractor does not use phantoms
    ) -> None:
        # A raise, not an assert, since assert is stripped under
        # python -O. Same guard shape as ScrummingBot.__init__.
        if config.mode != BotMode.EXTRACTOR:
            raise ValueError(
                f"ExtractorBot requires BotMode.EXTRACTOR; " f"got {config.mode!r}"
            )
        super().__init__(config, exchange)

        # Stored only: the Extractor runs no phantom logic.
        self._phantoms_enabled = bool(enable_phantoms)

        # Sized from the assigned chunk, never from exchange.get_balance.
        self._chunk_size_usd: float = float(config.extractor_chunk_size_usd)
        self._usd_per_base_rate: float = 1.0  # dollars per base unit; set externally
        self._chunk_size_base: float = self._chunk_size_usd  # rebased when rate is set
        self._chunk_free_base: float = self._chunk_size_base
        self._chunk_extracted_total: float = 0.0  # cumulative base extracted

        # update_usd_per_base_rate falls back to this window's median on a spike.
        self._recent_rates: list[float] = []  # last 3 accepted rates
        self._rate_spike_threshold_pct: float = 10.0
        self._rate_spike_window: int = 3
        self._rate_spike_events: int = 0  # diagnostic counter
        self._rate_refuse_events: int = 0  # zero/negative rate refusals

        # Set via set_bot_manager(); when None, profit credits don't
        # notify the registry.
        self._bot_manager = None

        # ── Positions (one per pair, keyed by pair symbol) ──
        self._positions: dict[str, ExtractorPosition] = {}
        self._closed_position_log: list[dict] = []  # last 200 closed
        self._closed_log_max: int = 200

        # ── Top-N watch list ──
        self._watch_list: list[str] = []
        # Zero means never refreshed, so the first tick is always due.
        self._watch_list_refreshed_at: float = 0.0
        # Stamped before the price read, so a failing venue cannot retry per tick.
        self._rate_read_at: float = 0.0
        self._tick_counter: int = 0

        # ── TA signal provider (one per bot; reused across pairs) ──
        # _timeframe lengths a candle for _candle_seconds, which sizes the
        # watch-list refresh.
        self._timeframe: str = (
            getattr(config, "ta_timeframe", self.DEFAULT_TIMEFRAME)
            or self.DEFAULT_TIMEFRAME
        )
        self._ta_provider = TASignalProvider(
            exchange,
            timeframe=self._timeframe,
        )

        # ── Trade metrics ──
        self._cycle_extracted_total: float = 0.0  # this session
        self._lifetime_extracted_total: float = 0.0

        # Reserved at set_initial_chunk_rate, released at stop(), pulsed each tick.
        self._crr_token: Optional[str] = None

    # ── Public chunk-rate setter ────────────────────────────────────

    def set_initial_chunk_rate(
        self, usd_per_base: float, *, total_holdings: Optional[float]
    ) -> None:
        """Rebase the USD-denominated chunk into base-currency units.

        ``usd_per_base`` is the dollar price of one base unit, the number
        ``BotContainer._usd_per_base_for`` returns:
        ``chunk_size_base = chunk_size_usd / usd_per_base``.

        ``total_holdings`` is this bot's base-currency balance, read by
        ``_read_base_holdings``. A ``None`` means the balance did not read,
        which is not a holdings figure and not a licence to claim: the chunk
        still rebases, no claim is placed, and one warning names the bot and
        the asset. A figure bounds the claim inside
        ``CapitalReservationRegistry.reserve``.
        """
        if usd_per_base <= 0:
            logger.warning(
                "Bot %s set_initial_chunk_rate: rate %s invalid; "
                "leaving chunk at 1:1 default",
                self.bot_id,
                usd_per_base,
            )
            return
        self._usd_per_base_rate = float(usd_per_base)
        self._chunk_size_base = self._chunk_size_usd / usd_per_base
        self._chunk_free_base = self._chunk_size_base

        # Reserved in asset quantity, not USD; a raising registry leaves this bot unreserved.
        base_asset = (self.config.base_currency or "").upper()
        total_reserved_base = self._chunk_size_base
        if base_asset and total_reserved_base > 0 and total_holdings is None:
            logger.warning(
                "Bot %s could not read its %s balance; placing no claim, "
                "because no holdings figure bounds it.",
                self.bot_id,
                base_asset,
            )
        elif base_asset and total_reserved_base > 0:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_reg = _crr_get_registry()
                self._crr_token = _crr_reg.reserve(
                    bot_id=self.bot_id,
                    asset=base_asset,
                    qty=total_reserved_base,
                    reason=(
                        f"Extractor chunk — "
                        f"chunk_usd=${self._chunk_size_usd:.2f}, "
                        f"usd_per_base={usd_per_base:.6g}"
                    ),
                    bot_kind="extractor",
                    total_holdings=total_holdings,
                )
                logger.info(
                    "Bot %s reserved %.10g %s with "
                    "CapitalReservationRegistry (token %s, "
                    "chunk_usd=$%.2f)",
                    self.bot_id,
                    total_reserved_base,
                    base_asset,
                    self._crr_token[:8] if self._crr_token else "?",
                    self._chunk_size_usd,
                )
            except Exception as _crr_exc:  # fails open: continues without a reservation
                logger.warning(
                    "Bot %s capital reservation at chunk-rate-set "
                    "raised %s: %s — continuing without reservation. "
                    "Concurrent ScrummingBot on %s will NOT see this "
                    "Extractor's claim. Investigate registry state.",
                    self.bot_id,
                    type(_crr_exc).__name__,
                    _crr_exc,
                    base_asset,
                )
                self._crr_token = None
        else:
            # base_currency is allowed to be empty by make_bot_config, and an
            # empty base_asset skips the claim with nothing else said.
            logger.warning(
                "Bot %s placed NO capital reservation: base_currency %r, "
                "chunk %.10g. A concurrent ScrummingBot may spend "
                "these units.",
                self.bot_id,
                base_asset,
                total_reserved_base,
            )

    def set_chunk_size_usd(self, new_value: float) -> dict:
        """Apply a new operator-set Pool Size (USD) to a running bot.

        The routed entry point for a live Pool Size edit. Updates both
        `config.extractor_chunk_size_usd` and the runtime chunk fields
        in lockstep, since neither re-reads the other after
        construction: recomputes `_chunk_size_base` from the current
        `_usd_per_base_rate`, scales `_chunk_free_base` to preserve the
        deployed-vs-free ratio, and resizes the
        CapitalReservationRegistry claim so concurrent ScrummingBots
        see it immediately. Idempotent:
        a no-change call is a clean no-op. Returns ``{"applied": True,
        ...}`` on success, ``{"applied": False, "reason": "..."}``
        on no-op.
        """
        try:
            new_value = float(new_value)
        except (TypeError, ValueError):
            return {"applied": False, "reason": "value not numeric"}
        if new_value <= 0:
            return {"applied": False, "reason": "Pool Size must be > 0"}

        old_usd = float(self._chunk_size_usd)
        if abs(new_value - old_usd) < 1e-9:
            return {"applied": False, "reason": "no change"}

        old_base = float(self._chunk_size_base)
        old_free_base = float(self._chunk_free_base)
        rate = float(self._usd_per_base_rate or 0.0)

        self._chunk_size_usd = new_value
        self.config.extractor_chunk_size_usd = new_value
        if rate > 0:
            new_chunk_base = new_value / rate
        else:
            new_chunk_base = new_value  # 1:1 fallback (pre-rate-set)

        # Preserves the deployed-vs-free ratio across the resize, so
        # the bot doesn't suddenly claim free base units it never earned.
        if old_base > 0:
            free_ratio = old_free_base / old_base
            free_ratio = max(0.0, min(1.0, free_ratio))
            new_free_base = new_chunk_base * free_ratio
        else:
            new_free_base = new_chunk_base
        self._chunk_size_base = new_chunk_base
        self._chunk_free_base = new_free_base

        # Update the registry claim so concurrent SBs see the new
        # number on their next decision tick.
        registry_updated = False
        if self._crr_token is not None:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_reg = _crr_get_registry()
                _crr_reg.update(self._crr_token, self.bot_id, self._chunk_size_base)
                registry_updated = True
            except (
                Exception
            ) as _crr_exc:  # best-effort; in-process state is authoritative
                logger.warning(
                    "Bot %s set_chunk_size_usd: registry update "
                    "raised %s: %s — in-process chunk state is "
                    "still updated, but concurrent ScrummingBot "
                    "will see the OLD claim until heartbeat-driven "
                    "refresh or restart.",
                    self.bot_id,
                    type(_crr_exc).__name__,
                    _crr_exc,
                )

        logger.info(
            "Bot %s Pool Size live-updated: $%.2f → $%.2f "
            "(chunk_base %.10g → %.10g, free_base %.10g → %.10g, "
            "registry_updated=%s)",
            self.bot_id,
            old_usd,
            new_value,
            old_base,
            new_chunk_base,
            old_free_base,
            new_free_base,
            registry_updated,
        )
        return {
            "applied": True,
            "old_usd": old_usd,
            "new_usd": new_value,
            "old_chunk_base": old_base,
            "new_chunk_base": new_chunk_base,
            "registry_updated": registry_updated,
        }

    # ── Lifecycle override: release reservation on stop ─────────────

    async def stop(self) -> None:
        """Release the capital reservation, then delegate to
        BotContainer.stop() for the standard shutdown path.

        If release fails, this logs and continues; the heartbeat-
        staleness pruner in the registry collects the reservation later.
        """
        if self._crr_token is not None:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_reg = _crr_get_registry()
                _crr_reg.release(self._crr_token, self.bot_id)
                logger.info(
                    "Bot %s released capital reservation %s on stop()",
                    self.bot_id,
                    self._crr_token[:8] if self._crr_token else "?",
                )
                self._crr_token = None
            except (
                Exception
            ) as _crr_exc:  # best-effort; heartbeat-staleness pruner is the backstop
                logger.warning(
                    "Bot %s capital reservation release at stop raised "
                    "%s: %s — leaving for heartbeat-staleness prune.",
                    self.bot_id,
                    type(_crr_exc).__name__,
                    _crr_exc,
                )
                # self._crr_token is left set; a restart reserves fresh
                # via set_initial_chunk_rate and this token is pruned by TTL.
        await super().stop()

    # ── Capacity check ──────────────────────────────────────────────

    def _has_chunk_capacity(self, artillery_base: float) -> bool:
        """Return True iff this bot's claim-aware free chunk has room
        for one more artillery round of `artillery_base` base units.

        Other bots' claims are not subtracted here; the cross-bot check
        is enforced by ScrummingBot's own claim-aware quote read.
        """
        return self._chunk_free_base >= artillery_base

    # ── Pool color (for GUI / dashboard) ─────────────────────────────

    def pool_color(self) -> str:
        """Green / yellow / red traffic-light status of the pool.

        green  — no open positions; pool fully in base
        yellow — positions open, none in drawdown
        red    — at least one position below its entry USD value
        """
        if not self._positions:
            return "green"
        for pos in self._positions.values():
            if pos.state == POSITION_STATE_DRAWDOWN:
                return "red"
        return "yellow"

    # ── Watch-list refresh ──────────────────────────────────────────

    async def _refresh_watch_list(self) -> None:
        """Re-rank the top-N ``*/<base>`` pairs by 24h volume.

        Refreshes every ``extractor_scan_refresh_candles`` candles and
        preserves pairs with an open position even if they fall out of
        the new list. If ``exchange.get_markets`` or ``get_ticker``
        raises, the watch list is left as-is.
        """
        base = (self.config.base_currency or "").upper()
        if not base:
            return

        try:
            markets = await self.exchange.get_markets()
        except Exception as exc:  # best-effort refresh
            logger.debug(
                "Bot %s _refresh_watch_list: get_markets raised %s: %s",
                self.bot_id,
                type(exc).__name__,
                exc,
            )
            return

        candidates: list[str] = []
        for m in markets:
            try:
                if not self._pair_filter_matches(m):
                    continue
                m_symbol = getattr(m, "symbol", None) or getattr(m, "id", None)
                if m_symbol:
                    candidates.append(m_symbol)
            except Exception as exc:  # skip malformed market entries
                logger.debug(
                    "Bot %s _refresh_watch_list: market entry "
                    "raised %s: %s — entry skipped, scan continues",
                    self.bot_id,
                    type(exc).__name__,
                    exc,
                )
                continue

        if not candidates:
            return

        # Pull 24h volume for each (best-effort; if a ticker fails,
        # that pair is dropped from THIS refresh and may reappear next).
        ranked: list[tuple[str, float]] = []
        for sym in candidates:
            try:
                ticker = await self.exchange.get_ticker(sym)
                vol = float(getattr(ticker, "volume_24h", 0) or 0)
                ranked.append((sym, vol))
            except Exception as exc:  # per-symbol probe failure
                logger.debug(
                    "Bot %s _refresh_watch_list: get_ticker(%s) raised "
                    "%s: %s — pair dropped from this refresh only",
                    self.bot_id,
                    sym,
                    type(exc).__name__,
                    exc,
                )
                continue

        ranked.sort(key=lambda x: x[1], reverse=True)
        top_n = int(self.config.extractor_scan_top_n)
        top_n = max(5, min(10, top_n))  # clamp to 5-10
        new_watch = [sym for sym, _ in ranked[:top_n]]

        # A pair with an open position stays in the watch even when it leaves the new one.
        for pair in list(self._positions.keys()):
            if pair not in new_watch:
                new_watch.append(pair)

        self._watch_list = new_watch
        self._watch_list_refreshed_at = time.time()

    def _candle_seconds(self) -> float:
        """Seconds in one candle of ``_timeframe``, falling back to
        ``DEFAULT_TIMEFRAME`` for a timeframe ``TIMEFRAME_SECONDS`` does
        not carry.

        ``extractor_scan_refresh_candles`` lengths a candle through this
        method, so the refresh counts candles and never ticks.
        """
        return float(
            TIMEFRAME_SECONDS.get(
                self._timeframe, TIMEFRAME_SECONDS[self.DEFAULT_TIMEFRAME]
            )
        )

    def _refresh_interval_seconds(self) -> float:
        """Seconds in ``extractor_scan_refresh_candles`` candles of ``_timeframe``.

        A candle is a candle of this bot's timeframe, not a tick: the loop
        ticks every ``tick_interval`` seconds whatever the timeframe is.
        """
        candles = int(self.config.extractor_scan_refresh_candles)
        return float(candles) * self._candle_seconds()

    def _watch_list_due_for_refresh(self) -> bool:
        """True once ``_refresh_interval_seconds`` have elapsed since
        ``_watch_list_refreshed_at``."""
        elapsed = time.time() - self._watch_list_refreshed_at
        return elapsed >= self._refresh_interval_seconds()

    # ── USD ↔ base conversion ───────────────────────────────────────

    def _usd_to_base(self, usd: float) -> float:
        """Divide ``usd`` by ``_usd_per_base_rate`` to reach base-currency units."""
        if self._usd_per_base_rate <= 0:
            return 0.0
        return float(usd) / float(self._usd_per_base_rate)

    def _base_to_usd(self, base: float) -> float:
        """Multiply ``base`` by ``_usd_per_base_rate`` to reach USD."""
        return float(base) * float(self._usd_per_base_rate)

    async def _acquire_usd_per_base_rate(self) -> None:
        """Read the base currency's dollar price and route it into the rate.

        A base in ``DOLLAR_PEGGED_CURRENCIES`` takes 1.0 and reads no
        ticker. The first rate on a bot with nothing deployed goes to
        ``set_initial_chunk_rate`` together with the balance
        ``_read_base_holdings`` answers, which rebases ``_chunk_size_base``
        and writes the registry claim; every
        rate after that goes to ``update_usd_per_base_rate``. A read runs no
        more often than ``_refresh_interval_seconds``, whether it succeeds
        or not.
        """
        base = (self.config.base_currency or "").upper()
        if not base:
            return
        if (time.time() - self._rate_read_at) < self._refresh_interval_seconds():
            return
        self._rate_read_at = time.time()
        if base in DOLLAR_PEGGED_CURRENCIES:
            rate = 1.0
        else:
            try:
                ticker = await self.exchange.get_ticker(f"{base}/USD")
                rate = float(ticker.last)
            except Exception as exc:  # the tick must not stop on a price read
                logger.warning(
                    "Bot %s could not read the %s/USD price (%s: %s). The "
                    "dollar-to-base rate stays at %s, so a dollar pool and "
                    "a dollar round are still counted as base units.",
                    self.bot_id,
                    base,
                    type(exc).__name__,
                    exc,
                    self._usd_per_base_rate,
                )
                return
        if rate <= 0:
            logger.warning(
                "Bot %s read a %s/USD price of %r, which cannot be a "
                "price. The dollar-to-base rate stays at %s.",
                self.bot_id,
                base,
                rate,
                self._usd_per_base_rate,
            )
            return
        # set_initial_chunk_rate reserves, so _recent_rates, _tick_counter
        # and _positions together hold it to one call per process.
        if not self._recent_rates and self._tick_counter <= 1 and not self._positions:
            self.set_initial_chunk_rate(
                rate, total_holdings=await self._read_base_holdings(base)
            )
        accepted, reason = self.update_usd_per_base_rate(rate)
        if not accepted:
            logger.info("Bot %s %s/USD rate %s", self.bot_id, base, reason)

    async def _read_base_holdings(self, base: str) -> Optional[float]:
        """Return the free balance of ``base`` on the venue, or None unread.

        None means the read did not answer, which ``set_initial_chunk_rate``
        treats as no room to claim rather than as a balance of zero.
        """
        _base = (base or "").upper()
        if not _base:
            return None
        try:
            _bal = await self.exchange.get_balance(_base)
        except Exception as _bal_exc:  # an unread balance is None, never 0
            logger.warning(
                "Bot %s could not read its %s balance (%s: %s).",
                self.bot_id,
                _base,
                type(_bal_exc).__name__,
                _bal_exc,
            )
            return None
        _free = getattr(_bal, "free", None)
        if _free is None:
            return None
        try:
            return float(_free)
        except (TypeError, ValueError):
            return None

    # ── Pair filter and signals ───────────────────────────────────────

    def _pair_filter_matches(self, market) -> bool:
        """Return True if `market` belongs in this bot's scanning universe.

        Keeps an active market whose QUOTE side equals the configured
        `base_currency`: base=USDC matches LINK/USDC, ETH/USDC, and so on.
        """
        try:
            if not getattr(market, "active", True):
                return False
            base = (self.config.base_currency or "").upper()
            if not base:
                return False
            m_quote = (getattr(market, "quote", "") or "").upper()
            return m_quote == base
        except Exception:  # defensive market filter
            return False

    def _entry_signal_matched(self, snapshot) -> bool:
        """True on a BEARISH `snapshot`, mirroring Scrumming's FOLD entry."""
        if snapshot is None:
            return False
        return bool(getattr(snapshot, "is_bearish", False))

    def _exit_signal_matched(self, snapshot) -> bool:
        """True on a BULLISH `snapshot`: sell the alt back to base."""
        if snapshot is None:
            return False
        return bool(getattr(snapshot, "is_bullish", False))

    def _entry_order_side(self):
        """OrderSide for artillery entry: BUY."""
        from ..exchange.base import OrderSide

        return OrderSide.BUY

    def _exit_order_side(self):
        """OrderSide for position exit: SELL."""
        from ..exchange.base import OrderSide

        return OrderSide.SELL

    def set_bot_manager(self, manager) -> None:
        """Accept a back-reference to BotManager so profit credits can
        call notify_bot_profit(). Called by BotManager during bot
        lifecycle wire-up, same pattern as ScrummingBot.set_bot_manager.
        """
        self._bot_manager = manager

    def update_usd_per_base_rate(self, rate_usd_per_base: float) -> tuple[bool, str]:
        """Update the dollars-per-base-unit rate each artillery shot is sized at.

        A zero or negative rate is refused; the last-known-good rate
        stays in effect. A rate diverging more than
        ``_rate_spike_threshold_pct`` from the most recent accepted
        sample is spike-protected: ``_usd_per_base_rate`` falls back
        to the median of ``_recent_rates`` instead. Otherwise the rate
        is accepted, ``_usd_per_base_rate`` updates, and the sample is
        appended to ``_recent_rates`` (trimmed to
        ``_rate_spike_window``).

        Returns ``(accepted, reason)``.
        """
        # Fail-closed on zero / negative — the rate must be positive.
        if rate_usd_per_base is None or rate_usd_per_base <= 0:
            self._rate_refuse_events += 1
            return False, (
                f"refused: invalid rate {rate_usd_per_base!r} " f"(must be > 0)"
            )
        new_rate = float(rate_usd_per_base)

        # First-ever update: accept unconditionally.
        if not self._recent_rates:
            self._recent_rates.append(new_rate)
            self._usd_per_base_rate = new_rate
            return True, "accepted (first sample)"

        # Spike check against the most recent accepted sample.
        last_rate = self._recent_rates[-1]
        if last_rate <= 0:  # defensive: window should always hold > 0
            self._recent_rates = [new_rate]
            self._usd_per_base_rate = new_rate
            return True, "accepted (recovered from invalid window)"

        # Both are dimensionless ratios, not percentages.
        divergence_ratio = abs(new_rate - last_rate) / last_rate
        spike_limit_ratio = self._rate_spike_threshold_pct / PERCENT_PER_RATIO_UNIT
        if divergence_ratio > spike_limit_ratio:
            # Spike: use the window median and do not append the
            # fresh sample, so consecutive spikes fall back the same way.
            self._rate_spike_events += 1
            window = sorted(self._recent_rates)
            mid = len(window) // 2
            if len(window) % 2 == 1:
                median = window[mid]
            else:
                median = (window[mid - 1] + window[mid]) / 2.0
            self._usd_per_base_rate = median
            return False, (
                f"spike-protected: incoming {new_rate:.6f} diverges "
                f"{divergence_ratio * PERCENT_PER_RATIO_UNIT:.2f}% from "
                f"last {last_rate:.6f}; "
                f"using median {median:.6f} of window"
            )

        # Normal acceptance — update the chunk rate and append to
        # the trailing window (trim to spike_window samples).
        self._recent_rates.append(new_rate)
        if len(self._recent_rates) > self._rate_spike_window:
            self._recent_rates = self._recent_rates[-self._rate_spike_window :]
        self._usd_per_base_rate = new_rate
        return True, "accepted"

    # ── State-machine evaluators ────────────────────────────────────

    def _position_value_usd(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> float:
        """USD value of the position: alt_units × alt_price_in_base × usd_per_base."""
        return pos.alt_units * alt_price_in_base * self._usd_per_base_rate

    def _is_in_drawdown(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> bool:
        """True while the position's USD value sits below
        `pos.artillery_size_usd_at_entry`, the figure snapshotted at
        firing and never updated afterward.
        """
        return (
            self._position_value_usd(pos, alt_price_in_base)
            < pos.artillery_size_usd_at_entry
        )

    def _exit_is_profitable_in_base(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> bool:
        """True iff the proportional sell would net more base units
        (after fees) than the proportional cost basis; refuses an exit
        that would grow USD but shrink the base unit count.
        """
        units_to_sell = pos.alt_units * (self.config.extractor_exit_pct / 100.0)
        base_back = units_to_sell * alt_price_in_base
        fee_pct = float(getattr(self.config, "trading_fee_pct", 0.6))
        base_back_after_fee = base_back * (1.0 - fee_pct / 100.0)
        base_in_proportional = pos.cost_basis_base * (
            self.config.extractor_exit_pct / 100.0
        )
        return base_back_after_fee > base_in_proportional

    # ── Pair action evaluation ──────────────────────────────────────

    async def _evaluate_open_position(
        self,
        pos: ExtractorPosition,
        snapshot: TASnapshot,
        alt_price_in_base: float,
    ) -> None:
        """Drive an open position through its state transitions."""
        if self._is_in_drawdown(pos, alt_price_in_base):
            pos.state = POSITION_STATE_DRAWDOWN
        elif pos.state == POSITION_STATE_DRAWDOWN:
            pos.state = POSITION_STATE_IN_FLIGHT

        if self._exit_signal_matched(snapshot) and self._exit_is_profitable_in_base(
            pos, alt_price_in_base
        ):
            pos.state = POSITION_STATE_BULLISH_EXIT
            await self._execute_bullish_exit(pos, alt_price_in_base)
            return

    async def manual_fire_position(self, pair: str) -> dict:
        """Close one open position at the current market price on
        operator request, from the position's Manual Fire button.

        Bypasses `_exit_is_profitable_in_base` and always closes in
        full, regardless of `extractor_exit_pct`.

        Returns a status dict the GUI consumes:
          {"success": bool, "pair": str, "reason": str,
           "alt_units_closed": float, "base_received": float,
           "gain_base": float, "log_message": str}
        """
        pos = self._positions.get(pair)
        if pos is None:
            return {
                "success": False,
                "pair": pair,
                "reason": f"no open position for {pair}",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": (
                    f"EXTRACTOR MANUAL FIRE: refused — no open position "
                    f"for {pair}. Watch list may show the pair but no "
                    f"artillery is in flight."
                ),
            }

        # Fetch current price (base-per-alt) for the close.
        try:
            ticker = await self.exchange.get_ticker(pair)
            alt_price_in_base = float(ticker.last)
        except Exception as exc:
            msg = (
                f"EXTRACTOR MANUAL FIRE {pair}: ticker fetch raised "
                f"{type(exc).__name__}: {exc}. Refusing to fire on "
                f"uncertain price."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
            logger.warning("Bot %s %s", self.bot_id, msg)
            return {
                "success": False,
                "pair": pair,
                "reason": f"ticker fetch failed: {exc}",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": msg,
            }
        if alt_price_in_base <= 0:
            msg = (
                f"EXTRACTOR MANUAL FIRE {pair}: ticker.last "
                f"non-positive ({alt_price_in_base}). Refusing."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
            return {
                "success": False,
                "pair": pair,
                "reason": "non-positive price",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": msg,
            }

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR MANUAL FIRE: operator requested close of "
                f"{pair} ({pos.alt_units:.6f} units @ "
                f"${alt_price_in_base:.8f}). Bypassing "
                f"base-unit-profitability gate per operator-sovereignty "
                f"invariant (v3.18.15)."
            ),
        )

        # Snapshot pre-close state for the return dict
        units_before = pos.alt_units

        # Overrides exit_pct on the shared config for this call only;
        # restored in the finally clause below.
        _original_exit_pct = float(self.config.extractor_exit_pct)
        try:
            self.config.extractor_exit_pct = 100.0
            await self._execute_bullish_exit(pos, alt_price_in_base)
        except Exception as exc:
            self.config.extractor_exit_pct = _original_exit_pct
            msg = (
                f"EXTRACTOR MANUAL FIRE {pair}: exit raised "
                f"{type(exc).__name__}: {exc}."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
            logger.exception("Manual fire on extractor position failed")
            return {
                "success": False,
                "pair": pair,
                "reason": f"exit raised: {exc}",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": msg,
            }
        finally:
            self.config.extractor_exit_pct = _original_exit_pct

        # A full exit removes the position and appends this close to
        # _closed_position_log; read the last entry for the return dict.
        last_close = self._closed_position_log[-1] if self._closed_position_log else {}
        return {
            "success": True,
            "pair": pair,
            "reason": "operator manual fire",
            "alt_units_closed": float(
                last_close.get("alt_units_initial", units_before)
            ),
            "base_received": float(last_close.get("base_received", 0.0)),
            "gain_base": float(last_close.get("gain_base", 0.0)),
            "log_message": (
                f"EXTRACTOR MANUAL FIRE COMPLETE: {pair} closed "
                f"{units_before:.6f} units; received "
                f"{last_close.get('base_received', 0.0):.8f} base; "
                f"gain {last_close.get('gain_base', 0.0):+.8f} base."
            ),
        }

    async def _execute_bullish_exit(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> None:
        """Sell extractor_exit_pct of the position back to base."""
        units_to_sell = pos.alt_units * (self.config.extractor_exit_pct / 100.0)
        if units_to_sell <= 0:
            return

        try:
            order = await self.guarded_place_order(
                symbol=pos.pair,
                side=self._exit_order_side(),
                order_type=OrderType.MARKET,
                amount=units_to_sell,
                price=None,
            )
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"EXTRACTOR EXIT FAILED on {pos.pair}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Extractor exit failed")
            return

        if order is None:
            return

        filled_units = float(
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or units_to_sell
        )
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or alt_price_in_base
        )
        base_received = filled_units * fill_price
        cost_basis_proportional = pos.cost_basis_base * (
            self.config.extractor_exit_pct / 100.0
        )
        gain_base = base_received - cost_basis_proportional

        # Update position: deduct sold units, deduct proportional cost basis
        pos.alt_units -= filled_units
        pos.cost_basis_base -= cost_basis_proportional

        # The gain locks to chunk_free_base; no roll re-enters the pair.
        self._chunk_free_base += base_received
        log_kind = "LOCK_TO_POOL"

        self._cycle_extracted_total += gain_base
        self._lifetime_extracted_total += gain_base
        self._chunk_extracted_total += gain_base

        # Grows the registry reservation at once, so no sibling claims the profit.
        if (
            gain_base > 0
            and self._bot_manager is not None
            and self._usd_per_base_rate > 0
        ):
            try:
                gain_usd = self._base_to_usd(gain_base)
                if gain_usd > 0:
                    self._bot_manager.notify_bot_profit(
                        bot_id=self.bot_id, profit_usd=gain_usd
                    )
            except Exception as _exc:  # best-effort; must not block trade flow
                logger.warning(
                    "v3.20.72 profit notification failed for bot %s: %s",
                    self.bot_id,
                    _exc,
                )

        # The sale has filled, so the base currency is back. Tell the
        # parent bot, which is what stops the parent selling it away.
        self._hand_base_currency_to_parent(base_received, pos.pair)

        # If position fully exited, remove + log to closed list
        if pos.alt_units < 1e-12 or self.config.extractor_exit_pct >= 100.0:
            self._closed_position_log.append(
                {
                    "pair": pos.pair,
                    "opened_at": pos.opened_at,
                    "closed_at": time.time(),
                    "alt_units_initial": (filled_units + pos.alt_units),
                    "cost_basis_base": (cost_basis_proportional + pos.cost_basis_base),
                    "base_received": base_received,
                    "gain_base": gain_base,
                    "log_kind": log_kind,
                }
            )
            # Cap closed-log size
            if len(self._closed_position_log) > self._closed_log_max:
                self._closed_position_log = self._closed_position_log[
                    -self._closed_log_max :
                ]
            self._positions.pop(pos.pair, None)

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR EXIT ({log_kind}): {pos.pair} sold "
                f"{filled_units:.6f} @ {fill_price:.8f}; "
                f"received {base_received:.8f} base; "
                f"gain {gain_base:+.8f} base."
            ),
        )

    def _hand_base_currency_to_parent(self, base_received: float, pair: str) -> None:
        """Tell the parent bot its base currency came back, so the
        parent raises its own target balance by the same amount
        instead of selling the arrival back out as surplus.

        Looks up the parent by `base_currency` scoped to this bot's own
        `exchange_id` (no default, so the lookup cannot silently cross
        exchanges) via `find_parent_bot_for_base_currency`, and books
        the arrival with `ScrummingBot.apply_extractor_tranche_return`.
        `base_received` is the observed fill, not a computed profit. No
        parent, no manager, or a refused booking is a no-op with no
        retry. A failure here is caught and logged; it never blocks the
        exit that already happened.
        """
        if base_received <= 0 or self._bot_manager is None:
            return
        try:
            parent = self._bot_manager.find_parent_bot_for_base_currency(
                self.config.base_currency, exchange_id=self.config.exchange_id
            )
            if parent is None:
                return
            parent.apply_extractor_tranche_return(
                usd_value=float(self._base_to_usd(base_received)),
                source=self.bot_id,
                base_units=float(base_received),
                ref=pair,
            )
        except Exception as _exc:  # the exit must finish anyway
            logger.warning(
                "Extractor %s could not hand %s back to a parent: %s: %s",
                self.bot_id,
                self.config.base_currency,
                type(_exc).__name__,
                _exc,
            )

    async def _fire_artillery(
        self,
        pair: str,
        snapshot: TASnapshot,
        alt_price_in_base: float,
    ) -> None:
        """Fire one artillery round into `pair`. Creates a new
        ExtractorPosition on success."""
        artillery_usd = float(self.config.extractor_artillery_size_usd)
        artillery_base = self._usd_to_base(artillery_usd)
        if artillery_base <= 0:
            return
        if not self._has_chunk_capacity(artillery_base):
            return  # chunk_free_base too small for one round

        if alt_price_in_base <= 0:
            return

        # Fail-closed buy-safety check; expected_units=0 since a fresh
        # position holds no alt yet.
        target_asset = pair.split("/")[0]
        verified, refuse = await verify_buy_safe_or_refuse(
            self.exchange,
            target_asset,
            expected_units=0.0,
            path="extractor_artillery",
        )
        if refuse:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=refuse)
            logger.warning("Bot %s %s", self.bot_id, refuse)
            return

        alt_units_to_buy = artillery_base / alt_price_in_base
        try:
            order = await self.guarded_place_order(
                symbol=pair,
                side=self._entry_order_side(),
                order_type=OrderType.MARKET,
                amount=alt_units_to_buy,
                price=None,
            )
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"EXTRACTOR ARTILLERY FAILED on {pair}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Extractor artillery failed")
            return
        if order is None:
            return

        filled_units = float(
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or alt_units_to_buy
        )
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or alt_price_in_base
        )
        actual_base_spent = filled_units * fill_price

        # Debit chunk
        self._chunk_free_base -= actual_base_spent

        # Create position
        pos = ExtractorPosition(
            pair=pair,
            state=POSITION_STATE_IN_FLIGHT,
            artillery_size_base=artillery_base,
            artillery_size_usd_at_entry=artillery_usd,
            alt_units=filled_units,
            entry_price_base_per_alt=fill_price,
            avg_buy_price_base_per_alt=fill_price,
            cost_basis_base=actual_base_spent,
            opened_at=time.time(),
        )
        self._positions[pair] = pos
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR ARTILLERY FIRED: {pair} bought "
                f"{filled_units:.6f} @ {fill_price:.8f} "
                f"(spent {actual_base_spent:.8f} base, "
                f"~${artillery_usd:.2f}). chunk_free now "
                f"{self._chunk_free_base:.8f} base."
            ),
        )

    # ── tick() — main per-cycle entrypoint ──────────────────────────

    async def tick(self) -> None:
        """One tick of the Extractor.

        Pulses the CapitalReservationRegistry heartbeat, then on a due
        refresh reads the base currency's dollar price through
        ``_acquire_usd_per_base_rate`` and re-ranks the watch list,
        evaluates every open position for drawdown/exit, and scans the
        watch list for a new artillery opportunity — the first eligible
        pair wins per tick.
        """
        self._tick_counter += 1

        # Registry heartbeat is defensive: it must never block a tick.
        if self._crr_token is not None:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_get_registry().heartbeat(self.bot_id)
            except Exception as _crr_exc:  # best-effort; tick must not block
                logger.debug(
                    "Bot %s capital reservation heartbeat raised %s — "
                    "continuing tick.",
                    self.bot_id,
                    _crr_exc,
                )

        # Step 0: refresh watch list if due
        if self._watch_list_due_for_refresh():
            await self._acquire_usd_per_base_rate()
            await self._refresh_watch_list()

        # Step 1: manage open positions
        for pair, pos in list(self._positions.items()):
            snapshot = await self._ta_provider.evaluate(pair)
            if snapshot is None:
                continue  # warmup or exchange hiccup; skip this pair
            try:
                ticker = await self.exchange.get_ticker(pair)
                alt_price_in_base = float(ticker.last)
            except Exception as exc:  # per-pair best-effort
                logger.debug(
                    "Bot %s tick: get_ticker(%s) raised %s: %s — open "
                    "position left untouched this tick",
                    self.bot_id,
                    pair,
                    type(exc).__name__,
                    exc,
                )
                continue
            if alt_price_in_base <= 0:
                continue
            # The parent values the tranche from this field, with no network call.
            pos.last_price_base_per_alt = alt_price_in_base
            pos.last_priced_at = time.time()
            try:
                await self._evaluate_open_position(pos, snapshot, alt_price_in_base)
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"EXTRACTOR position eval {pair} raised "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
                logger.exception("Extractor position eval failed")

        # Step 2: scan watch list for new entries
        for pair in self._watch_list:
            if pair in self._positions:
                continue  # one position per pair
            snapshot = await self._ta_provider.evaluate(pair)
            if snapshot is None:
                continue
            if not self._entry_signal_matched(snapshot):
                continue
            try:
                ticker = await self.exchange.get_ticker(pair)
                alt_price_in_base = float(ticker.last)
            except Exception as _tk_exc:  # noqa: BLE001 - skip this pair
                logger.warning(
                    "Extractor skipping %s after entry signal matched — "
                    "ticker fetch failed (%s): %s",
                    pair,
                    type(_tk_exc).__name__,
                    _tk_exc,
                )
                continue
            if alt_price_in_base <= 0:
                continue
            try:
                await self._fire_artillery(pair, snapshot, alt_price_in_base)
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"EXTRACTOR fire_artillery {pair} raised "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
                logger.exception("Extractor fire_artillery failed")
                continue
            # First eligible wins per tick — break to manage capital
            break

    # ── Positions snapshot (for detail-dialog Positions Held tab) ──

    def positions_for_gui(self) -> list[dict]:
        """Return a list of per-position dicts for the detail dialog's
        Positions Held tab: pair, state, tier, alt units, entry USD,
        current USD, delta %, and corrections fired.

        No ticker is fetched here since the GUI thread must never
        block on network; ``avg_buy_price_base_per_alt`` stands in for
        the current price until the dialog supplies a live one.
        """
        rows: list[dict] = []
        for p in self._positions.values():
            current_price = p.avg_buy_price_base_per_alt
            current_value_usd = p.alt_units * current_price * self._usd_per_base_rate
            entry_value_usd = p.artillery_size_usd_at_entry
            delta_pct = (
                ((current_value_usd - entry_value_usd) / entry_value_usd * 100.0)
                if entry_value_usd > 0
                else 0.0
            )
            rows.append(
                {
                    "pair": p.pair,
                    "state": p.state,
                    "alt_units": p.alt_units,
                    "entry_usd": entry_value_usd,
                    "current_usd_approx": current_value_usd,
                    "delta_pct_usd_approx": delta_pct,
                    "cost_basis_base": p.cost_basis_base,
                    "avg_buy_price_base_per_alt": p.avg_buy_price_base_per_alt,
                    "opened_at": p.opened_at,
                }
            )
        return rows

    # ── Extractor Tranches (for the parent's tranche list) ──────────

    def tranche_id_for_position(self, position: ExtractorPosition) -> str:
        """Build the stable Extractor Tranche id: ``bot_id|pair|opened_at``.

        The row emitter and `set_tranche_arbiter` both format
        `opened_at` through this one method, so they can never format
        it differently and disagree on the same id. `bot_id` survives
        restart and separates two Extractors on one pair; `pair` is
        unique within one Extractor; `opened_at` stops a closed-and-
        reopened position from inheriting its predecessor's id.
        """
        return (
            f"{self.bot_id}|{position.pair}|" f"{float(position.opened_at or 0.0):.6f}"
        )

    def set_tranche_arbiter(self, tranche_id: object, arbiter: object) -> str | None:
        """Record who may close one Extractor Tranche. Writes one
        string on the matching position; places no order and changes
        no balance. Resolved by full tranche id, never by pair alone,
        since a pair can close and reopen under a new id. Returns the
        stored value, or ``None`` (no write) when no open position
        carries that id.
        """
        wanted = str(tranche_id) if tranche_id is not None else ""
        if not wanted:
            return None
        for position in self._positions.values():
            if self.tranche_id_for_position(position) != wanted:
                continue
            position.arbiter = normalize_arbiter(arbiter)
            logger.info(
                "Bot %s: Extractor Tranche %s arbiter set to %s "
                "(record only — no order placed, no balance changed).",
                self.bot_id,
                wanted,
                position.arbiter,
            )
            return position.arbiter
        return None

    def toggle_tranche_arbiter(self, tranche_id: object) -> str | None:
        """Flip one tranche's arbiter to the other value, via
        `set_tranche_arbiter`. Returns the new value, or ``None`` when
        the id matches no open position.
        """
        wanted = str(tranche_id) if tranche_id is not None else ""
        if not wanted:
            return None
        for position in self._positions.values():
            if self.tranche_id_for_position(position) != wanted:
                continue
            return self.set_tranche_arbiter(wanted, other_arbiter(position.arbiter))
        return None

    def extractor_tranche_rows(self) -> list[dict]:
        """Describe every open position as an Extractor Tranche row,
        the child's half of the listing `ScrummingBot.
        open_extractor_tranches` reads on the parent side. This bot is
        the only writer of its own positions, so the parent asks
        rather than keeping a copy that could fall out of step.

        Reads only in-memory state — no network, no clock, no write —
        since the caller is the GUI thread. `mark_*` is ``None`` when a
        position has never been priced, rather than substituting the
        average buy price the way `positions_for_gui` does; that
        substitute would misrepresent a cost-basis number as a market
        value in the parent's own ledger.
        """
        rows: list[dict] = []
        base_asset = str(getattr(self.config, "base_currency", "") or "")
        rate = float(self._usd_per_base_rate or 0.0)
        for p in self._positions.values():
            mark_price = float(p.last_price_base_per_alt or 0.0)
            if mark_price > 0:
                mark_value_base = float(p.alt_units) * mark_price
                mark_value_usd = mark_value_base * rate if rate > 0 else None
            else:
                mark_value_base = None
                mark_value_usd = None
            rows.append(
                {
                    "tranche_id": self.tranche_id_for_position(p),
                    "kind": "extractor",
                    "child_bot_id": self.bot_id,
                    "child_bot_name": str(
                        getattr(self.config, "name", "") or self.bot_id
                    ),
                    "pair": p.pair,
                    "state": p.state,
                    "base_asset": base_asset,
                    "base_deployed": float(p.cost_basis_base or 0.0),
                    "alt_units": float(p.alt_units or 0.0),
                    "mark_price_base_per_alt": (mark_price if mark_price > 0 else None),
                    "mark_value_base": mark_value_base,
                    "mark_value_usd": mark_value_usd,
                    "marked_at": (
                        float(p.last_priced_at or 0.0) if mark_price > 0 else None
                    ),
                    "cost_basis_base": float(p.cost_basis_base or 0.0),
                    "entry_usd": float(p.artillery_size_usd_at_entry or 0.0),
                    "opened_at": float(p.opened_at or 0.0),
                    # Normalised on the way out, so a surface that trusts
                    # this dict can never be handed a third value.
                    "arbiter": normalize_arbiter(p.arbiter),
                }
            )
        rows.sort(key=lambda r: r["tranche_id"])
        return rows

    # ── Status snapshot (for GUI / dashboard) ───────────────────────

    def get_status(self) -> dict:
        """Snapshot of Extractor state for the bot table / dashboard."""
        base = super().get_status() if hasattr(super(), "get_status") else {}
        n_drawdown = sum(
            1 for p in self._positions.values() if p.state == POSITION_STATE_DRAWDOWN
        )
        base.update(
            {
                "bot_id": self.bot_id,
                "mode": "extractor",
                "base_currency": self.config.base_currency,
                "chunk_size_base": self._chunk_size_base,
                "chunk_free_base": self._chunk_free_base,
                "chunk_extracted_total": self._chunk_extracted_total,
                "chunk_size_usd": self._chunk_size_usd,
                "n_positions_open": len(self._positions),
                "n_positions_drawdown": n_drawdown,
                "pool_color": self.pool_color(),
                "watch_list": list(self._watch_list),
                "cycle_extracted_total": self._cycle_extracted_total,
                "lifetime_extracted_total": self._lifetime_extracted_total,
            }
        )
        return base

    # ── State persistence ──────────────────────────────────────────

    def export_state(self) -> dict:
        """Serialize the Extractor's runtime state for save/restore."""
        return {
            "version": 1,
            "mode": "extractor",
            "chunk_size_usd": self._chunk_size_usd,
            # On-disk key of _usd_per_base_rate; kept so saved state restores.
            "chunk_to_base_rate": self._usd_per_base_rate,
            "chunk_size_base": self._chunk_size_base,
            "chunk_free_base": self._chunk_free_base,
            "chunk_extracted_total": self._chunk_extracted_total,
            "positions": [
                {
                    "pair": p.pair,
                    "state": p.state,
                    "artillery_size_base": p.artillery_size_base,
                    "artillery_size_usd_at_entry": (p.artillery_size_usd_at_entry),
                    "alt_units": p.alt_units,
                    "entry_price_base_per_alt": p.entry_price_base_per_alt,
                    "avg_buy_price_base_per_alt": p.avg_buy_price_base_per_alt,
                    "cost_basis_base": p.cost_basis_base,
                    "opened_at": p.opened_at,
                    "last_price_base_per_alt": p.last_price_base_per_alt,
                    "last_priced_at": p.last_priced_at,
                    # An explicit key list: a field not named here is dropped on save.
                    "arbiter": normalize_arbiter(p.arbiter),
                }
                for p in self._positions.values()
            ],
            "closed_position_log": list(self._closed_position_log),
            "watch_list": list(self._watch_list),
            "tick_counter": self._tick_counter,
            "cycle_extracted_total": self._cycle_extracted_total,
            "lifetime_extracted_total": self._lifetime_extracted_total,
        }

    def import_state(self, state: dict) -> None:
        """Rehydrate from a previously-exported state dict.

        Graceful on missing fields (forward/backward compat): every
        read goes through `.get(key, default)`.
        """
        if not isinstance(state, dict):
            return
        self._chunk_size_usd = float(state.get("chunk_size_usd", self._chunk_size_usd))
        self._usd_per_base_rate = float(
            state.get("chunk_to_base_rate", self._usd_per_base_rate)
        )
        self._chunk_size_base = float(
            state.get("chunk_size_base", self._chunk_size_base)
        )
        self._chunk_free_base = float(
            state.get("chunk_free_base", self._chunk_free_base)
        )
        self._chunk_extracted_total = float(state.get("chunk_extracted_total", 0.0))
        self._positions = {}
        for pdict in state.get("positions", []):
            try:
                pos = ExtractorPosition(
                    pair=pdict["pair"],
                    state=pdict.get("state", POSITION_STATE_IN_FLIGHT),
                    artillery_size_base=float(pdict.get("artillery_size_base", 0.0)),
                    artillery_size_usd_at_entry=float(
                        pdict.get("artillery_size_usd_at_entry", 0.0)
                    ),
                    alt_units=float(pdict.get("alt_units", 0.0)),
                    entry_price_base_per_alt=float(
                        pdict.get("entry_price_base_per_alt", 0.0)
                    ),
                    avg_buy_price_base_per_alt=float(
                        pdict.get("avg_buy_price_base_per_alt", 0.0)
                    ),
                    cost_basis_base=float(pdict.get("cost_basis_base", 0.0)),
                    opened_at=float(pdict.get("opened_at", 0.0)),
                    # Absent on an older state file; 0.0 correctly means
                    # never priced for a position restored without a mark.
                    last_price_base_per_alt=float(
                        pdict.get("last_price_base_per_alt", 0.0)
                    ),
                    last_priced_at=float(pdict.get("last_priced_at", 0.0)),
                    # normalize_arbiter cannot raise, unlike the float() calls above.
                    arbiter=normalize_arbiter(pdict.get("arbiter", ARBITER_SIBLING)),
                )
                self._positions[pos.pair] = pos
            except Exception as exc:  # skip malformed position records
                logger.warning(
                    "Bot %s import_state: a saved position record raised "
                    "%s: %s — record dropped, remaining records still "
                    "load",
                    self.bot_id,
                    type(exc).__name__,
                    exc,
                )
                continue
        self._closed_position_log = list(state.get("closed_position_log", []))
        self._watch_list = list(state.get("watch_list", []))
        self._tick_counter = int(state.get("tick_counter", 0))
        self._cycle_extracted_total = float(state.get("cycle_extracted_total", 0.0))
        self._lifetime_extracted_total = float(
            state.get("lifetime_extracted_total", 0.0)
        )
