import React, { useState, useEffect, useMemo } from 'react';
import { autoOptimize, getStations } from '../api/client';
import LoadingSpinner from '../components/LoadingSpinner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ComposedChart, Line
} from 'recharts';
import {
  TrendingUp, Calendar, Zap, MapPin, Clock, ExternalLink,
  ChevronLeft, ChevronRight, RefreshCw, AlertCircle, Sparkles, Filter
} from 'lucide-react';
import { getDateOffset, shiftDate, formatDate } from '../utils/dateUtils';

function formatEventTime(timeStr) {
  if (!timeStr) return '';
  const timePart = timeStr.includes('T') ? timeStr.split('T')[1].substring(0, 5) : timeStr.substring(0, 5);
  const [hStr, mStr] = timePart.split(':');
  const h = parseInt(hStr, 10);
  const m = mStr || '00';
  const ampm = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${timePart} (${h12}:${m} ${ampm})`;
}

const CustomChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;
  const baseline = payload.find(p => p.dataKey === 'Baseline')?.value || 0;
  const eventSurge = payload.find(p => p.dataKey === 'Event_Surge')?.value || 0;
  const total = baseline + eventSurge;
  const surgePct = baseline > 0 ? Math.round((eventSurge / baseline) * 100) : 0;

  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-xl p-3 shadow-2xl text-xs space-y-1.5 min-w-[200px]">
      <div className="flex items-center justify-between border-b border-slate-800 pb-1 text-slate-300 font-semibold">
        <span>⏰ {label}:00 hrs</span>
        <span className="text-white font-mono font-bold">{total.toLocaleString()} pax</span>
      </div>
      <div className="flex justify-between text-cyan-400">
        <span>Baseline Commute:</span>
        <span className="font-mono font-semibold">{baseline.toLocaleString()}</span>
      </div>
      {eventSurge > 0 && (
        <div className="flex justify-between text-orange-400 font-semibold bg-orange-950/40 px-1.5 py-0.5 rounded border border-orange-500/30">
          <span>⚡ Predicted Event Surge:</span>
          <span className="font-mono">+{eventSurge.toLocaleString()} ({surgePct > 0 ? `+${surgePct}%` : ''})</span>
        </div>
      )}
      <div className="flex justify-between text-white font-bold pt-1 border-t border-slate-800">
        <span>Total Predicted Demand:</span>
        <span className="font-mono">{total.toLocaleString()}</span>
      </div>
    </div>
  );
};

export default function Trends() {
  const [selectedDate, setSelectedDate] = useState(getDateOffset(0));
  const [stations, setStations] = useState([]);
  const [selectedStation, setSelectedStation] = useState('KHA');
  const [corridorFilter, setCorridorFilter] = useState('ALL');
  const [chartMode, setChartMode] = useState('stacked'); // 'stacked' | 'comparison'
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Quick date presets
  const dateButtons = [
    { label: 'Today', offset: 0 },
    { label: 'Tomorrow', offset: 1 },
    { label: '+2 Days', offset: 2 },
    { label: '+3 Days', offset: 3 },
    { label: '+5 Days', offset: 5 },
    { label: '+7 Days', offset: 7 },
  ];

  // 1. Load station directory
  useEffect(() => {
    getStations().then(res => {
      if (Array.isArray(res)) {
        setStations(res.slice().sort((a, b) => a.stop_name.localeCompare(b.stop_name)));
      }
    }).catch(console.error);
  }, []);

  // 2. Fetch event-augmented optimization data for selectedDate
  const fetchTrendsData = async (dateStr) => {
    setLoading(true);
    setError(null);
    try {
      const res = await autoOptimize({ date: dateStr });
      setData(res);

      // Default to first station that has an active event if available
      const events = res.events_used || [];
      if (events.length > 0) {
        const evStation = events[0].nearest_station?.stop_id;
        if (evStation) {
          setSelectedStation(evStation);
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to load predicted trends');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrendsData(selectedDate);
  }, [selectedDate]);

  const handleShiftDate = (days) => {
    setSelectedDate(shiftDate(selectedDate, days));
  };

  // Identify events affecting the currently selected station
  const activeEventsForStation = useMemo(() => {
    if (!data?.events_used) return [];
    return data.events_used.filter(e => e.nearest_station?.stop_id === selectedStation);
  }, [data, selectedStation]);

  // Set of station IDs that have active events on this date
  const eventStationIds = useMemo(() => {
    if (!data?.events_used) return new Set();
    return new Set(data.events_used.map(e => e.nearest_station?.stop_id).filter(Boolean));
  }, [data]);

  // Hourly demand profile for selectedStation
  const hourlyChartData = useMemo(() => {
    if (!data?.station_demands?.[selectedStation]) return [];
    const stn = data.station_demands[selectedStation];
    const hours = [];
    for (let h = 5; h <= 23; h++) {
      const hStr = `${h}`;
      const base = stn.baseline?.[hStr] || stn.baseline?.[h] || 0;
      const pred = stn.predicted?.[hStr] || stn.predicted?.[h] || base;
      const surge = Math.max(0, pred - base);
      hours.push({
        hour: `${h}`,
        Baseline: base,
        Event_Surge: surge,
        Total: pred,
      });
    }
    return hours;
  }, [data, selectedStation]);

  // Summary Metrics
  const summaryMetrics = useMemo(() => {
    if (!data) return null;
    const events = data.events_used || [];
    const totalEventRiders = events.reduce((sum, e) => sum + (e.metro_riders || 0), 0);
    
    // Find station with highest surge
    let maxSurge = 0;
    let maxSurgeStationName = 'None';
    let maxSurgeHour = 0;

    if (data.station_demands) {
      for (const [sid, sdata] of Object.entries(data.station_demands)) {
        for (let h = 5; h <= 23; h++) {
          const hStr = `${h}`;
          const surge = (sdata.predicted?.[hStr] || 0) - (sdata.baseline?.[hStr] || 0);
          if (surge > maxSurge) {
            maxSurge = surge;
            maxSurgeHour = h;
            const matched = stations.find(s => s.stop_id === sid);
            maxSurgeStationName = matched?.stop_name || sid;
          }
        }
      }
    }

    return {
      totalEvents: events.length,
      totalEventRiders,
      maxSurge,
      maxSurgeStationName,
      maxSurgeHour,
    };
  }, [data, stations]);

  // Top stations peak comparison (Baseline vs Predicted Event Demand)
  const topStationsComparison = useMemo(() => {
    if (!data?.station_demands || !stations.length) return [];
    
    // Calculate peak predicted hour for each station
    const stationPeaks = stations.map(st => {
      const sid = st.stop_id;
      const sdata = data.station_demands[sid] || { baseline: {}, predicted: {} };
      
      let peakPred = 0;
      let peakBase = 0;
      let peakHour = 9;

      for (let h = 5; h <= 23; h++) {
        const hStr = `${h}`;
        const p = sdata.predicted?.[hStr] || sdata.predicted?.[h] || 0;
        const b = sdata.baseline?.[hStr] || sdata.baseline?.[h] || 0;
        if (p > peakPred) {
          peakPred = p;
          peakBase = b;
          peakHour = h;
        }
      }

      const hasEvent = eventStationIds.has(sid);
      return {
        stop_id: sid,
        name: st.stop_name,
        corridors: st.corridors || [],
        Baseline_Peak: peakBase,
        Event_Surge: Math.max(0, peakPred - peakBase),
        Total_Peak: peakPred,
        peakHour,
        hasEvent,
      };
    });

    // Filter by corridor if needed
    let filtered = stationPeaks;
    if (corridorFilter !== 'ALL') {
      filtered = filtered.filter(st => st.corridors.includes(corridorFilter));
    }

    // Sort by Total_Peak descending, prioritizing stations with event surges
    filtered.sort((a, b) => {
      if (a.hasEvent && !b.hasEvent) return -1;
      if (!a.hasEvent && b.hasEvent) return 1;
      return b.Total_Peak - a.Total_Peak;
    });

    return filtered.slice(0, 10);
  }, [data, stations, eventStationIds, corridorFilter]);

  const selectedStationObj = stations.find(s => s.stop_id === selectedStation);
  const isToday = selectedDate === getDateOffset(0);

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto pb-12">
      {/* ─── Top Bar: Title & Date Selector ─── */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-cyan-500/20 rounded-xl flex items-center justify-center border border-cyan-500/30">
              <TrendingUp className="w-6 h-6 text-cyan-400" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-bold text-white tracking-wide">Predicted Demand & Event Surge Trends</h1>
                {isToday && (
                  <span className="text-[10px] bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 px-2 py-0.5 rounded-full font-bold">
                    LIVE
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Dynamic passenger trends modeling baseline commutes and ML-predicted crowd influx from city events
              </p>
            </div>
          </div>

          <button
            onClick={() => fetchTrendsData(selectedDate)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold transition-colors border border-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Recalculating...' : 'Refresh Trends'}</span>
          </button>
        </div>

        {/* Compact Date Controller */}
        <div className="flex items-center gap-2.5 mt-5 pt-4 border-t border-slate-800/80 flex-wrap">
          <div className="inline-flex items-center rounded-xl bg-slate-950/80 border border-slate-800 p-1">
            <button
              onClick={() => handleShiftDate(-1)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Previous Day"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="px-3 text-xs font-semibold text-slate-200">
              {formatDate(selectedDate)}
            </div>
            <button
              onClick={() => handleShiftDate(1)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Next Day"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={() => setSelectedDate(getDateOffset(0))}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium border transition ${
              isToday
                ? 'bg-slate-800 text-cyan-300 border-cyan-500/40 font-semibold'
                : 'bg-slate-950/60 text-slate-400 border border-slate-800 hover:text-white'
            }`}
          >
            Today
          </button>

          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-slate-950/80 border border-slate-800 text-slate-300 text-xs rounded-xl px-2.5 py-1.5 focus:outline-none focus:border-cyan-500 ml-auto"
          />
        </div>

        {/* Holiday Banner if present */}
        {data?.holiday_info && (data.holiday_info.is_holiday || data.holiday_info.is_long_weekend) && (
          <div className="mt-4 p-3 bg-gradient-to-r from-purple-950/40 to-slate-900 border border-purple-500/30 rounded-xl flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="text-base">🎉</span>
              <div>
                <strong className="text-purple-300">{data.holiday_info.holiday_name}</strong>
                {data.holiday_info.is_long_weekend && (
                  <span className="ml-2 text-[10px] bg-purple-500/20 text-purple-200 border border-purple-500/30 px-2 py-0.5 rounded-full font-bold">
                    🏖️ Long Weekend ({data.holiday_info.long_weekend_span})
                  </span>
                )}
                <p className="text-[11px] text-slate-400 mt-0.5">{data.holiday_info.summary}</p>
              </div>
            </div>
            {data.holiday_info.bus_terminal_surge?.active && (
              <span className="text-[10px] text-red-300 bg-red-950/60 border border-red-500/30 px-2 py-1 rounded shrink-0 ml-2 font-mono font-semibold">
                🚌 +{data.holiday_info.bus_terminal_surge.surge_pct}% Bus Terminal Morning Exodus
              </span>
            )}
          </div>
        )}
      </div>

      {loading && !data ? (
        <div className="py-24 flex flex-col items-center justify-center text-slate-400">
          <LoadingSpinner />
          <p className="mt-4 text-sm font-medium">Computing event demand profiles & spatial splits...</p>
        </div>
      ) : error ? (
        <div className="bg-red-950/40 border border-red-500/40 rounded-xl p-6 text-red-300">
          <p className="font-bold text-base">Error Loading Predicted Trends</p>
          <p className="text-xs mt-1">{error}</p>
          <button onClick={() => fetchTrendsData(selectedDate)} className="mt-3 text-xs text-cyan-400 hover:underline">
            Retry
          </button>
        </div>
      ) : (
        <>
          {/* ─── Event Impact Summary Cards ─── */}
          {summaryMetrics && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <div className="flex items-center gap-2 text-xs text-slate-400 mb-1.5">
                  <Sparkles className="w-4 h-4 text-orange-400" />
                  <span>Predicted Event Riders</span>
                </div>
                <div className="text-2xl font-bold text-white font-mono">
                  {summaryMetrics.totalEventRiders.toLocaleString()}
                </div>
                <div className="text-[11px] text-orange-400/90 mt-1">
                  Across {summaryMetrics.totalEvents} predicted event{summaryMetrics.totalEvents === 1 ? '' : 's'}
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <div className="flex items-center gap-2 text-xs text-slate-400 mb-1.5">
                  <Zap className="w-4 h-4 text-cyan-400" />
                  <span>Highest Event Surge Station</span>
                </div>
                <div className="text-xl font-bold text-cyan-300 truncate">
                  {summaryMetrics.maxSurgeStationName}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Peak surge: <strong className="text-orange-400 font-mono">+{summaryMetrics.maxSurge.toLocaleString()}</strong> riders
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <div className="flex items-center gap-2 text-xs text-slate-400 mb-1.5">
                  <Clock className="w-4 h-4 text-emerald-400" />
                  <span>Network Peak Surge Hour</span>
                </div>
                <div className="text-2xl font-bold text-white font-mono">
                  {summaryMetrics.maxSurgeHour}:00 hrs
                </div>
                <div className="text-[11px] text-emerald-400/90 mt-1">
                  Event Ingress / Egress Window
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <div className="flex items-center gap-2 text-xs text-slate-400 mb-1.5">
                  <TrendingUp className="w-4 h-4 text-purple-400" />
                  <span>Predicted Events Active</span>
                </div>
                <div className="text-2xl font-bold text-white font-mono">
                  {summaryMetrics.totalEvents}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  {data?.weather?.description || 'Normal weather'} ({data?.weather?.temperature || 30}°C)
                </div>
              </div>
            </div>
          )}

          {/* ─── Main Trend Graph: Station Demand Profile with Predicted Event Surge ─── */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between flex-wrap gap-4 mb-4 pb-4 border-b border-slate-800">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <span>Hourly Passenger Demand Profile</span>
                  {activeEventsForStation.length > 0 && (
                    <span className="text-xs bg-orange-500/20 text-orange-400 border border-orange-500/40 px-2.5 py-0.5 rounded-full font-bold flex items-center gap-1">
                      <Zap className="w-3 h-3" /> Event Impact Active
                    </span>
                  )}
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Comparing baseline commuter turnout vs. crowd surge generated by predicted events
                </p>
              </div>

              <div className="flex items-center gap-3">
                {/* Station Dropdown */}
                <select
                  value={selectedStation}
                  onChange={(e) => setSelectedStation(e.target.value)}
                  className="bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-cyan-500"
                >
                  {stations.map(st => {
                    const hasEvent = eventStationIds.has(st.stop_id);
                    return (
                      <option key={st.stop_id} value={st.stop_id}>
                        {hasEvent ? '⚡ ' : ''}{st.stop_name} ({st.stop_id}){hasEvent ? ' — Event Venue' : ''}
                      </option>
                    );
                  })}
                </select>

                {/* View Mode Toggle */}
                <div className="bg-slate-800/80 p-0.5 rounded-lg border border-slate-700 flex text-xs">
                  <button
                    onClick={() => setChartMode('stacked')}
                    className={`px-2.5 py-1 rounded font-medium transition-colors ${
                      chartMode === 'stacked' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Stacked Surge
                  </button>
                  <button
                    onClick={() => setChartMode('comparison')}
                    className={`px-2.5 py-1 rounded font-medium transition-colors ${
                      chartMode === 'comparison' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Side-by-Side
                  </button>
                </div>
              </div>
            </div>

            {/* Event Context Banner for Selected Station */}
            {activeEventsForStation.length > 0 && (
              <div className="mb-5 p-3.5 bg-gradient-to-r from-orange-950/40 to-slate-900 border border-orange-500/40 rounded-xl space-y-2">
                {activeEventsForStation.map((ev, idx) => (
                  <div key={ev.id || idx} className="flex items-center justify-between flex-wrap gap-2 text-xs">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <strong className="text-white text-sm">{ev.name}</strong>
                        <span className="text-[10px] bg-orange-500/20 text-orange-300 border border-orange-500/40 px-2 py-0.2 rounded-full font-bold">
                          {ev.event_type}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-slate-400 text-[11px] flex-wrap">
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3 text-slate-500" /> {ev.venue_name}
                        </span>
                        <span className="flex items-center gap-1 text-cyan-400">
                          <Clock className="w-3 h-3" /> {formatEventTime(ev.start_time)} - {formatEventTime(ev.end_time)}
                        </span>
                        <span>
                          Distance: <strong className="text-white font-mono">{ev.distance_to_nearest_metro_km || 0.7} km</strong>
                        </span>
                        <span>
                          Predicted Turnout: <strong className="text-white font-mono">{(ev.expected_attendance || 0).toLocaleString()}</strong>
                        </span>
                        <span>
                          Metro Mode Share: <strong className="text-cyan-300 font-mono">{Math.round((ev.metro_fraction || 0.12) * 100)}%</strong>
                        </span>
                        <span className="text-orange-400 font-bold font-mono">
                          🚇 +{(ev.metro_riders || 0).toLocaleString()} extra metro riders
                        </span>
                      </div>
                    </div>

                    {ev.event_url && (
                      <a
                        href={ev.event_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[11px] text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 bg-cyan-950/60 hover:bg-cyan-900/60 px-2.5 py-1 rounded border border-cyan-700/50 transition-colors shrink-0"
                      >
                        <ExternalLink className="w-3 h-3" />
                        <span>View on BookMyShow</span>
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Chart Legend */}
            <div className="flex items-center gap-6 text-xs text-slate-400 mb-4">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-cyan-500" />
                Baseline Commuter Demand
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-orange-500" />
                Predicted Event & Crowd Surge
              </span>
            </div>

            {/* Chart Area */}
            <div className="h-[340px]">
              {hourlyChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  {chartMode === 'stacked' ? (
                    <BarChart data={hourlyChartData} margin={{ top: 10, right: 10, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="hour" stroke="#64748b" fontSize={11} tickFormatter={(v) => `${v}:00`} tickLine={false} axisLine={false} />
                      <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => v.toLocaleString()} />
                      <Tooltip content={<CustomChartTooltip />} />
                      <Bar dataKey="Baseline" stackId="a" fill="#0284c7" radius={[0, 0, 0, 0]} name="Baseline Commute" />
                      <Bar dataKey="Event_Surge" stackId="a" fill="#f97316" radius={[4, 4, 0, 0]} name="Event Crowd Surge" />
                    </BarChart>
                  ) : (
                    <BarChart data={hourlyChartData} margin={{ top: 10, right: 10, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="hour" stroke="#64748b" fontSize={11} tickFormatter={(v) => `${v}:00`} tickLine={false} axisLine={false} />
                      <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => v.toLocaleString()} />
                      <Tooltip content={<CustomChartTooltip />} />
                      <Bar dataKey="Baseline" fill="#0284c7" radius={[3, 3, 0, 0]} name="Baseline" />
                      <Bar dataKey="Total" fill="#f97316" radius={[3, 3, 0, 0]} name="Predicted with Event Surge" />
                    </BarChart>
                  )}
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-500 text-xs">
                  No hourly demand data available for this station.
                </div>
              )}
            </div>
          </div>

          {/* ─── Network Station Comparison: Top Stations with Event Surge ─── */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between flex-wrap gap-4 mb-4 pb-4 border-b border-slate-800">
              <div>
                <h2 className="text-lg font-bold text-white">Peak Passenger Demand Comparison (Top Stations)</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Displays peak hour demand across stations, highlighting the event surge for active venues
                </p>
              </div>

              {/* Corridor Filter */}
              <div className="flex items-center gap-1.5 bg-slate-800/80 p-0.5 rounded-lg border border-slate-700 text-xs">
                {['ALL', 'RED', 'BLUE', 'GREEN'].map(c => (
                  <button
                    key={c}
                    onClick={() => setCorridorFilter(c)}
                    className={`px-3 py-1 rounded font-semibold transition-colors ${
                      corridorFilter === c
                        ? 'bg-cyan-600 text-white'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {c === 'ALL' ? 'All Lines' : `${c} Line`}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-[380px]">
              {topStationsComparison.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topStationsComparison} margin={{ top: 15, right: 15, left: -5, bottom: 45 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis
                      dataKey="name"
                      stroke="#64748b"
                      fontSize={11}
                      angle={-25}
                      textAnchor="end"
                      interval={0}
                      tickLine={false}
                      tickFormatter={(name) => name.length > 15 ? name.substring(0, 13) + '..' : name}
                    />
                    <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => v.toLocaleString()} />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0]?.payload;
                        return (
                          <div className="bg-slate-900 border border-slate-700 rounded-xl p-3 shadow-2xl text-xs space-y-1">
                            <div className="font-bold text-white border-b border-slate-800 pb-1">
                              {d.name} {d.hasEvent ? '⚡ (Event Venue)' : ''}
                            </div>
                            <div className="text-cyan-400">Baseline Peak: <span className="font-mono">{d.Baseline_Peak?.toLocaleString()}</span></div>
                            {d.Event_Surge > 0 && (
                              <div className="text-orange-400 font-bold">
                                Predicted Event Surge: <span className="font-mono">+{d.Event_Surge?.toLocaleString()}</span>
                              </div>
                            )}
                            <div className="text-white font-bold pt-1 border-t border-slate-800">
                              Total Peak Demand: <span className="font-mono">{d.Total_Peak?.toLocaleString()}</span> (at {d.peakHour}:00)
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Bar dataKey="Baseline_Peak" stackId="a" fill="#0284c7" radius={[0, 0, 0, 0]} name="Baseline Peak" />
                    <Bar dataKey="Event_Surge" stackId="a" fill="#f97316" radius={[4, 4, 0, 0]} name="Predicted Event Surge" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-500 text-xs">
                  No station peak comparison data available.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
