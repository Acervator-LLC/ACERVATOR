"""
testnet_tab.py — Acervator Local Testnet GUI Tab
=================================================
In-platform block explorer for the local testnet.

Panels:
  • Chain status bar (block number, tx count, ACRV minted)
  • Run Competition button (auto-runs a full 3-bot demo)
  • Block explorer (latest blocks + transactions)
  • Event log (all emitted contract events)
  • Token supply dashboard (holders, tier distribution)
  • Oracle price controls (set mock prices for testing)
"""

from __future__ import annotations

import time
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QGroupBox,
        QSplitter,
        QTextEdit,
        QFrame,
        QScrollArea,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox,
        QSizePolicy,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QBrush

    _QT = True
except ImportError:
    _QT = False

if _QT:
    from ..competition.local_testnet import LocalTestnet

# ── Style ─────────────────────────────────────────────────────────────────────
CYAN = "#00FFEE"
GREEN = "#00FF88"
AMBER = "#FFAA00"
RED = "#FF3355"
MAGENTA = "#FF00AA"
MUTED = "#8899BB"
PANEL = "#080818"

TIER_COLORS = {
    "Harvest": GREEN,
    "Gold Fold": AMBER,
    "Bear Slayer": RED,
    "Grand Accumulator": CYAN,
    "Ekthelius": MAGENTA,
}


def _section(title: str) -> QGroupBox:
    g = QGroupBox(title.upper())
    g.setStyleSheet(f"""
        QGroupBox {{
            border: 1px solid rgba(0,255,238,0.15); border-radius:6px;
            margin-top:14px; background:{PANEL};
        }}
        QGroupBox::title {{
            subcontrol-origin:margin; left:10px;
            color:{CYAN}; font-family:Orbitron; font-size:9px; letter-spacing:3px;
        }}
    """)
    return g


def _lbl(text: str, color: str = MUTED, size: int = 10, bold: bool = False) -> QLabel:
    l = QLabel(text)
    w = "bold" if bold else "normal"
    l.setStyleSheet(
        f"color:{color}; font-family:Consolas; font-size:{size}px; font-weight:{w};"
    )
    return l


def _table(cols: list[str], max_h: int = 180) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setMaximumHeight(max_h)
    t.setStyleSheet(f"""
        QTableWidget {{ background:{PANEL}; color:#C0D0E8;
                        font-family:Consolas; font-size:10px;
                        border:none; gridline-color:rgba(0,255,238,0.07); }}
        QTableWidget::item:selected {{ background:rgba(0,255,238,0.08); }}
        QHeaderView::section {{ background:#0A0A20; color:{MUTED};
                                 font-family:Orbitron; font-size:8px;
                                 letter-spacing:2px; border:none;
                                 border-bottom:1px solid rgba(0,255,238,0.15);
                                 padding:4px; }}
    """)
    return t


def _add_row(tbl: QTableWidget, values: list, colors: list[str] = None):
    r = tbl.rowCount()
    tbl.insertRow(r)
    for c, v in enumerate(values):
        item = QTableWidgetItem(str(v))
        item.setTextAlignment(Qt.AlignCenter)
        if colors and c < len(colors) and colors[c]:
            item.setForeground(QBrush(QColor(colors[c])))
        tbl.setItem(r, c, item)
    tbl.scrollToBottom()


if _QT:

    class TestnetTab(QWidget):
        """Local testnet block explorer and competition runner."""

        def __init__(self, parent=None, shared_testnet=None, bridge=None):
            """Construct the Local Testnet tab.

            If `shared_testnet` + `bridge` are provided (v3.12.0+
            path via MainWindow), the tab uses the shared instance —
            Nuclear-mode PoA activity will populate the display.

            If not provided (legacy standalone path), falls back to
            a private LocalTestnet for self-contained operation.
            """
            super().__init__(parent)
            self.setAccessibleName("Testnet Tab")
            from ..competition.local_testnet import LocalTestnet

            self._testnet = shared_testnet or LocalTestnet()
            self._bridge = bridge
            self._comp_count = 0
            self._setup_ui()

            # Auto-refresh every 3s regardless of source
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_all)
            self._timer.start(3000)

            # If bridge is present, subscribe to live updates so the
            # tab reacts instantly instead of waiting for the 3s poll
            if self._bridge is not None:
                try:
                    self._bridge.chain_updated.connect(self._refresh_all)
                    self._bridge.chain_reset.connect(
                        lambda reason: self._msg(f"⚠ Chain reset: {reason}", "#ffaa00")
                    )
                except Exception:
                    pass  # sadp: R61 ACCEPT — bridge may
                # already have these signals connected from a prior
                # construction. Qt raises on duplicate connect; we don't
                # need Qt.UniqueConnection here because the tab itself
                # is singleton (created once at main_window init).

        def _refresh_all(self):
            """Run every refresh method. v3.13.1 — R28 FL applied.
            Previously four layers of `except Exception: pass` silently
            swallowed any refresh failure, leading to empty tables with
            no diagnostic trail. This pattern caused MEM-125, MEM-127,
            MEM-139 all to hide. Now: log the first 3 failures per
            method to stderr + acervator.testnet logger.  sadp: R28 FL
            """
            import sys, logging

            log = logging.getLogger("acervator.testnet")
            for name, fn in [
                ("stats", self._refresh_stats),
                ("blocks", self._refresh_blocks),
                ("events", self._refresh_events),
                ("holders", self._refresh_holders),
            ]:
                try:
                    fn()
                except Exception as exc:
                    k = f"_refresh_{name}_fails"
                    n = getattr(self, k, 0)
                    if n < 3:
                        setattr(self, k, n + 1)
                        sys.stderr.write(
                            f"TestnetTab._refresh_{name}: "
                            f"{type(exc).__name__}: {exc}\n"
                        )
                        if n == 0:
                            import traceback

                            traceback.print_exc(file=sys.stderr)
                        try:
                            log.error(
                                "_refresh_%s failed (%s): %s",
                                name,
                                type(exc).__name__,
                                exc,
                            )
                        except Exception:
                            pass  # sadp: R61 ACCEPT —
                        # logging module itself broken; stderr write
                        # above already surfaced, looping would risk
                        # recursive logger-failure spam.

        def _setup_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(10, 8, 10, 8)
            root.setSpacing(6)

            # ── Header ────────────────────────────────────────────────────────
            hdr = QHBoxLayout()
            ttl = QLabel("Local Testnet")
            ttl.setStyleSheet(
                f"color:{CYAN}; font-family:Orbitron; font-size:14px; font-weight:900;"
            )
            hdr.addWidget(ttl)
            hdr.addStretch()
            self._net_lbl = _lbl(
                "● ACERVATOR LOCAL TESTNET  ·  Chain ID 84532", GREEN, 10
            )
            hdr.addWidget(self._net_lbl)
            root.addLayout(hdr)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("color:rgba(0,255,238,0.15);")
            root.addWidget(sep)

            # ── Status bar ────────────────────────────────────────────────────
            stat = _section("Chain Status")
            stat_lay = stat.layout() or QVBoxLayout(stat)
            self._stat_row = QHBoxLayout()
            self._stat_vals: dict = {}
            for key in [
                "Block",
                "Transactions",
                "Events",
                "Competitions",
                "ACRV Minted",
                "Remaining",
            ]:
                col = QVBoxLayout()
                lk = _lbl(key.upper(), MUTED, 9)
                lk.setAlignment(Qt.AlignCenter)
                vk = _lbl("—", CYAN, 14, bold=True)
                vk.setAlignment(Qt.AlignCenter)
                col.addWidget(lk)
                col.addWidget(vk)
                self._stat_row.addLayout(col)
                self._stat_vals[key] = vk
            stat_lay.addLayout(self._stat_row)
            root.addWidget(stat)

            # ── Run competition controls ───────────────────────────────────────
            run_box = _section("Run Competition")
            run_lay = run_box.layout() or QVBoxLayout(run_box)
            ctrl_row = QHBoxLayout()

            ctrl_row.addWidget(_lbl("Bots:", MUTED, 10))
            self._n_bots = QSpinBox()
            self._n_bots.setRange(2, 8)
            self._n_bots.setValue(3)
            self._n_bots.setFixedWidth(55)
            self._n_bots.setStyleSheet(
                f"background:#0A0A20; color:{CYAN}; border:1px solid rgba(0,255,238,0.2); padding:3px;"
            )
            ctrl_row.addWidget(self._n_bots)

            ctrl_row.addWidget(_lbl("Symbol:", MUTED, 10))
            self._sym = QComboBox()
            self._sym.addItems(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
            self._sym.setFixedWidth(100)
            self._sym.setStyleSheet(
                f"background:#0A0A20; color:{CYAN}; border:1px solid rgba(0,255,238,0.2);"
            )
            ctrl_row.addWidget(self._sym)

            ctrl_row.addWidget(_lbl("Season:", MUTED, 10))
            self._season = QSpinBox()
            self._season.setRange(1, 20)
            self._season.setValue(1)
            self._season.setFixedWidth(55)
            self._season.setStyleSheet(
                f"background:#0A0A20; color:{CYAN}; border:1px solid rgba(0,255,238,0.2); padding:3px;"
            )
            ctrl_row.addWidget(self._season)

            ctrl_row.addStretch()

            self._run_btn = QPushButton("⚔  Run Competition")
            self._run_btn.setStyleSheet(
                f"background:rgba(0,255,238,0.08); color:{CYAN}; "
                f"border:1px solid {CYAN}; font-family:Orbitron; "
                f"font-size:10px; padding:8px 20px; border-radius:4px;"
            )
            self._run_btn.clicked.connect(self._run_competition)
            ctrl_row.addWidget(self._run_btn)

            self._stress_btn = QPushButton("⚡ Stress Test ×10")
            self._stress_btn.setStyleSheet(
                f"background:rgba(255,170,0,0.08); color:{AMBER}; "
                f"border:1px solid {AMBER}; font-family:Orbitron; "
                f"font-size:10px; padding:8px 20px; border-radius:4px;"
            )
            self._stress_btn.clicked.connect(self._stress_test)
            ctrl_row.addWidget(self._stress_btn)

            # Reset Chain — wipes memory + persistence file with confirm
            self._reset_btn = QPushButton("⟲  Reset Chain")
            self._reset_btn.setStyleSheet(
                f"background:rgba(255,60,100,0.08); color:{RED}; "
                f"border:1px solid {RED}; font-family:Orbitron; "
                f"font-size:10px; padding:8px 16px; border-radius:4px;"
            )
            self._reset_btn.clicked.connect(self._reset_chain)
            ctrl_row.addWidget(self._reset_btn)

            run_lay.addLayout(ctrl_row)

            # Oracle price control
            oracle_row = QHBoxLayout()
            oracle_row.addWidget(_lbl("Oracle BTC/USD:", MUTED, 10))
            self._btc_price = QDoubleSpinBox()
            self._btc_price.setRange(1000, 200000)
            self._btc_price.setValue(62000)
            self._btc_price.setDecimals(0)
            self._btc_price.setFixedWidth(90)
            self._btc_price.setStyleSheet(
                f"background:#0A0A20; color:{AMBER}; border:1px solid rgba(255,170,0,0.2); padding:3px;"
            )
            self._btc_price.valueChanged.connect(
                lambda v: self._testnet.set_mock_price("BTC/USDT", v)
            )
            oracle_row.addWidget(self._btc_price)
            oracle_row.addStretch()
            run_lay.addLayout(oracle_row)
            root.addWidget(run_box)

            # ── Splitter: blocks + events ──────────────────────────────────────
            split = QSplitter(Qt.Horizontal)
            split.setHandleWidth(5)
            split.setChildrenCollapsible(False)

            # Block explorer
            blk_box = _section("Block Explorer")
            blk_lay = blk_box.layout() or QVBoxLayout(blk_box)
            self._block_tbl = _table(["Block", "Txs", "Hash", "Age"], max_h=160)
            blk_lay.addWidget(self._block_tbl)
            split.addWidget(blk_box)

            # Transaction log
            tx_box = _section("Transaction Log")
            tx_lay = tx_box.layout() or QVBoxLayout(tx_box)
            self._tx_tbl = _table(["Tx Hash", "Function", "From", "Gas"], max_h=160)
            tx_lay.addWidget(self._tx_tbl)
            split.addWidget(tx_box)

            root.addWidget(split)

            # ── Event log ─────────────────────────────────────────────────────
            evt_box = _section("Contract Events")
            evt_lay = evt_box.layout() or QVBoxLayout(evt_box)
            self._evt_tbl = _table(["Block", "Event", "Details"], max_h=150)
            evt_lay.addWidget(self._evt_tbl)
            root.addWidget(evt_box)

            # ── Token holders ──────────────────────────────────────────────────
            tok_box = _section("Token Holders")
            tok_lay = tok_box.layout() or QVBoxLayout(tok_box)
            self._tok_tbl = _table(["Wallet", "Balance (ACRV)", "Tier"], max_h=130)
            tok_lay.addWidget(self._tok_tbl)
            root.addWidget(tok_box)

            # ── Log ───────────────────────────────────────────────────────────
            log_box = _section("Testnet Log")
            log_lay = log_box.layout() or QVBoxLayout(log_box)
            self._log = QTextEdit()
            self._log.setReadOnly(True)
            self._log.setMaximumHeight(120)
            self._log.setStyleSheet(
                f"background:#050510; color:#8899BB; "
                f"font-family:Consolas; font-size:10px; border:none;"
            )
            log_lay.addWidget(self._log)
            root.addWidget(log_box)

            self._refresh_stats()

        def _msg(self, text: str, color: str = MUTED):
            ts = time.strftime("%H:%M:%S")
            fmt = (
                f'<span style="color:#445566">[{ts}]</span> '
                f'<span style="color:{color}">{text}</span>'
            )
            self._log.append(fmt)

        def _refresh_stats(self):
            s = self._testnet.get_competition_stats()
            mapping = {
                "Block": str(s["block_number"]),
                "Transactions": str(s["total_transactions"]),
                "Events": str(s["total_events"]),
                "Competitions": str(s["total_competitions"]),
                "ACRV Minted": f"{s['acrv_total_supply']:,.0f}",
                "Remaining": f"{s['acrv_remaining']:,.0f}",
            }
            for k, v in mapping.items():
                if k in self._stat_vals:
                    self._stat_vals[k].setText(v)

        def _reset_chain(self):
            """Wipe in-memory chain + delete persistence file.
            Confirmation required because it's destructive."""
            from PySide6.QtWidgets import QMessageBox

            resp = QMessageBox.question(
                self,
                "Reset Chain?",
                "This will permanently delete all block history, "
                "transactions, token balances, and competition records "
                "on the local testnet.\n\n"
                "The persisted chain file will also be deleted.\n\n"
                "This cannot be undone. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return
            if self._bridge is not None:
                self._bridge.reset(reason="user clicked Reset Chain")
                self._msg("Chain reset via bridge.", AMBER)
            else:
                # Standalone fallback — no bridge, no persistence
                from ..competition.local_testnet import LocalTestnet

                self._testnet.__dict__.update(LocalTestnet().__dict__)
                self._msg("Chain reset (in-memory only).", AMBER)
            self._refresh_all()

        def _run_competition(self):
            self._run_btn.setEnabled(False)
            self._msg("Starting competition...", CYAN)
            # If bridge is available, queue through the shared worker —
            # writes land on the same chain as Nuclear-mode PoA rounds.
            # Otherwise legacy inline path (standalone use).
            if self._bridge is not None:
                from .shared_testnet import CompetitionRequest

                req = CompetitionRequest(
                    symbol=self._sym.currentText(),
                    season=self._season.value(),
                    n_bots=self._n_bots.value(),
                )
                try:
                    # v3.12.3 — Qt.UniqueConnection is 0x80, NOT 3.
                    # Value 3 = BlockingQueuedConnection (can deadlock).
                    from PySide6.QtCore import Qt

                    self._bridge.competition_completed.connect(
                        self._on_bridge_competition, type=Qt.UniqueConnection
                    )
                except Exception:
                    pass  # sadp: R61 ACCEPT — already
                # connected. Qt.UniqueConnection raises TypeError if
                # the signal is already connected to this slot, which
                # is the EXPECTED path on every subsequent button press.
                self._bridge.request_competition(req)
                return  # button re-enabled in _on_bridge_competition
            try:
                result = self._testnet.run_demo_competition(
                    n_bots=self._n_bots.value(),
                    season=self._season.value(),
                    symbol=self._sym.currentText(),
                )
                self._comp_count += 1
                self._msg(f"Competition {result['competition_id']} complete!", GREEN)
                self._msg(
                    f"  Winner: {result['winner_wallet'][:14]}...  "
                    f"Tier: {result['winner_tier']}  "
                    f"Awarded: {result['tokens_awarded']:,} ACRV",
                    GREEN,
                )
                self._msg(f"  Adj tx: {result['adj_tx_hash'][:20]}...", MUTED)
                self._refresh_all()
            except Exception as e:
                self._msg(f"Error: {e}", RED)
                import traceback

                traceback.print_exc()
            finally:
                self._run_btn.setEnabled(True)

        def _on_bridge_competition(self, result: dict):
            """Bridge callback when any queued competition finishes.
            Re-enables the run button and logs the outcome.

            v3.13.1 — added explicit _refresh_all() call. Previously
            relied solely on the 3s auto-refresh timer and the
            chain_updated signal, but screenshot evidence from user
            showed tables stayed empty for >1 minute after a successful
            competition. Surfaces a diagnostic tail to figure out why.
            """
            self._run_btn.setEnabled(True)
            self._stress_btn.setEnabled(True)
            if "error" in result:
                self._msg(f"Competition failed: {result['error']}", RED)
                return
            self._comp_count += 1
            self._msg(
                f"Competition {result.get('competition_id','?')} complete!", GREEN
            )
            self._msg(
                f"  Winner: {str(result.get('winner_wallet',''))[:14]}…  "
                f"Tier: {result.get('winner_tier','?')}  "
                f"Awarded: {result.get('tokens_awarded',0):,} ACRV",
                GREEN,
            )
            # Explicit refresh — R28 FL  (the prior reliance on 3s
            # timer + chain_updated signal was not observably firing
            # for the user in v3.13.0)
            self._refresh_all()

        def _stress_test(self):
            self._stress_btn.setEnabled(False)
            self._msg("Running 10 competitions...", AMBER)
            if self._bridge is not None:
                from .shared_testnet import CompetitionRequest

                try:
                    from PySide6.QtCore import Qt

                    self._bridge.competition_completed.connect(
                        self._on_bridge_competition, type=Qt.UniqueConnection
                    )
                except Exception:
                    pass  # sadp: R61 ACCEPT — already
                # connected. Same rationale as the single-run path above.
                for _ in range(10):
                    self._bridge.request_competition(
                        CompetitionRequest(
                            symbol=self._sym.currentText(),
                            season=self._season.value(),
                            n_bots=3,
                        )
                    )
                return  # workers run sequentially via drain loop
            try:
                for i in range(10):
                    self._testnet.run_demo_competition(
                        n_bots=3,
                        season=self._season.value(),
                        symbol=self._sym.currentText(),
                    )
                s = self._testnet.get_competition_stats()
                self._msg(
                    f"10 competitions done. "
                    f"Total minted: {s['acrv_total_supply']:,.0f} ACRV / "
                    f"{s['acrv_remaining']:,.0f} remaining.",
                    GREEN,
                )
                tiers = s.get("tier_counts", {})
                if tiers:
                    self._msg(
                        "  Tier distribution: "
                        + ", ".join(f"{k}: {v}" for k, v in tiers.items()),
                        AMBER,
                    )
                self._refresh_all()
            except Exception as e:
                self._msg(f"Stress test error: {e}", RED)
            finally:
                self._stress_btn.setEnabled(True)

        def _refresh_blocks(self):
            self._block_tbl.setRowCount(0)
            self._tx_tbl.setRowCount(0)
            for blk in self._testnet.chain.latest_blocks[:15]:
                age = int(time.time() - blk.timestamp)
                _add_row(
                    self._block_tbl,
                    [
                        str(blk.number),
                        str(len(blk.transactions)),
                        blk.hash[:18] + "...",
                        f"{age}s ago",
                    ],
                    [CYAN, AMBER, MUTED, MUTED],
                )
            for tx in list(reversed(list(self._testnet.chain._txs.values())))[:15]:
                _add_row(
                    self._tx_tbl,
                    [
                        tx.tx_hash[:14] + "...",
                        tx.function_name,
                        tx.from_addr[:10] + "...",
                        f"{tx.gas_used:,}",
                    ],
                    [CYAN, GREEN, MUTED, MUTED],
                )

        def _refresh_events(self):
            self._evt_tbl.setRowCount(0)
            for evt in self._testnet.chain.latest_events[:20]:
                color = {
                    "Adjudicated": GREEN,
                    "TokensMinted": AMBER,
                    "ResultSubmitted": CYAN,
                    "CompetitionOpened": MAGENTA,
                    "BotRegistered": MUTED,
                }.get(evt.event_name, MUTED)
                # Compact args display
                args_str = "  ".join(f"{k}={v}" for k, v in list(evt.args.items())[:3])
                _add_row(
                    self._evt_tbl,
                    [str(evt.block_number), evt.event_name, args_str],
                    [MUTED, color, MUTED],
                )

        def _refresh_holders(self):
            self._tok_tbl.setRowCount(0)
            balances = self._testnet.acrv._balances
            sorted_bal = sorted(balances.items(), key=lambda x: x[1], reverse=True)
            # Find tier for each holder from mint log
            holder_tiers: dict = {}
            for m in self._testnet.acrv._mint_log:
                holder_tiers[m["recipient"]] = m["tier"]
            for addr, wei in sorted_bal[:15]:
                tokens = wei / (10**18)
                tier = holder_tiers.get(addr, "—")
                col = TIER_COLORS.get(tier, MUTED)
                _add_row(
                    self._tok_tbl,
                    [addr[:14] + "...", f"{tokens:,.1f}", tier],
                    [MUTED, GREEN, col],
                )

else:

    class TestnetTab:
        def __init__(self, *a, **kw):
            pass
