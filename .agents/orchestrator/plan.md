# Orchestration Plan — Breakout Scanner Refactor & Verification

## Objectives
1. **Milestone 1: Codebase Audit & Baseline Assessment**
   - Perform read-only exploration of `backend/` (`scanner.py`, `capitulation_engine.py`, `shock_detector.py`, `data_fetcher.py`, `app.py`, storage JSON files) and `frontend/` (`App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`, `api.js`).
   - Identify precise root causes of:
     - Signal deletion/deduplication wipes within 24h & marginal bar deletions.
     - Data fetcher silent errors / `devnull` muting & rate limits on yfinance/Binance.
     - Timestamp parse errors causing NaN/Invalid Date and localStorage issues in Frontend.
   - Produce comprehensive audit findings in `.agents/explorer_1/analysis.md`.

2. **Milestone 2: Defensive Data Fetcher (`data_fetcher.py`)**
   - Implement persistent HTTP session (`requests.Session` / connection pooling).
   - Add realistic User-Agent and headers.
   - Replace devnull muting with structured error logging.
   - Add exponential backoff & retry mechanisms for yfinance and Binance.

3. **Milestone 3: Signal Logic & Persistence Refactor (`scanner.py`, `capitulation_engine.py`, `shock_detector.py`)**
   - Fix capitulation signal and breakout signal persistence in `capitulation_signals.json` / Render state.
   - Fix ticker deduplication logic to maintain valid active signals for at least 24 hours.
   - Prevent marginal bar deletions from wiping valid historical or active signals.

4. **Milestone 4: Frontend Stability, Timestamp Parsing & E2E Verification**
   - Fix UTC to ISO timestamp conversion in `App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`.
   - Ensure zero `NaN` or `Invalid Date` errors.
   - Ensure `localStorage` state persistence & clean sync across reloads.
   - Run verification scripts, test live endpoints `/api/capitulation` and `/api/candidates`.
   - Verify error-free `npm run build`.

## Verification Gate Criteria
- Forensic Auditor verdict CLEAN.
- Reviewer checks pass.
- Build & test verification scripts pass.
