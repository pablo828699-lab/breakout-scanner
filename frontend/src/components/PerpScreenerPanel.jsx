import React, { useState, useEffect } from 'react';

import { fetchWithTimeout } from '../services/api';

export default function PerpScreenerPanel({ apiBaseUrl = '' }) {
  const [activeSubTab, setActiveSubTab] = useState('approved');
  const [loading, setLoading] = useState(false);
  const [scanData, setScanData] = useState(() => {
    try {
      const saved = localStorage.getItem('perp_scan_cache');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [journalData, setJournalData] = useState(null);
  const [error, setError] = useState(null);

  const fetchPerpScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithTimeout(`${apiBaseUrl}/api/perp-screener`, {}, 120000);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setScanData(data);
      setError(null);
      try {
        localStorage.setItem('perp_scan_cache', JSON.stringify(data));
      } catch (e) {
        console.warn("Could not save perp_scan_cache to localStorage", e);
      }
      if (data.journal_summary) {
        setJournalData(data.journal_summary);
      }
    } catch (err) {
      console.error("Error fetching perp screener data:", err);
      if (!scanData) {
        setError("Conectando con la API del Perpetuals Screener...");
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchJournal = async () => {
    try {
      const res = await fetch(`${apiBaseUrl}/api/perp-journal`);
      if (res.ok) {
        const data = await res.json();
        setJournalData(data);
      }
    } catch (err) {
      console.error("Error fetching paper journal:", err);
    }
  };

  useEffect(() => {
    fetchPerpScan();
  }, []);

  const approvedLongs = scanData?.approved_longs || [];
  const approvedShorts = scanData?.approved_shorts || [];
  const rejected = scanData?.rejected || [];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl text-slate-100 font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-2xl">⚡</span>
            <h2 className="text-xl font-bold text-sky-400">Hyperliquid Perpetuals Screener</h2>
            <span className="bg-sky-950 text-sky-400 text-xs px-2.5 py-1 rounded-full border border-sky-800 font-mono">
              v4.0 Quant Engine
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Filtrado multi-temporal en 3 Fases (Técnico 1D+1H, Microestructura Dual DEX y Margen Aislado).
          </p>
        </div>

        <button
          onClick={fetchPerpScan}
          disabled={loading}
          className="bg-gradient-to-r from-sky-600 to-cyan-600 hover:from-sky-500 hover:to-cyan-500 text-white font-semibold text-sm px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 transition disabled:opacity-50"
        >
          {loading ? (
            <>
              <svg className="animate-spin h-4 w-4 text-white" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Escaneando Mercado...
            </>
          ) : (
            <>
              <span>🔄</span> Escanear Universo
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="bg-rose-950/60 border border-rose-800/80 text-rose-300 p-3.5 rounded-lg mb-6 text-sm flex items-center gap-2">
          <span>⚠️</span> {error}
        </div>
      )}

      {/* Sub-Navigation Tabs */}
      <div className="flex items-center gap-2 mb-6 border-b border-slate-800 text-sm font-medium">
        <button
          onClick={() => setActiveSubTab('approved')}
          className={`px-4 py-2.5 border-b-2 transition flex items-center gap-2 ${
            activeSubTab === 'approved'
              ? 'border-sky-500 text-sky-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>🎯</span> Setups Aprobados
          <span className="bg-emerald-950 text-emerald-400 text-xs px-2 py-0.5 rounded-full border border-emerald-800">
            {approvedLongs.length + approvedShorts.length}
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('rejected')}
          className={`px-4 py-2.5 border-b-2 transition flex items-center gap-2 ${
            activeSubTab === 'rejected'
              ? 'border-sky-500 text-sky-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>🚫</span> Descartes
          <span className="bg-slate-800 text-slate-400 text-xs px-2 py-0.5 rounded-full border border-slate-700">
            {rejected.length}
          </span>
        </button>

        <button
          onClick={() => {
            setActiveSubTab('journal');
            fetchJournal();
          }}
          className={`px-4 py-2.5 border-b-2 transition flex items-center gap-2 ${
            activeSubTab === 'journal'
              ? 'border-sky-500 text-sky-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>📓</span> Paper Trading Journal
          {journalData && (
            <span className={`text-xs px-2 py-0.5 rounded-full border ${
              journalData.total_pnl_usd >= 0 
                ? 'bg-emerald-950 text-emerald-400 border-emerald-800' 
                : 'bg-rose-950 text-rose-400 border-rose-800'
            }`}>
              ${journalData.total_pnl_usd} USD
            </span>
          )}
        </button>
      </div>

      {/* Tab Content: Approved Setups */}
      {activeSubTab === 'approved' && (
        <div className="space-y-6">
          {approvedLongs.length === 0 && approvedShorts.length === 0 ? (
            <div className="text-center py-12 bg-slate-950/40 rounded-xl border border-slate-800/80">
              <span className="text-4xl block mb-2">🔍</span>
              <p className="text-slate-400 text-sm font-medium">
                No hay setups en estado APROBADO en la iteración actual.
              </p>
              <p className="text-slate-500 text-xs mt-1">
                Todas las reglas cuantitativas (Técnico 1D+1H, Microestructura y Margen Aislado) están activadas estrictamente.
              </p>
            </div>
          ) : (
            <>
              {/* Approved Longs Section */}
              {approvedLongs.length > 0 && (
                <div>
                  <h3 className="text-sm font-bold text-emerald-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <span>🟢</span> Oportunidades Long ({approvedLongs.length})
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {approvedLongs.map((item, idx) => (
                      <PerpCard key={idx} setup={item} />
                    ))}
                  </div>
                </div>
              )}

              {/* Approved Shorts Section */}
              {approvedShorts.length > 0 && (
                <div>
                  <h3 className="text-sm font-bold text-rose-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <span>🔴</span> Oportunidades Short ({approvedShorts.length})
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {approvedShorts.map((item, idx) => (
                      <PerpCard key={idx} setup={item} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Tab Content: Rejected Candidates */}
      {activeSubTab === 'rejected' && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                <th className="p-3">Ticker</th>
                <th className="p-3">Símbolo HL</th>
                <th className="p-3">Dirección</th>
                <th className="p-3">Causa Principal de Rechazo</th>
                <th className="p-3">RSI 1H</th>
                <th className="p-3">Spread %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {rejected.map((item, idx) => (
                <tr key={idx} className="hover:bg-slate-800/40 transition">
                  <td className="p-3 font-semibold text-slate-200">{item.ticker}</td>
                  <td className="p-3 font-mono text-slate-400">{item.hl_symbol}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      item.direction === 'LONG' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                    }`}>
                      {item.direction}
                    </span>
                  </td>
                  <td className="p-3 text-rose-400 font-medium">{item.primary_reason}</td>
                  <td className="p-3 text-slate-300 font-mono">{item.rsi ? item.rsi.toFixed(1) : 'N/A'}</td>
                  <td className="p-3 text-slate-300 font-mono">
                    {item.microstructure ? `${(item.microstructure.spread_pct * 100).toFixed(3)}%` : 'N/A'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab Content: Paper Trading Journal */}
      {activeSubTab === 'journal' && (
        <PaperJournalView journal={journalData} />
      )}
    </div>
  );
}

function PerpCard({ setup }) {
  const isLong = setup.direction === 'LONG';
  const isLimit = setup.order_execution_mode?.includes('LIMIT');

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition shadow-lg flex flex-col justify-between">
      <div>
        {/* Card Top */}
        <div className="flex justify-between items-center mb-3">
          <div>
            <span className="text-base font-bold text-slate-100">{setup.ticker}</span>
            <span className="text-xs text-slate-500 font-mono ml-2">({setup.hl_symbol})</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${
              isLong ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'
            }`}>
              {setup.direction} {setup.leverage}x
            </span>
          </div>
        </div>

        {/* Execution Badge */}
        <div className="mb-3">
          <span className={`text-[11px] font-mono font-semibold px-2.5 py-1 rounded border inline-block ${
            isLimit 
              ? 'bg-cyan-950 text-cyan-300 border-cyan-800' 
              : 'bg-slate-900 text-slate-300 border-slate-800'
          }`}>
            ⚙️ {setup.order_execution_mode}
          </span>
        </div>

        {/* Trade Metrics */}
        <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60 mb-3">
          <div>
            <span className="text-slate-500 text-[10px] block">PRECIO ENTRADA</span>
            <span className="text-slate-200 font-bold">${setup.current_price?.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-500 text-[10px] block">POC PROFILE</span>
            <span className="text-cyan-400 font-bold">${setup.poc?.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-500 text-[10px] block">STOP LOSS</span>
            <span className="text-rose-400 font-bold">${setup.sl_price?.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-500 text-[10px] block">TAKE PROFIT (R:R)</span>
            <span className="text-emerald-400 font-bold">${setup.tp_price?.toFixed(2)} ({setup.rr_ratio?.toFixed(1)}x)</span>
          </div>
        </div>

        {/* Risk & Microstructure Details */}
        <div className="text-[11px] text-slate-400 space-y-1 bg-slate-950 p-2 rounded border border-slate-900">
          <div className="flex justify-between">
            <span>Liq Est:</span>
            <span className="font-mono text-rose-300">${setup.estimated_liq_price?.toFixed(2)}</span>
          </div>
          {setup.microstructure && (
            <>
              <div className="flex justify-between">
                <span>Funding 8h:</span>
                <span className="font-mono text-slate-300">
                  {(setup.microstructure.funding_8h * 100).toFixed(4)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span>Vol Nocional 24h:</span>
                <span className="font-mono text-slate-300">
                  ${(setup.microstructure.volume_24h / 1e6).toFixed(2)}M USD
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function PaperJournalView({ journal }) {
  if (!journal) {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        Cargando historial del Paper Trading Journal...
      </div>
    );
  }

  const openPositions = journal.open_positions || [];
  const closedHistory = journal.closed_history || [];

  return (
    <div className="space-y-6">
      {/* Metrics Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-xs text-slate-400 block">Posiciones Abiertas</span>
          <span className="text-xl font-bold text-sky-400">{journal.open_count}</span>
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-xs text-slate-400 block">Trades Cerrados</span>
          <span className="text-xl font-bold text-slate-200">{journal.closed_count}</span>
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-xs text-slate-400 block">PnL USD Acumulado</span>
          <span className={`text-xl font-bold ${journal.total_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            ${journal.total_pnl_usd}
          </span>
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-xs text-slate-400 block">Win Rate</span>
          <span className="text-xl font-bold text-amber-400">{journal.win_rate_pct}%</span>
        </div>
      </div>

      {/* Open Positions Table */}
      <div>
        <h4 className="text-sm font-bold text-slate-200 mb-3 flex items-center gap-2">
          <span>🟢</span> Posiciones Simuladas En Vivo ({openPositions.length})
        </h4>
        {openPositions.length === 0 ? (
          <p className="text-xs text-slate-500 italic">No hay posiciones en curso.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="bg-slate-950 text-slate-400 border-b border-slate-800">
                  <th className="p-2.5">Ticker</th>
                  <th className="p-2.5">Dirección</th>
                  <th className="p-2.5">Entrada</th>
                  <th className="p-2.5">Precio Actual</th>
                  <th className="p-2.5">SL</th>
                  <th className="p-2.5">TP</th>
                  <th className="p-2.5">PnL USD</th>
                  <th className="p-2.5">ROE %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {openPositions.map((pos) => (
                  <tr key={pos.id} className="hover:bg-slate-800/40">
                    <td className="p-2.5 font-bold text-slate-200">{pos.ticker}</td>
                    <td className="p-2.5 font-bold">{pos.direction} {pos.leverage}x</td>
                    <td className="p-2.5">${pos.entry_price?.toFixed(2)}</td>
                    <td className="p-2.5 text-cyan-300">${pos.current_price?.toFixed(2)}</td>
                    <td className="p-2.5 text-rose-400">${pos.sl_price?.toFixed(2)}</td>
                    <td className="p-2.5 text-emerald-400">${pos.tp_price?.toFixed(2)}</td>
                    <td className={`p-2.5 font-bold ${pos.pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      ${pos.pnl_usd}
                    </td>
                    <td className={`p-2.5 font-bold ${pos.roe_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pos.roe_pct}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
