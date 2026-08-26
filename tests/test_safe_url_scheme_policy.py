"""Pin tests for src/core/safe_url.py — scheme policy and transport.

The module had no test file. It is the single choke point through
which every URL in Acervator is opened, so the refusals it performs
were load-bearing and unpinned.

WHAT IS PINNED
==============
Two independent protections, tested separately because they can fail
separately:

  1. POLICY — ``_require_allowed_scheme`` raises ``ValueError`` naming
     the rejected scheme and the URL.
  2. TRANSPORT — the opener carries http/https handlers only, so
     ``file:``, ``ftp:`` and ``data:`` have no way to be fetched even
     with the policy check bypassed entirely.

Protection 2 is tested with a PAIRED CONTROL: the same real file on
disk is opened successfully through a stock ``build_opener()`` and
refused through the restricted opener. Without the paired control a
passing refusal test proves nothing — a URL that simply did not exist
would also "refuse". The control shows the file was genuinely
reachable and that the handler set is what refused it.

No test here makes a real outbound network call. The http/https
handlers are replaced with recorders.
"""

from __future__ import annotations

import ast
import email.message
import io
import inspect
import ssl
import sys
import tokenize
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.safe_url import (  # noqa: E402
    DEFAULT_ALLOWED_SCHEMES,
    SafeRequest,
    _build_restricted_opener,
    safe_urlopen,
)

# The distinct keyword shapes safe_urlopen is called with across the
# tree. safe_urlopen no longer accepts *args/**kwargs, so the binding
# tests below prove the narrowed signature still accepts every real shape.
_CALL_KWARGS: tuple[dict, ...] = (
    {"timeout": 10},
    {"timeout": 15},
    {"timeout": 10, "context": None},
    {"timeout": 15, "context": None},
)
_CALL_IDS = ["-".join(f"{k}={v}" for k, v in kw.items()) for kw in _CALL_KWARGS]

_MODULE_SOURCE = (REPO / "src" / "core" / "safe_url.py").read_text(encoding="utf-8")


def _canned(url: str, body: bytes = b"OK", code: int = 200):
    """A minimal response object of the type urllib handlers return.

    ``msg`` is set explicitly because ``HTTPErrorProcessor`` reads it
    on every response. That processor is a real part of the restricted
    opener, so these tests go through it rather than around it.
    """
    headers = email.message.Message()
    headers["Content-Type"] = "text/plain"
    response = urllib.response.addinfourl(io.BytesIO(body), headers, url, code)
    response.msg = "OK"
    return response


@pytest.fixture
def recorder(monkeypatch):
    """Replace the http/https transports with recorders.

    Everything else in the opener — the director, the redirect
    handler, the error processor — stays real, so dispatch is still
    being exercised.
    """
    seen: dict = {"calls": [], "https_context": "unset"}

    def http_open(self, req):
        seen["calls"].append(("http", req))
        return _canned(req.full_url)

    def https_open(self, req):
        seen["calls"].append(("https", req))
        return _canned(req.full_url)

    real_init = urllib.request.HTTPSHandler.__init__

    def recording_init(self, *args, context=None, **kwargs):
        seen["https_context"] = context
        real_init(self, *args, context=context, **kwargs)

    monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", http_open)
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
    monkeypatch.setattr(urllib.request.HTTPSHandler, "__init__", recording_init)
    return seen


class TestAllowlistContents:
    def test_allowlist_is_http_and_https_only(self):
        assert DEFAULT_ALLOWED_SCHEMES == frozenset({"http", "https"})

    def test_allowlist_is_immutable(self):
        assert isinstance(DEFAULT_ALLOWED_SCHEMES, frozenset)


class TestSchemeRefusals:
    """Protection 1 — the policy check."""

    def test_file_url_refused(self):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("file:///etc/passwd")
        assert "'file'" in str(exc.value)

    def test_file_refusal_names_the_url(self):
        url = "file:///C:/Users/secret.txt"
        with pytest.raises(ValueError) as exc:
            safe_urlopen(url)
        message = str(exc.value)
        assert "'file'" in message, "refusal must name the scheme"
        assert url in message, "refusal must name the URL"
        assert "http" in message, "refusal must state what IS allowed"

    def test_custom_scheme_refused(self):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("acervator-evil://payload")
        assert "'acervator-evil'" in str(exc.value)

    def test_ftp_refused(self):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("ftp://example.com/x")
        assert "'ftp'" in str(exc.value)

    def test_data_url_refused(self):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("data:text/plain;base64,QUJD")
        assert "'data'" in str(exc.value)

    def test_schemeless_refused(self):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("example.com/no-scheme")
        assert "''" in str(exc.value)

    def test_uppercase_file_refused(self):
        """Case folding must not become a bypass."""
        with pytest.raises(ValueError):
            safe_urlopen("FILE:///etc/passwd")

    def test_refusal_is_valueerror_exactly(self):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("file:///x")
        assert type(exc.value) is ValueError

    def test_request_mutated_after_construction_is_refused(self, tmp_path):
        """A Request is checked at open time, not trusted.

        ``Request.full_url`` is settable, so a request built clean can
        be pointed somewhere else before it is opened. This is the
        exact gap ``SafeRequest`` was written for, from the other side:
        the open-time check has to catch it, because construction-time
        validation did not happen here.

        The URI points at a file that really exists and really is
        readable, so the refusal cannot be a missing-file artefact.
        """
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET", encoding="utf-8")
        req = urllib.request.Request("https://example.com")
        req.full_url = secret.as_uri()
        with pytest.raises(ValueError) as exc:
            safe_urlopen(req)
        assert "'file'" in str(exc.value)

    def test_safe_request_mutated_after_construction_is_refused(self, tmp_path):
        """Same mutation against a SafeRequest.

        Construction-time validation cannot cover a later reassignment,
        which is why safe_urlopen re-checks instead of trusting the
        type. This test is what makes that repetition load-bearing.
        """
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET", encoding="utf-8")
        req = SafeRequest("https://example.com")
        req.full_url = secret.as_uri()
        with pytest.raises(ValueError) as exc:
            safe_urlopen(req)
        assert "'file'" in str(exc.value)

    def test_refused_before_any_transport(self, recorder):
        """A refusal must not have touched the network at all."""
        with pytest.raises(ValueError):
            safe_urlopen("file:///etc/passwd")
        assert recorder["calls"] == []

    def test_narrowed_allowlist_refuses_https(self, recorder):
        with pytest.raises(ValueError) as exc:
            safe_urlopen("https://example.com", allowed_schemes=["http"])
        assert "'https'" in str(exc.value)
        assert recorder["calls"] == []


class TestSafeRequestConstruction:
    def test_http_accepted(self):
        assert SafeRequest("http://example.com").full_url == ("http://example.com")

    def test_https_accepted(self):
        assert SafeRequest("https://example.com").full_url == ("https://example.com")

    def test_file_refused_at_construction(self):
        with pytest.raises(ValueError) as exc:
            SafeRequest("file:///etc/passwd")
        assert "'file'" in str(exc.value)

    def test_custom_scheme_refused_at_construction(self):
        with pytest.raises(ValueError):
            SafeRequest("acervator-evil://payload")

    def test_is_a_request(self):
        assert isinstance(SafeRequest("https://x.example"), urllib.request.Request)


class TestAllowedOpens:
    """http and https still work, with the transport recorded."""

    def test_http_opens(self, recorder):
        with safe_urlopen("http://example.com/a") as resp:
            body = resp.read()
        assert body == b"OK"
        assert [c[0] for c in recorder["calls"]] == ["http"]

    def test_https_opens(self, recorder):
        with safe_urlopen("https://example.com/a") as resp:
            body = resp.read()
        assert body == b"OK"
        assert [c[0] for c in recorder["calls"]] == ["https"]

    def test_status_is_readable(self, recorder):
        """sms_engine reads resp.status; keep that working."""
        with safe_urlopen("https://example.com/a") as resp:
            assert resp.status == 200

    def test_request_headers_survive(self, recorder):
        """Every caller uses add_header after building the Request."""
        req = urllib.request.Request("https://example.com/a")
        req.add_header("User-Agent", "Acervator/1.6")
        req.add_header("Accept", "application/json")
        safe_urlopen(req).read()
        sent = recorder["calls"][0][1]
        assert sent.get_header("User-agent") == "Acervator/1.6"
        assert sent.get_header("Accept") == "application/json"

    def test_request_body_and_method_survive(self, recorder):
        """sms_engine POSTs a urlencoded body; notifications POSTs JSON."""
        req = urllib.request.Request(
            "https://api.twilio.com/x", data=b"Body=hi", method="POST"
        )
        safe_urlopen(req).read()
        sent = recorder["calls"][0][1]
        assert sent.data == b"Body=hi"
        assert sent.get_method() == "POST"

    def test_data_argument_forwarded(self, recorder):
        safe_urlopen("https://example.com/a", b"payload=1").read()
        assert recorder["calls"][0][1].data == b"payload=1"

    def test_safe_request_opens(self, recorder):
        safe_urlopen(SafeRequest("https://example.com/a")).read()
        assert [c[0] for c in recorder["calls"]] == ["https"]

    def test_ssl_context_reaches_the_https_handler(self, recorder):
        """ccxt_connector and main_window pass context=; it must land."""
        ctx = ssl.create_default_context()
        safe_urlopen("https://example.com/a", context=ctx).read()
        assert recorder["https_context"] is ctx

    def test_no_context_leaves_handler_on_default(self, recorder):
        """context=None is urlopen's own default, NOT disabled verification."""
        safe_urlopen("https://example.com/a").read()
        assert recorder["https_context"] is None


class TestTransportRestriction:
    """Protection 2 — the opener physically cannot reach file/ftp/data.

    These tests bypass the policy check on purpose. That is the point:
    they measure what is left when protection 1 is gone.
    """

    def test_no_file_handler_installed(self):
        opener = _build_restricted_opener()
        assert not any(
            isinstance(h, urllib.request.FileHandler) for h in opener.handlers
        )

    def test_no_ftp_handler_installed(self):
        opener = _build_restricted_opener()
        assert not any(
            isinstance(h, urllib.request.FTPHandler) for h in opener.handlers
        )

    def test_no_data_handler_installed(self):
        opener = _build_restricted_opener()
        assert not any(
            isinstance(h, urllib.request.DataHandler) for h in opener.handlers
        )

    def test_http_and_https_handlers_are_installed(self):
        opener = _build_restricted_opener()
        assert any(isinstance(h, urllib.request.HTTPHandler) for h in opener.handlers)
        assert any(isinstance(h, urllib.request.HTTPSHandler) for h in opener.handlers)

    def test_stock_opener_DOES_read_the_file(self, tmp_path):
        """PAIRED CONTROL for the refusal test below.

        This is the blinding check. If this fails, the file was never
        reachable and the refusal test proves nothing.
        """
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET", encoding="utf-8")
        with urllib.request.build_opener().open(secret.as_uri()) as resp:
            assert resp.read() == b"TOP SECRET"

    def test_restricted_opener_refuses_the_same_file(self, tmp_path):
        """Same file, same URI, policy check bypassed — still refused."""
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET", encoding="utf-8")
        opener = _build_restricted_opener()
        with pytest.raises(urllib.error.URLError) as exc:
            opener.open(secret.as_uri())
        assert "unknown url type" in str(exc.value)

    def test_restricted_opener_raises_rather_than_returning_none(self, tmp_path):
        """UnknownHandler must be present.

        Without it OpenerDirector.open returns None for an unroutable
        scheme instead of raising, and a silent None read as a response
        is worse than an error.
        """
        secret = tmp_path / "secret.txt"
        secret.write_text("x", encoding="utf-8")
        opener = _build_restricted_opener()
        result = None
        with pytest.raises(urllib.error.URLError):
            result = opener.open(secret.as_uri())
        assert result is None

    def test_module_calls_neither_urlopen_nor_build_opener(self):
        """The whole point of the shape, checked on the AST not the text.

        Both ``urlopen`` and ``build_opener`` install file/ftp/data
        handlers by construction, so a return to either would silently
        undo protection 2 while every refusal test above still passed
        — the policy check would still be there, doing its job, and the
        second layer would be gone with nothing to say so.
        """
        tree = ast.parse(_MODULE_SOURCE)
        called = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                called.add(func.attr)
            elif isinstance(func, ast.Name):
                called.add(func.id)
        assert "urlopen" not in called
        assert "urlretrieve" not in called
        assert "build_opener" not in called
        assert (
            "OpenerDirector" in called
        ), "the restricted director is how this module opens anything"

    def test_no_suppression_directives_in_module(self):
        """The finding was satisfied, not silenced.

        The pre-existing ``# nosec B310`` went away with the urlopen
        call it justified. Nothing replaced it.

        Real COMMENT tokens are checked, not raw text. The module
        docstring discusses ``# nosec`` markers as history, and prose
        about a suppression is not a suppression — only a comment on a
        code line silences anything.
        """
        comments = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(_MODULE_SOURCE).readline)
            if token.type == tokenize.COMMENT
        ]
        assert comments, "tokenizer found no comments at all — it is blind"
        for directive in ("nosec", "noqa", "type: ignore", "pyright: ignore"):
            offenders = [c for c in comments if directive in c]
            assert not offenders, f"{directive} present: {offenders}"


class TestExistingCallersStillBind:
    """Every safe_urlopen call site in the tree, by exact shape.

    safe_urlopen no longer takes *args/**kwargs. These bind the eight
    real call shapes against the new signature so a narrowing that
    broke a caller would fail here rather than in production.
    """

    @pytest.mark.parametrize("kwargs", _CALL_KWARGS, ids=_CALL_IDS)
    def test_call_shape_binds(self, kwargs):
        req = urllib.request.Request("https://example.com")
        bound = inspect.signature(safe_urlopen).bind(req, **kwargs)
        assert bound.arguments["req_or_url"] is req
        assert bound.arguments["timeout"] == kwargs["timeout"]

    @pytest.mark.parametrize("kwargs", _CALL_KWARGS, ids=_CALL_IDS)
    def test_call_shape_runs(self, recorder, kwargs):
        req = urllib.request.Request("https://example.com")
        with safe_urlopen(req, **kwargs) as resp:
            assert resp.read() == b"OK"


class TestRealCallerIntegration:
    """One caller driven end to end through the new opener."""

    def test_market_data_batch_fetch(self, recorder, monkeypatch):
        from src.exchange import market_data

        payload = (
            b'[{"id":"bitcoin","symbol":"btc","current_price":50000,'
            b'"high_24h":51000,"low_24h":49000,"total_volume":1000,'
            b'"price_change_percentage_24h":2.5}]'
        )

        def https_open(self, req):
            recorder["calls"].append(("https", req))
            return _canned(req.full_url, payload)

        monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)

        result = market_data._fetch_batch(["bitcoin"], {"bitcoin": "BTC"})

        assert result, "caller returned {} — the open failed and was swallowed"
        assert result["BTC"]["current_price"] == 50000
        assert result["BTC"]["volume_24h"] == 1000
        assert recorder["calls"][0][1].full_url.startswith("https://api.coingecko.com/")
