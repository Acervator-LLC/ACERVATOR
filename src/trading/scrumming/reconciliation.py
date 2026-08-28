"""Holdings reconciliation for ScrummingBot: the venue is authoritative.

Pulls exchange truth -- balance, trade count, position health -- and folds
any difference into the internal lot book. Places no orders.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

logger = logging.getLogger("acervator.scrumming")


class ReconciliationEngineMixin:
    """Reconcile internal holdings and the lot book against the exchange.

    Internal numbers never override the venue: a disagreement is resolved
    by adopting the exchange reading and booking the difference as a
    reconciliation lot.
    """

    # Supplied by ScrummingBot at runtime; declared so a type
    # checker can resolve them. Annotations only: no attribute is
    # created and the runtime base stays `object`.
    _bus: Any
    _current_holdings: float
    _get_balance: Callable[..., Any]
    _get_ticker: Callable[..., Any]
    _main_lots: list[dict]
    _quote_to_usd: float
    _refresh_quote_to_usd: Callable[..., Any]
    bot_id: Any
    config: Any
    exchange: Any
    stats: Any

    EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC = 300.0

    async def refresh_exchange_position_health(self, force: bool = False) -> bool:
        """Refresh exchange-pulled position health stats.

        Returns True if a refresh actually fetched + updated stats,
        False if throttled or unavailable.

        Args:
            force: bypass throttle (use sparingly — e.g., on operator-
                triggered diagnostics).
        """
        import time as _t

        _now = _t.time()
        _cooldown = self.EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC
        if not force and (_now - self.stats.exchange_data_fresh_ts) < _cooldown:
            return False

        if self.exchange is None:
            return False
        if not hasattr(self.exchange, "get_my_trades"):
            return False

        try:
            from ...exchange.position_health import compute_position_health

            _trades = await self.exchange.get_my_trades(self.config.symbol, limit=500)
            if _trades is None:
                return False
            _asset_base = self.config.symbol.split("/")[0]
            _ph = compute_position_health(_trades, _asset_base)

            self.stats.realized_pnl_exchange = float(_ph.realized_pnl_usd)
            self.stats.avg_entry_exchange = float(_ph.avg_entry)
            self.stats.cost_basis_total_exchange = float(_ph.cost_basis_total_usd)
            self.stats.fees_paid_exchange = float(_ph.fees_paid_total)
            try:
                await self.sync_ytd_trade_count()
            except Exception as _ytd_exc:
                logger.debug(
                    "Bot %s YTD sync inside health-refresh raised: %s",
                    self.bot_id,
                    _ytd_exc,
                )
            self.stats.exchange_data_fresh_ts = _now

            try:
                _cash_usd = 0.0
                _bal_usd = await self._get_balance("USD")
                if _bal_usd is not None:
                    _cash_usd += float(getattr(_bal_usd, "free", 0) or 0)
                try:
                    _bal_usdc = await self._get_balance("USDC")
                    if _bal_usdc is not None:
                        _cash_usd += float(getattr(_bal_usdc, "free", 0) or 0)
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "refresh_exchange_position_health",
                        type(_sup).__name__,
                        _sup,
                    )
                self.stats.cash_balance_usd = _cash_usd
            except Exception as _cash_exc:
                logger.debug(
                    "Bot %s cash balance refresh failed (non-fatal): %s",
                    self.bot_id,
                    _cash_exc,
                )

            try:
                if hasattr(self.exchange, "get_open_orders"):
                    from ...exchange.base import OrderSide as _OS

                    _open = await self.exchange.get_open_orders(self.config.symbol)
                    if _open is not None:
                        _buys = sum(
                            1 for o in _open if getattr(o, "side", None) == _OS.BUY
                        )
                        _sells = sum(
                            1 for o in _open if getattr(o, "side", None) == _OS.SELL
                        )
                        self.stats.active_buy_orders = int(_buys)
                        self.stats.active_sell_orders = int(_sells)
            except Exception as _oo_exc:
                logger.debug(
                    "Bot %s open-orders refresh failed (non-fatal): %s",
                    self.bot_id,
                    _oo_exc,
                )

            return True
        except Exception as _exc:
            logger.warning(
                "Bot %s exchange position-health refresh failed: %s", self.bot_id, _exc
            )
            return False

    YTD_TRADE_ANCHOR_UTC = 1_775_001_600.0
    YTD_TRADE_PAGE_LIMIT = 500
    YTD_TRADE_MAX_PAGES = 40

    async def sync_ytd_trade_count(self) -> Optional[int]:
        """Paginate get_my_trades from YTD_TRADE_ANCHOR_UTC forward
        and reconcile ``stats.total_trades`` / ``exchange_trade_count``.

        Returns the reconciled total, or ``None`` when the exchange
        can't be consulted (missing connector, method not implemented,
        API error). Never lowers the persisted counter — the
        reconciled value is ``max(persisted, exchange_count)`` so a
        partial-page response or transient rate-limit can't wipe out
        real history. Called once at boot from
        ``bootstrap_exchange_state``; subsequent per-trade increments
        continue via the normal execute-buy / execute-sell paths.
        """
        if self.exchange is None:
            return None
        if not hasattr(self.exchange, "get_my_trades"):
            return None
        _persisted = int(getattr(self.stats, "total_trades", 0) or 0)
        import time as _t

        _now = _t.time()
        _window_s = 30 * 24 * 3600.0
        _cursor = self.YTD_TRADE_ANCHOR_UTC
        _seen_ids: set = set()
        _windows = 0
        _ytd_scrum_usd = 0.0
        _ytd_fold_usd = 0.0
        _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        try:
            while _cursor < _now and _windows < 12:
                _end = min(_cursor + _window_s, _now)
                _end_ms = int(_end * 1000)
                _window_trades = await self.exchange.get_my_trades(
                    self.config.symbol,
                    since=_cursor,
                    limit=self.YTD_TRADE_PAGE_LIMIT,
                    params={"paginate": True, "until": _end_ms},
                )
                _new = 0
                for _tr in _window_trades or []:
                    _tid = getattr(_tr, "id", None) or id(_tr)
                    if _tid in _seen_ids:
                        continue
                    _seen_ids.add(_tid)
                    _new += 1
                    try:
                        _amt = float(getattr(_tr, "amount", 0) or 0)
                        _px = float(getattr(_tr, "price", 0) or 0)
                        _usd = _amt * _px * _qrate
                        _side = getattr(_tr, "side", None)
                        _side_str = str(getattr(_side, "value", _side) or "").lower()
                        if "sell" in _side_str:
                            _ytd_scrum_usd += _usd
                        elif "buy" in _side_str:
                            _ytd_fold_usd += _usd
                    except (TypeError, ValueError) as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "sync_ytd_trade_count",
                            type(_sup).__name__,
                            _sup,
                        )
                logger.debug(
                    "Bot %s YTD window %d: [%.0f..%.0f] returned=%d "
                    "new=%d cumulative_unique=%d",
                    self.bot_id,
                    _windows + 1,
                    _cursor,
                    _end,
                    len(_window_trades or []),
                    _new,
                    len(_seen_ids),
                )
                _windows += 1
                _cursor = _end
            _count = len(_seen_ids)
            logger.info(
                "Bot %s YTD sync via chunked-window walk: "
                "symbol=%s returned %d unique trades over %d windows "
                "(scrummed=$%.2f folded=$%.2f)",
                self.bot_id,
                self.config.symbol,
                _count,
                _windows,
                _ytd_scrum_usd,
                _ytd_fold_usd,
            )
        except Exception as _exc:
            logger.warning(
                "Bot %s sync_ytd_trade_count fetch failed: %s "
                "(persisted counter %d retained)",
                self.bot_id,
                _exc,
                _persisted,
            )
            return None
        _prev_exc = int(getattr(self.stats, "exchange_trade_count", 0) or 0)
        _reconciled = max(_persisted, _prev_exc, _count)
        self.stats.total_trades = _reconciled
        self.stats.exchange_trade_count = _reconciled
        _prev_scrum = float(getattr(self.stats, "ytd_scrummed_usd", 0.0) or 0.0)
        _prev_fold = float(getattr(self.stats, "ytd_folded_usd", 0.0) or 0.0)
        self.stats.ytd_scrummed_usd = max(_prev_scrum, _ytd_scrum_usd)
        self.stats.ytd_folded_usd = max(_prev_fold, _ytd_fold_usd)
        import time as _t

        self.stats.exchange_data_fresh_ts = _t.time()
        logger.info(
            "Bot %s YTD trade-count sync: exchange=%d persisted=%d "
            "prev_exchange=%d reconciled=%d",
            self.bot_id,
            _count,
            _persisted,
            _prev_exc,
            _reconciled,
        )
        return _reconciled

    async def bootstrap_exchange_state(self) -> None:
        """One-shot live-pull of exchange state for the GUI.

        Populates: _current_holdings, stats.current_price, stats.position_value.
        Runs fail-closed — any exception logged but not raised. Intended to
        be scheduled as a background task right after the connector is
        attached to the bot; irrelevant for bots that tick quickly (the
        handshake covers them) but essential for bots that haven't started.
        """
        if (
            self.exchange is None
            or not hasattr(self.exchange, "get_balance")
            or type(self.exchange).__name__ == "_PlaceholderExchangeForRestore"
        ):
            logger.debug(
                "Bot %s bootstrap_exchange_state: exchange not ready "
                "(placeholder or missing); will retry once real "
                "connector attaches.",
                self.bot_id,
            )
            return
        try:
            symbol = self.config.symbol
            target_asset = self.config.target_asset
            _bal = await self._get_balance(target_asset)
            _units = float(getattr(_bal, "total", 0) or _bal.free or 0)
            _ticker = await self._get_ticker(symbol)
            _price = float(getattr(_ticker, "last", 0) or 0)
            try:
                await self._refresh_quote_to_usd()
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "bootstrap_exchange_state",
                    type(_sup).__name__,
                    _sup,
                )

            _tracked_units_bootstrap = sum(
                float(lot.get("units", 0) or 0) for lot in self._main_lots
            )
            if _units >= 0:
                self._current_holdings = (
                    min(max(0.0, _units), _tracked_units_bootstrap)
                    if _tracked_units_bootstrap > 0
                    else 0.0
                )
                self._bootstrap_adopt_from_exchange(
                    max(0.0, _units), _tracked_units_bootstrap, _price, target_asset
                )
            if _price > 0:
                self.stats.current_price = _price
            if _price > 0 and self._current_holdings > 0:
                self.stats.position_value = (
                    self._current_holdings * _price * float(self._quote_to_usd or 1.0)
                )
            else:
                self.stats.position_value = 0.0
            logger.info(
                "Bot %s bootstrap_exchange_state: %s units=%.8f @ $%.8f "
                "quote_to_usd=%.4f (position_usd=$%.4f)",
                self.bot_id,
                target_asset,
                _units,
                _price,
                self._quote_to_usd,
                _units * _price * float(self._quote_to_usd or 1.0),
            )

            try:
                _refreshed = await self.refresh_exchange_position_health(force=True)
                if _refreshed:
                    logger.info(
                        "Bot %s bootstrap_exchange_state: position health "
                        "refreshed (realized=$%.4f, avg_entry=$%.8f, "
                        "trades=%d)",
                        self.bot_id,
                        self.stats.realized_pnl_exchange,
                        self.stats.avg_entry_exchange,
                        self.stats.exchange_trade_count,
                    )
            except Exception as _ph_exc:
                logger.warning(
                    "Bot %s bootstrap position-health refresh failed: %s "
                    "(will retry on first action tick)",
                    self.bot_id,
                    _ph_exc,
                )
            try:
                await self.sync_ytd_trade_count()
            except Exception as _ytd_exc:
                logger.warning(
                    "Bot %s bootstrap YTD trade-count sync failed: %s "
                    "(persisted counter retained)",
                    self.bot_id,
                    _ytd_exc,
                )
        except Exception as exc:
            logger.warning(
                "Bot %s bootstrap_exchange_state raised %s: %s "
                "(GUI will show pending until first tick)",
                self.bot_id,
                type(exc).__name__,
                exc,
            )

    @staticmethod
    def _reconcilable_units(value: Any, label: str) -> tuple[float | None, str | None]:
        """One units reading as a finite, NON-NEGATIVE float, or a reason.

        Returns (number, None) when usable, (None, reason) when
        refused, the same shape as `_positive_observed_quantity`
        (:3134), `_finite_state_number` (:3199) and `_sum_lot_units`
        (:3245). Returning the refusal instead of raising is what lets
        `_reconcile_holdings` decline the whole audit before it writes
        anything.

        The restore paths coerce the same field more loosely, with
        `float(lot.get("units", 0) or 0)` (:6910, :7985). That
        divergence is deliberate and it runs one way only: this reader
        refuses a strict superset of what they refuse, so a book they
        loaded can be declined here, and a book declined here is never
        written to. The reverse -- a book this reader accepts that they
        would reject -- cannot happen.

        `-0.0` is a zero and is normalised to `0.0`, so no caller
        formats a negative zero into a log line.

        `float(10 ** 400)` raises OverflowError, which is neither
        ValueError nor TypeError, so it is caught by name. Reaching for
        `math.isfinite` instead does not help: the conversion raises
        before `isfinite` is ever evaluated, and `json.loads` parses a
        400-digit literal into exactly that int.
        """
        if type(value) is not int and type(value) is not float:
            return None, (
                f"{label} must be exactly an int or a float, "
                f"not a {type(value).__name__}; got {value!r}"
            )
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None, f"{label} is not a number; got {value!r}"
        if not math.isfinite(number):
            return None, f"{label} must be finite; got {number!r}"
        if number < 0.0:
            return None, f"{label} must be >= 0; got {number!r}"
        return number + 0.0, None

    def _reconcilable_lot_book(self) -> tuple[list[float] | None, str | None]:
        """Every lot's units, coerced, in book order — or a reason.

        The per-lot values are returned rather than only their total
        because the drift-down branch multiplies them one by one.
        Deriving them a second time down there would let two passes
        disagree about one book.

        NOT `_sum_lot_units` (:3245), and the difference is deliberate
        in both directions. That helper refuses a lot with no "units"
        key; here such a lot counts as ZERO, which is what the restore
        paths' `.get` already does (:6910, :7985). Refusing it instead
        would leave a bot permanently unreconcilable over a lot that
        holds nothing. It also returns a total only, and a total cannot
        be multiplied back into a book. Its contract is pinned by the
        atomicity check in `apply_extractor_tranche_return`, so it is
        left exactly as it is.

        ONE unreadable lot refuses the whole book: the correction is a
        single ratio applied to every lot, so a lot that cannot be read
        cannot be corrected around.

        The caller totals this with `sum`, not with a `+=` loop,
        because those two do not agree — CPython's `sum` applies
        Neumaier compensation to floats. On ORCA's real 48-lot book
        `sum` gives 54.053407815409216 and an accumulator loop gives
        54.05340781540922, one ULP apart. `sum` is what :6910 and :7985
        use to derive the scalar, so the audited total comes out
        bit-identical to theirs.
        """
        per_lot: list[float] = []
        for _index, _lot in enumerate(self._main_lots):
            if not isinstance(_lot, dict):
                return None, (
                    f"_main_lots[{_index}] must be a lot dict; "
                    f"got a {type(_lot).__name__}"
                )
            _raw = _lot.get("units", 0.0)
            _units, _why = self._reconcilable_units(
                _raw if _raw else 0.0, f"_main_lots[{_index}]['units']"
            )
            if _units is None:
                return None, _why
            per_lot.append(_units)
        return per_lot, None

    def _claimable_exchange_units(
        self, exchange_units: float
    ) -> tuple[float, float, float]:
        """``(claimable, personal_hold, sibling_tracked)`` for this asset.

        Lifted verbatim out of the drift-UP branch of
        ``_reconcile_holdings`` so ``bootstrap_exchange_state`` asks the
        same question the same way. The rule is unchanged:

            claimable = exchange - personal_hold_qty - sibling_tracked

        Both subtrahends are operator/bot DECLARATIONS, not inferences,
        and they are what preserves the 2026-07-27 ETH/BTC protection.

        FAIL CLOSED. An unreadable sibling total returns ``inf`` for the
        siblings, which drives ``claimable`` negative and claims
        nothing. Under-claiming costs a log line; over-claiming spends
        the operator's coins.
        """
        _personal = max(
            0.0, float(getattr(self.config, "personal_hold_qty", 0.0) or 0.0)
        )
        _sib_units = 0.0
        _mgr = getattr(self, "_bot_manager", None)
        if _mgr is not None:
            try:
                _sib_units = max(
                    0.0,
                    float(
                        _mgr.sum_sibling_tracked_units(
                            self.bot_id, self.config.target_asset
                        )
                    ),
                )
            except Exception as _sib_exc:  # R28-OK: fail closed
                logger.warning(
                    "Bot %s claimable units: sibling total unreadable "
                    "(%s) — claiming nothing this pass.",
                    self.bot_id,
                    _sib_exc,
                )
                _sib_units = float("inf")
        return (exchange_units - _personal - _sib_units, _personal, _sib_units)

    def _bootstrap_adopt_from_exchange(
        self, exchange_units: float, book_units: float, price: float, asset: str
    ) -> float | None:
        """Raise a restored book to the wallet at startup, once.

        Same ownership rule as the periodic reconcile, and the same lot
        writer, so a restart cannot re-introduce the figure that
        reconcile just corrected. Returns the units added, or ``None``
        when nothing was adopted.

        It lives in its own method rather than inline because the two
        branches it carries pushed ``bootstrap_exchange_state`` past
        the complexity ceiling, and both belong to one idea.
        """
        if book_units <= 0:
            return None
        _claimable, _personal, _sib = self._claimable_exchange_units(exchange_units)
        _adopt = min(exchange_units, _claimable)
        _gain = self._book_reconciliation_lot(_adopt, book_units, price)
        if _gain is None:
            return None
        _foreign = max(0.0, exchange_units - self._current_holdings)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DRIFT UP (bootstrap): adopted the exchange balance. "
                f"internal={book_units:.8f} -> "
                f"{self._current_holdings:.8f} {asset} "
                f"(exchange={exchange_units:.8f}). Booked {_gain:.8f} "
                f"units as a reconciliation lot at ${float(price):.8f}. "
                + (
                    f"{_foreign:.8f} units left unclaimed (personal hold "
                    f"{_personal:.8f}, siblings {_sib:.8f})."
                    if _foreign > 1e-9
                    else "No units on this asset are spoken for elsewhere."
                )
            ),
        )
        logger.warning(
            "Bot %s bootstrap adopted %.8f %s from the exchange "
            "(book %.8f -> holdings %.8f, foreign %.8f)",
            self.bot_id,
            _gain,
            asset,
            book_units,
            self._current_holdings,
            _foreign,
        )
        return _gain

    def _book_reconciliation_lot(
        self, adopt_units: float, book_units: float, price: float
    ) -> float | None:
        """Write the top-up as a lot, then re-derive holdings from it.

        Returns the units added, or ``None`` when nothing was written.

        TWO THINGS THIS CLOSES, BOTH OF THEM IN THE ARITHMETIC.

        1. THE TOP-UP IS MEASURED FROM THE BOOK. The drift-UP branch
           measured it from ``internal_units``, which is
           ``max(scalar, book)``. Whenever the scalar leads the book
           those are different numbers, the lot written is short by the
           difference, and the invariant the adopt exists to keep --
           ``sum(l["units"] for l in _main_lots) == _current_holdings``
           -- comes out FALSE. Measured on the live BILL book with a
           scalar of 15000 against a 14131-unit book and a 15778-unit
           wallet: holdings 15778, book 14909, invariant_ok False. The
           delta is computed from the scalar and the scrum reads the
           book, so the two consumers disagree by 869 units.

        2. NO PRICE, NO LOT. The basis was written straight from
           ``stats.current_price`` with no test, and that field is 0.0
           on a bot that has not completed a priced tick -- a
           post-failure reconcile on a freshly restored bot reaches
           here. The same measurement books
           ``initial_buy_price: 0.0``, which is not a cheap entry, it
           is a lot that claims infinite profit against every price
           and can arm a sell that never should have armed. Refusing
           costs one cycle; the reconcile runs again.

        The scalar is re-derived by summing the book rather than
        assigned from ``adopt_units``, so the two counters agree bit
        for bit whatever the float addition did.
        """
        # NO READING IS NOT A QUANTITY. `nan` compares False against
        # every bound, so `nan <= 1e-9` falls THROUGH a guard written
        # as a comparison and writes a nan lot, a nan scalar and a nan
        # delta. The reconcile path cannot deliver one -- its inputs go
        # through `_reconcilable_lot_book` first -- but the bootstrap
        # path sums the book with a bare `float(lot.get(...))` and can.
        # A writer that is safe only when its caller validates is not
        # safe.
        for _reading in (adopt_units, book_units):
            try:
                if not math.isfinite(float(_reading)):
                    return None
            except (TypeError, ValueError):
                return None
        if adopt_units - book_units <= 1e-9:
            return None
        try:
            _basis = float(price)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(_basis) or _basis <= 0.0:
            return None
        _gain = adopt_units - book_units
        self._main_lots.append(
            {
                "units": _gain,
                "initial_buy_price": _basis,
                "operator_initiated": False,
                "reconciled_to_exchange": True,
            }
        )
        self._current_holdings = sum(
            float(lot.get("units", 0) or 0) for lot in self._main_lots
        )
        return _gain

    async def _reconcile_holdings(self, reason: str = "periodic") -> bool:
        """Re-fetch asset balance from the exchange and compare it to
        what this bot claims to hold. On drift above tolerance, log
        prominently and reset internal state to exchange reality.


        Returns True if reconciliation completed (with or without drift
        action). Returns False in three cases, all of which leave every
        counter and every lot untouched: the balance fetch itself
        failed (network blip; retry next scheduled interval), the
        exchange OMITTED the currency from its response so the venue
        holding is unknown rather than zero (`Balance.absent`), or one
        of the three inputs was outside the reconcilable domain
        (exactly an int or a float, finite, non-negative — see
        `_reconcilable_units`).

        Reason tags help the operator and post-hoc investigation know
        why reconciliation ran:
          "init"           — first-tick verification after bot start
          "periodic"       — every N ticks routine check
          "post_failure"   — after a trade attempt returned None
          "operator_req"   — explicitly requested via future GUI action
        """
        try:
            balance = await self._get_balance(self.config.target_asset)

            _venue_absent = bool(getattr(balance, "absent", False))
            _venue_raw = getattr(balance, "total", 0) or balance.free or 0.0
        except Exception as exc:
            logger.debug(
                "Bot %s reconcile fetch failed (%s): %s", self.bot_id, reason, exc
            )
            return False

        if _venue_absent:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"RECONCILE REFUSED ({reason}): exchange OMITTED "
                    f"{self.config.target_asset} from the balance "
                    f"response, so the venue holding is UNKNOWN, not "
                    f"zero. No lot was rescaled and no holdings were "
                    f"reset. Retrying next interval."
                ),
            )
            logger.warning(
                "Bot %s reconcile (%s) REFUSED — %s absent from exchange "
                "response; venue holding UNKNOWN, not zero. No lot was "
                "rescaled and no holdings were reset.",
                self.bot_id,
                reason,
                self.config.target_asset,
            )
            return False

        _lot_each, _why = self._reconcilable_lot_book()
        _readings: list[float] = []
        if _lot_each is not None:
            for _value, _label in (
                (_venue_raw, "exchange balance (total)"),
                (self._current_holdings, "_current_holdings"),
                (sum(_lot_each), "_main_lots total"),
            ):
                _number, _why = self._reconcilable_units(_value, _label)
                if _number is None:
                    break
                _readings.append(_number)
        if _lot_each is None or len(_readings) != 3:
            logger.warning(
                "Bot %s reconcile (%s) REFUSED — %s. No lot was "
                "rescaled and no holdings were reset.",
                self.bot_id,
                reason,
                _why,
            )
            return False
        exchange_units, _scalar_units, _lot_units = _readings
        internal_units = _lot_units if _lot_units > _scalar_units else _scalar_units

        drift_units = exchange_units - internal_units
        if internal_units > 0:
            drift_pct = abs(drift_units) / internal_units * 100.0
        elif exchange_units > 0:
            drift_pct = float("inf")
        else:
            drift_pct = 0.0

        _TOLERANCE_PCT = 0.5
        _tolerance_units = abs(internal_units) * _TOLERANCE_PCT / 100.0

        if abs(drift_units) <= _tolerance_units:
            logger.debug(
                "Bot %s reconcile (%s) aligned: internal=%.6f exchange=%.6f "
                "drift=%.4f (%.3f%%)",
                self.bot_id,
                reason,
                internal_units,
                exchange_units,
                drift_units,
                drift_pct,
            )
            return True

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"BALANCE DRIFT ({reason}): internal={internal_units:.6f} "
                f"exchange={exchange_units:.6f} "
                f"drift={drift_units:+.6f} ({drift_pct:.2f}%)."
            ),
        )
        # This line is emitted BEFORE either branch runs, so it states
        # the OBSERVATION only. It used to end "Resetting internal
        # state to exchange reality" and then the drift-UP branch
        # preserved instead -- two log lines one second apart saying
        # opposite things, 735 times on BILL alone. Each branch below
        # reports what it actually did.
        logger.warning(
            "Bot %s balance drift (%s): internal=%.6f exchange=%.6f "
            "drift=%+.6f (%.3f%%)",
            self.bot_id,
            reason,
            internal_units,
            exchange_units,
            drift_units,
            drift_pct,
        )

        if exchange_units < internal_units - 1e-9:
            if internal_units > 0 and self._main_lots:
                _ratio = exchange_units / internal_units
                for _lot, _units in zip(self._main_lots, _lot_each, strict=True):
                    _lot["units"] = _units * _ratio
                self._main_lots = [l for l in self._main_lots if l["units"] > 1e-12]
            self._current_holdings = exchange_units
        else:

            _surplus = max(0.0, exchange_units - internal_units)
            if _surplus > 1e-9:
                _claimable, _personal, _sib_units = self._claimable_exchange_units(
                    exchange_units
                )
                _adopt = min(exchange_units, _claimable)
                # v3.25.10 — measured from the BOOK, not from
                # `internal_units`. See `_book_reconciliation_lot`:
                # `internal_units` is `max(scalar, book)`, so a scalar
                # that leads the book wrote a lot short by the
                # difference and left `sum(lots) != _current_holdings`.
                _gain = _adopt - _lot_units
                _basis = float(
                    getattr(getattr(self, "stats", None), "current_price", 0.0) or 0.0
                )

                # ONE WRITER DECIDES, AND THE SENTENCE FOLLOWS IT.
                # The branch used to re-test the price itself, so the
                # message could describe an adopt the writer had
                # refused -- and `_basis` of `inf` passes `> 0`, is
                # refused inside the writer, and would then have
                # formatted `None` into the operator's line and raised
                # a TypeError out of the tick. The writer answers with
                # the units it wrote, or None, and the two branches
                # below read that answer.
                _written = (
                    self._book_reconciliation_lot(_adopt, _lot_units, _basis)
                    if _gain > 1e-9
                    else None
                )
                if _written is not None:
                    # Reconciliation lot. The units are real and on the
                    # exchange; only their cost basis is unknown, so it
                    # is booked at the price this reconcile ran at and
                    # flagged, rather than inventing a fill that never
                    # happened. The invariant every consumer relies on
                    # -- sum(_main_lots units) == _current_holdings --
                    # is what makes the delta computable, so the lot is
                    # appended in the same step that moves the scalar,
                    # and the scalar is re-derived from the book.
                    _gain = _written
                    _adopt = self._current_holdings
                    _foreign = max(0.0, exchange_units - _adopt)
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DRIFT UP ({reason}): adopted the exchange "
                            f"balance. internal={internal_units:.8f} -> "
                            f"{_adopt:.8f} {self.config.target_asset} "
                            f"(exchange={exchange_units:.8f}). Booked "
                            f"{_gain:.8f} units as a reconciliation lot "
                            f"at ${_basis:.8f}. "
                            + (
                                f"{_foreign:.8f} units left unclaimed "
                                f"(personal hold {_personal:.8f}, "
                                f"siblings {_sib_units:.8f})."
                                if _foreign > 1e-9
                                else "No units on this asset are spoken for "
                                "elsewhere."
                            )
                        ),
                    )
                    logger.info(
                        "Bot %s drift UP (%s): adopted %.8f (was %.8f, "
                        "exchange %.8f, personal %.8f, siblings %.8f)",
                        self.bot_id,
                        reason,
                        _adopt,
                        internal_units,
                        exchange_units,
                        _personal,
                        _sib_units,
                    )
                elif _gain > 1e-9:  # claimable, but the writer refused
                    # v3.25.10 — the units are claimable but there is no
                    # price to book them at. A lot at a zero basis is
                    # not a cheap entry; it reads as infinite profit
                    # against every price and can arm a sell. Say so and
                    # keep the position, rather than write a number that
                    # was never observed.
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DRIFT UP ({reason}): {_gain:.8f} "
                            f"{self.config.target_asset} on exchange is "
                            f"this bot's, but there is no usable price "
                            f"to book it at (internal={internal_units:.8f} "
                            f"exchange={exchange_units:.8f}). ADOPTION "
                            f"DEFERRED — stats.current_price reads "
                            f"{_basis:.8f}, and a lot booked without a "
                            f"real basis claims unlimited profit against "
                            f"every price. Retrying next cycle."
                        ),
                    )
                    logger.warning(
                        "Bot %s drift UP (%s): adoption of %.8f deferred "
                        "— stats.current_price is %.8f",
                        self.bot_id,
                        reason,
                        _gain,
                        _basis,
                    )
                else:
                    # Every surplus unit is spoken for. This is the
                    # 2026-07-27 case and it still refuses -- but it
                    # now says WHY, with the numbers that decided it.
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DRIFT UP ({reason}): {_surplus:.8f} "
                            f"{self.config.target_asset} on exchange is "
                            f"not this bot's (internal="
                            f"{internal_units:.8f} exchange="
                            f"{exchange_units:.8f}). Personal hold "
                            f"{_personal:.8f}, sibling bots "
                            f"{_sib_units:.8f}. Preserving internal "
                            f"state."
                        ),
                    )
                    logger.info(
                        "Bot %s drift UP (%s): surplus=%.8f fully "
                        "attributed elsewhere — preserved internal=%.8f",
                        self.bot_id,
                        reason,
                        _surplus,
                        internal_units,
                    )
        return True
