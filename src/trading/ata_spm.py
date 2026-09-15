"""ata_spm.py -- the ATA-SPM run, phases one to three and eight.

``evaluate`` scans each ``Sector`` on its ticked timeframes and answers a
``SectorScan`` per sector. ``identify`` ranks every ``AssetVote`` the run cast,
and ``pull`` loads that chart with the ``IndicatorMessage`` rows confirming it.
``pull`` runs the live trade gates over that chart and renders a PNG under
``ata_post_paths`` only while ``ata_gate_scan.GateScan.would_fire`` answers
True, so a post carries a picture of a market Acervator would trade. ``agreement_for`` is phase eight: every
timeframe one call's asset voted on, and whether those votes agree.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..gui.native_chart import Candle, ChartImage, render_chart_png
from . import ata_gate_scan, ata_post_paths
from .ata_gate_scan import (
    BAND_LOWER_KEY,
    BAND_MIDDLE_KEY,
    BAND_POSITION_KEY,
    BAND_UPPER_KEY,
)
from .indicators.bb_proximity import detect_bb_proximity
from .indicators.bollinger import BollingerBands
from .indicators.types import (
    PERCENT_PER_RATIO_UNIT,
    Signal,
    SignalDirection,
    VotingSummary,
)
from .otd_math import minimum_opposing_trade_distance_pct
from .ta_engine import VotingEngine

logger = logging.getLogger("acervator.ata_spm")

CLASS_CRYPTO = "crypto"
CLASS_STOCKS = "stocks"
CLASS_METALS = "metals"
CLASS_DERIVATIVES = "derivatives"
CLASS_FOREX = "forex"

#: Every major asset class that charts and takes TA.
ASSET_CLASSES = (
    CLASS_CRYPTO,
    CLASS_STOCKS,
    CLASS_METALS,
    CLASS_DERIVATIVES,
    CLASS_FOREX,
)

CRYPTO_TIMEFRAMES = ("5m", "1h", "1d", "1w")
SLOWER_TIMEFRAMES = ("1h", "1d", "1w", "1M")

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60

#: The seconds one candle of the shortest timeframe each class scans covers.
#: An asset's rounds finish inside it or the chart already moved on.
SHORTEST_TIMEFRAME_SECONDS = {
    CRYPTO_TIMEFRAMES[0]: 5 * SECONDS_PER_MINUTE,
    SLOWER_TIMEFRAMES[0]: MINUTES_PER_HOUR * SECONDS_PER_MINUTE,
}

MIN_TIMEFRAMES_PER_ASSET = 1
NO_ROUND_MEASURED = 0.0
NO_CANDLES = 0

#: The candles one timeframe needs before ``_scan_timeframe`` votes on it.
MIN_CANDLES_TO_VOTE = ata_gate_scan.MIN_CANDLES_FOR_TA

#: The check-box wording for each timeframe key the engine reads.
TIMEFRAME_LABELS = {
    "5m": "5m",
    "1h": "1hr",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mnth",
}

DIRECTION_BULLISH = "bullish"
DIRECTION_BEARISH = "bearish"
DIRECTION_NEUTRAL = "neutral"

DIRECTION_NAMES = {
    SignalDirection.BULLISH: DIRECTION_BULLISH,
    SignalDirection.BEARISH: DIRECTION_BEARISH,
    SignalDirection.NEUTRAL: DIRECTION_NEUTRAL,
}

#: The voter that reads where the close sits between Bollinger's bands.
BAND_INDICATOR = "bollinger_bands"

#: The Heikin Ashi body percent under which ``detect_bb_proximity`` calls a
#: window tight, the same threshold ``ScrummingBot.tick`` passes.
CONSOLIDATION_THRESHOLD = 3.0

MIDLINE_POSITION = 0.5
NO_BAND_VALUE = 0.0
NO_BARS = 0
NO_TIMESTAMP = 0.0

#: A cap of zero draws every confirming indicator, in a post and on its chart.
NO_INDICATOR_CAP = 0

#: One standardised message per confirming voter. The same condition reads
#: the same way in every run.
MESSAGE_FORMAT = "{label}: {reading}. Votes {direction} at {confidence}% confidence."
NO_READING_TEXT = "no reading published"

#: Each voter's screen name, the ``Signal.details`` keys carrying the reading
#: its own direction is decided by, and the wording they are printed in.
#: ``value`` binds the first key, so a one-key row reads by that name.
READINGS: dict[str, tuple[str, tuple, str]] = {
    "bollinger_bands": (
        "Bollinger Bands",
        (BAND_POSITION_KEY,),
        "band position {value:.4f}",
    ),
    "vortex": ("Vortex", ("separation",), "VI+ less VI- at {value:+.4f}"),
    # The histogram is a price, so it prints significant figures, not decimals.
    "macd": ("MACD", ("histogram",), "histogram {value:+.8g}"),
    "stochastic_rsi": ("Stochastic RSI", ("k",), "%K at {value:.2f}"),
    "ichimoku": ("Ichimoku Cloud", ("price_vs_cloud",), "price {value} the cloud"),
    "volume": ("Volume", ("mfi",), "Money Flow Index {value:.1f}"),
    "slingshot": ("Slingshot", ("momentum",), "momentum {value:+.6f}"),
    "adx": (
        "ADX",
        ("di_plus", "di_minus", "adx"),
        "+DI {di_plus:.2f} against -DI {di_minus:.2f}, trend strength ADX {adx:.2f}",
    ),
    "supertrend": (
        "Supertrend",
        ("dist_pct",),
        "{value:+.3f}% from the Supertrend line",
    ),
    "zscore": (
        "Z-Score",
        ("z", "support_price", "resistance_price"),
        "z-score {z:+.3f}, predictive zone {support_price:g} to {resistance_price:g}",
    ),
    "kaufman_er": (
        "Kaufman Efficiency Ratio",
        ("er", "price_up"),
        "efficiency ratio {er:.4f}, close {price_up} the window open",
    ),
    "rsi": ("RSI", ("rsi",), "RSI {value:.2f}"),
}

#: The two words one boolean reading prints as, the true word first.
READING_WORDS = {"price_up": ("above", "below")}

PHASE_EVALUATE = "Phase 1 Evaluate"
PHASE_IDENTIFY = "Phase 2 Identify"
PHASE_PULL = "Phase 3 Pull"
PHASE_UNRUN = "No run yet"

SECTOR_LINE_FORMAT = "{sector} ({asset_class})"
SECTOR_META_FORMAT = "{assets} asset(s) · {votes} vote(s) · {calls} reversal call(s)"
TIMEFRAME_VOTE_FORMAT = (
    "{votes} vote(s), {unread} without candles, {short} under {floor} candles"
)
NO_TIMEFRAME_TEXT = "No timeframe ticked."
NO_ASSET_TEXT = "No asset source wired for {asset_class}."
UNLISTED_TEXT = "No configured venue lists {symbols}."
UNSERVED_TEXT = "No venue serves {labels}."
SYMBOL_SEPARATOR = ", "
CALL_LINE_FORMAT = "{symbol} on {label}: {direction} reversal"
CALL_META_FORMAT = (
    "{direction} reversal · net {net:+.4f} · confidence {confidence}% "
    "· band position {band:.4f}"
)
CHART_LINE_FORMAT = "{bars} candles, last close {close:g}"
BAND_LINE_FORMAT = "lower {lower:g} · middle {middle:g} · upper {upper:g}"

PHASE_RUN_FORMAT = (
    "{phase}: {sectors} sector(s), {calls} call(s), {pulls} chart(s), "
    "{refused} refused by the gates"
)

AGREEMENT_ROW_FORMAT = "{label} {direction}"
AGREEMENT_ROW_SEPARATOR = " · "
AGREEMENT_LABEL_SEPARATOR = ", "
AGREEMENT_AGREED_TEXT = "Every timeframe agrees."
AGREEMENT_SINGLE_TEXT = "Only one timeframe voted."
AGREEMENT_CONTRADICTED_FORMAT = "Contradicted on {labels}."
AGREEMENT_LINE_FORMAT = "Timeframes: {rows}. {verdict}"

TIMEFRAME_COUNT_FORMAT = (
    "{scanned} of {available} timeframe(s) at {seconds:.4f}s per round"
)
TIMEFRAME_DEFERRED_FORMAT = "{scanned} of {available} scanned, deferred {labels}"

#: The direction a vote contradicts, which is the one the call did not name.
OPPOSITE_DIRECTION = {
    SignalDirection.BULLISH: SignalDirection.BEARISH,
    SignalDirection.BEARISH: SignalDirection.BULLISH,
}

CANDLE_READ_FAILED_LOG = "ATA-SPM candle read failed on %s %s: %s"
CANDLE_SHAPE_LOG = "ATA-SPM candle row is not OHLCV: %s"
ASSET_READ_FAILED_LOG = "ATA-SPM asset read failed on %s: %s"
VOTE_FAILED_LOG = "ATA-SPM vote failed on %s %s: %s"


def timeframes_for(asset_class: Any) -> tuple:
    """The four timeframes one asset class is scanned on.

    Crypto reads ``CRYPTO_TIMEFRAMES`` and every other class reads
    ``SLOWER_TIMEFRAMES``.
    """
    if str(asset_class) == CLASS_CRYPTO:
        return CRYPTO_TIMEFRAMES
    return SLOWER_TIMEFRAMES


def timeframe_label(timeframe: Any) -> str:
    """The check-box wording ``TIMEFRAME_LABELS`` gives one timeframe key."""
    return TIMEFRAME_LABELS.get(str(timeframe), str(timeframe))


def scan_budget_s(asset_class: Any) -> int:
    """The seconds one asset's rounds have to finish inside.

    ``SHORTEST_TIMEFRAME_SECONDS`` reads the first timeframe of the class.
    """
    return SHORTEST_TIMEFRAME_SECONDS[timeframes_for(asset_class)[0]]


def timeframes_supported(round_seconds: Any, asset_class: Any) -> int:
    """How many timeframes one asset is scanned on, from a measured round.

    Never under ``MIN_TIMEFRAMES_PER_ASSET`` and never over the count
    ``timeframes_for`` lists; ``NO_ROUND_MEASURED`` answers that count.
    """
    available = len(timeframes_for(asset_class))
    cost = float(round_seconds or NO_ROUND_MEASURED)
    if cost <= NO_ROUND_MEASURED:
        return available
    fits = int(scan_budget_s(asset_class) // cost)
    return max(MIN_TIMEFRAMES_PER_ASSET, min(available, fits))


def direction_name(direction: Any) -> str:
    """One ``SignalDirection`` as the word the screen prints."""
    return DIRECTION_NAMES.get(direction, DIRECTION_NEUTRAL)


def confidence_pct(confidence: Any) -> int:
    """One confidence ratio as the whole percent the panel prints."""
    return round(float(confidence) * PERCENT_PER_RATIO_UNIT)


@dataclass
class Sector:
    """One market sector to scan, and the timeframes ticked on it."""

    name: str
    asset_class: str = CLASS_CRYPTO
    timeframes: tuple = ()

    def ticked(self) -> tuple:
        """The ticked timeframes, in the order this sector's class lists them."""
        held = {str(one) for one in self.timeframes}
        return tuple(one for one in timeframes_for(self.asset_class) if one in held)

    def boxes(self) -> list:
        """One row per check box: its key, its wording and whether it is ticked."""
        held = {str(one) for one in self.timeframes}
        return [
            [one, timeframe_label(one), one in held]
            for one in timeframes_for(self.asset_class)
        ]


@dataclass
class AssetVote:
    """One asset's vote on one timeframe, as the twelve voters cast it."""

    symbol: str
    timeframe: str
    direction: SignalDirection = SignalDirection.NEUTRAL
    net_score: float = 0.0
    confidence: float = 0.0
    band_position: float = MIDLINE_POSITION
    band_direction: SignalDirection = SignalDirection.NEUTRAL
    signals: list = field(default_factory=list)
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    summary: Optional[VotingSummary] = None

    def panel_row(self) -> dict:
        """This vote as one Indicator Voting Panel row for its timeframe.

        The keys are the ones ``IndicatorVotingPanel.update_data`` reads
        off each timeframe.
        """
        return {
            "bullish": self.bullish_count,
            "bearish": self.bearish_count,
            "neutral": self.neutral_count,
            "net_score": self.net_score,
            "confidence": self.confidence,
            "direction": direction_name(self.direction).upper(),
            "signals": [
                {
                    "indicator": one.indicator,
                    "direction": one.direction.name,
                    "confidence": round(one.confidence, 3),
                    "details": dict(getattr(one, "details", None) or {}),
                }
                for one in self.signals
            ],
            "locks": [],
        }

    @property
    def is_reversal(self) -> bool:
        """True while the band voter and the consensus name one direction.

        A ``SignalDirection.NEUTRAL`` on either side is not a reversal.
        """
        if self.direction == SignalDirection.NEUTRAL:
            return False
        return self.band_direction == self.direction

    @property
    def direction_text(self) -> str:
        """The vote's direction as the word the screen prints."""
        return direction_name(self.direction)


@dataclass
class TimeframeScan:
    """What one ticked timeframe of one sector returned.

    ``short`` names every asset whose history reached fewer than
    ``MIN_CANDLES_TO_VOTE`` candles, which is reported and never voted.
    """

    timeframe: str
    votes: list = field(default_factory=list)
    unread: list = field(default_factory=list)
    short: list = field(default_factory=list)

    @property
    def calls(self) -> list:
        """The votes on this timeframe carrying a reversal."""
        return [one for one in self.votes if one.is_reversal]


@dataclass
class RoundCost:
    """What one scan round costs: one asset, one timeframe, read to vote."""

    rounds: int = 0
    seconds: float = 0.0

    def take(self, seconds: Any) -> None:
        """Take one more round of ``seconds`` into the running total."""
        self.rounds += 1
        self.seconds += float(seconds)

    @property
    def per_round_s(self) -> float:
        """The seconds one round cost, ``NO_ROUND_MEASURED`` before any ran."""
        if self.rounds <= 0:
            return NO_ROUND_MEASURED
        return self.seconds / self.rounds


@dataclass
class TimeframeAgreement:
    """Phase eight: every timeframe one asset voted on, and their verdict."""

    symbol: str
    direction: SignalDirection = SignalDirection.NEUTRAL
    rows: tuple = ()
    against: tuple = ()

    @property
    def agreed(self) -> bool:
        """True while more than one timeframe voted and none named the opposite."""
        return len(self.rows) > 1 and not self.against

    @property
    def verdict(self) -> str:
        """Whether the timeframes agree, one contradicts, or only one voted."""
        if self.against:
            return AGREEMENT_CONTRADICTED_FORMAT.format(
                labels=AGREEMENT_LABEL_SEPARATOR.join(self.against)
            )
        if len(self.rows) > 1:
            return AGREEMENT_AGREED_TEXT
        return AGREEMENT_SINGLE_TEXT

    @property
    def text(self) -> str:
        """The one line a post and the ATA-SPM zone both read this from."""
        return AGREEMENT_LINE_FORMAT.format(
            rows=AGREEMENT_ROW_SEPARATOR.join(
                AGREEMENT_ROW_FORMAT.format(label=label, direction=word)
                for label, word in self.rows
            ),
            verdict=self.verdict,
        )


@dataclass
class SectorScan:
    """What one sector returned across every timeframe ticked on it."""

    sector: str
    asset_class: str = CLASS_CRYPTO
    assets: list = field(default_factory=list)
    timeframes: list = field(default_factory=list)
    note: str = ""
    round_seconds: float = NO_ROUND_MEASURED
    deferred: tuple = ()
    unlisted: tuple = ()
    unserved: tuple = ()

    @property
    def supported(self) -> int:
        """How many timeframes the measured round supports for this class."""
        return timeframes_supported(self.round_seconds, self.asset_class)

    @property
    def votes(self) -> list:
        """Every vote this sector's timeframes cast, in scan order."""
        found: list = []
        for one in self.timeframes:
            found.extend(one.votes)
        return found

    @property
    def calls(self) -> list:
        """Every vote this sector cast that carries a reversal."""
        return [one for one in self.votes if one.is_reversal]


@dataclass
class IndicatorMessage:
    """One confirming voter and the standardised sentence explaining it."""

    indicator: str
    label: str
    message: str


@dataclass
class ChartPull:
    """The chart one reversal call was made on, and its confirming messages.

    ``image`` is that chart rendered to a PNG, which the post's caption
    captions. A call ``gates`` refused carries the default empty ``ChartImage``.
    """

    symbol: str
    timeframe: str
    direction: SignalDirection = SignalDirection.NEUTRAL
    bars: int = NO_BARS
    first_ts: float = NO_TIMESTAMP
    last_ts: float = NO_TIMESTAMP
    last_close: float = NO_BAND_VALUE
    band_upper: float = NO_BAND_VALUE
    band_middle: float = NO_BAND_VALUE
    band_lower: float = NO_BAND_VALUE
    closes: tuple = ()
    agreement: Optional[TimeframeAgreement] = None
    messages: list = field(default_factory=list)
    landing_strip_side: str = ""
    landing_strip_candles: int = NO_BARS
    otd_pct: float = NO_BAND_VALUE
    gates: ata_gate_scan.GateScan = field(default_factory=ata_gate_scan.GateScan)
    panel: dict = field(default_factory=dict)
    image: ChartImage = field(default_factory=ChartImage)


@dataclass
class AtaSpmRun:
    """One ATA-SPM run: what phases one, two and three each produced.

    ``calls`` holds the votes the live chains would fire and ``pulls`` their
    charts; ``refused`` holds the ``ata_gate_scan.GateScan`` of every other
    vote, which drew no chart and reached no bucket.
    """

    scans: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    pulls: list = field(default_factory=list)
    refused: list = field(default_factory=list)

    @property
    def phase(self) -> str:
        """The last phase this run reached, and what it produced."""
        if not self.scans:
            return PHASE_UNRUN
        reached = PHASE_EVALUATE
        if self.calls:
            reached = PHASE_IDENTIFY
        if self.pulls:
            reached = PHASE_PULL
        return PHASE_RUN_FORMAT.format(
            phase=reached,
            sectors=len(self.scans),
            calls=len(self.calls),
            pulls=len(self.pulls),
            refused=len(self.refused),
        )

    def report(self) -> dict:
        """The run as the ATA-SPM zone's status line reads it.

        The Ready to Send count belongs to the bucket, and the host holding
        one writes it in beside ``phase``.
        """
        return {"phase": self.phase}


def band_signal(summary: Any) -> Optional[Signal]:
    """The ``BAND_INDICATOR`` vote inside one ``VotingSummary``."""
    for one in getattr(summary, "signals", []) or []:
        if getattr(one, "indicator", "") == BAND_INDICATOR and not one.abstained:
            return one
    return None


def band_position_of(signal: Any) -> float:
    """The ``BAND_POSITION_KEY`` reading one band signal published."""
    if signal is None:
        return MIDLINE_POSITION
    details = getattr(signal, "details", None) or {}
    found = details.get(BAND_POSITION_KEY)
    if found is None:
        return MIDLINE_POSITION
    return float(found)


def build_vote(symbol: Any, timeframe: Any, summary: VotingSummary) -> AssetVote:
    """One ``AssetVote`` from the ``VotingSummary`` the engine answered."""
    band = band_signal(summary)
    return AssetVote(
        symbol=str(symbol),
        timeframe=str(timeframe),
        direction=summary.consensus_direction,
        net_score=float(summary.net_score),
        confidence=float(summary.consensus_confidence),
        band_position=band_position_of(band),
        band_direction=(
            band.direction if band is not None else SignalDirection.NEUTRAL
        ),
        signals=list(summary.signals),
        bullish_count=int(summary.bullish_count),
        bearish_count=int(summary.bearish_count),
        neutral_count=int(summary.neutral_count),
        summary=summary,
    )


def candles_for(candle_source: Any, symbol: str, timeframe: str) -> list:
    """The candles one source holds for one symbol on one timeframe.

    A source that raises answers no candles, so the timeframe reads unread.
    """
    if candle_source is None:
        return []
    try:
        return list(candle_source(symbol, timeframe) or [])
    except Exception as exc:  # noqa: BLE001 - the source is host-supplied
        logger.debug(CANDLE_READ_FAILED_LOG, symbol, timeframe, exc)
        return []


def _listings_for(asset_source: Any, sector: Sector) -> list:
    """The asset rows one source holds for one sector.

    A source that raises answers none, so the sector reads its unwired note.
    """
    if asset_source is None:
        return []
    try:
        return list(asset_source(sector.name, sector.asset_class) or [])
    except Exception as exc:  # noqa: BLE001 - the source is host-supplied
        logger.debug(ASSET_READ_FAILED_LOG, sector.name, exc)
        return []


def symbol_of(listing: Any) -> str:
    """The symbol one asset row names, whether it is a row or a bare name."""
    return str(getattr(listing, "symbol", listing))


def is_listed(listing: Any) -> bool:
    """True while a row names a venue; a bare name states none and reads listed."""
    return bool(getattr(listing, "listed", True))


def serves(listing: Any, timeframe: Any) -> bool:
    """True while a row's venue answers ``timeframe``, or the row states none."""
    asked = getattr(listing, "serves", None)
    if asked is None:
        return True
    return bool(asked(timeframe))


def evaluate(
    sectors: Any,
    asset_source: Optional[Callable] = None,
    candle_source: Optional[Callable] = None,
    engine: Optional[VotingEngine] = None,
    clock: Optional[Callable] = None,
) -> list:
    """Phase one: scan every ``Sector`` on the timeframes ticked on it.

    Phase eight caps each sector at ``timeframes_supported`` of the ticked
    timeframes, measured from the ``RoundCost`` the rounds so far took.
    """
    voter = engine if engine is not None else VotingEngine()
    ticker = clock if clock is not None else time.perf_counter
    cost = RoundCost()
    scans: list = []
    for sector in list(sectors or []):
        rows = _listings_for(asset_source, sector)
        listed = [one for one in rows if is_listed(one)]
        assets = [symbol_of(one) for one in listed]
        ticked = sector.ticked()
        served = [one for one in ticked if any(serves(row, one) for row in listed)]
        scan = SectorScan(
            sector=sector.name,
            asset_class=sector.asset_class,
            assets=assets,
            unlisted=tuple(symbol_of(one) for one in rows if not is_listed(one)),
            unserved=(
                tuple(one for one in ticked if one not in served) if listed else ()
            ),
        )
        if not rows:
            scan.note = NO_ASSET_TEXT.format(asset_class=sector.asset_class)
        elif not listed:
            scan.note = UNLISTED_TEXT.format(
                symbols=SYMBOL_SEPARATOR.join(scan.unlisted)
            )
        elif not ticked:
            scan.note = NO_TIMEFRAME_TEXT
        for at, timeframe in enumerate(served):
            if len(scan.timeframes) >= timeframes_supported(
                cost.per_round_s, sector.asset_class
            ):
                scan.deferred = tuple(served[at:])
                break
            scan.timeframes.append(
                _scan_timeframe(voter, assets, timeframe, candle_source, cost, ticker)
            )
        scan.round_seconds = cost.per_round_s
        scans.append(scan)
    return scans


def _scan_timeframe(
    voter: VotingEngine,
    assets: list,
    timeframe: str,
    candle_source: Any,
    cost: RoundCost,
    clock: Callable,
) -> TimeframeScan:
    """One timeframe of one sector: a vote per asset the source can read.

    A history under ``MIN_CANDLES_TO_VOTE`` joins ``short`` instead of voting,
    and every asset read is one round ``cost`` takes the seconds of.
    """
    found = TimeframeScan(timeframe=timeframe)
    for symbol in assets:
        started = clock()
        candles = candles_for(candle_source, symbol, timeframe)
        if not candles:
            found.unread.append(symbol)
            cost.take(clock() - started)
            continue
        if len(candles) < MIN_CANDLES_TO_VOTE:
            found.short.append(symbol)
            cost.take(clock() - started)
            continue
        try:
            summary = voter.compute_all(candles, timeframe)
        except Exception as exc:  # noqa: BLE001 - one asset never stops a scan
            logger.debug(VOTE_FAILED_LOG, symbol, timeframe, exc)
            found.unread.append(symbol)
            cost.take(clock() - started)
            continue
        found.votes.append(build_vote(symbol, timeframe, summary))
        cost.take(clock() - started)
    return found


def agreement_for(scans: Any, vote: AssetVote) -> TimeframeAgreement:
    """Phase eight: every timeframe one call's asset voted on, and their verdict.

    A vote naming ``OPPOSITE_DIRECTION`` of the call contradicts it, and a
    ``SignalDirection.NEUTRAL`` vote is neither.
    """
    rows: list = []
    against: list = []
    opposite = OPPOSITE_DIRECTION.get(vote.direction)
    for scan in list(scans or []):
        for one in scan.timeframes:
            for held in one.votes:
                if held.symbol != vote.symbol:
                    continue
                label = timeframe_label(held.timeframe)
                rows.append((label, held.direction_text))
                if opposite is not None and held.direction == opposite:
                    against.append(label)
    return TimeframeAgreement(
        symbol=vote.symbol,
        direction=vote.direction,
        rows=tuple(rows),
        against=tuple(against),
    )


def midline_after(candles: Any, at: Any) -> list:
    """The Bollinger middle band at every candle after index ``at``.

    ``BollingerBands`` computes its published band on each window, so the
    target phase seven measures against moves with the market.
    """
    band = BollingerBands()
    held = list(candles or [])
    found: list = []
    for index in range(int(at) + 1, len(held)):
        signal = band.compute(held[: index + 1])
        details = getattr(signal, "details", None) or {}
        found.append(float(details.get(BAND_MIDDLE_KEY, NO_BAND_VALUE)))
    return found


def identify(scans: Any) -> list:
    """Phase two: every vote one run cast, strongest consensus first.

    ``run`` judges each one on its ``ata_gate_scan.GateScan``, and
    ``SectorScan.calls`` keeps the ``AssetVote.is_reversal`` rows for the
    sector readback.
    """
    votes: list = []
    for scan in list(scans or []):
        votes.extend(scan.votes)
    votes.sort(key=lambda one: -abs(one.net_score))
    return votes


def confirming_signals(vote: AssetVote) -> list:
    """The voters that read the chart and voted the call's own direction."""
    return [
        one
        for one in vote.signals
        if not one.abstained and one.direction == vote.direction
    ]


def reading_values(details: Any, keys: Any) -> Optional[dict]:
    """Every reading in ``keys`` one voter published, or None while one is missing.

    A key ``READING_WORDS`` names prints as one of its two words, so a
    boolean reading reads as the fact it carries.
    """
    found: dict = {}
    for key in keys:
        held = details.get(key)
        if held is None:
            return None
        words = READING_WORDS.get(key)
        found[key] = held if words is None else words[0 if held else 1]
    return found


def indicator_message(
    signal: Any, message_format: Optional[str] = None
) -> IndicatorMessage:
    """One confirming voter as its standardised sentence.

    ``message_format`` is the wording the ATA-SPM settings page sets, and
    ``MESSAGE_FORMAT`` is what an unset page leaves.
    """
    name = str(getattr(signal, "indicator", ""))
    label, keys, reading_format = READINGS.get(name, (name, (), ""))
    details = getattr(signal, "details", None) or {}
    values = reading_values(details, keys)
    reading = (
        reading_format.format(value=values[keys[0]], **values)
        if reading_format and values
        else NO_READING_TEXT
    )
    written = message_format or MESSAGE_FORMAT
    return IndicatorMessage(
        indicator=name,
        label=label,
        message=written.format(
            label=label,
            reading=reading,
            direction=direction_name(signal.direction),
            confidence=confidence_pct(signal.confidence),
        ),
    )


def panel_rows_for(scans: Any, symbol: Any) -> dict:
    """Every timeframe one asset voted on, as Indicator Voting Panel rows.

    The panel ATA-SMP carries reads only these rows, which come off the
    markets ATA-SMP scanned.
    """
    found: dict = {}
    for scan in list(scans or []):
        for one in scan.votes:
            if one.symbol == str(symbol):
                found[one.timeframe] = one.panel_row()
    for timeframe, row in found.items():
        row["composite_net"] = ata_gate_scan.composite_net(
            found, timeframe, row["net_score"]
        )
    return found


def proximity_of(candles: Any, settings: Any) -> Any:
    """The ``detect_bb_proximity`` reading, which carries the landing strip.

    ``bb_tolerance_pct`` and ``bb_landing_strip_candles`` come off
    ``settings``, the same two ``ScrummingBot.tick`` passes.
    """
    held = list(candles or [])
    if len(held) < ata_gate_scan.MIN_CANDLES_FOR_TA:
        return None
    return detect_bb_proximity(
        held,
        tolerance_pct=settings.bb_tolerance_pct,
        consolidation_threshold=CONSOLIDATION_THRESHOLD,
        min_pattern_candles=settings.bb_landing_strip_candles,
    )


def chart_candles(candles: Any) -> list:
    """The pulled candles as ``native_chart.Candle`` rows, value for value.

    Only the timestamp field is renamed, and a source missing any OHLCV field
    answers no rows.
    """
    try:
        return [
            Candle(
                time=int(one.timestamp),
                open=float(one.open),
                high=float(one.high),
                low=float(one.low),
                close=float(one.close),
                volume=float(one.volume),
            )
            for one in candles or []
        ]
    except (AttributeError, TypeError, ValueError) as exc:
        logger.debug(CANDLE_SHAPE_LOG, exc)
        return []


def post_caption(vote: AssetVote) -> str:
    """The standardised message one call's chart image carries.

    ``ata_spm_push.compose`` writes the same header, headline and address a
    post's own caption carries, and it is imported here because that module
    reads this one.
    """
    from . import ata_spm_push

    headline = ata_spm_push.POST_HEADLINE_FORMAT.format(
        symbol=vote.symbol,
        label=timeframe_label(vote.timeframe),
        vote=ata_spm_push.vote_word(vote.direction_text),
    )
    return ata_spm_push.compose((headline,))


def render_pull_image(
    vote: AssetVote,
    candles: Any,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
    messages: Any = (),
) -> ChartImage:
    """The call's own chart drawn to a PNG under ``ata_post_paths``.

    The overlays are the voters ``confirming_signals`` answered capped by
    ``max_supporting_indicators``, ``direction`` and ``messages`` are the
    markup, and ``prune_post_images`` bounds the store once the PNG is written.
    """
    held = chart_candles(candles)
    stamp = int(held[-1].time) if held else NO_TIMESTAMP
    path = ata_post_paths.post_image_path(vote.symbol, vote.timeframe, stamp)
    image = render_chart_png(
        held,
        vote.symbol,
        timeframe_label(vote.timeframe),
        path,
        voters=[one.indicator for one in confirming_signals(vote)],
        max_overlays=int(max_supporting_indicators or NO_INDICATOR_CAP),
        direction=vote.direction_text,
        readings=[(one.indicator, one.message) for one in messages or ()],
        caption=post_caption(vote),
    )
    ata_post_paths.prune_post_images(path)
    return image


def pull(
    vote: AssetVote,
    candle_source: Optional[Callable] = None,
    message_format: Optional[str] = None,
    agreement: Optional[TimeframeAgreement] = None,
    rows: Optional[dict] = None,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> ChartPull:
    """Phase three: the chart the call was made on, with its messages.

    ``ata_gate_scan.scan_gates`` reads the live trade gates over the chart
    first, and ``render_pull_image`` draws the PNG the post carries only while
    that scan answers ``would_fire``. A refused market leaves ``image`` empty
    and writes no file.
    """
    candles = candles_for(candle_source, vote.symbol, vote.timeframe)
    band = band_signal(vote)
    details = getattr(band, "details", None) or {}
    settings = ata_gate_scan.scan_settings(vote.symbol)
    proximity = proximity_of(candles, settings)
    gates = ata_gate_scan.scan_gates(
        vote.symbol,
        vote.timeframe,
        candles,
        vote.summary,
        proximity,
        rows,
        settings,
    )
    messages = [
        indicator_message(one, message_format) for one in confirming_signals(vote)
    ]
    image = (
        render_pull_image(vote, candles, max_supporting_indicators, messages)
        if gates.would_fire
        else ChartImage()
    )
    return ChartPull(
        symbol=vote.symbol,
        timeframe=vote.timeframe,
        direction=vote.direction,
        bars=len(candles),
        first_ts=(
            float(getattr(candles[0], "timestamp", NO_TIMESTAMP))
            if candles
            else NO_TIMESTAMP
        ),
        last_ts=(
            float(getattr(candles[-1], "timestamp", NO_TIMESTAMP))
            if candles
            else NO_TIMESTAMP
        ),
        last_close=(
            float(getattr(candles[-1], "close", NO_BAND_VALUE))
            if candles
            else NO_BAND_VALUE
        ),
        band_upper=float(details.get(BAND_UPPER_KEY, NO_BAND_VALUE)),
        band_middle=float(details.get(BAND_MIDDLE_KEY, NO_BAND_VALUE)),
        band_lower=float(details.get(BAND_LOWER_KEY, NO_BAND_VALUE)),
        closes=tuple(float(getattr(one, "close", NO_BAND_VALUE)) for one in candles),
        agreement=agreement,
        messages=messages,
        landing_strip_side=str(getattr(proximity, "landing_strip_side", "") or ""),
        landing_strip_candles=int(
            getattr(proximity, "landing_strip_candles", NO_BARS) or NO_BARS
        ),
        otd_pct=minimum_opposing_trade_distance_pct(
            settings.scrumming_interval_pct, settings.trading_fee_pct
        ),
        gates=gates,
        panel=dict(rows or {}),
        image=image,
    )


def run(
    sectors: Any,
    asset_source: Optional[Callable] = None,
    candle_source: Optional[Callable] = None,
    engine: Optional[VotingEngine] = None,
    message_format: Optional[str] = None,
    clock: Optional[Callable] = None,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> AtaSpmRun:
    """Phases one, two, three and eight in order, as one ``AtaSpmRun``.

    ``ata_gate_scan.GateScan.would_fire`` is the one judgement: a vote it
    answers True for reaches ``calls`` and ``pulls``, and from there the
    bucket, and every other vote leaves its scan in ``refused``.
    """
    scans = evaluate(sectors, asset_source, candle_source, engine, clock)
    found = AtaSpmRun(scans=scans)
    for vote in identify(scans):
        held = pull(
            vote,
            candle_source,
            message_format,
            agreement_for(scans, vote),
            panel_rows_for(scans, vote.symbol),
            max_supporting_indicators,
        )
        if held.gates.would_fire:
            found.calls.append(vote)
            found.pulls.append(held)
        else:
            found.refused.append(held.gates)
    return found


#: The index ``SectorBoard.scan_now`` answers when it added no sector.
NO_NEW_SECTOR = -1


class SectorBoard:
    """The sectors the ATA-SPM zone holds, and the run its last scan left.

    Every host owning an ATA-SPM zone keeps one of these, so the sector
    field, the class box, the four check boxes and Scan Now behave alike.
    """

    def __init__(self) -> None:
        self.sectors: list = []
        self.text = ""
        self.asset_class = CLASS_CRYPTO
        self.timeframes: tuple = timeframes_for(CLASS_CRYPTO)
        self.run: Optional[AtaSpmRun] = None

    def sector_at(self, at: Any) -> Optional[Sector]:
        """The sector one zone index shows, or None while the board is empty."""
        if not self.sectors:
            return None
        held = max(0, min(int(at or 0), len(self.sectors) - 1))
        return self.sectors[held]

    def set_text(self, text: Any) -> None:
        """Take what the operator typed into the sector field."""
        self.text = str(text or "").strip()

    def set_class(self, at: Any, name: Any) -> bool:
        """Take the asset class named, and answer whether it was accepted.

        A class outside ``ASSET_CLASSES`` is refused, so no sector carries
        one with no timeframes behind it.
        """
        asked = str(name or "")
        if asked not in ASSET_CLASSES:
            return False
        self.asset_class = asked
        self.timeframes = timeframes_for(asked)
        sector = self.sector_at(at)
        if sector is not None:
            sector.asset_class = asked
            sector.timeframes = timeframes_for(asked)
        return True

    def toggle_timeframe(self, at: Any, key: Any) -> bool:
        """Tick or untick one timeframe, and answer its state.

        The sector shown carries the tick, and while the board holds none
        ``timeframes`` carries it until ``compute`` gives it to the sector
        the next scan adds.
        """
        sector = self.sector_at(at)
        asked = str(key)
        asset_class = self.asset_class if sector is None else sector.asset_class
        held = set(self.timeframes if sector is None else sector.timeframes)
        if asked in held:
            held.discard(asked)
        else:
            held.add(asked)
        ticked = tuple(one for one in timeframes_for(asset_class) if one in held)
        if sector is None:
            self.timeframes = ticked
        else:
            sector.timeframes = ticked
        return asked in held

    def boxes(self, at: Any) -> list:
        """The four check rows of the sector shown, or of the next scan's sector."""
        sector = self.sector_at(at)
        if sector is not None:
            return sector.boxes()
        held = {str(one) for one in self.timeframes}
        return [
            [one, timeframe_label(one), one in held]
            for one in timeframes_for(self.asset_class)
        ]

    def compute(
        self,
        asset_source: Optional[Callable] = None,
        candle_source: Optional[Callable] = None,
        message_format: Optional[str] = None,
        max_supporting_indicators: Any = NO_INDICATOR_CAP,
    ) -> tuple:
        """The sectors this press holds, the index it added and the ``run``.

        Nothing on the board is written; a worker thread calls this and
        the drawing thread hands the answer to ``take``.
        """
        sectors = list(self.sectors)
        added = NO_NEW_SECTOR
        named = self.text
        if named and not any(one.name == named for one in sectors):
            sectors.append(
                Sector(
                    name=named,
                    asset_class=self.asset_class,
                    timeframes=self.timeframes,
                )
            )
            added = len(sectors) - 1
        found = (
            run(
                sectors,
                asset_source,
                candle_source,
                message_format=message_format,
                max_supporting_indicators=max_supporting_indicators,
            )
            if sectors
            else None
        )
        return (sectors, added, found)

    def take(self, sectors: Any, added: Any, found: Any) -> int:
        """Write what ``compute`` answered onto the board, and answer ``added``."""
        self.sectors = list(sectors)
        if found is not None:
            self.run = found
        return int(added)

    def scan_now(
        self,
        asset_source: Optional[Callable] = None,
        candle_source: Optional[Callable] = None,
        message_format: Optional[str] = None,
        max_supporting_indicators: Any = NO_INDICATOR_CAP,
    ) -> int:
        """``compute`` and ``take`` on one thread, answering the sector index.

        ``NO_NEW_SECTOR`` answers that the field named nothing new.
        """
        sectors, added, found = self.compute(
            asset_source, candle_source, message_format, max_supporting_indicators
        )
        return self.take(sectors, added, found)

    def report(self) -> dict:
        """The run report the ATA-SPM zone's line reads, empty before a scan."""
        if self.run is None:
            return {}
        return dict(self.run.report())

    def entries(self, entry_builder: Callable) -> list:
        """One zone entry per sector the last run scanned."""
        if self.run is None:
            return []
        return [entry_builder(one, self.run.pulls) for one in self.run.scans]
