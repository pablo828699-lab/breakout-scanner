## 2026-07-21T17:58:44Z
Identity & Archetype: teamwork_preview_worker
Working Directory: c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m2
Scope File: c:/Users/HP/mi-bot/breakout_scanner/PROJECT.md
Audit Reports to read:
- c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_2/handoff.md
- c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_2/analysis.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Task:
Refactor `backend/data_fetcher.py`, `backend/config.py`, and `backend/fundamental_filter.py` to make data fetching defensive, robust against rate-limiting, and transparently logged.

Specific Requirements:
1. **Persistent HTTP Session & Headers (`data_fetcher.py`)**:
   - Create a singleton or reusable `requests.Session()` with realistic browser User-Agent headers (e.g. `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36`).
   - Re-use this session for all Binance API requests (`_binance_request`) instead of calling raw un-sessionized `requests.get`.
   - Update `yf.download` / `yf.Ticker` calls to use the configured session/headers.

2. **Remove Error Muting (`data_fetcher.py`, `config.py`)**:
   - Remove `with redirect_stderr(devnull):` in `_safe_yf_download` (`data_fetcher.py`).
   - Remove `logging.getLogger("yfinance").setLevel(logging.CRITICAL + 1)` in `config.py`.
   - Ensure exceptions and HTTP rate-limit errors (429) are logged with full detail (`logger.warning` / `logger.error`).

3. **Exponential Backoff & Micro-Pacing (`data_fetcher.py`)**:
   - Implement exponential backoff retries (e.g. 3 retries with 1s, 2s, 4s delay + jitter) on HTTP 429 / 5xx / connection errors for both Binance and Yahoo Finance requests.
   - Add micro-pacing delays between ticker downloads in sequential scans to prevent burst rate limits.

4. **Fix `fundamental_filter.py` Session Leak**:
   - Pass the `DataFetcher` session/headers or a shared session to `yf.Ticker(ticker)` calls in `fundamental_filter.py:96`.

5. **Eliminate Silent Mock Fallback**:
   - Replace automatic fallback to random-walk mock prices (`_generate_mock_ohlcv`) on empty DataFrame with structured warning logs and returning empty/None gracefully. Real live scans must NEVER evaluate breakout logic on fake mock prices silently.

6. **Verification Script**:
   - Create a test script `backend/tests/test_data_fetcher.py` that tests `DataFetcher` methods, verifies retry logic and error logging. Run python test execution to confirm passing results.

Output Requirements:
- Document all modified files in `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m2/changes.md`.
- Document build and test outputs in `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m2/handoff.md`.
- Send message to orchestrator (d5b60c2c-cae3-4fcf-9beb-fdfe51e3634d) when done.
