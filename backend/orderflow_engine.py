"""
Order Flow & CVD Quantitative Analytics Engine.

Calculates continuous normalized metrics, aggression efficiency, absorption vs exhaustion,
CVD divergence, and the 4-quadrant Open Interest exposure matrix.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """Compute rolling z-score safely handling zero-variance slices."""
    if len(series) < 2:
        return pd.Series(0.0, index=series.index)
    rolling_mean = series.rolling(window, min_periods=max(3, window // 4)).mean()
    rolling_std = series.rolling(window, min_periods=max(3, window // 4)).std()
    rolling_std = rolling_std.replace(0.0, np.nan).fillna(1e-6)
    z = (series - rolling_mean) / rolling_std
    return z.fillna(0.0)


def calculate_slope(series: pd.Series, window: int = 5) -> float:
    """Compute linear regression slope over the last `window` points."""
    if len(series) < window or window < 2:
        return 0.0
    y = series.iloc[-window:].to_numpy(dtype=float)
    if np.all(np.isnan(y)) or np.all(y == y[0]):
        return 0.0
    x = np.arange(len(y), dtype=float)
    valid = ~np.isnan(y)
    if np.sum(valid) < 2:
        return 0.0
    slope, _ = np.polyfit(x[valid], y[valid], 1)
    return float(slope)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate rolling Average True Range."""
    high = df["High"]
    low = df["Low"]
    close_prev = df["Close"].shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=max(3, period // 3)).mean().fillna(high - low)


def evaluate_orderflow_metrics(
    df: pd.DataFrame,
    oi_series: Optional[pd.Series] = None,
    atr_window: int = 14,
    lookback: int = 20,
    window_delta: int = 5,
) -> Dict[str, Any]:
    """
    Evaluates order flow dynamics from candle data with volume and delta.
    
    Returns structured continuous metrics:
    - price_move_atr, volume_z, delta_z, cvd_change_z
    - cvd_slope_short, cvd_slope_medium, cvd_acceleration
    - aggression_efficiency, buy_efficiency, sell_efficiency
    - absorption & exhaustion scores (0-100)
    - 4-quadrant OI exposure classification
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # 1. Delta & CVD fallback (if not precomputed, estimate via candle geometry)
    if "Delta" in df.columns:
        delta = df["Delta"]
    else:
        # Classical approximation: (2 * (Close - Low) / (High - Low) - 1) * Volume
        denom = (high - low).replace(0.0, 1e-6)
        cl_ratio = (close - low) / denom
        delta = (2.0 * cl_ratio - 1.0) * volume

    if "CVD" in df.columns:
        cvd = df["CVD"]
    else:
        cvd = delta.cumsum()

    # 2. ATR & Normalized Price Move
    atr_series = calculate_atr(df, atr_window)
    curr_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 1.0
    curr_atr = max(curr_atr, 1e-6)

    n_win = min(window_delta, len(close) - 1) if len(close) > 1 else 1
    price_disp = float(close.iloc[-1] - close.iloc[-1 - n_win]) if len(close) > n_win else 0.0
    price_move_atr = float(price_disp / curr_atr)

    # 3. Z-scores & Slopes
    volume_z_s = calculate_zscore(volume, lookback)
    delta_z_s = calculate_zscore(delta, lookback)
    cvd_diff_s = cvd.diff(n_win).fillna(0.0)
    cvd_change_z_s = calculate_zscore(cvd_diff_s, lookback)

    volume_z = float(volume_z_s.iloc[-1])
    delta_z = float(delta_z_s.iloc[-1])
    cvd_change_z = float(cvd_change_z_s.iloc[-1])

    cvd_slope_short = calculate_slope(cvd, window=min(5, len(cvd)))
    cvd_slope_med = calculate_slope(cvd, window=min(14, len(cvd)))
    cvd_acceleration = float(cvd_slope_short - cvd_slope_med)

    # 4. Aggression Efficiency (Displacement / Aggression)
    mean_abs_delta = float(delta.abs().rolling(lookback, min_periods=3).mean().iloc[-1]) if len(delta) >= 3 else 1.0
    mean_abs_delta = max(mean_abs_delta, 1e-6)

    cvd_disp_val = float(cvd.iloc[-1] - cvd.iloc[-1 - n_win]) if len(cvd) > n_win else 0.0
    norm_cvd_disp = abs(cvd_disp_val) / mean_abs_delta
    aggression_efficiency = float(abs(price_move_atr) / max(norm_cvd_disp, 0.05))

    # Directional efficiencies
    pos_price = max(0.0, price_disp)
    pos_cvd = max(0.0, cvd_disp_val)
    neg_price = abs(min(0.0, price_disp))
    neg_cvd = abs(min(0.0, cvd_disp_val))

    buy_efficiency = float((pos_price / curr_atr) / max(pos_cvd / mean_abs_delta, 0.05)) if pos_cvd > 0 else 0.0
    sell_efficiency = float((neg_price / curr_atr) / max(neg_cvd / mean_abs_delta, 0.05)) if neg_cvd > 0 else 0.0

    # 5. Open Interest Matrix
    oi_change_pct = 0.0
    oi_change_z = 0.0
    if oi_series is not None and len(oi_series) >= 2:
        oi_pct_series = oi_series.pct_change().fillna(0.0)
        oi_change_pct = float((oi_series.iloc[-1] - oi_series.iloc[-1 - min(n_win, len(oi_series)-1)]) / max(oi_series.iloc[0], 1e-6))
        oi_change_z = float(calculate_zscore(oi_pct_series, lookback).iloc[-1])

    # 6. Classification of OI & Aggression Matrix
    oi_classification = "NEUTRAL"
    oi_confidence = 50.0

    if price_move_atr > 0.4 and cvd_change_z > 0.6:
        if oi_change_pct > 0.005 or oi_change_z > 0.5:
            oi_classification = "INITIATIVE_BUYING_NEW_EXPOSURE"
            oi_confidence = float(np.clip(60.0 + oi_change_z * 15.0, 50.0, 95.0))
        elif oi_change_pct < -0.005 or oi_change_z < -0.5:
            oi_classification = "SHORT_COVERING_SQUEEZE"
            oi_confidence = float(np.clip(60.0 + abs(oi_change_z) * 15.0, 50.0, 95.0))
    elif price_move_atr < -0.4 and cvd_change_z < -0.6:
        if oi_change_pct > 0.005 or oi_change_z > 0.5:
            oi_classification = "INITIATIVE_SELLING_NEW_EXPOSURE"
            oi_confidence = float(np.clip(60.0 + oi_change_z * 15.0, 50.0, 95.0))
        elif oi_change_pct < -0.005 or oi_change_z < -0.5:
            oi_classification = "LONG_LIQUIDATION_SQUEEZE"
            oi_confidence = float(np.clip(60.0 + abs(oi_change_z) * 15.0, 50.0, 95.0))
    elif price_move_atr >= -0.35 and cvd_change_z < -1.0:
        # Aggressive selling without proportional downward displacement -> Buyer absorption
        oi_classification = "BUYER_ABSORPTION_CANDIDATE"
        oi_confidence = float(np.clip(70.0 + abs(cvd_change_z) * 10.0, 60.0, 95.0))
    elif price_move_atr <= 0.35 and cvd_change_z > 1.0:
        # Aggressive buying without proportional upward displacement -> Seller absorption
        oi_classification = "SELLER_ABSORPTION_CANDIDATE"
        oi_confidence = float(np.clip(70.0 + abs(cvd_change_z) * 10.0, 60.0, 95.0))

    # 7. Absorption & Exhaustion Scores (0-100)
    # Seller Absorption: Positive CVD extreme + Low price displacement + High volume
    seller_abs_score = float(np.clip(
        (0.40 * max(0.0, cvd_change_z / 2.5) +
         0.35 * max(0.0, 1.0 - min(1.0, buy_efficiency)) +
         0.25 * max(0.0, volume_z / 2.5)) * 100.0,
        0.0, 100.0
    ))

    # Buyer Absorption: Negative CVD extreme + Low downward displacement + High volume
    buyer_abs_score = float(np.clip(
        (0.40 * max(0.0, -cvd_change_z / 2.5) +
         0.35 * max(0.0, 1.0 - min(1.0, sell_efficiency)) +
         0.25 * max(0.0, volume_z / 2.5)) * 100.0,
        0.0, 100.0
    ))

    # Buyer Exhaustion: Price extended but CVD acceleration declining sharply
    buyer_exh_score = float(np.clip(
        (0.60 * max(0.0, -cvd_acceleration / (mean_abs_delta + 1e-6)) +
         0.40 * max(0.0, (price_move_atr - 0.5) / 1.5)) * 100.0,
        0.0, 100.0
    ))

    # Seller Exhaustion: Price dumping but selling momentum drying up
    seller_exh_score = float(np.clip(
        (0.60 * max(0.0, cvd_acceleration / (mean_abs_delta + 1e-6)) +
         0.40 * max(0.0, (-price_move_atr - 0.5) / 1.5)) * 100.0,
        0.0, 100.0
    ))

    # 8. CVD Divergence Detection
    cvd_div = "NONE"
    if len(close) >= 10:
        price_hh = close.iloc[-1] > close.iloc[-10:-1].max()
        cvd_lh = cvd.iloc[-1] < cvd.iloc[-10:-1].max()
        price_ll = close.iloc[-1] < close.iloc[-10:-1].min()
        cvd_hl = cvd.iloc[-1] > cvd.iloc[-10:-1].min()

        if price_hh and cvd_lh:
            cvd_div = "BEARISH_CVD_DIVERGENCE"
        elif price_ll and cvd_hl:
            cvd_div = "BULLISH_CVD_DIVERGENCE"

    return {
        "price_move_atr": round(price_move_atr, 2),
        "volume_z": round(volume_z, 2),
        "delta_z": round(delta_z, 2),
        "cvd_change_z": round(cvd_change_z, 2),
        "cvd_slope_short": round(cvd_slope_short, 4),
        "cvd_slope_medium": round(cvd_slope_med, 4),
        "cvd_acceleration": round(cvd_acceleration, 4),
        "aggression_efficiency": round(aggression_efficiency, 2),
        "buy_efficiency": round(buy_efficiency, 2),
        "sell_efficiency": round(sell_efficiency, 2),
        "oi_change_pct": round(oi_change_pct * 100.0, 2),
        "oi_change_z": round(oi_change_z, 2),
        "oi_classification": oi_classification,
        "oi_confidence": round(oi_confidence, 1),
        "seller_absorption_score": round(seller_abs_score, 1),
        "buyer_absorption_score": round(buyer_abs_score, 1),
        "buyer_exhaustion_score": round(buyer_exh_score, 1),
        "seller_exhaustion_score": round(seller_exh_score, 1),
        "cvd_divergence": cvd_div,
        "atr": round(curr_atr, 4),
    }


def analyze_orderflow_and_auction(
    symbol: str,
    df_1h: pd.DataFrame,
    oi_series: Optional[pd.Series] = None,
    market: str = "CRYPTO",
) -> Dict[str, Any]:
    """
    Master orchestrator: Evaluates continuous order flow, dual volume profiles,
    auction regime, composite 0-100 scores, and generates the institutional market story.
    """
    from backend.auction_regime import compute_dual_session_profiles, evaluate_auction_context
    from backend.orderflow_models import compute_composite_scores, generate_market_story, OrderFlowReport

    if df_1h.empty or len(df_1h) < 5:
        return {
            "symbol": symbol,
            "market": market,
            "regime": "INSUFFICIENT_DATA",
            "scores": {},
            "metrics": {},
            "market_story": "Datos insuficientes para evaluación de microestructura.",
        }

    current_price = float(df_1h["Close"].iloc[-1])
    of_metrics = evaluate_orderflow_metrics(df_1h, oi_series=oi_series)
    of_metrics["current_price"] = round(current_price, 4)
    profiles = compute_dual_session_profiles(df_1h, session_bars=24)
    auc_context = evaluate_auction_context(current_price, profiles, of_metrics)
    scores = compute_composite_scores(of_metrics, auc_context)
    market_story = generate_market_story(symbol, of_metrics, auc_context, scores)

    # Compile list of active signals
    signals = []
    if scores.get("buyer_absorption", 0) >= 65.0:
        signals.append("BUYER_ABSORPTION")
    if scores.get("seller_absorption", 0) >= 65.0:
        signals.append("SELLER_ABSORPTION")
    if scores.get("trapped_shorts", 0) >= 65.0:
        signals.append("POTENTIAL_TRAPPED_SHORTS")
    if scores.get("trapped_longs", 0) >= 65.0:
        signals.append("POTENTIAL_TRAPPED_LONGS")
    if scores.get("initiative_buying", 0) >= 70.0:
        signals.append("INITIATIVE_BUYING")
    if scores.get("initiative_selling", 0) >= 70.0:
        signals.append("INITIATIVE_SELLING")
    if auc_context.get("value_migration") != "VALUE_FLAT":
        signals.append(auc_context["value_migration"])
    if of_metrics.get("cvd_divergence") != "NONE":
        signals.append(of_metrics["cvd_divergence"])

    # Extract last 20 bars for native visual sparklines
    last_20 = df_1h.tail(20)
    sparkline_price = [round(float(p), 4) for p in last_20["Close"].tolist()] if "Close" in last_20 else []
    sparkline_cvd = [round(float(c), 2) for c in last_20["CVD"].tolist()] if "CVD" in last_20 else []

    # Smart Multi-Module Confluence A+ Rules
    is_confluence_a_plus = False
    confluence_tags = []

    # A+ Rule 1: Capitulation Reversal (Extreme Selling Absorption at Value Support)
    if scores.get("buyer_absorption", 0) >= 70.0 and ("INSIDE_VALUE" in auc_context.get("location_tags", []) or "NEAR_INTRADAY_VAL" in auc_context.get("location_tags", [])):
        is_confluence_a_plus = True
        confluence_tags.append("CAPITULATION_ABSORPTION_REVERSAL")

    # A+ Rule 2: High Conviction Short Squeeze (Trapped Shorts + Heavy Aggression Absorption)
    if scores.get("trapped_shorts", 0) >= 70.0:
        is_confluence_a_plus = True
        confluence_tags.append("SHORT_SQUEEZE_HIGH_CONVICTION")

    # A+ Rule 3: Initiative Breakout with Value Expansion
    if scores.get("initiative_buying", 0) >= 70.0 and auc_context.get("value_migration") == "VALUE_MIGRATING_UP":
        is_confluence_a_plus = True
        confluence_tags.append("INITIATIVE_VALUE_EXPANSION")

    report = OrderFlowReport(
        symbol=symbol,
        market=market,
        regime=auc_context["regime"],
        activity_type=auc_context["activity_type"],
        location=auc_context["location_tags"],
        signals=signals,
        metrics={**of_metrics, **profiles, **{k: v for k, v in auc_context.items() if k not in ("location_tags", "regime", "activity_type")}},
        scores=scores,
        market_story=market_story,
        sparkline_price=sparkline_price,
        sparkline_cvd=sparkline_cvd,
        confluence_a_plus=is_confluence_a_plus,
        confluence_tags=confluence_tags,
    )

    return {
        "symbol": report.symbol,
        "market": report.market,
        "regime": report.regime,
        "activity_type": report.activity_type,
        "location": report.location,
        "signals": report.signals,
        "metrics": report.metrics,
        "scores": report.scores,
        "market_story": report.market_story,
        "sparkline_price": report.sparkline_price,
        "sparkline_cvd": report.sparkline_cvd,
        "confluence_a_plus": report.confluence_a_plus,
        "confluence_tags": report.confluence_tags,
    }

