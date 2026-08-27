"""
Ticker Mapper for Hyperliquid, Yahoo Finance, and Binance integration.

Normalizes tickers across platforms:
- Yahoo Finance: e.g. GC=F, ^GSPC, SI=F, CL=F, NVDA, PLTR
- Binance: e.g. BTCUSDT, ETHUSDT, SOLUSDT
- Hyperliquid: Main DEX (e.g. BTC, ETH, SOL) & HIP-3 DEX (e.g. xyz:NVDA, xyz:SPX, xyz:GOLD, xyz:CL)
"""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Static explicit mappings
YAHOO_TO_HL: Dict[str, str] = {
    "^GSPC": "xyz:SPX",
    "GC=F": "xyz:GOLD",
    "SI=F": "xyz:SILVER",
    "CL=F": "xyz:CL",
    "BZ=F": "xyz:BRENTOIL",
    "NG=F": "xyz:NG",
    "NATGAS": "xyz:NG",
    "NVDA": "xyz:NVDA",
    "PLTR": "xyz:PLTR",
    "AMD": "xyz:AMD",
    "INTC": "xyz:INTC",
    "QCOM": "xyz:QCOM",
    "AVGO": "xyz:AVGO",
    "TSM": "xyz:TSM",
    "AAPL": "xyz:AAPL",
    "MSFT": "xyz:MSFT",
    "GOOGL": "xyz:GOOGL",
    "META": "xyz:META",
    "AMZN": "xyz:AMZN",
    "ORCL": "xyz:ORCL",
    "CRM": "xyz:CRM",
    "SNOW": "xyz:SNOW",
    "NFLX": "xyz:NFLX",
    "XOM": "xyz:XOM",
    "CVX": "xyz:CVX",
    "SKHX": "xyz:SKHX",
    "MU": "xyz:MU",
    "MRVL": "xyz:MRVL",
    "ARM": "xyz:ARM",
    "DELL": "xyz:DELL",
    "SPCX": "xyz:SPCX",
    "CRCL": "xyz:CRCL",
    "BE": "xyz:BE",
    "LITE": "xyz:LITE",
}

BINANCE_TO_HL: Dict[str, str] = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "HYPEUSDT": "HYPE",
    "SUIUSDT": "SUI",
    "APTUSDT": "APT",
    "AVAXUSDT": "AVAX",
    "NEARUSDT": "NEAR",
    "TAOUSDT": "TAO",
    "DOGEUSDT": "DOGE",
}


def to_hyperliquid_symbol(ticker: str) -> str:
    """Normalize a ticker (from Yahoo or Binance) to its corresponding Hyperliquid symbol.

    Examples:
    - GC=F -> xyz:GOLD
    - BTCUSDT -> BTC
    - BTC -> BTC
    - NVDA -> xyz:NVDA
    - xyz:NVDA -> xyz:NVDA
    """
    clean = ticker.strip().upper()

    # Direct match in explicit dictionaries
    if clean in YAHOO_TO_HL:
        return YAHOO_TO_HL[clean]
    if clean in BINANCE_TO_HL:
        return BINANCE_TO_HL[clean]

    # Already has xyz: prefix
    if clean.startswith("XYZ:"):
        return f"xyz:{clean[4:]}"

    # If it ends with USDT (Binance pair), strip USDT for main crypto DEX
    if clean.endswith("USDT") and len(clean) > 4:
        return clean[:-4]

    # Default fallback: if not in YAHOO_TO_HL, return clean raw symbol
    return clean


def to_yahoo_symbol(hl_symbol: str) -> str:
    """Convert Hyperliquid symbol to Yahoo Finance ticker where applicable."""
    clean = hl_symbol.strip()
    if clean.startswith("xyz:"):
        base = clean[4:]
        # Reverse lookup in YAHOO_TO_HL
        for yf_tick, hl_tick in YAHOO_TO_HL.items():
            if hl_tick.upper() == clean.upper():
                return yf_tick
        return base
    return clean


def to_binance_symbol(hl_symbol: str) -> str:
    """Convert Hyperliquid crypto symbol to Binance USDT trading pair."""
    clean = hl_symbol.strip()
    if clean.startswith("xyz:"):
        clean = clean[4:]
    if not clean.endswith("USDT"):
        return f"{clean}USDT"
    return clean
