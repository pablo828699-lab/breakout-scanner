import React from 'react';

export default function TradeHistory({ history }) {
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
                    ${trade.entry.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-4 text-right font-medium text-slate-300">
                    ${trade.exit.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-4 text-right font-medium text-slate-400">
                    ${trade.brokenLevel.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </td>
                  <td className={`py-3 px-4 text-right font-bold ${
                    isWin ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {isWin ? '+' : ''}${trade.pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
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
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
