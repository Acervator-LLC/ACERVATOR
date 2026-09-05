"""``BotContainer.get_status`` emits each bot's own accumulators, ``BotState.ERROR``
is written and cleared, and ``check_live_monitor`` never invents a passive value.

``_status_of`` drives the real ``get_status`` on a real ``BotContainer``.
``_FailingTickBot`` drives ``_run_with_guard`` across a failing and a good tick.
``_analysis_message`` replaces ``LiveMonitor._call`` with a recorder and returns the
line ``LiveMonitor.analyze`` composed for it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.trading.bot_container import (  # noqa: E402
    BotConfig,
    BotContainer,
    BotManager,
    BotState,
    BotStats,
)
from src.trading.live_monitor import LiveMonitor  # noqa: E402

PER_BOT_KEYS = (
    "total_scrummed_usd",
    "total_folded_usd",
    "ytd_scrummed_usd",
    "ytd_folded_usd",
)


class _Exchange:
    """Stand-in venue for ``BotContainer``; it defines no method, so any call fails."""


def _config(**overrides) -> BotConfig:
    """Return a ``BotConfig`` for ``BTC/USD`` on ``coinbase``."""
    settings = dict(
        exchange_id="coinbase",
        base_currency="USD",
        target_asset="BTC",
        symbol="BTC/USD",
        target_balance=50.0,
    )
    settings.update(overrides)
    return BotConfig(**settings)


def _container(**stat_values) -> BotContainer:
    """Return a real ``BotContainer`` carrying real ``BotStats``.

    ``BotContainer.__init__`` resolves no path: a ``Path.home`` counter reads zero
    across the construction and one across a deliberate call after it.
    """
    bot = BotContainer(_config(), _Exchange())
    bot.stats = BotStats(**stat_values)
    bot.state = BotState.RUNNING
    return bot


def _status_of(**stat_values) -> dict:
    """Return ``get_status`` for a ``BotContainer`` whose ``BotStats`` carry
    ``stat_values``."""
    return _container(**stat_values).get_status()


class TestTheInstrumentWorks:
    def test_get_status_returns_a_dict_at_all(self):
        """Positive control: ``get_status`` answers with this bot's ``bot_id``."""
        bot = _container()
        status = bot.get_status()
        assert isinstance(status, dict) and status["bot_id"] == bot.bot_id

    def test_it_still_emits_its_original_keys(self):
        """Negative control: ``PER_BOT_KEYS`` displaced no earlier key."""
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
        """``check_live_monitor`` reads ``portfolio_value`` off the status root."""
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
    """Two ``BotContainer`` objects with different ``BotStats`` catch a
    fleet-aggregate source that one bot cannot tell from its own value."""

    def test_two_bots_report_different_values(self):
        a = _status_of(ytd_scrummed_usd=10.0, ytd_folded_usd=1.0, position_value=100.0)
        b = _status_of(ytd_scrummed_usd=25.0, ytd_folded_usd=2.0, position_value=250.0)
        assert a["stats"]["ytd_scrummed_usd"] != b["stats"]["ytd_scrummed_usd"]
        assert a["portfolio_value"] != b["portfolio_value"]

    def test_neither_bot_reports_the_pair_s_sum(self):
        """A fleet-sourced ``ytd_scrummed_usd`` would make both rows read 35.0."""
        a = _status_of(ytd_scrummed_usd=10.0)
        b = _status_of(ytd_scrummed_usd=25.0)
        total = 35.0
        assert a["stats"]["ytd_scrummed_usd"] != pytest.approx(total)
        assert b["stats"]["ytd_scrummed_usd"] != pytest.approx(total)
        assert (
            a["stats"]["ytd_scrummed_usd"] + b["stats"]["ytd_scrummed_usd"]
        ) == pytest.approx(total)


class _TickFailure(Exception):
    """Raised by ``_FailingTickBot.tick`` on the ticks a test wants to fail."""


class _FailingTickBot(BotContainer):
    """A ``BotContainer`` whose ``tick`` raises ``_TickFailure`` for its first
    ``failures`` calls and stops the loop on call ``total``.

    ``states`` records ``self.state`` on entry to each tick, so the state
    ``_run_with_guard`` left after the previous tick is observable.
    """

    def __init__(self, failures: int, total: int) -> None:
        super().__init__(_config(), _Exchange())
        self._failures = failures
        self._total = total
        self.ticks = 0
        self.states: list[BotState] = []

    @property
    def tick_interval(self) -> float:
        """Zero seconds between ticks, so ``_run_with_guard`` never waits."""
        return 0.0

    async def tick(self) -> None:
        """Record ``self.state``, then raise ``_TickFailure`` while ``ticks`` stays
        under ``failures``."""
        self.states.append(self.state)
        self.ticks += 1
        if self.ticks >= self._total:
            self._stop_event.set()
        if self.ticks <= self._failures:
            raise _TickFailure(f"tick {self.ticks} refused")


def _run_guard(failures: int, total: int) -> _FailingTickBot:
    """Drive the real ``_run_with_guard`` over ``total`` ticks and return the
    ``_FailingTickBot`` it ran."""
    bot = _FailingTickBot(failures=failures, total=total)
    asyncio.run(bot._run_with_guard())
    return bot


class TestErrorStateIsReachable:
    def test_the_enum_member_exists(self):
        """Positive control for the ``_run_guard`` assertions below."""
        assert BotState.ERROR.value == "error"

    def test_a_failed_tick_leaves_the_bot_in_error(self):
        """``BotState.ERROR`` was compared against and never written, which pinned
        the fleet ``errored`` count at zero."""
        bot = _run_guard(failures=1, total=2)
        assert bot.ticks == 2, bot.states
        assert bot.states[1] == BotState.ERROR, (
            f"the second tick started in {bot.states[1]}; a failed tick left "
            f"the bot in a state no fleet count reads as errored"
        )

    def test_a_good_tick_clears_it(self):
        """A ``BotState.ERROR`` never cleared would latch on one transient
        failure."""
        bot = _run_guard(failures=1, total=2)
        assert bot.state == BotState.RUNNING, bot.states

    def test_a_run_that_never_fails_never_reaches_error(self):
        """Negative control: the failure branch of ``_run_with_guard`` writes
        ``BotState.ERROR``, and a clean loop never does."""
        bot = _run_guard(failures=0, total=2)
        assert BotState.ERROR not in bot.states
        assert bot.state == BotState.RUNNING


class _Journal:
    """The ``TradeJournal`` readings ``LiveMonitor.analyze`` formats into its
    message."""

    chain_hash = "0" * 64
    record_count = 7
    stats = {
        "trades": 3,
        "harvests": 1,
        "folds": 2,
        "boost_sells": 0,
        "boost_folds": 0,
        "wires": 0,
        "volume": 1234.5,
        "max_dd": 1.5,
    }


class _RecordingLiveMonitor(LiveMonitor):
    """A ``LiveMonitor`` whose ``_call`` records the message in ``sent``.

    ``_call`` is the only method that reaches the network, so overriding it keeps
    ``analyze`` on its real path with nothing leaving the process.
    """

    def __init__(self) -> None:
        super().__init__(api_key="not-a-key", journal=_Journal())
        self._authenticated = True
        self.sent: list[str] = []

    async def _call(self, msg):
        """Append ``msg`` to ``sent`` and answer as the endpoint would."""
        self.sent.append(msg)
        return "recorded"


def _analysis_message(**kwargs) -> str:
    """Return the message ``LiveMonitor.analyze`` handed to ``_call``."""
    monitor = _RecordingLiveMonitor()
    result = asyncio.run(monitor.analyze(**kwargs))
    assert result.get("feedback") == "recorded", result
    assert len(monitor.sent) == 1, monitor.sent
    return monitor.sent[0]


class TestTheAIMonitorIsNotFedZeroes:
    def test_a_none_passive_reads_unavailable(self):
        """``passive_value`` has no source in ``src``; a ``$0.00`` passive made
        every advantage equal the whole portfolio."""
        line = _analysis_message(portfolio=1000.0, passive=None, bots=2)
        assert "Passive: unavailable" in line, line
        assert "Adv: not computed" in line, line
        assert "Passive: $0.00" not in line, line

    def test_a_real_passive_is_still_reported_as_money(self):
        """Positive control: only a ``None`` passive reaches the unavailable
        wording."""
        line = _analysis_message(portfolio=1000.0, passive=400.0, bots=2)
        assert "Passive: $400.00" in line, line
        assert "Adv: $+600.00" in line, line
        assert "unavailable" not in line, line


class _StatusBot:
    """A ``BotManager`` member whose ``get_status`` returns one fixed payload."""

    def __init__(self, bot_id, status):
        self.bot_id = bot_id
        self._status = status

    def get_status(self):
        """Return a copy of this bot's fixed status payload."""
        return dict(self._status)


class _RecordingMonitor:
    """Records the keywords ``check_live_monitor`` passes to ``analyze``."""

    enabled = True
    should_check = True

    def __init__(self):
        self.calls: list[dict] = []

    async def analyze(self, **kwargs):
        """Record ``kwargs`` and answer as a live ``analyze`` would."""
        self.calls.append(kwargs)
        return {"feedback": "ok"}


def _manager_with(*bots) -> tuple[BotManager, _RecordingMonitor]:
    """Return a ``BotManager`` on a private ``EventBus`` holding ``bots``, and the
    ``_RecordingMonitor`` attached to it."""
    manager = BotManager(bus=EventBus())
    monitor = _RecordingMonitor()
    manager._live_monitor = monitor
    for bot in bots:
        manager._bots[bot.bot_id] = bot
    return manager, monitor


class TestTheCallerDoesNotInventTheMissingKey:
    def test_it_sends_passive_as_none(self):
        manager, monitor = _manager_with(_StatusBot("a", {"portfolio_value": 10.0}))
        try:
            asyncio.run(manager.check_live_monitor())
        finally:
            manager.detach_bus()
        assert monitor.calls == [{"portfolio": 10.0, "passive": None, "bots": 1}]

    def test_it_sums_only_the_bots_that_reported(self):
        manager, monitor = _manager_with(
            _StatusBot("a", {"portfolio_value": 10.0}),
            _StatusBot("b", {}),
        )
        try:
            asyncio.run(manager.check_live_monitor())
        finally:
            manager.detach_bus()
        assert monitor.calls[0]["portfolio"] == pytest.approx(10.0)


class TestAPartialPortfolioIsFlagged:
    """``check_live_monitor`` warns ``PARTIAL`` when a bot omits
    ``portfolio_value``."""

    def _warnings(self, manager, capture_log) -> list[str]:
        """Run ``check_live_monitor`` and return the ``acervator.bot`` messages."""
        with capture_log("acervator.bot", logging.WARNING) as records:
            try:
                asyncio.run(manager.check_live_monitor())
            finally:
                manager.detach_bus()
        return [r.getMessage() for r in records]

    def test_a_silent_bot_makes_the_figure_partial(self, capture_log):
        manager, _monitor = _manager_with(
            _StatusBot("a", {"portfolio_value": 10.0}),
            _StatusBot("b", {}),
        )
        messages = self._warnings(manager, capture_log)
        assert any("PARTIAL" in m for m in messages), messages

    def test_a_fleet_that_all_reported_is_not_flagged(self, capture_log):
        """Positive control: the same reader over a complete fleet finds no
        ``PARTIAL`` warning."""
        manager, _monitor = _manager_with(
            _StatusBot("a", {"portfolio_value": 10.0}),
            _StatusBot("b", {"portfolio_value": 20.0}),
        )
        messages = self._warnings(manager, capture_log)
        assert not any("PARTIAL" in m for m in messages), messages
