"""A sim bot reserves its capital without inflating the sim inventory.

`_compute_reservation_qty` claims `target / price` with a 10% margin, and a sim
fleet is seeded at exactly `target / open_px`, so the claim exceeds the seed.
`_ensure_capital_reservation` passes `total_holdings=None` on the first sim
ensure, which skips `reserve`s over-commit check. The seed itself does not
move: `opening_lot_for_lotless` is held to `TARGET_USD` at `OPEN_PX`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.capital_reservation import (  # noqa: E402
    CapitalReservationRegistry,
)

OPEN_PX = 50_000.0
TARGET_USD = 100.0
SEEDED_UNITS = TARGET_USD / OPEN_PX


def _registry(tmp_path):
    return CapitalReservationRegistry(state_path=tmp_path / "res.json", autosave=False)


def _ensure_host(registry, *, sim_mode: bool):
    """A host carrying only what `_ensure_capital_reservation` reads.

    Holdings are seeded at `SEEDED_UNITS`, exactly `TARGET_USD` at `OPEN_PX`.
    """
    from src.trading.scrumming.capital_reservation_mixin import (
        CapitalReservationMixin,
    )

    class _Host(CapitalReservationMixin):
        def __init__(self) -> None:
            self.bot_id = "sim" if sim_mode else "live"
            self.config = type(
                "C",
                (),
                {
                    "self_reserve_capital": True,
                    "target_asset": "BTC",
                    "personal_hold_qty": 0.0,
                },
            )()
            self._target_balance = TARGET_USD
            self._quote_to_usd = 1.0
            self._sim_mode = sim_mode
            self._crr_token = None
            self._crr_last_reserved_qty = 0.0

        def _crr(self):
            return registry

        async def _get_cached_exchange_balance(self, _asset):
            return SEEDED_UNITS

    return _Host()


class TestTheDefectIsReal:
    def test_a_claim_above_holdings_is_refused(self, tmp_path):
        """POSITIVE CONTROL for the whole file: the over-commit raise is
        what made sim reservations fail. If it stopped firing, the fix
        below would be unnecessary and the tests vacuous."""
        reg = _registry(tmp_path)
        with pytest.raises(ValueError):
            reg.reserve(
                bot_id="b1",
                asset="BTC",
                qty=1.10,
                reason="sim",
                bot_kind="scrumming",
                total_holdings=1.0,
            )

    def test_the_same_claim_succeeds_when_holdings_are_not_asserted(self, tmp_path):
        """...and passing None is what unblocks it."""
        reg = _registry(tmp_path)
        tok = reg.reserve(
            bot_id="b1",
            asset="BTC",
            qty=1.10,
            reason="sim",
            bot_kind="scrumming",
            total_holdings=None,
        )
        assert tok


class TestTheMarginIsNotAnInventoryTarget:
    def test_the_claim_is_ten_percent_above_the_target(self, tmp_path):
        """`_compute_reservation_qty` returns `target / price` scaled by 1.10.

        The margin is live over-commit headroom, not an inventory target.
        """
        bot = _ensure_host(_registry(tmp_path), sim_mode=False)
        assert bot._compute_reservation_qty(OPEN_PX) == pytest.approx(
            SEEDED_UNITS * 1.10
        )

    def test_the_sim_seed_is_the_target_and_not_the_claim(self):
        """`opening_lot_for_lotless` seeds `target / open_px`, never 110% of it.

        A seed at the reservation ceiling would hand every sim bot more base
        units than a live bot holds.
        """
        from src.simulator.fleet.fleet_replay_controller import (
            opening_lot_for_lotless,
        )

        candles = [[1_776_778_500_000, OPEN_PX, OPEN_PX, OPEN_PX, OPEN_PX, 1.0]]
        lot = opening_lot_for_lotless(TARGET_USD, candles)

        assert lot is not None, "the seeding helper produced no lot"
        assert float(lot["units"]) == pytest.approx(SEEDED_UNITS)
        assert float(lot["units"]) < SEEDED_UNITS * 1.10


class TestTheRegistryContract:
    def test_reservations_are_keyed_by_token_not_bot_id(self, tmp_path):
        """The cascade's ORIGINAL exit gate asserted
        len(_reservations) == number of bots. It is keyed by a fresh
        token, so that clause was wrong for the data model and would
        fail a correct fix. The plan already corrects itself; this pins
        the reason."""
        reg = _registry(tmp_path)
        t1 = reg.reserve(
            bot_id="b1", asset="BTC", qty=1.0, reason="r", bot_kind="scrumming"
        )
        assert t1 not in ("b1",)
        assert len(t1) > 8, "token does not look like a uuid hex"

    def test_one_token_per_bot_after_repeated_ensures(self, tmp_path):
        """The idempotent-update contract: N ticks must not accumulate N
        tokens for one bot."""
        reg = _registry(tmp_path)
        tok = reg.reserve(
            bot_id="b1", asset="BTC", qty=1.0, reason="r", bot_kind="scrumming"
        )
        for q in (1.1, 1.2, 1.3):
            reg.update(tok, bot_id="b1", new_qty=q)
        mine = [r for r in reg._reservations.values() if r.bot_id == "b1"]
        assert len(mine) == 1

    def test_a_zero_qty_bot_reserves_nothing(self, tmp_path):
        """A bot with target_balance == 0, or no first candle, computes
        qty == 0 and is rejected at the door — so 'every bot holds a
        token' is the wrong assertion. Only ELIGIBLE bots do."""
        reg = _registry(tmp_path)
        with pytest.raises(ValueError):
            reg.reserve(
                bot_id="b0", asset="BTC", qty=0.0, reason="r", bot_kind="scrumming"
            )


class TestTheSimPathPassesNone:
    def test_a_sim_bots_first_ensure_reserves(self, tmp_path):
        """A sim bot claims its 110% against holdings seeded at 100%.

        `_ensure_capital_reservation` runs unmodified; only the registry, the
        balance read and the config are stood in for.
        """
        reg = _registry(tmp_path)
        bot = _ensure_host(reg, sim_mode=True)
        asyncio.run(bot._ensure_capital_reservation(OPEN_PX))

        assert bot._crr_token is not None, "the sim bot reserved nothing"
        mine = [r for r in reg._reservations.values() if r.bot_id == bot.bot_id]
        assert len(mine) == 1
        assert mine[0].qty == pytest.approx(SEEDED_UNITS * 1.10)

    def test_a_live_bot_on_the_same_numbers_is_clamped_to_its_holdings(self, tmp_path):
        """The control: without the sim branch the claim is cut to holdings.

        Same price, same target, same seeded balance, `_sim_mode` off.
        """
        reg = _registry(tmp_path)
        bot = _ensure_host(reg, sim_mode=False)
        asyncio.run(bot._ensure_capital_reservation(OPEN_PX))

        mine = [r for r in reg._reservations.values() if r.bot_id == bot.bot_id]
        assert len(mine) == 1
        assert mine[0].qty == pytest.approx(SEEDED_UNITS)
        assert mine[0].qty < SEEDED_UNITS * 1.10
