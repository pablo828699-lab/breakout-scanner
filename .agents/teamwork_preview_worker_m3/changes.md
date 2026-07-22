# Modified Files and Design Changes

## Summary of Changes

### 1. `backend/main.py`
- **Change**: Removed destructive file removal block in `/scan-capitulation` HTTP handler (former lines 346–350 which executed `os.remove("capitulation_signals.json")`).
- **Rationale**: Manual capitulation scan triggers must merge and update signal state atomically instead of wiping existing active signals.

### 2. `backend/shock_detector.py`
- **Change**: Refactored `detect_shock(daily_df, threshold_pct)` to evaluate shock qualification across recent daily candles (up to 3 completed/forming bars).
- **Rationale**: Prevents day 2 stabilization or marginal bar price fluctuations (e.g., price bouncing from -3.5% to -1.8%) from immediately dropping active capitulation signals during scan cycles.

### 3. `backend/scanner.py`
- **Change**:
  - Added `parse_iso_timestamp()` helper to robustly parse ISO 8601 strings, legacy UTC strings, and datetime objects.
  - Refactored `_save_recent_signals()` to perform key-based deduplication by `(ticker, direction)` or `ticker`, preserving `first_detected`, updating `last_updated`, and storing ISO 8601 strings.
  - Refactored `_save_capitulation_signals()` to enforce 24-hour TTL (86400s) retention, preserve `first_detected` on re-detected signals, purge expired/invalidated entries, and retain up to 100 active unique signals without arbitrary `[-30:]` truncation.
  - Replaced all non-standard `"%Y-%m-%d %H:%M UTC"` strftime formatting with strict ISO 8601 (`s.timestamp.isoformat()`).

### 4. `backend/tests/test_signal_persistence.py`
- **Change**: Created a comprehensive unittest suite covering ISO timestamp parsing, 3-bar shock detection lookback, 24h TTL signal retention & merge, and candidate key deduplication.
