import React, { useState, useEffect, useMemo } from 'react';
import { autoOptimize } from '../api/client';
import LoadingSpinner from '../components/LoadingSpinner';
import FrequencyTable from '../components/FrequencyTable';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  Calendar, ChevronLeft, ChevronRight, RefreshCw, Train, ArrowRight
} from 'lucide-react';
import { getDateOffset, shiftDate, formatDate } from '../utils/dateUtils';

const CORRIDORS = {
  RED: {
    id: 'RED',
    name: 'Red Line',
    terminals: 'Miyapur ⇄ LB Nagar',
    inboundRoute: 'Miyapur ➔ LB Nagar',
    outboundRoute: 'LB Nagar ➔ Miyapur',
    color: '#ef4444',
  },
  BLUE: {
    id: 'BLUE',
    name: 'Blue Line',
    terminals: 'Nagole ⇄ Raidurg',
    inboundRoute: 'Raidurg ➔ Nagole',
    outboundRoute: 'Nagole ➔ Raidurg',
    color: '#3b82f6',
  },
  GREEN: {
    id: 'GREEN',
    name: 'Green Line',
    terminals: 'JBS Parade Ground ⇄ MGBS',
    inboundRoute: 'JBS Parade Ground ➔ MGBS',
    outboundRoute: 'MGBS ➔ JBS Parade Ground',
    color: '#10b981',
  },
};

const CustomChartTooltip = ({ active, payload, label, corridorInfo }) => {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3 shadow-xl text-xs space-y-1.5 min-w-[240px]">
      <div className="flex items-center justify-between border-b border-slate-800 pb-1 font-semibold text-slate-300">
        <span>⏰ {label}</span>
        <span className="text-slate-400 font-mono">GTFS Base: {d.baseline_headway}m</span>
      </div>
      <div className="flex justify-between text-cyan-300 font-medium">
        <span>Inbound ({corridorInfo.inboundRoute}):</span>
        <span className="font-mono font-bold">{d.inbound_headway}m ({d.inbound_tph} TPH)</span>
      </div>
      <div className="flex justify-between text-rose-300 font-medium">
        <span>Outbound ({corridorInfo.outboundRoute}):</span>
        <span className="font-mono font-bold">{d.outbound_headway}m ({d.outbound_tph} TPH)</span>
      </div>
      {d.inbound_headway < d.baseline_headway && (
        <div className="text-[11px] text-emerald-400 pt-1 border-t border-slate-800">
          ⚡ Flow compressed {(d.baseline_headway - Math.min(d.inbound_headway, d.outbound_headway)).toFixed(1)}m for commuter demand
        </div>
      )}
    </div>
  );
};

export default function ScheduleView() {
  const [corridor, setCorridor] = useState('RED');
  const [date, setDate] = useState(getDateOffset(0));
  const [loading, setLoading] = useState(false);
  const [scheduleData, setScheduleData] = useState([]);
  const [recommendations, setRecommendations] = useState([]);

  const activeCorridor = CORRIDORS[corridor] || CORRIDORS.RED;
  const isToday = date === getDateOffset(0);

  useEffect(() => {
    fetchSchedule();
  }, [corridor, date]);

  const fetchSchedule = async () => {
    setLoading(true);
    try {
      const res = await autoOptimize({
        date: date,
        corridors: [corridor],
      });

      if (res?.directional_headways?.[corridor]) {
        const rows = res.directional_headways[corridor].map(r => ({
          ...r,
          hourLabel: `${String(r.hour).padStart(2, '0')}:00`,
        }));
        setScheduleData(rows);
      } else {
        setScheduleData([]);
      }
      setRecommendations(res?.recommendations || []);
    } catch (err) {
      console.error('Failed to load schedule:', err);
      setScheduleData([]);
    } finally {
      setLoading(false);
    }
  };

  const minInbound = scheduleData.length ? Math.min(...scheduleData.map(r => r.inbound_headway)) : null;
  const minOutbound = scheduleData.length ? Math.min(...scheduleData.map(r => r.outbound_headway)) : null;
  const avgBaseline = scheduleData.length ? (scheduleData.reduce((acc, r) => acc + r.baseline_headway, 0) / scheduleData.length).toFixed(1) : null;

  const relevantAlerts = useMemo(() => {
    return recommendations.filter(r => (r.corridor || '').toUpperCase().includes(corridor));
  }, [recommendations, corridor]);

  return (
    <div className="space-y-6 pb-12">
      {/* ─── Top Header: Unified & Clear ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/80">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <Train className="w-6 h-6 text-cyan-400" />
            Bidirectional Schedule Optimization
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Calibrates Inbound vs Outbound train frequencies against GTFS static timetables based on commuter directional demand.
          </p>
        </div>

        {/* Compact Controls */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="inline-flex items-center rounded-xl bg-slate-900 border border-slate-800 p-1">
            <button
              onClick={() => setDate(shiftDate(date, -1))}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Previous Day"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="px-3 text-xs font-semibold text-slate-200">
              {formatDate(date)}
            </div>
            <button
              onClick={() => setDate(shiftDate(date, 1))}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Next Day"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={() => setDate(getDateOffset(0))}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium border transition ${
              isToday
                ? 'bg-slate-800 text-cyan-300 border-cyan-500/40 font-semibold'
                : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
            }`}
          >
            Today
          </button>

          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-2.5 py-1.5 focus:outline-none focus:border-cyan-500"
          />

          <button
            onClick={fetchSchedule}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold transition shadow-md shadow-cyan-600/20 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* ─── Hero Container: Line Selection + Metrics + Chart ─── */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        {/* Line Switcher & Key Numbers */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="w-3 h-3 rounded-full" style={{ backgroundColor: activeCorridor.color }}></span>
              <h2 className="text-lg font-bold text-white tracking-wide">
                {activeCorridor.name}
              </h2>
              <span className="text-xs text-slate-400 font-mono">
                ({activeCorridor.terminals})
              </span>
            </div>
            {minInbound && (
              <p className="text-xs text-slate-400 mt-1">
                Peak Inbound: <strong className="text-cyan-300">{minInbound}m</strong> • Peak Outbound: <strong className="text-rose-300">{minOutbound}m</strong> • GTFS Average: <strong className="text-slate-300">{avgBaseline}m</strong>
              </p>
            )}
          </div>

          {/* Segmented Line Switcher */}
          <div className="inline-flex rounded-xl bg-slate-950/80 p-1 border border-slate-800">
            {['RED', 'BLUE', 'GREEN'].map(c => {
              const isSelected = corridor === c;
              const cfg = CORRIDORS[c];
              return (
                <button
                  key={c}
                  onClick={() => setCorridor(c)}
                  className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition ${
                    isSelected
                      ? 'bg-slate-800 text-white font-bold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: cfg.color }} />
                  {cfg.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* Directional Legend */}
        <div className="flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-cyan-300">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
              Inbound: {activeCorridor.inboundRoute}
            </span>
            <span className="flex items-center gap-1.5 text-rose-300">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
              Outbound: {activeCorridor.outboundRoute}
            </span>
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="w-3 h-0.5 border-b border-dashed border-slate-500 inline-block" />
              Baseline GTFS
            </span>
          </div>

          <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
            Lower minutes = tighter train frequency
          </span>
        </div>

        {/* Full-Width Chart */}
        <div style={{ height: '360px', width: '100%' }}>
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <LoadingSpinner />
            </div>
          ) : scheduleData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={scheduleData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="hourLabel"
                  stroke="#64748b"
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                  tickLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                  tickLine={false}
                  domain={[1.5, 'auto']}
                  label={{ value: 'Headway (min)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 12 }}
                />
                <Tooltip content={<CustomChartTooltip corridorInfo={activeCorridor} />} />
                <Line
                  type="monotone"
                  dataKey="baseline_headway"
                  stroke="#64748b"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="inbound_headway"
                  stroke="#38bdf8"
                  strokeWidth={3}
                  activeDot={{ r: 6, fill: '#38bdf8' }}
                  dot={{ r: 3, fill: '#38bdf8' }}
                />
                <Line
                  type="monotone"
                  dataKey="outbound_headway"
                  stroke="#f43f5e"
                  strokeWidth={3}
                  activeDot={{ r: 6, fill: '#f43f5e' }}
                  dot={{ r: 3, fill: '#f43f5e' }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
              No headway data available
            </div>
          )}
        </div>
      </div>

      {/* ─── Corridor Advisory Directives (if any) ─── */}
      {relevantAlerts.length > 0 && (
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 space-y-3">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider text-slate-300">
            Active Operating Directives for {activeCorridor.name}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {relevantAlerts.map((rec, i) => (
              <div key={i} className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/40 space-y-1.5 text-xs">
                <p className="text-slate-200 leading-relaxed font-medium">{rec.message}</p>
                {rec.action && (
                  <p className="text-cyan-400 font-semibold pt-1 border-t border-slate-800/80">
                    ➔ Action: {rec.action}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Detailed Hourly Dispatch Table ─── */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div>
          <h3 className="text-base font-bold text-white">
            Hourly Bidirectional Dispatch Schedule
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Hourly Inbound and Outbound headways, trains-per-hour (TPH), and commuter split percentages.
          </p>
        </div>

        <FrequencyTable
          rows={scheduleData}
          corridorInfo={activeCorridor}
        />
      </div>
    </div>
  );
}
