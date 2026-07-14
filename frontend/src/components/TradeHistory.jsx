import React from 'react';

export default function TradeHistory({ history, onDeleteTrade }) {
  const formatPrice = (val) => {
    if (val === undefined || val === null || isNaN(val)) return '0.00';
    if (val < 1) {
      return val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
    } else if (val < 100) {
      return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    } else {
      return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/20 p-6 backdrop-blur-xl">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-100">Historial de Operaciones</h2>
          <p className="text-xs text-slate-400 mt-1">Resultados de los últimos trades completados</p>
        </div>
        <span className="inline-flex items-center text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
          Registros: {history.length}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-[10px] uppercase font-bold text-slate-400 tracking-wider">
              <th className="py-3 px-4">Ticker</th>
              <th className="py-3 px-4">Dirección</th>
              <th className="py-3 px-4 text-right">Entrada</th>
              <th className="py-3 px-4 text-right">Salida</th>
              <th className="py-3 px-4 text-right">Nivel Roto</th>
              <th className="py-3 px-4 text-right">PnL Neto</th>
              <th className="py-3 px-4 text-right">PnL %</th>
              <th className="py-3 px-4 text-center">Resultado</th>
              <th className="py-3 px-4 text-center">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/40 text-sm">
            {history.map((trade) => {
              const isWin = trade.result === 'WIN';
              
              return (
                <tr key={trade.id} className="hover:bg-slate-900/10 transition duration-150">
                  <td className="py-3 px-4 font-bold text-slate-200">
                    <div className="flex flex-col">
                      <span>{trade.ticker}</span>
                      <span className="text-[9px] font-normal text-slate-500">{trade.market}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded ${
                      trade.direction === 'LONG' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {trade.direction}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right font-medium text-slate-400">
                    ${formatPrice(trade.entry)}
                  </td>
                  <td className="py-3 px-4 text-right font-medium text-slate-300">
                    ${formatPrice(trade.exit)}
                  </td>
                  <td className="py-3 px-4 text-right font-medium text-slate-400">
                    ${formatPrice(trade.brokenLevel)}
                  </td>
                  <td className={`py-3 px-4 text-right font-bold ${
                    isWin ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {isWin ? '+' : ''}${trade.pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className={`py-3 px-4 text-right font-bold ${
                    isWin ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {isWin ? '+' : ''}{trade.pnlPct.toFixed(2)}%
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className={`inline-flex items-center text-xs font-bold px-2 py-1 rounded-md ${
                      isWin 
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' 
                        : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                    }`}>
                      {isWin ? 'WIN ✓' : 'LOSS ✗'}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    <button
                      onClick={() => onDeleteTrade(trade.id)}
                      className="p-1.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 hover:border-rose-500/40 transition duration-200"
                      title="Eliminar del historial"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
