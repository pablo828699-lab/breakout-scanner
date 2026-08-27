"""
Perpetuals Screener & Evaluator Engine for Hyperliquid DEX

3-Phase Quantitative Evaluation with Advanced Features:
- Dynamic Leverage Sizing per Asset Class & ATR Volatility (12x Commodities, 10x Tech Mega-Cap, 8x Crypto Majors, 4-6x High Beta).
- Multi-Timeframe Confluence (1D Macro Trend EMA 21/50 + 1H Intraday Triggers).
- Dual-Direction Scanning (evaluates LONG & SHORT simultaneously).
- Automated Paper Trading Journal (`perp_journal.py`).
- Automatic Telegram Alerts (`telegram_notifier.py`).
"""

from __future__ import annotations

import logging
import time
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.data_fetcher import fetch_candles
from backend.hl_microstructure import get_asset_microstructure, get_tradeable_hl_universe
from backend.perp_journal import add_paper_trade, update_paper_positions
from backend.telegram_notifier import TelegramNotifier
from backend.ticker_mapper import to_hyperliquid_symbol
from backend.volume_profile import analyze_volume_profile

logger = logging.getLogger(__name__)

_notifier = TelegramNotifier(dry_run=True)

COMMODITIES = {
    "GC=F", "GOLD", "SI=F", "SILVER", "CL=F", "CL", "BRENTOIL", "NG=F", "NG", "NATGAS",
    "XYZ:GOLD", "XYZ:SILVER", "XYZ:CL", "XYZ:BRENTOIL", "XYZ:NG"
}
TECH_MEGACAP = {
    "NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META",
    "XYZ:NVDA", "XYZ:MSFT", "XYZ:AAPL", "XYZ:GOOGL", "XYZ:AMZN", "XYZ:META"
}
SEMICONDUCTORS = {
    "SKHX", "MU", "MRVL", "ARM", "INTC", "AMD", "TSM", "AVGO", "QCOM",
    "XYZ:SKHX", "XYZ:MU", "XYZ:MRVL", "XYZ:ARM", "XYZ:INTC", "XYZ:AMD", "XYZ:TSM", "XYZ:AVGO", "XYZ:QCOM"
}
CRYPTO_MAJORS = {
    "BTC", "ETH", "SOL", "HYPE", "BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"
}


def get_asset_sector(ticker: str) -> str:
    """Classify ticker into institutional risk/sector buckets."""
    clean = ticker.strip().upper()
    if clean in COMMODITIES:
        return "COMMODITIES"
    elif clean in TECH_MEGACAP:
        return "TECH_MEGACAP"
    elif clean in SEMICONDUCTORS:
        return "SEMICONDUCTORS"
    elif clean in CRYPTO_MAJORS:
        return "CRYPTO_MAJORS"
    else:
        return "CRYPTO_ALTS"


def get_dynamic_leverage(ticker: str, current_price: float, atr_1h: float, override_leverage: Optional[float] = None) -> float:
    """Calculate dynamic isolated leverage based on asset class and volatility (ATR %).

    Categories (Hyperliquid v4.0 Quantitative Specs):
    - Commodities (GOLD, SILVER, CL): 12x (low vol)
    - Tech Mega-Cap (NVDA, GOOGL, AMZN, MSFT, AAPL, META): 10x
    - Semiconductors & Crypto Majors (BTC, ETH, SOL, HYPE, MU, INTC, AMD): 8x
    - High Beta / Crypto Alts (SPCX, CRCL, SUI, APT, DOGE): 4x - 6x
    """
    if override_leverage is not None and override_leverage > 0 and override_leverage != 5.0:
        return float(override_leverage)

    clean = ticker.strip().upper()
    atr_pct = (atr_1h / current_price) if current_price > 0 else 0.03

    if clean in COMMODITIES:
        return 12.0 if atr_pct <= 0.02 else 10.0
    elif clean in TECH_MEGACAP:
        return 10.0 if atr_pct <= 0.03 else 8.0
    elif clean in SEMICONDUCTORS or clean in CRYPTO_MAJORS:
        return 8.0 if atr_pct <= 0.04 else 6.0
    else:
        # High Beta / Altcoins / Volatile stocks
        if atr_pct <= 0.02:
            return 8.0
        elif atr_pct <= 0.04:
            return 6.0
        elif atr_pct <= 0.07:
            return 5.0
        else:
            return 4.0


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD Line, Signal Line, and Histogram."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate current Average True Range (ATR)."""
    high = df["High"]
    low = df["Low"]
    close_prev = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs()
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(period).mean()
    val = atr_series.iloc[-1] if not atr_series.empty and not np.isnan(atr_series.iloc[-1]) else float((high.iloc[-1] - low.iloc[-1]))
    return max(val, 1e-6)


def evaluate_perp_candidate(
    ticker: str,
    direction: str = "LONG",
    leverage: Optional[float] = None,
    enable_journal_and_alerts: bool = True,
    df_1d: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Execute full 3-phase multi-timeframe evaluation for a target ticker on Hyperliquid perps.

    - Dynamic Leverage: Automatically computed based on asset class & volatility.
    - 1D Macro Trend: EMA 21 vs EMA 50 alignment.
    - 1H Intraday Triggers: Volume Profile (POC/VAH/VAL), RSI, MACD, 1H ATR Barrier.
    - Microstructure: Bulk snapshot, Open Interest, Funding 8h, Orderbook Spread.
    - Risk & Margin: Isolated Margin Liquidation vs Technical SL, R:R >= 2.5.
    """
    direction = direction.upper()
    if direction not in ("LONG", "SHORT"):
        direction = "LONG"

    hl_symbol = to_hyperliquid_symbol(ticker)
    rejection_reasons: List[str] = []

    # ---------------------------------------------------------------------------
    # Fast Track Phase 2: Hyperliquid Microstructure Check (Zero Net Latency)
    # ---------------------------------------------------------------------------
    micro = get_asset_microstructure(ticker)
    phase2_rejections = []

    if not micro:
        phase2_rejections.append(f"Sin snapshot de microestructura en Hyperliquid ({hl_symbol})")
        phase2_passed = False
    else:
        if not micro.get("has_sufficient_liquidity", False):
            phase2_rejections.append(f"Liquidez nocional 24h baja (${micro['volume_24h']:,.0f} < ${micro['min_required_vol']:,.0f})")

        funding_8h = micro.get("funding_8h", 0.0)
        if direction == "LONG" and funding_8h > 0.0005:
            phase2_rejections.append(f"Funding costoso para Long ({funding_8h*100:.4f}% > 0.05%)")
        elif direction == "SHORT" and funding_8h < -0.0005:
            phase2_rejections.append(f"Funding adverso para Short ({funding_8h*100:.4f}%)")

        phase2_passed = len(phase2_rejections) == 0

    if not phase2_passed:
        return {
            "ticker": ticker,
            "hl_symbol": hl_symbol,
            "direction": direction,
            "verdict": "RECHAZADO",
            "primary_reason": phase2_rejections[0],
            "rejection_reasons": phase2_rejections,
            "current_price": micro.get("mark_price", 0.0) if micro else 0.0,
            "poc": 0.0, "vah": 0.0, "val": 0.0, "rsi": 50.0, "rsi_slope": 0.0, "macd_hist": 0.0, "atr": 0.0,
            "leverage": leverage or 5.0, "sl_price": 0.0, "tp_price": 0.0, "estimated_liq_price": 0.0,
            "rr_ratio": 0.0, "order_execution_mode": "MARKET", "microstructure": micro,
            "phase1_passed": False, "phase2_passed": False, "phase3_passed": False
        }

    # ---------------------------------------------------------------------------
    # Data Fetching (1D Macro + 1H Intraday)
    # ---------------------------------------------------------------------------
    if df_1d is None:
        df_1d = fetch_candles(ticker, timeframe="1d", limit=120)
    if df_1h is None:
        df_1h = fetch_candles(ticker, timeframe="1h", limit=200)

    if df_1h is None or df_1h.empty or len(df_1h) < 30:
        return {
            "ticker": ticker,
            "hl_symbol": hl_symbol,
            "direction": direction,
            "verdict": "RECHAZADO",
            "primary_reason": "Datos OHLCV 1H insuficientes o inaccesibles",
            "rejection_reasons": ["Datos OHLCV 1H insuficientes"],
            "phase1_passed": False,
            "phase2_passed": False,
            "phase3_passed": False,
        }

    close_1h = df_1h["Close"].copy()
    current_price = float(close_1h.iloc[-1])
    # Append live mid_price as an unclosed bar so RSI/MACD compare live vs last closed candle
    if micro and micro.get("mid_price", 0) > 0:
        current_price = float(micro["mid_price"])
        close_1h = pd.concat([close_1h, pd.Series([current_price], index=[pd.Timestamp.now(tz="UTC")])])

    atr_1h = calculate_atr(df_1h)

    # Dynamic Leverage calculation
    leverage_val = get_dynamic_leverage(ticker, current_price, atr_1h, override_leverage=leverage)

    # ---------------------------------------------------------------------------
    # Phase 1: Local Technical Analysis & Multi-Timeframe Confluence
    # ---------------------------------------------------------------------------
    phase1_rejections = []

    # 1. 1D Macro Trend Filter (EMA 21 vs EMA 50)
    if df_1d is not None and not df_1d.empty and len(df_1d) >= 50:
        close_1d = df_1d["Close"]
        ema21_1d = float(close_1d.ewm(span=21, adjust=False).mean().iloc[-1])
        ema50_1d = float(close_1d.ewm(span=50, adjust=False).mean().iloc[-1])
        close_1d_last = float(close_1d.iloc[-1])

        if direction == "LONG":
            is_bullish_macro = (close_1d_last > ema21_1d) and (close_1d_last > ema50_1d) and (ema21_1d > ema50_1d)
            if not is_bullish_macro:
                phase1_rejections.append(f"Tendencia Macro 1D no alcista (Close ${close_1d_last:.2f} bajo EMA21 ${ema21_1d:.2f} o EMA50 ${ema50_1d:.2f})")
        else:  # SHORT
            is_bearish_macro = (close_1d_last < ema21_1d) and (close_1d_last < ema50_1d) and (ema21_1d < ema50_1d)
            if not is_bearish_macro:
                phase1_rejections.append(f"Tendencia Macro 1D no bajista (Close ${close_1d_last:.2f} sobre EMA21 ${ema21_1d:.2f} o EMA50 ${ema50_1d:.2f})")

    # 1.5 1H Intraday Trend Alignment (EMA 21)
    ema21_1h = float(close_1h.ewm(span=21, adjust=False).mean().iloc[-1])
    current_close_1h = float(close_1h.iloc[-1])
    if direction == "LONG" and current_close_1h <= ema21_1h:
        phase1_rejections.append(f"Precio 1H bajo media móvil EMA21 (${current_close_1h:.2f} <= ${ema21_1h:.2f})")
    elif direction == "SHORT" and current_close_1h >= ema21_1h:
        phase1_rejections.append(f"Precio 1H sobre media móvil EMA21 (${current_close_1h:.2f} >= ${ema21_1h:.2f})")

    # 2. 1H RSI Filter with Volume Spike Parabolic Exception & Noise Reduction
    rsi_series = calculate_rsi(close_1h)
    current_rsi = float(rsi_series.iloc[-1])
    prev_rsi = float(rsi_series.iloc[-2]) if len(rsi_series) > 1 else current_rsi
    rsi_t2 = float(rsi_series.iloc[-3]) if len(rsi_series) > 2 else prev_rsi
    rsi_slope = current_rsi - prev_rsi
    rsi_t1_slope = prev_rsi - rsi_t2

    vol_1h = df_1h["Volume"]
    vol_sma20 = float(vol_1h.rolling(20).mean().iloc[-1]) if len(vol_1h) >= 20 else float(vol_1h.mean())
    curr_vol = float(vol_1h.iloc[-1])
    is_institutional_vol_spike = (curr_vol >= 1.8 * vol_sma20) if vol_sma20 > 0 else False

    rsi_is_rising = (rsi_t1_slope > 0.0) or (rsi_slope >= 1.5)
    rsi_is_falling = (rsi_t1_slope < 0.0) or (rsi_slope <= -1.5)

    if direction == "LONG":
        if current_rsi >= 70.0 and not is_institutional_vol_spike:
            phase1_rejections.append(f"RSI 1H sobrecomprado ({current_rsi:.1f} >= 70 sin volumen 1.8x SMA20)")
        elif not rsi_is_rising:
            phase1_rejections.append(f"RSI 1H sin pendiente ascendente confirmada ({current_rsi:.1f}, Delta t-1 {rsi_t1_slope:.1f}, live Delta {rsi_slope:.1f})")
    else:  # SHORT
        if current_rsi <= 65.0 and not is_institutional_vol_spike:
            phase1_rejections.append(f"RSI 1H insuficiente para Short ({current_rsi:.1f} <= 65 sin volumen 1.8x SMA20)")
        elif not rsi_is_falling:
            phase1_rejections.append(f"RSI 1H sin pendiente descendente confirmada ({current_rsi:.1f}, Delta t-1 {rsi_t1_slope:.1f}, live Delta {rsi_slope:.1f})")

    # 3. 1H MACD Filter
    _, _, macd_hist = calculate_macd(close_1h)
    curr_hist = float(macd_hist.iloc[-1])
    prev_hist = float(macd_hist.iloc[-2]) if len(macd_hist) > 1 else curr_hist
    hist_delta = curr_hist - prev_hist

    if direction == "LONG":
        if hist_delta <= 0:
            phase1_rejections.append(f"MACD 1H Histograma en caída/deterioro ({curr_hist:.2f}, delta {hist_delta:.2f})")
    else:  # SHORT
        if hist_delta >= 0:
            phase1_rejections.append(f"MACD 1H Histograma en aumento alcista ({curr_hist:.2f}, delta {hist_delta:.2f})")

    # 4. 1H Volume Profile (POC, VAH, VAL)
    vp_res = analyze_volume_profile(df_1h, current_price)
    poc = vp_res.get("poc", current_price)
    vah = vp_res.get("vah", current_price * 1.05)
    val = vp_res.get("val", current_price * 0.95)

    # 5. Barrier Filter (S/R Distance >= Max(5%, 1.5 * ATR_1H))
    barrier_dist_pct = max(0.05, (1.5 * atr_1h) / current_price)
    min_barrier_gap = current_price * barrier_dist_pct

    high_recent = float(df_1h["High"].iloc[-30:].max())
    low_recent = float(df_1h["Low"].iloc[-30:].min())

    if direction == "LONG":
        res_price = min(vah, high_recent) if high_recent > current_price else vah
        gap_to_res = res_price - current_price
        if 0 < gap_to_res < min_barrier_gap:
            phase1_rejections.append(f"Bloqueo Resistencia < {barrier_dist_pct*100:.1f}% ({gap_to_res/current_price*100:.2f}%)")
    else:  # SHORT
        sup_price = max(val, low_recent) if low_recent < current_price else val
        gap_to_sup = current_price - sup_price
        if 0 < gap_to_sup < min_barrier_gap:
            phase1_rejections.append(f"Bloqueo Soporte < {barrier_dist_pct*100:.1f}% ({gap_to_sup/current_price*100:.2f}%)")

    phase1_passed = len(phase1_rejections) == 0
    rejection_reasons.extend(phase1_rejections)

    spread_pct = micro.get("spread_pct", 0.0) if micro else 0.0
    requires_limit = micro.get("requires_limit_order", False) if micro else False

    # ---------------------------------------------------------------------------
    # Phase 3: Risk Manager & Liquidation Math (Volatility-Targeted ATR Sizing)
    # ---------------------------------------------------------------------------
    phase3_rejections = []

    # Dynamic ATR Volatility Sizing: 2.0x ATR_1H (Floor: 0.8% for Commodities/Forex, Cap: 8.0% for High-Beta)
    sl_pct_raw = (2.0 * atr_1h) / current_price if current_price > 0 else 0.05
    sl_pct = max(0.008, min(0.08, sl_pct_raw))
    sl_gap = current_price * sl_pct

    if direction == "LONG":
        sl_price = current_price - sl_gap
        tp_price = current_price + (sl_gap * 2.5)
    else:
        sl_price = current_price + sl_gap
        tp_price = current_price - (sl_gap * 2.5)

    sl_dist = abs(current_price - sl_price)
    tp_dist = abs(tp_price - current_price)
    rr_ratio = tp_dist / sl_dist if sl_dist > 0 else 0.0

    if round(rr_ratio, 2) < 2.50:
        phase3_rejections.append(f"Ratio R:R insuficiente ({rr_ratio:.2f} < 2.5)")

    # Safe Leverage Auto-Tuning (Ensures Estimated Liquidation Distance >= 2.0x SL Distance)
    mmr = 0.05  # 5% Maintenance Margin
    max_safe_leverage = (1.0 - mmr) / (2.0 * sl_pct) if sl_pct > 0 else leverage_val
    if leverage_val > max_safe_leverage:
        # Dynamically calibrate leverage down to the highest safe integer level
        leverage_val = max(1.0, float(int(max_safe_leverage)))

    # Evaluate Isolated Margin Liquidation with Calibrated Leverage
    if direction == "LONG":
        estimated_liq_price = current_price * (1.0 - (1.0 / leverage_val) * (1.0 - mmr))
        liq_dist = current_price - estimated_liq_price
        if estimated_liq_price >= sl_price or liq_dist < (2.0 * sl_dist):
            phase3_rejections.append(
                f"Riesgo de Liquidación prematura (Liq: ${estimated_liq_price:.2f} vs SL: ${sl_price:.2f})"
            )
    else:  # SHORT
        estimated_liq_price = current_price * (1.0 + (1.0 / leverage_val) * (1.0 - mmr))
        liq_dist = estimated_liq_price - current_price
        if estimated_liq_price <= sl_price or liq_dist < (2.0 * sl_dist):
            phase3_rejections.append(
                f"Riesgo de Liquidación prematura (Liq: ${estimated_liq_price:.2f} vs SL: ${sl_price:.2f})"
            )

    phase3_passed = len(phase3_rejections) == 0
    rejection_reasons.extend(phase3_rejections)

    # ---------------------------------------------------------------------------
    # Final Verdict Synthesis (Technical Signal: Phase 1 Macro + Phase 2 Triggers)
    # Risk management & Phase 3 allocation are left to user discretion
    # ---------------------------------------------------------------------------
    verdict = "APROBADO" if (phase1_passed and phase2_passed) else "RECHAZADO"
    primary_reason = "Señal técnica aprobada (Fases 1 y 2)" if verdict == "APROBADO" else rejection_reasons[0]

    order_execution_mode = "MARKET"
    if micro and micro.get("requires_limit_order", False):
        order_execution_mode = f"LIMIT en POC (${poc:.2f})"

    res = {
        "ticker": ticker,
        "hl_symbol": hl_symbol,
        "direction": direction,
        "verdict": verdict,
        "primary_reason": primary_reason,
        "rejection_reasons": rejection_reasons,
        "current_price": current_price,
        "poc": poc,
        "vah": vah,
        "val": val,
        "rsi": current_rsi,
        "rsi_slope": rsi_slope,
        "macd_hist": curr_hist,
        "atr": atr_1h,
        "leverage": leverage_val,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "estimated_liq_price": estimated_liq_price,
        "rr_ratio": rr_ratio,
        "order_execution_mode": order_execution_mode,
        "microstructure": micro,
        "phase1_passed": phase1_passed,
        "phase2_passed": phase2_passed,
        "phase3_passed": phase3_passed,
    }

    if verdict == "APROBADO" and enable_journal_and_alerts:
        _notifier.send_perp_alert(res)
        add_paper_trade(res)

    return res


_perp_scan_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}


def scan_perps_universe(
    tickers: Optional[List[str]] = None,
    leverage: Optional[float] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Dual-Direction Scanning with Dynamic Asset Leverage.

    Evaluates both LONG and SHORT for each ticker.
    If tickers is None or empty, dynamically fetches all liquid, non-meme active perps from Hyperliquid.
    Caches default universe scan results for 60s to ensure instant (<1ms) API responses.
    """
    now = time.time()
    if not tickers and not force_refresh and (now - _perp_scan_cache["timestamp"] < 600.0) and _perp_scan_cache["data"]:
        return _perp_scan_cache["data"]

    if not tickers:
        tickers = get_tradeable_hl_universe()

    approved_longs = []
    approved_shorts = []
    rejected = []
    live_prices = {}

    def _eval_single_ticker(tick: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        res_l, res_s = None, None
        df_1d = fetch_candles(tick, timeframe="1d", limit=120)
        df_1h = fetch_candles(tick, timeframe="1h", limit=200)
        try:
            res_l = evaluate_perp_candidate(tick, direction="LONG", leverage=leverage, df_1d=df_1d, df_1h=df_1h)
        except Exception as exc:
            logger.error("Error evaluating LONG for %s: %s", tick, exc)
        try:
            res_s = evaluate_perp_candidate(tick, direction="SHORT", leverage=leverage, df_1d=df_1d, df_1h=df_1h)
        except Exception as exc:
            logger.error("Error evaluating SHORT for %s: %s", tick, exc)
        return res_l, res_s

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        eval_results = list(executor.map(_eval_single_ticker, tickers))

    for res_long, res_short in eval_results:
        if res_long:
            if res_long.get("current_price", 0) > 0:
                live_prices[res_long["ticker"]] = res_long["current_price"]
            if res_long["verdict"] == "APROBADO":
                approved_longs.append(res_long)
            else:
                rejected.append(res_long)

        if res_short:
            if res_short["verdict"] == "APROBADO":
                approved_shorts.append(res_short)
            else:
                rejected.append(res_short)

    # Quality Rank Score = Volume_24h_Score * R:R Ratio
    def _rank_score(s: Dict[str, Any]) -> float:
        vol = s.get("microstructure", {}).get("day_ntl_vlm", 1.0) if s.get("microstructure") else 1.0
        rr = s.get("rr_ratio", 2.5)
        return float(np.log10(max(1.0, vol)) * rr)

    approved_longs.sort(key=_rank_score, reverse=True)
    approved_shorts.sort(key=_rank_score, reverse=True)

    # Portfolio Heat & Sector Caps: Max 2 Crypto Alts, Max 1 Crypto Major, Max 1 Commodity, Max 1 Tech/Semi
    def _apply_portfolio_heat_cap(setups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sector_caps = {
            "COMMODITIES": 1,
            "TECH_MEGACAP": 1,
            "SEMICONDUCTORS": 1,
            "CRYPTO_MAJORS": 1,
            "CRYPTO_ALTS": 2,
        }
        counts: Dict[str, int] = {k: 0 for k in sector_caps}
        selected = []
        for st in setups:
            sec = get_asset_sector(st.get("ticker", ""))
            if counts.get(sec, 0) < sector_caps.get(sec, 1):
                selected.append(st)
                counts[sec] = counts.get(sec, 0) + 1
        return selected

    # All technically approved setups sorted by volume/RR rank
    diversified_longs = approved_longs
    diversified_shorts = approved_shorts

    # Update paper trading journal with live mark prices
    journal_summary = update_paper_positions(live_prices)

    res_dict = {
        "total_scanned_pairs": len(tickers) * 2,
        "total_approved_longs": len(approved_longs),
        "total_approved_shorts": len(approved_shorts),
        "total_raw_longs": len(approved_longs),
        "total_raw_shorts": len(approved_shorts),
        "total_rejected": len(rejected),
        "approved_longs": approved_longs,
        "approved_shorts": approved_shorts,
        "all_approved_longs": approved_longs,
        "all_approved_shorts": approved_shorts,
        "rejected": rejected,
        "journal_summary": journal_summary,
    }

    _perp_scan_cache["timestamp"] = now
    _perp_scan_cache["data"] = res_dict

    return res_dict
