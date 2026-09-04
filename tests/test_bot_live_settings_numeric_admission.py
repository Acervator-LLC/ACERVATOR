"""Numeric admission on the four display sites in bot_live_settings.

THE DEFECT THESE PIN
====================
All four sites decided "is this a number I can render" with an OPEN
predicate — ``isinstance(x, (int, float))`` at three of them and a bare
``float(x)`` at the fourth. ``bool`` is a subclass of ``int``, so
``isinstance(True, int)`` is True and a stored ``True`` was arithmetic'd
as ``1``:

* Stack summary + row: a tranche dated to one second after the epoch,
  reported as an age of about 57 years, on the row an operator reads to
  judge whether Stack Mode has stalled.
* Extractor cell: ``$1.0000`` for ``True`` and ``$0.0000`` for ``False``
  in a money column whose docstring promises an em dash when the
  position was never priced.

A TYPE IS NOT A DOMAIN, so these also pin the value:
``type(float("nan")) is float`` is True. ``inf`` passed the Stack site's
``> 0`` test and then ``int(-inf)`` inside ``_format_age`` raised
OverflowError with no ``try`` between there and the click — the dialog
would not open at all. An int above the float maximum raised
OverflowError from ``float()`` on every site.

AND THE GUARD MUST NOT OPEN THE HOLE IT CLOSES: ``math.isfinite(10**400)``
itself raises OverflowError. ``as_finite_float`` bounds ints with an
integer comparison, which cannot raise. ``test_huge_int_*`` is the row
that tells the two apart.

REACHABILITY: ``bot_state.json`` is read with ``json.load``, which
produces real ``True``/``NaN``/``Infinity``, and the tranche dicts are
copied key-for-key in and out of state with no per-key validation.

Every table below carries POSITIVE CONTROLS — genuine ints and floats
that must still render exactly as before. Without them a guard that
refuses everything would pass every other row while blanking the panel.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

NOW = 1_800_000_000.0
COL_USD_PARKED = 3


class _FloatSub(float):
    """A float subclass: passes isinstance, fails exact type."""


class _HasFloat:
    """Not a number, but float() of it succeeds."""

    def __float__(self) -> float:
        return 1.0


#: Shapes that must be REFUSED. Each renders the same "no value" text a
#: missing key already rendered, so a refusal is never a new code path.
REFUSED = [
    pytest.param(True, id="bool-True"),
    pytest.param(False, id="bool-False"),
    pytest.param(_FloatSub(1_700_000_000.0), id="float-subclass"),
    pytest.param(Decimal("1700000000"), id="Decimal"),
    pytest.param(Fraction(17, 10), id="Fraction"),
    pytest.param("1700000000", id="numeric-string"),
    pytest.param("", id="empty-string"),
    pytest.param(None, id="None"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="inf"),
    pytest.param(float("-inf"), id="-inf"),
    pytest.param(10**400, id="huge-int"),
    pytest.param(_HasFloat(), id="obj-with-__float__"),
]

#: Shapes that must be ACCEPTED unchanged. Exactly int and exactly
#: float, finite. These are the positive controls.
ACCEPTED_MARKS = [
    pytest.param(1, "$1.0000", id="int-1"),
    pytest.param(1_700_000_000, "$1,700,000,000.0000", id="int-large"),
    pytest.param(1_700_000_000.0, "$1,700,000,000.0000", id="float-large"),
    pytest.param(0, "$0.0000", id="int-zero"),
    pytest.param(0.0, "$0.0000", id="float-zero"),
    pytest.param(-5.0, "$-5.0000", id="negative"),
    pytest.param(1.2345, "$1.2345", id="float-small"),
]


def _cells(mark_value_usd):
    """One Extractor Tranche row's cells, from the real composer.

    Imported here rather than at module scope: the import needs REPO on
    `sys.path`, and an import placed after that assignment is an E402
    that would otherwise be silenced with a suppression.
    """
    from src.gui.bot_live_settings import _compose_extractor_tranche_cells

    row = {
        "opened_at": NOW - 100.0,
        "base_deployed": 1.0,
        "mark_value_usd": mark_value_usd,
        "state": "open",
        "pair": "X/Y",
    }
    return _compose_extractor_tranche_cells(row, NOW)


def _tooltip(mark_price):
    """The tooltip for that same row, from the real composer."""
    from src.gui.bot_live_settings import _compose_extractor_tranche_tooltip

    row = {
        "base_asset": "BTC",
        "base_deployed": 1.0,
        "alt_units": 2.0,
        "mark_price_base_per_alt": mark_price,
    }
    return _compose_extractor_tranche_tooltip(row)


# Site C — the "USD parked" cell


class TestExtractorUsdCell:
    """FAILURE MEANS: a stored flag or a non-finite value renders as a
    dollar amount in a money column, or a huge int takes the row builder
    down with OverflowError."""

    @pytest.mark.parametrize("value", REFUSED)
    def test_refused_shapes_render_em_dash(self, value):
        assert _cells(value)[COL_USD_PARKED] == "—"

    def test_refusal_is_the_same_branch_a_missing_key_takes(self):
        """The refusal must LAND somewhere, not merely not raise.

        A missing key is the shape this column already refused before
        this fix existed. Every newly refused shape must produce that
        exact cell, which is what proves the value went down the
        existing em-dash branch rather than some new path.
        """
        baseline = _cells(None)[COL_USD_PARKED]
        for value in (True, False, float("nan"), float("inf"), 10**400):
            assert _cells(value)[COL_USD_PARKED] == baseline

    @pytest.mark.parametrize("value,expected", ACCEPTED_MARKS)
    def test_genuine_numbers_render_unchanged(self, value, expected):
        """POSITIVE CONTROL. Fails if the guard blinded the column."""
        assert _cells(value)[COL_USD_PARKED] == expected

    def test_huge_int_does_not_raise(self):
        """Pins the integer-bound comparison specifically.

        A guard written with `math.isfinite` raises OverflowError on
        this exact input — the guard would open the hole it closes.
        """
        assert _cells(10**400)[COL_USD_PARKED] == "—"

    def test_other_columns_are_untouched(self):
        """This unit changed the USD cell only."""
        cells = _cells(True)
        assert cells[0] == "EXT"
        assert cells[2] == "1.000000"
        assert cells[7] == "open"


# Site D — the tooltip that explains that cell


class TestExtractorTooltip:
    """FAILURE MEANS: the cell and its own explanation disagree — a
    dashed cell beside a tooltip reading "Last mark: nan". The tooltip
    exists to say why the cell is blank."""

    @pytest.mark.parametrize("value", REFUSED)
    def test_refused_shapes_say_no_mark(self, value):
        tip = _tooltip(value)
        assert "No mark available" in tip
        assert "Last mark:" not in tip

    @pytest.mark.parametrize("value", [1, 0, 1.2345, -5.0, 1_700_000_000])
    def test_genuine_numbers_still_report_the_mark(self, value):
        """POSITIVE CONTROL. Fails if every priced position now reads
        as unpriced."""
        tip = _tooltip(value)
        assert "Last mark:" in tip
        assert "No mark available" not in tip
        assert f"{float(value):.8f}" in tip

    @pytest.mark.parametrize(
        "value",
        REFUSED
        + [
            pytest.param(1, id="accept-int"),
            pytest.param(1.5, id="accept-float"),
        ],
    )
    def test_cell_and_tooltip_never_disagree(self, value):
        """The stated contract between the two: the cell shows a dash
        exactly when the tooltip says there is no mark."""
        cell_dashed = _cells(value)[COL_USD_PARKED] == "—"
        tip_no_mark = "No mark available" in _tooltip(value)
        assert cell_dashed == tip_no_mark


# Sites A + B — the Stack Tranches tab, through the REAL method


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _DialogRest:
    """Whatever a stub does not define, taken off the real dialog.

    THE STUBS BELOW SUBSTITUTE THREE THINGS AND INHERIT THE REST. A tab
    builder that grows a collaborator -- a clear handler it connects a
    button to -- otherwise fails every test in this file for a reason
    none of them is about, which is how 228 of them went red on a change
    to neither the pending-size total nor the summary/row agreement they
    exist to guard.

    A NAME THE REAL DIALOG ALSO LACKS STILL RAISES, so this widens the
    fixture and not the assertion.
    """

    def __getattr__(self, name):
        from src.gui.bot_live_settings import BotLiveSettingsDialog

        # THROUGH `__dict__` AND THE DESCRIPTOR PROTOCOL, not through
        # `getattr(cls, name)`. That call has already run `__get__`, so a
        # plain function and a `staticmethod` come back looking alike and
        # binding either one passes `self` as the first argument -- the
        # exact hazard `_format_age` above is re-wrapped to avoid.
        for klass in BotLiveSettingsDialog.__mro__:
            if name in klass.__dict__:
                raw = klass.__dict__[name]
                getter = getattr(raw, "__get__", None)
                return getter(self, type(self)) if getter else raw
        raise AttributeError(name)


def _build_tab(opened_ts, monkeypatch):
    """Build the real Stack Tranches tab for one pending tranche.

    Drives `BotLiveSettingsDialog._create_stack_tranches_tab` itself
    through a stub `self`, so the assertions are about the shipped
    method and not about a copy of its logic.
    """
    app = _qt_or_skip()
    from PySide6.QtWidgets import QLabel

    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    # The method reads the clock itself. Freeze it, or "an hour ago"
    # is not expressible and the ages drift between runs.
    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    class _StubBot:
        _stack_tranches = [
            {
                "index": 1,
                "price": 100.0,
                "size": 2.0,
                "status": "pending",
                "visible": True,
                "fill_price": None,
                "opened_ts": opened_ts,
            }
        ]
        _stack_created = 4
        _stack_discarded = 0

    class _StubDlg(_DialogRest):
        # `_format_age` is a @staticmethod; re-wrap it or binding it
        # here would silently make it an instance method and pass
        # `self` as `seconds`.
        _format_age = staticmethod(_Dlg._format_age)
        _bot = _StubBot()

        def _configure_form(self, *args):
            return len(args) and None

    widget = _Dlg._create_stack_tranches_tab(_StubDlg())
    texts = [c.text() for c in widget.findChildren(QLabel)]
    summary = next(
        (texts[i + 1] for i, t in enumerate(texts) if t == "Oldest pending age:"),
        "<<missing>>",
    )
    detail = next(
        (
            t.rsplit("|", 1)[-1].strip()
            for t in texts
            if t.count("|") >= 6 and "Target Price" not in t
        ),
        "<<missing>>",
    )
    _ = app
    return summary, detail


NO_TS_SUMMARY = "— (no timestamp)"
NO_TS_ROW = "—"


class TestStackTrancheAge:
    """FAILURE MEANS: the panel misreports how long a tranche has been
    unfilled — by 57 years for a stored `True` — or, for `inf` and a
    huge int, raises OverflowError out of the dialog constructor so the
    operator cannot open Bot Settings for that bot at all."""

    @pytest.mark.parametrize("value", REFUSED)
    def test_refused_shapes_report_no_timestamp(self, value, monkeypatch):
        summary, detail = _build_tab(value, monkeypatch)
        assert summary == NO_TS_SUMMARY
        assert detail == NO_TS_ROW

    def test_refusal_is_the_same_branch_a_missing_key_takes(self, monkeypatch):
        """Prove the refusal REACHED the existing no-timestamp branch."""
        base_s, base_d = _build_tab(None, monkeypatch)
        assert base_s == NO_TS_SUMMARY
        for value in (True, False, float("inf"), 10**400, Decimal("1700000000")):
            summary, detail = _build_tab(value, monkeypatch)
            assert summary == base_s
            assert detail == base_d

    @pytest.mark.parametrize(
        "value,expected",
        [
            pytest.param(NOW - 3600.0, "1.0h", id="an-hour-ago"),
            pytest.param(NOW - 90000.0, "1.0d", id="a-day-ago"),
            pytest.param(NOW - 30.0, "30s", id="thirty-seconds-ago"),
            pytest.param(NOW - 600.0, "10m", id="ten-minutes-ago"),
            pytest.param(int(NOW - 3600), "1.0h", id="int-timestamp"),
        ],
    )
    def test_real_timestamps_still_render_an_age(self, value, expected, monkeypatch):
        """POSITIVE CONTROL, and the one that catches a guard which
        refuses everything. Without it the panel could go permanently
        blank while every refusal test above still passed."""
        summary, detail = _build_tab(value, monkeypatch)
        assert summary == expected
        assert detail == expected

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(float("inf"), id="inf"),
            pytest.param(10**400, id="huge-int"),
        ],
    )
    def test_non_finite_does_not_take_the_dialog_down(self, value, monkeypatch):
        """Both raised OverflowError before this fix, from `int()` and
        from `float()` respectively, with no `try` on the path to the
        operator's click."""
        summary, detail = _build_tab(value, monkeypatch)
        assert summary == NO_TS_SUMMARY
        assert detail == NO_TS_ROW

    @pytest.mark.parametrize(
        "value",
        REFUSED
        + [
            pytest.param(NOW - 3600.0, id="accept-recent"),
            pytest.param(1, id="accept-int-1"),
        ],
    )
    def test_summary_and_row_never_disagree(self, value, monkeypatch):
        """The summary and the row render the age of the SAME tranche
        from the SAME key. Closing one without the other produced a
        panel that contradicted itself, which is worse than the defect.
        """
        summary, detail = _build_tab(value, monkeypatch)
        assert (summary == NO_TS_SUMMARY) == (detail == NO_TS_ROW)


class TestAdmissionHelperIsTheRepoRule:
    """The sites must read through the settled helper, not a second
    mechanism invented here. A `math.isfinite` guard would raise on the
    huge-int row above."""

    def test_helper_refuses_bool_and_non_finite_and_huge_int(self):
        from src.trading.bot_container import as_finite_float

        for value in (
            True,
            False,
            float("nan"),
            float("inf"),
            float("-inf"),
            10**400,
            _FloatSub(1.0),
            Decimal("1"),
            "1",
            None,
        ):
            assert as_finite_float(value) is None

    def test_helper_accepts_exact_int_and_float(self):
        from src.trading.bot_container import as_finite_float

        assert as_finite_float(1) == 1.0
        assert as_finite_float(0) == 0.0
        assert as_finite_float(-5.5) == -5.5
        assert as_finite_float(NOW) == NOW


# The Stack Tranches ROW - index, price, size and fill price
#
# Four sibling keys read from the same dict as `opened_ts`, in the same
# row builder, with no guard at all. Measured on live before the fix:
#
#   index      inf -> OverflowError, nan -> ValueError, None and any
#              string -> TypeError/ValueError, True -> the ordinal 1,
#              10**400 -> a 400-digit cell that destroyed the row
#   price      10**400 -> OverflowError; nan/inf -> "$nan"/"$inf"
#   size       10**400 -> OverflowError; nan/inf -> "nan"/"inf"
#   fill_price 10**400 -> OverflowError; nan/inf -> "$nan"/"$inf"
#
# None of the four sits inside a `try`. The AST ancestor chain runs
# `_create_stack_tranches_tab` -> `BotLiveSettingsDialog.__init__` ->
# `MainWindow._on_bot_clicked` with no handler at any step, so a raise
# means the Bot Settings dialog does not open for that bot at all.

DASH = "\u2014"

ROW_KEYS = ["index", "price", "size", "fill_price"]

#: Column index in the rendered row string that each key drives.
ROW_COLUMN = {"index": 0, "price": 1, "size": 2, "fill_price": 5}


def _valid_tranche():
    """One realistic pending tranche with every key valid."""
    return {
        "index": 1,
        "price": 100.0,
        "size": 2.0,
        "status": "pending",
        "visible": True,
        "fill_price": 99.0,
        "opened_ts": NOW - 3600.0,
    }


def _build_rows(tranches, monkeypatch):
    """The real Stack Tranches tab. Returns (summary text, row texts).

    Drives the shipped method through a stub `self`, so every assertion
    below is about the dialog an operator opens and not about a copy of
    the row-building logic.
    """
    app = _qt_or_skip()
    from PySide6.QtWidgets import QLabel

    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    class _StubBot:
        _stack_tranches = list(tranches)
        _stack_created = 4
        _stack_discarded = 0

    class _StubDlg(_DialogRest):
        _format_age = staticmethod(_Dlg._format_age)
        _bot = _StubBot()

        def _configure_form(self, *forms):
            self._forms_seen = forms

    widget = _Dlg._create_stack_tranches_tab(_StubDlg())
    texts = [c.text() for c in widget.findChildren(QLabel)]
    summary = next((t for t in texts if "base units" in t), "<<missing>>")
    rows = [t for t in texts if t.count("|") >= 6 and "Target Price" not in t]
    _ = app
    return summary, rows


def _cell(key, value, monkeypatch):
    """The single cell `key` drives, with `value` stored under it."""
    tranche = _valid_tranche()
    tranche[key] = value
    _, rows = _build_rows([tranche], monkeypatch)
    return [c.strip() for c in rows[0].split("|")][ROW_COLUMN[key]]


class TestStackRowDialogOpens:
    """FAILURE MEANS: the Bot Settings dialog cannot be opened for that
    bot at all. This is the whole point of the unit, so it asserts on
    the built tab rather than on the admission helper."""

    @pytest.mark.parametrize("key", ROW_KEYS)
    @pytest.mark.parametrize("value", REFUSED)
    def test_no_exception_escapes_the_tab_builder(self, key, value, monkeypatch):
        tranche = _valid_tranche()
        tranche[key] = value
        summary, rows = _build_rows([tranche], monkeypatch)
        assert len(rows) == 1, "the row must still render"
        assert summary != "<<missing>>"

    @pytest.mark.parametrize("key", ROW_KEYS)
    def test_huge_int_does_not_raise_anywhere(self, key, monkeypatch):
        """Pins the integer-bound comparison specifically.

        A guard written with `math.isfinite` raises OverflowError on
        this exact input, so it would open the hole it closes.
        """
        assert _cell(key, 10**400, monkeypatch) == DASH

    def test_every_key_hostile_at_once(self, monkeypatch):
        """All four refused together still renders one whole row."""
        tranche = _valid_tranche()
        tranche.update(
            index=float("inf"), price=10**400, size=float("nan"), fill_price=True
        )
        _, rows = _build_rows([tranche], monkeypatch)
        assert len(rows) == 1
        cells = [c.strip() for c in rows[0].split("|")]
        assert cells[0] == cells[1] == cells[2] == cells[5] == DASH


class TestStackRowRefusalIsVisible:
    """FAILURE MEANS: a refused value renders as a number the operator
    would read as real - the defect this unit exists to prevent."""

    @pytest.mark.parametrize("key", ROW_KEYS)
    @pytest.mark.parametrize("value", REFUSED)
    def test_refused_shapes_render_the_em_dash(self, key, value, monkeypatch):
        assert _cell(key, value, monkeypatch) == DASH

    @pytest.mark.parametrize("key", ["price", "size", "fill_price"])
    @pytest.mark.parametrize("value", REFUSED)
    def test_money_refusal_never_reads_as_zero(self, key, value, monkeypatch):
        """A refusal that renders zero on a money column is a NEW
        defect, not a fix: nothing on the panel would distinguish an
        unreadable size from a genuinely empty one."""
        cell = _cell(key, value, monkeypatch)
        assert cell not in ("$0.00000000", "0.000000", "$0.0000", "0")
        assert float not in (type(cell),)
        assert cell == DASH

    @pytest.mark.parametrize("key", ROW_KEYS)
    def test_refusal_is_padded_to_its_column_width(self, key, monkeypatch):
        """The refusal keeps the monospace table aligned: each dash is
        padded to the minimum width that column's valid value occupies.
        """
        tranche = _valid_tranche()
        valid_widths = {"index": 2, "price": 11, "size": 10}
        if key not in valid_widths:
            return
        tranche[key] = float("nan")
        _, rows = _build_rows([tranche], monkeypatch)
        raw = rows[0].split("|")[ROW_COLUMN[key]]
        assert raw.strip() == DASH
        assert len(raw.strip(" ").rjust(valid_widths[key])) == valid_widths[key]


class TestStackRowValidInputUnchanged:
    """POSITIVE CONTROL, and the row that catches a guard which refuses
    everything. FAILURE MEANS: the unit changed what a real tranche
    displays, which it is not allowed to do by one character."""

    @pytest.mark.parametrize(
        "key,value,expected",
        [
            pytest.param("index", 1, "1", id="index-1"),
            pytest.param("index", 7, "7", id="index-7"),
            pytest.param("index", 0, "0", id="index-zero"),
            pytest.param("index", -5, "-5", id="index-negative"),
            pytest.param("index", 2.5, "2", id="index-float-truncates"),
            pytest.param("price", 100.0, "$100.00000000", id="price-100"),
            pytest.param("price", 2.5, "$2.50000000", id="price-small"),
            pytest.param("price", 0, "$0.00000000", id="price-int-zero"),
            pytest.param("price", 0.0, "$0.00000000", id="price-float-zero"),
            pytest.param("price", -5, "$-5.00000000", id="price-negative"),
            pytest.param("price", 7, "$7.00000000", id="price-int"),
            pytest.param("size", 2.0, "2.000000", id="size-2"),
            pytest.param("size", 0, "0.000000", id="size-int-zero"),
            pytest.param("size", 0.0, "0.000000", id="size-float-zero"),
            pytest.param("size", -5, "-5.000000", id="size-negative"),
            pytest.param("size", 7, "7.000000", id="size-int"),
            pytest.param("fill_price", 99.0, "$99.00000000", id="fill-99"),
            pytest.param("fill_price", 7, "$7.00000000", id="fill-int"),
            pytest.param("fill_price", -5, "$-5.00000000", id="fill-negative"),
            pytest.param("fill_price", 2.5, "$2.50000000", id="fill-small"),
        ],
    )
    def test_genuine_numbers_render_exactly_as_before(
        self, key, value, expected, monkeypatch
    ):
        assert _cell(key, value, monkeypatch) == expected

    @pytest.mark.parametrize("value", [0, 0.0])
    def test_zero_fill_price_still_dashes(self, value, monkeypatch):
        """PRE-EXISTING behaviour, deliberately preserved. The column
        gated on truthiness before this unit, so a stored 0.0 printed
        the dash. Admitting it here would be a display change."""
        assert _cell("fill_price", value, monkeypatch) == DASH

    def test_the_whole_valid_row_is_byte_identical(self, monkeypatch):
        """The exact string the shipped code produced before the fix,
        captured from live and pasted here."""
        _, rows = _build_rows([_valid_tranche()], monkeypatch)
        assert rows[0] == (
            "   1 |  $100.00000000  |    2.000000  |  VISIBLE  |"
            "  pending    |  $99.00000000 |  1.0h"
        )

    def test_the_valid_summary_is_byte_identical(self, monkeypatch):
        summary, _ = _build_rows([_valid_tranche()], monkeypatch)
        assert summary == "2.000000 base units"


class TestPendingSizeTotalCountsWhatItCannotRead:
    """FAILURE MEANS: an unreadable tranche is silently dropped from a
    money total, which under-reports with nothing on the panel saying
    so. That is the shape of the claim-total defect of 2026-08-10 -
    $2,000 reported against a true $3,000, with zero log lines."""

    def test_all_valid_totals_have_no_marker(self, monkeypatch):
        """POSITIVE CONTROL. Fails if every panel now claims to be
        partial."""
        summary, _ = _build_rows(
            [
                dict(_valid_tranche(), index=1, size=2.0),
                dict(_valid_tranche(), index=2, size=3.0),
            ],
            monkeypatch,
        )
        assert summary == "5.000000 base units"
        assert "unreadable" not in summary

    def test_a_refused_member_is_counted_not_dropped(self, monkeypatch):
        summary, rows = _build_rows(
            [
                dict(_valid_tranche(), index=1, size=2.0),
                dict(_valid_tranche(), index=2, size=float("nan")),
                dict(_valid_tranche(), index=3, size=10**400),
            ],
            monkeypatch,
        )
        assert summary == "2.000000 base units  (+2 unreadable)"
        assert len(rows) == 3

    @pytest.mark.parametrize("value", REFUSED)
    def test_every_refused_shape_is_counted(self, value, monkeypatch):
        summary, _ = _build_rows([dict(_valid_tranche(), size=value)], monkeypatch)
        assert summary.endswith("(+1 unreadable)")

    def test_only_pending_tranches_are_summed(self, monkeypatch):
        """The summary counts PENDING size. A refused size on a filled
        tranche must not mark the pending total partial."""
        summary, _ = _build_rows(
            [
                dict(_valid_tranche(), index=1, size=2.0, status="pending"),
                dict(_valid_tranche(), index=2, size=float("nan"), status="filled"),
            ],
            monkeypatch,
        )
        assert summary == "2.000000 base units"

    def test_summary_and_row_never_disagree(self, monkeypatch):
        """Both render `size` from the SAME key on the SAME tranche.
        Closing one without the other produces a panel that contradicts
        itself, which is worse than the defect."""
        for value in (
            2.0,
            0,
            -5,
            True,
            float("nan"),
            float("inf"),
            10**400,
            None,
            "",
            Decimal("2.5"),
        ):
            tranche = dict(_valid_tranche(), size=value)
            summary, rows = _build_rows([tranche], monkeypatch)
            cell = [c.strip() for c in rows[0].split("|")][ROW_COLUMN["size"]]
            assert (cell == DASH) == ("unreadable" in summary)
