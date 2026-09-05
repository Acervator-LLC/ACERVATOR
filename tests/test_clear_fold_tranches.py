"""Clearing fold tranches discards queued INTENT and nothing else.

Operator directive 2026-08-06:

    "let's just clear the existing tranche values and assume them as
     invalid. They were calculated without any outgoing safety rate math,
     have languished for weeks in some cases, and just need to be
     produced fresh with a more optimized platform."

WHAT THIS MUST NOT DO
A fold tranche is a queued intent to buy back units that were scrummed.
Discarding it must not sell, must not buy, and must not disturb the
position or the target. The audit found 129 of 948 open tranches larger
than their own bot's entire cycle cap, holding 71.5% of queued tranche
capital, so this is a real release -- but only of intent.

THE COUNTER SPLIT
Discards are counted in `_tranches_discarded_lifetime`, never in
`_tranches_closed_lifetime`. A closed tranche is one that FOLDED. The
self-destruct path at scrumming_bot.py:2785 conflates the two, which is
why created-minus-closed has never reconciled against the standing
count. Keeping them apart makes
`created - closed - discarded = standing` hold.

THE PENDING-CREDIT TRAP
The park/absorb outlet is gated on the bot holding ZERO tranches, so
clearing OPENS it. The absorb dumps the whole parked pool into ONE
tranche with no split and no cap reference. Live, BTC/USD holds $342.26
parked against a $2.50 cycle cap -- 137x over, permanently un-foldable.
The report therefore carries the parked amount so the caller can surface
it, and `clear_fold_tranches` deliberately does NOT touch that pool: it
is real routed income, not a tranche, and discarding it is a different
decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


class _Bus:
    def __init__(self):
        self.msgs = []

    def emit(self, _ev, **kw):
        self.msgs.append(kw.get("message", ""))

    def text(self):
        return "\n".join(self.msgs)


class _Bot:
    """Only the attributes clear_fold_tranches() touches.

    Constructing a real ScrummingBot resolves paths under the operator's
    home directory, so the method is exercised unbound.
    """

    clear_fold_tranches = ScrummingBot.clear_fold_tranches
    clear_pending_wire_credits = ScrummingBot.clear_pending_wire_credits

    def __init__(self, tranches, pending=0.0):
        self.bot_id = "bot-test-0001"
        self.config = type("C", (), {"symbol": "RAVE/USD"})()
        self._fold_tranches = list(tranches)
        self._fold_queue_usd = sum(float(t.get("usd", 0) or 0) for t in tranches)
        self._pending_wire_credits = float(pending)
        # Self-consistent by construction: created - closed == standing before
        # any clear, so the invariant test has something to measure.
        self._tranches_created_lifetime = 39
        self._tranches_closed_lifetime = 39 - len(self._fold_tranches)
        self._target_balance = 50.0
        self._anchor_target_balance = 50.0
        self._current_holdings = 12.5
        self._main_lots = [{"units": 12.5, "initial_buy_price": 0.30}]
        self.stats = type("S", (), {})()
        self._bus = _Bus()


def _tr(usd, units, ref=0.30):
    return {"usd": usd, "units": units, "ref": ref}


@pytest.fixture
def bot():
    return _Bot([_tr(1.25, 4.0), _tr(2.50, 8.0), _tr(0.75, 2.5)])


class TestTheInstrumentWorks:
    def test_the_bot_starts_with_tranches(self, bot):
        """Positive control: every 'cleared' assertion below would pass
        against a bot that never had any."""
        assert len(bot._fold_tranches) == 3
        assert bot._fold_queue_usd == pytest.approx(4.50)


class TestItDiscardsTheQueue:
    def test_the_tranches_are_gone(self, bot):
        bot.clear_fold_tranches()
        assert bot._fold_tranches == []

    def test_the_queue_total_is_zeroed(self, bot):
        """A stale _fold_queue_usd would keep every downstream sum
        reporting money that no longer has a tranche behind it."""
        bot.clear_fold_tranches()
        assert bot._fold_queue_usd == 0.0

    def test_the_report_states_what_was_discarded(self, bot):
        r = bot.clear_fold_tranches()
        assert r["count"] == 3
        assert r["usd"] == pytest.approx(4.50)
        assert r["units"] == pytest.approx(14.5)
        assert r["symbol"] == "RAVE/USD"

    def test_it_is_logged(self, bot):
        bot.clear_fold_tranches(reason="operator (GUI)")
        msg = bot._bus.text()
        assert "FOLD TRANCHES CLEARED" in msg
        assert "operator (GUI)" in msg
        assert "4.5000" in msg

    def test_clearing_an_empty_queue_is_a_no_op(self, bot):
        bot.clear_fold_tranches()
        before = len(bot._bus.msgs)
        r = bot.clear_fold_tranches()
        assert r["count"] == 0
        assert len(bot._bus.msgs) == before, "logged a no-op clear"


class TestItTouchesNothingElse:
    """The whole safety case. A discard is not a trade."""

    def test_holdings_are_untouched(self, bot):
        bot.clear_fold_tranches()
        assert bot._current_holdings == pytest.approx(12.5)

    def test_cost_basis_is_untouched(self, bot):
        """Unlike detonation's full reset, _main_lots must survive --
        reseeding it would rewrite the bot's cost basis."""
        bot.clear_fold_tranches()
        assert len(bot._main_lots) == 1
        assert bot._main_lots[0]["initial_buy_price"] == pytest.approx(0.30)

    def test_target_and_anchor_are_untouched(self, bot):
        bot.clear_fold_tranches()
        assert bot._target_balance == pytest.approx(50.0)
        assert bot._anchor_target_balance == pytest.approx(50.0)

    def test_pending_wire_credits_are_untouched(self):
        """That pool is real routed income, not a tranche. Discarding it
        is a separate decision and this method must not make it."""
        b = _Bot([_tr(1.0, 3.0)], pending=342.26)
        b.clear_fold_tranches()
        assert b._pending_wire_credits == pytest.approx(342.26)


class TestTheCounterSplit:
    def test_discards_do_not_count_as_closed(self, bot):
        """THE invariant. A closed tranche folded; a discarded one did
        not. Conflating them is what made created-minus-closed
        unreconcilable."""
        before = bot._tranches_closed_lifetime
        bot.clear_fold_tranches()
        assert bot._tranches_closed_lifetime == before

    def test_discards_are_counted_separately(self, bot):
        bot.clear_fold_tranches()
        assert bot._tranches_discarded_lifetime == 3

    def test_created_minus_closed_minus_discarded_is_standing(self, bot):
        bot.clear_fold_tranches()
        standing = len(bot._fold_tranches)
        assert (
            bot._tranches_created_lifetime
            - bot._tranches_closed_lifetime
            - bot._tranches_discarded_lifetime
        ) == standing

    def test_the_counter_accumulates(self, bot):
        bot.clear_fold_tranches()
        bot._fold_tranches = [_tr(9.0, 1.0)]
        bot.clear_fold_tranches()
        assert bot._tranches_discarded_lifetime == 4

    def test_it_mirrors_to_stats(self, bot):
        bot.clear_fold_tranches()
        assert bot.stats.tranches_discarded_lifetime == 3


class TestThePendingCreditTrap:
    def test_the_report_carries_the_parked_amount(self):
        """Clearing opens the absorb window, so the caller needs the
        number to warn with."""
        b = _Bot([_tr(1.0, 3.0)], pending=342.26)
        r = b.clear_fold_tranches()
        assert r["pending_wire_credits"] == pytest.approx(342.26)

    def test_the_log_warns_when_credits_are_parked(self):
        b = _Bot([_tr(1.0, 3.0)], pending=342.26)
        b.clear_fold_tranches()
        msg = b._bus.text()
        assert "WARNING" in msg
        assert "342.26" in msg
        assert "absorb window" in msg

    def test_no_warning_when_nothing_is_parked(self, bot):
        """NEGATIVE CONTROL: warning on every clear would train the
        operator to ignore it."""
        bot.clear_fold_tranches()
        assert "WARNING" not in bot._bus.text()


class TestClearingWireCredits:
    """Operator directive 2026-08-06: "Languishing wire credits can also
    be cleared. These too were not calculated using outgoing safety rate
    math." The parked figure is x% of GROSS scrum proceeds -- principal,
    not profit -- so it is derived off the wrong basis. Live fingerprint:
    usd/(units x ref) is a flat 0.800 on 16 bots, 0.900 on 4, 1.000 on 6.

    Discarding it destroys nothing. `_pending_wire_credits` is
    bookkeeping: no order, withdrawal or transfer site exists for it
    anywhere in src/, and all bots share one exchange wallet, so the
    cash returns to spendable balance.
    """

    def test_the_credit_is_discarded(self):
        b = _Bot([], pending=342.26)
        b._pending_wire_ledger = [{"usd": 342.26, "src": "bot-x"}]
        r = b.clear_pending_wire_credits()
        assert b._pending_wire_credits == 0.0
        assert r["usd"] == pytest.approx(342.26)

    def test_the_detail_ledger_is_discarded_too(self):
        """A surviving ledger would keep the panel itemising credits the
        total no longer contains."""
        b = _Bot([], pending=9.45)
        b._pending_wire_ledger = [{"usd": 4.0}, {"usd": 5.45}]
        r = b.clear_pending_wire_credits()
        assert b._pending_wire_ledger == []
        assert r["ledger_entries"] == 2

    def test_it_is_logged_as_an_earmark_not_a_transfer(self):
        b = _Bot([], pending=342.26)
        b.clear_pending_wire_credits(reason="operator (GUI)")
        msg = b._bus.text()
        assert "WIRE CREDITS CLEARED" in msg
        assert "342.26" in msg
        assert "no funds moved" in msg.lower()

    def test_the_discarded_total_accumulates(self):
        b = _Bot([], pending=10.0)
        b.clear_pending_wire_credits()
        b._pending_wire_credits = 5.5
        b.clear_pending_wire_credits()
        assert b._wire_credits_discarded_lifetime == pytest.approx(15.5)

    def test_clearing_nothing_is_a_no_op(self):
        b = _Bot([], pending=0.0)
        r = b.clear_pending_wire_credits()
        assert r["usd"] == 0.0
        assert b._bus.msgs == [], "logged a no-op clear"

    def test_tranches_are_untouched(self):
        """NEGATIVE CONTROL. The two clears are independent operations
        and a bot can want one without the other."""
        b = _Bot([_tr(1.25, 4.0), _tr(2.50, 8.0)], pending=99.0)
        b.clear_pending_wire_credits()
        assert len(b._fold_tranches) == 2
        assert b._fold_queue_usd == pytest.approx(3.75)

    def test_position_and_target_are_untouched(self):
        b = _Bot([], pending=99.0)
        b.clear_pending_wire_credits()
        assert b._current_holdings == pytest.approx(12.5)
        assert b._target_balance == pytest.approx(50.0)
        assert len(b._main_lots) == 1


class TestTheTwoClearsCloseTheTrap:
    def test_clearing_both_leaves_no_absorb_exposure(self):
        """Clearing tranches ALONE opens the park/absorb window (it is
        gated on zero tranches) and the absorb dumps the whole pool into
        one un-foldable tranche. Clearing both closes the trap instead
        of arming it -- which is why the operator authorised the second
        clear."""
        b = _Bot([_tr(1.0, 3.0)], pending=342.26)
        b.clear_fold_tranches()
        assert b._pending_wire_credits == pytest.approx(
            342.26
        ), "tranche clear must not silently take the credits too"
        b.clear_pending_wire_credits()
        assert b._fold_tranches == []
        assert b._pending_wire_credits == 0.0


class TestItSurvivesRestart:
    def test_the_counter_is_persisted(self):
        import ast
        import inspect

        _sf = inspect.getsourcefile(ScrummingBot.export_scrumming_state)
        assert _sf is not None
        src = Path(_sf).read_text(encoding="utf-8")
        assert '"tranches_discarded_lifetime"' in src, (
            "the counter is not written to state; a clear would vanish "
            "on restart and the reconciliation would break again"
        )
        # written AND read back
        assert src.count('"tranches_discarded_lifetime"') >= 2
        ast.parse(src)
