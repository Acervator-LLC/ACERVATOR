"""
analytics_engine.py — Performance analytics for trading bots.

Computes equity curves, win rates, Sharpe ratio, profit factor,
average hold times, and per-bot/per-timeframe performance comparisons.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

logger = logging.getLogger("acervator.analytics")


@dataclass
class TradeRecord:
    """A single completed trade (round-trip: entry + exit)."""

    trade_id: str
    bot_id: str
    symbol: str
    side: str  # "scrum", "fold", "grid_buy", "grid_sell"
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    entry_time: float
    exit_time: float
    hold_seconds: float
    ta_direction: str = ""  # TA consensus at trade time
    ta_confidence: float = 0.0
    ta_timeframe: str = ""
    exchange_id: str = ""


@dataclass
class EquityPoint:
    """A single point on the equity curve."""

    timestamp: float
    equity: float  # Total portfolio value
    pnl_cumulative: float
    drawdown_pct: float
    bot_count: int


@dataclass
class BotPerformance:
    """Aggregated performance metrics for a single bot."""

    bot_id: str
    symbol: str
    mode: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_hold_seconds: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    expectancy: float = 0.0  # Avg $ per trade
    trades_per_day: float = 0.0


class AnalyticsEngine:
    """
    Central analytics engine that collects trade records and computes
    performance metrics across all bots.
    """

    def __init__(self):
        self._trades: list[TradeRecord] = []
        self._equity_curve: list[EquityPoint] = []
        self._max_trades = 50000
        self._max_equity_points = 17280  # 48 hours at 10-sec intervals

    def record_trade(self, trade: TradeRecord):

        # sadp: R28 R29 R33  # trade record: fail-loudly(R28) idempotent(R29) append-only(R33)
        """Add a completed trade to the analytics store."""
        self._trades.append(trade)
        if len(self._trades) > self._max_trades:
            self._trades = self._trades[-self._max_trades :]
        logger.debug(
            "Trade recorded: %s %s P/L=$%.4f", trade.symbol, trade.side, trade.pnl
        )

    def record_trade_from_dict(self, d: dict):

        # sadp: R28 R29 R33  # trade record: fail-loudly(R28) idempotent(R29) append-only(R33)
        """Record a trade from a dictionary (convenience method)."""
        trade = TradeRecord(
            trade_id=d.get("trade_id", f"t_{time.time():.0f}"),
            bot_id=d.get("bot_id", ""),
            symbol=d.get("symbol", ""),
            side=d.get("side", ""),
            entry_price=d.get("entry_price", 0),
            exit_price=d.get("exit_price", 0),
            quantity=d.get("quantity", 0),
            pnl=d.get("pnl", 0),
            pnl_pct=d.get("pnl_pct", 0),
            entry_time=d.get("entry_time", time.time()),
            exit_time=d.get("exit_time", time.time()),
            hold_seconds=d.get("hold_seconds", 0),
            ta_direction=d.get("ta_direction", ""),
            ta_confidence=d.get("ta_confidence", 0),
            ta_timeframe=d.get("ta_timeframe", ""),
            exchange_id=d.get("exchange_id", ""),
        )
        self.record_trade(trade)

    def snapshot_equity(self, bot_manager) -> EquityPoint:

        # sadp: R28 R33  # equity snapshot: fail-loudly(R28) append-only(R33)
        """Take an equity snapshot from current portfolio state."""
        agg = bot_manager.get_aggregate_stats()
        total_pnl = agg.get("total_realised_pnl", 0)
        agg.get("running", 0)

        # Estimate total equity as sum of target balances + P/L
        statuses = bot_manager.list_bots()
        total_equity = sum(s.get("target_balance", 0) for s in statuses) + total_pnl

        # Calculate drawdown from peak
        peak = max((ep.equity for ep in self._equity_curve), default=total_equity)
        if total_equity > peak:
            peak = total_equity
        dd = ((peak - total_equity) / peak * 100) if peak > 0 else 0

        point = EquityPoint(
            timestamp=time.time(),
            equity=total_equity,
            pnl_cumulative=total_pnl,
            drawdown_pct=dd,
            bot_count=len(statuses),
        )
        self._equity_curve.append(point)
        if len(self._equity_curve) > self._max_equity_points:
            self._equity_curve = self._equity_curve[-self._max_equity_points :]

        return point

    def get_equity_curve(self, hours: float = 24) -> list[dict]:
        """Return equity curve points for the last N hours."""
        cutoff = time.time() - (hours * 3600)
        return [
            {
                "timestamp": p.timestamp,
                "equity": p.equity,
                "pnl": p.pnl_cumulative,
                "drawdown": p.drawdown_pct,
                "bots": p.bot_count,
            }
            for p in self._equity_curve
            if p.timestamp >= cutoff
        ]

    def get_bot_performance(self, bot_id: str = "") -> list[BotPerformance]:
        """
        Compute performance metrics per bot.
        If bot_id is empty, returns metrics for ALL bots.
        """
        # Group trades by bot
        by_bot: dict[str, list[TradeRecord]] = {}
        for t in self._trades:
            if bot_id and t.bot_id != bot_id:
                continue
            by_bot.setdefault(t.bot_id, []).append(t)

        results = []
        for bid, trades in by_bot.items():
            perf = self._compute_performance(bid, trades)
            results.append(perf)

        return sorted(results, key=lambda p: p.total_pnl, reverse=True)

    def get_timeframe_comparison(self) -> dict:
        """Compare performance across different TA timeframes."""
        by_tf: dict[str, list[TradeRecord]] = {}
        for t in self._trades:
            tf = t.ta_timeframe or "unknown"
            by_tf.setdefault(tf, []).append(t)

        results = {}
        for tf, trades in by_tf.items():
            wins = [t for t in trades if t.pnl > 0]
            total_pnl = sum(t.pnl for t in trades)
            results[tf] = {
                "total_trades": len(trades),
                "win_rate": len(wins) / len(trades) * 100 if trades else 0,
                "total_pnl": total_pnl,
                "avg_pnl": total_pnl / len(trades) if trades else 0,
            }

        return results

    def get_portfolio_summary(self) -> dict:
        """Return overall portfolio performance summary."""
        if not self._trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "profit_factor": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "avg_hold_time": "0s",
                "expectancy": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "trades_today": 0,
            }

        wins = [t for t in self._trades if t.pnl > 0]
        losses = [t for t in self._trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in self._trades)
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))

        # Sharpe ratio (annualized, using daily returns)
        daily_returns = self._compute_daily_returns()
        sharpe = self._sharpe_ratio(daily_returns)

        # Max drawdown from equity curve
        max_dd = max((p.drawdown_pct for p in self._equity_curve), default=0)

        # Average hold time
        avg_hold = sum(t.hold_seconds for t in self._trades) / len(self._trades)

        # Trades today
        today_start = time.time() - 86400
        trades_today = sum(1 for t in self._trades if t.exit_time >= today_start)

        return {
            "total_trades": len(self._trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(self._trades) * 100 if self._trades else 0,
            "total_pnl": round(total_pnl, 4),
            "gross_profit": round(gross_profit, 4),
            "gross_loss": round(gross_loss, 4),
            "profit_factor": (
                round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")
            ),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2),
            "avg_hold_time": self._format_duration(avg_hold),
            "expectancy": (
                round(total_pnl / len(self._trades), 4) if self._trades else 0
            ),
            "best_trade": round(max(t.pnl for t in self._trades), 4),
            "worst_trade": round(min(t.pnl for t in self._trades), 4),
            "trades_today": trades_today,
            "unique_bots": len(set(t.bot_id for t in self._trades)),
            "unique_symbols": len(set(t.symbol for t in self._trades)),
        }

    def _compute_performance(
        self, bot_id: str, trades: list[TradeRecord]
    ) -> BotPerformance:
        """Compute detailed performance metrics for a set of trades."""
        if not trades:
            return BotPerformance(bot_id=bot_id, symbol="", mode="")

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        total_pnl = sum(t.pnl for t in trades)

        # Sharpe from trade P/L series
        pnl_series = [t.pnl for t in trades]
        sharpe = 0.0
        if len(pnl_series) >= 2:
            mean = sum(pnl_series) / len(pnl_series)
            var = sum((x - mean) ** 2 for x in pnl_series) / len(pnl_series)
            std = math.sqrt(var) if var > 0 else 1
            sharpe = (mean / std) * math.sqrt(252)  # Annualized

        # Max drawdown from cumulative P/L
        cum_pnl = 0.0
        peak_cum = 0.0
        max_dd = 0.0
        for t in trades:
            cum_pnl += t.pnl
            if cum_pnl > peak_cum:
                peak_cum = cum_pnl
            dd = ((peak_cum - cum_pnl) / peak_cum * 100) if peak_cum > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Trades per day
        if len(trades) >= 2:
            span = trades[-1].exit_time - trades[0].entry_time
            tpd = len(trades) / (span / 86400) if span > 0 else 0
        else:
            tpd = 0

        return BotPerformance(
            bot_id=bot_id,
            symbol=trades[0].symbol,
            mode=(
                trades[0].side.split("_")[0]
                if "_" in trades[0].side
                else trades[0].side
            ),
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            total_pnl=round(total_pnl, 4),
            gross_profit=round(gross_profit, 4),
            gross_loss=round(gross_loss, 4),
            max_win=round(max((t.pnl for t in wins), default=0), 4),
            max_loss=round(min((t.pnl for t in losses), default=0), 4),
            avg_win=round(gross_profit / len(wins), 4) if wins else 0,
            avg_loss=round(gross_loss / len(losses), 4) if losses else 0,
            avg_hold_seconds=sum(t.hold_seconds for t in trades) / len(trades),
            win_rate=round(len(wins) / len(trades) * 100, 1),
            profit_factor=(
                round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")
            ),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown_pct=round(max_dd, 2),
            expectancy=round(total_pnl / len(trades), 4),
            trades_per_day=round(tpd, 1),
        )

    def _compute_daily_returns(self) -> list[float]:
        """Compute daily P/L returns from equity curve."""
        if len(self._equity_curve) < 2:
            return []

        # Group equity points by day
        by_day: dict[int, list[EquityPoint]] = {}
        for p in self._equity_curve:
            day = int(p.timestamp // 86400)
            by_day.setdefault(day, []).append(p)

        days = sorted(by_day.keys())
        returns = []
        for i in range(1, len(days)):
            prev_equity = by_day[days[i - 1]][-1].equity
            curr_equity = by_day[days[i]][-1].equity
            if prev_equity > 0:
                ret = (curr_equity - prev_equity) / prev_equity
                returns.append(ret)

        return returns

    def _sharpe_ratio(self, returns: list[float], risk_free: float = 0.0) -> float:
        """Compute annualized Sharpe ratio from daily returns."""
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var) if var > 0 else 1e-9
        return ((mean - risk_free / 365) / std) * math.sqrt(365)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds into human-readable duration."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            return f"{seconds / 60:.1f}m"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def trades(self) -> list[TradeRecord]:
        return list(self._trades)
