"""
Market Hours Utility

Provides market hours awareness for all trading agents.
Handles regular hours, extended hours, and holidays.
"""

from datetime import datetime, time, date
from typing import Tuple, Optional
from enum import Enum
import pytz

# US Eastern timezone (where NYSE/NASDAQ operate)
ET = pytz.timezone('America/New_York')


class MarketSession(str, Enum):
    """Current market session type"""
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


# 2024-2025 US Market Holidays (NYSE/NASDAQ closed)
# Update this list annually
MARKET_HOLIDAYS = {
    # 2024
    date(2024, 1, 1),    # New Year's Day
    date(2024, 1, 15),   # MLK Day
    date(2024, 2, 19),   # Presidents Day
    date(2024, 3, 29),   # Good Friday
    date(2024, 5, 27),   # Memorial Day
    date(2024, 6, 19),   # Juneteenth
    date(2024, 7, 4),    # Independence Day
    date(2024, 9, 2),    # Labor Day
    date(2024, 11, 28),  # Thanksgiving
    date(2024, 12, 25),  # Christmas

    # 2025
    date(2025, 1, 1),    # New Year's Day
    date(2025, 1, 20),   # MLK Day
    date(2025, 2, 17),   # Presidents Day
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 26),   # Memorial Day
    date(2025, 6, 19),   # Juneteenth
    date(2025, 7, 4),    # Independence Day
    date(2025, 9, 1),    # Labor Day
    date(2025, 11, 27),  # Thanksgiving
    date(2025, 12, 25),  # Christmas
}

# Early close days (1:00 PM ET close)
EARLY_CLOSE_DAYS = {
    date(2024, 7, 3),    # Day before Independence Day
    date(2024, 11, 29),  # Day after Thanksgiving
    date(2024, 12, 24),  # Christmas Eve

    date(2025, 7, 3),    # Day before Independence Day
    date(2025, 11, 28),  # Day after Thanksgiving
    date(2025, 12, 24),  # Christmas Eve
}


class MarketHours:
    """
    Market hours checker for US equity markets.

    Sessions:
    - Pre-market: 4:00 AM - 9:30 AM ET
    - Regular: 9:30 AM - 4:00 PM ET (1:00 PM on early close days)
    - After-hours: 4:00 PM - 8:00 PM ET

    Options only trade during regular hours.
    """

    # Time boundaries (Eastern Time)
    PRE_MARKET_OPEN = time(4, 0)      # 4:00 AM ET
    REGULAR_OPEN = time(9, 30)         # 9:30 AM ET
    REGULAR_CLOSE = time(16, 0)        # 4:00 PM ET
    EARLY_CLOSE = time(13, 0)          # 1:00 PM ET
    AFTER_HOURS_CLOSE = time(20, 0)    # 8:00 PM ET

    @classmethod
    def now_et(cls) -> datetime:
        """Get current time in Eastern timezone"""
        return datetime.now(ET)

    @classmethod
    def is_holiday(cls, check_date: date = None) -> bool:
        """Check if given date is a market holiday"""
        if check_date is None:
            check_date = cls.now_et().date()
        return check_date in MARKET_HOLIDAYS

    @classmethod
    def is_early_close(cls, check_date: date = None) -> bool:
        """Check if given date is an early close day"""
        if check_date is None:
            check_date = cls.now_et().date()
        return check_date in EARLY_CLOSE_DAYS

    @classmethod
    def is_weekend(cls, check_date: date = None) -> bool:
        """Check if given date is a weekend"""
        if check_date is None:
            check_date = cls.now_et().date()
        return check_date.weekday() >= 5  # Saturday = 5, Sunday = 6

    @classmethod
    def get_session(cls, at_time: datetime = None) -> MarketSession:
        """
        Get the current market session.

        Returns the session type based on current time.
        """
        if at_time is None:
            at_time = cls.now_et()
        else:
            # Ensure we're working in ET
            if at_time.tzinfo is None:
                at_time = ET.localize(at_time)
            else:
                at_time = at_time.astimezone(ET)

        current_date = at_time.date()
        current_time = at_time.time()

        # Check weekend
        if cls.is_weekend(current_date):
            return MarketSession.WEEKEND

        # Check holiday
        if cls.is_holiday(current_date):
            return MarketSession.HOLIDAY

        # Determine close time
        close_time = cls.EARLY_CLOSE if cls.is_early_close(current_date) else cls.REGULAR_CLOSE

        # Check time-based session
        if current_time < cls.PRE_MARKET_OPEN:
            return MarketSession.CLOSED
        elif current_time < cls.REGULAR_OPEN:
            return MarketSession.PRE_MARKET
        elif current_time < close_time:
            return MarketSession.REGULAR
        elif current_time < cls.AFTER_HOURS_CLOSE:
            return MarketSession.AFTER_HOURS
        else:
            return MarketSession.CLOSED

    @classmethod
    def is_market_open(cls, include_extended: bool = False) -> bool:
        """
        Check if market is currently open for trading.

        Args:
            include_extended: If True, includes pre-market and after-hours

        Returns:
            True if market is open for trading
        """
        session = cls.get_session()

        if include_extended:
            return session in [
                MarketSession.PRE_MARKET,
                MarketSession.REGULAR,
                MarketSession.AFTER_HOURS
            ]
        else:
            return session == MarketSession.REGULAR

    @classmethod
    def is_options_trading_open(cls) -> bool:
        """
        Check if options trading is available.
        Options only trade during regular market hours.
        """
        return cls.get_session() == MarketSession.REGULAR

    @classmethod
    def can_trade_stocks(cls, allow_extended: bool = True) -> bool:
        """
        Check if stock trading is available.

        Args:
            allow_extended: If True, allows pre-market and after-hours trading
        """
        return cls.is_market_open(include_extended=allow_extended)

    @classmethod
    def time_until_open(cls) -> Optional[int]:
        """
        Get seconds until market opens (regular session).

        Returns:
            Seconds until open, or None if market is already open
        """
        now = cls.now_et()
        session = cls.get_session()

        if session == MarketSession.REGULAR:
            return None  # Already open

        # If it's a weekend or holiday, calculate to next trading day
        target_date = now.date()

        # Find next trading day
        while cls.is_weekend(target_date) or cls.is_holiday(target_date):
            target_date = date(target_date.year, target_date.month, target_date.day + 1)

        # If same day and before open
        if target_date == now.date() and now.time() < cls.REGULAR_OPEN:
            open_dt = ET.localize(datetime.combine(target_date, cls.REGULAR_OPEN))
            return int((open_dt - now).total_seconds())

        # Next trading day
        if target_date > now.date():
            open_dt = ET.localize(datetime.combine(target_date, cls.REGULAR_OPEN))
            return int((open_dt - now).total_seconds())

        # After close, calculate to next day
        next_day = date(now.year, now.month, now.day + 1)
        while cls.is_weekend(next_day) or cls.is_holiday(next_day):
            next_day = date(next_day.year, next_day.month, next_day.day + 1)

        open_dt = ET.localize(datetime.combine(next_day, cls.REGULAR_OPEN))
        return int((open_dt - now).total_seconds())

    @classmethod
    def time_until_close(cls) -> Optional[int]:
        """
        Get seconds until market closes (regular session).

        Returns:
            Seconds until close, or None if market is closed
        """
        now = cls.now_et()
        session = cls.get_session()

        if session != MarketSession.REGULAR:
            return None  # Not in regular session

        close_time = cls.EARLY_CLOSE if cls.is_early_close() else cls.REGULAR_CLOSE
        close_dt = ET.localize(datetime.combine(now.date(), close_time))

        return int((close_dt - now).total_seconds())

    @classmethod
    def get_status(cls) -> dict:
        """
        Get comprehensive market status.

        Returns dict with:
        - session: Current session type
        - is_open: Whether regular market is open
        - can_trade_stocks: Whether stock trading is possible
        - can_trade_options: Whether options trading is possible
        - time_until_open: Seconds until open (if closed)
        - time_until_close: Seconds until close (if open)
        - current_time_et: Current Eastern time
        """
        now = cls.now_et()
        session = cls.get_session()

        return {
            "session": session.value,
            "is_open": session == MarketSession.REGULAR,
            "can_trade_stocks": cls.can_trade_stocks(),
            "can_trade_options": cls.is_options_trading_open(),
            "time_until_open": cls.time_until_open(),
            "time_until_close": cls.time_until_close(),
            "current_time_et": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "is_holiday": cls.is_holiday(),
            "is_early_close": cls.is_early_close(),
        }


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration"""
    if seconds is None:
        return "N/A"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"
