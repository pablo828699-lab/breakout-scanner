import React, { useState } from 'react';
import { formatTimestamp, formatRelativeTime } from '../utils/dateUtils';

const COLORS = {
  bg: '#0a0e17',
  card: '#111827',
  border: '#1e293b',
  greenPrimary: '#10b981',
  greenLight: '#34d399',
  redPrimary: '#ef4444',
  redLight: '#f87171',
  blue: '#3b82f6',
  yellow: '#f59e0b',
  purple: '#8b5cf6',
  cyan: '#06b6d4',
  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
};

function fmtPrice(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const val = Number(value);
  if (val > 1000) return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (val > 1) return val.toFixed(2);
  return val.toFixed(4);
}

function Badge({ label, bg, color }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 10px',
        borderRadius: 9999,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 0.4,
        textTransform: 'uppercase',
        backgroundColor: bg,
        color: color || '#fff',
        marginLeft: 6,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
}

function RegimeBadge({ regime = 'DEVELOPING' }) {
  const regStr = typeof regime === 'string' && regime ? regime : 'DEVELOPING';
  const label = regStr.replace(/_/g, ' ');
  let bg = 'rgba(59,130,246,0.18)';
  let color = COLORS.blue;

  if (regStr.includes('TRENDING_UP') || regStr.includes('ACCUMULATION')) {
    bg = 'rgba(16,185,129,0.2)';
    color = COLORS.greenPrimary;
  } else if (regStr.includes('DISTRIBUTION') || regStr.includes('TRENDING_DOWN')) {
    bg = 'rgba(239,68,68,0.2)';
    color = COLORS.redPrimary;
  } else if (regStr.includes('TRANSITION')) {
    bg = 'rgba(245,158,11,0.2)';
    color = COLORS.yellow;
  }

  return <Badge label={`🏛️ ${label}`} bg={bg} color={color} />;
}

function ScoreBar({ label, value, color }) {
  const val = Math.min(100, Math.max(0, Number(value) || 0));
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: COLORS.textSecondary, marginBottom: 3 }}>
        <span>{label}</span>
        <span style={{ fontWeight: 700, color: val >= 65 ? color : COLORS.textPrimary }}>{val.toFixed(0)}%</span>
      </div>
      <div style={{ height: 6, width: '100%', backgroundColor: '#1e293b', borderRadius: 3, overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            width: `${val}%`,
            backgroundColor: color,
            borderRadius: 3,
            transition: 'width 0.4s ease',
          }}
        />
      </div>
    </div>
  );
}

function Sparkline({ priceData = [], cvdData = [] }) {
  if (!priceData || priceData.length < 2) return null;

  const width = 280;
  const height = 44;
  const pad = 4;

  const minP = Math.min(...priceData);
  const maxP = Math.max(...priceData);
  const rangeP = maxP - minP || 1;

  const pointsP = priceData.map((p, i) => {
    const x = pad + (i / (priceData.length - 1)) * (width - pad * 2);
    const y = height - pad - ((p - minP) / rangeP) * (height - pad * 2);
    return `${x},${y}`;
  }).join(' ');

  let pointsC = '';
  if (cvdData && cvdData.length >= 2) {
    const minC = Math.min(...cvdData);
    const maxC = Math.max(...cvdData);
    const rangeC = maxC - minC || 1;
    pointsC = cvdData.map((c, i) => {
      const x = pad + (i / (cvdData.length - 1)) * (width - pad * 2);
      const y = height - pad - ((c - minC) / rangeC) * (height - pad * 2);
      return `${x},${y}`;
    }).join(' ');
  }

  return (
    <div style={{ backgroundColor: 'rgba(15,23,42,0.8)', padding: '8px 10px', borderRadius: 8, border: `1px solid #1e293b`, marginTop: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 4 }}>
        <span style={{ color: COLORS.cyan, fontWeight: 700 }}>● Precio (1h)</span>
        <span style={{ color: COLORS.purple, fontWeight: 700 }}>● CVD Acumulado</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 44, overflow: 'visible' }}>
        {pointsC && (
          <polyline
            fill="none"
            stroke={COLORS.purple}
            strokeWidth="1.8"
            strokeDasharray="2 2"
            points={pointsC}
          />
        )}
        <polyline
          fill="none"
          stroke={COLORS.cyan}
          strokeWidth="2"
          points={pointsP}
        />
      </svg>
    </div>
  );
}

export function OrderflowPanel({
  signals = [],
  livePrices = {},
  onApprove,
  onReject,
  onScan,
  isScanning = false,
}) {
  const [filter, setFilter] = useState('ALL');

  const safeSignals = Array.isArray(signals) ? signals : [];

  const filteredSignals = safeSignals.filter((s) => {
    if (!s || typeof s !== 'object') return false;
    const scores = s.scores || {};
    if (filter === 'CONFLUENCE') {
      return s.confluence_a_plus === true;
    }
    if (filter === 'ABSORPTION') {
      return (scores.buyer_absorption || 0) >= 60 || (scores.seller_absorption || 0) >= 60;
    }
    if (filter === 'TRAPPED') {
      return (scores.trapped_shorts || 0) >= 60 || (scores.trapped_longs || 0) >= 60;
    }
    if (filter === 'INITIATIVE') {
      return (scores.initiative_buying || 0) >= 65 || (scores.initiative_selling || 0) >= 65;
    }
    return true;
  });

  return (
    <div style={{ marginTop: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: COLORS.textPrimary, display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
            <span>🔬 Order Flow & Subasta Institucional</span>
            <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 12, backgroundColor: 'rgba(6,182,212,0.18)', color: COLORS.cyan, fontWeight: 600 }}>
              {filteredSignals.length} Activas
            </span>
          </h2>
          <p style={{ fontSize: 12, color: COLORS.textSecondary, margin: '4px 0 0 0' }}>
            Desacoples de agresión (CVD), esfuerzo vs resultado, absorción pasiva, traders atrapados y migración de valor.
          </p>
        </div>

        {/* Controls & Filter */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ display: 'flex', backgroundColor: '#111827', borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: 2 }}>
            {['ALL', 'CONFLUENCE', 'ABSORPTION', 'TRAPPED', 'INITIATIVE'].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '5px 12px',
                  borderRadius: 6,
                  border: 'none',
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                  backgroundColor: filter === f ? (f === 'CONFLUENCE' ? '#ef4444' : COLORS.cyan) : 'transparent',
                  color: filter === f ? '#0a0e17' : (f === 'CONFLUENCE' ? '#fca5a5' : COLORS.textSecondary),
                  transition: 'all 0.2s ease',
                }}
              >
                {f === 'ALL' ? 'Todos' : f === 'CONFLUENCE' ? '🔥 Confluencia A+' : f === 'ABSORPTION' ? 'Absorción' : f === 'TRAPPED' ? 'Atrapados' : 'Iniciativa'}
              </button>
            ))}
          </div>

          {onScan && (
            <button
              onClick={onScan}
              disabled={isScanning}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 14px',
                borderRadius: 8,
                border: 'none',
                backgroundColor: isScanning ? '#334155' : COLORS.cyan,
                color: '#0a0e17',
                fontSize: 12,
                fontWeight: 700,
                cursor: isScanning ? 'not-allowed' : 'pointer',
              }}
            >
              <span>{isScanning ? '⏳ Analizando...' : '🔄 Escanear Subasta'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Grid of Cards */}
      {filteredSignals.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', backgroundColor: COLORS.card, borderRadius: 12, border: `1px dashed ${COLORS.border}`, color: COLORS.textSecondary }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔬</div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>No hay desacoples o absorciones extremas en este momento</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>Las subastas monitoreadas se encuentran dentro de eficiencias normales.</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
          {filteredSignals.map((item, idx) => {
            if (!item || typeof item !== 'object') return null;
            const sym = item.symbol || item.ticker || 'N/A';
            const livePrice = (livePrices && livePrices[sym]) || item.metrics?.intra_poc || item.metrics?.current_price || 0;
            const metrics = item.metrics || {};
            const scores = item.scores || {};
            const locations = Array.isArray(item.location) ? item.location : [];

            return (
              <div
                key={`${sym}-${idx}`}
                style={{
                  backgroundColor: COLORS.card,
                  borderRadius: 12,
                  border: item.confluence_a_plus ? '1px solid #ef4444' : `1px solid ${COLORS.border}`,
                  padding: 16,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                  boxShadow: item.confluence_a_plus ? '0 4px 16px rgba(239,68,68,0.25)' : '0 4px 12px rgba(0,0,0,0.2)',
                }}
              >
                {/* Confluence A+ Banner */}
                {item.confluence_a_plus && (
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    backgroundColor: 'rgba(239,68,68,0.15)',
                    border: '1px solid #ef4444',
                    color: '#fca5a5',
                    padding: '4px 8px',
                    borderRadius: 6,
                    fontSize: 10,
                    fontWeight: 800,
                    letterSpacing: 0.5,
                    textTransform: 'uppercase'
                  }}>
                    <span>🔥 CONFLUENCIA A+:</span>
                    <span>{Array.isArray(item.confluence_tags) ? item.confluence_tags.join(' + ').replace(/_/g, ' ') : 'CONFIRMADO'}</span>
                  </div>
                )}

                {/* Card Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 17, fontWeight: 800, color: COLORS.textPrimary }}>{sym}</span>
                      <RegimeBadge regime={item.regime || 'DEVELOPING'} />
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textSecondary, marginTop: 4 }}>
                      {locations.map((loc, lIdx) => {
                        const locLabel = typeof loc === 'string' ? loc.replace(/_/g, ' ') : String(loc);
                        return (
                          <span key={`${locLabel}-${lIdx}`} style={{ marginRight: 6, color: COLORS.cyan, fontWeight: 500 }}>
                            📍 {locLabel}
                          </span>
                        );
                      })}
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 16, fontWeight: 800, color: COLORS.greenLight }}>
                      ${fmtPrice(livePrice)}
                    </div>
                    <div style={{ fontSize: 10, color: COLORS.textSecondary }}>
                      {formatRelativeTime(item.timestamp || item.last_updated)}
                    </div>
                  </div>
                </div>

                {/* Score Progress Bars */}
                <div style={{ backgroundColor: 'rgba(15,23,42,0.6)', padding: 10, borderRadius: 8, border: `1px solid #1e293b` }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: COLORS.textSecondary, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Probabilidades & Diagnósticos de Microestructura:
                  </div>
                  <ScoreBar label="Absorción Compradora (Límites en Bid)" value={scores.buyer_absorption || 0} color={COLORS.greenPrimary} />
                  <ScoreBar label="Absorción Vendedora (Límites en Ask)" value={scores.seller_absorption || 0} color={COLORS.redPrimary} />
                  <ScoreBar label="Vendedores Atrapados (Trapped Shorts)" value={scores.trapped_shorts || 0} color={COLORS.yellow} />
                  <ScoreBar label="Compradores Atrapados (Trapped Longs)" value={scores.trapped_longs || 0} color={COLORS.purple} />
                </div>

                {/* Native Visual Sparkline (Price vs CVD Trajectory) */}
                {item.sparkline_price && item.sparkline_price.length > 1 && (
                  <Sparkline priceData={item.sparkline_price} cvdData={item.sparkline_cvd} />
                )}

                {/* Metrics Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, textAlign: 'center' }}>
                  <div style={{ backgroundColor: '#0f172a', padding: '6px 8px', borderRadius: 6 }}>
                    <div style={{ fontSize: 10, color: COLORS.textSecondary }}>CVD z-score</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: (metrics.cvd_change_z || 0) >= 0 ? COLORS.greenLight : COLORS.redLight }}>
                      {typeof metrics.cvd_change_z === 'number'
                        ? (metrics.cvd_change_z > 0 ? `+${metrics.cvd_change_z.toFixed(2)}` : metrics.cvd_change_z.toFixed(2))
                        : metrics.cvd_change_z || 0}σ
                    </div>
                  </div>

                  <div style={{ backgroundColor: '#0f172a', padding: '6px 8px', borderRadius: 6 }}>
                    <div style={{ fontSize: 10, color: COLORS.textSecondary }}>Eficiencia</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: (metrics.aggression_efficiency || 1) < 0.8 ? COLORS.yellow : COLORS.blue }}>
                      {typeof metrics.aggression_efficiency === 'number' ? metrics.aggression_efficiency.toFixed(2) : (metrics.aggression_efficiency || 1)}
                    </div>
                  </div>

                  <div style={{ backgroundColor: '#0f172a', padding: '6px 8px', borderRadius: 6 }}>
                    <div style={{ fontSize: 10, color: COLORS.textSecondary }}>Developing POC</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: COLORS.textPrimary }}>
                      ${fmtPrice(metrics.intra_poc)}
                    </div>
                  </div>
                </div>

                {/* Institutional Market Story Quote */}
                {item.market_story && (
                  <div
                    style={{
                      backgroundColor: 'rgba(6,182,212,0.06)',
                      borderLeft: `3px solid ${COLORS.cyan}`,
                      padding: '8px 10px',
                      borderRadius: '0 6px 6px 0',
                      fontSize: 11,
                      color: '#cbd5e1',
                      lineHeight: 1.4,
                      fontStyle: 'italic',
                    }}
                  >
                    "{item.market_story}"
                  </div>
                )}

                {/* Action Buttons */}
                <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
                  <button
                    onClick={() => {
                      const clean = typeof sym === 'string' ? sym.replace('xyz:', '').replace('USDT', '') : '';
                      window.open(`https://www.tradingview.com/chart/?symbol=${clean}`, '_blank');
                    }}
                    style={{
                      flex: 1,
                      padding: '6px 10px',
                      borderRadius: 6,
                      border: `1px solid ${COLORS.border}`,
                      backgroundColor: '#1e293b',
                      color: COLORS.textPrimary,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    📊 TradingView
                  </button>

                  {onApprove && (
                    <button
                      onClick={() => onApprove(item)}
                      style={{
                        flex: 1,
                        padding: '6px 10px',
                        borderRadius: 6,
                        border: 'none',
                        backgroundColor: COLORS.greenPrimary,
                        color: '#0a0e17',
                        fontSize: 11,
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      ✓ Aprobar Setup
                    </button>
                  )}

                  {onReject && (
                    <button
                      onClick={() => onReject(sym)}
                      style={{
                        padding: '6px 10px',
                        borderRadius: 6,
                        border: `1px solid #334155`,
                        backgroundColor: 'transparent',
                        color: COLORS.textSecondary,
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default OrderflowPanel;
