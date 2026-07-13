"""
Data models for the breakout scanner system.
All domain objects are immutable dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceLevel:
    """A horizontal support or resistance level detected from daily data."""

    price: float
    level_type: str  # 'support' or 'resistance'
    touch_count: int
    first_seen: datetime
    last_tested: datetime


@dataclass
class BreakoutSignal:
    """A confirmed breakout event with full trade parameters."""

    ticker: str
    market: str  # 'US_EQUITIES' or 'CRYPTO'
    direction: str  # 'LONG' or 'SHORT'
    broken_level: float
    entry_price: float
    stop_loss: float
    take_profit: float
    volume_ratio: float
    atr_value: float
    timestamp: datetime


@dataclass
class OpenPosition:
    """A position that has been entered but not yet closed."""

    ticker: str
    market: str  # 'US_EQUITIES' or 'CRYPTO'
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    stop_loss: float
    take_profit: float
    broken_level: float
    entry_time: datetime
    current_price: float = 0.0


@dataclass
class ClosedTrade:
    """A completed trade with realised PnL."""

    ticker: str
    market: str  # 'US_EQUITIES' or 'CRYPTO'
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    broken_level: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
