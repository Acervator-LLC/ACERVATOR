"""``_redact`` hides credential-bearing params and ``record`` keeps them off the log.

``TestRedactHidesCredentials`` names every field ``_redact`` must replace, and
``TestNonCredentialParamsSurvive`` is the positive control for the same call.
``TestTheLoggerLineNeverCarriesParams`` reads the records ``record`` emits
through ``logger`` and asserts no param value appears in the formatted line.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.api_logger import (  # noqa: E402
    APIInteractionLog,
    _redact,
)

MASK = "***REDACTED***"
FAKE_SIGNATURE = "d3ad" * 16
FAKE_SECRET = "n0tarealsecret" * 4


class TestRedactHidesCredentials:
    @pytest.mark.parametrize(
        "field",
        [
            "key",
            "apiKey",
            "api_key",
            "privateKey",
            "secret",
            "client_secret",
            "password",
            "passphrase",
            "token",
            "access_token",
            "signature",
            "sign",
            "CB-ACCESS-SIGN",
        ],
    )
    def test_a_credential_field_is_replaced_by_the_mask(self, field):
        out = _redact({field: FAKE_SIGNATURE})
        assert out[field] == MASK, (
            f"{field!r} survived _redact as {out[field]!r}; a credential field "
            f"must be replaced by {MASK}"
        )

    def test_a_long_unmatched_value_is_never_left_whole(self):
        out = _redact({"note": FAKE_SECRET})
        assert out["note"] != FAKE_SECRET
        assert out["note"].endswith("...")


class TestNonCredentialParamsSurvive:
    """Positive control: redaction is targeted, not blanket."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("symbol", "BTC/USD"),
            ("side", "buy"),
            ("amount", 0.25),
            ("limit", 300),
            ("price", None),
        ],
    )
    def test_a_benign_field_passes_through_unchanged(self, field, value):
        assert _redact({field: value})[field] == value

    def test_the_instrument_would_have_seen_a_mask(self):
        out = _redact({"symbol": "BTC/USD", "secret": FAKE_SECRET})
        assert out["symbol"] == "BTC/USD"
        assert out["secret"] == MASK


class _Capture(logging.Handler):
    """Collect formatted messages straight off the ``acervator.api`` logger."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _record_one(params: dict) -> str:
    """Run ``record`` with ``params`` and return every line its logger emitted."""
    target = logging.getLogger("acervator.api")
    handler = _Capture()
    prior_level, prior_disabled = target.level, target.disabled
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    target.disabled = False
    try:
        APIInteractionLog().record(
            exchange="coinbase",
            action="PLACE_ORDER",
            reason="unit check",
            endpoint="create_order",
            params=params,
            result="ok",
        )
    finally:
        target.removeHandler(handler)
        target.setLevel(prior_level)
        target.disabled = prior_disabled
    return "\n".join(handler.messages)


class TestTheLoggerLineNeverCarriesParams:
    def test_no_param_value_reaches_the_emitted_log_line(self):
        emitted = _record_one({"signature": FAKE_SIGNATURE, "symbol": "BTC/USD"})
        assert "PLACE_ORDER" in emitted, (
            "positive control failed: record() emitted no line at all, so the "
            f"absence assertions below prove nothing. Captured: {emitted!r}"
        )
        assert FAKE_SIGNATURE not in emitted
        assert "BTC/USD" not in emitted

    def test_the_capture_handler_would_have_seen_a_param(self):
        """Negative control: the same handler sees a value put in ``reason``."""
        target = logging.getLogger("acervator.api")
        handler = _Capture()
        target.addHandler(handler)
        target.setLevel(logging.DEBUG)
        try:
            APIInteractionLog().record(
                exchange="coinbase",
                action="PLACE_ORDER",
                reason=FAKE_SIGNATURE,
            )
        finally:
            target.removeHandler(handler)
        assert FAKE_SIGNATURE in "\n".join(handler.messages)

    def test_the_stored_entry_holds_only_the_redacted_params(self):
        log = APIInteractionLog()
        entry = log.record(
            exchange="coinbase",
            action="PLACE_ORDER",
            reason="unit check",
            params={"signature": FAKE_SIGNATURE},
        )
        assert entry["params"]["signature"] == MASK
