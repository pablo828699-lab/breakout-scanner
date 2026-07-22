## 2026-07-21T14:57:04-03:00
<USER_REQUEST>
Identity & Archetype: teamwork_preview_explorer
Working Directory: c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1
Project Scope File: c:/Users/HP/mi-bot/breakout_scanner/PROJECT.md

Task:
Perform an in-depth, read-only audit of the backend signal detection, deduplication, and persistence logic in `c:/Users/HP/mi-bot/breakout_scanner/backend/`.
Focus files:
- `scanner.py`
- `capitulation_engine.py`
- `shock_detector.py`
- Any JSON persistence files (e.g., `capitulation_signals.json`, state files) and `app.py` / storage utilities.

Objectives:
1. Examine how signals are detected, saved, updated, and purged.
2. Identify why active capitulation signals or breakout candidates get wiped/deleted within 24h or when marginal bar closes occur.
3. Identify how signal deduplication is implemented and why it leads to signal loss instead of preserving active valid signals for >= 24h.
4. Formulate specific refactoring recommendations for `scanner.py`, `capitulation_engine.py`, and `shock_detector.py`.

Requirements:
- Read files using `view_file` or `grep_search`. Do NOT modify any source code files.
- Document step-by-step evidence chains with file paths and line numbers.
- Write your comprehensive audit report to `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1/analysis.md`.
- Write your handoff to `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_1/handoff.md`.
- Send a message back to the orchestrator (conversation ID: d5b60c2c-cae3-4fcf-9beb-fdfe51e3634d) when done with path to handoff.md.
</USER_REQUEST>
