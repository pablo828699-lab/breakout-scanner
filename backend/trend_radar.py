"""
Trend Radar — surface assets that just completed a directional, trending move.

This is a *detection* layer, not a trade generator. For each asset it answers:
"is this in a trend, and did it just do something worth analyzing?"

Two gates, both on the DAILY timeframe, evaluated on the last *completed* candle:

  Gate A — Trend regime (always required)
      * ADX(period) >= adx_min            → there IS a trend (not chop)
      * EMA alignment: price > EMAfast > EMAslow  (up)  / reverse (down)
      * +DI / -DI agrees with the direction

  Gate B — Trigger (at least one, in the trend's direction)
      * Donchian  → close makes a new N-day high (up) / low (down)
      * Impulse   → candle range > mult × ATR with expanded volume and a
                    directional body (a thrust day)

Entry point:
    evaluate_trend_radar(daily_df, ...) -> Optional[dict]
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA)."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def _adx(df: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Wilder ADX with +DI / -DI."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)

    atr = _rma(tr, period)
    plus_di = 100 * _rma(plus_dm, period) / atr.replace(0, np.nan)
    minus_di = 100 * _rma(minus_dm, period) / atr.replace(0, np.nan)
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = _rma(dx, period)
    return adx, plus_di, minus_di


def evaluate_trend_radar(
    daily_df: pd.DataFrame,
    *,
    adx_period: int = 14,
    adx_min: float = 23.0,
    ema_fast: int = 50,
    ema_slow: int = 200,
    donchian_n: int = 20,
    impulse_atr_mult: float = 1.5,
    impulse_volume_mult: float = 1.5,
    roc_period: int = 10,
) -> Optional[dict]:
    """Evaluate the two-gate trend radar on daily data.

    Returns a dict describing the hit, or ``None`` if the asset is not
    trending or did not fire a trigger.
    """
    needed = max(ema_slow, donchian_n, adx_period, roc_period) + 3
    if daily_df.empty or len(daily_df) < needed:
        return None

    close = daily_df["Close"].astype(float)
    high = daily_df["High"].astype(float)
    low = daily_df["Low"].astype(float)
    open_ = daily_df["Open"].astype(float)
    volume = daily_df["Volume"].astype(float)

    ema_f = _ema(close, ema_fast)
    ema_s = _ema(close, ema_slow)
    adx, plus_di, minus_di = _adx(daily_df, adx_period)

    # Last *completed* daily candle.
    i = -2
    px_close = float(close.iloc[i])
    ef = float(ema_f.iloc[i])
    es = float(ema_s.iloc[i])
    adx_val = float(adx.iloc[i])
    pdi = float(plus_di.iloc[i])
    mdi = float(minus_di.iloc[i])

    if not np.isfinite(adx_val) or adx_val < adx_min:
        return None

    # ---- Gate A: trend direction from EMA Stack or price crossing EMA50/200 ----
    # Relaxed: Price just needs to be above EMA50 for LONG (or below for SHORT) and DI indicators agree
    if px_close > ef and pdi > mdi:
        direction = "UP"
    elif px_close < ef and mdi > pdi:
        direction = "DOWN"
    else:
        return None
    
    # We still record if it's a perfect stack for visual verification in logs
    ema_stack = (px_close > ef > es) if direction == "UP" else (px_close < ef < es)

    # ---- Gate B: triggers (must agree with direction) ----
    triggers: list[str] = []

    # Donchian breakout of the prior N completed candles.
    prior_high = float(high.iloc[i - donchian_n : i].max())
    prior_low = float(low.iloc[i - donchian_n : i].min())
    if direction == "UP" and px_close > prior_high:
        triggers.append(f"DONCHIAN_{donchian_n}")
    elif direction == "DOWN" and px_close < prior_low:
        triggers.append(f"DONCHIAN_{donchian_n}")

    # Impulse / thrust candle: range expansion + volume + directional body.
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr_val = float(_rma(tr, adx_period).iloc[i])
    candle_range = float(high.iloc[i] - low.iloc[i])
    vol_sma = float(volume.iloc[i - 20 : i].mean())
    volume_ratio = float(volume.iloc[i] / vol_sma) if vol_sma > 0 else 0.0
    body_up = close.iloc[i] > open_.iloc[i]
    range_ok = atr_val > 0 and candle_range > impulse_atr_mult * atr_val
    vol_ok = volume_ratio >= impulse_volume_mult
    if range_ok and vol_ok:
        if (direction == "UP" and body_up) or (direction == "DOWN" and not body_up):
            triggers.append("IMPULSE")

    if not triggers:
        return None

    roc_pct = float((close.iloc[i] / close.iloc[i - roc_period] - 1.0) * 100.0)
    live_price = float(close.iloc[-1])

    logger.info(
        "RADAR hit — dir=%s, ADX=%.1f, triggers=%s, vol=%.2fx, ROC%d=%.1f%%",
        direction, adx_val, triggers, volume_ratio, roc_period, roc_pct,
    )

    return {
        "direction": direction,
        "price": round(live_price, 6),
        "triggers": triggers,
        "adx": round(adx_val, 1),
        "ema_stack": ema_stack,
        "volume_ratio": round(volume_ratio, 2),
        "roc_pct": round(roc_pct, 2),
        "donchian_n": donchian_n,
    }
