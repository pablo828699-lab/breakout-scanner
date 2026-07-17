"""Smart Money Concepts (SMC) price-action analysis on OHLCV DataFrames.

Provides detection of:
* Market Structure Breaks (MSB)
* Fair Value Gaps (FVG)
* Order Blocks (OB)
* Confluence Zones (FVG + OB overlap)
* Multi-timeframe orchestration (1D + 4H)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_ohlcv(df: pd.DataFrame, min_rows: int = 3) -> bool:
    """Return *True* if *df* looks like a usable OHLCV frame."""
    if df is None or df.empty:
        logger.warning("Received empty or None DataFrame – skipping analysis.")
        return False
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        logger.warning("DataFrame missing columns: %s", missing)
        return False
    if len(df) < min_rows:
        logger.warning(
            "DataFrame has only %d rows (need >= %d) – skipping.",
            len(df),
            min_rows,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# 1. Market Structure Breaks
# ---------------------------------------------------------------------------


def detect_msb(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Detect Market Structure Breaks on an OHLCV DataFrame.

    A *swing high* at index ``i`` satisfies
    ``High[i] > High[i-1]  AND  High[i] > High[i+1]``.

    A *swing low* at index ``i`` satisfies
    ``Low[i] < Low[i-1]  AND  Low[i] < Low[i+1]``.

    An MSB occurs when:
    * A swing high breaks *above* the previous swing high → **bullish**.
    * A swing low breaks *below* the previous swing low  → **bearish**.

    Returns the most recent **5** MSBs (newest last).
    """
    if not _validate_ohlcv(df, min_rows=3):
        return []

    highs: np.ndarray = df["High"].astype(float).values
    lows: np.ndarray = df["Low"].astype(float).values
    n = len(df)

    # --- Collect swing points ------------------------------------------------
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []

    for i in range(1, n - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            swing_highs.append((i, float(highs[i])))
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            swing_lows.append((i, float(lows[i])))

    # --- Detect breaks -------------------------------------------------------
    msb_list: list[dict[str, Any]] = []

    for idx in range(1, len(swing_highs)):
        prev_price = swing_highs[idx - 1][1]
        curr_idx, curr_price = swing_highs[idx]
        if curr_price > prev_price:
            msb_list.append(
                {
                    "type": "bullish",
                    "price": curr_price,
                    "index": curr_idx,
                    "broken_level": prev_price,
                }
            )

    for idx in range(1, len(swing_lows)):
        prev_price = swing_lows[idx - 1][1]
        curr_idx, curr_price = swing_lows[idx]
        if curr_price < prev_price:
            msb_list.append(
                {
                    "type": "bearish",
                    "price": curr_price,
                    "index": curr_idx,
                    "broken_level": prev_price,
                }
            )

    # Sort by index so "most recent" means highest index values.
    msb_list.sort(key=lambda m: m["index"])

    logger.debug("Detected %d total MSBs – returning last 5.", len(msb_list))
    return msb_list[-5:]


# ---------------------------------------------------------------------------
# 2. Fair Value Gaps
# ---------------------------------------------------------------------------


def detect_fvg(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Detect Fair Value Gaps (imbalances between 3 consecutive candles).

    *Bullish FVG*: ``candle[i-2].High < candle[i].Low``  (gap up).
    *Bearish FVG*: ``candle[i-2].Low  > candle[i].High`` (gap down).

    An FVG is marked ``filled=True`` when any subsequent candle's Close
    enters the gap range.

    Only **unfilled** FVGs whose anchor candle (``i``) falls within the
    last 50 rows are returned.
    """
    if not _validate_ohlcv(df, min_rows=3):
        return []

    highs: np.ndarray = df["High"].astype(float).values
    lows: np.ndarray = df["Low"].astype(float).values
    closes: np.ndarray = df["Close"].astype(float).values
    n = len(df)

    lookback_start = max(2, n - 50)

    fvg_list: list[dict[str, Any]] = []

    for i in range(lookback_start, n):
        # Bullish FVG: gap-up
        if highs[i - 2] < lows[i]:
            gap_low = float(highs[i - 2])
            gap_high = float(lows[i])
            midpoint = (gap_high + gap_low) / 2.0

            filled = bool(
                np.any((closes[i + 1 :] >= gap_low) & (closes[i + 1 :] <= gap_high))
                if i + 1 < n
                else False
            )

            if not filled:
                fvg_list.append(
                    {
                        "type": "bullish",
                        "high": gap_high,
                        "low": gap_low,
                        "midpoint": midpoint,
                        "index": i,
                        "filled": False,
                    }
                )

        # Bearish FVG: gap-down
        if lows[i - 2] > highs[i]:
            gap_high = float(lows[i - 2])
            gap_low = float(highs[i])
            midpoint = (gap_high + gap_low) / 2.0

            filled = bool(
                np.any((closes[i + 1 :] >= gap_low) & (closes[i + 1 :] <= gap_high))
                if i + 1 < n
                else False
            )

            if not filled:
                fvg_list.append(
                    {
                        "type": "bearish",
                        "high": gap_high,
                        "low": gap_low,
                        "midpoint": midpoint,
                        "index": i,
                        "filled": False,
                    }
                )

    logger.debug(
        "Detected %d unfilled FVGs in the last 50 candles.", len(fvg_list)
    )
    return fvg_list


# ---------------------------------------------------------------------------
# 3. Order Blocks
# ---------------------------------------------------------------------------


def detect_order_blocks(
    df: pd.DataFrame,
    impulse_threshold: float = 0.015,
) -> list[dict[str, Any]]:
    """Detect Order Blocks on an OHLCV DataFrame.

    A *bullish OB* is the last **bearish** candle before a bullish impulse
    move.  A *bearish OB* is the last **bullish** candle before a bearish
    impulse move.

    An **impulse move** is a sequence of ≥ 2 consecutive candles moving in
    the same direction whose total percentage move exceeds
    *impulse_threshold* (default 1.5 %).

    Returns the most recent **5** Order Blocks (newest last).
    """
    if not _validate_ohlcv(df, min_rows=4):
        return []

    opens: np.ndarray = df["Open"].astype(float).values
    highs: np.ndarray = df["High"].astype(float).values
    lows: np.ndarray = df["Low"].astype(float).values
    closes: np.ndarray = df["Close"].astype(float).values
    n = len(df)

    ob_list: list[dict[str, Any]] = []

    i = 0
    while i < n:
        # Try to find a bullish impulse starting at *i*.
        run_start = i
        while i < n - 1 and closes[i + 1] > closes[i]:
            i += 1
        run_len = i - run_start + 1
        if run_len >= 2 and closes[run_start] > 0.0:
            move_pct = (closes[i] - closes[run_start]) / closes[run_start]
            if move_pct > impulse_threshold:
                # Walk backwards from run_start to find last bearish candle.
                ob_idx = run_start - 1
                while ob_idx >= 0 and closes[ob_idx] >= opens[ob_idx]:
                    ob_idx -= 1
                if ob_idx >= 0:
                    ob_list.append(
                        {
                            "type": "bullish",
                            "high": float(highs[ob_idx]),
                            "low": float(lows[ob_idx]),
                            "index": ob_idx,
                        }
                    )

        # Try bearish impulse from the same segment starting point.
        j = run_start
        while j < n - 1 and closes[j + 1] < closes[j]:
            j += 1
        bear_run_len = j - run_start + 1
        if bear_run_len >= 2 and closes[run_start] > 0.0:
            move_pct = (closes[run_start] - closes[j]) / closes[run_start]
            if move_pct > impulse_threshold:
                ob_idx = run_start - 1
                while ob_idx >= 0 and closes[ob_idx] <= opens[ob_idx]:
                    ob_idx -= 1
                if ob_idx >= 0:
                    ob_list.append(
                        {
                            "type": "bearish",
                            "high": float(highs[ob_idx]),
                            "low": float(lows[ob_idx]),
                            "index": ob_idx,
                        }
                    )

        i = max(i + 1, run_start + 1)  # always advance

    # De-duplicate by (type, index) – keep first occurrence.
    seen: set[tuple[str, int]] = set()
    unique: list[dict[str, Any]] = []
    for ob in ob_list:
        key = (ob["type"], ob["index"])
        if key not in seen:
            seen.add(key)
            unique.append(ob)

    unique.sort(key=lambda o: o["index"])
    logger.debug("Detected %d unique OBs – returning last 5.", len(unique))
    return unique[-5:]


# ---------------------------------------------------------------------------
# 4. Confluence Zones
# ---------------------------------------------------------------------------


def find_confluence_zones(
    fvgs: list[dict[str, Any]],
    obs: list[dict[str, Any]],
    proximity_pct: float = 0.01,
) -> list[dict[str, Any]]:
    """Find zones where an FVG and an OB overlap or are nearby.

    Two zones are considered confluent when they overlap directly **or**
    when the gap between them is ≤ *proximity_pct* (default 1 %) of the
    midpoint of their combined range.

    Parameters
    ----------
    fvgs:
        Output of :func:`detect_fvg`.
    obs:
        Output of :func:`detect_order_blocks`.
    proximity_pct:
        Maximum relative distance to still count as "nearby".

    Returns
    -------
    list[dict]
        Each dict: ``{'zone_high', 'zone_low', 'components', 'strength'}``.
    """
    if not fvgs or not obs:
        return []

    zones: list[dict[str, Any]] = []

    for fvg in fvgs:
        fvg_high = float(fvg["high"])
        fvg_low = float(fvg["low"])

        for ob in obs:
            ob_high = float(ob["high"])
            ob_low = float(ob["low"])

            combined_high = max(fvg_high, ob_high)
            combined_low = min(fvg_low, ob_low)
            midpoint = (combined_high + combined_low) / 2.0

            if midpoint == 0.0:
                continue

            # Check overlap: two ranges overlap when max(lows) < min(highs).
            overlap = min(fvg_high, ob_high) - max(fvg_low, ob_low)
            if overlap >= 0:
                # Direct overlap
                zone_high = min(fvg_high, ob_high)
                zone_low = max(fvg_low, ob_low)
            else:
                # No overlap – check proximity.
                gap = abs(overlap)
                if gap / midpoint > proximity_pct:
                    continue
                zone_high = combined_high
                zone_low = combined_low

            components: list[str] = [
                f"FVG_{fvg['type']}@{fvg['index']}",
                f"OB_{ob['type']}@{ob['index']}",
            ]

            zones.append(
                {
                    "zone_high": float(zone_high),
                    "zone_low": float(zone_low),
                    "components": components,
                    "strength": len(components),
                }
            )

    logger.debug("Found %d confluence zones.", len(zones))
    return zones


# ---------------------------------------------------------------------------
# 5. Multi-timeframe Orchestrator
# ---------------------------------------------------------------------------


def analyze_price_structure(
    daily_df: pd.DataFrame,
    hourly_df: pd.DataFrame,
) -> dict[str, Any]:
    """Run full SMC analysis on daily and 4-hour timeframes.

    The hourly DataFrame is resampled to 4H internally.

    Returns
    -------
    dict
        Keys: ``msb_1d``, ``msb_4h``, ``fvg_1d``, ``fvg_4h``,
        ``ob_1d``, ``ob_4h``, ``confluence_zones``.
    """
    result: dict[str, Any] = {
        "msb_1d": [],
        "msb_4h": [],
        "fvg_1d": [],
        "fvg_4h": [],
        "ob_1d": [],
        "ob_4h": [],
        "confluence_zones": [],
    }

    # --- Resample hourly → 4H ------------------------------------------------
    h4_df = pd.DataFrame()
    if _validate_ohlcv(hourly_df, min_rows=4):
        try:
            h4_df = (
                hourly_df.resample("4h")
                .agg(
                    {
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last",
                        "Volume": "sum",
                    }
                )
                .dropna()
            )
        except Exception:
            logger.exception("Failed to resample hourly data to 4H.")

    # --- Daily analysis ------------------------------------------------------
    if _validate_ohlcv(daily_df):
        logger.info("Running SMC analysis on daily timeframe (%d rows).", len(daily_df))
        result["msb_1d"] = detect_msb(daily_df)
        result["fvg_1d"] = detect_fvg(daily_df)
        result["ob_1d"] = detect_order_blocks(daily_df)
    else:
        logger.warning("Skipping daily analysis – invalid DataFrame.")

    # --- 4H analysis ---------------------------------------------------------
    if _validate_ohlcv(h4_df):
        logger.info("Running SMC analysis on 4H timeframe (%d rows).", len(h4_df))
        result["msb_4h"] = detect_msb(h4_df)
        result["fvg_4h"] = detect_fvg(h4_df)
        result["ob_4h"] = detect_order_blocks(h4_df)
    else:
        logger.warning("Skipping 4H analysis – invalid DataFrame.")

    # --- Confluence (merge FVGs & OBs from both timeframes) -------------------
    all_fvgs = result["fvg_1d"] + result["fvg_4h"]
    all_obs = result["ob_1d"] + result["ob_4h"]
    result["confluence_zones"] = find_confluence_zones(all_fvgs, all_obs)

    logger.info(
        "Price-structure analysis complete: %d confluence zones found.",
        len(result["confluence_zones"]),
    )
    return result
