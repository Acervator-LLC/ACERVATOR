"""ata_spm.py -- the ATA-SPM run, phases one to three.

``evaluate`` scans each ``Sector`` on its ticked timeframes and answers a
``SectorScan`` per sector. ``identify`` keeps the ``AssetVote`` rows
carrying a reversal, and ``pull`` loads that chart with the
``IndicatorMessage`` rows confirming it. ``VotingEngine`` produces every
direction and confidence, so this module computes no indicator maths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .indicators.types import (
    PERCENT_PER_RATIO_UNIT,
    Signal,
    SignalDirection,
    VotingSummary,
)
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
BAND_POSITION_KEY = "bb_position"
BAND_UPPER_KEY = "upper"
BAND_MIDDLE_KEY = "middle"
BAND_LOWER_KEY = "lower"

MIDLINE_POSITION = 0.5
NO_BAND_VALUE = 0.0
NO_BARS = 0
NO_TIMESTAMP = 0.0

#: One standardised message per confirming voter. The same condition reads
#: the same way in every run.
MESSAGE_FORMAT = "{label}: {reading}. Votes {direction} at {confidence}% confidence."
NO_READING_TEXT = "no reading published"

#: Each voter's screen name, the ``Signal.details`` key carrying its own
#: reading, and the wording that reading is printed in.
READINGS: dict[str, tuple[str, str, str]] = {
    "bollinger_bands": (
        "Bollinger Bands",
        BAND_POSITION_KEY,
        "band position {value:.4f}",
    ),
    "vortex": ("Vortex", "separation", "VI+ less VI- at {value:+.4f}"),
    "macd": ("MACD", "histogram", "histogram {value:+.6f}"),
    "stochastic_rsi": ("Stochastic RSI", "k", "%K at {value:.2f}"),
    "ichimoku": ("Ichimoku Cloud", "price_vs_cloud", "price {value} the cloud"),
    "volume": ("Volume", "mfi", "Money Flow Index {value:.1f}"),
    "slingshot": ("Slingshot", "momentum", "momentum {value:+.6f}"),
    "adx": ("ADX", "adx", "ADX {value:.2f}"),
    "supertrend": (
        "Supertrend",
        "dist_pct",
        "{value:+.3f}% from the Supertrend line",
    ),
    "zscore": ("Z-Score", "z", "z-score {value:+.3f}"),
    "kaufman_er": ("Kaufman Efficiency Ratio", "er", "efficiency ratio {value:.4f}"),
    "rsi": ("RSI", "rsi", "RSI {value:.2f}"),
}

PHASE_EVALUATE = "Phase 1 Evaluate"
PHASE_IDENTIFY = "Phase 2 Identify"
PHASE_PULL = "Phase 3 Pull"
PHASE_UNRUN = "No run yet"

SECTOR_LINE_FORMAT = "{sector} ({asset_class})"
SECTOR_META_FORMAT = "{assets} asset(s) · {votes} vote(s) · {calls} reversal call(s)"
TIMEFRAME_VOTE_FORMAT = "{votes} vote(s), {unread} without candles"
NO_TIMEFRAME_TEXT = "No timeframe ticked."
NO_ASSET_TEXT = "No asset source wired for {asset_class}."
CALL_LINE_FORMAT = "{symbol} on {label}: {direction} reversal"
CALL_META_FORMAT = (
    "{direction} reversal · net {net:+.4f} · confidence {confidence}% "
    "· band position {band:.4f}"
)
CHART_LINE_FORMAT = "{bars} candles, last close {close:g}"
BAND_LINE_FORMAT = "lower {lower:g} · middle {middle:g} · upper {upper:g}"

PHASE_RUN_FORMAT = "{phase}: {sectors} sector(s), {calls} call(s), {pulls} chart(s)"

CANDLE_READ_FAILED_LOG = "ATA-SPM candle read failed on %s %s: %s"
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
    """What one ticked timeframe of one sector returned."""

    timeframe: str
    votes: list = field(default_factory=list)
    unread: list = field(default_factory=list)

    @property
    def calls(self) -> list:
        """The votes on this timeframe carrying a reversal."""
        return [one for one in self.votes if one.is_reversal]


@dataclass
class SectorScan:
    """What one sector returned across every timeframe ticked on it."""

    sector: str
    asset_class: str = CLASS_CRYPTO
    assets: list = field(default_factory=list)
    timeframes: list = field(default_factory=list)
    note: str = ""

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
    """The chart one reversal call was made on, and its confirming messages."""

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
    messages: list = field(default_factory=list)


@dataclass
class AtaSpmRun:
    """One ATA-SPM run: what phases one, two and three each produced."""

    scans: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    pulls: list = field(default_factory=list)

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
    )


def _candles_for(candle_source: Any, symbol: str, timeframe: str) -> list:
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


def _assets_for(asset_source: Any, sector: Sector) -> list:
    """The assets one source holds for one sector.

    A source that raises answers none, so the sector reads its unwired note.
    """
    if asset_source is None:
        return []
    try:
        return [str(one) for one in asset_source(sector.name, sector.asset_class) or []]
    except Exception as exc:  # noqa: BLE001 - the source is host-supplied
        logger.debug(ASSET_READ_FAILED_LOG, sector.name, exc)
        return []


def evaluate(
    sectors: Any,
    asset_source: Optional[Callable] = None,
    candle_source: Optional[Callable] = None,
    engine: Optional[VotingEngine] = None,
) -> list:
    """Phase one: scan every ``Sector`` on the timeframes ticked on it.

    Answers one ``SectorScan`` per sector, carrying the assets scanned and
    what each ticked timeframe returned.
    """
    voter = engine if engine is not None else VotingEngine()
    scans: list = []
    for sector in list(sectors or []):
        assets = _assets_for(asset_source, sector)
        ticked = sector.ticked()
        scan = SectorScan(
            sector=sector.name,
            asset_class=sector.asset_class,
            assets=assets,
        )
        if not assets:
            scan.note = NO_ASSET_TEXT.format(asset_class=sector.asset_class)
        elif not ticked:
            scan.note = NO_TIMEFRAME_TEXT
        for timeframe in ticked:
            scan.timeframes.append(
                _scan_timeframe(voter, assets, timeframe, candle_source)
            )
        scans.append(scan)
    return scans


def _scan_timeframe(
    voter: VotingEngine,
    assets: list,
    timeframe: str,
    candle_source: Any,
) -> TimeframeScan:
    """One timeframe of one sector: a vote per asset the source can read."""
    found = TimeframeScan(timeframe=timeframe)
    for symbol in assets:
        candles = _candles_for(candle_source, symbol, timeframe)
        if not candles:
            found.unread.append(symbol)
            continue
        try:
            summary = voter.compute_all(candles, timeframe)
        except Exception as exc:  # noqa: BLE001 - one asset never stops a scan
            logger.debug(VOTE_FAILED_LOG, symbol, timeframe, exc)
            found.unread.append(symbol)
            continue
        found.votes.append(build_vote(symbol, timeframe, summary))
    return found


def identify(scans: Any) -> list:
    """Phase two: the votes carrying a reversal, strongest consensus first.

    A vote is a reversal when its band voter and its consensus name one
    direction, which ``AssetVote.is_reversal`` decides.
    """
    calls: list = []
    for scan in list(scans or []):
        calls.extend(scan.calls)
    calls.sort(key=lambda one: -abs(one.net_score))
    return calls


def confirming_signals(vote: AssetVote) -> list:
    """The voters that read the chart and voted the call's own direction."""
    return [
        one
        for one in vote.signals
        if not one.abstained and one.direction == vote.direction
    ]


def indicator_message(
    signal: Any, message_format: Optional[str] = None
) -> IndicatorMessage:
    """One confirming voter as its standardised sentence.

    ``message_format`` is the wording the ATA-SPM settings page sets, and
    ``MESSAGE_FORMAT`` is what an unset page leaves.
    """
    name = str(getattr(signal, "indicator", ""))
    label, key, reading_format = READINGS.get(name, (name, "", ""))
    details = getattr(signal, "details", None) or {}
    value = details.get(key) if key else None
    reading = (
        reading_format.format(value=value)
        if reading_format and value is not None
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


def pull(
    vote: AssetVote,
    candle_source: Optional[Callable] = None,
    message_format: Optional[str] = None,
) -> ChartPull:
    """Phase three: the chart the call was made on, with its messages.

    The band values come from the ``BAND_INDICATOR`` vote, and no price is
    recomputed here.
    """
    candles = _candles_for(candle_source, vote.symbol, vote.timeframe)
    band = band_signal(vote)
    details = getattr(band, "details", None) or {}
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
        messages=[
            indicator_message(one, message_format) for one in confirming_signals(vote)
        ],
    )


def run(
    sectors: Any,
    asset_source: Optional[Callable] = None,
    candle_source: Optional[Callable] = None,
    engine: Optional[VotingEngine] = None,
    message_format: Optional[str] = None,
) -> AtaSpmRun:
    """The three phases in order, answered as one ``AtaSpmRun``."""
    scans = evaluate(sectors, asset_source, candle_source, engine)
    calls = identify(scans)
    return AtaSpmRun(
        scans=scans,
        calls=calls,
        pulls=[pull(one, candle_source, message_format) for one in calls],
    )


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
        sector = self.sector_at(at)
        if sector is not None:
            sector.asset_class = asked
            sector.timeframes = timeframes_for(asked)
        return True

    def toggle_timeframe(self, at: Any, key: Any) -> bool:
        """Tick or untick one box on the sector shown, and answer its state."""
        sector = self.sector_at(at)
        if sector is None:
            return False
        asked = str(key)
        held = set(sector.timeframes)
        if asked in held:
            held.discard(asked)
        else:
            held.add(asked)
        sector.timeframes = tuple(
            one for one in timeframes_for(sector.asset_class) if one in held
        )
        return asked in held

    def boxes(self, at: Any) -> list:
        """The four check-box rows of the sector shown, or the class's own four."""
        sector = self.sector_at(at)
        if sector is not None:
            return sector.boxes()
        return [
            [one, timeframe_label(one), False]
            for one in timeframes_for(self.asset_class)
        ]

    def scan_now(
        self,
        asset_source: Optional[Callable] = None,
        candle_source: Optional[Callable] = None,
        message_format: Optional[str] = None,
    ) -> int:
        """Add the typed sector if it is new, run the phases, answer its index.

        Answers ``NO_NEW_SECTOR`` when the field named nothing new, so a
        host holding a zone index keeps the entry already on screen.
        """
        added = NO_NEW_SECTOR
        named = self.text
        if named and not any(one.name == named for one in self.sectors):
            self.sectors.append(
                Sector(
                    name=named,
                    asset_class=self.asset_class,
                    timeframes=timeframes_for(self.asset_class),
                )
            )
            added = len(self.sectors) - 1
        if self.sectors:
            self.run = run(
                self.sectors,
                asset_source,
                candle_source,
                message_format=message_format,
            )
        return added

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
