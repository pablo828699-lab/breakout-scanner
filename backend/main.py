"""
Entry point — Breakout Scanner main loop.

Usage
-----
    python -m backend.main               # Normal mode (waits for HH:01)
    python -m backend.main --dry-run     # Dry-run (Telegram alerts logged only)
    python -m backend.main --once        # Single scan then exit
    python -m backend.main --once --dry-run
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

from dotenv import load_dotenv

import requests
import backend.config as cfg
from backend.scanner import BreakoutScanner

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)


class ScannerHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler to trigger breakout scans via webhooks."""
    
    scanner: BreakoutScanner = None

    def log_message(self, format, *args):
        # Redirect http.server logs to our logger
        logger.info("%s - - %s" % (self.address_string(), format % args))

    def _enviar_respuesta_json(self, data: dict | list, status: int = 200) -> None:
        """Envía una respuesta JSON con headers CORS."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _enviar_error_json(self, exc: Exception, status: int = 500) -> None:
        """Envía un error JSON serializado de forma segura (sin interpolación manual)."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        payload = {"status": "error", "message": str(exc)}
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        clean_path = self.path.split("?")[0].rstrip("/")
        logger.info("HTTP POST request: path=%s, clean_path=%s", self.path, clean_path)

        if clean_path in ("/api/capitulation", "/api/candidates", "/api/momentum"):
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                json_data = json.loads(post_data.decode('utf-8'))
                
                if clean_path == "/api/capitulation":
                    filename = "capitulation_signals.json"
                elif clean_path == "/api/momentum":
                    filename = "momentum_signals.json"
                else:
                    filename = "recent_signals.json"
                filepath = os.path.join(os.path.dirname(__file__), filename)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2)
                
                logger.info("Successfully updated %s via HTTP POST (%d items).", filename, len(json_data) if isinstance(json_data, list) else 1)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "ok", "message": "Updated {filename}"}}'
                self.wfile.write(res.encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP POST sync handler error for %s: %s", clean_path, exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

    def do_PUT(self) -> None:
        clean_path = self.path.split("?")[0].rstrip("/")
        logger.info("HTTP PUT request: path=%s, clean_path=%s", self.path, clean_path)

        if clean_path == "/api/cloud-state":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                put_data = self.rfile.read(content_length)
                
                filepath = os.path.join(os.path.dirname(__file__), "cloud_state.json")
                with open(filepath, "wb") as f:
                    f.write(put_data)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except Exception as exc:
                logger.error("HTTP cloud-state PUT handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

    def do_GET(self) -> None:
        # Strip trailing slashes and query parameters for robust routing
        clean_path = self.path.split("?")[0].rstrip("/")
        logger.info("HTTP GET request: path=%s, clean_path=%s", self.path, clean_path)

        if clean_path == "/scan":
            try:
                logger.info("External HTTP trigger received. Spawning background scan thread...")
                
                thread = threading.Thread(target=self.scanner.run_scan, name="ScanThread")
                thread.start()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = '{"status": "processing", "message": "Scan cycle started in background"}'
                self.wfile.write(res.encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP scan handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        elif clean_path == "/logs":
            try:
                log_filepath = os.path.join(os.path.dirname(__file__), "app.log")
                logs_text = "No log file found."
                if os.path.exists(log_filepath):
                    with open(log_filepath, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        logs_text = "".join(lines[-250:])
                
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(logs_text.encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP logs handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/api/candidates":
            try:
                filepath = os.path.join(os.path.dirname(__file__), "recent_signals.json")
                data = []
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP candidates handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/api/cloud-state":
            try:
                filepath = os.path.join(os.path.dirname(__file__), "cloud_state.json")
                data = {}
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP cloud-state GET handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/api/capitulation":
            try:
                filepath = os.path.join(os.path.dirname(__file__), "capitulation_signals.json")
                data = []
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP capitulation handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/api/momentum":
            try:
                filepath = os.path.join(os.path.dirname(__file__), "momentum_signals.json")
                data = []
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP momentum handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/api/prices":
            try:
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                tickers_str = query.get("tickers", [""])[0]
                if not tickers_str:
                    raise ValueError("Missing 'tickers' query parameter")

                tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
                prices = {}

                crypto_tickers = [t for t in tickers if t.endswith("USDT")]
                equity_tickers = [t for t in tickers if not t.endswith("USDT")]

                # 1. Fetch all crypto prices in a single Binance API request
                if crypto_tickers:
                    try:
                        # Binance allows batch fetching if no symbol is specified or passing a list
                        if len(crypto_tickers) == 1:
                            r = requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={crypto_tickers[0]}", timeout=5)
                            if r.status_code == 200:
                                prices[crypto_tickers[0]] = float(r.json().get("price", 0.0))
                        else:
                            r = requests.get("https://data-api.binance.vision/api/v3/ticker/price", timeout=5)
                            if r.status_code == 200:
                                raw_data = r.json()
                                crypto_set = set(crypto_tickers)
                                for item in raw_data:
                                    sym = item.get("symbol")
                                    if sym in crypto_set:
                                        prices[sym] = float(item.get("price", 0.0))
                    except Exception as e:
                        logger.error("Failed batch fetching crypto prices: %s", e)

                # Load cached signal prices for instant fallback (0ms latency)
                cached_signal_prices = {}
                try:
                    cap_file = _PROJECT_ROOT / "backend" / "capitulation_signals.json"
                    if cap_file.exists():
                        with open(cap_file, "r", encoding="utf-8") as f:
                            for item in json.load(f):
                                if "ticker" in item and "entry_price" in item:
                                    cached_signal_prices[item["ticker"].upper()] = float(item["entry_price"])
                except Exception:
                    pass

                def fetch_equity_price(ticker):
                    now_ms = int(time.time() * 1000)
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                        "Content-Type": "application/json",
                    }
                    hl_candidates = [f"xyz:{ticker}", ticker] if not ticker.startswith("xyz:") else [ticker]
                    for hl_coin in hl_candidates:
                        payload = {
                            "type": "candleSnapshot",
                            "req": {"coin": hl_coin, "interval": "1m", "startTime": now_ms - (15 * 60 * 1000), "endTime": now_ms}
                        }
                        try:
                            r = requests.post("https://api.hyperliquid.xyz/info", json=payload, headers=headers, timeout=3.5)
                            if r.status_code == 200:
                                candles = r.json()
                                if candles and isinstance(candles, list) and len(candles) > 0:
                                    return ticker, float(candles[-1]["c"])
                        except Exception:
                            pass

                    return ticker, cached_signal_prices.get(ticker, 0.0)

                if equity_tickers:
                    with ThreadPoolExecutor(max_workers=min(len(equity_tickers), 10)) as executor:
                        for ticker, price in executor.map(fetch_equity_price, equity_tickers):
                            if price > 0:
                                prices[ticker] = price

                # 3. Fallback check for missing cryptos
                for ticker in crypto_tickers:
                    if ticker not in prices or prices[ticker] <= 0:
                        try:
                            import yfinance as yf
                            yf_symbol = ticker.replace("USDT", "-USD")
                            tk = yf.Ticker(yf_symbol)
                            price = float(getattr(tk.fast_info, 'last_price', 0.0) or 0.0)
                            if price > 0:
                                prices[ticker] = price
                        except Exception:
                            pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(prices).encode("utf-8"))
            except (ConnectionAbortedError, BrokenPipeError):
                pass
            except Exception as exc:
                logger.error("HTTP prices handler error: %s", exc)
                try:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    res = f'{{"status": "error", "message": "{str(exc)}"}}'
                    self.wfile.write(res.encode("utf-8"))
                except Exception:
                    pass
        elif clean_path == "/api/volume-profile":
            try:
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                ticker = query.get("ticker", [""])[0].strip().upper()
                if not ticker:
                    raise ValueError("Missing 'ticker' query parameter")

                # Fetch hourly data using unified fetch_candles
                from backend.data_fetcher import fetch_candles
                df = fetch_candles(ticker, timeframe="1h", limit=200)
                df_daily = fetch_candles(ticker, timeframe="1d", limit=10)
                
                if df is None or df.empty or df_daily is None or df_daily.empty:
                    raise ValueError(f"No OHLCV data available for ticker '{ticker}'")
                    
                price = float(df_daily["Close"].iloc[-1])

                from backend.volume_profile import analyze_volume_profile
                profile_res = analyze_volume_profile(df, float(price))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(profile_res).encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP volume profile diagnostics error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/scan-capitulation":
            try:
                logger.info("Manual capitulation scan triggered via HTTP.")

                thread = threading.Thread(
                    target=self.scanner._run_capitulation_scan,
                    args=({
                        "CRYPTO": self.scanner._fetcher.get_crypto_tickers(),
                        "US_EQUITIES": self.scanner._fetcher.get_sp500_tickers()
                    },),
                    name="CapitulationScanThread",
                )
                thread.start()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = '{"status": "processing", "message": "Capitulation scan started in background"}'
                self.wfile.write(res.encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP capitulation scan handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/scan-momentum":
            try:
                logger.info("Manual momentum scan triggered via HTTP.")

                thread = threading.Thread(
                    target=self.scanner._run_momentum_scan,
                    args=({
                        "CRYPTO": self.scanner._fetcher.get_crypto_tickers(),
                        "US_EQUITIES": self.scanner._fetcher.get_sp500_tickers()
                    },),
                    name="MomentumScanThread",
                )
                thread.start()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = '{"status": "processing", "message": "Momentum scan started in background"}'
                self.wfile.write(res.encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP momentum scan handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/api/perp-screener":
            try:
                from urllib.parse import urlparse, parse_qs
                from backend.perp_screener import evaluate_perp_candidate, scan_perps_universe

                query = parse_qs(urlparse(self.path).query)
                tickers_str = query.get("tickers", [""])[0].strip()
                direction = query.get("direction", ["LONG"])[0].strip().upper()
                ticker_single = query.get("ticker", [""])[0].strip().upper()

                try:
                    leverage = float(query.get("leverage", ["5"])[0])
                except ValueError:
                    leverage = 5.0

                if ticker_single:
                    res = evaluate_perp_candidate(ticker_single, direction=direction, leverage=leverage)
                else:
                    target_tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()] if tickers_str else None
                    res = scan_perps_universe(target_tickers, leverage=leverage)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))
            except (ConnectionAbortedError, BrokenPipeError):
                pass
            except Exception as exc:
                logger.error("HTTP perp-screener handler error: %s", exc)
                try:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    res = f'{{"status": "error", "message": "{str(exc)}"}}'
                    self.wfile.write(res.encode("utf-8"))
                except Exception:
                    pass
        elif clean_path == "/api/perp-journal":
            try:
                from backend.perp_journal import update_paper_positions
                journal_res = update_paper_positions()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(journal_res, indent=2).encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP perp-journal handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "" or clean_path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Breakout Scanner Status</title>
                    <meta charset="utf-8">
                </head>
                <body style="font-family: system-ui, sans-serif; background: #0a0e17; color: #f1f5f9; padding: 40px; text-align: center;">
                    <h1 style="color: #3b82f6; font-size: 2.5rem; margin-bottom: 10px;">Breakout Scanner Active</h1>
                    <p style="color: #94a3b8; font-size: 1.1rem; margin-bottom: 30px;">Multi-Market Volume-Confirmed Breakout Detection System</p>
                    <div style="display: inline-block; background: #111827; border: 1px border #1e293b; padding: 20px 40px; border-radius: 12px; margin-bottom: 20px;">
                        <span style="display: inline-block; width: 10px; height: 10px; background: #10b981; border-radius: 50%; margin-right: 8px;"></span>
                        <span style="font-weight: bold; color: #e2e8f0; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.05em;">Servidor en Línea</span>
                    </div>
                    <p style="font-size: 0.9rem; color: #64748b;">
                        Visita <a href="/scan" style="color: #06b6d4; text-decoration: none; font-weight: bold;">/scan</a> para forzar una búsqueda manual.
                    </p>
                </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-Market Breakout Scanner with Volume Confirmation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Log Telegram alerts to console instead of sending them.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Run a single scan cycle and exit (useful for testing).",
    )
    return parser.parse_args()


def main() -> None:
    # Load .env from project root
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        # Re-read config values that depend on env vars
        cfg.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        cfg.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
        cfg.DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

    args = _parse_args()
    dry_run = args.dry_run or cfg.DRY_RUN

    cfg.configure_logging()
    
    scanner = BreakoutScanner(dry_run=dry_run)
    ScannerHTTPHandler.scanner = scanner

    if args.once:
        logger.info("Executing single scan cycle (--once flag detected)...")
        signals = scanner.run_scan()
        logger.info("Scan completed. %d signal(s) found.", len(signals))
        return

    # Start HTTP Server for 24/7 cron-job activations
    port = int(os.getenv("PORT", "8080"))
    server_address = ("", port)
    
    try:
        httpd = ThreadingHTTPServer(server_address, ScannerHTTPHandler)
        logger.info("Starting Multi-Threaded HTTP Server on port %d... Ready for cron triggers.", port)
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("HTTP Server stopped by user (Ctrl+C).")
    except Exception as exc:
        logger.critical("Fatal HTTP Server error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
