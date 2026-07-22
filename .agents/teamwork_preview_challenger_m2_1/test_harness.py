"""
Empirical Stress Test Harness for data_fetcher.py and fundamental_filter.py
Executed by Challenger Agent (teamwork_preview_challenger_m2_1)
"""

import sys
import os
import time
import logging
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import requests

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath("."))

import backend.config as cfg
from backend.data_fetcher import (
    DEFAULT_HEADERS,
    DataFetcher,
    _binance_request,
    _BINANCE_HOSTS,
    get_shared_session,
)
from backend.fundamental_filter import fetch_fundamentals, run_fundamental_filter

# Set up logging for test harness output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stress_test")


class TestEmpiricalChallenger(unittest.TestCase):

    def setUp(self):
        # Reset working host before each test
        import backend.data_fetcher as df_mod
        df_mod._working_host = None

    # -----------------------------------------------------------------------
    # 1. Verification of HTTP 429 / 5xx Retries & Backoff Timing
    # -----------------------------------------------------------------------
    @patch("time.sleep")
    def test_binance_request_429_exponential_backoff(self, mock_sleep):
        """Verify that 429 rate limit triggers exponential backoff and retries."""
        mock_session = MagicMock(spec=requests.Session)
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.text = "Too Many Requests"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"status": "ok"}

        # Attempt 1: 429, Attempt 2: 429, Attempt 3: 200
        mock_session.get.side_effect = [resp_429, resp_429, resp_200]

        result = _binance_request(
            "/api/v3/ping",
            max_retries=3,
            base_delay=1.0,
            session=mock_session,
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(mock_session.get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

        # Check sleep delays: 1st backoff base 1.0 * (2^0) + jitter [0.1..0.5] => ~1.1..1.5
        # 2nd backoff base 1.0 * (2^1) + jitter [0.1..0.5] => ~2.1..2.5
        delay1 = mock_sleep.call_args_list[0][0][0]
        delay2 = mock_sleep.call_args_list[1][0][0]
        self.assertTrue(1.0 <= delay1 <= 1.6, f"Delay 1 was {delay1}")
        self.assertTrue(2.0 <= delay2 <= 2.6, f"Delay 2 was {delay2}")

    # -----------------------------------------------------------------------
    # 2. Verification of HTTP 451 Immediate Host Failover
    # -----------------------------------------------------------------------
    @patch("time.sleep")
    def test_binance_request_451_geo_blocked_failover(self, mock_sleep):
        """Verify HTTP 451 causes instant failover to secondary host with zero sleep retries."""
        mock_session = MagicMock(spec=requests.Session)
        resp_451 = MagicMock()
        resp_451.status_code = 451
        resp_451.text = "Unavailable For Legal Reasons"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"symbol": "BTCUSDT"}

        # Primary host returns 451, secondary host returns 200
        mock_session.get.side_effect = [resp_451, resp_200]

        result = _binance_request(
            "/api/v3/ticker/price",
            max_retries=3,
            base_delay=1.0,
            session=mock_session,
        )

        self.assertEqual(result, {"symbol": "BTCUSDT"})
        self.assertEqual(mock_session.get.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 0, "451 geo-block must not trigger sleep retries!")

        # Verify cached primary host updated
        import backend.data_fetcher as df_mod
        self.assertEqual(df_mod._working_host, "https://data-api.binance.vision")

    # -----------------------------------------------------------------------
    # 3. Host Failover Persistence on Subsequent Calls
    # -----------------------------------------------------------------------
    def test_binance_working_host_cached_across_calls(self):
        """Verify that once primary host is learned, subsequent requests skip the blocked host."""
        mock_session = MagicMock(spec=requests.Session)
        resp_451 = MagicMock()
        resp_451.status_code = 451
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"symbol": "BTCUSDT"}

        # Call 1: Host 1 -> 451, Host 2 -> 200
        mock_session.get.side_effect = [resp_451, resp_200]
        res1 = _binance_request("/api/v3/ticker/price", session=mock_session)
        self.assertIsNotNone(res1)
        self.assertEqual(mock_session.get.call_count, 2)

        # Call 2: Host 2 is now first host. Host 2 -> 200
        mock_session.get.reset_mock()
        mock_session.get.side_effect = [resp_200]
        res2 = _binance_request("/api/v3/ticker/price", session=mock_session)
        self.assertIsNotNone(res2)
        self.assertEqual(mock_session.get.call_count, 1)
        # Verify the call went directly to host 2 (data-api.binance.vision)
        first_call_url = mock_session.get.call_args_list[0][0][0]
        self.assertTrue(first_call_url.startswith("https://data-api.binance.vision"))

    # -----------------------------------------------------------------------
    # 4. Stress Test: Client Errors (400 Bad Request / 404 Not Found)
    # -----------------------------------------------------------------------
    @patch("time.sleep")
    def test_binance_request_400_bad_request_behavior(self, mock_sleep):
        """Test how _binance_request handles HTTP 400 Bad Request."""
        mock_session = MagicMock(spec=requests.Session)
        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.text = '{"code":-1121,"msg":"Invalid symbol."}'
        resp_400.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Client Error", response=resp_400)

        mock_session.get.return_value = resp_400

        result = _binance_request(
            "/api/v3/klines",
            params={"symbol": "NONEXISTENT_SYMBOL"},
            max_retries=3,
            base_delay=0.1,
            session=mock_session,
        )

        self.assertIsNone(result)
        # Currently, HTTPError gets caught by RequestException and retried max_retries per host.
        # 2 hosts * 3 retries = 6 get calls.
        self.assertEqual(mock_session.get.call_count, 6)

    # -----------------------------------------------------------------------
    # 5. Stress Test: Dict Response in _binance_klines (e.g. error payload dict)
    # -----------------------------------------------------------------------
    @patch("backend.data_fetcher._binance_request")
    def test_binance_klines_handles_dict_response(self, mock_request):
        """Test how _binance_klines handles a dictionary payload (e.g. error dict) instead of list."""
        mock_request.return_value = {"code": -1100, "msg": "Illegal characters"}
        fetcher = DataFetcher()

        # If _binance_request returns a dict, pd.DataFrame(dict) won't have kline list layout.
        # Let's test if it raises an Exception or handles it cleanly.
        try:
            df = fetcher._binance_klines("INVALID", "1d", 10)
            # If it didn't raise an exception, check if it's handled or empty
            logger.info("Dict payload handled, df shape: %s", df.shape)
        except Exception as exc:
            logger.warning("Dict payload raised exception in _binance_klines: %s", exc)

    # -----------------------------------------------------------------------
    # 6. Verification of Empty DataFrame Fallback (No Mock Data)
    # -----------------------------------------------------------------------
    @patch("backend.data_fetcher.DataFetcher._fetch_yfinance_crypto")
    @patch("backend.data_fetcher.DataFetcher._binance_klines")
    def test_crypto_fetchers_no_mock_data(self, mock_binance, mock_yf):
        """Verify fetch_crypto_daily and fetch_crypto_hourly return empty DataFrames when both sources fail."""
        mock_binance.return_value = pd.DataFrame()
        mock_yf.return_value = pd.DataFrame()

        fetcher = DataFetcher()

        df_daily = fetcher.fetch_crypto_daily("BTCUSDT")
        self.assertTrue(isinstance(df_daily, pd.DataFrame))
        self.assertTrue(df_daily.empty, "fetch_crypto_daily must return empty DataFrame, NOT mock data!")

        df_hourly = fetcher.fetch_crypto_hourly("BTCUSDT")
        self.assertTrue(isinstance(df_hourly, pd.DataFrame))
        self.assertTrue(df_hourly.empty, "fetch_crypto_hourly must return empty DataFrame, NOT mock data!")

    # -----------------------------------------------------------------------
    # 7. Verification of yfinance Download Retry & MultiIndex Column Handling
    # -----------------------------------------------------------------------
    @patch("time.sleep")
    @patch("backend.data_fetcher.yf.download")
    def test_safe_yf_download_and_multiindex_flattening(self, mock_download, mock_sleep):
        """Test _safe_yf_download retry and fetch_sp500_daily MultiIndex column handling."""
        fetcher = DataFetcher()

        # Simulate MultiIndex columns from yfinance 0.2.x: tuple (Price, Ticker)
        tuples = [("Close", "AAPL"), ("High", "AAPL"), ("Low", "AAPL"), ("Open", "AAPL"), ("Volume", "AAPL")]
        multi_cols = pd.MultiIndex.from_tuples(tuples, names=["Price", "Ticker"])
        raw_df = pd.DataFrame(
            [[150.0, 155.0, 149.0, 151.0, 1000000]],
            columns=multi_cols,
            index=pd.date_range("2026-01-01", periods=1),
        )

        mock_download.return_value = raw_df

        df = fetcher.fetch_sp500_daily("AAPL")

        self.assertFalse(df.empty)
        # Check column names: droplevel(1) drops level 'Ticker' ('AAPL'), leaving ('Close', 'High', etc.)
        self.assertIn("Close", df.columns)
        self.assertIn("Open", df.columns)

    # -----------------------------------------------------------------------
    # 8. Verification of Micro-pacing Delay Execution
    # -----------------------------------------------------------------------
    @patch("time.sleep")
    @patch("backend.data_fetcher._binance_request")
    def test_micro_pacing_delay(self, mock_req, mock_sleep):
        """Verify micro-pacing delay is applied when REQUEST_PACE_DELAY_SEC > 0."""
        mock_req.return_value = []
        fetcher = DataFetcher()

        with patch.object(cfg, "REQUEST_PACE_DELAY_SEC", 0.15):
            fetcher._binance_klines("ETHUSDT", "1h", 10)
            mock_sleep.assert_called_with(0.15)

    # -----------------------------------------------------------------------
    # 9. Verification of Session Reuse & Headers
    # -----------------------------------------------------------------------
    def test_session_singleton_and_custom_headers(self):
        """Verify shared session returns same instance and browser headers."""
        s1 = get_shared_session()
        s2 = get_shared_session()
        self.assertIs(s1, s2)
        self.assertEqual(s1.headers["User-Agent"], DEFAULT_HEADERS["User-Agent"])

    # -----------------------------------------------------------------------
    # 10. Crypto Watchlist vs Dynamic Top-N Stablecoin Exclusions
    # -----------------------------------------------------------------------
    @patch("backend.data_fetcher._binance_request")
    def test_get_crypto_tickers_stablecoin_filtering(self, mock_req):
        """Verify dynamic crypto ticker fetching filters out stablecoins and junk pairs."""
        mock_req.return_value = [
            {"symbol": "BTCUSDT", "quoteVolume": "1000000000"},
            {"symbol": "USDCUSDT", "quoteVolume": "900000000"},   # Stablecoin pair
            {"symbol": "ETHUSDT", "quoteVolume": "800000000"},
            {"symbol": "FDUSDUSDT", "quoteVolume": "700000000"},  # Stablecoin pair
            {"symbol": "BTCUPUSDT", "quoteVolume": "600000000"},   # Leveraged token
            {"symbol": "PEPEUSDT", "quoteVolume": "500000000"},    # Excluded meme/stable list
            {"symbol": "SOLUSDT", "quoteVolume": "400000000"},
        ]

        fetcher = DataFetcher()

        with patch.object(cfg, "CRYPTO_USE_WATCHLIST", False):
            with patch.object(cfg, "CRYPTO_TOP_N", 3):
                tickers = fetcher.get_crypto_tickers()

        self.assertIn("BTCUSDT", tickers)
        self.assertIn("ETHUSDT", tickers)
        self.assertIn("SOLUSDT", tickers)
        self.assertNotIn("USDCUSDT", tickers)
        self.assertNotIn("FDUSDUSDT", tickers)
        self.assertNotIn("BTCUPUSDT", tickers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
