"""
Breakout Scanner — pipeline orchestrator.

Iterates through all configured tickers for open markets, applying the
full detection → confirmation → volume → risk pipeline for each one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import backend.config as cfg
from backend.breakout import confirm_breakout
from backend.data_fetcher import DataFetcher
from backend.levels import detect_key_levels
from backend.market_hours import is_market_open
from backend.models import BreakoutSignal, OpenPosition, RadarSignal
from backend.risk_manager import calculate_atr, calculate_risk_levels
from backend.telegram_notifier import TelegramNotifier
from backend.trend_radar import evaluate_trend_radar
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
        # Cooldown map: "TICKER:DIRECTION" -> last alert time (UTC).
        self._last_alert: Dict[str, datetime] = {}
        self._load_last_alerts()
        self._open_positions: List[OpenPosition] = []
        self._last_scan_time: Optional[datetime] = None

    def _in_cooldown(self, ticker: str, direction: str, now: datetime) -> bool:
        """True if this asset+direction was alerted within the cooldown window."""
        last = self._last_alert.get(f"{ticker}:{direction}")
        if last is None:
            return False
        return (now - last).total_seconds() < cfg.ALERT_COOLDOWN_HOURS * 3600

    # ------------------------------------------------------------------
    #  Per-ticker analysis
    # ------------------------------------------------------------------

    def scan_ticker(
        self, ticker: str, market: str
    ) -> "Optional[BreakoutSignal | RadarSignal]":
        """Run the full pipeline for a single ticker.

        In ``radar`` mode returns a ``RadarSignal`` (trend detection); in
        ``breakout`` mode returns a ``BreakoutSignal``. ``None`` if no hit.
        """
        # Open-position guard (dedup by asset+direction is applied in run_scan
        # once the signal — and thus its direction — is known).
        if any(p.ticker == ticker for p in self._open_positions):
            logger.debug("%s has an open position — skipping.", ticker)
            return None

        # --- 1. Fetch daily data ---
        if market == "US_EQUITIES":
            daily_df = self._fetcher.fetch_sp500_daily(ticker)
        else:
            daily_df = self._fetcher.fetch_crypto_daily(ticker)

        if daily_df.empty:
            return None

        # --- RADAR MODE: trend + trigger detection on daily data (no SL/TP) ---
        if cfg.DETECTION_MODE == "radar":
            hit = evaluate_trend_radar(
                daily_df,
                adx_period=cfg.RADAR_ADX_PERIOD,
                adx_min=cfg.RADAR_ADX_MIN,
                ema_fast=cfg.RADAR_EMA_FAST,
                ema_slow=cfg.RADAR_EMA_SLOW,
                donchian_n=cfg.RADAR_DONCHIAN_N,
                impulse_atr_mult=cfg.RADAR_IMPULSE_ATR_MULT,
                impulse_volume_mult=cfg.RADAR_IMPULSE_VOLUME_MULT,
                roc_period=cfg.RADAR_ROC_PERIOD,
            )
            if hit is None:
                return None
            return RadarSignal(
                ticker=ticker,
                market=market,
                direction=hit["direction"],
                price=hit["price"],
                triggers=hit["triggers"],
                adx=hit["adx"],
                ema_stack=hit["ema_stack"],
                volume_ratio=hit["volume_ratio"],
                roc_pct=hit["roc_pct"],
                donchian_n=hit["donchian_n"],
                timestamp=datetime.now(tz=timezone.utc),
            )

        # --- BREAKOUT MODE (legacy): detect key levels ---
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
        atr_value = calculate_atr(hourly_df, cfg.ATR_PERIOD)
        result = confirm_breakout(
            hourly_df,
            levels,
            current_price,
            atr_value=atr_value,
            penetration_atr_mult=cfg.PENETRATION_ATR_MULT,
        )
        if result is None:
            return None

        broken_level, direction = result
        entry_price = current_price

        # --- Trend filter: only trade breakouts aligned with the HTF trend ---
        if cfg.TREND_FILTER_ENABLED and len(daily_df) >= cfg.TREND_MA_PERIOD:
            trend_ma = float(
                daily_df["Close"].rolling(cfg.TREND_MA_PERIOD).mean().iloc[-1]
            )
            daily_close = float(daily_df["Close"].iloc[-1])
            if direction == "LONG" and daily_close < trend_ma:
                logger.info(
                    "%s LONG rejected — price below daily SMA%d (%.4f < %.4f).",
                    ticker, cfg.TREND_MA_PERIOD, daily_close, trend_ma,
                )
                return None
            if direction == "SHORT" and daily_close > trend_ma:
                logger.info(
                    "%s SHORT rejected — price above daily SMA%d (%.4f > %.4f).",
                    ticker, cfg.TREND_MA_PERIOD, daily_close, trend_ma,
                )
                return None

        # --- Pullback Guard: Reject if current price has pulled back across the broken level ---
        if direction == "LONG" and entry_price < broken_level.price:
            logger.info(
                "%s breakout rejected — price pulled back below broken resistance %.4f (current=%.4f).",
                ticker,
                broken_level.price,
                entry_price,
            )
            return None
        elif direction == "SHORT" and entry_price > broken_level.price:
            logger.info(
                "%s breakdown rejected — price pulled back above broken support %.4f (current=%.4f).",
                ticker,
                broken_level.price,
                entry_price,
            )
            return None

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

        # --- 4. Risk management (structural stop anchored to the breakout candle) ---
        breakout_candle = hourly_df.iloc[-2]
        stop_loss, take_profit, risk = calculate_risk_levels(
            entry_price=entry_price,
            breakout_candle_low=float(breakout_candle["Low"]),
            breakout_candle_high=float(breakout_candle["High"]),
            direction=direction,
            atr_value=atr_value,
            buffer_atr_mult=cfg.SL_BUFFER_ATR_MULT,
            min_stop_atr_mult=cfg.MIN_STOP_ATR_MULT,
            rr_ratio=cfg.RISK_REWARD_RATIO,
        )

        # --- Extension guard: reject if the live entry has run too far from the
        #     structural stop (chasing an over-extended breakout = poor R:R). ---
        max_risk = atr_value * cfg.MAX_STOP_ATR_MULT
        if risk > max_risk:
            logger.info(
                "%s breakout rejected — entry over-extended (risk %.4f > %.2f×ATR=%.4f).",
                ticker, risk, cfg.MAX_STOP_ATR_MULT, max_risk,
            )
            return None

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
        now = datetime.now(tz=timezone.utc)
        if self._last_scan_time is not None:
            time_since = (now - self._last_scan_time).total_seconds()
            if time_since < 900:  # 15 minutes
                logger.info(
                    "Scan request ignored — scan already completed %.1fs ago (min interval: 900s).",
                    time_since,
                )
                return []

        self._last_scan_time = now
        signals: List[BreakoutSignal] = []
        scan_start = now
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
                        alert_time = datetime.now(tz=timezone.utc)
                        if self._in_cooldown(signal.ticker, signal.direction, alert_time):
                            logger.debug(
                                "%s %s in cooldown (< %.0fh) — skipping alert.",
                                signal.ticker, signal.direction, cfg.ALERT_COOLDOWN_HOURS,
                            )
                            continue
                        self._last_alert[f"{signal.ticker}:{signal.direction}"] = alert_time
                        self._save_last_alerts()
                        self._notifier.send_alert(signal)
                        signals.append(signal)
                        if isinstance(signal, RadarSignal):
                            logger.info(
                                "✅ RADAR: %s %s @ %.4f [ADX=%.1f, %s, Vol=%.1fx, ROC=%.1f%%]",
                                signal.direction, signal.ticker, signal.price,
                                signal.adx, "+".join(signal.triggers),
                                signal.volume_ratio, signal.roc_pct,
                            )
                        else:
                            logger.info(
                                "✅ SIGNAL: %s %s @ %.4f [SL=%.4f, TP=%.4f, Vol=%.1fx]",
                                signal.direction, signal.ticker, signal.entry_price,
                                signal.stop_loss, signal.take_profit, signal.volume_ratio,
                            )
                except Exception as exc:
                    logger.error("Error scanning %s: %s", ticker, exc, exc_info=True)

        elapsed = (datetime.now(tz=timezone.utc) - scan_start).total_seconds()
        logger.info(
            "═══ Scan complete: %d signal(s) found in %.1fs ═══",
            len(signals),
            elapsed,
        )
        if signals:
            self._save_recent_signals(signals)
        return signals

    def _save_recent_signals(self, new_signals: List[BreakoutSignal]) -> None:
        import json
        import os
        filepath = os.path.join(os.path.dirname(__file__), "recent_signals.json")
        
        signals_dict = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    signals_dict = json.load(f)
            except Exception:
                signals_dict = []
                
        for s in new_signals:
            if isinstance(s, RadarSignal):
                signals_dict.append({
                    "type": "radar",
                    "ticker": s.ticker,
                    "market": s.market,
                    "direction": s.direction,
                    "price": s.price,
                    "triggers": s.triggers,
                    "adx": s.adx,
                    "volume_ratio": s.volume_ratio,
                    "roc_pct": s.roc_pct,
                    "timestamp": s.timestamp.strftime("%Y-%m-%d %H:%M UTC"),
                })
            else:
                signals_dict.append({
                    "type": "breakout",
                    "ticker": s.ticker,
                    "market": s.market,
                    "direction": s.direction,
                    "broken_level": s.broken_level,
                    "entry_price": s.entry_price,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "volume_ratio": s.volume_ratio,
                    "atr_value": s.atr_value,
                    "timestamp": s.timestamp.strftime("%Y-%m-%d %H:%M UTC"),
                })
            
        signals_dict = signals_dict[-50:]
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(signals_dict, f, indent=2)
        except Exception as exc:
            logger.error("Failed to save recent signals to disk: %s", exc)

    # ------------------------------------------------------------------
    #  Session management
    # ------------------------------------------------------------------

    def reset_session(self) -> None:
        """Clear the alert-cooldown map (optional — cooldown is time-based now).

        No longer required for correctness: de-duplication expires on its own
        after ``ALERT_COOLDOWN_HOURS``. Kept as a manual "forget everything" hook.
        """
        count = len(self._last_alert)
        self._last_alert.clear()
        self._save_last_alerts()
        logger.info("Session reset — cleared %d cooldown entries.", count)

    def _load_last_alerts(self) -> None:
        import json
        import os
        filepath = os.path.join(os.path.dirname(__file__), "last_alerts.json")
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, val in data.items():
                    self._last_alert[key] = datetime.fromisoformat(val)
            logger.info("Loaded %d alert cooldown records from disk.", len(self._last_alert))
        except Exception as exc:
            logger.warning("Failed to load last alerts: %s", exc)

    def _save_last_alerts(self) -> None:
        import json
        import os
        filepath = os.path.join(os.path.dirname(__file__), "last_alerts.json")
        try:
            data = {k: v.isoformat() for k, v in self._last_alert.items()}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("Saved alert cooldown records to disk.")
        except Exception as exc:
            logger.error("Failed to save last alerts: %s", exc)
