"""market_inspector_topologies.py — right-pane widget for cross-market
topology proposals + the preview modal.

Reference specification (Diataxis: reference). Consumes proposals from
`src/trading/topology_proposals.py`. Design doc:
`docs/engineering-notes/2026-07-31_market_inspector_topology_proposals_design.md`.

v3.23.68 — GUI cascade 2 of 3 for Market Inspector Piece 3.
The Adopt button in the preview modal is **disabled** in this cascade
(safe eyeballing only). v3.23.69 enables Adopt via the Bot Wizard
handoff to `SmartWireManager.set_wire`.

Two public classes:
    * ``MarketInspectorTopologies`` — the right-pane widget with the
      proposals card list, refresh button, and 24 h dismiss cache.
    * ``TopologyPreviewDialog`` — the modal opened by [Preview] on
      each card. Also opened by the future [Adopt] flow.

Both classes are Qt widgets, so this module is import-guarded on
``PySide6`` availability (matching `market_inspector.py`).

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from .main_tabs.market_inspector_surface import step_to
from .main_tabs.market_inspector_topologies_surface import (
    DISMISS_PART,
    FOOTER_STYLE,
    FOOTER_TEXT,
    HEADER_WORD_WRAP,
    PANE_MARGINS,
    PANE_SPACING,
    PREVIEW_PART,
    REFRESH_TEXT,
    REFRESH_TOOLTIP,
    REFRESH_WIDTH_PX,
    STATUS_STYLE,
    STATUS_UNWIRED,
    pane_view,
)

logger = logging.getLogger("acervator.topology_proposals_gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QGroupBox,
        QDialog,
        QTreeWidget,
        QTreeWidgetItem,
        QHeaderView,
        QMessageBox,
        QSizePolicy,
    )
    from PySide6.QtCore import Qt, QTimer, Signal

    _HAS_QT = True
except ImportError:  # pragma: no cover - GUI-only guard
    _HAS_QT = False


DISMISS_TTL_SECONDS: int = 24 * 60 * 60
# Settings key whose value is {proposal_id: expiry_epoch_seconds}.
DISMISS_SETTINGS_KEY: str = "topology_dismissed_proposals"
AUTO_REFRESH_MS: int = 10 * 60 * 1000
SCORE_HIGH: float = 80.0
SCORE_MID: float = 50.0


def _score_color(score: float) -> str:
    """Return the hex colour a proposal card is drawn in for ``score``."""
    if score >= SCORE_HIGH:
        return "#00cccc"
    if score >= SCORE_MID:
        return "#ffb84d"
    return "#888888"


def _archetype_label(archetype: str) -> str:
    return {
        "momentum_funnel": "Momentum funnel",
        "mean_reversion_pair": "Mean-reversion pair",
        "sector_cluster": "Sector cluster",
        "distance_to_band": "Distance handoff",
    }.get(archetype, archetype)


if _HAS_QT:

    class TopologyPreviewDialog(QDialog):
        """Modal preview for a single proposal.

        Layout:
            * Title + archetype badge (top)
            * Two side-by-side lists: Bots / Wires
            * Adopt-summary line at the bottom
            * [Cancel] (default) and [Adopt] buttons

        The Adopt button is force-disabled in v3.23.68; v3.23.69
        removes ``force_adopt_disabled`` and wires the click.
        """

        adoptClicked = Signal(dict)  # emits the proposal on Adopt

        def __init__(
            self,
            proposal: dict[str, Any],
            parent: Optional[QWidget] = None,
            force_adopt_disabled: bool = False,
        ) -> None:
            super().__init__(parent)
            self._proposal = dict(proposal or {})
            self.setWindowTitle(f"Preview: {self._proposal.get('title', 'topology')}")
            self.setMinimumSize(720, 460)

            root = QVBoxLayout(self)
            root.setContentsMargins(12, 12, 12, 12)
            root.setSpacing(10)

            # --- Header ----------------------------------------------
            header = QHBoxLayout()
            title_lbl = QLabel(f"<b>{self._proposal.get('title', '')}</b>")
            title_lbl.setStyleSheet("font-size: 14px;")
            header.addWidget(title_lbl)
            header.addStretch()
            archetype = self._proposal.get("archetype", "")
            score = float(self._proposal.get("score", 0.0))
            badge = QLabel(f" {_archetype_label(archetype)}  ·  score {score:.0f} ")
            badge.setStyleSheet(
                f"background-color: {_score_color(score)}; color: black; "
                "padding: 2px 8px; border-radius: 8px; font-weight: bold;"
            )
            header.addWidget(badge)
            root.addLayout(header)

            # --- Body: two columns -----------------------------------
            body = QHBoxLayout()
            body.setSpacing(12)

            bots_box = QGroupBox("Bots")
            bots_v = QVBoxLayout(bots_box)
            bots_tree = QTreeWidget(bots_box)
            bots_tree.setColumnCount(4)
            bots_tree.setHeaderLabels(["Asset", "Role", "Symbol", "Status"])
            bots_tree.setToolTip(
                "Bots involved in this topology proposal — EXISTING "
                "means the bot is already live; WILL CREATE means "
                "adopting will open the Bot Wizard for a new bot at "
                "the shown target USD."
            )
            bots_tree.setRootIsDecorated(False)
            bots_tree.setAlternatingRowColors(True)
            for b in self._proposal.get("bots", []):
                existing_id = str(b.get("existing_bot_id", "") or "")
                status = (
                    "EXISTING"
                    if existing_id
                    else f"WILL CREATE (${b.get('suggested_target_usd', 0):.0f})"
                )
                item = QTreeWidgetItem(
                    [
                        str(b.get("asset", "")),
                        str(b.get("role", "")),
                        str(b.get("symbol", "")),
                        status,
                    ]
                )
                if not existing_id:
                    for col in range(4):
                        item.setForeground(col, Qt.yellow)
                bots_tree.addTopLevelItem(item)
            bots_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            bots_v.addWidget(bots_tree)
            body.addWidget(bots_box, 1)

            wires_box = QGroupBox("Wires")
            wires_v = QVBoxLayout(wires_box)
            wires_tree = QTreeWidget(wires_box)
            wires_tree.setColumnCount(4)
            wires_tree.setHeaderLabels(["Source", "Target", "Pct", "Rationale"])
            wires_tree.setToolTip(
                "Wires the Adopt handoff will create between the bots "
                "above. Percentages are the operator's Rate spinbox "
                "equivalent (0-100)."
            )
            wires_tree.setRootIsDecorated(False)
            wires_tree.setAlternatingRowColors(True)
            for w in self._proposal.get("wires", []):
                item = QTreeWidgetItem(
                    [
                        str(w.get("source_asset", "")),
                        str(w.get("target_asset", "")),
                        f"{float(w.get('pct', 0.0)):.1f}%",
                        str(w.get("rationale", "")),
                    ]
                )
                wires_tree.addTopLevelItem(item)
            wires_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            wires_v.addWidget(wires_tree)
            body.addWidget(wires_box, 1)
            root.addLayout(body, 1)

            # --- Adopt summary + notes -------------------------------
            new_bots = sum(
                1
                for b in self._proposal.get("bots", [])
                if not b.get("existing_bot_id")
            )
            new_budget = sum(
                float(b.get("suggested_target_usd", 0.0))
                for b in self._proposal.get("bots", [])
                if not b.get("existing_bot_id")
            )
            summary = QLabel(
                f"<i>New bots to create: {new_bots}  ·  "
                f"target capital: ${new_budget:,.0f}</i>"
            )
            summary.setStyleSheet("color: #ccc;")
            root.addWidget(summary)
            for note in self._proposal.get("adopt_notes", []):
                nl = QLabel(f"  • {note}")
                nl.setWordWrap(True)
                nl.setStyleSheet("color: #aaa; font-size: 11px;")
                root.addWidget(nl)

            # --- Buttons ---------------------------------------------
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self._cancel_btn = QPushButton("Cancel")
            self._cancel_btn.setDefault(True)
            self._cancel_btn.clicked.connect(self.reject)
            btn_row.addWidget(self._cancel_btn)
            self._adopt_btn = QPushButton("Adopt")
            self._adopt_btn.setEnabled(not force_adopt_disabled)
            if force_adopt_disabled:
                self._adopt_btn.setToolTip("Adopt is disabled (test override).")
            else:
                self._adopt_btn.setToolTip(
                    "Walk the Bot Wizard for each new bot, then draw "
                    "the wires listed above. Cancelling any wizard "
                    "aborts the entire adoption."
                )
            self._adopt_btn.clicked.connect(self._on_adopt)
            btn_row.addWidget(self._adopt_btn)
            root.addLayout(btn_row)

        def _on_adopt(self) -> None:
            self.adoptClicked.emit(self._proposal)
            self.accept()

    class MarketInspectorTopologies(QWidget):
        """Right-pane widget: proposal list + refresh + dismiss cache.

        Callers wire the proposal source via
        ``set_proposal_source(getter)`` where ``getter()`` returns
        ``list[dict]``. If unwired the pane shows a placeholder.
        """

        adoptRequested = Signal(dict)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._proposal_source: Optional[Callable[[], list[dict]]] = None
            # dismissed_id -> expiry_epoch_seconds
            self._dismissed: dict[str, float] = {}
            # Injected by ``set_dismiss_store``; unset keeps dismissals in memory.
            self._dismiss_store: Optional[Any] = None
            self._proposals: list[dict[str, Any]] = []
            self._at = 0
            self._expanded = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(*PANE_MARGINS)
            layout.setSpacing(PANE_SPACING)

            # The button keeps its published width and the two lines share
            # what is left, so neither is sized by its own text and neither
            # can reach past the zone's edge.
            top_row = QHBoxLayout()
            top_row.setSpacing(PANE_SPACING)
            self._refresh_btn = QPushButton(REFRESH_TEXT)
            self._refresh_btn.setToolTip(REFRESH_TOOLTIP)
            self._refresh_btn.setFixedWidth(REFRESH_WIDTH_PX)
            self._refresh_btn.clicked.connect(self.refresh)
            top_row.addWidget(self._refresh_btn)
            self._footer_lbl = QLabel(FOOTER_TEXT)
            self._footer_lbl.setStyleSheet(FOOTER_STYLE)
            self._status_lbl = QLabel(STATUS_UNWIRED)
            self._status_lbl.setStyleSheet(STATUS_STYLE)
            for one in (self._footer_lbl, self._status_lbl):
                one.setWordWrap(HEADER_WORD_WRAP)
                one.setMinimumWidth(0)
                one.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                one.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
                top_row.addWidget(one, 1)
            layout.addLayout(top_row)

            from .market_inspector import ProposalStepper

            # The zone the pane sits in already carries the title, so the pane
            # holds the stepper directly rather than inside a second group box.
            self._stepper = ProposalStepper()
            self._stepper.stepped.connect(self._on_step)
            self._stepper.entryClicked.connect(self._on_entry_clicked)
            self._stepper.actionPressed.connect(self._on_action)
            layout.addWidget(self._stepper, 1)

            self._timer = QTimer(self)
            self._timer.setInterval(AUTO_REFRESH_MS)
            self._timer.timeout.connect(self.refresh)
            self._timer.start()

            # The first refresh is one interval away. Without this the zone's
            # first paint carries the stepper's own blank headline and its
            # entry hint instead of the empty sentence the page draws.
            self._render()

        # ── external API ─────────────────────────────────────────────
        def set_proposal_source(
            self,
            getter: Callable[[], list[dict]],
        ) -> None:
            self._proposal_source = getter
            self._status_lbl.setText("Ready — press Refresh.")

        def refresh(self) -> None:
            if self._proposal_source is None:
                return
            try:
                raw = self._proposal_source() or []
            except Exception as exc:  # noqa: BLE001 - detector surface
                logger.exception("topology proposals refresh failed: %s", exc)
                self._status_lbl.setText(f"Detector error: {exc}")
                return
            now = time.time()
            self._sweep_dismissed(now)
            self._proposals = [p for p in raw if p.get("id") not in self._dismissed]
            self._render()
            self._status_lbl.setText(
                f"{len(self._proposals)} proposal(s); "
                f"{len(self._dismissed)} dismissed"
            )

        def current_proposals(self) -> list:
            """The non-dismissed proposals currently on display.

            v3.24.79 — read access for Nuclear Mode, which stresses a
            proposal's topology across SIM bots under cycling load.
            Operator directive 2026-08-07: Nuclear "is supposed to be
            able to receive strategy injections from the Market
            Inspector to test the strategy propagation function and
            swarm topologies under cycling load."

            READ ONLY, and deliberately NOT the adopt path. Adopting
            (`adoptRequested` → `MainWindow._adopt_topology_proposal`)
            creates real bots and real wires on the live fleet. This
            hands over the same dicts for a simulator to replay, and
            reaches none of that.

            Returns a shallow copy of the list so a consumer cannot
            mutate what the pane is rendering. The proposal dicts
            themselves are shared — callers must treat them as
            read-only, which the sim path does.
            """
            return list(self._proposals)

        def dismiss(self, proposal_id: str, now: Optional[float] = None) -> None:
            """Suppress a proposal id for DISMISS_TTL_SECONDS."""
            _now = time.time() if now is None else now
            if not proposal_id:
                return
            self._dismissed[proposal_id] = _now + DISMISS_TTL_SECONDS
            self._persist_dismissed()
            self._proposals = [p for p in self._proposals if p.get("id") != proposal_id]
            self._render()

        def is_dismissed(
            self,
            proposal_id: str,
            now: Optional[float] = None,
        ) -> bool:
            _now = time.time() if now is None else now
            expiry = self._dismissed.get(proposal_id)
            if expiry is None:
                return False
            if expiry <= _now:
                del self._dismissed[proposal_id]
                return False
            return True

        def _sweep_dismissed(self, now: float) -> None:
            expired = [k for k, v in self._dismissed.items() if v <= now]
            for k in expired:
                del self._dismissed[k]
            if expired:
                self._persist_dismissed()

        def set_dismiss_store(self, store: Optional[Any]) -> None:
            """Attach ``store`` and load ``DISMISS_SETTINGS_KEY`` from it.

            ``store`` needs only ``get(key, default)`` and
            ``set(key, value)``. Entries whose expiry has passed are
            dropped at load and never enter ``_dismissed``.
            """
            self._dismiss_store = store
            if store is None:
                return
            try:
                raw = store.get(DISMISS_SETTINGS_KEY, {}) or {}
            except Exception as exc:  # a bad store must not break the pane
                logger.warning(
                    "topology dismissals could not be loaded (%s); "
                    "continuing with an empty cache",
                    exc,
                )
                return
            if not isinstance(raw, dict):
                logger.warning(
                    "topology dismissals were %s, not a dict; ignoring",
                    type(raw).__name__,
                )
                return
            now = time.time()
            loaded = 0
            for pid, expiry in raw.items():
                try:
                    exp = float(expiry)
                except (TypeError, ValueError):
                    continue
                if exp > now:
                    self._dismissed[str(pid)] = exp
                    loaded += 1
            logger.info(
                "topology dismissals restored: %d still active of %d " "persisted",
                loaded,
                len(raw),
            )

        def _persist_dismissed(self) -> None:
            """Write ``_dismissed`` to the store. Logs and returns on failure."""
            if self._dismiss_store is None:
                return
            try:
                self._dismiss_store.set(DISMISS_SETTINGS_KEY, dict(self._dismissed))
            except Exception as exc:  # persistence is best-effort
                logger.warning(
                    "topology dismissal could not be persisted (%s); it "
                    "will not survive restart",
                    exc,
                )

        # ── rendering ────────────────────────────────────────────────
        def _shown(self) -> int:
            """Which proposal is on screen, held inside the list the pane holds."""
            if not self._proposals:
                return 0
            return max(0, min(self._at, len(self._proposals) - 1))

        def _shown_id(self) -> str:
            """The id of the proposal on screen, or an empty string."""
            if not self._proposals:
                return ""
            return str(self._proposals[self._shown()].get("id", ""))

        def _on_step(self, by: int) -> None:
            """Move to the previous or next proposal and redraw."""
            self._at = step_to(self._shown(), len(self._proposals), by)
            self._render()

        def _on_entry_clicked(self) -> None:
            """Open or close the expansion and redraw."""
            self._expanded = not self._expanded
            self._render()

        def _on_action(self, part: str) -> None:
            """Run the button the expansion carries: Preview or Dismiss."""
            if part == PREVIEW_PART:
                self._on_preview(self._shown_id())
            elif part == DISMISS_PART:
                self._on_dismiss(self._shown_id())

        def _render(self) -> None:
            self._stepper.show_view(
                pane_view(self._proposals, self._shown(), self._expanded)
            )

        def _find_proposal(self, proposal_id: str) -> Optional[dict[str, Any]]:
            for p in self._proposals:
                if p.get("id") == proposal_id:
                    return p
            return None

        def _on_preview(self, proposal_id: str) -> None:
            p = self._find_proposal(proposal_id)
            if p is None:
                return
            dlg = TopologyPreviewDialog(p, parent=self)
            dlg.adoptClicked.connect(self.adoptRequested.emit)
            dlg.exec()

        def _on_dismiss(self, proposal_id: str) -> None:
            if not proposal_id:
                return
            reply = QMessageBox.question(
                self,
                "Dismiss proposal",
                f"Suppress this proposal for 24 h?\n\nId: {proposal_id}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.dismiss(proposal_id)


__all__ = [
    "DISMISS_TTL_SECONDS",
    "AUTO_REFRESH_MS",
    "SCORE_HIGH",
    "SCORE_MID",
]
if _HAS_QT:
    __all__.extend(["TopologyPreviewDialog", "MarketInspectorTopologies"])
