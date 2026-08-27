"""
Momentum & Trend Acceleration Engine.

Identifies assets experiencing explosive directional momentum using:
1. TTM Squeeze (Bollinger Bands vs Keltner Channels compression & expansion)
2. Relative Volume (RVOL >= 1.5x vs 20-day SMA)
3. Rate of Change (ROC 10-period momentum acceleration)
4. Fast EMA Ribbon alignment (EMA 9 / 21 / 50)
5. Asymmetric Risk Management (Tight SL below EMA9 / structural low, Target at 1:2.5+ R:R)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.models import MomentumSignal

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOMENTUM_SIGNALS_FILE = _PROJECT_ROOT / "backend" / "momentum_signals.json"

# Asset categorization sets
COMMODITY_TICKERS = {'GLD', 'SLV', 'USO', 'UNG', 'PPLT', 'CPER', 'GOLD', 'SILVER', 'BRENTOIL', 'NATGAS', 'PLATINUM', 'COPPER'}
INDEX_TICKERS = {'SPY', 'EWJ', 'EWY', 'SOXL', 'SPCX', 'SP500', 'JP225', 'KR200', 'XYZ100'}
FOREX_TICKERS = {'FXE', 'FXY', 'EUR', 'JPY'}


def get_asset_class(ticker: str, market: str) -> str:
    clean = ticker.upper().replace('XYZ:', '').replace('USDT', '').replace('PERP', '')
    if clean in COMMODITY_TICKERS:
        return 'MATERIAS_PRIMAS'
    if clean in INDEX_TICKERS:
        return 'INDICES'
    if clean in FOREX_TICKERS:
        return 'FOREX'
    if market == 'CRYPTO' or ticker.endswith('USDT'):
        return 'CRIPTO'
    return 'ACCIONES'


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_bollinger_and_keltner(df: pd.DataFrame, period: int = 20) -> Dict[str, pd.Series]:
    close = df['Close']
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    bb_upper = sma + (2.0 * std)
    bb_lower = sma - (2.0 * std)

    atr = calculate_atr(df, period=period)
    kc_upper = sma + (1.5 * atr)
    kc_lower = sma - (1.5 * atr)

    squeeze_on = (bb_upper < kc_upper) & (bb_lower > kc_lower)
    return {
        'sma': sma,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'kc_upper': kc_upper,
        'kc_lower': kc_lower,
        'squeeze_on': squeeze_on,
    }


def evaluate_momentum(
    daily_df: pd.DataFrame,
    ticker: str,
    market: str = "US_EQUITIES"
) -> Optional[MomentumSignal]:
    """Evaluates whether an asset qualifies for a high-conviction Momentum breakout."""
    if daily_df is None or len(daily_df) < 55:
        return None

    df = daily_df.copy()
    close = df['Close']
    volume = df['Volume']
    high = df['High']
    low = df['Low']

    # 1. Moving Averages (EMA 9, 21, 50, 200)
    ema_9 = close.ewm(span=9, adjust=False).mean()
    ema_21 = close.ewm(span=21, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean() if len(df) >= 200 else ema_50

    curr_close = float(close.iloc[-1])
    curr_ema9 = float(ema_9.iloc[-1])
    curr_ema21 = float(ema_21.iloc[-1])
    curr_ema50 = float(ema_50.iloc[-1])
    curr_ema200 = float(ema_200.iloc[-1])

    # 2. Volume Ratio vs 20d SMA
    vol_sma20 = volume.rolling(window=20).mean()
    rvol = float(volume.iloc[-1] / vol_sma20.iloc[-1]) if vol_sma20.iloc[-1] > 0 else 1.0

    # 3. Rate of Change (10-bar % change)
    roc_10 = float(((curr_close - close.iloc[-11]) / close.iloc[-11]) * 100) if len(close) >= 11 else 0.0

    # 4. RSI (14)
    rsi_series = calculate_rsi(close, period=14)
    curr_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    # 5. Squeeze Status
    sq_data = calculate_bollinger_and_keltner(df, period=20)
    sq_on_series = sq_data['squeeze_on']
    
    is_sq_on = bool(sq_on_series.iloc[-1])
    sq_fired_recently = (not is_sq_on) and any(sq_on_series.iloc[-4:-1])

    # 6. Evaluation Logic (LONG vs SHORT)
    is_crypto = (market == "CRYPTO" or ticker.endswith("USDT"))
    min_roc = 4.0 if is_crypto else 2.5
    min_rvol = 1.35

    is_long = False
    is_short = False
    trigger = "MOMENTUM_ACCELERATION"
    squeeze_status = "SQUEEZE_ON" if is_sq_on else "EXPANSION"

    # Bullish Momentum Check
    bullish_ema_stack = (curr_close > curr_ema9 > curr_ema21 > curr_ema50)
    if bullish_ema_stack and (roc_10 >= min_roc) and (rvol >= min_rvol) and (52.0 <= curr_rsi <= 80.0):
        is_long = True
        if sq_fired_recently:
            trigger = "SQUEEZE_BREAKOUT"
            squeeze_status = "FIRED_BULLISH"
        elif rvol >= 1.8:
            trigger = "INSTITUTIONAL_IMPULSE"

    # Bearish Momentum Check (Shorts)
    bearish_ema_stack = (curr_close < curr_ema9 < curr_ema21 < curr_ema50)
    if not is_long and bearish_ema_stack and (roc_10 <= -min_roc) and (rvol >= min_rvol) and (20.0 <= curr_rsi <= 48.0):
        is_short = True
        if sq_fired_recently:
            trigger = "SQUEEZE_BREAKDOWN"
            squeeze_status = "FIRED_BEARISH"
        elif rvol >= 1.8:
            trigger = "INSTITUTIONAL_IMPULSE"

    if not is_long and not is_short:
        return None

    # 7. Risk Management & Levels
    atr_val = float(calculate_atr(df, 14).iloc[-1])
    recent_low = float(low.iloc[-3:].min())
    recent_high = float(high.iloc[-3:].max())

    if is_long:
        direction = "LONG"
        # Stop loss below recent low or EMA9, with safety buffer
        stop_loss = max(recent_low, curr_ema9 - (0.3 * atr_val))
        if stop_loss >= curr_close:
            stop_loss = curr_close - (1.2 * atr_val)
        risk = curr_close - stop_loss
        take_profit = curr_close + (2.5 * risk)
        rr_ratio = 2.5
    else:
        direction = "SHORT"
        stop_loss = min(recent_high, curr_ema9 + (0.3 * atr_val))
        if stop_loss <= curr_close:
            stop_loss = curr_close + (1.2 * atr_val)
        risk = stop_loss - curr_close
        take_profit = curr_close - (2.5 * risk)
        rr_ratio = 2.5

    # Confidence score (0.0 - 1.0)
    confidence = 0.70
    if rvol >= 1.8:
        confidence += 0.10
    if sq_fired_recently:
        confidence += 0.10
    if abs(roc_10) >= (min_roc * 1.5):
        confidence += 0.05
    confidence = min(0.95, confidence)

    # Analysis summary
    dir_label = "alcista" if is_long else "bajista"
    summary = (
        f"Impulso {dir_label} de alta velocidad | ROC(10): {roc_10:+.1f}% | "
        f"RVOL: {rvol:.2f}x | RSI: {curr_rsi:.1f} | Estado: {squeeze_status} | "
        f"R:R = 1:{rr_ratio:.1f} | Confianza: {int(confidence * 100)}%"
    )

    asset_class = get_asset_class(ticker, market)

    return MomentumSignal(
        ticker=ticker,
        market=market,
        direction=direction,
        trigger=trigger,
        entry_price=round(curr_close, 4 if is_crypto else 2),
        stop_loss=round(stop_loss, 4 if is_crypto else 2),
        take_profit=round(take_profit, 4 if is_crypto else 2),
        rr_ratio=rr_ratio,
        rvol=round(rvol, 2),
        roc_10=round(roc_10, 2),
        rsi=round(curr_rsi, 1),
        squeeze_status=squeeze_status,
        ema_stack=(bullish_ema_stack if is_long else bearish_ema_stack),
        confidence_score=round(confidence, 2),
        analysis_summary=summary,
        timestamp=datetime.now(timezone.utc),
        asset_class=asset_class
    )


def save_momentum_signals(signals: List[MomentumSignal]) -> None:
    """Persists momentum signals to backend/momentum_signals.json."""
    data = []
    for s in signals:
        data.append({
            "ticker": s.ticker,
            "market": s.market,
            "direction": s.direction,
            "trigger": s.trigger,
            "entry_price": s.entry_price,
            "stop_loss": s.stop_loss,
            "take_profit": s.take_profit,
            "rr_ratio": s.rr_ratio,
            "rvol": s.rvol,
            "roc_10": s.roc_10,
            "rsi": s.rsi,
            "squeeze_status": s.squeeze_status,
            "ema_stack": s.ema_stack,
            "confidence_score": s.confidence_score,
            "analysis_summary": s.analysis_summary,
            "timestamp": s.timestamp.isoformat(),
            "asset_class": s.asset_class
        })
    try:
        with open(MOMENTUM_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d momentum signals to %s", len(data), MOMENTUM_SIGNALS_FILE)
    except Exception as exc:
        logger.error("Failed saving momentum signals: %s", exc)


def load_momentum_signals() -> List[Dict]:
    """Loads saved momentum signals from disk."""
    if not MOMENTUM_SIGNALS_FILE.exists():
        return []
    try:
        with open(MOMENTUM_SIGNALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed loading momentum signals: %s", exc)
        return []
