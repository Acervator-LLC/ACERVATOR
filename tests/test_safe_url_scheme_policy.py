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

# Every safe_urlopen call site in the tree, by file:line and by the
# exact keyword shape it passes. safe_urlopen no longer accepts
# *args/**kwargs, so this list is what proves the narrowing broke
# nobody. test_every_call_site_still_exists keeps the list honest.
_CALL_SITES: tuple[tuple[str, dict], ...] = (
    ("src/core/notifications.py:359", {"timeout": 10}),
    ("src/core/sms_engine.py:133", {"timeout": 10}),
    # RE-ANCHORED 2026-08-16, from :428. The pre-flight call did not
    # move in the source; 57 lines of docstring went in ABOVE it when
    # CCXTConnector.connect became a coroutine that actually yields.
    # The kwarg shape is unchanged -- only the line number moved, and
    # :485 was found by READING every `safe_urlopen(` occurrence in the
    # file, not by adding 57 to the old number. This pin still asserts
    # that `safe_urlopen(` is ON that line, which is its whole point.
    ("src/exchange/ccxt_connector.py:539", {"timeout": 15, "context": None}),
    ("src/exchange/crypto_assets.py:530", {"timeout": 10}),
    ("src/exchange/market_data.py:132", {"timeout": 15}),
    ("src/exchange/chart_data.py:281", {"timeout": 10}),
    # RE-ANCHORED 2026-08-21, from :3727 and :3825. THESE TWO CALLS
    # ARE INSIDE THE TAB THE CHANGE INSTRUMENTED, which is new: every
    # earlier move pushed them down from above. The API Tester emitter
    # unit put 276 lines into `APITesterTab`, and both calls live in
    # that class -- the first in `_raw_http_probe`, the second in
    # `_check_exchange_status` -- so each moved by the count of lines
    # inserted ABOVE IT rather than by one shared offset: 191 and 238.
    # That is why neither number may be derived by arithmetic. Both
    # were found by READING -- `grep -n "safe_urlopen("` over
    # main_window.py returns exactly these two lines and nothing else.
    # Neither call moved in the source and neither kwarg shape changed.
    #
    # BOTH PINS WERE PROVED TO STILL BIND, INDEPENDENTLY, by shifting
    # each call one line and watching only that row fail. A number
    # that is merely correct proves nothing about a pin that no longer
    # reads it.
    #
    # THE EMITTER UNIT ADDED NO MODULE-LEVEL IMPORT. Its five pins
    # import `src.core.signal_contract.emit` function-locally, the way
    # every other emitter site in this repo does, precisely so that the
    # only thing moving these two numbers is code inside the tab.
    #
    # THE MOVE FROM :3918 AND :4063 IS THE ONE REPAIR ABOVE THEM. The
    # guard that stopped `apitest.16.002`'s context read from adding a
    # precondition to `_do_disconnect` sits in that method, which is
    # ABOVE BOTH CALLS, so this time a single offset of sixteen lines
    # covers both -- unlike the unit before it, where the inserts
    # straddled the first call. That is a fact about where the change
    # landed, not a rule: both numbers were read again from
    # `grep -n "safe_urlopen(" src/gui/main_window.py`, which still
    # returns exactly these two lines. Neither call moved in the
    # source and neither kwarg shape changed.
    #
    # RE-ANCHORED 2026-08-21, from :3934 and :4079, by the issue #51
    # selection re-anchor. Both calls are BELOW everything that unit
    # touched -- a helper above `BotStatusTable`, one line in each of
    # the two `update_bots` methods, a comment restatement inside
    # `ExchangeTab.update_bots` and one widened import -- so one
    # shared offset of 125 lines covers both. That is a fact about
    # where the change landed and not a rule: both numbers were read
    # again from `grep -n "safe_urlopen(" src/gui/main_window.py`,
    # which still returns exactly these two lines. Neither call moved
    # in the source and neither kwarg shape changed.
    #
    # BOTH PINS WERE PROVED TO STILL BIND AGAIN, INDEPENDENTLY, by
    # shifting each call one line and watching only that row fail.
    #
    # RE-ANCHORED 2026-08-21, from :4059 and :4204, by the issue #57
    # throttle instance key. Both calls are BELOW everything that
    # change touched -- one comment inside `_refresh_chart_panels`,
    # one comment block and two `instance=` keywords inside
    # `ExchangeTab.update_bots` -- so one shared offset of 23 lines
    # covers both. That is a fact about where the change landed and
    # not a rule: both numbers were read again from
    # `grep -n "safe_urlopen(" src/gui/main_window.py`, which still
    # returns exactly these two lines and nothing else. Neither call
    # moved in the source and neither kwarg shape changed.
    #
    # BOTH PINS WERE PROVED TO STILL BIND AGAIN, INDEPENDENTLY, by
    # shifting each call one line and watching only that row fail.
    #
    # RE-ANCHORED 2026-08-21, from :4082 and :4227, by the issue #52
    # Detail-button row selection. Both calls are BELOW everything that
    # change touched -- one helper above `BotStatusTable` and a comment
    # plus one call at the top of each of the two `_on_detail` methods
    # -- so one shared offset of 96 lines covers both. That is a fact
    # about where the change landed and not a rule: both numbers were
    # read again from `grep -n "safe_urlopen(" src/gui/main_window.py`,
    # which still returns exactly these two lines and nothing else.
    # Neither call moved in the source and neither kwarg shape changed.
    #
    # BOTH PINS WERE PROVED TO STILL BIND AGAIN, INDEPENDENTLY, by
    # shifting each call one line and watching only that row fail.
    #
    # Earlier notes here recorded the move from :3244 and :3342 on
    # 2026-08-13 (the IVP persistence unit, twelve lines), from :3256
    # and :3354 (the Asset Charts emitter unit, 204 lines), from
    # :3460 and :3558 (the Exchange tab emitter unit, 267 lines), from
    # :3727 and :3825 (the API Tester emitter unit, 191 and 238), from
    # :3918 and :4063 (the `apitest.16.002` repair, sixteen), from
    # :3934 and :4079 (the issue #51 selection re-anchor, 125) and from
    # :4059 and :4204 (the issue #57 throttle instance key, 23).
    #
    # RE-ANCHORED 2026-08-24, from :4178 and :4323, by the issue #106
    # growth-cap re-base. Both calls are BELOW everything that change
    # touched in this file -- the chart's Target Balance ceiling line,
    # which is three hunks between :1299 and :1339 inside
    # `update_charts` -- so one shared offset of 24 lines happens to
    # cover both. That is a fact about where the change landed and not
    # a rule, and this pin block is the reason it must be said out
    # loud: the 2026-08-21 API Tester note above records two calls in
    # the SAME class moving by 191 and 238, because the inserts
    # straddled the first one. A single offset is a coincidence of a
    # change that landed entirely above both calls, never a method.
    #
    # Both numbers were read again from
    # `grep -n "safe_urlopen(" src/gui/main_window.py`, which still
    # returns exactly these two lines and nothing else, and each was
    # matched to its pin by the method it sits in and the keywords it
    # passes rather than by position alone: :4202 is
    # `APITesterTab._raw_http_probe` and carries `context=ssl_ctx`,
    # :4347 is `APITesterTab._check_exchange_status` and carries no
    # context. Reading the grep alone is not enough --
    # `ccxt_connector.py:337` is a DOCSTRING that names
    # `safe_urlopen(..., timeout=15)` and would answer that grep while
    # calling nothing. Neither call moved in the source and neither
    # kwarg shape changed.
    #
    # BOTH PINS WERE PROVED TO STILL BIND AGAIN, INDEPENDENTLY, by
    # shifting each call one line and watching only that row fail.
    #
    # THIS FILE WAS NOT IN THE ISSUE #106 BRIEF. That unit re-anchored
    # `tests/test_autonomous_fold_price_gate.py` and
    # `tests/test_extractor_tranche_containment.py` and was told those
    # were the only two guarded files. This is the third, and it was
    # found by a red release gate rather than by anything the unit
    # could have run. The three shapes do not share a matcher: this
    # table stores `"path:line"` strings, `CITATION_ANCHORS` stores
    # `int -> line text`, and `PRE_CHANGE_SHA256` pins no line at all.
    #
    # RE-ANCHORED for issue #46 (4202 -> 4249, 4347 -> 4394). That unit
    # inserted a symbol-change branch into `TradeChartsTab.update_charts`,
    # which is above both calls. The new numbers were READ from
    # `grep -n "safe_urlopen(" src/gui/main_window.py` after the
    # insertion was final, not computed from an offset.
    ("src/gui/main_window.py:4621", {"timeout": 10, "context": None}),
    ("src/gui/main_window.py:4787", {"timeout": 10}),
)
_CALL_IDS = [site for site, _ in _CALL_SITES]
_CALL_KWARGS = [kwargs for _, kwargs in _CALL_SITES]

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

    def test_every_call_site_still_exists(self):
        """The site list above is a claim about the tree; check it.

        If a caller moves or is deleted, this list is stale and the
        binding tests above are pinning a shape nobody uses.
        """
        for site in _CALL_IDS:
            path, line = site.rsplit(":", 1)
            source = (REPO / path).read_text(encoding="utf-8").splitlines()
            assert (
                "safe_urlopen(" in source[int(line) - 1]
            ), f"{site} no longer calls safe_urlopen"


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
