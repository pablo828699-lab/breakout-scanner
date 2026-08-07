"""
Capitulation Engine — orchestrates the 4 analysis modules into a single
pipeline that produces AsymmetricSignal results.

Flow:
  1. Shock Detector  →  gate (drop >= 2%)
  2. Price Structure →  SMC analysis (MSB, FVG, OB)
  3. Volume Profile  →  POC, VA, HVN/LVN
  4. Fundamental     →  solvency (equities) / correlation (crypto)
  5. Trade Model     →  entry, SL, TP, sizing, verdict
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

from backend.models import AsymmetricSignal
from backend.shock_detector import scan_for_shocks, classify_shock, ShockResult
from backend.price_structure import analyze_price_structure
from backend.volume_profile import analyze_volume_profile
from backend.fundamental_filter import run_fundamental_filter
from backend.asymmetric_trade import (
    calculate_entry_trigger,
    calculate_asymmetric_levels,
    calculate_position_size,
    calculate_confidence_score,
    build_analysis_summary,
    DEFAULT_RISK_PCT,
)
from backend.risk_manager import calculate_atr

logger = logging.getLogger(__name__)

COMMODITY_TICKERS = {"GLD", "SLV", "USO", "UNG", "PPLT", "CPER", "GOLD", "SILVER", "BRENTOIL", "NATGAS", "PLATINUM", "COPPER"}
INDEX_TICKERS = {"SPY", "EWJ", "EWY", "SOXL", "SPCX", "SP500", "JP225", "KR200", "XYZ100"}
FOREX_TICKERS = {"FXE", "FXY", "EUR", "JPY"}


def determine_asset_class(ticker: str, market: str) -> str:
    """Categorize a ticker into ACCIONES, MATERIAS_PRIMAS, INDICES, FOREX, or CRIPTO."""
    t_clean = ticker.replace("xyz:", "").upper()
    if market == "CRYPTO" or ticker.endswith("USDT") or t_clean in ("BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "NEAR", "ZEC", "XMR", "UNI", "ENA", "ONDO", "WLD", "ACE", "PAXG", "LIT", "XPL", "PUMP", "CASHCAT"):
        return "CRIPTO"
    elif t_clean in COMMODITY_TICKERS:
        return "MATERIAS_PRIMAS"
    elif t_clean in INDEX_TICKERS:
        return "INDICES"
    elif t_clean in FOREX_TICKERS:
        return "FOREX"
    else:
        return "ACCIONES"


def analyze_capitulation(
    ticker: str,
    market: str,
    daily_df: pd.DataFrame,
    hourly_df: pd.DataFrame,
    capital: float = 100_000.0,
    benchmark_df: Optional[pd.DataFrame] = None,
    shock_threshold: float = -0.02,
) -> Optional[AsymmetricSignal]:
    """Run the full capitulation analysis pipeline for a single asset.

    Parameters
    ----------
    ticker : str
        Asset symbol (e.g. 'AAPL', 'BTCUSDT').
    market : str
        'US_EQUITIES' or 'CRYPTO'.
    daily_df : pd.DataFrame
        Daily OHLCV with at least 200 rows.
    hourly_df : pd.DataFrame
        Hourly OHLCV with at least 5 days.
    capital : float
        Account capital for position sizing.
    benchmark_df : pd.DataFrame, optional
        Daily OHLCV for the benchmark (SPY or BTCUSDT).
    shock_threshold : float
        Minimum daily drop to qualify (default: -2%).

    Returns
    -------
    AsymmetricSignal or None
    """
    logger.info("═══ Capitulation analysis started for %s (%s) ═══", ticker, market)

    # ──────────────────────────────────────────────────────────
    # GATE 0: 24h Dollar Volume Liquidity Filter ($800k USD min)
    # ──────────────────────────────────────────────────────────
    try:
        last_close = float(daily_df["Close"].iloc[-1])
        last_volume = float(daily_df["Volume"].iloc[-1])
        dollar_volume_24h = last_close * last_volume
        if dollar_volume_24h < cfg.MIN_24H_VOLUME_USD:
            logger.info(
                "%s — 24h USD volume ($%.0f) below minimum threshold ($%.0f USD). Skipping.",
                ticker, dollar_volume_24h, cfg.MIN_24H_VOLUME_USD,
            )
            return None
    except Exception as exc:
        logger.debug("%s — failed evaluating 24h dollar volume: %s", ticker, exc)

    # ──────────────────────────────────────────────────────────
    # GATE 1: Shock Detection
    # ──────────────────────────────────────────────────────────
    shock = scan_for_shocks(daily_df, ticker, shock_threshold)
    if shock is None:
        logger.info("%s — no shock detected (drop < %.0f%%). Skipping.", ticker, abs(shock_threshold) * 100)
        return None

    # Classify as idiosyncratic vs systemic
    if benchmark_df is not None:
        shock = classify_shock(shock, benchmark_df, daily_df=daily_df)

    logger.info(
        "%s SHOCK: drop=%.2f%%, idiosyncratic=%s, cap_low=%.4f, vol_ratio=%.2fx",
        ticker, shock.drop_pct * 100, shock.is_idiosyncratic,
        shock.capitulation_low, shock.capitulation_volume_ratio,
    )

    # ──────────────────────────────────────────────────────────
    # MODULE 2: Price Structure (SMC)
    # ──────────────────────────────────────────────────────────
    try:
        structure = analyze_price_structure(daily_df, hourly_df)
    except Exception as exc:
        logger.error("%s — price structure analysis failed: %s", ticker, exc)
        structure = {
            "msb_1d": [], "msb_4h": [], "fvg_1d": [], "fvg_4h": [],
            "ob_1d": [], "ob_4h": [], "confluence_zones": [],
        }

    logger.info(
        "%s STRUCTURE: msb_1d=%d, fvg_1d=%d, ob_1d=%d, confluence=%d",
        ticker,
        len(structure.get("msb_1d", [])),
        len(structure.get("fvg_1d", [])),
        len(structure.get("ob_1d", [])),
        len(structure.get("confluence_zones", [])),
    )

    # ──────────────────────────────────────────────────────────
    # MODULE 3: Volume Profile
    # ──────────────────────────────────────────────────────────
    current_price = float(daily_df["Close"].iloc[-1])

    try:
        profile = analyze_volume_profile(hourly_df, current_price, lookback_days=20)
    except Exception as exc:
        logger.error("%s — volume profile analysis failed: %s", ticker, exc)
        profile = {
            "poc": current_price, "vah": current_price * 1.05,
            "val": current_price * 0.95, "hvn_zones": [], "lvn_zones": [],
            "price_vs_va": "unknown",
        }

    logger.info(
        "%s VOLUME PROFILE: POC=%.4f, VAH=%.4f, VAL=%.4f, price_vs_va=%s",
        ticker, profile["poc"], profile["vah"], profile["val"],
        profile["price_vs_va"],
    )

    # ──────────────────────────────────────────────────────────
    # MODULE 4: Fundamental Filter
    # ──────────────────────────────────────────────────────────
    try:
        fundamental = run_fundamental_filter(
            ticker, market,
            daily_df=daily_df,
            benchmark_df=benchmark_df,
        )
    except Exception as exc:
        logger.error("%s — fundamental filter failed: %s", ticker, exc)
        fundamental = {"passed": True, "market": market, "details": {}}

    if not fundamental.get("passed", True):
        logger.info(
            "%s FUNDAMENTAL FILTER: FAILED — %s. Marking as EVITAR.",
            ticker, fundamental.get("details", {}).get("risk_flags", []),
        )
        # Still generate the signal but with EVITAR verdict
        return _build_evitar_signal(ticker, market, shock, structure, profile, fundamental)

    logger.info("%s FUNDAMENTAL FILTER: PASSED", ticker)

    # ──────────────────────────────────────────────────────────
    # MODULE 5: Trade Model (R:R >= 1:3)
    # ──────────────────────────────────────────────────────────
    # Calculate ATR from hourly data
    atr_value = calculate_atr(hourly_df, period=14) if len(hourly_df) > 15 else current_price * 0.02

    # Determine entry trigger
    entry_trigger = calculate_entry_trigger(
        current_price=current_price,
        confluence_zones=structure.get("confluence_zones", []),
        fvg_zones=structure.get("fvg_1d", []) + structure.get("fvg_4h", []),
        ob_zones=structure.get("ob_1d", []) + structure.get("ob_4h", []),
        poc=profile["poc"],
        val=profile["val"],
        capitulation_low=shock.capitulation_low,
    )

    entry_price = entry_trigger["entry_price"]

    # Calculate SL, TP, R:R
    levels = calculate_asymmetric_levels(
        entry_price=entry_price,
        capitulation_low=shock.capitulation_low,
        atr_value=atr_value,
        poc=profile["poc"],
        vah=profile["vah"],
        fvg_targets=structure.get("fvg_1d", []),
    )

    if levels is None:
        logger.info("%s — no valid R:R >= 3.0 achievable. Verdict: EVITAR.", ticker)
        return _build_evitar_signal(ticker, market, shock, structure, profile, fundamental)

    # Position sizing
    qty = calculate_position_size(capital, DEFAULT_RISK_PCT, entry_price, levels["stop_loss"])

    # Confidence score
    shock_dict = {
        "drop_pct": shock.drop_pct,
        "is_idiosyncratic": shock.is_idiosyncratic,
        "capitulation_volume_ratio": shock.capitulation_volume_ratio,
    }
    confidence = calculate_confidence_score(shock_dict, structure, profile, fundamental)

    # Analysis summary
    summary = build_analysis_summary(
        ticker, shock_dict, entry_trigger, levels, structure, profile, fundamental, confidence,
    )

    # Determine MSB type
    msb_list = structure.get("msb_1d", [])
    msb_type = msb_list[-1]["type"] + "_reversal" if msb_list else "no_msb"

    # Select the most relevant FVG and OB zones
    bullish_fvgs = [f for f in structure.get("fvg_1d", []) if f.get("type") == "bullish"]
    best_fvg = (bullish_fvgs[-1]["low"], bullish_fvgs[-1]["high"]) if bullish_fvgs else (0.0, 0.0)
    bullish_obs = [o for o in structure.get("ob_1d", []) if o.get("type") == "bullish"]
    best_ob = (bullish_obs[-1]["low"], bullish_obs[-1]["high"]) if bullish_obs else (0.0, 0.0)

    signal = AsymmetricSignal(
        ticker=ticker,
        market=market,
        verdict="APTO_COMPRA_ASIMETRICA",
        drop_pct=shock.drop_pct,
        entry_price=round(entry_price, 6),
        stop_loss=levels["stop_loss"],
        take_profit=levels["take_profit"],
        rr_ratio=levels["rr_ratio"],
        position_size_qty=qty,
        poc=round(profile["poc"], 6),
        vah=round(profile["vah"], 6),
        val=round(profile["val"], 6),
        fvg_zone=best_fvg,
        ob_zone=best_ob,
        msb_type=msb_type,
        is_idiosyncratic=shock.is_idiosyncratic,
        fundamental_ok=fundamental.get("passed", True),
        confidence_score=confidence,
        analysis_summary=summary,
        timestamp=datetime.now(tz=timezone.utc),
        asset_class=determine_asset_class(ticker, market),
    )

    logger.info(
        "✅ %s VERDICT: %s [%s] | Entry=%.4f, SL=%.4f, TP=%.4f, R:R=1:%.1f, Confidence=%.0f%%",
        ticker, signal.verdict, signal.asset_class, signal.entry_price, signal.stop_loss,
        signal.take_profit, signal.rr_ratio, signal.confidence_score * 100,
    )

    return signal


def _build_evitar_signal(
    ticker: str,
    market: str,
    shock: ShockResult,
    structure: dict,
    profile: dict,
    fundamental: dict,
) -> AsymmetricSignal:
    """Build a signal with EVITAR verdict (for tracking/logging purposes)."""
    return AsymmetricSignal(
        ticker=ticker,
        market=market,
        verdict="EVITAR",
        drop_pct=shock.drop_pct,
        entry_price=0.0,
        stop_loss=0.0,
        take_profit=0.0,
        rr_ratio=0.0,
        position_size_qty=0.0,
        poc=round(profile.get("poc", 0.0), 6),
        vah=round(profile.get("vah", 0.0), 6),
        val=round(profile.get("val", 0.0), 6),
        fvg_zone=(0.0, 0.0),
        ob_zone=(0.0, 0.0),
        msb_type="no_msb",
        is_idiosyncratic=shock.is_idiosyncratic,
        fundamental_ok=fundamental.get("passed", False),
        confidence_score=0.0,
        analysis_summary=f"EVITAR — {fundamental.get('details', {}).get('risk_flags', ['R:R insuficiente'])}",
        timestamp=datetime.now(tz=timezone.utc),
        asset_class=determine_asset_class(ticker, market),
    )


def run_capitulation_scan(
    tickers_with_data: list[tuple[str, str, pd.DataFrame, pd.DataFrame]],
    capital: float = 100_000.0,
    benchmark_dfs: dict[str, pd.DataFrame] | None = None,
) -> list[AsymmetricSignal]:
    """Scan a list of tickers for capitulation opportunities.

    Parameters
    ----------
    tickers_with_data : list of (ticker, market, daily_df, hourly_df)
    capital : float
        Account capital.
    benchmark_dfs : dict, optional
        {'US_EQUITIES': spy_daily_df, 'CRYPTO': btc_daily_df}

    Returns
    -------
    list of AsymmetricSignal
        Only signals with verdict == 'APTO_COMPRA_ASIMETRICA'.
    """
    signals: list[AsymmetricSignal] = []
    benchmarks = benchmark_dfs or {}

    logger.info(
        "═══ Capitulation scan started — %d tickers ═══",
        len(tickers_with_data),
    )

    for ticker, market, daily_df, hourly_df in tickers_with_data:
        try:
            benchmark = benchmarks.get(market)
            signal = analyze_capitulation(
                ticker=ticker,
                market=market,
                daily_df=daily_df,
                hourly_df=hourly_df,
                capital=capital,
                benchmark_df=benchmark,
            )
            if signal is not None and signal.verdict == "APTO_COMPRA_ASIMETRICA":
                signals.append(signal)
        except Exception as exc:
            logger.error("Capitulation analysis failed for %s: %s", ticker, exc)

    logger.info(
        "═══ Capitulation scan complete — %d signals found ═══",
        len(signals),
    )

    return signals
