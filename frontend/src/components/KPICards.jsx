import React from 'react';
import { useAnimatedValue } from '../hooks/useAnimatedValue';

export default function KPICards({ kpis }) {
  const animatedPnL = useAnimatedValue(kpis.todayPnL);
  const animatedPnLPct = useAnimatedValue(kpis.todayPnLPct);
  const animatedWinRate = useAnimatedValue(kpis.winRate);
  const animatedTotalTrades = useAnimatedValue(kpis.totalTrades);

  const isPnLPositive = kpis.todayPnL >= 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
      {/* Card 1: Today's P&L */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-slate-700 hover:shadow-[0_8px_30px_rgb(0,0,0,0.4)]">
        <div className="absolute top-0 left-0 h-[2px] w-full bg-gradient-to-r from-cyan-500 to-blue-500" />
        <div className="flex justify-between items-start">
          <div>
            <p className="text-sm font-medium text-slate-400">P&L de la Jornada</p>
            <h3 className={`text-3xl font-bold mt-2 tracking-tight ${isPnLPositive ? 'text-emerald-400 drop-shadow-[0_0_12px_rgba(16,185,129,0.2)]' : 'text-rose-400 drop-shadow-[0_0_12px_rgba(239,68,68,0.2)]'}`}>
              {isPnLPositive ? '+' : ''}${animatedPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </h3>
            <span className={`inline-flex items-center text-xs font-semibold mt-2 px-2 py-0.5 rounded-full ${isPnLPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
              {isPnLPositive ? '▲' : '▼'} {animatedPnLPct.toFixed(2)}%
            </span>
          </div>
          <div className={`p-3 rounded-xl ${isPnLPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      {/* Card 2: Win Rate */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-slate-700 hover:shadow-[0_8px_30px_rgb(0,0,0,0.4)]">
        <div className="absolute top-0 left-0 h-[2px] w-full bg-gradient-to-r from-emerald-500 to-teal-500" />
        <div className="flex justify-between items-start">
          <div>
            <p className="text-sm font-medium text-slate-400">Win Rate Actual</p>
            <h3 className="text-3xl font-bold mt-2 tracking-tight text-slate-100">
              {animatedWinRate.toFixed(1)}%
            </h3>
            <p className="text-xs text-slate-400 mt-2">
              {kpis.winningTrades} Ganadoras / {kpis.losingTrades} Perdedoras
            </p>
          </div>
          <div className="relative flex justify-center items-center">
            {/* SVG Circle Progress */}
            <svg className="w-16 h-16 transform -rotate-90">
              <circle cx="32" cy="32" r="28" className="stroke-slate-800" strokeWidth="4" fill="transparent" />
              <circle
                cx="32"
                cy="32"
                r="28"
                className="stroke-emerald-500 drop-shadow-[0_0_8px_rgba(16,185,129,0.4)]"
                strokeWidth="4"
                fill="transparent"
                strokeDasharray={2 * Math.PI * 28}
                strokeDashoffset={2 * Math.PI * 28 * (1 - kpis.winRate / 100)}
                strokeLinecap="round"
              />
            </svg>
            <span className="absolute text-[10px] font-bold text-slate-200">{Math.round(kpis.winRate)}%</span>
          </div>
        </div>
      </div>

      {/* Card 3: Total Trades */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-slate-700 hover:shadow-[0_8px_30px_rgb(0,0,0,0.4)]">
        <div className="absolute top-0 left-0 h-[2px] w-full bg-gradient-to-r from-blue-500 to-indigo-500" />
        <div className="flex justify-between items-start">
          <div>
            <p className="text-sm font-medium text-slate-400">Operaciones Ejecutadas</p>
            <h3 className="text-3xl font-bold mt-2 tracking-tight text-slate-100">
              {Math.round(animatedTotalTrades)}
            </h3>
            <span className="inline-flex items-center text-xs font-semibold mt-2 px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400">
              R:R Promedio 1:2
            </span>
          </div>
          <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2h2a2 2 0 002-2zm12-3a2 2 0 00-2-2h-2a2 2 0 00-2 2v3a2 2 0 002 2h2a2 2 0 002-2v-3zm0 0V5a2 2 0 00-2-2h-2a2 2 0 00-2 2v11a2 2 0 002 2h2a2 2 0 002-2z" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
