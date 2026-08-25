"""The two sim venues must report the same market limits (SN-20, part).

C19, second pass.

WHAT SN-20 SAYS, AND WHAT IS ACTUALLY FIXABLE
The finding is "replace fabricated uniform limits with real per-symbol
limits". Verified 2026-08-07: the real limits are **not available
offline**. `bot_container._get_market_limits` reads them from
`exchange.get_markets()`, which for a sim bot is the sim venue's own
table, and nothing in `data/` or `contracts/` persists a captured copy.
Serving genuine per-symbol limits needs a capture step that does not
exist, so that half of SN-20 is a rescope, not an implementation.

WHAT IS FIXABLE TODAY, AND IS A REAL DEFECT
The two venues disagree with each other:

    Fleet    min_cost = 1.00
    Nuclear  min_cost = 0.01

A 100x difference in the smallest order either harness will accept. The
same strategy replayed on both produces different trade COUNTS — small
orders that Nuclear takes, Fleet rejects — and a difference that appears
on one venue and not the other reads as a finding rather than a
harness artefact. That is precisely the hazard C19 names.

WHICH VALUE, AND WHY
Aligned on the HIGHER floor. A too-low minimum lets the sim place orders
the real exchange would refuse, so the harness reports fills that could
never happen — false positives, in the direction that flatters a
strategy. A too-high floor only suppresses trades, which is visible as a
lower trade count rather than invented profit.

The uniform value remains an approximation and is labelled as one at
both sites. This pin exists so the two cannot drift apart again while
the real-limits capture is outstanding.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SYM = "BTC/USD"
CANDLE = [0, 100.0, 105.0, 95.0, 100.0, 10.0]


class _Src:
    def current(self, _tape_id):
        return list(CANDLE)

    def active_tapes(self):
        return ["tape"]


def _nuclear():
    from src.gui.simulator_tab.nuclear_sim_exchange import NuclearSimExchange

    ex = object.__new__(NuclearSimExchange)
    ex._src = _Src()
    ex._fee_pct = 0.0
    ex._balances = {"USD": 1_000.0, "BTC": 10.0}
    ex._exchange_id = "nuclear_sim"
    ex._connected = True
    ex._trades = []
    ex._orders = {}
    ex._quote = "USD"
    ex._asset_meta = {}
    ex._resolve_tape = lambda _s: "tape"
    return ex


def _fleet():
    from src.gui.simulator_tab.fleet.candle_series import CandleSeries
    from src.gui.simulator_tab.fleet.sim_exchange import FleetSimExchange

    return FleetSimExchange(
        series_map={SYM: CandleSeries(symbol=SYM, rows=[list(CANDLE)])},
        starting_balances={"USD": 1_000.0, "BTC": 10.0},
    )


async def _limits(ex):
    """(min_amount, min_cost) as the venue reports them.

    The two venues return different SHAPES from get_markets -- one a
    list of AssetInfo, one a dict -- which is itself a small parity
    wrinkle. Normalised here so the assertions compare limits rather
    than container types.
    """
    markets = await ex.get_markets()
    if isinstance(markets, dict):
        entries = list(markets.values())
    else:
        entries = list(markets)
    assert entries, "venue reported no markets"
    m = entries[0]
    return (
        float(getattr(m, "min_amount", 0.0) or 0.0),
        float(getattr(m, "min_cost", 0.0) or 0.0),
    )


class TestTheInstrumentWorks:
    @pytest.mark.asyncio
    async def test_both_venues_report_limits_at_all(self):
        """POSITIVE CONTROL. If either stopped reporting, the agreement
        assertion below would pass on two absences."""
        for build in (_nuclear, _fleet):
            _min_amt, _min_cost = await _limits(build())
            assert _min_cost > 0.0


class TestTheVenuesAgree:
    @pytest.mark.asyncio
    async def test_min_cost_is_identical(self):
        """A 100x gap in the smallest acceptable order means the same
        strategy produces different trade COUNTS on the two harnesses."""
        n_amt, n_cost = await _limits(_nuclear())
        f_amt, f_cost = await _limits(_fleet())
        assert n_cost == pytest.approx(f_cost), (
            f"nuclear min_cost={n_cost}, fleet min_cost={f_cost}; small "
            f"orders one venue accepts, the other rejects"
        )

    @pytest.mark.asyncio
    async def test_min_amount_is_identical(self):
        n_amt, _ = await _limits(_nuclear())
        f_amt, _ = await _limits(_fleet())
        assert n_amt == pytest.approx(f_amt)


class TestTheFloorErrsTowardsRefusing:
    @pytest.mark.asyncio
    async def test_min_cost_is_not_below_one_dollar(self):
        """A too-LOW minimum lets the sim place orders the real exchange
        would refuse, so the harness reports fills that could never have
        happened — false positives, in the direction that flatters a
        strategy. A too-high floor only suppresses trades, which shows
        up honestly as a lower trade count."""
        for name, build in (("nuclear", _nuclear), ("fleet", _fleet)):
            _amt, cost = await _limits(build())
            assert cost >= 1.0, (
                f"{name} min_cost={cost} would accept orders Coinbase " f"rejects"
            )


class TestTheApproximationIsLabelled:
    def test_both_sites_say_the_limits_are_not_real(self):
        """SN-20's real-limits half is outstanding. A fabricated uniform
        value that is not labelled as one is how the next reader
        concludes the sim honours venue limits."""
        for rel in (
            "src/gui/simulator_tab/fleet/sim_exchange.py",
            "src/gui/simulator_tab/nuclear_sim_exchange.py",
        ):
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "SN-20" in src, (
                f"{rel} does not record that its market limits are a "
                f"placeholder pending real per-symbol capture"
            )
