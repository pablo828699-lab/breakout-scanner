"""
Volume filter — ensures the breakout candle carries institutional-grade volume.

A candle passes the filter when its volume is >= VOLUME_MULTIPLIER × SMA(volume, VOLUME_SMA_PERIOD).
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def passes_volume_filter(
    hourly_df: pd.DataFrame,
    multiplier: float = 1.5,
    sma_period: int = 20,
) -> Tuple[bool, float]:
    """Check whether the last completed 1H candle has sufficient volume.

    Parameters
    ----------
    hourly_df : pd.DataFrame
        1-hour OHLCV data with a ``Volume`` column (at least ``sma_period + 2`` rows).
    multiplier : float
        Minimum ratio of candle volume to the SMA of prior volumes.
    sma_period : int
        Lookback window for the volume simple moving average.

    Returns
    -------
    (passes, volume_ratio)
        ``passes`` is ``True`` when volume_ratio >= multiplier.
    """
    required_rows = sma_period + 2  # need sma_period PRIOR + the candle itself
    if hourly_df.empty or len(hourly_df) < required_rows:
        logger.warning(
            "Insufficient hourly data for volume filter (%d rows, need %d).",
            len(hourly_df),
            required_rows,
        )
        return False, 0.0

    volumes = hourly_df["Volume"].values.astype(float)

    # Last completed candle is at index -2 (conservative; -1 may still be forming)
    candle_volume = volumes[-2]

    # SMA of the *sma_period* candles BEFORE the breakout candle
    prior_volumes = volumes[-(sma_period + 2) : -2]
    sma_volume = float(np.mean(prior_volumes))

    if sma_volume <= 0:
        logger.warning("SMA volume is zero or negative — cannot evaluate filter.")
        return False, 0.0

    volume_ratio = candle_volume / sma_volume
    passes = volume_ratio >= multiplier

    logger.info(
        "Volume filter: candle_vol=%.0f, SMA(%d)=%.0f, ratio=%.2fx — %s",
        candle_volume,
        sma_period,
        sma_volume,
        volume_ratio,
        "PASS" if passes else "FAIL",
    )
    return passes, round(volume_ratio, 2)
