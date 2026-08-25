"""
market_hours.py — Stock market hours awareness.

Tracks NYSE/NASDAQ trading sessions, pre-market, after-hours,
and US market holidays. Provides schedule-aware bot control.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, date, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.stocks.hours")


class MarketSession(Enum):
    PRE_MARKET = "pre_market"  # 4:00 AM - 9:30 AM ET
    REGULAR = "regular"  # 9:30 AM - 4:00 PM ET
    AFTER_HOURS = "after_hours"  # 4:00 PM - 8:00 PM ET
    CLOSED = "closed"  # 8:00 PM - 4:00 AM ET
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


# US market holidays (approximate — some shift for weekends)
US_MARKET_HOLIDAYS_2025_2026 = {
    # 2025
    date(2025, 1, 1): "New Year's Day",
    date(2025, 1, 20): "MLK Day",
    date(2025, 2, 17): "Presidents' Day",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 26): "Memorial Day",
    date(2025, 6, 19): "Juneteenth",
    date(2025, 7, 4): "Independence Day",
    date(2025, 9, 1): "Labor Day",
    date(2025, 11, 27): "Thanksgiving",
    date(2025, 12, 25): "Christmas",
    # 2026
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 19): "MLK Day",
    date(2026, 2, 16): "Presidents' Day",
    date(2026, 4, 3): "Good Friday",
    date(2026, 5, 25): "Memorial Day",
    date(2026, 6, 19): "Juneteenth",
    date(2026, 7, 3): "Independence Day (observed)",
    date(2026, 9, 7): "Labor Day",
    date(2026, 11, 26): "Thanksgiving",
    date(2026, 12, 25): "Christmas",
}

# Session times in ET (Eastern Time)
PRE_MARKET_OPEN = dt_time(4, 0)
REGULAR_OPEN = dt_time(9, 30)
REGULAR_CLOSE = dt_time(16, 0)
AFTER_HOURS_CLOSE = dt_time(20, 0)


class MarketHours:
    """
    Market hours tracker for US equity markets.
    All times in Eastern Time (ET).
    """

    def __init__(self):
        self._tz_offset_hours = self._detect_et_offset()

    def get_session(self, dt: datetime = None) -> MarketSession:
        """Get current market session."""
        if dt is None:
            dt = datetime.now()
        # Convert to ET approximation
        et = self._to_eastern(dt)

        # Check weekend
        if et.weekday() >= 5:  # Saturday or Sunday
            return MarketSession.WEEKEND

        # Check holidays
        if et.date() in US_MARKET_HOLIDAYS_2025_2026:
            return MarketSession.HOLIDAY

        t = et.time()
        if t < PRE_MARKET_OPEN:
            return MarketSession.CLOSED
        elif t < REGULAR_OPEN:
            return MarketSession.PRE_MARKET
        elif t < REGULAR_CLOSE:
            return MarketSession.REGULAR
        elif t < AFTER_HOURS_CLOSE:
            return MarketSession.AFTER_HOURS
        else:
            return MarketSession.CLOSED

    def is_market_open(self, dt: datetime = None) -> bool:
        """Check if regular market is currently open."""
        return self.get_session(dt) == MarketSession.REGULAR

    def is_trading_allowed(
        self, allow_extended: bool = False, dt: datetime = None
    ) -> bool:
        """Check if any trading is allowed right now."""
        session = self.get_session(dt)
        if session == MarketSession.REGULAR:
            return True
        if allow_extended and session in (
            MarketSession.PRE_MARKET,
            MarketSession.AFTER_HOURS,
        ):
            return True
        return False

    def next_open(self, dt: datetime = None) -> datetime:
        """Get next regular market open time."""
        if dt is None:
            dt = datetime.now()
        et = self._to_eastern(dt)

        # If market is currently open or not yet open today
        if et.weekday() < 5:  # Weekday
            today_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
            if et < today_open and et.date() not in US_MARKET_HOLIDAYS_2025_2026:
                return today_open

        # Find next trading day
        check = et.date() + timedelta(days=1)
        for _ in range(10):  # Max 10 days ahead
            if check.weekday() < 5 and check not in US_MARKET_HOLIDAYS_2025_2026:
                return datetime.combine(check, REGULAR_OPEN)
            check += timedelta(days=1)

        return datetime.combine(check, REGULAR_OPEN)

    def next_close(self, dt: datetime = None) -> datetime:
        """Get next regular market close time."""
        if dt is None:
            dt = datetime.now()
        et = self._to_eastern(dt)

        if et.weekday() < 5 and et.date() not in US_MARKET_HOLIDAYS_2025_2026:
            today_close = et.replace(hour=16, minute=0, second=0, microsecond=0)
            if et < today_close:
                return today_close

        # Next trading day close
        nxt = self.next_open(dt)
        return nxt.replace(hour=16, minute=0)

    def time_to_open(self, dt: datetime = None) -> Optional[timedelta]:
        """Time remaining until market opens. None if already open."""
        if self.is_market_open(dt):
            return None
        if dt is None:
            dt = datetime.now()
        nxt = self.next_open(dt)
        return nxt - self._to_eastern(dt)

    def time_to_close(self, dt: datetime = None) -> Optional[timedelta]:
        """Time remaining until market closes. None if already closed."""
        if not self.is_market_open(dt):
            return None
        if dt is None:
            dt = datetime.now()
        et = self._to_eastern(dt)
        close = et.replace(hour=16, minute=0, second=0)
        return close - et

    def get_status_string(self, dt: datetime = None) -> str:
        """Get human-readable market status."""
        session = self.get_session(dt)
        names = {
            MarketSession.PRE_MARKET: "Pre-Market (4:00-9:30 ET)",
            MarketSession.REGULAR: "Market Open (9:30-4:00 ET)",
            MarketSession.AFTER_HOURS: "After Hours (4:00-8:00 ET)",
            MarketSession.CLOSED: "Market Closed",
            MarketSession.WEEKEND: "Weekend — Market Closed",
            MarketSession.HOLIDAY: f"Holiday — {US_MARKET_HOLIDAYS_2025_2026.get(self._to_eastern(dt or datetime.now()).date(), 'Market Closed')}",
        }
        status = names.get(session, "Unknown")

        if session in (
            MarketSession.CLOSED,
            MarketSession.WEEKEND,
            MarketSession.HOLIDAY,
        ):
            ttopen = self.time_to_open(dt)
            if ttopen:
                hours = ttopen.total_seconds() / 3600
                if hours < 1:
                    status += f" — Opens in {ttopen.total_seconds() / 60:.0f}m"
                else:
                    status += f" — Opens in {hours:.1f}h"
        elif session == MarketSession.REGULAR:
            ttclose = self.time_to_close(dt)
            if ttclose:
                hours = ttclose.total_seconds() / 3600
                status += f" — Closes in {hours:.1f}h"

        return status

    def _to_eastern(self, dt: datetime) -> datetime:
        """Approximate conversion to Eastern Time."""
        return dt - timedelta(hours=self._tz_offset_hours)

    def _detect_et_offset(self) -> float:
        """Detect offset from local time to ET."""
        import time as _time

        # UTC offset of local time
        local_offset = (
            -(_time.timezone if _time.daylight == 0 else _time.altzone) / 3600
        )
        # ET is UTC-5 (EST) or UTC-4 (EDT)
        # Approximate: use -5 as default
        et_offset = -5
        return local_offset - et_offset
