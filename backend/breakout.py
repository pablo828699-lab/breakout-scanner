"""
Breakout confirmation on the 1-hour timeframe.

Only the candle *body* (Open → Close) is considered.
Wicks / spikes are strictly ignored.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import pandas as pd

from backend.models import PriceLevel

logger = logging.getLogger(__name__)


def confirm_breakout(
    hourly_df: pd.DataFrame,
    levels: List[PriceLevel],
    current_price: float,
    atr_value: float,
    penetration_atr_mult: float = 0.15,
) -> Optional[Tuple[PriceLevel, str]]:
    """Check the last completed 1H candle for a valid body-close breakout.

    A break only counts if the candle *body* closes beyond the level by at
    least ``penetration_atr_mult`` × ATR. This margin filters marginal pokes
    and stop-runs that close a hair past the level and reverse.

    Parameters
    ----------
    hourly_df : pd.DataFrame
        OHLCV data on the 1-hour timeframe (at least 2 rows).
    levels : list[PriceLevel]
        Validated daily key levels.
    current_price : float
        Most recent market price (used for context only).
    atr_value : float
        Pre-computed ATR on the 1H timeframe (sets the penetration margin).
    penetration_atr_mult : float
        Required close-beyond-level distance, as a fraction of ATR.

    Returns
    -------
    Optional[Tuple[PriceLevel, str]]
        ``(broken_level, 'LONG' | 'SHORT')`` if a valid breakout is
        confirmed, otherwise ``None``.
    """
    if hourly_df.empty or len(hourly_df) < 2:
        logger.warning("Insufficient hourly data for breakout confirmation.")
        return None

    # Use the second-to-last row as the last *completed* candle to be safe.
    # If the data provider already excludes the currently forming candle,
    # index -1 is correct, but -2 is the conservative choice.
    last_candle = hourly_df.iloc[-2]
    candle_open = float(last_candle["Open"])
    candle_close = float(last_candle["Close"])

    margin = atr_value * penetration_atr_mult

    for level in levels:
        price = level.price

        # ---- Crossing from below to above → LONG breakout ----
        # Body must open at/below the level and close clear of it by `margin`.
        if candle_open < price and candle_close > price + margin:
            level.level_type = "support"  # broken resistance now acts as support
            logger.info(
                "LONG breakout confirmed — body closed %.4f above level "
                "%.4f (open=%.4f, margin=%.4f).",
                candle_close - price,
                price,
                candle_open,
                margin,
            )
            return level, "LONG"

        # ---- Crossing from above to below → SHORT breakdown ----
        elif candle_open > price and candle_close < price - margin:
            level.level_type = "resistance"  # broken support now acts as resistance
            logger.info(
                "SHORT breakout confirmed — body closed %.4f below level "
                "%.4f (open=%.4f, margin=%.4f).",
                price - candle_close,
                price,
                candle_open,
                margin,
            )
            return level, "SHORT"

    return None
