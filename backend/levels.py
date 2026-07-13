"""
Key level detection from daily OHLCV data.

Identifies horizontal support and resistance zones by clustering swing
pivots and counting how many times price has tested each level.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import numpy as np
import pandas as pd

from backend.models import PriceLevel

logger = logging.getLogger(__name__)


def _find_swing_highs(highs: np.ndarray, k: int = 3) -> np.ndarray:
    """Return indices of swing highs (local maxima in a window of 2k+1 candles)."""
    indices: list[int] = []
    for i in range(k, len(highs) - k):
        val = highs[i]
        if all(val >= highs[j] for j in range(i - k, i + k + 1) if j != i):
            indices.append(i)
    return np.array(indices, dtype=int)


def _find_swing_lows(lows: np.ndarray, k: int = 3) -> np.ndarray:
    """Return indices of swing lows (local minima in a window of 2k+1 candles)."""
    indices: list[int] = []
    for i in range(k, len(lows) - k):
        val = lows[i]
        if all(val <= lows[j] for j in range(i - k, i + k + 1) if j != i):
            indices.append(i)
    return np.array(indices, dtype=int)


def _cluster_prices(prices: np.ndarray, proximity_pct: float) -> List[List[float]]:
    """Group *sorted* prices that are within *proximity_pct* of each other."""
    if len(prices) == 0:
        return []
    sorted_prices = np.sort(prices)
    clusters: List[List[float]] = [[float(sorted_prices[0])]]
    for p in sorted_prices[1:]:
        cluster_mean = np.mean(clusters[-1])
        if abs(p - cluster_mean) / cluster_mean <= proximity_pct:
            clusters[-1].append(float(p))
        else:
            clusters.append([float(p)])
    return clusters


def _count_touches(
    daily_df: pd.DataFrame,
    level_price: float,
    proximity_pct: float,
) -> tuple[int, datetime, datetime]:
    """Count how many daily candles 'test' a level without breaking it.

    Returns (touch_count, first_seen, last_tested).
    """
    highs = daily_df["High"].values
    lows = daily_df["Low"].values
    closes = daily_df["Close"].values
    dates = daily_df.index

    touch_count = 0
    first_seen: datetime | None = None
    last_tested: datetime | None = None

    lower_band = level_price * (1 - proximity_pct)
    upper_band = level_price * (1 + proximity_pct)

    for i in range(len(daily_df)):
        touched_as_resistance = highs[i] >= lower_band and closes[i] < level_price
        touched_as_support = lows[i] <= upper_band and closes[i] > level_price

        if touched_as_resistance or touched_as_support:
            touch_count += 1
            ts = (
                dates[i].to_pydatetime()
                if hasattr(dates[i], "to_pydatetime")
                else datetime.now(tz=timezone.utc)
            )
            if first_seen is None:
                first_seen = ts
            last_tested = ts

    now = datetime.now(tz=timezone.utc)
    return touch_count, first_seen or now, last_tested or now


def detect_key_levels(
    daily_df: pd.DataFrame,
    proximity_pct: float = 0.005,
    min_touches: int = 3,
) -> List[PriceLevel]:
    """Detect support and resistance levels from daily OHLCV data.

    Algorithm
    ---------
    1. Find swing highs and swing lows.
    2. Cluster pivot prices by proximity.
    3. Count how many times price tested each level without breaking it.
    4. Keep only levels with ``touch_count >= min_touches``.
    5. Classify each level relative to the most recent close.
    """
    if daily_df.empty or len(daily_df) < 5:
        logger.warning("Insufficient daily data for level detection (%d rows).", len(daily_df))
        return []

    highs = daily_df["High"].values
    lows = daily_df["Low"].values

    swing_high_idx = _find_swing_highs(highs)
    swing_low_idx = _find_swing_lows(lows)

    pivot_prices = np.concatenate([highs[swing_high_idx], lows[swing_low_idx]])
    if len(pivot_prices) == 0:
        logger.debug("No swing pivots found.")
        return []

    clusters = _cluster_prices(pivot_prices, proximity_pct)
    last_close = float(daily_df["Close"].iloc[-1])
    levels: List[PriceLevel] = []

    for cluster in clusters:
        level_price = float(np.mean(cluster))
        touch_count, first_seen, last_tested = _count_touches(
            daily_df, level_price, proximity_pct
        )

        if touch_count < min_touches:
            continue

        level_type = "support" if last_close > level_price else "resistance"
        levels.append(
            PriceLevel(
                price=round(level_price, 6),
                level_type=level_type,
                touch_count=touch_count,
                first_seen=first_seen,
                last_tested=last_tested,
            )
        )

    levels.sort(key=lambda lv: lv.price)
    logger.info(
        "Detected %d key levels (from %d pivot points, %d clusters).",
        len(levels),
        len(pivot_prices),
        len(clusters),
    )
    return levels
