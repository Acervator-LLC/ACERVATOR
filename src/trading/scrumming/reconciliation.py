"""Holdings reconciliation for ScrummingBot: the venue is authoritative.

``ReconciliationEngineMixin`` pulls the balance, the trade count and the
position health from the exchange, then books any difference into
``_main_lots`` without placing an order.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

from .sizing import priced_usd

logger = logging.getLogger("acervator.scrumming")

# The value the per-bot P/L surfaces draw as their empty marker.
UNREALISED_NO_READING = 0.0

# The values the venue-sourced trade counters and the YTD dollar sums draw when
# the walk finished without counting every window.
TRADE_COUNT_NO_READING = 0
YTD_USD_NO_READING = 0.0


class ReconciliationEngineMixin:
    """Reconcile ``_current_holdings`` and ``_main_lots`` against the exchange.

    A disagreement is settled by adopting the exchange reading;
    ``_book_reconciliation_lot`` writes the difference as a lot flagged
    ``reconciled_to_exchange``.
    """

    # Supplied by ScrummingBot at runtime; annotations only, no attribute
    # is created.
    _bus: Any
    _current_holdings: float
    _fill_history: Any
    _get_balance: Callable[..., Any]
    _get_ticker: Callable[..., Any]
    _main_lots: list[dict]
    _quote_to_usd: float
    _refresh_quote_to_usd: Callable[..., Any]
    bot_id: Any
    config: Any
    exchange: Any
    stats: Any

    # Written by the YTD walk itself on its first complete reading; nothing is
    # held on disk, so a restart walks every window again.
    _ytd_settled_segments: list[dict]
    _ytd_full_walk_ts: float

    EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC = 300.0

    async def fetch_fill_history(self) -> Optional[list]:
        """Every fill for ``config.symbol`` from ``_fill_history``, refreshed; None when the exchange answers None."""
        if self._fill_history is None:
            from ...exchange.fill_history import FillHistory

            self._fill_history = FillHistory(self.config.symbol)
        return await self._fill_history.refresh(self.exchange)

    async def fetch_spot_positions(self) -> Optional[dict]:
        """The venue's open spot positions keyed by asset from ``exchange.get_spot_positions``, or None when the venue did not answer.

        An empty mapping is an answer: the venue holds no open spot position. None
        is the absence of an answer, so ``refresh_exchange_position_health`` can
        tell a flat position from a venue it could not read.
        """
        _get = getattr(self.exchange, "get_spot_positions", None)
        if _get is None:
            return None
        try:
            _positions = await _get()
        except Exception as _exc:
            logger.warning(
                "Bot %s %s: get_spot_positions raised, so the venue's "
                "unrealised figure has no reading this refresh: %s",
                self.bot_id,
                self.config.symbol,
                _exc,
            )
            return None
        if _positions is None:
            return None
        return dict(_positions)

    def _log_basis_check(self, venue_basis: float, health: Any) -> str:
        """Log ``venue_basis`` against ``health.open_lot_basis_usd`` and ``health.cost_basis_total_usd``; returns the closer method's name."""
        _fifo = float(health.open_lot_basis_usd)
        _avg = float(health.cost_basis_total_usd)
        _scale = max(abs(float(venue_basis)), 1e-9)
        _fifo_gap = abs(_fifo - float(venue_basis)) / _scale
        _avg_gap = abs(_avg - float(venue_basis)) / _scale
        _closer = "fifo" if _fifo_gap <= _avg_gap else "average"
        logger.info(
            "Bot %s basis check %s: venue=%.4f fifo_open_lots=%.4f (%.2f%% off) "
            "average=%.4f (%.2f%% off) closer=%s",
            self.bot_id,
            self.config.symbol,
            float(venue_basis),
            _fifo,
            _fifo_gap * 100.0,
            _avg,
            _avg_gap * 100.0,
            _closer,
        )
        return _closer

    async def refresh_exchange_position_health(self, force: bool = False) -> bool:
        """Refresh the exchange-pulled fields on ``stats``.

        The fill-derived fields are written only when ``FillHistory.complete``
        reads True, so a walk that stopped short leaves the last complete
        reading in place and ``stats.fill_history_complete`` False; the header
        strip's realised column draws its empty marker while any answered bot
        reads False.

        Returns True when a fetch updated ``stats``; returns False when
        ``EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC`` throttles the call without
        ``force``, and when ``self.exchange`` cannot serve ``get_my_trades``.
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

            _trades = await self.fetch_fill_history()
            if _trades is None:
                return False
            _complete = bool(getattr(self._fill_history, "complete", False))
            self.stats.fill_history_complete = _complete
            _asset_base = self.config.symbol.split("/")[0]
            _ph = compute_position_health(_trades, _asset_base)

            if _complete:
                self.stats.realized_pnl_exchange = float(_ph.realized_pnl_usd)
                self.stats.fees_paid_exchange = float(_ph.fees_paid_total)
            else:
                logger.warning(
                    "Bot %s %s: %d fills, history incomplete; realised P/L and "
                    "fees keep their last complete reading of %.4f and %.4f",
                    self.bot_id,
                    self.config.symbol,
                    len(_trades),
                    float(self.stats.realized_pnl_exchange),
                    float(self.stats.fees_paid_exchange),
                )
            _positions = await self.fetch_spot_positions()
            _venue = None if _positions is None else _positions.get(_asset_base)
            if _venue is None:
                _dropped = float(self.stats.unrealised_pnl)
                self.stats.unrealised_pnl = UNREALISED_NO_READING
                if _positions is None:
                    logger.warning(
                        "Bot %s %s: the venue answered no spot positions; the "
                        "unrealised figure drops its last reading of %.4f "
                        "rather than stand as current",
                        self.bot_id,
                        self.config.symbol,
                        _dropped,
                    )
                if _complete:
                    self.stats.avg_entry_exchange = float(_ph.avg_entry)
                    self.stats.cost_basis_total_exchange = float(
                        _ph.cost_basis_total_usd
                    )
            else:
                self.stats.avg_entry_exchange = float(_venue.avg_entry_price)
                self.stats.cost_basis_total_exchange = float(_venue.cost_basis_usd)
                self.stats.unrealised_pnl = float(_venue.unrealized_pnl_usd)
                self._log_basis_check(_venue.cost_basis_usd, _ph)
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
    YTD_TRADE_WINDOW_SEC = 30 * 24 * 3600.0

    YTD_BULK_READ_ATTEMPTS = 2

    YTD_SETTLE_LAG_SEC = 7 * 24 * 3600.0
    YTD_FULL_REWALK_SEC = 3600.0

    async def _await_ytd_read_slot(self) -> float:
        """Seconds ``exchange.await_bulk_read_slot`` waited before this window's call.

        The walk is a bulk reader on the connector every bot of a venue shares,
        so each window's request waits here for a free call queue. An exchange
        without the method, and a wait that raises, both answer 0.0 and the
        request goes ahead, so a connector that does not serialise its calls is
        unaffected.
        """
        _slot = getattr(self.exchange, "await_bulk_read_slot", None)
        if _slot is None:
            return 0.0
        try:
            _waited = float(await _slot())
        except (AttributeError, TypeError, ValueError) as _slot_exc:
            logger.debug(
                "Bot %s YTD bulk-read slot wait skipped: %s: %s",
                self.bot_id,
                type(_slot_exc).__name__,
                _slot_exc,
            )
            return 0.0
        if _waited > 0:
            logger.debug(
                "Bot %s YTD walk waited %.3fs for a free venue call queue",
                self.bot_id,
                _waited,
            )
        return _waited

    @staticmethod
    def _is_bulk_queue_full(exc: BaseException) -> bool:
        """True when ``exc`` is a connector's refusal at its call-queue cap."""
        try:
            from ...exchange.ccxt_connector import CCXTQueueFullError
        except ImportError:
            return False
        return isinstance(exc, CCXTQueueFullError)

    async def _ytd_window_page(self, cursor: float, end_ms: int) -> list:
        """One window's ``get_my_trades`` rows, each attempt behind ``_await_ytd_read_slot``.

        The rows, their order and their count are the connector's own answer to
        the same request the walk made before the wait was added.
        ``YTD_BULK_READ_ATTEMPTS`` bounds the attempts and
        ``_is_bulk_queue_full`` decides which refusal earns another; every other
        exception, and a refusal on the last attempt, propagate, so
        ``sync_ytd_trade_count`` reports no reading rather than count this
        window short.
        """
        _attempt = 0
        while True:
            await self._await_ytd_read_slot()
            _attempt += 1
            try:
                return list(
                    await self.exchange.get_my_trades(
                        self.config.symbol,
                        since=cursor,
                        limit=self.YTD_TRADE_PAGE_LIMIT,
                        params={"paginate": True, "until": end_ms},
                    )
                    or []
                )
            except Exception as _page_exc:
                if _attempt < self.YTD_BULK_READ_ATTEMPTS and self._is_bulk_queue_full(
                    _page_exc
                ):
                    logger.debug(
                        "Bot %s YTD window ending %d refused at the call-queue "
                        "cap on attempt %d; waiting for room again",
                        self.bot_id,
                        end_ms,
                        _attempt,
                    )
                    continue
                raise

    @staticmethod
    def _venue_order_key(trade: Any, fill_key: Any) -> tuple:
        """The venue's order identifier for one fill, or the fill's own key when the venue gave none.

        ccxt sets the unified ``order`` key on every ``fetch_my_trades`` row and
        ``CCXTConnector.get_my_trades`` keeps the row in ``Trade.raw``, so the
        several fills of one order share one key here. A fill the venue did not
        group counts as an order of its own. The leading tag keeps an order
        identifier from ever colliding with a fill identifier.
        """
        _raw = getattr(trade, "raw", None)
        if isinstance(_raw, dict):
            _oid = _raw.get("order")
            if _oid:
                return ("order", str(_oid))
        return ("fill", fill_key)

    @staticmethod
    def _ytd_fill_row(trade: Any, fill_key: Any, order_key: tuple) -> tuple:
        """One fill as the walk accounts it: its keys and the venue's own amount, price and side.

        The venue's figures are carried unconverted, so a replayed row and a
        freshly read one reach ``_ytd_tally_fill`` in the same form and a row
        the venue sent uncoercible still counts as a fill.
        """
        return (
            fill_key,
            order_key,
            getattr(trade, "amount", 0),
            getattr(trade, "price", 0),
            getattr(trade, "side", None),
        )

    def _ytd_tally_fill(
        self,
        row: tuple,
        seen_ids: set,
        order_keys: set,
        scrum_fold_usd: list,
        quote_to_usd: float,
    ) -> bool:
        """Count one ``_ytd_fill_row`` into the walk's running figures; False when already counted.

        A fill key already in ``seen_ids`` is the same fill read twice and
        changes nothing. Otherwise the fill joins ``seen_ids``, its order key
        joins ``order_keys``, and ``amount * price * quote_to_usd`` is added to
        index 0 of ``scrum_fold_usd`` for a sale and index 1 for a buy. A
        replayed row and a freshly read one take this one path, so the dollar
        figures depend on the order of the fills and not on which windows were
        read this walk.
        """
        _fill_key, _order_key, _amount, _price, _side = row
        if _fill_key in seen_ids:
            return False
        seen_ids.add(_fill_key)
        order_keys.add(_order_key)
        try:
            _usd = float(_amount or 0) * float(_price or 0) * quote_to_usd
            _side_str = str(getattr(_side, "value", _side) or "").lower()
            if "sell" in _side_str:
                scrum_fold_usd[0] += _usd
            elif "buy" in _side_str:
                scrum_fold_usd[1] += _usd
        except (TypeError, ValueError) as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_ytd_tally_fill",
                type(_sup).__name__,
                _sup,
            )
        return True

    def _ytd_resume_point(self, now: float) -> tuple[list, float]:
        """The settled windows this walk replays, and the span start it must read from.

        A window is settled when its own request counted it whole and its end
        is older than ``YTD_SETTLE_LAG_SEC``, so a fill the venue reports or
        amends inside that lag is read again rather than replayed. The held
        windows are dropped altogether once ``YTD_FULL_REWALK_SEC`` has passed
        since the last walk that started at the anchor, which bounds how long a
        fill arriving later than the lag can go uncounted. The lag is positive,
        so the replayed span never reaches ``now`` and every walk still makes at
        least one request; a venue refusing that request raises as before.
        """
        _segments = list(getattr(self, "_ytd_settled_segments", ()) or ())
        _last_full_walk = float(getattr(self, "_ytd_full_walk_ts", 0.0) or 0.0)
        if not _segments or now - _last_full_walk >= self.YTD_FULL_REWALK_SEC:
            return [], self.YTD_TRADE_ANCHOR_UTC
        _settle_horizon = now - self.YTD_SETTLE_LAG_SEC
        _replayed: list = []
        for _segment in _segments:
            if float(_segment["end"]) > _settle_horizon:
                break
            _replayed.append(_segment)
        if not _replayed:
            return [], self.YTD_TRADE_ANCHOR_UTC
        return _replayed, float(_replayed[-1]["next_cursor"])

    def _ytd_settled_cache(
        self, replayed: list, read: list, settle_horizon: float
    ) -> list:
        """The windows the next walk may replay: ``replayed`` plus the settled leading run of ``read``.

        The run stops at the first window that read short or that ends after
        ``settle_horizon``, so what is held stays one contiguous span starting
        at the anchor and the next walk reads everything past it.
        """
        _cache = list(replayed)
        for _segment in read:
            if not _segment["whole"] or float(_segment["end"]) > settle_horizon:
                break
            _cache.append(
                {
                    "cursor": _segment["cursor"],
                    "end": _segment["end"],
                    "next_cursor": _segment["next_cursor"],
                    "rows": _segment["rows"],
                }
            )
        return _cache

    def _ytd_next_cursor(
        self, page: list, cursor: float, end: float
    ) -> tuple[float, bool]:
        """Where the next request starts, and whether this window was counted whole.

        A page holding ``YTD_TRADE_PAGE_LIMIT`` rows means the venue had more
        inside the window than it would serve, so the walk resumes at the newest
        fill instead of stepping past the remainder. A full page carrying no
        timestamp later than ``cursor`` cannot be resumed; that window's
        remainder goes uncounted, the walk logs a warning naming it, and the
        second element comes back False.
        """
        if len(page) < self.YTD_TRADE_PAGE_LIMIT:
            return end, True
        _newest = cursor
        for _tr in page:
            try:
                _ts = float(getattr(_tr, "timestamp", 0.0) or 0.0)
            except (TypeError, ValueError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_ytd_next_cursor",
                    type(_sup).__name__,
                    _sup,
                )
                continue
            if _ts > _newest:
                _newest = _ts
        if cursor < _newest < end:
            return _newest, True
        logger.warning(
            "Bot %s YTD walk truncated inside window [%.0f..%.0f]: the venue "
            "served %d rows at its page limit and none carries a timestamp "
            "later than the window start, so the rest of that window is "
            "not counted",
            self.bot_id,
            cursor,
            end,
            len(page),
        )
        return end, False

    async def sync_ytd_trade_count(self) -> Optional[int]:
        """Walk ``get_my_trades`` from the YTD anchor to the present in 30-day windows.

        The accounted span always starts at the anchor, but only the windows
        ``_ytd_resume_point`` leaves unsettled are requested; the settled ones
        are replayed from the fills the last walk read, so the request count
        follows the unsettled tail and not the distance from the anchor. One
        trade is one order the venue filled, so the walk counts distinct venue
        order identifiers and returns that figure; the distinct fill count goes
        to ``stats.exchange_fill_count`` beside it. Every request goes through
        ``_ytd_window_page``, which waits for a free venue call queue first, so
        the walk does not hold the connector's worker against the balance,
        ticker, open-order and candle reads the running platform polls.

        Each fill, replayed or freshly read, is counted by ``_ytd_tally_fill``
        in window order, so the five figures are the same whichever windows
        this walk requested.

        A walk that counted every window writes the venue's own numbers over
        ``stats.exchange_trade_count``, ``stats.total_trades``,
        ``stats.ytd_scrummed_usd`` and ``stats.ytd_folded_usd``, upwards or
        downwards. A walk that skipped a window's remainder has no complete
        reading, so all five figures drop to their no-reading markers rather
        than leave the stored numbers standing as current.

        ``None`` comes back when ``self.exchange`` cannot serve
        ``get_my_trades``, when the walk raises, or when the walk read short.
        """
        if self.exchange is None:
            return None
        if not hasattr(self.exchange, "get_my_trades"):
            return None
        _persisted = int(getattr(self.stats, "total_trades", 0) or 0)
        import time as _t

        _now = _t.time()
        _window_s = self.YTD_TRADE_WINDOW_SEC
        _settle_horizon = _now - self.YTD_SETTLE_LAG_SEC
        _replayed, _cursor = self._ytd_resume_point(_now)
        _read_from = _cursor
        _seen_ids: set = set()
        _order_keys: set = set()
        _every_window_whole = True
        _requests = 0
        _scrum_fold_usd = [0.0, 0.0]
        _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        for _segment in _replayed:
            for _row in _segment["rows"]:
                self._ytd_tally_fill(
                    _row, _seen_ids, _order_keys, _scrum_fold_usd, _qrate
                )
        _read: list = []
        try:
            while _cursor < _now:
                _end = min(_cursor + _window_s, _now)
                _end_ms = int(_end * 1000)
                _page = await self._ytd_window_page(_cursor, _end_ms)
                _rows: list = []
                _new = 0
                for _index, _tr in enumerate(_page):
                    _tid = getattr(_tr, "id", None) or ("unkeyed", _cursor, _index)
                    _row = self._ytd_fill_row(
                        _tr, _tid, self._venue_order_key(_tr, _tid)
                    )
                    _rows.append(_row)
                    if self._ytd_tally_fill(
                        _row, _seen_ids, _order_keys, _scrum_fold_usd, _qrate
                    ):
                        _new += 1
                logger.debug(
                    "Bot %s YTD request %d: [%.0f..%.0f] returned=%d "
                    "new=%d cumulative_unique=%d",
                    self.bot_id,
                    _requests + 1,
                    _cursor,
                    _end,
                    len(_page),
                    _new,
                    len(_seen_ids),
                )
                _requests += 1
                _next_cursor, _window_whole = self._ytd_next_cursor(
                    _page, _cursor, _end
                )
                _every_window_whole = _every_window_whole and _window_whole
                _read.append(
                    {
                        "cursor": _cursor,
                        "end": _end,
                        "next_cursor": _next_cursor,
                        "rows": tuple(_rows),
                        "whole": _window_whole,
                    }
                )
                _cursor = _next_cursor
            _fill_count = len(_seen_ids)
            _order_count = len(_order_keys)
            _ytd_scrum_usd, _ytd_fold_usd = _scrum_fold_usd
            logger.info(
                "Bot %s YTD sync via chunked-window walk: "
                "symbol=%s returned %d unique fills in %d venue orders "
                "over %d requests spanning [%.0f..%.0f] "
                "(replayed_windows=%d read_from=%.0f scrummed=$%.2f "
                "folded=$%.2f every_window_whole=%s)",
                self.bot_id,
                self.config.symbol,
                _fill_count,
                _order_count,
                _requests,
                self.YTD_TRADE_ANCHOR_UTC,
                _cursor,
                len(_replayed),
                _read_from,
                _ytd_scrum_usd,
                _ytd_fold_usd,
                _every_window_whole,
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
        if not _every_window_whole:
            logger.warning(
                "Bot %s YTD walk skipped a window's remainder, so it holds no "
                "complete reading; the trade count and the YTD dollars drop "
                "their last reading of %d and $%.2f/$%.2f rather than stand "
                "as current",
                self.bot_id,
                _prev_exc,
                float(getattr(self.stats, "ytd_scrummed_usd", 0.0) or 0.0),
                float(getattr(self.stats, "ytd_folded_usd", 0.0) or 0.0),
            )
            self.stats.exchange_trade_count = TRADE_COUNT_NO_READING
            self.stats.exchange_fill_count = TRADE_COUNT_NO_READING
            self.stats.total_trades = TRADE_COUNT_NO_READING
            self.stats.ytd_scrummed_usd = YTD_USD_NO_READING
            self.stats.ytd_folded_usd = YTD_USD_NO_READING
            return None
        self.stats.exchange_trade_count = _order_count
        self.stats.exchange_fill_count = _fill_count
        self.stats.total_trades = _order_count
        self.stats.ytd_scrummed_usd = _ytd_scrum_usd
        self.stats.ytd_folded_usd = _ytd_fold_usd
        self._ytd_settled_segments = self._ytd_settled_cache(
            _replayed, _read, _settle_horizon
        )
        if not _replayed:
            self._ytd_full_walk_ts = _now
        import time as _t

        self.stats.exchange_data_fresh_ts = _t.time()
        logger.info(
            "Bot %s YTD trade-count sync: venue_orders=%d venue_fills=%d "
            "platform_tally=%d prev_venue_orders=%d",
            self.bot_id,
            _order_count,
            _fill_count,
            _persisted,
            _prev_exc,
        )
        return _order_count

    async def bootstrap_exchange_state(self) -> None:
        """One-shot live pull of exchange state after the connector attaches.

        Sets ``_current_holdings``, ``stats.current_price`` and
        ``stats.position_value``, calls ``_bootstrap_adopt_from_exchange``,
        and logs every exception without raising.
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
                self.stats.position_value = priced_usd(
                    self._current_holdings, _price, float(self._quote_to_usd or 1.0)
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
        """One units reading as a finite, non-negative float, or a reason.

        Returns ``(number, None)`` when usable and ``(None, reason)`` when
        refused; ``-0.0`` normalises to ``0.0``, and ``OverflowError`` from
        ``float`` is caught by name alongside ``TypeError`` and ``ValueError``.
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

        One lot that ``_reconcilable_units`` refuses returns ``(None, reason)``
        for the whole book; a lot with no ``units`` key counts as zero, and
        ``_reconcile_holdings`` totals the returned list with ``sum``.
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

        ``claimable`` is ``exchange_units`` less ``config.personal_hold_qty``
        and ``sum_sibling_tracked_units``; an unreadable second total becomes
        ``inf``, which drives ``claimable`` negative and claims nothing.
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
            except Exception as _sib_exc:
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

        Calls ``_claimable_exchange_units`` and ``_book_reconciliation_lot``,
        the pair ``_reconcile_holdings`` also uses, and returns the units
        added or ``None``.
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
        """Write the top-up as a lot, then re-derive ``_current_holdings``.

        The lot holds ``adopt_units`` less ``book_units`` at a ``price`` that
        must be finite and above zero, and ``_current_holdings`` is then
        re-summed from ``_main_lots``.
        """
        # nan compares False against every bound, so both readings go
        # through math.isfinite.
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
        """Compare ``_current_holdings`` and ``_main_lots`` against the venue.

        ``reason`` tags every log line with ``periodic`` or ``post_failure``,
        and the return is True once the comparison completes, False when the
        balance fetch raises, when ``Balance.absent`` marks the currency
        missing from the response, or when ``_reconcilable_units`` refuses an
        input.
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
        # Observation only; each branch below logs what it did.
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
                # Measured from _lot_units; internal_units is
                # max(scalar, book) and would write a short lot.
                _gain = _adopt - _lot_units
                _basis = float(
                    getattr(getattr(self, "stats", None), "current_price", 0.0) or 0.0
                )

                # _book_reconciliation_lot returns the units it wrote;
                # both branches below read that, not _basis.
                _written = (
                    self._book_reconciliation_lot(_adopt, _lot_units, _basis)
                    if _gain > 1e-9
                    else None
                )
                if _written is not None:
                    # Booked at this pass's price and flagged
                    # reconciled_to_exchange; no fill is invented.
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
                elif _gain > 1e-9:
                    # A lot at a zero basis reads as unlimited profit
                    # against every price and can arm a sell.
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
                    # The whole surplus is attributed to personal hold
                    # plus other bots, so nothing is claimed.
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
