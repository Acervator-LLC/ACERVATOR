"""ata_spm_push.py -- the ATA-SPM run, phases four, five and six.

``format_post`` writes one ``FormattedPost`` per ``PushTarget`` from the
``ata_spm.ChartPull`` phase three produced. ``distribute`` hands those to a
host-supplied sender and answers one ``DeliveryRecord`` each, sent or
failed. ``ReadyToSend`` is the bucket the operator approves from, and
``AtaSpmSettings`` carries the configuration those three read.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import ata_spm

logger = logging.getLogger("acervator.ata_spm_push")

#: Ships on every artefact ``FormattedPost`` composes. No caller supplies it
#: and no caller can remove it.
FIXED_HEADER = (
    "This is not investment advice. It is a demonstration of Ekthelius's "
    "proprietary TA engine housed in the Acervator governance execution "
    "platform."
)

TARGET_TRADINGVIEW = "TradingView"
TARGET_X = "X"
TARGET_INSTAGRAM = "Instagram"
TARGET_LINKEDIN = "LinkedIn"

SECTION_CALL = "call"
SECTION_CHART = "chart"
SECTION_BANDS = "bands"
SECTION_INDICATORS = "indicators"

ARTEFACT_BODY = "body"
ARTEFACT_CAPTION = "caption"
ARTEFACT_THREAD_ROOT = "thread_root"

#: The three artefacts of one post, each composed with ``FIXED_HEADER``.
ARTEFACT_KEYS = (ARTEFACT_BODY, ARTEFACT_CAPTION, ARTEFACT_THREAD_ROOT)

VOTE_BULL = "bull"
VOTE_BEAR = "bear"
VOTE_NEITHER = "neither"

VOTE_WORDS = {
    ata_spm.DIRECTION_BULLISH: VOTE_BULL,
    ata_spm.DIRECTION_BEARISH: VOTE_BEAR,
}

PHASE_FORMAT_NAME = "Phase 4 Format"
PHASE_DISTRIBUTE_NAME = "Phase 5 Distribute"
PHASE_BUCKET_NAME = "Phase 6 Ready to Send"

POST_HEADLINE_FORMAT = "{symbol} {label} · {vote}"
POST_LINE_SEPARATOR = "\n"

CHART_SECTION_FORMAT = "Chart: {bars} candles, last close {close:g}"
BANDS_SECTION_FORMAT = "Bands: lower {lower:g} · middle {middle:g} · upper {upper:g}"
CALL_SECTION_FORMAT = "{symbol} on {label}: {direction} reversal called."


@dataclass(frozen=True)
class PushTarget:
    """One push target, and the evidence sections its body carries in order."""

    name: str
    sections: tuple = ()


#: Adding a target is adding a row here. ``format_post``, ``distribute`` and
#: ``ReadyToSend`` read the row and change for none of them.
PUSH_TARGETS = (
    PushTarget(
        TARGET_TRADINGVIEW,
        (SECTION_CALL, SECTION_CHART, SECTION_BANDS, SECTION_INDICATORS),
    ),
    PushTarget(TARGET_X, (SECTION_CALL, SECTION_INDICATORS)),
    PushTarget(TARGET_INSTAGRAM, (SECTION_CALL, SECTION_BANDS, SECTION_INDICATORS)),
    PushTarget(TARGET_LINKEDIN, (SECTION_CALL, SECTION_CHART, SECTION_INDICATORS)),
)

TARGET_NAMES = tuple(one.name for one in PUSH_TARGETS)

STATE_WAITING = "waiting"
STATE_APPROVED = "approved"
STATE_DECLINED = "declined"

STATE_WORDS = (STATE_WAITING, STATE_APPROVED, STATE_DECLINED)

#: A ceiling of zero releases nothing. The operator sets one on the settings
#: page before any post leaves.
NO_CEILING_SET = 0

#: A cap of zero draws every confirming indicator phase three explained.
NO_INDICATOR_CAP = 0

SECONDS_PER_HOUR = 3600

NO_CREDENTIAL_TEXT = "No credential held for {target}."
NO_SENDER_TEXT = "No sender wired for {target}."
NO_CEILING_TEXT = "Max posts per hour is unset. Nothing leaves."
RATE_HELD_TEXT = "{sent} post(s) sent this hour, ceiling {ceiling}."
DECLINED_TEXT = "Declined. Not sent."
SEND_FAILED_TEXT = "{target} refused the post: {error}"
NO_DESTINATION_TEXT = ""

DELIVERY_SENT_FORMAT = "{target} · {symbol} {label} · sent to {destination}"
DELIVERY_FAILED_FORMAT = "{target} · {symbol} {label} · not sent · {detail}"

BUCKET_EMPTY_TEXT = "No post formatted. Scan a sector first."
BUCKET_HOLDS_FORMAT = (
    "{total} post(s) · {approved} approved · {declined} declined · {waiting} waiting"
)
BUCKET_META_FORMAT = "{target} · {state}"
FULL_AUTO_ON_TEXT = "Full Auto on"
FULL_AUTO_OFF_TEXT = "Full Auto off"

#: The two values ``CredentialVault.store`` takes for one push target, in the
#: order ``save_credentials`` reads them.
CREDENTIAL_FIELD_KEYS = ("credential-key", "credential-signature")

CREDENTIAL_HELD_TEXT = "held"
CREDENTIAL_MISSING_TEXT = "not held"
NO_VAULT_TEXT = "Credential vault not wired."

SEND_FAILED_LOG = "ATA-SPM send failed on %s %s: %s"
VAULT_READ_FAILED_LOG = "ATA-SPM credential read failed on %s: %s"
VAULT_STORE_FAILED_LOG = "ATA-SPM credential store failed on %s: %s"


def vote_word(direction_text: Any) -> str:
    """One direction word as the bull or bear the bucket line prints."""
    return VOTE_WORDS.get(str(direction_text), VOTE_NEITHER)


def _call_lines(vote: Any, pull: Any, cap: Any) -> list:
    """The call section: the asset, its timeframe and the direction voted."""
    del pull, cap
    return [
        CALL_SECTION_FORMAT.format(
            symbol=vote.symbol,
            label=ata_spm.timeframe_label(vote.timeframe),
            direction=vote.direction_text,
        )
    ]


def _chart_lines(vote: Any, pull: Any, cap: Any) -> list:
    """The chart section: the candles pulled and the last close on them."""
    del vote, cap
    return [CHART_SECTION_FORMAT.format(bars=pull.bars, close=pull.last_close)]


def _band_lines(vote: Any, pull: Any, cap: Any) -> list:
    """The bands section: the three values the Bollinger voter published."""
    del vote, cap
    return [
        BANDS_SECTION_FORMAT.format(
            lower=pull.band_lower,
            middle=pull.band_middle,
            upper=pull.band_upper,
        )
    ]


def _message_lines(vote: Any, pull: Any, cap: Any) -> list:
    """The indicator section: each confirming message, capped by ``cap``."""
    del vote
    held = [one.message for one in pull.messages]
    limit = int(cap or NO_INDICATOR_CAP)
    if limit > NO_INDICATOR_CAP:
        return held[:limit]
    return held


SECTION_WRITERS = {
    SECTION_CALL: _call_lines,
    SECTION_CHART: _chart_lines,
    SECTION_BANDS: _band_lines,
    SECTION_INDICATORS: _message_lines,
}


@dataclass(frozen=True)
class FormattedPost:
    """One reversal call formatted for one push target.

    ``body``, ``caption`` and ``thread_root`` each compose ``FIXED_HEADER``
    with the lines, so no artefact of this post can omit the header.
    """

    target: str
    symbol: str
    timeframe: str
    vote: str
    band_position: float = ata_spm.MIDLINE_POSITION
    band_lower: float = ata_spm.NO_BAND_VALUE
    band_middle: float = ata_spm.NO_BAND_VALUE
    band_upper: float = ata_spm.NO_BAND_VALUE
    bars: int = ata_spm.NO_BARS
    last_close: float = ata_spm.NO_BAND_VALUE
    lines: tuple = ()

    @property
    def headline(self) -> str:
        """The ticker, its timeframe and whether the vote is bull or bear."""
        return POST_HEADLINE_FORMAT.format(
            symbol=self.symbol,
            label=ata_spm.timeframe_label(self.timeframe),
            vote=self.vote,
        )

    @property
    def body(self) -> str:
        """The post body: ``FIXED_HEADER`` over this target's own sections."""
        return POST_LINE_SEPARATOR.join((FIXED_HEADER,) + tuple(self.lines))

    @property
    def caption(self) -> str:
        """The image caption: ``FIXED_HEADER`` over the headline."""
        return POST_LINE_SEPARATOR.join((FIXED_HEADER, self.headline))

    @property
    def thread_root(self) -> str:
        """The thread root: ``FIXED_HEADER`` over the headline."""
        return POST_LINE_SEPARATOR.join((FIXED_HEADER, self.headline))

    def artefacts(self) -> dict:
        """Every artefact of this post, keyed by ``ARTEFACT_KEYS``."""
        written = (self.body, self.caption, self.thread_root)
        return dict(zip(ARTEFACT_KEYS, written))


def format_post(
    vote: Any,
    pull: Any,
    target: PushTarget,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> FormattedPost:
    """Phase four: one reversal call written for one push target.

    The sections come from ``target.sections`` and their wording from the
    evidence ``ata_spm.pull`` answered.
    """
    lines: list = []
    for name in target.sections:
        writer = SECTION_WRITERS.get(name)
        if writer is None:
            continue
        lines.extend(writer(vote, pull, max_supporting_indicators))
    return FormattedPost(
        target=target.name,
        symbol=vote.symbol,
        timeframe=vote.timeframe,
        vote=vote_word(vote.direction_text),
        band_position=float(vote.band_position),
        band_lower=pull.band_lower,
        band_middle=pull.band_middle,
        band_upper=pull.band_upper,
        bars=pull.bars,
        last_close=pull.last_close,
        lines=tuple(lines),
    )


def format_run(
    run: Any,
    targets: Any = PUSH_TARGETS,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> list:
    """Phase four over one ``ata_spm.AtaSpmRun``: every call, every target."""
    pulls = {(one.symbol, one.timeframe): one for one in getattr(run, "pulls", [])}
    posts: list = []
    for vote in getattr(run, "calls", []):
        pull = pulls.get((vote.symbol, vote.timeframe))
        if pull is None:
            continue
        posts.extend(
            format_post(vote, pull, one, max_supporting_indicators) for one in targets
        )
    return posts


@dataclass
class DeliveryRecord:
    """What phase five did with one post: where it went, or why it did not."""

    target: str
    symbol: str
    timeframe: str
    sent: bool = False
    destination: str = NO_DESTINATION_TEXT
    detail: str = ""

    @property
    def line(self) -> str:
        """This record as the one line the Ready to Send zone reads back."""
        label = ata_spm.timeframe_label(self.timeframe)
        if self.sent:
            return DELIVERY_SENT_FORMAT.format(
                target=self.target,
                symbol=self.symbol,
                label=label,
                destination=self.destination,
            )
        return DELIVERY_FAILED_FORMAT.format(
            target=self.target,
            symbol=self.symbol,
            label=label,
            detail=self.detail,
        )


class SendRate:
    """The posts sent inside the last hour, against the configured ceiling."""

    def __init__(self) -> None:
        self.sent_at: list = []

    def sent_within_hour(self, now: float) -> int:
        """How many of ``sent_at`` fall inside the hour ending at ``now``."""
        self.sent_at = [one for one in self.sent_at if now - one < SECONDS_PER_HOUR]
        return len(self.sent_at)

    def allows(self, now: float, ceiling: Any) -> bool:
        """Whether one more post fits under ``ceiling`` at ``now``."""
        limit = int(ceiling or NO_CEILING_SET)
        if limit <= NO_CEILING_SET:
            return False
        return self.sent_within_hour(now) < limit

    def record(self, now: float) -> None:
        """Take one send at ``now`` into ``sent_at``."""
        self.sent_at.append(float(now))

    def held_text(self, now: float, ceiling: Any) -> str:
        """Why ``allows`` refused: an unset ceiling, or one already reached."""
        limit = int(ceiling or NO_CEILING_SET)
        if limit <= NO_CEILING_SET:
            return NO_CEILING_TEXT
        return RATE_HELD_TEXT.format(sent=self.sent_within_hour(now), ceiling=limit)


class AtaSpmSettings:
    """The ATA-SPM settings page, carrying only what a phase reads.

    ``max_posts_per_hour`` is the ceiling ``SendRate`` obeys,
    ``message_format`` the wording phase three writes each indicator in, and
    ``max_supporting_indicators`` the cap phase four draws them under.
    """

    def __init__(self) -> None:
        self.max_posts_per_hour = NO_CEILING_SET
        self.max_supporting_indicators = NO_INDICATOR_CAP
        self.message_format = ata_spm.MESSAGE_FORMAT
        self.vault: Any = None
        self.typed: dict = {}

    def set_vault(self, vault: Any) -> None:
        """Take the credential vault every push target's token is held in."""
        self.vault = vault

    def set_credential_text(self, target: Any, field: Any, typed: Any) -> None:
        """Hold what one credential field carries until Save reads it.

        Nothing here reaches ``credential_rows``, so no view model or render
        carries a typed value.
        """
        self.typed.setdefault(str(target), {})[str(field)] = str(typed or "")

    def typed_credential(self, target: Any) -> list:
        """The two values one target's fields hold, in ``CREDENTIAL_FIELD_KEYS``."""
        held = self.typed.get(str(target), {})
        return [str(held.get(one, "")) for one in CREDENTIAL_FIELD_KEYS]

    def save_credentials(self) -> list:
        """Encrypt every typed credential into the vault and clear what was typed.

        Answers the targets whose credential landed.
        """
        stored = []
        for name in TARGET_NAMES:
            api_key, api_secret = self.typed_credential(name)
            if self.store_credential(name, api_key, api_secret):
                stored.append(name)
        self.typed = {}
        return stored

    def store_credential(self, target: Any, api_key: Any, api_secret: Any) -> bool:
        """Encrypt one target's credential into ``vault``, and answer whether it landed.

        A missing or refusing ``vault`` answers False, and the target then
        reads unreachable.
        """
        if self.vault is None or not str(api_key or ""):
            return False
        try:
            self.vault.store(str(target), str(api_key), str(api_secret or ""))
        except Exception as exc:  # noqa: BLE001 - the vault is host-supplied
            logger.debug(VAULT_STORE_FAILED_LOG, target, exc)
            return False
        return True

    def holds(self, target: Any) -> bool:
        """Whether ``vault`` holds a credential for one push target."""
        if self.vault is None:
            return False
        try:
            return bool(self.vault.has_exchange(str(target)))
        except Exception as exc:  # noqa: BLE001 - the vault is host-supplied
            logger.debug(VAULT_READ_FAILED_LOG, target, exc)
            return False

    def credential_row(self, target: Any) -> list:
        """One push target's name, whether a credential is held, and the wording.

        No token is published here, so no view model or render carries one.
        """
        held = self.holds(target)
        if held:
            return [str(target), True, CREDENTIAL_HELD_TEXT]
        if self.vault is None:
            return [str(target), False, NO_VAULT_TEXT]
        return [str(target), False, CREDENTIAL_MISSING_TEXT]

    def credential_rows(self) -> list:
        """One ``credential_row`` per name in ``TARGET_NAMES``."""
        return [self.credential_row(one) for one in TARGET_NAMES]


def deliver_one(
    post: FormattedPost,
    sender: Optional[Callable],
    settings: AtaSpmSettings,
    rate: SendRate,
    now: float,
) -> DeliveryRecord:
    """Phase five for one post: send it, or record why it did not go.

    Every refusal answers a ``DeliveryRecord`` naming the target, and no
    target is skipped silently.
    """
    record = DeliveryRecord(
        target=post.target, symbol=post.symbol, timeframe=post.timeframe
    )
    if not settings.holds(post.target):
        record.detail = NO_CREDENTIAL_TEXT.format(target=post.target)
        return record
    if sender is None:
        record.detail = NO_SENDER_TEXT.format(target=post.target)
        return record
    if not rate.allows(now, settings.max_posts_per_hour):
        record.detail = rate.held_text(now, settings.max_posts_per_hour)
        return record
    try:
        record.destination = str(sender(post))
    except Exception as exc:  # noqa: BLE001 - the sender is host-supplied
        logger.debug(SEND_FAILED_LOG, post.target, post.symbol, exc)
        record.detail = SEND_FAILED_TEXT.format(target=post.target, error=exc)
        return record
    record.sent = True
    rate.record(now)
    return record


def distribute(
    posts: Any,
    sender: Optional[Callable] = None,
    settings: Optional[AtaSpmSettings] = None,
    rate: Optional[SendRate] = None,
    clock: Optional[Callable] = None,
) -> list:
    """Phase five: send every post given, and answer one record for each.

    With no ``sender`` every post records the target it could not reach.
    """
    held = settings if settings is not None else AtaSpmSettings()
    counter = rate if rate is not None else SendRate()
    now = float(clock() if clock is not None else 0.0)
    return [deliver_one(one, sender, held, counter, now) for one in list(posts or [])]


@dataclass
class BucketPost:
    """One formatted post waiting in Ready to Send, and its approval state."""

    post: FormattedPost
    state: str = STATE_WAITING

    @property
    def meta(self) -> str:
        """The target this post is for, and whether it is approved."""
        return BUCKET_META_FORMAT.format(target=self.post.target, state=self.state)


class ReadyToSend:
    """Phase six: the bucket the operator approves from before phase five.

    ``post_selected`` sends the post on screen, ``post_all`` every approved
    post, and ``release`` the same while ``full_auto`` is on.
    """

    def __init__(self) -> None:
        self.posts: list[BucketPost] = []
        self.full_auto = False
        self.rate = SendRate()
        self.records: list = []

    def load_run(
        self,
        run: Any,
        settings: Optional[AtaSpmSettings] = None,
        targets: Any = PUSH_TARGETS,
    ) -> int:
        """Run ``format_run`` over ``run`` and hold every post it wrote.

        Answers how many posts the bucket now carries.
        """
        cap = (
            settings.max_supporting_indicators
            if settings is not None
            else NO_INDICATOR_CAP
        )
        self.posts = [BucketPost(post=one) for one in format_run(run, targets, cap)]
        return len(self.posts)

    def at(self, index: Any) -> Optional[BucketPost]:
        """The bucket post one zone index shows, or None while it holds none."""
        if not self.posts:
            return None
        held = max(0, min(int(index or 0), len(self.posts) - 1))
        return self.posts[held]

    def approve(self, index: Any) -> str:
        """Approve the post one zone index shows and answer its state."""
        return self._set_state(index, STATE_APPROVED)

    def decline(self, index: Any) -> str:
        """Decline the post one zone index shows and answer its state."""
        return self._set_state(index, STATE_DECLINED)

    def _set_state(self, index: Any, state: str) -> str:
        held = self.at(index)
        if held is None:
            return STATE_WAITING
        held.state = state
        return held.state

    def approved(self) -> list:
        """Every post in the bucket the operator approved."""
        return [one for one in self.posts if one.state == STATE_APPROVED]

    def counts(self) -> dict:
        """How many posts the bucket holds in each of ``STATE_WORDS``."""
        return {
            one: len([held for held in self.posts if held.state == one])
            for one in STATE_WORDS
        }

    def summary(self) -> str:
        """The Ready to Send zone's own line: the bucket and its states."""
        if not self.posts:
            return BUCKET_EMPTY_TEXT
        counts = self.counts()
        return BUCKET_HOLDS_FORMAT.format(
            total=len(self.posts),
            approved=counts[STATE_APPROVED],
            declined=counts[STATE_DECLINED],
            waiting=counts[STATE_WAITING],
        )

    def toggle_full_auto(self) -> bool:
        """Turn Send Bucket Full Auto on or off and answer its state."""
        self.full_auto = not self.full_auto
        return self.full_auto

    def full_auto_text(self) -> str:
        """Whether Send Bucket Full Auto is on, as the button reads."""
        return FULL_AUTO_ON_TEXT if self.full_auto else FULL_AUTO_OFF_TEXT

    def post_selected(
        self,
        index: Any,
        sender: Optional[Callable] = None,
        settings: Optional[AtaSpmSettings] = None,
        clock: Optional[Callable] = None,
    ) -> list:
        """Send the post on screen, and answer the records phase five wrote.

        A ``STATE_DECLINED`` post is never sent and records ``DECLINED_TEXT``.
        """
        held = self.at(index)
        if held is None:
            return []
        if held.state == STATE_DECLINED:
            return self._hold_declined([held])
        return self._send([held], sender, settings, clock)

    def post_all(
        self,
        sender: Optional[Callable] = None,
        settings: Optional[AtaSpmSettings] = None,
        clock: Optional[Callable] = None,
    ) -> list:
        """Send every approved post, and answer the records phase five wrote."""
        return self._send(self.approved(), sender, settings, clock)

    def release(
        self,
        sender: Optional[Callable] = None,
        settings: Optional[AtaSpmSettings] = None,
        clock: Optional[Callable] = None,
    ) -> list:
        """Send every approved post while ``full_auto`` is on, and answer records."""
        if not self.full_auto:
            return []
        return self.post_all(sender, settings, clock)

    def _hold_declined(self, held: list) -> list:
        records = [
            DeliveryRecord(
                target=one.post.target,
                symbol=one.post.symbol,
                timeframe=one.post.timeframe,
                detail=DECLINED_TEXT,
            )
            for one in held
        ]
        self.records.extend(records)
        return records

    def _send(
        self,
        held: list,
        sender: Optional[Callable],
        settings: Optional[AtaSpmSettings],
        clock: Optional[Callable],
    ) -> list:
        records = distribute(
            [one.post for one in held], sender, settings, self.rate, clock
        )
        self.records.extend(records)
        return records

    def record_lines(self) -> list:
        """Every phase five record so far, as the lines the zone reads back."""
        return [one.line for one in self.records]


class PushBoard:
    """The Ready to Send bucket, the ATA-SPM settings, and the page shown.

    Every host owning the ATA-SPM zones keeps one of these, so the bucket,
    the four buttons and the settings page behave alike.
    """

    def __init__(self) -> None:
        self.settings = AtaSpmSettings()
        self.bucket = ReadyToSend()
        self.settings_open = False
        self.sender: Optional[Callable] = None
        self.clock: Optional[Callable] = None

    def set_sender(self, sender: Optional[Callable]) -> None:
        """Take what phase five sends through, or None to send nothing."""
        self.sender = sender

    def toggle_settings(self) -> bool:
        """Show the ATA-SPM settings page, or the scan page, and answer which."""
        self.settings_open = not self.settings_open
        return self.settings_open

    def load_run(self, run: Any) -> int:
        """Fill the bucket from one run and answer how many posts it holds."""
        return self.bucket.load_run(run, self.settings)

    def post_selected(self, index: Any) -> list:
        """Press Post Selected on the post one zone index shows."""
        return self.bucket.post_selected(index, self.sender, self.settings, self.clock)

    def post_all(self) -> list:
        """Press Post All over every approved post in the bucket."""
        return self.bucket.post_all(self.sender, self.settings, self.clock)

    def release(self) -> list:
        """Release the bucket while Send Bucket Full Auto is on."""
        return self.bucket.release(self.sender, self.settings, self.clock)

    def phase_report(self) -> dict:
        """What phases four, five and six each produced, for the zone lines."""
        return {
            PHASE_FORMAT_NAME: len(self.bucket.posts),
            PHASE_DISTRIBUTE_NAME: len(self.bucket.records),
            PHASE_BUCKET_NAME: self.bucket.summary(),
        }


@dataclass
class RecordedDestination:
    """A sender that keeps every artefact and reaches no platform.

    ``__call__`` answers the destination ``name`` phase five records, and
    ``artefacts`` holds what each post handed it.
    """

    name: str = "recorded"
    artefacts: list = field(default_factory=list)

    def __call__(self, post: FormattedPost) -> str:
        """Keep one post's artefacts and answer the destination recorded."""
        self.artefacts.append([post.target, post.symbol, post.artefacts()])
        return self.name
