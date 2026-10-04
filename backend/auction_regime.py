"""
Auction Market Theory (AMT) & Value Migration Engine.

Separates Previous Session Profile from Developing Intraday Profile,
evaluates value migration slopes, POC-price divergence, acceptance vs rejection,
failed auctions, and market regime classification.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from backend.volume_profile import compute_volume_profile

logger = logging.getLogger(__name__)


def compute_dual_session_profiles(
    df: pd.DataFrame,
    session_bars: int = 24,
) -> Dict[str, Any]:
    """
    Computes both Previous Session Profile (frozen) and Developing Intraday Profile (causal).
    
    Returns:
    - prev_poc, prev_vah, prev_val
    - intra_poc, intra_vah, intra_val
    - poc_slope, vah_slope, val_slope
    """
    n = len(df)
    if n < 10:
        return {
            "prev_poc": 0.0, "prev_vah": 0.0, "prev_val": 0.0,
            "intra_poc": 0.0, "intra_vah": 0.0, "intra_val": 0.0,
            "poc_slope": 0.0, "vah_slope": 0.0, "val_slope": 0.0,
        }

    # Standardize column names
    df_clean = pd.DataFrame()
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df_clean[col.lower()] = df[col]

    sb = min(session_bars, n // 2) if n >= 20 else n

    # 1. Previous Session Profile (Frozen historical session)
    if n >= sb * 2:
        df_prev = df_clean.iloc[-sb * 2 : -sb].copy()
        res_prev = compute_volume_profile(df_prev, {"bars": sb, "rows": 40, "percent": 70.0})
    else:
        df_prev = df_clean.iloc[:sb].copy()
        res_prev = compute_volume_profile(df_prev, {"bars": len(df_prev), "rows": 40, "percent": 70.0})

    # 2. Developing Intraday Profile (Active session)
    df_intra = df_clean.iloc[-sb:].copy()
    res_intra = compute_volume_profile(df_intra, {"bars": len(df_intra), "rows": 40, "percent": 70.0})

    # 3. Rolling slopes of Developing Value Area (causal expansion)
    pocs, vahs, vals = [], [], []
    step_start = max(3, len(df_intra) // 4)
    for step in range(step_start, len(df_intra) + 1):
        sub_df = df_intra.iloc[:step]
        sub_res = compute_volume_profile(sub_df, {"bars": step, "rows": 30, "percent": 70.0})
        if sub_res:
            pocs.append(sub_res["poc"])
            vahs.append(sub_res["va_high"])
            vals.append(sub_res["va_low"])

    def _calc_slope(arr: List[float]) -> float:
        if len(arr) < 2 or np.all(arr == arr[0]):
            return 0.0
        x = np.arange(len(arr), dtype=float)
        slope, _ = np.polyfit(x, arr, 1)
        return float(slope)

    prev_poc = res_prev["poc"] if res_prev else 0.0
    prev_vah = res_prev["va_high"] if res_prev else 0.0
    prev_val = res_prev["va_low"] if res_prev else 0.0

    intra_poc = res_intra["poc"] if res_intra else prev_poc
    intra_vah = res_intra["va_high"] if res_intra else prev_vah
    intra_val = res_intra["va_low"] if res_intra else prev_val

    return {
        "prev_poc": float(prev_poc),
        "prev_vah": float(prev_vah),
        "prev_val": float(prev_val),
        "intra_poc": float(intra_poc),
        "intra_vah": float(intra_vah),
        "intra_val": float(intra_val),
        "poc_slope": _calc_slope(pocs),
        "vah_slope": _calc_slope(vahs),
        "val_slope": _calc_slope(vals),
    }


def evaluate_auction_context(
    price: float,
    profiles: Dict[str, Any],
    of_metrics: Dict[str, Any],
    bars_above_vah: int = 0,
    bars_below_val: int = 0,
    vol_share_above_vah: float = 0.0,
    vol_share_below_val: float = 0.0,
) -> Dict[str, Any]:
    """
    Evaluates relative price location, value migration, acceptance/rejection,
    POC divergence, initiative/responsive flow, and market auction regime.
    """
    atr = max(float(of_metrics.get("atr", 1.0)), 1e-6)

    prev_poc = profiles.get("prev_poc", price)
    prev_vah = profiles.get("prev_vah", price * 1.02)
    prev_val = profiles.get("prev_val", price * 0.98)

    intra_poc = profiles.get("intra_poc", price)
    intra_vah = profiles.get("intra_vah", price * 1.02)
    intra_val = profiles.get("intra_val", price * 0.98)

    poc_slope = profiles.get("poc_slope", 0.0)
    vah_slope = profiles.get("vah_slope", 0.0)
    val_slope = profiles.get("val_slope", 0.0)

    # 1. Location Tags
    dist_vah_atr = abs(price - intra_vah) / atr
    dist_val_atr = abs(price - intra_val) / atr
    dist_poc_atr = abs(price - intra_poc) / atr

    location_tags = []
    if price > intra_vah:
        location_tags.append("ABOVE_INTRADAY_VAH")
    elif price < intra_val:
        location_tags.append("BELOW_INTRADAY_VAL")
    else:
        location_tags.append("INSIDE_VALUE")

    if dist_vah_atr < 0.35:
        location_tags.append("NEAR_INTRADAY_VAH")
    if dist_val_atr < 0.35:
        location_tags.append("NEAR_INTRADAY_VAL")
    if dist_poc_atr < 0.35:
        location_tags.append("NEAR_INTRADAY_POC")

    if price > prev_vah:
        location_tags.append("ABOVE_PREV_VAH")
    elif price < prev_val:
        location_tags.append("BELOW_PREV_VAL")

    # 2. Value Migration
    slope_thr = 0.02 * atr
    if poc_slope > slope_thr and vah_slope > slope_thr and val_slope > slope_thr:
        migration_state = "VALUE_MIGRATION_UP"
    elif poc_slope < -slope_thr and vah_slope < -slope_thr and val_slope < -slope_thr:
        migration_state = "VALUE_MIGRATION_DOWN"
    else:
        migration_state = "VALUE_FLAT"

    # Inter-session relationships
    if intra_val > prev_vah:
        overlap_tag = "NON_OVERLAPPING_HIGHER_VALUE"
    elif intra_vah < prev_val:
        overlap_tag = "NON_OVERLAPPING_LOWER_VALUE"
    elif intra_poc > prev_poc and intra_val < prev_vah:
        overlap_tag = "OVERLAPPING_HIGHER_VALUE"
    elif intra_poc < prev_poc and intra_vah > prev_val:
        overlap_tag = "OVERLAPPING_LOWER_VALUE"
    else:
        overlap_tag = "OVERLAPPING_EQUAL_VALUE"

    # 3. POC-Price Divergence
    price_move_atr = of_metrics.get("price_move_atr", 0.0)
    poc_price_divergence = "NONE"
    if price_move_atr > 0.8 and abs(poc_slope) < (0.01 * atr):
        poc_price_divergence = "PRICE_UP_VALUE_FLAT"
    elif price_move_atr < -0.8 and abs(poc_slope) < (0.01 * atr):
        poc_price_divergence = "PRICE_DOWN_VALUE_FLAT"

    # 4. Acceptance vs Rejection
    is_acceptance_above = (bars_above_vah >= 3) and (vol_share_above_vah >= 0.55) and (poc_slope >= 0)
    is_acceptance_below = (bars_below_val >= 3) and (vol_share_below_val >= 0.55) and (poc_slope <= 0)

    is_rejection_above = (price <= intra_vah) and (bars_above_vah > 0 and bars_above_vah < 3)
    is_rejection_below = (price >= intra_val) and (bars_below_val > 0 and bars_below_val < 3)

    # Failed Auction Signals
    auction_signals = []
    if is_rejection_above and of_metrics.get("cvd_change_z", 0) > 0.5:
        auction_signals.append("FAILED_AUCTION_UP")
    if is_rejection_below and of_metrics.get("cvd_change_z", 0) < -0.5:
        auction_signals.append("FAILED_AUCTION_DOWN")

    # 5. Initiative vs Responsive Activity
    activity_type = "NEUTRAL"
    if price < intra_val and is_rejection_below and price >= intra_val:
        activity_type = "RESPONSIVE_BUYING"
    elif price > intra_vah and is_rejection_above and price <= intra_vah:
        activity_type = "RESPONSIVE_SELLING"
    elif price > intra_vah and is_acceptance_above:
        activity_type = "INITIATIVE_BUYING"
    elif price < intra_val and is_acceptance_below:
        activity_type = "INITIATIVE_SELLING"

    # 6. Regime Classifier
    if migration_state == "VALUE_FLAT" and "INSIDE_VALUE" in location_tags:
        regime = "ROTATIONAL_BALANCED"
    elif migration_state == "VALUE_MIGRATION_UP" and price >= intra_poc:
        regime = "TRENDING_UP"
    elif migration_state == "VALUE_MIGRATION_DOWN" and price <= intra_poc:
        regime = "TRENDING_DOWN"
    elif is_acceptance_above:
        regime = "TRANSITION_IMBALANCE_UP"
    elif is_acceptance_below:
        regime = "TRANSITION_IMBALANCE_DOWN"
    elif price > intra_vah and poc_price_divergence == "PRICE_UP_VALUE_FLAT":
        regime = "DISTRIBUTION_DETERIORATION"
    elif price < intra_val and poc_price_divergence == "PRICE_DOWN_VALUE_FLAT":
        regime = "ACCUMULATION_RECOVERY"
    else:
        regime = "DEVELOPING"

    return {
        "location_tags": location_tags,
        "dist_vah_atr": round(dist_vah_atr, 2),
        "dist_val_atr": round(dist_val_atr, 2),
        "dist_poc_atr": round(dist_poc_atr, 2),
        "value_migration": migration_state,
        "overlap_tag": overlap_tag,
        "poc_price_divergence": poc_price_divergence,
        "is_acceptance_above": is_acceptance_above,
        "is_acceptance_below": is_acceptance_below,
        "is_rejection_above": is_rejection_above,
        "is_rejection_below": is_rejection_below,
        "auction_signals": auction_signals,
        "activity_type": activity_type,
        "regime": regime,
    }
