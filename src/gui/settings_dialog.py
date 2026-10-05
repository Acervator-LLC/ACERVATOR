"""Declares ``SettingsDialog``, the Qt Settings window ``variant_surface`` returns."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QTabWidget,
        QWidget,
        QLabel,
        QLineEdit,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox,
        QCheckBox,
        QGroupBox,
        QPushButton,
        QSlider,
        QListWidget,
        QListWidgetItem,
        QTextEdit,
        QFormLayout,
        QMessageBox,
    )
    from PySide6.QtCore import Qt, Signal

    _HAS_QT = True
except ImportError:
    _HAS_QT = False
from src.gui.qt_safe_events import safe_process_events

if _HAS_QT:

    from .main_tabs import asset_class_surface as acs
    from .main_tabs import settings_dialog_surface as sds
    from .main_tabs.asset_class_surface import EQUITY_VENUES as EQUITY_EXCHANGE_IDS

    class SettingsDialog(QDialog):

        settings_changed = Signal()

        def __init__(
            self, settings_manager, status_log=None, parent=None, wing: str = "crypto"
        ):
            """Wing-aware Settings dialog.

            Parameters
            ----------
            wing : {"crypto", "stock"}
                Which trading-mode wing the dialog was opened from.
                Filters the Exchanges tab so the operator only sees
                exchanges that belong to that wing:
                  * crypto: the CCXT-supported list (binance, coinbase,
                    kraken, etc.) — current behaviour
                  * stock:  the planned equity-broker list (alpaca,
                    ibkr, schwab, ...) with a "broker integration
                    queued; not yet live" banner and the Add/Test
                    buttons disabled
                The "Configured Exchanges" list at the top of the tab
                is also filtered to match — stock-wing operators no
                longer see their crypto exchanges in the Stock
                Settings, and vice versa.
            """
            super().__init__(parent)
            self.setWindowTitle(
                f"Settings — {wing.capitalize()} Wing"
                if wing in ("crypto", "stock")
                else "Settings"
            )
            self.setMinimumSize(700, 600)
            self._sm = settings_manager
            self._status_log = status_log
            self._last_validation = None
            # normalise resolves the legacy wing word "stock" onto "stocks".
            self._wing = acs.normalise(wing)
            self._setup_ui()
            self._load_current()

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            tabs = QTabWidget()
            tabs.addTab(self._create_user_tab(), "User")
            tabs.addTab(self._create_exchange_tab(), "Exchanges")
            tabs.addTab(self._create_trading_tab(), "Trading")
            tabs.addTab(self._create_ta_tab(), "TA Indicators")
            tabs.addTab(self._create_phantom_tab(), "Phantom Bots")
            tabs.addTab(self._create_theme_tab(), "Theme")
            tabs.addTab(self._create_sound_tab(), "Sound")
            tabs.addTab(self._create_sms_tab(), "SMS")
            tabs.addTab(self._create_ai_monitor_tab(), "AI Monitor")
            self._tabs = tabs
            layout.addWidget(tabs)

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self._cancel_btn = QPushButton("Cancel")
            self._cancel_btn.clicked.connect(lambda: self.reject())
            btn_row.addWidget(self._cancel_btn)
            self._save_btn = QPushButton("Save")
            self._save_btn.setProperty("accent", True)
            self._save_btn.setStyleSheet("font-weight: bold; padding: 6px 24px;")
            self._save_btn.clicked.connect(lambda: self._save())
            btn_row.addWidget(self._save_btn)
            layout.addLayout(btn_row)

        @property
        def tab(self) -> str:
            """The title of the tab the dialog is showing."""
            book = getattr(self, "_tabs", None)
            if book is None:
                return ""
            return book.tabText(book.currentIndex())

        def show_tab(self, title: str) -> None:
            """Show the tab whose title is ``title``, and ignore an unknown one.

            The match is on the title each tab carries, so a tab added before
            another does not move which one a caller gets.
            """
            book = getattr(self, "_tabs", None)
            if book is None:
                return
            for at in range(book.count()):
                if book.tabText(at) == title:
                    book.setCurrentIndex(at)
                    return

        def _create_user_tab(self) -> QWidget:
            w = QWidget()
            form = QFormLayout(w)
            self._username = QLineEdit()
            form.addRow("Username:", self._username)
            return w

        def _create_exchange_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)

            if self._wing == "stocks":
                _banner = QLabel(
                    "<b>Stock Wing:</b> equity-broker integration is "
                    "queued — no live brokers are wired up yet. The "
                    "list below shows the planned brokers; Add / Test "
                    "are disabled until the broker connectors ship. "
                    "Use the Crypto Wing for active trading today."
                )
                _banner.setWordWrap(True)
                # Qt reads eight hex digits alpha-first, so the edge is
                # written rgba and draws the tint it names.
                _banner.setStyleSheet(
                    "background: rgba(102, 153, 255, 30); "
                    "color: #6699ff; border: 1px solid rgba(102, 153, 255, 85); "
                    "padding: 8px; border-radius: 4px;"
                )
                layout.addWidget(_banner)

            self._exchange_list = QListWidget()
            layout.addWidget(QLabel(sds.exchange_status_label()))
            layout.addWidget(self._exchange_list)

            add_group = QGroupBox(
                f"Add {acs.display_name(self._wing)} {acs.venue_noun(self._wing)}"
            )
            add_form = QFormLayout(add_group)

            self._new_exchange = QComboBox()
            from src.exchange.ccxt_connector import (
                SUPPORTED_EXCHANGES,
                PASSPHRASE_EXCHANGES,
                exchange_label,
            )

            self._passphrase_exchanges = PASSPHRASE_EXCHANGES

            # The active class filters the venue list. A venue serving two
            # classes is offered under both.
            for eid in sorted(acs.venues_for_class(self._wing)):
                if eid in EQUITY_EXCHANGE_IDS:
                    self._new_exchange.addItem(
                        f"{eid.capitalize()} (planned, not yet live)",
                        eid,
                    )
                elif eid in SUPPORTED_EXCHANGES:
                    self._new_exchange.addItem(exchange_label(eid), eid)
            self._new_exchange.currentIndexChanged.connect(self._on_exchange_changed)
            add_form.addRow("Exchange:", self._new_exchange)

            self._new_api_key = QLineEdit()
            self._new_api_key.setPlaceholderText(
                "API Key or organizations/.../.../apiKeys/..."
            )
            self._new_api_key.setToolTip(
                "For Coinbase CDP keys, paste the full organizations/.../apiKeys/... string"
            )
            add_form.addRow("API Key:", self._new_api_key)

            self._new_api_secret = QTextEdit()
            self._new_api_secret.setMaximumHeight(60)
            self._new_api_secret.setPlaceholderText(
                "API Secret or EC Private Key (PEM format with \\n is OK)"
            )
            self._new_api_secret.setToolTip(
                "For Coinbase CDP keys, paste the full PEM key including\n"
                "-----BEGIN EC PRIVATE KEY----- and -----END EC PRIVATE KEY-----\n"
                "Literal \\n characters will be auto-converted to newlines."
            )
            add_form.addRow("API Secret:", self._new_api_secret)

            # _new_passphrase is built above _pp_check so _sync_passphrase_row
            # has both names. The rows keep the painted order below.
            self._new_passphrase = QLineEdit()
            self._new_passphrase.setEchoMode(QLineEdit.Password)
            self._new_passphrase.setPlaceholderText(
                "Passphrase set when creating API key"
            )
            self._new_passphrase.setVisible(False)

            self._pp_check = QCheckBox("This exchange uses an API passphrase")
            self._pp_check.toggled.connect(lambda: self._sync_passphrase_row())
            add_form.addRow(self._pp_check)
            add_form.addRow("", self._new_passphrase)

            btn_row = QHBoxLayout()
            self._test_btn = QPushButton("Test Connection")
            self._test_btn.clicked.connect(self._test_api_connection)
            btn_row.addWidget(self._test_btn)

            self._add_btn = QPushButton("Test and Add Exchange")
            self._add_btn.setProperty("accent", True)
            self._add_btn.clicked.connect(self._add_exchange)
            btn_row.addWidget(self._add_btn)
            add_form.addRow(btn_row)

            self._api_feedback = QLabel("")
            self._api_feedback.setWordWrap(True)
            add_form.addRow(self._api_feedback)

            if self._wing == "stocks":
                _disabled_tip = (
                    "Stock broker connector integration is queued; "
                    "no live brokers ship yet. Use the Crypto Wing "
                    "for active trading."
                )
                # setEnabled and setToolTip refuse only a deleted C++ object,
                # and _create_exchange_tab builds every widget named here.
                for _w in (
                    self._test_btn,
                    self._add_btn,
                    self._new_api_key,
                    self._new_api_secret,
                    self._new_passphrase,
                    self._pp_check,
                ):
                    _w.setEnabled(False)
                    _w.setToolTip(_disabled_tip)

            layout.addWidget(add_group)

            rm_btn = QPushButton("Remove Selected")
            rm_btn.setProperty("danger", True)
            rm_btn.clicked.connect(self._remove_exchange)
            layout.addWidget(rm_btn)

            self._on_exchange_changed()
            self._refresh_exchange_status()
            return w

        def _status_class(self) -> str:
            """The sector the Exchange Status panel lists venues for."""
            return acs.normalise(self._wing)

        def _recorded_venue_states(self) -> dict:
            """Every venue's last recorded credential check, read off disk."""
            from src.exchange.credential_state import recorded_states

            try:
                return recorded_states()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Exchange Status read no recorded state: %s", exc)
                return {}

        def _refresh_exchange_status(self) -> None:
            """Draw one pressable row per venue serving the dialog's sector.

            Reads the recorded states off disk, so a redraw places no venue call.
            """
            states = self._recorded_venue_states()
            self._venue_states = states
            rows = sds.exchange_status_rows(self._status_class(), states)
            self._exchange_list.clear()
            for at, (words, venue, _state, _colour, style, tip) in enumerate(rows):
                # The item keeps the row text so _list_exchange_once and
                # _remove_exchange read the venue id off it; the button covers it.
                item = QListWidgetItem(words)
                self._exchange_list.addItem(item)
                press = QPushButton(words)
                press.setStyleSheet(style)
                press.setToolTip(tip)
                press.setEnabled(bool(venue))
                press.clicked.connect(
                    lambda *_ignored, row=at: self._open_credentials_for_row(row)
                )
                item.setSizeHint(press.sizeHint())
                self._exchange_list.setItemWidget(item, press)

        def _open_credentials_for_row(self, at) -> None:
            """Bind the Add-exchange form to the venue the row at ``at`` names."""
            states = getattr(self, "_venue_states", {})
            venue = sds.row_venue_id(self._status_class(), at, states)
            if not venue:
                return
            self._exchange_list.setCurrentRow(int(at))
            found = self._new_exchange.findData(venue)
            if found < 0:
                self._set_feedback(
                    sds.VENUE_HAS_NO_FORM.format(name=venue.capitalize()), "warning"
                )
                return
            self._new_exchange.setCurrentIndex(found)
            self._on_exchange_changed()
            self._set_feedback(
                sds.VENUE_FORM_BOUND.format(name=venue.capitalize()), "info"
            )

        def _on_exchange_changed(self) -> None:
            eid = self._new_exchange.currentData()
            needs_pp = eid in self._passphrase_exchanges
            self._pp_check.setChecked(needs_pp)
            self._sync_passphrase_row()
            self._api_feedback.setText("")

        def _sync_passphrase_row(self) -> None:
            """Draw ``_new_passphrase`` while ``_pp_check`` is ticked.

            Both builds call this; the React holder's ``setChecked`` emits no
            Qt ``toggled``.
            """
            self._new_passphrase.setVisible(self._pp_check.isChecked())

        def _typed_secret(self) -> str:
            """The API Secret row, with a pasted PEM's escaped newlines made real.

            The row's tooltip promises the conversion, so it runs here rather
            than at connect, and every venue receives the same bytes.
            """
            from src.core.encryption import looks_like_pem, unescape_pem_newlines

            typed = self._new_api_secret.toPlainText().strip()
            if looks_like_pem(typed):
                return unescape_pem_newlines(typed)
            return typed

        def _test_api_connection(self):
            eid = self._new_exchange.currentData()
            key = self._new_api_key.text().strip()
            secret = self._typed_secret()
            pp = (
                self._new_passphrase.text().strip()
                if self._pp_check.isChecked()
                else ""
            )

            if not key or not secret:
                self._set_feedback("Enter API key and secret first.", "error")
                return None

            self._set_feedback(f"Testing connection to {eid.capitalize()}...", "info")
            self._test_btn.setEnabled(False)
            self._add_btn.setEnabled(False)
            safe_process_events("legacy processEvents site")

            try:
                from src.exchange.api_validator import validate_credentials

                result = validate_credentials(eid, key, secret, pp)
                if result.success:
                    msg = result.message
                    if result.details:
                        msg += f"\nBalances: {result.details}"
                    self._set_feedback(msg, "success")
                    if self._status_log:
                        self._status_log.log(result.message, "success")
                        if result.details:
                            self._status_log.log(f"Balances: {result.details}", "info")
                    self._last_validation = result
                    return result
                else:
                    msg = result.message
                    if result.details:
                        msg += f"\n{result.details}"
                    self._set_feedback(msg, "error")
                    if self._status_log:
                        self._status_log.log(
                            f"API failed ({eid}): {result.message}", "error"
                        )
                    self._last_validation = None
                    return None
            except Exception as exc:
                self._set_feedback(f"Test failed: {exc}", "error")
                self._last_validation = None
                return None
            finally:
                self._test_btn.setEnabled(True)
                self._add_btn.setEnabled(True)
                self._refresh_exchange_status()

        def _set_feedback(self, message: str, level: str = "info") -> None:
            colors = {
                "info": "#00aaff",
                "success": "#00ff88",
                "warning": "#ffaa00",
                "error": "#ff3366",
            }
            self._api_feedback.setText(message)
            self._api_feedback.setStyleSheet(f"color: {colors.get(level, '#e0e0f0')};")

        def _add_exchange(self) -> None:
            # Prevent duplicate clicks
            self._add_btn.setEnabled(False)
            self._test_btn.setEnabled(False)
            safe_process_events("legacy processEvents site")

            try:
                eid = self._new_exchange.currentData()
                key = self._new_api_key.text().strip()
                secret = self._typed_secret()
                pp = (
                    self._new_passphrase.text().strip()
                    if self._pp_check.isChecked()
                    else ""
                )

                if key and secret:
                    result = self._test_api_connection()
                    if result is None or not result.success:
                        return

                from src.core.settings import ExchangeConfig

                config = ExchangeConfig(exchange_id=eid, display_name=eid.capitalize())

                if key and secret:
                    from src.core.encryption import encrypt, vault_phrase

                    master = vault_phrase(self._sm.get("username", ""))
                    config.api_key_enc = encrypt(key, master)
                    config.api_secret_enc = encrypt(secret, master)
                    if pp:
                        config.passphrase_enc = encrypt(pp, master)

                self._sm.add_exchange(config)
                self._list_exchange_once(eid)
                self._refresh_exchange_status()
                self._new_api_key.clear()
                self._new_api_secret.clear()
                self._new_passphrase.clear()

                from .main_tabs.settings_dialog_surface import (
                    stored_credential_phrase,
                )

                has_creds = stored_credential_phrase(self._sm.get_exchange(eid))
                self._set_feedback(f"{eid.capitalize()} added {has_creds}.", "success")
                if self._status_log:
                    self._status_log.log(
                        f"Exchange added: {eid.capitalize()} ({has_creds})", "success"
                    )
                QMessageBox.information(
                    self,
                    "Exchange Added",
                    f"{eid.capitalize()} has been added {has_creds}.\n"
                    f"The exchange tab will appear in the main window.",
                )
                self.accept()
            finally:
                self._add_btn.setEnabled(True)
                self._test_btn.setEnabled(True)

        def _list_exchange_once(self, eid: str) -> None:
            """Draw ``eid`` in ``_exchange_list`` while no line names it yet.

            Both builds run this method and the Qt-free model calls the same
            ``listed_exchange_position``.
            """
            from .main_tabs.settings_dialog_surface import (
                NO_MATCH_INDEX,
                listed_exchange_position,
            )

            drawn = [
                self._exchange_list.item(at).text()
                for at in range(self._exchange_list.count())
            ]
            if listed_exchange_position(drawn, eid) == NO_MATCH_INDEX:
                self._exchange_list.addItem(f"{eid.capitalize()} ({eid})")

        def _remove_exchange(self) -> None:
            item = self._exchange_list.currentItem()
            if not item:
                self._set_feedback("Select an exchange to remove.", "warning")
                return
            text = item.text()
            eid = text.split("(")[-1].rstrip(")")
            from src.exchange.credential_state import forget

            self._sm.remove_exchange(eid)
            self._exchange_list.takeItem(self._exchange_list.row(item))
            forget(eid)
            self._refresh_exchange_status()
            self._set_feedback(f"{eid.capitalize()} removed.", "info")
            if self._status_log:
                self._status_log.log(f"Exchange removed: {eid}", "warning")

        def _create_trading_tab(self) -> QWidget:
            w = QWidget()
            form = QFormLayout(w)
            self._default_balance = QDoubleSpinBox()
            self._default_balance.setRange(1.0, 1000000.0)
            self._default_balance.setPrefix("$")
            self._default_balance.setDecimals(2)
            form.addRow("Default Target Balance:", self._default_balance)
            self._visibility = QComboBox()
            self._visibility.addItems(["orderbook", "internal"])
            form.addRow("Bot Visibility:", self._visibility)
            self._aggressive = QCheckBox("Enable aggressive trading mode")
            form.addRow(self._aggressive)
            return w

        def _create_ta_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.addWidget(QLabel("Adjust indicator weights in the voting engine."))
            from src.gui.main_tabs.settings_dialog_surface import (
                TA_LABEL_MIN_WIDTH,
                TA_SLIDER_RANGE,
                TA_SLIDER_SCALE,
                TA_VALUE_MIN_WIDTH,
                ta_label,
                ta_slider_value,
                ta_value_text,
            )
            from src.trading.ta_engine import DEFAULT_WEIGHTS

            self._ta_weight_sliders = {}
            for ind_name, default_w in DEFAULT_WEIGHTS.items():
                row = QHBoxLayout()
                label = QLabel(ta_label(ind_name))
                label.setMinimumWidth(TA_LABEL_MIN_WIDTH)
                row.addWidget(label)
                slider = QSlider(Qt.Horizontal)
                slider.setRange(*TA_SLIDER_RANGE)
                slider.setValue(ta_slider_value(default_w))
                row.addWidget(slider)
                val_label = QLabel(ta_value_text(default_w))
                val_label.setMinimumWidth(TA_VALUE_MIN_WIDTH)
                slider.valueChanged.connect(
                    lambda v, lbl=val_label: lbl.setText(
                        ta_value_text(v / TA_SLIDER_SCALE)
                    )
                )
                row.addWidget(val_label)
                self._ta_weight_sliders[ind_name] = slider
                layout.addLayout(row)
            layout.addStretch()
            return w

        def _create_phantom_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)
            self._phantoms_enabled = QCheckBox("Enable Phantom Bots for Scrumming")
            self._phantoms_enabled.setChecked(True)
            layout.addWidget(self._phantoms_enabled)
            from src.gui.main_tabs.settings_dialog_surface import (
                LOCK_CANDLE_DEFAULT,
                PHANTOM_TIMEFRAME_DEFAULT,
                PHANTOM_TIMEFRAMES,
            )

            layout.addWidget(QLabel("Default Phantom Timeframes:"))
            self._phantom_timeframe = QComboBox()
            for tf in PHANTOM_TIMEFRAMES:
                self._phantom_timeframe.addItem(tf, tf)
            self._phantom_timeframe.setCurrentIndex(
                self._phantom_timeframe.findData(PHANTOM_TIMEFRAME_DEFAULT)
            )
            self._phantom_timeframe.setToolTip(
                "The one phantom timeframe a new bot starts with"
            )
            layout.addWidget(self._phantom_timeframe)
            lock_group = QGroupBox("Higher-TF Lock Settings")
            lock_form = QFormLayout(lock_group)
            self._lock_candles = QSpinBox()
            self._lock_candles.setRange(1, 10)
            self._lock_candles.setValue(LOCK_CANDLE_DEFAULT)
            lock_form.addRow("Lock duration (candles):", self._lock_candles)
            layout.addWidget(lock_group)
            layout.addStretch()
            return w

        def _create_theme_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)

            layout.addWidget(QLabel("Visual Theme:"))
            self._theme_combo = QComboBox()
            from src.gui.theme_engine import THEMES

            for name, tokens in THEMES.items():
                self._theme_combo.addItem(tokens.display_name, name)
            layout.addWidget(self._theme_combo)

            layout.addWidget(QLabel("Accent Color:"))
            self._accent_color = QLineEdit()
            self._accent_color.setPlaceholderText("#00ffcc")
            layout.addWidget(self._accent_color)

            layout.addStretch()
            return w

        def _create_sound_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)
            self._sound_enabled = QCheckBox("Enable sound notifications")
            self._sound_enabled.setChecked(True)
            self._sound_enabled.setToolTip("Master switch for all audio notifications")
            layout.addWidget(self._sound_enabled)

            layout.addWidget(QLabel("Sound Events:"))
            self._sound_buy = QCheckBox("Buy order fills (blurb + squirt tone)")
            self._sound_buy.setChecked(True)
            self._sound_buy.setToolTip(
                "Plays a low bubbly rising tone when a buy order is filled"
            )
            layout.addWidget(self._sound_buy)

            self._sound_sell = QCheckBox("Sell order fills (bell + jingle tone)")
            self._sound_sell.setChecked(True)
            self._sound_sell.setToolTip(
                "Plays a high bright bell tone when a sell order is filled"
            )
            layout.addWidget(self._sound_sell)

            self._sound_error = QCheckBox("Errors (alert tone)")
            self._sound_error.setChecked(True)
            layout.addWidget(self._sound_error)

            self._sound_state = QCheckBox("Bot state changes (subtle click)")
            self._sound_state.setChecked(True)
            layout.addWidget(self._sound_state)

            self._sound_fire = QCheckBox("Scrum/Fold Fire (sniper rifle shot)")
            self._sound_fire.setChecked(True)
            self._sound_fire.setToolTip(
                "Synthesized rifle shot plays when a scrum or fold\n"
                "actually executes. Also plays on Manual Fire."
            )
            layout.addWidget(self._sound_fire)

            self._sound_track = QCheckBox(
                "Tracking beeps (speeds up as bot closes on fire)"
            )
            self._sound_track.setChecked(True)
            self._sound_track.setToolTip(
                "Short beep paced by scrum phase:\n"
                "  SEARCH = silent\n"
                "  TRACK  = slow beep (800ms)\n"
                "  FIRE   = fast beep (200ms)"
            )
            layout.addWidget(self._sound_track)

            self._sound_profit = QCheckBox("P/L increase (coins dropping into bucket)")
            self._sound_profit.setChecked(True)
            self._sound_profit.setToolTip(
                "Synthesized 3-coin bucket drop plays on any trade\n"
                "event with realized profit > 0. Fires on grid and\n"
                "scrumming bots alike."
            )
            layout.addWidget(self._sound_profit)

            self._sound_drip = QCheckBox("Accumulation (water drip)")
            self._sound_drip.setChecked(True)
            self._sound_drip.setToolTip(
                "Water drip plays on FOLD events — the canonical\n"
                "Acervator accumulation moment (buying back more asset\n"
                "than was sold). Does not fire on SCRUM or DIST."
            )
            layout.addWidget(self._sound_drip)

            vol_row = QHBoxLayout()
            vol_row.addWidget(QLabel("SFX Volume:"))
            self._sound_volume = QSlider(Qt.Horizontal)
            self._sound_volume.setRange(0, 100)
            self._sound_volume.setValue(70)
            vol_row.addWidget(self._sound_volume)
            self._vol_label = QLabel("70%")
            self._sound_volume.valueChanged.connect(
                lambda v: self._vol_label.setText(f"{v}%")
            )
            # Volume is baked into each sample at synth time, so the
            # cache is cleared here.
            self._sound_volume.valueChanged.connect(self._on_sfx_volume_changed)
            vol_row.addWidget(self._vol_label)
            layout.addLayout(vol_row)

            from src.gui.main_tabs.settings_dialog_surface import SOUND_CONFIG_FIELDS

            for _key, name in SOUND_CONFIG_FIELDS:
                getattr(self, f"_{name}").toggled.connect(self._push_sound_config)

            test_row = QHBoxLayout()
            test_buy = QPushButton("Test Buy")
            test_buy.clicked.connect(lambda: self._test_sound("buy"))
            test_row.addWidget(test_buy)
            test_sell = QPushButton("Test Sell")
            test_sell.clicked.connect(lambda: self._test_sound("sell"))
            test_row.addWidget(test_sell)
            test_fire = QPushButton("Test Fire")
            test_fire.setToolTip("Play the sniper rifle SFX.")
            test_fire.clicked.connect(lambda: self._test_sound("fire"))
            test_row.addWidget(test_fire)
            test_track = QPushButton("Test Track")
            test_track.setToolTip("Play one tracking beep.")
            test_track.clicked.connect(lambda: self._test_sound("track"))
            test_row.addWidget(test_track)
            test_profit = QPushButton("Test Profit")
            test_profit.setToolTip("Play the coins-in-bucket SFX.")
            test_profit.clicked.connect(lambda: self._test_sound("profit"))
            test_row.addWidget(test_profit)
            test_drip = QPushButton("Test Drip")
            test_drip.setToolTip("Play the water-drip SFX.")
            test_drip.clicked.connect(lambda: self._test_sound("drip"))
            test_row.addWidget(test_drip)
            layout.addLayout(test_row)

            layout.addStretch()
            return w

        def _on_sfx_volume_changed(self, v: int) -> None:
            """Hand the engine this page's switches at volume ``v``, in percent.

            Each sample bakes its volume when it is made, so the engine's cache
            is dropped and the next ``play`` regenerates. The switches come from
            ``SOUND_CONFIG_FIELDS``, which is also what ``_sound_rows`` persists.
            """
            try:
                from src.core.sound_engine import SoundConfig, get_sound_engine
                from src.gui.main_tabs.settings_dialog_surface import (
                    SOUND_CONFIG_FIELDS,
                    VOLUME_SCALE,
                )

                asked = {
                    key: getattr(self, f"_{name}").isChecked()
                    for key, name in SOUND_CONFIG_FIELDS
                }
                se = get_sound_engine()
                se.update_config(SoundConfig(volume=v / VOLUME_SCALE, **asked))
                se._available = False
                se._cache = {}
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning("sound settings did not reach the engine: %s", _sf_exc)

        def _push_sound_config(self) -> None:
            """Hand the engine every switch at the volume the slider is showing.

            Wired to each sound box, so one box ticked on its own reaches the
            engine without the slider moving.
            """
            self._on_sfx_volume_changed(self._sound_volume.value())

        def _test_sound(self, name: str) -> None:
            from src.core.sound_engine import get_sound_engine

            self._push_sound_config()
            get_sound_engine().play(name)

        def _create_sms_tab(self) -> QWidget:
            from PySide6.QtWidgets import QFormLayout as QFL, QScrollArea

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            inner = QWidget()
            layout = QVBoxLayout(inner)
            layout.setSpacing(8)

            self._sms_enabled = QCheckBox("Enable SMS notifications")
            self._sms_enabled.setToolTip(
                "Send text messages to your phone for trading events"
            )
            layout.addWidget(self._sms_enabled)

            provider_group = QGroupBox("SMS Provider")
            pf = QFL(provider_group)
            pf.setSpacing(6)
            pf.setContentsMargins(8, 16, 8, 8)

            from src.core.sms_engine import CARRIER_GATEWAYS, FIELD_BOUNDS, SMSConfig
            from src.gui.main_tabs.settings_dialog_surface import SMS_PROVIDERS

            built = SMSConfig()

            self._sms_provider = QComboBox()
            self._sms_provider.setMinimumHeight(28)
            for label, value in SMS_PROVIDERS:
                self._sms_provider.addItem(label, value)
            pf.addRow("Provider:", self._sms_provider)

            self._sms_phone = QLineEdit()
            self._sms_phone.setMinimumHeight(28)
            self._sms_phone.setPlaceholderText("+15551234567")
            pf.addRow("Phone Number:", self._sms_phone)

            self._sms_twilio_sid = QLineEdit()
            self._sms_twilio_sid.setMinimumHeight(28)
            self._sms_twilio_sid.setPlaceholderText("AC...")
            pf.addRow("Twilio Account SID:", self._sms_twilio_sid)

            self._sms_twilio_token = QLineEdit()
            self._sms_twilio_token.setMinimumHeight(28)
            self._sms_twilio_token.setEchoMode(QLineEdit.Password)
            self._sms_twilio_token.setPlaceholderText(
                "Auth token from the Twilio console"
            )
            pf.addRow("Twilio Auth Token:", self._sms_twilio_token)

            self._sms_twilio_from = QLineEdit()
            self._sms_twilio_from.setMinimumHeight(28)
            self._sms_twilio_from.setPlaceholderText("+15559876543")
            pf.addRow("Twilio From Number:", self._sms_twilio_from)

            sep = QLabel("Email Gateway Settings")
            sep.setStyleSheet("color: #00cccc; font-weight: bold; margin-top: 6px;")
            pf.addRow(sep)

            self._sms_carrier = QComboBox()
            self._sms_carrier.setMinimumHeight(28)
            for carrier in CARRIER_GATEWAYS:
                self._sms_carrier.addItem(carrier)
            self._sms_carrier.currentIndexChanged.connect(
                lambda _at: self._fill_gateway_email()
            )
            pf.addRow("Carrier:", self._sms_carrier)

            self._sms_gateway = QLineEdit()
            self._sms_gateway.setMinimumHeight(28)
            self._sms_gateway.setPlaceholderText("5551234567@vtext.com")
            self._sms_gateway.setToolTip("Full email address for carrier SMS gateway")
            pf.addRow("Gateway Email:", self._sms_gateway)

            self._sms_smtp_user = QLineEdit()
            self._sms_smtp_user.setMinimumHeight(28)
            self._sms_smtp_user.setPlaceholderText("your.email@gmail.com")
            pf.addRow("SMTP Username:", self._sms_smtp_user)

            self._sms_smtp_pass = QLineEdit()
            self._sms_smtp_pass.setMinimumHeight(28)
            self._sms_smtp_pass.setEchoMode(QLineEdit.Password)
            self._sms_smtp_pass.setPlaceholderText(
                "App password (not regular password)"
            )
            pf.addRow("SMTP Password:", self._sms_smtp_pass)

            self._sms_smtp_server = QLineEdit()
            self._sms_smtp_server.setMinimumHeight(28)
            self._sms_smtp_server.setPlaceholderText(built.smtp_server)
            pf.addRow("Mail Server:", self._sms_smtp_server)

            self._sms_smtp_port = QSpinBox()
            self._sms_smtp_port.setMinimumHeight(28)
            self._sms_smtp_port.setRange(*FIELD_BOUNDS["smtp_port"])
            self._sms_smtp_port.setValue(built.smtp_port)
            pf.addRow("Mail Port:", self._sms_smtp_port)

            layout.addWidget(provider_group)

            events_group = QGroupBox("Notification Events")
            ef = QFL(events_group)
            ef.setSpacing(6)
            ef.setContentsMargins(8, 16, 8, 8)
            self._sms_buy = QCheckBox("Buy fills")
            self._sms_buy.setChecked(built.notify_buy_fills)
            ef.addRow(self._sms_buy)
            self._sms_sell = QCheckBox("Sell fills")
            self._sms_sell.setChecked(built.notify_sell_fills)
            ef.addRow(self._sms_sell)
            self._sms_state = QCheckBox("Bot state changes (start/stop/error)")
            self._sms_state.setChecked(built.notify_bot_state_changes)
            ef.addRow(self._sms_state)
            self._sms_errors = QCheckBox("API errors and failures")
            self._sms_errors.setChecked(built.notify_errors)
            ef.addRow(self._sms_errors)
            self._sms_pl = QCheckBox("P/L threshold alerts")
            ef.addRow(self._sms_pl)
            self._sms_pl_amount = QDoubleSpinBox()
            self._sms_pl_amount.setMinimumHeight(28)
            self._sms_pl_amount.setRange(*FIELD_BOUNDS["pl_threshold_amount"])
            self._sms_pl_amount.setValue(built.pl_threshold_amount)
            self._sms_pl_amount.setPrefix("$")
            ef.addRow("P/L threshold:", self._sms_pl_amount)
            self._sms_balance = QCheckBox("Low balance warnings")
            ef.addRow(self._sms_balance)
            self._sms_connection = QCheckBox("Exchange connection status")
            ef.addRow(self._sms_connection)

            layout.addWidget(events_group)

            rate_group = QGroupBox("Rate Limiting")
            rf = QFL(rate_group)
            rf.setSpacing(6)
            rf.setContentsMargins(8, 16, 8, 8)
            self._sms_max_hour = QSpinBox()
            self._sms_max_hour.setMinimumHeight(28)
            self._sms_max_hour.setRange(*FIELD_BOUNDS["max_messages_per_hour"])
            self._sms_max_hour.setValue(built.max_messages_per_hour)
            rf.addRow("Max messages per hour:", self._sms_max_hour)
            self._sms_cooldown = QSpinBox()
            self._sms_cooldown.setMinimumHeight(28)
            self._sms_cooldown.setRange(*FIELD_BOUNDS["cooldown_seconds"])
            self._sms_cooldown.setValue(built.cooldown_seconds)
            self._sms_cooldown.setSuffix(" sec")
            rf.addRow("Min time between messages:", self._sms_cooldown)
            layout.addWidget(rate_group)

            layout.addStretch()
            scroll.setWidget(inner)
            return scroll

        def _create_ai_monitor_tab(self) -> QWidget:
            from PySide6.QtWidgets import QScrollArea

            QFL = QFormLayout
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            inner = QWidget()
            layout = QVBoxLayout(inner)
            layout.setSpacing(12)

            api_group = QGroupBox("Claude API Connection")
            af = QFL(api_group)
            af.setSpacing(6)
            af.setContentsMargins(8, 16, 8, 8)

            self._ai_api_key = QLineEdit()
            self._ai_api_key.setMinimumHeight(28)
            self._ai_api_key.setEchoMode(QLineEdit.Password)
            self._ai_api_key.setPlaceholderText("sk-ant-api03-...")
            af.addRow("Anthropic API Key:", self._ai_api_key)

            self._ai_interval = QDoubleSpinBox()
            self._ai_interval.setMinimumHeight(28)
            self._ai_interval.setRange(0.5, 24.0)
            self._ai_interval.setValue(4.0)
            self._ai_interval.setSuffix(" hours")
            self._ai_interval.setDecimals(1)
            af.addRow("Check interval:", self._ai_interval)

            layout.addWidget(api_group)

            hs_group = QGroupBox("Handshake Authentication")
            hf = QFL(hs_group)
            hf.setSpacing(6)
            hf.setContentsMargins(8, 16, 8, 8)

            info = QLabel(
                "The connect phrase is embedded in the system prompt sent to Claude.\n"
                "The confirm phrase is what Claude must respond with to prove identity.\n"
                "Change both phrases together. Keep them secret."
            )
            info.setStyleSheet("color: #888; font-size: 10px;")
            info.setWordWrap(True)
            hf.addRow(info)

            self._ai_connect_phrase = QLineEdit()
            self._ai_connect_phrase.setMinimumHeight(28)
            self._ai_connect_phrase.setPlaceholderText("acervator-heapbuilder-live")
            hf.addRow("Connect phrase:", self._ai_connect_phrase)

            self._ai_confirm_phrase = QLineEdit()
            self._ai_confirm_phrase.setMinimumHeight(28)
            self._ai_confirm_phrase.setPlaceholderText("the-heap-grows-by-accumulation")
            hf.addRow("Confirm phrase:", self._ai_confirm_phrase)

            layout.addWidget(hs_group)

            bh_group = QGroupBox("Monitor Behavior")
            bf = QFL(bh_group)
            bf.setSpacing(6)
            bf.setContentsMargins(8, 16, 8, 8)

            self._ai_enabled = QCheckBox("Enable AI Monitor feedback loop")
            self._ai_enabled.setChecked(False)
            bf.addRow(self._ai_enabled)

            self._ai_auto_handshake = QCheckBox("Auto-handshake on first analysis")
            self._ai_auto_handshake.setChecked(True)
            bf.addRow(self._ai_auto_handshake)

            self._ai_log_feedback = QCheckBox("Log AI feedback to trade journal")
            self._ai_log_feedback.setChecked(True)
            bf.addRow(self._ai_log_feedback)

            layout.addWidget(bh_group)

            st_group = QGroupBox("Connection Status")
            sf = QFL(st_group)
            sf.setSpacing(4)
            sf.setContentsMargins(8, 16, 8, 8)

            self._ai_status = QLabel("Not connected")
            self._ai_status.setStyleSheet("color: #888; font-weight: bold;")
            sf.addRow("Status:", self._ai_status)

            self._ai_hash = QLabel("—")
            self._ai_hash.setStyleSheet("color: #666; font-family: Consolas;")
            sf.addRow("Journal hash:", self._ai_hash)

            self._ai_checks = QLabel("0")
            sf.addRow("Checks completed:", self._ai_checks)

            self._ai_test_btn = QPushButton("Test Handshake")
            self._ai_test_btn.setMinimumHeight(32)
            self._ai_test_btn.setStyleSheet(
                "background: #1a3a4a; color: #00ddff; border: 1px solid #00aacc; "
                "border-radius: 4px; font-weight: bold;"
            )
            self._ai_test_btn.clicked.connect(self._test_ai_handshake)
            sf.addRow(self._ai_test_btn)

            layout.addWidget(st_group)

            layout.addStretch()
            scroll.setWidget(inner)
            return scroll

        def _test_ai_handshake(self):
            """Trigger a test handshake (informational only — real handshake needs async)."""
            key = self._ai_api_key.text().strip()
            connect = self._ai_connect_phrase.text().strip()
            confirm = self._ai_confirm_phrase.text().strip()
            if not key:
                self._ai_status.setText("No API key entered")
                self._ai_status.setStyleSheet("color: #ff3366; font-weight: bold;")
                return
            if not connect or not confirm:
                self._ai_status.setText("Phrases required")
                self._ai_status.setStyleSheet("color: #ff3366; font-weight: bold;")
                return
            self._ai_status.setText("Settings saved — handshake runs on next bot cycle")
            self._ai_status.setStyleSheet("color: #00ddff; font-weight: bold;")

        def _show_text(self, combo: QComboBox, value: object) -> None:
            """Shows ``value`` in a drop-down, by its row or as typed text.

            A fixed list that does not offer ``value`` keeps the row it is on.
            """
            at = combo.findText(str(value))
            if at >= 0:
                combo.setCurrentIndex(at)
            elif combo.isEditable():
                combo.setCurrentText(str(value))

        def _show_data(self, combo: QComboBox, value: object) -> None:
            """Shows the drop-down row carrying ``value``, or keeps the row it is on."""
            at = combo.findData(value)
            if at >= 0:
                combo.setCurrentIndex(at)

        def _stored_rows(self) -> tuple:
            """Every setting this dialog persists at the top level of the store.

            One row carries the store key, the read off its control, the write
            back into that control, and what stands in for a store without the
            key. ``_save`` and ``_load_current`` walk these same rows, so no row
            can be written without also being loaded.
            """
            from src.gui.main_tabs.settings_dialog_surface import (
                ACCENT_DEFAULT,
                LOCK_CANDLE_DEFAULT,
                PHANTOM_TIMEFRAME_DEFAULT,
            )

            return (
                (
                    "username",
                    lambda: self._username.text().strip(),
                    self._username.setText,
                    "",
                ),
                (
                    "default_target_balance",
                    self._default_balance.value,
                    self._default_balance.setValue,
                    200.0,
                ),
                (
                    "bot_visibility",
                    self._visibility.currentText,
                    lambda value: self._show_text(self._visibility, value),
                    "orderbook",
                ),
                (
                    "aggressive_trading",
                    self._aggressive.isChecked,
                    lambda value: self._aggressive.setChecked(bool(value)),
                    False,
                ),
                (
                    "default_enable_phantoms",
                    self._phantoms_enabled.isChecked,
                    lambda value: self._phantoms_enabled.setChecked(bool(value)),
                    True,
                ),
                (
                    "default_phantom_timeframe",
                    self._phantom_timeframe.currentData,
                    lambda value: self._show_data(self._phantom_timeframe, value),
                    PHANTOM_TIMEFRAME_DEFAULT,
                ),
                (
                    "default_lock_candle_count",
                    self._lock_candles.value,
                    lambda value: self._lock_candles.setValue(int(value)),
                    LOCK_CANDLE_DEFAULT,
                ),
                (
                    "theme",
                    self._theme_combo.currentData,
                    lambda value: self._show_data(self._theme_combo, value),
                    "cyberpunk_dark",
                ),
                (
                    "accent_color",
                    lambda: self._accent_color.text().strip(),
                    self._accent_color.setText,
                    ACCENT_DEFAULT,
                ),
            )

        def _stored_groups(self) -> tuple:
            """Every group this dialog persists as one key, with the rows inside it.

            A row reads and writes the same way a ``_stored_rows`` row does.
            """
            from src.core.sms_engine import SETTINGS_GROUP as MESSAGE_CHANNELS_GROUP_KEY

            return (
                (
                    "ai_monitor",
                    (
                        (
                            "api_key",
                            lambda: self._ai_api_key.text().strip(),
                            self._ai_api_key.setText,
                            "",
                        ),
                        (
                            "interval_hours",
                            self._ai_interval.value,
                            self._ai_interval.setValue,
                            4.0,
                        ),
                        (
                            "connect_phrase",
                            lambda: self._ai_connect_phrase.text().strip(),
                            self._ai_connect_phrase.setText,
                            "",
                        ),
                        (
                            "confirm_phrase",
                            lambda: self._ai_confirm_phrase.text().strip(),
                            self._ai_confirm_phrase.setText,
                            "",
                        ),
                        (
                            "enabled",
                            self._ai_enabled.isChecked,
                            lambda value: self._ai_enabled.setChecked(bool(value)),
                            False,
                        ),
                        (
                            "auto_handshake",
                            self._ai_auto_handshake.isChecked,
                            lambda value: self._ai_auto_handshake.setChecked(
                                bool(value)
                            ),
                            True,
                        ),
                        (
                            "log_feedback",
                            self._ai_log_feedback.isChecked,
                            lambda value: self._ai_log_feedback.setChecked(bool(value)),
                            True,
                        ),
                    ),
                ),
                ("ta_indicator_weights", self._ta_weight_rows()),
                ("sound", self._sound_rows()),
                (MESSAGE_CHANNELS_GROUP_KEY, self._sms_rows()),
            )

        def _fill_gateway_email(self) -> None:
            """Build the Gateway Email row from the carrier and the typed number.

            A number the carrier's gateway cannot address, and the manual choice,
            both leave the row as the operator left it.
            """
            from src.core.sms_engine import gateway_address

            built = gateway_address(
                self._sms_carrier.currentText(), self._sms_phone.text()
            )
            if built:
                self._sms_gateway.setText(built)

        def _sms_rows(self) -> tuple:
            """One ``_stored_groups`` row per SMS page control.

            ``SMS_CONFIG_FIELDS`` pairs each ``SMSConfig`` field with the control
            carrying it, and the control's spec kind decides how a row reads it.
            """
            from src.core.sms_engine import SMSConfig
            from src.gui.main_tabs.settings_dialog_surface import (
                CHECK,
                COMBO_DATA,
                COMBO_TEXT,
                DOUBLE_SPIN,
                LINE,
                SMS_CONFIG_FIELDS,
                spec_for,
            )

            built = SMSConfig()

            def pick_text(box) -> Callable[[object], None]:
                # findText and setCurrentIndex are the two calls both builds'
                # drop-downs answer; isEditable is Qt's alone.
                def put(value: object) -> None:
                    at = box.findText(str(value))
                    if at >= 0:
                        box.setCurrentIndex(at)

                return put

            def row(key: str, name: str) -> tuple:
                box = getattr(self, f"_{name}")
                fallback = getattr(built, key)
                kind = spec_for(name)["kind"]
                if kind == CHECK:
                    return (
                        key,
                        box.isChecked,
                        lambda value: box.setChecked(bool(value)),
                        fallback,
                    )
                if kind == LINE:
                    return (key, lambda: box.text().strip(), box.setText, fallback)
                if kind == COMBO_DATA:
                    return (
                        key,
                        box.currentData,
                        lambda value: self._show_data(box, value),
                        fallback,
                    )
                if kind == COMBO_TEXT:
                    return (key, box.currentText, pick_text(box), fallback)
                if kind == DOUBLE_SPIN:
                    return (
                        key,
                        box.value,
                        lambda value: box.setValue(float(value)),
                        fallback,
                    )
                return (
                    key,
                    box.value,
                    lambda value: box.setValue(int(value)),
                    fallback,
                )

            return tuple(row(key, name) for key, name in SMS_CONFIG_FIELDS)

        def _sound_rows(self) -> tuple:
            """One ``_stored_groups`` row per sound switch, plus the volume.

            The slider shows whole percent and ``SoundConfig.volume`` holds a
            fraction, so the volume row divides out and multiplies back.
            """
            from src.core.sound_engine import SoundConfig
            from src.gui.main_tabs.settings_dialog_surface import (
                SOUND_CONFIG_FIELDS,
                VOLUME_SCALE,
            )

            built = SoundConfig()

            def show(box) -> Callable[[object], None]:
                return lambda value: box.setChecked(bool(value))

            switches = tuple(
                (
                    key,
                    getattr(self, f"_{name}").isChecked,
                    show(getattr(self, f"_{name}")),
                    getattr(built, key),
                )
                for key, name in SOUND_CONFIG_FIELDS
            )
            return switches + (
                (
                    "volume",
                    lambda: self._sound_volume.value() / VOLUME_SCALE,
                    lambda value: self._sound_volume.setValue(
                        int(round(float(value) * VOLUME_SCALE))
                    ),
                    built.volume,
                ),
            )

        def _ta_weight_rows(self) -> tuple:
            """One ``_stored_groups`` row per indicator weight slider.

            A slider holds the weight times ``TA_SLIDER_SCALE``, so a row reads
            the weight out of the position and writes the position back in.
            """
            from src.gui.main_tabs.settings_dialog_surface import TA_SLIDER_SCALE
            from src.trading.ta_engine import DEFAULT_WEIGHTS

            def read(name: str) -> Callable[[], float]:
                return lambda: (self._ta_weight_sliders[name].value() / TA_SLIDER_SCALE)

            def show(name: str) -> Callable[[object], None]:
                return lambda value: self._ta_weight_sliders[name].setValue(
                    int(round(float(value) * TA_SLIDER_SCALE))
                )

            return tuple(
                (name, read(name), show(name), figure)
                for name, figure in DEFAULT_WEIGHTS.items()
            )

        def _show_stored(
            self, key: str, show: Callable[[object], None], value: object
        ) -> None:
            """Puts one stored value into its control.

            A value the control refuses leaves that control on its build figure
            and names ``key`` in the log, so one unreadable entry in the
            settings file cannot stop the dialog opening.
            """
            try:
                show(value)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Settings kept the default for %s: %s", key, exc)

        def _load_current(self) -> None:
            if not self._sm:
                return
            for key, _read, show, fallback in self._stored_rows():
                self._show_stored(key, show, self._sm.get(key, fallback))
            for group, rows in self._stored_groups():
                stored = self._sm.get(group, {})
                for key, _read, show, fallback in rows:
                    self._show_stored(f"{group}.{key}", show, stored.get(key, fallback))
            for exch in self._sm.list_exchanges():
                _eid = (exch.get("exchange_id", "") or "").lower()
                if not acs.serves(_eid, self._wing):
                    continue
                self._list_exchange_once(_eid)
            self._push_sound_config()

        def _save(self) -> None:
            """Save all settings and close. ALWAYS closes the dialog."""
            import sys

            print("[SETTINGS] _save called", file=sys.stderr, flush=True)

            if not self._sm:
                print(
                    "[SETTINGS] No settings manager, closing",
                    file=sys.stderr,
                    flush=True,
                )
                self.accept()
                return

            # A setting that fails to save never blocks the close.
            pairs = {key: read for key, read, _show, _fallback in self._stored_rows()}
            saved = 0
            failed: list[str] = []
            for key, getter in pairs.items():
                try:
                    self._sm.set(key, getter())
                    saved += 1
                except Exception as e:
                    failed.append(f"{key} ({e})")
                    print(f"[SETTINGS ERROR] {key}: {e}", file=sys.stderr, flush=True)

            for group, rows in self._stored_groups():
                try:
                    self._sm.set(
                        group,
                        {key: read() for key, read, _show, _fallback in rows},
                    )
                    saved += 1
                except Exception as e:
                    failed.append(f"{group} ({e})")
                    print(f"[SETTINGS ERROR] {group}: {e}", file=sys.stderr, flush=True)

            try:
                self.settings_changed.emit()
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning(
                    "settings save step failed — a field may not have persisted: %s",
                    _sf_exc,
                )

            try:
                if self._status_log:
                    if failed:
                        self._status_log.log(
                            f"Settings PARTIALLY saved: {saved} ok, "
                            f"{len(failed)} FAILED — {'; '.join(failed)}",
                            "error",
                        )
                    else:
                        self._status_log.log(
                            f"Settings saved ({saved} groups).", "success"
                        )
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning(
                    "settings save step failed — a field may not have persisted: %s",
                    _sf_exc,
                )

            print(
                f"[SETTINGS] Saved {saved} groups, closing dialog",
                file=sys.stderr,
                flush=True,
            )

            # Wrapped and last: a message box must not be able to
            # strand the dialog open.
            if failed:
                try:
                    QMessageBox.warning(
                        self,
                        "Settings partially saved",
                        f"{saved} setting group(s) saved, but "
                        f"{len(failed)} FAILED and were discarded:\n\n"
                        + "\n".join(f"  • {f}" for f in failed)
                        + "\n\nThese values are NOT persisted and will "
                        "revert when the dialog is reopened.",
                    )
                except Exception as _mb_exc:  # noqa: BLE001
                    logger.warning("could not show partial-save warning: %s", _mb_exc)

            self.accept()
