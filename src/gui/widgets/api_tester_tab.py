"""Isolated exchange API tester. Touches no bot and no live credential."""

from __future__ import annotations

import asyncio
import logging
import time

from ...core.safe_url import SafeRequest, safe_urlopen
from .. import design_system as ds
from ..qt_safe_events import safe_process_events

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # API Tester Tab - isolated exchange testing
    # ---------------------------------------------------------------
    class APITesterTab(QWidget):
        """Standalone API testing tool. Fully isolated from the bot system."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._connector = None
            self._connected = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)

            # --- Connection panel ---
            conn_group = QGroupBox(
                "Exchange Connection (Isolated - does not affect bots)"
            )
            conn_layout = QVBoxLayout(conn_group)
            conn_layout.setContentsMargins(6, 14, 6, 6)
            conn_layout.setSpacing(4)

            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Exchange:"))
            self._exchange = QComboBox()
            from ...exchange.ccxt_connector import SUPPORTED_EXCHANGES

            for eid in sorted(SUPPORTED_EXCHANGES.keys()):
                self._exchange.addItem(eid.capitalize(), eid)
            row1.addWidget(self._exchange)
            self._use_stored = QCheckBox("Use stored credentials")
            self._use_stored.setChecked(True)
            self._use_stored.setToolTip(
                "Use API keys saved in Settings instead of entering manually"
            )
            self._use_stored.toggled.connect(
                lambda on: self._manual_frame.setVisible(not on)
            )
            row1.addWidget(self._use_stored)
            conn_layout.addLayout(row1)

            self._manual_frame = QFrame()
            ml = QHBoxLayout(self._manual_frame)
            ml.setContentsMargins(0, 0, 0, 0)
            ml.setSpacing(4)
            self._api_key = QLineEdit()
            self._api_key.setPlaceholderText("API Key")
            self._api_key.setEchoMode(QLineEdit.Password)
            ml.addWidget(self._api_key)
            self._api_secret = QLineEdit()
            self._api_secret.setPlaceholderText("API Secret")
            self._api_secret.setEchoMode(QLineEdit.Password)
            ml.addWidget(self._api_secret)
            self._api_pp = QLineEdit()
            self._api_pp.setPlaceholderText("Passphrase (if needed)")
            self._api_pp.setEchoMode(QLineEdit.Password)
            ml.addWidget(self._api_pp)
            self._manual_frame.setVisible(False)
            conn_layout.addWidget(self._manual_frame)

            row2 = QHBoxLayout()
            self._connect_btn = QPushButton("Connect")
            self._connect_btn.setToolTip(
                "Establish isolated connection to exchange API"
            )
            self._connect_btn.clicked.connect(self._do_connect)
            row2.addWidget(self._connect_btn)
            self._disconnect_btn = QPushButton("Disconnect")
            self._disconnect_btn.clicked.connect(self._do_disconnect)
            self._disconnect_btn.setEnabled(False)
            row2.addWidget(self._disconnect_btn)
            self._conn_status = QLabel("Not connected")
            self._conn_status.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
            row2.addWidget(self._conn_status)
            conn_layout.addLayout(row2)
            layout.addWidget(conn_group)

            # --- Operations + Results ---
            ops_splitter = QSplitter(Qt.Horizontal)
            ops_splitter.setHandleWidth(5)
            ops_splitter.setChildrenCollapsible(False)

            btn_group = QGroupBox("API Operations")
            btn_layout = QVBoxLayout(btn_group)
            btn_layout.setContentsMargins(6, 14, 6, 6)
            btn_layout.setSpacing(3)

            self._symbol_input = QLineEdit("BTC/USDT")
            self._symbol_input.setToolTip(
                "Trading pair for ticker, orderbook, OHLCV queries"
            )
            btn_layout.addWidget(self._symbol_input)

            tests = [
                ("Fetch Markets", "fetch_markets", "Load all trading pairs"),
                ("Fetch Ticker", "fetch_ticker", "Current bid/ask/last price"),
                (
                    "Fetch Balances",
                    "fetch_balances",
                    "Account balances (requires auth)",
                ),
                ("Fetch Order Book", "fetch_orderbook", "Top 20 bids and asks"),
                ("Fetch OHLCV (1h x50)", "fetch_ohlcv", "50 hourly candles"),
                ("Fetch Open Orders", "fetch_open_orders", "Currently open orders"),
                ("Fetch My Trades", "fetch_trades", "Recent trade history"),
            ]
            for label, cmd, tip in tests:
                btn = QPushButton(label)
                btn.setToolTip(tip)
                btn.clicked.connect(lambda _checked, c=cmd: self._run_test(c))
                btn_layout.addWidget(btn)

            # Diagnostic tools (bypass CCXT)
            sep = QLabel("--- Diagnostics ---")
            sep.setStyleSheet(f"color: {ds.TEXT_PLACEHOLDER}; margin-top: 6px;")
            sep.setAlignment(Qt.AlignCenter)
            btn_layout.addWidget(sep)

            raw_btn = QPushButton("Raw HTTP Probe")
            raw_btn.setToolTip(
                "Bypass CCXT and make a direct HTTP request to the exchange.\n"
                "Shows exact HTTP status, headers, and response body.\n"
                "Use this to diagnose connection failures."
            )
            raw_btn.clicked.connect(self._raw_http_probe)
            btn_layout.addWidget(raw_btn)

            status_btn = QPushButton("Exchange Status Page")
            status_btn.setToolTip("Check if the exchange reports any known outages")
            status_btn.clicked.connect(self._check_exchange_status)
            btn_layout.addWidget(status_btn)

            btn_layout.addStretch()
            ops_splitter.addWidget(btn_group)

            result_group = QGroupBox("Response")
            rl = QVBoxLayout(result_group)
            rl.setContentsMargins(6, 14, 6, 6)
            self._result_info = QLabel("")
            self._result_info.setWordWrap(True)
            rl.addWidget(self._result_info)
            # DPA: Q-001 exception — _result_view displays exchange-test
            # result bursts (HTML formatting useful; content short), not a
            # streaming log. QPlainTextEdit not appropriate here.
            self._result_view = QTextEdit()
            self._result_view.setReadOnly(True)
            self._result_view.setPlaceholderText(
                "Connect to an exchange and run a test..."
            )
            rl.addWidget(self._result_view)
            ops_splitter.addWidget(result_group)
            ops_splitter.setSizes([250, 750])
            layout.addWidget(ops_splitter)

        def _log(
            self, title: str, detail: str, elapsed: float = 0, level: str = "info"
        ):
            colors = {
                "info": ds.STATUS_INFO,
                "success": ds.SUCCESS,
                "warning": ds.WARNING,
                "error": ds.ERROR,
            }
            color = colors.get(level, ds.TEXT_NEUTRAL)
            timing = f" ({elapsed:.0f}ms)" if elapsed > 0 else ""
            self._result_info.setText(f"{title}{timing}")
            self._result_info.setStyleSheet(f"color: {color}; font-weight: bold;")
            import time as _t

            ts = _t.strftime("%H:%M:%S")
            self._result_view.append(
                f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                f'<span style="color:{color}"><b>{title}</b>{timing}</span><br>'
                f'<pre style="color:{ds.TEXT_NEUTRAL}; margin:0; '
                f'white-space:pre-wrap;">{detail}</pre><br>'
            )
            self._result_view.verticalScrollBar().setValue(
                self._result_view.verticalScrollBar().maximum()
            )

        def _get_settings(self):
            p = self.parent()
            while p:
                if hasattr(p, "_settings"):
                    return p._settings
                p = p.parent()
            return None

        def _do_connect(self):
            import time as _t

            eid = self._exchange.currentData()
            # 10.9 -- the two values apitest.16.001 reads, bound
            # BEFORE the try so the `finally` can read them on every
            # exit path, including the two early returns inside the
            # try. `_call_s` stays None until `sync_connect` returns,
            # so a path that never reached the network carries no
            # duration rather than a fabricated one.
            #
            # `_supplied` IS A PRESENCE BOOLEAN AND NOTHING ELSE. It
            # says a non-empty key and a non-empty secret were
            # resolved. No length, no prefix, no hash: this record is
            # serialised to ~/.acervator_logs/signals/ and the
            # operator trades real money on those keys.
            _supplied = False
            _call_s = None
            self._conn_status.setText(f"Connecting to {eid.capitalize()}...")
            self._conn_status.setStyleSheet(f"color: {ds.STATUS_INFO};")
            self._connect_btn.setEnabled(False)

            safe_process_events("legacy P4.1 site")

            try:
                from ...exchange.ccxt_connector import CCXTConnector

                if self._use_stored.isChecked():
                    sm = self._get_settings()
                    if not sm:
                        self._log("ERROR", "Settings not available", level="error")
                        return
                    exch = None
                    for e in sm.list_exchanges():
                        if e.get("exchange_id") == eid:
                            exch = e
                            break
                    if not exch or not exch.get("api_key_enc"):
                        self._log(
                            "NO CREDENTIALS",
                            f"No stored credentials for {eid.capitalize()}.\n"
                            f"Uncheck 'Use stored credentials' to enter manually,\n"
                            f"or add the exchange in Settings.",
                            level="error",
                        )
                        return
                    from ...core.encryption import decrypt

                    master = f"qat_{sm.get('username', 'user')}_vault"
                    key = decrypt(exch["api_key_enc"], master)
                    secret = decrypt(exch["api_secret_enc"], master)
                    pp = (
                        decrypt(exch["passphrase_enc"], master)
                        if exch.get("passphrase_enc")
                        else ""
                    )
                else:
                    key = self._api_key.text().strip()
                    secret = self._api_secret.text().strip()
                    pp = self._api_pp.text().strip()
                    if not key or not secret:
                        self._log("ERROR", "Enter API key and secret", level="error")
                        return

                _supplied = bool(key) and bool(secret)
                conn = CCXTConnector(eid)
                start = _t.monotonic()
                conn.sync_connect(key, secret, pp)
                elapsed = (_t.monotonic() - start) * 1000
                _call_s = elapsed / 1000.0
                try:
                    mcount = (
                        len(conn._ccxt.markets)
                        if conn._ccxt and conn._ccxt.markets
                        else 0
                    )
                except Exception:
                    mcount = None
                # A count nothing read shows the mark, never a measured zero.
                shown = "?" if mcount is None else str(mcount)

                self._connector = conn
                self._connected = True
                self._connect_btn.setEnabled(False)
                self._disconnect_btn.setEnabled(True)
                self._conn_status.setText(
                    f"Connected: {eid.capitalize()} ({shown} markets)"
                )
                self._conn_status.setStyleSheet(f"color: {ds.SUCCESS};")
                self._log(
                    f"CONNECTED to {eid.capitalize()}",
                    f"Markets: {shown}\n"
                    f"Auth: not checked - press Fetch Balances\n"
                    f"This connection is isolated from bots.",
                    elapsed,
                    "success",
                )
                # Register history callback if the trade history tab is available
                try:
                    main_win = self.window()
                    if (
                        hasattr(main_win, "_trade_history_tab")
                        and main_win._trade_history_tab is not None
                    ):
                        conn.set_history_callback(
                            main_win._trade_history_tab.get_history_callback()
                        )
                        # Register all active bot symbols for scanning
                        if hasattr(main_win, "_bot_manager") and main_win._bot_manager:
                            main_win._bot_manager.set_connector(conn)
                except Exception as _e:
                    logger.debug("History callback registration: %s", _e)
            except Exception as exc:
                from ...exchange.ccxt_connector import CCXTConnector as CC

                self._conn_status.setText("Failed")
                self._conn_status.setStyleSheet(f"color: {ds.ERROR};")
                self._log(
                    "CONNECTION FAILED", CC._format_exchange_error(exc), level="error"
                )
            finally:
                if not self._connected:
                    self._connect_btn.setEnabled(True)
                # 10.9 -- apitest.16.001. THE LABEL IS ALL THE
                # OPERATOR HAS. A connect that paints "Connected"
                # while holding no session leaves every later button
                # failing against a tab that says the link is up.
                #
                # `expected` IS WHAT THE OPERATOR WAS TOLD, read back
                # off `_conn_status` after the handler wrote it.
                # `actual` IS WHETHER A SESSION EXISTS: the connector
                # reference, the tab's own flag, and the connector's
                # `_ex` -- the property every later call resolves
                # through. `sync_connect` returning without an
                # exchange instance is the false green this pin is
                # for. No argument to this method is read back as a
                # result.
                #
                # IN THE `finally` SO EVERY EXIT IS ON THE RECORD.
                # Both early returns inside the try leave the label on
                # "Connecting to ...", which does not start with
                # "Connected", so they report an honest green rather
                # than nothing at all.
                #
                # NO CREDENTIAL REACHES THIS RECORD. `key`, `secret`
                # and `pp` are not read here in any form -- not the
                # value, not a length, not a hash. A length leaks and
                # a hash of a short secret is brute-forceable. One
                # PRESENCE BOOLEAN rides in the context:
                # `credentials_supplied` says a key AND a secret were
                # resolved and says nothing else, and it is what tells
                # a refusal for missing credentials apart from a
                # refusal by the venue.
                #
                # THE DURATION IS THE `sync_connect` BRACKET ONLY
                # (E8), and it is None on every path that never
                # reached the call.
                #
                # NO `every=`: the Connect button is the cadence, so
                # silence from this pin says nothing about the tab.
                _session = getattr(self._connector, "_ex", None)
                _usable = (
                    self._connector is not None
                    and self._connected
                    and _session is not None
                )
                _claims = self._conn_status.text().startswith("Connected")
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _api_emit

                    _api_emit(
                        "apitest.16.001.postcondition.label_matches_session",
                        actual=_usable,
                        expected=_claims,
                        context={
                            "exchange": eid,
                            "used_stored_credentials": bool(
                                self._use_stored.isChecked()
                            ),
                            "credentials_supplied": _supplied,
                            "connector_held": self._connector is not None,
                            "disconnect_enabled": self._disconnect_btn.isEnabled(),
                        },
                        duration=_call_s,
                    )

        def _do_disconnect(self):
            # 10.9 -- the state apitest.16.002 reads on every exit
            # path, bound before the branch that fills it. `failure`
            # MOVED UP from inside the branch and nothing else about
            # it changed: it was already initialised to None there,
            # and the pin below has to be able to read it when there
            # was no connector to close.
            #
            # THE CONTEXT READ IS GUARDED AND THE VERDICT IS NOT.
            # `_exchange` is the ONE attribute this pin needs that the
            # method did not need before it, so reading it bare turned
            # instrumentation into a PRECONDITION ON THE HOST: a caller
            # that binds this method onto an object without that widget
            # used to run and would now raise AttributeError. A pin may
            # never make its host need more than it did -- the same
            # rule `emit` itself follows. The guard covers the whole
            # read, a missing attribute and a deleted C++ widget alike,
            # and the cost of a miss is ONE CONTEXT FIELD falling to
            # None. `actual`, `expected`, `ok` and the duration do not
            # read it, so on a real tab -- which has the widget -- the
            # record is byte for byte the one it was.
            import contextlib

            _eid = None
            with contextlib.suppress(Exception):
                _eid = self._exchange.currentData()
            _held = self._connector is not None
            _close_s = None
            failure = None
            if self._connector:
                # Suppression audit 2026-08-13, H3. Two layers
                # used to lose the failure: the worker exception
                # died with the executor because nothing read the
                # Future, and anything the handler could still see
                # was dropped by a bare pass. The connector
                # reference is discarded either way and the label
                # below reads "Disconnected", so an unreported
                # failure leaves a session open that nothing can
                # close and a display that asserts the opposite.
                try:
                    import concurrent.futures

                    _close_at = time.monotonic()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(asyncio.run, self._connector.disconnect())
                    # The executor's __exit__ waits for the worker, so
                    # this reading spans the whole close attempt and
                    # not the submit. It stays None if the executor
                    # itself could not be built.
                    _close_s = time.monotonic() - _close_at
                    failure = fut.exception()
                except Exception as exc:
                    logger.exception("API tester: disconnect call failed")
                    failure = exc
                if failure is not None:
                    self._log(
                        "DISCONNECT FAILED",
                        f"{type(failure).__name__}: {failure}\n"
                        "The exchange session may still be open. "
                        "The connector reference is dropped either "
                        "way, so nothing can close it from here.",
                        level="error",
                    )
                self._connector = None
            self._connected = False
            self._connect_btn.setEnabled(True)
            self._disconnect_btn.setEnabled(False)
            self._conn_status.setText("Disconnected")
            self._conn_status.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
            # A close that never ran must not report a closed connection.
            if _held:
                self._log("DISCONNECTED", "Connection closed", level="info")
            else:
                self._log(
                    "NOTHING TO CLOSE",
                    "No session was open, so no close was attempted.",
                    level="info",
                )
            # 10.9 -- apitest.16.002, AND IT IS THE ONE THAT MATTERS
            # MOST IN THIS TAB. The label two lines above reads
            # "Disconnected" whatever happened and the connector
            # reference is dropped either way, so a close that failed
            # leaves an AUTHENTICATED SESSION open that nothing can
            # reach and a display that asserts the opposite. The
            # method's own comment above says exactly that; nothing
            # recorded it.
            #
            # `expected` IS THE CLAIM ON SCREEN, read off the label.
            # `actual` IS WHETHER THE SESSION WAS RELEASED: the close
            # raised nothing, the reference is gone and the flag is
            # down. A failed close therefore reports red while the
            # screen reads "Disconnected", which is the whole point.
            #
            # THE CONTEXT CARRIES THE ERROR'S CLASS NAME AND NEVER ITS
            # MESSAGE. A venue error message quotes request parameters
            # and some echo the key, and this record goes to disk.
            #
            # THE DURATION SPANS THE CLOSE ATTEMPT (E8) and is None
            # when there was no connector to close.
            #
            # NO `every=`: the Disconnect button is the cadence.
            _released = (
                failure is None and self._connector is None and not self._connected
            )
            _claims_closed = self._conn_status.text().startswith("Disconnected")
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _api_emit

                _api_emit(
                    "apitest.16.002.postcondition.session_released",
                    actual=_released,
                    expected=_claims_closed,
                    context={
                        "exchange": _eid,
                        "connector_held": _held,
                        "failure_class": (
                            type(failure).__name__ if failure is not None else ""
                        ),
                    },
                    duration=_close_s,
                )

        def _run_test(self, test: str):
            if not self._connected or not self._connector:
                self._log("ERROR", "Connect first", level="error")
                return
            import time as _t, json

            sym = self._symbol_input.text().strip()
            self._log(f"Running {test}...", f"Symbol: {sym}", level="info")

            safe_process_events("legacy P4.1 site")

            # Use sync exchange (no asyncio/aiohttp)
            c = getattr(self._connector, "_ccxt_sync", self._connector._ccxt)

            # Started OUTSIDE the try. The failure handler below reads
            # `start` to report how long the call took before it broke;
            # binding it as the try's first statement left that read
            # depending on the binding itself having succeeded, so the
            # error report could raise instead of printing the error.
            # Nothing runs between here and the try, so the elapsed
            # figure is the same number it was.
            start = _t.monotonic()
            # 10.9 -- apitest.16.003's OBSERVABLE, and it is one
            # token. The dispatch chain's last arm answers a name it
            # does not know with an empty dict, and the success path
            # below then logs "<test> OK" -- the operator reads a pass
            # for a call that never happened. Binding that arm to a
            # sentinel changes no value, no type and no branch: `{}`
            # is still `{}`, still empty, and still renders as `{}`.
            # It lets the pin read the RESULT to tell a real answer
            # from the do-nothing arm, instead of reading the `test`
            # argument back in as though it were a result.
            _nothing: dict = {}
            try:
                if test == "fetch_markets":
                    m = c.markets
                    syms = sorted(str(k) for k in m)[:50]
                    result = {
                        "total": len(m),
                        "spot": sum(
                            1
                            for v in m.values()
                            if isinstance(v, dict) and v.get("type") == "spot"
                        ),
                        "first_50": syms,
                    }
                elif test == "fetch_ticker":
                    result = c.fetch_ticker(sym)
                elif test == "fetch_balances":
                    result = c.fetch_balance()
                elif test == "fetch_orderbook":
                    result = c.fetch_order_book(sym, limit=20)
                elif test == "fetch_ohlcv":
                    d = c.fetch_ohlcv(sym, "1h", limit=50)

                    def _close(rows, at):
                        """One end candle's close, or the mark when it has none."""
                        if not rows:
                            return 0
                        row = rows[at]
                        if isinstance(row, (list, tuple)) and len(row) > 4:
                            return row[4]
                        return "?"

                    result = {
                        "candles": len(d),
                        "latest_close": _close(d, -1),
                        "oldest_close": _close(d, 0),
                    }
                elif test == "fetch_open_orders":
                    result = c.fetch_open_orders(sym)
                elif test == "fetch_trades":
                    result = c.fetch_my_trades(sym, limit=20)
                else:
                    result = _nothing

                elapsed = (_t.monotonic() - start) * 1000

                def _positive(section):
                    """One balance section: zero dropped, unreadable marked."""
                    found = {}
                    for k, v in section.items():
                        if not v:
                            continue
                        try:
                            reading = float(v)
                        except (TypeError, ValueError):
                            found[k] = "?"
                            continue
                        if reading > 0:
                            found[k] = v
                    return found

                if isinstance(result, dict):
                    for _name in ("free", "used", "total"):
                        if _name in result and isinstance(result[_name], dict):
                            result[_name] = _positive(result[_name])
                    display = json.dumps(result, indent=2, default=str)
                    if len(display) > 3000:
                        display = display[:3000] + "\n... (truncated)"
                elif isinstance(result, list):
                    display = f"[{len(result)} items]\n" + json.dumps(
                        result[:5], indent=2, default=str
                    )
                    if len(result) > 5:
                        display += f"\n... and {len(result) - 5} more"
                else:
                    display = str(result)
                # A name no arm answered never reached the venue, so it
                # reports NOT RUN rather than a green OK headline.
                if result is _nothing:
                    display = (
                        "This screen has no call by that name, "
                        "so the venue was never asked."
                    )
                    self._log(f"{test} NOT RUN", display, elapsed, "warning")
                else:
                    self._log(f"{test} OK", display, elapsed, "success")
                # 10.9 -- apitest.16.003. A GREEN HEADLINE OVER A CALL
                # THAT NEVER RAN is the failure shape this tab has:
                # the chain above answers an unrecognised name with an
                # empty dict and falls straight through to the success
                # log.
                #
                # `expected` IS THE HEADLINE THE OPERATOR READS, taken
                # back off `_result_info` after `_log` painted it, not
                # from the string handed to `_log`. `actual` IS
                # WHETHER AN ARM RAN, read off the result object's own
                # identity.
                #
                # NO OPERATOR FREE TEXT IN THE CONTEXT. `test` is the
                # fixed vocabulary the seven buttons pass. The symbol
                # box is NOT recorded: this tab has three password
                # fields one row above it, and free text typed in this
                # tab is exactly what must never reach a file.
                #
                # THE DURATION IS THE CALL BRACKET (E8), and it is
                # None on the arm that ran nothing.
                #
                # NO `every=`: each test button press is one record.
                _ran = result is not _nothing
                _headline = self._result_info.text()
                _claimed_ok = _headline.split(" (")[0].endswith(" OK")
                _entries = len(result) if isinstance(result, (dict, list)) else 1
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _api_emit

                    _api_emit(
                        "apitest.16.003.postcondition.reported_ok_ran_a_test",
                        actual=_ran,
                        expected=_claimed_ok,
                        context={
                            "exchange": self._exchange.currentData(),
                            "test": test,
                            "result_kind": type(result).__name__,
                            "result_entries": _entries,
                            "truncated": "(truncated)" in display,
                        },
                        duration=(elapsed / 1000.0 if _ran else None),
                    )
            except Exception as exc:
                elapsed = (_t.monotonic() - start) * 1000
                from ...exchange.ccxt_connector import CCXTConnector as CC

                self._log(
                    f"{test} FAILED", CC._format_exchange_error(exc), elapsed, "error"
                )

        def _raw_http_probe(self):
            """Bypass CCXT entirely. Direct HTTP + SSL diagnostics."""
            import time as _t, json, ssl, socket

            eid = self._exchange.currentData()

            # --- SSL Diagnostic first ---
            host_map = {
                "coinbase": "api.coinbase.com",
                "binance": "api.binance.com",
                "kraken": "api.kraken.com",
                "kucoin": "api.kucoin.com",
                "bybit": "api.bybit.com",
                "okx": "www.okx.com",
            }
            host = host_map.get(eid, f"api.{eid}.com")

            self._log(
                "SSL DIAGNOSTIC",
                f"Testing SSL/TLS connection to {host}:443...",
                level="info",
            )

            safe_process_events("legacy P4.1 site")

            # Test 1: Raw TCP connection
            try:
                start = _t.monotonic()
                sock = socket.create_connection((host, 443), timeout=10)
                tcp_elapsed = (_t.monotonic() - start) * 1000
                sock.close()
                self._log(
                    f"TCP OK ({tcp_elapsed:.0f}ms)",
                    f"Connected to {host}:443",
                    level="success",
                )
            except Exception as exc:
                self._log(
                    "TCP FAILED",
                    f"Cannot reach {host}:443 - {exc}\nThis is a network/firewall issue, not an API issue.",
                    level="error",
                )
                return

            safe_process_events("legacy P4.1 site")

            # Test 2: SSL handshake with default certs
            try:
                start = _t.monotonic()
                ctx = ssl.create_default_context()
                with socket.create_connection((host, 443), timeout=10) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                        ssl_elapsed = (_t.monotonic() - start) * 1000
                        cert = ssock.getpeercert()
                        subject = dict(x[0] for x in cert.get("subject", []))
                        issuer = dict(x[0] for x in cert.get("issuer", []))
                        self._log(
                            f"SSL OK ({ssl_elapsed:.0f}ms)",
                            f"Protocol: {ssock.version()}\n"
                            f"Cipher: {ssock.cipher()[0]}\n"
                            f"Server CN: {subject.get('commonName', '?')}\n"
                            f"Issuer: {issuer.get('organizationName', '?')}\n"
                            f"Not After: {cert.get('notAfter', '?')}",
                            level="success",
                        )
            except ssl.SSLCertVerificationError as exc:
                self._log(
                    "SSL CERT FAILED",
                    f"Python cannot verify the SSL certificate for {host}.\n"
                    f"Error: {exc}\n"
                    f"FIX: Run 'pip install --upgrade certifi' then rebuild.\n"
                    f"This is why CCXT fails but your browser works - browsers use\n"
                    f"the Windows certificate store, Python uses its own CA bundle.",
                    level="error",
                )
            except Exception as exc:
                self._log("SSL FAILED", f"{type(exc).__name__}: {exc}", level="error")

            safe_process_events("legacy P4.1 site")

            # Test 3: SSL with certifi (if available)
            try:
                import certifi

                start = _t.monotonic()
                ctx2 = ssl.create_default_context(cafile=certifi.where())
                with socket.create_connection((host, 443), timeout=10) as sock:
                    with ctx2.wrap_socket(sock, server_hostname=host) as ssock:
                        ssl_elapsed = (_t.monotonic() - start) * 1000
                        self._log(
                            f"SSL+certifi OK ({ssl_elapsed:.0f}ms)",
                            f"Certifi CA bundle: {certifi.where()}\n"
                            f"Protocol: {ssock.version()}",
                            level="success",
                        )
            except ImportError:
                self._log(
                    "certifi NOT INSTALLED",
                    "Install with: pip install certifi\nThis provides CA certificates Python needs on Windows.",
                    level="warning",
                )
            except Exception as exc:
                self._log(
                    "SSL+certifi FAILED", f"{type(exc).__name__}: {exc}", level="error"
                )

            safe_process_events("legacy P4.1 site")

            # --- HTTP endpoint probes ---
            probes = {
                "coinbase": [
                    (
                        "GET",
                        "https://api.coinbase.com/api/v3/brokerage/market/products",
                        "v3 Public Products (what CCXT uses)",
                    ),
                    (
                        "GET",
                        "https://api.coinbase.com/v2/currencies",
                        "v2 Currencies (legacy)",
                    ),
                    (
                        "GET",
                        "https://api.exchange.coinbase.com/products",
                        "Exchange Products (alt)",
                    ),
                ],
                "binance": [
                    (
                        "GET",
                        "https://api.binance.com/api/v3/exchangeInfo",
                        "Exchange Info",
                    ),
                    ("GET", "https://api.binance.com/api/v3/ping", "Ping"),
                ],
                "kraken": [
                    (
                        "GET",
                        "https://api.kraken.com/0/public/SystemStatus",
                        "System Status",
                    ),
                    (
                        "GET",
                        "https://api.kraken.com/0/public/AssetPairs",
                        "Asset Pairs",
                    ),
                ],
            }
            default_probe = [("GET", f"https://api.{eid}.com", "Root endpoint")]
            endpoints = probes.get(eid, default_probe)

            self._log(
                "HTTP PROBES", f"Testing {len(endpoints)} endpoints...", level="info"
            )
            safe_process_events("legacy P4.1 site")

            import urllib.error

            # Use certifi for SSL if available
            ssl_ctx = None
            try:
                import certifi

                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ssl_ctx = ssl.create_default_context()

            # 10.9 -- apitest.16.004's ledger. `_green` counts the
            # SUCCESS headlines the operator sees; `_green_with_body`
            # counts how many of those really carried bytes off the
            # socket. They are incremented on the same path but under
            # DIFFERENT conditions, so a 200 with an empty body moves
            # one and not the other.
            _green = 0
            _green_with_body = 0
            _attempted = 0
            _statuses: list = []
            _sweep_at = _t.monotonic()
            for method, url, desc in endpoints:
                _attempted += 1
                try:
                    start = _t.monotonic()
                    # SafeRequest refuses any scheme outside the
                    # http/https allowlist AT CONSTRUCTION. The probe
                    # table above is all https literals, but the
                    # fallback entry builds its host from the selected
                    # exchange id, so the string reaching here is not a
                    # constant and nothing downstream re-reads its
                    # scheme before the open.
                    req = SafeRequest(url)
                    req.add_header("User-Agent", "Acervator/1.8 (diagnostic)")
                    req.add_header("Accept", "application/json")

                    with safe_urlopen(req, timeout=10, context=ssl_ctx) as resp:
                        elapsed = (_t.monotonic() - start) * 1000
                        status = resp.status
                        headers = dict(resp.headers)
                        read_back = resp.read()
                        if isinstance(read_back, (bytes, bytearray)):
                            body = read_back.decode("utf-8", errors="replace")
                        elif isinstance(read_back, str):
                            body = read_back
                        else:
                            body = f"[body is {type(read_back).__name__}, not text]"

                        # Truncate body for display
                        if len(body) > 1000:
                            body_display = body[:1000] + "\n... (truncated)"
                        else:
                            body_display = body

                        # Try to parse as JSON for pretty display
                        try:
                            parsed = json.loads(body)
                            if isinstance(parsed, dict):
                                keys = list(parsed.keys())[:10]
                                body_display = f"JSON keys: {keys}\n"
                                if isinstance(parsed.get("products"), list):
                                    body_display += (
                                        f"Products count: {len(parsed['products'])}\n"
                                    )
                                body_display += json.dumps(parsed, indent=2)[:800]
                        except json.JSONDecodeError:
                            pass

                        # A status nothing read shows the mark, and the
                        # line must not paint like a measured pass.
                        unread = status is None
                        shown = "?" if unread else str(status)
                        detail = (
                            f"Endpoint: {desc}\n"
                            f"URL: {url}\n"
                            f"HTTP Status: {shown}\n"
                            f"Content-Type: {headers.get('Content-Type', 'unknown')}\n"
                            f"Content-Length: {headers.get('Content-Length', 'unknown')}\n"
                            f"Response:\n{body_display}"
                        )
                        if unread:
                            detail += (
                                "\nNo HTTP status came back, so nothing here"
                                " says the request succeeded."
                            )
                        self._log(
                            f"HTTP {shown} - {desc}",
                            detail,
                            elapsed,
                            "warning" if unread else "success",
                        )
                        _green += 1
                        _statuses.append(status)
                        if body:
                            _green_with_body += 1

                except urllib.error.HTTPError as exc:
                    elapsed = (_t.monotonic() - start) * 1000
                    body = ""
                    try:  # noqa: SIM105
                        body = exc.read().decode("utf-8", errors="replace")[:500]
                    except Exception:  # noqa: S110
                        pass
                    detail = (
                        f"Endpoint: {desc}\n"
                        f"URL: {url}\n"
                        f"HTTP Status: {exc.code}\n"
                        f"Reason: {exc.reason}\n"
                        f"Response Body: {body}"
                    )
                    self._log(f"HTTP {exc.code} - {desc}", detail, elapsed, "error")

                except urllib.error.URLError as exc:
                    elapsed = (_t.monotonic() - start) * 1000
                    detail = (
                        f"Endpoint: {desc}\n"
                        f"URL: {url}\n"
                        f"Error: {exc.reason}\n"
                        f"This means the request never reached the server.\n"
                        f"Check: DNS resolution, firewall, VPN, proxy settings."
                    )
                    self._log(f"UNREACHABLE - {desc}", detail, elapsed, "error")

                except Exception as exc:
                    elapsed = (_t.monotonic() - start) * 1000
                    self._log(
                        f"ERROR - {desc}",
                        f"URL: {url}\n{type(exc).__name__}: {exc}",
                        elapsed,
                        "error",
                    )

                safe_process_events("legacy P4.1 site")

            # 10.9 -- apitest.16.004. A GREEN PROBE THAT READ NOTHING.
            # The success branch reports `HTTP <status>` from the
            # response object and then prints whatever `read()`
            # returned, so an endpoint that answers 200 with an empty
            # body paints the same green line as one that returned the
            # product list -- and the operator uses this button
            # precisely when nothing else works.
            #
            # `expected` IS THE NUMBER OF GREENS SHOWN.  `actual` IS
            # HOW MANY OF THEM CARRIED BYTES. Neither side is the
            # endpoint table read back: a probe that raised is in
            # neither count, and `attempted` rides in the context so a
            # reader sees the sweep's own size.
            #
            # THE DURATION IS THE SWEEP (E8) -- the loop above and
            # nothing else. The SSL and TCP diagnostics before it are
            # separate operations with their own log lines.
            #
            # NO `every=`: the Raw HTTP Probe button is the cadence.
            _sweep_s = _t.monotonic() - _sweep_at
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _api_emit

                _api_emit(
                    "apitest.16.004.postcondition.green_probe_read_a_body",
                    actual=_green_with_body,
                    expected=_green,
                    context={
                        "exchange": eid,
                        "host": host,
                        "endpoints": len(endpoints),
                        "attempted": _attempted,
                        "http_statuses": _statuses,
                        "not_green": _attempted - _green,
                    },
                    duration=_sweep_s,
                )

        def _check_exchange_status(self):
            """Check exchange status pages for known outages."""
            import time as _t, json

            eid = self._exchange.currentData()

            status_urls = {
                "coinbase": "https://status.coinbase.com/api/v2/status.json",
                "binance": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&pageNo=1&pageSize=1",
                "kraken": "https://status.kraken.com/api/v2/status.json",
            }

            # 10.9 -- the vocabulary apitest.16.005 judges the
            # fetched document against. Statuspage publishes
            # `status.indicator` as one of none / minor / major /
            # critical; `maintenance` is carried too because some
            # pages report it, and a value the venue never sends costs
            # nothing while a missing one would paint a false red.
            _mappable = ("none", "minor", "major", "critical", "maintenance")

            url = status_urls.get(eid)
            if not url:
                self._log(
                    "STATUS",
                    f"No known status page for {eid.capitalize()}",
                    level="warning",
                )
                return

            self._log(
                "CHECKING STATUS",
                f"Querying {eid.capitalize()} status page...",
                level="info",
            )

            safe_process_events("legacy P4.1 site")

            try:
                start = _t.monotonic()
                # Same allowlist as the probe path above. Here the URL
                # is always one of the three https literals in
                # status_urls (the `if not url: return` above rules out
                # anything else), so the check can only ever pass — but
                # it is the check, not the table, that makes that true
                # for a reader and for the next entry added to it.
                req = SafeRequest(url)
                req.add_header("User-Agent", "Acervator/1.8")
                req.add_header("Accept", "application/json")
                with safe_urlopen(req, timeout=10) as resp:
                    elapsed = (_t.monotonic() - start) * 1000
                    read_back = resp.read()
                    if isinstance(read_back, (bytes, bytearray)):
                        body = read_back.decode("utf-8", errors="replace")
                    elif isinstance(read_back, str):
                        body = read_back
                    else:
                        body = f"[body is {type(read_back).__name__}, not text]"
                    data = json.loads(body)

                    if isinstance(data, dict) and "status" in data:
                        s = data["status"] if isinstance(data["status"], dict) else {}
                        indicator = s.get("indicator", "unknown")
                        desc = s.get("description", "unknown")
                        detail = (
                            f"Exchange: {eid.capitalize()}\n"
                            f"Status: {str(indicator).upper()}\n"
                            f"Description: {desc}\n"
                            f"Raw: {json.dumps(data, indent=2)[:500]}"
                        )
                        # A word this screen has no mapping for was
                        # never read as an outage, so it paints amber.
                        if indicator in ("none", "minor"):
                            level = "success"
                        elif indicator in _mappable:
                            level = "error"
                        else:
                            level = "warning"
                        self._log(f"STATUS: {desc}", detail, elapsed, level)
                        # 10.9 -- apitest.16.005. THE VERDICT IS
                        # DERIVED FROM A WORD THE TAB MAY NOT KNOW.
                        # The line above maps `none` and `minor` to
                        # green and EVERYTHING ELSE to red, so a
                        # missing field (which `get` answers with
                        # "unknown") or a renamed one paints an outage
                        # the venue never declared, and the operator
                        # stops trading on it.
                        #
                        # `actual` IS THE WORD THE DOCUMENT CARRIED,
                        # read back out of the parsed body and capped
                        # at 32 characters because it is untrusted
                        # venue text. `expected` is the vocabulary,
                        # and `ok` is membership -- the two sides are
                        # not the same expression.
                        #
                        # THE DURATION SPANS THE FETCH AND THE PARSE
                        # (E8). It is this pin's own reading and does
                        # not touch the `elapsed` the log line shows.
                        #
                        # NO `every=`: the Exchange Status Page button
                        # is the cadence.
                        _ind_seen = str(s.get("indicator", ""))[:32]
                        _fetch_s = _t.monotonic() - start
                        import contextlib

                        with contextlib.suppress(Exception):
                            from src.core.signal_contract import emit as _api_emit

                            _api_emit(
                                "apitest.16.005.postcondition.indicator_is_mappable",
                                actual=_ind_seen,
                                expected=_mappable,
                                ok=_ind_seen in _mappable,
                                context={
                                    "exchange": eid,
                                    "http_status": getattr(resp, "status", None),
                                    "body_bytes": len(body),
                                    "level_shown": level,
                                },
                                duration=_fetch_s,
                            )
                    else:
                        self._log(
                            "STATUS", json.dumps(data, indent=2)[:800], elapsed, "info"
                        )

            except Exception as exc:
                self._log(
                    "STATUS CHECK FAILED", f"{type(exc).__name__}: {exc}", level="error"
                )
