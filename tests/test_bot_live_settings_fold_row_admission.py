"""Numeric admission on the fold-tranche row of the Bot Settings dialog.

`_build` drives the shipped `_create_fold_tranches_tab` through a stub `self`,
so every assertion is about the tab an operator opens. `TestTheDialogOpens`,
`TestTheRefusalIsHonest` and `TestTheParkedTotalCountsWhatItCannotRead` hold
every shape in REFUSED to DASH, and `TestValidInputIsByteIdentical` holds
LIVE_LABELS and LIVE_ROW as the positive control.
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

#: Frozen clock. The method reads the wall clock itself, so without this
#: "an hour ago" is not expressible and every age drifts between runs.
NOW = 1_800_000_000.0

DASH = "—"
NO_TS_SUMMARY = "— (pre-v3.16.39 tranches, no timestamp)"

#: Column indices in the per-tranche detail table.
COL_AGE = 1
COL_UNITS = 2
COL_USD = 3
COL_REF = 4
COL_COST = 5
COL_MIN_REBUY = 6
COL_STATUS = 7

#: The five keys this unit closed, and the cell each one drives.
MONEY_KEYS = ["units", "usd", "ref", "initial_buy_price"]
KEY_COLUMN = {
    "units": COL_UNITS,
    "usd": COL_USD,
    "ref": COL_REF,
    "initial_buy_price": COL_COST,
    "created_ts": COL_AGE,
}
ALL_KEYS = MONEY_KEYS + ["created_ts"]


class _FloatSub(float):
    """A float subclass: passes isinstance, fails exact type."""


class _HasFloat:
    """Not a number, but float() of it succeeds."""

    def __float__(self) -> float:
        return 1.0


#: Shapes that must be REFUSED. Each renders the same "no value" text
#: the column already used, so a refusal is never a new code path.
REFUSED = [
    pytest.param(True, id="bool-True"),
    pytest.param(False, id="bool-False"),
    pytest.param(_FloatSub(7.0), id="float-subclass"),
    pytest.param(Decimal("2.5"), id="Decimal"),
    pytest.param(Fraction(5, 2), id="Fraction"),
    pytest.param("2.5", id="numeric-string"),
    pytest.param("", id="empty-string"),
    pytest.param(None, id="None"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="inf"),
    pytest.param(float("-inf"), id="-inf"),
    pytest.param(10**400, id="huge-int"),
    pytest.param(_HasFloat(), id="obj-with-__float__"),
    pytest.param([1.0], id="list"),
    pytest.param({"a": 1}, id="dict"),
]


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _valid_tranche():
    """One realistic fold tranche with every key valid.

    The numbers are the ones the live probe used, so the expected
    strings pasted into this file are the strings the shipped code
    produced for exactly this dict.
    """
    return {
        "units": 1.5,
        "usd": 250.0,
        "ref": 30000.0,
        "initial_buy_price": 29000.0,
        "created_ts": NOW - 3600.0,
        "operator_initiated": False,
    }


def _build(tranches, monkeypatch, cur_price=31000.0):
    """Build the REAL Fold Tranches tab. Returns (labels, rows).

    Drives ``BotLiveSettingsDialog._create_fold_tranches_tab`` itself
    through a stub ``self``, so every assertion below is about the tab
    an operator opens and not about a copy of its logic. Asserting on
    the admission helper instead would prove nothing about the dialog.
    """
    app = _qt_or_skip()
    from PySide6.QtWidgets import QLabel, QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    class _Cfg:
        scrumming_interval_pct = 1.5

    class _StubBot:
        _fold_tranches = list(tranches)
        _tranches_created_lifetime = 10
        _tranches_closed_lifetime = 6
        _tranches_discarded_lifetime = 0
        _pending_wire_credits = 12.5
        config = _Cfg()
        bot_id = "bot-fold-test"

        def get_status(self):
            return {"stats": {"current_price": cur_price}}

    class _StubDlg:
        # Without the re-wrap `_format_age` binds as an instance method and
        # takes `self` as `seconds`.
        _format_age = staticmethod(_Dlg._format_age)
        _paint_fold_tranche_row = _Dlg._paint_fold_tranche_row
        _paint_extractor_tranche_rows = _Dlg._paint_extractor_tranche_rows
        _bot = _StubBot()

        def _configure_form(self, *forms):
            self._forms_seen = forms

        def _on_clear_fold_tranches(self):
            return None

        def _on_clear_wire_credits(self):
            return None

        def _on_clear_lifetime_counters(self):
            return None

        def _on_fire_tranche_clicked(self, tranche):
            return None

    widget = _Dlg._create_fold_tranches_tab(_StubDlg())
    labels = [c.text() for c in widget.findChildren(QLabel)]
    rows = []
    for table in widget.findChildren(QTableWidget)[:1]:
        for r in range(table.rowCount()):
            rows.append(
                [
                    (table.item(r, c).text() if table.item(r, c) else None)
                    for c in range(table.columnCount())
                ]
            )
    _ = app
    return labels, rows


def _summary(labels, key):
    """The value QLabel that follows the named form-row label."""
    for i, text in enumerate(labels):
        if text == key:
            return labels[i + 1] if i + 1 < len(labels) else "<<end>>"
    return "<<missing>>"


def _cell(key, value, monkeypatch, column=None):
    """The one cell `key` drives, with `value` stored under it."""
    tranche = _valid_tranche()
    tranche[key] = value
    _, rows = _build([tranche], monkeypatch)
    assert len(rows) == 1, "the row must still render"
    return rows[0][column if column is not None else KEY_COLUMN[key]]


def _parked(labels):
    return _summary(labels, "Parked USD (in fold queue):")


# CONTROL A - THE DIALOG OPENS


class TestTheDialogOpens:
    """FAILURE MEANS: the operator cannot open Bot Settings for that bot
    at all. Five of the seven sites raised OverflowError or TypeError on
    a shape `json.load` can produce, with no `try` between there and the
    click. This is the whole point of the unit, so it asserts on the
    built tab and never on the admission helper."""

    @pytest.mark.parametrize("key", ALL_KEYS)
    @pytest.mark.parametrize("value", REFUSED)
    def test_no_exception_escapes_the_tab_builder(self, key, value, monkeypatch):
        tranche = _valid_tranche()
        tranche[key] = value
        labels, rows = _build([tranche], monkeypatch)
        assert len(rows) == 1, "the row must still render"
        assert _summary(labels, "Open tranches:") == "1"
        assert _parked(labels) != "<<missing>>"

    def test_every_key_hostile_at_once(self, monkeypatch):
        """All five refused together still renders one whole row."""
        tranche = _valid_tranche()
        tranche.update(
            units=float("inf"),
            usd=10**400,
            ref=float("nan"),
            initial_buy_price=True,
            created_ts=float("inf"),
        )
        labels, rows = _build([tranche], monkeypatch)
        assert len(rows) == 1
        for col in (
            COL_AGE,
            COL_UNITS,
            COL_USD,
            COL_REF,
            COL_COST,
            COL_MIN_REBUY,
            COL_STATUS,
        ):
            assert rows[0][col] == DASH
        assert _summary(labels, "Oldest tranche age:") == NO_TS_SUMMARY

    def test_a_hostile_tranche_does_not_hide_a_healthy_one(self, monkeypatch):
        """The refusal is per tranche. A corrupt entry must not blank
        the row beside it, which is what a raise out of the loop did."""
        good = _valid_tranche()
        bad = dict(_valid_tranche(), usd=float("inf"), created_ts=10**400)
        _, rows = _build([good, bad], monkeypatch)
        assert len(rows) == 2
        assert rows[0][COL_USD] == "$250.0000"
        assert rows[0][COL_AGE] == "1.0h"
        assert rows[1][COL_USD] == DASH
        assert rows[1][COL_AGE] == DASH


# CONTROL B - VALID INPUT RENDERS IDENTICALLY

#: Captured from a live bot through the same builder, asserted byte for byte.
LIVE_LABELS = [
    "Open tranches:",
    "1",
    "Parked USD (in fold queue):",
    "$250.0000",
    "Oldest tranche age:",
    "1.0h",
    "Units marked (queue vs held):",
    "1.500000 marked / holdings unreadable",
    "Tranche despawn timer:",
    "Off  -  Settings tab > Advanced > Tranche Despawn Timer",
    "Despawn would remove:",
    (
        "if armed at  7d: 0 ($0.0000)  -  14d: 0 ($0.0000)  -  "
        "30d: 0 ($0.0000)  -  60d: 0 ($0.0000)"
    ),
    "Lifetime tranches opened:",
    "10",
    "Lifetime tranches closed (fold-back fired):",
    "6",
    "Cycle close ratio (folded / opened minus discarded):",
    "60.00%  (6/10)",
    "Tranches dropped as malformed:",
    "0",
    "Fold budget this cycle:",
    "$0.0000 spent of $0.0000",
    "Order:",
]
LIVE_ROW = [
    "1",
    "1.0h",
    "1.500000",
    "$250.0000",
    "$30000.00000000",
    "$29000.00000000",
    "≤$29370.00000000",
    "Need price ≤ OTD (+5.55%)",
    "auto rebalance",
    "",
    DASH,
]


def _digest(obj):
    import hashlib

    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class TestValidInputIsByteIdentical:
    """POSITIVE CONTROL, and the row that catches a guard which refuses
    everything. FAILURE MEANS: the unit changed what a real fold tranche
    displays, which it is not allowed to do by one character. Without
    this the panel could go permanently blank while every refusal test
    above still passed."""

    def test_every_label_is_byte_identical_to_live(self, monkeypatch):
        labels, _ = _build([_valid_tranche()], monkeypatch)
        assert labels == LIVE_LABELS

    def test_the_whole_row_is_byte_identical_to_live(self, monkeypatch):
        _, rows = _build([_valid_tranche()], monkeypatch)
        assert rows[0] == LIVE_ROW

    def test_the_digests_match_the_live_capture(self, monkeypatch):
        """The same assertion as a single hash, so a silent one-space
        drift in any cell is one failing line rather than a diff."""
        labels, rows = _build([_valid_tranche()], monkeypatch)
        assert _digest(labels) == _digest(LIVE_LABELS)
        assert _digest(rows[0]) == _digest(LIVE_ROW)

    def test_the_json_round_trip_renders_identically(self, monkeypatch):
        """THE REAL SAVED PATH. Fold tranches go to `bot_state.json` and
        come back verbatim, so the shapes the panel actually meets are
        whatever `json.loads` produces. A guard that is right in memory
        and wrong after a save is not a fix."""
        restored = json.loads(json.dumps([_valid_tranche()]))
        labels, rows = _build(restored, monkeypatch)
        assert labels == LIVE_LABELS
        assert rows[0] == LIVE_ROW

    @pytest.mark.parametrize(
        "key,value,expected",
        [
            pytest.param("units", 7, "7.000000", id="units-int"),
            pytest.param("units", 0, "0.000000", id="units-int-zero"),
            pytest.param("units", 0.0, "0.000000", id="units-float-zero"),
            pytest.param("units", -5.0, "-5.000000", id="units-negative"),
            pytest.param("usd", 7, "$7.0000", id="usd-int"),
            pytest.param("usd", 0, "$0.0000", id="usd-int-zero"),
            pytest.param("usd", 0.0, "$0.0000", id="usd-float-zero"),
            pytest.param("usd", -5.0, "$-5.0000", id="usd-negative"),
            pytest.param("ref", 7, "$7.00000000", id="ref-int"),
            pytest.param("ref", 0, "$0.00000000", id="ref-int-zero"),
            pytest.param("ref", -5.0, "$-5.00000000", id="ref-negative"),
            pytest.param("initial_buy_price", 7, "$7.00000000", id="cost-int"),
            pytest.param("initial_buy_price", 0, "$0.00000000", id="cost-int-zero"),
            pytest.param("initial_buy_price", -5.0, "$-5.00000000", id="cost-negative"),
        ],
    )
    def test_genuine_numbers_render_exactly_as_live_did(
        self, key, value, expected, monkeypatch
    ):
        assert _cell(key, value, monkeypatch) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            pytest.param(NOW - 30.0, "30s", id="thirty-seconds-ago"),
            pytest.param(NOW - 600.0, "10m", id="ten-minutes-ago"),
            pytest.param(NOW - 3600.0, "1.0h", id="an-hour-ago"),
            pytest.param(NOW - 90000.0, "1.0d", id="a-day-ago"),
            pytest.param(int(NOW - 3600), "1.0h", id="int-timestamp"),
        ],
    )
    def test_real_timestamps_still_render_an_age(self, value, expected, monkeypatch):
        labels, rows = _build([dict(_valid_tranche(), created_ts=value)], monkeypatch)
        assert rows[0][COL_AGE] == expected
        assert _summary(labels, "Oldest tranche age:") == expected

    @pytest.mark.parametrize(
        "key,expected",
        [
            pytest.param("units", "0.000000", id="units"),
            pytest.param("usd", "$0.0000", id="usd"),
            pytest.param("ref", "$0.00000000", id="ref"),
            pytest.param("initial_buy_price", "$0.00000000", id="cost"),
        ],
    )
    def test_an_absent_key_renders_what_it_always_did(self, key, expected, monkeypatch):
        """PRE-EXISTING behaviour, deliberately preserved, and every
        string here was captured from live. `or 0` is gone, but
        `t.get(key, 0)` still defaults an ABSENT key to 0, so an absent
        money key still prints a real zero. Only a PRESENT but unusable
        value changed."""
        tranche = _valid_tranche()
        del tranche[key]
        _, rows = _build([tranche], monkeypatch)
        assert rows[0][KEY_COLUMN[key]] == expected

    def test_an_absent_ref_still_dashes_the_two_derived_cells(self, monkeypatch):
        """Also pre-existing and also captured from live: an absent ref
        defaults to 0, prints "$0.00000000" in its own column, and the
        `ref_v > 0` tests below then dash Min-rebuy and Status. A
        REFUSED ref must reach this same pair of dashes, which is the
        row above in `TestTheRefusalIsHonest`."""
        tranche = _valid_tranche()
        del tranche["ref"]
        _, rows = _build([tranche], monkeypatch)
        assert rows[0][COL_REF] == "$0.00000000"
        assert rows[0][COL_MIN_REBUY] == DASH
        assert rows[0][COL_STATUS] == DASH

    def test_an_absent_created_ts_still_reports_no_timestamp(self, monkeypatch):
        tranche = _valid_tranche()
        del tranche["created_ts"]
        labels, rows = _build([tranche], monkeypatch)
        assert rows[0][COL_AGE] == DASH
        assert _summary(labels, "Oldest tranche age:") == NO_TS_SUMMARY

    def test_the_empty_queue_message_is_unchanged(self, monkeypatch):
        labels, rows = _build([], monkeypatch)
        assert rows == []
        assert _parked(labels) == "$0.0000"
        assert _summary(labels, "Oldest tranche age:") == "no open tranches"


# CONTROL C - THE REFUSAL IS HONEST


class TestTheRefusalIsHonest:
    """FAILURE MEANS: a refused value renders as a number the operator
    would read as real. Printing zero for an unreadable dollar figure is
    a NEW defect, not a fix — nothing on the panel would distinguish an
    unreadable amount from a genuinely empty one."""

    @pytest.mark.parametrize("key", MONEY_KEYS)
    @pytest.mark.parametrize("value", REFUSED)
    def test_a_refused_money_value_never_reads_as_zero(self, key, value, monkeypatch):
        cell = _cell(key, value, monkeypatch)
        assert cell not in ("$0.0000", "$0.00000000", "0.000000", "0", "$0", "0.0")
        assert cell == DASH

    @pytest.mark.parametrize("key", ALL_KEYS)
    @pytest.mark.parametrize("value", REFUSED)
    def test_the_refusal_reaches_the_branch_a_missing_key_takes(
        self, key, value, monkeypatch
    ):
        """The refusal must LAND somewhere, not merely not raise. A
        missing key is the shape each column already refused before this
        fix, so every newly refused shape must produce that exact cell.
        """
        absent = _valid_tranche()
        del absent[key]
        _, base_rows = _build([absent], monkeypatch)
        if key == "created_ts":
            assert _cell(key, value, monkeypatch) == base_rows[0][COL_AGE]
        else:
            assert _cell(key, value, monkeypatch) == DASH

    @pytest.mark.parametrize("value", REFUSED)
    def test_a_refused_ref_dashes_all_three_cells_it_drives(self, value, monkeypatch):
        """`ref` feeds the Sell-ref cell, the Min-rebuy estimate and the
        Status verdict. Closing one and leaving the others would print a
        rebuy target computed from a value the panel just refused."""
        tranche = dict(_valid_tranche(), ref=value)
        _, rows = _build([tranche], monkeypatch)
        assert rows[0][COL_REF] == DASH
        assert rows[0][COL_MIN_REBUY] == DASH
        assert rows[0][COL_STATUS] == DASH

    def test_a_valid_ref_still_drives_all_three(self, monkeypatch):
        """POSITIVE CONTROL for the row above."""
        _, rows = _build([_valid_tranche()], monkeypatch)
        assert rows[0][COL_REF] == "$30000.00000000"
        assert rows[0][COL_MIN_REBUY] == "≤$29370.00000000"
        assert rows[0][COL_STATUS] == "Need price ≤ OTD (+5.55%)"

    @pytest.mark.parametrize("value", REFUSED)
    def test_summary_and_row_never_disagree_on_the_age(self, value, monkeypatch):
        """Both render the age of the SAME tranche from the SAME key.
        Closing one without the other gives a panel that contradicts
        itself, which is worse than the defect."""
        labels, rows = _build([dict(_valid_tranche(), created_ts=value)], monkeypatch)
        assert rows[0][COL_AGE] == DASH
        assert _summary(labels, "Oldest tranche age:") == NO_TS_SUMMARY

    @pytest.mark.parametrize("value", REFUSED)
    def test_summary_and_row_never_disagree_on_the_usd(self, value, monkeypatch):
        """`usd` is read twice: once for the parked total and once for
        the row cell. A dashed cell beside an unmarked total would say
        two different things about one number."""
        labels, rows = _build([dict(_valid_tranche(), usd=value)], monkeypatch)
        assert (rows[0][COL_USD] == DASH) == ("unreadable" in _parked(labels))


# CONTROL D - THE SUM


class TestTheParkedTotalCountsWhatItCannotRead:
    """FAILURE MEANS: an unreadable tranche is silently dropped from a
    money total, which under-reports with nothing on the panel saying
    so. That is the shape of the claim-total defect of 2026-08-10 —
    $2,000 reported against a true $3,000, with zero log lines. It also
    means one bad entry can still poison the whole figure, which is what
    a `sum` did."""

    def test_all_valid_totals_carry_no_marker(self, monkeypatch):
        """POSITIVE CONTROL. Fails if every panel now claims partial."""
        labels, _ = _build(
            [dict(_valid_tranche(), usd=250.0), dict(_valid_tranche(), usd=100.0)],
            monkeypatch,
        )
        assert _parked(labels) == "$350.0000"
        assert "unreadable" not in _parked(labels)

    def test_a_refused_contributor_is_counted_not_dropped(self, monkeypatch):
        labels, rows = _build(
            [
                dict(_valid_tranche(), usd=250.0),
                dict(_valid_tranche(), usd=float("nan")),
                dict(_valid_tranche(), usd=10**400),
            ],
            monkeypatch,
        )
        assert _parked(labels) == "$250.0000  (+2 unreadable)"
        assert len(rows) == 3

    @pytest.mark.parametrize("value", REFUSED)
    def test_every_refused_shape_is_counted(self, value, monkeypatch):
        labels, _ = _build(
            [dict(_valid_tranche(), usd=250.0), dict(_valid_tranche(), usd=value)],
            monkeypatch,
        )
        assert _parked(labels) == "$250.0000  (+1 unreadable)"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(float("nan"), id="nan"),
            pytest.param(float("inf"), id="inf"),
            pytest.param(float("-inf"), id="-inf"),
        ],
    )
    def test_one_bad_entry_no_longer_poisons_the_whole_total(self, value, monkeypatch):
        """This was a `sum`: a single non-finite contributor took the
        parked figure to "$nan" or "$inf" for every OTHER tranche in the
        queue as well."""
        labels, _ = _build(
            [dict(_valid_tranche(), usd=250.0), dict(_valid_tranche(), usd=value)],
            monkeypatch,
        )
        parked = _parked(labels)
        assert parked.startswith("$250.0000")
        assert "nan" not in parked and "inf" not in parked

    def test_the_count_is_not_the_row_count(self, monkeypatch):
        """A marker that just echoed the tranche count would pass every
        test above while telling the operator nothing."""
        labels, _ = _build(
            [
                dict(_valid_tranche(), usd=1.0),
                dict(_valid_tranche(), usd=2.0),
                dict(_valid_tranche(), usd=3.0),
                dict(_valid_tranche(), usd=None),
            ],
            monkeypatch,
        )
        assert _parked(labels) == "$6.0000  (+1 unreadable)"


# CONTROL E - 10 ** 400 RAISES NOWHERE, INCLUDING INSIDE THE GUARD


class TestHugeIntDoesNotRaiseAnywhere:
    """FAILURE MEANS: the guard opened the hole it closes.
    `math.isfinite(10 ** 400)` itself raises OverflowError, so the
    obvious finite-check is wrong on exactly this input.
    `as_finite_float` bounds ints with an INTEGER comparison, which is
    exact and cannot raise. This class is the row that tells the two
    apart."""

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_huge_int_renders_a_dash(self, key, monkeypatch):
        assert _cell(key, 10**400, monkeypatch) == DASH

    def test_huge_int_in_the_parked_total(self, monkeypatch):
        labels, _ = _build([dict(_valid_tranche(), usd=10**400)], monkeypatch)
        assert _parked(labels) == "$0.0000  (+1 unreadable)"

    def test_the_helper_itself_does_not_raise(self):
        """Directly, so a failure here names the guard rather than the
        panel. `math.isfinite` on this input raises; the shipped helper
        must return None."""
        from src.trading.bot_container import as_finite_float

        assert as_finite_float(10**400) is None
        assert as_finite_float(-(10**400)) is None

    def test_math_isfinite_really_does_raise_on_it(self):
        """The two-sided half of the row above. If this ever stops
        raising, the integer-comparison bound has lost its reason and
        the test above stops discriminating."""
        import math

        with pytest.raises(OverflowError):
            math.isfinite(10**400)


class TestPrecisionBandIsUnchanged:
    """FAILURE MEANS: the guard silently moved a money figure. Every
    expected string below was captured from LIVE before the change."""

    @pytest.mark.parametrize(
        "key,value,expected",
        [
            pytest.param(
                "usd", 2**53 + 1, "$9,007,199,254,740,992.0000", id="usd-2**53+1"
            ),
            pytest.param(
                "usd", 2**60 + 1, "$1,152,921,504,606,846,976.0000", id="usd-2**60+1"
            ),
            pytest.param(
                "units", 2**53 + 1, "9007199254740992.000000", id="units-2**53+1"
            ),
            pytest.param(
                "units", 2**60 + 1, "1152921504606846976.000000", id="units-2**60+1"
            ),
            pytest.param(
                "ref", 2**53 + 1, "$9007199254740992.00000000", id="ref-2**53+1"
            ),
            pytest.param(
                "ref", 2**60 + 1, "$1152921504606846976.00000000", id="ref-2**60+1"
            ),
            pytest.param(
                "initial_buy_price",
                2**53 + 1,
                "$9007199254740992.00000000",
                id="cost-2**53+1",
            ),
            pytest.param(
                "initial_buy_price",
                2**60 + 1,
                "$1152921504606846976.00000000",
                id="cost-2**60+1",
            ),
        ],
    )
    def test_the_band_renders_exactly_what_live_rendered(
        self, key, value, expected, monkeypatch
    ):
        assert _cell(key, value, monkeypatch) == expected

    @pytest.mark.parametrize("value", [2**53 + 1, 2**60 + 1])
    def test_the_parked_total_is_unchanged_in_the_band(self, value, monkeypatch):
        labels, _ = _build([dict(_valid_tranche(), usd=value)], monkeypatch)
        assert "unreadable" not in _parked(labels)
        assert _parked(labels) == "${:,.4f}".format(float(value))

    def test_the_helper_matches_a_bare_float_across_the_band(self):
        """The precision claim, stated directly: for every int the
        helper accepts, it returns exactly what `float()` returned
        before. Any divergence here is a moved money figure."""
        from src.trading.bot_container import as_finite_float

        for exponent in range(50, 70):
            for value in (2**exponent, 2**exponent + 1, -(2**exponent) - 1):
                assert as_finite_float(value) == float(value)

    def test_the_int_bound_is_where_the_helper_says_it_is(self):
        """The one band where the helper and a bare `float()` differ:
        above 2 ** 1023 the helper refuses a value `float()` would still
        convert. Recorded deliberately — no dollar figure, unit count or
        timestamp reaches 10 ** 308, and a fourth admission variant
        invented to close this band would be worse than the band."""
        from src.trading.bot_container import as_finite_float

        assert as_finite_float(2**1023) == float(2**1023)
        assert as_finite_float(2**1023 + 1) is None
        assert float(2**1023 + 1) == float(2**1023)


# The admission rule is the repo's, not a fourth variant


class TestAdmissionHelperIsTheRepoRule:
    """FAILURE MEANS: this unit invented its own guard. Four sites in
    this file and two more in `bot_container` must answer the same
    question the same way, or the panels contradict each other."""

    @pytest.mark.parametrize("key", MONEY_KEYS)
    def test_the_panel_verdict_matches_the_helper_verdict(self, key, monkeypatch):
        """Every money cell agrees with `as_finite_float` shape for shape.

        The oracle is the helper's own answer, so a hand-rolled guard that
        drifts from it prints a number where the helper says None.
        """
        from src.trading.bot_container import as_finite_float

        shapes = [
            True,
            False,
            _FloatSub(7.0),
            Decimal("2.5"),
            Fraction(5, 2),
            "2.5",
            "",
            None,
            float("nan"),
            float("inf"),
            float("-inf"),
            10**400,
            _HasFloat(),
            [1.0],
            {"a": 1},
            1.5,
            250.0,
            0,
        ]
        verdicts = [as_finite_float(v) is None for v in shapes]
        assert any(verdicts) and not all(verdicts), (
            "the oracle must both refuse and accept, or agreement is vacuous; "
            f"got {verdicts}"
        )
        for shape, refused in zip(shapes, verdicts):
            cell = _cell(key, shape, monkeypatch)
            if refused:
                assert cell == DASH, (key, shape, cell)
            else:
                assert cell != DASH, (key, shape, cell)

    def test_helper_refuses_every_shape_the_panel_refuses(self):
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
            Fraction(1, 2),
            "1",
            "",
            None,
            _HasFloat(),
            [1.0],
            {"a": 1},
        ):
            assert as_finite_float(value) is None

    def test_helper_accepts_exact_int_and_float(self):
        from src.trading.bot_container import as_finite_float

        assert as_finite_float(1) == 1.0
        assert as_finite_float(0) == 0.0
        assert as_finite_float(-5.5) == -5.5
        assert as_finite_float(NOW) == NOW


# Reachability - the shapes above are what the saved file produces


class TestTheHostileShapesAreReachable:
    """FAILURE MEANS: this whole file is defending against something
    that cannot happen. `bot_state.json` is the fold tranches' only
    persistence, it round-trips them verbatim, and these are the shapes
    its decoder emits."""

    def test_json_decodes_the_shapes_the_panel_now_refuses(self):
        assert json.loads('{"a": true}')["a"] is True
        assert json.loads('{"a": NaN}')["a"] != json.loads('{"a": NaN}')["a"]
        assert json.loads('{"a": Infinity}')["a"] == float("inf")
        assert json.loads('{"a": -Infinity}')["a"] == float("-inf")
        assert json.loads('{"a": null}')["a"] is None
        huge = json.loads('{"a": 1%s}' % ("0" * 400))["a"]
        assert type(huge) is int
        assert huge == 10**400

    def test_a_tranche_dict_survives_a_round_trip_verbatim(self):
        """No per-key validation stands between the file and the panel,
        which is why the panel has to do the refusing."""
        tranche = _valid_tranche()
        assert json.loads(json.dumps(tranche)) == tranche
