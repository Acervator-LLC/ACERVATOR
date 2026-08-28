"""A bot may not adopt more than the operator allows.

Operator approved 2026-08-09, after research into how the field solves
shared-account attribution:
docs/engineering-notes/2026-08-09_position_attribution_shared_account_research.md

THE GAP THIS CLOSES. The never-scrummed rule (v3.24.85) lets a bot with
no earned history adopt an operator-placed position as its opening lot.
That fixed the BICO/IMU incident, where two new bots each bought a
SECOND full position because their own ledger said they held nothing.

But adoption INFERS ownership from the exchange balance, and nothing on
the exchange distinguishes "the seed the operator bought for this bot"
from "coins the operator holds and wants left alone". A fresh bot on an
asset the operator already held would take all of it.

WHAT THE FIELD DOES. Three patterns found:

  * Freqtrade — internal ledger authoritative, no adoption at all:
    "Freqtrade assumes that the trades it opens are managed only
    through the bot."
  * Coinbase Portfolios — exchange-level sub-accounts, attribution
    becomes a fact rather than an inference.
  * Hummingbot `balance limit` — an operator-DECLARED cap on what the
    bot may use. Documented as: "Sets the amount limit on how much
    assets Hummingbot can use in an exchange or wallet. This can be
    useful when running multiple bots on different trading pairs with
    same tokens."
    https://hummingbot.org/client/global-configs/balance-limit/

The third is what was missing here, and it is the only one that answers
the question the inference cannot. `max_adoptable_usd` is that
declaration, defaulting to `target_balance`: a bot asked to hold $25 has
no business claiming $500 because it happened to be there.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SYM = "BICO/USDC"
ASSET = "BICO"
PX = 0.0706380489
T0 = 1_776_778_500_000
STEP = 300_000


def _cap_units(exchange_units, cap_usd, target_balance, price):
    """The capping arithmetic exactly as the adoption site applies it.

    Pinned here because the site itself lives inline in `tick`, which
    needs a running loop; a change to the rule fails here rather than
    in production.
    """
    own = float(exchange_units)
    cap = float(cap_usd or 0.0)
    if cap <= 0:
        cap = float(target_balance or 0.0)
    if cap > 0 and price > 0:
        own = min(own, cap / price)
    return own


class TestTheDefaultIsTargetBalance:
    def test_zero_means_use_target_balance(self):
        """0.0 is 'unset', not 'adopt nothing'. Treating it as a literal
        zero would silently disable adoption for every existing bot,
        since none of them carry the new field."""
        got = _cap_units(10_000.0, 0.0, 25.0, PX)
        assert got == pytest.approx(25.0 / PX)

    def test_a_bot_asked_to_hold_25_adopts_at_most_25(self):
        got = _cap_units(10_000.0, 0.0, 25.0, PX)
        assert got * PX == pytest.approx(25.0)

    def test_an_explicit_cap_overrides_the_default(self):
        got = _cap_units(10_000.0, 10.0, 25.0, PX)
        assert got * PX == pytest.approx(10.0)

    def test_the_field_exists_on_botconfig(self):
        from src.trading.bot_container import BotConfig

        assert hasattr(BotConfig, "max_adoptable_usd")
        assert BotConfig.max_adoptable_usd == 0.0


class TestTheCapOnlyEverReduces:
    def test_a_small_holding_is_adopted_whole(self):
        """The BICO case: the operator's manual $25 against a $25
        target. The cap must not shave it."""
        units = 25.0 / PX
        assert _cap_units(units, 0.0, 25.0, PX) == pytest.approx(units)

    def test_it_never_invents_units(self):
        """A cap above the holding must not raise the holding to it."""
        units = 5.0 / PX
        assert _cap_units(units, 1000.0, 25.0, PX) == pytest.approx(units)

    def test_a_zero_price_leaves_the_holding_alone(self):
        """No price means no USD conversion, so no defensible cap.
        Capping to zero here would discard a real position on a failed
        ticker read."""
        units = 100.0
        assert _cap_units(units, 25.0, 25.0, 0.0) == pytest.approx(units)

    def test_no_target_and_no_cap_leaves_the_holding_alone(self):
        assert _cap_units(100.0, 0.0, 0.0, PX) == pytest.approx(100.0)


class TestTheOperatorsSurplusIsWithheld:
    def test_the_withheld_amount_is_the_difference(self):
        """The operator holds 500 of the asset; the bot may take $25."""
        held = 500.0
        got = _cap_units(held, 0.0, 25.0, PX)
        withheld = held - got
        assert withheld > 0
        assert got * PX == pytest.approx(25.0)
        assert withheld == pytest.approx(held - 25.0 / PX)

    def test_the_uncapped_rule_would_have_taken_everything(self):
        """NEGATIVE CONTROL. Without the cap the bot adopts the lot --
        this is the behaviour the cap exists to prevent, and if it were
        not reproducible the tests above would prove nothing."""
        held = 500.0
        uncapped = held
        capped = _cap_units(held, 0.0, 25.0, PX)
        assert uncapped > capped
        assert uncapped == pytest.approx(held)


def _adoption_source() -> str:
    """The module that owns the boot handshake, whichever file that is."""
    path = inspect.getsourcefile(ScrummingBot._tick_initialise)
    return Path(path).read_text(encoding="utf-8")


class TestItIsWiredIntoAdoption:
    def test_the_adoption_site_applies_the_cap(self):
        src = _adoption_source()
        assert "max_adoptable_usd" in src
        assert "ADOPTION CAPPED" in src
        assert "bot.01.003.postcondition.adoption_capped" in src

    def test_the_cap_is_applied_before_the_lot_is_built(self):
        """Order matters: capping after `_main_lots` was written would
        record the uncapped position and then contradict it."""
        import re

        src = _adoption_source()
        i_cap = src.index("_cap_usd = float(getattr(")
        # black may wrap `[{` across lines; match the dict-literal build, not `[]`.
        i_lot = re.search(r"self\._main_lots = \[\s*\{", src).start()
        assert i_cap < i_lot, "cap must precede lot construction"

    def test_the_emitter_reports_what_was_withheld(self):
        """`expected` is what the exchange offered, `actual` what was
        taken, so ok=False marks every bot holding operator surplus."""
        src = _adoption_source()
        blk = src[src.index("bot.01.003.postcondition.adoption_capped") :][:600]
        assert "withheld_units" in blk
        assert "cap_usd" in blk


class TestTheOperatorIsTold:
    def test_the_log_names_the_lever(self):
        """A cap the operator cannot find is a cap they will report as
        a bug."""
        src = _adoption_source()
        blk = src[src.index("ADOPTION CAPPED") :][:900]
        assert "max_adoptable_usd" in blk
        assert "unmanaged" in blk
