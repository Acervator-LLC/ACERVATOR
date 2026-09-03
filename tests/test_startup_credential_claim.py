"""The launch-time credential report must claim only what it measured.

THE DEFECT
The launch report read `api_key_enc` out of the settings entry and
tested it for a non-empty value. It made no exchange call of any kind,
and it then told the operator
"credentials present, ready to trade" and recorded
"Credentials found (encrypted). Ready for authenticated API calls."
at `level="success"`.

A revoked, expired, wrong or malformed key produces exactly the same
blob length as a working one, so every one of those keys read as "ready
to trade" at launch. The operator found out at the first trade.

WHAT IS PINNED HERE
The method is driven with a stub `self`, the way
`tests/test_c39f_wire_does_not_rewrite_config.py` drives its handler:
the whole window would test Qt, not this decision. Every string the
method emits -- Activity Log line, notification, and each API-log
`reason`, `result` and `data_usage` -- goes through `overclaims`, which
matches the four claim classes this path is not entitled to make:
readiness, connectivity, reachability and verification.

`test_the_detector_matches_the_wording_this_path_used_to_emit` is the
control. It feeds the five retired strings to the same detector and
requires a hit on each, so a detector that stopped matching cannot make
the other tests pass by seeing nothing.

NOTHING HERE TOUCHES THE NETWORK OR THE OPERATOR'S TREE. The settings
object is a local list of dicts, the API log is a fresh
`APIInteractionLog` bound over the module global for the call, and the
method under test opens no socket and reads no file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from src.exchange import api_logger  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402

READY = re.compile(r"\bready\b", re.IGNORECASE)
CONNECTED = re.compile(r"\bconnect\w*", re.IGNORECASE)
REACHABLE = re.compile(r"\breachab\w*", re.IGNORECASE)
VERIFIED = re.compile(r"(?<!un)(?<!not )verif\w*", re.IGNORECASE)

CLAIMS = (
    ("readiness", READY),
    ("connectivity", CONNECTED),
    ("reachability", REACHABLE),
    ("verification", VERIFIED),
)

RETIRED_STRINGS = (
    "Check exchange connectivity on launch and log to API panel.",
    "Verifying 2 exchange(s)...",
    "Coinbase: credentials present, ready to trade",
    "Credentials found (encrypted). Ready for authenticated API calls.",
    "Application launched, verifying 2 exchange(s)",
)


def overclaims(text: str) -> list[str]:
    """Name every claim class *text* makes that a settings read cannot support.

    Used by the launch-report tests to hold the emitted operator text to
    what was measured. "unverified" and "not verified" are excluded, so
    a string may state the absence of verification.
    """
    return [name for name, pattern in CLAIMS if pattern.search(text)]


class _Log:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def log(self, msg: str, level: str = "info") -> None:
        self.lines.append((level, msg))


class _Spool:
    def __init__(self) -> None:
        self.notes: list[tuple[str, str]] = []

    def notify(self, message: str, level: str = "info") -> None:
        self.notes.append((level, message))


class _Settings:
    def __init__(self, exchanges: list[dict]) -> None:
        self._exchanges = exchanges

    def list_exchanges(self) -> list[dict]:
        return self._exchanges


STORED = {"exchange_id": "coinbase", "api_key_enc": "gAAAAAB-ciphertext"}
EMPTY = {"exchange_id": "kraken", "api_key_enc": ""}


def _drive(
    exchanges: list[dict], monkeypatch: pytest.MonkeyPatch
) -> tuple[list, list, list]:
    """Run the real launch report over *exchanges* and return what it emitted."""
    log = api_logger.APIInteractionLog()
    monkeypatch.setattr(api_logger, "get_api_log", lambda: log)
    me = SimpleNamespace(
        _settings=_Settings(exchanges),
        _status_log=_Log(),
        _spool=_Spool(),
    )
    MainWindow._report_stored_credentials_on_startup(me)
    return me._status_log.lines, me._spool.notes, log.get_recent(50)


def _texts(lines: list, notes: list, records: list) -> list[str]:
    out = [msg for _lvl, msg in lines] + [msg for _lvl, msg in notes]
    for rec in records:
        out += [rec["reason"], rec["result"], rec["data_usage"]]
    return out


def test_the_detector_matches_the_wording_this_path_used_to_emit() -> None:
    """The control for every "nothing overclaims" test below.

    A detector that matched nothing would pass them all while the old
    wording shipped, so each retired string has to score a hit.
    """
    for text in RETIRED_STRINGS:
        assert overclaims(text), f"detector went blind on the retired string: {text!r}"


def test_the_detector_lets_a_stated_absence_of_verification_through() -> None:
    """A stated absence of verification is not a claim of verification."""
    assert overclaims("credentials stored, unverified") == []
    assert overclaims("Encrypted credentials found. Not verified.") == []
    assert overclaims("credentials verified") == ["verification"]


def test_a_stored_credential_claims_nothing_beyond_being_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty blob in settings is the whole measurement."""
    lines, notes, records = _drive([STORED], monkeypatch)
    offenders = [(t, overclaims(t)) for t in _texts(lines, notes, records)]
    guilty = [(t, c) for t, c in offenders if c]
    assert not guilty, f"the launch report claims what it never measured: {guilty}"


def test_a_stored_credential_is_still_reported_as_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the test above: silence would also pass it."""
    lines, notes, records = _drive([STORED], monkeypatch)
    blob = " ".join(_texts(lines, notes, records)).lower()
    assert "coinbase" in blob, f"the exchange is never named: {lines} {notes}"
    assert "stored" in blob, f"the stored credential is never reported: {blob}"
    assert notes, "the operator is notified of nothing"


def test_a_stored_credential_is_never_recorded_as_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`level="success"` paints the row green; no venue was contacted."""
    lines, notes, records = _drive([STORED], monkeypatch)
    green = [r for r in records if r["level"] == "success"]
    assert not green, f"a settings read is recorded as a success: {green}"
    assert [lvl for lvl, _m in lines + notes if lvl == "success"] == []


def test_a_missing_credential_claims_nothing_beyond_being_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty blob is reported as missing and nothing further."""
    lines, notes, records = _drive([EMPTY], monkeypatch)
    guilty = [
        (t, overclaims(t)) for t in _texts(lines, notes, records) if overclaims(t)
    ]
    assert not guilty, f"the launch report claims what it never measured: {guilty}"


def test_a_missing_credential_is_still_reported_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the test above: silence would also pass it."""
    lines, notes, records = _drive([EMPTY], monkeypatch)
    blob = " ".join(_texts(lines, notes, records)).lower()
    assert "kraken" in blob, f"the exchange is never named: {lines} {notes}"
    assert "no credentials" in blob or "no api credentials" in blob, blob
    assert [lvl for lvl, _m in notes] == ["warning"], notes


def test_both_exchanges_are_reported_and_neither_overclaims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop reports each exchange without either branch overclaiming."""
    lines, notes, records = _drive([STORED, EMPTY], monkeypatch)
    texts = _texts(lines, notes, records)
    guilty = [(t, overclaims(t)) for t in texts if overclaims(t)]
    assert not guilty, f"the launch report claims what it never measured: {guilty}"
    blob = " ".join(texts).lower()
    assert "coinbase" in blob and "kraken" in blob, blob


def test_no_configured_exchange_reports_that_and_nothing_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The early return states only that no exchange is configured."""
    lines, notes, records = _drive([], monkeypatch)
    guilty = [
        (t, overclaims(t)) for t in _texts(lines, notes, records) if overclaims(t)
    ]
    assert not guilty, f"the empty launch report overclaims: {guilty}"
    assert notes == [("warning", "No exchanges configured.")], notes
