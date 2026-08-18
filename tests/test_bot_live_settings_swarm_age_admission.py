"""Age admission on the two Bot Swarm tables of bot_live_settings.

THE DEFECT THESE PIN
====================
``_create_bot_swarm_tab`` rendered two Age columns from a bare
``float(... or 0)`` followed by ``> 0``:

* the PENDING WIRE CREDITS table, reading ``credit["ts"]`` off a dict;
* the RECENT WIRE TRANSACTIONS table, reading ``tx.timestamp`` off an
  object.

These were the last two of six ``_format_age`` callers in the file. The
other four were closed by earlier units.

THE SHAPE HERE IS NOT THE SHAPE THE FOLD SITES HAD, and the difference
decides which values are dangerous. These coerce with ``float(x or 0)``
FIRST and compare ``> 0`` SECOND. Measured through the real expression:

* ``or 0`` short-circuits every FALSY value before ``float()`` sees it,
  so ``None``, ``""``, ``[]``, ``{}``, ``False`` and ``0`` already
  rendered the dash. They were never the hole.
* ``nan`` survived ``float()`` and was then filtered by ``nan > 0``
  being False. Also already safe.
* ``inf`` survived BOTH — ``inf > 0`` is True — and reached
  ``_format_age``, whose ``int(seconds)`` raised OverflowError.
* A TRUTHY non-number raised at the ``float()`` itself, before any guard
  could run: ``"abc"`` ValueError, ``[1, 2]`` and ``{"a": 1}``
  TypeError, and ``10 ** 400`` OverflowError (it exceeds float range).
* ``True`` did not raise. It read as one second past the epoch and
  printed a confident ``"20833.3d"`` for a stored flag.

So five shapes raised and two lied. That is the table this file pins,
and it was derived for THESE sites rather than carried over.

WHY A RAISE MATTERS: the AST ancestor chain from both sites is
``For`` -> ``If`` -> ``_create_bot_swarm_tab`` -> ``BotLiveSettings
Dialog.__init__`` -> ``MainWindow._on_bot_clicked``, with NO ``try`` at
any step. A raise means the Bot Settings dialog does not open for that
bot. The contrast that proves the walk discriminates:
``simulator_tab.py:695`` builds the same dialog inside a ``try`` with an
``Exception`` handler, so the Simulator path is protected and the
operator's path is not.

REACHABILITY DIFFERS BETWEEN THE TWO SITES, and they are not one story:

* PENDING LEDGER — ACTIVE. ``ScrummingBot._restore_state`` rebuilds the
  list as ``dict(_e)`` per entry and coerces no key, so ``ts`` arrives
  exactly as ``json.load`` decoded it. ``json.loads("Infinity")``
  returns a real ``inf`` and JSON has no integer width limit.
  ``test_dict_site_json_round_trip_*`` drives that path rather than
  asserting it.
* RECENT TRANSACTIONS — LATENT. ``SmartWireManager._transactions`` has
  no assignment anywhere in ``src/`` or ``tests/``; it is only appended
  to. Both reachable constructors pass ``int(time.time())``. It is
  guarded because ``getattr`` is duck-typed and ``WireTransaction`` is a
  ``@dataclass``, which annotates ``timestamp: int`` without enforcing
  it — and because two Age columns in one tab must not disagree about
  what an unreadable timestamp means.

AND THE GUARD MUST NOT OPEN THE HOLE IT CLOSES: ``math.isfinite(10 **
400)`` itself raises OverflowError. ``as_finite_float`` bounds ints with
an integer comparison, which cannot raise. ``test_huge_int_*`` is the
row that tells the two apart.

Every table below carries POSITIVE CONTROLS — real timestamps whose
rendering was captured from the shipped code and pasted here byte for
byte. Without them a guard that refused everything would pass every
refusal test while blanking both columns.
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

#: The refusal string. NOT a new one — this is the exact text both
#: columns already printed for a credit or a transaction with no
#: timestamp, and closing the admission must land in that same branch.
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


#: Shapes that must render the dash. Each is a value the old code either
#: raised on, lied about, or already dashed — after the fix all three
#: groups land in the one branch that already existed.
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
    pytest.param(2 ** 1023 + 1, id="int-just-over-bound"),
    pytest.param(10 ** 400, id="huge-int"),
    pytest.param(_HasFloat(), id="obj-with-__float__"),
    pytest.param([1, 2], id="list"),
    pytest.param({"a": 1}, id="dict"),
]

#: Shapes that must still render a real age, with the exact string the
#: shipped code produced. Without these the refusal tests are satisfied
#: by a guard that dashes everything.
ACCEPTED = [
    pytest.param(NOW - 30.0, "30s", id="float-seconds"),
    pytest.param(NOW - 1800.0, "30m", id="float-half-hour"),
    pytest.param(NOW - 3600.0, "1.0h", id="float-one-hour"),
    pytest.param(int(NOW) - 7200, "2.0h", id="int-two-hours"),
    pytest.param(NOW - 43200.0, "12.0h", id="float-half-day"),
    pytest.param(int(NOW) - 90000, "1.0d", id="int-one-day"),
    pytest.param(NOW - 172800.0, "2.0d", id="float-two-days"),
    # 2**53+1 is INSIDE the helper's int bound, so it is admitted and
    # renders a nonsense but non-raising age. Pinned because it is the
    # behaviour the shipped code already had — the guard neither
    # widened nor narrowed it, and a future change to the bound would
    # show up here rather than silently.
    pytest.param(2 ** 53 + 1, "-9007197454740992s", id="int-2**53+1"),
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
    return {"ts": NOW - 3600.0, "source": "bot-parent",
            "usd": 42.5, "ref": "scrum@30000.00000000"}


def _valid_tx():
    """One realistic recent transaction, every field valid."""
    return _Tx(timestamp=int(NOW) - 7200, source_bot=BOT_ID,
               target_bot="bot-child", amount=17.25,
               wire_type="SCRUM_ROUTE")


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
        _wires = ({BOT_ID: {"bot-child": 25.0},
                   "bot-parent": {BOT_ID: 40.0}} if full else {})
        _ledgers = ({BOT_ID: _Ledger(), "bot-child": _Ledger(),
                     "bot-parent": _Ledger()} if full else {})
        _transactions = tx_list
        _bot_refs: dict = {}

    class _StubBot:
        _smart_wire_mgr = _Mgr()
        bot_id = BOT_ID
        _pending_wire_ledger = list(credits) if credits is not None else []
        _pending_wire_credits = 42.5

    class _StubDlg:
        # `_format_age` is a @staticmethod; binding it here without the
        # re-wrap would silently make it an instance method and pass
        # `self` as `seconds`.
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
        got = [tbl.horizontalHeaderItem(c).text()
               for c in range(tbl.columnCount())
               if tbl.horizontalHeaderItem(c) is not None]
        if got == headers:
            return tbl
    raise AssertionError(f"no table with headers {headers}")


def _rows(widget, headers):
    tbl = _table(widget, headers)
    return [[(tbl.item(r, c).text() if tbl.item(r, c) else None)
             for c in range(tbl.columnCount())]
            for r in range(tbl.rowCount())]


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


# ---------------------------------------------------------------------
# (a) THE TAB BUILDS.
#     A failure here means a corrupted or hand-edited bot_state.json
#     stops the Bot Settings dialog from opening for that bot at all.
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# (b) VALID INPUT RENDERS IDENTICALLY.
#     A failure here means the guard changed a real, readable age —
#     the fix would be silently rewriting the operator's data.
# ---------------------------------------------------------------------

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


@pytest.mark.parametrize("literal,decoded", [
    ('{"ts": Infinity}', float("inf")),
    ('{"ts": -Infinity}', float("-inf")),
    ('{"ts": NaN}', float("nan")),
])
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
    assert row == ["1.0h", "bot-parent", "$42.5000",
                   "scrum@30000.00000000"]


def test_the_other_transaction_cells_are_untouched(monkeypatch):
    widget = _build(monkeypatch, txs=[_valid_tx()])
    row = _rows(widget, RECENT_HEADERS)[0]
    assert row == ["2.0h", "OUT →", "bot-child", "$17.2500",
                   "SCRUM_ROUTE"]


# ---------------------------------------------------------------------
# (c) THE REFUSAL USES THE EXISTING BRANCH.
#     A failure here means the fix invented a new "no value" string,
#     so the same absence would read two different ways in one tab.
# ---------------------------------------------------------------------

def test_refusal_string_equals_the_absent_timestamp_string(monkeypatch):
    """A refused value must render what an ABSENT one already rendered.

    `omit=True` takes the pre-existing else-branch — the one that
    shipped before this unit — and every refused shape must land on the
    identical string.
    """
    absent_dict = _dict_age(None, monkeypatch, omit=True)
    absent_obj = _obj_age(None, monkeypatch, omit=True)
    assert absent_dict == absent_obj == DASH
    for probe in (float("inf"), 10 ** 400, [1, 2], True, "abc"):
        assert _dict_age(probe, monkeypatch) == absent_dict
        assert _obj_age(probe, monkeypatch) == absent_obj


def test_refusal_is_the_dash_the_file_already_used():
    """The dash is U+2014, not a hyphen and not an en dash."""
    assert DASH == "—"
    assert len(DASH) == 1


# ---------------------------------------------------------------------
# (d) THE GUARD MUST NOT OPEN THE HOLE IT CLOSES.
#     A failure here means the guard itself raises on the value it
#     exists to refuse — `math.isfinite(10 ** 400)` raises
#     OverflowError, so an isfinite-first guard would be worse than
#     none at all.
# ---------------------------------------------------------------------

def test_huge_int_does_not_raise_inside_the_guard():
    import math

    from src.trading.bot_container import as_finite_float

    with pytest.raises(OverflowError):
        math.isfinite(10 ** 400)
    assert as_finite_float(10 ** 400) is None
    assert as_finite_float(2 ** 1023 + 1) is None
    # The bound is inclusive, and a float at 1e308 is still accepted —
    # only the INT path carries the bound.
    assert as_finite_float(2 ** 1023) == float(2 ** 1023)
    assert as_finite_float(1e308) == 1e308


@pytest.mark.parametrize("value", [10 ** 400, 2 ** 1023 + 1])
def test_huge_int_does_not_raise_through_either_tab_site(
        value, monkeypatch):
    assert _dict_age(value, monkeypatch) == DASH
    assert _obj_age(value, monkeypatch) == DASH


# ---------------------------------------------------------------------
# THE CALL SITES THEMSELVES.
#     A failure here means a sixth variant of the admission rule was
#     written instead of the shipped helper being reused, or a bare
#     read was reintroduced beside a guarded one.
# ---------------------------------------------------------------------

def _swarm_tab_source():
    import inspect
    import textwrap

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    return textwrap.dedent(inspect.getsource(
        BotLiveSettingsDialog._create_bot_swarm_tab))


def test_no_bare_float_read_feeds_format_age(monkeypatch):
    """Walk the AST: every `_format_age` argument must be guarded.

    Text matching would pass on a commented-out example. This resolves
    the name each call's argument was assigned from and requires it to
    come from the admission helper.
    """
    import ast

    tree = ast.parse(_swarm_tab_source())
    guarded = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "_as_finite_float"):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    guarded.add(tgt.id)

    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_format_age"]
    assert len(calls) == 2, "both Age columns must still be here"

    for call in calls:
        arg = call.args[0]
        names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
        assert names & guarded, (
            f"_format_age argument {ast.unparse(arg)!r} is not fed by "
            "_as_finite_float")


def test_the_guard_is_the_shipped_helper_not_a_local_copy():
    """No sixth variant: the name must resolve to bot_container's."""
    import ast

    tree = ast.parse(_swarm_tab_source())
    imported = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and any(a.name == "as_finite_float"
                and a.asname == "_as_finite_float" for a in n.names)]
    assert imported, "the helper must be imported, not redefined"
    assert not [n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef)
                and n.name.endswith("finite_float")], (
        "a local re-implementation of the admission rule")
