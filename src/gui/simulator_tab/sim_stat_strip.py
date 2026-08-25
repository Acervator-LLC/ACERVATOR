"""
src/gui/simulator_tab/sim_stat_strip.py — Inline header stat strip.

Mirrors the live Trading tab's window-level stat strip field-for-field,
but bound to the Simulator's own context (sim bot manager + sim
balances). The window-level strip is HIDDEN while the Simulator tab is
active (operator directive 2026-05-19 — "If its hidden then it does
not need the extra features, right?") — the absence of the live strip
is itself the unambiguous "you are not on live trading" signal.

Fields (10, identical to live):
  Spendable │ Realised │ Locked │ Mature │ Exch │
  Scrummed │ Folded │ Trades │ Bots │ Errors

Phase A (v3.18.3): all values show "—" placeholder; the strip is wired
into the Basic Modes flow when a battery completes (shows summary
metrics from the subprocess result) and into Nuclear Mode bindings
when those land in Phase B+.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

_PLACEHOLDER = "—"  # em-dash; matches live strip's "no data" rendering


class _StatCell(QFrame):
    """One field of the stat strip: label above, value below."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Stat Cell")
        self.setFrameShape(QFrame.NoFrame)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._label = QLabel(f"{label}:")
        self._label.setStyleSheet("color: #88aaff; font-size: 11px;")
        layout.addWidget(self._label)

        self._value = QLabel(_PLACEHOLDER)
        self._value.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        layout.addWidget(self._value)

    def set_value(self, text: str) -> None:
        self._value.setText(text if text else _PLACEHOLDER)


class SimStatStrip(QWidget):
    """
    Inline stat strip rendered at the TOP of the Simulator tab content.
    The 10 fields mirror the live Trading-tab header. No PAPER/SIM
    badge, no extras — the absence of the live header strip when this
    tab is active is itself the context differentiator (operator
    decision 2026-05-19).

    Public API:
        set(field: str, value: str) — update one field
        clear()                     — reset all fields to placeholder
    """

    FIELDS = (
        "Spendable",
        "Realised",
        "Locked",
        "Mature",
        "Exch",
        "Scrummed",
        "Folded",
        "Trades",
        "Bots",
        "Errors",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Sim Stat Strip")
        self.setObjectName("SimStatStrip")
        # Match the spacing/density of the live header strip so the
        # visual is near-identical when the operator switches tabs.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        self._cells: dict[str, _StatCell] = {}
        for field in self.FIELDS:
            cell = _StatCell(field, self)
            self._cells[field] = cell
            layout.addWidget(cell)

        layout.addStretch()

    # -- public ----------------------------------------------------------

    def set(self, field: str, value: str) -> None:
        """Update one field's displayed value. Unknown fields are
        silently ignored (callers may pass field names that don't yet
        exist while we evolve the strip)."""
        cell = self._cells.get(field)
        if cell is not None:
            cell.set_value(value)

    def clear(self) -> None:
        """Reset every field to the em-dash placeholder."""
        for cell in self._cells.values():
            cell.set_value(_PLACEHOLDER)
