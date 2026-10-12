import React from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

export default function DemandChart({ data, height = 220, color = '#06b6d4' }) {
  const hasEventSurge = data?.some(d => (d.event_surge || 0) > 0);

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    const item = payload[0]?.payload || {};
    const total = item.passengers ?? ((item.baseline || 0) + (item.event_surge || 0));
    const baseline = item.baseline ?? item.passengers ?? 0;
    const surge = item.event_surge ?? 0;
    const surgePct = baseline > 0 ? Math.round((surge / baseline) * 100) : 0;

    return (
      <div className="bg-slate-900/95 border border-slate-700 rounded-xl p-3 shadow-2xl text-xs space-y-1.5 min-w-[190px]">
        <div className="text-slate-300 font-semibold border-b border-slate-800 pb-1 flex justify-between items-center">
          <span>⏰ {label}:00 hrs</span>
          <span className="text-white font-mono font-bold">{total.toLocaleString()} pax</span>
        </div>
        <div className="flex justify-between text-cyan-400">
          <span>Baseline Commute:</span>
          <span className="font-mono font-bold">{baseline.toLocaleString()}</span>
        </div>
        {surge > 0 && (
          <div className="flex justify-between text-orange-400 font-semibold bg-orange-950/40 px-1.5 py-0.5 rounded border border-orange-500/30">
            <span>⚡ Event Surge:</span>
            <span className="font-mono">+{surge.toLocaleString()} ({surgePct > 0 ? `+${surgePct}%` : ''})</span>
          </div>
        )}
        <div className="flex justify-between text-white font-bold pt-1 border-t border-slate-800">
          <span>Total Demand:</span>
          <span className="font-mono">{total.toLocaleString()}</span>
        </div>
      </div>
    );
  };

  return (
    <div style={{ height, width: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="colorBaseline" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.65} />
              <stop offset="95%" stopColor={color} stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="colorSurge" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f97316" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#f97316" stopOpacity={0.15} />
            </linearGradient>
          </defs>
          <XAxis 
            dataKey="hour" 
            tickFormatter={(tick) => `${tick}:00`} 
            stroke="#64748b" 
            tick={{ fill: '#94a3b8', fontSize: 11 }} 
          />
          <YAxis 
            stroke="#64748b" 
            tick={{ fill: '#94a3b8', fontSize: 11 }} 
            tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(1)}k` : v}
          />
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" opacity={0.4} />
          <Tooltip content={<CustomTooltip />} />
          <Area 
            type="monotone" 
            dataKey="baseline" 
            stackId="1"
            stroke={color} 
            strokeWidth={2}
            fillOpacity={1} 
            fill="url(#colorBaseline)" 
            name="Baseline"
          />
          {hasEventSurge && (
            <Area 
              type="monotone" 
              dataKey="event_surge" 
              stackId="1"
              stroke="#f97316" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorSurge)" 
              name="Event Surge"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
