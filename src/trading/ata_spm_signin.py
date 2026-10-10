"""ata_spm_signin.py -- one sign-in route per ATA-SPM push target and per
browser-authorization trading venue.

``SIGN_IN_ROUTES`` maps one target or venue id to the route that signs it in,
and ``BROWSER_AUTHORIZATION_VENUES`` names the venue ids among them.
``REDIRECT_POLICIES`` carries the redirect address each venue's own
documentation accepts, and ``LoopbackReceiver`` opens only for a venue that
takes an RFC 8252 address. ``build_connector`` wraps the map into the one
callable ``AtaSpmSettings.set_connector`` takes, and no route reaches a venue
itself -- each sends through ``SignInSession.transport``.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import logging
import secrets
import threading
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import ata_spm_push, ata_spm_send

logger = logging.getLogger("acervator.ata_spm_signin")

#: The only address ``LoopbackReceiver`` binds. A wider bind would put the
#: authorization code on the network, and no caller can name a host.
LOOPBACK_HOST = "127.0.0.1"

#: The operating system chooses the port, which RFC 8252 section 7.3 asks for.
#: Only LinkedIn and TikTok publish a redirect rule that accepts a port that
#: changes on every press.
EPHEMERAL_PORT = 0

#: The one loopback port every exact-match venue binds. X, Instagram, Threads
#: and Reddit each check the redirect against a registered address character for
#: character and publish no wildcard, so the program declares one port, prints
#: it on Level 1A, and binds the same one every press. No venue publishes a
#: number, so this is a local choice with nothing to read it against.
FIXED_CALLBACK_PORT = 8723

#: The path every loopback redirect carries, which each venue's own example
#: also carries.
CALLBACK_PATH = "/callback"

#: The three wordings ``RedirectPolicy.register_as`` takes for a loopback venue.
#: TikTok publishes the wildcard port; LinkedIn's native page asks for no
#: registration at all.
LOOPBACK_ADDRESS_FORMAT = "http://127.0.0.1:{port}{path}"
WILDCARD_PORT_FORMAT = "http://127.0.0.1:*{path}"
ANY_LOOPBACK_PORT_TEXT = (
    "nothing; LinkedIn's native page asks for no registered address and takes "
    "any loopback port"
)

CALLBACK_TIMEOUT_SECONDS = 180.0
TRANSPORT_TIMEOUT_SECONDS = 30.0

#: The whole scheme allowlist ``urlopen_transport`` hands ``SafeRequest``. Every
#: venue address below is https, so nothing else is permitted to be sent.
HTTPS_SCHEME = "https"

CODE_PARAM = "code"
STATE_PARAM = "state"
ERROR_PARAM = "error"
ERROR_DESCRIPTION_PARAM = "error_description"
REDIRECT_PARAM = "redirect_uri"

CHALLENGE_METHOD_S256 = "S256"
RESPONSE_TYPE_CODE = "code"
#: Meta's manual-flow page states a desktop app asks for this ``response_type``
#: instead of a code, because its desktop redirect answers in the fragment of
#: the address the view lands on.
DESKTOP_RESPONSE_TYPE = "token"
GRANT_AUTHORIZATION_CODE = "authorization_code"

METHOD_GET = "GET"
METHOD_POST = "POST"

FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
CONTENT_TYPE_HEADER = "Content-Type"
USER_AGENT_HEADER = "User-Agent"
ACCEPT_HEADER = "Accept"
JSON_ACCEPT = "application/json"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
LENGTH_HEADER = "Content-Length"
AUTHORIZATION_HEADER = "Authorization"

CALLBACK_PAGE_BODY = (
    "<html><body><p>Acervator has the sign-in. "
    "Close this tab and return to the program.</p></body></html>"
)
CALLBACK_REFUSED_BODY = "<html><body><p>Refused.</p></body></html>"

CALLBACK_OK_STATUS = 200
CALLBACK_REFUSED_STATUS = 400

#: Bytes of entropy behind ``new_state`` and ``new_verifier``. RFC 7636 fixes the
#: verifier between 43 and 128 characters, which 32 bytes satisfies.
STATE_BYTES = 32
VERIFIER_BYTES = 32

SCOPE_SEPARATOR = " "
COMMA_SEPARATOR = ","
QUERY_MARK = "?"

NO_CALLBACK_TEXT = "no reply came back from the browser"
WRONG_STATE_TEXT = "the browser came back with a state this sign-in did not send"
NO_CODE_TEXT = "the browser came back with no authorization code"
NO_FIELD_FORMAT = "the venue answered with no {field}"
NO_PAGE_TEXT = "the account administers no Page"
NO_ROUTE_FORMAT = "No sign-in route for {target}."
PORT_BUSY_FORMAT = (
    "port {port} on 127.0.0.1 is already taken, and this venue matches the one "
    "address registered with it"
)
NOT_LOOPBACK_FORMAT = "this venue redirects to {address}, so no listener opens"
NO_VIEW_TEXT = (
    "this venue answers only inside a sign-in view the program draws, and none "
    "is wired"
)
IS_LOOPBACK_TEXT = "this venue redirects to a loopback address, which needs no view"
#: Carries the host and never the address. A venue answering at its own desktop
#: redirect puts its token in the fragment of that address.
WRONG_HOST_FORMAT = "the sign-in view reached {host}, which is not the venue"
NO_POLICY_FORMAT = "No redirect address for {target}."

#: How much of a refusal body ``refusal_text`` reads. RFC 6749 section 5.2 puts
#: the whole reason in two short fields, so anything past this is not one.
REFUSAL_BODY_LIMIT = 4096

#: What Level 1A prints when a venue refuses. ``VENUE_SAID_FORMAT`` carries the
#: venue's own reason, without which the page names only the status.
HTTP_REFUSAL_FORMAT = "HTTP {status} {reason}"
VENUE_SAID_FORMAT = "{http}, and the venue said {said}"
VENUE_REASON_FORMAT = "{error}: {description}"

CALLBACK_LOG = "ATA-SPM sign-in callback refused: %s"
REFUSAL_BODY_LOG = "ATA-SPM sign-in refusal body unread: %s"


class SignInError(Exception):
    """A venue, a browser or ``LoopbackReceiver`` stopped one sign-in short."""


@dataclass(frozen=True)
class SignInRequest:
    """One call a route makes, and the only shape ``SignInSession.transport`` takes.

    ``params`` is the query string, ``data`` the form body, ``json_body`` a JSON
    body in place of ``data``, and ``basic_auth`` the user and password of an
    HTTP Basic header.
    """

    method: str
    url: str
    params: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    basic_auth: tuple = ()
    json_body: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RedirectPolicy:
    """The redirect address one venue's own documentation accepts.

    ``loopback`` true means the venue takes an RFC 8252 address, and
    ``LoopbackReceiver`` binds ``port`` and serves ``path``. False means the
    venue publishes its own desktop ``address`` and no listener opens at all.
    ``register_as`` is what Level 1A prints for what he registers at the venue.
    """

    loopback: bool
    port: int = FIXED_CALLBACK_PORT
    path: str = CALLBACK_PATH
    address: str = ""
    register_as: str = ""


#: What ``registered_redirect`` answers for a name ``REDIRECT_POLICIES`` has no
#: row for, so the page prints an empty wording and never an address.
NO_POLICY_ROW = RedirectPolicy(loopback=False)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Answers the one redirect ``LoopbackReceiver.wait`` waits for."""

    def do_GET(self) -> None:
        """Record the callback query and answer the browser once."""
        held = urllib.parse.urlsplit(self.path).query
        self.server.callback_query = dict(urllib.parse.parse_qsl(held))
        sent = str(self.server.callback_query.get(STATE_PARAM, ""))
        good = secrets.compare_digest(sent, str(self.server.expected_state))
        self.server.callback_state_ok = good
        body = (CALLBACK_PAGE_BODY if good else CALLBACK_REFUSED_BODY).encode()
        self.send_response(CALLBACK_OK_STATUS if good else CALLBACK_REFUSED_STATUS)
        self.send_header(CONTENT_TYPE_HEADER, HTML_CONTENT_TYPE)
        self.send_header(LENGTH_HEADER, str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        """``_CallbackHandler`` writes no log line."""


class LoopbackReceiver:
    """The one-shot ``127.0.0.1`` listener RFC 8252 names for a native app.

    ``open`` binds ``LOOPBACK_HOST`` at the port it was built with, and ``wait``
    serves exactly one request, checks the ``state`` it was built with, and
    closes. ``EPHEMERAL_PORT`` lets the operating system choose; a venue that
    matches its registered address exactly names a fixed port instead.
    """

    def __init__(self, state: str, path: str = "", port: int = EPHEMERAL_PORT) -> None:
        self.state = str(state)
        self.path = str(path)
        self.port = int(port)
        self._server: Any = None

    def open(self) -> str:
        """Bind the listener and answer the ``redirect_uri`` it now serves.

        A fixed port already in use raises ``SignInError``, because the venue
        accepts no other address.
        """
        try:
            self._server = http.server.HTTPServer(
                (LOOPBACK_HOST, self.port), _CallbackHandler
            )
        except OSError as exc:
            raise SignInError(PORT_BUSY_FORMAT.format(port=self.port)) from exc
        self._server.expected_state = self.state
        self._server.callback_query = {}
        self._server.callback_state_ok = False
        return self.redirect_uri

    @property
    def redirect_uri(self) -> str:
        """The loopback address the venue redirects to, at the port ``open`` bound."""
        if self._server is None:
            return ""
        return "http://{host}:{port}{path}".format(
            host=LOOPBACK_HOST, port=self._server.server_address[1], path=self.path
        )

    def wait(self, timeout: float = CALLBACK_TIMEOUT_SECONDS) -> dict:
        """Serve one request and answer its query, or raise ``SignInError``.

        A ``state`` this receiver did not generate is refused, and a timeout
        with no callback at all is refused the same way.
        """
        if self._server is None:
            raise SignInError(NO_CALLBACK_TEXT)
        self._server.timeout = float(timeout)
        served = threading.Thread(
            target=self._server.handle_request, daemon=True, name="ata-spm-signin"
        )
        served.start()
        served.join(float(timeout))
        try:
            held = dict(self._server.callback_query)
            good = bool(self._server.callback_state_ok)
        finally:
            self.close()
        if not held:
            raise SignInError(NO_CALLBACK_TEXT)
        if not good:
            logger.debug(CALLBACK_LOG, WRONG_STATE_TEXT)
            raise SignInError(WRONG_STATE_TEXT)
        if held.get(ERROR_PARAM):
            raise SignInError(
                str(held.get(ERROR_DESCRIPTION_PARAM) or held[ERROR_PARAM])
            )
        if not held.get(CODE_PARAM):
            raise SignInError(NO_CODE_TEXT)
        return held

    def close(self) -> None:
        """Shut the listener ``open`` bound, whether or not a callback arrived."""
        if self._server is None:
            return
        self._server.server_close()
        self._server = None


def new_state() -> str:
    """One ``state`` value per sign-in, checked back in ``LoopbackReceiver.wait``."""
    return secrets.token_urlsafe(STATE_BYTES)


def new_verifier() -> str:
    """One PKCE ``code_verifier``, sized by ``VERIFIER_BYTES`` per RFC 7636."""
    return secrets.token_urlsafe(VERIFIER_BYTES)


def code_challenge(verifier: str) -> str:
    """The ``CHALLENGE_METHOD_S256`` challenge one ``new_verifier`` value produces."""
    digest = hashlib.sha256(str(verifier).encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def open_in_browser(url: str) -> None:
    """Open one authorize address through ``webbrowser``, the system browser."""
    import webbrowser

    webbrowser.open(str(url), new=2)


def venue_reason(answered: Any) -> str:
    """``ERROR_PARAM`` and ``ERROR_DESCRIPTION_PARAM`` out of one refusal body.

    ``VENUE_REASON_FORMAT`` joins the two, and no other value the venue
    answered is read out.
    """
    held = dict(answered or {})
    code = str(held.get(ERROR_PARAM, "") or "").strip()
    said = str(held.get(ERROR_DESCRIPTION_PARAM, "") or "").strip()
    if code and said:
        return VENUE_REASON_FORMAT.format(error=code, description=said)
    return said or code


def refusal_text(error: Any) -> str:
    """``HTTP_REFUSAL_FORMAT`` for one refusal, with ``venue_reason`` inside it.

    A body no longer than ``REFUSAL_BODY_LIMIT`` is read, and one that is not
    JSON leaves ``HTTP_REFUSAL_FORMAT`` alone.
    """
    import json

    held = HTTP_REFUSAL_FORMAT.format(
        status=getattr(error, "code", ""), reason=getattr(error, "reason", "")
    )
    try:
        answered = json.loads(bytes(error.read(REFUSAL_BODY_LIMIT)).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - the body is venue-supplied
        logger.debug(REFUSAL_BODY_LOG, exc)
        return held
    said = venue_reason(answered)
    return VENUE_SAID_FORMAT.format(http=held, said=said) if said else held


def urlopen_transport(request: SignInRequest) -> dict:
    """Send one ``SignInRequest`` through ``safe_urlopen`` and answer its JSON.

    ``HTTPS_SCHEME`` is the whole allowlist handed to ``SafeRequest``, which
    narrows the default and refuses every other scheme at construction, and a
    venue refusing raises ``SignInError`` carrying ``refusal_text``.
    """
    import json

    from ..core.safe_url import SafeRequest, safe_urlopen

    address = str(request.url)
    if request.params:
        address = address + QUERY_MARK + urllib.parse.urlencode(request.params)
    body = urllib.parse.urlencode(request.data).encode() if request.data else None
    if request.json_body:
        body = json.dumps(dict(request.json_body)).encode()
    sent = SafeRequest(address, allowed_schemes=(HTTPS_SCHEME,))
    for name, value in request.headers.items():
        sent.add_header(str(name), str(value))
    if request.basic_auth:
        pair = "{user}:{password}".format(
            user=request.basic_auth[0], password=request.basic_auth[1]
        )
        sent.add_header(
            AUTHORIZATION_HEADER, "Basic " + base64.b64encode(pair.encode()).decode()
        )
    sent.method = str(request.method)
    try:
        with safe_urlopen(
            sent,
            body,
            timeout=TRANSPORT_TIMEOUT_SECONDS,
            allowed_schemes=(HTTPS_SCHEME,),
        ) as answered:
            return dict(json.loads(answered.read().decode()))
    except urllib.error.HTTPError as exc:
        raise SignInError(refusal_text(exc)) from exc


@dataclass
class SignInSession:
    """What one sign-in is driven through: ``transport``, ``browser``, ``receiver``.

    A stub for each drives every route in ``SIGN_IN_ROUTES`` with nothing
    leaving the machine.
    """

    transport: Callable
    browser: Callable = open_in_browser
    receiver: Callable = LoopbackReceiver
    view: Optional[Callable] = None
    state_source: Callable = new_state
    verifier_source: Callable = new_verifier
    timeout: float = CALLBACK_TIMEOUT_SECONDS

    def approve(
        self, authorize_url: str, params: dict, policy: RedirectPolicy
    ) -> tuple:
        """Run the RFC 8252 approval leg and answer the code and redirect address.

        ``LoopbackReceiver.open`` runs first, at the port and path ``policy``
        names, and fixes the ``REDIRECT_PARAM`` value the ``browser`` call
        carries. A policy that is not loopback opens no listener and raises.
        """
        if not policy.loopback:
            raise SignInError(NOT_LOOPBACK_FORMAT.format(address=policy.address))
        state = str(self.state_source())
        held = self.receiver(state, policy.path, policy.port)
        redirect_uri = held.open()
        sent = dict(params)
        sent[STATE_PARAM] = state
        sent[REDIRECT_PARAM] = redirect_uri
        try:
            self.browser(authorize_url + QUERY_MARK + urllib.parse.urlencode(sent))
            answered = held.wait(self.timeout)
        finally:
            held.close()
        return str(answered[CODE_PARAM]), redirect_uri

    def approve_at_view(
        self, authorize_url: str, params: dict, policy: RedirectPolicy
    ) -> dict:
        """Approve at a venue-published desktop address, and answer its fragment.

        No listener opens and no browser opens. ``view`` drives the venue's own
        page to ``policy.address`` and answers the address it landed on, whose
        fragment carries what the venue issued.
        """
        if policy.loopback:
            raise SignInError(IS_LOOPBACK_TEXT)
        if self.view is None:
            raise SignInError(NO_VIEW_TEXT)
        state = str(self.state_source())
        sent = dict(params)
        sent[STATE_PARAM] = state
        sent[REDIRECT_PARAM] = policy.address
        landed = self.view(
            authorize_url + QUERY_MARK + urllib.parse.urlencode(sent), policy.address
        )
        host = landed_host(landed)
        if not host:
            raise SignInError(NO_CALLBACK_TEXT)
        if host not in sign_in_hosts(authorize_url, policy.address):
            logger.debug(CALLBACK_LOG, WRONG_HOST_FORMAT.format(host=host))
            raise SignInError(WRONG_HOST_FORMAT.format(host=host))
        held = read_fragment(landed)
        if held.get(ERROR_PARAM):
            raise SignInError(
                str(held.get(ERROR_DESCRIPTION_PARAM) or held[ERROR_PARAM])
            )
        if not held:
            raise SignInError(NO_CALLBACK_TEXT)
        if not secrets.compare_digest(str(held.get(STATE_PARAM, "")), state):
            logger.debug(CALLBACK_LOG, WRONG_STATE_TEXT)
            raise SignInError(WRONG_STATE_TEXT)
        return held


def read_fragment(landed: Any) -> dict:
    """The fragment values of one landed address, which is where Meta answers.

    A fragment never leaves the browser, so only a view the program draws can
    read one.
    """
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(str(landed)).fragment))


def landed_host(landed: Any) -> str:
    """The host of one landed address, lowercased.

    ``WRONG_HOST_FORMAT`` carries this and never the address itself.
    """
    return str(urllib.parse.urlsplit(str(landed)).netloc).lower()


def sign_in_hosts(authorize_url: Any, redirect_address: Any) -> tuple:
    """The hosts one ``approve_at_view`` sign-in may reach, in the order given.

    They are the hosts of the two addresses that sign-in was built from, and
    ``approve_at_view`` refuses a landing on any other.
    """
    held: list = []
    for one in (authorize_url, redirect_address):
        host = landed_host(one)
        if host and host not in held:
            held.append(host)
    return tuple(held)


def is_redirect_landing(landed: Any, redirect_address: Any) -> bool:
    """True where one landed address is the published redirect, fragment aside.

    A venue answering at its own desktop redirect adds the fragment, so the
    scheme, the host and the path are what identify the landing.
    """
    held = urllib.parse.urlsplit(str(landed))
    sent = urllib.parse.urlsplit(str(redirect_address))
    return (held.scheme, held.netloc.lower(), held.path) == (
        sent.scheme,
        sent.netloc.lower(),
        sent.path,
    )


def read_field(answered: Any, key: str, label: str = "") -> str:
    """One value out of a venue's reply, raising ``SignInError`` where absent."""
    held = str(dict(answered or {}).get(key, "") or "")
    if not held:
        raise SignInError(NO_FIELD_FORMAT.format(field=label or key))
    return held


# ── X ────────────────────────────────────────────────────────────────
X_AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
X_EXCHANGE_URL = "https://api.x.com/2/oauth2/token"


def sign_in_x(typed: dict, session: SignInSession) -> dict:
    """X's authorization code flow, from ``X_AUTHORIZE_URL`` to ``X_EXCHANGE_URL``.

    X takes ``code_verifier`` on the token call and authenticates a confidential
    client by HTTP Basic.
    """
    verifier = str(session.verifier_source())
    client_id = str(typed.get("x-client-id", ""))
    code, redirect_uri = session.approve(
        X_AUTHORIZE_URL,
        {
            "response_type": RESPONSE_TYPE_CODE,
            "client_id": client_id,
            "scope": SCOPE_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_X)
            ),
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": CHALLENGE_METHOD_S256,
        },
        redirect_policy(ata_spm_push.TARGET_X),
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=X_EXCHANGE_URL,
            data={
                "grant_type": GRANT_AUTHORIZATION_CODE,
                "code": code,
                "client_id": client_id,
                REDIRECT_PARAM: redirect_uri,
                "code_verifier": verifier,
            },
            headers={CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE},
            basic_auth=(client_id, str(typed.get("x-client-secret", ""))),
        )
    )
    return {
        "x-access-token": read_field(answered, "access_token"),
        "x-refresh-token": read_field(answered, "refresh_token"),
    }


# ── Instagram ────────────────────────────────────────────────────────
INSTAGRAM_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_EXCHANGE_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_LONG_LIVED_URL = "https://graph.instagram.com/access_token"
INSTAGRAM_EXCHANGE_GRANT = "ig_exchange_token"


def sign_in_instagram(typed: dict, session: SignInSession) -> dict:
    """Instagram Business Login, then ``INSTAGRAM_LONG_LIVED_URL`` for sixty days.

    Instagram runs the flow across three hosts, and only the long-lived token
    is answered.
    """
    secret = str(typed.get("instagram-client-secret", ""))
    client_id = str(typed.get("instagram-client-id", ""))
    code, redirect_uri = session.approve(
        INSTAGRAM_AUTHORIZE_URL,
        {
            "client_id": client_id,
            "response_type": RESPONSE_TYPE_CODE,
            "scope": COMMA_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_INSTAGRAM)
            ),
        },
        redirect_policy(ata_spm_push.TARGET_INSTAGRAM),
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=INSTAGRAM_EXCHANGE_URL,
            data={
                "client_id": client_id,
                "client_secret": secret,
                "grant_type": GRANT_AUTHORIZATION_CODE,
                REDIRECT_PARAM: redirect_uri,
                "code": code,
            },
            headers={CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE},
        )
    )
    long_lived = session.transport(
        SignInRequest(
            method=METHOD_GET,
            url=INSTAGRAM_LONG_LIVED_URL,
            params={
                "grant_type": INSTAGRAM_EXCHANGE_GRANT,
                "client_secret": secret,
                "access_token": read_field(answered, "access_token"),
            },
            headers={ACCEPT_HEADER: JSON_ACCEPT},
        )
    )
    return {
        "instagram-user-id": read_field(answered, "user_id"),
        "instagram-access-token": read_field(long_lived, "access_token"),
    }


# ── LinkedIn ─────────────────────────────────────────────────────────
LINKEDIN_AUTHORIZE_URL = "https://www.linkedin.com/oauth/native-pkce/authorization"
LINKEDIN_EXCHANGE_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def sign_in_linkedin(typed: dict, session: SignInSession) -> dict:
    """LinkedIn's native-client flow at ``LINKEDIN_AUTHORIZE_URL``, loopback only.

    That address takes no client secret, and ``code_verifier`` stands in its
    place at ``LINKEDIN_EXCHANGE_URL``.
    """
    verifier = str(session.verifier_source())
    client_id = str(typed.get("linkedin-client-id", ""))
    code, redirect_uri = session.approve(
        LINKEDIN_AUTHORIZE_URL,
        {
            "response_type": RESPONSE_TYPE_CODE,
            "client_id": client_id,
            "scope": SCOPE_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_LINKEDIN)
            ),
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": CHALLENGE_METHOD_S256,
        },
        redirect_policy(ata_spm_push.TARGET_LINKEDIN),
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=LINKEDIN_EXCHANGE_URL,
            data={
                "grant_type": GRANT_AUTHORIZATION_CODE,
                "code": code,
                REDIRECT_PARAM: redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
            headers={CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE},
        )
    )
    return {"linkedin-access-token": read_field(answered, "access_token")}


# ── TikTok ───────────────────────────────────────────────────────────
TIKTOK_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_EXCHANGE_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def sign_in_tiktok(typed: dict, session: SignInSession) -> dict:
    """TikTok's flow at ``TIKTOK_AUTHORIZE_URL``, whose client field is ``client_key``.

    TikTok states ``code_verifier`` is required for a desktop program.
    """
    verifier = str(session.verifier_source())
    client_key = str(typed.get("tiktok-client-key", ""))
    code, redirect_uri = session.approve(
        TIKTOK_AUTHORIZE_URL,
        {
            "client_key": client_key,
            "response_type": RESPONSE_TYPE_CODE,
            "scope": COMMA_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_TIKTOK)
            ),
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": CHALLENGE_METHOD_S256,
        },
        redirect_policy(ata_spm_push.TARGET_TIKTOK),
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=TIKTOK_EXCHANGE_URL,
            data={
                "client_key": client_key,
                "client_secret": str(typed.get("tiktok-client-secret", "")),
                "code": urllib.parse.unquote(code),
                "grant_type": GRANT_AUTHORIZATION_CODE,
                REDIRECT_PARAM: redirect_uri,
                "code_verifier": verifier,
            },
            headers={CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE},
        )
    )
    return {
        "tiktok-open-id": read_field(answered, "open_id"),
        "tiktok-access-token": read_field(answered, "access_token"),
        "tiktok-refresh-token": read_field(answered, "refresh_token"),
    }


# ── Facebook ─────────────────────────────────────────────────────────
FACEBOOK_GRAPH_VERSION = "v25.0"
FACEBOOK_AUTHORIZE_URL = "https://www.facebook.com/{version}/dialog/oauth"
FACEBOOK_EXCHANGE_URL = "https://graph.facebook.com/{version}/oauth/access_token"
FACEBOOK_ACCOUNTS_URL = "https://graph.facebook.com/{version}/me/accounts"
FACEBOOK_EXCHANGE_GRANT = "fb_exchange_token"

#: Meta's manual-flow page names this address for a desktop app, and Meta's
#: Login Security page requires HTTPS for every OAuth redirect. A loopback
#: address is neither published nor excepted, so no listener opens here.
FACEBOOK_DESKTOP_REDIRECT = "https://www.facebook.com/connect/login_success.html"


def sign_in_facebook(typed: dict, session: SignInSession) -> dict:
    """Facebook's desktop login, ``FACEBOOK_EXCHANGE_GRANT``, then the Page token.

    ``approve_at_view`` answers the fragment of ``FACEBOOK_DESKTOP_REDIRECT``,
    which carries a short-lived user token that ``FACEBOOK_EXCHANGE_GRANT``
    trades up before ``FACEBOOK_ACCOUNTS_URL`` lists the Page.
    """
    app_id = str(typed.get("facebook-app-id", ""))
    secret = str(typed.get("facebook-app-secret", ""))
    landed = session.approve_at_view(
        FACEBOOK_AUTHORIZE_URL.format(version=FACEBOOK_GRAPH_VERSION),
        {
            "client_id": app_id,
            "response_type": DESKTOP_RESPONSE_TYPE,
            "scope": COMMA_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_FACEBOOK)
            ),
        },
        redirect_policy(ata_spm_push.TARGET_FACEBOOK),
    )
    long_lived = session.transport(
        SignInRequest(
            method=METHOD_GET,
            url=FACEBOOK_EXCHANGE_URL.format(version=FACEBOOK_GRAPH_VERSION),
            params={
                "grant_type": FACEBOOK_EXCHANGE_GRANT,
                "client_id": app_id,
                "client_secret": secret,
                FACEBOOK_EXCHANGE_GRANT: read_field(landed, "access_token"),
            },
            headers={ACCEPT_HEADER: JSON_ACCEPT},
        )
    )
    pages = session.transport(
        SignInRequest(
            method=METHOD_GET,
            url=FACEBOOK_ACCOUNTS_URL.format(version=FACEBOOK_GRAPH_VERSION),
            params={"access_token": read_field(long_lived, "access_token")},
            headers={ACCEPT_HEADER: JSON_ACCEPT},
        )
    )
    listed = list(dict(pages or {}).get("data") or [])
    if not listed:
        raise SignInError(NO_PAGE_TEXT)
    return {
        "facebook-page-id": read_field(listed[0], "id", "Page id"),
        "facebook-page-token": read_field(listed[0], "access_token", "Page token"),
    }


# ── Threads ──────────────────────────────────────────────────────────
THREADS_AUTHORIZE_URL = "https://threads.com/oauth/authorize"
THREADS_EXCHANGE_URL = "https://graph.threads.com/oauth/access_token"
THREADS_LONG_LIVED_URL = "https://graph.threads.net/access_token"
THREADS_EXCHANGE_GRANT = "th_exchange_token"


def sign_in_threads(typed: dict, session: SignInSession) -> dict:
    """Threads Login at ``THREADS_AUTHORIZE_URL``, then ``THREADS_LONG_LIVED_URL``.

    Meta publishes ``graph.threads.com`` and ``graph.threads.net`` as one API,
    and each call here carries the host its own documentation page prints.
    """
    secret = str(typed.get("threads-client-secret", ""))
    client_id = str(typed.get("threads-client-id", ""))
    code, redirect_uri = session.approve(
        THREADS_AUTHORIZE_URL,
        {
            "client_id": client_id,
            "response_type": RESPONSE_TYPE_CODE,
            "scope": COMMA_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_THREADS)
            ),
        },
        redirect_policy(ata_spm_push.TARGET_THREADS),
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=THREADS_EXCHANGE_URL,
            data={
                "client_id": client_id,
                "client_secret": secret,
                "grant_type": GRANT_AUTHORIZATION_CODE,
                REDIRECT_PARAM: redirect_uri,
                "code": code,
            },
            headers={CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE},
        )
    )
    long_lived = session.transport(
        SignInRequest(
            method=METHOD_GET,
            url=THREADS_LONG_LIVED_URL,
            params={
                "grant_type": THREADS_EXCHANGE_GRANT,
                "client_secret": secret,
                "access_token": read_field(answered, "access_token"),
            },
            headers={ACCEPT_HEADER: JSON_ACCEPT},
        )
    )
    return {
        "threads-user-id": read_field(answered, "user_id"),
        "threads-access-token": read_field(long_lived, "access_token"),
    }


# ── Reddit ───────────────────────────────────────────────────────────
REDDIT_AUTHORIZE_URL = "https://www.reddit.com/api/v1/authorize"
REDDIT_EXCHANGE_URL = "https://www.reddit.com/api/v1/access_token"

#: Reddit issues a refresh token only where the authorize call asks for one.
REDDIT_PERMANENT_DURATION = "permanent"


def sign_in_reddit(typed: dict, session: SignInSession) -> dict:
    """Reddit's flow with HTTP Basic at ``REDDIT_EXCHANGE_URL`` and a stated agent.

    ``REDDIT_PERMANENT_DURATION`` on the authorize call is what makes Reddit
    issue a refresh token, and a generic ``USER_AGENT_HEADER`` is rate limited.
    """
    app_id = str(typed.get("reddit-app-id", ""))
    code, redirect_uri = session.approve(
        REDDIT_AUTHORIZE_URL,
        {
            "client_id": app_id,
            "response_type": RESPONSE_TYPE_CODE,
            "duration": REDDIT_PERMANENT_DURATION,
            "scope": SCOPE_SEPARATOR.join(
                ata_spm_push.target_scopes(ata_spm_push.TARGET_REDDIT)
            ),
        },
        redirect_policy(ata_spm_push.TARGET_REDDIT),
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=REDDIT_EXCHANGE_URL,
            data={
                "grant_type": GRANT_AUTHORIZATION_CODE,
                "code": code,
                REDIRECT_PARAM: redirect_uri,
            },
            headers={
                CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE,
                USER_AGENT_HEADER: str(typed.get("reddit-user-agent", "")),
            },
            basic_auth=(app_id, str(typed.get("reddit-app-secret", ""))),
        )
    )
    return {
        "reddit-access-token": read_field(answered, "access_token"),
        "reddit-refresh-token": read_field(answered, "refresh_token"),
    }


#: One route per push target name. A name with no row here cannot sign in, and
#: ``build_connector`` says so rather than running a flow that fits no venue.
def sign_in_discord(typed: dict, session: SignInSession) -> dict:
    """Check the typed webhook URL reads as ``DISCORD_WEBHOOK_FORM`` and issue nothing.

    No browser opens and no venue is reached; ``AtaSpmSettings.connect``
    then stores the URL, which ``ata_spm_send.send_discord`` posts through.
    """
    del session
    try:
        ata_spm_send.parse_webhook(typed.get(ata_spm_push.DISCORD_WEBHOOK_FIELD))
    except ata_spm_send.SendRefused as exc:
        raise SignInError(exc.detail) from exc
    return {}


def sign_in_telegram(typed: dict, session: SignInSession) -> dict:
    """Check the typed bot token and chat id read as their forms and issue nothing.

    No browser opens and no venue is reached; ``AtaSpmSettings.connect``
    then stores both, which ``ata_spm_send.send_telegram`` posts through.
    """
    del session
    try:
        ata_spm_send.check_telegram_credential(dict(typed))
    except ata_spm_send.SendRefused as exc:
        raise SignInError(exc.detail) from exc
    return {}


# ── Robinhood ────────────────────────────────────────────────────────
# OVERTAKEN, quoted whole:
#   "The venue id this venue's broker connector, its equity venue row and its
#   sign-in row all carry."
# True today: one firm, one venue id, across every sector it serves. The
# transport is chosen below it, by the sector the bot trades.
#: The venue id this firm's crypto connector, its broker connector, its equity
#: venue row and its sign-in row all carry.
ROBINHOOD_VENUE = "robinhood"

#: The sectors Robinhood's Model Context Protocol route serves, every one traded
#: as a fund share. ``robinhood_broker.SECTORS_SERVED`` is this tuple, and
#: ``crypto`` is absent because that sector reaches the signed REST route in
#: ``robinhood_connector`` instead.
ROBINHOOD_MCP_SECTORS = ("stocks", "commodities", "indices", "forex")

ROBINHOOD_AUTHORIZE_URL = "https://robinhood.com/oauth"
ROBINHOOD_EXCHANGE_URL = "https://api.robinhood.com/oauth2/token/"
ROBINHOOD_REGISTRATION_URL = "https://agent.robinhood.com/oauth/trading/register"

#: The one scope this venue's protected-resource metadata publishes.
ROBINHOOD_MCP_SCOPE = "internal"

#: The client name the registration call sends, which names the program and no
#: operator.
ROBINHOOD_CLIENT_NAME = "Acervator"

ROBINHOOD_CLIENT_ID_FIELD = "robinhood-mcp-client-id"
ROBINHOOD_BEARER_FIELD = "robinhood-mcp-access-token"
ROBINHOOD_REFRESH_FIELD = "robinhood-mcp-refresh-token"

JSON_CONTENT_TYPE = "application/json"

#: ``token_endpoint_auth_methods_supported`` at this venue, so no route holds a
#: client secret and none is sent.
AUTH_METHOD_NONE = "none"
REFRESH_GRANT = "refresh_token"

CLIENT_ID_FIELD_NAME = "client_id"
BEARER_FIELD_NAME = "access_token"
REFRESH_FIELD_NAME = "refresh_token"


def register_robinhood_client(session: SignInSession, policy: RedirectPolicy) -> str:
    """Earn one client id at ``ROBINHOOD_REGISTRATION_URL`` and answer it.

    This writes a record at the venue, so it runs only where the operator holds
    no client id yet, and the reply carrying no ``client_id`` raises
    ``SignInError``.
    """
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=ROBINHOOD_REGISTRATION_URL,
            json_body={
                "client_name": ROBINHOOD_CLIENT_NAME,
                "redirect_uris": [policy.register_as],
                "grant_types": [GRANT_AUTHORIZATION_CODE, REFRESH_GRANT],
                "response_types": [RESPONSE_TYPE_CODE],
                "token_endpoint_auth_method": AUTH_METHOD_NONE,
            },
            headers={
                CONTENT_TYPE_HEADER: JSON_CONTENT_TYPE,
                ACCEPT_HEADER: JSON_ACCEPT,
            },
        )
    )
    return read_field(answered, CLIENT_ID_FIELD_NAME)


def sign_in_robinhood_mcp(typed: dict, session: SignInSession) -> dict:
    """Robinhood's MCP authorization code flow, calling
    ``register_robinhood_client`` where the operator holds no client id.

    This venue publishes ``AUTH_METHOD_NONE``, so the route sends
    ``code_verifier`` and no secret, and what it answers belongs to one operator.
    """
    policy = redirect_policy(ROBINHOOD_VENUE)
    client_id = str(typed.get(ROBINHOOD_CLIENT_ID_FIELD, "") or "")
    if not client_id:
        client_id = register_robinhood_client(session, policy)
    verifier = str(session.verifier_source())
    code, redirect_uri = session.approve(
        ROBINHOOD_AUTHORIZE_URL,
        {
            "response_type": RESPONSE_TYPE_CODE,
            "client_id": client_id,
            "scope": ROBINHOOD_MCP_SCOPE,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": CHALLENGE_METHOD_S256,
        },
        policy,
    )
    answered = session.transport(
        SignInRequest(
            method=METHOD_POST,
            url=ROBINHOOD_EXCHANGE_URL,
            data={
                "grant_type": GRANT_AUTHORIZATION_CODE,
                "code": code,
                CLIENT_ID_FIELD_NAME: client_id,
                REDIRECT_PARAM: redirect_uri,
                "code_verifier": verifier,
            },
            headers={CONTENT_TYPE_HEADER: FORM_CONTENT_TYPE},
        )
    )
    return {
        ROBINHOOD_CLIENT_ID_FIELD: client_id,
        ROBINHOOD_BEARER_FIELD: read_field(answered, BEARER_FIELD_NAME),
        ROBINHOOD_REFRESH_FIELD: read_field(answered, REFRESH_FIELD_NAME),
    }


SIGN_IN_ROUTES = {
    ata_spm_push.TARGET_X: sign_in_x,
    ata_spm_push.TARGET_INSTAGRAM: sign_in_instagram,
    ata_spm_push.TARGET_LINKEDIN: sign_in_linkedin,
    ata_spm_push.TARGET_TIKTOK: sign_in_tiktok,
    ata_spm_push.TARGET_FACEBOOK: sign_in_facebook,
    ata_spm_push.TARGET_THREADS: sign_in_threads,
    ata_spm_push.TARGET_REDDIT: sign_in_reddit,
    ata_spm_push.TARGET_DISCORD: sign_in_discord,
    ata_spm_push.TARGET_TELEGRAM: sign_in_telegram,
    ROBINHOOD_VENUE: sign_in_robinhood_mcp,
}


# OVERTAKEN, quoted whole:
#   "Every trading venue id that connects through ``SIGN_IN_ROUTES`` instead of
#   a typed API key and secret. ``settings_dialog_surface.credential_kind``
#   reads this, so the Add form asks for what the pressed venue actually takes."
# True today: a venue reaches the browser route on the sectors named beside it,
# and the key-and-secret route on every other sector it serves.
#: Every trading venue id that connects through ``SIGN_IN_ROUTES`` rather than a
#: typed API key and secret, mapped to the sectors reaching that route. An empty
#: tuple names every sector the venue serves, and
#: ``settings_dialog_surface.credential_kind`` reads this for the pressed wing.
BROWSER_AUTHORIZATION_SECTORS = {ROBINHOOD_VENUE: ROBINHOOD_MCP_SECTORS}

#: Every trading venue id ``BROWSER_AUTHORIZATION_SECTORS`` names, on any sector.
BROWSER_AUTHORIZATION_VENUES = frozenset(BROWSER_AUTHORIZATION_SECTORS)

#: The client-id and bearer field names each browser venue's own sign-in answers.
#: ``settings_dialog_surface.browser_credential_fields`` reads this, so no screen
#: names a venue to learn what its sign-in issues.
BROWSER_CREDENTIAL_FIELDS = {
    ROBINHOOD_VENUE: (ROBINHOOD_CLIENT_ID_FIELD, ROBINHOOD_BEARER_FIELD),
}

#: Every venue whose own route publishes a trade-approval setting the credentials
#: page reads back. ``approval_reader`` resolves the callable.
APPROVAL_READ_VENUES = frozenset({ROBINHOOD_VENUE})

#: The ``core.settings.ExchangeConfig`` field pair a typed key and secret sit
#: under, which every venue taking one is stored in.
TYPED_CREDENTIAL_STORE = ("api_key_enc", "api_secret_enc")

#: The ``core.settings.ExchangeConfig`` field pair a browser sign-in's client id
#: and bearer sit under. One venue holds this beside ``TYPED_CREDENTIAL_STORE``
#: where its sectors reach two transports.
BROWSER_CREDENTIAL_STORE = ("mcp_client_id_enc", "mcp_bearer_enc")


def credential_store_fields(venue_id: Any, sector: Any = "") -> tuple:
    """The two ``ExchangeConfig`` field names one venue's stored credential sits
    under, on one ``sector``.

    ``takes_browser_authorization`` picks ``BROWSER_CREDENTIAL_STORE``, and every
    other venue and sector answers ``TYPED_CREDENTIAL_STORE``.
    """
    if takes_browser_authorization(venue_id, sector):
        return BROWSER_CREDENTIAL_STORE
    return TYPED_CREDENTIAL_STORE


def browser_authorization_sectors(venue_id: Any) -> tuple:
    """The sectors one venue signs in at a browser for, and () for a venue
    ``BROWSER_AUTHORIZATION_SECTORS`` does not name.

    A named venue carrying an empty tuple answers every sector, which
    ``takes_browser_authorization`` reads as no narrowing.
    """
    asked = str(venue_id or "").strip().lower()
    return tuple(BROWSER_AUTHORIZATION_SECTORS.get(asked, ()))


def takes_browser_authorization(venue_id: Any, sector: Any = "") -> bool:
    """Whether one venue id signs in at a browser, on one ``sector``.

    An empty ``sector`` asks after any sector the venue serves, and a venue whose
    ``browser_authorization_sectors`` omits ``sector`` answers False.
    """
    asked = str(venue_id or "").strip().lower()
    if asked not in BROWSER_AUTHORIZATION_VENUES:
        return False
    named = browser_authorization_sectors(asked)
    held = str(sector or "").strip().lower()
    if not named or not held:
        return True
    return held in named


def browser_credential_fields(venue_id: Any) -> tuple:
    """The client-id and bearer field names one venue's own sign-in answers.

    A venue ``BROWSER_CREDENTIAL_FIELDS`` does not name answers ("", "").
    """
    asked = str(venue_id or "").strip().lower()
    return tuple(BROWSER_CREDENTIAL_FIELDS.get(asked, ("", "")))


def approval_reader(venue_id: Any) -> Optional[Callable]:
    """The callable reading one venue's own trade-approval setting, and None for
    a venue ``APPROVAL_READ_VENUES`` does not name.

    ``robinhood_broker.read_trade_approval`` is imported inside this function,
    and that module reads ``ROBINHOOD_VENUE`` from this one.
    """
    if str(venue_id or "").strip().lower() not in APPROVAL_READ_VENUES:
        return None
    from ..stocks.robinhood_broker import read_trade_approval

    return read_trade_approval


def approval_states() -> tuple:
    """The on, off and unread trade-approval states, in that order.

    ``robinhood_broker`` owns the three strings, and this names them for a screen
    that reads a level off a state.
    """
    from ..stocks.robinhood_broker import APPROVAL_OFF, APPROVAL_ON, APPROVAL_UNREAD

    return (APPROVAL_ON, APPROVAL_OFF, APPROVAL_UNREAD)


def approval_sentence(state: Any) -> str:
    """The sentence an operator's screen carries for one trade-approval state.

    ``robinhood_broker.approval_words`` is the one source of the wording.
    """
    from ..stocks.robinhood_broker import approval_words

    return approval_words(state)


def read_venue_approval(venue_id: Any, bearer: Any, reader: Any = None) -> dict:
    """One venue's own trade-approval state and the refusal that stopped the
    read, over its own ``approval_reader``.

    A venue ``approval_reader`` answers None for reads its own unread state with
    no call made, and ``reader`` stands in for that lookup.
    """
    from ..stocks.robinhood_broker import APPROVAL_UNREAD, RouteRefused

    held = reader or approval_reader(venue_id)
    if held is None:
        return {"approval": APPROVAL_UNREAD, "refusal": ""}
    try:
        return {"approval": held(bearer), "refusal": ""}
    except (RouteRefused, OSError, ValueError) as exc:
        return {"approval": APPROVAL_UNREAD, "refusal": str(exc)}


#: Where each push target sends the operator to approve. Level 1A prints this,
#: so he reads the address before the system browser opens on it.
AUTHORIZE_ADDRESSES = {
    ata_spm_push.TARGET_X: X_AUTHORIZE_URL,
    ata_spm_push.TARGET_INSTAGRAM: INSTAGRAM_AUTHORIZE_URL,
    ata_spm_push.TARGET_LINKEDIN: LINKEDIN_AUTHORIZE_URL,
    ata_spm_push.TARGET_TIKTOK: TIKTOK_AUTHORIZE_URL,
    ata_spm_push.TARGET_FACEBOOK: FACEBOOK_AUTHORIZE_URL.format(
        version=FACEBOOK_GRAPH_VERSION
    ),
    ata_spm_push.TARGET_THREADS: THREADS_AUTHORIZE_URL,
    ata_spm_push.TARGET_REDDIT: REDDIT_AUTHORIZE_URL,
    ROBINHOOD_VENUE: ROBINHOOD_AUTHORIZE_URL,
}


#: What each venue's own documentation accepts as a redirect address, and the
#: exact wording Level 1A prints for what he registers at that venue.
#:
#: X, Instagram, Threads and Reddit each match the registered address exactly
#: and publish no wildcard port, so each binds ``FIXED_CALLBACK_PORT``. LinkedIn
#: asks a native client for a random loopback port, and TikTok publishes a
#: wildcard port for that case, so both take ``EPHEMERAL_PORT``. Facebook
#: requires HTTPS and publishes ``FACEBOOK_DESKTOP_REDIRECT`` instead.
REDIRECT_POLICIES = {
    ata_spm_push.TARGET_X: RedirectPolicy(
        loopback=True,
        port=FIXED_CALLBACK_PORT,
        register_as=LOOPBACK_ADDRESS_FORMAT.format(
            port=FIXED_CALLBACK_PORT, path=CALLBACK_PATH
        ),
    ),
    ata_spm_push.TARGET_INSTAGRAM: RedirectPolicy(
        loopback=True,
        port=FIXED_CALLBACK_PORT,
        register_as=LOOPBACK_ADDRESS_FORMAT.format(
            port=FIXED_CALLBACK_PORT, path=CALLBACK_PATH
        ),
    ),
    ata_spm_push.TARGET_LINKEDIN: RedirectPolicy(
        loopback=True,
        port=EPHEMERAL_PORT,
        register_as=ANY_LOOPBACK_PORT_TEXT,
    ),
    ata_spm_push.TARGET_TIKTOK: RedirectPolicy(
        loopback=True,
        port=EPHEMERAL_PORT,
        register_as=WILDCARD_PORT_FORMAT.format(path=CALLBACK_PATH),
    ),
    ata_spm_push.TARGET_FACEBOOK: RedirectPolicy(
        loopback=False,
        address=FACEBOOK_DESKTOP_REDIRECT,
        register_as=FACEBOOK_DESKTOP_REDIRECT,
    ),
    ata_spm_push.TARGET_THREADS: RedirectPolicy(
        loopback=True,
        port=FIXED_CALLBACK_PORT,
        register_as=LOOPBACK_ADDRESS_FORMAT.format(
            port=FIXED_CALLBACK_PORT, path=CALLBACK_PATH
        ),
    ),
    ata_spm_push.TARGET_REDDIT: RedirectPolicy(
        loopback=True,
        port=FIXED_CALLBACK_PORT,
        register_as=LOOPBACK_ADDRESS_FORMAT.format(
            port=FIXED_CALLBACK_PORT, path=CALLBACK_PATH
        ),
    ),
    # register_robinhood_client sends register_as, so the operator types no
    # address at this venue and FIXED_CALLBACK_PORT is what approve binds.
    ROBINHOOD_VENUE: RedirectPolicy(
        loopback=True,
        port=FIXED_CALLBACK_PORT,
        register_as=LOOPBACK_ADDRESS_FORMAT.format(
            port=FIXED_CALLBACK_PORT, path=CALLBACK_PATH
        ),
    ),
}


def redirect_policy(target: Any) -> RedirectPolicy:
    """The ``REDIRECT_POLICIES`` row one push target redirects by.

    A name with no row raises ``SignInError``, and no route falls back to an
    address its venue never published.
    """
    held = REDIRECT_POLICIES.get(str(target))
    if held is None:
        raise SignInError(NO_POLICY_FORMAT.format(target=target))
    return held


def registered_redirect(target: Any) -> str:
    """The ``RedirectPolicy.register_as`` wording one push target's page prints."""
    return str(REDIRECT_POLICIES.get(str(target), NO_POLICY_ROW).register_as)


def redirects_to_view(target: Any) -> bool:
    """Whether one push target answers inside a sign-in view the program draws.

    A name with no ``REDIRECT_POLICIES`` row answers False, and its Level 1A
    page then carries the wording every loopback venue carries.
    """
    held = REDIRECT_POLICIES.get(str(target))
    return held is not None and not held.loopback


def sign_in_route(target: Any) -> Optional[Callable]:
    """The ``SIGN_IN_ROUTES`` row one push target name signs in through, or None."""
    return SIGN_IN_ROUTES.get(str(target))


def authorize_address(target: Any) -> str:
    """The ``AUTHORIZE_ADDRESSES`` row one push target sends the operator to."""
    return str(AUTHORIZE_ADDRESSES.get(str(target), ""))


def build_connector(session: SignInSession) -> Callable:
    """The callable ``AtaSpmSettings.set_connector`` takes, over one ``SignInSession``.

    It answers what the venue issued, which ``AtaSpmSettings.connect`` stores
    beside what the operator typed.
    """

    def connect_one(target: Any, typed: Any) -> dict:
        """Sign ``target`` in through its ``SIGN_IN_ROUTES`` row."""
        route = sign_in_route(target)
        if route is None:
            raise SignInError(NO_ROUTE_FORMAT.format(target=target))
        return dict(route(dict(typed or {}), session))

    return connect_one


def default_session(view: Optional[Callable] = None) -> SignInSession:
    """A ``SignInSession`` on ``open_in_browser`` and ``urlopen_transport``.

    ``view`` is what ``approve_at_view`` draws a venue's own desktop sign-in
    in, and stays None where the caller draws none.
    """
    return SignInSession(transport=urlopen_transport, view=view)
