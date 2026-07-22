# Empirical Verification & Stress Test Handoff Report

## 1. Observation

### Test Execution Results
Executed Python test suite command:
`python -m unittest discover -s backend`

Console output snippet:
```
Ran 32 tests in 0.165s

OK
```

All 32 tests (23 baseline tests + 9 adversarial challenger tests) passed cleanly without errors or regressions.

### Codebase Inspections
1. **Timestamp Parsing Helper (`backend/scanner.py`, lines 29–52)**:
   ```python
   def parse_iso_timestamp(ts_val: str | datetime | None) -> datetime:
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
   ```

2. **Candidate Deduplication & Persistence (`backend/scanner.py`, lines 351–433)**:
   - File path: `backend/recent_signals.json`
   - Key format: `f"{ticker}:{direction}" if direction else ticker` (line 368 & line 378).
   - Timestamp updates: `first_detected` is preserved if present in `existing_by_key` (lines 380–384), while `timestamp` and `last_updated` are set to `iso_ts` (ISO 8601 format).
   - Array truncation: entries sorted by `last_updated`/`timestamp` descending and sliced to `[:100]` (lines 420–425).

3. **Capitulation Deduplication & 24h TTL Retention (`backend/scanner.py`, lines 483–556)**:
   - File path: `backend/capitulation_signals.json`
   - Retention condition: `(now - ts_dt).total_seconds() < ttl_seconds and verdict != "INVALIDATED"` (line 502).
   - Preservation: `first_detected` preserved from existing record on disk (lines 510–514).

4. **Non-Destructive Manual Scan Trigger (`backend/main.py`, lines 342–360)**:
   - HTTP endpoint `/scan-capitulation` runs background `CapitulationScanThread` without executing `os.remove("capitulation_signals.json")`.

5. **3-Bar Shock Detection Lookback (`backend/shock_detector.py`, lines 39–100)**:
   - `detect_shock()` iterates over `range(-1, -1 - lookback_bars, -1)` (where `lookback_bars = min(3, len(daily_df) - 21)`).
   - Evaluates `effective_drop = min(daily_return, intraday_return)` across 3 daily candles to prevent day 2 stabilization or intraday price noise from dropping active signals.

6. **Adversarial Test Suite (`backend/tests/test_empirical_challenger_m3.py`)**:
   - `TestMilestone3ISO8601TimestampParsing`: verified parsing for Z-suffix, offset strings, legacy UTC, datetimes, None, empty string, malformed strings, and non-string data types.
   - `TestMilestone3SignalDeduplication`: verified direction-aware keys (`BTCUSDT:LONG` vs `BTCUSDT:SHORT`), `first_detected` preservation vs `last_updated` refresh, and max 100 signal array truncation.
   - `TestMilestone3NonDestructiveMergesAndTTL`: verified 23h 59m retention vs 24h 01m pruning, `INVALIDATED` verdict removal, and resilience when encountering malformed JSON on disk.
   - `TestMilestone3ShockDetectorLookback`: verified intraday spike detection and dataframe length guard (`< 22` rows returns `None`).

## 2. Logic Chain

1. **Timestamp Parsing Verification**:
   - *Observation*: `parse_iso_timestamp` handles ISO 8601 strings with `Z` or `+00:00`, legacy `"%Y-%m-%d %H:%M UTC"` strings, naive/aware `datetime` objects, and returns `datetime.now(timezone.utc)` for invalid/missing values.
   - *Reasoning*: Testing with valid, malformed, non-string, and empty inputs confirmed that the function guarantees a UTC-aware `datetime` instance in all execution paths without crashing or returning naive datetimes.

2. **Signal Deduplication & Preservation Verification**:
   - *Observation*: `_save_recent_signals()` generates keys using `f"{ticker}:{direction}" if direction else ticker`.
   - *Reasoning*: In our empirical test, adding `BTCUSDT LONG` followed by `BTCUSDT SHORT` yielded 2 distinct entries. Adding a second `BTCUSDT LONG` updated `entry_price` and `last_updated` while leaving `first_detected` at the original detection timestamp.

3. **24h TTL Retention & Non-Destructive Merge Verification**:
   - *Observation*: `_save_capitulation_signals()` checks `(now - ts_dt).total_seconds() < 86400 and verdict != "INVALIDATED"`.
   - *Reasoning*: In our boundary test, a signal created 23h 59m ago was retained, while a signal created 24h 01m ago and a signal marked `INVALIDATED` were pruned from disk. When `/scan-capitulation` runs via HTTP, active signals persist across background scans without file deletion.

4. **3-Bar Shock Detection Lookback Verification**:
   - *Observation*: `detect_shock()` scans `min(3, len(daily_df) - 21)` bars and checks both close return and intraday low return.
   - *Reasoning*: In our test scenario where bar -3 experienced a -5.5% drop and bars -2/-1 stabilized (+0.5% and +1.0%), `detect_shock()` correctly identified the shock at bar -3 and returned `capitulation_low = 94.5`.

## 3. Caveats

- **Network Sync Mocking**: Unit tests mock `_sync_to_render_backend()` to prevent external network calls during local test runs. In production, if Render is unreachable or cold-starting, `_sync_to_render_backend()` logs a warning after 3 retries without interrupting local JSON disk persistence.
- **TTL Scope**: 24-hour TTL is calculated relative to `first_detected`. If a signal is continuously active and re-detected beyond 24 hours, its `first_detected` resets to the current scan timestamp once the original 24h window lapses, starting a new 24h cycle.

## 4. Conclusion

Milestone 3 implementations for **Signal Deduplication**, **Non-Destructive JSON Merges**, **24h TTL Signal Retention**, and **ISO 8601 Timestamp Parsing** are **EMPIRICALLY VERIFIED** and fully operational.
- All 32 backend tests pass (100% pass rate).
- Zero NaN or invalid date parsing errors.
- Candidate deduplication, capitulation 24h TTL, and 3-bar shock lookback behave correctly under adversarial stress conditions.

## 5. Verification Method

To independently verify these findings:

1. **Execute Unittest Suite**:
   ```bash
   python -m unittest discover -s backend
   ```
   *Expected Output*: `Ran 32 tests in ~0.17s ... OK`

2. **Inspect Empirical Test File**:
   `backend/tests/test_empirical_challenger_m3.py`

3. **Inspect Implementation Files**:
   - `backend/scanner.py` (lines 29–52, 351–433, 483–556)
   - `backend/shock_detector.py` (lines 39–100)
   - `backend/main.py` (lines 342–360)
