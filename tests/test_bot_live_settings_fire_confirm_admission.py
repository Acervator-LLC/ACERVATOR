"""Numeric admission on the Manual Fire CONFIRMATION dialog.

THE DEFECT THESE PIN
====================
``_on_fire_tranche_clicked`` read three money values off the fold
tranche dict with bare ``float(t.get(key, 0) or 0)``, and formatted all
three into the confirmation the operator reads BEFORE authorising a
MARKET buy that bypasses the TA, OTD and Target-Delta gates::

    USD parked: $%.4f / Sell ref: $%.8f / Original cost: $%.8f

Measured through the real method, before the fix:

* a stored ``True`` rendered ``$1.0000`` -- a flag priced as one dollar
* ``None``/``""``/``False`` rendered ``$0.0000`` -- an ABSENCE shown as
  a real zero
* ``nan``/``inf``/``-inf`` rendered ``$nan``/``$inf``/``$-inf``
* the string ``"20.0"`` rendered ``$20.0000`` -- a string priced
* ``Decimal``/``Fraction``/a float subclass/an object with ``__float__``
  all rendered as though they were stored numbers
* ``10 ** 400``, a list and a dict raised OverflowError/TypeError

THE RAISE IS CONTAINED, AND THAT MATTERS FOR HOW THIS IS STATED.
The AST ancestor chain from all four reads is the method's own outer
``Try`` and then ``FunctionDef@_on_fire_tranche_clicked`` -- no
intervening frame -- and that ``try``'s only handler is ``except
Exception as exc`` -> ``logger.exception`` ->
``QMessageBox.critical("Manual Fire error")``. So unlike the fold-row
builder next door, a raise here does NOT stop the dialog opening. This
is NOT a crash defect. It is a FABRICATED-NUMBER defect, and the four
raising shapes are the mildest rows in the table, not the worst.

That containment is why a value whose ``repr`` itself raises still
ends safely: measured, it reaches the generic "Manual Fire error"
handler rather than the specific refusal, and NO order is placed.

WHY IT IS STILL SERIOUS -- AND WHY THE FIRE IS REFUSED, NOT JUST BLANKED
=======================================================================
The three values are DISPLAY-ONLY inside this method. Exhaustive AST
check: the only ``Load`` of ``_usd``/``_ref``/``_ibp`` is the
``_confirm_msg`` f-string, and the only thing crossing into the order
is ``idx``, an ``int``, at ``self._bot.manual_fire_tranche(idx)``.

Blanking the labels to an em dash would therefore have been the WRONG
whole fix, because the order path re-derives the same numbers from the
SAME dict -- captured by identity where the Fire button was built --
with a character-identical expression::

    # ScrummingBot.manual_fire_tranche
    cost = float(tranche.get("usd", 0) or 0)
    ...
    fill_price = await self._execute_buy(cost=cost, price=price, ...)

and its ONLY guard is ``cost <= 0``. Driven, not predicted: ``nan <= 0``
is False and ``inf <= 0`` is False, so a stored ``nan`` arrives as
``_execute_buy(cost=nan)`` intact. A stored ``True`` buys one dollar.
``"20.0"`` buys twenty.

A dash beside a Confirm button that still buys reads as handled and is
worse than the honest ``$nan``. So the fire is REFUSED before the
confirmation is offered, and the refusal names the field and its stored
value. ``test_refusal_*`` pins that; ``test_valid_*`` are the positive
controls that stop a guard which refuses everything from passing.

REACHABILITY: fold tranches round-trip through ``bot_state.json``
verbatim. ``json.loads`` yields ``True`` from ``true``, ``nan`` from
``NaN``, ``inf`` from ``Infinity`` and an unbounded ``int`` from a
400-digit literal. ``test_refusal_survives_a_real_state_file_round_trip``
decodes its rows with ``json.loads`` rather than hand-building them.

AND THE GUARD MUST NOT OPEN THE HOLE IT CLOSES: ``float(10 ** 400)``
raises OverflowError and ``math.isfinite(10 ** 400)`` raises it too.
``as_finite_float`` bounds ints with an integer comparison, which
cannot raise. ``test_huge_int_refused_without_raising`` is the row that
tells the two apart.

THE EXPECTED STRINGS BELOW WERE CAPTURED FROM LIVE, BYTE FOR BYTE,
before the change, by driving this same method. They are positive
controls: if the guard ever alters a readable value, they go red.
"""
from __future__ import annotations

import json
import sys
import types
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class _FloatSub(float):
    """A float subclass: passes isinstance, fails exact type."""


class _HasFloat:
    """Not a number, but float() of it succeeds."""

    def __float__(self) -> float:
        return 7.0

    def __repr__(self) -> str:
        return "<HasFloat>"


#: Every shape the confirmation must REFUSE, with what live showed for
#: it. The third column is the whole point of the unit: what the
#: operator would have read on a money-decision surface.
REFUSED = [
    pytest.param(True, "$1.0000", id="bool-True"),
    pytest.param(False, "$0.0000", id="bool-False"),
    pytest.param(None, "$0.0000", id="None"),
    pytest.param("", "$0.0000", id="empty-string"),
    pytest.param("20.0", "$20.0000", id="numeric-string"),
    pytest.param(float("nan"), "$nan", id="nan"),
    pytest.param(float("inf"), "$inf", id="inf"),
    pytest.param(float("-inf"), "$-inf", id="-inf"),
    pytest.param(Decimal("1.5"), "$1.5000", id="Decimal"),
    pytest.param(Fraction(3, 2), "$1.5000", id="Fraction"),
    pytest.param(_FloatSub(2.5), "$2.5000", id="float-subclass"),
    pytest.param(_HasFloat(), "$7.0000", id="obj-with-__float__"),
    pytest.param(2 ** 1023 + 1, "$8988465674311579", id="int-above-bound"),
    pytest.param(10 ** 400, "OverflowError", id="huge-int"),
    pytest.param([1.0], "TypeError", id="list"),
    pytest.param({"a": 1}, "TypeError", id="dict"),
]

#: Values that MUST still be accepted, with the exact confirmation line
#: live produced. Without these a guard refusing everything would pass
#: every refusal test above.
ACCEPTED = [
    pytest.param(20.0, "  USD parked:    $20.0000", id="float"),
    pytest.param(5, "  USD parked:    $5.0000", id="int"),
    pytest.param(0.0, "  USD parked:    $0.0000", id="zero"),
    pytest.param(-3.25, "  USD parked:    $-3.2500", id="negative"),
    pytest.param(-0.0, "  USD parked:    $0.0000", id="negative-zero"),
    pytest.param(2 ** 53 + 1, "  USD parked:    $9007199254740992.0000",
                 id="2**53+1"),
    pytest.param(5e-324, "  USD parked:    $0.0000", id="smallest-subnormal"),
]

MONEY_KEYS = ["usd", "ref", "initial_buy_price"]

#: The confirmation live rendered for a wholly valid tranche. Captured
#: byte for byte before the change.
LIVE_CONFIRM_TYPICAL = (
    "Fire tranche #1?\n\n"
    "  USD parked:    $20.0000\n"
    "  Sell ref:      $0.00012345\n"
    "  Original cost: $0.00011111\n\n"
    "This will execute a MARKET buy at the current price, bypassing "
    "TA / OTD / Target-Delta gates. Smart Ceiling and MEM-257 "
    "fail-closed still apply.")


def _valid_tranche():
    """One realistic fold tranche, every key a native float.

    These are the numbers the pre-change probe used, so
    LIVE_CONFIRM_TYPICAL is the string the shipped code produced for
    exactly this dict.
    """
    return {"usd": 20.0, "ref": 0.00012345,
            "initial_buy_price": 0.00011111}


class _Result:
    """Records what the operator saw and what the order received."""

    def __init__(self):
        self.events: list = []
        self.order_calls: list = []

    def dialog(self, kind):
        for e in self.events:
            if e["kind"] == kind:
                return e
        return None

    @property
    def confirm_text(self):
        e = self.dialog("question")
        return e["text"] if e else None

    @property
    def refusal(self):
        return self.dialog("critical")


def _fire(tranche, monkeypatch, answer_yes=True):
    """Drive the REAL _on_fire_tranche_clicked. Returns a _Result.

    Asserting on ``as_finite_float`` instead would prove nothing about
    the dialog, so this binds the shipped method to a stub ``self`` and
    reads the messages it actually raises. ``manual_fire_tranche`` is
    intercepted at the call boundary: it is the only value that crosses
    from this method into the order path, so recording its arguments is
    how "the order is untouched" is measured rather than assumed.
    """
    pytest.importorskip("PySide6.QtWidgets")
    import PySide6.QtCore as _QtCore
    import PySide6.QtWidgets as _QtWidgets

    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    res = _Result()

    class _Msg:
        Yes = 0x4000
        No = 0x10000

        @classmethod
        def _rec(cls, kind, title, text):
            res.events.append({"kind": kind, "title": title, "text": text})

        @classmethod
        def warning(cls, _p, title, text, *_a, **_k):
            cls._rec("warning", title, text)
            return cls.No

        @classmethod
        def critical(cls, _p, title, text, *_a, **_k):
            cls._rec("critical", title, text)
            return cls.No

        @classmethod
        def information(cls, _p, title, text, *_a, **_k):
            cls._rec("information", title, text)
            return cls.No

        @classmethod
        def question(cls, _p, title, text, *_a, **_k):
            cls._rec("question", title, text)
            return cls.Yes if answer_yes else cls.No

    class _Timer:
        def __init__(self, *_a, **_k):
            self.timeout = types.SimpleNamespace(
                connect=lambda *_a, **_k: None)

        def setInterval(self, *_a, **_k):
            pass

        def start(self, *_a, **_k):
            pass

        def stop(self, *_a, **_k):
            pass

    class _Coro:
        def close(self):
            pass

    class _Bot:
        bot_id = "bot-fire-test"

        def __init__(self):
            self._fold_tranches = [tranche]

        def manual_fire_tranche(self, *args, **kwargs):
            res.order_calls.append({"args": args, "kwargs": kwargs})
            return _Coro()

    class _StubDlg:
        def __init__(self):
            self._bot = _Bot()
            self._bm = types.SimpleNamespace(_async_loop=object())

    monkeypatch.setattr(_QtWidgets, "QMessageBox", _Msg)
    monkeypatch.setattr(_QtCore, "QTimer", _Timer)
    import asyncio as _asyncio
    monkeypatch.setattr(
        _asyncio, "run_coroutine_threadsafe",
        lambda *_a, **_k: types.SimpleNamespace(done=lambda: False))

    _Dlg._on_fire_tranche_clicked(_StubDlg(), tranche)
    return res


# --------------------------------------------------------------------
# POSITIVE CONTROLS. A guard that refused everything would pass every
# refusal test below while making the Fire button useless.
# --------------------------------------------------------------------

def test_valid_tranche_confirmation_is_byte_identical_to_live(monkeypatch):
    """If this fails, the guard changed what a READABLE value displays.

    The operator would be reading a different number for a tranche that
    was never broken -- a restyle this unit was not authorised to make.
    """
    res = _fire(_valid_tranche(), monkeypatch)
    assert res.confirm_text == LIVE_CONFIRM_TYPICAL
    assert res.refusal is None


def test_valid_tranche_still_places_the_order(monkeypatch):
    """If this fails, the guard broke the Manual Fire button outright.

    The live-money control: a healthy tranche must still reach
    manual_fire_tranche with the identical argument.
    """
    res = _fire(_valid_tranche(), monkeypatch)
    assert len(res.order_calls) == 1
    call = res.order_calls[0]
    assert call["args"] == (0,)
    assert call["kwargs"] == {}
    assert type(call["args"][0]) is int


@pytest.mark.parametrize("value,expected_line", ACCEPTED)
def test_valid_usd_values_render_unchanged(value, expected_line, monkeypatch):
    """If this fails, a readable number now displays differently.

    ``negative-zero`` is the load-bearing row: live computed
    ``float(x or 0)``, which maps ``-0.0`` to POSITIVE ``0.0``. A guard
    that returned ``-0.0`` unchanged would print ``$-0.0000`` and this
    row would go red.
    """
    tr = {"usd": value, "ref": 1.0, "initial_buy_price": 1.0}
    res = _fire(tr, monkeypatch)
    assert res.refusal is None, "a valid value was refused"
    assert expected_line in res.confirm_text
    assert len(res.order_calls) == 1


def test_operator_answering_no_places_no_order(monkeypatch):
    """If this fails, Confirm/Cancel stopped being honoured."""
    res = _fire(_valid_tranche(), monkeypatch, answer_yes=False)
    assert res.confirm_text is not None
    assert res.order_calls == []


# --------------------------------------------------------------------
# THE REFUSAL
# --------------------------------------------------------------------

@pytest.mark.parametrize("bad,_live_showed", REFUSED)
@pytest.mark.parametrize("key", MONEY_KEYS)
def test_refusal_blocks_the_order(key, bad, _live_showed, monkeypatch):
    """If this fails, an unreadable stored value can still be bought.

    The market buy is sized from this same dict by the order path's own
    read, so a value the dialog cannot show honestly must not reach a
    Confirm button.
    """
    tr = _valid_tranche()
    tr[key] = bad
    res = _fire(tr, monkeypatch)
    assert res.order_calls == [], "the order was still dispatched"
    assert res.confirm_text is None, "a Confirm button was still offered"


@pytest.mark.parametrize("bad,_live_showed", REFUSED)
@pytest.mark.parametrize("key", MONEY_KEYS)
def test_refusal_is_visible_and_says_why(key, bad, _live_showed, monkeypatch):
    """If this fails, Fire became a silent no-op.

    The operator pressed a button on a money surface; a refusal they
    cannot see is its own defect.
    """
    tr = _valid_tranche()
    tr[key] = bad
    res = _fire(tr, monkeypatch)
    ref = res.refusal
    assert ref is not None, "no refusal dialog was shown"
    assert "refused" in ref["title"].lower()
    assert "NO ORDER" in ref["text"]
    assert "not a usable number" in ref["text"]
    assert key in ref["text"], "the refusal does not name the bad field"


def test_refusal_names_every_bad_field_not_just_the_first(monkeypatch):
    """If this fails, the operator fixes one field and hits the next."""
    tr = {"usd": True, "ref": None, "initial_buy_price": float("nan")}
    res = _fire(tr, monkeypatch)
    text = res.refusal["text"]
    for key in MONEY_KEYS:
        assert key in text


def test_huge_int_refused_without_raising(monkeypatch):
    """If this fails, the guard opened the hole it closes.

    ``float(10 ** 400)`` raises OverflowError and
    ``math.isfinite(10 ** 400)`` raises it too. Only an integer
    comparison can bound this without raising. Live reached the generic
    "Manual Fire error" handler here; the refusal must be the specific
    one instead.
    """
    tr = _valid_tranche()
    tr["usd"] = 10 ** 400
    res = _fire(tr, monkeypatch)
    assert res.refusal is not None
    assert "unreadable" in res.refusal["title"]
    assert res.order_calls == []


def test_refusal_echo_is_bounded(monkeypatch):
    """If this fails, a 401-digit int is pasted into a QMessageBox.

    The echo exists to identify the bad field, not to reprint it.
    """
    tr = _valid_tranche()
    tr["usd"] = 10 ** 400
    res = _fire(tr, monkeypatch)
    assert "..." in res.refusal["text"]
    assert len(res.refusal["text"]) < 1200


@pytest.mark.parametrize("literal,key", [
    ('{"usd": NaN, "ref": 1.0, "initial_buy_price": 1.0}', "usd"),
    ('{"usd": true, "ref": 1.0, "initial_buy_price": 1.0}', "usd"),
    ('{"usd": 1.0, "ref": Infinity, "initial_buy_price": 1.0}', "ref"),
    ('{"usd": 1.0, "ref": 1.0, "initial_buy_price": null}',
     "initial_buy_price"),
])
def test_refusal_survives_a_real_state_file_round_trip(literal, key,
                                                       monkeypatch):
    """If this fails, the reachable shapes are not the ones pinned.

    These are decoded by ``json.loads`` exactly as a corrupted or
    hand-edited ``bot_state.json`` would be, rather than hand-built.
    """
    tr = json.loads(literal)
    res = _fire(tr, monkeypatch)
    assert res.refusal is not None
    assert key in res.refusal["text"]
    assert res.order_calls == []


def test_ibp_falls_back_to_ref_when_the_key_is_absent(monkeypatch):
    """If this fails, the fallback this unit had to preserve is gone.

    ``t.get("initial_buy_price", t.get("ref", 0))`` falls back only on
    an ABSENT key, never on a present ``None``. The next test is the
    contrast that proves this one discriminates.
    """
    res = _fire({"usd": 7.5, "ref": 3.5}, monkeypatch)
    assert res.refusal is None
    assert "  Original cost: $3.50000000" in res.confirm_text


def test_present_but_none_ibp_does_not_fall_back_to_ref(monkeypatch):
    """If this fails, a present None started borrowing ref's number.

    That would show the operator a real 'original cost' for a tranche
    that stores none -- the fabrication this unit exists to stop.
    """
    res = _fire({"usd": 7.5, "ref": 3.5, "initial_buy_price": None},
                monkeypatch)
    assert res.refusal is not None
    assert "initial_buy_price" in res.refusal["text"]


def test_absent_money_keys_still_read_as_zero(monkeypatch):
    """If this fails, the unit widened past what it was scoped to.

    An ABSENT key has always defaulted to 0 through ``.get(key, 0)``,
    and the order path refuses that with "has zero USD". Only a PRESENT
    unreadable value is this unit's to refuse.
    """
    res = _fire({}, monkeypatch)
    assert res.refusal is None
    assert "  USD parked:    $0.0000" in res.confirm_text
