"""Phase 1 Step 4 — diagnostic state must survive a restart.

Five fields were written every session and persisted by none of them, so
each reset to zero at the moment it was needed. Every one exists to
answer "why did nothing happen":

  _pending_wire_ledger        the PROVENANCE of parked wire credit. The
                              total was persisted; the itemisation
                              saying where it came from was not, so
                              after any restart the money had no
                              explanation. `_add_wire_credits` also
                              guards with `if entries:`, so a
                              post-restart absorb wrote no wire_credits
                              key at all.
  _fold_accumulator           the lifetime compound counter -- the only
                              running total of how much compounding had
                              ever actually happened.
  _tranches_malformed_dropped how many tranches were silently discarded
                              for bad shape. The single most diagnostic
                              number for "tranches fill but nothing
                              happens".
  _stack_tranches
  _stack_created              latent today (stack_mode off on all 35),
                              persisted for the same reason
                              `pending_stack_buy_usd` already is: a
                              restart must not lose a queued
                              acquisition, and the tranches it produces
                              are part of that acquisition.

COMPATIBILITY, BOTH DIRECTIONS
A newer build reading an OLDER file must not raise -- every restore is
defaulted. An older build reading a NEWER file must not choke -- the
export only ADDS keys, and import reads by `data.get`, ignoring unknown
ones. Both directions are pinned below.

No back-fill is attempted for any of them. Fabricating a historical
value would corrupt the very counters these exist to make trustworthy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

FIELDS = (
    "_pending_wire_ledger",
    "_fold_accumulator",
    "_tranches_malformed_dropped",
    "_stack_tranches",
    "_stack_created",
)


class _Bus:
    def emit(self, *_a, **_k):
        pass


class _Bot:
    """Carries only what import_scrumming_state reads off `self`."""

    import_scrumming_state = ScrummingBot.import_scrumming_state

    def __init__(self):
        self.bot_id = "bot-test-0001"
        self.config = type("C", (), {"symbol": "RAVE/USD", "target_balance": 50.0})()
        self._bus = _Bus()
        self._current_holdings = 0.0
        self._anchor_target_balance = 50.0
        self._target_balance = 50.0
        self._standing_surplus_usd = 0.0
        self._fold_cycle_cap_consumed = 0.0
        self._pending_wire_credits = 0.0
        self._last_trade_price = 0.0
        self._last_trade_side = ""
        self._hyst_ref_fold_side = 0.0
        self._hyst_ref_scrum_side = 0.0
        self._hyst_armed_fold_side = False
        self._hyst_armed_scrum_side = False
        self._dist_accumulator = 0.0
        self._hedge_bal = 0.0
        self._hedge_trades = 0
        self._cb_hard_tripped = False
        self._compact_wire_credits = lambda *_a, **_k: None


POPULATED = {
    "pending_wire_ledger": [
        {"usd": 4.0, "src": "bot-x"},
        {"usd": 5.45, "src": "bot-y"},
    ],
    "fold_accumulator": 12.3456,
    "tranches_malformed_dropped": 7,
    "stack_tranches": [{"usd": 1.0, "ref": 0.5}],
    "stack_created": 3,
}


@pytest.fixture
def bot():
    return _Bot()


class TestTheStubWorks:
    def test_import_runs_at_all(self, bot):
        """POSITIVE CONTROL. If import raised, every assertion below
        would fail for the wrong reason and the defaults tests would be
        indistinguishable from a broken stub."""
        bot.import_scrumming_state(dict(POPULATED))
        assert bot.bot_id == "bot-test-0001"


class TestPopulatedStateRestores:
    def test_the_wire_ledger_comes_back(self, bot):
        bot.import_scrumming_state(dict(POPULATED))
        assert len(bot._pending_wire_ledger) == 2
        assert bot._pending_wire_ledger[0]["src"] == "bot-x"

    def test_the_compound_counter_comes_back(self, bot):
        bot.import_scrumming_state(dict(POPULATED))
        assert bot._fold_accumulator == pytest.approx(12.3456)

    def test_the_malformed_drop_count_comes_back(self, bot):
        bot.import_scrumming_state(dict(POPULATED))
        assert bot._tranches_malformed_dropped == 7

    def test_the_stack_fields_come_back(self, bot):
        bot.import_scrumming_state(dict(POPULATED))
        assert len(bot._stack_tranches) == 1
        assert bot._stack_created == 3


class TestAnOlderFileStillLoads:
    """A newer build reading state written before these keys existed."""

    @pytest.mark.parametrize("field", FIELDS)
    def test_every_field_defaults_rather_than_raising(self, bot, field):
        bot.import_scrumming_state({})
        assert hasattr(bot, field), f"{field} unset after an empty import"

    def test_the_defaults_are_empty_not_fabricated(self, bot):
        """No back-fill. A guessed historical value would corrupt the
        counters these exist to make trustworthy."""
        bot.import_scrumming_state({})
        assert bot._pending_wire_ledger == []
        assert bot._fold_accumulator == 0.0
        assert bot._tranches_malformed_dropped == 0
        assert bot._stack_tranches == []
        assert bot._stack_created == 0

    def test_junk_entries_are_filtered_not_trusted(self, bot):
        """The ledger is a list of dicts. A non-dict entry from a
        corrupt file must not reach code that will subscript it."""
        bot.import_scrumming_state(
            {
                "pending_wire_ledger": [{"usd": 1.0}, "not-a-dict", None],
                "stack_tranches": ["junk", {"usd": 2.0}],
            }
        )
        assert bot._pending_wire_ledger == [{"usd": 1.0}]
        assert bot._stack_tranches == [{"usd": 2.0}]


class TestBothSidesExist:
    """An export without an import is a write-only field: it looks
    persisted and restores to nothing."""

    @pytest.mark.parametrize("field", FIELDS)
    def test_the_key_is_on_both_sides(self, field):
        import ast
        import inspect

        _sf = inspect.getsourcefile(ScrummingBot.export_scrumming_state)
        assert _sf is not None
        src = Path(_sf).read_text(encoding="utf-8")
        key = field.lstrip("_")
        tree = ast.parse(src)
        exp = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "export_scrumming_state"
        )
        imp = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "import_scrumming_state"
        )
        assert f'"{key}"' in (
            ast.get_source_segment(src, exp) or ""
        ), f"{key} is not exported"
        assert f'"{key}"' in (
            ast.get_source_segment(src, imp) or ""
        ), f"{key} is exported but never restored -- write-only"
