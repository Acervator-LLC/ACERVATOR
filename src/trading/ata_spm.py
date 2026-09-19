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

from ..core.signal_contract import emit as _pin_emit
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
CLASS_ENERGY = "energy"

#: Every major asset class that charts and takes TA.
ASSET_CLASSES = (
    CLASS_CRYPTO,
    CLASS_STOCKS,
    CLASS_METALS,
    CLASS_DERIVATIVES,
    CLASS_FOREX,
    CLASS_ENERGY,
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
MARKET_LINE_FORMAT = "{ticker} in {asset_class}"
MARKET_META_FORMAT = "1 market on {venue} · {votes} vote(s) · {hits} hit(s)"
#: One phase-one row per timeframe of a one-market scan: the candles read
#: and what the vote came to.
MARKET_TIMEFRAME_FORMAT = "{candles} candle(s) · {reading}"
#: What ``MARKET_META_FORMAT`` names for a market no configured venue lists.
NO_VENUE_NAME = "no venue"
MARKET_HIT_READING = "{direction} vote, hit"
MARKET_REFUSED_READING = "{direction} vote, refused by the gates"
MARKET_NO_VOTE_READING = "no vote"
VOLUME_LINE_FORMAT = "{asset_class} by volume"
MAP_ORDER_LINE_FORMAT = "{asset_class} in map order"
VOLUME_META_FORMAT = "{read} market(s) read · {hits} hit(s) · {stop}"
STOPPED_AT_TARGET_TEXT = "stopped at target"
SECTOR_EXHAUSTED_TEXT = "sector exhausted"
#: The order line a by-volume scan carries: what ordered the class, then the
#: markets read, first read first.
ORDER_LINE_FORMAT = "Order by {source}: {markets}"
ORDER_UNREAD_FORMAT = "{markets} ({unread} not read)"
ORDER_UNFIGURED_FORMAT = "{source}, {unfigured} with no figure last by name"
MAP_ORDER_SOURCE_TEXT = "map order, no volume figure"
UNSTATED_ORDER_SOURCE_TEXT = "the order the source listed"
NO_MARKET_TEXT = "none"

#: The pin ``_scan_until_hits`` writes at each hit, through ``_pin_emit``.
HIT_PIN = "inspector.ata.hit"
#: The pin ``SectorBoard.compute`` writes once per press with text in the
#: field: the market the text named and its class, or the refusal.
TICKER_RESOLVED_PIN = "inspector.ata.ticker_resolved"

#: The hits an empty-field scan stops at until the operator sets a count.
DEFAULT_HITS_PER_SCAN = 3
#: A ``Sector`` carrying this reads its whole list and stops at no count.
NO_HIT_TARGET = 0
NO_MARKETS_READ = 0
TIMEFRAME_VOTE_FORMAT = (
    "{votes} vote(s), {unread} without candles, {short} under {floor} candles"
)
NO_TIMEFRAME_TEXT = "No timeframe ticked."
NO_ASSET_TEXT = "No asset source wired for {asset_class}."
TICKER_UNHELD_FORMAT = "No class lists ticker {ticker}. Pick one the field offers."
CLASS_MOVED_TEXT = (
    "ATA-SPM ticker {ticker} is listed under {placed}; the class box moves "
    "from {chosen} to {placed}"
)
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
PHASE_MARKET_FORMAT = (
    "{phase}: {markets} market(s), {calls} call(s), {pulls} chart(s), "
    "{refused} refused by the gates"
)
PHASE_BOTH_FORMAT = (
    "{phase}: {sectors} sector(s), {markets} market(s), {calls} call(s), "
    "{pulls} chart(s), {refused} refused by the gates"
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
MARKET_READ_FAILED_LOG = "ATA-SPM market read failed on %s: %s"
CLASS_READ_FAILED_LOG = "ATA-SPM market list read failed on %s: %s"
CANDLE_SHAPE_LOG = "ATA-SPM candle row is not OHLCV: %s"
ASSET_READ_FAILED_LOG = "ATA-SPM asset read failed on %s: %s"
VOTE_FAILED_LOG = "ATA-SPM vote failed on %s %s: %s"

#: The lines one Scan Now press writes, in the order its phases run.
SCAN_PRESSED_TEXT = (
    "ATA-SPM scan pressed: {asset_class} on {timeframes}, ticker '{ticker}', "
    "target {hits} hit(s)"
)
SCAN_BUSY_TEXT = "ATA-SPM scan pressed while a scan is running; press ignored"
NO_TIMEFRAME_LIST_TEXT = "no timeframe"
TIMEFRAME_LIST_JOIN = " "
MARKET_READ_TEXT = "ATA-SPM read {symbol} on {label} from {venue}: {candles} candle(s)"
MARKET_EMPTY_TEXT = "ATA-SPM read {symbol} on {label} from {venue}: no candles"
MARKET_REFUSED_TEXT = "ATA-SPM read {symbol} on {label} from {venue}: refused, {reason}"
HIT_TEXT = "ATA-SPM hit: {call}"
SCAN_FINISHED_TEXT = "ATA-SPM scan finished: {headline} · {meta}. {method}"
SCAN_NOTE_TEXT = "ATA-SPM scan finished: {note}"
SCAN_EMPTY_TEXT = "ATA-SPM scan finished: no sector to scan"
SCAN_FAILED_TEXT = "ATA-SPM scan failed: {error}"


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


def hits_target(asked: Any) -> int:
    """The hits one empty-field scan stops at.

    Text that is not a whole number, and any count under 1, read as
    ``DEFAULT_HITS_PER_SCAN``.
    """
    try:
        held = int(str(asked).strip())
    except (TypeError, ValueError):
        return DEFAULT_HITS_PER_SCAN
    if held < 1:
        return DEFAULT_HITS_PER_SCAN
    return held


@dataclass
class MarketOrder:
    """One class's rows in the order a by-volume scan walks them.

    ``source`` names what ordered ``listings``; ``figures`` holds each
    symbol's volume figure and ``unfigured`` counts the rows that had none.
    """

    listings: list = field(default_factory=list)
    source: str = UNSTATED_ORDER_SOURCE_TEXT
    figures: dict = field(default_factory=dict)
    unfigured: int = 0

    @property
    def by_volume(self) -> bool:
        """True while at least one row was ranked by a figure."""
        return bool(self.figures)

    @property
    def symbols(self) -> list:
        """Each row's symbol, first walked first."""
        return [symbol_of(one) for one in self.listings]

    @property
    def source_line(self) -> str:
        """``source``, with ``ORDER_UNFIGURED_FORMAT`` while rows had no figure."""
        if self.by_volume and self.unfigured:
            return ORDER_UNFIGURED_FORMAT.format(
                source=self.source, unfigured=self.unfigured
            )
        return self.source


@dataclass
class TickerPlacement:
    """One typed ticker placed: the row read and the class that lists it.

    ``typed`` is the text as the operator wrote it; ``symbol`` is the name
    the class lists it under, which the scan and the zone carry.
    """

    listing: Any
    asset_class: str
    typed: str = ""

    @property
    def symbol(self) -> str:
        """The symbol ``listing`` names."""
        return symbol_of(self.listing)

    @property
    def venue(self) -> str:
        """The venue ``listing`` names, empty for a row no venue lists."""
        return str(getattr(self.listing, "venue", "") or "")


def order_line(order: MarketOrder, read: Any) -> str:
    """``ORDER_LINE_FORMAT`` over the first ``read`` symbols of ``order``.

    The symbols after ``read`` are counted into ``ORDER_UNREAD_FORMAT``.
    """
    symbols = order.symbols
    held = max(0, int(read or 0))
    named = SYMBOL_SEPARATOR.join(symbols[:held]) or NO_MARKET_TEXT
    if len(symbols) > held:
        named = ORDER_UNREAD_FORMAT.format(markets=named, unread=len(symbols) - held)
    return ORDER_LINE_FORMAT.format(source=order.source_line, markets=named)


@dataclass
class Sector:
    """One scan the ATA-SPM zone holds, and the timeframes ticked on it.

    ``ticker`` names one market inside the sector and ``listings`` holds that
    market's own row, so ``_listings_for`` reads one market and asks no asset
    source; a ``hit_target`` above ``NO_HIT_TARGET`` reads ``listings`` in
    ``order`` market by market and stops at that many hits.
    """

    name: str
    asset_class: str = CLASS_CRYPTO
    timeframes: tuple = ()
    ticker: str = ""
    listings: tuple = ()
    hit_target: int = NO_HIT_TARGET
    order: Optional[MarketOrder] = None

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
    ``MIN_CANDLES_TO_VOTE`` candles, which is reported and never voted;
    ``read`` holds the candle count each asset's read answered.
    """

    timeframe: str
    votes: list = field(default_factory=list)
    unread: list = field(default_factory=list)
    short: list = field(default_factory=list)
    read: dict = field(default_factory=dict)

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
    """What one scan returned across every timeframe ticked on it.

    A ``ticker`` says the scan read one market on ``venue``, which is what
    ``MARKET_LINE_FORMAT`` and ``MARKET_META_FORMAT`` are written for; a
    ``hit_target`` says it read ``markets_read`` markets in ``order``, which
    is what ``VOLUME_META_FORMAT`` and ``stopped_at_target`` are written for.
    ``judged`` says ``_scan_until_hits`` walked the scan, so ``hits`` holds
    the votes ``ata_gate_scan.GateScan.would_fire`` admitted out of the
    ``pulls`` it judged.
    """

    sector: str
    asset_class: str = CLASS_CRYPTO
    ticker: str = ""
    venue: str = ""
    assets: list = field(default_factory=list)
    timeframes: list = field(default_factory=list)
    note: str = ""
    round_seconds: float = NO_ROUND_MEASURED
    deferred: tuple = ()
    unlisted: tuple = ()
    unserved: tuple = ()
    hit_target: int = NO_HIT_TARGET
    markets_read: int = NO_MARKETS_READ
    stopped_at_target: bool = False
    order: MarketOrder = field(default_factory=MarketOrder)
    judged: bool = False
    hits: list = field(default_factory=list)
    pulls: list = field(default_factory=list)

    @property
    def by_volume(self) -> bool:
        """True while ``hit_target`` set the scan to walk ``order``."""
        return self.hit_target > NO_HIT_TARGET

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
        """A judged scan's ``hits``, or every vote carrying a reversal."""
        if self.judged:
            return list(self.hits)
        return [one for one in self.votes if one.is_reversal]

    def hit_on(self, timeframe: Any) -> Optional[AssetVote]:
        """The hit ``timeframe`` carries, or None while none fired there."""
        asked = str(timeframe)
        return next((one for one in self.hits if one.timeframe == asked), None)


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
    captions, and ``venue_posts`` holds what each push target's folder took.
    A call ``gates`` refused carries the default empty ``ChartImage``.
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
    venue_posts: dict = field(default_factory=dict)


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
        """The last phase this run reached, and what it produced.

        A scan carrying a ``SectorScan.ticker`` counts as a market and every
        other scan as a sector, so the line says which kind this run read.
        """
        if not self.scans:
            return PHASE_UNRUN
        reached = PHASE_EVALUATE
        if self.calls:
            reached = PHASE_IDENTIFY
        if self.pulls:
            reached = PHASE_PULL
        markets = sum(1 for one in self.scans if one.ticker)
        counts = {
            "phase": reached,
            "sectors": len(self.scans) - markets,
            "markets": markets,
            "calls": len(self.calls),
            "pulls": len(self.pulls),
            "refused": len(self.refused),
        }
        if not markets:
            return PHASE_RUN_FORMAT.format(**counts)
        if not counts["sectors"]:
            return PHASE_MARKET_FORMAT.format(**counts)
        return PHASE_BOTH_FORMAT.format(**counts)

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

    A ``Sector.listings`` naming one market, and a ``Sector.hit_target``, are
    answered from ``listings`` outright; a source that raises answers none, so
    the sector reads its unwired note.
    """
    if sector.listings or sector.hit_target > NO_HIT_TARGET:
        return list(sector.listings)
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


def market_of(
    market_source: Any, ticker: Any, asset_class: Any
) -> Optional[TickerPlacement]:
    """The ``TickerPlacement`` a typed ticker names, the chosen class first.

    A source answering a bare row is read as a row of ``asset_class``; a
    source that is None, and a source that raises, both answer None, which
    ``SectorBoard.compute`` reads as a ticker no class lists.
    """
    if market_source is None:
        return None
    try:
        placed = market_source(ticker, asset_class)
    except Exception as exc:  # noqa: BLE001 - the source is host-supplied
        logger.debug(MARKET_READ_FAILED_LOG, ticker, exc)
        return None
    if placed is None or isinstance(placed, TickerPlacement):
        return placed
    return TickerPlacement(
        listing=placed, asset_class=str(asset_class), typed=str(ticker or "")
    )


def markets_of(class_source: Any, asset_class: Any) -> MarketOrder:
    """Every asset row one class holds, as the ``MarketOrder`` the source ranked.

    A source answering a bare list carries ``UNSTATED_ORDER_SOURCE_TEXT``; a
    source that is None, and a source that raises, both answer no rows, so
    the scan reads ``NO_ASSET_TEXT``.
    """
    if class_source is None:
        return MarketOrder()
    try:
        answered = class_source(asset_class)
    except Exception as exc:  # noqa: BLE001 - the source is host-supplied
        logger.debug(CLASS_READ_FAILED_LOG, asset_class, exc)
        return MarketOrder()
    if isinstance(answered, MarketOrder):
        return answered
    return MarketOrder(listings=list(answered or []))


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
    message_format: Optional[str] = None,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> list:
    """Phase one: scan every ``Sector`` on the timeframes ticked on it.

    Phase eight caps each sector at ``timeframes_supported`` of the ticked
    timeframes, measured from the ``RoundCost`` the rounds so far took. A
    ``Sector.hit_target`` sector and a ``Sector.ticker`` market are walked
    by ``_scan_until_hits``, which judges each vote through ``pull`` as it
    goes; a market has no target, so every ticked timeframe is judged.
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
            ticker=sector.ticker,
            venue=str(getattr(rows[0], "venue", "") or "") if rows else "",
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
        if sector.hit_target > NO_HIT_TARGET or sector.ticker:
            scan.hit_target = int(sector.hit_target)
            scan.order = (
                sector.order
                if sector.order is not None
                else MarketOrder(listings=list(rows))
            )
            _scan_until_hits(
                voter,
                assets,
                served,
                candle_source,
                cost,
                ticker,
                scan,
                _gate_judge(candle_source, message_format, max_supporting_indicators),
            )
            scan.assets = assets[: scan.markets_read]
            scan.round_seconds = cost.per_round_s
            scans.append(scan)
            continue
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

    ``_vote_one`` reads each asset, so a history under ``MIN_CANDLES_TO_VOTE``
    joins ``short`` and every asset read is one round ``cost`` takes.
    """
    found = TimeframeScan(timeframe=timeframe)
    for symbol in assets:
        _vote_one(voter, symbol, timeframe, candle_source, cost, clock, found)
    return found


def _vote_one(
    voter: VotingEngine,
    symbol: str,
    timeframe: str,
    candle_source: Any,
    cost: RoundCost,
    clock: Callable,
    found: TimeframeScan,
) -> Optional[AssetVote]:
    """One asset on one timeframe: read, vote, and record the round on ``found``.

    Answers the ``AssetVote`` cast, or None when the asset joined ``unread``
    or ``short``.
    """
    started = clock()
    candles = candles_for(candle_source, symbol, timeframe)
    found.read[symbol] = len(candles)
    if not candles:
        found.unread.append(symbol)
        cost.take(clock() - started)
        return None
    if len(candles) < MIN_CANDLES_TO_VOTE:
        found.short.append(symbol)
        cost.take(clock() - started)
        return None
    try:
        summary = voter.compute_all(candles, timeframe)
    except Exception as exc:  # noqa: BLE001 - one asset never stops a scan
        logger.debug(VOTE_FAILED_LOG, symbol, timeframe, exc)
        found.unread.append(symbol)
        cost.take(clock() - started)
        return None
    vote = build_vote(symbol, timeframe, summary)
    found.votes.append(vote)
    cost.take(clock() - started)
    return vote


def _gate_judge(
    candle_source: Any,
    message_format: Optional[str],
    max_supporting_indicators: Any,
) -> Callable:
    """The callable ``_scan_until_hits`` judges one vote with: ``pull`` over
    the vote's own scan, so the gates read that market's other timeframes."""

    def judge(vote: AssetVote, scan: SectorScan) -> ChartPull:
        return pull(
            vote,
            candle_source,
            message_format,
            agreement_for([scan], vote),
            panel_rows_for([scan], vote.symbol),
            max_supporting_indicators,
        )

    return judge


def _scan_until_hits(
    voter: VotingEngine,
    assets: list,
    timeframes: list,
    candle_source: Any,
    cost: RoundCost,
    clock: Callable,
    scan: SectorScan,
    judge: Callable,
) -> None:
    """Market by market, every timeframe each, until ``scan.hit_target`` hits.

    Each market's votes are judged by ``judge`` in timeframe order after its
    last timeframe is read, a ``GateScan.would_fire`` verdict is one hit into
    ``scan.hits``, every ``ChartPull`` joins ``scan.pulls``, and the hit that
    reaches the target ends the walk with ``scan.stopped_at_target`` True. A
    target of ``NO_HIT_TARGET`` walks every market and stops at no count.
    """
    frames = [TimeframeScan(timeframe=one) for one in timeframes]
    scan.timeframes = frames
    scan.markets_read = NO_MARKETS_READ
    scan.stopped_at_target = False
    scan.judged = True
    if not frames:
        return
    for symbol in assets:
        scan.markets_read += 1
        votes = [
            vote
            for vote in (
                _vote_one(
                    voter, symbol, found.timeframe, candle_source, cost, clock, found
                )
                for found in frames
            )
            if vote is not None
        ]
        for vote in votes:
            held = judge(vote, scan)
            scan.pulls.append(held)
            if not held.gates.would_fire:
                continue
            scan.hits.append(vote)
            most = scan.hit_target if scan.by_volume else len(frames)
            _pin_emit(
                HIT_PIN,
                actual=len(scan.hits),
                expected=most,
                ok=len(scan.hits) <= most,
                context={
                    "asset_class": scan.asset_class,
                    "symbol": vote.symbol,
                    "timeframe": vote.timeframe,
                    "direction": vote.direction_text,
                    "firing_side": held.gates.firing_side,
                    "net_score": vote.net_score,
                    "confidence": vote.confidence,
                    "markets_read": scan.markets_read,
                },
            )
            if NO_HIT_TARGET < scan.hit_target <= len(scan.hits):
                scan.stopped_at_target = True
                return


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
    """The standardised message one call's root chart image carries.

    ``ata_spm_push.compose`` writes ``FIXED_HEADER``, the headline and the
    address; the root image serves every push target, so no row's own header
    reaches it. It is imported here because that module reads this one.
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
    first, and only while that scan answers ``would_fire`` does
    ``render_pull_image`` draw the PNG the post carries and
    ``ata_venue_folders.write_venue_posts`` fill each push target's folder
    from the same candles. A refused market leaves ``image`` and
    ``venue_posts`` empty and writes no file.
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
    held = ChartPull(
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
    )
    if gates.would_fire:
        from .ata_venue_folders import write_venue_posts

        held.image = render_pull_image(
            vote, candles, max_supporting_indicators, messages
        )
        held.venue_posts = write_venue_posts(
            vote, held, candles, max_supporting_indicators
        )
    return held


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
    bucket, and every other vote leaves its scan in ``refused``. A
    ``SectorScan.judged`` scan, by volume or one market, judged its own
    votes inside ``evaluate`` and hands over ``hits`` and ``pulls``; every
    other scan's votes are judged here.
    """
    scans = evaluate(
        sectors,
        asset_source,
        candle_source,
        engine,
        clock,
        message_format,
        max_supporting_indicators,
    )
    found = AtaSpmRun(scans=scans)
    for scan in scans:
        if not scan.judged:
            continue
        found.calls.extend(scan.hits)
        for held in scan.pulls:
            if held.gates.would_fire:
                found.pulls.append(held)
            else:
                found.refused.append(held.gates)
    for vote in identify([one for one in scans if not one.judged]):
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
        self.note = ""

    def sector_at(self, at: Any) -> Optional[Sector]:
        """The sector one zone index shows, or None while the board is empty."""
        if not self.sectors:
            return None
        held = max(0, min(int(at or 0), len(self.sectors) - 1))
        return self.sectors[held]

    def set_text(self, text: Any) -> None:
        """Take what the operator typed into the ticker field, clearing ``note``."""
        self.text = str(text or "").strip()
        self.note = ""

    def set_class(self, at: Any, name: Any) -> bool:
        """Take the asset class named, and answer whether it was accepted.

        A class outside ``ASSET_CLASSES`` is refused, so no sector carries
        one with no timeframes behind it. A placed market keeps the class
        that lists it; ``take`` moved the box to that class.
        """
        self.note = ""
        asked = str(name or "")
        if asked not in ASSET_CLASSES:
            return False
        self.asset_class = asked
        self.timeframes = timeframes_for(asked)
        sector = self.sector_at(at)
        if sector is not None and not sector.ticker:
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

    def ticked_at(self, at: Any) -> tuple:
        """The timeframes ticked on the sector one zone index shows.

        While the board holds none, ``timeframes`` carries them.
        """
        sector = self.sector_at(at)
        if sector is None:
            return tuple(self.timeframes)
        return tuple(sector.timeframes)

    def compute(
        self,
        asset_source: Optional[Callable] = None,
        candle_source: Optional[Callable] = None,
        message_format: Optional[str] = None,
        max_supporting_indicators: Any = NO_INDICATOR_CAP,
        market_source: Optional[Callable] = None,
        class_source: Optional[Callable] = None,
        hit_target: Any = DEFAULT_HITS_PER_SCAN,
        at: Any = 0,
    ) -> tuple:
        """The scans this press holds, the index to show, the ``run`` and a note.

        A ``self.text`` that ``market_of`` places scans that one market under
        the class the placement names, a ``self.text`` the ``asset_source``
        answers rows for scans that whole sector, anything else answers
        ``TICKER_UNHELD_FORMAT`` and runs nothing, and an empty ``self.text``
        scans what ``class_source`` lists for ``asset_class`` until
        ``hit_target`` hits; nothing on the board is written until ``take``.
        Each press with text writes ``TICKER_RESOLVED_PIN`` once.
        """
        sectors = list(self.sectors)
        added = NO_NEW_SECTOR
        named = self.text
        ticked = self.ticked_at(at)
        if named:
            placed = market_of(market_source, named, self.asset_class)
            if placed is not None:
                self._say_resolved(named, placed.asset_class, placed=placed)
                added = self._market_at(sectors, placed, ticked)
            elif self._sector_holds(asset_source, named):
                self._say_resolved(named, self.asset_class, sector=named)
                added = self._sector_at(sectors, named, ticked)
            else:
                note = TICKER_UNHELD_FORMAT.format(ticker=named)
                self._say_resolved(named, "", refusal=note)
                return (sectors, added, None, note)
        elif class_source is not None:
            order = markets_of(class_source, self.asset_class)
            added = self._volume_at(sectors, order, hits_target(hit_target), ticked)
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
        return (sectors, added, found, "")

    def _say_resolved(
        self,
        typed: str,
        landed: str,
        placed: Optional[TickerPlacement] = None,
        sector: str = "",
        refusal: str = "",
    ) -> None:
        """Write ``TICKER_RESOLVED_PIN``: ``landed`` is the class the text
        named, ``asset_class`` the one chosen, and ok says a market or a
        sector was named; a move reads ok with the two classes apart."""
        _pin_emit(
            TICKER_RESOLVED_PIN,
            actual=landed,
            expected=self.asset_class,
            ok=not refusal,
            context={
                "typed": typed,
                "symbol": placed.symbol if placed is not None else "",
                "asset_class": landed,
                "venue": placed.venue if placed is not None else "",
                "moved": bool(landed) and landed != self.asset_class,
                "sector": sector,
                "refusal": refusal,
            },
        )

    def _sector_holds(self, asset_source: Any, named: str) -> bool:
        """True while ``asset_source`` answers any row for ``named`` as a sector."""
        asked = Sector(name=named, asset_class=self.asset_class)
        return bool(_listings_for(asset_source, asked))

    def _sector_at(self, sectors: list, named: str, ticked: tuple) -> int:
        """The index one new sector took in ``sectors``, ``NO_NEW_SECTOR`` when held."""
        if any(one.name == named and not one.hit_target for one in sectors):
            return NO_NEW_SECTOR
        sectors.append(
            Sector(
                name=named,
                asset_class=self.asset_class,
                timeframes=ticked,
            )
        )
        return len(sectors) - 1

    def _market_at(self, sectors: list, placed: TickerPlacement, ticked: tuple) -> int:
        """The index of one placed market's scan in ``sectors``, appending it
        when new; the scan carries the class ``placed`` names and the ticks of
        ``ticked`` that class lists."""
        ticker = placed.symbol
        for at, one in enumerate(sectors):
            if one.ticker == ticker and one.asset_class == placed.asset_class:
                one.listings = (placed.listing,)
                return at
        held = {str(one) for one in ticked}
        sectors.append(
            Sector(
                name=ticker,
                asset_class=placed.asset_class,
                timeframes=tuple(
                    one for one in timeframes_for(placed.asset_class) if one in held
                ),
                ticker=ticker,
                listings=(placed.listing,),
            )
        )
        return len(sectors) - 1

    def _volume_at(
        self, sectors: list, order: MarketOrder, target: int, ticked: tuple
    ) -> int:
        """The index of ``asset_class``'s by-volume scan in ``sectors``.

        A held one takes ``order`` and ``target`` again, so a re-press reads
        the class's markets as they rank now; a new one is appended.
        """
        for at, one in enumerate(sectors):
            if one.hit_target > NO_HIT_TARGET and one.asset_class == self.asset_class:
                one.name = self.asset_class
                one.listings = tuple(order.listings)
                one.order = order
                one.hit_target = target
                return at
        sectors.append(
            Sector(
                name=self.asset_class,
                asset_class=self.asset_class,
                timeframes=ticked,
                listings=tuple(order.listings),
                hit_target=target,
                order=order,
            )
        )
        return len(sectors) - 1

    def take(self, sectors: Any, added: Any, found: Any, note: Any = "") -> int:
        """Write what ``compute`` answered onto the board, and answer ``added``.

        The class box follows the entry ``added`` names, so a placed market
        moves it to the class that lists the market.
        """
        self.sectors = list(sectors)
        self.note = str(note or "")
        if found is not None:
            self.run = found
        shown = int(added)
        if shown != NO_NEW_SECTOR and 0 <= shown < len(self.sectors):
            self.asset_class = self.sectors[shown].asset_class
            self.timeframes = tuple(self.sectors[shown].timeframes)
        return shown

    def scan_now(
        self,
        asset_source: Optional[Callable] = None,
        candle_source: Optional[Callable] = None,
        message_format: Optional[str] = None,
        max_supporting_indicators: Any = NO_INDICATOR_CAP,
        market_source: Optional[Callable] = None,
        class_source: Optional[Callable] = None,
        hit_target: Any = DEFAULT_HITS_PER_SCAN,
        at: Any = 0,
    ) -> int:
        """``compute`` and ``take`` on one thread, answering the index to show.

        ``NO_NEW_SECTOR`` answers that the field named nothing to scan.
        """
        sectors, added, found, note = self.compute(
            asset_source,
            candle_source,
            message_format,
            max_supporting_indicators,
            market_source,
            class_source,
            hit_target,
            at,
        )
        return self.take(sectors, added, found, note)

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
