"""The fold path's answer must not depend on ladder ORDER -- at BOTH sites.

TWO SITES, ONE ROOT CAUSE, AND THEY LAND TOGETHER
=================================================
A value sets an ordering or a threshold ONLY IF IT IS A FINITE NUMBER.
The fold money path broke that rule twice, and the second half of this
file exists because fixing only the first would have been a net
worsening.

  SITE A, the rebuy-distance GATE. ``max`` over ``ref * factor``. It
    decides WHETHER the fold fires. Covered from "THE DEFECT" below.

  SITE B, the discharge SORT inside ``_preview_fold_growth``. It decides
    the AMOUNT sent to the exchange. Covered from "SITE B" onward.

MEASURED ACROSS THREE TREES, exhaustive ordered tuples over
{nan, inf, good, zero} at sizes 2, 3 and 4, grouped by sorted multiset,
at the operator's own config (interval 5.0, fee 1.6, growth cap 1.0):

    tree                       autonomous     manual_button
                               (130 buckets)  (65 buckets)
    neither site fixed          50 split       22 split
    SITE A ONLY                 30 split       22 split
    both sites fixed             0 split        0 split

The middle row is why this is one unit. With only the gate repaired,
THIRTY autonomous buckets still gave two answers, and every one of them
differed on the AMOUNT alone -- 17.4976 units against 18.0 for the same
ladder at the same price. The gate's repair makes MORE folds fire, and
each extra fire was then sized by a sort whose key could receive ``nan``.
159 of the 195 buckets held more than one ordering, so the zero in the
last row is not the arithmetic of single-ordering buckets.

THE DEFECT
==========
The gate computed its threshold with a bare ``max`` over a generator::

    _best_rebuy = max(
        float(t.get("ref", 0)) * _fold_factor
        for t in self._fold_tranches)

``max`` keeps whichever operand it saw FIRST whenever the comparison is
False, and EVERY comparison against ``nan`` is False. So ``max``
DISCARDS a ``nan`` it meets late and KEEPS one it meets first. Measured
on the shipped code, one ``nan`` ref beside one plainly eligible
``ref=1.0`` at price 0.5::

    [nan, good]  ->  AUTONOMOUS FIRE REFUSED, "best rebuy nan"
    [good, nan]  ->  PLACED BUY

Same ladder, same price, opposite answer, decided by list position.
Driven over every permutation of four ladder contents, 4 of 7 contents
gave more than one answer; a 4-row ladder holding one ``nan`` refused on
6 permutations and bought on 18.

``+inf`` is the same hole facing the other way, and it is the worse
one. ``inf`` WINS every comparison, ``price <= inf`` is True for every
price, and the gate is then fully DISABLED -- measured: a ladder holding
only an ``inf`` ref placed a buy at a price no tranche could justify.

THE TREATMENT: SKIP THE UNREADABLE ROW, AND SAY SO
==================================================
A row sets the threshold only if its threshold is a finite number.

This is NOT a new policy. It is the policy the gate already had for
every other malformed ref, and the shipped tests already pin it: a
missing key reads 0.0 through the ``get`` default, and 0.0 and a
negative both LOSE the ``max``. All three therefore already failed to
set the threshold while the gate answered on the readable rows --
``test_a_ladder_of_only_malformed_refs_refuses`` and the "a zero ref and
a negative ref sit beside a good one" row of ``IN_SPEC`` are that
contract. ``nan`` was the single value that escaped, because it is the
single value ``max`` cannot order.

WHY NOT PURGE, WHICH IS WHAT THE TICK PATH DOES
===============================================
The tick path's guard DELETES malformed rows and bumps
``_tranches_malformed_dropped``. It can, because it runs after its fold
has committed to acting. This site can ``return`` WITHOUT firing, so a
purge here would destroy ladder rows on a fire that never happened --
and ``test_an_autonomous_fold_is_refused_when_no_tranche_is_eligible``
already asserts "the ladder was disturbed by a fire that never
happened". ``manual_button`` skips the whole block, so a purge would
also make ladder CONTENT depend on which caller fired. Mutation is a
second verb and it is not this one's.

WHY NOT REFUSE THE WHOLE FIRE ON ANY nan
========================================
Because the tick path, on the same data, FIRES: it drops the ``nan``
row and its per-tranche filter then finds the good ref eligible. The
gate's stated purpose is to ask "the same question" that path asks, and
``test_the_gate_agrees_with_the_tick_path_on_every_config`` pins the
agreement. Refusing here would make the two fold paths disagree about
the same tranche on the same tick, which is the drift ``otd_math`` was
extracted to end. One corrupt row would also disable autonomous folding
for a whole bot; the operator's live state holds one ladder of 150.

WHAT A FAILURE OF EACH TEST WOULD MEAN is stated in its own docstring.
No test here plants a defect to watch it go red: the reds that shaped
this file were the real ones the change produced while it was being
written, and they are recorded in the unit's report.
"""
from __future__ import annotations

import asyncio
import itertools
import math

import pytest

from src.trading.otd_math import fold_rebuy_factor
from src.trading.scrumming_bot import ScrummingBot

AUTONOMOUS = ("wire_stack", "max_cartridge")
NAN = float("nan")
INF = float("inf")


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_folded_usd = 0.0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


class _Config:
    def __init__(self, interval=1.0, fee=0.6):
        self.symbol = "CHIP/USD"
        self.target_asset = "CHIP"
        self.exchange_id = "coinbase"
        self.scrumming_interval_pct = interval
        self.trading_fee_pct = fee
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True
        self.scrum_fold_pct = 100


class _Order:
    id = "order-nl"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last):
        self.last = last


def _bot(tranches, *, holdings=50.0, target=None, price=0.5,
         interval=1.0, fee=0.6):
    """A bot that runs the REAL ``_execute_manual_rebalance``.

    Only the outward edges are stubbed -- exchange, emitters, settled
    fill. The gate, the sizing preview and the discharge loop are the
    shipping code.

    ``target`` DEFAULTS FROM THE PRICE, and that is load-bearing. The
    method only reaches the FOLD branch when the position is BELOW
    target; above it, it SELLS and the gate never runs at all. A fixed
    target of 100.0 silently routed every high-price row to the scrum
    side, where "an order was placed" is true and means nothing about
    this gate. Scaling the target with the price keeps every row on the
    branch it claims to test.
    """
    if target is None:
        target = holdings * price * 3.0 + 100.0
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "nl-bot"
    bot.seen = {"placed": None}
    bot._bus = _Bus()
    bot.config = _Config(interval=interval, fee=fee)
    bot.stats = _Stats()
    bot._fold_tranches = [dict(t) for t in tranches]
    bot._main_lots = [{"units": holdings, "initial_buy_price": price}]
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._fold_queue_usd = 0.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._fold_accumulator = 0.0
    bot._target_grow_last_side = None
    bot._tranches_closed_lifetime = 0
    bot._tranches_created_lifetime = 0
    bot._tranches_malformed_dropped = 0
    bot._pending_wire_credits = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.seen["placed"] = dict(kwargs)
        return _Order()

    async def _settled(order, symbol_, requested, tick_price):
        del order, symbol_, tick_price
        return requested, price, True

    async def _balance(currency):
        free = holdings if currency == "CHIP" else 1_000_000.0
        return type("B", (), {"total": free, "free": free,
                              "absent": False})()

    def _ignore(*args, **kwargs):
        del args, kwargs

    def _zero(*args, **kwargs):
        del args, kwargs
        return 0.0

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._emit_voting_panel_snapshot_at_fire = _ignore
    bot._emit_gate_decision_at_fire = _ignore
    bot._reset_opposing_hysteresis_after_fill = _ignore
    bot._route_scrum_proceeds_via_wires = _zero
    bot.note_scrum_retention_usd = _ignore
    return bot


def _decision(tranches, price=0.5, intent="max_cartridge", **kw):
    """The GATE's answer alone: ALLOWED, REFUSED, SCRUMMED, or a raise.

    Read separately from the order AMOUNT on purpose, so that a failure
    in this half names the GATE. The amount is set by
    ``_preview_fold_growth`` -- a different method with a different verb
    -- and it carried an order dependence of its own. That is SITE B,
    and it is closed too: ``_answer`` further down reads the decision
    and the amount TOGETHER, and the sweep that uses it is what proves
    the pair. Collapsing the two here would attribute site B's defect to
    this gate.

    (This docstring used to end "measured and deliberately did not fix".
    That was true for one unit and stopped being true when site B
    landed; it is corrected here rather than left to mislead.)

    A SELL RETURNS "SCRUMMED", NEVER "ALLOWED". The first version of
    this helper reported any placed order as ALLOWED, so a scenario that
    took the SCRUM branch -- where this gate does not run -- read as the
    gate permitting a fold. Three tests passed their assertion while
    measuring the sell side. Naming the side is what makes a green here
    mean the fold was allowed.
    """
    bot = _bot(tranches, price=price, **kw)
    try:
        asyncio.run(bot._execute_manual_rebalance(_Ticker(price), intent))
    except Exception as exc:
        return f"RAISED {type(exc).__name__}"
    if bot.seen["placed"] is None:
        refused = [m for m in bot._bus.messages
                   if "AUTONOMOUS FIRE REFUSED (opposing distance" in m]
        return "REFUSED" if refused else "NO-ORDER-NO-REFUSAL"
    side = getattr(bot.seen["placed"].get("side"), "value", "?")
    return "ALLOWED" if side == "buy" else "SCRUMMED"


def _row(ref, units=100.0, present=True):
    t = {"usd": 10.0, "units": units, "initial_buy_price": 0.8}
    if present:
        t["ref"] = ref
    return t


def _ladder(*refs, units=100.0):
    return [_row(r, units=units) for r in refs]


# ── a. ORDER INDEPENDENCE, over every permutation ────────────────────

LADDERS = [
    ("3-row, no nan", (1.0, 0.9, 0.8)),
    ("3-row, one nan", (NAN, 1.0, 0.9)),
    ("3-row, two nans", (NAN, NAN, 1.0)),
    ("3-row, nan beside inf", (NAN, INF, 1.0)),
    ("3-row, only unreadable", (NAN, INF, float("-inf"))),
    ("4-row, no nan", (1.0, 0.9, 0.8, 0.7)),
    ("4-row, one nan", (NAN, 1.0, 0.9, 0.8)),
    ("4-row, two nans and an inf", (NAN, NAN, INF, 1.0)),
]


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize("label, refs", LADDERS, ids=[r[0] for r in LADDERS])
def test_the_gate_gives_one_answer_per_ladder_content(label, refs, intent):
    """THE WHOLE UNIT, stated as one property.

    Every permutation of the same ladder CONTENT must produce the same
    gate answer. The answer set is required to have exactly one member.

    IF THIS FAILS: the gate's decision is being made by list position
    rather than by the ladder, on a path where every other gate is
    bypassed by design and the next step buys at market. Two operators
    with identical ladders would get opposite answers, and neither
    could tell why.
    """
    answers = {}
    for perm in itertools.permutations(range(len(refs))):
        ladder = _ladder(*[refs[i] for i in perm])
        answers.setdefault(_decision(ladder, intent=intent), []).append(perm)

    assert len(answers) == 1, (
        f"{label} / {intent}: {len(answers)} different answers over "
        f"{math.factorial(len(refs))} permutations of ONE ladder content — "
        + "; ".join(f"{a} from {len(p)} perm(s) e.g. {p[0]}"
                    for a, p in answers.items()))


@pytest.mark.parametrize("label, refs", LADDERS, ids=[r[0] for r in LADDERS])
def test_the_permutation_sweep_actually_varies_the_ladder(label, refs):
    """CONTROL for the sweep above, at the surface it reads.

    A sweep that handed the gate the same list every time would report
    one answer for every content and prove nothing. This asserts the
    permutations really are distinct orderings of the refs.

    IF THIS FAILS: the order-independence test is green because nothing
    was reordered, which is an oracle false negative — the exact shape
    the repo's two-sided-control rule exists to catch.
    """
    seen = {tuple(
        "nan" if r != r else r for r in [refs[i] for i in perm])
        for perm in itertools.permutations(range(len(refs)))}
    distinct_values = len({"nan" if r != r else r for r in refs})
    if distinct_values > 1:
        assert len(seen) > 1, (
            f"{label}: the sweep produced one ordering only")


# ── b. THE IN-SPEC FOLD IS UNTOUCHED ─────────────────────────────────
#
# The whole-observable comparison against a byte-provable pre-change
# twin lives in test_autonomous_fold_price_gate.py and covers 12
# scenarios by 3 intents. It is not restated here. What IS asserted
# here is the arithmetic claim this change rests on: where every ref is
# finite, the new filtered threshold equals the old bare-max formula
# EXACTLY, so no all-finite ladder can have moved.

FINITE_LADDERS = [
    (1.0,), (1.0, 0.9), (2.0, 0.1), (0.0, 1.0), (-1.0, 1.0),
    (0.0, -1.0), (1.0, 1.0, 1.0), (5.0, 0.2, 0.9, 3.3),
    (1e-9, 1.0), (1e9, 1.0),
]


@pytest.mark.parametrize("refs", FINITE_LADDERS, ids=str)
def test_an_all_finite_ladder_keeps_the_old_threshold_to_the_bit(refs):
    """THE CONTROL THAT PROTECTS TODAY'S FOLDS.

    For a ladder whose refs are all finite, the filter removes nothing,
    so the threshold must be bit-identical to ``max(ref * factor)`` --
    the expression this change replaced. The boundary is probed from
    both sides: exactly ON it must fire, one float above must refuse.

    IF THIS FAILS: an in-spec fold that fires on the operator's live
    bots today would fire differently or stop firing. Too strict is the
    more dangerous direction — the position never returns to centre and
    the ladder is stranded with money queued and no path to spend it.
    """
    factor = fold_rebuy_factor(1.0, 0.6)
    edge = max(ref * factor for ref in refs)
    if edge <= 0:
        pytest.skip("no positive threshold; covered by the malformed rows")

    assert _decision(_ladder(*refs), price=edge) == "ALLOWED", (
        f"price exactly ON the old formula's threshold {edge!r} was "
        f"refused; the rule is `<=` and this ladder has not moved")
    above = math.nextafter(edge, math.inf)
    assert _decision(_ladder(*refs), price=above) == "REFUSED", (
        f"one float above the old formula's threshold {edge!r} was still "
        f"admitted; the boundary moved")


def test_the_factor_is_always_finite_so_only_the_ref_needs_testing():
    """The assumption the filter rests on, checked instead of assumed.

    The gate tests the finiteness of ``ref * factor``. That is only a
    test OF THE REF if the factor is always finite. ``otd_math`` clamps
    it into [0.5, 1.0]; this drives the clamp with the hostile inputs
    rather than trusting the docstring, because a docstring that states
    a property is a claim and no gate reads prose.

    IF THIS FAILS: a config value could make every threshold non-finite,
    every row would read as unreadable, and the bot would refuse every
    autonomous fold while the log blamed the ladder.
    """
    for interval in (0.0, 1.0, 60.0, NAN, INF, float("-inf")):
        for fee in (0.0, 0.6, NAN, INF):
            factor = fold_rebuy_factor(interval, fee)
            assert math.isfinite(factor), (interval, fee, factor)
            assert 0.5 <= factor <= 1.0, (interval, fee, factor)


# ── c. THE CORRUPT CASE IS VISIBLE ───────────────────────────────────


def _messages(tranches, price=0.5, intent="max_cartridge"):
    bot = _bot(tranches, price=price)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), intent))
    return bot._bus.messages, bot


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_a_skipped_row_is_reported_on_the_fire_it_allows(intent):
    """SKIPPING MUST NOT BE SILENT.

    Refusing is loud by construction -- a fold stops and the operator
    notices. Firing on a partly readable ladder is the QUIET case, and
    it is the one that needs saying, because the answer was computed
    from fewer tranches than he has.

    IF THIS FAILS: the bot trades on a ladder it has silently discarded
    part of, and nothing in the log says which part or how much. That is
    the "silently dropped an unreadable sibling" failure the island
    ledger already records once.
    """
    msgs, bot = _messages(_ladder(NAN, 1.0, 0.9), intent=intent)
    assert bot.seen["placed"] is not None, "this row is meant to fire"
    line = [m for m in msgs if "FOLD REF UNREADABLE" in m]
    assert len(line) == 1, msgs
    for fragment in ("1 of 3", "not a finite number",
                     "2 readable", "NOT altered"):
        assert fragment in line[0], f"{fragment!r} missing from {line[0]!r}"


def test_the_refusal_says_when_the_ladder_was_unreadable():
    """A refusal must not blame the price for a corrupt ladder.

    With no readable row the threshold is 0.0, and the refusal's "the
    highest rebuy any of them allows is $0.00000000" would otherwise be
    a true sentence that tells the operator the wrong thing.

    IF THIS FAILS: the operator reads a distance refusal, waits for the
    price to fall, and it never helps, because the real cause was a
    corrupt ref he was never told about.
    """
    msgs, bot = _messages(_ladder(NAN, INF))
    assert bot.seen["placed"] is None
    refusal = [m for m in msgs
               if "AUTONOMOUS FIRE REFUSED (opposing distance)" in m]
    assert len(refusal) == 1, msgs
    assert "2 of the 2 queued tranche(s)" in refusal[0]
    assert "0 readable tranche(s)" in refusal[0]


def test_a_clean_ladder_says_nothing_extra():
    """CONTROL for both visibility tests.

    IF THIS FAILS: the unreadable notice fires on healthy ladders, which
    would make it noise, and noise hides the signals already present.
    """
    msgs, bot = _messages(_ladder(1.0, 0.9, 0.8))
    assert bot.seen["placed"] is not None
    assert [m for m in msgs if "FOLD REF UNREADABLE" in m] == []


def test_a_refused_fire_leaves_every_unreadable_row_in_the_ladder():
    """THE VERB IS REFUSE, NOT PURGE -- asserted, not just documented.

    Read on the REFUSED path, because that is the only place the claim
    is clean. When the fire proceeds, the discharge loop consumes
    tranches by design and a row count would then be measuring the
    discharge, not the gate. The first version of this test asserted the
    count on a FIRING ladder and went red for exactly that reason.

    IF THIS FAILS: the gate has grown a second verb. A tranche would be
    destroyed by a fire that never happened, and because
    ``manual_button`` skips this block entirely, the ladder's content
    would start depending on which caller fired.
    """
    for refs in ((NAN, INF), (NAN,), (NAN, NAN, float("-inf"))):
        before = _ladder(*refs)
        bot = _bot(before, price=0.5)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(0.5), "wire_stack"))
        assert bot.seen["placed"] is None, f"{refs}: meant to be refused"
        after = bot._fold_tranches
        assert len(after) == len(before), (
            f"{refs}: the ladder went from {len(before)} rows to "
            f"{len(after)} on a fire that never happened")
        assert sum(1 for t in after if t["ref"] != t["ref"]) == sum(
            1 for r in refs if r != r), f"{refs}: a nan row was removed"
        assert bot._tranches_malformed_dropped == 0, (
            "the gate bumped the tick path's malformed-drop counter")


def test_an_allowed_fire_does_not_purge_for_unreadability_either():
    """The same claim on the FIRING path, read where it is measurable.

    The discharge loop legitimately spends tranches, so a bare row count
    cannot be asserted here -- a first draft used 100-unit rows, the
    fill was 300 units, the loop consumed all three by design and the
    test went red for the wrong reason.

    THE LADDER IS THEREFORE SIZED SO THE FILL CANNOT EMPTY IT. At 10,000
    units a row against a fill of ~300, the loop touches one row and
    every row survives, so "the nan row is still there" is a claim about
    purging rather than about arithmetic. The malformed-drop counter is
    asserted beside it: it is the tick path's purge signal, and this
    gate must never touch it.

    IF THIS FAILS: this site has started purging, and the operator's
    malformed-drop total would count rows no tick ever dropped.
    """
    bot = _bot(_ladder(NAN, 1.0, 0.9, units=10_000.0), price=0.5)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(0.5), "wire_stack"))
    assert bot.seen["placed"] is not None, "this row is meant to fire"
    assert bot._tranches_malformed_dropped == 0
    assert len(bot._fold_tranches) == 3, (
        f"a row was removed: {bot._fold_tranches}")
    assert any(t["ref"] != t["ref"] for t in bot._fold_tranches), (
        "the nan row vanished although the fill was far too small to "
        "consume it, so it was purged rather than spent")


# ── d. THE FULL VALUE DOMAIN ON ref, EACH IN BOTH POSITIONS ──────────
#
# The OBSERVED answer, recorded by driving the real method, never
# predicted. Two rows disagree with what a reader might expect and are
# called out in the docstring below rather than smoothed over.

GOOD = 1.0

DOMAIN = [
    ("nan", _row(NAN), "ALLOWED"),
    ("+inf", _row(INF), "ALLOWED"),
    ("-inf", _row(float("-inf")), "ALLOWED"),
    ("int zero", _row(0), "ALLOWED"),
    ("float zero", _row(0.0), "ALLOWED"),
    ("negative", _row(-5.0), "ALLOWED"),
    ("huge int 10**400", _row(10 ** 400), "REFUSED"),
    ("None", _row(None), "REFUSED"),
    ("numeric string", _row("2.0"), "RAISED TypeError"),
    ("bool True", _row(True), "ALLOWED"),
    ("bool False", _row(False), "ALLOWED"),
    ("missing key", _row(None, present=False), "RAISED KeyError"),
]


@pytest.mark.parametrize(
    "label, bad, expected", DOMAIN, ids=[r[0] for r in DOMAIN])
def test_the_ref_domain_answers_the_same_in_either_position(
        label, bad, expected):
    """THE CLOSED VALUE DOMAIN, read at both positions.

    A type gate does not close a float's value range: ``nan``, ``inf``
    and ``-inf`` are all exactly ``float``. Each row is driven beside a
    good ``ref=1.0`` in BOTH orders and both answers must match.

    TWO ROWS ARE NOT THIS UNIT'S AND ARE PINNED AS-IS, so a later reader
    does not credit them here:
      * "numeric string" raises TypeError and "missing key" raises
        KeyError, both from the DISCHARGE loop's
        ``sort(key=lambda t: t["ref"])`` (:12403), which runs after the
        buy has already been placed. Both raise on every permutation, so
        neither is order-dependent. They are recorded in the unit's
        report as pre-existing defects of the discharge, not the gate.
      * a numeric STRING is still accepted by the gate itself, because
        ``float("2.0")`` parses. Nothing here writes a coerced value
        back, so tightening that would be a second change.

    IF THIS FAILS: a value class that reaches the gate from a corrupt
    or hand-edited state file is answered by position rather than by
    content.
    """
    first = _decision([dict(bad), _row(GOOD)])
    second = _decision([_row(GOOD), dict(bad)])
    assert first == second, (
        f"{label}: [bad, good] gave {first} but [good, bad] gave {second}")
    assert first == expected, (
        f"{label}: expected {expected}, observed {first}")


ALONE = [
    ("nan", _row(NAN), "REFUSED"),
    ("+inf", _row(INF), "REFUSED"),
    ("-inf", _row(float("-inf")), "REFUSED"),
    ("int zero", _row(0), "REFUSED"),
    ("negative", _row(-5.0), "REFUSED"),
    ("huge int 10**400", _row(10 ** 400), "REFUSED"),
    ("None", _row(None), "REFUSED"),
    ("bool False", _row(False), "REFUSED"),
    ("missing key", _row(None, present=False), "REFUSED"),
]


@pytest.mark.parametrize(
    "label, bad, expected", ALONE, ids=[r[0] for r in ALONE])
def test_a_ladder_of_one_unreadable_row_refuses(label, bad, expected):
    """NO READABLE ROW MEANS NO THRESHOLD MEANS NO FIRE.

    ``+inf`` is the row that moved. Before this change a lone ``inf``
    ref PLACED A BUY, because ``price <= inf`` is True for every price
    -- the gate was not merely wrong, it was absent. ``10**400`` also
    moved: ``float()`` raises OverflowError on it, which the old
    ``except (TypeError, ValueError)`` did not catch, so it left the
    method entirely and crashed the fold instead of refusing it.

    IF THIS FAILS: a bot whose whole ladder is corrupt buys at market
    with nothing to measure the price against.
    """
    assert _decision([dict(bad)]) == expected


def test_an_inf_ref_no_longer_disables_the_gate_for_its_neighbours():
    """The sharpest single consequence, pinned on its own.

    An ``inf`` ref used to make EVERY price pass, so one corrupt row
    turned the whole distance gate off for the bot. Here the good ref is
    1.0, its threshold ~0.984, and the price is 5.0 -- far above
    anything the ladder justifies.

    IF THIS FAILS: one corrupt row re-disables the gate on the path
    where every other gate is already bypassed, which is the defect the
    gate was built to close, restored by a value nobody typed.
    """
    assert _decision(_ladder(INF, 1.0), price=5.0) == "REFUSED"
    assert _decision(_ladder(1.0, INF), price=5.0) == "REFUSED"


# ═════════════════════════════════════════════════════════════════════
# SITE B -- THE SORT THAT SIZES THE ORDER
# ═════════════════════════════════════════════════════════════════════
#
# Everything above tests the DECISION. Site B decides the AMOUNT, and
# the two are separate defects with the same root cause:
#
#     key=lambda t: float(t.get("ref", 0.0) or 0.0)
#
# `nan` is TRUTHY, so `or 0.0` never fires and the key receives it.
# Every comparison against nan is False, `sorted` cannot place it, and
# the result depends on where the nan started.
#
# THIS SECTION WAS BUILT WRONG THE FIRST TIME AND THE CORRECTION IS THE
# POINT. `_preview_fold_growth` takes `min(units, _remaining)` from each
# row in sorted order. When the ladder's TOTAL units fit inside the buy,
# every row contributes in full and the sum is the same in ANY order --
# the sort cannot matter and every assertion passes against known-broken
# code. The first sweep was built that way and reported a clean zero
# against the shipped defect.
#
# So the numbers below make `_remaining` BIND. The buy is 16 units, each
# row offers 10, and a `zero` row earns nothing while still CONSUMING
# the remainder -- so whether it sits before or after a `good` row
# changes the surplus. Measured on the pre-change code, ONE content
# {good, nan} gave 17.4976 units for one ordering and 18.0 for the
# other. `test_the_sweep_is_not_vacuous` asserts the sweep still has
# that property, so a future edit that re-clamps it goes red instead of
# green.

SIZING_PRICE = 0.5
SIZING_UNITS = 10.0
SIZING_HOLDINGS = 334.0
SIZING_TARGET = 175.0
# The operator's own: interval 5.0, fee 1.6, growth cap 1.0. At that
# factor (0.934) a ref of 0.6 sets a threshold of 0.5604, above the 0.5
# price, so the distance gate ALLOWS and the sweep measures sizing.
OPERATOR_CFG = {"interval": 5.0, "fee": 1.6}
ALPHABET = (("nan", NAN), ("inf", INF), ("good", 0.6), ("zero", 0.0))
EVERY_INTENT = AUTONOMOUS + ("manual_button",)

# Three well-formed refs, DESCENDING, for the truncation control below.
# The buy takes ~18 base units and each row offers 10, so the discharge
# is exhausted inside the SECOND row and the third is never reached --
# which is what makes "deleting the last row changes nothing" a true
# statement about truncation rather than about arithmetic. The refs sit
# just above the 0.5 price so the accumulator peaks near 1.0 against a
# cycle cap of 1.75, leaving the result unclamped; a clamped preview
# would return the cap for every variant and prove nothing.
TRUNCATING = (0.56, 0.55, 0.54)


def _sizing_bot(refs):
    bot = _bot([{"usd": 10.0, "units": SIZING_UNITS,
                 "initial_buy_price": 0.4, "ref": r} for r in refs],
               holdings=SIZING_HOLDINGS, target=SIZING_TARGET,
               price=SIZING_PRICE, **OPERATOR_CFG)
    return bot


def _answer(refs, intent):
    """(decision, order amount to the bit) -- the PAIR, never one half.

    Either half alone hides the other. The gate can give one decision
    for every ordering while the sizing preview hands the exchange two
    different amounts; that is exactly the pair of defects this unit
    closes, and a test that read only the decision passed through it.

    ``float.hex()`` is exact. A rounded compare would hide the drift.
    """
    bot = _sizing_bot(refs)
    try:
        asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                                  intent))
    except Exception as exc:
        return (f"RAISED {type(exc).__name__}", None)
    placed = bot.seen["placed"]
    if placed is None:
        refused = any("AUTONOMOUS FIRE REFUSED (opposing distance" in m
                      for m in bot._bus.messages)
        return ("REFUSED" if refused else "NO-ORDER-NO-REFUSAL", None)
    side = getattr(placed.get("side"), "value", "?")
    return (("ALLOWED" if side == "buy" else "SCRUMMED"),
            float(placed["amount"]).hex())


def _buckets(size, intent):
    """Every ordered tuple of `size`, grouped by its sorted multiset."""
    out = {}
    for combo in itertools.product(ALPHABET, repeat=size):
        names = tuple(n for n, _ in combo)
        got = _answer(tuple(v for _, v in combo), intent)
        out.setdefault(tuple(sorted(names)), {}).setdefault(
            got, []).append(names)
    return out


@pytest.mark.parametrize("intent", EVERY_INTENT)
@pytest.mark.parametrize("size", (2, 3, 4))
def test_one_answer_per_multiset_at_both_sites(size, intent):
    """THE WHOLE UNIT, stated once, over DECISION AND AMOUNT together.

    Exhaustive ordered tuples over {nan, inf, good, zero}, grouped by
    sorted multiset. Every bucket must hold exactly ONE answer, where
    the answer is the decision AND the order amount to the bit.

    MEASURED BEFORE THE CHANGE, at these same settings: 50 of 130
    autonomous buckets split, and 22 of 65 `manual_button` buckets --
    the manual ones on the AMOUNT alone, because that intent skips the
    gate and leaves site B naked. With ONLY the gate repaired, 30 of 130
    autonomous buckets still split, every one of them amount-only, on
    fires the repaired gate newly allows. That is why the two had to
    land together.

    IF THIS FAILS: the same ladder at the same price sends a different
    quantity to Coinbase depending on the order its rows happen to sit
    in, on a path where every other gate is bypassed by design.
    """
    buckets = _buckets(size, intent)
    split = {k: v for k, v in buckets.items() if len(v) > 1}
    assert not split, (
        f"size {size} / {intent}: {len(split)} of {len(buckets)} multisets "
        f"gave more than one answer — "
        + "; ".join(
            f"{'/'.join(k)} -> " + " vs ".join(
                f"{a[0]}@{None if a[1] is None else float.fromhex(a[1])}"
                for a in v)
            for k, v in list(split.items())[:4]))


@pytest.mark.parametrize("intent", EVERY_INTENT)
@pytest.mark.parametrize("size", (2, 3, 4))
def test_the_sweep_actually_contains_more_than_one_ordering(size, intent):
    """A SINGLE-ORDERING BUCKET PROVES NOTHING ABOUT ORDER.

    ``{nan, nan}`` has one ordering, so "one answer" is arithmetic
    rather than evidence. This counts the buckets that really do hold
    several orderings; if that number were small the sweep above would
    be green for the wrong reason.

    IF THIS FAILS: the order-independence result is an artefact of a
    sweep that never reordered anything — an oracle false negative.
    """
    buckets = _buckets(size, intent)
    multi = sum(1 for v in buckets.values()
                if sum(len(o) for o in v.values()) > 1)
    assert multi >= len(buckets) // 2, (
        f"size {size} / {intent}: only {multi} of {len(buckets)} buckets "
        f"held more than one ordering")


def test_the_sweep_is_not_vacuous_on_the_amount():
    """THE CONTROL WITHOUT WHICH THE SWEEP MEANS NOTHING.

    `_preview_fold_growth` clamps its result to the remaining cycle cap,
    and it contributes nothing at all when the ladder fits inside the
    buy. Under either condition the amount is the same number for every
    ordering however broken the sort is, and every bucket above holds
    one answer for a reason unrelated to this change.

    This requires the sweep's settings to produce SEVERAL distinct
    amounts, and requires the discharge to truncate.

    IF THIS FAILS: the settings drifted into the region where the sort
    cannot affect the amount, and the whole section above is measuring
    nothing.
    """
    amounts = set()
    for size in (2, 3, 4):
        for combo in itertools.product(ALPHABET, repeat=size):
            amounts.add(_answer(tuple(v for _, v in combo),
                                "manual_button")[1])
    assert len(amounts) >= 3, (
        f"the sweep produced only {len(amounts)} distinct amount(s); the "
        f"growth is clamped or the ladder never truncates, so the sort "
        f"cannot influence the amount and the sweep is vacuous")

    # And the truncation itself, OBSERVED THROUGH THE SHIPPING METHOD.
    #
    # This used to compare the ladder's units against a hand-recomputed
    # buy size, `(target - holdings * price) / price`. That number is
    # NOT the one the shipping caller passes: the real caller adds the
    # growth term to the numerator inside a four-iteration fixed point,
    # so the check was an approximation of the very quantity it claimed
    # to verify, and it also compared a summed magnitude against a
    # divided one (`ta_archetype` TA004).
    #
    # Truncation has an exact observable signature instead. If the buy
    # runs out BEFORE the discharge reaches the lowest-ref row, then
    # deleting that row cannot change the answer. Deleting the HIGHEST
    # row must change it -- otherwise no row contributes at all and the
    # first equality would be vacuous in its own right. Both halves are
    # read from the shipping `_preview_fold_growth`, at the units the
    # shipping caller really passed, captured here rather than derived.
    seen: list[float] = []
    probe = _sizing_bot(TRUNCATING)
    _real_preview = probe._preview_fold_growth

    def _capture(units, price):
        seen.append(units)
        return _real_preview(units, price)

    probe._preview_fold_growth = _capture
    asyncio.run(probe._execute_manual_rebalance(
        _Ticker(SIZING_PRICE), "manual_button"))
    assert seen, "the caller never previewed growth, so nothing was sized"
    real_units = seen[-1]

    full = _sizing_bot(TRUNCATING)._preview_fold_growth(
        real_units, SIZING_PRICE)
    less_lowest = _sizing_bot(TRUNCATING[:-1])._preview_fold_growth(
        real_units, SIZING_PRICE)
    less_highest = _sizing_bot(TRUNCATING[1:])._preview_fold_growth(
        real_units, SIZING_PRICE)
    assert full == less_lowest, (
        f"dropping the lowest-ref row moved the growth {full} -> "
        f"{less_lowest}, so the discharge reached that row; the buy "
        f"consumes the whole ladder and row order cannot matter")
    assert full != less_highest, (
        f"dropping the highest-ref row left the growth at {full}, so no "
        f"row contributes and the equality above is vacuous")


# ── c. THE SORT IS A TOTAL ORDER ─────────────────────────────────────


class _MathSpy:
    """`math`, recording every `isfinite` call the module makes."""

    def __init__(self, real):
        self._real = real
        self.calls = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def isfinite(self, value):
        result = self._real.isfinite(value)
        self.calls.append((value, result))
        return result


def test_the_sort_key_never_receives_a_non_finite_value(monkeypatch):
    """THE PROPERTY, PROVED BY DRIVING IT, NOT BY READING THE SOURCE.

    The key is the ref itself, and every ref reaches the key only after
    ``math.isfinite`` admitted it -- so the sort is a total order by
    construction. This replaces the module's ``math`` with a recorder
    and drives a hostile ladder, then requires that EVERY admitted value
    is finite and that one test ran per row, before any ordering.

    THE ASSERTION IS ON THE REF PHASE BY VALUE, NOT ON A TOTAL COUNT.
    It used to read `len(spy.calls) == len(refs)`, which was a proxy for
    "one test per row" that silently assumed `ref` is the ONLY field the
    method tests for finiteness. When the `units` guard landed in the
    same loop the count became 8 for 6 rows and this went red, though
    every ref had still been tested exactly once before the sort. A
    count cannot tell "a row skipped its test" from "a second field is
    also tested".

    So the ref phase is now pinned BY VALUE AND ORDER: the first
    `len(refs)` recorded calls must be exactly the ladder's refs, in
    ladder order, before any ordering happens. That is strictly stronger
    than the count it replaces -- it would catch a row tested twice
    while another went untested, which the count would have passed --
    and it no longer breaks when a later unit guards a second field.

    IF THIS FAILS: some path reaches the sort without the finiteness
    test, `nan` gets in again, and the ordering is decided by list
    position wherever it does.
    """
    import src.trading.scrumming_bot as module

    spy = _MathSpy(math)
    monkeypatch.setattr(module, "math", spy)
    refs = (NAN, INF, 0.6, 0.0, float("-inf"), 0.9)
    bot = _sizing_bot(refs)
    out = bot._preview_fold_growth(16.0, SIZING_PRICE)

    assert len(spy.calls) >= len(refs), (
        f"{len(spy.calls)} finiteness tests for {len(refs)} rows; a row "
        f"reached the ordering without being tested")
    ref_phase = spy.calls[:len(refs)]
    seen = [v for v, _ in ref_phase]
    assert all(a is b or a == b or (a != a and b != b)
               for a, b in zip(seen, refs)), (
        f"the ref phase tested {seen}, not the ladder's own refs "
        f"{list(refs)} in order")
    admitted = [v for v, ok in spy.calls if ok]
    refused = [v for v, ok in ref_phase if not ok]
    assert all(math.isfinite(v) for v in admitted), admitted
    assert len(refused) == 3, refused
    assert math.isfinite(out), out


def test_the_total_order_spy_would_notice_a_non_finite_key(monkeypatch):
    """POSITIVE CONTROL for the spy above.

    A recorder that never fires would report "no non-finite value
    reached the key" for a method that does not test anything. This
    drives the SAME spy over values it must classify both ways and
    requires it to have seen both.

    IF THIS FAILS: the spy is not observing the shipping code, and the
    test above is an assertion about an empty list.
    """
    import src.trading.scrumming_bot as module

    spy = _MathSpy(math)
    monkeypatch.setattr(module, "math", spy)
    bot = _sizing_bot((NAN, 0.6))
    bot._preview_fold_growth(16.0, SIZING_PRICE)
    assert any(ok for _, ok in spy.calls), "the spy admitted nothing"
    assert any(not ok for _, ok in spy.calls), "the spy refused nothing"


# ── d. THE SIZING SKIP IS VISIBLE ────────────────────────────────────


@pytest.mark.parametrize("intent", EVERY_INTENT)
def test_a_row_skipped_by_the_SIZING_is_reported(intent):
    """THE NOTICE ON THE MONEY SIDE, AND ITS COUNT CHECKED AGAINST THE
    LADDER.

    The gate's own notice says a row set no THRESHOLD. This one says a
    row set no DISCHARGE ORDER and added no growth -- which matters
    more, because the gate only withholds a fire while this decides the
    AMOUNT. It is emitted for EVERY intent, including `manual_button`,
    which skips the gate entirely and would otherwise size off a subset
    of the ladder in silence.

    THE COUNT IS CHECKED AGAINST THE LADDER, not against the message's
    own arithmetic. A message that counts itself is consistent with any
    defect.

    IF THIS FAILS: the bot sends an amount computed from part of a
    ladder and nothing says which part.
    """
    refs = (NAN, 0.6, INF, 0.6, 0.0)
    bot = _sizing_bot(refs)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE), intent))

    unreadable = sum(1 for r in refs if not math.isfinite(r))
    total = len(refs)
    assert unreadable == 2 and total == 5, "the fixture drifted"

    lines = [m for m in bot._bus.messages
             if "FOLD SIZING REF UNREADABLE" in m]
    assert len(lines) == 1, (
        f"expected exactly one sizing notice, got {len(lines)}: "
        f"{bot._bus.messages}")
    line = lines[0]
    assert f"{unreadable} of {total} queued tranche(s)" in line, line
    assert f"sized on the {total - unreadable} readable one(s)" in line, line
    assert "not a finite number" in line, line
    assert "NOT altered" in line, line
    # the counter the notice reads is the ladder's, not a running total
    assert bot._fold_preview_unreadable_refs == unreadable


def test_a_clean_ladder_says_nothing_about_unreadable_refs():
    """THE OTHER HALF OF THE NOTICE.

    A message that appears on every fold is noise, and noise is how a
    real warning gets ignored. Nothing is said when nothing was skipped.

    IF THIS FAILS: the notice fires on healthy ladders, and the operator
    learns to skip past the one line that would have told him his state
    file is damaged.
    """
    bot = _sizing_bot((0.6, 0.6, 0.0))
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                              "manual_button"))
    assert not [m for m in bot._bus.messages
                if "FOLD SIZING REF UNREADABLE" in m], bot._bus.messages
    assert bot._fold_preview_unreadable_refs == 0


def test_the_skip_counter_does_not_carry_over_between_folds():
    """THE RESET, driven rather than trusted, over TWO CONSECUTIVE FOLDS.

    The counter lives on the bot. The caller clears it BEFORE the fixed
    point, because `_denom_pre <= 0` skips the loop entirely and a count
    left from an earlier fold would then be reported against a ladder it
    never came from.

    THE POSITION IS RESET BETWEEN THE TWO FIRES, and that is not
    cosmetic. The first fold buys the deficit, so the second fire on the
    untouched bot lands inside the dust band and takes neither branch --
    it runs no growth preview at all, the counter is not written, and an
    earlier version of this test read the first fold's value and called
    it a carry-over defect. The contract is about the LAST PREVIEW, so
    the test has to produce a second preview.

    IF THIS FAILS: an operator repairs his state, folds again, and is
    told the same rows are still broken.
    """
    bot = _sizing_bot((NAN, 0.6))
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                              "manual_button"))
    assert bot.seen["placed"] is not None, "the first fire must fold"
    assert bot._fold_preview_unreadable_refs == 1

    bot._fold_tranches = [{"usd": 10.0, "units": SIZING_UNITS,
                           "initial_buy_price": 0.4, "ref": 0.6}]
    bot._current_holdings = SIZING_HOLDINGS
    bot._main_lots = [{"units": SIZING_HOLDINGS,
                       "initial_buy_price": SIZING_PRICE}]
    bot._target_balance = SIZING_TARGET
    bot._anchor_target_balance = SIZING_TARGET
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot.seen["placed"] = None
    bot._bus.messages.clear()
    bot._manual_fire_pending = True
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                              "manual_button"))
    assert bot.seen["placed"] is not None, "the second fire must fold too"
    assert bot._fold_preview_unreadable_refs == 0, (
        "the count from the previous fold survived into this one")
    assert not [m for m in bot._bus.messages
                if "FOLD SIZING REF UNREADABLE" in m]
