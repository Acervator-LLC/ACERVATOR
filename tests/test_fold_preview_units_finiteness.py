"""THE THIRD ORDER-DEPENDENT MONEY SITE: `units` in the fold preview.

Two sites in `_preview_fold_growth` were closed before this one, both
on `ref`: the value that sets a row's discharge ORDER. This closes the
third, on `units`: the value that sets how MUCH a row discharges. Same
rule, one field over -- a value sets an ordering or a threshold only if
it is finite, tested BEFORE any comparison rather than as part of one.

WHAT THE DEFECT DID, driven rather than predicted. The work order
predicted the poisoned remainder would produce a wrong non-zero amount.
It does not. Driving `[big, nan, big]` through the shipping method
showed:

    take = min(nan, _remaining)      -> nan   (nan < x is False)
    take <= 1e-12                    -> False, so the row is NOT skipped
    _accum += take * (_ref - price)  -> nan
    _remaining -= take               -> nan
    _remaining <= 1e-12              -> False for ever; `break` is DEAD

and then, at the end, `max(0.0, nan * quote)` returns **0.0**, because
`nan > 0.0` is False. So the poisoned accumulator never surfaces as a
nan the caller could notice. It surfaces as ZERO GROWTH, which silently
reinstates the exact defect this method exists to prevent: the fold
lands short and cannot compound. A test asserting "the answer becomes
nan" would have passed on the broken code and shipped the defect.

WHY THE REFS TIE IN EVERY FIXTURE HERE. The method sorts by `ref`
descending before the loop. With DISTINCT refs the loop order is fixed
and no input ordering can show through, so a sweep over distinct refs
measures ref/units PAIRING -- a different ladder each time -- not a
reordering of one ladder. Holding every ref equal makes the sort a tie;
`list.sort` is stable, so the input order reaches the loop unchanged and
an order-dependent answer is attributable to the loop alone.

THIS IS NOT A CONTRIVANCE. The operator's own largest real ladder, read
read-only from his state file on 2026-08-15, is 156 rows carrying just
FOUR distinct refs -- 106 tied at 0.02443 and 44 more at 0.02307. Tied
refs are the normal shape of his data, not an edge case, so the stable
sort really does leave input order in control of the discharge loop.

THE REDS IN THIS FILE WERE REAL. The order-independence sweep and the
break-fires test both failed against the pre-change method while it was
being written, and the calibration of the read-first enumerator that
found this site failed twice for its own reasons before it discriminated.
Those failures are recorded in the unit's report.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import math

import pytest

from tests.test_fold_gate_order_independence import (
    EVERY_INTENT,
    INF,
    NAN,
    OPERATOR_CFG,
    SIZING_HOLDINGS,
    SIZING_PRICE,
    SIZING_TARGET,
    _bot,
    _Ticker,
)

# Well-formed, above the price, and THE SAME on every row so the sort
# ties and the input order survives into the discharge loop.
#
# 0.56 RATHER THAN 0.6, AND THE CONTROL CHOSE IT. At 0.6 the row
# surplus is 0.1/unit, so an 18-unit buy accumulates 1.8 against a cycle
# cap of 1.75 and EVERY answer clamps to the cap -- which would have
# made the order-independence sweep pass by flattening its own
# measurement. `test_the_units_sweep_is_not_vacuous` caught exactly
# that and reported `growth 1.75 against cap 1.75`. At 0.56 the surplus
# is 0.06/unit and 18 units reach 1.08, comfortably unclamped, and the
# distance gate still allows because 0.56 * 0.934 = 0.523 sits above the
# 0.5 price.
GOOD_REF = 0.56

# `big` exceeds what one row can discharge against the buy, `small` does
# not, and `zero` contributes nothing. Together they make the ladder
# truncate rather than run to the end -- asserted, not assumed, by
# `test_the_units_sweep_is_not_vacuous`.
ALPHABET = (("nan", NAN), ("inf", INF), ("big", 10.0),
            ("small", 3.0), ("zero", 0.0))

# The operator's own largest real ladder: bot c8e5c5db, 156 rows,
# captured READ-ONLY from ~/.acervator/bot_state.json on 2026-08-15.
# Held verbatim so the in-spec control runs on the shape his money
# actually has, not on a shape chosen to suit the assertion.
REAL_LADDER = (
    (0.02307, 16.05757596502564), (0.02307, 2.1225710445587276),
    (0.02307, 10.247448159771844), (0.02307, 11.52281377261206),
    (0.02307, 6.049591058032313), (0.02307, 0.7177170476109538),
    (0.02307, 0.012367047853611937), (0.02307, 4.001908693042009),
    (0.02307, 3.671684081820782), (0.02307, 4.726214689257208),
    (0.02307, 5.392945570138096), (0.02307, 9.533339050682512),
    (0.02307, 8.100180837008134), (0.02307, 0.9013196992226786),
    (0.02307, 1.6060339482213937), (0.02307, 4.561425963818048),
    (0.02307, 14.60877994835712), (0.02307, 4.7290313477999275),
    (0.02307, 12.02830210533179), (0.02307, 0.8498303788354915),
    (0.02307, 1.887165204349482), (0.02307, 7.350677020715576),
    (0.02307, 8.32107736593468), (0.02307, 4.400797054879652),
    (0.02307, 14.497836764977402), (0.02307, 2.5992029451208634),
    (0.02307, 12.616675072006986), (0.02307, 18.38941808037523),
    (0.02307, 0.4358232153819219), (0.02307, 91.93637900155736),
    (0.02307, 3.162118880553647), (0.02307, 50.73230019957436),
    (0.02307, 0.5021632350226195), (0.02307, 0.7272855505499436),
    (0.02307, 17.15857196933031), (0.02307, 34.786738091307235),
    (0.02307, 26.479680927564395), (0.02307, 6.859633960071549),
    (0.02307, 45.96048078512275), (0.02307, 15.060906673779193),
    (0.02307, 26.419814763804254), (0.02307, 11.38303522854934),
    (0.02307, 3.891137600470989), (0.02307, 9.999999999999481),
    (0.02443, 0.35135561404731025), (0.02443, 0.6168129967228372),
    (0.02443, 0.3585862012275434), (0.02443, 1.756248726968331),
    (0.02443, 0.13260474542577103), (0.02443, 1.2942436493470337),
    (0.02443, 1.346963046598738), (0.02443, 0.9025305922932351),
    (0.02443, 0.5399785130065273), (0.02443, 0.23298886917375258),
    (0.02443, 1.1171732691871057), (0.02443, 0.085644402451279),
    (0.02443, 0.8913356665100879), (0.02443, 0.42318263004657397),
    (0.02443, 0.3291240553351481), (0.02443, 0.21371925133366018),
    (0.02443, 1.2873961573620842), (0.02443, 0.1165338907237369),
    (0.02443, 1.3397376007603645), (0.02443, 0.30415384504463316),
    (0.02443, 0.4819622543690833), (0.02443, 0.3621738315243262),
    (0.02443, 0.1425025364978587), (0.02443, 0.04107813439675888),
    (0.02443, 0.8991023530586362), (0.02443, 1.0502164379807297),
    (0.02443, 0.05680458512996033), (0.02443, 1.930808910845731),
    (0.02443, 0.08525750395350751), (0.02443, 0.08643601611121352),
    (0.02443, 0.23150177710775888), (0.02443, 0.2820709342071193),
    (0.02443, 0.5397866370915642), (0.02443, 0.9640612000232344),
    (0.02443, 0.9789838272393844), (0.02443, 1.7997405018809272),
    (0.02443, 0.5714940473374044), (0.02443, 1.5800953026252937),
    (0.02443, 1.3166743309892577), (0.02443, 4.546198009345945),
    (0.02443, 0.21159583659744632), (0.02443, 0.30188961680306303),
    (0.02443, 1.613399019715371), (0.02443, 0.9855889964699347),
    (0.02443, 2.9352251394224407), (0.02443, 0.020924684024890144),
    (0.02443, 1.6041360724286755), (0.02443, 0.7399777792564941),
    (0.02443, 0.32619881491516844), (0.02443, 1.4506198241096315),
    (0.02443, 3.182397021090051), (0.02443, 0.29670998434817447),
    (0.02443, 0.38591536408210325), (0.02443, 0.2033342885343338),
    (0.02443, 0.7821285388043792), (0.02443, 0.2456425134498349),
    (0.02443, 0.01040035102852449), (0.02443, 0.1931614739486564),
    (0.02443, 0.5090153865414588), (0.02443, 0.04550203365392041),
    (0.02443, 1.3955085396915619), (0.02443, 3.326355527022752),
    (0.02443, 1.0162769301389574), (0.02443, 3.500000000000259),
    (0.02443, 0.4808168282827081), (0.02443, 6.470038775926412),
    (0.02443, 0.3100560260537075), (0.02443, 0.3421942301559687),
    (0.02443, 2.7567503962380537), (0.02443, 2.489033236437236),
    (0.02443, 8.25021929134968), (0.02443, 1.658954273541691),
    (0.02443, 2.232686780519298), (0.02443, 0.40099520039881176),
    (0.02443, 5.181996844984345), (0.02443, 5.975042202743342),
    (0.02443, 10.929694824183771), (0.02443, 1.4963594131946003),
    (0.02443, 2.351476748092866), (0.02443, 2.976748690895869),
    (0.02443, 0.7964361354911211), (0.02443, 4.967301274361092),
    (0.02443, 2.197486872183556), (0.02443, 0.5510527977193407),
    (0.02443, 0.7329140155356666), (0.02443, 0.5290119178647479),
    (0.02443, 1.7739956484552553), (0.02443, 5.279570984031315),
    (0.02443, 11.299027837300631), (0.02443, 6.834268329549046),
    (0.02443, 13.817265563987716), (0.02443, 3.5494382691631774),
    (0.02443, 13.773478685305841), (0.02443, 15.08839423847894),
    (0.02443, 6.106631250007737), (0.02443, 12.974038444185567),
    (0.02443, 18.03315724868122), (0.02443, 0.6381270762151452),
    (0.02443, 16.638127076215202), (0.02443, 20.863879213328367),
    (0.02443, 15.989889397090145), (0.02443, 7.401519778657538),
    (0.02443, 6.930609160327798), (0.02443, 18.5988781262384),
    (0.02443, 33.61769050986761), (0.02443, 2.845579795399722),
    (0.0255726422764228, 22.6255827767871),
    (0.0255726422764228, 81.923579260178),
    (0.0255726422764228, 52.34557979539995),
    (0.0255726422764228, 89.10525816763496),
    (0.02606, 25.639509391424966), (0.02606, 59.860490608575034),
)


def _units_bot(units_seq, ref=GOOD_REF):
    """A bot whose ladder varies only in `units`; every ref identical."""
    return _bot([{"usd": 10.0, "units": u, "initial_buy_price": 0.4,
                  "ref": ref} for u in units_seq],
                holdings=SIZING_HOLDINGS, target=SIZING_TARGET,
                price=SIZING_PRICE, **OPERATOR_CFG)


def _answer(units_seq, intent="manual_button"):
    """(decision, order amount to the bit) -- the PAIR, never one half.

    Either half alone hides the other. The gate can hand back one
    decision for every ordering while the sizing preview sends the
    exchange two different amounts; that is exactly this defect, and a
    test reading only the decision passes straight through it.

    `float.hex()` is exact. A rounded compare would hide the drift.
    """
    bot = _units_bot(units_seq)
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


def _buckets(size, intent="manual_button"):
    """Every ordered tuple of `size`, grouped by its sorted multiset."""
    out: dict = {}
    for combo in itertools.product(ALPHABET, repeat=size):
        names = tuple(n for n, _ in combo)
        got = _answer(tuple(v for _, v in combo), intent)
        out.setdefault(tuple(sorted(names)), {}).setdefault(
            got, []).append(names)
    return out


# -- a. ORDER INDEPENDENCE ON UNITS ---------------------------------


@pytest.mark.parametrize("size", (2, 3, 4))
def test_every_units_multiset_gives_exactly_one_answer(size):
    """THE WHOLE POINT, swept rather than sampled.

    A ladder is a SET of rows. The order they arrive in is an accident
    of how state was written, so two ladders holding the same rows must
    send the same amount. Every ordering of every multiset is driven
    through the real `_execute_manual_rebalance`, and each multiset must
    collapse to ONE (decision, amount) pair.

    IF THIS FAILS: the same ladder sends two different amounts to
    Coinbase depending on the order rows happen to sit in the state
    file, and no log line says which one the operator got.
    """
    buckets = _buckets(size)
    split = {k: v for k, v in buckets.items() if len(v) > 1}
    assert not split, (
        f"size {size}: {len(split)} multiset(s) gave more than one "
        f"answer: " + "; ".join(
            f"{k} -> {sorted(v)}" for k, v in sorted(split.items())))


@pytest.mark.parametrize("size", (2, 3, 4))
def test_the_units_sweep_covers_more_than_one_ordering(size):
    """A SINGLE-ORDERING BUCKET PROVES NOTHING.

    If every multiset held one ordering, the test above would be
    comparing each answer with itself and would pass on any code at all.

    IF THIS FAILS: the sweep above is vacuous and its green is empty.
    """
    buckets = _buckets(size)
    multi = [k for k, v in buckets.items()
             if sum(len(o) for o in v.values()) > 1]
    assert len(multi) >= len(buckets) // 2, (
        f"size {size}: only {len(multi)} of {len(buckets)} buckets held "
        f"more than one ordering")


def test_the_units_sweep_is_not_vacuous():
    """BOTH CONDITIONS THE SWEEP DEPENDS ON, READ BACK.

    A previous sweep of this method returned a false zero because
    neither condition held: the ladder did not truncate, so no ordering
    could ever reach a row another ordering had skipped, and the cycle
    cap clamped every answer to the same number.

    TRUNCATION means the buy exhausts inside the ladder, leaving at
    least one row unread -- that is what makes "which row came first"
    able to matter. NO CLAMP means the returned growth is the ladder's
    own surplus rather than the cap, so a difference in surplus is
    visible in the answer instead of being flattened.

    IF THIS FAILS: every other test in this file is measuring a
    scenario in which the defect could not have appeared, and their
    greens say nothing about the code.
    """
    reads: list[float] = []

    class _Row(dict):
        def get(self, key, default=None):
            if key == "units":
                reads.append(super().get("units"))
            return super().get(key, default)

    bot = _units_bot([10.0, 10.0, 10.0, 10.0])
    bot._fold_tranches = [_Row(r) for r in bot._fold_tranches]
    growth = bot._preview_fold_growth(18.0, SIZING_PRICE)

    assert len(reads) < len(bot._fold_tranches), (
        f"the ladder did NOT truncate: the loop read all "
        f"{len(reads)} rows, so no ordering can skip a row")

    cap = bot._anchor_target_balance * (
        bot.config.max_target_growth_pct / 100.0)
    assert 0.0 < growth < cap, (
        f"the cycle cap is clamping: growth {growth} against cap {cap}")


# -- b. THE AMOUNT IS UNCHANGED ON WELL-FORMED LADDERS ---------------


WELL_FORMED = (
    (10.0, 10.0, 10.0),
    (3.0, 10.0, 3.0, 10.0),
    (0.0, 10.0, 10.0),
    (1.5, 2.5, 3.5, 4.5),
    (10.0,),
)


@pytest.mark.parametrize("units_seq", WELL_FORMED)
def test_a_well_formed_ladder_still_sizes_the_same_amount(units_seq):
    """THE ONE THING THIS CHANGE MUST NOT DO.

    The finiteness test is new; the coercion is not. `float(x) or 0.0`
    still runs, so every ladder that sized correctly before must size to
    the identical bit pattern now. The expected surplus is computed here
    from the ladder itself -- take = min(row, remaining), surplus =
    take * (ref - price) -- rather than read back out of the method, so
    the assertion does not derive from the code it checks.

    IF THIS FAILS: the finiteness test is rejecting rows it should have
    admitted, and every fold on healthy state is now sized short.
    """
    bot = _units_bot(units_seq)
    buy_units = 18.0
    remaining = buy_units
    expect = 0.0
    for u in units_seq:
        if remaining <= 1e-12:
            break
        take = min(u, remaining)
        if take <= 1e-12:
            continue
        if GOOD_REF > SIZING_PRICE:
            expect += take * (GOOD_REF - SIZING_PRICE)
        remaining -= take
    got = bot._preview_fold_growth(buy_units, SIZING_PRICE)
    assert float(got).hex() == float(expect).hex(), (
        f"{units_seq}: got {got!r} want {expect!r}")


def test_the_operators_own_largest_real_ladder_is_unchanged():
    """THE REAL SHAPE, NOT A SHAPE CHOSEN TO SUIT THE ASSERTION.

    156 rows, three distinct refs, 44 of them tied at 0.02307 -- read
    read-only from the operator's state file. A fixture built to match
    the predicate under test cannot falsify it; this one was built from
    his data before any assertion was written.

    The JSON ROUND TRIP is part of the control: his ladder reaches the
    bot through `json.loads`, and a float that survives the arithmetic
    but not the serialiser would still change the amount he is charged.

    IF THIS FAILS: the change moved the number on the one ladder that is
    certain to be exercised the next time his fold fires.
    """
    rows = [{"usd": 1.0, "units": u, "initial_buy_price": 0.01,
             "ref": r} for r, u in REAL_LADDER]
    assert len(rows) == 156, len(rows)
    refs = [r["ref"] for r in rows]
    assert len(set(refs)) == 4, "the fixture drifted"
    assert refs.count(0.02443) == 106 and refs.count(0.02307) == 44, (
        "the tie structure drifted -- the ties are the whole reason "
        "this ladder can expose an order-dependent answer")

    direct = _bot(rows, holdings=SIZING_HOLDINGS, target=SIZING_TARGET,
                  price=SIZING_PRICE, **OPERATOR_CFG)
    tripped = _bot(json.loads(json.dumps(rows)),
                   holdings=SIZING_HOLDINGS, target=SIZING_TARGET,
                   price=SIZING_PRICE, **OPERATOR_CFG)

    a = direct._preview_fold_growth(18.0, 0.01)
    b = tripped._preview_fold_growth(18.0, 0.01)
    assert float(a).hex() == float(b).hex(), (a, b)
    assert math.isfinite(a) and a > 0.0, a


def test_the_comparator_sees_a_ladder_that_must_differ():
    """THE CANARY. A comparator that cannot go red is not a comparator.

    Two ladders whose surpluses genuinely differ must compare unequal
    under the same `float.hex()` test the controls above rely on. This
    is the positive side of those assertions: without it, a broken
    comparator would make every "unchanged" claim above pass by being
    blind rather than by being right.

    IF THIS FAILS: the equality checks in this file are not reading the
    amount, and their greens are empty.
    """
    small = _units_bot((1.0, 1.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    large = _units_bot((10.0, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    assert float(small).hex() != float(large).hex(), (small, large)

    higher = _units_bot((10.0, 10.0), ref=0.9).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    assert float(higher).hex() != float(large).hex(), (higher, large)


def test_the_coercion_is_unchanged_for_strings_and_none():
    """THE COERCION SURVIVES; ONLY THE FINITENESS TEST IS NEW.

    `float(x) or 0.0` still parses a string and still reads a None as
    0.0. Narrowing this to `as_finite_float` would ALSO drop string and
    bool units and would change the amount on ladders that size
    correctly today.

    IF THIS FAILS: the repair widened past its remit and silently
    dropped rows that have always been sized.
    """
    as_str = _units_bot(("10.0", "10.0")).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    as_num = _units_bot((10.0, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    assert float(as_str).hex() == float(as_num).hex(), (as_str, as_num)

    with_none = _units_bot((None, 10.0, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    with_zero = _units_bot((0.0, 10.0, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    assert float(with_none).hex() == float(with_zero).hex(), (
        with_none, with_zero)


# -- c. THE POISONED REMAINDER IS GONE -------------------------------


def test_the_break_fires_with_a_non_finite_row_in_the_ladder():
    """THE DEAD `break`, OBSERVED AT THE LOOP RATHER THAN INFERRED.

    `_remaining -= nan` used to make `_remaining <= 1e-12` False for the
    rest of the ladder, so the `break` at the top of the loop could
    never fire again and every remaining row was read. A dict subclass
    records each `get("units")` the shipping loop performs, so the row
    count is measured at the method's own access.

    IF THIS FAILS: a single damaged row still disables the loop's exit
    and the remainder is still poisoned for every row behind it.
    """
    reads: list[str] = []

    class _Row(dict):
        def get(self, key, default=None):
            if key == "units":
                reads.append(repr(super().get("units")))
            return super().get(key, default)

    bot = _units_bot([10.0, NAN, 10.0, 10.0])
    bot._fold_tranches = [_Row(r) for r in bot._fold_tranches]
    growth = bot._preview_fold_growth(18.0, SIZING_PRICE)

    assert len(reads) < 4, (
        f"the break never fired: the loop read all {len(reads)} rows "
        f"({reads})")
    assert math.isfinite(growth), growth
    assert growth > 0.0, (
        "the growth collapsed to zero -- the accumulator was poisoned "
        "and `max(0.0, nan)` swallowed it")


def test_a_non_finite_row_does_not_zero_the_growth():
    """THE OBSERVABLE THE DEFECT ACTUALLY PRODUCED.

    Not a nan answer -- a ZERO one, because `max(0.0, nan)` is 0.0. A
    ladder carrying one damaged row must still size off its healthy
    rows, exactly as a ladder shorter by that row would.

    IF THIS FAILS: one bad row in state silently reverts the fold to
    pre-growth sizing, which is the defect `_preview_fold_growth` was
    written to prevent.
    """
    poisoned = _units_bot((10.0, NAN, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    without = _units_bot((10.0, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    assert float(poisoned).hex() == float(without).hex(), (
        poisoned, without)


@pytest.mark.parametrize("bad", (NAN, INF, -INF))
def test_every_non_finite_units_value_is_skipped_not_absorbed(bad):
    """nan AND inf, because the rule is finiteness and not nan-ness.

    `min(inf, remaining)` returns the remainder and silently consumes
    the whole buy, which is a different wrong answer from nan's but the
    same root cause.

    IF THIS FAILS: the guard tests for the wrong property and one class
    of damaged row still reaches the arithmetic.
    """
    got = _units_bot((10.0, bad, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    want = _units_bot((10.0, 10.0)).\
        _preview_fold_growth(18.0, SIZING_PRICE)
    assert float(got).hex() == float(want).hex(), (bad, got, want)


# -- d. THE REFUSAL IS VISIBLE ---------------------------------------


@pytest.mark.parametrize("intent", EVERY_INTENT)
def test_a_row_skipped_for_units_is_reported(intent):
    """THE TWIN OF THE REF NOTICE, ON THE SAME SURFACE.

    The ref notice says a row set no discharge ORDER. This one says a
    row discharged no AMOUNT. Both shrink the ladder the buy is sized
    on, and the operator needs the same sentence about each. Emitted for
    EVERY intent, including `manual_button`, which skips the distance
    gate entirely and would otherwise size off a subset in silence.

    THE COUNT IS CHECKED AGAINST THE LADDER, not against the message's
    own arithmetic. A message that counts itself is consistent with any
    defect.

    IF THIS FAILS: the bot sends an amount computed from part of a
    ladder and nothing says which part.
    """
    units = (NAN, 10.0, INF, 10.0, 0.0)
    bot = _units_bot(units)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                              intent))

    unsizable = sum(1 for u in units if not math.isfinite(u))
    total = len(units)
    assert unsizable == 2 and total == 5, "the fixture drifted"

    lines = [m for m in bot._bus.messages
             if "FOLD SIZING UNITS UNREADABLE" in m]
    assert len(lines) == 1, (
        f"expected exactly one units notice, got {len(lines)}: "
        f"{bot._bus.messages}")
    line = lines[0]
    assert f"{unsizable} of {total} queued tranche(s)" in line, line
    assert "not a finite number" in line, line
    assert "NOT altered" in line, line
    assert bot._fold_preview_unreadable_units == unsizable


def test_a_clean_ladder_says_nothing_about_unreadable_units():
    """THE OTHER HALF OF THE NOTICE.

    A message that appears on every fold is noise, and noise is how a
    real warning gets ignored.

    IF THIS FAILS: the notice fires on healthy ladders and the operator
    learns to skip past the one line that would have told him his state
    file is damaged.
    """
    bot = _units_bot((10.0, 10.0, 0.0))
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                              "manual_button"))
    assert not [m for m in bot._bus.messages
                if "FOLD SIZING UNITS UNREADABLE" in m], bot._bus.messages
    assert bot._fold_preview_unreadable_units == 0


def test_the_units_counter_does_not_carry_over_between_folds():
    """THE RESET, DRIVEN OVER TWO CONSECUTIVE FIRES.

    The counter lives on the bot. The caller clears it BEFORE the fixed
    point, because `_denom_pre <= 0` skips the loop entirely and a count
    left from an earlier fold would then be reported against a ladder it
    never came from.

    THE POSITION IS RESET BETWEEN THE TWO FIRES, and that is not
    cosmetic. The first fold buys the deficit, so a second fire on the
    untouched bot lands inside the dust band, takes neither branch and
    runs NO preview at all -- the counter is never written and the test
    reads the first fold's value. The first version of this test did
    exactly that and called it a carry-over defect; the contract is
    about the LAST PREVIEW, so the test must produce a second preview.

    IF THIS FAILS: a damaged ladder makes every LATER fold claim damage
    it does not have, and the notice stops meaning anything.
    """
    bot = _units_bot((NAN, 10.0, 10.0))
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SIZING_PRICE),
                                              "manual_button"))
    assert bot.seen["placed"] is not None, "the first fire must fold"
    assert bot._fold_preview_unreadable_units == 1

    bot._fold_tranches = [{"usd": 10.0, "units": 10.0,
                           "initial_buy_price": 0.4, "ref": GOOD_REF}
                          for _ in range(3)]
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
    assert bot._fold_preview_unreadable_units == 0, (
        "the count carried over from the previous fold")
    assert not [m for m in bot._bus.messages
                if "FOLD SIZING UNITS UNREADABLE" in m]


def test_the_two_notices_are_independent():
    """A ROW CAN FAIL EITHER TEST, AND THE REPAIR DIFFERS BY FIELD.

    A ladder whose refs are all readable but whose units are not must
    raise the units notice and NOT the ref notice, and the reverse.
    Collapsing them into one message would tell the operator to repair
    the wrong field.

    IF THIS FAILS: the two counters are aliased and the notice names a
    field that is not the damaged one.
    """
    units_bad = _units_bot((NAN, 10.0, 10.0))
    asyncio.run(units_bad._execute_manual_rebalance(
        _Ticker(SIZING_PRICE), "manual_button"))
    msgs = units_bad._bus.messages
    assert [m for m in msgs if "FOLD SIZING UNITS UNREADABLE" in m], msgs
    assert not [m for m in msgs
                if "FOLD SIZING REF UNREADABLE" in m], msgs

    ref_bad = _bot([{"usd": 10.0, "units": 10.0,
                     "initial_buy_price": 0.4, "ref": r}
                    for r in (NAN, GOOD_REF, GOOD_REF)],
                   holdings=SIZING_HOLDINGS, target=SIZING_TARGET,
                   price=SIZING_PRICE, **OPERATOR_CFG)
    asyncio.run(ref_bad._execute_manual_rebalance(
        _Ticker(SIZING_PRICE), "manual_button"))
    msgs = ref_bad._bus.messages
    assert [m for m in msgs if "FOLD SIZING REF UNREADABLE" in m], msgs
    assert not [m for m in msgs
                if "FOLD SIZING UNITS UNREADABLE" in m], msgs
