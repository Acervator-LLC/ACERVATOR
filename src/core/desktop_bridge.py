"""desktop_bridge.py -- the request boundary between the desktop frontend
and the Python backend.

The Electron main process starts this module as a child process and talks
to it over that child's stdin and stdout. One request is one JSON object
on one line, and one response is one JSON object on one line:

    -> {"id": 1, "method": "history.view_model", "params": {...}}
    <- {"id": 1, "ok": true, "result": {...}}
    <- {"id": 1, "ok": false, "error": {"type": "...", "message": "..."}}

There is no socket and no port. The channel is the pipe the parent
already owns, so the backend is reachable only by the process that
started it and exits when that process does.

A surface is a function taking the request's ``params`` and returning a
serialisable result. ``build_registry`` names the surfaces the frontend
can reach; adding one there is what makes a new screen reachable.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, BinaryIO, Callable, Dict

logger = logging.getLogger("acervator.core.desktop_bridge")

Handler = Callable[[dict], Any]

PROTOCOL_VERSION = 1


class UnknownMethod(LookupError):
    """The request named a method no surface is registered for."""


def build_registry() -> Dict[str, Handler]:
    """Return the methods the frontend may call, keyed by method name.

    This is the wiring point for the whole frontend: a surface is
    reachable exactly when it appears here. Surfaces are imported inside
    the function so that the transport above carries no dependency on any
    one domain package.
    """
    from src.exchange import history_surface
    from src.gui.main_tabs import (
        alerts_tab_surface,
        analytics_tab_surface,
        bot_selection_surface,
        buy_confirmation_surface,
        capital_registry_surface,
        console_log_surface,
        console_tab_surface,
        dashboard_stat_card_surface,
        design_system_surface,
        header_strip_surface,
        init_wizard_surface,
        instance_consent_surface,
        journal_tab_surface,
        launcher_surface,
        live_status_tab_surface,
        notification_spool_surface,
        positions_held_surface,
        preflight_check_surface,
        privacy_dot_surface,
        react_history_panel_surface,
        sim_stat_strip_surface,
        spendable_profits_surface,
        start_all_progress_surface,
        status_log_surface,
        table_cells_surface,
        theme_engine_surface,
        trading_tab_surface,
        tradingview_chart_surface,
        visualizer_themes_surface,
        wire_canvas_surface,
    )

    return {
        history_surface.METHOD: history_surface.view_model,
        console_log_surface.METHOD: console_log_surface.view_model,
        console_tab_surface.METHOD: console_tab_surface.view_model,
        header_strip_surface.METHOD: header_strip_surface.view_model,
        trading_tab_surface.METHOD: trading_tab_surface.view_model,
        status_log_surface.METHOD: status_log_surface.view_model,
        notification_spool_surface.METHOD: notification_spool_surface.view_model,
        capital_registry_surface.METHOD: capital_registry_surface.view_model,
        bot_selection_surface.METHOD: bot_selection_surface.view_model,
        start_all_progress_surface.METHOD: start_all_progress_surface.view_model,
        buy_confirmation_surface.METHOD: buy_confirmation_surface.view_model,
        instance_consent_surface.METHOD: instance_consent_surface.view_model,
        preflight_check_surface.METHOD: preflight_check_surface.view_model,
        table_cells_surface.METHOD: table_cells_surface.view_model,
        design_system_surface.METHOD: design_system_surface.view_model,
        theme_engine_surface.METHOD: theme_engine_surface.view_model,
        alerts_tab_surface.METHOD: alerts_tab_surface.view_model,
        analytics_tab_surface.METHOD: analytics_tab_surface.view_model,
        dashboard_stat_card_surface.METHOD: dashboard_stat_card_surface.view_model,
        init_wizard_surface.METHOD: init_wizard_surface.view_model,
        journal_tab_surface.METHOD: journal_tab_surface.view_model,
        launcher_surface.METHOD: launcher_surface.view_model,
        live_status_tab_surface.METHOD: live_status_tab_surface.view_model,
        positions_held_surface.METHOD: positions_held_surface.view_model,
        privacy_dot_surface.METHOD: privacy_dot_surface.view_model,
        react_history_panel_surface.METHOD: react_history_panel_surface.view_model,
        sim_stat_strip_surface.METHOD: sim_stat_strip_surface.view_model,
        spendable_profits_surface.METHOD: spendable_profits_surface.view_model,
        tradingview_chart_surface.METHOD: tradingview_chart_surface.view_model,
        visualizer_themes_surface.METHOD: visualizer_themes_surface.view_model,
        wire_canvas_surface.METHOD: wire_canvas_surface.view_model,
        "bridge.ping": lambda params: {"protocol": PROTOCOL_VERSION},
    }


def dispatch(method: str, params: dict, registry: Dict[str, Handler]) -> Any:
    """Run one registered handler and return its result.

    Raises ``UnknownMethod`` when no surface is registered under
    ``method``; every other exception is the handler's own.
    """
    handler = registry.get(method)
    if handler is None:
        raise UnknownMethod(method)
    return handler(params or {})


def error_frame(request_id: Any, exc: BaseException) -> dict:
    """Return the response for a request that raised."""
    return {
        "id": request_id,
        "ok": False,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def handle_line(line: str, registry: Dict[str, Handler]) -> dict:
    """Turn one request line into one response object.

    Never raises: a handler that fails, a method that does not exist and
    a line that is not a JSON object all become an error response, so one
    bad request cannot end the session.
    """
    try:
        request = json.loads(line)
    except ValueError as exc:
        return error_frame(None, exc)
    if not isinstance(request, dict):
        return error_frame(None, TypeError("request must be a JSON object"))
    request_id = request.get("id")
    try:
        result = dispatch(request.get("method"), request.get("params"), registry)
    except Exception as exc:
        logger.warning("bridge method %r failed: %s", request.get("method"), exc)
        return error_frame(request_id, exc)
    return {"id": request_id, "ok": True, "result": result}


def encode_frame(response: dict) -> bytes:
    """Encode one response as the bytes of a single protocol line.

    ``ensure_ascii`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and terminate a line for the reader on the other side.
    The newline is written as one byte so that the platform's text-mode
    translation cannot put a carriage return inside the frame.
    """
    return json.dumps(response, ensure_ascii=True).encode("utf-8") + b"\n"


def serve(reader: BinaryIO, writer: BinaryIO, registry: Dict[str, Handler]) -> int:
    """Answer requests from ``reader`` on ``writer`` until the pipe closes.

    Returns the number of requests answered. Blank lines are skipped so
    that a writer padding the stream cannot produce a spurious error
    response.
    """
    answered = 0
    for raw in reader:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        writer.write(encode_frame(handle_line(text, registry)))
        writer.flush()
        answered += 1
    return answered


def main() -> int:
    """Run the bridge on this process's own stdin and stdout.

    ``sys.stdout`` is rebound to ``sys.stderr`` before the first request
    is read, so that a print or a logging handler anywhere in the backend
    cannot write a non-protocol line into the frame stream. The real
    stdout is kept as the protocol channel and is written as bytes.
    """
    channel = sys.stdout.buffer
    sys.stdout = sys.stderr
    serve(sys.stdin.buffer, channel, build_registry())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
