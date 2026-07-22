# Handoff Report — Frontend Audit & Refactoring Proposal

**Agent ID**: teamwork_preview_explorer_m1_3  
**Target Project**: Breakout Scanner (`frontend/`)  
**Date**: 2026-07-21  

---

## 1. Observation

Direct observations from examining source files in `c:/Users/HP/mi-bot/breakout_scanner/frontend/src/`:

1. **`App.jsx` Lines 20–26 (`safeDateParse`)**:
   ```javascript
   function safeDateParse(tsStr) {
     if (!tsStr) return Date.now();
     if (typeof tsStr === 'number') return tsStr;
     const isoStr = String(tsStr).replace(' ', 'T').replace(' UTC', 'Z');
     const parsed = Date.parse(isoStr);
     return isNaN(parsed) ? Date.now() : parsed;
   }
   ```
   *Observed flaw*: Numeric epoch seconds `1721584620` return as-is (`typeof tsStr === 'number'`), skewing date math against millisecond timestamps (`Date.now()`). Numeric strings like `"1721584620"` fail `Date.parse()` and fall back to `Date.now()`. Microsecond strings like `"2026-07-21 17:54:00.123456 UTC"` cause `Date.parse()` failure in JS environments.

2. **`CapitulationPanel.jsx` Lines 433–441 (Inline Date Parsing)**:
   ```javascript
   {timestamp && (
     <div style={{ fontSize: 10, color: COLORS.textSecondary, marginTop: 12, textAlign: 'right' }}>
       {(() => {
         const iso = String(timestamp).replace(' ', 'T').replace(' UTC', 'Z');
         const d = new Date(iso);
         return isNaN(d.getTime()) ? timestamp : d.toLocaleString('es-AR');
       })()}
     </div>
   )}
   ```
   *Observed flaw*: Inline IIFE executes on every render. Missing `' UTC'` suffix in strings parses as local time instead of UTC. Fallback returns unformatted raw string when parsing fails.

3. **`CapitulationPanel.jsx` Line 486 (Array Index Key Prop)**:
   ```javascript
   key={sig?.ticker ? `${sig.ticker}-${idx}` : idx}
   ```
   *Observed flaw*: Array index `idx` is used in React `key` prop, leading to element state recycling bugs when capitulation items are removed or approved.

4. **`CandidatePanel.jsx` Line 56 (Raw Timestamp Render)**:
   ```javascript
   <p className="text-[10px] text-slate-500 mt-1">{candidate.timestamp}</p>
   ```
   *Observed flaw*: Renders raw `{candidate.timestamp}` without parsing or localization.

5. **`App.jsx` Line 149 vs Lines 159–208 (Missing Persistence for Capitulation Signals)**:
   - `candidates`, `openPositions`, `tradeHistory`, `kpis` are stored/rehydrated from `localStorage`.
   - `capitulationSignals` state (Line 149) has no `localStorage.getItem` or `localStorage.setItem` call. On F5 reload, `capitulationSignals` flashes empty `[]`.

6. **`App.jsx` Lines 549–550 vs Line 346 (Approved Signal Re-appearance Bug)**:
   - Line 549: `setCandidates(candidates.filter((c) => c.id !== candidate.id));` removes candidate from state upon approval.
   - Line 549 does NOT add `${candidate.ticker}_${candidate.timestamp}` to `ignoredCandidates` or an `approvedCandidates` set in `localStorage`.
   - Line 346 (`fetchCandidates` filter): checks `!existingIds.has(...) && !ignoredSet.has(...)`. On the next 2-minute poll, the candidate is re-fetched from `/api/candidates` and re-appended to `candidates`.

---

## 2. Logic Chain

1. **Observation 1 & 2** show that timestamp strings coming from python backend/pandas (`"YYYY-MM-DD HH:mm:ss.ffffff UTC"`, epoch seconds, or local format strings) fail `Date.parse()` or fall back to `Date.now()` / unformatted strings.
2. **Observation 3** shows that React keys in `CapitulationPanel` rely on array index `idx`. When an item is removed from `capitulationSignals`, React reuses existing DOM nodes, resulting in UI inconsistencies or broken event handlers.
3. **Observation 4 & 5** confirm that local UI state is partially unpersisted: refreshing the browser (F5) clears `capitulationSignals` completely and displays raw string timestamps on Candidate cards.
4. **Observation 6** proves why approved candidates re-appear after 2 minutes: removing a candidate from `candidates` state without persisting its key into an ignore/approved set causes `fetchCandidates()` to re-add the item on the next background poll cycle.
5. **Conclusion**: A modular API service (`src/services/api.js`), a defensive UTC date utility (`src/utils/dateUtils.js`), approved-set tracking, and stable entity React keys are required to fix these defects.

---

## 3. Caveats

- **Network Environment**: Audit was conducted in `CODE_ONLY` mode. Backend API endpoints (`https://breakout-scanner-xg9f.onrender.com`) were inspected via static source code and JSON fixture files (`backend/recent_signals.json`, `backend/capitulation_signals.json`). Live network response headers were not tested directly.
- **Source Code Immutability**: No source code files were modified during this investigation. Implementation of recommendations is deferred to subsequent implementation tasks (e.g. Milestone 4).

---

## 4. Conclusion

The frontend codebase is functional but contains critical state management, persistence, timestamp, and React key issues. 

### Core Actionable Recommendations:
1. **Create `frontend/src/services/api.js`**: Centralize HTTP communication, AbortController timeouts, and dual-fetch CDN fallbacks.
2. **Create `frontend/src/utils/dateUtils.js`**: Implement `parseUTCTimestamp()` and `formatDisplayDate()` to handle numeric seconds, ISO strings, microsecond strings, and UTC conversions safely.
3. **Fix Candidate Approval Persistence**: Append approved candidate keys to `ignoredCandidates` (or a new `approvedCandidates` set) in `handleApprove` to prevent signals from re-appearing on polling updates.
4. **Fix React Key Props in `CapitulationPanel.jsx`**: Change `key={`${sig.ticker}-${idx}`}` to `key={sig.id || `${sig.ticker}_${sig.timestamp}_${idx}`}`.
5. **Persist Capitulation Signals**: Save and restore `capitulationSignals` state to/from `localStorage` to prevent blank panel flashes on F5 reload.

---

## 5. Verification Method

To verify findings and future fixes independently:

1. **File Inspection**:
   - Inspect `c:/Users/HP/mi-bot/breakout_scanner/.agents/teamwork_preview_explorer_m1_3/analysis.md` for detailed line-by-line evidence chains and refactoring code templates.
2. **Timestamp Verification Test**:
   - Run a test script or browser console test passing `"2026-07-21 17:54:00.123456 UTC"`, `1721584620`, and `"1721584620"` to `parseUTCTimestamp` to confirm valid `Date` objects are produced without `NaN` or `Invalid Date`.
3. **Build & Lint Verification**:
   - Run `npm run build` inside `frontend/` directory to verify Vite bundling and JSX syntax validity.
4. **State Persistence Verification**:
   - Load dashboard, approve a signal, trigger a refresh (F5), wait 2 minutes for polling, and verify the signal does NOT re-appear in candidate cards.
