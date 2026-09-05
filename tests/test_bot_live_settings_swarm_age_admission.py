"""Age admission on the two Bot Swarm tables of ``bot_live_settings``.

``_create_bot_swarm_tab`` renders one Age column from ``credit["ts"]`` and
one from ``tx.timestamp``, and both read their stamp through
``as_finite_float``. ``REFUSED`` lists every shape whose cell must be
``DASH``; ``ACCEPTED`` pins the string each readable stamp renders, so a
guard that dashed everything would fail. ``_build`` drives the real method
through a stub ``self``, so every row below is the tab an operator opens.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Frozen clock. The method calls ``time.time()`` itself, so without this
#: "an hour ago" is not expressible and every age drifts between runs.
NOW = 1_800_000_000.0

#: The text both columns print for a credit or transaction with no timestamp.
DASH = "—"

#: Column 0 is Age in both tables.
COL_AGE = 0

PENDING_HEADERS = ["Age", "Source", "USD", "Ref"]
RECENT_HEADERS = ["Age", "Direction", "Other Bot", "USD", "Type"]

BOT_ID = "bot-swarm-test"


class _FloatSub(float):
    """A float subclass: passes isinstance, fails exact type."""


class _HasFloat:
    """Not a number, but float() of it succeeds."""

    def __float__(self) -> float:
        return 1.0


REFUSED = [
    pytest.param(True, id="bool-True"),
    pytest.param(False, id="bool-False"),
    pytest.param(_FloatSub(NOW - 3600.0), id="float-subclass"),
    pytest.param(Decimal("1799996400"), id="Decimal"),
    pytest.param(Fraction(1799996400, 1), id="Fraction"),
    pytest.param("1799996400", id="numeric-string"),
    pytest.param("abc", id="non-numeric-string"),
    pytest.param("", id="empty-string"),
    pytest.param(None, id="None"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="inf"),
    pytest.param(float("-inf"), id="-inf"),
    pytest.param(0, id="zero"),
    pytest.param(-5.0, id="negative"),
    pytest.param(2**1023 + 1, id="int-just-over-bound"),
    pytest.param(10**400, id="huge-int"),
    pytest.param(_HasFloat(), id="obj-with-__float__"),
    pytest.param([1, 2], id="list"),
    pytest.param({"a": 1}, id="dict"),
]

#: (stamp, the exact string the shipped code renders for it).
ACCEPTED = [
    pytest.param(NOW - 30.0, "30s", id="float-seconds"),
    pytest.param(NOW - 1800.0, "30m", id="float-half-hour"),
    pytest.param(NOW - 3600.0, "1.0h", id="float-one-hour"),
    pytest.param(int(NOW) - 7200, "2.0h", id="int-two-hours"),
    pytest.param(NOW - 43200.0, "12.0h", id="float-half-day"),
    pytest.param(int(NOW) - 90000, "1.0d", id="int-one-day"),
    pytest.param(NOW - 172800.0, "2.0d", id="float-two-days"),
    # Inside the helper's 2**1023 int bound, so it is admitted and renders
    # nonsense without raising.
    pytest.param(2**53 + 1, "-9007197454740992s", id="int-2**53+1"),
]


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Tx:
    """Stand-in for smart_wire.WireTransaction.

    Attributes are set per instance so a test can OMIT ``timestamp``
    entirely, which is the missing-attribute case the object site has
    and the dict site expresses as a missing key.
    """

    def __init__(self, **kw):
        self.source_bot = ""
        self.target_bot = ""
        self.amount = 0.0
        self.wire_type = "WIRE_BACK"
        for k, v in kw.items():
            setattr(self, k, v)


class _Ledger:
    """Stand-in for smart_wire.BotLedger, all fields valid."""

    asset = "BTC"
    wired_in = 1250.0
    wired_out = 300.0
    starting_balance = 5000.0
    predominant_source = "bot-parent"
    mature_profit_total = 700.0
    mature_profit_available = 420.0
    mature_profit_allocated = 280.0
    provenance = {"bot-parent": 900.0, "bot-sibling": 350.0}


def _valid_credit():
    """One realistic pending wire credit, every key valid."""
    return {
        "ts": NOW - 3600.0,
        "source": "bot-parent",
        "usd": 42.5,
        "ref": "scrum@30000.00000000",
    }


def _valid_tx():
    """One realistic recent transaction, every field valid."""
    return _Tx(
        timestamp=int(NOW) - 7200,
        source_bot=BOT_ID,
        target_bot="bot-child",
        amount=17.25,
        wire_type="SCRUM_ROUTE",
    )


def _build(monkeypatch, credits=None, txs=None, full=False):
    """Build the REAL Bot Swarm tab. Returns the widget.

    Drives ``BotLiveSettingsDialog._create_bot_swarm_tab`` itself through
    a stub ``self``, so every assertion below is about the tab an
    operator opens and not about a copy of its logic. Asserting on the
    admission helper instead would prove nothing about the dialog: the
    helper could be perfect and the call site still unguarded, which is
    exactly the state this unit found.
    """
    app = _qt_or_skip()
    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    tx_list = list(txs) if txs is not None else []

    class _Mgr:
        _wires = (
            {BOT_ID: {"bot-child": 25.0}, "bot-parent": {BOT_ID: 40.0}} if full else {}
        )
        _ledgers = (
            {BOT_ID: _Ledger(), "bot-child": _Ledger(), "bot-parent": _Ledger()}
            if full
            else {}
        )
        _transactions = tx_list
        _bot_refs: dict = {}

    class _StubBot:
        _smart_wire_mgr = _Mgr()
        bot_id = BOT_ID
        _pending_wire_ledger = list(credits) if credits is not None else []
        _pending_wire_credits = 42.5

    class _StubDlg:
        # Re-wrapped: an unwrapped bind makes `_format_age` an instance
        # method and passes `self` as `seconds`.
        _format_age = staticmethod(_Dlg._format_age)
        _bot = _StubBot()

        def _configure_form(self, *forms):
            self._forms_seen = forms

    widget = _Dlg._create_bot_swarm_tab(_StubDlg())
    _ = app
    return widget


def _table(widget, headers):
    """The one QTableWidget whose header labels are `headers`.

    Selected by header text, not by index, so adding a table elsewhere
    in the tab cannot silently repoint an assertion at the wrong one.
    """
    from PySide6.QtWidgets import QTableWidget

    for tbl in widget.findChildren(QTableWidget):
        got = [
            tbl.horizontalHeaderItem(c).text()
            for c in range(tbl.columnCount())
            if tbl.horizontalHeaderItem(c) is not None
        ]
        if got == headers:
            return tbl
    raise AssertionError(f"no table with headers {headers}")


def _rows(widget, headers):
    tbl = _table(widget, headers)
    return [
        [
            (tbl.item(r, c).text() if tbl.item(r, c) else None)
            for c in range(tbl.columnCount())
        ]
        for r in range(tbl.rowCount())
    ]


def _dict_age(value, monkeypatch, *, omit=False):
    """The Age cell the pending-ledger row renders for `value`."""
    credit = _valid_credit()
    if omit:
        credit.pop("ts")
    else:
        credit["ts"] = value
    widget = _build(monkeypatch, credits=[credit])
    rows = _rows(widget, PENDING_HEADERS)
    assert len(rows) == 1, "the row must still render"
    return rows[0][COL_AGE]


def _obj_age(value, monkeypatch, *, omit=False):
    """The Age cell the recent-transactions row renders for `value`."""
    tx = _valid_tx()
    if omit:
        del tx.timestamp
    else:
        tx.timestamp = value
    widget = _build(monkeypatch, txs=[tx])
    rows = _rows(widget, RECENT_HEADERS)
    assert len(rows) == 1, "the row must still render"
    return rows[0][COL_AGE]


@pytest.mark.parametrize("value", REFUSED)
def test_dict_site_refuses_without_raising(value, monkeypatch):
    assert _dict_age(value, monkeypatch) == DASH


@pytest.mark.parametrize("value", REFUSED)
def test_object_site_refuses_without_raising(value, monkeypatch):
    assert _obj_age(value, monkeypatch) == DASH


def test_dict_site_missing_key_refuses(monkeypatch):
    assert _dict_age(None, monkeypatch, omit=True) == DASH


def test_object_site_missing_attribute_refuses(monkeypatch):
    """The object site's own shape: `timestamp` absent entirely."""
    assert _obj_age(None, monkeypatch, omit=True) == DASH


def test_one_bad_row_does_not_take_the_good_rows_with_it(monkeypatch):
    """A hostile entry must cost its own cell, not the whole table."""
    good = _valid_credit()
    bad = _valid_credit()
    bad["ts"] = float("inf")
    later = _valid_credit()
    later["ts"] = NOW - 30.0
    widget = _build(monkeypatch, credits=[good, bad, later])
    ages = [r[COL_AGE] for r in _rows(widget, PENDING_HEADERS)]
    assert ages == ["1.0h", DASH, "30s"]


def test_object_site_one_bad_row_keeps_the_others(monkeypatch):
    good = _valid_tx()
    bad = _valid_tx()
    bad.timestamp = float("inf")
    widget = _build(monkeypatch, txs=[good, bad])
    ages = [r[COL_AGE] for r in _rows(widget, RECENT_HEADERS)]
    # `recent_tx` reverses the feed, so the hostile row renders first.
    assert ages == [DASH, "2.0h"]


@pytest.mark.parametrize("value,expected", ACCEPTED)
def test_dict_site_accepts_real_timestamps(value, expected, monkeypatch):
    assert _dict_age(value, monkeypatch) == expected


@pytest.mark.parametrize("value,expected", ACCEPTED)
def test_object_site_accepts_real_timestamps(value, expected, monkeypatch):
    assert _obj_age(value, monkeypatch) == expected


def test_dict_site_json_round_trip_preserves_a_real_age(monkeypatch):
    """The ACTIVE reachability path, driven rather than asserted.

    A credit that has been through `json.dumps` and `json.loads` — the
    same trip `_restore_state` gives it — must render the same age it
    had in memory.
    """
    credit = json.loads(json.dumps(_valid_credit()))
    widget = _build(monkeypatch, credits=[credit])
    assert _rows(widget, PENDING_HEADERS)[0][COL_AGE] == "1.0h"


@pytest.mark.parametrize(
    "literal,decoded",
    [
        ('{"ts": Infinity}', float("inf")),
        ('{"ts": -Infinity}', float("-inf")),
        ('{"ts": NaN}', float("nan")),
    ],
)
def test_json_really_decodes_these_shapes(literal, decoded):
    """The control for the reachability claim itself.

    If `json.loads` ever stopped returning real non-finite floats for
    these literals, the ACTIVE verdict above would be wrong and the
    refusal tests would be pinning an unreachable path.
    """
    got = json.loads(literal)["ts"]
    assert type(got) is float
    assert (got != got) if (decoded != decoded) else (got == decoded)


def test_dict_site_json_round_trip_of_infinity_refuses(monkeypatch):
    """End to end: a state file carrying `Infinity` must not raise."""
    credit = _valid_credit()
    credit["ts"] = json.loads('{"ts": Infinity}')["ts"]
    assert _dict_age(credit["ts"], monkeypatch) == DASH


def test_the_other_cells_on_the_row_are_untouched(monkeypatch):
    """This unit closed the AGE column and nothing else on the row."""
    credit = _valid_credit()
    widget = _build(monkeypatch, credits=[credit])
    row = _rows(widget, PENDING_HEADERS)[0]
    assert row == ["1.0h", "bot-parent", "$42.5000", "scrum@30000.00000000"]


def test_the_other_transaction_cells_are_untouched(monkeypatch):
    widget = _build(monkeypatch, txs=[_valid_tx()])
    row = _rows(widget, RECENT_HEADERS)[0]
    assert row == ["2.0h", "OUT →", "bot-child", "$17.2500", "SCRUM_ROUTE"]


def test_refusal_string_equals_the_absent_timestamp_string(monkeypatch):
    """A refused value must render what an ABSENT one already rendered.

    `omit=True` takes the pre-existing else-branch — the one that
    shipped before this unit — and every refused shape must land on the
    identical string.
    """
    absent_dict = _dict_age(None, monkeypatch, omit=True)
    absent_obj = _obj_age(None, monkeypatch, omit=True)
    assert absent_dict == absent_obj == DASH
    for probe in (float("inf"), 10**400, [1, 2], True, "abc"):
        assert _dict_age(probe, monkeypatch) == absent_dict
        assert _obj_age(probe, monkeypatch) == absent_obj


def test_refusal_is_the_dash_the_file_already_used():
    """The dash is U+2014, not a hyphen and not an en dash."""
    assert DASH == "—"
    assert len(DASH) == 1


def test_huge_int_does_not_raise_inside_the_guard():
    import math

    from src.trading.bot_container import as_finite_float

    with pytest.raises(OverflowError):
        math.isfinite(10**400)
    assert as_finite_float(10**400) is None
    assert as_finite_float(2**1023 + 1) is None
    # The bound is inclusive, and a float at 1e308 is still accepted —
    # only the INT path carries the bound.
    assert as_finite_float(2**1023) == float(2**1023)
    assert as_finite_float(1e308) == 1e308


@pytest.mark.parametrize("value", [10**400, 2**1023 + 1])
def test_huge_int_does_not_raise_through_either_tab_site(value, monkeypatch):
    assert _dict_age(value, monkeypatch) == DASH
    assert _obj_age(value, monkeypatch) == DASH


def _spy_on_the_shipped_helper(monkeypatch):
    """Record every value `bot_container.as_finite_float` is asked about.

    The real helper still answers, so `_build` renders exactly as it does
    unpatched.
    """
    from src.trading import bot_container

    real = bot_container.as_finite_float
    seen: list = []

    def spy(value):
        seen.append(value)
        return real(value)

    monkeypatch.setattr(bot_container, "as_finite_float", spy)
    return seen


def test_both_age_columns_read_their_timestamp_through_the_shipped_helper(
    monkeypatch,
):
    """Both `ts` and `timestamp` reach `bot_container.as_finite_float`."""
    seen = _spy_on_the_shipped_helper(monkeypatch)
    credit = _valid_credit()
    credit["ts"] = NOW - 3600.0
    tx = _valid_tx()
    tx.timestamp = int(NOW) - 7200

    rows = _rows(_build(monkeypatch, credits=[credit], txs=[tx]), RECENT_HEADERS)

    assert seen, "the tab asked the shipped helper about nothing"
    assert NOW - 3600.0 in seen, (
        "the pending-credit `ts` never reached bot_container.as_finite_float; "
        f"the helper was asked about {seen!r}"
    )
    assert int(NOW) - 7200 in seen, (
        "the transaction `timestamp` never reached "
        f"bot_container.as_finite_float; the helper was asked about {seen!r}"
    )
    assert rows[0][COL_AGE] == "2.0h", "the spy changed what the tab renders"


def test_both_age_columns_dash_when_the_shipped_helper_refuses(monkeypatch):
    """A refusing `bot_container.as_finite_float` dashes both Age columns.

    A private copy of the admission rule inside `_create_bot_swarm_tab`
    would still render an age and leave this red.
    """
    from src.trading import bot_container

    monkeypatch.setattr(bot_container, "as_finite_float", lambda value: None)
    widget = _build(monkeypatch, credits=[_valid_credit()], txs=[_valid_tx()])
    assert _rows(widget, PENDING_HEADERS)[0][COL_AGE] == DASH
    assert _rows(widget, RECENT_HEADERS)[0][COL_AGE] == DASH


def test_the_control_arm_renders_a_real_age_with_the_helper_unpatched(monkeypatch):
    """The control for the refusal above: unpatched, both columns render."""
    widget = _build(monkeypatch, credits=[_valid_credit()], txs=[_valid_tx()])
    assert _rows(widget, PENDING_HEADERS)[0][COL_AGE] == "1.0h"
    assert _rows(widget, RECENT_HEADERS)[0][COL_AGE] == "2.0h"
