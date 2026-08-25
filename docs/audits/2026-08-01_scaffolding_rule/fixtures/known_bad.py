"""Fixture: ground-truth scaffolding defects.

Ground truth:
    D1 (S001, medium) — fallback string in setText call.  line ~28
    D2 (S002, high)   — wall-clock QTimer paired with async without
                        add_done_callback.                          line ~35
    D3 (S003, high)   — self._real_candles referenced but never
                        assigned in __init__.                       line ~50
    D4 (S004, low)    — placeholder TODO comment.                   line ~14
    D5 (S004, low)    — placeholder "not yet wired".                line ~44

Each rule should fire on the labeled line (± a few for the AST
walker's node.lineno accounting).
"""

from __future__ import annotations

import asyncio
from typing import Any


# D4 (S004) — TODO placeholder here
class BadPanel:  # noqa: RUF100 - fixture class name

    def __init__(self) -> None:
        self._status = None  # a status label stub

    def on_click_bad(self) -> None:
        # D1 (S001) — fallback string before verification
        if self._status is not None:
            self._status.setText(
                "Fetch YTD returned no trades. Check console log for details."
            )

        # D2 (S002) — wall-clock completion timer paired with async
        loop: Any = asyncio.new_event_loop()
        asyncio.run_coroutine_threadsafe(self._do_work(), loop)
        timer: Any = object()
        timer.timeout.connect(self._on_done)  # scheduled without add_done_callback

    async def _do_work(self) -> None:
        # D5 (S004) — "not yet wired" placeholder
        pass  # not yet wired

    def _on_done(self) -> None:
        # D3 (S003) — self._real_candles read but never assigned in __init__
        if self._real_candles:
            print(list(self._real_candles.values())[0])
