import assert from 'assert';

console.log('====================================================');
console.log('CHALLENGER M4.1 — EMPIRICAL SUITE FOR App.jsx FILTERING');
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

// Simulated LocalStorage mock
class LocalStorageMock {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return this.store[key] || null;
  }
  setItem(key, value) {
    this.store[key] = String(value);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

const mockLocalStorage = new LocalStorageMock();

// Pure implementation of App.jsx candidate filtering logic
function filterIncomingCandidates(incomingData, currentCandidates, localStorage) {
  const existingIds = new Set(currentCandidates.map(c => `${c.ticker}_${c.timestamp}`));
  const savedOpen = JSON.parse(localStorage.getItem('openPositions') || '[]');
  const openIds = new Set(savedOpen.map(p => p.ticker));
  const savedIgnored = JSON.parse(localStorage.getItem('ignoredCandidates') || '[]');
  const ignoredSet = new Set(savedIgnored);
  const savedApproved = JSON.parse(localStorage.getItem('approvedCandidates') || '[]');
  const approvedSet = new Set(savedApproved);

  const newCandidates = incomingData
    .map((c, index) => {
      const isRadar = c.type === 'radar' || c.entry_price === undefined;
      const entryVal = isRadar ? c.price : c.entry_price;
      const directionVal = c.direction === 'UP' ? 'LONG' : (c.direction === 'DOWN' ? 'SHORT' : c.direction);
      return {
        id: c.id || `fetched_${c.ticker}_${c.timestamp}_${index}`,
        ticker: c.ticker,
        timestamp: c.timestamp,
        entry: entryVal,
        direction: directionVal,
        inPosition: openIds.has(c.ticker)
      };
    })
    .filter(c => !existingIds.has(`${c.ticker}_${c.timestamp}`) && 
                 !ignoredSet.has(`${c.ticker}_${c.timestamp}`) &&
                 !approvedSet.has(`${c.ticker}_${c.timestamp}`));

  return [...currentCandidates, ...newCandidates];
}

// Pure implementation of App.jsx capitulation filtering logic
function filterIncomingCapitulation(incomingData, localStorage) {
  const savedIgnored = JSON.parse(localStorage.getItem('ignoredCandidates') || '[]');
  const ignoredSet = new Set(savedIgnored);
  const savedApproved = JSON.parse(localStorage.getItem('approvedCandidates') || '[]');
  const approvedSet = new Set(savedApproved);
  const savedOpen = JSON.parse(localStorage.getItem('openPositions') || '[]');
  const openIds = new Set(savedOpen.map(p => p.ticker));

  return incomingData
    .map((c, index) => ({
      id: c.id || `cap_${c.ticker}_${c.timestamp}_${index}`,
      ticker: c.ticker,
      timestamp: c.timestamp,
      entry: c.entry_price || 0,
      inPosition: openIds.has(c.ticker)
    }))
    .filter(c => !ignoredSet.has(`${c.ticker}_${c.timestamp}`) && !approvedSet.has(`${c.ticker}_${c.timestamp}`));
}

// Simulation Test 1: Fresh Candidates Load
runTest('Initial fetch loads candidates into state', () => {
  mockLocalStorage.clear();
  const apiData = [
    { ticker: 'BTCUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 65000, direction: 'UP' },
    { ticker: 'ETHUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 3400, direction: 'UP' }
  ];

  const state1 = filterIncomingCandidates(apiData, [], mockLocalStorage);
  assert.strictEqual(state1.length, 2);
  assert.strictEqual(state1[0].ticker, 'BTCUSDT');
  assert.strictEqual(state1[1].ticker, 'ETHUSDT');
});

// Simulation Test 2: Approve Candidate & Polling Refetch
runTest('Approved candidate key persisted in localStorage is excluded on polling refetch', () => {
  mockLocalStorage.clear();
  const apiData = [
    { ticker: 'BTCUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 65000, direction: 'UP' },
    { ticker: 'ETHUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 3400, direction: 'UP' }
  ];

  // User approves BTCUSDT
  const approvedKey = 'BTCUSDT_2026-07-21T18:00:00Z';
  mockLocalStorage.setItem('approvedCandidates', JSON.stringify([approvedKey]));

  // Current candidates state after user approved BTC (only ETHUSDT remains in panel)
  const currentCandidates = [
    { id: 'ETHUSDT_id', ticker: 'ETHUSDT', timestamp: '2026-07-21T18:00:00Z', entry: 3400, direction: 'LONG' }
  ];

  // Polling refetch 2 minutes later
  const stateAfterPoll = filterIncomingCandidates(apiData, currentCandidates, mockLocalStorage);
  
  assert.strictEqual(stateAfterPoll.length, 1, 'Only ETHUSDT should be in candidate list');
  assert.strictEqual(stateAfterPoll[0].ticker, 'ETHUSDT');
  assert(!stateAfterPoll.some(c => c.ticker === 'BTCUSDT'), 'Approved BTCUSDT candidate MUST NOT reappear');
});

// Simulation Test 3: Reject Candidate & Polling Refetch
runTest('Rejected candidate key persisted in localStorage is excluded on polling refetch', () => {
  mockLocalStorage.clear();
  const apiData = [
    { ticker: 'BTCUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 65000, direction: 'UP' },
    { ticker: 'ETHUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 3400, direction: 'UP' }
  ];

  // User rejects ETHUSDT
  const ignoredKey = 'ETHUSDT_2026-07-21T18:00:00Z';
  mockLocalStorage.setItem('ignoredCandidates', JSON.stringify([ignoredKey]));

  const currentCandidates = [
    { id: 'BTCUSDT_id', ticker: 'BTCUSDT', timestamp: '2026-07-21T18:00:00Z', entry: 65000, direction: 'LONG' }
  ];

  // Polling refetch
  const stateAfterPoll = filterIncomingCandidates(apiData, currentCandidates, mockLocalStorage);

  assert.strictEqual(stateAfterPoll.length, 1);
  assert.strictEqual(stateAfterPoll[0].ticker, 'BTCUSDT');
  assert(!stateAfterPoll.some(c => c.ticker === 'ETHUSDT'), 'Rejected ETHUSDT candidate MUST NOT reappear');
});

// Simulation Test 4: Capitulation Signal Persistence & Filtering
runTest('Approved/Rejected keys filter out capitulation signals on refetch', () => {
  mockLocalStorage.clear();
  const capData = [
    { ticker: 'SOLUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 140 },
    { ticker: 'AVAUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 25 }
  ];

  // SOL approved, AVA ignored
  mockLocalStorage.setItem('approvedCandidates', JSON.stringify(['SOLUSDT_2026-07-21T18:00:00Z']));
  mockLocalStorage.setItem('ignoredCandidates', JSON.stringify(['AVAUSDT_2026-07-21T18:00:00Z']));

  const capState = filterIncomingCapitulation(capData, mockLocalStorage);

  assert.strictEqual(capState.length, 0, 'Both approved SOL and ignored AVA should be filtered out');
});

// Simulation Test 5: New Signal Arrival
runTest('New candidate signal with different timestamp or ticker is allowed through', () => {
  mockLocalStorage.clear();
  mockLocalStorage.setItem('approvedCandidates', JSON.stringify(['BTCUSDT_2026-07-21T18:00:00Z']));

  const newApiData = [
    { ticker: 'BTCUSDT', timestamp: '2026-07-21T18:00:00Z', entry_price: 65000, direction: 'UP' }, // Old approved
    { ticker: 'BTCUSDT', timestamp: '2026-07-21T18:05:00Z', entry_price: 66000, direction: 'UP' }, // New signal!
  ];

  const state = filterIncomingCandidates(newApiData, [], mockLocalStorage);
  assert.strictEqual(state.length, 1);
  assert.strictEqual(state[0].timestamp, '2026-07-21T18:05:00Z');
});

console.log('\n----------------------------------------------------');
console.log(`SUMMARY: ${passCount} Passed, ${failCount} Failed.`);
console.log('----------------------------------------------------');

if (failCount > 0) {
  process.exit(1);
}
