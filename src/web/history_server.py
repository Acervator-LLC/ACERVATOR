"""A loopback HTTP server for the React History panel.

WHAT IT SERVES

    GET /                 the page shell, which loads the assets below
    GET /assets/<name>    the files under ``src/gui/web`` (.js and .css)
    GET /api/history      the History view model as JSON

The JSON is what ``src/gui/web/history_panel.js`` already consumes: the
shell's bootstrap hands the response to ``window.acervatorSetState``,
the same payload the Qt host pushes over its bridge.

IT CANNOT TRADE, AND THAT IS STRUCTURAL

Three properties, none of them a runtime check:

    1. The import closure is ``history_read_contract`` and
       ``history_view_model`` plus the standard library. No exchange
       connector, no bot container and no broker is reachable, so no
       order-placing call is reachable.
       ``tests/test_history_server.py`` walks that closure.
    2. Trades arrive from an injected ``TradeSource``. The default,
       ``no_trades``, returns an empty list, so the process opens no
       connection and reads no credential.
    3. The handler defines ``do_GET`` and nothing else. Every other HTTP
       method answers 501 from ``BaseHTTPRequestHandler``.

THE BIND ADDRESS IS A CONSTANT, NOT A PARAMETER

``LOOPBACK_HOST`` is the only address this module binds. There is no
host argument to pass wrong.
"""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, unquote, urlparse

from src.exchange import history_read_contract as hrc
from src.web.history_view_model import asset_dir, build_view_model

logger = logging.getLogger("acervator.web.history")

LOOPBACK_HOST = "127.0.0.1"
"""The only interface this module binds. A public bind would expose the
operator's trade history to the network."""

DEFAULT_PORT = 8765

INDEX_ROUTE = "/"
DATA_ROUTE = "/api/history"
ASSET_PREFIX = "/assets/"

ASSET_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
"""The only two suffixes served from the asset directory. A file whose
suffix is not a key here is a 404."""

JSON_CONTENT_TYPE = "application/json; charset=utf-8"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"

TradeSource = Callable[[], list]
"""Returns normalized trade rows, newest first: the shape
``history_helpers.normalize_trade`` emits."""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acervator History</title>
<link rel="stylesheet" href="/assets/history_panel.css">
</head>
<body>
<div id="root"></div>
<script src="/assets/vendor/react.production.min.js"></script>
<script src="/assets/vendor/react-dom.production.min.js"></script>
<script src="/assets/history_panel.js"></script>
<script>
window
  .fetch("/api/history")
  .then(function (response) {
    return response.json();
  })
  .then(function (state) {
    window.acervatorSetState(state);
  })
  .catch(function () {
    window.acervatorSetState(null);
  });
</script>
</body>
</html>
"""


def no_trades() -> list:
    """The default trade source: no rows.

    A server started with this reads no credential and opens no exchange
    connection. A host that has rows injects its own source.
    """
    return []


def resolve_asset(request_path: str) -> Optional[Path]:
    """The file under the asset root a ``/assets/`` path names, or None.

    None for a path that escapes the root, for a suffix outside
    ``ASSET_CONTENT_TYPES`` and for anything that is not a regular file.
    The path is percent-decoded first, so an encoded ``..`` is rejected
    by the same rule as a literal one.
    """
    if not request_path.startswith(ASSET_PREFIX):
        return None
    relative = unquote(request_path[len(ASSET_PREFIX) :])
    parts = [part for part in relative.split("/") if part]
    if not parts:
        return None
    if any(part in (".", "..") or "\\" in part or ":" in part for part in parts):
        return None
    candidate = asset_dir().joinpath(*parts)
    if candidate.suffix.lower() not in ASSET_CONTENT_TYPES:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _as_int(text: str) -> int:
    """The integer a query value carries, or 0 when it carries none."""
    try:
        return int(text)
    except ValueError:
        return 0


def _first(parsed: dict, name: str, fallback: str) -> str:
    values = parsed.get(name) or []
    return values[0] if values else fallback


def filters_from_query(query: str) -> hrc.HistoryFilters:
    """The five contract filters a query string carries.

    An absent or unparseable bound is 0, which the contract reads as
    inactive. An absent dropdown is ``hrc.ALL``.
    """
    parsed = parse_qs(query)
    return hrc.HistoryFilters(
        from_ts=_as_int(_first(parsed, "from", "0")),
        to_ts=_as_int(_first(parsed, "to", "0")),
        exchange=_first(parsed, "exchange", hrc.ALL),
        symbol=_first(parsed, "symbol", hrc.ALL),
        side=_first(parsed, "side", hrc.ALL),
    )


def history_payload(trades: list, query: str) -> dict:
    """The view model for one request, as the frontend consumes it.

    ``last_fetched_ts`` is 0: this server serves what its source holds
    and fetches nothing, so the summary reads "no fetch yet".
    """
    page = _as_int(_first(parse_qs(query), "page", "0"))
    return build_view_model(
        trades,
        filters_from_query(query),
        page=page,
        bot_manager=None,
        last_fetched_ts=0.0,
    )


class HistoryHandler(BaseHTTPRequestHandler):
    """Answers the three GET routes.

    No other ``do_*`` method is defined, so every mutating request
    answers 501 from ``BaseHTTPRequestHandler``.
    """

    server_version = "AcervatorHistory"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        """Route one request. Unknown paths answer 404 as JSON."""
        route = urlparse(self.path)
        if route.path == INDEX_ROUTE:
            self._send(HTTPStatus.OK, HTML_CONTENT_TYPE, INDEX_HTML.encode("utf-8"))
            return
        if route.path == DATA_ROUTE:
            trades = self.server.trade_source()
            self._send_json(HTTPStatus.OK, history_payload(trades, route.query))
            return
        asset = resolve_asset(route.path)
        if asset is not None:
            self._send(
                HTTPStatus.OK,
                ASSET_CONTENT_TYPES[asset.suffix.lower()],
                asset.read_bytes(),
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "no such route"})

    def log_message(self, format: str, *args: Any) -> None:
        """Send the access line to the application logger, not stderr."""
        logger.debug("%s %s", self.address_string(), format % args)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("ascii")
        self._send(status, JSON_CONTENT_TYPE, body)

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class HistoryServer(ThreadingHTTPServer):
    """The serving process, bound to ``LOOPBACK_HOST``.

    ``port`` 0 binds a free port; read the bound one back from ``url``.
    """

    daemon_threads = True

    def __init__(self, source: TradeSource = no_trades, port: int = DEFAULT_PORT):
        super().__init__((LOOPBACK_HOST, port), HistoryHandler)
        self.trade_source: TradeSource = source

    @property
    def port(self) -> int:
        """The bound port. Answers the real one after a ``port=0`` bind."""
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        """The origin the server is reachable at."""
        return f"http://{LOOPBACK_HOST}:{self.port}"


def main(argv: Optional[list] = None) -> int:
    """Serve until interrupted, with the empty trade source.

    Reads no credential and opens no exchange connection.
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.web.history_server",
        description="Serve the React History panel on loopback.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    server = HistoryServer(no_trades, args.port)
    logger.info("History server listening on %s", server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
