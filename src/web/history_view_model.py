"""The History panel's view model, built without Qt.

``build_view_model`` turns ``src.exchange.history_read_contract`` answers
into the one JSON-serialisable payload ``src/gui/web/history_panel.js``
renders. Two hosts consume it: the Qt panel in
``src/gui/react_history_panel.py`` and the HTTP server in
``src/web/history_server.py``. One payload builder, so the two hosts
cannot disagree about what History is.

It decides no value of its own. Every field is a contract answer.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.exchange import history_read_contract as hrc


def asset_dir() -> Path:
    """The directory holding the panel's JS and CSS.

    Two candidates, in order. ``__file__`` covers running from source.
    ``sys._MEIPASS`` covers the frozen build, where
    ``tools/spec_common.py:datas_candidates`` ships the whole ``src``
    directory to ``<bundle>/src``.
    """
    beside_package = Path(__file__).resolve().parents[1] / "gui" / "web"
    if beside_package.is_dir():
        return beside_package
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "src" / "gui" / "web"
    return beside_package


def _date_text(ts: int) -> str:
    """A filter bound as text. 0 means the bound is inactive."""
    if ts <= 0:
        return "(any)"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def build_view_model(
    trades: list,
    filters: Any,
    page: int = 0,
    bot_manager: Any = None,
    last_fetched_ts: float = 0.0,
    now_ts: Optional[float] = None,
    filtered: Optional[list] = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
    chrome: Optional[dict] = None,
) -> dict:
    """Everything the page draws, as one JSON-serialisable dict.

    Every field is the contract's answer. This function chooses which of
    the contract's functions to call and in what order; it decides no
    value of its own.

    ``filtered`` is the retained set when the caller has already applied
    the filters and counted the result. Supplying it skips a second
    filter pass over the same rows; the contract's own pass runs when it
    is omitted.

    ``gate_index`` and ``voting_index`` are the caller's per-page join
    indexes. Supplying them keeps the log read to one per page.
    """
    retained = hrc.apply_filters(trades, filters) if filtered is None else filtered
    rendered = hrc.build_page(retained, page, bot_manager, gate_index, voting_index)
    return {
        "columns": [
            {
                "index": c.index,
                "key": c.key,
                "header": c.header,
                "header_tooltip": c.header_tooltip,
            }
            for c in hrc.COLUMNS
        ],
        "page": rendered.as_dict(),
        "summary": hrc.summary_line(retained, len(trades), last_fetched_ts, now_ts),
        "filters": filters.as_dict(),
        "filter_options": hrc.filter_options(trades),
        "loaded": len(trades),
        "from_text": _date_text(filters.from_ts),
        "to_text": _date_text(filters.to_ts),
        "chrome": dict(chrome) if chrome else {},
    }
