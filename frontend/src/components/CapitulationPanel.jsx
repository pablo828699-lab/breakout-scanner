import React from 'react';
import { formatTimestamp, formatRelativeTime } from '../utils/dateUtils';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function fmtPct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function fmtRatio(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(2)}:1`;
}

function fmtZone(zone, market) {
  if (!Array.isArray(zone) || zone.length < 2) return '—';
  return `${fmtPrice(zone[0], market)} – ${fmtPrice(zone[1], market)}`;
}

function fmtConfidence(value) {
  if (value == null || Number.isNaN(Number(value))) return 0;
  return Math.round(Number(value) * 100);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

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

function VerdictBadge({ verdict }) {
  const isApto = verdict === 'APTO_COMPRA_ASIMETRICA';
  return (
    <Badge
      label={isApto ? 'APTO' : verdict === 'EVITAR' ? 'EVITAR' : (verdict ?? '—')}
      bg={isApto ? 'rgba(16,185,129,0.18)' : 'rgba(239,68,68,0.18)'}
      color={isApto ? COLORS.greenPrimary : COLORS.redPrimary}
    />
  );
}

function MarketBadge({ market }) {
  if (!market) return null;
  return (
    <Badge
      label={market}
      bg="rgba(59,130,246,0.15)"
      color={COLORS.blue}
    />
  );
}

function FundamentalBadge({ ok }) {
  if (ok == null) return null;
  return ok ? (
    <Badge label="✔ Fundamental OK" bg="rgba(16,185,129,0.15)" color={COLORS.greenPrimary} />
  ) : (
    <Badge label="⚠ Fundamental" bg="rgba(245,158,11,0.15)" color={COLORS.yellow} />
  );
}

function IdiosyncraticBadge({ value }) {
  if (value == null) return null;
  return value ? (
    <Badge label="Idiosincrático" bg="rgba(59,130,246,0.13)" color={COLORS.blue} />
  ) : (
    <Badge label="Sistémico" bg="rgba(148,163,184,0.13)" color={COLORS.textSecondary} />
  );
}

function SectionTitle({ children }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: 1,
        color: COLORS.textSecondary,
        marginBottom: 6,
        marginTop: 14,
      }}
    >
      {children}
    </div>
  );
}

function LevelRow({ label, value, color }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '3px 0',
        fontSize: 13,
      }}
    >
      <span style={{ color: COLORS.textSecondary }}>{label}</span>
      <span style={{ color: color || COLORS.textPrimary, fontWeight: 600, fontFamily: 'monospace' }}>
        {value}
      </span>
    </div>
  );
}

function ConfidenceMeter({ value }) {
  const pct = fmtConfidence(value);
  let barColor = COLORS.redPrimary;
  if (pct >= 70) barColor = COLORS.greenPrimary;
  else if (pct >= 40) barColor = COLORS.yellow;

  return (
    <div style={{ marginTop: 12 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 11,
          marginBottom: 4,
        }}
      >
        <span style={{ color: COLORS.textSecondary, fontWeight: 700 }}>Puntuación Confianza</span>
        <span style={{ color: barColor, fontWeight: 800, fontFamily: 'monospace' }}>{pct}%</span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          backgroundColor: COLORS.border,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            backgroundColor: barColor,
            borderRadius: 3,
            transition: 'width 0.4s ease',
          }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card Component
// ---------------------------------------------------------------------------

function SignalCard({ signal, livePriceMap = {}, onApprove, onReject }) {
  const {
    id,
    ticker,
    market,
    verdict,
    drop_pct,
    entry,
    entry_price,
    stopLoss,
    stop_loss,
    takeProfit,
    take_profit,
    rr_ratio,
    position_size_qty,
    poc,
    vah,
    val,
    fvg_zone,
    ob_zone,
    msb_type,
    is_idiosyncratic,
    fundamental_ok,
    confidence_score,
    analysis_summary,
    timestamp,
  } = signal || {};

  // Resolve properties
  const finalEntry = entry !== undefined ? entry : entry_price;
  const finalStopLoss = stopLoss !== undefined ? stopLoss : stop_loss;
  const finalTakeProfit = takeProfit !== undefined ? takeProfit : take_profit;
  const livePrice = livePriceMap[ticker];

  // Calculate R:R dynamically if missing
  const risk = Math.abs((finalEntry || 0) - (finalStopLoss || 0));
  const reward = Math.abs((finalTakeProfit || 0) - (finalEntry || 0));
  const computedRR = (risk > 0 && reward > 0) ? (reward / risk) : null;
  const displayRR = rr_ratio || computedRR;

  // Status checks based on live price
  const isTargetHit = livePrice > 0 && finalTakeProfit > 0 && livePrice >= finalTakeProfit;
  const isStopHit = livePrice > 0 && finalStopLoss > 0 && livePrice <= finalStopLoss;
  const isDiscountZone = livePrice > 0 && finalEntry > 0 && finalStopLoss > 0 && livePrice < finalEntry && livePrice > finalStopLoss;

  const isApto = verdict === 'APTO_COMPRA_ASIMETRICA';

  return (
    <div
      style={{
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 12,
        padding: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}
    >
      {/* ---- Header ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 6,
          marginBottom: 6,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: COLORS.textPrimary }}>
            {ticker ?? '—'}
          </span>
          <MarketBadge market={market} />
          <VerdictBadge verdict={verdict} />
          {isTargetHit && (
            <Badge label="🎯 Target Alcanzado" bg="rgba(16,185,129,0.2)" color={COLORS.greenPrimary} />
          )}
          {isStopHit && (
            <Badge label="🛑 Stop Loss Hit" bg="rgba(239,68,68,0.2)" color={COLORS.redPrimary} />
          )}
          {isDiscountZone && (
            <Badge label="🏷️ Zona Descuento" bg="rgba(59,130,246,0.2)" color={COLORS.blue} />
          )}
          {signal?.inPosition && (
            <Badge label="🟢 En Posición" bg="rgba(16,185,129,0.15)" color={COLORS.greenPrimary} />
          )}
          <FundamentalBadge ok={fundamental_ok} />
          <IdiosyncraticBadge value={is_idiosyncratic} />
        </div>

        {livePrice > 0 && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: '#06b6d4',
              backgroundColor: 'rgba(6,182,212,0.15)',
              padding: '3px 10px',
              borderRadius: 6,
              border: '1px solid rgba(6,182,212,0.3)',
              fontFamily: 'monospace',
              letterSpacing: 0.5
            }}
          >
            Live: ${fmtPrice(livePrice, market)}
          </span>
        )}
      </div>

      {/* ---- Drop % ---- */}
      <div style={{ fontSize: 28, fontWeight: 800, color: COLORS.redPrimary, marginBottom: 4 }}>
        {drop_pct != null ? fmtPct(drop_pct) : '—'}
      </div>
      <div style={{ fontSize: 11, color: COLORS.textSecondary, marginBottom: 8 }}>Caída</div>

      {/* ---- Price Levels ---- */}
      <SectionTitle>Niveles de Precio</SectionTitle>
      {livePrice > 0 && (
        <div style={{ backgroundColor: 'rgba(6,182,212,0.1)', padding: '4px 8px', borderRadius: 6, marginBottom: 4, border: '1px solid rgba(6,182,212,0.2)' }}>
          <LevelRow label="Cotización en Vivo" value={`$${fmtPrice(livePrice, market)}`} color="#06b6d4" />
        </div>
      )}
      <LevelRow label="Entrada Alerta" value={fmtPrice(finalEntry, market)} color={COLORS.textPrimary} />
      <LevelRow label="Stop Loss" value={fmtPrice(finalStopLoss, market)} color={COLORS.redPrimary} />
      <LevelRow label="Objetivo" value={fmtPrice(finalTakeProfit, market)} color={COLORS.greenPrimary} />
      <LevelRow label="R:R" value={fmtRatio(displayRR)} color={COLORS.blue} />

      {/* ---- Volume Profile ---- */}
      <SectionTitle>Perfil de Volumen</SectionTitle>
      <LevelRow label="POC" value={fmtPrice(poc, market)} />
      <LevelRow label="VAH" value={fmtPrice(vah, market)} />
      <LevelRow label="VAL" value={fmtPrice(val, market)} />

      {/* ---- SMC Zones ---- */}
      <SectionTitle>Zonas SMC</SectionTitle>
      <LevelRow label="FVG" value={fmtZone(fvg_zone, market)} />
      <LevelRow label="Order Block" value={fmtZone(ob_zone, market)} />
      <LevelRow label="MSB" value={msb_type ?? '—'} />

      {/* ---- Position Size ---- */}
      <SectionTitle>Tamaño Posición</SectionTitle>
      <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.textPrimary, fontFamily: 'monospace' }}>
        {position_size_qty != null ? Number(position_size_qty).toFixed(4) : '—'}
      </div>

      {/* ---- Confidence ---- */}
      <ConfidenceMeter value={confidence_score} />

      {/* ---- Analysis Summary ---- */}
      {analysis_summary && (
        <>
          <SectionTitle>Análisis</SectionTitle>
          <div
            style={{
              fontSize: 12,
              lineHeight: 1.55,
              color: COLORS.textSecondary,
              borderLeft: `3px solid ${COLORS.border}`,
              paddingLeft: 10,
            }}
          >
            {analysis_summary}
          </div>
        </>
      )}

      {/* ---- Action Buttons ---- */}
      {isApto && (onApprove || onReject) && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            marginTop: 18,
            paddingTop: 12,
            borderTop: `1px solid ${COLORS.border}`,
          }}
        >
          {onReject && (
            <button
              onClick={() => onReject(id)}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 600,
                backgroundColor: 'rgba(30, 41, 59, 0.8)',
                color: COLORS.textSecondary,
                border: 'none',
                cursor: 'pointer',
                transition: 'background-color 0.2s',
              }}
              onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(51, 65, 85, 0.8)'}
              onMouseLeave={(e) => e.target.style.backgroundColor = 'rgba(30, 41, 59, 0.8)'}
            >
              Ignorar
            </button>
          )}
          {onApprove && (
            <button
              onClick={() => !signal?.inPosition && !isTargetHit && !isStopHit && onApprove(signal)}
              disabled={signal?.inPosition || isTargetHit || isStopHit}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 700,
                background: (signal?.inPosition || isTargetHit)
                  ? 'rgba(16, 185, 129, 0.2)' 
                  : (isStopHit ? 'rgba(239, 68, 68, 0.2)' : 'linear-gradient(to right, #2563eb, #0891b2)'),
                color: (signal?.inPosition || isTargetHit) 
                  ? COLORS.greenPrimary 
                  : (isStopHit ? COLORS.redPrimary : COLORS.textPrimary),
                border: (signal?.inPosition || isTargetHit) 
                  ? '1px solid rgba(16, 185, 129, 0.4)' 
                  : (isStopHit ? '1px solid rgba(239, 68, 68, 0.4)' : 'none'),
                cursor: (signal?.inPosition || isTargetHit || isStopHit) ? 'default' : 'pointer',
                boxShadow: (signal?.inPosition || isTargetHit || isStopHit) ? 'none' : '0 4px 6px -1px rgba(8, 145, 178, 0.15)',
                transition: 'opacity 0.2s',
              }}
              onMouseEnter={(e) => { if (!signal?.inPosition && !isTargetHit && !isStopHit) e.target.style.opacity = '0.9'; }}
              onMouseLeave={(e) => { if (!signal?.inPosition && !isTargetHit && !isStopHit) e.target.style.opacity = '1'; }}
            >
              {isTargetHit ? 'Target Alcanzado ✓' : (isStopHit ? 'Invalidado (SL Hit)' : (signal?.inPosition ? 'En Posición ✓' : 'Aprobar'))}
            </button>
          )}
        </div>
      )}

      {/* ---- Timestamp ---- */}
      {timestamp && (
        <div style={{ fontSize: 10, color: COLORS.textSecondary, marginTop: 12, textAlign: 'right' }}>
          {formatTimestamp(timestamp)} ({formatRelativeTime(timestamp)})
        </div>
      )}
    </div>
  );
}

// Asset class categorization helper
const COMMODITY_TICKERS = new Set(['GLD', 'SLV', 'USO', 'UNG', 'PPLT', 'CPER', 'GOLD', 'SILVER', 'BRENTOIL', 'NATGAS', 'PLATINUM', 'COPPER']);
const INDEX_TICKERS = new Set(['SPY', 'EWJ', 'EWY', 'SOXL', 'SPCX', 'SP500', 'JP225', 'KR200', 'XYZ100']);
const FOREX_TICKERS = new Set(['FXE', 'FXY', 'EUR', 'JPY']);

function getAssetClass(sig) {
  if (sig?.asset_class) {
    if (sig.asset_class === 'MATERIAS_PRIMAS') return 'MATERIAS PRIMAS';
    return sig.asset_class;
  }
  const ticker = (sig?.ticker || '').replace('xyz:', '').toUpperCase();
  const market = (sig?.market || '').toLowerCase();
  
  if (market.includes('crypto') || (sig?.ticker && sig.ticker.endsWith('USDT'))) return 'CRIPTO';
  if (COMMODITY_TICKERS.has(ticker)) return 'MATERIAS PRIMAS';
  if (INDEX_TICKERS.has(ticker)) return 'ÍNDICES';
  if (FOREX_TICKERS.has(ticker)) return 'FOREX';
  return 'ACCIONES';
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export default function CapitulationPanel({ signals, livePriceMap = {}, onApprove, onReject }) {
  const [activeTab, setActiveTab] = React.useState('TODOS');
  const list = Array.isArray(signals) ? signals : [];

  const categories = ['TODOS', 'ACCIONES', 'MATERIAS PRIMAS', 'ÍNDICES', 'FOREX', 'CRIPTO'];

  const counts = React.useMemo(() => {
    const acc = { TODOS: list.length, ACCIONES: 0, 'MATERIAS PRIMAS': 0, ÍNDICES: 0, FOREX: 0, CRIPTO: 0 };
    list.forEach(s => {
      const cls = getAssetClass(s);
      if (acc[cls] !== undefined) acc[cls]++;
    });
    return acc;
  }, [list]);

  const filteredList = list.filter(sig => {
    if (activeTab === 'TODOS') return true;
    return getAssetClass(sig) === activeTab;
  });

  if (list.length === 0) {
    return (
      <div
        style={{
          border: `1px solid ${COLORS.border}`,
          borderRadius: 16,
          backgroundColor: COLORS.bg,
          minHeight: 200,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 40,
        }}
      >
        <span style={{ color: COLORS.textSecondary, fontSize: 14, fontStyle: 'italic' }}>
          No hay señales de capitulación activas
        </span>
      </div>
    );
  }

  return (
    <div style={{ backgroundColor: COLORS.bg, padding: 24 }}>
      {/* Category Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {categories.map(cat => {
          const isActive = activeTab === cat;
          const count = counts[cat] || 0;
          return (
            <button
              key={cat}
              onClick={() => setActiveTab(cat)}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
                border: isActive ? '1px solid #3b82f6' : '1px solid #1e293b',
                backgroundColor: isActive ? 'rgba(59, 130, 246, 0.2)' : '#111827',
                color: isActive ? '#60a5fa' : '#94a3b8',
                transition: 'all 0.2s',
              }}
            >
              {cat} ({count})
            </button>
          );
        })}
      </div>

      {filteredList.length === 0 ? (
        <div
          style={{
            border: `1px solid ${COLORS.border}`,
            borderRadius: 16,
            backgroundColor: COLORS.card,
            padding: 40,
            textAlign: 'center',
            color: COLORS.textSecondary,
            fontSize: 14,
          }}
        >
          No hay señales activas en la categoría "{activeTab}"
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: 20,
          }}
        >
          {filteredList.map((sig, idx) => {
            const key = sig?.id || (sig?.ticker && sig?.timestamp ? `${sig.ticker}_${sig.timestamp}` : `cap_${sig?.ticker || idx}`);
            return (
              <SignalCard
                key={key}
                signal={sig}
                livePriceMap={livePriceMap}
                onApprove={onApprove}
                onReject={onReject}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
