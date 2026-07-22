"""
Shock Detector — identifies assets that experienced a significant price drop.

This is the entry gate for the Asymmetric Capitulation Detector module.
It flags assets with a daily drop >= SHOCK_THRESHOLD_PCT and classifies
the drop as idiosyncratic (asset-specific) or systemic (market-wide).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Default shock threshold: -2% daily drop
SHOCK_THRESHOLD_PCT: float = -0.02
# Benchmark threshold: if the benchmark also drops this much, the shock
# is considered systemic (less favorable for asymmetric buy)
BENCHMARK_SYSTEMIC_PCT: float = -0.01
# Cumulative drop multiplier for multi-day capitulation detection
CUMULATIVE_DROP_MULT: float = 1.5


@dataclass
class ShockResult:
    """Result of the shock detection gate."""

    ticker: str
    drop_pct: float                 # Negative value (e.g. -0.035 = -3.5%)
    is_idiosyncratic: bool          # True if benchmark didn't crash too
    benchmark_drop_pct: float       # Benchmark's daily return
    capitulation_low: float         # Session low (for SL anchoring)
    capitulation_volume_ratio: float  # Volume vs 20-day SMA


def detect_shock(
    daily_df: pd.DataFrame,
    threshold_pct: float = SHOCK_THRESHOLD_PCT,
) -> Optional[ShockResult]:
    """Check if any recent daily candle (last 3 bars) qualifies as a shock.

    Evaluates both close return and intraday low return vs previous close across
    recent bars (up to last 3 bars) to prevent marginal bar price changes or day 2
    stabilization from immediately dropping active capitulation signals.

    Parameters
    ----------
    daily_df : pd.DataFrame
        Daily OHLCV DataFrame with at least 22 rows (20 for vol SMA + 2 for return).
    threshold_pct : float
        Minimum negative return to qualify (default: -0.02 = -2%).

    Returns
    -------
    ShockResult or None
        Result if shock detected, None otherwise.
    """
    if daily_df is None or len(daily_df) < 22:
        return None

    close = daily_df["Close"].astype(float)
    volume = daily_df["Volume"].astype(float)
    low = daily_df["Low"].astype(float)

    # Evaluate shock strictly on the latest candle (bar -1) to ensure signal reflects current market state
    prev_close = float(close.iloc[-2])
    if prev_close <= 0:
        return None

    daily_return = float((close.iloc[-1] / prev_close) - 1.0)
    intraday_return = float((low.iloc[-1] / prev_close) - 1.0)
    effective_drop = min(daily_return, intraday_return)

    vol_sma_20 = float(volume.iloc[-21:-1].mean())
    vol_ratio = float(volume.iloc[-1] / vol_sma_20) if vol_sma_20 > 0 else 1.0

    if effective_drop > threshold_pct:
        return None  # Current candle drop does not meet threshold

    capitulation_low = float(low.iloc[-1])

    logger.info(
        "SHOCK detected on current candle: effective_return=%.2f%%, low=%.4f, vol_ratio=%.2fx",
        effective_drop * 100, capitulation_low, vol_ratio,
    )

    return ShockResult(
        ticker="",  # Will be set by the caller
        drop_pct=round(effective_drop, 4),
        is_idiosyncratic=True,  # Will be refined by benchmark comparison
        benchmark_drop_pct=0.0,  # Will be set by the caller
        capitulation_low=capitulation_low,
        capitulation_volume_ratio=round(vol_ratio, 2),
    )


def classify_shock(
    shock: ShockResult,
    benchmark_df: pd.DataFrame,
    benchmark_systemic_pct: float = BENCHMARK_SYSTEMIC_PCT,
    daily_df: Optional[pd.DataFrame] = None,
) -> ShockResult:
    """Refine a shock result by comparing against the benchmark.

    Parameters
    ----------
    shock : ShockResult
        The initial shock detection result.
    benchmark_df : pd.DataFrame
        Daily OHLCV for the benchmark (SPY for equities, BTCUSDT for crypto).
    benchmark_systemic_pct : float
        If benchmark dropped more than this, the shock is systemic.
    daily_df : pd.DataFrame, optional
        Daily OHLCV for the asset to align benchmark dates.

    Returns
    -------
    ShockResult
        Updated with benchmark comparison data.
    """
    if benchmark_df is None or len(benchmark_df) < 2:
        logger.warning("Benchmark data unavailable — assuming idiosyncratic shock.")
        return shock

    try:
        bench_close = benchmark_df["Close"].astype(float)
        bench_return = None

        # Align dates if both daily_df and benchmark_df have DatetimeIndex
        if daily_df is not None and not daily_df.empty and isinstance(daily_df.index, pd.DatetimeIndex) and isinstance(benchmark_df.index, pd.DatetimeIndex):
            common_dates = daily_df.index.intersection(benchmark_df.index)
            if len(common_dates) >= 2:
                aligned_bench = benchmark_df.loc[common_dates, "Close"].astype(float)
                prev_val = float(aligned_bench.iloc[-2])
                if prev_val > 0:
                    bench_return = float((aligned_bench.iloc[-1] / prev_val) - 1.0)

        if bench_return is None:
            prev_val = float(bench_close.iloc[-2])
            if prev_val > 0:
                bench_return = float((bench_close.iloc[-1] / prev_val) - 1.0)
            else:
                bench_return = 0.0

        is_idiosyncratic = bench_return > benchmark_systemic_pct

        shock.benchmark_drop_pct = round(bench_return, 4)
        shock.is_idiosyncratic = is_idiosyncratic

        logger.info(
            "Shock classification: benchmark_return=%.2f%%, is_idiosyncratic=%s",
            bench_return * 100, is_idiosyncratic,
        )
    except Exception as exc:
        logger.warning("Failed benchmark classification: %s — assuming idiosyncratic.", exc)
        shock.benchmark_drop_pct = 0.0
        shock.is_idiosyncratic = True

    return shock


def scan_for_shocks(
    daily_df: pd.DataFrame,
    ticker: str,
    threshold_pct: float = SHOCK_THRESHOLD_PCT,
) -> Optional[ShockResult]:
    """Convenience wrapper: detect shock + set ticker name.

    This is the main entry point called from the capitulation engine.
    """
    result = detect_shock(daily_df, threshold_pct)
    if result is not None:
        result.ticker = ticker
    return result
