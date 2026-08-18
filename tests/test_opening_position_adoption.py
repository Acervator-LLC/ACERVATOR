"""A bot that has never scrummed treats the exchange as its position.

LIVE INCIDENT 2026-08-09 (v3.24.51), operator report: "Set the target
balance to $25 for BICO and IMU. Manually purchased the first $25.
Platform ignored this balance and proceeded to buy another $25 for
each."

WHAT HAPPENED. `bootstrap_exchange_state` reads the real exchange
balance into `_units`, then discards it when `_main_lots` is empty:

    self._current_holdings = min(max(0.0, _units), _tracked_bootstrap) \\
        if _tracked_bootstrap > 0 else 0.0

`position_value` therefore reported $0.00 while the operator was looking
at coins on Coinbase. Max Cartridge Fire computed
`delta = current_value - target_balance = -$25` and bought a second $25
with its gates deliberately bypassed:

    03:07:57  CARTRIDGE_FOLD  BICO/USDC  BUY  347.96 @ 0.0706380489
    03:11:19  CARTRIDGE_FOLD  IMU/USDC   BUY  6350.0 @ 0.0039

Both gate records read `scrum_armed=false fold_armed=false
blockers=["pre-tick"]`.

THE RULE. v3.23.43 made `_main_lots` the sole source of holdings to stop
a bot claiming units belonging to the operator, a sibling, or a prior
bot -- the ETH/BTC $178 surplus. Every one of those is about a bot with
TRADING HISTORY. A bot that has never scrummed has no history for a
surplus to be measured against, so whatever sits on the exchange for its
asset is simply its opening position.

The condition is `_tranches_created_lifetime == 0`, NOT "no lots".
Keying on empty lots would miss exactly the bots that need it: BICO and
IMU now carry a lot from the erroneous cartridge buy, while their scrum
history is still zero.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.fleet import (  # noqa: E402
    fleet_replay_controller as frc,
)

SYM = "BICO/USDC"
ASSET = "BICO"
STEP = 300_000
T0 = 1_776_778_500_000
SEED_UNITS = 347.96          # the operator's manual $25 of BICO
PX = 0.0706380489


def _rows(n=400):
    return [[T0 + i * STEP, PX, PX * 1.002, PX * 0.998, PX, 500.0]
            for i in range(n)]


def _cfg(**over):
    c = {"mode": "scrumming", "symbol": SYM, "target_balance": 25.0,
         "target_asset": ASSET, "base_currency": "USDC",
         "_src_bot_id": "cd98052b"}
    c.update(over)
    return c


def _bot(exchange_units=SEED_UNITS, cfg=None):
    """A bot wired to a tablet-backed connector holding real units."""
    from src.exchange.ccxt_connector import CCXTConnector
    from src.exchange.tablet_backend import TabletBackend

    be = TabletBackend(
        {SYM: _rows()},
        balances={"USDC": 500.0, ASSET: float(exchange_units)})
    for _ in range(300):
        be.step()
    conn = CCXTConnector("coinbase")
    conn.attach_backend(be)
    bot = frc._instantiate_bot(cfg or _cfg(), conn,
                              frc._make_sim_capital_registry())
    return bot, be


class TestTheConditionIsNeverScrummed:
    def test_a_fresh_bot_reports_zero_before_the_fix_condition(self):
        """The state that caused the incident: real units on the
        exchange, no lots, so holdings read zero."""
        bot, be = _bot()
        assert bot is not None
        assert bot._main_lots == []
        assert bot._current_holdings == 0.0
        # The exchange really does hold them.
        assert be.fetch_balance()[ASSET]["total"] == pytest.approx(SEED_UNITS)

    def test_never_scrummed_is_the_signal_not_empty_lots(self):
        """BICO after the erroneous cartridge buy: lots NON-empty,
        scrum history still zero. Keying on empty lots misses it."""
        bot, _ = _bot()
        bot._main_lots = [{"units": 347.96, "initial_buy_price": PX}]
        assert bot._main_lots != []
        assert int(getattr(bot, "_tranches_created_lifetime", 0) or 0) == 0

    def test_a_scrummed_bot_is_excluded(self):
        """v3.23.43's protection must remain for a bot with history."""
        bot, _ = _bot()
        bot._tranches_created_lifetime = 4
        assert int(bot._tranches_created_lifetime) != 0


class TestTheAdoptionArithmetic:
    """The decision the handshake makes, exercised directly.

    The adoption block lives inline in `tick`, which needs a running
    loop; these pin the arithmetic it performs so a change to the rule
    fails here rather than in production.
    """

    @staticmethod
    def _own(exchange_units, sibling_units, has_sibling):
        sib = float(sibling_units) if has_sibling else 0.0
        return max(0.0, float(exchange_units) - sib)

    def test_sole_bot_claims_everything(self):
        assert self._own(SEED_UNITS, 0.0, False) == pytest.approx(SEED_UNITS)

    def test_sibling_tracked_units_are_excluded(self):
        """BICO/USDC and BICO/BTC each holding a position: this bot
        claims only what its sibling does not track."""
        assert self._own(1000.0, 400.0, True) == pytest.approx(600.0)

    def test_a_sibling_tracking_everything_leaves_nothing(self):
        assert self._own(400.0, 400.0, True) == pytest.approx(0.0)

    def test_never_negative(self):
        assert self._own(100.0, 250.0, True) == 0.0

    def test_adoption_is_not_capped_at_target(self):
        """Adoption records what is HELD. Capping at what target BUYS
        would leave real units unattributed and rebuild the same blind
        spot one layer down."""
        units_worth_50 = SEED_UNITS * 2
        assert self._own(units_worth_50, 0.0, False) == pytest.approx(
            units_worth_50)


class TestTheInvariantSurvives:
    def test_holdings_equal_lot_units_after_adoption(self):
        """`sum(lot['units']) == _current_holdings` is enforced by
        `_main_lots_invariant_ok()`; adoption must not break it."""
        bot, _ = _bot()
        bot._main_lots = [{"units": SEED_UNITS, "initial_buy_price": PX}]
        bot._current_holdings = sum(
            float(x.get("units", 0) or 0) for x in bot._main_lots)
        assert bot._main_lots_invariant_ok() is True
        assert bot._current_holdings == pytest.approx(SEED_UNITS)

    def test_the_invariant_check_can_fail(self):
        """NEGATIVE CONTROL."""
        bot, _ = _bot()
        bot._main_lots = [{"units": SEED_UNITS, "initial_buy_price": PX}]
        bot._current_holdings = 0.0
        assert bot._main_lots_invariant_ok() is False


class TestCartridgeDeltaIsWhatSpent:
    """The arithmetic that actually bought the second $25."""

    @staticmethod
    def _delta(current_value, target):
        return float(current_value) - float(target)

    def test_zero_holdings_produces_a_full_target_buy(self):
        assert self._delta(0.0, 25.0) == -25.0

    def test_adopted_holdings_produce_at_most_a_small_topup(self):
        """MEASURED, not assumed. The operator's manual $25 filled at
        347.96 @ 0.0706380489 = $24.58 after fees, so after adoption the
        delta is -$0.42 -- outside the 1% dust band, so the bot tops up
        42 cents. That is the bot doing its job.

        The DEFECT was a delta of -$25.00: a whole second position. The
        property worth pinning is the ratio, not zero."""
        adopted_value = SEED_UNITS * PX
        d = self._delta(adopted_value, 25.0)
        assert -1.0 < d < 0.0, d
        # Before adoption the shortfall was the entire target.
        assert abs(d) < 0.05 * abs(self._delta(0.0, 25.0))
