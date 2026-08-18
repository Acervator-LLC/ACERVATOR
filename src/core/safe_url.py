"""
safe_url.py — scheme-restricted URL opener.

Replacement for ``urllib.request.urlopen`` that rejects any URL whose
scheme is not in the allowlist (http / https). Closes the v3.15.84
bandit B310 audit batch by replacing 18 bare ``urlopen`` sites across
the codebase with a single point of policy.

Why a wrapper rather than 18 ``# nosec B310`` markers:
  • The wrapper is a real check, not just a suppression.
  • One audit point if the scheme policy ever changes (e.g., disallow
    plain http on production builds).
  • Future url-open sites get the validation for free if they use
    the wrapper from the start.

Two independent protections, deliberately not the same mechanism:

  1. POLICY — ``_require_allowed_scheme`` parses the URL and raises
     ``ValueError`` naming the rejected scheme and the URL. It runs at
     ``SafeRequest`` construction and again at open time.
  2. TRANSPORT — the opener built by ``_build_restricted_opener``
     carries handlers for http and https only. It has no
     ``FileHandler``, no ``FTPHandler`` and no ``DataHandler``, which
     the stock ``urllib.request.urlopen`` opener all install. So a
     ``file:``, ``ftp:`` or ``data:`` URL has no transport here even if
     the policy check were removed or bypassed; it raises ``URLError``
     from ``UnknownHandler`` instead of being fetched.

Protection 2 is why this module no longer calls ``urlopen`` at all.
``urlopen`` reaches those extra schemes by construction, so a caller
who slipped past the policy check would still get a local file read.
An opener that cannot address the filesystem cannot be talked into it.

Usage:
    from src.core.safe_url import safe_urlopen
    with safe_urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

A caller that genuinely needs a non-http(s) scheme cannot get it from
this module by widening ``allowed_schemes``: that parameter narrows the
policy, and no amount of widening adds a transport handler. Such a
caller must use ``urllib`` directly and justify it at its own site.

sadp: R28 R71 R76
"""
from __future__ import annotations

import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Iterable, Optional, Union

if TYPE_CHECKING:  # pragma: no cover - annotations only
    import ssl

# The three names this module exists to hand out: the policy itself,
# a request that has been checked against it, and an open that has.
__all__ = ["DEFAULT_ALLOWED_SCHEMES", "SafeRequest", "safe_urlopen"]

# Default scheme allowlist — http and https only. Acervator never
# legitimately needs file:// or ftp:// for runtime URL opens.
DEFAULT_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def _extract_url(req_or_url: Union[str, urllib.request.Request]) -> str:
    """Return the URL string from either a Request object or a raw URL."""
    if isinstance(req_or_url, urllib.request.Request):
        return req_or_url.full_url
    return str(req_or_url)


def _require_allowed_scheme(
    url: str, allowed_schemes: Optional[Iterable[str]] = None,
) -> None:
    """Raise ValueError unless ``url``'s scheme is in the allowlist."""
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    allowed = (frozenset(s.lower() for s in allowed_schemes)
               if allowed_schemes is not None
               else DEFAULT_ALLOWED_SCHEMES)
    if scheme not in allowed:
        raise ValueError(
            f"safe_urlopen: refused scheme {scheme!r} "
            f"(URL: {url!r}). Allowed schemes: {sorted(allowed)}."
        )


def _build_restricted_opener(
    context: ssl.SSLContext | None = None,
) -> urllib.request.OpenerDirector:
    """Build an opener that can transport http and https, and nothing else.

    ``urllib.request.build_opener`` cannot be used here. It always
    installs ``FTPHandler``, ``FileHandler`` and ``DataHandler``, and
    handlers passed to it are added to that set rather than replacing
    it — there is no supported way to take a handler away again. So the
    director is assembled by hand from the http(s) subset.

    The handler list below is ``build_opener``'s default list minus
    those three. ``UnknownHandler`` is kept deliberately: without it an
    unroutable scheme makes ``OpenerDirector.open`` return ``None``
    rather than raise, and a silent ``None`` is worse than an error.
    With it, an unroutable scheme raises ``URLError``.

    ``context=None`` is what ``urlopen`` passes when a caller supplies
    no SSL context, and leaves ``HTTPSHandler`` on the interpreter's
    default verified-TLS context. It does not disable verification.
    """
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.ProxyHandler())
    opener.add_handler(urllib.request.HTTPHandler())
    opener.add_handler(urllib.request.HTTPSHandler(context=context))
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.add_handler(urllib.request.HTTPRedirectHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    opener.add_handler(urllib.request.UnknownHandler())
    return opener


class SafeRequest(urllib.request.Request):
    """A ``urllib.request.Request`` that cannot hold a bad scheme.

    ``safe_urlopen`` validates at OPEN time. That is late for a caller
    that builds a request, attaches headers, and only then opens it:
    between construction and the open, the object looks like a
    perfectly ordinary request for a ``file:`` path. This subclass
    moves the same check to CONSTRUCTION, so an object of this type is
    proof on its own that the scheme was checked against the
    allowlist — there is no way to obtain one that was not.

    The check is the same policy as ``safe_urlopen``, from the same
    allowlist, and raises the same ``ValueError``. Passing one of these
    to ``safe_urlopen`` re-checks it; that repetition is deliberate,
    since neither call may assume the other happened.

    Only the URL is accepted. The base class also takes ``data``,
    ``headers``, ``origin_req_host``, ``unverifiable`` and ``method``;
    forwarding them blind would mean typing them as ``object`` and
    handing the base class arguments no type checker can vouch for.
    Callers attach headers with ``add_header`` after construction,
    which is what both existing call sites already do.
    """

    def __init__(
        self,
        url: str,
        *,
        allowed_schemes: Iterable[str] | None = None,
    ) -> None:
        """Build a request, refusing a scheme outside the allowlist."""
        _require_allowed_scheme(url, allowed_schemes)
        super().__init__(url)


def safe_urlopen(
    req_or_url: Union[str, urllib.request.Request],
    data: bytes | None = None,
    *,
    timeout: float = 10.0,
    allowed_schemes: Iterable[str] | None = None,
    context: ssl.SSLContext | None = None,
):
    """Open a URL after validating its scheme is in ``allowed_schemes``.

    Raises ``ValueError`` for any disallowed scheme. The error message
    surfaces the rejected scheme + URL so the operator can see exactly
    what was refused.

    ``data``, ``timeout`` and ``context`` mean what they mean for
    ``urllib.request.urlopen``. They are spelled out instead of being
    swept into ``*args``/``**kwargs`` because ``context`` has to be
    routed into the HTTPS handler when the opener is built, which a
    blind forward cannot do, and because a named parameter is a typed
    one.
    """
    # One copy of the check, shared with SafeRequest. The message and
    # the exception type are unchanged from when this was written out
    # here; moving it into the helper is what lets the constructor-time
    # check be the same policy rather than a second one that could
    # drift from it.
    _require_allowed_scheme(_extract_url(req_or_url), allowed_schemes)
    # Second, independent protection: this opener has no file/ftp/data
    # handler, so those schemes have no transport even if the check
    # above were bypassed. See _build_restricted_opener.
    opener = _build_restricted_opener(context)
    return opener.open(req_or_url, data, timeout)
