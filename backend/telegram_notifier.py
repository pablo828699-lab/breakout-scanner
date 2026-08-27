"""
Telegram notification service.

Sends formatted breakout alerts via the Telegram Bot API.
In dry-run mode, alerts are logged to the console instead.
"""

from __future__ import annotations

import logging
from datetime import timezone

import requests

from backend.models import AsymmetricSignal, BreakoutSignal, MomentumSignal, RadarSignal

logger = logging.getLogger(__name__)

_MARKET_LABELS = {
    "US_EQUITIES": "US Equities (S&P 500)",
    "CRYPTO": "Crypto (Binance Spot)",
}

_DIRECTION_EMOJI = {"LONG": "📈", "SHORT": "📉"}

# Radar helpers
_RADAR_DIR = {"UP": ("🟢", "ALCISTA"), "DOWN": ("🔴", "BAJISTA")}
_TRIGGER_LABELS = {"IMPULSE": "Impulso"}
_ANALYZE_MARKET = {"US_EQUITIES": "stock", "CRYPTO": "crypto"}


def _trigger_label(trigger: str) -> str:
    if trigger.startswith("DONCHIAN_"):
        return f"Donchian({trigger.split('_')[1]})"
    return _TRIGGER_LABELS.get(trigger, trigger.title())


class TelegramNotifier:
    """Send formatted trade alerts via Telegram or log them in dry-run mode."""

    def __init__(
        self,
        bot_token: str = "",
        chat_id: str = "",
        dry_run: bool = True,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._dry_run = dry_run

        if not dry_run and (not bot_token or not chat_id):
            logger.warning(
                "Telegram credentials missing — forcing DRY-RUN mode."
            )
            self._dry_run = True

    # ------------------------------------------------------------------

    def _format_message(self, signal: BreakoutSignal) -> str:
        """Build the alert text with emojis and structured layout."""
        market_label = _MARKET_LABELS.get(signal.market, signal.market)
        dir_emoji = _DIRECTION_EMOJI.get(signal.direction, "➡️")
        ts = signal.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Choose price format based on market (crypto can have many decimals)
        fmt = ".2f" if signal.market == "US_EQUITIES" else ".4f"

        return (
            f"📊 BREAKOUT ALERT\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ Ticker: {signal.ticker}\n"
            f"🏦 Market: {market_label}\n"
            f"{dir_emoji} Direction: {signal.direction}\n"
            f"💰 Broken Level: ${signal.broken_level:{fmt}}\n"
            f"📍 Entry: ${signal.entry_price:{fmt}}\n"
            f"🛑 Stop-Loss: ${signal.stop_loss:{fmt}}\n"
            f"🎯 Take-Profit: ${signal.take_profit:{fmt}}\n"
            f"📊 Volume Ratio: {signal.volume_ratio:.1f}x\n"
            f"📐 ATR: ${signal.atr_value:{fmt}}\n"
            f"⏰ {ts}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

    def _format_radar(self, signal: RadarSignal) -> str:
        """Build a trend-radar alert with clear, self-explanatory indicators."""
        market_label = _MARKET_LABELS.get(signal.market, signal.market)
        emoji, dir_label = _RADAR_DIR.get(signal.direction, ("➡️", signal.direction))
        ts = signal.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        fmt = ".2f" if signal.market == "US_EQUITIES" else ".4f"
        
        # Format trigger explanations
        triggers_list = []
        for t in signal.triggers:
            label = _trigger_label(t)
            if t.startswith("DONCHIAN_"):
                triggers_list.append(f"{label} (Ruptura Max/Min {t.split('_')[1]}d)")
            elif t == "IMPULSE":
                triggers_list.append(f"{label} (Vela rango amplio)")
            else:
                triggers_list.append(label)
        triggers = " + ".join(triggers_list)

        # ADX trend strength explanation
        adx_strength = "Rango/Lateral" if signal.adx < 20 else ("Tendencia Fuerte" if signal.adx > 25 else "Tendencia Naciendo")
        stack_desc = "Fase Madura ✓" if signal.ema_stack else "Fase Temprana"
        
        # Volume relative explanation
        vol_desc = "Normal" if signal.volume_ratio < 1.2 else ("Alto" if signal.volume_ratio < 2.0 else "Institucional/Pánico")

        # Calculate trade levels (same logic as frontend App.jsx)
        is_crypto = signal.market == "CRYPTO"
        sl_pct = 0.05 if is_crypto else 0.02  # 5% crypto, 2% stocks
        tp_pct = sl_pct * 2.0  # 1:2 R:R

        entry = signal.price
        if signal.direction == "UP":
            sl = entry * (1 - sl_pct)
            tp = entry * (1 + tp_pct)
        else:
            sl = entry * (1 + sl_pct)
            tp = entry * (1 - tp_pct)

        return (
            f"📡 RADAR DE TENDENCIA\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ {signal.ticker} — {market_label}\n"
            f"{emoji} Tendencia: {dir_label}\n"
            f"⚡ Disparador: {triggers}\n"
            f"💪 ADX: {signal.adx:.1f} ({adx_strength})  |  {stack_desc}\n"
            f"📊 Volumen: {signal.volume_ratio:.1f}x ({vol_desc})  |  ROC: {signal.roc_pct:+.1f}%\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 Entrada: ${entry:{fmt}}\n"
            f"🛑 Stop-Loss: ${sl:{fmt}} ({sl_pct*100:.0f}%)\n"
            f"🎯 Take-Profit: ${tp:{fmt}} ({tp_pct*100:.0f}%)\n"
            f"⚖️ R:R = 1:2\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {ts}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

    # ------------------------------------------------------------------

    def send_alert(self, signal) -> bool:
        """Send (or log) an alert (breakout or radar).

        Returns ``True`` on success, ``False`` on failure.
        """
        if isinstance(signal, AsymmetricSignal):
            text = self._format_asymmetric(signal)
        elif isinstance(signal, RadarSignal):
            text = self._format_radar(signal)
        else:
            text = self._format_message(signal)

        if self._dry_run:
            logger.info("[DRY-RUN] Telegram alert:\n%s", text)
            return True

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram alert sent for %s.", signal.ticker)
                return True
            logger.error(
                "Telegram API error %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    def _format_asymmetric(self, signal: AsymmetricSignal) -> str:
        """Build a capitulation alert with full analysis details."""
        market_label = _MARKET_LABELS.get(signal.market, signal.market)
        ts = signal.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        fmt = ".2f" if signal.market == "US_EQUITIES" else ".4f"

        verdict_emoji = "🟢" if signal.verdict == "APTO_COMPRA_ASIMETRICA" else "🔴"
        verdict_label = "APTO COMPRA ASIMÉTRICA" if signal.verdict == "APTO_COMPRA_ASIMETRICA" else "EVITAR"
        shock_type = "Idiosincrática" if signal.is_idiosyncratic else "Sistémica"
        fund_label = "✅ Solvente" if signal.fundamental_ok else "⚠️ Riesgo"

        lines = [
            f"🔬 ANÁLISIS DE CAPITULACIÓN",
            f"━━━━━━━━━━━━━━━━━━",
            f"🏷️ {signal.ticker} — {market_label}",
            f"{verdict_emoji} Veredicto: {verdict_label}",
            f"📉 Caída: {signal.drop_pct * 100:.1f}% ({shock_type})",
            f"📊 Confianza: {signal.confidence_score * 100:.0f}%",
            f"━━━━━━━━━━━━━━━━━━",
        ]

        if signal.verdict == "APTO_COMPRA_ASIMETRICA":
            lines.extend([
                f"📍 Entrada: ${signal.entry_price:{fmt}}",
                f"🛑 Stop Loss: ${signal.stop_loss:{fmt}}",
                f"🎯 Take Profit: ${signal.take_profit:{fmt}}",
                f"⚖️ R:R = 1:{signal.rr_ratio:.1f}",
                f"📐 Tamaño: {signal.position_size_qty:.4f} unidades",
                f"━━━━━━━━━━━━━━━━━━",
                f"📊 POC: ${signal.poc:{fmt}}",
                f"📊 VAH: ${signal.vah:{fmt}} | VAL: ${signal.val:{fmt}}",
            ])

            if signal.fvg_zone and signal.fvg_zone != (0.0, 0.0):
                lines.append(f"🟦 FVG: ${signal.fvg_zone[0]:{fmt}} — ${signal.fvg_zone[1]:{fmt}}")
            if signal.ob_zone and signal.ob_zone != (0.0, 0.0):
                lines.append(f"🟧 OB: ${signal.ob_zone[0]:{fmt}} — ${signal.ob_zone[1]:{fmt}}")
            if signal.msb_type and signal.msb_type != "n/a":
                lines.append(f"🔄 MSB: {signal.msb_type}")

        lines.extend([
            f"💼 Fundamental: {fund_label}",
            f"⏰ {ts}",
            f"━━━━━━━━━━━━━━━━━━",
            f"📝 {signal.analysis_summary}",
        ])

        return "\n".join(lines)

    def send_perp_alert(self, setup: dict) -> bool:
        """Format and send a Telegram alert for an APPROVED Hyperliquid perps setup."""
        if setup.get("verdict") != "APROBADO":
            return False

        ticker = setup.get("ticker", "")
        hl_symbol = setup.get("hl_symbol", ticker)
        direction = setup.get("direction", "LONG")
        dir_emoji = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
        leverage = setup.get("leverage", 5.0)

        entry = setup.get("current_price", 0.0)
        poc = setup.get("poc", entry)
        mode = setup.get("order_execution_mode", "MARKET")
        sl = setup.get("sl_price", 0.0)
        tp = setup.get("tp_price", 0.0)
        liq = setup.get("estimated_liq_price", 0.0)
        rr = setup.get("rr_ratio", 2.5)

        micro = setup.get("microstructure") or {}
        funding = micro.get("funding_8h", 0.0) * 100.0
        vol_24h = micro.get("volume_24h", 0.0)

        msg = (
            f"⚡ *HYPERLIQUID PERP SETUP APROBADO*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *{ticker}* ({hl_symbol}) | {dir_emoji} *{leverage:.0f}x Isolated*\n"
            f"📍 *Entrada:* ${entry:,.2f} | *POC:* ${poc:,.2f}\n"
            f"⚙️ *Ejecución:* {mode}\n"
            f"🛑 *Stop Loss:* ${sl:,.2f}\n"
            f"🎯 *Take Profit:* ${tp:,.2f} (R:R 1:{rr:.2f})\n"
            f"🛡️ *Liquidación:* ${liq:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Funding 8h:* {funding:+.4f}%\n"
            f"💧 *Volumen 24h:* ${vol_24h:,.0f} USD\n"
            f"✅ *Veredicto:* 100% Validaciones Aprobadas"
        )

        if self._dry_run:
            logger.info("[DRY-RUN Telegram Perp Alert]:\n%s", msg)
            return True

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": msg,
            "parse_mode": "Markdown",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram perp alert sent for %s", ticker)
                return True
            logger.error("Failed sending Telegram perp alert: HTTP %d %s", resp.status_code, resp.text)
            return False
        except Exception as exc:
            logger.error("Error sending Telegram perp alert: %s", exc)
            return False

    def _format_momentum(self, signal: MomentumSignal) -> str:
        """Build an explosive momentum / squeeze alert."""
        market_label = _MARKET_LABELS.get(signal.market, signal.market)
        ts = signal.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        fmt = ".2f" if signal.market == "US_EQUITIES" else ".4f"

        dir_emoji = "🟢 LONG ▲" if signal.direction == "LONG" else "🔴 SHORT ▼"
        
        lines = [
            f"🚀 ALERTA DE MOMENTUM INSTITUCIONAL",
            f"━━━━━━━━━━━━━━━━━━",
            f"🏷️ {signal.ticker} — {market_label} ({signal.asset_class})",
            f"⚡ Dirección: {dir_emoji}",
            f"💥 Disparador: {signal.trigger} ({signal.squeeze_status})",
            f"📈 ROC(10): {signal.roc_10:+.1f}% | RSI(14): {signal.rsi:.1f}",
            f"💧 Volumen Relativo: {signal.rvol:.2f}x (SMA 20)",
            f"📊 Confianza Cuantitativa: {signal.confidence_score * 100:.0f}%",
            f"━━━━━━━━━━━━━━━━━━",
            f"📍 Entrada: ${signal.entry_price:{fmt}}",
            f"🛑 Stop Loss: ${signal.stop_loss:{fmt}}",
            f"🎯 Take Profit: ${signal.take_profit:{fmt}} (R:R 1:{signal.rr_ratio:.1f})",
            f"━━━━━━━━━━━━━━━━━━",
            f"⏰ {ts}",
            f"📝 {signal.analysis_summary}",
        ]
        return "\n".join(lines)

    def send_momentum_alert(self, signal: MomentumSignal) -> bool:
        """Format and dispatch a momentum signal alert."""
        text = self._format_momentum(signal)
        return self._send(text)


