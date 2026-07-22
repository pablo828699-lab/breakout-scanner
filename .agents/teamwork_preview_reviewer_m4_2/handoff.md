# Review Handoff Report — Reviewer M4.2

## 1. Observation
- **Frontend API Service (`frontend/src/services/api.js`)**:
  - `fetchWithTimeout` (lines 18–31) instantiates `AbortController` and a `setTimeout` timer set to `DEFAULT_TIMEOUT_MS` (12000ms), properly aborting pending fetch requests on timeout and clearing timers in `finally`.
  - `fetchCapitulationSignals` (lines 40–70) and `fetchCandidates` (lines 79–109) target primary endpoints (`/api/capitulation`, `/api/candidates`), validate `resp.ok` and `Array.isArray(data)`, fall back gracefully to static local JSON files (`/capitulation_signals.json`, `/recent_signals.json`), and return empty arrays `[]` on complete failure.
- **Frontend Date Utilities (`frontend/src/utils/dateUtils.js`)**:
  - `parseDate` (lines 18–67) handles Unix timestamps in seconds (<= 1e11) and ms (> 1e11), microsecond sub-second strings (truncating digits to 3, line 48), space-separated UTC strings, and missing timezone offsets (appending 'Z').
  - `formatTimestamp`, `formatISO`, `formatRelativeTime`, and `safeDateParse` (lines 76–162) wrap all formatting in try-catch guards, guaranteeing string outputs never contain `"NaN"` or `"Invalid Date"`.
- **React Key Stability (`CapitulationPanel.jsx` & `CandidatePanel.jsx`)**:
  - `CapitulationPanel.jsx` (line 482): `const key = sig?.id || (sig?.ticker && sig?.timestamp ? `${sig.ticker}_${sig.timestamp}` : `cap_${sig?.ticker || idx}`);`
  - `CandidatePanel.jsx` (line 43): `key={candidate.id || `${candidate.ticker}_${candidate.timestamp}`}`
  - Both panels use stable entity identifier keys instead of array indices.
- **State Management & Rehydration (`frontend/src/App.jsx`)**:
  - `approvedCandidates` (lines 135–138) and `ignoredCandidates` (lines 130–133) rehydrate state from `localStorage` on initial mount.
  - Candidate and capitulation polling (lines 262–331, 359–410) constructs `approvedSet` and `ignoredSet` from `localStorage` and filters incoming signals using `${ticker}_${timestamp}` composite keys, ensuring approved and dismissed candidates remain excluded during background polling refreshes.
  - State changes to `approvedCandidates` and `ignoredCandidates` automatically sync back to `localStorage` (lines 222–228).
- **Backend Scanner TTL Logic (`backend/scanner.py`)**:
  - `_save_recent_signals` (lines 369–371) and `_save_capitulation_signals` (lines 499–502) check `last_updated` first (`ts_val = item.get("last_updated") or item.get("first_detected") or item.get("timestamp")`).
  - Active signals refreshed during scans update `last_updated` to current time while preserving `first_detected`, extending retention in `recent_signals.json` and `capitulation_signals.json` for 24 hours.

## 2. Logic Chain
1. **Error Resilience & Fallbacks**: Wrapping HTTP calls in `fetchWithTimeout` with `AbortController` prevents hanging network connections if the backend host is sleeping or slow. Returning `[]` or fallback JSON arrays on error ensures components render predictable structures without runtime crashes.
2. **Date Parsing Integrity**: Input dates from external services (Binance API, yfinance, Render endpoints) come in varied representations. Normalizing microsecond precision (`.123456Z` -> `.123Z`), space-separated UTC strings, and numeric timestamps in `dateUtils.js` eliminates invalid date artifacts across the UI.
3. **DOM & State Stability**: Using composite keys (`${ticker}_${timestamp}`) ensures React reconciles list DOM elements cleanly during 2-minute polling re-fetches without DOM node replacement or state flickering.
4. **Approval Persistence**: Storing approved/rejected composite keys in `localStorage` and applying set filtering inside polling loaders guarantees user actions (approvals and ignoration) persist across page reloads and periodic background data refreshes.
5. **Integrity & Code Quality Verification**:
   - Zero hardcoded test outputs or facade implementations were detected in `api.js`, `dateUtils.js`, `App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`, or `scanner.py`.
   - All logic implements real, functional operations matching the project specifications.

## 3. Caveats
- Browser `localStorage` is isolated to the origin/domain. Clearing browser storage will reset locally stored approval and ignored candidate sets, allowing previously dismissed signals to re-appear unless synchronized with cloud backend storage (`/api/cloud-state`).

## 4. Conclusion
**Verdict**: **APPROVED**

Worker M4 has successfully delivered all requested frontend fixes, candidate persistence, stable keying, API resilience, and backend TTL retention logic. All code is clean, robust, thoroughly tested, and completely free of integrity violations or hardcoded shortcuts.

## 5. Verification Method
The work product was independently verified using the following execution commands:

1. **Backend Unit Test Suite**:
   - Command: `python -m unittest discover -s backend/tests`
   - Result: 32 tests ran, 32 passed (0 failures, 0 errors) in 0.129s.
2. **Node Verification Test Script**:
   - Command: `node scripts/verify_m4.js`
   - Result: All 3 verification steps (dateUtils parsing/fallbacks, approval state filtering, JSON endpoint artifact structure) passed cleanly.
3. **Frontend Production Build**:
   - Command: `npm run build` (inside `frontend/`)
   - Result: Vite production build completed cleanly in 2.07s with zero errors and zero warnings (`dist/assets/index-CsT6G7Fp.js`).
