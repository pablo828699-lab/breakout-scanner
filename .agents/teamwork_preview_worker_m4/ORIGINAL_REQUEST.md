## 2026-07-21T18:10:18Z
You are Worker M4 for the Breakout Scanner project.

Your Working Directory: c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m4

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Tasks:
1. Frontend Date Utility (`frontend/src/utils/dateUtils.js`):
   Create or update `dateUtils.js` to provide robust date parsing and formatting:
   - Handle unix timestamps (seconds or milliseconds), ISO 8601 strings, microsecond strings (e.g., `2026-07-21T18:00:00.123456Z`), and UTC format strings.
   - Prevent any output of `NaN` or `Invalid Date`.
   - Provide helper functions for relative time formatting (e.g., "5 mins ago") and formatted ISO/locale strings.

2. Frontend API Service (`frontend/src/services/api.js`):
   Create or update `api.js` to centralize HTTP fetching for endpoints:
   - `fetchCapitulationSignals()` targeting `/api/capitulation`
   - `fetchCandidates()` targeting `/api/candidates`
   - Include error handling, timeout defaults, and clean fallback arrays on fetch failure.

3. App Component (`frontend/src/App.jsx`):
   - Refactor timestamp parsing using `dateUtils.js`.
   - Implement `localStorage` state persistence for signals and candidate approval status.
   - Maintain `approvedCandidates` / `ignoredCandidates` in `localStorage` so that when candidates are approved/dismissed by the user, they are persisted locally and excluded from rendering during 2-minute polling refreshes.

4. Component Panels:
   - Refactor `frontend/src/components/CapitulationPanel.jsx` (or `frontend/src/CapitulationPanel.jsx` / existing component structure): use stable entity React keys (`sig.id` or `${sig.ticker}_${sig.timestamp}`) instead of array index keys.
   - Refactor `frontend/src/components/CandidatePanel.jsx`: format timestamps with `dateUtils.js`.

5. Backend Adjustments:
   - Check `backend/capitulation_engine.py` & `backend/scanner.py`: verify TTL evaluation checks `last_updated` (preserving active signals for 24h) and `first_detected` correctly.
   - Check `backend/shock_detector.py`: ensure benchmark calculation in `classify_shock` handles market benchmark alignment cleanly.

6. Build & Verification:
   - Execute clean build: `npm run build` inside `frontend/` directory and ensure zero errors or warnings.
   - Execute verification test script testing backend API responses (`/api/capitulation` and `/api/candidates`).
   - Create tests or test script verifying date parsing and frontend candidate approval filtering.
   - Document all changes, test commands, and build results in `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m4/handoff.md`.

When complete, reply with a detailed summary of your work and handoff report location.
