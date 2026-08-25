"""Item 5 — the per-tranche Extractor Tranche Arbiter toggle.

WHAT ITEM 5 IS
Operator, 2026-08-10: "Just have a toggling option for 'Extractor
Tranche Abiter' which decides who gets to sell it and when i.e. Parent
or Sibling", and it "should be next to each Extractor Tranche that
spawns and be a toggling status button that reads Parent or Sibling
under an Arbiter column."

So: one stored value per TRANCHE, one button per row, two words.

WHAT ITEM 5 IS NOT, AND THIS FILE PINS THE DIFFERENCE
The `Parent` value names a force-sell of the tranche by the base-
currency Scrumming Bot at a growth threshold. NO SUCH MECHANISM EXISTS
in this repository — no trigger, no threshold field, no caller. It was
deliberately not built: a toggle that records an intention is safe, and
a half-built force-sell moves real money. The tests below therefore
prove the value is STORED and SURVIVES, and prove that setting it
places no order and changes no balance. They make no claim that
anything acts on it, because nothing does.

WHY `sibling` IS THE SAFE DEFAULT
It is a description of the running code: the automatic closer is the
Extractor's own bullish exit, the operator closer is the Extractor's
own manual fire, and the parent only books money that already arrived.
Defaulting to `parent` would put a false record on every tranche and
would silently arm all of them the moment a force-sell was built.

EVERY MECHANISM HERE HAS A PAIRED CONTROL. A test that still passes
when the thing it tests is blinded is not evidence, so each group
carries a control that must fail if the mechanism stopped working.
"""

from __future__ import annotations

import copy
import json

import pytest

from src.core.event_bus import EventBus
from src.trading.bot_container import BotManager, BotMode
from src.trading.extractor_bot import (
    ARBITER_PARENT,
    ARBITER_SIBLING,
    ExtractorBot,
    ExtractorPosition,
    arbiter_label,
    normalize_arbiter,
    other_arbiter,
)
from src.trading.scrumming_bot import ScrummingBot

COINBASE = "coinbase"
ETH = "ETH"


# ─────────────────────────────────────────────────────────────────────
# Builders — the same `object.__new__` construction the item 4 listing
# tests use. The real constructors want an exchange, a bus and a live
# balance; what is under test reads a bot's type, its settings and its
# in-memory positions, and all three are genuine here.
# ─────────────────────────────────────────────────────────────────────
def _cfg(**kw):
    return type("_Cfg", (), kw)()


def _parent(bot_id="scrum-eth", target_asset=ETH, exchange=COINBASE):
    bot = object.__new__(ScrummingBot)
    bot.bot_id = bot_id
    bot.config = _cfg(
        exchange_id=exchange,
        mode=BotMode.SCRUMMING,
        target_asset=target_asset,
        base_currency="USD",
        scrumming_interval_pct=2.0,
        name=bot_id,
    )
    bot._bot_manager = None
    bot._fold_tranches = []
    bot._main_lots = []
    bot._current_holdings = 0.0
    bot._fold_queue_usd = 0.0
    bot._target_balance = 1000.0
    bot._anchor_target_balance = 1000.0
    bot._pending_wire_credits = 0.0
    bot._tranches_created_lifetime = 0
    bot._tranches_closed_lifetime = 0
    bot._tranches_discarded_lifetime = 0
    bot._bus = EventBus()
    return bot


def _child(bot_id="ext-1", base_currency=ETH, exchange=COINBASE):
    bot = object.__new__(ExtractorBot)
    bot.bot_id = bot_id
    bot.config = _cfg(
        exchange_id=exchange,
        mode=BotMode.EXTRACTOR,
        target_asset="ALT",
        base_currency=base_currency,
        name=f"name-of-{bot_id}",
        extractor_direction="normal",
        inverted_extractor_standing_alt_units=0,
    )
    bot._positions = {}
    # USD PER ONE BASE UNIT, whatever the parameter name says
    # elsewhere: `_position_value_usd` multiplies a base amount by it.
    bot._chunk_to_base_rate = 3000.0
    bot._chunk_size_base = 1.0
    bot._chunk_free_base = 1.0
    bot._chunk_size_usd = 3000.0
    bot._chunk_extracted_total = 0.0
    bot._hedge_budget_usd = 0.0
    bot._hedge_free_base = 0.0
    bot._closed_position_log = []
    bot._closed_log_max = 200
    bot._watch_list = []
    bot._tick_counter = 0
    bot._cycle_extracted_total = 0.0
    bot._lifetime_extracted_total = 0.0
    return bot


def _position(
    pair="SOL/ETH",
    alt_units=100.0,
    entry_price=0.005,
    mark=0.006,
    opened_at=1000.0,
    arbiter=None,
):
    """One open Extractor position, entered at a price for a quantity.

    `arbiter=None` means "do not name the field at all", which is how a
    position built anywhere else in the codebase is built — so the
    dataclass default is what these fixtures exercise unless a test
    deliberately asks for the other value.
    """
    cost_basis_base = alt_units * entry_price
    kw = {}
    if arbiter is not None:
        kw["arbiter"] = arbiter
    pos = ExtractorPosition(
        pair=pair,
        state="in_flight",
        artillery_size_base=cost_basis_base,
        artillery_size_usd_at_entry=cost_basis_base * 3000.0,
        alt_units=alt_units,
        entry_price_base_per_alt=entry_price,
        avg_buy_price_base_per_alt=entry_price,
        cost_basis_base=cost_basis_base,
        opened_at=opened_at,
        **kw,
    )
    if mark is not None:
        pos.last_price_base_per_alt = mark
        pos.last_priced_at = opened_at + 60.0
    return pos


def _wire(parent, *children):
    manager = BotManager(bus=EventBus())
    manager._bots[parent.bot_id] = parent
    for c in children:
        manager._bots[c.bot_id] = c
    parent._bot_manager = manager
    return manager


def _family(**pos_kw):
    """A parent, one child, one open position. The common case."""
    parent, child = _parent(), _child()
    child._positions["SOL/ETH"] = _position(**pos_kw)
    _wire(parent, child)
    return parent, child


def _id_of(child, pair):
    return child.tranche_id_for_position(child._positions[pair])


# ═════════════════════════════════════════════════════════════════════
# A. THE STORED VALUE AND ITS COERCION
# ═════════════════════════════════════════════════════════════════════
def test_a_freshly_opened_tranche_is_a_sibling():
    """The default is the value that describes the running code."""
    pos = _position()
    assert pos.arbiter == ARBITER_SIBLING
    assert ARBITER_SIBLING == "sibling"


def test_control_the_field_is_real_and_not_a_hard_coded_sibling():
    """THE CONTROL for the test above.

    A property that returned "sibling" for everything would satisfy it
    while storing nothing. Naming the other value must produce the
    other value.
    """
    pos = _position(arbiter=ARBITER_PARENT)
    assert pos.arbiter == ARBITER_PARENT
    assert ARBITER_PARENT == "parent"


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        None,
        0,
        1,
        3.5,
        "child",
        "Child",
        "paren",
        "",
        "  ",
        "parental",
        ["parent"],
        {"parent": True},
        object(),
    ],
)
def test_anything_that_is_not_the_word_parent_reads_as_sibling(value):
    """FAIL TOWARDS THE INERT VALUE.

    A typo, a bool, a None, a truncated write — every one of them must
    land on the value that changes nothing, never on the one a later
    force-sell would act on. `True` matters most: it is an int
    subclass and reaches this code from a state file as easily as a
    string does.
    """
    assert normalize_arbiter(value) == ARBITER_SIBLING


@pytest.mark.parametrize(
    "value",
    [
        "parent",
        "PARENT",
        "Parent",
        " parent ",
        "\tparent\n",
    ],
)
def test_control_the_word_parent_really_does_read_as_parent(value):
    """THE CONTROL for the test above.

    A coercion that answered "sibling" unconditionally would pass every
    case above while measuring nothing at all.
    """
    assert normalize_arbiter(value) == ARBITER_PARENT


def test_the_coercion_cannot_raise_on_an_object_that_refuses_to_print():
    """A preference must never cost the operator a position.

    `import_state` DROPS a position whose record raises, and a dropped
    record is a position the bot stops managing. So this read is
    incapable of raising: it never calls `__str__` on anything.
    """

    class _Hostile:
        def __str__(self):
            raise RuntimeError("no string for you")

        def __repr__(self):
            raise RuntimeError("nor a repr")

    assert normalize_arbiter(_Hostile()) == ARBITER_SIBLING


def test_the_two_words_on_the_surface_are_the_operators_own():
    """ "Sibling", never "child" — the operator's word, that spelling."""
    assert arbiter_label(ARBITER_PARENT) == "Parent"
    assert arbiter_label(ARBITER_SIBLING) == "Sibling"
    assert arbiter_label("nonsense") == "Sibling"


def test_a_toggle_has_exactly_two_positions():
    assert other_arbiter(ARBITER_SIBLING) == ARBITER_PARENT
    assert other_arbiter(ARBITER_PARENT) == ARBITER_SIBLING
    assert other_arbiter(other_arbiter(ARBITER_PARENT)) == ARBITER_PARENT


# ═════════════════════════════════════════════════════════════════════
# B. THE TOGGLE — one tranche, and only that one
# ═════════════════════════════════════════════════════════════════════
def test_toggling_flips_the_value_of_that_tranche():
    _, child = _family()
    tid = _id_of(child, "SOL/ETH")
    assert child.toggle_tranche_arbiter(tid) == ARBITER_PARENT
    assert child._positions["SOL/ETH"].arbiter == ARBITER_PARENT
    assert child.toggle_tranche_arbiter(tid) == ARBITER_SIBLING
    assert child._positions["SOL/ETH"].arbiter == ARBITER_SIBLING


def test_toggling_one_tranche_leaves_every_sibling_tranche_alone():
    """PER TRANCHE, NOT PER BOT — the operator's directive, measured.

    One Extractor holding three positions. Flipping one must leave the
    other two exactly as they were, or the control is a bot-wide
    setting wearing a per-row costume.
    """
    _, child = _family()
    child._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", opened_at=2000.0)
    child._positions["INJ/ETH"] = _position(pair="INJ/ETH", opened_at=3000.0)

    child.toggle_tranche_arbiter(_id_of(child, "AVAX/ETH"))

    assert child._positions["AVAX/ETH"].arbiter == ARBITER_PARENT
    assert child._positions["SOL/ETH"].arbiter == ARBITER_SIBLING
    assert child._positions["INJ/ETH"].arbiter == ARBITER_SIBLING


def test_control_each_of_those_tranches_can_be_flipped_on_its_own():
    """THE CONTROL for the test above.

    If only one position were ever writable — say the first, or the
    one whose pair sorted first — the isolation test would pass for
    the wrong reason. Each must be individually settable.
    """
    _, child = _family()
    child._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", opened_at=2000.0)
    child._positions["INJ/ETH"] = _position(pair="INJ/ETH", opened_at=3000.0)

    for pair in ("SOL/ETH", "AVAX/ETH", "INJ/ETH"):
        assert child.toggle_tranche_arbiter(_id_of(child, pair)) == ARBITER_PARENT
    assert all(p.arbiter == ARBITER_PARENT for p in child._positions.values())


def test_two_extractors_on_the_same_pair_are_told_apart():
    """`tranche_id` starts with the bot id for exactly this case.

    Two Extractors can hold the same pair against the same parent. A
    write must reach the one that owns the row, not the first match.
    """
    parent = _parent()
    kid_a, kid_b = _child("ext-a"), _child("ext-b")
    kid_a._positions["SOL/ETH"] = _position()
    kid_b._positions["SOL/ETH"] = _position()
    _wire(parent, kid_a, kid_b)

    kid_b.toggle_tranche_arbiter(_id_of(kid_b, "SOL/ETH"))

    assert kid_b._positions["SOL/ETH"].arbiter == ARBITER_PARENT
    assert kid_a._positions["SOL/ETH"].arbiter == ARBITER_SIBLING
    # And the other Extractor refuses its sibling's id outright.
    assert kid_a.toggle_tranche_arbiter(_id_of(kid_b, "SOL/ETH")) is None


def test_an_id_that_matches_nothing_is_refused_and_writes_nothing():
    _, child = _family()
    for bogus in ("", None, "ext-1|SOL/ETH", "nope", 17, "ext-1|SOL/ETH|9999.000000"):
        assert child.toggle_tranche_arbiter(bogus) is None
        assert child.set_tranche_arbiter(bogus, ARBITER_PARENT) is None
    assert child._positions["SOL/ETH"].arbiter == ARBITER_SIBLING


def test_setting_a_nonsense_value_stores_the_inert_one():
    """The setter normalises too, so no third value can be stored."""
    _, child = _family()
    tid = _id_of(child, "SOL/ETH")
    assert child.set_tranche_arbiter(tid, "banana") == ARBITER_SIBLING
    assert child.set_tranche_arbiter(tid, True) == ARBITER_SIBLING
    assert child.set_tranche_arbiter(tid, "parent") == ARBITER_PARENT
    assert child._positions["SOL/ETH"].arbiter == ARBITER_PARENT


# ═════════════════════════════════════════════════════════════════════
# C. IDENTITY SURVIVES A CLOSE
# ═════════════════════════════════════════════════════════════════════
def test_the_right_tranche_changes_after_another_one_has_closed():
    """A row index would be wrong here. The identity is not.

    The table is a snapshot and the Extractors keep ticking behind it,
    so by the time a button is clicked an earlier tranche may be gone.
    """
    _, child = _family()
    child._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", opened_at=2000.0)
    child._positions["INJ/ETH"] = _position(pair="INJ/ETH", opened_at=3000.0)
    captured = _id_of(child, "INJ/ETH")

    # The first tranche exits while the captured id sits in a closure.
    del child._positions["SOL/ETH"]

    assert child.toggle_tranche_arbiter(captured) == ARBITER_PARENT
    assert child._positions["INJ/ETH"].arbiter == ARBITER_PARENT
    assert child._positions["AVAX/ETH"].arbiter == ARBITER_SIBLING


def test_a_reopened_position_does_not_inherit_the_closed_ones_setting():
    """`opened_at` is in the id for exactly this reason.

    `_positions` is keyed by PAIR, so a pair-keyed write would land on
    the successor position and silently mislabel a tranche the
    operator never touched.
    """
    _, child = _family()
    old_id = _id_of(child, "SOL/ETH")
    child.toggle_tranche_arbiter(old_id)
    assert child._positions["SOL/ETH"].arbiter == ARBITER_PARENT

    # Same pair, new position, opened later.
    del child._positions["SOL/ETH"]
    child._positions["SOL/ETH"] = _position(opened_at=5000.0)

    assert child.toggle_tranche_arbiter(old_id) is None
    assert child._positions["SOL/ETH"].arbiter == ARBITER_SIBLING


def test_control_the_reopened_position_is_settable_by_its_own_id():
    """THE CONTROL for the test above.

    If NOTHING could be written after a reopen, the refusal above
    would prove nothing about identity. The successor's own id works.
    """
    _, child = _family()
    del child._positions["SOL/ETH"]
    child._positions["SOL/ETH"] = _position(opened_at=5000.0)
    new_id = _id_of(child, "SOL/ETH")
    assert child.toggle_tranche_arbiter(new_id) == ARBITER_PARENT


def test_the_id_the_row_carries_is_the_id_the_setter_accepts():
    """One format, one copy. The emitter and the setter must agree.

    If the row formatted `opened_at` differently from the resolver,
    every click would be refused — or, worse, match the wrong row.
    """
    parent, child = _family()
    row = parent.open_extractor_tranches()[0]
    assert row["tranche_id"] == _id_of(child, "SOL/ETH")
    assert (
        child.set_tranche_arbiter(row["tranche_id"], ARBITER_PARENT) == ARBITER_PARENT
    )


# ═════════════════════════════════════════════════════════════════════
# D. PERSISTENCE — it has to survive a restart to be worth anything
# ═════════════════════════════════════════════════════════════════════
def _restore(child, state):
    """Rebuild a second Extractor from a state dict, as a restart does."""
    fresh = _child(child.bot_id)
    fresh.import_state(state)
    return fresh


def test_the_value_round_trips_through_export_and_import():
    _, child = _family()
    child._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", opened_at=2000.0)
    child.toggle_tranche_arbiter(_id_of(child, "SOL/ETH"))

    restored = _restore(child, child.export_state())

    assert restored._positions["SOL/ETH"].arbiter == ARBITER_PARENT
    assert restored._positions["AVAX/ETH"].arbiter == ARBITER_SIBLING


def test_the_value_survives_the_json_file_the_fleet_actually_writes():
    """Not just a dict copy. `StateManager` serialises with `json.dump`
    and reads it back, so the value is round-tripped through real JSON
    text here rather than through an in-process object."""
    _, child = _family()
    child.toggle_tranche_arbiter(_id_of(child, "SOL/ETH"))

    on_disk = json.loads(json.dumps(child.export_state(), default=str))
    restored = _restore(child, on_disk)

    assert restored._positions["SOL/ETH"].arbiter == ARBITER_PARENT


def test_export_names_the_key_for_every_position():
    """The export literal is an EXPLICIT key list, not a dataclass
    dump: a field that is not named there is dropped on every save."""
    _, child = _family()
    child._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", opened_at=2000.0)
    saved = child.export_state()["positions"]
    assert len(saved) == 2
    assert all("arbiter" in p for p in saved)


def test_a_saved_position_with_no_arbiter_field_loads_as_a_sibling():
    """BACKWARD COMPATIBILITY. Every state file written before item 5
    lacks this key — which today is every state file that exists."""
    _, child = _family()
    state = child.export_state()
    for pdict in state["positions"]:
        del pdict["arbiter"]

    restored = _restore(child, state)

    assert restored._positions["SOL/ETH"].arbiter == ARBITER_SIBLING


def test_control_the_importer_reads_the_field_instead_of_defaulting():
    """THE CONTROL for the test above.

    An importer that ignored the key entirely and always wrote
    "sibling" would pass the backward-compatibility test while
    throwing the operator's setting away on every restart.
    """
    _, child = _family()
    child.toggle_tranche_arbiter(_id_of(child, "SOL/ETH"))
    state = child.export_state()
    assert state["positions"][0]["arbiter"] == ARBITER_PARENT

    restored = _restore(child, state)

    assert restored._positions["SOL/ETH"].arbiter == ARBITER_PARENT


def test_an_old_record_loads_otherwise_completely_unchanged():
    """ "Exactly as before" is a claim about EVERY field, not one.

    A field added to the constructor call is a chance to disturb the
    others, so the whole restored position is compared against the
    original save minus the new key.
    """
    _, child = _family()
    state = child.export_state()
    original = copy.deepcopy(state["positions"][0])
    del state["positions"][0]["arbiter"]

    restored = _restore(child, state)
    round_tripped = restored.export_state()["positions"][0]

    assert round_tripped == original


@pytest.mark.parametrize("bad", [True, None, "banana", 7, ["parent"]])
def test_a_corrupt_arbiter_value_never_drops_the_position(bad):
    """`import_state` DROPS a record whose rebuild raises, and a
    dropped record is a position the bot stops managing. A preference
    about who may sell must never cost the operator a position."""
    _, child = _family()
    state = child.export_state()
    state["positions"][0]["arbiter"] = bad

    restored = _restore(child, state)

    assert "SOL/ETH" in restored._positions
    assert restored._positions["SOL/ETH"].arbiter == ARBITER_SIBLING
    assert restored._positions["SOL/ETH"].alt_units == pytest.approx(100.0)


def test_control_import_still_drops_a_record_that_is_genuinely_broken():
    """THE CONTROL for the test above.

    If the importer had stopped dropping anything at all, the test
    above would pass without proving the arbiter read is the safe one.
    A record whose REQUIRED key is missing must still be dropped.
    """
    _, child = _family()
    state = child.export_state()
    del state["positions"][0]["pair"]

    restored = _restore(child, state)

    assert restored._positions == {}


# ═════════════════════════════════════════════════════════════════════
# E. THE ROW THE PARENT PUBLISHES
# ═════════════════════════════════════════════════════════════════════
def test_the_parents_row_carries_the_arbiter_value():
    """The row dict is the ONLY thing the surface sees."""
    parent, child = _family()
    assert parent.open_extractor_tranches()[0]["arbiter"] == (ARBITER_SIBLING)

    child.toggle_tranche_arbiter(_id_of(child, "SOL/ETH"))

    assert parent.open_extractor_tranches()[0]["arbiter"] == (ARBITER_PARENT)


def test_the_row_reports_one_of_the_two_values_even_when_state_is_junk():
    """A surface that trusts this dict can never be handed a third
    value, so the emitter normalises on the way out as well as in."""
    parent, child = _family()
    child._positions["SOL/ETH"].arbiter = "something else entirely"
    assert parent.open_extractor_tranches()[0]["arbiter"] == (ARBITER_SIBLING)


# ═════════════════════════════════════════════════════════════════════
# F. NO MONEY MOVES — the whole safety argument for shipping this alone
# ═════════════════════════════════════════════════════════════════════
class _RecordingExchange:
    """A stub that records every call and performs none.

    Named methods rather than a catch-all `__getattr__`, so the test
    states exactly which operations it is watching for.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return None

    def create_order(self, *a, **kw):
        return self._record("create_order", *a, **kw)

    def place_order(self, *a, **kw):
        return self._record("place_order", *a, **kw)

    def cancel_order(self, *a, **kw):
        return self._record("cancel_order", *a, **kw)

    def get_ticker(self, *a, **kw):
        return self._record("get_ticker", *a, **kw)

    def get_balance(self, *a, **kw):
        return self._record("get_balance", *a, **kw)

    def get_ohlcv(self, *a, **kw):
        return self._record("get_ohlcv", *a, **kw)


def _money_snapshot(parent, child):
    """Every number a toggle could plausibly disturb."""
    return {
        "target_balance": parent._target_balance,
        "anchor_target_balance": parent._anchor_target_balance,
        "current_holdings": parent._current_holdings,
        "fold_queue_usd": parent._fold_queue_usd,
        "fold_tranches": copy.deepcopy(parent._fold_tranches),
        "main_lots": copy.deepcopy(parent._main_lots),
        "chunk_free_base": child._chunk_free_base,
        "chunk_size_base": child._chunk_size_base,
        "chunk_extracted_total": child._chunk_extracted_total,
        "hedge_free_base": child._hedge_free_base,
        "alt_units": child._positions["SOL/ETH"].alt_units,
        "cost_basis_base": child._positions["SOL/ETH"].cost_basis_base,
        "state": child._positions["SOL/ETH"].state,
    }


def test_toggling_places_no_order_and_changes_no_balance():
    """The reason this ships without the force-sell.

    Asserted against a stub exchange that RECORDS calls, and against
    every balance on both bots, because "it only writes a string" is a
    claim and this is the measurement of it.
    """
    parent, child = _family()
    exchange = _RecordingExchange()
    child.exchange = exchange
    parent.exchange = exchange
    before = _money_snapshot(parent, child)

    child.toggle_tranche_arbiter(_id_of(child, "SOL/ETH"))
    child.set_tranche_arbiter(_id_of(child, "SOL/ETH"), ARBITER_PARENT)

    assert exchange.calls == []
    assert _money_snapshot(parent, child) == before
    # The one thing that DID change.
    assert child._positions["SOL/ETH"].arbiter == ARBITER_PARENT


def test_control_the_stub_exchange_records_a_call_when_one_is_made():
    """THE CONTROL for the test above.

    A stub that recorded nothing would report "no orders placed" for
    any code at all, including code that placed one. It must be able
    to see a call.
    """
    exchange = _RecordingExchange()
    exchange.create_order("SOL/ETH", "buy", 1.0)
    assert exchange.calls == [("create_order", ("SOL/ETH", "buy", 1.0), {})]


def test_control_the_money_snapshot_notices_a_change():
    """THE CONTROL for the snapshot comparison.

    A snapshot that compared equal to itself regardless would make the
    balance assertion above vacuous.
    """
    parent, child = _family()
    before = _money_snapshot(parent, child)
    parent._target_balance += 1.0
    assert _money_snapshot(parent, child) != before


# ═════════════════════════════════════════════════════════════════════
# G. THE SURFACE — the operator's button
# ═════════════════════════════════════════════════════════════════════
pytest.importorskip("PySide6.QtWidgets")

FIRE_COLUMN = 9
FOLD_ROW = 0
EXT_ROWS = (1, 2)


def _build_tab(parent):
    """Build the REAL Open Tranches tab for `parent`.

    `QDialog.__init__` directly, so the object is a genuine dialog
    carrying every real method without the construction path that
    wants a live bot, an exchange and a bus. The tab itself is built
    by the production code under test.
    """
    from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])

    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = parent
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    tables = widget.findChildren(QTableWidget)
    assert tables, "the tab rendered no table"
    return dlg, widget, tables[0]


def _destroy_tab(dlg, widget) -> None:
    """Destroy a dialog built by `_build_tab`. NOT optional.

    THE QApplication IS SHARED BY THE WHOLE TEST SESSION, and other
    suites enumerate `app.topLevelWidgets()` to find the dialog they
    just opened — `tests/test_sim_visuals_expand_reentrancy.py` takes
    the FIRST QDialog it finds there and asserts that closing it
    destroys it. A dialog left alive by this file becomes that first
    one, and their assertion then fails on an object they never made.

    MEASURED, not guessed: running this file immediately before that
    one failed `test_the_dialog_does_not_outlive_its_close` until this
    teardown existed, and passed with it. A leak here is a defect in
    THIS file even though the failure surfaces in another.

    `deleteLater()` ALONE IS NOT ENOUGH HERE, and the guard test at
    the bottom of this file is what proved it: after `close()` +
    `deleteLater()` + `processEvents()`, fourteen dialogs were still
    standing. Qt only delivers a DeferredDelete when the event loop
    unwinds to the level that posted it, and these tests never enter
    one, so the deletes sat in the queue.

    EACH `sendPostedEvents` NAMES ITS RECEIVER, and that is not a
    detail. The receiver-less form flushes the DeferredDelete queue
    for EVERY object in the application, including objects other
    suites have scheduled and still hold references to. Measured: with
    `sendPostedEvents(None, ...)` the full suite died mid-file with no
    traceback — a hard interpreter exit, not a test failure. Naming
    the receiver deletes exactly these two objects and leaves every
    other suite's queue untouched.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    widget.setParent(None)
    dlg.close()
    widget.deleteLater()
    dlg.deleteLater()
    QApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    QApplication.sendPostedEvents(dlg, QEvent.Type.DeferredDelete)


@pytest.fixture
def _family_tab():
    """One fold tranche and TWO Extractor Tranches, on one table.

    Two Extractor rows, because a per-row control that quietly wrote
    to "the" tranche would look perfectly correct with one.
    """
    parent = _parent()
    kid_a, kid_b = _child("ext-a"), _child("ext-b")
    kid_a._positions["SOL/ETH"] = _position()
    kid_b._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", opened_at=2000.0)
    _wire(parent, kid_a, kid_b)
    parent._fold_tranches = [
        {
            "usd": 25.0,
            "units": 0.01,
            "ref": 2100.0,
            "initial_buy_price": 2000.0,
            "created_ts": 1.0,
            "operator_initiated": True,
        }
    ]
    parent.get_status = lambda: {"stats": {"current_price": 2000.0}}

    dlg, widget, table = _build_tab(parent)
    # YIELD, not return: the tab widget has no parent, so returning
    # would drop the last reference and Qt would destroy the table
    # before the test touched it.
    yield parent, kid_a, kid_b, table, dlg
    _destroy_tab(dlg, widget)


def test_the_arbiter_column_is_appended_after_fire(_family_tab):
    """Column 9 is the Fire column and stays the Fire column.

    Fire dispatches a REAL market buy. Renumbering it to make room for
    a toggle would put an unguarded control where a money-moving one
    is expected — which is why the new column is APPENDED.
    """
    from src.gui.bot_live_settings import (
        ARBITER_COLUMN_INDEX,
        ARBITER_COLUMN_HEADER,
    )

    _, _, _, table, _ = _family_tab

    assert ARBITER_COLUMN_INDEX == 10
    assert table.columnCount() == 11
    assert table.horizontalHeaderItem(FIRE_COLUMN).text() == "Fire"
    assert (
        table.horizontalHeaderItem(ARBITER_COLUMN_INDEX).text() == ARBITER_COLUMN_HEADER
    )
    assert ARBITER_COLUMN_HEADER == "Arbiter"


def test_each_extractor_row_has_its_own_toggle_reading_sibling(_family_tab):
    """A toggling status button per row, in the operator's words."""
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    _, _, _, table, _ = _family_tab

    buttons = [table.cellWidget(r, ARBITER_COLUMN_INDEX) for r in EXT_ROWS]
    assert all(b is not None for b in buttons)
    assert [b.text() for b in buttons] == ["Sibling", "Sibling"]
    assert buttons[0] is not buttons[1]


def test_the_button_label_matches_the_stored_value(_family_tab):
    """The word on the button is not decoration; it reports the field.

    Built with one tranche already set to parent, so a button that
    always said "Sibling" would fail here.
    """
    parent, kid_a, _, _, _ = _family_tab
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    kid_a._positions["SOL/ETH"].arbiter = ARBITER_PARENT
    second_dlg, second_widget, table = _build_tab(parent)
    try:
        labels = sorted(
            table.cellWidget(r, ARBITER_COLUMN_INDEX).text() for r in EXT_ROWS
        )
        assert labels == ["Parent", "Sibling"]
    finally:
        _destroy_tab(second_dlg, second_widget)


def test_clicking_the_toggle_flips_the_stored_value_and_the_label(_family_tab):
    """The click reaches the CHILD's position, not a display copy."""
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    _, kid_a, kid_b, table, _ = _family_tab

    row = _row_of(table, "ext-a")
    button = table.cellWidget(row, ARBITER_COLUMN_INDEX)
    button.click()

    assert kid_a._positions["SOL/ETH"].arbiter == ARBITER_PARENT
    assert button.text() == "Parent"
    # The model cell agrees with the widget.
    assert table.item(row, ARBITER_COLUMN_INDEX).text() == "Parent"
    # And the other tranche is untouched, on both surfaces.
    assert kid_b._positions["AVAX/ETH"].arbiter == ARBITER_SIBLING
    other = _row_of(table, "ext-b")
    assert table.cellWidget(other, ARBITER_COLUMN_INDEX).text() == "Sibling"


def test_clicking_twice_returns_the_tranche_to_sibling(_family_tab):
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    _, kid_a, _, table, _ = _family_tab

    button = table.cellWidget(_row_of(table, "ext-a"), ARBITER_COLUMN_INDEX)
    button.click()
    button.click()

    assert kid_a._positions["SOL/ETH"].arbiter == ARBITER_SIBLING
    assert button.text() == "Sibling"


def _row_of(table, child_bot_id):
    """Find an Extractor row by the child that owns it.

    BY CONTENT, NEVER BY A HARD-CODED ROW NUMBER: the rows are sorted
    by tranche id, so pinning row 1 to a particular child would make
    these tests pass or fail on an unrelated ordering change.
    """
    for row in EXT_ROWS:
        tip = table.item(row, 0).toolTip()
        if child_bot_id in tip:
            return row
    raise AssertionError(f"no Extractor row for {child_bot_id}")


def test_a_click_on_a_tranche_that_closed_changes_nothing(_family_tab, monkeypatch):
    """The table is a snapshot and the Extractors keep ticking.

    A position can close while the panel sits on screen. The click
    must refuse rather than write to whatever is there now.
    """
    from PySide6.QtWidgets import QMessageBox

    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    _, kid_a, kid_b, table, _ = _family_tab

    warnings: list[tuple] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or QMessageBox.Ok
    )

    row = _row_of(table, "ext-a")
    button = table.cellWidget(row, ARBITER_COLUMN_INDEX)
    kid_a._positions.clear()  # the Extractor exited
    button.click()

    assert warnings, "a refusal must be reported, not swallowed"
    assert button.text() == "Sibling", "the label claimed a write"
    assert kid_a._positions == {}
    assert kid_b._positions["AVAX/ETH"].arbiter == ARBITER_SIBLING


def test_control_the_same_click_works_while_the_tranche_is_open(
    _family_tab, monkeypatch
):
    """THE CONTROL for the test above.

    If clicks never did anything, the refusal test would pass for a
    reason unrelated to the tranche closing.
    """
    from PySide6.QtWidgets import QMessageBox

    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    _, kid_a, _, table, _ = _family_tab

    warnings: list[tuple] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or QMessageBox.Ok
    )

    button = table.cellWidget(_row_of(table, "ext-a"), ARBITER_COLUMN_INDEX)
    button.click()

    assert warnings == []
    assert button.text() == "Parent"
    assert kid_a._positions["SOL/ETH"].arbiter == ARBITER_PARENT


def test_a_click_reaches_the_child_that_owns_the_row(_family_tab):
    """Rows from several Extractors are merged into one list, so the
    write must be routed by `child_bot_id`, not to "the" Extractor."""
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    _, kid_a, kid_b, table, _ = _family_tab

    table.cellWidget(_row_of(table, "ext-b"), ARBITER_COLUMN_INDEX).click()

    assert kid_b._positions["AVAX/ETH"].arbiter == ARBITER_PARENT
    assert kid_a._positions["SOL/ETH"].arbiter == ARBITER_SIBLING


def test_clicking_the_toggle_places_no_order(_family_tab):
    """The control sits one column from a live Fire button."""
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    parent, kid_a, kid_b, table, _ = _family_tab

    exchange = _RecordingExchange()
    for bot in (parent, kid_a, kid_b):
        bot.exchange = exchange
    before = _money_snapshot(parent, kid_a)

    for row in EXT_ROWS:
        table.cellWidget(row, ARBITER_COLUMN_INDEX).click()

    assert exchange.calls == []
    after = _money_snapshot(parent, kid_a)
    after["arbiter_ignored"] = None
    before["arbiter_ignored"] = None
    assert after == before


def test_a_fold_row_has_no_arbiter_button_and_says_so(_family_tab):
    """An Arbiter belongs to an Extractor Tranche. A fold tranche has
    no child holding it, so the cell prints the same em dash item 4
    prints under Fire on an Extractor row."""
    from src.gui.bot_live_settings import (
        ARBITER_COLUMN_INDEX,
        ARBITER_NOT_APPLICABLE,
    )

    _, _, _, table, _ = _family_tab

    assert table.cellWidget(FOLD_ROW, ARBITER_COLUMN_INDEX) is None
    assert table.item(FOLD_ROW, ARBITER_COLUMN_INDEX).text() == (ARBITER_NOT_APPLICABLE)
    assert ARBITER_NOT_APPLICABLE == "—"


def test_the_fold_row_keeps_its_fire_button_where_it_was(_family_tab):
    """Item 4's arrangement is unchanged by the new column."""
    _, _, _, table, _ = _family_tab

    fire = table.cellWidget(FOLD_ROW, FIRE_COLUMN)
    assert fire is not None
    assert fire.text() == "Fire"
    for row in EXT_ROWS:
        assert table.cellWidget(row, FIRE_COLUMN) is None
        assert table.item(row, FIRE_COLUMN).text() == "—"


def test_every_column_of_both_row_kinds_is_still_painted(_family_tab):
    """The new column must not end the coloured band one cell short.

    That is the exact defect the Fire column caused on fold rows, and
    a cell holding only a widget would reproduce it.
    """
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_FG_HEX,
        FOLD_TRANCHE_BG_HEX,
    )

    _, _, _, table, _ = _family_tab

    for col in range(table.columnCount()):
        fold = table.item(FOLD_ROW, col)
        assert fold is not None, f"fold column {col} has no item"
        assert fold.background().color().name() == FOLD_TRANCHE_BG_HEX
        for row in EXT_ROWS:
            cell = table.item(row, col)
            assert cell is not None, f"ext column {col} has no item"
            assert cell.background().color().name() == (EXTRACTOR_TRANCHE_BG_HEX)
            assert cell.foreground().color().name() == (EXTRACTOR_TRANCHE_FG_HEX)


def test_the_toggle_carries_the_inset_that_frees_the_container_edge(_family_tab):
    """`setCellWidget` paints a widget over the delegate's rule, so a
    full-height button breaks the row's edge at its own column — the
    measured defect the Fire button's margin exists to prevent."""
    from src.gui.bot_live_settings import (
        ARBITER_COLUMN_INDEX,
        EXTRACTOR_TRANCHE_BG_HEX,
        TRANCHE_FIRE_BTN_INSET_PX,
    )

    _, _, _, table, _ = _family_tab

    sheet = table.cellWidget(EXT_ROWS[0], ARBITER_COLUMN_INDEX).styleSheet()
    assert f"margin: {TRANCHE_FIRE_BTN_INSET_PX // 2}px 0px" in sheet
    # And it sits ON the row fill, so the red band stays continuous.
    assert EXTRACTOR_TRANCHE_BG_HEX in sheet


def test_this_file_leaves_no_dialog_alive_for_the_next_suite():
    """A leaked QDialog is the NEXT suite's failure, not this one's.

    `tests/test_sim_visuals_expand_reentrancy.py` finds the dialog it
    just opened by taking the first QDialog in
    `app.topLevelWidgets()`, then asserts that closing it destroys it.
    A dialog left alive here becomes that first one and fails their
    assertion on an object they never created — which is exactly what
    happened while this file was being written, and is why
    `_destroy_tab` exists.

    THE CONTROL IS BUILT IN: the middle assertion proves a build
    really does add a dialog, so the final assertion cannot pass by
    counting nothing.
    """
    from PySide6.QtWidgets import QApplication

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    app = QApplication.instance() or QApplication([])

    def _mine():
        return [
            w for w in app.topLevelWidgets() if isinstance(w, BotLiveSettingsDialog)
        ]

    parent, _ = _family()
    parent.get_status = lambda: {"stats": {"current_price": 2000.0}}
    before = len(_mine())

    dlg, widget, _table = _build_tab(parent)
    assert len(_mine()) == before + 1, (
        "the build added no dialog, so the teardown check below would " "prove nothing"
    )

    _destroy_tab(dlg, widget)
    assert (
        len(_mine()) == before
    ), "a dialog outlived this test and will break the next suite"


def test_the_tooltip_does_not_claim_a_behaviour_that_does_not_exist():
    """THE HONESTY TEST.

    The parent force-sell that `Parent` names is not built. A tooltip
    describing it as working behaviour would be a false claim about
    the fleet, made on the operator's own screen.
    """
    from src.gui.bot_live_settings import _compose_arbiter_tooltip

    tip = _compose_arbiter_tooltip(ARBITER_PARENT)
    assert tip.startswith("ARBITER: Parent")
    assert "Sibling" in tip
    assert "no order" in tip.lower()
    assert "not built" in tip.lower()
    assert _compose_arbiter_tooltip(ARBITER_SIBLING).startswith("ARBITER: Sibling")
