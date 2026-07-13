"""
Risk management — ATR-based Stop-Loss and fixed R:R Take-Profit.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _calculate_atr(hourly_df: pd.DataFrame, period: int = 14) -> float:
    """Compute the Average True Range over the last *period* candles."""
    if len(hourly_df) < period + 1:
        logger.warning("Not enough data for ATR(%d); using fallback.", period)
        return float(hourly_df["High"].iloc[-1] - hourly_df["Low"].iloc[-1])

    highs = hourly_df["High"].values.astype(float)
    lows = hourly_df["Low"].values.astype(float)
    closes = hourly_df["Close"].values.astype(float)

    tr_values: list[float] = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_values.append(max(hl, hc, lc))

    atr = float(np.mean(tr_values[-period:]))
    return atr


def calculate_risk_levels(
    entry_price: float,
    broken_level: float,
    direction: str,
    hourly_df: pd.DataFrame,
    atr_period: int = 14,
    atr_sl_multiplier: float = 0.5,
    rr_ratio: float = 2.0,
) -> Tuple[float, float, float]:
    """Calculate Stop-Loss, Take-Profit, and ATR for a trade.

    Parameters
    ----------
    entry_price : float
        The intended entry price (typically the breakout candle's close).
    broken_level : float
        The daily key level that was broken.
    direction : str
        ``'LONG'`` or ``'SHORT'``.
    hourly_df : pd.DataFrame
        1-hour OHLCV data used to compute ATR.
    atr_period : int
        ATR lookback period (default 14).
    atr_sl_multiplier : float
        Fraction of ATR added as margin beyond the broken level for the SL.
    rr_ratio : float
        Reward-to-risk ratio for the take-profit target.

    Returns
    -------
    (stop_loss, take_profit, atr_value)
    """
    atr_value = _calculate_atr(hourly_df, atr_period)
    margin = atr_value * atr_sl_multiplier

    if direction == "LONG":
        stop_loss = broken_level - margin
        risk = abs(entry_price - stop_loss)
        take_profit = entry_price + (risk * rr_ratio)
    elif direction == "SHORT":
        stop_loss = broken_level + margin
        risk = abs(stop_loss - entry_price)
        take_profit = entry_price - (risk * rr_ratio)
    else:
        raise ValueError(f"Invalid direction: {direction!r}")

    logger.info(
        "Risk levels [%s]: SL=%.4f, TP=%.4f, ATR=%.4f, risk=%.4f, margin=%.4f",
        direction,
        stop_loss,
        take_profit,
        atr_value,
        risk,
        margin,
    )
    return round(stop_loss, 6), round(take_profit, 6), round(atr_value, 6)
