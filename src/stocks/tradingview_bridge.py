"""TradingView webhook intake and chart URL construction.

``TradingViewBridge`` listens for alert posts on ``/webhook`` and turns each
body into a ``TVAlert`` through ``_parse_alert``. Every callable added with
``register_handler`` then receives that alert. ``get_chart_url`` builds a
tradingview.com embed URL as text and opens no connection.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import time
from dataclasses import dataclass
from typing import Mapping, Optional, Callable

BIND_ALL_INTERFACES = str(ipaddress.IPv4Address(0))

logger = logging.getLogger("acervator.stocks.tradingview")


@dataclass
class TVAlert:
    """One alert ``_parse_alert`` accepted, with ``raw`` holding the body it read."""

    timestamp: float
    symbol: str
    action: str  # lowercased by _parse_alert; "buy", "sell", "close" or "info"
    price: float = 0
    quantity: float = 0
    strategy: str = ""  # Pine Script strategy name
    message: str = ""
    timeframe: str = ""
    indicator: str = ""
    raw: str = ""


class TradingViewBridge:
    """Webhook intake for TradingView alerts.

    ``start`` serves ``/webhook``, ``/health`` and ``/status`` on ``_bind_host``
    and ``_port``, falling back to ``_start_basic_server`` without aiohttp.
    ``_alert_history`` keeps the last ``_max_history`` alerts ``_parse_alert``
    accepted.
    """

    DEFAULT_PORT = 8742
    # TradingView posts alerts from its own servers, which cannot reach loopback.
    DEFAULT_BIND_HOST = "127.0.0.1"

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        bind_host: str = DEFAULT_BIND_HOST,
        force_unauthenticated_lan: bool = False,
    ):
        self._port = port
        self._bind_host = bind_host
        self._force_unauthenticated_lan = bool(force_unauthenticated_lan)
        self._server = None
        self._running = False
        self._handlers: list[Callable[[TVAlert], None]] = []
        self._alert_history: list[TVAlert] = []
        self._max_history = 1000
        self._auth_token: str = ""
        if bind_host == BIND_ALL_INTERFACES:
            logger.warning(
                "TradingView bridge binding to 0.0.0.0 — webhook server "
                "will be reachable from the local network. Ensure auth "
                "token is configured (set_auth_token) before exposing."
            )

    @property
    def port(self) -> int:
        return self._port

    @property
    def running(self) -> bool:
        return self._running

    @property
    def alert_history(self) -> list[TVAlert]:
        return list(self._alert_history)

    def set_auth_token(self, token: str):
        """Store *token* as ``_auth_token`` for ``_check_auth`` to match."""
        self._auth_token = token

    def _check_auth(self, headers: Mapping[str, str]) -> bool:
        """Return True when *headers* carry the ``_auth_token`` bearer value.

        An empty ``_auth_token`` returns True for any request, and the match runs
        through ``hmac.compare_digest``.
        """
        if not self._auth_token:
            return True
        # aiohttp and http.server expose different header objects, both with .get.
        try:
            auth = headers.get("Authorization", "") or ""
        except Exception:
            auth = ""
        expected = f"Bearer {self._auth_token}"
        return hmac.compare_digest(auth, expected)

    def register_handler(self, handler: Callable[[TVAlert], None]):
        """Append *handler* to ``_handlers``, which every parsed alert reaches."""
        self._handlers.append(handler)

    def unregister_handler(self, handler: Callable):
        """Drop *handler* from ``_handlers``."""
        self._handlers = [h for h in self._handlers if h != handler]

    async def start(self):
        """Serve ``/webhook``, ``/health`` and ``/status`` on ``_bind_host``.

        Refuses ``BIND_ALL_INTERFACES`` with no ``_auth_token`` unless
        ``_force_unauthenticated_lan`` is set.
        """
        if self._running:
            return

        if self._bind_host == BIND_ALL_INTERFACES and not self._auth_token:
            if not self._force_unauthenticated_lan:
                raise RuntimeError(
                    "TradingView bridge refusing to start: "
                    "bind_host='0.0.0.0' with no auth token configured. "
                    "Trade-alert injection from anyone on the LAN would "
                    "be possible. Resolve via one of:\n"
                    "  (a) bridge.set_auth_token('your-secret') BEFORE "
                    "calling start() — recommended\n"
                    "  (b) construct with bind_host='127.0.0.1' (the "
                    "default; restricts to local machine)\n"
                    "  (c) construct with force_unauthenticated_lan=True "
                    "to explicitly opt in to unauthenticated LAN exposure "
                    "(NOT recommended)"
                )
            logger.warning(
                "TradingView bridge starting on 0.0.0.0 with NO AUTH "
                "TOKEN — force_unauthenticated_lan=True was set "
                "explicitly. Anyone on the local network can submit "
                "trade alerts."
            )

        try:
            from aiohttp import web

            app = web.Application()
            app.router.add_post("/webhook", self._handle_webhook)
            app.router.add_get("/health", self._handle_health)
            app.router.add_get("/status", self._handle_status)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, self._bind_host, self._port)
            await site.start()

            self._server = runner
            self._running = True
            logger.info("TradingView webhook server started on port %d", self._port)
        except ImportError:
            logger.warning(
                "aiohttp not installed — webhook server unavailable. "
                "Install with: pip install aiohttp"
            )
            await self._start_basic_server()
        except Exception as e:
            logger.error("Failed to start webhook server: %s", e)

    async def stop(self):
        """Clean up ``_server`` and clear ``_running``."""
        if self._server:
            try:
                await self._server.cleanup()
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning("TradingView bridge request failed: %s", _sf_exc)
        self._running = False
        logger.info("TradingView webhook server stopped")

    async def _handle_webhook(self, request):
        """Parse the *request* body with ``_parse_alert``, then call ``_handlers``.

        Returns 401 when ``_check_auth`` refuses the request.
        """
        from aiohttp import web

        if not self._check_auth(request.headers):
            return web.Response(status=401, text="Unauthorized")

        try:
            body = await request.text()
            alert = self._parse_alert(body)

            if alert:
                self._alert_history.append(alert)
                if len(self._alert_history) > self._max_history:
                    self._alert_history = self._alert_history[-self._max_history :]

                logger.info(
                    "TV Alert: %s %s @ $%.2f (%s)",
                    alert.action,
                    alert.symbol,
                    alert.price,
                    alert.strategy,
                )

                for handler in self._handlers:
                    try:
                        handler(alert)
                    except Exception as e:
                        logger.error("Alert handler failed: %s", e)

                return web.Response(status=200, text="OK")
            else:
                return web.Response(status=400, text="Could not parse alert")

        except Exception as e:
            logger.error("Webhook error: %s", e)
            return web.Response(status=500, text=str(e))

    async def _handle_health(self, request):
        """Return 200 on the ``/health`` route ``start`` registers."""
        from aiohttp import web

        return web.Response(status=200, text="OK")

    async def _handle_status(self, request):
        """Return ``_running``, ``_port`` and the ``_alert_history`` count as JSON."""
        from aiohttp import web

        status = {
            "running": self._running,
            "port": self._port,
            "handlers": len(self._handlers),
            "alerts_received": len(self._alert_history),
            "last_alert": (
                self._alert_history[-1].timestamp if self._alert_history else 0
            ),
        }
        return web.json_response(status)

    async def _start_basic_server(self):
        """Serve ``WebhookHandler`` from ``http.server.HTTPServer`` on a daemon thread.

        ``start`` calls this where ``aiohttp`` will not import.
        """
        import http.server
        import threading

        class WebhookHandler(http.server.BaseHTTPRequestHandler):
            bridge = self

            def do_POST(self_inner):
                if not self.bridge._check_auth(self_inner.headers):
                    self_inner.send_response(401)
                    self_inner.end_headers()
                    return
                length = int(self_inner.headers.get("Content-Length", 0))
                body = self_inner.rfile.read(length).decode()
                alert = self.bridge._parse_alert(body)
                if alert:
                    self.bridge._alert_history.append(alert)
                    for handler in self.bridge._handlers:
                        try:
                            handler(alert)
                        except Exception as _sf_exc:  # noqa: BLE001
                            logger.warning(
                                "TradingView bridge request failed: %s", _sf_exc
                            )
                    self_inner.send_response(200)
                else:
                    self_inner.send_response(400)
                self_inner.end_headers()

            def log_message(self_inner, format: str, *args: object) -> None:
                logger.debug(format, *args)

        def run_server():
            server = http.server.HTTPServer(
                (self._bind_host, self._port), WebhookHandler
            )
            self._server = server
            self._running = True
            logger.info("Basic webhook server started on port %d", self._port)
            server.serve_forever()

        thread = threading.Thread(
            target=run_server, daemon=True, name="tv-bridge-server"
        )
        thread.start()

    def _parse_alert(self, body: str) -> Optional[TVAlert]:
        """Return a ``TVAlert`` built from a JSON *body* or the plain-text form.

        Returns None where neither shape yields a symbol and an action.
        """
        now = time.time()

        try:
            data = json.loads(body)
            return TVAlert(
                timestamp=now,
                symbol=data.get("symbol", data.get("ticker", "")).upper(),
                action=data.get("action", data.get("order", "info")).lower(),
                price=float(data.get("price", data.get("close", 0))),
                quantity=float(data.get("quantity", data.get("qty", 0))),
                strategy=data.get("strategy", data.get("name", "")),
                message=data.get("message", data.get("msg", "")),
                timeframe=data.get("timeframe", data.get("interval", "")),
                indicator=data.get("indicator", ""),
                raw=body,
            )
        except (json.JSONDecodeError, ValueError):
            pass

        # Plain-text form: "BUY AAPL @ 185.50".
        try:
            parts = body.strip().split()
            if len(parts) >= 2:
                action = parts[0].lower()
                symbol = parts[1].upper()
                price = 0
                if "@" in parts:
                    idx = parts.index("@")
                    if idx + 1 < len(parts):
                        price = float(parts[idx + 1])
                return TVAlert(
                    timestamp=now, symbol=symbol, action=action, price=price, raw=body
                )
        except Exception as _sf_exc:  # noqa: BLE001
            logger.warning("TradingView bridge request failed: %s", _sf_exc)

        return None

    @staticmethod
    def get_chart_url(symbol: str, interval: str = "D", theme: str = "dark") -> str:
        """Build a tradingview.com widgetembed URL for *symbol* at *interval*.

        The result is text; ``get_chart_url`` opens no connection of its own.
        """
        return (
            f"https://www.tradingview.com/widgetembed/?frameElementId=tv_chart"
            f"&symbol={symbol}&interval={interval}&theme={theme}"
            f"&style=1&locale=en&toolbarbg=f1f3f6&enable_publishing=0"
            f"&hide_side_toolbar=0&allow_symbol_change=1"
        )

    def get_summary(self) -> dict:
        """Return ``_running``, ``_port`` and ``_auth_token`` presence with counts.

        ``alerts_1h`` counts the ``_alert_history`` entries under an hour old.
        """
        recent = [a for a in self._alert_history if time.time() - a.timestamp < 3600]
        return {
            "running": self._running,
            "port": self._port,
            "auth_enabled": bool(self._auth_token),
            "handlers": len(self._handlers),
            "total_alerts": len(self._alert_history),
            "alerts_1h": len(recent),
            "last_alert_age": (
                time.time() - self._alert_history[-1].timestamp
                if self._alert_history
                else None
            ),
        }
