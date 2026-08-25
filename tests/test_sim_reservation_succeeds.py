"""Sim reservations must succeed, without inflating sim inventory (C16).

Finding SN-5. Tier sim-only. Hard after C15.

THE DEFECT
`_compute_reservation_qty` claims `target / (price x quote_to_usd)` with
a **10% safety margin** so tick-to-tick drift cannot leave a live bot
under-reserved. Sim holdings are seeded at exactly `target / open_px`.
So the claim is ~110% of the seeded inventory, `reserve()` sees
`qty > total_holdings`, raises on over-commit, and the reservation fails
for every bot on every tick.

Consequence: the "SELL REFUSED (capital reservation)" branch is
UNREACHABLE in sim. A gate that can never fire is a gate the simulator
cannot tell you anything about.

THE FIX, AND THE TRAP IN THE OBVIOUS ALTERNATIVE
Pass `total_holdings=None` on the first sim ensure. The over-commit
check exists to protect LIVE inventory accounting across bots sharing
one exchange balance; a sim fleet holds a private registry (C15) and no
live inventory, so the check is measuring the wrong thing.

The tempting alternative — seed sim holdings at the reservation ceiling
— is WRONG and the cascade says so explicitly. The 1.10 is live
over-commit headroom, not an inventory target. Seeding there hands every
sim bot 110% of a live bot's base units, so sim out-scrums live and the
inflation reads as the fix working. `test_sim_seed_is_unchanged` pins
that the seed did not move.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.capital_reservation import (  # noqa: E402
    CapitalReservationRegistry,
)

SB = REPO_ROOT / "src" / "trading" / "scrumming_bot.py"


def _registry(tmp_path):
    return CapitalReservationRegistry(state_path=tmp_path / "res.json", autosave=False)


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
    def test_the_margin_is_ten_percent_headroom(self):
        """The 1.10 is live over-commit headroom. Seeding sim inventory
        at it would give every sim bot 110% of a live bot's base units,
        and sim would out-scrum live while looking fixed."""
        src = SB.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "_compute_reservation_qty"
        )
        seg = ast.get_source_segment(src, fn) or ""
        assert (
            "1.10" in seg or "1.1" in seg
        ), "the safety margin moved; re-derive C16 before trusting it"

    def test_sim_seed_is_unchanged(self):
        """C16 step 2: sim holdings stay at exactly target/open_px so
        sim and live start from identical inventory. Asserted against
        the seeding site, not against a number I chose."""
        fc = (
            REPO_ROOT
            / "src"
            / "gui"
            / "simulator_tab"
            / "fleet"
            / "fleet_replay_controller.py"
        )
        src = fc.read_text(encoding="utf-8")
        assert "1.10" not in src, (
            "the reservation ceiling leaked into the sim seeding path; "
            "sim inventory would exceed live"
        )


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
    def test_the_first_sim_ensure_does_not_assert_holdings(self):
        """Structural: the sim branch must reach `reserve` without
        handing it a holdings figure the 10% margin guarantees it
        exceeds."""
        src = SB.read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and "_ensure_capital_reservation" in n.name
            ),
            None,
        )
        assert fn is not None, "the ensure method was renamed"

        # AST, not substring. An earlier version of this test checked
        # `"_sim_mode" in seg` and PASSED against unfixed code, because
        # the method carries a comment at :1138 recording a DIFFERENT
        # `if _sim_mode: return` removed in v3.24.31. That is trap #5 in
        # docs/audits/2026-08-07_traps_that_pass_a_naive_test.md, sprung
        # inside the test written to verify the fix for it.
        sim_branches = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.If)
            and "_sim_mode" in (ast.get_source_segment(src, n.test) or "")
        ]
        assert sim_branches, (
            "the ensure path has no executable sim branch; sim "
            "reservations still fail the over-commit check every tick"
        )

    def test_the_reason_is_recorded_at_the_site(self):
        """Someone will read `total_holdings=None` and 'fix' it back."""
        src = SB.read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "_ensure_capital_reservation" in n.name
        )
        seg = ast.get_source_segment(src, fn) or ""
        assert "C16" in seg
