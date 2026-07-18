"""Volume Profile analysis translating TradingView's Fixed Range indicator logic.

Distributes candle volume across price rows by dividing each candle into body, 
top wick, and bottom wick segments, returning POC, VAH, and VAL.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default configurations mapping to TradingView standards
DEFAULTS = {
    "bars": 130,       # number of most-recent candles in the fixed range (130 for equities ~20 days, 480 for crypto)
    "rows": 50,        # number of price buckets (Pine "Row Size" / cnum)
    "percent": 70.0,   # Value Area volume %
}


def _get_vol(y11: float, y12: float, y21: float, y22: float, height: float, vol: float) -> float:
    """Volume contributed by the intersection of price band [y11,y12] with the
    candle segment [y21,y22]. Mirrors the Pine `get_vol()` helper."""
    if height <= 0:
        return 0.0
    top = min(max(y11, y12), max(y21, y22))
    bottom = max(min(y11, y12), min(y21, y22))
    overlap = top - bottom
    if overlap <= 0:
        return 0.0
    return overlap * vol / height


def compute_volume_profile(df: pd.DataFrame, cfg: Optional[dict] = None) -> Optional[dict]:
    """Compute the fixed-range volume profile for the last `bars` candles.

    Args:
        df:  DataFrame with columns time, open, high, low, close, volume.
        cfg: dict overriding DEFAULTS (bars / rows / percent).

    Returns:
        dict with keys: rows, poc, va_high, va_low, max_total, t_start, t_end, bars.
    """
    c = dict(DEFAULTS)
    if cfg:
        c.update({k: v for k, v in cfg.items() if v is not None})

    n = len(df)
    if n < 2:
        return None

    bbars = max(1, min(int(c["bars"]), n))
    cnum = max(5, min(int(c["rows"]), 150))
    percent = max(0.0, min(float(c["percent"]), 100.0))

    # Support timestamps as index if "time" column is not present
    if "time" in df.columns:
        time = df["time"].to_numpy()
    else:
        time = df.index.to_numpy()

    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)

    start = n - bbars
    seg_high = high[start:]
    seg_low = low[start:]

    top = float(seg_high.max())
    bot = float(seg_low.min())
    if top <= bot:
        return None

    step = (top - bot) / cnum
    levels = [bot + step * x for x in range(cnum + 1)]

    up_vol = [0.0] * cnum
    down_vol = [0.0] * cnum

    for i in range(start, n):
        o, h, l, cl, v = open_[i], high[i], low[i], close[i], volume[i]
        if v <= 0 or np.isnan(v):
            continue
        body_top = max(cl, o)
        body_bot = min(cl, o)
        itsgreen = cl >= o

        topwick = h - body_top
        bottomwick = body_bot - l
        body = body_top - body_bot

        denom = 2 * topwick + 2 * bottomwick + body
        if denom <= 0:
            continue

        bodyvol = body * v / denom
        topwickvol = 2 * topwick * v / denom
        bottomwickvol = 2 * bottomwick * v / denom

        for x in range(cnum):
            lx = levels[x]
            lx1 = levels[x + 1]
            body_part = _get_vol(lx, lx1, body_bot, body_top, body, bodyvol)
            top_part = _get_vol(lx, lx1, body_top, h, topwick, topwickvol) / 2.0
            bot_part = _get_vol(lx, lx1, body_bot, l, bottomwick, bottomwickvol) / 2.0

            up_vol[x] += (body_part if itsgreen else 0.0) + top_part + bot_part
            down_vol[x] += (0.0 if itsgreen else body_part) + top_part + bot_part

    total = [up_vol[x] + down_vol[x] for x in range(cnum)]
    grand_total = sum(total)
    if grand_total <= 0:
        return None

    # POC = row with maximum total volume
    poc = int(max(range(cnum), key=lambda x: total[x]))

    # Value area expansion
    totalmax = grand_total * percent / 100.0
    va_total = total[poc]
    up = poc
    down = poc
    for _ in range(cnum):
        if va_total >= totalmax:
            break
        uppervol = total[up + 1] if up < cnum - 1 else 0.0
        lowervol = total[down - 1] if down > 0 else 0.0
        if uppervol == 0.0 and lowervol == 0.0:
            break
        if uppervol >= lowervol:
            va_total += uppervol
            up += 1
        else:
            va_total += lowervol
            down -= 1

    max_total = max(total)
    poc_level = (levels[poc] + levels[poc + 1]) / 2.0

    rows = []
    for x in range(cnum):
        rows.append({
            "y1": float(levels[x]),
            "y2": float(levels[x + 1]),
            "up": float(up_vol[x]),
            "down": float(down_vol[x]),
            "va": bool(down <= x <= up),
        })

    return {
        "rows": rows,
        "poc": float(poc_level),
        "va_high": float(levels[up + 1]),
        "va_low": float(levels[down]),
        "max_total": float(max_total),
        "bars": bbars,
    }


def analyze_volume_profile(
    hourly_df: pd.DataFrame,
    current_price: float,
    lookback_days: int = 20,
) -> dict[str, Any]:
    """High-level orchestrator implementing the exact TradingView calculations."""
    empty_result: dict[str, Any] = {
        "poc": 0.0,
        "vah": 0.0,
        "val": 0.0,
        "hvn_zones": [],
        "lvn_zones": [],
        "price_vs_va": "in_value_area",
    }

    if hourly_df.empty:
        return empty_result

    # Standardize columns to lowercase for compute_volume_profile compatibility
    df_mapped = pd.DataFrame()
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in hourly_df.columns:
            df_mapped[col.lower()] = hourly_df[col]
        else:
            logger.warning("analyze_volume_profile: missing column %s", col)
            return empty_result

    if "time" in hourly_df.columns:
        df_mapped["time"] = hourly_df["time"]

    # Determine bars: Cripto (24/7) -> 20 days is 480 bars. Equities -> 20 days is ~130 bars.
    is_crypto = len(hourly_df) > 300
    bars = 480 if is_crypto else 130

    res = compute_volume_profile(df_mapped, {"bars": bars, "rows": 50, "percent": 70.0})
    if not res:
        return empty_result

    poc = res["poc"]
    vah = res["va_high"]
    val = res["va_low"]

    if current_price < val:
        price_vs_va = "below_val"
    elif current_price > vah:
        price_vs_va = "above_vah"
    else:
        price_vs_va = "in_value_area"

    # Identify HVN/LVN zones for confluence compatibility
    hvn_zones = []
    lvn_zones = []
    try:
        volumes = np.array([r["up"] + r["down"] for r in res["rows"]])
        centers = np.array([(r["y1"] + r["y2"]) / 2.0 for r in res["rows"]])
        vol_mean = float(volumes.mean())
        vol_range = float(volumes.max() - volumes.min())
        hvn_thresh = vol_mean + 0.15 * vol_range
        lvn_thresh = vol_mean - 0.15 * vol_range
        hvn_zones = centers[volumes > hvn_thresh].tolist()
        lvn_zones = centers[(volumes < lvn_thresh) & (volumes > 0)].tolist()
    except Exception:
        pass

    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "hvn_zones": hvn_zones,
        "lvn_zones": lvn_zones,
        "price_vs_va": price_vs_va,
    }
