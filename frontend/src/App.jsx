import React, { useState, useEffect } from 'react';
import KPICards from './components/KPICards';
import CandidatePanel from './components/CandidatePanel';
import AnalyticsChart from './components/AnalyticsChart';
import OpenPositions from './components/OpenPositions';
import TradeHistory from './components/TradeHistory';

// Import raw mock data
import {
  candidates as initialCandidates,
  kpis as initialKpis,
  openPositions as initialOpenPositions,
  tradeHistory as initialTradeHistory,
  dailyAnalytics
} from './data/mockData';

export default function App() {
  const [candidates, setCandidates] = useState(initialCandidates);
  const [openPositions, setOpenPositions] = useState(initialOpenPositions);
  const [tradeHistory, setTradeHistory] = useState(initialTradeHistory);
  const [kpis, setKpis] = useState(initialKpis);
  const [time, setTime] = useState(new Date());

  // Real-time clock update
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Handler to approve a breakout signal (move candidate to open positions)
  const handleApprove = (candidate) => {
    // 1. Create a new open position
    const newPosition = {
      id: Date.now(),
      ticker: candidate.ticker,
      market: candidate.market,
      direction: candidate.direction,
      entry: candidate.entry,
      current: candidate.entry, // starts at entry price
      stopLoss: candidate.stopLoss,
      takeProfit: candidate.takeProfit,
      brokenLevel: candidate.brokenLevel,
      entryTime: new Date().toISOString().replace('T', ' ').substring(0, 16),
      pnl: 0.00,
      pnlPct: 0.00
    };

    setOpenPositions([newPosition, ...openPositions]);

    // 2. Remove from candidates panel
    setCandidates(candidates.filter((c) => c.id !== candidate.id));

    // 3. Update KPIs (increase active trade count, etc.)
    setKpis((prev) => ({
      ...prev,
      totalTrades: prev.totalTrades + 1
    }));
  };

  // Handler to reject/ignore a candidate signal
  const handleReject = (id) => {
    setCandidates(candidates.filter((c) => c.id !== id));
  };

  // Handler to close an open position (move it to closed trade history)
  const handleClosePosition = (id) => {
    const position = openPositions.find((p) => p.id === id);
    if (!position) return;

    // Simulate exit price near current or take profit/stop loss randomly
    const isWin = Math.random() > 0.35; // 65% win rate simulation
    const exitPrice = isWin ? position.takeProfit : position.stopLoss;
    const risk = Math.abs(position.entry - position.stopLoss);
    const pnl = isWin ? (risk * 2) * 50 : -risk * 50; // scaled simulated dollar pnl
    const pnlPct = ((exitPrice - position.entry) / position.entry) * (position.direction === 'LONG' ? 100 : -100);

    // 1. Create closed trade object
    const closedTrade = {
      id: Date.now(),
      ticker: position.ticker,
      market: position.market,
      direction: position.direction,
      entry: position.entry,
      exit: exitPrice,
      brokenLevel: position.brokenLevel,
      entryTime: position.entryTime,
      exitTime: new Date().toISOString().replace('T', ' ').substring(0, 16),
      pnl: pnl,
      pnlPct: pnlPct,
      result: isWin ? 'WIN' : 'LOSS'
    };

    setTradeHistory([closedTrade, ...tradeHistory]);

    // 2. Remove from open positions
    setOpenPositions(openPositions.filter((p) => p.id !== id));

    // 3. Recalculate KPIs based on the trade outcome
    setKpis((prev) => {
      const newWinningTrades = isWin ? prev.winningTrades + 1 : prev.winningTrades;
      const newLosingTrades = !isWin ? prev.losingTrades + 1 : prev.losingTrades;
      const newTotal = prev.totalTrades;
      const newWinRate = (newWinningTrades / newTotal) * 100;
      const newPnL = prev.todayPnL + pnl;

      return {
        ...prev,
        todayPnL: newPnL,
        todayPnLPct: (newPnL / 200000) * 100, // assume $200k base capital
        winRate: newWinRate,
        winningTrades: newWinningTrades,
        losingTrades: newLosingTrades
      };
    });
  };

  return (
    <div className="min-h-screen bg-[#0a0e17] text-slate-100 font-sans selection:bg-cyan-500/30 selection:text-cyan-200">
      
      {/* Background ambient glows */}
      <div className="fixed top-0 left-1/4 w-[500px] h-[500px] bg-blue-900/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="fixed bottom-0 right-1/4 w-[600px] h-[600px] bg-cyan-900/10 rounded-full blur-[140px] pointer-events-none" />

      {/* Main Container */}
      <div className="max-w-7xl mx-auto px-4 py-8 relative z-10 space-y-6">
        
        {/* Header Section */}
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-900">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-cyan-400 to-indigo-400 bg-clip-text text-transparent drop-shadow-sm">
              Breakout Scanner
            </h1>
            <p className="text-sm text-slate-400 mt-1.5 font-medium">
              Multi-Market Volume-Confirmed Breakout Detection System
            </p>
          </div>
          
          <div className="flex items-center gap-4 mt-4 md:mt-0 bg-slate-900/50 px-4 py-2 rounded-xl border border-slate-800/80 backdrop-blur-md">
            {/* Live Indicator */}
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse drop-shadow-[0_0_8px_rgba(16,185,129,0.6)]" />
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Live Scanner</span>
            </div>
            
            <div className="h-4 w-[1px] bg-slate-800" />
            
            {/* Live clock */}
            <span className="text-sm font-semibold text-slate-200 tracking-wide font-mono">
              {time.toLocaleTimeString('en-US', { hour12: false })}
            </span>
          </div>
        </header>

        {/* Global KPIs cards row */}
        <section className="w-full">
          <KPICards kpis={kpis} />
        </section>

        {/* Primary Dashboard Content (Grid: Candidates + SVG Chart) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <section className="lg:col-span-2">
            <CandidatePanel
              candidates={candidates}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          </section>
          
          <section className="lg:col-span-1">
            <AnalyticsChart data={dailyAnalytics} />
          </section>
        </div>

        {/* Open Positions monitoring */}
        <section className="w-full">
          <OpenPositions
            positions={openPositions}
            onClosePosition={handleClosePosition}
          />
        </section>

        {/* Trade history log */}
        <section className="w-full">
          <TradeHistory history={tradeHistory} />
        </section>
        
      </div>
    </div>
  );
}
