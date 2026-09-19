"""One trade parity report per Simulator run: a Markdown file and a JSON
sidecar of the same ``figures`` under ``reports_dir``.

``write_report`` builds the figures of a finished ``ValidationRun``,
``BackTestRun`` or ``BatteryRun`` through ``validation_figures``,
``back_test_figures`` or ``battery_figures`` and writes both files;
``write_partial`` writes what a run that raised had, with the exception named.
``report_line`` is the Activity Log line the two Sim hosts write when
``run`` hands back a ``ParityReport``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from .. import __version__
from ..core.log_paths import get_reports_dir
from .back_test import (
    BACK_TESTED,
    BackTestRun,
    BotResult,
    FOLD,
    FUNDED_BY_PROCEEDS,
    FUNDED_BY_TARGETS,
    SCRUM,
    UNCITED_RULE,
    cited_rule_for,
    run_budget_usd,
    uncited_rule_line,
)
from .fleet_source import SimBot
from .portfolio_battery import (
    RAN,
    READINGS,
    BatteryRun,
    SymbolRun,
    TimeframeResult,
)
from .portfolios import PORTFOLIOS
from .sim_bus import sim_log_paths
from .tablet_source import TabletSource, tablet_key
from .validation import (
    CAUSES,
    CHAIN_CAUSE,
    FIXTURE_CAUSE,
    MIN_RERUN_CANDLES,
    NO_BOT_TABLET,
    NO_YTD_FILE,
    TAPE_CAUSE,
    VALIDATED,
    RowComparison,
    ValidationRun,
    bot_outcome_line,
    iso_stamp,
    summarise,
)

logger = logging.getLogger("acervator.simulator.parity_report")

VALIDATION = "validation"
BACK_TEST = "back_test"
PORTFOLIO_BATTERY = "portfolio_battery"
MODES = (VALIDATION, BACK_TEST, PORTFOLIO_BATTERY)
MODE_TITLE = {
    VALIDATION: "Validation",
    BACK_TEST: "Back Test",
    PORTFOLIO_BATTERY: "Portfolio Battery",
}

#: The directory under ``get_reports_dir`` every report lands in.
REPORTS_SUBDIR = "simulator"
MARKDOWN_SUFFIX = ".md"
JSON_SUFFIX = ".json"
STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
SUBJECT_LIMIT = 40
EVERY_PORTFOLIO = "every-portfolio"
NOT_COMPUTED = "not computed"

MISSING = "missing"
EXTRA = "extra"
DIFFERS = "differs"
VARIANT_DIFFERS = "variant_differs"
COUNT_NAMES = (MISSING, EXTRA, DIFFERS, VARIANT_DIFFERS)
BY_CAUSE = "by_cause"

#: What each cause of a differing light reads, from the row's own fields.
CAUSE_DEFINITIONS = {
    TAPE_CAUSE: (
        "the tablet candle the rerun read differs from the reading the bot "
        "recorded: the recorded bb_pos, or the bank's recorded band flag, "
        "does not match the rerun's"
    ),
    FIXTURE_CAUSE: (
        "a recorded field the light reads is absent from the row's fixture, "
        "or the phantom lock could not be recovered from the recorded row"
    ),
    CHAIN_CAUSE: (
        "the same inputs on both sides and a different light: the gate chain"
    ),
}
STOPPED_NOTE = "the operator pressed Stop before every bot and row was reached"

#: What each of the four counts reads, over the record Live wrote and the
#: rerun the Simulator latched.
COUNT_DEFINITIONS = {
    MISSING: (
        "a blocker the recorded row names that maps to no gate light "
        "(unknown_recorded_blockers)"
    ),
    EXTRA: (
        "a blocker the rerun raised that maps to no gate light "
        "(unknown_rerun_blockers)"
    ),
    DIFFERS: "a light in both whose recorded and rerun states differ (disagreed)",
    VARIANT_DIFFERS: (
        "a row whose nineteen lights all agree and whose armed flags differ"
    ),
}

FUNDING_RULE = {
    FUNDED_BY_TARGETS: (
        "the spendable budget is the sum of the held Target Balances and no "
        "fold is capped for cash"
    ),
    FUNDED_BY_PROCEEDS: (
        "each bot's fold spends its own scrum proceeds and there is no run budget"
    ),
}

REPORT_LINE_FORMAT = "{mode} report written: {path}"
NOTHING_UNVERIFIED = "Nothing was left unverified by this run."
NO_LIVE_FILL_TEXT = (
    "No fill is compared against a live one: Back Test has no recorded trade "
    "to compare to."
)
#: How the Battery reads one scrummed end against its historical path, the
#: words ``portfolio_battery.reading_for`` answers.
BATTERY_READING_RULE = (
    "the historical path is buy-and-hold over the span: start = the Target "
    "Balances committed, trough = the sum of each symbol's lowest untraded "
    "value on a walked bar, end = baseline; the scrummed end is accumulation; "
    "reversed = at or above the start after the path fell below it, improved = "
    "above the end, defended = above the trough, undefended = at or below the "
    "trough, not run = no symbol walked"
)


@dataclass(frozen=True)
class ParityReport:
    """Where one run's report landed: ``markdown_path`` and ``json_path`` share
    ``name``; ``partial`` is True when ``error`` names the exception."""

    mode: str
    name: str
    markdown_path: Path
    json_path: Path
    stamp: str
    partial: bool = False
    error: str = ""
    #: True when the run was ended by Stop; ``partial`` reads True as well.
    stopped: bool = False
    #: The id every sim log row of the run carries; empty when the run was
    #: handed no bus.
    run_id: str = ""


def reports_dir() -> Path:
    """``get_reports_dir() / REPORTS_SUBDIR``, created."""
    path = get_reports_dir() / REPORTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_stamp(moment: Optional[datetime] = None) -> str:
    """``moment`` in UTC as ``STAMP_FORMAT``; now when None."""
    when = moment if moment is not None else datetime.now(timezone.utc)
    return when.astimezone(timezone.utc).strftime(STAMP_FORMAT)


def new_run_id(mode: str) -> str:
    """``<mode>-<utc_stamp()>``, taken when a run starts, before its first row."""
    return f"{safe_name(mode)}-{utc_stamp()}"


def rows_section(run_id: str, emitted: dict) -> dict:
    """The report's ``rows`` figures: ``run_id``, the ``sim_log_paths`` files,
    what the run emitted per topic, and the ``EmitObserver`` reading."""
    observer = dict(emitted.get("observer") or {})
    return {
        "run_id": run_id,
        "files": sim_log_paths(),
        "emitted": dict(emitted.get("emitted") or {}),
        "topics_declared": int(observer.get("topics_declared", 0) or 0),
        "topics_seen": int(observer.get("topics_seen", 0) or 0),
        "observed": dict(observer.get("emissions") or {}),
        "violations": list(observer.get("violations") or []),
    }


def safe_name(text: object) -> str:
    """``text`` with every character outside letters, digits, dot, dash and
    underscore replaced by a dash."""
    return (
        "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(text or ""))
        or "none"
    )


def report_name(mode: str, subject: str, span: str, stamp: str) -> str:
    """The file stem: mode, subject, span and stamp joined by ``__``."""
    return "__".join(
        (safe_name(mode), safe_name(subject)[:SUBJECT_LIMIT], safe_name(span), stamp)
    )


def day_of(ts_ms: object) -> str:
    """The ``YYYY-MM-DD`` of ``iso_stamp(ts_ms)``, empty when it is empty."""
    return iso_stamp(ts_ms)[:10]


def span_label(first_ms: int, last_ms: int) -> str:
    """``first_to_last`` in days, ``no-span`` when neither is known."""
    if not first_ms and not last_ms:
        return "no-span"
    return f"{day_of(first_ms) or 'unknown'}_{day_of(last_ms) or 'unknown'}"


def create_pair(directory: Path, stem: str) -> tuple[Path, Path]:
    """The first ``stem`` under ``directory`` whose Markdown and JSON paths both
    do not exist, the Markdown created exclusively so no report is overwritten."""
    suffix = 0
    while True:
        name = stem if suffix == 0 else f"{stem}-{suffix + 1}"
        markdown = directory / (name + MARKDOWN_SUFFIX)
        sidecar = directory / (name + JSON_SUFFIX)
        if sidecar.exists():
            suffix += 1
            continue
        try:
            with open(markdown, "x", encoding="utf-8", newline="\n"):
                pass
        except FileExistsError:
            suffix += 1
            continue
        return markdown, sidecar


def fleet_origins(bots: Sequence[SimBot]) -> list[str]:
    """Every distinct ``SimBot.origin`` in ``bots``, sorted."""
    return sorted({str(one.origin) for one in bots})


def tablet_rows(tablets: Optional[TabletSource], wanted: Optional[set] = None) -> dict:
    """One row per MANIFEST entry ``tablets`` answers, kept to the ``(asset,
    exchange_id)`` pairs in ``wanted`` when given; a source that raises answers
    ``{"unread": <error>}``."""
    if tablets is None:
        return {"unread": "no tablet source was handed to the run"}
    try:
        entries = tablets.entries()
        root = str(tablets.root())
    except Exception as exc:  # noqa: BLE001 - the tablet section names its own failure
        return {"unread": f"{type(exc).__name__}: {exc}"}
    rows = []
    for entry in entries:
        if wanted is not None and (entry.asset, entry.exchange_id) not in wanted:
            continue
        rows.append(
            {
                "key": tablet_key(entry),
                "asset": entry.asset,
                "exchange_id": entry.exchange_id,
                "timeframe": entry.timeframe,
                "year": int(entry.year),
                "candles": int(entry.candle_count),
                "first": iso_stamp(entry.first_ts_ms),
                "last": iso_stamp(entry.last_ts_ms),
                "sha256": entry.checksum_sha256,
            }
        )
    return {"root": root, "rows": rows}


def tablet_span(tablet_section: dict) -> tuple[int, int]:
    """The earliest ``first`` and latest ``last`` over the rows of
    ``tablet_section``, zeros when it holds none."""
    rows = tablet_section.get("rows")
    if not rows:
        return 0, 0
    firsts = [_ms_of(one["first"]) for one in rows]
    lasts = [_ms_of(one["last"]) for one in rows]
    return min(firsts), max(lasts)


def _ms_of(stamp: str) -> int:
    if not stamp:
        return 0
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def rule_row(asset: str, exchange_id: str) -> dict:
    """``cited_rule_for`` over the pair as the three report fields."""
    class_name, venue, rule = cited_rule_for(asset, exchange_id)
    return {
        "asset_class": class_name or "none",
        "venue": venue or "none",
        "unit_rule": rule or "none",
        "rule_cited": rule is not None,
    }


def budget_section(funding: str, bots: Sequence[SimBot]) -> dict:
    """The funding word, its rule and the budget it gives ``bots``."""
    with_target = [one for one in bots if one.target_usd is not None]
    budget = run_budget_usd(bots) if funding == FUNDED_BY_TARGETS else None
    return {
        "funding": funding,
        "rule": FUNDING_RULE.get(funding, ""),
        "budget_usd": budget,
        "bots_with_target": len(with_target),
        "bots_without_target": len(bots) - len(with_target),
    }


def header(
    mode: str,
    stamp: str,
    bots: Sequence[SimBot],
    exchange_id: str,
    first_ms: int,
    last_ms: int,
    span: str,
    funding: str,
    subject: str,
    run_id: str = "",
    emitted: Optional[dict] = None,
) -> dict:
    """The header every mode carries, with ``rows_section`` over ``run_id``
    and ``emitted``."""
    return {
        "mode": mode,
        "title": MODE_TITLE.get(mode, mode),
        "stamp": stamp,
        "build": str(__version__),
        "fleet_origin": fleet_origins(bots),
        "exchange": exchange_id or "",
        "subject": subject,
        "span": {
            "label": span,
            "first": iso_stamp(first_ms),
            "last": iso_stamp(last_ms),
        },
        "bots": len(bots),
        "budget": budget_section(funding, bots),
        "run_id": run_id,
        "rows": rows_section(run_id, emitted or {}),
    }


def comparison_counts(rows: Sequence[RowComparison]) -> dict:
    """``summarise`` over ``rows`` and the four ``COUNT_NAMES``."""
    counts = dict(summarise(rows))
    counts[MISSING] = sum(len(one.unknown_recorded_blockers) for one in rows)
    counts[EXTRA] = sum(len(one.unknown_rerun_blockers) for one in rows)
    counts[DIFFERS] = sum(len(one.disagreed) for one in rows)
    counts[VARIANT_DIFFERS] = sum(
        1 for one in rows if not one.disagreed and not one.latches_identically
    )
    counts[BY_CAUSE] = {
        name: sum(one.causes.get(name, 0) for one in rows) for name in CAUSES
    }
    return counts


def comparison_row(row: RowComparison) -> dict:
    """One ``RowComparison`` as the report carries it."""
    return {
        "trade_id": row.trade_id,
        "bot_id": row.bot_id,
        "symbol": row.symbol,
        "trade_at": iso_stamp(row.trade_ts_ms),
        "candle_at": iso_stamp(row.candle_ts_ms),
        "gate_row_at": iso_stamp(row.gate_ts_ms),
        "latches_identically": bool(row.latches_identically),
        "agreed": int(row.agreed),
        "lights": len(row.labels),
        "recorded_armed": {
            "scrum": row.recorded_scrum_armed,
            "fold": row.recorded_fold_armed,
        },
        "rerun_armed": {"scrum": row.rerun_scrum_armed, "fold": row.rerun_fold_armed},
        "phantom_locked_known": bool(row.phantom_locked_known),
        "disagreed": [
            {
                "bank": one.bank,
                "label": one.label,
                "recorded": one.recorded,
                "rerun": one.rerun,
                "driven_by": one.driven_by,
                "cause": one.cause,
            }
            for one in row.disagreed
        ],
        "causes": dict(row.causes),
        "recorded_bb_pos": row.recorded_bb_pos,
        "rerun_bb_pos": row.rerun_bb_pos,
        "missing_fixture_fields": list(row.missing_fixture_fields),
        "unknown_recorded_blockers": list(row.unknown_recorded_blockers),
        "unknown_rerun_blockers": list(row.unknown_rerun_blockers),
    }


def validation_bots(run: ValidationRun) -> list[dict]:
    """One row per held bot: the pair's rule row and its ``by_bot`` counts."""
    rows = []
    for bot in run.bots:
        counts = run.by_bot.get(bot.bot_id, {})
        row = {
            "bot_id": bot.bot_id,
            "symbol": bot.symbol,
            "exchange_id": bot.exchange_id,
            "origin": bot.origin,
            "target_usd": bot.target_usd,
            "outcome": counts.get("outcome", "not reached"),
            "snapped": int(counts.get("snapped", 0)),
            "unsnapped": int(counts.get("unsnapped", 0)),
            "compared": int(counts.get("compared", 0)),
            "latching": int(counts.get("latching", 0)),
            "gate_rows": int(counts.get("gate_rows", 0)),
        }
        row.update(rule_row(bot.asset, bot.exchange_id))
        rows.append(row)
    return rows


def validation_not_verified(run: ValidationRun, bots: Sequence[dict]) -> list[str]:
    """What the Validation run could not verify, one line each: the stop line
    first when ``run.stopped``, then each bot with no YTD file, no tablet or no
    recorded gate row, then the coverage and rerun gaps; the two lines counting
    snapped rows against matched and rerun rows are left out of a stopped run,
    whose stop line states the rows rerun."""
    out = []
    if run.stopped:
        out.append(run.stopped_line)
    for row in bots:
        if row["outcome"] in (NO_YTD_FILE, NO_BOT_TABLET) or (
            row["outcome"] == VALIDATED and not row["gate_rows"]
        ):
            out.append(
                bot_outcome_line(
                    row["bot_id"], row["symbol"], row["outcome"], row["snapped"]
                )
            )
    cover = run.coverage
    for reason, count in sorted(cover.by_reason.items()):
        out.append(f"{count} YTD entries not snapped: {reason}.")
    if cover.has_uncovered_span:
        out.append(
            f"uncovered span {iso_stamp(cover.uncovered_since_ms)} to "
            f"{iso_stamp(cover.uncovered_until_ms)}; the newest candle is "
            f"{iso_stamp(cover.tablet_last_ts_ms)}."
        )
    unmatched = cover.snapped - run.rows_matched
    if unmatched > 0 and not run.stopped:
        out.append(f"{unmatched} snapped trades matched no recorded gate row.")
    if run.rows_without_fixture:
        out.append(
            f"{run.rows_without_fixture} matched gate rows carry no fixture "
            "and were not rerun."
        )
    short = run.rows_matched - run.rows_without_fixture - len(run.comparisons)
    if short > 0 and not run.stopped:
        out.append(
            f"{short} matched rows were not rerun: over the rerun limit or a window "
            f"under {MIN_RERUN_CANDLES} candles."
        )
    unknown_lock = sum(1 for one in run.comparisons if not one.phantom_locked_known)
    if unknown_lock:
        out.append(
            f"{unknown_lock} reruns could not recover the phantom lock from "
            "the recorded row."
        )
    blockers = sum(
        len(one.unknown_recorded_blockers) + len(one.unknown_rerun_blockers)
        for one in run.comparisons
    )
    if blockers:
        out.append(
            f"{blockers} blocker phrases map to no gate light and were not compared."
        )
    not_reproduced = run.lag_checked - len(run.lag_offsets)
    if not_reproduced > 0:
        out.append(
            f"{not_reproduced} of {run.lag_checked} recorded readings were not "
            "reproduced "
            "from the tablet."
        )
    return out or [NOTHING_UNVERIFIED]


def validation_figures(
    run: ValidationRun, tablets: Optional[TabletSource], stamp: str
) -> dict:
    """The figures of one ``ValidationRun``."""
    wanted = {(one.asset, one.exchange_id) for one in run.bots}
    tablet_section = tablet_rows(tablets, wanted)
    first_ms, last_ms = tablet_span(tablet_section)
    bots = validation_bots(run)
    subject = (
        f"{run.exchange_id or 'fleet'}-{'-'.join(fleet_origins(run.bots)) or 'none'}"
    )
    head = header(
        VALIDATION,
        stamp,
        run.bots,
        run.exchange_id,
        first_ms,
        last_ms,
        span_label(first_ms, last_ms),
        FUNDED_BY_TARGETS,
        subject,
        run.run_id,
        run.emitted,
    )
    head["budget"][
        "note"
    ] = "Validation reruns gates and sizes no trade; no buy was refused for cash."
    head["match_key"] = run.match_key
    head["gate_rows_read"] = int(run.gate_rows_read)
    head["stopped"] = bool(run.stopped)
    head["bots_reached"] = len(run.bots) - len(run.unreached)
    return {
        "mode": VALIDATION,
        "partial": bool(run.stopped),
        "stopped": bool(run.stopped),
        "error": None,
        "header": head,
        "tablets": tablet_section,
        "bots": bots,
        "comparison": {
            "definitions": dict(COUNT_DEFINITIONS),
            "cause_definitions": dict(CAUSE_DEFINITIONS),
            "counts": comparison_counts(run.comparisons),
            "rows": [comparison_row(one) for one in run.comparisons],
        },
        "not_verified": validation_not_verified(run, bots),
        "lines": list(run.lines),
    }


def back_test_bot(result: BotResult, bot: Optional[SimBot]) -> dict:
    """One ``BotResult`` as the report carries it."""
    row = {
        "bot_id": result.bot_id,
        "symbol": result.symbol,
        "exchange_id": bot.exchange_id if bot is not None else "",
        "origin": bot.origin if bot is not None else "",
        "target_usd": bot.target_usd if bot is not None else None,
        "asset_class": result.asset_class or "none",
        "venue": result.venue or "none",
        "unit_rule": result.unit_rule or "none",
        "rule_cited": bool(result.unit_rule),
        "outcome": result.outcome,
        "tablet_key": result.tablet_key,
        "candles_read": int(result.candles_read),
        "ticks": int(result.ticks),
        "scrum_latched": int(result.scrum_latched),
        "fold_latched": int(result.fold_latched),
        "trades": len(result.trades),
        "scrums": int(result.scrum_trades),
        "folds": int(result.fold_trades),
        "start_units": result.start_units,
        "end_units": result.end_units,
        "units_gained": result.units_gained,
        "cash_usd": result.cash_usd,
        "fees_usd": result.fees_usd,
        "first": iso_stamp(result.first_ts_ms),
        "last": iso_stamp(result.last_ts_ms),
    }
    return row


def back_test_not_verified(run: BackTestRun) -> list[str]:
    """What the Back Test run could not verify, one line each: the stop line
    first when ``run.stopped``."""
    out = ([run.stopped_line] if run.stopped else []) + [NO_LIVE_FILL_TEXT]
    for asset, venue in run.missing:
        out.append(f"{asset} on {venue}: no Stone Tablet; the bot walked nothing.")
    for result in run.uncited:
        out.append(uncited_rule_line(result))
    for result in run.results:
        if (
            result.outcome not in (BACK_TESTED, UNCITED_RULE)
            and result.tablet_key == ""
        ):
            if result.candles_read:
                out.append(
                    f"{result.bot_id} ({result.symbol}): {result.outcome}, "
                    f"{result.candles_read} candles; the bot walked nothing."
                )
    return out


def back_test_figures(
    run: BackTestRun, tablets: Optional[TabletSource], stamp: str
) -> dict:
    """The figures of one ``BackTestRun``."""
    by_id = {one.bot_id: one for one in run.bots}
    wanted = {(one.asset, one.exchange_id) for one in run.bots}
    tablet_section = tablet_rows(tablets, wanted)
    ran = run.ran
    first_ms = min((one.first_ts_ms for one in ran if one.first_ts_ms), default=0)
    last_ms = max((one.last_ts_ms for one in ran if one.last_ts_ms), default=0)
    if not first_ms and not last_ms:
        first_ms, last_ms = tablet_span(tablet_section)
    subject = (
        f"{run.exchange_id or 'fleet'}-{'-'.join(fleet_origins(run.bots)) or 'none'}"
    )
    head = header(
        BACK_TEST,
        stamp,
        run.bots,
        run.exchange_id,
        first_ms,
        last_ms,
        span_label(first_ms, last_ms),
        run.funding,
        subject,
        run.run_id,
        run.emitted,
    )
    head["budget"]["budget_usd"] = run.budget_usd
    head["interval_ms"] = int(run.interval_ms)
    head["bot_outcomes"] = dict(run.bot_outcomes)
    head["stopped"] = bool(run.stopped)
    head["bots_reached"] = len(run.bots) - len(run.unreached)
    return {
        "mode": BACK_TEST,
        "partial": bool(run.stopped),
        "stopped": bool(run.stopped),
        "error": None,
        "header": head,
        "tablets": tablet_section,
        "bots": [back_test_bot(one, by_id.get(one.bot_id)) for one in run.results],
        "summary": dict(run.summary),
        "not_verified": back_test_not_verified(run),
        "lines": list(run.lines),
    }


def symbol_row(portfolio: str, symbol_run: SymbolRun, whole_usd: float) -> dict:
    """One ``SymbolRun`` as the report carries it, with its weight of
    ``whole_usd``."""
    trades = symbol_run.trades
    return {
        "portfolio": portfolio,
        "timeframe": symbol_run.timeframe,
        "asset": symbol_run.asset,
        "symbol": symbol_run.symbol,
        "exchange_id": symbol_run.exchange_id,
        "capital_usd": symbol_run.capital_usd,
        "weight": symbol_run.capital_usd / whole_usd if whole_usd > 0.0 else 0.0,
        "asset_class": symbol_run.asset_class or "none",
        "venue": symbol_run.venue or "none",
        "unit_rule": symbol_run.unit_rule or "none",
        "rule_cited": bool(symbol_run.unit_rule),
        "outcome": symbol_run.outcome,
        "bars": int(symbol_run.bars),
        "ticks": int(symbol_run.ticks),
        "trades": len(trades),
        "scrums": sum(1 for one in trades if one.side == SCRUM),
        "folds": sum(1 for one in trades if one.side == FOLD),
        "start_units": symbol_run.start_units,
        "end_units": symbol_run.end_units,
        "units_gained": symbol_run.units_gained,
        "baseline_usd": symbol_run.baseline_usd,
        "accumulation_usd": symbol_run.accumulation_usd,
        "fees_usd": symbol_run.fees_usd,
        "first": iso_stamp(symbol_run.first_ts_ms),
        "last": iso_stamp(symbol_run.last_ts_ms),
        "bot_id": symbol_run.bot_id,
        "origin": symbol_run.origin,
        "trough_usd": symbol_run.trough_usd,
        "reading": symbol_run.reading,
        "tablet_timeframe": symbol_run.tablet_timeframe,
        "tablets": symbol_run.tablet_rows,
        "refusal": symbol_run.refusal,
    }


def battery_tablets_by_bot(run: BatteryRun) -> list[dict]:
    """One row per bot of ``run``: the bot's own ``ta_timeframe``, the
    ``tablet_timeframe`` its walk read, every ``TabletRead`` file with its
    candle count and checksum, the timeframes it walked with each outcome,
    and the ``refusal`` where it read no bar."""
    seated = {bot.bot_id: bot for bot in run.bots}
    rows: dict[str, dict] = {}
    for portfolio in run.portfolios:
        for timeframe in portfolio.timeframes:
            for one in timeframe.runs:
                row = rows.get(one.bot_id)
                if row is None:
                    bot = seated.get(one.bot_id)
                    row = {
                        "bot_id": one.bot_id,
                        "asset": one.asset,
                        "exchange_id": one.exchange_id,
                        "ta_timeframe": (
                            str(bot.ta_timeframe) if bot is not None else ""
                        ),
                        "tablet_timeframe": one.tablet_timeframe,
                        "files": list(one.tablet_rows),
                        "candles": sum(
                            int(read["candles"]) for read in one.tablet_rows
                        ),
                        "walked": {},
                        "refusal": one.refusal,
                    }
                    rows[one.bot_id] = row
                row["walked"][one.timeframe] = one.outcome
                if one.refusal and not row["refusal"]:
                    row["refusal"] = one.refusal
    return [rows[key] for key in sorted(rows)]


def timeframe_section(portfolio: str, result: TimeframeResult) -> dict:
    """One ``TimeframeResult``: its ``summary``, the arithmetic and its
    symbol rows."""
    whole = sum(one.capital_usd for one in result.runs)
    summary = dict(result.summary)
    summary["arithmetic"] = (
        f"accumulation {result.accumulation_usd:,.2f} - baseline "
        f"{result.baseline_usd:,.2f} = {result.improvement_usd:,.2f} "
        f"({result.improvement_pct:.2f}%), verdict {result.verdict}"
    )
    summary["symbol_rows"] = [symbol_row(portfolio, one, whole) for one in result.runs]
    return summary


def battery_refusals(run: BatteryRun) -> list[dict]:
    """One entry per refused asset with the line ``uncited_rule_line`` writes."""
    seen: dict[str, dict] = {}
    for portfolio in run.portfolios:
        for timeframe in portfolio.timeframes:
            for one in timeframe.runs:
                if one.outcome == UNCITED_RULE and one.asset not in seen:
                    seen[one.asset] = {
                        "asset": one.asset,
                        "symbol": one.symbol,
                        "exchange_id": one.exchange_id,
                        "asset_class": one.asset_class or "none",
                        "venue": one.venue or "none",
                        "capital_usd": one.capital_usd,
                        "line": uncited_rule_line(one),
                    }
    return [seen[key] for key in sorted(seen)]


def battery_bots(run: BatteryRun) -> list[dict]:
    """Every symbol row of every portfolio and timeframe."""
    rows: list[dict] = []
    for portfolio in run.portfolios:
        for timeframe in portfolio.timeframes:
            whole = sum(one.capital_usd for one in timeframe.runs)
            rows.extend(
                symbol_row(portfolio.name, one, whole) for one in timeframe.runs
            )
    return rows


def battery_not_verified(run: BatteryRun) -> list[str]:
    """What the Portfolio Battery run could not verify, one line each."""
    out: list[str] = []
    refusals = {
        one.asset: one.refusal
        for portfolio in run.portfolios
        for timeframe in portfolio.timeframes
        for one in timeframe.runs
        if one.refusal
    }
    for asset in run.missing_assets:
        out.append(
            f"{asset}: {refusals.get(asset) or 'no RA-StoneTablet'}; its capital "
            "is missing weight."
        )
    for refusal in battery_refusals(run):
        out.append(refusal["line"])
    short = sorted(
        {
            f"{one.asset} at {timeframe.timeframe}"
            for portfolio in run.portfolios
            for timeframe in portfolio.timeframes
            for one in timeframe.runs
            if one.outcome not in (RAN, UNCITED_RULE)
            and one.asset not in run.missing_assets
        }
    )
    for name in short:
        out.append(f"{name}: too few bars; the symbol walked nothing.")
    for gap in run.gaps:
        out.append(
            f"{gap['asset']} on {gap['exchange_id']}: recorded gap {gap['since']} to "
            f"{gap['until']} ({gap['reason']})."
        )
    return out


def battery_outcome(run: BatteryRun) -> dict:
    """The defend, improve or reverse reading of ``run``: the rule, one entry
    per portfolio and timeframe with its arithmetic, and the counts of each
    of ``READINGS`` per timeframe."""
    per_portfolio = [
        {
            "portfolio": portfolio.name,
            "timeframe": frame.timeframe,
            "reading": frame.reading,
            "historical_failed": frame.historical_failed,
            "arithmetic": frame.reading_arithmetic,
        }
        for portfolio in run.portfolios
        for frame in portfolio.timeframes
    ]
    counts = {tf: run.reading_counts(tf) for tf in run.timeframes}
    summary = "; ".join(
        f"at {tf}: " + ", ".join(f"{counts[tf][one]} {one}" for one in READINGS)
        for tf in run.timeframes
    )
    return {
        "defend_improve_reverse": summary or NOT_COMPUTED,
        "rule": BATTERY_READING_RULE,
        "counts": counts,
        "per_portfolio": per_portfolio,
    }


def battery_subject(run: BatteryRun) -> str:
    """``EVERY_PORTFOLIO`` when every ``PORTFOLIOS`` name ran, else the names
    joined."""
    names = [one.name for one in run.portfolios]
    if names and sorted(names) == sorted(PORTFOLIOS):
        return EVERY_PORTFOLIO
    return "-".join(names) or "no-portfolio"


def battery_figures(
    run: BatteryRun, tablets: Optional[TabletSource], stamp: str
) -> dict:
    """The figures of one ``BatteryRun``."""
    bots = battery_bots(run)
    walked = {
        (row["bot_id"], row["timeframe"]) for row in bots if row["outcome"] == RAN
    }
    with_target = [one for one in run.bots if one.target_usd is not None]
    head = {
        "mode": PORTFOLIO_BATTERY,
        "title": MODE_TITLE[PORTFOLIO_BATTERY],
        "stamp": stamp,
        "build": str(__version__),
        "fleet_origin": list(run.fleet_origins) or fleet_origins(run.bots),
        "exchange": "",
        "subject": battery_subject(run),
        "span": {
            "label": run.span,
            "first": iso_stamp(run.start_ms),
            "last": iso_stamp(run.end_ms),
        },
        "bots": len(run.bots),
        "budget": {
            "funding": FUNDED_BY_TARGETS,
            "rule": FUNDING_RULE[FUNDED_BY_TARGETS],
            "budget_usd": float(run.budget_usd),
            "bots_with_target": len(with_target),
            "bots_without_target": len(run.bots) - len(with_target),
            "note": (
                f"the sum of the Target Balances of the run's {len(run.bots)} "
                f"bot(s), origins {', '.join(run.fleet_origins) or 'none'}; "
                f"{len(walked)} (bot, timeframe) walk(s) ran"
            ),
        },
        "tablet_root": run.tablet_root,
        "timeframes": list(run.timeframes),
        "symbol_runs": int(run.symbol_runs),
        "run_id": run.run_id,
        "rows": rows_section(run.run_id, run.emitted),
    }
    portfolios = [
        {
            "name": portfolio.name,
            "description": portfolio.description,
            "span": portfolio.span,
            "first": iso_stamp(portfolio.start_ms),
            "last": iso_stamp(portfolio.end_ms),
            "improved_timeframes": list(portfolio.improved_timeframes),
            "fleet_origin": portfolio.fleet_origin,
            "bot_ids": list(portfolio.bot_ids),
            "readings": dict(portfolio.readings),
            "timeframes": [
                timeframe_section(portfolio.name, one) for one in portfolio.timeframes
            ],
        }
        for portfolio in run.portfolios
    ]
    tablet_section = tablet_rows(tablets)
    tablet_section["by_bot"] = battery_tablets_by_bot(run)
    tablet_section["retrievals"] = [dict(one) for one in run.retrievals]
    return {
        "mode": PORTFOLIO_BATTERY,
        "partial": False,
        "error": None,
        "header": head,
        "tablets": tablet_section,
        "bots": bots,
        "battery": {
            "portfolios": portfolios,
            "refused": battery_refusals(run),
            "gaps": [dict(one) for one in run.gaps],
            "outcome": battery_outcome(run),
        },
        "summary": dict(run.summary),
        "not_verified": battery_not_verified(run),
        "lines": list(run.lines),
    }


FIGURES: dict[str, Callable[..., dict]] = {
    VALIDATION: validation_figures,
    BACK_TEST: back_test_figures,
    PORTFOLIO_BATTERY: battery_figures,
}


def money(value: Optional[float]) -> str:
    """``value`` as ``$1,234.56``, ``none`` when it is None."""
    if value is None:
        return "none"
    return f"${float(value):,.2f}"


def units(value: float) -> str:
    """``value`` to eight places with trailing zeros cut."""
    text = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return text or "0"


def cell(value: object) -> str:
    """``value`` as one Markdown table cell."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "none"
    if isinstance(value, float):
        return units(value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(columns: Sequence[tuple[str, str]], rows: Sequence[dict]) -> list[str]:
    """A Markdown table of ``rows`` over ``columns`` as ``(key, heading)``."""
    if not rows:
        return ["(none)", ""]
    out = [
        "| " + " | ".join(heading for _key, heading in columns) + " |",
        "|" + "|".join("---" for _column in columns) + "|",
    ]
    for row in rows:
        out.append(
            "| " + " | ".join(cell(row.get(key)) for key, _heading in columns) + " |"
        )
    out.append("")
    return out


def render_header(figures: dict) -> list[str]:
    """The ``Run`` section."""
    head = figures["header"]
    span = head["span"]
    budget = head["budget"]
    out = [
        f"# Simulator trade parity report: {head['title']}",
        "",
        "## Run",
        "",
        f"- mode: {head['mode']}",
        f"- written: {head['stamp']} (UTC)",
        f"- build: {head['build']}",
        f"- fleet origin: {', '.join(head['fleet_origin']) or 'none'}",
        f"- exchange: {head['exchange'] or 'none'}",
        f"- subject: {head['subject']}",
        f"- span: {span['label']} ({span['first'] or 'unknown'} to "
        f"{span['last'] or 'unknown'})",
        f"- bots: {head['bots']}",
        f"- funding: {budget['funding']}; {budget['rule']}",
        f"- budget: {money(budget['budget_usd'])}; "
        f"{budget['bots_with_target']} bots "
        f"with a Target Balance, {budget['bots_without_target']} without",
    ]
    if budget.get("note"):
        out.append(f"- budget note: {budget['note']}")
    for key in (
        "match_key",
        "gate_rows_read",
        "interval_ms",
        "tablet_root",
        "symbol_runs",
    ):
        if key in head:
            out.append(f"- {key.replace('_', ' ')}: {head[key]}")
    if "bot_outcomes" in head:
        out.append(
            "- bot outcomes: "
            + ", ".join(
                f"{name} {count}" for name, count in head["bot_outcomes"].items()
            )
        )
    if figures.get("stopped"):
        out.append(
            f"- partial: yes; {STOPPED_NOTE}; {head.get('bots_reached', 0)} of "
            f"{head['bots']} bots reached"
        )
    elif figures.get("partial"):
        error = figures.get("error") or {}
        out.append(
            f"- partial: yes; the run raised {error.get('type')}: "
            f"{error.get('message')}"
        )
    out += render_rows(head.get("rows") or {})
    out.append("")
    return out


def render_rows(rows: dict) -> list[str]:
    """The ``Run`` lines naming the run's sim log rows: the run id, the four
    files, the rows emitted per topic and the ``EmitObserver`` reading."""
    run_id = rows.get("run_id") or ""
    if not run_id:
        return [
            "- run id: none; no bus was handed to the run, so no sim log row was written"
        ]
    emitted = rows.get("emitted") or {}
    observed = rows.get("observed") or {}
    violations = rows.get("violations") or []
    out = [
        f"- run id: {run_id}",
        "- row files: "
        + ", ".join(
            f"{name} {path}" for name, path in (rows.get("files") or {}).items()
        ),
        "- rows emitted: "
        + (", ".join(f"{topic} {count}" for topic, count in emitted.items()) or "none"),
        f"- observer: {rows.get('topics_seen', 0)} of {rows.get('topics_declared', 0)} "
        "declared topic(s) seen; "
        + (
            ", ".join(f"{topic} {count}" for topic, count in observed.items())
            or "nothing observed"
        )
        + f"; {len(violations)} violation(s)",
    ]
    for one in violations:
        out.append(
            f"- observer violation: [{one.get('kind')}] {one.get('topic')}: "
            f"{one.get('detail')} (x{one.get('count', 1)})"
        )
    return out


TABLET_COLUMNS = (
    ("key", "tablet"),
    ("asset", "asset"),
    ("exchange_id", "exchange"),
    ("timeframe", "timeframe"),
    ("year", "year"),
    ("candles", "candles"),
    ("first", "first"),
    ("last", "last"),
    ("sha256", "sha256"),
)


def render_tablets(figures: dict) -> list[str]:
    """The ``Tablets`` section."""
    section = figures.get("tablets") or {}
    out = ["## Tablets", ""]
    if "unread" in section:
        out += [f"not read: {section['unread']}", ""]
        return out
    out.append(f"root: {section.get('root', '')}")
    out.append("")
    out += table(TABLET_COLUMNS, section.get("rows") or [])
    by_bot = section.get("by_bot") or []
    if by_bot:
        out += ["", "### Per bot", ""]
        out += table(
            TABLET_BY_BOT_COLUMNS,
            [
                {
                    "bot_id": row["bot_id"],
                    "ta_timeframe": row["ta_timeframe"],
                    "tablet_timeframe": row["tablet_timeframe"] or "none",
                    "files": ", ".join(read["file"] for read in row["files"]) or "none",
                    "candles": int(row["candles"]),
                    "sha256": ", ".join(read["sha256"][:12] for read in row["files"])
                    or "none",
                    "walked": ", ".join(
                        f"{tf} {outcome}" for tf, outcome in row["walked"].items()
                    ),
                    "refusal": row["refusal"] or "",
                }
                for row in by_bot
            ],
        )
    retrievals = section.get("retrievals") or []
    if retrievals:
        out += ["", "### Retrieved before the walk", ""]
        out += table(TABLET_RETRIEVAL_COLUMNS, retrievals)
    return out


TABLET_BY_BOT_COLUMNS = (
    ("bot_id", "bot"),
    ("ta_timeframe", "bot timeframe"),
    ("tablet_timeframe", "tablet timeframe"),
    ("files", "file"),
    ("candles", "candles"),
    ("sha256", "sha256"),
    ("walked", "walked"),
    ("refusal", "refusal"),
)

TABLET_RETRIEVAL_COLUMNS = (
    ("asset", "asset"),
    ("exchange_id", "venue"),
    ("timeframe", "timeframe"),
    ("since", "since"),
    ("until", "until"),
    ("candles_asked", "candles asked"),
    ("candles_appended", "appended"),
    ("chunks", "chunks walked"),
    ("chunks_fetched", "chunks fetched"),
    ("calls", "calls"),
    ("refused", "refused"),
    ("error", "error"),
)


BOT_COLUMNS = {
    VALIDATION: (
        ("bot_id", "bot"),
        ("symbol", "symbol"),
        ("target_usd", "target"),
        ("origin", "origin"),
        ("asset_class", "class"),
        ("venue", "venue"),
        ("unit_rule", "unit rule"),
        ("rule_cited", "cited"),
        ("outcome", "outcome"),
        ("snapped", "snapped"),
        ("unsnapped", "unsnapped"),
        ("compared", "compared"),
        ("latching", "latching"),
    ),
    BACK_TEST: (
        ("bot_id", "bot"),
        ("symbol", "symbol"),
        ("target_usd", "target"),
        ("origin", "origin"),
        ("asset_class", "class"),
        ("venue", "venue"),
        ("unit_rule", "unit rule"),
        ("rule_cited", "cited"),
        ("outcome", "outcome"),
        ("tablet_key", "tablet"),
        ("ticks", "ticks"),
        ("trades", "trades"),
        ("scrums", "scrums"),
        ("folds", "folds"),
        ("start_units", "start units"),
        ("end_units", "end units"),
        ("units_gained", "units gained"),
        ("cash_usd", "cash"),
        ("fees_usd", "fees"),
    ),
    PORTFOLIO_BATTERY: (
        ("portfolio", "portfolio"),
        ("timeframe", "timeframe"),
        ("asset", "asset"),
        ("exchange_id", "tablet venue"),
        ("capital_usd", "target"),
        ("weight", "weight"),
        ("asset_class", "class"),
        ("venue", "venue"),
        ("unit_rule", "unit rule"),
        ("rule_cited", "cited"),
        ("outcome", "outcome"),
        ("ticks", "ticks"),
        ("trades", "trades"),
        ("scrums", "scrums"),
        ("folds", "folds"),
        ("units_gained", "units gained"),
        ("baseline_usd", "baseline"),
        ("accumulation_usd", "accumulation"),
    ),
}


def render_bots(figures: dict) -> list[str]:
    """The ``Bots`` section."""
    return ["## Bots", ""] + table(
        BOT_COLUMNS[figures["mode"]], figures.get("bots") or []
    )


COMPARISON_COLUMNS = (
    ("trade_id", "trade"),
    ("bot_id", "bot"),
    ("symbol", "symbol"),
    ("trade_at", "trade at"),
    ("candle_at", "candle"),
    ("gate_row_at", "gate row"),
    ("latches_identically", "latches identically"),
    ("agreed", "agreed"),
    ("lights", "lights"),
    ("armed", "armed recorded / rerun"),
    ("disagreed_text", "disagreeing lights (recorded > rerun, driver)"),
    ("unknown_text", "blockers with no light (recorded / rerun)"),
)


def render_comparison(figures: dict) -> list[str]:
    """The ``Gate-light comparison`` section."""
    section = figures.get("comparison")
    if section is None:
        return []
    counts = section["counts"]
    out = ["## Gate-light comparison", ""]
    out += [
        f"- rows compared: {counts['rows_compared']}",
        f"- rows latching identically: {counts['rows_latching_identically']}",
        f"- rows disagreeing: {counts['rows_disagreeing']}",
        f"- lights compared: {counts['lights_compared']}",
        f"- lights agreeing: {counts['lights_agreeing']}",
        f"- lights disagreeing: {counts['lights_disagreeing']}",
        "",
        "| count | value | definition |",
        "|---|---|---|",
    ]
    for name in COUNT_NAMES:
        out.append(
            f"| {name.replace('_', ' ')} | {counts[name]} | "
            f"{section['definitions'][name]} |"
        )
    out.append("")
    by_cause = counts.get(BY_CAUSE) or {}
    cause_words = section.get("cause_definitions") or {}
    if by_cause:
        out.append(
            "- differs by cause: "
            + ", ".join(f"{name} {by_cause.get(name, 0)}" for name in CAUSES)
        )
        out += ["", "| cause | definition |", "|---|---|"]
        for name in CAUSES:
            out.append(f"| {name} | {cause_words.get(name, '')} |")
        out.append("")
    rows = []
    for row in section["rows"]:
        shown = dict(row)
        shown["armed"] = (
            f"S {cell(row['recorded_armed']['scrum'])}/"
            f"{cell(row['rerun_armed']['scrum'])}, "
            f"F {cell(row['recorded_armed']['fold'])}/"
            f"{cell(row['rerun_armed']['fold'])}"
        )
        shown["disagreed_text"] = "; ".join(
            f"{one['bank']}/{one['label']} {one['recorded']} > {one['rerun']} "
            f"({one['driven_by']}, {one.get('cause') or 'agrees'})"
            for one in row["disagreed"]
        )
        shown["unknown_text"] = (
            (", ".join(row["unknown_recorded_blockers"]) or "none")
            + " / "
            + (", ".join(row["unknown_rerun_blockers"]) or "none")
        )
        rows.append(shown)
    out += table(COMPARISON_COLUMNS, rows)
    return out


def render_battery(figures: dict) -> list[str]:
    """The ``Portfolio Battery`` section."""
    section = figures.get("battery")
    if section is None:
        return []
    out = ["## Portfolio Battery", ""]
    outcome = section["outcome"]
    out += [
        f"- defend, improve or reverse: {outcome['defend_improve_reverse']}",
        f"- the reading: {outcome['rule']}",
        "",
    ]
    for portfolio in section["portfolios"]:
        readings = ", ".join(
            f"{tf} {read}" for tf, read in portfolio.get("readings", {}).items()
        )
        out += [
            f"### {portfolio['name']}: {portfolio['description']}",
            "",
            f"- span: {portfolio['span']} ({portfolio['first']} to "
            f"{portfolio['last']})",
            f"- bots: {portfolio.get('fleet_origin', '')} ("
            + (", ".join(portfolio.get("bot_ids", [])) or "none")
            + ")",
            f"- defend, improve or reverse: {readings or 'none'}",
            "- improved timeframes: "
            + (", ".join(portfolio["improved_timeframes"]) or "none"),
            "",
        ]
        for frame in portfolio["timeframes"]:
            out += [
                f"#### {portfolio['name']} at {frame['timeframe']}",
                "",
                f"- reading: {frame.get('reading_arithmetic', NOT_COMPUTED)}",
                f"- symbols: {frame['symbols_run']} of {frame['symbols']} ran",
                f"- committed: {money(frame['committed_usd'])}; missing: "
                f"{money(frame['missing_usd'])} "
                f"({frame['missing_weight'] * 100:.2f}% of the weight)"
                + (
                    f"; missing symbols: {', '.join(frame['missing_symbols'])}"
                    if frame["missing_symbols"]
                    else ""
                ),
                f"- {frame['arithmetic']}",
                f"- units gained: {units(frame['units_gained'])}; "
                f"trades: {frame['trades']}; fees: {money(frame['fees_usd'])}",
                "",
            ]
    refused = section["refused"]
    out += ["### Refused symbols", ""]
    if refused:
        out += [f"- {one['line']}" for one in refused]
    else:
        out.append("(none)")
    out.append("")
    return out


def render_summary(figures: dict) -> list[str]:
    """The ``Summary`` section, the run's own ``summary`` dict."""
    summary = figures.get("summary")
    if not summary:
        return []
    out = ["## Summary", ""]
    for key, value in summary.items():
        if isinstance(value, dict):
            continue
        shown = (
            ", ".join(str(one) for one in value)
            if isinstance(value, list)
            else cell(value)
        )
        out.append(f"- {key.replace('_', ' ')}: {shown}")
    out.append("")
    return out


def render_not_verified(figures: dict) -> list[str]:
    """The ``Not verified`` section, one line per entry."""
    entries = figures.get("not_verified") or [NOTHING_UNVERIFIED]
    return ["## Not verified", ""] + [f"- {one}" for one in entries] + [""]


def render_lines(figures: dict) -> list[str]:
    """The ``Lines`` section, the run's own Activity Log lines."""
    lines = figures.get("lines") or []
    out = ["## Lines", ""]
    out += [f"- {one}" for one in lines] if lines else ["(none)"]
    out.append("")
    return out


def render_markdown(figures: dict) -> str:
    """The whole Markdown report of ``figures``."""
    parts = (
        render_header(figures)
        + render_tablets(figures)
        + render_bots(figures)
        + render_comparison(figures)
        + render_battery(figures)
        + render_summary(figures)
        + render_not_verified(figures)
        + render_lines(figures)
    )
    return "\n".join(parts).rstrip("\n") + "\n"


def write_figures(figures: dict, stamp: str) -> ParityReport:
    """Write ``figures`` as Markdown and JSON under ``reports_dir`` and answer
    where they landed."""
    head = figures["header"]
    stem = report_name(figures["mode"], head["subject"], head["span"]["label"], stamp)
    markdown, sidecar = create_pair(reports_dir(), stem)
    with open(markdown, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_markdown(figures))
    with open(sidecar, "x", encoding="utf-8", newline="\n") as handle:
        json.dump(figures, handle, indent=1, default=str)
        handle.write("\n")
    error = figures.get("error") or {}
    return ParityReport(
        mode=figures["mode"],
        name=markdown.stem,
        markdown_path=markdown,
        json_path=sidecar,
        stamp=stamp,
        partial=bool(figures.get("partial")),
        error=f"{error.get('type')}: {error.get('message')}" if error else "",
        stopped=bool(figures.get("stopped")),
        run_id=str(figures.get("header", {}).get("run_id") or ""),
    )


def write_report(
    mode: str, run: object, tablets: Optional[TabletSource]
) -> ParityReport:
    """Write the report of a finished ``run`` in ``mode`` and answer where it
    landed."""
    stamp = utc_stamp()
    return write_figures(FIGURES[mode](run, tablets, stamp), stamp)


def partial_figures(
    mode: str,
    error: BaseException,
    stamp: str,
    bots: Sequence[SimBot] = (),
    exchange_id: str = "",
    tablets: Optional[TabletSource] = None,
    funding: str = "",
    names: Sequence[str] = (),
    span: str = "",
    run_id: str = "",
) -> dict:
    """The figures a run in ``mode`` had when ``error`` was raised."""
    if mode == PORTFOLIO_BATTERY:
        subject = EVERY_PORTFOLIO if not names else "-".join(str(one) for one in names)
        funding = funding or FUNDED_BY_TARGETS
    else:
        subject = f"{exchange_id or 'fleet'}-{'-'.join(fleet_origins(bots)) or 'none'}"
        funding = funding or (
            FUNDED_BY_PROCEEDS if mode == BACK_TEST else FUNDED_BY_TARGETS
        )
    head = header(
        mode,
        stamp,
        bots,
        exchange_id,
        0,
        0,
        span or "no-span",
        funding,
        subject,
        run_id,
    )
    bot_rows = []
    for bot in bots:
        row = {
            "bot_id": bot.bot_id,
            "symbol": bot.symbol,
            "exchange_id": bot.exchange_id,
            "origin": bot.origin,
            "target_usd": bot.target_usd,
            "outcome": "not reached",
        }
        row.update(rule_row(bot.asset, bot.exchange_id))
        bot_rows.append(row)
    return {
        "mode": mode,
        "partial": True,
        "error": {"type": type(error).__name__, "message": str(error)},
        "header": head,
        "tablets": tablet_rows(tablets),
        "bots": bot_rows,
        "not_verified": [
            f"Nothing was verified: the run raised {type(error).__name__}: {error}."
        ],
        "lines": [],
    }


def write_partial(
    mode: str, error: BaseException, **held: object
) -> Optional[ParityReport]:
    """Write the partial report of a run in ``mode`` that raised ``error``,
    from the ``held`` arguments ``partial_figures`` takes; a write that itself
    fails is logged and answers None so ``error`` is what propagates."""
    stamp = utc_stamp()
    try:
        return write_figures(partial_figures(mode, error, stamp, **held), stamp)
    except Exception:  # noqa: BLE001 - the run's own error must propagate
        logger.exception("parity_report: partial %s report not written", mode)
        return None


def report_line(report: ParityReport) -> str:
    """The Activity Log line naming ``report.markdown_path``."""
    return REPORT_LINE_FORMAT.format(
        mode=MODE_TITLE.get(report.mode, report.mode), path=report.markdown_path
    )


__all__ = [
    "BACK_TEST",
    "BATTERY_READING_RULE",
    "BY_CAUSE",
    "CAUSE_DEFINITIONS",
    "COUNT_DEFINITIONS",
    "COUNT_NAMES",
    "DIFFERS",
    "EXTRA",
    "FUNDING_RULE",
    "MISSING",
    "MODES",
    "MODE_TITLE",
    "NOT_COMPUTED",
    "PORTFOLIO_BATTERY",
    "REPORTS_SUBDIR",
    "REPORT_LINE_FORMAT",
    "STAMP_FORMAT",
    "STOPPED_NOTE",
    "VALIDATION",
    "VARIANT_DIFFERS",
    "ParityReport",
    "back_test_figures",
    "battery_figures",
    "battery_outcome",
    "battery_tablets_by_bot",
    "comparison_counts",
    "comparison_row",
    "create_pair",
    "partial_figures",
    "new_run_id",
    "render_markdown",
    "render_rows",
    "report_line",
    "report_name",
    "rows_section",
    "reports_dir",
    "safe_name",
    "span_label",
    "tablet_rows",
    "utc_stamp",
    "validation_figures",
    "write_figures",
    "write_partial",
    "write_report",
]
