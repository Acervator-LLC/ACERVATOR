"""history_surface.py -- the History view model served to a frontend.

Assembles everything a History surface draws into one JSON-serialisable
dict, using ``history_read_contract`` as the only source of values. It
selects which contract functions to call and in what order; it derives no
value of its own, so a cost, a grade, a colour or a gate light on screen
is always the contract's answer rather than a second implementation.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``history.view_model`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt or a browser, so the same function
serves any frontend.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from src.exchange import history_read_contract as hrc

METHOD = "history.view_model"

SECTION = "history"


def date_text(ts: int) -> str:
    """Render a filter bound as text. A bound of 0 or less is inactive."""
    if ts <= 0:
        return "(any)"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def hydrate_rows(trades: list) -> list:
    """Give each row the ``datetime`` object the contract reads.

    ``history_read_contract`` renders the timestamp column from a row's
    ``datetime`` value and falls back to its empty marker when there is
    none. JSON carries no datetime, so a row that arrived over the bridge
    has only ``timestamp``; this derives the missing value from it using
    the same UTC convention the contract's own callers use. A row that
    already carries one is passed through untouched.
    """
    hydrated = []
    for row in trades:
        if not isinstance(row, dict) or row.get("datetime") is not None:
            hydrated.append(row)
            continue
        stamp = row.get("timestamp") or 0
        filled = dict(row)
        filled["datetime"] = (
            datetime.fromtimestamp(float(stamp), tz=timezone.utc) if stamp else None
        )
        hydrated.append(filled)
    return hydrated


def build_view_model(
    trades: list,
    filters: Any,
    page: int = 0,
    bot_manager: Any = None,
    last_fetched_ts: float = 0.0,
    now_ts: Optional[float] = None,
    chrome: Optional[dict] = None,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    ``chrome`` selects which strips the page draws. An omitted or empty
    mapping leaves the renderer's own defaults in force, which draw the
    summary line, the filter bar and the pager.
    """
    retained = hrc.apply_filters(hydrate_rows(trades), filters)
    gate_index, voting_index = hrc.build_join_indexes(hrc.page_slice(retained, page))
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
        "from_text": date_text(filters.from_ts),
        "to_text": date_text(filters.to_ts),
        "chrome": dict(chrome) if chrome else {},
    }


def filters_from(params: dict) -> Any:
    """Return the ``HistoryFilters`` a request asked for.

    Filters arrive as the contract's own field names; any the caller omits
    keep the value ``history_read_contract.default_filters`` chose.
    """
    supplied = params.get("filters") or {}
    filters = hrc.default_filters(params.get("now_ts"))
    known = {k: supplied[k] for k in hrc.HistoryFilters().as_dict() if k in supplied}
    if known:
        filters = replace(filters, **known)
    return filters


def view_model(params: dict) -> dict:
    """Bridge handler for ``history.view_model``.

    Reads ``trades``, ``page``, ``last_fetched_ts``, ``now_ts`` and
    ``chrome`` from the request parameters, and its filters from
    ``filters_from``.
    """
    return build_view_model(
        params.get("trades") or [],
        filters_from(params),
        page=int(params.get("page") or 0),
        last_fetched_ts=float(params.get("last_fetched_ts") or 0.0),
        now_ts=params.get("now_ts"),
        chrome=params.get("chrome"),
    )


def live_view_model(params: dict, live: Any) -> dict:
    """Build the History view model from ``live``, not from the request.

    ``live.section(SECTION)`` carries the trades and the fetch time the
    running History tab published, and ``live.bot_manager`` names each
    row's bot; ``view_model`` answers while that section holds no trades.
    """
    published = live.section(SECTION)
    if "trades" not in published:
        return view_model(params)
    return build_view_model(
        published.get("trades") or [],
        filters_from(params),
        page=int(params.get("page") or 0),
        bot_manager=getattr(live, "bot_manager", None),
        last_fetched_ts=float(published.get("last_fetched_ts") or 0.0),
        now_ts=params.get("now_ts"),
        chrome=params.get("chrome"),
    )


def bind_live(live: Any) -> Any:
    """Return a ``history.view_model`` handler reading ``live``.

    ``src.core.desktop_bridge.build_registry`` calls this when the running
    program serves the bridge, and the handler defers to ``live_view_model``.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
