"""C54: get_status() must emit each bot's OWN values, and ERROR must exist.

THREE DEFECTS, VERIFIED FROM SOURCE

NF-83 — get_status() emitted none of ytd_scrummed_usd, ytd_folded_usd,
total_scrummed_usd, total_folded_usd or portfolio_value. The fields are
real and ARE written (scrumming_bot.py:4056-4057, 8385, 9377, 10278,
10878); they simply never reached anything reading a status dict.

The subtle trap, and why this test is VALUE-level rather than text-level:
the obvious "fix" is to source those keys from
BotManager.get_aggregate_stats, which is a FLEET-WIDE sum. Doing that
makes every per-bot row show the fleet total. Two bots with different
values are the only fixture that catches it -- one bot, or a text-level
assertion on the source line, passes against the wrong object. The
existing pins (test_status_tab_sources.py, test_ytd_per_trade_increment)
assert source TEXT and would have stayed green.

NF-122 — BotState.ERROR was assigned NOWHERE in src/. Grep found it only
in comparisons, in `BotContainer._run_with_guard`
(`src/trading/bot_container.py`). The tick loop went
RUNNING -> COOLDOWN (at 5 consecutive errors) -> RUNNING and skipped
ERROR entirely, so get_aggregate_stats' "errored" count was structurally
pinned at zero. A bot could fail every single tick and the dashboard
would report a healthy fleet.

THE AI MONITOR (found while verifying NF-83)
check_live_monitor summed s.get("portfolio_value", 0) and
s.get("passive_value", 0) across all bots. get_status() emitted NEITHER,
so both totals were exactly 0.0 on every check, for every bot, forever.
LiveMonitor.analyze then formatted "Portfolio: $0.00 | Passive: $0.00 |
Adv: $+0.00", sent it to the model, and surfaced the reply on the bus as
ai.feedback -- advice about a portfolio it had been told was empty. The
default argument made it silent.

passive_value has NO source anywhere in src/: declared nowhere, written
nowhere. It is now reported as unavailable rather than as $0.00, because
a buy-and-hold baseline needs each position's entry basis and inventing
a zero for it is exactly what made this wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.bot_container import BotState  # noqa: E402

PER_BOT_KEYS = (
    "total_scrummed_usd",
    "total_folded_usd",
    "ytd_scrummed_usd",
    "ytd_folded_usd",
)


class _Stats:
    """Only the fields get_status() reads."""

    def __init__(self, **kw):
        defaults = dict(
            total_trades=0,
            exchange_trade_count=0,
            exchange_data_fresh_ts=0.0,
            trade_volume=0.0,
            realised_pnl=0.0,
            unrealised_pnl=0.0,
            active_buy_orders=0,
            active_sell_orders=0,
            current_price=0.0,
            position_value=0.0,
            extended_positions_created=0,
            uptime_seconds=0.0,
            last_error="",
            total_scrummed_usd=0.0,
            total_folded_usd=0.0,
            ytd_scrummed_usd=0.0,
            ytd_folded_usd=0.0,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def _status_of(**stat_values) -> dict:
    """Call the REAL get_status() against a minimal stand-in.

    Constructing a real BotContainer would resolve paths under the
    operator's home directory, so the method is invoked unbound against
    an object carrying only the attributes it touches.
    """
    from src.trading.bot_container import BotContainer

    class _Bot:
        bot_id = "bot-test"
        state = BotState.RUNNING
        stats = None
        _start_time = None
        _current_holdings = 0.0
        _quote_to_usd = 1.0
        _last_gate_state = {}

        def __init__(self, st):
            self.stats = st
            # Exactly the four config attributes get_status() reads,
            # extracted from its AST rather than guessed.
            self.config = type(
                "C",
                (),
                {
                    "symbol": "BTC/USD",
                    "exchange_id": "coinbase",
                    # get_status reads config.mode.value -- it is an enum,
                    # not a string.
                    "mode": type("M", (), {"value": "live"})(),
                    "target_balance": 50.0,
                },
            )()

    bot = _Bot(_Stats(**stat_values))
    return BotContainer.get_status(bot)


class TestTheInstrumentWorks:
    def test_get_status_returns_a_dict_at_all(self):
        """Positive control. Every assertion below is about keys in this
        dict; if the call itself were broken they would all fail for the
        wrong reason."""
        s = _status_of()
        assert isinstance(s, dict) and s.get("bot_id") == "bot-test"

    def test_it_still_emits_its_original_keys(self):
        """Negative control: adding keys must not have displaced any."""
        s = _status_of(position_value=12.0)
        assert "stats" in s and "auto_fire" in s
        assert s["stats"]["position_value"] == pytest.approx(12.0)


class TestPerBotKeysAreEmitted:
    @pytest.mark.parametrize("key", PER_BOT_KEYS)
    def test_the_key_is_present(self, key):
        assert (
            key in _status_of()["stats"]
        ), f"{key} is read by consumers but never emitted"

    def test_portfolio_value_is_present_at_the_root(self):
        """check_live_monitor reads it off the status ROOT, not stats."""
        assert "portfolio_value" in _status_of()

    def test_the_values_are_this_bot_s_own(self):
        s = _status_of(
            ytd_scrummed_usd=11.0,
            ytd_folded_usd=22.0,
            total_scrummed_usd=33.0,
            total_folded_usd=44.0,
            position_value=55.0,
        )["stats"]
        assert s["ytd_scrummed_usd"] == pytest.approx(11.0)
        assert s["ytd_folded_usd"] == pytest.approx(22.0)
        assert s["total_scrummed_usd"] == pytest.approx(33.0)
        assert s["total_folded_usd"] == pytest.approx(44.0)


class TestTwoBotsDoNotShareValues:
    """THE fixture that catches a fleet-aggregate source. One bot cannot
    distinguish 'this bot's value' from 'the fleet total'."""

    def test_two_bots_report_different_values(self):
        a = _status_of(ytd_scrummed_usd=10.0, ytd_folded_usd=1.0, position_value=100.0)
        b = _status_of(ytd_scrummed_usd=25.0, ytd_folded_usd=2.0, position_value=250.0)
        assert a["stats"]["ytd_scrummed_usd"] != b["stats"]["ytd_scrummed_usd"]
        assert a["portfolio_value"] != b["portfolio_value"]

    def test_neither_bot_reports_the_pair_s_sum(self):
        """A fleet-sourced key would make BOTH rows read 35.0."""
        a = _status_of(ytd_scrummed_usd=10.0)
        b = _status_of(ytd_scrummed_usd=25.0)
        total = 35.0
        assert a["stats"]["ytd_scrummed_usd"] != pytest.approx(total)
        assert b["stats"]["ytd_scrummed_usd"] != pytest.approx(total)
        assert (
            a["stats"]["ytd_scrummed_usd"] + b["stats"]["ytd_scrummed_usd"]
        ) == pytest.approx(total)


class TestErrorStateIsReachable:
    def test_the_enum_member_exists(self):
        """Positive control for the scanner below."""
        assert BotState.ERROR.value == "error"

    def test_something_actually_assigns_it(self):
        """NF-122: it was compared against but never written, so the
        fleet 'errored' count could not rise above zero."""
        import ast

        import src.trading.bot_container as bc

        src = Path(bc.__file__).read_text(encoding="utf-8")
        writes = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Assign):
                continue
            val = ast.unparse(node.value)
            if val.endswith("BotState.ERROR"):
                writes.append(node.lineno)
        assert writes, (
            "BotState.ERROR is assigned nowhere; get_aggregate_stats "
            "counts bots in that state, so 'errored' is pinned at 0"
        )

    def test_it_is_also_cleared(self):
        """A state that is set but never cleared would latch: one
        transient failure and the bot reads errored forever."""
        import ast

        import src.trading.bot_container as bc

        src = Path(bc.__file__).read_text(encoding="utf-8")
        cleared = False
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.If) and "BotState.ERROR" in ast.unparse(node.test):
                if "BotState.RUNNING" in ast.unparse(node):
                    cleared = True
        assert cleared, "ERROR is set but never cleared on a good tick"


class TestTheAIMonitorIsNotFedZeroes:
    def test_passive_is_reported_unavailable_not_zero(self):
        """It has no source in src/. Reporting $0.00 made every report
        claim an advantage equal to the entire portfolio."""
        import inspect

        from src.trading.live_monitor import LiveMonitor

        src = inspect.getsource(LiveMonitor.analyze)
        assert "passive is None" in src
        assert "unavailable" in src

    def test_the_caller_no_longer_defaults_the_missing_key(self):
        import inspect

        from src.trading.bot_container import BotManager

        src = inspect.getsource(BotManager.check_live_monitor)
        assert (
            's.get("passive_value", 0)' not in src
        ), "still defaulting a key that is emitted nowhere"
        assert "passive=None" in src

    def test_a_partial_portfolio_is_flagged(self):
        """If some bots cannot report, the total is partial and must say
        so rather than reading as a smaller portfolio."""
        import inspect

        from src.trading.bot_container import BotManager

        src = inspect.getsource(BotManager.check_live_monitor)
        assert "PARTIAL" in src
