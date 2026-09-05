"""The Fold-Tranche panel's health metric must mean what its label says.

ISSUE #98 DEFECT 4. Two faults, one unit.

(a) DISCARDS STAYED IN THE DENOMINATOR. The ratio was
`closed / created`, so a tranche the operator cleared, the despawn
sweep delisted or a detonation abandoned counted against the bot
forever. Measured on the live state file, 2026-08-23 and again
2026-08-24: BTC/USD had opened 160, folded back 118 and discarded 42,
which is every tranche it still had, and the panel printed 73.75%.

(b) THE COUNTERS DID NOT RECONCILE WITH THE STANDING LIST. The stated
invariant is `created - closed - discarded == len(_fold_tranches)`.
Read off `~/.acervator/bot_state.json`, saved 2026-08-24 16:14:19, 38
bots, every field taken from under `scrumming_state`: it failed on 13
of 38 and it drifted BOTH ways -- ORCA/USD -24, CHIP/USD -21, KAT/USD
-13, ZEC/USD +11, BIO/USD +7. The reader's control: `bot_count` reads
38 and 38 records were walked; all five fields were present on all 38;
the same key read at BOT level rather than under `scrumming_state`
returned 0 of 38, which is the mis-read an earlier pass made.

WHERE NEGATIVE DRIFT COMES FROM, WHICH IS WHAT THIS UNIT HAD TO
ESTABLISH. Write the identity out as a signed quantity:

    drift = standing - created + closed + discarded

A removal that moves no term takes `standing` down by one and leaves
the rest alone, so it moves drift by -1. Nothing else can: bumping
`closed` or `discarded` without a removal moves drift UP, appending
without bumping `created` moves it UP, and decrementing `created`
without a removal moves it UP. The restore-path clamp
(`if _closed > _created: _closed = _created`) also cannot leave drift
negative -- it fires only when `closed > created`, and drift is then
already at least the amount the clamp takes away.

So negative drift is exactly "a tranche left the queue and no term of
the identity moved". `src/trading/scrumming_bot.py` held eleven sites
that remove from `_fold_tranches`. Nine moved a term. TWO DID NOT:

  1. the TD-017 fold guard, which drops records whose `ref` is not
     above zero and bumped `_tranches_malformed_dropped` -- a counter
     that is NOT a term of the identity;
  2. the restore filter in `import_scrumming_state`, which drops
     stored entries that are not records and bumped nothing at all.

Both now bump `_tranches_discarded_lifetime`, and the malformed
counter is a SUB-COUNT of it rather than a fourth term.

WHAT THIS UNIT DOES NOT CLAIM. It does not attribute ORCA's -24 or
CHIP's -21 to a dated event. The counter that would have recorded a
malformed drop did not survive a launch until v3.24.49 -- the export
site says so in its own words -- so today's fleet-wide 0 is a
statement about the counter, not about the world. The `bot.log` bus
messages that name each drop are not persisted either: measured over
`~/.acervator_logs`, 4,188 files, "FOLD" appears in 58 of them and
"SCRUM" in 64, while "FOLD GUARD: dropping", "FOLD TOP-UP",
"MANUAL TRANCHE FIRE COMPLETE" and "SELF-DESTRUCT" appear in zero. The
mechanism is established and repaired; the historical magnitudes are
NOT VERIFIED, and they are not back-filled, because inventing a value
would corrupt the counters this repair exists to make trustworthy.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SOURCE_PATH = REPO_ROOT / "src" / "trading" / "scrumming_bot.py"

#: Every module holding part of the ScrummingBot engine. The counters
#: swept below are written from all four.
ENGINE_PATHS = (
    SOURCE_PATH,
    REPO_ROOT / "src" / "trading" / "scrumming" / "execution.py",
    REPO_ROOT / "src" / "trading" / "scrumming" / "fold_tranches.py",
    REPO_ROOT / "src" / "trading" / "scrumming" / "reconciliation.py",
    REPO_ROOT / "src" / "trading" / "scrumming" / "tick_phases.py",
)

DAY = 86400.0
NOW = 1_756_000_000.0


class _Exchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


def _bot(despawn_days: int = 0):
    """A real ``ScrummingBot``. Every assertion below drives shipped code."""
    from src.trading.bot_container import BotMode, make_bot_config

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="BTC",
        target_balance=100.0,
    )
    cfg.tranche_despawn_days = despawn_days
    return ScrummingBot(cfg, _Exchange(), enable_phantoms=False)


def _tranche(
    ref=100.0, usd=1.0, units=0.01, age_days: float | None = 1.0, **extra
) -> dict:
    record = {"usd": usd, "units": units, "ref": ref, "initial_buy_price": 90.0}
    if age_days is not None:
        record["created_ts"] = NOW - age_days * DAY
    record.update(extra)
    return record


def _seed(bot, tranches, *, created=None, closed=0, discarded=0):
    """Seed a queue whose counters reconcile BEFORE the act under test.

    A fixture that already violates the identity cannot test it.
    """
    bot._fold_tranches = [dict(t) for t in tranches]
    bot._fold_queue_usd = sum(float(t.get("usd", 0) or 0) for t in tranches)
    bot._tranches_closed_lifetime = closed
    bot._tranches_discarded_lifetime = discarded
    bot._tranches_created_lifetime = (
        len(bot._fold_tranches) + closed + discarded if created is None else created
    )
    return bot


def _books(bot) -> tuple[int, int, int, int]:
    return (
        int(bot._tranches_created_lifetime),
        int(bot._tranches_closed_lifetime),
        int(bot._tranches_discarded_lifetime),
        len(bot._fold_tranches),
    )


def _drift(bot) -> int:
    created, closed, discarded, standing = _books(bot)
    return standing - created + closed + discarded


# A. THE INSTRUMENT. A test that never sees the defect is not a
#    measurement.
class TestTheInstrumentWorks:

    def test_a_seeded_bot_reconciles_before_anything_acts(self):
        bot = _seed(_bot(), [_tranche(), _tranche()], closed=7, discarded=3)
        assert _books(bot) == (12, 7, 3, 2)
        assert _drift(bot) == 0

    def test_POSITIVE_CONTROL_the_drift_reader_can_report_negative(self):
        """Remove a record and move no counter. That IS the defect."""
        bot = _seed(_bot(), [_tranche(), _tranche()], closed=7, discarded=3)
        bot._fold_tranches.pop()
        assert _drift(bot) == -1

    def test_POSITIVE_CONTROL_the_drift_reader_can_report_positive(self):
        """Bump a counter and remove nothing. The other direction."""
        bot = _seed(_bot(), [_tranche()], closed=7, discarded=3)
        bot._tranches_closed_lifetime += 5
        assert _drift(bot) == 5


# B. THE WRITE SITE THAT PRODUCED NEGATIVE DRIFT.
class TestTheMalformedDropIsCountedAsADiscard:

    #: `ref` values the guard refuses; `nan` fails `ref > 0` like a missing key.
    BAD_REFS = (0.0, -1.0, float("nan"))

    def test_it_removes_only_the_unreadable_records(self):
        bot = _seed(
            _bot(),
            [
                _tranche(ref=100.0),
                _tranche(ref=0.0),
                _tranche(ref=-1.0),
                _tranche(ref=200.0),
            ],
        )
        assert bot._drop_malformed_fold_tranches() == 2
        assert [t["ref"] for t in bot._fold_tranches] == [100.0, 200.0]

    def test_the_discard_counter_moves_by_what_it_dropped(self):
        bot = _seed(
            _bot(),
            [_tranche(ref=100.0), _tranche(ref=0.0), _tranche(ref=-1.0)],
            closed=4,
            discarded=1,
        )
        before = _books(bot)
        bot._drop_malformed_fold_tranches()
        created, closed, discarded, standing = _books(bot)
        assert created == before[0]
        assert closed == before[1], "a malformed record never folded"
        assert discarded == before[2] + 2
        assert standing == before[3] - 2

    def test_the_identity_survives_the_drop(self):
        bot = _seed(
            _bot(),
            [_tranche(ref=100.0), _tranche(ref=0.0), _tranche(ref=-1.0)],
            closed=4,
            discarded=1,
        )
        bot._drop_malformed_fold_tranches()
        assert _drift(bot) == 0

    def test_POSITIVE_CONTROL_the_old_behaviour_drifts_by_the_drop_count(self):
        """The measurement this repair is against.

        The pre-change site bumped the malformed counter and nothing
        else. Reproduced here on the same fixture: three drops, drift
        -3, and the malformed counter cannot close the gap because it
        is not a term of the identity.
        """
        bot = _seed(
            _bot(),
            [
                _tranche(ref=100.0),
                _tranche(ref=0.0),
                _tranche(ref=-1.0),
                _tranche(ref=0.0),
            ],
            closed=4,
            discarded=1,
        )
        bot._tranches_malformed_dropped += 3
        bot._fold_tranches = [t for t in bot._fold_tranches if t["ref"] > 0]
        assert _drift(bot) == -3

    @pytest.mark.parametrize("bad", BAD_REFS)
    def test_every_refused_ref_shape_is_counted(self, bad):
        bot = _seed(_bot(), [_tranche(ref=100.0), _tranche(ref=bad)])
        assert bot._drop_malformed_fold_tranches() == 1
        assert bot._tranches_discarded_lifetime == 1
        assert _drift(bot) == 0

    def test_a_tranche_with_no_ref_key_at_all_is_counted(self):
        bot = _seed(_bot(), [_tranche(ref=100.0), {"usd": 1.0, "units": 0.5}])
        assert bot._drop_malformed_fold_tranches() == 1
        assert bot._tranches_discarded_lifetime == 1

    def test_it_moves_NOTHING_when_every_record_is_readable(self):
        """The other half of the calibration.

        A counter that only ever rises is not measuring. It has to stay
        still when the thing it counts does not happen.
        """
        bot = _seed(
            _bot(), [_tranche(ref=100.0), _tranche(ref=200.0)], closed=4, discarded=1
        )
        before = (_books(bot), bot._tranches_malformed_dropped)
        assert bot._drop_malformed_fold_tranches() == 0
        assert (_books(bot), bot._tranches_malformed_dropped) == before

    def test_the_malformed_counter_stays_a_sub_count_of_discarded(self):
        bot = _seed(_bot(), [_tranche(ref=100.0), _tranche(ref=0.0)])
        bot._drop_malformed_fold_tranches()
        assert bot._tranches_malformed_dropped == 1
        assert bot._tranches_discarded_lifetime == 1

    def test_it_says_so_on_the_bus(self):
        """SUBSCRIBE, never replace `emit`.

        `_bus` is shared, so assigning over its `emit` leaves every
        later test in the session talking to this closure. Measured:
        one such assignment here silenced
        `test_the_sweep_reports_what_it_did` two files away.
        """
        bot = _seed(_bot(), [_tranche(ref=0.0)])
        seen: list[str] = []
        bot._bus.subscribe(
            "bot.log", lambda event: seen.append(str(event.data.get("message", "")))
        )
        bot._drop_malformed_fold_tranches()
        assert any("FOLD GUARD" in m and "DISCARDED" in m for m in seen)


# C. THE RESTORE FILTER, the second unbalanced removal.
def _state(tranches, created, closed, discarded, malformed=0) -> dict:
    return {
        "fold_tranches": list(tranches),
        "tranches_created_lifetime": created,
        "tranches_closed_lifetime": closed,
        "tranches_discarded_lifetime": discarded,
        "tranches_malformed_dropped": malformed,
    }


class TestTheRestoreFilterCountsWhatItDrops:

    def test_an_unreadable_stored_entry_is_a_discard(self):
        bot = _bot()
        bot.import_scrumming_state(_state([_tranche(), "not a record", None], 10, 6, 1))
        assert len(bot._fold_tranches) == 1
        assert bot._tranches_discarded_lifetime == 3
        assert bot._tranches_malformed_dropped == 2
        assert _drift(bot) == 0

    def test_POSITIVE_CONTROL_without_the_bump_the_restore_drifts(self):
        """The same state, with the counter left where the file put it."""
        bot = _bot()
        bot.import_scrumming_state(_state([_tranche(), "not a record", None], 10, 6, 1))
        bot._tranches_discarded_lifetime -= 2
        assert _drift(bot) == -2

    def test_it_moves_NOTHING_when_every_stored_entry_is_a_record(self):
        bot = _bot()
        bot.import_scrumming_state(_state([_tranche(), _tranche()], 10, 6, 2))
        assert bot._tranches_discarded_lifetime == 2
        assert bot._tranches_malformed_dropped == 0
        assert _drift(bot) == 0

    def test_the_restored_counters_still_come_from_the_file(self):
        """The bump adds to the stored value; it does not replace it."""
        bot = _bot()
        bot.import_scrumming_state(_state([_tranche(), 17], 10, 6, 3, malformed=5))
        assert bot._tranches_discarded_lifetime == 4
        assert bot._tranches_malformed_dropped == 6


# D. THE THREE VERBS. Merge, despawn and clear are the only three that
#    collapse or remove a tranche, and each moves ONE counter.
class TestClearMovesDiscarded:

    def test_clear_discards_and_never_closes(self):
        bot = _seed(_bot(), [_tranche(), _tranche(), _tranche()], closed=9, discarded=2)
        bot.clear_fold_tranches(reason="test")
        created, closed, discarded, standing = _books(bot)
        assert (closed, discarded, standing) == (9, 5, 0)
        assert _drift(bot) == 0

    def test_clearing_an_empty_queue_moves_nothing(self):
        bot = _seed(_bot(), [], closed=9, discarded=2)
        before = _books(bot)
        bot.clear_fold_tranches(reason="test")
        assert _books(bot) == before


class TestDespawnMovesDiscarded:

    def test_despawn_discards_what_it_removes(self):
        bot = _seed(
            _bot(despawn_days=30),
            [_tranche(age_days=40), _tranche(age_days=1), _tranche(age_days=31)],
            closed=9,
            discarded=2,
        )
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["fold_delisted"] == 2
        created, closed, discarded, standing = _books(bot)
        assert (closed, discarded, standing) == (9, 4, 1)
        assert _drift(bot) == 0

    def test_a_despawn_that_removes_nothing_moves_nothing(self):
        """The timer is Off on all 38 live bots, so this is the fleet's
        own case."""
        bot = _seed(
            _bot(despawn_days=0), [_tranche(age_days=400)], closed=9, discarded=2
        )
        before = _books(bot)
        assert bot._despawn_aged_tranches(now=NOW)["fold_delisted"] == 0
        assert _books(bot) == before


class TestMergeMovesCreatedDown:

    def test_a_merge_takes_created_down_by_what_it_removed(self):
        """The one verb that moves `created`, and it moves it DOWN.

        A merged tranche was opened by this sell and then folded into an
        older part-spent record, so the sell did not, in the end, open
        it. Removal and decrement are equal, which is why a merge cannot
        drift the identity in either direction.
        """
        older = _tranche(ref=100.0, usd=2.0, units=0.02, fold_partial_spent=True)
        fresh = _tranche(ref=110.0, usd=1.0, units=0.01)
        bot = _seed(_bot(), [older, fresh], closed=5, discarded=0)
        merged, moved_usd = bot._top_up_remnant_fold_tranches(
            first_new_index=1, bb_lower=50.0, bb_upper=150.0
        )
        assert merged == 1
        assert moved_usd == pytest.approx(1.0)
        created, closed, discarded, standing = _books(bot)
        assert (created, closed, discarded, standing) == (6, 5, 0, 1)
        assert _drift(bot) == 0

    def test_a_merge_that_finds_no_candidate_moves_nothing(self):
        older = _tranche(ref=100.0, usd=2.0, units=0.02)  # not a remnant
        fresh = _tranche(ref=110.0, usd=1.0, units=0.01)
        bot = _seed(_bot(), [older, fresh], closed=5, discarded=0)
        before = _books(bot)
        assert bot._top_up_remnant_fold_tranches(
            first_new_index=1, bb_lower=50.0, bb_upper=150.0
        ) == (0, 0.0)
        assert _books(bot) == before


# E. THE SOURCE RULE. A later edit must not re-open the hole.
def _functions_assigning(name: str) -> set[str]:
    """Every engine function that ASSIGNS `self.<name>`."""
    nodes: list = []
    for path in ENGINE_PATHS:
        nodes.extend(ast.walk(ast.parse(path.read_text(encoding="utf-8"))))
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            targets: list = []
            if isinstance(inner, ast.Assign):
                targets = list(inner.targets)
            elif isinstance(inner, ast.AugAssign):
                targets = [inner.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr == name:
                    found.add(node.name)
    return found


def test_the_reader_finds_the_writers_it_is_asked_about():
    """POSITIVE CONTROL. A scanner that finds nothing proves nothing."""
    writers = _functions_assigning("_tranches_discarded_lifetime")
    assert "clear_fold_tranches" in writers
    assert "_despawn_aged_tranches" in writers
    assert _functions_assigning("_no_such_attribute_anywhere") == set()


def test_no_function_moves_the_malformed_counter_alone():
    """The malformed counter is a SUB-COUNT, so it never travels alone.

    Any function that writes it must also write the discard counter
    that carries it into the reconciliation. This is the rule the
    pre-change fold guard broke.
    """
    malformed = _functions_assigning("_tranches_malformed_dropped")
    discarded = _functions_assigning("_tranches_discarded_lifetime")
    assert malformed, "the scanner found no writer at all"
    assert malformed <= discarded, sorted(malformed - discarded)


#: Read off the live state file as `(symbol, created, closed, discarded)`.
BTC = ("BTC/USD", 160, 118, 42)
CHIP = ("CHIP/USD", 4924, 4603, 90)
BIO = ("BIO/USD", 305, 161, 132)


def _ratio(created, closed, discarded):
    from src.gui.bot_live_settings import compose_cycle_close_ratio

    return compose_cycle_close_ratio(created, closed, discarded)


class TestTheRatioExcludesDiscards:

    def test_btc_folded_everything_it_kept_and_now_reads_so(self):
        _, created, closed, discarded = BTC
        text, _colour = _ratio(created, closed, discarded)
        assert text == "100.00%  (118/118)"

    def test_POSITIVE_CONTROL_the_old_arithmetic_reads_73_75_percent(self):
        """The number the panel printed, from the same three counters.

        Without this the line above could be describing a change that
        never happened.
        """
        _, created, closed, _discarded = BTC
        assert f"{closed / created:.2%}" == "73.75%"

    def test_a_standing_tranche_still_counts_against_the_ratio(self):
        """CHIP holds 210 open. They are opened, not discarded and not
        yet folded, so they belong in the denominator -- that is what
        makes a stagnating queue visible here at all."""
        _, created, closed, discarded = CHIP
        text, _colour = _ratio(created, closed, discarded)
        assert text == "95.22%  (4603/4834)"

    def test_discarding_a_standing_tranche_raises_the_ratio(self):
        """It leaves the population rather than failing inside it."""
        before, _ = _ratio(100, 50, 0)
        after, _ = _ratio(100, 50, 25)
        assert before == "50.00%  (50/100)"
        assert after == "66.67%  (50/75)"

    def test_folding_one_more_raises_the_ratio(self):
        assert _ratio(100, 50, 0)[0] == "50.00%  (50/100)"
        assert _ratio(100, 51, 0)[0] == "51.00%  (51/100)"

    def test_opening_one_more_lowers_the_ratio(self):
        assert _ratio(101, 50, 0)[0] == "49.50%  (50/101)"

    def test_a_bot_that_discarded_everything_is_not_100_percent(self):
        """THE TRAP THIS ROW HAD TO AVOID. A metric whose healthy value
        and whose broken value are both '100%' is not a measurement."""
        text, colour = _ratio(42, 0, 42)
        assert text == "—  (nothing left to fold back)"
        assert colour is None

    def test_a_bot_that_has_never_scrummed_says_so(self):
        assert _ratio(0, 0, 0)[0] == "—  (nothing left to fold back)"

    def test_bio_is_the_live_bot_the_case_applies_to(self):
        """BIO discarded 132 of 305. It reads on the surviving
        population, not on the lifetime."""
        _, created, closed, discarded = BIO
        assert _ratio(created, closed, discarded)[0] == "93.06%  (161/173)"


class TestTheColourFollowsTheSameNumber:

    def test_the_three_bands_are_the_ones_this_row_always_used(self):
        from src.gui.bot_live_settings import (
            FOLD_RATIO_AMBER_FG_HEX,
            FOLD_RATIO_GREEN_FG_HEX,
            FOLD_RATIO_RED_FG_HEX,
        )

        assert _ratio(100, 40, 0)[1] == FOLD_RATIO_RED_FG_HEX
        assert _ratio(100, 60, 0)[1] == FOLD_RATIO_AMBER_FG_HEX
        assert _ratio(100, 90, 0)[1] == FOLD_RATIO_GREEN_FG_HEX

    def test_btc_is_green_where_it_used_to_be_amber(self):
        from src.gui.bot_live_settings import (
            FOLD_RATIO_AMBER_FG_HEX,
            FOLD_RATIO_GREEN_FG_HEX,
        )

        _, created, closed, discarded = BTC
        assert _ratio(created, closed, discarded)[1] == (FOLD_RATIO_GREEN_FG_HEX)
        assert (
            0.5 <= closed / created < 0.8
        ), "the old arithmetic painted this bot amber"
        assert FOLD_RATIO_AMBER_FG_HEX != FOLD_RATIO_GREEN_FG_HEX

    def test_a_denominator_under_five_is_not_judged(self):
        """The panel never coloured a verdict off a handful of cycles."""
        assert _ratio(4, 0, 0)[1] is None
