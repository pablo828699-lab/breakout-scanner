# Original User Request

## 2026-07-21T18:10:00Z

Identity & Archetype: Project Orchestrator (Generation 2)
Working Directory: c:/Users/HP/mi-bot/breakout_scanner/.agents/orchestrator
Scope File: c:/Users/HP/mi-bot/breakout_scanner/PROJECT.md

Task:
Resume orchestrator execution for Breakout Scanner project.
Read handoff.md, BRIEFING.md, ORIGINAL_REQUEST.md, and progress.md in c:/Users/HP/mi-bot/breakout_scanner/.agents/orchestrator/ for current state.
Your parent is 35e2212e-647a-4ee7-b062-9c248b2c58b6 — use this ID for all escalation and status reporting (send_message).

Objectives:
1. Re-initialize your 10-minute heartbeat cron.
2. Execute Milestone 4 (Frontend Fixes, Candidate Persistence & E2E Verification).
   - Dispatch Worker M4 (`teamwork_preview_worker`) with `.agents/teamwork_preview_worker_m4` to:
     a. Fix `dateUtils.js` & `api.js` in `frontend/src/`.
     b. Refactor `App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`.
     c. Fix candidate approval persistence in `localStorage` so approved items do not re-appear on 2-minute polling.
     d. Fix minor TTL evaluation (`last_updated` vs `first_detected`) and `classify_shock` benchmark alignment in backend.
     e. Run clean `npm run build` in `frontend/`.
     f. Run live verification test script against Render backend endpoints (`/api/capitulation`, `/api/candidates`).
3. Run verification subagents for Milestone 4 (Reviewers, Challengers, Forensic Auditor M4).
4. Present final synthesis and report victory to the Sentinel!
