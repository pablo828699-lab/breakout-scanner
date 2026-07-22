# Project: Breakout Scanner Refactor & Verification

## Architecture
Breakout Scanner is a full-stack scanning system (Python backend + React/Vite frontend) tracking Equities, Crypto, and Mineras for capitulation signals, volume shocks, and breakouts.

- **Backend**: Python scanner modules (`scanner.py`, `capitulation_engine.py`, `shock_detector.py`, `data_fetcher.py`), serving API endpoints (`/api/capitulation`, `/api/candidates`) and syncing JSON persistence files.
- **Frontend**: React + Vite (`App.jsx`, `CapitulationPanel.jsx`, `CandidatePanel.jsx`), handling real-time signal cards, filtering, localstorage state, and UTC/ISO timestamp formatting.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Codebase Audit & Baseline Assessment | Comprehensive audit of backend & frontend code | none | DONE |
| 2 | Defensive Data Fetcher Refactor | `data_fetcher.py`: persistent sessions, realistic headers, error logging, exponential backoff | M1 | DONE |
| 3 | Signal Deduplication & Persistence Refactor | `scanner.py`, `capitulation_engine.py`, `shock_detector.py`: preserve signals >=24h, eliminate marginal bar wipes | M1, M2 | DONE |
| 4 | Frontend Fixes & E2E Verification | `App.jsx`, panels: UTC->ISO timestamp parsing, zero NaN/Invalid Date, localstorage persistence, `npm run build`, endpoint testing | M1, M2, M3 | DONE |

## Interface Contracts
### Backend API Endpoints
- `GET /api/capitulation`: Returns active capitulation signal items containing valid ISO timestamps.
- `GET /api/candidates`: Returns candidate breakout items containing valid ISO timestamps.

## Code Layout
- `backend/`: Python backend engine and API server.
- `frontend/`: React + Vite dashboard app.
