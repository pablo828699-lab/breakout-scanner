# Comprehensive Audit Report: Backend Signal Detection, Deduplication & Persistence

**Scope**: `c:/Users/HP/mi-bot/breakout_scanner/backend/`  
**Focus Files**: `scanner.py`, `capitulation_engine.py`, `shock_detector.py`, `main.py`, `models.py`, `config.py`, and JSON state files (`capitulation_signals.json`, `recent_signals.json`, `last_alerts.json`).

---

## 1. Executive Summary

An in-depth, read-only architectural audit of the Breakout Scanner backend reveals **four critical failure mechanisms** responsible for active signal wiping, premature purging within 24 hours, and signal loss during signal deduplication and HTTP scanning triggers:

1. **Destructive File Purging on Manual Triggers**: `main.py` explicitly executes `os.remove()` on `capitulation_signals.json` whenever the `/scan-capitulation` HTTP endpoint is invoked, destroying all historical active signals before a new scan runs.
2. **Stateless Single-Bar Detection Gate (Shock Memory Loss)**: `shock_detector.py` evaluates price drop percentage exclusively on the single latest daily candle (`daily_df.iloc[-1]`). Once a crash candle closes or an intraday bounce occurs (e.g. drop recovers from -2.2% to -1.8%), the gate returns `None`. Without stateful TTL memory, active capitulation opportunities are immediately dropped on the subsequent scan cycle instead of remaining active for 24+ hours.
3. **Flawed Deduplication and Blind Truncation**:
   - `_save_recent_signals()` in `scanner.py` blindly appends duplicate signals for the same ticker+direction every cycle without deduplication keying, causing list length to explode and truncating older valid signals (`[-50:]`).
   - `_save_capitulation_signals()` uses `ticker` as a dictionary key, but because the file is deleted on manual triggers or overwritten with empty scan lists, valid active signals fail to persist across cycles.
4. **Timestamp & ISO Standard Inconsistencies**: Timestamps are formatted as non-standard human strings (`"%Y-%m-%d %H:%M UTC"`) in JSON signal outputs, violating ISO 8601 formatting expected by `PROJECT.md` and frontend JavaScript parsers.

---

## 2. Detailed Findings & Evidence Chains

### Finding 1: Destructive File Purging in Endpoint Handlers
* **File**: `c:/Users/HP/mi-bot/breakout_scanner/backend/main.py`
* **Line Range**: 342–353
* **Observation**:
  ```python
  342: elif clean_path == "/scan-capitulation":
  343:     try:
  344:         logger.info("Manual capitulation scan triggered via HTTP.")
  345:         # Clean up existing signals file to force overwrite of everything
  346:         try:
  347:             filepath = os.path.join(os.path.dirname(__file__), "capitulation_signals.json")
  348:             if os.path.exists(filepath):
  349:                 os.remove(filepath)
  350:                 logger.info("Cleared old capitulation signals file for fresh manual run.")
  351:         except Exception:
  352:             pass
  ```
* **Logic Chain**:
  1. Whenever a user or scheduled job accesses `/scan-capitulation`, line 349 deletes `capitulation_signals.json` from disk.
  2. The background thread `CapitulationScanThread` is spawned to execute `_run_capitulation_scan()`.
  3. Inside `scanner.py` lines 431–436, `_save_capitulation_signals()` checks `if os.path.exists(filepath)`. Because the file was removed at line 349, `os.path.exists` returns `False`, resetting `existing_by_ticker` to `{}`.
  4. Only tickers that pass the shock detection gate on that *exact* instant of the scan cycle are written to the newly created file.
  5. Any asset whose signal was generated 1–23 hours prior (and whose price has since stabilized or bounced) is permanently deleted.
* **Conclusion**: Active capitulation signals are forcibly wiped on every manual scan trigger.

---

### Finding 2: Single-Bar Stateless Gate in Shock Detector
* **File**: `c:/Users/HP/mi-bot/breakout_scanner/backend/shock_detector.py` & `c:/Users/HP/mi-bot/breakout_scanner/backend/capitulation_engine.py`
* **Line Range**: `shock_detector.py` lines 65–70; `capitulation_engine.py` lines 76–80
* **Observation**:
  ```python
  # shock_detector.py
  65: daily_return = float((close.iloc[-1] / close.iloc[-2]) - 1.0)
  66: intraday_return = float((low.iloc[-1] / close.iloc[-2]) - 1.0)
  67: effective_drop = min(daily_return, intraday_return)
  68: 
  69: if effective_drop > threshold_pct:
  70:     return None  # No shock
  ```
  ```python
  # capitulation_engine.py
  76: shock = scan_for_shocks(daily_df, ticker, shock_threshold)
  77: if shock is None:
  78:     logger.info("%s — no shock detected (drop < %.0f%%). Skipping.", ticker, abs(shock_threshold) * 100)
  79:     return None
  ```
* **Logic Chain**:
  1. `detect_shock()` computes returns exclusively comparing the single latest row (`iloc[-1]`) against `iloc[-2]`.
  2. It does not inspect recent daily candles (`iloc[-2]`, `iloc[-3]`) or check an active state store.
  3. When a daily candle closes and a new daily candle opens (or if intraday low moves slightly up from -2.1% to -1.9%), `effective_drop > -0.02` becomes `True`.
  4. `scan_for_shocks()` returns `None`.
  5. `analyze_capitulation()` logs `Skipping.` and returns `None`.
  6. `run_capitulation_scan()` omits the ticker from its return list (`signals`).
  7. On the next save cycle, the active signal is lost or excluded.
* **Conclusion**: Signal detection lacks multi-bar lookback and stateful memory, treating ongoing 24-hour capitulation setups as invalid as soon as the active bar close changes slightly.

---

### Finding 3: Flawed Signal Deduplication & Unbounded List Purging
* **File**: `c:/Users/HP/mi-bot/breakout_scanner/backend/scanner.py`
* **Line Range**: 325–376 (`_save_recent_signals`) & 426–478 (`_save_capitulation_signals`)
* **Observation (`_save_recent_signals`)**:
  ```python
  338: for s in new_signals:
  339:     if isinstance(s, RadarSignal):
  340:         signals_dict.append({ ... })
  ...
  368: signals_dict = signals_dict[-50:]
  ```
  Inspection of `backend/recent_signals.json` revealed:
  - `ETHUSDT` duplicated 7 times across sequential timestamps (`05:38`, `08:09`, `10:57`, `12:20`, `14:59 UTC`).
  - `LDOUSDT` duplicated 7 times across sequential timestamps.
* **Logic Chain**:
  1. `_save_recent_signals` loads `recent_signals.json` into `signals_dict`.
  2. It iterates through `new_signals` and unconditionally calls `signals_dict.append()`.
  3. No deduplication key (e.g. `ticker + direction`) is applied.
  4. With frequent scan cycles (every 15–60 mins), duplicate entries for active trending assets flood `signals_dict`.
  5. Line 368 truncates `signals_dict` to the last 50 items (`signals_dict[-50:]`).
  6. Duplicate entries for 2–3 volatile tickers fill up the array, pushing out and deleting valid signals for other tickers detected within the last 24 hours.
* **Observation (`_save_capitulation_signals`)**:
  ```python
  439: existing_by_ticker = {}
  440: for item in signals_dict:
  441:     ticker_key = item.get("ticker")
  442:     if ticker_key:
  443:         existing_by_ticker[ticker_key] = item
  ...
  470: signals_dict = list(existing_by_ticker.values())[-30:]  # Keep last 30
  ```
* **Logic Chain**:
  1. Keying by `ticker` prevents duplicate entries for the same asset in capitulation signals.
  2. However, line 470 arbitrarily truncates the list to 30 items (`[-30:]`) without considering signal age or TTL.
  3. When new signals are appended, the 31st ticker is evicted regardless of whether its detection timestamp was 10 minutes ago or 20 hours ago.

---

### Finding 4: Timestamp Formatting Inconsistency
* **File**: `c:/Users/HP/mi-bot/breakout_scanner/backend/scanner.py`
* **Line Range**: 351, 365, 468
* **Observation**:
  `"timestamp": s.timestamp.strftime("%Y-%m-%d %H:%M UTC")`
* **Logic Chain**:
  1. `PROJECT.md` (lines 19–20) defines API contracts requiring ISO 8601 timestamps:
     - `GET /api/capitulation`: Returns active capitulation signal items containing valid ISO timestamps.
     - `GET /api/candidates`: Returns candidate breakout items containing valid ISO timestamps.
  2. String format `"2026-07-20 15:12 UTC"` lacks the standard ISO `T` separator and timezone offset format (`Z` or `+00:00`).
  3. Standard JavaScript `Date.parse()` on the frontend can evaluate custom string formats as `NaN` or `Invalid Date`.

---

## 3. Signal Lifecycle & Persistence Comparison

| Component | Current Implementation | Target Refactored Design |
|---|---|---|
| **Shock Gate** | Single bar (`daily_df.iloc[-1]`) check | 3-day / 72-hour rolling window + stateful active signal check |
| **Capitulation Storage** | File removed on `/scan-capitulation` | Immutable file store, atomic update with 24h TTL merge |
| **Candidate Storage** | Blind list append + `[-50:]` truncation | Keyed by `(ticker, direction)`, 24h TTL pruning |
| **Signal Expiration** | Arbitrary index slicing (`[-30:]`, `[-50:]`) | Explicit `expires_at` (ISO timestamp) + active state tracking |
| **Timestamp Standard** | `"%Y-%m-%d %H:%M UTC"` | Standard ISO 8601 (`s.timestamp.isoformat()`) |

---

## 4. Refactoring Recommendations

### Recommendation 1: State-Aware `shock_detector.py` & `capitulation_engine.py`
1. Modify `detect_shock()` in `shock_detector.py` to evaluate the last 3 daily candles (`daily_df.iloc[-3:]`) for shock qualification.
2. In `capitulation_engine.py`, before discarding a ticker whose latest bar drop is < 2%, check if an active unexpired signal exists in `capitulation_signals.json`.
3. If an active signal exists (< 24h old) and current price has not breached `stop_loss` or `take_profit`, preserve the signal as `"ACTIVE"`.

### Recommendation 2: Non-Destructive Storage Engine in `scanner.py` & `main.py`
1. In `main.py` line 349: **Remove `os.remove(filepath)`**.
2. In `scanner.py`, refactor `_save_capitulation_signals` and `_save_recent_signals` to perform **Stateful TTL-based Merging**:
   - Assign `expires_at = timestamp + timedelta(hours=24)`.
   - Prune entries only when `current_time > expires_at` or `status == "INVALIDATED"`.
   - Key candidates by `(ticker, direction)` to prevent duplicate listings of the same asset.

### Recommendation 3: Standardize Timestamps to ISO 8601
1. Update `_save_recent_signals` and `_save_capitulation_signals` to serialize timestamps using `s.timestamp.isoformat()`.
2. Ensure full compatibility with `PROJECT.md` API specification.
