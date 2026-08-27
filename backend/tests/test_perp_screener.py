"""
Unit and Integration Tests for Hyperliquid Perpetuals Screener & Microstructure
"""

import pytest
from backend.ticker_mapper import to_hyperliquid_symbol, to_binance_symbol, to_yahoo_symbol
from backend.hl_microstructure import fetch_hl_snapshots, get_asset_microstructure
from backend.perp_screener import evaluate_perp_candidate, scan_perps_universe


def test_ticker_mapper():
    assert to_hyperliquid_symbol("GC=F") == "xyz:GOLD"
    assert to_hyperliquid_symbol("^GSPC") == "xyz:SPX"
    assert to_hyperliquid_symbol("NVDA") == "xyz:NVDA"
    assert to_hyperliquid_symbol("BTCUSDT") == "BTC"
    assert to_hyperliquid_symbol("ETH") == "ETH"
    assert to_hyperliquid_symbol("xyz:PLTR") == "xyz:PLTR"

    assert to_binance_symbol("BTC") == "BTCUSDT"
    assert to_binance_symbol("xyz:NVDA") == "NVDAUSDT"
    assert to_yahoo_symbol("xyz:GOLD") == "GC=F"


def test_hl_microstructure_snapshots():
    main_dex, xyz_dex = fetch_hl_snapshots(force_refresh=True)
    assert isinstance(main_dex, dict)
    assert isinstance(xyz_dex, dict)
    # Check BTC in main dex or NVDA in xyz dex if network is up
    assert "BTC" in main_dex or len(main_dex) > 0
    assert "xyz:NVDA" in xyz_dex or "NVDA" in xyz_dex or len(xyz_dex) > 0


def test_evaluate_perp_candidate():
    res = evaluate_perp_candidate("BTCUSDT", direction="LONG", leverage=5.0)
    assert isinstance(res, dict)
    assert res["ticker"] == "BTCUSDT"
    assert res["hl_symbol"] == "BTC"
    assert res["verdict"] in ("APROBADO", "RECHAZADO")
    assert "phase1_passed" in res
    assert "phase2_passed" in res
    assert "phase3_passed" in res
    assert "rejection_reasons" in res


def test_scan_perps_universe():
    res = scan_perps_universe(["BTCUSDT", "NVDA"], leverage=5.0)
    assert isinstance(res, dict)
    assert res["total_scanned_pairs"] == 4
    assert "approved_longs" in res
    assert "approved_shorts" in res
    assert "rejected" in res
    assert "journal_summary" in res



if __name__ == "__main__":
    print("Running test_ticker_mapper()...")
    test_ticker_mapper()
    print("[PASS] test_ticker_mapper")

    print("Running test_hl_microstructure_snapshots()...")
    test_hl_microstructure_snapshots()
    print("[PASS] test_hl_microstructure_snapshots")

    print("Running test_evaluate_perp_candidate()...")
    test_evaluate_perp_candidate()
    print("[PASS] test_evaluate_perp_candidate")

    print("Running test_scan_perps_universe()...")
    test_scan_perps_universe()
    print("[PASS] test_scan_perps_universe")

    print("\nALL HYPERLIQUID PERPETUALS SCREENER TESTS PASSED SUCCESSFULLY!")

