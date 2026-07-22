# Handoff Report — Empirical Verification & Adversarial Review (Milestone 2)

**Agent**: `teamwork_preview_challenger_m2_1`  
**Role**: Empirical Challenger (critic, specialist)  
**Target Files**: `backend/data_fetcher.py`, `backend/tests/test_data_fetcher.py`, `backend/fundamental_filter.py`, `backend/config.py`  
**Date**: 2026-07-21  

---

## 1. Observation

Direct empirical observations obtained via test execution and live API calls:

1. **Unit Test Suite Execution**:
   - Command: `python -m unittest backend/tests/test_data_fetcher.py`
   - Result: 11 tests executed in 0.018s — **11 PASSED / 0 FAILED**.
   - Output snippet:
     ```text
     Ran 11 tests in 0.018s
     OK
     ```

2. **Empirical Stress Harness Execution**:
   - Command: `python .agents/teamwork_preview_challenger_m2_1/test_harness.py`
   - Result: 10 stress tests executed in 0.143s — **10 PASSED / 0 FAILED**.
   - Verified behaviors:
     - HTTP 429 exponential backoff: Delay 1 was ~1.42s, Delay 2 was ~2.17s for `base_delay=1.0`.
     - HTTP 451 geo-blocked failover: Instant switch from `https://api.binance.com` to `https://data-api.binance.vision` with **0 sleep retries**.
     - Host failover persistence: `_working_host` cached across calls, reducing scan overhead.
     - Mock price fallback elimination: `fetch_crypto_daily` and `fetch_crypto_hourly` return empty `pd.DataFrame()` without throwing unhandled exceptions or generating fake random-walk OHLCV prices.
     - `yfinance` MultiIndex handling: `df.columns.droplevel(1)` flattens `('Close', 'AAPL')` to `'Close'`.
     - Micro-pacing: `time.sleep(0.15)` correctly invoked in `_binance_klines` when `REQUEST_PACE_DELAY_SEC > 0`.
     - Session singleton: `get_shared_session()` maintains Chrome 126 `User-Agent` headers across requests.

3. **Live API Integration Verification**:
   - Crypto Binance REST API: `fetcher.fetch_crypto_daily('BTCUSDT')` returned shape `(300, 5)` with valid OHLCV prices (Close ~ $66,180.91).
   - US Equities yfinance API: `fetcher.fetch_sp500_daily('AAPL')` returned shape `(300, 5)` with valid OHLCV prices (Close ~ $327.52).
   - Fundamentals Filter: `fetch_fundamentals('AAPL')` returned dict containing `ebit`, `current_assets`, `current_liabilities`, `inventory`.

4. **Edge Cases & Failure Modes Uncovered**:
   - **Client Error Retry Overhead (HTTP 400 / 404 / 403)**:
     - Location: `backend/data_fetcher.py`: lines 106–129 in `_binance_request`.
     - Observation: `resp.status_code` for 400 (Bad Request) or 404 (Not Found) falls through line 106 check (which only targets 429, 418, >=500). `resp.raise_for_status()` raises `requests.exceptions.HTTPError`.
     - Result: Caught by `except requests.exceptions.RequestException`, causing `_binance_request` to attempt 3 retries on host 1 (sleeping with exponential backoff) and then 3 retries on host 2 (sleeping with exponential backoff) — total 6 requests and ~3-5 seconds latency per invalid symbol.
   - **Geo-blocked Host Re-probing on Transient Failures**:
     - Location: `backend/data_fetcher.py`: line 149 in `_binance_request`.
     - Observation: If host 1 returns HTTP 451 (geo-blocked) and `_working_host` is set to host 2 (`data-api.binance.vision`), but host 2 experiences a single transient failure (e.g. timeout or 500), line 149 executes `_working_host = None`.
     - Result: On the very next symbol request, `_binance_request` re-probes host 1 (`api.binance.com`), logging warning `Binance host ... geo-blocked (451)` again and incurring unnecessary failover latency.

---

## 2. Logic Chain

1. **Verification of Worker Claims**:
   - The worker (`teamwork_preview_worker_m2`) claimed in `changes.md` that persistent sessions, exponential backoff, immediate 451 host failover, yfinance un-muting, micro-pacing, and mock price elimination were implemented.
   - We verified each claim empirically using both mock assertion tests and live network requests.
   - All 11 unit tests and 10 custom stress tests passed without error.

2. **Analysis of Robustness & Failure Modes**:
   - While the implementation correctly addresses 429/418/5xx errors and 451 geo-blocking, catching generic `RequestException` for status errors means client-side errors (HTTP 400 Bad Request, HTTP 404 Not Found) are treated as temporary network failures.
   - Because client-side errors will never resolve on retry, retrying 3 times per host wastes compute and increases scan time.
   - Similarly, resetting `_working_host = None` on any total failure wipes the learned knowledge that host 1 is geo-blocked.

---

## 3. Caveats

- Live API calls depend on external network availability and remote API status.
- Yahoo Finance rate limits are enforced dynamically by Yahoo servers; while `REQUEST_PACE_DELAY_SEC` micro-pacing mitigates rate limits, high-frequency continuous scans may still hit yfinance rate limits.

---

## 4. Conclusion

- **Overall Status**: **APPROVED WITH MINOR OBSERVATIONS** (Risk Level: **LOW**).
- **Core Requirements**: Met. The refactored `backend/data_fetcher.py` successfully hardened rate limiting, eliminated dangerous silent mock price generation, added persistent session headers, and implemented immediate 451 host failover.
- **Recommended Non-Blocking Improvements**:
  1. In `_binance_request`, exclude client status errors (400, 403, 404) from retry loops.
  2. Maintain a set of geo-blocked/unreachable hosts instead of clearing `_working_host` on transient failures.

---

## 5. Verification Method

To independently verify these results:

1. **Run Unit Test Suite**:
   ```bash
   python -m unittest backend/tests/test_data_fetcher.py
   ```
2. **Run Empirical Stress Harness**:
   ```bash
   python .agents/teamwork_preview_challenger_m2_1/test_harness.py
   ```
3. **Run Live Fetch Test**:
   ```bash
   python -c "from backend.data_fetcher import DataFetcher; fetcher = DataFetcher(); print('Crypto:', fetcher.fetch_crypto_daily('BTCUSDT').shape); print('Equities:', fetcher.fetch_sp500_daily('AAPL').shape)"
   ```
