"""The shipped Notifications and Alerts tab and the Qt-free surface, side by side.

A failure means the view model carries a different label, a different
table row, a different colour, a different widget tree, a different
recorded call or a different path than ``AlertsTab``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import alerts_tab as shipped
from src.gui.main_tabs import alerts_tab_surface as surface
from tests.fixtures.host_fonts import (
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    assert_same_skin,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

TAB_PATH = REPO_ROOT / "src/gui/alerts_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/alerts_tab_surface.py"
TIMER_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/live_bot_window.py"

PIXEL_SIZE = (900, 620)

# The design-system colours these cells use, typed out here rather than
# read from the surface, so a renamed or re-valued token cannot move both
# sides together.
SUCCESS_HEX = "#00ff88"
ERROR_HEX = "#ff3366"
WARNING_HEX = "#ffaa00"
PRIMARY_HEX = "#00ffcc"
INFO_HEX = "#00aaff"
LABEL_HEX = "#888"
PLACEHOLDER_HEX = "#555555"
TEXT_HIGH_HEX = "#e0e0f0"
CHART_HEX = "#0a0a12"
CARD_BORDER_HEX = "#2a2a3f"
PANEL_BORDER_HEX = "#1a1a3f"
PRIMARY_HOVER_HEX = "#00ddaa"

# The counts the shipped tab carries. Each is measured off the file and
# compared with what the surface declares.
TAB_CONNECT_SITES = 3
TAB_TIMER_SITES = 0
TAB_BUS_SITES = 0

CLOCK_STAMP = 1_700_000_000.0
LATER_STAMP = 1_700_000_060.0
BILLION_STAMP = 1_000_000_000.0

UNICODE_NAME = "Δ_flip→⚡"
MARKUP_NAME = "<b>bot</b>_error"
NEWLINE_NAME = "two\nlines"
LONG_NAME = "x" * 200
LONG_MESSAGE = "Z" * 200

SENT_BOT_KEY = "abc123"
SENT_CHAT_ID = "55512345"
SHORT_CHAT_ID = "555"
PHONE_NUMBER = "+15551234"

TABS_HELD: list = []


# The manager both sides read, recording every call it is asked to make


class FakePriority:
    """One priority, carrying the word the Priority cell prints."""

    def __init__(self, value):
        self.value = value


class FakeRecord:
    """One history record, with the six fields the history row reads."""

    def __init__(
        self,
        timestamp=CLOCK_STAMP,
        priority="medium",
        title="Bot started",
        message="RAVE bot is live",
        channels_sent=("IN_APP",),
        acknowledged=True,
    ):
        self.timestamp = timestamp
        self.priority = FakePriority(priority)
        self.title = title
        self.message = message
        self.channels_sent = list(channels_sent)
        self.acknowledged = acknowledged


class FakeManager:
    """A notification manager whose every read and write is steerable."""

    def __init__(
        self,
        config=None,
        history=(),
        unread=0,
        config_error=None,
        history_error=None,
        send_error=None,
        truthy=True,
    ):
        self._config = {} if config is None else config
        self._history = [FakeRecord(**spec) for spec in history]
        self._unread = unread
        self.config_error = config_error
        self.history_error = history_error
        self.send_error = send_error
        self.truthy = truthy
        self.telegram_calls: list = []
        self.sms_calls: list = []
        self.sent: list = []
        self.acknowledge_count = 0

    def __bool__(self):
        return self.truthy

    def get_config(self):
        if self.config_error is not None:
            raise self.config_error
        return self._config

    @property
    def unacknowledged_count(self):
        return self._unread

    @property
    def history(self):
        if self.history_error is not None:
            raise self.history_error
        return list(self._history)

    def configure_telegram(self, bot_token, chat_id):
        self.telegram_calls.append([bot_token, chat_id])

    def configure_sms(self, phone):
        self.sms_calls.append([phone])

    def acknowledge_all(self):
        self.acknowledge_count += 1
        for record in self._history:
            record.acknowledged = True
        self._unread = 0

    def _send_telegram(self, title, message, priority):
        self.sent.append([title, message, priority])
        if self.send_error is not None:
            raise self.send_error


def record(**over):
    """One history record's values, with the happy record as the base."""
    base = {
        "timestamp": CLOCK_STAMP,
        "priority": "medium",
        "title": "Bot started",
        "message": "RAVE bot is live",
        "channels_sent": ["IN_APP"],
        "acknowledged": True,
    }
    base.update(over)
    return base


CONFIG_NONE = {
    "telegram_configured": False,
    "sms_configured": False,
    "rules": {},
}
RULES_TWO = {
    "bot_started": {"channels": ["IN_APP"], "priority": "low"},
    "drawdown_critical": {
        "channels": ["IN_APP", "TELEGRAM", "SOUND"],
        "priority": "critical",
    },
}


def config(telegram=False, sms=False, rules=None):
    """One manager config, as ``get_config`` returns it."""
    return {
        "telegram_configured": telegram,
        "sms_configured": sms,
        "rules": {} if rules is None else rules,
    }


REFRESH_CASES: dict = {
    "happy": {
        "config": config(True, True, RULES_TWO),
        "history": [
            record(),
            record(priority="high", acknowledged=False, timestamp=LATER_STAMP),
        ],
        "unread": 1,
    },
    "empty": {"config": CONFIG_NONE, "history": [], "unread": 0},
    "zero_unread": {"config": CONFIG_NONE, "history": [record()], "unread": 0},
    "negative_unread": {"config": CONFIG_NONE, "history": [record()], "unread": -5},
    "thousand_million_unread": {
        "config": CONFIG_NONE,
        "history": [record()],
        "unread": 1_000_000_000,
    },
    "one_billionth_unread": {
        "config": CONFIG_NONE,
        "history": [record()],
        "unread": 1e-9,
    },
    "infinite_unread": {
        "config": CONFIG_NONE,
        "history": [record()],
        "unread": float("inf"),
    },
    "telegram_only": {"config": config(True, False, RULES_TWO), "unread": 3},
    "sms_only": {"config": config(False, True, RULES_TWO), "unread": 3},
    "no_rules_key": {"config": {"telegram_configured": True}, "unread": 0},
    "no_config_keys": {"config": {}, "unread": 0},
    "missing_priority": {
        "config": config(rules={"trade_executed": {"channels": ["IN_APP"]}}),
        "unread": 0,
    },
    "missing_channels": {
        "config": config(rules={"bot_error": {"priority": "high"}}),
        "unread": 0,
    },
    "unknown_priority": {
        "config": config(
            rules={"pnl_milestone": {"channels": ["TELEGRAM"], "priority": "urgent"}}
        ),
        "history": [record(priority="urgent")],
        "unread": 0,
    },
    "wrong_capitals": {
        "config": config(
            rules={
                "bot_stopped": {
                    "channels": ["in_app", "telegram", "sound"],
                    "priority": "Medium",
                }
            }
        ),
        "history": [record(priority="Medium")],
        "unread": 0,
    },
    "unicode_names": {
        "config": config(rules={UNICODE_NAME: {"channels": ["IN_APP"]}}),
        "history": [record(title=UNICODE_NAME, message=UNICODE_NAME)],
        "unread": 0,
    },
    "markup_names": {
        "config": config(rules={MARKUP_NAME: {"channels": ["SOUND"]}}),
        "history": [record(title=MARKUP_NAME, message=MARKUP_NAME)],
        "unread": 0,
    },
    "newline_names": {
        "config": config(rules={NEWLINE_NAME: {"channels": ["IN_APP"]}}),
        "history": [record(title=NEWLINE_NAME, message=NEWLINE_NAME)],
        "unread": 0,
    },
    "long_names": {
        "config": config(rules={LONG_NAME: {"channels": ["IN_APP"]}}),
        "history": [record(title=LONG_NAME, message=LONG_MESSAGE)],
        "unread": 0,
    },
    "all_priorities": {
        "config": config(rules=RULES_TWO),
        "history": [
            record(priority=name, title=f"note {name}")
            for name in ("low", "medium", "high", "critical")
        ],
        "unread": 0,
    },
    "unacknowledged": {
        "config": config(rules=RULES_TWO),
        "history": [
            record(priority=name, acknowledged=False, title=f"note {name}")
            for name in ("low", "medium", "high", "critical")
        ],
        "unread": 4,
    },
    "over_limit": {
        "config": CONFIG_NONE,
        "history": [
            record(title=f"note {index}", timestamp=CLOCK_STAMP + index)
            for index in range(120)
        ],
        "unread": 0,
    },
    "billion_stamp": {
        "config": CONFIG_NONE,
        "history": [record(timestamp=BILLION_STAMP)],
        "unread": 0,
    },
    "no_channels_sent": {
        "config": CONFIG_NONE,
        "history": [record(channels_sent=[])],
        "unread": 0,
    },
    "config_raises": {
        "config_error": RuntimeError("config unavailable"),
        "unread": 0,
    },
    "history_raises": {
        "config": CONFIG_NONE,
        "history_error": RuntimeError("history unavailable"),
        "unread": 0,
    },
    "unread_is_text": {"config": CONFIG_NONE, "unread": "many"},
    "text_timestamp": {
        "config": CONFIG_NONE,
        "history": [record(timestamp="noon")],
        "unread": 0,
    },
    "infinite_timestamp": {
        "config": CONFIG_NONE,
        "history": [record(timestamp=float("inf"))],
        "unread": 0,
    },
}

REFRESH_REFUSING = (
    "config_raises",
    "history_raises",
    "unread_is_text",
    "text_timestamp",
    "infinite_timestamp",
)

NUMBER_PRIORITY_RULES = {"bot_started": {"channels": ["IN_APP"], "priority": 5}}

TELEGRAM_CASES: dict = {
    "no_manager": (None, "", ""),
    "no_credentials": ({}, "", ""),
    "no_token": ({}, "", SENT_CHAT_ID),
    "no_chat": ({}, SENT_BOT_KEY, ""),
    "whitespace_only": ({}, "   ", "  "),
    "sent": ({}, SENT_BOT_KEY, SENT_CHAT_ID),
    "padded": ({}, "  abc123  ", "  55512345  "),
    "failed": (
        {"send_error": ValueError("telegram refused")},
        SENT_BOT_KEY,
        SHORT_CHAT_ID,
    ),
    "unicode": ({}, "Δ→⚡", "⚡"),
    "long": ({}, "x" * 200, "y" * 200),
    "markup": ({}, "<b>abc</b>", "<i>555</i>"),
    "newline": ({}, "two\nlines", "chat\nid"),
    "digits": ({}, "12345", "67890"),
}

TELEGRAM_NO_MANAGER = ("no_manager",)

SAVE_CASES: dict = {
    "no_manager": (None, "", "", ""),
    "both": ({}, SENT_BOT_KEY, SENT_CHAT_ID, ""),
    "token_only": ({}, SENT_BOT_KEY, "", ""),
    "chat_only": ({}, "", SENT_CHAT_ID, ""),
    "phone_only": ({}, "", "", PHONE_NUMBER),
    "all_three": ({}, SENT_BOT_KEY, SENT_CHAT_ID, PHONE_NUMBER),
    "whitespace": ({}, "   ", "  ", "   "),
    "padded": ({}, "  abc123  ", "  555  ", "  +15551234  "),
    "nothing": ({}, "", "", ""),
    "unicode_phone": ({}, "", "", "+⚡"),
}

ACK_CASES: dict = {
    "no_manager": None,
    "with_history": "unacknowledged",
    "empty_history": "empty",
    "over_limit": "over_limit",
}


def make_manager(name):
    """One fresh manager for a refresh case, so no case sees another's marks."""
    return FakeManager(**REFRESH_CASES[name])


# Reading the two sides into one shape


def canon_colour(value):
    """One colour in a single spelling, so ``#888`` and ``#888888`` agree.

    The widget stores a colour, never the text it was given, so the same
    canonical form is applied to both sides.
    """
    from PySide6.QtGui import QColor

    if not value:
        return ""
    return QColor(value).name().lower()


def canon_rows(rows):
    """One table's rows as text, canonical colour and alignment."""
    return [
        [
            {
                "text": found["text"],
                "color": canon_colour(found["color"]),
                "alignment": found["alignment"],
            }
            for found in row
        ]
        for row in rows
    ]


def read_table(table):
    """One real table's rows, read cell by cell off the widget."""
    from PySide6.QtGui import QColor
    from PySide6.QtCore import Qt

    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                cells.append({"text": None, "color": "", "alignment": ""})
                continue
            brush = item.foreground()
            colour = "" if brush.style() == Qt.NoBrush else QColor(brush.color()).name()
            cells.append(
                {
                    "text": item.text(),
                    "color": colour.lower(),
                    "alignment": (
                        "AlignCenter"
                        if int(item.textAlignment()) == 132
                        else str(int(item.textAlignment()))
                    ),
                }
            )
        rows.append(cells)
    return rows


def read_tab(tab):
    """The shipped tab's visible state, read off the live widgets."""
    return {
        "status_text": tab._lbl_status.text(),
        "status_style": tab._lbl_status.styleSheet(),
        "unread_text": tab._lbl_unread.text(),
        "unread_style": tab._lbl_unread.styleSheet(),
        "telegram_status_text": tab._tg_status.text(),
        "telegram_status_style": tab._tg_status.styleSheet(),
        "sms_status_text": tab._sms_status.text(),
        "sms_status_style": tab._sms_status.styleSheet(),
        "token": tab._tg_token.text(),
        "chat_id": tab._tg_chat.text(),
        "phone": tab._sms_phone.text(),
        "rules_rows": canon_rows(read_table(tab._rules_table)),
        "history_rows": canon_rows(read_table(tab._history_table)),
    }


def read_model(model):
    """The surface model's state in the same shape as the shipped tab's."""
    return {
        "status_text": model.status_text,
        "status_style": model.status_style,
        "unread_text": model.unread_text,
        "unread_style": model.unread_style,
        "telegram_status_text": model.telegram_status_text,
        "telegram_status_style": model.telegram_status_style,
        "sms_status_text": model.sms_status_text,
        "sms_status_style": model.sms_status_style,
        "token": model.token,
        "chat_id": model.chat_id,
        "phone": model.phone,
        "rules_rows": canon_rows(model.rules_rows),
        "history_rows": canon_rows(model.history_rows),
    }


def read_manager(manager):
    """What a manager was asked to do, in the order it was asked."""
    if manager is None:
        return {"telegram": [], "sms": [], "sent": [], "acknowledged": 0}
    return {
        "telegram": [list(call) for call in manager.telegram_calls],
        "sms": [list(call) for call in manager.sms_calls],
        "sent": [list(call) for call in manager.sent],
        "acknowledged": manager.acknowledge_count,
    }


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        run()
        return {"error": "", "message": ""}
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc)}


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def new_tab(manager):
    """One real AlertsTab, held so no read reaches a collected widget."""
    app()
    tab = shipped.AlertsTab(manager)
    TABS_HELD.append(tab)
    return tab


# Drivers


def old_refresh(name, by_argument=False):
    """Drive the shipped tab's refresh over one case."""
    manager = make_manager(name)
    tab = new_tab(None if by_argument else manager)
    outcome = guarded(lambda: tab.refresh(manager) if by_argument else tab.refresh())
    return {
        "outcome": outcome,
        "state": read_tab(tab),
        "manager": read_manager(manager),
    }


def new_refresh(name, by_argument=False):
    """Drive the surface's refresh over the same case."""
    manager = make_manager(name)
    model = surface.AlertsTabModel(None if by_argument else manager)
    outcome = guarded(
        lambda: model.refresh(manager) if by_argument else model.refresh()
    )
    return {
        "outcome": outcome,
        "state": read_model(model),
        "manager": read_manager(manager),
    }


def new_refresh_model(name):
    """The surface model for one refresh case, and how the drive ended."""
    manager = make_manager(name)
    model = surface.AlertsTabModel(manager)
    return model, guarded(model.refresh)


def old_no_manager_refresh():
    """Drive the shipped tab's refresh with no manager anywhere."""
    tab = new_tab(None)
    outcome = guarded(tab.refresh)
    return {"outcome": outcome, "state": read_tab(tab), "manager": read_manager(None)}


def new_no_manager_refresh():
    """Drive the surface's refresh with no manager anywhere."""
    model = surface.AlertsTabModel(None)
    outcome = guarded(model.refresh)
    return {
        "outcome": outcome,
        "state": read_model(model),
        "manager": read_manager(None),
    }


def telegram_manager(name):
    """The manager one Telegram-test case is driven against, or None."""
    spec = TELEGRAM_CASES[name][0]
    if spec is None:
        return None
    return FakeManager(config=CONFIG_NONE, **spec)


def old_telegram(name):
    """Drive the shipped tab's Telegram test over one case."""
    _, token, chat_id = TELEGRAM_CASES[name]
    manager = telegram_manager(name)
    tab = new_tab(manager)
    tab._tg_token.setText(token)
    tab._tg_chat.setText(chat_id)
    assert tab._tg_token.text() == token, name
    assert tab._tg_chat.text() == chat_id, name
    outcome = guarded(tab._test_telegram)
    return {
        "outcome": outcome,
        "state": read_tab(tab),
        "manager": read_manager(manager),
    }


def new_telegram(name):
    """Drive the surface's Telegram test over the same case."""
    _, token, chat_id = TELEGRAM_CASES[name]
    manager = telegram_manager(name)
    model = surface.AlertsTabModel(manager)
    model.token = token
    model.chat_id = chat_id
    outcome = guarded(model.test_telegram)
    return {
        "outcome": outcome,
        "state": read_model(model),
        "manager": read_manager(manager),
    }


def new_telegram_model(name):
    """The surface model for one Telegram-test case."""
    _, token, chat_id = TELEGRAM_CASES[name]
    model = surface.AlertsTabModel(telegram_manager(name))
    model.token = token
    model.chat_id = chat_id
    model.test_telegram()
    return model


def save_manager(name):
    """The manager one Save case is driven against, or None."""
    spec = SAVE_CASES[name][0]
    if spec is None:
        return None
    return FakeManager(config=CONFIG_NONE, **spec)


def old_save(name):
    """Drive the shipped tab's Save over one case."""
    _, token, chat_id, phone = SAVE_CASES[name]
    manager = save_manager(name)
    tab = new_tab(manager)
    tab._tg_token.setText(token)
    tab._tg_chat.setText(chat_id)
    tab._sms_phone.setText(phone)
    outcome = guarded(tab._save_config)
    return {
        "outcome": outcome,
        "state": read_tab(tab),
        "manager": read_manager(manager),
    }


def new_save(name):
    """Drive the surface's Save over the same case."""
    _, token, chat_id, phone = SAVE_CASES[name]
    manager = save_manager(name)
    model = surface.AlertsTabModel(manager)
    model.token = token
    model.chat_id = chat_id
    model.phone = phone
    outcome = guarded(model.save_config)
    return {
        "outcome": outcome,
        "state": read_model(model),
        "manager": read_manager(manager),
    }


def new_save_model(name):
    """The surface model for one Save case."""
    _, token, chat_id, phone = SAVE_CASES[name]
    model = surface.AlertsTabModel(save_manager(name))
    model.token = token
    model.chat_id = chat_id
    model.phone = phone
    model.save_config()
    return model


def ack_manager(name):
    """The manager one Acknowledge case is driven against, or None."""
    case = ACK_CASES[name]
    return None if case is None else make_manager(case)


def old_ack(name):
    """Drive the shipped tab's Acknowledge All over one case."""
    manager = ack_manager(name)
    tab = new_tab(manager)
    outcome = guarded(tab._acknowledge_all)
    return {
        "outcome": outcome,
        "state": read_tab(tab),
        "manager": read_manager(manager),
    }


def new_ack(name):
    """Drive the surface's Acknowledge All over the same case."""
    manager = ack_manager(name)
    model = surface.AlertsTabModel(manager)
    outcome = guarded(model.acknowledge_all)
    return {
        "outcome": outcome,
        "state": read_model(model),
        "manager": read_manager(manager),
    }


def new_ack_model(name):
    """The surface model for one Acknowledge case."""
    model = surface.AlertsTabModel(ack_manager(name))
    model.acknowledge_all()
    return model


# Side by side, value for value and by hash


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_is_the_shipped_tabs_refresh(name):
    """The surface painted a different tab than the shipped refresh."""
    old = old_refresh(name)
    new = new_refresh(name)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_by_argument_is_the_shipped_tabs_refresh(name):
    """The manager passed to refresh reached one side and not the other."""
    old = old_refresh(name, by_argument=True)
    new = new_refresh(name, by_argument=True)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_snapshot_holds_the_whole_tab(name):
    """The comparison passed by measuring nothing."""
    old = old_refresh(name)
    refused = name in REFRESH_REFUSING
    assert (old["outcome"]["error"] != "") is refused, name
    state = old["state"]
    assert isinstance(state["status_text"], str) and state["status_text"] != "", name
    assert state["unread_text"].startswith("Unread: "), name
    assert state["sms_status_text"] == "Not configured", name
    for row in state["rules_rows"] + state["history_rows"]:
        assert len(row) == 5, name
        for found in row:
            assert found["alignment"] in ("AlignCenter", ""), name
            if not refused:
                assert found["alignment"] == "AlignCenter", name
    if not refused:
        assert old["outcome"]["message"] == "", name


def test_the_no_manager_refresh_is_the_shipped_tabs():
    """A tab with no manager painted differently on the two sides."""
    old = old_no_manager_refresh()
    new = new_no_manager_refresh()
    assert new == old
    assert digest(new) == digest(old)
    assert old["state"]["rules_rows"] == []
    assert old["state"]["history_rows"] == []
    assert old["state"]["status_text"] == "Notifications: Active"
    assert old["state"]["unread_text"] == "Unread: 0"


@pytest.mark.parametrize("name", sorted(TELEGRAM_CASES))
def test_the_telegram_test_is_the_shipped_tabs(name):
    """The surface sent or refused a Telegram test the shipped tab did not."""
    old = old_telegram(name)
    new = new_telegram(name)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(TELEGRAM_CASES))
def test_the_telegram_snapshot_holds_the_whole_line(name):
    """The comparison passed by measuring nothing."""
    old = old_telegram(name)
    assert old["outcome"]["error"] == "", name
    state = old["state"]
    if name in TELEGRAM_NO_MANAGER:
        assert state["telegram_status_text"] == "", name
        assert old["manager"]["sent"] == [], name
        return
    assert isinstance(state["telegram_status_text"], str), name
    assert state["telegram_status_style"] in (
        f"color: {ERROR_HEX};",
        f"color: {SUCCESS_HEX};",
    ), name


@pytest.mark.parametrize("name", sorted(SAVE_CASES))
def test_the_save_is_the_shipped_tabs(name):
    """The surface saved a different configuration than the shipped tab."""
    old = old_save(name)
    new = new_save(name)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(ACK_CASES))
def test_the_acknowledge_is_the_shipped_tabs(name):
    """The surface acknowledged differently than the shipped tab."""
    old = old_ack(name)
    new = new_ack(name)
    assert new == old, name
    assert digest(new) == digest(old), name


def test_the_sample_hashes_are_reported():
    """Two sides agreed by both carrying nothing at all."""
    samples = {}
    for name in ("happy", "empty", "unacknowledged", "over_limit", "unicode_names"):
        old = old_refresh(name)
        new = new_refresh(name)
        samples[name] = (digest(old), digest(new))
        assert samples[name][0] == samples[name][1], name
    assert len({pair[0] for pair in samples.values()}) == 5
    changed = old_refresh("happy")
    changed["state"]["status_text"] = "Notifications: Off"
    assert digest(changed) != samples["happy"][0]
    assert digest(old_refresh("happy")) == samples["happy"][0]


def test_two_genuinely_different_cases_hash_apart():
    """The hash reports one value for every input, so it proves nothing."""
    happy = digest(old_refresh("happy"))
    empty = digest(old_refresh("empty"))
    assert happy != empty
    assert digest(new_refresh("happy")) == happy
    assert digest(new_refresh("empty")) == empty


# The paths every case reaches


def test_every_refresh_case_reaches_the_path_it_names():
    """A case stopped reaching the path it stands for."""
    reached = {}
    refused = set()
    for name in REFRESH_CASES:
        model, outcome = new_refresh_model(name)
        reached[name] = model.refresh_path
        if outcome["error"]:
            refused.add(name)
    assert refused == set(REFRESH_REFUSING)
    assert reached["happy"] == surface.REFRESH_PATH_PAINTED
    for name in REFRESH_REFUSING:
        assert reached[name] == surface.NO_PATH, name
    assert set(reached.values()) == {surface.NO_PATH, surface.REFRESH_PATH_PAINTED}
    model = surface.AlertsTabModel(None)
    model.refresh()
    assert model.refresh_path == surface.REFRESH_PATH_NO_MANAGER
    assert set(surface.REFRESH_PATHS) == {
        surface.REFRESH_PATH_NO_MANAGER,
        surface.REFRESH_PATH_PAINTED,
    }


def test_the_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    outcomes = {name: old_refresh(name)["outcome"]["error"] for name in REFRESH_CASES}
    refused = {name for name, error in outcomes.items() if error}
    answered = set(outcomes) - refused
    assert refused == set(REFRESH_REFUSING)
    assert len(answered) >= 20
    assert outcomes["config_raises"] == "RuntimeError"
    assert outcomes["history_raises"] == "RuntimeError"
    assert outcomes["unread_is_text"] == "TypeError"
    assert outcomes["text_timestamp"] == "TypeError"
    assert outcomes["infinite_timestamp"] == "OverflowError"
    for name in REFRESH_REFUSING:
        assert new_refresh(name)["outcome"] == old_refresh(name)["outcome"], name


def test_every_telegram_case_reaches_the_path_it_names():
    """A Telegram case stopped reaching the path it stands for."""
    reached = {name: new_telegram_model(name).test_path for name in TELEGRAM_CASES}
    assert reached["no_manager"] == surface.TEST_PATH_NO_MANAGER
    assert reached["no_credentials"] == surface.TEST_PATH_MISSING
    assert reached["no_token"] == surface.TEST_PATH_MISSING
    assert reached["no_chat"] == surface.TEST_PATH_MISSING
    assert reached["whitespace_only"] == surface.TEST_PATH_MISSING
    assert reached["sent"] == surface.TEST_PATH_SENT
    assert reached["padded"] == surface.TEST_PATH_SENT
    assert reached["failed"] == surface.TEST_PATH_FAILED
    assert set(reached.values()) == set(surface.TEST_PATHS)


def test_every_save_and_acknowledge_case_reaches_the_path_it_names():
    """A Save or Acknowledge case stopped reaching its path."""
    saved = {name: new_save_model(name).save_path for name in SAVE_CASES}
    assert saved["no_manager"] == surface.SAVE_PATH_NO_MANAGER
    assert saved["both"] == surface.SAVE_PATH_SAVED
    assert set(saved.values()) == set(surface.SAVE_PATHS)
    acked = {name: new_ack_model(name).ack_path for name in ACK_CASES}
    assert acked["no_manager"] == surface.ACK_PATH_NO_MANAGER
    assert acked["with_history"] == surface.ACK_PATH_ACKNOWLEDGED
    assert set(acked.values()) == set(surface.ACK_PATHS)


# The values behind the two tables


def test_the_unread_line_is_the_shipped_tabs_own():
    """The unread line changed its wording or its colour rule."""
    for name, expected, style in (
        ("happy", "Unread: 1", f"color: {WARNING_HEX}; font-size: 12px;"),
        ("zero_unread", "Unread: 0", f"color: {LABEL_HEX}; font-size: 12px;"),
        ("negative_unread", "Unread: -5", f"color: {LABEL_HEX}; font-size: 12px;"),
        (
            "thousand_million_unread",
            "Unread: 1000000000",
            f"color: {WARNING_HEX}; font-size: 12px;",
        ),
        (
            "one_billionth_unread",
            "Unread: 1e-09",
            f"color: {WARNING_HEX}; font-size: 12px;",
        ),
        ("infinite_unread", "Unread: inf", f"color: {WARNING_HEX}; font-size: 12px;"),
    ):
        old = old_refresh(name)["state"]
        new = new_refresh(name)["state"]
        assert old["unread_text"] == expected, name
        assert new["unread_text"] == expected, name
        assert old["unread_style"] == style, name
        assert new["unread_style"] == style, name
    assert surface.UNREAD_FORMAT == "Unread: {unread}"
    assert surface.UNREAD_FORMAT.format(unread=7) == "Unread: 7"


def test_the_status_line_is_the_shipped_tabs_own():
    """The status line stopped naming a connected channel."""
    for name, expected in (
        ("happy", "Notifications: Active | TG: Connected | SMS: Connected"),
        ("telegram_only", "Notifications: Active | TG: Connected"),
        ("sms_only", "Notifications: Active | SMS: Connected"),
        ("empty", "Notifications: Active"),
        ("no_config_keys", "Notifications: Active"),
    ):
        assert old_refresh(name)["state"]["status_text"] == expected, name
        assert new_refresh(name)["state"]["status_text"] == expected, name


def test_the_routing_row_is_the_shipped_tabs_own():
    """A routing cell changed its word, its colour or its column."""
    old = old_refresh("happy")["state"]["rules_rows"]
    new = new_refresh("happy")["state"]["rules_rows"]
    assert new == old
    assert len(old) == 2
    assert [found["text"] for found in old[0]] == [
        "Bot Started",
        "low",
        "Yes",
        "No",
        "No",
    ]
    assert [found["text"] for found in old[1]] == [
        "Drawdown Critical",
        "critical",
        "Yes",
        "Yes",
        "Yes",
    ]
    assert [found["color"] for found in old[0]] == [
        "",
        "",
        canon_colour(SUCCESS_HEX),
        canon_colour(PLACEHOLDER_HEX),
        canon_colour(PLACEHOLDER_HEX),
    ]
    assert [found["color"] for found in old[1]][2:] == [canon_colour(SUCCESS_HEX)] * 3


def test_a_channel_named_in_the_wrong_capitals_is_not_routed():
    """Channel matching stopped being exact."""
    old = old_refresh("wrong_capitals")["state"]["rules_rows"]
    new = new_refresh("wrong_capitals")["state"]["rules_rows"]
    assert new == old
    assert [found["text"] for found in old[0]][2:] == ["No", "No", "No"]
    assert old[0][1]["text"] == "Medium"
    assert old[0][0]["text"] == "Bot Stopped"


def test_a_rule_without_a_priority_or_channels_uses_the_shipped_defaults():
    """A missing rule key stopped falling back where the shipped tab does."""
    missing_priority = old_refresh("missing_priority")["state"]["rules_rows"]
    assert missing_priority[0][1]["text"] == "medium"
    assert new_refresh("missing_priority")["state"]["rules_rows"] == missing_priority
    missing_channels = old_refresh("missing_channels")["state"]["rules_rows"]
    assert [found["text"] for found in missing_channels[0]][2:] == ["No", "No", "No"]
    assert new_refresh("missing_channels")["state"]["rules_rows"] == missing_channels
    assert surface.DEFAULT_PRIORITY == "medium"


def test_the_history_row_is_the_shipped_tabs_own():
    """A history cell changed its text, its colour or its order."""
    old = old_refresh("happy")["state"]["history_rows"]
    new = new_refresh("happy")["state"]["history_rows"]
    assert new == old
    assert len(old) == 2
    assert old[0][2]["text"] == "Bot started"
    assert old[0][1]["text"] == "high"
    assert old[0][1]["color"] == canon_colour(TEXT_HIGH_HEX)
    assert old[1][1]["color"] == canon_colour(INFO_HEX)
    assert old[0][4]["text"] == "IN_APP"
    for row in old:
        assert len(row[0]["text"]) == 8
        assert row[0]["text"][2] == ":" and row[0]["text"][5] == ":"


def test_the_newest_notification_is_painted_first():
    """The history stopped showing the newest row at the top."""
    old = old_refresh("over_limit")["state"]["history_rows"]
    new = new_refresh("over_limit")["state"]["history_rows"]
    assert new == old
    assert len(old) == 100
    assert old[0][2]["text"] == "note 119"
    assert old[-1][2]["text"] == "note 20"
    assert [row[2]["text"] for row in old][:3] == ["note 119", "note 118", "note 117"]
    assert "note 19" not in {row[2]["text"] for row in old}
    assert surface.HISTORY_LIMIT == 100


def test_a_long_message_is_cut_where_the_shipped_tab_cuts_it():
    """The message column stopped truncating at the shipped width."""
    old = old_refresh("long_names")["state"]["history_rows"]
    new = new_refresh("long_names")["state"]["history_rows"]
    assert new == old
    assert old[0][3]["text"] == "Z" * 60
    assert len(old[0][3]["text"]) == 60
    assert old[0][2]["text"] == "x" * 200
    assert surface.MESSAGE_MAX_CHARS == 60


def test_an_unacknowledged_row_is_drawn_over_its_priority_colour():
    """The unacknowledged colour stopped overwriting the priority colour."""
    old = old_refresh("unacknowledged")["state"]["history_rows"]
    new = new_refresh("unacknowledged")["state"]["history_rows"]
    assert new == old
    for row in old:
        for found in row:
            assert found["color"] == canon_colour(TEXT_HIGH_HEX)
    read = old_refresh("all_priorities")["state"]["history_rows"]
    assert new_refresh("all_priorities")["state"]["history_rows"] == read
    assert [row[1]["color"] for row in read] == [
        canon_colour(ERROR_HEX),
        canon_colour(WARNING_HEX),
        canon_colour(INFO_HEX),
        canon_colour(LABEL_HEX),
    ]
    for row in read:
        assert row[0]["color"] == ""


def test_an_unknown_priority_falls_back_to_the_shipped_colour():
    """The priority colour table stopped falling back."""
    old = old_refresh("unknown_priority")["state"]["history_rows"]
    new = new_refresh("unknown_priority")["state"]["history_rows"]
    assert new == old
    assert old[0][1]["text"] == "urgent"
    assert old[0][1]["color"] == canon_colour(LABEL_HEX)
    assert surface.priority_color("urgent") == surface.PRIORITY_FALLBACK_COLOR
    assert surface.priority_color("high") != surface.PRIORITY_FALLBACK_COLOR


def test_the_colours_are_told_apart_by_the_canonical_form():
    """The colour comparison collapsed two different colours into one."""
    tokens = (
        SUCCESS_HEX,
        ERROR_HEX,
        WARNING_HEX,
        INFO_HEX,
        LABEL_HEX,
        PLACEHOLDER_HEX,
        TEXT_HIGH_HEX,
    )
    assert len({canon_colour(hexed) for hexed in tokens}) == len(tokens)
    assert canon_colour(LABEL_HEX) == "#888888"
    assert canon_colour("") == ""
    assert canon_colour(SUCCESS_HEX) != canon_colour(ERROR_HEX)


def test_the_telegram_line_is_the_shipped_tabs_own():
    """The Telegram test line changed its wording or its colour."""
    missing = old_telegram("no_credentials")["state"]
    assert missing["telegram_status_text"] == "Enter bot token and chat ID first"
    assert missing["telegram_status_style"] == f"color: {ERROR_HEX};"
    sent = old_telegram("sent")
    assert sent["state"]["telegram_status_text"] == "Test sent successfully!"
    assert sent["state"]["telegram_status_style"] == f"color: {SUCCESS_HEX};"
    assert sent["manager"]["sent"] == [
        [
            "Acervator",
            "Test notification — Telegram is configured correctly!",
            None,
        ]
    ]
    failed = old_telegram("failed")
    assert failed["state"]["telegram_status_text"] == "Failed: telegram refused"
    assert failed["state"]["telegram_status_style"] == f"color: {ERROR_HEX};"
    for name in ("no_credentials", "sent", "failed"):
        assert new_telegram(name)["state"] == old_telegram(name)["state"], name


def test_the_test_button_trims_what_it_was_given():
    """The Telegram test stopped trimming the two fields."""
    padded = old_telegram("padded")
    assert padded["manager"]["telegram"] == [[SENT_BOT_KEY, SENT_CHAT_ID]]
    assert new_telegram("padded")["manager"] == padded["manager"]
    assert old_telegram("whitespace_only")["manager"]["telegram"] == []


def test_the_save_writes_only_what_the_shipped_tab_writes():
    """Save wrote a channel setting the shipped tab leaves alone."""
    for name, telegram, sms in (
        ("both", [[SENT_BOT_KEY, SENT_CHAT_ID]], []),
        ("token_only", [], []),
        ("chat_only", [], []),
        ("phone_only", [], [[PHONE_NUMBER]]),
        ("all_three", [[SENT_BOT_KEY, SENT_CHAT_ID]], [[PHONE_NUMBER]]),
        ("whitespace", [], []),
        ("padded", [[SENT_BOT_KEY, SHORT_CHAT_ID]], [[PHONE_NUMBER]]),
        ("nothing", [], []),
    ):
        old = old_save(name)
        assert old["manager"]["telegram"] == telegram, name
        assert old["manager"]["sms"] == sms, name
        assert new_save(name)["manager"] == old["manager"], name
    assert old_save("both")["state"]["status_text"] == "Configuration saved!"
    assert old_save("no_manager")["state"]["status_text"] == "Notifications: Active"


def test_the_acknowledge_clears_the_unread_line_and_repaints():
    """Acknowledge stopped clearing the unread line or stopped repainting."""
    old = old_ack("with_history")
    new = new_ack("with_history")
    assert new == old
    assert old["manager"]["acknowledged"] == 1
    assert old["state"]["unread_text"] == "Unread: 0"
    assert len(old["state"]["history_rows"]) == 4
    for row in old["state"]["history_rows"]:
        assert row[0]["color"] == ""
    assert old_ack("no_manager")["manager"]["acknowledged"] == 0
    assert old_ack("no_manager")["state"]["unread_text"] == "Unread: 0"


def test_the_number_where_text_belongs_is_kept_by_one_side_only():
    """A non-text cell value stopped being reported the way each side reports it.

    A Qt table item built from a number takes the item-type argument, so
    the cell prints nothing and carries the number as its type. The
    surface carries the number itself. Both answers are read here rather
    than assumed equal.
    """
    manager = FakeManager(config=config(rules=NUMBER_PRIORITY_RULES), unread=0)
    tab = new_tab(manager)
    tab.refresh()
    item = tab._rules_table.item(0, 1)
    assert item.text() == ""
    assert item.type() == 5
    model = surface.AlertsTabModel(
        FakeManager(config=config(rules=NUMBER_PRIORITY_RULES), unread=0)
    )
    model.refresh()
    assert model.rules_rows[0][1]["text"] == 5
    assert model.rules_rows[0][0]["text"] == "Bot Started"
    assert tab._rules_table.item(0, 0).text() == "Bot Started"


def test_the_format_strings_carry_their_own_placeholders():
    """A format string lost the value it is meant to carry."""
    assert surface.UNREAD_FORMAT.count("{unread}") == 1
    assert surface.TELEGRAM_FAILED_FORMAT.count("{error}") == 1
    assert surface.TELEGRAM_FAILED_FORMAT.format(error="x") == "Failed: x"
    assert surface.TIME_FORMAT == "%H:%M:%S"
    assert surface.STATUS_SEPARATOR == " | "
    assert surface.CHANNEL_JOIN == ", "
    assert surface.UNREAD_FORMAT.format(unread=0) == surface.UNREAD_START_TEXT


def test_the_time_column_is_read_the_same_way_on_both_sides():
    """The time column stopped reading the clock the shipped tab reads."""
    import time

    stamped = time.strftime("%H:%M:%S", time.localtime(CLOCK_STAMP))
    assert surface.clock_text(CLOCK_STAMP) == stamped
    old = old_refresh("billion_stamp")["state"]["history_rows"]
    new = new_refresh("billion_stamp")["state"]["history_rows"]
    assert new == old
    assert old[0][0]["text"] == time.strftime("%H:%M:%S", time.localtime(BILLION_STAMP))
    assert surface.clock_text(CLOCK_STAMP) != surface.clock_text(BILLION_STAMP)


# The tab the two sides paint


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def fill_table(table, columns, rows, payload, no_edits):
    """One table built from the payload alone, filled from one case's rows."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setAlternatingRowColors(payload["alternating_row_colors"])
    if no_edits:
        table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(payload["vertical_header_visible"])
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, found in enumerate(row):
            item = QTableWidgetItem(found["text"])
            item.setTextAlignment(Qt.AlignmentFlag(payload["alignment_value"]))
            if found["color"]:
                item.setForeground(QColor(found["color"]))
            table.setItem(row_index, column, item)


def build_tab(payload, state):
    """One tab built only from the surface's view model and one case's state."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSplitter,
        QTableWidget,
        QVBoxLayout,
        QWidget,
    )

    app()
    nodes = {node["name"]: node for node in payload["widgets"]}
    tab = QWidget()
    TABS_HELD.append(tab)
    tab.setAccessibleName(payload["accessible_name"])
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*payload["content_margins"])
    layout.setSpacing(payload["content_spacing"])

    split = QSplitter(Qt.Horizontal)
    split.setHandleWidth(payload["splitter_handle_width"])
    split.setChildrenCollapsible(payload["splitter_children_collapsible"])

    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(*payload["pane_margins"])

    status = QLabel(state["status_text"])
    status.setStyleSheet(state["status_style"])
    left_layout.addWidget(status)

    unread = QLabel(state["unread_text"])
    unread.setStyleSheet(state["unread_style"])
    left_layout.addWidget(unread)

    telegram_group = QGroupBox(nodes["telegram_group"]["title"])
    telegram_group.setStyleSheet(nodes["telegram_group"]["style_sheet"])
    telegram_form = QFormLayout(telegram_group)

    token = QLineEdit()
    token.setPlaceholderText(nodes["token_input"]["placeholder"])
    token.setEchoMode(
        QLineEdit.EchoMode(payload["echo_values"][nodes["token_input"]["echo_mode"]])
    )
    token.setText(state["token"])
    telegram_form.addRow(nodes["token_input"]["row_label"], token)

    chat = QLineEdit()
    chat.setPlaceholderText(nodes["chat_input"]["placeholder"])
    chat.setEchoMode(
        QLineEdit.EchoMode(payload["echo_values"][nodes["chat_input"]["echo_mode"]])
    )
    chat.setText(state["chat_id"])
    telegram_form.addRow(nodes["chat_input"]["row_label"], chat)

    test_button = QPushButton(nodes["test_button"]["text"])
    test_button.setStyleSheet(nodes["test_button"]["style_sheet"])
    test_button.setEnabled(nodes["test_button"]["enabled"])
    telegram_form.addRow(test_button)

    telegram_status = QLabel(state["telegram_status_text"])
    telegram_status.setStyleSheet(state["telegram_status_style"])
    telegram_form.addRow(telegram_status)
    left_layout.addWidget(telegram_group)

    sms_group = QGroupBox(nodes["sms_group"]["title"])
    sms_group.setStyleSheet(nodes["sms_group"]["style_sheet"])
    sms_form = QFormLayout(sms_group)

    phone = QLineEdit()
    phone.setPlaceholderText(nodes["phone_input"]["placeholder"])
    phone.setText(state["phone"])
    sms_form.addRow(nodes["phone_input"]["row_label"], phone)

    sms_status = QLabel(state["sms_status_text"])
    sms_status.setStyleSheet(state["sms_status_style"])
    sms_form.addRow(sms_status)
    left_layout.addWidget(sms_group)

    save_button = QPushButton(nodes["save_button"]["text"])
    save_button.setStyleSheet(nodes["save_button"]["style_sheet"])
    save_button.setEnabled(nodes["save_button"]["enabled"])
    left_layout.addWidget(save_button)
    left_layout.addStretch()
    split.addWidget(left)

    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(*payload["pane_margins"])

    rules_group = QGroupBox(nodes["rules_group"]["title"])
    rules_group.setStyleSheet(nodes["rules_group"]["style_sheet"])
    rules_layout = QVBoxLayout(rules_group)
    rules_table = QTableWidget()
    fill_table(
        rules_table,
        payload["rules_columns"],
        state["rules_rows"],
        payload,
        no_edits=False,
    )
    rules_layout.addWidget(rules_table)
    right_layout.addWidget(rules_group, stretch=nodes["rules_group"]["stretch"])

    history_group = QGroupBox(nodes["history_group"]["title"])
    history_group.setStyleSheet(nodes["history_group"]["style_sheet"])
    history_layout = QVBoxLayout(history_group)
    ack_row = QHBoxLayout()
    ack_row.addStretch()
    ack_button = QPushButton(nodes["ack_button"]["text"])
    ack_button.setStyleSheet(nodes["ack_button"]["style_sheet"])
    ack_button.setEnabled(nodes["ack_button"]["enabled"])
    ack_row.addWidget(ack_button)
    history_layout.addLayout(ack_row)
    history_table = QTableWidget()
    fill_table(
        history_table,
        payload["history_columns"],
        state["history_rows"],
        payload,
        no_edits=True,
    )
    history_layout.addWidget(history_table)
    right_layout.addWidget(history_group, stretch=nodes["history_group"]["stretch"])

    split.addWidget(right)
    split.setSizes(payload["splitter_sizes"])
    layout.addWidget(split)
    return tab


PICTURE_CASES = (
    "happy",
    "empty",
    "all_priorities",
    "unacknowledged",
    "unicode_names",
    "markup_names",
    "long_names",
    "wrong_capitals",
    "over_limit",
    "telegram_only",
)


def old_picture_tab(name):
    """The shipped tab, driven over one case and ready to render."""
    manager = make_manager(name)
    tab = new_tab(manager)
    tab.refresh()
    return tab


def new_picture_tab(name):
    """A tab built only from the surface's payload for the same case."""
    manager = make_manager(name)
    model = surface.AlertsTabModel(manager)
    payload = surface.build_view_model(model, action="refresh")
    return build_tab(payload, read_model(model))


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a tab the shipped tab does not."""
    app()
    old_side = render_offscreen(old_picture_tab(name), PIXEL_SIZE)
    new_side = render_offscreen(new_picture_tab(name), PIXEL_SIZE)
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the second side paints.

    One render comes from the shipped tab and one from the surface, and
    the two carry genuinely different data. A comparison that could not
    report would call them the same.
    """
    app()
    old_side = render_offscreen(old_picture_tab("happy"), PIXEL_SIZE)
    new_side = render_offscreen(new_picture_tab("empty"), PIXEL_SIZE)
    assert_pictures_differ(old_side=old_side, new_side=new_side, note="happy vs empty")
    assert colour_count(old_side) > 1
    assert colour_count(new_side) > 1
    assert_pictures_differ(
        old_side=render_offscreen(old_picture_tab("empty"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("all_priorities"), PIXEL_SIZE),
        note="empty vs all_priorities",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("happy"), PIXEL_SIZE),
        note="one case, both sides",
    )


def test_the_typed_fields_reach_the_picture_on_both_sides():
    """What the operator typed is painted on one side and not the other."""
    app()
    manager = FakeManager(config=CONFIG_NONE, unread=0)
    tab = new_tab(manager)
    tab._tg_token.setText(SENT_BOT_KEY)
    tab._tg_chat.setText(SENT_CHAT_ID)
    tab._sms_phone.setText(PHONE_NUMBER)
    tab.refresh()
    model = surface.AlertsTabModel(FakeManager(config=CONFIG_NONE, unread=0))
    model.token = SENT_BOT_KEY
    model.chat_id = SENT_CHAT_ID
    model.phone = PHONE_NUMBER
    payload = surface.build_view_model(model, action="refresh")
    assert_pictures_match(
        old_side=render_offscreen(tab, PIXEL_SIZE),
        new_side=render_offscreen(build_tab(payload, read_model(model)), PIXEL_SIZE),
        note="typed fields",
    )
    assert read_model(model)["phone"] == PHONE_NUMBER
    assert tab._sms_phone.text() == PHONE_NUMBER


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    metrics = QFontMetrics(QApplication.font())
    narrow = metrics.horizontalAdvance("iiiiiiii")
    wide = metrics.horizontalAdvance("WWWWWWWW")
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font
    database, so the box-font premise the picture checks rest on is
    stale."""
    app()
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    metrics = QFontMetrics(QApplication.font())
    assert metrics.horizontalAdvance("ii") == metrics.horizontalAdvance("WW")


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding a font database measured every glyph the same
    width, so no picture on it can report a changed string."""
    app()
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    metrics = QFontMetrics(QApplication.font())
    assert metrics.horizontalAdvance("WW") > metrics.horizontalAdvance("ii")


# What a picture cannot see


def test_the_splitter_sizes_are_compared_as_the_request():
    """The splitter request was read back instead of asserted.

    A window resizes the two panes to fit, so the sizes it reports are
    never the sizes it was given. The request is what the surface holds,
    and two different requests are proved to settle differently.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter, QWidget

    app()
    tab = old_picture_tab("happy")
    split = tab.findChild(QSplitter)
    assert split is not None
    assert surface.SPLITTER_SIZES == (350, 550)
    assert list(surface.SPLITTER_SIZES) == [350, 550]
    assert split.handleWidth() == surface.SPLITTER_HANDLE_WIDTH == 5
    assert split.childrenCollapsible() is surface.SPLITTER_CHILDREN_COLLAPSIBLE
    assert int(split.orientation().value) == surface.SPLITTER_ORIENTATION_VALUE
    assert surface.SPLITTER_ORIENTATION == "Horizontal"
    settled = []
    for request in ([350, 550], [700, 200]):
        probe = QSplitter(Qt.Horizontal)
        left, right = QWidget(), QWidget()
        probe.addWidget(left)
        probe.addWidget(right)
        probe.resize(900, 400)
        probe.setSizes(request)
        render_offscreen(probe, (900, 400))
        settled.append(list(probe.sizes()))
    assert settled[0] != settled[1]
    assert settled[0] != [350, 550]


def test_the_placeholders_and_the_hidden_field_are_compared_as_values():
    """A placeholder or the hidden bot-token field reached no pixel."""
    app()
    tab = old_picture_tab("empty")
    assert tab._tg_token.placeholderText() == surface.TELEGRAM_BOT_PLACEHOLDER
    assert tab._tg_chat.placeholderText() == surface.CHAT_PLACEHOLDER
    assert tab._sms_phone.placeholderText() == surface.PHONE_PLACEHOLDER
    assert surface.TELEGRAM_BOT_PLACEHOLDER == "Bot token from @BotFather"
    assert surface.CHAT_PLACEHOLDER == "Chat ID (use @userinfobot)"
    assert surface.PHONE_PLACEHOLDER == "+1234567890"
    assert int(tab._tg_token.echoMode().value) == surface.ECHO_VALUES["Password"] == 2
    assert int(tab._tg_chat.echoMode().value) == surface.ECHO_VALUES["Normal"] == 0
    assert int(tab._sms_phone.echoMode().value) == 0


def test_the_accessible_name_is_compared_as_a_string():
    """The name a screen reader announces reached no pixel."""
    app()
    tab = old_picture_tab("empty")
    assert tab.accessibleName() == surface.ACCESSIBLE_NAME
    assert surface.ACCESSIBLE_NAME == "Notifications and Alerts tab"
    assert surface.AlertsTabModel().accessible_name == surface.ACCESSIBLE_NAME


def test_the_edit_rule_on_the_two_tables_is_compared_as_a_value():
    """A table became editable or stopped being editable, unseen by a render."""
    from PySide6.QtWidgets import QTableWidget

    app()
    tab = old_picture_tab("happy")
    assert (
        int(tab._history_table.editTriggers().value)
        == surface.EDIT_TRIGGERS_NONE_VALUE
        == 0
    )
    assert (
        int(tab._rules_table.editTriggers().value)
        == surface.EDIT_TRIGGERS_DEFAULT_VALUE
        == 26
    )
    assert tab._history_table.editTriggers() == QTableWidget.NoEditTriggers
    assert tab._rules_table.editTriggers() != QTableWidget.NoEditTriggers
    assert surface.EDIT_TRIGGERS_NONE == ()
    assert len(surface.EDIT_TRIGGERS_DEFAULT) == 3


def test_the_table_settings_are_compared_as_values():
    """A header or a row rule drifted between the two sides."""
    from PySide6.QtWidgets import QHeaderView

    app()
    tab = old_picture_tab("happy")
    for table, columns in (
        (tab._rules_table, surface.RULES_COLUMNS),
        (tab._history_table, surface.HISTORY_COLUMNS),
    ):
        assert table.columnCount() == len(columns) == 5
        header = table.horizontalHeader()
        assert [
            table.horizontalHeaderItem(index).text() for index in range(len(columns))
        ] == list(columns)
        assert header.sectionResizeMode(0) == QHeaderView.Stretch
        assert int(header.sectionResizeMode(0).value) == surface.HEADER_RESIZE_VALUE
        assert table.alternatingRowColors() is surface.ALTERNATING_ROW_COLORS
        assert table.verticalHeader().isVisible() is surface.VERTICAL_HEADER_VISIBLE
    assert surface.RULES_COLUMNS == ("Event", "Priority", "In-App", "Telegram", "Sound")
    assert surface.HISTORY_COLUMNS == (
        "Time",
        "Priority",
        "Title",
        "Message",
        "Channels",
    )


def test_the_layout_numbers_are_compared_as_values():
    """A margin or a spacing drifted between the two sides."""
    app()
    tab = old_picture_tab("empty")
    margins = tab.layout().contentsMargins()
    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == surface.CONTENT_MARGINS
    assert tab.layout().spacing() == surface.CONTENT_SPACING == 8
    assert surface.CONTENT_MARGINS == (8, 8, 8, 8)
    assert surface.PANE_MARGINS == (0, 0, 0, 0)


def test_the_buttons_are_enabled_and_run_the_action_the_surface_names():
    """A button stopped running the action the surface names for it."""
    app()
    manager = FakeManager(config=CONFIG_NONE, unread=0)
    tab = new_tab(manager)
    tab._tg_token.setText(SENT_BOT_KEY)
    tab._tg_chat.setText(SENT_CHAT_ID)
    tab._sms_phone.setText(PHONE_NUMBER)
    for button in (tab._tg_test, tab._btn_save, tab._btn_ack):
        assert button.isEnabled() is True
    tab._tg_test.click()
    assert manager.sent == [
        ["Acervator", "Test notification — Telegram is configured correctly!", None]
    ]
    tab._btn_save.click()
    assert manager.sms_calls == [[PHONE_NUMBER]]
    tab._btn_ack.click()
    assert manager.acknowledge_count == 1
    assert set(surface.ACTIONS.values()) == {
        "test_telegram",
        "save_config",
        "acknowledge_all",
    }
    assert surface.BUTTONS_ENABLED == {
        "test_button": True,
        "save_button": True,
        "ack_button": True,
    }


def test_the_recorded_calls_are_compared_as_values():
    """The ordered call list reached no pixel and was never compared."""
    model, _ = new_refresh_model("happy")
    names = [call[0] for call in model.calls]
    assert names == [
        "refresh.start",
        "refresh.config",
        "refresh.unread",
        "refresh.status",
        "refresh.rules",
        "refresh.history",
        "refresh.return",
    ]
    empty, _ = new_refresh_model("empty")
    assert [call[0] for call in empty.calls] == names
    assert model.calls[-1] == ["refresh.return", "painted", 2, 2]
    assert empty.calls[-1] == ["refresh.return", "painted", 0, 0]


BLIND_TO_THE_PICTURE = {
    "splitter_sizes": "test_the_splitter_sizes_are_compared_as_the_request",
    "splitter_handle_width": "test_the_splitter_sizes_are_compared_as_the_request",
    "splitter_collapsible": "test_the_splitter_sizes_are_compared_as_the_request",
    "placeholder_text": (
        "test_the_placeholders_and_the_hidden_field_are_compared_as_values"
    ),
    "echo_mode": "test_the_placeholders_and_the_hidden_field_are_compared_as_values",
    "accessible_name": "test_the_accessible_name_is_compared_as_a_string",
    "edit_triggers": "test_the_edit_rule_on_the_two_tables_is_compared_as_a_value",
    "header_resize_mode": "test_the_table_settings_are_compared_as_values",
    "vertical_header_visible": "test_the_table_settings_are_compared_as_values",
    "alternating_row_colors": "test_the_table_settings_are_compared_as_values",
    "content_margins": "test_the_layout_numbers_are_compared_as_values",
    "content_spacing": "test_the_layout_numbers_are_compared_as_values",
    "button_enabled": (
        "test_the_buttons_are_enabled_and_run_the_action_the_surface_names"
    ),
    "action_wiring": (
        "test_the_buttons_are_enabled_and_run_the_action_the_surface_names"
    ),
    "recorded_calls": "test_the_recorded_calls_are_compared_as_values",
    "manager_writes": "test_the_save_writes_only_what_the_shipped_tab_writes",
    "refusal_type": "test_the_outcome_set_holds_both_an_answer_and_a_refusal",
    "timer_delay": "test_the_tab_starts_no_timer",
    "bus_topic": "test_the_tab_subscribes_to_no_bus_topic",
    "non_text_cell": "test_the_number_where_text_belongs_is_kept_by_one_side_only",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    app()
    assert len(BLIND_TO_THE_PICTURE) == 20
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert_pictures_match(
        old_side=render_offscreen(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("happy"), PIXEL_SIZE),
    )


# The counterpart map


METHOD_MAP = {
    "AlertsTab.__init__": "AlertsTabModel.__init__",
    "AlertsTab._setup_ui": "AlertsTabModel.setup_ui",
    "AlertsTab._test_telegram": "AlertsTabModel.test_telegram",
    "AlertsTab._save_config": "AlertsTabModel.save_config",
    "AlertsTab._acknowledge_all": "AlertsTabModel.acknowledge_all",
    "AlertsTab.refresh": "AlertsTabModel.refresh",
}

MODEL_MEMBERS = {
    "__init__",
    "setup_ui",
    "test_telegram",
    "_test_finish",
    "save_config",
    "_save_finish",
    "acknowledge_all",
    "_ack_finish",
    "refresh",
    "_rule_row",
    "_history_row",
    "_refresh_finish",
}

HELPER_MAP = {
    "widget_node": "widget",
    "event_name": "event_title",
    "routing_word": "routed_text",
    "routing_colour": "routed_color",
    "priority_colour": "priority_color",
    "time_of_day": "clock_text",
    "table_cell": "cell",
    "blank_table_row": "blank_row",
    "manager_from_values": "build_manager",
    "payload": "build_view_model",
    "bridge_handler": "view_model",
}

SURFACE_ONLY_CLASSES = ("Priority", "NotificationRecord", "ManagerSnapshot")


def members(owner):
    """Every method and property a class defines, by name."""
    import inspect

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value) or isinstance(value, property):
            found.add(name)
    return found


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_classes():
    """Every class the shipped module defines, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_class_and_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert shipped_classes() == {"AlertsTab"}
    assert len(shipped_classes()) == 1
    assert members(shipped.AlertsTab) == {
        "__init__",
        "_setup_ui",
        "_test_telegram",
        "_save_config",
        "_acknowledge_all",
        "refresh",
    }
    assert len(members(shipped.AlertsTab)) == 6
    assert {name.split(".")[-1] for name in METHOD_MAP} == members(shipped.AlertsTab)
    assert len(METHOD_MAP) == 6
    for target in METHOD_MAP.values():
        assert callable(resolve(target)), target
    assert members(surface.AlertsTabModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 12
    assert {target.split(".")[-1] for target in METHOD_MAP.values()} < MODEL_MEMBERS
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 11
    for name in SURFACE_ONLY_CLASSES:
        assert callable(getattr(surface, name)), name


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "refresh" in members(shipped.AlertsTab)
    assert "_setup_ui" in members(shipped.AlertsTab)
    assert "logger" not in shipped_classes()
    assert "QWidget" not in shipped_classes()
    with pytest.raises(AttributeError):
        resolve("AlertsTabModel.no_such_member")
    assert MODEL_MEMBERS - {"refresh"} != MODEL_MEMBERS
    assert members(surface.AlertsTabModel) - {"setup_ui"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"AlertsTab.refresh"} != set(METHOD_MAP)
    assert set(HELPER_MAP.values()) & MODEL_MEMBERS == set()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    for old_name, new_name in (
        ("__init__", "__init__"),
        ("refresh", "refresh"),
        ("_test_telegram", "test_telegram"),
        ("_save_config", "save_config"),
        ("_acknowledge_all", "acknowledge_all"),
    ):
        old = list(inspect.signature(getattr(shipped.AlertsTab, old_name)).parameters)
        new = list(
            inspect.signature(getattr(surface.AlertsTabModel, new_name)).parameters
        )
        if old_name == "__init__":
            assert old == ["self", "notification_manager", "parent"]
            assert new == ["self", "notification_manager"]
            continue
        assert new == old, old_name
    assert list(inspect.signature(shipped.AlertsTab.refresh).parameters) == [
        "self",
        "notification_manager",
    ]
    refresh_default = inspect.signature(shipped.AlertsTab.refresh).parameters[
        "notification_manager"
    ]
    assert refresh_default.default is None
    model_default = inspect.signature(surface.AlertsTabModel.refresh).parameters[
        "notification_manager"
    ]
    assert model_default.default is None


def count_sites(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    assert count_sites(TAB_PATH, ".connect(") == TAB_CONNECT_SITES == 3
    assert count_sites(SURFACE_PATH, ".connect(") == 0
    assert len(surface.ACTIONS) == count_sites(TAB_PATH, ".connect(")
    assert set(surface.ACTIONS) == {
        "test_button.clicked",
        "save_button.clicked",
        "ack_button.clicked",
    }
    assert count_sites(TAB_PATH, "clicked.connect(") == 3
    assert count_sites(TAB_PATH, "a-call-this-tab-never-makes") == 0


def test_the_tab_starts_no_timer():
    """A wait appeared on one side and not the other.

    The counter is proved able to report by counting a neighbouring file
    that really does start one, and by starting one under the watcher.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    assert count_sites(TAB_PATH, "QTimer") == TAB_TIMER_SITES == 0
    assert count_sites(SURFACE_PATH, "QTimer") == 0
    assert count_sites(TIMER_NEIGHBOUR_PATH, "QTimer") > 0
    started: list = []
    original_start_timer = QObject.startTimer
    original_timer_start = QTimer.start
    original_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return original_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return original_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        for name in ("happy", "empty"):
            old_picture_tab(name)
            new_picture_tab(name)
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == len(observed) == 0


def test_the_tab_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_sites(TAB_PATH, ".subscribe(") == TAB_BUS_SITES == 0
    assert count_sites(SURFACE_PATH, ".subscribe(") == 0
    assert count_sites(BUS_NEIGHBOUR_PATH, ".subscribe(") > 0
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_sites(TAB_PATH, ".subscribe(")


def test_the_tab_declares_no_skin_of_its_own():
    """A colour the surface ships is one the tab never paints."""
    app()
    assert surface.SKIN == {}
    assert surface.TAB_STYLE_SHEET == ""
    assert_same_skin(
        build_old_side=lambda: old_picture_tab("happy"),
        build_new_side=lambda: new_picture_tab("happy"),
        size=PIXEL_SIZE,
        control_rule="QTableWidget { background: #3a1414; }",
        note="neither side carries a skin of its own",
    )


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {
        "__future__",
        "time",
        "typing",
        "design_system",
        "color_alpha",
    }
    for sibling in imported:
        beside = SURFACE_PATH.parent.parent / (sibling + ".py")
        if not beside.exists():
            continue
        pulled = {
            (node.module or "")
            for node in ast.walk(ast.parse(beside.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
        }
        assert not any(
            name.startswith(("PySide6", "shiboken")) for name in pulled
        ), f"{beside.name} pulls Qt into the surface: {sorted(pulled)}"
    tab_tree = ast.parse(TAB_PATH.read_text(encoding="utf-8"))
    tab_imports = {
        (node.module or "")
        for node in ast.walk(tab_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in tab_imports), tab_imports


def layout_entries(layout):
    """Every direct entry of one layout, in the order it was added."""
    found = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is not None:
            found.append(item.widget())
        elif item.layout() is not None:
            found.append(item.layout())
        else:
            found.append("stretch")
    return found


def entry_kinds(layout):
    """The class name of each entry of one layout, in order."""
    return [
        entry if isinstance(entry, str) else entry.metaObject().className()
        for entry in layout_entries(layout)
    ]


def test_the_widget_tree_is_the_tabs_own():
    """A widget appeared on one side, or moved to another parent."""
    from PySide6.QtWidgets import QGroupBox, QLineEdit, QPushButton, QTableWidget

    app()
    tab = old_picture_tab("empty")
    model = surface.AlertsTabModel()
    built = model.setup_ui()
    assert [node["name"] for node in built] == list(surface.WIDGET_NAMES)
    assert len(built) == 23
    assert entry_kinds(tab.layout()) == ["QSplitter"]
    split = layout_entries(tab.layout())[0]
    assert split.count() == 2
    left, right = split.widget(0), split.widget(1)
    assert entry_kinds(left.layout()) == [
        "QLabel",
        "QLabel",
        "QGroupBox",
        "QGroupBox",
        "QPushButton",
        "stretch",
    ]
    assert entry_kinds(right.layout()) == ["QGroupBox", "QGroupBox"]
    telegram_group, sms_group = layout_entries(left.layout())[2:4]
    rules_group, history_group = layout_entries(right.layout())
    assert entry_kinds(telegram_group.layout()) == [
        "QLabel",
        "QLineEdit",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QLabel",
    ]
    assert entry_kinds(sms_group.layout()) == ["QLabel", "QLineEdit", "QLabel"]
    assert entry_kinds(rules_group.layout()) == ["QTableWidget"]
    assert entry_kinds(history_group.layout()) == ["QHBoxLayout", "QTableWidget"]
    ack_row = layout_entries(history_group.layout())[0]
    assert entry_kinds(ack_row) == ["stretch", "QPushButton"]
    form = layout_entries(telegram_group.layout())
    assert form[0].text() == surface.TELEGRAM_BOT_LABEL
    assert form[2].text() == surface.CHAT_LABEL
    assert layout_entries(sms_group.layout())[0].text() == surface.PHONE_LABEL
    assert [group.title() for group in (telegram_group, sms_group)] == [
        "Telegram Bot",
        "SMS Alerts",
    ]
    assert [group.title() for group in (rules_group, history_group)] == [
        "Event Routing",
        "Notification History",
    ]
    assert len(tab.findChildren(QGroupBox)) == 4
    assert len(tab.findChildren(QTableWidget)) == 2
    assert len(tab.findChildren(QPushButton)) == 3
    assert len(tab.findChildren(QLineEdit)) == 3
    assert {found.text() for found in tab.findChildren(QPushButton)} == {
        "Test Telegram",
        "Save Configuration",
        "Acknowledge All",
    }
    assert surface.WIDGET_INDEX["status_label"] == 0
    assert surface.WIDGET_INDEX["unread_label"] == 1
    assert surface.WIDGET_INDEX["save_button"] == 4
    assert surface.WIDGET_INDEX["left_stretch"] == 5
    assert surface.WIDGET_CHILDREN["main_split"] == ("left", "right")
    assert surface.WIDGET_CHILDREN["left"] == (
        "status_label",
        "unread_label",
        "telegram_group",
        "sms_group",
        "save_button",
        "left_stretch",
    )
    assert surface.WIDGET_CHILDREN["telegram_group"] == (
        "token_input",
        "chat_input",
        "test_button",
        "telegram_status",
    )
    assert surface.WIDGET_PARENTS["history_table"] == "history_group"
    assert surface.WIDGET_KINDS["rules_table"] == "QTableWidget"
    assert model.calls[0] == ["setup.start"]
    assert model.calls[-1] == ["setup.return", 23]


# Every value reaches the compared snapshot


def normalise(value):
    """One value with every tuple turned into a list."""
    if isinstance(value, tuple):
        return [normalise(item) for item in value]
    if isinstance(value, list):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        return {key: normalise(item) for key, item in value.items()}
    return value


def freeze(value):
    """One value as a single comparable string."""
    return json.dumps(normalise(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    import inspect

    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if isinstance(value, surface.AlertsTabModel):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    model = surface.AlertsTabModel(make_manager("happy"))
    model.setup_ui()
    payloads.append(surface.build_view_model(model, action="refresh"))
    for name, action in (
        ("sent", "test_telegram"),
        ("no_credentials", "test_telegram"),
        ("no_manager", "test_telegram"),
    ):
        spec, token, chat_id = TELEGRAM_CASES[name]
        driven = surface.AlertsTabModel(telegram_manager(name))
        payloads.append(
            surface.build_view_model(
                driven,
                fields={"token": token, "chat_id": chat_id, "phone": PHONE_NUMBER},
                action=action,
            )
        )
    saved = surface.AlertsTabModel(save_manager("all_three"))
    payloads.append(
        surface.build_view_model(
            saved,
            fields={"token": SENT_BOT_KEY, "chat_id": "555", "phone": PHONE_NUMBER},
            action="save_config",
        )
    )
    acked = surface.AlertsTabModel(make_manager("unacknowledged"))
    payloads.append(surface.build_view_model(acked, action="acknowledge_all"))
    lonely = surface.AlertsTabModel(None)
    payloads.append(surface.build_view_model(lonely, action="refresh"))
    unknown = surface.AlertsTabModel(make_manager("unknown_priority"))
    payloads.append(surface.build_view_model(unknown, action="refresh"))
    return payloads


COVERED_ELSEWHERE = {
    "TEST_FAILED": "test_the_telegram_line_is_the_shipped_tabs_own",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped tab."""
    constants = surface_constants()
    assert len(constants) > 80
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "STATUS_TEXT" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "widgets": ("WIDGETS",),
    "widget_names": ("WIDGET_NAMES",),
    "widget_kinds": ("WIDGET_KINDS",),
    "widget_parents": ("WIDGET_PARENTS",),
    "widget_children": ("WIDGET_CHILDREN",),
    "widget_index": ("WIDGET_INDEX",),
    "button_names": ("BUTTON_NAMES",),
    "buttons_enabled": ("BUTTONS_ENABLED",),
    "content_margins": ("CONTENT_MARGINS",),
    "content_spacing": ("CONTENT_SPACING",),
    "pane_margins": ("PANE_MARGINS",),
    "splitter_orientation": ("SPLITTER_ORIENTATION",),
    "splitter_orientation_value": ("SPLITTER_ORIENTATION_VALUE",),
    "splitter_handle_width": ("SPLITTER_HANDLE_WIDTH",),
    "splitter_children_collapsible": ("SPLITTER_CHILDREN_COLLAPSIBLE",),
    "splitter_sizes": ("SPLITTER_SIZES",),
    "group_titles": (
        "TELEGRAM_GROUP_TITLE",
        "SMS_GROUP_TITLE",
        "RULES_GROUP_TITLE",
        "HISTORY_GROUP_TITLE",
    ),
    "row_labels": (
        "TELEGRAM_BOT_LABEL",
        "CHAT_LABEL",
        "PHONE_LABEL",
        "SPANNING_LABEL",
    ),
    "placeholders": (
        "TELEGRAM_BOT_PLACEHOLDER",
        "CHAT_PLACEHOLDER",
        "PHONE_PLACEHOLDER",
    ),
    "echo_modes": ("ECHO_NORMAL", "ECHO_HIDDEN"),
    "echo_values": ("ECHO_VALUES",),
    "button_texts": ("TEST_BUTTON_TEXT", "SAVE_BUTTON_TEXT", "ACK_BUTTON_TEXT"),
    "rules_columns": ("RULES_COLUMNS",),
    "history_columns": ("HISTORY_COLUMNS",),
    "rules_column_count": ("RULES_COLUMN_COUNT",),
    "history_column_count": ("HISTORY_COLUMN_COUNT",),
    "header_resize_mode": ("HEADER_RESIZE_MODE",),
    "header_resize_value": ("HEADER_RESIZE_VALUE",),
    "alternating_row_colors": ("ALTERNATING_ROW_COLORS",),
    "vertical_header_visible": ("VERTICAL_HEADER_VISIBLE",),
    "edit_triggers_default": ("EDIT_TRIGGERS_DEFAULT",),
    "edit_triggers_default_value": ("EDIT_TRIGGERS_DEFAULT_VALUE",),
    "edit_triggers_none": ("EDIT_TRIGGERS_NONE",),
    "edit_triggers_none_value": ("EDIT_TRIGGERS_NONE_VALUE",),
    "alignment": ("ALIGNMENT",),
    "alignment_value": ("ALIGNMENT_VALUE",),
    "styles": (
        "STATUS_STYLE",
        "UNREAD_WARNING_STYLE",
        "UNREAD_QUIET_STYLE",
        "SMS_STATUS_STYLE",
        "TELEGRAM_ERROR_STYLE",
        "TELEGRAM_SUCCESS_STYLE",
        "GROUP_BOX_STYLE",
        "TEST_BUTTON_STYLE",
        "SAVE_BUTTON_STYLE",
        "ACK_BUTTON_STYLE",
        "EMPTY_STYLE",
    ),
    "texts": (
        "STATUS_TEXT",
        "STATUS_SEPARATOR",
        "TELEGRAM_CONNECTED_TEXT",
        "SMS_CONNECTED_TEXT",
        "SAVED_TEXT",
        "UNREAD_FORMAT",
        "UNREAD_START_TEXT",
        "SMS_STATUS_TEXT",
        "TELEGRAM_STATUS_TEXT",
        "TELEGRAM_MISSING_TEXT",
        "TELEGRAM_SENT_TEXT",
        "TELEGRAM_FAILED_FORMAT",
        "TELEGRAM_TEST_TITLE",
        "TELEGRAM_TEST_MESSAGE",
        "YES_TEXT",
        "NO_TEXT",
        "TIME_FORMAT",
        "CHANNEL_JOIN",
        "EVENT_UNDERSCORE",
        "EVENT_SPACE",
    ),
    "telegram_test_priority": ("TELEGRAM_TEST_PRIORITY",),
    "cell_colors": (
        "CELL_YES_COLOR",
        "CELL_NO_COLOR",
        "UNACKNOWLEDGED_COLOR",
        "NO_COLOR",
    ),
    "priority_colors": ("PRIORITY_COLORS",),
    "priority_fallback_color": ("PRIORITY_FALLBACK_COLOR",),
    "priorities": (
        "PRIORITY_LOW",
        "PRIORITY_MEDIUM",
        "PRIORITY_HIGH",
        "PRIORITY_CRITICAL",
    ),
    "default_priority": ("DEFAULT_PRIORITY",),
    "routed_channels": ("ROUTED_CHANNELS",),
    "channels": ("CHANNEL_IN_APP", "CHANNEL_TELEGRAM", "CHANNEL_SOUND"),
    "config_keys": ("CONFIG_TELEGRAM_KEY", "CONFIG_SMS_KEY", "CONFIG_RULES_KEY"),
    "rule_keys": ("RULE_CHANNELS_KEY", "RULE_PRIORITY_KEY"),
    "message_max_chars": ("MESSAGE_MAX_CHARS",),
    "history_limit": ("HISTORY_LIMIT",),
    "priority_column": ("PRIORITY_COLUMN",),
    "colored_from_column": ("COLORED_FROM_COLUMN",),
    "test_paths": ("TEST_PATHS",),
    "save_paths": ("SAVE_PATHS",),
    "ack_paths": ("ACK_PATHS",),
    "refresh_paths": ("REFRESH_PATHS",),
    "no_path": ("NO_PATH",),
    "actions": ("ACTIONS",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "skin": ("SKIN",),
    "tab_style_sheet": ("TAB_STYLE_SHEET",),
    "status_text": ("model.status_text",),
    "status_style": ("model.status_style",),
    "unread_text": ("model.unread_text",),
    "unread_style": ("model.unread_style",),
    "telegram_status_text": ("model.telegram_status_text",),
    "telegram_status_style": ("model.telegram_status_style",),
    "sms_status_text": ("model.sms_status_text",),
    "sms_status_style": ("model.sms_status_style",),
    "token": ("model.token",),
    "chat_id": ("model.chat_id",),
    "phone": ("model.phone",),
    "rules_rows": ("model.rules_rows",),
    "history_rows": ("model.history_rows",),
    "test_path": ("model.test_path",),
    "save_path": ("model.save_path",),
    "ack_path": ("model.ack_path",),
    "refresh_path": ("model.refresh_path",),
    "has_manager": ("model.manager",),
    "calls": ("model.calls",),
}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        return getattr(model, name.split(".", 1)[1])
    return getattr(surface, name)


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources hold."""
    resolved = [resolve_source(name, model) for name in sources]
    if key == "has_manager":
        return value is (resolved[0] is not None)
    if len(sources) == 1:
        return freeze(value) == freeze(resolved[0])
    if isinstance(value, dict):
        return sorted(freeze(item) for item in value.values()) == sorted(
            freeze(item) for item in resolved
        )
    return [freeze(item) for item in value] == [freeze(item) for item in resolved]


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = surface.AlertsTabModel(make_manager("happy"))
    payload = surface.build_view_model(model, action="refresh")
    assert set(payload) == set(PAYLOAD_KEY_SOURCES)
    assert len(payload) == 84
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(model, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, model), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.AlertsTabModel(make_manager("happy"))
    payload = surface.build_view_model(model, action="refresh")
    assert backed("alignment", payload["alignment"], ("ALIGNMENT",), model)
    assert not backed("alignment", "AlignLeft", ("ALIGNMENT",), model)
    assert not backed("rules_columns", ["Event"], ("RULES_COLUMNS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)


# The bridge


BRIDGE_MANAGER = {
    "config": config(True, False, RULES_TWO),
    "history": [
        {
            "timestamp": CLOCK_STAMP,
            "priority": "high",
            "title": "Bot started",
            "message": "RAVE bot is live",
            "channels_sent": ["IN_APP"],
            "acknowledged": True,
        }
    ],
    "unread": 2,
}


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.AlertsTabModel(make_manager("happy"))
    payload = surface.build_view_model(model, action="refresh")
    encoded = json.loads(json.dumps(payload))
    assert encoded["method"] == "alerts_tab.state"
    assert encoded["accessible_name"] == "Notifications and Alerts tab"
    assert encoded["status_text"] == (
        "Notifications: Active | TG: Connected | SMS: Connected"
    )
    assert encoded["unread_text"] == "Unread: 1"
    assert encoded["refresh_path"] == "painted"
    assert encoded["rules_columns"] == [
        "Event",
        "Priority",
        "In-App",
        "Telegram",
        "Sound",
    ]
    assert encoded["alignment_value"] == 132
    assert encoded["splitter_sizes"] == [350, 550]
    assert encoded["actions"] == {
        "test_button.clicked": "test_telegram",
        "save_button.clicked": "save_config",
        "ack_button.clicked": "acknowledge_all",
    }
    assert encoded["timers"] == {}
    assert encoded["timer_delays_ms"] == []
    assert encoded["bus_topics"] == []
    assert encoded["skin"] == {}
    assert len(encoded["widgets"]) == 23
    assert encoded["history_rows"][0][1]["color"] == TEXT_HIGH_HEX
    assert [call[0] for call in encoded["calls"]][-1] == "refresh.return"


def test_bridge_registers_the_alerts_tab_method():
    """The renderer cannot reach the alerts tab through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "alerts_tab.state"
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 91,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "manager": BRIDGE_MANAGER,
                    "action": "refresh",
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["status_text"] == "Notifications: Active | TG: Connected"
    assert result["unread_text"] == "Unread: 2"
    assert result["refresh_path"] == "painted"
    assert len(result["rules_rows"]) == 2
    assert len(result["history_rows"]) == 1
    assert result["history_rows"][0][1]["text"] == "high"
    desktop_bridge.handle_line(
        json.dumps({"id": 92, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


def test_the_bridge_carries_every_action():
    """An action over the bridge left the tab unchanged."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 93, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    sent = call(
        {
            "reset": True,
            "manager": BRIDGE_MANAGER,
            "fields": {"token": SENT_BOT_KEY, "chat_id": "555"},
            "action": "test_telegram",
        }
    )
    assert sent["test_path"] == "sent"
    assert sent["telegram_status_text"] == "Test sent successfully!"
    saved = call({"fields": {"phone": PHONE_NUMBER}, "action": "save_config"})
    assert saved["save_path"] == "saved"
    assert saved["status_text"] == "Configuration saved!"
    acked = call({"action": "acknowledge_all"})
    assert acked["ack_path"] == "acknowledged"
    assert acked["unread_text"] == "Unread: 0"
    idle = call({"reset": True})
    assert idle["refresh_path"] == ""
    assert idle["calls"] == []
    assert idle["has_manager"] is False
    assert idle["rules_rows"] == []
    call({"reset": True})


def test_the_bridge_keeps_what_was_typed_until_a_reset():
    """The surface forgot the typed fields between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 94, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    first = call(
        {"reset": True, "manager": BRIDGE_MANAGER, "fields": {"token": SENT_BOT_KEY}}
    )
    assert first["token"] == SENT_BOT_KEY
    kept = call({})
    assert kept["token"] == SENT_BOT_KEY
    fresh = call({"reset": True})
    assert fresh["token"] == ""
    call({"reset": True})


# Without Qt at all

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'alerts_tab.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + "import json, sys\n"
    "from src.gui.main_tabs import alerts_tab_surface as s\n"
    "manager = s.build_manager({'config': {'telegram_configured': True,\n"
    "    'sms_configured': False, 'rules': {'bot_started':\n"
    "    {'channels': ['IN_APP'], 'priority': 'low'}}},\n"
    "    'history': [{'timestamp': 1700000000.0, 'priority': 'high',\n"
    "    'title': 'Bot started', 'message': 'RAVE bot is live',\n"
    "    'channels_sent': ['IN_APP'], 'acknowledged': True}], 'unread': 2})\n"
    "model = s.AlertsTabModel(manager)\n"
    "painted = model.refresh()\n"
    "model.token = 'abc123'\n"
    "model.chat_id = '555'\n"
    "tested = model.test_telegram()\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'status': painted['status_text'], 'unread': painted['unread_text'],\n"
    "    'rules': painted['rules_rows'], 'history': painted['history_rows'],\n"
    "    'refresh_path': model.refresh_path, 'test_path': model.test_path,\n"
    "    'telegram_text': tested['text'], 'widgets': len(s.WIDGETS),\n"
    "    'calls': len(model.calls)}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the alerts tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == "alerts_tab.state"
    assert result["accessible_name"] == "Notifications and Alerts tab"
    assert result["rules_columns"] == [
        "Event",
        "Priority",
        "In-App",
        "Telegram",
        "Sound",
    ]
    assert result["splitter_sizes"] == [350, 550]
    assert result["alignment_value"] == 132
    assert result["rules_rows"] == []
    assert result["history_rows"] == []


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_paints_the_tab_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["status"] == "Notifications: Active | TG: Connected"
    assert answered["unread"] == "Unread: 2"
    assert answered["refresh_path"] == "painted"
    assert answered["test_path"] == "sent"
    assert answered["telegram_text"] == "Test sent successfully!"
    assert answered["widgets"] == 23
    assert len(answered["rules"]) == 1
    assert [found["text"] for found in answered["rules"][0]] == [
        "Bot Started",
        "low",
        "Yes",
        "No",
        "No",
    ]
    assert answered["history"][0][1]["text"] == "high"
    assert answered["calls"] == 11


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_paints_the_tab():
    """The Qt block let the shipped tab through."""
    probe = BLOCK_QT + (
        "import json\n"
        "from src.gui import alerts_tab\n"
        "print(json.dumps({'built': hasattr(alerts_tab, 'AlertsTab'),\n"
        "    'has_qt': alerts_tab._HAS_QT}))\n"
    )
    answered = run_script(probe)
    assert answered["has_qt"] is False
    assert answered["built"] is False
