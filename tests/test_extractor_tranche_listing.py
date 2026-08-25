"""Item 4 — an Extractor Tranche is listed and valued under its parent.

WHAT ITEM 4 IS
An Extractor spends a base currency that a Scrumming Bot owns. While the
Extractor holds a position, that position is an "Extractor Tranche", and
the operator's design says it is "listed under the base-currency bot" and
its "value is tracked by the parent Scrumming Bot".

So the parent can now enumerate what is leased out of its asset. A claim
that lives in the parent cannot be invisible to the parent.

WHAT ITEM 4 IS NOT
It is a RECORD, not a transfer. Nothing here moves money, raises a target
balance or places an order. The lift that contains a child's returned
gain is item 1's `apply_extractor_tranche_return`, which is untouched.

THE THING THIS FILE MOSTLY EXISTS TO PROVE
The parent must never trade on an Extractor Tranche. If a lease were
counted as the parent's own inventory, the parent would SCRUM units it
does not hold, or open a fold gate against a tranche it cannot discharge.
The design removes that whole surface by construction: an Extractor
Tranche is a COMPUTED VIEW and is never written into `_fold_tranches` or
`_main_lots`, which are the only two lists the trading path reads.

"By construction" is a claim, so the HAZARD tests below check it site by
site, one test per consumer named in the read phase, against the exact
expression that consumer evaluates.

EVERY MECHANISM HERE HAS A PAIRED CONTROL. A test that passes when the
mechanism is blinded is not evidence, so each group carries a control
that must fail if the thing under test stopped working.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.trading.bot_container import BotManager, BotMode  # noqa: E402
from src.trading.extractor_bot import (  # noqa: E402
    ExtractorBot,
    ExtractorPosition,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

COINBASE = "coinbase"
KRAKEN = "kraken"

# The parent's asset, and therefore the currency a child must spend to
# be a child of it.
ETH = "ETH"


# ─────────────────────────────────────────────────────────────────────
# Builders
#
# Built with `object.__new__`, which is how `test_extractor_parent_
# lookup.py` builds the same two bot types. The real constructors want
# an exchange, a bus and a live balance; the code under test reads a
# bot's type, its settings and its in-memory positions, and all three
# of those are genuine here.
# ─────────────────────────────────────────────────────────────────────
def _cfg(**kw):
    return type("_Cfg", (), kw)()


def _parent(bot_id="scrum-eth", target_asset=ETH, exchange=COINBASE):
    """A Scrumming Bot holding `target_asset`, with an empty book."""
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
    # The parent's own books. Everything the trading path reads.
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
    # The rest of what `import_scrumming_state` reads as its own
    # defaults. Present so the persistence tests exercise the REAL
    # importer rather than a reduced stand-in.
    bot._last_trade_price = 0.0
    bot._last_trade_side = None
    bot._quote_to_usd = 1.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._tranches_malformed_dropped = 0
    bot._stack_tranches = []
    bot._stack_created = 0
    bot._dist_accumulator = 0.0
    bot._standing_surplus_usd = 0.0
    bot._hedge_bal = 0.0
    bot._hedge_trades = 0
    bot._hyst_armed_fold_side = False
    bot._hyst_armed_scrum_side = False
    bot._hyst_ref_fold_side = 0.0
    bot._hyst_ref_scrum_side = 0.0
    bot._cb_hard_tripped = False
    bot._bus = EventBus()
    return bot


def _child(
    bot_id="ext-1", base_currency=ETH, exchange=COINBASE, rate_usd_per_base=3000.0
):
    """An Extractor spending `base_currency`, holding nothing yet."""
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
    # USD PER ONE BASE UNIT. Pinned by `set_initial_chunk_rate`, which
    # divides a USD chunk by it to get base units, and by
    # `_position_value_usd`, which multiplies a base amount by it to get
    # USD. The parameter it arrives under is named `base_per_usd`, which
    # says the opposite; the arithmetic is what governs.
    bot._chunk_to_base_rate = rate_usd_per_base
    bot._chunk_size_base = 1.0
    bot._chunk_free_base = 1.0
    # What `export_state` writes and `import_state` reads, so the
    # persistence tests run the REAL round trip.
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
    # `_is_inverted` is a read-only property derived from
    # `config.extractor_direction`, so it is set on the config, not on
    # the bot.
    return bot


def _position(
    pair="SOL/ETH",
    alt_units=100.0,
    entry_price=0.005,
    mark=None,
    opened_at=1000.0,
    state="in_flight",
):
    """One open Extractor position.

    The ENTRY PRICE is the input and the cost basis follows from it by
    multiplication. Deriving the price by dividing a cost basis instead
    would be the same numbers, but it marks this fixture as a
    dimensionless quantity for the rest of the file and every later
    `pos.<field> == approx(<absolute>)` then reads as a units mismatch.
    A position is entered at a price, for a quantity, so this is also
    the order the real bot builds one in.
    """
    cost_basis_base = alt_units * entry_price
    pos = ExtractorPosition(
        pair=pair,
        state=state,
        artillery_size_base=cost_basis_base,
        artillery_size_usd_at_entry=cost_basis_base * 3000.0,
        alt_units=alt_units,
        entry_price_base_per_alt=entry_price,
        avg_buy_price_base_per_alt=entry_price,
        cost_basis_base=cost_basis_base,
        opened_at=opened_at,
    )
    if mark is not None:
        pos.last_price_base_per_alt = mark
        pos.last_priced_at = opened_at + 60.0
    return pos


def _wire(parent, *children):
    """Put the bots on one manager's books and attach the back-link."""
    manager = BotManager(bus=EventBus())
    manager._bots[parent.bot_id] = parent
    for c in children:
        manager._bots[c.bot_id] = c
    parent._bot_manager = manager
    return manager


def _family(mark=0.006, **pos_kw):
    """A parent, one child, and one marked position. The common case."""
    parent, child = _parent(), _child()
    child._positions["SOL/ETH"] = _position(mark=mark, **pos_kw)
    _wire(parent, child)
    return parent, child


# ═════════════════════════════════════════════════════════════════════
# A. THE LISTING
# ═════════════════════════════════════════════════════════════════════
def test_parent_lists_the_tranche_while_the_child_holds_a_position():
    parent, _ = _family()
    rows = parent.open_extractor_tranches()
    assert len(rows) == 1
    assert rows[0]["kind"] == "extractor"
    assert rows[0]["pair"] == "SOL/ETH"
    assert rows[0]["child_bot_id"] == "ext-1"
    assert rows[0]["base_asset"] == ETH


def test_control_parent_lists_nothing_when_the_child_holds_nothing():
    """The control for the test above.

    If the listing returned rows regardless of what the child holds, the
    test above would pass while proving nothing. The child here is wired
    identically and simply has no position.
    """
    parent, child = _parent(), _child()
    _wire(parent, child)
    assert parent.open_extractor_tranches() == []


def test_parent_lists_nothing_without_a_bot_manager():
    parent, child = _parent(), _child()
    child._positions["SOL/ETH"] = _position(mark=0.006)
    # No `_wire`: the bot was never registered.
    assert parent.open_extractor_tranches() == []


def test_parent_does_not_list_an_extractor_on_another_exchange():
    parent = _parent(exchange=COINBASE)
    child = _child(exchange=KRAKEN)
    child._positions["SOL/ETH"] = _position(mark=0.006)
    _wire(parent, child)
    assert parent.open_extractor_tranches() == []


def test_parent_does_not_list_an_extractor_spending_another_asset():
    parent = _parent(target_asset="ETH")
    child = _child(base_currency="BTC")
    child._positions["SOL/BTC"] = _position(pair="SOL/BTC", mark=0.006)
    _wire(parent, child)
    assert parent.open_extractor_tranches() == []


def test_parent_lists_tranches_from_every_matching_child():
    """Several Extractors may lease from one parent at once.

    The PAYMENT lookup refuses when two bots match, because a payment
    cannot be split by guessing. Listing has no such problem and must
    name them all.
    """
    parent = _parent()
    c1, c2 = _child(bot_id="ext-a"), _child(bot_id="ext-b")
    c1._positions["SOL/ETH"] = _position(mark=0.006)
    c2._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", mark=0.002)
    _wire(parent, c1, c2)
    rows = parent.open_extractor_tranches()
    assert {r["child_bot_id"] for r in rows} == {"ext-a", "ext-b"}


def test_one_broken_child_does_not_blind_the_parent_to_the_others():
    parent = _parent()
    good, bad = _child(bot_id="ext-good"), _child(bot_id="ext-bad")
    good._positions["SOL/ETH"] = _position(mark=0.006)

    def _raise():
        raise RuntimeError("child is wedged")

    bad.extractor_tranche_rows = _raise
    _wire(parent, good, bad)
    rows = parent.open_extractor_tranches()
    assert [r["child_bot_id"] for r in rows] == ["ext-good"]


def test_listing_is_ordered_the_same_way_on_every_read():
    parent = _parent()
    c1, c2 = _child(bot_id="ext-b"), _child(bot_id="ext-a")
    c1._positions["SOL/ETH"] = _position(mark=0.006)
    c2._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", mark=0.002)
    _wire(parent, c1, c2)
    first = [r["tranche_id"] for r in parent.open_extractor_tranches()]
    second = [r["tranche_id"] for r in parent.open_extractor_tranches()]
    assert first == second == sorted(first)


# ═════════════════════════════════════════════════════════════════════
# B. THE VALUE
# ═════════════════════════════════════════════════════════════════════
def test_tracked_value_reflects_the_marked_position():
    parent, _ = _family(mark=0.006, alt_units=100.0)
    row = parent.open_extractor_tranches()[0]
    # 100 alt x 0.006 ETH/alt = 0.6 ETH
    assert row["mark_value_base"] == pytest.approx(0.6)
    # 0.6 ETH x 3000 USD/ETH = 1800 USD
    assert row["mark_value_usd"] == pytest.approx(1800.0)


def test_control_tracked_value_moves_when_the_mark_moves():
    """The control for the test above.

    A hard-coded value, or one derived from cost basis, would satisfy
    the previous test and never move. This doubles the price and
    requires the reported value to double with it.
    """
    parent, child = _family(mark=0.006, alt_units=100.0)
    before = parent.open_extractor_tranches()[0]["mark_value_usd"]
    child._positions["SOL/ETH"].last_price_base_per_alt = 0.012
    after = parent.open_extractor_tranches()[0]["mark_value_usd"]
    assert after == pytest.approx(before * 2.0)


def test_mark_in_usd_multiplies_by_the_rate_and_does_not_divide():
    """The rate is USD per base unit, so base x rate is USD.

    Inverting it is the defect this pins. At a real ETH rate the
    inverted answer is out by a factor of nine million, and it would
    read as a plausible small number rather than as an obvious error.
    """
    parent, _ = _family(mark=0.006, alt_units=100.0)
    row = parent.open_extractor_tranches()[0]
    base = row["mark_value_base"]
    assert row["mark_value_usd"] == pytest.approx(base * 3000.0)
    assert row["mark_value_usd"] != pytest.approx(base / 3000.0)


def test_an_unpriced_position_reports_no_mark_rather_than_cost_basis():
    """Cost basis must never be dressed up as a current value.

    `positions_for_gui` substitutes the average buy price when it has no
    live price, which makes its "current" value equal cost basis and its
    delta near zero by construction. Repeating that here would put a
    stale purchase price under a market-value heading in the parent's
    own ledger.
    """
    parent, _ = _family(mark=None, entry_price=0.005)
    row = parent.open_extractor_tranches()[0]
    assert row["mark_value_base"] is None
    assert row["mark_value_usd"] is None
    assert row["mark_price_base_per_alt"] is None
    assert row["marked_at"] is None
    # The cost basis is still reported — under its own name.
    assert row["cost_basis_base"] == pytest.approx(0.5)


def test_base_deployed_needs_no_price_at_all():
    """How much of MY asset is out on lease is exact, not marked."""
    parent, _ = _family(mark=None, entry_price=0.0042)
    assert parent.open_extractor_tranches()[0]["base_deployed"] == (pytest.approx(0.42))


def test_the_child_records_the_price_its_own_tick_already_fetched():
    """The mark exists because the tick keeps what it already had.

    This is what keeps the GUI thread free of network calls: the parent
    reads a number the child observed, and fetches nothing itself.
    """
    pos = _position(mark=None)
    assert pos.last_price_base_per_alt == 0.0
    # What the tick does, at the point the price is known good.
    pos.last_price_base_per_alt = 0.006
    pos.last_priced_at = 1234.0
    child = _child()
    child._positions["SOL/ETH"] = pos
    row = child.extractor_tranche_rows()[0]
    assert row["mark_price_base_per_alt"] == pytest.approx(0.006)
    assert row["marked_at"] == pytest.approx(1234.0)


def test_listing_performs_no_network_call():
    """No I/O on the Qt thread, enforced rather than asserted.

    Every coroutine in this application runs on the GUI thread, so a
    ticker fetch while building the tranche table would freeze the
    interface for the round trip, once per tranche, per repaint.
    """
    parent, child = _family()

    def _explode(*_a, **_kw):
        raise AssertionError("open_extractor_tranches touched the exchange")

    child.exchange = type(
        "_Ex", (), {"get_ticker": _explode, "fetch_ticker": _explode}
    )()
    rows = parent.open_extractor_tranches()
    assert len(rows) == 1


# ═════════════════════════════════════════════════════════════════════
# C. HAZARDS — the parent must not trade on an Extractor Tranche.
#
# One test per consumer named in the read phase, each asserting the
# exact expression that consumer evaluates.
# ═════════════════════════════════════════════════════════════════════
def test_hazard_the_listing_leaves_the_parents_own_books_untouched():
    """The umbrella proof. Every group-1 hazard reads one of these."""
    parent, _ = _family()
    fold_before = parent._fold_tranches
    lots_before = parent._main_lots
    snapshot = {
        "fold": list(parent._fold_tranches),
        "lots": list(parent._main_lots),
        "holdings": parent._current_holdings,
        "queue_usd": parent._fold_queue_usd,
        "target": parent._target_balance,
        "anchor": parent._anchor_target_balance,
    }
    parent.open_extractor_tranches()
    # Same objects, not merely equal ones: nothing was rebound either.
    assert parent._fold_tranches is fold_before
    assert parent._main_lots is lots_before
    assert list(parent._fold_tranches) == snapshot["fold"]
    assert list(parent._main_lots) == snapshot["lots"]
    assert parent._current_holdings == snapshot["holdings"]
    assert parent._fold_queue_usd == snapshot["queue_usd"]
    assert parent._target_balance == snapshot["target"]
    assert parent._anchor_target_balance == snapshot["anchor"]


def test_hazard_1_fold_gate_inputs_do_not_see_an_extractor_tranche():
    """`scrumming_bot.py:8609-8610` -> `gate_chain.TranchesQueuedGate`.

    THE CENTRAL HAZARD. One Extractor Tranche in `_fold_tranches` would
    make the FOLD gate report "queued" while the parent has zero real
    fold inventory, clearing the gate toward a buy it has no tranche to
    discharge.
    """
    parent, _ = _family()
    assert parent.open_extractor_tranches()  # a tranche exists
    # The two expressions the gate context is built from, verbatim.
    assert bool(parent._fold_tranches) is False
    assert len(parent._fold_tranches or []) == 0


def test_hazard_2_the_fold_buy_eligible_set_is_empty():
    """`scrumming_bot.py:9492-9495` — this IS the fold buy set."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    otd_factor = 0.98
    ticker_last = 1.0
    eligible = [
        t
        for t in parent._fold_tranches
        if ticker_last <= float(t.get("ref", 0)) * otd_factor
    ]
    assert eligible == []


def test_hazard_3_cycle_cap_packing_sees_no_extractor_usd():
    """`scrumming_bot.py:9548-9562` — an Extractor Tranche must not
    consume fold budget and defer a genuine tranche to a later cycle."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    packed = sum(float(t.get("usd", 0)) for t in parent._fold_tranches)
    assert packed == 0.0


def test_hazard_4_main_lots_gains_no_fabricated_cost_basis():
    """`scrumming_bot.py:9744-9750` — a rebuy inherits
    `initial_buy_price` from the tranche it discharges. A fabricated
    basis here would corrupt MEM-171 protection permanently."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    assert parent._main_lots == []


def test_hazard_6_wire_income_is_not_divided_into_an_extractor_tranche():
    """`scrumming_bot.py:2197-2220` — `apply_wire_income` credits every
    entry in `_fold_tranches`. Real Smart Wire money divided into an
    Extractor Tranche would become unreachable."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    # The divisor the real method uses.
    assert len(parent._fold_tranches) == 0


def test_hazard_7_manual_rebalance_sort_finds_no_extractor_tranche():
    """`scrumming_bot.py:11113-11160` — sorts on a bare `t["ref"]`,
    which an Extractor Tranche does not have, and would consume it."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    # The sort the real method performs. Raises KeyError if an entry
    # without `ref` ever reached this list.
    assert sorted(parent._fold_tranches, key=lambda t: t["ref"]) == []


def test_hazard_8_the_manual_fire_index_still_maps_to_fold_tranches():
    """`scrumming_bot.py:3196` with `bot_live_settings.py:1500-1544`.

    Manual fire is POSITION-indexed into `_fold_tranches`. If an
    Extractor Tranche shifted that mapping, the operator's Fire button
    would sell the wrong tranche.
    """
    parent, _ = _family()
    fold = [
        {
            "usd": 10.0,
            "units": 1.0,
            "ref": 100.0,
            "initial_buy_price": 90.0,
            "created_ts": 1.0,
        },
        {
            "usd": 20.0,
            "units": 2.0,
            "ref": 200.0,
            "initial_buy_price": 180.0,
            "created_ts": 2.0,
        },
    ]
    parent._fold_tranches = fold
    assert len(parent.open_extractor_tranches()) == 1
    # Each fold tranche still answers at its own index.
    for i, t in enumerate(fold):
        assert parent._fold_tranches.index(t) == i
        assert parent._fold_tranches[i] is t


def test_hazard_9_no_extractor_tranche_is_dropped_as_malformed():
    """`scrumming_bot.py:9425-9443` — the filter deletes anything
    failing `ref > 0` and counts it as corrupt. An Extractor Tranche has
    no `ref` and would be silently deleted and mislabelled."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    kept = [t for t in parent._fold_tranches if t.get("ref", 0) > 0]
    assert kept == list(parent._fold_tranches)
    assert (
        parent._tranches_malformed_dropped == 0
        if hasattr(parent, "_tranches_malformed_dropped")
        else True
    )
    # And the tranche is still listed after the filter would have run.
    assert len(parent.open_extractor_tranches()) == 1


def test_hazard_10_clearing_fold_tranches_does_not_destroy_the_record():
    """`scrumming_bot.py:11366-11418` and the detonation paths all do
    `self._fold_tranches = []`. None of them can reach a child's live
    position, so the parent's record of it survives."""
    parent, _ = _family()
    parent._fold_tranches = [
        {"usd": 5.0, "units": 1.0, "ref": 100.0, "initial_buy_price": 90.0}
    ]
    assert len(parent.open_extractor_tranches()) == 1
    parent._fold_tranches = []  # what the Clear button does
    assert len(parent.open_extractor_tranches()) == 1


def test_hazard_11_fold_queue_usd_sum_excludes_the_extractor_tranche():
    """`scrumming_bot.py:5016` and six sibling sites, several of which
    use a bare `t["usd"]` and would raise on an entry lacking it."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    assert sum(t["usd"] for t in parent._fold_tranches) == 0.0


def test_hazard_12_prospective_surplus_preview_is_unmoved():
    """`scrumming_bot.py:1709-1725` — feeds
    `_apply_fold_target_growth`. A phantom tranche inflates predicted
    surplus and widens a real growth decision."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    price = 100.0
    preview = sum(
        float(t["units"]) * (float(t["ref"]) - price)
        for t in sorted(parent._fold_tranches, key=lambda t: t["ref"])
    )
    assert preview == 0.0


def test_hazard_13_the_min_ref_diagnostic_finds_no_extractor_tranche():
    """`scrumming_bot.py:10052-10054` — a bare subscript inside the
    HOLD-FOLD diagnostic, which raises on a missing key."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    assert parent._fold_tranches == []  # min() is never reached


def test_hazard_17_current_holdings_excludes_the_leased_units():
    """`scrumming_bot.py:6497` — THE decision itself.

    `current_value = _current_holdings x price x quote_to_usd`, and the
    delta against Target Balance is what makes the bot SCRUM or FOLD.
    Since v3.23.43 `_current_holdings` derives from `_main_lots` alone,
    so putting an Extractor Tranche in `_main_lots` would make the
    parent count units it does not hold AND SELL THEM. This is the
    precise failure item 4 had to avoid.
    """
    parent, _ = _family(entry_price=0.005)
    parent._main_lots = [{"units": 2.0, "initial_buy_price": 3000.0}]
    parent._current_holdings = 2.0
    assert len(parent.open_extractor_tranches()) == 1
    # The derivation the bot performs, run again after listing.
    assert sum(float(lot["units"]) for lot in parent._main_lots) == 2.0
    assert parent._current_holdings == 2.0
    # The leased 0.5 ETH is NOT in there.
    assert parent._current_holdings != pytest.approx(2.5)


def test_hazard_18_capital_reservation_total_holdings_not_inflated():
    """`scrumming_bot.py:12137-12141` — the sell allowance is computed
    against `total_holdings=self._current_holdings`. Inflating it would
    widen the parent's own sell allowance against the very asset the
    child reserved, and the check fails open, so the mistake would not
    be caught."""
    parent, _ = _family(entry_price=0.005)
    parent._main_lots = [{"units": 2.0, "initial_buy_price": 3000.0}]
    parent._current_holdings = 2.0
    parent.open_extractor_tranches()
    assert float(parent._current_holdings or 0) == 2.0


def test_hazard_19_the_anchor_and_target_balance_are_untouched():
    """`scrumming_bot.py:1601-1605` and `:4481` — the anchor sets both
    the per-cycle Growth Rate Cap and the Smart Ceiling. Item 1 already
    lifts it when a tranche RETURNS; item 4 must not lift anything on
    the open side or the same money is counted twice."""
    parent, _ = _family()
    parent.open_extractor_tranches()
    assert parent._target_balance == 1000.0
    assert parent._anchor_target_balance == 1000.0


def test_hazard_no_money_moves_and_no_order_is_placed():
    """Item 4 is a record. If it ever needs an exchange, that is a
    different item."""
    parent, child = _family()
    calls = []
    for name in ("create_order", "place_order", "market_sell", "market_buy"):
        setattr(parent, name, lambda *a, _n=name, **kw: calls.append(_n))
    parent.open_extractor_tranches()
    assert calls == []
    assert child._chunk_free_base == 1.0


# ═════════════════════════════════════════════════════════════════════
# D. BACKWARD COMPATIBILITY WITH THE OPERATOR'S SAVED STATE
# ═════════════════════════════════════════════════════════════════════
def test_a_scrumming_state_without_the_new_field_loads_unchanged():
    """Item 4 adds NO key to the Scrumming Bot's saved state, because
    the listing is computed rather than stored. So the operator's file
    loads exactly as it did before."""
    parent = _parent()
    state = {
        "main_lots": [{"units": 1.5, "initial_buy_price": 2000.0}],
        "fold_tranches": [
            {"usd": 10.0, "units": 0.1, "ref": 2100.0, "initial_buy_price": 2000.0}
        ],
        "tranches_created_lifetime": 7,
        "tranches_closed_lifetime": 4,
    }
    assert "extractor_tranches" not in state
    parent.import_scrumming_state(dict(state))
    assert len(parent._main_lots) == 1
    assert parent._main_lots[0]["units"] == pytest.approx(1.5)
    assert len(parent._fold_tranches) == 1
    assert parent._fold_tranches[0]["ref"] == pytest.approx(2100.0)
    assert parent._tranches_created_lifetime == 7
    assert parent._tranches_closed_lifetime == 4


def test_an_empty_scrumming_state_still_loads():
    parent = _parent()
    parent.import_scrumming_state({})
    assert parent._fold_tranches == []
    assert parent._main_lots == []


def test_an_extractor_position_saved_before_item_4_loads_with_no_mark():
    """The two mark fields are new on a saved position. A file written
    before item 4 has neither, and the honest default is "never
    priced" — not a fabricated price of zero treated as real."""
    child = _child()
    legacy = {
        "positions": [
            {
                "pair": "SOL/ETH",
                "state": "in_flight",
                "artillery_size_base": 0.5,
                "artillery_size_usd_at_entry": 1500.0,
                "alt_units": 100.0,
                "entry_price_base_per_alt": 0.005,
                "avg_buy_price_base_per_alt": 0.005,
                "cost_basis_base": 0.5,
                "compounding_tier": 1,
                "corrections_fired": 0,
                "last_correction_ts": 0.0,
                "opened_at": 1000.0,
            }
        ],
    }
    assert "last_price_base_per_alt" not in legacy["positions"][0]
    child.import_state(legacy)
    pos = child._positions["SOL/ETH"]
    assert pos.alt_units == pytest.approx(100.0)
    assert pos.cost_basis_base == pytest.approx(0.5)
    assert pos.last_price_base_per_alt == 0.0
    row = child.extractor_tranche_rows()[0]
    assert row["mark_value_usd"] is None
    assert row["base_deployed"] == pytest.approx(0.5)


def test_an_extractor_state_round_trips_the_mark():
    child = _child()
    child._positions["SOL/ETH"] = _position(mark=0.006)
    restored = _child()
    restored.import_state(child.export_state())
    pos = restored._positions["SOL/ETH"]
    assert pos.last_price_base_per_alt == pytest.approx(0.006)
    assert pos.last_priced_at == pytest.approx(1060.0)


def test_control_a_round_trip_without_the_mark_key_yields_no_mark():
    """The control for the round-trip test.

    If `import_state` invented a mark, the test above would pass while
    the persistence was broken. Stripping the key must produce a
    position that reports no mark.
    """
    child = _child()
    child._positions["SOL/ETH"] = _position(mark=0.006)
    state = child.export_state()
    for p in state["positions"]:
        p.pop("last_price_base_per_alt")
        p.pop("last_priced_at")
    restored = _child()
    restored.import_state(state)
    assert restored._positions["SOL/ETH"].last_price_base_per_alt == 0.0


# ═════════════════════════════════════════════════════════════════════
# E. IDENTITY — item 5 hangs a per-row control on this.
# ═════════════════════════════════════════════════════════════════════
def test_the_tranche_id_survives_a_resort():
    parent = _parent()
    c1, c2 = _child(bot_id="ext-a"), _child(bot_id="ext-b")
    c1._positions["SOL/ETH"] = _position(mark=0.006)
    c2._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", mark=0.002)
    _wire(parent, c1, c2)
    before = {r["tranche_id"]: r["pair"] for r in parent.open_extractor_tranches()}
    rows = parent.open_extractor_tranches()
    rows.sort(key=lambda r: -float(r["alt_units"]))
    rows.sort(key=lambda r: r["pair"])
    after = {r["tranche_id"]: r["pair"] for r in rows}
    assert before == after


def test_the_tranche_id_survives_another_tranche_closing():
    parent = _parent()
    keeper, goer = _child(bot_id="ext-keep"), _child(bot_id="ext-go")
    keeper._positions["SOL/ETH"] = _position(mark=0.006)
    goer._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", mark=0.002)
    _wire(parent, keeper, goer)
    rows = parent.open_extractor_tranches()
    keeper_id = next(r["tranche_id"] for r in rows if r["child_bot_id"] == "ext-keep")
    # The other position closes.
    goer._positions.clear()
    rows_after = parent.open_extractor_tranches()
    assert [r["tranche_id"] for r in rows_after] == [keeper_id]


def test_a_reopened_position_does_not_inherit_the_old_identity():
    """`opened_at` is in the id precisely so a closed-and-reopened
    position cannot pick up whatever item 5 attached to its
    predecessor."""
    child = _child()
    child._positions["SOL/ETH"] = _position(mark=0.006, opened_at=1000.0)
    first = child.extractor_tranche_rows()[0]["tranche_id"]
    child._positions["SOL/ETH"] = _position(mark=0.006, opened_at=5000.0)
    second = child.extractor_tranche_rows()[0]["tranche_id"]
    assert first != second


def test_two_children_on_the_same_pair_get_different_identities():
    parent = _parent()
    c1, c2 = _child(bot_id="ext-a"), _child(bot_id="ext-b")
    c1._positions["SOL/ETH"] = _position(mark=0.006)
    c2._positions["SOL/ETH"] = _position(mark=0.006)
    _wire(parent, c1, c2)
    ids = [r["tranche_id"] for r in parent.open_extractor_tranches()]
    assert len(set(ids)) == 2


def test_the_identity_can_carry_a_per_tranche_field_for_item_5():
    """Item 5 adds a per-tranche Arbiter toggle. It is NOT built here.

    What is proven here is only that this structure can carry one: a
    side-table keyed by `tranche_id` still resolves to the right row
    after another tranche closes, which a row index would not.
    """
    parent = _parent()
    c1, c2 = _child(bot_id="ext-a"), _child(bot_id="ext-b")
    c1._positions["SOL/ETH"] = _position(mark=0.006)
    c2._positions["AVAX/ETH"] = _position(pair="AVAX/ETH", mark=0.002)
    _wire(parent, c1, c2)
    rows = parent.open_extractor_tranches()
    prefs = {rows[0]["tranche_id"]: {"arbiter": "sibling"}}
    marked_pair = rows[0]["pair"]
    # The OTHER tranche closes; a row index would now be wrong.
    other = next(r for r in rows if r["pair"] != marked_pair)
    (c1 if other["child_bot_id"] == "ext-a" else c2)._positions.clear()
    remaining = parent.open_extractor_tranches()
    assert len(remaining) == 1
    assert prefs.get(remaining[0]["tranche_id"]) == {"arbiter": "sibling"}
    assert remaining[0]["pair"] == marked_pair


# ═════════════════════════════════════════════════════════════════════
# F. THE COLOUR — measured, not asserted.
# ═════════════════════════════════════════════════════════════════════
def _srgb_to_linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_the_red_row_passes_wcag_aa_for_normal_text():
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_FG_HEX,
    )

    ratio = _contrast(EXTRACTOR_TRANCHE_FG_HEX, EXTRACTOR_TRANCHE_BG_HEX)
    assert ratio >= 4.5, f"white on {EXTRACTOR_TRANCHE_BG_HEX} is {ratio:.2f}:1"
    assert ratio == pytest.approx(6.54, abs=0.05)


def test_control_the_contrast_calculator_rejects_a_known_bad_pair():
    """The control for the measurement above.

    A calculator that returned a large number for everything would pass
    the test above while measuring nothing. The theme's own
    `accent_danger` (#ff5577) with white is the pair that was REJECTED
    when the colour was chosen; it must still measure as failing.
    """
    assert _contrast("#ffffff", "#ff5577") < 4.5
    assert _contrast("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert _contrast("#000000", "#ffffff") == pytest.approx(21.0)


def test_the_cell_texts_never_mix_denominations():
    """Price columns belong to the parent's asset. An Extractor
    Tranche's prices are quoted against a different pair, so those
    columns print an em dash rather than one asset's number under
    another asset's heading."""
    from src.gui.bot_live_settings import (
        _compose_extractor_tranche_cells,
    )

    parent, _ = _family(mark=0.006, alt_units=100.0)
    row = parent.open_extractor_tranches()[0]
    cells = _compose_extractor_tranche_cells(row, 1600.0)
    assert len(cells) == 10
    assert cells[0] == "EXT"  # never a fold index
    assert cells[2] == "0.500000"  # base on lease
    assert cells[3] == "$1,800.0000"  # marked value
    assert cells[4] == "—"  # Sell ref $
    assert cells[5] == "—"  # Original cost $
    assert cells[6] == "—"  # Min rebuy $
    assert cells[8] == "extractor SOL/ETH"
    assert cells[9] == "—"  # Fire


def test_an_unpriced_row_shows_a_dash_not_a_dollar_figure():
    from src.gui.bot_live_settings import (
        _compose_extractor_tranche_cells,
    )

    parent, _ = _family(mark=None)
    row = parent.open_extractor_tranches()[0]
    cells = _compose_extractor_tranche_cells(row, 1600.0)
    assert cells[3] == "—"


# ── The rendered widget ──────────────────────────────────────────────
pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def _tab():
    """Build the REAL Open Tranches tab with one row of each kind.

    `QDialog.__init__` is called directly rather than
    `BotLiveSettingsDialog.__init__`, so the object is a genuine dialog
    carrying every real method, without the full construction path that
    wants a live bot, an exchange and a bus. The tab itself is built by
    the production code under test.
    """
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QTableWidget,
    )
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])

    parent, _ = _family(mark=0.006, alt_units=100.0)
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

    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = parent
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    tables = widget.findChildren(QTableWidget)
    assert tables, "the tab rendered no table"
    # YIELD, not return. The tab widget has no parent, so returning
    # would drop the last reference to it and Qt would destroy the
    # whole tree — including this table — before the test touched it.
    # Yielding keeps this frame, and therefore `dlg` and `widget`,
    # alive for the duration of the test.
    yield tables[0]


def test_the_table_holds_one_fold_row_and_one_extractor_row(_tab):
    assert _tab.rowCount() == 2


def test_the_extractor_row_is_red_with_white_text_in_every_column(_tab):
    """The operator's spec, read back off the widget itself.

    Per-cell painting means a missed column leaves the row half red, so
    every one of the ten is checked — column 9 especially, which holds a
    widget on a fold row and would otherwise show a blue Fire button on
    a red row.
    """
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_FG_HEX,
    )

    for col in range(_tab.columnCount()):
        cell = _tab.item(1, col)
        assert cell is not None, f"column {col} has no item to paint"
        assert cell.background().color().name() == (
            EXTRACTOR_TRANCHE_BG_HEX
        ), f"column {col} is not red"
        assert cell.foreground().color().name() == (
            EXTRACTOR_TRANCHE_FG_HEX
        ), f"column {col} is not white"
    assert EXTRACTOR_TRANCHE_BG_HEX == "#b3261e"
    assert EXTRACTOR_TRANCHE_FG_HEX == "#ffffff"


def test_the_ordinary_tranche_row_is_not_repainted(_tab):
    """A fold row is BLUE, never the Extractor red.

    RESTATED 2026-08-11, and made stronger. This test used to say fold
    rows "keep their default background" and checked only that row 0
    was NOT red. That description retired when the operator asked for
    the blue to be painted: before, "blue" was only the per-cell
    `#00ccff` Source foreground and the Fire button's stylesheet, and
    the row background was whatever the theme's alternating brush
    supplied.

    The invariant the test exists for is unchanged — no red may leak
    onto a fold row, and the Source colour and Fire button must
    survive. It is now asserted POSITIVELY: the row must equal the
    fold blue, rather than merely differ from the red. "Not red" was
    satisfied by an unpainted row, so it could not have caught the
    blue failing to paint.
    """
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        FOLD_TRANCHE_BG_HEX,
    )

    source_cell = _tab.item(0, 8)
    assert source_cell.text() == "manual fire"
    assert source_cell.foreground().color().name() == "#00ccff"

    fire_btn = _tab.cellWidget(0, 9)
    assert fire_btn is not None, "the fold row lost its Fire button"
    assert "#00ccff" in fire_btn.styleSheet()

    for col in range(_tab.columnCount()):
        cell = _tab.item(0, col)
        assert cell is not None, f"column {col} has no item to paint"
        assert cell.background().color().name() != EXTRACTOR_TRANCHE_BG_HEX
        assert cell.background().color().name() == FOLD_TRANCHE_BG_HEX


def test_the_extractor_row_has_no_fire_button(_tab):
    """`manual_fire_tranche` indexes `_fold_tranches`. A button on this
    row would dispatch a real fold-back against an unrelated tranche."""
    assert _tab.cellWidget(1, 9) is None
    assert _tab.item(1, 9).text() == "—"


def test_the_fold_row_comes_first_so_its_index_still_maps(_tab):
    """Row number must equal `_fold_tranches` index for the Fire button
    to resolve its target correctly."""
    assert _tab.item(0, 0).text() == "1"
    assert _tab.item(1, 0).text() == "EXT"
