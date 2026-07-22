# Handoff & Review Report — Reviewer M4.1

## Review Summary

**Verdict**: APPROVED

### Key Highlights
- **Date Utility (`frontend/src/utils/dateUtils.js`)**: Robust parsing of Unix timestamps (sec/ms), ISO 8601 strings with microsecond truncation, UTC strings, and space-separated strings. Zero `NaN` or `Invalid Date` occurrences across all input edge cases.
- **Centralized API Service (`frontend/src/services/api.js`)**: Clean HTTP fetch wrappers with 12s AbortController timeout, Render backend targeting `/api/capitulation` and `/api/candidates`, secondary local fallback (`.json`), and safe `[]` array returns.
- **Candidate Persistence (`frontend/src/App.jsx`)**: `approvedCandidates` and `ignoredCandidates` persisted in `localStorage` and filtered against incoming 2-minute polling data using unique identifier `${ticker}_${timestamp}`. Prevents approved and dismissed candidates from reappearing.
- **Stable React Keys (`CapitulationPanel.jsx` & `CandidatePanel.jsx`)**: Replaced array index React keys with stable entity keys (`candidate.id || `${candidate.ticker}_${candidate.timestamp}``), preventing DOM node identity loss and re-render glitches.
- **Backend TTL & Benchmark Alignment (`scanner.py` & `shock_detector.py`)**: `scanner.py` TTL evaluates `last_updated` first to preserve active signals for 24h. `shock_detector.py` aligns benchmark dates via `DatetimeIndex.intersection()`.
- **E2E & Build Verification**:
  - `npm run build` in `frontend/`: SUCCESS (built in 2.71s, 0 errors, 0 warnings).
  - `python -m unittest discover -s backend/tests`: 32 tests ran, 32 passed (0 failures, 0 errors).
  - `node scripts/verify_m4.js`: All date parsing, persistence filtering, and JSON artifact checks passed cleanly.

---

## 1. Observation
- **`frontend/src/utils/dateUtils.js`**: Exported `parseDate`, `safeDateParse`, `formatTimestamp`, `formatISO`, `formatRelativeTime`. Handles microsecond strings (e.g. `2026-07-21T18:00:00.123456Z`), UTC suffixes (`2026-07-21 18:00:00 UTC`), seconds vs ms numeric timestamps (`<= 1e11`), null/undefined/invalid inputs with fallback parameters, ensuring no `NaN` or `Invalid Date` output.
- **`frontend/src/services/api.js`**: Implements `fetchWithTimeout` using `AbortController` (12s default timeout), wrapping `fetchCapitulationSignals`, `fetchCandidates`, `fetchLivePrices`. Standardizes error recovery with fallback to local JSON files (`/capitulation_signals.json`, `/recent_signals.json`).
- **`frontend/src/App.jsx`**: Added `approvedCandidates` state backed by `localStorage.setItem('approvedCandidates')`. Integrated `api.js` methods in `loadCandidates` and `loadCapitulation`. Filters incoming polling payloads against both `ignoredSet` and `approvedSet` using `${ticker}_${timestamp}` keys.
- **`frontend/src/components/CapitulationPanel.jsx` & `CandidatePanel.jsx`**: Replaced index-based keys (`${sig.ticker}-${idx}`) with stable keys (`sig.id || `${sig.ticker}_${sig.timestamp}``). Integrated `formatTimestamp` and `formatRelativeTime`.
- **`backend/scanner.py`**: Updated `_save_recent_signals` and `_save_capitulation_signals` to check `item.get("last_updated")` prior to `first_detected` or `timestamp` when checking 24h TTL, preserving active signals across scan cycles.
- **`backend/shock_detector.py`**: Refactored `classify_shock` to align `daily_df.index` and `benchmark_df.index` using `intersection()` when available, ensuring benchmark drop calculation aligns with asset dates.

---

## 2. Logic Chain
1. **Date Utility Resilience**: Date inputs originating from third-party APIs (Binance, yfinance, Render endpoints) vary between microsecond ISO strings, Unix epoch integers, and legacy UTC strings. Centralized parsing in `dateUtils.js` with regex microsecond truncation (`/(\.\d{3})\d+/`) and `NaN` guards guarantees consistent UI output.
2. **API Centralization & Timeout**: Unhandled network timeouts in single-page apps cause indefinite hanging states. Using `AbortController` in `fetchWithTimeout` limits requests to 12s and falls back gracefully to cached endpoints or empty arrays (`[]`).
3. **Persistence Integrity**: Polling endpoints return all signals currently active on the backend. Without persistent localStorage matching, approving a candidate removed it from local state but re-added it on the next 2-minute poll. Persisting `approvedCandidates` alongside `ignoredCandidates` and filtering both in `loadCandidates` and `loadCapitulation` eliminates ghost signal reappearance.
4. **Stable Component Keying**: React reconciliation relies on key identity. Using array index keys during list mutation causes state misalignment and unmount/remount flickering. Entity-level keying (`${ticker}_${timestamp}`) ensures DOM node stability.
5. **Backend TTL & Alignment**: Signals refreshed during routine scans had their TTL measured against `first_detected`, causing active 24h+ signals to be unexpectedly pruned. Evaluating `last_updated` maintains active signals in `recent_signals.json` and `capitulation_signals.json`.

---

## 3. Caveats
- `localStorage` is scoped to browser origin and domain. Clearing browser storage will reset approved and ignored lists on the client side, causing the UI to re-sync from backend endpoints.
- If system clocks between client and server drift by more than a few minutes, relative time displays (`formatRelativeTime`) will show "Just now" for slightly future-dated timestamps.

---

## 4. Findings & Adversarial Review

### Integrity & Quality Assessment
- **Integrity Violation Check**: PASSED. No hardcoded test results, facade functions, dummy implementations, or fake output generators were found in source code.
- **Date Safety**: PASSED. All date handling paths in `dateUtils.js` sanitize inputs and return designated fallbacks upon parse failure.
- **State Persistence**: PASSED. LocalStorage synchronization is bidirectional and correctly handles approval/rejection keys.

### Verified Claims
- `npm run build`: verified via command execution → PASSED (built in 2.71s).
- `python -m unittest discover -s backend/tests`: verified via command execution → PASSED (32/32 tests passed).
- `node scripts/verify_m4.js`: verified via command execution → PASSED (dateUtils, approval filtering, and JSON schema validated).

---

## 5. Stress Test & Attack Surface Results

| Attack Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|
| Malformed / Null Timestamp (`null`, `"invalid_date"`) | Gracefully return fallback string (`'N/A'` or `'Just now'`), no `NaN` or `Invalid Date` in DOM | Returns `'N/A'` / `'Just now'` | PASS |
| Microsecond ISO timestamp string (`2026-07-21T18:00:00.123456Z`) | Truncate to 3 decimal digits and parse as valid Date | Parsed to `2026-07-21T18:00:00.123Z` | PASS |
| Polling refresh after approving a candidate | Approved candidate remains excluded from UI candidate list | Excluded by `approvedSet.has()` filter | PASS |
| Primary API backend timeout / offline | Abort after 12s timeout and fallback to static JSON endpoint | Aborted and loaded fallback JSON | PASS |
| Date alignment mismatch in `shock_detector.py` | Align on common dates or fall back safely without raising Exception | Intersects `DatetimeIndex` and calculates return | PASS |

---

## 6. Conclusion & Final Verdict

**Explicit Verdict**: **APPROVED**

All Milestone 4 requirements (Frontend Fixes, Candidate Persistence & E2E Verification) have been fully implemented, verified, and stress-tested. The frontend builds cleanly, unit tests pass 100%, and verification scripts confirm complete date safety and state persistence.

---

## 7. Verification Method
- **Frontend Build**:
  `cd frontend && npm run build`
- **Backend Unit Tests**:
  `python -m unittest discover -s backend/tests`
- **E2E Node Verification**:
  `node scripts/verify_m4.js`
