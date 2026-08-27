"""The Live Bot Settings dialog paints the same colours after the token
migration.

A failure means a `design_system` token edit, or a change to
`src/gui/bot_live_settings.py`, moved pixels in the dialog the operator
opens to change a bot's settings.

Every expected colour is the LITERAL the file shipped before the tokens
replaced it. An assertion fed by the token it measures cannot falsify
that token: both sides move together and a wrong colour passes.

Colours are read off the RENDER. A stylesheet string reports what the
widget was told to paint, not what reached the screen. Six colours sit
on `:hover` and `:disabled` rules that an offscreen render never enters;
those are pinned as stylesheet text and are named as such.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

FROZEN_NOW = 1_787_500_000.0
DIALOG_SIZE = (1400, 900)
TAB_SIZE = (1200, 700)

FOLD_ROW_FILL = "#123a63"
FOLD_ROW_EDGE = "#6ea6e6"
EXTRACTOR_ROW_FILL = "#b3261e"
EXTRACTOR_ROW_EDGE = "#ffb0a6"
EXTRACTOR_ROW_TEXT = "#ffffff"
SOURCE_MANUAL = "#00ccff"

#: Painted somewhere in the dialog, by the shipped literal.
PALETTE = {
    "#00ccff": "manual fold source, Fire button",
    "#00ff88": "gain, open price gate",
    "#00ffcc": "dialog header, Apply button",
    "#0a0a12": "group-box ground",
    "#123a63": "fold tranche row fill",
    "#1a1a2e": "nav button ground",
    "#2a2a3f": "card border, Close button",
    "#333333": "disabled Apply ground",
    "#3a2020": "clear-counter button ground",
    "#3a3a5f": "Close button border",
    "#440011": "self-destruct ground",
    "#444444": "disabled clear-counter border",
    "#666666": "disabled Apply text",
    "#66ccff": "stack tranche header",
    "#6ea6e6": "fold tranche row edge",
    "#888888": "idle state, empty-list text",
    "#8a8aab": "positions empty state",
    "#a8a8c5": "unknown pool colour",
    "#aaaaaa": "hint and message text",
    "#b3261e": "extractor tranche row fill",
    "#cccccc": "wire provenance text",
    "#e0e0f0": "fold tranche row text",
    "#ff3366": "loss, destructive control",
    "#ff6600": "manual fire button",
    "#ff9900": "shut price gate, fold ratio amber",
    "#ffaa00": "paused and cooldown state",
    "#ffb0a6": "extractor tranche row edge",
    "#ffffff": "extractor tranche row text",
}

#: On a `:hover` or `:disabled` rule. No offscreen render enters those
#: states, so these are pinned as stylesheet text instead of pixels.
PSEUDO_STATE = {
    "#001122": "text on the Fire button hover fill",
    "#00ddaa": "Apply button hover ground",
    "#1a1a1a": "disabled Fire button ground",
    "#555555": "disabled Fire and nav button text",
    "#660022": "self-destruct hover ground",
    "#ff8833": "manual fire hover ground",
}

#: Absent from the dialog. The control colour for the sampler.
ABSENT = "#7f00ff"


class _Exchange:
    exchange_id = "test"


class _Ledger:
    wired_in = 40.0
    wired_out = 15.0
    provenance = {"scrum-btc": 25.0, "scrum-eth": 15.0}
    mature_profit_total = 12.0
    mature_profit_allocated = 4.0


class _WireManager:
    def __init__(self, bot_id):
        self._wires = {}
        self._ledgers = {bot_id: _Ledger()}
        self._transactions = []
        self._bot_refs = {}


def _pixels(image):
    """The image as a height x width array of packed RGB values."""
    import numpy as np
    from PySide6.QtGui import QImage

    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    array = np.frombuffer(bytes(rgb.constBits()), dtype=np.uint32)
    return array.reshape(rgb.height(), rgb.bytesPerLine() // 4)[:, : rgb.width()]


def _colours(image) -> set:
    """Every colour painted in `image`, as lowercase #rrggbb."""
    import numpy as np

    return {"#%06x" % int(v & 0xFFFFFF) for v in np.unique(_pixels(image))}


def _tranches(count):
    return [
        {
            "usd": 3.31,
            "units": 101.5,
            "ref": 0.02977,
            "initial_buy_price": 0.02957,
            "created_ts": FROZEN_NOW - 900.0 * i,
            "operator_initiated": i % 2 == 0,
        }
        for i in range(count)
    ]


def _extractor_child(bot_id, base_currency):
    from src.trading.bot_container import BotMode, BotState, make_bot_config
    from src.trading.extractor_bot import ExtractorBot, ExtractorPosition

    bot = object.__new__(ExtractorBot)
    bot.bot_id = bot_id
    bot.config = make_bot_config(
        BotMode.EXTRACTOR,
        exchange_id="test",
        base_currency=base_currency,
        target_asset="*",
    )
    bot.state = BotState.RUNNING
    position = ExtractorPosition(
        pair=f"SOL/{base_currency}",
        state="in_flight",
        artillery_size_base=0.5,
        artillery_size_usd_at_entry=1500.0,
        alt_units=100.0,
        entry_price_base_per_alt=0.005,
        avg_buy_price_base_per_alt=0.005,
        cost_basis_base=0.5,
        opened_at=FROZEN_NOW - 3600,
    )
    position.last_price_base_per_alt = 0.006
    position.last_priced_at = FROZEN_NOW - 60
    bot._positions = {position.pair: position}
    bot._chunk_to_base_rate = 3000.0
    return bot


def _scrum_bot(bot_id, tranche_count):
    from src.trading.bot_container import BotMode, BotState, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
    )
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=True)
    bot.bot_id = bot_id
    bot.state = BotState.RUNNING
    bot._fold_tranches = _tranches(tranche_count)
    bot._current_holdings = 8193.0
    bot._tranches_created_lifetime = 12
    bot._tranches_closed_lifetime = 8
    bot._tranches_discarded_lifetime = 3
    bot._pending_wire_credits = 5.0
    bot._position_health = {
        "realized_pnl": 12.5,
        "unrealized_pnl": -12.5,
        "avg_entry_price": 0.0295,
        "cost_basis_total": 240.0,
        "total_fees": 1.25,
        "trade_count": 7,
        "fetched_at": FROZEN_NOW - 30,
    }
    bot._smart_wire_mgr = _WireManager(bot_id)
    bot._stack_tranches = [
        {
            "usd": 2.0,
            "units": 50.0,
            "target_price": 0.031,
            "status": "filled",
            "mode": "stack",
            "fill_price": 0.0309,
            "created_ts": FROZEN_NOW - 1200,
        },
        {
            "usd": 2.0,
            "units": 50.0,
            "target_price": 0.032,
            "status": "cancelled",
            "mode": "stack",
            "created_ts": FROZEN_NOW - 2400,
        },
    ]
    bot._stack_created = 4
    bot._stack_discarded = 1
    return bot


@pytest.fixture
def themed(monkeypatch):
    """The theme `main.py` applies when none is chosen, and a fixed clock.

    An application stylesheet is global, so it is put back: a theme left
    behind changes what every later GUI file in the session renders.
    """
    from PySide6.QtWidgets import QApplication

    from src.gui.theme_engine import THEMES, generate_qss

    monkeypatch.setattr(time, "time", lambda: FROZEN_NOW)
    app = QApplication.instance() or QApplication([])
    before = app.styleSheet()
    app.setStyleSheet(generate_qss(THEMES["cyberpunk_dark"]))
    yield app
    app.setStyleSheet(before)


@pytest.fixture
def dialog(themed):
    """The real dialog, with fold tranches, Extractor children and a sibling."""
    from src.core.event_bus import EventBus
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotManager

    parent = _scrum_bot("scrum-parent", 6)
    sibling = _scrum_bot("scrum-sibling", 1)
    kids = [_extractor_child("ext-a", "CHIP"), _extractor_child("ext-b", "CHIP")]
    manager = BotManager(bus=EventBus())
    for bot in (parent, sibling, *kids):
        manager._bots[bot.bot_id] = bot
    parent._bot_manager = manager

    dlg = BotLiveSettingsDialog(parent, manager, None)
    dlg.resize(*DIALOG_SIZE)
    dlg.show()
    themed.processEvents()
    yield dlg
    dlg.close()


@pytest.fixture
def positions_tab(themed):
    """The Extractor-only tab, built off a dialog stub."""
    from PySide6.QtWidgets import QDialog

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    bot = _extractor_child("ext-tab", "CHIP")
    bot.pool_color = lambda: "unknown"
    bot.positions_for_gui = lambda: [
        {
            "pair": "SOL/CHIP",
            "state": "in_flight",
            "tier": 1,
            "alt_units": 100.0,
            "entry_usd": 12.0,
            "current_usd": 13.5,
            "delta_pct": 12.5,
            "corrections": 0,
        }
    ]
    bot._chunk_size_usd = 50.0
    bot._chunk_free_base = 0.25
    bot._chunk_size_base = 0.5
    bot._chunk_extracted_total = 1.5
    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = bot
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_positions_held_tab()
    widget.resize(*TAB_SIZE)
    widget.ensurePolished()
    themed.processEvents()
    yield dlg, widget
    dlg.close()


def _quiet_dialog(themed):
    """A paused bot with nothing to clear: the states the busy one hides.

    The paused state colour and the disabled clear-button border are
    only on screen when the bot is paused and its ledgers are empty.
    """
    from src.core.event_bus import EventBus
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotManager, BotState

    bot = _scrum_bot("scrum-quiet", 0)
    bot.state = BotState.PAUSED
    bot._tranches_created_lifetime = 0
    bot._tranches_closed_lifetime = 0
    bot._tranches_discarded_lifetime = 0
    bot._pending_wire_credits = 0.0
    bot._stack_tranches = []
    bot._stack_created = 0
    bot._stack_discarded = 0
    manager = BotManager(bus=EventBus())
    manager._bots[bot.bot_id] = bot
    bot._bot_manager = manager
    dlg = BotLiveSettingsDialog(bot, manager, None)
    dlg.resize(*DIALOG_SIZE)
    dlg.show()
    themed.processEvents()
    return dlg


def _empty_positions_tab(themed):
    from PySide6.QtWidgets import QDialog

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    bot = _extractor_child("ext-empty", "CHIP")
    bot.pool_color = lambda: "green"
    bot.positions_for_gui = lambda: []
    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = bot
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_positions_held_tab()
    widget.resize(*TAB_SIZE)
    widget.ensurePolished()
    themed.processEvents()
    return dlg, widget


def _tab_images(dialog, app):
    """One render per tab, plus the dialog chrome around them."""
    from PySide6.QtWidgets import QScrollArea

    images = {}
    tabs = dialog._tabs
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        app.processEvents()
        page = tabs.widget(index)
        content = page.widget() if isinstance(page, QScrollArea) else page
        content.ensurePolished()
        app.processEvents()
        images[tabs.tabText(index)] = content.grab().toImage()
    images["chrome"] = dialog.grab().toImage()
    return images


def _sheet_text(*roots):
    from PySide6.QtWidgets import QWidget

    parts = []
    for root in roots:
        parts.append(root.styleSheet())
        parts += [w.styleSheet() for w in root.findChildren(QWidget)]
    return "\n".join(parts)


def test_every_shipped_colour_is_still_painted(dialog, positions_tab, themed) -> None:
    """A failure names a colour that left the operator's screen."""
    painted = set()
    for image in _tab_images(dialog, themed).values():
        painted |= _colours(image)
    _tab_dlg, tab_widget = positions_tab
    painted |= _colours(tab_widget.grab().toImage())
    empty_dlg, empty_widget = _empty_positions_tab(themed)
    try:
        painted |= _colours(empty_widget.grab().toImage())
    finally:
        empty_dlg.close()
    quiet = _quiet_dialog(themed)
    try:
        for image in _tab_images(quiet, themed).values():
            painted |= _colours(image)
    finally:
        quiet.close()

    missing = {value: where for value, where in PALETTE.items() if value not in painted}
    assert not missing, missing
    assert ABSENT not in painted


def test_the_tranche_rows_paint_their_own_skins(dialog, themed) -> None:
    """A failure means a tranche row lost its fill, edge or text colour."""
    images = _tab_images(dialog, themed)
    fold = _colours(images["Fold Tranches"])
    for value in (
        FOLD_ROW_FILL,
        FOLD_ROW_EDGE,
        EXTRACTOR_ROW_FILL,
        EXTRACTOR_ROW_EDGE,
        EXTRACTOR_ROW_TEXT,
        SOURCE_MANUAL,
    ):
        assert value in fold, value
    assert ABSENT not in fold


def test_pseudo_state_colours_stay_in_the_stylesheets(
    dialog, positions_tab, themed
) -> None:
    """A failure means a hover or disabled skin changed colour."""
    tab_dlg, tab_widget = positions_tab
    text = _sheet_text(dialog, tab_dlg, tab_widget)
    missing = {v: where for v, where in PSEUDO_STATE.items() if v not in text}
    assert not missing, missing


def test_the_colour_sampler_can_fail(dialog, themed) -> None:
    """A failure means the sampler reports every colour present.

    Without this, the assertions above pass over a blank render.
    """
    fold = _colours(_tab_images(dialog, themed)["Fold Tranches"])
    assert FOLD_ROW_FILL in fold
    assert "#123a64" not in fold, "one digit off the fold fill is reported present"
    assert len(fold) > 1, "the render carries a single colour; nothing was painted"
