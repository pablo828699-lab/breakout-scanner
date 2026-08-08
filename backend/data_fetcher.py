"""
Data fetching abstraction layer.

- US Equities: yfinance
- Crypto: Binance public REST API (no keys required for market data)
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np
import pandas as pd
import requests

import backend.config as cfg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent HTTP Session & Browser Headers
# ---------------------------------------------------------------------------
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_shared_session: requests.Session | None = None


def get_shared_session() -> requests.Session:
    """Return a singleton requests.Session configured with realistic browser User-Agent headers."""
    global _shared_session
    if _shared_session is None:
        _shared_session = requests.Session()
        _shared_session.headers.update(DEFAULT_HEADERS)
    return _shared_session


# ---------------------------------------------------------------------------
# Optional yfinance import (US Equities)
# ---------------------------------------------------------------------------
try:
    import yfinance as yf

    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
    logger.warning("yfinance not installed — US Equities data unavailable.")


# ---------------------------------------------------------------------------
# Binance public market-data hosts, tried in order.
# api.binance.com is geo-blocked (HTTP 451) from many US datacenter IPs
# (GitHub Actions / Render / Railway), so data-api.binance.vision — the public
# data-only mirror with the same /api/v3 schema — is used as a fallback.
# ---------------------------------------------------------------------------
_BINANCE_HOSTS = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
)

# Remembers the last host that worked so we don't re-try a geo-blocked host on
# every symbol (halves scan time and stops log spam once the block is learned).
_working_host: str | None = None


def _binance_request(
    path: str,
    params: dict | None = None,
    timeout: int = 15,
    max_retries: int = 3,
    base_delay: float = 1.0,
    session: requests.Session | None = None,
) -> dict | list | None:
    """GET a Binance public endpoint, falling back across hosts on failure with exponential backoff.

    Tries the last known-good host first, then the rest. Reuses a persistent session.
    Returns the parsed JSON on the first host that responds, or ``None`` if every host fails.
    """
    global _working_host

    sess = session or get_shared_session()
    hosts = list(_BINANCE_HOSTS)
    if _working_host in hosts:
        hosts.remove(_working_host)
        hosts.insert(0, _working_host)

    last_error: str | None = None
    for host in hosts:
        url = f"{host}{path}"
        for attempt in range(1, max_retries + 1):
            try:
                resp = sess.get(url, params=params, timeout=timeout)
                if resp.status_code == 451:
                    last_error = f"{host} → 451 (geo-blocked)"
                    if _working_host != host:  # only log the first time we learn it
                        logger.warning("Binance host %s geo-blocked (451) — trying next host.", host)
                    break  # geo-blocked host won't recover on retry, move to next host

                if resp.status_code in (429, 418) or resp.status_code >= 500:
                    last_error = f"{host} → HTTP {resp.status_code}: {resp.text[:100]}"
                    if attempt < max_retries:
                        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                        logger.warning(
                            "Binance host %s returned status %d on attempt %d/%d — retrying in %.2fs...",
                            host, resp.status_code, attempt, max_retries, delay
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            "Binance host %s exhausted %d retries with status %d — trying next host.",
                            host, max_retries, resp.status_code
                        )
                        break

                resp.raise_for_status()
                if _working_host != host:
                    logger.info("Binance host %s is working — caching as primary.", host)
                    _working_host = host
                return resp.json()

            except requests.exceptions.RequestException as exc:
                last_error = f"{host} → {type(exc).__name__}: {exc}"
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                    logger.warning(
                        "Binance request to %s failed (%s) on attempt %d/%d — retrying in %.2fs...",
                        url, exc, attempt, max_retries, delay
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        "Binance host %s failed after %d attempts (%s) — trying next host.",
                        host, max_retries, exc
                    )
                    break
            except Exception as exc:
                last_error = f"{host} → {type(exc).__name__}: {exc}"
                logger.error("Unexpected error requesting Binance host %s: %s", host, exc)
                break

    _working_host = None  # reset so the next call re-probes from the top
    logger.error("All Binance hosts failed for %s. Last error: %s", path, last_error)
    return None


class DataFetcher:
    """Unified data access for both US equities and crypto markets."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._crypto_tickers_cache: List[str] | None = None
        self._session = session or get_shared_session()
        self._yf_session = self._session

    def get_session(self) -> requests.Session:
        """Return the persistent HTTP session used by this DataFetcher."""
        return self._session

    # ------------------------------------------------------------------
    #  S&P 500  (yfinance)
    # ------------------------------------------------------------------

    def _safe_yf_download(
        self,
        ticker: str,
        period: str,
        interval: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> pd.DataFrame:
        """Safely fetch historical data from Yahoo Finance using custom session with browser User-Agent and exponential backoff."""
        if not _YF_AVAILABLE:
            return pd.DataFrame()

        # Apply micro-pacing delay if configured
        pace_delay = getattr(cfg, "REQUEST_PACE_DELAY_SEC", 0.0)
        if pace_delay > 0:
            time.sleep(pace_delay)

        download_kwargs = {
            "period": period,
            "interval": interval,
            "progress": False,
            "auto_adjust": True,
        }
        if self._yf_session is not None:
            download_kwargs["session"] = self._yf_session

        for attempt in range(1, max_retries + 1):
            try:
                df = yf.download(ticker, **download_kwargs)
                if df is not None and not df.empty:
                    return df
                logger.warning(
                    "yfinance download returned empty DataFrame for %s (attempt %d/%d).",
                    ticker, attempt, max_retries,
                )
            except Exception as exc:
                logger.warning(
                    "yfinance download error for %s on attempt %d/%d: %s",
                    ticker, attempt, max_retries, exc,
                )

            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                logger.info("Retrying yfinance download for %s in %.2fs...", ticker, delay)
                time.sleep(delay)

        logger.error("yfinance download failed for %s after %d retries.", ticker, max_retries)
        return pd.DataFrame()

    def _fetch_hyperliquid_candles(self, ticker: str, interval: str = "1h") -> pd.DataFrame:
        """Fetch 24/7 candles directly from Hyperliquid public API for a given symbol."""
        url = "https://api.hyperliquid.xyz/info"
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (30 * 24 * 3600 * 1000)
        
        candidates = [ticker]
        if ticker.endswith("USDT"):
            candidates.append(ticker.replace("USDT", ""))
        if not ticker.startswith("xyz:"):
            candidates.append(f"xyz:{ticker}")

        for coin_name in candidates:
            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": coin_name,
                    "interval": interval,
                    "startTime": start_ms,
                    "endTime": now_ms,
                }
            }
            try:
                resp = self._session.post(url, json=payload, timeout=8)
                if resp.status_code == 200:
                    raw_candles = resp.json()
                    if raw_candles and isinstance(raw_candles, list) and len(raw_candles) > 10:
                        records = []
                        for c in raw_candles:
                            records.append({
                                "Open": float(c["o"]),
                                "High": float(c["h"]),
                                "Low": float(c["l"]),
                                "Close": float(c["c"]),
                                "Volume": float(c["v"]),
                                "Timestamp": pd.to_datetime(c["t"], unit="ms", utc=True),
                            })
                        df = pd.DataFrame(records)
                        df.set_index("Timestamp", inplace=True)
                        logger.info("Hyperliquid API returned %d 24/7 %s candles for %s (%s).", len(df), interval, ticker, coin_name)
                        return df
            except Exception as exc:
                logger.debug("Hyperliquid candle fetch attempt failed for %s (%s): %s", ticker, coin_name, exc)
                
        return pd.DataFrame()

    def fetch_sp500_daily(self, ticker: str) -> pd.DataFrame:
        """Fetch ~6 months of daily OHLCV for a US equity ticker, prioritizing Hyperliquid 24/7 API."""
        hl_df = self._fetch_hyperliquid_candles(ticker, "1d")
        if not hl_df.empty:
            return hl_df

        df = self._safe_yf_download(ticker, f"{cfg.DAILY_LOOKBACK_DAYS}d", "1d")
        if df.empty:
            logger.warning("No daily data returned for %s.", ticker)
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df

    def fetch_sp500_hourly(self, ticker: str) -> pd.DataFrame:
        """Fetch ~1 month of 1-hour OHLCV for a US equity ticker, prioritizing Hyperliquid 24/7 API."""
        hl_df = self._fetch_hyperliquid_candles(ticker, "1h")
        if not hl_df.empty:
            return hl_df

        df = self._safe_yf_download(ticker, "1mo", "1h")
        if df.empty:
            logger.warning("No hourly data returned for %s.", ticker)
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        logger.info(
            "fetch_sp500_hourly for %s: downloaded %d candles. Last candle: Open=%.4f Close=%.4f Vol=%.0f Time=%s",
            ticker,
            len(df),
            float(df["Open"].iloc[-1]),
            float(df["Close"].iloc[-1]),
            float(df["Volume"].iloc[-1]),
            str(df.index[-1])
        )
        return df

    # ------------------------------------------------------------------
    #  Crypto  (Binance public REST API)
    # ------------------------------------------------------------------

    def _binance_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """Fetch klines from Binance public API (no authentication needed)."""
        pace_delay = getattr(cfg, "REQUEST_PACE_DELAY_SEC", 0.0)
        if pace_delay > 0:
            time.sleep(pace_delay)

        raw = _binance_request(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            session=self._session,
        )
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

    def _fetch_yfinance_crypto(self, yf_symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch historical crypto data from Yahoo Finance as a backup."""
        df = self._safe_yf_download(yf_symbol, period, interval)
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        required = ["Open", "High", "Low", "Close", "Volume"]
        if all(c in df.columns for c in required):
            return df[required]
        return pd.DataFrame()

    def fetch_crypto_daily(self, symbol: str) -> pd.DataFrame:
        """Fetch ~180 daily candles for a crypto pair (tries Binance, falls back to yfinance)."""
        df = self._binance_klines(symbol, "1d", cfg.DAILY_LOOKBACK_DAYS)
        if df.empty:
            logger.warning("Binance daily empty for %s — trying Yahoo Finance fallback.", symbol)
            yf_symbol = symbol.replace("USDT", "-USD")
            df = self._fetch_yfinance_crypto(yf_symbol, f"{cfg.DAILY_LOOKBACK_DAYS}d", "1d")

        if df.empty:
            logger.error("Crypto daily data unavailable for %s across Binance and Yahoo Finance.", symbol)
            return pd.DataFrame()
        return df

    def fetch_crypto_hourly(self, symbol: str) -> pd.DataFrame:
        """Fetch ~120 hourly candles (tries Binance, falls back to yfinance)."""
        limit = cfg.HOURLY_LOOKBACK_DAYS * 24
        df = self._binance_klines(symbol, "1h", limit)
        if df.empty:
            logger.warning("Binance hourly empty for %s — trying Yahoo Finance fallback.", symbol)
            yf_symbol = symbol.replace("USDT", "-USD")
            df = self._fetch_yfinance_crypto(yf_symbol, f"{cfg.HOURLY_LOOKBACK_DAYS}d", "1h")

        if df.empty:
            logger.error("Crypto hourly data unavailable for %s across Binance and Yahoo Finance.", symbol)
            return pd.DataFrame()
        return df

    # ------------------------------------------------------------------
    #  Dynamic top-N crypto tickers by 24h volume
    # ------------------------------------------------------------------

    def get_crypto_tickers(self) -> List[str]:
        """Return the crypto universe to scan.

        Defaults to the curated watchlist (quality/liquid assets). Set
        ``CRYPTO_USE_WATCHLIST=false`` to use the dynamic top-N by 24h volume.
        """
        if self._crypto_tickers_cache is not None:
            return self._crypto_tickers_cache

        if cfg.CRYPTO_USE_WATCHLIST:
            self._crypto_tickers_cache = list(cfg.CRYPTO_WATCHLIST)
            logger.info("Using curated crypto watchlist (%d assets).", len(self._crypto_tickers_cache))
            return self._crypto_tickers_cache

        stablecoins = {
            "USDC", "USDT", "BUSD", "TUSD", "PAX", "DAI", "EUR", "FDUSD",
            "AEUR", "USDS", "GBP", "TRY", "RUB", "UAH", "BIDR", "PEPE", "SHIB",
            # Additional stable/fiat-pegged tokens that leak into the top-N by volume
            "USD1", "USDE", "USDD", "USDP", "PYUSD", "FRAX", "GUSD", "LUSD",
            "EURI", "XUSD", "USDG", "FDUSD", "RLUSD", "XAUT", "PAXG",
        }

        try:
            tickers_raw = _binance_request("/api/v3/ticker/24hr", session=self._session)
            if not tickers_raw:
                raise RuntimeError("all Binance hosts unavailable")

            # Filter to USDT pairs only, exclude leveraged/down tokens, stablecoins/
            # fiat-pegs, and junk/promo pairs (non-ASCII symbols).
            usdt_pairs = [
                t for t in tickers_raw
                if t["symbol"].endswith("USDT")
                and t["symbol"].isascii()
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
    #  Mock data generator (standalone utility, not auto-invoked)
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
