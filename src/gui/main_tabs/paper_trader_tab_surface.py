"""paper_trader_tab_surface.py -- the Paper tab's empty state as data.

``view_model`` answers ``HEADING``, ``STATE_TEXT`` and ``ISSUE_TEXT``: the tab's
name, the sentence saying the tab is not built, and the issue that carries the
build-out. ``src.core.desktop_bridge`` registers it under ``METHOD``, which is
how the Electron renderer reaches it. ``BUILT`` is false and ``view_model``
publishes no row, no price and no bot.
"""

from __future__ import annotations

METHOD = "paper_trader_tab.state"

HEADING = "Paper"
ISSUE = 19
BUILT = False
STATE_TEXT = "This tab is not built."
ISSUE_TEXT = f"Issue #{ISSUE} carries the build-out."

DECLARED_FIELDS = (
    "accessible_name",
    "built",
    "heading",
    "issue",
    "issue_text",
    "method",
    "state_text",
)


def view_model(params: dict) -> dict:
    """Bridge handler for ``paper_trader_tab.state``.

    Answers every name in ``DECLARED_FIELDS``, the same for any ``params``.
    """
    del params
    return {
        "accessible_name": HEADING,
        "built": BUILT,
        "heading": HEADING,
        "issue": ISSUE,
        "issue_text": ISSUE_TEXT,
        "method": METHOD,
        "state_text": STATE_TEXT,
    }
