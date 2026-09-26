"""
market_hours.py — Stock market hours awareness.

Tracks NYSE/NASDAQ trading sessions, pre-market, after-hours,
and US market holidays. Provides schedule-aware bot control.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, date, timedelta, timezone
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

#: Eastern Time's two offsets from UTC, standard and daylight.
ET_STANDARD_OFFSET_HOURS = -5
ET_DAYLIGHT_OFFSET_HOURS = -4

#: US daylight time runs from the second Sunday in March at 07:00 UTC to the
#: first Sunday in November at 06:00 UTC, unchanged since 2007.
DST_START_MONTH = 3
DST_START_SUNDAY = 2
DST_START_UTC_HOUR = 7
DST_END_MONTH = 11
DST_END_SUNDAY = 1
DST_END_UTC_HOUR = 6


def nth_sunday(year: int, month: int, nth: int) -> date:
    """The ``nth`` Sunday of ``month`` in ``year``."""
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))


def et_offset_hours(utc: datetime) -> int:
    """Eastern Time's offset from UTC at naive ``utc``, by the US daylight time
    rule the two DST constants state."""
    start = datetime.combine(
        nth_sunday(utc.year, DST_START_MONTH, DST_START_SUNDAY),
        dt_time(DST_START_UTC_HOUR),
    )
    end = datetime.combine(
        nth_sunday(utc.year, DST_END_MONTH, DST_END_SUNDAY),
        dt_time(DST_END_UTC_HOUR),
    )
    if start <= utc < end:
        return ET_DAYLIGHT_OFFSET_HOURS
    return ET_STANDARD_OFFSET_HOURS


def eastern_at(moment_s: float) -> datetime:
    """``moment_s``, epoch seconds, as a naive Eastern Time datetime; no local
    timezone is read."""
    utc = datetime.fromtimestamp(float(moment_s), tz=timezone.utc).replace(tzinfo=None)
    return utc + timedelta(hours=et_offset_hours(utc))


def session_of(et: datetime) -> MarketSession:
    """The ``MarketSession`` Eastern Time ``et`` falls in."""
    if et.weekday() >= 5:  # Saturday or Sunday
        return MarketSession.WEEKEND
    if et.date() in US_MARKET_HOLIDAYS_2025_2026:
        return MarketSession.HOLIDAY
    t = et.time()
    if t < PRE_MARKET_OPEN:
        return MarketSession.CLOSED
    if t < REGULAR_OPEN:
        return MarketSession.PRE_MARKET
    if t < REGULAR_CLOSE:
        return MarketSession.REGULAR
    if t < AFTER_HOURS_CLOSE:
        return MarketSession.AFTER_HOURS
    return MarketSession.CLOSED


def session_at(moment_s: float) -> MarketSession:
    """The ``MarketSession`` US equity venues are in at ``moment_s``, epoch
    seconds."""
    return session_of(eastern_at(moment_s))


def accepts_order(moment_s: float) -> bool:
    """True when US equity venues take an order at ``moment_s``: the regular
    session only, with pre-market and after-hours excluded."""
    return session_at(moment_s) == MarketSession.REGULAR


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
        # Check holidays
        return session_of(et)

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
