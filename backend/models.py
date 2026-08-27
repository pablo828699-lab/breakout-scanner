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
class RadarSignal:
    """A trend-radar hit — an asset that just completed a directional move.

    This is a *detection* signal (a candidate to analyze), not a full trade:
    no stop-loss / take-profit. The manual analysis happens downstream.
    """

    ticker: str
    market: str  # 'US_EQUITIES' or 'CRYPTO'
    direction: str  # 'UP' or 'DOWN'
    price: float
    triggers: list  # e.g. ['DONCHIAN_20', 'IMPULSE']
    adx: float
    ema_stack: bool  # True when EMAs are aligned with the direction
    volume_ratio: float
    roc_pct: float  # momentum: % change over the lookback window
    donchian_n: int
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


@dataclass
class AsymmetricSignal:
    """Asymmetric buy opportunity detected after a capitulation/shock event.

    Combines SMC price structure, volume profile, and fundamental solvency
    analysis into a single actionable signal with R:R >= 1:3.
    """

    ticker: str
    market: str           # 'US_EQUITIES' or 'CRYPTO'
    verdict: str          # 'APTO_COMPRA_ASIMETRICA' or 'EVITAR'
    drop_pct: float       # Session drop % that triggered the analysis
    entry_price: float
    stop_loss: float
    take_profit: float
    rr_ratio: float
    position_size_qty: float
    poc: float            # Volume Profile Point of Control
    vah: float            # Value Area High
    val: float            # Value Area Low
    fvg_zone: tuple       # (low, high) of the most relevant FVG
    ob_zone: tuple        # (low, high) of the most relevant Order Block
    msb_type: str         # 'bullish_reversal', 'bearish_continuation', etc.
    is_idiosyncratic: bool
    fundamental_ok: bool
    confidence_score: float  # 0.0 - 1.0
    timestamp: datetime
    asset_class: str = "ACCIONES"  # 'ACCIONES', 'MATERIAS_PRIMAS', 'INDICES', 'FOREX', 'CRIPTO'


@dataclass
class MomentumSignal:
    """Explosive trend acceleration opportunity detected by the Momentum engine.

    Combines TTM Squeeze, Relative Volume (RVOL), Rate of Change (ROC),
    and fast EMA Ribbon alignment into an asymmetric trend-following signal.
    """

    ticker: str
    market: str                     # 'US_EQUITIES' or 'CRYPTO'
    direction: str                  # 'LONG' or 'SHORT'
    trigger: str                    # 'SQUEEZE_BREAKOUT', 'IMPULSE_MOMENTUM', 'EMA_EXPANSION'
    entry_price: float
    stop_loss: float
    take_profit: float
    rr_ratio: float
    rvol: float                     # Volume vs 20-day SMA
    roc_10: float                   # % change over 10 days
    rsi: float                      # 14-period RSI
    squeeze_status: str             # 'FIRED_BULLISH', 'FIRED_BEARISH', 'SQUEEZE_ON'
    ema_stack: bool                 # True if EMA 9 > 21 > 50 (or vice versa for SHORT)
    confidence_score: float         # 0.0 - 1.0
    analysis_summary: str
    timestamp: datetime
    asset_class: str = "ACCIONES"

