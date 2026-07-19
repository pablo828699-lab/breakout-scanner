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
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
from pathlib import Path
import sys
import threading

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

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_PUT(self) -> None:
        clean_path = self.path.split("?")[0].rstrip("/")
        logger.info("HTTP PUT request: path=%s, clean_path=%s", self.path, clean_path)

        if clean_path == "/api/cloud-state":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                put_data = self.rfile.read(content_length)
                
                # Send PUT request to JSONBlob backend-to-backend (no CORS preflight constraints)
                r = requests.put(
                    'https://jsonblob.com/api/jsonBlob/019f6b43-4f24-7714-a721-e0abdf41d4e9',
                    headers={'Content-Type': 'application/json'},
                    data=put_data,
                    timeout=10
                )
                
                self.send_response(r.status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(r.content)
            except Exception as exc:
                logger.error("HTTP cloud-state PUT proxy error: %s", exc)
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
                r = requests.get('https://jsonblob.com/api/jsonBlob/019f6b43-4f24-7714-a721-e0abdf41d4e9', timeout=10)
                self.send_response(r.status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(r.content)
            except Exception as exc:
                logger.error("HTTP cloud-state GET proxy error: %s", exc)
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

                # 2. Fetch equities
                for ticker in equity_tickers:
                    try:
                        import yfinance as yf
                        tk = yf.Ticker(ticker)
                        price = float(getattr(tk.fast_info, 'last_price', 0.0) or getattr(tk.fast_info, 'regular_market_price', 0.0) or 0.0)
                        if price <= 0.0:
                            hist = tk.history(period="1d")
                            if not hist.empty:
                                price = float(hist["Close"].iloc[-1])
                        if price > 0:
                            prices[ticker] = price
                    except Exception as e:
                        logger.error("Failed fetching equity price for %s: %s", ticker, e)

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
            except Exception as exc:
                logger.error("HTTP prices handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res = f'{{"status": "error", "message": "{str(exc)}"}}'
                self.wfile.write(res.encode("utf-8"))
        elif clean_path == "/scan-capitulation":
            try:
                logger.info("Manual capitulation scan triggered via HTTP.")
                # Clean up existing signals file to force overwrite of everything
                try:
                    filepath = os.path.join(os.path.dirname(__file__), "capitulation_signals.json")
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.info("Cleared old capitulation signals file for fresh manual run.")
                except Exception:
                    pass

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
        httpd = HTTPServer(server_address, ScannerHTTPHandler)
        logger.info("Starting HTTP Server on port %d... Ready for cron triggers.", port)
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("HTTP Server stopped by user (Ctrl+C).")
    except Exception as exc:
        logger.critical("Fatal HTTP Server error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
