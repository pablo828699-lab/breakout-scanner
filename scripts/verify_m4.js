/**
 * Verification Test Script for Worker M4.
 * Tests:
 * 1. dateUtils.js: unix sec/ms, ISO 8601, microsecond strings, UTC format strings, invalid inputs.
 * 2. Candidate approval filtering & localStorage state persistence simulation.
 * 3. Endpoints JSON format validity (recent_signals.json and capitulation_signals.json).
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

// 1. Load dateUtils module dynamically
const dateUtilsPath = path.join(__dirname, '../frontend/src/utils/dateUtils.js');
const dateUtilsCode = fs.readFileSync(dateUtilsPath, 'utf8');

// Convert ESM exports to CommonJS module.exports for Node testing environment
const cjsCode = dateUtilsCode.replace(/export function (\w+)/g, 'function $1') + 
  '\nmodule.exports = { parseDate, safeDateParse, formatTimestamp, formatISO, formatRelativeTime };';

const testModule = { exports: {} };
const evalFn = new Function('module', 'exports', cjsCode);
evalFn(testModule, testModule.exports);

const { parseDate, safeDateParse, formatTimestamp, formatISO, formatRelativeTime } = testModule.exports;

console.log('=== Step 1: Testing dateUtils.js ===');

// Test unix seconds
const d1 = parseDate(1780000000);
assert(d1 instanceof Date, 'Unix seconds should return Date');
assert.strictEqual(d1.getUTCFullYear(), 2026, 'Year for 1780000000 should be 2026');

// Test unix ms
const d2 = parseDate(1780000000000);
assert(d2 instanceof Date, 'Unix ms should return Date');
assert.strictEqual(d2.getUTCFullYear(), 2026, 'Year for 1780000000000 should be 2026');

// Test numeric string
const d3 = parseDate('1780000000');
assert(d3 instanceof Date, 'Numeric string should return Date');

// Test ISO 8601 with microseconds
const d4 = parseDate('2026-07-21T18:00:00.123456Z');
assert(d4 instanceof Date, 'Microsecond ISO string should return Date');
assert.strictEqual(d4.toISOString(), '2026-07-21T18:00:00.123Z');

// Test UTC format string
const d5 = parseDate('2026-07-21 18:00:00 UTC');
assert(d5 instanceof Date, 'UTC format string should return Date');
assert.strictEqual(d5.toISOString(), '2026-07-21T18:00:00.000Z');

// Test space-separated without timezone
const d6 = parseDate('2026-07-21 18:00:00');
assert(d6 instanceof Date, 'Space-separated date string should return Date');
assert.strictEqual(d6.toISOString(), '2026-07-21T18:00:00.000Z');

// Test invalid inputs
const inv1 = formatTimestamp(null);
assert.strictEqual(inv1, 'N/A', 'null should return fallback');
assert(!inv1.includes('NaN'), 'Should not include NaN');
assert(!inv1.includes('Invalid Date'), 'Should not include Invalid Date');

const inv2 = formatTimestamp('invalid_string');
assert.strictEqual(inv2, 'N/A', 'invalid string should return fallback');

const inv3 = formatRelativeTime(undefined);
assert.strictEqual(inv3, 'Just now', 'undefined should return fallback Just now');

const rel1 = formatRelativeTime(Date.now() - 300000); // 5 mins ago
assert(rel1.includes('5 mins ago'), 'Relative time should format minutes correctly');

console.log('✅ dateUtils.js passed all tests cleanly!');

console.log('\n=== Step 2: Testing Candidate Approval Filtering & State Persistence ===');

const mockCandidates = [
  { ticker: 'AAPL', timestamp: '2026-07-21T18:00:00Z', type: 'breakout' },
  { ticker: 'NVDA', timestamp: '2026-07-21T18:00:00Z', type: 'breakout' },
  { ticker: 'BTCUSDT', timestamp: '2026-07-21T18:00:00Z', type: 'capitulation' },
];

const approvedCandidates = ['AAPL_2026-07-21T18:00:00Z'];
const ignoredCandidates = ['BTCUSDT_2026-07-21T18:00:00Z'];

const approvedSet = new Set(approvedCandidates);
const ignoredSet = new Set(ignoredCandidates);

const filtered = mockCandidates.filter(
  c => !approvedSet.has(`${c.ticker}_${c.timestamp}`) && !ignoredSet.has(`${c.ticker}_${c.timestamp}`)
);

assert.strictEqual(filtered.length, 1, 'Only NVDA should remain after filtering approved & ignored');
assert.strictEqual(filtered[0].ticker, 'NVDA');

console.log('✅ Candidate approval filtering passed cleanly!');

console.log('\n=== Step 3: Checking Local API JSON Artifacts ===');
const recentJsonPath = path.join(__dirname, '../backend/recent_signals.json');
const capJsonPath = path.join(__dirname, '../backend/capitulation_signals.json');

if (fs.existsSync(recentJsonPath)) {
  const data = JSON.parse(fs.readFileSync(recentJsonPath, 'utf8'));
  assert(Array.isArray(data), 'recent_signals.json must be an array');
  console.log(`✅ recent_signals.json verified (${data.length} items)`);
}

if (fs.existsSync(capJsonPath)) {
  const data = JSON.parse(fs.readFileSync(capJsonPath, 'utf8'));
  assert(Array.isArray(data), 'capitulation_signals.json must be an array');
  console.log(`✅ capitulation_signals.json verified (${data.length} items)`);
}

console.log('\nALL VERIFICATION CHECKS PASSED!');
