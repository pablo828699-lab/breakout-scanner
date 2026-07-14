"""
Risk management — structural Stop-Loss anchored to the breakout candle,
with an ATR buffer and distance guards, plus fixed R:R Take-Profit.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_atr(hourly_df: pd.DataFrame, period: int = 14) -> float:
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
    breakout_candle_low: float,
    breakout_candle_high: float,
    direction: str,
    atr_value: float,
    buffer_atr_mult: float = 0.10,
    min_stop_atr_mult: float = 0.5,
    rr_ratio: float = 2.0,
) -> Tuple[float, float, float]:
    """Calculate a structural Stop-Loss, Take-Profit, and risk for a trade.

    The stop is placed just beyond the *breakout candle's* extreme (its low for
    a LONG, its high for a SHORT) plus a small ATR buffer — i.e. at the level
    where the breakout would be invalidated, not at an arbitrary distance from
    entry. A minimum-distance floor (``min_stop_atr_mult`` × ATR) prevents a
    sub-noise stop when the breakout candle is tiny.

    Parameters
    ----------
    entry_price : float
        The intended entry price (current/live price at signal time).
    breakout_candle_low, breakout_candle_high : float
        Low/High of the confirmed 1H breakout candle (the invalidation anchor).
    direction : str
        ``'LONG'`` or ``'SHORT'``.
    atr_value : float
        Pre-computed ATR on the 1H timeframe.
    buffer_atr_mult : float
        Extra margin beyond the candle extreme, as a fraction of ATR.
    min_stop_atr_mult : float
        Minimum stop distance from entry, as a fraction of ATR.
    rr_ratio : float
        Reward-to-risk ratio for the take-profit target.

    Returns
    -------
    (stop_loss, take_profit, risk)
        ``risk`` is the per-unit distance between entry and stop.
    """
    buffer = atr_value * buffer_atr_mult
    min_distance = atr_value * min_stop_atr_mult

    if direction == "LONG":
        structural_stop = breakout_candle_low - buffer
        # Floor the distance: take whichever stop sits further below entry.
        stop_loss = min(structural_stop, entry_price - min_distance)
        risk = entry_price - stop_loss
        take_profit = entry_price + (risk * rr_ratio)
    elif direction == "SHORT":
        structural_stop = breakout_candle_high + buffer
        # Floor the distance: take whichever stop sits further above entry.
        stop_loss = max(structural_stop, entry_price + min_distance)
        risk = stop_loss - entry_price
        take_profit = entry_price - (risk * rr_ratio)
    else:
        raise ValueError(f"Invalid direction: {direction!r}")

    logger.info(
        "Risk levels [%s]: entry=%.4f, SL=%.4f, TP=%.4f, ATR=%.4f, risk=%.4f (%.2f×ATR)",
        direction,
        entry_price,
        stop_loss,
        take_profit,
        atr_value,
        risk,
        risk / atr_value if atr_value else 0.0,
    )
    return round(stop_loss, 6), round(take_profit, 6), round(risk, 6)
