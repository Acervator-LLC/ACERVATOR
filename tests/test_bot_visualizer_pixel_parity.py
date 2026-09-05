"""The bot visualizer paints the same colours after the token migration.

A failure means a `design_system` token edit, or a change to
`src/gui/bot_visualizer.py`, moved pixels in the operator's live GUI.

Every expected colour is the LITERAL the file shipped before the tokens
replaced it. An assertion fed by the token it measures cannot falsify that
token: both sides move together and a wrong colour passes.

Colours are read off the RENDER. `setStyleSheet` strings and `QPainter`
calls report what the widget was told to paint, not what reached the screen.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

TAB = (1400, 900)
QRM = (600, 300)
ROW = (700, 40)
MENU = (320, 200)

CFG = {
    "symbol": "BTC-USD",
    "pair": "BTC-USD",
    "target": 100.0,
    "capital": 500.0,
    "mode": "SCRUM",
    "timeframe": "1m",
    "metric_init": "$100.00",
    "status": "RUNNING",
}

# Every colour the migration replaced, keyed by the token that now holds it.
# Values are the literals the file shipped at 65f6e95.
SHIPPED = {
    "ACCENT_GOLD": "#ffd700",
    "CARD_METRIC_BORDER": "#2a2a3f",
    "CARD_METRIC_LABEL": "#888888",
    "ERROR": "#ff3366",
    "MENU_BORDER": "#3a3a5f",
    "MENU_ITEM_SELECTED": "#2a2a4f",
    "MENU_SURFACE": "#1a1a2f",
    "PRIMARY_BRIGHT": "#00ffee",
    "SUCCESS": "#00ff88",
    "TEXT_HIGH": "#e0e0f0",
    "TEXT_INACTIVE": "#aaaaaa",
    "TEXT_PLACEHOLDER": "#555555",
    "VIZ_CAPTION": "#445566",
    "VIZ_CAPTION_DIM": "#556677",
    "VIZ_CONFIRM_SURFACE": "#003822",
    "VIZ_GO_HOVER": "#001a0a",
    "VIZ_HEADING": "#c8d8f0",
    "VIZ_INPUT_BORDER": "#2244aa",
    "VIZ_INPUT_SURFACE": "#142244",
    "VIZ_LANE_LIVE": "#091a0e",
    "VIZ_LANE_PAPER": "#0e0e09",
    "VIZ_LIST_BORDER": "#1a2a4a",
    "VIZ_LIST_SURFACE": "#0a0a18",
    "VIZ_LIST_TEXT": "#aaccff",
    "VIZ_NUCLEAR_BORDER": "#cc0000",
    "VIZ_NUCLEAR_SURFACE": "#ff0000",
    "VIZ_PANEL_BORDER": "#1a1a3f",
    "VIZ_PANEL_SURFACE": "#0c0c1a",
    "VIZ_STOP_HOVER": "#1a0011",
    "VIZ_SWARM_SURFACE": "#070710",
    "VIZ_TAB_SELECTED": "#0a0a20",
    "VIZ_TAB_TEXT": "#666677",
}

# Grounds only a `:hover` rule paints, which the offscreen platform never
# reaches. Each maps to the base ground of the same button.
HOVER_ONLY = {
    "VIZ_GO_HOVER_DEEP": ("#00290f", "#001a0a"),
    "VIZ_STOP_HOVER_DEEP": ("#2a0018", "#1a0011"),
    "VIZ_SIM_HOVER": ("#001a18", "#0c0c1a"),
    "VIZ_GOLD_HOVER": ("#1a1400", "#0c0c1a"),
}


def _visualizer():
    """The bot visualizer module, read from `sys.modules`.

    `import src.gui.bot_visualizer as x` binds the parent package's
    attribute first. A sibling test re-imports this module under a stubbed
    registry and restores only `sys.modules`, so the plain import form can
    hand back the fallback module whose privacy helper is None.
    """
    import importlib

    return importlib.import_module("src.gui.bot_visualizer")


def _contains(image, expected_hex: str) -> bool:
    """True when a pixel in `image` is exactly `expected_hex`."""
    from PySide6.QtGui import QColor, QImage

    rgb = QColor(expected_hex)
    pattern = bytes((rgb.blue(), rgb.green(), rgb.red(), 0xFF))
    # The converted image must outlive the read: constBits() points into it.
    converted = image.convertToFormat(QImage.Format.Format_ARGB32)
    raw = bytes(converted.constBits())
    idx = raw.find(pattern)
    while idx != -1:
        if idx % 4 == 0:
            return True
        idx = raw.find(pattern, idx + 1)
    return False


@pytest.fixture(scope="module")
def renders():
    """One render per paint branch the migration touched. {name: QImage}."""
    from PySide6.QtCore import QPointF

    from src.core.privacy_mask_registry import get_privacy_mask_registry
    from tests.qt_pixel import ensure_app, render_widget

    mod = _visualizer()

    ensure_app()
    get_privacy_mask_registry().set_all(False)
    out = {}

    def emit(name, widget, size):
        out[name] = render_widget(widget, size=size)

    t1 = mod.BotVisualizationTab()
    t1.register_sim_run("s1", "SIM A", CFG)
    t1.register_paper_run("p1", "PAPER B", CFG)
    for idx, name in ((0, "live"), (1, "sim"), (2, "paper")):
        t1._tabs.setCurrentIndex(idx)
        emit(f"tab_{name}", t1, TAB)

    t2 = mod.BotVisualizationTab()
    t2._create_sim_bot_row()
    t2._create_paper_bot_row()
    t2._tabs.setCurrentIndex(1)
    emit("tab_sim_row_idle", t2, TAB)
    t2._sim_bots[0]["run_btn"].click()
    emit("tab_sim_row_running", t2, TAB)
    t2._sim_bots[0]["run_btn"].click()
    emit("tab_sim_row_stopped", t2, TAB)
    t2._tabs.setCurrentIndex(2)
    emit("tab_paper_row_idle", t2, TAB)
    t2._paper_bots[0]["start_btn"].click()
    emit("tab_paper_row_running", t2, TAB)

    t3 = mod.BotVisualizationTab()
    t3.register_sim_run("s3", "SIM C", CFG)
    t3.register_paper_run("p3", "PAPER D", CFG)
    t3.update_sim_run("s3", pnl=12.5, trades=4, candle_idx=50)
    t3.update_paper_run("p3", price=99.0, pnl=-7.5, trades=2)
    emit("tab_updated", t3, TAB)
    t3.stop_sim_run("s3", pnl=-2.0, trades=1)
    t3.stop_paper_run("p3", pnl=5.0, trades=3)
    emit("tab_stopped", t3, TAB)

    t4 = mod.BotVisualizationTab()
    t4._view_stack.setCurrentIndex(1)
    emit("tab_grid_empty", t4, TAB)

    t5 = mod.BotVisualizationTab()
    t5._on_privacy_mode_btn_clicked()
    t5._toggle_bot_swarm_identifier_mask()
    emit("tab_privacy_on", t5, TAB)

    emit("quick_routing", mod.QuickRoutingMatrix(mod.BotVisualizationTab()), QRM)

    t6 = mod.BotVisualizationTab()
    for kind in ("live", "sim", "paper", "other"):
        handle = t6._create_swarm_row(kind, f"{kind.upper()}-ROW", dict(CFG))
        emit(f"row_{kind}", handle["widget"], ROW)
    live = t6._create_swarm_row("live", "LIVE-UPD", dict(CFG))
    t6._live_bot_rows["liv-1"] = live
    t6.update_live_run("liv-1", price=100.5, pnl=3.25, trades=9, status="RUNNING")
    emit("row_live_updated", live["widget"], ROW)
    stopped = t6._create_swarm_row("live", "LIVE-STOP", dict(CFG))
    t6._live_bot_rows["liv-2"] = stopped
    t6.stop_live_run("liv-2", pnl=-1.5, trades=2)
    emit("row_live_stopped", stopped["widget"], ROW)

    t7 = mod.BotVisualizationTab()
    t7._wires = [
        {"source_id": "aaaaaaaa11", "target_id": "bbbbbbbb22", "pct": 25, "phase": 0.0},
        {"source_id": "cccccccc33", "target_id": "aaaaaaaa11", "pct": 40, "phase": 0.0},
    ]
    captured = []

    real_menu = mod.QMenu

    def _recording_menu(parent):
        """Build a real QMenu whose exec records instead of blocking."""
        menu = real_menu(parent)
        menu.exec = lambda *_a, **_k: captured.append(menu)
        return menu

    mod.QMenu = _recording_menu
    try:
        t7._show_disconnect_picker("aaaaaaaa11", QPointF(10, 10))
        t7._show_disconnect_menu(QPointF(10, 10), t7._wires[0])
    finally:
        mod.QMenu = real_menu
    assert len(captured) == 2
    emit("menu_picker", captured[0], MENU)
    emit("menu_disconnect", captured[1], MENU)
    selected = real_menu(None)
    selected.setStyleSheet(captured[0].styleSheet())
    for action in captured[0].actions():
        selected.addAction(action.text())
    selected.setActiveAction([a for a in selected.actions() if a.isEnabled()][0])
    emit("menu_selected", selected, MENU)

    real_registry = mod._get_privacy_mask_registry
    mod._get_privacy_mask_registry = None
    try:
        t8 = mod.BotVisualizationTab()
        t8._toggle_bot_swarm_identifier_mask()
        emit("tab_registry_broken", t8, TAB)
    finally:
        mod._get_privacy_mask_registry = real_registry
    return out


EXPECTED = [
    ("tab_live", "VIZ_SWARM_SURFACE"),
    ("tab_live", "VIZ_PANEL_SURFACE"),
    ("tab_live", "VIZ_PANEL_BORDER"),
    ("tab_live", "VIZ_TAB_SELECTED"),
    ("tab_live", "VIZ_TAB_TEXT"),
    ("tab_live", "PRIMARY_BRIGHT"),
    ("tab_live", "TEXT_INACTIVE"),
    ("tab_live", "CARD_METRIC_BORDER"),
    ("tab_live", "VIZ_LIST_SURFACE"),
    ("tab_live", "VIZ_LIST_BORDER"),
    ("tab_live", "VIZ_LIST_TEXT"),
    ("tab_live", "VIZ_INPUT_SURFACE"),
    ("tab_live", "VIZ_INPUT_BORDER"),
    ("tab_sim", "VIZ_HEADING"),
    ("tab_sim", "SUCCESS"),
    ("tab_sim", "ERROR"),
    ("tab_sim", "VIZ_CAPTION"),
    ("tab_paper", "ACCENT_GOLD"),
    ("tab_sim_row_idle", "VIZ_GO_HOVER"),
    ("tab_sim_row_idle", "VIZ_STOP_HOVER"),
    ("tab_sim_row_running", "VIZ_STOP_HOVER"),
    ("tab_paper_row_idle", "VIZ_GO_HOVER"),
    ("tab_paper_row_idle", "MENU_SURFACE"),
    ("tab_grid_empty", "TEXT_PLACEHOLDER"),
    ("tab_privacy_on", "VIZ_CONFIRM_SURFACE"),
    ("tab_registry_broken", "VIZ_NUCLEAR_SURFACE"),
    ("tab_registry_broken", "VIZ_NUCLEAR_BORDER"),
    ("row_live", "VIZ_LANE_LIVE"),
    ("row_sim", "VIZ_LANE_LIVE"),
    ("row_paper", "VIZ_LANE_PAPER"),
    ("row_other", "VIZ_PANEL_SURFACE"),
    ("row_live", "CARD_METRIC_LABEL"),
    ("row_live", "VIZ_CAPTION_DIM"),
    ("row_live_updated", "PRIMARY_BRIGHT"),
    ("row_live_updated", "SUCCESS"),
    ("row_live_stopped", "ERROR"),
    ("row_live_stopped", "VIZ_PANEL_BORDER"),
    ("menu_picker", "MENU_SURFACE"),
    ("menu_picker", "MENU_BORDER"),
    ("menu_picker", "TEXT_HIGH"),
    ("menu_disconnect", "MENU_BORDER"),
    ("menu_selected", "MENU_ITEM_SELECTED"),
]


@pytest.mark.parametrize("scenario,token", EXPECTED)
def test_scenario_paints_its_shipped_colour(renders, scenario, token) -> None:
    """A failure means this widget stopped painting the colour it shipped."""
    expected = SHIPPED[token]
    assert _contains(
        renders[scenario], expected
    ), f"{scenario} does not paint {expected} ({token})"


def test_every_provable_colour_reaches_a_pixel(renders) -> None:
    """A failure means a migrated colour vanished from every render."""
    missing = [
        f"{token} {value}"
        for token, value in SHIPPED.items()
        if not any(_contains(img, value) for img in renders.values())
    ]
    assert not missing, missing


def test_pnl_sign_selects_the_shipped_gain_and_loss_colours(renders) -> None:
    """A failure means the P/L row colours swapped or moved."""
    assert _contains(renders["row_live_updated"], SHIPPED["SUCCESS"])
    assert not _contains(renders["row_live_updated"], SHIPPED["ERROR"])
    assert _contains(renders["row_live_stopped"], SHIPPED["ERROR"])


def test_hover_rules_carry_their_shipped_literals() -> None:
    """A failure means a `:hover` ground changed, or its button stopped
    painting the base ground from the same stylesheet."""
    from PySide6.QtWidgets import QPushButton

    from src.core.privacy_mask_registry import get_privacy_mask_registry
    from tests.qt_pixel import ensure_app, render_widget

    mod = _visualizer()

    ensure_app()
    get_privacy_mask_registry().set_all(False)
    tab = mod.BotVisualizationTab()
    tab._create_sim_bot_row()
    tab._create_paper_bot_row()
    buttons = tab.findChildren(QPushButton)
    for token, (hover, base) in HOVER_ONLY.items():
        rule = f"QPushButton:hover{{background:{hover};}}"
        owners = [b for b in buttons if rule in b.styleSheet()]
        assert owners, f"no button carries {rule} ({token})"
        for button in owners:
            assert f"background:{base};" in button.styleSheet(), token
            image = render_widget(button, size=(160, 30))
            assert _contains(image, base), f"{token} button does not paint {base}"


# `BotNodeWidget` and `_WireCanvas` need their own render. The values are
# the `THEMES` literals written out, so a changed entry fails.
THEME_SHIPPED = {
    "QUANTUM_BG": "#0a0f19",
    "QUANTUM_ACCENT": "#00c8ff",
    "QUANTUM_ACCENT2": "#00ffc8",
    "QUANTUM_SUCCESS": "#00ff88",
    "QUANTUM_WARNING": "#ffb400",
    "QUANTUM_ERROR": "#ff3250",
    "QUANTUM_TEXT": "#b4dcff",
    "NEBULA_BG": "#080414",
    "NEBULA_ACCENT": "#7850ff",
    "MATRIX_BG": "#000800",
    "MATRIX_ACCENT": "#00ff41",
    "OCEAN_BG": "#050a1e",
    "OCEAN_ACCENT": "#0096ff",
    "IDLE_GREY": "#646464",
    "STOPPED_GREY": "#505050",
}

NODE = (112, 98)
CANVAS = (900, 600)

SWARM = [
    {
        "symbol": f"SYM{i}-USD",
        "bot_id": f"botid{i:04d}",
        "state": "running" if i % 2 else "paused",
        "mode": "scrumming",
        "stats": {
            "realised_pnl": 10.0 * i - 15,
            "total_trades": i,
            "current_price": 100.0 + i,
            "trade_volume": 1000.0 * i,
        },
    }
    for i in range(6)
]


def _node_data(state, pnl):
    return {
        "symbol": "BTC-USD",
        "bot_id": "abcdef123456",
        "state": state,
        "mode": "scrumming",
        "stats": {
            "realised_pnl": pnl,
            "total_trades": 7,
            "current_price": 68000.0,
            "trade_volume": 12345.0,
        },
    }


def _contains_rgb(image, expected_hex: str) -> bool:
    """True when a pixel in `image` carries `expected_hex` at any alpha.

    `_contains` requires alpha 0xFF. The wire overlay is a transparent
    widget, so most of what it paints never reaches full opacity.
    """
    from PySide6.QtGui import QColor, QImage

    want = QColor(expected_hex).rgb() & 0xFFFFFF
    converted = image.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(converted.height()):
        for x in range(converted.width()):
            if converted.pixel(x, y) & 0xFFFFFF == want:
                return True
    return False


def _steady(node):
    """Pin the draws the widget seeds from system entropy and from elapsed
    time, so one render is reproducible."""
    node._phase = 0.7
    node._particles = []
    node._trade_pulses = []
    node._antenna_drive = 0.0
    return node


@pytest.fixture(scope="module")
def widget_renders():
    """One render per paint branch inside the extracted widget modules."""
    from PySide6.QtCore import QPointF

    from src.core.privacy_mask_registry import get_privacy_mask_registry
    from tests.qt_pixel import ensure_app, render_widget

    mod = _visualizer()

    ensure_app()
    get_privacy_mask_registry().set_all(False)
    out = {}

    for state, pnl in (
        ("running", 250.0),
        ("idle", 0.0),
        ("paused", -12.5),
        ("error", -9999.0),
        ("stopped", 3.0),
        ("cooldown", 0.25),
    ):
        node = _steady(mod.BotNodeWidget())
        node.set_bot_data(_node_data(state, pnl))
        out[f"node_{state}"] = render_widget(_steady(node), size=NODE)

    for theme in ("nebula", "matrix", "ocean"):
        node = _steady(mod.BotNodeWidget())
        node.set_theme(theme)
        node.set_bot_data(_node_data("running", 42.0))
        out[f"node_theme_{theme}"] = render_widget(_steady(node), size=NODE)

    out["node_no_data"] = render_widget(mod.BotNodeWidget(), size=NODE)

    tab = mod.BotVisualizationTab()
    tab._anim_timer.stop()
    tab.resize(1400, 900)
    tab._view_stack.setCurrentIndex(1)
    tab.update_bots(SWARM)
    for widget in tab._bot_widgets.values():
        _steady(widget)
    wires = [
        {"source_id": "botid0000", "target_id": "botid0001", "pct": 25, "phase": 0.0},
        {"source_id": "botid0001", "target_id": "botid0000", "pct": 40, "phase": 1.2},
        {"source_id": "botid0002", "target_id": "botid0005", "pct": 100, "phase": 2.4},
    ]
    tab._wires = list(wires)
    out["wire_wires"] = render_widget(tab._wire_canvas, size=CANVAS)
    tab._wires = []
    out["wire_none"] = render_widget(tab._wire_canvas, size=CANVAS)
    tab._wires = list(wires)

    tab._dragging_wire = True
    tab._wire_start_id = "botid0000"
    tab._wire_mouse_pos = QPointF(500.0, 400.0)
    out["wire_drag_free"] = render_widget(tab._wire_canvas, size=CANVAS)
    tab._wire_mouse_pos = tab._get_bot_center("botid0003")
    out["wire_drag_connect"] = render_widget(tab._wire_canvas, size=CANVAS)
    tab._dragging_wire = False
    tab._wire_mouse_pos = None
    tab._wire_start_id = None

    for theme in ("nebula", "matrix", "ocean"):
        tab._theme_key = theme
        out[f"wire_theme_{theme}"] = render_widget(tab._wire_canvas, size=CANVAS)
    tab._theme_key = "quantum"

    return out


NODE_EXPECTED = [
    ("node_running", "QUANTUM_BG"),
    ("node_running", "QUANTUM_SUCCESS"),
    ("node_running", "QUANTUM_TEXT"),
    ("node_idle", "IDLE_GREY"),
    ("node_idle", "STOPPED_GREY"),
    ("node_paused", "QUANTUM_WARNING"),
    ("node_paused", "QUANTUM_ERROR"),
    ("node_error", "QUANTUM_ERROR"),
    ("node_stopped", "STOPPED_GREY"),
    ("node_cooldown", "QUANTUM_WARNING"),
    ("node_theme_nebula", "NEBULA_BG"),
    ("node_theme_matrix", "MATRIX_BG"),
    ("node_theme_ocean", "OCEAN_BG"),
]

WIRE_EXPECTED = [
    ("wire_wires", "QUANTUM_ACCENT"),
    ("wire_wires", "QUANTUM_ACCENT2"),
    ("wire_drag_free", "QUANTUM_WARNING"),
    ("wire_drag_connect", "QUANTUM_SUCCESS"),
    ("wire_theme_nebula", "NEBULA_ACCENT"),
    ("wire_theme_matrix", "MATRIX_ACCENT"),
    ("wire_theme_ocean", "OCEAN_ACCENT"),
]


@pytest.mark.parametrize("scenario,token", NODE_EXPECTED)
def test_bot_node_paints_its_shipped_colour(widget_renders, scenario, token):
    """A failure means the bot node stopped painting the colour it shipped,
    or stopped being reached at all."""
    expected = THEME_SHIPPED[token]
    assert _contains(
        widget_renders[scenario], expected
    ), f"{scenario} does not paint {expected} ({token})"


@pytest.mark.parametrize("scenario,token", WIRE_EXPECTED)
def test_wire_canvas_paints_its_shipped_colour(widget_renders, scenario, token):
    """A failure means the wire overlay stopped painting the colour it
    shipped, or stopped being reached at all."""
    expected = THEME_SHIPPED[token]
    assert _contains_rgb(
        widget_renders[scenario], expected
    ), f"{scenario} does not paint {expected} ({token})"


def test_an_unfed_bot_node_paints_none_of_them(widget_renders):
    """CONTROL. `paintEvent` returns before the first draw with no bot data,
    so a checker that reports a hit here cannot tell painted from unpainted."""
    hits = [
        token
        for token, value in THEME_SHIPPED.items()
        if _contains(widget_renders["node_no_data"], value)
    ]
    assert not hits, hits


def test_a_wireless_canvas_paints_none_of_them(widget_renders):
    """CONTROL for the alpha-blind checker. `paintEvent` returns before the
    first draw with no wires, so a hit here means `_contains_rgb` reports a
    colour the overlay never painted."""
    hits = [
        token
        for token, value in THEME_SHIPPED.items()
        if _contains_rgb(widget_renders["wire_none"], value)
    ]
    assert not hits, hits
