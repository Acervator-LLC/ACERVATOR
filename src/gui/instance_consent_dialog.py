"""
instance_consent_dialog.py - the consent surface for issue #96
===============================================================

The guard in `src/core/instance_guard.py` decides whether this launch
may start the saved fleet by itself. When it refuses, the operator has
to SEE the refusal and make the call. This dialog is that surface.

WHAT IT MUST SHOW, AND WHY EACH LINE IS THERE
----------------------------------------------
Three facts decide the answer, so the dialog states all three and
nothing else competes with them:

1. **Which machine last wrote this fleet, and when.** Without the date
   the operator cannot tell a directory he copied last week from the one
   his own computer wrote four minutes ago.
2. **Which machine he is on now.** Both names are on screen together, so
   the comparison is a glance rather than a memory test.
3. **What happens if he continues.** The number of bots and the words
   "live exchange account" are in that sentence. A dialog that says
   "continue?" without naming the consequence collects a click, not
   consent.

THE SAFE ANSWER IS THE DEFAULT ANSWER
--------------------------------------
"Do not start bots" is the default button and the Escape key, and it is
also what closing the window with the title-bar X does. Every way of
dismissing this dialog without reading it leaves the fleet idle. The
operator can still start any bot by hand afterwards, which is itself an
explicit act.

The other button carries the bot count in its own text, so the operator
never has to look back up at the body to know what he is authorising.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtWidgets

from src.gui import design_system as ds

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from src.core.instance_guard import GuardDecision

logger = logging.getLogger("acervator.gui.instance_consent")


class InstanceConsentDialog(QtWidgets.QDialog):
    """Ask the operator whether this machine may start the saved fleet.

    `decision` is a `GuardDecision` from `src.core.instance_guard`. The
    dialog renders it and adds nothing of its own: every sentence on
    screen comes from the guard, so the words the operator reads are the
    words the log and the emitter record carry.
    """

    def __init__(self, decision: GuardDecision,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Build the dialog from one guard decision."""
        super().__init__(parent)
        self._decision = decision
        self._consented = False

        self.setAccessibleName("Instance Consent Dialog")
        self.setWindowTitle("Acervator - start the saved fleet?")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(_STYLE_SHEET)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(ds.SPACE_L, ds.SPACE_L,
                                  ds.SPACE_L, ds.SPACE_L)
        layout.setSpacing(ds.SPACE_M)

        headline = QtWidgets.QLabel(str(decision.headline))
        headline.setObjectName("headline")
        headline.setWordWrap(True)
        layout.addWidget(headline)

        detail = QtWidgets.QLabel(str(decision.detail))
        detail.setObjectName("detail")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        facts = QtWidgets.QFrame()
        facts.setObjectName("facts")
        facts_layout = QtWidgets.QVBoxLayout(facts)
        facts_layout.setContentsMargins(ds.SPACE_M, ds.SPACE_M,
                                        ds.SPACE_M, ds.SPACE_M)
        facts_layout.setSpacing(ds.SPACE_S)
        for text in (decision.owner_line, decision.this_machine_line):
            line = QtWidgets.QLabel(str(text))
            line.setObjectName("fact")
            line.setWordWrap(True)
            line.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            facts_layout.addWidget(line)
        layout.addWidget(facts)

        consequence = QtWidgets.QLabel(str(decision.consequence_line))
        consequence.setObjectName("consequence")
        consequence.setWordWrap(True)
        layout.addWidget(consequence)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(ds.SPACE_M)
        buttons.addStretch(1)

        self._refuse_button = QtWidgets.QPushButton("Do not start bots")
        self._refuse_button.setObjectName("refuse")
        self._refuse_button.setMinimumHeight(ds.TARGET_LARGE)
        self._refuse_button.setDefault(True)
        self._refuse_button.setAutoDefault(True)
        self._refuse_button.clicked.connect(self._on_refuse)
        buttons.addWidget(self._refuse_button)

        count = int(getattr(decision, "fleet_bot_count", 0) or 0)
        self._consent_button = QtWidgets.QPushButton(
            f"Take ownership and start {count} bot(s)")
        self._consent_button.setObjectName("consent")
        self._consent_button.setMinimumHeight(ds.TARGET_LARGE)
        self._consent_button.setDefault(False)
        self._consent_button.setAutoDefault(False)
        self._consent_button.clicked.connect(self._on_consent)
        # A live second copy is proved by the operating system, not
        # inferred from a file, and no answer the operator gives makes
        # two copies on one account safe. The button is therefore
        # disabled rather than present-and-ignored, so the dialog never
        # offers a choice it would refuse to honour.
        if not bool(decision.consent_is_possible):
            self._consent_button.setEnabled(False)
            self._consent_button.setToolTip(
                "Another Acervator holds the exclusive handle on this "
                "directory. Close it first.")
        buttons.addWidget(self._consent_button)

        layout.addLayout(buttons)
        self._refuse_button.setFocus()

    @property
    def consented(self) -> bool:
        """True only when the operator pressed the ownership button."""
        return self._consented

    def _on_refuse(self) -> None:
        self._consented = False
        logger.warning(
            "instance consent: operator DECLINED to start the fleet on "
            "this machine (verdict %s)",
            getattr(self._decision, "verdict", "unknown"))
        self.reject()

    def _on_consent(self) -> None:
        self._consented = True
        logger.warning(
            "instance consent: operator GRANTED ownership to this machine "
            "and authorised %s bot(s) (verdict %s)",
            getattr(self._decision, "fleet_bot_count", 0),
            getattr(self._decision, "verdict", "unknown"))
        self.accept()

    def reject(self) -> None:
        """Escape and the title-bar X land here, and both mean no.

        Qt routes both to `reject`, so the flag is cleared here as well
        as in `_on_refuse`. A dialog whose only safe path is a button the
        operator did not press is not fail-closed.
        """
        self._consented = False
        super().reject()


def release_dialog(dialog: Optional[InstanceConsentDialog]) -> None:
    """Destroy the dialog now. Never with `deleteLater()`.

    MEASURED 2026-08-23, PySide6 on Windows and on the offscreen plugin.
    Three cases, one line of output each:

        parentless dialog, Python reference dropped     0 alive
        deleteLater() first, then reference dropped     1 alive
        after sendPostedEvents(None, DeferredDelete)    0 alive

    `deleteLater()` MOVES OWNERSHIP FROM PYTHON TO C++. The object then
    waits for a `DeferredDelete` event, and `QApplication.processEvents()`
    does not deliver one - only a running event loop or an explicit
    `sendPostedEvents(None, DeferredDelete)` does. A dialog "cleaned up"
    that way therefore OUTLIVES the call that made it and stays in
    `QApplication.topLevelWidgets()`, where anything that walks that list
    picks it up. The cleanup call is what causes the leak.

    `setParent(None)` hands ownership back to Python, so the widget dies
    with the last reference to it, deterministically and with no event
    loop involved.

    `WA_DeleteOnClose` IS DELIBERATELY NOT SET ON THIS DIALOG. `exec()`
    returns and the caller must still read `consented`. Deleting on close
    would destroy the C++ object when the operator dismisses the dialog
    with the window X - one of the two safe answers - and the read after
    it would raise `RuntimeError: Internal C++ object already deleted`.
    The owner destroys the dialog after it has the answer, which is this
    function, called after the answer is already in a local.
    """
    if dialog is None:
        return
    try:
        dialog.close()
        dialog.setParent(None)
    except RuntimeError as exc:
        # The C++ object is already gone. Nothing is left to release, and
        # the answer was read before this call, so this cannot lose one.
        logger.debug("instance consent dialog was already destroyed: %s", exc)


def ask_for_consent(decision: GuardDecision,
                    parent: Optional[QtWidgets.QWidget] = None) -> bool:
    """Show the dialog and return True only on an explicit grant.

    Any failure to display returns False. A consent surface that cannot
    be drawn has collected no consent, and the caller must treat that
    exactly as a refusal.

    THE ORDER OF THE LAST THREE STEPS IS THE CONTRACT. The answer is read
    into a local FIRST, the dialog is destroyed SECOND, and the local is
    returned THIRD. Any other order reads a widget that may already be
    gone. This function owns the dialog for its whole life and leaves
    nothing behind: before this, the dialog was parented to the main
    window and stayed attached to it, hidden, for the rest of the session.
    """
    dialog: Optional[InstanceConsentDialog] = None
    try:
        dialog = InstanceConsentDialog(decision, parent=parent)
        dialog.exec()
        granted = bool(dialog.consented)
    except Exception as exc:  # noqa: BLE001 - a broken dialog means no consent
        logger.error(
            "instance consent dialog could not be shown (%s). Treating "
            "this as a refusal: no bot starts without a surface the "
            "operator can read.", exc)
        granted = False
    finally:
        release_dialog(dialog)
    return granted


_STYLE_SHEET = (
    f"QDialog {{ background: {ds.SURFACE_3}; color: {ds.TEXT_HIGH}; }}"
    f"QLabel {{ color: {ds.TEXT_MED};"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QLabel#headline {{ color: {ds.WARNING};"
    f" font-size: {ds.TYPE_H3}px;"
    f" font-weight: {ds.WEIGHT_BOLD}; }}"
    f"QLabel#detail {{ color: {ds.TEXT_HIGH}; }}"
    f"QLabel#fact {{ color: {ds.TEXT_HIGH};"
    f" font-family: {ds.FONT_FAMILY_MONO};"
    f" font-size: {ds.TYPE_SMALL}px; }}"
    f"QLabel#consequence {{ color: {ds.DANGER}; }}"
    f"QFrame#facts {{ background: {ds.SURFACE_1};"
    f" border: 1px solid {ds.OUTLINE};"
    f" border-radius: {ds.RADIUS_SM}px; }}"
    f"QPushButton {{ background: {ds.SURFACE_2};"
    f" color: {ds.TEXT_HIGH};"
    f" border: 1px solid {ds.OUTLINE};"
    f" border-radius: {ds.RADIUS_SM}px;"
    f" padding: {ds.SPACE_S}px {ds.SPACE_L}px;"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QPushButton#refuse {{ border: {ds.FOCUS_RING_WIDTH}px solid"
    f" {ds.PRIMARY}; color: {ds.PRIMARY}; }}"
    f"QPushButton#consent {{ color: {ds.DANGER};"
    f" border: 1px solid {ds.DANGER}; }}"
    f"QPushButton:focus {{ outline: none;"
    f" border: {ds.FOCUS_RING_WIDTH}px solid {ds.FOCUS_RING_COLOR}; }}"
)
"""Built from `design_system` tokens only. A hex literal in widget code
is an R65 violation, and the linter reads this file like any other."""
