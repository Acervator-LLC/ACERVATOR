"""ata_spm_signin.py -- one sign-in route per ATA-SPM push target.

``SIGN_IN_ROUTES`` maps one push target name to the route that signs it in.
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
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import ata_spm_push

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
NO_POLICY_FORMAT = "No redirect address for {target}."

CALLBACK_LOG = "ATA-SPM sign-in callback refused: %s"


class SignInError(Exception):
    """A venue, a browser or ``LoopbackReceiver`` stopped one sign-in short."""


@dataclass(frozen=True)
class SignInRequest:
    """One call a route makes, and the only shape ``SignInSession.transport`` takes.

    ``params`` is the query string, ``data`` the form body, and ``basic_auth``
    the user and password of an HTTP Basic header.
    """

    method: str
    url: str
    params: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    basic_auth: tuple = ()


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


def urlopen_transport(request: SignInRequest) -> dict:
    """Send one ``SignInRequest`` through ``safe_urlopen`` and answer its JSON.

    ``HTTPS_SCHEME`` is the whole allowlist handed to ``SafeRequest``, which
    narrows the default and refuses every other scheme at construction.
    """
    import json

    from ..core.safe_url import SafeRequest, safe_urlopen

    address = str(request.url)
    if request.params:
        address = address + QUERY_MARK + urllib.parse.urlencode(request.params)
    body = urllib.parse.urlencode(request.data).encode() if request.data else None
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
    with safe_urlopen(
        sent, body, timeout=TRANSPORT_TIMEOUT_SECONDS, allowed_schemes=(HTTPS_SCHEME,)
    ) as answered:
        return dict(json.loads(answered.read().decode()))


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
SIGN_IN_ROUTES = {
    ata_spm_push.TARGET_X: sign_in_x,
    ata_spm_push.TARGET_INSTAGRAM: sign_in_instagram,
    ata_spm_push.TARGET_LINKEDIN: sign_in_linkedin,
    ata_spm_push.TARGET_TIKTOK: sign_in_tiktok,
    ata_spm_push.TARGET_FACEBOOK: sign_in_facebook,
    ata_spm_push.TARGET_THREADS: sign_in_threads,
    ata_spm_push.TARGET_REDDIT: sign_in_reddit,
}


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


def default_session() -> SignInSession:
    """A ``SignInSession`` on ``open_in_browser`` and ``urlopen_transport``."""
    return SignInSession(transport=urlopen_transport)
