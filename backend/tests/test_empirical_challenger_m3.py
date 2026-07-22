"""
Empirical Challenger Test Harness for Milestone 3 Verification.
Tests signal deduplication, non-destructive JSON merges, 24h TTL retention,
ISO 8601 timestamp parsing robustness, 3-bar shock detection lookback,
and boundary edge cases.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.models import AsymmetricSignal, BreakoutSignal, RadarSignal
from backend.scanner import BreakoutScanner, parse_iso_timestamp
from backend.shock_detector import detect_shock, ShockResult


class TestMilestone3ISO8601TimestampParsing(unittest.TestCase):
    """Empirical verification of ISO 8601 timestamp parsing and edge cases."""

    def test_iso8601_parsing_valid_variants(self):
        """Test ISO 8601 parsing across UTC ISO, offset ISO, Z suffix, and legacy UTC formats."""
        now_utc = datetime.now(timezone.utc)

        # ISO with Z suffix
        dt1 = parse_iso_timestamp("2026-07-21T15:30:00Z")
        self.assertIsNotNone(dt1.tzinfo)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 7)
        self.assertEqual(dt1.day, 21)
        self.assertEqual(dt1.hour, 15)

        # ISO with +00:00 offset
        dt2 = parse_iso_timestamp("2026-07-21T15:30:00+00:00")
        self.assertIsNotNone(dt2.tzinfo)
        self.assertEqual(dt2.minute, 30)

        # ISO with non-UTC offset (+03:00 -> 15:30 +03:00 is 12:30 UTC)
        dt3 = parse_iso_timestamp("2026-07-21T15:30:00+03:00")
        self.assertIsNotNone(dt3.tzinfo)
        self.assertEqual(dt3.utcoffset(), timedelta(hours=3))

        # Legacy UTC string format
        dt4 = parse_iso_timestamp("2026-07-21 15:30 UTC")
        self.assertIsNotNone(dt4.tzinfo)
        self.assertEqual(dt4.year, 2026)

        # Naive datetime
        naive_dt = datetime(2026, 7, 21, 15, 30)
        dt5 = parse_iso_timestamp(naive_dt)
        self.assertIsNotNone(dt5.tzinfo)

        # Aware datetime
        dt6 = parse_iso_timestamp(now_utc)
        self.assertEqual(dt6, now_utc)

    def test_iso8601_parsing_invalid_and_adversarial_inputs(self):
        """Test timestamp parsing against corrupt, missing, or type-mismatched inputs."""
        before = datetime.now(timezone.utc) - timedelta(seconds=2)

        # None input
        res_none = parse_iso_timestamp(None)
        self.assertGreaterEqual(res_none, before)

        # Invalid string
        res_garbage = parse_iso_timestamp("not-a-timestamp")
        self.assertGreaterEqual(res_garbage, before)

        # Empty string
        res_empty = parse_iso_timestamp("")
        self.assertGreaterEqual(res_empty, before)

        # Non-string types (int, float, list, dict, bool)
        for bad_val in [1234567890, 123.45, ["2026-01-01"], {"ts": "2026"}, True]:
            res_bad = parse_iso_timestamp(bad_val)
            self.assertGreaterEqual(res_bad, before)


class TestMilestone3SignalDeduplication(unittest.TestCase):
    """Empirical verification of signal deduplication for candidates and capitulation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.rec_json_path = os.path.join(self.test_dir, "recent_signals.json")
        self.cap_json_path = os.path.join(self.test_dir, "capitulation_signals.json")

    def tearDown(self):
        for path in [self.rec_json_path, self.cap_json_path]:
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
    def test_recent_signals_separate_keys_by_direction(self, mock_sync):
        """Verify that same ticker with different directions (LONG vs SHORT) yields distinct keys."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        sig_long = BreakoutSignal(
            ticker="BTCUSDT",
            market="CRYPTO",
            direction="LONG",
            broken_level=60000.0,
            entry_price=60500.0,
            stop_loss=59000.0,
            take_profit=63500.0,
            volume_ratio=2.5,
            atr_value=1000.0,
            timestamp=now,
        )

        sig_short = BreakoutSignal(
            ticker="BTCUSDT",
            market="CRYPTO",
            direction="SHORT",
            broken_level=55000.0,
            entry_price=54500.0,
            stop_loss=56000.0,
            take_profit=51500.0,
            volume_ratio=2.2,
            atr_value=1000.0,
            timestamp=now,
        )

        with patch("os.path.join", return_value=self.rec_json_path):
            scanner._save_recent_signals([sig_long, sig_short])

            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(len(saved), 2, "LONG and SHORT for same ticker should not overwrite each other")
            directions = {item["direction"] for item in saved}
            self.assertEqual(directions, {"LONG", "SHORT"})

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_first_detected_preservation_and_last_updated_update(self, mock_sync):
        """Verify first_detected timestamp is preserved across multiple scan cycles while last_updated is refreshed."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)
        first_time = now - timedelta(hours=5)
        first_iso = first_time.isoformat()

        # Seed disk with an existing signal detected 5 hours ago
        seed_data = [
            {
                "type": "asymmetric",
                "ticker": "SOLUSDT",
                "market": "CRYPTO",
                "verdict": "APTO_COMPRA_ASIMETRICA",
                "drop_pct": -0.06,
                "entry_price": 140.0,
                "stop_loss": 130.0,
                "take_profit": 160.0,
                "rr_ratio": 2.0,
                "position_size_qty": 10.0,
                "poc": 140.0,
                "vah": 145.0,
                "val": 135.0,
                "fvg_zone": [138.0, 142.0],
                "ob_zone": [135.0, 138.0],
                "msb_type": "bullish_reversal",
                "is_idiosyncratic": True,
                "fundamental_ok": True,
                "confidence_score": 0.88,
                "analysis_summary": "Original SOL signal",
                "timestamp": first_iso,
                "first_detected": first_iso,
                "last_updated": first_iso,
            }
        ]

        with patch("os.path.join", return_value=self.cap_json_path):
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                json.dump(seed_data, f)

            # New scan cycle at `now` re-detects SOLUSDT
            new_sig = AsymmetricSignal(
                ticker="SOLUSDT",
                market="CRYPTO",
                verdict="APTO_COMPRA_ASIMETRICA",
                drop_pct=-0.05,
                entry_price=142.0,
                stop_loss=132.0,
                take_profit=162.0,
                rr_ratio=2.0,
                position_size_qty=10.0,
                poc=142.0,
                vah=146.0,
                val=136.0,
                fvg_zone=(140.0, 144.0),
                ob_zone=(136.0, 140.0),
                msb_type="bullish_reversal",
                is_idiosyncratic=True,
                fundamental_ok=True,
                confidence_score=0.90,
                analysis_summary="Updated SOL signal",
                timestamp=now,
            )

            scanner._save_capitulation_signals([new_sig])

            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(len(saved), 1)
            item = saved[0]
            self.assertEqual(item["ticker"], "SOLUSDT")
            self.assertEqual(item["first_detected"], first_iso, "first_detected must remain original initial detection time")
            self.assertEqual(item["entry_price"], 142.0, "entry_price must update to latest scan value")
            self.assertNotEqual(item["last_updated"], first_iso, "last_updated must update to current scan time")

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_recent_signals_truncation_to_100_max(self, mock_sync):
        """Verify candidate list is truncated to a maximum of 100 entries ordered by last_updated descending."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        signals = []
        for i in range(120):
            sig = BreakoutSignal(
                ticker=f"STOCK_{i:03d}",
                market="US_EQUITIES",
                direction="LONG",
                broken_level=100.0 + i,
                entry_price=101.0 + i,
                stop_loss=98.0 + i,
                take_profit=107.0 + i,
                volume_ratio=2.0,
                atr_value=1.5,
                timestamp=now - timedelta(minutes=120 - i),
            )
            signals.append(sig)

        with patch("os.path.join", return_value=self.rec_json_path):
            scanner._save_recent_signals(signals)

            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(len(saved), 100, "Must cap saved signals at 100 items max")
            # Most recent signal (STOCK_119) should be first
            self.assertEqual(saved[0]["ticker"], "STOCK_119")


class TestMilestone3NonDestructiveMergesAndTTL(unittest.TestCase):
    """Empirical verification of 24h TTL signal retention and non-destructive merges."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cap_json_path = os.path.join(self.test_dir, "capitulation_signals.json")

    def tearDown(self):
        if os.path.exists(self.cap_json_path):
            try:
                os.remove(self.cap_json_path)
            except Exception:
                pass
        try:
            os.rmdir(self.test_dir)
        except Exception:
            pass

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_24h_ttl_boundary_and_invalidated_signal_pruning(self, mock_sync):
        """Verify 23h 59m active signals are retained, >=24h signals are pruned, and INVALIDATED signals are purged."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        ts_23h59m = (now - timedelta(hours=23, minutes=59)).isoformat()
        ts_24h01m = (now - timedelta(hours=24, minutes=1)).isoformat()
        ts_12h_inval = (now - timedelta(hours=12)).isoformat()

        seed_items = [
            {
                "type": "asymmetric",
                "ticker": "ACTIVE_RETAINED",
                "market": "CRYPTO",
                "verdict": "APTO_COMPRA_ASIMETRICA",
                "drop_pct": -0.05,
                "first_detected": ts_23h59m,
                "timestamp": ts_23h59m,
            },
            {
                "type": "asymmetric",
                "ticker": "EXPIRED_PRUNED",
                "market": "CRYPTO",
                "verdict": "APTO_COMPRA_ASIMETRICA",
                "drop_pct": -0.05,
                "first_detected": ts_24h01m,
                "timestamp": ts_24h01m,
            },
            {
                "type": "asymmetric",
                "ticker": "INVALIDATED_PRUNED",
                "market": "CRYPTO",
                "verdict": "INVALIDATED",
                "drop_pct": -0.05,
                "first_detected": ts_12h_inval,
                "timestamp": ts_12h_inval,
            },
        ]

        with patch("os.path.join", return_value=self.cap_json_path):
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                json.dump(seed_items, f)

            # Trigger save with an empty new signals list to test TTL load & prune filter
            scanner._save_capitulation_signals([])

            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            tickers = [item["ticker"] for item in saved]
            self.assertIn("ACTIVE_RETAINED", tickers, "23h59m signal should be retained")
            self.assertNotIn("EXPIRED_PRUNED", tickers, ">=24h signal should be pruned")
            self.assertNotIn("INVALIDATED_PRUNED", tickers, "INVALIDATED signal should be pruned")

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_corrupt_json_file_resilience(self, mock_sync):
        """Verify _save_capitulation_signals and _save_recent_signals do not crash when json file on disk is corrupt."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        with patch("os.path.join", return_value=self.cap_json_path):
            # Write malformed JSON
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                f.write("{ corrupt json content ... ")

            new_sig = AsymmetricSignal(
                ticker="ETHUSDT",
                market="CRYPTO",
                verdict="APTO_COMPRA_ASIMETRICA",
                drop_pct=-0.04,
                entry_price=3000.0,
                stop_loss=2900.0,
                take_profit=3300.0,
                rr_ratio=3.0,
                position_size_qty=0.5,
                poc=3000.0,
                vah=3050.0,
                val=2950.0,
                fvg_zone=(2980.0, 3020.0),
                ob_zone=(2950.0, 2980.0),
                msb_type="bullish_reversal",
                is_idiosyncratic=True,
                fundamental_ok=True,
                confidence_score=0.85,
                analysis_summary="Eth test",
                timestamp=now,
            )

            # Should not throw an unhandled exception
            scanner._save_capitulation_signals([new_sig])

            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["ticker"], "ETHUSDT")


class TestMilestone3ShockDetectorLookback(unittest.TestCase):
    """Empirical verification of 3-bar shock detection lookback logic."""

    def test_shock_detection_intraday_spike_qualification(self):
        """Verify detect_shock captures intraday low drop even if close price rebounded."""
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=25, freq="D")
        close_prices = [100.0] * 24 + [99.0]  # Close drop is only -1.0%
        low_prices = [99.5] * 24 + [96.0]     # Intraday low dropped -4.0%
        volume_data = [10000.0] * 25

        daily_df = pd.DataFrame({
            "Close": close_prices,
            "Low": low_prices,
            "High": [101.0] * 25,
            "Open": [100.0] * 25,
            "Volume": volume_data,
        }, index=dates)

        shock = detect_shock(daily_df, threshold_pct=-0.02)
        self.assertIsNotNone(shock, "Intraday low drop of -4.0% must qualify as shock despite close rebound to -1.0%")
        self.assertLessEqual(shock.drop_pct, -0.039)
        self.assertEqual(shock.capitulation_low, 96.0)

    def test_shock_detection_insufficient_dataframe(self):
        """Verify detect_shock returns None gracefully when daily_df has < 22 rows."""
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=15, freq="D")
        daily_df = pd.DataFrame({
            "Close": [100.0] * 15,
            "Low": [90.0] * 15,
            "High": [105.0] * 15,
            "Open": [100.0] * 15,
            "Volume": [10000.0] * 15,
        }, index=dates)

        res = detect_shock(daily_df)
        self.assertIsNone(res, "Must return None when rows < 22")


if __name__ == "__main__":
    unittest.main()
