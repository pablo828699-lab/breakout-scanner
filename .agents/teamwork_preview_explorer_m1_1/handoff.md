# Handoff Report: Backend Signal Detection, Deduplication & Persistence Audit

**Agent Archetype**: `teamwork_preview_explorer`  
**Milestone**: M1_1 Codebase Audit & Baseline Assessment  
**Working Directory**: `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1/`  
**Analysis File**: `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1/analysis.md`

---

## 1. Observation

Direct observations from inspecting source code files in `c:/Users/HP/mi-bot/breakout_scanner/backend/`:

1. **`backend/main.py` (lines 346–350)**:
   ```python
   filepath = os.path.join(os.path.dirname(__file__), "capitulation_signals.json")
   if os.path.exists(filepath):
       os.remove(filepath)
       logger.info("Cleared old capitulation signals file for fresh manual run.")
   ```
   *Observation*: Invoking `/scan-capitulation` deletes `capitulation_signals.json` from the filesystem prior to running `_run_capitulation_scan()`.

2. **`backend/shock_detector.py` (lines 65–70)**:
   ```python
   daily_return = float((close.iloc[-1] / close.iloc[-2]) - 1.0)
   intraday_return = float((low.iloc[-1] / close.iloc[-2]) - 1.0)
   effective_drop = min(daily_return, intraday_return)

   if effective_drop > threshold_pct:
       return None  # No shock
   ```
   *Observation*: `detect_shock()` checks exclusively `iloc[-1]` vs `iloc[-2]`. If effective drop on the single latest candle is > -2.0%, `None` is returned.

3. **`backend/scanner.py` (lines 338–368)**:
   ```python
   for s in new_signals:
       if isinstance(s, RadarSignal):
           signals_dict.append({ ... })
       else:
           signals_dict.append({ ... })
   signals_dict = signals_dict[-50:]
   ```
   *Observation*: `_save_recent_signals()` unconditionally appends items to `signals_dict` without key-based deduplication and slices `[-50:]`.

4. **`backend/recent_signals.json`**:
   Direct inspection revealed `ETHUSDT` duplicated 7 times across sequential scan timestamps (`05:38`, `08:09`, `10:57`, `12:20`, `14:59 UTC`) and `LDOUSDT` duplicated 7 times.

5. **`backend/scanner.py` (lines 351, 365, 468)**:
   ```python
   "timestamp": s.timestamp.strftime("%Y-%m-%d %H:%M UTC")
   ```
   *Observation*: Timestamps are serialized as human strings rather than standard ISO 8601 format (`s.timestamp.isoformat()`).

---

## 2. Logic Chain

1. **Premise**: User reports active capitulation signals and breakout candidates disappearing within 24 hours or when marginal bar closes occur.
2. **Step 1 (File Wiping)**: `main.py` lines 346–350 explicitly deletes `capitulation_signals.json` on HTTP `/scan-capitulation`. When the file is deleted, `_save_capitulation_signals()` starts with an empty list (`existing_by_ticker = {}`), losing all signals previously stored.
3. **Step 2 (Single-Bar Gate Loss)**: `shock_detector.py` lines 65–70 evaluates shock exclusively on `daily_df.iloc[-1]`. If an asset crashes on day 1 (triggering a signal) and stabilizes/bounces slightly on day 2 (drop on day 2 candle = 0.0%), `detect_shock()` returns `None`. Because there is no stateful TTL store, the engine drops the ticker on day 2, causing the active 24-hour setup to be lost.
4. **Step 3 (Unbounded Duplicate Flooding & List Truncation)**: In `scanner.py` lines 338–368, `_save_recent_signals()` appends signals without checking if `(ticker, direction)` already exists. Over 24 hours of scans, 2–3 active tickers generate dozens of duplicate entries. Slicing `signals_dict[-50:]` evicts older valid signals for other tickers.
5. **Step 4 (Timestamp Format Mismatch)**: Formatting as `"%Y-%m-%d %H:%M UTC"` violates the ISO 8601 specification defined in `PROJECT.md` lines 19–20, causing frontend date parsing failures.

---

## 3. Caveats

- **Frontend Impact**: This audit focused exclusively on `backend/`. The frontend (`frontend/src/`) components (`App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`) consume `/api/capitulation` and `/api/candidates`. Frontend timestamp parsing and localStorage interaction should be reviewed in M4.
- **Data Fetcher Rate Limits**: `data_fetcher.py` was inspected for data feeding mechanics, but full defensive error-handling refactoring for yfinance/Binance is scheduled for Milestone 2.

---

## 4. Conclusion

The signal wiping and deduplication loss bugs are caused by:
1. **Destructive file deletion** (`os.remove()`) in `main.py`.
2. **Stateless single-bar shock detection** in `shock_detector.py` and `capitulation_engine.py`.
3. **Blind appending without key-based deduplication** and hard truncation (`[-50:]`) in `scanner.py`.
4. **Non-ISO timestamp serialization** in `scanner.py`.

A clean refactoring plan is documented in `analysis.md` to introduce a stateful TTL-based signal store with 24-hour persistence and ISO 8601 compliance.

---

## 5. Verification Method

To independently verify these findings:

1. **Verify File Removal**: Inspect `backend/main.py` lines 346–350. Notice `os.remove(filepath)` on `capitulation_signals.json`.
2. **Verify Single-Bar Gate**: Inspect `backend/shock_detector.py` lines 65–70. Notice `daily_return = float((close.iloc[-1] / close.iloc[-2]) - 1.0)` evaluates only `iloc[-1]`.
3. **Verify Candidate Duplicates**: Inspect `backend/recent_signals.json`. Count duplicate entries for `ETHUSDT` and `LDOUSDT`.
4. **Verify Timestamp Formatting**: Inspect `backend/scanner.py` lines 351, 365, 468 and check string output vs ISO 8601 spec in `PROJECT.md`.
