# Breakout Scanner — Multi-Market Volume-Confirmed Breakout Detection

A quantitative trading scanner that detects breakout opportunities confirmed by institutional volume across **US Equities (S&P 500)** and **Crypto (Binance Spot)** markets.

## Features

- **Daily Support/Resistance Detection** — Swing-pivot clustering with minimum 3-touch validation
- **Hourly Breakout Confirmation** — Body-close only (wicks are strictly ignored)
- **Institutional Volume Filter** — Requires ≥1.5× the 20-period volume SMA
- **ATR-Based Risk Management** — Dynamic stop-loss with 1:2 risk-reward take-profit
- **Market Hours Control** — NYSE Mon–Fri 09:30–16:00 ET; Crypto 24/7
- **Telegram Alerts** — Formatted notifications for each qualifying signal
- **Duplicate Prevention** — Each ticker alerts only once per trading session
- **Dynamic Crypto Tickers** — Automatically fetches top 20 pairs by 24h volume from Binance

## Quick Start

### 1. Install Dependencies
```bash
cd breakout_scanner
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID
```

### 3. Run the Scanner
```bash
# Dry-run mode (alerts logged to console)
python -m backend.main --dry-run --once

# Production loop (scans every hour at HH:01)
python -m backend.main
```

## Architecture

```
backend/
├── config.py          # Centralized configuration from env vars
├── models.py          # Dataclasses (PriceLevel, BreakoutSignal, etc.)
├── levels.py          # Daily support/resistance detection
├── breakout.py        # 1H body-close breakout confirmation
├── volume_filter.py   # Volume ≥ 1.5× SMA(20) filter
├── risk_manager.py    # ATR-based SL + 1:2 R:R TP calculation
├── market_hours.py    # NYSE/Crypto hours + HH:01 scheduling
├── data_fetcher.py    # yfinance (equities) + Binance API (crypto)
├── telegram_notifier.py  # Formatted Telegram alerts
├── scanner.py         # Pipeline orchestrator
└── main.py            # Entry point with loop
```

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `PROXIMITY_THRESHOLD_PCT` | 0.005 (0.5%) | Clustering proximity for level detection |
| `MIN_TOUCHES` | 3 | Minimum touches to validate a level |
| `VOLUME_MULTIPLIER` | 1.5 | Volume must be ≥ this × SMA(20) |
| `ATR_PERIOD` | 14 | ATR lookback period |
| `ATR_SL_MULTIPLIER` | 0.5 | SL margin = ATR × this value |
| `RISK_REWARD_RATIO` | 2.0 | Take-profit = risk × this ratio |
| `CRYPTO_TOP_N` | 20 | Number of top crypto pairs to scan |

## Strategy Logic

1. **Identify** horizontal support/resistance levels on daily charts (≥3 touches)
2. **Confirm** breakout with a 1H candle body closing beyond the level
3. **Filter** by institutional volume (≥1.5× average)
4. **Calculate** stop-loss (ATR-based) and take-profit (1:2 R:R)
5. **Alert** via Telegram with full trade parameters
