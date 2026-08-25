"""The compounding surface must be exported by ``BotContainer.get_status``.

WHY THIS IS NOT COSMETIC
``get_status`` used to export ``"target_balance": self.config.target_balance``
-- the operator's INPUT value, which compounding does not move -- and never
exported the runtime ``live_target_balance`` the bot actually trades against.
So no GUI could show whether compounding had done anything.

The Target Balance spinbox must keep showing ``config.target_balance`` (the
change-detector diffs edits against it), while the GROWN value is surfaced
separately. This file pins the STATUS-DICT half of that contract functionally:
it builds a bot with stubbed collaborators, calls the real ``get_status``, and
reads the returned dict.

Previously this file grepped bot_container.py / bot_live_settings.py source
text (``"key" in get_status_source``, label strings ``in GUI_SRC``, line-number
windows). That was a stateful check of the source, not a test of behaviour, so
it tripped on any reformat and proved nothing about what the method returns. It
was replaced with the functional test below.

COVERAGE GAP (flagged, not silently dropped): the GUI-render half -- that
``BotLiveSettings`` actually paints "Live target (traded against):",
"Standing surplus:", "Cycle growth budget:" and "Over-cap tranches:" rows, and
that the spinbox is not repointed to the runtime value -- is no longer pinned
here. A functional replacement needs a constructed ``BotLiveSettings`` dialog
(Qt, offscreen) reading a real status dict; it belongs in a GUI test that
builds that widget.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.bot_container import BotStats  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

# The compounding surface: runtime keys get_status must export so a GUI can
# show whether compounding has moved anything.
SURFACE_KEYS = (
    "live_target_balance",
    "standing_surplus_usd",
    "fold_cycle_cap_consumed",
    "cycle_growth_budget_usd",
    "tranches_over_cycle_cap",
    "tranches_over_cycle_cap_usd",
)


def _stub(**kw):
    return type("_Stub", (), kw)()


def _bot(target_balance: float = 1000.0, live_target_balance: float = 1234.5):
    """A ScrummingBot with stubbed collaborators, ready for get_status().

    Collaborators the method reads (config/state/stats and a few scalar
    attributes) are stubbed; the method under test is the real one.
    """
    bot = object.__new__(ScrummingBot)
    bot.config = _stub(
        target_balance=target_balance,
        target_asset="BTC",
        base_currency="USD",
        name="bot",
        mode=_stub(value="scrumming"),
        exchange_id="coinbase",
        symbol="BTC/USD",
    )
    bot.bot_id = "bot"
    bot.symbol = "BTC/USD"
    bot.state = _stub(value="idle")
    bot.stats = BotStats()
    bot._start_time = 0.0
    bot._live_target_balance = live_target_balance
    return bot


class TestTheStatusDictCarriesTheSurface:
    def test_every_surface_key_is_exported(self):
        status = _bot().get_status()
        missing = [k for k in SURFACE_KEYS if k not in status]
        assert (
            not missing
        ), f"get_status does not export {missing}; no GUI can show them"

    def test_the_config_target_is_still_exported(self):
        # NEGATIVE CONTROL: the additions must not displace the field existing
        # consumers (the spinbox change-detector) read.
        assert "target_balance" in _bot().get_status()

    def test_live_and_config_targets_are_distinct_keys(self):
        # They are different quantities; collapsing them into one key is the
        # defect, not the fix.
        status = _bot(target_balance=1000.0, live_target_balance=1500.0).get_status()
        assert "target_balance" in status and "live_target_balance" in status
        assert status["target_balance"] == 1000.0

    def test_the_over_cap_summary_does_not_raise(self):
        # A status call that raises takes the dashboard down; getting a clean
        # dict back IS the proof the over-cap arithmetic is guarded.
        status = _bot().get_status()
        assert "tranches_over_cycle_cap" in status
        assert "tranches_over_cycle_cap_usd" in status
