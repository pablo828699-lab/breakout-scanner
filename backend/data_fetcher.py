"""
Data fetching abstraction layer.

- US Equities: yfinance
- Crypto: Binance public REST API (no keys required for market data)
- Fallback: Numpy-generated random-walk mock data for crypto
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np
import pandas as pd
import requests

import backend.config as cfg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional yfinance import (US Equities)
# ---------------------------------------------------------------------------
try:
    import yfinance as yf

    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
    logger.warning("yfinance not installed — US Equities data unavailable.")


class DataFetcher:
    """Unified data access for both US equities and crypto markets."""

    def __init__(self) -> None:
        self._crypto_tickers_cache: List[str] | None = None

    # ------------------------------------------------------------------
    #  S&P 500  (yfinance)
    # ------------------------------------------------------------------

    def fetch_sp500_daily(self, ticker: str) -> pd.DataFrame:
        """Fetch ~6 months of daily OHLCV for a US equity ticker."""
        if not _YF_AVAILABLE:
            logger.error("yfinance unavailable — cannot fetch %s daily.", ticker)
            return pd.DataFrame()
        try:
            df = yf.download(
                ticker,
                period=f"{cfg.DAILY_LOOKBACK_DAYS}d",
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            if df.empty:
                logger.warning("No daily data returned for %s.", ticker)
            return df
        except Exception as exc:
            logger.error("yfinance daily fetch error for %s: %s", ticker, exc)
            return pd.DataFrame()

    def fetch_sp500_hourly(self, ticker: str) -> pd.DataFrame:
        """Fetch ~5 days of 1-hour OHLCV for a US equity ticker."""
        if not _YF_AVAILABLE:
            logger.error("yfinance unavailable — cannot fetch %s hourly.", ticker)
            return pd.DataFrame()
        try:
            df = yf.download(
                ticker,
                period=f"{cfg.HOURLY_LOOKBACK_DAYS}d",
                interval="1h",
                progress=False,
                auto_adjust=True,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            if df.empty:
                logger.warning("No hourly data returned for %s.", ticker)
            return df
        except Exception as exc:
            logger.error("yfinance hourly fetch error for %s: %s", ticker, exc)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    #  Crypto  (Binance public REST API)
    # ------------------------------------------------------------------

    @staticmethod
    def _binance_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """Fetch klines from Binance public API (no authentication needed)."""
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            logger.error("Binance klines error for %s (%s): %s", symbol, interval, exc)
            return pd.DataFrame()

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(
            raw,
            columns=[
                "OpenTime", "Open", "High", "Low", "Close", "Volume",
                "CloseTime", "QuoteVolume", "Trades", "TakerBuyBase",
                "TakerBuyQuote", "Ignore",
            ],
        )
        df["Open"] = df["Open"].astype(float)
        df["High"] = df["High"].astype(float)
        df["Low"] = df["Low"].astype(float)
        df["Close"] = df["Close"].astype(float)
        df["Volume"] = df["Volume"].astype(float)
        df.index = pd.to_datetime(df["OpenTime"], unit="ms", utc=True)
        df.index.name = "Date"
        return df[["Open", "High", "Low", "Close", "Volume"]]

    def fetch_crypto_daily(self, symbol: str) -> pd.DataFrame:
        """Fetch ~180 daily candles for a crypto pair from Binance."""
        df = self._binance_klines(symbol, "1d", cfg.DAILY_LOOKBACK_DAYS)
        if df.empty:
            logger.warning("Binance daily empty for %s — generating mock data.", symbol)
            return self._generate_mock_ohlcv(180, base_price=50000.0 if "BTC" in symbol else 2000.0)
        return df

    def fetch_crypto_hourly(self, symbol: str) -> pd.DataFrame:
        """Fetch ~120 hourly candles (5 days) for a crypto pair from Binance."""
        limit = cfg.HOURLY_LOOKBACK_DAYS * 24
        df = self._binance_klines(symbol, "1h", limit)
        if df.empty:
            logger.warning("Binance hourly empty for %s — generating mock data.", symbol)
            return self._generate_mock_ohlcv(limit, base_price=50000.0 if "BTC" in symbol else 2000.0)
        return df

    # ------------------------------------------------------------------
    #  Dynamic top-N crypto tickers by 24h volume
    # ------------------------------------------------------------------

    def get_crypto_tickers(self) -> List[str]:
        """Return top N USDT spot pairs by 24h quote volume from Binance."""
        if self._crypto_tickers_cache is not None:
            return self._crypto_tickers_cache

        try:
            url = "https://api.binance.com/api/v3/ticker/24hr"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            tickers_raw = resp.json()

            # Filter to USDT pairs only, exclude leveraged/down tokens and stablecoins/fiat pegs
            stablecoins = {
                "USDC", "USDT", "BUSD", "TUSD", "PAX", "DAI", "EUR", "FDUSD", 
                "AEUR", "USDS", "GBP", "TRY", "RUB", "UAH", "BIDR", "PEPE", "SHIB"
            }
            usdt_pairs = [
                t for t in tickers_raw
                if t["symbol"].endswith("USDT")
                and not any(x in t["symbol"] for x in ["UP", "DOWN", "BEAR", "BULL"])
                and not any(t["symbol"].startswith(s) for s in stablecoins)
            ]

            # Sort by 24h quote volume descending
            usdt_pairs.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)

            top_n = [t["symbol"] for t in usdt_pairs[: cfg.CRYPTO_TOP_N]]
            logger.info("Fetched top %d crypto tickers by 24h volume (excl. stablecoins): %s", len(top_n), top_n[:5])
            self._crypto_tickers_cache = top_n
            return top_n

        except Exception as exc:
            logger.error("Failed to fetch Binance 24hr tickers: %s — using fallback list.", exc)
            self._crypto_tickers_cache = [
                t for t in cfg.CRYPTO_FALLBACK_TICKERS 
                if not any(t.startswith(s) for s in stablecoins)
            ][: cfg.CRYPTO_TOP_N]
            return self._crypto_tickers_cache

    def get_sp500_tickers(self) -> List[str]:
        """Return the configured S&P 500 ticker list."""
        return cfg.SP500_TICKERS

    # ------------------------------------------------------------------
    #  Mock data generator (fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_mock_ohlcv(
        periods: int,
        base_price: float = 100.0,
        volatility: float = 0.015,
    ) -> pd.DataFrame:
        """Generate realistic random-walk OHLCV data for testing."""
        rng = np.random.default_rng(seed=42)
        returns = rng.normal(0, volatility, periods)
        closes = base_price * np.exp(np.cumsum(returns))

        highs = closes * (1 + rng.uniform(0, volatility, periods))
        lows = closes * (1 - rng.uniform(0, volatility, periods))
        opens = np.roll(closes, 1)
        opens[0] = base_price
        volumes = rng.uniform(1_000_000, 10_000_000, periods)

        dates = pd.date_range(
            end=datetime.now(tz=timezone.utc),
            periods=periods,
            freq="h",
        )

        df = pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
            index=dates,
        )
        df.index.name = "Date"
        return df
