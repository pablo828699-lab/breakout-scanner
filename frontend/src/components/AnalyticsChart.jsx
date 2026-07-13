import React, { useState } from 'react';

export default function AnalyticsChart({ data }) {
  const [activeTooltip, setActiveTooltip] = useState(null);

  // SVG dimensions
  const width = 360;
  const height = 220;
  const padding = 30;

  // Max value to scale heights
  const maxVal = Math.max(...data.map(d => Math.max(d.wins, d.losses))) || 5;

  // Chart configuration
  const chartHeight = height - padding * 2;
  const chartWidth = width - padding * 2;
  const barWidth = 14;
  const groupGap = 4;
  const columnGap = chartWidth / data.length;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/20 p-6 backdrop-blur-xl h-full flex flex-col justify-between">
      <div>
        <h2 className="text-xl font-bold text-slate-100">Desempeño Diario</h2>
        <p className="text-xs text-slate-400 mt-1">Comparativa de trades ganadores vs perdedores</p>
      </div>

      <div className="relative flex justify-center items-center mt-6">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full max-w-[360px] overflow-visible">
          {/* Y Axis Grid Lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
            const y = padding + chartHeight * (1 - ratio);
            const gridValue = Math.round(maxVal * ratio);
            return (
              <g key={i} className="opacity-20">
                <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#475569" strokeWidth="1" strokeDasharray="4" />
                <text x={padding - 8} y={y + 3} fill="#94a3b8" fontSize="10" textAnchor="end">{gridValue}</text>
              </g>
            );
          })}

          {/* Render columns and bars */}
          {data.map((d, index) => {
            const xCenter = padding + index * columnGap + columnGap / 2;
            
            // Scaled heights
            const winHeight = (d.wins / maxVal) * chartHeight;
            const lossHeight = (d.losses / maxVal) * chartHeight;
            
            // Y coordinates
            const winY = height - padding - winHeight;
            const lossY = height - padding - lossHeight;

            // X coordinates for grouped bars
            const winX = xCenter - barWidth - groupGap / 2;
            const lossX = xCenter + groupGap / 2;

            return (
              <g key={d.day}>
                {/* Win Bar */}
                <rect
                  x={winX}
                  y={winY}
                  width={barWidth}
                  height={winHeight}
                  rx="3"
                  className="fill-emerald-500 hover:fill-emerald-450 cursor-pointer transition-all duration-300 drop-shadow-[0_0_6px_rgba(16,185,129,0.3)]"
                  onMouseEnter={() => setActiveTooltip({ day: d.day, type: 'Ganadoras', val: d.wins, x: winX + barWidth / 2, y: winY - 10 })}
                  onMouseLeave={() => setActiveTooltip(null)}
                />
                
                {/* Loss Bar */}
                <rect
                  x={lossX}
                  y={lossY}
                  width={barWidth}
                  height={lossHeight}
                  rx="3"
                  className="fill-rose-500 hover:fill-rose-450 cursor-pointer transition-all duration-300 drop-shadow-[0_0_6px_rgba(239,68,68,0.3)]"
                  onMouseEnter={() => setActiveTooltip({ day: d.day, type: 'Perdedoras', val: d.losses, x: lossX + barWidth / 2, y: lossY - 10 })}
                  onMouseLeave={() => setActiveTooltip(null)}
                />

                {/* X Axis Label */}
                <text
                  x={xCenter}
                  y={height - padding + 16}
                  fill="#94a3b8"
                  fontSize="11"
                  textAnchor="middle"
                  fontWeight="600"
                >
                  {d.day}
                </text>
              </g>
            );
          })}

          {/* X Axis Line */}
          <line
            x1={padding}
            y1={height - padding}
            x2={width - padding}
            y2={height - padding}
            stroke="#1e293b"
            strokeWidth="2"
          />

          {/* Simple Tooltip rendered in SVG */}
          {activeTooltip && (
            <g>
              {/* Tooltip Background */}
              <rect
                x={activeTooltip.x - 45}
                y={activeTooltip.y - 28}
                width="90"
                height="22"
                rx="4"
                fill="#0f172a"
                stroke="#334155"
                strokeWidth="1"
                className="drop-shadow-lg"
              />
              {/* Tooltip Text */}
              <text
                x={activeTooltip.x}
                y={activeTooltip.y - 14}
                fill="#f1f5f9"
                fontSize="9"
                fontWeight="bold"
                textAnchor="middle"
              >
                {activeTooltip.type}: {activeTooltip.val}
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex justify-center gap-6 mt-4 pt-2 border-t border-slate-800/40 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded bg-emerald-500 inline-block drop-shadow-[0_0_4px_rgba(16,185,129,0.4)]" />
          <span className="text-slate-400 font-medium">Ganadoras</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded bg-rose-500 inline-block drop-shadow-[0_0_4px_rgba(239,68,68,0.4)]" />
          <span className="text-slate-400 font-medium">Perdedoras</span>
        </div>
      </div>
    </div>
  );
}
