"""
Breakout Scanner — pipeline orchestrator.

Iterates through all configured tickers for open markets, applying the
full detection → confirmation → volume → risk pipeline for each one.
"""

from __future__ import annotations

import json
import logging
import os
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
from backend.capitulation_engine import run_capitulation_scan, AsymmetricSignal
from backend.momentum_engine import evaluate_momentum, MomentumSignal

logger = logging.getLogger(__name__)


def parse_iso_timestamp(ts_val: str | datetime | None) -> datetime:
    """Parse ISO 8601 string or legacy UTC string into a UTC-aware datetime."""
    if ts_val is None:
        return datetime.now(timezone.utc)
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=timezone.utc)
        return ts_val
    if not isinstance(ts_val, str):
        return datetime.now(timezone.utc)
    ts_str = ts_val.strip()
    if ts_str.endswith(" UTC"):
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M UTC")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


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

        # --- Capitulation analysis (runs after normal scan) ---
        try:
            cap_signals = self._run_capitulation_scan(markets)
            if cap_signals:
                for cs in cap_signals:
                    alert_time = datetime.now(tz=timezone.utc)
                    cooldown_key = f"CAP:{cs.ticker}:{cs.verdict}"
                    if cooldown_key not in self._last_alert or \
                       (alert_time - self._last_alert[cooldown_key]).total_seconds() > cfg.ALERT_COOLDOWN_HOURS * 3600:
                        self._last_alert[cooldown_key] = alert_time
                        self._save_last_alerts()
                        self._notifier.send_alert(cs)
                        logger.info(
                            "📊 CAPITULATION ALERT sent: %s %s (R:R=1:%.1f, Confidence=%.0f%%)",
                            cs.ticker, cs.verdict, cs.rr_ratio, cs.confidence_score * 100,
                        )
        except Exception as exc:
            logger.error("Capitulation scan failed: %s", exc, exc_info=True)

        # --- Momentum / Squeeze analysis ---
        try:
            mom_signals = self._run_momentum_scan(markets)
            if mom_signals:
                for ms in mom_signals:
                    alert_time = datetime.now(tz=timezone.utc)
                    cooldown_key = f"MOM:{ms.ticker}:{ms.direction}"
                    if cooldown_key not in self._last_alert or \
                       (alert_time - self._last_alert[cooldown_key]).total_seconds() > cfg.ALERT_COOLDOWN_HOURS * 3600:
                        self._last_alert[cooldown_key] = alert_time
                        self._save_last_alerts()
                        self._notifier.send_momentum_alert(ms)
                        logger.info(
                            "🚀 MOMENTUM ALERT sent: %s %s (Trigger=%s, R:R=1:%.1f)",
                            ms.ticker, ms.direction, ms.trigger, ms.rr_ratio,
                        )
        except Exception as exc:
            logger.error("Momentum scan failed: %s", exc, exc_info=True)

        return signals

    def _save_recent_signals(self, new_signals: List[BreakoutSignal | RadarSignal]) -> None:
        import json
        import os
        filepath = os.path.join(os.path.dirname(__file__), "recent_signals.json")
        now = datetime.now(timezone.utc)
        ttl_seconds = 24 * 3600

        existing_by_key: Dict[str, dict] = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    for item in items:
                        ticker = item.get("ticker")
                        direction = item.get("direction", "")
                        if not ticker:
                            continue
                        key = f"{ticker}:{direction}" if direction else ticker
                        ts_val = item.get("last_updated") or item.get("first_detected") or item.get("timestamp")
                        ts_dt = parse_iso_timestamp(ts_val)
                        if (now - ts_dt).total_seconds() < ttl_seconds:
                            existing_by_key[key] = item
            except Exception as exc:
                logger.warning("Failed loading existing recent signals: %s", exc)
                existing_by_key = {}

        for s in new_signals:
            key = f"{s.ticker}:{s.direction}" if getattr(s, "direction", None) else s.ticker
            iso_ts = s.timestamp.isoformat()
            first_detected = (
                existing_by_key[key].get("first_detected")
                if key in existing_by_key and existing_by_key[key].get("first_detected")
                else iso_ts
            )
            if isinstance(s, RadarSignal):
                item_dict = {
                    "type": "radar",
                    "ticker": s.ticker,
                    "market": s.market,
                    "direction": s.direction,
                    "price": s.price,
                    "triggers": s.triggers,
                    "adx": s.adx,
                    "volume_ratio": s.volume_ratio,
                    "roc_pct": s.roc_pct,
                    "ema_stack": s.ema_stack,
                    "timestamp": iso_ts,
                    "first_detected": first_detected,
                    "last_updated": iso_ts,
                }
            else:
                item_dict = {
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
                    "timestamp": iso_ts,
                    "first_detected": first_detected,
                    "last_updated": iso_ts,
                }
            existing_by_key[key] = item_dict

        signals_dict = list(existing_by_key.values())
        signals_dict.sort(
            key=lambda x: parse_iso_timestamp(x.get("last_updated") or x.get("timestamp")),
            reverse=True,
        )
        if len(signals_dict) > 100:
            signals_dict = signals_dict[:100]

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(signals_dict, f, indent=2)
            self._sync_to_render_backend("/api/candidates", signals_dict)
        except Exception as exc:
            logger.error("Failed to save recent signals to disk: %s", exc)

    def _run_capitulation_scan(
        self, markets: Dict[str, List[str]],
    ) -> List[AsymmetricSignal]:
        """Run capitulation analysis on all tickers across open markets."""
        tickers_with_data = []
        benchmark_dfs = {}

        # Fetch benchmark data
        try:
            spy_df = self._fetcher.fetch_sp500_daily("SPY")
            if not spy_df.empty:
                benchmark_dfs["US_EQUITIES"] = spy_df
        except Exception:
            pass
        try:
            btc_df = self._fetcher.fetch_crypto_daily("BTCUSDT")
            if not btc_df.empty:
                benchmark_dfs["CRYPTO"] = btc_df
        except Exception:
            pass

        for market, tickers in markets.items():
            for ticker in tickers:
                try:
                    if market == "US_EQUITIES":
                        daily_df = self._fetcher.fetch_sp500_daily(ticker)
                        hourly_df = self._fetcher.fetch_sp500_hourly(ticker)
                    else:
                        daily_df = self._fetcher.fetch_crypto_daily(ticker)
                        hourly_df = self._fetcher.fetch_crypto_hourly(ticker)

                    if not daily_df.empty and not hourly_df.empty:
                        tickers_with_data.append((ticker, market, daily_df, hourly_df))
                except Exception as exc:
                    logger.debug("Capitulation data fetch failed for %s: %s", ticker, exc)

        if not tickers_with_data:
            return []

        signals = run_capitulation_scan(tickers_with_data, benchmark_dfs=benchmark_dfs)

        # Persist the calculated signals to capitulation_signals.json
        try:
            self._save_capitulation_signals(signals)
        except Exception as exc:
            logger.error("Failed persisting manual capitulation signals: %s", exc)

        return signals

    def _save_capitulation_signals(self, signals: List[AsymmetricSignal]) -> None:
        import json
        import os
        filepath = os.path.join(os.path.dirname(__file__), "capitulation_signals.json")
        now = datetime.now(timezone.utc)
        ttl_seconds = 24 * 3600

        existing_by_ticker: Dict[str, dict] = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    for item in items:
                        ticker_key = item.get("ticker")
                        if not ticker_key:
                            continue
                        ts_val = item.get("last_updated") or item.get("first_detected") or item.get("timestamp")
                        ts_dt = parse_iso_timestamp(ts_val)
                        verdict = item.get("verdict")
                        if (now - ts_dt).total_seconds() < ttl_seconds and verdict != "INVALIDATED":
                            existing_by_ticker[ticker_key] = item
            except Exception as exc:
                logger.warning("Failed loading existing capitulation signals: %s", exc)
                existing_by_ticker = {}

        for s in signals:
            iso_ts = s.timestamp.isoformat()
            first_detected = (
                existing_by_ticker[s.ticker].get("first_detected")
                if s.ticker in existing_by_ticker and existing_by_ticker[s.ticker].get("first_detected")
                else iso_ts
            )
            existing_by_ticker[s.ticker] = {
                "type": "asymmetric",
                "ticker": s.ticker,
                "market": s.market,
                "asset_class": getattr(s, "asset_class", "ACCIONES"),
                "verdict": s.verdict,
                "drop_pct": s.drop_pct,
                "entry_price": s.entry_price,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "rr_ratio": s.rr_ratio,
                "position_size_qty": s.position_size_qty,
                "poc": s.poc,
                "vah": s.vah,
                "val": s.val,
                "fvg_zone": list(s.fvg_zone),
                "ob_zone": list(s.ob_zone),
                "msb_type": s.msb_type,
                "is_idiosyncratic": s.is_idiosyncratic,
                "fundamental_ok": s.fundamental_ok,
                "confidence_score": s.confidence_score,
                "analysis_summary": s.analysis_summary,
                "timestamp": iso_ts,
                "first_detected": first_detected,
                "last_updated": iso_ts,
            }

        signals_dict = list(existing_by_ticker.values())
        signals_dict.sort(
            key=lambda x: parse_iso_timestamp(x.get("last_updated") or x.get("timestamp")),
            reverse=True,
        )
        if len(signals_dict) > 100:
            signals_dict = signals_dict[:100]

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(signals_dict, f, indent=2)
            logger.info("Saved %d capitulation signals to disk.", len(signals_dict))
            self._sync_to_render_backend("/api/capitulation", signals_dict)
        except Exception as exc:
            logger.error("Failed to save capitulation signals: %s", exc)

    def _run_momentum_scan(self, markets: Dict[str, List[str]]) -> List[MomentumSignal]:
        """Run momentum and squeeze breakout analysis on all tickers."""
        signals: List[MomentumSignal] = []
        for market, tickers in markets.items():
            for ticker in tickers:
                try:
                    if market == "US_EQUITIES":
                        daily_df = self._fetcher.fetch_sp500_daily(ticker)
                    else:
                        daily_df = self._fetcher.fetch_crypto_daily(ticker)

                    if daily_df is not None and len(daily_df) >= 55:
                        sig = evaluate_momentum(daily_df, ticker, market=market)
                        if sig:
                            signals.append(sig)
                except Exception as exc:
                    logger.debug("Momentum eval failed for %s: %s", ticker, exc)

        if signals:
            try:
                self._save_momentum_signals(signals)
            except Exception as exc:
                logger.error("Failed persisting momentum signals: %s", exc)

        return signals

    def _save_momentum_signals(self, signals: List[MomentumSignal]) -> None:
        import json
        import os
        filepath = os.path.join(os.path.dirname(__file__), "momentum_signals.json")
        now = datetime.now(timezone.utc)
        ttl_seconds = 24 * 3600

        existing_by_ticker: Dict[str, dict] = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    for item in items:
                        ticker_key = item.get("ticker")
                        if not ticker_key:
                            continue
                        ts_val = item.get("last_updated") or item.get("first_detected") or item.get("timestamp")
                        ts_dt = parse_iso_timestamp(ts_val)
                        if (now - ts_dt).total_seconds() < ttl_seconds:
                            existing_by_ticker[ticker_key] = item
            except Exception as exc:
                logger.warning("Failed loading existing momentum signals: %s", exc)
                existing_by_ticker = {}

        for s in signals:
            iso_ts = s.timestamp.isoformat()
            first_detected = (
                existing_by_ticker[s.ticker].get("first_detected")
                if s.ticker in existing_by_ticker and existing_by_ticker[s.ticker].get("first_detected")
                else iso_ts
            )
            existing_by_ticker[s.ticker] = {
                "type": "momentum",
                "ticker": s.ticker,
                "market": s.market,
                "direction": s.direction,
                "trigger": s.trigger,
                "entry_price": s.entry_price,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "rr_ratio": s.rr_ratio,
                "rvol": s.rvol,
                "roc_10": s.roc_10,
                "rsi": s.rsi,
                "squeeze_status": s.squeeze_status,
                "ema_stack": s.ema_stack,
                "confidence_score": s.confidence_score,
                "analysis_summary": s.analysis_summary,
                "timestamp": iso_ts,
                "first_detected": first_detected,
                "last_updated": iso_ts,
                "asset_class": getattr(s, "asset_class", "ACCIONES"),
            }

        signals_dict = list(existing_by_ticker.values())
        signals_dict.sort(
            key=lambda x: parse_iso_timestamp(x.get("last_updated") or x.get("timestamp")),
            reverse=True,
        )
        if len(signals_dict) > 100:
            signals_dict = signals_dict[:100]

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(signals_dict, f, indent=2)
            logger.info("Saved %d momentum signals to disk.", len(signals_dict))
            self._sync_to_render_backend("/api/momentum", signals_dict)
        except Exception as exc:
            logger.error("Failed to save momentum signals: %s", exc)

    def _sync_to_render_backend(self, endpoint_path: str, data: list) -> None:
        """Sync json data directly to Render backend with retries and timeout for Cold-Start toleration."""
        import os
        import time
        import requests
        render_url = os.getenv("RENDER_BACKEND_URL", "https://breakout-scanner-xg9f.onrender.com").rstrip("/")
        url = f"{render_url}{endpoint_path}"
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(url, json=data, timeout=30)
                if resp.status_code == 200:
                    logger.info("Successfully synced %d items to Render backend (%s).", len(data), endpoint_path)
                    return
                else:
                    logger.warning("Render sync status %d on attempt %d/3 for %s: %s", resp.status_code, attempt, endpoint_path, resp.text)
            except Exception as exc:
                logger.warning("Render sync error on attempt %d/3 for %s: %s", attempt, endpoint_path, exc)
            time.sleep(3)

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
