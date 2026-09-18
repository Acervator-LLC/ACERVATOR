"""Validation Mode: YTD trades snapped to Stone Tablet candles, gates rerun.

``snap_trades`` puts each ``YtdTrade`` on the tablet candle whose period holds
it and ``coverage`` reports how many could not be placed and over what period.
``rerun_context`` rebuilds a ``GateContext`` from that candle and the recorded
``GateRow`` fixture, ``latch`` evaluates the shipped scrum and fold chains on
it, and ``compare_row`` puts the rerun's nineteen ``gate_vocabulary`` lights
beside the recorded ones. ``run`` drives the whole pass and reports agreement,
never profit and never a trade count.
"""

from __future__ import annotations

import bisect
import logging
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence

from ..exchange.ytd_trade_store import SIDE_SELL
from ..trading.gate_chain import (
    GateContext,
    build_scrumming_fold_chain,
    build_scrumming_scrum_chain,
)
from ..trading.gate_vocabulary import gate_light_row, unknown_blockers
from ..trading.scrumming.sizing import target_delta_pct
from .fleet_source import LIVE_ORIGIN, SimBot

if TYPE_CHECKING:
    from .back_test import SimTrade

logger = logging.getLogger("acervator.simulator.validation")

#: The candle count live reads. ``ScrummingBot`` asks ``get_ohlcv`` for 100.
RERUN_WINDOW_CANDLES = 100

#: Below this the voting engine and the Bollinger window have too few candles.
MIN_RERUN_CANDLES = 30

#: Used when a tablet holds too few rows for a gap to be measured.
FALLBACK_INTERVAL_MS = 300_000

#: ``ScrummingBot`` compares ``bb_pos`` against this midline.
BB_MIDLINE = 0.50

#: ``detect_bb_proximity`` is called with this, matching ``ScrummingBot.tick``.
BB_CONSOLIDATION_THRESHOLD = 3.0

#: How far a recorded gate row may sit from a fill and still describe it.
GATE_MATCH_WINDOW_MS = 300_000

#: How far back ``tape_lag`` searches for the window a recorded reading came
#: from.
LAG_SEARCH_CANDLES = 120

#: ``gate.log`` stores ``bb_pos`` to four places, so a gap this small is a
#: match.
LAG_EXACT_GAP = 1e-4

#: How many rows ``run`` measures the lag on. The search costs one Bollinger
#: pass per offset.
LAG_SAMPLE_ROWS = 60

SNAPPED = "snapped"
NO_TABLET = "no_tablet"
BEFORE_FIRST_CANDLE = "before_first_candle"
AFTER_LAST_CANDLE = "after_last_candle"
INSIDE_GAP = "inside_gap"
SHORT_WINDOW = "short_window"

UNSNAPPED_REASONS = (
    NO_TABLET,
    BEFORE_FIRST_CANDLE,
    AFTER_LAST_CANDLE,
    INSIDE_GAP,
    SHORT_WINDOW,
)

NO_YTD_FILE = "no_ytd_file"
NO_BOT_TABLET = "no_tablet_for_bot"
VALIDATED = "validated"

TAPE = "tape"
RECORD = "record"
OVERRIDE = "override"

#: An imported bot kept its live id; a generated bot is a new bot with a new
#: id.
MATCH_BY_BOT_ID = "bot id and time window"
MATCH_BY_PAIR = "exchange, symbol and time window"

#: Which side of the rerun moves each light: the tablet, or the recorded row.
LABEL_DRIVER: dict[tuple[str, str], str] = {
    ("S", "TGT"): RECORD,
    ("S", "INT"): RECORD,
    ("S", "BB"): TAPE,
    ("S", "FIRE"): RECORD,
    ("S", "TA"): RECORD,
    ("S", "LS"): OVERRIDE,
    ("S", "TRND"): RECORD,
    ("S", "HTF"): RECORD,
    ("S", "CB"): RECORD,
    ("S", "OTD"): RECORD,
    ("F", "BB"): TAPE,
    ("F", "MID"): TAPE,
    ("F", "TA"): RECORD,
    ("F", "LS"): OVERRIDE,
    ("F", "TRNQ"): RECORD,
    ("F", "CEIL"): RECORD,
    ("F", "HTF"): RECORD,
    ("F", "CB"): RECORD,
    ("F", "OTD"): RECORD,
}

#: The ``GateContext`` fields ``rerun_context`` computes from the tablet.
TAPE_FIELDS = (
    "ticker_last",
    "bb_pos",
    "bb_above_upper_dt",
    "bb_below_lower_dt",
    "scrum_ok",
    "fold_ok_midline",
    "ripe_scrum",
    "deep_fold",
)


@dataclass(frozen=True)
class SnappedTrade:
    """One YTD trade placed on the tablet candle whose period holds it."""

    trade_id: str
    symbol: str
    exchange_id: str
    side: str
    trade_ts_ms: int
    candle_ts_ms: int = 0
    candle_index: int = -1
    outcome: str = SNAPPED

    @property
    def is_snapped(self) -> bool:
        """True while ``outcome`` reads ``SNAPPED``."""
        return self.outcome == SNAPPED


@dataclass(frozen=True)
class Coverage:
    """How many trades reached a candle, and the period that reached none."""

    total: int
    snapped: int
    unsnapped: int
    by_reason: dict[str, int] = field(default_factory=dict)
    tablet_last_ts_ms: int = 0
    uncovered_since_ms: int = 0
    uncovered_until_ms: int = 0

    @property
    def has_uncovered_span(self) -> bool:
        """True while a trade falls after the newest candle on disk."""
        return self.uncovered_until_ms > 0 and self.uncovered_since_ms > 0


@dataclass(frozen=True)
class LabelComparison:
    """One gate light, as the log recorded it and as the rerun latched it."""

    bank: str
    label: str
    recorded: str
    rerun: str
    driven_by: str

    @property
    def agrees(self) -> bool:
        """True while the recorded state and the rerun state read the same."""
        return self.recorded == self.rerun


@dataclass(frozen=True)
class RowComparison:
    """One snapped trade's rerun, label by label, against its recorded row."""

    trade_id: str
    bot_id: str
    symbol: str
    trade_ts_ms: int
    candle_ts_ms: int
    gate_ts_ms: int
    labels: tuple[LabelComparison, ...]
    recorded_scrum_armed: bool
    recorded_fold_armed: bool
    rerun_scrum_armed: bool
    rerun_fold_armed: bool
    phantom_locked_known: bool
    unknown_recorded_blockers: tuple[str, ...] = ()
    unknown_rerun_blockers: tuple[str, ...] = ()

    @property
    def agreed(self) -> int:
        """How many of the nineteen lights read the same on both sides."""
        return sum(1 for one in self.labels if one.agrees)

    @property
    def disagreed(self) -> tuple[LabelComparison, ...]:
        """Every light whose recorded state and rerun state differ."""
        return tuple(one for one in self.labels if not one.agrees)

    @property
    def latches_identically(self) -> bool:
        """True while every light and both armed flags read the same."""
        return (
            not self.disagreed
            and self.recorded_scrum_armed == self.rerun_scrum_armed
            and self.recorded_fold_armed == self.rerun_fold_armed
        )


def iso_stamp(ts_ms: Any) -> str:
    """``ts_ms`` as a UTC ``YYYY-MM-DDTHH:MM:SSZ`` stamp, empty at or below
    zero."""
    try:
        stamp = int(ts_ms)
    except (TypeError, ValueError):
        return ""
    if stamp <= 0:
        return ""
    moment = datetime.fromtimestamp(stamp / 1000.0, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def candle_interval_ms(candle_ts: Sequence[int]) -> int:
    """The most common positive gap between consecutive ``candle_ts`` values."""
    gaps: Counter = Counter()
    for index in range(1, len(candle_ts)):
        step = int(candle_ts[index]) - int(candle_ts[index - 1])
        if step > 0:
            gaps[step] += 1
    if not gaps:
        return FALLBACK_INTERVAL_MS
    return int(gaps.most_common(1)[0][0])


def snap_index(
    candle_ts: Sequence[int], trade_ts_ms: int, interval_ms: int
) -> tuple[int, str]:
    """The index of the candle whose period holds ``trade_ts_ms``.

    An unplaceable trade answers ``-1`` with ``NO_TABLET``,
    ``BEFORE_FIRST_CANDLE``, ``AFTER_LAST_CANDLE`` or ``INSIDE_GAP``.
    """
    if not candle_ts:
        return -1, NO_TABLET
    if trade_ts_ms < int(candle_ts[0]):
        return -1, BEFORE_FIRST_CANDLE
    slot = bisect.bisect_right(candle_ts, trade_ts_ms) - 1
    if slot < 0:
        return -1, BEFORE_FIRST_CANDLE
    if trade_ts_ms < int(candle_ts[slot]) + interval_ms:
        return slot, SNAPPED
    if slot == len(candle_ts) - 1:
        return -1, AFTER_LAST_CANDLE
    return -1, INSIDE_GAP


def snap_trades(
    trades: Sequence[Any], candles: Sequence[Sequence[float]]
) -> list[SnappedTrade]:
    """Every trade in ``trades`` placed on ``candles``, snapped or refused."""
    candle_ts = [int(row[0]) for row in candles]
    interval_ms = candle_interval_ms(candle_ts)
    out: list[SnappedTrade] = []
    for trade in trades:
        index, outcome = snap_index(candle_ts, int(trade.ts_ms), interval_ms)
        out.append(
            SnappedTrade(
                trade_id=str(trade.id),
                symbol=str(getattr(trade, "symbol", "")),
                exchange_id=str(getattr(trade, "exchange_id", "")),
                side=str(trade.side),
                trade_ts_ms=int(trade.ts_ms),
                candle_ts_ms=candle_ts[index] if index >= 0 else 0,
                candle_index=index,
                outcome=outcome,
            )
        )
    return out


def coverage(
    snapped: Sequence[SnappedTrade], candles: Sequence[Sequence[float]]
) -> Coverage:
    """The counts, and the exact period the trades in ``snapped`` could not
    reach."""
    reasons = Counter(one.outcome for one in snapped if not one.is_snapped)
    placed = sum(1 for one in snapped if one.is_snapped)
    last_ts = int(candles[-1][0]) if candles else 0
    beyond = [one.trade_ts_ms for one in snapped if one.outcome == AFTER_LAST_CANDLE]
    return Coverage(
        total=len(snapped),
        snapped=placed,
        unsnapped=len(snapped) - placed,
        by_reason={name: int(count) for name, count in sorted(reasons.items())},
        tablet_last_ts_ms=last_ts,
        uncovered_since_ms=min(beyond) if beyond else 0,
        uncovered_until_ms=max(beyond) if beyond else 0,
    )


def coverage_lines(cover: Coverage) -> list[str]:
    """What Validation says about the trades it could and could not verify."""
    read = [
        f"{cover.snapped} of {cover.total} YTD entries snapped to a candle; "
        f"{cover.unsnapped} could not be."
    ]
    for name in UNSNAPPED_REASONS:
        count = cover.by_reason.get(name, 0)
        if count:
            read.append(f"{name}: {count}")
    if cover.has_uncovered_span:
        read.append(
            f"uncovered span {iso_stamp(cover.uncovered_since_ms)} to "
            f"{iso_stamp(cover.uncovered_until_ms)}; the newest candle is "
            f"{iso_stamp(cover.tablet_last_ts_ms)}"
        )
    return read


def phantom_locked(bot: SimBot, fixture: dict) -> tuple[bool, bool]:
    """The phantom lock the recorded ``scrum_ok`` implies, and whether it is
    known.

    ``scrum_ok`` is ``(bb_pos > 0.50) and not locked`` under
    ``bb_midline_gate``; a recorded False at or below ``BB_MIDLINE`` names no
    lock state.
    """
    recorded_ok = bool(fixture.get("scrum_ok"))
    recorded_bb_pos = float(fixture.get("bb_pos") or 0.0)
    if not bot.bb_midline_gate:
        return (not recorded_ok), True
    if recorded_ok:
        return False, True
    if recorded_bb_pos > BB_MIDLINE:
        return True, True
    return True, False


def bb_reading(candles: Sequence[Any], bot: SimBot):
    """``detect_bb_proximity`` over ``candles``, called as ``ScrummingBot.tick``
    calls it."""
    from ..trading.indicators.bb_proximity import detect_bb_proximity

    return detect_bb_proximity(
        list(candles),
        tolerance_pct=bot.bb_tolerance_pct,
        consolidation_threshold=BB_CONSOLIDATION_THRESHOLD,
        min_pattern_candles=bot.bb_landing_strip_candles,
    )


def _delta_pct(delta: float, target_usd: Optional[float]) -> float:
    """``target_delta_pct`` of ``delta`` over ``target_usd``, zero when no
    target is known."""
    if not target_usd:
        return 0.0
    return target_delta_pct(delta, float(target_usd))


def rerun_context(
    bot: SimBot, row: Any, candles: Sequence[Any]
) -> tuple[GateContext, float, bool]:
    """A ``GateContext`` with the ``TAPE_FIELDS`` recomputed and the rest
    recorded.

    Answers the context, the ``bb_pos`` read off ``candles`` and whether
    ``phantom_locked`` was recoverable.
    """
    scrum = dict(row.scrum_fixture)
    fold = dict(row.fold_fixture)
    reading = bb_reading(candles, bot)
    bb_pos = float(reading.bb_position)
    ticker_last = float(candles[-1].close)

    bb_upper_dt = float(scrum.get("bb_upper_dt") or 0.0)
    bb_lower_dt = float(scrum.get("bb_lower_dt") or 0.0)
    delta = float(scrum.get("delta") or 0.0)
    below_interval = bool(scrum.get("below_interval"))

    locked, locked_known = phantom_locked(bot, scrum)
    if bot.bb_midline_gate:
        scrum_ok = (bb_pos > BB_MIDLINE) and not locked
        fold_ok_midline = bb_pos < BB_MIDLINE
    else:
        scrum_ok = not locked
        fold_ok_midline = True
    if not locked_known:
        scrum_ok = bool(scrum.get("scrum_ok"))

    bb_above_upper_dt = bb_pos >= bb_upper_dt
    bb_below_lower_dt = bb_pos <= bb_lower_dt
    ripe_scrum = delta > 0 and not below_interval and bb_above_upper_dt
    deep_fold = delta < 0 and not below_interval and bb_below_lower_dt

    context = GateContext(
        symbol=row.symbol,
        ticker_last=ticker_last,
        bb_pos=bb_pos,
        bb_upper_dt=bb_upper_dt,
        bb_lower_dt=bb_lower_dt,
        delta=delta,
        delta_pct=_delta_pct(delta, bot.target_usd),
        below_interval=below_interval,
        is_bullish=bool(scrum.get("is_bullish")),
        is_bearish=bool(fold.get("is_bearish")),
        trend_hold=bool(scrum.get("trend_hold")),
        trend_strength=float(scrum.get("trend_strength") or 0.0),
        eff_direction_name=str(scrum.get("eff_direction") or ""),
        eff_is_bullish=bool(scrum.get("eff_is_bullish")),
        eff_is_bearish=bool(fold.get("eff_is_bearish")),
        eff_trend_hold=bool(scrum.get("eff_trend_hold")),
        eff_htf_blocks_scrum=bool(scrum.get("eff_htf_blocks")),
        eff_htf_blocks_fold=bool(fold.get("eff_htf_blocks_fold")),
        flag_require_ta_bullish=bool(scrum.get("flag_require_ta_bullish")),
        flag_hold_in_uptrend=bool(scrum.get("flag_hold_in_uptrend")),
        flag_defer_to_htf=bool(scrum.get("flag_defer_to_htf")),
        flag_fold_require_ta_bearish=bool(fold.get("flag_fold_require_ta_bearish")),
        flag_fold_defer_to_htf=bool(fold.get("flag_fold_defer_to_htf")),
        bb_above_upper_dt=bb_above_upper_dt,
        bb_below_lower_dt=bb_below_lower_dt,
        scrum_ok=scrum_ok,
        fold_ok_midline=fold_ok_midline,
        target_fires=bool(scrum.get("target_fires")),
        cb_blocks_scrum=bool(scrum.get("cb_blocks_scrum")),
        cb_blocks_fold=bool(fold.get("cb_blocks_fold")),
        hyst_ok_scrum_side=bool(scrum.get("hyst_ok_scrum_side")),
        hyst_ok_fold_side=bool(fold.get("hyst_ok_fold_side")),
        hyst_armed_scrum_side=bool(scrum.get("hyst_armed_scrum_side")),
        hyst_armed_fold_side=bool(fold.get("hyst_armed_fold_side")),
        hyst_ref_scrum_side=float(scrum.get("hyst_ref_scrum_side") or 0.0),
        hyst_ref_fold_side=float(fold.get("hyst_ref_fold_side") or 0.0),
        mem253_at_ceiling=bool(fold.get("mem253_at_ceiling")),
        mem253_smart_ceiling_usd=float(fold.get("mem253_smart_ceiling_usd") or 0.0),
        mem253_current_pos=float(fold.get("mem253_current_pos") or 0.0),
        has_fold_tranches=bool(fold.get("has_fold_tranches")),
        n_fold_tranches=int(fold.get("n_fold_tranches") or 0),
        htf_bias_name=scrum.get("htf_bias_dir"),
        htf_blocks_scrum=bool(scrum.get("htf_blocks_scrum")),
        htf_blocks_fold=bool(fold.get("htf_blocks_fold")),
        scrumming_interval_pct=bot.scrumming_interval_pct,
        trading_fee_pct=bot.trading_fee_pct,
        ripe_scrum=ripe_scrum,
        deep_fold=deep_fold,
    )
    return context, bb_pos, locked_known


def latch(context: GateContext) -> dict:
    """The shipped scrum and fold chains evaluated on ``context``."""
    scrum = build_scrumming_scrum_chain().evaluate(context)
    fold = build_scrumming_fold_chain().evaluate(context)
    return {
        "scrum_armed": bool(scrum.should_fire),
        "fold_armed": bool(fold.should_fire),
        "scrum_blockers": [message for _name, message in scrum.blocked],
        "fold_blockers": [message for _name, message in fold.blocked],
    }


def light_states(
    scrum_armed: bool,
    fold_armed: bool,
    scrum_blockers: Sequence[str],
    fold_blockers: Sequence[str],
) -> list[dict]:
    """The nineteen ``gate_vocabulary`` lights for one armed-and-blocked
    reading."""
    return gate_light_row(
        scrum_armed=scrum_armed,
        fold_armed=fold_armed,
        scrum_blockers=list(scrum_blockers),
        fold_blockers=list(fold_blockers),
    )


def compare_row(
    bot: SimBot, row: Any, snap: SnappedTrade, candles: Sequence[Any]
) -> RowComparison:
    """One snapped trade's rerun beside its recorded row, light by light."""
    context, _bb_pos, locked_known = rerun_context(bot, row, candles)
    rerun = latch(context)
    recorded_lights = light_states(
        row.scrum_armed, row.fold_armed, row.scrum_blockers, row.fold_blockers
    )
    rerun_lights = light_states(
        rerun["scrum_armed"],
        rerun["fold_armed"],
        rerun["scrum_blockers"],
        rerun["fold_blockers"],
    )
    labels = tuple(
        LabelComparison(
            bank=str(left["bank"]),
            label=str(left["label"]),
            recorded=str(left["state"]),
            rerun=str(right["state"]),
            driven_by=LABEL_DRIVER.get((str(left["bank"]), str(left["label"])), RECORD),
        )
        for left, right in zip(recorded_lights, rerun_lights, strict=True)
    )
    return RowComparison(
        trade_id=snap.trade_id,
        bot_id=row.bot_id,
        symbol=row.symbol,
        trade_ts_ms=snap.trade_ts_ms,
        candle_ts_ms=snap.candle_ts_ms,
        gate_ts_ms=row.ts_ms,
        labels=labels,
        recorded_scrum_armed=bool(row.scrum_armed),
        recorded_fold_armed=bool(row.fold_armed),
        rerun_scrum_armed=bool(rerun["scrum_armed"]),
        rerun_fold_armed=bool(rerun["fold_armed"]),
        phantom_locked_known=bool(locked_known),
        unknown_recorded_blockers=tuple(
            unknown_blockers(list(row.scrum_blockers) + list(row.fold_blockers))
        ),
        unknown_rerun_blockers=tuple(
            unknown_blockers(rerun["scrum_blockers"] + rerun["fold_blockers"])
        ),
    )


def tape_lag(
    bot: SimBot,
    row: Any,
    candles: Sequence[Any],
    index: int,
    spread: int = LAG_SEARCH_CANDLES,
) -> tuple[Optional[int], float]:
    """The window offset from ``index`` that reproduces ``row``'s recorded
    ``bb_pos``.

    Answers the offset in candles and the gap it left; None means no window
    within ``spread`` reproduced the reading.
    """
    recorded = row.scrum_fixture.get("bb_pos")
    if recorded is None:
        return None, 1.0
    target = float(recorded)
    best_offset: Optional[int] = None
    best_gap = 1.0
    for offset in range(-spread, spread + 1):
        window = rerun_window(candles, index + offset)
        if len(window) < MIN_RERUN_CANDLES:
            continue
        gap = abs(float(bb_reading(window, bot).bb_position) - target)
        if gap < best_gap:
            best_gap = gap
            best_offset = offset
    if best_gap > LAG_EXACT_GAP:
        return None, best_gap
    return best_offset, best_gap


def lag_lines(offsets: Sequence[int], interval_ms: int, checked: int) -> list[str]:
    """What Validation says about the window the recorded readings came from."""
    if not offsets:
        return [f"No recorded reading was reproduced from the tape in {checked} rows."]
    counted = Counter(offsets)
    common, hits = counted.most_common(1)[0]
    minutes = abs(common) * interval_ms / 60_000.0
    read = [
        f"{len(offsets)} of {checked} recorded readings were reproduced exactly "
        "from the tablet.",
    ]
    if common == 0:
        read.append("The recorded window and the tablet window are the same.")
    else:
        read.append(
            f"{hits} of them came from a window {abs(common)} candles "
            f"({minutes:.0f} minutes) behind the trade's own candle."
        )
    return read


def is_rerunnable(row: Any) -> bool:
    """True while ``row`` carries both fixtures ``rerun_context`` reads.

    ``gate.log`` also holds pre-tick rows whose fixtures are empty and whose
    only blocker maps to no gate label.
    """
    return bool(row.scrum_fixture) and bool(row.fold_fixture)


def nearest_gate_row(rows: Sequence[Any], ts_ms: int, window_ms: int):
    """The row in ``rows`` closest to ``ts_ms`` within ``window_ms``, or
    None."""
    best = None
    best_gap = window_ms + 1
    for row in rows:
        gap = abs(int(row.ts_ms) - int(ts_ms))
        if gap <= window_ms and gap < best_gap:
            best = row
            best_gap = gap
    return best


def rerun_window(candles: Sequence[Any], index: int) -> list:
    """The ``RERUN_WINDOW_CANDLES`` rows of ``candles`` ending at ``index``."""
    if index < 0:
        return []
    start = max(0, index + 1 - RERUN_WINDOW_CANDLES)
    return list(candles[start : index + 1])


def summarise(rows: Sequence[RowComparison]) -> dict:
    """The agreement counts over ``rows``: lights, rows and armed flags."""
    lights = sum(len(one.labels) for one in rows)
    agreed = sum(one.agreed for one in rows)
    identical = sum(1 for one in rows if one.latches_identically)
    return {
        "rows_compared": len(rows),
        "rows_latching_identically": identical,
        "rows_disagreeing": len(rows) - identical,
        "lights_compared": lights,
        "lights_agreeing": agreed,
        "lights_disagreeing": lights - agreed,
    }


def verdict_lines(summary: dict) -> list[str]:
    """What Validation says about gate latching, in lights and rows."""
    if not summary["rows_compared"]:
        return ["No YTD entry reached both a candle and a recorded gate row."]
    return [
        f"{summary['rows_latching_identically']} of {summary['rows_compared']} "
        "reruns latched every gate identically.",
        f"{summary['lights_agreeing']} of {summary['lights_compared']} gate "
        "lights agreed.",
    ]


@dataclass(frozen=True)
class ValidationRun:
    """One Validation pass: its fleet, its coverage and its gate comparison."""

    exchange_id: str
    bots: tuple[SimBot, ...]
    coverage: Coverage
    comparisons: tuple[RowComparison, ...]
    bot_outcomes: dict[str, int] = field(default_factory=dict)
    gate_rows_read: int = 0
    rows_matched: int = 0
    rows_without_fixture: int = 0
    lag_offsets: tuple[int, ...] = ()
    lag_checked: int = 0
    lag_interval_ms: int = FALLBACK_INTERVAL_MS
    by_bot: dict[str, dict] = field(default_factory=dict)
    #: The ``ParityReport`` ``run`` wrote for this pass; None until it has.
    report: Any = None

    @property
    def summary(self) -> dict:
        """The agreement counts over ``comparisons``."""
        return summarise(self.comparisons)

    @property
    def match_key(self) -> str:
        """What a gate row was matched on: the bot id, or the pair."""
        made = [one for one in self.bots if one.origin != LIVE_ORIGIN]
        return MATCH_BY_PAIR if made else MATCH_BY_BOT_ID

    @property
    def lines(self) -> list[str]:
        """The fleet, the coverage, the latching verdict, then the tape lag."""
        return (
            [
                f"{len(self.bots)} bots, matched to a recorded gate row on "
                f"{self.match_key}."
            ]
            + coverage_lines(self.coverage)
            + verdict_lines(self.summary)
            + lag_lines(self.lag_offsets, self.lag_interval_ms, self.lag_checked)
        )


def tablet_for(entries: Sequence[Any], asset: str, exchange_id: str):
    """The tablet entry for ``asset`` on ``exchange_id``, or None."""
    for entry in entries:
        if entry.asset == asset and entry.exchange_id == exchange_id:
            return entry
    return None


def bot_counts(bot: SimBot, outcome: str, rows: Sequence[SnappedTrade]) -> dict:
    """One ``ValidationRun.by_bot`` entry: ``outcome``, the snapped and
    unsnapped counts over ``rows``, and zero compared and latching."""
    return {
        "symbol": bot.symbol,
        "outcome": outcome,
        "snapped": sum(1 for one in rows if one.is_snapped),
        "unsnapped": sum(1 for one in rows if not one.is_snapped),
        "compared": 0,
        "latching": 0,
    }


def rerun_trade(bot: SimBot, fill: Any) -> "SimTrade":
    """The ``SimTrade`` one rerun YTD fill reads as: ``SCRUM`` for ``SIDE_SELL``
    and ``FOLD`` otherwise, ``amount`` as the units, ``cost`` as the USD."""
    from .back_test import FOLD, SCRUM, SimTrade

    return SimTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=SCRUM if str(fill.side).upper() == SIDE_SELL else FOLD,
        ts_ms=int(fill.ts_ms),
        price=float(fill.price),
        units=float(fill.amount),
        usd=float(fill.cost),
        fee_usd=float(fill.fee),
    )


def run(
    bots: Sequence[SimBot],
    tablets: Any,
    ytd: Any,
    gates: Any,
    exchange_id: str = "",
    limit: int = 0,
    lag_sample: int = LAG_SAMPLE_ROWS,
    on_trade: Optional[Callable[["SimTrade"], None]] = None,
) -> ValidationRun:
    """Snap every bot's YTD trades, rerun each against its recorded gate row,
    and write the pass through ``write_report`` onto ``ValidationRun.report``.

    ``limit`` caps how many matched trades are rerun, ``lag_sample`` how many
    have ``tape_lag`` measured, ``on_trade`` is handed ``rerun_trade`` of each
    fill as it is rerun; a ``_validate`` that raises reaches ``write_partial``
    with the exception and re-raises.
    """
    from .parity_report import VALIDATION, write_partial, write_report

    try:
        outcome = _validate(
            bots, tablets, ytd, gates, exchange_id, limit, lag_sample, on_trade
        )
    except Exception as exc:
        write_partial(
            VALIDATION, exc, bots=bots, exchange_id=exchange_id, tablets=tablets
        )
        raise
    return replace(outcome, report=write_report(VALIDATION, outcome, tablets))


def _validate(
    bots: Sequence[SimBot],
    tablets: Any,
    ytd: Any,
    gates: Any,
    exchange_id: str,
    limit: int,
    lag_sample: int,
    on_trade: Optional[Callable[["SimTrade"], None]] = None,
) -> ValidationRun:
    """The pass ``run`` wraps: ``snap_trades``, ``compare_row`` and ``tape_lag``
    over ``bots``, with no report written; ``on_trade`` is handed
    ``rerun_trade`` of each fill at its ``compare_row``."""
    from ..trading.indicators.types import candles_from_raw

    tablet_entries = tablets.entries()
    ytd_entries = {(one.exchange_id, one.symbol): one for one in ytd.entries()}
    outcomes: Counter = Counter()
    placed: list[tuple[SimBot, SnappedTrade]] = []
    fills: dict[tuple[str, str], Any] = {}
    raw_by_symbol: dict[str, list] = {}
    by_bot: dict[str, dict] = {}
    newest_candle_ms = 0

    for bot in bots:
        entry = ytd_entries.get((bot.exchange_id, bot.symbol))
        tablet = tablet_for(tablet_entries, bot.asset, bot.exchange_id)
        if entry is None:
            outcomes[NO_YTD_FILE] += 1
            by_bot[bot.bot_id] = bot_counts(bot, NO_YTD_FILE, [])
            continue
        if tablet is None:
            outcomes[NO_BOT_TABLET] += 1
            by_bot[bot.bot_id] = bot_counts(bot, NO_BOT_TABLET, [])
            continue
        raw = tablets.candles(tablet)
        raw_by_symbol[bot.symbol] = raw
        if raw:
            newest_candle_ms = max(newest_candle_ms, int(raw[-1][0]))
        recorded = list(ytd.trades(entry))
        fills.update({(bot.bot_id, str(one.id)): one for one in recorded})
        rows = snap_trades(recorded, raw)
        placed.extend((bot, one) for one in rows)
        by_bot[bot.bot_id] = bot_counts(bot, VALIDATED, rows)
        outcomes[VALIDATED] += 1

    flat = [one for _bot, one in placed]
    reasons = Counter(one.outcome for one in flat if not one.is_snapped)
    beyond = [one.trade_ts_ms for one in flat if one.outcome == AFTER_LAST_CANDLE]
    cover = Coverage(
        total=len(flat),
        snapped=sum(1 for one in flat if one.is_snapped),
        unsnapped=sum(1 for one in flat if not one.is_snapped),
        by_reason={name: int(count) for name, count in sorted(reasons.items())},
        tablet_last_ts_ms=newest_candle_ms,
        uncovered_since_ms=min(beyond) if beyond else 0,
        uncovered_until_ms=max(beyond) if beyond else 0,
    )

    # A generated bot is a new bot with a new id and wrote no gate row, so it
    # is matched on exchange and symbol.
    live_ids = {bot.bot_id for bot in bots if bot.origin == LIVE_ORIGIN}
    made_symbols = {bot.symbol for bot in bots if bot.origin != LIVE_ORIGIN}
    rows_by_bot: dict[str, list] = {}
    rows_by_pair: dict[tuple[str, str], list] = {}
    gate_rows_read = 0
    for row in gates.rows(bot_ids=live_ids, symbols=made_symbols):
        gate_rows_read += 1
        rows_by_bot.setdefault(row.bot_id, []).append(row)
        rows_by_pair.setdefault((row.exchange_id, row.symbol), []).append(row)

    comparisons: list[RowComparison] = []
    without_fixture = 0
    matched = 0
    lag_offsets: list[int] = []
    lag_checked = 0
    lag_interval_ms = FALLBACK_INTERVAL_MS
    parsed_cache: dict[str, list] = {}
    for bot, snap in placed:
        if not snap.is_snapped:
            continue
        near = (
            rows_by_bot.get(bot.bot_id)
            if bot.origin == LIVE_ORIGIN
            else rows_by_pair.get((bot.exchange_id, bot.symbol))
        )
        row = nearest_gate_row(near or [], snap.trade_ts_ms, GATE_MATCH_WINDOW_MS)
        if row is None:
            continue
        matched += 1
        if not is_rerunnable(row):
            without_fixture += 1
            continue
        if limit and len(comparisons) >= limit:
            continue
        if bot.symbol not in parsed_cache:
            parsed_cache[bot.symbol] = candles_from_raw(raw_by_symbol[bot.symbol])
        window = rerun_window(parsed_cache[bot.symbol], snap.candle_index)
        if len(window) < MIN_RERUN_CANDLES:
            continue
        seen = compare_row(bot, row, snap, window)
        comparisons.append(seen)
        if on_trade is not None:
            on_trade(rerun_trade(bot, fills[(bot.bot_id, snap.trade_id)]))
        counts = by_bot.get(bot.bot_id)
        if counts is not None:
            counts["compared"] += 1
            counts["latching"] += 1 if seen.latches_identically else 0
        if lag_sample and lag_checked < lag_sample:
            lag_checked += 1
            lag_interval_ms = candle_interval_ms(
                [int(one[0]) for one in raw_by_symbol[bot.symbol]]
            )
            offset, _gap = tape_lag(
                bot, row, parsed_cache[bot.symbol], snap.candle_index
            )
            if offset is not None:
                lag_offsets.append(offset)

    return ValidationRun(
        exchange_id=exchange_id,
        bots=tuple(bots),
        coverage=cover,
        comparisons=tuple(comparisons),
        bot_outcomes={name: int(count) for name, count in sorted(outcomes.items())},
        gate_rows_read=gate_rows_read,
        rows_matched=matched,
        rows_without_fixture=without_fixture,
        lag_offsets=tuple(lag_offsets),
        lag_checked=lag_checked,
        lag_interval_ms=lag_interval_ms,
        by_bot=by_bot,
    )


__all__ = [
    "AFTER_LAST_CANDLE",
    "BB_CONSOLIDATION_THRESHOLD",
    "BB_MIDLINE",
    "BEFORE_FIRST_CANDLE",
    "FALLBACK_INTERVAL_MS",
    "GATE_MATCH_WINDOW_MS",
    "INSIDE_GAP",
    "LABEL_DRIVER",
    "LAG_EXACT_GAP",
    "LAG_SAMPLE_ROWS",
    "LAG_SEARCH_CANDLES",
    "MATCH_BY_BOT_ID",
    "MATCH_BY_PAIR",
    "MIN_RERUN_CANDLES",
    "NO_BOT_TABLET",
    "NO_TABLET",
    "NO_YTD_FILE",
    "OVERRIDE",
    "RECORD",
    "RERUN_WINDOW_CANDLES",
    "SHORT_WINDOW",
    "SNAPPED",
    "TAPE",
    "TAPE_FIELDS",
    "UNSNAPPED_REASONS",
    "VALIDATED",
    "Coverage",
    "LabelComparison",
    "RowComparison",
    "SnappedTrade",
    "ValidationRun",
    "bb_reading",
    "bot_counts",
    "candle_interval_ms",
    "compare_row",
    "coverage",
    "coverage_lines",
    "is_rerunnable",
    "iso_stamp",
    "lag_lines",
    "latch",
    "light_states",
    "nearest_gate_row",
    "phantom_locked",
    "rerun_context",
    "rerun_trade",
    "rerun_window",
    "run",
    "snap_index",
    "snap_trades",
    "summarise",
    "tablet_for",
    "tape_lag",
    "verdict_lines",
]
