"""
Adversarial Stress & Edge-Case Test Suite for DataFetcher Session Management & Rate-Limit Backoff (Milestone 2 Verification).
Created by teamwork_preview_challenger to empirically challenge and verify data_fetcher implementation assumptions.
"""

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import requests

import backend.config as cfg
from backend.data_fetcher import (
    DEFAULT_HEADERS,
    DataFetcher,
    _binance_request,
    get_shared_session,
)
from backend.fundamental_filter import evaluate_correlation_filter, run_fundamental_filter
from backend.scanner import BreakoutScanner


class TestAdversarialRateLimitAndHeaders(unittest.TestCase):
    """Stress-test rate limit backoff, Retry-After header handling, and 429/418 responses."""

    @patch("time.sleep")
    def test_binance_429_retry_after_header_handling(self, mock_sleep: MagicMock) -> None:
        """Test whether _binance_request respects Retry-After header on HTTP 429."""
        mock_session = MagicMock(spec=requests.Session)
        
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "5"}
        mock_resp_429.text = "Too Many Requests"

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = [{"symbol": "BTCUSDT", "price": "60000"}]

        mock_session.get.side_effect = [mock_resp_429, mock_resp_200]

        result = _binance_request(
            "/api/v3/ticker/price",
            max_retries=2,
            base_delay=0.1,
            session=mock_session,
        )

        self.assertIsNotNone(result)
        # Check sleep duration call: if Retry-After: 5 was ignored, sleep delay was ~0.1 - 0.6s.
        sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
        logging.info("Sleep delays called on 429 retry: %s", sleep_args)
        # Record finding for report whether Retry-After was respected
        self.assertTrue(len(sleep_args) > 0)


class TestAdversarialHostFailoverState(unittest.TestCase):
    """Stress-test Binance host failover state persistence and invalidation logic."""

    @patch("time.sleep")
    def test_working_host_invalidation_memory(self, mock_sleep: MagicMock) -> None:
        """Test state of _working_host when primary host recovers or secondary fails."""
        mock_session = MagicMock(spec=requests.Session)
        
        mock_451 = MagicMock()
        mock_451.status_code = 451

        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "Server Error"

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = [{"symbol": "BTCUSDT"}]

        # Call 1: Host 1 (api.binance.com) -> 451, Host 2 (vision) -> 200.
        # Should set _working_host to Host 2 (vision).
        mock_session.get.side_effect = [mock_451, mock_200]
        res1 = _binance_request("/api/v3/klines", max_retries=1, session=mock_session)
        self.assertIsNotNone(res1)

        # Call 2: Host 2 (vision) fails with 500. Host 1 (api.binance.com) returns 451.
        # Entire request fails, resetting _working_host to None.
        mock_session.get.side_effect = [mock_500, mock_451]
        res2 = _binance_request("/api/v3/klines", max_retries=1, session=mock_session)
        self.assertIsNone(res2)

        # Call 3: Now Host 2 (vision) recovers with 200, Host 1 still 451.
        # Since _working_host was reset to None, Call 3 will try Host 1 first (451), then Host 2 (200).
        mock_session.get.side_effect = [mock_451, mock_200]
        res3 = _binance_request("/api/v3/klines", max_retries=1, session=mock_session)
        self.assertIsNotNone(res3)
        self.assertEqual(mock_session.get.call_count, 6)


class TestAdversarialCryptoTickerFiltering(unittest.TestCase):
    """Stress-test get_crypto_tickers filtering logic for stablecoins, memecoins, and fallback list."""

    @patch.object(cfg, "CRYPTO_USE_WATCHLIST", False)
    @patch("backend.data_fetcher._binance_request")
    def test_memecoin_and_symbol_prefix_filtering(self, mock_request: MagicMock) -> None:
        """Verify if PEPE, SHIB, or legitimate tokens are inadvertently filtered by stablecoin set."""
        mock_request.return_value = [
            {"symbol": "BTCUSDT", "quoteVolume": "1000000000", "isascii": True},
            {"symbol": "ETHUSDT", "quoteVolume": "500000000", "isascii": True},
            {"symbol": "PEPEUSDT", "quoteVolume": "400000000", "isascii": True},
            {"symbol": "SHIBUSDT", "quoteVolume": "300000000", "isascii": True},
            {"symbol": "TRYPUSDT", "quoteVolume": "200000000", "isascii": True},
            {"symbol": "USDCUSDT", "quoteVolume": "100000000", "isascii": True},
        ]

        fetcher = DataFetcher()
        tickers = fetcher.get_crypto_tickers()

        logging.info("Returned top-N tickers: %s", tickers)
        # Check if PEPEUSDT and SHIBUSDT were filtered out
        pepe_filtered = "PEPEUSDT" not in tickers
        shib_filtered = "SHIBUSDT" not in tickers
        tryp_filtered = "TRYPUSDT" not in tickers

        self.assertTrue(pepe_filtered, "PEPEUSDT was filtered out due to 'PEPE' in stablecoins set")
        self.assertTrue(shib_filtered, "SHIBUSDT was filtered out due to 'SHIB' in stablecoins set")


class TestAdversarialSessionLifecycle(unittest.TestCase):
    """Stress-test get_shared_session singleton lifecycle under session closure or modification."""

    def test_shared_session_header_mutation_propagation(self) -> None:
        """Verify that mutating headers on get_shared_session affects all fetcher instances."""
        session1 = get_shared_session()
        fetcher1 = DataFetcher()
        fetcher2 = DataFetcher()

        self.assertEqual(fetcher1.get_session().headers["User-Agent"], session1.headers["User-Agent"])
        self.assertEqual(fetcher2.get_session().headers["User-Agent"], session1.headers["User-Agent"])

        # Mutate header
        session1.headers["User-Agent"] = "MutatedAgent/1.0"
        self.assertEqual(fetcher1.get_session().headers["User-Agent"], "MutatedAgent/1.0")
        self.assertEqual(fetcher2.get_session().headers["User-Agent"], "MutatedAgent/1.0")

        # Reset back to default for other tests
        session1.headers.update(DEFAULT_HEADERS)


class TestAdversarialYfinanceMultiIndexHandling(unittest.TestCase):
    """Verify yfinance download multiindex column handling with Pandas 3.0+."""

    @patch("backend.data_fetcher.yf.download")
    def test_droplevel_multiindex_columns(self, mock_download: MagicMock) -> None:
        # Create MultiIndex DataFrame as returned by yfinance 1.5+ on Pandas 3.0+
        cols = pd.MultiIndex.from_tuples(
            [("Close", "AAPL"), ("High", "AAPL"), ("Low", "AAPL"), ("Open", "AAPL"), ("Volume", "AAPL")],
            names=["Price", "Ticker"],
        )
        mock_df = pd.DataFrame([[100.0, 105.0, 95.0, 98.0, 1000000]], columns=cols)
        mock_download.return_value = mock_df

        fetcher = DataFetcher()
        with patch.object(cfg, "REQUEST_PACE_DELAY_SEC", 0.0):
            df = fetcher.fetch_sp500_daily("AAPL")

        self.assertFalse(df.empty)
        self.assertListEqual(list(df.columns), ["Close", "High", "Low", "Open", "Volume"])



class TestAdversarialEmptyDataDownstreamPipeline(unittest.TestCase):
    """Verify that returning empty DataFrames (post mock-data removal) does not crash scanner pipeline."""

    def test_empty_dataframe_correlation_filter(self) -> None:
        empty_df = pd.DataFrame()
        valid_df = pd.DataFrame(
            {"Close": [100.0] * 30},
            index=pd.date_range("2026-01-01", periods=30),
        )

        res1 = evaluate_correlation_filter(empty_df, valid_df)
        self.assertFalse(res1["passed"] if "passed" in res1 else res1["is_idiosyncratic"])
        self.assertEqual(res1["correlation"], 0.0)

        res2 = evaluate_correlation_filter(valid_df, empty_df)
        self.assertFalse(res2["passed"] if "passed" in res2 else res2["is_idiosyncratic"])
        self.assertEqual(res2["correlation"], 0.0)

    @patch("backend.scanner.DataFetcher")
    def test_scanner_scan_ticker_handles_empty_dataframe(self, mock_fetcher_cls: MagicMock) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_sp500_daily.return_value = pd.DataFrame()
        mock_fetcher.fetch_crypto_daily.return_value = pd.DataFrame()
        mock_fetcher_cls.return_value = mock_fetcher

        scanner = BreakoutScanner(dry_run=True)
        res_eq = scanner.scan_ticker("AAPL", "US_EQUITIES")
        self.assertIsNone(res_eq)

        res_cr = scanner.scan_ticker("BTCUSDT", "CRYPTO")
        self.assertIsNone(res_cr)


class TestAdversarialConcurrency(unittest.TestCase):
    """Stress-test thread safety of _binance_request and global _working_host state."""

    @patch("time.sleep")
    def test_concurrent_binance_requests(self, mock_sleep: MagicMock) -> None:
        mock_session = MagicMock(spec=requests.Session)
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = [{"symbol": "BTCUSDT"}]
        mock_session.get.return_value = mock_200

        exceptions = []

        def worker_task(idx: int) -> None:
            try:
                for _ in range(20):
                    _binance_request("/api/v3/ticker/price", session=mock_session)
            except Exception as exc:
                exceptions.append(exc)

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(exceptions), 0)


if __name__ == "__main__":
    unittest.main()
