"""The Indicator Voting Panel keeps its last TA read, and names ONE cause.

WHAT THE OPERATOR HIT, 2026-08-13
He reported the panel showing nothing for several assets and concluded it
was "choking". It was not. From his console log, every selection where the
bot HAD data rendered in 0.55-1.86 s and there were zero empty renders:
CHIP 0.55 s, DOGE 1.86 s, SOL 1.53 s, BICO 1.56 s, IMU 0.98 s, AERO 1.64 s,
BTC 0.87 s. Every failure was one state, and the panel was correct each
time -- BTC 16:01:06 held 11.1 s never fed, BTC 16:04:30 held 4.6 s never
fed, KAT 16:04:34 held 10.0 s never fed. The panel had nothing to show.

THE MECHANISM
The panel is fed from `bot._last_summary`, a value the TRADING tick leaves
behind as a by-product of deciding whether to trade. It is assigned at
exactly two sites in scrumming_bot.py (:7269 and :7513), both behind
`len(candles) >= 30`, and it lives only in memory on the bot object. So:

  1. a restart blanks the whole fleet -- 8 of 34 bots had produced no TA
     at all when he looked, half an hour after a restart;
  2. a bot parked inside its dust band never produces one, because
     `ScrummingBot.tick` (`src/trading/scrumming_bot.py`) returns
     before the TA block. That is
     correct trading behaviour (MEM-258) and is not changed here;
  3. a good reading is thrown away -- BTC emitted "TA Vote: BEARISH
     (conf=0.13, B:2/N:5/S:5)" at 22:00:26 and the restart discarded it.

UNIT 1 (PERSISTS) keeps the reading that was already paid for, and makes it
carry its age. Zero new API calls and zero new TA computation: computing TA
before the early exit would undo exactly the spend MEM-258 exists to avoid.

UNIT 2 (NAMES) replaces the one sentence the panel printed for every empty
case -- "running - no TA read yet (first read can take ~60s; a bot parked
at target evaluates no TA)" -- which offers two causes and leads with the
wrong one. The operator read "~60s", waited, and switched bots for minutes.

WHAT A FAILURE OF EACH TEST MEANS is stated in that test's own docstring.
"""

from __future__ import annotations

import json
import os
import time

import pytest

# `tests/conftest.py` puts the repo root on sys.path before this module
# loads. `qapp` sets QT_QPA_PLATFORM, which Qt reads at construction.
try:
    from PySide6.QtWidgets import QApplication, QLayout

    from src.gui.indicator_panel import (
        IndicatorVotingPanel,
        describe_no_data_cause,
        format_age,
        load_ta_snapshot,
        save_ta_snapshot,
        ta_snapshot_dir,
    )
    from src.gui.main_window import MainWindow
    from src.trading.scrumming_bot import ScrummingBot
except ImportError as _import_exc:  # pragma: no cover
    pytest.skip(f"PySide6 stack unavailable: {_import_exc}", allow_module_level=True)

# The negative fixture: the detectors below must call this sentence a
# conflation, or their verdicts on the new ones mean nothing.
OLD_CONFLATED_SENTENCE = (
    "running — no TA read yet (first read can take ~60s; a bot parked "
    "at target evaluates no TA)"
)

# Phrases that betray which cause a sentence is talking about. A sentence
# may carry markers from its OWN cause and from no other.
CAUSE_MARKERS: dict[str, tuple] = {
    "parked_at_target": ("parked at target",),
    "cold_start": ("cold start", "first read", "no TA read yet"),
    "not_running": ("not running",),
    "no_selection": ("no bot is selected",),
    "too_few_candles": ("too few candles",),
}

# Connectives that turn a diagnosis into a list of possibilities.
DISJUNCTION_TOKENS = (" or ", "either", ";")

FIVE_CAUSES: tuple = (
    ("parked_at_target", {"position": 250.27, "target": 250.17, "delta": 0.10}),
    ("cold_start", {}),
    ("not_running", {"state": "idle"}),
    ("no_selection", {}),
    ("too_few_candles", {"candles": 12, "symbol": "BTC/USD", "timeframe": "1h"}),
)


def foreign_markers(cause: str, message: str) -> list:
    """Markers of OTHER causes found in this cause's sentence."""
    found: list = []
    lowered = message.lower()
    for other, markers in CAUSE_MARKERS.items():
        if other == cause:
            continue
        found.extend(m for m in markers if m.lower() in lowered)
    return found


def disjunctions_in(message: str) -> list:
    """Disjunction connectives found in a message."""
    lowered = message.lower()
    return [t for t in DISJUNCTION_TOKENS if t in lowered]


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the module, constructed headless.

    Qt reads QT_QPA_PLATFORM when the application object is built, not
    when PySide6 is imported, so setting it here is early enough and
    keeps every import in this file at the top of the module.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _destroy_widgets(qapp):
    """Delete every top-level widget after each test.

    Qt keeps a parentless widget alive for the life of the process, and
    an accumulating pile of them takes the suite down with SIGSEGV (exit
    139) at a moving point with no failure summary printed.
    """
    yield
    for widget in list(qapp.topLevelWidgets()):
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()
    qapp.processEvents()


@pytest.fixture
def state_dir(tmp_path):
    """An isolated stand-in for `~/.acervator`.

    Never the real one: these tests write snapshots, and the operator's
    live state directory is read-only to this suite.
    """
    target = tmp_path / "acervator_state"
    target.mkdir()
    return target


@pytest.fixture
def panel(qapp, state_dir):
    """A REAL IndicatorVotingPanel pointed at the isolated state dir."""
    widget = IndicatorVotingPanel()
    widget.set_ta_state_dir(state_dir)
    yield widget
    widget.deleteLater()


def real_reading() -> dict:
    """A payload of the shape the main_window feed site builds.

    Shaped by hand rather than computed, because these tests must not
    call the TA engine -- that is the thing Unit 1 promises not to add.
    """
    return {
        "1h": {
            "bullish": 2,
            "bearish": 5,
            "neutral": 5,
            "net_score": -1.35,
            "confidence": 0.13,
            "direction": "BEARISH",
            "signals": [
                {
                    "indicator": "bollinger",
                    "direction": "BEARISH",
                    "confidence": 0.53,
                    "details": {"bb_pos": 0.53},
                },
                {
                    "indicator": "macd",
                    "direction": "NEUTRAL",
                    "confidence": 0.0,
                    "details": {},
                },
            ],
            "locks": [],
        }
    }


def widget_is_in_a_layout(root, target) -> bool:
    """Walk `root`'s real layout tree looking for `target`.

    `inspect.getsource` plus a substring cannot see a widget that was
    built and never added to a layout. This walks the constructed
    object instead.
    """

    def walk(layout) -> bool:
        if layout is None:
            return False
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is None:
                continue
            if item.widget() is target:
                return True
            child = item.layout()
            if isinstance(child, QLayout) and walk(child):
                return True
        return False

    return walk(root.layout())


class _Config:
    """The handful of BotConfig fields the empty-state decision reads."""

    def __init__(self, symbol="BTC/USD", exchange_id="coinbase", ta_timeframe="1h"):
        self.symbol = symbol
        self.exchange_id = exchange_id
        self.ta_timeframe = ta_timeframe


class _Stats:
    def __init__(self, current_price=0.0, last_error=""):
        self.current_price = current_price
        self.last_error = last_error


class _State:
    def __init__(self, value):
        self.value = value


class _Bot:
    """A bot-shaped argument carrying the REAL position_value_usd property.

    The property is bound off ScrummingBot itself, so the position figure
    in the parked sentence is produced by the same arithmetic the trading
    layer uses rather than by a number invented here.
    """

    position_value_usd = ScrummingBot.position_value_usd

    def __init__(
        self,
        state="running",
        holdings=0.0,
        price=0.0,
        target=0.0,
        parked_ticks=0,
        last_error="",
    ):
        self.config = _Config()
        self.state = _State(state)
        self.stats = _Stats(current_price=price, last_error=last_error)
        self._current_holdings = holdings
        self._last_trade_price = price
        self._quote_to_usd = 1.0
        self._target_balance = target
        self._at_target_counter = parked_ticks


class _WindowShell:
    """The REAL MainWindow decision methods, without a real QMainWindow.

    Both attributes are the function objects off MainWindow itself, so
    the code under test is the shipped code. Constructing an actual
    MainWindow would wire exchanges, timers and the live bot manager,
    which this suite must never touch.
    """

    _ivp_cached_candle_count = MainWindow._ivp_cached_candle_count
    _ivp_empty_state_cause = MainWindow._ivp_empty_state_cause


class TestTheInstrumentWorks:
    """Positive controls. Every test below is void without these."""

    def test_the_store_round_trips(self, state_dir):
        """FAILURE MEANS: the snapshot store cannot persist anything, so
        every Unit 1 test that follows would pass against a panel that
        simply never shows a reading -- proving nothing."""
        payload = real_reading()
        written = save_ta_snapshot(
            "bot-round-trip", "BTC/USD", payload, state_dir=state_dir, taken_at=1000.0
        )
        assert written is not None and written.is_file()
        loaded = load_ta_snapshot("bot-round-trip", state_dir=state_dir)
        assert loaded is not None
        assert loaded["taken_at"] == 1000.0
        assert loaded["symbol"] == "BTC/USD"
        assert loaded["timeframes"]["1h"]["net_score"] == pytest.approx(-1.35)

    def test_an_untouched_directory_yields_nothing(self, state_dir):
        """FAILURE MEANS: the loader invents a reading, and a panel would
        show TA for a bot that never produced any."""
        assert load_ta_snapshot("bot-never-seen", state_dir=state_dir) is None

    def test_the_conflation_detector_flags_the_old_sentence(self):
        """TWO-SIDED CONTROL for Unit 2.

        FAILURE MEANS: the detectors used below are blind, and their
        verdict that the five new sentences are clean would be worthless.
        The sentence the panel actually shipped names TWO causes and
        joins them with a semicolon; both detectors must say so."""
        assert foreign_markers("cold_start", OLD_CONFLATED_SENTENCE) == [
            "parked at target"
        ]
        assert disjunctions_in(OLD_CONFLATED_SENTENCE) == [";"]

    def test_format_age_is_not_a_constant(self):
        """FAILURE MEANS: the age band would print the same text for a
        five-second-old reading and a three-day-old one, and the age
        assertions below would be satisfied by a stuck string."""
        rendered = [format_age(s) for s in (1, 42, 300, 7200, 300000)]
        assert len(set(rendered)) == len(rendered)


class TestUnit1Persists:
    """A reading already paid for is not thrown away."""

    def test_a_stored_reading_is_rendered_when_there_is_no_live_one(
        self, panel, state_dir
    ):
        """FAILURE MEANS: a parked bot still shows a blank panel even
        though its last vote is on disk -- the operator's 2026-08-13
        complaint would be unfixed."""
        save_ta_snapshot(
            "bot-parked",
            "BTC/USD",
            real_reading(),
            state_dir=state_dir,
            taken_at=time.time() - 250,
        )
        panel.show_no_data(
            bot_id="bot-parked",
            symbol="BTC/USD",
            cause="parked_at_target",
            detail={"position": 250.27, "target": 250.17, "delta": 0.10},
        )
        assert panel._table_a.rowCount() == 1
        assert sorted(panel._data) == ["1h"]
        assert panel._showing_stored is True

    def test_the_rendered_reading_carries_its_age(self, panel, state_dir):
        """FAILURE MEANS: an old vote is presented as the current one,
        which the operator has said is worse than a blank panel."""
        save_ta_snapshot(
            "bot-aged",
            "BTC/USD",
            real_reading(),
            state_dir=state_dir,
            taken_at=time.time() - 250,
        )
        panel.show_no_data(bot_id="bot-aged", symbol="BTC/USD", cause="cold_start")
        banner = panel._staleness_label.text()
        assert panel._staleness_label.isVisible() or not panel.isVisible()
        assert panel._staleness_label.isHidden() is False
        assert "NOT CURRENT" in banner
        assert "4m 1" in banner or "4m 0" in banner, banner
        assert "ago" in banner

    def test_the_age_band_is_in_a_layout(self, panel):
        """FAILURE MEANS: the age exists on an object nobody can see.

        A widget built and never added to a layout is invisible, and a
        source scan cannot tell the two apart. This walks the tree."""
        assert widget_is_in_a_layout(panel, panel._staleness_label)

    def test_a_bot_that_never_computed_one_renders_an_empty_state(self, panel):
        """FAILURE MEANS: the panel fabricates, or shows another bot's
        reading, for a bot that has produced nothing."""
        panel.show_no_data(bot_id="bot-virgin", symbol="KAT/USD", cause="cold_start")
        assert panel._data == {}
        assert panel._table_a.rowCount() == 0
        assert panel._showing_stored is False
        assert panel._staleness_label.isHidden() is True
        assert panel._summary_label.text().startswith("No TA data")

    def test_a_restart_does_not_blank_a_bot_that_had_a_reading(self, qapp, state_dir):
        """THE HEADLINE PROPERTY.

        FAILURE MEANS: a restart still discards every vote in the fleet,
        which is what left 8 of 34 bots blank half an hour after the
        22:35 UTC restart. A brand-new panel object holds nothing in
        memory; anything it shows came off the disk."""
        first = IndicatorVotingPanel()
        first.set_ta_state_dir(state_dir)
        first.update_data(real_reading(), "BTC/USD")
        first.remember_ta("bot-survivor", "BTC/USD", real_reading())
        first.deleteLater()

        after_restart = IndicatorVotingPanel()
        after_restart.set_ta_state_dir(state_dir)
        assert after_restart._data == {}, "fresh panel started with data"
        after_restart.show_no_data(
            bot_id="bot-survivor", symbol="BTC/USD", cause="cold_start"
        )
        assert sorted(after_restart._data) == ["1h"]
        assert after_restart._showing_stored is True
        assert "NOT CURRENT" in after_restart._staleness_label.text()
        after_restart.deleteLater()

    def test_a_live_feed_takes_the_stale_band_down(self, panel, state_dir):
        """FAILURE MEANS: the 'not current' banner survives over a table
        that has since been refilled with live data -- the panel would
        then be lying in the opposite direction."""
        save_ta_snapshot(
            "bot-refed",
            "BTC/USD",
            real_reading(),
            state_dir=state_dir,
            taken_at=time.time() - 600,
        )
        panel.show_no_data(bot_id="bot-refed", symbol="BTC/USD", cause="cold_start")
        assert panel._staleness_label.isHidden() is False
        panel.update_data(real_reading(), "BTC/USD")
        assert panel._staleness_label.isHidden() is True
        assert panel._staleness_label.text() == ""
        assert panel._showing_stored is False

    def test_an_unchanged_reading_is_not_rewritten(self, panel, state_dir):
        """FAILURE MEANS: the dashboard rewrites the same file every 2 s
        per bot, putting avoidable disk I/O on the Qt GUI thread -- the
        thread every coroutine in this application already shares."""
        payload = real_reading()
        panel.remember_ta("bot-dedupe", "BTC/USD", payload)
        target = ta_snapshot_dir(state_dir) / next(
            iter(p.name for p in ta_snapshot_dir(state_dir).glob("*.json"))
        )
        first_write = target.stat().st_mtime_ns
        for _ in range(20):
            panel.remember_ta("bot-dedupe", "BTC/USD", payload)
        assert target.stat().st_mtime_ns == first_write

    def test_a_changed_reading_is_written(self, panel, state_dir):
        """PAIRED CONTROL for the dedupe above.

        FAILURE MEANS: the dedupe is not skipping duplicates, it is
        refusing to write at all, and the panel would show a reading
        that never updates."""
        panel.remember_ta("bot-moves", "BTC/USD", real_reading())
        moved = real_reading()
        moved["1h"]["net_score"] = 2.5
        panel.remember_ta("bot-moves", "BTC/USD", moved)
        stored = load_ta_snapshot("bot-moves", state_dir=state_dir)
        assert stored is not None
        assert stored["timeframes"]["1h"]["net_score"] == pytest.approx(2.5)

    def test_a_corrupt_snapshot_is_treated_as_absent(self, panel, state_dir):
        """FAILURE MEANS: a truncated file crashes the dashboard tick, or
        worse, renders as a reading with no establishable age."""
        save_ta_snapshot("bot-corrupt", "BTC/USD", real_reading(), state_dir=state_dir)
        written = next(iter(ta_snapshot_dir(state_dir).glob("*.json")))
        written.write_text("{not json", encoding="utf-8")
        panel._ta_snapshot_cache.clear()
        panel.show_no_data(bot_id="bot-corrupt", symbol="BTC/USD", cause="cold_start")
        assert panel._data == {}
        assert panel._summary_label.text().startswith("No TA data")

    def test_a_snapshot_with_no_timestamp_is_refused(self, state_dir):
        """FAILURE MEANS: a reading whose age cannot be established gets
        shown anyway. The age is the whole point; without it the panel
        is back to presenting an old vote as current."""
        directory = ta_snapshot_dir(state_dir)
        directory.mkdir(parents=True, exist_ok=True)
        save_ta_snapshot("bot-undated", "BTC/USD", real_reading(), state_dir=state_dir)
        path = next(iter(directory.glob("*.json")))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["taken_at"] = 0
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert load_ta_snapshot("bot-undated", state_dir=state_dir) is None

    def test_a_bot_id_cannot_escape_the_snapshot_directory(self, state_dir):
        """FAILURE MEANS: a bot_id carrying path separators writes
        outside the snapshot directory."""
        written = save_ta_snapshot(
            "../../evil", "BTC/USD", real_reading(), state_dir=state_dir
        )
        assert written is not None
        assert written.parent == ta_snapshot_dir(state_dir)
        assert load_ta_snapshot("../../evil", state_dir=state_dir) is not None

    def test_the_snapshot_directory_is_bounded(self, state_dir):
        """FAILURE MEANS: a directory that grows without limit.

        One file per bot is written for the life of the install, and a
        bot_id is never reused, so renames and deletions would otherwise
        accumulate forever. The bound is checked against the constant
        rather than a literal, so raising the constant does not silently
        retire the test."""
        from src.gui.indicator_panel import _TA_SNAPSHOT_KEEP

        payload = real_reading()
        for index in range(_TA_SNAPSHOT_KEEP + 25):
            save_ta_snapshot(
                f"bot-bulk-{index:05d}",
                "BTC/USD",
                payload,
                state_dir=state_dir,
                taken_at=1000.0 + index,
            )
        remaining = list(ta_snapshot_dir(state_dir).glob("*.json"))
        assert len(remaining) <= _TA_SNAPSHOT_KEEP, len(remaining)
        assert len(remaining) >= _TA_SNAPSHOT_KEEP - 1, (
            "pruning removed far more than the bound; a live bot's "
            "reading would be thrown away"
        )

    def test_pruning_keeps_the_newest(self, state_dir):
        """PAIRED CONTROL for the bound above.

        FAILURE MEANS: the bound is held by deleting the wrong files, so
        the bots the operator is actually watching lose their readings
        while stale ones survive."""
        from src.gui.indicator_panel import _TA_SNAPSHOT_KEEP

        payload = real_reading()
        for index in range(_TA_SNAPSHOT_KEEP + 10):
            save_ta_snapshot(
                f"bot-order-{index:05d}",
                "BTC/USD",
                payload,
                state_dir=state_dir,
                taken_at=1000.0 + index,
            )
        newest = f"bot-order-{_TA_SNAPSHOT_KEEP + 9:05d}"
        assert load_ta_snapshot(newest, state_dir=state_dir) is not None

    def test_an_unwritable_directory_does_not_raise(self, panel, tmp_path):
        """FAILURE MEANS: a disk problem takes the dashboard tick down.

        A snapshot is a convenience. A file where the directory should be
        makes mkdir fail, and the tick must survive it."""
        blocked = tmp_path / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        panel.set_ta_state_dir(blocked)
        assert (
            save_ta_snapshot(
                "bot-blocked", "BTC/USD", real_reading(), state_dir=blocked
            )
            is None
        )
        panel.remember_ta("bot-blocked", "BTC/USD", real_reading())
        panel.show_no_data(bot_id="bot-blocked", symbol="BTC/USD", cause="cold_start")
        assert panel._summary_label.text().startswith("No TA data")


class TestUnit2Names:
    """The empty state names the ONE cause that applies."""

    def test_five_causes_render_five_different_messages(self, panel):
        """FAILURE MEANS: the panel is still answering different
        situations with one sentence, which is what sent the operator
        switching bots for minutes."""
        messages = []
        for cause, detail in FIVE_CAUSES:
            panel.show_no_data(
                bot_id="bot-probe", symbol="BTC/USD", cause=cause, detail=detail
            )
            messages.append(panel._no_data_message)
        assert len(set(messages)) == 5, messages

    def test_each_message_reaches_a_visible_label(self, panel):
        """FAILURE MEANS: the sentence is computed and never displayed.

        Read off the constructed widget, not off the source."""
        for cause, detail in FIVE_CAUSES:
            panel.show_no_data(
                bot_id="bot-probe", symbol="BTC/USD", cause=cause, detail=detail
            )
            assert panel._no_data_message in panel._summary_label.text()
            assert widget_is_in_a_layout(panel, panel._summary_label)

    def test_no_message_names_a_second_cause(self, panel):
        """FAILURE MEANS: a diagnosis is still offering the operator a
        list to work through. Proven non-blind by
        test_the_conflation_detector_flags_the_old_sentence."""
        for cause, detail in FIVE_CAUSES:
            panel.show_no_data(
                bot_id="bot-probe", symbol="BTC/USD", cause=cause, detail=detail
            )
            intruders = foreign_markers(cause, panel._no_data_message)
            assert intruders == [], (cause, intruders, panel._no_data_message)

    def test_no_message_contains_a_disjunction(self, panel):
        """FAILURE MEANS: the sentence joins alternatives instead of
        stating one. Proven non-blind by the same control."""
        for cause, detail in FIVE_CAUSES:
            panel.show_no_data(
                bot_id="bot-probe", symbol="BTC/USD", cause=cause, detail=detail
            )
            found = disjunctions_in(panel._no_data_message)
            assert found == [], (cause, found, panel._no_data_message)

    def test_each_message_names_its_own_cause(self, panel):
        """FAILURE MEANS: five distinct sentences that are distinct for
        some reason other than naming the right cause."""
        for cause, detail in FIVE_CAUSES:
            panel.show_no_data(
                bot_id="bot-probe", symbol="BTC/USD", cause=cause, detail=detail
            )
            markers = CAUSE_MARKERS[cause]
            message = panel._no_data_message.lower()
            assert any(m.lower() in message for m in markers), (
                cause,
                panel._no_data_message,
            )

    def test_the_parked_message_carries_position_and_target(self, panel):
        """FAILURE MEANS: the operator is told the bot is parked without
        the two figures that let him check whether it should be."""
        panel.show_no_data(
            bot_id="bot-parked",
            symbol="BTC/USD",
            cause="parked_at_target",
            detail={"position": 250.27, "target": 250.17, "delta": 0.10},
        )
        message = panel._no_data_message
        assert "250.27" in message
        assert "250.17" in message

    def test_an_unknown_cause_is_reported_not_guessed(self):
        """FAILURE MEANS: a caller typo silently produces a confident
        sentence about a cause nobody established."""
        text = describe_no_data_cause("banana", {})
        assert "banana" in text
        assert "cold start" not in text.lower()


class TestMainWindowPicksTheCause:
    """The REAL MainWindow decision function, one case per cause."""

    def test_a_parked_bot_is_named_parked(self):
        """FAILURE MEANS: the bot's own record of the dust-band exit is
        not reaching the surface, and the panel falls back to guessing.
        `_at_target_counter` is incremented on the parked return in
        ScrummingBot.tick and zeroed as soon as the tick gets past it."""
        bot = _Bot(
            state="running", holdings=2.0, price=125.135, target=250.17, parked_ticks=7
        )
        cause, detail = _WindowShell()._ivp_empty_state_cause(bot, "bid-1")
        assert cause == "parked_at_target"
        assert detail["position"] == pytest.approx(250.27)
        assert detail["target"] == pytest.approx(250.17)
        assert detail["delta"] == pytest.approx(0.10)

    def test_a_running_bot_with_no_reading_is_a_cold_start(self):
        """FAILURE MEANS: a genuinely transient state is reported as the
        permanent one, which is the same defect with the signs flipped."""
        bot = _Bot(state="running", holdings=1.0, price=100.0, target=50.0)
        cause, _ = _WindowShell()._ivp_empty_state_cause(bot, "bid-2")
        assert cause == "cold_start"

    def test_an_idle_bot_is_named_not_running(self):
        """FAILURE MEANS: a bot the operator never started is reported as
        slow rather than as stopped."""
        bot = _Bot(state="idle")
        cause, detail = _WindowShell()._ivp_empty_state_cause(bot, "bid-3")
        assert cause == "not_running"
        assert detail["state"] == "idle"

    def test_a_bot_in_error_carries_its_message(self):
        """FAILURE MEANS: the one state with an actionable message
        discards it."""
        bot = _Bot(state="error", last_error="auth rejected")
        cause, detail = _WindowShell()._ivp_empty_state_cause(bot, "bid-4")
        assert cause == "bot_error"
        assert detail["error"] == "auth rejected"

    def test_a_missing_bot_is_named_missing(self):
        """FAILURE MEANS: a selected bot that has gone from the fleet is
        described as if it were merely slow."""
        cause, _ = _WindowShell()._ivp_empty_state_cause(None, "bid-5")
        assert cause == "bot_missing"

    def test_a_short_candle_cache_is_named(self):
        """Drives the REAL MarketDataPool: a slot is inserted into the
        live pool's cache dict and read back through the shipped
        `_candle_key`.

        FAILURE MEANS: a bot blocked by the 30-candle gate --
        `ScrummingBot.tick` (`src/trading/scrumming_bot.py`) and
        `_tick_initial_entry` (`src/trading/scrumming/tick_phases.py`)
        -- is reported as a cold start, and
        the operator waits for a read that cannot happen."""
        from src.exchange.data_pool import CacheEntry, _candle_key, get_data_pool

        pool = get_data_pool()
        key = _candle_key("coinbase", "BTC/USD", "1h")
        previous = pool._candles.get(key)
        pool._candles[key] = CacheEntry(
            exchange_id="coinbase",
            symbol="BTC/USD",
            timeframe="1h",
            candles=[[0, 1.0, 1.0, 1.0, 1.0, 1.0]] * 12,
            fetch_time=time.time(),
        )
        try:
            bot = _Bot(state="running", holdings=1.0, price=100.0, target=50.0)
            cause, detail = _WindowShell()._ivp_empty_state_cause(bot, "bid-6")
        finally:
            if previous is None:
                pool._candles.pop(key, None)
            else:
                pool._candles[key] = previous
        assert cause == "too_few_candles"
        assert detail["candles"] == 12
        assert detail["symbol"] == "BTC/USD"
        assert detail["timeframe"] == "1h"

    def test_a_full_candle_cache_is_not_named(self):
        """PAIRED CONTROL for the test above.

        FAILURE MEANS: the candle check reports 'too few' regardless of
        what the cache holds, so its pass proves nothing."""
        from src.exchange.data_pool import CacheEntry, _candle_key, get_data_pool

        pool = get_data_pool()
        key = _candle_key("coinbase", "BTC/USD", "1h")
        previous = pool._candles.get(key)
        pool._candles[key] = CacheEntry(
            exchange_id="coinbase",
            symbol="BTC/USD",
            timeframe="1h",
            candles=[[0, 1.0, 1.0, 1.0, 1.0, 1.0]] * 100,
            fetch_time=time.time(),
        )
        try:
            bot = _Bot(state="running", holdings=1.0, price=100.0, target=50.0)
            cause, _ = _WindowShell()._ivp_empty_state_cause(bot, "bid-7")
        finally:
            if previous is None:
                pool._candles.pop(key, None)
            else:
                pool._candles[key] = previous
        assert cause == "cold_start"

    def test_the_five_causes_the_window_can_pick_all_have_wording(self):
        """FAILURE MEANS: MainWindow emits a token the panel cannot
        render, and the operator gets 'unrecognised cause'."""
        for token in (
            "bot_missing",
            "not_running",
            "bot_error",
            "parked_at_target",
            "too_few_candles",
            "cold_start",
            "no_selection",
            "new_bot",
        ):
            text = describe_no_data_cause(token, {"state": "idle"})
            assert "unrecognised cause" not in text, token
