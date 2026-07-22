# Forensic Audit Report — Milestone 4

**Work Product**: Milestone 4 (Frontend Fixes, Candidate Persistence & E2E Verification)  
**Profile**: General Project  
**Verdict**: CLEAN  

---

## 1. Observation

Direct empirical inspection of modified Milestone 4 files and test executions yielded the following evidence:

1. **Frontend Date Utility (`frontend/src/utils/dateUtils.js`)**:
   - `parseDate` (lines 18–67) implements genuine regex and timestamp detection supporting Unix timestamps (seconds vs. ms cutoff at `1e11`), ISO 8601 strings with sub-second microsecond truncation (`replace(/(\.\d{3})\d+/, '$1')`), UTC suffix cleanup, and missing timezone normalization to UTC (`Z`).
   - `formatTimestamp` (lines 90–113) and `formatRelativeTime` (lines 140–162) handle invalid/missing input gracefully without ever returning `"NaN"` or `"Invalid Date"`.
2. **Frontend API Service (`frontend/src/services/api.js`)**:
   - `fetchWithTimeout` (lines 18–31) uses `AbortController` with `DEFAULT_TIMEOUT_MS` (12000ms) and guarantees `clearTimeout` execution in a `finally` block.
   - `fetchCapitulationSignals` (lines 40–70) and `fetchCandidates` (lines 79–109) query primary Render backend endpoints (`/api/capitulation` & `/api/candidates`), with fallback to local JSON files (`/capitulation_signals.json` & `/recent_signals.json`), and safe `[]` array returns on total failure.
3. **App Component (`frontend/src/App.jsx`)**:
   - Lines 130–138: Initialized `ignoredCandidates` and `approvedCandidates` state from `localStorage`.
   - Lines 271–272, 364–367, 402, 463, 497–501, 513–516, 525–528: `loadCandidates` and `loadCapitulation` map incoming items and filter against `ignoredSet` and `approvedSet` using unique item key identifier `${ticker}_${timestamp}`. Handlers `handleApprove`, `handleReject`, and `handleRejectCapitulation` persist these keys into `localStorage` (`approvedCandidates` and `ignoredCandidates`).
4. **Component Panels**:
   - `frontend/src/components/CapitulationPanel.jsx`: Line 482 constructs stable entity React keys `const key = sig?.id || (sig?.ticker && sig?.timestamp ? `${sig.ticker}_${sig.timestamp}` : `cap_${sig?.ticker || idx}`);`. Lines 436 formats timestamps using `formatTimestamp(timestamp)` and `formatRelativeTime(timestamp)`.
   - `frontend/src/components/CandidatePanel.jsx`: Line 43 constructs stable entity React keys `key={candidate.id || `${candidate.ticker}_${candidate.timestamp}`}`. Lines 57 uses `formatTimestamp` and `formatRelativeTime`.
5. **Backend Modules**:
   - `backend/scanner.py`: Lines 369 & 499 evaluate signal retention TTL against `item.get("last_updated") or item.get("first_detected") or item.get("timestamp")`, ensuring actively re-detected signals are preserved for 24 hours.
   - `backend/shock_detector.py`: Lines 142–150 in `classify_shock` accept optional `daily_df` and compute `common_dates = daily_df.index.intersection(benchmark_df.index)` for exact date index alignment between asset and benchmark.
6. **Independent Execution Results**:
   - **Backend Unit Tests**: Command `python -m unittest discover -s backend/tests` executed 32 tests in 0.108s. Result: **32 passed, 0 failures, 0 errors**.
   - **Node Date Utility Verification**: Command `node scripts/verify_m4.js` passed all assertions for date parsing (unix sec, unix ms, microsecond strings, UTC strings, invalid inputs, relative formatting, candidate approval filtering, JSON array checks).
   - **Frontend Build**: Command `npm run build` in `frontend/` completed in 1.78s with **0 errors and 0 warnings**, producing production assets `dist/assets/index-CsT6G7Fp.js` (247.16 kB) and `dist/assets/index-CO22c7EJ.css` (43.25 kB).

---

## 2. Logic Chain

1. **Absence of Hardcoded Values & Facades**: Inspection of `dateUtils.js`, `api.js`, `App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`, `scanner.py`, and `shock_detector.py` confirmed that all data transformations, network retries/fallbacks, and calculation routines implement real algorithm logic.
2. **State & Filtering Integrity**: In `App.jsx`, candidates and capitulations are filtered against persisted `approvedCandidates` and `ignoredCandidates` sets. When a candidate is approved or rejected, its unique identifier `${ticker}_${timestamp}` is added to the respective state set and written to `localStorage`. During subsequent 2-minute polling cycles, incoming signals matching these keys are filtered out prior to state update, preventing dismissed or approved candidates from reappearing on the dashboard.
3. **React Render Stability**: Changing list item React keys from array index keys (`${sig.ticker}-${idx}`) to stable entity identifiers (`candidate.id` or `${candidate.ticker}_${candidate.timestamp}`) in `CapitulationPanel.jsx` and `CandidatePanel.jsx` prevents DOM element re-creation and state mismatch during polling updates.
4. **Backend Retention & Alignment**: Evaluating `last_updated` in `scanner.py` guarantees active signals are retained for 24 hours from their latest update. Date index intersection in `shock_detector.py` eliminates classification errors caused by misaligned trading calendar dates between equities/crypto and benchmark indexes (SPY/BTCUSDT).
5. **Empirical Verification**: Running backend unit tests, Node assertion scripts, and Vite production build independently confirmed complete operational readiness with zero errors.

---

## 3. Caveats

- `localStorage` persistence is local to the browser instance/origin. Clearing browser cache resets local approval/rejection state, causing signals present in backend JSON endpoints to reload into the UI unless synced to cloud state.
- `fetchWithTimeout` default timeout of 12000ms relies on standard browser/Node `AbortController` support.

---

## 4. Conclusion

Milestone 4 is **CLEAN**. There are no integrity violations, no hardcoded test values, no facade implementations, no suppressed errors, and no unhandled exceptions. All functional requirements have been genuinely implemented and verified.

---

## 5. Verification Method

To independently verify this audit:

1. **Run Backend Unit Tests**:
   ```bash
   python -m unittest discover -s backend/tests
   ```
   *Expected Output*: 32 tests pass with 0 errors.

2. **Run Node Verification Script**:
   ```bash
   node scripts/verify_m4.js
   ```
   *Expected Output*: `ALL VERIFICATION CHECKS PASSED!`

3. **Run Frontend Production Build**:
   ```bash
   cd frontend && npm run build
   ```
   *Expected Output*: Build completes with zero errors and zero warnings.
