"""
tradingview_bridge.py — TradingView integration bridge.

Provides:
- Webhook HTTP server to receive TradingView alerts
- Alert parsing and signal routing to stock bots
- TradingView chart URL generation for embedded views
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Mapping, Optional, Callable

logger = logging.getLogger("acervator.stocks.tradingview")


@dataclass
class TVAlert:
    """Parsed TradingView alert."""
    timestamp: float
    symbol: str
    action: str         # "buy", "sell", "close", "info"
    price: float = 0
    quantity: float = 0
    strategy: str = ""  # Pine Script strategy name
    message: str = ""
    timeframe: str = ""
    indicator: str = ""
    raw: str = ""


class TradingViewBridge:
    """
    TradingView integration hub.
    
    Receives webhook alerts from TradingView and routes them to
    registered handlers (stock bots, notification system, journal).
    
    TradingView Alert Setup:
    1. Create alert on TradingView
    2. Set webhook URL to: http://localhost:{port}/webhook
    3. Set alert message to JSON: {"symbol":"AAPL","action":"buy","price":{{close}}}
    """

    DEFAULT_PORT = 8742
    # v3.15.85 — bind to localhost by default. Public-network exposure
    # (host="0.0.0.0") now requires explicit operator opt-in via the
    # `bind_host` constructor parameter. Closes the bandit B104 finding
    # surfaced in the v3.15.84 SADP upgrade audit.
    DEFAULT_BIND_HOST = "127.0.0.1"

    def __init__(self, port: int = DEFAULT_PORT,
                 bind_host: str = DEFAULT_BIND_HOST,
                 force_unauthenticated_lan: bool = False):
        # v3.15.89 (TV-AUTH-5 fix): force_unauthenticated_lan is the
        # escape hatch for the otherwise-blocked combination of
        # bind_host="0.0.0.0" + empty auth token. start() refuses to
        # launch the server in that combination unless this flag is
        # True. Default False — protects operators who haven't read
        # the auth audit doc.
        self._port = port
        self._bind_host = bind_host
        self._force_unauthenticated_lan = bool(force_unauthenticated_lan)
        self._server = None
        self._running = False
        self._handlers: list[Callable[[TVAlert], None]] = []
        self._alert_history: list[TVAlert] = []
        self._max_history = 1000
        self._auth_token: str = ""  # Optional auth for webhook security
        if bind_host == "0.0.0.0":  # nosec B104 — defensive comparison only, not a bind
            logger.warning(
                "TradingView bridge binding to 0.0.0.0 — webhook server "
                "will be reachable from the local network. Ensure auth "
                "token is configured (set_auth_token) before exposing.")

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
        """Set authentication token for webhook security."""
        self._auth_token = token

    def _check_auth(self, headers: Mapping[str, str]) -> bool:
        """v3.15.88 (TV-AUTH-1, TV-AUTH-2 fix) — single auth check
        for both server backends.

        Returns True if the request is authorized (or auth is
        disabled). Returns False otherwise.

        Implementation notes:
          * If ``self._auth_token`` is empty, auth is DISABLED — the
            method returns True for any request. This preserves the
            "no token configured = no auth required" semantic for
            local-bind operation. PRIORITY 1l TV-AUTH-5 covers
            tightening this when the bridge binds to 0.0.0.0.
          * Token comparison uses ``hmac.compare_digest`` to defeat
            timing-attack recovery (TV-AUTH-2). Plain ``!=`` would
            short-circuit on the first differing character, leaking
            the token byte-by-byte to a network observer measuring
            response-time deltas.
          * The basic HTTP fallback path now also calls this helper
            (TV-AUTH-1) so an operator running without aiohttp
            doesn't get an unauthenticated webhook server.
        """
        if not self._auth_token:
            return True  # auth disabled by configuration
        # `headers` may be a dict or an aiohttp/http.server Mapping.
        # `.get` is universally available; default to empty string.
        try:
            auth = headers.get("Authorization", "") or ""
        except Exception:
            auth = ""
        expected = f"Bearer {self._auth_token}"
        return hmac.compare_digest(auth, expected)

    def register_handler(self, handler: Callable[[TVAlert], None]):
        """Register a callback to receive parsed alerts."""
        self._handlers.append(handler)

    def unregister_handler(self, handler: Callable):
        """Remove a handler."""
        self._handlers = [h for h in self._handlers if h != handler]

    async def start(self):
        """Start the webhook HTTP server."""
        if self._running:
            return

        # v3.15.89 (TV-AUTH-5 fix) — refuse to expose an unauthenticated
        # webhook on the LAN. The combination of bind_host="0.0.0.0"
        # AND empty auth token means anyone on the local network can
        # submit trade alerts that dispatch directly to bot handlers.
        # Required: either set an auth token (recommended) or
        # construct with force_unauthenticated_lan=True (explicit
        # operator opt-in; warn loudly).
        if self._bind_host == "0.0.0.0" and not self._auth_token:  # nosec B104 — defensive refusal, not a bind
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
                    "(NOT recommended)\n"
                    "See docs/audits/2026-04-28_tradingview_bridge_auth_"
                    "audit.md TV-AUTH-5 for context.")
            logger.warning(
                "TradingView bridge starting on 0.0.0.0 with NO AUTH "
                "TOKEN — force_unauthenticated_lan=True was set "
                "explicitly. Anyone on the local network can submit "
                "trade alerts.")

        try:
            from aiohttp import web

            app = web.Application()
            app.router.add_post('/webhook', self._handle_webhook)
            app.router.add_get('/health', self._handle_health)
            app.router.add_get('/status', self._handle_status)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, self._bind_host, self._port)  # nosec B104 — operator-configurable; defaults to 127.0.0.1
            await site.start()

            self._server = runner
            self._running = True
            logger.info("TradingView webhook server started on port %d", self._port)
        except ImportError:
            logger.warning("aiohttp not installed — webhook server unavailable. "
                          "Install with: pip install aiohttp")
            # Fallback: basic HTTP server
            await self._start_basic_server()
        except Exception as e:
            logger.error("Failed to start webhook server: %s", e)

    async def stop(self):
        """Stop the webhook server."""
        if self._server:
            try:
                await self._server.cleanup()
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning(
                    "TradingView bridge request failed: %s", _sf_exc)
        self._running = False
        logger.info("TradingView webhook server stopped")

    async def _handle_webhook(self, request):
        """Handle incoming TradingView webhook."""
        from aiohttp import web

        # v3.15.88 — auth via shared _check_auth helper. Uses
        # hmac.compare_digest under the hood (TV-AUTH-2 fix).
        if not self._check_auth(request.headers):
            return web.Response(status=401, text="Unauthorized")

        try:
            body = await request.text()
            alert = self._parse_alert(body)

            if alert:
                self._alert_history.append(alert)
                if len(self._alert_history) > self._max_history:
                    self._alert_history = self._alert_history[-self._max_history:]

                logger.info("TV Alert: %s %s @ $%.2f (%s)",
                           alert.action, alert.symbol, alert.price, alert.strategy)

                # Dispatch to handlers
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
        """Health check endpoint."""
        from aiohttp import web
        return web.Response(status=200, text="OK")

    async def _handle_status(self, request):
        """Status endpoint."""
        from aiohttp import web
        status = {
            "running": self._running,
            "port": self._port,
            "handlers": len(self._handlers),
            "alerts_received": len(self._alert_history),
            "last_alert": self._alert_history[-1].timestamp if self._alert_history else 0,
        }
        return web.json_response(status)

    async def _start_basic_server(self):
        """Fallback: basic asyncio HTTP server without aiohttp."""
        import http.server
        import threading

        class WebhookHandler(http.server.BaseHTTPRequestHandler):
            bridge = self

            def do_POST(self_inner):
                # v3.15.88 (TV-AUTH-1 fix) — basic HTTP fallback path
                # now consults _check_auth before dispatching to handlers.
                # Pre-fix this branch had NO auth check, so an operator
                # without aiohttp was running an unauthenticated webhook.
                if not self.bridge._check_auth(self_inner.headers):
                    self_inner.send_response(401)
                    self_inner.end_headers()
                    return
                length = int(self_inner.headers.get('Content-Length', 0))
                body = self_inner.rfile.read(length).decode()
                alert = self.bridge._parse_alert(body)
                if alert:
                    self.bridge._alert_history.append(alert)
                    for handler in self.bridge._handlers:
                        try:
                            handler(alert)
                        except Exception as _sf_exc:  # noqa: BLE001
                            logger.warning(
                                "TradingView bridge request failed: %s", _sf_exc)
                    self_inner.send_response(200)
                else:
                    self_inner.send_response(400)
                self_inner.end_headers()

            def log_message(self_inner, *args):
                pass  # Suppress default logging

        def run_server():
            server = http.server.HTTPServer((self._bind_host, self._port), WebhookHandler)  # nosec B104 — operator-configurable; defaults to 127.0.0.1
            self._server = server
            self._running = True
            logger.info("Basic webhook server started on port %d", self._port)
            server.serve_forever()

        thread = threading.Thread(target=run_server, daemon=True, name="tv-bridge-server")
        thread.start()

    def _parse_alert(self, body: str) -> Optional[TVAlert]:
        """Parse a TradingView alert message."""
        now = time.time()

        # Try JSON first
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

        # Try plain text parsing: "BUY AAPL @ 185.50"
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
                    timestamp=now, symbol=symbol, action=action,
                    price=price, raw=body)
        except Exception as _sf_exc:  # noqa: BLE001
            logger.warning(
                "TradingView bridge request failed: %s", _sf_exc)

        return None

    @staticmethod
    def get_chart_url(symbol: str, interval: str = "D",
                      theme: str = "dark") -> str:
        """Generate TradingView chart embed URL."""
        return (
            f"https://www.tradingview.com/widgetembed/?frameElementId=tv_chart"
            f"&symbol={symbol}&interval={interval}&theme={theme}"
            f"&style=1&locale=en&toolbarbg=f1f3f6&enable_publishing=0"
            f"&hide_side_toolbar=0&allow_symbol_change=1"
        )

    def get_summary(self) -> dict:
        """Get bridge status summary."""
        recent = [a for a in self._alert_history
                  if time.time() - a.timestamp < 3600]
        return {
            "running": self._running,
            "port": self._port,
            "auth_enabled": bool(self._auth_token),
            "handlers": len(self._handlers),
            "total_alerts": len(self._alert_history),
            "alerts_1h": len(recent),
            "last_alert_age": (time.time() - self._alert_history[-1].timestamp
                              if self._alert_history else None),
        }
