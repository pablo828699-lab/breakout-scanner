"""
Telegram notification service.

Sends formatted breakout alerts via the Telegram Bot API.
In dry-run mode, alerts are logged to the console instead.
"""

from __future__ import annotations

import logging
from datetime import timezone

import requests

from backend.models import BreakoutSignal

logger = logging.getLogger(__name__)

_MARKET_LABELS = {
    "US_EQUITIES": "US Equities (S&P 500)",
    "CRYPTO": "Crypto (Binance Spot)",
}

_DIRECTION_EMOJI = {"LONG": "📈", "SHORT": "📉"}


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

    # ------------------------------------------------------------------

    def send_alert(self, signal: BreakoutSignal) -> bool:
        """Send (or log) a breakout alert.

        Returns ``True`` on success, ``False`` on failure.
        """
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
