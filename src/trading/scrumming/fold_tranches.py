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
"""How many candles back TREND-HOLD reads. ``tick`` slices exactly this
many."""

_STRONG_TREND_MIN_BULL_CANDLES = 13
"""How many of them must close up before the reading is a strong trend."""


class FoldTrancheAccountingMixin:
    """Open, bound, top up, discharge, delist and count fold tranches.

    Every write here lands on the tranche book or a counter derived from
    it; nothing on this mixin reaches the exchange.
    """

    # Supplied by ScrummingBot at runtime; declared so a type
    # checker can resolve them. Annotations only: no attribute is
    # created and the runtime base stays `object`.
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
        This is the single definition of fold eligibility, called by both
        the FOLD_DIAG counter and the fold-back executor so the
        diagnostic can never report a different set than the one that
        fires.
        """
        return [
            t
            for t in self._fold_tranches
            if ticker_last <= float(t.get("ref", 0)) * otd_factor
        ]

    def _apply_scrum_fold_pct(
        self, _tranche_count_before: int, scrum_usd: float, scrum_asset: float
    ) -> None:
        """Scale the tranches THIS sell just appended by scrum_fold_pct.

        CALL IT BEFORE ``_top_up_remnant_fold_tranches``. The top-up
        merges this sale's money into an OLDER record, which sits
        outside the ``_tranche_count_before:`` slice. Merging first
        would let that money escape the ratio entirely.

        CALL IT BEFORE refreshing ``_fold_queue_usd``, so the derived
        scalar reports the queue that survived the ratio.

        Args:
            _tranche_count_before: ``len(self._fold_tranches)`` sampled
                before this sale's build loop ran. The slice from there
                to the end is exactly what this sale appended.
            scrum_usd: dollars this sale left with THIS bot, already net
                of Smart Wire routing, and the same figure the build
                loop divided.
            scrum_asset: units this sale sold, the same figure the build
                loop divided. The two together give the sale's own net
                rate, which is what tells scrum proceeds apart from
                wired-in money below.
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

        Returns the number removed.

        WHY THIS IS A METHOD. It was eleven statements inside ``tick``,
        and ``tick`` needs a live ticker, a populated TA engine and an
        exchange to reach them. So the one removal site on the fold
        queue that no test could drive was also the one whose counters
        were wrong. Issue #98 defect 4.

        WHAT A MALFORMED TRANCHE IS. ``ref`` is the price the scrum
        sold at, and every fold divides by it. A record whose ``ref``
        is missing, zero, negative or ``nan`` fails
        ``t.get("ref", 0) > 0`` -- ``nan`` because every comparison
        against ``nan`` is False -- and it would otherwise raise out of
        ``sum(t["usd"] / t["ref"])`` and end the cycle.

        WHICH COUNTERS MOVE, AND WHY THAT CHANGED.

        * ``_tranches_discarded_lifetime`` moves UP by the number
          removed. THIS IS THE FIX. The drop used to move
          ``_tranches_malformed_dropped`` and nothing else, and that
          counter is not a term in the reconciliation the Fold-Tranche
          panel prints -- ``created - closed - discarded == standing``.
          A removal that moves no term of that identity leaves the
          standing count one lower than the counters predict, per
          record, forever. It is a NEGATIVE-drift write site, and every
          other removal on this queue already moves a term:
          ``_settle_fold_plan`` moves ``closed``, ``clear_fold_tranches``
          and ``run_despawn_sweep`` and the detonation reset move
          ``discarded``, and ``_top_up_remnant_fold_tranches`` moves
          ``created`` down by exactly what it removes.

        * ``_tranches_malformed_dropped`` moves UP by the same number,
          and it is now a SUB-COUNT of ``discarded`` rather than a
          fourth term. It answers "how many of the discards were
          unreadable", which is what the panel row reading "Tranches
          dropped as malformed" claims.

        * ``_tranches_closed_lifetime`` does NOT move, and must not. A
          closed tranche is one that FOLDED BACK. ``ref <= 0`` means
          the record never held a price to fold against, so counting
          it as folded would re-introduce the exact conflation
          v3.24.44 split apart.

        NOT DONE HERE, AND NAMED SO IT IS NOT MISTAKEN FOR AN OMISSION:
        ``_fold_queue_usd`` is not recomputed. The pre-existing code did
        not recompute it either, and the derived scalar agreed with the
        summed tranche ``usd`` on all 38 live bots when the panel was
        evaluated, so nothing is measured wrong today. Moving it is a
        second verb.
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

        This was
        ``[t for t in self._fold_tranches if t not in _eligible]``, a
        VALUE compare against the admitted list. Under partial
        consumption the fold buys from SLICES, and a PART-consumed
        slice does not equal its source, so that line would have left
        the source in the queue holding its whole balance and the bot
        would have rebought the same money on every later fold. On a
        WHOLE take the slice does still compare equal, which is the
        second defect below rather than a saving grace.

        Each source gives up what the plan took from it. A source
        drained to nothing is removed, exactly as a whole consumption
        removed it before. A source with a balance left STAYS, carrying
        the untouched ``initial_buy_price`` and ``ref`` it had on the
        way in -- the operator's "a tranche that does not spend all of
        its money just sits there minus what left".

        Removal is BY IDENTITY, not by value. The old ``not in``
        deleted every tranche that compared equal to an admitted one,
        so two tranches holding identical numbers -- routine after the
        proportional ``scrum_fold_pct`` rescale, which writes the same
        figure onto each new tranche cut from one lot -- meant one buy
        silently retired two records.

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

        ``ref`` DOES blend, and it has to. Requiring a ``ref`` match too
        would make this dead code, because ``ref`` is a fill price and
        two fills are never equal. The blend is the one that preserves
        ``usd / ref``, the units-at-sale quantity the surplus step reads
        as ``asset_at_scrum``. Keeping the old ``ref`` would understate
        surplus; taking the new one would overstate it and invent
        compounding that did not happen.

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

        THE ONE READER of ``_last_trend_bull_candles``, which ``tick``
        writes as the number of the last 20 candles that closed up.

        ON TWO COUNTS, NOT ON THE SHARE. TREND-HOLD asks
        ``bull_count / 20 > 13 / 20``; this asks ``bull_count > 13``.
        Over the closed domain -- ``bull_count`` is an integer in
        [0, 20] -- the two answer identically, and the integer form
        cannot round at its own threshold.

        A bot that has not measured the market holds 0 and reads False,
        and an unreadable count reads False as well. The exception
        LOOSENS a bound, so its default has to be off.
        """
        _n = as_finite_float(getattr(self, "_last_trend_bull_candles", 0))
        return _n is not None and _n > _STRONG_TREND_MIN_BULL_CANDLES

    def _bound_new_fold_tranches(self, first_new_index: int) -> int:
        """One sell opens one fold tranche, unless the trend is strong.

        issue #133 unit 2, operator rule 2026-08-25: "We should never
        see more Fold tranches than Scrums that have occurred except
        during strong trends."

        WHERE THE COUNT CAME FROM. All three build loops -- the SCRUM,
        the DIST sell and ``_execute_manual_rebalance`` -- append ONE
        tranche PER ``_main_lots`` entry they consume, so that each
        lot's ``initial_buy_price`` travels with its own units.
        ``_main_lots`` gains an entry on every buy, so one sell that
        walks twelve lots opens twelve tranches and the panel counts
        twelve. Measured on the operator's saved state 2026-08-25:
        16,042 tranches opened against 445 recorded sells across 38
        bots, 37 of the 38 above 1.0, and CHIP alone at 4,925 against
        461 exchange trades counting BOTH sides.

        CALLED ONCE PER SELL, DIRECTLY AFTER ITS BUILD LOOP, and it
        carries the sell counter for that reason: a caller cannot take
        the exception and forget to count the sell, because both
        decisions are made here.

        WHAT IS CONSERVED, AND WHY IT CAN BE. Every record in this slice
        came from ONE sale, so all of them carry that sale's fill as
        ``ref`` and the same USD-per-unit rate. ``usd`` and ``units``
        are summed in the order the build loop wrote them and come back
        bit-identical; ``usd / ref``, the units-at-sale quantity the
        surplus step reads, comes with them.

        ``initial_buy_price`` IS THE ONE FIELD THAT DIFFERS ACROSS THE
        SLICE, and the merged record takes it UNITS-WEIGHTED. That
        conserves ``units x initial_buy_price`` -- the term summed as
        the cost basis behind unrealised P/L, and summed again as the
        skim cost basis inside ``_apply_scrum_fold_pct``. Measured over
        20,000 synthetic sales of up to 60 lots each, prices 1e-8 to
        61234.5: every conserved quantity within 4.4e-16 relative.

        TAKING THE MINIMUM WAS THE OTHER CANDIDATE and it is refused by
        measurement. It would honour ``_top_up_remnant_fold_tranches``'s
        rule against averaging a floor, and on the same sweep it
        understates the merged cost basis by up to 91.6% -- a bot
        reporting profit it did not make. The floor that rule protects
        is not read on this path: v3.16.43 took ``initial_buy_price``
        out of the fold eligibility gate, which is ``ticker.last <= ref
        x (1 - OTD/100)`` and carries no basis term.
        ``_top_up_remnant_fold_tranches`` merges across DIFFERENT sells
        at different fills and is left exactly as it was.

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
        # The sell counted here OPENED a tranche. A sell that reached
        # the build loop and appended nothing -- no lots left to
        # consume -- is not a scrum this rule has to answer for.
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

        # NAMED `_row_*` AND NOT `_t_*`. The SCRUM build loop already
        # binds `_t_usd` to `(_take / scrum_asset) * scrum_usd`, and
        # `ta_archetype` reads provenance per MODULE: a second meaning
        # for that name carries the first one's units into every
        # comparison here.
        _read = []
        for _t in _fresh:
            _row_units = as_finite_float(_t.get("units", 0.0))
            _row_usd = as_finite_float(_t.get("usd", 0.0))
            _row_ref = as_finite_float(_t.get("ref", 0.0))
            _row_basis = as_finite_float(_t.get("initial_buy_price", 0.0))
            _row = (_row_units, _row_usd, _row_ref, _row_basis)
            if any(_v is None for _v in _row):
                # A record this method cannot read is a record it must
                # not fold into another one. Merging would carry the
                # unreadable field into a good record and lose the bad
                # one; leaving the slice alone keeps the malformed row
                # where `_drop_malformed_fold_tranches` can see it.
                return 0
            if _row_units <= 0.0 or _row_ref <= 0.0:
                return 0
            _read.append(_row)

        # `math.fsum` and NOT `+=` or `sum`, on all four. This method
        # replaces N records with one, so the survivor's totals have to
        # be the totals of what it replaced, and an accumulation order
        # must not decide them. Measured on a 25-lot sale: a running
        # `+=` lands 2.8e-14 away from the true total on $147.03, which
        # is the accumulation drifting, not the money moving.
        # `math.fsum` is exactly rounded, so a second reader summing the
        # same records gets the same number.
        _usd = math.fsum(_r[1] for _r in _read)
        _units = math.fsum(_r[0] for _r in _read)
        _cost = math.fsum(_r[0] * _r[3] for _r in _read)
        _at_sale = math.fsum(_r[1] / _r[2] for _r in _read)
        _refs = {_r[2] for _r in _read}
        if _units <= 0.0 or _at_sale <= 0.0:
            return 0

        # One fill wrote every record here, so the set holds one price
        # and it is kept VERBATIM. Re-deriving it as ``usd / at_sale``
        # lands an ULP away and moves the ``ticker.last <= ref x
        # factor`` comparison at its own boundary. The derived form is
        # the fallback, and it is the one that preserves ``usd / ref``.
        _ref = _refs.pop() if len(_refs) == 1 else (_usd / _at_sale)
        _merged = dict(_fresh[0])
        _merged["usd"] = _usd
        _merged["units"] = _units
        _merged["ref"] = _ref
        _merged["initial_buy_price"] = _cost / _units
        if any(bool(_t.get("operator_initiated")) for _t in _fresh):
            # The operator touched part of this sale, so the surviving
            # record says so. The Fold Tranches table is the only
            # consumer of the tag; no gate, order or amount reads it.
            _merged["operator_initiated"] = True
        # REBOUND, not slice-assigned, and that is deliberate. This
        # method REMOVES records; it is a sibling of
        # `_top_up_remnant_fold_tranches` and
        # `_drop_malformed_fold_tranches` and it rebinds the way both of
        # them do. A subscript write to `_fold_tranches` is the shape
        # every build site uses, and the wiring scan in
        # `test_scrum_fold_pct_mirrored_on_every_path` reads it as one.
        self._fold_tranches = self._fold_tranches[:first_new_index] + [_merged]

        _removed = len(_fresh) - 1
        # These records were never separately opened, so the created
        # counter must not claim they were. Same reasoning as the
        # decrement in ``_top_up_remnant_fold_tranches``: leaving it up
        # breaks ``created - closed - discarded == standing``.
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
        whose ``ref`` and ``units`` are both finite numbers -- the same
        rows in the same order as ``_preview_fold_growth``, which sizes
        the buy. Runs after the fill, so it raises on no row.
        """

        def _rank(t) -> float:
            # Total order. A row that cannot yield a finite ref sorts last.
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

        WHAT THIS DOES NOT TOUCH, deliberately:
          * holdings, `_main_lots`, or any position — nothing is sold or
            bought, no order is placed
          * `_target_balance` or `_anchor_target_balance` — unlike
            detonation's full reset, the target is left exactly where it
            is
          * `_pending_wire_credits` — that is real routed income, not a
            tranche. See the warning below.


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

        issue #133 unit 3, operator directive 2026-08-25: "Lifetime
        tranche counts can be cleared since we are resetting to the new
        standard." The live CHIP bot carried opened 4925, closed 4813
        and discarded 91, all accumulated under rules that no longer
        apply.

        FOUR COUNTERS, FIVE FIGURES ON THE PANEL. Opened, closed,
        discarded and malformed-dropped are stored and are cleared here.
        The cycle close ratio is `closed / (created - discarded)`,
        computed on the panel from three of them, so it follows the
        reset without being a counter of its own.

        MALFORMED IS A SUB-COUNT OF DISCARDED, so clearing discarded and
        leaving it would publish a sub-count larger than the total it
        belongs to.

        THE `stats` MIRROR GOES TOO. `stats.tranches_discarded_lifetime`
        is a second copy of one of the four and is serialised into its
        own section of the state file, so a clear that skipped it would
        write 0 under `scrumming_state` and 91 under `stats`.

        WHAT THIS DOES NOT TOUCH: the standing `_fold_tranches` and the
        `_fold_queue_usd` they park, `_pending_wire_credits` and its
        ledger, `_wire_credits_discarded_lifetime`, the stack-side
        `_stack_created` and `_stack_discarded`, and every holding, lot,
        cost basis and target. This clears counters, not inventory.

        THE RESET STAMP IS NOT A DECORATION. The init handshake reads
        `_tranches_created_lifetime == 0` as "no scrum has ever fired"
        and adopts the exchange balance as the bot's opening position,
        REPLACING `_main_lots` with one lot at a single derived basis.
        Zeroing the counter alone would re-arm that at the next launch
        on a bot with thousands of scrums behind it. The stamp records
        that the zero was written by an operator, and the predicate
        reads it.

        A BOT WHOSE FOUR COUNTERS ARE ALREADY ZERO IS LEFT ALONE, stamp
        included. On that bot the zero is its real history, and stamping
        it would take the opening-position adoption away from the one
        bot that needs it.

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

        None is not an error. It is the answer for a record that carries
        no usable timestamp, and the despawn sweep treats it as "do not
        touch" rather than as zero or as infinity.

        `as_finite_float` carries the whole admission rule: exactly int
        or exactly float, and finite. `bool` is a subclass of `int`, so
        a stored `True` would otherwise be read as 1.0 and date the
        record to the epoch — an age of about 56 years, which every
        threshold would delist. A numeric string, a Decimal, None, an
        object with `__float__`, `nan` and the infinities all take the
        same no-timestamp path.

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

        A thin read of the shared rule in ``bot_container``, which the
        live-settings spinbox also reads, so the sweep and the control
        that sets it can never disagree about what a stored value means.
        """
        return despawn_threshold_days(self.config)

    def _despawn_aged_tranches(self, now: Optional[float] = None) -> dict:
        """Delist tranches older than ``config.tranche_despawn_days``.

        WHAT IT DOES WRITE, and why each is part of dropping the record
        rather than something extra: ``_fold_queue_usd`` is a DERIVED
        aggregate, recomputed at every other site that removes a fold
        tranche; leaving it stale would keep the tick's
        ``_fold_queue_usd == 0`` short-circuit and the panel's "Parked
        USD" both reporting money with no tranche behind it. And a
        delist is counted in ``_tranches_discarded_lifetime``, never in
        ``_tranches_closed_lifetime``, because a closed tranche is one
        that FOLDED. That split is what keeps
        ``created - closed - discarded == standing`` true.

        BOTH LEDGERS KEEP THAT INVARIANT, not the fold one alone. This
        sweep is the only site in src/ that removes a stack tranche, so
        ``_stack_discarded`` is incremented here beside
        ``_stack_created``. An earlier build dropped stack records and
        touched no counter at all, which left ``_stack_created``
        climbing against a shrinking standing list and drove the Stack
        panel's ``filled / created`` readout down permanently — red
        below 30% — with no discarded row to account for it. On this
        ledger the ``closed`` term is structurally zero: filling a stack
        tranche sets its ``status`` and LEAVES THE RECORD LISTED, so
        nothing else ever takes one out.

        THE ONE ASYMMETRY, and it is a refusal rather than a second
        policy. A Visible-mode stack tranche holds a resting LIMIT order
        on the exchange — ``status == "pending"`` with an ``order_id``.
        Dropping THAT record would leave a live order on the book with
        nothing tracking it, which is the single way this sweep could
        strand something and would falsify the "no order" claim above.
        Such a tranche is kept and counted. Invisible-mode tranches
        carry ``order_id=None`` and are delisted like any other record,
        as are filled and cancelled ones, whose orders are already
        terminal.

        IT CANNOT RAISE OUT OF THE TICK, and that is a requirement
        rather than a hope: the call site sits outside every ``try`` in
        ``tick``, so an exception here ends the tick. Every number this
        method reads — the threshold, both timestamps, the injected
        ``now``, the delisted USD total, the parked-credit total and
        BOTH discard counters — goes through
        ``as_finite_float`` or the shared threshold reader, which refuse
        `nan`, the infinities and out-of-range ints instead of
        converting them. An earlier build gated on exact type ALONE and
        `type(float("nan")) is float` is True, so `nan` passed the gate
        and `int(nan)` then raised ValueError from a site with no
        handler above it.

        THE QUEUE-TOTAL RECOMPUTE IS GUARDED TOO, and it therefore
        DIVERGES from the six sibling sites that recompute the same
        aggregate with ``float(t.get("usd", 0) or 0)``. Leaving it
        unguarded would falsify the paragraph above: a surviving
        tranche whose ``usd`` is a huge int makes ``float()`` raise
        from a site with no handler. Those six keep the old expression;
        putting all seven on one rule is a separate unit, named here
        and deliberately not done here.

        Args:
          now: wall-clock seconds to age against. Defaults to
            ``time.time()``; injected by the tests. A non-numeric or
            non-finite value makes every age unmeasurable, so the sweep
            delists nothing and says so.

        Returns:
          A report of what the sweep did.
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
