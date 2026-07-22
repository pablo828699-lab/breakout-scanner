# Comprehensive Audit Report: Backend Data Fetching & Network Utilities

**Target File**: `c:/Users/HP/mi-bot/breakout_scanner/backend/data_fetcher.py`  
**Related Backend Utilities**: `config.py`, `fundamental_filter.py`, `telegram_notifier.py`, `scanner.py`  
**Auditor Archetype**: `teamwork_preview_explorer`  
**Date**: 2026-07-21  

---

## Executive Summary

An in-depth, read-only audit of `backend/data_fetcher.py` and associated backend network utilities was conducted. The audit evaluated data fetching mechanisms across **US Equities**, **Crypto**, and **Mineras (Bitcoin Miners)**, focusing on exception handling, stderr muting (`os.devnull`), HTTP session reuse, header management, and rate-limiting/retry behavior.

Key vulnerabilities and architecture weaknesses discovered:
1. **Double-Blinded Error Muting (`os.devnull` & Logger Silencing)**: `yfinance` download stderr is redirected to `os.devnull` (`data_fetcher.py:126-127`), while `config.py:196` silences the `yfinance` logger entirely (`CRITICAL + 1`). Rate limits (HTTP 429), API changes, and data errors are completely invisible.
2. **Un-sessionized Binance & Telegram Requests**: Binance API calls (`_binance_request`, `data_fetcher.py:70`) and Telegram notifications (`telegram_notifier.py:166`) issue raw `requests.get()` / `requests.post()` calls without `requests.Session()`, resulting in dozens of redundant TCP/TLS handshakes per scan cycle.
3. **Zero Exponential Backoff / Naive Retry**: No backoff or jitter algorithm exists anywhere in the backend. When HTTP 429 or server errors occur, `_binance_request` immediately switches hosts or fails outright.
4. **Un-configured `yf.Ticker` in `fundamental_filter.py`**: While `DataFetcher` configures a custom `User-Agent` session for `yf.download()`, `fundamental_filter.py:96` executes un-configured `yf.Ticker(ticker)` calls, bypassing custom headers and triggering rate limits.
5. **Silent Mock Data Fallback**: When Binance and Yahoo Finance fail for crypto, `data_fetcher.py:217,231` silently generates random-walk mock data using `numpy`, masking network or rate-limit failures from operators.

---

## 1. Data Fetching Architecture Overview

Data fetching is partitioned into three asset categories across `config.py`, `data_fetcher.py`, `fundamental_filter.py`, and `scanner.py`:

```
                       ┌─────────────────────────┐
                       │   BreakoutScanner       │
                       └───────────┬─────────────┘
                                   │
                ┌──────────────────┴──────────────────┐
                ▼                                     ▼
        [ US_EQUITIES ]                           [ CRYPTO ]
   (S&P 500, Volatile Caps,                     (Binance Spot)
    Bitcoin Miners/Mineras)                           │
                │                                     ├─► Primary: Binance REST API
                ▼                                     │   (api.binance.com)
         yfinance Library                             │
   (_safe_yf_download / yf.Ticker)                    ├─► Geo-Fallback: Binance Vision
                │                                     │   (data-api.binance.vision)
                ├─► Daily & Hourly OHLCV              │
                └─► Quarterly Financials              ├─► Backup: yfinance (USDT->-USD)
                    (Solvency Ratios)                 │
                                                      └─► Fallback: Mock Data (Numpy)
```

### 1.1 US Equities & Mineras
- **Tickers Source**: Defined in `backend/config.py:88-101` (`SP500_TICKERS`). Includes S&P 500 mega-caps (`AAPL`, `MSFT`), volatile large-caps (`NFLX`, `MU`, `COIN`, `MSTR`), commodity ETFs (`GLD`, `SLV`, `USO`), and **Bitcoin Miners / Mineras** (`HUT`, `KEEL`, `RIOT`, `MARA`, `CLSK`, `IREN`, `CIFR`, `WULF`, `BITF`).
- **Fetch Pipeline**:
  - `DataFetcher.fetch_sp500_daily(ticker)` (`data_fetcher.py:134-142`): Fetches `DAILY_LOOKBACK_DAYS` (300d) of 1-day candles.
  - `DataFetcher.fetch_sp500_hourly(ticker)` (`data_fetcher.py:144-162`): Fetches `1mo` of 1-hour candles.
- **Fundamental Solvency Data**:
  - `fundamental_filter.py:80-128` (`fetch_fundamentals`): Calls `yf.Ticker(ticker)` to pull `quarterly_financials` and `quarterly_balance_sheet`.

### 1.2 Crypto Market
- **Tickers Source**: Configured via `CRYPTO_WATCHLIST` (`config.py:115-128`, 40 curated USDT pairs) or dynamic top-N by 24h volume (`data_fetcher.py:238-289`).
- **Fetch Pipeline**:
  - Primary: `DataFetcher._binance_klines(symbol, interval, limit)` (`data_fetcher.py:169-193`), calling `_binance_request("/api/v3/klines", ...)` (`data_fetcher.py:51-88`).
  - Known-good host tracking (`_working_host`, `data_fetcher.py:48`): Tries `https://api.binance.com`, falls back to `https://data-api.binance.vision` if HTTP 451 (geo-blocked) or network error occurs.
  - Backup: `_fetch_yfinance_crypto` (`data_fetcher.py:195-205`), mapping `USDT` to `-USD` (e.g. `BTCUSDT` -> `BTC-USD`).
  - Fallback: `_generate_mock_ohlcv` (`data_fetcher.py:299-327`), producing synthetic random walk data if both Binance and yfinance return empty.

---

## 2. Evidence Chain: Silence & Muting Analysis (`os.devnull` & Swallowed Errors)

### 2.1 Stderr Redirection to `os.devnull`
- **Location**: `backend/data_fetcher.py:126-127` inside `_safe_yf_download`:
  ```python
  116:         try:
  ...
  126:             with open(os.devnull, "w") as devnull:
  127:                 with redirect_stderr(devnull):
  128:                     df = yf.download(ticker, **download_kwargs)
  129:             return df
  ```
- **Evidence & Impact**:
  `yf.download()` outputs verbose diagnostic messages directly to `sys.stderr` when rate-limited (HTTP 429), when crumb/cookie authentication fails, or when a ticker symbol is invalid/delisted. Wrapping `yf.download` in `redirect_stderr(devnull)` silently swallows all stderr output. As a result, terminal logs show no indication of why `yf.download` returned an empty DataFrame.

### 2.2 Complete Logger Silencing in `config.py`
- **Location**: `backend/config.py:196`:
  ```python
  195:     logging.getLogger("urllib3").setLevel(logging.WARNING)
  196:     logging.getLogger("yfinance").setLevel(logging.CRITICAL + 1)
  197:     logging.getLogger("binance").setLevel(logging.WARNING)
  ```
- **Evidence & Impact**:
  Setting `logging.getLogger("yfinance").setLevel(logging.CRITICAL + 1)` disables all internal logging from `yfinance` at level 51 (above `CRITICAL`). Combined with `os.devnull` redirection, `yfinance` is double-blinded: neither standard logging nor stderr can report API blocks, rate limits, or network failures.

### 2.3 Swallowed Exceptions & Generic Catch-Alls
- **Location 1**: `data_fetcher.py:81-84` in `_binance_request`:
  ```python
  81:         except Exception as exc:
  82:             last_error = f"{host} → {type(exc).__name__}: {exc}"
  83:             logger.warning("Binance host %s failed (%s) — trying next host.", host, exc)
  84:             continue
  ```
  *Impact*: Catches broad `Exception`. HTTP 429 (Too Many Requests), 418 (IP Ban), 502/503 (Server Error), and ConnectionTimeouts are caught indiscriminately. The function logs a generic warning and immediately proceeds to the next host without sleeping or respecting rate limits.

- **Location 2**: `data_fetcher.py:130-132` in `_safe_yf_download`:
  ```python
  130:         except Exception as exc:
  131:             logger.error("yfinance download error for %s: %s", ticker, exc)
  132:             return pd.DataFrame()
  ```
  *Impact*: Returns an empty `pd.DataFrame()`. In `scanner.py:76`, `scan_ticker` receives an empty DataFrame and silently skips the ticker (`return None`), obscuring network/API failures as "no market data".

- **Location 3**: `fundamental_filter.py:125-127` in `fetch_fundamentals`:
  ```python
  125:     except Exception:
  126:         logger.exception("Failed to fetch fundamentals for %s.", ticker)
  127:         return None
  ```
  *Impact*: Any failure in quarterly balance sheet / income statement fetching returns `None`, causing `run_fundamental_filter` (`fundamental_filter.py:337`) to return `passed: False` without differentiating missing data from low solvency.

- **Location 4**: `data_fetcher.py:283-289` in `get_crypto_tickers`:
  ```python
  283:         except Exception as exc:
  284:             logger.error("Failed to fetch Binance 24hr tickers: %s — using fallback list.", exc)
  285:             self._crypto_tickers_cache = [
  ...
  289:             ]
  ```
  *Impact*: If top-N ticker fetching fails, it silently switches to fallback tickers without alerting downstream callers.

### 2.4 Silent Mock Data Fallback
- **Location**: `data_fetcher.py:215-217` & `229-231`:
  ```python
  215:         if df.empty:
  216:             logger.warning("Yahoo Finance fallback empty for %s — generating mock data.", symbol)
  217:             return self._generate_mock_ohlcv(180, base_price=50000.0 if "BTC" in symbol else 2000.0)
  ```
  *Impact*: If both Binance and yfinance fail for crypto assets (e.g. during an internet outage or API rate-limit), the system silently generates random-walk prices via `np.random.default_rng(seed=42)` (`data_fetcher.py:306`). The scanner then runs breakout detection on artificial mock prices, potentially triggering false signals.

---

## 3. Evidence Chain: HTTP Session & Header Analysis

### 3.1 `requests.Session` Usage & Discrepancies
- **Yahoo Finance (`DataFetcher`)**:
  - `data_fetcher.py:96-104`: Initialized in `__init__`:
    ```python
    96:         self._yf_session = requests.Session()
    97:         self._yf_session.headers.update({
    98:             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    99:         })
    ```
  - Passed into `yf.download(..., session=self._yf_session)` on line 124.
- **Fundamental Filter Bypass**:
  - `fundamental_filter.py:96`: Call to `yf.Ticker(ticker)` does **NOT** use `DataFetcher` or `self._yf_session`! It invokes `yf.Ticker` directly without custom User-Agent or session headers, creating standalone requests with default `yfinance` headers.
- **Binance Un-sessionized Requests**:
  - `data_fetcher.py:70` inside `_binance_request`:
    ```python
    70:             resp = requests.get(url, params=params, timeout=timeout)
    ```
  - `_binance_request` uses module-level standalone `requests.get()` calls.
  - **Performance Impact**: A full scan cycle scanning 40 crypto tickers for daily and hourly data executes at least 80 individual `requests.get()` calls. Without a persistent `requests.Session()`, each request opens a new TCP socket, performs TLS handshake, and closes the connection.
- **Telegram Un-sessionized Requests**:
  - `telegram_notifier.py:166`:
    ```python
    166:             resp = requests.post(url, json=payload, timeout=10)
    ```
  - Discards session reuse for outbound webhooks.

### 3.2 Header Realism
- Currently, only `User-Agent` is specified for `_yf_session` (`Chrome/124.0.0.0`).
- Missing standard browser headers expected by Cloudflare / Yahoo Finance WAF:
  - `Accept`: `text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8`
  - `Accept-Language`: `en-US,en;q=0.9`
  - `Accept-Encoding`: `gzip, deflate, br`
  - `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform`
- Binance requests send default `python-requests/2.3x.x` User-Agent, exposing automated scanner requests to rate-limit triggers.

---

## 4. Evidence Chain: Rate-Limiting & Retry Behavior

### 4.1 Exponential Backoff Assessment
- **Finding**: **Zero exponential backoff is implemented anywhere in the backend.**
- Neither `urllib3.util.Retry`, `tenacity`, nor manual `time.sleep()` backoff loops exist in `data_fetcher.py`, `fundamental_filter.py`, or `telegram_notifier.py`.

### 4.2 Handling of HTTP Status Codes
- **HTTP 451 (Unavailable For Legal Reasons / Geo-Block)**:
  - Handled in `_binance_request` (`data_fetcher.py:71-75`). Remembers `_working_host` to switch from `api.binance.com` to `data-api.binance.vision`.
- **HTTP 429 (Too Many Requests) & HTTP 418 (IP Ban)**:
  - `_binance_request` does **not** check for 429/418 status codes explicitly.
  - `resp.raise_for_status()` (`data_fetcher.py:76`) raises `HTTPError`.
  - Caught by `except Exception as exc:` on line 81.
  - Logs warning `logger.warning("Binance host %s failed (%s) — trying next host.", host, exc)` and immediately attempts `data-api.binance.vision` without delay.
  - **Risk**: Hitting 429 on host 1 and immediately querying host 2 within milliseconds will trigger rate limits on host 2 or result in a sub-network IP ban.
- **HTTP 5xx (Server Errors)**:
  - Treated identically to 429. Immediately cycles host. If all hosts fail, sets `_working_host = None` (`line 86`) and returns `None`.

### 4.3 Inter-Request Delays
- In `scanner.py:56-140` (`scan_ticker`), tickers in `SP500_TICKERS` (59 assets) and `CRYPTO_WATCHLIST` (40 assets) are scanned in a rapid synchronous `for` loop without any inter-request delay (`time.sleep`).
- 59 US Equity tickers * 2 requests (daily + hourly) = 118 sequential `yfinance` requests issued in rapid succession, frequently triggering Yahoo Finance HTTP 429 rate limiting.

---

## 5. Formulate Specific Refactoring Recommendations for `data_fetcher.py`

To prepare `data_fetcher.py` for Milestone 2 ("Defensive Data Fetcher Refactor"), the following specific structural changes are recommended:

### Recommendation 1: Create Centralized Persistent Network Sessions with Realistic Headers
1. Modify `DataFetcher.__init__` to instantiate persistent `requests.Session` instances for both Yahoo Finance and Binance.
2. Define a standard browser header dictionary:
   ```python
   DEFAULT_HEADERS = {
       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
       "Accept": "application/json, text/plain, */*",
       "Accept-Language": "en-US,en;q=0.9",
       "Cache-Control": "no-cache",
   }
   ```
3. Mount an `HTTPAdapter` with `urllib3.util.Retry` configured for status codes `[429, 500, 502, 503, 504]`, `backoff_factor=1.5`, and `total=3`.

### Recommendation 2: Remove `os.devnull` & Unmute `yfinance` Logging Safely
1. In `data_fetcher.py:_safe_yf_download`: Remove `redirect_stderr(devnull)` and `open(os.devnull, "w")`.
2. In `config.py:196`: Adjust `logging.getLogger("yfinance").setLevel(logging.CRITICAL + 1)` to `logging.getLogger("yfinance").setLevel(logging.ERROR)`.
3. Inspect `df` returned by `yf.download`: Check for empty DataFrames or empty indices, and log explicit error context (e.g. `logger.error("yfinance returned empty data for %s (check rate limits or ticker validity)", ticker)`).

### Recommendation 3: Implement Explicit Rate-Limit Handling & Exponential Backoff for Binance
1. In `_binance_request`: Explicitly check `resp.status_code == 429` or `resp.status_code == 418`.
2. Parse `Retry-After` header if supplied by Binance, or apply exponential sleep (`time.sleep(2 ** attempt + random.uniform(0, 1))`).
3. Maintain persistent `requests.Session` across all Binance endpoints to reuse TCP/TLS connections.

### Recommendation 4: Refactor Fundamental Data Fetching to Share Session Settings
1. Pass `DataFetcher`'s session or header configuration to `fundamental_filter.py:fetch_fundamentals`.
2. Ensure `yf.Ticker(ticker, session=session)` uses the configured session with browser User-Agent.

### Recommendation 5: Make Mock Data Fallback Explicit & Opt-In
1. Add a configuration flag `ALLOW_MOCK_FALLBACK: bool = os.getenv("ALLOW_MOCK_FALLBACK", "false").lower() == "true"` in `config.py`.
2. In `fetch_crypto_daily` / `fetch_crypto_hourly`: Only generate mock data if `ALLOW_MOCK_FALLBACK` is `True`. Otherwise, return empty `pd.DataFrame()` and log a high-priority warning (`logger.error("Data unavailable for %s across Binance and yfinance", symbol)`).

### Recommendation 6: Introduce Micro-Pacing Inter-Request Delays
1. Add `REQUEST_PACE_DELAY_SEC: float = 0.1` in `config.py`.
2. Introduce a micro-sleep (`time.sleep(cfg.REQUEST_PACE_DELAY_SEC)`) between ticker iterations in `scanner.py` to prevent rapid burst traffic against rate-limiting firewalls.

---

## Audit Evidence Summary Table

| Issue Category | File Path | Line Range | Description | Impact |
|---|---|---|---|---|
| Stderr Redirection | `backend/data_fetcher.py` | 126–127 | `redirect_stderr(devnull)` inside `_safe_yf_download` | Hides YF 429 rate limits & errors |
| Logger Muting | `backend/config.py` | 196 | `setLevel(logging.CRITICAL + 1)` on `yfinance` | Completely disables YF logging |
| Un-sessionized HTTP | `backend/data_fetcher.py` | 70 | Module-level `requests.get()` in `_binance_request` | 80+ redundant TCP/TLS handshakes per scan |
| Header Bypassing | `backend/fundamental_filter.py` | 96 | Un-configured `yf.Ticker(ticker)` call | Bypasses User-Agent session headers |
| Zero Backoff | `backend/data_fetcher.py` | 67–85 | Immediate host failover without backoff | Escalates HTTP 429 to IP bans |
| Silent Mocking | `backend/data_fetcher.py` | 215–217, 229–231 | Generates numpy random walk on API failure | Runs scanner on fake prices without warning |
| Missing Delays | `backend/scanner.py` | 71–74 | Synchronous loop across 99 tickers without sleep | Triggers rapid rate limits on YF & Binance |

---
*Report generated by `teamwork_preview_explorer_m1_2`.*
