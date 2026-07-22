"""
Asymmetric Trade Model — calculates precise entry, SL, TP with R:R >= 1:3.

Combines outputs from the shock detector, price structure (SMC), volume
profile, and fundamental filter into a single actionable trade signal
with position sizing at 1% risk per trade.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum acceptable reward-to-risk ratio
MIN_RR_RATIO: float = 3.0

# Default risk per trade as fraction of capital
DEFAULT_RISK_PCT: float = 0.01

# ATR buffer below the capitulation low for the stop loss
SL_ATR_BUFFER_MULT: float = 0.25


def calculate_entry_trigger(
    current_price: float,
    confluence_zones: list[dict],
    fvg_zones: list[dict],
    ob_zones: list[dict],
    poc: float,
    val: float,
    capitulation_low: float = 0.0,
) -> dict:
    """Determine the optimal entry price based on confluence of SMC zones.

    The entry price MUST be above ``capitulation_low`` so that the stop-loss
    (anchored below the capitulation low) is always below entry, yielding a
    positive risk value.

    Priority order:
    1. Confluence zone (FVG + OB overlap) closest to current price & above cap low
    2. Bullish FVG closest to current price & above cap low
    3. Bullish Order Block closest to current price & above cap low
    4. POC or VAL as fallback (only if above cap low)
    5. Current price as last resort

    Returns
    -------
    dict
        ``{'entry_price': float, 'trigger_type': str, 'zone': tuple}``
    """
    # Filter for bullish zones below current price (potential support)
    # BUT above capitulation_low so that entry > SL
    candidates = []

    # Priority 1: Confluence zones
    for z in (confluence_zones or []):
        zone_high = z["zone_high"]
        if z["zone_low"] <= current_price and zone_high > capitulation_low:
            candidates.append({
                "entry_price": zone_high,
                "trigger_type": "CONFLUENCE",
                "zone": (z["zone_low"], zone_high),
                "strength": z.get("strength", 2),
                "distance": abs(current_price - zone_high),
            })

    # Priority 2: Bullish FVGs
    for fvg in (fvg_zones or []):
        if fvg.get("type") == "bullish" and fvg["low"] <= current_price and fvg["high"] > capitulation_low:
            candidates.append({
                "entry_price": fvg["high"],
                "trigger_type": "FVG",
                "zone": (fvg["low"], fvg["high"]),
                "strength": 1,
                "distance": abs(current_price - fvg["high"]),
            })

    # Priority 3: Bullish Order Blocks
    for ob in (ob_zones or []):
        if ob.get("type") == "bullish" and ob["low"] <= current_price and ob["high"] > capitulation_low:
            candidates.append({
                "entry_price": ob["high"],
                "trigger_type": "ORDER_BLOCK",
                "zone": (ob["low"], ob["high"]),
                "strength": 1,
                "distance": abs(current_price - ob["high"]),
            })

    if candidates:
        # Sort by strength (descending) then by proximity to current price (ascending)
        candidates.sort(key=lambda c: (-c["strength"], c["distance"]))
        best = candidates[0]
        return {
            "entry_price": best["entry_price"],
            "trigger_type": best["trigger_type"],
            "zone": best["zone"],
        }

    # Fallback: use VAL or POC (only if above capitulation_low)
    if val > capitulation_low and val <= current_price:
        return {
            "entry_price": val,
            "trigger_type": "VAL_FALLBACK",
            "zone": (val, val),
        }
    if poc > capitulation_low:
        return {
            "entry_price": poc,
            "trigger_type": "POC_FALLBACK",
            "zone": (poc, poc),
        }

    # Last resort: current price (always above cap low after a bounce)
    return {
        "entry_price": current_price,
        "trigger_type": "MARKET",
        "zone": (current_price, current_price),
    }


def calculate_asymmetric_levels(
    entry_price: float,
    capitulation_low: float,
    atr_value: float,
    poc: float,
    vah: float,
    fvg_targets: list[dict],
    sl_buffer_mult: float = SL_ATR_BUFFER_MULT,
    min_rr: float = MIN_RR_RATIO,
) -> Optional[dict]:
    """Calculate SL, TP, and R:R for an asymmetric trade.

    Stop Loss: Below the capitulation low + ATR buffer.
    Take Profit: The highest valid target that achieves R:R >= min_rr,
    chosen from POC, VAH, or bearish FVG zones above entry.

    Returns
    -------
    dict or None
        ``{'stop_loss', 'take_profit', 'rr_ratio', 'risk', 'reward', 'tp_target_type'}``
        or None if no target achieves the minimum R:R.
    """
    # Stop Loss: below capitulation low with ATR buffer
    buffer = atr_value * sl_buffer_mult
    stop_loss = capitulation_low - buffer
    risk = entry_price - stop_loss

    if risk <= 0:
        logger.warning(
            "Invalid risk calculation: entry=%.4f, SL=%.4f, risk=%.4f",
            entry_price, stop_loss, risk,
        )
        return None

    # Collect potential take-profit targets (above entry)
    tp_candidates = []

    if poc > entry_price:
        tp_candidates.append(("POC", poc))
    if vah > entry_price:
        tp_candidates.append(("VAH", vah))

    # Add bearish FVGs above entry as reversal targets
    for fvg in (fvg_targets or []):
        if fvg.get("type") == "bearish" and fvg.get("low", 0) > entry_price:
            tp_candidates.append(("FVG_TARGET", fvg["low"]))

    # NOTE: No synthetic MIN_RR fallback — TP must come from real technical
    # levels (POC, VAH, FVG).  If no real target achieves min_rr, the signal
    # is rejected.  This prevents the filter from accepting every single ticker.

    # Sort by distance (pick the closest that meets min_rr)
    tp_candidates.sort(key=lambda t: t[1])

    for tp_type, tp_price in tp_candidates:
        reward = tp_price - entry_price
        rr = reward / risk if risk > 0 else 0
        if rr >= min_rr:
            logger.info(
                "Asymmetric levels: entry=%.4f, SL=%.4f, TP=%.4f, R:R=%.1f (%s)",
                entry_price, stop_loss, tp_price, rr, tp_type,
            )
            return {
                "stop_loss": round(stop_loss, 6),
                "take_profit": round(tp_price, 6),
                "rr_ratio": round(rr, 2),
                "risk": round(risk, 6),
                "reward": round(reward, 6),
                "tp_target_type": tp_type,
            }

    logger.info(
        "No TP target achieves R:R >= %.1f for entry=%.4f, SL=%.4f",
        min_rr, entry_price, stop_loss,
    )
    return None


def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
) -> float:
    """Calculate position size based on fixed fractional risk.

    Parameters
    ----------
    capital : float
        Total account capital.
    risk_pct : float
        Maximum risk per trade as a decimal (e.g. 0.01 = 1%).
    entry_price, stop_loss : float
        Trade levels.

    Returns
    -------
    float
        Quantity to buy (number of shares/coins).
    """
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit <= 0:
        return 0.0

    risk_amount = capital * risk_pct
    qty = risk_amount / risk_per_unit

    logger.info(
        "Position sizing: capital=%.2f, risk_pct=%.2f%%, risk_amount=%.2f, "
        "risk_per_unit=%.4f, qty=%.4f",
        capital, risk_pct * 100, risk_amount, risk_per_unit, qty,
    )
    return round(qty, 6)


def calculate_confidence_score(
    shock_result: dict,
    structure_result: dict,
    profile_result: dict,
    fundamental_result: dict,
) -> float:
    """Calculate a 0.0–1.0 confidence score based on signal confluence.

    Scoring:
    - Idiosyncratic shock (not systemic): +0.15
    - High capitulation volume (>= 2x): +0.10
    - Confluence zone present: +0.20
    - FVG support present: +0.10
    - Order Block support present: +0.10
    - Price below VAL (oversold): +0.10
    - Fundamental solvency OK: +0.15
    - Bullish MSB present: +0.10
    """
    score = 0.0

    # Shock quality
    if shock_result.get("is_idiosyncratic", False):
        score += 0.15
    if shock_result.get("capitulation_volume_ratio", 0) >= 2.0:
        score += 0.10

    # Price structure
    if structure_result.get("confluence_zones"):
        score += 0.20
    if any(f.get("type") == "bullish" for f in structure_result.get("fvg_1d", [])):
        score += 0.10
    if any(o.get("type") == "bullish" for o in structure_result.get("ob_1d", [])):
        score += 0.10
    if any(m.get("type") == "bullish" for m in structure_result.get("msb_1d", [])):
        score += 0.10

    # Volume profile
    if profile_result.get("price_vs_va") == "below_val":
        score += 0.10

    # Fundamentals
    if fundamental_result.get("passed", False):
        score += 0.15

    return round(min(score, 1.0), 2)


def build_analysis_summary(
    ticker: str,
    shock: dict,
    entry_trigger: dict,
    levels: dict,
    structure: dict,
    profile: dict,
    fundamental: dict,
    confidence: float,
) -> str:
    """Build a human-readable analysis summary for the signal."""
    parts = []

    # Shock description
    parts.append(
        f"Caída de {abs(shock.get('drop_pct', 0)) * 100:.1f}% "
        f"({'idiosincrática' if shock.get('is_idiosyncratic') else 'sistémica'})"
    )

    # Entry trigger
    parts.append(f"Entrada: {entry_trigger.get('trigger_type', 'N/A')}")

    # Structure
    n_conf = len(structure.get("confluence_zones", []))
    if n_conf > 0:
        parts.append(f"{n_conf} zona(s) de confluencia SMC")

    # Volume profile
    price_vs_va = profile.get("price_vs_va", "unknown")
    if price_vs_va == "below_val":
        parts.append("Precio bajo VAL (sobreventa)")
    elif price_vs_va == "in_value_area":
        parts.append("Precio dentro del Value Area")

    # R:R
    rr = levels.get("rr_ratio", 0)
    parts.append(f"R:R = 1:{rr:.1f} ({levels.get('tp_target_type', 'N/A')})")

    # Confidence
    parts.append(f"Confianza: {confidence * 100:.0f}%")

    return " | ".join(parts)
