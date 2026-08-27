"""
Hyperliquid Microstructure Module (Dual DEX Snapshot Reader)

Fetches and caches bulk market snapshot data (metaAndAssetCtxs) from Hyperliquid:
1. Main DEX (Crypto) -> dex: ""
2. HIP-3 DEX (Equities & Commodities) -> dex: "xyz"

Validates derivative metrics: Open Interest, Funding Rate, 24h Volume, and Bid-Ask Spread.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

import requests

from backend.ticker_mapper import to_hyperliquid_symbol

logger = logging.getLogger(__name__)

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
CACHE_TTL_SECONDS = 15.0

_snapshot_cache: Dict[str, Any] = {
    "timestamp": 0.0,
    "main_dex": {},
    "xyz_dex": {},
}


_hl_session = None

def _get_hl_session():
    global _hl_session
    if _hl_session is None:
        _hl_session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=3)
        _hl_session.mount("https://", adapter)
        _hl_session.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return _hl_session


def fetch_hl_snapshots(force_refresh: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Fetch bulk metaAndAssetCtxs for both Main DEX (Crypto) and HIP-3 DEX (xyz).

    Caches results for 15 seconds to eliminate rate-limit errors (HTTP 429/1152).
    """
    now = time.time()
    if not force_refresh and (now - _snapshot_cache["timestamp"] < CACHE_TTL_SECONDS) and _snapshot_cache["main_dex"] and _snapshot_cache["xyz_dex"]:
        return _snapshot_cache["main_dex"], _snapshot_cache["xyz_dex"]

    sess = _get_hl_session()

    # 1. Main DEX (Crypto)
    main_ctxs = {}
    try:
        resp = sess.post(HL_INFO_URL, json={"type": "metaAndAssetCtxs"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) == 2:
                meta, ctxs = data[0], data[1]
                universe = meta.get("universe", [])
                for idx, asset in enumerate(universe):
                    name = asset.get("name")
                    if name and idx < len(ctxs):
                        main_ctxs[name] = ctxs[idx]
                        main_ctxs[name]["name"] = name
    except Exception as exc:
        logger.warning("Error fetching Hyperliquid Main DEX snapshot: %s", exc)

    # 2. HIP-3 DEX (Equities / Commodities)
    xyz_ctxs = {}
    try:
        resp = sess.post(HL_INFO_URL, json={"type": "metaAndAssetCtxs", "dex": "xyz"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) == 2:
                meta, ctxs = data[0], data[1]
                universe = meta.get("universe", [])
                for idx, asset in enumerate(universe):
                    name = asset.get("name")
                    if name and idx < len(ctxs):
                        # Hyperliquid HIP-3 names can be 'xyz:XYZ100' or 'xyz:GOLD' or 'XYZ100'
                        clean_hl_symbol = name if name.startswith("xyz:") else f"xyz:{name}"
                        raw_sub = clean_hl_symbol[4:]
                        
                        xyz_ctxs[name] = ctxs[idx]
                        xyz_ctxs[clean_hl_symbol] = ctxs[idx]
                        xyz_ctxs[raw_sub] = ctxs[idx]
                        if raw_sub.startswith("XYZ:"):
                            bare = raw_sub[4:]
                            xyz_ctxs[bare] = ctxs[idx]
                            xyz_ctxs[f"xyz:{bare}"] = ctxs[idx]
                            
                        ctxs[idx]["name"] = clean_hl_symbol
    except Exception as exc:
        logger.warning("Error fetching Hyperliquid HIP-3 DEX snapshot: %s", exc)

    if main_ctxs:
        _snapshot_cache["main_dex"] = main_ctxs
    if xyz_ctxs:
        _snapshot_cache["xyz_dex"] = xyz_ctxs
    if main_ctxs or xyz_ctxs:
        _snapshot_cache["timestamp"] = now

    return _snapshot_cache["main_dex"], _snapshot_cache["xyz_dex"]


def get_asset_microstructure(ticker: str) -> Optional[Dict[str, Any]]:
    """Retrieve derivative microstructure metrics for a given ticker.

    Accepts raw ticker (e.g. NVDA, GC=F, BTCUSDT) or HL symbol (e.g. xyz:NVDA, BTC).
    """
    hl_symbol = to_hyperliquid_symbol(ticker)
    main_dex, xyz_dex = fetch_hl_snapshots()

    ctx = None
    is_xyz = hl_symbol.startswith("xyz:") or ticker.startswith("xyz:") or f"xyz:{ticker}" in xyz_dex or ticker in xyz_dex

    if is_xyz:
        clean_name = hl_symbol[4:] if hl_symbol.startswith("xyz:") else hl_symbol
        ctx = (
            xyz_dex.get(hl_symbol)
            or xyz_dex.get(f"xyz:{clean_name}")
            or xyz_dex.get(clean_name)
            or xyz_dex.get(clean_name.upper())
            or xyz_dex.get(f"xyz:{clean_name.upper()}")
            or xyz_dex.get(ticker)
            or main_dex.get(ticker)
        )
    else:
        ctx = (
            main_dex.get(hl_symbol)
            or main_dex.get(ticker)
            or main_dex.get(hl_symbol.upper())
            or xyz_dex.get(hl_symbol)
            or xyz_dex.get(f"xyz:{hl_symbol}")
            or xyz_dex.get(ticker)
        )

    if not ctx:
        logger.warning("Microstructure data for symbol %s (HL: %s) not found in snapshot.", ticker, hl_symbol)
        return None

    try:
        mark_price = float(ctx.get("markPx", 0.0))
        mid_price = float(ctx.get("midPx", mark_price))
        funding_8h = float(ctx.get("funding", 0.0))
        open_interest = float(ctx.get("openInterest", 0.0))
        volume_24h = float(ctx.get("dayNtlVlm", 0.0))

        # Best bid/ask or impact prices estimation
        impact_pxs = ctx.get("impactPxs")
        if impact_pxs and len(impact_pxs) >= 2:
            bid_price = float(impact_pxs[0])
            ask_price = float(impact_pxs[1])
        else:
            # Fallback estimation around mid price if impactPxs is omitted
            spread_est = 0.0005  # 0.05%
            bid_price = mid_price * (1.0 - spread_est / 2.0)
            ask_price = mid_price * (1.0 + spread_est / 2.0)

        spread_pct = (ask_price - bid_price) / ask_price if ask_price > 0 else 0.0
        requires_limit_order = spread_pct > 0.0015  # > 0.15% forces LIMIT order at POC

        # Volume threshold validation
        min_vol = 800_000.0 if is_xyz else 1_500_000.0
        has_sufficient_liquidity = volume_24h >= min_vol

        is_short_squeeze_catalyst = funding_8h <= -0.0008  # <= -0.08% (Short Squeeze catalyst for LONG)
        is_long_squeeze_catalyst = funding_8h >= 0.0008   # >= +0.08% (Long Squeeze catalyst for SHORT)

        return {
            "hl_symbol": hl_symbol,
            "raw_ticker": ticker,
            "dex": "xyz" if is_xyz else "main",
            "mark_price": mark_price,
            "mid_price": mid_price,
            "bid_price": bid_price,
            "ask_price": ask_price,
            "spread_pct": spread_pct,
            "requires_limit_order": requires_limit_order,
            "funding_8h": funding_8h,
            "funding_daily": funding_8h * 3.0,
            "is_short_squeeze_catalyst": is_short_squeeze_catalyst,
            "is_long_squeeze_catalyst": is_long_squeeze_catalyst,
            "open_interest": open_interest,
            "volume_24h": volume_24h,
            "has_sufficient_liquidity": has_sufficient_liquidity,
            "min_required_vol": min_vol,
        }
    except Exception as exc:
        logger.error("Error parsing microstructure for %s: %s", hl_symbol, exc)
        return None


MEMECOINS = {
    "DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "POPCAT", "MEW", "TRUMP", "NEIRO",
    "MOG", "PNUT", "PENGU", "TURBO", "BRETT", "LADYS", "BOME", "MYRO", "MEME", "1000PEPE",
    "1000BONK", "1000SHIB", "1000FLOKI", "1000CHEEMS", "1000RATS", "1000SATS", "KAS", "WIFUSDT", "PEPEUSDT",
    "KPEPE", "KBONK", "KSHIB", "KFLOKI", "KCHEEMS", "KRATS", "KSATS", "KLADYS", "KBOME", "KMEW", "KMOG",
    "FARTCOIN", "PUMP", "MOODENG", "VIRTUAL", "AI16Z", "CHILLGUY", "DEGEN", "SLERF", "SCHIZO", "GOAT"
}


def get_tradeable_hl_universe(min_crypto_vol: float = 1_500_000, min_xyz_vol: float = 800_000) -> List[str]:
    """Fetch all active perps dynamically from Hyperliquid Main DEX and HIP-3 DEX.

    Filters out:
    - Memecoins / speculative low-utility tokens
    - Perps with 24h volume below thresholds ($1.5M Main DEX / $800k HIP-3)
    """
    main_dex, xyz_dex = fetch_hl_snapshots(force_refresh=True)
    universe: List[str] = []

    # 1. Main DEX (Crypto)
    for name, ctx in main_dex.items():
        clean = name.upper()
        if clean in MEMECOINS:
            continue
        try:
            vol = float(ctx.get("dayNtlVlm", 0.0))
            if vol >= min_crypto_vol:
                universe.append(name)
        except Exception:
            pass

    # 2. HIP-3 DEX (Equities / Commodities / Indices)
    processed_xyz = set()
    for raw_name, ctx in xyz_dex.items():
        symbol = raw_name if raw_name.startswith("xyz:") else f"xyz:{raw_name}"
        if symbol in processed_xyz:
            continue
        processed_xyz.add(symbol)

        clean_base = symbol[4:].upper()
        if clean_base in MEMECOINS and clean_base != "SPX":
            continue

        try:
            vol = float(ctx.get("dayNtlVlm", 0.0))
            if vol >= min_xyz_vol:
                universe.append(symbol)
        except Exception:
            pass

    logger.info("Extracted %d liquid, non-meme tradeable perps from Hyperliquid snapshots.", len(universe))
    return universe

