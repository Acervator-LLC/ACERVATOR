"""The main window paints the same colours after the token migration.

A failure means a `design_system` token edit, or a change to
`src/gui/main_window.py`, moved pixels in the operator's live GUI.

Every expected colour is the LITERAL the file shipped before the tokens
replaced it. An assertion fed by the token it measures cannot falsify
that token: both sides move together and a wrong colour passes.

Colours are read off the RENDER. A stylesheet string reports what a
widget was told to paint, not what reached the screen. `MainWindow`
itself is never rendered whole: two instances built from one source
produce different images, so its chrome is located by exact stylesheet
text and each owning child widget is rendered on its own.
"""

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

AMMO_SCRUM = "#00ff88"
AMMO_FOLD = "#ff3366"
AMMO_NEUTRAL = "#a8a8c5"

LOG_TIMESTAMP = "#888888"
LOG_SENT = "#00ffcc"
LOG_FILLED = "#00ff88"
LOG_PLACED = "#ffaa00"
LOG_CANCELLED = "#ff3366"
LOG_WIRE_FLOW = "#ff66dd"
LOG_WIRE_STACK = "#ffcc44"
LOG_UNKNOWN_LEVEL = "#e0e0f0"

SPOOL_MARKET = "#88ccff"
SPOOL_PLACEHOLDER = "#555555"

CARD_LABEL = "#7a7d99"
CARD_VALUE = "#00ffcc"

DOT_REVEALED = "#00ffee"

SPENDABLE_LABEL = "#888888"
SPENDABLE_SEPARATOR = "#2a2a3a"
SPENDABLE_NEUTRAL = "#cccccc"

STATE_RUNNING = "#00ff88"
STATE_IDLE = "#888888"
STATE_PAUSED = "#ffaa00"
STATE_ERROR = "#ff3366"
STATE_COOLDOWN = "#ff6600"
STATE_STOPPED = "#666666"
STATE_STARTING = "#00e6ff"
TABLE_INFO_SOFT = "#66ccff"
TABLE_PLACEHOLDER = "#555555"

API_INFO = "#00aaff"
API_SUCCESS = "#00ff88"
API_WARNING = "#ffaa00"
API_ERROR = "#ff3366"
API_DEFAULT = "#cccccc"

EXCHANGE_BADGE = "#7fb3ff"
EXCHANGE_DIM = "#a8a8c5"

# TradeChartsTab and CapitalRegistryPanel read no design_system token;
# these are the Qt palette colours they ship with.
CHARTS_GROUND = "#efefef"
CHARTS_FRAME = "#b8b8b8"
REGISTRY_ROW = "#ffffff"
REGISTRY_ALT_ROW = "#f7f7f7"
REGISTRY_TEXT = "#000000"

TOOLBAR_GROUND = "#14141e"
TOOLBAR_RULE = "#2a2a3a"
BUTTON_GROUND = "#1a1a26"
BUTTON_BORDER = "#3a3a4a"
BUTTON_TEXT = "#c0c0c0"
CONSOLE_GROUND = "#0a0a12"
GATE_LOG_GROUND = "#05050a"
GATE_LOG_HEADER_GROUND = "#0a0a14"
GATE_LOG_HEADER_TEXT = "#00ffcc"
GATE_LOG_HEADER_RULE = "#2a2a44"

TOOLBAR_STRIP = "QWidget { background: #14141e; border-bottom: 1px solid #2a2a3a; }"
TOOLBAR_TOGGLE = (
    "QPushButton { background: #1a1a26; color: #c0c0c0; border: 1px solid #3a3a4a; "
    "padding: 4px 12px; font-family: Consolas; font-size: 10px; }"
    "QPushButton:checked { background: #663300; color: #ffaa00; "
    "border-color: #ffaa00; }"
    "QPushButton:hover { background: #22222e; }"
)
TOOLBAR_BUTTON = (
    "QPushButton { background: #1a1a26; color: #c0c0c0; border: 1px solid #3a3a4a; "
    "padding: 4px 12px; font-family: Consolas; font-size: 10px; }"
    "QPushButton:hover { background: #22222e; }"
)
CONSOLE_PANE = (
    "QPlainTextEdit { background: #0a0a12; color: #c0c0c0; "
    "border: none; padding: 4px; }"
)
GATE_LOG_PANE = (
    "QPlainTextEdit{background:#05050a;color:#c0ffe0;"
    "font-family:Consolas;font-size:10px;border:none;}"
)
GATE_LOG_HEADER = (
    "background:#0a0a14;color:#00ffcc;font-family:Consolas;"
    "font-size:10px;padding:3px;border-top:1px solid #2a2a44;"
)
CHROME = {
    TOOLBAR_STRIP: (TOOLBAR_GROUND, TOOLBAR_RULE),
    TOOLBAR_TOGGLE: (BUTTON_GROUND, BUTTON_BORDER, BUTTON_TEXT),
    TOOLBAR_BUTTON: (BUTTON_GROUND, BUTTON_BORDER, BUTTON_TEXT),
    CONSOLE_PANE: (CONSOLE_GROUND,),
    GATE_LOG_PANE: (GATE_LOG_GROUND,),
    GATE_LOG_HEADER: (
        GATE_LOG_HEADER_GROUND,
        GATE_LOG_HEADER_TEXT,
        GATE_LOG_HEADER_RULE,
    ),
}

STATES = ("running", "idle", "paused", "error", "cooldown", "stopped", "starting")


def _count_colour(image, expected_hex: str) -> int:
    """Pixels in `image` whose painted colour equals `expected_hex`."""
    from PySide6.QtGui import QColor

    want = QColor(expected_hex).rgb()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).rgb() == want
    )


def _scrum_status(index: int, state: str) -> dict:
    """One SCRUMMING row for `BotStatusTable.update_bots`."""
    return {
        "bot_id": f"botid{index:04d}aaaa",
        "symbol": "BTC/USD",
        "exchange": "coinbase",
        "mode": "scrumming",
        "state": state,
        "current_holdings": 0.5 + index,
        "quote_to_usd": 1.0,
        "target_balance": 100.0,
        "live_target_balance": 100.0 + index,
        "stats": {
            "position_value": 100.0 + (index - 3) * 20.0,
            "current_price": 200.0,
            "total_trades": index,
            "ytd_folded_usd": 1.0 * index,
            "ytd_scrummed_usd": 2.0 * index,
        },
    }


def _extractor_status(index: int, state: str) -> dict:
    """One EXTRACTOR row for `ExtractorBotTable.update_bots`."""
    return {
        "bot_id": f"extractor-{index}",
        "base_currency": "BTC",
        "state": state,
        "chunk_size_usd": 100.0,
        "chunk_size_base": 2.0,
        "chunk_free_base": 1.0,
        "n_positions_open": index % 3,
        "n_positions_drawdown": index % 2,
        "pool_color": ("green", "yellow", "red")[index % 3],
        "stats": {"total_trades": index},
    }


def build_status_log(module):
    """A StatusLog carrying one message per colour branch."""
    widget = module.StatusLog()
    widget.log("TRADE NOTIFICATION: FILLED 0.01 BTC", "info")
    widget.log("TRADE NOTIFICATION: PLACED 0.01 BTC", "info")
    widget.log("TRADE NOTIFICATION: SENT 0.01 BTC", "info")
    widget.log("TRADE NOTIFICATION: CANCELLED 0.01 BTC", "info")
    widget.log("WIRE FLOW 12.00 USD", "info")
    widget.log("WIRE STACK 12.00 USD", "info")
    widget.log("plain unknown level", "nosuchlevel")
    return widget, (700, 260)


def build_notification_spool(module):
    """A NotificationSpool carrying one message per level."""
    widget = module.NotificationSpool()
    for level in ("info", "success", "warning", "error", "market", "nosuchlevel"):
        widget.notify(f"message {level}", level)
    return widget, (700, 160)


def build_stat_card(module):
    return module.StatCard("Total Value", "$12,345.67"), (240, 90)


def build_privacy_dot(module):
    return module.PrivacyDot("main_window_pixel_parity"), (40, 40)


def build_spendable_profits(module):
    return module.SpendableProfitsWidget(), (420, 160)


def build_bot_status_table(module):
    widget = module.BotStatusTable()
    widget.update_bots([_scrum_status(i, s) for i, s in enumerate(STATES)])
    return widget, (1400, 360)


def build_extractor_table(module):
    widget = module.ExtractorBotTable()
    widget.update_bots([_extractor_status(i, s) for i, s in enumerate(STATES)])
    return widget, (1400, 360)


def build_api_tester(module):
    """An APITesterTab carrying one result line per level."""
    widget = module.APITesterTab()
    for level in ("info", "success", "warning", "error", "nosuchlevel"):
        widget._log("Ping", "ok", 12, level)
    return widget, (1000, 700)


def build_exchange_tab(module):
    return module.ExchangeTab("coinbase", "Coinbase"), (1200, 800)


def build_trade_charts(module):
    return module.TradeChartsTab(), (900, 600)


def _reservation(index):
    """One row for `CapitalRegistryPanel.update_from_registry`."""
    return SimpleNamespace(
        bot_id=f"bot-{index}",
        exchange_id="coinbase",
        base_currency="USD",
        reserved_usd=100.0 + index,
        reserved_base=0.5 + index,
        bot_mode="scrumming",
        last_rate_usd_per_base=1000.0 + index,
    )


def build_capital_registry(module):
    widget = module.CapitalRegistryPanel()
    widget.update_from_registry(
        SimpleNamespace(get_reservations=lambda: [_reservation(i) for i in range(3)])
    )
    return widget, (900, 240)


BUILDERS = {
    "StatusLog": build_status_log,
    "NotificationSpool": build_notification_spool,
    "StatCard": build_stat_card,
    "PrivacyDot": build_privacy_dot,
    "SpendableProfitsWidget": build_spendable_profits,
    "BotStatusTable": build_bot_status_table,
    "ExtractorBotTable": build_extractor_table,
    "APITesterTab": build_api_tester,
    "ExchangeTab": build_exchange_tab,
    "TradeChartsTab": build_trade_charts,
    "CapitalRegistryPanel": build_capital_registry,
}


def _render(name):
    from tests.qt_pixel import ensure_app, render_widget
    import src.gui.main_window as mw

    ensure_app()
    widget, size = BUILDERS[name](mw)
    return render_widget(widget, size=size)


def test_ammo_cell_constants_are_the_shipped_colours() -> None:
    """A failure means an Ammo cell repainted in the operator's bot table."""
    import src.gui.main_window as mw

    assert mw._AMMO_SCRUM == AMMO_SCRUM
    assert mw._AMMO_FOLD == AMMO_FOLD
    assert mw._AMMO_NEUTRAL == AMMO_NEUTRAL


def test_target_denom_cell_falls_back_to_the_shipped_neutral() -> None:
    """A failure means the blank Target-BTC / Target-ETH cell changed colour."""
    import src.gui.main_window as mw

    assert mw._compose_table_target_denom_cell("", "BTC", "coinbase", 100.0) == (
        "",
        AMMO_NEUTRAL,
    )


def test_status_log_paints_every_stage_colour() -> None:
    """A failure means a trade-notification line changed colour."""
    image = _render("StatusLog")
    for colour in (
        LOG_TIMESTAMP,
        LOG_SENT,
        LOG_FILLED,
        LOG_PLACED,
        LOG_CANCELLED,
        LOG_WIRE_FLOW,
        LOG_WIRE_STACK,
        LOG_UNKNOWN_LEVEL,
    ):
        assert _count_colour(image, colour) > 0, colour


def test_notification_spool_paints_every_level_colour() -> None:
    """A failure means a market or bot notification changed colour."""
    image = _render("NotificationSpool")
    for colour in (
        LOG_SENT,
        LOG_FILLED,
        LOG_PLACED,
        LOG_CANCELLED,
        SPOOL_MARKET,
        LOG_UNKNOWN_LEVEL,
        SPOOL_PLACEHOLDER,
    ):
        assert _count_colour(image, colour) > 0, colour


def test_stat_card_paints_its_label_and_value() -> None:
    """A failure means a header stat card changed colour."""
    image = _render("StatCard")
    assert _count_colour(image, CARD_LABEL) > 0
    assert _count_colour(image, CARD_VALUE) > 0


def test_privacy_dot_paints_its_revealed_cyan() -> None:
    """A failure means the privacy dot changed colour."""
    image = _render("PrivacyDot")
    assert _count_colour(image, DOT_REVEALED) > 0


def test_spendable_profits_paints_its_chrome() -> None:
    """A failure means the spendable-profits panel changed colour."""
    image = _render("SpendableProfitsWidget")
    for colour in (
        SPENDABLE_LABEL,
        SPENDABLE_SEPARATOR,
        SPENDABLE_NEUTRAL,
        AMMO_SCRUM,
        CARD_VALUE,
    ):
        assert _count_colour(image, colour) > 0, colour


def test_bot_status_table_paints_every_state_colour() -> None:
    """A failure means a Mode cell in the Scrumming Bots table changed colour."""
    image = _render("BotStatusTable")
    for colour in (
        STATE_RUNNING,
        STATE_IDLE,
        STATE_PAUSED,
        STATE_ERROR,
        STATE_COOLDOWN,
        STATE_STOPPED,
        STATE_STARTING,
        TABLE_INFO_SOFT,
        TABLE_PLACEHOLDER,
        AMMO_NEUTRAL,
    ):
        assert _count_colour(image, colour) > 0, colour


def test_extractor_table_paints_every_state_colour() -> None:
    """A failure means a Mode cell in the Extractor table changed colour."""
    image = _render("ExtractorBotTable")
    for colour in (
        STATE_RUNNING,
        STATE_IDLE,
        STATE_PAUSED,
        STATE_ERROR,
        STATE_COOLDOWN,
        STATE_STOPPED,
        STATE_STARTING,
        TABLE_PLACEHOLDER,
    ):
        assert _count_colour(image, colour) > 0, colour


def test_api_tester_paints_every_result_level() -> None:
    """A failure means an API-tester result line changed colour."""
    image = _render("APITesterTab")
    for colour in (API_INFO, API_SUCCESS, API_WARNING, API_ERROR, API_DEFAULT):
        assert _count_colour(image, colour) > 0, colour


def test_exchange_tab_paints_its_badge_and_dim_text() -> None:
    """A failure means the exchange tab header changed colour."""
    image = _render("ExchangeTab")
    assert _count_colour(image, EXCHANGE_BADGE) > 0
    assert _count_colour(image, EXCHANGE_DIM) > 0


def test_trade_charts_tab_paints_its_scroll_chrome() -> None:
    """A failure means the Asset Charts backdrop changed colour."""
    image = _render("TradeChartsTab")
    assert _count_colour(image, CHARTS_GROUND) > 0
    assert _count_colour(image, CHARTS_FRAME) > 0


def test_capital_registry_panel_paints_its_rows() -> None:
    """A failure means the capital-reservation table changed colour."""
    image = _render("CapitalRegistryPanel")
    for colour in (REGISTRY_ROW, REGISTRY_ALT_ROW, REGISTRY_TEXT):
        assert _count_colour(image, colour) > 0, colour


def test_main_window_chrome_paints_its_shipped_colours() -> None:
    """A failure means the toolbar, console or gate-log chrome changed colour."""
    from PySide6.QtWidgets import QWidget

    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.main_window import MainWindow

    ensure_app()
    window = MainWindow(bot_manager=None, settings_manager=None)
    try:
        children = window.findChildren(QWidget)
        for sheet, colours in CHROME.items():
            owners = [w for w in children if w.styleSheet() == sheet]
            assert owners, sheet
            image = render_widget(owners[0], size=(240, 60))
            for colour in colours:
                assert _count_colour(image, colour) > 0, (colour, sheet)
    finally:
        window.close()
        window.deleteLater()
