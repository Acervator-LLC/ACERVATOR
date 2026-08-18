"""An Extractor may not be created without a Scrumming Bot to pay back.

THE REQUIREMENT (operator, 2026-08-10)
"Given the design change of the Extractor bot as a sibling of the
Scrumming Bot, it would seem logical to require a Scrumming Bot first."

An Extractor works in one base currency and hands that currency back
when it closes a position. It goes to the Scrumming Bot that HOLDS that
currency, which raises its target balance to keep the gain. With no such
bot the money has nowhere to go. Requiring the holder to exist BEFORE
the Extractor is created removes that case by construction, rather than
meeting it later with a live position already open.

REFUSED AT CREATION, TOLERATED AT RESTORE
This is the asymmetry the whole item turns on, and the last test in this
file is the one that proves it survived.

The wizard refuses. Nothing has been bought, nothing has been written,
and the operator retypes a form.

The restore path does NOT refuse, deliberately. An Extractor whose
parent was deleted after the fact still holds a real position on a real
exchange. Refusing to load it would leave that position unmanaged -- no
exit, no accounting, real money in it -- and the saved record would then
be erased by the next save, which rebuilds the roster from the
registered set. A rejected form costs nothing; a stranded position costs
money.

TWO REASONS, NEVER ONE
`find_parent_bot_for_base_currency` answers nothing in two different
situations: when NO Scrumming Bot holds the currency, and when TWO OR
MORE do and it will not guess an owner. Both refuse creation, but the
operator's remedy is opposite -- create a bot, versus decide which of
several existing ones is the parent -- so the two messages must differ.
A single "no parent found" would send the operator to make a third ETH
bot when the problem was that there were already two.

EXCHANGE BOUND
Scrumming (parent) and Extractor (sibling) live on one exchange. There
is no cross-exchange arbitrage. A holder on another venue is not a
parent however well its currency matches, so it does not satisfy the
requirement. Rows 4a/4b below differ in the holder's exchange and in
nothing else, so 4b refusing can only be the exchange.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.gui.bot_wizard as bot_wizard  # noqa: E402
import src.gui.main_window as main_window  # noqa: E402
import src.trading.extractor_bot as extractor_bot  # noqa: E402
from src.core.event_bus import EventBus  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402
from src.trading.bot_container import BotManager, BotMode  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

COINBASE = "coinbase"
KRAKEN = "kraken"


# ----------------------------------------------------------------------
# The books
# ----------------------------------------------------------------------
def _scrumming_bot(bot_id: str, target_asset: str, exchange: str):
    """One Scrumming Bot on the manager's books, holding one asset.

    Built without running the real constructor, which would want an
    exchange, a bus and a live balance. The requirement is decided from
    the bot's type and its settings, and both of those are real here.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = bot_id
    bot.config = type("_Cfg", (), {
        "exchange_id": exchange,
        "mode": BotMode.SCRUMMING,
        "target_asset": target_asset,
        "base_currency": "USD",
    })()
    return bot


def _manager(holders) -> BotManager:
    """A real BotManager holding the given bots, on its own private bus.

    Real, because the lookup being exercised is the shipped one. Private
    bus, so nothing in this file can reach a live handler.
    """
    manager = BotManager(bus=EventBus())
    for bot_id, target_asset, exchange in holders:
        manager._bots[bot_id] = _scrumming_bot(bot_id, target_asset, exchange)
    return manager


@pytest.fixture
def books():
    made: list[BotManager] = []

    def _make(holders) -> BotManager:
        manager = _manager(holders)
        made.append(manager)
        return manager

    yield _make
    for manager in made:
        manager.detach_bus()


# ----------------------------------------------------------------------
# The window, reduced to what the creation path actually touches
# ----------------------------------------------------------------------
class _Log:
    def __init__(self):
        self.entries: list[tuple[str, str]] = []

    def log(self, msg, level="info"):
        self.entries.append((level, msg))

    def text(self) -> str:
        return "\n".join(m for _, m in self.entries)


class _Spool:
    def __init__(self):
        self.entries: list[tuple[str, str]] = []

    def notify(self, msg, level="info"):
        self.entries.append((level, msg))


class _StatusBar:
    def __init__(self):
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, msg, timeout=0):  # noqa: N802 - Qt's name
        self.messages.append((msg, timeout))


class _Dialogs:
    """Stands in for QMessageBox and records what the operator saw."""

    def __init__(self):
        self.critical_calls: list[tuple[str, str]] = []

    def critical(self, parent, title, text):
        self.critical_calls.append((title, text))

    def question(self, *args, **kwargs):
        raise AssertionError(
            f"the Extractor path must not reach a question dialog "
            f"(called with {args!r} {kwargs!r})")

    def warning(self, parent, title, text):
        self.critical_calls.append((title, text))

    def last_text(self) -> str:
        return self.critical_calls[-1][1] if self.critical_calls else ""


class _Window:
    """The wizard's host. Only the attributes `_create_bot` reads.

    The methods under test are bound from the real MainWindow, so what
    runs here is the shipped implementation and not a paraphrase of it.
    """

    def __init__(self, manager):
        self._bot_manager = manager
        self._status_log = _Log()
        self._spool = _Spool()
        self._settings = None
        self._indicator_panel = None
        self._bar = _StatusBar()

    def statusBar(self):  # noqa: N802 - Qt's name
        return self._bar

    _extractor_parent_refusal = MainWindow._extractor_parent_refusal
    _refuse_extractor_without_parent = (
        MainWindow._refuse_extractor_without_parent)
    _create_bot = MainWindow._create_bot


#: Every wizard opening in the current test, as
#: ``(exchanges, defaults, parent)``. A refusal that skipped the wizard
#: entirely would look identical to one the operator was shown, so the
#: openings are recorded and asserted on.
WIZARD_OPENINGS: list[tuple] = []

#: `QWizard.DialogCode.Accepted`. Named here rather than read off the
#: stub instance so no method reaches for an attribute its own __init__
#: never set.
_ACCEPTED = 1


class _AcceptedWizard:
    """A creation wizard the operator filled in and accepted."""

    config: dict = {}

    class DialogCode:
        Accepted = _ACCEPTED
        Rejected = 0

    def __init__(self, exchanges, defaults, parent):
        WIZARD_OPENINGS.append((exchanges, defaults, parent))

    def exec(self):
        return _ACCEPTED

    def get_bot_config(self) -> dict:
        return dict(self.config)


def _wizard_returning(config: dict):
    return type("_Wizard", (_AcceptedWizard,), {"config": config})


class _ReachedConstruction(BaseException):
    """Raised in place of building an ExtractorBot.

    A BaseException and not an Exception, because `_create_bot` wraps
    its whole body in `except Exception` -- an ordinary exception would
    be caught there and logged as "Failed to create bot", which is
    indistinguishable from a refusal. This one escapes, so "control
    reached the constructor" and "control was refused before it" can
    never be confused with each other.
    """

    def __init__(self, config):
        super().__init__("ExtractorBot constructed")
        self.config = config


class _ProbeExtractorBot:
    def __init__(self, config, exchange, **kwargs):
        raise _ReachedConstruction((config, exchange, kwargs))


CREATED_BOT_ID = "created-extractor"


class _RecordingExtractorBot:
    """A stand-in the BotManager can actually register.

    The probe above stops at construction, which is enough to show that
    a refusal happened BEFORE it. It is not enough to show that nothing
    was written, because a bot that was never constructed can never be
    registered either -- the claim would hold no matter what the guard
    did. This one lets the creation path run on into `register`, which
    is what puts a bot in the roster that `save_state` writes from. Now
    "the roster is unchanged" is a claim the guard can fail.
    """

    def __init__(self, config, exchange, **kwargs):
        self.config = config
        self.exchange = exchange
        self.options = dict(kwargs)
        self.bot_id = CREATED_BOT_ID


def _extractor_config(base_currency, exchange: str = COINBASE) -> dict:
    return {
        "mode": "extractor",
        "exchange_id": exchange,
        "base_currency": base_currency,
        "target_asset": "*",
        "extractor_chunk_size_usd": 100.0,
    }


def _open_wizard(monkeypatch, manager, config, extractor_class):
    """Open the creation wizard on these books, with the given
    stand-in for ExtractorBot. Returns ``(window, dialogs)``."""
    window = _Window(manager)
    dialogs = _Dialogs()
    WIZARD_OPENINGS.clear()
    monkeypatch.setattr(main_window, "QMessageBox", dialogs)
    monkeypatch.setattr(
        bot_wizard, "BotCreationWizard", _wizard_returning(config))
    monkeypatch.setattr(extractor_bot, "ExtractorBot", extractor_class)
    return window, dialogs


def _run_wizard(monkeypatch, manager, config):
    """Open the creation wizard and stop the moment a bot is built.

    Returns ``(window, dialogs, reached_construction)``.
    """
    window, dialogs = _open_wizard(
        monkeypatch, manager, config, _ProbeExtractorBot)
    reached = False
    try:
        window._create_bot(exchange_id=config["exchange_id"])
    except _ReachedConstruction:
        reached = True
    return window, dialogs, reached


def _run_wizard_to_registration(monkeypatch, manager, config):
    """Open the creation wizard and let it finish, registration and all.

    Returns ``(window, dialogs)``. Use where the question is what ended
    up on the books, not where control stopped.
    """
    window, dialogs = _open_wizard(
        monkeypatch, manager, config, _RecordingExtractorBot)
    window._create_bot(exchange_id=config["exchange_id"])
    return window, dialogs


# ----------------------------------------------------------------------
# 1 -- nobody holds it
# ----------------------------------------------------------------------
class TestNoHolder:
    def test_creation_is_refused(self, monkeypatch, books):
        manager = books([("scrum-btc", "BTC", COINBASE)])
        _win, dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        assert reached is False, (
            "the ExtractorBot was constructed with no Scrumming Bot "
            "holding ETH")
        assert len(dialogs.critical_calls) == 1, (
            "the refusal was silent; the operator would see a wizard "
            "close and no bot appear")

    def test_the_operator_is_told_to_create_the_parent_first(
            self, monkeypatch, books):
        manager = books([("scrum-btc", "BTC", COINBASE)])
        _win, dialogs, _reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        text = dialogs.last_text()
        assert "ETH" in text
        assert COINBASE in text
        assert "Create a Scrumming Bot" in text, (
            f"the remedy is not stated; operator saw: {text!r}")

    def test_no_bot_is_created_and_no_state_is_written(
            self, monkeypatch, books):
        """The refusal happens before construction AND before
        registration, so the roster is exactly what it was. Absence from
        the roster is what keeps the save timer from writing anything:
        `save_state` rebuilds the saved bots from the registered set.

        This runs the creation path all the way through registration --
        the constructor is not made to explode here -- so the roster
        staying unchanged is a claim the guard can actually fail. Its
        control is the next test, where one holder exists and the same
        run DOES put a bot on the books.
        """
        manager = books([("scrum-btc", "BTC", COINBASE)])
        before = set(manager._bots)
        _run_wizard_to_registration(
            monkeypatch, manager, _extractor_config("ETH"))

        assert set(manager._bots) == before, (
            "the wizard put a bot on the books; the next save writes it "
            "to bot_state.json")
        assert CREATED_BOT_ID not in manager._bots

    def test_control_the_same_run_does_register_when_a_parent_exists(
            self, monkeypatch, books):
        """CONTROL for the test above. Without it, "the roster is
        unchanged" would also pass if registration never happened for
        some unrelated reason.
        """
        manager = books([("scrum-eth", "ETH", COINBASE)])
        _run_wizard_to_registration(
            monkeypatch, manager, _extractor_config("ETH"))

        assert CREATED_BOT_ID in manager._bots, (
            "an allowed creation did not reach registration, so the "
            "refusal test above proves nothing")

    def test_the_refusal_is_on_the_record(self, monkeypatch, books):
        manager = books([("scrum-btc", "BTC", COINBASE)])
        window, _dialogs, _reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        assert any(level == "error" and "REFUSED" in msg
                   for level, msg in window._status_log.entries), (
            f"nothing in the activity log records the refusal: "
            f"{window._status_log.entries!r}")

    def test_the_wizard_was_opened_before_it_was_refused(
            self, monkeypatch, books):
        """CONTROL for every `reached is False` in this file. A wizard
        that never opened would also never construct a bot, so without
        this the refusal assertions could be satisfied by a broken
        creation path rather than by the requirement.
        """
        manager = books([("scrum-btc", "BTC", COINBASE)])
        window, _dialogs, _reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        assert len(WIZARD_OPENINGS) == 1, (
            "the creation wizard was never opened")
        _exchanges, _defaults, parent = WIZARD_OPENINGS[0]
        assert parent is window


# ----------------------------------------------------------------------
# 2 -- two hold it, and that is a different problem
# ----------------------------------------------------------------------
class TestTwoHolders:
    HOLDERS = [("scrum-eth-a", "ETH", COINBASE),
               ("scrum-eth-b", "ETH", COINBASE)]

    def test_creation_is_refused(self, monkeypatch, books):
        manager = books(self.HOLDERS)
        _win, dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        assert reached is False, (
            "an Extractor was created against an ambiguous parent; the "
            "return would raise the wrong bot's target")
        assert len(dialogs.critical_calls) == 1

    def test_both_candidates_are_named(self, monkeypatch, books):
        """The operator cannot decide between bots nobody listed."""
        manager = books(self.HOLDERS)
        _win, dialogs, _reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        text = dialogs.last_text()
        assert "scrum-eth-a" in text
        assert "scrum-eth-b" in text

    def test_the_message_differs_from_the_no_holder_message(
            self, monkeypatch, books):
        """THE distinction. The remedies are opposite: one wants a bot
        created, the other wants two reduced to one. A shared message
        would send the operator to build a third ETH bot.
        """
        crowded = books(self.HOLDERS)
        _w1, d_two, _r1 = _run_wizard(
            monkeypatch, crowded, _extractor_config("ETH"))

        empty = books([("scrum-btc", "BTC", COINBASE)])
        _w2, d_none, _r2 = _run_wizard(
            monkeypatch, empty, _extractor_config("ETH"))

        assert d_two.last_text() != d_none.last_text()
        assert "ambiguous" in d_two.last_text()
        assert "Create a Scrumming Bot" not in d_two.last_text(), (
            "the ambiguous case tells the operator to create another "
            "holder, which is the opposite of the remedy")


# ----------------------------------------------------------------------
# 3 -- exactly one holder is the whole requirement
# ----------------------------------------------------------------------
class TestExactlyOneHolder:
    def test_creation_proceeds(self, monkeypatch, books):
        """POSITIVE CONTROL for every refusal above. If creation could
        not proceed here, `reached is False` would prove nothing --
        every test in this file would pass with the wizard simply
        broken.
        """
        manager = books([("scrum-eth", "ETH", COINBASE)])
        _win, dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH"))

        assert reached is True, (
            "creation did not reach the ExtractorBot constructor even "
            "though one Scrumming Bot holds ETH")
        assert dialogs.critical_calls == [], (
            f"an allowed creation still showed a refusal: "
            f"{dialogs.critical_calls!r}")


# ----------------------------------------------------------------------
# 4 -- the holder must be on the same exchange
# ----------------------------------------------------------------------
class TestExchangeBound:
    """4a and 4b are one pair. They differ in the holder's exchange and
    in nothing else, so 4b refusing can only be the exchange."""

    def test_4a_a_holder_on_this_exchange_satisfies_it(
            self, monkeypatch, books):
        manager = books([("scrum-eth", "ETH", COINBASE)])
        _win, _dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH", COINBASE))
        assert reached is True

    def test_4b_the_only_holder_is_on_another_exchange(
            self, monkeypatch, books):
        manager = books([("scrum-eth", "ETH", KRAKEN)])
        _win, dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config("ETH", COINBASE))

        assert reached is False, (
            "a Kraken bot was accepted as the parent of a Coinbase "
            "Extractor; there is no cross-exchange arbitrage and the "
            "return would pay a bot that never received the money")
        assert "Create a Scrumming Bot" in dialogs.last_text(), (
            "an off-exchange holder must read as NO holder, not as an "
            "ambiguous one")


# ----------------------------------------------------------------------
# 5 -- the asset is matched loosely, exactly as the lookup matches it
# ----------------------------------------------------------------------
class TestAssetMatching:
    @pytest.mark.parametrize("held,asked", [
        ("ETH", "eth"),
        ("eth", "ETH"),
        ("ETH", "  ETH  "),
        ("  ETH  ", "ETH"),
    ], ids=["asked lower", "held lower", "asked padded", "held padded"])
    def test_case_and_spaces_do_not_break_the_match(
            self, monkeypatch, books, held, asked):
        manager = books([("scrum-eth", held, COINBASE)])
        _win, dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config(asked))

        assert reached is True, (
            f"holder {held!r} did not satisfy an Extractor asking "
            f"{asked!r}; operator saw: {dialogs.last_text()!r}")

    def test_a_different_asset_still_refuses(self, monkeypatch, books):
        """CONTROL for the four rows above. Without this, a match that
        accepted anything at all would pass every one of them."""
        manager = books([("scrum-eth", "ETH", COINBASE)])
        _win, _dialogs, reached = _run_wizard(
            monkeypatch, manager, _extractor_config("SOL"))
        assert reached is False


# ----------------------------------------------------------------------
# 6 -- an unavailable roster is not a satisfied requirement
# ----------------------------------------------------------------------
class TestNoRoster:
    def test_creation_is_refused_when_there_is_no_bot_manager(self):
        """A requirement that cannot be checked has not been met.
        Proceeding here would create exactly the parentless Extractor
        the item exists to prevent.
        """
        window = _Window(None)
        reason = window._extractor_parent_refusal("ETH", COINBASE)
        assert reason is not None
        assert "roster is not available" in reason


# ----------------------------------------------------------------------
# 7 -- THE LOAD-BEARING TEST: restore still tolerates a missing parent
# ----------------------------------------------------------------------
class TestRestoreStillTolerates:
    """If this fails, the item has done real harm.

    An Extractor whose parent was deleted holds a live position. It must
    still load, or that position is unmanaged and its saved record is
    erased by the next save.
    """

    @staticmethod
    def _extractor_record(bot_id: str) -> dict:
        return {
            "bot_id": bot_id,
            "config": {
                "exchange_id": COINBASE,
                "symbol": "ETH/USD",
                "mode": "extractor",
                "base_currency": "ETH",
                "target_asset": "*",
            },
            "state_when_saved": "idle",
        }

    def test_a_parentless_extractor_still_loads(self):
        manager = BotManager(bus=EventBus())
        try:
            manager.restore_bots_from_state(
                {"bots": {"orphan-extractor":
                          self._extractor_record("orphan-extractor")}})
            loaded = set(manager._bots)
        finally:
            manager.detach_bus()

        assert "orphan-extractor" in loaded, (
            "the restore path refused an Extractor with no parent. Its "
            "open position is now unmanaged and the next save will "
            "erase its record.")

    def test_it_is_not_in_the_skip_ledger(self):
        """A bot can also be lost by being skipped rather than refused.
        The ledger is where restore records what it did not load.
        """
        manager = BotManager(bus=EventBus())
        try:
            manager.restore_bots_from_state(
                {"bots": {"orphan-extractor":
                          self._extractor_record("orphan-extractor")}})
            ledger = dict(manager._restore_ledger or {})
        finally:
            manager.detach_bus()

        assert "orphan-extractor" not in ledger, (
            f"restore skipped the parentless Extractor: "
            f"{ledger.get('orphan-extractor')!r}")

    def test_the_restore_path_does_not_consult_the_parent_lookup(self):
        """CONTROL: the two tests above would also pass if restore
        happened to have a parent on its books by accident. This one
        makes the lookup explode, so any call from the restore path
        fails loudly instead of quietly agreeing.
        """
        manager = BotManager(bus=EventBus())

        def _explode(*args, **kwargs):
            raise AssertionError(
                "restore_bots_from_state consulted the parent lookup; "
                "the creation-time requirement has leaked into the "
                "load path")

        manager.find_parent_bot_for_base_currency = _explode
        manager.list_parent_bot_candidates_for_base_currency = _explode
        try:
            manager.restore_bots_from_state(
                {"bots": {"orphan-extractor":
                          self._extractor_record("orphan-extractor")}})
            loaded = set(manager._bots)
        finally:
            manager.detach_bus()

        assert "orphan-extractor" in loaded
