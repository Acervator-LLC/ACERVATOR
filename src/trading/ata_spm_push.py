"""ata_spm_push.py -- the ATA-SPM run, phases four to seven.

``format_post`` writes one ``FormattedPost`` per ``PushTarget`` from the
``ata_spm.ChartPull`` phase three produced, and ``fit_to_target`` holds each
body under the ``body_limit`` that target publishes. ``distribute`` hands
those to a host-supplied sender and answers one ``DeliveryRecord`` each.
``ReadyToSend`` is the bucket the operator approves from, and
``FollowUpWatch`` is phase seven.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import ata_spm

logger = logging.getLogger("acervator.ata_spm_push")

#: The header a ``PushTarget`` row carries unless the row names its own.
FIXED_HEADER = (
    "This is not investment advice. It is a demonstration of Ekthelius's "
    "proprietary TA engine housed in the Acervator governance execution "
    "platform."
)

#: The header ``TARGET_X``'s row carries in place of ``FIXED_HEADER``.
X_HEADER = "Not investment advice. Acervator TA engine demonstration."

#: Ships under the lines on every artefact ``compose`` writes. ``fit_to_target``
#: drops evidence lines to reach a ceiling and never this.
ORGANIZATION_URL = "https://github.com/Acervator-LLC"

TARGET_X = "X"
TARGET_INSTAGRAM = "Instagram"
TARGET_LINKEDIN = "LinkedIn"
TARGET_TIKTOK = "TikTok"
TARGET_FACEBOOK = "Facebook"
TARGET_THREADS = "Threads"
TARGET_REDDIT = "Reddit"

SECTION_CALL = "call"
SECTION_CHART = "chart"
SECTION_BANDS = "bands"
SECTION_INDICATORS = "indicators"

ARTEFACT_BODY = "body"
ARTEFACT_CAPTION = "caption"
ARTEFACT_THREAD_ROOT = "thread_root"
ARTEFACT_TITLE = "title"

#: The PNG ``ata_spm.render_pull_image`` drew, which ``caption`` captions.
ARTEFACT_IMAGE = "image"

#: The three artefacts every post carries, each composed with the row's header.
ARTEFACT_KEYS = (ARTEFACT_BODY, ARTEFACT_CAPTION, ARTEFACT_THREAD_ROOT)

#: The unit each push target counts its text in, from the audit page.
COUNT_CHARACTERS = "characters"
COUNT_WEIGHTED = "weighted"
COUNT_UTF16_RUNES = "utf16-runes"
COUNT_UTF8_EMOJI = "utf8-emoji"

#: A target whose platform publishes no text ceiling. No number is guessed.
NO_LIMIT_PUBLISHED = 0

#: A target carrying no title field beside its body.
NO_TITLE_FIELD = 0

NO_DROPPED = 0

#: X wraps every URL with t.co and counts 23 whatever the real length.
X_URL_COST = 23

ASCII_WEIGHT = 1

#: Weight 1 covers Latin, punctuation and common symbols; weight 2 the rest.
NON_ASCII_WEIGHT = 2

URL_PREFIXES = ("http://", "https://")

UTF16_ENCODING = "utf-16-le"
UTF8_ENCODING = "utf-8"
BYTES_PER_RUNE = 2

WHITESPACE_RUN = re.compile(r"(\s+)")

#: The order ``fit_to_target`` drops a line in. ``KEEP_LINE`` never drops.
KEEP_LINE = None
DROP_FIRST = 0
DROP_LAST = 1

ABBREVIATED_FORMAT = "Abbreviated: {dropped} evidence line(s) omitted."
OVER_LIMIT_TEXT = "{target} publishes {limit}; this post measures {measured}."
TITLE_TOO_SMALL_FORMAT = (
    "{target} title holds {limit} and the header with the headline "
    "measures {measured}, so no artefact maps to it."
)

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
PHASE_FOLLOW_UP_NAME = "Phase 7 Follow-Up"

OUTCOME_CONFIRMED = "confirmed"
OUTCOME_FAILED = "failed"
OUTCOME_OPEN = "open"

#: A reversal call fails when the trend it called against carries on for
#: this many candles in a row. The floor is the definition, not a setting.
CONTINUATION_CANDLE_FLOOR = 3

#: A confirmation share of zero confirms nothing. The operator sets one on
#: the settings page before any call can confirm.
NO_SHARE_SET = 0

#: A Bollinger middle band of zero was never published; every close the
#: candle reader admits is above zero.
NO_MIDLINE = 0.0
NO_CONTINUATION = 0

FOLLOW_UP_HEAD_FORMAT = "Follow-up on {headline}: {state}."
FOLLOW_UP_CALL_FORMAT = "{symbol} on {label}: the {direction} reversal {state}."
FOLLOW_UP_EVIDENCE_FORMAT = "Evidence: {detail}."
FOLLOW_UP_LINE_FORMAT = "{headline} · {state} · {detail}"
FOLLOW_UP_CONFIRMED_FORMAT = (
    "close {close:g} reached {target:g}, {share}% of the run to midline "
    "{midline:g}, after {candles} candle(s)"
)
FOLLOW_UP_FAILED_FORMAT = (
    "the trend held for {run} candles in a row, last close {close:g}, "
    "after {candles} candle(s)"
)
FOLLOW_UP_OPEN_FORMAT = (
    "{candles} candle(s) since the call, last close {close:g}, "
    "target {target:g} not reached"
)
FOLLOW_UP_NOT_READY_FORMAT = (
    "the trend has held for {run} of the {floor} candles a failure needs, "
    "last close {close:g}, target {target:g} not reached"
)
FOLLOW_UP_NO_SHARE_FORMAT = (
    "{candles} candle(s) since the call, last close {close:g}. "
    "Confirmation share is unset, so nothing confirms"
)
FOLLOW_UP_NO_CANDLE_TEXT = "no candle has closed since the call"

POST_HEADLINE_FORMAT = "{symbol} {label} · {vote}"
POST_LINE_SEPARATOR = "\n"

CHART_SECTION_FORMAT = "Chart: {bars} candles, last close {close:g}"
BANDS_SECTION_FORMAT = "Bands: lower {lower:g} · middle {middle:g} · upper {upper:g}"
CALL_SECTION_FORMAT = "{symbol} on {label}: {direction} reversal called."


@dataclass(frozen=True)
class CredentialField:
    """One value a push target's sign-in needs, its part name and its empty wording."""

    key: str
    label: str


@dataclass(frozen=True)
class PushTarget:
    """One push target, its header, its sections, its text ceilings and its sign-in.

    ``fields`` is what the operator types and the Level 1A page draws a box
    for; ``issued`` is what the venue's own flow hands back, and no page draws
    one of those.
    """

    name: str
    sections: tuple = ()
    body_limit: int = NO_LIMIT_PUBLISHED
    title_limit: int = NO_TITLE_FIELD
    count_unit: str = COUNT_CHARACTERS
    header: str = FIXED_HEADER
    fields: tuple = ()
    issued: tuple = ()
    endpoint: str = ""
    scopes: tuple = ()
    registration: str = ""
    prerequisite: str = ""


#: A target is added by naming a row here; ``format_post``, ``distribute``
#: and ``ReadyToSend`` read the row rather than the name.
PUSH_TARGETS = (
    PushTarget(
        TARGET_X,
        (SECTION_CALL, SECTION_INDICATORS),
        body_limit=280,
        count_unit=COUNT_WEIGHTED,
        header=X_HEADER,
        fields=(
            CredentialField("x-client-id", "Client ID"),
            CredentialField("x-client-secret", "Client secret"),
        ),
        issued=(
            CredentialField("x-access-token", "Access token"),
            CredentialField("x-refresh-token", "Refresh token"),
        ),
        endpoint="https://api.x.com/2/tweets",
        scopes=(
            "tweet.write",
            "tweet.read",
            "users.read",
            "media.write",
            "offline.access",
        ),
        registration="An X developer app with OAuth 2.0 user authentication "
        "and a loopback callback address. Register the app at "
        "https://console.x.com.",
        prerequisite="X ended its free tier on 6 February 2026 and now bills "
        "per post, about $0.015 for a post and about $0.20 where the post "
        "carries a link. The app needs a paid usage plan before it can post.",
    ),
    PushTarget(
        TARGET_INSTAGRAM,
        (SECTION_CALL, SECTION_BANDS, SECTION_INDICATORS),
        body_limit=2200,
        fields=(
            CredentialField("instagram-client-id", "App ID"),
            CredentialField("instagram-client-secret", "App secret"),
        ),
        issued=(
            CredentialField("instagram-user-id", "Instagram user id"),
            CredentialField("instagram-access-token", "Access token"),
        ),
        endpoint="POST /<IG_ID>/media then /<IG_ID>/media_publish",
        scopes=("instagram_business_basic", "instagram_business_content_publish"),
        registration="A Meta app with Instagram Login, and an Instagram "
        "professional account. Register the app at "
        "developers.facebook.com/apps/creation/. Meta publishes no Business "
        "use case, so pick the Other use case, then the Business app type. "
        "Add the Instagram product. Open API setup with Instagram Login in "
        "the left menu: the App ID and App secret boxes above take the "
        "Instagram app ID and Instagram app secret printed on that panel, "
        "which are not the App ID and App secret on App settings then Basic. "
        "Add your account under Generate access tokens, then enter the "
        "redirect address under Business login settings, which is not in the "
        "main OAuth settings. This route needs no Facebook Page.",
        prerequisite="No App Review. Meta grants Standard Access to every "
        "permission automatically, and it covers any account holding a role "
        "on the app, so give your account a role on it. Page Publishing "
        "Authorization must be complete, and publishing is capped at 100 "
        "posts in a rolling 24 hours, 50 where the post is a carousel.",
    ),
    PushTarget(
        TARGET_LINKEDIN,
        (SECTION_CALL, SECTION_CHART, SECTION_INDICATORS),
        body_limit=3000,
        fields=(
            CredentialField("linkedin-client-id", "Client ID"),
            CredentialField("linkedin-version", "Linkedin-Version (YYYYMM)"),
        ),
        issued=(CredentialField("linkedin-access-token", "Access token"),),
        endpoint="https://api.linkedin.com/rest/posts",
        scopes=("w_member_social",),
        registration="A LinkedIn developer app carrying the Community "
        "Management API, with a loopback redirect address. Register the app "
        "at www.linkedin.com/developers/apps, then press Create app.",
        prerequisite="LinkedIn is the one venue that may refuse outright. The "
        "Community Management API needs a registered company, a verified Page "
        "and a two-tier review carrying a screencast. LinkedIn must also "
        "switch its native PKCE flow on for the app by hand. Until both are "
        "granted, Connect reaches LinkedIn and LinkedIn turns it away.",
    ),
    PushTarget(
        TARGET_TIKTOK,
        (SECTION_CALL, SECTION_CHART, SECTION_BANDS, SECTION_INDICATORS),
        body_limit=4000,
        title_limit=90,
        count_unit=COUNT_UTF16_RUNES,
        fields=(
            CredentialField("tiktok-client-key", "Client key"),
            CredentialField("tiktok-client-secret", "Client secret"),
            CredentialField("tiktok-url-prefix", "Verified URL prefix"),
        ),
        issued=(
            CredentialField("tiktok-open-id", "Open id"),
            CredentialField("tiktok-access-token", "Access token"),
            CredentialField("tiktok-refresh-token", "Refresh token"),
        ),
        endpoint="POST /v2/post/publish/content/init/",
        scopes=("user.info.basic", "video.publish"),
        registration="A TikTok developer app with Content Posting and Direct "
        "Post switched on, and a verified address prefix. Register the app at "
        "developers.tiktok.com/apps.",
        prerequisite="The app will be unaudited, and TikTok restricts every "
        "post an unaudited client makes to private viewing, which means only "
        "you see it. TikTok also caps an unaudited client at 5 posting "
        "accounts in 24 hours and requires the account to be private at the "
        "time of posting. TikTok's audit of the API client is what lifts "
        "that; video.publish posts to the profile and video.upload would "
        "instead leave the post in your drafts.",
    ),
    PushTarget(
        TARGET_FACEBOOK,
        (SECTION_CALL, SECTION_CHART, SECTION_BANDS, SECTION_INDICATORS),
        fields=(
            CredentialField("facebook-app-id", "App ID"),
            CredentialField("facebook-app-secret", "App secret"),
        ),
        issued=(
            CredentialField("facebook-page-id", "Page id"),
            CredentialField("facebook-page-token", "Page access token"),
        ),
        endpoint="POST /<page_id>/feed and /<page_id>/photos",
        scopes=(
            "pages_manage_posts",
            "pages_manage_metadata",
            "pages_read_engagement",
            "pages_show_list",
        ),
        registration="A Meta app with the Pages API, and a Page you "
        "administer. Register the app at "
        "developers.facebook.com/apps/creation/, and pick the use case "
        "Manage everything on your Page.",
        prerequisite="No App Review. Meta grants Standard Access to every "
        "permission automatically, and it covers any account holding a role "
        "on the app, so give your account a role on it.",
    ),
    PushTarget(
        TARGET_THREADS,
        (SECTION_CALL, SECTION_INDICATORS),
        body_limit=500,
        count_unit=COUNT_UTF8_EMOJI,
        fields=(
            CredentialField("threads-client-id", "App ID"),
            CredentialField("threads-client-secret", "App secret"),
        ),
        issued=(
            CredentialField("threads-user-id", "Threads user id"),
            CredentialField("threads-access-token", "Access token"),
        ),
        endpoint="POST /<threads-user-id>/threads then /threads_publish",
        scopes=("threads_basic", "threads_content_publish"),
        registration="A Meta app with the Threads API, on a Threads profile. "
        "Register the app at developers.facebook.com/apps/creation/, and pick "
        "the use case Access the Threads API.",
        prerequisite="No App Review. Meta grants Standard Access to every "
        "permission automatically, and it covers any account holding a role "
        "on the app, so give your account a role on it.",
    ),
    PushTarget(
        TARGET_REDDIT,
        (SECTION_CALL, SECTION_CHART, SECTION_BANDS, SECTION_INDICATORS),
        body_limit=40000,
        title_limit=300,
        fields=(
            CredentialField("reddit-app-id", "App ID"),
            CredentialField("reddit-app-secret", "App secret"),
            CredentialField("reddit-subreddit", "Subreddit"),
            CredentialField("reddit-user-agent", "User agent"),
        ),
        issued=(
            CredentialField("reddit-access-token", "Access token"),
            CredentialField("reddit-refresh-token", "Refresh token"),
        ),
        endpoint="https://www.reddit.com/api/v1/access_token then /api/submit",
        scopes=("identity", "submit"),
        registration="A Reddit app at www.reddit.com/prefs/apps carrying a "
        "loopback redirect address, and a target subreddit.",
        prerequisite="No review and no fee. Reddit requires the User-Agent to "
        "read <platform>:<app ID>:<version> (by /u/<username>), and rate "
        "limits a generic one hard.",
    ),
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
NO_INDICATOR_CAP = ata_spm.NO_INDICATOR_CAP

SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60

#: ``RepostGuard.since`` answers this while a symbol has never reached a target.
NO_SEND_RECORDED = None

NO_CREDENTIAL_TEXT = "No credential held for {target}."
NO_SENDER_TEXT = "No sender wired for {target}."
NO_CEILING_TEXT = "Max posts per hour is unset. Nothing leaves."
RATE_HELD_TEXT = "{sent} post(s) sent this hour, ceiling {ceiling}."
REPOST_HELD_FORMAT = (
    "{symbol} reached {target} {minutes:.0f} minute(s) ago; "
    "one post per ticker per hour."
)
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

#: Every ``CredentialField`` key across ``PUSH_TARGETS``, which is what a page
#: reports back as the part one credential box was typed into.
CREDENTIAL_FIELD_KEYS = tuple(
    one.key for target in PUSH_TARGETS for one in target.fields
)

#: ``CredentialVault.store`` keys one entry per push target and field, so a
#: target holding five values holds five entries.
VAULT_KEY_FORMAT = "{target}:{field}"

CREDENTIAL_HELD_TEXT = "held"
CREDENTIAL_MISSING_TEXT = "not held"
NO_VAULT_TEXT = "Credential vault not wired."

#: What ``held_value`` answers for a field the vault holds nothing for.
NO_CREDENTIAL_VALUE = ""

#: ``CredentialVault.retrieve`` answers a key, a secret and a phrase.
#: ``hold_credential`` writes one field into the first of the three.
VAULT_VALUE_AT = 0

CONNECT_OK_FORMAT = "{target} accepted the credential."
CONNECT_FAILED_FORMAT = "{target} refused the sign-in: {error}"
MISSING_FIELD_FORMAT = "{label} is empty."
NO_CONNECTOR_FORMAT = "No sign-in route wired for {target}."

#: Reads inside ``CONNECT_FAILED_FORMAT`` where a venue completed its flow and
#: still handed back nothing for one of its ``PushTarget.issued`` fields.
NO_ISSUED_FORMAT = "it issued no {label}"

SEND_FAILED_LOG = "ATA-SPM send failed on %s %s: %s"
VAULT_READ_FAILED_LOG = "ATA-SPM credential read failed on %s: %s"
VAULT_STORE_FAILED_LOG = "ATA-SPM credential store failed on %s: %s"
CONNECT_FAILED_LOG = "ATA-SPM sign-in failed on %s: %s"

#: Every ``connect`` outcome, accepted or not. ``CONNECT_FAILED_LOG`` covers only
#: the branch a connector raises on, and four other branches raise nothing.
CONNECT_RESULT_LOG = "ATA-SPM sign-in on %s: accepted=%s, %s"


@dataclass
class ConnectResult:
    """One Level 1A press: the push target, whether it accepted, and its wording."""

    target: str = ""
    ok: bool = False
    detail: str = ""


def push_target(target: Any) -> Optional[PushTarget]:
    """The ``PushTarget`` row one name carries, or None for a name outside it."""
    for one in PUSH_TARGETS:
        if one.name == str(target):
            return one
    return None


def credential_fields(target: Any) -> tuple:
    """Every ``CredentialField`` the operator types for one push target, in page order."""
    found = push_target(target)
    return () if found is None else tuple(found.fields)


def issued_fields(target: Any) -> tuple:
    """Every ``CredentialField`` one push target's own sign-in flow hands back."""
    found = push_target(target)
    return () if found is None else tuple(found.issued)


def stored_fields(target: Any) -> tuple:
    """``credential_fields`` and ``issued_fields`` together, as the vault holds them."""
    return credential_fields(target) + issued_fields(target)


def target_scopes(target: Any) -> tuple:
    """The permissions one push target's own documentation names, in page order."""
    found = push_target(target)
    return () if found is None else tuple(found.scopes)


def missing_value(target: Any, held: Any) -> Optional[CredentialField]:
    """The first ``stored_fields`` entry of one push target carrying no text."""
    values = dict(held or {})
    for one in stored_fields(target):
        if not str(values.get(one.key, "")).strip():
            return one
    return None


def vault_key(target: Any, field_key: Any) -> str:
    """The ``CredentialVault`` entry name one push target's field is held under."""
    return VAULT_KEY_FORMAT.format(target=str(target), field=str(field_key))


def vote_word(direction_text: Any) -> str:
    """One direction word as the bull or bear the bucket line prints."""
    return VOTE_WORDS.get(str(direction_text), VOTE_NEITHER)


def weighted_length(text: str) -> int:
    """X's count of ``text``: each URL costs ``X_URL_COST``, each character its weight."""
    total = 0
    for token in WHITESPACE_RUN.split(text):
        if token.startswith(URL_PREFIXES):
            total += X_URL_COST
            continue
        total += sum(
            ASCII_WEIGHT if one.isascii() else NON_ASCII_WEIGHT for one in token
        )
    return total


def measure_text(text: Any, count_unit: Any = COUNT_CHARACTERS) -> int:
    """How many units the target counting in ``count_unit`` reads in ``text``.

    A character outside ASCII takes the heavier count in every unit, which
    can over-count and never under-count.
    """
    written = str(text)
    if count_unit == COUNT_WEIGHTED:
        return weighted_length(written)
    if count_unit == COUNT_UTF16_RUNES:
        return len(written.encode(UTF16_ENCODING)) // BYTES_PER_RUNE
    if count_unit == COUNT_UTF8_EMOJI:
        return sum(
            ASCII_WEIGHT if one.isascii() else len(one.encode(UTF8_ENCODING))
            for one in written
        )
    return len(written)


def compose(lines: Any, header: Any = FIXED_HEADER) -> str:
    """``header`` over ``lines`` over ``ORGANIZATION_URL``.

    ``fit_to_target`` drops ``lines`` to reach a ceiling and reaches neither
    ``header`` nor ``ORGANIZATION_URL``.
    """
    return POST_LINE_SEPARATOR.join((str(header),) + tuple(lines) + (ORGANIZATION_URL,))


def target_header(target: Any) -> str:
    """The header one push target's row carries, ``FIXED_HEADER`` where the row names none."""
    return str(getattr(target, "header", FIXED_HEADER) or FIXED_HEADER)


def fit_to_target(ranked: Any, target: Any) -> tuple:
    """The lines ``target.body_limit`` holds, and how many were dropped.

    A line drops whole and the longest evidence drops first, so no price,
    band value or statistic is ever cut mid-digit.
    """
    rows = list(ranked)
    lines = [line for _rank, line in rows]
    limit = int(getattr(target, "body_limit", NO_LIMIT_PUBLISHED) or NO_LIMIT_PUBLISHED)
    unit = getattr(target, "count_unit", COUNT_CHARACTERS)
    header = target_header(target)
    if limit <= NO_LIMIT_PUBLISHED:
        return tuple(lines), NO_DROPPED
    if measure_text(compose(lines, header), unit) <= limit:
        return tuple(lines), NO_DROPPED
    order = sorted(
        (at for at, (rank, _line) in enumerate(rows) if rank is not None),
        key=lambda at: rows[at][0],
    )
    gone: set = set()
    kept = list(lines)
    for at in order:
        gone.add(at)
        kept = [line for pos, line in enumerate(lines) if pos not in gone]
        kept.append(ABBREVIATED_FORMAT.format(dropped=len(gone)))
        if measure_text(compose(kept, header), unit) <= limit:
            break
    return tuple(kept), len(gone)


def title_notes(target: Any, headline: str) -> tuple:
    """What one target's title field could not carry, as the note phase five records.

    A ``title_limit`` too small for the row's header with ``headline`` answers
    one ``TITLE_TOO_SMALL_FORMAT`` note.
    """
    limit = int(getattr(target, "title_limit", NO_TITLE_FIELD) or NO_TITLE_FIELD)
    if limit <= NO_TITLE_FIELD:
        return ()
    unit = getattr(target, "count_unit", COUNT_CHARACTERS)
    measured = measure_text(compose((headline,), target_header(target)), unit)
    if measured <= limit:
        return ()
    return (
        TITLE_TOO_SMALL_FORMAT.format(
            target=getattr(target, "name", ""), limit=limit, measured=measured
        ),
    )


def ranked_lines(written: Any) -> list:
    """Each ``(group, line)`` pair with the sort key ``fit_to_target`` drops it by.

    A ``KEEP_LINE`` group never drops, and inside ``DROP_FIRST`` and
    ``DROP_LAST`` the longest line drops first.
    """
    ranked: list = []
    for group, line in written:
        if group is KEEP_LINE:
            ranked.append((KEEP_LINE, line))
            continue
        ranked.append(((group, -len(line)), line))
    return ranked


def post_groups(written: Any) -> list:
    """Each ``(section, line)`` pair of a phase four post as a ``ranked_lines`` group.

    The first ``SECTION_CALL`` line takes ``KEEP_LINE`` and ``SECTION_INDICATORS``
    takes ``DROP_FIRST``.
    """
    grouped: list = []
    call_kept = False
    for name, line in written:
        if name == SECTION_CALL and not call_kept:
            call_kept = True
            grouped.append((KEEP_LINE, line))
            continue
        grouped.append((DROP_FIRST if name == SECTION_INDICATORS else DROP_LAST, line))
    return grouped


def _call_lines(vote: Any, pull: Any, cap: Any) -> list:
    """The call section: the asset, its timeframe, the direction and the timeframes.

    Phase eight's ``ata_spm.TimeframeAgreement`` writes the second line, so
    a post says whether the timeframes agree or one contradicts.
    """
    del cap
    lines = [
        CALL_SECTION_FORMAT.format(
            symbol=vote.symbol,
            label=ata_spm.timeframe_label(vote.timeframe),
            direction=vote.direction_text,
        )
    ]
    agreement = getattr(pull, "agreement", None)
    if agreement is not None:
        lines.append(agreement.text)
    return lines


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

    ``body``, ``caption`` and ``thread_root`` each compose ``header``
    with the lines, so no artefact of this post can omit the header.
    """

    target: str
    symbol: str
    timeframe: str
    vote: str
    header: str = FIXED_HEADER
    band_position: float = ata_spm.MIDLINE_POSITION
    band_lower: float = ata_spm.NO_BAND_VALUE
    band_middle: float = ata_spm.NO_BAND_VALUE
    band_upper: float = ata_spm.NO_BAND_VALUE
    bars: int = ata_spm.NO_BARS
    last_close: float = ata_spm.NO_BAND_VALUE
    closes: tuple = ()
    image_path: str = ""
    lines: tuple = ()
    follows: str = ""
    body_limit: int = NO_LIMIT_PUBLISHED
    title_limit: int = NO_TITLE_FIELD
    count_unit: str = COUNT_CHARACTERS
    dropped: int = NO_DROPPED
    notes: tuple = ()

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
        """The post body: ``header`` over this target's own sections."""
        return compose(self.lines, self.header)

    @property
    def caption(self) -> str:
        """The caption for ``image_path``: ``header`` over the headline."""
        return compose((self.headline,), self.header)

    @property
    def thread_root(self) -> str:
        """The thread root: ``header`` over the headline."""
        return compose((self.headline,), self.header)

    @property
    def title(self) -> str:
        """This target's own title field, empty where ``title_limit`` cannot hold it."""
        if self.title_limit <= NO_TITLE_FIELD:
            return ""
        written = compose((self.headline,), self.header)
        if measure_text(written, self.count_unit) > self.title_limit:
            return ""
        return written

    @property
    def measured(self) -> int:
        """The body's length in the unit ``count_unit`` names."""
        return measure_text(self.body, self.count_unit)

    @property
    def over_limit(self) -> bool:
        """Whether the body measures more than ``body_limit`` publishes."""
        if self.body_limit <= NO_LIMIT_PUBLISHED:
            return False
        return self.measured > self.body_limit

    def artefacts(self) -> dict:
        """Every artefact of this post, keyed by ``ARTEFACT_KEYS`` and ``ARTEFACT_TITLE``.

        A post whose phase-three render wrote no file carries no
        ``ARTEFACT_IMAGE`` key, and every text key composes ``header``.
        """
        written = dict(zip(ARTEFACT_KEYS, (self.body, self.caption, self.thread_root)))
        title = self.title
        if title:
            written[ARTEFACT_TITLE] = title
        if self.image_path:
            written[ARTEFACT_IMAGE] = self.image_path
        return written


def format_post(
    vote: Any,
    pull: Any,
    target: PushTarget,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> FormattedPost:
    """Phase four: one reversal call written for one push target.

    The sections come from ``target.sections`` and their wording from the
    evidence ``ata_spm.pull`` answered, and ``fit_to_target`` holds the body
    under the ceiling this target publishes.
    """
    written: list = []
    for name in target.sections:
        writer = SECTION_WRITERS.get(name)
        if writer is None:
            continue
        written.extend(
            (name, one) for one in writer(vote, pull, max_supporting_indicators)
        )
    lines, dropped = fit_to_target(ranked_lines(post_groups(written)), target)
    return FormattedPost(
        target=target.name,
        symbol=vote.symbol,
        timeframe=vote.timeframe,
        vote=vote_word(vote.direction_text),
        header=target_header(target),
        band_position=float(vote.band_position),
        band_lower=pull.band_lower,
        band_middle=pull.band_middle,
        band_upper=pull.band_upper,
        bars=pull.bars,
        last_close=pull.last_close,
        closes=tuple(pull.closes),
        image_path=str(getattr(getattr(pull, "image", None), "path", "") or ""),
        lines=lines,
        body_limit=int(getattr(target, "body_limit", NO_LIMIT_PUBLISHED)),
        title_limit=int(getattr(target, "title_limit", NO_TITLE_FIELD)),
        count_unit=str(getattr(target, "count_unit", COUNT_CHARACTERS)),
        dropped=dropped,
        notes=title_notes(
            target,
            POST_HEADLINE_FORMAT.format(
                symbol=vote.symbol,
                label=ata_spm.timeframe_label(vote.timeframe),
                vote=vote_word(vote.direction_text),
            ),
        ),
    )


def format_follow_up(outcome: FollowUpOutcome, target: PushTarget) -> FormattedPost:
    """Phase seven's own post: what happened to one call, written for one target.

    ``follows`` names the original post, so a reader sees the call and its
    outcome together, and ``SECTION_CHART`` adds the candles read since.
    """
    call = outcome.call
    written = [
        (
            KEEP_LINE,
            FOLLOW_UP_HEAD_FORMAT.format(headline=call.headline, state=outcome.state),
        ),
        (
            DROP_LAST,
            FOLLOW_UP_CALL_FORMAT.format(
                symbol=call.symbol,
                label=ata_spm.timeframe_label(call.timeframe),
                direction=call.direction,
                state=outcome.state,
            ),
        ),
        (DROP_LAST, FOLLOW_UP_EVIDENCE_FORMAT.format(detail=outcome.detail)),
    ]
    if SECTION_CHART in target.sections:
        written.append(
            (
                DROP_FIRST,
                CHART_SECTION_FORMAT.format(
                    bars=len(outcome.closes), close=outcome.close
                ),
            )
        )
    if SECTION_BANDS in target.sections:
        written.append(
            (
                DROP_FIRST,
                BANDS_SECTION_FORMAT.format(
                    lower=call.band_lower,
                    middle=call.band_middle,
                    upper=call.band_upper,
                ),
            )
        )
    lines, dropped = fit_to_target(ranked_lines(written), target)
    return FormattedPost(
        target=target.name,
        symbol=call.symbol,
        timeframe=call.timeframe,
        vote=call.vote,
        header=target_header(target),
        band_position=call.band_position,
        band_lower=call.band_lower,
        band_middle=call.band_middle,
        band_upper=call.band_upper,
        bars=len(outcome.closes),
        last_close=outcome.close,
        closes=outcome.closes,
        lines=lines,
        follows=call.headline,
        body_limit=int(getattr(target, "body_limit", NO_LIMIT_PUBLISHED)),
        title_limit=int(getattr(target, "title_limit", NO_TITLE_FIELD)),
        count_unit=str(getattr(target, "count_unit", COUNT_CHARACTERS)),
        dropped=dropped,
        notes=title_notes(target, call.headline),
    )


class FollowUpWatch:
    """Phase seven: the reversal calls being watched, and their outcomes.

    ``watch_run`` takes every call one run charted, and ``check`` reads each
    chart again and answers what happened to it.
    """

    def __init__(self) -> None:
        self.calls: list = []
        self.outcomes: list = []
        self.settled: dict = {}

    def watch_run(self, run: Any) -> int:
        """Watch every charted reversal call, and answer how many are held.

        A call already watched, one already settled, and one the gates refused
        a chart are not taken; ``FollowUpCall.key`` decides the first two.
        """
        pulls = {(one.symbol, one.timeframe): one for one in getattr(run, "pulls", [])}
        held = {one.key for one in self.calls} | set(self.settled)
        for vote in getattr(run, "calls", []):
            pull = pulls.get((vote.symbol, vote.timeframe))
            if pull is None or pull.bars <= ata_spm.NO_CANDLES:
                continue
            call = FollowUpCall(
                symbol=vote.symbol,
                timeframe=vote.timeframe,
                direction=vote.direction_text,
                vote=vote_word(vote.direction_text),
                at=pull.bars - 1,
                close=pull.last_close,
                headline=POST_HEADLINE_FORMAT.format(
                    symbol=vote.symbol,
                    label=ata_spm.timeframe_label(vote.timeframe),
                    vote=vote_word(vote.direction_text),
                ),
                band_position=float(vote.band_position),
                band_lower=pull.band_lower,
                band_middle=pull.band_middle,
                band_upper=pull.band_upper,
            )
            if call.key in held:
                continue
            held.add(call.key)
            self.calls.append(call)
        return len(self.calls)

    def check(self, candle_source: Any, share_pct: Any) -> list:
        """Read each watched call's chart again and answer what happened to it.

        A settled call stops being watched and an open one stays, so no call
        is posted on twice.
        """
        found: list = []
        still: list = []
        for call in self.calls:
            candles = ata_spm.candles_for(candle_source, call.symbol, call.timeframe)
            outcome = follow_up_outcome(call, candles, share_pct)
            found.append(outcome)
            if outcome.settled:
                self.settled[call.key] = call
            else:
                still.append(call)
        self.calls = still
        self.outcomes = found
        return found

    def lines(self) -> list:
        """Every outcome the last check answered, as the lines the zone reads."""
        return [one.line for one in self.outcomes]


def format_run(
    run: Any,
    targets: Any = PUSH_TARGETS,
    max_supporting_indicators: Any = NO_INDICATOR_CAP,
) -> list:
    """Phase four over one ``ata_spm.AtaSpmRun``: every target of every call
    that carries a chart, which is every call the live gate chains would fire.
    """
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


def expected_move(call_close: Any, midline: Any) -> float:
    """The move one reversal call expects: its own close to the Bollinger midline."""
    return float(midline) - float(call_close)


def confirmation_target(call_close: Any, midline: Any, share_pct: Any) -> float:
    """The close a confirmation needs: ``share_pct`` of the run to the midline."""
    share_ratio = float(share_pct) / ata_spm.PERCENT_PER_RATIO_UNIT
    return float(call_close) + expected_move(call_close, midline) * share_ratio


def target_reached(direction_text: Any, close: Any, target: Any) -> bool:
    """Whether one close moved the called direction as far as ``target``."""
    if str(direction_text) == ata_spm.DIRECTION_BULLISH:
        return float(close) >= float(target)
    if str(direction_text) == ata_spm.DIRECTION_BEARISH:
        return float(close) <= float(target)
    return False


def continues_against(direction_text: Any, close: Any, previous: Any) -> bool:
    """Whether one candle carried on the trend the reversal called against."""
    if str(direction_text) == ata_spm.DIRECTION_BULLISH:
        return float(close) < float(previous)
    if str(direction_text) == ata_spm.DIRECTION_BEARISH:
        return float(close) > float(previous)
    return False


@dataclass(frozen=True)
class FollowUpCall:
    """One reversal call phase seven watches, and the post that made it."""

    symbol: str
    timeframe: str
    direction: str
    vote: str
    at: int = 0
    close: float = NO_MIDLINE
    headline: str = ""
    band_position: float = ata_spm.MIDLINE_POSITION
    band_lower: float = ata_spm.NO_BAND_VALUE
    band_middle: float = ata_spm.NO_BAND_VALUE
    band_upper: float = ata_spm.NO_BAND_VALUE

    @property
    def key(self) -> tuple:
        """What tells two watched calls apart: the asset, its timeframe, its bar."""
        return (self.symbol, self.timeframe, self.at)


@dataclass
class FollowUpOutcome:
    """Phase seven for one call: confirmed, failed, or still open."""

    call: FollowUpCall
    state: str = OUTCOME_OPEN
    candles: int = 0
    close: float = NO_MIDLINE
    target: float = NO_MIDLINE
    midline: float = NO_MIDLINE
    against_run: int = NO_CONTINUATION
    closes: tuple = ()
    detail: str = ""

    @property
    def settled(self) -> bool:
        """Whether the state is ``OUTCOME_CONFIRMED`` or ``OUTCOME_FAILED``."""
        return self.state in (OUTCOME_CONFIRMED, OUTCOME_FAILED)

    @property
    def line(self) -> str:
        """The original call, the outcome and its evidence, as one line."""
        return FOLLOW_UP_LINE_FORMAT.format(
            headline=self.call.headline, state=self.state, detail=self.detail
        )


def follow_up_detail(outcome: FollowUpOutcome, share_pct: Any) -> str:
    """The evidence one outcome rests on, worded for the state it reached."""
    if outcome.state == OUTCOME_CONFIRMED:
        return FOLLOW_UP_CONFIRMED_FORMAT.format(
            close=outcome.close,
            target=outcome.target,
            share=int(share_pct),
            midline=outcome.midline,
            candles=outcome.candles,
        )
    if outcome.state == OUTCOME_FAILED:
        return FOLLOW_UP_FAILED_FORMAT.format(
            run=outcome.against_run, close=outcome.close, candles=outcome.candles
        )
    if not outcome.candles:
        return FOLLOW_UP_NO_CANDLE_TEXT
    if int(share_pct or NO_SHARE_SET) <= NO_SHARE_SET:
        return FOLLOW_UP_NO_SHARE_FORMAT.format(
            candles=outcome.candles, close=outcome.close
        )
    if outcome.against_run > NO_CONTINUATION:
        return FOLLOW_UP_NOT_READY_FORMAT.format(
            run=outcome.against_run,
            floor=CONTINUATION_CANDLE_FLOOR,
            close=outcome.close,
            target=outcome.target,
        )
    return FOLLOW_UP_OPEN_FORMAT.format(
        candles=outcome.candles, close=outcome.close, target=outcome.target
    )


def follow_up_outcome(
    call: FollowUpCall, candles: Any, share_pct: Any
) -> FollowUpOutcome:
    """Phase seven over the candles that closed after one watched call.

    A close reaching ``confirmation_target`` confirms it, and
    ``CONTINUATION_CANDLE_FLOOR`` candles in a row against it fail it.
    """
    held = list(candles or [])
    closes = [float(getattr(one, "close", NO_MIDLINE)) for one in held]
    midlines = ata_spm.midline_after(held, call.at)
    found = FollowUpOutcome(call=call, close=call.close, closes=tuple(closes))
    share = int(share_pct or NO_SHARE_SET)
    previous = call.close
    run_against = NO_CONTINUATION
    for step, close in enumerate(closes[call.at + 1 :]):
        found.candles = step + 1
        found.close = close
        found.midline = midlines[step] if step < len(midlines) else NO_MIDLINE
        if share > NO_SHARE_SET and found.midline > NO_MIDLINE:
            found.target = confirmation_target(call.close, found.midline, share)
            if target_reached(call.direction, close, found.target):
                found.state = OUTCOME_CONFIRMED
                break
        if continues_against(call.direction, close, previous):
            run_against += 1
        else:
            run_against = NO_CONTINUATION
        if run_against >= CONTINUATION_CANDLE_FLOOR:
            found.state = OUTCOME_FAILED
            break
        previous = close
    found.against_run = run_against
    found.detail = follow_up_detail(found, share)
    return found


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


class RepostGuard:
    """One ticker, one post per push target per hour, whatever composed it.

    ``ReadyToSend`` keeps one of these, so the hour holds across the whole
    bucket and a second call on a symbol is refused like a repost of the first.
    """

    def __init__(self) -> None:
        self.sent_at: dict = {}

    def since(self, now: float, symbol: Any, target: Any) -> Optional[float]:
        """Seconds since ``symbol`` last reached ``target``, or None for never."""
        held = self.sent_at.get((str(symbol), str(target)))
        if held is None:
            return NO_SEND_RECORDED
        return float(now) - float(held)

    def allows(self, now: float, symbol: Any, target: Any) -> bool:
        """Whether an hour has passed since ``symbol`` last reached ``target``."""
        gap = self.since(now, symbol, target)
        return gap is NO_SEND_RECORDED or gap >= SECONDS_PER_HOUR

    def record(self, now: float, symbol: Any, target: Any) -> None:
        """Take one send of ``symbol`` to ``target`` at ``now``."""
        self.sent_at[(str(symbol), str(target))] = float(now)

    def held_text(self, now: float, symbol: Any, target: Any) -> str:
        """Why ``allows`` refused: how long ago ``symbol`` reached ``target``."""
        gap = self.since(now, symbol, target)
        return REPOST_HELD_FORMAT.format(
            symbol=symbol,
            target=target,
            minutes=(gap or 0.0) / SECONDS_PER_MINUTE,
        )


class AtaSpmSettings:
    """The ATA-SPM settings page, carrying only what a phase reads.

    ``max_posts_per_hour`` is the ceiling ``SendRate`` obeys and
    ``max_supporting_indicators`` the cap phase four draws under.
    ``confirmation_share_pct`` is the share of the run to the Bollinger
    midline ``confirmation_target`` reads.
    """

    def __init__(self) -> None:
        self.max_posts_per_hour = NO_CEILING_SET
        self.max_supporting_indicators = NO_INDICATOR_CAP
        self.confirmation_share_pct = NO_SHARE_SET
        self.message_format = ata_spm.MESSAGE_FORMAT
        self.vault: Any = None
        self.connector: Optional[Callable] = None
        self.typed: dict = {}

    def set_vault(self, vault: Any) -> None:
        """Take the credential vault every push target's token is held in."""
        self.vault = vault

    def set_connector(self, connector: Optional[Callable]) -> None:
        """Take what signs one push target in, or None while no route is wired."""
        self.connector = connector

    def set_credential_text(self, target: Any, field: Any, typed: Any) -> None:
        """Hold what one credential field carries until ``connect`` reads it.

        Nothing here reaches ``credential_rows``, so no view model or render
        carries a typed value.
        """
        # A pasted value carries edge whitespace and the venue reads it
        # literally, so it is stripped here, where ``missing_field`` strips.
        held = str(typed or "").strip()
        self.typed.setdefault(str(target), {})[str(field)] = held

    def hold_credential(self, target: Any, field: Any) -> bool:
        """Encrypt what one finished credential box carries into ``vault``.

        Level 1A calls this when he leaves a box, not on every keystroke, and
        answers whether the vault now holds a value for it. A box he emptied
        drops its entry instead, so ``held_fields`` reads what is held without
        decrypting anything.
        """
        name = str(target)
        key = str(field)
        typed = self.typed.get(name, {})
        if key not in typed or self.vault is None:
            return False
        held = str(typed[key]).strip()
        try:
            if held:
                self.vault.store(vault_key(name, key), held, "")
            else:
                self.vault.delete(vault_key(name, key))
        except Exception as exc:  # noqa: BLE001 - the vault is host-supplied
            logger.debug(VAULT_STORE_FAILED_LOG, name, exc)
            return False
        return bool(held)

    def held_value(self, target: Any, field_key: Any) -> str:
        """The value ``vault`` holds for one field of one push target, or no text."""
        if self.vault is None:
            return NO_CREDENTIAL_VALUE
        entry = vault_key(target, field_key)
        try:
            if not self.vault.has_exchange(entry):
                return NO_CREDENTIAL_VALUE
            return str(self.vault.retrieve(entry)[VAULT_VALUE_AT])
        except Exception as exc:  # noqa: BLE001 - the vault is host-supplied
            logger.debug(VAULT_READ_FAILED_LOG, target, exc)
            return NO_CREDENTIAL_VALUE

    def credential_value(self, target: Any, field_key: Any) -> str:
        """What one credential box carries: what he typed, or what ``vault`` holds.

        A key he has typed into this run wins, so emptying a held box reads
        empty rather than falling back to the value it replaced.
        """
        held = self.typed.get(str(target), {})
        key = str(field_key)
        if key in held:
            return str(held[key])
        return self.held_value(target, key)

    def held_fields(self, target: Any) -> tuple:
        """Every ``CredentialField`` key of one push target ``vault`` holds a value for.

        ``has_exchange`` answers this without decrypting, so Level 1A can draw
        a box as held on every paint and no value leaves the vault.
        """
        if self.vault is None:
            return ()
        try:
            return tuple(
                one.key
                for one in credential_fields(target)
                if self.vault.has_exchange(vault_key(target, one.key))
            )
        except Exception as exc:  # noqa: BLE001 - the vault is host-supplied
            logger.debug(VAULT_READ_FAILED_LOG, target, exc)
            return ()

    def typed_credential(self, target: Any) -> dict:
        """Each ``CredentialField`` key of one push target, and the value it carries."""
        return {
            one.key: self.credential_value(target, one.key)
            for one in credential_fields(target)
        }

    def missing_field(self, target: Any) -> Optional[CredentialField]:
        """The first ``CredentialField`` of one push target carrying no text.

        A value the vault holds counts as present, so a page he filled before
        a restart takes Connect without being typed again.
        """
        for one in credential_fields(target):
            if not self.credential_value(target, one.key).strip():
                return one
        return None

    def connect(self, target: Any) -> "ConnectResult":
        """Sign one push target in, and record what it answered.

        Every branch of ``sign_in_answer`` reaches this one ``CONNECT_RESULT_LOG``
        line, so a sign-in that raises nothing is still written down.
        """
        answer = self.sign_in_answer(target)
        logger.info(CONNECT_RESULT_LOG, answer.target, answer.ok, answer.detail)
        return answer

    def sign_in_answer(self, target: Any) -> "ConnectResult":
        """Sign one push target in, and store the credential only once it accepts.

        An empty box, an unwired ``connector`` and a refusing venue each
        answer ``ok`` False with the wording Level 1A prints.
        """
        name = str(target)
        answer = ConnectResult(target=name)
        empty = self.missing_field(name)
        if empty is not None:
            answer.detail = MISSING_FIELD_FORMAT.format(label=empty.label)
            return answer
        if self.connector is None:
            answer.detail = NO_CONNECTOR_FORMAT.format(target=name)
            return answer
        typed = self.typed_credential(name)
        try:
            issued = self.connector(name, dict(typed))
        except Exception as exc:  # noqa: BLE001 - the connector is host-supplied
            logger.debug(CONNECT_FAILED_LOG, name, exc)
            answer.detail = CONNECT_FAILED_FORMAT.format(target=name, error=exc)
            return answer
        held = dict(typed)
        held.update({str(key): str(one) for key, one in dict(issued or {}).items()})
        absent = missing_value(name, held)
        if absent is not None:
            answer.detail = CONNECT_FAILED_FORMAT.format(
                target=name, error=NO_ISSUED_FORMAT.format(label=absent.label)
            )
            return answer
        if not self.store_credential(name, held):
            answer.detail = NO_VAULT_TEXT
            return answer
        self.typed.pop(name, None)
        answer.ok = True
        answer.detail = CONNECT_OK_FORMAT.format(target=name)
        return answer

    def store_credential(self, target: Any, typed: Any) -> bool:
        """Encrypt one push target's ``stored_fields`` into ``vault``, one entry each.

        A missing or refusing ``vault`` answers False, and the target then
        reads unreachable.
        """
        if self.vault is None:
            return False
        held = dict(typed or {})
        if not held:
            return False
        try:
            for field_key, value in held.items():
                self.vault.store(vault_key(target, field_key), str(value), "")
        except Exception as exc:  # noqa: BLE001 - the vault is host-supplied
            logger.debug(VAULT_STORE_FAILED_LOG, target, exc)
            return False
        return True

    def holds(self, target: Any) -> bool:
        """Whether ``vault`` holds every ``stored_fields`` entry one push target needs.

        A target reads held only once its own sign-in has run, since the
        ``PushTarget.issued`` entries reach the vault nowhere else.
        """
        fields = stored_fields(target)
        if self.vault is None or not fields:
            return False
        try:
            return all(
                bool(self.vault.has_exchange(vault_key(target, one.key)))
                for one in fields
            )
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
    repost: RepostGuard,
    now: float,
) -> DeliveryRecord:
    """Phase five for one post: send it, or record why it did not go.

    Every refusal answers a ``DeliveryRecord`` naming the target, and a post
    whose ``over_limit`` is true, or whose ticker ``repost`` still holds,
    never reaches ``sender``.
    """
    record = DeliveryRecord(
        target=post.target, symbol=post.symbol, timeframe=post.timeframe
    )
    if post.over_limit:
        record.detail = OVER_LIMIT_TEXT.format(
            target=post.target, limit=post.body_limit, measured=post.measured
        )
        return record
    if not settings.holds(post.target):
        record.detail = NO_CREDENTIAL_TEXT.format(target=post.target)
        return record
    if sender is None:
        record.detail = NO_SENDER_TEXT.format(target=post.target)
        return record
    if not rate.allows(now, settings.max_posts_per_hour):
        record.detail = rate.held_text(now, settings.max_posts_per_hour)
        return record
    if not repost.allows(now, post.symbol, post.target):
        record.detail = repost.held_text(now, post.symbol, post.target)
        return record
    try:
        record.destination = str(sender(post))
    except Exception as exc:  # noqa: BLE001 - the sender is host-supplied
        logger.debug(SEND_FAILED_LOG, post.target, post.symbol, exc)
        record.detail = SEND_FAILED_TEXT.format(target=post.target, error=exc)
        return record
    record.sent = True
    rate.record(now)
    repost.record(now, post.symbol, post.target)
    return record


def distribute(
    posts: Any,
    sender: Optional[Callable] = None,
    settings: Optional[AtaSpmSettings] = None,
    rate: Optional[SendRate] = None,
    clock: Optional[Callable] = None,
    repost: Optional[RepostGuard] = None,
) -> list:
    """Phase five: send every post given, and answer one record for each.

    With no ``sender`` every post records the target it could not reach.
    """
    held = settings if settings is not None else AtaSpmSettings()
    counter = rate if rate is not None else SendRate()
    guard = repost if repost is not None else RepostGuard()
    now = float(clock() if clock is not None else 0.0)
    return [
        deliver_one(one, sender, held, counter, guard, now) for one in list(posts or [])
    ]


@dataclass(frozen=True)
class WatchedMarket:
    """One market on the ATA-SMP chart list, and the call that queued it."""

    symbol: str
    vote: str = VOTE_NEITHER
    timeframes: tuple = ()


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
        self.repost = RepostGuard()
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

    def load_follow_ups(self, outcomes: Any, targets: Any = PUSH_TARGETS) -> int:
        """Hold one phase seven post per settled outcome, per push target.

        The follow-ups a previous check wrote are dropped first, so the
        bucket never carries two posts about one call.
        """
        self.posts = [one for one in self.posts if not one.post.follows]
        written = [
            format_follow_up(one, target)
            for one in list(outcomes or [])
            if one.settled
            for target in targets
        ]
        self.posts.extend(BucketPost(post=one) for one in written)
        return len(written)

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
            [one.post for one in held],
            sender,
            settings,
            self.rate,
            clock,
            self.repost,
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
        self.follow_up = FollowUpWatch()
        self.settings_open = False
        self.credential_target: Optional[str] = None
        self.connect_result: Optional[ConnectResult] = None
        self.sender: Optional[Callable] = None
        self.clock: Optional[Callable] = None

    def set_sender(self, sender: Optional[Callable]) -> None:
        """Take what phase five sends through, or None to send nothing."""
        self.sender = sender

    def toggle_settings(self) -> bool:
        """Show Level 1, or the scan page, and answer which.

        Closing drops ``credential_target`` and ``connect_result``, so Level 1A
        never reopens on a target the operator left.
        """
        self.settings_open = not self.settings_open
        if not self.settings_open:
            self.credential_target = None
            self.connect_result = None
        return self.settings_open

    def open_credentials(self, target: Any) -> Optional[str]:
        """Show one push target's Level 1A page, and answer which target it draws."""
        found = push_target(target)
        if found is None:
            return None
        self.settings_open = True
        self.credential_target = found.name
        self.connect_result = None
        return self.credential_target

    def close_credentials(self) -> None:
        """Leave Level 1A for Level 1, dropping what the last ``connect`` said."""
        self.credential_target = None
        self.connect_result = None

    def connect_credentials(self) -> Optional[ConnectResult]:
        """Sign the open Level 1A target in, and leave the page only once it accepts."""
        if self.credential_target is None:
            return None
        answer = self.settings.connect(self.credential_target)
        self.connect_result = answer
        if answer.ok:
            self.credential_target = None
        return answer

    def load_run(self, run: Any) -> int:
        """Fill the bucket from one run and answer how many posts it holds."""
        return self.bucket.load_run(run, self.settings)

    def after_scan(self, run: Any, candle_source: Any) -> list:
        """Phase seven around one scan, and the outcomes the check answered.

        The calls watched before this scan are checked first, then this
        run's own calls are taken, so no call is checked against no candle.
        """
        found = self.follow_up.check(
            candle_source, self.settings.confirmation_share_pct
        )
        self.bucket.load_follow_ups(found)
        self.follow_up.watch_run(run)
        return found

    def post_selected(self, index: Any) -> list:
        """Press Post Selected on the post one zone index shows."""
        return self.bucket.post_selected(index, self.sender, self.settings, self.clock)

    def post_all(self) -> list:
        """Press Post All over every approved post in the bucket."""
        return self.bucket.post_all(self.sender, self.settings, self.clock)

    def release(self) -> list:
        """Release the bucket while Send Bucket Full Auto is on."""
        return self.bucket.release(self.sender, self.settings, self.clock)

    def watched_rows(self) -> list:
        """Every call under watch as symbol, timeframe and vote, oldest first.

        The settled calls are sorted by ``FollowUpCall.key`` so the order does
        not follow the dictionary.
        """
        rows = [
            [one.symbol, one.timeframe, one.vote]
            for one in sorted(self.follow_up.settled.values(), key=lambda c: c.key)
        ]
        rows.extend(
            [one.symbol, one.timeframe, one.vote] for one in self.follow_up.calls
        )
        rows.extend(
            [one.post.symbol, one.post.timeframe, one.post.vote]
            for one in self.bucket.posts
        )
        return rows

    def watched_markets(self) -> list:
        """One ``WatchedMarket`` per market that reached Ready to Send.

        The bucket is the trigger and ``follow_up`` keeps a market listed
        after ``load_run`` replaces the bucket, so the Charts tab and phase
        seven read one set. The newest call's vote wins.
        """
        held: dict = {}
        for symbol, timeframe, vote in self.watched_rows():
            found = held.get(symbol)
            timeframes = () if found is None else found.timeframes
            if timeframe not in timeframes:
                timeframes = timeframes + (timeframe,)
            held[symbol] = WatchedMarket(
                symbol=symbol, vote=vote, timeframes=timeframes
            )
        return list(held.values())

    def phase_report(self) -> dict:
        """What phases four, five and six each produced, for the zone lines."""
        return {
            PHASE_FORMAT_NAME: len(self.bucket.posts),
            PHASE_DISTRIBUTE_NAME: len(self.bucket.records),
            PHASE_BUCKET_NAME: self.bucket.summary(),
            PHASE_FOLLOW_UP_NAME: len(self.follow_up.calls),
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
