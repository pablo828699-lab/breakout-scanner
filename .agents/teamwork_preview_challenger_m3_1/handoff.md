# Milestone 3 Empirical Verification & Stress Test Handoff Report

## 1. Observation

### Test Execution Commands & Results
- **Unit Test Suite**: Executed `python -m unittest discover -s backend`
  - **Result**: `Ran 23 tests in 0.099s` — `OK` (All 23 baseline unit tests pass).
- **Stress Test Harness 1**: Executed `python .agents/teamwork_preview_challenger_m3_1/run_empirical_stress_tests.py`
  - **Result**: `Ran 4 tests in 0.032s` — `OK`.
  - **Verbatim Findings Output**:
    ```
    [EMPIRICAL TEST 1 FINDINGS]
    Scenario A (Not re-flagged this cycle): Signal retained? False (Expected True if last_updated is 10m ago, but actual code purged it!)
    Scenario B (Re-flagged): original first_detected=2026-07-20T18:04:09.408621+00:00, new first_detected=2026-07-21T18:09:09.408621+00:00
    Is first_detected reset/lost? True

    [EMPIRICAL TEST 2 FINDINGS]
    Shock detected effective_drop: -6.50%
    Actual benchmark drop on shock bar (bar -3): -3.0% (Systemic!)
    Classified benchmark_drop_pct reported: 1.51% (from bar -1!)
    Classified is_idiosyncratic: True

    [EMPIRICAL TEST 4 FINDINGS]
    Input: 2 signals for BTCUSDT in single batch. Output item count: 1
    Deduplicated entry_price: 61000.0 (Latest scan wins)
    ```
- **Stress Test Harness 2**: Executed `python .agents/teamwork_preview_challenger_m3_1/run_empirical_stress_tests_2.py`
  - **Result**: `Ran 2 tests in 0.022s` — `OK`.
  - **Verbatim Findings Output**:
    ```
    [EMPIRICAL TEST 5 FINDINGS] Scanner successfully recovers from corrupted JSON on disk.
    [EMPIRICAL TEST 6 FINDINGS] Saved signal count for NVDA:LONG: 1 (Latest signal type: breakout)
    ```

### Specific Code Inspection Observations
1. `backend/scanner.py:371` and `backend/scanner.py:502`:
   ```python
   ts_val = item.get("first_detected") or item.get("timestamp")
   ts_dt = parse_iso_timestamp(ts_val)
   if (now - ts_dt).total_seconds() < ttl_seconds and verdict != "INVALIDATED":
       existing_by_ticker[ticker_key] = item
   ```
2. `backend/shock_detector.py:136-138`:
   ```python
   bench_close = benchmark_df["Close"].astype(float)
   bench_return = float((bench_close.iloc[-1] / bench_close.iloc[-2]) - 1.0)
   is_idiosyncratic = bench_return > benchmark_systemic_pct
   ```

---

## 2. Logic Chain

1. **Observation**: In `backend/scanner.py` (lines 371 & 502), the 24-hour TTL check evaluates `(now - parse_iso_timestamp(first_detected)).total_seconds() < 86400`.
2. **Logic Step**: If an active signal was first detected 24 hours and 5 minutes ago (`first_detected` = T-24h5m), but was updated 10 minutes ago (`last_updated` = T-10m):
   - When loading disk JSON during a scan cycle, `now - first_detected` is 86700 seconds (> 86400s).
   - If the ticker is **not re-flagged** in that cycle, line 502/371 excludes the item from `existing_by_ticker` / `existing_by_key`, causing the active signal to be **immediately purged** from `capitulation_signals.json` / `recent_signals.json`, despite having been updated 10 minutes ago.
   - If the ticker **is re-flagged** in that cycle, because line 502/371 excluded the existing item during disk load, `key in existing_by_key` evaluates to `False`. Line 380/510 sets `first_detected = iso_ts` (current time). The historical `first_detected` timestamp is **wiped and reset** to current time.
3. **Observation**: In `backend/shock_detector.py:39-108`, `detect_shock` checks bars `-1`, `-2`, and `-3` for a drop exceeding `threshold_pct`, identifying `best_bar_idx` (e.g. `i = -3`). In `backend/shock_detector.py:136-138`, `classify_shock` calculates `bench_return = float((bench_close.iloc[-1] / bench_close.iloc[-2]) - 1.0)`.
4. **Logic Step**: `classify_shock` calculates `bench_return` using ONLY the latest candle (`iloc[-1]` vs `iloc[-2]`), regardless of which bar (`best_bar_idx`) caused the shock. If the benchmark crashed -3% on bar `-3` (a market-wide systemic crash), but on bar `-1` the benchmark recovered +1.5%, `classify_shock` evaluates `bench_return = +1.5%` and classifies the bar `-3` shock as `is_idiosyncratic = True`.

---

## 3. Caveats

- **Scope Limit**: Review-only verification role. No fixes were applied to implementation files (`backend/scanner.py` or `backend/shock_detector.py`).
- **Data Fetcher Mocking**: Unit tests and stress tests mock daily/hourly DataFrames to guarantee deterministic boundary testing without relying on external Binance/Yahoo Finance APIs.
- **Render Backend Sync**: External HTTP POST syncing to Render backend was mocked during stress tests to avoid network calls in CODE_ONLY mode.

---

## 4. Conclusion

Milestone 3 signal persistence and shock detection changes significantly improve signal stability and deduplication compared to legacy code. Baseline test coverage is solid (23/23 tests pass). However, empirical stress testing revealed two key logic flaws:

1. **CRITICAL (Signal TTL Expiration & Timestamp Reset)**: Evaluating TTL age using `first_detected` instead of `last_updated` causes active signals > 24h old to be prematurely deleted if a scan cycle does not re-flag them, or resets their `first_detected` timestamp to current time upon re-detection.
2. **MEDIUM (Multi-Bar Shock Benchmark Misalignment)**: `classify_shock` calculates benchmark return exclusively on bar `-1`, misclassifying multi-bar shocks (bars `-2` and `-3`) when the benchmark recovers on subsequent days.

All other features (ISO 8601 formatting, key-based deduplication, non-destructive JSON merges, corrupted JSON recovery) passed empirical verification.

---

## 5. Verification Method

To independently verify these findings:

1. **Run Unit Tests**:
   ```bash
   python -m unittest discover -s backend
   ```
2. **Run Empirical Stress Harness 1**:
   ```bash
   python .agents/teamwork_preview_challenger_m3_1/run_empirical_stress_tests.py
   ```
   - **Expectation**: Confirms `first_detected` reset/purge when age > 24h, and benchmark misalignment on multi-bar shock classification.
3. **Run Empirical Stress Harness 2**:
   ```bash
   python .agents/teamwork_preview_challenger_m3_1/run_empirical_stress_tests_2.py
   ```
   - **Expectation**: Confirms corrupted JSON recovery and key deduplication for Radar/Breakout signals.
