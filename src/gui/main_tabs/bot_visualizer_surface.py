"""bot_visualizer_surface.py -- the Bot Swarm tab and its three layers.

Describes everything the Bot Swarm screen works out before it draws: the
three swarm layers (live, simulator, paper) and the identical row each
one builds, the locust grid and the message shown when no bot is
running, the wires between bots and where they sit, the routes those
wires are saved as, the Exchange filter, the privacy glyphs, and the
words every menu and confirmation puts on screen.

``SwarmLayer`` holds one layer's rows and the summary line under them.
``WireBoard`` holds the wires, adds and drops them, and answers which
wire a click landed on. ``FleetGrid`` places each bot in the grid and
decides when the empty message shows. The route helpers turn a stored
fleet load into the wires the canvas paints, and back again.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_visualizer.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.bot_visualizer``, so a value changed on one side alone is
reported. Nothing here imports Qt, reads a file or reads the clock.
"""

from __future__ import annotations

import math
from typing import Any, Optional

METHOD = "bot_visualizer.state"

LOGGER_NAME = "acervator.gui.bot_visualizer"

MASK_FIELD_ID = "bot_swarm.identifiers"
MASK_TEXT = "****"

SUCCESS_COLOR = "#00ff88"
ERROR_COLOR = "#ff3366"
ACCENT_GOLD_COLOR = "#ffd700"
PRIMARY_BRIGHT_COLOR = "#00ffee"
TEXT_INACTIVE_COLOR = "#aaaaaa"
TEXT_HIGH_COLOR = "#e0e0f0"
TEXT_PLACEHOLDER_COLOR = "#555555"
CARD_METRIC_LABEL_COLOR = "#888"
CARD_METRIC_BORDER_COLOR = "#2a2a3f"
MENU_SURFACE_COLOR = "#1a1a2f"
MENU_BORDER_COLOR = "#3a3a5f"
MENU_ITEM_SELECTED_COLOR = "#2a2a4f"
VIZ_PANEL_BORDER_COLOR = "#1a1a3f"
VIZ_PANEL_SURFACE_COLOR = "#0c0c1a"
VIZ_SWARM_SURFACE_COLOR = "#070710"
VIZ_TAB_TEXT_COLOR = "#666677"
VIZ_TAB_SELECTED_COLOR = "#0a0a20"
VIZ_LANE_LIVE_COLOR = "#091a0e"
VIZ_LANE_PAPER_COLOR = "#0e0e09"
VIZ_CAPTION_COLOR = "#445566"
VIZ_CAPTION_DIM_COLOR = "#556677"
VIZ_HEADING_COLOR = "#c8d8f0"
VIZ_NUCLEAR_SURFACE_COLOR = "#ff0000"
VIZ_NUCLEAR_BORDER_COLOR = "#cc0000"
VIZ_CONFIRM_SURFACE_COLOR = "#003822"
VIZ_GO_HOVER_COLOR = "#001a0a"
VIZ_GO_HOVER_DEEP_COLOR = "#00290f"
VIZ_STOP_HOVER_COLOR = "#1a0011"
VIZ_STOP_HOVER_DEEP_COLOR = "#2a0018"
VIZ_SIM_HOVER_COLOR = "#001a18"
VIZ_GOLD_HOVER_COLOR = "#1a1400"

WARNING_LEVEL = "WARNING"
INFO_LEVEL = "INFO"

COLORS = {
    "success": SUCCESS_COLOR,
    "error": ERROR_COLOR,
    "accent_gold": ACCENT_GOLD_COLOR,
    "primary_bright": PRIMARY_BRIGHT_COLOR,
    "text_inactive": TEXT_INACTIVE_COLOR,
    "text_high": TEXT_HIGH_COLOR,
    "text_placeholder": TEXT_PLACEHOLDER_COLOR,
    "card_metric_label": CARD_METRIC_LABEL_COLOR,
    "card_metric_border": CARD_METRIC_BORDER_COLOR,
    "menu_surface": MENU_SURFACE_COLOR,
    "menu_border": MENU_BORDER_COLOR,
    "menu_item_selected": MENU_ITEM_SELECTED_COLOR,
    "panel_border": VIZ_PANEL_BORDER_COLOR,
    "panel_surface": VIZ_PANEL_SURFACE_COLOR,
    "swarm_surface": VIZ_SWARM_SURFACE_COLOR,
    "tab_text": VIZ_TAB_TEXT_COLOR,
    "tab_selected": VIZ_TAB_SELECTED_COLOR,
    "lane_live": VIZ_LANE_LIVE_COLOR,
    "lane_paper": VIZ_LANE_PAPER_COLOR,
    "caption": VIZ_CAPTION_COLOR,
    "caption_dim": VIZ_CAPTION_DIM_COLOR,
    "heading": VIZ_HEADING_COLOR,
    "nuclear_surface": VIZ_NUCLEAR_SURFACE_COLOR,
    "nuclear_border": VIZ_NUCLEAR_BORDER_COLOR,
    "confirm_surface": VIZ_CONFIRM_SURFACE_COLOR,
    "go_hover": VIZ_GO_HOVER_COLOR,
    "go_hover_deep": VIZ_GO_HOVER_DEEP_COLOR,
    "stop_hover": VIZ_STOP_HOVER_COLOR,
    "stop_hover_deep": VIZ_STOP_HOVER_DEEP_COLOR,
    "sim_hover": VIZ_SIM_HOVER_COLOR,
    "gold_hover": VIZ_GOLD_HOVER_COLOR,
}

TAB_KIND = "QTabWidget"
ROW_KIND = "QFrame"
LABEL_KIND = "QLabel"
BUTTON_KIND = "QPushButton"

TAB_STYLE_SHEET = (
    f"QTabWidget::pane{{border:1px solid {VIZ_PANEL_BORDER_COLOR};"
    f"background:{VIZ_SWARM_SURFACE_COLOR};}}"
    f"QTabBar::tab{{background:{VIZ_PANEL_SURFACE_COLOR};"
    f"color:{VIZ_TAB_TEXT_COLOR};border:1px solid {VIZ_PANEL_BORDER_COLOR};"
    "padding:4px 12px;font-size:9px;}"
    f"QTabBar::tab:selected{{background:{VIZ_TAB_SELECTED_COLOR};"
    f"color:{PRIMARY_BRIGHT_COLOR};"
    f"border-bottom:2px solid {PRIMARY_BRIGHT_COLOR};}}"
    f"QTabBar::tab:hover{{color:{TEXT_INACTIVE_COLOR};}}"
)

TAB_TITLES = ("⚡ Bot Swarm", "\U0001f5a5 Simulator Swarm", "\U0001f4c4 Paper Swarm")
SWARM_TAB_INDEX = 0
SIM_TAB_INDEX = 1
PAPER_TAB_INDEX = 2

HEADER_TITLE = "Bot Swarm"
HEADER_HINT = "   Drag between bots to connect  •  Right-click wire to disconnect"

# The unified swarm row

LIVE_KIND = "live"
SIM_KIND = "sim"
PAPER_KIND = "paper"
ROW_KINDS = (LIVE_KIND, SIM_KIND, PAPER_KIND)
FALLBACK_KIND = SIM_KIND

SWARM_ACCENTS: dict[str, tuple[str, str, str]] = {
    LIVE_KIND: (SUCCESS_COLOR, SUCCESS_COLOR, SUCCESS_COLOR),
    SIM_KIND: (SUCCESS_COLOR, PRIMARY_BRIGHT_COLOR, SUCCESS_COLOR),
    PAPER_KIND: (ACCENT_GOLD_COLOR, ACCENT_GOLD_COLOR, ACCENT_GOLD_COLOR),
}

SWARM_TINTS: dict[str, str] = {
    LIVE_KIND: VIZ_LANE_LIVE_COLOR,
    SIM_KIND: VIZ_LANE_LIVE_COLOR,
    PAPER_KIND: VIZ_LANE_PAPER_COLOR,
}
FALLBACK_TINT = VIZ_PANEL_SURFACE_COLOR

ROW_MARGINS = (8, 4, 8, 4)
ROW_SPACING = 6
ROW_RADIUS_PX = 4

DOT_WIDTH_PX = 12
ID_WIDTH_PX = 80
CONTEXT_WIDTH_PX = 88
MODE_WIDTH_PX = 72
FEED_WIDTH_PX = 60
CAPITAL_WIDTH_PX = 58
STATUS_WIDTH_PX = 60
METRIC_WIDTH_PX = 58
PNL_WIDTH_PX = 88
TRADES_WIDTH_PX = 68

DOT_TEXT = "●"
MISSING_TEXT = "—"
PNL_PLACEHOLDER_TEXT = "PnL —"
TRADES_PLACEHOLDER_TEXT = "0 trades"

STATUS_RUNNING = "RUNNING"
STATUS_STOPPED = "STOPPED"
STATUS_DONE = "DONE"
STATUS_LIVE = "LIVE"
STATUS_IDLE = "IDLE"

CAPITAL_TEXT_FORMAT = "${capital:,.0f}"
PNL_TEXT_FORMAT = "PnL {pnl:+,.2f}"
TRADES_TEXT_FORMAT = "{trades} trades"
PROGRESS_TEXT_FORMAT = "{pct}%"
PRICE_SMALL_FORMAT = "${price:,.4f}"
PRICE_LARGE_FORMAT = "${price:,.2f}"
PRICE_FORMAT_LIMIT = 1000

PROGRESS_MIN_TOTAL = 1
PROGRESS_MAX_PCT = 100
PROGRESS_SCALE = 100
PROGRESS_DONE_TEXT = "100%"
PROGRESS_START_TEXT = "0%"

DEFAULT_CAPITAL = 0
DEFAULT_CANDLE_TOTAL = 0
SIM_CANDLE_TOTAL = 1
DEFAULT_PNL = 0

ROW_HANDLE_KEYS = (
    "kind",
    "widget",
    "dot",
    "id_lbl",
    "context_lbl",
    "mode_lbl",
    "feed_lbl",
    "cap_lbl",
    "status_lbl",
    "metric_lbl",
    "pnl_lbl",
    "trades_lbl",
    "_accent",
    "running",
    "total_candles",
)

CONTEXT_CFG_KEYS = ("context", "pair", "asset")
FEED_CFG_KEYS = ("feed", "timeframe", "source")


def row_style_sheet(tint: str, border: str) -> str:
    """The frame rule one swarm row is painted with."""
    return (
        f"QFrame{{background:{tint};border:1px solid {border};"
        f"border-radius:{ROW_RADIUS_PX}px;}}"
    )


def dot_style_sheet(color: str) -> str:
    """The rule the live dot at the left of a row is painted with."""
    return f"color:{color};font-size:10px;font-weight:bold;background:transparent;"


def id_style_sheet(color: str) -> str:
    """The rule the row's identifier is painted with."""
    return (
        f"color:{color};font-size:9px;font-weight:bold;"
        f"font-family:Consolas;background:transparent;"
    )


def context_style_sheet() -> str:
    """The rule the asset column is painted with."""
    return (
        f"color:{PRIMARY_BRIGHT_COLOR};font-size:9px;font-weight:bold;"
        "font-family:Consolas;background:transparent;"
    )


def small_style_sheet(color: str) -> str:
    """The rule every eight-point column in a row is painted with."""
    return f"color:{color};font-size:8px;font-family:Consolas;background:transparent;"


def bold_small_style_sheet(color: str) -> str:
    """The rule the status column is painted with."""
    return (
        f"color:{color};font-size:8px;font-family:Consolas;"
        f"font-weight:bold;background:transparent;"
    )


def stopped_row_style_sheet() -> str:
    """The frame rule a stopped row is repainted with."""
    return (
        f"QFrame{{background:{VIZ_PANEL_SURFACE_COLOR};"
        f"border:1px solid {VIZ_PANEL_BORDER_COLOR};"
        f"border-radius:{ROW_RADIUS_PX}px;}}"
    )


def stopped_status_style_sheet() -> str:
    """The rule the status column is repainted with when a row stops."""
    return (
        f"color:{VIZ_CAPTION_COLOR};font-size:8px;font-family:Consolas;"
        "font-weight:bold;background:transparent;"
    )


def accents_for(kind: str) -> tuple[str, str, str]:
    """The border, label and dot colours one layer's rows carry.

    A layer name the screen does not know takes the simulator colours.
    """
    return SWARM_ACCENTS.get(kind, SWARM_ACCENTS[FALLBACK_KIND])


def tint_for(kind: str) -> str:
    """The background one layer's rows carry."""
    return SWARM_TINTS.get(kind, FALLBACK_TINT)


def first_present(cfg: dict, keys: tuple, fallback: str) -> Any:
    """The first of `keys` the run carries, else `fallback`.

    A key present and holding nothing is carried as it is; only a key
    that is absent falls through to the next.
    """
    for key in keys:
        if key in cfg:
            return cfg[key]
    return fallback


def capital_text(capital: Any) -> str:
    """One layer's starting money as the capital column writes it."""
    return CAPITAL_TEXT_FORMAT.format(capital=capital)


def pnl_text(pnl: Any) -> str:
    """One run's profit as the PnL column writes it."""
    return PNL_TEXT_FORMAT.format(pnl=pnl)


def pnl_color(pnl: Any) -> str:
    """The colour a profit is written in.

    Nothing lost is green and anything else red. A profit that is not a
    number is red, because every comparison against it is false.
    """
    return SUCCESS_COLOR if pnl >= 0 else ERROR_COLOR


def trades_text(trades: Any) -> str:
    """One run's trade count as the trades column writes it."""
    return TRADES_TEXT_FORMAT.format(trades=trades)


def progress_pct(candle_idx: Any, total_candles: Any) -> int:
    """How far a bounded simulator run has got, as a whole percentage.

    A total below one is lifted to one, so a run with no candles reads
    as finished rather than dividing by nothing. The share is cut off at
    a hundred.
    """
    total = max(PROGRESS_MIN_TOTAL, total_candles)
    return min(PROGRESS_MAX_PCT, int(candle_idx / total * PROGRESS_SCALE))


def progress_text(candle_idx: Any, total_candles: Any) -> str:
    """One simulator run's progress as the metric column writes it."""
    return PROGRESS_TEXT_FORMAT.format(pct=progress_pct(candle_idx, total_candles))


def price_text(price: Any) -> str:
    """One price as the metric column writes it.

    Under a thousand takes four decimal places and anything else two. A
    price that is not a number takes the two-place form, because the
    comparison against it is false.
    """
    if price < PRICE_FORMAT_LIMIT:
        return PRICE_SMALL_FORMAT.format(price=price)
    return PRICE_LARGE_FORMAT.format(price=price)


def price_style_sheet() -> str:
    """The rule the metric column is repainted with once it shows a price."""
    return small_style_sheet(PRIMARY_BRIGHT_COLOR)


def swarm_row(kind: str, label: str, cfg: dict) -> dict:
    """One swarm row: the same ten columns whatever layer built it.

    The handle carries the same key set for every layer, which is what
    lets one update path serve all three.
    """
    border, label_color, dot_color = accents_for(kind)
    tint = tint_for(kind)
    return {
        "kind": kind,
        "widget": {
            "kind": ROW_KIND,
            "style_sheet": row_style_sheet(tint, border),
            "margins": list(ROW_MARGINS),
            "spacing": ROW_SPACING,
        },
        "dot": column(DOT_TEXT, DOT_WIDTH_PX, dot_style_sheet(dot_color)),
        "id_lbl": column(label, ID_WIDTH_PX, id_style_sheet(label_color)),
        "context_lbl": column(
            first_present(cfg, CONTEXT_CFG_KEYS, MISSING_TEXT),
            CONTEXT_WIDTH_PX,
            context_style_sheet(),
        ),
        "mode_lbl": column(
            cfg.get("mode", MISSING_TEXT),
            MODE_WIDTH_PX,
            small_style_sheet(CARD_METRIC_LABEL_COLOR),
        ),
        "feed_lbl": column(
            first_present(cfg, FEED_CFG_KEYS, MISSING_TEXT),
            FEED_WIDTH_PX,
            small_style_sheet(VIZ_CAPTION_DIM_COLOR),
        ),
        "cap_lbl": column(
            capital_text(cfg.get("capital", DEFAULT_CAPITAL)),
            CAPITAL_WIDTH_PX,
            small_style_sheet(VIZ_CAPTION_DIM_COLOR),
        ),
        "status_lbl": column(
            cfg.get("status", STATUS_RUNNING),
            STATUS_WIDTH_PX,
            bold_small_style_sheet(label_color),
        ),
        "metric_lbl": column(
            cfg.get("metric_init", MISSING_TEXT),
            METRIC_WIDTH_PX,
            small_style_sheet(VIZ_CAPTION_COLOR),
        ),
        "pnl_lbl": column(
            PNL_PLACEHOLDER_TEXT, PNL_WIDTH_PX, small_style_sheet(VIZ_CAPTION_COLOR)
        ),
        "trades_lbl": column(
            TRADES_PLACEHOLDER_TEXT,
            TRADES_WIDTH_PX,
            small_style_sheet(VIZ_CAPTION_COLOR),
        ),
        "_accent": label_color,
        "running": True,
        "total_candles": cfg.get("candle_total", DEFAULT_CANDLE_TOTAL),
    }


def column(text: Any, width: int, style_sheet: str) -> dict:
    """One column of a swarm row: its text, its width and its paint rule."""
    return {
        "kind": LABEL_KIND,
        "text": text,
        "width": width,
        "style_sheet": style_sheet,
    }


def apply_stopped_style(handle: dict) -> dict:
    """Repaint one row in the stopped colours and mark it not running."""
    handle["running"] = False
    handle["dot"]["style_sheet"] = dot_style_sheet(VIZ_CAPTION_COLOR)
    handle["widget"]["style_sheet"] = stopped_row_style_sheet()
    handle["status_lbl"]["style_sheet"] = stopped_status_style_sheet()
    return handle


def apply_pnl(handle: dict, pnl: Any) -> dict:
    """Write one profit into a row, in the colour that profit earns."""
    handle["pnl_lbl"]["text"] = pnl_text(pnl)
    handle["pnl_lbl"]["style_sheet"] = small_style_sheet(pnl_color(pnl))
    return handle


# What each layer's caller hands the row factory

SIM_MODE = "SIM"
PAPER_MODE = "PAPER"
LIVE_MODE = "LIVE"


def sim_cfg(label: str, cfg: dict) -> dict:
    """One simulator run's settings in the shape every row is built from."""
    return {
        "context": cfg.get("asset", cfg.get("label", label)),
        "mode": cfg.get("mode", SIM_MODE),
        "feed": cfg.get("timeframe", MISSING_TEXT),
        "capital": cfg.get("capital", DEFAULT_CAPITAL),
        "status": STATUS_RUNNING,
        "metric_init": PROGRESS_START_TEXT,
        "candle_total": cfg.get("candle_total", SIM_CANDLE_TOTAL),
    }


def paper_cfg(cfg: dict) -> dict:
    """One paper run's settings in the shape every row is built from."""
    return {
        "context": cfg.get("pair", MISSING_TEXT),
        "mode": cfg.get("mode", PAPER_MODE),
        "feed": cfg.get("source", MISSING_TEXT),
        "capital": cfg.get("capital", DEFAULT_CAPITAL),
        "status": STATUS_LIVE,
        "metric_init": MISSING_TEXT,
    }


def live_cfg(cfg: dict) -> dict:
    """One live bot's settings in the shape every row is built from."""
    return {
        "context": cfg.get("pair", cfg.get("asset", MISSING_TEXT)),
        "mode": cfg.get("mode", LIVE_MODE),
        "feed": cfg.get("timeframe", cfg.get("source", MISSING_TEXT)),
        "capital": cfg.get("capital", DEFAULT_CAPITAL),
        "status": STATUS_RUNNING,
        "metric_init": cfg.get("metric_init", MISSING_TEXT),
    }


LAYER_CFG_BUILDERS = {SIM_KIND: sim_cfg, PAPER_KIND: paper_cfg, LIVE_KIND: live_cfg}
LAYER_ID_KEYS = {SIM_KIND: "sim_id", PAPER_KIND: "paper_id", LIVE_KIND: "bot_id"}
LAYER_STOP_STATUS = {
    SIM_KIND: STATUS_DONE,
    PAPER_KIND: STATUS_STOPPED,
    LIVE_KIND: STATUS_STOPPED,
}

SIM_REGISTERED_SIGNAL = "swarm.11.001.postcondition.sim_run_registered"
PAPER_REGISTERED_SIGNAL = "swarm.11.002.postcondition.paper_run_registered"
REGISTERED_SIGNALS = {
    SIM_KIND: SIM_REGISTERED_SIGNAL,
    PAPER_KIND: PAPER_REGISTERED_SIGNAL,
}


class SwarmLayer:
    """One swarm layer: the rows it holds, keyed by run.

    `on_change` is called after every register, update and stop that
    found its row, and nowhere else. The summary under the rows is
    rewritten there, so a summary shows the last event and not the
    moment it was read.
    """

    def __init__(self, kind: str, on_change=None) -> None:
        self.kind = kind
        self.rows: dict[str, dict] = {}
        self.order: list[str] = []
        self.signals: list[dict] = []
        self.on_change = on_change

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def register(self, run_id: str, label: str, cfg: dict) -> dict:
        """Build one row for a run, replacing any row that run already had."""
        self.remove(run_id)
        builder = LAYER_CFG_BUILDERS[self.kind]
        built = builder(label, cfg) if self.kind == SIM_KIND else builder(cfg)
        handle = swarm_row(self.kind, label, built)
        handle[LAYER_ID_KEYS[self.kind]] = run_id
        self.rows[run_id] = handle
        self.order.append(run_id)
        topic = REGISTERED_SIGNALS.get(self.kind)
        if topic is not None:
            self.signals.append(
                {
                    "topic": topic,
                    "actual": (self.rows.get(run_id) or {}).get("kind"),
                    "expected": self.kind,
                    "layer": self.kind,
                    "id": str(run_id),
                    "rows_in_layer": len(self.rows),
                }
            )
        self._changed()
        return handle

    def update(
        self,
        run_id: str,
        pnl: Any = DEFAULT_PNL,
        trades: Any = 0,
        candle_idx: Any = 0,
        price: Optional[Any] = None,
        status: Optional[str] = None,
    ) -> Optional[dict]:
        """Write one tick into a run's row. A run with no row is ignored."""
        handle = self.rows.get(run_id)
        if handle is None:
            return None
        if status is not None:
            handle["status_lbl"]["text"] = status
        if self.kind == SIM_KIND:
            handle["metric_lbl"]["text"] = progress_text(
                candle_idx, handle.get("total_candles", SIM_CANDLE_TOTAL)
            )
        elif price is not None and (self.kind == PAPER_KIND or price > 0):
            handle["metric_lbl"]["text"] = price_text(price)
            handle["metric_lbl"]["style_sheet"] = price_style_sheet()
        apply_pnl(handle, pnl)
        handle["trades_lbl"]["text"] = trades_text(trades)
        handle["_pnl"] = pnl
        self._changed()
        return handle

    def stop(
        self, run_id: str, pnl: Any = DEFAULT_PNL, trades: Any = 0
    ) -> Optional[dict]:
        """Mark one run finished. A run with no row is ignored."""
        handle = self.rows.get(run_id)
        if handle is None:
            return None
        apply_stopped_style(handle)
        handle["status_lbl"]["text"] = LAYER_STOP_STATUS[self.kind]
        apply_pnl(handle, pnl)
        handle["trades_lbl"]["text"] = trades_text(trades)
        if self.kind == SIM_KIND:
            handle["metric_lbl"]["text"] = PROGRESS_DONE_TEXT
        self._changed()
        return handle

    def remove(self, run_id: str) -> bool:
        """Drop one run's row. True when a row was there to drop."""
        if run_id not in self.rows:
            return False
        del self.rows[run_id]
        self.order = [one for one in self.order if one != run_id]
        return True

    def running_count(self) -> int:
        """How many of this layer's rows are still running."""
        return sum(1 for one in self.rows.values() if one.get("running"))

    def pnls(self) -> list:
        """Every profit this layer's rows carry, in the order they were built."""
        return [self.rows[one].get("_pnl", DEFAULT_PNL) for one in self.order]


SIM_SUMMARY_RUNNING_FORMAT = "Bots: {running}/{total} running"
SIM_SUMMARY_PNL_FORMAT = "Total PnL: ${total:+,.2f}"
SIM_SUMMARY_PNL_EMPTY = "Total PnL: —"
SIM_SUMMARY_TRADES = "Aggregate trades: —"
PAPER_SUMMARY_ACTIVE_FORMAT = "Active: {running}/{total}"
PAPER_SUMMARY_CAPITAL_FORMAT = "Total Capital: ${capital:,.0f}"
PAPER_SUMMARY_PNL = "Net PnL: —"

SIM_SUMMARY_TITLE = "SWARM SUMMARY"
PAPER_SUMMARY_TITLE = "PORTFOLIO SUMMARY"
SIM_SUMMARY_WINS_START = "Wins: —"
SIM_SUMMARY_TRADES_START = "Trades: —"
PAPER_SUMMARY_CAPITAL_START = "Total Capital: —"
PAPER_SUMMARY_ACTIVE_START = "Active Bots: 0"

SIM_SUMMARY_START = {
    "wins": SIM_SUMMARY_WINS_START,
    "pnl": SIM_SUMMARY_PNL_EMPTY,
    "trades": SIM_SUMMARY_TRADES_START,
}
PAPER_SUMMARY_START = {
    "active": PAPER_SUMMARY_ACTIVE_START,
    "total": PAPER_SUMMARY_CAPITAL_START,
    "pnl": PAPER_SUMMARY_PNL,
}


def sim_summary(bench_running: int, bench_total: int, layer: SwarmLayer) -> dict:
    """The three lines under the Simulator Swarm rows.

    `bench_running` and `bench_total` are the bench rows the operator
    added by hand; the layer holds the runs the simulator started.
    """
    running = bench_running + layer.running_count()
    total = bench_total + len(layer.rows)
    found = layer.pnls()
    return {
        "wins": SIM_SUMMARY_RUNNING_FORMAT.format(running=running, total=total),
        "pnl": (
            SIM_SUMMARY_PNL_FORMAT.format(total=sum(found))
            if found
            else SIM_SUMMARY_PNL_EMPTY
        ),
        "trades": SIM_SUMMARY_TRADES,
    }


def paper_summary(bench_running: int, bench_total: int, bench_capital: Any) -> dict:
    """The three lines under the Paper Swarm rows.

    Only the bench rows the operator added reach this summary; the runs
    the paper trader started are counted nowhere in it.
    """
    return {
        "active": PAPER_SUMMARY_ACTIVE_FORMAT.format(
            running=bench_running, total=bench_total
        ),
        "total": PAPER_SUMMARY_CAPITAL_FORMAT.format(capital=bench_capital),
        "pnl": PAPER_SUMMARY_PNL,
    }


# The bench rows the operator adds by hand

SIM_BENCH_ID_FORMAT = "SIM-{idx:02d}"
PAPER_BENCH_ID_FORMAT = "PAP-{idx:02d}"

SIM_BENCH_ASSETS = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "BNB/USDT",
    "ADA/USDT",
    "DOGE/USDT",
)
SIM_BENCH_PRESETS = (
    "btc_bull",
    "btc_range",
    "eth_volatile",
    "dust_coin_pump",
    "dust_coin_sideways",
    "high_volatility",
    "crash_recovery",
)
PAPER_BENCH_PAIRS = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "SPY",
    "QQQ",
    "GLD",
    "AAPL",
    "NVDA",
)
PAPER_BENCH_SOURCES = ("CoinGecko", "Kraken", "Yahoo")

CAPITAL_MIN = 10
CAPITAL_MAX = 999999
CAPITAL_START = 400
CAPITAL_PREFIX = "$"

RUN_BUTTON_TEXT = "▶ Run"
STOP_BUTTON_TEXT = "■ Stop"
START_BUTTON_TEXT = "▶ Start"
REMOVE_BUTTON_TEXT = "✕"

BENCH_ID_WIDTH_PX = 48
BENCH_ASSET_WIDTH_PX = 110
BENCH_PRESET_WIDTH_PX = 120
BENCH_CAPITAL_WIDTH_PX = 80
BENCH_SIM_STATUS_WIDTH_PX = 90
BENCH_PAPER_STATUS_WIDTH_PX = 56
BENCH_PNL_WIDTH_PX = 80
BENCH_PRICE_WIDTH_PX = 72
BENCH_SOURCE_WIDTH_PX = 88
BENCH_RUN_BUTTON_SIZE = (58, 22)
BENCH_START_BUTTON_SIZE = (62, 22)
BENCH_REMOVE_BUTTON_SIZE = (22, 22)

BENCH_PNL_PLACEHOLDER = "PnL: —"


def bench_id_text(kind: str, idx: int) -> str:
    """The badge one hand-added bench row carries."""
    if kind == PAPER_KIND:
        return PAPER_BENCH_ID_FORMAT.format(idx=idx)
    return SIM_BENCH_ID_FORMAT.format(idx=idx)


def go_button_style_sheet() -> str:
    """The rule a Run or Start button is painted with."""
    return (
        f"QPushButton{{background:{VIZ_GO_HOVER_COLOR};color:{SUCCESS_COLOR};"
        f"border:1px solid {SUCCESS_COLOR};"
        "border-radius:3px;font-size:9px;font-weight:bold;}"
        f"QPushButton:hover{{background:{VIZ_GO_HOVER_DEEP_COLOR};}}"
    )


def stop_button_style_sheet() -> str:
    """The rule a Stop button is painted with."""
    return (
        f"QPushButton{{background:{VIZ_STOP_HOVER_COLOR};color:{ERROR_COLOR};"
        f"border:1px solid {ERROR_COLOR};"
        "border-radius:3px;font-size:9px;font-weight:bold;}"
        f"QPushButton:hover{{background:{VIZ_STOP_HOVER_DEEP_COLOR};}}"
    )


def remove_button_style_sheet() -> str:
    """The rule the cross that drops a bench row is painted with."""
    return (
        f"QPushButton{{background:{VIZ_STOP_HOVER_COLOR};color:{ERROR_COLOR};"
        f"border:1px solid {ERROR_COLOR};"
        "border-radius:3px;font-size:9px;}"
        f"QPushButton:hover{{background:{VIZ_STOP_HOVER_DEEP_COLOR};}}"
    )


def bench_status_style_sheet(color: str) -> str:
    """The rule a bench row's status is painted with."""
    return f"color:{color};font-size:8px;font-family:Consolas;font-weight:bold;"


def bench_toggled(kind: str, running: bool) -> dict:
    """What a bench row's button and status read after one click.

    `running` is the state BEFORE the click, so a running row stops.
    """
    if running:
        return {
            "running": False,
            "button_text": _idle_button_text(kind),
            "button_style_sheet": go_button_style_sheet(),
            "status_text": STATUS_STOPPED,
            "status_style_sheet": bench_status_style_sheet(VIZ_CAPTION_COLOR),
        }
    return {
        "running": True,
        "button_text": STOP_BUTTON_TEXT,
        "button_style_sheet": stop_button_style_sheet(),
        "status_text": STATUS_LIVE if kind == PAPER_KIND else STATUS_RUNNING,
        "status_style_sheet": bench_status_style_sheet(
            ACCENT_GOLD_COLOR if kind == PAPER_KIND else SUCCESS_COLOR
        ),
    }


def _idle_button_text(kind: str) -> str:
    """The word a bench row's button carries while the row is not running."""
    return START_BUTTON_TEXT if kind == PAPER_KIND else RUN_BUTTON_TEXT


# The locust grid and the empty fleet

GRID_COLS = 6
GRID_SPACING = 10
GRID_MARGINS = (6, 6, 6, 6)
EMPTY_TEXT = "No active bots. Start bots to see visualizations."
EMPTY_STYLE_SHEET = f"color:{TEXT_PLACEHOLDER_COLOR};padding:40px;"
EMPTY_ALIGNMENT = "AlignCenter"
GRID_ALIGNMENT = "AlignLeft|AlignTop"

DEFAULT_THEME_KEY = "quantum"
THEME_KEYS = ("nebula", "matrix", "quantum", "ocean")
THEME_START_INDEX = 2

VIEW_LIST = "list"
VIEW_GRID = "grid"
VIEW_MODES = (VIEW_LIST, VIEW_GRID)
VIEW_LIST_INDEX = 0
VIEW_GRID_INDEX = 1
DEFAULT_VIEW_MODE = VIEW_LIST

OPACITY_MIN_PCT = 0
OPACITY_MAX_PCT = 100
OPACITY_START_PCT = 100
OPACITY_SLIDER_WIDTH_PX = 90


def grid_cell(idx: int, cols: int = GRID_COLS) -> tuple[int, int]:
    """Where the bot at one place in the fleet sits in the grid."""
    return (idx // cols, idx % cols)


def empty_label_row(count: int, cols: int = GRID_COLS) -> int:
    """The grid row the empty message is put back on after a rebuild."""
    return (count // cols) + 1


def view_index(mode: str) -> int:
    """Which stacked page one view name shows."""
    return VIEW_GRID_INDEX if mode == VIEW_GRID else VIEW_LIST_INDEX


def canvas_visible(mode: str) -> bool:
    """Whether the wire sheet is shown in one view."""
    return mode == VIEW_GRID


def canvas_shown_on_tab(tab_index: int, mode: str) -> bool:
    """Whether the wire sheet is shown for one tab and one view."""
    return tab_index == SWARM_TAB_INDEX and mode == VIEW_GRID


class FleetGrid:
    """The locust grid: which bot sits where, and whether it is empty."""

    def __init__(self, cols: int = GRID_COLS) -> None:
        self.cols = cols
        self.bot_ids: list[str] = []
        self.bot_data: dict[str, dict] = {}
        self.theme_key = DEFAULT_THEME_KEY

    def set_theme(self, theme_key: str) -> None:
        """Change the theme every locust is drawn in."""
        self.theme_key = theme_key

    def update_bots(self, bot_statuses: list) -> list:
        """Take one fleet load and return the bots that are no longer in it.

        A status with no bot id is skipped. A bot already placed keeps
        its place, so the wires between locusts do not jump.
        """
        current: list[str] = []
        for status in bot_statuses:
            found = status.get("bot_id", "") if isinstance(status, dict) else ""
            if not found:
                continue
            current.append(found)
            if found not in self.bot_data:
                self.bot_ids.append(found)
            self.bot_data[found] = status
        dropped = [one for one in self.bot_ids if one not in current]
        for one in dropped:
            self.bot_ids.remove(one)
            del self.bot_data[one]
        return dropped

    def cells(self) -> list:
        """Every bot with the grid row and column it is drawn in."""
        return [
            [bot_id, *grid_cell(at, self.cols)]
            for at, bot_id in enumerate(self.bot_ids)
        ]

    def is_empty(self) -> bool:
        """Whether the empty message is showing."""
        return not self.bot_ids

    def exchange_of(self, bot_id: str) -> str:
        """One bot's exchange, from the status it was drawn with."""
        return bot_exchange_id(self.bot_data.get(bot_id))


def bot_exchange_id(data: Any) -> str:
    """One bot's exchange, read out of the status it was drawn with.

    Anything that is not a status reads as no exchange, and so does a
    status whose exchange is missing or empty.
    """
    if isinstance(data, dict):
        return str(data.get("exchange", "") or "")
    return ""


ALL_EXCHANGES_LABEL = "All"
ALL_EXCHANGES_VALUE = ""


def exchange_items(exchanges_by_bot: dict) -> list:
    """The Exchange list: All first, then every exchange in the fleet, sorted."""
    distinct = {one for one in exchanges_by_bot.values() if one}
    return [[ALL_EXCHANGES_LABEL, ALL_EXCHANGES_VALUE]] + [
        [one, one] for one in sorted(distinct)
    ]


def ids_in_scope(exchanges_by_bot: dict, selected: str) -> list:
    """The bots the Quick Routing lists cover under one Exchange choice."""
    if not selected:
        return list(exchanges_by_bot)
    return [one for one, eid in exchanges_by_bot.items() if eid == selected]


def visible_bots(exchanges_by_bot: dict, selected: str) -> dict:
    """Whether each bot is shown under one Exchange choice."""
    if not selected:
        return {one: True for one in exchanges_by_bot}
    return {one: eid == selected for one, eid in exchanges_by_bot.items()}


# The list view rows

LIST_ROW_KEYS = ("bot_id", "symbol", "inflow_usd", "outflow_usd", "outflow_pct")
INFLOW_STAT_KEY = "ytd_folded_usd"
OUTFLOW_STAT_KEY = "ytd_scrummed_usd"
MISSING_AMOUNT = 0.0


def flow_amount(data: dict, key: str) -> float:
    """One year-to-date total, from the stats or from the status itself.

    A stats value of nothing falls through to the status, and a status
    value of nothing reads as zero. A stored `True` is a number here and
    reads as one dollar.
    """
    stats = data.get("stats", {}) or {}
    return float(
        stats.get(key, MISSING_AMOUNT)
        or data.get(key, MISSING_AMOUNT)
        or MISSING_AMOUNT
    )


def outflow_pct_by_bot(wires: list) -> dict:
    """How much of its profit each bot exports, added over its wires."""
    found: dict[str, float] = {}
    for wire in wires:
        source = str(wire.get("source_id", "") or "")
        if not source:
            continue
        found[source] = found.get(source, MISSING_AMOUNT) + float(
            wire.get("pct", 0) or 0
        )
    return found


def list_rows(bot_data: dict, wires: list, masked: bool = False) -> list:
    """The dense list, one row per bot, with the symbol already masked."""
    exported = outflow_pct_by_bot(wires)
    rows = []
    for bot_id, data in bot_data.items():
        held = data if isinstance(data, dict) else {}
        symbol = str(held.get("symbol", "") or "")
        rows.append(
            {
                "bot_id": bot_id,
                "symbol": mask_or(symbol, masked),
                "inflow_usd": flow_amount(held, INFLOW_STAT_KEY),
                "outflow_usd": flow_amount(held, OUTFLOW_STAT_KEY),
                "outflow_pct": exported.get(bot_id, MISSING_AMOUNT),
            }
        )
    return rows


def mask_or(value: Any, masked: bool) -> str:
    """One identifier, hidden behind stars while the mask is on."""
    return MASK_TEXT if masked else str(value)


# The privacy glyphs

REVEALED_GLYPH = "●"
MASKED_GLYPH = "○"
PRIVACY_DOT_TOOLTIP = (
    "Bot Swarm identifier privacy — masks bot hash IDs + "
    "symbol labels (● revealed / ○ masked)."
)
PRIVACY_MODE_ON_TEXT = "Privacy Mode: ON"
PRIVACY_MODE_OFF_TEXT = "Privacy Mode: OFF"
PRIVACY_MODE_TOOLTIP = (
    "Toggle ALL privacy masks across Trading + Bot Swarm tabs (shared singleton)."
)
PRIVACY_DOT_STYLE_SHEET = (
    f"QLabel{{color:{PRIMARY_BRIGHT_COLOR};background:transparent;"
    "padding:0 4px;font-size:14px;}"
)
BROKEN_DOT_STYLE_SHEET = (
    f"QFrame{{background:{VIZ_NUCLEAR_SURFACE_COLOR};border:1px solid "
    f"{VIZ_NUCLEAR_BORDER_COLOR};border-radius:3px;}}"
    "/* wiring-broken indicator (v3.23.12) */"
)
BROKEN_PRIVACY_BUTTON_STYLE_SHEET = (
    f"QPushButton{{background:{VIZ_NUCLEAR_SURFACE_COLOR};color:white;"
    f"border:1px solid {VIZ_NUCLEAR_BORDER_COLOR};padding:3px 12px;}}"
    "/* wiring-broken (v3.23.18) */"
)
PRIVACY_ON_STYLE_SHEET = (
    f"QPushButton{{background:{VIZ_CONFIRM_SURFACE_COLOR};color:{SUCCESS_COLOR};"
    f"border:1px solid {SUCCESS_COLOR};border-radius:3px;"
    "padding:3px 12px;font-weight:bold;}"
)
PRIVACY_OFF_STYLE_SHEET = (
    f"QPushButton{{background:{VIZ_PANEL_SURFACE_COLOR};color:{TEXT_INACTIVE_COLOR};"
    f"border:1px solid {CARD_METRIC_BORDER_COLOR};border-radius:3px;"
    "padding:3px 12px;}"
)
MASK_UNAVAILABLE_WARNING = (
    "[bot_swarm] WARNING: privacy_mask_registry import unavailable — click NO-OP\n"
)
MASK_FAILED_WARNING_FORMAT = (
    "[bot_swarm] WARNING: identifier mask toggle failed: {kind}: {message}\n"
)
PRIVACY_UNAVAILABLE_WARNING = (
    "[bot_swarm] WARNING: privacy_mask_registry import unavailable — "
    "Privacy Mode click NO-OP\n"
)
PRIVACY_FAILED_WARNING_FORMAT = (
    "[bot_swarm] WARNING: Privacy Mode toggle failed: {kind}: {message}\n"
)


def privacy_glyph(masked: bool) -> str:
    """The dot shown for the Bot Swarm identifier mask."""
    return MASKED_GLYPH if masked else REVEALED_GLYPH


def privacy_mode_text(any_on: bool) -> str:
    """The word on the Privacy Mode button."""
    return PRIVACY_MODE_ON_TEXT if any_on else PRIVACY_MODE_OFF_TEXT


def privacy_mode_style_sheet(any_on: bool) -> str:
    """The rule the Privacy Mode button is painted with."""
    return PRIVACY_ON_STYLE_SHEET if any_on else PRIVACY_OFF_STYLE_SHEET


# The wires

WIRE_KEYS = ("source_id", "target_id", "pct", "phase")
START_PHASE = 0.0
PHASE_RATE = 2.5
FRAME_INTERVAL_MS = 33

BIDIRECTIONAL_OFFSET_PX = 25.0
NO_OFFSET_PX = 0.0
HIT_THRESHOLD_PX = 12.0
HIT_SAMPLES = (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0)
CURVE_SCALE = 4

MIN_WIRE_PCT = 0
WIRE_PCT_MIN = 1
WIRE_PCT_MAX = 100
WIRE_PCT_START = 50
WIRE_PCT_SUFFIX = "% of realized profit"

SHORT_ID_LENGTH = 8

WIRE_CREATED_TOPIC = "wire.created"
WIRE_REMOVED_TOPIC = "wire.removed"
BOT_LOG_TOPIC = "bot.log"
BUS_TOPICS = (WIRE_CREATED_TOPIC, WIRE_REMOVED_TOPIC)
BUS_EMITTED = (WIRE_CREATED_TOPIC, WIRE_REMOVED_TOPIC, BOT_LOG_TOPIC)

WIRE_CONNECTED_LOG_FORMAT = "WIRE CONNECTED: {pct}% of profit → bot {target}"
WIRE_DISCONNECTED_LOG_FORMAT = "WIRE DISCONNECTED from bot {target}"


def short_id(bot_id: Any) -> str:
    """One bot's identifier cut to the eight characters a menu shows."""
    return str(bot_id)[:SHORT_ID_LENGTH]


def wire_center(origin: tuple, size: tuple) -> tuple:
    """The middle of one locust, measured from the sheet's top left."""
    return (origin[0] + size[0] / 2, origin[1] + size[1] / 2)


def point_in_rect(point: tuple, origin: tuple, size: tuple) -> bool:
    """Whether one point lands inside one locust.

    The rectangle carries its last row and column, so a point on the far
    edge is inside it.
    """
    return (
        origin[0] <= point[0] <= origin[0] + size[0] - 1
        and origin[1] <= point[1] <= origin[1] + size[1] - 1
    )


class WireBoard:
    """Every wire between two bots, and where each one is drawn."""

    def __init__(self) -> None:
        self.wires: list[dict] = []
        self.dragging = False
        self.drag_start_id = ""
        self.drag_pos: Optional[tuple] = None
        self.emitted: list[list] = []

    def add(self, source_id: str, target_id: str, pct: Any) -> dict:
        """Put one wire on the board and report the two messages it sends."""
        wire = {
            "source_id": source_id,
            "target_id": target_id,
            "pct": pct,
            "phase": START_PHASE,
        }
        self.wires.append(wire)
        self.emitted.append(
            [
                BOT_LOG_TOPIC,
                source_id,
                WIRE_CONNECTED_LOG_FORMAT.format(pct=pct, target=short_id(target_id)),
            ]
        )
        self.emitted.append([WIRE_CREATED_TOPIC, source_id, target_id, pct])
        return wire

    def on_created(self, event: dict) -> str:
        """Take one wire.created message. The same pair twice is one wire.

        Reports what it did: `refused` when either end is missing or the
        share is not above zero, `updated` when the pair was already
        wired, and `added` otherwise.
        """
        source = str(event.get("source_id", "") or "")
        target = str(event.get("target_id", "") or "")
        try:
            pct = float(event.get("pct", 0) or 0)
        except (TypeError, ValueError):
            return "refused"
        if not source or not target or pct <= MIN_WIRE_PCT:
            return "refused"
        for wire in self.wires:
            if wire.get("source_id") == source and wire.get("target_id") == target:
                wire["pct"] = pct
                return "updated"
        self.wires.append(
            {
                "source_id": source,
                "target_id": target,
                "pct": pct,
                "phase": START_PHASE,
            }
        )
        return "added"

    def on_removed(self, event: dict) -> str:
        """Take one wire.removed message and drop every wire it names."""
        source = str(event.get("source_id", "") or "")
        target = str(event.get("target_id", "") or "")
        if not source or not target:
            return "refused"
        self.wires = [
            wire
            for wire in self.wires
            if not (wire.get("source_id") == source and wire.get("target_id") == target)
        ]
        return "removed"

    def remove(self, source_id: str, target_id: str) -> None:
        """Cut one wire and report the two messages that go with it."""
        self.wires = [
            wire
            for wire in self.wires
            if not (wire["source_id"] == source_id and wire["target_id"] == target_id)
        ]
        self.emitted.append(
            [
                BOT_LOG_TOPIC,
                source_id,
                WIRE_DISCONNECTED_LOG_FORMAT.format(target=short_id(target_id)),
            ]
        )
        self.emitted.append([WIRE_REMOVED_TOPIC, source_id, target_id])

    def drop_bot(self, bot_id: str) -> None:
        """Cut every wire that touches one bot, which has left the fleet."""
        self.wires = [
            wire
            for wire in self.wires
            if wire["source_id"] != bot_id and wire["target_id"] != bot_id
        ]

    def advance(self, dt: float) -> None:
        """Move every wire's glow on by one frame."""
        for wire in self.wires:
            wire["phase"] = wire.get("phase", START_PHASE) + dt * PHASE_RATE

    def is_bidirectional(self, source_id: str, target_id: str) -> bool:
        """Whether a wire runs back the other way between the same two bots."""
        return any(
            wire["source_id"] == target_id and wire["target_id"] == source_id
            for wire in self.wires
        )

    def offset(self, wire: dict, centers: dict) -> float:
        """How far one wire is moved off the straight line between two bots.

        A wire with no pair running back stays on the line. A pair is
        split: left to right takes the lower slot and right to left the
        upper.
        """
        source = centers.get(wire["source_id"])
        target = centers.get(wire["target_id"])
        if not source or not target:
            return NO_OFFSET_PX
        if not self.is_bidirectional(wire["source_id"], wire["target_id"]):
            return NO_OFFSET_PX
        if source[0] <= target[0]:
            return BIDIRECTIONAL_OFFSET_PX
        return -BIDIRECTIONAL_OFFSET_PX

    def wire_at(
        self, pos: tuple, centers: dict, threshold: float = HIT_THRESHOLD_PX
    ) -> Optional[dict]:
        """The wire nearest a click, within the threshold, or nothing.

        Seven points along each wire are measured, with the wire's bend
        added, and the nearest of them decides.
        """
        best_wire = None
        best_dist = threshold
        for wire in self.wires:
            source = centers.get(wire["source_id"])
            target = centers.get(wire["target_id"])
            if not source or not target:
                continue
            shift = self.offset(wire, centers)
            for step in HIT_SAMPLES:
                px = source[0] + (target[0] - source[0]) * step
                py = source[1] + (target[1] - source[1]) * step
                py += shift * CURVE_SCALE * step * (1 - step)
                dist = math.sqrt((pos[0] - px) ** 2 + (pos[1] - py) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    best_wire = wire
        return best_wire

    def outgoing(self, bot_id: str) -> list:
        """Every wire leaving one bot."""
        return [wire for wire in self.wires if wire["source_id"] == bot_id]

    def incoming(self, bot_id: str) -> list:
        """Every wire arriving at one bot."""
        return [wire for wire in self.wires if wire["target_id"] == bot_id]

    def pct_of(self, source_id: str, target_id: str) -> Optional[Any]:
        """The share one wire carries, or nothing when no such wire exists."""
        return next(
            (
                wire.get("pct")
                for wire in self.wires
                if wire.get("source_id") == source_id
                and wire.get("target_id") == target_id
            ),
            None,
        )

    def start_drag(self, bot_id: str, pos: tuple) -> None:
        """Begin dragging a wire out of one bot."""
        self.dragging = True
        self.drag_start_id = bot_id
        self.drag_pos = pos

    def update_drag(self, pos: tuple) -> None:
        """Move the loose end of the wire being dragged."""
        self.drag_pos = pos

    def finish_drag(self, target_id: str) -> dict:
        """End a drag and report what the release means.

        Releasing on a second bot either asks for a rate or, when the
        pair is already wired, asks to cut it. Releasing on nothing cuts
        the source bot's only outgoing wire, or offers a picker when it
        has more than one.
        """
        start_id = self.drag_start_id
        self.dragging = False
        self.drag_pos = None
        if not start_id:
            self.drag_start_id = ""
            return {"action": "none", "pairs": [], "why": ""}
        outcome = self._release(start_id, target_id)
        self.drag_start_id = ""
        return outcome

    def _release(self, start_id: str, target_id: str) -> dict:
        """What one release means, before the drag state is cleared."""
        if target_id and target_id != start_id:
            existing = [
                wire
                for wire in self.wires
                if wire["source_id"] == start_id and wire["target_id"] == target_id
            ]
            if existing:
                return {
                    "action": "confirm_disconnect",
                    "pairs": [[start_id, target_id]],
                    "why": DRAG_ONTO_WIRED_WHY,
                }
            return {
                "action": "configure",
                "pairs": [[start_id, target_id]],
                "why": "",
            }
        if not target_id:
            leaving = self.outgoing(start_id)
            if len(leaving) == 1:
                return {
                    "action": "confirm_disconnect",
                    "pairs": [[leaving[0]["source_id"], leaving[0]["target_id"]]],
                    "why": DRAG_TO_EMPTY_WHY,
                }
            if len(leaving) > 1:
                return {"action": "pick", "pairs": [], "why": ""}
        return {"action": "none", "pairs": [], "why": ""}


DRAG_ONTO_WIRED_WHY = "Dragging between two already-connected bots disconnects them."
DRAG_TO_EMPTY_WHY = (
    "Releasing a drag on empty space disconnects the source bot's only "
    "outgoing wire."
)

CONFIRM_TITLE = "Disconnect Smart Wire?"
CONFIRM_LINE_FORMAT = "  • {source} → {target}{pct}"
CONFIRM_PCT_FORMAT = " at {pct}%"
CONFIRM_HEAD_FORMAT = "Disconnect {count} Smart Wire"
CONFIRM_PLURAL = "s"
CONFIRM_TAIL = "\n\nThis stops profit routing between these bots and cannot be undone."
CONFIRM_DEFAULT_BUTTON = "No"
CONFIRM_YES_BUTTON = "Yes"

PANEL_CONFIG = "config"
PANEL_CONFIRM = "confirm"
PANEL_PICKER = "picker"
PANEL_OK = "ok"
PANEL_YES = "yes"
PANEL_CANCEL = "cancel"
PANEL_OK_BUTTON = "OK"

#: How many numbers one measured locust box carries: left, top, width, height.
BOX_VALUES = 4

#: The style the wire sheet is laid over its page with.
OVERLAY_STYLE = {
    "position": "absolute",
    "left": "0",
    "top": "0",
    "right": "0",
    "bottom": "0",
}

#: Every word a page needs to tell one panel from another, and to answer it.
PANEL_WORDS = {
    "config": PANEL_CONFIG,
    "confirm": PANEL_CONFIRM,
    "picker": PANEL_PICKER,
    "ok": PANEL_OK,
    "yes": PANEL_YES,
    "cancel": PANEL_CANCEL,
    "ok_button": PANEL_OK_BUTTON,
    "yes_button": CONFIRM_YES_BUTTON,
}

# The drag has no on-screen position off a widget; the release decides alone.
DRAG_START_POS = (0.0, 0.0)

CONFIRM_UNSHOWABLE_LOG = (
    "wire-removal confirmation could not be shown (%s); refusing the removal"
)


def confirm_body(pairs: list, pcts: list, why: str = "") -> str:
    """The words the disconnect confirmation puts on screen.

    `pcts` holds one share per pair, or nothing where the wire has gone.
    The share is shown because it is the part the operator cannot
    rebuild from memory.
    """
    lines = [
        CONFIRM_LINE_FORMAT.format(
            source=short_id(source),
            target=short_id(target),
            pct="" if pct is None else CONFIRM_PCT_FORMAT.format(pct=pct),
        )
        for (source, target), pct in zip(pairs, pcts)
    ]
    head = (f"{why}\n\n" if why else "") + CONFIRM_HEAD_FORMAT.format(count=len(pairs))
    plural = CONFIRM_PLURAL if len(pairs) != 1 else ""
    return head + plural + "?\n\n" + "\n".join(lines) + CONFIRM_TAIL


PICKER_OUTGOING_HEADER = "Disconnect outgoing wire:"
PICKER_INCOMING_HEADER = "Disconnect incoming wire:"
PICKER_OUTGOING_FORMAT = "  → {target} ({pct}%)"
PICKER_INCOMING_FORMAT = "  ← {source} ({pct}%)"
MENU_CANCEL = "Cancel"
MENU_SEPARATOR = "---"
MENU_WIRE_HEADER_FORMAT = "Wire: {source} → {target} ({pct}%)"
MENU_DISCONNECT = "Disconnect Wire"
MENU_DISCONNECT_BOTH = "Disconnect Both Directions"
MENU_STYLE_SHEET = (
    f"QMenu {{ background: {MENU_SURFACE_COLOR}; color: {TEXT_HIGH_COLOR}; "
    f"border: 1px solid {MENU_BORDER_COLOR}; }}"
    f"QMenu::item:selected {{ background: {MENU_ITEM_SELECTED_COLOR}; }}"
)
WIRE_MENU_STYLE_SHEET = MENU_STYLE_SHEET + (
    f"QMenu::separator {{ background: {MENU_BORDER_COLOR}; height: 1px; }}"
)


def picker_entries(outgoing: list, incoming: list) -> list:
    """The lines the pick-a-wire menu shows for one bot."""
    entries: list = []
    if outgoing:
        entries.append([PICKER_OUTGOING_HEADER, None])
        for wire in outgoing:
            entries.append(
                [
                    PICKER_OUTGOING_FORMAT.format(
                        target=short_id(wire["target_id"]), pct=wire["pct"]
                    ),
                    ["out", wire["source_id"], wire["target_id"]],
                ]
            )
    if incoming:
        if outgoing:
            entries.append([MENU_SEPARATOR, None])
        entries.append([PICKER_INCOMING_HEADER, None])
        for wire in incoming:
            entries.append(
                [
                    PICKER_INCOMING_FORMAT.format(
                        source=short_id(wire["source_id"]), pct=wire["pct"]
                    ),
                    ["in", wire["source_id"], wire["target_id"]],
                ]
            )
    entries.append([MENU_SEPARATOR, None])
    entries.append([MENU_CANCEL, None])
    return entries


def wire_menu_entries(wire: dict, bidirectional: bool) -> list:
    """The lines the right-click menu shows over one wire."""
    entries = [
        [
            MENU_WIRE_HEADER_FORMAT.format(
                source=short_id(wire["source_id"]),
                target=short_id(wire["target_id"]),
                pct=wire.get("pct", 0),
            ),
            None,
        ],
        [MENU_SEPARATOR, None],
        [MENU_DISCONNECT, "one"],
    ]
    if bidirectional:
        entries.append([MENU_DISCONNECT_BOTH, "both"])
    entries.append([MENU_SEPARATOR, None])
    entries.append([MENU_CANCEL, None])
    return entries


WIRE_CONFIG_TITLE = "Configure Profit Wire"
WIRE_CONFIG_WIDTH_PX = 350
WIRE_CONFIG_PROMPT_FORMAT = "Route profits from bot {source}\nto bot {target}"
WIRE_CONFIG_ROW_LABEL = "Routing:"


def wire_config_prompt(source_id: str, target_id: str) -> str:
    """The sentence above the rate box when a new wire is being set."""
    return WIRE_CONFIG_PROMPT_FORMAT.format(
        source=short_id(source_id), target=short_id(target_id)
    )


# The routes a wire is stored as

ROUTES_KEY = "smart_wire_routes"
SCRUMMING_KEY = "scrumming_state"
BOTS_KEY = "bots"
DEST_KEY = "dest_bot_id"
PCT_KEY = "pct"

HYDRATION_SHORTFALL_WARNING = (
    "wire hydration: %d of %d route(s) in bot_state.json painted -- %d "
    "rejected by the bus, %d unusable; the wire overlay under-reports the "
    "state file"
)
HYDRATION_EMITTED_INFO = "wire hydration: %d wire.created event(s) emitted"
HYDRATION_NO_BUS_ERROR = (
    "wire hydration: no event bus, so no route in bot_state.json reaches " "the canvas"
)
HYDRATION_REJECTED_WARNING = (
    "wire hydration: the bus rejected route %s -> %s (%s%%), so that wire "
    "is not painted"
)
HYDRATION_FAILED_ERROR = (
    "wire hydration failed; the wire overlay may show fewer wires than "
    "bot_state.json holds"
)
LIST_REFRESH_DEBUG = "list-view row refresh raised: %s"
STATE_WRITE_FAILED_ERROR = (
    "bot_visualizer: direct write to bot_state.json FAILED (%s: %s). Wire "
    "routing changes made in the GUI were not persisted by this path; the "
    "durable smart_wires channel is unaffected."
)


def apply_routes(state: dict, add: list, remove: list) -> dict:
    """Write wires into a stored fleet load and hand the whole load back.

    A route added for a destination that is already wired takes the new
    share rather than a second entry. A route removed from a bot the
    load does not carry is skipped.
    """
    bots = state.setdefault(BOTS_KEY, {})

    def routes_of(bot_id: str) -> list:
        bot = bots.setdefault(bot_id, {})
        scrumming = bot.setdefault(SCRUMMING_KEY, {})
        routes = scrumming.setdefault(ROUTES_KEY, [])
        if not isinstance(routes, list):
            routes = []
            scrumming[ROUTES_KEY] = routes
        return routes

    for source, dest, pct in add:
        routes = routes_of(source)
        replaced = False
        for entry in routes:
            if isinstance(entry, dict) and entry.get(DEST_KEY) == dest:
                entry[PCT_KEY] = float(pct)
                replaced = True
                break
        if not replaced:
            routes.append({DEST_KEY: dest, PCT_KEY: float(pct)})

    for source, dest in remove:
        if source not in bots:
            continue
        routes = routes_of(source)
        bots[source][SCRUMMING_KEY][ROUTES_KEY] = [
            entry
            for entry in routes
            if not (isinstance(entry, dict) and entry.get(DEST_KEY) == dest)
        ]
    return state


def clear_all_routes(state: dict) -> list:
    """Empty every bot's routes and report the pairs that were there."""
    bots = state.get(BOTS_KEY, {}) if isinstance(state, dict) else {}
    removed: list = []
    for bot_id, bot in bots.items():
        if not isinstance(bot, dict):
            continue
        scrumming = bot.get(SCRUMMING_KEY, {})
        if not isinstance(scrumming, dict):
            continue
        routes = scrumming.get(ROUTES_KEY, [])
        if isinstance(routes, list):
            for entry in routes:
                if isinstance(entry, dict):
                    dest = entry.get(DEST_KEY, "")
                    if dest:
                        removed.append([bot_id, str(dest)])
        scrumming[ROUTES_KEY] = []
    return removed


def hydration_plan(state: dict) -> dict:
    """The wires a stored fleet load asks the canvas to paint.

    `seen` counts every route in the load, `events` the ones that can be
    painted, and `unusable` the rest. Nothing is emitted here; the
    caller sends the events and counts the ones the bus refused.
    """
    bots = state.get(BOTS_KEY, {}) if isinstance(state, dict) else {}
    events: list = []
    seen = 0
    for bot_id, bot in bots.items():
        if not isinstance(bot, dict):
            continue
        scrumming = bot.get(SCRUMMING_KEY, {})
        routes = scrumming.get(ROUTES_KEY, []) if isinstance(scrumming, dict) else []
        if not isinstance(routes, list):
            continue
        for entry in routes:
            seen += 1
            if not isinstance(entry, dict):
                continue
            dest = str(entry.get(DEST_KEY, "") or "")
            try:
                pct = float(entry.get(PCT_KEY, 0) or 0)
            except (TypeError, ValueError):
                pct = 0.0
            if not dest or pct <= MIN_WIRE_PCT:
                continue
            events.append([str(bot_id), dest, pct])
    return {"events": events, "seen": seen, "unusable": seen - len(events)}


def hydration_shortfall(painted: int, seen: int, rejected: int) -> Optional[list]:
    """The warning a shortfall writes, or nothing when every route painted.

    Silent when the two counts agree, so the record always means a real
    shortfall and never just that the load ran.
    """
    if painted == seen:
        return None
    return [
        WARNING_LEVEL,
        HYDRATION_SHORTFALL_WARNING,
        painted,
        seen,
        rejected,
        seen - painted - rejected,
    ]


OUTER_MARGINS = (4, 4, 4, 4)
OUTER_SPACING = 0
VIZ_MARGINS = (4, 4, 4, 4)
VIZ_SPACING = 4
INNER_SPACING = 0
LAYER_MARGINS = (8, 8, 8, 8)
LAYER_SPACING = 6
LAYER_LIST_MARGINS = (4, 4, 4, 4)
LAYER_LIST_SPACING = 4
SUMMARY_SPACING = 12
QT_UNSET_SPACING = 6
QT_GROUP_BOX_MARGIN = 9
NESTED_MARGINS = (0, 0, 0, 0)
HEADER_SPACING = QT_UNSET_SPACING
LAYER_HEADER_SPACING = QT_UNSET_SPACING
SUMMARY_MARGINS = (
    QT_GROUP_BOX_MARGIN,
    QT_GROUP_BOX_MARGIN,
    QT_GROUP_BOX_MARGIN,
    QT_GROUP_BOX_MARGIN,
)

LABEL_WORD_WRAP = False
DESCRIPTION_WORD_WRAP = True
DOT_CURSOR = "PointingHandCursor"

EXCHANGE_CAPTION = "Exchange:"
THEME_CAPTION = "Theme:"
VIEW_CAPTION = "View:"
WIRES_CAPTION = "Wires:"
VIEW_LABELS = ("List", "Grid")

EXCHANGE_TOOLTIP = (
    "Filter Bot Swarm visualizer + Quick Routing scope by exchange. Default: All."
)
VIEW_TOOLTIP = (
    "List: dense row-per-bot table with vertical-lane wires "
    "(the default).\nGrid: locust-avatar swarm view (legacy fallback)."
)
OPACITY_TOOLTIP = (
    "Wire opacity 0–100 %. Lower for more contrast on underlying "
    "readouts; 100 = fully opaque."
)

SIM_HEADING_TEXT = "SIMULATOR SWARM"
PAPER_HEADING_TEXT = "PAPER TRADER SWARM"
SIM_DESCRIPTION_TEXT = (
    "Run multiple simultaneous simulators. Each bot runs independently "
    "on its own asset/timeframe. Results aggregate in the summary row."
)
PAPER_DESCRIPTION_TEXT = (
    "Run multiple live paper trading bots simultaneously. Each bot trades "
    "a different asset with virtual capital against real market data. "
    "Source: CoinGecko (crypto) or Yahoo Finance (equities). No geographic "
    "restrictions."
)

SIM_ADD_TEXT = "+ Add Sim Bot"
SIM_RUN_ALL_TEXT = "▶ Run All"
SIM_STOP_ALL_TEXT = "■ Stop All"
PAPER_ADD_TEXT = "+ Add Paper Bot"
PAPER_START_ALL_TEXT = "▶ Start All"
PAPER_STOP_ALL_TEXT = "■ Stop All"

SIM_SUMMARY_ORDER = ("wins", "pnl", "trades")
PAPER_SUMMARY_ORDER = ("total", "pnl", "active")


def heading_style_sheet(color: str) -> str:
    """The rule one layer's heading is painted with."""
    return f"color:{color};font-weight:bold;font-size:10px;font-family:Consolas;"


DESCRIPTION_STYLE_SHEET = f"color:{VIZ_CAPTION_COLOR};font-size:8px;"


def layer_button_style_sheet(color: str, hover: str) -> str:
    """The rule one of a layer's three header buttons is painted with."""
    return (
        f"QPushButton{{background:{VIZ_PANEL_SURFACE_COLOR};color:{color};"
        f"border:1px solid {color};"
        "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
        f"QPushButton:hover{{background:{hover};}}"
    )


SCROLL_STYLE_SHEET = (
    f"QScrollArea{{border:1px solid {VIZ_PANEL_BORDER_COLOR};"
    f"background:{VIZ_SWARM_SURFACE_COLOR};}}"
)

SWARM_LIST_STYLE_SHEET = f"background:{VIZ_SWARM_SURFACE_COLOR};"


def summary_box_style_sheet(color: str) -> str:
    """The rule the box under one layer's rows is painted with."""
    return (
        f"QGroupBox{{border:1px solid {VIZ_PANEL_BORDER_COLOR};color:{color};"
        "font-size:8px;font-weight:bold;margin-top:6px;padding-top:6px;}"
        "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
    )


SUMMARY_LABEL_STYLE_SHEET = (
    f"color:{VIZ_HEADING_COLOR};font-size:9px;font-family:Consolas;" "font-weight:bold;"
)


def layer_button(text: str, color: str, hover: str) -> dict:
    """One header button of a layer: its word and its paint rule."""
    return {
        "kind": BUTTON_KIND,
        "text": text,
        "style_sheet": layer_button_style_sheet(color, hover),
    }


LAYER_CHROME = {
    SIM_KIND: {
        "heading_text": SIM_HEADING_TEXT,
        "heading_style_sheet": heading_style_sheet(PRIMARY_BRIGHT_COLOR),
        "description_text": SIM_DESCRIPTION_TEXT,
        "summary_title": SIM_SUMMARY_TITLE,
        "summary_style_sheet": summary_box_style_sheet(PRIMARY_BRIGHT_COLOR),
        "summary_order": list(SIM_SUMMARY_ORDER),
        "buttons": [
            layer_button(SIM_ADD_TEXT, SUCCESS_COLOR, VIZ_GO_HOVER_COLOR),
            layer_button(SIM_RUN_ALL_TEXT, PRIMARY_BRIGHT_COLOR, VIZ_SIM_HOVER_COLOR),
            layer_button(SIM_STOP_ALL_TEXT, ERROR_COLOR, VIZ_STOP_HOVER_COLOR),
        ],
    },
    PAPER_KIND: {
        "heading_text": PAPER_HEADING_TEXT,
        "heading_style_sheet": heading_style_sheet(ACCENT_GOLD_COLOR),
        "description_text": PAPER_DESCRIPTION_TEXT,
        "summary_title": PAPER_SUMMARY_TITLE,
        "summary_style_sheet": summary_box_style_sheet(ACCENT_GOLD_COLOR),
        "summary_order": list(PAPER_SUMMARY_ORDER),
        "buttons": [
            layer_button(PAPER_ADD_TEXT, ACCENT_GOLD_COLOR, VIZ_GOLD_HOVER_COLOR),
            layer_button(PAPER_START_ALL_TEXT, SUCCESS_COLOR, VIZ_GO_HOVER_COLOR),
            layer_button(PAPER_STOP_ALL_TEXT, ERROR_COLOR, VIZ_STOP_HOVER_COLOR),
        ],
    },
}


# The whole screen

ACTIONS = {
    "register_sim": "Build a Simulator Swarm row for one run",
    "update_sim": "Write one simulator tick into its row",
    "stop_sim": "Mark one simulator run finished",
    "register_paper": "Build a Paper Swarm row for one session",
    "update_paper": "Write one paper tick into its row",
    "stop_paper": "Mark one paper session stopped",
    "register_live": "Build a Bot Swarm row for one live bot",
    "update_live": "Write one live tick into its row",
    "stop_live": "Mark one live bot stopped",
    "update_bots": "Take one fleet load into the locust grid",
    "wire_created": "Take one wire.created message",
    "wire_removed": "Take one wire.removed message",
    "remove_wire": "Cut one wire",
    "animate": "Move every wire's glow on by one frame",
    "set_view_mode": "Switch between the list and the grid",
    "set_opacity": "Set how solid the wires are drawn",
    "set_exchange": "Filter the swarm by exchange",
    "set_theme": "Change the theme every locust is drawn in",
    "set_masked": "Turn the identifier mask on or off",
    "toggle_privacy_mode": "Turn every mask on, or every mask off",
    "wire_sheet": "Redraw the wires over the locust boxes the page measured",
    "finish_drag": "End a wire drag and open what the release asks for",
    "answer_panel": "Take the answer to the rate box, the confirmation or the picker",
    "hydrate": "Paint the wires a stored fleet load holds",
}

SIGNALS: tuple = ()
THREADS: tuple = ()
TIMERS = {"animation": FRAME_INTERVAL_MS}
TIMER_DELAYS_MS = (FRAME_INTERVAL_MS,)


class BotVisualizerModel:
    """The whole Bot Swarm screen, with no widget behind it."""

    def __init__(self) -> None:
        self.grid = FleetGrid()
        self.board = WireBoard()
        self.live = SwarmLayer(LIVE_KIND)
        self.sim = SwarmLayer(SIM_KIND, self.refresh_sim_summary)
        self.paper = SwarmLayer(PAPER_KIND, self.refresh_paper_summary)
        self.sim_summary_shown = dict(SIM_SUMMARY_START)
        self.paper_summary_shown = dict(PAPER_SUMMARY_START)
        self.bench_sim_running = 0
        self.bench_sim_total = 0
        self.bench_paper_running = 0
        self.bench_paper_total = 0
        self.bench_paper_capital: Any = DEFAULT_CAPITAL
        self.view_mode = DEFAULT_VIEW_MODE
        self.opacity_pct = OPACITY_START_PCT
        self.exchange = ALL_EXCHANGES_VALUE
        self.masked = False
        self.any_masked = False
        self.privacy_mode_shown = {
            "text": privacy_mode_text(False),
            "style_sheet": privacy_mode_style_sheet(False),
        }
        self.tab_index = SWARM_TAB_INDEX
        self.log_lines: list[list] = []
        self.rows_sent: list[list] = []
        self.panel: Optional[dict] = None
        self.sheet: dict = {}

    def layer(self, kind: str) -> SwarmLayer:
        """One of the three layers, by name."""
        return {LIVE_KIND: self.live, SIM_KIND: self.sim, PAPER_KIND: self.paper}[kind]

    def update_bots(self, bot_statuses: list) -> None:
        """Take one fleet load, then cut the wires of every bot that left.

        The dense list is handed a fresh row set here and nowhere else,
        so a mask turned on between two loads reaches the list only at
        the next one.
        """
        for bot_id in self.grid.update_bots(bot_statuses):
            self.board.drop_bot(bot_id)
        self.rows_sent.append(
            list_rows(self.grid.bot_data, self.board.wires, self.masked)
        )
        self.set_exchange(self.exchange)

    def set_exchange(self, exchange: str) -> None:
        """Choose one exchange to filter by.

        The selector holds only the exchanges the fleet trades on, so a
        name no bot carries leaves the filter on All. The same rule runs
        after a fleet load, which is how the last bot on an exchange
        leaving clears the filter.
        """
        offered = {found[1] for found in exchange_items(self.exchanges())}
        self.exchange = exchange if exchange in offered else ALL_EXCHANGES_VALUE

    def hydrate(self, state: dict) -> dict:
        """Paint the wires a stored fleet load holds and report the count."""
        plan = hydration_plan(state)
        for source, target, pct in plan["events"]:
            self.board.on_created(
                {"source_id": source, "target_id": target, "pct": pct}
            )
        painted = len(plan["events"])
        shortfall = hydration_shortfall(painted, plan["seen"], 0)
        if shortfall is not None:
            self.log_lines.append(shortfall)
        self.log_lines.append([INFO_LEVEL, HYDRATION_EMITTED_INFO, painted])
        return {"painted": painted, "seen": plan["seen"], "unusable": plan["unusable"]}

    def exchanges(self) -> dict:
        """Each bot in the fleet with the exchange it trades on."""
        return {one: self.grid.exchange_of(one) for one in self.grid.bot_ids}

    def toggle_identifier_mask(self, masked: Optional[bool] = None) -> None:
        """Flip the Bot Swarm identifier mask.

        The dot follows immediately. The Privacy Mode button does NOT:
        the screen never rewrites it here, so it can read OFF while this
        mask is on.
        """
        self.masked = (not self.masked) if masked is None else bool(masked)
        self.any_masked = self.any_masked or self.masked

    def finish_drag(self, source_id: str, target_id: str) -> Optional[dict]:
        """Set ``panel`` to what a wire drag from ``source_id`` asks for next.

        ``WireBoard.finish_drag`` decides the outcome; this turns it into
        the rate box, the disconnect confirmation or the wire picker the
        screen shows.
        """
        self.panel = None
        self.board.start_drag(source_id, DRAG_START_POS)
        outcome = self.board.finish_drag(target_id)
        action = outcome["action"]
        pairs = [tuple(pair) for pair in outcome["pairs"]]
        if action == "configure":
            self.panel = self._config_panel(pairs[0][0], pairs[0][1])
        elif action == "confirm_disconnect":
            pcts = [self.board.pct_of(source, target) for source, target in pairs]
            self.panel = self._confirm_panel(pairs, pcts, outcome["why"])
        elif action == "pick":
            self.panel = {
                "kind": PANEL_PICKER,
                "source_id": source_id,
                "title": PICKER_OUTGOING_HEADER,
                "entries": picker_entries(
                    self.board.outgoing(source_id), self.board.incoming(source_id)
                ),
                "cancel": MENU_CANCEL,
                "style_sheet": MENU_STYLE_SHEET,
            }
        return self.panel

    def _config_panel(self, source_id: str, target_id: str) -> dict:
        """The rate box shown before a new wire between two bots is made."""
        return {
            "kind": PANEL_CONFIG,
            "source_id": source_id,
            "target_id": target_id,
            "title": WIRE_CONFIG_TITLE,
            "prompt": wire_config_prompt(source_id, target_id),
            "row_label": WIRE_CONFIG_ROW_LABEL,
            "suffix": WIRE_PCT_SUFFIX,
            "min": WIRE_PCT_MIN,
            "max": WIRE_PCT_MAX,
            "value": WIRE_PCT_START,
            "width_px": WIRE_CONFIG_WIDTH_PX,
            "ok": PANEL_OK_BUTTON,
            "cancel": MENU_CANCEL,
        }

    def _confirm_panel(self, pairs: list, pcts: list, why: str) -> dict:
        """The disconnect confirmation shown over ``pairs``."""
        return {
            "kind": PANEL_CONFIRM,
            "title": CONFIRM_TITLE,
            "body": confirm_body(pairs, pcts, why),
            "pairs": [[source, target] for source, target in pairs],
            "default": CONFIRM_DEFAULT_BUTTON,
            "yes": CONFIRM_YES_BUTTON,
            "no": CONFIRM_DEFAULT_BUTTON,
        }

    def answer_panel(self, choice: str, pct: Any = None, entry: Any = None) -> None:
        """Take the operator's answer to ``panel`` and clear it.

        ``ok`` makes the wire the rate box was set for, ``yes`` cuts every
        pair the confirmation named, and an ``entry`` from the picker cuts
        the one wire it names.
        """
        panel = self.panel
        self.panel = None
        if not isinstance(panel, dict) or choice == PANEL_CANCEL:
            return
        kind = panel.get("kind")
        if kind == PANEL_CONFIG and choice == PANEL_OK:
            share = WIRE_PCT_START if pct is None else pct
            self.board.add(panel["source_id"], panel["target_id"], share)
        elif kind == PANEL_CONFIRM and choice == PANEL_YES:
            for source, target in panel.get("pairs") or []:
                self.board.remove(source, target)
        elif kind == PANEL_PICKER and isinstance(entry, (list, tuple)):
            chosen = list(entry)
            if len(chosen) == 3:
                self.board.remove(chosen[1], chosen[2])

    def toggle_privacy_mode(self) -> None:
        """Turn every mask on, or every mask off, and rewrite the button."""
        turning_on = not self.any_masked
        self.any_masked = turning_on
        self.masked = turning_on
        self.privacy_mode_shown = {
            "text": privacy_mode_text(turning_on),
            "style_sheet": privacy_mode_style_sheet(turning_on),
        }

    def refresh_sim_summary(self) -> None:
        """Rewrite the three lines under the Simulator Swarm rows."""
        self.sim_summary_shown = sim_summary(
            self.bench_sim_running, self.bench_sim_total, self.sim
        )

    def refresh_paper_summary(self) -> None:
        """Rewrite the three lines under the Paper Swarm rows.

        Only the bench rows reach it. The runs the paper trader started
        are counted in neither line, which is why a live paper session
        leaves the summary reading zero.
        """
        self.paper_summary_shown = paper_summary(
            self.bench_paper_running, self.bench_paper_total, self.bench_paper_capital
        )


PANE_MODEL = BotVisualizerModel()


def wire_sheet(model: BotVisualizerModel, boxes: Any) -> dict:
    """The wire sheet drawn over the locust boxes the page measured.

    ``boxes`` maps a bot id to its left, top, width and height; the
    centre of each is what ``wire_canvas_surface`` paints between.
    """
    from . import wire_canvas_surface

    centers = {
        str(bot_id): list(wire_center((box[0], box[1]), (box[2], box[3])))
        for bot_id, box in (boxes or {}).items()
        if isinstance(box, (list, tuple)) and len(box) == BOX_VALUES
    }
    state = wire_canvas_surface.CanvasTabState(
        wires=[dict(one) for one in model.board.wires],
        bot_centers=centers,
        theme_key=model.grid.theme_key,
        wire_opacity_pct=model.opacity_pct,
    )
    return wire_canvas_surface.build_view_model(
        wire_canvas_surface.WireCanvasModel(state)
    )


def locust_cards(model: BotVisualizerModel) -> dict:
    """One locust card payload per bot in the grid, keyed by bot id.

    ``bot_node_surface`` builds each card, so the grid draws the same
    locust the Qt ``BotNodeWidget`` paints.
    """
    from . import bot_node_surface

    hide = bot_node_surface.masking(
        (bot_node_surface.MASK_FIELD_ID,) if model.masked else ()
    )
    return {
        bot_id: bot_node_surface.build_view_model(
            bot_node_surface.BotNodeModel(
                theme_key=model.grid.theme_key, bot_data=data
            ),
            mask=hide,
        )
        for bot_id, data in model.grid.bot_data.items()
    }


def build_payload(model: BotVisualizerModel) -> dict:
    """Everything one Bot Swarm screen carries, as the frontend reads it."""
    exchanges = model.exchanges()
    return {
        "method": METHOD,
        "logger_name": LOGGER_NAME,
        "colors": dict(COLORS),
        "warning_level": WARNING_LEVEL,
        "info_level": INFO_LEVEL,
        "mask_field_id": MASK_FIELD_ID,
        "mask_text": MASK_TEXT,
        "tab_kind": TAB_KIND,
        "row_kind": ROW_KIND,
        "label_kind": LABEL_KIND,
        "button_kind": BUTTON_KIND,
        "tab_style_sheet": TAB_STYLE_SHEET,
        "tab_titles": list(TAB_TITLES),
        "swarm_tab_index": SWARM_TAB_INDEX,
        "sim_tab_index": SIM_TAB_INDEX,
        "paper_tab_index": PAPER_TAB_INDEX,
        "header_title": HEADER_TITLE,
        "header_hint": HEADER_HINT,
        "row_kinds": list(ROW_KINDS),
        "fallback_kind": FALLBACK_KIND,
        "swarm_accents": {one: list(found) for one, found in SWARM_ACCENTS.items()},
        "swarm_tints": dict(SWARM_TINTS),
        "fallback_tint": FALLBACK_TINT,
        "row_margins": list(ROW_MARGINS),
        "row_spacing": ROW_SPACING,
        "row_radius_px": ROW_RADIUS_PX,
        "row_handle_keys": list(ROW_HANDLE_KEYS),
        "context_cfg_keys": list(CONTEXT_CFG_KEYS),
        "feed_cfg_keys": list(FEED_CFG_KEYS),
        "column_widths": {
            "dot": DOT_WIDTH_PX,
            "id": ID_WIDTH_PX,
            "context": CONTEXT_WIDTH_PX,
            "mode": MODE_WIDTH_PX,
            "feed": FEED_WIDTH_PX,
            "capital": CAPITAL_WIDTH_PX,
            "status": STATUS_WIDTH_PX,
            "metric": METRIC_WIDTH_PX,
            "pnl": PNL_WIDTH_PX,
            "trades": TRADES_WIDTH_PX,
        },
        "dot_text": DOT_TEXT,
        "missing_text": MISSING_TEXT,
        "pnl_placeholder_text": PNL_PLACEHOLDER_TEXT,
        "trades_placeholder_text": TRADES_PLACEHOLDER_TEXT,
        "status_running": STATUS_RUNNING,
        "status_stopped": STATUS_STOPPED,
        "status_done": STATUS_DONE,
        "status_live": STATUS_LIVE,
        "status_idle": STATUS_IDLE,
        "capital_text_format": CAPITAL_TEXT_FORMAT,
        "pnl_text_format": PNL_TEXT_FORMAT,
        "trades_text_format": TRADES_TEXT_FORMAT,
        "progress_text_format": PROGRESS_TEXT_FORMAT,
        "price_small_format": PRICE_SMALL_FORMAT,
        "price_large_format": PRICE_LARGE_FORMAT,
        "price_format_limit": PRICE_FORMAT_LIMIT,
        "progress_min_total": PROGRESS_MIN_TOTAL,
        "progress_max_pct": PROGRESS_MAX_PCT,
        "progress_scale": PROGRESS_SCALE,
        "progress_done_text": PROGRESS_DONE_TEXT,
        "progress_start_text": PROGRESS_START_TEXT,
        "default_capital": DEFAULT_CAPITAL,
        "default_candle_total": DEFAULT_CANDLE_TOTAL,
        "sim_candle_total": SIM_CANDLE_TOTAL,
        "default_pnl": DEFAULT_PNL,
        "sim_mode": SIM_MODE,
        "paper_mode": PAPER_MODE,
        "live_mode": LIVE_MODE,
        "layer_id_keys": dict(LAYER_ID_KEYS),
        "layer_stop_status": dict(LAYER_STOP_STATUS),
        "sim_registered_signal": SIM_REGISTERED_SIGNAL,
        "paper_registered_signal": PAPER_REGISTERED_SIGNAL,
        "sim_summary_running_format": SIM_SUMMARY_RUNNING_FORMAT,
        "sim_summary_pnl_format": SIM_SUMMARY_PNL_FORMAT,
        "sim_summary_pnl_empty": SIM_SUMMARY_PNL_EMPTY,
        "sim_summary_trades": SIM_SUMMARY_TRADES,
        "paper_summary_active_format": PAPER_SUMMARY_ACTIVE_FORMAT,
        "paper_summary_capital_format": PAPER_SUMMARY_CAPITAL_FORMAT,
        "paper_summary_pnl": PAPER_SUMMARY_PNL,
        "sim_summary_title": SIM_SUMMARY_TITLE,
        "paper_summary_title": PAPER_SUMMARY_TITLE,
        "sim_summary_wins_start": SIM_SUMMARY_WINS_START,
        "sim_summary_trades_start": SIM_SUMMARY_TRADES_START,
        "paper_summary_capital_start": PAPER_SUMMARY_CAPITAL_START,
        "paper_summary_active_start": PAPER_SUMMARY_ACTIVE_START,
        "sim_bench_id_format": SIM_BENCH_ID_FORMAT,
        "paper_bench_id_format": PAPER_BENCH_ID_FORMAT,
        "sim_bench_assets": list(SIM_BENCH_ASSETS),
        "sim_bench_presets": list(SIM_BENCH_PRESETS),
        "paper_bench_pairs": list(PAPER_BENCH_PAIRS),
        "paper_bench_sources": list(PAPER_BENCH_SOURCES),
        "capital_min": CAPITAL_MIN,
        "capital_max": CAPITAL_MAX,
        "capital_start": CAPITAL_START,
        "capital_prefix": CAPITAL_PREFIX,
        "run_button_text": RUN_BUTTON_TEXT,
        "stop_button_text": STOP_BUTTON_TEXT,
        "start_button_text": START_BUTTON_TEXT,
        "remove_button_text": REMOVE_BUTTON_TEXT,
        "bench_widths": {
            "id": BENCH_ID_WIDTH_PX,
            "asset": BENCH_ASSET_WIDTH_PX,
            "preset": BENCH_PRESET_WIDTH_PX,
            "capital": BENCH_CAPITAL_WIDTH_PX,
            "sim_status": BENCH_SIM_STATUS_WIDTH_PX,
            "paper_status": BENCH_PAPER_STATUS_WIDTH_PX,
            "pnl": BENCH_PNL_WIDTH_PX,
            "price": BENCH_PRICE_WIDTH_PX,
            "source": BENCH_SOURCE_WIDTH_PX,
        },
        "bench_run_button_size": list(BENCH_RUN_BUTTON_SIZE),
        "bench_start_button_size": list(BENCH_START_BUTTON_SIZE),
        "bench_remove_button_size": list(BENCH_REMOVE_BUTTON_SIZE),
        "bench_pnl_placeholder": BENCH_PNL_PLACEHOLDER,
        "grid_cols": GRID_COLS,
        "grid_spacing": GRID_SPACING,
        "grid_margins": list(GRID_MARGINS),
        "empty_text": EMPTY_TEXT,
        "empty_style_sheet": EMPTY_STYLE_SHEET,
        "empty_alignment": EMPTY_ALIGNMENT,
        "grid_alignment": GRID_ALIGNMENT,
        "default_theme_key": DEFAULT_THEME_KEY,
        "theme_keys": list(THEME_KEYS),
        "theme_start_index": THEME_START_INDEX,
        "view_modes": list(VIEW_MODES),
        "view_list_index": VIEW_LIST_INDEX,
        "view_grid_index": VIEW_GRID_INDEX,
        "default_view_mode": DEFAULT_VIEW_MODE,
        "opacity_min_pct": OPACITY_MIN_PCT,
        "opacity_max_pct": OPACITY_MAX_PCT,
        "opacity_start_pct": OPACITY_START_PCT,
        "opacity_slider_width_px": OPACITY_SLIDER_WIDTH_PX,
        "list_row_keys": list(LIST_ROW_KEYS),
        "inflow_stat_key": INFLOW_STAT_KEY,
        "outflow_stat_key": OUTFLOW_STAT_KEY,
        "missing_amount": MISSING_AMOUNT,
        "all_exchanges_label": ALL_EXCHANGES_LABEL,
        "all_exchanges_value": ALL_EXCHANGES_VALUE,
        "revealed_glyph": REVEALED_GLYPH,
        "masked_glyph": MASKED_GLYPH,
        "privacy_dot_tooltip": PRIVACY_DOT_TOOLTIP,
        "privacy_mode_on_text": PRIVACY_MODE_ON_TEXT,
        "privacy_mode_off_text": PRIVACY_MODE_OFF_TEXT,
        "privacy_mode_tooltip": PRIVACY_MODE_TOOLTIP,
        "privacy_dot_style_sheet": PRIVACY_DOT_STYLE_SHEET,
        "broken_dot_style_sheet": BROKEN_DOT_STYLE_SHEET,
        "broken_privacy_button_style_sheet": BROKEN_PRIVACY_BUTTON_STYLE_SHEET,
        "privacy_on_style_sheet": PRIVACY_ON_STYLE_SHEET,
        "privacy_off_style_sheet": PRIVACY_OFF_STYLE_SHEET,
        "mask_unavailable_warning": MASK_UNAVAILABLE_WARNING,
        "mask_failed_warning_format": MASK_FAILED_WARNING_FORMAT,
        "privacy_unavailable_warning": PRIVACY_UNAVAILABLE_WARNING,
        "privacy_failed_warning_format": PRIVACY_FAILED_WARNING_FORMAT,
        "wire_keys": list(WIRE_KEYS),
        "start_phase": START_PHASE,
        "phase_rate": PHASE_RATE,
        "frame_interval_ms": FRAME_INTERVAL_MS,
        "bidirectional_offset_px": BIDIRECTIONAL_OFFSET_PX,
        "no_offset_px": NO_OFFSET_PX,
        "hit_threshold_px": HIT_THRESHOLD_PX,
        "hit_samples": list(HIT_SAMPLES),
        "curve_scale": CURVE_SCALE,
        "min_wire_pct": MIN_WIRE_PCT,
        "wire_pct_min": WIRE_PCT_MIN,
        "wire_pct_max": WIRE_PCT_MAX,
        "wire_pct_start": WIRE_PCT_START,
        "wire_pct_suffix": WIRE_PCT_SUFFIX,
        "short_id_length": SHORT_ID_LENGTH,
        "wire_created_topic": WIRE_CREATED_TOPIC,
        "wire_removed_topic": WIRE_REMOVED_TOPIC,
        "bot_log_topic": BOT_LOG_TOPIC,
        "bus_topics": list(BUS_TOPICS),
        "bus_emitted": list(BUS_EMITTED),
        "wire_connected_log_format": WIRE_CONNECTED_LOG_FORMAT,
        "wire_disconnected_log_format": WIRE_DISCONNECTED_LOG_FORMAT,
        "drag_onto_wired_why": DRAG_ONTO_WIRED_WHY,
        "drag_to_empty_why": DRAG_TO_EMPTY_WHY,
        "confirm_title": CONFIRM_TITLE,
        "confirm_line_format": CONFIRM_LINE_FORMAT,
        "confirm_pct_format": CONFIRM_PCT_FORMAT,
        "confirm_head_format": CONFIRM_HEAD_FORMAT,
        "confirm_plural": CONFIRM_PLURAL,
        "confirm_tail": CONFIRM_TAIL,
        "confirm_default_button": CONFIRM_DEFAULT_BUTTON,
        "confirm_unshowable_log": CONFIRM_UNSHOWABLE_LOG,
        "picker_outgoing_header": PICKER_OUTGOING_HEADER,
        "picker_incoming_header": PICKER_INCOMING_HEADER,
        "picker_outgoing_format": PICKER_OUTGOING_FORMAT,
        "picker_incoming_format": PICKER_INCOMING_FORMAT,
        "menu_cancel": MENU_CANCEL,
        "menu_separator": MENU_SEPARATOR,
        "menu_wire_header_format": MENU_WIRE_HEADER_FORMAT,
        "menu_disconnect": MENU_DISCONNECT,
        "menu_disconnect_both": MENU_DISCONNECT_BOTH,
        "menu_style_sheet": MENU_STYLE_SHEET,
        "wire_menu_style_sheet": WIRE_MENU_STYLE_SHEET,
        "wire_config_title": WIRE_CONFIG_TITLE,
        "wire_config_width_px": WIRE_CONFIG_WIDTH_PX,
        "wire_config_prompt_format": WIRE_CONFIG_PROMPT_FORMAT,
        "wire_config_row_label": WIRE_CONFIG_ROW_LABEL,
        "routes_key": ROUTES_KEY,
        "scrumming_key": SCRUMMING_KEY,
        "bots_key": BOTS_KEY,
        "dest_key": DEST_KEY,
        "pct_key": PCT_KEY,
        "hydration_shortfall_warning": HYDRATION_SHORTFALL_WARNING,
        "hydration_emitted_info": HYDRATION_EMITTED_INFO,
        "hydration_no_bus_error": HYDRATION_NO_BUS_ERROR,
        "hydration_rejected_warning": HYDRATION_REJECTED_WARNING,
        "hydration_failed_error": HYDRATION_FAILED_ERROR,
        "list_refresh_debug": LIST_REFRESH_DEBUG,
        "state_write_failed_error": STATE_WRITE_FAILED_ERROR,
        "outer_margins": list(OUTER_MARGINS),
        "outer_spacing": OUTER_SPACING,
        "viz_margins": list(VIZ_MARGINS),
        "viz_spacing": VIZ_SPACING,
        "inner_spacing": INNER_SPACING,
        "layer_margins": list(LAYER_MARGINS),
        "layer_spacing": LAYER_SPACING,
        "layer_list_margins": list(LAYER_LIST_MARGINS),
        "layer_list_spacing": LAYER_LIST_SPACING,
        "summary_spacing": SUMMARY_SPACING,
        "qt_unset_spacing": QT_UNSET_SPACING,
        "nested_margins": list(NESTED_MARGINS),
        "header_spacing": HEADER_SPACING,
        "layer_header_spacing": LAYER_HEADER_SPACING,
        "summary_margins": list(SUMMARY_MARGINS),
        "label_word_wrap": LABEL_WORD_WRAP,
        "description_word_wrap": DESCRIPTION_WORD_WRAP,
        "dot_cursor": DOT_CURSOR,
        "exchange_caption": EXCHANGE_CAPTION,
        "theme_caption": THEME_CAPTION,
        "view_caption": VIEW_CAPTION,
        "wires_caption": WIRES_CAPTION,
        "view_labels": list(VIEW_LABELS),
        "exchange_tooltip": EXCHANGE_TOOLTIP,
        "view_tooltip": VIEW_TOOLTIP,
        "opacity_tooltip": OPACITY_TOOLTIP,
        "description_style_sheet": DESCRIPTION_STYLE_SHEET,
        "scroll_style_sheet": SCROLL_STYLE_SHEET,
        "swarm_list_style_sheet": SWARM_LIST_STYLE_SHEET,
        "summary_label_style_sheet": SUMMARY_LABEL_STYLE_SHEET,
        "layer_chrome": {
            one: {
                name: (
                    [dict(each) for each in found]
                    if isinstance(found, list) and name == "buttons"
                    else (list(found) if isinstance(found, list) else found)
                )
                for name, found in chrome.items()
            }
            for one, chrome in LAYER_CHROME.items()
        },
        "actions": dict(ACTIONS),
        "signals": list(SIGNALS),
        "threads": list(THREADS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "view_mode": model.view_mode,
        "view_index": view_index(model.view_mode),
        "canvas_visible": canvas_visible(model.view_mode),
        "canvas_shown": canvas_shown_on_tab(model.tab_index, model.view_mode),
        "opacity_pct": model.opacity_pct,
        "exchange": model.exchange,
        "masked": model.masked,
        "any_masked": model.any_masked,
        "theme_key": model.grid.theme_key,
        "privacy_glyph": privacy_glyph(model.masked),
        "privacy_mode_text": model.privacy_mode_shown["text"],
        "privacy_mode_style_sheet": model.privacy_mode_shown["style_sheet"],
        "bot_ids": list(model.grid.bot_ids),
        "grid_cells": model.grid.cells(),
        "is_empty": model.grid.is_empty(),
        "empty_visible": model.grid.is_empty(),
        "exchanges": exchanges,
        "exchange_items": exchange_items(exchanges),
        "ids_in_scope": ids_in_scope(exchanges, model.exchange),
        "visible_bots": visible_bots(exchanges, model.exchange),
        "rows_sent": [[dict(one) for one in sent] for sent in model.rows_sent],
        "wires": [dict(one) for one in model.board.wires],
        "wire_count": len(model.board.wires),
        "locust_cards": locust_cards(model),
        "wire_sheet": dict(model.sheet),
        "overlay_style": dict(OVERLAY_STYLE),
        "bot_symbols": {
            bot_id: str((data or {}).get("symbol", ""))
            for bot_id, data in model.grid.bot_data.items()
        },
        "panel": dict(model.panel) if model.panel else {},
        "panel_words": dict(PANEL_WORDS),
        "drag_start_pos": list(DRAG_START_POS),
        "dragging": model.board.dragging,
        "drag_start_id": model.board.drag_start_id,
        "emitted": [list(one) for one in model.board.emitted],
        "log_lines": [list(one) for one in model.log_lines],
        "live_rows": {one: dict(found) for one, found in model.live.rows.items()},
        "sim_rows": {one: dict(found) for one, found in model.sim.rows.items()},
        "paper_rows": {one: dict(found) for one, found in model.paper.rows.items()},
        "live_row_order": list(model.live.order),
        "sim_row_order": list(model.sim.order),
        "paper_row_order": list(model.paper.order),
        "layer_signals": {
            LIVE_KIND: [dict(one) for one in model.live.signals],
            SIM_KIND: [dict(one) for one in model.sim.signals],
            PAPER_KIND: [dict(one) for one in model.paper.signals],
        },
        "sim_summary": dict(model.sim_summary_shown),
        "paper_summary": dict(model.paper_summary_shown),
        "sim_summary_start": dict(SIM_SUMMARY_START),
        "paper_summary_start": dict(PAPER_SUMMARY_START),
    }


LAYER_OF_ACTION = {
    "register_sim": SIM_KIND,
    "update_sim": SIM_KIND,
    "stop_sim": SIM_KIND,
    "register_paper": PAPER_KIND,
    "update_paper": PAPER_KIND,
    "stop_paper": PAPER_KIND,
    "register_live": LIVE_KIND,
    "update_live": LIVE_KIND,
    "stop_live": LIVE_KIND,
}


def apply_action(model: BotVisualizerModel, params: dict) -> dict:
    """Apply one ``action`` from ``params`` to ``model`` and return its payload.

    ``view_model`` and the Qt-hosted React tab both dispatch through here,
    so a screen served over the bridge and a screen drawn in the window
    take the same action by the same code.
    """
    action = params.get("action", "")
    kind = LAYER_OF_ACTION.get(action)
    if kind is not None:
        layer = model.layer(kind)
        run_id = params.get("run_id", "")
        if action.startswith("register"):
            layer.register(run_id, params.get("label", ""), params.get("cfg") or {})
        elif action.startswith("update"):
            layer.update(
                run_id,
                pnl=params.get("pnl", DEFAULT_PNL),
                trades=params.get("trades", 0),
                candle_idx=params.get("candle_idx", 0),
                price=params.get("price"),
                status=params.get("status"),
            )
        else:
            layer.stop(
                run_id,
                pnl=params.get("pnl", DEFAULT_PNL),
                trades=params.get("trades", 0),
            )
    elif action == "update_bots":
        model.update_bots(params.get("bot_statuses") or [])
    elif action == "wire_created":
        model.board.on_created(params.get("event") or {})
    elif action == "wire_removed":
        model.board.on_removed(params.get("event") or {})
    elif action == "remove_wire":
        model.board.remove(params.get("source_id", ""), params.get("target_id", ""))
    elif action == "animate":
        model.board.advance(float(params.get("dt", 0.0)))
    elif action == "set_view_mode":
        model.view_mode = str(params.get("mode", DEFAULT_VIEW_MODE))
    elif action == "set_opacity":
        model.opacity_pct = int(params.get("pct", OPACITY_START_PCT))
    elif action == "set_exchange":
        model.set_exchange(str(params.get("exchange", ALL_EXCHANGES_VALUE)))
    elif action == "set_theme":
        model.grid.set_theme(str(params.get("theme_key", DEFAULT_THEME_KEY)))
    elif action == "set_masked":
        model.toggle_identifier_mask(params.get("masked"))
    elif action == "toggle_privacy_mode":
        model.toggle_privacy_mode()
    elif action == "wire_sheet":
        model.sheet = wire_sheet(model, params.get("boxes"))
    elif action == "finish_drag":
        model.finish_drag(
            str(params.get("source_id", "")), str(params.get("target_id", ""))
        )
    elif action == "answer_panel":
        model.answer_panel(
            str(params.get("choice", PANEL_CANCEL)),
            pct=params.get("pct"),
            entry=params.get("entry"),
        )
    elif action == "hydrate":
        model.hydrate(params.get("state") or {})
    return build_payload(model)


def view_model(params: dict) -> dict:
    """Bridge handler for ``bot_visualizer.state``.

    Reads ``reset`` and one ``action``. The rows, the wires and the
    fleet persist between calls because the screen's own state does;
    ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = BotVisualizerModel()
    return apply_action(PANE_MODEL, params)
