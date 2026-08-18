"""Fixture: zero scaffolding defects. Should produce 0 findings."""
from __future__ import annotations

import asyncio
from typing import Any


class GoodPanel:
    def __init__(self) -> None:
        self._status: Any = None
        self._real_candles: dict[str, list] = {}

    def on_click_good(self) -> None:
        loop = asyncio.new_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._do_work(), loop)
        future.add_done_callback(self._on_done)

    async def _do_work(self) -> None:
        return None

    def _on_done(self, _future: Any) -> None:
        if self._real_candles:
            print(next(iter(self._real_candles.values())))
