"""Every spawn site must MERGE remnants, not just build tranches.

THE DEFECT
==========
Three places in ``scrumming_bot.py`` lengthen ``self._fold_tranches``:

* the autonomous SCRUM sell in ``tick``     -- merged remnants,
* the DIST re-fold sell in ``tick``         -- merged remnants,
* ``_execute_manual_rebalance``             -- DID NOT.

``_top_up_remnant_fold_tranches`` is what collapses a part-spent tranche
back together with the next opposing trade's money. Without it on the
third site, every fire there left a NEW record beside the remnants
instead of merging into them, so the tranche list grew on that path
alone.

That site is not "the manual button". ``_INTENT_MAP`` routes three
callers through the same build loop and two of them fire autonomously:
Wire Stack and Max Cartridge. So the growth was never bounded by
operator clicks.

THE GOVERNING RULE, operator 2026-08-12: "Functionality should be
mirrored between either side of the ladder." A path that spawns but
never merges is not mirrored with the two that do.

WHERE THE BAND COMES FROM
=========================
The merge only considers remnants whose ``ref`` sits inside the current
Bollinger range. Sites 1 and 2 read ``bb_result``, a LOCAL of ``tick``.
``_execute_manual_rebalance`` is a different method and cannot see it,
and all three of its callers sit ABOVE the ``detect_bb_proximity`` call
in ``tick``, so even a parameter would carry the previous tick's band.
``self._last_bb`` IS that band, cached by ``tick`` itself, and it is
already read this way by the Smart Cartridge gate. Nothing is
recomputed: this path holds no candles. With no band, nothing merges.

WHAT HAPPENS TO ``operator_initiated``
======================================
A merge keeps the OLDER record, so the surviving tranche keeps the tag
it already had. Measured on the operator's pinned state (2026-08-12
23:32:24): 389 of 515 open tranches carry ``operator_initiated=True``,
so most merges will be like-for-like. When they are not, an
operator-initiated tranche merged into an autonomous remnant is
displayed afterwards as autonomous. Only the Fold Tranches "Source"
column reads that field. ``trade.filled`` and ``pnl.event`` carry the
attribution separately and no merge touches them. This file PINS that
behaviour so it cannot drift silently; changing it means changing the
SHARED helper, which is a change to sites 1 and 2 as well.

EVERY CHECK CARRIES A TWO-SIDED CONTROL
=======================================
Each ``_check_*`` helper runs twice: on the shipping code, where it must
pass, and against a planted defect of the kind that check exists to
catch, where it must raise. A plant that no longer matches the shipping
text raises ``StalePlant`` rather than skipping, so a stale plant cannot
decay into a green run.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
from pathlib import Path

import pytest

from src.trading.scrumming_bot import ScrummingBot

REPO = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO / "src" / "trading" / "scrumming_bot.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")

TARGET_LIST = "_fold_tranches"
TOPUP_CALL = "_top_up_remnant_fold_tranches"
FOLD_CALL = "_apply_scrum_fold_pct"
SITE3 = "_execute_manual_rebalance"

# Money is compared to the bit. A tolerance would hide the drift these
# checks exist to catch.
EXACT = 0.0


class StalePlant(RuntimeError):
    """A plant no longer matches the shipping source."""


# ─────────────────────────────────────────────────────────────────────
# THE PRE-CHANGE RECORD — sites 1 and 2, captured before this unit ran
# ─────────────────────────────────────────────────────────────────────
#
# Taken from src/trading/scrumming_bot.py as it stood before the site-3
# call was added. Sites 1 and 2 reach their behaviour through exactly
# two things: the two call statements in ``tick``, and the shared helper
# they call. If all three texts are byte-identical, neither site can
# have changed.
# The three digests below were re-derived 2026-08-25 after the black
# normal-form pass. Not a recalibration: each slice was proved AST-identical
# to the slice its previous digest covered before the constant moved.
PRE_CHANGE_TOPUP_HELPER_SHA256 = (
    "0893eb9b72bb0132e385836b55b14e6a3a0466ba06f48d867eec77bb9da6a975"
)
PRE_CHANGE_TICK_TOPUP_CALLS_SHA256 = (
    "b5c1ffccd3117f5b034c8a04a37837c7afb441d16b00720206cb594ebf3e96ad",
    "01efa42f2c96418bfd602b6c0987f7f5a9229bba55505058371bdac23bb13350",
)
PRE_CHANGE_TICK_FOLDPCT_CALLS_SHA256 = (
    "f6160c8bf7a39c4577e106ecf31354f0f4e57833642809d75aabfccfdeb4eaec",
    "6c462421a2351716076343a212fd3108d5e91741e71d1fcd91892ad99e17c076",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _segment(src: str, node: ast.AST) -> str:
    text = ast.get_source_segment(src, node)
    if text is None:
        raise AssertionError(
            "ast could not recover a node's source; the text checks "
            "below would silently compare nothing"
        )
    return text


def _functions(tree):
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _named(src: str, name: str):
    for node in _functions(ast.parse(src)):
        if node.name == name:
            return node
    raise AssertionError(f"{name} is not in the source at all")


def _self_calls(func, name):
    return [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == name
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "self"
    ]


def _call_statement_texts(src: str, func_name: str, attr: str) -> list[str]:
    """Source of every STATEMENT in `func_name` calling ``self.attr``.

    Statements, not bare calls, so the compare covers the arguments and
    their layout rather than just the name.
    """
    func = _named(src, func_name)
    found: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Expr) and _is_self_call(node.value, attr):
            found.append((node.lineno, _segment(src, node)))
    found.sort()
    return [text for _, text in found]


def _is_self_call(node, attr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    )


# ─────────────────────────────────────────────────────────────────────
# 1. THE WIRING CLAIM — every spawn site merges, in the right order
# ─────────────────────────────────────────────────────────────────────


def _self_attr(node, name) -> bool:
    if isinstance(node, ast.Subscript):
        node = node.value
    return (
        isinstance(node, ast.Attribute)
        and node.attr == name
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _grows_the_list(node) -> bool:
    """True for every way a statement can LENGTHEN the tranche list.

    A grep for ``.append`` is blind to four of the five forms, and the
    fifth would be the one somebody used.
    """
    if isinstance(node, ast.Call):
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in {"append", "insert", "extend"}
            and _self_attr(func.value, TARGET_LIST)
        )
    if isinstance(node, ast.AugAssign):
        return _self_attr(node.target, TARGET_LIST) and isinstance(node.op, ast.Add)
    if isinstance(node, ast.Assign):
        return any(
            isinstance(t, ast.Subscript) and _self_attr(t, TARGET_LIST)
            for t in node.targets
        )
    return False


def _spawn_sites(source: str):
    """(function, growth line, next growth line) for every spawn site."""
    sites = []
    for func in _functions(ast.parse(source)):
        lines = sorted({n.lineno for n in ast.walk(func) if _grows_the_list(n)})
        for index, line in enumerate(lines):
            nxt = lines[index + 1] if index + 1 < len(lines) else 10**9
            sites.append((func, line, nxt))
    return sites


def _check_every_spawn_site_merges(source: str) -> None:
    """The mirroring claim, read at the source surface."""
    sites = _spawn_sites(source)
    if not sites:
        raise AssertionError(
            "no tranche-building site found at all; the walker is blind "
            "and every verdict below it is void"
        )

    for func, line, nxt in sites:
        tops = [c for c in _self_calls(func, TOPUP_CALL) if line < c.lineno < nxt]
        if not tops:
            raise AssertionError(
                f"{func.name} spawns a fold tranche at line {line} and "
                f"never merges remnants. Two of the three spawn sites "
                f"call {TOPUP_CALL}; a site that spawns without merging "
                f"leaves a new record beside every part-spent tranche "
                f"and the list grows on that path alone."
            )
        top = min(t.lineno for t in tops)

        folds = [c for c in _self_calls(func, FOLD_CALL) if line < c.lineno < nxt]
        if not folds:
            raise AssertionError(
                f"{func.name}: spawn site at line {line} has a merge but "
                f"no scrum_fold_pct call to order it against"
            )
        fold = min(f.lineno for f in folds)
        if top < fold:
            raise AssertionError(
                f"{func.name}: the merge at line {top} runs BEFORE the "
                f"scrum_fold_pct call at {fold}. The merge moves this "
                f"sale's money into an older tranche, outside the "
                f"`count_before:` slice, where the operator's fold "
                f"ratio can no longer reach it."
            )


def _plant_site3_never_merges(source: str) -> str:
    """THE DEFECT ITSELF, put back."""
    anchor = "            _merged_n, _ = self._top_up_remnant_fold_tranches("
    if anchor not in source:
        raise StalePlant("the site-3 merge call is not where the plant " "expects it")
    head, _, tail = source.partition(anchor)
    _dropped, _, rest = tail.partition("\n\n")
    return head + "            _merged_n = 0\n\n" + rest


def _plant_site3_merges_first(source: str) -> str:
    """Swap the two calls, so the merge outruns the ratio."""
    lines = source.split("\n")
    func = _named(source, SITE3)
    folds = _self_calls(func, FOLD_CALL)
    tops = _self_calls(func, TOPUP_CALL)
    if not folds or not tops:
        raise StalePlant("site 3 no longer has both calls to swap")
    fold = min(folds, key=lambda c: c.lineno)
    top = min(tops, key=lambda c: c.lineno)
    if not fold.lineno < top.lineno:
        raise StalePlant(
            "plant expects the ratio call to precede the " "merge on site 3"
        )
    fold_text = lines[fold.lineno - 1 : fold.end_lineno]
    top_text = lines[top.lineno - 1 : top.end_lineno]
    lines[fold.lineno - 1 : top.end_lineno] = top_text + fold_text
    return "\n".join(lines)


def _plant_a_fourth_unmerged_site(source: str) -> str:
    anchor = "    def clear_fold_tranches("
    if anchor not in source:
        raise StalePlant("plant anchor is gone from the source")
    rogue = (
        "    def _rogue_spawner(self, take, sale_asset, sale_usd):\n"
        "        t_usd = (take / sale_asset) * sale_usd\n"
        '        self._fold_tranches.append({"usd": t_usd})\n'
        "        self._apply_scrum_fold_pct(0, sale_usd, sale_asset)\n"
        "\n"
    )
    return source.replace(anchor, rogue + anchor, 1)


def test_every_spawn_site_merges_remnants():
    """The claim this unit exists to make true."""
    _check_every_spawn_site_merges(SOURCE)


@pytest.mark.parametrize(
    "plant, label",
    [
        (_plant_site3_never_merges, "site 3 spawns without merging"),
        (_plant_site3_merges_first, "the merge outruns the fold ratio"),
        (_plant_a_fourth_unmerged_site, "a new unmerged site appears"),
    ],
)
def test_control_the_wiring_check_catches_a_planted_defect(plant, label):
    """CONTROL. Each plant must turn the wiring check red."""
    with pytest.raises(AssertionError) as caught:
        _check_every_spawn_site_merges(plant(SOURCE))
    assert str(caught.value).strip(), (
        f"the plant '{label}' failed without saying what changed; a "
        f"control that cannot be read is not evidence"
    )


def test_control_a_blind_walker_is_an_error_not_a_pass():
    """If the walker finds nothing it must say so, not report clean."""
    with pytest.raises(AssertionError, match="walker is blind"):
        _check_every_spawn_site_merges("def unrelated():\n    return 1\n")


# ─────────────────────────────────────────────────────────────────────
# 2. THE BAND SOURCE — cached, never recomputed on this path
# ─────────────────────────────────────────────────────────────────────


def _band_source_names(func) -> set[str]:
    """Locals in `func` assigned from a read of ``self._last_bb``.

    Read off the AST, not the text. The call site EXPLAINS itself in a
    comment that names ``detect_bb_proximity``, and a substring check
    would trip on the explanation instead of the code.
    """
    names: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        reads_it = any(
            (isinstance(sub, ast.Attribute) and sub.attr == "_last_bb")
            or (isinstance(sub, ast.Constant) and sub.value == "_last_bb")
            for sub in ast.walk(node.value)
        )
        if reads_it:
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _check_the_band_is_read_not_recomputed(source: str) -> None:
    func = _named(source, SITE3)
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "detect_bb_proximity"
        ):
            raise AssertionError(
                f"{SITE3} CALLS detect_bb_proximity at line "
                f"{node.lineno}. This path holds no candles; a band "
                f"computed here would be computed from whatever was "
                f"lying around."
            )

    names = _band_source_names(func)
    if not names:
        raise AssertionError(
            f"{SITE3} never reads self._last_bb, so the merge it "
            f"performs cannot be filtered by the tick's real band"
        )

    tops = _self_calls(func, TOPUP_CALL)
    if not tops:
        raise AssertionError(f"{SITE3} does not call {TOPUP_CALL}")
    for call in tops:
        used = {
            n.id
            for arg in call.args[1:]
            for n in ast.walk(arg)
            if isinstance(n, ast.Name)
        }
        if not (used & names):
            raise AssertionError(
                f"{SITE3}: the merge at line {call.lineno} takes its "
                f"band from {sorted(used)}, none of which came from "
                f"self._last_bb. The candidate filter would then run "
                f"on a range this tick never measured."
            )


def _plant_a_recomputed_band(source: str) -> str:
    anchor = '            _bb_last = getattr(self, "_last_bb", None)'
    if anchor not in source:
        raise StalePlant("the band read is not where the plant expects")
    return source.replace(anchor, "            _bb_last = detect_bb_proximity([])", 1)


def _plant_no_band_read_at_all(source: str) -> str:
    anchor = '            _bb_last = getattr(self, "_last_bb", None)'
    if anchor not in source:
        raise StalePlant("the band read is not where the plant expects")
    return source.replace(anchor, "            _bb_last = None", 1)


def _plant_a_hardcoded_band(source: str) -> str:
    """A made-up range wide enough to admit every remnant."""
    anchor = (
        '                float(getattr(_bb_last, "lower", 0.0) '
        "or 0.0),\n"
        '                float(getattr(_bb_last, "upper", 0.0) '
        "or 0.0),\n"
        "            )"
    )
    if anchor not in source:
        raise StalePlant("the band arguments are not where the plant " "expects them")
    return source.replace(
        anchor,
        "                0.0,\n" "                1e9,\n" "            )",
        1,
    )


def test_site3_reads_the_cached_band_and_computes_nothing():
    _check_the_band_is_read_not_recomputed(SOURCE)


@pytest.mark.parametrize(
    "plant, label",
    [
        (_plant_a_recomputed_band, "a band recomputed on a candle-less path"),
        (_plant_no_band_read_at_all, "no band read at all"),
        (_plant_a_hardcoded_band, "an invented range passed to the merge"),
    ],
)
def test_control_the_band_check_catches_a_planted_defect(plant, label):
    with pytest.raises(AssertionError) as caught:
        _check_the_band_is_read_not_recomputed(plant(SOURCE))
    assert str(caught.value).strip(), label


# ─────────────────────────────────────────────────────────────────────
# 3. SITES 1 AND 2 ARE UNCHANGED
# ─────────────────────────────────────────────────────────────────────


def _check_sites_one_and_two_are_unchanged(source: str) -> None:
    """Read at the two surfaces those sites reach behaviour through."""
    helper = _segment(source, _named(source, TOPUP_CALL))
    got = _sha(helper)
    if got != PRE_CHANGE_TOPUP_HELPER_SHA256:
        raise AssertionError(
            f"the SHARED merge helper changed (sha256 {got}, was "
            f"{PRE_CHANGE_TOPUP_HELPER_SHA256}). Sites 1 and 2 call it, "
            f"so a change here is a change to them."
        )

    tops = tuple(_sha(t) for t in _call_statement_texts(source, "tick", TOPUP_CALL))
    if tops != PRE_CHANGE_TICK_TOPUP_CALLS_SHA256:
        raise AssertionError(
            f"the merge calls inside tick changed: {tops} vs the "
            f"pre-change {PRE_CHANGE_TICK_TOPUP_CALLS_SHA256}"
        )

    folds = tuple(_sha(t) for t in _call_statement_texts(source, "tick", FOLD_CALL))
    if folds != PRE_CHANGE_TICK_FOLDPCT_CALLS_SHA256:
        raise AssertionError(
            f"the fold-ratio calls inside tick changed: {folds} vs the "
            f"pre-change {PRE_CHANGE_TICK_FOLDPCT_CALLS_SHA256}"
        )


def _plant_touch_the_shared_helper(source: str) -> str:
    """The change this unit deliberately did NOT make."""
    anchor = '                if not _cand.get("fold_partial_spent"):'
    if anchor not in source:
        raise StalePlant("the helper's candidate test moved")
    return source.replace(
        anchor, '                if not _cand.get("fold_partial_spent", True):', 1
    )


def _plant_touch_site_one(source: str) -> str:
    anchor = (
        "                self._top_up_remnant_fold_tranches(\n"
        "                    _tranche_count_before,"
    )
    if anchor not in source:
        raise StalePlant("site 1's merge call moved")
    return source.replace(
        anchor,
        "                self._top_up_remnant_fold_tranches(\n"
        "                    0,",
        1,
    )


def _plant_touch_site_two(source: str) -> str:
    anchor = (
        "                        self._apply_scrum_fold_pct(\n"
        "                            _dist_tranche_count_before,"
    )
    if anchor not in source:
        raise StalePlant("site 2's ratio call moved")
    return source.replace(
        anchor,
        "                        self._apply_scrum_fold_pct(\n"
        "                            0,",
        1,
    )


def test_sites_one_and_two_are_byte_for_byte_what_they_were():
    _check_sites_one_and_two_are_unchanged(SOURCE)


@pytest.mark.parametrize(
    "plant, label",
    [
        (_plant_touch_the_shared_helper, "the shared helper was edited"),
        (_plant_touch_site_one, "site 1's call was edited"),
        (_plant_touch_site_two, "site 2's call was edited"),
    ],
)
def test_control_the_unchanged_check_catches_a_planted_edit(plant, label):
    """CONTROL. Without this the three hashes could be stale constants
    that match nothing and pass anyway."""
    with pytest.raises(AssertionError) as caught:
        _check_sites_one_and_two_are_unchanged(plant(SOURCE))
    assert str(caught.value).strip(), label


# ─────────────────────────────────────────────────────────────────────
# THE RUNNING HARNESS — the real _execute_manual_rebalance
# ─────────────────────────────────────────────────────────────────────


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.events: list[tuple[str, dict]] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")
        self.events.append((topic, payload))

    def text(self) -> str:
        return "\n".join(self.messages)


class _Config:
    def __init__(self, fold_pct=100):
        self.scrum_fold_pct = fold_pct
        self.symbol = "BONK/USD"
        self.target_asset = "BONK"
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


class _Band:
    def __init__(self, lower, upper):
        self.lower = lower
        self.upper = upper


class _Order:
    id = "order-1"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last):
        self.last = last


def remnant(usd, units, ref, ibp, **extra) -> dict:
    """A part-spent tranche: what _settle_fold_plan leaves behind."""
    t = {
        "usd": usd,
        "units": units,
        "ref": ref,
        "initial_buy_price": ibp,
        "created_ts": 1.0,
        "fold_partial_spent": True,
    }
    t.update(extra)
    return t


def _manual_bot(
    *,
    tranches=None,
    lots=None,
    band=_Band(0.5, 1.5),
    fold_pct=100,
    holdings=1000.0,
    target=100.0,
    price=1.0,
):
    """A bot that runs the SHIPPING ``_execute_manual_rebalance``.

    Only the outward edges are stubbed: the exchange, the wire routing,
    the emitters. Everything between the sell and the tranche list is
    the shipping code. Every stub RECORDS what it was called with, so a
    test can read what the shipping code actually asked the outside
    world for and not only what it did afterwards.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "site3-bot"
    bot.seen = {
        "placed": [],
        "settled": [],
        "balances": [],
        "routed": [],
        "snapshots": [],
        "gates": [],
        "retained": [],
        "disarms": 0,
    }
    bot._bus = _Bus()
    bot.config = _Config(fold_pct)
    bot.stats = _Stats()
    bot._fold_tranches = list(tranches or [])
    bot._main_lots = [
        dict(lot)
        for lot in (
            lots if lots is not None else [{"units": 600.0, "initial_buy_price": 0.9}]
        )
    ]
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._tranches_created_lifetime = len(bot._fold_tranches)
    bot._fold_queue_usd = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._pending_wire_credits = 0.0
    bot._last_bb = band

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.seen["placed"].append(kwargs)
        return _Order()

    async def _settled(order, symbol, requested, tick_price):
        bot.seen["settled"].append((order.id, symbol, requested, tick_price))
        return requested, price, True

    async def _balance(currency):
        bot.seen["balances"].append(currency)
        return type("B", (), {"total": holdings, "free": holdings, "absent": False})()

    def _route(scrum_usd, sell_fill, label):
        bot.seen["routed"].append((scrum_usd, sell_fill, label))
        return 0.0

    def _snapshot(side, trade_action):
        bot.seen["snapshots"].append((side, trade_action))

    def _gate(side, trade_action):
        bot.seen["gates"].append((side, trade_action))

    def _retained(retained_usd):
        bot.seen["retained"].append(retained_usd)

    def _disarm():
        bot.seen["disarms"] += 1

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._route_scrum_proceeds_via_wires = _route
    bot._emit_voting_panel_snapshot_at_fire = _snapshot
    bot._emit_gate_decision_at_fire = _gate
    bot._reset_opposing_hysteresis_after_fill = _disarm
    bot.note_scrum_retention_usd = _retained
    return bot


def _fire(bot, price=1.0, intent="manual_button"):
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), intent))
    return bot._fold_tranches


def _never_merges(bot):
    """CONTROL BOT: the defect, reinstated. The site spawns and the
    merge never reaches it -- which is exactly what shipped."""
    bot._top_up_remnant_fold_tranches = lambda first_new_index, bb_lower, bb_upper: (
        0,
        0.0,
    )
    return bot


# The sale every behaviour check below runs: holdings 1000 at $1.00
# against a $100 target sells $900, and the single 600-unit lot prices
# one tranche at (600 / 900) x 900 = $600.
SALE_TRANCHE_USD = 600.0
SALE_TRANCHE_UNITS = 600.0


# ─────────────────────────────────────────────────────────────────────
# 4. A SITE-3 SPAWN MERGES INSTEAD OF ADDING A RECORD
# ─────────────────────────────────────────────────────────────────────


def _check_the_spawn_merges(make) -> None:
    """Read at the tranche list after a real fire."""
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = make(_manual_bot(tranches=[rem]))
    after = _fire(bot)
    if len(after) != 1:
        raise AssertionError(
            f"the fire left {len(after)} records. A spawn with an "
            f"eligible remnant must merge into it, leaving 1."
        )
    if after[0] is not rem:
        raise AssertionError("the surviving record is not the remnant")
    if abs(rem["usd"] - (10.0 + SALE_TRANCHE_USD)) > EXACT:
        raise AssertionError(
            f"the remnant holds ${rem['usd']!r}; the sale's "
            f"${SALE_TRANCHE_USD} did not go into it"
        )
    if abs(rem["units"] - (10.0 + SALE_TRANCHE_UNITS)) > EXACT:
        raise AssertionError(
            f"the remnant holds {rem['units']!r} units, not the "
            f"{10.0 + SALE_TRANCHE_UNITS} a merge would leave"
        )


def test_a_site3_spawn_merges_into_an_eligible_remnant():
    _check_the_spawn_merges(lambda bot: bot)


def test_control_without_the_merge_the_fire_adds_a_record():
    """CONTROL. This is the shipped defect, and it must go red."""
    with pytest.raises(AssertionError, match="left 2 records"):
        _check_the_spawn_merges(_never_merges)


@pytest.mark.parametrize("intent", ["manual_button", "wire_stack", "max_cartridge"])
def test_all_three_callers_merge_not_only_the_button(intent):
    """Two of the three fire without the operator."""
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = _manual_bot(tranches=[rem])
    after = _fire(bot, intent=intent)
    assert len(after) == 1, (
        f"{intent} left {len(after)} records; the gap was never " f"'manual only'"
    )
    assert rem["usd"] == pytest.approx(610.0)


def test_the_lifetime_created_counter_comes_back_down():
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = _manual_bot(tranches=[rem])
    before = bot._tranches_created_lifetime
    _fire(bot)
    assert bot._tranches_created_lifetime == before, (
        "the fire did not, in the end, open a record; leaving the "
        "count up breaks the created-versus-closed reconciliation"
    )


def test_the_operator_is_told_the_true_open_count():
    """The FILLED log must not claim records that were merged away."""
    bot = _manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)])
    _fire(bot)
    assert "0 tranche(s) queued" in bot._bus.text(), (
        "the fire merged its only tranche away but still reported it " "as queued"
    )
    assert (
        "FOLD TOP-UP:" in bot._bus.text()
    ), "nothing told the operator where the money went"


def test_the_derived_queue_scalar_matches_the_merged_list():
    bot = _manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)])
    after = _fire(bot)
    assert bot._fold_queue_usd == pytest.approx(sum(t["usd"] for t in after))


# ─────────────────────────────────────────────────────────────────────
# 5. THE LOWEST PRICED CANDIDATE INSIDE THE BAND RECEIVES IT
# ─────────────────────────────────────────────────────────────────────


def _check_lowest_priced_wins(pick) -> None:
    dear = remnant(10.0, 10.0, 1.2, 0.9)
    cheap = remnant(10.0, 10.0, 0.6, 0.9)
    bot = _manual_bot(tranches=[dear, cheap])
    _fire(bot)
    winner = pick(dear, cheap)
    if abs(winner["usd"] - 10.0) < 1e-12:
        raise AssertionError(
            f"the remnant at ref {winner['ref']} received nothing; "
            f"dear=${dear['usd']!r} cheap=${cheap['usd']!r}"
        )


def test_the_lowest_priced_remnant_in_the_band_receives_it():
    _check_lowest_priced_wins(lambda dear, cheap: cheap)


def test_control_expecting_the_dearest_to_win_goes_red():
    """CONTROL. The STACK side takes the highest; the FOLD side takes
    the lowest, and picking the wrong end is the mistake here."""
    with pytest.raises(AssertionError, match="received nothing"):
        _check_lowest_priced_wins(lambda dear, cheap: dear)


def test_a_remnant_outside_the_band_is_not_a_candidate():
    below = remnant(10.0, 10.0, 0.2, 0.9)
    inside = remnant(10.0, 10.0, 0.9, 0.9)
    bot = _manual_bot(tranches=[below, inside], band=_Band(0.5, 1.5))
    _fire(bot)
    assert below["usd"] == pytest.approx(
        10.0
    ), "a remnant below the band took the money anyway"
    assert inside["usd"] == pytest.approx(610.0)


def test_a_tranche_that_was_never_part_spent_is_not_a_candidate():
    whole = {
        "usd": 10.0,
        "units": 10.0,
        "ref": 0.8,
        "initial_buy_price": 0.9,
        "created_ts": 1.0,
    }
    bot = _manual_bot(tranches=[whole])
    after = _fire(bot)
    assert len(after) == 2, "a whole tranche must not absorb the sale"
    assert whole["usd"] == pytest.approx(10.0)


# ─────────────────────────────────────────────────────────────────────
# 6. A DIFFERENT initial_buy_price REFUSES THE MERGE  (MEM-171)
# ─────────────────────────────────────────────────────────────────────


def _check_a_different_floor_refuses(compare) -> None:
    """The incoming basis is 0.9, off the lot; the remnant's is 0.7."""
    rem = remnant(10.0, 10.0, 0.8, 0.7)
    bot = _manual_bot(tranches=[rem])
    after = _fire(bot)
    if not compare(len(after), rem):
        raise AssertionError(
            f"a remnant with floor {rem['initial_buy_price']} absorbed "
            f"a sale with floor 0.9. Averaging two floors raises the "
            f"floor on the cheaper units, which MEM-171 forbids; the "
            f"list is {len(after)} long and the remnant holds "
            f"${rem['usd']!r}"
        )


def test_a_different_initial_buy_price_refuses_the_merge():
    _check_a_different_floor_refuses(lambda n, rem: n == 2 and rem["usd"] == 10.0)


def test_control_a_tolerant_floor_match_would_go_red():
    """CONTROL. If the check were reading nothing, this inverted
    expectation would pass too."""
    with pytest.raises(AssertionError, match="MEM-171 forbids"):
        _check_a_different_floor_refuses(lambda n, rem: n == 1 and rem["usd"] > 10.0)


def test_the_merged_record_keeps_that_exact_floor():
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = _manual_bot(tranches=[rem])
    _fire(bot)
    assert (
        rem["initial_buy_price"] == 0.9
    ), "the surviving floor was rewritten by the merge"


# ─────────────────────────────────────────────────────────────────────
# 7. NO BAND MEANS NO MERGE, AND NO INVENTED BAND
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("band", [None, _Band(0.0, 0.0)])
def test_with_no_band_reading_nothing_merges(band):
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = _manual_bot(tranches=[rem], band=band)
    after = _fire(bot)
    assert len(after) == 2, (
        "with no band the fire must leave the sale where the build "
        "loop put it, not merge on a made-up range"
    )
    assert rem["usd"] == pytest.approx(10.0)


def test_a_bot_that_never_had_a_last_bb_attribute_still_fires():
    """`_last_bb` is set in __init__, but a restored or partially
    constructed bot must not crash the fire."""
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = _manual_bot(tranches=[rem])
    del bot._last_bb
    after = _fire(bot)
    assert len(after) == 2
    assert bot.stats.total_trades == 1, "the sale itself still happened"


# ─────────────────────────────────────────────────────────────────────
# 8. THE MERGE RUNS AFTER THE FOLD RATIO, NOT BEFORE
# ─────────────────────────────────────────────────────────────────────
#
# At scrum_fold_pct=50 the $600 tranche is halved to $300 and only that
# survives to merge, so the remnant ends at $310. Merging FIRST would
# move the whole $600 into the remnant, which sits outside the slice the
# ratio scales, and the remnant would end at $610 with the operator's
# setting having touched nothing. The two orders give different numbers,
# which is what makes this readable at all.


def _run_in_order(order) -> float:
    """Run the two shipping helpers in `order` on one starting state."""
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    fresh = {
        "usd": SALE_TRANCHE_USD,
        "units": SALE_TRANCHE_UNITS,
        "ref": 1.0,
        "initial_buy_price": 0.9,
        "created_ts": 1.0,
    }
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "order-bot"
    bot._bus = _Bus()
    bot.config = _Config(50)
    bot._fold_tranches = [rem, fresh]
    bot._tranches_created_lifetime = 2
    for step in order:
        if step == "ratio":
            bot._apply_scrum_fold_pct(1, 900.0, 900.0)
        else:
            bot._top_up_remnant_fold_tranches(1, 0.5, 1.5)
    return rem["usd"]


def test_the_shipping_order_puts_only_the_scaled_money_in_the_remnant():
    assert _run_in_order(("ratio", "merge")) == pytest.approx(310.0)


def test_control_merging_first_lets_the_money_escape_the_ratio():
    """CONTROL. The planted order, executed. It must produce a
    different, larger figure -- otherwise the assertion above is
    reading something that does not depend on the order."""
    escaped = _run_in_order(("merge", "ratio"))
    assert escaped == pytest.approx(610.0)
    assert escaped != pytest.approx(310.0)


def test_the_real_fire_produces_the_shipping_order_figure():
    """Read at the surface that matters: the real method."""
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    bot = _manual_bot(tranches=[rem], fold_pct=50)
    _fire(bot)
    assert rem["usd"] == pytest.approx(
        310.0
    ), "the fire merged money the fold ratio never got to scale"


# ─────────────────────────────────────────────────────────────────────
# 9. operator_initiated — PINNED, INCLUDING WHAT IT COSTS
# ─────────────────────────────────────────────────────────────────────


def _check_the_survivor_keeps_its_own_tag(make) -> None:
    """The older record survives, so ITS tag is the one that stands."""
    rem = remnant(10.0, 10.0, 0.8, 0.9, operator_initiated=False)
    bot = make(_manual_bot(tranches=[rem]))
    _fire(bot, intent="manual_button")
    if rem.get("operator_initiated") is not False:
        raise AssertionError(
            f"the surviving record's operator_initiated became "
            f"{rem.get('operator_initiated')!r}. A merge keeps the "
            f"OLDER record and must not rewrite its provenance from "
            f"the incoming one."
        )


def _copies_the_incoming_tag(bot):
    """PLANT: a merge that stamps the incoming tag on the survivor."""
    real = bot._top_up_remnant_fold_tranches

    def _tagged(first_new_index, bb_lower, bb_upper):
        incoming = [dict(t) for t in bot._fold_tranches[first_new_index:]]
        out = real(first_new_index, bb_lower, bb_upper)
        if out[0] and incoming:
            for t in bot._fold_tranches:
                t["operator_initiated"] = incoming[0].get("operator_initiated")
        return out

    bot._top_up_remnant_fold_tranches = _tagged
    return bot


def test_a_merge_keeps_the_older_records_tag():
    _check_the_survivor_keeps_its_own_tag(lambda bot: bot)


def test_control_a_merge_that_rewrote_the_tag_goes_red():
    """CONTROL. Proves the pin above actually reads the field."""
    with pytest.raises(AssertionError, match="operator_initiated"):
        _check_the_survivor_keeps_its_own_tag(_copies_the_incoming_tag)


def test_an_operator_fire_merged_into_an_autonomous_remnant_reads_auto():
    """THE COST, stated as a test rather than left to be discovered.

    The Fold Tranches "Source" column shows `operator_initiated` as
    "manual fire" or "auto scrum". After this merge the operator's money
    sits in a record that reads "auto scrum". Nothing gates on the
    field, and the trade log carries its own copy.
    """
    rem = remnant(10.0, 10.0, 0.8, 0.9)  # no tag at all: "auto scrum"
    bot = _manual_bot(tranches=[rem])
    after = _fire(bot, intent="manual_button")
    assert len(after) == 1
    assert not after[0].get(
        "operator_initiated"
    ), "pinned: the survivor reads as an autonomous record"
    filled = [p for topic, p in bot._bus.events if topic == "trade.filled"]
    assert filled, "no trade.filled emitted"
    assert filled[0]["data"]["operator_initiated"] is True, (
        "the TRADE attribution must survive the merge untouched; this "
        "is what v3.23.2 fixed and no merge may undo it"
    )


def test_a_manual_fire_merging_into_a_manual_remnant_keeps_the_label():
    """The common case. 389 of 515 live tranches carry the tag."""
    rem = remnant(10.0, 10.0, 0.8, 0.9, operator_initiated=True)
    bot = _manual_bot(tranches=[rem])
    after = _fire(bot, intent="manual_button")
    assert len(after) == 1
    assert after[0]["operator_initiated"] is True


@pytest.mark.parametrize(
    "intent, expected",
    [
        ("manual_button", True),
        ("wire_stack", False),
        ("max_cartridge", False),
    ],
)
def test_each_caller_still_emits_its_own_attribution(intent, expected):
    """The three tags stay distinct on the trade record, merge or not."""
    bot = _manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)])
    _fire(bot, intent=intent)
    filled = [p for topic, p in bot._bus.events if topic == "trade.filled"]
    assert filled[0]["data"]["operator_initiated"] is expected


# ─────────────────────────────────────────────────────────────────────
# 10. THE MERGE MOVES MONEY, IT DOES NOT MAKE OR LOSE ANY
# ─────────────────────────────────────────────────────────────────────


def test_total_queued_dollars_are_the_same_merged_or_not():
    rem_a = remnant(10.0, 10.0, 0.8, 0.9)
    rem_b = remnant(10.0, 10.0, 0.8, 0.9)
    merged = sum(t["usd"] for t in _fire(_manual_bot(tranches=[rem_a])))
    unmerged = sum(
        t["usd"] for t in _fire(_never_merges(_manual_bot(tranches=[rem_b])))
    )
    assert merged == pytest.approx(unmerged), "the merge is a move, not an adjustment"


def test_the_blended_ref_preserves_units_at_sale():
    """`asset_at_scrum` in the fold path is ``sum(usd / ref)``. The
    merged record must report what the two records reported apart."""
    rem = remnant(10.0, 10.0, 0.8, 0.9)
    before = 10.0 / 0.8 + SALE_TRANCHE_USD / 1.0
    bot = _manual_bot(tranches=[rem])
    _fire(bot)
    assert rem["usd"] / rem["ref"] == pytest.approx(before)


# ─────────────────────────────────────────────────────────────────────
# 11. THE SELL ITSELF IS UNTOUCHED BY THE MERGE
# ─────────────────────────────────────────────────────────────────────
#
# Read at the outward edges, from what each stub was CALLED with. The
# merge happens after the order is placed and settled, so it must not
# change the order, the routing, or anything the fire reports outward.


def test_the_merge_changes_nothing_the_fire_asks_the_outside_world():
    merged = _manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)])
    plain = _never_merges(_manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)]))
    _fire(merged)
    _fire(plain)

    assert merged.seen["placed"] == plain.seen["placed"], (
        "the order placed changed because of a merge that happens "
        "after the order is already filled"
    )
    assert merged.seen["settled"] == plain.seen["settled"]
    assert merged.seen["routed"] == plain.seen["routed"], (
        "Smart Wire routing runs before the build loop and must not "
        "see the merge at all"
    )
    assert merged.seen["retained"] == plain.seen["retained"]
    assert merged.seen["snapshots"] == plain.seen["snapshots"]
    assert merged.seen["gates"] == plain.seen["gates"]
    assert merged.seen["disarms"] == plain.seen["disarms"] == 1
    assert merged.stats.total_trades == plain.stats.total_trades == 1
    assert merged.stats.total_scrummed_usd == pytest.approx(
        plain.stats.total_scrummed_usd
    )


@pytest.mark.parametrize("intent", ["wire_stack", "max_cartridge"])
def test_the_autonomous_callers_still_verify_against_the_exchange(intent):
    """The 2026-08-09 BICO/IMU guard is upstream of the merge and
    stays there."""
    bot = _manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)])
    _fire(bot, intent=intent)
    assert bot.seen["balances"] == [
        "BONK"
    ], f"{intent} fired without reading the exchange balance"


def test_the_operator_button_is_still_exempt_from_that_check():
    bot = _manual_bot(tranches=[remnant(10.0, 10.0, 0.8, 0.9)])
    _fire(bot, intent="manual_button")
    assert bot.seen["balances"] == [], (
        "the operator-pressed path gained an exchange check it never " "had"
    )
