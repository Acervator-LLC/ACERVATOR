"""Bot Swarm tab of the Live Bot Settings dialog."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from .. import design_system as ds
from ..main_tabs.bot_swarm_tab_surface import PROVENANCE_GROUP_TITLE_QT

logger = logging.getLogger("acervator.gui")


class BotSwarmTabMixin:
    """Smart Wire topology, per-bot ledgers and the event feed."""

    # Supplied by BotLiveSettingsDialog at runtime. Annotations only:
    # no attribute is created and the runtime base stays `object`.
    _bot: Any
    _configure_form: Callable[..., Any]
    _format_age: Callable[..., Any]

    def _create_bot_swarm_tab(self) -> QWidget:
        import time as _time

        # Imported inside the call, so building a tab drags no trading
        # code in at module import time.
        from ...trading.bot_container import (
            as_finite_float as _as_finite_float,
        )

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        # Set on the bot by set_smart_wire; None until it is attached.
        mgr = getattr(self._bot, "_smart_wire_mgr", None)
        bot_id = getattr(self._bot, "bot_id", "")
        now_ts = _time.time()

        if mgr is None:
            msg = QLabel(
                "<b>Bot Swarm not active for this bot.</b><br><br>"
                "Smart Wire manager has not been attached. The "
                "bot is operating standalone — no wire connections "
                "can fire to/from it. To enable Bot Swarm "
                "integration, ensure the bot is registered with "
                "the platform's Smart Wire manager (typically "
                "automatic for scrumming bots created via the "
                "Bot Wizard with Smart Wire enabled)."
            )
            msg.setStyleSheet(f"color: {ds.TEXT_INACTIVE}; padding: 12px;")
            msg.setWordWrap(True)
            layout.addWidget(msg)
            layout.addStretch()
            return w

        wires_dict = getattr(mgr, "_wires", {}) or {}
        ledgers = getattr(mgr, "_ledgers", {}) or {}
        transactions = getattr(mgr, "_transactions", []) or []
        getattr(mgr, "_bot_refs", {}) or {}

        # The key is kept when the percentage is refused, the same way
        # the inbound side keeps it.
        outbound = {
            tgt_id: _as_finite_float(pct)
            for tgt_id, pct in dict(wires_dict.get(bot_id, {})).items()
        }
        inbound: dict = {}
        for src_id, targets in wires_dict.items():
            if isinstance(targets, dict) and bot_id in targets:
                # The key is kept when the value is refused: the wire
                # exists and only its percentage is unreadable.
                inbound[src_id] = _as_finite_float(targets[bot_id])

        ledger = ledgers.get(bot_id)

        summary = QGroupBox("Swarm Connections && Capital Flow")
        sf = QFormLayout(summary)
        self._configure_form(sf)

        sf.addRow("Outbound wires:", QLabel(f"{len(outbound)} target(s)"))
        sf.addRow("Inbound wires:", QLabel(f"{len(inbound)} source(s)"))

        wired_in = _as_finite_float(getattr(ledger, "wired_in", 0)) if ledger else 0.0
        wired_out = _as_finite_float(getattr(ledger, "wired_out", 0)) if ledger else 0.0
        in_lbl = QLabel("—" if wired_in is None else f"${wired_in:,.4f}")
        in_lbl.setStyleSheet(
            "font-weight: bold; color: "
            + (
                ds.SUCCESS
                if wired_in is not None and wired_in > 0
                else ds.TEXT_INACTIVE
            )
        )
        sf.addRow("Lifetime wired-in (received):", in_lbl)

        out_lbl = QLabel("—" if wired_out is None else f"${wired_out:,.4f}")
        out_lbl.setStyleSheet(
            "font-weight: bold; color: "
            + (
                ds.FOLD_RATIO_AMBER
                if wired_out is not None and wired_out > 0
                else ds.TEXT_INACTIVE
            )
        )
        sf.addRow("Lifetime wired-out (sent):", out_lbl)

        # Net flow inherits the refusal: with one leg unreadable the
        # difference is unknowable.
        if wired_in is None or wired_out is None:
            net_lbl = QLabel("—")
            net_lbl.setStyleSheet(f"font-weight: bold; color: {ds.TEXT_INACTIVE};")
        else:
            net_flow = wired_in - wired_out
            net_lbl = QLabel(f"${net_flow:+,.4f}")
            net_lbl.setStyleSheet(
                "font-weight: bold; color: "
                + (ds.SUCCESS if net_flow >= 0 else ds.ERROR)
            )
        sf.addRow("Net flow (in − out):", net_lbl)

        pending_usd = _as_finite_float(getattr(self._bot, "_pending_wire_credits", 0))
        pending_lbl = QLabel("—" if pending_usd is None else f"${pending_usd:,.4f}")
        if pending_usd is not None and pending_usd > 0:
            pending_lbl.setStyleSheet(
                f"font-weight: bold; color: {ds.FOLD_SOURCE_MANUAL};"
            )
        sf.addRow("Pending wire credits:", pending_lbl)

        layout.addWidget(summary)

        if ledger is not None:
            prov_group = QGroupBox(PROVENANCE_GROUP_TITLE_QT)
            pf = QFormLayout(prov_group)
            self._configure_form(pf)

            starting = _as_finite_float(getattr(ledger, "starting_balance", 0))
            pf.addRow(
                "Starting balance (seed):",
                QLabel("—" if starting is None else f"${starting:,.4f}"),
            )

            pred_src = None
            pred_refused = False
            try:
                pred_src = ledger.predominant_source
            except Exception:  # R28-OK: defensive accessor probe
                pred_refused = True
                pred_src = None
            if pred_refused:
                pf.addRow("Predominant funder (PPS):", QLabel("—"))
            elif pred_src:
                pf.addRow("Predominant funder (PPS):", QLabel(str(pred_src)))
            else:
                pf.addRow("Predominant funder (PPS):", QLabel("— (SEED-funded only)"))

            prov_dict = dict(getattr(ledger, "provenance", {}) or {})
            if prov_dict:
                # Largest admitted amount first, then the funders whose
                # amount no reading admits, by name.
                prov_read: list = []
                prov_refused: list = []
                for _src, _amt in prov_dict.items():
                    _read = _as_finite_float(_amt)
                    if _read is None:
                        prov_refused.append(_src)
                    else:
                        prov_read.append((_src, _read))
                prov_read.sort(key=lambda kv: (-kv[1], str(kv[0])))
                prov_str = ", ".join(
                    [f"{k}: ${v:,.2f}" for k, v in prov_read]
                    + [f"{k}: —" for k in sorted(prov_refused, key=str)]
                )
                prov_label = QLabel(prov_str)
                prov_label.setWordWrap(True)
                prov_label.setStyleSheet(f"color: {ds.TEXT_NEUTRAL}; font-size: 11px;")
                pf.addRow("Provenance breakdown:", prov_label)

            layout.addWidget(prov_group)

        if outbound:
            out_group = QGroupBox(f"Outbound Wires ({len(outbound)})")
            ol = QVBoxLayout(out_group)

            out_tbl = QTableWidget()
            out_tbl.setColumnCount(3)
            out_tbl.setHorizontalHeaderLabels(
                ["Target Bot", "Wire %", "Lifetime $ to target"]
            )
            out_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            out_tbl.setRowCount(len(outbound))
            out_tbl.setMaximumHeight(180)
            out_tbl.setAlternatingRowColors(True)
            out_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

            # An unreadable leg poisons the total rather than vanishing
            # from it: a skipped row would print a sum that is short.
            out_lifetime: dict = {tgt: 0.0 for tgt in outbound}
            out_unreadable: set = set()
            for tx in transactions:
                if (
                    getattr(tx, "source_bot", None) == bot_id
                    and getattr(tx, "target_bot", None) in out_lifetime
                ):
                    _amt = _as_finite_float(getattr(tx, "amount", None))
                    if _amt is None:
                        out_unreadable.add(tx.target_bot)
                    else:
                        out_lifetime[tx.target_bot] += _amt

            for row, (tgt_id, pct) in enumerate(sorted(outbound.items())):
                tgt_asset = ""
                tgt_ledger = ledgers.get(tgt_id)
                if tgt_ledger:
                    tgt_asset = getattr(tgt_ledger, "asset", "") or ""
                label = f"{tgt_id}" + (f" ({tgt_asset})" if tgt_asset else "")
                out_tbl.setItem(row, 0, QTableWidgetItem(label))
                out_tbl.setItem(
                    row, 1, QTableWidgetItem("—" if pct is None else f"{pct:.2f}%")
                )
                lifetime = out_lifetime.get(tgt_id, 0.0)
                out_tbl.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        "—" if tgt_id in out_unreadable else f"${lifetime:,.4f}"
                    ),
                )

            ol.addWidget(out_tbl)
            layout.addWidget(out_group)

        if inbound:
            in_group = QGroupBox(f"Inbound Wires ({len(inbound)})")
            il = QVBoxLayout(in_group)

            in_tbl = QTableWidget()
            in_tbl.setColumnCount(3)
            in_tbl.setHorizontalHeaderLabels(
                ["Source Bot", "Wire %", "Lifetime $ from source"]
            )
            in_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            in_tbl.setRowCount(len(inbound))
            in_tbl.setMaximumHeight(180)
            in_tbl.setAlternatingRowColors(True)
            in_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

            in_lifetime: dict = {src: 0.0 for src in inbound}
            in_unreadable: set = set()
            for tx in transactions:
                if (
                    getattr(tx, "target_bot", None) == bot_id
                    and getattr(tx, "source_bot", None) in in_lifetime
                ):
                    _amt = _as_finite_float(getattr(tx, "amount", None))
                    if _amt is None:
                        in_unreadable.add(tx.source_bot)
                    else:
                        in_lifetime[tx.source_bot] += _amt

            for row, (src_id, pct) in enumerate(sorted(inbound.items())):
                src_asset = ""
                src_ledger = ledgers.get(src_id)
                if src_ledger:
                    src_asset = getattr(src_ledger, "asset", "") or ""
                label = f"{src_id}" + (f" ({src_asset})" if src_asset else "")
                in_tbl.setItem(row, 0, QTableWidgetItem(label))
                in_tbl.setItem(
                    row, 1, QTableWidgetItem("—" if pct is None else f"{pct:.2f}%")
                )
                lifetime = in_lifetime.get(src_id, 0.0)
                in_tbl.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        "—" if src_id in in_unreadable else f"${lifetime:,.4f}"
                    ),
                )

            il.addWidget(in_tbl)
            layout.addWidget(in_group)

        pending_ledger = list(getattr(self._bot, "_pending_wire_ledger", []) or [])
        if pending_ledger:
            pl_group = QGroupBox(f"Pending Wire Credits ({len(pending_ledger)})")
            pll = QVBoxLayout(pl_group)

            pl_tbl = QTableWidget()
            pl_tbl.setColumnCount(4)
            pl_tbl.setHorizontalHeaderLabels(["Age", "Source", "USD", "Ref"])
            pl_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            pl_tbl.setRowCount(len(pending_ledger))
            pl_tbl.setMaximumHeight(180)
            pl_tbl.setAlternatingRowColors(True)
            pl_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

            for row, credit in enumerate(pending_ledger):
                # Restored verbatim as `dict(_e)` with no key coerced,
                # so `ts` arrives as `json.load` decoded it.
                cts = _as_finite_float(credit.get("ts"))
                if cts is not None and cts > 0:
                    age_str = self._format_age(now_ts - cts)
                else:
                    age_str = "—"
                pl_tbl.setItem(row, 0, QTableWidgetItem(age_str))
                pl_tbl.setItem(row, 1, QTableWidgetItem(str(credit.get("source", "?"))))
                cusd = _as_finite_float(credit.get("usd"))
                pl_tbl.setItem(
                    row,
                    2,
                    QTableWidgetItem("—" if cusd is None else f"${cusd:,.4f}"),
                )
                pl_tbl.setItem(row, 3, QTableWidgetItem(str(credit.get("ref", ""))))

            pll.addWidget(pl_tbl)
            layout.addWidget(pl_group)

        recent_tx = [
            tx
            for tx in reversed(transactions)
            if (
                getattr(tx, "source_bot", None) == bot_id
                or getattr(tx, "target_bot", None) == bot_id
            )
        ][:20]
        if recent_tx:
            tx_group = QGroupBox(f"Recent Wire Transactions (last {len(recent_tx)})")
            tl = QVBoxLayout(tx_group)

            tx_tbl = QTableWidget()
            tx_tbl.setColumnCount(5)
            tx_tbl.setHorizontalHeaderLabels(
                ["Age", "Direction", "Other Bot", "USD", "Type"]
            )
            tx_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            tx_tbl.setRowCount(len(recent_tx))
            tx_tbl.setMaximumHeight(280)
            tx_tbl.setAlternatingRowColors(True)
            tx_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

            for row, tx in enumerate(recent_tx):
                # Nothing restores `_transactions` from saved state, and
                # `WireTransaction` does not enforce its own types.
                cts = _as_finite_float(getattr(tx, "timestamp", None))
                if cts is not None and cts > 0:
                    age_str = self._format_age(now_ts - cts)
                else:
                    age_str = "—"
                tx_tbl.setItem(row, 0, QTableWidgetItem(age_str))

                src = getattr(tx, "source_bot", "")
                tgt = getattr(tx, "target_bot", "")
                if src == bot_id:
                    direction_str = "OUT →"
                    other = tgt
                    dir_color = ds.FOLD_RATIO_AMBER
                else:
                    direction_str = "← IN"
                    other = src
                    dir_color = ds.SUCCESS
                di = QTableWidgetItem(direction_str)
                di.setForeground(QColor(dir_color))
                tx_tbl.setItem(row, 1, di)

                tx_tbl.setItem(row, 2, QTableWidgetItem(str(other)))
                tamt = _as_finite_float(getattr(tx, "amount", None))
                tx_tbl.setItem(
                    row,
                    3,
                    QTableWidgetItem("—" if tamt is None else f"${tamt:,.4f}"),
                )
                tx_tbl.setItem(
                    row,
                    4,
                    QTableWidgetItem(str(getattr(tx, "wire_type", "") or "")),
                )

            tl.addWidget(tx_tbl)
            layout.addWidget(tx_group)

        if (
            not outbound
            and not inbound
            and not pending_ledger
            and not recent_tx
            and ledger is None
        ):
            empty = QLabel(
                "Bot Swarm manager is attached but this bot has "
                "no wire activity yet. Outbound wires are configured "
                "via the Bot Swarm panel (drag connections between "
                "bot tiles). Inbound wires fire when other bots "
                "realize fold profit and route a configured % to "
                "this bot. Until then, this tab will populate as "
                "swarm activity occurs."
            )
            empty.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-style: italic; " "padding: 10px;"
            )
            empty.setWordWrap(True)
            layout.addWidget(empty)

        layout.addStretch()
        return w
