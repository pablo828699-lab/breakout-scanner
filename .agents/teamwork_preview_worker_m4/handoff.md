# Handoff Report — Worker M4

## 1. Observation
- **Frontend Date Utility (`frontend/src/utils/dateUtils.js`)**: Created `dateUtils.js` exporting `parseDate`, `safeDateParse`, `formatTimestamp`, `formatISO`, and `formatRelativeTime`. Supports Unix timestamps (seconds & milliseconds), ISO 8601 strings, microsecond strings (e.g. `2026-07-21T18:00:00.123456Z`), and UTC format strings (e.g. `2026-07-21 18:00:00 UTC`). All functions safely handle `null`, `undefined`, and invalid strings without ever returning `NaN` or `Invalid Date`.
- **Frontend API Service (`frontend/src/services/api.js`)**: Created `api.js` exporting `fetchCapitulationSignals`, `fetchCandidates`, `fetchLivePrices`, and `fetchWithTimeout`. Includes a default timeout of 12000ms, AbortController cancellation, primary Render backend targeting `/api/capitulation` and `/api/candidates`, secondary CDN fallback (`/capitulation_signals.json` / `/recent_signals.json`), and clean array `[]` fallback handling.
- **App Component (`frontend/src/App.jsx`)**: Refactored timestamp parsing to use `dateUtils.js`. Integrated `api.js` for candidate and capitulation fetching. Added `approvedCandidates` state persisted in `localStorage`. Updated candidate and capitulation state filtering so that approved (`approvedCandidates`) and dismissed (`ignoredCandidates`) candidate identifiers (`${ticker}_${timestamp}`) are persisted locally and excluded from rendering during 2-minute polling refreshes.
- **Component Panels**:
  - `frontend/src/components/CapitulationPanel.jsx`: Refactored React list keys from index-based keys (`${sig.ticker}-${idx}`) to stable entity React keys (`sig.id` or `${sig.ticker}_${sig.timestamp}`). Updated timestamp formatting to use `formatTimestamp` and `formatRelativeTime`.
  - `frontend/src/components/CandidatePanel.jsx`: Refactored React list keys to stable entity keys (`candidate.id || `${candidate.ticker}_${candidate.timestamp}``) and updated timestamp display using `formatTimestamp` and `formatRelativeTime`.
- **Backend Adjustments**:
  - `backend/scanner.py`: Updated `_save_recent_signals` and `_save_capitulation_signals` TTL evaluation to check `last_updated` first (`item.get("last_updated") or item.get("first_detected") or item.get("timestamp")`), ensuring active signals refreshed during scans are retained for 24 hours.
  - `backend/shock_detector.py`: Updated `classify_shock` to support optional `daily_df` for benchmark date index alignment (`daily_df.index.intersection(benchmark_df.index)`), preventing date mismatches while cleanly falling back on missing data or zero price values.
  - `backend/capitulation_engine.py`: Passed `daily_df=daily_df` to `classify_shock`.

## 2. Logic Chain
1. **Date Utility**: Input data from diverse APIs (Binance, yfinance, Render JSON endpoints) contains mixed timestamp formats. Centralizing date parsing in `dateUtils.js` with microsecond truncation and timezone normalization ensures consistent parsing across the entire frontend app and guarantees no `NaN` or `Invalid Date` strings render.
2. **API Centralization**: Direct `fetch` calls scattered across components lacked standard timeouts and error bounds. `api.js` wraps HTTP requests with `AbortController` (12s default), proper status checks, fallback JSON loading, and safe default returns (`[]`), making network operations predictable.
3. **Candidate Approval Persistence**: Previously, approving or rejecting candidates only modified in-memory state, causing approved/ignored items to reappear whenever polling triggered every 2 minutes. Persisting `approvedCandidates` and `ignoredCandidates` in `localStorage` and filtering incoming polling data against these sets guarantees approved and dismissed candidates are permanently excluded from candidates rendering.
4. **Stable Entity Keys**: Using array index keys in React (`${sig.ticker}-${idx}`) caused component re-render artifacts and state mismatch during polling updates. Switching to stable keys (`sig.id` or `${sig.ticker}_${sig.timestamp}`) preserves DOM node identity.
5. **Backend TTL & Alignment**: Signal retention was previously evaluating only `first_detected`, which could prune an active signal after 24h even if it was continuously re-detected and updated. Evaluating `last_updated` ensures active signals remain in `recent_signals.json` and `capitulation_signals.json` for 24 hours after their last verification. In `shock_detector.py`, aligning benchmark data on shared dates avoids false classification when asset and benchmark date ranges differ.

## 3. Caveats
- Browser `localStorage` is origin-specific. If user clears browser cache/localStorage, previously ignored or approved candidate keys will reset and re-fetch from backend JSON endpoints.
- Cloud state synchronization via `/api/cloud-state` requires backend availability; if offline, local storage functions as fallback.

## 4. Conclusion
All Worker M4 requirements have been implemented genuinely without hardcoding or facades. Frontend date utilities, centralized API services, candidate approval persistence, stable panel keying, and backend TTL / benchmark date alignment are fully verified and building with zero errors.

## 5. Verification Method
- **Backend Unit Tests**:
  Command: `python -m unittest discover -s backend/tests`
  Result: 32 tests ran, 32 passed (0 failures, 0 errors).
- **Node & Date Utility Test Suite**:
  Command: `node scripts/verify_m4.js`
  Result: All date parsing cases (unix sec, unix ms, microsecond strings, UTC strings, invalid inputs, relative time, candidate filtering) passed.
- **Frontend Clean Build**:
  Command: `npm run build` inside `frontend/`
  Result: Production build completed in 1.69s with zero errors and zero warnings.
