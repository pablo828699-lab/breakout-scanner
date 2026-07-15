import React, { useState, useEffect } from 'react';
import KPICards from './components/KPICards';
import CandidatePanel from './components/CandidatePanel';
import AnalyticsChart from './components/AnalyticsChart';
import OpenPositions from './components/OpenPositions';
import TradeHistory from './components/TradeHistory';

// Import fallback mock data in case localStorage is empty initially
import {
  candidates as fallbackCandidates,
  kpis as fallbackKpis,
  openPositions as fallbackOpenPositions,
  tradeHistory as fallbackTradeHistory,
  dailyAnalytics
} from './data/mockData';

const BACKEND_URL = 'https://breakout-scanner-xg9f.onrender.com';

export default function App() {
  const [candidates, setCandidates] = useState(() => {
    const saved = localStorage.getItem('candidates');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [openPositions, setOpenPositions] = useState(() => {
    const saved = localStorage.getItem('openPositions');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [tradeHistory, setTradeHistory] = useState(() => {
    const saved = localStorage.getItem('tradeHistory');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [kpis, setKpis] = useState(() => {
    const saved = localStorage.getItem('kpis');
    return saved ? JSON.parse(saved) : {
      todayPnL: 0,
      todayPnLPct: 0,
      winRate: 0,
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      avgWin: 0,
      avgLoss: 0,
      sharpeRatio: 0
    };
  });

  const [capitalPerTrade, setCapitalPerTrade] = useState(() => {
    const saved = localStorage.getItem('capitalPerTrade');
    return saved ? Number(saved) : 1000;
  });

  const [accountBalance, setAccountBalance] = useState(() => {
    const saved = localStorage.getItem('accountBalance');
    return saved ? Number(saved) : 100000;
  });

  const [ignoredCandidates, setIgnoredCandidates] = useState(() => {
    const saved = localStorage.getItem('ignoredCandidates');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [time, setTime] = useState(new Date());
  const [isScanning, setIsScanning] = useState(false);
  const [approveModalCandidate, setApproveModalCandidate] = useState(null);
  const [approveModalSize, setApproveModalSize] = useState(1000);

  // Real-time clock update
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Sync state changes with localStorage
  useEffect(() => {
    localStorage.setItem('candidates', JSON.stringify(candidates));
  }, [candidates]);

  useEffect(() => {
    localStorage.setItem('openPositions', JSON.stringify(openPositions));
  }, [openPositions]);

  useEffect(() => {
    localStorage.setItem('tradeHistory', JSON.stringify(tradeHistory));
  }, [tradeHistory]);

  useEffect(() => {
    localStorage.setItem('kpis', JSON.stringify(kpis));
  }, [kpis]);

  useEffect(() => {
    localStorage.setItem('capitalPerTrade', capitalPerTrade.toString());
  }, [capitalPerTrade]);

  useEffect(() => {
    localStorage.setItem('accountBalance', accountBalance.toString());
  }, [accountBalance]);

  useEffect(() => {
    localStorage.setItem('ignoredCandidates', JSON.stringify(ignoredCandidates));
  }, [ignoredCandidates]);

  // Simulate minor price fluctuations for active open positions to bring the dashboard to life
  useEffect(() => {
    if (openPositions.length === 0) return;

    const timer = setInterval(() => {
      setOpenPositions((prevPositions) =>
        prevPositions.map((pos) => {
          // Volatility fluctuation: between -0.12% and +0.12%
          const changePct = (Math.random() - 0.5) * 0.0024;
          const nextPrice = pos.current * (1 + changePct);
          return {
            ...pos,
            current: Math.max(0.000001, nextPrice)
          };
        })
      );
    }, 4000);

    return () => clearInterval(timer);
  }, [openPositions.length]);

  // Fetch actual candidates from Render backend
  useEffect(() => {
    const fetchCandidates = async () => {
      try {
        const resp = await fetch(`${BACKEND_URL}/api/candidates`);
        if (!resp.ok) throw new Error('Backend response was not ok');
        const data = await resp.json();
        
        setCandidates((prevCandidates) => {
          const existingIds = new Set(prevCandidates.map(c => `${c.ticker}_${c.timestamp}`));
          const savedOpen = JSON.parse(localStorage.getItem('openPositions') || '[]');
          const openIds = new Set(savedOpen.map(p => p.ticker));
          const savedIgnored = JSON.parse(localStorage.getItem('ignoredCandidates') || '[]');
          const ignoredSet = new Set(savedIgnored);
          
          const newCandidates = data
            .map((c, index) => {
              const isRadar = c.type === 'radar' || c.entry_price === undefined;
              const entryVal = isRadar ? c.price : c.entry_price;
              const directionVal = c.direction === 'UP' ? 'LONG' : (c.direction === 'DOWN' ? 'SHORT' : c.direction);
              
              // Calculate default SL and TP for radar signals (1:2 Risk/Reward)
              let slVal = c.stop_loss;
              let tpVal = c.take_profit;
              
              if (isRadar || !slVal || !tpVal) {
                const isCrypto = c.market === 'CRYPTO';
                // 2% for stocks, 5% for crypto
                const slPct = isCrypto ? 0.05 : 0.02;
                const tpPct = slPct * 2.0; // 1:2 R:R
                
                if (directionVal === 'LONG') {
                  slVal = entryVal * (1 - slPct);
                  tpVal = entryVal * (1 + tpPct);
                } else {
                  slVal = entryVal * (1 + slPct);
                  tpVal = entryVal * (1 - tpPct);
                }
              }

              return {
                id: c.id || `fetched_${c.ticker}_${Date.parse(c.timestamp)}_${index}`,
                ticker: c.ticker,
                market: c.market === 'US_EQUITIES' ? 'US Equities' : 'Crypto',
                direction: directionVal,
                brokenLevel: isRadar ? entryVal : c.broken_level,
                entry: entryVal,
                stopLoss: slVal,
                takeProfit: tpVal,
                volumeRatio: c.volume_ratio,
                atr: c.atr_value || (entryVal * (c.market === 'CRYPTO' ? 0.05 : 0.02)),
                timestamp: c.timestamp,
                status: 'pending'
              };
            })
            .filter(c => !existingIds.has(`${c.ticker}_${c.timestamp}`) && 
                         !openIds.has(c.ticker) &&
                         !ignoredSet.has(`${c.ticker}_${c.timestamp}`));
            
          return [...prevCandidates, ...newCandidates];
        });
      } catch (err) {
        console.error('Failed to fetch candidates from backend:', err);
      }
    };

    fetchCandidates();
    // Poll every 2 minutes
    const interval = setInterval(fetchCandidates, 2 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // Force manual scan trigger protected by PIN
  const handleForceScan = async () => {
    if (isScanning) return;

    const pin = prompt('Ingrese la clave de seguridad para iniciar el escaneo:');
    if (pin !== '1234') {
      alert('Clave incorrecta. Escaneo cancelado.');
      return;
    }

    setIsScanning(true);
    try {
      const resp = await fetch(`${BACKEND_URL}/scan`);
      if (resp.ok) {
        alert('Escaneo iniciado en segundo plano. Espera 1 minuto y recarga la página para verificar nuevas señales.');
      } else {
        alert('El servidor respondió con error al iniciar el escaneo.');
      }
    } catch (err) {
      console.error(err);
      alert('Error de conexión al iniciar el escaneo en el backend.');
    } finally {
      setIsScanning(false);
    }
  };

  // Handler to approve a breakout signal (move candidate to open positions)
  const handleApprove = (candidate, customSize) => {
    const tradeSize = customSize !== undefined ? customSize : capitalPerTrade;
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
      size: tradeSize, // Save the trade size at approval time
      pnl: 0.00,
      pnlPct: 0.00
    };

    setOpenPositions([newPosition, ...openPositions]);
    setCandidates(candidates.filter((c) => c.id !== candidate.id));
    setKpis((prev) => ({
      ...prev,
      totalTrades: prev.totalTrades + 1
    }));
  };

  // Handler to reject/ignore a candidate signal persistently
  const handleReject = (id) => {
    const candidate = candidates.find((c) => c.id === id);
    if (candidate) {
      const key = `${candidate.ticker}_${candidate.timestamp}`;
      setIgnoredCandidates((prev) => {
        if (prev.includes(key)) return prev;
        return [...prev, key];
      });
    }
    setCandidates(candidates.filter((c) => c.id !== id));
  };

  // Handler to close an open position (move it to closed trade history)
  const handleClosePosition = (id) => {
    const position = openPositions.find((p) => p.id === id);
    if (!position) return;

    // Use current live price as the exit price
    const exitPrice = position.current;
    const size = position.size || capitalPerTrade;
    const pnlPct = ((exitPrice - position.entry) / position.entry) * (position.direction === 'LONG' ? 100 : -100);
    const pnl = (pnlPct / 100) * size;
    const isWin = pnl >= 0;

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
      result: isWin ? 'WIN' : 'LOSS',
      size: size
    };

    setTradeHistory([closedTrade, ...tradeHistory]);
    setOpenPositions(openPositions.filter((p) => p.id !== id));
    setKpis((prev) => {
      const newWinningTrades = isWin ? prev.winningTrades + 1 : prev.winningTrades;
      const newLosingTrades = !isWin ? prev.losingTrades + 1 : prev.losingTrades;
      const newTotal = prev.totalTrades;
      const newWinRate = newTotal > 0 ? (newWinningTrades / newTotal) * 100 : 0;
      const newPnL = prev.todayPnL + pnl;

      return {
        ...prev,
        todayPnL: newPnL,
        todayPnLPct: (newPnL / accountBalance) * 100, // Dynamic percentage based on user's balance
        winRate: newWinRate,
        winningTrades: newWinningTrades,
        losingTrades: newLosingTrades
      };
    });
  };

  // Handler to delete a trade from history and adjust KPIs
  const handleDeleteTrade = (id) => {
    const trade = tradeHistory.find((t) => t.id === id);
    if (!trade) return;

    setTradeHistory(tradeHistory.filter((t) => t.id !== id));
    setKpis((prev) => {
      const isWin = trade.result === 'WIN';
      const newWinningTrades = isWin ? Math.max(0, prev.winningTrades - 1) : prev.winningTrades;
      const newLosingTrades = !isWin ? Math.max(0, prev.losingTrades - 1) : prev.losingTrades;
      const newTotal = Math.max(0, prev.totalTrades - 1);
      const newWinRate = newTotal > 0 ? (newWinningTrades / newTotal) * 100 : 0;
      const newPnL = prev.todayPnL - trade.pnl;

      return {
        ...prev,
        todayPnL: newPnL,
        todayPnLPct: (newPnL / accountBalance) * 100,
        winRate: newWinRate,
        totalTrades: newTotal,
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
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-900 gap-4">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-cyan-400 to-indigo-400 bg-clip-text text-transparent drop-shadow-sm">
              Breakout Scanner
            </h1>
            <p className="text-sm text-slate-400 mt-1.5 font-medium">
              Multi-Market Volume-Confirmed Breakout Detection System
            </p>
          </div>
          
          <div className="flex flex-wrap items-center gap-4 mt-4 md:mt-0">
            {/* Sizing Configurations */}
            <div className="flex items-center gap-3 bg-slate-900/40 px-3.5 py-1.5 rounded-xl border border-slate-800/80 backdrop-blur-md text-xs font-semibold">
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400">Capital/Trade:</span>
                <span className="text-slate-500 font-mono">$</span>
                <input
                  type="number"
                  value={capitalPerTrade}
                  onChange={(e) => setCapitalPerTrade(Math.max(1, Number(e.target.value)))}
                  className="w-16 bg-slate-950/80 border border-slate-800 rounded px-1.5 py-0.5 text-slate-200 focus:outline-none focus:border-cyan-500 text-right font-mono"
                  title="Capital utilizado para calcular PnL neto en cada trade"
                />
              </div>
              <div className="h-4 w-[1px] bg-slate-800" />
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400">Balance Cuenta:</span>
                <span className="text-slate-500 font-mono">$</span>
                <input
                  type="number"
                  value={accountBalance}
                  onChange={(e) => setAccountBalance(Math.max(1, Number(e.target.value)))}
                  className="w-24 bg-slate-950/80 border border-slate-800 rounded px-1.5 py-0.5 text-slate-200 focus:outline-none focus:border-cyan-500 text-right font-mono"
                  title="Balance de cuenta para calcular PnL % de la jornada"
                />
              </div>
            </div>

            <div className="flex items-center gap-4 bg-slate-900/50 px-4 py-2 rounded-xl border border-slate-800/80 backdrop-blur-md">
              {/* Force Scan Button */}
              <button
                onClick={handleForceScan}
                disabled={isScanning}
                className={`text-xs font-bold px-3 py-1.5 rounded-lg border transition-all duration-300 ${
                  isScanning
                    ? 'bg-slate-800 border-slate-700 text-slate-500 cursor-not-allowed'
                    : 'bg-blue-600/10 border-blue-500/30 text-blue-400 hover:bg-blue-600/20 hover:border-blue-500/60'
                }`}
              >
                {isScanning ? 'Escaneando...' : 'Escanear Ahora'}
              </button>
              
              <div className="h-4 w-[1px] bg-slate-800" />
              
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
              onApprove={(candidate) => {
                setApproveModalCandidate(candidate);
                setApproveModalSize(capitalPerTrade);
              }}
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
          <TradeHistory history={tradeHistory} onDeleteTrade={handleDeleteTrade} />
        </section>

        {/* Custom Modal for Approval Size */}
        {approveModalCandidate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-md transition-all duration-300">
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl max-w-sm w-full shadow-2xl backdrop-blur-xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <h3 className="text-md font-bold text-slate-100 flex items-center gap-2">
                  <span>Confirmar Entrada: {approveModalCandidate.ticker}</span>
                </h3>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  approveModalCandidate.direction === 'LONG' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                }`}>
                  {approveModalCandidate.direction}
                </span>
              </div>
              
              <div className="text-xs text-slate-400 space-y-2">
                <div className="flex justify-between">
                  <span>Precio Entrada:</span>
                  <span className="font-semibold text-slate-200">${approveModalCandidate.entry.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span>Stop Loss:</span>
                  <span className="font-semibold text-rose-400/90">${approveModalCandidate.stopLoss.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span>Take Profit:</span>
                  <span className="font-semibold text-emerald-400/90">${approveModalCandidate.takeProfit.toLocaleString()}</span>
                </div>
              </div>

              <div className="space-y-2 pt-2 border-t border-slate-800/60">
                <label className="block text-xs font-semibold text-slate-400">
                  Importe de la Operación (USD):
                </label>
                <div className="relative rounded-lg shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <span className="text-slate-500 sm:text-sm">$</span>
                  </div>
                  <input
                    type="number"
                    value={approveModalSize}
                    onChange={(e) => setApproveModalSize(Math.max(1, Number(e.target.value)))}
                    className="block w-full pl-7 pr-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-cyan-500 font-mono text-sm"
                    placeholder="1000"
                    autoFocus
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setApproveModalCandidate(null)}
                  className="flex-1 py-2 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 transition duration-200"
                >
                  Cancelar
                </button>
                <button
                  onClick={() => {
                    handleApprove(approveModalCandidate, approveModalSize);
                    setApproveModalCandidate(null);
                  }}
                  className="flex-1 py-2 rounded-lg text-xs font-bold bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-slate-100 transition duration-200 shadow-lg shadow-cyan-900/20"
                >
                  Confirmar
                </button>
              </div>
            </div>
          </div>
        )}
        
      </div>
    </div>
  );
}
