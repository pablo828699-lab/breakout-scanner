import React from 'react';

export default function OpenPositions({ positions, onClosePosition }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/20 p-6 backdrop-blur-xl">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-100">Posiciones Abiertas</h2>
          <p className="text-xs text-slate-400 mt-1">Operaciones actualmente en ejecución y monitoreo</p>
        </div>
        <span className="inline-flex items-center text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          Activas: {positions.length}
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 border border-dashed border-slate-800 rounded-xl">
          <svg className="w-12 h-12 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-sm text-slate-400">Sin posiciones abiertas. Esperando señales aprobadas.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                <th className="py-3 px-4">Ticker</th>
                <th className="py-3 px-4">Dirección</th>
                <th className="py-3 px-4 text-right">Precio Entrada</th>
                <th className="py-3 px-4 text-right">Precio Actual</th>
                <th className="py-3 px-4 text-right">Stop Loss</th>
                <th className="py-3 px-4 text-right">Take Profit</th>
                <th className="py-3 px-4 text-right">PnL Neto</th>
                <th className="py-3 px-4 text-right">PnL %</th>
                <th className="py-3 px-4 text-center">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40 text-sm">
              {positions.map((pos) => {
                const isLong = pos.direction === 'LONG';
                const isProfit = pos.pnl >= 0;

                return (
                  <tr key={pos.id} className="hover:bg-slate-900/30 transition duration-150">
                    <td className="py-3.5 px-4 font-bold text-slate-100">
                      <div className="flex flex-col">
                        <span>{pos.ticker}</span>
                        <span className="text-[9px] font-normal text-slate-500">{pos.market}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded ${
                        isLong ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                      }`}>
                        {isLong ? 'LONG' : 'SHORT'}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right font-medium text-slate-300">
                      ${pos.entry.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3.5 px-4 text-right font-medium text-slate-300">
                      ${pos.current.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3.5 px-4 text-right font-medium text-rose-500/80">
                      ${pos.stopLoss.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3.5 px-4 text-right font-medium text-emerald-500/80">
                      ${pos.takeProfit.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className={`py-3.5 px-4 text-right font-bold transition-all duration-300 animate-pulse ${
                      isProfit ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.2)]' : 'text-rose-400 drop-shadow-[0_0_8px_rgba(239,68,68,0.2)]'
                    }`}>
                      {isProfit ? '+' : ''}${pos.pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className={`py-3.5 px-4 text-right font-bold ${
                      isProfit ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {isProfit ? '+' : ''}{pos.pnlPct.toFixed(2)}%
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={() => onClosePosition(pos.id)}
                        className="px-2.5 py-1 rounded text-xs font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 hover:border-rose-500/40 transition duration-200"
                      >
                        Cerrar Trade
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
