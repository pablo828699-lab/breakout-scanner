"""
Unit tests for signal persistence, 24h TTL retention, key-based deduplication,
ISO 8601 timestamp formatting, and non-destructive JSON merges.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pandas as pd

from backend.models import AsymmetricSignal, BreakoutSignal, RadarSignal
from backend.scanner import BreakoutScanner, parse_iso_timestamp
from backend.shock_detector import detect_shock, ShockResult


class TestSignalPersistence(unittest.TestCase):
    """Test suite for signal persistence, TTL, deduplication, and ISO 8601 formatting."""

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

    def test_parse_iso_timestamp(self):
        """Verify timestamp parsing handles ISO 8601 strings, legacy UTC strings, and datetimes."""
        now_utc = datetime.now(timezone.utc)
        # ISO string
        iso_str = now_utc.isoformat()
        dt_iso = parse_iso_timestamp(iso_str)
        self.assertIsNotNone(dt_iso.tzinfo)
        self.assertEqual(dt_iso.year, now_utc.year)

        # Legacy UTC string
        legacy_str = "2026-07-21 15:30 UTC"
        dt_legacy = parse_iso_timestamp(legacy_str)
        self.assertEqual(dt_legacy.year, 2026)
        self.assertEqual(dt_legacy.month, 7)
        self.assertEqual(dt_legacy.day, 21)

        # Datetime object
        dt_obj = parse_iso_timestamp(now_utc)
        self.assertEqual(dt_obj, now_utc)

    def test_detect_shock_marginal_bar_preservation(self):
        """Verify detect_shock retains shock detection over a 3-bar window despite day 2 stabilization."""
        # Create a 25-day daily_df
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=25, freq="D")
        close_prices = [100.0] * 22 + [95.0, 95.5, 96.0]  # Bar -3 dropped 5%, Bar -2 and -1 stabilized
        low_prices = [99.5] * 22 + [94.5, 95.0, 95.5]
        volume_data = [10000.0] * 25

        daily_df = pd.DataFrame({
            "Close": close_prices,
            "Low": low_prices,
            "High": [c * 1.01 for c in close_prices],
            "Open": close_prices,
            "Volume": volume_data,
        }, index=dates)

        # Shock occurred at bar -3 (-5.0% drop). Day 2 (bar -2) and Day 3 (bar -1) are flat/rebounding.
        shock = detect_shock(daily_df, threshold_pct=-0.02)
        self.assertIsNotNone(shock)
        self.assertLessEqual(shock.drop_pct, -0.045)
        self.assertEqual(shock.capitulation_low, 94.5)

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_save_capitulation_signals_24h_ttl_and_merge(self, mock_sync):
        """Verify capitulation signals persist for 24 hours and non-destructive merges update state."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        # 1. Create an existing signal on disk: one 10 hours old, one 30 hours old (expired)
        old_10h_ts = (now - timedelta(hours=10)).isoformat()
        old_30h_ts = (now - timedelta(hours=30)).isoformat()

        existing_data = [
            {
                "type": "asymmetric",
                "ticker": "ETHUSDT",
                "market": "CRYPTO",
                "verdict": "APTO_COMPRA_ASIMETRICA",
                "drop_pct": -0.05,
                "entry_price": 2500.0,
                "stop_loss": 2400.0,
                "take_profit": 2800.0,
                "rr_ratio": 3.0,
                "position_size_qty": 1.0,
                "poc": 2500.0,
                "vah": 2600.0,
                "val": 2450.0,
                "fvg_zone": [2480.0, 2520.0],
                "ob_zone": [2450.0, 2490.0],
                "msb_type": "bullish_reversal",
                "is_idiosyncratic": True,
                "fundamental_ok": True,
                "confidence_score": 0.85,
                "analysis_summary": "10h old active signal",
                "timestamp": old_10h_ts,
                "first_detected": old_10h_ts,
                "last_updated": old_10h_ts,
            },
            {
                "type": "asymmetric",
                "ticker": "OLDEXPIRED",
                "market": "US_EQUITIES",
                "verdict": "APTO_COMPRA_ASIMETRICA",
                "drop_pct": -0.04,
                "entry_price": 50.0,
                "stop_loss": 48.0,
                "take_profit": 56.0,
                "rr_ratio": 3.0,
                "position_size_qty": 100.0,
                "poc": 50.0,
                "vah": 52.0,
                "val": 49.0,
                "fvg_zone": [0.0, 0.0],
                "ob_zone": [0.0, 0.0],
                "msb_type": "none",
                "is_idiosyncratic": True,
                "fundamental_ok": True,
                "confidence_score": 0.75,
                "analysis_summary": "30h old expired signal",
                "timestamp": old_30h_ts,
                "first_detected": old_30h_ts,
                "last_updated": old_30h_ts,
            },
        ]

        with patch("os.path.join", return_value=self.cap_json_path):
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f)

            # 2. Add a new signal for BTCUSDT
            new_sig = AsymmetricSignal(
                ticker="BTCUSDT",
                market="CRYPTO",
                verdict="APTO_COMPRA_ASIMETRICA",
                drop_pct=-0.03,
                entry_price=60000.0,
                stop_loss=58000.0,
                take_profit=66000.0,
                rr_ratio=3.0,
                position_size_qty=0.5,
                poc=60000.0,
                vah=61000.0,
                val=59000.0,
                fvg_zone=(59500.0, 60500.0),
                ob_zone=(59000.0, 59500.0),
                msb_type="bullish_reversal",
                is_idiosyncratic=True,
                fundamental_ok=True,
                confidence_score=0.90,
                analysis_summary="New BTC signal",
                timestamp=now,
            )

            scanner._save_capitulation_signals([new_sig])

            # Read back saved file
            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            tickers = [item["ticker"] for item in saved]
            self.assertIn("ETHUSDT", tickers, "Active 10h signal for ETHUSDT should be retained")
            self.assertIn("BTCUSDT", tickers, "New signal for BTCUSDT should be saved")
            self.assertNotIn("OLDEXPIRED", tickers, "Expired 30h signal should be pruned")

            # Check ISO timestamp formatting
            for item in saved:
                ts_str = item["timestamp"]
                self.assertNotIn("UTC", ts_str, "Timestamps must be strict ISO 8601, not human formatted")
                # Ensure parsing ISO string works cleanly
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                self.assertIsNotNone(dt)

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_save_recent_signals_key_deduplication(self, mock_sync):
        """Verify candidate saving in _save_recent_signals performs key-based deduplication."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        with patch("os.path.join", return_value=self.rec_json_path):
            sig1 = BreakoutSignal(
                ticker="AAPL",
                market="US_EQUITIES",
                direction="LONG",
                broken_level=150.0,
                entry_price=151.0,
                stop_loss=148.0,
                take_profit=157.0,
                volume_ratio=2.5,
                atr_value=2.0,
                timestamp=now - timedelta(minutes=30),
            )

            # First scan cycle saves AAPL LONG
            scanner._save_recent_signals([sig1])

            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved1 = json.load(f)
            self.assertEqual(len(saved1), 1)
            self.assertEqual(saved1[0]["ticker"], "AAPL")
            self.assertEqual(saved1[0]["direction"], "LONG")

            # Second scan cycle re-detects AAPL LONG (price moved to 151.5)
            sig2 = BreakoutSignal(
                ticker="AAPL",
                market="US_EQUITIES",
                direction="LONG",
                broken_level=150.0,
                entry_price=151.5,
                stop_loss=148.0,
                take_profit=157.0,
                volume_ratio=2.8,
                atr_value=2.0,
                timestamp=now,
            )

            # Also add a new candidate NVDA LONG
            sig3 = BreakoutSignal(
                ticker="NVDA",
                market="US_EQUITIES",
                direction="LONG",
                broken_level=400.0,
                entry_price=402.0,
                stop_loss=395.0,
                take_profit=420.0,
                volume_ratio=3.0,
                atr_value=5.0,
                timestamp=now,
            )

            scanner._save_recent_signals([sig2, sig3])

            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved2 = json.load(f)

            # Should have 2 unique signals (AAPL LONG and NVDA LONG), not 3!
            self.assertEqual(len(saved2), 2, "Duplicate AAPL entry should be deduplicated")
            aapl_item = next(item for item in saved2 if item["ticker"] == "AAPL")
            self.assertEqual(aapl_item["entry_price"], 151.5, "AAPL entry_price should be updated to latest scan")
            self.assertIn("first_detected", aapl_item)
            self.assertIn("last_updated", aapl_item)


if __name__ == "__main__":
    unittest.main()
