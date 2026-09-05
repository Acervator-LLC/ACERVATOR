"""Fold-tranche accounting for ScrummingBot: create, bound, consume, clear.

Owns the queued fold-tranche records, the discharge order the buy path
reads, and the lifetime counters that summarise them. Places no orders.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Optional

from ..bot_container import as_finite_float, despawn_threshold_days

logger = logging.getLogger("acervator.scrumming")


_STRONG_TREND_CANDLES = 20
"""Candle count TREND-HOLD reads; ``ScrummingBot.tick`` slices exactly this many."""

_STRONG_TREND_MIN_BULL_CANDLES = 13
"""How many of them must close up before the reading is a strong trend."""


class FoldTrancheAccountingMixin:
    """Open, bound, top up, discharge, remove and count fold tranches.

    Every write here lands on the tranche book or a counter derived from
    it; nothing on this mixin reaches the exchange.
    """

    # Annotation only: ScrummingBot supplies each name at runtime and no
    # attribute is created here.
    _bus: Any
    _fold_queue_usd: float
    _fold_tranches: list[dict]
    _last_trend_bull_candles: int
    _scrum_sells_lifetime: int
    _stack_discarded: int
    _stack_tranches: list[dict]
    _tranches_closed_lifetime: int
    _tranches_counters_reset_ts: float
    _tranches_created_lifetime: int
    _tranches_discarded_lifetime: Any
    _tranches_malformed_dropped: int
    bot_id: Any
    config: Any
    stats: Any

    def _fold_eligible_tranches(self, ticker_last: float, otd_factor: float) -> list:
        """Fold-queue tranches eligible for fold-back at ``ticker_last``.

        A tranche is eligible when ``ticker_last <= ref * otd_factor``.
        The FOLD_DIAG diagnostic and the fold-back executor in
        ``tick_phases`` both call this, so the two cannot report
        different sets.
        """
        return [
            t
            for t in self._fold_tranches
            if ticker_last <= float(t.get("ref", 0)) * otd_factor
        ]

    def _apply_scrum_fold_pct(
        self, _tranche_count_before: int, scrum_usd: float, scrum_asset: float
    ) -> None:
        """Scale the tranches this sell just appended by scrum_fold_pct.

        Runs before ``_top_up_remnant_fold_tranches``, which merges this
        sale's money into an older record outside the slice, and before
        ``_fold_queue_usd`` is refreshed. Money outside the sale's own
        rate is wired-in credit and keeps its full USD.

        Args:
            _tranche_count_before: ``len(self._fold_tranches)`` sampled
                before this sale's build loop ran. The slice from there
                to the end is exactly what this sale appended.
            scrum_usd: dollars this sale left with THIS bot, already net
                of Smart Wire routing, and the same figure the build
                loop divided.
            scrum_asset: units this sale sold, the same figure the build
                loop divided. The two give the sale's own net rate.
        """
        _fold_pct = max(0, min(100, int(getattr(self.config, "scrum_fold_pct", 100))))
        _new_tranches = self._fold_tranches[_tranche_count_before:]
        if _fold_pct < 100 and _new_tranches:
            _fold_frac = _fold_pct / 100.0
            _rate_known = scrum_asset > 0
            _unit_rate = (scrum_usd / scrum_asset) if _rate_known else 0.0
            _skim_usd = 0.0
            _skim_cost_basis = 0.0
            _queued_usd = 0.0
            for _t in _new_tranches:
                _full_usd = _t["usd"]
                _full_units = _t["units"]
                _scrummed_usd = (
                    min(max(_full_units * _unit_rate, 0.0), _full_usd)
                    if _rate_known
                    else _full_usd
                )
                _wire_usd = _full_usd - _scrummed_usd
                _t["usd"] = _wire_usd + _scrummed_usd * _fold_frac
                _t["units"] = _full_units * _fold_frac
                _skim_units = _full_units * (1 - _fold_frac)
                _skim_proceeds = _scrummed_usd * (1 - _fold_frac)
                _skim_usd += _skim_proceeds
                _skim_cost_basis += _skim_units * _t["initial_buy_price"]
                _queued_usd += _t["usd"]
            _skim_profit = _skim_usd - _skim_cost_basis
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD RATIO: scrum_fold_pct={_fold_pct}% — "
                    f"queued ${_queued_usd:.4f} for "
                    f"fold, retired ${_skim_usd:.4f} as cash "
                    f"(realised profit ${_skim_profit:+.4f}). "
                    f"Cash buffer preserved against further drops."
                ),
            )

    def _plan_fold_consumption(
        self, eligible: list, cap_remaining: float
    ) -> tuple[list, list, int]:
        """Decide what this fold cycle takes from each tranche.

        Args:
          eligible: price-eligible tranches, already ordered
            highest-``initial_buy_price``-first by the caller.
          cap_remaining: room left under the per-cycle growth cap.

        Returns:
          (plan, slices, part-consumed count). ``plan`` is a list of
          ``(source tranche, usd taken, units taken)``.
        """
        plan: list[tuple[dict, float, float]] = []
        slices: list[dict] = []
        running_usd = 0.0
        partial_count = 0
        for _t in eligible:
            room = cap_remaining - running_usd
            if room <= 1e-12:
                break
            tranche_usd = float(_t.get("usd", 0) or 0)
            tranche_units = float(_t.get("units", 0) or 0)
            if tranche_usd <= 0.0 or tranche_units <= 0.0:
                continue
            if tranche_usd <= room + 1e-9:
                take_usd = tranche_usd
                take_units = tranche_units
            else:
                take_usd = room
                take_units = tranche_units * (take_usd / tranche_usd)
                partial_count += 1
            slices.append(
                {
                    "usd": take_usd,
                    "units": take_units,
                    "ref": float(_t.get("ref", 0) or 0),
                    "initial_buy_price": _t["initial_buy_price"],
                    "created_ts": _t.get("created_ts", 0.0),
                }
            )
            plan.append((_t, take_usd, take_units))
            running_usd += take_usd
        return plan, slices, partial_count

    def _drop_malformed_fold_tranches(self) -> int:
        """Remove every queued tranche whose ``ref`` is not above zero.

        ``ref`` is the price the scrum sold at and every fold divides by
        it, so a record whose ``ref`` is missing, zero, negative or
        ``nan`` would raise out of ``sum(t["usd"] / t["ref"])`` and end
        the cycle. ``nan`` fails ``t.get("ref", 0) > 0`` because every
        comparison against ``nan`` is False.

        Each removal raises ``_tranches_discarded_lifetime``, which is a
        term of the reconciliation the Fold-Tranche panel prints,
        ``created - closed - discarded == standing``. It also raises
        ``_tranches_malformed_dropped``, a sub-count of the discards
        behind the panel row "Tranches dropped as malformed". The closed
        counter stays still: a closed tranche is one that folded back,
        and ``ref <= 0`` means this record never held a price to fold
        against.

        ``_fold_queue_usd`` is not recomputed here.

        Returns the number removed.
        """
        _malformed = [t for t in self._fold_tranches if not (t.get("ref", 0) > 0)]
        if not _malformed:
            return 0
        _dropped = len(_malformed)
        self._tranches_malformed_dropped = (
            int(getattr(self, "_tranches_malformed_dropped", 0) or 0) + _dropped
        )
        self._tranches_discarded_lifetime = (
            int(getattr(self, "_tranches_discarded_lifetime", 0) or 0) + _dropped
        )
        try:
            self.stats.tranches_discarded_lifetime = self._tranches_discarded_lifetime
        except AttributeError as exc:
            logger.debug("_drop_malformed_fold_tranches: stats mirror failed: %s", exc)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"FOLD GUARD: dropping {_dropped} malformed "
                f"tranche(s) with ref<=0. Operator visibility: "
                f"{_malformed}. Malformed-dropped now "
                f"{self._tranches_malformed_dropped}, and these "
                f"are counted as DISCARDED, never as closed."
            ),
        )
        self._fold_tranches = [t for t in self._fold_tranches if (t.get("ref", 0) > 0)]
        return _dropped

    def _settle_fold_plan(self, plan: list) -> tuple[int, int]:
        """Take from each source tranche what the plan says.

        Each source gives up the USD and units the plan took from it. A
        source drained to nothing is removed BY IDENTITY, so two records
        holding identical numbers -- routine after the proportional
        ``scrum_fold_pct`` rescale -- cannot retire together. A source
        with a balance left stays, keeping the ``initial_buy_price`` and
        ``ref`` it came in with, and is tagged ``fold_partial_spent``.

        The fold-back path in ``tick_phases`` adds what this removes to
        ``_tranches_closed_lifetime``.

        Args:
          plan: ``(source tranche, usd taken, units taken)`` triples,
            as returned by ``_plan_fold_consumption``.

        Returns:
          (records removed from the queue, records drained to nothing).
        """
        pre_remove = len(self._fold_tranches)
        spent: set[int] = set()
        for src, took_usd, took_units in plan:
            src["usd"] = max(0.0, float(src.get("usd", 0) or 0) - took_usd)
            src["units"] = max(0.0, float(src.get("units", 0) or 0) - took_units)
            if src["usd"] <= 1e-9 or src["units"] <= 1e-12:
                spent.add(id(src))
            else:
                src["fold_partial_spent"] = True
        self._fold_tranches = [t for t in self._fold_tranches if id(t) not in spent]
        return pre_remove - len(self._fold_tranches), len(spent)

    def _top_up_remnant_fold_tranches(
        self, first_new_index: int, bb_lower: float, bb_upper: float
    ) -> tuple[int, float]:
        """Move a sell's new tranche money into a part-spent tranche.

        A candidate must match on ``initial_buy_price`` and sit inside
        this tick's Bollinger band; ``ref`` is a fill price, so requiring
        a ``ref`` match too would make this dead code. The survivor takes
        the blended ``ref`` that preserves ``usd / ref``, the
        units-at-sale quantity the surplus step reads as
        ``asset_at_scrum``.

        Args:
          first_new_index: index in ``_fold_tranches`` where this
            sell's own tranches start. Records before it are the
            candidates; records from it on are the new money.
          bb_lower: lower Bollinger band this tick. 0.0 when the tick
            had no BB reading.
          bb_upper: upper Bollinger band this tick.

        Returns:
          (tranches merged away, USD moved).
        """
        if not (bb_upper > bb_lower > 0.0):
            return 0, 0.0
        if first_new_index <= 0:
            return 0, 0.0
        _candidates = self._fold_tranches[:first_new_index]
        _fresh = self._fold_tranches[first_new_index:]
        _merged_away: set[int] = set()
        _merged_n = 0
        _merged_usd = 0.0
        for _new_t in _fresh:
            _new_usd = float(_new_t.get("usd", 0) or 0)
            _new_units = float(_new_t.get("units", 0) or 0)
            _new_ref = float(_new_t.get("ref", 0) or 0)
            if _new_usd <= 0.0 or _new_units <= 0.0 or _new_ref <= 0.0:
                continue
            _new_ibp = float(_new_t.get("initial_buy_price", 0.0) or 0.0)
            _best = None
            _best_ref = 0.0
            for _cand in _candidates:
                if not _cand.get("fold_partial_spent"):
                    continue
                if float(_cand.get("usd", 0) or 0) <= 0.0:
                    continue
                if float(_cand.get("initial_buy_price", 0.0) or 0.0) != _new_ibp:
                    continue
                _c_ref = float(_cand.get("ref", 0) or 0)
                if not (bb_lower <= _c_ref <= bb_upper):
                    continue
                if _best is None or _c_ref < _best_ref:
                    _best = _cand
                    _best_ref = _c_ref
            if _best is None:
                continue
            _b_usd = float(_best.get("usd", 0) or 0)
            _b_ref = float(_best.get("ref", 0) or 0)
            _units_at_sale = (_b_usd / _b_ref) + (_new_usd / _new_ref)
            _best["usd"] = _b_usd + _new_usd
            _best["units"] = float(_best.get("units", 0) or 0) + _new_units
            _best["ref"] = _best["usd"] / _units_at_sale
            _merged_away.add(id(_new_t))
            _merged_n += 1
            _merged_usd += _new_usd
        if not _merged_away:
            return 0, 0.0
        self._fold_tranches = [
            t for t in self._fold_tranches if id(t) not in _merged_away
        ]
        self._tranches_created_lifetime = max(
            0, int(self._tranches_created_lifetime) - _merged_n
        )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"FOLD TOP-UP: ${_merged_usd:.4f} from this sell "
                f"went INTO {_merged_n} part-spent tranche(s) "
                f"instead of opening new ones — same "
                f"initial_buy_price, lowest ref inside the BB "
                f"range ${bb_lower:.8f}..${bb_upper:.8f}. "
                f"{len(self._fold_tranches)} tranche(s) open."
            ),
        )
        return _merged_n, _merged_usd

    def _strong_trend_now(self) -> bool:
        """Is the market in a strong trend, on the TREND-HOLD reading.

        Reads ``_last_trend_bull_candles``, which ``ScrummingBot.tick``
        writes as the number of the last ``_STRONG_TREND_CANDLES``
        candles that closed up.

        TREND-HOLD compares the share against
        ``_STRONG_TREND_MIN_BULL_SHARE``; this compares the count against
        ``_STRONG_TREND_MIN_BULL_CANDLES``. Over the closed integer
        domain [0, 20] the two answer identically.

        A bot that has not measured the market holds 0, and an
        unreadable count reads False as well, because the exception this
        answers loosens a bound.
        """
        _n = as_finite_float(getattr(self, "_last_trend_bull_candles", 0))
        return _n is not None and _n > _STRONG_TREND_MIN_BULL_CANDLES

    def _bound_new_fold_tranches(self, first_new_index: int) -> int:
        """One sell opens one fold tranche, unless the trend is strong.

        All three build loops -- the SCRUM, the DIST sell and
        ``_execute_manual_rebalance`` -- append one tranche per
        ``_main_lots`` entry they consume, so one sell that walks twelve
        lots opens twelve records. This merges that slice back to one.

        Called once per sell, directly after its build loop, and it
        carries ``_scrum_sells_lifetime``, so a caller cannot take the
        strong-trend exception and forget to count the sell.

        Every record in the slice came from ONE sale, so all carry that
        sale's fill as ``ref`` and the same USD-per-unit rate.
        ``initial_buy_price`` is the one field that differs, and the
        survivor takes it units-weighted, conserving
        ``units x initial_buy_price`` -- the cost basis behind unrealised
        P/L and behind the skim in ``_apply_scrum_fold_pct``. Taking the
        minimum instead understates that basis by up to 91.6% on a
        20,000-sale sweep, and ``initial_buy_price`` is not a term of
        fold eligibility, which is ``ticker.last <= ref x (1 - OTD/100)``.

        Args:
          first_new_index: index in ``_fold_tranches`` where this sell's
            own records start. Everything before it belongs to earlier
            sells and is not touched.

        Returns:
          The number of records removed. 0 when this sell opened fewer
          than two, and 0 under the strong-trend exception.
        """
        _fresh = self._fold_tranches[first_new_index:] if first_new_index >= 0 else []
        if not _fresh:
            return 0
        # Only a sell that appended a tranche is counted; one that found
        # no lot to consume is not a scrum this rule answers for.
        _sells = int(getattr(self, "_scrum_sells_lifetime", 0) or 0)
        self._scrum_sells_lifetime = _sells + 1
        if len(_fresh) < 2:
            return 0
        if self._strong_trend_now():
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD TRANCHE BOUND LIFTED: "
                    f"{self._last_trend_bull_candles} of the last "
                    f"{_STRONG_TREND_CANDLES} candles closed up, over "
                    f"the {_STRONG_TREND_MIN_BULL_CANDLES} that make a "
                    f"strong trend, so this sell keeps its "
                    f"{len(_fresh)} per-lot tranche(s)."
                ),
            )
            return 0

        # `_row_*` and not `_t_*`: `ta_archetype` reads provenance per
        # module, and `tick_phases` already binds `_t_usd` to a rate.
        _read = []
        for _t in _fresh:
            _row_units = as_finite_float(_t.get("units", 0.0))
            _row_usd = as_finite_float(_t.get("usd", 0.0))
            _row_ref = as_finite_float(_t.get("ref", 0.0))
            _row_basis = as_finite_float(_t.get("initial_buy_price", 0.0))
            _row = (_row_units, _row_usd, _row_ref, _row_basis)
            if any(_v is None for _v in _row):
                # Leaving the slice alone keeps the unreadable row where
                # `_drop_malformed_fold_tranches` can remove it.
                return 0
            if _row_units <= 0.0 or _row_ref <= 0.0:
                return 0
            _read.append(_row)

        # `math.fsum` is exactly rounded, so accumulation order cannot
        # decide the survivor's totals; a running `+=` drifts 2.8e-14.
        _usd = math.fsum(_r[1] for _r in _read)
        _units = math.fsum(_r[0] for _r in _read)
        _cost = math.fsum(_r[0] * _r[3] for _r in _read)
        _at_sale = math.fsum(_r[1] / _r[2] for _r in _read)
        _refs = {_r[2] for _r in _read}
        if _units <= 0.0 or _at_sale <= 0.0:
            return 0

        # Kept verbatim: re-deriving lands an ULP away and moves the
        # `ticker.last <= ref x factor` comparison at its boundary.
        _ref = _refs.pop() if len(_refs) == 1 else (_usd / _at_sale)
        _merged = dict(_fresh[0])
        _merged["usd"] = _usd
        _merged["units"] = _units
        _merged["ref"] = _ref
        _merged["initial_buy_price"] = _cost / _units
        if any(bool(_t.get("operator_initiated")) for _t in _fresh):
            # Only the Fold Tranches table reads this tag; no order or
            # amount does.
            _merged["operator_initiated"] = True
        self._fold_tranches = self._fold_tranches[:first_new_index] + [_merged]

        _removed = len(_fresh) - 1
        # Never separately opened, so `created` comes back down; leaving
        # it up breaks `created - closed - discarded == standing`.
        _created = int(getattr(self, "_tranches_created_lifetime", 0) or 0)
        self._tranches_created_lifetime = max(0, _created - _removed)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"FOLD TRANCHE BOUND: this sell's {len(_fresh)} per-lot "
                f"tranche(s) opened as ONE record -- ${_usd:.4f} over "
                f"{_units:.6f} units at ref ${_ref:.8f}, cost basis "
                f"${_merged['initial_buy_price']:.8f}. "
                f"{self._scrum_sells_lifetime} sell(s) have opened "
                f"tranches; {len(self._fold_tranches)} open."
            ),
        )
        return _removed

    def _fold_discharge_order(self) -> list[dict]:
        """Queued tranches in discharge order; unreadable rows omitted.

        Sorts ``_fold_tranches`` in place by ``ref`` descending, rows
        whose ``ref`` is not a finite number last. Returns only the rows
        whose ``ref`` and ``units`` are both finite numbers, in the
        ref-descending order ``_preview_fold_growth`` used to size the
        buy. Returns an empty list when no row is readable.
        """

        def _rank(t) -> float:
            # A row that cannot yield a finite ref sorts last.
            if not isinstance(t, dict):
                return float("-inf")
            try:
                _ref = float(t.get("ref", 0.0) or 0.0)
            except (TypeError, ValueError, OverflowError):
                return float("-inf")
            return _ref if math.isfinite(_ref) else float("-inf")

        self._fold_tranches.sort(key=_rank, reverse=True)

        _readable: list[dict] = []
        for _t in self._fold_tranches:
            if not isinstance(_t, dict):
                continue
            try:
                _ref = float(_t.get("ref", 0.0) or 0.0)
                _units = float(_t.get("units", 0.0) or 0.0)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(_ref) and math.isfinite(_units):
                _readable.append(_t)
        return _readable

    def clear_fold_tranches(self, reason: str = "operator") -> dict:
        """Discard every queued fold tranche. Trades nothing.

        Leaves holdings, `_main_lots`, `_target_balance`,
        `_anchor_target_balance` and `_pending_wire_credits` alone.
        Parked wire credits are routed income rather than tranches, so
        the emitted message warns when any remain.

        Returns a report of what was discarded. Never raises.
        """
        tranches = list(self._fold_tranches or [])
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "count": len(tranches),
            "usd": round(sum(float(t.get("usd", 0) or 0) for t in tranches), 8),
            "units": round(sum(float(t.get("units", 0) or 0) for t in tranches), 8),
            "pending_wire_credits": round(
                float(getattr(self, "_pending_wire_credits", 0.0) or 0.0), 8
            ),
            "reason": str(reason),
        }
        if not tranches:
            return report

        self._fold_tranches = []
        self._fold_queue_usd = 0.0
        self._tranches_discarded_lifetime = (
            int(getattr(self, "_tranches_discarded_lifetime", 0) or 0) + report["count"]
        )

        try:
            self.stats.tranches_discarded_lifetime = self._tranches_discarded_lifetime
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_fold_tranches: stats mirror failed: %s", exc)

        try:
            _warn = ""
            if report["pending_wire_credits"] > 1e-9:
                _warn = (
                    f" WARNING: ${report['pending_wire_credits']:.4f} "
                    f"of pending wire credits remain parked, and "
                    f"clearing has OPENED the absorb window — the "
                    f"next scrum will dump all of it into a single "
                    f"tranche."
                )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD TRANCHES CLEARED ({reason}): discarded "
                    f"{report['count']} tranche(s) holding "
                    f"${report['usd']:.4f} against "
                    f"{report['units']:.8f} units. No trade was "
                    f"placed; holdings and target balance are "
                    f"unchanged.{_warn}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_fold_tranches: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared %d fold tranche(s) ($%.4f, %.8f units) "
            "reason=%s pending_wire_credits=$%.4f",
            self.bot_id,
            report["count"],
            report["usd"],
            report["units"],
            reason,
            report["pending_wire_credits"],
        )
        return report

    def clear_lifetime_tranche_counters(self, reason: str = "operator") -> dict:
        """Reset the four fold-tranche lifetime counters to zero.

        Opened, closed, discarded and malformed-dropped are the four
        stored counters and are cleared together; malformed is a
        sub-count of discarded, so clearing one without the other would
        publish a sub-count larger than its total. The panel's cycle
        close ratio, `closed / (created - discarded)`, is computed from
        three of them and follows the reset.

        `stats.tranches_discarded_lifetime` is a second copy serialised
        into its own section of the state file, so it is cleared too.

        `_tranches_counters_reset_ts` is stamped because the init
        handshake in `tick_phases` reads `_tranches_created_lifetime ==
        0` with no stamp as a bot that has never scrummed, and adopts
        the exchange balance as its opening position, replacing
        `_main_lots` with one lot at a single derived basis. A bot whose
        four counters are already zero is left alone, stamp included,
        because on that bot the zero is its real history.

        Untouched: the standing `_fold_tranches` and the
        `_fold_queue_usd` they park, `_pending_wire_credits` and its
        ledger, `_wire_credits_discarded_lifetime`, the stack-side
        `_stack_created` and `_stack_discarded`, and every holding, lot,
        cost basis and target.

        Returns a report of the four values destroyed. Never raises.
        """
        _before = {
            "created": int(
                as_finite_float(getattr(self, "_tranches_created_lifetime", 0)) or 0.0
            ),
            "closed": int(
                as_finite_float(getattr(self, "_tranches_closed_lifetime", 0)) or 0.0
            ),
            "discarded": int(
                as_finite_float(getattr(self, "_tranches_discarded_lifetime", 0)) or 0.0
            ),
            "malformed": int(
                as_finite_float(getattr(self, "_tranches_malformed_dropped", 0)) or 0.0
            ),
        }
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "before": dict(_before),
            "cleared": sum(_before.values()),
            "open_tranches": len([t for t in (self._fold_tranches or [])]),
            "reset_ts": float(getattr(self, "_tranches_counters_reset_ts", 0.0) or 0.0),
            "reason": str(reason),
        }
        if report["cleared"] <= 0:
            return report

        self._tranches_created_lifetime = 0
        self._tranches_closed_lifetime = 0
        self._tranches_discarded_lifetime = 0
        self._tranches_malformed_dropped = 0
        self._tranches_counters_reset_ts = float(time.time())
        report["reset_ts"] = self._tranches_counters_reset_ts

        try:
            self.stats.tranches_discarded_lifetime = 0
        except Exception as exc:  # noqa: BLE001 - telemetry mirror only
            logger.debug(
                "clear_lifetime_tranche_counters: stats mirror failed: %s", exc
            )

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"LIFETIME TRANCHE COUNTERS CLEARED ({reason}): "
                    f"opened {_before['created']}, closed "
                    f"{_before['closed']}, discarded "
                    f"{_before['discarded']}, malformed-dropped "
                    f"{_before['malformed']} are now zero. No tranche, "
                    f"no parked credit and no holding was touched; "
                    f"{report['open_tranches']} tranche(s) remain in "
                    f"the queue."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
            logger.debug("clear_lifetime_tranche_counters: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared lifetime tranche counters "
            "(opened=%d closed=%d discarded=%d malformed=%d) reason=%s "
            "open_tranches=%d",
            self.bot_id,
            _before["created"],
            _before["closed"],
            _before["discarded"],
            _before["malformed"],
            reason,
            report["open_tranches"],
        )
        return report

    @staticmethod
    def _tranche_age_seconds(tranche: dict, field: str, now: float) -> Optional[float]:
        """Age of one tranche in seconds, or None when it has no age.

        None is the answer for a record with no usable timestamp, and
        the despawn sweep leaves such a record alone rather than reading
        it as zero or as infinity.

        `as_finite_float` admits exactly int or exactly float, and
        finite. `bool` is a subclass of `int`, so a stored `True` would
        otherwise read as 1.0 and date the record to the epoch. A
        numeric string, a Decimal, None, an object with `__float__`,
        `nan` and the infinities all take the no-timestamp path.

        Args:
          tranche: one fold or stack tranche record.
          field: ``created_ts`` on the fold side, ``opened_ts`` on the
            stack side. Each ledger ages on its own field.
          now: the wall-clock second to measure against.

        Returns:
          Age in seconds, which may be negative for a future-dated
          stamp, or None when there is no usable timestamp.
        """
        _ts = as_finite_float(tranche.get(field))
        if _ts is None or _ts <= 0:
            return None
        return now - _ts

    def _despawn_threshold_days(self) -> int:
        """This bot's despawn threshold in whole days; 0 means off.

        Reads the shared ``despawn_threshold_days`` in ``bot_container``,
        which the live-settings spinbox also reads, so the sweep and the
        spinbox cannot disagree about what a stored value means.
        """
        return despawn_threshold_days(self.config)

    def _despawn_aged_tranches(self, now: Optional[float] = None) -> dict:
        """Remove tranches older than ``config.tranche_despawn_days``.

        Removing a fold tranche recomputes ``_fold_queue_usd``, the
        derived aggregate behind the tick's ``_fold_queue_usd == 0``
        short-circuit and the panel's "Parked USD", and counts the
        record in ``_tranches_discarded_lifetime``, never in
        ``_tranches_closed_lifetime``, because a closed tranche is one
        that FOLDED. That split keeps
        ``created - closed - discarded == standing`` true.

        This is the only site in src/ that removes a stack tranche, so
        ``_stack_discarded`` moves here beside ``_stack_created``, which
        holds the Stack panel's ``filled / created`` readout to the same
        invariant. On that ledger the ``closed`` term is structurally
        zero: filling a stack tranche sets its ``status`` and leaves the
        record listed.

        An aged stack tranche with ``status == "pending"`` and an
        ``order_id`` holds a resting LIMIT order on the exchange. It is
        kept and counted, because removing it would leave that order on
        the book with nothing tracking it. Invisible-mode tranches carry
        ``order_id=None``, and filled and cancelled orders are already
        terminal, so those records go.

        The call site sits outside every ``try`` in ``tick``, so an
        exception here would end the tick. Every number read goes
        through ``as_finite_float`` or ``despawn_threshold_days``, which
        refuse `nan`, the infinities and out-of-range ints rather than
        converting them. That includes the queue-total recompute, so it
        differs from the six other sites that write the same aggregate
        with ``float(t.get("usd", 0) or 0)``.

        Args:
          now: wall-clock seconds to age against. Defaults to
            ``time.time()``; injected by the tests. A non-numeric or
            non-finite value makes every age unmeasurable, so the sweep
            removes nothing and says so.

        Returns:
          A report of what the sweep did, keyed ``fold_delisted``,
          ``stack_delisted``, ``stack_kept_live_order``, ``ageless_kept``
          and ``usd_delisted``.
        """
        _days = self._despawn_threshold_days()
        report = {
            "threshold_days": _days,
            "fold_delisted": 0,
            "stack_delisted": 0,
            "stack_kept_live_order": 0,
            "ageless_kept": 0,
            "usd_delisted": 0.0,
        }
        if _days <= 0:
            return report

        _now = time.time() if now is None else as_finite_float(now)
        if _now is None:
            logger.warning(
                "Bot %s: despawn sweep delisted nothing — `now` was %r, "
                "which is not a finite number, so no age is measurable",
                self.bot_id,
                now,
            )
            return report
        _cutoff = _days * 86400.0

        _fold_keep = []
        for _t in self._fold_tranches or []:
            _age = self._tranche_age_seconds(_t, "created_ts", _now)
            if _age is None:
                report["ageless_kept"] += 1
                _fold_keep.append(_t)
            elif _age >= _cutoff:
                report["fold_delisted"] += 1
                _usd = as_finite_float(_t.get("usd", 0))
                if _usd is not None:
                    report["usd_delisted"] += _usd
            else:
                _fold_keep.append(_t)

        _stack_keep = []
        for _t in self._stack_tranches or []:
            _age = self._tranche_age_seconds(_t, "opened_ts", _now)
            if _age is None:
                report["ageless_kept"] += 1
                _stack_keep.append(_t)
            elif _age < _cutoff:
                _stack_keep.append(_t)
            elif _t.get("status") == "pending" and _t.get("order_id"):
                report["stack_kept_live_order"] += 1
                _stack_keep.append(_t)
            else:
                report["stack_delisted"] += 1

        if not (report["fold_delisted"] or report["stack_delisted"]):
            return report

        if report["fold_delisted"]:
            self._fold_tranches = _fold_keep
            self._fold_queue_usd = sum(
                (as_finite_float(_t.get("usd", 0)) or 0.0) for _t in self._fold_tranches
            )
            self._tranches_discarded_lifetime = (
                int(
                    as_finite_float(getattr(self, "_tranches_discarded_lifetime", 0))
                    or 0.0
                )
                + report["fold_delisted"]
            )
            try:
                self.stats.tranches_discarded_lifetime = (
                    self._tranches_discarded_lifetime
                )
            except AttributeError as exc:
                logger.debug("despawn: stats mirror failed: %s", exc)
        if report["stack_delisted"]:
            self._stack_tranches = _stack_keep
            self._stack_discarded = (
                int(as_finite_float(getattr(self, "_stack_discarded", 0)) or 0.0)
                + report["stack_delisted"]
            )

        _parked = as_finite_float(getattr(self, "_pending_wire_credits", 0.0)) or 0.0
        _warn = ""
        if not self._fold_tranches and _parked > 1e-9:
            _warn = (
                f" WARNING: ${_parked:.4f} of pending wire credits "
                f"remain parked and the fold queue is now empty, "
                f"which has OPENED the absorb window — the next "
                f"scrum will dump all of it into a single tranche."
            )
        _skipped = ""
        if report["stack_kept_live_order"]:
            _skipped = (
                f" {report['stack_kept_live_order']} aged stack "
                f"tranche(s) KEPT: they hold resting exchange "
                f"orders, and delisting a record that owns a "
                f"live order would strand it."
            )
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"TRANCHES DESPAWNED (>= {_days}d): delisted "
                    f"{report['fold_delisted']} fold tranche(s) "
                    f"holding ${report['usd_delisted']:.4f} and "
                    f"{report['stack_delisted']} stack tranche(s). "
                    f"No order was placed or cancelled; holdings, "
                    f"cost basis and target balance are "
                    f"unchanged.{_skipped}{_warn}"
                ),
            )
        except AttributeError as exc:
            logger.debug("despawn: log emit failed: %s", exc)

        logger.info(
            "Bot %s: despawned %d fold + %d stack tranche(s) at >= %d "
            "days (kept %d ageless, %d with live orders)",
            self.bot_id,
            report["fold_delisted"],
            report["stack_delisted"],
            _days,
            report["ageless_kept"],
            report["stack_kept_live_order"],
        )
        return report
