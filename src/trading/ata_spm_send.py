"""ata_spm_send.py -- the API senders phase five posts through.

``build_sender`` answers the ``ApiSender`` that ``PushBoard.set_sender``
takes: one ``SEND_ROUTES`` row per venue whose credential is typed on the
settings page, each building one ``multipart/form-data`` request carrying
the post's body and its venue image, sent through ``safe_urlopen`` and
recorded on the ``APIInteractionLog``. A venue refusing raises
``SendRefused`` carrying the detail ``ata_spm_push.deliver_one`` writes.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.signal_contract import emit as _pin_emit
from . import ata_spm, ata_spm_push

logger = logging.getLogger("acervator.ata_spm_send")

#: The pin ``ApiSender`` writes once per request, through ``_pin_emit``.
SENT_PIN = "inspector.ata.sent"

#: The two hosts the senders post to. A reading points them at loopback.
DISCORD_API_BASE = "https://discord.com/api/webhooks"
TELEGRAM_API_BASE = "https://api.telegram.org"

#: A webhook URL as Discord's channel settings print it.
DISCORD_WEBHOOK_PATTERN = re.compile(
    r"^https://discord\.com/api/webhooks/(?P<id>\d+)/(?P<token>[A-Za-z0-9_-]+)$"
)
DISCORD_WEBHOOK_FORM = "https://discord.com/api/webhooks/<id>/<token>"

#: A bot token as BotFather prints it, and a chat id as a number or @name.
TELEGRAM_BOT_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
TELEGRAM_CHAT_PATTERN = re.compile(r"^(-?\d+|@[A-Za-z][A-Za-z0-9_]{4,})$")
TELEGRAM_BOT_FORM = "<bot id>:<secret part>, as BotFather prints it"
TELEGRAM_CHAT_FORM = "a chat id number or @channelname"

#: ``?wait=true`` makes Discord answer the created message and its ``id``.
DISCORD_WAIT_QUERY = "wait=true"
DISCORD_PAYLOAD_FIELD = "payload_json"
DISCORD_FILE_FIELD = "files[0]"
DISCORD_CONTENT_KEY = "content"
DISCORD_ID_KEY = "id"
DISCORD_CHANNEL_KEY = "channel_id"
DISCORD_MESSAGE_KEY = "message"

TELEGRAM_SEND_PHOTO = "sendPhoto"
TELEGRAM_BOT_PATH_FORMAT = "bot{token}"
TELEGRAM_CHAT_FIELD = "chat_id"
TELEGRAM_CAPTION_FIELD = "caption"
TELEGRAM_PHOTO_FIELD = "photo"
TELEGRAM_OK_KEY = "ok"
TELEGRAM_RESULT_KEY = "result"
TELEGRAM_MESSAGE_ID_KEY = "message_id"
TELEGRAM_CHAT_KEY = "chat"
TELEGRAM_DESCRIPTION_KEY = "description"
TELEGRAM_PARAMETERS_KEY = "parameters"

RETRY_AFTER_KEY = "retry_after"
NO_RETRY_AFTER = 0.0

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_TOO_MANY_REQUESTS = 429
CREDENTIAL_REFUSED_CODES = (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN)
#: What ``urlopen_multipart`` records when no HTTP answer came back.
NO_HTTP = 0

PNG_CONTENT_TYPE = "image/png"
JSON_ACCEPT = "application/json"
MULTIPART_FORMAT = "multipart/form-data; boundary={boundary}"
CONTENT_TYPE_HEADER = "Content-Type"
ACCEPT_HEADER = "Accept"
USER_AGENT_HEADER = "User-Agent"
USER_AGENT = "Acervator ATA-SPM"
METHOD_POST = "POST"
FIELD_PART_FORMAT = (
    '--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
)
FILE_PART_FORMAT = (
    '--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
    'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
)
CLOSE_PART_FORMAT = "\r\n--{boundary}--\r\n"
TEXT_ENCODING = "utf-8"

#: What one ``APIInteractionLog`` block carries; the token never reaches it.
DISCORD_ACTION = "execute_webhook"
TELEGRAM_ACTION = "send_photo"
DISCORD_LOGGED_ENDPOINT = DISCORD_API_BASE + "/<id>/<token>?" + DISCORD_WAIT_QUERY
TELEGRAM_LOGGED_ENDPOINT = TELEGRAM_API_BASE + "/bot<token>/" + TELEGRAM_SEND_PHOTO
API_REASON_FORMAT = "ATA-SPM post {symbol} {label}"
API_SENT_FORMAT = "{http} message {message_id}"
API_REFUSED_FORMAT = "refused: {detail}"
API_LEVEL_INFO = "info"
API_LEVEL_ERROR = "error"
SEND_DATA_USAGE = "The post's text and its venue image, handed to the venue"
PARAM_TEXT_CHARS = "text_chars"
PARAM_IMAGE_BYTES = "image_bytes"
PARAM_IMAGE_NAME = "image_name"
PARAM_CHAT_ID = "chat_id"
PARAM_WAIT = "wait"

DESTINATION_FORMAT = "{place} {place_id}, message {message_id}"
DISCORD_PLACE = "channel"
TELEGRAM_PLACE = "chat"
NO_PLACE_ID = "?"

RATE_LIMITED_FORMAT = "429, retry after {seconds:g} s"
CREDENTIAL_REFUSED_FORMAT = "{http}, the credential was refused: {said}"
HTTP_REFUSED_FORMAT = "{http}, {said}"
NO_CONNECTION_FORMAT = "no connection: {reason}"
NO_IMAGE_FORMAT = "no image on disk at {path}"
NO_MESSAGE_ID_FORMAT = "{target} answered no message id"
NO_SEND_ROUTE_FORMAT = "No send route for {target}."
WRONG_SHAPE_FORMAT = "the {label} does not read as {form}"
VENUE_SAID_NOTHING_TEXT = "the venue said nothing"

SEND_LOG = "ATA-SPM send to %s for %s %s: %s"
SEND_REFUSED_LOG = "ATA-SPM send to %s for %s %s refused: %s"


class SendRefused(Exception):
    """A venue, the network or the post itself stopped one send short.

    ``http`` is the status the venue answered, or ``NO_HTTP`` where none came.
    """

    def __init__(self, detail: str, http: int = NO_HTTP) -> None:
        super().__init__(detail)
        self.detail = detail
        self.http = http


@dataclass(frozen=True)
class SendRequest:
    """One multipart request: the form fields, the one file part and its bytes."""

    url: str
    fields: dict
    file_field: str
    filename: str
    content: bytes
    content_type: str = PNG_CONTENT_TYPE


@dataclass(frozen=True)
class SendAnswer:
    """What a venue answered one ``SendRequest`` with: the status and the JSON."""

    http: int
    body: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SendOutcome:
    """What one route made of a venue's answer: the destination phase five
    records, the message id, the status, and the parameters the API block names."""

    destination: str
    message_id: str
    http: int
    params: dict = field(default_factory=dict)


def multipart_body(request: SendRequest) -> tuple:
    """The ``multipart/form-data`` bytes of one request and the boundary used."""
    boundary = uuid.uuid4().hex
    parts = [
        FIELD_PART_FORMAT.format(boundary=boundary, name=name, value=value).encode(
            TEXT_ENCODING
        )
        for name, value in request.fields.items()
    ]
    parts.append(
        FILE_PART_FORMAT.format(
            boundary=boundary,
            name=request.file_field,
            filename=request.filename,
            content_type=request.content_type,
        ).encode(TEXT_ENCODING)
    )
    parts.append(bytes(request.content))
    parts.append(CLOSE_PART_FORMAT.format(boundary=boundary).encode(TEXT_ENCODING))
    return b"".join(parts), boundary


def _json_of(raw: bytes) -> dict:
    """The JSON object ``raw`` decodes to, or an empty dict for anything else."""
    try:
        held = json.loads(raw.decode(TEXT_ENCODING))
    except (UnicodeDecodeError, ValueError):
        return {}
    return held if isinstance(held, dict) else {}


def urlopen_multipart(request: SendRequest) -> SendAnswer:
    """Post one ``SendRequest`` through ``safe_urlopen`` and answer the ``SendAnswer``.

    An HTTP error answers its status and body too; no connection raises
    ``SendRefused`` with ``NO_CONNECTION_FORMAT``.
    """
    from ..core.safe_url import SafeRequest, safe_urlopen
    from .ata_spm_signin import TRANSPORT_TIMEOUT_SECONDS

    body, boundary = multipart_body(request)
    sent = SafeRequest(request.url)
    sent.add_header(CONTENT_TYPE_HEADER, MULTIPART_FORMAT.format(boundary=boundary))
    sent.add_header(ACCEPT_HEADER, JSON_ACCEPT)
    sent.add_header(USER_AGENT_HEADER, USER_AGENT)
    sent.method = METHOD_POST
    try:
        with safe_urlopen(sent, body, timeout=TRANSPORT_TIMEOUT_SECONDS) as answered:
            return SendAnswer(int(answered.status), _json_of(answered.read()))
    except urllib.error.HTTPError as exc:
        return SendAnswer(int(exc.code), _json_of(exc.read()))
    except urllib.error.URLError as exc:
        raise SendRefused(NO_CONNECTION_FORMAT.format(reason=exc.reason)) from exc
    except OSError as exc:
        raise SendRefused(NO_CONNECTION_FORMAT.format(reason=exc)) from exc


def image_bytes(post: Any) -> bytes:
    """The venue image ``post.image_path`` names, or ``SendRefused`` where none is on disk."""
    path = str(getattr(post, "image_path", "") or "")
    if not path:
        raise SendRefused(NO_IMAGE_FORMAT.format(path=path))
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise SendRefused(NO_IMAGE_FORMAT.format(path=path)) from exc


def retry_after_seconds(body: dict, nested: Any = None) -> float:
    """``retry_after`` off a 429 body, or off its ``nested`` key where the venue nests it."""
    held = body
    if nested is not None and isinstance(body.get(nested), dict):
        held = body[nested]
    try:
        return float(held.get(RETRY_AFTER_KEY, NO_RETRY_AFTER))
    except (TypeError, ValueError):
        return NO_RETRY_AFTER


def refuse(answer: SendAnswer, said: str, nested: Any = None) -> SendRefused:
    """The ``SendRefused`` one venue answer earns: a 429 names its wait, a 401
    or 403 names the credential, anything else names the status and ``said``."""
    if answer.http == HTTP_TOO_MANY_REQUESTS:
        return SendRefused(
            RATE_LIMITED_FORMAT.format(
                seconds=retry_after_seconds(answer.body, nested)
            ),
            answer.http,
        )
    said = said or VENUE_SAID_NOTHING_TEXT
    if answer.http in CREDENTIAL_REFUSED_CODES:
        return SendRefused(
            CREDENTIAL_REFUSED_FORMAT.format(http=answer.http, said=said), answer.http
        )
    return SendRefused(
        HTTP_REFUSED_FORMAT.format(http=answer.http, said=said), answer.http
    )


def parse_webhook(webhook_url: Any) -> tuple:
    """The id and the token one Discord webhook URL carries, by ``DISCORD_WEBHOOK_PATTERN``."""
    found = DISCORD_WEBHOOK_PATTERN.match(str(webhook_url or "").strip())
    if found is None:
        raise SendRefused(
            WRONG_SHAPE_FORMAT.format(label="webhook URL", form=DISCORD_WEBHOOK_FORM)
        )
    return found.group("id"), found.group("token")


def check_telegram_credential(credential: dict) -> tuple:
    """The bot token and the chat id one typed Telegram credential carries,
    each checked against the form its own page prints."""
    token = str(credential.get(ata_spm_push.TELEGRAM_BOT_FIELD, "") or "").strip()
    chat_id = str(credential.get(ata_spm_push.TELEGRAM_CHAT_FIELD, "") or "").strip()
    if TELEGRAM_BOT_PATTERN.match(token) is None:
        raise SendRefused(
            WRONG_SHAPE_FORMAT.format(label="bot token", form=TELEGRAM_BOT_FORM)
        )
    if TELEGRAM_CHAT_PATTERN.match(chat_id) is None:
        raise SendRefused(
            WRONG_SHAPE_FORMAT.format(label="chat id", form=TELEGRAM_CHAT_FORM)
        )
    return token, chat_id


def send_discord(post: Any, credential: dict, transport: Callable) -> SendOutcome:
    """Execute the channel's webhook with ``post.body`` as ``content`` and the
    venue image as ``files[0]``, and answer the message Discord created."""
    webhook_id, token = parse_webhook(
        credential.get(ata_spm_push.DISCORD_WEBHOOK_FIELD)
    )
    content = image_bytes(post)
    filename = Path(str(post.image_path)).name
    request = SendRequest(
        url="{base}/{id}/{token}?{query}".format(
            base=DISCORD_API_BASE, id=webhook_id, token=token, query=DISCORD_WAIT_QUERY
        ),
        fields={DISCORD_PAYLOAD_FIELD: json.dumps({DISCORD_CONTENT_KEY: post.body})},
        file_field=DISCORD_FILE_FIELD,
        filename=filename,
        content=content,
    )
    params = {
        PARAM_TEXT_CHARS: len(post.body),
        PARAM_IMAGE_BYTES: len(content),
        PARAM_IMAGE_NAME: filename,
        PARAM_WAIT: True,
    }
    answer = transport(request)
    if answer.http != HTTP_OK:
        raise refuse(answer, str(answer.body.get(DISCORD_MESSAGE_KEY, "") or ""))
    message_id = str(answer.body.get(DISCORD_ID_KEY, "") or "")
    if not message_id:
        raise SendRefused(
            NO_MESSAGE_ID_FORMAT.format(target=ata_spm_push.TARGET_DISCORD), answer.http
        )
    return SendOutcome(
        destination=DESTINATION_FORMAT.format(
            place=DISCORD_PLACE,
            place_id=str(answer.body.get(DISCORD_CHANNEL_KEY, "") or NO_PLACE_ID),
            message_id=message_id,
        ),
        message_id=message_id,
        http=answer.http,
        params=params,
    )


def send_telegram(post: Any, credential: dict, transport: Callable) -> SendOutcome:
    """Call ``sendPhoto`` with the venue image as ``photo`` and ``post.body`` as
    its ``caption``, and answer the message Telegram created."""
    token, chat_id = check_telegram_credential(credential)
    content = image_bytes(post)
    filename = Path(str(post.image_path)).name
    request = SendRequest(
        url="{base}/{bot}/{method}".format(
            base=TELEGRAM_API_BASE,
            bot=TELEGRAM_BOT_PATH_FORMAT.format(token=token),
            method=TELEGRAM_SEND_PHOTO,
        ),
        fields={TELEGRAM_CHAT_FIELD: chat_id, TELEGRAM_CAPTION_FIELD: post.body},
        file_field=TELEGRAM_PHOTO_FIELD,
        filename=filename,
        content=content,
    )
    params = {
        PARAM_CHAT_ID: chat_id,
        PARAM_TEXT_CHARS: len(post.body),
        PARAM_IMAGE_BYTES: len(content),
        PARAM_IMAGE_NAME: filename,
    }
    answer = transport(request)
    if answer.http != HTTP_OK or not answer.body.get(TELEGRAM_OK_KEY):
        raise refuse(
            answer,
            str(answer.body.get(TELEGRAM_DESCRIPTION_KEY, "") or ""),
            TELEGRAM_PARAMETERS_KEY,
        )
    result = answer.body.get(TELEGRAM_RESULT_KEY)
    result = result if isinstance(result, dict) else {}
    message_id = str(result.get(TELEGRAM_MESSAGE_ID_KEY, "") or "")
    if not message_id:
        raise SendRefused(
            NO_MESSAGE_ID_FORMAT.format(target=ata_spm_push.TARGET_TELEGRAM),
            answer.http,
        )
    chat = result.get(TELEGRAM_CHAT_KEY)
    chat = chat if isinstance(chat, dict) else {}
    return SendOutcome(
        destination=DESTINATION_FORMAT.format(
            place=TELEGRAM_PLACE,
            place_id=str(chat.get(DISCORD_ID_KEY, "") or chat_id),
            message_id=message_id,
        ),
        message_id=message_id,
        http=answer.http,
        params=params,
    )


#: One route per venue whose post leaves through its API. A target absent
#: here takes the folder or the intent route, whatever the vault holds.
SEND_ROUTES = {
    ata_spm_push.TARGET_DISCORD: send_discord,
    ata_spm_push.TARGET_TELEGRAM: send_telegram,
}

#: What each route's ``APIInteractionLog`` block names.
API_ACTIONS = {
    ata_spm_push.TARGET_DISCORD: (DISCORD_ACTION, DISCORD_LOGGED_ENDPOINT),
    ata_spm_push.TARGET_TELEGRAM: (TELEGRAM_ACTION, TELEGRAM_LOGGED_ENDPOINT),
}


def record_api(
    target: str, post: Any, result: str, elapsed_ms: float, level: str, params: dict
) -> None:
    """One ``APIInteractionLog`` block for a send, which the Live tab's API
    Interaction Log draws; the endpoint names the route with no token."""
    from ..exchange.api_logger import get_api_log

    action, endpoint = API_ACTIONS.get(target, (target, ""))
    get_api_log().record(
        exchange=str(target).lower(),
        action=action,
        reason=API_REASON_FORMAT.format(
            symbol=post.symbol, label=ata_spm.timeframe_label(post.timeframe)
        ),
        endpoint=endpoint,
        params=dict(params),
        result=result,
        elapsed_ms=elapsed_ms,
        level=level,
        data_usage=SEND_DATA_USAGE,
    )


class ApiSender:
    """What ``PushBoard.set_sender`` takes: ``__call__`` posts one
    ``FormattedPost`` through its ``SEND_ROUTES`` row and answers the
    destination, and ``targets`` names the venues it takes so ``route_for``
    leaves every other venue on its folder or intent route.
    """

    def __init__(self, settings: Any, transport: Callable = urlopen_multipart) -> None:
        self.settings = settings
        self.transport = transport
        self.targets = tuple(SEND_ROUTES)

    def __call__(self, post: Any) -> str:
        """Send one post and answer the destination, or raise ``SendRefused``."""
        target = str(post.target)
        route = SEND_ROUTES.get(target)
        if route is None:
            raise SendRefused(NO_SEND_ROUTE_FORMAT.format(target=target))
        credential = dict(self.settings.typed_credential(target))
        empty = ata_spm_push.missing_value(target, credential)
        if empty is not None:
            raise SendRefused(
                ata_spm_push.MISSING_FIELD_FORMAT.format(label=empty.label)
            )
        started = time.monotonic()
        try:
            outcome = route(post, credential, self.transport)
        except SendRefused as exc:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            logger.warning(
                SEND_REFUSED_LOG, target, post.symbol, post.timeframe, exc.detail
            )
            record_api(
                target,
                post,
                API_REFUSED_FORMAT.format(detail=exc.detail),
                elapsed_ms,
                API_LEVEL_ERROR,
                {},
            )
            self._emit(post, False, exc.http, "", exc.detail, elapsed_ms)
            raise
        elapsed_ms = (time.monotonic() - started) * 1000.0
        logger.info(SEND_LOG, target, post.symbol, post.timeframe, outcome.destination)
        record_api(
            target,
            post,
            API_SENT_FORMAT.format(http=outcome.http, message_id=outcome.message_id),
            elapsed_ms,
            API_LEVEL_INFO,
            outcome.params,
        )
        self._emit(post, True, outcome.http, outcome.message_id, "", elapsed_ms)
        return outcome.destination

    @staticmethod
    def _emit(
        post: Any,
        sent: bool,
        http: int,
        message_id: str,
        detail: str,
        elapsed_ms: float,
    ) -> None:
        _pin_emit(
            SENT_PIN,
            actual=message_id if sent else detail,
            ok=sent,
            context={
                "venue": post.target,
                "symbol": post.symbol,
                "timeframe": post.timeframe,
                "http": http,
                "message_id": message_id,
                "detail": detail,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )


def build_sender(settings: Any, transport: Optional[Callable] = None) -> ApiSender:
    """The ``ApiSender`` one host hands ``PushBoard.set_sender``, reading its
    credentials off ``settings`` and posting through ``transport``."""
    return ApiSender(
        settings, transport if transport is not None else urlopen_multipart
    )


__all__ = [
    "ApiSender",
    "DISCORD_API_BASE",
    "DISCORD_WEBHOOK_PATTERN",
    "SEND_ROUTES",
    "SENT_PIN",
    "SendAnswer",
    "SendOutcome",
    "SendRefused",
    "SendRequest",
    "TELEGRAM_API_BASE",
    "TELEGRAM_BOT_PATTERN",
    "TELEGRAM_CHAT_PATTERN",
    "build_sender",
    "check_telegram_credential",
    "multipart_body",
    "parse_webhook",
    "send_discord",
    "send_telegram",
    "urlopen_multipart",
]
