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
import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

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

    def do_GET(self) -> None:
        # Strip trailing slashes and query parameters for robust routing
        clean_path = self.path.split("?")[0].rstrip("/")
        logger.info("HTTP GET request: path=%s, clean_path=%s", self.path, clean_path)

        if clean_path == "/scan":
            try:
                logger.info("External HTTP trigger received. Starting scan cycle...")
                signals = self.scanner.run_scan()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                res = f'{{"status": "success", "signals_found": {len(signals)}}}'
                self.wfile.write(res.encode("utf-8"))
            except Exception as exc:
                logger.error("HTTP scan handler error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
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
