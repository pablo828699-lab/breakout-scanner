import React from 'react';

export default function CandidatePanel({ candidates, onApprove, onReject }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/20 p-6 backdrop-blur-xl">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-100">Candidatos en Tiempo Real</h2>
          <p className="text-xs text-slate-400 mt-1">Activos que califican según estrategia y esperan aprobación</p>
        </div>
        <span className="inline-flex items-center text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
          Encontrados: {candidates.length}
        </span>
      </div>

      {candidates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 border border-dashed border-slate-800 rounded-xl">
          <svg className="w-12 h-12 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <p className="text-sm text-slate-400">Ningún activo califica en este momento.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {candidates.map((candidate) => {
            const isLong = candidate.direction === 'LONG';
            const fmt = candidate.market === 'Crypto' ? '0,0.00' : '0,0.00';
            
            return (
              <div
                key={candidate.id}
                className="relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40 p-5 transition-all duration-300 hover:scale-[1.01] hover:border-slate-700 hover:bg-slate-900/60"
              >
                {/* Diagonal background indicator */}
                <div className={`absolute top-0 right-0 w-24 h-24 -mr-12 -mt-12 rotate-45 opacity-5 ${isLong ? 'bg-emerald-500' : 'bg-rose-500'}`} />

                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-bold text-slate-100 tracking-tight">{candidate.ticker}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 uppercase font-semibold">
                        {candidate.market}
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">{candidate.timestamp}</p>
                  </div>
                  
                  <span className={`inline-flex items-center text-xs font-bold px-2.5 py-1 rounded-md ${
                    isLong 
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                      : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                  }`}>
                    {isLong ? 'LONG ▲' : 'SHORT ▼'}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 mt-4 text-center">
                  <div className="bg-slate-950/40 rounded-lg p-2 border border-slate-800/30">
                    <p className="text-[9px] uppercase font-bold text-slate-500 tracking-wider">Entrada</p>
                    <p className="text-sm font-semibold text-slate-200 mt-0.5">
                      ${candidate.entry.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="bg-slate-950/40 rounded-lg p-2 border border-slate-800/30">
                    <p className="text-[9px] uppercase font-bold text-slate-500 tracking-wider">Stop Loss</p>
                    <p className="text-sm font-semibold text-rose-400/90 mt-0.5">
                      ${candidate.stopLoss.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="bg-slate-950/40 rounded-lg p-2 border border-slate-800/30">
                    <p className="text-[9px] uppercase font-bold text-slate-500 tracking-wider">Take Profit</p>
                    <p className="text-sm font-semibold text-emerald-400/90 mt-0.5">
                      ${candidate.takeProfit.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                </div>

                {/* Volume indicators and Action buttons */}
                <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800/40">
                  <div className="flex-1 max-w-[50%]">
                    <div className="flex justify-between items-center text-[10px] text-slate-400 mb-1">
                      <span>Ratio Vol: {candidate.volumeRatio}x</span>
                      <span className="font-bold text-cyan-400">Institucional</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-blue-500 to-cyan-500 rounded-full" 
                        style={{ width: `${Math.min((candidate.volumeRatio / 3) * 100, 100)}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => onReject(candidate.id)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 transition duration-200"
                    >
                      Ignorar
                    </button>
                    <button
                      onClick={() => onApprove(candidate)}
                      className="px-3 py-1.5 rounded-lg text-xs font-bold bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-slate-100 transition duration-200 shadow-lg shadow-cyan-900/20"
                    >
                      Aprobar
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
