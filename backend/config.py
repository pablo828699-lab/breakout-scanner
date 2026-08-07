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
PROXIMITY_THRESHOLD_PCT: float = float(os.getenv("PROXIMITY_THRESHOLD_PCT", "0.012"))
MIN_TOUCHES: int = int(os.getenv("MIN_TOUCHES", "2"))

# ---------------------------------------------------------------------------
# Volume Filter
# ---------------------------------------------------------------------------
VOLUME_MULTIPLIER: float = float(os.getenv("VOLUME_MULTIPLIER", "1.2"))
VOLUME_SMA_PERIOD: int = int(os.getenv("VOLUME_SMA_PERIOD", "20"))

# ---------------------------------------------------------------------------
# Breakout Confirmation
# ---------------------------------------------------------------------------
# Minimum penetration beyond the level, as a fraction of ATR, for the 1H body
# close to count as a valid break (filters marginal pokes / stop-runs).
PENETRATION_ATR_MULT: float = float(os.getenv("PENETRATION_ATR_MULT", "0.02"))

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
# Trend Radar — detection mode
# ---------------------------------------------------------------------------
# "radar"    → surface assets that just completed a trending move (Donchian /
#              momentum impulse) filtered by ADX + EMA alignment. No SL/TP.
# "breakout" → legacy per-trade breakout signals with structural SL/TP.
DETECTION_MODE: str = os.getenv("DETECTION_MODE", "radar").lower()

# Trend filter (daily timeframe)
RADAR_ADX_PERIOD: int = int(os.getenv("RADAR_ADX_PERIOD", "14"))
RADAR_ADX_MIN: float = float(os.getenv("RADAR_ADX_MIN", "18.0"))
RADAR_EMA_FAST: int = int(os.getenv("RADAR_EMA_FAST", "50"))
RADAR_EMA_SLOW: int = int(os.getenv("RADAR_EMA_SLOW", "200"))

# Triggers
RADAR_DONCHIAN_N: int = int(os.getenv("RADAR_DONCHIAN_N", "15"))       # new N-day high/low
RADAR_IMPULSE_ATR_MULT: float = float(os.getenv("RADAR_IMPULSE_ATR_MULT", "1.2"))  # range > x*ATR
RADAR_IMPULSE_VOLUME_MULT: float = float(os.getenv("RADAR_IMPULSE_VOLUME_MULT", "1.2"))
RADAR_ROC_PERIOD: int = int(os.getenv("RADAR_ROC_PERIOD", "10"))       # momentum lookback (days)

# De-duplication: don't re-alert the same asset+direction within this window.
# Lets the radar re-fire on a genuinely new move without spamming the same day.
ALERT_COOLDOWN_HOURS: float = float(os.getenv("ALERT_COOLDOWN_HOURS", "12"))

# ---------------------------------------------------------------------------
# Lookback Windows
# ---------------------------------------------------------------------------
# Needs to comfortably exceed RADAR_EMA_SLOW (200) so the daily EMA200 is well-formed.
DAILY_LOOKBACK_DAYS: int = int(os.getenv("DAILY_LOOKBACK_DAYS", "300"))
HOURLY_LOOKBACK_DAYS: int = int(os.getenv("HOURLY_LOOKBACK_DAYS", "5"))

# ---------------------------------------------------------------------------
# Equities, ETFs & Commodities — Strictly Hyperliquid Perps List (64 Assets)
# ---------------------------------------------------------------------------
SP500_TICKERS: List[str] = [
    # Megacap & Tech Perps
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "IBM",
    "NFLX", "MU", "BABA", "COIN", "MSTR", "MRVL", "AMD", "INTC",
    "AVGO", "ORCL", "TSM", "ASML", "ARM", "DELL", "WDC",
    # High-Beta & Growth Perps
    "DKNG", "RKLB", "HIMS", "PLTR", "HOOD", "LLY", "CL", "USAR",
    "BE", "STRC", "BOT", "SHAZ", "QNT", "NBIS", "CBRS", "SOXL",
    "LITE", "SKHY", "CRCL", "DRAM", "CRWV", "BB", "LYTE",
    "NOW", "SNDK", "SKHX", "KORU", "SPCX",
    # ETFs, Commodities & FX (GOLD=GLD, SILVER=SLV, BRENTOIL=USO, NATGAS=UNG, SP500=SPY, JP225=EWJ, KR200=EWY, EUR=FXE, JPY=FXY, PLATINUM=PPLT, COPPER=CPER)
    "GLD", "SLV", "USO", "UNG", "SPY", "EWJ", "EWY", "FXE", "FXY", "PPLT", "CPER"
]

# ---------------------------------------------------------------------------
# Crypto Perps — Strictly Hyperliquid Perps List (19 Assets)
# ---------------------------------------------------------------------------
CRYPTO_TOP_N: int = int(os.getenv("CRYPTO_TOP_N", "40"))
CRYPTO_USE_WATCHLIST: bool = os.getenv("CRYPTO_USE_WATCHLIST", "true").lower() in ("true", "1", "yes")

# Strict Hyperliquid Crypto Perps List
CRYPTO_WATCHLIST: List[str] = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "ADAUSDT",
    "NEARUSDT", "ZECUSDT", "XMRUSDT", "UNIUSDT", "ENAUSDT", "ONDOUSDT",
    "WLDUSDT", "ACEUSDT", "PAXGUSDT", "LITUSDT", "XPLUSDT", "PUMPUSDT",
    "CASHCATUSDT"
]

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
# Scanner Timing & Rate-Limiting Micro-Pacing
# ---------------------------------------------------------------------------
SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))
REQUEST_PACE_DELAY_SEC: float = float(os.getenv("REQUEST_PACE_DELAY_SEC", "0.1"))

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Set up root logging with the configured level and format, outputting to console and app.log."""
    import sys
    from pathlib import Path
    
    numeric_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    if not root_logger.handlers:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        
        # Console handler with UTF-8 enforcement to prevent Windows console encoding errors
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # File handler for remote diagnostics
        try:
            log_filepath = Path(__file__).resolve().parent / "app.log"
            file_handler = logging.FileHandler(log_filepath, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception:
            pass # Fallback if file system is read-only
            
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("binance").setLevel(logging.WARNING)

