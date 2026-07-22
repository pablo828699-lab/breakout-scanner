# Comprehensive Frontend Audit & Technical Analysis Report

**Project**: Breakout Scanner (Frontend React + Vite Dashboard)  
**Auditor**: teamwork_preview_explorer (Frontend Explorer Agent)  
**Date**: 2026-07-21  
**Scope**: `frontend/src/App.jsx`, `frontend/src/components/CapitulationPanel.jsx`, `frontend/src/components/CandidatePanel.jsx`, `frontend/src/components/OpenPositions.jsx`, `frontend/src/components/TradeHistory.jsx`, `frontend/src/data/mockData.js`, API services & persistence logic.

---

## Executive Summary

An in-depth, read-only architectural and code-level audit was conducted on the frontend dashboard application of the Breakout Scanner system. The investigation identified critical bugs, structural anti-patterns, state corruption vectors on page reload (F5), key generation defects causing React DOM mis-renders, and timestamp parsing vulnerabilities leading to `NaN` or `Invalid Date` outputs.

### Summary of Key Findings
1. **Timestamp Processing Vulnerabilities**:
   - Date parsing functions (`safeDateParse` in `App.jsx` and inline IIFE in `CapitulationPanel.jsx`) fail on numeric epoch timestamps, microsecond timestamps (`.123456`), and strings lacking explicit timezone offsets.
   - `CandidatePanel.jsx` renders raw timestamp strings without normalization or formatting.
2. **Key Generation & State Filtering Flaws**:
   - `CapitulationPanel.jsx` uses array indices (`key={`${sig.ticker}-${idx}`}`) instead of unique entity IDs, causing React component state corruption and animation glitches when cards are removed or approved.
   - Signals approved by the user temporarily disappear from state but **re-appear in the candidate list after 2 minutes** when the polling interval fires because `handleApprove` does not add approved signal keys to the ignored/approved persistence filter.
3. **`localStorage` Persistence & Lifecycle Defects**:
   - `capitulationSignals` is **never persisted** to `localStorage`. On F5 reload, capitulation signals flash empty until the network fetch completes (up to 50 seconds if Render backend is sleeping).
   - Race condition between `loadStateFromCloud` and the `localStorage` sync `useEffect` can overwrite valid cloud state with empty/stale local state.
   - `capitalPerTrade` and `accountBalance` lack `isNaN()` guards during rehydration.
4. **Architectural Monolith**:
   - `App.jsx` (866 lines) acts as a monolithic controller containing 7 `useEffect` hooks, raw `fetch` logic, dual-fetch CDN fallbacks, inline signal calculations, modal state, and UI rendering. There is no `src/services/api.js` or `src/utils/dateUtils.js` module.

---

## 1. Timestamp Processing & Formatting Audit

### Evidence Chain & Code Locations

#### A. `App.jsx`: `safeDateParse(tsStr)` Implementation Analysis
- **Location**: `frontend/src/App.jsx`, Lines 20–26
```javascript
20: function safeDateParse(tsStr) {
21:   if (!tsStr) return Date.now();
22:   if (typeof tsStr === 'number') return tsStr;
23:   const isoStr = String(tsStr).replace(' ', 'T').replace(' UTC', 'Z');
24:   const parsed = Date.parse(isoStr);
25:   return isNaN(parsed) ? Date.now() : parsed;
26: }
```
- **Observed Failures & Edge Cases**:
  1. **Numeric Seconds vs Milliseconds**: Line 22 checks `typeof tsStr === 'number'` and directly returns `tsStr`. If the backend sends numeric Unix timestamps in seconds (e.g. `1721584620`), `safeDateParse` returns `1721584620`. When passed to `new Date(1721584620)`, JavaScript interprets this as milliseconds after epoch (~Jan 20, 1970), causing invalid date display and ID generation skew when compared against `Date.now()` (~`1721584620000`).
  2. **Numeric String Timestamps**: If `tsStr` is a string containing digits only (e.g., `"1721584620"`), line 23 turns it into `"1721584620"`. `Date.parse("1721584620")` evaluates to `NaN`. Line 25 catches the `NaN` and returns `Date.now()`, silently overriding the true timestamp with the current client time.
  3. **Microsecond Precision**: Backend pandas/SQL export outputs timestamps like `"2026-07-21 17:54:00.123456 UTC"`. `isoStr` becomes `"2026-07-21T17:54:00.123456Z"`. Standard JavaScript `Date.parse()` in V8/Safari supports up to 3 fractional digits (milliseconds). 6 fractional digits cause `Date.parse()` to return `NaN` in several browser environments, forcing a fallback to `Date.now()`.
  4. **Local Timezone Bias**: If `tsStr` is `"2026-07-21 17:54:00"` (without `' UTC'`), line 23 produces `"2026-07-21T17:54:00"`. `Date.parse()` without trailing `Z` parses ISO strings as **Local Time**, introducing timezone offsets (e.g., -3 hours in GMT-3), misaligning UTC trading signals with local system clocks.

#### B. `CapitulationPanel.jsx`: Inline IIFE Formatting
- **Location**: `frontend/src/components/CapitulationPanel.jsx`, Lines 433–441
```javascript
433: {timestamp && (
434:   <div style={{ fontSize: 10, color: COLORS.textSecondary, marginTop: 12, textAlign: 'right' }}>
435:     {(() => {
436:       const iso = String(timestamp).replace(' ', 'T').replace(' UTC', 'Z');
437:       const d = new Date(iso);
438:       return isNaN(d.getTime()) ? timestamp : d.toLocaleString('es-AR');
439:     })()}
440:   </div>
441: )}
```
- **Observed Failures**:
  1. **Duplicated Parsing Logic**: Performs inline string replacement inside component render loop on every state update.
  2. **Hardcoded Locale**: `d.toLocaleString('es-AR')` is hardcoded to Argentina locale formatting (`DD/MM/YYYY, HH:mm:ss`), inconsistent with the rest of the application.
  3. **Fallback to Unformatted String**: When `isNaN(d.getTime())` is true (e.g., due to string numeric timestamp or microsecond format), it falls back to raw `timestamp`, rendering strings like `"1721584620"` or `"2026-07-20 18:02:00.123456 UTC"` directly to users.

#### C. `CandidatePanel.jsx`: Unformatted Raw Rendering
- **Location**: `frontend/src/components/CandidatePanel.jsx`, Line 56
```javascript
56: <p className="text-[10px] text-slate-500 mt-1">{candidate.timestamp}</p>
```
- **Observed Failure**: Displays raw `{candidate.timestamp}` as stored in state. If backend returns `"2026-07-16 14:59 UTC"`, `"2026-07-16T14:59:00.000Z"`, or `undefined`, it displays raw unformatted strings or blank spaces with zero consistency across panels.

---

## 2. Key Generation & State Filtering Audit

### Evidence Chain & Code Locations

#### A. React `key` Prop Violation in `CapitulationPanel.jsx`
- **Location**: `frontend/src/components/CapitulationPanel.jsx`, Lines 484–492
```javascript
484: {list.map((sig, idx) => (
485:   <SignalCard
486:     key={sig?.ticker ? `${sig.ticker}-${idx}` : idx}
487:     signal={sig}
488:     livePriceMap={livePriceMap}
489:     onApprove={onApprove}
490:     onReject={onReject}
491:   />
492: ))}
```
- **Defect Analysis**:
  - `key` is constructed using array index `idx` (`${sig.ticker}-${idx}`).
  - When a user rejects or approves a signal card, `setCapitulationSignals` filters the array, changing item indices.
  - Because React relies on stable keys to match virtual DOM nodes, using index-based keys causes React to preserve child state/DOM elements for the wrong item (e.g. action button hover states, expanded accordions, live price animation timers).
  - **Correct Key**: `sig.id` or `${sig.ticker}_${sig.timestamp}`.

#### B. Approved Candidate Re-appearance Bug
- **Location**: `frontend/src/App.jsx`, Lines 262–357 (`fetchCandidates`) & Lines 528–551 (`handleApprove`)
- **Step-by-Step Evidence Chain**:
  1. `App.jsx` Line 528–551: User clicks "Aprobar" on a candidate card. `handleApprove` runs:
     ```javascript
     setOpenPositions([newPosition, ...openPositions]);
     setCandidates(candidates.filter((c) => c.id !== candidate.id));
     ```
  2. `candidates` state is updated by removing the candidate.
  3. `localStorage.setItem('candidates', ...)` updates `localStorage` (Line 160).
  4. **The Bug**: 2 minutes later, the polling interval inside `fetchCandidates()` fires (Line 355).
  5. `fetchCandidates()` fetches raw JSON from `/api/candidates` (Line 269).
  6. `fetchCandidates()` evaluates `existingIds`:
     ```javascript
     const existingIds = new Set(prevCandidates.map(c => `${c.ticker}_${c.timestamp}`));
     ```
     Because the approved candidate was removed from `candidates`, it is **no longer in `prevCandidates`**.
  7. `fetchCandidates()` evaluates `ignoredSet` from `localStorage.getItem('ignoredCandidates')`. Because `handleApprove` **never added the approved signal key to `ignoredCandidates`**, `ignoredSet.has(...)` returns `false`!
  8. `fetchCandidates()` concludes this candidate is new, appends it to `candidates`, and **the approved signal re-appears on the CandidatePanel**!

#### C. `inPosition` Filtering Behavior Divergence
- **Location**: `frontend/src/App.jsx`, Candidate mapping (Line 342) vs. Capitulation mapping (Line 452 & 513)
- **Defect**:
  - In `fetchCandidates()` (Line 342), candidate objects are mapped with `inPosition: openIds.has(c.ticker)`, but they are **NOT filtered out** of `candidates` array! They remain visible in `CandidatePanel`.
  - In manual capitulation scan (Line 513), capitulation signals are explicitly filtered with `!openIds.has(c.ticker)`.
  - This inconsistency causes candidate panels to exhibit different filtering rules depending on whether signals are fetched via automatic background polling vs manual scan button clicks.

---

## 3. `localStorage` Persistence & State Lifecycle Audit

### Evidence Chain & Code Locations

#### A. Missing `localStorage` Persistence for Capitulation Signals
- **Location**: `frontend/src/App.jsx`, Lines 149 & 386–460
- **Evidence**:
  - Candidates: Initialized from `localStorage.getItem('candidates')` (Line 37) and updated via `useEffect` (Line 160).
  - Open Positions: Initialized from `localStorage.getItem('openPositions')` (Line 66) and updated via `useEffect` (Line 188).
  - Trade History: Initialized from `localStorage.getItem('tradeHistory')` (Line 77) and updated via `useEffect` (Line 189).
  - Capitulation Signals: Initialized as `useState([])` (Line 149). **No `localStorage.getItem('capitulationSignals')` or `localStorage.setItem('capitulationSignals', ...)` exists anywhere in `App.jsx`.**
- **Impact**: On every browser refresh (F5), `capitulationSignals` resets to `[]`. The user sees an empty Capitulation Panel until `fetchCapitulation()` completes its HTTP call (up to 50 seconds on Render cold starts).

#### B. Cloud Sync vs. Local Storage Race Condition
- **Location**: `frontend/src/App.jsx`, Lines 166–184 & Lines 187–208
- **Evidence**:
  1. On component mount, `loadStateFromCloud()` fires asynchronously (Line 166).
  2. Simultaneously, `openPositions` and `tradeHistory` are loaded from `localStorage`.
  3. `isLoadedFromCloud` is initially `false`.
  4. Line 187 has a sync `useEffect` with dependency array `[openPositions, tradeHistory, kpis, isLoadedFromCloud]`.
  5. If `loadStateFromCloud()` fails or returns empty data, `isLoadedFromCloud` is set to `true` in the `finally` block (Line 179).
  6. The `useEffect` on Line 187 immediately triggers `saveStateToCloud()` after 1000ms debounce, pushing whatever local state was in `localStorage` back to the cloud endpoint `/api/cloud-state`, overwriting cloud data with potentially stale local data.

#### C. Floating Point / NaN Corruption on Settings Rehydration
- **Location**: `frontend/src/App.jsx`, Lines 87–95
```javascript
87: const [capitalPerTrade, setCapitalPerTrade] = useState(() => {
88:   const saved = localStorage.getItem('capitalPerTrade');
89:   return saved ? Number(saved) : 1000;
90: });
```
- **Defect**: If a user clears the input box or enters invalid characters, `capitalPerTrade` becomes `NaN`. Line 211 saves `"NaN"` to `localStorage`. On F5 reload, `Number("NaN")` evaluates to `NaN`. All trade sizing calculations (`pnl`, `size`) become `NaN` throughout the application.

---

## 4. Specific Refactoring Recommendations

### Recommendation 1: Create Centralized API Service (`frontend/src/services/api.js`)
Extract all direct `fetch` calls, base URL configuration, AbortController timeouts, and dual-fetch fallback logic out of `App.jsx` into a modular service layer.

```javascript
// frontend/src/services/api.js
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'https://breakout-scanner-xg9f.onrender.com';

async function fetchWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (err) {
    clearTimeout(id);
    throw err;
  }
}

export const apiService = {
  async getCandidates() {
    try {
      const resp = await fetchWithTimeout(`${BACKEND_URL}/api/candidates`);
      if (resp.ok) return await resp.json();
    } catch (e) {
      console.warn('Render candidates endpoint failed, trying CDN fallback...');
    }
    const fallbackResp = await fetchWithTimeout('/recent_signals.json');
    if (fallbackResp.ok) return await fallbackResp.json();
    throw new Error('Failed to fetch candidates from all sources');
  },

  async getCapitulationSignals() {
    try {
      const resp = await fetchWithTimeout(`${BACKEND_URL}/api/capitulation`);
      if (resp.ok) return await resp.json();
    } catch (e) {
      console.warn('Render capitulation endpoint failed, trying CDN fallback...');
    }
    const fallbackResp = await fetchWithTimeout('/capitulation_signals.json');
    if (fallbackResp.ok) return await fallbackResp.json();
    throw new Error('Failed to fetch capitulation signals from all sources');
  },

  async getLivePrices(tickers = []) {
    if (!tickers || tickers.length === 0) return {};
    const unique = [...new Set(tickers)].filter(Boolean).join(',');
    const resp = await fetchWithTimeout(`${BACKEND_URL}/api/prices?tickers=${unique}`, {}, 8000);
    if (resp.ok) return await resp.json();
    return {};
  },

  async triggerScan(endpoint, pin) {
    if (pin !== '1234') throw new Error('Invalid PIN');
    const resp = await fetchWithTimeout(`${BACKEND_URL}/${endpoint}`);
    return resp.ok;
  },

  async getCloudState() {
    const resp = await fetchWithTimeout(`${BACKEND_URL}/api/cloud-state`, {}, 6000);
    if (resp.ok) return await resp.json();
    return null;
  },

  async saveCloudState(state) {
    await fetchWithTimeout(`${BACKEND_URL}/api/cloud-state`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state)
    }, 6000);
  }
};
```

---

### Recommendation 2: Create Defensive Date Utility (`frontend/src/utils/dateUtils.js`)
Create a robust, zero-dependency date utility to standardize UTC parsing, microsecond handling, and localized ISO formatting.

```javascript
// frontend/src/utils/dateUtils.js

/**
 * Defensively parses any timestamp input (ISO string, UTC string, numeric epoch seconds/ms, microsecond string)
 * into a valid UTC Date object.
 */
export function parseUTCTimestamp(ts) {
  if (!ts) return new Date();
  if (typeof ts === 'number') {
    // If epoch seconds (< 10^11), convert to milliseconds
    return new Date(ts < 10000000000 ? ts * 1000 : ts);
  }

  const str = String(ts).trim();
  
  // If string contains pure numbers (epoch string)
  if (/^\d+$/.test(str)) {
    const num = Number(str);
    return new Date(num < 10000000000 ? num * 1000 : num);
  }

  // Normalize spaces, python ' UTC' suffix, and trim microseconds (.123456 -> .123)
  let normalized = str
    .replace(' ', 'T')
    .replace(' UTC', 'Z')
    .replace(/(\.\d{3})\d+/, '$1'); // truncate microseconds to milliseconds

  // Ensure trailing Z for UTC if no timezone offset is present
  if (!normalized.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized += 'Z';
  }

  const parsedMs = Date.parse(normalized);
  return isNaN(parsedMs) ? new Date() : new Date(parsedMs);
}

/**
 * Formats timestamp to ISO string YYYY-MM-DD HH:mm UTC
 */
export function formatDisplayDate(ts, locale = 'es-AR') {
  const d = parseUTCTimestamp(ts);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
}
```

---

### Recommendation 3: Refactor `App.jsx`
1. **Add `approvedCandidates` tracking**:
   - Maintain `approvedCandidates` in `localStorage` or append approved signal keys (`${ticker}_${timestamp}`) to `ignoredCandidates` inside `handleApprove` to prevent approved signals from re-appearing on the next 2-minute polling fetch.
2. **Persist `capitulationSignals` to `localStorage`**:
   - Store and rehydrate `capitulationSignals` from `localStorage.getItem('capitulationSignals')`.
3. **Add `isNaN()` Guards to numeric settings**:
   ```javascript
   const [capitalPerTrade, setCapitalPerTrade] = useState(() => {
     const saved = localStorage.getItem('capitalPerTrade');
     const num = Number(saved);
     return (saved && !isNaN(num) && num > 0) ? num : 1000;
   });
   ```

---

### Recommendation 4: Refactor `CapitulationPanel.jsx`
1. **Fix React Key Prop** (Line 486):
   - Replace `key={`${sig.ticker}-${idx}`}` with `key={sig.id || `${sig.ticker}_${sig.timestamp}_${idx}`}`.
2. **Replace Inline IIFE Date Parsing** (Line 436):
   - Use `formatDisplayDate(timestamp)` from `dateUtils.js`.

---

### Recommendation 5: Refactor `CandidatePanel.jsx`
1. **Format Timestamps** (Line 56):
   - Replace raw `{candidate.timestamp}` with `formatDisplayDate(candidate.timestamp)`.
2. **Defensive Indicator Rendering**:
   - Wrap `candidate.adx`, `candidate.rocPct` with nullish fallback checks to prevent `NaN%` displays.

---

## Verification Matrix

| Vulnerability / Defect | Location | Verification Method |
|---|---|---|
| `NaN` / `Invalid Date` on timestamps | `App.jsx:20`, `CapitulationPanel.jsx:436` | Test with epoch seconds, ISO strings, microsecond strings |
| Key prop index usage | `CapitulationPanel.jsx:486` | Verify React keys are stable UUIDs / entity IDs |
| Approved signal re-appearance | `App.jsx:549` vs `App.jsx:346` | Approve a signal, wait 2 min for polling, verify signal does NOT return |
| Missing Capitulation persistence | `App.jsx:149` | Reload page (F5), verify capitulation signals remain cached |
| Settings `NaN` corruption | `App.jsx:87` | Pass invalid string to `capitalPerTrade`, reload F5, verify fallback to 1000 |
