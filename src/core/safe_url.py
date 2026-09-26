"""Scheme-restricted replacement for ``urllib.request.urlopen``.

``_require_allowed_scheme`` raises ``ValueError`` for any URL whose scheme
is outside ``DEFAULT_ALLOWED_SCHEMES``, and it runs both at ``SafeRequest``
construction and inside ``safe_urlopen``. ``_build_restricted_opener``
installs http and https handlers only; a ``file:``, ``ftp:`` or ``data:``
URL raises ``URLError`` from ``UnknownHandler``. The ``allowed_schemes``
argument narrows that allowlist and never widens it. ``openable_url`` checks the
same allowlist for an address bound for the system browser, and answers a
refused one as an empty address carrying ``NO_ADDRESS_REASON`` or
``REFUSED_SCHEME_REASON``.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Iterable, Optional, Union

if TYPE_CHECKING:  # pragma: no cover - annotations only
    import ssl

__all__ = [
    "DEFAULT_ALLOWED_SCHEMES",
    "NO_ADDRESS_REASON",
    "REFUSED_SCHEME_REASON",
    "SafeRequest",
    "openable_url",
    "safe_urlopen",
]

DEFAULT_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

#: What ``openable_url`` answers for an address holding no scheme at all.
NO_ADDRESS_REASON = "no address is known"

#: What ``openable_url`` answers for a scheme outside the allowlist.
REFUSED_SCHEME_REASON = "the {scheme} scheme does not open; allowed: {allowed}"


def _extract_url(req_or_url: Union[str, urllib.request.Request]) -> str:
    """Return the URL string from either a Request object or a raw URL."""
    if isinstance(req_or_url, urllib.request.Request):
        return req_or_url.full_url
    return str(req_or_url)


def _require_allowed_scheme(
    url: str,
    allowed_schemes: Optional[Iterable[str]] = None,
) -> None:
    """Raise ValueError unless ``url``'s scheme is in the allowlist."""
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    allowed = (
        frozenset(s.lower() for s in allowed_schemes)
        if allowed_schemes is not None
        else DEFAULT_ALLOWED_SCHEMES
    )
    if scheme not in allowed:
        raise ValueError(
            f"safe_urlopen: refused scheme {scheme!r} "
            f"(URL: {url!r}). Allowed schemes: {sorted(allowed)}."
        )


def openable_url(
    url: object,
    allowed_schemes: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
    """An address a browser may open, with ``NO_ADDRESS_REASON`` or ``REFUSED_SCHEME_REASON`` for one it may not."""
    text = str(url)
    allowed = (
        DEFAULT_ALLOWED_SCHEMES
        if allowed_schemes is None
        else frozenset(one.lower() for one in allowed_schemes)
    )
    try:
        _require_allowed_scheme(text, allowed)
    except ValueError:
        scheme = (urllib.parse.urlparse(text).scheme or "").lower()
        if not scheme:
            return "", NO_ADDRESS_REASON
        return "", REFUSED_SCHEME_REASON.format(
            scheme=scheme, allowed=", ".join(sorted(allowed))
        )
    return text, ""


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
    """A ``urllib.request.Request`` whose scheme is checked at construction.

    ``_require_allowed_scheme`` runs here as well as in ``safe_urlopen``.
    The constructor accepts only the URL; callers attach headers with
    ``add_header``.
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
    """Open a URL after checking its scheme against ``allowed_schemes``.

    Raises ``ValueError`` naming the rejected scheme and URL; ``context``
    is routed into the HTTPS handler ``_build_restricted_opener`` builds.
    """
    _require_allowed_scheme(_extract_url(req_or_url), allowed_schemes)
    opener = _build_restricted_opener(context)
    return opener.open(req_or_url, data, timeout)
