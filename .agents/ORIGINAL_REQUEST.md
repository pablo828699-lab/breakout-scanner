# Original User Request

## 2026-07-21T17:56:12Z

<USER_REQUEST>
Auditoría integral, refactorización lógica y verificación rigurosa del sistema Breakout Scanner (Equities + Crypto + Mineras), eliminando errores de sincronización, rate-limits y fallos silenciosos en Backend y Frontend.

Working directory: c:/Users/HP/mi-bot/breakout_scanner
Integrity mode: development

## Requirements

### R1. Auditoría de Lógica y Persistencia de Señales (Backend Python)
Auditar y refactorizar el flujo completo de detección (`scanner.py`, `capitulation_engine.py`, `shock_detector.py`) para garantizar que la desduplicación, actualización y sincronización a Render no eliminen señales activas de capitulación ni radar/breakout por cierres marginales.

### R2. Manejo Defensivo de Fuentes de Datos (Data Fetcher)
Fortalecer `data_fetcher.py` ante rate-limits de Yahoo Finance y Binance, utilizando sesiones HTTP persistentes con headers realistas, manejo transparente de errores (sin silenciarlos en `os.devnull`) y backoff exponencial.

### R3. Estabilidad y Parseo de Fechas en Dashboard (Frontend React/Vite)
Corregir en `App.jsx`, `CapitulationPanel.jsx` y `CandidatePanel.jsx` la conversión de marcas de tiempo UTC a ISO para evitar IDs NaN o Invalid Date, asegurando la persistencia y filtrado correcto en `localStorage`.

### R4. Verificación Automatizada y Cero Alucinaciones
Validar cada cambio mediante scripts de prueba independientes, peticiones HTTP reales a los endpoints de Render (`/api/capitulation`, `/api/candidates`) y un build de producción `npm run build` sin errores.

## Acceptance Criteria

### Backend & Sincronización
- All active capitulation signals persist in capitulation_signals.json and Render without getting deleted on reload.
- Rate limits on yfinance or Binance are caught and retried cleanly without halting scans.
- Ticker deduplication preserves active valid signals for at least 24 hours.

### Frontend & UI
- No ID or timestamp produces NaN or Invalid Date in browser console.
- Rendering of capitulation and candidate cards is 100% stable across F5 reloads.
- Build npm run build compiles with zero errors.
</USER_REQUEST>
