"""Absorbed wire credit must not be scaled by ``scrum_fold_pct``.

THE DEFECT
==========
At the scrum tranche-build site in ``tick()`` the order of operations was
absorb-then-skim:

* ``_absorb_pending_wire_credits_into`` adds the WHOLE parked pool to the
  first new tranche's ``usd``.
* the fold-ratio block then slices ``_fold_tranches[_tranche_count_before:]``
  -- and because the absorb only runs when ``_tranche_count_before == 0``,
  that slice always contains the tranche just absorbed into.
* the loop wrote ``_t["usd"] = _full_usd * _fold_frac``.

So on any bot with ``scrum_fold_pct < 100``, money that another bot earned,
that a Smart Wire routed here, and that was merely PARKED because this bot
had no tranche to receive it, was scaled down by the scrum fold ratio and
the remainder retired as cash. ``scrum_fold_pct`` decides how much of a
SCRUM'S OWN PROCEEDS fold back. It has no authority over wired-in money.

MEASURED LIVE EXPOSURE (read-only copy of ``bot_state.json``, saved
2026-08-11 20:33, 37 bots): $363.01 parked fleet-wide, 8 of 37 bots at
``scrum_fold_pct < 100``, and bot 7c39c7a2 (BTC/USD) holding $343.68 parked
with zero fold tranches at ``scrum_fold_pct=50``.

HOW THE FIX TELLS THE TWO APART, AND WHY NOT BY PROVENANCE
==========================================================
By UNITS. The build loop prices every tranche at
``(_take / scrum_asset) * scrum_usd``, so a tranche's scrummed dollars are
exactly its units at this scrum's own net rate. The absorb adds USD and no
units. Whatever a tranche holds above its units at that rate was wired in.

Reading the ``wire_credits`` provenance instead is the obvious answer and
it is WRONG ON REAL DATA. ``pending_wire_ledger`` was not persisted before
v3.24.49, so every restart before that fix kept the parked total and
dropped its itemisation. Measured on the same live copy:

    bot        parked      ledger sum   gap
    7c39c7a2   $343.68     $1.43        $342.26
    5d335c96   $13.34      $1.56        $11.78
    c8e5c5db   $4.49       $4.49        $0.00
    7c4c4ff3   $1.50       $1.50        $0.00

Exempting the RECORDED amount would have rescued $0.71 of 7c39c7a2's
$171.84 and retired the other $171.13 -- a fix that reads correct, cites
real lines, and does almost nothing.
``test_the_live_ledger_gap_does_not_defeat_the_fix`` pins that case with
the measured numbers, and its control is the provenance-based fix itself:
plant it and the test goes red by $171.13.

WHY THESE TESTS RUN THE SHIPPING SOURCE
=======================================
The block lives inside ``tick()``, a 4,400-line async method with no seam,
so there is no function to call. Re-implementing the arithmetic in the test
would be the instrument agreeing with itself -- the classic oracle false
negative. Instead each test SLICES THE REAL BLOCK out of
``src/trading/scrumming_bot.py`` and runs those exact bytes against a stub
bot. The planted-defect controls prove the slice is live: every one of them
mutates the shipping text and is required to turn an assertion red.

The absorb half needs no slicing -- ``_absorb_pending_wire_credits_into``
and ``_add_wire_credits`` are real methods and are called as such, so the
absorb -> exemption chain runs end to end on real code.

EVERY CHECK HERE CARRIES A PLANTED-DEFECT CONTROL
=================================================
Each ``_check_*`` helper is called twice: once on the clean shipping block,
where it must pass, and once on a block carrying a planted defect of the
kind that check exists to catch, where it must raise. Both readings are
taken at the same surface -- the tranche dict's ``usd`` and ``units``, and
the operator log -- because that is what the money and the operator see.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import sys
import tempfile
import textwrap
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SCRUMMING_BOT_SRC = (
    REPO / "src" / "trading" / "scrumming" / "fold_tranches.py"
).read_text(encoding="utf-8")

# The defect signal this suite must be able to see is at its smallest when
# the parked pool is smallest and the fold percentage is highest: at
# $0.01 parked and scrum_fold_pct=99 the pre-fix code mis-routes $0.0001.
# The comparison tolerance below is 1e-9 -- five orders of magnitude
# smaller -- so it cannot hide the defect. It is above float64's ~1e-11
# absolute error at the largest magnitude swept ($99,999.99), so it does
# not manufacture failures either. THIS NUMBER IS PART OF THE CHECK. Do
# not widen it to make a failing case pass.
MONEY_TOL_USD = 1e-9

_BLOCK_START = "_fold_pct = max(0, min(100, int(getattr("
_BLOCK_END = "Cash buffer preserved against further drops."

_GENERATED_MODULE = '''"""Generated at test time from the shipping source.

The body below is a verbatim slice of the scrum fold-ratio block in
``ScrummingBot.tick``. Do not edit this file; edit the source.
"""


def run_shipped_fold_block(self, scrum_usd, scrum_asset,
                           _tranche_count_before):
{body}
'''


# ── slicing the shipping block ───────────────────────────────────


def _fold_block_source() -> str:
    """Return the scrum fold-ratio block, verbatim and dedented.

    The end anchor marks the block's last *logical* line -- the fold-ratio
    operator log. That log statement is wrapped across several physical lines
    in the shipping source (``self._bus.emit(..., message=(...))``), so the
    anchor line itself can fall inside the still-open call. Extend the slice
    forward from the anchor until the dedented block is a complete parse --
    i.e. every bracket the log statement opened has closed -- so churn in how
    the message is wrapped can never truncate the block mid-statement.
    """
    lines = SCRUMMING_BOT_SRC.splitlines()
    starts = [i for i, line in enumerate(lines) if _BLOCK_START in line]
    ends = [i for i, line in enumerate(lines) if _BLOCK_END in line]
    assert len(starts) == 1, (
        f"expected exactly one fold-ratio block start; found {len(starts)}. "
        f"The slice anchors no longer identify one block -- fix the anchors, "
        f"do not delete the test."
    )
    assert (
        len(ends) == 1
    ), f"expected exactly one fold-ratio block end; found {len(ends)}"
    assert ends[0] > starts[0], "fold-ratio block end precedes its start"
    end = ends[0]
    while True:
        block = textwrap.dedent("\n".join(lines[starts[0] : end + 1]))
        try:
            ast.parse(block)
            break
        except SyntaxError:
            end += 1
            assert end < len(lines), (
                "fold-ratio block never closes after its end anchor; the log "
                "statement's brackets stay unbalanced to end of file -- fix "
                "the anchors, do not delete the test."
            )
    assert block.startswith("_fold_pct"), (
        "dedent did not land the block at column 0; the source indentation " "changed"
    )
    return block


def _load_block(*mutations: tuple[str, str]):
    """Import the shipping block as a callable, optionally with a plant.

    Each mutation must MATCH the shipping text. A plant that no longer
    matches would silently degrade into a clean run and every control
    would go green for the wrong reason, so a miss is an error.
    """
    block = _fold_block_source()
    for old, new in mutations:
        assert old in block, (
            f"planted defect does not match the shipping source: {old!r}. "
            f"The control cannot fire, so it proves nothing."
        )
        block = block.replace(old, new)
    text = _GENERATED_MODULE.format(body=textwrap.indent(block, "    "))
    holder = tempfile.TemporaryDirectory()
    path = Path(holder.name) / "shipped_fold_block.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("shipped_fold_block", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Keep the directory alive for the module's lifetime.
    module._tmp_holder = holder
    return module


CLEAN = _load_block()

# The historical defect: scale the SUMMED usd, wire credit included.
PLANT_PRE_FIX = (
    (
        '_t["usd"] = _wire_usd + _scrummed_usd * _fold_frac',
        '_t["usd"] = _full_usd * _fold_frac',
    ),
    (
        "_skim_proceeds = _scrummed_usd * (1 - _fold_frac)",
        "_skim_proceeds = _full_usd * (1 - _fold_frac)",
    ),
)

# The plausible-but-broken fix: exempt what the `wire_credits` record
# says instead of what the units say. Correct on a bot whose ledger
# survived, useless on the two live bots whose ledger did not.
_RECORDED = (
    "min(max(sum(float(_e.get('usd', 0.0) or 0.0) for _e in "
    "(_t.get('wire_credits') or [])), 0.0), _full_usd)"
)
PLANT_EXEMPT_BY_PROVENANCE = (
    ("_wire_usd = _full_usd - _scrummed_usd", f"_wire_usd = {_RECORDED}"),
    (
        '_t["usd"] = _wire_usd + _scrummed_usd * _fold_frac',
        '_t["usd"] = _wire_usd + (_full_usd - _wire_usd) * _fold_frac',
    ),
    (
        "_skim_proceeds = _scrummed_usd * (1 - _fold_frac)",
        "_skim_proceeds = (_full_usd - _wire_usd) * (1 - _fold_frac)",
    ),
)

# Drop a tenth of the folded proceeds on the floor: the split stops
# summing to what went in.
PLANT_VALUE_LEAK = (
    (
        '_t["usd"] = _wire_usd + _scrummed_usd * _fold_frac',
        '_t["usd"] = _wire_usd + _scrummed_usd * _fold_frac * 0.9',
    ),
)

# The same leak, on the RETIRED side. The sweep checks the wire half
# before it checks conservation, and PLANT_VALUE_LEAK moves the tranche's
# usd, so that plant trips the wire assertion first and the conservation
# assertion is never reached -- a control that fires for the wrong reason
# proves nothing about the check it was meant to exercise. Leaking from
# `_skim_usd` leaves the tranche untouched, so the wire assertion passes
# and conservation is the one that must go red.
PLANT_RETIRED_LEAK = (
    ("_skim_usd += _skim_proceeds", "_skim_usd += _skim_proceeds * 0.9"),
)

# Let the block run at 100% and halve the fraction while it is there.
PLANT_TOUCHES_FULL_FOLD_BOT = (
    ("if _fold_pct < 100 and _new_tranches:", "if _fold_pct <= 100 and _new_tranches:"),
    ("_fold_frac = _fold_pct / 100.0", "_fold_frac = _fold_pct / 200.0"),
)


# ── stub bot ─────────────────────────────────────────────────────


class _Bus:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def emit(self, event: str, **kwargs) -> None:
        self.messages.append((event, kwargs))

    def logs(self) -> list[str]:
        return [
            str(kw.get("message", "")) for ev, kw in self.messages if ev == "bot.log"
        ]


class _Config:
    def __init__(self, scrum_fold_pct: int) -> None:
        self.scrum_fold_pct = scrum_fold_pct


class _Bot:
    """The surface the fold block and the absorb method actually touch.

    ``_add_wire_credits`` is the REAL method, bound here, so the bounded
    append and its ``wire_credits_rolled`` overflow run exactly as they do
    in production. Nothing about the provenance path is simulated.
    """

    def __init__(self, scrum_fold_pct: int = 50) -> None:
        self.bot_id = "stub"
        self.config = _Config(scrum_fold_pct)
        self._bus = _Bus()
        self._fold_tranches: list[dict] = []
        self._pending_wire_credits = 0.0
        self._pending_wire_ledger: list[dict] = []
        self._add_wire_credits = types.MethodType(ScrummingBot._add_wire_credits, self)

    def park(
        self,
        usd: float,
        source: str = "peer-bot",
        entries: int = 1,
        ledger_usd: float | None = None,
    ) -> None:
        """Park wire income exactly as ``apply_wire_income`` case 2 does.

        ``ledger_usd`` models the v3.24.49 restart gap: the parked TOTAL
        survived a restart but the itemisation did not, so the ledger can
        account for less than the money.
        """
        self._pending_wire_credits += usd
        recorded = usd if ledger_usd is None else ledger_usd
        share = recorded / entries
        for i in range(entries):
            self._pending_wire_ledger.append(
                {"ts": 1000.0 + i, "source": source, "usd": share, "ref": f"wire-{i}"}
            )

    def build_tranche(self, usd: float, units: float, initial_buy_price: float) -> dict:
        tranche = {
            "usd": usd,
            "units": units,
            "ref": 100.0,
            "initial_buy_price": initial_buy_price,
            "created_ts": 1.0,
        }
        self._fold_tranches.append(tranche)
        return tranche

    def absorb_into(self, tranche: dict) -> float:
        """Run the REAL absorb, at the real drain window (zero tranches
        before this scrum). Unit 1 does not touch that window."""
        return ScrummingBot._absorb_pending_wire_credits_into(self, tranche)

    def retired_usd(self) -> float:
        """Dollars the block reports as retired to cash, read off the
        operator log -- the surface the operator actually reads."""
        for message in self._bus.logs():
            if message.startswith("FOLD RATIO:"):
                after = message.split("retired $", 1)[1]
                return float(after.split(" as cash", 1)[0])
        return 0.0

    def queued_usd_from_log(self) -> float:
        for message in self._bus.logs():
            if message.startswith("FOLD RATIO:"):
                after = message.split("queued $", 1)[1]
                return float(after.split(" for", 1)[0])
        return 0.0


class _Spread:
    """Deterministic, equidistributed values for the sweep.

    An additive recurrence on the golden ratio, not a PRNG. It is
    reproducible with no seed to record, and it fills the interval more
    evenly than sampling would, which is the point of a sweep: the goal
    is to COVER the domain, not to imitate randomness.
    """

    _STEP = 0.6180339887498949

    def __init__(self) -> None:
        self._x = 0.5

    def between(self, low: float, high: float) -> float:
        self._x = (self._x + self._STEP) % 1.0
        return low + (high - low) * self._x


def _scrum(
    module,
    bot: _Bot,
    parked: float,
    proceeds: float,
    units: float = 1.0,
    price: float = 100.0,
    entries: int = 1,
    ledger_usd: float | None = None,
) -> dict:
    """One autonomous scrum on a bot that held zero tranches.

    Parks ``parked``, sells ``units`` for ``proceeds``, builds the single
    tranche that sale produces, absorbs at the real drain window, then
    runs the shipping fold block with the same ``scrum_usd`` /
    ``scrum_asset`` pair the build loop divided.
    """
    if parked > 0:
        bot.park(parked, entries=entries, ledger_usd=ledger_usd)
    tranche = bot.build_tranche(proceeds, units, price)
    bot.absorb_into(tranche)
    module.run_shipped_fold_block(bot, proceeds, units, 0)
    return tranche


# ── the checks, each run clean and planted ───────────────────────


def _check_absorbed_credit_lands_at_full_value(module) -> None:
    bot = _Bot(scrum_fold_pct=50)
    tranche = _scrum(module, bot, parked=343.68, proceeds=100.0)
    wire_present = tranche["usd"] - 100.0 * 0.5
    assert round(wire_present, 2) == 343.68, (
        f"absorbed wire credit must reach the fold queue at full value; "
        f"tranche holds ${wire_present:.4f} of $343.68"
    )


def _check_own_proceeds_are_still_scaled(module) -> None:
    bot = _Bot(scrum_fold_pct=50)
    tranche = _scrum(module, bot, parked=343.68, proceeds=100.0)
    proceeds_present = tranche["usd"] - 343.68
    assert round(proceeds_present, 2) == 50.00, (
        f"the scrum's OWN proceeds must still be folded at 50%; "
        f"${proceeds_present:.4f} of $100.00 queued"
    )
    assert round(bot.retired_usd(), 2) == 50.00, (
        f"the retired half must be proceeds only; log says " f"${bot.retired_usd():.4f}"
    )
    assert (
        round(tranche["units"], 9) == 0.5
    ), "units carry no wire credit and must still be scaled in full"


def _check_the_live_ledger_gap_does_not_defeat_the_fix(module) -> None:
    """7c39c7a2 as it actually stands: $343.68 parked, $1.43 itemised.

    A fix that exempts the RECORDED amount rescues $0.71 and retires
    $171.13 of wired-in money. This is the check that tells the two
    designs apart, so it carries the provenance-based fix as its plant.
    """
    bot = _Bot(scrum_fold_pct=50)
    tranche = _scrum(
        module,
        bot,
        parked=343.6824420629954,
        proceeds=200.0,
        units=0.00399929,
        entries=3,
        ledger_usd=1.425739,
    )
    wire_present = tranche["usd"] - 200.0 * 0.5
    assert round(wire_present, 2) == 343.68, (
        f"the exempt amount must follow the MONEY, not the ledger: only "
        f"${wire_present:.2f} of $343.68 survived, so ${343.68 - wire_present:.2f} "
        f"of wired-in money was retired as cash"
    )


def _check_provenance_never_overstates(module) -> None:
    """Constraint (c), in the direction that can be guaranteed.

    The record must never claim MORE wire money than the tranche holds,
    because that is the divergence the defect created: the entries kept
    their full usd while the usd was scaled down. Where the ledger
    survived, record and money agree to the cent. Where it did not, the
    record under-states -- a pre-existing v3.24.49 gap this change does
    not widen and does not repair.
    """
    for entries, ledger_usd, exact in (
        (1, None, True),
        (3, None, True),
        (3, 1.425739, False),
    ):
        bot = _Bot(scrum_fold_pct=40)
        tranche = _scrum(
            module,
            bot,
            parked=343.68,
            proceeds=100.0,
            entries=entries,
            ledger_usd=ledger_usd,
        )
        recorded = sum(
            float(e.get("usd", 0.0) or 0.0) for e in tranche.get("wire_credits") or []
        )
        present = tranche["usd"] - 100.0 * 0.40
        assert recorded <= present + MONEY_TOL_USD, (
            f"provenance over-states: the record claims ${recorded:.6f} but "
            f"only ${present:.6f} of wire money is in the tranche"
        )
        if exact:
            assert round(recorded, 2) == round(present, 2), (
                "with an intact ledger the record and the money must agree "
                "to the cent"
            )


def _check_full_fold_bot_is_untouched(module) -> None:
    bot = _Bot(scrum_fold_pct=100)
    bot.park(343.68)
    tranche = bot.build_tranche(100.0, 1.0, 100.0)
    bot.absorb_into(tranche)
    before = copy.deepcopy(bot._fold_tranches)
    logs_before = len(bot._bus.logs())

    module.run_shipped_fold_block(bot, 100.0, 1.0, 0)

    assert (
        bot._fold_tranches == before
    ), "a bot at scrum_fold_pct=100 must come out identical"
    assert (
        len(bot._bus.logs()) == logs_before
    ), "a bot at scrum_fold_pct=100 must not emit a FOLD RATIO line"
    assert round(tranche["usd"], 2) == 443.68


def _check_value_is_conserved(module) -> None:
    for fold_pct in (0, 1, 37, 50, 99):
        bot = _Bot(scrum_fold_pct=fold_pct)
        bot.park(343.68)
        tranche = bot.build_tranche(100.0, 1.0, 100.0)
        bot.absorb_into(tranche)
        before = tranche["usd"]

        module.run_shipped_fold_block(bot, 100.0, 1.0, 0)

        after = tranche["usd"] + bot.retired_usd()
        assert abs(after - before) <= MONEY_TOL_USD, (
            f"value is not conserved at scrum_fold_pct={fold_pct}: "
            f"${before:.6f} in, ${after:.6f} out "
            f"(${tranche['usd']:.6f} queued + ${bot.retired_usd():.6f} "
            f"retired)"
        )


def _check_sweep(module) -> None:
    """Rule 2 of two-sided-control: close the numeric domain.

    ``scrum_fold_pct`` is clamped to the integers 0..100, so 0..99 is the
    ENTIRE domain on which the block runs -- enumerated exhaustively, not
    sampled. Parked pools span six decades, from one cent to $99,999.99,
    plus eight values drawn from ``_Spread`` across that range. Proceeds
    and units advance independently at every point, so the wire half and
    the proceeds half can never be confused by a coincidence of equal
    magnitudes. Every third point also carries the live ledger gap, so
    the sweep covers both provenance states.
    """
    spread = _Spread()
    parked_values = [0.01, 0.13, 1.0, 12.34, 343.68, 1000.0, 99999.99]
    parked_values += [round(spread.between(0.01, 50000.0), 2) for _ in range(8)]
    checked = 0
    for fold_pct in range(0, 100):
        frac = fold_pct / 100.0
        for index, parked in enumerate(parked_values):
            proceeds = round(spread.between(0.5, 25000.0), 2)
            units = spread.between(0.001, 40.0)
            gap = parked * 0.004 if index % 3 == 0 else None
            bot = _Bot(scrum_fold_pct=fold_pct)
            tranche = _scrum(
                module,
                bot,
                parked=parked,
                proceeds=proceeds,
                units=units,
                ledger_usd=gap,
            )

            wire_present = tranche["usd"] - proceeds * frac
            assert abs(wire_present - parked) <= MONEY_TOL_USD, (
                f"fold_pct={fold_pct} parked=${parked} proceeds=${proceeds}: "
                f"${wire_present:.9f} of wire money survived, expected "
                f"${parked}"
            )

            recorded = sum(
                float(e.get("usd", 0.0) or 0.0)
                for e in tranche.get("wire_credits") or []
            )
            assert recorded <= wire_present + MONEY_TOL_USD, (
                f"fold_pct={fold_pct} parked=${parked}: provenance "
                f"${recorded:.9f} over-states the ${wire_present:.9f} "
                f"present"
            )

            total_out = tranche["usd"] + bot.retired_usd()
            assert abs(total_out - (parked + proceeds)) <= MONEY_TOL_USD, (
                f"conservation broken at fold_pct={fold_pct} "
                f"parked=${parked} proceeds=${proceeds}: "
                f"${parked + proceeds:.9f} in, ${total_out:.9f} out"
            )

            assert (
                abs(tranche["units"] - units * frac) <= MONEY_TOL_USD
            ), f"fold_pct={fold_pct}: units must be scaled in full"

            assert (
                abs(bot.queued_usd_from_log() - tranche["usd"]) <= 1e-4
            ), "the FOLD RATIO log must report the queue it just wrote"
            checked += 1
    assert checked == 100 * len(parked_values)


# ── clean side: the shipping block must pass every check ─────────


def test_absorbed_credit_lands_at_full_value():
    _check_absorbed_credit_lands_at_full_value(CLEAN)


def test_own_proceeds_are_still_scaled():
    _check_own_proceeds_are_still_scaled(CLEAN)


def test_the_live_ledger_gap_does_not_defeat_the_fix():
    _check_the_live_ledger_gap_does_not_defeat_the_fix(CLEAN)


def test_provenance_never_overstates():
    _check_provenance_never_overstates(CLEAN)


def test_full_fold_bot_is_untouched():
    _check_full_fold_bot_is_untouched(CLEAN)


def test_value_is_conserved():
    _check_value_is_conserved(CLEAN)


def test_sweep_over_the_whole_fold_domain():
    _check_sweep(CLEAN)


# ── planted side: every check must be able to go red ─────────────


def test_control_full_value_check_fails_on_the_original_defect():
    with pytest.raises(AssertionError, match="full value"):
        _check_absorbed_credit_lands_at_full_value(_load_block(*PLANT_PRE_FIX))


def test_control_proceeds_check_fails_when_the_fold_fraction_is_dropped():
    plant = _load_block(
        (
            '_t["usd"] = _wire_usd + _scrummed_usd * _fold_frac',
            '_t["usd"] = _wire_usd + _scrummed_usd',
        )
    )
    with pytest.raises(AssertionError, match="OWN proceeds"):
        _check_own_proceeds_are_still_scaled(plant)


def test_control_ledger_gap_check_fails_on_the_provenance_based_fix():
    """The control that separates the two candidate designs.

    Exempting the recorded amount passes every other check in this file
    and still leaves $171.13 of 7c39c7a2's money to be retired as cash.
    """
    with pytest.raises(AssertionError, match="follow the MONEY"):
        _check_the_live_ledger_gap_does_not_defeat_the_fix(
            _load_block(*PLANT_EXEMPT_BY_PROVENANCE)
        )


def test_control_provenance_check_fails_when_the_record_overstates():
    with pytest.raises(AssertionError, match="over-state"):
        _check_provenance_never_overstates(_load_block(*PLANT_PRE_FIX))


def test_control_full_fold_check_fails_when_the_block_touches_that_bot():
    with pytest.raises(AssertionError, match="scrum_fold_pct=100"):
        _check_full_fold_bot_is_untouched(_load_block(*PLANT_TOUCHES_FULL_FOLD_BOT))


def test_control_conservation_check_fails_on_a_value_leak():
    with pytest.raises(AssertionError, match="not conserved"):
        _check_value_is_conserved(_load_block(*PLANT_VALUE_LEAK))


def test_control_sweep_fails_on_the_original_defect():
    with pytest.raises(AssertionError, match="wire money survived"):
        _check_sweep(_load_block(*PLANT_PRE_FIX))


def test_control_sweep_fails_on_a_value_leak():
    with pytest.raises(AssertionError, match="conservation broken"):
        _check_sweep(_load_block(*PLANT_RETIRED_LEAK))


# ── edges the exemption must not mis-handle ──────────────────────


def test_a_scrum_with_no_parked_pool_is_folded_in_full():
    """The exemption must be zero when nothing was wired in, or every
    ordinary scrum would stop honouring the operator's fold ratio."""
    bot = _Bot(scrum_fold_pct=25)
    tranche = _scrum(CLEAN, bot, parked=0.0, proceeds=400.0, units=2.0)
    assert round(tranche["usd"], 2) == 100.00
    assert round(bot.retired_usd(), 2) == 300.00


def test_a_multi_tranche_scrum_exempts_only_the_absorbed_one():
    """The absorb lands in the FIRST new tranche. The others hold pure
    proceeds and must be folded in full."""
    bot = _Bot(scrum_fold_pct=50)
    bot.park(343.68)
    first = bot.build_tranche(60.0, 3.0, 100.0)
    second = bot.build_tranche(40.0, 2.0, 90.0)
    bot.absorb_into(first)

    CLEAN.run_shipped_fold_block(bot, 100.0, 5.0, 0)

    assert round(first["usd"], 2) == round(343.68 + 30.0, 2)
    assert round(second["usd"], 2) == 20.00
    assert round(bot.retired_usd(), 2) == 50.00


def test_an_unknown_sale_rate_falls_back_to_the_old_behaviour():
    """With no units sold there is no rate to price units at. The block
    must then treat everything as proceeds -- the pre-fix behaviour --
    rather than inventing an exemption it cannot substantiate."""
    bot = _Bot(scrum_fold_pct=50)
    tranche = bot.build_tranche(100.0, 0.0, 100.0)

    CLEAN.run_shipped_fold_block(bot, 0.0, 0.0, 0)

    assert round(tranche["usd"], 2) == 50.00
    assert round(bot.retired_usd(), 2) == 50.00


def test_a_tranche_richer_than_its_units_cannot_shrink_the_queue():
    """The clamp, at the surface: if rounding ever prices a tranche's
    units above the dollars it holds, the wire share must floor at zero
    rather than going negative and eating the queue."""
    bot = _Bot(scrum_fold_pct=50)
    tranche = bot.build_tranche(100.0, 5.0, 100.0)

    # Units priced at the scrum rate come to $500 against $100 held.
    CLEAN.run_shipped_fold_block(bot, 200.0, 2.0, 0)

    assert round(tranche["usd"], 2) == 50.00
    assert round(bot.retired_usd(), 2) == 50.00
