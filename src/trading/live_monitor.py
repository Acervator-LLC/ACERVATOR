"""
live_monitor.py — Real-Time AI Feedback Loop + Official Trade Reporting
=======================================================================
Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator).
All rights reserved. See LICENSE for details.
Acervator(TM) is a trademark of Anthony L. Brown.
"""

from __future__ import annotations
import json, hashlib, logging, time, platform
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger("acervator.live_monitor")
REPORT_SCHEMA = "1.0.0"


@dataclass
class TradeRecord:
    timestamp: str
    unix_ts: float
    bot_id: str
    asset: str
    action: str
    side: str
    price: float
    quantity: float
    usd_value: float
    target_balance: float
    portfolio_value: float
    delta_pct: float
    confidence: float
    bb_position: float = 0.0
    z_score: float = 0.0
    trend_strength: float = 0.0
    tightening: bool = False
    ta_direction: str = ""
    notes: str = ""

    @property
    def record_hash(self) -> str:
        # Hashes only this record's fields; TradeJournal.record adds the chain link.
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, default=str).encode()
        ).hexdigest()


class TradeJournal:
    def __init__(self, path="acervator_journal.jsonl"):
        self._path = Path(path)
        self._last_hash = "GENESIS"
        self._seq = 0
        self._s = dict(
            trades=0,
            harvests=0,
            folds=0,
            boost_sells=0,
            boost_folds=0,
            wires=0,
            wins=0,
            pnl=0.0,
            volume=0.0,
            peak=0.0,
            max_dd=0.0,
        )
        if self._path.exists():
            self._resume()

    def _resume(self):
        with open(self._path) as f:
            for line in f:
                r = json.loads(line.strip())
                self._last_hash = r.get("chain_hash", self._last_hash)
                self._seq = r.get("seq", self._seq) + 1
                self._s["trades"] += 1

    @staticmethod
    def _chain_link(prev_hash: str, record_hash: str) -> str:
        return hashlib.sha256(f"{prev_hash}:{record_hash}".encode()).hexdigest()

    def record(self, trade: TradeRecord) -> str:
        # Builds the next chain link and appends it; the journal is never rewritten.
        ch = self._chain_link(self._last_hash, trade.record_hash)
        e = asdict(trade)
        e["chain_hash"] = ch
        e["seq"] = self._seq
        with open(self._path, "a") as f:
            f.write(json.dumps(e, default=str) + "\n")
        self._last_hash = ch
        self._seq += 1
        s = self._s
        s["trades"] += 1
        s["volume"] += trade.usd_value
        if trade.action in ("HARVEST", "BOOST_SELL"):
            s["harvests"] += 1
        if trade.action in ("FOLD", "BOOST_FOLD"):
            s["folds"] += 1
            s["wins"] += 1
        if trade.action == "BOOST_SELL":
            s["boost_sells"] += 1
        if trade.action == "BOOST_FOLD":
            s["boost_folds"] += 1
        if trade.action == "WIRE":
            s["wires"] += 1
        if trade.portfolio_value > s["peak"]:
            s["peak"] = trade.portfolio_value
        if s["peak"] > 0:
            dd = (s["peak"] - trade.portfolio_value) / s["peak"] * 100
            if dd > s["max_dd"]:
                s["max_dd"] = dd
        return ch

    def verify(self) -> tuple[bool, int]:
        """Recomputes the chain from GENESIS via TradeRecord.record_hash and
        _chain_link, and confirms it against each entry's stored chain_hash."""
        if not self._path.exists():
            return True, 0
        n = 0
        last_hash = "GENESIS"
        with open(self._path) as f:
            for line in f:
                r = json.loads(line.strip())
                stored = r.get("chain_hash")
                fields = {k: v for k, v in r.items() if k not in ("chain_hash", "seq")}
                trade = TradeRecord(**fields)
                expected = self._chain_link(last_hash, trade.record_hash)
                if expected != stored:
                    return False, n
                last_hash = expected
                n += 1
        return True, n

    @property
    def stats(self):
        return dict(self._s)

    @property
    def chain_hash(self):
        return self._last_hash

    @property
    def record_count(self):
        return self._seq


class ReportGenerator:
    def __init__(self, reports_dir="reports"):
        self._dir = Path(reports_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._prev = self._find_last()

    def _find_last(self):
        rr = sorted(self._dir.glob("acervator_report_*.json"))
        if not rr:
            return "GENESIS"
        try:
            with open(rr[-1]) as f:
                return json.load(f).get("report_hash", "GENESIS")
        except Exception:
            return "GENESIS"  # matches TradeJournal's own default chain-start value

    def generate(
        self,
        journal,
        portfolio=0.0,
        passive=0.0,
        starting=0.0,
        exchange="",
        bots=None,
        env="live",
    ):
        # Builds the report dict; ReportGenerator.save writes it as JSON, not PDF.
        from src import __version__

        now = datetime.now(timezone.utc)
        s = journal.stats
        adv = portfolio - passive
        return {
            "schema": REPORT_SCHEMA,
            "report_id": f"ACR-{now.strftime('%Y%m%d-%H%M%S')}",
            "generated": now.isoformat(),
            "platform": "Acervator",
            "version": __version__,
            "strategy": "Accumulation Trading",
            "environment": env,
            "exchange": exchange,
            "operator": "Ekthelius the Accumulator",
            "copyright": "Copyright (c) 2025 Anthony L. Brown. All rights reserved.",
            "portfolio": {
                "starting": starting,
                "current": portfolio,
                "passive": passive,
                "advantage": round(adv, 2),
                "advantage_pct": round(adv / passive * 100 if passive else 0, 2),
                "max_dd": round(s["max_dd"], 2),
            },
            "activity": {
                k: s[k]
                for k in [
                    "trades",
                    "harvests",
                    "folds",
                    "boost_sells",
                    "boost_folds",
                    "wires",
                    "wins",
                    "volume",
                ]
            },
            "integrity": {
                "journal_records": journal.record_count,
                "journal_hash": journal.chain_hash,
                "previous_report": self._prev,
            },
            "system": {"python": platform.python_version(), "os": platform.system()},
        }

    def save(self, report):
        canonical = json.dumps(
            {k: v for k, v in report.items() if k != "report_hash"},
            sort_keys=True,
            default=str,
        )
        report["report_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        rid = report["report_id"]
        p = self._dir / f"acervator_report_{rid}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        self._prev = report["report_hash"]
        logger.info("Report saved: %s", p)
        return p


class LiveMonitor:
    """
    Claude API Feedback Loop with handshake authentication.

    On first connection, a HANDSHAKE exchange verifies both sides:
      Platform → sends HANDSHAKE message (system prompt contains shared phrases)
      Claude   → responds with confirmation phrase (proves it read the right prompt)
      Platform → verifies confirmation matches expected value

    Subsequent calls include the rolling journal chain hash,
    which only the real platform with the real trade history can produce.
    """

    PROMPT_TEMPLATE = (
        "You are the AI monitor for Acervator, an Accumulation Trading Platform.\n"
        "IDENTITY: This connection is authenticated. Operator: Ekthelius the Accumulator.\n"
        'CONNECTION PHRASE: "{connect_phrase}"\n'
        'CONFIRMATION PHRASE: "{confirm_phrase}"\n'
        'JOURNAL HASH: "{hash_prefix}"\n\n'
        "RULES:\n"
        '- If user message is exactly "HANDSHAKE", respond with ONLY the confirmation '
        "phrase on a single line. Nothing else.\n"
        "- For all other messages: review LIVE trading data.\n"
        "  1. Assess health, flag anomalies, suggest actions\n"
        "  2. Rate confidence 1-10\n"
        "  3. Compare against the 75/75 simulation baseline\n"
        "  4. End every response with: [HASH:{hash_prefix}] to prove authentication\n"
        "Be direct. The operator values honest analysis."
    )

    DEFAULT_CONNECT = "acervator-heapbuilder-live"
    DEFAULT_CONFIRM = "the-heap-grows-by-accumulation"

    def __init__(
        self,
        api_key="",
        journal=None,
        interval_hours=4.0,
        connect_phrase="",
        confirm_phrase="",
    ):
        self._key = api_key
        self._journal = journal or TradeJournal()
        self._interval = interval_hours
        self._last = 0.0
        self._history = []
        self._enabled = bool(api_key)
        self._authenticated = False
        self._connect = connect_phrase or self.DEFAULT_CONNECT
        self._confirm = confirm_phrase or self.DEFAULT_CONFIRM

    @property
    def enabled(self):
        return self._enabled

    @property
    def authenticated(self):
        return self._authenticated

    @property
    def should_check(self):
        return (time.time() - self._last) >= self._interval * 3600

    def _prompt(self):
        return self.PROMPT_TEMPLATE.format(
            connect_phrase=self._connect,
            confirm_phrase=self._confirm,
            hash_prefix=self._journal.chain_hash[:12],
        )

    async def _call(self, msg):
        import httpx

        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1500,
                    "system": self._prompt(),
                    "messages": [{"role": "user", "content": msg}],
                },
                timeout=30,
            )
            return r.json().get("content", [{}])[0].get("text", "")

    async def handshake(self) -> dict:
        """Authenticate the connection with a shared phrase exchange."""
        if not self._enabled:
            return {"authenticated": False, "message": "No API key"}
        try:
            resp = (await self._call("HANDSHAKE")).strip()
            if resp == self._confirm:
                self._authenticated = True
                logger.info("LiveMonitor: HANDSHAKE OK — authenticated")
                return {
                    "authenticated": True,
                    "phrase": resp,
                    "hash": self._journal.chain_hash[:12],
                }
            else:
                logger.warning("LiveMonitor: HANDSHAKE FAILED — got '%s'", resp[:50])
                return {"authenticated": False, "received": resp[:80]}
        except Exception as e:  # caught broadly; the error is returned, not raised
            return {"authenticated": False, "message": str(e)}

    async def analyze(self, portfolio=0.0, passive=0.0, bots=0) -> dict:
        """Send performance snapshot. Auto-handshakes if needed."""
        if not self._enabled:
            return {"status": "disabled"}
        if not self._authenticated:
            hs = await self.handshake()
            if not hs.get("authenticated"):
                return {"status": "auth_failed", **hs}
        s = self._journal.stats
        # passive may arrive as None; the line then reads "unavailable", not $0.00.
        if passive is None:
            pv_line = (
                f"Portfolio: ${portfolio:,.2f} | Passive: unavailable "
                f"| Adv: not computed"
            )
        else:
            adv = portfolio - passive
            pv_line = (
                f"Portfolio: ${portfolio:,.2f} | "
                f"Passive: ${passive:,.2f} | Adv: ${adv:+,.2f}"
            )
        msg = (
            f"LIVE ANALYSIS — Connection: {self._connect}\n"
            f"Hash: {self._journal.chain_hash[:16]} | Records: {self._journal.record_count}\n\n"
            f"{pv_line}\n"
            f"Trades: {s['trades']} H:{s['harvests']} F:{s['folds']} "
            f"BS:{s['boost_sells']} BF:{s['boost_folds']} W:{s['wires']}\n"
            f"Volume: ${s['volume']:,.2f} | DD: {s['max_dd']:.1f}% | Bots: {bots}"
        )
        try:
            text = await self._call(msg)
            fb = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "feedback": text,
                "hash": self._journal.chain_hash,
                "authenticated": True,
            }
            self._history.append(fb)
            self._last = time.time()
            return fb
        except Exception as e:  # caught broadly; the error is returned, not raised
            return {"status": "error", "message": str(e)}

    @property
    def feedback_history(self):
        return self._history

    @property
    def connection_info(self) -> dict:
        return {
            "enabled": self._enabled,
            "authenticated": self._authenticated,
            "connect_phrase": self._connect,
            "hash": self._journal.chain_hash[:12],
            "checks": len(self._history),
        }
