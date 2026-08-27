"""
Paper Trading Journal Module for Hyperliquid Perpetuals Screener.

Manages simulated paper trades approved by the screener:
- Persists trades in perp_journal.json
- Evaluates open positions against live mark prices
- Auto-closes on TP, SL, or Time-Decay (120h estancamiento)
- Computes PnL USD, ROE %, and Win Rate statistics
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

JOURNAL_FILE = Path(__file__).resolve().parent / "perp_journal.json"


def load_journal() -> List[Dict[str, Any]]:
    """Load the paper trading journal from perp_journal.json."""
    if not JOURNAL_FILE.exists():
        return []
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Error loading perp_journal.json: %s", exc)
        return []


def save_journal(journal_data: List[Dict[str, Any]]) -> bool:
    """Save the paper trading journal to perp_journal.json."""
    try:
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(journal_data, f, indent=2)
        return True
    except Exception as exc:
        logger.error("Error saving perp_journal.json: %s", exc)
        return False


def add_paper_trade(setup: Dict[str, Any], initial_margin_usd: float = 500.0) -> Optional[Dict[str, Any]]:
    """Add a newly approved setup to the paper trading journal as an OPEN position.

    Deduplicates active open trades for the same ticker and direction.
    """
    if setup.get("verdict") != "APROBADO":
        return None

    journal = load_journal()
    ticker = setup.get("ticker", "")
    direction = setup.get("direction", "LONG")

    # Check if open trade already exists for ticker & direction
    for trade in journal:
        if trade.get("ticker") == ticker and trade.get("direction") == direction and trade.get("status") == "OPEN":
            logger.info("Open paper trade already exists for %s (%s) — skipping duplicate.", ticker, direction)
            return trade

    current_price = float(setup.get("current_price", 0.0))
    poc = float(setup.get("poc", current_price))
    requires_limit = "LIMIT" in setup.get("order_execution_mode", "")
    entry_price = poc if (requires_limit and poc > 0) else current_price

    leverage = float(setup.get("leverage", 5.0))

    sl_price_orig = float(setup.get("sl_price", 0.0))
    tp_price_orig = float(setup.get("tp_price", 0.0))
    
    # Recalculate SL, TP and Liq if entry price shifted (e.g. LIMIT order execution at POC)
    if current_price > 0 and abs(entry_price - current_price) > 1e-6:
        orig_sl_dist = abs(current_price - sl_price_orig)
        orig_tp_dist = abs(tp_price_orig - current_price)
        if direction == "LONG":
            sl_price = entry_price - orig_sl_dist
            tp_price = entry_price + orig_tp_dist
        else:
            sl_price = entry_price + orig_sl_dist
            tp_price = entry_price - orig_tp_dist
    else:
        sl_price = sl_price_orig
        tp_price = tp_price_orig

    # Isolated Margin Liquidation (MMR = 5%)
    mmr = 0.05
    if direction == "LONG":
        liq_price = entry_price * (1.0 - (1.0 / leverage) * (1.0 - mmr))
    else:
        liq_price = entry_price * (1.0 + (1.0 / leverage) * (1.0 - mmr))

    sl_dist = abs(entry_price - sl_price)
    tp_dist = abs(tp_price - entry_price)
    liq_dist = abs(entry_price - liq_price)
    rr_ratio = (tp_dist / sl_dist) if sl_dist > 0 else 0.0

    # CRO VETO Checks:
    # 1. Structural directional validity (LONG: SL < Entry < TP | SHORT: TP < Entry < SL)
    if direction == "LONG" and not (sl_price < entry_price < tp_price):
        logger.error("VETO CRO: Invalid LONG level placement for %s: entry=%.4f, SL=%.4f, TP=%.4f", ticker, entry_price, sl_price, tp_price)
        return None
    elif direction == "SHORT" and not (tp_price < entry_price < sl_price):
        logger.error("VETO CRO: Invalid SHORT level placement for %s: entry=%.4f, SL=%.4f, TP=%.4f", ticker, entry_price, sl_price, tp_price)
        return None

    # 2. Minimum R:R ratio threshold (>= 2.50)
    if rr_ratio < 2.499:
        logger.error("VETO CRO: R:R ratio below 1:2.50 threshold for %s (%.2f)", ticker, rr_ratio)
        return None

    # 3. Liquidation distance must be at least 2x Stop Loss distance
    if liq_dist < (2.0 * sl_dist):
        logger.error("VETO CRO: Liquidation distance (%.4f) < 2x SL distance (%.4f) for %s", liq_dist, 2.0 * sl_dist, ticker)
        return None

    position_value = initial_margin_usd * leverage
    position_qty = position_value / entry_price if entry_price > 0 else 0.0
    now_iso = datetime.now(timezone.utc).isoformat()

    new_trade = {
        "id": f"perp_{int(time.time()*1000)}",
        "timestamp": now_iso,
        "ticker": ticker,
        "hl_symbol": setup.get("hl_symbol", ticker),
        "direction": direction,
        "entry_price": round(entry_price, 6),
        "current_price": round(entry_price, 6),
        "sl_price": round(sl_price, 6),
        "tp_price": round(tp_price, 6),
        "liq_price": round(liq_price, 6),
        "leverage": leverage,
        "margin_usd": initial_margin_usd,
        "position_val_usd": round(position_value, 2),
        "qty": position_qty,
        "rr_ratio": round(rr_ratio, 2),
        "status": "OPEN",
        "pnl_usd": 0.0,
        "roe_pct": 0.0,
        "open_time_ms": int(time.time() * 1000),
        "close_time": None,
        "close_reason": None,
        "order_execution_mode": setup.get("order_execution_mode", "MARKET"),
    }

    journal.append(new_trade)
    save_journal(journal)
    logger.info("Added new paper trade: %s (%s %dx) @ $%.2f", ticker, direction, leverage, entry_price)
    return new_trade


def update_paper_positions(live_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Evaluate all OPEN paper positions against live mark prices.

    Closes trades on TP, SL, Liquidation, or 120h Time-Decay.
    Returns summary of open, closed, and PnL metrics.
    """
    journal = load_journal()
    if not journal:
        return {"open_count": 0, "closed_count": 0, "total_pnl_usd": 0.0, "win_rate_pct": 0.0, "trades": []}

    now_ms = int(time.time() * 1000)
    time_decay_limit_ms = 120 * 3600 * 1000  # 120 hours

    open_trades = []
    closed_trades = []
    total_pnl_usd = 0.0
    wins = 0

    for trade in journal:
        if trade["status"] == "OPEN":
            ticker = trade["ticker"]
            mark = live_prices.get(ticker, 0.0) if live_prices else 0.0
            if mark <= 0:
                mark = trade["entry_price"]

            trade["current_price"] = mark
            entry = trade["entry_price"]
            direction = trade["direction"]
            margin = trade["margin_usd"]
            qty = trade["qty"]

            # Price delta and PnL calculation
            price_delta = (mark - entry) if direction == "LONG" else (entry - mark)
            pnl_usd = price_delta * qty
            roe_pct = (pnl_usd / margin) * 100.0 if margin > 0 else 0.0

            trade["pnl_usd"] = round(pnl_usd, 2)
            trade["roe_pct"] = round(roe_pct, 2)

            # Check exit conditions
            sl = trade["sl_price"]
            tp = trade["tp_price"]
            liq = trade["liq_price"]
            elapsed_ms = now_ms - trade.get("open_time_ms", now_ms)

            hit_sl = (mark <= sl) if direction == "LONG" else (mark >= sl)
            hit_tp = (mark >= tp) if direction == "LONG" else (mark <= tp)
            hit_liq = (mark <= liq) if direction == "LONG" else (mark >= liq)

            if hit_liq:
                trade["status"] = "LIQUIDATED"
                trade["close_time"] = datetime.now(timezone.utc).isoformat()
                trade["close_reason"] = "Liquidación por mecha"
                trade["pnl_usd"] = -margin
                trade["roe_pct"] = -100.0
            elif hit_sl:
                trade["status"] = "CLOSED_SL"
                trade["close_time"] = datetime.now(timezone.utc).isoformat()
                trade["close_reason"] = "Stop Loss alcanzado"
            elif hit_tp:
                trade["status"] = "CLOSED_TP"
                trade["close_time"] = datetime.now(timezone.utc).isoformat()
                trade["close_reason"] = "Take Profit alcanzado"
            elif elapsed_ms >= time_decay_limit_ms:
                trade["status"] = "CLOSED_TIME_DECAY"
                trade["close_time"] = datetime.now(timezone.utc).isoformat()
                trade["close_reason"] = "Cierre por estancamiento (120h)"

        if trade["status"] != "OPEN":
            closed_trades.append(trade)
            total_pnl_usd += trade.get("pnl_usd", 0.0)
            if trade.get("pnl_usd", 0.0) > 0:
                wins += 1
        else:
            open_trades.append(trade)

    save_journal(journal)
    win_rate = (wins / len(closed_trades) * 100.0) if closed_trades else 0.0

    return {
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "win_rate_pct": round(win_rate, 1),
        "open_positions": open_trades,
        "closed_history": closed_trades,
        "all_trades": journal,
    }
