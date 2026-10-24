import React, { useState, useEffect, useCallback } from 'react';
import { getLiveDisruptions, refreshDisruptions } from '../api/client';
import {
  AlertTriangle, AlertCircle, CloudRain, Sun, Zap, Train,
  RefreshCw, MapPin, ExternalLink, Filter, Clock, Activity,
  ShieldAlert, Layers, CheckCircle2, Flame, Bus, Calendar
} from 'lucide-react';

const CATEGORY_TABS = [
  { id: 'all', label: 'All Signals' },
  { id: 'event', label: 'Events', icon: Flame, countKey: 'event' },
  { id: 'weather', label: 'Weather Telemetry', icon: CloudRain, countKey: 'weather' },
  { id: 'transit', label: 'Transit Ops', icon: Train, countKey: 'transit' },
];

function formatEventSchedule(startTime, endTime) {
  if (!startTime) return { dateStr: 'Date TBA', timeStr: '', fullStr: 'Schedule TBA' };
  try {
    const d = new Date(startTime);
    if (isNaN(d.getTime())) return { dateStr: 'Date TBA', timeStr: '', fullStr: startTime };

    const dateStr = d.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    });

    const timeStr = d.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Asia/Kolkata',
    });

    let timeRange = timeStr;
    if (endTime) {
      const endD = new Date(endTime);
      if (!isNaN(endD.getTime())) {
        const endTimeStr = endD.toLocaleTimeString('en-IN', {
          hour: '2-digit',
          minute: '2-digit',
          hour12: true,
          timeZone: 'Asia/Kolkata',
        });
        timeRange = `${timeStr} – ${endTimeStr}`;
      }
    }

    const now = new Date();
    const todayStr = now.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    });
    const tomorrow = new Date(now.getTime() + 86400000);
    const tomorrowStr = tomorrow.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    });

    let displayDay = dateStr;
    if (dateStr === todayStr) {
      displayDay = `Today, ${dateStr}`;
    } else if (dateStr === tomorrowStr) {
      displayDay = `Tomorrow, ${dateStr}`;
    }

    return {
      dateStr: displayDay,
      timeStr: timeRange,
      fullStr: `${displayDay} • ${timeRange}`,
    };
  } catch {
    return { dateStr: startTime, timeStr: '', fullStr: startTime };
  }
}

const CORRIDOR_TABS = [
  { id: 'ALL', label: 'All Corridors', color: 'text-slate-300' },
  { id: 'RED', label: 'Red Line (Miyapur ⇄ LB Nagar)', color: 'text-rose-400', border: 'border-rose-500/50' },
  { id: 'BLUE', label: 'Blue Line (Nagole ⇄ Raidurg)', color: 'text-blue-400', border: 'border-blue-500/50' },
  { id: 'GREEN', label: 'Green Line (JBS ⇄ MGBS)', color: 'text-emerald-400', border: 'border-emerald-500/50' },
];

const SEVERITY_COLORS = {
  high: {
    badge: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
    dot: 'bg-rose-500',
    border: 'border-rose-500/30',
  },
  medium: {
    badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    dot: 'bg-amber-500',
    border: 'border-amber-500/30',
  },
  low: {
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    dot: 'bg-emerald-500',
    border: 'border-slate-800',
  },
};

const CORRIDOR_BADGES = {
  RED: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  BLUE: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  GREEN: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
};

export default function DisruptionRadar() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [corridorFilter, setCorridorFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('all');

  const fetchDisruptions = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const params = {};
      if (categoryFilter !== 'all') params.category = categoryFilter;
      if (corridorFilter !== 'ALL') params.corridor = corridorFilter;
      if (severityFilter !== 'all') params.severity = severityFilter;
      params.limit = 80;

      const res = await getLiveDisruptions(params);
      setData(res);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to fetch disruptions.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [categoryFilter, corridorFilter, severityFilter]);

  useEffect(() => {
    fetchDisruptions();
    const timer = setInterval(() => fetchDisruptions(false), 90000); // 90s background poll
    return () => clearInterval(timer);
  }, [fetchDisruptions]);

  const handleManualRefresh = async () => {
    try {
      setRefreshing(true);
      await refreshDisruptions();
      await fetchDisruptions(true);
    } catch (err) {
      setError('Refresh failed: ' + (err.message || 'Server timeout'));
      setRefreshing(false);
    }
  };

  const summary = data?.summary || {};
  const byCategory = summary.by_category || {};
  const bySeverity = summary.by_severity || {};
  const disruptions = data?.disruptions || [];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ─── Top Telemetry Banner & Actions ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-2xl border border-slate-800 backdrop-blur-sm">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2 bg-rose-500/10 text-rose-400 rounded-xl border border-rose-500/20">
              <ShieldAlert className="w-5 h-5 animate-pulse" />
            </span>
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                Live Disruption & Impact Radar
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono">
                  LIVE TELEMETRY
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Verified Live Events (AllEvents & BookMyShow) • Open-Meteo & OpenWeather Live • TGSRTC Feeder Ops
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 self-end md:self-center">
          {data?.last_updated && (
            <span className="text-xs text-slate-400 font-mono flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-500" />
              Updated {new Date(data.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={handleManualRefresh}
            disabled={refreshing || loading}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white transition disabled:opacity-50 shadow-md shadow-cyan-950/40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing Feeds...' : 'Refresh Sources'}
          </button>
        </div>
      </div>

      {/* ─── KPI Metrics Overview ─── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Total Active Signals</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-black text-white font-mono">
            {data?.total_count ?? (loading ? '...' : 0)}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex gap-2">
            <span className="text-rose-400 font-semibold">{bySeverity.high || 0} Critical</span>
            <span>•</span>
            <span className="text-amber-400 font-semibold">{bySeverity.medium || 0} Moderate</span>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Verified Events</span>
            <Flame className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-black text-amber-300 font-mono">
            {byCategory.event || 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 truncate">
            Live Verified Hyderabad Venues
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Weather Telemetry</span>
            <CloudRain className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-black text-cyan-400 font-mono">
            {byCategory.weather || 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Open-Meteo & OpenWeather Live
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Max Predicted Surge</span>
            <Zap className="w-4 h-4 text-yellow-400" />
          </div>
          <div className="text-2xl font-black text-yellow-300 font-mono">
            +{summary.max_predicted_surge_pct || 0}%
          </div>
          <div className="text-[11px] text-slate-400 mt-1 truncate">
            Peak Focus: <span className="text-cyan-300 font-medium">{summary.most_impacted_station || 'Ameerpet'}</span>
          </div>
        </div>
      </div>

      {/* ─── Filter Controls ─── */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 space-y-3.5">
        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 mr-1">
            <Filter className="w-3.5 h-3.5" /> Category:
          </span>
          {CATEGORY_TABS.map((cat) => {
            const isActive = categoryFilter === cat.id;
            const count = cat.countKey ? byCategory[cat.countKey] : data?.total_count;
            return (
              <button
                key={cat.id}
                onClick={() => setCategoryFilter(cat.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium transition flex items-center gap-1.5 border ${
                  isActive
                    ? 'bg-cyan-500/20 text-cyan-200 border-cyan-500/50 shadow-sm shadow-cyan-900/30'
                    : 'bg-slate-800/60 text-slate-400 border-slate-700/60 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                {cat.icon && <cat.icon className="w-3 h-3" />}
                {cat.label}
                {count !== undefined && (
                  <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                    isActive ? 'bg-cyan-400/30 text-cyan-100' : 'bg-slate-700 text-slate-300'
                  }`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Corridor & Severity Filters */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-slate-800/80">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 mr-1">
              <Layers className="w-3.5 h-3.5" /> Corridor:
            </span>
            {CORRIDOR_TABS.map((cor) => {
              const isActive = corridorFilter === cor.id;
              return (
                <button
                  key={cor.id}
                  onClick={() => setCorridorFilter(cor.id)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition border ${
                    isActive
                      ? `bg-slate-800 ${cor.color} border-slate-600 font-bold shadow-sm`
                      : 'bg-transparent text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/40'
                  }`}
                >
                  {cor.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">Severity:</span>
            {['all', 'high', 'medium', 'low'].map((sev) => {
              const isActive = severityFilter === sev;
              return (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={`px-2.5 py-0.5 rounded-lg text-xs capitalize transition ${
                    isActive
                      ? 'bg-slate-700 text-white font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {sev}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ─── Disruption Cards Feed ─── */}
      {loading ? (
        <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-3">
          <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
          <p className="text-sm font-medium">Aggregating live weather telemetry, events, and transit operations...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-rose-300 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      ) : disruptions.length === 0 ? (
        <div className="p-12 text-center text-slate-400 bg-slate-900/40 rounded-2xl border border-slate-800">
          <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-2 opacity-80" />
          <p className="text-sm font-medium text-slate-300">No active disruptions matching current filter criteria.</p>
          <p className="text-xs text-slate-500 mt-1">Normal service across all transit corridors.</p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs text-slate-400 px-1 flex justify-between items-center">
            <span>Showing top {disruptions.length} matching signals</span>
            <span className="font-mono text-[11px]">Sorted by Transit Criticality & Proximity</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {disruptions.map((item) => {
              const sev = SEVERITY_COLORS[item.severity] || SEVERITY_COLORS.low;
              const impact = item.impact || {};
              const isActiveNow = impact.is_active_now;
              const sched = formatEventSchedule(item.startTime, item.endTime);

              return (
                <div
                  key={item.id}
                  className={`bg-slate-900/85 border ${sev.border} rounded-2xl p-4 shadow-sm hover:border-slate-600 transition flex flex-col justify-between`}
                >
                  <div>
                    {/* Header: Category Badge, Severity, Time & Date */}
                    <div className="flex items-start justify-between gap-2 mb-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border ${sev.badge} flex items-center gap-1`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${sev.dot} animate-pulse`} />
                          {item.severity}
                        </span>

                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 capitalize font-medium">
                          {item.category.replace('_', ' ')}
                        </span>

                        {isActiveNow && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold animate-pulse">
                            ACTIVE NOW
                          </span>
                        )}
                      </div>

                      {/* Explicit Start Date and Time Badge */}
                      <div className="text-right flex-shrink-0">
                        <div className="text-xs font-semibold text-cyan-300 font-mono flex items-center justify-end gap-1 bg-slate-800/90 px-2.5 py-1 rounded-lg border border-slate-700/70">
                          <Clock className="w-3.5 h-3.5 text-cyan-400" />
                          <span>{sched.timeStr || sched.dateStr}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 font-medium mt-0.5 font-mono">
                          {sched.dateStr}
                        </div>
                      </div>
                    </div>

                    {/* Title & Location */}
                    <h3 className="text-sm font-bold text-slate-100 line-clamp-2 leading-snug">
                      {item.title}
                    </h3>

                    <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
                      <span className="truncate">{item.location}</span>
                    </p>

                    {/* Explicit Date & Time Bar */}
                    <div className="mt-2.5 px-3 py-1.5 bg-slate-950/70 border border-slate-800/80 rounded-xl flex items-center justify-between text-xs">
                      <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                        <Calendar className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                        {item.category === 'weather' ? 'Weather Observation:' : item.category === 'transit' ? 'Service Window:' : 'Event Starts:'}
                      </span>
                      <span className="font-semibold text-slate-200 font-mono text-[11px] text-right">
                        {sched.fullStr}
                      </span>
                    </div>

                    {/* Transit Impact Box */}
                    <div className="mt-2.5 p-3 bg-slate-950/70 border border-slate-800/90 rounded-xl space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-400 flex items-center gap-1">
                          <Train className="w-3.5 h-3.5 text-cyan-400" /> Nearest Metro:
                        </span>
                        <span className="font-semibold text-slate-200">
                          {impact.nearest_station_name}
                          {impact.nearest_station_distance_km !== null && (
                            <span className="text-cyan-400 font-mono ml-1">
                              ({impact.nearest_station_distance_km} km)
                            </span>
                          )}
                        </span>
                      </div>

                      {/* Affected Corridors */}
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-400">Corridors:</span>
                        <div className="flex gap-1.5">
                          {impact.affected_corridors?.map((c) => (
                            <span
                              key={c}
                              className={`text-[10px] font-bold px-1.5 py-0.2 rounded border ${
                                CORRIDOR_BADGES[c] || 'bg-slate-800 text-slate-300'
                              }`}
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Estimated Surge */}
                      {impact.estimated_surge_pct > 0 && (
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-400">Expected Surge:</span>
                          <span className="text-yellow-400 font-mono font-bold">
                            +{impact.estimated_surge_pct}% Demand
                          </span>
                        </div>
                      )}

                      {/* Impact Explanation */}
                      {impact.impact_reason && (
                        <p className="text-[11px] text-slate-300 border-t border-slate-800/80 pt-1.5 leading-relaxed">
                          ⚡ <span className="font-medium text-slate-200">{impact.impact_reason}</span>
                        </p>
                      )}

                      {/* Feeder Bus Hub */}
                      {impact.feeder_bus_hubs?.length > 0 && (
                        <div className="text-[10px] text-slate-400 flex items-center gap-1 pt-0.5">
                          <Bus className="w-3 h-3 text-emerald-400" />
                          <span className="truncate">TGSRTC Feeder: {impact.feeder_bus_hubs.join(', ')}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Footer: Source Attribution & Link */}
                  <div className="mt-3 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                    <span className="truncate font-mono">
                      Source: <span className="text-slate-400 font-medium">{item.source}</span>
                    </span>

                    {item.sourceUrl && (
                      <a
                        href={item.sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition flex-shrink-0 ml-2"
                      >
                        Official Source <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
