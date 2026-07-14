"""
Centralized configuration for the breakout scanner system.
All thresholds are loaded from environment variables with sensible defaults.
"""

import os
import logging
from typing import List


# ---------------------------------------------------------------------------
# Proximity / Level Detection
# ---------------------------------------------------------------------------
PROXIMITY_THRESHOLD_PCT: float = float(os.getenv("PROXIMITY_THRESHOLD_PCT", "0.005"))
MIN_TOUCHES: int = int(os.getenv("MIN_TOUCHES", "3"))

# ---------------------------------------------------------------------------
# Volume Filter
# ---------------------------------------------------------------------------
VOLUME_MULTIPLIER: float = float(os.getenv("VOLUME_MULTIPLIER", "1.5"))
VOLUME_SMA_PERIOD: int = int(os.getenv("VOLUME_SMA_PERIOD", "20"))

# ---------------------------------------------------------------------------
# Breakout Confirmation
# ---------------------------------------------------------------------------
# Minimum penetration beyond the level, as a fraction of ATR, for the 1H body
# close to count as a valid break (filters marginal pokes / stop-runs).
PENETRATION_ATR_MULT: float = float(os.getenv("PENETRATION_ATR_MULT", "0.15"))

# ---------------------------------------------------------------------------
# ATR / Risk Management
# ---------------------------------------------------------------------------
ATR_PERIOD: int = int(os.getenv("ATR_PERIOD", "14"))
RISK_REWARD_RATIO: float = float(os.getenv("RISK_REWARD_RATIO", "2.0"))

# Structural stop: placed beyond the breakout candle's extreme, with a small
# ATR buffer. A minimum distance floor prevents sub-noise stops; a maximum
# distance ceiling rejects chasing an over-extended entry.
SL_BUFFER_ATR_MULT: float = float(os.getenv("SL_BUFFER_ATR_MULT", "0.10"))
MIN_STOP_ATR_MULT: float = float(os.getenv("MIN_STOP_ATR_MULT", "0.5"))
MAX_STOP_ATR_MULT: float = float(os.getenv("MAX_STOP_ATR_MULT", "3.0"))

# Deprecated — kept for backward compat with existing .env files (unused).
ATR_SL_MULTIPLIER: float = float(os.getenv("ATR_SL_MULTIPLIER", "0.5"))

# ---------------------------------------------------------------------------
# Regime / Trend Filter
# ---------------------------------------------------------------------------
# Only take LONGs when the last daily close is above its SMA, and SHORTs when
# below — keeps breakouts aligned with the higher-timeframe trend.
TREND_FILTER_ENABLED: bool = os.getenv("TREND_FILTER_ENABLED", "true").lower() in ("true", "1", "yes")
TREND_MA_PERIOD: int = int(os.getenv("TREND_MA_PERIOD", "50"))

# ---------------------------------------------------------------------------
# Lookback Windows
# ---------------------------------------------------------------------------
DAILY_LOOKBACK_DAYS: int = int(os.getenv("DAILY_LOOKBACK_DAYS", "180"))
HOURLY_LOOKBACK_DAYS: int = int(os.getenv("HOURLY_LOOKBACK_DAYS", "5"))

# ---------------------------------------------------------------------------
# S&P 500 — Top ~50 most liquid tickers (static list)
# ---------------------------------------------------------------------------
SP500_TICKERS: List[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC",
    "XOM", "PFE", "KO", "PEP", "CSCO", "ABT", "CRM", "AVGO", "TMO",
    "COST", "NKE", "MRK", "ACN", "LLY", "ABBV", "MCD", "TXN", "QCOM",
    "DHR", "NEE", "ORCL", "ADBE", "AMD", "INTC", "AMGN", "PM", "HON",
    "UPS", "IBM", "GE", "CAT", "BA",
]

# ---------------------------------------------------------------------------
# Crypto Tickers — fetched dynamically as top N by 24h volume from Binance
# Fallback list used if the public API is unreachable.
# ---------------------------------------------------------------------------
CRYPTO_TOP_N: int = int(os.getenv("CRYPTO_TOP_N", "20"))
CRYPTO_FALLBACK_TICKERS: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "POLUSDT",
    "SHIBUSDT", "LINKUSDT", "TRXUSDT", "NEARUSDT", "UNIUSDT",
    "LTCUSDT", "APTUSDT", "ICPUSDT", "ATOMUSDT", "ARBUSDT",
]

# ---------------------------------------------------------------------------
# Telegram Configuration
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Binance Configuration
# ---------------------------------------------------------------------------
BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

# ---------------------------------------------------------------------------
# Scanner Timing
# ---------------------------------------------------------------------------
SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Set up root logging with the configured level and format."""
    numeric_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.CRITICAL + 1)
    logging.getLogger("binance").setLevel(logging.WARNING)
