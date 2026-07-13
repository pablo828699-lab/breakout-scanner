"""
Breakout Scanner — pipeline orchestrator.

Iterates through all configured tickers for open markets, applying the
full detection → confirmation → volume → risk pipeline for each one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Set

import backend.config as cfg
from backend.breakout import confirm_breakout
from backend.data_fetcher import DataFetcher
from backend.levels import detect_key_levels
from backend.market_hours import is_market_open
from backend.models import BreakoutSignal, OpenPosition
from backend.risk_manager import calculate_risk_levels
from backend.telegram_notifier import TelegramNotifier
from backend.volume_filter import passes_volume_filter

logger = logging.getLogger(__name__)


class BreakoutScanner:
    """Orchestrate the full breakout-scanning pipeline."""

    def __init__(self, dry_run: bool = True) -> None:
        self._fetcher = DataFetcher()
        self._notifier = TelegramNotifier(
            bot_token=cfg.TELEGRAM_BOT_TOKEN,
            chat_id=cfg.TELEGRAM_CHAT_ID,
            dry_run=dry_run,
        )
        self._alerted_tickers: Set[str] = set()
        self._open_positions: List[OpenPosition] = []

    # ------------------------------------------------------------------
    #  Per-ticker analysis
    # ------------------------------------------------------------------

    def scan_ticker(
        self, ticker: str, market: str
    ) -> Optional[BreakoutSignal]:
        """Run the full pipeline for a single ticker.

        Returns a ``BreakoutSignal`` if the ticker qualifies, else ``None``.
        """
        # Duplicate / open-position guard
        if ticker in self._alerted_tickers:
            logger.debug("%s already alerted this session — skipping.", ticker)
            return None

        if any(p.ticker == ticker for p in self._open_positions):
            logger.debug("%s has an open position — skipping.", ticker)
            return None

        # --- 1. Fetch daily data & detect key levels ---
        if market == "US_EQUITIES":
            daily_df = self._fetcher.fetch_sp500_daily(ticker)
        else:
            daily_df = self._fetcher.fetch_crypto_daily(ticker)

        if daily_df.empty:
            return None

        levels = detect_key_levels(
            daily_df,
            proximity_pct=cfg.PROXIMITY_THRESHOLD_PCT,
            min_touches=cfg.MIN_TOUCHES,
        )
        if not levels:
            logger.debug("%s — no valid key levels found.", ticker)
            return None

        # --- 2. Fetch hourly data & confirm breakout ---
        if market == "US_EQUITIES":
            hourly_df = self._fetcher.fetch_sp500_hourly(ticker)
        else:
            hourly_df = self._fetcher.fetch_crypto_hourly(ticker)

        if hourly_df.empty:
            return None

        current_price = float(hourly_df["Close"].iloc[-1])
        result = confirm_breakout(hourly_df, levels, current_price)
        if result is None:
            return None

        broken_level, direction = result

        # --- 3. Volume filter ---
        passes, volume_ratio = passes_volume_filter(
            hourly_df,
            multiplier=cfg.VOLUME_MULTIPLIER,
            sma_period=cfg.VOLUME_SMA_PERIOD,
        )
        if not passes:
            logger.info(
                "%s breakout rejected — insufficient volume (%.2fx < %.1fx).",
                ticker,
                volume_ratio,
                cfg.VOLUME_MULTIPLIER,
            )
            return None

        # --- 4. Risk management ---
        entry_price = current_price
        stop_loss, take_profit, atr_value = calculate_risk_levels(
            entry_price=entry_price,
            broken_level=broken_level.price,
            direction=direction,
            hourly_df=hourly_df,
            atr_period=cfg.ATR_PERIOD,
            atr_sl_multiplier=cfg.ATR_SL_MULTIPLIER,
            rr_ratio=cfg.RISK_REWARD_RATIO,
        )

        signal = BreakoutSignal(
            ticker=ticker,
            market=market,
            direction=direction,
            broken_level=broken_level.price,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume_ratio=volume_ratio,
            atr_value=atr_value,
            timestamp=datetime.now(tz=timezone.utc),
        )
        return signal

    # ------------------------------------------------------------------
    #  Full-market scan
    # ------------------------------------------------------------------

    def run_scan(self) -> List[BreakoutSignal]:
        """Scan all configured tickers across open markets."""
        signals: List[BreakoutSignal] = []
        scan_start = datetime.now(tz=timezone.utc)
        logger.info("═══ Scan cycle started at %s ═══", scan_start.strftime("%H:%M:%S UTC"))

        markets = {
            "US_EQUITIES": self._fetcher.get_sp500_tickers(),
            "CRYPTO": self._fetcher.get_crypto_tickers(),
        }

        for market, tickers in markets.items():
            if not is_market_open(market):
                logger.info("Market %s is CLOSED — skipping %d tickers.", market, len(tickers))
                continue

            logger.info("Scanning %s (%d tickers)…", market, len(tickers))
            for ticker in tickers:
                try:
                    signal = self.scan_ticker(ticker, market)
                    if signal is not None:
                        self._alerted_tickers.add(ticker)
                        self._notifier.send_alert(signal)
                        signals.append(signal)
                        logger.info(
                            "✅ SIGNAL: %s %s @ %.4f [SL=%.4f, TP=%.4f, Vol=%.1fx]",
                            signal.direction,
                            signal.ticker,
                            signal.entry_price,
                            signal.stop_loss,
                            signal.take_profit,
                            signal.volume_ratio,
                        )
                except Exception as exc:
                    logger.error("Error scanning %s: %s", ticker, exc, exc_info=True)

        elapsed = (datetime.now(tz=timezone.utc) - scan_start).total_seconds()
        logger.info(
            "═══ Scan complete: %d signal(s) found in %.1fs ═══",
            len(signals),
            elapsed,
        )
        return signals

    # ------------------------------------------------------------------
    #  Session management
    # ------------------------------------------------------------------

    def reset_session(self) -> None:
        """Clear per-session state (call at the start of a new trading day)."""
        count = len(self._alerted_tickers)
        self._alerted_tickers.clear()
        logger.info("Session reset — cleared %d alerted tickers.", count)
