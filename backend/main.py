"""
Entry point — Breakout Scanner main loop.

Usage
-----
    python -m backend.main               # Normal mode (waits for HH:01)
    python -m backend.main --dry-run     # Dry-run (Telegram alerts logged only)
    python -m backend.main --once        # Single scan then exit
    python -m backend.main --once --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure the project root is on sys.path so ``backend.*`` imports work
# even when invoked as ``python backend/main.py``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

import backend.config as cfg
from backend.market_hours import get_next_scan_time, seconds_until
from backend.scanner import BreakoutScanner

logger = logging.getLogger(__name__)


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
        cfg.TELEGRAM_BOT_TOKEN = __import__("os").getenv("TELEGRAM_BOT_TOKEN", "")
        cfg.TELEGRAM_CHAT_ID = __import__("os").getenv("TELEGRAM_CHAT_ID", "")
        cfg.DRY_RUN = __import__("os").getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

    args = _parse_args()
    dry_run = args.dry_run or cfg.DRY_RUN

    cfg.configure_logging()
    logger.info("Breakout Scanner starting (dry_run=%s, once=%s)", dry_run, args.once)

    scanner = BreakoutScanner(dry_run=dry_run)
    last_day: int | None = None

    try:
        while True:
            # --- Day-reset logic ---
            today = datetime.now(tz=timezone.utc).day
            if last_day is not None and today != last_day:
                scanner.reset_session()
            last_day = today

            # --- Run the scan ---
            signals = scanner.run_scan()
            logger.info("Cycle result: %d qualifying signal(s).", len(signals))

            if args.once:
                logger.info("--once flag set. Exiting after single scan.")
                break

            # --- Wait until next HH:01 ---
            next_scan = get_next_scan_time()
            wait_secs = seconds_until(next_scan)
            logger.info(
                "Next scan at %s UTC (%.0f seconds from now).",
                next_scan.strftime("%H:%M:%S"),
                wait_secs,
            )
            time.sleep(wait_secs)

    except KeyboardInterrupt:
        logger.info("Scanner stopped by user (Ctrl+C).")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
