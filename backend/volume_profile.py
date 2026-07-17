"""Volume Profile analysis from OHLCV candle data.

Builds an estimated Volume Profile by distributing each candle's volume
uniformly across price bins that fall between its Low and High.  Provides
helpers to extract Point of Control (POC), Value Area, and High/Low
Volume Nodes.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_volume_profile(df: pd.DataFrame, n_bins: int = 50) -> dict[str, Any]:
    """Build a volume profile histogram from OHLCV data.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain at least ``High``, ``Low``, and ``Volume`` columns.
    n_bins : int, optional
        Number of evenly-spaced price bins (default 50).

    Returns
    -------
    dict
        ``bins``       – 1-D array of bin centre prices.
        ``volumes``    – 1-D array of accumulated volume per bin.
        ``price_min``  – lower edge of the price range.
        ``price_max``  – upper edge of the price range.
        ``bin_width``  – width of each bin.
    """
    if df.empty:
        logger.warning("build_volume_profile: received empty DataFrame")
        return {
            "bins": np.array([], dtype=np.float64),
            "volumes": np.array([], dtype=np.float64),
            "price_min": 0.0,
            "price_max": 0.0,
            "bin_width": 0.0,
        }

    price_min: float = float(df["Low"].min())
    price_max: float = float(df["High"].max())

    if price_min == price_max:
        logger.warning(
            "build_volume_profile: price_min == price_max (%.6f); "
            "returning single-bin profile",
            price_min,
        )
        return {
            "bins": np.array([price_min], dtype=np.float64),
            "volumes": np.array([float(df["Volume"].sum())], dtype=np.float64),
            "price_min": price_min,
            "price_max": price_max,
            "bin_width": 0.0,
        }

    # Bin edges (n_bins + 1 edges → n_bins centres)
    edges = np.linspace(price_min, price_max, n_bins + 1)
    bin_width: float = float(edges[1] - edges[0])
    centres = (edges[:-1] + edges[1:]) / 2.0
    volumes = np.zeros(n_bins, dtype=np.float64)

    # Vectorised distribution: for each candle find the bins its range covers
    lows = df["Low"].values.astype(np.float64)
    highs = df["High"].values.astype(np.float64)
    vols = df["Volume"].values.astype(np.float64)

    for low, high, vol in zip(lows, highs, vols):
        if vol <= 0 or np.isnan(vol):
            continue
        # Indices of bins whose centres fall within [low, high]
        mask = (centres >= low) & (centres <= high)
        n_covered = int(mask.sum())
        if n_covered == 0:
            # Candle range narrower than a single bin – assign to nearest bin
            nearest = int(np.argmin(np.abs(centres - (low + high) / 2.0)))
            volumes[nearest] += vol
        else:
            volumes[mask] += vol / n_covered

    logger.debug(
        "build_volume_profile: %d candles → %d bins [%.4f – %.4f]",
        len(df),
        n_bins,
        price_min,
        price_max,
    )

    return {
        "bins": centres,
        "volumes": volumes,
        "price_min": price_min,
        "price_max": price_max,
        "bin_width": bin_width,
    }


# ---------------------------------------------------------------------------
# Point of Control
# ---------------------------------------------------------------------------

def find_poc(profile: dict[str, Any]) -> float:
    """Return the bin centre with the highest accumulated volume.

    Parameters
    ----------
    profile : dict
        Output of :func:`build_volume_profile`.

    Returns
    -------
    float
        Price level of the Point of Control, or ``0.0`` for empty profiles.
    """
    bins: np.ndarray = profile["bins"]
    volumes: np.ndarray = profile["volumes"]

    if bins.size == 0 or volumes.sum() == 0:
        logger.warning("find_poc: empty or zero-volume profile")
        return 0.0

    poc_idx = int(np.argmax(volumes))
    return float(bins[poc_idx])


# ---------------------------------------------------------------------------
# Value Area
# ---------------------------------------------------------------------------

def find_value_area(
    profile: dict[str, Any],
    pct: float = 0.70,
) -> tuple[float, float]:
    """Compute Value Area Low and Value Area High.

    Starting from the POC bin, alternately expand one bin above and one
    bin below, accumulating volume until *pct* of total volume is captured.

    Parameters
    ----------
    profile : dict
        Output of :func:`build_volume_profile`.
    pct : float, optional
        Fraction of total volume to capture (default 0.70).

    Returns
    -------
    tuple[float, float]
        ``(val, vah)`` – Value Area Low and Value Area High.
    """
    bins: np.ndarray = profile["bins"]
    volumes: np.ndarray = profile["volumes"]

    if bins.size == 0:
        logger.warning("find_value_area: empty profile")
        return (0.0, 0.0)

    total_volume = volumes.sum()
    if total_volume == 0:
        logger.warning("find_value_area: zero total volume")
        return (float(bins[0]), float(bins[-1]))

    poc_idx = int(np.argmax(volumes))
    accumulated = float(volumes[poc_idx])
    lo = poc_idx
    hi = poc_idx
    target = total_volume * pct

    while accumulated < target:
        can_go_down = lo > 0
        can_go_up = hi < len(bins) - 1

        if not can_go_down and not can_go_up:
            break

        vol_below = float(volumes[lo - 1]) if can_go_down else -1.0
        vol_above = float(volumes[hi + 1]) if can_go_up else -1.0

        if vol_below >= vol_above:
            lo -= 1
            accumulated += volumes[lo]
        else:
            hi += 1
            accumulated += volumes[hi]

    val = float(bins[lo])
    vah = float(bins[hi])

    logger.debug(
        "find_value_area: VAL=%.4f  VAH=%.4f  (%.1f%% of volume captured)",
        val,
        vah,
        (accumulated / total_volume) * 100,
    )
    return (val, vah)


# ---------------------------------------------------------------------------
# High / Low Volume Nodes
# ---------------------------------------------------------------------------

def find_hvn_lvn(
    profile: dict[str, Any],
    threshold_pct: float = 0.15,
) -> tuple[list[float], list[float]]:
    """Identify High Volume Nodes and Low Volume Nodes.

    * **HVN** – bins with volume > ``mean + threshold_pct * range``
    * **LVN** – bins with volume < ``mean - threshold_pct * range`` *and*
      volume > 0 (truly empty bins are excluded).

    Parameters
    ----------
    profile : dict
        Output of :func:`build_volume_profile`.
    threshold_pct : float, optional
        Fraction of the volume range used as offset from the mean
        (default 0.15).

    Returns
    -------
    tuple[list[float], list[float]]
        ``(hvn_prices, lvn_prices)`` – lists of bin centre prices.
    """
    bins: np.ndarray = profile["bins"]
    volumes: np.ndarray = profile["volumes"]

    if bins.size == 0:
        logger.warning("find_hvn_lvn: empty profile")
        return ([], [])

    vol_mean = float(volumes.mean())
    vol_range = float(volumes.max() - volumes.min())

    hvn_thresh = vol_mean + threshold_pct * vol_range
    lvn_thresh = vol_mean - threshold_pct * vol_range

    hvn_mask = volumes > hvn_thresh
    lvn_mask = (volumes < lvn_thresh) & (volumes > 0)

    hvn_prices: list[float] = bins[hvn_mask].tolist()
    lvn_prices: list[float] = bins[lvn_mask].tolist()

    logger.debug(
        "find_hvn_lvn: %d HVN zones, %d LVN zones (threshold_pct=%.2f)",
        len(hvn_prices),
        len(lvn_prices),
        threshold_pct,
    )
    return (hvn_prices, lvn_prices)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def analyze_volume_profile(
    hourly_df: pd.DataFrame,
    current_price: float,
    lookback_days: int = 20,
) -> dict[str, Any]:
    """High-level analysis: build profile and extract key levels.

    Parameters
    ----------
    hourly_df : pd.DataFrame
        Hourly OHLCV data with a ``DatetimeIndex``.
    current_price : float
        Latest known price for the asset.
    lookback_days : int, optional
        Number of trailing calendar days to include (default 20).

    Returns
    -------
    dict
        ``poc``, ``vah``, ``val``, ``hvn_zones``, ``lvn_zones``,
        ``price_vs_va`` (one of ``'below_val'``, ``'in_value_area'``,
        ``'above_vah'``).
    """
    empty_result: dict[str, Any] = {
        "poc": 0.0,
        "vah": 0.0,
        "val": 0.0,
        "hvn_zones": [],
        "lvn_zones": [],
        "price_vs_va": "in_value_area",
    }

    if hourly_df.empty:
        logger.warning("analyze_volume_profile: empty DataFrame received")
        return empty_result

    # Filter to lookback window
    if not isinstance(hourly_df.index, pd.DatetimeIndex):
        logger.warning(
            "analyze_volume_profile: index is not DatetimeIndex; "
            "attempting to convert"
        )
        try:
            hourly_df = hourly_df.copy()
            hourly_df.index = pd.to_datetime(hourly_df.index)
        except Exception:
            logger.error(
                "analyze_volume_profile: failed to convert index to datetime"
            )
            return empty_result

    cutoff = hourly_df.index.max() - timedelta(days=lookback_days)
    filtered = hourly_df.loc[hourly_df.index >= cutoff]

    if filtered.empty:
        logger.warning(
            "analyze_volume_profile: no data within the last %d days",
            lookback_days,
        )
        return empty_result

    logger.info(
        "analyze_volume_profile: %d candles in last %d days, price=%.4f",
        len(filtered),
        lookback_days,
        current_price,
    )

    profile = build_volume_profile(filtered)
    poc = find_poc(profile)
    val, vah = find_value_area(profile)
    hvn_zones, lvn_zones = find_hvn_lvn(profile)

    if current_price < val:
        price_vs_va = "below_val"
    elif current_price > vah:
        price_vs_va = "above_vah"
    else:
        price_vs_va = "in_value_area"

    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "hvn_zones": hvn_zones,
        "lvn_zones": lvn_zones,
        "price_vs_va": price_vs_va,
    }
