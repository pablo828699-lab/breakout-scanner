import { parseDate, safeDateParse, formatTimestamp, formatISO, formatRelativeTime } from '../../frontend/src/utils/dateUtils.js';
import assert from 'assert';

console.log('====================================================');
console.log('CHALLENGER M4.1 — EMPIRICAL SUITE FOR dateUtils.js');
console.log('====================================================\n');

let passCount = 0;
let failCount = 0;

function runTest(description, fn) {
  try {
    fn();
    console.log(`[PASS] ${description}`);
    passCount++;
  } catch (err) {
    console.error(`[FAIL] ${description}: ${err.message}`);
    failCount++;
  }
}

// Group 1: Null / Undefined / Empty / Non-String Non-Number Types
runTest('Null input to parseDate returns null', () => {
  assert.strictEqual(parseDate(null), null);
});

runTest('Undefined input to parseDate returns null', () => {
  assert.strictEqual(parseDate(undefined), null);
});

runTest('Empty string to parseDate returns null', () => {
  assert.strictEqual(parseDate(''), null);
});

runTest('Whitespace string to parseDate returns null', () => {
  assert.strictEqual(parseDate('   '), null);
});

runTest('Boolean false to parseDate returns null', () => {
  assert.strictEqual(parseDate(false), null);
});

runTest('Boolean true to parseDate returns null', () => {
  assert.strictEqual(parseDate(true), null);
});

runTest('Object input to parseDate returns null', () => {
  assert.strictEqual(parseDate({ key: 'val' }), null);
});

runTest('Array input to parseDate returns null', () => {
  assert.strictEqual(parseDate([123, 456]), null);
});

runTest('NaN number to parseDate returns null', () => {
  assert.strictEqual(parseDate(NaN), null);
});

runTest('Infinity to parseDate returns null', () => {
  assert.strictEqual(parseDate(Infinity), null);
});

// Group 2: Malformed & Garbage Strings
runTest('Arbitrary text "hello world" returns null', () => {
  assert.strictEqual(parseDate('hello world'), null);
});

runTest('Malformed date "2026-99-99T99:99:99" returns null', () => {
  assert.strictEqual(parseDate('2026-99-99T99:99:99'), null);
});

runTest('JSON string "{foo:123}" returns null', () => {
  assert.strictEqual(parseDate('{foo:123}'), null);
});

runTest('Extremely long numeric string returns null without crashing', () => {
  assert.strictEqual(parseDate('99999999999999999999999999999'), null);
});

// Group 3: Unix Timestamps (Numbers & String Numbers)
runTest('Unix timestamp in seconds (number: 1780000000)', () => {
  const res = parseDate(1780000000);
  assert(res instanceof Date);
  assert.strictEqual(res.getUTCFullYear(), 2026);
});

runTest('Unix timestamp in milliseconds (number: 1780000000000)', () => {
  const res = parseDate(1780000000000);
  assert(res instanceof Date);
  assert.strictEqual(res.getUTCFullYear(), 2026);
});

runTest('Unix timestamp in seconds (string: "1780000000")', () => {
  const res = parseDate('1780000000');
  assert(res instanceof Date);
  assert.strictEqual(res.getUTCFullYear(), 2026);
});

runTest('Unix timestamp in milliseconds (string: "1780000000000")', () => {
  const res = parseDate('1780000000000');
  assert(res instanceof Date);
  assert.strictEqual(res.getUTCFullYear(), 2026);
});

runTest('Unix timestamp zero (number: 0)', () => {
  const res = parseDate(0);
  assert(res instanceof Date);
  assert.strictEqual(res.getTime(), 0);
});

runTest('Unix timestamp zero (string: "0")', () => {
  const res = parseDate('0');
  assert(res instanceof Date);
  assert.strictEqual(res.getTime(), 0);
});

runTest('Unix timestamp decimal seconds string ("1780000000.123")', () => {
  const res = parseDate('1780000000.123');
  assert(res instanceof Date);
  assert.strictEqual(res.getUTCFullYear(), 2026);
});

// Group 4: ISO 8601 & Microsecond ISO Strings
runTest('Standard ISO 8601 string ("2026-07-21T18:00:00Z")', () => {
  const res = parseDate('2026-07-21T18:00:00Z');
  assert(res instanceof Date);
  assert.strictEqual(res.toISOString(), '2026-07-21T18:00:00.000Z');
});

runTest('Microsecond ISO string ("2026-07-21T18:00:00.123456Z")', () => {
  const res = parseDate('2026-07-21T18:00:00.123456Z');
  assert(res instanceof Date);
  assert.strictEqual(res.toISOString(), '2026-07-21T18:00:00.123Z');
});

runTest('Microsecond string without T or Z ("2026-07-21 18:00:00.123456")', () => {
  const res = parseDate('2026-07-21 18:00:00.123456');
  assert(res instanceof Date);
  assert.strictEqual(res.toISOString(), '2026-07-21T18:00:00.123Z');
});

runTest('UTC format string ("2026-07-21 18:00:00 UTC")', () => {
  const res = parseDate('2026-07-21 18:00:00 UTC');
  assert(res instanceof Date);
  assert.strictEqual(res.toISOString(), '2026-07-21T18:00:00.000Z');
});

runTest('Space separated UTC string ("2026-07-21 18:00:00")', () => {
  const res = parseDate('2026-07-21 18:00:00');
  assert(res instanceof Date);
  assert.strictEqual(res.toISOString(), '2026-07-21T18:00:00.000Z');
});

// Group 5: Formatting Functions Edge Cases & No NaN/Invalid Date Guarantee
runTest('formatTimestamp returns fallback for null/undefined/invalid without NaN/Invalid Date', () => {
  const f1 = formatTimestamp(null);
  const f2 = formatTimestamp(undefined);
  const f3 = formatTimestamp('invalid');
  assert.strictEqual(f1, 'N/A');
  assert.strictEqual(f2, 'N/A');
  assert.strictEqual(f3, 'N/A');
  assert(!f1.includes('NaN') && !f1.includes('Invalid Date'));
  assert(!f2.includes('NaN') && !f2.includes('Invalid Date'));
  assert(!f3.includes('NaN') && !f3.includes('Invalid Date'));
});

runTest('formatISO returns fallback for invalid inputs', () => {
  assert.strictEqual(formatISO(null), 'N/A');
  assert.strictEqual(formatISO('invalid'), 'N/A');
  assert.strictEqual(formatISO(undefined, 'FALLBACK'), 'FALLBACK');
});

runTest('formatRelativeTime returns fallback "Just now" for null/undefined/invalid', () => {
  assert.strictEqual(formatRelativeTime(null), 'Just now');
  assert.strictEqual(formatRelativeTime(undefined), 'Just now');
  assert.strictEqual(formatRelativeTime('invalid'), 'Just now');
});

runTest('formatRelativeTime handles recent past dates correctly', () => {
  const now = Date.now();
  assert.strictEqual(formatRelativeTime(now - 5000), 'Just now');
  assert.strictEqual(formatRelativeTime(now - 30000), '30 secs ago');
  assert.strictEqual(formatRelativeTime(now - 300000), '5 mins ago');
  assert.strictEqual(formatRelativeTime(now - 7200000), '2 hours ago');
});

runTest('safeDateParse returns fallbackMs when invalid', () => {
  const fallback = 123456789;
  assert.strictEqual(safeDateParse(null, fallback), fallback);
  assert.strictEqual(safeDateParse('garbage', fallback), fallback);
  const validMs = safeDateParse('2026-07-21T18:00:00Z', fallback);
  assert.strictEqual(validMs, new Date('2026-07-21T18:00:00Z').getTime());
});

console.log('\n----------------------------------------------------');
console.log(`SUMMARY: ${passCount} Passed, ${failCount} Failed.`);
console.log('----------------------------------------------------');

if (failCount > 0) {
  process.exit(1);
}
