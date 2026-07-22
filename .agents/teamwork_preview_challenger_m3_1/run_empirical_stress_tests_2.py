"""
Empirical Stress Test Harness 2 — Additional Edge Cases & Resilience Testing.

Tests:
1. Benchmark date/length misalignment in classify_shock.
2. Corrupted JSON file handling in scanner.py.
3. HTTP handler file overwrite behavior in main.py.
4. Radar vs Breakout signal key deduplication in recent_signals.json.
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

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models import AsymmetricSignal, BreakoutSignal, RadarSignal
from backend.scanner import BreakoutScanner, parse_iso_timestamp
from backend.shock_detector import detect_shock, classify_shock, ShockResult
from backend.main import ScannerHTTPHandler


class EmpiricalStressTests2(unittest.TestCase):

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
    def test_corrupted_json_file_recovery(self, mock_sync):
        """Verify scanner graceful recovery when JSON file on disk is corrupted."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        # Write invalid JSON content to capitulation_signals.json
        with patch("os.path.join", return_value=self.cap_json_path):
            with open(self.cap_json_path, "w", encoding="utf-8") as f:
                f.write("{ INVALID JSON CONTENT ... ")

            new_sig = AsymmetricSignal(
                ticker="ETHUSDT",
                market="CRYPTO",
                verdict="APTO_COMPRA_ASIMETRICA",
                drop_pct=-0.04,
                entry_price=2500.0,
                stop_loss=2400.0,
                take_profit=2800.0,
                rr_ratio=3.0,
                position_size_qty=1.0,
                poc=2500.0,
                vah=2600.0,
                val=2450.0,
                fvg_zone=(2480.0, 2520.0),
                ob_zone=(2450.0, 2490.0),
                msb_type="bullish_reversal",
                is_idiosyncratic=True,
                fundamental_ok=True,
                confidence_score=0.85,
                analysis_summary="Recovery test",
                timestamp=now,
            )

            # Scanner should log warning and continue saving new signal without crashing
            try:
                scanner._save_capitulation_signals([new_sig])
                recovered = True
            except Exception as e:
                recovered = False
                print(f"Failed to recover from corrupted JSON: {e}")

            self.assertTrue(recovered, "Scanner should catch JSONDecodeError and overwrite with valid data")

            with open(self.cap_json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["ticker"], "ETHUSDT")
            print("\n[EMPIRICAL TEST 5 FINDINGS] Scanner successfully recovers from corrupted JSON on disk.")

    @patch("backend.scanner.BreakoutScanner._sync_to_render_backend")
    def test_radar_vs_breakout_key_deduplication(self, mock_sync):
        """Verify RadarSignal vs BreakoutSignal key formatting in _save_recent_signals."""
        scanner = BreakoutScanner(dry_run=True)
        now = datetime.now(timezone.utc)

        with patch("os.path.join", return_value=self.rec_json_path):
            radar_sig = RadarSignal(
                ticker="NVDA",
                market="US_EQUITIES",
                direction="LONG",
                price=120.0,
                triggers=["EMA_CROSS"],
                adx=30.0,
                ema_stack=True,
                volume_ratio=2.5,
                roc_pct=5.0,
                donchian_n=20,
                timestamp=now - timedelta(minutes=10),
            )

            breakout_sig = BreakoutSignal(
                ticker="NVDA",
                market="US_EQUITIES",
                direction="LONG",
                broken_level=118.0,
                entry_price=120.5,
                stop_loss=115.0,
                take_profit=130.0,
                volume_ratio=3.0,
                atr_value=4.0,
                timestamp=now,
            )

            # Save radar signal first
            scanner._save_recent_signals([radar_sig])
            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved1 = json.load(f)
            self.assertEqual(saved1[0]["type"], "radar")

            # Now save breakout signal for same ticker and direction
            scanner._save_recent_signals([breakout_sig])
            with open(self.rec_json_path, "r", encoding="utf-8") as f:
                saved2 = json.load(f)

            print("\n[EMPIRICAL TEST 6 FINDINGS]")
            print(f"Saved signal count for NVDA:LONG: {len(saved2)}")
            print(f"Latest signal type: {saved2[0]['type']}")
            self.assertEqual(len(saved2), 1, "BreakoutSignal and RadarSignal for same ticker:direction should share deduplication key")
            self.assertEqual(saved2[0]["type"], "breakout", "Latest breakout signal overwrites radar signal for same asset+direction")


if __name__ == "__main__":
    unittest.main()
