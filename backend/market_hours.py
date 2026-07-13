"""
Market-hours gating and scan-time scheduling.

- NYSE (US Equities): Mon–Fri 09:30–16:00 Eastern.
- Crypto: 24/7, always open.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def is_market_open(market: str) -> bool:
    """Return ``True`` if *market* is currently within trading hours."""
    if market == "CRYPTO":
        return True

    if market == "US_EQUITIES":
        now_et = datetime.now(tz=_ET)
        weekday = now_et.weekday()  # 0=Mon … 6=Sun
        if weekday >= 5:
            logger.debug("NYSE closed — weekend (weekday=%d).", weekday)
            return False
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        is_open = market_open <= now_et <= market_close
        if not is_open:
            logger.debug("NYSE closed — outside 09:30–16:00 ET (now=%s).", now_et.strftime("%H:%M"))
        return is_open

    logger.warning("Unknown market %r — treating as closed.", market)
    return False


def get_next_scan_time() -> datetime:
    """Calculate the next ``HH:01:00`` wall-clock time in UTC.

    The scanner fires 1 minute after each hourly candle close.
    If the current time is already past ``HH:01``, the next target is
    the following hour's ``HH:01``.
    """
    now = datetime.now(tz=timezone.utc)
    candidate = now.replace(minute=1, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(hours=1)
    return candidate


def seconds_until(target: datetime) -> float:
    """Seconds from *now* until *target* (clamped to >= 0)."""
    delta = (target - datetime.now(tz=timezone.utc)).total_seconds()
    return max(delta, 0.0)
