"""
Order Flow Models, Composite Scoring & Institutional Market Story Generator.

Produces clean, bounded 0-100 scores and synthesized microstructure narrative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass
class OrderFlowReport:
    """Complete institutional Order Flow, CVD and Auction context report."""
    symbol: str
    market: str
    regime: str
    activity_type: str
    location: List[str]
    signals: List[str]
    metrics: Dict[str, Any]
    scores: Dict[str, float]
    market_story: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


def compute_composite_scores(
    of: Dict[str, Any],
    auc: Dict[str, Any],
) -> Dict[str, float]:
    """
    Computes bounded 0-100 setup scores:
    - seller_absorption
    - buyer_absorption
    - trapped_shorts
    - trapped_longs
    - initiative_buying
    - initiative_selling
    - exhaustion
    """
    loc = auc.get("location_tags", [])
    near_vah = "NEAR_INTRADAY_VAH" in loc or "ABOVE_INTRADAY_VAH" in loc
    near_val = "NEAR_INTRADAY_VAL" in loc or "BELOW_INTRADAY_VAL" in loc

    cvd_z = of.get("cvd_change_z", 0.0)
    vol_z = of.get("volume_z", 0.0)
    oi_z = of.get("oi_change_z", 0.0)
    eff = of.get("aggression_efficiency", 1.0)
    buy_eff = of.get("buy_efficiency", 1.0)
    sell_eff = of.get("sell_efficiency", 1.0)
    cvd_acc = of.get("cvd_acceleration", 0.0)

    # 1. Seller Absorption Score
    w_cvd_pos = max(0.0, min(1.0, cvd_z / 2.5))
    w_low_buy_eff = max(0.0, min(1.0, 1.0 - min(1.0, buy_eff)))
    w_vol_pos = max(0.0, min(1.0, vol_z / 2.5))
    w_loc_vah = 1.0 if near_vah else 0.2
    w_oi_exp = max(0.0, min(1.0, oi_z / 2.0))

    seller_abs_raw = (0.30 * w_cvd_pos + 0.25 * w_low_buy_eff + 0.15 * w_vol_pos + 0.20 * w_loc_vah + 0.10 * w_oi_exp) * 100.0

    # 2. Buyer Absorption Score
    w_cvd_neg = max(0.0, min(1.0, -cvd_z / 2.5))
    w_low_sell_eff = max(0.0, min(1.0, 1.0 - min(1.0, sell_eff)))
    w_loc_val = 1.0 if near_val else 0.2

    buyer_abs_raw = (0.30 * w_cvd_neg + 0.25 * w_low_sell_eff + 0.15 * w_vol_pos + 0.20 * w_loc_val + 0.10 * w_oi_exp) * 100.0

    # 3. Trapped Shorts Score
    is_failed_down = "FAILED_AUCTION_DOWN" in auc.get("auction_signals", []) or auc.get("is_rejection_below", False)
    w_failed_down = 1.0 if is_failed_down else (0.4 if near_val else 0.1)
    trapped_shorts_raw = (0.35 * w_cvd_neg + 0.25 * w_oi_exp + 0.40 * w_failed_down) * 100.0

    # 4. Trapped Longs Score
    is_failed_up = "FAILED_AUCTION_UP" in auc.get("auction_signals", []) or auc.get("is_rejection_above", False)
    w_failed_up = 1.0 if is_failed_up else (0.4 if near_vah else 0.1)
    trapped_longs_raw = (0.35 * w_cvd_pos + 0.25 * w_oi_exp + 0.40 * w_failed_up) * 100.0

    # 5. Initiative Buying Score
    is_acc_up = 1.0 if auc.get("is_acceptance_above", False) else 0.0
    w_mig_up = 1.0 if auc.get("value_migration") == "VALUE_MIGRATION_UP" else 0.2
    w_high_buy_eff = min(1.0, max(0.0, buy_eff / 1.5))
    init_buy_raw = (0.35 * is_acc_up + 0.25 * w_mig_up + 0.20 * w_cvd_pos + 0.20 * w_high_buy_eff) * 100.0

    # 6. Initiative Selling Score
    is_acc_down = 1.0 if auc.get("is_acceptance_below", False) else 0.0
    w_mig_down = 1.0 if auc.get("value_migration") == "VALUE_MIGRATION_DOWN" else 0.2
    w_high_sell_eff = min(1.0, max(0.0, sell_eff / 1.5))
    init_sell_raw = (0.35 * is_acc_down + 0.25 * w_mig_down + 0.20 * w_cvd_neg + 0.20 * w_high_sell_eff) * 100.0

    # 7. Exhaustion Score
    w_decel = max(0.0, min(1.0, abs(cvd_acc) / 500.0))
    w_low_vol = max(0.0, min(1.0, -vol_z / 2.0))
    exhaustion_raw = (0.60 * w_decel + 0.40 * w_low_vol) * 100.0

    return {
        "seller_absorption": round(float(np.clip(seller_abs_raw, 0.0, 100.0)), 1),
        "buyer_absorption": round(float(np.clip(buyer_abs_raw, 0.0, 100.0)), 1),
        "trapped_shorts": round(float(np.clip(trapped_shorts_raw, 0.0, 100.0)), 1),
        "trapped_longs": round(float(np.clip(trapped_longs_raw, 0.0, 100.0)), 1),
        "initiative_buying": round(float(np.clip(init_buy_raw, 0.0, 100.0)), 1),
        "initiative_selling": round(float(np.clip(init_sell_raw, 0.0, 100.0)), 1),
        "exhaustion": round(float(np.clip(exhaustion_raw, 0.0, 100.0)), 1),
    }


def generate_market_story(
    symbol: str,
    of: Dict[str, Any],
    auc: Dict[str, Any],
    scores: Dict[str, float],
) -> str:
    """Synthesize institutional microstructural context narrative."""
    parts = []
    regime = auc.get("regime", "DEVELOPING")
    locations = ", ".join(auc.get("location_tags", []))
    parts.append(f"Subasta en régimen [{regime}] con precio ubicado en [{locations}].")

    # Order flow dynamics
    cvd_z = of.get("cvd_change_z", 0.0)
    eff = of.get("aggression_efficiency", 1.0)
    oi_class = of.get("oi_classification", "NEUTRAL")

    if scores.get("buyer_absorption", 0) >= 65.0:
        parts.append(
            f"Venta agresiva extrema (CVD z={cvd_z:.2f}) sin desplazamiento a la baja proporcional "
            f"(Eficiencia={eff:.2f}); compradores pasivos absorben la oferta en soporte/VAL."
        )
    elif scores.get("seller_absorption", 0) >= 65.0:
        parts.append(
            f"Compra agresiva extrema (CVD z={cvd_z:.2f}) bloqueada por absorción pasiva de vendedores "
            f"cerca de VAH (Eficiencia={eff:.2f})."
        )

    if scores.get("trapped_shorts", 0) >= 65.0:
        parts.append("Estructura de Vendedores Atrapados (Trapped Shorts) con rechazo bajo VAL; riesgo de Short Squeeze.")
    elif scores.get("trapped_longs", 0) >= 65.0:
        parts.append("Estructura de Compradores Atrapados (Trapped Longs) con rechazo sobre VAH; riesgo de Long Squeeze.")

    if scores.get("initiative_buying", 0) >= 70.0:
        parts.append("Flujo de Iniciativa Compradora confirmado con aceptación y migración ascendente de valor.")
    elif scores.get("initiative_selling", 0) >= 70.0:
        parts.append("Flujo de Iniciativa Vendedora confirmado con aceptación y migración descendente de valor.")

    if oi_class != "NEUTRAL":
        parts.append(f"Dinámica de Exposición Abierta: {oi_class} (Confianza: {of.get('oi_confidence', 50):.0f}%).")

    return " ".join(parts)
