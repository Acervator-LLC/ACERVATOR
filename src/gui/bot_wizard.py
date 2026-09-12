"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
bot_wizard.py - Bot Creation Wizard v1.9.7
===========================================
Feature split:
  Grid Bot: Investment Amount, Position Count/Distance/Increment,
            Profit Folding, Upward Distribution, Extended Positions
  Accumulation Bot: Target Balance, Scrumming Interval, TA Engine, Phantoms
  Both: Visibility, Aggressive Trading, Bulk Trading (when Aggressive on)
"""

from __future__ import annotations
import logging
from typing import Optional

from . import design_system as ds

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWizard,
        QWizardPage,
        QVBoxLayout,
        QHBoxLayout,
        QFormLayout,
        QLabel,
        QLineEdit,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox,
        QCheckBox,
        QRadioButton,
        QGroupBox,
        QPushButton,
        QScrollArea,
        QWidget,
    )
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

    _HAS_QT = True
except ImportError:
    _HAS_QT = False
from src.gui.qt_safe_events import safe_process_events
from src.exchange.lazy_singleton import LazySingleton, ThrottledFault


def _market_text(value) -> str:
    """The text one market row carries, empty where it carries no text."""
    return value if type(value) is str else ""


def _market_number(value):
    """The number one market row carries, nothing where it carries no number."""
    return float(value) if type(value) in (int, float) else None


def _build_asset_manager():
    """Construct the AssetManager. Import deferred to keep GUI imports cheap."""
    from src.exchange.crypto_assets import AssetManager

    return AssetManager()


_ASSET_MANAGER = LazySingleton(
    _build_asset_manager,
    "coin icons",
    "Every asset row will show a lettered circle instead of its logo.",
)

_ICON_LOAD_FAULT = ThrottledFault(
    "coin icon loading",
    "Assets whose logo cannot be read will show a lettered circle.",
)


def _get_coin_icon(
    symbol: str, size: int = 20, download: bool = True
) -> Optional["QIcon"]:
    """Get coin logo as QIcon — cached file or generated fallback.

    Returns None when PySide6 is absent, because there is no QIcon type
    to build. All three callers already read the result as optional and
    fall back to a text-only row: AssetSelectionPage._filter_assets in
    this module, and update_bots in main_window's BotStatusTable and
    ExtractorBotTable. Each guards with `if icon:`. The annotation now
    says what the function does.

    Set download=False to avoid network calls on UI thread.
    """
    if not _HAS_QT:
        return None
    mgr = _ASSET_MANAGER.get()
    if mgr is not None:
        try:
            path = mgr.get_logo_path(symbol)
            if not path and download:
                path = mgr.download_logo(symbol)
            if path and path.exists():
                px = QPixmap(str(path))
                if not px.isNull():
                    _ICON_LOAD_FAULT.note_success()
                    return QIcon(
                        px.scaled(
                            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
        except Exception as _icon_exc:  # noqa: BLE001 - GUI fallback path
            _ICON_LOAD_FAULT.note_failure(_icon_exc)
    px = QPixmap(size, size)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    h = sum(ord(c) for c in symbol) % 360
    p.setBrush(QColor.fromHsv(h, 120, 180))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Segoe UI", int(size * 0.45), QFont.Bold))
    from PySide6.QtCore import QRectF

    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, symbol[0])
    p.end()
    return QIcon(px)


if _HAS_QT:

    PAGE_ASSET = 0
    PAGE_MODE = 1
    PAGE_PARAMS = 2
    PAGE_FOLDING = 3
    PAGE_PHANTOM = 4
    PAGE_EXTRACTOR_POOL = 5

    class AssetSelectionPage(QWizardPage):
        def __init__(self, exchanges: list[dict], parent=None):
            super().__init__(parent)
            self.setTitle("Select Asset Pair")
            self.setSubTitle("Choose the exchange and trading pair.")
            self._exchanges = exchanges
            form = QFormLayout(self)

            self._exchange = QComboBox()
            for exch in exchanges:
                eid = _market_text(exch.get("exchange_id"))
                self._exchange.addItem(exch.get("display_name", eid), eid)
            self._exchange.currentIndexChanged.connect(self._on_exchange_changed)
            form.addRow("Exchange:", self._exchange)

            self._base = QComboBox()
            self._base.addItems(["USDT", "USDC", "BTC", "ETH", "BNB", "EUR", "USD"])
            self._base.currentIndexChanged.connect(self._filter_assets)
            form.addRow("Base Currency:", self._base)

            target_row = QHBoxLayout()
            self._target = QComboBox()
            self._target.setMinimumWidth(400)
            self._target.setIconSize(QSize(20, 20))
            self._target.currentIndexChanged.connect(self._update_info)
            target_row.addWidget(self._target, stretch=1)
            self._info_btn = QPushButton(" ℹ ")
            self._info_btn.setStyleSheet(
                f"color: {ds.FOLD_SOURCE_MANUAL}; font-weight: bold; "
                f"border: 1px solid {ds.FOLD_SOURCE_MANUAL}; "
                "border-radius: 10px; padding: 2px 6px; margin-left: 4px; "
                "max-width: 28px;"
            )
            self._info_btn.clicked.connect(self._show_info)
            target_row.addWidget(self._info_btn)
            form.addRow("Target Asset:", target_row)

            self._status = QLabel("")
            self._status.setWordWrap(True)
            form.addRow(self._status)
            self._markets_cache: dict = {}
            self._descriptions_cache: dict = {}
            try:
                from src.exchange.crypto_assets import ASSETS

                for sym, a in ASSETS.items():
                    parts = [a.description or a.name]
                    if a.consensus:
                        parts.append(f"Consensus: {a.consensus}")
                    if a.launch_year:
                        parts.append(f"Launched: {a.launch_year}")
                    if a.category:
                        parts.append(f"Category: {a.category}")
                    self._descriptions_cache[sym] = f"{a.name} ({sym})\n" + "\n".join(
                        parts
                    )
            except Exception as _desc_exc:  # noqa: BLE001 - asset cache best-effort
                logger.debug("asset description cache failed: %s", _desc_exc)
            if exchanges:
                self._on_exchange_changed()

        def _on_exchange_changed(self):
            eid = self._exchange.currentData()
            if not eid:
                return
            self._status.setText(f"Loading from {eid.capitalize()}...")
            self._status.repaint()
            safe_process_events("legacy P4.1 site")
            if eid not in self._markets_cache:
                try:
                    self._markets_cache[eid] = self._fetch_markets(eid)
                except Exception as exc:
                    self._status.setText(f"Failed to load markets: {str(exc)[:50]}")
                    self._markets_cache[eid] = []
            self._filter_assets()

        def _fetch_markets(self, exchange_id):
            try:
                import ccxt as ccxt_sync
                from src.exchange.ccxt_connector import (
                    CCXTConnector,
                    EXCHANGE_OPTIONS,
                    DISABLE_FETCH_CURRENCIES,
                )

                conn = CCXTConnector(exchange_id)
                cls = getattr(ccxt_sync, conn._ccxt_id)
                cfg = {"enableRateLimit": True, "timeout": 15000}
                opts = EXCHANGE_OPTIONS.get(exchange_id)
                if opts:
                    cfg["options"] = dict(opts)
                exch = cls(cfg)
                if exchange_id in DISABLE_FETCH_CURRENCIES:
                    exch.has["fetchCurrencies"] = False
                exch.load_markets()
                markets = []
                for sym, info in exch.markets.items():
                    if (
                        not info.get("active", True)
                        or info.get("type", "spot") != "spot"
                    ):
                        continue
                    b, q = info.get("base", ""), info.get("quote", "")
                    if b and q:
                        markets.append(
                            {
                                "symbol": sym,
                                "base": b,
                                "quote": q,
                                "volume": 0,
                                "volatility": 0,
                            }
                        )
                try:
                    tickers = exch.fetch_tickers()
                    for m in markets:
                        t = tickers.get(m["symbol"], {})
                        m["volume"] = float(t.get("quoteVolume", 0) or 0)
                        h, l, c = (
                            float(t.get("high", 0) or 0),
                            float(t.get("low", 0) or 0),
                            float(t.get("last", 0) or 0),
                        )
                        if c > 0:
                            m["volatility"] = round((h - l) / c * 100, 2)
                except Exception as _vol_exc:
                    logger.warning(
                        "bot_wizard: ticker/volatility enrichment "
                        "for %s failed (%s): %s — markets returned "
                        "without volume/volatility metrics",
                        exchange_id,
                        type(_vol_exc).__name__,
                        _vol_exc,
                    )
                return markets
            except Exception as exc:
                logger.warning("Market fetch failed for %s: %s", exchange_id, exc)
                try:
                    from src.exchange.crypto_assets import ASSETS

                    return [
                        {
                            "symbol": f"{s}/USDT",
                            "base": s,
                            "quote": "USDT",
                            "volume": 0,
                            "volatility": 0,
                        }
                        for s in sorted(ASSETS)
                    ]
                except Exception:
                    return []

        def _filter_assets(self):
            eid = self._exchange.currentData()
            base = self._base.currentText().strip().upper()
            markets = self._markets_cache.get(eid, [])
            self._target.clear()
            filtered = [
                m
                for m in markets
                if m.get("quote") == base and _market_text(m.get("base"))
            ]
            # Cached volume only, since a network fetch here blocks the GUI thread.
            filtered.sort(
                key=lambda m: _market_number(m.get("volume")) or 0.0, reverse=True
            )
            for m in filtered:
                vol = _market_number(m.get("volume"))
                vol_s = ""
                if vol is not None:
                    vol_s = (
                        f"${vol/1e9:.1f}B"
                        if vol >= 1e9
                        else (
                            f"${vol/1e6:.1f}M"
                            if vol >= 1e6
                            else f"${vol/1e3:.0f}K" if vol >= 1e3 else ""
                        )
                    )
                parts = [f"Vol: {vol_s}"] if vol_s else []
                if m.get("volatility", 0) > 0:
                    parts.append(f"Volat: {m['volatility']:.1f}%")
                named = _market_text(m.get("base"))
                label = named + (f"  ({', '.join(parts)})" if parts else "")
                # The cached icon only, since a download here blocks the GUI thread.
                icon = _get_coin_icon(named, download=False)
                if icon:
                    self._target.addItem(icon, label, named)
                else:
                    self._target.addItem(label, named)
            if not filtered:
                self._target.addItem("No pairs found", "")
            self._status.setText(
                f"{len(filtered)} {base} pairs"
                + (
                    " (sorted by volume)"
                    if any(
                        (_market_number(m.get("volume")) or 0.0) > 0 for m in filtered
                    )
                    else ""
                )
            )
            self._update_info()

        def _update_info(self):
            sym = self._target.currentData()
            desc = self._descriptions_cache.get(sym, "")
            self._info_btn.setToolTip(desc or f"No info available for {sym}")

        def _show_info(self):
            """Show asset description popup on (i) click."""
            sym = self._target.currentData()
            if not sym:
                return
            desc = self._descriptions_cache.get(sym, "")
            if not desc:
                desc = f"{sym}\nNo detailed description available for this asset."
            from PySide6.QtWidgets import QMessageBox

            msg = QMessageBox(self)
            msg.setWindowTitle(f"Asset Info — {sym}")
            msg.setText(desc)
            msg.setIcon(QMessageBox.Information)
            msg.exec()

        def get_config(self):
            return {
                "exchange_id": self._exchange.currentData(),
                "base_currency": self._base.currentText().strip().upper(),
                "target_asset": self._target.currentData() or "",
            }

    class ModeSelectionPage(QWizardPage):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setTitle("Trading Mode")
            self.setSubTitle("Select the trading engine for this bot.")
            layout = QVBoxLayout(self)
            self._scrumming = QRadioButton("Accumulation Trading (Scrumming)")
            self._scrumming.setChecked(True)
            sd = QLabel(
                "The core trading engine. Uses 12-indicator TA voting to optimize "
                "scrum-fold cycles relative to a Target Balance. Supports multi-timeframe "
                "Phantom Balance coordination, Landing Strip detection, MR Inspector "
                "Boosted Fold, and Smart Wire cross-compounding."
            )
            sd.setWordWrap(True)
            sd.setProperty("muted", True)
            layout.addWidget(self._scrumming)
            layout.addWidget(sd)

            self._extractor = QRadioButton("Base Currency Extractor (Multi-Target)")
            self._extractor.setToolTip(
                "Grows a base-currency pool by harvesting volatility across "
                "top-N */<base> alt pairs. No spawn cascades, no phantoms; "
                "per-position Manual Fire in the detail dialog."
            )
            ed = QLabel(
                "Grows a base-currency pool by extracting volatility from "
                "top-N */<base> alt pairs. Fires small artillery rounds into "
                "bearish alt signals; closes on bullish signals only if the "
                "exit nets MORE base units than it started with (double-layer "
                "valuation). Multi-pair by design — no spawn cascades, no "
                "phantoms. Per-position Manual Fire in the bot's detail "
                "dialog (Positions Held tab)."
            )
            ed.setWordWrap(True)
            ed.setProperty("muted", True)
            layout.addWidget(self._extractor)
            layout.addWidget(ed)
            layout.addStretch()

        def is_grid(self):
            return False  # Grid Bot deprecated

        def is_extractor(self) -> bool:
            """v3.19.3 — True if the operator selected the Extractor
            radio. Consumed by TradingParamsPage.set_mode() to swap
            the form's visible widgets, and by BotCreationWizard.nextId()
            + get_config() to route the wizard properly."""
            return self._extractor.isChecked()

    class ExtractorPoolPage(QWizardPage):
        # The asset the pool accumulates into. Alts trade against it.
        _POOL_BASES = ["BTC", "ETH", "USDT", "USDC", "BNB"]

        def __init__(self, exchanges: list[dict], parent=None) -> None:
            super().__init__(parent)
            self.setTitle("Extractor Pool")
            self.setSubTitle(
                "Choose the base currency the pool accumulates and "
                "select target alt pairs from the exchange scan. "
                "Leave all unchecked to use auto-scan (top-N by volume)."
            )
            self._exchanges = exchanges
            self._markets_cache: dict = {}

            outer = QVBoxLayout(self)
            form = QFormLayout()

            self._exchange = QComboBox()
            for exch in exchanges:
                eid = _market_text(exch.get("exchange_id"))
                self._exchange.addItem(exch.get("display_name", eid), eid)
            self._exchange.currentIndexChanged.connect(self._on_exchange_changed)
            self._exchange.setToolTip(
                "Exchange this pool trades on. Changing it re-scans that "
                "exchange for tradable pairs."
            )
            form.addRow("Exchange:", self._exchange)

            self._base = QComboBox()
            self._base.addItems(self._POOL_BASES)
            self._base.currentIndexChanged.connect(self._refresh_alt_list)
            self._base.setToolTip(
                "The asset this pool accumulates. The list below shows the "
                "alts that trade against it."
            )
            form.addRow("Pool Base Currency:", self._base)
            outer.addLayout(form)

            self._status = QLabel("")
            self._status.setWordWrap(True)
            outer.addWidget(self._status)

            outer.addWidget(QLabel("Target alt pairs (multi-select):"))
            from PySide6.QtWidgets import QListWidget

            self._alt_list = QListWidget()
            self._alt_list.setSelectionMode(QListWidget.NoSelection)
            # 10-50 alt pairs typical.
            self._alt_list.setMinimumHeight(280)
            self._alt_list.setAccessibleName("Target alt pairs")
            self._alt_list.setToolTip(
                "Tick the alt pairs this Extractor may hunt. Leave every "
                "box clear and it auto-scans the top-N by 24h volume."
            )
            outer.addWidget(self._alt_list)

            btn_row = QHBoxLayout()
            self._btn_all = QPushButton("Select all")
            self._btn_all.clicked.connect(self._select_all)
            self._btn_all.setToolTip("Tick every alt pair in the list.")
            self._btn_none = QPushButton("Clear")
            self._btn_none.clicked.connect(self._clear_all)
            self._btn_none.setToolTip("Clear every tick. No ticks means auto-scan.")
            btn_row.addWidget(self._btn_all)
            btn_row.addWidget(self._btn_none)
            btn_row.addStretch()
            outer.addLayout(btn_row)

            if exchanges:
                self._on_exchange_changed()

        def _on_exchange_changed(self) -> None:
            eid = self._exchange.currentData()
            if not eid:
                return
            self._status.setText(f"Loading {eid.capitalize()} markets...")
            self._status.repaint()
            safe_process_events("legacy P4.1 site")
            if eid not in self._markets_cache:
                try:
                    self._markets_cache[eid] = self._fetch_markets(eid)
                except Exception as exc:
                    self._status.setText(f"Failed to load markets: {str(exc)[:50]}")
                    self._markets_cache[eid] = []
            self._refresh_alt_list()

        def _fetch_markets(self, exchange_id: str) -> list[dict]:
            """Reuse the same ccxt-based market scan AssetSelectionPage
            uses. Returns list of {symbol, base, quote, volume}."""
            try:
                import ccxt as ccxt_sync
                from src.exchange.ccxt_connector import (
                    CCXTConnector,
                    EXCHANGE_OPTIONS,
                    DISABLE_FETCH_CURRENCIES,
                )

                conn = CCXTConnector(exchange_id)
                cls = getattr(ccxt_sync, conn._ccxt_id)
                cfg = {"enableRateLimit": True, "timeout": 15000}
                opts = EXCHANGE_OPTIONS.get(exchange_id)
                if opts:
                    cfg["options"] = dict(opts)
                exch = cls(cfg)
                if exchange_id in DISABLE_FETCH_CURRENCIES:
                    exch.has["fetchCurrencies"] = False
                exch.load_markets()
                markets = []
                for sym, info in exch.markets.items():
                    if not info.get("active", True):
                        continue
                    if info.get("type", "spot") != "spot":
                        continue
                    b = info.get("base", "")
                    q = info.get("quote", "")
                    if b and q:
                        markets.append(
                            {"symbol": sym, "base": b, "quote": q, "volume": 0.0}
                        )
                try:
                    tickers = exch.fetch_tickers()
                    for m in markets:
                        t = tickers.get(m["symbol"], {})
                        m["volume"] = float(t.get("quoteVolume", 0) or 0)
                except Exception as _vol_exc:
                    logger.warning(
                        "bot_wizard ExtractorPool: ticker fetch failed "
                        "for %s (%s): %s",
                        exchange_id,
                        type(_vol_exc).__name__,
                        _vol_exc,
                    )
                return markets
            except Exception as exc:
                logger.warning(
                    "ExtractorPool market fetch failed for %s: %s", exchange_id, exc
                )
                return []

        def _refresh_alt_list(self) -> None:
            """Repopulate the multi-select with all alts available
            against the currently-selected base."""
            from PySide6.QtWidgets import QListWidgetItem

            eid = self._exchange.currentData()
            base = self._base.currentText().strip().upper()
            markets = self._markets_cache.get(eid, [])
            self._alt_list.clear()
            filtered = [
                m
                for m in markets
                if m.get("quote") == base
                and _market_text(m.get("base"))
                and _market_text(m.get("symbol"))
            ]
            # Descending volume matches the auto-scan top-N order.
            filtered.sort(
                key=lambda m: _market_number(m.get("volume")) or 0.0, reverse=True
            )
            for m in filtered:
                vol = _market_number(m.get("volume"))
                if vol is None:
                    vol_s = ""
                elif vol >= 1e9:
                    vol_s = f"${vol/1e9:.1f}B"
                elif vol >= 1e6:
                    vol_s = f"${vol/1e6:.1f}M"
                elif vol >= 1e3:
                    vol_s = f"${vol/1e3:.0f}K"
                else:
                    vol_s = ""
                named = _market_text(m.get("base"))
                label = f"{named}  ({vol_s})" if vol_s else named
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, _market_text(m.get("symbol")))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self._alt_list.addItem(item)
            self._status.setText(
                f"{len(filtered)} */{base} pairs available "
                f"(sorted by 24h volume). Leave all unchecked for "
                f"auto-scan (top-N by volume)."
            )

        def _select_all(self) -> None:
            for i in range(self._alt_list.count()):
                self._alt_list.item(i).setCheckState(Qt.Checked)

        def _clear_all(self) -> None:
            for i in range(self._alt_list.count()):
                self._alt_list.item(i).setCheckState(Qt.Unchecked)

        def get_config(self) -> dict:
            """Returns the wizard's extractor-pool selection.

            Output shape:
              exchange_id (str): selected exchange id
              base_currency (str): the pool's base (which asset is accumulated)
              target_asset (str): convention placeholder — Extractor uses
                a pool of alts rather than a single target. Set to the
                first selected alt for downstream symbol-construction
                compatibility, or to base itself if no alts selected
                (the auto-scan will run at runtime).
              extractor_alt_targets (list[str]): operator-selected alt
                symbols. Empty = auto-scan top-N at runtime.
            """
            checked: list[str] = []
            for i in range(self._alt_list.count()):
                item = self._alt_list.item(i)
                if item.checkState() == Qt.Checked:
                    sym = item.data(Qt.UserRole)
                    if sym:
                        checked.append(sym)
            base = self._base.currentText().strip().upper()
            return {
                "exchange_id": self._exchange.currentData(),
                "base_currency": base,
                "target_asset": "*",  # pool sigil — multi-pair indicator
                "extractor_alt_targets": checked,
            }

    class TradingParamsPage(QWizardPage):
        def __init__(self, defaults: dict, parent=None):
            super().__init__(parent)
            self.setTitle("Trading Parameters")
            self._is_grid = False
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self._scroll = QScrollArea(self)
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QScrollArea.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            inner = QWidget()
            self._scroll.setWidget(inner)
            outer.addWidget(self._scroll)
            groups = QVBoxLayout(inner)
            groups.setContentsMargins(12, 12, 12, 12)
            groups.setSpacing(10)

            def _mkform():
                f = QFormLayout()
                f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
                f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
                f.setHorizontalSpacing(18)
                f.setVerticalSpacing(8)
                return f

            self._mode_group = QGroupBox("Trading Parameters")
            mf = _mkform()
            self._mode_group.setLayout(mf)

            self._visibility = QComboBox()
            self._visibility.addItem("Order Book (Visible)", "orderbook")
            self._visibility.addItem("Internal (Invisible)", "internal")
            # defaults carries the stored bot_visibility; findData refuses a name
            # the two items do not offer, leaving the box on orderbook.
            _vis_at = self._visibility.findData(
                defaults.get("bot_visibility", "orderbook")
            )
            if _vis_at >= 0:
                self._visibility.setCurrentIndex(_vis_at)
            self._visibility.setToolTip("How orders appear on the exchange.")
            self._visibility.currentIndexChanged.connect(self._on_visibility_changed)
            mf.addRow("Order Visibility:", self._visibility)

            self._aggressive = QCheckBox("Aggressive Trading (force IOC-limit takers)")
            # defaults carries the stored aggressive_trading, admitted the way
            # the Settings dialog's own load row admits it.
            self._aggressive.setChecked(bool(defaults.get("aggressive_trading", False)))
            self._aggressive.setToolTip(
                "When ON, every engine-initiated buy/sell executes as "
                "an Immediate-Or-Cancel limit order priced through "
                "the spread — i.e., pays the taker fee for immediate "
                "fill. When OFF, the bot may use passive maker orders "
                "where appropriate. Manual fire is unaffected."
            )
            mf.addRow(self._aggressive)

            from ..trading.bot_container import STACK_MODE_DEFAULT

            self._stack_mode = QCheckBox(
                "Stack Mode (split SCRUM across upward tranches)"
            )
            # One declaration, so the box and the config cannot disagree.
            self._stack_mode.setChecked(STACK_MODE_DEFAULT)
            self._stack_mode.setToolTip(
                "When ON, a SCRUM fires as N Stack Tranches at "
                "ascending price levels instead of a single sell. "
                "First tranche at the Minimum Opposing Trade Distance "
                "(opposing hysteresis level); successive tranches "
                "spaced by Split Distance per the Spacing model. "
                "Visibility gates book placement: orderbook = resting "
                "limits; internal = tracked off-books, market-fire on "
                "threshold cross."
            )
            mf.addRow(self._stack_mode)

            self._split_distance = QDoubleSpinBox()
            self._split_distance.setRange(0.1, 20.0)
            self._split_distance.setDecimals(2)
            self._split_distance.setSuffix(" %")
            self._split_distance.setValue(1.0)
            self._split_distance.setToolTip(
                "Percent spacing between successive Stack tranches. "
                "Applied per Spacing mode: Linear = constant delta, "
                "Quadratic = arithmetically-growing delta, "
                "Exponential = geometrically-growing delta."
            )
            mf.addRow("Split Distance:", self._split_distance)

            self._stack_count = QSpinBox()
            self._stack_count.setRange(2, 20)
            self._stack_count.setValue(3)
            self._stack_count.setToolTip(
                "Target number of Stack tranches to create from a "
                "SCRUM. Actual runtime count may be lower if "
                "per-tranche size falls below the exchange minimum, "
                "or two computed tranche prices land within 0.1% of "
                "each other (then merged upwards)."
            )
            mf.addRow("Tranche Count:", self._stack_count)

            self._stack_spacing = QComboBox()
            self._stack_spacing.addItem("Linear (1, 2, 3, 4…)", "linear")
            self._stack_spacing.addItem("Quadratic (1, 2, 4, 7…)", "quadratic")
            self._stack_spacing.addItem("Exponential (1, 2, 4, 8…)", "exponential")
            self._stack_spacing.setToolTip(
                "Spacing model for successive Stack tranches. The "
                "sequences show Δp in units of Split Distance between "
                "consecutive tranches."
            )
            mf.addRow("Spacing:", self._stack_spacing)

            self._personal_hold_qty = QDoubleSpinBox()
            self._personal_hold_qty.setRange(0.0, 1_000_000_000.0)
            self._personal_hold_qty.setDecimals(10)
            self._personal_hold_qty.setValue(0.0)
            self._personal_hold_qty.setToolTip(
                "Target-asset units to hold OUT of the bot's view "
                "(personal reserve). The bot won't buy or sell these "
                "units; they're also reserved from any sibling bot on "
                "the same asset. Leave at 0 unless you want the bot "
                "to ignore a personal stash on the exchange."
            )
            mf.addRow("Personal Hold (units):", self._personal_hold_qty)

            groups.addWidget(self._mode_group)

            self._scrum_group = QGroupBox("Scrumming Settings")
            sf = _mkform()
            self._scrum_group.setLayout(sf)

            self._scrumming_interval = QDoubleSpinBox()
            self._scrumming_interval.setRange(0.1, 20.0)
            self._scrumming_interval.setDecimals(2)
            self._scrumming_interval.setSuffix(" %")
            self._scrumming_interval.setValue(1.0)
            self._scrumming_interval.setToolTip(
                "Minimum market move before the bot takes action."
            )
            sf.addRow("Opposing Trade Interval:", self._scrumming_interval)

            self._bb_tolerance = QDoubleSpinBox()
            self._bb_tolerance.setRange(0.25, 5.0)
            self._bb_tolerance.setDecimals(2)
            self._bb_tolerance.setSuffix(" %")
            self._bb_tolerance.setValue(1.0)
            self._bb_tolerance.setToolTip(
                "Bollinger Band proximity tolerance for Landing Strip."
            )
            sf.addRow("BB Tolerance:", self._bb_tolerance)

            self._ls_candles = QSpinBox()
            self._ls_candles.setRange(2, 10)
            self._ls_candles.setValue(3)
            self._ls_candles.setSuffix(" candles")
            self._ls_candles.setToolTip(
                "Min consecutive tight Heikin Ashi candles near a "
                "Bollinger Band to confirm a Landing Strip pattern."
            )
            sf.addRow("Landing Strip Candles:", self._ls_candles)

            self._ta_timeframe = QComboBox()
            for _tf in ("1m", "5m", "15m", "30m", "1h", "4h", "1d"):
                self._ta_timeframe.addItem(_tf, _tf)
            self._ta_timeframe.setCurrentIndex(4)  # Default 1h
            self._ta_timeframe.setToolTip(
                "Timeframe for TA indicator calculations. Filtered "
                "against exchange support at set_exchange_id() time. "
                "Shorter = more responsive; longer = smoother signals."
            )
            sf.addRow("TA Timeframe:", self._ta_timeframe)

            self._target_balance = QDoubleSpinBox()
            self._target_balance.setRange(1.0, 1000000.0)
            self._target_balance.setDecimals(2)
            self._target_balance.setPrefix("$ ")
            self._target_balance.setValue(defaults.get("default_target_balance", 200.0))
            self._target_balance.setToolTip(
                "The balance this bot trades relative to. HARD-CAPPED: "
                "position can never exceed Target × (1 + Max Target "
                "Growth %/100). MEM-246/249/251."
            )
            sf.addRow("Target Balance:", self._target_balance)

            self._max_entry_px = QDoubleSpinBox()
            self._max_entry_px.setRange(0.0, 10_000_000.0)
            self._max_entry_px.setDecimals(8)
            self._max_entry_px.setPrefix("$ ")
            self._max_entry_px.setValue(0.0)
            self._max_entry_px.setToolTip(
                "Bot REFUSES any auto-buy when current price is ABOVE "
                "this. 0 = no ceiling (default). Manual Fire bypasses "
                "this gate."
            )
            sf.addRow("Max Entry Price:", self._max_entry_px)

            self._min_entry_px = QDoubleSpinBox()
            self._min_entry_px.setRange(0.0, 10_000_000.0)
            self._min_entry_px.setDecimals(8)
            self._min_entry_px.setPrefix("$ ")
            self._min_entry_px.setValue(0.0)
            self._min_entry_px.setToolTip(
                "Bot REFUSES any auto-buy when current price is BELOW "
                "this. 0 = no floor (default). Manual Fire bypasses "
                "this gate."
            )
            sf.addRow("Min Entry Price:", self._min_entry_px)

            self._trading_fee = QDoubleSpinBox()
            self._trading_fee.setRange(0.0, 5.0)
            self._trading_fee.setSuffix(" %")
            self._trading_fee.setDecimals(2)
            self._trading_fee.setSingleStep(0.05)
            self._trading_fee.setValue(0.6)
            self._trading_fee.setToolTip(
                "Coinbase trading fee tier (per side). The opposite-"
                "direction hysteresis safety adds this to the scrum "
                "interval — bot will not flip BUY↔SELL until price "
                "moves ≥ (interval + fee)% in the opposing direction. "
                "0.6 % = Coinbase Advanced Trade max-tier default."
            )
            sf.addRow("Trading Fee %:", self._trading_fee)

            self._max_target_growth_pct = QDoubleSpinBox()
            self._max_target_growth_pct.setRange(0.0, 100.0)
            self._max_target_growth_pct.setSuffix(" %")
            self._max_target_growth_pct.setDecimals(2)
            self._max_target_growth_pct.setSingleStep(0.25)
            self._max_target_growth_pct.setValue(1.0)
            self._max_target_growth_pct.setToolTip(
                "Per-event cap on how much a fold surplus may grow "
                "Target Balance.\nAbsolute ceiling = Target × (1 + "
                "this%/100). Default 1%.\nTHIS IS THE ONLY MECHANISM "
                "ALLOWED TO INCREASE TARGET BALANCE.\nSet to 0% to "
                "freeze Target Balance entirely."
            )
            sf.addRow("Max Target Growth %:", self._max_target_growth_pct)

            self._scrum_fold_pct = QSpinBox()
            self._scrum_fold_pct.setRange(1, 100)
            self._scrum_fold_pct.setValue(100)
            self._scrum_fold_pct.setSuffix(" %")
            self._scrum_fold_pct.setToolTip(
                "% of scrum sale proceeds queued for fold (rebuy).\n"
                "100 % = full reentry (max accumulation, max risk).\n"
                "Lower values preserve cash buffer — safer when price "
                "keeps falling after the scrum."
            )
            sf.addRow("Scrum Fold Ratio:", self._scrum_fold_pct)

            groups.addWidget(self._scrum_group)

            self._adv_group = QGroupBox("Advanced Scrumming (P1.9)")
            af = _mkform()
            self._adv_group.setLayout(af)

            self._scrum_detect_pct = QSpinBox()
            self._scrum_detect_pct.setRange(10, 90)
            self._scrum_detect_pct.setSuffix(" %")
            self._scrum_detect_pct.setValue(75)
            self._scrum_detect_pct.setToolTip(
                "BB DETECT threshold: % distance from BB midline to "
                "band before SEARCH→TRACK. Lower = earlier detection. "
                "v3.15.57 HARD GATE: SCRUM cannot occur below the "
                "Upper BB Detection Threshold; FOLD cannot occur "
                "above the Lower BB Detection Threshold. 75 % → "
                "upper gate at bb_pos ≥ 0.875, lower gate at "
                "bb_pos ≤ 0.125."
            )
            af.addRow("Detect Threshold:", self._scrum_detect_pct)

            self._scrum_fire_pct = QDoubleSpinBox()
            self._scrum_fire_pct.setRange(0.1, 10.0)
            self._scrum_fire_pct.setDecimals(2)
            self._scrum_fire_pct.setSuffix(" %")
            self._scrum_fire_pct.setValue(0.5)
            self._scrum_fire_pct.setToolTip(
                "FIRE threshold: % distance from BB band to trigger " "trade."
            )
            af.addRow("Fire Threshold:", self._scrum_fire_pct)

            self._bb_midline_gate = QCheckBox("BB Midline Gate")
            self._bb_midline_gate.setChecked(True)
            self._bb_midline_gate.setToolTip(
                "When enabled: scrums ONLY fire above BB midline, "
                "folds ONLY fire below midline (sell-high/buy-low)."
            )
            af.addRow(self._bb_midline_gate)

            self._scrum_read_rate = QSpinBox()
            self._scrum_read_rate.setRange(1, 60)
            self._scrum_read_rate.setSuffix(" min")
            self._scrum_read_rate.setValue(5)
            self._scrum_read_rate.setToolTip(
                "SEARCH-mode read rate in minutes. TRACK mode reads " "10x faster."
            )
            af.addRow("Read Rate:", self._scrum_read_rate)

            self._band_travel_pct = QSpinBox()
            self._band_travel_pct.setRange(0, 100)
            self._band_travel_pct.setSuffix(" %")
            self._band_travel_pct.setValue(70)
            self._band_travel_pct.setToolTip(
                "Secondary harvest trigger: % of BB band width price "
                "must travel since last fold. 0 disables."
            )
            af.addRow("Band Travel:", self._band_travel_pct)

            self._bb_bullseye = QCheckBox("BB Bullseye Check")
            self._bb_bullseye.setChecked(True)
            self._bb_bullseye.setToolTip(
                "Rapid Fire override when price touches BB band "
                "within 0.5 % (or the candle wick reaches within "
                "0.2 %). When triggered, bypasses the fire threshold "
                "— bullseye alone can arm a fire, subject to midline "
                "gate."
            )
            af.addRow(self._bb_bullseye)

            self._wire_inflow_stack_pct = QDoubleSpinBox()
            self._wire_inflow_stack_pct.setRange(0.0, 100.0)
            self._wire_inflow_stack_pct.setDecimals(2)
            self._wire_inflow_stack_pct.setSuffix(" %")
            self._wire_inflow_stack_pct.setValue(1.0)
            self._wire_inflow_stack_pct.setToolTip(
                "Wire inflow stacking percentage. Controls how "
                "aggressively the bot stacks new buy-side positions "
                "when fresh wire-inflow signals arrive. Default "
                "1.0 %; rarely adjusted in practice."
            )
            af.addRow("Wire Inflow Stack:", self._wire_inflow_stack_pct)

            groups.addWidget(self._adv_group)

            self._hedge_group = QGroupBox("Hedge Rebalance")
            hf = _mkform()
            self._hedge_group.setLayout(hf)

            self._hedge_rebalance = QCheckBox("Hedge Rebalance Active")
            self._hedge_rebalance.setChecked(True)
            self._hedge_rebalance.setToolTip(
                "Separate USD reserve for buying on sharp drawdowns. "
                "NOT taken from Target Balance."
            )
            hf.addRow(self._hedge_rebalance)

            self._hedge_amount = QDoubleSpinBox()
            self._hedge_amount.setRange(0.0, 999999999.0)
            self._hedge_amount.setDecimals(2)
            self._hedge_amount.setPrefix("$ ")
            self._hedge_amount.setValue(200.0)
            self._hedge_amount.setToolTip(
                "USD reserve amount for hedge rebalancing (separate "
                "from Target Balance)."
            )
            hf.addRow("Hedge Balance:", self._hedge_amount)

            groups.addWidget(self._hedge_group)

            self._cb_group = QGroupBox("Circuit Breakers (v3.15.58)")
            cf = _mkform()
            self._cb_group.setLayout(cf)

            self._cb_soft_pct = QDoubleSpinBox()
            self._cb_soft_pct.setRange(0.0, 100.0)
            self._cb_soft_pct.setDecimals(1)
            self._cb_soft_pct.setSuffix(" %")
            self._cb_soft_pct.setValue(25.0)
            self._cb_soft_pct.setToolTip(
                "SOFT Circuit Breaker threshold. Single-candle move "
                "≥ this % interrupts the side of the market that "
                "just moved (UP→SCRUM, DOWN→FOLD). Re-opens after "
                "cooldown candles. Default 25 %. Set 0 to disable."
            )
            cf.addRow("Soft CB Threshold:", self._cb_soft_pct)

            self._cb_hard_pct = QDoubleSpinBox()
            self._cb_hard_pct.setRange(0.0, 100.0)
            self._cb_hard_pct.setDecimals(1)
            self._cb_hard_pct.setSuffix(" %")
            self._cb_hard_pct.setValue(35.0)
            self._cb_hard_pct.setToolTip(
                "HARD Circuit Breaker threshold. Single-candle move "
                "≥ this % PAUSES the bot. Operator reset required "
                "to resume. Persists across restart. Default 35 %. "
                "Set 0 to disable."
            )
            cf.addRow("Hard CB Threshold:", self._cb_hard_pct)

            self._cb_cooldown = QSpinBox()
            self._cb_cooldown.setRange(1, 100)
            self._cb_cooldown.setValue(3)
            self._cb_cooldown.setToolTip(
                "Number of candles the soft breaker stays active "
                "before re-opening. Default 3."
            )
            cf.addRow("Soft CB Cooldown:", self._cb_cooldown)

            self._max_cartridge_pct = QDoubleSpinBox()
            self._max_cartridge_pct.setRange(0.0, 200.0)
            self._max_cartridge_pct.setDecimals(1)
            self._max_cartridge_pct.setSuffix(" %")
            self._max_cartridge_pct.setValue(10.0)
            self._max_cartridge_pct.setToolTip(
                "Maximum |Target Delta| as % of Target Balance. "
                "When the position drifts beyond this %, the bot "
                "fires an immediate aggressive rebalance (bypasses "
                "BB Detection / hysteresis / soft CB / higher-TF "
                "bias). Default 10 %. Set 0 to disable. v3.15.63."
            )
            cf.addRow("Max Cartridge Size:", self._max_cartridge_pct)

            self._cartridge_smart_chk = QCheckBox("Calibrate to BB range")
            self._cartridge_smart_chk.setChecked(False)
            self._cartridge_smart_chk.setToolTip(
                "When ON, Cartridge size is derived from current BB "
                "range rather than the static % above. Hard floor "
                "at the Opposing Trade Interval (cartridge cannot "
                "fire below the interval). Soft ceiling configured "
                "below. Default OFF preserves static behavior. "
                "v3.15.92."
            )
            cf.addRow("Smart Cartridge:", self._cartridge_smart_chk)

            self._cartridge_smart_ceiling = QDoubleSpinBox()
            self._cartridge_smart_ceiling.setRange(1.0, 100.0)
            self._cartridge_smart_ceiling.setDecimals(1)
            self._cartridge_smart_ceiling.setSuffix(" %")
            self._cartridge_smart_ceiling.setValue(30.0)
            self._cartridge_smart_ceiling.setToolTip(
                "Maximum effective cartridge threshold under Smart "
                "calibration. Prevents cartridge from being "
                "effectively disabled during volatility expansion. "
                "Only applies when Smart Cartridge is ON. Default "
                "30 %. v3.15.92."
            )
            cf.addRow("Smart Ceiling:", self._cartridge_smart_ceiling)

            groups.addWidget(self._cb_group)

            self._risk_group = QGroupBox("Risk Controls (MEM-244)")
            rf = _mkform()
            self._risk_group.setLayout(rf)

            self._position_ceiling_enabled = QCheckBox("Enable Position Ceiling")
            self._position_ceiling_enabled.setChecked(False)
            self._position_ceiling_enabled.setToolTip(
                "Cap accumulation at Nx of the bot's INITIAL "
                "target_balance (stable anchor set at creation). "
                "Fold rate tapers 100 % → 10 % as value approaches "
                "ceiling (ratio 0.5 → 1.0), hard-stops at ceiling. "
                "Scrum always allowed. Protects against runaway "
                "accumulation on conviction plays."
            )
            rf.addRow(self._position_ceiling_enabled)

            self._position_ceiling_multiple = QDoubleSpinBox()
            self._position_ceiling_multiple.setRange(1.0, 10.0)
            self._position_ceiling_multiple.setDecimals(1)
            self._position_ceiling_multiple.setSingleStep(0.5)
            self._position_ceiling_multiple.setSuffix("x anchor")
            self._position_ceiling_multiple.setValue(5.0)
            self._position_ceiling_multiple.setToolTip(
                "Ceiling multiplier. 1x = no accumulation beyond "
                "anchor. 10x = 10x runway. Default 5x."
            )
            rf.addRow("Ceiling Multiple:", self._position_ceiling_multiple)

            self._detonation_enabled = QCheckBox(
                "Enable Detonation (auto-harvest on bullish TF)"
            )
            self._detonation_enabled.setChecked(False)
            self._detonation_enabled.setToolTip(
                "Monitor a higher TF for BULLISH + high-confidence "
                "signal. Edge-triggered: fires ONCE per transition "
                "into bullish state.\nOn trigger: MARKET sell "
                "everything above the anchor, then reset "
                "target_balance to anchor ('lock in' gains, "
                "re-accumulate from scratch).\nRate-limited to 1 "
                "check/hour.\nAdditional gate: fires only when "
                "current value is above the anchor — no harvest if "
                "the bot is below its initial anchor."
            )
            rf.addRow(self._detonation_enabled)

            self._detonation_timeframe = QComboBox()
            self._detonation_timeframe.addItem("1d", "1d")
            self._detonation_timeframe.addItem("1w", "1w")
            self._detonation_timeframe.setToolTip(
                "Timeframe to monitor for bullish detonation "
                "signal. 1D = daily, 1W = weekly. Higher = stronger "
                "conviction, fewer triggers."
            )
            rf.addRow("Detonation TF:", self._detonation_timeframe)

            self._detonation_confidence_min = QDoubleSpinBox()
            self._detonation_confidence_min.setRange(0.50, 1.00)
            self._detonation_confidence_min.setDecimals(2)
            self._detonation_confidence_min.setSingleStep(0.05)
            self._detonation_confidence_min.setValue(0.75)
            self._detonation_confidence_min.setToolTip(
                "Minimum TA consensus confidence for detonation. "
                "Default 0.75 (high conviction only, per MEM-244)."
            )
            rf.addRow("Min Confidence:", self._detonation_confidence_min)

            groups.addWidget(self._risk_group)

            # Conservative = every gate ON (default), Lean = every gate OFF.
            # 39 sims x 2 profiles measured ~94.9 % win rate for both.
            self._gates_group = QGroupBox("Strategy Gate Flags (v3.16.15)")
            gf = _mkform()
            self._gates_group.setLayout(gf)

            self._gate_scrum_ta_chk = QCheckBox("SCRUM requires bullish TA")
            self._gate_scrum_ta_chk.setChecked(True)
            self._gate_scrum_ta_chk.setToolTip(
                "ON (Conservative): scrum auto-fire requires TA "
                "consensus BULLISH. OFF (Lean): scrum fires at "
                "BB-upper + delta regardless of TA."
            )
            gf.addRow(self._gate_scrum_ta_chk)

            self._gate_scrum_uptrend_chk = QCheckBox("SCRUM holds in sustained uptrend")
            self._gate_scrum_uptrend_chk.setChecked(True)
            self._gate_scrum_uptrend_chk.setToolTip(
                "ON (Conservative): if 65 %+ of last 20 candles "
                "were bullish, bot holds rather than scrumming each "
                "band touch. OFF (Lean): scrum every BB-upper touch "
                "regardless of trend strength."
            )
            gf.addRow(self._gate_scrum_uptrend_chk)

            self._gate_scrum_htf_chk = QCheckBox("SCRUM defers to higher-TF bullish")
            self._gate_scrum_htf_chk.setChecked(True)
            self._gate_scrum_htf_chk.setToolTip(
                "ON (Conservative): refuse scrum when a higher-TF "
                "phantom signals BULLISH. OFF (Lean): cartridge "
                "captures HTF swings organically."
            )
            gf.addRow(self._gate_scrum_htf_chk)

            self._gate_fold_ta_chk = QCheckBox("FOLD requires bearish TA")
            self._gate_fold_ta_chk.setChecked(True)
            self._gate_fold_ta_chk.setToolTip(
                "ON (Conservative): mirror of SCRUM TA gate on the "
                "fold side. OFF (Lean): fold fires at BB-lower + "
                "tranche-eligible regardless of TA."
            )
            gf.addRow(self._gate_fold_ta_chk)

            self._gate_fold_htf_chk = QCheckBox("FOLD defers to higher-TF bearish")
            self._gate_fold_htf_chk.setChecked(True)
            self._gate_fold_htf_chk.setToolTip(
                "ON (Conservative): mirror of SCRUM HTF gate on "
                "the fold side. OFF (Lean): fold fires regardless "
                "of higher-TF bearish bias."
            )
            gf.addRow(self._gate_fold_htf_chk)

            groups.addWidget(self._gates_group)

            self._routing_group = QGroupBox("Profit Routing (v3.20.85)")
            pr = _mkform()
            self._routing_group.setLayout(pr)

            self._profit_route = QComboBox()
            self._profit_route.addItem("Fold back to target balance", "fold_to_target")
            self._profit_route.addItem("Send to spendable", "spendable")
            self._profit_route.addItem("Split fold/spendable per %", "split")
            self._profit_route.addItem("Route to another bot (cross-bot)", "cross_bot")
            self._profit_route.setToolTip(
                "Where realized profit flows on fold. "
                "fold_to_target = increase target balance "
                "(compound); spendable = mark for withdrawal; "
                "split = use fold % below; cross_bot = route to "
                "the target bot ID."
            )
            pr.addRow("Route:", self._profit_route)

            self._profit_route_bot_id = QLineEdit()
            self._profit_route_bot_id.setPlaceholderText(
                "leave blank unless route = cross_bot"
            )
            self._profit_route_bot_id.setToolTip(
                "Target bot ID for cross-bot profit routing. Only "
                "consulted when route = cross_bot."
            )
            pr.addRow("Target bot ID:", self._profit_route_bot_id)

            groups.addWidget(self._routing_group)

            # One group, so every Extractor widget shows and hides together.
            self._extractor_group = QGroupBox("Extractor — Pool & Artillery")
            self._extractor_group.setVisible(False)
            eform = QFormLayout(self._extractor_group)
            eform.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            eform.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

            self._ext_chunk_size_usd = QDoubleSpinBox()
            self._ext_chunk_size_usd.setRange(10.0, 10_000_000.0)
            self._ext_chunk_size_usd.setPrefix("$")
            self._ext_chunk_size_usd.setDecimals(2)
            self._ext_chunk_size_usd.setValue(100.0)
            self._ext_chunk_size_usd.setToolTip(
                "USD-equivalent of base currency THIS bot owns. Converted "
                "to base units at bot creation; thereafter tracked in "
                "base units. The bot NEVER queries the total exchange "
                "balance — only this chunk."
            )
            eform.addRow("Chunk size (USD):", self._ext_chunk_size_usd)

            self._ext_artillery_size_usd = QDoubleSpinBox()
            self._ext_artillery_size_usd.setRange(0.5, 100_000.0)
            self._ext_artillery_size_usd.setPrefix("$")
            self._ext_artillery_size_usd.setDecimals(2)
            self._ext_artillery_size_usd.setValue(5.0)
            self._ext_artillery_size_usd.setToolTip(
                "USD value of each artillery round (single buy into one "
                "alt pair). Default $5 — small enough to fire frequently, "
                "large enough to clear exchange min-cost thresholds."
            )
            eform.addRow("Artillery size (USD):", self._ext_artillery_size_usd)

            self._ext_scan_top_n = QSpinBox()
            self._ext_scan_top_n.setRange(5, 10)
            self._ext_scan_top_n.setValue(8)
            self._ext_scan_top_n.setToolTip(
                "Top-N */<base> pairs by 24h volume kept on the watch "
                "list. Range 5-10. Higher = more candidates; lower = "
                "tighter focus on the most-liquid alts."
            )
            eform.addRow("Watch list top-N:", self._ext_scan_top_n)

            self._ext_scan_refresh = QSpinBox()
            self._ext_scan_refresh.setRange(10, 240)
            self._ext_scan_refresh.setValue(60)
            self._ext_scan_refresh.setSuffix(" candles")
            self._ext_scan_refresh.setToolTip(
                "Re-rank top-N every N candles. Default 60 = once per "
                "hour at 1m cadence. Lower = more responsive to volume "
                "shifts; higher = less API churn."
            )
            eform.addRow("Watch list refresh:", self._ext_scan_refresh)

            self._ext_pool_reserve = QDoubleSpinBox()
            self._ext_pool_reserve.setRange(0.0, 90.0)
            self._ext_pool_reserve.setSuffix("%")
            self._ext_pool_reserve.setDecimals(1)
            self._ext_pool_reserve.setValue(50.0)
            self._ext_pool_reserve.setToolTip(
                "Fraction of chunk that stays free as reserve. New "
                "artillery only fires if (chunk_free − artillery_size) "
                "≥ reserve. Default 50% — caps concurrent deployment."
            )
            eform.addRow("Pool reserve:", self._ext_pool_reserve)

            self._ext_exit_pct = QDoubleSpinBox()
            self._ext_exit_pct.setRange(10.0, 100.0)
            self._ext_exit_pct.setSuffix("%")
            self._ext_exit_pct.setDecimals(1)
            self._ext_exit_pct.setValue(100.0)
            self._ext_exit_pct.setToolTip(
                "Fraction of position sold on bullish trigger. 100 = "
                "full exit. Below 100 leaves a 'rider' tail in the "
                "position for continued upside."
            )
            eform.addRow("Exit %:", self._ext_exit_pct)

            self._ext_max_tier = QSpinBox()
            self._ext_max_tier.setRange(1, 10)
            self._ext_max_tier.setValue(3)
            self._ext_max_tier.setToolTip(
                "Per-position compounding tier max. Tier 1 always locks "
                "to pool. Higher tiers roll the realized gain back into "
                "the next round on the same pair. The counter dies with "
                "the position."
            )
            eform.addRow("Max compounding tier:", self._ext_max_tier)

            self._ext_max_cost_basis = QDoubleSpinBox()
            self._ext_max_cost_basis.setRange(1.0, 10.0)
            self._ext_max_cost_basis.setDecimals(1)
            self._ext_max_cost_basis.setSuffix("×")
            self._ext_max_cost_basis.setValue(2.0)
            self._ext_max_cost_basis.setToolTip(
                "Safety cap: cost basis of any position can't exceed "
                "this multiplier × original artillery_size. Hard floor "
                "against runaway averaging-down. Default 2× (one full "
                "doubling). Set 1.0 to disable averaging-down entirely."
            )
            eform.addRow("Max cost-basis multiple:", self._ext_max_cost_basis)

            self._ext_direction = QComboBox()
            self._ext_direction.addItem("Normal (base → alt: buy first)", "normal")
            self._ext_direction.addItem(
                "Inverted (standing alt → base: sell first)", "inverted"
            )
            self._ext_direction.setToolTip(
                "Normal Extractor (default): allocates from base "
                "currency (cash) — fires artillery as BUYS on dips, "
                "exits on bounces. Inverted Extractor: allocates from "
                "an existing standing alt position — fires artillery "
                "as SELLS on spikes, exits via buy-backs when prices "
                "fall. Use Inverted when you have a LINK / SOL / etc. "
                "you want to harvest volatility from without selling "
                "into cash. v3.20.74 backend; v3.20.84 wizard wiring."
            )
            eform.addRow("Direction:", self._ext_direction)

            self._ext_standing_alt_units = QDoubleSpinBox()
            self._ext_standing_alt_units.setRange(0.0, 1_000_000_000.0)
            self._ext_standing_alt_units.setDecimals(8)
            self._ext_standing_alt_units.setValue(0.0)
            self._ext_standing_alt_units.setToolTip(
                "Inverted Extractor only — units of standing alt this "
                "bot owns. Used by set_initial_chunk_rate to reflect "
                "the existing position so artillery rounds size "
                "correctly against the standing supply. Ignored when "
                "Direction = Normal (default 0)."
            )
            eform.addRow("Standing alt units (Inverted):", self._ext_standing_alt_units)

            self._ext_correction_skip = QSpinBox()
            self._ext_correction_skip.setRange(0, 100)
            self._ext_correction_skip.setValue(4)
            self._ext_correction_skip.setSuffix(" candles")
            self._ext_correction_skip.setToolTip(
                "Averaging-down throttle: after a correction (drawdown) "
                "fire, wait this many candles before the next "
                "correction-driven fire on the same pair. Default 4. "
                "Higher = more selective; lower = more aggressive "
                "cost-basis averaging."
            )
            eform.addRow("Correction skip candles:", self._ext_correction_skip)

            self._ext_drawdown_threshold = QDoubleSpinBox()
            self._ext_drawdown_threshold.setRange(0.0, 50.0)
            self._ext_drawdown_threshold.setSuffix("%")
            self._ext_drawdown_threshold.setDecimals(2)
            self._ext_drawdown_threshold.setValue(3.0)
            self._ext_drawdown_threshold.setToolTip(
                "USD drawdown threshold below cost basis that triggers "
                "an averaging-down correction fire. Default 3%. "
                "Symmetric for Inverted (drawup spike). Higher = react "
                "less often; lower = react earlier."
            )
            eform.addRow("Drawdown threshold:", self._ext_drawdown_threshold)

            self._ext_hedge_budget = QDoubleSpinBox()
            self._ext_hedge_budget.setRange(0.0, 10_000_000.0)
            self._ext_hedge_budget.setPrefix("$")
            self._ext_hedge_budget.setDecimals(2)
            self._ext_hedge_budget.setValue(0.0)
            self._ext_hedge_budget.setToolTip(
                "Optional separate base-currency hedge reserve, in USD. "
                "Default $0 (disabled). When >0, this amount is held "
                "out of artillery rotation as a hedge buffer. Operator "
                "tuning field; safe to leave 0 for v3.20.74 + v3.20.84 "
                "behavior."
            )
            eform.addRow("Hedge budget (USD):", self._ext_hedge_budget)

            self._ext_trend_strength = QDoubleSpinBox()
            self._ext_trend_strength.setRange(0.0, 1.0)
            self._ext_trend_strength.setDecimals(3)
            self._ext_trend_strength.setSingleStep(0.05)
            self._ext_trend_strength.setValue(0.65)
            self._ext_trend_strength.setToolTip(
                "Trend-hold threshold gating Extractor BB+trend "
                "signals. Default 0.65. Below this, fires require BB "
                "trigger; at/above, trend-hold suppresses noise fires. "
                "Tighter = fewer fires in choppy ranges; looser = more "
                "fires, more cost-basis churn."
            )
            eform.addRow("Trend strength threshold:", self._ext_trend_strength)

            groups.addWidget(self._extractor_group)

        def _on_visibility_changed(self):
            """Update UI elements when visibility mode changes."""

        def set_exchange_id(self, exchange_id: str | None) -> None:
            """v3.15.61 — refilter the TA Timeframe combo based on the
            selected exchange's supported granularities (operator
            directive 2026-04-26: "TF choices for given exchanges
            should change based on availability. For example, 4h
            should be disabled for Coinbase").
            """
            try:
                from src.exchange.timeframes import available_timeframes
            except Exception:
                return
            allowed = available_timeframes(exchange_id)
            current = self._ta_timeframe.currentData() or "1h"
            self._ta_timeframe.blockSignals(True)
            self._ta_timeframe.clear()
            for tf in allowed:
                self._ta_timeframe.addItem(tf, tf)
            idx = self._ta_timeframe.findData(current)
            if idx < 0:
                idx = self._ta_timeframe.findData("1h")
            if idx < 0:
                idx = 0
            self._ta_timeframe.setCurrentIndex(idx)
            self._ta_timeframe.blockSignals(False)

        def set_mode(self, is_grid: bool, is_extractor: bool = False):
            """v3.23.34 — group-level visibility toggle.

            Post-refactor layout has 8 QGroupBoxes for Scrumming
            (mirroring Bot Details Settings) + 1 Extractor group. Grid
            mode has been dead since v3.23.21; the ``is_grid`` argument
            is preserved for signature compatibility but hides all 8
            Scrumming groups when True (nothing to show).
            """
            self._is_grid = is_grid
            self._is_extractor = is_extractor
            scrum_visible = not is_grid and not is_extractor
            for g in (
                self._mode_group,
                self._scrum_group,
                self._adv_group,
                self._hedge_group,
                self._cb_group,
                self._risk_group,
                self._gates_group,
                self._routing_group,
            ):
                g.setVisible(scrum_visible)
            self._extractor_group.setVisible(is_extractor)
            if is_extractor:
                self.setSubTitle(
                    "Configure base-currency chunk, artillery sizing, "
                    "and compounding-tier policy."
                )
            elif is_grid:
                self.setSubTitle(
                    "Grid mode is retired (v3.23.21); no configurable "
                    "fields on this page."
                )
            else:
                self.setSubTitle(
                    "Configure target balance, scrumming interval, " "and compounding."
                )

        def get_config(self):
            """Return one key per widget this page draws, and no other key.

            profit_folding_active comes from ProfitFoldingPage, not this page.
            """
            cfg = {
                "visibility": self._visibility.currentData(),
                "aggressive_trading": self._aggressive.isChecked(),
            }
            if getattr(self, "_is_extractor", False):
                cfg.update(
                    {
                        "extractor_chunk_size_usd": self._ext_chunk_size_usd.value(),
                        "extractor_artillery_size_usd": self._ext_artillery_size_usd.value(),
                        "extractor_scan_top_n": int(self._ext_scan_top_n.value()),
                        "extractor_scan_refresh_candles": int(
                            self._ext_scan_refresh.value()
                        ),
                        "extractor_pool_reserve_pct": self._ext_pool_reserve.value(),
                        "extractor_exit_pct": self._ext_exit_pct.value(),
                        "extractor_max_compounding_tier": int(
                            self._ext_max_tier.value()
                        ),
                        "extractor_max_cost_basis_multiple": self._ext_max_cost_basis.value(),
                        "extractor_direction": self._ext_direction.currentData(),
                        "inverted_extractor_standing_alt_units": self._ext_standing_alt_units.value(),
                        "extractor_correction_skip_candles": int(
                            self._ext_correction_skip.value()
                        ),
                        "extractor_drawdown_threshold_pct": self._ext_drawdown_threshold.value(),
                        "extractor_hedge_budget_usd": self._ext_hedge_budget.value(),
                        "extractor_trend_strength_threshold": self._ext_trend_strength.value(),
                    }
                )
                return cfg
            _max_ep = self._max_entry_px.value()
            _min_ep = self._min_entry_px.value()
            cfg.update(
                {
                    "stack_mode": self._stack_mode.isChecked(),
                    "split_distance": self._split_distance.value(),
                    "stack_tranche_count_target": int(self._stack_count.value()),
                    "stack_spacing_mode": self._stack_spacing.currentData(),
                    "personal_hold_qty": float(self._personal_hold_qty.value()),
                    "scrumming_interval_pct": self._scrumming_interval.value(),
                    "bb_tolerance_pct": self._bb_tolerance.value(),
                    "bb_landing_strip_candles": self._ls_candles.value(),
                    "ta_timeframe": self._ta_timeframe.currentData(),
                    "target_balance": self._target_balance.value(),
                    "max_entry_price": (float(_max_ep) if _max_ep > 0 else None),
                    "min_entry_price": (float(_min_ep) if _min_ep > 0 else None),
                    "trading_fee_pct": self._trading_fee.value(),
                    "max_target_growth_pct": self._max_target_growth_pct.value(),
                    "scrum_fold_pct": self._scrum_fold_pct.value(),
                    "scrum_detect_pct": self._scrum_detect_pct.value(),
                    "scrum_fire_pct": self._scrum_fire_pct.value(),
                    "bb_midline_gate": self._bb_midline_gate.isChecked(),
                    "scrum_read_rate_min": self._scrum_read_rate.value(),
                    "band_travel_pct": self._band_travel_pct.value(),
                    "bb_bullseye_check": self._bb_bullseye.isChecked(),
                    "wire_inflow_stack_pct": self._wire_inflow_stack_pct.value(),
                    "hedge_rebalance_active": self._hedge_rebalance.isChecked(),
                    "hedge_balance": self._hedge_amount.value(),
                    "circuit_breaker_soft_pct": self._cb_soft_pct.value(),
                    "circuit_breaker_hard_pct": self._cb_hard_pct.value(),
                    "circuit_breaker_cooldown_candles": self._cb_cooldown.value(),
                    "max_cartridge_size_pct": self._max_cartridge_pct.value(),
                    "max_cartridge_smart": self._cartridge_smart_chk.isChecked(),
                    "max_cartridge_smart_ceiling_pct": self._cartridge_smart_ceiling.value(),
                    "position_ceiling_enabled": self._position_ceiling_enabled.isChecked(),
                    "position_ceiling_multiple": self._position_ceiling_multiple.value(),
                    "detonation_enabled": self._detonation_enabled.isChecked(),
                    "detonation_timeframe": self._detonation_timeframe.currentData(),
                    "detonation_confidence_min": self._detonation_confidence_min.value(),
                    "scrum_require_ta_bullish": self._gate_scrum_ta_chk.isChecked(),
                    "scrum_hold_in_uptrend": self._gate_scrum_uptrend_chk.isChecked(),
                    "scrum_defer_to_htf": self._gate_scrum_htf_chk.isChecked(),
                    "fold_require_ta_bearish": self._gate_fold_ta_chk.isChecked(),
                    "fold_hold_in_downtrend": True,  # reserved, no gate
                    "fold_defer_to_htf": self._gate_fold_htf_chk.isChecked(),
                    "profit_route": self._profit_route.currentData(),
                    "profit_route_bot_id": self._profit_route_bot_id.text().strip(),
                }
            )
            return cfg

    class ProfitFoldingPage(QWizardPage):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setTitle("Profit Folding & Upward Distribution")
            self.setSubTitle(
                "Configure how realized profits are recycled into new positions."
            )
            layout = QVBoxLayout(self)

            self._active = QCheckBox("Enable Profit Folding")
            self._active.setChecked(True)
            self._active.setToolTip(
                "Realized sell profits fold into buy positions. "
                "Accumulated asset distributes into sell positions. "
                "Extended Positions created when enough accumulates."
            )
            layout.addWidget(self._active)

            mode_group = QGroupBox("Distribution Mode")
            ml = QVBoxLayout(mode_group)
            self._fold_equal = QRadioButton("Equal - spread evenly")
            self._fold_equal.setChecked(True)
            self._fold_log = QRadioButton("Logarithmic - weight toward nearest")
            ml.addWidget(self._fold_equal)
            ml.addWidget(self._fold_log)
            layout.addWidget(mode_group)

            fold_group = QGroupBox(
                "Profit Folding Target (sell profits -> buy positions)"
            )
            ff = QFormLayout(fold_group)
            self._fold_all = QRadioButton("All buy positions")
            self._fold_all.setChecked(True)
            ff.addRow(self._fold_all)
            self._fold_x = QRadioButton("Nearest X buys:")
            ff.addRow(self._fold_x)
            self._fold_x_count = QSpinBox()
            self._fold_x_count.setRange(1, 50)
            self._fold_x_count.setValue(5)
            ff.addRow("  Count:", self._fold_x_count)
            self._fold_recent = QRadioButton("Most recent buy only")
            ff.addRow(self._fold_recent)
            layout.addWidget(fold_group)

            dist_group = QGroupBox(
                "Upward Distribution Target (accumulated asset -> sell positions)"
            )
            df = QFormLayout(dist_group)
            self._dist_all = QRadioButton("All sell positions")
            self._dist_all.setChecked(True)
            df.addRow(self._dist_all)
            self._dist_x = QRadioButton("Nearest X sells:")
            df.addRow(self._dist_x)
            self._dist_x_count = QSpinBox()
            self._dist_x_count.setRange(1, 50)
            self._dist_x_count.setValue(5)
            df.addRow("  Count:", self._dist_x_count)
            self._dist_recent = QRadioButton("Most recent sell only")
            df.addRow(self._dist_recent)
            layout.addWidget(dist_group)

        def get_config(self):
            ft = "all_buy"
            if self._fold_x.isChecked():
                ft = "x_buy"
            elif self._fold_recent.isChecked():
                ft = "most_recent_buy"
            dt = "all_sell"
            if self._dist_x.isChecked():
                dt = "x_sell"
            elif self._dist_recent.isChecked():
                dt = "most_recent_sell"
            return {
                "profit_folding_active": self._active.isChecked(),
                "fold_mode": "logarithmic" if self._fold_log.isChecked() else "equal",
                "fold_target": ft,
                "fold_target_count": self._fold_x_count.value(),
                "distribute_target": dt,
                "distribute_target_count": self._dist_x_count.value(),
            }

    class PhantomConfigPage(QWizardPage):
        def __init__(self, defaults: dict, parent=None):
            super().__init__(parent)
            self.setTitle("Phantom Balance Bots")
            self.setSubTitle(
                "Multi-timeframe shadow bots. Higher TFs override lower TFs."
            )
            self._exchange_id: str | None = None
            from src.core.settings import AppSettings

            self._stored_timeframe = str(
                (defaults or {}).get("default_phantom_timeframe")
                or AppSettings().default_phantom_timeframe
            )
            self._stored_lock_candles = int(
                (defaults or {}).get("default_lock_candle_count")
                or AppSettings().default_lock_candle_count
            )
            layout = QVBoxLayout(self)
            self._enable = QCheckBox("Enable Phantom Balance Bots")
            self._enable.setChecked(
                bool((defaults or {}).get("default_enable_phantoms", False))
            )
            layout.addWidget(self._enable)
            layout.addWidget(QLabel("Active Timeframes:"))
            self._tf_checks: dict[str, QCheckBox] = {}
            tf_row = QHBoxLayout()
            for tf in [
                "1m",
                "5m",
                "15m",
                "30m",
                "1h",
                "2h",
                "4h",
                "6h",
                "12h",
                "1d",
                "1w",
            ]:
                cb = QCheckBox(tf)
                cb.setChecked(False)
                self._tf_checks[tf] = cb
                tf_row.addWidget(cb)
            layout.addLayout(tf_row)
            lock_group = QGroupBox("Higher-TF Lock Duration")
            lf = QFormLayout(lock_group)
            self._lock_candles = QSpinBox()
            self._lock_candles.setRange(1, 10)
            self._lock_candles.setValue(self._stored_lock_candles)
            lf.addRow("Candles to lock:", self._lock_candles)
            layout.addWidget(lock_group)
            layout.addStretch()

        def get_config(self):
            checked = [
                tf
                for tf, cb in self._tf_checks.items()
                if cb.isChecked() and cb.isEnabled()
            ]
            return {
                "enable_phantoms": self._enable.isChecked(),
                "phantom_timeframes": checked,
                "lock_candle_count": self._lock_candles.value(),
            }

        def set_exchange_id(self, exchange_id: str | None) -> None:
            """v3.15.61 — disable phantom-TF checkboxes for TFs the
            exchange does not support. Keeps the layout stable
            (checkboxes still visible, but greyed and unchecked) so the
            operator can SEE which TFs are unavailable on this exchange.
            """
            self._exchange_id = exchange_id
            try:
                from src.exchange.timeframes import available_timeframes
            except Exception:
                return
            allowed = set(available_timeframes(exchange_id))
            for tf, cb in self._tf_checks.items():
                supported = tf in allowed
                cb.setEnabled(supported)
                if not supported and cb.isChecked():
                    cb.setChecked(False)
                cb.setToolTip(
                    f"Timeframe {tf}: "
                    + (
                        "supported"
                        if supported
                        else f"NOT supported by {exchange_id or 'this exchange'}"
                    )
                )

        def set_parent_timeframe(self, ta_timeframe: str | None) -> None:
            """Tick the stored phantom timeframe, refusing one the bot cannot use.

            The Settings dialog writes ``default_phantom_timeframe``. A
            timeframe at or below ``ta_timeframe``, or one the venue does not
            offer, stays clear and its box says why. A box the operator has
            already ticked keeps his choice.
            """
            from src.gui.main_tabs.bot_wizard_surface import (
                PHANTOM_NOT_HIGHER_FORMAT,
                PHANTOM_NOT_OFFERED_FORMAT,
                PHANTOM_UNKNOWN_EXCHANGE,
            )
            from src.trading.phantom_balance import is_higher_tf

            parent = str(ta_timeframe or "")
            if any(one.isChecked() for one in self._tf_checks.values()):
                return
            cb = self._tf_checks.get(self._stored_timeframe)
            if cb is None:
                return
            if not is_higher_tf(self._stored_timeframe, parent):
                cb.setToolTip(
                    PHANTOM_NOT_HIGHER_FORMAT.format(
                        timeframe=self._stored_timeframe, parent=parent
                    )
                )
                return
            if not cb.isEnabled():
                cb.setToolTip(
                    PHANTOM_NOT_OFFERED_FORMAT.format(
                        timeframe=self._stored_timeframe,
                        exchange=self._exchange_id or PHANTOM_UNKNOWN_EXCHANGE,
                    )
                )
                return
            cb.setChecked(True)

        def validatePage(self) -> bool:
            """v3.23.40 — API-load gate. If phantoms are enabled and
            the projected calls-per-minute would breach the 75 % safety
            threshold for the selected exchange, warn the operator and
            let them either back off or force through."""
            if not self._enable.isChecked():
                return True
            checked = [
                tf
                for tf, cb in self._tf_checks.items()
                if cb.isChecked() and cb.isEnabled()
            ]
            if not checked:
                return True
            ex_id = self._exchange_id or ""
            if not ex_id:
                return True
            try:
                from src.exchange.api_load_monitor import get_load_monitor

                mon = get_load_monitor()
                allow, reason = mon.should_allow_new_phantom_set(ex_id, len(checked))
            except Exception:  # noqa: BLE001 - monitor best-effort
                return True
            if allow:
                return True
            try:
                from PySide6.QtWidgets import QMessageBox
            except Exception:  # noqa: BLE001 - dialog best-effort
                return True
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Phantom Bots — API load warning")
            box.setText(
                f"Enabling {len(checked)} phantom(s) on "
                f"{ex_id} may exceed the API-load safety "
                f"threshold.\n\n{reason}"
            )
            box.setInformativeText(
                "Choose Back to reduce timeframes or disable phantoms. "
                "Choose Continue to proceed anyway (the bot will still "
                "be created; individual API calls may throttle)."
            )
            back_btn = box.addButton("Back to adjust", QMessageBox.RejectRole)
            box.addButton("Continue anyway", QMessageBox.AcceptRole)
            box.setDefaultButton(back_btn)
            box.exec()
            clicked = box.clickedButton()
            return clicked is not back_btn

    class BotCreationWizard(QWizard):
        def __init__(self, exchanges: list[dict], defaults: dict, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Create Auto Trader")
            self.setAccessibleName("Create Auto Trader")
            self.setAccessibleDescription(
                "Creates one bot. Pick the mode, then the pair or the "
                "pool, then the trading parameters."
            )
            self.setMinimumSize(700, 550)
            self.resize(1100, 750)
            self._asset_page = AssetSelectionPage(exchanges)
            self._mode_page = ModeSelectionPage()
            self._extractor_pool_page = ExtractorPoolPage(exchanges)
            self._params_page = TradingParamsPage(defaults)
            self._folding_page = ProfitFoldingPage()
            self._phantom_page = PhantomConfigPage(defaults)
            self.setPage(PAGE_ASSET, self._asset_page)
            self.setPage(PAGE_MODE, self._mode_page)
            self.setPage(PAGE_EXTRACTOR_POOL, self._extractor_pool_page)
            self.setPage(PAGE_PARAMS, self._params_page)
            self.setPage(PAGE_FOLDING, self._folding_page)
            self.setPage(PAGE_PHANTOM, self._phantom_page)
            self.setStartId(PAGE_MODE)
            self.currentIdChanged.connect(self._on_page_changed)

        def _on_page_changed(self, page_id):
            if page_id == PAGE_PARAMS:
                self._params_page.set_mode(
                    self._mode_page.is_grid(),
                    is_extractor=self._mode_page.is_extractor(),
                )
                # Coinbase offers no 4h. The venue's list replaces the combo's.
                try:
                    eid = self._asset_page._exchange.currentData()
                    self._params_page.set_exchange_id(eid)
                except Exception as _tf_exc:  # noqa: BLE001 - TF-filter best-effort
                    logger.debug("params_page.set_exchange_id failed: %s", _tf_exc)
            elif page_id == PAGE_PHANTOM:
                try:
                    eid = self._asset_page._exchange.currentData()
                    self._phantom_page.set_exchange_id(eid)
                except Exception as _ph_tf_exc:  # noqa: BLE001 - TF-filter best-effort
                    logger.debug("phantom_page.set_exchange_id failed: %s", _ph_tf_exc)
                try:
                    self._phantom_page.set_parent_timeframe(
                        self._params_page._ta_timeframe.currentData()
                    )
                except Exception as _ph_parent_exc:  # noqa: BLE001 - seed best-effort
                    logger.debug(
                        "phantom_page.set_parent_timeframe failed: %s", _ph_parent_exc
                    )

        def nextId(self):
            current = self.currentId()
            if current == PAGE_MODE:
                if self._mode_page.is_extractor():
                    return PAGE_EXTRACTOR_POOL
                return PAGE_ASSET
            if current == PAGE_ASSET:
                return PAGE_PARAMS
            if current == PAGE_EXTRACTOR_POOL:
                return PAGE_PARAMS
            if current == PAGE_PARAMS:
                if self._mode_page.is_extractor():
                    return -1
                # is_grid() returns False always; this branch is unreachable.
                if self._mode_page.is_grid():
                    return PAGE_FOLDING
                return PAGE_PHANTOM
            if current == PAGE_FOLDING:
                return -1
            if current == PAGE_PHANTOM:
                return -1
            return current + 1

        def get_bot_config(self):
            config = {}
            if self._mode_page.is_extractor():
                config["mode"] = "extractor"
                config.update(self._extractor_pool_page.get_config())
            else:
                config["mode"] = "scrumming"
                config.update(self._asset_page.get_config())
            config.update(self._params_page.get_config())
            if config["mode"] == "extractor":
                config["enable_phantoms"] = False
                config["profit_folding_active"] = False
            else:
                config.update(self._phantom_page.get_config())
            return config
