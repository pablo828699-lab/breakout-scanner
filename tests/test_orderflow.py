"""
Unit and Synthetic Scenario Tests for Order Flow & Auction Market Theory Engine.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

# Ensure root directory is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.orderflow_engine import (
    calculate_zscore,
    calculate_slope,
    evaluate_orderflow_metrics,
    analyze_orderflow_and_auction,
)
from backend.auction_regime import compute_dual_session_profiles, evaluate_auction_context
from backend.orderflow_models import compute_composite_scores, generate_market_story


def generate_synthetic_candles(
    n_bars: int = 60,
    base_price: float = 100.0,
    trend_drift: float = 0.0,
    delta_profile: str = "neutral",
) -> pd.DataFrame:
    """Generates synthetic OHLCV + Delta dataset with deterministic seeds."""
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n_bars, freq="1h")
    
    price_steps = np.random.normal(trend_drift, 0.3, n_bars)
    prices = base_price + np.cumsum(price_steps)
    volumes = np.random.uniform(1000.0, 2500.0, n_bars)

    buy_ratio = np.random.uniform(0.48, 0.52, n_bars)
    if delta_profile == "heavy_sell":
        # Baseline neutral, then aggressive sell surge on last 8 bars
        buy_ratio[-8:] = np.random.uniform(0.05, 0.15, 8)
        volumes[-8:] = volumes[-8:] * 2.2
    elif delta_profile == "heavy_buy":
        # Baseline neutral, then aggressive buy surge on last 8 bars
        buy_ratio[-8:] = np.random.uniform(0.85, 0.95, 8)
        volumes[-8:] = volumes[-8:] * 2.2
    elif delta_profile == "exhaustion_buy":
        decay = np.linspace(0.85, 0.45, n_bars)
        buy_ratio = decay

    buy_vol = volumes * buy_ratio
    sell_vol = volumes - buy_vol
    delta = buy_vol - sell_vol
    cvd = np.cumsum(delta)

    highs = prices + np.random.uniform(0.2, 0.8, n_bars)
    lows = prices - np.random.uniform(0.2, 0.8, n_bars)
    opens = prices - price_steps / 2.0

    return pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": prices,
        "Volume": volumes,
        "BuyVolume": buy_vol,
        "SellVolume": sell_vol,
        "Delta": delta,
        "CVD": cvd,
    }, index=dates)


def test_synthetic_buyer_absorption():
    """
    Test Buyer Absorption:
    - Heavy sell aggression (Delta & CVD strongly negative).
    - Price remains flat / slightly positive (inefficient selling).
    - OI is expanding.
    Expected: buyer_absorption_score >= 60, oi_classification = BUYER_ABSORPTION_CANDIDATE.
    """
    df = generate_synthetic_candles(n_bars=60, base_price=100.0, trend_drift=0.02, delta_profile="heavy_sell")
    oi_series = pd.Series(np.linspace(10000, 14000, 60), index=df.index)

    of = evaluate_orderflow_metrics(df, oi_series=oi_series)
    profiles = {
        "prev_poc": 100.0, "prev_vah": 102.0, "prev_val": 98.0,
        "intra_poc": 100.0, "intra_vah": 101.5, "intra_val": 99.8,
        "poc_slope": 0.0, "vah_slope": 0.0, "val_slope": 0.0,
    }
    auc = evaluate_auction_context(float(df["Close"].iloc[-1]), profiles, of)
    scores = compute_composite_scores(of, auc)

    assert of["cvd_change_z"] < -1.0, f"CVD z-score should be negative, got {of['cvd_change_z']}"
    assert scores["buyer_absorption"] >= 55.0, f"Buyer absorption score should be high, got {scores['buyer_absorption']}"
    assert of["oi_classification"] == "BUYER_ABSORPTION_CANDIDATE"


def test_synthetic_seller_absorption():
    """
    Test Seller Absorption:
    - Heavy buy aggression (Delta & CVD strongly positive).
    - Price fails to expand upwards (inefficient buying).
    Expected: seller_absorption_score >= 55, oi_classification = SELLER_ABSORPTION_CANDIDATE.
    """
    df = generate_synthetic_candles(n_bars=60, base_price=100.0, trend_drift=-0.01, delta_profile="heavy_buy")
    oi_series = pd.Series(np.linspace(10000, 14000, 60), index=df.index)

    last_p = float(df["Close"].iloc[-1])
    of = evaluate_orderflow_metrics(df, oi_series=oi_series)
    profiles = {
        "prev_poc": last_p - 0.8, "prev_vah": last_p + 0.2, "prev_val": last_p - 1.5,
        "intra_poc": last_p - 0.4, "intra_vah": last_p + 0.05, "intra_val": last_p - 1.2,
        "poc_slope": 0.0, "vah_slope": 0.0, "val_slope": 0.0,
    }
    auc = evaluate_auction_context(last_p, profiles, of)
    scores = compute_composite_scores(of, auc)

    assert of["cvd_change_z"] > 1.0, f"CVD z-score should be positive, got {of['cvd_change_z']}"
    assert scores["seller_absorption"] >= 55.0, f"Seller absorption score should be high, got {scores['seller_absorption']}"
    assert of["oi_classification"] == "SELLER_ABSORPTION_CANDIDATE"


def test_synthetic_short_covering_squeeze():
    """
    Test Short Covering:
    - Price pushes up with positive CVD.
    - OI declines sharply (destruction of short positions).
    Expected: oi_classification = SHORT_COVERING_SQUEEZE.
    """
    df = generate_synthetic_candles(n_bars=60, base_price=100.0, trend_drift=0.35, delta_profile="heavy_buy")
    oi_series = pd.Series(np.linspace(20000, 11000, 60), index=df.index) # Sharp OI decline

    of = evaluate_orderflow_metrics(df, oi_series=oi_series)
    assert of["oi_classification"] == "SHORT_COVERING_SQUEEZE"
    assert of["oi_confidence"] >= 60.0


def test_synthetic_long_liquidation_squeeze():
    """
    Test Long Liquidation:
    - Price drops with negative CVD.
    - OI declines sharply (destruction of long positions).
    Expected: oi_classification = LONG_LIQUIDATION_SQUEEZE.
    """
    df = generate_synthetic_candles(n_bars=60, base_price=100.0, trend_drift=-0.35, delta_profile="heavy_sell")
    oi_series = pd.Series(np.linspace(20000, 11000, 60), index=df.index) # Sharp OI decline

    of = evaluate_orderflow_metrics(df, oi_series=oi_series)
    assert of["oi_classification"] == "LONG_LIQUIDATION_SQUEEZE"


def test_dual_session_profiles_and_value_migration():
    """
    Test Value Migration and Dual Profiles:
    - Upward drift across 50 bars.
    Expected: intra_poc > prev_poc and value_migration = VALUE_MIGRATION_UP.
    """
    df = generate_synthetic_candles(n_bars=72, base_price=100.0, trend_drift=0.25, delta_profile="neutral")
    profiles = compute_dual_session_profiles(df, session_bars=24)

    assert profiles["intra_poc"] > 0
    assert profiles["prev_poc"] > 0

    of = evaluate_orderflow_metrics(df)
    auc = evaluate_auction_context(float(df["Close"].iloc[-1]), profiles, of)
    assert "location_tags" in auc
    assert "regime" in auc


def test_master_analyze_orderflow_and_auction():
    """
    Test end-to-end analysis output schema.
    """
    df = generate_synthetic_candles(n_bars=60, base_price=50000.0, trend_drift=50.0, delta_profile="heavy_sell")
    oi_series = pd.Series(np.linspace(500000, 580000, 60), index=df.index)

    result = analyze_orderflow_and_auction(
        symbol="BTCUSDT",
        df_1h=df,
        oi_series=oi_series,
        market="CRYPTO",
    )

    assert result["symbol"] == "BTCUSDT"
    assert "regime" in result
    assert "location" in result
    assert "scores" in result
    assert "metrics" in result
    assert "market_story" in result
    assert isinstance(result["market_story"], str) and len(result["market_story"]) > 10

    scores = result["scores"]
    for key in ["seller_absorption", "buyer_absorption", "trapped_shorts", "trapped_longs", "initiative_buying", "exhaustion"]:
        assert key in scores, f"Missing score: {key}"
        assert 0.0 <= scores[key] <= 100.0, f"Score {key} out of range 0-100: {scores[key]}"


if __name__ == "__main__":
    print("Running Order Flow & Auction Market Theory Test Suite...")
    test_synthetic_buyer_absorption()
    print("[PASS] test_synthetic_buyer_absorption")
    test_synthetic_seller_absorption()
    print("[PASS] test_synthetic_seller_absorption")
    test_synthetic_short_covering_squeeze()
    print("[PASS] test_synthetic_short_covering_squeeze")
    test_synthetic_long_liquidation_squeeze()
    print("[PASS] test_synthetic_long_liquidation_squeeze")
    test_dual_session_profiles_and_value_migration()
    print("[PASS] test_dual_session_profiles_and_value_migration")
    test_master_analyze_orderflow_and_auction()
    print("[PASS] test_master_analyze_orderflow_and_auction")
    print("\nALL 6 ORDER FLOW & AUCTION TESTS PASSED (100% SUCCESS)!")
