"""The end-of-restore log must describe what ``save_state`` actually does.

``StateManager.save_state`` copies every on-disk record that is absent from
the saved fleet back into the file, so a bot that failed to restore is not
deleted by the next save. The completion log said the opposite. An operator
who believes the record is about to be deleted recreates the bot, and that
is the one action that destroys it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.bot_container import BotManager  # noqa: E402

BOT_LOGGER = "acervator.bot"


def _record(bot_id: str, **cfg) -> dict:
    base = {"exchange_id": "coinbase", "symbol": "BTC/USD", "mode": "scrumming"}
    base.update(cfg)
    return {"bot_id": bot_id, "config": base, "state_when_saved": "idle"}


def _completion_messages(records) -> list[str]:
    return [r.getMessage() for r in records if "restore completed" in r.getMessage()]


@pytest.fixture
def mgr():
    return BotManager()


def test_the_completion_log_fires_when_a_bot_fails_to_load(mgr, capture_log):
    """POSITIVE CONTROL: without this the assertions below pass vacuously."""
    state = {"bots": {"bot-broken": _record("bot-broken", exchange_id="")}}
    with capture_log(BOT_LOGGER) as records:
        mgr.restore_bots_from_state(state)
    msgs = _completion_messages(records)
    assert msgs, (
        "no completion log was captured, so every assertion about its "
        f"wording is vacuous. Captured: {[r.getMessage() for r in records]}"
    )
    assert "bot-broken" in msgs[0], msgs[0]


def test_the_completion_log_says_the_records_are_carried_forward(mgr, capture_log):
    state = {"bots": {"bot-broken": _record("bot-broken", exchange_id="")}}
    with capture_log(BOT_LOGGER) as records:
        mgr.restore_bots_from_state(state)
    msg = _completion_messages(records)[0]
    assert "carries them forward" in msg, (
        "the completion log must say save_state carries an unloaded "
        f"record forward. Got: {msg}"
    )
    assert "DELETED" not in msg, (
        "the completion log claims the record will be deleted; save_state "
        f"carries it forward instead. Got: {msg}"
    )


def test_no_completion_warning_when_every_bot_loads(mgr, capture_log):
    """NEGATIVE CONTROL: a clean restore must not raise the alarm at all."""
    with capture_log(BOT_LOGGER) as records:
        mgr.restore_bots_from_state({"bots": {"bot-ok": _record("bot-ok")}})
    msg = _completion_messages(records)[0]
    assert "NOT loaded" not in msg, msg
