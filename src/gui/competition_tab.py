"""
competition_tab.py — Proof of Accumulation GUI Tab
===================================================
Displays:
  - Bot identity panel (bot ID, public key, status)
  - Token wallet (ACRV balance, tier badges, award history)
  - Active/recent competitions (status, participants, results)
  - Leaderboard (Elo ratings, win/loss)
  - Challenge panel (issue and respond to challenges)
  - Supply dashboard (global ACRV stats)
"""

from __future__ import annotations

import time
from pathlib import Path
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
        QFrame,
        QScrollArea,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QBrush

    _QT = True
except ImportError:
    _QT = False

if _QT:
    from ..competition import (
        BotIdentity,
        TokenLedger,
        RatingRegistry,
        season_reward,
        TOTAL_SUPPLY_CAP,
    )

# ── Style constants ──────────────────────────────────────────────────────────
CYAN = "#00FFEE"
GREEN = "#00FF88"
AMBER = "#FFAA00"
RED = "#FF3355"
MAGENTA = "#FF00AA"
MUTED = "#8899BB"
PANEL = "#0A0A1C"

TIER_COLORS = {
    "Harvest": "#00FF88",
    "Gold Fold": "#FFAA00",
    "Bear Slayer": "#FF3355",
    "Grand Accumulator": "#00FFEE",
    "Ekthelius": "#FF00AA",
}

_LABEL_STYLE = f"color:{CYAN}; font-family:Orbitron; font-size:9px; letter-spacing:3px;"
_VAL_STYLE = "color:#D8E8FF; font-family:Consolas; font-size:12px;"
_MONO_STYLE = "color:#8899BB; font-family:Consolas; font-size:10px;"


if _QT:

    class _Section(QGroupBox):
        def __init__(self, title: str, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Section")
            self.setStyleSheet(f"""
                QGroupBox {{
                    border: 1px solid rgba(0,255,238,0.15);
                    border-radius: 6px;
                    margin-top: 14px;
                    background: {PANEL};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 10px;
                    color: {CYAN};
                    font-family: Orbitron;
                    font-size: 9px;
                    letter-spacing: 3px;
                }}
            """)
            self.setTitle(title.upper())
            self._inner = QVBoxLayout(self)
            self._inner.setContentsMargins(8, 16, 8, 8)
            self._inner.setSpacing(6)

        def inner(self) -> QVBoxLayout:
            return self._inner

    # ── Bot identity panel ────────────────────────────────────────────────────
    class _IdentityPanel(_Section):
        def __init__(self, identity: Optional[BotIdentity], parent=None):
            super().__init__("Bot Identity", parent)
            row = QHBoxLayout()
            if identity:
                id_lbl = QLabel(f"ID: {identity.short_id}...")
                id_lbl.setStyleSheet(_VAL_STYLE)
                full = QLabel(identity.bot_id[:24] + "...")
                full.setStyleSheet(_MONO_STYLE)
                row.addWidget(id_lbl)
                row.addWidget(full)
            else:
                row.addWidget(QLabel("No identity — generate keypair to compete"))
            self.inner().addLayout(row)

    # ── Wallet panel ──────────────────────────────────────────────────────────
    class _WalletPanel(_Section):
        def __init__(self, ledger: TokenLedger, bot_id: str, parent=None):
            super().__init__("ACRV Wallet", parent)
            bal = ledger.balance(bot_id) if bot_id else 0
            awards = ledger.awards(bot_id) if bot_id else []

            bal_lbl = QLabel(f"{bal:,} ACRV")
            bal_lbl.setStyleSheet(
                f"color:{GREEN}; font-family:Orbitron; font-size:18px; font-weight:900;"
            )
            self.inner().addWidget(bal_lbl)

            if awards:
                tbl = QTableWidget(len(awards), 4)
                tbl.setHorizontalHeaderLabels(["Tier", "Amount", "Competition", "Date"])
                tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                tbl.verticalHeader().setVisible(False)
                tbl.setMaximumHeight(min(120, len(awards) * 26 + 28))
                tbl.setEditTriggers(QTableWidget.NoEditTriggers)
                for r, award in enumerate(awards):
                    col = TIER_COLORS.get(award.tier_name, MUTED)
                    items = [
                        f"{award.tier_emoji} {award.tier_name}",
                        f"{award.amount:,}",
                        award.competition_id,
                        time.strftime("%Y-%m-%d", time.localtime(award.timestamp)),
                    ]
                    for c, txt in enumerate(items):
                        item = QTableWidgetItem(txt)
                        item.setTextAlignment(Qt.AlignCenter)
                        if c == 0:
                            item.setForeground(QBrush(QColor(col)))
                        tbl.setItem(r, c, item)
                self.inner().addWidget(tbl)
            else:
                self.inner().addWidget(
                    QLabel("No awards yet — enter a competition to earn ACRV")
                )

    # ── Supply dashboard ──────────────────────────────────────────────────────
    class _SupplyPanel(_Section):
        def __init__(self, ledger: TokenLedger, season: int = 1, parent=None):
            super().__init__("Global Supply", parent)
            s = ledger.supply_summary()
            row = QHBoxLayout()
            for label, val in [
                ("Total Cap", f"{TOTAL_SUPPLY_CAP:,}"),
                ("Minted", f"{s['total_minted']:,}"),
                ("Remaining", f"{s['remaining']:,}"),
                ("Season Budget", f"{season_reward(season):,}"),
                ("Holders", str(s["total_holders"])),
            ]:
                col = QVBoxLayout()
                lbl = QLabel(label.upper())
                lbl.setStyleSheet(_LABEL_STYLE)
                v = QLabel(val)
                v.setStyleSheet(
                    f"color:{CYAN}; font-family:Orbitron; font-size:13px; font-weight:700;"
                )
                v.setAlignment(Qt.AlignCenter)
                lbl.setAlignment(Qt.AlignCenter)
                col.addWidget(lbl)
                col.addWidget(v)
                row.addLayout(col)
            self.inner().addLayout(row)

    # ── Leaderboard ───────────────────────────────────────────────────────────
    class _LeaderboardPanel(_Section):
        def __init__(self, registry: RatingRegistry, parent=None):
            super().__init__("Elo Leaderboard", parent)
            rows = registry.leaderboard(10)
            if not rows:
                self.inner().addWidget(QLabel("No matches played yet"))
                return
            tbl = QTableWidget(len(rows), 5)
            tbl.setHorizontalHeaderLabels(["#", "Bot", "Rating", "W/L", "Win%"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            for r, row in enumerate(rows):
                for c, txt in enumerate(
                    [
                        str(row["rank"]),
                        row["bot_id"],
                        str(row["rating"]),
                        f"{row['w']}/{row['l']}",
                        row["win_rate"],
                    ]
                ):
                    item = QTableWidgetItem(txt)
                    item.setTextAlignment(Qt.AlignCenter)
                    if c == 0 and r == 0:
                        item.setForeground(QBrush(QColor(AMBER)))
                    tbl.setItem(r, c, item)
            self.inner().addWidget(tbl)

    # ── Main competition tab ──────────────────────────────────────────────────
    class CompetitionTab(QWidget):
        """
        PoA Network tab — read-only identity and wallet panel.
        Competition execution removed. Real P2P relay required (ADR-009, v3.9.0).
        Local simulation belongs in the Testnet tab only.
        """

        def __init__(self, parent=None, data_dir: str = "competition_data"):
            super().__init__(parent)
            self.setAccessibleName("Competition Tab")
            self._data_dir = Path(data_dir)
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._identity = self._load_identity()
            self._ledger = TokenLedger(str(self._data_dir / "acrv_ledger.json"))
            self._ledger.load()
            self._registry = RatingRegistry(str(self._data_dir / "elo_registry.json"))
            self._registry.load()
            self._season = 1
            self._setup_ui()

        def _load_identity(self):
            try:
                return BotIdentity(str(self._data_dir / "bot_identity.json")).generate()
            except Exception:
                return None

        def _setup_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(10, 8, 10, 8)
            root.setSpacing(8)

            hdr = QHBoxLayout()
            ttl = QLabel("Proof of Accumulation")
            ttl.setStyleSheet(
                f"color:{CYAN}; font-family:Orbitron; font-size:14px; font-weight:900;"
            )
            hdr.addWidget(ttl)
            hdr.addStretch()
            sub = QLabel("PoA Network  \u00b7  ACRV Token  \u00b7  Season 1")
            sub.setStyleSheet(f"color:{MUTED}; font-family:Consolas; font-size:10px;")
            hdr.addWidget(sub)
            root.addLayout(hdr)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("color:rgba(0,255,238,0.15);")
            root.addWidget(sep)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            container = QWidget()
            inner = QVBoxLayout(container)
            inner.setSpacing(8)

            # Identity, wallet, supply, leaderboard — all read-only, genuinely useful
            inner.addWidget(_IdentityPanel(self._identity))
            row = QHBoxLayout()
            bot_id = self._identity.bot_id if self._identity else ""
            row.addWidget(_WalletPanel(self._ledger, bot_id))
            row.addWidget(_SupplyPanel(self._ledger, self._season))
            inner.addLayout(row)
            inner.addWidget(_LeaderboardPanel(self._registry))

            # Network connection panel
            net_box = _Section("PoA Network Connection")
            net_lay = net_box.inner()

            status_row = QHBoxLayout()
            dot = QLabel("\u25cf")
            dot.setStyleSheet(f"color:{RED}; font-size:14px;")
            slbl = QLabel("NOT CONNECTED  \u2014  Relay server required")
            slbl.setStyleSheet(
                f"color:{RED}; font-family:Orbitron; font-size:10px; letter-spacing:2px;"
            )
            status_row.addWidget(dot)
            status_row.addWidget(slbl)
            status_row.addStretch()
            net_lay.addLayout(status_row)

            lines = [
                "A real PoA competition requires connection and mutual authentication",
                "with a second Acervator instance on a separate machine.",
                "",
                "This tab will be rebuilt in v3.9.0 (ADR-009):",
                "  1.  Connect to relay  (wss://relay.acervator.io)",
                "  2.  Authenticate via Ed25519 keypair",
                "  3.  Discover bots, issue or receive a signed challenge",
                "  4.  Both bots register on-chain  (Base CompetitionRegistry)",
                "  5.  Competition runs  \u2014  Merkle heartbeats prove liveness",
                "  6.  Both bots submit on-chain  \u2014  winner adjudicated",
                "",
                "To run a local simulation now, use the  \u26d3 Testnet  tab.",
            ]
            info = QLabel("\n".join(lines))
            info.setWordWrap(True)
            info.setStyleSheet(f"color:{MUTED}; font-family:Consolas; font-size:10px;")
            net_lay.addWidget(info)

            url_row = QHBoxLayout()
            url_lbl = QLabel("Relay:")
            url_lbl.setStyleSheet(
                f"color:{MUTED}; font-family:Consolas; font-size:10px;"
            )
            url_row.addWidget(url_lbl)
            from PySide6.QtWidgets import QLineEdit

            self._relay_url = QLineEdit("wss://relay.acervator.io")
            self._relay_url.setEnabled(False)
            self._relay_url.setStyleSheet(
                f"background:#0A0A18; color:#445566;"
                f" border:1px solid rgba(0,255,238,0.1);"
                f" font-family:Consolas; font-size:10px; padding:4px 8px;"
            )
            url_row.addWidget(self._relay_url)
            connect_btn = QPushButton("Connect  (v3.9.0)")
            connect_btn.setEnabled(False)
            connect_btn.setStyleSheet(
                f"background:rgba(0,255,238,0.04); color:#334455;"
                f" border:1px solid rgba(0,255,238,0.1);"
                f" font-family:Orbitron; font-size:9px;"
                f" padding:6px 14px; border-radius:4px;"
            )
            url_row.addWidget(connect_btn)
            net_lay.addLayout(url_row)

            inner.addWidget(net_box)
            inner.addStretch()
            scroll.setWidget(container)
            root.addWidget(scroll)

        def get_wallet_balance(self) -> int:
            if not self._identity:
                return 0
            return self._ledger.balance(self._identity.bot_id)

else:
    # Headless stub
    class CompetitionTab:
        def __init__(self, *args, **kwargs):
            pass
