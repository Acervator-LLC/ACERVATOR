"""``scrum_fold_pct`` must mean the same thing on every selling path.

THE DEFECT
==========
``scrum_fold_pct`` is one operator setting. It decides how much of a
sale's proceeds queue for fold and how much is retired as cash. Three
places in ``scrumming_bot.py`` append to ``self._fold_tranches``, and the
setting was applied at exactly one of them:

* the autonomous SCRUM in ``tick`` -- APPLIED, and this is the reference,
* the DIST excess-distribution sell in ``tick`` -- NOT applied,
* ``_execute_manual_rebalance`` -- NOT applied.

That last site is not "the manual button". ``_INTENT_MAP`` routes three
callers through it and two of them fire autonomously: Wire Stack and Max
Cartridge. So a bot could sell all day, on paths the operator never
touched, with the ratio silently meaning nothing.

MEASURED, from the operator's filled sells 2026-06-09 to 2026-08-13:
276 of 380 (72.6%) ran an unscaled path. Across the eight bots that set
the value below 100, 95.6% of sell dollars bypassed it.

THE GOVERNING PRINCIPLE, operator 2026-08-12: "Functionality should be
mirrored between either side of the ladder."

TERMINAL ACTIONS ARE OUT OF SCOPE, and the code already agrees with the
operator's rule that "Detonations and Self-Destruct actions do not spawn
or populate tranches". ``_execute_detonation`` and ``self_destruct``
contain no statement that lengthens ``_fold_tranches``; they clear it.
``test_terminal_actions_build_no_tranche`` pins that, so a future edit
that gave a terminal action a tranche would have to face this file.

HOW THE FIX WORKS
=================
The reference arithmetic was MOVED, character for character, out of
``tick`` and into ``_apply_scrum_fold_pct``. All three sites call it.
Nothing was reimplemented, so the three cannot drift apart.

WHAT THIS FILE CHECKS, AND AT WHICH SURFACE
===========================================
1. The moved arithmetic is the pre-change arithmetic -- by the numbers
   it produces (a text/hash pin was removed as an antipattern).
2. Every site that appends a tranche calls it, after the append and
   before the top-up, with THAT site's own sale figures.
3. A manual fire and an autonomous scrum of the same sale leave the
   same tranches -- read off the tranche dicts after running the real
   ``_execute_manual_rebalance``.
4. At 100 nothing changes anywhere, which is 29 of the operator's 37
   bots.
5. Wired-in money is still exempt, still told apart by units.

EVERY CHECK CARRIES A PLANTED-DEFECT CONTROL
============================================
Each ``_check_*`` helper is run twice: on the shipping code, where it
must pass, and on a copy carrying a planted defect of the kind that
check exists to catch, where it must raise. A plant that no longer
matches the shipping text is an error, not a skip -- otherwise a stale
plant degrades into a green run and the control proves nothing.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import tempfile
import textwrap
from pathlib import Path

import pytest

from src.trading.scrumming_bot import ScrummingBot

# tests/conftest.py puts the repo root on sys.path at collection time,
# before any test module is imported, so this import needs no path
# juggling ahead of it and is therefore not a late import. The three
# lines that used to do the juggling here were what forced the E402
# suppression that sat on the import; both are gone.
REPO = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO / "src" / "trading" / "scrumming_bot.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")

# Money is compared to the bit. These vectors were produced by running
# the pre-change code, so an exact comparison is the honest one; a
# tolerance would hide precisely the drift this file exists to catch.
EXACT = 0.0

_BLOCK_START = "_fold_pct = max(0, min(100, int(getattr("
_BLOCK_END = "Cash buffer preserved against further drops."

# ── the pre-change record ────────────────────────────────────────────
#
# The behaviour is pinned by GOLDEN_PRE_CHANGE below (the old code's own
# numeric outputs), verified in test_the_shipping_method_reproduces_the_
# pre_change_numbers. A text/sha256 pin of the block used to sit here too;
# it was removed as an antipattern — hashing source couples the test to
# formatting, so an autoformat or refactor trips a false "behaviour changed"
# alarm. The numeric golden is the real oracle.

# name -> (scrum_usd, scrum_asset, tranche_count_before, tranches,
#          {fold_pct: ((usd, units), ...)})
GOLDEN_PRE_CHANGE = {
    # One lot, no wire credit. The plain case.
    "plain_single": (
        100.0,
        10.0,
        0,
        lambda: [{"usd": 100.0, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0}],
        {
            0: ((0.0, 0.0),),
            1: ((1.0, 0.1),),
            25: ((25.0, 2.5),),
            37: ((37.0, 3.7),),
            50: ((50.0, 5.0),),
            66: ((66.0, 6.6000000000000005),),
            99: ((99.0, 9.9),),
            100: ((100.0, 10.0),),
        },
    ),
    # Two lots from one sale. Scaling is per-tranche because each
    # carries its own MEM-171 initial_buy_price floor.
    "two_lots": (
        100.0,
        10.0,
        0,
        lambda: [
            {"usd": 60.0, "units": 6.0, "ref": 10.0, "initial_buy_price": 12.0},
            {"usd": 40.0, "units": 4.0, "ref": 10.0, "initial_buy_price": 8.0},
        ],
        {
            0: ((0.0, 0.0), (0.0, 0.0)),
            1: ((0.6, 0.06), (0.4, 0.04)),
            25: ((15.0, 1.5), (10.0, 1.0)),
            37: ((22.2, 2.2199999999999998), (14.8, 1.48)),
            50: ((30.0, 3.0), (20.0, 2.0)),
            66: ((39.6, 3.96), (26.400000000000002, 2.64)),
            99: ((59.4, 5.9399999999999995), (39.6, 3.96)),
            100: ((60.0, 6.0), (40.0, 4.0)),
        },
    ),
    # $343.68 of wired-in money absorbed into the tranche, the live
    # shape measured on bot 7c39c7a2. The $343.68 must survive every
    # percentage untouched; only the $100 of scrum proceeds scales.
    "absorbed_wire": (
        100.0,
        10.0,
        0,
        lambda: [{"usd": 443.68, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0}],
        {
            0: ((343.68, 0.0),),
            1: ((344.68, 0.1),),
            25: ((368.68, 2.5),),
            37: ((380.68, 3.7),),
            50: ((393.68, 5.0),),
            66: ((409.68, 6.6000000000000005),),
            99: ((442.68, 9.9),),
            100: ((443.68, 10.0),),
        },
    ),
    # No usable rate. The fallback treats everything as scrum proceeds
    # rather than inventing an exemption it cannot justify.
    "no_rate": (
        50.0,
        0.0,
        0,
        lambda: [{"usd": 50.0, "units": 0.0, "ref": 0.0, "initial_buy_price": 5.0}],
        {
            0: ((0.0, 0.0),),
            1: ((0.5, 0.0),),
            25: ((12.5, 0.0),),
            37: ((18.5, 0.0),),
            50: ((25.0, 0.0),),
            66: ((33.0, 0.0),),
            99: ((49.5, 0.0),),
            100: ((50.0, 0.0),),
        },
    ),
    # A tranche from an EARLIER sale is outside the slice and must not
    # be re-scaled; re-scaling it would corrupt its MEM-171 contract.
    "older_tranche_present": (
        100.0,
        10.0,
        1,
        lambda: [
            {"usd": 999.0, "units": 99.0, "ref": 3.0, "initial_buy_price": 3.0},
            {"usd": 100.0, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0},
        ],
        {
            0: ((999.0, 99.0), (0.0, 0.0)),
            1: ((999.0, 99.0), (1.0, 0.1)),
            25: ((999.0, 99.0), (25.0, 2.5)),
            37: ((999.0, 99.0), (37.0, 3.7)),
            50: ((999.0, 99.0), (50.0, 5.0)),
            66: ((999.0, 99.0), (66.0, 6.6000000000000005)),
            99: ((999.0, 99.0), (99.0, 9.9)),
            100: ((999.0, 99.0), (100.0, 10.0)),
        },
    ),
    # Un-round figures, built the way the shipping loop builds them, so
    # the dollars equal the units at the sale's rate to the last bit.
    # The 3.55e-15 at 0% is float noise the old code produced and the
    # new code must reproduce.
    "ragged_lots": (
        37.77,
        3.3333,
        0,
        lambda: [
            {
                "usd": (0.9805 / 3.3333) * 37.77,
                "units": 0.9805,
                "ref": 11.331,
                "initial_buy_price": 13.7,
            },
            {
                "usd": (2.3528 / 3.3333) * 37.77,
                "units": 2.3528,
                "ref": 11.331,
                "initial_buy_price": 9.02,
            },
        ],
        {
            0: ((0.0, 0.0), (3.552713678800501e-15, 0.0)),
            1: (
                (0.11110156601566017, 0.009805000000000001),
                (0.2665984339843434, 0.023527999999999997),
            ),
            25: ((2.777539150391504, 0.245125), (6.6649608496085, 0.5882)),
            37: (
                (4.110757942579426, 0.362785),
                (9.864142057420578, 0.8705359999999999),
            ),
            50: ((5.555078300783008, 0.49025), (13.329921699216996, 1.1764)),
            66: (
                (7.332703357033571, 0.6471300000000001),
                (17.595496642966435, 1.552848),
            ),
            99: (
                (10.999055035550356, 0.970695),
                (26.39324496444965, 2.3292719999999996),
            ),
            100: ((11.110156601566016, 0.9805), (26.65984339843399, 2.3528)),
        },
    ),
}


# ── stubs ────────────────────────────────────────────────────────────


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _Config:
    def __init__(self, fold_pct=100, symbol="BONK/USD", target="BONK"):
        self.scrum_fold_pct = fold_pct
        self.symbol = symbol
        self.target_asset = target
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


def _bare_bot(fold_pct, tranches):
    """The least bot ``_apply_scrum_fold_pct`` needs to run."""
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "test-bot"
    bot._bus = _Bus()
    bot._fold_tranches = tranches
    bot.config = _Config(fold_pct)
    return bot


# ── slicing the shipping arithmetic, for the planted controls ────────

_GENERATED = '''"""Generated at test time from the shipping source."""


def run(self, scrum_usd, scrum_asset, _tranche_count_before):
{body}
'''


class StalePlant(RuntimeError):
    """A plant no longer matches the shipping text.

    DELIBERATELY NOT AN ``AssertionError``. Every control below is
    written as ``pytest.raises(AssertionError)``, so if a stale plant
    raised one, the control would go GREEN for the wrong reason -- the
    check would never have run and nothing would say so. A distinct
    type makes a stale plant an ERROR that has to be fixed.
    """


def _block_source() -> str:
    """The fold-ratio block, verbatim and dedented to column 0."""
    lines = SOURCE.splitlines()
    starts = [i for i, ln in enumerate(lines) if _BLOCK_START in ln]
    ends = [i for i, ln in enumerate(lines) if _BLOCK_END in ln]
    if len(starts) != 1:
        raise StalePlant(
            f"expected one fold-ratio block start, found {len(starts)}. "
            f"Fix the anchors, do not delete the test."
        )
    if len(ends) != 1 or ends[0] <= starts[0]:
        raise StalePlant(f"fold-ratio block end is wrong: starts={starts} ends={ends}")
    # The end anchor marks the block's last logical line -- the fold-ratio
    # operator log. That log statement is wrapped across several physical lines
    # (``self._bus.emit(..., message=(...))``), so the anchor line can fall
    # inside the still-open call. Extend forward until the dedented block is a
    # complete parse, so log-wrapping churn can never truncate it mid-statement.
    end = ends[0]
    while True:
        block = textwrap.dedent("\n".join(lines[starts[0] : end + 1]))
        try:
            ast.parse(block)
            break
        except SyntaxError:
            end += 1
            if end >= len(lines):
                raise StalePlant("fold-ratio block never closes after its anchor")
    if not block.startswith("_fold_pct"):
        raise StalePlant("dedent did not land the block at column 0; indentation moved")
    return block


def _load_block(*mutations: tuple[str, str]):
    """Compile the shipping block, optionally carrying a planted defect."""
    block = _block_source()
    for old, new in mutations:
        if old not in block:
            raise StalePlant(
                f"planted defect does not match the shipping source: "
                f"{old!r}. The control cannot fire, so it proves nothing."
            )
        block = block.replace(old, new)
    text = _GENERATED.format(body=textwrap.indent(block, "    "))
    holder = tempfile.TemporaryDirectory()
    path = Path(holder.name) / "sliced_fold_block.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("sliced_fold_block", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._holder = holder
    return module.run


# The defect this whole unit is about, expressed inside the arithmetic:
# ignore the setting and queue everything.
PLANT_IGNORE_THE_SETTING = (("_fold_frac = _fold_pct / 100.0", "_fold_frac = 1.0"),)
# Scale the summed usd, wire credit included -- the ISLAND_ABSORBFIX
# defect, replanted here because the exemption must survive the move.
PLANT_SCALE_WIRED_MONEY = (
    (
        '_t["usd"] = _wire_usd + _scrummed_usd * _fold_frac',
        '_t["usd"] = _full_usd * _fold_frac',
    ),
)
# Leave units alone: the queue would then hold more units than dollars.
PLANT_UNITS_UNSCALED = (
    ('_t["units"] = _full_units * _fold_frac', '_t["units"] = _full_units'),
)
# Re-scale every tranche, not just this sale's.
PLANT_RESCALE_OLD_TRANCHES = (
    (
        "_new_tranches = self._fold_tranches[_tranche_count_before:]",
        "_new_tranches = self._fold_tranches[0:]",
    ),
)


# ── check 1: the arithmetic is the pre-change arithmetic ─────────────


def _check_goldens(apply_fold) -> None:
    """Every recorded pre-change output must be reproduced exactly.

    ``apply_fold(bot, count_before, scrum_usd, scrum_asset)`` runs the
    thing under test. Read at the tranche dict, because that dict is
    the money.
    """
    for name, (usd, asset, before, factory, table) in GOLDEN_PRE_CHANGE.items():
        for pct, expected in table.items():
            tranches = factory()
            bot = _bare_bot(pct, tranches)
            apply_fold(bot, before, usd, asset)
            got = tuple((t["usd"], t["units"]) for t in tranches)
            if len(got) != len(expected):
                raise AssertionError(
                    f"{name} at {pct}%: tranche count changed, "
                    f"{len(expected)} -> {len(got)}"
                )
            for index, (want, have) in enumerate(zip(expected, got)):
                if abs(want[0] - have[0]) > EXACT:
                    raise AssertionError(
                        f"{name} at {pct}%, tranche {index}: usd was "
                        f"{want[0]!r} before the change and is {have[0]!r} "
                        f"now"
                    )
                if abs(want[1] - have[1]) > EXACT:
                    raise AssertionError(
                        f"{name} at {pct}%, tranche {index}: units were "
                        f"{want[1]!r} before the change and are {have[1]!r} "
                        f"now"
                    )


def _apply_via_method(bot, before, usd, asset):
    bot._apply_scrum_fold_pct(before, usd, asset)


def _apply_via(run):
    def _inner(bot, before, usd, asset):
        run(bot, usd, asset, before)

    return _inner


def test_the_shipping_method_reproduces_the_pre_change_numbers():
    """The autonomous path's behaviour is unchanged, measured."""
    _check_goldens(_apply_via_method)


def test_the_sliced_block_matches_the_method():
    """The plants below act on the slice, so the slice must be live."""
    _check_goldens(_apply_via(_load_block()))


@pytest.mark.parametrize(
    "plant, label",
    [
        (PLANT_IGNORE_THE_SETTING, "queue everything regardless of the setting"),
        (PLANT_SCALE_WIRED_MONEY, "scale wired-in money too"),
        (PLANT_UNITS_UNSCALED, "leave units unscaled"),
        (PLANT_RESCALE_OLD_TRANCHES, "re-scale earlier sales' tranches"),
    ],
)
def test_control_the_goldens_catch_a_planted_defect(plant, label):
    """CONTROL. Each plant must turn the golden check red."""
    with pytest.raises(AssertionError) as caught:
        _check_goldens(_apply_via(_load_block(*plant)))
    assert str(caught.value).strip(), (
        f"the plant '{label}' failed without saying what changed; a "
        f"control that cannot be read is not evidence"
    )


# ── check 2: every build site is wired to it ─────────────────────────

TARGET_LIST = "_fold_tranches"
FOLD_CALL = "_apply_scrum_fold_pct"
TOPUP_CALL = "_top_up_remnant_fold_tranches"


def _self_attr(node, name) -> bool:
    if isinstance(node, ast.Subscript):
        node = node.value
    return (
        isinstance(node, ast.Attribute)
        and node.attr == name
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _functions(tree):
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _grows_the_list(node) -> bool:
    """True for every way a statement can LENGTHEN the tranche list.

    A grep for ``.append`` is blind to four of the five, and the fifth
    would be the one somebody used.
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


def _self_calls(func, name):
    out = []
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == name
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            out.append(node)
    return out


def _sale_figures(func, build_line, floor):
    """The (usd, asset) names the build loop divided, for this site.

    The shipping loops all price a tranche as
    ``(take / asset) * usd``. That expression is the ONLY place the
    sale's own rate appears, and passing anything else to the helper
    would make the wired-in-money split read the wrong rate.
    """
    best = None
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign) or node.lineno >= build_line:
            continue
        if node.lineno <= floor:
            continue
        value = node.value
        if (
            isinstance(value, ast.BinOp)
            and isinstance(value.op, ast.Mult)
            and isinstance(value.left, ast.BinOp)
            and isinstance(value.left.op, ast.Div)
            and isinstance(value.left.right, ast.Name)
            and isinstance(value.right, ast.Name)
        ):
            if best is None or node.lineno > best[0]:
                best = (node.lineno, value.right.id, value.left.right.id)
    return None if best is None else (best[1], best[2])


def _check_every_site_is_wired(source: str) -> None:
    """Each tranche-building site scales, in the right order, on its
    own sale's figures."""
    tree = ast.parse(source)
    sites = []
    for func in _functions(tree):
        lines = sorted({n.lineno for n in ast.walk(func) if _grows_the_list(n)})
        for index, line in enumerate(lines):
            nxt = lines[index + 1] if index + 1 < len(lines) else 10**9
            prev = lines[index - 1] if index else func.lineno
            sites.append((func, line, prev, nxt))

    if not sites:
        raise AssertionError(
            "no tranche-building site found at all; the walker is blind"
        )

    for func, line, prev, nxt in sites:
        folds = [c for c in _self_calls(func, FOLD_CALL) if line < c.lineno < nxt]
        if not folds:
            raise AssertionError(
                f"{func.name} appends a fold tranche at line {line} and "
                f"never applies scrum_fold_pct to it. Every path that "
                f"builds a tranche must scale it the way the autonomous "
                f"scrum does."
            )
        fold = min(folds, key=lambda c: c.lineno)

        tops = [c for c in _self_calls(func, TOPUP_CALL) if line < c.lineno < nxt]
        if tops and min(t.lineno for t in tops) < fold.lineno:
            raise AssertionError(
                f"{func.name}: the top-up at line "
                f"{min(t.lineno for t in tops)} runs before the "
                f"scrum_fold_pct call at {fold.lineno}. The top-up moves "
                f"this sale's money into an older tranche, outside the "
                f"slice, where the ratio can no longer reach it."
            )

        figures = _sale_figures(func, line, prev)
        if figures is None:
            raise AssertionError(
                f"{func.name}: could not find the `(take / asset) * usd` "
                f"pricing for the site at line {line}"
            )
        usd_name, asset_name = figures
        if len(fold.args) != 3:
            raise AssertionError(
                f"{func.name}: scrum_fold_pct call takes "
                f"{len(fold.args)} positional arguments, expected 3"
            )
        got = tuple(
            a.id if isinstance(a, ast.Name) else ast.dump(a) for a in fold.args[1:]
        )
        if got != (usd_name, asset_name):
            raise AssertionError(
                f"{func.name}: the site at line {line} priced its "
                f"tranches with ({usd_name} / {asset_name}) but passes "
                f"{got} to scrum_fold_pct. The helper would read a "
                f"different rate than the tranches were built at, and "
                f"the wired-in-money split would be wrong."
            )


def _plant_drop_one_call(source: str) -> str:
    old = (
        "            self._apply_scrum_fold_pct(\n"
        "                _manual_tranche_count_before, fill_usd, fill_amount\n"
        "            )"
    )
    if old not in source:
        raise StalePlant("plant no longer matches the shipping source")
    return source.replace(old, "            pass")


def _plant_swap_the_rate(source: str) -> str:
    old = "                            _dist_tranche_count_before, dist_usd, dist_asset"
    if old not in source:
        raise StalePlant("plant no longer matches the shipping source")
    return source.replace(
        old,
        "                            _dist_tranche_count_before, dist_asset, dist_usd",
    )


def _plant_reorder_against_the_topup(source: str) -> str:
    """Move the DIST scaling call to AFTER the top-up."""
    lines = source.split("\n")
    tree = ast.parse(source)
    func = next(f for f in _functions(tree) if f.name == "tick")
    fold = max(_self_calls(func, FOLD_CALL), key=lambda c: c.lineno)
    top = max(_self_calls(func, TOPUP_CALL), key=lambda c: c.lineno)
    if not fold.lineno < top.lineno:
        raise StalePlant("plant expects the DIST scaling call to precede its top-up")
    fold_text = lines[fold.lineno - 1 : fold.end_lineno]
    top_text = lines[top.lineno - 1 : top.end_lineno]
    lines[fold.lineno - 1 : top.end_lineno] = top_text + fold_text
    return "\n".join(lines)


def _plant_a_fourth_unscaled_site(source: str) -> str:
    anchor = "    def clear_fold_tranches("
    if anchor not in source:
        raise StalePlant("plant anchor is gone from the source")
    new_method = (
        "    def _rogue_builder(self, take, sale_asset, sale_usd):\n"
        "        t_usd = (take / sale_asset) * sale_usd\n"
        '        self._fold_tranches.append({"usd": t_usd})\n'
        "\n"
    )
    return source.replace(anchor, new_method + anchor, 1)


def test_every_tranche_building_site_applies_the_setting():
    """The mirroring claim itself, checked on the shipping source."""
    _check_every_site_is_wired(SOURCE)


@pytest.mark.parametrize(
    "plant, label",
    [
        (_plant_drop_one_call, "a site stops applying the setting"),
        (_plant_swap_the_rate, "a site passes the wrong rate"),
        (_plant_reorder_against_the_topup, "the top-up runs first"),
        (_plant_a_fourth_unscaled_site, "a new unscaled site appears"),
    ],
)
def test_control_the_wiring_check_catches_a_planted_defect(plant, label):
    """CONTROL. Each plant must turn the wiring check red."""
    with pytest.raises(AssertionError) as caught:
        _check_every_site_is_wired(plant(SOURCE))
    assert str(caught.value).strip(), (
        f"the plant '{label}' failed without saying what changed; a "
        f"control that cannot be read is not evidence"
    )


def test_terminal_actions_build_no_tranche():
    """The operator's rule: detonation and self-destruct are terminal.

    "Detonations and Self-Destruct actions do not spawn or populate
    tranches. These two are considered 'terminal actions'." The code
    agrees, so there is nothing here to scale. This pins it, because a
    terminal action that grew a tranche would need scaling and would
    otherwise slip past the wiring check as a new site.
    """
    tree = ast.parse(SOURCE)
    for name in ("_execute_detonation", "self_destruct"):
        func = next(f for f in _functions(tree) if f.name == name)
        grew = [n.lineno for n in ast.walk(func) if _grows_the_list(n)]
        assert grew == [], (
            f"{name} lengthens the fold-tranche list at {grew}, but the "
            f"operator's rule says terminal actions neither spawn nor "
            f"populate tranches"
        )


# ── check 3: a manual fire scales the way an autonomous scrum does ───


class _Order:
    id = "order-1"
    filled = 0.0
    average = 0.0


def _manual_bot(
    fold_pct, *, holdings=1000.0, target=100.0, price=1.0, lots=None, wire_out=0.0
):
    """A bot that can run the real ``_execute_manual_rebalance``.

    Only the outward edges are stubbed -- the exchange, the wire
    routing, the emitters. Everything between the sell and the tranche
    list is the shipping code. Every stub RECORDS its arguments, so a
    test can read what the shipping code actually asked for rather than
    only what it did afterwards.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "manual-bot"
    bot.seen = {"placed": None, "settled": None, "balances": [], "routed": []}
    bot._bus = _Bus()
    bot.config = _Config(fold_pct)
    bot.stats = _Stats()
    bot._fold_tranches = []
    bot._main_lots = (
        lots
        if lots is not None
        else [
            {"units": 600.0, "initial_buy_price": 0.9},
            {"units": 600.0, "initial_buy_price": 0.7},
        ]
    )
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._tranches_created_lifetime = 0
    bot._fold_queue_usd = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._pending_wire_credits = 0.0

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.seen["placed"] = kwargs
        return _Order()

    async def _settled(order, symbol, requested, tick_price):
        bot.seen["settled"] = (order.id, symbol, requested, tick_price)
        return requested, price, True

    async def _balance(currency):
        bot.seen["balances"].append(currency)
        return type("B", (), {"total": holdings, "free": holdings, "absent": False})()

    def _route(scrum_usd, sell_fill, label):
        bot.seen["routed"].append((scrum_usd, sell_fill, label))
        return wire_out

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._route_scrum_proceeds_via_wires = _route

    def _snapshot(side, trade_action):
        bot.seen.setdefault("snapshots", []).append((side, trade_action))

    def _gate(side, trade_action):
        bot.seen.setdefault("gates", []).append((side, trade_action))

    def _retained(retained_usd):
        bot.seen.setdefault("retained", []).append(retained_usd)

    bot._emit_voting_panel_snapshot_at_fire = _snapshot
    bot._emit_gate_decision_at_fire = _gate
    bot._reset_opposing_hysteresis_after_fill = lambda: bot.seen.setdefault(
        "disarms", []
    ).append(True)
    bot.note_scrum_retention_usd = _retained
    return bot


class _Ticker:
    def __init__(self, last):
        self.last = last


def _fire_manual(bot, price=1.0, intent="manual_button"):
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), intent))
    return [(t["usd"], t["units"]) for t in bot._fold_tranches]


def _reference_for_the_same_sale(fold_pct, sale_usd, sale_units, lots):
    """What the autonomous path would leave, for the same sale.

    Built by running the shipping build-and-scale sequence: the same
    highest-price-first split, then the same helper.
    """
    lots = [dict(lot) for lot in lots]
    lots.sort(key=lambda lot: lot["initial_buy_price"], reverse=True)
    tranches = []
    remaining = sale_units
    for lot in list(lots):
        if remaining <= 1e-12:
            break
        take = min(lot["units"], remaining)
        tranches.append(
            {
                "usd": (take / sale_units) * sale_usd,
                "units": take,
                "ref": sale_usd / sale_units,
                "initial_buy_price": lot["initial_buy_price"],
            }
        )
        remaining -= take
    bot = _bare_bot(fold_pct, tranches)
    bot._apply_scrum_fold_pct(0, sale_usd, sale_units)
    return [(t["usd"], t["units"]) for t in tranches]


def _check_manual_matches_the_reference(bot_factory, fold_pct) -> None:
    """Read at the tranche list after a real manual fire."""
    lots = [
        {"units": 600.0, "initial_buy_price": 0.9},
        {"units": 600.0, "initial_buy_price": 0.7},
    ]
    bot = bot_factory(fold_pct, lots=[dict(lot) for lot in lots])
    got = _fire_manual(bot)
    # holdings 1000 at $1.00 against a $100 target sells $900 of units.
    want = _reference_for_the_same_sale(fold_pct, 900.0, 900.0, lots)
    if len(got) != len(want):
        raise AssertionError(
            f"manual fire produced {len(got)} tranches, the autonomous "
            f"path produces {len(want)} for the same sale"
        )
    for index, (have, expect) in enumerate(zip(got, want)):
        if abs(have[0] - expect[0]) > EXACT:
            raise AssertionError(
                f"tranche {index}: manual fire queued ${have[0]!r} but an "
                f"autonomous scrum of the same sale queues ${expect[0]!r} "
                f"at scrum_fold_pct={fold_pct}"
            )
        if abs(have[1] - expect[1]) > EXACT:
            raise AssertionError(
                f"tranche {index}: manual fire queued {have[1]!r} units, "
                f"autonomous queues {expect[1]!r}"
            )


def _unscaled_manual_bot(fold_pct, **kwargs):
    """CONTROL BOT: the defect, reinstated. The site builds tranches and
    the setting never reaches them -- which is exactly what shipped."""
    bot = _manual_bot(fold_pct, **kwargs)

    def _never_applied(before, usd, asset):
        bot.seen.setdefault("skipped", []).append((before, usd, asset))

    bot._apply_scrum_fold_pct = _never_applied
    return bot


@pytest.mark.parametrize("fold_pct", [0, 1, 25, 50, 66, 99])
def test_a_manual_fire_scales_like_an_autonomous_scrum(fold_pct):
    """The defect this unit exists to remove."""
    _check_manual_matches_the_reference(_manual_bot, fold_pct)


@pytest.mark.parametrize("fold_pct", [0, 1, 25, 50, 66, 99])
def test_control_the_manual_check_catches_the_unscaled_path(fold_pct):
    """CONTROL. With the setting not reaching the tranches -- which is
    exactly what shipped before -- the check must go red."""
    with pytest.raises(AssertionError):
        _check_manual_matches_the_reference(_unscaled_manual_bot, fold_pct)


@pytest.mark.parametrize("intent", ["wire_stack", "max_cartridge"])
def test_the_autonomous_callers_of_the_manual_method_scale_too(intent):
    """Two of the three callers fire without the operator.

    Wire Stack and Max Cartridge run the same method, so the gap was
    never "manual only". They must scale as well.
    """
    bot = _manual_bot(50)
    got = _fire_manual(bot, intent=intent)
    assert got, f"{intent} built no tranche; the fire did not reach the build"
    total = sum(usd for usd, _ in got)
    assert abs(total - 450.0) <= 1e-9, (
        f"{intent} queued ${total:.4f} of a $900 sale at "
        f"scrum_fold_pct=50; expected $450.00"
    )


# ── check 4: at 100 nothing changes ──────────────────────────────────


def _check_hundred_is_a_no_op(apply_fold) -> None:
    """A bot at 100 -- 29 of the operator's 37 -- must see no change."""
    for name, (usd, asset, before, factory, _table) in GOLDEN_PRE_CHANGE.items():
        tranches = factory()
        untouched = [(t["usd"], t["units"]) for t in tranches]
        bot = _bare_bot(100, tranches)
        apply_fold(bot, before, usd, asset)
        got = [(t["usd"], t["units"]) for t in tranches]
        if got != untouched:
            raise AssertionError(
                f"{name}: scrum_fold_pct=100 changed the tranches from "
                f"{untouched} to {got}"
            )
        if bot._bus.messages:
            raise AssertionError(
                f"{name}: scrum_fold_pct=100 emitted {bot._bus.messages}; "
                f"the default must be silent as well as inert"
            )


def test_a_bot_at_one_hundred_percent_sees_no_change():
    _check_hundred_is_a_no_op(_apply_via_method)


def test_control_the_hundred_percent_check_catches_a_planted_defect():
    """CONTROL. Make the gate run at 100 and the check must go red."""
    with pytest.raises(AssertionError):
        _check_hundred_is_a_no_op(
            _apply_via(
                _load_block(
                    (
                        "if _fold_pct < 100 and _new_tranches:",
                        "if _fold_pct <= 100 and _new_tranches:",
                    )
                )
            )
        )


def test_a_manual_fire_at_one_hundred_percent_queues_the_whole_sale():
    """The same no-op, read at the end of a real manual fire."""
    bot = _manual_bot(100)
    got = _fire_manual(bot)
    total = sum(usd for usd, _ in got)
    assert (
        abs(total - 900.0) <= 1e-9
    ), f"a $900 manual sale at scrum_fold_pct=100 queued ${total:.4f}"
    assert sum(units for _, units in got) == pytest.approx(900.0)


# ── check 5: wired-in money is still exempt, told apart by units ─────


def _check_wire_credit_survives(apply_fold) -> None:
    """Money another bot earned is not the operator's to retire here.

    It is told apart BY UNITS: the absorb adds dollars and no units, so
    whatever a tranche holds above its units at the sale's own rate was
    wired in. The pool must come out whole at every percentage.
    """
    parked = 343.68
    for pct in range(0, 100):
        tranches = [
            {
                "usd": 100.0 + parked,
                "units": 10.0,
                "ref": 10.0,
                "initial_buy_price": 8.0,
            }
        ]
        bot = _bare_bot(pct, tranches)
        apply_fold(bot, 0, 100.0, 10.0)
        kept = tranches[0]["usd"]
        expected = parked + 100.0 * (pct / 100.0)
        if abs(kept - expected) > 1e-9:
            raise AssertionError(
                f"at scrum_fold_pct={pct} the tranche holds ${kept:.6f}; "
                f"${parked:.2f} of wired-in money plus ${100.0 * pct / 100:.6f} "
                f"of scrum proceeds is ${expected:.6f}. "
                f"${expected - kept:.6f} of another bot's money was "
                f"retired as cash."
            )


def test_wired_in_money_is_still_exempt():
    """Swept over the whole 0..99 domain, not a hand-written table."""
    _check_wire_credit_survives(_apply_via_method)


def test_control_the_wire_check_catches_the_pre_absorbfix_defect():
    """CONTROL. Scale the summed usd and the check must go red."""
    with pytest.raises(AssertionError):
        _check_wire_credit_survives(_apply_via(_load_block(*PLANT_SCALE_WIRED_MONEY)))


def test_the_manual_path_reads_this_sales_own_rate():
    """A wire credit sitting on a manual fire's tranche survives.

    The manual site prices its tranches at ``fill_usd / fill_amount``
    and hands the helper those same two figures, so a tranche's own
    dollars are exactly its units at that rate and anything above them
    is recognised as wired in. Passing any other rate would misclassify
    the split; this reads the result at the tranche.
    """
    bot = _manual_bot(50)
    parked = 40.0
    original_apply = bot._apply_scrum_fold_pct

    def _absorb_then_apply(before, usd, asset):
        # Stand in for _absorb_pending_wire_credits_into: dollars, and
        # no units, added to the first tranche this fire built.
        bot._fold_tranches[before]["usd"] += parked
        original_apply(before, usd, asset)

    bot._apply_scrum_fold_pct = _absorb_then_apply
    got = _fire_manual(bot)
    total = sum(usd for usd, _ in got)
    assert abs(total - (450.0 + parked)) <= 1e-9, (
        f"a $900 manual sale at 50% with ${parked:.2f} of wired-in money "
        f"left ${total:.4f} queued; expected ${450.0 + parked:.2f}. The "
        f"wired-in money was scaled."
    )


def test_the_operator_is_told_what_happened_on_a_manual_fire():
    """The FOLD RATIO line is the operator's only signal that the
    setting acted. It was absent on this path before the change."""
    bot = _manual_bot(50)
    _fire_manual(bot)
    ratio_lines = [m for m in bot._bus.messages if "FOLD RATIO" in m]
    assert len(ratio_lines) == 1, (
        f"expected one FOLD RATIO line after a manual fire at 50%, got "
        f"{ratio_lines}"
    )
    assert "scrum_fold_pct=50%" in ratio_lines[0]
