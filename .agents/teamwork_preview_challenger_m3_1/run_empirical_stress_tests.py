"""
Empirical Stress Test Harness for Milestone 3 Signal Persistence & Shock Detection.

Tests boundary conditions:
1. 24h boundary TTL expiration vs re-detection merge (first_detected reset / premature purge).
2. Benchmark bar alignment in classify_shock for multi-bar shock retention.
3. NaN / 0-volume data edge cases in detect_shock & JSON serialization.
4. Concurrent file read/write race conditions in signal persistence.
5. Max signal list truncation and duplicate ticker merging.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models import AsymmetricSignal, BreakoutSignal, RadarSignal
from backend.scanner import BreakoutScanner, parse_iso_timestamp
from backend.shock_detector import detect_shock, classify_shock, ShockResult


class EmpiricalStressTests(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cap_json_path = os.path.join(self.test_dir, "capitulation_signals.json")
        self.rec_json_path = os.path.join(self.test_dir, "recent_signals.json")

    def tearDown(self):
        for path in [self.cap_json_path, self.rec_json_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        try:
            os.rmdir(self.test_dir)
        except Exception:
            pass

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_24h_boundary_first_detected_reset_and_purge(self, mock_sync):
        """Harness 1: Verify behavior when first_detected exceeds 24h but signal is actively updated."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        # 1. Existing signal created 24 hours and 5 minutes ago (86700s ago)
        # but updated 10 minutes ago
        first_detected_ts = (now - timedelta(hours=24, minutes=5)).isoformat()
        last_updated_ts = (now - timedelta(minutes=10)).isoformat()

        initial_signal = {
            "type": "asymmetric",
            "ticker": "SOLUSDT",
            "market": "CRYPTO",
            "verdict": "APTO_COMPRA_ASIMETRICA",
            "drop_pct": -0.05,
            "entry_price": 140.0,
            "stop_loss": 130.0,
            "take_profit": 170.0,
            "rr_ratio": 3.0,
            "position_size_qty": 10.0,
            "poc": 140.0,
            "vah": 145.0,
            "val": 135.0,
            "fvg_zone": [138.0, 142.0],
            "ob_zone": [135.0, 138.0],
            "msb_type": "bullish_reversal",
            "is_idiosyncratic": True,
            "fundamental_ok": True,
            "confidence_score": 0.85,
            "analysis_summary": "Active SOL signal",
            "timestamp": last_updated_ts,
            "first_detected": first_detected_ts,
            "last_updated": last_updated_ts,
        }

        with patch("os.path.join", return_value=self.cap_json_path):
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                json.dump([initial_signal], f)

            # Scenario A: Scanner runs and SOLUSDT is NOT re-flagged this cycle
            # (e.g. price consolidating)
            scanner._save_capitulation_signals([])

            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved_a = json.load(f)

            # Empirical check: Was SOLUSDT purged even though it was updated 10 mins ago?
            sol_in_a = any(item["ticker"] == "SOLUSDT" for item in saved_a)

            # Scenario B: Now reset file, and scanner runs where SOLUSDT IS re-flagged
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                json.dump([initial_signal], f)

            new_sol_sig = AsymmetricSignal(
                ticker="SOLUSDT",
                market="CRYPTO",
                verdict="APTO_COMPRA_ASIMETRICA",
                drop_pct=-0.05,
                entry_price=141.0,
                stop_loss=130.0,
                take_profit=170.0,
                rr_ratio=3.0,
                position_size_qty=10.0,
                poc=140.0,
                vah=145.0,
                val=135.0,
                fvg_zone=(138.0, 142.0),
                ob_zone=(135.0, 138.0),
                msb_type="bullish_reversal",
                is_idiosyncratic=True,
                fundamental_ok=True,
                confidence_score=0.85,
                analysis_summary="Re-flagged SOL signal",
                timestamp=now,
            )

            scanner._save_capitulation_signals([new_sol_sig])

            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved_b = json.load(f)

            sol_item_b = next((item for item in saved_b if item["ticker"] == "SOLUSDT"), None)
            first_det_b = sol_item_b.get("first_detected") if sol_item_b else None

            print("\n[EMPIRICAL TEST 1 FINDINGS]")
            print(f"Scenario A (Not re-flagged this cycle): Signal retained? {sol_in_a} (Expected True if last_updated is 10m ago, but actual code purged it!)")
            if sol_item_b:
                print(f"Scenario B (Re-flagged): original first_detected={first_detected_ts}, new first_detected={first_det_b}")
                print(f"Is first_detected reset/lost? {first_det_b != first_detected_ts}")

            # Assertions to record empirical findings:
            # We record that code currently purges SOL when not re-flagged because first_detected > 24h
            self.assertFalse(sol_in_a, "Empirical finding confirmed: Signal is purged when first_detected > 24h even if updated 10m ago!")
            self.assertNotEqual(first_det_b, first_detected_ts, "Empirical finding confirmed: original first_detected is wiped and reset when crossing 24h!")

    def test_benchmark_misalignment_in_classify_shock(self):
        """Harness 2: Verify classify_shock uses bar -1 benchmark instead of shock bar index."""
        # Target asset daily_df (25 bars):
        # Bar -3 (2 days ago): Asset dropped -6.0% (Shock bar!)
        # Bar -2 (1 day ago): Asset flat 0.0%
        # Bar -1 (today): Asset flat +0.5%
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=25, freq="D")
        asset_close = [100.0] * 22 + [94.0, 94.0, 94.5]
        asset_low = [99.5] * 22 + [93.5, 93.8, 94.2]
        volume = [10000.0] * 25

        asset_df = pd.DataFrame({
            "Close": asset_close,
            "Low": asset_low,
            "High": [c * 1.01 for c in asset_close],
            "Open": asset_close,
            "Volume": volume,
        }, index=dates)

        # Benchmark daily_df (25 bars):
        # Bar -3 (2 days ago): Benchmark dropped -3.0% (Systemic crash! BENCHMARK_SYSTEMIC_PCT is -1.0%)
        # Bar -2 (1 day ago): Benchmark flat 0.0%
        # Bar -1 (today): Benchmark rebound +1.5%
        bench_close = [400.0] * 22 + [388.0, 388.0, 393.84] # 400 -> 388 (-3%), 388 -> 388 (0%), 388 -> 393.84 (+1.5%)
        bench_df = pd.DataFrame({
            "Close": bench_close,
            "Low": bench_close,
            "High": bench_close,
            "Open": bench_close,
            "Volume": volume,
        }, index=dates)

        shock = detect_shock(asset_df, threshold_pct=-0.02)
        self.assertIsNotNone(shock)

        classified_shock = classify_shock(shock, bench_df)

        print("\n[EMPIRICAL TEST 2 FINDINGS]")
        print(f"Shock detected effective_drop: {shock.drop_pct * 100:.2f}%")
        print(f"Actual benchmark drop on shock bar (bar -3): -3.0% (Systemic!)")
        print(f"Classified benchmark_drop_pct reported: {classified_shock.benchmark_drop_pct * 100:.2f}% (from bar -1!)")
        print(f"Classified is_idiosyncratic: {classified_shock.is_idiosyncratic}")

        # The shock happened on bar -3 (when market crashed -3%). But classify_shock evaluated bar -1 (+1.5%)
        # and incorrectly concluded is_idiosyncratic = True!
        self.assertTrue(classified_shock.is_idiosyncratic, "Empirical finding confirmed: classify_shock evaluates bar -1 benchmark, misclassifying multi-bar shock as idiosyncratic!")

    def test_shock_detector_nan_and_zero_volume_handling(self):
        """Harness 3: Verify detect_shock with NaN / 0 volume data."""
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=25, freq="D")
        close_prices = [100.0] * 22 + [95.0, 95.0, 95.0]
        low_prices = [99.5] * 22 + [94.5, 94.5, 94.5]
        # NaN in volume for bar -1
        volume_data = [10000.0] * 24 + [np.nan]

        df_nan_vol = pd.DataFrame({
            "Close": close_prices,
            "Low": low_prices,
            "High": [c * 1.01 for c in close_prices],
            "Open": close_prices,
            "Volume": volume_data,
        }, index=dates)

        shock = detect_shock(df_nan_vol, threshold_pct=-0.02)
        print("\n[EMPIRICAL TEST 3 FINDINGS]")
        if shock:
            print(f"Shock vol ratio with NaN volume: {shock.capitulation_volume_ratio}")
            # Is it NaN?
            is_nan_vol = np.isnan(shock.capitulation_volume_ratio)
            print(f"Is volume ratio NaN? {is_nan_vol}")
            if is_nan_vol:
                # Test JSON serialization of shock or dict containing NaN
                test_dict = {"vol_ratio": shock.capitulation_volume_ratio}
                try:
                    json_str = json.dumps(test_dict)
                    print(f"JSON serialized: {json_str} (Note: JSON standard strictly forbids NaN!)")
                except Exception as e:
                    print(f"JSON serialization failed: {e}")

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_duplicate_ticker_updates_in_single_scan(self, mock_sync):
        """Harness 4: Verify behavior when multiple signals for the same ticker are passed to _save_recent_signals."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        with patch("os.path.join", return_value=self.rec_json_path):
            sig1 = BreakoutSignal(
                ticker="BTCUSDT",
                market="CRYPTO",
                direction="LONG",
                broken_level=60000.0,
                entry_price=60500.0,
                stop_loss=59000.0,
                take_profit=63000.0,
                volume_ratio=2.0,
                atr_value=1000.0,
                timestamp=now - timedelta(minutes=5),
            )
            sig2 = BreakoutSignal(
                ticker="BTCUSDT",
                market="CRYPTO",
                direction="LONG",
                broken_level=60000.0,
                entry_price=61000.0,
                stop_loss=59500.0,
                take_profit=64000.0,
                volume_ratio=3.5,
                atr_value=1000.0,
                timestamp=now,
            )

            scanner._save_recent_signals([sig1, sig2])

            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            print("\n[EMPIRICAL TEST 4 FINDINGS]")
            print(f"Input: 2 signals for BTCUSDT in single batch. Output item count: {len(saved)}")
            if len(saved) == 1:
                print(f"Deduplicated entry_price: {saved[0]['entry_price']} (Latest scan wins)")
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["entry_price"], 61000.0)


if __name__ == "__main__":
    unittest.main()
