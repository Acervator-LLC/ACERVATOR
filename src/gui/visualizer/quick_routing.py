"""QuickRoutingMatrix wires checked source bots to checked destination bots."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .privacy import _mask_or

if TYPE_CHECKING:
    from ..bot_visualizer import BotVisualizationTab

logger = logging.getLogger("acervator.gui.bot_visualizer")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QFrame,
        QPushButton,
        QSizePolicy,
        QMessageBox,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
    )
    from PySide6.QtCore import Qt, QTimer

    from .. import design_system as ds

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class QuickRoutingMatrix(QWidget):
        """Three side-by-side zones: _source_list, _rate_input and _dest_list.

        _on_connect_clicked, _on_disconnect_clicked and
        _on_disconnect_all_clicked run from the buttons below them.
        """

        def __init__(self, viz_tab: BotVisualizationTab):
            super().__init__(viz_tab)
            self._viz = viz_tab
            outer = QVBoxLayout(self)
            outer.setContentsMargins(4, 0, 4, 0)
            outer.setSpacing(4)

            col_row = QHBoxLayout()
            col_row.setSpacing(0)
            col_row.setContentsMargins(0, 0, 0, 0)

            _list_style = (
                f"QListWidget{{background:{ds.VIZ_LIST_SURFACE};color:{ds.VIZ_LIST_TEXT};"
                f"border:1px solid {ds.VIZ_LIST_BORDER};font-family:Consolas;"
                "font-size:11px;}"
                "QListWidget::item{padding:3px 4px;}"
                f"QListWidget::item:hover{{background:{ds.VIZ_INPUT_SURFACE};}}"
            )

            self._source_list = QListWidget()
            self._source_list.setSelectionMode(QListWidget.NoSelection)
            self._source_list.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            self._source_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._source_list.setStyleSheet(_list_style)
            self._source_list.setToolTip(
                "Source Bots — check one or more; Connect wires every "
                "checked source → every checked destination at the Rate."
            )
            col_row.addWidget(self._source_list, stretch=1)

            rate_zone = QFrame()
            rate_zone.setFrameShape(QFrame.Box)
            rate_zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            rate_zone.setStyleSheet(
                f"QFrame{{background:{ds.VIZ_LIST_SURFACE};border:1px solid {ds.VIZ_LIST_BORDER};}}"
            )
            rate_lay = QVBoxLayout(rate_zone)
            rate_lay.setContentsMargins(8, 8, 8, 8)
            self._rate_label = QLabel("Rate")
            self._rate_label.setAlignment(Qt.AlignCenter)
            self._rate_label.setStyleSheet(
                f"color:{ds.VIZ_LIST_TEXT};font-family:Consolas;font-size:11px;"
                "font-weight:bold;border:none;"
            )
            rate_lay.addWidget(self._rate_label)
            self._rate_input = QLineEdit("25")
            self._rate_input.setAlignment(Qt.AlignCenter)
            self._rate_input.setStyleSheet(
                f"QLineEdit{{background:{ds.VIZ_INPUT_SURFACE};color:{ds.VIZ_LIST_TEXT};"
                f"border:1px solid {ds.VIZ_INPUT_BORDER};padding:3px 6px;"
                "font-family:Consolas;font-size:11px;}"
            )
            self._rate_input.setToolTip(
                "Percent of each source's profit-per-trade routed to "
                "each destination."
            )
            rate_lay.addWidget(self._rate_input)
            rate_lay.addStretch()
            col_row.addWidget(rate_zone, stretch=1)

            self._dest_list = QListWidget()
            self._dest_list.setSelectionMode(QListWidget.NoSelection)
            self._dest_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._dest_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._dest_list.setStyleSheet(_list_style)
            self._dest_list.setToolTip(
                "Destination Bots — wires terminate at every checked " "destination."
            )
            col_row.addWidget(self._dest_list, stretch=1)

            outer.addLayout(col_row, stretch=1)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            btn_row.setContentsMargins(0, 4, 0, 4)
            btn_row.addStretch()
            self._connect_btn = QPushButton("Connect")
            self._connect_btn.setToolTip(
                "Wire every checked Source → every checked Destination "
                "at the current Rate %."
            )
            self._connect_btn.clicked.connect(self._on_connect_clicked)
            btn_row.addWidget(self._connect_btn)

            self._disconnect_btn = QPushButton("Disconnect")
            self._disconnect_btn.setToolTip(
                "Remove wires for every checked (Source, Destination) "
                "pair in the current selection."
            )
            self._disconnect_btn.clicked.connect(self._on_disconnect_clicked)
            btn_row.addWidget(self._disconnect_btn)

            self._disconnect_all_btn = QPushButton("Disconnect All")
            self._disconnect_all_btn.setToolTip(
                "Clear ALL Smart Wires across the entire swarm "
                "(asks for confirmation)."
            )
            self._disconnect_all_btn.clicked.connect(self._on_disconnect_all_clicked)
            btn_row.addWidget(self._disconnect_all_btn)
            btn_row.addStretch()
            outer.addLayout(btn_row)

        def rebuild_scope(self, bot_ids: list[str]) -> None:
            """Repopulate _source_list and _dest_list from bot_ids.

            Checked bot_ids and both scrollbar offsets carry across the
            rebuild.
            """
            prior_src = self._selected_sources()
            prior_dst = self._selected_destinations()
            # clear() collapses the scrollbar range and clamps its value to 0.
            prior_src_scroll = self._source_list.verticalScrollBar().value()
            prior_dst_scroll = self._dest_list.verticalScrollBar().value()
            self._source_list.clear()
            self._dest_list.clear()
            # _mask_or hides sym and short in label under one field id.
            self._last_scope_ids = list(bot_ids)
            for bid in bot_ids:
                sym = self._symbol_for(bid)
                short = bid[:8] if bid else ""
                label = (
                    f"{_mask_or(sym, 'bot_swarm.identifiers')} "
                    f"[{_mask_or(short, 'bot_swarm.identifiers', mask='********')}]"
                )

                si = QListWidgetItem(label)
                si.setData(Qt.UserRole, bid)
                si.setFlags(si.flags() | Qt.ItemIsUserCheckable)
                si.setCheckState(Qt.Checked if bid in prior_src else Qt.Unchecked)
                self._source_list.addItem(si)

                di = QListWidgetItem(label)
                di.setData(Qt.UserRole, bid)
                di.setFlags(di.flags() | Qt.ItemIsUserCheckable)
                di.setCheckState(Qt.Checked if bid in prior_dst else Qt.Unchecked)
                self._dest_list.addItem(di)

            # The QTimer pass repeats setValue once the relayout fixes the range.
            for lst, val in (
                (self._source_list, prior_src_scroll),
                (self._dest_list, prior_dst_scroll),
            ):
                if not val:
                    continue
                lst.verticalScrollBar().setValue(val)
                QTimer.singleShot(
                    0, lambda b=lst.verticalScrollBar(), v=val: b.setValue(v)
                )

        def _symbol_for(self, bot_id: str) -> str:
            """Return the symbol for bot_id, read from _viz._bot_widgets.

            Falls back to StateManager, then to a single question mark.
            """
            try:
                w = self._viz._bot_widgets.get(bot_id)
                if w is not None:
                    sym = (
                        w._bot_data.get("symbol", "") if hasattr(w, "_bot_data") else ""
                    )
                    if sym:
                        return str(sym)
            except Exception:  # noqa: S110
                pass
            try:
                from ...core.state_manager import StateManager

                st = StateManager().load_state()
                cfg = (st.get("bots", {}) or {}).get(bot_id, {}).get("config", {}) or {}
                return str(cfg.get("symbol", "") or "?")
            except Exception:
                return "?"

        def _selected_sources(self) -> list[str]:
            """Return every checked bot_id in _source_list."""
            out: list[str] = []
            for i in range(self._source_list.count()):
                it = self._source_list.item(i)
                if it.checkState() == Qt.Checked:
                    bid = it.data(Qt.UserRole) or ""
                    if bid:
                        out.append(str(bid))
            return out

        def _selected_destinations(self) -> list[str]:
            """Return every checked bot_id in _dest_list."""
            out: list[str] = []
            for i in range(self._dest_list.count()):
                it = self._dest_list.item(i)
                if it.checkState() == Qt.Checked:
                    bid = it.data(Qt.UserRole) or ""
                    if bid:
                        out.append(str(bid))
            return out

        def _reject(self, why: str) -> None:
            """Show why in a QMessageBox, and log it when the box cannot open."""
            try:
                QMessageBox.warning(self, "Quick Routing", why)
            except Exception as exc:  # noqa: BLE001
                logger.warning("quick-routing rejection unshowable: %s", exc)

        def _confirm_mass(self, verb: str, n: int, detail: str) -> bool:
            """Ask before verb on n wires, and return True to proceed.

            QMessageBox defaults to No; a box that cannot open returns
            False.
            """
            try:
                reply = QMessageBox.question(
                    self,
                    f"{verb} {n} Smart Wire" + ("s" if n != 1 else "") + "?",
                    f"{verb} {n} wire"
                    + ("s" if n != 1 else "")
                    + f" across the selected bots?\n\n{detail}\n\n"
                    + (
                        "Existing rates on these pairs will be OVERWRITTEN."
                        if verb == "Create"
                        else "This stops profit routing on every pair listed."
                    )
                    + "\n\nThis cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                return reply == QMessageBox.Yes
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "quick-routing confirmation unshowable (%s); refusing", exc
                )
                return False

        def _on_connect_clicked(self) -> None:
            sources = self._selected_sources()
            dests = self._selected_destinations()
            # rstrip("%") lets "25%" parse the same as "25".
            raw = ""
            try:
                raw = self._rate_input.text().strip().rstrip("%").strip()
                pct = float(raw)
            except (ValueError, AttributeError):
                self._reject(
                    f"Rate {raw!r} is not a number. Enter a percentage "
                    f"between 0 and 100."
                )
                return
            if not (0.0 <= pct <= 100.0):
                self._reject(f"Rate {pct} is outside 0–100%.")
                return
            if not sources:
                self._reject("No SOURCE bots are checked.")
                return
            if not dests:
                self._reject("No DESTINATION bots are checked.")
                return
            if pct <= 0:
                self._reject(
                    "Rate is 0% — that would create wires that route " "nothing."
                )
                return
            wires_created: list[tuple[str, str, float]] = []
            for src in sources:
                for dst in dests:
                    if src == dst:
                        continue
                    wires_created.append((src, dst, pct))
            if not wires_created:
                self._reject(
                    "Every selected pair is the same bot — a bot cannot "
                    "wire to itself."
                )
                return
            if not self._confirm_mass(
                "Create",
                len(wires_created),
                f"{len(sources)} source(s) x {len(dests)} destination(s) "
                f"at {pct}% each.",
            ):
                return
            try:
                self._viz._apply_routes_to_state(add=wires_created, remove=[])
            except Exception as exc:  # noqa: BLE001
                # A raise here means _apply_routes_to_state saved nothing.
                logger.error(
                    "quick-routing connect: persisting %d wire(s) FAILED "
                    "(%s); no wire was created",
                    len(wires_created),
                    exc,
                )
                self._reject(
                    f"Nothing was changed — saving the routing table "
                    f"failed:\n\n{exc}"
                )
                return
            # wire.created reaches the canvas and SmartWireManager.
            try:
                from ...core.event_bus import get_event_bus

                bus = get_event_bus()
                for src, dst, p in wires_created:
                    bus.emit("wire.created", source_id=src, target_id=dst, pct=p)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "quick-routing connect: %d wire(s) were saved but "
                    "the redraw events FAILED (%s) — the canvas is stale, "
                    "not empty",
                    len(wires_created),
                    exc,
                )

        def _on_disconnect_clicked(self) -> None:
            sources = self._selected_sources()
            dests = self._selected_destinations()
            if not sources:
                self._reject("No SOURCE bots are checked.")
                return
            if not dests:
                self._reject("No DESTINATION bots are checked.")
                return
            pairs: list[tuple[str, str]] = []
            for src in sources:
                for dst in dests:
                    if src == dst:
                        continue
                    pairs.append((src, dst))
            if not pairs:
                self._reject(
                    "Every selected pair is the same bot — nothing to " "disconnect."
                )
                return
            if not self._confirm_mass(
                "Disconnect",
                len(pairs),
                f"{len(sources)} source(s) x {len(dests)} " f"destination(s).",
            ):
                return
            try:
                self._viz._apply_routes_to_state(add=[], remove=pairs)
            except Exception as exc:  # noqa: BLE001
                # A raise here means _apply_routes_to_state removed nothing.
                logger.error(
                    "quick-routing disconnect: persisting %d removal(s) "
                    "FAILED (%s); no wire was removed",
                    len(pairs),
                    exc,
                )
                self._reject(
                    f"Nothing was changed — saving the routing table "
                    f"failed:\n\n{exc}"
                )
                return
            try:
                from ...core.event_bus import get_event_bus

                bus = get_event_bus()
                for src, dst in pairs:
                    bus.emit("wire.removed", source_id=src, target_id=dst)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "quick-routing disconnect: %d removal(s) were saved "
                    "but the redraw events FAILED (%s) — the canvas is "
                    "stale, not wrong",
                    len(pairs),
                    exc,
                )

        def _on_disconnect_all_clicked(self) -> None:
            reply = QMessageBox.question(
                self,
                "Disconnect All Wires?",
                "Disconnect ALL Smart Wires across the entire swarm? "
                "This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                removed = self._viz._clear_all_routes_in_state()
            except Exception as exc:
                logger.error(
                    "quick-routing disconnect-all: clearing every wire "
                    "FAILED (%s); no wire was removed",
                    exc,
                )
                self._reject(
                    f"Nothing was changed — clearing the routing table "
                    f"failed:\n\n{exc}"
                )
                return
            try:
                from ...core.event_bus import get_event_bus

                bus = get_event_bus()
                for src, dst in removed:
                    bus.emit("wire.removed", source_id=src, target_id=dst)
            except Exception as exc:
                logger.error(
                    "quick-routing disconnect-all: %d removal(s) were "
                    "saved but the redraw events FAILED (%s) — the "
                    "canvas is stale, not wrong",
                    len(removed),
                    exc,
                )
