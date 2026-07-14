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
) -> Optional[Tuple[PriceLevel, str]]:
    """Check the last completed 1H candle for a valid body-close breakout.

    Parameters
    ----------
    hourly_df : pd.DataFrame
        OHLCV data on the 1-hour timeframe (at least 2 rows).
    levels : list[PriceLevel]
        Validated daily key levels.
    current_price : float
        Most recent market price (used for context only).

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

    for level in levels:
        price = level.price

        # ---- Crossing from below to above → LONG breakout ----
        if candle_open < price and candle_close > price:
            level.level_type = "resistance"  # Update type contextually
            logger.info(
                "LONG breakout confirmed — body closed above level "
                "%.4f (open=%.4f, close=%.4f).",
                price,
                candle_open,
                candle_close,
            )
            return level, "LONG"

        # ---- Crossing from above to below → SHORT breakdown ----
        elif candle_open > price and candle_close < price:
            level.level_type = "support"  # Update type contextually
            logger.info(
                "SHORT breakout confirmed — body closed below level "
                "%.4f (open=%.4f, close=%.4f).",
                price,
                candle_open,
                candle_close,
            )
            return level, "SHORT"

    return None
