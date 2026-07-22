"""
Unit and integration tests for backend/data_fetcher.py, backend/config.py, and backend/fundamental_filter.py.
Verifies persistent HTTP sessions, realistic browser headers, retry & exponential backoff logic,
un-muted yfinance logger & error handling, micro-pacing, and elimination of mock data fallbacks.
"""

import logging
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
from backend.fundamental_filter import fetch_fundamentals, run_fundamental_filter


class TestDataFetcherSessionAndHeaders(unittest.TestCase):
    """Test persistent HTTP session creation and realistic browser headers."""

    def test_shared_session_headers(self) -> None:
        session = get_shared_session()
        self.assertIsInstance(session, requests.Session)
        self.assertIn("User-Agent", session.headers)
        self.assertIn("Mozilla/5.0", session.headers["User-Agent"])
        self.assertIn("Chrome/", session.headers["User-Agent"])

    def test_data_fetcher_session_init(self) -> None:
        fetcher = DataFetcher()
        session = fetcher.get_session()
        self.assertIsInstance(session, requests.Session)
        self.assertEqual(session.headers.get("User-Agent"), DEFAULT_HEADERS["User-Agent"])


class TestBinanceRetryAndBackoff(unittest.TestCase):
    """Test exponential backoff retries and host failover for Binance requests."""

    @patch("time.sleep")
    def test_binance_request_retry_on_500(self, mock_sleep: MagicMock) -> None:
        mock_session = MagicMock(spec=requests.Session)
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = [{"symbol": "BTCUSDT", "price": "60000"}]

        # 2 failed attempts, 3rd succeeds
        mock_session.get.side_effect = [
            mock_response_500,
            mock_response_500,
            mock_response_200,
        ]

        result = _binance_request(
            "/api/v3/ticker/price",
            max_retries=3,
            base_delay=0.1,
            session=mock_session,
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(mock_session.get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("time.sleep")
    def test_binance_request_451_geo_blocked_immediate_failover(
        self, mock_sleep: MagicMock
    ) -> None:
        mock_session = MagicMock(spec=requests.Session)
        mock_response_451 = MagicMock()
        mock_response_451.status_code = 451

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = [{"symbol": "ETHUSDT", "price": "3000"}]

        # Host 1 returns 451 immediately, host 2 returns 200
        mock_session.get.side_effect = [
            mock_response_451,
            mock_response_200,
        ]

        result = _binance_request(
            "/api/v3/ticker/price",
            max_retries=3,
            base_delay=0.1,
            session=mock_session,
        )

        self.assertIsNotNone(result)
        self.assertEqual(mock_session.get.call_count, 2)
        # Should not sleep on 451 (should failover immediately to secondary host)
        self.assertEqual(mock_sleep.call_count, 0)


class TestYfinanceRetryAndErrorHandling(unittest.TestCase):
    """Test Yahoo Finance download retries, logging, and stderr un-muting."""

    @patch("time.sleep")
    @patch("backend.data_fetcher.yf.download")
    def test_safe_yf_download_retry_on_empty(
        self, mock_yf_download: MagicMock, mock_sleep: MagicMock
    ) -> None:
        fetcher = DataFetcher()

        # First attempt returns empty, second returns valid DataFrame
        valid_df = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.date_range("2026-01-01", periods=2),
        )
        mock_yf_download.side_effect = [pd.DataFrame(), valid_df]

        with patch.object(cfg, "REQUEST_PACE_DELAY_SEC", 0.0):
            df = fetcher._safe_yf_download("AAPL", "1mo", "1d", max_retries=2, base_delay=0.1)

        self.assertFalse(df.empty)
        self.assertEqual(len(df), 2)
        self.assertEqual(mock_yf_download.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    def test_yfinance_logger_unmuted(self) -> None:
        cfg.configure_logging()
        yf_logger = logging.getLogger("yfinance")
        self.assertLessEqual(yf_logger.level, logging.WARNING)


class TestEliminateSilentMockFallback(unittest.TestCase):
    """Verify that empty data returns empty DataFrame without silent mock generation."""

    @patch("backend.data_fetcher.DataFetcher._fetch_yfinance_crypto")
    @patch("backend.data_fetcher.DataFetcher._binance_klines")
    def test_fetch_crypto_daily_returns_empty_on_failure(
        self, mock_binance: MagicMock, mock_yf: MagicMock
    ) -> None:
        mock_binance.return_value = pd.DataFrame()
        mock_yf.return_value = pd.DataFrame()

        fetcher = DataFetcher()
        df = fetcher.fetch_crypto_daily("BTCUSDT")

        self.assertTrue(df.empty)

    @patch("backend.data_fetcher.DataFetcher._fetch_yfinance_crypto")
    @patch("backend.data_fetcher.DataFetcher._binance_klines")
    def test_fetch_crypto_hourly_returns_empty_on_failure(
        self, mock_binance: MagicMock, mock_yf: MagicMock
    ) -> None:
        mock_binance.return_value = pd.DataFrame()
        mock_yf.return_value = pd.DataFrame()

        fetcher = DataFetcher()
        df = fetcher.fetch_crypto_hourly("BTCUSDT")

        self.assertTrue(df.empty)


class TestFundamentalFilterSessionLeak(unittest.TestCase):
    """Test passing custom session to fundamental filter."""

    @patch("backend.fundamental_filter.yf.Ticker")
    def test_fetch_fundamentals_uses_session(self, mock_ticker: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.quarterly_financials = pd.DataFrame()
        mock_instance.quarterly_balance_sheet = pd.DataFrame()
        mock_ticker.return_value = mock_instance

        custom_session = requests.Session()
        custom_session.headers.update({"User-Agent": "TestAgent/1.0"})

        fetch_fundamentals("AAPL", session=custom_session)

        mock_ticker.assert_called_once_with("AAPL", session=custom_session)

    @patch("backend.fundamental_filter.fetch_fundamentals")
    def test_run_fundamental_filter_passes_session(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = None
        custom_session = requests.Session()

        run_fundamental_filter("AAPL", "US_EQUITIES", session=custom_session)

        mock_fetch.assert_called_once_with("AAPL", session=custom_session)


class TestMicroPacing(unittest.TestCase):
    """Test inter-request micro-pacing delay."""

    @patch("time.sleep")
    @patch("backend.data_fetcher._binance_request")
    def test_binance_klines_applies_pacing(
        self, mock_request: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_request.return_value = []
        with patch.object(cfg, "REQUEST_PACE_DELAY_SEC", 0.1):
            fetcher = DataFetcher()
            fetcher._binance_klines("BTCUSDT", "1d", 10)
            mock_sleep.assert_called_with(0.1)


if __name__ == "__main__":
    unittest.main()
