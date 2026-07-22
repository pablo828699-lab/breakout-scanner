## 2026-07-21T15:04:54Z
<USER_REQUEST>
Identity & Archetype: teamwork_preview_worker
Working Directory: c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m3
Scope File: c:/Users/HP/mi-bot/breakout_scanner/PROJECT.md
Audit Reports to read:
- c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1/handoff.md
- c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1/analysis.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Task:
Refactor backend signal detection, deduplication, and persistence logic in `backend/main.py`, `backend/scanner.py`, `backend/capitulation_engine.py`, `backend/shock_detector.py`, and JSON signal state management.

Specific Requirements:
1. **Remove Destructive File Removal (`backend/main.py`)**:
   - Locate and REMOVE lines 346-350 in `main.py` (`os.remove(filepath)` on `capitulation_signals.json`). Manual scan triggers must merge and update signal state, NEVER delete the persistence file!

2. **24-Hour Persistence & Marginal Bar Preservation (`capitulation_engine.py`, `shock_detector.py`)**:
   - Refactor capitulation signal storage (`_save_capitulation_signals`) and tracking logic so signals persist for at least 24 hours (TTL = 24h) based on `timestamp` / `first_detected`.
   - Prevent marginal bar price changes (or day 2 stabilization) from immediately dropping active capitulation signals. An active signal remains in state until its 24-hour TTL expires or an explicit invalidation rule triggers.

3. **Key-Based Deduplication (`backend/scanner.py`)**:
   - Refactor candidate saving in `_save_recent_signals()` to perform key-based deduplication by `(ticker, direction)` or `ticker`.
   - Update existing entry timestamp or attributes when a ticker is re-detected, instead of blindly appending duplicate entries to `recent_signals.json`.
   - Retain all unique active signals within 24h window (or up to max 100 unique signals) without truncating active signals for other assets.

4. **Strict ISO 8601 Timestamp Formatting**:
   - Standardize all signal timestamp serialization (`timestamp`, `first_detected`, `last_updated`) to ISO 8601 strings (e.g. `s.timestamp.isoformat()` or `datetime.now(timezone.utc).isoformat()`). Do NOT format as `"%Y-%m-%d %H:%M UTC"`.

5. **Unit Tests**:
   - Create `backend/tests/test_signal_persistence.py` verifying 24h TTL signal retention, key deduplication, ISO timestamp formatting, and non-destructive JSON merges.
   - Run `python -m unittest discover -s backend` to verify all unit tests pass cleanly.

Output Requirements:
- Document all modified files in `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m3/changes.md`.
- Document test outcomes in `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_worker_m3/handoff.md`.
- Send message to orchestrator (d5b60c2c-cae3-4fcf-9beb-fdfe51e3634d) when done.
</USER_REQUEST>
