// Today's candidates (recently qualified breakouts)
export const candidates = [
  { id: 1, ticker: 'NVDA', market: 'US Equities', direction: 'LONG', brokenLevel: 142.80, entry: 143.25, stopLoss: 141.50, takeProfit: 146.75, volumeRatio: 2.3, atr: 1.85, timestamp: '2026-07-12 14:01 UTC', status: 'pending' },
  { id: 2, ticker: 'BTCUSDT', market: 'Crypto', direction: 'LONG', brokenLevel: 98500.00, entry: 98750.00, stopLoss: 97800.00, takeProfit: 100650.00, volumeRatio: 1.8, atr: 450.00, timestamp: '2026-07-12 13:01 UTC', status: 'approved' },
  { id: 3, ticker: 'AAPL', market: 'US Equities', direction: 'SHORT', brokenLevel: 198.50, entry: 197.80, stopLoss: 199.70, takeProfit: 194.00, volumeRatio: 1.6, atr: 1.20, timestamp: '2026-07-12 15:01 UTC', status: 'pending' },
  { id: 4, ticker: 'ETHUSDT', market: 'Crypto', direction: 'LONG', brokenLevel: 3850.00, entry: 3875.00, stopLoss: 3780.00, takeProfit: 4065.00, volumeRatio: 2.1, atr: 55.00, timestamp: '2026-07-12 12:01 UTC', status: 'approved' },
  { id: 5, ticker: 'TSLA', market: 'US Equities', direction: 'LONG', brokenLevel: 285.00, entry: 286.50, stopLoss: 283.00, takeProfit: 293.50, volumeRatio: 1.9, atr: 3.10, timestamp: '2026-07-12 14:01 UTC', status: 'pending' },
];

// KPIs
export const kpis = {
  todayPnL: 4285.50,
  todayPnLPct: 2.14,
  winRate: 68.5,
  totalTrades: 23,
  winningTrades: 16,
  losingTrades: 7,
  avgWin: 485.30,
  avgLoss: -210.75,
  sharpeRatio: 1.82,
};

// Open positions
export const openPositions = [
  { id: 1, ticker: 'NVDA', market: 'US Equities', direction: 'LONG', entry: 143.25, current: 145.80, stopLoss: 141.50, takeProfit: 146.75, brokenLevel: 142.80, entryTime: '2026-07-12 14:01', pnl: 255.00, pnlPct: 1.78 },
  { id: 2, ticker: 'BTCUSDT', market: 'Crypto', direction: 'LONG', entry: 98750.00, current: 99200.00, stopLoss: 97800.00, takeProfit: 100650.00, brokenLevel: 98500.00, entryTime: '2026-07-12 13:01', pnl: 450.00, pnlPct: 0.46 },
  { id: 3, ticker: 'META', market: 'US Equities', direction: 'SHORT', entry: 520.30, current: 518.50, stopLoss: 525.80, takeProfit: 509.30, brokenLevel: 521.00, entryTime: '2026-07-12 10:01', pnl: 180.00, pnlPct: 0.35 },
  { id: 4, ticker: 'SOLUSDT', market: 'Crypto', direction: 'LONG', entry: 185.50, current: 188.20, stopLoss: 182.00, takeProfit: 192.50, brokenLevel: 185.00, entryTime: '2026-07-12 11:01', pnl: 270.00, pnlPct: 1.46 },
];

// Trade history (closed trades)
export const tradeHistory = [
  { id: 1, ticker: 'GOOGL', market: 'US Equities', direction: 'LONG', entry: 178.50, exit: 183.20, stopLoss: 176.00, takeProfit: 183.50, brokenLevel: 178.00, entryTime: '2026-07-11 10:01', exitTime: '2026-07-11 15:01', pnl: 470.00, pnlPct: 2.63, result: 'WIN' },
  { id: 2, ticker: 'BTCUSDT', market: 'Crypto', direction: 'SHORT', entry: 97200.00, exit: 97800.00, stopLoss: 97900.00, takeProfit: 95800.00, brokenLevel: 97300.00, entryTime: '2026-07-11 08:01', exitTime: '2026-07-11 12:01', pnl: -600.00, pnlPct: -0.62, result: 'LOSS' },
  { id: 3, ticker: 'AMZN', market: 'US Equities', direction: 'LONG', entry: 198.75, exit: 203.40, stopLoss: 196.50, takeProfit: 203.25, brokenLevel: 198.50, entryTime: '2026-07-10 14:01', exitTime: '2026-07-11 10:01', pnl: 465.00, pnlPct: 2.34, result: 'WIN' },
  { id: 4, ticker: 'ETHUSDT', market: 'Crypto', direction: 'LONG', entry: 3780.00, exit: 3920.00, stopLoss: 3720.00, takeProfit: 3900.00, brokenLevel: 3770.00, entryTime: '2026-07-10 06:01', exitTime: '2026-07-10 18:01', pnl: 1400.00, pnlPct: 3.70, result: 'WIN' },
  { id: 5, ticker: 'TSLA', market: 'US Equities', direction: 'LONG', entry: 278.50, exit: 275.80, stopLoss: 275.00, takeProfit: 285.50, brokenLevel: 278.00, entryTime: '2026-07-10 10:01', exitTime: '2026-07-10 14:01', pnl: -270.00, pnlPct: -0.97, result: 'LOSS' },
  { id: 6, ticker: 'BNBUSDT', market: 'Crypto', direction: 'LONG', entry: 625.00, exit: 641.50, stopLoss: 618.00, takeProfit: 639.00, brokenLevel: 624.00, entryTime: '2026-07-09 22:01', exitTime: '2026-07-10 04:01', pnl: 1650.00, pnlPct: 2.64, result: 'WIN' },
  { id: 7, ticker: 'MSFT', market: 'US Equities', direction: 'SHORT', entry: 445.20, exit: 442.10, stopLoss: 448.00, takeProfit: 439.60, brokenLevel: 445.80, entryTime: '2026-07-09 11:01', exitTime: '2026-07-09 15:01', pnl: 310.00, pnlPct: 0.70, result: 'WIN' },
  { id: 8, ticker: 'ADAUSDT', market: 'Crypto', direction: 'SHORT', entry: 0.4850, exit: 0.4920, stopLoss: 0.4950, takeProfit: 0.4650, brokenLevel: 0.4870, entryTime: '2026-07-09 16:01', exitTime: '2026-07-09 20:01', pnl: -70.00, pnlPct: -1.44, result: 'LOSS' },
];

// Analytics data (wins vs losses per day)
export const dailyAnalytics = [
  { day: 'Mon', wins: 3, losses: 1 },
  { day: 'Tue', wins: 4, losses: 2 },
  { day: 'Wed', wins: 2, losses: 1 },
  { day: 'Thu', wins: 5, losses: 2 },
  { day: 'Fri', wins: 2, losses: 1 },
];
