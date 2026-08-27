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

function isCrypto(market) {
  if (!market) return false;
  return market.toLowerCase().includes('crypto');
}

function fmtPrice(value, market) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const decimals = isCrypto(market) ? 4 : 2;
  return Number(value).toFixed(decimals);
}

function Badge({ label, bg, color }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
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

function DirectionBadge({ direction }) {
  const isLong = direction === 'LONG';
  return (
    <Badge
      label={isLong ? 'LONG ▲' : 'SHORT ▼'}
      bg={isLong ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}
      color={isLong ? COLORS.greenPrimary : COLORS.redPrimary}
    />
  );
}

function SqueezeBadge({ status }) {
  let label = status;
  let bg = 'rgba(59,130,246,0.18)';
  let color = COLORS.blue;

  if (status === 'FIRED_BULLISH') {
    label = '💥 SQUEEZE FIRED';
    bg = 'rgba(16,185,129,0.25)';
    color = COLORS.greenLight;
  } else if (status === 'FIRED_BEARISH') {
    label = '💥 SQUEEZE BREAK';
    bg = 'rgba(239,68,68,0.25)';
    color = COLORS.redLight;
  } else if (status === 'SQUEEZE_ON') {
    label = '🔒 SQUEEZE COMPRESIÓN';
    bg = 'rgba(245,158,11,0.2)';
    color = COLORS.yellow;
  } else {
    label = '⚡ EXPANSION';
    bg = 'rgba(139,92,246,0.2)';
    color = COLORS.purple;
  }

  return <Badge label={label} bg={bg} color={color} />;
}

function ConfidenceBar({ score }) {
  const pct = Math.round((score || 0) * 100);
  const color = pct >= 80 ? COLORS.greenPrimary : pct >= 65 ? COLORS.yellow : COLORS.blue;
  return (
    <div style={{ width: '100%', marginTop: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: COLORS.textSecondary, marginBottom: 2 }}>
        <span>Confianza Cuantitativa</span>
        <span style={{ fontWeight: 700, color }}>{pct}%</span>
      </div>
      <div style={{ background: '#1e293b', borderRadius: 4, height: 5, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, background: color, height: '100%', borderRadius: 4, transition: 'width 0.3s' }} />
      </div>
    </div>
  );
}

export default function MomentumPanel({
  signals = [],
  livePriceMap = {},
  onApprove,
  onReject,
  onScan,
  isScanning = false,
}) {
  const [selectedDirection, setSelectedDirection] = useState('ALL');
  const [selectedAssetClass, setSelectedAssetClass] = useState('ALL');

  const filteredSignals = signals.filter((s) => {
    if (selectedDirection !== 'ALL' && s.direction !== selectedDirection) return false;
    if (selectedAssetClass !== 'ALL' && (s.asset_class || 'ACCIONES') !== selectedAssetClass) return false;
    return true;
  });

  return (
    <div
      style={{
        background: '#0d131f',
        borderRadius: 16,
        border: `1px solid ${COLORS.border}`,
        padding: '24px 28px',
        marginBottom: 32,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
    >
      {/* Header Section */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
          borderBottom: `1px solid ${COLORS.border}`,
          paddingBottom: 20,
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              background: 'linear-gradient(135deg, rgba(139,92,246,0.3) 0%, rgba(59,130,246,0.3) 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 22,
              border: '1px solid rgba(139,92,246,0.4)',
            }}
          >
            🚀
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h2 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: COLORS.textPrimary, letterSpacing: -0.5 }}>
                Módulo de Momentum y Aceleración
              </h2>
              <span
                style={{
                  background: 'rgba(139,92,246,0.2)',
                  color: COLORS.purple,
                  fontSize: 12,
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: 12,
                  border: '1px solid rgba(139,92,246,0.3)',
                }}
              >
                {signals.length} Activos
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: COLORS.textSecondary, marginTop: 2 }}>
              Detección de Volatility Squeeze (TTM), impulso de volumen institucional (RVOL) y aceleración de tendencia (ROC).
            </p>
          </div>
        </div>

        {/* Action button & filters */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          {onScan && (
            <button
              onClick={onScan}
              disabled={isScanning}
              style={{
                background: isScanning ? '#374151' : 'linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%)',
                color: '#fff',
                border: 'none',
                padding: '8px 16px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 700,
                cursor: isScanning ? 'not-allowed' : 'pointer',
                boxShadow: isScanning ? 'none' : '0 4px 14px rgba(139,92,246,0.4)',
                transition: 'all 0.2s',
              }}
            >
              {isScanning ? '⏳ Escaneando Momentum...' : '⚡ Escanear Momentum'}
            </button>
          )}

          {/* Direction Filter */}
          <div style={{ display: 'flex', background: '#111827', borderRadius: 8, padding: 3, border: `1px solid ${COLORS.border}` }}>
            {['ALL', 'LONG', 'SHORT'].map((dir) => (
              <button
                key={dir}
                onClick={() => setSelectedDirection(dir)}
                style={{
                  background: selectedDirection === dir ? (dir === 'LONG' ? COLORS.greenPrimary : dir === 'SHORT' ? COLORS.redPrimary : '#3b82f6') : 'transparent',
                  color: selectedDirection === dir ? '#fff' : COLORS.textSecondary,
                  border: 'none',
                  borderRadius: 6,
                  padding: '5px 12px',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'background 0.2s',
                }}
              >
                {dir === 'ALL' ? 'Todos' : dir}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Signals Grid */}
      {filteredSignals.length === 0 ? (
        <div
          style={{
            background: '#111827',
            borderRadius: 12,
            border: `1px dashed ${COLORS.border}`,
            padding: '40px 20px',
            textAlign: 'center',
            color: COLORS.textSecondary,
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.textPrimary }}>No hay señales activas de momentum</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>
            El motor está monitoreando compresión de volatilidad (Squeeze) y volumen relativo en 83 activos 24/7.
          </div>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: 16,
          }}
        >
          {filteredSignals.map((signal) => {
            const signalId = `${signal.ticker}_${signal.direction}_${signal.timestamp}`;
            const livePrice = livePriceMap[signal.ticker] || signal.entry_price;
            const isLong = signal.direction === 'LONG';
            const pnlPct = isLong
              ? ((livePrice - signal.entry_price) / signal.entry_price) * 100
              : ((signal.entry_price - livePrice) / signal.entry_price) * 100;

            return (
              <div
                key={signalId}
                style={{
                  background: '#111827',
                  borderRadius: 12,
                  border: `1px solid ${COLORS.border}`,
                  padding: 18,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: 14,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {/* Accent Top Border */}
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 3,
                    background: isLong ? COLORS.greenPrimary : COLORS.redPrimary,
                  }}
                />

                {/* Card Header */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 18, fontWeight: 900, color: COLORS.textPrimary, letterSpacing: -0.5 }}>
                        {signal.ticker}
                      </span>
                      <DirectionBadge direction={signal.direction} />
                      <SqueezeBadge status={signal.squeeze_status} />
                    </div>
                    <span style={{ fontSize: 11, color: COLORS.textSecondary }}>
                      {formatRelativeTime(signal.timestamp)}
                    </span>
                  </div>

                  {/* Quantitative Stats Row */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: 8,
                      background: '#0a0e17',
                      borderRadius: 8,
                      padding: '10px 12px',
                      marginTop: 10,
                      border: '1px solid rgba(255,255,255,0.04)',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 10, color: COLORS.textSecondary, textTransform: 'uppercase' }}>RVOL (Vol)</div>
                      <div style={{ fontSize: 13, fontWeight: 800, color: signal.rvol >= 1.8 ? COLORS.greenLight : COLORS.cyan }}>
                        {signal.rvol ? `${signal.rvol.toFixed(2)}x` : '—'}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: COLORS.textSecondary, textTransform: 'uppercase' }}>ROC(10)</div>
                      <div style={{ fontSize: 13, fontWeight: 800, color: signal.roc_10 > 0 ? COLORS.greenPrimary : COLORS.redPrimary }}>
                        {signal.roc_10 ? `${signal.roc_10 > 0 ? '+' : ''}${signal.roc_10.toFixed(1)}%` : '—'}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: COLORS.textSecondary, textTransform: 'uppercase' }}>RSI (14)</div>
                      <div style={{ fontSize: 13, fontWeight: 800, color: COLORS.yellow }}>
                        {signal.rsi ? signal.rsi.toFixed(1) : '—'}
                      </div>
                    </div>
                  </div>

                  {/* Tactical Execution Levels */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: 8,
                      marginTop: 10,
                      fontSize: 12,
                    }}
                  >
                    <div>
                      <span style={{ color: COLORS.textSecondary, display: 'block', fontSize: 10 }}>📍 ENTRADA</span>
                      <span style={{ fontWeight: 700, color: COLORS.textPrimary }}>${fmtPrice(signal.entry_price, signal.market)}</span>
                    </div>
                    <div>
                      <span style={{ color: COLORS.textSecondary, display: 'block', fontSize: 10 }}>🛑 STOP LOSS</span>
                      <span style={{ fontWeight: 700, color: COLORS.redLight }}>${fmtPrice(signal.stop_loss, signal.market)}</span>
                    </div>
                    <div>
                      <span style={{ color: COLORS.textSecondary, display: 'block', fontSize: 10 }}>🎯 TARGET (R:R {signal.rr_ratio}:1)</span>
                      <span style={{ fontWeight: 700, color: COLORS.greenLight }}>${fmtPrice(signal.take_profit, signal.market)}</span>
                    </div>
                  </div>

                  {/* Live Price & Live PnL */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: 'rgba(255,255,255,0.02)',
                      padding: '8px 12px',
                      borderRadius: 8,
                      marginTop: 10,
                      border: '1px solid rgba(255,255,255,0.04)',
                    }}
                  >
                    <div>
                      <span style={{ fontSize: 10, color: COLORS.textSecondary, display: 'block' }}>PRECIO EN VIVO</span>
                      <span style={{ fontSize: 14, fontWeight: 800, color: COLORS.textPrimary }}>
                        ${fmtPrice(livePrice, signal.market)}
                      </span>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: 10, color: COLORS.textSecondary, display: 'block' }}>VARIACIÓN</span>
                      <span
                        style={{
                          fontSize: 13,
                          fontWeight: 800,
                          color: pnlPct >= 0 ? COLORS.greenPrimary : COLORS.redPrimary,
                        }}
                      >
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </span>
                    </div>
                  </div>

                  {/* Confidence Meter */}
                  <ConfidenceBar score={signal.confidence_score} />
                </div>

                {/* Action Buttons Container */}
                {(onApprove || onReject) && (
                  <div
                    style={{
                      display: 'flex',
                      gap: 8,
                      paddingTop: 10,
                      borderTop: `1px solid rgba(255,255,255,0.06)`,
                    }}
                  >
                    {onReject && (
                      <button
                        onClick={() => onReject(signalId)}
                        style={{
                          flex: 1,
                          background: 'rgba(239,68,68,0.12)',
                          color: COLORS.redLight,
                          border: '1px solid rgba(239,68,68,0.3)',
                          borderRadius: 8,
                          padding: '8px 0',
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                        }}
                      >
                        ✕ Ignorar
                      </button>
                    )}
                    {onApprove && (
                      <button
                        onClick={() => onApprove(signal)}
                        style={{
                          flex: 2,
                          background: isLong ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                          color: '#fff',
                          border: 'none',
                          borderRadius: 8,
                          padding: '8px 0',
                          fontSize: 12,
                          fontWeight: 800,
                          cursor: 'pointer',
                          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                          transition: 'all 0.2s',
                        }}
                      >
                        ✓ Aprobar Operación
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
